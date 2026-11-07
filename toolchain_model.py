"""Optional tool discovery and bounded local execution without shell commands."""
from __future__ import annotations

import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import tempfile
import time

from hdl_model import import_verilog, parse

VERSION_ARGS = {"iverilog": ("-V",), "vvp": ("-V",), "yosys": ("-V",),
                "verilator": ("--version",), "gtkwave": ("--version",)}


def detect_tool(name):
    if name not in VERSION_ARGS: raise ValueError("Unknown tool")
    path = shutil.which(name)
    if path is None:
        return {"name": name, "installed": False, "path": None, "version": None,
                "available": False, "last_verification": "Executable not installed"}
    try:
        result = subprocess.run([path, *VERSION_ARGS[name]], capture_output=True, text=True,
                                timeout=3, check=False)
        output = (result.stdout or result.stderr).strip()[:2048]
        first = output.splitlines()[0] if output else "Unknown"
        return {"name": name, "installed": True, "path": path, "version": first,
                "available": result.returncode == 0,
                "last_verification": "Version probe passed" if result.returncode == 0 else
                f"Version probe returned {result.returncode}: {first}"}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"name": name, "installed": True, "path": path, "version": None,
                "available": False, "last_verification": str(error)}


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def run_restricted(command, folder, *, timeout=30, cancelled=None):
    """Run a fixed argv inside Bubblewrap; cancel/timeout kill the process group."""
    bwrap = shutil.which("bwrap")
    if bwrap is None: raise ValueError("Bubblewrap is required to run external HDL tools")
    folder = Path(folder).resolve()
    args = [bwrap, "--die-with-parent", "--new-session", "--unshare-all"]
    for path in ("/usr", "/lib", "/lib64", "/bin"):
        if Path(path).exists(): args += ["--ro-bind", path, path]
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
             "--bind", str(folder), "/work", "--chdir", "/work",
             "--setenv", "HOME", "/work", "--setenv", "TMPDIR", "/tmp", "--", *command]
    log = folder / "toolchain.log"
    start = time.monotonic()
    with log.open("wb") as output:
        process = subprocess.Popen(args, cwd=folder, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True, preexec_fn=_limits)
        try:
            while process.poll() is None:
                if cancelled and cancelled():
                    raise ValueError("External tool run cancelled")
                if time.monotonic() - start > timeout:
                    raise ValueError(f"External tool exceeded {timeout} seconds")
                time.sleep(0.05)
        except ValueError:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
            raise
    text = log.read_bytes()[:1024 * 1024].decode("utf-8", errors="replace")
    if process.returncode:
        raise ValueError(f"External tool exited {process.returncode}: {text[-4000:]}")
    return text


def _validated_design(source, top):
    if top not in parse(source): raise ValueError(f"Top module {top} is missing")
    import_verilog(source, top)


def run_yosys(source, top, *, cancelled=None):
    if shutil.which("yosys") is None: raise ValueError("Yosys is not installed")
    _validated_design(source, top)
    with tempfile.TemporaryDirectory(prefix="logicspace-yosys-") as temporary:
        folder = Path(temporary)
        (folder / "design.sv").write_text(source, encoding="utf-8")
        script = ("read_verilog -sv design.sv\n" + f"hierarchy -check -top {top}\n" +
                  f"synth -top {top}\n" + "write_json netlist.json\nstat\n")
        (folder / "build.ys").write_text(script, encoding="utf-8")
        log = run_restricted([shutil.which("yosys"), "-s", "build.ys"], folder, cancelled=cancelled)
        path = folder / "netlist.json"
        if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Yosys did not produce a valid bounded netlist file")
        netlist = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(netlist, dict) or top not in netlist.get("modules", {}):
            raise ValueError("Yosys netlist does not contain the requested top module")
        return {"top": top, "modules": list(netlist["modules"]), "log": log,
                "netlist": netlist}


def run_verilator_lint(source, top, *, cancelled=None):
    if shutil.which("verilator") is None: raise ValueError("Verilator is not installed")
    _validated_design(source, top)
    with tempfile.TemporaryDirectory(prefix="logicspace-verilator-") as temporary:
        folder = Path(temporary)
        (folder / "design.sv").write_text(source, encoding="utf-8")
        log = run_restricted([shutil.which("verilator"), "--lint-only", "--top-module", top,
                              "design.sv"], folder, cancelled=cancelled)
        return {"top": top, "log": log}


def open_vcd(path):
    executable = shutil.which("gtkwave")
    if executable is None: raise ValueError("GTKWave is not installed")
    target = Path(path).resolve()
    if not target.is_file() or target.suffix.lower() != ".vcd":
        raise ValueError("Choose an existing VCD waveform file")
    return subprocess.Popen([executable, str(target)], start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

"""Optional, isolated Icarus checks for the supported HDL subset."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from hdl_model import import_verilog, parse, run_vectors
from toolchain_model import run_restricted


def external_availability():
    missing = [name for name in ("iverilog", "vvp", "bwrap") if shutil.which(name) is None]
    if missing:
        return False, "External HDL tools unavailable: " + ", ".join(missing)
    with tempfile.TemporaryDirectory(prefix="logicspace-hdl-check-") as temporary:
        try: _sandbox(["/usr/bin/true"], temporary, timeout=2)
        except ValueError as error: return False, "HDL sandbox unavailable: " + str(error)
    return True, "Available"


def _sandbox(command, folder, timeout=5):
    return run_restricted(command, folder, timeout=timeout)


def run_external_vectors(source, vectors, top=None, *, vcd_path=None):
    """Compile and run a generated testbench in a private, restricted directory.

    Arbitrary HDL testbench text is never executed. The parser must first accept
    the DUT, and only validated numeric vectors are rendered into testbench code.
    """
    available, reason = external_availability()
    if not available: raise ValueError(reason)
    modules = parse(source)
    module_name = top or list(modules)[-1]
    clocks = {}
    resets = {}
    for module in modules.values():
        for procedure in module.procedures:
            if procedure.kind == "clocked":
                previous = clocks.setdefault(procedure.clock, procedure.edge)
                if previous != procedure.edge:
                    raise ValueError(f"External comparison cannot initialize both edges of {procedure.clock}")
                if procedure.reset:
                    inactive = 0 if procedure.reset_edge == "posedge" else 1
                    previous_reset = resets.setdefault(procedure.reset, inactive)
                    if previous_reset != inactive:
                        raise ValueError(f"Conflicting reset polarity for {procedure.reset}")
    if clocks:
        if not vectors:
            raise ValueError("Sequential external comparison needs at least one vector")
        previous_values = {clock: 0 if edge == "posedge" else 1 for clock, edge in clocks.items()}
        for clock, edge in clocks.items():
            expected = previous_values[clock]
            if vectors[0].get("inputs", {}).get(clock) != expected:
                raise ValueError(f"First vector must start {clock}={expected} before its {edge} events")
        for index, vector in enumerate(vectors):
            drive = vector.get("inputs", {})
            for clock in clocks:
                if vector.get("step") is not True and drive.get(clock) != previous_values[clock]:
                    raise ValueError(f"Vector {index}: clock changes require step=true")
                previous_values[clock] = drive.get(clock)
    circuit = import_verilog(source, top)
    reference = run_vectors(source, vectors, top)
    ins = {c.params["label"]: c.params.get("width", 1) for c in circuit.components.values()
           if c.kind in ("INPUT", "Bus Input")}
    outs = {c.params["label"]: c.params.get("width", 1) for c in circuit.components.values()
            if c.kind in ("OUTPUT", "Bus Output")}
    if any(clock not in ins for clock in clocks) or any(reset not in ins for reset in resets):
        raise ValueError("External comparison needs clocks/resets exposed by name on the top module")
    lines = ["module logicspace_tb;"]
    for name, width in ins.items():
        initial = ("1" if clocks.get(name) == "negedge" or resets.get(name) == 1 else "0") * width
        lines.append(f"  reg {f'[{width-1}:0] ' if width > 1 else ''}{name} = {width}'b{initial};")
    for name, width in outs.items(): lines.append(f"  wire {f'[{width-1}:0] ' if width > 1 else ''}{name};")
    connections = ", ".join(f".{name}({name})" for name in (*ins, *outs))
    lines.append(f"  {module_name} dut ({connections});")
    lines.append("  initial begin")
    if vcd_path is not None:
        if Path(vcd_path).suffix.lower() != ".vcd":
            raise ValueError("VCD export path must end in .vcd")
        lines.append('    $dumpfile("wave.vcd");')
        lines.append("    $dumpvars(0, logicspace_tb);")
    lines.append("    #1; // establish clock baseline before the first vector")
    for index, vector in enumerate(vectors):
        for name, width in sorted(ins.items(), key=lambda item: item[0] in clocks):
            value = vector["inputs"][name]
            literal = f"{width}'b" + ("x" * width if value is None else format(value, f"0{width}b"))
            lines.append(f"    {name} = {literal};")
        lines.append("    #1; // settle combinational logic and nonblocking assignments")
        for name in outs:
            lines.append(f'    $display("LS:{index}:{name}:%b", {name});')
    lines += ["    $finish;", "  end", "endmodule"]
    with tempfile.TemporaryDirectory(prefix="logicspace-hdl-") as temporary:
        folder = Path(temporary)
        (folder / "design.sv").write_text(source, encoding="utf-8")
        (folder / "testbench.sv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        _sandbox([shutil.which("iverilog"), "-g2012", "-s", "logicspace_tb", "-o", "out.vvp",
                  "design.sv", "testbench.sv"], folder)
        output = _sandbox([shutil.which("vvp"), "out.vvp"], folder)
        if vcd_path is not None:
            waveform = folder / "wave.vcd"
            if not waveform.is_file() or not 0 < waveform.stat().st_size <= 64 * 1024 * 1024:
                raise ValueError("Icarus did not produce a bounded VCD waveform")
            with waveform.open("rb") as stream:
                header = stream.read(65536)
                stream.seek(max(0, waveform.stat().st_size - 65536))
                tail = stream.read()
            if b"$enddefinitions" not in header or b"#" not in tail:
                raise ValueError("Icarus produced an invalid or empty VCD waveform")
            destination = Path(vcd_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(prefix=".logicspace-vcd-", dir=destination.parent)
            os.close(descriptor)
            temporary_path = Path(temp_name)
            try:
                shutil.copyfile(waveform, temporary_path)
                os.replace(temporary_path, destination)
            finally:
                if temporary_path.exists(): temporary_path.unlink()
    actual = [{} for _ in vectors]
    for line in output.splitlines():
        match = re.fullmatch(r"LS:(\d+):([A-Za-z_][A-Za-z_0-9$]*):([01xXzZ]+)", line.strip())
        if not match: continue
        index, name, bits = int(match[1]), match[2], match[3].lower()
        if index >= len(actual) or name not in outs:
            raise ValueError("External simulator returned an unexpected signal")
        actual[index][name] = None if any(bit in bits for bit in "xz") else int(bits, 2)
    if any(set(row) != set(outs) for row in actual):
        raise ValueError("External simulator omitted one or more results")
    return [{"step": index, "external": row, "logicspace": reference[index]["actual"],
             "equivalent": row == reference[index]["actual"]} for index, row in enumerate(actual)]


def export_report(path, results):
    path = Path(path)
    if path.suffix.lower() != ".json": raise ValueError("HDL report must end in .json")
    path.write_text(json.dumps({"format": "logicspace-hdl-report", "version": 1,
                                "results": results}, indent=2), encoding="utf-8")


def first_equivalence_mismatch(rows):
    """Return the earliest externally measured mismatch, or None."""
    for row in rows:
        external, internal = row["external"], row["logicspace"]
        for name in sorted(set(external) | set(internal)):
            if external.get(name) != internal.get(name):
                return {"step": row["step"], "signal": name,
                        "external": external.get(name), "logicspace": internal.get(name)}
    return None

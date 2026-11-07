"""Validated local FPGA project packages; device data is always user supplied."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import zipfile

from hdl_model import HDLError, import_verilog, parse

PROFILE_FORMAT = "logicspace-fpga-profile"
WORKSPACE_FORMAT = "logicspace-fpga-workspace"
PACKAGE_FORMAT = "logicspace-fpga-package"
VERSION = 1
_IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9$]*\Z")
_PIN = re.compile(r"[A-Za-z0-9_.:+-]+\Z")


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def valid(self): return not self.errors


def blank_workspace():
    return {"format": WORKSPACE_FORMAT, "version": VERSION, "name": "FPGA project",
            "top": "", "files": {}, "profile": None, "pins": {}, "clocks_mhz": {},
            "signal_groups": {}, "build": {"synthesis": "yosys", "constraints": "ice40-pcf"}}


def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get("format") != PROFILE_FORMAT or profile.get("version") != VERSION:
        raise ValueError("Invalid FPGA device profile format or version")
    for key in ("manufacturer", "family", "device", "package", "source"):
        if not isinstance(profile.get(key), str) or not profile[key].strip() or len(profile[key]) > 500:
            raise ValueError(f"Device profile needs {key}; use 'Unknown' only when truly unknown")
    pins = profile.get("pins")
    clocks = profile.get("clock_pins")
    if (not isinstance(pins, list) or not pins or len(pins) > 4096 or
            any(not isinstance(pin, str) or not _PIN.fullmatch(pin) for pin in pins) or
            len(pins) != len(set(pins)) or not isinstance(clocks, list) or
            any(pin not in pins for pin in clocks) or len(clocks) != len(set(clocks))):
        raise ValueError("Device profile needs unique valid pins and a clock-pin subset")
    if profile.get("constraint_format") not in ("ice40-pcf", "unknown"):
        raise ValueError("Only nextpnr iCE40 PCF or unknown constraint format is supported")
    requirements = profile.get("toolchain_requirements", [])
    if (not isinstance(requirements, list) or len(requirements) > 16 or
            any(not isinstance(item, str) or not item.strip() or len(item) > 100
                for item in requirements)):
        raise ValueError("Device profile toolchain requirements must be a short string list")
    return deepcopy(profile)


def load_profile(path):
    return validate_profile(json.loads(Path(path).read_text(encoding="utf-8")))


def save_profile(profile, path):
    data = validate_profile(profile)
    target = Path(path)
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")


def validate_workspace_schema(data):
    if not isinstance(data, dict) or data.get("format") != WORKSPACE_FORMAT or data.get("version") != VERSION:
        raise ValueError("Invalid FPGA workspace format or version")
    if (not isinstance(data.get("name"), str) or not isinstance(data.get("top"), str) or
            not isinstance(data.get("files"), dict) or len(data["files"]) > 64 or
            not isinstance(data.get("pins"), dict) or not isinstance(data.get("clocks_mhz"), dict) or
            not isinstance(data.get("signal_groups"), dict) or not isinstance(data.get("build"), dict)):
        raise ValueError("Invalid FPGA workspace fields")
    for name, source in data["files"].items():
        if (not isinstance(name, str) or Path(name).name != name or
                Path(name).suffix.lower() not in (".v", ".sv") or not isinstance(source, str) or
                len(source.encode("utf-8")) > 1024 * 1024):
            raise ValueError("HDL files must have simple .v/.sv names and be at most 1 MiB")
    if any(not isinstance(port, str) or not isinstance(pin, str) for port, pin in data["pins"].items()):
        raise ValueError("Invalid FPGA pin assignments")
    if any(not isinstance(port, str) or type(freq) not in (int, float) or
           not math.isfinite(freq) or freq <= 0 for port, freq in data["clocks_mhz"].items()):
        raise ValueError("Clock frequencies must be positive finite MHz values")
    if any(not isinstance(name, str) or not _IDENT.fullmatch(name) or
           not isinstance(members, list) or len(members) > 1024 or
           any(not isinstance(member, str) for member in members)
           for name, members in data["signal_groups"].items()):
        raise ValueError("Signal groups must map names to lists of signal names")
    if data["build"].get("synthesis") != "yosys" or data["build"].get("constraints") != "ice40-pcf":
        raise ValueError("Only Yosys generic synthesis with iCE40 PCF export is configured")
    if data.get("profile") is not None: validate_profile(data["profile"])
    return deepcopy(data)


def _modules_with_files(files):
    modules, locations = {}, {}
    for filename, source in files.items():
        try: found = parse(source)
        except HDLError as error:
            raise ValueError(f"{filename}:{error}") from error
        for name, module in found.items():
            if name in modules: raise ValueError(f"Duplicate module {name} in {locations[name]} and {filename}")
            modules[name] = module; locations[name] = filename
    return modules, locations


def top_ports(module):
    result = {}
    for name in module.header:
        direction, width = module.signals[name]
        for bit in range(width):
            result[name if width == 1 else f"{name}[{bit}]"] = (direction, name, bit)
    return result


def validate_workspace(data):
    try: item = validate_workspace_schema(data)
    except ValueError as error: return ValidationReport((str(error),), ())
    errors, warnings = [], []
    if not item["name"].strip(): errors.append("Project name is empty")
    if not _IDENT.fullmatch(item["top"]): errors.append("Choose a valid top module name")
    if not item["files"]: errors.append("Add at least one HDL source file")
    try: modules, locations = _modules_with_files(item["files"])
    except ValueError as error:
        errors.append(str(error)); modules = {}
    top = modules.get(item["top"])
    if item["top"] and top is None: errors.append(f"Top module {item['top']} is missing")
    if top is not None:
        try: import_verilog("\n".join(item["files"].values()), item["top"])
        except (HDLError, ValueError) as error: errors.append(f"HDL connectivity/width: {error}")
        ports = top_ports(top)
        for port in ports:
            if port not in item["pins"]: errors.append(f"Unassigned top-level pin {port}")
        for port in item["pins"]:
            if port not in ports: errors.append(f"Pin assignment references missing top-level port {port}")
        for clock in item["clocks_mhz"]:
            if clock not in ports or ports[clock][0] != "input":
                errors.append(f"Clock constraint {clock} is not a top-level input")
        clocked = any(procedure.kind == "clocked" for module in modules.values()
                      for procedure in module.procedures)
        if clocked and not item["clocks_mhz"]:
            errors.append("Sequential design needs at least one clock constraint")
        if not clocked and item["clocks_mhz"]:
            warnings.append("Clock constraints exist but no clocked HDL block was found")
        if any(ports[p][0] == "input" and p not in item["pins"] for p in ports):
            warnings.append("Some input ports are not assigned to package pins")
    profile = item.get("profile")
    if profile is None:
        errors.append("Select a user-supplied device profile; device characteristics are Unknown")
    else:
        available = set(profile["pins"])
        used = {}
        for port, pin in item["pins"].items():
            if pin not in available: errors.append(f"Pin {pin} for {port} is absent from the profile")
            if pin in used: errors.append(f"Pin {pin} is assigned to both {used[pin]} and {port}")
            used[pin] = port
        clock_pins = set(profile["clock_pins"])
        for clock in item["clocks_mhz"]:
            pin = item["pins"].get(clock)
            if pin and clock_pins and pin not in clock_pins:
                errors.append(f"Clock {clock} uses non-clock-capable pin {pin}")
        if not clock_pins and item["clocks_mhz"]:
            warnings.append("Clock-capable pins are Unknown in this user profile")
        if profile["constraint_format"] != "ice40-pcf":
            errors.append("Constraint export needs a supported format; only nextpnr iCE40 PCF is implemented")
        else:
            manufacturer = profile["manufacturer"].casefold()
            family = profile["family"].casefold()
            if manufacturer != "unknown" and "lattice" not in manufacturer:
                errors.append("iCE40 PCF constraints require a Lattice device profile")
            if family != "unknown" and "ice40" not in family:
                errors.append("iCE40 PCF constraints require an iCE40 family profile")
        if "unknown" in (profile["manufacturer"].lower(), profile["device"].lower()):
            warnings.append("Device identity is Unknown; package pins were not independently verified")
    return ValidationReport(tuple(errors), tuple(warnings))


def render_pcf(data):
    report = validate_workspace(data)
    if not report.valid: raise ValueError("FPGA project is invalid: " + "; ".join(report.errors))
    lines = ["# nextpnr iCE40 PCF generated by LogicSpace"]
    for port, pin in sorted(data["pins"].items()):
        if not _PIN.fullmatch(pin): raise ValueError(f"Unsafe package pin {pin}")
        lines.append(f"set_io {port} {pin}")
    for clock, frequency in sorted(data["clocks_mhz"].items()):
        lines.append(f"set_frequency {clock} {frequency:g}")
    return "\n".join(lines) + "\n"


def export_fpga_package(data, path, *, overwrite=False):
    report = validate_workspace(data)
    if not report.valid: raise ValueError("FPGA project is invalid: " + "; ".join(report.errors))
    target = Path(path)
    if target.exists() and not overwrite: raise ValueError("Destination exists; choose another filename")
    target.parent.mkdir(parents=True, exist_ok=True)
    members = {"hdl/" + name: source.encode("utf-8") for name, source in data["files"].items()}
    members["constraints/" + data["top"] + ".pcf"] = render_pcf(data).encode("utf-8")
    manifest = {"format": PACKAGE_FORMAT, "version": VERSION, "name": data["name"],
                "top": data["top"], "profile": data["profile"],
                "files": sorted(data["files"]), "pins": data["pins"],
                "clocks_mhz": data["clocks_mhz"], "signal_groups": data["signal_groups"],
                "build": data["build"], "warnings": list(report.warnings),
                "checksums": {name: hashlib.sha256(body).hexdigest() for name, body in members.items()}}
    members["manifest.json"] = json.dumps(manifest, indent=2).encode("utf-8")
    members["README.md"] = (f"# {data['name']}\n\nTop module: `{data['top']}`.\n\n"
                            "HDL and nextpnr iCE40 PCF constraints are included. "
                            "LogicSpace did not synthesize, place, route or validate physical timing. "
                            "Verify the user-supplied device profile against official package files.\n").encode("utf-8")
    handle, temporary = tempfile.mkstemp(prefix=".logicspace-fpga-", suffix=".zip", dir=target.parent)
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(members): archive.writestr(name, members[name])
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return manifest


def verify_fpga_package(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 72 or sum(item.file_size for item in entries) > 80 * 1024 * 1024:
            raise ValueError("FPGA package exceeds size or entry limits")
        names = {item.filename for item in entries}
        if len(names) != len(entries): raise ValueError("FPGA package has duplicate entries")
        if any(name.startswith("/") or ".." in Path(name).parts or "\\" in name for name in names):
            raise ValueError("FPGA package has an unsafe member name")
        if "manifest.json" not in names: raise ValueError("FPGA package has no manifest")
        if archive.getinfo("manifest.json").file_size > 1024 * 1024:
            raise ValueError("FPGA manifest is too large")
        manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict) or manifest.get("format") != PACKAGE_FORMAT or manifest.get("version") != VERSION:
            raise ValueError("Unsupported FPGA package")
        if not isinstance(manifest.get("checksums"), dict) or not manifest["checksums"]:
            raise ValueError("FPGA package has no content checksums")
        for name, digest in manifest.get("checksums", {}).items():
            if name not in names or hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"FPGA package content is missing or corrupted: {name}")
        if not isinstance(manifest.get("files"), list) or any(not isinstance(name, str) for name in manifest["files"]):
            raise ValueError("FPGA manifest has invalid HDL file list")
        try:
            files = {name: archive.read("hdl/" + name).decode("utf-8") for name in manifest["files"]}
            fields = {key: manifest[key] for key in ("name", "top", "profile", "pins",
                                                      "clocks_mhz", "signal_groups", "build")}
        except (KeyError, UnicodeDecodeError, TypeError) as error:
            raise ValueError(f"FPGA package is missing valid configuration data: {error}") from error
        workspace = blank_workspace()
        workspace.update(fields)
        workspace["files"] = files
        report = validate_workspace(workspace)
        if not report.valid:
            raise ValueError("FPGA package HDL/configuration is invalid: " + "; ".join(report.errors))
        return manifest

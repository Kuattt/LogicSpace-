"""Discover and validate wired ISA 2.1 CPUs without relying on board labels.

Only topology and actual component ports establish compatibility. This module
does not evaluate an instruction or synthesize a signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import json
import uuid

from engine import BusWire, bit_width, bus_ports, memory_geometry, register_file_geometry, wire_bit_pairs
from cpu_isa import INSTRUCTIONS


ROLES = {
    "clock": "Clock Generator", "enable": "CONST", "reset": "CONST",
    "pc": "Program Counter", "rom": "ROM", "ir": "Instruction Register",
    "control": "ISA Control Unit", "registers": "Register File",
    "alu": "ALU", "ram": "RAM",
    "rf_imm": "Multiplexer", "rf_mem": "Multiplexer", "rf_reg": "Multiplexer",
    "pc_data": "Multiplexer", "mem_data": "Multiplexer",
}

# Physical ISA 2.1 datapath contract. A single scalar wire has width 1;
# multibit links must be native BusWire with the exact LSB-first port mapping.
REQUIRED_LINKS = (
    *(("clock", "Q", role, "CLK", 1) for role in ("pc", "ir", "control", "registers", "ram")),
    ("enable", "Q", "pc", "ENABLE", 1), ("reset", "Q", "pc", "RESET", 1),
    ("control", "PC_INC", "pc", "INC", 1), ("control", "PC_LOAD", "pc", "LOAD", 1),
    ("pc_data", "Q", "pc", "D", 8),
    ("pc", "Q", "rom", "A", 8), ("pc", "Q", "control", "PC", 8),
    ("rom", "Q", "ir", "D", 8), ("rom", "Q", "control", "ROM_D", 8),
    ("control", "IR_LOAD", "ir", "LOAD", 1), ("ir", "Q", "control", "IR", 8),
    ("control", "RA0", "registers", "RA0", 2),
    ("control", "RA1", "registers", "RA1", 2),
    ("control", "WA", "registers", "WA", 2),
    ("control", "RF_WE", "registers", "WE", 1),
    ("rf_reg", "Q", "registers", "D", 8),
    ("registers", "R0", "alu", "A", 8),
    ("registers", "R1", "alu", "B", 8),
    ("control", "ALU_OP", "alu", "OP", 4),
    *(("alu", flag, "control", "ALU_" + flag, 1)
      for flag in ("ZERO", "CARRY", "NEGATIVE", "OVERFLOW")),
    ("alu", "Q", "rf_imm", "A", 8),
    ("control", "IMM", "rf_imm", "B", 8),
    ("control", "RF_IMM", "rf_imm", "SEL", 1),
    ("rf_imm", "Q", "rf_mem", "A", 8),
    ("ram", "Q", "rf_mem", "B", 8),
    ("control", "RF_MEM", "rf_mem", "SEL", 1),
    ("rf_mem", "Q", "rf_reg", "A", 8),
    ("registers", "R1", "rf_reg", "B", 8),
    ("control", "RF_REG", "rf_reg", "SEL", 1),
    ("control", "IMM", "pc_data", "A", 8),
    ("ram", "Q", "pc_data", "B", 8),
    ("control", "PC_MEM", "pc_data", "SEL", 1),
    ("registers", "R0", "mem_data", "A", 8),
    ("pc", "Q", "mem_data", "B", 8),
    ("control", "MEM_PC", "mem_data", "SEL", 1),
    ("control", "MEM_A", "ram", "A", 8),
    ("mem_data", "Q", "ram", "D", 8),
    ("control", "MEM_WE", "ram", "WE", 1),
    ("ram", "Q", "control", "MEM_Q", 8),
)


@dataclass
class CpuCandidate:
    ids: dict[str, str]
    issues: list[str]
    profile: dict | None
    extras: dict[str, list[str]]

    @property
    def compatible(self):
        return not self.issues


def _links(circuit):
    return {(w.source, w.source_pin, w.target, w.target_pin, w.width if isinstance(w, BusWire) else 1)
            for w in circuit.wires.values()}


def _neighbor(circuit, links, root, source_port, target_port, kind, *, incoming=False):
    matches = []
    for source, output, target, input_pin, _ in links:
        other = source if incoming else target
        if ((target if incoming else source) == root and
                (input_pin if incoming else output) == (target_port if incoming else source_port) and
                circuit.components.get(other) and circuit.components[other].kind == kind):
            matches.append(other)
    return sorted(set(matches))


def _candidate_ids(circuit, control_id, links):
    ids = {"control": control_id}
    for role, source_port, target_port, incoming in (
        ("clock", "Q", "CLK", True), ("pc", "Q", "PC", True),
        ("rom", "Q", "ROM_D", True), ("ir", "Q", "IR", True),
        ("ram", "Q", "MEM_Q", True), ("alu", "ZERO", "ALU_ZERO", True),
        ("registers", "RA0", "RA0", False),
        ("rf_imm", "RF_IMM", "SEL", False),
        ("rf_mem", "RF_MEM", "SEL", False),
        ("rf_reg", "RF_REG", "SEL", False),
        ("pc_data", "PC_MEM", "SEL", False),
        ("mem_data", "MEM_PC", "SEL", False),
    ):
        found = _neighbor(circuit, links, control_id, source_port, target_port,
                          ROLES[role], incoming=incoming)
        if found: ids[role] = found[0]
    pc = ids.get("pc")
    if pc:
        for role, target_port in (("enable", "ENABLE"), ("reset", "RESET")):
            found = _neighbor(circuit, links, pc, "Q", target_port, "CONST", incoming=True)
            if found: ids[role] = found[0]
    return ids


def validate_mapping(circuit, ids):
    """Collect every detectable problem; a missing manifest is never proof of failure."""
    issues = []
    if not isinstance(ids, dict): return ["Component mapping is missing"]
    for role, kind in ROLES.items():
        component = circuit.components.get(ids.get(role))
        if component is None:
            issues.append(f"Missing {role}: {kind}")
        elif component.kind != kind:
            issues.append(f"{role}: expected {kind}, found {component.kind}")
    if len([cid for cid in ids.values() if cid in circuit.components]) != len(set(cid for cid in ids.values() if cid in circuit.components)):
        issues.append("One component is mapped to multiple CPU roles")
    actual = _links(circuit)
    for source_role, source_port, target_role, target_port, width in REQUIRED_LINKS:
        source, target = ids.get(source_role), ids.get(target_role)
        if not source or not target or source not in circuit.components or target not in circuit.components:
            continue
        if (source, source_port, target, target_port, width) not in actual:
            same_endpoint = [entry for entry in actual if entry[:4] == (source, source_port, target, target_port)]
            if same_endpoint:
                issues.append(f"{source_role}.{source_port} → {target_role}.{target_port}: bus width mismatch (expected {width})")
            else:
                issues.append(f"Missing connection: {source_role}.{source_port} → {target_role}.{target_port} ({width} bit)")
    for role in ("pc", "ir", "alu", "rf_imm", "rf_mem", "rf_reg", "pc_data", "mem_data"):
        c = circuit.components.get(ids.get(role))
        if c:
            try:
                if bit_width(c) != 8: issues.append(f"{role}: ISA 2.1 requires 8-bit width")
                if role == "alu" and c.params.get("alu_version", 1) < 2:
                    issues.append("ALU: ISA 2.1 requires version 2 operations and flags")
            except (ValueError, TypeError) as error: issues.append(f"{role}: {error}")
    for role in ("ram", "rom"):
        c = circuit.components.get(ids.get(role))
        if c:
            try:
                address, data, depth = memory_geometry(c)
                if (address, data, depth) != (8, 8, 256):
                    issues.append(f"{role}: ISA 2.1 requires 8 address bits, 8 data bits, 256 words; found {address}/{data}/{depth}")
            except (ValueError, TypeError) as error: issues.append(f"{role}: {error}")
    c = circuit.components.get(ids.get("registers"))
    if c:
        try:
            count, data, reads, address = register_file_geometry(c)
            if (count, data, reads, address) != (4, 8, 2, 2):
                issues.append(f"registers: ISA 2.1 requires 4×8 registers, two read ports")
        except (ValueError, TypeError) as error: issues.append(f"registers: {error}")
    for role, expected in (("enable", 1), ("reset", 0)):
        c = circuit.components.get(ids.get(role))
        if c and c.params.get("value") != expected:
            issues.append(f"{role}: PC {role.upper()} needs constant {expected}")
    mapped = set(ids.values())
    relevant_wires = {wid for wid, wire in circuit.wires.items()
                      if wire.source in mapped or wire.target in mapped}
    try:
        structural_errors = circuit.validate()
    except (ValueError, TypeError, KeyError) as error:
        structural_errors = [f"Circuit pin validation: {error}"]
    for error in structural_errors:
        if any(wid in error for wid in relevant_wires): issues.append(error)
        elif error.startswith("Circuit pin validation:"): issues.append(error)
    return issues


def _profile(ids, name):
    return {"format": "logicspace-cpu-profile", "version": 1, "name": name,
            "isa_version": "2.1", "data_bits": 8, "address_bits": 8,
            "registers": 4, "rom_words": 256, "ram_words": 256,
            "operations": sorted({spec.mnemonic for spec in INSTRUCTIONS}),
            "roles": deepcopy(ROLES), "links": [list(link) for link in REQUIRED_LINKS]}


def discover_cpus(circuit):
    links = _links(circuit)
    found = []
    for control in circuit.components.values():
        if control.kind != "ISA Control Unit": continue
        ids = _candidate_ids(circuit, control.id, links)
        issues = validate_mapping(circuit, ids)
        mapped = set(ids.values())
        adjacent = {source for source, _, target, _, _ in links if target in mapped}
        adjacent |= {target for source, _, target, _, _ in links if source in mapped}
        extras = {kind: sorted(cid for cid in adjacent if circuit.components[cid].kind == kind)
                  for kind in ("Address Decoder", "Bus Input", "Bus Output")}
        name = control.params.get("label") or f"CPU {len(found) + 1}"
        found.append(CpuCandidate(ids, issues, _profile(ids, name) if not issues else None, extras))
    return found


def get_bindings(circuit):
    registry = circuit.cpu_architectures
    if registry is not None: return registry["items"]
    return [circuit.cpu_workspace] if circuit.cpu_workspace else []


def get_active_binding(circuit):
    registry = circuit.cpu_architectures
    if registry is None: return circuit.cpu_workspace
    return next((item for item in registry["items"] if item["id"] == registry.get("active")), None)


def _ensure_registry(circuit):
    if circuit.cpu_architectures is None:
        items = []
        if circuit.cpu_workspace:
            old = deepcopy(circuit.cpu_workspace)
            old.setdefault("id", uuid.uuid4().hex)
            old.setdefault("name", "Legacy CPU")
            items.append(old)
        circuit.cpu_architectures = {"version": 1, "active": items[0]["id"] if items else None,
                                     "items": items}
    return circuit.cpu_architectures


def _select_clock(circuit, registry):
    """Use actual Clock Generator run controls to isolate bound CPUs."""
    active = next((item for item in registry["items"] if item["id"] == registry.get("active")), None)
    active_clock = active["ids"].get("clock") if active else None
    for candidate in discover_cpus(circuit):
        clock = circuit.components.get(candidate.ids.get("clock"))
        if clock and clock.kind == "Clock Generator":
            clock.params["running"] = clock.id == active_clock
    for item in registry["items"]:
        clock = circuit.components.get(item["ids"].get("clock"))
        if clock and clock.kind == "Clock Generator":
            clock.params["running"] = item["id"] == registry.get("active")


def sync_active_from_clocks(circuit):
    """Align UI binding with restored Time Travel clock parameters."""
    registry = circuit.cpu_architectures
    if registry is None: return get_active_binding(circuit)
    running = [item for item in registry["items"]
               if circuit.components.get(item["ids"].get("clock")) and
               circuit.components[item["ids"]["clock"]].params.get("running", True)]
    registry["active"] = running[0]["id"] if len(running) == 1 else None
    return get_active_binding(circuit)


def bind_cpu(circuit, candidate, name=None, source="NOP\nHLT\n"):
    if candidate.issues: raise ValueError("ISA compatibility failed: " + "; ".join(candidate.issues))
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 80):
        raise ValueError("CPU architecture name must contain 1–80 characters")
    if not isinstance(source, str): raise ValueError("Assembly source must be text")
    registry = _ensure_registry(circuit)
    control_id = candidate.ids["control"]
    existing = next((item for item in registry["items"]
                     if item["ids"].get("control") == control_id), None)
    if existing:
        registry["active"] = existing["id"]
        _select_clock(circuit, registry)
        return existing
    clock_id = candidate.ids["clock"]
    if any(item["ids"].get("clock") == clock_id for item in registry["items"]):
        raise ValueError("Each bound CPU needs a separate Clock Generator for independent stepping")
    item = {"version": 1, "id": uuid.uuid4().hex, "name": name or candidate.profile["name"],
            "ids": deepcopy(candidate.ids), "source": source,
            "draft_source": source, "profile": candidate.profile}
    registry["items"].append(item)
    registry["active"] = item["id"]
    _select_clock(circuit, registry)
    return item


def select_cpu(circuit, binding_id):
    registry = _ensure_registry(circuit)
    item = next((item for item in registry["items"] if item["id"] == binding_id), None)
    if item is None: raise ValueError("CPU binding is unavailable")
    issues = validate_mapping(circuit, item["ids"])
    if issues: raise ValueError("CPU binding is stale: " + "; ".join(issues))
    registry["active"] = binding_id
    _select_clock(circuit, registry)
    return item


def unbind_cpu(circuit, binding_id=None):
    registry = _ensure_registry(circuit)
    binding_id = binding_id or registry.get("active")
    registry["items"] = [item for item in registry["items"] if item["id"] != binding_id]
    registry["active"] = registry["items"][0]["id"] if registry["items"] else None
    _select_clock(circuit, registry)


def rebind_cpu(circuit, binding_id, candidate):
    if candidate.issues: raise ValueError("CPU circuit is incompatible: " + "; ".join(candidate.issues))
    registry = _ensure_registry(circuit)
    item = next((entry for entry in registry["items"] if entry["id"] == binding_id), None)
    if item is None: raise ValueError("CPU binding is unavailable")
    if any(entry is not item and entry["ids"].get("control") == candidate.ids["control"]
           for entry in registry["items"]):
        raise ValueError("That ISA Control Unit is already bound to another CPU")
    item["ids"] = deepcopy(candidate.ids)
    item["profile"] = candidate.profile
    registry["active"] = binding_id
    _select_clock(circuit, registry)
    return item


def export_profile(binding):
    profile = binding.get("profile")
    if not isinstance(profile, dict):
        profile = _profile(binding["ids"], binding.get("name", "CPU"))
    return json.dumps(profile, indent=2, sort_keys=True)


def match_profile(candidate, profile):
    if not isinstance(profile, dict) or profile.get("format") != "logicspace-cpu-profile" or profile.get("version") != 1:
        raise ValueError("Unsupported CPU architecture profile")
    if candidate.issues: raise ValueError("CPU circuit is incompatible: " + "; ".join(candidate.issues))
    if not isinstance(profile.get("name"), str) or not 1 <= len(profile["name"].strip()) <= 80:
        raise ValueError("CPU profile name must contain 1–80 characters")
    expected = candidate.profile
    for key in ("isa_version", "data_bits", "address_bits", "registers", "rom_words", "ram_words", "operations", "roles", "links"):
        if profile.get(key) != expected[key]:
            raise ValueError(f"CPU profile {key} does not match this circuit")
    return True

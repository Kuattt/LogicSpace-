"""Reference wired 8-bit CPU board built from ordinary LogicSpace components."""
from __future__ import annotations

from engine import Circuit, Simulator
from cpu_isa import assemble
from cpu_architecture import get_active_binding, validate_mapping


ROLES = {
    "clock": "Clock Generator", "pc": "Program Counter", "rom": "ROM",
    "ir": "Instruction Register", "control": "ISA Control Unit",
    "registers": "Register File", "alu": "ALU", "ram": "RAM",
}


def validate_board(circuit, workspace=None):
    workspace = workspace if workspace is not None else get_active_binding(circuit)
    if not isinstance(workspace, dict) or workspace.get("version") != 1:
        raise ValueError("This project has no wired LogicSpace CPU board")
    ids = workspace.get("ids", {})
    for role, kind in ROLES.items():
        component = circuit.components.get(ids.get(role))
        if component is None or component.kind != kind:
            raise ValueError(f"CPU board {role} component is missing or has changed")
    issues = validate_mapping(circuit, ids)
    if issues:
        raise ValueError("CPU board has invalid physical connections: " + "; ".join(issues))
    links = workspace.get("links")
    actual = {(wire.source, wire.source_pin, wire.target, wire.target_pin,
               getattr(wire, "width", 1)) for wire in circuit.wires.values()}
    if links is not None:
        if not isinstance(links, list) or not links:
            raise ValueError("CPU board wiring manifest is invalid")
        for link in links:
            if not isinstance(link, list) or len(link) != 5 or tuple(link) not in actual:
                raise ValueError("CPU board is missing a required physical connection")
    return ids


def program_matches_rom(circuit, program, workspace=None):
    ids = validate_board(circuit, workspace)
    contents = circuit.components[ids["rom"]].params.get("contents", {})
    return all(contents.get(str(address), 0) == byte
               for address, byte in enumerate(program.image))


def create_cpu_circuit(source="NOP\nHLT\n"):
    program = assemble(source)
    circuit = Circuit()
    ids = {}
    links = []

    def part(role, kind, x, y, **params):
        component = circuit.add(kind, x, y, {"label": role.title(), **params})
        ids[role] = component.id
        return component

    def wire(source, pin, target, target_pin):
        circuit.connect(source.id, pin, target.id, target_pin)
        links.append([source.id, pin, target.id, target_pin, 1])

    def bus(source, port, target, target_port):
        connection = circuit.connect_bus(source.id, port, target.id, target_port)
        links.append([source.id, port, target.id, target_port, connection.width])

    clock = part("clock", "Clock Generator", -1200, -420, period=2)
    one = part("enable", "CONST", -1200, -210, value=1)
    zero = part("reset", "CONST", -1200, 0, value=0)
    pc = part("pc", "Program Counter", -880, -430, width=8)
    rom = part("rom", "ROM", -570, -430, address_bits=8, data_bits=8, depth=256,
               contents={str(address): program.image[address]
                         for address in sorted(program.used_addresses)})
    ir = part("ir", "Instruction Register", -260, -430, width=8)
    control = part("control", "ISA Control Unit", 60, -430)
    registers = part("registers", "Register File", -610, 310, registers=4, data_bits=8,
                     read_ports=2)
    alu = part("alu", "ALU", -260, 310, width=8)
    ram = part("ram", "RAM", 890, 310, address_bits=8, data_bits=8, depth=256)
    rf_imm = part("rf_imm", "Multiplexer", 70, 320, width=8)
    rf_mem = part("rf_mem", "Multiplexer", 360, 320, width=8)
    rf_reg = part("rf_reg", "Multiplexer", 620, 320, width=8)
    pc_data = part("pc_data", "Multiplexer", 390, -760, width=8)
    mem_data = part("mem_data", "Multiplexer", 590, 80, width=8)

    for component in (pc, ir, control, registers, ram):
        wire(clock, "Q", component, "CLK")
    wire(one, "Q", pc, "ENABLE")
    wire(zero, "Q", pc, "RESET")
    wire(control, "PC_INC", pc, "INC")
    wire(control, "PC_LOAD", pc, "LOAD")
    bus(pc_data, "Q", pc, "D")
    bus(pc, "Q", rom, "A")
    bus(pc, "Q", control, "PC")
    bus(rom, "Q", ir, "D")
    bus(rom, "Q", control, "ROM_D")
    wire(control, "IR_LOAD", ir, "LOAD")
    bus(ir, "Q", control, "IR")

    bus(control, "RA0", registers, "RA0")
    bus(control, "RA1", registers, "RA1")
    bus(control, "WA", registers, "WA")
    wire(control, "RF_WE", registers, "WE")
    bus(rf_reg, "Q", registers, "D")
    bus(registers, "R0", alu, "A")
    bus(registers, "R1", alu, "B")
    bus(control, "ALU_OP", alu, "OP")
    for flag_source, flag_target in (("ZERO", "ALU_ZERO"), ("CARRY", "ALU_CARRY"),
                                     ("NEGATIVE", "ALU_NEGATIVE"), ("OVERFLOW", "ALU_OVERFLOW")):
        wire(alu, flag_source, control, flag_target)

    bus(alu, "Q", rf_imm, "A")
    bus(control, "IMM", rf_imm, "B")
    wire(control, "RF_IMM", rf_imm, "SEL")
    bus(rf_imm, "Q", rf_mem, "A")
    bus(ram, "Q", rf_mem, "B")
    wire(control, "RF_MEM", rf_mem, "SEL")
    bus(rf_mem, "Q", rf_reg, "A")
    bus(registers, "R1", rf_reg, "B")
    wire(control, "RF_REG", rf_reg, "SEL")

    bus(control, "IMM", pc_data, "A")
    bus(ram, "Q", pc_data, "B")
    wire(control, "PC_MEM", pc_data, "SEL")
    bus(registers, "R0", mem_data, "A")
    bus(pc, "Q", mem_data, "B")
    wire(control, "MEM_PC", mem_data, "SEL")
    bus(control, "MEM_A", ram, "A")
    bus(mem_data, "Q", ram, "D")
    wire(control, "MEM_WE", ram, "WE")
    bus(ram, "Q", control, "MEM_Q")

    circuit.cpu_workspace = {"version": 1, "source": source, "ids": ids, "links": links}
    simulator = Simulator(circuit)
    if simulator.errors:
        raise ValueError("Reference CPU has invalid wiring: " + "; ".join(simulator.errors))
    return circuit


def load_program(circuit, source, workspace=None):
    workspace = workspace if workspace is not None else get_active_binding(circuit)
    ids = validate_board(circuit, workspace)
    program = assemble(source)
    circuit.components[ids["rom"]].params["contents"] = {
        str(address): program.image[address] for address in sorted(program.used_addresses)}
    workspace["source"] = source
    workspace["draft_source"] = source
    workspace["program_origin"] = "assembly"
    if circuit.cpu_workspace is not None and circuit.cpu_workspace is not workspace and circuit.cpu_workspace.get("ids") == ids:
        circuit.cpu_workspace.update(source=source, draft_source=source)
    return program


def load_rom_image(circuit, image, workspace=None, origin="bin"):
    """Program the selected physical ROM; never modify CPU execution state."""
    workspace = workspace if workspace is not None else get_active_binding(circuit)
    ids = validate_board(circuit, workspace)
    if not isinstance(image, (bytes, bytearray)) or not 1 <= len(image) <= 256:
        raise ValueError("ROM image must contain 1–256 bytes")
    rom = circuit.components[ids["rom"]]
    if len(image) > rom.params.get("depth", 256):
        raise ValueError("ROM image exceeds selected ROM capacity")
    rom.params["contents"] = {str(address): value for address, value in enumerate(image) if value}
    workspace["program_origin"] = origin
    return len(image)


def reset_bound_cpu(simulator, workspace=None):
    """Clear only this board's sequential state, preserving other CPUs."""
    circuit = simulator.circuit
    ids = validate_board(circuit, workspace)
    for role in ("pc", "ir", "control", "registers", "ram"):
        circuit.components[ids[role]].state.clear()
    simulator.evaluate()


def parse_intel_hex(text):
    """Strict Intel HEX subset for an 8-bit address ROM: data and EOF records."""
    if not isinstance(text, str): raise ValueError("Intel HEX must be text")
    cells = {}
    ended = False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line: continue
        if ended: raise ValueError(f"Line {number}: data after Intel HEX EOF")
        if not line.startswith(":"):
            raise ValueError(f"Line {number}: Intel HEX record must start with ':'")
        try: record = bytes.fromhex(line[1:])
        except ValueError: raise ValueError(f"Line {number}: invalid hexadecimal digits") from None
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) & 0xFF:
            raise ValueError(f"Line {number}: invalid Intel HEX length or checksum")
        count, address, kind = record[0], record[1] * 256 + record[2], record[3]
        if kind == 1:
            if count or address: raise ValueError(f"Line {number}: invalid EOF record")
            ended = True
        elif kind == 0:
            if address + count > 256: raise ValueError(f"Line {number}: ROM address exceeds 0xFF")
            for offset, value in enumerate(record[4:-1]):
                if address + offset in cells: raise ValueError(f"Line {number}: overlapping ROM address")
                cells[address + offset] = value
        else:
            raise ValueError(f"Line {number}: unsupported Intel HEX record type {kind}")
    if not ended: raise ValueError("Intel HEX EOF record is missing")
    if not cells: raise ValueError("Intel HEX contains no ROM bytes")
    return bytes(cells.get(address, 0) for address in range(max(cells) + 1))

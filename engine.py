"""LogicSpace circuit model and discrete time digital simulator (no GUI imports)."""
from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field
import json
import re
import uuid

from cpu_isa import BY_OPCODE, STACK_START, STACK_END


def new_id():
    return uuid.uuid4().hex[:12]


def invert(a):
    return None if a is None else 1 - a


def land(*v):
    return 0 if 0 in v else (None if None in v else 1)


def lor(*v):
    return 1 if 1 in v else (None if None in v else 0)


def lxor(*v):
    return None if None in v else sum(v) % 2


def to_int(v):
    return None if None in v else sum(b << i for i, b in enumerate(v))


def from_int(n, width, prefix="Q"):
    return {f"{prefix}{i}": None if n is None else (n >> i) & 1 for i in range(width)}


def trace_state(component):
    """Small state projection used by transient debugger transition facts."""
    summary = {key: component.state.get(key, component.params.get("initial", 0) if key in ("q", "value") else 0)
               for key in ("q", "value", "last_clk", "count")}
    if "last_write" in component.state:
        summary["last_write"] = deepcopy(component.state["last_write"])
    if isinstance(component.state.get("bit_values"), list):
        summary["bit_values"] = list(component.state["bit_values"])
    if "last_read" in component.state:
        summary["last_read"] = deepcopy(component.state["last_read"])
    if component.kind == "ISA Control Unit":
        for key in ("phase", "opcode", "arg1", "arg2", "sp", "zero", "carry",
                    "negative", "overflow", "instructions", "current_pc", "call_depth",
                    "halted", "fault", "last_completed"):
            if key in component.state:
                summary[key] = deepcopy(component.state[key])
    return summary


CATALOG = {
    "INPUT": ("I/O", [], ["Q"]), "OUTPUT": ("I/O", ["A"], []),
    "CONST": ("I/O", [], ["Q"]),
    "Bus Input": ("Bus", [], []),
    "Bus Output": ("Bus", [], []),
    "Bus Probe": ("Bus", [], []),
    "Bus Splitter": ("Bus", [], []),
    "Bus Merger": ("Bus", [], []),
    "Bit Selector": ("Bus", [], ["Q"]),
    "Lamp": ("Displays", ["A"], []),
    "LED": ("Displays", ["A"], []),
    "RGB": ("Displays", ["R", "G", "B"], []),
    "RGB Lamp": ("Displays", ["R", "G", "B"], []),
    "RGB LED": ("Displays", ["R", "G", "B"], []),
    "Seven-segment Display": ("Displays", ["A", "B", "C", "D", "E", "F", "G"], []),
    "AND": ("Logic Gates", ["A", "B"], ["Q"]),
    "OR": ("Logic Gates", ["A", "B"], ["Q"]),
    "NOT": ("Logic Gates", ["A"], ["Q"]),
    "HDL Truth": ("HDL", ["A"], ["Q"]),
    "HDL Case Match": ("HDL", ["A"], ["Q"]),
    "NAND": ("Logic Gates", ["A", "B"], ["Q"]),
    "NOR": ("Logic Gates", ["A", "B"], ["Q"]),
    "XOR": ("Logic Gates", ["A", "B"], ["Q"]),
    "XNOR": ("Logic Gates", ["A", "B"], ["Q"]),
    "SR Latch": ("Memory Elements", ["S", "R"], ["Q", "!Q"]),
    "D Latch": ("Memory Elements", ["D", "E"], ["Q", "!Q"]),
    "D Flip-Flop": ("Memory Elements", ["D", "CLK"], ["Q", "!Q"]),
    "JK Flip-Flop": ("Memory Elements", ["J", "K", "CLK"], ["Q", "!Q"]),
    "T Flip-Flop": ("Memory Elements", ["T", "CLK"], ["Q", "!Q"]),
    "Half Adder": ("Basic Circuits", ["A", "B"], ["SUM", "CARRY"]),
    "Full Adder": ("Basic Circuits", ["A", "B", "CIN"], ["SUM", "COUT"]),
    "Half Subtractor": ("Basic Circuits", ["A", "B"], ["DIFF", "BORROW"]),
    "Full Subtractor": ("Basic Circuits", ["A", "B", "BIN"], ["DIFF", "BOUT"]),
    "Comparator": ("Basic Circuits", ["A", "B"], ["LT", "EQ", "GT"]),
    "Multiplexer": ("Basic Circuits", ["A", "B", "SEL"], ["Q"]),
    "Demultiplexer": ("Basic Circuits", ["A", "SEL"], ["Q0", "Q1"]),
    "Decoder": ("Basic Circuits", ["A", "B"], ["Q0", "Q1", "Q2", "Q3"]),
    "Encoder": ("Basic Circuits", ["D0", "D1", "D2", "D3"], ["A", "B"]),
    "Register": ("Registers and Counters", [], []),
    "Shift Register": ("Registers and Counters", ["DIN", "CLK"], []),
    "Binary Counter": ("Registers and Counters", ["CLK", "RESET"], []),
    "Up Counter": ("Registers and Counters", ["CLK", "RESET"], []),
    "Down Counter": ("Registers and Counters", ["CLK", "RESET"], []),
    "Adder": ("Arithmetic", [], []), "Subtractor": ("Arithmetic", [], []),
    "Multiplier": ("Arithmetic", [], []), "Divider": ("Arithmetic", [], []),
    "ALU": ("Arithmetic", [], []),
    "Clock Generator": ("Timing", [], ["Q"]),
    "Oscillator": ("Timing", [], ["Q"]),
    "Clock Divider": ("Timing", ["CLK"], ["Q"]),
    "Timer": ("Timing", ["START", "RESET"], ["Q"]),
    "Pulse Generator": ("Timing", ["TRIG"], ["Q"]),
    "RAM": ("Memory", [], []), "ROM": ("Memory", [], []),
    "Register File": ("Memory", [], []),
    "Address Decoder": ("Memory", [], []),
    "SRAM": ("Memory", [], []), "DRAM": ("Memory", [], []),
    "EEPROM": ("Memory", [], []), "Flash Memory": ("Memory", [], []),
    "Program Counter": ("CPU", [], []),
    "Instruction Register": ("CPU", [], []),
    "Control Unit": ("CPU", [], []),
    "ISA Control Unit": ("CPU", [], []),
}
ANALOG = ("Resistor", "Capacitor", "Diode", "Transistor", "MOSFET", "BJT", "Crystal Oscillator")
DISPLAYS = ("Lamp", "LED", "RGB", "RGB Lamp", "RGB LED", "Seven-segment Display")
LOGIC_GATES = ("AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR")
BIT_WIDTH_KINDS = (
    "INPUT", "OUTPUT", "CONST", *LOGIC_GATES, "HDL Truth", "HDL Case Match",
    "Comparator", "Multiplexer", "Demultiplexer",
    "Bus Input", "Bus Output", "Bus Probe", "Bus Splitter", "Bus Merger", "Bit Selector",
    "Register", "Shift Register", "Binary Counter", "Up Counter", "Down Counter",
    "Adder", "Subtractor", "Multiplier", "Divider", "ALU",
    "Program Counter", "Instruction Register",
)
DEFAULT_FOUR_BIT = (
    "Bus Input", "Bus Output", "Bus Probe", "Bus Splitter", "Bus Merger", "Bit Selector",
    "Register", "Shift Register", "Binary Counter", "Up Counter", "Down Counter",
    "Adder", "Subtractor", "Multiplier", "Divider", "ALU",
    "Program Counter", "Instruction Register",
)
for _kind in ANALOG:
    CATALOG[_kind] = ("Electronic Components · visual only", ["A"], ["B"])

SEQUENTIAL = {
    "SR Latch", "D Latch", "D Flip-Flop", "JK Flip-Flop", "T Flip-Flop",
    "Register", "Shift Register", "Binary Counter", "Up Counter", "Down Counter",
    "Clock Divider", "Timer", "Pulse Generator",
    "RAM", "SRAM", "DRAM", "EEPROM", "Flash Memory",
    "Register File", "Program Counter", "Instruction Register", "ISA Control Unit",
}


@dataclass
class Component:
    id: str
    kind: str
    x: float = 0
    y: float = 0
    params: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)


@dataclass
class Wire:
    id: str
    source: str
    source_pin: str
    target: str
    target_pin: str
    bends: list = field(default_factory=list)


BUS_WIDTHS = (2, 4, 8, 16, 32)
BUS_COMPONENTS = ("Bus Input", "Bus Output", "Bus Probe", "Bus Splitter", "Bus Merger", "Bit Selector")


@dataclass
class BusWire(Wire):
    width: int = 4
    source_bits: list = field(default_factory=list)
    target_bits: list = field(default_factory=list)


def wire_to_dict(wire):
    data = deepcopy(vars(wire))
    if isinstance(wire, BusWire):
        data["kind"] = "bus"
    return data


def wire_from_dict(data):
    data = deepcopy(data)
    kind = data.pop("kind", "wire")
    if kind == "bus":
        return BusWire(**data)
    if kind == "wire":
        return Wire(**data)
    raise ValueError(f"Unknown connection type: {kind}")


def wire_bit_pairs(wire):
    if isinstance(wire, BusWire):
        return tuple(zip(wire.source_bits, wire.target_bits))
    return ((wire.source_pin, wire.target_pin),)


def bus_component_width(component):
    width = component.params.get("width", 4)
    if type(width) is not int or width not in BUS_WIDTHS:
        raise ValueError(f"{component.kind}: bus width must be 2, 4, 8, 16 or 32 bits")
    return width


def bus_input_bits(component):
    width = bus_component_width(component)
    explicit = component.params.get("_bit_values")
    if explicit is not None:
        if (not isinstance(explicit, list) or len(explicit) != width or
                any(bit is not None and (type(bit) is not int or bit not in (0, 1)) for bit in explicit)):
            raise ValueError(f"{component.kind}: binary value needs exactly {width} bits of 0, 1 or X")
        return list(explicit)
    value = component.params.get("value", 0)
    if value is None:
        return [None] * width
    if type(value) is not int or not 0 <= value < (1 << width):
        raise ValueError(f"{component.kind}: value must fit in {width} bits")
    return [(value >> i) & 1 for i in range(width)]


def bit_width(component):
    default = 4 if component.kind in DEFAULT_FOUR_BIT else 1
    maximum = 8 if component.kind in ("INPUT", "OUTPUT", "CONST") else 32
    width = component.params.get("width", default)
    if type(width) is not int or not 1 <= width <= maximum:
        raise ValueError(f"{component.kind}: bit width must be 1–{maximum}")
    return width


def memory_geometry(component):
    address = component.params.get("address_bits", 4)
    data = component.params.get("data_bits", 4)
    if type(address) is not int or not 1 <= address <= 8:
        raise ValueError(f"{component.kind}: address bits must be 1–8")
    if type(data) is not int or not 1 <= data <= 32:
        raise ValueError(f"{component.kind}: data bits must be 1–32")
    depth = component.params.get("depth", 1 << address)
    if type(depth) is not int or not 1 <= depth <= 1 << address:
        raise ValueError(f"{component.kind}: address count must be 1–{1 << address}")
    if component.kind in ("RAM", "ROM"):
        read_mode = component.params.get("read_mode", "async" if component.kind == "ROM" else "legacy")
        if read_mode not in (("async", "sync") if component.kind == "ROM" else ("legacy", "async", "sync")):
            raise ValueError(f"{component.kind}: invalid read mode")
        if type(component.params.get("read_enable", False)) is not bool:
            raise ValueError(f"{component.kind}: read_enable must be true or false")
        if component.params.get("edge", "rising") not in ("rising", "falling"):
            raise ValueError(f"{component.kind}: invalid clock edge")
        if component.kind == "RAM":
            if component.params.get("write_mode", "sync") != "sync":
                raise ValueError("RAM: only synchronous writes are supported")
            if component.params.get("read_during_write", "new") not in ("new", "old", "no_change"):
                raise ValueError("RAM: invalid read-during-write mode")
            if read_mode == "async" and component.params.get("read_during_write", "new") != "new":
                raise ValueError("RAM: asynchronous reads always show the committed new value")
            initial = component.params.get("init", {})
            if (not isinstance(initial, dict) or any(not isinstance(key, str) or not key.isdigit()
                    or str(int(key)) != key or int(key) >= depth or type(value) is not int
                    or not 0 <= value < (1 << data) for key, value in initial.items())):
                raise ValueError("RAM: init must map valid addresses to values within the data width")
    if component.kind == "ROM":
        contents = component.params.get("contents", {})
        if (not isinstance(contents, dict) or any(not isinstance(key, str) or not key.isdigit()
                or str(int(key)) != key or int(key) >= depth or type(value) is not int or not 0 <= value < (1 << data)
                for key, value in contents.items())):
            raise ValueError("ROM: contents must map valid addresses to values within the data width")
    return address, data, depth


def memory_read_mode(component):
    return component.params.get("read_mode", "async" if component.kind == "ROM" else "legacy")


def register_file_geometry(component):
    count = component.params.get("registers", 8)
    data = component.params.get("data_bits", 8)
    reads = component.params.get("read_ports", 2)
    if type(count) is not int or not 2 <= count <= 32:
        raise ValueError("Register File: register count must be 2–32")
    if type(data) is not int or not 1 <= data <= 32:
        raise ValueError("Register File: data bits must be 1–32")
    if type(reads) is not int or not 1 <= reads <= 2:
        raise ValueError("Register File: read ports must be 1 or 2")
    return count, data, reads, (count - 1).bit_length()


CONTROL_SIGNALS = ("REG_WE", "MEM_WE", "PC_LOAD", "PC_INC", "IR_LOAD")
DEFAULT_MICROCODE = {
    "0": {"alu": 0, "REG_WE": 1, "PC_INC": 1},   # ADD
    "1": {"alu": 1, "REG_WE": 1, "PC_INC": 1},   # SUB
    "2": {"alu": 2, "REG_WE": 1, "PC_INC": 1},   # AND
    "3": {"alu": 3, "REG_WE": 1, "PC_INC": 1},   # OR
    "4": {"alu": 4, "REG_WE": 1, "PC_INC": 1},   # XOR
    "5": {"alu": 0, "MEM_WE": 1, "PC_INC": 1},   # STORE
    "6": {"alu": 0, "PC_LOAD": 1},               # JUMP
    "7": {"alu": 0, "PC_INC": 1, "branch_zero": 1}, # BEQ
    "8": {"alu": 0, "IR_LOAD": 1, "PC_INC": 1},   # FETCH
}


def control_geometry(component):
    width = component.params.get("opcode_bits", 4)
    if type(width) is not int or width not in (4, 8):
        raise ValueError("Control Unit: opcode bits must be 4 or 8")
    table = component.params.get("microcode", DEFAULT_MICROCODE)
    if not isinstance(table, dict):
        raise ValueError("Control Unit: microcode must be a JSON object")
    for key, entry in table.items():
        if (not isinstance(key, str) or not key.isdigit() or str(int(key)) != key or int(key) >= (1 << width)
                or not isinstance(entry, dict) or type(entry.get("alu", 0)) is not int
                or not 0 <= entry.get("alu", 0) <= 15
                or any(name not in (*CONTROL_SIGNALS, "alu", "branch_zero") or
                       (name != "alu" and (type(value) is not int or value not in (0, 1)))
                       for name, value in entry.items())):
            raise ValueError("Control Unit: invalid microcode opcode or control field")
    return width, table


ISA_CONTROL_INPUTS = ([f"ROM_D{i}" for i in range(8)] + [f"IR{i}" for i in range(8)] +
                      [f"PC{i}" for i in range(8)] + [f"MEM_Q{i}" for i in range(8)] +
                      ["ALU_ZERO", "ALU_CARRY", "ALU_NEGATIVE", "ALU_OVERFLOW", "CLK"])
ISA_CONTROL_OUTPUTS = ([f"RA0_{i}" for i in range(2)] + [f"RA1_{i}" for i in range(2)] +
                       [f"WA{i}" for i in range(2)] + [f"MEM_A{i}" for i in range(8)] +
                       [f"IMM{i}" for i in range(8)] + [f"ALU_OP{i}" for i in range(4)] +
                       [f"SP{i}" for i in range(8)] +
                       ["RF_WE", "MEM_WE", "PC_INC", "PC_LOAD", "IR_LOAD",
                        "RF_IMM", "RF_MEM", "RF_REG", "PC_MEM", "MEM_PC",
                        "HALTED", "FAULT", "ZERO", "CARRY", "NEGATIVE", "OVERFLOW"])


def isa_control_outputs(state):
    """Control lines for one microphase; data still flows through wired blocks."""
    phase = state.get("phase", "FETCH")
    opcode = state.get("opcode")
    first, second = state.get("arg1"), state.get("arg2")
    sp = state.get("sp", STACK_END)
    signals = {pin: 0 for pin in ISA_CONTROL_OUTPUTS}
    for name, key in (("ZERO", "zero"), ("CARRY", "carry"),
                      ("NEGATIVE", "negative"), ("OVERFLOW", "overflow")):
        signals[name] = state.get(key, 0)
    signals.update(from_int(sp, 8, "SP"))
    signals["HALTED"] = int(phase == "HALT")
    signals["FAULT"] = int(bool(state.get("fault")))
    if phase == "FETCH":
        signals["IR_LOAD"] = signals["PC_INC"] = 1
    elif phase in ("ARG1", "ARG2"):
        signals["PC_INC"] = 1
    if phase not in ("READ", "EXEC") or opcode is None:
        return signals
    if opcode in (0x12, 0x13):  # LOAD / STORE direct RAM address
        memory_address = second
    elif opcode in (0x40, 0x35):  # PUSH / CALL write at current SP
        memory_address = sp
    elif opcode in (0x41, 0x36):  # POP / RET read from SP + 1, then SP is updated
        memory_address = (sp + 1 if sp < STACK_END else None) if phase == "READ" else sp
    else:
        memory_address = 0
    signals.update(from_int(memory_address, 8, "MEM_A"))
    if phase == "READ":
        return signals
    if first is not None:
        signals.update(from_int(first & 3, 2, "RA0_"))
        signals.update(from_int(first & 3, 2, "WA"))
    if second is not None:
        signals.update(from_int(second & 3, 2, "RA1_"))
    immediate = second if opcode == 0x10 else first if opcode in range(0x30, 0x36) else 0
    signals.update(from_int(immediate, 8, "IMM"))
    alu_code = {0x20: 0, 0x21: 1, 0x22: 2, 0x23: 3, 0x24: 4,
                0x25: 5, 0x26: 6, 0x27: 7, 0x28: 1}.get(opcode, 0)
    signals.update(from_int(alu_code, 4, "ALU_OP"))
    if opcode in (0x10, 0x11, 0x12, 0x20, 0x21, 0x22, 0x23, 0x24,
                  0x25, 0x26, 0x27, 0x41):
        signals["RF_WE"] = 1
    signals["RF_IMM"] = int(opcode == 0x10)
    signals["RF_MEM"] = int(opcode in (0x12, 0x41))
    signals["RF_REG"] = int(opcode == 0x11)
    if opcode in (0x13, 0x40, 0x35) and STACK_START <= sp <= STACK_END:
        signals["MEM_WE"] = 1
    if opcode == 0x13:
        signals["MEM_WE"] = 1
    signals["MEM_PC"] = int(opcode == 0x35)
    taken = (opcode in (0x30, 0x35, 0x36) or
             opcode == 0x31 and state.get("zero", 0) == 1 or
             opcode == 0x32 and state.get("zero", 0) == 0 or
             opcode == 0x33 and state.get("carry", 0) == 1 or
             opcode == 0x34 and state.get("carry", 0) == 0)
    signals["PC_LOAD"] = int(taken)
    signals["PC_MEM"] = int(opcode == 0x36)
    return signals


def pins(c, blocks=None):
    if c.kind.startswith("BLOCK:"):
        definition = (blocks or {}).get(c.kind[6:])
        if definition is None:
            raise ValueError(f"Missing custom block: {c.kind[6:]}")
        return list(definition["inputs"]), list(definition["outputs"])
    if c.kind not in CATALOG:
        raise ValueError(f"Unknown component: {c.kind}")
    if c.kind in BUS_COMPONENTS:
        width = bus_component_width(c)
        names = [f"D{i}" for i in range(width)]
        if c.kind == "Bus Input":
            bus_input_bits(c)
            return [], [f"Q{i}" for i in range(width)]
        if c.kind in ("Bus Output", "Bus Probe"):
            return names, []
        if c.kind == "Bus Splitter":
            exposed = c.params.get("expose", list(range(width)))
            if (not isinstance(exposed, list) or not exposed or
                    any(type(index) is not int or not 0 <= index < width for index in exposed) or
                    len(set(exposed)) != len(exposed)):
                raise ValueError("Bus Splitter: exposed bits must be unique indices within the width")
            return names, [f"Q{i}" for i in sorted(exposed)]
        if c.kind == "Bus Merger":
            return names, [f"Q{i}" for i in range(width)]
        index = c.params.get("index", 0)
        if type(index) is not int or not 0 <= index < width:
            raise ValueError("Bit Selector: selected bit is outside the bus width")
        return names, ["Q"]
    if c.kind in ("HDL Truth", "HDL Case Match"):
        width = bit_width(c)
        if c.kind == "HDL Case Match" and (type(c.params.get("match")) is not int or
                                              not 0 <= c.params["match"] < (1 << width)):
            raise ValueError("HDL Case Match: match value must fit the input width")
        return (["A"] if width == 1 else [f"A{i}" for i in range(width)]), ["Q"]
    if c.kind == "Register File":
        count, data, reads, address = register_file_geometry(c)
        ins = [f"RA{port}_{i}" for port in range(reads) for i in range(address)]
        ins += [f"WA{i}" for i in range(address)] + [f"D{i}" for i in range(data)] + ["WE", "CLK"]
        outs = [f"R{port}_{i}" for port in range(reads) for i in range(data)]
        return ins, outs
    if c.kind == "Address Decoder":
        address = c.params.get("address_bits", 3)
        outputs = c.params.get("outputs", 1 << address if type(address) is int and 1 <= address <= 5 else 8)
        if type(address) is not int or not 1 <= address <= 5 or type(outputs) is not int or not 2 <= outputs <= (1 << address):
            raise ValueError("Address Decoder: use 1–5 address bits and 2–2^bits outputs")
        return [f"A{i}" for i in range(address)], [f"S{i}" for i in range(outputs)]
    if c.kind == "Control Unit":
        width, _ = control_geometry(c)
        return [f"OP{i}" for i in range(width)] + ["ZERO"], [f"ALU_OP{i}" for i in range(4)] + list(CONTROL_SIGNALS)
    if c.kind == "ISA Control Unit":
        return list(ISA_CONTROL_INPUTS), list(ISA_CONTROL_OUTPUTS)
    ins, outs = CATALOG[c.kind][1:]
    width = bit_width(c)
    if c.kind in ("INPUT", "CONST") and width > 1:
        return [], [f"Q{i}" for i in range(width)]
    if c.kind == "OUTPUT" and width > 1:
        return [f"A{i}" for i in range(width)], []
    if c.kind in LOGIC_GATES and width > 1:
        inputs = [f"A{i}" for i in range(width)]
        if c.kind != "NOT": inputs += [f"B{i}" for i in range(width)]
        return inputs, [f"Q{i}" for i in range(width)]
    if c.kind == "Comparator" and width > 1:
        return [f"A{i}" for i in range(width)] + [f"B{i}" for i in range(width)], ["LT", "EQ", "GT"]
    if c.kind == "Multiplexer" and width > 1:
        return [f"A{i}" for i in range(width)] + [f"B{i}" for i in range(width)] + ["SEL"], [f"Q{i}" for i in range(width)]
    if c.kind == "Demultiplexer" and width > 1:
        return [f"A{i}" for i in range(width)] + ["SEL"], [f"Q0_{i}" for i in range(width)] + [f"Q1_{i}" for i in range(width)]
    if c.kind == "Register":
        inputs = [f"D{i}" for i in range(width)] + ["CLK"]
        if c.params.get("async_reset", False):
            if c.params.get("reset_active", 1) not in (0, 1) or type(c.params.get("reset_active", 1)) is not int:
                raise ValueError("Register: asynchronous reset active level must be 0 or 1")
            value = c.params.get("reset_value", 0)
            if type(value) is not int or not 0 <= value < (1 << width):
                raise ValueError("Register: asynchronous reset value must fit the width")
            inputs.append("ARST")
        return inputs, [f"Q{i}" for i in range(width)]
    if c.kind in ("Shift Register", "Binary Counter", "Up Counter", "Down Counter"):
        return list(ins), [f"Q{i}" for i in range(width)]
    if c.kind == "Program Counter":
        return [f"D{i}" for i in range(width)] + ["CLK", "RESET", "LOAD", "INC", "ENABLE"], [f"Q{i}" for i in range(width)]
    if c.kind == "Instruction Register":
        return [f"D{i}" for i in range(width)] + ["CLK", "LOAD"], [f"Q{i}" for i in range(width)]
    if c.kind in ("Adder", "Subtractor", "Multiplier", "Divider", "ALU"):
        extra = ["CIN"] if c.kind == "Adder" else ([f"OP{i}" for i in range(4 if c.params.get("alu_version", 1) >= 2 else 2)] if c.kind == "ALU" else [])
        flags = ["ZERO", "CARRY", "NEGATIVE", "OVERFLOW"] if c.kind == "ALU" and c.params.get("alu_version", 1) >= 2 else []
        return [f"A{i}" for i in range(width)] + [f"B{i}" for i in range(width)] + extra, [f"Q{i}" for i in range(width)] + (["COUT"] if c.kind == "Adder" else []) + flags
    if c.kind in ("RAM", "ROM", "SRAM", "DRAM", "EEPROM", "Flash Memory"):
        ab, db, _ = memory_geometry(c)
        extra = (["REFRESH"] if c.kind == "DRAM" else (["ERASE"] if c.kind == "Flash Memory" else []))
        control = ["RE"] if c.kind in ("RAM", "ROM") and c.params.get("read_enable", False) else []
        if c.kind == "ROM":
            control += ["CLK"] if c.params.get("read_mode", "async") == "sync" else []
            return [f"A{i}" for i in range(ab)] + control, [f"Q{i}" for i in range(db)]
        return [f"A{i}" for i in range(ab)] + [f"D{i}" for i in range(db)] + ["WE", "CLK"] + control + extra, [f"Q{i}" for i in range(db)]
    if c.kind == "D Flip-Flop" and c.params.get("async_reset", False):
        if c.params.get("reset_active", 1) not in (0, 1) or type(c.params.get("reset_active", 1)) is not int:
            raise ValueError("D Flip-Flop: asynchronous reset active level must be 0 or 1")
        if c.params.get("reset_value", 0) not in (0, 1) or type(c.params.get("reset_value", 0)) is not int:
            raise ValueError("D Flip-Flop: asynchronous reset value must be 0 or 1")
        return list(ins) + ["ARST"], list(outs)
    return list(ins), list(outs)


def bus_ports(component, blocks=None):
    """Map one visible bus port to existing scalar pins, LSB first."""
    result = {"input": {}, "output": {}}
    if component.kind.startswith("BLOCK:"):
        definition = (blocks or {})[component.kind[6:]]
        explicit = definition.get("_hdl_bus_ports", {})
        for direction in ("input", "output"):
            for name, external_pins in explicit.get(direction, {}).items():
                result[direction][name] = tuple(external_pins)
        for direction in ("input", "output"):
            groups = {}
            for external, target in definition[direction + "_map"].items():
                match = re.fullmatch(r"(.+?)(\d+)", external)
                if not match or not isinstance(target, list) or len(target) != 2:
                    continue
                cid, internal_pin = target
                index = int(match.group(2))
                expected = ("Q" if direction == "input" else "A") + str(index)
                if internal_pin == expected:
                    groups.setdefault((cid, match.group(1)), {})[index] = external
            for (_, name), indexed in groups.items():
                if len(indexed) in BUS_WIDTHS and set(indexed) == set(range(len(indexed))):
                    result[direction][name] = tuple(indexed[index] for index in range(len(indexed)))
        return result
    kind = component.kind
    if kind not in BIT_WIDTH_KINDS and kind not in ("RAM", "ROM", "SRAM", "DRAM", "EEPROM", "Flash Memory",
                                                    "Register File", "Address Decoder", "Control Unit", "ISA Control Unit"):
        return result
    inputs, outputs = pins(component, blocks)
    width = (bus_component_width(component) if kind in BUS_COMPONENTS else
             bit_width(component) if kind in BIT_WIDTH_KINDS else 1)
    groups = []
    if kind in ("INPUT", "CONST", "Bus Input"):
        groups = [("output", "Q", [f"Q{i}" for i in range(width)])]
    elif kind in ("OUTPUT",):
        groups = [("input", "A", [f"A{i}" for i in range(width)])]
    elif kind in ("Bus Output", "Bus Probe", "Bus Splitter", "Bit Selector"):
        groups = [("input", "D", [f"D{i}" for i in range(width)])]
    elif kind == "Bus Merger":
        groups = [("output", "Q", [f"Q{i}" for i in range(width)])]
    elif kind in LOGIC_GATES:
        groups = [("input", "A", [f"A{i}" for i in range(width)]),
                  ("output", "Q", [f"Q{i}" for i in range(width)])]
        if kind != "NOT": groups.append(("input", "B", [f"B{i}" for i in range(width)]))
    elif kind in ("HDL Truth", "HDL Case Match"):
        groups = [("input", "A", [f"A{i}" for i in range(width)])]
    elif kind in ("Comparator", "Multiplexer", "Demultiplexer", "Register",
                  "Program Counter", "Instruction Register",
                  "Adder", "Subtractor", "Multiplier", "Divider", "ALU"):
        groups = [("input", "A", [f"A{i}" for i in range(width)]),
                  ("input", "B", [f"B{i}" for i in range(width)]),
                  ("output", "Q", [f"Q{i}" for i in range(width)])]
        if kind == "Register": groups = [("input", "D", [f"D{i}" for i in range(width)]),
                                         ("output", "Q", [f"Q{i}" for i in range(width)])]
        elif kind in ("Program Counter", "Instruction Register"):
            groups = [("input", "D", [f"D{i}" for i in range(width)]),
                      ("output", "Q", [f"Q{i}" for i in range(width)])]
        elif kind == "Comparator": groups = groups[:2]
        elif kind == "Demultiplexer":
            groups = [("input", "A", [f"A{i}" for i in range(width)]),
                      ("output", "Q0", [f"Q0_{i}" for i in range(width)]),
                      ("output", "Q1", [f"Q1_{i}" for i in range(width)])]
        elif kind == "ALU" and component.params.get("alu_version", 1) >= 2:
            groups.append(("input", "OP", [f"OP{i}" for i in range(4)]))
    elif kind in ("Shift Register", "Binary Counter", "Up Counter", "Down Counter"):
        groups = [("output", "Q", [f"Q{i}" for i in range(width)])]
    elif kind in ("RAM", "ROM", "SRAM", "DRAM", "EEPROM", "Flash Memory"):
        address, data, _ = memory_geometry(component)
        groups = [("input", "A", [f"A{i}" for i in range(address)]),
                  ("output", "Q", [f"Q{i}" for i in range(data)])]
        if kind != "ROM": groups.append(("input", "D", [f"D{i}" for i in range(data)]))
    elif kind == "Register File":
        _, data, reads, address = register_file_geometry(component)
        groups = [("input", "WA", [f"WA{i}" for i in range(address)]),
                  ("input", "D", [f"D{i}" for i in range(data)])]
        for port in range(reads):
            groups.extend((("input", f"RA{port}", [f"RA{port}_{i}" for i in range(address)]),
                           ("output", f"R{port}", [f"R{port}_{i}" for i in range(data)])))
    elif kind == "Address Decoder":
        address = component.params.get("address_bits", 3)
        groups = [("input", "A", [f"A{i}" for i in range(address)])]
    elif kind == "Control Unit":
        address, _ = control_geometry(component)
        groups = [("input", "OP", [f"OP{i}" for i in range(address)]),
                  ("output", "ALU_OP", [f"ALU_OP{i}" for i in range(4)])]
    elif kind == "ISA Control Unit":
        groups = [("input", "ROM_D", [f"ROM_D{i}" for i in range(8)]),
                  ("input", "IR", [f"IR{i}" for i in range(8)]),
                  ("input", "PC", [f"PC{i}" for i in range(8)]),
                  ("input", "MEM_Q", [f"MEM_Q{i}" for i in range(8)]),
                  ("output", "MEM_A", [f"MEM_A{i}" for i in range(8)]),
                  ("output", "IMM", [f"IMM{i}" for i in range(8)]),
                  ("output", "SP", [f"SP{i}" for i in range(8)]),
                  ("output", "ALU_OP", [f"ALU_OP{i}" for i in range(4)]),
                  ("output", "RA0", [f"RA0_{i}" for i in range(2)]),
                  ("output", "RA1", [f"RA1_{i}" for i in range(2)]),
                  ("output", "WA", [f"WA{i}" for i in range(2)])]
    for direction, port, names in groups:
        available = inputs if direction == "input" else outputs
        if len(names) in BUS_WIDTHS and all(name in available for name in names):
            result[direction][port] = tuple(names)
    return result


class Circuit:
    def __init__(self):
        self.components = {}
        self.wires = {}
        self.blocks = {}
        self.tick = 0
        self.testbenches = None  # Optional versioned project data; legacy JSON stays unchanged.
        self.testbench_issues = []
        self._invalid_testbenches = None
        self.cpu_workspace = None  # Optional Assembly source and IDs for a wired ISA board.
        self.cpu_architectures = None  # Optional selected CPU bindings; legacy workspace stays readable.
        self.project_info = None  # Optional template/package provenance; no effect on simulation.
        self.fpga_workspace = None  # Optional versioned HDL/project metadata; no simulation effect.
        self.hdl_sources = None  # Optional source snapshots for HDL ↔ circuit navigation.

    def add(self, kind, x=0, y=0, params=None):
        component_id = new_id()
        while component_id in self.components:
            component_id = new_id()
        settings = dict(params or {})
        if kind == "ALU": settings.setdefault("alu_version", 2)
        c = Component(component_id, kind, x, y, settings)
        pins(c, self.blocks)
        self.components[c.id] = c
        return c

    def connect(self, source, source_pin, target, target_pin, bends=None):
        if source not in self.components or target not in self.components:
            raise ValueError("Both components must exist")
        if source_pin not in pins(self.components[source], self.blocks)[1]:
            raise ValueError("Source must be an output pin")
        if target_pin not in pins(self.components[target], self.blocks)[0]:
            raise ValueError("Target must be an input pin")
        if source == target:
            raise ValueError("A component cannot wire to itself")
        if any(w.target == target and any(bit == target_pin for _, bit in wire_bit_pairs(w))
               for w in self.wires.values()):
            raise ValueError("Input pin already has a driver")
        w = Wire(new_id(), source, source_pin, target, target_pin, list(bends or []))
        self.wires[w.id] = w
        return w

    def connect_bus(self, source, source_port, target, target_port, bends=None):
        if source not in self.components or target not in self.components:
            raise ValueError("Both components must exist")
        if source == target:
            raise ValueError("A component cannot wire to itself")
        source_bits = bus_ports(self.components[source], self.blocks)["output"].get(source_port)
        target_bits = bus_ports(self.components[target], self.blocks)["input"].get(target_port)
        if source_bits is None or target_bits is None:
            raise ValueError("Choose valid multibit output and input bus ports")
        if len(source_bits) != len(target_bits):
            raise ValueError(f"Bus width mismatch: {len(source_bits)} output bits, {len(target_bits)} input bits")
        driven = {(wire.target, bit) for wire in self.wires.values()
                  for _, bit in wire_bit_pairs(wire)}
        if any((target, bit) in driven for bit in target_bits):
            raise ValueError("One or more destination bus bits already have a driver")
        wire = BusWire(new_id(), source, source_port, target, target_port, list(bends or []),
                       len(source_bits), list(source_bits), list(target_bits))
        self.wires[wire.id] = wire
        return wire

    def remove(self, cid):
        self.components.pop(cid, None)
        self.wires = {wid: w for wid, w in self.wires.items() if w.source != cid and w.target != cid}

    def validate(self):
        errors, driven = [], set()
        pin_cache, bus_cache = {}, {}
        def interface(cid):
            if cid not in pin_cache:
                pin_cache[cid] = pins(self.components[cid], self.blocks)
            return pin_cache[cid]
        def buses(cid):
            if cid not in bus_cache:
                bus_cache[cid] = bus_ports(self.components[cid], self.blocks)
            return bus_cache[cid]
        for w in self.wires.values():
            if w.source not in self.components or w.target not in self.components:
                errors.append(f"Wire {w.id}: missing component")
                continue
            if isinstance(w, BusWire):
                try:
                    source_bits = buses(w.source)["output"].get(w.source_pin)
                    target_bits = buses(w.target)["input"].get(w.target_pin)
                except (ValueError, KeyError, TypeError) as error:
                    errors.append(f"Bus {w.id}: {error}")
                    continue
                if (type(w.width) is not int or w.width not in BUS_WIDTHS or
                        not isinstance(w.source_bits, list) or not isinstance(w.target_bits, list) or
                        source_bits is None or target_bits is None or
                        len(w.source_bits) != w.width or len(w.target_bits) != w.width or
                        tuple(w.source_bits) != source_bits or tuple(w.target_bits) != target_bits):
                    errors.append(f"Bus {w.id}: invalid width or bit mapping")
                    continue
            elif (w.source_pin not in interface(w.source)[1] or
                  w.target_pin not in interface(w.target)[0]):
                errors.append(f"Wire {w.id}: invalid pin")
                continue
            for _, target_pin in wire_bit_pairs(w):
                if (w.target, target_pin) in driven:
                    errors.append(f"Wire {w.id}: multiple drivers on {target_pin}")
                driven.add((w.target, target_pin))
        return errors

    def bus_warnings(self):
        driven = {(wire.target, bit) for wire in self.wires.values()
                  for _, bit in wire_bit_pairs(wire)}
        return [f"Bus Merger {component.id}: unconnected {pin} becomes X"
                for component in self.components.values() if component.kind == "Bus Merger"
                for pin in pins(component, self.blocks)[0] if (component.id, pin) not in driven]

    def to_dict(self):
        data = {"format": "logicspace", "version": 1, "tick": self.tick,
                "components": [vars(c) for c in self.components.values()],
                "wires": [wire_to_dict(w) for w in self.wires.values()], "blocks": self.blocks}
        if self.testbenches is not None:
            data["testbenches"] = deepcopy(self.testbenches)
        elif self._invalid_testbenches is not None:
            data["testbenches"] = deepcopy(self._invalid_testbenches)
        if self.cpu_workspace is not None:
            data["cpu_workspace"] = deepcopy(self.cpu_workspace)
        if self.cpu_architectures is not None:
            data["cpu_architectures"] = deepcopy(self.cpu_architectures)
        if self.project_info is not None:
            data["project_info"] = deepcopy(self.project_info)
        if self.fpga_workspace is not None:
            data["fpga_workspace"] = deepcopy(self.fpga_workspace)
        if self.hdl_sources is not None:
            data["hdl_sources"] = deepcopy(self.hdl_sources)
        return data

    @classmethod
    def from_dict(cls, data):
        if data.get("format") != "logicspace" or data.get("version") != 1:
            raise ValueError("Unsupported circuit file")
        c = cls()
        c.tick = int(data.get("tick", 0))
        c.blocks = deepcopy(data.get("blocks", {}))
        for item in data.get("components", []):
            obj = Component(**deepcopy(item))
            pins(obj, c.blocks)
            if obj.id in c.components:
                raise ValueError("Duplicate component ID")
            c.components[obj.id] = obj
        for item in data.get("wires", []):
            w = wire_from_dict(item)
            if w.id in c.wires:
                raise ValueError("Duplicate wire ID")
            c.wires[w.id] = w
        if c.validate():
            raise ValueError("; ".join(c.validate()))
        if "cpu_workspace" in data:
            workspace = data["cpu_workspace"]
            if (not isinstance(workspace, dict) or workspace.get("version") != 1 or
                    not isinstance(workspace.get("source"), str) or
                    not isinstance(workspace.get("ids"), dict) or
                    any(not isinstance(role, str) or not isinstance(cid, str)
                        for role, cid in workspace["ids"].items())):
                raise ValueError("Invalid CPU workspace metadata or missing board component")
            c.cpu_workspace = deepcopy(workspace)
        if "cpu_architectures" in data:
            registry = data["cpu_architectures"]
            if (not isinstance(registry, dict) or registry.get("version") != 1 or
                    not isinstance(registry.get("items"), list) or
                    len(registry["items"]) > 64 or
                    not all(isinstance(item, dict) and item.get("version") == 1 and
                            isinstance(item.get("id"), str) and isinstance(item.get("name"), str) and
                            isinstance(item.get("source"), str) and isinstance(item.get("ids"), dict) and
                            all(isinstance(role, str) and isinstance(cid, str)
                                for role, cid in item["ids"].items())
                            for item in registry["items"]) or
                    len({item["id"] for item in registry["items"]}) != len(registry["items"]) or
                    registry.get("active") not in (None, *(item["id"] for item in registry["items"]))):
                raise ValueError("Invalid CPU architecture bindings")
            c.cpu_architectures = deepcopy(registry)
        if "project_info" in data:
            info = data["project_info"]
            if (not isinstance(info, dict) or info.get("version") != 1 or
                    any(not isinstance(info.get(key, ""), str)
                        for key in ("name", "description", "source_template"))):
                raise ValueError("Invalid project information")
            c.project_info = deepcopy(info)
        if "fpga_workspace" in data:
            from fpga_model import validate_workspace_schema
            c.fpga_workspace = validate_workspace_schema(data["fpga_workspace"])
        if "hdl_sources" in data:
            sources = data["hdl_sources"]
            if (not isinstance(sources, dict) or len(sources) > 64 or
                    any(not isinstance(key, str) or not isinstance(value, dict) or
                            not isinstance(value.get("module"), str) or
                            not isinstance(value.get("source"), str) or
                            len(value["source"]) > 1_000_000 or
                            not isinstance(value.get("filename", ""), str)
                            for key, value in sources.items())):
                raise ValueError("Invalid HDL source navigation metadata")
            c.hdl_sources = deepcopy(sources)
        if "testbenches" in data:
            from testbench_model import validate_package
            package = deepcopy(data["testbenches"])
            try:
                c.testbench_issues = validate_package(c, package, allow_missing_refs=True)
                c.testbenches = package
            except (ValueError, TypeError, KeyError) as error:
                c.testbench_issues = [f"Testbench data is invalid: {error}"]
                c._invalid_testbenches = package
        return c

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


def copy_selection(circuit, selected, dx=40, dy=40):
    mapping = {}
    for cid in selected:
        if cid not in circuit.components:
            continue
        c = deepcopy(circuit.components[cid])
        c.id = new_id()
        c.x += dx
        c.y += dy
        mapping[cid] = c.id
        circuit.components[c.id] = c
    for w in list(circuit.wires.values()):
        if w.source in mapping and w.target in mapping:
            clone = deepcopy(w)
            clone.id = new_id()
            clone.source = mapping[w.source]
            clone.target = mapping[w.target]
            clone.bends = [[x + dx, y + dy] for x, y in w.bends]
            circuit.wires[clone.id] = clone
    return list(mapping.values())


class Simulator:
    def __init__(self, circuit, block_stack=()):
        self.circuit = circuit
        self.block_stack = block_stack
        self.outputs = {}
        self.inputs = {}
        self.errors = []
        self.warnings = []
        # Facts from the latest completed tick, used by the debugger. This is
        # transient simulation data and is never written to circuit JSON.
        self.last_transitions = {}
        self.last_block_events = {}
        # Temporary debugger forces live only in this simulator, never in circuit JSON.
        self.forced_inputs = {}
        self.forced_outputs = {}
        self._order_key = None
        self._order_value = None
        self.evaluate()

    def force_pin(self, component_id, pin, direction, value):
        if value not in (0, 1):
            raise ValueError("A pin can only be forced to 0 or 1")
        component = self.circuit.components.get(component_id)
        if component is None or direction not in ("input", "output"):
            raise ValueError("Invalid pin")
        inputs, outputs = pins(component, self.circuit.blocks)
        if pin not in (inputs if direction == "input" else outputs):
            raise ValueError("Invalid pin")
        target = self.forced_inputs if direction == "input" else self.forced_outputs
        target[component_id, pin] = value
        self.evaluate()

    def release_pin(self, component_id, pin, direction):
        if direction not in ("input", "output"):
            raise ValueError("Invalid pin direction")
        target = self.forced_inputs if direction == "input" else self.forced_outputs
        target.pop((component_id, pin), None)
        self.evaluate()

    def reset(self):
        previous = {cid: trace_state(c)
                    for cid, c in self.circuit.components.items() if c.kind in SEQUENTIAL}
        self.forced_inputs.clear()
        self.forced_outputs.clear()
        self.circuit.tick = 0
        for c in self.circuit.components.values():
            if c.kind in ("EEPROM", "Flash Memory"):
                memory = c.state.get("memory", {})
                c.state.clear()
                c.state["memory"] = memory
            else:
                c.state.clear()
        self.evaluate()
        self.last_block_events = {}
        self.last_transitions = {
            cid: {"step": 0, "event": "simulation reset", "previous": previous[cid],
                  "current": trace_state(self.circuit.components[cid]),
                  "inputs": dict(self.inputs.get(cid, {}))}
            for cid in previous}

    def step(self):
        self.evaluate(advance=True)

    def _order(self):
        c = self.circuit
        key = (tuple((cid, comp.kind,
                      memory_read_mode(comp) if comp.kind in ("RAM", "ROM") else None)
                     for cid, comp in c.components.items()),
               tuple((wire.id, wire.source, wire.target, wire.target_pin)
                     for wire in c.wires.values()))
        if key == self._order_key:
            return self._order_value
        dependencies = defaultdict(set)
        followers = defaultdict(set)
        for w in c.wires.values():
            target = c.components[w.target]
            sequential_read = (target.kind == "RAM" and memory_read_mode(target) == "async"
                               and (w.target_pin.startswith("A") or w.target_pin == "RE"))
            rom_clocked = target.kind == "ROM" and memory_read_mode(target) == "sync"
            if (target.kind not in SEQUENTIAL and not rom_clocked or sequential_read or
                    target.kind == "Register File" and w.target_pin.startswith("RA")):
                dependencies[w.target].add(w.source)
                followers[w.source].add(w.target)
        degree = {cid: len(dependencies[cid]) for cid in c.components}
        ready = deque(sorted(cid for cid, n in degree.items() if n == 0))
        order = []
        while ready:
            cid = ready.popleft()
            order.append(cid)
            for target in sorted(followers[cid]):
                degree[target] -= 1
                if degree[target] == 0:
                    ready.append(target)
        result = (order, set(c.components) - set(order))
        self._order_key, self._order_value = key, result
        return result

    def _apply_async_resets(self):
        """Commit independently asserted reset inputs after combinational settling."""
        changes = {}
        for cid, component in self.circuit.components.items():
            if component.kind not in ("D Flip-Flop", "Register") or not component.params.get("async_reset"):
                continue
            level = self.inputs.get(cid, {}).get("ARST")
            active = component.params.get("reset_active", 1)
            if level not in (active, None):
                continue
            key = "q" if component.kind == "D Flip-Flop" else "value"
            old = component.state.get(key, component.params.get("initial", 0))
            reset_value = component.params.get("reset_value", 0)
            new = reset_value if level == active else (old if old == reset_value else None)
            if old != new:
                before = trace_state(component)
                component.state[key] = new
                if component.kind == "Register":
                    component.state["bit_values"] = None if new is not None else [None] * bit_width(component)
                changes[cid] = {"step": self.circuit.tick, "event": "asynchronous reset",
                                "previous": before, "inputs": dict(self.inputs[cid]),
                                "reset": level == active, "reset_unknown": level is None}
        return changes

    def evaluate(self, advance=False):
        c = self.circuit
        self.errors = c.validate()
        self.warnings = c.bus_warnings() if not self.errors else []
        if self.errors:
            self.outputs.clear()
            self.inputs.clear()
            return
        order, loops = self._order()
        if loops:
            self.errors.append("Combinational feedback loop: " + ", ".join(sorted(loops)))
        drivers = {(w.target, target_pin): (w.source, source_pin)
                   for w in c.wires.values() for source_pin, target_pin in wire_bit_pairs(w)}
        async_events = {}
        for _ in range(8):
            self.outputs, self.inputs = {}, {}
            for cid, comp in c.components.items():
                if (comp.kind in SEQUENTIAL and not (comp.kind == "RAM" and memory_read_mode(comp) == "async") or
                        comp.kind == "ROM" and memory_read_mode(comp) == "sync"):
                    for pin, value in self._state_outputs(comp).items():
                        self.outputs[cid, pin] = self.forced_outputs.get((cid, pin), value)
            for cid in order:
                comp = c.components[cid]
                ip, op = pins(comp, c.blocks)
                values = {p: self.forced_inputs.get((cid, p), self.outputs.get(drivers.get((cid, p)))) for p in ip}
                self.inputs[cid] = values
                combinational_ram = comp.kind == "RAM" and memory_read_mode(comp) == "async"
                clocked_rom = comp.kind == "ROM" and memory_read_mode(comp) == "sync"
                if (comp.kind not in SEQUENTIAL or comp.kind == "Register File" or combinational_ram) and not clocked_rom:
                    result = (self._register_file_read(comp, values) if comp.kind == "Register File" else
                              self._async_ram_read(comp, values) if combinational_ram else self._compute(comp, values))
                    for p in op:
                        self.outputs[cid, p] = self.forced_outputs.get((cid, p), result.get(p))
            for cid in loops:
                comp = c.components[cid]
                self.inputs[cid] = {p: None for p in pins(comp, c.blocks)[0]}
                for p in pins(comp, c.blocks)[1]:
                    self.outputs[cid, p] = None
            # Sequential outputs are seeded before the combinational pass, but
            # their input values must be sampled after every driver has settled.
            # Otherwise random component IDs can make reset/clock inputs appear X.
            for cid, comp in c.components.items():
                if comp.kind in SEQUENTIAL or comp.kind == "ROM" and memory_read_mode(comp) == "sync":
                    self.inputs[cid] = {
                        p: self.forced_inputs.get((cid, p), self.outputs.get(drivers.get((cid, p))))
                        for p in pins(comp, c.blocks)[0]
                    }
            changes = self._apply_async_resets()
            for cid, event in changes.items():
                async_events.setdefault(cid, event)
            if not changes: break
        else:
            self.errors.append("Asynchronous reset feedback did not settle in 8 passes")
        if async_events and not advance:
            self.last_transitions = {cid: {**event, "current": trace_state(c.components[cid])}
                                     for cid, event in async_events.items()}
        if advance:
            updates = {}
            transitions = {}
            self._pending_block_events = {}
            self._advance_warnings = []
            for cid, comp in c.components.items():
                if comp.kind in SEQUENTIAL or comp.kind == "ROM" and memory_read_mode(comp) == "sync":
                    values = {p: self.forced_inputs.get((cid, p), self.outputs.get(drivers.get((cid, p))))
                              for p in pins(comp, c.blocks)[0]}
                    updates[cid] = self._next_state(comp, values)
                    transitions[cid] = {
                        "step": c.tick + 1,
                        "previous": async_events[cid]["previous"] if cid in async_events else trace_state(comp),
                        "inputs": dict(values),
                        "clock_edge": self._edge(comp, values) if "CLK" in values else False,
                        "reset": values.get("RESET") == 1,
                        "async_reset": cid in async_events or
                                       comp.params.get("async_reset", False) and
                                       values.get("ARST") == comp.params.get("reset_active", 1),
                    }
                elif comp.kind.startswith("BLOCK:"):
                    values = {p: self.forced_inputs.get((cid, p), self.outputs.get(drivers.get((cid, p))))
                              for p in pins(comp, c.blocks)[0]}
                    updates[cid] = self._advance_block(comp, values)
            for cid, state in updates.items():
                c.components[cid].state.update(state)
            c.tick += 1
            self.evaluate()
            self.warnings.extend(self._advance_warnings)
            for cid, event in transitions.items():
                comp = c.components[cid]
                event["current"] = trace_state(comp)
            self.last_transitions = transitions
            self.last_block_events = self._pending_block_events
            del self._pending_block_events
            del self._advance_warnings

    def _state_outputs(self, c):
        k, s = c.kind, c.state
        if k in ("SR Latch", "D Latch", "D Flip-Flop", "JK Flip-Flop", "T Flip-Flop"):
            q = s.get("q", c.params.get("initial", 0))
            return {"Q": q, "!Q": invert(q)}
        if k in ("Register", "Shift Register", "Binary Counter", "Up Counter", "Down Counter",
                 "Program Counter", "Instruction Register"):
            if k == "Register" and isinstance(s.get("bit_values"), list):
                return {f"Q{i}": value for i, value in enumerate(s["bit_values"])}
            return from_int(s.get("value", c.params.get("initial", 0)), len(pins(c, self.circuit.blocks)[1]))
        if k in ("Clock Divider", "Timer", "Pulse Generator"):
            return {"Q": s.get("q", 0)}
        if k == "ISA Control Unit":
            return isa_control_outputs(s)
        if k in ("RAM", "SRAM", "DRAM", "EEPROM", "Flash Memory"):
            return from_int(s.get("read"), len(pins(c, self.circuit.blocks)[1]))
        if k == "ROM" and memory_read_mode(c) == "sync":
            return from_int(s.get("read"), len(pins(c, self.circuit.blocks)[1]))
        return {}

    def _async_ram_read(self, component, values):
        address_bits, data_bits, depth = memory_geometry(component)
        address = to_int([values[f"A{i}"] for i in range(address_bits)])
        enabled = values.get("RE", 1)
        if address is not None and address >= depth:
            self.warnings.append(f"RAM {component.id}: address {address} is outside 0–{depth - 1}")
        if enabled != 1 or address is None or address >= depth:
            return from_int(None, data_bits)
        memory = component.state.get("memory", component.params.get("init", {}))
        return from_int(memory.get(str(address), 0), data_bits)

    def _register_file_read(self, component, values):
        count, data, reads, address = register_file_geometry(component)
        words = component.state.get("words", {})
        result = {}
        for port in range(reads):
            index = to_int([values[f"RA{port}_{bit}"] for bit in range(address)])
            if index is not None and index >= count:
                self.warnings.append(f"Register File {component.id}: read address {index} is outside 0–{count - 1}")
            word = words.get(str(index), 0) if index is not None and index < count else None
            result.update(from_int(word, data, f"R{port}_"))
        return result

    def _edge(self, c, v):
        before, now = c.state.get("last_clk", 0), v.get("CLK")
        return before == 0 and now == 1 if c.params.get("edge", "rising") == "rising" else before == 1 and now == 0

    def _next_state(self, c, v):
        k, s = c.kind, c.state
        update = {}
        edge = self._edge(c, v) if "CLK" in v else False
        if "CLK" in v:
            update["last_clk"] = v["CLK"]
        q = s.get("q", c.params.get("initial", 0))
        if k == "SR Latch":
            a, b = v["S"], v["R"]
            update["q"] = None if a is None or b is None or a == b == 1 else (1 if a else (0 if b else q))
        elif k == "D Latch":
            if v["E"] == 1: update["q"] = v["D"]
            elif v["E"] is None: update["q"] = None
        elif k == "D Flip-Flop":
            if c.params.get("async_reset") and v.get("ARST") == c.params.get("reset_active", 1):
                update["q"] = c.params.get("reset_value", 0)
            elif c.params.get("async_reset") and v.get("ARST") is None:
                update["q"] = None
            elif edge:
                update["q"] = v["D"]
        elif k == "JK Flip-Flop" and edge:
            j, kk = v["J"], v["K"]
            update["q"] = None if j is None or kk is None else (invert(q) if j == kk == 1 else (1 if j else (0 if kk else q)))
        elif k == "T Flip-Flop" and edge:
            update["q"] = None if v["T"] is None or q is None else q ^ v["T"]
        elif k == "Register":
            if c.params.get("async_reset") and v.get("ARST") == c.params.get("reset_active", 1):
                update["value"] = c.params.get("reset_value", 0)
                update["bit_values"] = None
            elif c.params.get("async_reset") and v.get("ARST") is None:
                update["value"] = None
                update["bit_values"] = [None] * bit_width(c)
            elif edge:
                bits = [v[f"D{i}"] for i in range(bit_width(c))]
                update["value"] = to_int(bits)
                update["bit_values"] = bits if None in bits else None
        elif k == "Instruction Register" and edge:
            if v["LOAD"] == 1:
                update["value"] = to_int([v[f"D{i}"] for i in range(bit_width(c))])
            elif v["LOAD"] is None:
                update["value"] = None
        elif k == "Program Counter":
            if v["RESET"] == 1:
                update["value"] = 0
            elif edge:
                if v["RESET"] is None or v["ENABLE"] is None:
                    update["value"] = None
                elif v["ENABLE"] == 1:
                    if v["LOAD"] == 1:
                        update["value"] = to_int([v[f"D{i}"] for i in range(bit_width(c))])
                    elif v["LOAD"] is None or v["INC"] is None:
                        update["value"] = None
                    elif v["INC"] == 1:
                        old = s.get("value", 0)
                        update["value"] = None if old is None else (old + 1) & ((1 << bit_width(c)) - 1)
        elif k == "Register File":
            count, data, _, address = register_file_geometry(c)
            index = to_int([v[f"WA{i}"] for i in range(address)])
            if edge and v["WE"] in (1, None) and index is not None and index < count:
                words = dict(s.get("words", {}))
                incoming = to_int([v[f"D{i}"] for i in range(data)]) if v["WE"] == 1 else None
                update.update(words={**words, str(index): incoming}, last_write={
                    "address": index, "previous": words.get(str(index), 0), "current": incoming,
                    "enabled": v["WE"]})
            elif edge and v["WE"] == 1 and index is not None and index >= count:
                self._advance_warnings.append(f"Register File {c.id}: write address {index} is outside 0–{count - 1}")
        elif k == "Shift Register" and edge:
            width = len(pins(c, self.circuit.blocks)[1])
            old = s.get("value", 0)
            update["value"] = None if v["DIN"] is None or old is None else ((old << 1) | v["DIN"]) & ((1 << width) - 1)
        elif k in ("Binary Counter", "Up Counter", "Down Counter"):
            width = len(pins(c, self.circuit.blocks)[1])
            if v["RESET"] == 1: update["value"] = 0
            elif edge:
                old = s.get("value", 0)
                update["value"] = None if old is None else (old + (-1 if k == "Down Counter" else 1)) % (1 << width)
        elif k == "Clock Divider" and edge:
            divisor = max(2, int(c.params.get("divide", 2)))
            count = (s.get("count", 0) + 1) % divisor
            update.update(count=count, q=int(count >= (divisor + 1) // 2))
        elif k == "Timer":
            duration = max(1, int(c.params.get("duration", 5)))
            count = 0 if v["RESET"] == 1 else (s.get("count", 0) + 1 if v["START"] == 1 else s.get("count", 0))
            update.update(count=count, q=int(count >= duration))
        elif k == "Pulse Generator":
            trig = v["TRIG"]
            remaining = max(1, int(c.params.get("duration", 1))) if s.get("last_trig", 0) == 0 and trig == 1 else max(0, s.get("remaining", 0) - 1)
            update.update(last_trig=trig, remaining=remaining, q=int(remaining > 0))
        elif k == "ROM" and memory_read_mode(c) == "sync":
            ab, db, depth = memory_geometry(c)
            addr = to_int([v[f"A{i}"] for i in range(ab)])
            if addr is not None and addr >= depth:
                self._advance_warnings.append(f"ROM {c.id}: address {addr} is outside 0–{depth - 1}")
            if edge and v.get("RE", 1) == 1:
                value = c.params.get("contents", {}).get(str(addr), 0) if addr is not None and addr < depth else None
                update["read"] = value
                update["last_read"] = {"address": addr if addr is not None and addr < depth else None,
                                       "value": value}
            elif edge and v.get("RE", 1) is None:
                update["read"] = None
        elif k in ("RAM", "SRAM", "DRAM", "EEPROM", "Flash Memory"):
            ab, db, depth = memory_geometry(c)
            read_mode = memory_read_mode(c) if k == "RAM" else "legacy"
            addr = to_int([v[f"A{i}"] for i in range(ab)])
            memory = dict(s.get("memory", c.params.get("init", {}) if k == "RAM" else {}))
            blank = (1 << db) - 1 if k == "Flash Memory" else 0
            ages = dict(s.get("ages", {}))
            if k == "DRAM":
                retention = max(1, int(c.params.get("retention_ticks", 64)))
                for key in list(memory):
                    ages[key] = ages.get(key, 0) + 1
                    if ages[key] > retention:
                        memory[key] = None
                if v["REFRESH"] == 1:
                    ages = {key: 0 for key in memory}
                if addr is not None:
                    ages[str(addr)] = 0
            valid_address = addr is not None and addr < depth
            previous_read = memory.get(str(addr), blank) if valid_address else None
            if addr is not None and not valid_address:
                self._advance_warnings.append(f"{k} {c.id}: address {addr} is outside 0–{depth - 1}")
            if edge and k == "Flash Memory" and v["ERASE"] == 1:
                memory.clear()
            elif edge and v["WE"] == 1 and valid_address:
                incoming = to_int([v[f"D{i}"] for i in range(db)])
                if k == "Flash Memory":
                    old = memory.get(str(addr), blank)
                    memory[str(addr)] = None if old is None or incoming is None else old & incoming
                else:
                    memory[str(addr)] = incoming
                if k == "DRAM": ages[str(addr)] = 0
                update["last_write"] = {"address": addr, "previous": s.get("memory", {}).get(str(addr), blank),
                                        "current": memory.get(str(addr)), "enabled": v["WE"]}
            elif edge and k == "RAM" and read_mode != "legacy" and v["WE"] in (1, None):
                # An unknown write control or address can affect any candidate word.
                # Retain the legacy mode's historical behavior for old projects.
                candidate = to_int([v[f"D{i}"] for i in range(db)])
                addresses = (range(depth) if addr is None else (addr,))
                changed = []
                for index in addresses:
                    if index >= depth: continue
                    old = memory.get(str(index), blank)
                    new = old if v["WE"] is None and old == candidate else None
                    if new != old:
                        memory[str(index)] = new
                        changed.append(index)
                if changed:
                    update["last_write"] = {"address": addr if valid_address else None,
                                            "previous": None, "current": None,
                                            "enabled": v["WE"], "possible_addresses": changed}
            update["memory"] = memory
            if read_mode == "legacy":
                update["read"] = memory.get(str(addr), blank) if valid_address else None
                update["last_read"] = {"address": addr if valid_address else None,
                                       "value": update["read"]}
            elif read_mode == "sync" and edge:
                if v.get("RE", 1) == 1:
                    collision = v["WE"] == 1 and valid_address
                    policy = c.params.get("read_during_write", "new")
                    if collision and policy == "old":
                        read_value = previous_read
                    elif collision and policy == "no_change":
                        read_value = s.get("read")
                    else:
                        read_value = memory.get(str(addr), blank) if valid_address else None
                    update["read"] = read_value
                    update["last_read"] = {"address": addr if valid_address else None,
                                           "value": read_value}
                elif v.get("RE") is None:
                    update["read"] = None
            if k == "DRAM": update["ages"] = ages
        elif k == "ISA Control Unit" and edge:
            update.update(self._next_isa_control(c, v))
        elif k.startswith("BLOCK:"):
            pass
        return update

    def _next_isa_control(self, component, values):
        state = component.state
        phase = state.get("phase", "FETCH")
        if phase == "HALT": return {}
        if phase == "FETCH":
            address = to_int([values[f"PC{i}"] for i in range(8)])
            if address is None:
                return {"phase": "HALT", "fault": "Program Counter is X"}
            return {"phase": "DECODE", "current_pc": address, "opcode": None,
                    "arg1": None, "arg2": None}
        if phase == "DECODE":
            opcode = to_int([values[f"IR{i}"] for i in range(8)])
            instruction = BY_OPCODE.get(opcode)
            if instruction is None:
                return {"phase": "HALT", "fault": f"Invalid opcode {opcode!r} at 0x{state.get('current_pc', 0):02X}"}
            following = "READ" if opcode == 0x36 else "ARG1" if instruction.size > 1 else "EXEC"
            return {"opcode": opcode, "phase": following}
        instruction = BY_OPCODE.get(state.get("opcode"))
        if instruction is None:
            return {"phase": "HALT", "fault": "Decoded instruction is unavailable"}
        if phase in ("ARG1", "ARG2"):
            operand = to_int([values[f"ROM_D{i}"] for i in range(8)])
            position = 0 if phase == "ARG1" else 1
            if operand is None:
                return {"phase": "HALT", "fault": f"Instruction operand {position + 1} is X"}
            if instruction.operands[position] == "r" and operand >= 4:
                return {"phase": "HALT", "fault": f"Invalid register R{operand} at 0x{state.get('current_pc', 0):02X}"}
            following = ("ARG2" if phase == "ARG1" and instruction.size == 3 else
                         "READ" if instruction.opcode in (0x12, 0x41) else "EXEC")
            return {"arg1" if phase == "ARG1" else "arg2": operand, "phase": following}
        if phase == "READ":
            if instruction.opcode in (0x41, 0x36):
                sp = state.get("sp", STACK_END)
                if sp >= STACK_END:
                    return {"phase": "HALT", "fault": f"Stack underflow at 0x{state.get('current_pc', 0):02X}"}
                return {"sp": sp + 1, "phase": "EXEC"}
            return {"phase": "EXEC"}
        if phase != "EXEC":
            return {"phase": "HALT", "fault": f"Invalid CPU microphase {phase}"}
        opcode = instruction.opcode
        if opcode in (0x40, 0x35) and state.get("sp", STACK_END) < STACK_START:
            return {"phase": "HALT", "fault": f"Stack overflow at 0x{state.get('current_pc', 0):02X}"}
        flag = state.get("zero", 0) if opcode in (0x31, 0x32) else state.get("carry", 0)
        if opcode in (0x31, 0x32, 0x33, 0x34) and flag is None:
            return {"phase": "HALT", "fault": f"Conditional branch uses X flag at 0x{state.get('current_pc', 0):02X}"}
        update = {"phase": "HALT" if opcode == 0x01 else "FETCH",
                  "instructions": state.get("instructions", 0) + 1,
                  "last_completed": {"address": state.get("current_pc", 0),
                                     "opcode": opcode, "mnemonic": instruction.mnemonic,
                                     "args": [state.get("arg1"), state.get("arg2")][:len(instruction.operands)],
                                     "step": self.circuit.tick + 1}}
        if opcode in (0x12, 0x13, 0x40, 0x41, 0x35, 0x36):
            memory_address = (state.get("arg2") if opcode in (0x12, 0x13) else
                              state.get("sp", STACK_END))
            update["last_completed"]["memory"] = {
                "address": memory_address,
                "access": "read" if opcode in (0x12, 0x41, 0x36) else "write"}
        if opcode in (0x40, 0x35): update["sp"] = state.get("sp", STACK_END) - 1
        if opcode == 0x35: update["call_depth"] = state.get("call_depth", 0) + 1
        if opcode == 0x36: update["call_depth"] = max(0, state.get("call_depth", 0) - 1)
        if opcode in range(0x20, 0x29):
            for target, source in (("zero", "ALU_ZERO"), ("carry", "ALU_CARRY"),
                                   ("negative", "ALU_NEGATIVE"), ("overflow", "ALU_OVERFLOW")):
                update[target] = values[source]
        return update

    def _compute(self, c, v):
        k = c.kind
        if k in ("HDL Truth", "HDL Case Match"):
            width = bit_width(c)
            bits = [v.get("A" if width == 1 else f"A{i}") for i in range(width)]
            if k == "HDL Truth":
                return {"Q": int(1 in bits)}
            return {"Q": int(None not in bits and to_int(bits) == c.params["match"])}
        if k == "Bus Input":
            return {f"Q{i}": bit for i, bit in enumerate(bus_input_bits(c))}
        if k in ("Bus Output", "Bus Probe"):
            return {}
        if k == "Bus Splitter":
            return {pin: v.get("D" + pin[1:]) for pin in pins(c, self.circuit.blocks)[1]}
        if k == "Bus Merger":
            return {f"Q{i}": v.get(f"D{i}") for i in range(bus_component_width(c))}
        if k == "Bit Selector":
            return {"Q": v.get(f"D{c.params.get('index', 0)}")}
        if k in ("INPUT", "CONST"):
            width = bit_width(c)
            value = c.params.get("value", 0 if k == "INPUT" else 1)
            if width == 1: return {"Q": None if value is None else int(bool(value))}
            explicit = c.params.get("_bit_values")
            if explicit is not None:
                return {f"Q{i}": explicit[i] for i in range(width)}
            return from_int(value, width)
        if k == "OUTPUT" or k in ANALOG or k in DISPLAYS: return {}
        if k in ("Clock Generator", "Oscillator"):
            period = max(2, int(c.params.get("period", 4)))
            return {"Q": int(bool(c.params.get("running", True)) and self.circuit.tick % period >= period // 2)}
        a, b = v.get("A"), v.get("B")
        if k in LOGIC_GATES:
            def gate(left, right):
                return {"AND": land(left, right), "OR": lor(left, right), "NOT": invert(left),
                        "NAND": invert(land(left, right)), "NOR": invert(lor(left, right)),
                        "XOR": lxor(left, right), "XNOR": invert(lxor(left, right))}[k]
            width = bit_width(c)
            if width == 1: return {"Q": gate(a, b)}
            return {f"Q{i}": gate(v[f"A{i}"], v.get(f"B{i}")) for i in range(width)}
        if k in ("Half Adder", "Full Adder"):
            carry = v.get("CIN", 0)
            return {"SUM": lxor(a, b, carry), "CARRY" if k == "Half Adder" else "COUT": lor(land(a, b), land(a, carry), land(b, carry))}
        if k in ("Half Subtractor", "Full Subtractor"):
            borrow = v.get("BIN", 0)
            return {"DIFF": lxor(a, b, borrow), "BORROW" if k == "Half Subtractor" else "BOUT": lor(land(invert(a), b), land(invert(lxor(a, b)), borrow))}
        if k == "Comparator":
            if bit_width(c) > 1:
                width = bit_width(c)
                a = to_int([v[f"A{i}"] for i in range(width)])
                b = to_int([v[f"B{i}"] for i in range(width)])
            return {"LT": None if None in (a, b) else int(a < b),
                    "EQ": None if None in (a, b) else int(a == b),
                    "GT": None if None in (a, b) else int(a > b)}
        if k == "Multiplexer":
            s = v["SEL"]
            if bit_width(c) > 1:
                return {f"Q{i}": (v[f"A{i}"] if s == 0 else
                                   (v[f"B{i}"] if s == 1 else
                                    (v[f"A{i}"] if v[f"A{i}"] == v[f"B{i}"] else None)))
                        for i in range(bit_width(c))}
            return {"Q": a if s == 0 else (b if s == 1 else (a if a == b else None))}
        if k == "Demultiplexer":
            if bit_width(c) > 1:
                result = {}
                for i in range(bit_width(c)):
                    result[f"Q0_{i}"] = land(v[f"A{i}"], invert(v["SEL"]))
                    result[f"Q1_{i}"] = land(v[f"A{i}"], v["SEL"])
                return result
            return {"Q0": land(a, invert(v["SEL"])), "Q1": land(a, v["SEL"])}
        if k == "Decoder":
            return {f"Q{i}": land(a if i & 1 else invert(a), b if i & 2 else invert(b)) for i in range(4)}
        if k == "Encoder":
            active = [i for i in range(4) if v[f"D{i}"] == 1]
            n = active[0] if len(active) == 1 and None not in v.values() else None
            return {"A": None if n is None else n & 1, "B": None if n is None else n >> 1 & 1}
        if k == "ROM":
            ab, data, depth = memory_geometry(c)
            addr = to_int([v[f"A{i}"] for i in range(ab)])
            contents = c.params.get("contents", {})
            if v.get("RE", 1) != 1:
                return from_int(None, data)
            if addr is not None and addr >= depth:
                self.warnings.append(f"ROM {c.id}: address {addr} is outside 0–{depth - 1}")
            return from_int(contents.get(str(addr), 0) if addr is not None and addr < depth else None, data)
        if k == "Address Decoder":
            address = c.params.get("address_bits", 3)
            count = c.params.get("outputs", 1 << address)
            value = to_int([v[f"A{i}"] for i in range(address)])
            if value is not None and value >= count:
                self.warnings.append(f"Address Decoder {c.id}: address {value} has no select output")
            return {f"S{i}": None if value is None or value >= count else int(i == value)
                    for i in range(count)}
        if k == "Control Unit":
            width, table = control_geometry(c)
            opcode = to_int([v[f"OP{i}"] for i in range(width)])
            entry = table.get(str(opcode)) if opcode is not None else None
            if opcode is not None and entry is None:
                self.warnings.append(f"Control Unit {c.id}: undefined opcode {opcode}")
            if entry is None:
                return {pin: None for pin in pins(c, self.circuit.blocks)[1]}
            result = from_int(entry.get("alu", 0), 4, "ALU_OP")
            result.update({name: entry.get(name, 0) for name in CONTROL_SIGNALS})
            if entry.get("branch_zero"):
                result["PC_LOAD"] = v.get("ZERO")
                result["PC_INC"] = invert(v.get("ZERO"))
            return result
        if k in ("Adder", "Subtractor", "Multiplier", "Divider", "ALU"):
            width = len([p for p in v if p.startswith("A")])
            left = to_int([v[f"A{i}"] for i in range(width)])
            right = to_int([v[f"B{i}"] for i in range(width)])
            if k == "ALU" and c.params.get("alu_version", 1) >= 2:
                return self._advanced_alu(c, v, left, right, width)
            if left is None or right is None: result = None
            elif k == "Adder": result = None if v["CIN"] is None else left + right + v["CIN"]
            elif k == "Subtractor": result = left - right
            elif k == "Multiplier": result = left * right
            elif k == "Divider": result = None if right == 0 else left // right
            else:
                op = to_int([v["OP0"], v["OP1"]])
                result = [left + right, left - right, left & right, left | right][op] if op is not None else None
            out = from_int(result, width)
            if k == "Adder": out["COUT"] = None if result is None else int(result >= 1 << width)
            return out
        if k.startswith("BLOCK:"):
            return self._block(c, v)
        return {}

    def _advanced_alu(self, component, values, left, right, width):
        opcode = to_int([values.get(f"OP{i}") for i in range(4)])
        mask, sign = (1 << width) - 1, 1 << (width - 1)
        result = carry = overflow = None
        if opcode is None or opcode > 10:
            if opcode is not None:
                self.warnings.append(f"ALU {component.id}: undefined operation {opcode}")
        elif opcode in (2, 3, 4, 5):
            bits = []
            for i in range(width):
                a, b = values.get(f"A{i}"), values.get(f"B{i}")
                bits.append((land(a, b) if opcode == 2 else lor(a, b) if opcode == 3 else
                             lxor(a, b) if opcode == 4 else invert(a)))
            result = to_int(bits)
            outputs = {f"Q{i}": bit for i, bit in enumerate(bits)}
            carry = overflow = 0
        elif opcode == 0 and left is not None and right is not None:
            raw = left + right
            result, carry = raw & mask, int(raw > mask)
            overflow = int(bool((~(left ^ right) & (left ^ result) & sign)))
        elif opcode == 1 and left is not None and right is not None:
            result, carry = (left - right) & mask, int(left >= right)
            overflow = int(bool(((left ^ right) & (left ^ result) & sign)))
        elif opcode == 6 and left is not None:
            result, carry, overflow = (left << 1) & mask, int(bool(left & sign)), 0
        elif opcode == 7 and left is not None:
            result, carry, overflow = left >> 1, left & 1, 0
        elif opcode in (8, 9, 10) and left is not None and right is not None:
            result = int((left == right) if opcode == 8 else (left < right) if opcode == 9 else (left > right))
            carry = overflow = 0
        if opcode not in (2, 3, 4, 5) or opcode is None:
            outputs = from_int(result, width)
        bits = [outputs[f"Q{i}"] for i in range(width)]
        zero = 0 if 1 in bits else (1 if None not in bits else None)
        outputs.update(ZERO=zero, CARRY=carry, NEGATIVE=bits[-1], OVERFLOW=overflow)
        return outputs

    def _block(self, c, values):
        name = c.kind[6:]
        if name in self.block_stack:
            self.errors.append(f"Recursive custom block: {name}")
            return {p: None for p in pins(c, self.circuit.blocks)[1]}
        definition = self.circuit.blocks[name]
        inner = Circuit.from_dict(definition["circuit"])
        inner.tick = c.state.get("inner_tick", 0)
        self._set_block_inputs(inner, definition, values)
        for cid, state in c.state.get("inner", {}).items():
            if cid in inner.components:
                inner.components[cid].state = deepcopy(state)
        sim = Simulator(inner, self.block_stack + (name,))
        self.errors.extend(f"Block {c.kind[6:]}: {error}" for error in sim.errors)
        result = {external: sim.inputs.get(target if isinstance(target, str) else target[0], {}).get(
            "A" if isinstance(target, str) else target[1])
            for external, target in definition["output_map"].items()}
        return result

    @staticmethod
    def _set_block_inputs(inner, definition, values):
        bit_values = {}
        for external, target in definition["input_map"].items():
            if isinstance(target, str):
                inner.components[target].params["value"] = values.get(external)
            else:
                cid, pin = target
                bit_values.setdefault(cid, {})[int(pin[1:])] = values.get(external)
        for cid, mapped in bit_values.items():
            width = bit_width(inner.components[cid])
            inner.components[cid].params["_bit_values"] = [mapped.get(i) for i in range(width)]

    def _advance_block(self, c, values):
        name = c.kind[6:]
        if name in self.block_stack:
            return {}
        definition = self.circuit.blocks[name]
        inner = Circuit.from_dict(definition["circuit"])
        inner.tick = c.state.get("inner_tick", 0)
        self._set_block_inputs(inner, definition, values)
        for cid, state in c.state.get("inner", {}).items():
            if cid in inner.components:
                inner.components[cid].state = deepcopy(state)
        inner_sim = Simulator(inner, self.block_stack + (name,))
        inner_sim.step()
        self._pending_block_events[c.id] = {
            "transitions": deepcopy(inner_sim.last_transitions),
            "blocks": deepcopy(inner_sim.last_block_events),
        }
        return {"inner_tick": inner.tick,
                "inner": {cid: deepcopy(obj.state) for cid, obj in inner.components.items() if obj.state}}

"""Regenerate cpu_8bit.json using LogicSpace's public circuit API."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Circuit, Simulator


def build():
    circuit = Circuit()

    def add(kind, x, y, label, **params):
        return circuit.add(kind, x, y, {"label": label, **params})

    def wire(source, source_pin, target, target_pin):
        circuit.connect(source.id, source_pin, target.id, target_pin)

    def bus(source, source_port, target, target_port):
        circuit.connect_bus(source.id, source_port, target.id, target_port)

    clock = add("Clock Generator", -980, -200, "CPU clock", period=2)
    one = add("CONST", -980, 40, "Enable", value=1)
    zero = add("CONST", -980, 250, "Reset / Z", value=0)
    branch_target = add("Bus Input", -980, 470, "Jump target", width=8, value=0)
    pc = add("Program Counter", -650, -220, "PC", width=8)
    rom = add("ROM", -350, -220, "Program ROM", address_bits=4, data_bits=8, depth=16,
              contents={"0": 0, "1": 1, "2": 2, "3": 5, "4": 6})
    ir = add("Instruction Register", -50, -220, "Instruction", width=8)
    control = add("Control Unit", 270, -220, "Control", opcode_bits=4)

    addr_a = add("Bus Input", -700, 220, "Read A · r0", width=2, value=0)
    addr_b = add("Bus Input", -700, 410, "Read B · r1", width=2, value=1)
    addr_write = add("Bus Input", -700, 600, "Write · r2", width=2, value=2)
    rf = add("Register File", -340, 300, "Registers", registers=4, data_bits=8, read_ports=2)
    rf.state["words"] = {"0": 5, "1": 3}
    alu = add("ALU", 70, 310, "ALU", width=8)
    ram = add("RAM", 450, 410, "Data RAM", address_bits=2, data_bits=8, depth=4)

    pc_probe = add("Bus Probe", -380, -520, "PC value", width=8, display="hex")
    ir_probe = add("Bus Probe", 20, -520, "Instruction", width=8, display="hex")
    alu_probe = add("Bus Probe", 430, 200, "ALU result", width=8, display="hex")
    ram_probe = add("Bus Probe", 770, 410, "RAM read", width=8, display="hex")

    for target in (pc, ir, rf, ram):
        wire(clock, "Q", target, "CLK")
    wire(one, "Q", pc, "ENABLE")
    wire(one, "Q", ir, "LOAD")
    wire(zero, "Q", pc, "RESET")
    wire(zero, "Q", control, "ZERO")
    bus(branch_target, "Q", pc, "D")
    wire(control, "PC_INC", pc, "INC")
    wire(control, "PC_LOAD", pc, "LOAD")
    bus(pc, "Q", pc_probe, "D")
    for bit in range(4):
        wire(pc, f"Q{bit}", rom, f"A{bit}")
        wire(ir, f"Q{bit}", control, f"OP{bit}")
    bus(rom, "Q", ir, "D")
    bus(ir, "Q", ir_probe, "D")

    bus(addr_a, "Q", rf, "RA0")
    bus(addr_b, "Q", rf, "RA1")
    bus(addr_write, "Q", rf, "WA")
    bus(addr_write, "Q", ram, "A")
    wire(control, "REG_WE", rf, "WE")
    wire(control, "MEM_WE", ram, "WE")
    bus(rf, "R0", alu, "A")
    bus(rf, "R1", alu, "B")
    bus(control, "ALU_OP", alu, "OP")
    bus(alu, "Q", rf, "D")
    bus(alu, "Q", ram, "D")
    bus(alu, "Q", alu_probe, "D")
    bus(ram, "Q", ram_probe, "D")

    simulator = Simulator(circuit)
    if simulator.errors:
        raise ValueError("CPU example has invalid topology: " + "; ".join(simulator.errors))
    return circuit


if __name__ == "__main__":
    destination = Path(__file__).with_name("cpu_8bit.json")
    build().save(destination)
    print(destination)

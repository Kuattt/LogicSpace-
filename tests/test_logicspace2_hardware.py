"""Advanced buses, memory and CPU blocks use the existing Simulator."""
import json
import unittest
from pathlib import Path

from engine import Circuit, Simulator, pins
from testbench_model import TestbenchSession, new_testbench, signal_ref_dict
from timing_model import SignalRef
from time_travel_model import SimulationHistory
from tracing_model import TraceAnalyzer, TraceFrame
from tests.test_bus import chain


def bus(sim, component, port="Q", direction="output"):
    return SignalRef.bus_port(component.id, port, direction).value(sim)


def integer(bits):
    return None if None in bits else sum(bit << i for i, bit in enumerate(bits))


def driven_bit(circuit, value, target, pin):
    source = circuit.add("INPUT", params={"value": value})
    circuit.connect(source.id, "Q", target.id, pin)
    return source


class WideBusTests(unittest.TestCase):
    def test_16_and_32_bit_split_merge_round_trip(self):
        for width, number in ((16, 0xBEEF), (32, 0xA5C37E19)):
            with self.subTest(width=width):
                circuit, source, splitter, merger, probe, first, last = chain(width, number)
                simulator = Simulator(circuit)
                self.assertEqual(integer(bus(simulator, probe, "D", "input")), number)
                self.assertEqual(first.width, width)
                self.assertEqual(circuit.validate(), [])
                self.assertEqual(integer(tuple(simulator.outputs[splitter.id, f"Q{i}"]
                                               for i in range(width))), number)
                display = circuit.add("Bus Output", params={"width": width})
                circuit.connect_bus(source.id, "Q", display.id, "D")
                simulator.evaluate()
                self.assertEqual(integer(bus(simulator, display, "D", "input")), number)
                restored = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
                self.assertEqual(integer(bus(Simulator(restored), restored.components[probe.id], "D", "input")), number)

    def test_selector_31_unknown_and_width_rejection(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 32, "_bit_values": [0] * 31 + [None]})
        selector = circuit.add("Bit Selector", params={"width": 32, "index": 31})
        circuit.connect_bus(source.id, "Q", selector.id, "D")
        self.assertIsNone(Simulator(circuit).outputs[selector.id, "Q"])
        with self.assertRaisesRegex(ValueError, "outside"):
            circuit.add("Bit Selector", params={"width": 32, "index": 32})
        probe = circuit.add("Bus Probe", params={"width": 16})
        with self.assertRaisesRegex(ValueError, "width mismatch"):
            circuit.connect_bus(source.id, "Q", probe.id, "D")
        with self.assertRaisesRegex(ValueError, "fit"):
            circuit.add("Bus Input", params={"width": 16, "value": 1 << 16})

    def test_32_bit_bus_branch_and_time_travel(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 32, "value": 0xFFFFFFFF})
        sinks = [circuit.add("Bus Probe", params={"width": 32}) for _ in range(2)]
        wires = [circuit.connect_bus(source.id, "Q", sink.id, "D") for sink in sinks]
        simulator = Simulator(circuit)
        history = SimulationHistory(simulator)
        self.assertEqual(len({wire.id for wire in wires}), 2)
        source.params["value"] = 0x12345678
        simulator.step(); history.record(simulator)
        self.assertEqual([integer(bus(simulator, sink, "D", "input")) for sink in sinks],
                         [0x12345678] * 2)
        history.navigate(simulator, 0)
        self.assertEqual(integer(bus(simulator, sinks[0], "D", "input")), 0xFFFFFFFF)


class MemoryTests(unittest.TestCase):
    def test_ram_16_bit_write_read_and_invalid_address(self):
        circuit = Circuit()
        data = circuit.add("Bus Input", params={"width": 16, "value": 0xBEEF})
        ram = circuit.add("RAM", params={"address_bits": 2, "data_bits": 16, "depth": 3})
        address = circuit.add("Bus Input", params={"width": 2, "value": 1})
        clk = driven_bit(circuit, 0, ram, "CLK")
        driven_bit(circuit, 1, ram, "WE")
        circuit.connect_bus(data.id, "Q", ram.id, "D")
        circuit.connect_bus(address.id, "Q", ram.id, "A")
        sim = Simulator(circuit)
        clk.params["value"] = 1; sim.step()
        self.assertEqual(ram.state["memory"]["1"], 0xBEEF)
        self.assertEqual(integer(bus(sim, ram)), 0xBEEF)
        address.params["value"] = 3; clk.params["value"] = 0; sim.step()
        self.assertIsNone(integer(bus(sim, ram)))
        self.assertTrue(any("outside" in warning for warning in sim.warnings))
        self.assertNotIn("3", ram.state["memory"])

    def test_rom_contents_and_invalid_address(self):
        circuit = Circuit()
        address = circuit.add("Bus Input", params={"width": 2, "value": 2})
        rom = circuit.add("ROM", params={"address_bits": 2, "data_bits": 16,
                                          "depth": 3, "contents": {"2": 0xCAFE}})
        circuit.connect_bus(address.id, "Q", rom.id, "A")
        sim = Simulator(circuit)
        self.assertEqual(integer(bus(sim, rom)), 0xCAFE)
        self.assertEqual(Circuit.from_dict(circuit.to_dict()).components[rom.id].params["contents"], {"2": 0xCAFE})
        address.params["value"] = 3; sim.evaluate()
        self.assertIsNone(integer(bus(sim, rom)))
        with self.assertRaisesRegex(ValueError, "contents"):
            circuit.add("ROM", params={"address_bits": 2, "data_bits": 4, "contents": {"0": 16}})
        with self.assertRaisesRegex(ValueError, "contents"):
            circuit.add("ROM", params={"address_bits": 2, "data_bits": 4, "contents": {"01": 3}})

    def test_register_file_two_read_ports_write_and_time_travel(self):
        circuit = Circuit()
        rf = circuit.add("Register File", params={"registers": 4, "data_bits": 8, "read_ports": 2})
        data = circuit.add("Bus Input", params={"width": 8, "value": 0xA5})
        address = circuit.add("Bus Input", params={"width": 2, "value": 2})
        clk = driven_bit(circuit, 0, rf, "CLK")
        driven_bit(circuit, 1, rf, "WE")
        circuit.connect_bus(data.id, "Q", rf.id, "D")
        for port in ("WA", "RA0", "RA1"):
            circuit.connect_bus(address.id, "Q", rf.id, port)
        sim = Simulator(circuit)
        history = SimulationHistory(sim)
        self.assertEqual(integer(bus(sim, rf, "R0")), 0)
        clk.params["value"] = 1; sim.step(); history.record(sim)
        self.assertEqual(integer(bus(sim, rf, "R0")), 0xA5)
        self.assertEqual(integer(bus(sim, rf, "R1")), 0xA5)
        self.assertEqual(rf.state["last_write"]["address"], 2)
        explanation = " ".join(TraceAnalyzer(circuit, TraceFrame.from_simulator(sim), sim).explain(
            SignalRef.component_pin(rf.id, "R0_0", "output")))
        self.assertIn("register 2 was written", explanation)
        history.navigate(sim, 0)
        self.assertEqual(integer(bus(sim, rf, "R0")), 0)
        history.navigate(sim, 1)
        self.assertEqual(integer(bus(sim, rf, "R0")), 0xA5)

    def test_address_decoder(self):
        circuit = Circuit()
        address = circuit.add("Bus Input", params={"width": 4, "value": 3})
        decoder = circuit.add("Address Decoder", params={"address_bits": 4, "outputs": 10})
        circuit.connect_bus(address.id, "Q", decoder.id, "A")
        sim = Simulator(circuit)
        self.assertEqual([sim.outputs[decoder.id, f"S{i}"] for i in range(10)],
                         [int(i == 3) for i in range(10)])
        address.params["value"] = 12; sim.evaluate()
        self.assertTrue(all(sim.outputs[decoder.id, f"S{i}"] is None for i in range(10)))
        self.assertTrue(any("no select output" in warning for warning in sim.warnings))

    def test_32_bit_ram_and_rom(self):
        circuit = Circuit()
        address = circuit.add("Bus Input", params={"width": 2, "value": 0})
        data = circuit.add("Bus Input", params={"width": 32, "value": 0x89ABCDEF})
        ram = circuit.add("RAM", params={"address_bits": 2, "data_bits": 32})
        rom = circuit.add("ROM", params={"address_bits": 2, "data_bits": 32,
                                          "contents": {"0": 0xFEDCBA98}})
        clock = driven_bit(circuit, 0, ram, "CLK")
        driven_bit(circuit, 1, ram, "WE")
        circuit.connect_bus(address.id, "Q", ram.id, "A")
        circuit.connect_bus(address.id, "Q", rom.id, "A")
        circuit.connect_bus(data.id, "Q", ram.id, "D")
        simulator = Simulator(circuit)
        self.assertEqual(integer(bus(simulator, rom)), 0xFEDCBA98)
        clock.params["value"] = 1; simulator.step()
        self.assertEqual(integer(bus(simulator, ram)), 0x89ABCDEF)
        reopened = Circuit.from_dict(circuit.to_dict())
        self.assertEqual(integer(bus(Simulator(reopened), reopened.components[rom.id])), 0xFEDCBA98)


class CpuTests(unittest.TestCase):
    def alu(self, width=8, left=0, right=0, opcode=0):
        circuit = Circuit()
        a = circuit.add("Bus Input", params={"width": width, "value": left})
        b = circuit.add("Bus Input", params={"width": width, "value": right})
        op = circuit.add("Bus Input", params={"width": 4, "value": opcode})
        alu = circuit.add("ALU", params={"width": width})
        circuit.connect_bus(a.id, "Q", alu.id, "A")
        circuit.connect_bus(b.id, "Q", alu.id, "B")
        circuit.connect_bus(op.id, "Q", alu.id, "OP")
        return circuit, a, b, op, alu, Simulator(circuit)

    def test_alu_operations_and_flags(self):
        circuit, a, b, op, alu, sim = self.alu(8, 0x7F, 1, 0)
        self.assertEqual(integer(bus(sim, alu)), 0x80)
        self.assertEqual((sim.outputs[alu.id, "NEGATIVE"], sim.outputs[alu.id, "OVERFLOW"]), (1, 1))
        checks = {1: 0x7E, 2: 1, 3: 0x7F, 4: 0x7E, 5: 0x80,
                  6: 0xFE, 7: 0x3F, 8: 0, 9: 0, 10: 1}
        for opcode, expected in checks.items():
            op.params["value"] = opcode; sim.evaluate()
            self.assertEqual(integer(bus(sim, alu)), expected, f"opcode {opcode}")
        a.params["value"] = 0xFF; b.params["value"] = 1; op.params["value"] = 0
        sim.evaluate()
        self.assertEqual((integer(bus(sim, alu)), sim.outputs[alu.id, "ZERO"],
                          sim.outputs[alu.id, "CARRY"]), (0, 1, 1))

    def test_32_bit_alu_and_flags(self):
        circuit, left, right, opcode, alu, sim = self.alu(32, 0x7FFFFFFF, 1, 0)
        self.assertEqual(integer(bus(sim, alu)), 0x80000000)
        self.assertEqual((sim.outputs[alu.id, "NEGATIVE"], sim.outputs[alu.id, "OVERFLOW"]), (1, 1))
        left.params["value"] = 0xFFFFFFFF; sim.evaluate()
        self.assertEqual((integer(bus(sim, alu)), sim.outputs[alu.id, "CARRY"],
                          sim.outputs[alu.id, "ZERO"]), (0, 1, 1))

    def test_legacy_alu_pins_keep_old_operation(self):
        data = {"format": "logicspace", "version": 1, "tick": 0, "blocks": {}, "wires": [],
                "components": [{"id": "old", "kind": "ALU", "x": 0, "y": 0,
                                "params": {"width": 4}, "state": {}}]}
        circuit = Circuit.from_dict(data)
        ins, outs = pins(circuit.components["old"], circuit.blocks)
        self.assertIn("OP1", ins); self.assertNotIn("OP2", ins)
        self.assertNotIn("ZERO", outs)

    def test_program_counter_and_instruction_register(self):
        circuit = Circuit()
        pc = circuit.add("Program Counter", params={"width": 8})
        ir = circuit.add("Instruction Register", params={"width": 8})
        data = circuit.add("Bus Input", params={"width": 8, "value": 0x3C})
        clk = circuit.add("INPUT", params={"value": 0})
        for target in (pc, ir): circuit.connect(clk.id, "Q", target.id, "CLK")
        circuit.connect_bus(data.id, "Q", pc.id, "D")
        circuit.connect_bus(data.id, "Q", ir.id, "D")
        driven_bit(circuit, 0, pc, "RESET")
        load = driven_bit(circuit, 1, pc, "LOAD")
        inc = driven_bit(circuit, 0, pc, "INC")
        driven_bit(circuit, 1, pc, "ENABLE")
        driven_bit(circuit, 1, ir, "LOAD")
        sim = Simulator(circuit)
        clk.params["value"] = 1; sim.step()
        self.assertEqual(integer(bus(sim, pc)), 0x3C)
        self.assertEqual(integer(bus(sim, ir)), 0x3C)
        load.params["value"] = 0; inc.params["value"] = 1
        clk.params["value"] = 0; sim.step(); clk.params["value"] = 1; sim.step()
        self.assertEqual(integer(bus(sim, pc)), 0x3D)

    def test_control_unit_branch_and_undefined_opcode(self):
        circuit = Circuit()
        opcode = circuit.add("Bus Input", params={"width": 4, "value": 7})
        zero = circuit.add("INPUT", params={"value": 1})
        control = circuit.add("Control Unit")
        circuit.connect_bus(opcode.id, "Q", control.id, "OP")
        circuit.connect(zero.id, "Q", control.id, "ZERO")
        sim = Simulator(circuit)
        self.assertEqual((sim.outputs[control.id, "PC_LOAD"], sim.outputs[control.id, "PC_INC"]), (1, 0))
        zero.params["value"] = 0; sim.evaluate()
        self.assertEqual((sim.outputs[control.id, "PC_LOAD"], sim.outputs[control.id, "PC_INC"]), (0, 1))
        opcode.params["value"] = 15; sim.evaluate()
        self.assertIsNone(sim.outputs[control.id, "ALU_OP0"])
        self.assertTrue(any("undefined opcode" in warning for warning in sim.warnings))
        with self.assertRaisesRegex(ValueError, "microcode"):
            circuit.add("Control Unit", params={"microcode": {"0": {"bad_pin": 1}}})


class IntegrationTests(unittest.TestCase):
    def test_32_bit_bus_testbench_does_not_mutate_live_circuit(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 32, "value": 0})
        probe = circuit.add("Bus Probe", params={"width": 32})
        circuit.connect_bus(source.id, "Q", probe.id, "D")
        bench = new_testbench("32-bit bus")
        bench["signals"] = [
            {"id": "drive", "role": "drive", "ref": signal_ref_dict(SignalRef.bus_port(source.id, "Q", "output"))},
            {"id": "result", "role": "observe", "ref": signal_ref_dict(SignalRef.bus_port(probe.id, "D", "input"))}]
        bench["steps"] = [
            {"drive": {"drive": 0xAABBCCDD}, "expect": {"result": 0xAABBCCDD}, "repeat": 1},
            {"drive": {"drive": 0x80000001}, "expect": {"result": 0x80000001}, "repeat": 1}]
        live_before = circuit.to_dict()
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual((result.passed, result.failed), (2, 0))
        self.assertEqual(circuit.to_dict(), live_before)
        self.assertEqual(integer(SignalRef.bus_port(probe.id, "D", "input").value(Simulator(circuit))), 0)

    def test_register_file_clock_testbench_and_project_round_trip(self):
        circuit = Circuit()
        rf = circuit.add("Register File", params={"registers": 4, "data_bits": 8})
        data = circuit.add("Bus Input", params={"width": 8, "value": 0})
        address = circuit.add("Bus Input", params={"width": 2, "value": 1})
        clk = driven_bit(circuit, 0, rf, "CLK")
        driven_bit(circuit, 1, rf, "WE")
        circuit.connect_bus(data.id, "Q", rf.id, "D")
        circuit.connect_bus(address.id, "Q", rf.id, "WA")
        circuit.connect_bus(address.id, "Q", rf.id, "RA0")
        restored = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
        bench = new_testbench("Register File write")
        bench["signals"] = [
            {"id": "data", "role": "drive", "ref": signal_ref_dict(SignalRef.bus_port(data.id, "Q", "output"))},
            {"id": "clock", "role": "drive", "ref": signal_ref_dict(SignalRef.component_pin(clk.id, "Q", "output"))},
            {"id": "out", "role": "observe", "ref": signal_ref_dict(SignalRef.bus_port(rf.id, "R0", "output"))}]
        bench["steps"] = [
            {"drive": {"data": 0x5A, "clock": 0}, "expect": {"out": 0}, "repeat": 1},
            {"drive": {"clock": 1}, "expect": {"out": 0x5A}, "repeat": 1}]
        result = TestbenchSession(restored, bench).run()
        self.assertEqual((result.passed, result.failed), (2, 0))
        self.assertEqual(restored.components[rf.id].state, {})

    def test_cpu_example_executes_and_reopens(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "cpu_8bit.json"
        circuit = Circuit.load(path)
        self.assertFalse(circuit.validate())
        simulator = Simulator(circuit)
        self.assertFalse(simulator.errors)
        find = lambda label: next(c for c in circuit.components.values() if c.params.get("label") == label)
        pc, ir, rf, ram = [find(label) for label in ("PC", "Instruction", "Registers", "Data RAM")]
        for _ in range(10): simulator.step()
        self.assertEqual(integer(bus(simulator, pc)), 5)
        self.assertEqual(integer(bus(simulator, ir)), 6)
        self.assertEqual(rf.state["words"]["2"], 1)
        self.assertEqual(ram.state["memory"]["2"], 8)
        simulator.step(); simulator.step()
        self.assertEqual(integer(bus(simulator, pc)), 0)
        reopened = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
        self.assertEqual(integer(bus(Simulator(reopened), reopened.components[ram.id])), 8)


if __name__ == "__main__":
    unittest.main()

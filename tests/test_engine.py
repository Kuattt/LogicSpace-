import json
import unittest

from engine import Circuit, Simulator, copy_selection


class SimulationTests(unittest.TestCase):
    def test_gate_propagation_and_fanout(self):
        c = Circuit()
        a = c.add("INPUT", params={"value": 1})
        b = c.add("INPUT", params={"value": 0})
        gate = c.add("AND")
        out1, out2 = c.add("OUTPUT"), c.add("OUTPUT")
        c.connect(a.id, "Q", gate.id, "A")
        c.connect(b.id, "Q", gate.id, "B")
        c.connect(gate.id, "Q", out1.id, "A")
        c.connect(gate.id, "Q", out2.id, "A")
        sim = Simulator(c)
        self.assertEqual(sim.inputs[out1.id]["A"], 0)
        self.assertEqual(sim.inputs[out2.id]["A"], 0)
        b.params["value"] = 1
        sim.evaluate()
        self.assertEqual(sim.outputs[gate.id, "Q"], 1)

    def test_unknown_and_decoder(self):
        c = Circuit()
        a = c.add("INPUT", params={"value": None})
        b = c.add("CONST", params={"value": 0})
        gate = c.add("AND")
        c.connect(a.id, "Q", gate.id, "A")
        c.connect(b.id, "Q", gate.id, "B")
        self.assertEqual(Simulator(c).outputs[gate.id, "Q"], 0)
        c.components[b.id].params["value"] = 1
        self.assertIsNone(Simulator(c).outputs[gate.id, "Q"])

    def test_clocked_flip_flop_and_reset(self):
        c = Circuit()
        clk = c.add("Clock Generator", params={"period": 2})
        data = c.add("CONST", params={"value": 1})
        flip = c.add("D Flip-Flop")
        c.connect(clk.id, "Q", flip.id, "CLK")
        c.connect(data.id, "Q", flip.id, "D")
        sim = Simulator(c)
        self.assertEqual(sim.outputs[flip.id, "Q"], 0)
        sim.step()
        sim.step()
        self.assertEqual(sim.outputs[flip.id, "Q"], 1)
        sim.reset()
        self.assertEqual(sim.outputs[flip.id, "Q"], 0)

    def test_feedback_reports_error_without_hanging(self):
        c = Circuit()
        a, b = c.add("NOT"), c.add("NOT")
        c.connect(a.id, "Q", b.id, "A")
        c.connect(b.id, "Q", a.id, "A")
        sim = Simulator(c)
        self.assertTrue(any("feedback loop" in error for error in sim.errors))
        self.assertIsNone(sim.outputs[a.id, "Q"])

    def test_connection_validation(self):
        c = Circuit()
        a, b, gate = c.add("INPUT"), c.add("INPUT"), c.add("OR")
        c.connect(a.id, "Q", gate.id, "A")
        with self.assertRaises(ValueError):
            c.connect(b.id, "Q", gate.id, "A")
        with self.assertRaises(ValueError):
            c.connect(gate.id, "A", a.id, "Q")

    def test_serialization_and_duplicate(self):
        c = Circuit()
        a, gate = c.add("INPUT", 10, 20), c.add("NOT", 100, 20)
        c.connect(a.id, "Q", gate.id, "A", [[50, 30]])
        created = copy_selection(c, [a.id, gate.id])
        self.assertEqual(len(created), 2)
        self.assertEqual(len(c.wires), 2)
        restored = Circuit.from_dict(json.loads(json.dumps(c.to_dict())))
        self.assertEqual(len(restored.components), 4)
        self.assertEqual(len(restored.wires), 2)
        self.assertEqual(restored.validate(), [])

    def test_custom_block_and_state(self):
        sub = Circuit()
        inp = sub.add("INPUT")
        inv = sub.add("NOT")
        out = sub.add("OUTPUT")
        sub.connect(inp.id, "Q", inv.id, "A")
        sub.connect(inv.id, "Q", out.id, "A")
        c = Circuit()
        c.blocks["Invert"] = {
            "inputs": ["IN"], "outputs": ["OUT"],
            "input_map": {"IN": inp.id}, "output_map": {"OUT": out.id},
            "circuit": sub.to_dict(),
        }
        source = c.add("CONST", params={"value": 1})
        block = c.add("BLOCK:Invert")
        c.connect(source.id, "Q", block.id, "IN")
        self.assertEqual(Simulator(c).outputs[block.id, "OUT"], 0)

    def test_rom_and_ram(self):
        c = Circuit()
        address = c.add("CONST", params={"value": 1})
        rom = c.add("ROM", params={"address_bits": 1, "data_bits": 2, "contents": {"1": 3}})
        c.connect(address.id, "Q", rom.id, "A0")
        sim = Simulator(c)
        self.assertEqual(sim.outputs[rom.id, "Q0"], 1)
        self.assertEqual(sim.outputs[rom.id, "Q1"], 1)

    def test_ram_write_and_nonvolatile_reset(self):
        c = Circuit()
        address = c.add("CONST", params={"value": 1})
        data = c.add("CONST", params={"value": 1})
        write = c.add("CONST", params={"value": 1})
        clock = c.add("INPUT", params={"value": 0})
        memory = c.add("EEPROM", params={"address_bits": 1, "data_bits": 1})
        for source, target_pin in ((address, "A0"), (data, "D0"), (write, "WE"), (clock, "CLK")):
            c.connect(source.id, "Q", memory.id, target_pin)
        sim = Simulator(c)
        sim.step()
        clock.params["value"] = 1
        sim.step()
        self.assertEqual(sim.outputs[memory.id, "Q0"], 1)
        sim.reset()
        self.assertEqual(memory.state["memory"]["1"], 1)

    def test_clock_divider_frequency(self):
        c = Circuit()
        clock = c.add("INPUT", params={"value": 0})
        divider = c.add("Clock Divider", params={"divide": 2})
        c.connect(clock.id, "Q", divider.id, "CLK")
        sim = Simulator(c)
        observed = []
        for value in (1, 0, 1, 0):
            clock.params["value"] = value
            sim.step()
            observed.append(sim.outputs[divider.id, "Q"])
        self.assertEqual(observed, [1, 1, 0, 0])

    def test_flash_program_and_erase(self):
        c = Circuit()
        address = c.add("CONST", params={"value": 0})
        data = c.add("INPUT", params={"value": 0})
        write = c.add("CONST", params={"value": 1})
        erase = c.add("INPUT", params={"value": 0})
        clock = c.add("INPUT", params={"value": 0})
        flash = c.add("Flash Memory", params={"address_bits": 1, "data_bits": 1})
        for source, target in ((address, "A0"), (data, "D0"), (write, "WE"), (erase, "ERASE"), (clock, "CLK")):
            c.connect(source.id, "Q", flash.id, target)
        sim = Simulator(c)
        clock.params["value"] = 1
        sim.step()
        self.assertEqual(sim.outputs[flash.id, "Q0"], 0)
        clock.params["value"] = 0
        data.params["value"] = 1
        sim.step()
        clock.params["value"] = 1
        sim.step()
        self.assertEqual(sim.outputs[flash.id, "Q0"], 0)
        clock.params["value"] = 0
        sim.step()
        erase.params["value"] = 1
        clock.params["value"] = 1
        sim.step()
        self.assertEqual(sim.outputs[flash.id, "Q0"], 1)

    def test_dram_retention(self):
        c = Circuit()
        address = c.add("INPUT", params={"value": 0})
        data = c.add("CONST", params={"value": 1})
        write = c.add("INPUT", params={"value": 1})
        refresh = c.add("INPUT", params={"value": 0})
        clock = c.add("INPUT", params={"value": 1})
        dram = c.add("DRAM", params={"address_bits": 1, "data_bits": 1, "retention_ticks": 1})
        for source, target in ((address, "A0"), (data, "D0"), (write, "WE"), (refresh, "REFRESH"), (clock, "CLK")):
            c.connect(source.id, "Q", dram.id, target)
        sim = Simulator(c)
        sim.step()
        self.assertEqual(sim.outputs[dram.id, "Q0"], 1)
        address.params["value"] = 1
        write.params["value"] = 0
        sim.step()
        sim.step()
        address.params["value"] = 0
        sim.step()
        self.assertIsNone(sim.outputs[dram.id, "Q0"])

    def test_displays_follow_digital_inputs(self):
        c = Circuit()
        red = c.add("INPUT", params={"value": 1})
        green = c.add("INPUT", params={"value": 0})
        blue = c.add("INPUT", params={"value": 1})
        displays = [c.add("RGB"), c.add("RGB Lamp")]
        for lamp in displays:
            for source, pin in ((red, "R"), (green, "G"), (blue, "B")):
                c.connect(source.id, "Q", lamp.id, pin)
        sim = Simulator(c)
        for lamp in displays:
            self.assertEqual(sim.inputs[lamp.id], {"R": 1, "G": 0, "B": 1})
        green.params["value"] = 1
        sim.evaluate()
        for lamp in displays:
            self.assertEqual(sim.inputs[lamp.id]["G"], 1)
        self.assertEqual(c.validate(), [])

    def test_configurable_four_bit_gate_and_io(self):
        c = Circuit()
        a = c.add("INPUT", params={"width": 4, "value": 0b1010})
        b = c.add("CONST", params={"width": 4, "value": 0b1100})
        gate = c.add("AND", params={"width": 4})
        display = c.add("OUTPUT", params={"width": 4})
        for i in range(4):
            c.connect(a.id, f"Q{i}", gate.id, f"A{i}")
            c.connect(b.id, f"Q{i}", gate.id, f"B{i}")
            c.connect(gate.id, f"Q{i}", display.id, f"A{i}")
        sim = Simulator(c)
        self.assertEqual([sim.outputs[gate.id, f"Q{i}"] for i in range(4)], [0, 0, 0, 1])
        self.assertEqual([sim.inputs[display.id][f"A{i}"] for i in range(4)], [0, 0, 0, 1])
        self.assertEqual(Circuit.from_dict(c.to_dict()).validate(), [])

    def test_configurable_comparator_and_mux(self):
        c = Circuit()
        a = c.add("INPUT", params={"width": 3, "value": 5})
        b = c.add("INPUT", params={"width": 3, "value": 3})
        select = c.add("INPUT", params={"value": 1})
        comparator = c.add("Comparator", params={"width": 3})
        mux = c.add("Multiplexer", params={"width": 3})
        for i in range(3):
            for target in (comparator, mux):
                c.connect(a.id, f"Q{i}", target.id, f"A{i}")
                c.connect(b.id, f"Q{i}", target.id, f"B{i}")
        c.connect(select.id, "Q", mux.id, "SEL")
        sim = Simulator(c)
        self.assertEqual([sim.outputs[comparator.id, p] for p in ("LT", "EQ", "GT")], [0, 0, 1])
        self.assertEqual([sim.outputs[mux.id, f"Q{i}"] for i in range(3)], [1, 1, 0])

    def test_configurable_demultiplexer(self):
        c = Circuit()
        source = c.add("INPUT", params={"width": 2, "value": 0b10})
        select = c.add("INPUT", params={"value": 1})
        demux = c.add("Demultiplexer", params={"width": 2})
        for i in range(2):
            c.connect(source.id, f"Q{i}", demux.id, f"A{i}")
        c.connect(select.id, "Q", demux.id, "SEL")
        sim = Simulator(c)
        self.assertEqual([sim.outputs[demux.id, f"Q0_{i}"] for i in range(2)], [0, 0])
        self.assertEqual([sim.outputs[demux.id, f"Q1_{i}"] for i in range(2)], [0, 1])

    def test_reusable_block_with_multibit_terminals(self):
        sub = Circuit()
        terminal_in = sub.add("INPUT", params={"width": 2})
        inverter = sub.add("NOT", params={"width": 2})
        terminal_out = sub.add("OUTPUT", params={"width": 2})
        for i in range(2):
            sub.connect(terminal_in.id, f"Q{i}", inverter.id, f"A{i}")
            sub.connect(inverter.id, f"Q{i}", terminal_out.id, f"A{i}")
        c = Circuit()
        c.blocks["Invert2"] = {
            "inputs": ["IN0", "IN1"], "outputs": ["OUT0", "OUT1"],
            "input_map": {f"IN{i}": [terminal_in.id, f"Q{i}"] for i in range(2)},
            "output_map": {f"OUT{i}": [terminal_out.id, f"A{i}"] for i in range(2)},
            "circuit": sub.to_dict(),
        }
        source = c.add("INPUT", params={"width": 2, "value": 1})
        block = c.add("BLOCK:Invert2")
        for i in range(2):
            c.connect(source.id, f"Q{i}", block.id, f"IN{i}")
        sim = Simulator(c)
        self.assertEqual([sim.outputs[block.id, f"OUT{i}"] for i in range(2)], [0, 1])


if __name__ == "__main__":
    unittest.main()

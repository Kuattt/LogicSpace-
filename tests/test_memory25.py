"""Explicit RAM/ROM timing modes preserve legacy projects and Time Travel."""
import unittest

from engine import Circuit, Simulator
from time_travel_model import SimulationHistory
from memory_model import (export_memory_image, load_memory_image, memory_changes,
                          memory_word, set_memory_word)


def ram_circuit(mode="sync", policy="new", initial=None, read_enable=False):
    circuit = Circuit()
    address = circuit.add("Bus Input", params={"width": 2, "value": 1})
    data = circuit.add("Bus Input", params={"width": 2, "value": 3})
    we = circuit.add("INPUT", params={"value": 0})
    clk = circuit.add("INPUT", params={"value": 0})
    settings = {"address_bits": 2, "data_bits": 2, "read_mode": mode,
                "read_during_write": policy, "init": initial or {"1": 2},
                "read_enable": read_enable}
    ram = circuit.add("RAM", params=settings)
    circuit.connect_bus(address.id, "Q", ram.id, "A")
    circuit.connect_bus(data.id, "Q", ram.id, "D")
    circuit.connect(we.id, "Q", ram.id, "WE")
    circuit.connect(clk.id, "Q", ram.id, "CLK")
    re = None
    if read_enable:
        re = circuit.add("INPUT", params={"value": 1})
        circuit.connect(re.id, "Q", ram.id, "RE")
    return circuit, Simulator(circuit), ram, address, data, we, clk, re


def output(sim, component, width=2):
    bits = [sim.outputs.get((component.id, f"Q{i}")) for i in range(width)]
    return None if None in bits else sum(bit << index for index, bit in enumerate(bits))


class MemoryModes(unittest.TestCase):
    def test_inspector_image_round_trip_and_history(self):
        circuit, sim, ram, *_ = ram_circuit("async")
        history = SimulationHistory(sim)
        set_memory_word(ram, 2, 3)
        sim.evaluate(); history.record_mutation(sim)
        self.assertEqual(memory_word(ram, 2), 3)
        self.assertEqual(memory_changes(history, ram.id)[-1]["address"], 2)
        binary = export_memory_image(ram, "bin")
        self.assertEqual(binary[2], 3)
        hex_text = export_memory_image(ram, "hex")
        other = Circuit().add("RAM", params={"address_bits": 2, "data_bits": 2, "read_mode": "async"})
        self.assertEqual(load_memory_image(other, hex_text, "hex"), 4)
        self.assertEqual(memory_word(other, 2), 3)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            load_memory_image(other, bytes([0] * 5), "bin")

    def test_unknown_write_control_and_address_propagate_x(self):
        _, sim, ram, address, _, we, clk, _ = ram_circuit("async")
        we.params["value"] = None
        clk.params["value"] = 1
        sim.evaluate(); sim.step()
        self.assertIsNone(ram.state["memory"]["1"])
        self.assertIsNone(output(sim, ram))
        clk.params["value"] = 0; we.params["value"] = 1
        address.params["value"] = None
        sim.evaluate(); sim.step()
        clk.params["value"] = 1; sim.evaluate(); sim.step()
        self.assertTrue(all(ram.state["memory"].get(str(index)) is None for index in range(4)))

    def test_async_read_and_initialization(self):
        _, sim, ram, address, _, _, _, _ = ram_circuit("async")
        self.assertEqual(output(sim, ram), 2)
        address.params["value"] = 0; sim.evaluate()
        self.assertEqual(output(sim, ram), 0)

    def test_sync_read_only_updates_on_edge(self):
        _, sim, ram, address, _, _, clk, _ = ram_circuit("sync")
        self.assertIsNone(output(sim, ram))
        sim.step(); self.assertIsNone(output(sim, ram))
        clk.params["value"] = 1; sim.evaluate(); sim.step()
        self.assertEqual(output(sim, ram), 2)
        address.params["value"] = 0; sim.evaluate()
        self.assertEqual(output(sim, ram), 2)

    def test_read_during_write_policies(self):
        for policy, expected in (("new", 3), ("old", 2), ("no_change", None)):
            with self.subTest(policy=policy):
                _, sim, ram, _, _, we, clk, _ = ram_circuit("sync", policy)
                we.params["value"] = clk.params["value"] = 1
                sim.evaluate(); sim.step()
                self.assertEqual(ram.state["memory"]["1"], 3)
                self.assertEqual(output(sim, ram), expected)

    def test_read_enable_hold_and_async_x(self):
        _, sim, ram, _, _, _, clk, re = ram_circuit("sync", read_enable=True)
        clk.params["value"] = 1; sim.evaluate(); sim.step()
        self.assertEqual(output(sim, ram), 2)
        re.params["value"] = 0; clk.params["value"] = 0; sim.evaluate(); sim.step()
        clk.params["value"] = 1; sim.evaluate(); sim.step()
        self.assertEqual(output(sim, ram), 2)
        _, sim, ram, _, _, _, _, re = ram_circuit("async", read_enable=True)
        re.params["value"] = 0; sim.evaluate()
        self.assertIsNone(output(sim, ram))

    def test_sync_rom(self):
        circuit = Circuit()
        address = circuit.add("Bus Input", params={"width": 2, "value": 1})
        clock = circuit.add("INPUT", params={"value": 0})
        rom = circuit.add("ROM", params={"address_bits": 2, "data_bits": 2,
                                          "read_mode": "sync", "contents": {"1": 3}})
        circuit.connect_bus(address.id, "Q", rom.id, "A")
        circuit.connect(clock.id, "Q", rom.id, "CLK")
        sim = Simulator(circuit)
        self.assertIsNone(output(sim, rom))
        clock.params["value"] = 1; sim.evaluate(); sim.step()
        self.assertEqual(output(sim, rom), 3)
        address.params["value"] = 2; sim.evaluate()
        self.assertEqual(output(sim, rom), 3)

    def test_invalid_address_and_configuration(self):
        circuit = Circuit()
        with self.assertRaisesRegex(ValueError, "init"):
            circuit.add("RAM", params={"address_bits": 2, "depth": 2, "init": {"2": 1}})
        with self.assertRaisesRegex(ValueError, "asynchronous reads always"):
            circuit.add("RAM", params={"read_mode": "async", "read_during_write": "old"})
        _, sim, ram, address, _, _, _, _ = ram_circuit("async")
        ram.params["depth"] = 2
        address.params["value"] = 3; sim.evaluate()
        self.assertIsNone(output(sim, ram))
        self.assertTrue(any("outside" in warning for warning in sim.warnings))

    def test_memory_state_time_travel(self):
        circuit, sim, ram, _, _, we, clk, _ = ram_circuit("sync")
        history = SimulationHistory(sim)
        we.params["value"] = clk.params["value"] = 1
        sim.evaluate(); sim.step(); history.record(sim)
        self.assertEqual(ram.state["memory"]["1"], 3)
        history.navigate(sim, 0)
        self.assertNotIn("1", ram.state.get("memory", {}))
        self.assertEqual(circuit.tick, 0)

    def test_legacy_default_project_semantics(self):
        circuit, sim, ram, *_ = ram_circuit("legacy")
        self.assertIsNone(output(sim, ram))
        sim.step()
        self.assertEqual(output(sim, ram), 2)
        self.assertEqual(Circuit.from_dict(circuit.to_dict()).validate(), [])


if __name__ == "__main__": unittest.main()

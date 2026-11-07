"""RAM/ROM watchpoints observe actual component memory and Time Travel navigation."""
import unittest

from breakpoints import BreakpointManager
from engine import Circuit, Simulator
from memory_model import set_memory_word
from time_travel_model import SimulationHistory


class MemoryWatchTests(unittest.TestCase):
    def test_ram_write_and_rewind_rearm(self):
        circuit = Circuit()
        ram = circuit.add("RAM", params={"address_bits": 2, "data_bits": 2, "depth": 4})
        address = circuit.add("CONST", params={"width": 2, "value": 1})
        data = circuit.add("CONST", params={"width": 2, "value": 3})
        enable = circuit.add("CONST", params={"value": 1})
        clock = circuit.add("INPUT", params={"value": 0})
        circuit.connect_bus(address.id, "Q", ram.id, "A")
        circuit.connect_bus(data.id, "Q", ram.id, "D")
        circuit.connect(enable.id, "Q", ram.id, "WE")
        circuit.connect(clock.id, "Q", ram.id, "CLK")
        simulator = Simulator(circuit)
        history = SimulationHistory(simulator)
        manager = BreakpointManager()
        item = manager.add_memory_watch(ram.id, 1, simulator)
        simulator.step(); history.record(simulator)
        self.assertEqual(manager.check(simulator), [])
        clock.params["value"] = 1
        simulator.step(); history.record(simulator)
        events = manager.check(simulator)
        self.assertEqual((events[0].before, events[0].after), (0, 3))
        self.assertEqual(circuit.components[ram.id].state["memory"]["1"], 3)
        history.navigate(simulator, 0)
        manager.arm(simulator)
        self.assertEqual(manager.check(simulator), [])
        history.navigate(simulator, 2)
        self.assertEqual(manager.check(simulator)[0].after, 3)
        circuit.remove(ram.id)
        self.assertEqual(manager.remove_invalid(circuit), [item.id])

    def test_rom_inspector_mutation_is_visible(self):
        circuit = Circuit()
        rom = circuit.add("ROM", params={"address_bits": 2, "data_bits": 8, "depth": 4})
        simulator = Simulator(circuit)
        manager = BreakpointManager()
        manager.add_memory_watch(rom.id, 2, simulator)
        set_memory_word(rom, 2, 0x7F)
        simulator.evaluate()
        event = manager.check(simulator)[0]
        self.assertEqual((event.before, event.after), (0, 0x7F))


if __name__ == "__main__": unittest.main()

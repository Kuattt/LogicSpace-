"""Logic analyzer and breakpoints observe the existing simulator's steps."""
import csv
import tempfile
import unittest
from pathlib import Path

from breakpoints import BreakpointManager
from engine import Circuit, Simulator
from logic_analyzer_model import LogicAnalyzer, format_value
from time_travel_model import SimulationHistory
from timing_model import SignalRef, TimingHistory


class LogicAnalyzerTests(unittest.TestCase):
    def capture(self):
        circuit = Circuit()
        clock = circuit.add("INPUT", params={"value": 0})
        data = circuit.add("Bus Input", params={"width": 16, "value": 0})
        simulator = Simulator(circuit)
        clock_ref = SignalRef.component_pin(clock.id, "Q", "output")
        data_ref = SignalRef.bus_port(data.id, "Q", "output")
        history = TimingHistory(limit=10)
        history.add(clock_ref, simulator)
        history.add(data_ref, simulator)
        for clock_value, data_value in ((1, 0), (1, 1), (0, 1), (0, 2),
                                        (1, 2), (0, 2), (1, 3), (0, 3)):
            clock.params["value"] = clock_value
            data.params["value"] = data_value
            simulator.step()
            history.record_step(simulator)
        return history, clock_ref, data_ref

    def test_edges_pulses_periods_and_cycle_comparison(self):
        history, clock, data = self.capture()
        analyzer = LogicAnalyzer(history)
        self.assertEqual([e.step for e in analyzer.find(clock, "rising")], [1, 5, 7])
        self.assertEqual([e.step for e in analyzer.find(clock, "falling")], [3, 6, 8])
        self.assertEqual(analyzer.pulse_widths(clock), [(1, 3, 2), (5, 6, 1), (7, 8, 1)])
        self.assertEqual(analyzer.clock_periods(clock), [(1, 5, 4), (5, 7, 2)])
        self.assertEqual((analyzer.clock_cycles(clock)[0].high_steps,
                          analyzer.clock_cycles(clock)[0].low_steps), (2, 2))
        self.assertTrue(analyzer.compare_cycles(clock, (data,), 0, 1))
        self.assertEqual(analyzer.observed_transition_offset(clock, data, 1), 1)
        self.assertEqual(analyzer.setup_hold_spacings(clock, data)[1]["before_steps"], 1)

    def test_bus_radix_csv_unknown_and_bounded_capture(self):
        history, clock, data = self.capture()
        analyzer = LogicAnalyzer(history)
        self.assertEqual(format_value(history.value_at(data, 8), "hex"), "0x0003")
        self.assertEqual(format_value(history.value_at(data, 8), "decimal"), "3")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "capture.csv"
            self.assertEqual(analyzer.export_csv(path, (clock, data), start=7, end=8,
                                                 radix="hex"), 2)
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1][0], "7")
            self.assertEqual(rows[2][2], "0x0003")
        history.set_limit(4)  # The shared history enforces its minimum of ten.
        self.assertEqual(history.limit, 10)
        with self.assertRaisesRegex(ValueError, "outside retained"):
            analyzer.find(clock, start=11, end=12)
        self.assertEqual(format_value((None, 1, 0), "hex"), "X (01X)")


class BreakpointTests(unittest.TestCase):
    def test_edges_change_bus_condition_and_time_travel(self):
        circuit = Circuit()
        source = circuit.add("INPUT", params={"value": 0})
        bus = circuit.add("Bus Input", params={"width": 32, "value": 0})
        simulator = Simulator(circuit)
        history = SimulationHistory(simulator)
        manager = BreakpointManager(limit=10)
        bit = SignalRef.component_pin(source.id, "Q", "output")
        word = SignalRef.bus_port(bus.id, "Q", "output")
        manager.add(bit, "rising", simulator)
        manager.add(bit, "falling", simulator)
        manager.add(word, "equals", simulator, 0x80000000)
        source.params["value"] = 1
        bus.params["value"] = 0x80000000
        simulator.step(); history.record(simulator)
        self.assertEqual([event.reason for event in manager.check(simulator)], ["rising", "equals"])
        source.params["value"] = 0
        simulator.step(); history.record(simulator)
        self.assertIn("falling", [event.reason for event in manager.check(simulator)])
        history.navigate(simulator, 1)
        self.assertEqual(bit.value(simulator), 1)
        manager.arm(simulator)
        self.assertEqual(manager.check(simulator)[0].reason, "equals")

    def test_unknown_and_conflict_and_invalid_reference(self):
        circuit = Circuit()
        source = circuit.add("INPUT", params={"value": 0})
        simulator = Simulator(circuit)
        manager = BreakpointManager()
        ref = SignalRef.component_pin(source.id, "Q", "output")
        manager.add(ref, "unknown", simulator)
        manager.add_conflict(simulator)
        source.params["value"] = None
        simulator.step()
        self.assertIn("unknown", [event.reason for event in manager.check(simulator)])
        simulator.warnings.append("multiple drivers")
        self.assertIn("multiple drivers", [event.reason for event in manager.check(simulator)])
        circuit.components.pop(source.id)
        self.assertEqual(len(manager.remove_invalid(circuit)), 1)


if __name__ == "__main__":
    unittest.main()

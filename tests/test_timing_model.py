"""Timing capture tests using the application's real circuit simulator."""
import unittest

from engine import Circuit, Simulator
from timing_model import MISSING, SignalRef, TimingHistory


class TimingHistoryTests(unittest.TestCase):
    def setUp(self):
        self.circuit = Circuit()
        self.source = self.circuit.add("INPUT", params={"value": 0})
        self.sim = Simulator(self.circuit)
        self.ref = SignalRef.component_pin(self.source.id, "Q", "output")
        self.history = TimingHistory()
        self.history.add(self.ref, self.sim)

    def step_with(self, value):
        self.source.params["value"] = value
        self.sim.step()
        self.history.record_step(self.sim)

    def test_low_high_low_and_event_order(self):
        self.step_with(1)
        self.step_with(0)
        self.assertEqual(list(self.history.tracks[self.ref].events), [(0, 0), (1, 1), (2, 0)])
        self.assertEqual([self.history.value_at(self.ref, i) for i in range(3)], [0, 1, 0])

    def test_unchanged_values_do_not_duplicate_events(self):
        for _ in range(4):
            self.step_with(0)
        self.assertEqual(list(self.history.tracks[self.ref].events), [(0, 0)])
        self.assertEqual(self.history.last_step, 4)

    def test_multiple_signals_input_pin_and_wire(self):
        target = self.circuit.add("OUTPUT")
        wire = self.circuit.connect(self.source.id, "Q", target.id, "A")
        self.sim.evaluate()
        input_ref = SignalRef.component_pin(target.id, "A", "input")
        wire_ref = SignalRef.wire(wire.id)
        for ref in (input_ref, wire_ref):
            self.history.add(ref, self.sim)
        self.step_with(1)
        for ref in (self.ref, input_ref, wire_ref):
            self.assertEqual(self.history.value_at(ref, 1), 1)

    def test_unknown_state(self):
        self.step_with(None)
        self.assertIsNone(self.history.value_at(self.ref, 1))
        self.assertEqual(list(self.history.tracks[self.ref].events), [(0, 0), (1, None)])

    def test_reset_clears_history_and_restarts_axis(self):
        self.step_with(1)
        self.sim.reset()
        self.history.clear_history(self.sim)
        self.assertEqual(list(self.history.steps), [0])
        self.assertEqual(list(self.history.tracks[self.ref].events), [(0, 1)])

    def test_limit_retains_correct_oldest_value(self):
        self.history.set_limit(10)
        for i in range(20):
            self.step_with(i % 2)
        self.assertEqual(len(self.history.steps), 10)
        self.assertEqual(self.history.first_step, 11)
        for step in self.history.steps:
            self.assertEqual(self.history.value_at(self.ref, step), (step - 1) % 2)

    def test_remove_and_clear_release_history(self):
        self.step_with(1)
        self.assertTrue(self.history.remove(self.ref))
        self.assertIs(self.history.value_at(self.ref, 1), MISSING)
        self.history.clear_signals()
        self.assertEqual(len(self.history.steps), 0)

    def test_multibit_pins_are_independent(self):
        bus = self.circuit.add("INPUT", params={"width": 4, "value": 0})
        self.sim.evaluate()
        refs = [SignalRef.component_pin(bus.id, f"Q{i}", "output") for i in range(4)]
        for ref in refs:
            self.history.add(ref, self.sim)
        bus.params["value"] = 0b1010
        self.sim.step()
        self.history.record_step(self.sim)
        self.assertEqual([self.history.value_at(ref, 1) for ref in refs], [0, 1, 0, 1])

    def test_new_signal_has_no_fabricated_past(self):
        for _ in range(3):
            self.step_with(0)
        second = self.circuit.add("INPUT", params={"value": 1})
        self.sim.evaluate()
        ref = SignalRef.component_pin(second.id, "Q", "output")
        self.history.add(ref, self.sim)
        self.assertIs(self.history.value_at(ref, 2), MISSING)
        self.assertEqual(self.history.value_at(ref, 3), 1)

    def test_clock_flip_flop_and_led_match_simulator(self):
        c = Circuit()
        clock = c.add("Clock Generator", params={"period": 2})
        data = c.add("CONST", params={"value": 1})
        flip = c.add("D Flip-Flop")
        led = c.add("LED")
        c.connect(clock.id, "Q", flip.id, "CLK")
        c.connect(data.id, "Q", flip.id, "D")
        c.connect(flip.id, "Q", led.id, "A")
        sim = Simulator(c)
        history = TimingHistory()
        refs = [SignalRef.component_pin(clock.id, "Q", "output"),
                SignalRef.component_pin(flip.id, "Q", "output"),
                SignalRef.component_pin(led.id, "A", "input")]
        for ref in refs:
            history.add(ref, sim)
        for step in range(1, 7):
            sim.step()
            history.record_step(sim)
            self.assertEqual([history.value_at(ref, step) for ref in refs],
                             [ref.value(sim) for ref in refs])
        self.assertEqual([history.value_at(refs[0], i) for i in range(7)], [0, 1, 0, 1, 0, 1, 0])
        self.assertEqual([history.value_at(refs[1], i) for i in range(7)], [0, 0, 1, 1, 1, 1, 1])

    def test_counter_and_register_outputs(self):
        c = Circuit()
        clock = c.add("Clock Generator", params={"period": 2})
        data = c.add("CONST", params={"width": 3, "value": 0b101})
        counter = c.add("Binary Counter", params={"width": 3})
        register = c.add("Register", params={"width": 3})
        c.connect(clock.id, "Q", counter.id, "CLK")
        c.connect(clock.id, "Q", register.id, "CLK")
        for i in range(3):
            c.connect(data.id, f"Q{i}", register.id, f"D{i}")
        sim = Simulator(c)
        history = TimingHistory()
        refs = [SignalRef.component_pin(part.id, f"Q{i}", "output")
                for part in (counter, register) for i in range(3)]
        for ref in refs:
            history.add(ref, sim)
        for step in range(1, 6):
            sim.step()
            history.record_step(sim)
            self.assertEqual([history.value_at(ref, step) for ref in refs], [ref.value(sim) for ref in refs])
        self.assertEqual([history.value_at(ref, 2) for ref in refs[:3]], [1, 0, 0])
        self.assertEqual([history.value_at(ref, 2) for ref in refs[3:]], [1, 0, 1])


if __name__ == "__main__":
    unittest.main()

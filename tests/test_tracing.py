import os
import sys
import unittest
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication

from component_library import block_definition_from_circuit
from engine import Circuit, Simulator, Wire
from main import Editor
from timing_model import SignalRef
from tracing_model import TraceAnalyzer, TraceFrame, TraceHistory


def ref(component, pin="Q", direction="output"):
    return SignalRef.component_pin(component.id, pin, direction)


def lines(analyzer, signal):
    return "\n".join(analyzer.explain(signal))


def flatten(node):
    return [node.text] + [text for child in node.children for text in flatten(child)]


class TracingModelTests(unittest.TestCase):
    def analyzer(self, circuit, simulator=None, frame=None, historical=False):
        simulator = simulator or Simulator(circuit)
        return TraceAnalyzer(circuit, frame or TraceFrame.from_simulator(simulator), simulator,
                             historical=historical)

    def test_and_backward_and_multiple_input_dependencies(self):
        circuit = Circuit()
        a = circuit.add("INPUT", params={"value": 1})
        b = circuit.add("INPUT", params={"value": 1})
        gate = circuit.add("AND")
        w1 = circuit.connect(a.id, "Q", gate.id, "A")
        w2 = circuit.connect(b.id, "Q", gate.id, "B")
        analyzer = self.analyzer(circuit)
        tree = analyzer.backward(ref(gate))
        text = "\n".join(flatten(tree))
        self.assertIn("AND.Q = 1", text)
        self.assertIn("INPUT.Q = 1", text)
        self.assertEqual(analyzer.connected_wires, {w1.id, w2.id})
        self.assertEqual(analyzer.active_wires, {w1.id, w2.id})
        self.assertEqual(analyzer.input_influence(gate.id, "Q"), {"A": "influences", "B": "influences"})

    def test_or_forward_fanout_and_disconnected_pin(self):
        circuit = Circuit()
        source = circuit.add("INPUT", params={"value": 1})
        gate = circuit.add("OR")
        left, right = circuit.add("LED"), circuit.add("LED")
        circuit.connect(source.id, "Q", gate.id, "A")
        w1 = circuit.connect(gate.id, "Q", left.id, "A")
        w2 = circuit.connect(gate.id, "Q", right.id, "A")
        analyzer = self.analyzer(circuit)
        tree = analyzer.forward(ref(gate))
        self.assertEqual(analyzer.connected_wires, {w1.id, w2.id})
        self.assertEqual(len(tree.children), 2)
        self.assertIn("Unconnected input", "\n".join(flatten(analyzer.backward(ref(gate, "B", "input")))))

    def test_not_and_and_controlling_zero(self):
        circuit = Circuit()
        a = circuit.add("INPUT", params={"value": 0})
        b = circuit.add("INPUT", params={"value": 1})
        gate = circuit.add("AND")
        inv = circuit.add("NOT")
        circuit.connect(a.id, "Q", gate.id, "A")
        circuit.connect(b.id, "Q", gate.id, "B")
        circuit.connect(gate.id, "Q", inv.id, "A")
        analyzer = self.analyzer(circuit)
        explanation = lines(analyzer, ref(gate))
        self.assertIn("AND.Q = 0", explanation)
        self.assertIn("A=0 influences", explanation)
        self.assertIn("B=1 is connected but changing it alone leaves this output unchanged", explanation)
        self.assertIn("NOT.Q = 1", lines(analyzer, ref(inv)))
        self.assertIn("A=0 influences", lines(analyzer, ref(inv)))

    def test_two_controlling_inputs_are_both_sufficient(self):
        circuit = Circuit()
        a = circuit.add("INPUT", params={"value": 0})
        b = circuit.add("INPUT", params={"value": 0})
        gate = circuit.add("AND")
        circuit.connect(a.id, "Q", gate.id, "A")
        circuit.connect(b.id, "Q", gate.id, "B")
        analyzer = self.analyzer(circuit)
        self.assertEqual(analyzer.input_influence(gate.id, "Q"), {"A": "sufficient", "B": "sufficient"})
        explanation = lines(analyzer, ref(gate))
        self.assertIn("A=0 is sufficient", explanation)
        self.assertIn("B=0 is sufficient", explanation)

    def test_forward_marks_connected_but_inactive_branch(self):
        circuit = Circuit()
        zero = circuit.add("INPUT", params={"value": 0})
        one = circuit.add("INPUT", params={"value": 1})
        gate = circuit.add("AND")
        lamp = circuit.add("LED")
        circuit.connect(zero.id, "Q", gate.id, "A")
        circuit.connect(one.id, "Q", gate.id, "B")
        downstream = circuit.connect(gate.id, "Q", lamp.id, "A")
        analyzer = self.analyzer(circuit)
        analyzer.forward(ref(one))
        self.assertIn(downstream.id, analyzer.connected_wires)
        self.assertNotIn(downstream.id, analyzer.active_wires)

    def test_unknown_and_feedback_cycle(self):
        circuit = Circuit()
        source = circuit.add("INPUT", params={"value": None})
        inv = circuit.add("NOT")
        circuit.connect(source.id, "Q", inv.id, "A")
        analyzer = self.analyzer(circuit)
        self.assertIn("NOT.Q = X", lines(analyzer, ref(inv)))
        self.assertIn("A=X may determine", lines(analyzer, ref(inv)))
        cycle = Circuit()
        first, second = cycle.add("NOT"), cycle.add("NOT")
        cycle.connect(first.id, "Q", second.id, "A")
        cycle.connect(second.id, "Q", first.id, "A")
        simulator = Simulator(cycle)
        self.assertTrue(any("feedback loop" in error for error in simulator.errors))
        analyzer = self.analyzer(cycle, simulator)
        self.assertIn("Cycle already visited", "\n".join(flatten(analyzer.backward(ref(first)))))
        self.assertIn("NOT.Q = X", lines(analyzer, ref(first)))

    def test_unknown_other_input_does_not_claim_independence(self):
        circuit = Circuit()
        a = circuit.add("INPUT", params={"value": 0})
        b = circuit.add("INPUT", params={"value": None})
        gate = circuit.add("XOR")
        circuit.connect(a.id, "Q", gate.id, "A")
        circuit.connect(b.id, "Q", gate.id, "B")
        analyzer = self.analyzer(circuit)
        self.assertEqual(analyzer.input_influence(gate.id, "Q")["A"], "indeterminate")
        self.assertIn("cannot be determined", lines(analyzer, ref(gate)))

    def test_invalid_multiple_driver_does_not_claim_causation(self):
        circuit = Circuit()
        a, b, gate = circuit.add("INPUT"), circuit.add("INPUT"), circuit.add("AND")
        circuit.connect(a.id, "Q", gate.id, "A")
        circuit.wires["extra"] = Wire("extra", b.id, "Q", gate.id, "A")
        simulator = Simulator(circuit)
        explanation = lines(self.analyzer(circuit, simulator), ref(gate))
        self.assertIn("circuit wiring is invalid", explanation)
        self.assertIn("multiple drivers", explanation)

    def test_d_flip_flop_rising_edge_and_hold(self):
        circuit = Circuit()
        data = circuit.add("INPUT", params={"value": 1})
        clock = circuit.add("INPUT", params={"value": 0})
        ff = circuit.add("D Flip-Flop")
        circuit.connect(data.id, "Q", ff.id, "D")
        circuit.connect(clock.id, "Q", ff.id, "CLK")
        simulator = Simulator(circuit)
        clock.params["value"] = 1
        simulator.step()
        analyzer = self.analyzer(circuit, simulator)
        explanation = lines(analyzer, ref(ff))
        self.assertIn("rising clock edge", explanation)
        self.assertIn("D was sampled as 1", explanation)
        self.assertIn("Q changed 0→1", explanation)
        path = "\n".join(flatten(analyzer.backward(ref(ff))))
        self.assertIn("D Flip-Flop.D = 1", path)
        self.assertIn("D Flip-Flop.CLK = 1", path)
        simulator.step()
        held = lines(self.analyzer(circuit, simulator), ref(ff))
        self.assertIn("No rising clock edge", held)
        self.assertIn("Q = 1", held)

    def test_historical_flip_flop_event_and_simulation_reset(self):
        circuit = Circuit()
        data = circuit.add("INPUT", params={"value": 1})
        clock = circuit.add("INPUT", params={"value": 0})
        ff = circuit.add("D Flip-Flop")
        circuit.connect(data.id, "Q", ff.id, "D")
        circuit.connect(clock.id, "Q", ff.id, "CLK")
        simulator = Simulator(circuit)
        history = TraceHistory()
        history.record(simulator)
        clock.params["value"] = 1
        simulator.step(); history.record(simulator)
        clock.params["value"] = 0
        simulator.step(); history.record(simulator)
        old = self.analyzer(circuit, simulator, history.at(1), historical=True)
        self.assertIn("D was sampled as 1", lines(old, ref(ff)))
        self.assertIn("Q changed 0→1", lines(old, ref(ff)))
        simulator.reset()
        self.assertIn("Simulation reset cleared the stored state", lines(self.analyzer(circuit, simulator), ref(ff)))
        self.assertIn("D Flip-Flop.Q = 0", lines(self.analyzer(circuit, simulator), ref(ff)))

    def test_sampled_clock_is_not_confused_with_post_step_clock(self):
        circuit = Circuit()
        data = circuit.add("INPUT", params={"value": 1})
        clock = circuit.add("Clock Generator", params={"period": 2})
        ff = circuit.add("D Flip-Flop")
        circuit.connect(data.id, "Q", ff.id, "D")
        circuit.connect(clock.id, "Q", ff.id, "CLK")
        simulator = Simulator(circuit)
        simulator.step(); simulator.step()
        analyzer = self.analyzer(circuit, simulator)
        self.assertIn("rising clock edge", lines(analyzer, ref(ff)))
        path = "\n".join(flatten(analyzer.backward(ref(ff))))
        self.assertIn("sampled 1", path)
        self.assertIn("Current input differs from the sampled event", path)

    def test_register_counter_and_reset_events(self):
        circuit = Circuit()
        d0 = circuit.add("INPUT", params={"value": 1})
        d1 = circuit.add("INPUT", params={"value": 0})
        clk = circuit.add("INPUT", params={"value": 0})
        reset = circuit.add("INPUT", params={"value": 0})
        register = circuit.add("Register", params={"width": 2})
        counter = circuit.add("Binary Counter", params={"width": 2})
        for source, target, pin in ((d0, register, "D0"), (d1, register, "D1"),
                                    (clk, register, "CLK"), (clk, counter, "CLK"),
                                    (reset, counter, "RESET")):
            circuit.connect(source.id, "Q", target.id, pin)
        simulator = Simulator(circuit)
        clk.params["value"] = 1
        simulator.step()
        analyzer = self.analyzer(circuit, simulator)
        self.assertIn("D bits sampled: 01", lines(analyzer, ref(register, "Q0")))
        self.assertIn("stored value changed 0→1", lines(analyzer, ref(register, "Q0")))
        self.assertIn("Stored count changed 0→1", lines(analyzer, ref(counter, "Q0")))
        reset.params["value"] = 1
        simulator.step()
        reset_explanation = lines(self.analyzer(circuit, simulator), ref(counter, "Q0"))
        self.assertIn("RESET was sampled at 1", reset_explanation)
        self.assertIn("Stored count changed 1→0", reset_explanation)

    def test_historical_values_and_expiration(self):
        circuit = Circuit()
        source = circuit.add("INPUT", params={"value": 0})
        inv = circuit.add("NOT")
        circuit.connect(source.id, "Q", inv.id, "A")
        simulator = Simulator(circuit)
        history = TraceHistory(10)
        history.record(simulator)
        source.params["value"] = 1
        simulator.step()
        history.record(simulator)
        old = self.analyzer(circuit, simulator, history.at(0), historical=True)
        self.assertIn("NOT.Q = 1", lines(old, ref(inv)))
        self.assertIn("A=0 influences", lines(old, ref(inv)))
        self.assertIn("NOT.Q = 0", lines(self.analyzer(circuit, simulator, history.at(1), True), ref(inv)))
        for _ in range(12):
            simulator.step(); history.record(simulator)
        self.assertIsNone(history.at(0))
        self.assertEqual(len(history.frames), 10)

    def test_nested_block_and_state_preservation(self):
        inner = Circuit()
        terminal_in = inner.add("INPUT", params={"label": "A"})
        inv = inner.add("NOT")
        terminal_out = inner.add("OUTPUT", params={"label": "Y"})
        inner.connect(terminal_in.id, "Q", inv.id, "A")
        inner.connect(inv.id, "Q", terminal_out.id, "A")
        circuit = Circuit()
        circuit.blocks["Invert"] = block_definition_from_circuit(inner)
        source = circuit.add("INPUT", params={"value": 0})
        block = circuit.add("BLOCK:Invert")
        lamp = circuit.add("LED")
        circuit.connect(source.id, "Q", block.id, "A")
        circuit.connect(block.id, "Y", lamp.id, "A")
        simulator = Simulator(circuit)
        before = deepcopy(circuit.to_dict())
        analyzer = self.analyzer(circuit, simulator)
        explanation = lines(analyzer, ref(block, "Y"))
        self.assertIn("BLOCK:Invert.Y = 1", explanation)
        self.assertIn("Inside Invert", explanation)
        self.assertIn("NOT.Q = 1", explanation)
        analyzer.backward(ref(block, "Y"))
        analyzer.forward(ref(block, "Y"))
        self.assertEqual(circuit.to_dict(), before)
        historical = self.analyzer(circuit, simulator, TraceFrame.from_simulator(simulator), True)
        self.assertIn("complete historical internal signal snapshot was not retained",
                      lines(historical, ref(block, "Y")))

    def test_nested_block_paths_do_not_invent_cross_connections(self):
        inner = Circuit()
        a = inner.add("INPUT", params={"label": "A"})
        b = inner.add("INPUT", params={"label": "B"})
        y = inner.add("OUTPUT", params={"label": "Y"})
        z = inner.add("OUTPUT", params={"label": "Z"})
        inner.connect(a.id, "Q", y.id, "A")
        inner.connect(b.id, "Q", z.id, "A")
        circuit = Circuit()
        circuit.blocks["Separate"] = block_definition_from_circuit(inner)
        block = circuit.add("BLOCK:Separate")
        analyzer = self.analyzer(circuit)
        forward = "\n".join(flatten(analyzer.forward(ref(block, "A", "input"))))
        self.assertIn("BLOCK:Separate.Y", forward)
        self.assertNotIn("BLOCK:Separate.Z", forward)
        backward = "\n".join(flatten(analyzer.backward(ref(block, "Y"))))
        self.assertIn("BLOCK:Separate.A", backward)
        self.assertNotIn("BLOCK:Separate.B", backward)

    def test_nested_flip_flop_uses_recorded_inner_edge(self):
        inner = Circuit()
        d = inner.add("INPUT", params={"label": "D"})
        clock = inner.add("INPUT", params={"label": "CLK"})
        ff = inner.add("D Flip-Flop")
        out = inner.add("OUTPUT", params={"label": "Y"})
        inner.connect(d.id, "Q", ff.id, "D")
        inner.connect(clock.id, "Q", ff.id, "CLK")
        inner.connect(ff.id, "Q", out.id, "A")
        circuit = Circuit()
        circuit.blocks["Stored"] = block_definition_from_circuit(inner)
        data = circuit.add("INPUT", params={"value": 1})
        clk = circuit.add("INPUT", params={"value": 0})
        block = circuit.add("BLOCK:Stored")
        circuit.connect(data.id, "Q", block.id, "D")
        circuit.connect(clk.id, "Q", block.id, "CLK")
        simulator = Simulator(circuit)
        clk.params["value"] = 1
        simulator.step()
        explanation = lines(self.analyzer(circuit, simulator), ref(block, "Y"))
        self.assertIn("BLOCK:Stored.Y = 1", explanation)
        self.assertIn("rising clock edge", explanation)
        self.assertIn("D was sampled as 1", explanation)

    def test_deep_path_is_bounded(self):
        circuit = Circuit()
        source = circuit.add("INPUT")
        previous = source
        for _ in range(110):
            gate = circuit.add("NOT")
            circuit.connect(previous.id, "Q", gate.id, "A")
            previous = gate
        analyzer = self.analyzer(circuit)
        text = "\n".join(flatten(analyzer.backward(ref(previous))))
        self.assertIn("Trace depth/size limit reached", text)


class TracingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_timing_cursor_highlight_and_circuit_change(self):
        editor = Editor()
        editor.show()
        self.app.processEvents()
        source = editor.circuit.add("INPUT", params={"value": 0})
        inv = editor.circuit.add("NOT")
        wire = editor.circuit.connect(source.id, "Q", inv.id, "A")
        editor.render()
        selected = ref(inv)
        editor.add_timing_signal(selected)
        source.params["value"] = 1
        editor.step()
        editor.trace_signal(selected, 2)
        editor.timing_panel.view.cursor_step = 0
        editor.timing_panel.view.follow_latest = False
        editor.trace_panel.on_timing_cursor()
        self.assertIn("Captured simulation step 0", editor.trace_panel.summary.text())
        self.assertIn("NOT.Q = 1", editor.trace_panel.explain_text.toPlainText())
        self.assertIn(wire.id, editor.trace_wires)
        root = editor.trace_panel.backward_tree.topLevelItem(0)
        editor.trace_panel.backward_tree.itemClicked.emit(root, 0)
        self.assertIn(inv.id, editor.selected_components())
        editor.trace_panel.clear_highlight()
        self.assertFalse(editor.trace_wires)
        editor.trace_panel.refresh()
        self.assertFalse(editor.trace_wires)
        editor.trace_history.clear()
        editor.trace_panel.refresh()
        self.assertIn("outside retained causal history", editor.trace_panel.summary.text())
        self.assertIn("Current values were not substituted", editor.trace_panel.explain_text.toPlainText())
        editor.circuit.remove(inv.id)
        editor.render()
        self.assertIsNone(editor.trace_history.at(1))
        self.assertIn("deleted", editor.trace_panel.summary.text().lower())
        editor.dirty = False
        editor.close()

    def test_inspector_can_trace_selected_wire(self):
        editor = Editor()
        source = editor.circuit.add("INPUT", params={"value": 1})
        lamp = editor.circuit.add("LED")
        wire = editor.circuit.connect(source.id, "Q", lamp.id, "A")
        editor.render()
        editor.wire_items[wire.id].setSelected(True)
        self.assertEqual(editor.inspect_name.text(), "Wire")
        self.assertIn("Signal  1", editor.inspect_detail.text())
        self.assertTrue(editor.inspect_trace_button.isEnabled())
        editor.trace_selected()
        self.assertEqual(editor.trace_panel.ref, SignalRef.wire(wire.id))
        editor.dirty = False
        editor.close()


if __name__ == "__main__":
    unittest.main()

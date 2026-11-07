import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication, QTableWidgetItem

from component_library import block_definition_from_circuit
from engine import Circuit, Simulator
from main import Editor
from testbench_model import (TestbenchSession, empty_package, new_testbench, signal_ref_dict,
                             validate_package, _isolated_circuit)
from testbench_view import TestbenchManager, TestbenchResultDialog
from timing_model import SignalRef


def bench_for(circuit, name, drives, observes, steps, assertions=None, stop=False):
    bench = new_testbench(name)
    keys = {}
    for role, signals in (("drive", drives), ("observe", observes)):
        for label, ref in signals.items():
            keys[label] = label
            bench["signals"].append({"id": label, "role": role, "ref": signal_ref_dict(ref)})
    bench["steps"] = [{"drive": {keys[k]: v for k, v in drive.items()},
                       "expect": {keys[k]: v for k, v in expect.items()},
                       "repeat": repeat}
                      for drive, expect, repeat in steps]
    bench["assertions"] = assertions or []
    bench["stop_on_failure"] = stop
    return bench


def output(component, pin="Q"):
    return SignalRef.component_pin(component.id, pin, "output")


class TestbenchEngineTests(unittest.TestCase):
    def gate_case(self, gate_kind, values, expected):
        circuit = Circuit()
        a = circuit.add("INPUT")
        b = circuit.add("INPUT") if gate_kind != "NOT" else None
        gate = circuit.add(gate_kind)
        circuit.connect(a.id, "Q", gate.id, "A")
        drives = {"A": output(a)}
        if b:
            circuit.connect(b.id, "Q", gate.id, "B")
            drives["B"] = output(b)
        steps = [({"A": row[0], **({"B": row[1]} if b else {})}, {"Y": y}, 1)
                 for row, y in zip(values, expected)]
        bench = bench_for(circuit, gate_kind, drives, {"Y": output(gate)}, steps)
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.passed, len(expected))
        self.assertEqual([row["Y"] for row in result.observations], expected)
        self.assertEqual(circuit.tick, 0)

    def test_and_truth_table(self):
        self.gate_case("AND", [(0, 0), (0, 1), (1, 0), (1, 1)], [0, 0, 0, 1])

    def test_or_truth_table(self):
        self.gate_case("OR", [(0, 0), (0, 1), (1, 0), (1, 1)], [0, 1, 1, 1])

    def test_xor_truth_table(self):
        self.gate_case("XOR", [(0, 0), (0, 1), (1, 0), (1, 1)], [0, 1, 1, 0])

    def test_not_gate(self):
        self.gate_case("NOT", [(0,), (1,)], [1, 0])

    def test_half_adder_multiple_outputs(self):
        circuit = Circuit()
        a, b, adder = circuit.add("INPUT"), circuit.add("INPUT"), circuit.add("Half Adder")
        circuit.connect(a.id, "Q", adder.id, "A")
        circuit.connect(b.id, "Q", adder.id, "B")
        steps = [({"A": x, "B": y}, {"SUM": x ^ y, "CARRY": x & y}, 1)
                 for x, y in ((0, 0), (0, 1), (1, 0), (1, 1))]
        bench = bench_for(circuit, "Half adder", {"A": output(a), "B": output(b)},
                          {"SUM": output(adder, "SUM"), "CARRY": output(adder, "CARRY")}, steps,
                          [{"id": "both", "kind": "all_equal", "at": 3,
                            "values": {"SUM": 0, "CARRY": 1}}])
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.passed, 9)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.observations[3]["CARRY"], 1)

    def test_failure_first_step_and_continue_or_stop(self):
        circuit = Circuit(); source = circuit.add("INPUT"); inv = circuit.add("NOT")
        circuit.connect(source.id, "Q", inv.id, "A")
        steps = [({"A": 0}, {"Y": 1}, 1), ({"A": 1}, {"Y": 1}, 1),
                 ({"A": 0}, {"Y": 0}, 1)]
        bench = bench_for(circuit, "Failure", {"A": output(source)}, {"Y": output(inv)}, steps)
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.failed, 2)
        self.assertEqual(result.first_failure.step, 1)
        self.assertEqual(result.first_failure.actual, 0)
        self.assertIn(1, result.snapshots)
        bench["stop_on_failure"] = True
        stopped = TestbenchSession(circuit, bench).run()
        self.assertEqual(len(stopped.observations), 2)
        self.assertTrue(stopped.stopped_early)

    def test_unknown_is_explicit_and_not_equal_is_inconclusive(self):
        circuit = Circuit(); source = circuit.add("INPUT"); inv = circuit.add("NOT")
        circuit.connect(source.id, "Q", inv.id, "A")
        assertions = [{"id": "neq", "kind": "not_equals", "signal": "Y", "value": 0, "at": 0}]
        bench = bench_for(circuit, "X", {"A": output(source)}, {"Y": output(inv)},
                          [({"A": None}, {"Y": None}, 1)], assertions)
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.passed, 1)
        self.assertEqual(result.inconclusive, 1)
        self.assertIsNone(result.observations[0]["Y"])

    def test_d_flip_flop_clock_sequence(self):
        circuit = Circuit(); data = circuit.add("INPUT"); clk = circuit.add("INPUT")
        ff = circuit.add("D Flip-Flop")
        circuit.connect(data.id, "Q", ff.id, "D")
        circuit.connect(clk.id, "Q", ff.id, "CLK")
        steps = [({"D": 1, "CLK": 0}, {"Q": 0}, 1),
                 ({"CLK": 1}, {"Q": 1}, 1),
                 ({"D": 0, "CLK": 0}, {"Q": 1}, 1),
                 ({"CLK": 1}, {"Q": 0}, 1)]
        assertions = [{"id": "edge", "kind": "changes_after", "signal": "Q", "event_signal": "CLK",
                       "from": 0, "to": 1, "within": 0}]
        bench = bench_for(circuit, "DFF", {"D": output(data), "CLK": output(clk)},
                          {"Q": output(ff)}, steps, assertions)
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual([row["Q"] for row in result.observations], [0, 1, 1, 0])
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.passed, 5)

    def test_builtin_clock_generator_and_d_flip_flop(self):
        circuit = Circuit()
        data = circuit.add("INPUT")
        clock = circuit.add("Clock Generator", params={"period": 2, "running": True})
        ff = circuit.add("D Flip-Flop")
        circuit.connect(data.id, "Q", ff.id, "D")
        circuit.connect(clock.id, "Q", ff.id, "CLK")
        bench = bench_for(circuit, "Clock", {"D": output(data)},
                          {"CLK": output(clock), "Q": output(ff)},
                          [({"D": 1}, {"CLK": 0, "Q": 0}, 1),
                           ({}, {"CLK": 1, "Q": 0}, 1),
                           ({}, {"CLK": 0, "Q": 1}, 1),
                           ({"D": 0}, {"CLK": 1, "Q": 1}, 1),
                           ({}, {"CLK": 0, "Q": 0}, 1)])
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.failed, 0)
        self.assertEqual([row["Q"] for row in result.observations], [0, 0, 1, 1, 0])

    def test_register_multibit_and_counter_reset(self):
        circuit = Circuit()
        d0, d1, clk, reset = (circuit.add("INPUT") for _ in range(4))
        reg = circuit.add("Register", params={"width": 2})
        counter = circuit.add("Binary Counter", params={"width": 2})
        for source, target, pin in ((d0, reg, "D0"), (d1, reg, "D1"), (clk, reg, "CLK"),
                                    (clk, counter, "CLK"), (reset, counter, "RESET")):
            circuit.connect(source.id, "Q", target.id, pin)
        bench = bench_for(circuit, "State", {"D0": output(d0), "D1": output(d1),
                                             "CLK": output(clk), "RESET": output(reset)},
                          {"R0": output(reg, "Q0"), "R1": output(reg, "Q1"),
                           "C0": output(counter, "Q0")},
                          [({"D0": 1, "D1": 0, "CLK": 0, "RESET": 0}, {"R0": 0, "R1": 0, "C0": 0}, 1),
                           ({"CLK": 1}, {"R0": 1, "R1": 0, "C0": 1}, 1),
                           ({"RESET": 1}, {"R0": 1, "C0": 0}, 1)])
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.observations[1]["R0"], 1)
        self.assertEqual(result.observations[2]["C0"], 0)

    def test_individual_multibit_input_pins(self):
        circuit = Circuit()
        source = circuit.add("INPUT", params={"width": 2, "value": 0})
        gate = circuit.add("NOT", params={"width": 2})
        circuit.connect(source.id, "Q0", gate.id, "A0")
        circuit.connect(source.id, "Q1", gate.id, "A1")
        bench = bench_for(circuit, "Bits", {"A0": output(source, "Q0"), "A1": output(source, "Q1")},
                          {"Y0": output(gate, "Q0"), "Y1": output(gate, "Q1")},
                          [({"A0": 1, "A1": 0}, {"Y0": 0, "Y1": 1}, 1),
                           ({"A0": 0, "A1": 1}, {"Y0": 1, "Y1": 0}, 1)])
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.passed, 4)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.timing.value_at(output(gate, "Q1"), 1), 0)

    def test_stability_equals_at_and_multiple_assertions(self):
        circuit = Circuit(); source = circuit.add("INPUT")
        bench = bench_for(circuit, "Assertions", {"A": output(source)}, {"Y": output(source)},
                          [({"A": 1}, {}, 3)],
                          [{"id": "stable", "kind": "stable", "signal": "Y", "start": 0, "end": 2},
                           {"id": "at", "kind": "equals_at", "signal": "Y", "value": 1, "at": 2},
                           {"id": "not", "kind": "not_equals", "signal": "Y", "value": 0, "at": 1}])
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.passed, 3)
        self.assertEqual(result.failed, 0)
        self.assertEqual(len(result.observations), 3)
        self.assertEqual(result.timing.last_step, 2)

    def test_stability_failure_and_missing_event_inconclusive(self):
        circuit = Circuit(); source = circuit.add("INPUT")
        bench = bench_for(circuit, "Stability", {"A": output(source)}, {"Y": output(source)},
                          [({"A": 0}, {}, 1), ({"A": 1}, {}, 1)],
                          [{"id": "stable", "kind": "stable", "signal": "Y", "start": 0, "end": 1},
                           {"id": "event", "kind": "changes_after", "signal": "Y", "event_signal": "A",
                            "from": 1, "to": 0, "within": 0}])
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.inconclusive, 1)

    def test_change_after_event_reports_deadline_failure(self):
        circuit = Circuit(); event = circuit.add("INPUT"); output_pin = circuit.add("INPUT")
        bench = bench_for(circuit, "Event deadline", {"E": output(event)},
                          {"Y": output(output_pin)},
                          [({"E": 0}, {}, 1), ({"E": 1}, {}, 2)],
                          [{"id": "after", "kind": "changes_after", "signal": "Y",
                            "event_signal": "E", "from": 0, "to": 1, "within": 1}])
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.first_failure.step, 2)
        self.assertEqual(result.first_failure.actual, 0)

    def test_cancel_and_original_state_preserved(self):
        circuit = Circuit(); source = circuit.add("INPUT", params={"value": 1})
        inv = circuit.add("NOT"); circuit.connect(source.id, "Q", inv.id, "A")
        circuit.tick = 7; source.state["custom"] = 123
        original = deepcopy(circuit.to_dict())
        live = Simulator(circuit); live_before = (deepcopy(live.outputs), deepcopy(live.inputs))
        bench = bench_for(circuit, "Cancel", {"A": output(source)}, {"Y": output(inv)},
                          [({"A": 0}, {"Y": 1}, 500)])
        session = TestbenchSession(circuit, bench)
        session.advance(10); session.cancel()
        self.assertTrue(session.result.cancelled)
        self.assertEqual(len(session.result.observations), 10)
        self.assertEqual(circuit.to_dict(), original)
        self.assertEqual((live.outputs, live.inputs), live_before)

    def test_isolated_reset_preserves_nonvolatile_memory(self):
        circuit = Circuit()
        flash = circuit.add("Flash Memory")
        flash.state.update(memory={"3": 5}, read=2)
        register = circuit.add("Register")
        register.state["value"] = 7
        circuit.tick = 9
        copied = _isolated_circuit(circuit)
        self.assertEqual(copied.tick, 0)
        self.assertEqual(copied.components[flash.id].state, {"memory": {"3": 5}})
        self.assertEqual(copied.components[register.id].state, {})
        self.assertEqual(circuit.components[register.id].state["value"], 7)

    def test_nested_custom_block(self):
        inner = Circuit(); a = inner.add("INPUT", params={"label": "A"})
        inv = inner.add("NOT"); y = inner.add("OUTPUT", params={"label": "Y"})
        inner.connect(a.id, "Q", inv.id, "A"); inner.connect(inv.id, "Q", y.id, "A")
        circuit = Circuit(); circuit.blocks["Invert"] = block_definition_from_circuit(inner)
        source = circuit.add("INPUT"); block = circuit.add("BLOCK:Invert")
        circuit.connect(source.id, "Q", block.id, "A")
        bench = bench_for(circuit, "Nested", {"A": output(source)}, {"Y": output(block, "Y")},
                          [({"A": 0}, {"Y": 1}, 1), ({"A": 1}, {"Y": 0}, 1)])
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual(result.passed, 2)
        self.assertEqual(result.failed, 0)

    def test_project_json_roundtrip_and_backward_compatibility(self):
        circuit = Circuit(); source = circuit.add("INPUT"); inv = circuit.add("NOT")
        circuit.connect(source.id, "Q", inv.id, "A")
        self.assertNotIn("testbenches", circuit.to_dict())
        bench = bench_for(circuit, "Saved", {"A": output(source)}, {"Y": output(inv)},
                          [({"A": 0}, {"Y": 1}, 1)])
        package = empty_package(); package["items"].append(bench); circuit.testbenches = package
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"; circuit.save(path)
            restored = Circuit.load(path)
            self.assertEqual(restored.testbenches, package)
            self.assertEqual(TestbenchSession(restored, restored.testbenches["items"][0]).run().passed, 1)
        old = Circuit.from_dict({key: value for key, value in circuit.to_dict().items() if key != "testbenches"})
        self.assertIsNone(old.testbenches)

    def test_invalid_values_and_deleted_pin(self):
        circuit = Circuit(); source = circuit.add("INPUT"); inv = circuit.add("NOT")
        circuit.connect(source.id, "Q", inv.id, "A")
        bench = bench_for(circuit, "Invalid", {"A": output(source)}, {"Y": output(inv)},
                          [({"A": 0}, {"Y": 1}, 1)])
        package = empty_package(); package["items"].append(bench)
        package["items"][0]["steps"][0]["drive"]["A"] = 2
        with self.assertRaisesRegex(ValueError, "use 0, 1 or X"):
            validate_package(circuit, package)
        package["items"][0]["steps"][0]["drive"]["A"] = 0
        package["items"][0]["steps"][0]["drive"]["A"] = True
        with self.assertRaisesRegex(ValueError, "use 0, 1 or X"):
            validate_package(circuit, package)
        package["items"][0]["steps"][0]["drive"]["A"] = 0
        circuit.testbenches = package
        circuit.remove(inv.id)
        loaded = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
        self.assertTrue(loaded.testbench_issues)
        with self.assertRaisesRegex(ValueError, "missing or unsupported pin"):
            TestbenchSession(loaded, bench)

    def test_malformed_testbench_data_preserved_with_warning(self):
        data = Circuit().to_dict(); data["testbenches"] = {"version": 99}
        loaded = Circuit.from_dict(data)
        self.assertIn("schema version", loaded.testbench_issues[0])
        self.assertEqual(loaded.to_dict()["testbenches"], {"version": 99})

    def test_configurable_limits(self):
        circuit = Circuit(); source = circuit.add("INPUT")
        bench = bench_for(circuit, "Limit", {"A": output(source)}, {"Y": output(source)},
                          [({"A": 0}, {"Y": 0}, 6), ({"A": 1}, {"Y": 1}, 6)])
        with self.assertRaisesRegex(ValueError, "exceeds 10"):
            TestbenchSession(circuit, bench, max_steps=10)


class TestbenchUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_manager_sequence_timing_and_failure_trace(self):
        editor = Editor(); editor.show(); self.app.processEvents()
        source = editor.circuit.add("INPUT")
        inv = editor.circuit.add("NOT")
        editor.circuit.connect(source.id, "Q", inv.id, "A")
        editor.render()
        bench = bench_for(editor.circuit, "UI failure", {"A": output(source)}, {"Y": output(inv)},
                          [({"A": 0}, {"Y": 0}, 1), ({"A": 1}, {"Y": 0}, 1)])
        package = empty_package(); package["items"] = [bench]
        editor.circuit.testbenches = deepcopy(package)
        original = deepcopy(editor.circuit.to_dict())
        manager = TestbenchManager(editor)
        self.assertEqual(manager.steps.rowCount(), 2)
        manager.run_selected()
        while manager.running: manager._advance()
        result = manager.results[0]
        self.assertEqual(result.first_failure.step, 0)
        self.assertEqual(result.timing.value_at(output(inv), 0), 1)
        dialog = TestbenchResultDialog(editor, result)
        self.assertEqual(dialog.items.rowCount(), 2)
        dialog.show_timing()
        self.assertEqual(dialog.waveform.cursor_step, 0)
        dialog.items.selectRow(0)
        dialog.explain_selected()
        self.assertIn("Failed assertion at step 0", editor.trace_panel.explain_text.toPlainText())
        self.assertIn("NOT.Q = 1", editor.trace_panel.explain_text.toPlainText())
        self.assertEqual(editor.circuit.to_dict(), original)
        dialog.close(); manager.dirty = False; manager.close(); editor.dirty = False; editor.close()

    def test_manager_runs_edited_steps_and_all_benches(self):
        editor = Editor(); source = editor.circuit.add("INPUT")
        inv = editor.circuit.add("NOT"); editor.circuit.connect(source.id, "Q", inv.id, "A")
        first = bench_for(editor.circuit, "First", {"A": output(source)}, {"Y": output(inv)},
                          [({"A": 0}, {"Y": 1}, 1)])
        second = deepcopy(first); second["id"] = "second"; second["name"] = "Second"
        editor.circuit.testbenches = empty_package(); editor.circuit.testbenches["items"] = [first, second]
        manager = TestbenchManager(editor)
        manager.steps.setItem(0, 1, QTableWidgetItem("1"))
        manager.run_selected()
        while manager.running: manager._advance()
        self.assertEqual(manager.results[0].failed, 1)
        manager.run_all()
        while manager.running: manager._advance()
        self.assertEqual([result.failed for result in manager.results], [1, 0])
        manager.dirty = False; manager.close(); editor.dirty = False; editor.close()

    def test_manager_commit_is_undoable(self):
        editor = Editor()
        manager = TestbenchManager(editor)
        bench = new_testbench("Undoable")
        manager.package["items"].append(bench)
        manager.refresh_benches(bench["id"])
        self.assertTrue(manager.commit())
        self.assertEqual(editor.circuit.testbenches["items"][0]["name"], "Undoable")
        editor.undo()
        self.assertIsNone(editor.circuit.testbenches)
        editor.redo()
        self.assertEqual(editor.circuit.testbenches["items"][0]["name"], "Undoable")
        manager.close(); editor.dirty = False; editor.close()

    def test_editor_manager_is_modeless_and_closes_on_new_project(self):
        editor = Editor(); editor.show(); self.app.processEvents()
        editor.open_testbench_manager()
        manager = editor.testbench_manager
        self.assertTrue(manager.isVisible())
        self.assertFalse(manager.isModal())
        editor.new_file()
        self.app.processEvents()
        self.assertIsNone(editor.testbench_manager)
        editor.dirty = False; editor.close()


if __name__ == "__main__":
    unittest.main()

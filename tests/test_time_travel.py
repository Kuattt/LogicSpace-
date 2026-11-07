import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication

from engine import Circuit, Simulator
from component_library import block_definition_from_circuit
from main import Editor
from testbench_model import TestbenchSession
from testbench_view import TestbenchResultDialog
from tests.test_testbench import bench_for, output
from time_travel_model import SimulationHistory, SimulationSnapshot
from timing_model import SignalRef


def clocked_circuit():
    circuit = Circuit()
    data = circuit.add("INPUT", params={"value": 1})
    clock = circuit.add("Clock Generator", params={"period": 2, "running": True})
    ff = circuit.add("D Flip-Flop")
    register = circuit.add("Register", params={"width": 2})
    counter = circuit.add("Binary Counter", params={"width": 2})
    reset = circuit.add("INPUT", params={"value": 0})
    circuit.connect(data.id, "Q", ff.id, "D")
    circuit.connect(data.id, "Q", register.id, "D0")
    circuit.connect(data.id, "Q", register.id, "D1")
    for target in (ff, register, counter):
        circuit.connect(clock.id, "Q", target.id, "CLK")
    circuit.connect(reset.id, "Q", counter.id, "RESET")
    return circuit, data, clock, ff, register, counter, reset


class TimeTravelModelTests(unittest.TestCase):
    def setUp(self):
        self.circuit, self.data, self.clock, self.ff, self.register, self.counter, self.reset = clocked_circuit()
        self.sim = Simulator(self.circuit)
        self.history = SimulationHistory(self.sim, limit=40)

    def advance(self, count):
        for _ in range(count):
            self.sim.step()
            self.history.record(self.sim)

    def test_backward_forward_and_arbitrary_jump_restore_values(self):
        self.advance(6)
        recorded = {step: self.history.snapshot_at("main", step)
                    for step in self.history.available_steps()}
        for step in (2, 0, 4, 6):
            snapshot = self.history.navigate(self.sim, step)
            self.assertEqual(self.circuit.tick, step)
            self.assertEqual(self.sim.outputs, snapshot.frame.outputs)
            self.assertEqual(self.sim.inputs, snapshot.frame.inputs)
            self.assertEqual(self.ff.state, recorded[step].states[self.ff.id])

    def test_clock_flip_flop_register_counter_restore_and_replay(self):
        self.advance(5)
        final = self.history.snapshot_at("main", 5)
        self.assertEqual(final.states[self.ff.id]["q"], 1)
        self.assertEqual(final.states[self.register.id]["value"], 3)
        self.assertEqual(final.states[self.counter.id]["value"], 2)
        self.history.navigate(self.sim, 2)
        self.assertEqual(self.clock.params["period"], 2)
        self.assertEqual(self.ff.state, self.history.current.states[self.ff.id])
        self.assertEqual(self.register.state, self.history.current.states[self.register.id])
        self.assertEqual(self.counter.state, self.history.current.states[self.counter.id])
        for _ in range(3): self.sim.step()
        self.assertEqual(self.sim.outputs, final.frame.outputs)
        self.assertEqual(self.ff.state, final.states[self.ff.id])
        self.assertEqual(self.counter.state, final.states[self.counter.id])

    def test_checkpoint_jump_rename_delete(self):
        self.advance(3)
        self.history.navigate(self.sim, 1)
        checkpoint = self.history.add_checkpoint("before edge")
        self.history.rename_checkpoint(checkpoint.id, "edge start")
        self.assertEqual(checkpoint.name, "edge start")
        self.history.navigate(self.sim, 3)
        self.history.navigate_checkpoint(self.sim, checkpoint.id)
        self.assertEqual(self.circuit.tick, 1)
        self.history.delete_checkpoint(checkpoint.id)
        self.assertNotIn(checkpoint.id, self.history.checkpoints)

    def test_branch_preserves_old_future_and_input_mutation(self):
        self.advance(4)
        old_head = self.history.snapshot_at("main", 4)
        self.history.navigate(self.sim, 2)
        self.data.params["value"] = 0
        self.sim.evaluate()
        self.history.record_mutation(self.sim)
        branch_id = self.history.active_branch
        self.assertEqual(len(self.history.branches), 2)
        self.assertNotEqual(branch_id, "main")
        self.advance(2)
        self.assertEqual(self.history.latest_step, 4)
        new_head = self.history.current
        self.assertNotEqual(new_head.frame.outputs, old_head.frame.outputs)
        self.history.navigate(self.sim, 4, "main")
        self.assertEqual(self.sim.outputs, old_head.frame.outputs)
        self.history.navigate(self.sim, 4, branch_id)
        self.assertEqual(self.sim.outputs, new_head.frame.outputs)

    def test_automatic_branch_on_step_from_past(self):
        self.advance(4)
        self.history.navigate(self.sim, 2)
        self.sim.step(); self.history.record(self.sim)
        self.assertEqual(self.history.current.step, 3)
        self.assertNotEqual(self.history.active_branch, "main")
        self.assertEqual(self.history.branches["main"].latest_step, 4)

    def test_state_pin_and_wire_comparison(self):
        self.advance(4)
        first = self.history.snapshot_at("main", 1)
        second = self.history.snapshot_at("main", 2)
        rows = self.history.compare(self.circuit, first, second)
        self.assertTrue(any(row.category == "State" and self.ff.id == row.component_id and row.changed
                            for row in rows))
        self.assertTrue(any(row.category == "Pin" and row.changed for row in rows))
        self.assertTrue(any(row.category == "Wire" and row.changed for row in rows))
        self.assertTrue(all(row.changed for row in rows))
        with_unchanged = self.history.compare(self.circuit, first, second, include_unchanged=True)
        self.assertGreater(len(with_unchanged), len(rows))

    def test_history_expiration_and_checkpoint_status(self):
        history = SimulationHistory(self.sim, limit=3)
        checkpoint = history.add_checkpoint("initial")
        for _ in range(5):
            self.sim.step(); history.record(self.sim)
        self.assertLessEqual(len(history.snapshots), 3)
        self.assertFalse(history.checkpoint_available(checkpoint))
        with self.assertRaisesRegex(ValueError, "unavailable"):
            history.navigate(self.sim, 0)
        with self.assertRaisesRegex(ValueError, "expired"):
            history.navigate_checkpoint(self.sim, checkpoint.id)

    def test_memory_limit_evicts_large_states(self):
        self.data.state["large"] = "x" * 750000
        self.sim.evaluate()
        history = SimulationHistory(self.sim, limit=20, memory_mib=1)
        for _ in range(4):
            self.sim.step(); history.record(self.sim)
        self.assertLessEqual(history.total_bytes, 1048576)
        self.assertLess(len(history.snapshots), 4)

    def test_branch_count_is_bounded(self):
        self.advance(1)
        self.history.navigate(self.sim, 0)
        checkpoint = self.history.add_checkpoint("original")
        for _ in range(18):
            self.history.fork()
        self.assertLessEqual(len(self.history.branches), 16)
        self.assertFalse(self.history.checkpoint_available(checkpoint))

    def test_forced_pin_restore_and_deterministic_continuation(self):
        self.sim.force_pin(self.data.id, "Q", "output", 0)
        self.history.record_mutation(self.sim)
        self.advance(2)
        forced = self.history.current
        self.sim.release_pin(self.data.id, "Q", "output")
        self.history.navigate(self.sim, 2)
        self.assertEqual(self.sim.forced_outputs[(self.data.id, "Q")], 0)
        self.assertEqual(self.sim.outputs, forced.frame.outputs)
        self.sim.step()
        self.assertEqual(self.sim.forced_outputs[(self.data.id, "Q")], 0)

    def test_ram_contents_restore(self):
        circuit = Circuit()
        data = circuit.add("INPUT", params={"value": 1})
        address = circuit.add("INPUT", params={"value": 0})
        write = circuit.add("INPUT", params={"value": 1})
        clock = circuit.add("INPUT", params={"value": 0})
        ram = circuit.add("RAM", params={"address_bits": 1, "data_bits": 1})
        for source, pin in ((data, "D0"), (address, "A0"), (write, "WE"), (clock, "CLK")):
            circuit.connect(source.id, "Q", ram.id, pin)
        sim = Simulator(circuit); history = SimulationHistory(sim)
        clock.params["value"] = 1
        sim.evaluate(); history.record_mutation(sim)
        sim.step(); history.record(sim)
        self.assertEqual(ram.state["memory"]["0"], 1)
        written = history.current
        history.navigate(sim, 0)
        self.assertNotIn("0", ram.state.get("memory", {}))
        sim.step()
        self.assertEqual(ram.state, written.states[ram.id])

    def test_nested_block_internal_state_restores(self):
        inner = Circuit()
        data = inner.add("INPUT", params={"label": "D"})
        clock = inner.add("INPUT", params={"label": "CLK"})
        flip = inner.add("D Flip-Flop")
        output_terminal = inner.add("OUTPUT", params={"label": "Q"})
        inner.connect(data.id, "Q", flip.id, "D")
        inner.connect(clock.id, "Q", flip.id, "CLK")
        inner.connect(flip.id, "Q", output_terminal.id, "A")
        outer = Circuit()
        outer.blocks["Stored"] = block_definition_from_circuit(inner)
        source = outer.add("INPUT", params={"value": 1})
        clock_source = outer.add("Clock Generator", params={"period": 2})
        block = outer.add("BLOCK:Stored")
        outer.connect(source.id, "Q", block.id, "D")
        outer.connect(clock_source.id, "Q", block.id, "CLK")
        definition_before = deepcopy(outer.blocks["Stored"])
        sim = Simulator(outer); history = SimulationHistory(sim)
        for _ in range(5): sim.step(); history.record(sim)
        self.assertEqual(outer.blocks["Stored"], definition_before)
        final = history.current
        self.assertIn("inner", block.state)
        history.navigate(sim, 2)
        for _ in range(3): sim.step()
        self.assertEqual(block.state, final.states[block.id])
        self.assertEqual(sim.outputs, final.frame.outputs)

    def test_project_json_unchanged_by_history(self):
        original = deepcopy(self.circuit.to_dict())
        self.advance(3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            self.circuit.save(path)
            reopened = Circuit.load(path)
            self.assertEqual(reopened.to_dict(), self.circuit.to_dict())
            self.assertNotIn("time_travel", json.loads(path.read_text()))
        self.assertEqual(original["components"][0]["id"], self.circuit.to_dict()["components"][0]["id"])


class TimeTravelUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def editor(self):
        editor = Editor()
        editor.show()
        circuit, data, clock, ff, register, counter, reset = clocked_circuit()
        editor.circuit = circuit
        editor.sim = Simulator(circuit)
        editor.render()
        self.app.processEvents()
        return editor, data, clock, ff, register, counter

    def test_navigation_updates_canvas_timing_and_tracing(self):
        editor, data, clock, ff, register, counter = self.editor()
        ref = SignalRef.component_pin(ff.id, "Q", "output")
        editor.timing_panel.add_refs([ref])
        for _ in range(5): editor.step()
        editor.show_time_debugger()
        editor.time_panel.back()
        self.assertEqual(editor.circuit.tick, 4)
        self.assertEqual(editor.timing_panel.view.cursor_step, 4)
        self.assertEqual(editor.sim.outputs[ff.id, "Q"], editor.time_history.current.frame.outputs[ff.id, "Q"])
        editor.trace_signal(ref, 2)
        self.assertIn("Step 4", editor.trace_panel.explain_text.toPlainText())
        editor.time_panel.first()
        self.assertEqual(editor.circuit.tick, 0)
        editor.timing_panel.view.cursor_step = 3
        editor.timing_panel.view.follow_latest = False
        editor.timing_panel.view.cursorChanged.emit()
        self.assertEqual(editor.circuit.tick, 3)
        editor.timing_panel.view.cursor_step = 0
        editor.timing_panel.view.cursorChanged.emit()
        self.assertEqual(editor.circuit.tick, 0)
        editor.time_panel.latest()
        self.assertEqual(editor.circuit.tick, 5)
        editor.dirty = False; editor.close()

    def test_editor_step_from_past_branches_and_replay(self):
        editor, data, clock, ff, register, counter = self.editor()
        for _ in range(4): editor.step()
        editor.navigate_time(1)
        editor.step()
        self.assertNotEqual(editor.time_history.active_branch, "main")
        self.assertEqual(editor.time_history.branches["main"].latest_step, 4)
        editor.navigate_time(0, "main")
        editor.time_panel._replay_next()
        self.assertEqual(editor.circuit.tick, 1)
        editor.dirty = False; editor.close()

    def test_testbench_failure_inspection_does_not_change_live_state(self):
        editor, data, clock, ff, register, counter = self.editor()
        bench = bench_for(editor.circuit, "Failure", {"D": output(data)}, {"Q": output(ff)},
                          [({"D": 1}, {"Q": 0}, 1), ({}, {"Q": 1}, 1)])
        result = TestbenchSession(editor.circuit, bench).run()
        self.assertEqual(result.first_failure.step, 1)
        original = deepcopy(editor.circuit.to_dict())
        outputs = deepcopy(editor.sim.outputs)
        dialog = TestbenchResultDialog(editor, result)
        dialog.items.selectRow(1)
        dialog.open_debugger("previous")
        self.assertEqual(editor.circuit.to_dict(), original)
        self.assertEqual(editor.sim.outputs, outputs)
        self.assertIn("isolated inspection", editor.time_panel.summary.text())
        self.assertGreater(editor.time_panel.differences.rowCount(), 0)
        branches = len(editor.time_history.branches)
        editor.time_panel.continue_here()
        self.assertEqual(len(editor.time_history.branches), branches)
        editor.time_panel.inspect_testbench(result, 1, "expected")
        self.assertEqual(editor.time_panel.differences.item(0, 2).text(), "1")
        self.assertEqual(editor.time_panel.differences.item(0, 3).text(), "0")
        dialog.close(); editor.dirty = False; editor.close()

    def test_historical_save_writes_branch_head_without_moving_preview(self):
        editor, data, clock, ff, register, counter = self.editor()
        for _ in range(5): editor.step()
        head = editor.time_history.current
        editor.navigate_time(2)
        with tempfile.TemporaryDirectory() as directory:
            editor.path = str(Path(directory) / "history.json")
            self.assertTrue(editor.save())
            saved = Circuit.load(editor.path)
            self.assertEqual(saved.tick, 5)
            self.assertEqual(saved.components[ff.id].state, head.states[ff.id])
            self.assertEqual(editor.circuit.tick, 2)
        editor.dirty = False; editor.close()

    def test_switching_branches_rebuilds_timing_waveform(self):
        editor, data, clock, ff, register, counter = self.editor()
        ref = output(ff)
        editor.timing_panel.add_refs([ref])
        for _ in range(5): editor.step()
        old_value = editor.timing_history.value_at(ref, 4)
        editor.navigate_time(2)
        editor.toggle_input(data.id)
        new_branch = editor.time_history.active_branch
        self.assertEqual(len(editor.time_history.branches), 2)
        for _ in range(2): editor.step()
        self.assertNotEqual(new_branch, "main")
        self.assertNotEqual(editor.timing_history.value_at(ref, 4), old_value)
        editor.navigate_time(4, "main")
        self.assertEqual(editor.timing_history.value_at(ref, 4), old_value)
        editor.dirty = False; editor.close()

    def test_timing_signal_added_later_uses_retained_snapshots(self):
        editor, data, clock, ff, register, counter = self.editor()
        for _ in range(5): editor.step()
        ref = output(ff)
        editor.timing_panel.add_refs([ref])
        editor.navigate_time(2)
        expected = editor.time_history.current.frame.value(ref, editor.circuit)
        self.assertEqual(editor.timing_history.value_at(ref, 2), expected)
        editor.dirty = False; editor.close()


if __name__ == "__main__":
    unittest.main()

"""Headless Qt integration tests for the timing panel and existing editor controls."""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import Editor
from timing_model import SignalRef
from timing_view import SignalPicker


class TimingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = Editor()
        self.editor.show()
        self.editor.show_timing(True)
        self.app.processEvents()

    def tearDown(self):
        self.editor.timer.stop()
        self.editor.dirty = False
        self.editor.close()
        self.app.processEvents()

    def test_manual_step_pause_and_reset(self):
        clock = self.editor.circuit.add("Clock Generator", params={"period": 2})
        self.editor.render()
        ref = SignalRef.component_pin(clock.id, "Q", "output")
        self.editor.add_timing_signal(ref)
        self.editor.step()
        self.assertEqual(self.editor.timing_history.last_step, 1)
        self.assertEqual(self.editor.timing_history.value_at(ref, 1), 1)
        self.editor.speed.setValue(20)
        self.editor.toggle_run()
        QTest.qWait(125)
        self.assertGreaterEqual(self.editor.timing_history.last_step, 2)
        self.editor.toggle_run()
        stopped = self.editor.timing_history.last_step
        QTest.qWait(120)
        self.assertEqual(self.editor.timing_history.last_step, stopped)
        self.editor.reset()
        self.assertEqual(list(self.editor.timing_history.steps), [0])
        self.assertEqual(self.editor.timing_history.value_at(ref, 0), 0)

    def test_picker_multi_select_and_remove(self):
        a = self.editor.circuit.add("INPUT")
        b = self.editor.circuit.add("INPUT")
        self.editor.render()
        picker = SignalPicker(self.editor.circuit)
        self.assertGreaterEqual(picker.list.count(), 2)
        picker.list.item(0).setSelected(True)
        picker.list.item(1).setSelected(True)
        selected = picker.selected_refs()
        self.assertEqual(len(selected), 2)
        picker.close()
        self.editor.timing_panel.add_refs(selected)
        self.assertEqual(len(self.editor.timing_history.tracks), 2)
        self.editor.timing_panel.view.selected_ref = selected[0]
        self.editor.timing_panel.remove_selected()
        self.assertEqual(len(self.editor.timing_history.tracks), 1)

    def test_cursor_lookup_and_zoom_coordinates(self):
        clock = self.editor.circuit.add("Clock Generator", params={"period": 2})
        self.editor.render()
        ref = SignalRef.component_pin(clock.id, "Q", "output")
        self.editor.add_timing_signal(ref)
        for _ in range(5):
            self.editor.step()
        view = self.editor.timing_panel.view
        view.fit_all()
        view.zoom(0.8)
        old_scale = view.pixels_per_step
        view.zoom(1.25)
        self.assertGreater(view.pixels_per_step, old_scale)
        for step in range(6):
            self.assertEqual(view._x_step(view._step_x(step)), step)
            self.assertEqual(self.editor.timing_history.value_at(ref, step), step % 2)
        view.cursor_step = 3
        self.editor.timing_panel.update_cursor_label()
        self.assertIn("Step 3", self.editor.timing_panel.cursor_label.text())
        self.assertIn("1", self.editor.timing_panel.cursor_label.text())

    def test_multibit_summary_when_all_bits_selected(self):
        bus = self.editor.circuit.add("INPUT", params={"width": 4, "value": 0b1010})
        self.editor.render()
        refs = [SignalRef.component_pin(bus.id, f"Q{i}", "output") for i in range(4)]
        self.editor.timing_panel.add_refs(refs)
        self.assertIn("Q[3:0]: 1010", self.editor.timing_panel.cursor_label.text())

    def test_fit_all_includes_long_history(self):
        clock = self.editor.circuit.add("Clock Generator", params={"period": 2})
        self.editor.render()
        self.editor.add_timing_signal(SignalRef.component_pin(clock.id, "Q", "output"))
        for _ in range(600):
            self.editor.sim.step()
            self.editor.timing_history.record_step(self.editor.sim)
        view = self.editor.timing_panel.view
        view.fit_all()
        self.assertEqual(view.horizontalScrollBar().maximum(), 0)
        self.assertLess(view._step_x(600), view.viewport().width())

    def test_structural_edit_restarts_capture(self):
        clock = self.editor.circuit.add("Clock Generator")
        self.editor.render()
        self.editor.add_timing_signal(SignalRef.component_pin(clock.id, "Q", "output"))
        self.editor.step()
        self.editor.circuit.add("LED")
        self.editor.render()
        self.assertEqual(list(self.editor.timing_history.steps), [1])


if __name__ == "__main__":
    unittest.main()

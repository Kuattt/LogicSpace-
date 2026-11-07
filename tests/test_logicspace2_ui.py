"""GUI integration for advanced signal tools and wide bus presentation."""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication

from logic_analyzer_model import format_value
from main import Editor
from timing_model import SignalRef


class LogicSpace2UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = Editor()
        self.editor.show()
        self.app.processEvents()

    def tearDown(self):
        self.editor.timer.stop()
        self.editor.dirty = False
        self.editor.close()
        self.app.processEvents()

    def test_analyzer_uses_timing_capture_and_wide_bus(self):
        source = self.editor.circuit.add("Bus Input", params={"width": 32, "value": 0xAABBCCDD})
        probe = self.editor.circuit.add("Bus Probe", params={"width": 32, "display": "hex"})
        self.editor.circuit.connect_bus(source.id, "Q", probe.id, "D")
        self.editor.render()
        ref = SignalRef.bus_port(probe.id, "D", "input")
        self.editor.add_timing_signal(ref)
        self.editor.show_logic_analyzer()
        self.app.processEvents()
        self.assertTrue(self.editor.analyzer_dock.isVisible())
        self.assertIn(ref, self.editor.timing_history.tracks)
        self.assertEqual(format_value(ref.value(self.editor.sim), "hex"), "0xAABBCCDD")
        self.editor.step()
        self.assertEqual(self.editor.analyzer_panel.end.value(), 1)
        self.editor.analyzer_panel.view.follow_latest = False
        self.editor.analyzer_panel.view.cursor_step = 0
        self.editor.analyzer_panel.view.cursorChanged.emit()
        self.assertEqual(self.editor.circuit.tick, 0)
        self.assertEqual(self.editor.timing_panel.view.cursor_step, 0)

    def test_rising_breakpoint_stops_run_and_clock_cycle(self):
        clock = self.editor.circuit.add("Clock Generator", params={"period": 2})
        self.editor.render()
        ref = SignalRef.component_pin(clock.id, "Q", "output")
        self.editor.breakpoints.add(ref, "rising", self.editor.sim)
        self.editor.show_advanced_debugger()
        self.editor.toggle_run()
        self.editor.step()
        self.assertFalse(self.editor.timer.isActive())
        self.assertEqual(self.editor.circuit.tick, 1)
        self.assertEqual(self.editor.last_break_events[0].reason, "rising")
        self.assertEqual(self.editor.step_clock_cycle(ref), 3)

    def test_step_spacing_marks_actual_recorded_edges(self):
        clock = self.editor.circuit.add("INPUT", params={"value": 0})
        data = self.editor.circuit.add("INPUT", params={"value": 0})
        self.editor.render()
        clock_ref = SignalRef.component_pin(clock.id, "Q", "output")
        data_ref = SignalRef.component_pin(data.id, "Q", "output")
        self.editor.add_timing_signal(clock_ref)
        self.editor.add_timing_signal(data_ref)
        self.editor.show_logic_analyzer()
        data.params["value"] = 1; self.editor.step()
        clock.params["value"] = 1; self.editor.step()
        panel = self.editor.analyzer_panel
        panel.clock_signal.setCurrentIndex(panel.clock_signal.findData(clock_ref))
        panel.data_signal.setCurrentIndex(panel.data_signal.findData(data_ref))
        panel.analyze_spacing()
        self.assertIn((2, "#e4b46f"), panel.view.analysis_markers)
        self.assertIn((1, "#65d7bd"), panel.view.analysis_markers)
        self.assertIn("previous change 1 steps before", panel.report.toPlainText())
        self.editor.reset()
        self.assertEqual(panel.view.analysis_markers, [])


if __name__ == "__main__":
    unittest.main()

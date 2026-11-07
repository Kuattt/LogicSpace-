"""Source snapshots and project navigation survive real editor serialization."""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from engine import Circuit
from hdl_model import HDLError, hdl_signal_components, import_verilog
from main import Editor


SOURCE = "module gate(input a,input b,output y); assign y=a&b; endmodule"


class SourceMapTests(unittest.TestCase):
    def test_source_snapshot_targets_real_gate_and_survives_json(self):
        circuit = import_verilog(SOURCE)
        source_id = next(iter(circuit.hdl_sources))
        producers = hdl_signal_components(circuit, source_id, "y")
        self.assertEqual(producers[0].kind, "AND")
        restored = Circuit.from_dict(circuit.to_dict())
        self.assertEqual(restored.hdl_sources[source_id]["source"], SOURCE)
        self.assertEqual(hdl_signal_components(restored, source_id, "y")[0].kind, "AND")

    def test_invalid_source_metadata_is_rejected(self):
        data = Circuit().to_dict()
        data["hdl_sources"] = {"bad": {"module": "gate", "source": 7}}
        self.assertRaises(ValueError, Circuit.from_dict, data)
        self.assertRaises(HDLError, import_verilog, "x" * 1_000_001)


class NavigationUiTests(unittest.TestCase):
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
        self.editor.hdl_panel.dirty = False
        self.editor.close()
        self.app.processEvents()

    def test_hdl_to_canvas_and_inspector_back_to_source(self):
        panel = self.editor.hdl_panel
        panel.code.setPlainText(SOURCE)
        panel.import_circuit()
        self.assertTrue(self.editor.circuit.hdl_sources)
        offset = SOURCE.index("assign y") + len("assign ")
        cursor = panel.code.textCursor()
        cursor.setPosition(offset)
        panel.code.setTextCursor(cursor)
        panel.find_signal_on_canvas()
        selected = self.editor.selected_components()
        self.assertEqual(len(selected), 1)
        self.assertEqual(self.editor.circuit.components[selected[0]].kind, "AND")
        self.assertTrue(self.editor.inspect_hdl_button.isVisible())
        self.assertTrue(panel.open_source_for_component(self.editor.circuit.components[selected[0]]))
        self.assertEqual(panel.code.toPlainText(), SOURCE)
        self.editor.project_search.setText("AND")
        self.assertGreater(self.editor.project_results.topLevelItemCount(), 0)
        self.editor.focus_first_project_result()
        self.assertEqual(self.editor.circuit.components[self.editor.selected_components()[0]].kind, "AND")
        restored = Circuit.from_dict(self.editor.circuit.to_dict())
        self.assertEqual(len(restored.hdl_sources), 1)

    def test_source_limit_rejects_merge_before_mutating_project(self):
        self.editor.circuit.hdl_sources = {
            str(index): {"module": "m", "source": "module m(); endmodule", "filename": ""}
            for index in range(64)}
        before = self.editor.circuit.to_dict()
        self.assertRaises(ValueError, self.editor._merge, import_verilog(SOURCE))
        self.assertEqual(self.editor.circuit.to_dict(), before)


if __name__ == "__main__": unittest.main()

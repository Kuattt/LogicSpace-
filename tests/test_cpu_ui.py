"""CPU workspace uses the live editor, simulator and Time Travel history."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication

from cpu_board import validate_board
from cpu_architecture import discover_cpus, get_active_binding, get_bindings
from engine import Simulator, copy_selection
from main import Editor


class CpuUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = Editor()
        self.editor.show(); self.editor.show_cpu_assembly()
        self.app.processEvents()

    def tearDown(self):
        self.editor.timer.stop(); self.editor.dirty = False
        self.editor.close(); self.app.processEvents()

    def test_create_assemble_load_step_and_memory_edit(self):
        panel = self.editor.cpu_panel
        panel.create_board()
        ids = validate_board(self.editor.circuit)
        self.assertTrue(self.editor.cpu_dock.isVisible())
        panel.source.setPlainText("MOV R0, 8\nSTORE R0, 0x20\nHLT\n")
        self.assertIsNotNone(panel.assemble_source())
        self.assertEqual(panel.machine.rowCount(), 3)
        panel.load_to_rom()
        self.assertEqual(self.editor.circuit.components[ids["rom"]].params["contents"]["2"], 8)
        panel.step_mode("instruction")
        self.assertEqual(self.editor.circuit.components[ids["registers"]].state["words"]["0"], 8)
        self.assertEqual(self.editor.circuit.components[ids["control"]].state["instructions"], 1)
        self.assertGreater(self.editor.circuit.tick, 1)
        self.assertEqual(panel.instruction_history.count(), 1)
        panel.memory_address.setValue(0x30)
        panel.memory_value.setText("0x7F")
        branch_before = self.editor.time_history.active_branch
        panel.write_memory()
        self.assertEqual(self.editor.circuit.components[ids["ram"]].state["memory"]["48"], 127)
        self.assertNotEqual(self.editor.time_history.active_branch, branch_before)
        self.assertIn("0x7F", panel.address_info.text())

    def test_line_error_and_breakpoint_pause_before_execution(self):
        panel = self.editor.cpu_panel
        panel.create_board()
        panel.source.setPlainText("NOP\nBAD R0\n")
        self.assertIsNone(panel.assemble_source())
        self.assertIn("Line 2", panel.status.text())
        self.assertEqual(panel.source.textCursor().blockNumber(), 1)
        panel.source.setPlainText("MOV R0, 3\nHLT\n")
        panel.load_to_rom()
        self.editor.cpu_breakpoints.add("line", 1)
        for _ in range(20):
            self.editor.step()
            if self.editor.last_cpu_events: break
        self.assertTrue(self.editor.last_cpu_events)
        ids = validate_board(self.editor.circuit)
        self.assertEqual(self.editor.circuit.components[ids["control"]].state["phase"], "EXEC")
        self.assertEqual(self.editor.circuit.components[ids["registers"]].state.get("words", {}), {})
        self.assertGreaterEqual(self.editor.debug_panel.events.count(), 1)
        panel.step_mode("instruction")
        self.assertEqual(self.editor.circuit.components[ids["registers"]].state["words"]["0"], 3)

    def test_assembly_load_undo_redo_preserves_wired_rom(self):
        panel = self.editor.cpu_panel
        panel.create_board()
        first = self.editor.circuit.components[validate_board(self.editor.circuit)["rom"]].params["contents"]["0"]
        panel.source.setPlainText("HLT\n")
        panel.load_to_rom()
        self.assertEqual(self.editor.circuit.components[validate_board(self.editor.circuit)["rom"]].params["contents"]["0"], 1)
        self.editor.undo()
        self.assertEqual(self.editor.circuit.components[validate_board(self.editor.circuit)["rom"]].params["contents"]["0"], first)
        self.editor.redo()
        self.assertEqual(self.editor.circuit.components[validate_board(self.editor.circuit)["rom"]].params["contents"]["0"], 1)

    def test_edit_invalidates_stale_machine_code(self):
        panel = self.editor.cpu_panel
        panel.create_board()
        panel.source.setPlainText("MOV R0, 1\nHLT\n")
        first = panel.assemble_source()
        self.assertEqual(first.image[2], 1)
        panel.source.setPlainText("MOV R0, 2\nHLT\n")
        self.assertIsNone(panel.assembled)
        self.assertEqual(panel.machine.rowCount(), 0)
        self.assertEqual(panel.assemble_source().image[2], 2)

    def test_gui_save_and_reopen_cpu_project(self):
        panel = self.editor.cpu_panel
        panel.create_board()
        panel.source.setPlainText("MOV R0, 23\nHLT\n")
        panel.load_to_rom()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "cpu.json")
            self.editor.path = path
            self.assertTrue(self.editor.save())
            with patch("main.QFileDialog.getOpenFileName", return_value=(path, "")):
                self.editor.open_file()
            ids = validate_board(self.editor.circuit)
            self.assertEqual(panel.source.toPlainText(), "MOV R0, 23\nHLT\n")
            self.assertEqual(self.editor.circuit.components[ids["rom"]].params["contents"]["2"], 23)
            panel.step_mode("instruction")
            self.assertEqual(self.editor.circuit.components[ids["registers"]].state["words"]["0"], 23)

    def test_gui_detect_bind_and_switch_two_wired_cpus(self):
        panel = self.editor.cpu_panel
        panel.create_board()
        first_ids = panel._ids()
        copy_selection(self.editor.circuit, list(self.editor.circuit.components), 3000, 0)
        self.editor.sim = Simulator(self.editor.circuit)
        self.editor.render()
        candidates = panel.detect_architectures()
        self.assertEqual(len(candidates), 2)
        second_row = next(index for index, item in enumerate(candidates)
                          if item.ids["control"] != first_ids["control"])
        panel.arch_candidates.setCurrentRow(second_row)
        panel.bind_architecture()
        self.assertEqual(len(get_bindings(self.editor.circuit)), 2)
        second_ids = get_active_binding(self.editor.circuit)["ids"]
        panel.source.setPlainText("MOV R0, 12\nHLT\n")
        panel.load_to_rom()
        panel.step_mode("instruction")
        self.assertEqual(self.editor.circuit.components[second_ids["registers"]].state["words"]["0"], 12)
        self.assertEqual(self.editor.circuit.components[first_ids["registers"]].state.get("words", {}), {})
        panel.arch_bindings.setCurrentIndex(0)
        self.assertEqual(get_active_binding(self.editor.circuit)["ids"]["control"], first_ids["control"])
        self.assertFalse(self.editor.circuit.components[second_ids["clock"]].params["running"])
        panel.step_mode("instruction")
        self.assertEqual(self.editor.circuit.components[first_ids["registers"]].state["words"]["0"], 10)
        panel.reset()
        self.assertEqual(self.editor.circuit.components[first_ids["registers"]].state, {})
        self.assertEqual(self.editor.circuit.components[second_ids["registers"]].state["words"]["0"], 12)

    def test_gui_load_bin_into_selected_rom(self):
        panel = self.editor.cpu_panel
        panel.create_board()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "program.bin"
            path.write_bytes(bytes((0x10, 0, 0x2A, 0x01)))
            with patch("cpu_view.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                panel.load_image("bin")
        ids = panel._ids()
        self.assertEqual(self.editor.circuit.components[ids["rom"]].params["contents"]["2"], 42)
        self.assertEqual(panel.machine.rowCount(), 16)
        panel._machine_line(0, 0)  # Raw image has no source line.
        panel.step_mode("instruction")
        self.assertEqual(self.editor.circuit.components[ids["registers"]].state["words"]["0"], 42)


if __name__ == "__main__":
    unittest.main()

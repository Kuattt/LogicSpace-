import os
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtCore import QPoint, QPointF, Qt, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from component_library import ComponentLibrary
from engine import Circuit, Simulator
from library_manager import LibraryManager
from main import COMPONENT_MIME, Editor


class LibraryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_project_a_to_library_to_dragged_project_b(self):
        with tempfile.TemporaryDirectory() as directory:
            library = ComponentLibrary(Path(directory) / "library")
            project_a = Editor()
            project_a.global_library = library
            project_a.show()
            source = project_a.circuit.add("INPUT", params={"label": "A"})
            gate = project_a.circuit.add("NOT")
            terminal = project_a.circuit.add("OUTPUT", params={"label": "Y"})
            project_a.circuit.connect(source.id, "Q", gate.id, "A")
            project_a.circuit.connect(gate.id, "Q", terminal.id, "A")
            project_a.render()
            for component_id in (source.id, gate.id, terminal.id):
                project_a.component_items[component_id].setSelected(True)
            save_dialog = MagicMock()
            save_dialog.exec.return_value = QDialog.Accepted
            save_dialog.name.text.return_value = "Invert"
            save_dialog.project.isChecked.return_value = True
            save_dialog.global_library.isChecked.return_value = True
            save_dialog.category.currentText.return_value = "Custom"
            save_dialog.description.toPlainText.return_value = "One bit inverter"
            with patch("main.SaveBlockDialog", return_value=save_dialog):
                project_a.save_selection_block()
            self.assertIn("Invert", project_a.circuit.blocks)
            entry = library.list_entries()[0]
            project_a.circuit.save(Path(directory) / "project-a.json")
            project_a.dirty = False
            project_a.close()

            project_b = Editor()
            project_b.global_library = library
            project_b.populate_library()
            project_b.show()
            self.app.processEvents()
            names = [project_b.library.topLevelItem(i).text(0) for i in range(project_b.library.topLevelItemCount())]
            self.assertIn("Library · Custom", names)
            manager = LibraryManager(project_b, library)
            self.assertEqual(manager.items.count(), 1)
            manager.close()
            mime = QMimeData()
            mime.setData(COMPONENT_MIME, ("LIB:" + entry["id"]).encode())
            enter = QDragEnterEvent(QPoint(200, 150), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
            project_b.canvas.dragEnterEvent(enter)
            self.assertTrue(enter.isAccepted())
            self.assertIsNotNone(project_b.canvas.drag_ghost)
            drop = QDropEvent(QPointF(200, 150), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
            project_b.canvas.dropEvent(drop)
            self.assertEqual(len(project_b.circuit.components), 1)
            block = next(iter(project_b.circuit.components.values()))
            self.assertEqual(block.kind, "BLOCK:Invert")
            driver = project_b.circuit.add("CONST", params={"value": 1})
            lamp = project_b.circuit.add("LED")
            project_b.circuit.connect(driver.id, "Q", block.id, "A")
            project_b.circuit.connect(block.id, "Y", lamp.id, "A")
            project_b.render()
            project_b.speed.setValue(20)
            project_b.toggle_run()
            QTest.qWait(90)
            project_b.toggle_run()
            self.assertGreater(project_b.circuit.tick, 0)
            self.assertEqual(project_b.sim.inputs[lamp.id]["A"], 0)
            saved = Path(directory) / "project-b.json"
            project_b.circuit.save(saved)
            project_b.dirty = False
            project_b.close()
            library.delete(entry["id"])
            reopened = Editor()
            reopened.global_library = library
            with patch("main.QFileDialog.getOpenFileName", return_value=(str(saved), "LogicSpace circuits (*.json)")):
                reopened.open_file()
            self.assertEqual(reopened.sim.inputs[lamp.id]["A"], 0)
            reopened.dirty = False
            reopened.close()

    def test_global_only_save_does_not_change_current_project(self):
        with tempfile.TemporaryDirectory() as directory:
            editor = Editor()
            editor.global_library = ComponentLibrary(Path(directory) / "library")
            source = editor.circuit.add("INPUT")
            target = editor.circuit.add("OUTPUT")
            editor.circuit.connect(source.id, "Q", target.id, "A")
            editor.render()
            editor.component_items[source.id].setSelected(True)
            editor.component_items[target.id].setSelected(True)
            before = editor.circuit.to_dict()
            dialog = MagicMock()
            dialog.exec.return_value = QDialog.Accepted
            dialog.name.text.return_value = "Wire"
            dialog.project.isChecked.return_value = False
            dialog.global_library.isChecked.return_value = True
            dialog.category.currentText.return_value = "Custom"
            dialog.description.toPlainText.return_value = ""
            with patch("main.SaveBlockDialog", return_value=dialog):
                editor.save_selection_block()
            self.assertEqual(editor.circuit.to_dict(), before)
            self.assertEqual(len(editor.global_library.list_entries()), 1)
            editor.dirty = False
            editor.close()


if __name__ == "__main__":
    unittest.main()

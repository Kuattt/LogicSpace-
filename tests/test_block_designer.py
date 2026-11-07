import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtCore import QPoint, QPointF, Qt, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QDialog

from block_visuals import terminal_positions
from component_library import ComponentLibrary, block_definition_from_circuit
from designer_model import DesignerModel
from engine import Circuit, Simulator
from main import COMPONENT_MIME, Editor, component_preview


def xor_document():
    model = DesignerModel(name="XOR2")
    a = model.add_terminal("A", "INPUT")
    b = model.add_terminal("B", "INPUT")
    y = model.add_terminal("Y", "OUTPUT")
    gate = model.circuit.add("XOR")
    model.circuit.connect(a.id, "Q", gate.id, "A")
    model.circuit.connect(b.id, "Q", gate.id, "B")
    model.circuit.connect(gate.id, "Q", y.id, "A")
    return model


class DesignerModelTests(unittest.TestCase):
    def test_empty_add_remove_and_wiring_validation(self):
        model = DesignerModel()
        with self.assertRaisesRegex(ValueError, "INPUT and one OUTPUT"):
            model.validate()
        a = model.add_terminal("A", "INPUT")
        y = model.add_terminal("Y", "OUTPUT")
        with self.assertRaisesRegex(ValueError, "Connect external output"):
            model.validate()
        model.circuit.connect(a.id, "Q", y.id, "A")
        self.assertEqual(model.validate()["inputs"], ["A"])
        model.remove_terminal(a.id)
        self.assertEqual(len(model.circuit.wires), 0)

    def test_rename_width_order_side_and_preview_positions(self):
        model = DesignerModel(name="Bus")
        a = model.add_terminal("A", "INPUT")
        y = model.add_terminal("Y", "OUTPUT")
        model.circuit.connect(a.id, "Q", y.id, "A")
        model.configure_terminal(a.id, name="DATA", width=2, side="TOP", order=3, description="payload")
        model.configure_terminal(y.id, width=2, side="BOTTOM", order=1)
        # Existing one-bit wires are remapped to bit zero; connect bit one too.
        self.assertEqual(next(iter(model.circuit.wires.values())).source_pin, "Q0")
        self.assertEqual(next(iter(model.circuit.wires.values())).target_pin, "A0")
        model.circuit.connect(a.id, "Q1", y.id, "A1")
        definition = model.validate()
        self.assertEqual(definition["inputs"], ["DATA0", "DATA1"])
        positions = terminal_positions(definition, 180, 120)
        self.assertEqual(positions["input", "DATA0"][1], "TOP")
        self.assertEqual(positions["output", "Y0"][1], "BOTTOM")
        self.assertEqual(definition["designer"]["terminals"]["DATA1"]["description"], "payload")
        self.assertEqual(model.test({"DATA0": 1, "DATA1": 0}), {"Y0": 1, "Y1": 0})
        with self.assertRaisesRegex(ValueError, "Disconnect wires"):
            model.configure_terminal(a.id, width=1)
        self.assertEqual(model.circuit.components[a.id].params["width"], 2)

    def test_unique_names_and_valid_width(self):
        model = DesignerModel()
        a = model.add_terminal("A", "INPUT")
        model.add_terminal("Y", "OUTPUT")
        with self.assertRaisesRegex(ValueError, "unique"):
            model.configure_terminal(a.id, name="Y")
        with self.assertRaises(ValueError):
            model.configure_terminal(a.id, width=9)
        model.configure_terminal(a.id, width=2)
        model.add_terminal("A0", "INPUT")
        with self.assertRaisesRegex(ValueError, "External pin name A0"):
            model.validate()

    def test_xor_all_inputs_and_original_state_preserved(self):
        model = xor_document()
        original = deepcopy(model.circuit.to_dict())
        expected = ((0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0))
        for a, b, y in expected:
            self.assertEqual(model.test({"A": a, "B": b}), {"Y": y})
        self.assertEqual(model.circuit.to_dict(), original)

    def test_appearance_and_legacy_open(self):
        model = xor_document()
        model.appearance.update(body_color="#345678", width=225, height=150,
                                label="X2", short_description="exclusive or")
        definition = model.validate()
        self.assertEqual(definition["designer"]["appearance"]["label"], "X2")
        legacy = block_definition_from_circuit(model.circuit)
        reopened = DesignerModel.from_definition(legacy, "Old XOR")
        self.assertEqual(reopened.test({"A": 1, "B": 0}), {"Y": 1})

    def test_nested_block_and_recursive_rejection(self):
        inner = xor_document()
        outer = DesignerModel(name="Outer")
        outer.circuit.blocks["XOR2"] = inner.validate()
        a = outer.add_terminal("A", "INPUT")
        b = outer.add_terminal("B", "INPUT")
        y = outer.add_terminal("Y", "OUTPUT")
        nested = outer.circuit.add("BLOCK:XOR2")
        outer.circuit.connect(a.id, "Q", nested.id, "A")
        outer.circuit.connect(b.id, "Q", nested.id, "B")
        outer.circuit.connect(nested.id, "Y", y.id, "A")
        self.assertEqual(outer.test({"A": 1, "B": 0}), {"Y": 1})
        outer.name = "XOR2"
        with self.assertRaisesRegex(ValueError, "Recursive"):
            outer.validate()


class DesignerUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.editor = Editor()
        self.editor.global_library = ComponentLibrary(Path(self.temp.name) / "library")
        self.editor.show()
        self.designer = self.editor.new_block_designer()
        self.app.processEvents()

    def tearDown(self):
        self.designer.dirty = False
        self.designer.load_appearance()
        self.designer.refresh_terminals()
        self.designer.close()
        self.editor.dirty = False
        self.editor.close()
        self.temp.cleanup()

    def make_xor(self):
        for kind in ("INPUT", "INPUT", "OUTPUT"):
            self.designer.add_terminal(kind)
        terminals = self.designer.model.terminals()
        for component, name in zip(terminals, ("A", "B", "Y")):
            self.designer.model.configure_terminal(component.id, name=name)
        gate = self.designer.circuit.add("XOR")
        self.designer.circuit.connect(terminals[0].id, "Q", gate.id, "A")
        self.designer.circuit.connect(terminals[1].id, "Q", gate.id, "B")
        self.designer.circuit.connect(gate.id, "Q", terminals[2].id, "A")
        self.designer.model.name = "XOR2"
        self.designer.render(); self.designer.refresh_terminals(); self.designer.load_appearance()

    def test_window_terminal_tools_undo_redo(self):
        self.assertEqual(self.designer.sidebar_tabs.count(), 2)
        self.designer.add_terminal("INPUT")
        self.assertEqual(len(self.designer.model.terminals()), 1)
        self.designer.undo()
        self.assertEqual(len(self.designer.model.terminals()), 0)
        self.designer.redo()
        self.assertEqual(len(self.designer.model.terminals()), 1)

    def test_canvas_placed_terminal_is_editable(self):
        self.designer.place_component("INPUT", QPointF(-100, 80))
        terminal = self.designer.model.terminals()[0]
        self.assertEqual(terminal.params["label"], "IN1")
        self.assertEqual(self.designer.terminal_list.count(), 1)
        self.designer.circuit.remove(terminal.id)
        self.designer.render()
        self.assertEqual(self.designer.terminal_list.count(), 0)

    def test_terminal_preview_updates_before_apply(self):
        self.designer.add_terminal("INPUT")
        self.designer.term_name.setText("BUS")
        self.designer.term_width.setValue(3)
        self.designer.term_side.setCurrentText("TOP")
        spec = self.designer.terminal_draft_spec()
        self.assertEqual(spec["inputs"], ["BUS0", "BUS1", "BUS2"])
        self.assertEqual(spec["designer"]["terminals"]["BUS2"]["side"], "TOP")
        self.assertEqual(self.designer.model.terminals()[0].params["label"], "IN1")

    def test_save_project_global_version_and_independent_snapshot(self):
        self.make_xor()
        dialog = MagicMock()
        dialog.exec.return_value = QDialog.Accepted
        dialog.name.text.return_value = "XOR2"
        dialog.project.isChecked.return_value = True
        dialog.global_library.isChecked.return_value = True
        dialog.category.currentText.return_value = "Custom"
        dialog.description.toPlainText.return_value = "Test XOR"
        with patch("block_designer.SaveBlockDialog", return_value=dialog):
            self.assertTrue(self.designer.save())
        self.assertFalse(self.designer._has_drafts())
        self.assertIn("XOR2", self.editor.circuit.blocks)
        entry = self.editor.global_library.list_entries()[0]
        project = Circuit()
        name = self.editor.global_library.install_into(project, entry["id"])
        old = deepcopy(project.blocks[name])
        edited = self.editor.open_library_designer(entry["id"])
        edited.model.appearance["body_color"] = "#8899aa"
        edited.load_appearance()
        edited.dirty = True
        update_dialog = MagicMock()
        update_dialog.exec.return_value = QDialog.Accepted
        update_dialog.name.text.return_value = "XOR2"
        update_dialog.project.isChecked.return_value = False
        update_dialog.global_library.isChecked.return_value = True
        update_dialog.category.currentText.return_value = "Custom"
        update_dialog.description.toPlainText.return_value = "Test XOR"
        with patch("block_designer.SaveBlockDialog", return_value=update_dialog):
            self.assertTrue(edited.save())
        self.assertEqual(self.editor.global_library.get(entry["id"])["version"], 2)
        self.assertEqual(project.blocks[name], old)
        edited.dirty = False; edited.close()

    def test_convert_selection_opens_editable_copy(self):
        a = self.editor.circuit.add("INPUT")
        y = self.editor.circuit.add("OUTPUT")
        self.editor.circuit.connect(a.id, "Q", y.id, "A")
        self.editor.render()
        self.editor.component_items[a.id].setSelected(True)
        self.editor.component_items[y.id].setSelected(True)
        original = deepcopy(self.editor.circuit.to_dict())
        converted = self.editor.design_selection_as_block()
        self.assertIsNotNone(converted)
        self.assertEqual(len(converted.model.terminals()), 2)
        self.assertEqual(self.editor.circuit.to_dict(), original)
        converted.dirty = False; converted.close()

    def test_designed_library_drag_simulation_and_reopen(self):
        self.make_xor()
        entry = self.editor.global_library.save("XOR2", self.designer.model.validate())
        other = Editor()
        other.global_library = self.editor.global_library
        other.populate_library()
        other.show()
        self.app.processEvents()
        preview = component_preview(other, "LIB:" + entry["id"])
        self.assertEqual(preview.width(), 210)
        mime = QMimeData()
        mime.setData(COMPONENT_MIME, ("LIB:" + entry["id"]).encode())
        enter = QDragEnterEvent(QPoint(200, 150), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        other.canvas.dragEnterEvent(enter)
        self.assertTrue(enter.isAccepted())
        drop = QDropEvent(QPointF(200, 150), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        other.canvas.dropEvent(drop)
        block = next(c for c in other.circuit.components.values() if c.kind.startswith("BLOCK:"))
        self.assertTrue(other.component_items[block.id].designed_block)
        a = other.circuit.add("INPUT", params={"value": 1})
        b = other.circuit.add("INPUT", params={"value": 0})
        lamp = other.circuit.add("LED")
        other.circuit.connect(a.id, "Q", block.id, "A")
        other.circuit.connect(b.id, "Q", block.id, "B")
        other.circuit.connect(block.id, "Y", lamp.id, "A")
        other.sim.evaluate()
        self.assertEqual(other.sim.inputs[lamp.id]["A"], 1)
        path = Path(self.temp.name) / "other-project.json"
        other.circuit.save(path)
        reopened = Circuit.load(path)
        self.editor.global_library.delete(entry["id"])
        self.assertEqual(Simulator(reopened).inputs[lamp.id]["A"], 1)
        other.dirty = False; other.close()


if __name__ == "__main__":
    unittest.main()

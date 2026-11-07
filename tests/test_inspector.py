"""Inline component configuration in the right Inspector."""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication

from main import Editor


class InspectorTests(unittest.TestCase):
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

    def select(self, component):
        self.editor.render()
        self.editor.component_items[component.id].setSelected(True)
        self.app.processEvents()

    def test_select_shows_settings_and_apply_preserves_selection(self):
        gate = self.editor.circuit.add("AND", params={"width": 4})
        self.select(gate)
        self.assertTrue(self.editor.config_panel.isVisible())
        form = self.editor.settings_form
        self.assertEqual(form.controls["width"].value(), 4)
        form.controls["width"].setValue(6)
        self.editor.refresh()
        self.assertIs(self.editor.settings_form, form)
        self.assertEqual(form.controls["width"].value(), 6)
        self.editor.apply_component_settings()
        self.assertEqual(self.editor.circuit.components[gate.id].params["width"], 6)
        self.assertEqual(self.editor.selected_components(), [gate.id])
        self.assertEqual(self.editor.settings_form.controls["width"].value(), 6)
        self.editor.undo()
        self.assertEqual(self.editor.circuit.components[gate.id].params["width"], 4)

    def test_invalid_width_keeps_connected_pins(self):
        source = self.editor.circuit.add("INPUT", params={"width": 4, "value": 0})
        target = self.editor.circuit.add("OUTPUT", params={"width": 4})
        wire = self.editor.circuit.connect(source.id, "Q3", target.id, "A3")
        self.select(source)
        self.editor.settings_form.controls["width"].setValue(2)
        self.editor.apply_component_settings()
        self.assertEqual(self.editor.circuit.components[source.id].params["width"], 4)
        self.assertIn(wire.id, self.editor.circuit.wires)
        self.assertTrue(self.editor.config_error.isVisible())

    def test_input_value_updates_simulation(self):
        source = self.editor.circuit.add("INPUT", params={"value": 0})
        gate = self.editor.circuit.add("NOT")
        self.editor.circuit.connect(source.id, "Q", gate.id, "A")
        self.select(source)
        self.editor.settings_form.controls["value"].setValue(1)
        self.editor.apply_component_settings()
        self.assertEqual(self.editor.sim.outputs[gate.id, "Q"], 0)
        self.assertEqual(self.editor.selected_components(), [source.id])

    def test_double_click_toggle_refreshes_input_field(self):
        source = self.editor.circuit.add("INPUT", params={"value": 0})
        self.select(source)
        self.editor.toggle_input(source.id)
        self.assertEqual(self.editor.settings_form.controls["value"].value(), 1)

    def test_invalid_rom_json_stays_in_form(self):
        rom = self.editor.circuit.add("ROM")
        self.select(rom)
        form = self.editor.settings_form
        form.contents.setPlainText("{bad json")
        self.editor.apply_component_settings()
        self.assertIs(self.editor.settings_form, form)
        self.assertTrue(self.editor.config_error.isVisible())
        self.assertNotIn("contents", self.editor.circuit.components[rom.id].params)


if __name__ == "__main__":
    unittest.main()

"""The new panels operate on the live editor and persist through project JSON."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication, QMessageBox

from fpga_model import PROFILE_FORMAT
from main import Editor


class Panels25(unittest.TestCase):
    def test_hdl_canvas_import_uses_wired_clock_generator(self):
        panel = self.editor.hdl_panel
        panel.code.setPlainText("module d(input clk,input d,output logic q); "
                                "always_ff @(posedge clk) q<=d; endmodule")
        panel.import_circuit()
        clock = next(c for c in self.editor.circuit.components.values() if c.kind == "Clock Generator")
        flip = next(c for c in self.editor.circuit.components.values() if c.kind == "D Flip-Flop")
        self.assertTrue(any(w.source == clock.id and w.target == flip.id and w.target_pin == "CLK"
                            for w in self.editor.circuit.wires.values()))
        data = next(c for c in self.editor.circuit.components.values() if c.kind == "INPUT")
        data.params["value"] = 1
        self.editor.sim.evaluate()
        self.editor.step(); self.editor.step()
        self.assertEqual(self.editor.sim.outputs[flip.id, "Q"], 1)

    def test_hdl_ram_import_is_editable_and_visible_in_memory_inspector(self):
        source = (Path(__file__).resolve().parents[1] / "examples" / "hdl25" /
                  "ram_module.sv").read_text(encoding="utf-8")
        panel = self.editor.hdl_panel
        panel.code.setPlainText(source)
        panel.import_circuit()
        ram = next(c for c in self.editor.circuit.components.values() if c.kind == "RAM")
        self.assertEqual(ram.params["init"]["1"], 52)
        self.editor.show_memory_inspector()
        self.app.processEvents()
        self.assertEqual(self.editor.memory_panel.component().id, ram.id)
        self.assertEqual(self.editor.memory_panel.table.item(1, 1).text(), "0x34")

    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = Editor(); self.editor.show(); self.app.processEvents()

    def tearDown(self):
        self.editor.timer.stop(); self.editor.dirty = False
        self.editor.hdl_panel.dirty = False
        self.editor.close()
        self.app.processEvents()

    def test_fpga_panel_saves_and_restores_workspace(self):
        panel = self.editor.fpga_panel
        self.editor.show_fpga_workflow()
        self.app.processEvents()
        self.assertTrue(self.editor.fpga_dock.isVisible())
        panel.name.setText("Logic gate")
        panel.top.setText("gate")
        panel.workspace["files"] = {"gate.v": "module gate(input a,input b,output y); assign y=a&b; endmodule"}
        panel.workspace["profile"] = {"format": PROFILE_FORMAT, "version": 1,
                                      "manufacturer": "Unknown", "family": "Unknown",
                                      "device": "Unknown", "package": "Unknown",
                                      "source": "User test fixture", "pins": ["P1", "P2", "P3"],
                                      "clock_pins": [], "constraint_format": "ice40-pcf"}
        panel.pins.setPlainText('{"a":"P1","b":"P2","y":"P3"}')
        self.assertIsNotNone(panel.validate())
        panel.save_workspace()
        saved = self.editor.circuit.to_dict()
        self.assertEqual(saved["fpga_workspace"]["top"], "gate")
        self.editor.circuit.fpga_workspace = None
        panel.sync_circuit()
        self.assertEqual(panel.top.text(), "")

    def test_memory_inspector_edits_ram_and_records_history(self):
        ram = self.editor.circuit.add("RAM", params={"address_bits": 2, "data_bits": 2,
                                                    "read_mode": "async"})
        self.editor.render()
        self.editor.show_memory_inspector(); self.app.processEvents()
        panel = self.editor.memory_panel
        self.assertEqual(panel.component().id, ram.id)
        panel.address.setValue(1); panel.value.setValue(3)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            panel.write_value()
        self.assertEqual(self.editor.circuit.components[ram.id].state["memory"]["1"], 3)
        self.assertIn("0x3", panel.table.item(1, 1).text().lower())
        self.assertIn("[0x01]", panel.history.toPlainText())
        latest = next(reversed(self.editor.time_history.branch.states.values()))
        self.assertIn(ram.id, self.editor.time_history.snapshots[latest].states)


if __name__ == "__main__": unittest.main()

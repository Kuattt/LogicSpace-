"""Momentary signal forcing and destructive canvas tool behavior."""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from engine import Circuit, Simulator
from main import Editor


class ForcePinTests(unittest.TestCase):
    def test_output_force_propagates_and_restores_without_changing_circuit(self):
        circuit = Circuit()
        source = circuit.add("INPUT", params={"value": 0})
        target = circuit.add("OUTPUT")
        circuit.connect(source.id, "Q", target.id, "A")
        sim = Simulator(circuit)
        sim.force_pin(source.id, "Q", "output", 1)
        self.assertEqual(sim.outputs[source.id, "Q"], 1)
        self.assertEqual(sim.inputs[target.id]["A"], 1)
        self.assertEqual(source.params["value"], 0)
        self.assertNotIn("forced_outputs", circuit.to_dict())
        sim.release_pin(source.id, "Q", "output")
        self.assertEqual(sim.inputs[target.id]["A"], 0)

    def test_input_force_overrides_receiver_only_and_survives_step(self):
        circuit = Circuit()
        source = circuit.add("INPUT", params={"value": 1})
        gate = circuit.add("NOT")
        circuit.connect(source.id, "Q", gate.id, "A")
        sim = Simulator(circuit)
        sim.force_pin(gate.id, "A", "input", 0)
        self.assertEqual(sim.outputs[source.id, "Q"], 1)
        self.assertEqual(sim.inputs[gate.id]["A"], 0)
        self.assertEqual(sim.outputs[gate.id, "Q"], 1)
        sim.step()
        self.assertEqual(sim.outputs[gate.id, "Q"], 1)
        sim.release_pin(gate.id, "A", "input")
        self.assertEqual(sim.outputs[gate.id, "Q"], 0)

    def test_multibit_pin_force_is_individual_and_reset_clears_it(self):
        circuit = Circuit()
        source = circuit.add("INPUT", params={"width": 3, "value": 0b101})
        sim = Simulator(circuit)
        sim.force_pin(source.id, "Q1", "output", 1)
        self.assertEqual([sim.outputs[source.id, f"Q{i}"] for i in range(3)], [1, 1, 1])
        sim.reset()
        self.assertEqual([sim.outputs[source.id, f"Q{i}"] for i in range(3)], [1, 0, 1])
        self.assertFalse(sim.forced_outputs)

    def test_invalid_force_is_rejected(self):
        circuit = Circuit()
        source = circuit.add("INPUT")
        sim = Simulator(circuit)
        with self.assertRaises(ValueError):
            sim.force_pin(source.id, "Q", "output", 2)
        with self.assertRaises(ValueError):
            sim.force_pin(source.id, "A", "input", 1)


class CanvasToolTests(unittest.TestCase):
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

    def pin_point(self, component_id, direction, pin):
        item = self.editor.component_items[component_id].pin_items[direction, pin]
        return self.editor.canvas.mapFromScene(item.scenePos())

    def test_flip_probe_hold_release_and_escape(self):
        source = self.editor.circuit.add("INPUT", params={"value": 0})
        target = self.editor.circuit.add("LED", x=300)
        self.editor.circuit.connect(source.id, "Q", target.id, "A")
        self.editor.render()
        self.editor.set_tool("flip")
        point = self.pin_point(source.id, "output", "Q")
        QTest.mousePress(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual(self.editor.sim.inputs[target.id]["A"], 1)
        self.assertIsNotNone(self.editor.canvas.held_force)
        QTest.mouseRelease(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual(self.editor.sim.inputs[target.id]["A"], 0)
        self.assertIsNone(self.editor.canvas.held_force)
        self.assertEqual(source.params["value"], 0)
        self.editor.set_tool(None)
        self.assertFalse(any(button.isChecked() for button in self.editor.tool_buttons.values()))

    def test_flip_probe_on_connected_input(self):
        source = self.editor.circuit.add("INPUT", params={"value": 1})
        gate = self.editor.circuit.add("NOT", x=300)
        self.editor.circuit.connect(source.id, "Q", gate.id, "A")
        self.editor.render()
        self.editor.set_tool("flip")
        point = self.pin_point(gate.id, "input", "A")
        QTest.mousePress(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual(self.editor.sim.inputs[gate.id]["A"], 0)
        self.assertEqual(self.editor.sim.outputs[gate.id, "Q"], 1)
        QTest.mouseRelease(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual(self.editor.sim.inputs[gate.id]["A"], 1)

    def test_switching_tools_releases_held_force(self):
        source = self.editor.circuit.add("INPUT", params={"value": 0})
        self.editor.render()
        self.editor.set_tool("flip")
        point = self.pin_point(source.id, "output", "Q")
        QTest.mousePress(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual(self.editor.sim.outputs[source.id, "Q"], 1)
        self.editor.set_tool("cut")
        self.assertEqual(self.editor.sim.outputs[source.id, "Q"], 0)
        self.assertIsNone(self.editor.canvas.held_force)
        QTest.mouseRelease(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)

    def test_probe_ignores_unknown_signal(self):
        source = self.editor.circuit.add("INPUT", params={"value": None})
        self.editor.render()
        self.editor.set_tool("flip")
        point = self.pin_point(source.id, "output", "Q")
        QTest.mousePress(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)
        self.assertIsNone(self.editor.canvas.held_force)
        self.assertIsNone(self.editor.sim.outputs[source.id, "Q"])
        QTest.mouseRelease(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)

    def test_eraser_component_and_undo(self):
        component = self.editor.circuit.add("AND")
        self.editor.render()
        self.editor.set_tool("erase")
        body = self.editor.component_items[component.id]
        point = self.editor.canvas.mapFromScene(body.mapToScene(78, 50))
        QTest.mouseClick(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)
        self.assertNotIn(component.id, self.editor.circuit.components)
        self.editor.undo()
        self.assertIn(component.id, self.editor.circuit.components)

    def test_eraser_removes_single_wire(self):
        source = self.editor.circuit.add("INPUT")
        target = self.editor.circuit.add("OUTPUT", x=310)
        wire = self.editor.circuit.connect(source.id, "Q", target.id, "A")
        self.editor.render()
        self.editor.set_tool("erase")
        points = self.editor.raw_wire_points(wire)
        point = self.editor.canvas.mapFromScene((points[0] + points[-1]) / 2)
        QTest.mouseClick(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)
        self.assertNotIn(wire.id, self.editor.circuit.wires)
        self.assertIn(source.id, self.editor.circuit.components)
        self.assertIn(target.id, self.editor.circuit.components)

    def test_cut_one_wire_keeps_other_branch_and_undo(self):
        source = self.editor.circuit.add("INPUT")
        left = self.editor.circuit.add("OUTPUT", x=310)
        right = self.editor.circuit.add("OUTPUT", x=310, y=160)
        first = self.editor.circuit.connect(source.id, "Q", left.id, "A")
        second = self.editor.circuit.connect(source.id, "Q", right.id, "A")
        self.editor.render()
        self.editor.set_tool("cut")
        points = self.editor.raw_wire_points(second)
        midpoint = (points[-2] + points[-1]) / 2
        point = self.editor.canvas.mapFromScene(midpoint)
        QTest.mouseClick(self.editor.canvas.viewport(), Qt.LeftButton, pos=point)
        self.assertNotIn(second.id, self.editor.circuit.wires)
        self.assertIn(first.id, self.editor.circuit.wires)
        self.editor.undo()
        self.assertIn(second.id, self.editor.circuit.wires)


if __name__ == "__main__":
    unittest.main()

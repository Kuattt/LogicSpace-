"""Native buses exercise the existing scalar simulator and project integrations."""
import json
import os
import sys
import unittest
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF

from component_library import block_definition_from_circuit
from engine import BusWire, Circuit, Simulator, bus_ports, copy_selection
from main import Editor, format_bus
from testbench_model import TestbenchSession, new_testbench, signal_ref_dict, validate_package
from timing_model import SignalRef, TimingHistory
from timing_view import WaveformView
from tracing_model import TraceAnalyzer, TraceFrame, value_text
from time_travel_model import SimulationHistory


def bits(sim, cid, prefix, width):
    return tuple(sim.outputs[cid, f"{prefix}{index}"] for index in range(width))


def chain(width, value):
    circuit = Circuit()
    source = circuit.add("Bus Input", params={"width": width, "value": value})
    splitter = circuit.add("Bus Splitter", params={"width": width})
    merger = circuit.add("Bus Merger", params={"width": width})
    probe = circuit.add("Bus Probe", params={"width": width})
    first = circuit.connect_bus(source.id, "Q", splitter.id, "D")
    for index in range(width):
        circuit.connect(splitter.id, f"Q{index}", merger.id, f"D{index}")
    last = circuit.connect_bus(merger.id, "Q", probe.id, "D")
    return circuit, source, splitter, merger, probe, first, last


class BusEngineTests(unittest.TestCase):
    def test_2_4_8_bit_round_trip_and_order(self):
        for width, value in ((2, 2), (4, 11), (8, 0xB6)):
            with self.subTest(width=width):
                circuit, source, splitter, merger, probe, first, last = chain(width, value)
                sim = Simulator(circuit)
                expected = tuple((value >> index) & 1 for index in range(width))
                self.assertEqual(bits(sim, splitter.id, "Q", width), expected)
                self.assertEqual(bits(sim, merger.id, "Q", width), expected)
                self.assertEqual(tuple(sim.inputs[probe.id][f"D{i}"] for i in range(width)), expected)
                self.assertEqual((first.width, last.width), (width, width))
                self.assertEqual(circuit.validate(), [])

    def test_branching_and_per_bit_taps(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 8, "value": 0x81})
        a, b = (circuit.add("Bus Probe", params={"width": 8}) for _ in range(2))
        selector = circuit.add("Bit Selector", params={"width": 8, "index": 7})
        led = circuit.add("LED")
        circuit.connect_bus(source.id, "Q", a.id, "D")
        circuit.connect_bus(source.id, "Q", b.id, "D")
        circuit.connect_bus(source.id, "Q", selector.id, "D")
        circuit.connect(selector.id, "Q", led.id, "A")
        sim = Simulator(circuit)
        self.assertEqual(sim.inputs[a.id], sim.inputs[b.id])
        self.assertEqual(sim.outputs[selector.id, "Q"], 1)
        self.assertEqual(sim.inputs[led.id]["A"], 1)

    def test_unknown_unconnected_merger_and_invalid_index(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 4, "_bit_values": [1, None, 0, 1]})
        splitter = circuit.add("Bus Splitter", params={"width": 4, "expose": [0, 1, 3]})
        merger = circuit.add("Bus Merger", params={"width": 4})
        circuit.connect_bus(source.id, "Q", splitter.id, "D")
        for index in (0, 1, 3):
            circuit.connect(splitter.id, f"Q{index}", merger.id, f"D{index}")
        sim = Simulator(circuit)
        self.assertEqual(bits(sim, merger.id, "Q", 4), (1, None, None, 1))
        self.assertTrue(any("D2" in warning for warning in sim.warnings))
        with self.assertRaisesRegex(ValueError, "outside"):
            circuit.add("Bit Selector", params={"width": 4, "index": 4})
        with self.assertRaisesRegex(ValueError, "unique"):
            circuit.add("Bus Splitter", params={"width": 4, "expose": [1, 1]})

    def test_width_and_driver_validation(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 4})
        target = circuit.add("Bus Probe", params={"width": 8})
        with self.assertRaisesRegex(ValueError, "width mismatch"):
            circuit.connect_bus(source.id, "Q", target.id, "D")
        target.params["width"] = 4
        wire = circuit.connect_bus(source.id, "Q", target.id, "D")
        with self.assertRaisesRegex(ValueError, "driver"):
            circuit.connect_bus(source.id, "Q", target.id, "D")
        with self.assertRaisesRegex(ValueError, "driver"):
            circuit.connect(source.id, "Q0", target.id, "D0")
        wire.target_bits[0] = "D1"
        self.assertTrue(any("invalid width or bit mapping" in error for error in circuit.validate()))
        with self.assertRaises(ValueError):
            Circuit.from_dict(circuit.to_dict())

    def test_8_bit_adder_and_register(self):
        circuit = Circuit()
        a = circuit.add("Bus Input", params={"width": 8, "value": 0x3A})
        b = circuit.add("Bus Input", params={"width": 8, "value": 0x17})
        zero = circuit.add("INPUT", params={"value": 0})
        clock = circuit.add("Clock Generator", params={"period": 2})
        adder = circuit.add("Adder", params={"width": 8})
        register = circuit.add("Register", params={"width": 8})
        probe = circuit.add("Bus Probe", params={"width": 8})
        circuit.connect_bus(a.id, "Q", adder.id, "A")
        circuit.connect_bus(b.id, "Q", adder.id, "B")
        circuit.connect(zero.id, "Q", adder.id, "CIN")
        circuit.connect_bus(adder.id, "Q", register.id, "D")
        circuit.connect(clock.id, "Q", register.id, "CLK")
        circuit.connect_bus(register.id, "Q", probe.id, "D")
        sim = Simulator(circuit)
        self.assertEqual(value_text(SignalRef.bus_port(adder.id, "Q", "output").value(sim)), "01010001 (0x51)")
        sim.step(); sim.step()
        self.assertEqual(value_text(SignalRef.bus_port(register.id, "Q", "output").value(sim)), "01010001 (0x51)")
        self.assertEqual(format_bus(SignalRef.bus_port(probe.id, "D", "input").value(sim), "hex"), "0x51")
        self.assertEqual(format_bus(SignalRef.bus_port(probe.id, "D", "input").value(sim)), "01010001")
        self.assertEqual(format_bus(SignalRef.bus_port(probe.id, "D", "input").value(sim), "decimal"), "81")

    def test_json_copy_and_legacy_project(self):
        circuit, source, splitter, merger, probe, first, last = chain(4, 9)
        cloned = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
        self.assertIsInstance(cloned.wires[first.id], BusWire)
        self.assertEqual(cloned.wires[first.id].source_bits, [f"Q{i}" for i in range(4)])
        new_ids = copy_selection(cloned, list(cloned.components))
        self.assertEqual(len(new_ids), 4)
        self.assertEqual(len([wire for wire in cloned.wires.values() if isinstance(wire, BusWire)]), 4)
        self.assertEqual(cloned.validate(), [])
        old = Circuit()
        one, lamp = old.add("INPUT"), old.add("LED")
        old.connect(one.id, "Q", lamp.id, "A")
        restored = Circuit.from_dict(old.to_dict())
        self.assertEqual(type(next(iter(restored.wires.values()))).__name__, "Wire")


class BusIntegrationTests(unittest.TestCase):
    def test_timing_grouped_and_bits(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 4, "value": 0})
        probe = circuit.add("Bus Probe", params={"width": 4})
        wire = circuit.connect_bus(source.id, "Q", probe.id, "D")
        sim = Simulator(circuit)
        history = TimingHistory(limit=10)
        aggregate = SignalRef.wire(wire.id)
        bit = SignalRef.wire_bit(wire.id, 3)
        history.add(aggregate, sim); history.add(bit, sim)
        source.params["value"] = 8
        sim.step(); history.record_step(sim)
        self.assertEqual(history.value_at(aggregate, 1), (0, 0, 0, 1))
        self.assertEqual(history.value_at(bit, 1), 1)
        self.assertEqual(len(history.tracks[aggregate].events), 2)

    def test_tracing_bus_and_bit(self):
        circuit, source, splitter, merger, probe, first, last = chain(4, 9)
        sim = Simulator(circuit)
        analyzer = TraceAnalyzer(circuit, TraceFrame.from_simulator(sim), sim)
        tree = analyzer.backward(SignalRef.wire(last.id))
        self.assertEqual(len(tree.children), 4)
        self.assertIn(first.id, analyzer.connected_wires)
        self.assertIn(last.id, analyzer.connected_wires)
        explanation = "\n".join(analyzer.explain(SignalRef.wire_bit(first.id, 3)))
        self.assertIn("Bus bit 3", explanation)
        self.assertIn("= 1", explanation)
        forward = TraceAnalyzer(circuit, TraceFrame.from_simulator(sim), sim)
        self.assertIn(last.id, forward.connected_wires) if forward.forward(SignalRef.wire(first.id)) else None

    def test_testbench_multibit_and_independence(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 4, "value": 0})
        probe = circuit.add("Bus Probe", params={"width": 4})
        circuit.connect_bus(source.id, "Q", probe.id, "D")
        original = deepcopy(circuit.to_dict())
        bench = new_testbench("Bus values")
        bench["signals"] = [
            {"id": "drive", "role": "drive", "ref": signal_ref_dict(SignalRef.bus_port(source.id, "Q", "output"))},
            {"id": "read", "role": "observe", "ref": signal_ref_dict(SignalRef.bus_port(probe.id, "D", "input"))},
        ]
        bench["steps"] = [
            {"drive": {"drive": 0}, "expect": {"read": 0}},
            {"drive": {"drive": [1, None, 0, 1]}, "expect": {"read": [1, None, 0, 1]}},
            {"drive": {"drive": 5}, "expect": {"read": 5}},
        ]
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual((result.passed, result.failed), (3, 0))
        self.assertEqual(result.observations[1]["read"], (1, None, 0, 1))
        self.assertEqual(circuit.to_dict(), original)
        invalid = deepcopy(bench)
        invalid["steps"][2]["drive"]["drive"] = 16
        with self.assertRaisesRegex(ValueError, "4-bit"):
            validate_package(circuit, {"version": 1, "limits": {"max_testbenches": 1, "max_steps": 10}, "items": [invalid]})

    def test_time_travel_bus_restore_and_compare(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 4, "value": 0})
        probe = circuit.add("Bus Probe", params={"width": 4})
        wire = circuit.connect_bus(source.id, "Q", probe.id, "D")
        sim = Simulator(circuit)
        history = SimulationHistory(sim)
        source.params["value"] = 9
        sim.step(); history.record(sim)
        self.assertEqual(SignalRef.wire(wire.id).value(sim), (1, 0, 0, 1))
        history.navigate(sim, 0)
        self.assertEqual(SignalRef.wire(wire.id).value(sim), (0, 0, 0, 0))
        history.navigate(sim, 1)
        self.assertEqual(SignalRef.wire(wire.id).value(sim), (1, 0, 0, 1))
        differences = history.compare(circuit, history.snapshot_at("main", 0), history.snapshot_at("main", 1))
        self.assertTrue(any(diff.signal_ref == SignalRef.wire(wire.id) and diff.changed
                            for diff in differences))

    def test_custom_block_bus_port(self):
        inner = Circuit()
        terminal_in = inner.add("INPUT", params={"width": 4, "label": "A"})
        terminal_out = inner.add("OUTPUT", params={"width": 4, "label": "Y"})
        inner.connect_bus(terminal_in.id, "Q", terminal_out.id, "A")
        definition = block_definition_from_circuit(inner)
        outer = Circuit()
        outer.blocks["Pass4"] = definition
        source = outer.add("Bus Input", params={"width": 4, "value": 10})
        block = outer.add("BLOCK:Pass4")
        probe = outer.add("Bus Probe", params={"width": 4})
        self.assertEqual(bus_ports(block, outer.blocks)["input"]["A"], ("A0", "A1", "A2", "A3"))
        outer.connect_bus(source.id, "Q", block.id, "A")
        outer.connect_bus(block.id, "Y", probe.id, "D")
        sim = Simulator(outer)
        self.assertEqual(SignalRef.bus_port(probe.id, "D", "input").value(sim), (0, 1, 0, 1))


class BusGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_bus_ports_route_and_copy_paste(self):
        editor = Editor()
        try:
            source = editor.circuit.add("Bus Input", 0, 0, {"width": 4, "value": 5})
            target = editor.circuit.add("Bus Probe", 300, 0, {"width": 4})
            wire = editor.circuit.connect_bus(source.id, "Q", target.id, "D")
            editor.render()
            self.assertTrue(editor.raw_wire_points(wire))
            self.assertIn(("output", "Q"), editor.component_items[source.id].bus_pin_items)
            self.assertIn(("input", "D"), editor.component_items[target.id].bus_pin_items)
            editor.component_items[source.id].setSelected(True)
            editor.component_items[target.id].setSelected(True)
            editor.copy(); editor.paste()
            self.assertEqual(len([w for w in editor.circuit.wires.values() if isinstance(w, BusWire)]), 2)
            self.assertEqual(editor.circuit.validate(), [])
        finally:
            editor.dirty = False
            editor.close()

    def test_click_to_connect_checks_width_and_undo(self):
        editor = Editor()
        try:
            source = editor.circuit.add("Bus Input", 0, 0, {"width": 4})
            target = editor.circuit.add("Bus Probe", 300, 0, {"width": 8})
            editor.render()
            editor.pin_clicked(editor.component_items[source.id].bus_pin_items["output", "Q"])
            editor.pin_clicked(editor.component_items[target.id].bus_pin_items["input", "D"])
            self.assertEqual(len(editor.circuit.wires), 0)
            target.params["width"] = 4
            editor.render()
            editor.pin_clicked(editor.component_items[source.id].bus_pin_items["output", "Q"])
            editor.pin_clicked(editor.component_items[target.id].bus_pin_items["input", "D"])
            self.assertEqual(len(editor.circuit.wires), 1)
            self.assertIsInstance(next(iter(editor.circuit.wires.values())), BusWire)
            editor.undo()
            self.assertEqual(len(editor.circuit.wires), 0)
        finally:
            editor.dirty = False
            editor.close()

    def test_bus_routing_corner_handle(self):
        editor = Editor()
        try:
            source = editor.circuit.add("Bus Input", 0, 0, {"width": 4})
            target = editor.circuit.add("Bus Probe", 400, 160, {"width": 4})
            wire = editor.circuit.connect_bus(source.id, "Q", target.id, "D")
            editor.render()
            item = editor.wire_items[wire.id]
            item.insert_bend(QPointF(260, 120))
            self.assertEqual(len(wire.bends), 1)
            self.assertEqual(len(item.handles), 1)
            item.setSelected(True)
            editor.selection_changed()
            self.assertTrue(item.handles[0].isVisible())
            item.handles[0].setPos(QPointF(280, 140))
            self.assertEqual(wire.bends[0], [280, 140])
            self.assertTrue(editor.raw_wire_points(wire))
        finally:
            editor.dirty = False
            editor.close()

    def test_waveform_zoom_retains_bus_values(self):
        circuit = Circuit()
        source = circuit.add("Bus Input", params={"width": 4, "value": 1})
        sim = Simulator(circuit)
        ref = SignalRef.bus_port(source.id, "Q", "output")
        model = TimingHistory()
        model.add(ref, sim)
        source.params["value"] = 6
        sim.step(); model.record_step(sim)
        view = WaveformView(model)
        try:
            before = model.value_at(ref, 1)
            view.cursor_step = 1
            view.zoom(2)
            self.assertEqual(model.value_at(ref, view.cursor_step), before)
            self.assertGreater(view.pixels_per_step, 30)
            view.grab()  # Exercise grouped waveform painting.
        finally:
            view.close()

    def test_inspector_updates_input_and_blocks_connected_width_change(self):
        editor = Editor()
        try:
            source = editor.circuit.add("Bus Input", 0, 0, {"width": 4, "value": 0})
            probe = editor.circuit.add("Bus Probe", 300, 0, {"width": 4})
            editor.circuit.connect_bus(source.id, "Q", probe.id, "D")
            editor.render()
            editor.component_items[source.id].setSelected(True)
            editor.settings_form.bus_value.setText("0b10X1")
            editor.apply_component_settings()
            self.assertEqual(SignalRef.bus_port(probe.id, "D", "input").value(editor.sim),
                             (1, None, 0, 1))
            editor.settings_form.controls["width"].setCurrentIndex(
                editor.settings_form.controls["width"].findData(8))
            editor.settings_form.bus_value.setText("0b00001001")
            editor.apply_component_settings()
            self.assertEqual(editor.circuit.components[source.id].params["width"], 4)
            self.assertIn("connected bus", editor.config_error.text())
            self.assertEqual(editor.circuit.validate(), [])
        finally:
            editor.dirty = False
            editor.close()


if __name__ == "__main__":
    unittest.main()

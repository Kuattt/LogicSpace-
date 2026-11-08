"""Real parser, netlist, simulator, export, tutorial and GUI checks for HDL 2.4."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication

from component_library import validate_definition
from engine import BusWire, Circuit, Simulator
from hdl_lessons import CustomLessonStore
from hdl_model import (HDLError, export_issues, export_verilog, import_verilog,
                       parse, prepare_import, run_circuit_vectors, run_vectors, validate_hdl)
from hdl_tools import _sandbox, external_availability, export_report, run_external_vectors
from main import Editor
from tutorials import HDL_LESSONS, validate_hdl_lesson


AND = "module gate(input a, input b, output y); assign y = a & b; endmodule"


def vectors(width, operator):
    mask = (1 << width) - 1
    return [{"inputs": {"a": a, "b": b}, "expected": {"y": operator(a, b) & mask}}
            for a, b in ((0, 0), (1, 1), (mask, 1), (mask // 2, mask))]


class ParserTests(unittest.TestCase):
    def test_ast_and_non_ansi_ports(self):
        modules = parse("module m(a,b,y); input a,b; output y; wire t; assign t=a&b; assign y=t; endmodule")
        self.assertEqual(modules["m"].signals["t"], ("wire", 1))
        self.assertEqual(len(modules["m"].assignments), 2)
        ansi = parse("module g(input [3:0] a,b, output [3:0] y); assign y=a&b; endmodule")
        self.assertEqual(ansi["g"].signals["b"], ("input", 4))

    def test_diagnostic_line_and_column(self):
        with self.assertRaises(HDLError) as error:
            import_verilog("module m(input a,output y);\n assign y = a @ 1;\nendmodule")
        self.assertEqual((error.exception.line, error.exception.column), (2, 15))

    def test_unsupported_construct_is_rejected(self):
        for source in ("module m(input a, output y); initial y=a; endmodule",
                       "module m(input a, output y); assign y = 1'bz; endmodule"):
            self.assertTrue(validate_hdl(source))

    def test_width_mismatch_and_missing_driver(self):
        self.assertIn("width", validate_hdl("module m(input [3:0] a,output y); assign y=a; endmodule")[0].lower())
        self.assertIn("driver", validate_hdl("module m(output y); wire t; assign y=t; endmodule")[0].lower())

    def test_recursive_module_rejected(self):
        source = "module m(input a,output y); m u(.a(a),.y(y)); endmodule"
        self.assertIn("Recursive", validate_hdl(source)[0])


class CircuitTests(unittest.TestCase):
    def test_and_truth_table_uses_real_gate(self):
        circuit = import_verilog(AND)
        self.assertIn("AND", {c.kind for c in circuit.components.values()})
        self.assertEqual(len(circuit.wires), 3)
        cases = vectors(1, lambda a, b: a & b)
        self.assertTrue(all(row["passed"] for row in run_vectors(AND, cases)))

    def test_all_bus_widths_and_addition(self):
        for width in (2, 4, 8, 16, 32):
            with self.subTest(width=width):
                source = f"module add(input [{width-1}:0] a,input [{width-1}:0] b,output [{width-1}:0] y); assign y=a+b; endmodule"
                circuit = import_verilog(source)
                self.assertTrue(any(isinstance(w, BusWire) for w in circuit.wires.values()))
                self.assertEqual(circuit.validate(), [])
                self.assertTrue(all(row["passed"] for row in run_vectors(source, vectors(width, lambda a, b: a + b))))

    def test_32_bit_literal(self):
        source = "module m(input [31:0] a,output [31:0] y); assign y=a+32'd1; endmodule"
        self.assertTrue(run_vectors(source, [{"inputs": {"a": 4294967295}, "expected": {"y": 0}}])[0]["passed"])

    def test_multiply_and_divide(self):
        multiply = "module m(input [3:0] a,input [3:0] b,output [3:0] y); assign y=a*b; endmodule"
        divide = "module m(input [3:0] a,input [3:0] b,output [3:0] y); assign y=a/b; endmodule"
        self.assertTrue(run_vectors(multiply, [{"inputs": {"a": 7, "b": 3}, "expected": {"y": 5}}])[0]["passed"])
        self.assertTrue(run_vectors(divide, [{"inputs": {"a": 7, "b": 2}, "expected": {"y": 3}}])[0]["passed"])
        self.assertTrue(run_vectors(divide, [{"inputs": {"a": 7, "b": 0}, "expected": {"y": None}}])[0]["passed"])

    def test_mux_and_boolean(self):
        source = "module mux(input a,input b,input sel,output y); assign y=sel ? b : a; endmodule"
        self.assertTrue(all(row["passed"] for row in run_vectors(source, [
            {"inputs": {"a": a, "b": b, "sel": s}, "expected": {"y": b if s else a}}
            for a in (0, 1) for b in (0, 1) for s in (0, 1)])))

    def test_nested_module_simulation_and_snapshot(self):
        source = ("module inner(input a,input b,output y); assign y=a^b; endmodule "
                  "module outer(input a,input b,output y); inner u(.a(a),.b(b),.y(y)); endmodule")
        circuit = import_verilog(source)
        self.assertTrue(any(c.kind == "BLOCK:inner" for c in circuit.components.values()))
        reopened = Circuit.from_dict(circuit.to_dict())
        self.assertTrue(run_circuit_vectors(reopened, [{"inputs": {"a": 1, "b": 0}, "expected": {"y": 1}}])[0]["passed"])
        self.assertIn("module inner", export_verilog(reopened))

    def test_wide_nested_module(self):
        source = ("module inv(input [15:0] a,output [15:0] y); assign y=~a; endmodule "
                  "module top(input [15:0] a,output [15:0] y); inv u(.a(a),.y(y)); endmodule")
        circuit = import_verilog(source)
        self.assertEqual(sum(isinstance(w, BusWire) for w in circuit.wires.values()), 2)
        validate_definition(circuit.blocks["inv"], "inv")
        self.assertTrue(run_vectors(source, [{"inputs": {"a": 0x1234}, "expected": {"y": 0xEDCB}}])[0]["passed"])

    def test_import_collision_keeps_nested_connections(self):
        first = ("module inner(input a,output y); assign y=~a; endmodule "
                 "module top(input a,output y); inner u(.a(a),.y(y)); endmodule")
        second = ("module inner(input a,output y); assign y=a; endmodule "
                  "module top(input a,output y); inner u(.a(a),.y(y)); endmodule")
        destination = import_verilog(first)
        prepared = prepare_import(import_verilog(second), destination)
        self.assertIn("inner_hdl2", prepared.blocks)
        self.assertTrue(run_circuit_vectors(prepared, [{"inputs": {"a": 1}, "expected": {"y": 1}}])[0]["passed"])

    def test_x_propagation_and_live_circuit_preserved(self):
        circuit = import_verilog(AND)
        before = circuit.to_dict()
        result = run_circuit_vectors(circuit, [{"inputs": {"a": None, "b": 1}, "expected": {"y": None}}])
        self.assertTrue(result[0]["passed"])
        self.assertEqual(circuit.to_dict(), before)

    def test_vectors_override_existing_bus_input_bits(self):
        source = "module m(input [3:0] a,output [3:0] y); assign y=a; endmodule"
        circuit = import_verilog(source)
        next(c for c in circuit.components.values() if c.kind == "INPUT").params["_bit_values"] = [1, 1, 1, 1]
        self.assertTrue(run_circuit_vectors(circuit, [{"inputs": {"a": 0}, "expected": {"y": 0}}])[0]["passed"])

    def test_vector_failure_and_range_validation(self):
        self.assertFalse(run_vectors(AND, [{"inputs": {"a": 1, "b": 1}, "expected": {"y": 0}}])[0]["passed"])
        with self.assertRaisesRegex(ValueError, "does not fit"):
            run_vectors(AND, [{"inputs": {"a": 2, "b": 0}, "expected": {"y": 0}}])


class ExportTests(unittest.TestCase):
    def test_gate_export_round_trip(self):
        generated = export_verilog(import_verilog(AND))
        self.assertIn("assign", generated)
        self.assertTrue(all(row["passed"] for row in run_vectors(generated, vectors(1, lambda a, b: a & b))))

    def test_bus_export_keeps_width(self):
        source = "module xor4(input [3:0] a,input [3:0] b,output [3:0] y); assign y=a^b; endmodule"
        generated = export_verilog(import_verilog(source))
        self.assertIn("[3:0] a", generated)
        self.assertTrue(all(row["passed"] for row in run_vectors(generated, vectors(4, lambda a, b: a ^ b))))

    def test_export_rejects_unsupported_and_disconnected(self):
        circuit = Circuit(); circuit.add("RAM"); circuit.add("OUTPUT", params={"label": "y"})
        issues = export_issues(circuit)
        self.assertTrue(any("RAM" in issue for issue in issues))
        self.assertTrue(any("disconnected" in issue for issue in issues))
        with self.assertRaisesRegex(ValueError, "Cannot export"):
            export_verilog(circuit)

    def test_register_export_uses_edge(self):
        circuit = Circuit(); d = circuit.add("INPUT", params={"label": "D"})
        clk = circuit.add("INPUT", params={"label": "CLK"})
        q = circuit.add("OUTPUT", params={"label": "Q"})
        reg = circuit.add("D Flip-Flop")
        circuit.connect(d.id, "Q", reg.id, "D"); circuit.connect(clk.id, "Q", reg.id, "CLK")
        circuit.connect(reg.id, "Q", q.id, "A")
        self.assertIn("always @(posedge CLK)", export_verilog(circuit))
        self.assertTrue(validate_hdl_lesson(circuit, "hdl_register").passed)


class TutorialAndToolTests(unittest.TestCase):
    def test_builtin_hdl_lessons_are_behavior_checked(self):
        self.assertEqual(len(HDL_LESSONS), 7)
        valid = "module first(input a,output y); assign y=~a; endmodule"
        self.assertTrue(validate_hdl_lesson(Circuit(), "hdl_first", valid).passed)
        self.assertFalse(validate_hdl_lesson(Circuit(), "hdl_first", "module first(input a,output y); assign y=a; endmodule").passed)

    def test_all_combinational_hdl_lesson_solutions(self):
        solutions = {
            "hdl_comb": "module comb(input a,input b,input c,output y); assign y=(a&b)|c; endmodule",
            "hdl_mux": "module mux(input a,input b,input sel,output y); assign y=sel?b:a; endmodule",
            "hdl_validation": "module add4(input [3:0] a,input [3:0] b,output [3:0] y); assign y=a+b; endmodule",
            "hdl_import": "module xor2(input a,input b,output y); assign y=a^b; endmodule",
        }
        for lesson_id, source in solutions.items():
            with self.subTest(lesson_id=lesson_id):
                circuit = import_verilog(source) if lesson_id == "hdl_import" else Circuit()
                self.assertTrue(validate_hdl_lesson(circuit, lesson_id, source).passed)

    def test_existing_project_still_loads(self):
        project = Circuit.load(Path(__file__).resolve().parents[1] / "examples/half_adder.json")
        self.assertFalse(Simulator(project).errors)

    def test_custom_lesson_store_and_grade(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CustomLessonStore(folder)
            case = [{"inputs": {"a": 0, "b": 1}, "expected": {"y": 0}}]
            store.save("and_gate", "AND", "Learn AND", "Build AND", case, Circuit(), AND)
            self.assertEqual(len(store.list()), 1)
            self.assertTrue(store.check("and_gate", source=AND).passed)
            self.assertFalse(store.check("and_gate", source="module gate(input a,input b,output y); assign y=a|b; endmodule").passed)
            store.delete("and_gate"); self.assertEqual(store.list(), [])

    def test_external_tools_missing_is_actionable(self):
        with patch("hdl_tools.shutil.which", return_value=None):
            self.assertIn("iverilog", external_availability()[1])
            with self.assertRaisesRegex(ValueError, "unavailable"):
                run_external_vectors(AND, [])

    def test_external_sandbox_failure_is_reported(self):
        with patch("hdl_tools.shutil.which", return_value="/usr/bin/tool"), patch(
                "hdl_tools._sandbox", side_effect=ValueError("namespace denied")):
            available, reason = external_availability()
        self.assertFalse(available)
        self.assertIn("namespace denied" if os.name == "posix" else "Windows", reason)

    def test_external_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("hdl_tools.run_restricted", side_effect=ValueError("External tool exceeded 2 seconds")):
                with self.assertRaisesRegex(ValueError, "exceeded"):
                    _sandbox(["/usr/bin/false"], folder, timeout=2)

    def test_report_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            export_report(path, [{"passed": True}])
            self.assertEqual(json.loads(path.read_text())["results"][0]["passed"], True)


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hdl_panel_validate_import_export_and_test(self):
        editor = Editor(); panel = editor.hdl_panel
        try:
            panel.code.setPlainText(AND); panel.validate()
            self.assertIn("Valid", panel.diagnostics.text())
            panel.import_circuit()
            self.assertIn("AND", {c.kind for c in editor.circuit.components.values()})
            panel.export_circuit()
            self.assertIn("module logicspace_top", panel.code.toPlainText())
            panel.vectors.setPlainText(json.dumps(vectors(1, lambda a, b: a & b)))
            panel.run_internal()
            self.assertIn("4/4 passed", panel.results.toPlainText())
        finally:
            panel.dirty = False
            editor.dirty = False
            editor.close()

    def test_hdl_file_save_and_open(self):
        editor = Editor(); panel = editor.hdl_panel
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "test.sv"
                panel.path = path; panel.code.setPlainText(AND); panel.save_file()
                self.assertEqual(path.read_text(), AND)
                panel.code.setPlainText("changed")
                with patch.object(panel, "_confirm_discard", return_value=True), patch(
                        "hdl_view.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                    panel.open_file()
                self.assertEqual(panel.code.toPlainText(), AND)
                self.assertFalse(panel.dirty)
        finally:
            panel.dirty = False; editor.dirty = False; editor.close()


if __name__ == "__main__": unittest.main()

"""Templates, lessons, local gallery, benchmarks and ZIP exchange."""
import csv
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication

from benchmark import PRESETS, export_csv, export_json, run_benchmark
from cpu_board import create_cpu_circuit
from engine import Circuit, Simulator
from main import Editor
from project_experience import (BUILTIN_TEMPLATES, CATEGORIES, ProjectGallery,
                                ProjectPackage, TemplateStore)
from tutorials import (LESSONS, TutorialProgress, starter_circuit, validate_lesson)


def labelled(circuit):
    return {component.params.get("label"): component for component in circuit.components.values()}


def finish_lesson(name):
    if name == "cpu": return create_cpu_circuit("MOV R0,9\nHLT\n")
    if name == "isa":
        return create_cpu_circuit("MOV R0,0\nMOV R1,1\nMOV R2,3\nLOOP: ADD R0,R1\nCMP R0,R2\nJNZ LOOP\nHLT\n")
    if name == "assembly":
        return create_cpu_circuit("MOV R0,10\nMOV R1,5\nADD R0,R1\nSTORE R0,0x20\nHLT\n")
    c = starter_circuit(name); p = labelled(c)
    if name == "gates":
        gate = c.add("AND")
        for input_name in ("A", "B"): c.connect(p[input_name].id, "Q", gate.id, input_name)
        c.connect(gate.id, "Q", p["Y"].id, "A")
    elif name == "adders":
        gate = c.add("Full Adder")
        for input_name in ("A", "B", "CIN"):
            c.connect(p[input_name].id, "Q", gate.id, input_name)
        c.connect(gate.id, "SUM", p["SUM"].id, "A")
        c.connect(gate.id, "COUT", p["COUT"].id, "A")
    elif name == "arithmetic":
        gate = c.add("Adder", params={"width": 4})
        for port in ("A", "B"): c.connect_bus(p[port].id, "Q", gate.id, port)
        c.connect(p["CIN"].id, "Q", gate.id, "CIN")
        c.connect_bus(gate.id, "Q", p["SUM"].id, "D")
        c.connect(gate.id, "COUT", p["COUT"].id, "A")
    elif name == "mux_decoder":
        mux, decoder = c.add("Multiplexer"), c.add("Decoder")
        for port in ("A", "B", "SEL"): c.connect(p[port].id, "Q", mux.id, port)
        c.connect(mux.id, "Q", p["Y"].id, "A")
        for port in ("A", "B"): c.connect(p[port].id, "Q", decoder.id, port)
        for index in range(4): c.connect(decoder.id, f"Q{index}", p[f"D{index}"].id, "A")
    elif name == "sequential":
        flip, reg = c.add("D Flip-Flop"), c.add("Register", params={"width": 4})
        c.connect(p["D"].id, "Q", flip.id, "D")
        c.connect(p["CLK"].id, "Q", flip.id, "CLK")
        c.connect(flip.id, "Q", p["Q"].id, "A")
        c.connect_bus(p["DATA"].id, "Q", reg.id, "D")
        c.connect(p["CLK"].id, "Q", reg.id, "CLK")
        c.connect_bus(reg.id, "Q", p["REG"].id, "D")
    elif name == "alu":
        alu = c.add("ALU", params={"width": 8})
        for port in ("A", "B", "OP"): c.connect_bus(p[port].id, "Q", alu.id, port)
        c.connect_bus(alu.id, "Q", p["RESULT"].id, "D")
        for flag in ("ZERO", "CARRY"): c.connect(alu.id, flag, p[flag].id, "A")
    elif name == "ram":
        ram = c.add("RAM", params={"address_bits": 8, "data_bits": 8, "depth": 256})
        for input_name, port in (("ADDRESS", "A"), ("DATA", "D")):
            c.connect_bus(p[input_name].id, "Q", ram.id, port)
        for port in ("WE", "CLK"): c.connect(p[port].id, "Q", ram.id, port)
        c.connect_bus(ram.id, "Q", p["Q"].id, "D")
    return c


class TemplateTests(unittest.TestCase):
    def test_all_nine_builtin_categories_create_real_editable_circuits(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TemplateStore(folder)
            self.assertEqual({item.category for item in BUILTIN_TEMPLATES}, set(CATEGORIES))
            for item in BUILTIN_TEMPLATES:
                with self.subTest(item=item.id):
                    circuit = store.create(item.id)
                    self.assertTrue(circuit.components)
                    self.assertFalse(Simulator(circuit).errors)
                    reopened = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
                    self.assertEqual(len(reopened.wires), len(circuit.wires))
                    self.assertEqual(reopened.project_info["source_template"], item.id)

    def test_user_template_save_reopen_and_project_independence(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TemplateStore(folder)
            original = finish_lesson("gates"); before = original.to_dict()
            identifier = store.save(original, "My AND", "Logic Gates", "Beginner", "Two-input AND")
            first = store.create(identifier); second = store.create(identifier)
            first.components[next(iter(first.components))].params["value"] = 1
            self.assertNotEqual(first.to_dict(), second.to_dict())
            self.assertEqual(original.to_dict(), before)
            self.assertEqual(first.project_info["source_template"], identifier)
            self.assertIn(identifier, {item.id for item in store.list()})


class TutorialTests(unittest.TestCase):
    def test_all_lessons_require_behavior_and_completed_circuits_pass(self):
        self.assertEqual(len(LESSONS), 10)
        for lesson in LESSONS:
            with self.subTest(lesson=lesson.id):
                starter = starter_circuit(lesson.id)
                self.assertFalse(validate_lesson(starter, lesson.id).passed)
                circuit = finish_lesson(lesson.id)
                before = circuit.to_dict()
                result = validate_lesson(circuit, lesson.id)
                self.assertTrue(result.passed, result.message)
                self.assertGreater(result.checked, 0)
                self.assertEqual(circuit.to_dict(), before)

    def test_gate_presence_without_correct_wiring_fails_with_reason(self):
        circuit = finish_lesson("gates")
        gate = next(c for c in circuit.components.values() if c.kind == "AND")
        for wid, wire in list(circuit.wires.items()):
            if wire.target == gate.id and wire.target_pin == "B": circuit.wires.pop(wid)
        result = validate_lesson(circuit, "gates")
        self.assertFalse(result.passed)
        self.assertIn("Y should be", result.message)

    def test_isa_lesson_rejects_jnz_that_never_takes_a_loop(self):
        circuit = create_cpu_circuit("MOV R0,3\nMOV R1,3\nCMP R0,R1\nJNZ START\n"
                                     "START: CMP R0,R1\nJNZ START\nHLT\n")
        result = validate_lesson(circuit, "isa")
        self.assertFalse(result.passed)
        self.assertIn("JNZ loop", result.message)

    def test_progress_only_records_passed_simulation(self):
        with tempfile.TemporaryDirectory() as folder:
            progress = TutorialProgress(Path(folder) / "progress.json")
            bad = validate_lesson(starter_circuit("gates"), "gates")
            with self.assertRaises(ValueError): progress.mark("gates", bad)
            good = validate_lesson(finish_lesson("gates"), "gates")
            progress.mark("gates", good)
            self.assertIn("gates", TutorialProgress(progress.path).completed())


class BenchmarkTests(unittest.TestCase):
    def test_standard_presets_and_signal_changes_are_real(self):
        for name in PRESETS:
            with self.subTest(name=name):
                result = run_benchmark(name, 2)
                self.assertEqual(result.completed_steps, 2)
                self.assertGreater(result.components, 0)
                self.assertGreaterEqual(result.connections, result.bus_wires)
                self.assertGreater(result.signal_changes, 0)
                self.assertAlmostEqual(result.average_step_seconds * 2, result.simulation_seconds)
        self.assertEqual(run_benchmark("logic_100", 1).components, 101)
        self.assertEqual(run_benchmark("logic_100", 2).signal_changes, 202)
        self.assertEqual(run_benchmark("logic_500", 1).components, 501)
        self.assertEqual(run_benchmark("logic_1000", 1).components, 1001)

    def test_cancel_and_json_csv_export(self):
        result = run_benchmark("logic_100", 5, cancelled=lambda: True)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.completed_steps, 0)
        with tempfile.TemporaryDirectory() as folder:
            json_path, csv_path = Path(folder) / "result.json", Path(folder) / "result.csv"
            export_json(result, json_path); export_csv(result, csv_path)
            self.assertEqual(json.loads(json_path.read_text())["components"], result.components)
            with csv_path.open() as stream:
                self.assertEqual(next(csv.DictReader(stream))["completed_steps"], "0")


class GalleryAndPackageTests(unittest.TestCase):
    def test_gallery_filter_duplicate_remove_preserves_source(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); source = base / "source.json"
            finish_lesson("gates").save(source)
            gallery = ProjectGallery(base / "gallery.json")
            identifier = gallery.add(source, "My gate", "Logic Gates", "Beginner", "Working AND")
            self.assertEqual(len(gallery.list("my gate", "Logic Gates", "Beginner")), 1)
            duplicate = base / "duplicate.json"
            gallery.duplicate(identifier, duplicate)
            self.assertEqual(len(Circuit.load(duplicate).components), len(Circuit.load(source).components))
            with self.assertRaises(FileExistsError): gallery.duplicate(identifier, duplicate)
            gallery.remove(identifier)
            self.assertTrue(source.exists())
            self.assertFalse(gallery.list("my gate"))
            self.assertTrue(any(item["builtin"] for item in gallery.list()))

    def test_zip_roundtrip_includes_user_template_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); store = TemplateStore(base / "templates")
            identifier = store.save(finish_lesson("gates"), "Shared gate", "Logic Gates", "Beginner", "A gate")
            circuit = store.create(identifier)
            meta = dict(name="Circuit kit", category="Logic Gates", difficulty="Beginner", description="Shareable")
            package = base / "project.zip"; destination = base / "opened.json"
            ProjectPackage.export(circuit, package, meta, store)
            with zipfile.ZipFile(package) as archive:
                self.assertIn("project.json", archive.namelist())
                self.assertIn("README.md", archive.namelist())
                self.assertIn(f"templates/{identifier}.json", archive.namelist())
            installed = TemplateStore(base / "installed")
            reopened, metadata, bundled = ProjectPackage.import_package(package, destination, installed)
            self.assertEqual(metadata["name"], "Circuit kit")
            self.assertEqual(len(bundled), 1)
            self.assertEqual(Circuit.load(destination).to_dict(), reopened.to_dict())
            self.assertEqual(installed.create(identifier).project_info["source_template"], identifier)
            with self.assertRaises(FileExistsError):
                ProjectPackage.import_package(package, destination, installed)

    def test_invalid_zip_and_old_project_compatibility(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); invalid = base / "bad.zip"; destination = base / "never.json"
            with zipfile.ZipFile(invalid, "w") as archive:
                archive.writestr("../escape.json", "{}")
            with self.assertRaises(ValueError): ProjectPackage.import_package(invalid, destination)
            self.assertFalse(destination.exists())
            broken = base / "wrong_version.zip"
            with zipfile.ZipFile(broken, "w") as archive:
                archive.writestr("project.json", json.dumps(finish_lesson("gates").to_dict()))
                archive.writestr("metadata.json", json.dumps({"format": "logicspace-package", "version": 99}))
                archive.writestr("README.md", "Bad version")
            with self.assertRaisesRegex(ValueError, "version"):
                ProjectPackage.import_package(broken, destination)
            self.assertFalse(destination.exists())
            old = Circuit.load(Path(__file__).parents[1] / "examples/half_adder.json")
            self.assertIsNone(old.project_info)
            package = base / "old.zip"
            ProjectPackage.export(old, package, dict(name="Old circuit", category="Combinational Circuits",
                                                     difficulty="Beginner", description="Legacy"))
            reopened, _, _ = ProjectPackage.import_package(package)
            self.assertEqual(len(reopened.wires), len(old.wires))


class ExperienceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = Editor(); self.editor.show(); self.app.processEvents()

    def tearDown(self):
        if self.editor.experience_panel.worker and self.editor.experience_panel.worker.isRunning():
            self.editor.experience_panel.cancel_benchmark()
            self.editor.experience_panel.worker.wait()
        self.editor.timer.stop(); self.editor.dirty = False
        self.editor.close(); self.app.processEvents()

    def test_welcome_template_preview_create_and_lesson_feedback(self):
        panel = self.editor.experience_panel
        self.assertTrue(self.editor.experience_dock.isVisible())
        panel.show_tab("templates")
        self.assertGreaterEqual(panel.template_list.count(), 9)
        self.assertIsNotNone(panel.template_preview.circuit)
        panel.create_template_project()
        self.assertTrue(self.editor.circuit.components)
        self.assertFalse(self.editor.sim.errors)
        self.editor.dirty = False
        panel.show_tab("tutorials")
        panel.lesson_list.setCurrentRow(0)
        panel.start_lesson()
        panel.check_lesson()
        self.assertIn("Fix:", panel.lesson_feedback.text())

    def test_benchmark_gallery_and_zip_actions_in_gui(self):
        panel = self.editor.experience_panel
        panel.show_tab("benchmark")
        panel.benchmark_steps.setValue(2)
        panel.start_benchmark()
        panel.worker.wait(5000); self.app.processEvents()
        self.assertEqual(panel.last_benchmark.completed_steps, 2)
        panel.show_tab("gallery")
        self.assertGreaterEqual(panel.gallery_list.count(), 3)
        panel.show_tab("templates"); panel.create_template_project()
        with tempfile.TemporaryDirectory() as folder:
            package = str(Path(folder) / "circuit.zip")
            destination = str(Path(folder) / "imported.json")
            panel.package_name.setText("GUI package")
            with patch("experience_view.QFileDialog.getSaveFileName", return_value=(package, "")):
                panel.export_package()
            self.assertTrue(Path(package).exists())
            self.editor.dirty = False
            with (patch("experience_view.QFileDialog.getOpenFileName", return_value=(package, "")),
                  patch("experience_view.QFileDialog.getSaveFileName", return_value=(destination, ""))):
                panel.import_package()
            self.assertEqual(self.editor.path, destination)
            self.assertEqual(len(self.editor.circuit.components), len(Circuit.load(destination).components))

    def test_gui_benchmark_cancel(self):
        panel = self.editor.experience_panel
        panel.show_tab("benchmark")
        panel.benchmark_preset.setCurrentIndex(2)  # 1000 logic gates
        panel.benchmark_steps.setValue(10000)
        panel.start_benchmark()
        panel.cancel_benchmark()
        self.assertTrue(panel.worker.wait(5000))
        self.app.processEvents()
        self.assertTrue(panel.last_benchmark.cancelled)
        self.assertLess(panel.last_benchmark.completed_steps, 10000)


if __name__ == "__main__": unittest.main()

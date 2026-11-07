"""A single compact Start & Learn dock for templates, lessons, benchmarks and projects."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTabWidget, QListWidget, QLineEdit, QComboBox, QSpinBox,
                               QTextEdit, QFileDialog, QMessageBox, QInputDialog,
                               QScrollArea, QDialog, QFormLayout, QDialogButtonBox,
                               QCheckBox)
from PySide6.QtWidgets import QListWidgetItem

from engine import Circuit, Simulator
from project_experience import (CATEGORIES, DIFFICULTIES, ProjectGallery,
                                ProjectPackage, TemplateStore)
from tutorials import (LESSONS, HDL_LESSONS, HDL_LESSON_BY_ID, TutorialProgress,
                       starter_circuit, validate_lesson, validate_hdl_lesson)
from hdl_lessons import CustomLessonStore
from benchmark import BenchmarkHistory, PRESETS, run_benchmark, export_csv, export_json


class CircuitPreview(QWidget):
    """Overview derived from the actual component coordinates and wire endpoints."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.circuit = None
        self.setMinimumHeight(180)

    def set_circuit(self, circuit):
        self.circuit = circuit
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#151e29"))
        if self.circuit is None or not self.circuit.components:
            painter.setPen(QColor("#8c9caf"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No components to preview")
            return
        parts = list(self.circuit.components.values())
        xs, ys = [part.x for part in parts], [part.y for part in parts]
        left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
        span_x, span_y = max(180, right - left + 180), max(130, bottom - top + 130)
        scale = min((self.width() - 35) / span_x, (self.height() - 40) / span_y)
        def point(part):
            return (int(18 + (part.x - left + 80) * scale),
                    int(14 + (part.y - top + 55) * scale))
        lookup = self.circuit.components
        painter.setPen(QPen(QColor("#456478"), 1))
        for wire in self.circuit.wires.values():
            if wire.source in lookup and wire.target in lookup:
                x0, y0 = point(lookup[wire.source]); x1, y1 = point(lookup[wire.target])
                painter.drawLine(x0, y0, x1, y1)
        for part in parts:
            x, y = point(part)
            painter.setPen(QPen(QColor("#79b9f0"), 1))
            painter.setBrush(QColor("#253d56"))
            painter.drawRoundedRect(x - 5, y - 4, 10, 8, 2, 2)
            if len(parts) <= 12:
                painter.setPen(QColor("#bdd5e9"))
                painter.drawText(x + 8, y + 3, part.params.get("label") or part.kind)
        painter.setPen(QColor("#a9b9c8"))
        painter.drawText(8, self.height() - 7,
                         f"{len(parts)} components · {len(self.circuit.wires)} connections")


class BenchmarkWorker(QThread):
    finished_result = Signal(object)
    failed = Signal(str)

    def __init__(self, name, steps, parent=None):
        super().__init__(parent)
        self.name, self.steps = name, steps
        self.cancel_requested = False

    def run(self):
        try:
            self.finished_result.emit(run_benchmark(self.name, self.steps,
                                                    cancelled=lambda: self.cancel_requested))
        except Exception as error:
            self.failed.emit(str(error))


class ExperiencePanel(QWidget):
    def __init__(self, editor, parent=None, templates=None, gallery=None, progress=None):
        super().__init__(parent)
        self.editor = editor
        self.templates = templates or TemplateStore()
        self.gallery = gallery or ProjectGallery()
        self.progress = progress or TutorialProgress()
        self.hdl_lessons = CustomLessonStore()
        self.worker = None
        self.last_benchmark = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self._build_welcome()
        self._build_templates()
        self._build_tutorials()
        self._build_benchmark()
        self._build_gallery()
        self._build_package()
        self._build_hdl_tutorials()
        self.status = QLabel("Choose a project, lesson or measurement")
        self.status.setWordWrap(True); layout.addWidget(self.status)

    def show_tab(self, name):
        index = {"welcome": 0, "templates": 1, "tutorials": 2,
                 "benchmark": 3, "gallery": 4, "package": 5, "hdl": 6}[name]
        if name == "templates": self.refresh_templates()
        if name == "gallery": self.refresh_gallery()
        if name == "tutorials": self.refresh_lessons()
        if name == "hdl": self.refresh_hdl_lessons()
        self.tabs.setCurrentIndex(index)

    def _button(self, text, callback, layout):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def _build_welcome(self):
        page = QWidget(); box = QVBoxLayout(page)
        heading = QLabel("Welcome to LogicSpace")
        heading.setStyleSheet("font-size: 20px; font-weight: 600; color: #dce9f8;")
        box.addWidget(heading)
        intro = QLabel("Build a circuit, try a guided lesson, or open a ready project. The canvas stays your main workspace.")
        intro.setWordWrap(True); box.addWidget(intro)
        for label, callback in (("Create from template", lambda: self.show_tab("templates")),
                                ("Try the half-adder example", self.open_starter_example),
                                ("Browse local projects", lambda: self.show_tab("gallery")),
                                ("Start a tutorial", lambda: self.show_tab("tutorials")),
                                ("Open a project file…", self.editor.open_file),
                                ("New blank circuit", self.editor.new_file),
                                ("CPU / Assembly", self.editor.show_cpu_assembly)):
            self._button(label, callback, box)
        box.addStretch()
        self.tabs.addTab(page, "Start")

    def open_starter_example(self):
        path = Path(__file__).resolve().parent / "examples" / "half_adder.json"
        try:
            if self._adopt(Circuit.load(path)):
                self.editor.set_status("Half-adder ready · toggle its INPUT switches and watch SUM/CARRY")
                self.editor.experience_dock.hide()
        except (OSError, ValueError, TypeError, KeyError) as error:
            QMessageBox.warning(self, "Open example", str(error))

    def _filters(self, row):
        category = QComboBox(); category.addItems(("All", *CATEGORIES)); row.addWidget(category)
        difficulty = QComboBox(); difficulty.addItems(("All", *DIFFICULTIES)); row.addWidget(difficulty)
        return category, difficulty

    def _build_templates(self):
        page = QWidget(); box = QVBoxLayout(page)
        self.template_search = QLineEdit(); self.template_search.setPlaceholderText("Search templates…")
        self.template_search.textChanged.connect(self.refresh_templates); box.addWidget(self.template_search)
        row = QHBoxLayout(); self.template_category, self.template_difficulty = self._filters(row)
        self.template_category.currentTextChanged.connect(self.refresh_templates)
        self.template_difficulty.currentTextChanged.connect(self.refresh_templates)
        box.addLayout(row)
        self.template_list = QListWidget(); self.template_list.currentRowChanged.connect(self._template_selected)
        self.template_list.setStyleSheet("QListWidget::item:selected { background: #285f93; color: white; }")
        box.addWidget(self.template_list, 1)
        self.template_description = QLabel("Select a template")
        self.template_description.setWordWrap(True); box.addWidget(self.template_description)
        self.template_preview = CircuitPreview(); box.addWidget(self.template_preview)
        row = QHBoxLayout()
        self._button("Create project", self.create_template_project, row)
        self._button("Save current as template…", self.save_template, row)
        box.addLayout(row)
        self.tabs.addTab(page, "Templates")

    def refresh_templates(self, *_):
        try: items = self.templates.list()
        except (ValueError, OSError) as error: self.status.setText(str(error)); return
        if self.templates.issues:
            self.status.setText(f"Skipped {len(self.templates.issues)} damaged user template(s): " +
                                self.templates.issues[0])
        query = self.template_search.text().casefold().strip()
        items = [item for item in items if (not query or query in (item.name + " " + item.description).casefold())
                 and (self.template_category.currentText() == "All" or item.category == self.template_category.currentText())
                 and (self.template_difficulty.currentText() == "All" or item.difficulty == self.template_difficulty.currentText())]
        current = self.template_list.currentItem().data(Qt.UserRole) if self.template_list.currentItem() else None
        self.template_list.clear()
        for info in items:
            self.template_list.addItem(f"{info.name} · {info.difficulty}")
            self.template_list.item(self.template_list.count() - 1).setData(Qt.UserRole, info.id)
        if items:
            index = next((index for index, info in enumerate(items) if info.id == current), 0)
            self.template_list.setCurrentRow(index)
        else:
            self.template_description.setText("No templates match this filter")
            self.template_preview.set_circuit(None)

    def _template_selected(self, *_):
        item = self.template_list.currentItem()
        if item is None: return
        try:
            info = next(info for info in self.templates.list() if info.id == item.data(Qt.UserRole))
            circuit = self.templates.create(info.id)
            self.template_description.setText(f"{info.category} · {info.difficulty}\n{info.description}")
            self.template_preview.set_circuit(circuit)
        except (ValueError, OSError, StopIteration) as error:
            self.template_description.setText(str(error))

    def _adopt(self, circuit, path=None, confirmed=False):
        if not confirmed and not self.editor._confirm_discard(): return False
        self.editor._close_testbench_editor()
        self.editor.timer.stop()
        self.editor.run_button.setText("▶ Run")
        self.editor.circuit, self.editor.sim, self.editor.path = circuit, Simulator(circuit), path
        self.editor.timing_panel.sync_circuit(clear=True)
        self.editor.history.clear(); self.editor.future.clear()
        self.editor.dirty = path is None
        self.editor.render(); self.editor.populate_library()
        self.editor.setWindowTitle("LogicSpace — " + (Path(path).name if path else "Untitled"))
        self.editor.canvas.centerOn(0, 0)
        return True

    def create_template_project(self):
        item = self.template_list.currentItem()
        if item is None: return
        try:
            circuit = self.templates.create(item.data(Qt.UserRole))
            if self._adopt(circuit):
                self.status.setText("Editable project created from template")
                self.editor.experience_dock.hide()
        except (ValueError, OSError) as error: QMessageBox.warning(self, "Template", str(error))

    def save_template(self):
        name, ok = QInputDialog.getText(self, "Save template", "Template name:")
        if not ok: return
        description, ok = QInputDialog.getText(self, "Save template", "Short description:")
        if not ok: return
        category, ok = QInputDialog.getItem(self, "Save template", "Category:", CATEGORIES, 0, False)
        if not ok: return
        difficulty, ok = QInputDialog.getItem(self, "Save template", "Difficulty:", DIFFICULTIES, 1, False)
        if not ok: return
        try:
            identifier = self.templates.save(self.editor.circuit, name, category, difficulty, description)
            self.refresh_templates(); self.status.setText(f"Saved user template {identifier[:8]}")
        except (ValueError, OSError) as error: QMessageBox.warning(self, "Save template", str(error))

    def _build_tutorials(self):
        page = QWidget(); box = QVBoxLayout(page)
        self.lesson_list = QListWidget(); self.lesson_list.currentRowChanged.connect(self._lesson_selected)
        self.lesson_list.setStyleSheet("QListWidget::item:selected { background: #285f93; color: white; }")
        box.addWidget(self.lesson_list, 1)
        self.lesson_detail = QLabel("Select a lesson")
        self.lesson_detail.setWordWrap(True); box.addWidget(self.lesson_detail)
        row = QHBoxLayout()
        self._button("Start lesson", self.start_lesson, row)
        self._button("Check current circuit", self.check_lesson, row)
        box.addLayout(row)
        self.lesson_feedback = QLabel("Simulation checks run on an isolated copy of your circuit.")
        self.lesson_feedback.setWordWrap(True); box.addWidget(self.lesson_feedback)
        self.tabs.addTab(page, "Learn")

    def refresh_lessons(self):
        try: completed = self.progress.completed()
        except (ValueError, OSError) as error:
            completed = {}; self.lesson_feedback.setText(str(error))
        current = self.lesson_list.currentRow()
        self.lesson_list.clear()
        for lesson in LESSONS:
            self.lesson_list.addItem(("✓ " if lesson.id in completed else "○ ") + lesson.title)
        if LESSONS: self.lesson_list.setCurrentRow(max(0, current))

    def _lesson_selected(self, index):
        if not 0 <= index < len(LESSONS): return
        lesson = LESSONS[index]
        self.lesson_detail.setText(f"{lesson.explanation}\n\nTask: {lesson.task}\n\nComponents: {lesson.components}\n\nPass: {lesson.completion}")

    def start_lesson(self):
        index = self.lesson_list.currentRow()
        if not 0 <= index < len(LESSONS): return
        lesson = LESSONS[index]
        try:
            if self._adopt(starter_circuit(lesson.id)):
                self.lesson_feedback.setText(f"Started {lesson.title}. Build the circuit on the canvas, then check it here.")
        except ValueError as error: self.lesson_feedback.setText(str(error))

    def check_lesson(self):
        index = self.lesson_list.currentRow()
        if not 0 <= index < len(LESSONS): return
        lesson = LESSONS[index]
        result = validate_lesson(self.editor.circuit, lesson.id)
        self.lesson_feedback.setText(("✓ " if result.passed else "Fix: ") + result.message)
        if result.passed:
            try: self.progress.mark(lesson.id, result); self.refresh_lessons()
            except (ValueError, OSError) as error: self.lesson_feedback.setText(str(error))

    def _build_benchmark(self):
        page = QWidget(); box = QVBoxLayout(page)
        note = QLabel("Local simulator timing only. Compare runs on the same machine and settings; build time is separate.")
        note.setWordWrap(True); box.addWidget(note)
        self.benchmark_preset = QComboBox()
        for name, title in PRESETS.items(): self.benchmark_preset.addItem(title, name)
        box.addWidget(self.benchmark_preset)
        row = QHBoxLayout(); row.addWidget(QLabel("Steps"))
        self.benchmark_steps = QSpinBox(); self.benchmark_steps.setRange(1, 10000)
        self.benchmark_steps.setValue(20); row.addWidget(self.benchmark_steps)
        self._button("Run", self.start_benchmark, row)
        self._button("Cancel", self.cancel_benchmark, row)
        box.addLayout(row)
        self.benchmark_result = QTextEdit(); self.benchmark_result.setReadOnly(True)
        box.addWidget(self.benchmark_result, 1)
        row = QHBoxLayout()
        self._button("Export CSV", lambda: self.export_benchmark("csv"), row)
        self._button("Export JSON", lambda: self.export_benchmark("json"), row)
        box.addLayout(row)
        self.tabs.addTab(page, "Bench")

    def start_benchmark(self):
        if self.worker and self.worker.isRunning(): return
        self.benchmark_result.setPlainText("Building circuit and measuring the real Simulator…")
        self.worker = BenchmarkWorker(self.benchmark_preset.currentData(), self.benchmark_steps.value(), self)
        self.worker.finished_result.connect(self._benchmark_finished)
        self.worker.failed.connect(self.benchmark_result.setPlainText)
        self.worker.start()

    def cancel_benchmark(self):
        if self.worker and self.worker.isRunning(): self.worker.cancel_requested = True

    def _benchmark_finished(self, result):
        self.last_benchmark = result
        comparison = ""
        try:
            previous = BenchmarkHistory().record(result)
            if previous is not None and previous.simulation_seconds > 0:
                change = 100 * (result.simulation_seconds / previous.simulation_seconds - 1)
                comparison = (f"\nPrevious comparable run: {previous.simulation_seconds:.6f} s · "
                              f"current {change:+.1f}% (local wall time; lower is faster)")
        except (OSError, ValueError, TypeError) as error:
            comparison = f"\nBenchmark history unavailable: {error}"
        self.benchmark_result.setPlainText(
            f"{result.name}\nComponents {result.components} · wires {result.connections} · BusWire {result.bus_wires}\n"
            f"Steps {result.completed_steps}/{result.requested_steps} · signal changes {result.signal_changes}\n"
            f"Build {result.build_seconds:.6f} s · simulation {result.simulation_seconds:.6f} s\n"
            f"Average step {result.average_step_seconds * 1000:.3f} ms"
            + (" · cancelled" if result.cancelled else "") + comparison + "\n\n" + result.note)

    def export_benchmark(self, format_name):
        if self.last_benchmark is None: self.status.setText("Run a benchmark first"); return
        suffix = ".csv" if format_name == "csv" else ".json"
        path, _ = QFileDialog.getSaveFileName(self, "Export benchmark report", "benchmark" + suffix)
        if not path: return
        try:
            if format_name == "csv": export_csv(self.last_benchmark, path)
            else: export_json(self.last_benchmark, path)
            self.status.setText(f"Exported {path}")
        except OSError as error: QMessageBox.warning(self, "Benchmark export", str(error))

    def _build_gallery(self):
        page = QWidget(); box = QVBoxLayout(page)
        self.gallery_search = QLineEdit(); self.gallery_search.setPlaceholderText("Search local projects…")
        self.gallery_search.textChanged.connect(self.refresh_gallery); box.addWidget(self.gallery_search)
        row = QHBoxLayout(); self.gallery_category, self.gallery_difficulty = self._filters(row)
        self.gallery_category.currentTextChanged.connect(self.refresh_gallery)
        self.gallery_difficulty.currentTextChanged.connect(self.refresh_gallery)
        box.addLayout(row)
        self.gallery_list = QListWidget(); self.gallery_list.currentRowChanged.connect(self._gallery_selected)
        self.gallery_list.setStyleSheet("QListWidget::item:selected { background: #285f93; color: white; }")
        box.addWidget(self.gallery_list, 1)
        self.gallery_description = QLabel("Select a local example or registered project")
        self.gallery_description.setWordWrap(True); box.addWidget(self.gallery_description)
        self.gallery_preview = CircuitPreview(); box.addWidget(self.gallery_preview)
        row = QHBoxLayout()
        for title, callback in (("Open", self.open_gallery_project),
                                ("Duplicate…", self.duplicate_gallery_project),
                                ("Remove entry", self.remove_gallery_entry),
                                ("Add current", self.add_current_to_gallery)):
            self._button(title, callback, row)
        box.addLayout(row)
        self.tabs.addTab(page, "Gallery")

    def refresh_gallery(self, *_):
        try:
            items = self.gallery.list(self.gallery_search.text(), self.gallery_category.currentText(),
                                      self.gallery_difficulty.currentText())
        except (OSError, ValueError) as error: self.status.setText(str(error)); return
        current = self.gallery_list.currentItem().data(Qt.UserRole) if self.gallery_list.currentItem() else None
        self.gallery_list.clear()
        for item in items:
            self.gallery_list.addItem(("Built-in · " if item["builtin"] else "My project · ") + item["name"])
            self.gallery_list.item(self.gallery_list.count() - 1).setData(Qt.UserRole, item["id"])
        if items:
            self.gallery_list.setCurrentRow(next((index for index, item in enumerate(items) if item["id"] == current), 0))
        else:
            self.gallery_description.setText("No projects match this filter")
            self.gallery_preview.set_circuit(None)

    def _gallery_item(self):
        current = self.gallery_list.currentItem()
        if current is None: return None
        return next((item for item in self.gallery.list() if item["id"] == current.data(Qt.UserRole)), None)

    def _gallery_selected(self, *_):
        item = self._gallery_item()
        if item is None: return
        self.gallery_description.setText(f"{item['category']} · {item['difficulty']}\n{item['description']}\n{item['path']}")
        try: self.gallery_preview.set_circuit(Circuit.load(item["path"]))
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.gallery_preview.set_circuit(None); self.gallery_description.setText(str(error))

    def open_gallery_project(self):
        item = self._gallery_item()
        if item is None: return
        try:
            if self._adopt(self.gallery.open(item["id"]), item["path"]):
                self.editor.dirty = False
                self.editor.experience_dock.hide()
        except (OSError, ValueError) as error: QMessageBox.warning(self, "Open gallery project", str(error))

    def duplicate_gallery_project(self):
        item = self._gallery_item()
        if item is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Duplicate project", item["name"] + ".json", "LogicSpace (*.json)")
        if not path: return
        try:
            self.gallery.duplicate(item["id"], path)
            self.status.setText(f"Duplicated to {path}")
        except (OSError, ValueError) as error: QMessageBox.warning(self, "Duplicate project", str(error))

    def remove_gallery_entry(self):
        item = self._gallery_item()
        if item is None: return
        if item["builtin"]:
            self.status.setText("Built-in examples cannot be removed")
            return
        self.gallery.remove(item["id"])
        self.refresh_gallery()
        self.status.setText("Gallery entry removed; source project file remains")

    def add_current_to_gallery(self):
        if not self.editor.path or self.editor.dirty:
            if not self.editor.save(): return
        name, ok = QInputDialog.getText(self, "Add project to gallery", "Project name:", text=Path(self.editor.path).stem)
        if not ok: return
        category = self.gallery_category.currentText()
        difficulty = self.gallery_difficulty.currentText()
        if category == "All": category = "Combinational Circuits"
        if difficulty == "All": difficulty = "Intermediate"
        try:
            self.gallery.add(self.editor.path, name, category, difficulty)
            self.refresh_gallery()
            self.status.setText("Project added to local gallery")
        except (OSError, ValueError) as error: QMessageBox.warning(self, "Gallery", str(error))

    def _build_package(self):
        page = QWidget(); box = QVBoxLayout(page)
        text = QLabel("Share a data-only ZIP containing project.json, metadata.json, README.md and a linked user template when available.")
        text.setWordWrap(True); box.addWidget(text)
        self.package_name = QLineEdit(); self.package_name.setPlaceholderText("Project name")
        box.addWidget(self.package_name)
        self.package_category = QComboBox(); self.package_category.addItems(CATEGORIES)
        box.addWidget(self.package_category)
        self.package_difficulty = QComboBox(); self.package_difficulty.addItems(DIFFICULTIES)
        box.addWidget(self.package_difficulty)
        self.package_description = QTextEdit(); self.package_description.setPlaceholderText("Short project description")
        self.package_description.setMaximumHeight(100); box.addWidget(self.package_description)
        row = QHBoxLayout()
        self._button("Export ZIP…", self.export_package, row)
        self._button("Import ZIP…", self.import_package, row)
        box.addLayout(row)
        box.addStretch()
        self.tabs.addTab(page, "Share")

    def export_package(self):
        metadata = dict(name=self.package_name.text().strip() or
                        (self.editor.circuit.project_info or {}).get("name") or
                        (Path(self.editor.path).stem if self.editor.path else "LogicSpace project"),
                        category=self.package_category.currentText(),
                        difficulty=self.package_difficulty.currentText(),
                        description=self.package_description.toPlainText())
        path, _ = QFileDialog.getSaveFileName(self, "Export LogicSpace package", "project.zip", "ZIP (*.zip)")
        if not path: return
        try:
            ProjectPackage.export(self.editor.circuit, path, metadata, self.templates)
            self.status.setText(f"Exported package {path}")
        except (OSError, ValueError) as error: QMessageBox.warning(self, "Package export", str(error))

    def import_package(self):
        source, _ = QFileDialog.getOpenFileName(self, "Import LogicSpace package", "", "ZIP (*.zip)")
        if not source: return
        target, _ = QFileDialog.getSaveFileName(self, "Save imported project as", Path(source).stem + ".json",
                                               "LogicSpace (*.json)")
        if not target: return
        if Path(target).exists():
            QMessageBox.warning(self, "Package import", "Choose a new filename; existing projects are not overwritten")
            return
        if not self.editor._confirm_discard(): return
        try:
            circuit, metadata, _ = ProjectPackage.import_package(source, target, self.templates)
            if self._adopt(circuit, target, confirmed=True):
                self.editor.dirty = False
                self.status.setText(f"Imported {metadata['name']}")
                self.editor.experience_dock.hide()
        except (OSError, ValueError, KeyError, TypeError) as error:
            QMessageBox.warning(self, "Package import", str(error))

    def _build_hdl_tutorials(self):
        page = QWidget(); box = QVBoxLayout(page)
        self.hdl_lesson_list = QListWidget()
        self.hdl_lesson_list.currentItemChanged.connect(self._hdl_lesson_detail)
        box.addWidget(self.hdl_lesson_list, 1)
        self.hdl_lesson_description = QLabel("Choose an HDL lesson")
        self.hdl_lesson_description.setWordWrap(True); box.addWidget(self.hdl_lesson_description)
        row = QHBoxLayout()
        for title, callback in (("Start", self.start_hdl_lesson), ("Check", self.check_hdl_lesson)):
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        box.addLayout(row)
        edit_row = QHBoxLayout()
        for title, callback in (("Create lesson…", self.create_custom_lesson),
                                ("Edit custom…", lambda: self.create_custom_lesson(edit=True)),
                                ("Delete custom", self.delete_custom_lesson)):
            button = QPushButton(title); button.clicked.connect(callback); edit_row.addWidget(button)
        box.addLayout(edit_row)
        self.hdl_lesson_feedback = QLabel("Solutions are checked against real LogicSpace simulation vectors.")
        self.hdl_lesson_feedback.setWordWrap(True); box.addWidget(self.hdl_lesson_feedback)
        self.tabs.addTab(page, "HDL")

    def refresh_hdl_lessons(self):
        try: completed = self.progress.completed()
        except (OSError, ValueError): completed = {}
        self.hdl_lesson_list.clear()
        for lesson in HDL_LESSONS:
            item = QListWidgetItem(("✓ " if lesson.id in completed else "○ ") + lesson.title)
            item.setData(Qt.UserRole, lesson.id); self.hdl_lesson_list.addItem(item)
        for lesson in self.hdl_lessons.list():
            key = "custom:" + lesson["id"]
            item = QListWidgetItem(("✓ " if key in completed else "○ ") + lesson["title"] + " · custom")
            item.setData(Qt.UserRole, key); self.hdl_lesson_list.addItem(item)
        if self.hdl_lesson_list.count(): self.hdl_lesson_list.setCurrentRow(0)

    def _selected_hdl_lesson(self):
        item = self.hdl_lesson_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _hdl_lesson_detail(self, current, previous):
        key = self._selected_hdl_lesson()
        if not key: return
        try:
            lesson = self.hdl_lessons.load(key[7:]) if key.startswith("custom:") else HDL_LESSON_BY_ID[key]
            explanation = lesson["description"] if isinstance(lesson, dict) else lesson.explanation
            task = lesson["task"] if isinstance(lesson, dict) else lesson.task
            self.hdl_lesson_description.setText(f"{explanation}\n\nTask: {task}")
        except (OSError, ValueError, KeyError) as error: self.hdl_lesson_description.setText(str(error))

    def start_hdl_lesson(self):
        key = self._selected_hdl_lesson()
        if not key: return
        try:
            if key.startswith("custom:"):
                item = self.hdl_lessons.load(key[7:])
                if item["starter"] is not None and not self._adopt(Circuit.from_dict(item["starter"])): return
                starter = item["source"]
            else:
                lesson = HDL_LESSON_BY_ID[key]
                starter = lesson.starter
                if lesson.mode in ("import", "export", "circuit"):
                    circuit = Circuit()
                    if lesson.mode in ("export", "circuit"):
                        names = ("D", "CLK") if lesson.mode == "circuit" else ("a", "b")
                        output = "Q" if lesson.mode == "circuit" else "y"
                        for index, name in enumerate(names): circuit.add("INPUT", 0, index * 100, {"label": name})
                        circuit.add("OUTPUT", 340, 0, {"label": output})
                    if not self._adopt(circuit): return
            if starter:
                panel = self.editor.hdl_panel
                panel.code.setPlainText(starter)
                panel.path = None; panel.dirty = True
                self.editor.show_hdl()
            self.hdl_lesson_feedback.setText("Lesson started. Check the actual behavior when ready.")
        except (OSError, ValueError, KeyError) as error: self.hdl_lesson_feedback.setText(str(error))

    def check_hdl_lesson(self):
        key = self._selected_hdl_lesson()
        if not key: return
        try:
            if key.startswith("custom:"):
                item = self.hdl_lessons.load(key[7:])
                source = self.editor.hdl_panel.code.toPlainText() if item["source"] else ""
                result = self.hdl_lessons.check(key[7:], self.editor.circuit, source)
            else:
                result = validate_hdl_lesson(self.editor.circuit, key,
                                             self.editor.hdl_panel.code.toPlainText())
            self.hdl_lesson_feedback.setText(("✓ " if result.passed else "Fix: ") + result.message)
            if result.passed:
                self.progress.mark(key, result)
                self.refresh_hdl_lessons()
        except (OSError, ValueError, KeyError) as error: self.hdl_lesson_feedback.setText(str(error))

    def create_custom_lesson(self, edit=False):
        existing = None
        if edit:
            key = self._selected_hdl_lesson()
            if not key or not key.startswith("custom:"): return
            try: existing = self.hdl_lessons.load(key[7:])
            except (OSError, ValueError, KeyError) as error:
                self.hdl_lesson_feedback.setText(str(error)); return
        dialog = QDialog(self); dialog.setWindowTitle("Create HDL / circuit lesson")
        form = QFormLayout(dialog)
        lesson_id, title, description, task = QLineEdit(), QLineEdit(), QTextEdit(), QTextEdit()
        vectors = QTextEdit(); vectors.setPlainText('[{"inputs":{"a":0},"expected":{"y":0}}]')
        source = QTextEdit(); source.setPlainText(self.editor.hdl_panel.code.toPlainText())
        hdl_mode = QCheckBox("Grade HDL source (otherwise grade canvas circuit)"); hdl_mode.setChecked(True)
        use_canvas = QCheckBox("Use current canvas as starter"); use_canvas.setChecked(not edit)
        if existing:
            lesson_id.setText(existing["id"]); lesson_id.setEnabled(False)
            title.setText(existing["title"]); description.setPlainText(existing["description"])
            task.setPlainText(existing["task"])
            vectors.setPlainText(json.dumps(existing["vectors"], indent=2))
            source.setPlainText(existing["source"])
            hdl_mode.setChecked(bool(existing["source"]))
        for name, widget in (("ID", lesson_id), ("Title", title), ("Explanation", description),
                             ("Task", task), ("Starter HDL", source), ("Test vectors JSON", vectors)):
            form.addRow(name, widget)
        form.addRow(hdl_mode)
        form.addRow(use_canvas)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted: return
        try:
            starter = (self.editor.circuit if use_canvas.isChecked() else
                       Circuit.from_dict(existing["starter"]) if existing and existing["starter"] else None)
            self.hdl_lessons.save(lesson_id.text().strip(), title.text(), description.toPlainText(),
                                  task.toPlainText(), json.loads(vectors.toPlainText()),
                                  starter, source.toPlainText() if hdl_mode.isChecked() else "")
            self.refresh_hdl_lessons(); self.hdl_lesson_feedback.setText("Custom lesson saved locally")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            QMessageBox.warning(self, "Create lesson", str(error))

    def delete_custom_lesson(self):
        key = self._selected_hdl_lesson()
        if not key or not key.startswith("custom:"): return
        if QMessageBox.question(self, "Delete lesson", f"Delete custom lesson {key[7:]}?") != QMessageBox.Yes: return
        try:
            self.hdl_lessons.delete(key[7:]); self.refresh_hdl_lessons()
        except (OSError, ValueError) as error: self.hdl_lesson_feedback.setText(str(error))

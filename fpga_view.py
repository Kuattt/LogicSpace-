"""Local FPGA project workspace; synthesis is optional and never simulated."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPlainTextEdit,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from fpga_model import (blank_workspace, export_fpga_package, load_profile,
                        save_profile, validate_workspace, validate_workspace_schema)
from toolchain_model import VERSION_ARGS, detect_tool, open_vcd, run_verilator_lint, run_yosys


class ToolWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, kind, source, top, parent=None):
        super().__init__(parent)
        self.kind, self.source, self.top = kind, source, top
        self.cancel_requested = False

    def run(self):
        try:
            operation = run_yosys if self.kind == "Yosys" else run_verilator_lint
            self.completed.emit(operation(self.source, self.top,
                                          cancelled=lambda: self.cancel_requested))
        except (ValueError, OSError) as error:
            self.failed.emit(str(error))


class DetectionWorker(QThread):
    completed = Signal(object)

    def run(self):
        self.completed.emit([detect_tool(name) for name in VERSION_ARGS])


class FPGAWorkflowPanel(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.workspace = blank_workspace()
        self.worker = None
        self.detector = None
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        project = QWidget(); box = QVBoxLayout(project)
        self.name = QLineEdit(); self.top = QLineEdit()
        for label, field in (("Project name", self.name), ("Top module", self.top)):
            box.addWidget(QLabel(label)); box.addWidget(field)
        box.addWidget(QLabel("HDL source files embedded in this project"))
        self.files = QListWidget(); box.addWidget(self.files, 1)
        row = QHBoxLayout()
        for label, callback in (("Add .v/.sv", self.add_file),
                                ("Use HDL editor", self.add_editor_source),
                                ("Remove", self.remove_file)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        box.addLayout(row)
        self.tabs.addTab(project, "Project")

        device = QWidget(); box = QVBoxLayout(device)
        self.profile_label = QLabel("No device profile selected. Device properties are Unknown.")
        self.profile_label.setWordWrap(True); box.addWidget(self.profile_label)
        row = QHBoxLayout()
        for label, callback in (("Load profile JSON", self.load_device),
                                ("Save profile JSON", self.export_device)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        box.addLayout(row)
        box.addWidget(QLabel('Pin assignments JSON: {"clk": "P1", "data[0]": "P2"}'))
        self.pins = QPlainTextEdit(); self.pins.setPlaceholderText("{}")
        box.addWidget(self.pins, 1)
        box.addWidget(QLabel('Clock constraints in MHz JSON: {"clk": 12.0}'))
        self.clocks = QPlainTextEdit(); self.clocks.setPlaceholderText("{}")
        box.addWidget(self.clocks, 1)
        self.tabs.addTab(device, "Device & pins")

        tools = QWidget(); box = QVBoxLayout(tools)
        self.tool_status = QPlainTextEdit(); self.tool_status.setReadOnly(True)
        box.addWidget(self.tool_status, 1)
        row = QHBoxLayout()
        for label, callback in (("Detect tools", self.detect_tools),
                                ("Yosys synthesis", lambda: self.start_tool("Yosys")),
                                ("Verilator lint", lambda: self.start_tool("Verilator")),
                                ("Open VCD", self.open_waveform),
                                ("Cancel", self.cancel_tool)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        box.addLayout(row)
        self.tabs.addTab(tools, "Toolchain")

        row = QHBoxLayout()
        for label, callback in (("Validate", self.validate), ("Save in project", self.save_workspace),
                                ("Export ZIP", self.export_package)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        root.addLayout(row)
        self.diagnostics = QPlainTextEdit(); self.diagnostics.setReadOnly(True)
        self.diagnostics.setMaximumHeight(135); root.addWidget(self.diagnostics)
        self.sync_circuit()
        app = QApplication.instance()
        if app is not None: app.aboutToQuit.connect(self._stop_threads)

    def sync_circuit(self):
        self.workspace = deepcopy(self.editor.circuit.fpga_workspace or blank_workspace())
        self.name.setText(self.workspace["name"])
        self.top.setText(self.workspace["top"])
        self.files.clear(); self.files.addItems(sorted(self.workspace["files"]))
        self.pins.setPlainText(json.dumps(self.workspace["pins"], indent=2))
        self.clocks.setPlainText(json.dumps(self.workspace["clocks_mhz"], indent=2))
        self._profile_label()

    def _profile_label(self):
        profile = self.workspace.get("profile")
        if profile:
            self.profile_label.setText(f"{profile['manufacturer']} · {profile['device']} · "
                                       f"{profile['package']} · {len(profile['pins'])} listed pins\n"
                                       f"Source: {profile['source']}")
        else: self.profile_label.setText("No device profile selected. Device properties are Unknown.")

    def _collect(self):
        item = deepcopy(self.workspace)
        item["name"] = self.name.text().strip()
        item["top"] = self.top.text().strip()
        item["pins"] = json.loads(self.pins.toPlainText() or "{}")
        item["clocks_mhz"] = json.loads(self.clocks.toPlainText() or "{}")
        return validate_workspace_schema(item)

    def add_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add HDL sources", "", "Verilog (*.v *.sv)")
        for path in paths:
            try:
                name = Path(path).name
                if name in self.workspace["files"]:
                    raise ValueError(f"A file named {name} is already in the project")
                source = Path(path).read_text(encoding="utf-8")
                tentative = deepcopy(self.workspace)
                tentative["files"][name] = source
                validate_workspace_schema(tentative)
                self.workspace = tentative; self.files.addItem(name)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "HDL source", str(error))

    def add_editor_source(self):
        panel = self.editor.hdl_panel
        name = panel.path.name if panel.path else "editor.sv"
        if name in self.workspace["files"]:
            answer = QMessageBox.question(self, "Replace HDL source", f"Replace {name} in FPGA project?",
                                          QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes: return
        try:
            tentative = deepcopy(self.workspace)
            tentative["files"][name] = panel.code.toPlainText()
            validate_workspace_schema(tentative)
            self.workspace = tentative
            self.files.clear(); self.files.addItems(sorted(self.workspace["files"]))
            if not self.top.text().strip() and panel.module.currentText():
                self.top.setText(panel.module.currentText())
        except ValueError as error: QMessageBox.warning(self, "HDL source", str(error))

    def remove_file(self):
        item = self.files.currentItem()
        if item:
            self.workspace["files"].pop(item.text(), None)
            self.files.takeItem(self.files.row(item))

    def load_device(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load user device profile", "", "JSON (*.json)")
        if path:
            try:
                self.workspace["profile"] = load_profile(path)
                self._profile_label()
            except (OSError, ValueError, KeyError) as error:
                QMessageBox.warning(self, "Device profile", str(error))

    def export_device(self):
        if not self.workspace.get("profile"):
            QMessageBox.information(self, "Device profile", "Load a device profile first")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save device profile", "device.json", "JSON (*.json)")
        if path:
            try: save_profile(self.workspace["profile"], path)
            except (OSError, ValueError) as error: QMessageBox.warning(self, "Device profile", str(error))

    def validate(self):
        try:
            item = self._collect()
            report = validate_workspace(item)
            self.diagnostics.setPlainText("\n".join([*("Error: " + e for e in report.errors),
                                                       *("Warning: " + w for w in report.warnings)])
                                          or "Project configuration is valid for package export.")
            return item if report.valid else None
        except (ValueError, TypeError, KeyError) as error:
            self.diagnostics.setPlainText(str(error)); return None

    def save_workspace(self):
        try: item = self._collect()
        except (ValueError, TypeError, KeyError) as error:
            self.diagnostics.setPlainText(str(error)); return
        self.editor.push_history()
        self.editor.circuit.fpga_workspace = item
        self.editor.dirty = True
        self.workspace = item
        self.diagnostics.setPlainText("FPGA configuration saved in the circuit project.")

    def export_package(self):
        item = self.validate()
        if item is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Export FPGA project ZIP", "fpga-project.zip", "ZIP (*.zip)")
        if not path: return
        if not path.lower().endswith(".zip"): path += ".zip"
        overwrite = False
        if Path(path).exists():
            overwrite = QMessageBox.question(self, "Replace package", f"Replace {path}?",
                                              QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes
            if not overwrite: return
        try:
            export_fpga_package(item, path, overwrite=overwrite)
            self.diagnostics.setPlainText(f"Exported {path}. Physical timing was not verified.")
        except (OSError, ValueError) as error: QMessageBox.warning(self, "FPGA export", str(error))

    def detect_tools(self):
        if self.detector and self.detector.isRunning(): return
        self.tool_status.setPlainText("Checking installed HDL tools…")
        self.detector = DetectionWorker(self)
        self.detector.completed.connect(self._show_detected_tools)
        self.detector.start()

    def _show_detected_tools(self, results):
        lines = []
        for result in results:
            name = result["name"]
            lines.append(f"{name}: {result['path'] or 'Not installed'} · "
                         f"{result['version'] or 'Unknown version'} · {result['last_verification']}")
        self.tool_status.setPlainText("\n".join(lines))

    def open_waveform(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open VCD waveform", "", "VCD (*.vcd)")
        if path:
            try:
                open_vcd(path)
                self.tool_status.setPlainText(f"Opened {path} in GTKWave")
            except (OSError, ValueError) as error:
                self.tool_status.setPlainText(str(error))

    def start_tool(self, kind):
        if self.worker and self.worker.isRunning():
            self.tool_status.setPlainText("An external tool is already running")
            return
        item = self.validate()
        if item is None: return
        source = "\n".join(item["files"].values())
        self.worker = ToolWorker(kind, source, item["top"], self)
        self.worker.completed.connect(lambda result: self.tool_status.setPlainText(result["log"][-10000:]))
        self.worker.failed.connect(self.tool_status.setPlainText)
        self.tabs.setCurrentIndex(2)
        self.tool_status.setPlainText(f"Running {kind} in a restricted temporary directory…")
        self.worker.start()

    def cancel_tool(self):
        if self.worker and self.worker.isRunning(): self.worker.cancel_requested = True

    def closeEvent(self, event):
        self._stop_threads()
        super().closeEvent(event)

    def _stop_threads(self):
        self.cancel_tool()
        if self.worker and self.worker.isRunning(): self.worker.wait(5000)
        if self.detector and self.detector.isRunning(): self.detector.wait(5000)

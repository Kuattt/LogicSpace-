"""Compact HDL workspace embedded as a dock in the existing editor."""
from __future__ import annotations

import json
from pathlib import Path
import re

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMenu,
                               QMessageBox, QPlainTextEdit, QPushButton, QTabWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from hdl_model import (HDLError, export_issues, export_verilog, hdl_signal_components, import_verilog,
                       prepare_import, run_vectors, validate_hdl)
from hdl_tools import (external_availability, export_report,
                       first_equivalence_mismatch, run_external_vectors)


class HDLHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        for pattern, color in ((r"\b(module|endmodule|input|output|wire|logic|assign|always|always_comb|always_ff|posedge|negedge|begin|end|if|else|case|default|endcase)\b", "#8dbdff"),
                               (r"\b\d+'[bBhHdD][0-9a-fA-F_xXzZ]+\b|\b\d+\b", "#d7b47b"),
                               (r"\b[A-Za-z_][A-Za-z_0-9$]*(?=\s*\()", "#b8a4e5"),
                               (r"//[^\n]*", "#7e93a5")):
            fmt = QTextCharFormat(); fmt.setForeground(QColor(color))
            self.rules.append((re.compile(pattern), fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class CodeEditor(QPlainTextEdit):
    KEYWORDS = ("module", "endmodule", "input", "output", "wire", "logic", "assign",
                "always_comb", "always_ff", "always", "posedge", "negedge",
                "begin", "end", "if", "else", "case", "default", "endcase",
                "&", "|", "^", "~", "&&", "||", "!")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gutter = QWidget(self)
        self.gutter.paintEvent = self._paint_numbers
        self.blockCountChanged.connect(self._margin)
        self.updateRequest.connect(self._update_gutter)
        self._margin()
        font = QFont("DejaVu Sans Mono", 10)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance("    "))
        self.setStyleSheet("QPlainTextEdit { background:#121a24; color:#e5edf5; border:1px solid #354456; selection-background-color:#315f8b; }")
        self.highlighter = HDLHighlighter(self.document())

    def _margin(self):
        self.setViewportMargins(14 + self.fontMetrics().horizontalAdvance(str(self.blockCount())), 0, 0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect(); self.gutter.setGeometry(rect.left(), rect.top(), self.viewportMargins().left(), rect.height())

    def _update_gutter(self, rect, dy):
        if dy: self.gutter.scroll(0, dy)
        else: self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()): self._margin()

    def _paint_numbers(self, event):
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor("#1a2531"))
        painter.setPen(QColor("#8296a9"))
        block = self.firstVisibleBlock()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = int(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.drawText(0, top, self.gutter.width() - 6, height, Qt.AlignRight, str(block.blockNumber() + 1))
            block = block.next(); top += height

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and event.modifiers() & Qt.ControlModifier:
            cursor = self.textCursor(); cursor.select(QTextCursor.WordUnderCursor)
            prefix = cursor.selectedText()
            menu = QMenu(self)
            for word in self.KEYWORDS:
                if word.startswith(prefix) and word != prefix: menu.addAction(word)
            chosen = menu.exec(self.mapToGlobal(self.cursorRect().bottomLeft())) if menu.actions() else None
            if chosen:
                cursor.insertText(chosen.text()); self.setTextCursor(cursor)
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor(); block = cursor.block().text()
            indent = re.match(r"\s*", block).group()
            if block.rstrip().endswith(("begin", ":")): indent += "    "
            super().keyPressEvent(event)
            self.insertPlainText(indent)
            return
        super().keyPressEvent(event)

    def show_error(self, line):
        self.setExtraSelections([])
        if line < 1: return
        block = self.document().findBlockByNumber(line - 1)
        if not block.isValid(): return
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(block)
        selection.format.setBackground(QColor("#573039"))
        selection.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        self.setExtraSelections([selection])
        self.setTextCursor(QTextCursor(block)); self.centerCursor()


class ExternalWorker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, source, vectors, top, parent=None, vcd_path=None):
        super().__init__(parent)
        self.source, self.vectors, self.top = source, vectors, top
        self.vcd_path = vcd_path

    def run(self):
        try: self.result.emit(run_external_vectors(self.source, self.vectors, self.top,
                                                   vcd_path=self.vcd_path))
        except (ValueError, OSError) as error: self.failed.emit(str(error))


class HDLPanel(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.path = None
        self.dirty = False
        self.last_results = None
        self.worker = None
        box = QVBoxLayout(self); box.setContentsMargins(8, 8, 8, 8)
        self.tabs = QTabWidget(); box.addWidget(self.tabs, 1)
        source_page = QWidget(); source_box = QVBoxLayout(source_page)
        file_row = QHBoxLayout()
        for label, callback in (("New", self.new_file), ("Open .v/.sv", self.open_file),
                                ("Save", self.save_file), ("Save As", self.save_as)):
            button = QPushButton(label); button.clicked.connect(callback); file_row.addWidget(button)
        source_box.addLayout(file_row)
        nav = QHBoxLayout(); nav.addWidget(QLabel("Module"))
        self.module = QComboBox(); self.module.currentTextChanged.connect(self.jump_to_module)
        nav.addWidget(self.module, 1); source_box.addLayout(nav)
        self.code = CodeEditor(); self.code.textChanged.connect(self._code_changed)
        self.code.setPlainText("module my_gate(input a, input b, output y);\n  assign y = a & b;\nendmodule\n")
        source_box.addWidget(self.code, 1)
        row = QHBoxLayout()
        for label, callback in (("Validate", self.validate), ("Import to canvas", self.import_circuit),
                                ("Export canvas", self.export_circuit)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        source_box.addLayout(row)
        find_button = QPushButton("Find signal on canvas")
        find_button.setToolTip("Place the cursor on a signal name in the imported HDL snapshot")
        find_button.clicked.connect(self.find_signal_on_canvas)
        source_box.addWidget(find_button)
        self.auto_clock = QCheckBox("Use Clock Generator for direct top-level HDL clock inputs")
        self.auto_clock.setChecked(True)
        self.auto_clock.setToolTip("Imported test vectors still use explicit clock inputs; this option affects canvas import only.")
        source_box.addWidget(self.auto_clock)
        self.diagnostics = QLabel("Supported: assign, combinational if/case, one-edge clocked registers, named module instances. Unsupported HDL reports an error.")
        self.diagnostics.setWordWrap(True); source_box.addWidget(self.diagnostics)
        self.tabs.addTab(source_page, "Verilog")
        test_page = QWidget(); test_box = QVBoxLayout(test_page)
        test_box.addWidget(QLabel('Vectors: JSON list of {"inputs": {...}, "expected": {...}}. Use null for X.'))
        self.vectors = QPlainTextEdit()
        self.vectors.setFont(QFont("DejaVu Sans Mono", 9))
        self.vectors.setPlainText('[\n  {"inputs": {"a": 0, "b": 1}, "expected": {"y": 0}},\n  {"inputs": {"a": 1, "b": 1}, "expected": {"y": 1}}\n]')
        test_box.addWidget(self.vectors, 1)
        test_row = QHBoxLayout()
        for label, callback in (("Run LogicSpace", self.run_internal),
                                ("Compare Icarus", self.run_external),
                                ("Export Icarus VCD…", self.export_external_vcd),
                                ("Export report", self.save_report)):
            button = QPushButton(label); button.clicked.connect(callback); test_row.addWidget(button)
        test_box.addLayout(test_row)
        self.results = QTextEdit(); self.results.setReadOnly(True); test_box.addWidget(self.results, 1)
        available, reason = external_availability()
        self.external_status = QLabel(reason); self.external_status.setWordWrap(True)
        test_box.addWidget(self.external_status)
        self.tabs.addTab(test_page, "Test vectors")
        self.refresh_modules()
        self.dirty = False

    def _code_changed(self):
        self.dirty = True
        self.last_results = None
        self.code.show_error(0)
        self.refresh_modules()

    def refresh_modules(self):
        previous = self.module.currentText()
        names = re.findall(r"\bmodule\s+([A-Za-z_][A-Za-z_0-9$]*)", self.code.toPlainText())
        self.module.blockSignals(True)
        self.module.clear(); self.module.addItems(names)
        self.module.setCurrentText(previous if previous in names else (names[-1] if names else ""))
        self.module.blockSignals(False)

    def jump_to_module(self, name):
        if not name: return
        match = re.search(r"\bmodule\s+" + re.escape(name) + r"\b", self.code.toPlainText())
        if match:
            cursor = self.code.textCursor(); cursor.setPosition(match.start())
            self.code.setTextCursor(cursor); self.code.centerCursor()

    def _confirm_discard(self):
        if not self.dirty: return True
        answer = QMessageBox.question(self, "Unsaved HDL", "Discard unsaved HDL changes?",
                                      QMessageBox.Discard | QMessageBox.Cancel)
        return answer == QMessageBox.Discard

    def new_file(self):
        if not self._confirm_discard(): return
        self.path = None; self.code.setPlainText("module new_module(input a, output y);\n  assign y = a;\nendmodule\n")
        self.dirty = False

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open HDL", "", "Verilog (*.v *.sv)")
        if not path or not self._confirm_discard(): return
        try:
            self.code.setPlainText(Path(path).read_text(encoding="utf-8"))
            self.path, self.dirty = Path(path), False
            self.diagnostics.setText(f"Opened {self.path.name}")
        except OSError as error: QMessageBox.warning(self, "HDL", str(error))

    def save_file(self):
        if self.path is None: return self.save_as()
        try:
            self.path.write_text(self.code.toPlainText(), encoding="utf-8")
            self.dirty = False; self.diagnostics.setText(f"Saved {self.path.name}")
        except OSError as error: QMessageBox.warning(self, "HDL", str(error))

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save HDL", str(self.path or Path.home() / "module.v"), "Verilog (*.v *.sv)")
        if not path: return
        self.path = Path(path if Path(path).suffix.lower() in (".v", ".sv") else path + ".v")
        self.save_file()

    def _top(self): return self.module.currentText() or None

    def _failure(self, error):
        self.diagnostics.setText(str(error))
        if isinstance(error, HDLError): self.code.show_error(error.line)

    def validate(self):
        issues = validate_hdl(self.code.toPlainText(), self._top())
        if issues:
            self._failure(HDLError(issues[0]) if not re.match(r"\d+:\d+:", issues[0]) else ValueError(issues[0]))
            match = re.match(r"(\d+):(\d+):", issues[0])
            if match: self.code.show_error(int(match[1]))
            return False
        self.diagnostics.setText("Valid for LogicSpace HDL subset · module connections and widths checked")
        return True

    def import_circuit(self):
        try:
            circuit = prepare_import(import_verilog(self.code.toPlainText(), self._top(),
                                                    clock_generators=self.auto_clock.isChecked()),
                                     self.editor.circuit)
            self.editor._merge(circuit)
            selected = [item for item in self.editor.component_items.values() if item.isSelected()]
            if selected:
                bounds = selected[0].sceneBoundingRect()
                for item in selected[1:]: bounds = bounds.united(item.sceneBoundingRect())
                self.editor.canvas.fitInView(bounds.adjusted(-110, -110, 110, 110), Qt.KeepAspectRatio)
            self.editor.set_status(f"Imported {self._top()} as editable components")
            self.diagnostics.setText(f"Imported {len(circuit.components)} components and {len(circuit.wires)} connections")
            self.tabs.setCurrentIndex(0)
        except (HDLError, ValueError, KeyError) as error: self._failure(error)

    def find_signal_on_canvas(self):
        cursor = self.code.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        signal = cursor.selectedText()
        sources = self.editor.circuit.hdl_sources or {}
        matches = [(sid, source) for sid, source in sources.items()
                   if source["source"] == self.code.toPlainText() and
                   source["module"] == self._top()]
        if not matches:
            self.diagnostics.setText("Import this exact HDL source first. The editor text has changed since import, or no linked circuit exists.")
            return
        for source_id, _ in reversed(matches):
            components = hdl_signal_components(self.editor.circuit, source_id, signal)
            if components:
                component = components[0]
                item = self.editor.component_items.get(component.id)
                if item is not None:
                    self.editor.scene.clearSelection()
                    item.setSelected(True)
                    self.editor.canvas.centerOn(item)
                    self.diagnostics.setText(f"{signal} → {component.kind} on canvas")
                    return
        self.diagnostics.setText(f"No imported canvas component is linked to signal {signal!r}.")

    def open_source_for_component(self, component):
        source_id = component.params.get("_hdl_source_ref")
        record = (self.editor.circuit.hdl_sources or {}).get(source_id)
        if record is None: return False
        if self.code.toPlainText() != record["source"]:
            if not self._confirm_discard(): return False
            self.code.setPlainText(record["source"])
            self.path = None
            self.dirty = False
        self.module.setCurrentText(record["module"])
        line = component.params.get("_hdl_line", 1)
        self.code.show_error(line if isinstance(line, int) else 1)
        self.tabs.setCurrentIndex(0)
        self.editor.show_hdl()
        self.diagnostics.setText("Showing the source snapshot used to import this component.")
        return True

    def export_circuit(self):
        issues = export_issues(self.editor.circuit)
        if issues:
            self.diagnostics.setText("Export blocked:\n" + "\n".join(issues[:12]))
            return
        try:
            self.code.setPlainText(export_verilog(self.editor.circuit))
            self.path = None; self.dirty = True
            self.diagnostics.setText("Generated Verilog from the active circuit. Save the HDL file when ready.")
        except ValueError as error: self._failure(error)

    def _vectors(self):
        data = json.loads(self.vectors.toPlainText())
        if not isinstance(data, list) or len(data) > 5000 or any(not isinstance(x, dict) for x in data):
            raise ValueError("Vectors must be a JSON list of at most 5000 objects")
        return data

    def run_internal(self):
        try:
            results = run_vectors(self.code.toPlainText(), self._vectors(), self._top())
            self.last_results = results
            passed = sum(row["passed"] for row in results)
            self.results.setPlainText(f"{passed}/{len(results)} passed on LogicSpace Simulator\n" +
                                      json.dumps(results, indent=2))
            self.tabs.setCurrentIndex(1)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            self.results.setPlainText(str(error))

    def run_external(self, vcd_path=None):
        if self.worker and self.worker.isRunning(): return
        try: vectors = self._vectors()
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            self.results.setPlainText(str(error)); return
        self.results.setPlainText("Running Icarus in a restricted workspace…")
        self.worker = ExternalWorker(self.code.toPlainText(), vectors, self._top(), self,
                                     vcd_path=vcd_path if isinstance(vcd_path, str) else None)
        self.worker.result.connect(self._external_result)
        self.worker.failed.connect(self.results.setPlainText)
        self.worker.start()

    def export_external_vcd(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export measured Icarus waveform",
                                              "waveform.vcd", "VCD (*.vcd)")
        if path:
            self.run_external(path if path.lower().endswith(".vcd") else path + ".vcd")

    def _external_result(self, rows):
        if self.worker is not None and self.worker.source != self.code.toPlainText():
            self.results.setPlainText("HDL source changed during the external run; result discarded")
            return
        self.last_results = rows
        mismatch = first_equivalence_mismatch(rows)
        summary = (f"First mismatch at vector {mismatch['step']}: {mismatch['signal']} · "
                   f"Icarus={mismatch['external']} LogicSpace={mismatch['logicspace']}\n"
                   if mismatch else "No mismatch in measured output vectors.\n")
        self.results.setPlainText(f"{sum(row['equivalent'] for row in rows)}/{len(rows)} match LogicSpace\n" +
                                  summary +
                                  (f"Icarus VCD saved: {self.worker.vcd_path}\n" if self.worker and self.worker.vcd_path else "") +
                                  json.dumps(rows, indent=2))

    def save_report(self):
        if self.last_results is None:
            self.results.setPlainText("Run the test vectors before exporting a report")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export HDL test report", "hdl-report.json", "JSON (*.json)")
        if not path: return
        try: export_report(path if path.endswith(".json") else path + ".json", self.last_results)
        except (OSError, ValueError) as error: QMessageBox.warning(self, "HDL report", str(error))

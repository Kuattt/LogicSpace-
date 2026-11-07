"""Assembly workspace for a wired LogicSpace CPU, with no interpreter or CPU loop."""
from __future__ import annotations

from pathlib import Path
import json
import re

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import (QColor, QFont, QPainter, QTextCharFormat, QTextCursor,
                           QSyntaxHighlighter)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTabWidget, QPlainTextEdit, QTextEdit, QListWidget,
                               QTableWidget, QTableWidgetItem, QAbstractItemView,
                               QSpinBox, QComboBox, QLineEdit, QFileDialog, QMessageBox,
                               QCompleter, QApplication)

from cpu_board import (create_cpu_circuit, load_program, load_rom_image, reset_bound_cpu,
                       parse_intel_hex, validate_board, program_matches_rom)
from cpu_architecture import (bind_cpu, discover_cpus, export_profile, get_active_binding,
                              get_bindings, match_profile, rebind_cpu, select_cpu,
                              unbind_cpu, validate_mapping)
from cpu_debugger import CpuBreakpointManager, CpuStepper
from cpu_isa import AssemblyError, BY_MNEMONIC, assemble, decode
from engine import Circuit, Simulator
from logic_analyzer_model import format_value
from timing_model import SignalRef


class AssemblyHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        def add(pattern, color, bold=False):
            style = QTextCharFormat(); style.setForeground(QColor(color))
            if bold: style.setFontWeight(QFont.DemiBold)
            self.rules.append((re.compile(pattern, re.IGNORECASE), style))
        add(r"\b(?:" + "|".join(BY_MNEMONIC) + r")\b", "#82baff", True)
        add(r"\bR[0-3]\b", "#77dcc0", True)
        add(r"\b(?:0x[0-9a-f]+|0b[01]+|[0-9]+)\b", "#e8be82")
        add(r"\b\.(?:ORG|BYTE|WORD|EQU)\b", "#cfadf8", True)
        add(r"\b[A-Za-z_][A-Za-z0-9_]*:", "#f0d38b", True)
        add(r";.*$", "#7c899a")

    def highlightBlock(self, text):
        for expression, style in self.rules:
            for match in expression.finditer(text):
                self.setFormat(match.start(), len(match.group()), style)


class _LineArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_area_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_area(event)


class AssemblyEditor(QPlainTextEdit):
    """Monospace editor with line numbers, indentation and mnemonic completion."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Monospace", 11))
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setPlaceholderText("; Write an 8-bit LogicSpace program here\nMOV R0, 10\nHLT")
        self.line_area = _LineArea(self)
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._update_line_area)
        self._update_margin()
        self.highlighter = AssemblyHighlighter(self.document())
        self.completer = QCompleter(sorted(BY_MNEMONIC), self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setWidget(self)
        self.completer.activated.connect(self._complete)

    def line_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margin(self, *_):
        self.setViewportMargins(self.line_area_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy):
        if dy: self.line_area.scroll(0, dy)
        else: self.line_area.update(0, rect.y(), self.line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()): self._update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.line_area.setGeometry(QRect(0, 0, self.line_area_width(), self.contentsRect().height()))

    def paint_line_area(self, event):
        painter = QPainter(self.line_area)
        painter.fillRect(event.rect(), QColor("#18212d"))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.setPen(QColor("#8294a9"))
                painter.drawText(0, top, self.line_area.width() - 5, height,
                                 Qt.AlignRight, str(block.blockNumber() + 1))
            block = block.next(); top += height

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            line = self.textCursor().block().text()
            indent = re.match(r"\s*", line).group()
            super().keyPressEvent(event)
            self.insertPlainText(indent + ("    " if line.rstrip().endswith(":") else ""))
            return
        if event.key() == Qt.Key_Space and event.modifiers() & Qt.ControlModifier:
            self._show_completion(); return
        super().keyPressEvent(event)
        if event.text().isalpha():
            prefix = self._word_under_cursor()
            if len(prefix) >= 2 and any(name.startswith(prefix.upper()) for name in BY_MNEMONIC):
                self._show_completion()

    def _word_under_cursor(self):
        cursor = self.textCursor(); cursor.select(QTextCursor.WordUnderCursor)
        return cursor.selectedText()

    def _show_completion(self):
        prefix = self._word_under_cursor()
        self.completer.setCompletionPrefix(prefix)
        rect = self.cursorRect()
        rect.setWidth(self.completer.popup().sizeHintForColumn(0) + 24)
        self.completer.complete(rect)

    def _complete(self, word):
        cursor = self.textCursor(); cursor.select(QTextCursor.WordUnderCursor)
        cursor.insertText(word)
        self.setTextCursor(cursor)

    def goto_line(self, number):
        block = self.document().findBlockByNumber(max(0, number - 1))
        if not block.isValid(): return
        cursor = QTextCursor(block); self.setTextCursor(cursor); self.centerCursor(); self.setFocus()


class CpuAssemblyPanel(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.bound_circuit = None
        self.bound_binding_key = None
        self.breakpoint_managers = {}
        self.discovered = []
        self.assembled = None
        self._updating = False
        self._running_stepper = False
        self._cancel_stepper = False
        self.last_instruction_count = -1
        root = QVBoxLayout(self)
        root.setContentsMargins(9, 9, 9, 9)
        header = QHBoxLayout()
        for title, callback in (("New CPU", self.create_board), ("Assemble", self.assemble_source),
                                ("Load ROM", self.load_to_rom)):
            button = QPushButton(title); button.clicked.connect(callback); header.addWidget(button)
        root.addLayout(header)
        self.status = QLabel("Create a wired CPU board or open a CPU project")
        self.status.setWordWrap(True); root.addWidget(self.status)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        self._build_assembly_tab()
        self._build_state_tab()
        self._build_memory_tab()
        self._build_debug_tab()
        self._build_architecture_tab()
        self.sync_circuit()

    def _build_assembly_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.source = AssemblyEditor()
        self.source.textChanged.connect(self._source_changed)
        self.source.cursorPositionChanged.connect(self._select_machine_for_line)
        layout.addWidget(self.source, 1)
        self.diagnostics = QListWidget(); self.diagnostics.setMaximumHeight(78)
        self.diagnostics.itemClicked.connect(lambda item: self.source.goto_line(item.data(Qt.UserRole)))
        layout.addWidget(self.diagnostics)
        export_row = QHBoxLayout()
        for title, mode in (("Export BIN", "bin"), ("Export HEX", "hex"),
                            ("Export listing", "listing")):
            button = QPushButton(title); button.clicked.connect(lambda _=False, mode=mode: self.export(mode))
            export_row.addWidget(button)
        layout.addLayout(export_row)
        self.machine = QTableWidget(0, 3)
        self.machine.setHorizontalHeaderLabels(("Addr", "Bytes", "Assembly / line"))
        self.machine.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.machine.cellDoubleClicked.connect(self._machine_line)
        self.machine.horizontalHeader().setStretchLastSection(True)
        self.machine.setMaximumHeight(195)
        layout.addWidget(self.machine)
        self.tabs.addTab(tab, "Assembly")

    def _build_state_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        for title, callback in (("Start / Resume", self.start), ("Pause", self.pause),
                                ("Stop", self.stop), ("Reset", self.reset)):
            button = QPushButton(title); button.clicked.connect(callback); controls.addWidget(button)
        layout.addLayout(controls)
        steps = QHBoxLayout()
        for title, mode in (("Step instruction", "instruction"), ("Step clock", "cycle")):
            button = QPushButton(title); button.clicked.connect(lambda _=False, mode=mode: self.step_mode(mode))
            steps.addWidget(button)
        layout.addLayout(steps)
        speed = QHBoxLayout(); speed.addWidget(QLabel("Execution speed"))
        self.speed = QSpinBox(); self.speed.setRange(1, 20)
        self.speed.setValue(self.editor.speed.value())
        self.speed.valueChanged.connect(self.editor.speed.setValue)
        self.editor.speed.valueChanged.connect(self.speed.setValue)
        speed.addWidget(self.speed); layout.addLayout(speed)
        self.cpu_state = QLabel("No CPU board")
        self.cpu_state.setWordWrap(True); self.cpu_state.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.cpu_state.setAlignment(Qt.AlignTop)
        layout.addWidget(self.cpu_state, 1)
        self.tabs.addTab(tab, "CPU state")

    def _build_memory_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Harvard map: ROM 00–FF · RAM 00–BF · stack C0–FF (same RAM)"))
        row = QHBoxLayout()
        self.memory_region = QComboBox(); self.memory_region.addItems(("RAM", "ROM"))
        self.memory_region.currentTextChanged.connect(self.refresh_memory)
        row.addWidget(self.memory_region)
        self.memory_address = QSpinBox(); self.memory_address.setRange(0, 255)
        self.memory_address.setPrefix("0x"); self.memory_address.setDisplayIntegerBase(16)
        self.memory_address.valueChanged.connect(self.inspect_address)
        row.addWidget(self.memory_address)
        self.memory_value = QLineEdit(); self.memory_value.setPlaceholderText("0x00–0xFF")
        row.addWidget(self.memory_value)
        write = QPushButton("Write RAM"); write.clicked.connect(self.write_memory)
        row.addWidget(write); layout.addLayout(row)
        self.address_info = QLabel("Select an address")
        layout.addWidget(self.address_info)
        self.memory_table = QTableWidget(16, 17)
        self.memory_table.setHorizontalHeaderLabels(["Address"] + [f"{i:X}" for i in range(16)])
        self.memory_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.memory_table.cellClicked.connect(self._memory_clicked)
        for column in range(17): self.memory_table.setColumnWidth(column, 36 if column else 67)
        layout.addWidget(self.memory_table, 1)
        dump = QPushButton("Export memory dump…"); dump.clicked.connect(self.export_dump)
        layout.addWidget(dump)
        self.tabs.addTab(tab, "Memory")

    def _build_debug_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        row = QHBoxLayout()
        self.break_kind = QComboBox(); self.break_kind.addItems(("line", "address", "register", "memory"))
        row.addWidget(self.break_kind)
        self.break_target = QSpinBox(); self.break_target.setRange(0, 255)
        row.addWidget(self.break_target)
        self.break_value = QLineEdit(); self.break_value.setPlaceholderText("R value or read/write")
        row.addWidget(self.break_value)
        add = QPushButton("+ Break"); add.clicked.connect(self.add_breakpoint)
        row.addWidget(add); layout.addLayout(row)
        self.break_list = QListWidget(); self.break_list.setMaximumHeight(125)
        layout.addWidget(self.break_list)
        remove = QPushButton("Remove selected breakpoint"); remove.clicked.connect(self.remove_breakpoint)
        layout.addWidget(remove)
        row = QHBoxLayout()
        for title, mode in (("Step Into", "instruction"), ("Step Over", "over"), ("Step Out", "out")):
            button = QPushButton(title); button.clicked.connect(lambda _=False, mode=mode: self.step_mode(mode))
            row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(QLabel("INSTRUCTION HISTORY · double-click to open Time Travel"))
        self.instruction_history = QListWidget()
        self.instruction_history.itemDoubleClicked.connect(self.open_history_step)
        layout.addWidget(self.instruction_history, 1)
        self.tabs.addTab(tab, "Debug")

    def _build_architecture_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("DETECT CPU · physical ports, BusWire widths and ISA 2.1 datapath"))
        row = QHBoxLayout()
        for title, callback in (("Detect", self.detect_architectures),
                                ("Validate", self.validate_architecture),
                                ("Bind", self.bind_architecture),
                                ("Rebind", self.rebind_architecture)):
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        layout.addLayout(row)
        self.arch_candidates = QListWidget()
        self.arch_candidates.setStyleSheet("QListWidget::item:selected { background: #285f93; color: white; }")
        self.arch_candidates.setMaximumHeight(110)
        self.arch_candidates.currentRowChanged.connect(self._show_candidate)
        layout.addWidget(self.arch_candidates)
        layout.addWidget(QLabel("COMPONENT MAPPING · identified by connected ports"))
        self.arch_mapping = QTableWidget(0, 3)
        self.arch_mapping.setHorizontalHeaderLabels(("Role", "Component", "ID"))
        self.arch_mapping.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.arch_mapping.horizontalHeader().setStretchLastSection(True)
        self.arch_mapping.setColumnWidth(0, 90)
        self.arch_mapping.setColumnWidth(1, 155)
        self.arch_mapping.setMaximumHeight(190)
        layout.addWidget(self.arch_mapping)
        layout.addWidget(QLabel("ASSEMBLY BINDING · choose which CPU this panel controls"))
        self.arch_name = QLineEdit(); self.arch_name.setPlaceholderText("Architecture name (optional)")
        layout.addWidget(self.arch_name)
        row = QHBoxLayout()
        self.arch_bindings = QComboBox()
        self.arch_bindings.currentIndexChanged.connect(self._choose_binding)
        row.addWidget(self.arch_bindings, 1)
        unbind = QPushButton("Unbind"); unbind.clicked.connect(self.unbind_architecture)
        row.addWidget(unbind); layout.addLayout(row)
        row = QHBoxLayout()
        for title, callback in (("Export profile", self.save_profile),
                                ("Import profile", self.import_profile),
                                ("Load BIN", lambda: self.load_image("bin")),
                                ("Load HEX", lambda: self.load_image("hex"))):
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        layout.addLayout(row)
        self.arch_report = QTextEdit(); self.arch_report.setReadOnly(True)
        layout.addWidget(self.arch_report, 1)
        self.tabs.addTab(tab, "Architecture")

    def _binding(self):
        return get_active_binding(self.editor.circuit)

    def _binding_key(self, binding):
        return binding.get("ids", {}).get("control") if binding else None

    def _refresh_binding_choices(self):
        circuit = self.editor.circuit
        active = self._binding()
        self.arch_bindings.blockSignals(True)
        self.arch_bindings.clear()
        for binding in get_bindings(circuit):
            self.arch_bindings.addItem(binding.get("name", "CPU"),
                                       binding.get("id", self._binding_key(binding)))
        index = self.arch_bindings.findData(active.get("id", self._binding_key(active)) if active else None)
        self.arch_bindings.setCurrentIndex(index)
        self.arch_bindings.blockSignals(False)

    def detect_architectures(self):
        self.discovered = discover_cpus(self.editor.circuit)
        self.arch_candidates.clear()
        bindings = get_bindings(self.editor.circuit)
        for index, candidate in enumerate(self.discovered, 1):
            control = self.editor.circuit.components[candidate.ids["control"]]
            bound = next((item for item in bindings
                          if item["ids"].get("control") == control.id), None)
            label = bound.get("name") if bound else control.params.get("label") or f"CPU {index}"
            self.arch_candidates.addItem(f"{label} · {'ISA compatible' if candidate.compatible else str(len(candidate.issues)) + ' issue(s)'}")
        active = self._binding()
        selected = next((index for index, candidate in enumerate(self.discovered)
                         if active and candidate.ids["control"] == active["ids"].get("control")), 0)
        if self.discovered: self.arch_candidates.setCurrentRow(selected)
        else: self.arch_report.setPlainText("No ISA Control Unit found. Add one and wire the CPU datapath.")
        self._refresh_binding_choices()
        return self.discovered

    def _candidate(self):
        index = self.arch_candidates.currentRow()
        return self.discovered[index] if 0 <= index < len(self.discovered) else None

    def _show_candidate(self, *_):
        candidate = self._candidate()
        self.arch_mapping.setRowCount(0)
        if candidate is None: return
        bound = next((item for item in get_bindings(self.editor.circuit)
                      if item["ids"].get("control") == candidate.ids["control"]), None)
        self.arch_name.setText(bound.get("name") if bound else candidate.profile["name"] if candidate.profile else "")
        for role, cid in candidate.ids.items():
            component = self.editor.circuit.components.get(cid)
            row = self.arch_mapping.rowCount(); self.arch_mapping.insertRow(row)
            for column, value in enumerate((role, component.kind if component else "missing", cid[:12])):
                self.arch_mapping.setItem(row, column, QTableWidgetItem(value))
        self.arch_report.setPlainText(
            "ISA 2.1 compatible. All required physical links are present." if candidate.compatible else
            "Architecture diagnostics:\n" + "\n".join(f"• {issue}" for issue in candidate.issues))
        item = self.editor.component_items.get(candidate.ids["control"])
        if item is not None: self.editor.canvas.centerOn(item)

    def validate_architecture(self):
        candidate = self._candidate()
        if candidate is None: self.detect_architectures(); candidate = self._candidate()
        if candidate is not None:
            refreshed = next((item for item in discover_cpus(self.editor.circuit)
                              if item.ids["control"] == candidate.ids["control"]), None)
            if refreshed is not None:
                self.discovered[self.arch_candidates.currentRow()] = refreshed
                self._show_candidate()

    def _after_binding_change(self):
        self.editor.sim.evaluate()
        self.editor.time_history.record_mutation(self.editor.sim)
        self.editor._sync_time_branch()
        self.sync_circuit()
        self.detect_architectures()
        self.editor.refresh()
        self.editor.dirty = True; self.editor._title()

    def bind_architecture(self):
        candidate = self._candidate()
        if candidate is None: self.detect_architectures(); candidate = self._candidate()
        if candidate is None: return
        try:
            bind_cpu(self.editor.circuit, candidate, name=self.arch_name.text().strip() or None,
                     source=self.source.toPlainText() or "NOP\nHLT\n")
            self._after_binding_change()
            self.status.setText("Assembly bound to validated physical CPU")
        except ValueError as error: self.arch_report.setPlainText(str(error))

    def rebind_architecture(self):
        candidate, binding = self._candidate(), self._binding()
        if candidate is None or binding is None: return
        try:
            if "id" in binding:
                rebind_cpu(self.editor.circuit, binding["id"], candidate)
            else:
                bind_cpu(self.editor.circuit, candidate, name=binding.get("name"),
                         source=binding["source"])
            self._after_binding_change()
            self.status.setText("CPU binding refreshed from physical connections")
        except (ValueError, KeyError) as error: self.arch_report.setPlainText(str(error))

    def unbind_architecture(self):
        binding = self._binding()
        if binding is None: return
        unbind_cpu(self.editor.circuit, binding.get("id"))
        self._after_binding_change()
        self.status.setText("Assembly unbound; circuit components remain on the canvas")

    def _choose_binding(self, index):
        if index < 0 or not self.arch_bindings.itemData(index): return
        if self.editor.circuit.cpu_architectures is None: return
        try:
            select_cpu(self.editor.circuit, self.arch_bindings.itemData(index))
            self._after_binding_change()
            self.status.setText("Selected CPU; other bound CPU clocks paused")
        except ValueError as error: self.arch_report.setPlainText(str(error))

    def save_profile(self):
        binding = self._binding()
        if binding is None: return
        issues = validate_mapping(self.editor.circuit, binding["ids"])
        if issues: self.arch_report.setPlainText("Cannot export invalid CPU:\n" + "\n".join(issues)); return
        path, _ = QFileDialog.getSaveFileName(self, "Export CPU profile", "cpu_profile.json")
        if path:
            try: Path(path).write_text(export_profile(binding), encoding="utf-8")
            except OSError as error: self.arch_report.setPlainText(str(error))

    def import_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import CPU profile", "", "JSON (*.json)")
        if not path: return
        candidate = self._candidate()
        if candidate is None: self.detect_architectures(); candidate = self._candidate()
        if candidate is None: return
        try:
            profile = json.loads(Path(path).read_text(encoding="utf-8"))
            match_profile(candidate, profile)
            bind_cpu(self.editor.circuit, candidate, name=profile["name"],
                     source=self.source.toPlainText() or "NOP\nHLT\n")
            self._after_binding_change()
        except (ValueError, OSError, KeyError) as error: self.arch_report.setPlainText(str(error))

    def load_image(self, mode):
        try: binding = self._binding(); validate_board(self.editor.circuit, binding)
        except ValueError as error: self.status.setText(str(error)); return
        path, _ = QFileDialog.getOpenFileName(self, "Load ROM image", "", "BIN (*.bin);;Intel HEX (*.hex)")
        if not path: return
        try:
            raw = Path(path).read_bytes()
            image = raw if mode == "bin" else parse_intel_hex(raw.decode("utf-8"))
            self.editor.push_history()
            count = load_rom_image(self.editor.circuit, image, binding, mode)
            if len(get_bindings(self.editor.circuit)) > 1:
                reset_bound_cpu(self.editor.sim, binding)
            else:
                self.editor.sim.reset()
            self.editor.render()
            self.assembled = None
            self._populate_raw_rom()
            self.editor.dirty = True; self.editor._title()
            self.status.setText(f"Loaded {count} bytes into selected physical ROM · source mapping unavailable unless bytes match")
        except (ValueError, UnicodeDecodeError, OSError) as error: self.status.setText(str(error))

    def sync_circuit(self):
        circuit = self.editor.circuit
        binding = self._binding()
        key = self._binding_key(binding)
        if circuit is self.bound_circuit and key == self.bound_binding_key:
            try:
                validate_board(circuit, binding)
                if self.editor.cpu_breakpoints.program is None:
                    self.editor.cpu_breakpoints.bind(circuit, binding)
            except ValueError as error:
                self.editor.cpu_breakpoints.program = None
                self.status.setText(str(error))
            self._refresh_binding_choices()
            return
        if circuit is not self.bound_circuit:
            self.breakpoint_managers = {}
        self.bound_circuit = circuit
        self.bound_binding_key = key
        self.editor.cpu_breakpoints = self.breakpoint_managers.setdefault(key, CpuBreakpointManager())
        self.assembled = None
        self._updating = True
        workspace = binding or {}
        self.source.setPlainText(workspace.get("draft_source", workspace.get("source", "")))
        self._updating = False
        self.machine.setRowCount(0)
        self.diagnostics.clear()
        try:
            validate_board(circuit, binding)
            self.editor.cpu_breakpoints.bind(circuit, binding)
            self.assembled = assemble(workspace["source"])
            self._populate_machine()
            self.status.setText("Wired CPU board ready · Assemble, then Load ROM to run edits" if
                                program_matches_rom(circuit, self.assembled, binding) else
                                "ROM differs from loaded Assembly source; source-line mapping is unavailable")
        except ValueError as error:
            self.status.setText(str(error))
        self.break_list.clear()
        for item in self.editor.cpu_breakpoints.items.values():
            self.break_list.addItem(f"{item.kind} {item.target}" + (f" = {item.expected}" if item.expected is not None else ""))
            self.break_list.item(self.break_list.count() - 1).setData(Qt.UserRole, item.id)
        self._refresh_binding_choices()
        self.detect_architectures()
        self.refresh_state(force=True)

    def _source_changed(self):
        workspace = self._binding()
        if self._updating or workspace is None: return
        self.assembled = None
        self.machine.setRowCount(0)
        self.diagnostics.clear()
        workspace["draft_source"] = self.source.toPlainText()
        self.editor.dirty = True
        self.editor._title()
        self.status.setText("Assembly source changed · Assemble to refresh machine code")

    def create_board(self):
        if self.editor.circuit.components and not self.editor._confirm_discard(): return
        starter = "; LogicSpace 8-bit CPU\nMOV R0, 10\nMOV R1, 5\nADD R0, R1\nSTORE R0, 0x20\nHLT\n"
        circuit = create_cpu_circuit(starter)
        self.editor.timer.stop()
        self.editor.circuit, self.editor.sim, self.editor.path = circuit, Simulator(circuit), None
        self.editor.history.clear(); self.editor.future.clear()
        self.editor.timing_panel.sync_circuit(clear=True)
        self.editor.render(); self.editor.populate_library()
        self.editor.dirty = True; self.editor._title()
        self.status.setText("Reference CPU created. Edit Assembly and click Load ROM.")

    def assemble_source(self):
        self.diagnostics.clear()
        try:
            self.assembled = assemble(self.source.toPlainText())
            self._populate_machine()
            self.status.setText(f"Assembled {len(self.assembled.used_addresses)} ROM byte(s); Load ROM to execute")
            return self.assembled
        except AssemblyError as error:
            self.assembled = None
            self.machine.setRowCount(0)
            self.diagnostics.addItem(str(error))
            self.diagnostics.item(0).setData(Qt.UserRole, error.line)
            self.source.goto_line(error.line)
            self.status.setText(str(error))
            return None

    def _populate_machine(self):
        if self.assembled is None: return
        self.machine.setRowCount(len(self.assembled.listing))
        for row, entry in enumerate(self.assembled.listing):
            for column, value in enumerate((f"{entry.address:02X}", entry.data.hex(" ").upper(),
                                            f"{entry.source.strip()}  · line {entry.line}")):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, entry.line)
                self.machine.setItem(row, column, item)

    def _populate_raw_rom(self):
        binding = self._binding()
        if binding is None: return
        rom = self.editor.circuit.components[binding["ids"]["rom"]]
        contents = rom.params.get("contents", {})
        self.machine.setRowCount(16)
        for row in range(16):
            data = bytes(contents.get(str(row * 16 + offset), 0) for offset in range(16))
            for column, value in enumerate((f"{row * 16:02X}", data.hex(" ").upper(), "Raw ROM image")):
                self.machine.setItem(row, column, QTableWidgetItem(value))

    def _machine_line(self, row, column):
        item = self.machine.item(row, column)
        if item and isinstance(item.data(Qt.UserRole), int):
            self.source.goto_line(item.data(Qt.UserRole))

    def _select_machine_for_line(self):
        line = self.source.textCursor().blockNumber() + 1
        for row in range(self.machine.rowCount()):
            item = self.machine.item(row, 0)
            if item and item.data(Qt.UserRole) == line:
                self.machine.selectRow(row)
                return

    def load_to_rom(self):
        if self.assemble_source() is None: return
        try:
            binding = self._binding()
            validate_board(self.editor.circuit, binding)
            self.editor.push_history()
            load_program(self.editor.circuit, self.source.toPlainText(), binding)
            binding["draft_source"] = self.source.toPlainText()
            if len(get_bindings(self.editor.circuit)) > 1:
                reset_bound_cpu(self.editor.sim, binding)
            else:
                self.editor.sim.reset()
            self.editor.render()
            self.editor.cpu_breakpoints.bind(self.editor.circuit, binding)
            self.editor.dirty = True; self.editor._title()
            self.status.setText("Program loaded into wired ROM; CPU reset to step 0")
            self.refresh_state(force=True)
        except (ValueError, TypeError) as error:
            self.status.setText(str(error))

    def export(self, mode):
        if self.assembled is None and self.assemble_source() is None: return
        suffix = {"bin": ".bin", "hex": ".hex", "listing": ".lst"}[mode]
        path, _ = QFileDialog.getSaveFileName(self, "Export assembled program", "program" + suffix)
        if not path: return
        try:
            output = self.assembled.image if mode == "bin" else (
                self.assembled.intel_hex() if mode == "hex" else self.assembled.listing_text())
            if isinstance(output, bytes): Path(path).write_bytes(output)
            else: Path(path).write_text(output, encoding="utf-8")
            self.status.setText(f"Exported {path}")
        except OSError as error: QMessageBox.warning(self, "Export", str(error))

    def _ids(self):
        return validate_board(self.editor.circuit, self._binding())

    def start(self):
        try:
            ids = self._ids()
            if self.editor.circuit.components[ids["control"]].state.get("phase") == "HALT":
                raise ValueError("CPU halted; Reset or Load ROM before starting")
            if not self.editor.timer.isActive(): self.editor.toggle_run()
            self.status.setText("CPU running on the LogicSpace clock")
        except ValueError as error: self.status.setText(str(error))

    def pause(self):
        if self.editor.timer.isActive(): self.editor.toggle_run()
        self.status.setText("CPU paused; state preserved")

    def stop(self):
        self.pause()
        self.status.setText("Automatic execution stopped; Reset clears volatile state")

    def reset(self):
        try: self._ids()
        except ValueError as error: self.status.setText(str(error)); return
        if len(get_bindings(self.editor.circuit)) > 1:
            self.editor.timer.stop(); self.editor.run_button.setText("▶ Run")
            reset_bound_cpu(self.editor.sim, self._binding())
            self.editor.time_history.record_mutation(self.editor.sim)
            self.editor._sync_time_branch()
            self.editor.cpu_breakpoints.arm(self.editor.circuit)
            self.editor.refresh(); self.editor.time_panel.refresh_panel()
            self.editor.dirty = True; self.editor._title()
        else:
            self.editor.reset(); self.editor.cpu_breakpoints.arm(self.editor.circuit)
        self.refresh_state(force=True)

    def step_mode(self, mode):
        if self._running_stepper:
            self._cancel_stepper = True; return
        self._running_stepper = True; self._cancel_stepper = False
        try:
            self._ids()
            self.editor.timer.stop(); self.editor.run_button.setText("▶ Run")
            self.editor.last_break_events = []
            self.editor.last_cpu_events = []
            count = 0
            def advance():
                nonlocal count
                self.editor.step()
                count += 1
                if count % 16 == 0: QApplication.processEvents()
            runner = CpuStepper(self.editor.sim, advance, self._binding())
            interrupted = lambda: self._cancel_stepper or bool(self.editor.last_break_events or
                                                                self.editor.last_cpu_events)
            if mode == "cycle": completed = runner.step_clock_cycle(interrupted=interrupted)
            elif mode == "over": completed = runner.step_over(interrupted=interrupted)
            elif mode == "out": completed = runner.step_out(interrupted=interrupted)
            else: completed = runner.step_instruction(interrupted=interrupted)
            self.refresh_state(force=True)
            if not completed and runner.state.get("phase") == "HALT":
                self.status.setText("CPU halted; Reset or Load ROM before stepping")
        except ValueError as error:
            self.status.setText(str(error))
        finally:
            self._running_stepper = False

    def refresh_state(self, force=False):
        try: ids = self._ids()
        except ValueError:
            self.cpu_state.setText("No valid wired CPU board")
            return
        circuit, sim = self.editor.circuit, self.editor.sim
        if self.editor.cpu_breakpoints.program and not program_matches_rom(circuit, self.editor.cpu_breakpoints.program, self._binding()):
            self.status.setText("ROM differs from loaded Assembly source; source-line breakpoints are disabled")
        control = circuit.components[ids["control"]].state
        pc = circuit.components[ids["pc"]].state.get("value", 0)
        ir = circuit.components[ids["ir"]].state.get("value", 0)
        registers = circuit.components[ids["registers"]].state.get("words", {})
        alu_bits = SignalRef.bus_port(ids["alu"], "Q", "output").value(sim)
        rom = circuit.components[ids["rom"]].params.get("contents", {})
        image = bytes(rom.get(str(index), 0) for index in range(256))
        current_address = control.get("current_pc", pc)
        last = control.get("last_completed", {})
        lines = [f"Tick {circuit.tick} · Clock edges are not completed instructions",
                 f"PC  {self._hex(pc)}    IR  {self._hex(ir)}",
                 f"Phase  {control.get('phase', 'FETCH')}    Completed  {control.get('instructions', 0)}",
                 f"Current  {self._hex(current_address)}  {decode(image, current_address or 0)}",
                 f"Next at PC  {decode(image, pc or 0)}",
                 f"ALU  {format_value(alu_bits, 'hex')}",
                 "Flags  Z={} C={} N={} V={}".format(*(self._bit(control.get(name, 0)) for name in
                                                        ("zero", "carry", "negative", "overflow"))),
                 "Registers  " + "  ".join(f"R{i}={self._hex(registers.get(str(i), 0))}" for i in range(4)),
                 f"Stack pointer  {self._hex(control.get('sp', 255))}    CALL depth  {control.get('call_depth', 0)}",
                 f"Last completed  {last.get('mnemonic', '—')} at {self._hex(last.get('address'))}"]
        if control.get("fault"): lines.append("FAULT  " + control["fault"])
        if control.get("phase") == "HALT" and not control.get("fault"): lines.append("HALTED")
        self.cpu_state.setText("\n".join(lines))
        count = control.get("instructions", 0)
        if force or count != self.last_instruction_count:
            self.last_instruction_count = count
            self.refresh_memory()
            self.refresh_history()

    @staticmethod
    def _hex(value):
        return "X" if value is None else f"0x{value:02X}"

    @staticmethod
    def _bit(value):
        return "X" if value is None else str(value)

    def refresh_memory(self, *_):
        try: ids = self._ids()
        except ValueError: return
        if self.memory_region.currentText() == "ROM":
            values = self.editor.circuit.components[ids["rom"]].params.get("contents", {})
        else:
            values = self.editor.circuit.components[ids["ram"]].state.get("memory", {})
        for row in range(16):
            self.memory_table.setItem(row, 0, QTableWidgetItem(f"{row * 16:02X}"))
            for column in range(16):
                value = values.get(str(row * 16 + column), 0)
                cell = QTableWidgetItem("XX" if value is None else f"{value:02X}")
                if self.memory_region.currentText() == "RAM" and row >= 12:
                    cell.setForeground(QColor("#e4b46f"))
                self.memory_table.setItem(row, column + 1, cell)
        self.inspect_address()

    def _memory_clicked(self, row, column):
        if column > 0: self.memory_address.setValue(row * 16 + column - 1)

    def inspect_address(self, *_):
        try: ids = self._ids()
        except ValueError: return
        address = self.memory_address.value()
        region = self.memory_region.currentText()
        component = self.editor.circuit.components[ids["rom" if region == "ROM" else "ram"]]
        values = component.params.get("contents", {}) if region == "ROM" else component.state.get("memory", {})
        value = values.get(str(address), 0)
        tag = " · stack" if region == "RAM" and address >= 0xC0 else ""
        self.address_info.setText(f"{region} 0x{address:02X}{tag} = {self._hex(value)}")

    def write_memory(self):
        try:
            ids = self._ids()
            if self.memory_region.currentText() != "RAM":
                raise ValueError("ROM is loaded from Assembly; choose RAM to edit a byte")
            raw = self.memory_value.text().strip()
            value = None if raw.upper() == "X" else int(raw, 0)
            if value is not None and not 0 <= value <= 255:
                raise ValueError("RAM byte must be 0–255 or X")
            ram = self.editor.circuit.components[ids["ram"]]
            memory = dict(ram.state.get("memory", {}))
            memory[str(self.memory_address.value())] = value
            ram.state["memory"] = memory
            self.editor.sim.evaluate()
            self.editor.time_history.record_mutation(self.editor.sim)
            self.editor._sync_time_branch()
            self.editor.refresh(); self.editor.time_panel.refresh_panel()
            self.editor.dirty = True; self.editor._title()
            self.refresh_memory()
            self.status.setText("RAM edited; Time Travel captured the new state")
        except (ValueError, TypeError) as error:
            self.status.setText(str(error))

    def export_dump(self):
        try:
            ids = self._ids()
            region = self.memory_region.currentText()
            component = self.editor.circuit.components[ids["rom" if region == "ROM" else "ram"]]
            values = component.params.get("contents", {}) if region == "ROM" else component.state.get("memory", {})
            if any(value is None for value in values.values()):
                raise ValueError("Memory contains X; raw byte dump cannot represent it")
            data = bytes(values.get(str(index), 0) for index in range(256))
            path, _ = QFileDialog.getSaveFileName(self, "Export memory dump", region.lower() + ".bin")
            if path: Path(path).write_bytes(data); self.status.setText(f"Exported {path}")
        except (ValueError, OSError) as error: self.status.setText(str(error))

    def add_breakpoint(self):
        try:
            self._ids()
            kind, target = self.break_kind.currentText(), self.break_target.value()
            raw = self.break_value.text().strip().lower()
            expected = (int(raw, 0) if kind == "register" else raw or "any" if kind == "memory" else None)
            item = self.editor.cpu_breakpoints.add(kind, target, expected)
            self.break_list.addItem(f"{item.kind} {item.target}" + (f" = {item.expected}" if item.expected is not None else ""))
            self.break_list.item(self.break_list.count() - 1).setData(Qt.UserRole, item.id)
        except ValueError as error: self.status.setText(str(error))

    def remove_breakpoint(self):
        item = self.break_list.currentItem()
        if item is None: return
        self.editor.cpu_breakpoints.remove(item.data(Qt.UserRole))
        self.break_list.takeItem(self.break_list.row(item))

    def refresh_history(self):
        self.instruction_history.clear()
        try:
            ids = self._ids()
            snapshots = self.editor.time_history.snapshots
            branch = self.editor.time_history.branch
        except (ValueError, AttributeError): return
        seen = set()
        for step, uid in reversed(branch.states.items()):
            snapshot = snapshots.get(uid)
            if snapshot is None: continue
            record = snapshot.states.get(ids["control"], {}).get("last_completed")
            if not record or record.get("step") in seen: continue
            seen.add(record["step"])
            address = record.get("address", 0)
            line = (self.editor.cpu_breakpoints.program.address_to_line.get(address)
                    if self.editor.cpu_breakpoints.program and self.editor.cpu_breakpoints.source_sync else None)
            text = f"Step {record['step']} · 0x{address:02X} {record['mnemonic']}"
            if line: text += f" · line {line}"
            self.instruction_history.addItem(text)
            self.instruction_history.item(self.instruction_history.count() - 1).setData(Qt.UserRole, record["step"])
            if len(seen) >= 100: break

    def open_history_step(self, item):
        try: self.editor.navigate_time(item.data(Qt.UserRole))
        except ValueError as error: self.status.setText(str(error))

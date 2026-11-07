"""Qt manager, sequence editor and result views for isolated LogicSpace tests."""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QSplitter,
                               QLabel, QPushButton, QLineEdit, QListWidget, QListWidgetItem,
                               QTableWidget, QTableWidgetItem, QTabWidget, QSpinBox, QComboBox,
                               QCheckBox, QMessageBox, QInputDialog, QDialogButtonBox, QWidget,
                               QAbstractItemView)

from engine import ANALOG, BusWire, bus_ports, pins, Simulator
from timing_model import SignalRef
from timing_view import WaveformView
from testbench_model import (TestbenchSession, empty_package, new_testbench, new_id,
                             signal_ref_dict, signal_ref_from_dict, signal_width, validate_package)
from tracing_model import value_text


def display_value(value):
    if isinstance(value, (tuple, list)):
        return "0b" + "".join("X" if bit is None else str(bit) for bit in reversed(value))
    return "X" if value is None else str(value)


def named_result_value(result, value):
    if isinstance(value, dict):
        return ", ".join(f"{result.signal_labels.get(key, key)}={display_value(bit)}"
                         for key, bit in value.items())
    return display_value(value)


def parse_cell(text, width=1):
    value = text.strip().upper()
    if value in ("", "—", "-"):
        return False, None
    if value == "X":
        return True, None
    if width == 1 and value in ("0", "1"):
        return True, int(value)
    if width > 1:
        if value.startswith("0B") or "X" in value:
            digits = value[2:] if value.startswith("0B") else value
            if len(digits) != width or any(char not in "01X" for char in digits):
                raise ValueError(f"Enter exactly {width} binary digits (0, 1 or X)")
            return True, [None if char == "X" else int(char) for char in reversed(digits)]
        try: number = int(value, 16 if value.startswith("0X") else 10)
        except ValueError: raise ValueError("Use decimal, 0x hexadecimal, 0b binary or X") from None
        if not 0 <= number < (1 << width):
            raise ValueError(f"Value must fit in {width} bits")
        return True, number
    raise ValueError("Step values must be blank, 0, 1 or X")


class TestbenchSignalPicker(QDialog):
    def __init__(self, circuit, role, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose circuit inputs" if role == "drive" else "Choose observed signals")
        self.resize(500, 450)
        layout = QVBoxLayout(self)
        search = QLineEdit()
        search.setPlaceholderText("Search components or pins…")
        layout.addWidget(search)
        self.items = QListWidget()
        self.items.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.items)
        for component in circuit.components.values():
            if component.kind in ANALOG:
                continue
            inputs, outputs = pins(component, circuit.blocks)
            if role == "drive":
                if component.kind not in ("INPUT", "CONST", "Bus Input"):
                    continue
                candidates = [("output", pin) for pin in outputs]
            else:
                candidates = [("output", pin) for pin in outputs] + [("input", pin) for pin in inputs]
            for direction, pin in candidates:
                ref = SignalRef.component_pin(component.id, pin, direction)
                item = QListWidgetItem(ref.label(circuit) + f" · {direction}")
                item.setData(Qt.UserRole, ref)
                self.items.addItem(item)
            for direction, ports in bus_ports(component, circuit.blocks).items():
                if role == "drive" and direction != "output": continue
                for port in ports:
                    ref = SignalRef.bus_port(component.id, port, direction)
                    item = QListWidgetItem("Bus · " + ref.label(circuit))
                    item.setData(Qt.UserRole, ref)
                    self.items.addItem(item)
        if role == "observe":
            for wire in circuit.wires.values():
                ref = SignalRef.wire(wire.id)
                item = QListWidgetItem("Wire · " + ref.label(circuit))
                item.setData(Qt.UserRole, ref)
                self.items.addItem(item)
                if isinstance(wire, BusWire):
                    for index in range(wire.width):
                        bit_ref = SignalRef.wire_bit(wire.id, index)
                        bit_item = QListWidgetItem("Bus bit · " + bit_ref.label(circuit))
                        bit_item.setData(Qt.UserRole, bit_ref)
                        self.items.addItem(bit_item)
        search.textChanged.connect(lambda text: [self.items.item(i).setHidden(
            text.casefold() not in self.items.item(i).text().casefold())
            for i in range(self.items.count())])
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_refs(self):
        return [item.data(Qt.UserRole) for item in self.items.selectedItems()]


class AssertionDialog(QDialog):
    KINDS = (("equals", "Output equals"), ("not_equals", "Output does not equal"),
             ("equals_at", "Equals at step"), ("stable", "Remains stable"),
             ("changes_after", "Changes after event"), ("all_equal", "Multiple outputs equal"))

    def __init__(self, bench, circuit, existing=None, parent=None):
        super().__init__(parent)
        self.bench, self.existing, self.circuit = bench, existing, circuit
        self.setWindowTitle("Edit assertion" if existing else "Add assertion")
        self.resize(480, 540)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        for key, label in self.KINDS: self.kind.addItem(label, key)
        self.target = QComboBox()
        self.event = QComboBox()
        for entry in bench["signals"]:
            ref = signal_ref_from_dict(entry["ref"])
            label = ref.label(circuit)
            if entry["role"] == "observe": self.target.addItem(label, entry["id"])
            self.event.addItem(label, entry["id"])
        self.value = QComboBox(); self.value.addItems(("0", "1", "X")); self.value.setEditable(True)
        self.at = QSpinBox(); self.at.setRange(0, 9999)
        self.start = QSpinBox(); self.start.setRange(0, 9999)
        self.end = QSpinBox(); self.end.setRange(0, 9999); self.end.setValue(1)
        self.within = QSpinBox(); self.within.setRange(0, 9999); self.within.setValue(1)
        self.event_from = QComboBox(); self.event_from.addItems(("0", "1", "X")); self.event_from.setEditable(True)
        self.event_to = QComboBox(); self.event_to.addItems(("0", "1", "X")); self.event_to.setEditable(True); self.event_to.setCurrentText("1")
        for label, widget in (("Condition", self.kind), ("Output", self.target), ("Value", self.value),
                              ("At step", self.at), ("Range start", self.start), ("Range end", self.end),
                              ("Event signal", self.event), ("Event from", self.event_from),
                              ("Event to", self.event_to), ("Within steps", self.within)):
            form.addRow(label, widget)
        root.addLayout(form)
        root.addWidget(QLabel("For multiple outputs, choose an expected value for each selected output:"))
        self.multi = QTableWidget(self.target.count(), 2)
        self.multi.setHorizontalHeaderLabels(("Output", "Expected"))
        self.multi.horizontalHeader().setStretchLastSection(True)
        self.multi.setFixedHeight(155)
        for row in range(self.target.count()):
            self.multi.setItem(row, 0, QTableWidgetItem(self.target.itemText(row)))
            choices = QComboBox(); choices.addItems(("—", "0", "1", "X")); choices.setEditable(True)
            self.multi.setCellWidget(row, 1, choices)
        root.addWidget(self.multi)
        hint = QLabel("Blank expected values are ignored. X is an explicit unknown value.")
        hint.setObjectName("hint"); hint.setWordWrap(True)
        root.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        if existing:
            self.kind.setCurrentIndex(self.kind.findData(existing["kind"]))
            if "signal" in existing: self.target.setCurrentIndex(self.target.findData(existing["signal"]))
            if "value" in existing: self.value.setCurrentText(display_value(existing["value"]))
            self.at.setValue(existing.get("at", 0)); self.start.setValue(existing.get("start", 0))
            self.end.setValue(existing.get("end", 1)); self.within.setValue(existing.get("within", 1))
            if "event_signal" in existing: self.event.setCurrentIndex(self.event.findData(existing["event_signal"]))
            self.event_from.setCurrentText(display_value(existing.get("from", 0)))
            self.event_to.setCurrentText(display_value(existing.get("to", 1)))
            for row in range(self.multi.rowCount()):
                signal_id = self.target.itemData(row)
                if signal_id in existing.get("values", {}):
                    self.multi.cellWidget(row, 1).setCurrentText(display_value(existing["values"][signal_id]))

    @staticmethod
    def _value(combo, width=1):
        present, value = parse_cell(combo.currentText(), width)
        if not present: raise ValueError("Enter an assertion value")
        return value

    def definition(self):
        kind = self.kind.currentData()
        data = {"id": self.existing["id"] if self.existing else new_id(), "kind": kind}
        if kind == "all_equal":
            data["at"] = self.at.value()
            data["values"] = {}
            for row in range(self.multi.rowCount()):
                selection = self.multi.cellWidget(row, 1).currentText()
                if selection != "—":
                    sid = self.target.itemData(row)
                    ref = signal_ref_from_dict(next(entry["ref"] for entry in self.bench["signals"] if entry["id"] == sid))
                    data["values"][sid] = self._value(self.multi.cellWidget(row, 1), signal_width(self.circuit, ref))
            if len(data["values"]) < 2:
                raise ValueError("Select expected values for at least two outputs")
            return data
        if self.target.currentIndex() < 0:
            raise ValueError("Add an observed signal first")
        data["signal"] = self.target.currentData()
        if kind in ("equals", "not_equals", "equals_at"):
            ref = signal_ref_from_dict(next(entry["ref"] for entry in self.bench["signals"] if entry["id"] == data["signal"]))
            data["value"] = self._value(self.value, signal_width(self.circuit, ref))
            data["at"] = self.at.value()
        elif kind == "stable":
            data.update(start=self.start.value(), end=self.end.value())
        else:
            if self.event.currentIndex() < 0:
                raise ValueError("Choose an event signal")
            event_ref = signal_ref_from_dict(next(entry["ref"] for entry in self.bench["signals"] if entry["id"] == self.event.currentData()))
            event_width = signal_width(self.circuit, event_ref)
            data.update(event_signal=self.event.currentData(), **{"from": self._value(self.event_from, event_width),
                                                                     "to": self._value(self.event_to, event_width)},
                        within=self.within.value())
        return data

    def accept(self):
        try: self.definition()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid assertion", str(error)); return
        super().accept()


class TestbenchWaveformView(WaveformView):
    def __init__(self, result, parent=None):
        super().__init__(result.timing, parent)
        self.result = result
        self.fit_all()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.viewport().rect()
        painter.setClipRect(self.LEFT, self.AXIS, rect.width() - self.LEFT, rect.height() - self.AXIS)
        ref_rows = {ref: index for index, ref in enumerate(self.model.tracks)}
        for step, expected in self.result.expected_by_step.items():
            x1, x2 = self._step_x(step), self._step_x(step + 1)
            if x2 < self.LEFT or x1 > rect.width(): continue
            for signal_id, value in expected.items():
                ref = self.result.signal_refs.get(signal_id)
                if ref not in ref_rows: continue
                row = ref_rows[ref]
                y = self.AXIS + row * self.ROW - self.verticalScrollBar().value()
                if isinstance(value, (tuple, list)):
                    painter.setPen(QPen(QColor("#f6c779"), 1.8, Qt.DashLine))
                    upper, lower = y + 7, y + self.ROW - 7
                    painter.drawLine(max(self.LEFT, int(x1)), upper, min(rect.width(), int(x2)), upper)
                    painter.drawLine(max(self.LEFT, int(x1)), lower, min(rect.width(), int(x2)), lower)
                    if x2 - x1 > 42:
                        painter.drawText(max(self.LEFT, int(x1)) + 4, int(y + self.ROW / 2) + 3,
                                         display_value(value))
                    continue
                level = y + (13 if value == 1 else (self.ROW - 13 if value == 0 else self.ROW / 2))
                painter.setPen(QPen(QColor("#f6c779"), 2.2, Qt.DashLine))
                painter.drawLine(max(self.LEFT, int(x1)), int(level), min(rect.width(), int(x2)), int(level))
        for step in {item.step for item in self.result.outcomes if item.status == "failed" and item.step is not None}:
            x = self._step_x(step)
            painter.setPen(QPen(QColor("#f17f80"), 1.8, Qt.DashLine))
            painter.drawLine(int(x), self.AXIS, int(x), rect.height())
        painter.end()


class TestbenchResultDialog(QDialog):
    def __init__(self, editor, result, parent=None):
        super().__init__(parent)
        self.editor, self.result = editor, result
        self.setWindowTitle("Testbench Result — " + result.name)
        self.resize(1050, 660)
        layout = QVBoxLayout(self)
        first = result.first_failure
        header = QLabel(f"{result.name}  ·  {len(result.outcomes)} checks  ·  "
                        f"{result.passed} passed  ·  {result.failed} failed  ·  {result.inconclusive} inconclusive  ·  "
                        f"{result.duration_seconds:.3f} s" +
                        ("  ·  cancelled" if result.cancelled else "  ·  stopped early" if result.stopped_early else ""))
        header.setObjectName("inspectName")
        header.setWordWrap(True)
        layout.addWidget(header)
        if first:
            failure = QLabel(f"First failure: step {first.step} · expected {named_result_value(result, first.expected)} "
                             f"· actual {named_result_value(result, first.actual)}")
            failure.setObjectName("error"); layout.addWidget(failure)
        tabs = QTabWidget()
        self.tabs = tabs
        self.items = QTableWidget(len(result.outcomes), 6)
        self.items.setHorizontalHeaderLabels(("Status", "Step", "Signal", "Expected", "Actual", "Details"))
        self.items.horizontalHeader().setStretchLastSection(True)
        self.items.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.items.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.items.itemDoubleClicked.connect(lambda *_: self.explain_selected())
        for row, outcome in enumerate(result.outcomes):
            label = result.signal_labels.get(outcome.signal_id, "—")
            for col, text in enumerate((outcome.status.upper(), "—" if outcome.step is None else str(outcome.step),
                                         label, named_result_value(result, outcome.expected),
                                         named_result_value(result, outcome.actual), outcome.message)):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setForeground(QColor("#63d39b" if outcome.status == "passed" else
                                              "#f17f80" if outcome.status == "failed" else "#e7aa60"))
                self.items.setItem(row, col, item)
        self.items.selectRow(next((i for i, outcome in enumerate(result.outcomes) if outcome.status == "failed"), 0))
        tabs.addTab(self.items, "Checks")
        timing_page = QWidget(); timing_layout = QVBoxLayout(timing_page)
        timing_layout.addWidget(QLabel("Actual: solid waveform    Expected: amber dashed    Failure: red marker"))
        self.waveform = TestbenchWaveformView(result)
        timing_layout.addWidget(self.waveform)
        self.cursor_label = QLabel("Select a simulation step to inspect values")
        self.cursor_label.setObjectName("hint")
        timing_layout.addWidget(self.cursor_label)
        self.waveform.cursorChanged.connect(self.update_cursor)
        tabs.addTab(timing_page, "Timing Diagram")
        layout.addWidget(tabs)
        bar = QHBoxLayout()
        explain = QPushButton("Explain Failure")
        explain.setObjectName("primary")
        explain.clicked.connect(self.explain_selected)
        failed_step = QPushButton("Open Failed Step")
        failed_step.clicked.connect(lambda: self.open_debugger("open"))
        previous = QPushButton("Compare Previous")
        previous.clicked.connect(lambda: self.open_debugger("previous"))
        expected = QPushButton("Expected vs Actual")
        expected.clicked.connect(lambda: self.open_debugger("expected"))
        timing = QPushButton("Open in Timing Diagram")
        timing.clicked.connect(self.show_timing)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        for button in (explain, failed_step, previous, expected, timing):
            bar.addWidget(button)
        bar.addStretch(); bar.addWidget(close)
        layout.addLayout(bar)
        self.update_cursor()

    def selected_outcome(self):
        row = self.items.currentRow()
        return self.result.outcomes[row] if 0 <= row < len(self.result.outcomes) else None

    def show_timing(self):
        self.tabs.setCurrentIndex(1)
        outcome = self.selected_outcome() or self.result.first_failure
        if outcome and outcome.step is not None:
            self.waveform.cursor_step = outcome.step
            self.waveform.update_ranges()
            self.update_cursor()

    def update_cursor(self):
        step = self.waveform.cursor_step
        if step is None or step >= len(self.result.observations):
            self.cursor_label.setText("Select a simulation step to inspect values")
            return
        actual = self.result.observations[step]
        expected = self.result.expected_by_step.get(step, {})
        names = [f"{self.result.signal_labels[sid]}: "
                 f"actual {display_value(value)}" +
                 (f", expected {display_value(expected[sid])}" if sid in expected else "")
                 for sid, value in actual.items()]
        self.cursor_label.setText(f"Step {step} · " + "   |   ".join(names))

    def explain_selected(self):
        outcome = self.selected_outcome() or self.result.first_failure
        if not outcome or outcome.status != "failed" or outcome.signal_id is None:
            QMessageBox.information(self, "Explain Failure", "Select a failed check first.")
            return
        snapshot = self.result.snapshots.get(outcome.step)
        if snapshot is None:
            QMessageBox.information(self, "Explain Failure", "Causal snapshot for this step was not retained. The waveform shows recorded values only.")
            return
        signal = self.result.signal_refs[outcome.signal_id]
        simulator = Simulator(snapshot.circuit)
        simulator.last_transitions = deepcopy(snapshot.frame.transitions)
        simulator.last_block_events = deepcopy(snapshot.frame.block_events)
        self.editor.trace_dock.show()
        self.editor.trace_dock.raise_()
        note = (f"Failed assertion at step {outcome.step}: expected {named_result_value(self.result, outcome.expected)}, "
                f"observed {named_result_value(self.result, outcome.actual)}.")
        self.editor.trace_panel.select_snapshot(signal, snapshot.circuit, snapshot.frame,
                                                simulator, f"Testbench {self.result.name}", note)
        self.editor.focus_trace_ref(signal)
        self.accept()
        self.editor.raise_()
        self.editor.activateWindow()

    def open_debugger(self, mode="open"):
        outcome = self.selected_outcome() or self.result.first_failure
        if not outcome or outcome.status != "failed" or outcome.step is None:
            QMessageBox.information(self, "Time Travel Debugger", "Select a failed check first.")
            return
        if outcome.step not in self.result.time_snapshots:
            QMessageBox.information(self, "Time Travel Debugger", "The isolated state for this failure was not retained.")
            return
        self.editor.show_time_debugger()
        self.editor.time_panel.inspect_testbench(self.result, outcome.step, mode)
        self.accept()
        self.editor.raise_()
        self.editor.activateWindow()


class TestbenchManager(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent or editor)
        self.editor = editor
        self.source_circuit = editor.circuit
        self.package = deepcopy(editor.circuit.testbenches or empty_package())
        self.current_id = None
        self.table_signal_ids = []
        self.dirty = False
        self.results = []
        self.sessions = []
        self.active_session = None
        self.running = False
        self._loading = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.setWindowTitle("LogicSpace — Testbench Manager")
        self.resize(1230, 760)
        self._build_ui()
        self.refresh_benches()
        if editor.circuit.testbench_issues:
            self.status.setText("Testbench data needs repair: " + "; ".join(editor.circuit.testbench_issues[:2]))

    def _build_ui(self):
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel("AUTOMATED TESTBENCHES")
        title.setObjectName("overline")
        top.addWidget(title); top.addStretch()
        top.addWidget(QLabel("Max testbenches"))
        self.max_benches = QSpinBox(); self.max_benches.setRange(1, 256)
        self.max_benches.setValue(self.package["limits"]["max_testbenches"])
        self.max_benches.valueChanged.connect(self.mark_dirty)
        top.addWidget(self.max_benches)
        top.addWidget(QLabel("Max steps"))
        self.max_steps = QSpinBox(); self.max_steps.setRange(1, 10000)
        self.max_steps.setValue(self.package["limits"]["max_steps"])
        self.max_steps.valueChanged.connect(self.mark_dirty)
        top.addWidget(self.max_steps)
        root.addLayout(top)
        splitter = QSplitter(Qt.Horizontal)
        left = QWidget(); left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("TESTBENCHES"))
        self.benches = QListWidget()
        self.benches.currentItemChanged.connect(self.switch_bench)
        left_layout.addWidget(self.benches)
        for label, callback in (("+ New", self.add_bench), ("Rename", self.rename_bench),
                                ("Duplicate", self.duplicate_bench), ("Delete", self.delete_bench)):
            button = QPushButton(label); button.clicked.connect(callback); left_layout.addWidget(button)
        left_layout.addStretch()
        splitter.addWidget(left)
        right = QTabWidget(); self.tabs = right
        edit = QWidget(); edit_layout = QVBoxLayout(edit)
        note = QLabel("Each row is a simulation step. Blank cells keep the previous input or skip an expectation. "
                      "Use X for an explicit unknown. Repeat runs the same row over consecutive steps.")
        note.setWordWrap(True); note.setObjectName("hint")
        edit_layout.addWidget(note)
        signal_bar = QHBoxLayout()
        for label, callback in (("+ Circuit input", lambda: self.add_signal("drive")),
                                ("+ Observe output", lambda: self.add_signal("observe")),
                                ("Remove signal", self.remove_signal)):
            button = QPushButton(label); button.clicked.connect(callback); signal_bar.addWidget(button)
        signal_bar.addStretch(); edit_layout.addLayout(signal_bar)
        self.signals = QListWidget(); self.signals.setFixedHeight(95)
        edit_layout.addWidget(self.signals)
        self.steps = QTableWidget()
        self.steps.horizontalHeader().setStretchLastSection(True)
        self.steps.itemChanged.connect(self.mark_dirty)
        edit_layout.addWidget(self.steps, 2)
        step_bar = QHBoxLayout()
        for label, callback in (("+ Step", self.add_step), ("Duplicate step", self.duplicate_step),
                                ("Remove step", self.remove_step)):
            button = QPushButton(label); button.clicked.connect(callback); step_bar.addWidget(button)
        step_bar.addStretch(); edit_layout.addLayout(step_bar)
        edit_layout.addWidget(QLabel("ASSERTIONS"))
        self.assertions = QListWidget(); self.assertions.setFixedHeight(105)
        self.assertions.itemDoubleClicked.connect(lambda *_: self.edit_assertion())
        edit_layout.addWidget(self.assertions)
        assertion_bar = QHBoxLayout()
        for label, callback in (("+ Assertion", self.add_assertion), ("Edit", self.edit_assertion),
                                ("Remove", self.remove_assertion)):
            button = QPushButton(label); button.clicked.connect(callback); assertion_bar.addWidget(button)
        assertion_bar.addStretch(); edit_layout.addLayout(assertion_bar)
        self.stop_failure = QCheckBox("Stop on first failure")
        self.stop_failure.toggled.connect(self.mark_dirty)
        edit_layout.addWidget(self.stop_failure)
        right.addTab(edit, "Sequence & Assertions")
        results_page = QWidget(); results_layout = QVBoxLayout(results_page)
        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(lambda *_: self.view_results())
        results_layout.addWidget(self.result_list)
        right.addTab(results_page, "Results")
        splitter.addWidget(right); splitter.setSizes([235, 950]); root.addWidget(splitter, 1)
        run_bar = QHBoxLayout()
        for label, callback in (("Run selected", self.run_selected), ("Run all", self.run_all),
                                ("Stop", self.stop), ("View results", self.view_results),
                                ("Save to project", self.commit)):
            button = QPushButton(label); button.clicked.connect(callback); run_bar.addWidget(button)
            if label == "Stop": self.stop_button = button; button.setEnabled(False)
            if label == "Run selected": button.setObjectName("primary")
        run_bar.addStretch()
        close = QPushButton("Close"); close.clicked.connect(self.reject); run_bar.addWidget(close)
        root.addLayout(run_bar)
        self.status = QLabel("Ready")
        self.status.setObjectName("status")
        root.addWidget(self.status)

    def selected_bench(self):
        return next((bench for bench in self.package["items"] if bench["id"] == self.current_id), None)

    def refresh_benches(self, select=None):
        select = select or self.current_id
        self.benches.blockSignals(True)
        self.benches.clear()
        for bench in self.package["items"]:
            item = QListWidgetItem(bench["name"])
            item.setData(Qt.UserRole, bench["id"])
            self.benches.addItem(item)
            if bench["id"] == select: self.benches.setCurrentItem(item)
        if not self.benches.currentItem() and self.benches.count(): self.benches.setCurrentRow(0)
        self.benches.blockSignals(False)
        self.current_id = self.benches.currentItem().data(Qt.UserRole) if self.benches.currentItem() else None
        self.load_current()

    def switch_bench(self, current, previous):
        if self._loading: return
        old = self.current_id
        if old and not self.save_current():
            self.benches.blockSignals(True)
            for i in range(self.benches.count()):
                if self.benches.item(i).data(Qt.UserRole) == old: self.benches.setCurrentRow(i); break
            self.benches.blockSignals(False)
            return
        self.current_id = current.data(Qt.UserRole) if current else None
        self.load_current()

    def load_current(self):
        self._loading = True
        bench = self.selected_bench()
        self.signals.clear(); self.assertions.clear(); self.steps.blockSignals(True); self.steps.clear()
        if not bench:
            self.steps.setRowCount(0); self.steps.setColumnCount(0)
            self.stop_failure.setChecked(False)
            self._loading = False
            return
        for entry in bench["signals"]:
            ref = signal_ref_from_dict(entry["ref"])
            label = ref.label(self.editor.circuit) if ref.valid(self.editor.circuit) else "Missing pin"
            item = QListWidgetItem(("SET  " if entry["role"] == "drive" else "WATCH  ") + label)
            item.setData(Qt.UserRole, entry["id"])
            self.signals.addItem(item)
        self.table_signal_ids = [entry["id"] for entry in bench["signals"]]
        self.steps.setColumnCount(1 + len(self.table_signal_ids))
        labels = ["Repeat"] + [("Set " if entry["role"] == "drive" else "Expect ") +
                               (signal_ref_from_dict(entry["ref"]).label(self.editor.circuit)
                                if signal_ref_from_dict(entry["ref"]).valid(self.editor.circuit) else "Missing")
                               for entry in bench["signals"]]
        self.steps.setHorizontalHeaderLabels(labels)
        self.steps.setColumnWidth(0, 82)
        for column, label in enumerate(labels[1:], 1):
            self.steps.setColumnWidth(column, max(145, min(250, self.steps.fontMetrics().horizontalAdvance(label) + 28)))
        self.steps.setRowCount(len(bench["steps"]))
        for row_index, row in enumerate(bench["steps"]):
            self.steps.setItem(row_index, 0, QTableWidgetItem(str(row.get("repeat", 1))))
            for column, entry in enumerate(bench["signals"], 1):
                field = "drive" if entry["role"] == "drive" else "expect"
                value = row.get(field, {}).get(entry["id"], "")
                self.steps.setItem(row_index, column, QTableWidgetItem("" if value == "" else display_value(value)))
        self.steps.blockSignals(False)
        for assertion in bench.get("assertions", []):
            item = QListWidgetItem(self.assertion_label(assertion))
            item.setData(Qt.UserRole, assertion["id"])
            self.assertions.addItem(item)
        self.stop_failure.setChecked(bench.get("stop_on_failure", False))
        self._loading = False

    def assertion_label(self, assertion):
        kind = assertion["kind"].replace("_", " ").title()
        if kind == "All Equal": return f"{kind} · step {assertion.get('at', 'last')} · {len(assertion['values'])} outputs"
        signal = next((entry for entry in self.selected_bench()["signals"]
                       if entry["id"] == assertion.get("signal")), None)
        ref = signal_ref_from_dict(signal["ref"]) if signal else None
        label = ref.label(self.editor.circuit) if ref and ref.valid(self.editor.circuit) else "Missing output"
        return f"{kind} · {label} · " + str(assertion.get("value", ""))

    def mark_dirty(self, *_):
        if not self._loading: self.dirty = True

    def save_current(self):
        if self.editor.circuit is not self.source_circuit:
            self.status.setText("The project changed. Reopen Testbench Manager for the current project.")
            return False
        bench = self.selected_bench()
        if not bench: return True
        rows = []
        try:
            for row_index in range(self.steps.rowCount()):
                repeat_text = self.steps.item(row_index, 0).text() if self.steps.item(row_index, 0) else "1"
                repeat = int(repeat_text)
                row = {"repeat": repeat, "drive": {}, "expect": {}}
                for column, signal_id in enumerate(self.table_signal_ids, 1):
                    item = self.steps.item(row_index, column)
                    entry = next(signal for signal in bench["signals"] if signal["id"] == signal_id)
                    ref = signal_ref_from_dict(entry["ref"])
                    present, value = parse_cell(item.text() if item else "", signal_width(self.editor.circuit, ref))
                    if present:
                        row["drive" if entry["role"] == "drive" else "expect"][signal_id] = value
                rows.append(row)
            if not rows: raise ValueError("Add at least one simulation step")
            draft = deepcopy(self.package)
            draft_bench = next(item for item in draft["items"] if item["id"] == bench["id"])
            draft_bench["steps"] = rows
            draft_bench["stop_on_failure"] = self.stop_failure.isChecked()
            draft["limits"] = {"max_testbenches": self.max_benches.value(),
                               "max_steps": self.max_steps.value()}
            validate_package(self.editor.circuit, draft, allow_missing_refs=True)
            self.package = draft
            return True
        except (ValueError, KeyError) as error:
            QMessageBox.warning(self, "Invalid testbench", str(error))
            return False

    def add_bench(self):
        if not self.save_current(): return
        if len(self.package["items"]) >= self.max_benches.value():
            QMessageBox.warning(self, "Testbench limit", "Increase Max testbenches before adding another."); return
        name, ok = QInputDialog.getText(self, "New testbench", "Name", text="New Testbench")
        if not ok: return
        bench = new_testbench(name.strip())
        if any(item["name"].casefold() == bench["name"].casefold() for item in self.package["items"]):
            QMessageBox.warning(self, "Duplicate name", "Choose a unique testbench name."); return
        self.package["items"].append(bench); self.mark_dirty(); self.refresh_benches(bench["id"])

    def rename_bench(self):
        if not self.save_current(): return
        bench = self.selected_bench()
        if not bench: return
        name, ok = QInputDialog.getText(self, "Rename testbench", "Name", text=bench["name"])
        if not ok: return
        name = name.strip()
        if not name or any(other is not bench and other["name"].casefold() == name.casefold()
                           for other in self.package["items"]):
            QMessageBox.warning(self, "Invalid name", "Enter a unique nonempty name."); return
        bench["name"] = name; self.mark_dirty(); self.refresh_benches(bench["id"])

    def duplicate_bench(self):
        if not self.save_current(): return
        bench = self.selected_bench()
        if not bench: return
        if len(self.package["items"]) >= self.max_benches.value():
            QMessageBox.warning(self, "Testbench limit", "Increase Max testbenches before duplicating."); return
        copy = deepcopy(bench); copy["id"] = new_id()
        base = bench["name"] + " Copy"; name = base; suffix = 2
        while any(item["name"].casefold() == name.casefold() for item in self.package["items"]):
            name = f"{base} {suffix}"; suffix += 1
        copy["name"] = name
        for assertion in copy["assertions"]: assertion["id"] = new_id()
        self.package["items"].append(copy); self.mark_dirty(); self.refresh_benches(copy["id"])

    def delete_bench(self):
        bench = self.selected_bench()
        if not bench: return
        if QMessageBox.question(self, "Delete testbench", f"Delete {bench['name']}?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self.package["items"].remove(bench); self.mark_dirty(); self.refresh_benches()

    def add_signal(self, role):
        if not self.save_current(): return
        bench = self.selected_bench()
        if not bench: return
        picker = TestbenchSignalPicker(self.editor.circuit, role, self)
        if picker.exec() != QDialog.Accepted: return
        existing = {(entry["role"], signal_ref_from_dict(entry["ref"])) for entry in bench["signals"]}
        for ref in picker.selected_refs():
            if (role, ref) not in existing:
                bench["signals"].append({"id": new_id(), "role": role, "ref": signal_ref_dict(ref)})
                existing.add((role, ref))
        self.mark_dirty(); self.load_current()

    def remove_signal(self):
        if not self.save_current(): return
        bench = self.selected_bench(); item = self.signals.currentItem()
        if not bench or not item: return
        sid = item.data(Qt.UserRole)
        bench["signals"] = [entry for entry in bench["signals"] if entry["id"] != sid]
        for row in bench["steps"]:
            row.get("drive", {}).pop(sid, None); row.get("expect", {}).pop(sid, None)
        bench["assertions"] = [a for a in bench["assertions"] if a.get("signal") != sid and
                               a.get("event_signal") != sid and sid not in a.get("values", {})]
        self.mark_dirty(); self.load_current()

    def add_step(self):
        if not self.selected_bench(): return
        row = self.steps.rowCount(); self.steps.insertRow(row)
        for column in range(self.steps.columnCount()):
            self.steps.setItem(row, column, QTableWidgetItem("1" if column == 0 else ""))
        self.steps.setCurrentCell(row, 0); self.mark_dirty()

    def duplicate_step(self):
        row = self.steps.currentRow()
        if row < 0: return
        self.steps.insertRow(row + 1)
        for column in range(self.steps.columnCount()):
            item = self.steps.item(row, column)
            self.steps.setItem(row + 1, column, QTableWidgetItem(item.text() if item else ""))
        self.steps.setCurrentCell(row + 1, 0); self.mark_dirty()

    def remove_step(self):
        if self.steps.rowCount() <= 1: return
        row = self.steps.currentRow()
        if row >= 0: self.steps.removeRow(row); self.mark_dirty()

    def add_assertion(self):
        if not self.save_current(): return
        bench = self.selected_bench()
        if not bench: return
        dialog = AssertionDialog(bench, self.editor.circuit, parent=self)
        if dialog.exec() == QDialog.Accepted:
            bench["assertions"].append(dialog.definition()); self.mark_dirty(); self.load_current()

    def edit_assertion(self):
        if not self.save_current(): return
        bench = self.selected_bench(); item = self.assertions.currentItem()
        if not bench or not item: return
        old = next(a for a in bench["assertions"] if a["id"] == item.data(Qt.UserRole))
        dialog = AssertionDialog(bench, self.editor.circuit, old, self)
        if dialog.exec() == QDialog.Accepted:
            bench["assertions"][bench["assertions"].index(old)] = dialog.definition()
            self.mark_dirty(); self.load_current()

    def remove_assertion(self):
        if not self.save_current(): return
        bench = self.selected_bench(); item = self.assertions.currentItem()
        if not bench or not item: return
        bench["assertions"] = [a for a in bench["assertions"] if a["id"] != item.data(Qt.UserRole)]
        self.mark_dirty(); self.load_current()

    def commit(self):
        if not self.save_current(): return False
        try: validate_package(self.editor.circuit, self.package)
        except ValueError as error:
            QMessageBox.warning(self, "Cannot save testbenches", str(error)); return False
        if self.editor.circuit.testbenches != self.package:
            self.editor.push_history()
            self.editor.circuit.testbenches = deepcopy(self.package)
        self.editor.circuit._invalid_testbenches = None
        self.editor.circuit.testbench_issues = []
        self.dirty = False
        self.status.setText("Testbenches saved with this project. Use File → Save to write the JSON file.")
        return True

    def run_selected(self):
        bench = self.selected_bench()
        if bench: self._start([bench])

    def run_all(self):
        self._start(list(self.package["items"]))

    def _start(self, benches):
        if self.running or not benches: return
        selected_ids = {bench["id"] for bench in benches}
        if not self.save_current(): return
        benches = [bench for bench in self.package["items"] if bench["id"] in selected_ids]
        try:
            validate_package(self.editor.circuit, self.package)
            if any(not any(row.get("expect") for row in bench["steps"]) and not bench.get("assertions")
                   for bench in benches):
                raise ValueError("Every testbench needs an expected output or assertion before running")
            self.active_session = TestbenchSession(self.editor.circuit, benches[0],
                                                   max_steps=self.max_steps.value())
            self.sessions = list(benches[1:])
        except (ValueError, TypeError, KeyError) as error:
            QMessageBox.warning(self, "Cannot run testbench", str(error)); return
        self.results = []
        self.result_list.clear()
        self.running = True
        self.stop_button.setEnabled(True)
        self.status.setText("Running " + self.active_session.bench["name"])
        self.timer.start(0)

    def _advance(self):
        if not self.active_session: return
        try:
            done = self.active_session.advance(12)
        except (ValueError, TypeError, KeyError) as error:
            self.timer.stop(); self.running = False; self.stop_button.setEnabled(False)
            QMessageBox.warning(self, "Testbench execution failed", str(error)); return
        session = self.active_session
        self.status.setText(f"Running {session.bench['name']} · step {session.index}/{len(session.rows)}")
        if done:
            self._completed(session.result)
            if self.sessions:
                try:
                    self.active_session = TestbenchSession(self.editor.circuit, self.sessions.pop(0),
                                                           max_steps=self.max_steps.value())
                except (ValueError, TypeError, KeyError) as error:
                    self.active_session = None; self.sessions.clear(); self.running = False
                    self.timer.stop(); self.stop_button.setEnabled(False)
                    QMessageBox.warning(self, "Testbench execution failed", str(error))
            else:
                self.active_session = None; self.running = False
                self.timer.stop(); self.stop_button.setEnabled(False)
                self.status.setText(f"Finished {len(self.results)} testbench(es)")
                self.tabs.setCurrentIndex(1)

    def _completed(self, result):
        self.results.append(result)
        item = QListWidgetItem(f"{'CANCELLED' if result.cancelled else 'FAIL' if result.failed else 'PASS'}  "
                               f"{result.name} · {result.passed} passed, {result.failed} failed, "
                               f"{result.inconclusive} inconclusive")
        item.setData(Qt.UserRole, len(self.results) - 1)
        self.result_list.addItem(item)
        self.result_list.setCurrentItem(item)

    def stop(self):
        if not self.running: return
        self.timer.stop()
        if self.active_session:
            self.active_session.cancel()
            self._completed(self.active_session.result)
        self.sessions.clear(); self.active_session = None; self.running = False
        self.stop_button.setEnabled(False)
        self.status.setText("Execution stopped")
        self.tabs.setCurrentIndex(1)

    def view_results(self):
        item = self.result_list.currentItem()
        if item:
            TestbenchResultDialog(self.editor, self.results[item.data(Qt.UserRole)], self).exec()

    def reject(self):
        if self.running: self.stop()
        if self.dirty:
            answer = QMessageBox.question(self, "Unsaved testbenches", "Save testbench changes to the project?",
                                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                          QMessageBox.Save)
            if answer == QMessageBox.Cancel or answer == QMessageBox.Save and not self.commit(): return
        if getattr(self.editor, "testbench_manager", None) is self:
            self.editor.testbench_manager = None
        super().reject()

    def accept(self):
        if self.running: self.stop()
        if self.dirty and not self.commit(): return
        if getattr(self.editor, "testbench_manager", None) is self:
            self.editor.testbench_manager = None
        super().accept()

    def closeEvent(self, event):
        if self.running: self.stop()
        if self.dirty:
            answer = QMessageBox.question(self, "Unsaved testbenches", "Save testbench changes to the project?",
                                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                          QMessageBox.Save)
            if answer == QMessageBox.Cancel or answer == QMessageBox.Save and not self.commit():
                event.ignore(); return
        event.accept()
        if getattr(self.editor, "testbench_manager", None) is self:
            self.editor.testbench_manager = None

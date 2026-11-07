"""Breakpoint controls layered over LogicSpace's existing Time Travel debugger."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QComboBox, QLineEdit, QSpinBox, QListWidget, QListWidgetItem,
                               QMessageBox, QDialog)

from timing_view import SignalPicker
from tracing_model import value_text
from engine import memory_geometry


class AdvancedDebuggerPanel(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.manager = editor.breakpoints
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.addWidget(QLabel("BREAKPOINTS & WATCHPOINTS"))
        self.signal = None
        choose_row = QHBoxLayout()
        choose = QPushButton("Choose signal…"); choose.clicked.connect(self.choose_signal)
        choose_row.addWidget(choose)
        self.signal_label = QLabel("No signal selected"); self.signal_label.setWordWrap(True)
        choose_row.addWidget(self.signal_label, 1)
        root.addLayout(choose_row)
        condition = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(("change", "rising", "falling", "equals", "not_equals", "unknown", "watch"))
        condition.addWidget(self.mode)
        self.value = QLineEdit(); self.value.setPlaceholderText("0, 1, X, 0xA or 0b1010")
        condition.addWidget(self.value)
        add = QPushButton("+ Add"); add.clicked.connect(self.add_breakpoint)
        condition.addWidget(add)
        root.addLayout(condition)
        self.list = QListWidget()
        self.list.itemChanged.connect(self.toggle_item)
        root.addWidget(self.list, 1)
        row = QHBoxLayout()
        remove = QPushButton("Remove selected"); remove.clicked.connect(self.remove_selected)
        row.addWidget(remove)
        conflict = QPushButton("Break on conflict"); conflict.clicked.connect(self.add_conflict)
        row.addWidget(conflict)
        root.addLayout(row)
        memory_row = QHBoxLayout()
        self.memory = QComboBox()
        self.memory.currentIndexChanged.connect(self.update_memory_range)
        memory_row.addWidget(self.memory, 1)
        self.memory_address = QSpinBox()
        self.memory_address.setPrefix("Address ")
        memory_row.addWidget(self.memory_address)
        memory_button = QPushButton("Watch memory")
        memory_button.clicked.connect(self.add_memory_watch)
        memory_row.addWidget(memory_button)
        root.addLayout(memory_row)
        cycle = QHBoxLayout()
        clock = QPushButton("Choose clock…"); clock.clicked.connect(self.choose_clock)
        cycle.addWidget(clock)
        self.clock_label = QLabel("No clock selected"); self.clock_label.setWordWrap(True)
        cycle.addWidget(self.clock_label, 1)
        self.cycle_button = QPushButton("Step clock cycle")
        self.cycle_button.clicked.connect(self.step_cycle)
        cycle.addWidget(self.cycle_button)
        root.addLayout(cycle)
        self.clock_ref = None
        self._cycle_running = False
        root.addWidget(QLabel("RECENT SIGNAL HISTORY"))
        self.events = QListWidget(); self.events.setMaximumHeight(170)
        self.events.itemDoubleClicked.connect(self.open_event)
        root.addWidget(self.events)
        self.sequential = QLabel("Sequential events: step the simulator to inspect clock edges and changed state.")
        self.sequential.setWordWrap(True)
        root.addWidget(self.sequential)
        self.status = QLabel("Breakpoints pause Run after the recorded simulation step.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def choose_signal(self):
        dialog = SignalPicker(self.editor.circuit, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_refs():
            self.signal = dialog.selected_refs()[0]
            self.signal_label.setText(self.signal.label(self.editor.circuit))

    def choose_clock(self):
        dialog = SignalPicker(self.editor.circuit, self)
        dialog.setWindowTitle("Choose one-bit clock signal")
        if dialog.exec() == QDialog.Accepted and dialog.selected_refs():
            ref = dialog.selected_refs()[0]
            if isinstance(ref.value(self.editor.sim), tuple):
                QMessageBox.warning(self, "Clock cycle", "Choose an individual one-bit signal")
                return
            self.clock_ref = ref
            self.clock_label.setText(ref.label(self.editor.circuit))

    def _parse_expected(self):
        text = self.value.text().strip().upper()
        if text == "X": return None
        if text.startswith("0B") and "X" in text:
            return tuple(None if char == "X" else int(char) for char in reversed(text[2:]))
        try: return int(text, 16 if text.startswith("0X") else 2 if text.startswith("0B") else 10)
        except ValueError: raise ValueError("Enter 0, 1, X, binary, decimal or hexadecimal") from None

    def add_breakpoint(self):
        try:
            if self.signal is None: raise ValueError("Choose a signal first")
            mode = self.mode.currentText()
            expected = self._parse_expected() if mode in ("equals", "not_equals") else None
            item = self.manager.add(self.signal, mode, self.editor.sim, expected)
        except ValueError as error:
            QMessageBox.warning(self, "Breakpoint", str(error)); return
        self._append(item)

    def add_conflict(self):
        if any(item.mode == "conflict" for item in self.manager.items.values()): return
        self._append(self.manager.add_conflict(self.editor.sim))

    def update_memory_range(self):
        component = self.editor.circuit.components.get(self.memory.currentData())
        self.memory_address.setMaximum(memory_geometry(component)[2] - 1 if component else 0)

    def add_memory_watch(self):
        try:
            item = self.manager.add_memory_watch(self.memory.currentData(),
                                                 self.memory_address.value(), self.editor.sim)
        except ValueError as error:
            QMessageBox.warning(self, "Memory watchpoint", str(error)); return
        self._append(item)

    def _append(self, breakpoint):
        label = (f"{breakpoint.component_id[:8]}[{breakpoint.address:#x}]"
                 if breakpoint.mode == "memory_change" else
                 "Circuit conflict" if breakpoint.ref is None else
                 breakpoint.ref.label(self.editor.circuit))
        expected = f" {value_text(breakpoint.expected)}" if breakpoint.mode in ("equals", "not_equals") else ""
        item = QListWidgetItem(f"{breakpoint.mode}: {label}{expected}")
        item.setData(Qt.UserRole, breakpoint.id)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if breakpoint.enabled else Qt.Unchecked)
        self.list.addItem(item)

    def toggle_item(self, row):
        item = self.manager.items.get(row.data(Qt.UserRole))
        if item: item.enabled = row.checkState() == Qt.Checked

    def remove_selected(self):
        row = self.list.currentItem()
        if row is None: return
        self.manager.remove(row.data(Qt.UserRole))
        self.list.takeItem(self.list.row(row))

    def reset_for_circuit(self):
        self.manager.remove_invalid(self.editor.circuit)
        selected_memory = self.memory.currentData()
        self.memory.blockSignals(True)
        self.memory.clear()
        for component in self.editor.circuit.components.values():
            if component.kind in ("RAM", "ROM"):
                self.memory.addItem(f"{component.kind} · {component.params.get('label') or component.id[:8]}", component.id)
        index = self.memory.findData(selected_memory)
        self.memory.setCurrentIndex(index if index >= 0 else 0)
        self.memory.blockSignals(False)
        self.update_memory_range()
        self.list.clear()
        for item in self.manager.items.values(): self._append(item)
        if self.signal is not None and not self.signal.valid(self.editor.circuit):
            self.signal = None; self.signal_label.setText("No signal selected")
        if self.clock_ref is not None and not self.clock_ref.valid(self.editor.circuit):
            self.clock_ref = None; self.clock_label.setText("No clock selected")
        self.events.clear()
        self.manager.arm(self.editor.sim, clear_events=True)

    def on_events(self, events):
        for event in events:
            item = QListWidgetItem(f"Step {event.step} · {event.reason}: {event.label} "
                                   f"{value_text(event.before)} → {value_text(event.after)}")
            item.setData(Qt.UserRole, event.step)
            self.events.addItem(item)
        while self.events.count() > 200:
            self.events.takeItem(0)
        if events:
            self.status.setText(f"Paused at step {events[0].step}: {events[0].reason} · {events[0].label}")

    def update_sequential(self):
        sim = self.editor.sim
        lines = [f"Simulation step {sim.circuit.tick} · logical steps (no physical time model)"]
        clocks = [(c.id[:8], sim.outputs.get((c.id, "Q"))) for c in sim.circuit.components.values()
                  if c.kind in ("Clock Generator", "Oscillator")]
        if clocks: lines.append("Clock outputs: " + ", ".join(f"{name}={value_text(value)}" for name, value in clocks))
        events = []
        for cid, fact in sim.last_transitions.items():
            if fact.get("step") != sim.circuit.tick: continue
            if not fact.get("clock_edge") and fact.get("previous") == fact.get("current"): continue
            kind = sim.circuit.components[cid].kind if cid in sim.circuit.components else "Deleted component"
            edge = "clock edge" if fact.get("clock_edge") else "state update"
            changes = [f"{key}: {value_text(before)} → {value_text(fact['current'].get(key))}"
                       for key, before in fact["previous"].items()
                       if before != fact["current"].get(key) and key != "last_clk"]
            events.append(f"{kind} {cid[:8]} · {edge}" + (" · " + ", ".join(changes) if changes else ""))
        lines.extend(events[:8])
        if len(events) > 8: lines.append(f"…and {len(events) - 8} more state events")
        if not events: lines.append("No sequential state change in this step")
        self.sequential.setText("\n".join(lines))

    def open_event(self, item):
        step = item.data(Qt.UserRole)
        if step is None: return
        try: self.editor.navigate_time(step)
        except ValueError as error: QMessageBox.information(self, "Expired history", str(error))

    def step_cycle(self):
        if self._cycle_running:
            self.editor._clock_cycle_cancelled = True
            return
        self._cycle_running = True
        self.cycle_button.setText("Cancel cycle")
        try:
            if self.clock_ref is None: raise ValueError("Choose a one-bit clock signal first")
            reached = self.editor.step_clock_cycle(self.clock_ref)
            self.status.setText(f"Clock cycle ended at step {reached}")
        except ValueError as error: QMessageBox.warning(self, "Clock cycle", str(error))
        finally:
            self._cycle_running = False
            self.cycle_button.setText("Step clock cycle")

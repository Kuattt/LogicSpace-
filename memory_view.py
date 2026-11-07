"""RAM/ROM Inspector backed by Circuit state and the existing Time Travel history."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QTextEdit, QVBoxLayout, QWidget)

from engine import memory_geometry
from memory_model import (export_memory_image, load_memory_image, memory_changes,
                          memory_word, set_memory_word)


class MemoryInspector(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        box = QVBoxLayout(self); box.setContentsMargins(8, 8, 8, 8)
        row = QHBoxLayout(); row.addWidget(QLabel("Memory"))
        self.components = QComboBox(); self.components.currentIndexChanged.connect(self.refresh_values)
        row.addWidget(self.components, 1)
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh)
        row.addWidget(refresh); box.addLayout(row)
        row = QHBoxLayout(); row.addWidget(QLabel("Address"))
        self.address = QSpinBox(); self.address.setRange(0, 255); row.addWidget(self.address)
        row.addWidget(QLabel("Value"))
        self.value = QSpinBox(); self.value.setRange(0, 255); row.addWidget(self.value)
        self.format = QComboBox(); self.format.addItems(("Hex", "Binary", "Decimal"))
        self.format.currentIndexChanged.connect(self.refresh_values); row.addWidget(self.format)
        box.addLayout(row)
        row = QHBoxLayout()
        for label, callback in (("Go to", self.go_to), ("Write value…", self.write_value),
                                ("Load BIN/HEX…", self.load_image), ("Export…", self.export_image)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        box.addLayout(row)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(("Address", "Value"))
        self.table.cellClicked.connect(self._selected_row)
        box.addWidget(self.table, 1)
        self.history = QTextEdit(); self.history.setReadOnly(True)
        self.history.setMaximumHeight(110); box.addWidget(self.history)
        self.note = QLabel("Edits are confirmed and recorded as Time Travel mutations.")
        self.note.setWordWrap(True); box.addWidget(self.note)
        self.refresh()

    def component(self):
        return self.editor.circuit.components.get(self.components.currentData())

    def refresh(self):
        current = self.components.currentData()
        self.components.blockSignals(True)
        self.components.clear()
        for component in self.editor.circuit.components.values():
            if component.kind in ("RAM", "ROM"):
                label = component.params.get("label") or component.id[:6]
                self.components.addItem(f"{component.kind} · {label}", component.id)
        index = self.components.findData(current)
        self.components.setCurrentIndex(index if index >= 0 else 0)
        self.components.blockSignals(False)
        self.refresh_values()

    def _display(self, value, width):
        if value is None: return "X"
        if self.format.currentText() == "Binary": return f"0b{value:0{width}b}"
        if self.format.currentText() == "Decimal": return str(value)
        return f"0x{value:0{(width + 3) // 4}X}"

    def refresh_values(self):
        component = self.component()
        if component is None:
            self.table.setRowCount(0); self.history.setPlainText("No RAM or ROM in this project")
            return
        _, width, depth = memory_geometry(component)
        self.address.setMaximum(depth - 1)
        self.value.setMaximum((1 << width) - 1)
        self.table.setRowCount(depth)
        for address in range(depth):
            self.table.setItem(address, 0, QTableWidgetItem(f"0x{address:02X}"))
            self.table.setItem(address, 1, QTableWidgetItem(self._display(memory_word(component, address), width)))
        changes = memory_changes(self.editor.time_history, component.id)
        self.history.setPlainText("Retained memory changes (Time Travel):\n" +
                                  ("\n".join(f"step {item['step']} · [{item['address']:#04x}] "
                                             f"{item['before']} → {item['after']}" for item in changes[-25:])
                                   or "No changes in retained history"))
        self.note.setText(f"{component.kind}: {depth} addresses × {width} bits · "
                          f"read {component.params.get('read_mode', 'async' if component.kind == 'ROM' else 'legacy')}")

    def _selected_row(self, row, column):
        self.address.setValue(row)
        component = self.component()
        if component:
            value = memory_word(component, row)
            if value is not None: self.value.setValue(value)

    def go_to(self):
        row = self.address.value()
        if row < self.table.rowCount():
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, 0))

    def _commit(self, operation):
        component = self.component()
        if component is None: return
        self.editor.time_panel.external = None
        self.editor.push_history()
        operation(component)
        self.editor.sim.evaluate()
        self.editor.time_history.record_mutation(self.editor.sim)
        self.editor._sync_time_branch()
        events = self.editor.breakpoints.check(self.editor.sim)
        if events:
            self.editor.last_break_events = events
            self.editor.debug_panel.on_events(events)
            self.editor.timer.stop()
            self.editor.run_button.setText("▶ Run")
            self.editor.set_status(f"Memory watchpoint: {events[0].label}")
        self.editor.time_panel.refresh_panel()
        self.editor.refresh()
        self.refresh_values()

    def write_value(self):
        component = self.component()
        if component is None: return
        address, value = self.address.value(), self.value.value()
        if QMessageBox.question(self, "Edit memory", f"Write {value} to address {address} in {component.kind}?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        try: self._commit(lambda item: set_memory_word(item, address, value))
        except (ValueError, KeyError) as error: QMessageBox.warning(self, "Memory", str(error))

    def load_image(self):
        component = self.component()
        if component is None: return
        path, _ = QFileDialog.getOpenFileName(self, "Load memory image", "", "Memory images (*.bin *.hex)")
        if not path: return
        kind = "hex" if Path(path).suffix.lower() == ".hex" else "bin"
        try:
            data = Path(path).read_text(encoding="utf-8") if kind == "hex" else Path(path).read_bytes()
            count = load_memory_image(deepcopy(component), data, kind)
            if QMessageBox.question(self, "Load memory", f"Write {count} words into {component.kind}?",
                                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
            self._commit(lambda item: load_memory_image(item, data, kind))
        except (OSError, ValueError) as error: QMessageBox.warning(self, "Memory", str(error))

    def export_image(self):
        component = self.component()
        if component is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Export memory image", "memory.hex",
                                              "Intel HEX (*.hex);;Binary (*.bin)")
        if not path: return
        kind = "bin" if Path(path).suffix.lower() == ".bin" else "hex"
        try:
            data = export_memory_image(component, kind)
            if kind == "bin": Path(path).write_bytes(data)
            else: Path(path).write_text(data, encoding="utf-8")
        except (OSError, ValueError) as error: QMessageBox.warning(self, "Memory", str(error))

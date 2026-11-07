"""PySide6 timing diagram: signal picker, timeline controls and waveform view."""
from __future__ import annotations

import math
import re

from PySide6.QtCore import Qt, QRectF, QPoint, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QAbstractScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QCheckBox, QSpinBox, QDialog, QLineEdit, QListWidget, QListWidgetItem,
    QDialogButtonBox, QInputDialog,
)

from engine import ANALOG, BusWire, bus_ports, pins
from logic_analyzer_model import format_value
from timing_model import SignalRef, MISSING
from tracing_model import value_text

BG = QColor("#11151c")
PANEL = QColor("#171d26")
MUTED = QColor("#94a3b8")
HIGH = QColor("#63d39b")
LOW = QColor("#7891ae")
UNKNOWN = QColor("#e7aa60")
PALETTE = ("#6ea8fe", "#dd9af9", "#65d7bd", "#f6c779", "#ed94ac", "#9dbbfb")


class SignalPicker(QDialog):
    def __init__(self, circuit, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add signals")
        self.resize(540, 470)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search components, pins or wires…")
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.list)
        self.search.textChanged.connect(self.filter_items)
        for component in circuit.components.values():
            if component.kind in ANALOG:
                continue
            inputs, outputs = pins(component, circuit.blocks)
            for direction, ports in bus_ports(component, circuit.blocks).items():
                for port in ports:
                    ref = SignalRef.bus_port(component.id, port, direction)
                    item = QListWidgetItem(f"Bus   {ref.label(circuit)}   ·   {direction}")
                    item.setData(Qt.UserRole, ref)
                    self.list.addItem(item)
            for direction, names in (("output", outputs), ("input", inputs)):
                for pin in names:
                    ref = SignalRef.component_pin(component.id, pin, direction)
                    item = QListWidgetItem(f"{ref.label(circuit)}   ·   {direction}")
                    item.setData(Qt.UserRole, ref)
                    self.list.addItem(item)
        for wire in circuit.wires.values():
            ref = SignalRef.wire(wire.id)
            item = QListWidgetItem(f"Wire   {ref.label(circuit)}")
            item.setData(Qt.UserRole, ref)
            self.list.addItem(item)
            if isinstance(wire, BusWire):
                for index in range(wire.width):
                    bit_ref = SignalRef.wire_bit(wire.id, index)
                    bit_item = QListWidgetItem(f"Bus bit   {bit_ref.label(circuit)}")
                    bit_item.setData(Qt.UserRole, bit_ref)
                    self.list.addItem(bit_item)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Add selected")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def filter_items(self, text):
        query = text.casefold()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(query not in item.text().casefold())

    def selected_refs(self):
        return [item.data(Qt.UserRole) for item in self.list.selectedItems()]


class WaveformView(QAbstractScrollArea):
    selectedChanged = Signal()
    cursorChanged = Signal()
    renameRequested = Signal()
    followChanged = Signal(bool)
    LEFT = 250
    AXIS = 38
    ROW = 42

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.pixels_per_step = 30.0
        self.cursor_step = None
        self.cursor_b = None
        self.selected_ref = None
        self.follow_latest = True
        self.analysis_markers = []  # Optional (step, color) markers for Logic Analyzer only.
        self._program_scroll = False
        self.setMinimumHeight(130)
        self.setMouseTracking(True)
        self.horizontalScrollBar().valueChanged.connect(self._scroll_changed)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)
        self.update_ranges()

    def _scroll_changed(self):
        if not self._program_scroll:
            self.follow_latest = False
            self.followChanged.emit(False)
        self.viewport().update()

    def update_ranges(self, follow=False):
        self._program_scroll = True
        steps = max(1, self.model.last_step - self.model.first_step + 2)
        timeline_width = max(0, self.viewport().width() - self.LEFT)
        full_width = int(steps * self.pixels_per_step)
        self.horizontalScrollBar().setPageStep(timeline_width)
        self.horizontalScrollBar().setRange(0, max(0, full_width - timeline_width))
        rows_height = max(0, self.viewport().height() - self.AXIS)
        self.verticalScrollBar().setPageStep(rows_height)
        self.verticalScrollBar().setRange(0, max(0, len(self.model.tracks) * self.ROW - rows_height))
        self._program_scroll = False
        if follow and self.follow_latest:
            self.scroll_latest()
        self.viewport().update()

    def scroll_latest(self):
        self._program_scroll = True
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().maximum())
        self._program_scroll = False
        self.cursor_step = self.model.last_step
        self.cursorChanged.emit()

    def zoom(self, factor):
        center = self.cursor_step if self.cursor_step is not None else self.model.last_step
        old_x = self._step_x(center)
        self.pixels_per_step = max(0.01, min(160.0, self.pixels_per_step * factor))
        self.update_ranges()
        self._program_scroll = True
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + int(self._step_x(center) - old_x))
        self._program_scroll = False
        self.viewport().update()

    def fit_all(self):
        count = max(1, self.model.last_step - self.model.first_step + 2)
        width = max(40, self.viewport().width() - self.LEFT - 12)
        self.pixels_per_step = max(0.01, min(160.0, width / count))
        self.follow_latest = False
        self.followChanged.emit(False)
        self.update_ranges()
        self._program_scroll = True
        self.horizontalScrollBar().setValue(0)
        self._program_scroll = False

    def _step_x(self, step):
        return self.LEFT + (step - self.model.first_step) * self.pixels_per_step - self.horizontalScrollBar().value()

    def _x_step(self, x):
        raw = self.model.first_step + (x - self.LEFT + self.horizontalScrollBar().value()) / self.pixels_per_step
        return max(self.model.first_step, min(self.model.last_step, round(raw)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_ranges(follow=True)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.zoom(1.25 if event.angleDelta().y() > 0 else 0.8)
        else:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(event.angleDelta().y() / 2))
        event.accept()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        y = event.position().y()
        x = event.position().x()
        if x < self.LEFT and y >= self.AXIS:
            index = int((y - self.AXIS + self.verticalScrollBar().value()) // self.ROW)
            refs = list(self.model.tracks)
            self.selected_ref = refs[index] if 0 <= index < len(refs) else None
            self.selectedChanged.emit()
            self.viewport().update()
        elif x >= self.LEFT:
            step = self._x_step(x)
            if event.modifiers() & Qt.ShiftModifier:
                self.cursor_b = step
            else:
                self.cursor_step = step
            self.follow_latest = False
            self.followChanged.emit(False)
            self.cursorChanged.emit()
            self.viewport().update()
        event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and event.position().x() >= self.LEFT:
            self.cursor_step = self._x_step(event.position().x())
            self.follow_latest = False
            self.followChanged.emit(False)
            self.cursorChanged.emit()
            self.viewport().update()
        else:
            super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.position().x() < self.LEFT:
            self.mousePressEvent(event)
            self.renameRequested.emit()
        else:
            super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.viewport().rect()
        painter.fillRect(rect, BG)
        painter.fillRect(QRectF(0, 0, self.LEFT, rect.height()), PANEL)
        painter.fillRect(QRectF(0, 0, rect.width(), self.AXIS), QColor("#1c2530"))
        painter.setPen(QColor("#314052"))
        painter.drawLine(self.LEFT, 0, self.LEFT, rect.height())
        painter.drawLine(0, self.AXIS, rect.width(), self.AXIS)
        painter.setFont(QFont("Sans Serif", 8, QFont.DemiBold))
        painter.setPen(MUTED)
        painter.drawText(QRectF(14, 0, self.LEFT - 20, self.AXIS), Qt.AlignVCenter, "SIGNAL")
        painter.drawText(QRectF(self.LEFT + 9, 0, 110, 16), Qt.AlignVCenter, "SIMULATION STEP")
        first, last = self.model.first_step, self.model.last_step
        stride = max(1, math.ceil(58 / self.pixels_per_step))
        visible_start = max(first, int(first + (self.horizontalScrollBar().value() / self.pixels_per_step)) - 1)
        visible_end = min(last + 1, int(first + (self.horizontalScrollBar().value() + rect.width()) / self.pixels_per_step) + 2)
        painter.save()
        painter.setClipRect(QRectF(self.LEFT, 0, rect.width() - self.LEFT, rect.height()))
        for step in range(visible_start, visible_end + 1):
            if (step - first) % stride:
                continue
            x = self._step_x(step)
            painter.setPen(QPen(QColor("#283545"), 1))
            painter.drawLine(QPoint(round(x), self.AXIS), QPoint(round(x), rect.height()))
            painter.setPen(MUTED)
            painter.drawText(QRectF(x + 3, 18, 55, 17), str(step))
        refs = list(self.model.tracks)
        for index, ref in enumerate(refs):
            y = self.AXIS + index * self.ROW - self.verticalScrollBar().value()
            if y > rect.height() or y + self.ROW < self.AXIS:
                continue
            if index % 2:
                painter.fillRect(QRectF(self.LEFT, y, rect.width() - self.LEFT, self.ROW), QColor("#141b24"))
            painter.setPen(QPen(QColor("#263340"), 1))
            painter.drawLine(self.LEFT, y + self.ROW, rect.width(), y + self.ROW)
            events = list(self.model.tracks[ref].events)
            for j, (step, value) in enumerate(events):
                next_step = events[j + 1][0] if j + 1 < len(events) else last + 1
                if next_step < visible_start or step > visible_end:
                    continue
                x1, x2 = self._step_x(step), self._step_x(next_step)
                if isinstance(value, (tuple, list)):
                    color = UNKNOWN if None in value else QColor(PALETTE[self.model.tracks[ref].color_index % len(PALETTE)])
                    painter.setPen(QPen(color, 1.8))
                    upper, lower = y + 10, y + self.ROW - 10
                    left, right = max(x1, self.LEFT), min(x2, rect.width())
                    painter.drawLine(QPointF(left, upper), QPointF(right, upper))
                    painter.drawLine(QPointF(left, lower), QPointF(right, lower))
                    if j:
                        painter.drawLine(QPointF(x1 - 4, upper), QPointF(x1 + 4, lower))
                        painter.drawLine(QPointF(x1 - 4, lower), QPointF(x1 + 4, upper))
                    if right - left >= 37:
                        painter.setFont(QFont("Monospace", 8, QFont.DemiBold))
                        painter.drawText(QRectF(left + 6, y + 12, max(0, right - left - 12), 18),
                                         Qt.AlignVCenter, format_value(value, "hex") if len(value) >= 16
                                         else value_text(value))
                    continue
                level = y + (10 if value == 1 else (self.ROW - 10 if value == 0 else self.ROW / 2))
                color = HIGH if value == 1 else (LOW if value == 0 else UNKNOWN)
                painter.setPen(QPen(color, 2.4, Qt.DashLine if value is None else Qt.SolidLine))
                painter.drawLine(QPointF(max(x1, self.LEFT), level), QPointF(min(x2, rect.width()), level))
                if j:
                    previous = events[j - 1][1]
                    before = y + (10 if previous == 1 else (self.ROW - 10 if previous == 0 else self.ROW / 2))
                    painter.setPen(QPen(color, 2))
                    painter.drawLine(QPointF(x1, before), QPointF(x1, level))
                if value is None and x2 - x1 > 16:
                    painter.setPen(UNKNOWN)
                    painter.drawText(QRectF(max(x1 + 4, self.LEFT), y + 2, 18, self.ROW - 4), Qt.AlignVCenter, "X")
        for step, color in self.analysis_markers:
            if visible_start <= step <= visible_end:
                x = self._step_x(step)
                marker = QColor(color)
                marker.setAlpha(155)
                painter.setPen(QPen(marker, 1.4, Qt.DotLine))
                painter.drawLine(QPointF(x, self.AXIS), QPointF(x, rect.height()))
        if self.cursor_step is not None:
            x = self._step_x(self.cursor_step)
            painter.setPen(QPen(QColor("#d5e6ff"), 1.4))
            painter.drawLine(QPointF(x, 18), QPointF(x, rect.height()))
            painter.fillRect(QRectF(x - 13, 2, 26, 15), QColor("#4d7fbd"))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(x - 13, 2, 26, 15), Qt.AlignCenter, str(self.cursor_step))
        if self.cursor_b is not None:
            x = self._step_x(self.cursor_b)
            painter.setPen(QPen(QColor("#e4b46f"), 1.4, Qt.DashLine))
            painter.drawLine(QPointF(x, 18), QPointF(x, rect.height()))
        painter.restore()
        for index, ref in enumerate(refs):
            y = self.AXIS + index * self.ROW - self.verticalScrollBar().value()
            if y > rect.height() or y + self.ROW < self.AXIS:
                continue
            track = self.model.tracks[ref]
            if ref == self.selected_ref:
                painter.fillRect(QRectF(0, y, self.LEFT, self.ROW), QColor("#2a3b50"))
            painter.setBrush(QColor(PALETTE[track.color_index % len(PALETTE)]))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(13, y + self.ROW / 2), 4, 4)
            painter.setFont(QFont("Sans Serif", 9))
            painter.setPen(QColor("#dce7f5"))
            label = painter.fontMetrics().elidedText(track.label, Qt.ElideMiddle, self.LEFT - 120)
            painter.drawText(QRectF(24, y, self.LEFT - 118, self.ROW), Qt.AlignVCenter, label)
            value = self.model.value_at(ref, self.cursor_step if self.cursor_step is not None else last)
            painter.setPen(HIGH if value == 1 else (LOW if value == 0 else UNKNOWN))
            painter.setFont(QFont("Sans Serif", 10, QFont.Bold))
            shown = "—" if value is MISSING else value_text(value)
            painter.drawText(QRectF(self.LEFT - 82, y, 74, self.ROW), Qt.AlignCenter,
                             painter.fontMetrics().elidedText(shown, Qt.ElideMiddle, 74))
        if not refs:
            painter.setPen(MUTED)
            painter.drawText(QRectF(self.LEFT, self.AXIS, rect.width() - self.LEFT, rect.height() - self.AXIS),
                             Qt.AlignCenter, "Add pins or wires to start capturing")


class TimingPanel(QWidget):
    def __init__(self, editor, model, parent=None):
        super().__init__(parent)
        self.editor, self.model = editor, model
        self.setObjectName("timingPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        bar = QHBoxLayout()
        title = QLabel("TIMING DIAGRAM")
        title.setObjectName("overline")
        bar.addWidget(title)
        for name, callback in (("+ Add", self.pick_signals), ("+ Selected", self.add_selected),
                               ("Expand bus", self.expand_selected),
                               ("Rename", self.rename_selected), ("Remove", self.remove_selected),
                               ("Clear signals", self.clear_signals), ("Clear history", self.clear_history),
                               ("−", lambda: self.view.zoom(0.8)), ("+", lambda: self.view.zoom(1.25)),
                               ("Fit", self.view_fit)):
            button = QPushButton(name)
            button.clicked.connect(callback)
            bar.addWidget(button)
        self.follow = QCheckBox("Follow")
        self.follow.setChecked(True)
        self.follow.toggled.connect(self.set_follow)
        bar.addWidget(self.follow)
        bar.addWidget(QLabel("Limit"))
        self.limit = QSpinBox()
        self.limit.setRange(10, 10000)
        self.limit.setValue(model.limit)
        self.limit.setSingleStep(100)
        self.limit.setFixedWidth(74)
        self.limit.valueChanged.connect(self.set_limit)
        bar.addWidget(self.limit)
        bar.addStretch()
        layout.addLayout(bar)
        self.view = WaveformView(model, self)
        self.view.cursorChanged.connect(self.update_cursor_label)
        self.view.renameRequested.connect(self.rename_selected)
        self.view.followChanged.connect(self.follow.setChecked)
        layout.addWidget(self.view)
        self.cursor_label = QLabel("Step —")
        self.cursor_label.setObjectName("hint")
        layout.addWidget(self.cursor_label)

    def pick_signals(self):
        dialog = SignalPicker(self.editor.circuit, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.add_refs(dialog.selected_refs())

    def add_selected(self):
        refs = [SignalRef.wire(wid) for wid in self.editor.selected_wires()]
        for cid in self.editor.selected_components():
            component = self.editor.circuit.components[cid]
            input_pins, output_pins = pins(component, self.editor.circuit.blocks)
            direction, names = ("output", output_pins) if output_pins else ("input", input_pins)
            ports = bus_ports(component, self.editor.circuit.blocks)[direction]
            grouped = {pin for bits in ports.values() for pin in bits}
            refs.extend(SignalRef.bus_port(cid, port, direction) for port in ports)
            refs.extend(SignalRef.component_pin(cid, pin, direction) for pin in names if pin not in grouped)
        self.add_refs(refs)

    def expand_selected(self):
        ref = self.view.selected_ref
        if ref is None or not ref.valid(self.editor.circuit):
            return
        if ref.kind == "bus":
            bits = bus_ports(self.editor.circuit.components[ref.component_id], self.editor.circuit.blocks)[ref.direction][ref.pin]
            self.add_refs([SignalRef.component_pin(ref.component_id, pin, ref.direction) for pin in bits])
        elif ref.kind == "wire" and isinstance(self.editor.circuit.wires.get(ref.wire_id), BusWire):
            wire = self.editor.circuit.wires[ref.wire_id]
            self.add_refs([SignalRef.wire_bit(ref.wire_id, index) for index in range(wire.width)])

    def add_refs(self, refs):
        added = 0
        for ref in refs:
            if self.model.add(ref, self.editor.sim):
                added += 1
        if added:
            self.editor.trace_history.record(self.editor.sim)
            self.view.update_ranges(follow=True)
            self.view.cursor_step = self.model.last_step
            self.update_cursor_label()
            self.editor.show_timing(True)

    def remove_selected(self):
        if self.view.selected_ref and self.model.remove(self.view.selected_ref):
            self.view.selected_ref = None
            self.view.update_ranges()
            self.update_cursor_label()

    def rename_selected(self):
        ref = self.view.selected_ref
        if ref not in self.model.tracks:
            return
        track = self.model.tracks[ref]
        label, accepted = QInputDialog.getText(self, "Rename signal", "Display label", text=track.label)
        if accepted and label.strip():
            track.label = label.strip()
            self.view.viewport().update()
            self.update_cursor_label()

    def clear_signals(self):
        self.model.clear_signals()
        if hasattr(self.editor, "trace_history") and not self.editor.trace_dock.isVisible():
            self.editor.trace_history.clear()
        if hasattr(self.editor, "trace_panel"):
            self.editor.trace_panel.cursor.setChecked(False)
        self.view.selected_ref = None
        self.view.cursor_step = None
        self.view.cursor_b = None
        self.view.update_ranges()
        self.update_cursor_label()
        if hasattr(self.editor, "trace_panel") and self.editor.trace_dock.isVisible():
            self.editor.trace_panel.refresh()

    def clear_history(self):
        self.model.clear_history(self.editor.sim)
        self.editor.trace_history.clear()
        if self.model.tracks:
            self.editor.trace_history.record(self.editor.sim)
        self.view.cursor_step = self.model.last_step
        self.view.cursor_b = None
        self.view.update_ranges(follow=True)
        self.update_cursor_label()
        if self.editor.trace_dock.isVisible() and not self.editor._trace_refresh_suppressed:
            self.editor.trace_panel.refresh()

    def reset_history(self):
        self.clear_history()

    def record_step(self):
        if self.model.record_step(self.editor.sim):
            if self.isVisible():
                self.view.update_ranges(follow=True)
                self.update_cursor_label()

    def sync_circuit(self, clear=False, reset=False):
        if clear:
            self.clear_signals()
        else:
            removed = self.model.remove_invalid(self.editor.circuit)
            if self.model.tracks and (reset or removed or
                                      (self.model.steps and self.editor.circuit.tick < self.model.last_step)):
                self.model.clear_history(self.editor.sim)
            self.view.update_ranges()
            self.update_cursor_label()

    def set_follow(self, checked):
        self.view.follow_latest = checked
        if checked:
            self.view.scroll_latest()
            self.view.viewport().update()

    def set_limit(self, limit):
        self.model.set_limit(limit)
        self.editor.trace_history.set_limit(limit)
        self.view.update_ranges(follow=True)
        if self.editor.trace_dock.isVisible():
            self.editor.trace_panel.refresh()

    def view_fit(self):
        self.view.fit_all()
        self.update_cursor_label()

    def update_cursor_label(self):
        if not self.model.tracks:
            self.cursor_label.setText("Step — · Select pins or wires to record")
            return
        step = self.view.cursor_step if self.view.cursor_step is not None else self.model.last_step
        values = []
        for track in self.model.tracks.values():
            value = self.model.value_at(track.ref, step)
            values.append(f"{track.label}: {'—' if value is MISSING else value_text(value)}")
        groups = {}
        for ref in self.model.tracks:
            if ref.kind != "pin":
                continue
            match = re.fullmatch(r"(.+?)(\d+)", ref.pin)
            if match:
                groups.setdefault((ref.component_id, ref.direction, match.group(1)), {})[int(match.group(2))] = ref
        for (cid, direction, prefix), selected in groups.items():
            component = self.editor.circuit.components.get(cid)
            if component is None:
                continue
            available = pins(component, self.editor.circuit.blocks)[0 if direction == "input" else 1]
            indices = sorted(int(pin[len(prefix):]) for pin in available
                             if re.fullmatch(re.escape(prefix) + r"\d+", pin))
            if len(indices) < 2 or set(indices) != set(selected):
                continue
            bits = []
            for index in reversed(indices):
                value = self.model.value_at(selected[index], step)
                bits.append("—" if value is MISSING else ("X" if value is None else str(value)))
            name = component.params.get("label") or component.kind
            values.append(f"{name}.{prefix}[{max(indices)}:0]: {''.join(bits)}")
        delta = f" · Δ {abs(self.view.cursor_b - step)} steps" if self.view.cursor_b is not None else ""
        summary = "   |   ".join(values)
        self.cursor_label.setText(f"Step {step}{delta}   ·   {summary}")

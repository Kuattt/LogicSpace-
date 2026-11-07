"""LogicSpace desktop interface."""
from __future__ import annotations

import json
import math
import sys
from collections import deque
from copy import deepcopy
from pathlib import Path
from version import APP_VERSION
from update_view import UpdateController

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QTimer, QMimeData
from PySide6.QtGui import (
    QAction, QColor, QBrush, QPainter, QPainterPath, QPen, QFont,
    QKeySequence, QDrag, QIcon, QPixmap, QCursor, QRadialGradient, QLinearGradient,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame,
    QPushButton, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QGraphicsView,
    QGraphicsScene, QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsEllipseItem,
    QGraphicsRectItem, QGraphicsTextItem, QFileDialog, QMessageBox, QDialog,
    QFormLayout, QDialogButtonBox, QSpinBox, QComboBox, QCheckBox, QTextEdit,
    QSlider, QSplitter, QMenu, QScrollArea, QTabWidget, QDockWidget,
)

from engine import (CATALOG, ANALOG, DISPLAYS, LOGIC_GATES, BIT_WIDTH_KINDS, bit_width,
                    Circuit, Simulator, Component, Wire, BusWire, BUS_COMPONENTS, BUS_WIDTHS, DEFAULT_MICROCODE,
                    bus_ports, wire_bit_pairs, wire_to_dict, wire_from_dict,
                    pins, copy_selection, new_id)
from visuals import paint_component_body
from timing_model import SignalRef, TimingHistory
from timing_view import TimingPanel
from tool_visuals import TOOL_COLORS, tool_pixmap
from component_library import ComponentLibrary, block_definition_from_circuit
from library_manager import LibraryManager, SaveBlockDialog
from block_visuals import block_geometry, terminal_positions, paint_designed_block
from tracing_model import TraceHistory
from tracing_view import SignalTracingPanel
from time_travel_model import SimulationHistory
from time_travel_view import TimeTravelPanel
from breakpoints import BreakpointManager
from debugger_view import AdvancedDebuggerPanel
from logic_analyzer_view import LogicAnalyzerPanel
from cpu_debugger import CpuBreakpointManager
from cpu_architecture import get_active_binding, sync_active_from_clocks
from cpu_view import CpuAssemblyPanel
from experience_view import ExperiencePanel
from hdl_view import HDLPanel
from fpga_view import FPGAWorkflowPanel
from memory_view import MemoryInspector

BG = QColor("#11151c")
GRID = QColor("#1d2530")
PANEL = "#171d26"
CARD = QColor("#222b37")
EDGE = QColor("#394657")
TEXT = QColor("#e7edf7")
MUTED = QColor("#94a3b8")
BLUE = QColor("#6ea8fe")
GREEN = QColor("#63d39b")
LOW = QColor("#7891ae")
UNKNOWN = QColor("#e7aa60")
COMPONENT_MIME = "application/x-logicspace-component"


def signal_color(value):
    return GREEN if value == 1 else (LOW if value == 0 else UNKNOWN)


def format_bus(bits, mode="binary"):
    if any(bit is None for bit in bits):
        return ("".join("X" if bit is None else str(bit) for bit in reversed(bits))
                if mode == "binary" else "X")
    number = sum(bit << index for index, bit in enumerate(bits))
    if mode == "hex": return f"0x{number:0{(len(bits) + 3) // 4}X}"
    if mode == "decimal": return str(number)
    return "".join(str(bit) for bit in reversed(bits))


def nice_name(kind):
    return kind[6:] if kind.startswith("BLOCK:") else kind


def point_tuple(p):
    return [round(p.x(), 2), round(p.y(), 2)]


def draw_symbol(painter, kind, rect):
    """Small vector symbols shared by the library and canvas components."""
    painter.save()
    painter.translate(rect.x(), rect.y())
    painter.scale(rect.width() / 24, rect.height() / 24)
    painter.setRenderHint(QPainter.Antialiasing)
    color = QColor("#8db9ff") if kind not in DISPLAYS else QColor("#ffd36c")
    painter.setPen(QPen(color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    if kind in ("Lamp", "RGB Lamp", "LED", "RGB LED", "OUTPUT"):
        painter.drawEllipse(QPointF(12, 10), 6.5, 6.5)
        painter.drawLine(9, 18, 15, 18)
        if kind in ("Lamp", "RGB Lamp"):
            for a, b, c, d in ((12, 0, 12, 2), (2, 10, 4, 10), (20, 10, 22, 10), (4, 2, 5, 3), (19, 2, 20, 3)):
                painter.drawLine(a, b, c, d)
        elif kind in ("LED", "RGB LED"):
            painter.drawLine(17, 4, 21, 0)
            painter.drawLine(18, 8, 23, 5)
    elif kind == "RGB":
        painter.setPen(Qt.NoPen)
        for color, cx, cy in (("#ff6a6a", 8, 8), ("#65dda0", 16, 8), ("#6ca7ff", 12, 16)):
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPointF(cx, cy), 4, 4)
    elif kind == "Seven-segment Display":
        painter.setFont(QFont("Sans Serif", 17, QFont.Bold))
        painter.drawText(QRectF(0, -2, 24, 26), Qt.AlignCenter, "8")
    elif kind == "INPUT":
        painter.drawLine(2, 17, 7, 17)
        painter.drawLine(7, 17, 17, 7)
        painter.drawEllipse(QPointF(18, 6), 2, 2)
        painter.drawLine(20, 6, 23, 6)
    elif kind in ("Clock Generator", "Oscillator", "Clock Divider", "Timer", "Pulse Generator", "Crystal Oscillator"):
        painter.drawEllipse(2, 2, 20, 20)
        painter.drawLine(12, 12, 12, 5)
        painter.drawLine(12, 12, 17, 15)
    elif kind in ("AND", "NAND", "OR", "NOR", "XOR", "XNOR", "NOT"):
        painter.drawLine(1, 7, 5, 7)
        painter.drawLine(1, 17, 5, 17)
        path = QPainterPath()
        if kind == "NOT":
            path.moveTo(5, 4); path.lineTo(5, 20); path.lineTo(19, 12); path.closeSubpath()
        elif kind in ("AND", "NAND"):
            path.moveTo(5, 4); path.lineTo(12, 4); path.cubicTo(24, 4, 24, 20, 12, 20); path.lineTo(5, 20); path.closeSubpath()
        else:
            path.moveTo(5, 4); path.cubicTo(12, 4, 20, 6, 21, 12)
            path.cubicTo(20, 18, 12, 20, 5, 20)
            path.cubicTo(9, 15, 9, 9, 5, 4)
            if kind in ("XOR", "XNOR"):
                painter.drawArc(QRectF(1, 4, 9, 16), -90 * 16, 180 * 16)
        painter.drawPath(path)
        if kind in ("NAND", "NOR", "XNOR", "NOT"):
            painter.drawEllipse(QPointF(22, 12), 2, 2)
        else:
            painter.drawLine(21, 12, 24, 12)
    elif kind in ANALOG:
        if kind == "Resistor":
            path = QPainterPath(QPointF(1, 12))
            for x, y in ((5, 12), (7, 6), (10, 18), (13, 6), (16, 18), (19, 12), (23, 12)):
                path.lineTo(x, y)
            painter.drawPath(path)
        elif kind == "Capacitor":
            painter.drawLine(1, 12, 9, 12); painter.drawLine(9, 5, 9, 19)
            painter.drawLine(15, 5, 15, 19); painter.drawLine(15, 12, 23, 12)
        elif kind == "Diode":
            path = QPainterPath(QPointF(5, 5)); path.lineTo(5, 19); path.lineTo(16, 12); path.closeSubpath()
            painter.drawPath(path)
            painter.drawLine(17, 5, 17, 19)
        elif kind == "Crystal Oscillator":
            painter.drawRect(QRectF(7, 7, 10, 10))
            painter.drawLine(4, 5, 4, 19); painter.drawLine(20, 5, 20, 19)
        elif kind == "MOSFET":
            painter.drawLine(7, 5, 7, 19); painter.drawLine(12, 5, 12, 19)
            painter.drawLine(12, 7, 20, 7); painter.drawLine(12, 17, 20, 17)
        elif kind in ("BJT", "Transistor"):
            painter.drawEllipse(2, 2, 20, 20)
            painter.drawLine(8, 6, 8, 18)
            painter.drawLine(8, 9, 17, 4); painter.drawLine(8, 15, 17, 20)
            if kind == "BJT": painter.drawLine(14, 16, 17, 20)
        else:
            painter.drawEllipse(3, 3, 18, 18)
            painter.drawLine(0, 12, 3, 12); painter.drawLine(21, 12, 24, 12)
    elif CATALOG.get(kind, ("",))[0] in ("Memory", "Memory Elements", "Registers and Counters") or kind.startswith("BLOCK:"):
        painter.drawRoundedRect(4, 3, 16, 18, 2, 2)
        for y in (7, 12, 17):
            painter.drawLine(1, y, 4, y); painter.drawLine(20, y, 23, y)
        mark = {"RAM": "R", "ROM": "O", "SRAM": "S", "DRAM": "D", "EEPROM": "E", "Flash Memory": "F",
                "D Flip-Flop": "D", "JK Flip-Flop": "J", "T Flip-Flop": "T", "SR Latch": "S", "D Latch": "L",
                "Register": "R", "Shift Register": "⇢", "Binary Counter": "#", "Up Counter": "↑", "Down Counter": "↓"}.get(kind, "C")
        painter.setFont(QFont("Sans Serif", 9, QFont.Bold))
        painter.drawText(QRectF(5, 5, 14, 15), Qt.AlignCenter, mark)
    elif CATALOG.get(kind, ("",))[0] == "Basic Circuits":
        painter.drawRoundedRect(2, 4, 20, 16, 3, 3)
        mark = {"Half Adder": "½+", "Full Adder": "+", "Half Subtractor": "½−",
                "Full Subtractor": "−", "Comparator": "=", "Multiplexer": "M",
                "Demultiplexer": "D", "Decoder": "2→", "Encoder": "→2"}.get(kind, "C")
        painter.setFont(QFont("Sans Serif", 7, QFont.Bold))
        painter.drawText(QRectF(3, 4, 18, 16), Qt.AlignCenter, mark)
    elif CATALOG.get(kind, ("",))[0] == "Arithmetic":
        painter.drawEllipse(2, 2, 20, 20)
        mark = {"Adder": "+", "Subtractor": "−", "Multiplier": "×", "Divider": "÷", "ALU": "A"}.get(kind, "+")
        painter.setFont(QFont("Sans Serif", 12, QFont.Bold))
        painter.drawText(QRectF(2, 2, 20, 20), Qt.AlignCenter, mark)
    else:
        painter.drawRoundedRect(3, 4, 18, 16, 3, 3)
        painter.drawLine(7, 12, 17, 12)
    painter.restore()


def component_icon(kind):
    pixmap = QPixmap(34, 34)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    draw_symbol(painter, kind, QRectF(5, 5, 24, 24))
    painter.end()
    return QIcon(pixmap)


LAMP_COLORS = {
    "Warm white": QColor("#ffd38a"),
    "White": QColor("#e9f4ff"),
    "Red": QColor("#ff5a62"),
    "Green": QColor("#65e6a0"),
    "Blue": QColor("#66aaff"),
    "Amber": QColor("#ffb74d"),
}


def draw_bulb(painter, center, radius, color, on, led=False, unknown=False):
    """A glass lens, reflected highlight, filament and optional emitted glow."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    x, y = center.x(), center.y()
    if on:
        glow = QRadialGradient(center, radius * 2.25)
        near = QColor(color); near.setAlpha(115)
        mid = QColor(color); mid.setAlpha(35)
        far = QColor(color); far.setAlpha(0)
        glow.setColorAt(0, near)
        glow.setColorAt(0.44, mid)
        glow.setColorAt(1, far)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, radius * 2.25, radius * 2.25)
    glass = QRadialGradient(QPointF(x - radius * 0.35, y - radius * 0.45), radius * 1.55)
    if on:
        glass.setColorAt(0, color.lighter(185))
        glass.setColorAt(0.42, color)
        glass.setColorAt(1, color.darker(245))
    else:
        glass.setColorAt(0, QColor("#5c6e7c") if not unknown else QColor("#796044"))
        glass.setColorAt(0.58, QColor("#344452"))
        glass.setColorAt(1, QColor("#1a2633"))
    painter.setPen(QPen(QColor("#dce7f2") if on else QColor("#708195"), 1.2))
    painter.setBrush(QBrush(glass))
    painter.drawEllipse(center, radius, radius)
    reflection = QColor("#ffffff"); reflection.setAlpha(155 if on else 65)
    painter.setPen(Qt.NoPen)
    painter.setBrush(reflection)
    painter.drawEllipse(QPointF(x - radius * 0.37, y - radius * 0.42), radius * 0.27, radius * 0.16)
    if led:
        painter.setPen(QPen(QColor("#788fa5"), 1.4))
        painter.drawLine(QPointF(x - radius * 0.4, y + radius), QPointF(x - radius * 0.4, y + radius + 10))
        painter.drawLine(QPointF(x + radius * 0.4, y + radius), QPointF(x + radius * 0.4, y + radius + 10))
    else:
        filament = QColor("#fff6d1") if on else QColor("#8e8170")
        painter.setPen(QPen(filament, 1.5))
        painter.drawLine(QPointF(x - radius * 0.42, y + radius * 0.25), QPointF(x - radius * 0.18, y - radius * 0.18))
        painter.drawLine(QPointF(x - radius * 0.18, y - radius * 0.18), QPointF(x + radius * 0.18, y - radius * 0.18))
        painter.drawLine(QPointF(x + radius * 0.18, y - radius * 0.18), QPointF(x + radius * 0.42, y + radius * 0.25))
        metal = QLinearGradient(x - radius * 0.45, y, x + radius * 0.45, y)
        metal.setColorAt(0, QColor("#667381"))
        metal.setColorAt(0.5, QColor("#c7d0d9"))
        metal.setColorAt(1, QColor("#5a6878"))
        painter.setPen(QPen(QColor("#3e4a58"), 1))
        painter.setBrush(QBrush(metal))
        base = QRectF(x - radius * 0.46, y + radius * 0.82, radius * 0.92, radius * 0.62)
        painter.drawRoundedRect(base, 2, 2)
        painter.setPen(QPen(QColor("#485566"), 1))
        for shift in (0.17, 0.36):
            yy = base.top() + base.height() * shift
            painter.drawLine(QPointF(base.left() + 2, yy), QPointF(base.right() - 2, yy))
    painter.restore()


def draw_seven_segment(painter, values):
    """Draw seven digital display bars, A through G."""
    center_x, top = 120, 72
    bars = {
        "A": QRectF(center_x - 17, top, 34, 6),
        "B": QRectF(center_x + 14, top + 6, 6, 39),
        "C": QRectF(center_x + 14, top + 51, 6, 39),
        "D": QRectF(center_x - 17, top + 90, 34, 6),
        "E": QRectF(center_x - 20, top + 51, 6, 39),
        "F": QRectF(center_x - 20, top + 6, 6, 39),
        "G": QRectF(center_x - 17, top + 45, 34, 6),
    }
    for name, rect in bars.items():
        active = values.get(name) == 1
        if active:
            glow = QColor("#ff684d"); glow.setAlpha(55)
            painter.setPen(QPen(glow, 11, Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 3, 3)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ff7257") if active else QColor("#3c3034"))
        painter.drawRoundedRect(rect, 2, 2)


class ComponentTree(QTreeWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor

    def startDrag(self, supported_actions):
        item = self.currentItem()
        kind = item.data(0, Qt.UserRole) if item else None
        if not kind:
            return
        self.editor.set_tool(None)
        drag = QDrag(self)
        data = QMimeData()
        data.setData(COMPONENT_MIME, kind.encode("utf-8"))
        drag.setMimeData(data)
        drag.setPixmap(component_preview(self.editor, kind))
        drag.setHotSpot(QPointF(16, 12).toPoint())
        self.editor.set_status(f"Dragging {item.text(0)} · release on the canvas to place")
        result = drag.exec(Qt.CopyAction)
        if result == Qt.IgnoreAction:
            self.editor.set_status("Ready · Drag a component from the library onto the canvas")


class PinItem(QGraphicsEllipseItem):
    def __init__(self, owner, name, direction, x, y, *, is_bus=False, width=1):
        radius = 8 if is_bus else 5.5
        super().__init__(-radius, -radius, radius * 2, radius * 2, owner)
        self.owner = owner
        self.name = name
        self.direction = direction
        self.is_bus = is_bus
        self.bus_width = width
        self.setPos(x, y)
        self.setZValue(5)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{direction.title()} · {name}" + (f" · {width}-bit bus" if is_bus else ""))
        self.setBrush(QBrush(BG))
        self.setPen(QPen(QColor("#65d7bd") if is_bus else BLUE, 2.5 if is_bus else 2))

    def mousePressEvent(self, event):
        self.owner.editor.pin_clicked(self)
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu()
        ref = (SignalRef.bus_port(self.owner.component.id, self.name, self.direction) if self.is_bus
               else SignalRef.component_pin(self.owner.component.id, self.name, self.direction))
        backward = menu.addAction("Trace Backward")
        forward = menu.addAction("Trace Forward")
        explain = menu.addAction("Explain Signal")
        menu.addSeparator()
        add = menu.addAction("Add bus to Timing Diagram" if self.is_bus else "Add pin to Timing Diagram")
        chosen = menu.exec(event.screenPos())
        if chosen == add:
            self.owner.editor.add_timing_signal(ref)
        elif chosen in (backward, forward, explain):
            self.owner.editor.trace_signal(ref, {backward: 0, forward: 1, explain: 2}[chosen])
        event.accept()

    def hoverEnterEvent(self, event):
        self.setScale(1.35)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setScale(1)
        super().hoverLeaveEvent(event)


class ComponentItem(QGraphicsItem):
    def __init__(self, editor, component):
        super().__init__()
        self.editor = editor
        self.component = component
        self.ins, self.outs = pins(component, editor.circuit.blocks)
        self.bus_ports = bus_ports(component, editor.circuit.blocks)
        compact_bus = component.kind in BUS_COMPONENTS
        dense_ports = component.kind == "ISA Control Unit"
        wide_data = any(len(names) >= 16 for ports in self.bus_ports.values() for names in ports.values())
        hidden_direction = ("output" if component.kind in ("Bus Input", "Bus Merger") else "input")
        hidden_scalar_connection = any(not isinstance(wire, BusWire) and
                                       (wire.source == component.id if hidden_direction == "output"
                                        else wire.target == component.id)
                                       for wire in editor.circuit.wires.values())
        self.show_bit_pins = not compact_bus or bool(component.params.get("show_bits")) or hidden_scalar_connection
        self.visible_ins = (self.ins if self.show_bit_pins or component.kind == "Bus Merger" else [])
        self.visible_outs = (self.outs if self.show_bit_pins or component.kind in ("Bus Splitter", "Bit Selector") else [])
        if (wide_data or dense_ports) and not compact_bus and not component.params.get("show_bits"):
            grouped_inputs = {pin for group in self.bus_ports["input"].values() for pin in group}
            grouped_outputs = {pin for group in self.bus_ports["output"].values() for pin in group}
            wired_inputs = {wire.target_pin for wire in editor.circuit.wires.values()
                            if not isinstance(wire, BusWire) and wire.target == component.id}
            wired_outputs = {wire.source_pin for wire in editor.circuit.wires.values()
                             if not isinstance(wire, BusWire) and wire.source == component.id}
            self.visible_ins = [pin for pin in self.ins if pin not in grouped_inputs or pin in wired_inputs]
            self.visible_outs = [pin for pin in self.outs if pin not in grouped_outputs or pin in wired_outputs]
        self.block_definition = editor.circuit.blocks.get(component.kind[6:]) if component.kind.startswith("BLOCK:") else None
        self.designed_block = bool(self.block_definition and self.block_definition.get("designer"))
        self.sliced = 1 < bit_width(component) <= 8 and component.kind in (
            *LOGIC_GATES, "Comparator", "Multiplexer", "Demultiplexer",
            "Adder", "Subtractor", "Multiplier", "Divider", "ALU")
        self.width = 218 if self.sliced else (300 if wide_data and component.kind in ("Bus Input", "Bus Output", "Bus Probe")
                                            else 240 if wide_data or dense_ports else 220 if compact_bus else 156)
        if not self.sliced and (component.kind in (
                "Register", "Shift Register", "Binary Counter", "Up Counter", "Down Counter",
                "RAM", "ROM", "SRAM", "DRAM", "EEPROM", "Flash Memory", "Register File")) and max(len(self.ins), len(self.outs)) > 5 and not wide_data:
            self.width = 190
        self.height = max(125 if component.kind == "Bus Probe" and not self.show_bit_pins else 80,
                          43 + 24 * max(len(self.visible_ins), len(self.visible_outs)))
        if self.sliced:
            n = bit_width(component)
            pitch = 34 if component.kind == "NOT" else 38
            extra = max(len([p for p in self.ins if not (p.startswith("A") and p[1:].isdigit() or p.startswith("B") and p[1:].isdigit())]),
                        len([p for p in self.outs if not ((p.startswith("Q") and p[1:].isdigit()) or p.startswith("Q0_") or p.startswith("Q1_"))]))
            self.height = 45 + n * pitch + extra * 25
        if component.kind in ("Lamp", "LED"):
            self.height = max(self.height, 102)
        elif component.kind in ("RGB", "RGB Lamp", "RGB LED"):
            self.height = max(self.height, 119)
        elif component.kind in ANALOG:
            self.height = max(self.height, 108)
        if self.designed_block:
            self.width, self.height = block_geometry(self.block_definition)
            self.block_positions = terminal_positions(self.block_definition, self.width, self.height)
        elif any(self.bus_ports.values()):
            self.height += 28 + 23 * max(len(self.bus_ports["input"]), len(self.bus_ports["output"]))
        self.setPos(component.x, component.y)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(2)
        self.pin_items = {}
        self.pin_coords = {}
        n = bit_width(component)
        pitch = 34 if component.kind == "NOT" else 38
        def position(direction, name, index):
            if self.designed_block:
                return self.block_positions[direction, name][0]
            if not self.sliced:
                return QPointF(0 if direction == "input" else self.width, 47 + index * 24)
            if name.startswith("A") and name[1:].isdigit():
                return QPointF(0, 55 + int(name[1:]) * pitch)
            if name.startswith("B") and name[1:].isdigit():
                return QPointF(0, 71 + int(name[1:]) * pitch)
            if name.startswith("Q") and name[1:].isdigit():
                return QPointF(self.width, 63 + int(name[1:]) * pitch)
            if component.kind == "Demultiplexer" and name.startswith("Q0_"):
                return QPointF(self.width, 55 + int(name[3:]) * pitch)
            if component.kind == "Demultiplexer" and name.startswith("Q1_"):
                return QPointF(self.width, 71 + int(name[3:]) * pitch)
            if name in ("LT", "EQ", "GT"):
                return QPointF(self.width, 55 + n * pitch + ("LT", "EQ", "GT").index(name) * 24)
            offset = 0 if direction == "input" else self.width
            extras = [p for p in (self.ins if direction == "input" else self.outs)
                      if not (p.startswith("A") and p[1:].isdigit() or p.startswith("B") and p[1:].isdigit()
                              or p.startswith("Q") and p[1:].isdigit() or p.startswith("Q0_") or p.startswith("Q1_"))]
            return QPointF(offset, 55 + n * pitch + extras.index(name) * 24)
        for direction, names, x in (("input", self.visible_ins, 0), ("output", self.visible_outs, self.width)):
            for i, name in enumerate(names):
                point = position(direction, name, i)
                self.pin_coords[direction, name] = point
                self.pin_items[direction, name] = PinItem(self, name, direction, point.x(), point.y())
        self.bus_pin_items = {}
        rows = max(len(self.bus_ports["input"]), len(self.bus_ports["output"]))
        for direction in ("input", "output"):
            for index, (port, names) in enumerate(self.bus_ports[direction].items()):
                point = (QPointF(-12 if direction == "input" else self.width + 12,
                                 min(self.height - 18, 44 + index * 24)) if self.designed_block else
                         QPointF(0 if direction == "input" else self.width,
                                 self.height - 17 - (rows - 1 - index) * 23))
                self.bus_pin_items[direction, port] = PinItem(
                    self, port, direction, point.x(), point.y(), is_bus=True, width=len(names))
        self.setToolTip(nice_name(component.kind) + (" · visual only" if component.kind in ANALOG else ""))

    def boundingRect(self):
        if self.designed_block:
            return QRectF(-12, -12, self.width + 24, self.height + 24)
        return QRectF(-11, -3, self.width + 22, self.height + 6)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        if self.designed_block:
            paint_designed_block(painter, self.block_definition, nice_name(self.component.kind),
                                 self.width, self.height, self.block_positions, self.isSelected())
            painter.setPen(QColor("#65d7bd"))
            painter.setFont(QFont("Sans Serif", 7, QFont.Bold))
            for (direction, port), item in self.bus_pin_items.items():
                x = 0 if direction == "input" else self.width - 37
                painter.drawText(QRectF(x, item.pos().y() - 8, 37, 16), Qt.AlignCenter,
                                 f"{port}{item.bus_width}b")
            self.paint_trace_outline(painter)
            return
        painter.setPen(QPen(QColor("#607b97"), 2, Qt.SolidLine, Qt.RoundCap))
        for (direction, _), point in self.pin_coords.items():
            if direction == "input":
                painter.drawLine(QPointF(0, point.y()), QPointF(23, point.y()))
            else:
                painter.drawLine(QPointF(self.width - 23, point.y()), QPointF(self.width, point.y()))
        visual_params = self.component.params
        if self.component.kind in ("INPUT", "CONST") and any(
                (self.component.id, pin) in self.editor.sim.forced_outputs for pin in self.outs):
            bits = [self.editor.sim.outputs.get((self.component.id, pin)) for pin in self.outs]
            if all(bit in (0, 1) for bit in bits):
                visual_params = {**visual_params, "value": sum(bit << i for i, bit in enumerate(bits))}
        paint_component_body(painter, self.component.kind, self.width, self.height,
                             self.isSelected(), visual_params,
                             self.pin_coords if self.sliced else None)
        painter.setFont(QFont("Sans Serif", 9, QFont.DemiBold))
        painter.setPen(TEXT)
        label = self.component.params.get("label", "") if self.component.kind in ("INPUT", "OUTPUT") else ""
        title = ("7-Segment" if self.component.kind == "Seven-segment Display" else nice_name(self.component.kind)) + (" · " + str(label) if label else "")
        draw_symbol(painter, self.component.kind, QRectF(10, 7, 20, 20))
        show_width = self.component.kind in BIT_WIDTH_KINDS and bit_width(self.component) > 1
        title_width = self.width - (76 if show_width else 46)
        painter.drawText(QRectF(37, 5, title_width, 25), Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(title, Qt.ElideRight, int(title_width)))
        if show_width:
            painter.setPen(QPen(BLUE, 1))
            painter.setBrush(QColor("#263b52"))
            painter.drawRoundedRect(QRectF(self.width - 32, 7, 29, 19), 5, 5)
            painter.setPen(QColor("#d3e7ff"))
            painter.setFont(QFont("Sans Serif", 7, QFont.Bold))
            painter.drawText(QRectF(self.width - 32, 7, 29, 19), Qt.AlignCenter, f"{bit_width(self.component)}b")
        painter.setFont(QFont("Sans Serif", 8))
        painter.setPen(MUTED)
        for name in self.visible_ins:
            y = self.pin_coords["input", name].y()
            painter.drawText(QRectF(14, y - 10, 62, 20), Qt.AlignVCenter, name)
        for name in self.visible_outs:
            y = self.pin_coords["output", name].y()
            painter.drawText(QRectF(self.width - 73, y - 10, 59, 20), Qt.AlignVCenter | Qt.AlignRight, name)
        for (direction, port), item in self.bus_pin_items.items():
            y = item.pos().y()
            painter.setPen(QColor("#65d7bd"))
            painter.setFont(QFont("Sans Serif", 8, QFont.DemiBold))
            rect = QRectF(16 if direction == "input" else self.width - 86, y - 11, 70, 21)
            align = Qt.AlignVCenter | (Qt.AlignLeft if direction == "input" else Qt.AlignRight)
            painter.drawText(rect, align, f"{port}[{item.bus_width - 1}:0]")
        if self.component.kind in ("INPUT", "CONST") and bit_width(self.component) > 1:
            value = visual_params.get("value", 0)
            painter.setPen(GREEN if value else LOW)
            painter.setFont(QFont("Sans Serif", 11, QFont.Bold))
            text = "X" if value is None else f"0x{value:X}"
            value_rect = (QRectF(72, 37, 42, 27) if self.component.kind == "INPUT"
                          else QRectF(64, 37, 60, 27))
            painter.drawText(value_rect, Qt.AlignCenter, text)
        if self.component.kind in ("CONST", "Clock Generator", "Oscillator") and bit_width(self.component) == 1:
            val = self.editor.sim.outputs.get((self.component.id, "Q"))
            painter.setPen(signal_color(val))
            painter.setFont(QFont("Sans Serif", 13, QFont.Bold))
            value_rect = QRectF(73, 38, 26, 26) if self.component.kind == "CONST" else QRectF(118, 39, 23, 25)
            painter.drawText(value_rect, Qt.AlignCenter, "X" if val is None else str(val))
        if self.component.kind == "OUTPUT":
            if bit_width(self.component) == 1:
                val = self.editor.sim.inputs.get(self.component.id, {}).get("A")
                draw_bulb(painter, QPointF(self.width - 35, 51), 9, GREEN, val == 1, led=True, unknown=val is None)
            else:
                values = self.editor.sim.inputs.get(self.component.id, {})
                bits = [values.get(f"A{i}") for i in range(bit_width(self.component))]
                value = None if None in bits else sum(bit << i for i, bit in enumerate(bits))
                painter.setFont(QFont("Sans Serif", 11, QFont.Bold))
                painter.setPen(GREEN if value else (UNKNOWN if value is None else LOW))
                painter.drawText(QRectF(76, 39, 69, 31), Qt.AlignCenter,
                                 "X" if value is None else f"0x{value:X}")
        if self.component.kind in ("Lamp", "LED", "RGB", "RGB Lamp", "RGB LED"):
            values = self.editor.sim.inputs.get(self.component.id, {})
            rgb = self.component.kind.startswith("RGB")
            if rgb:
                color = QColor(*(255 if values.get(channel) == 1 else 0 for channel in ("R", "G", "B")))
                on = any(values.get(channel) == 1 for channel in ("R", "G", "B"))
                unknown = any(values.get(channel) is None for channel in ("R", "G", "B"))
            else:
                default_color = "Red" if self.component.kind == "LED" else "Warm white"
                color = LAMP_COLORS.get(self.component.params.get("color", default_color), LAMP_COLORS[default_color])
                on = values.get("A") == 1
                unknown = values.get("A") is None
            led = self.component.kind.endswith("LED")
            center = QPointF(119, 72 if rgb else 59)
            draw_bulb(painter, center, 13 if led else 17, color, on, led=led, unknown=unknown)
        if self.component.kind == "Seven-segment Display":
            draw_seven_segment(painter, self.editor.sim.inputs.get(self.component.id, {}))
        if self.component.kind in ("Bus Input", "Bus Output", "Bus Probe"):
            direction, port = ("output", "Q") if self.component.kind == "Bus Input" else ("input", "D")
            names = self.bus_ports[direction][port]
            values = (self.editor.sim.outputs if direction == "output"
                      else self.editor.sim.inputs.get(self.component.id, {}))
            bits = [values.get((self.component.id, pin)) if direction == "output" else values.get(pin)
                    for pin in names]
            painter.setPen(UNKNOWN if None in bits else QColor("#b1f4e4"))
            painter.setFont(QFont("Monospace", 12, QFont.Bold))
            painter.drawText(QRectF(24, 68, self.width - 48, 32), Qt.AlignCenter,
                             format_bus(bits, self.component.params.get("display", "binary")))
            if self.component.kind == "Bus Probe":
                painter.setFont(QFont("Monospace", 8))
                summary = f"{format_bus(bits, 'binary')}  ·  {format_bus(bits, 'hex')}  ·  {format_bus(bits, 'decimal')}"
                painter.drawText(QRectF(18, 103, self.width - 36, 32), Qt.AlignCenter, summary)
        self.paint_trace_outline(painter)

    def paint_trace_outline(self, painter):
        if self.component.id not in self.editor.trace_components:
            return
        active = self.component.id in self.editor.trace_active_components
        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#f6c779" if active else "#6ea8fe"), 3 if active else 2))
        painter.drawRoundedRect(QRectF(3, 28, self.width - 6, self.height - 34), 11, 11)
        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.editor.snap:
            value = QPointF(round(value.x() / 20) * 20, round(value.y() / 20) * 20)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.component.x, self.component.y = self.pos().x(), self.pos().y()
            self.editor.update_wires_for(self.component.id)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        if self.component.kind == "INPUT":
            self.editor.toggle_input(self.component.id)
            event.accept()
        elif self.component.kind.startswith("BLOCK:"):
            self.editor.open_block_designer(self.component.id)
            event.accept()
        else:
            self.editor.edit_component(self.component.id)
            event.accept()


def component_preview(editor, kind):
    """Visible drag image: a rendered component with its pins and placement rim."""
    if kind.startswith("LIB:"):
        entry = editor.global_library.get(kind[4:])
        definition = entry["definition"]
        if definition.get("designer"):
            width, height = block_geometry(definition)
            positions = terminal_positions(definition, width, height)
            pixmap = QPixmap(width + 30, height + 30)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.translate(15, 15)
            paint_designed_block(painter, definition, entry["name"], width, height, positions)
            painter.setPen(QPen(QColor("#9acaff"), 2))
            painter.setBrush(QColor("#11151c"))
            for point, _ in positions.values():
                painter.drawEllipse(point, 5, 5)
            painter.end()
            return pixmap
        pixmap = QPixmap(220, 110)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#203747"))
        painter.setPen(QPen(QColor("#6ce4cf"), 2))
        painter.drawRoundedRect(QRectF(8, 8, 204, 94), 13, 13)
        painter.setPen(TEXT)
        painter.setFont(QFont("Sans Serif", 11, QFont.DemiBold))
        painter.drawText(QRectF(22, 20, 177, 30), Qt.AlignVCenter, entry["name"])
        painter.setPen(MUTED)
        painter.setFont(QFont("Sans Serif", 8))
        info = f"{len(entry['definition']['inputs'])} in  ·  {len(entry['definition']['outputs'])} out  ·  v{entry['version']}"
        painter.drawText(QRectF(22, 52, 177, 28), Qt.AlignVCenter, info)
        painter.end()
        return pixmap
    component = Component("drag-preview", kind)
    item = ComponentItem(editor, component)
    pixmap = QPixmap(int(item.width + 30), int(item.height + 24))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    halo = QColor("#6ea8fe"); halo.setAlpha(55)
    painter.setPen(QPen(QColor("#a9d0ff"), 2.5, Qt.DashLine))
    painter.setBrush(halo)
    painter.drawRoundedRect(QRectF(4, 3, pixmap.width() - 8, pixmap.height() - 6), 11, 11)
    painter.translate(15, 12)
    item.paint(painter, None)
    painter.setPen(QPen(QColor("#a3c9ff"), 2))
    painter.setBrush(QColor("#172637"))
    for pin in (*item.pin_items.values(), *item.bus_pin_items.values()):
        painter.drawEllipse(pin.pos(), 5.5, 5.5)
    painter.end()
    if pixmap.height() > 240:
        return pixmap.scaledToHeight(240, Qt.SmoothTransformation)
    return pixmap


class WireBendHandle(QGraphicsEllipseItem):
    def __init__(self, wire_item, index):
        super().__init__(-6, -6, 12, 12, wire_item)
        self.wire_item, self.index = wire_item, index
        self.syncing = False
        self.setZValue(2)
        self.setBrush(QBrush(QColor("#192c3b")))
        self.setPen(QPen(QColor("#b0d8ff"), 2))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setToolTip("Drag to move routing corner")

    def mousePressEvent(self, event):
        self.wire_item.editor.push_history()
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and not self.syncing:
            self.wire_item.wire.bends[self.index] = point_tuple(self.scenePos())
            self.wire_item.update_path()
        return super().itemChange(change, value)


class WireItem(QGraphicsPathItem):
    def __init__(self, editor, wire):
        super().__init__()
        self.editor, self.wire = editor, wire
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(0)
        self.setAcceptHoverEvents(True)
        self.handles = []
        self.update_path()

    def sync_handles(self):
        if len(self.handles) != len(self.wire.bends):
            for handle in self.handles:
                handle.setParentItem(None)
                if handle.scene(): handle.scene().removeItem(handle)
            self.handles = [WireBendHandle(self, index) for index in range(len(self.wire.bends))]
        for handle, point in zip(self.handles, self.wire.bends):
            handle.syncing = True
            handle.setPos(QPointF(*point))
            handle.syncing = False
            handle.setVisible(self.isSelected())

    def insert_bend(self, point):
        start = self.editor.pin_position(self.wire.source, "output", self.wire.source_pin)
        end = self.editor.pin_position(self.wire.target, "input", self.wire.target_pin)
        if start is None or end is None:
            return
        waypoints = [start] + [QPointF(*bend) for bend in self.wire.bends] + [end]
        nearest, insertion = float("inf"), len(self.wire.bends)
        for index, (a, b) in enumerate(zip(waypoints, waypoints[1:])):
            corner = QPointF(b.x(), a.y())
            segments = ((a, corner), (corner, b)) if a.x() != b.x() and a.y() != b.y() else ((a, b),)
            for first, second in segments:
                dx, dy = second.x() - first.x(), second.y() - first.y()
                length = dx * dx + dy * dy
                fraction = max(0, min(1, ((point.x() - first.x()) * dx +
                                          (point.y() - first.y()) * dy) / length)) if length else 0
                distance = (point.x() - first.x() - fraction * dx) ** 2 + (point.y() - first.y() - fraction * dy) ** 2
                if distance < nearest:
                    nearest, insertion = distance, index
        self.wire.bends.insert(insertion, point_tuple(point))
        self.update_path()

    def update_path(self):
        points = self.editor.raw_wire_points(self.wire)
        if not points: return
        path = QPainterPath(points[0])
        for first, second in zip(points, points[1:]):
            if first.y() == second.y() and first.x() != second.x():
                crossings = []
                for other in self.editor.circuit.wires.values():
                    if other.id == self.wire.id or (other.source, other.source_pin) == (self.wire.source, self.wire.source_pin):
                        continue
                    other_points = self.editor.raw_wire_points(other)
                    for a, b in zip(other_points, other_points[1:]):
                        if a.x() == b.x() and a.y() != b.y() and min(first.x(), second.x()) + 8 < a.x() < max(first.x(), second.x()) - 8 and min(a.y(), b.y()) + 8 < first.y() < max(a.y(), b.y()) - 8:
                            crossings.append(a.x())
                for x in sorted(set(crossings), reverse=second.x() < first.x()):
                    direction = 1 if second.x() > first.x() else -1
                    path.lineTo(x - direction * 6, first.y())
                    path.moveTo(x + direction * 6, first.y())
            path.lineTo(second)
        self.setPath(path)
        self.sync_handles()
        if isinstance(self.wire, BusWire):
            bits = tuple(self.editor.sim.outputs.get((self.wire.source, pin)) for pin in self.wire.source_bits)
            color_value = None if None in bits else (0 if not any(bits) else (1 if all(bits) else "mixed"))
        else:
            color_value = self.editor.sim.outputs.get((self.wire.source, self.wire.source_pin))
        active = self.wire.id in self.editor.trace_active_wires
        connected = self.wire.id in self.editor.trace_wires
        color = QColor("#f6c779") if active else (QColor("#6ea8fe") if connected else
                (BLUE if self.isSelected() else signal_color(color_value)))
        if isinstance(self.wire, BusWire) and not (active or connected or self.isSelected()):
            color = (UNKNOWN if color_value is None else
                     GREEN if color_value == 1 else LOW if color_value == 0 else QColor("#65d7bd"))
        thickness = 5.4 if isinstance(self.wire, BusWire) else 3.2
        self.setPen(QPen(color, 5.8 if active else (5.5 if connected else thickness),
                         Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if not isinstance(self.wire, BusWire):
            return
        point = self.path().pointAtPercent(0.5)
        painter.save()
        painter.setPen(QColor("#d7f8f0"))
        painter.setBrush(QColor("#153b3b"))
        painter.drawRoundedRect(QRectF(point.x() - 17, point.y() - 11, 34, 20), 5, 5)
        painter.setFont(QFont("Sans Serif", 8, QFont.Bold))
        painter.drawText(QRectF(point.x() - 17, point.y() - 11, 34, 20), Qt.AlignCenter,
                         f"{self.wire.width}b")
        painter.restore()

    def shape(self):
        stroke = super().shape()
        from PySide6.QtGui import QPainterPathStroker
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path()).united(stroke)

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.editor.start_branch(self.wire, event.scenePos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        ref = SignalRef.wire(self.wire.id)
        backward = menu.addAction("Trace Backward")
        forward = menu.addAction("Trace Forward")
        explain = menu.addAction("Explain Signal")
        menu.addSeparator()
        add = menu.addAction("Add wire to Timing Diagram")
        bend = menu.addAction("Add routing corner here")
        clear_bends = menu.addAction("Reset routing corners")
        chosen = menu.exec(event.screenPos())
        if chosen == add:
            self.editor.add_timing_signal(ref)
        elif chosen in (backward, forward, explain):
            self.editor.trace_signal(ref, {backward: 0, forward: 1, explain: 2}[chosen])
        elif chosen == bend:
            self.editor.push_history()
            self.insert_bend(event.scenePos())
        elif chosen == clear_bends:
            self.editor.push_history()
            self.wire.bends.clear()
            self.update_path()
        event.accept()


class CircuitScene(QGraphicsScene):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setSceneRect(-50000, -50000, 100000, 100000)
        self.selectionChanged.connect(editor.selection_changed)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, BG)
        spacing = 20
        left = math.floor(rect.left() / spacing) * spacing
        top = math.floor(rect.top() / spacing) * spacing
        lines = []
        from PySide6.QtCore import QLineF
        for x in range(left, int(rect.right()) + spacing, spacing):
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
        for y in range(top, int(rect.bottom()) + spacing, spacing):
            lines.append(QLineF(rect.left(), y, rect.right(), y))
        painter.setPen(QPen(GRID, 0))
        painter.drawLines(lines)
        painter.setPen(QPen(QColor("#273140"), 0))
        painter.drawLine(0, rect.top(), 0, rect.bottom())
        painter.drawLine(rect.left(), 0, rect.right(), 0)


class Canvas(QGraphicsView):
    def __init__(self, editor):
        super().__init__(editor.scene)
        self.editor = editor
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.space_down = False
        self.panning = False
        self.pan_from_blank = False
        self.pan_moved = False
        self.pan_start = None
        self.drag_snapshot = None
        self.drag_ghost = None
        self.drop_target = None
        self.drag_phase = 0.0
        self.drag_timer = QTimer(self)
        self.drag_timer.setInterval(40)
        self.drag_timer.timeout.connect(self.pulse_drag_ghost)
        self.hover_target = None
        self.held_force = None
        self.tool_phase = 0.0
        self.tool_timer = QTimer(self)
        self.tool_timer.setInterval(40)
        self.tool_timer.timeout.connect(self.animate_tool)
        self.tool_cursors = {name: QCursor(tool_pixmap(name, 32), 16, 16)
                             for name in ("flip", "erase", "cut")}
        self.setMouseTracking(True)
        self.centerOn(0, 0)

    def set_active_tool(self, tool):
        self.cancel_tool_hold()
        self.hover_target = None
        if tool:
            self.tool_timer.start()
            self.setCursor(self.tool_cursors[tool])
        else:
            self.tool_timer.stop()
            self.unsetCursor()
        self.viewport().update()

    def cancel_tool_hold(self):
        if self.held_force:
            simulator, cid, pin, direction = self.held_force
            self.held_force = None
            simulator.release_pin(cid, pin, direction)
            if simulator is self.editor.sim:
                self.editor.refresh()
        self.hover_target = None
        self.viewport().update()

    def animate_tool(self):
        self.tool_phase += 0.16
        if self.hover_target or self.held_force:
            self.viewport().update()

    def resolve_tool_target(self, item):
        tool = self.editor.active_tool
        if tool == "flip":
            if isinstance(item, PinItem) and not item.is_bus and item.owner.component.kind not in ANALOG:
                return item
            if isinstance(item, ComponentItem) and item.component.kind == "INPUT" and bit_width(item.component) == 1:
                return item.pin_items.get(("output", "Q"))
        elif tool == "erase":
            if isinstance(item, WireBendHandle): return item.wire_item
            return item.owner if isinstance(item, PinItem) else (item if isinstance(item, (ComponentItem, WireItem)) else None)
        elif tool == "cut":
            return item.wire_item if isinstance(item, WireBendHandle) else (item if isinstance(item, WireItem) else None)
        return None

    def use_tool(self, target):
        tool = self.editor.active_tool
        if tool == "flip" and isinstance(target, PinItem):
            cid, pin, direction = target.owner.component.id, target.name, target.direction
            value = (self.editor.sim.inputs.get(cid, {}).get(pin) if direction == "input"
                     else self.editor.sim.outputs.get((cid, pin)))
            if value not in (0, 1):
                self.editor.set_status("Flip Probe needs a known 0 or 1 signal")
                return
            self.editor.sim.force_pin(cid, pin, direction, 1 - value)
            self.held_force = (self.editor.sim, cid, pin, direction)
            self.editor.refresh()
            self.editor.set_status(f"Flip Probe · {pin}: {value} → {1 - value} · release to restore")
        elif tool in ("erase", "cut"):
            self.editor.erase_tool_target(target, wires_only=tool == "cut")
        elif tool:
            self.editor.set_status("Point at a pin" if tool == "flip" else
                                   ("Point at a wire" if tool == "cut" else "Point at a component or wire"))

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        tool = self.editor.active_tool
        target = self.hover_target
        if not tool or not target:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        scale = max(0.18, self.transform().m11())
        color = TOOL_COLORS[tool]
        if isinstance(target, PinItem):
            pos = target.scenePos()
            held = self.held_force is not None
            radius = (13 + 2.5 * math.sin(self.tool_phase)) / scale
            glow = QColor(color); glow.setAlpha(55 if held else 30)
            painter.setBrush(glow)
            painter.setPen(QPen(color, (2.8 if held else 1.8) / scale))
            painter.drawEllipse(pos, radius, radius)
            if held:
                painter.setPen(QPen(color, 1.7 / scale, Qt.SolidLine, Qt.RoundCap))
                for index in range(6):
                    angle = index * math.tau / 6 + self.tool_phase * 0.3
                    inner, outer = 17 / scale, (20 + 2 * math.sin(self.tool_phase)) / scale
                    painter.drawLine(pos + QPointF(math.cos(angle) * inner, math.sin(angle) * inner),
                                     pos + QPointF(math.cos(angle) * outer, math.sin(angle) * outer))
        elif isinstance(target, WireItem):
            glow = QColor(color); glow.setAlpha(70)
            painter.setPen(QPen(glow, (11 + 2 * math.sin(self.tool_phase)) / scale,
                                Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(target.path())
            painter.setPen(QPen(color, 2.2 / scale, Qt.DashLine))
            painter.drawPath(target.path())
        elif isinstance(target, ComponentItem):
            box = target.sceneBoundingRect().adjusted(-5 / scale, -5 / scale, 5 / scale, 5 / scale)
            glow = QColor(color); glow.setAlpha(32)
            painter.setBrush(glow)
            painter.setPen(QPen(color, (2 + math.sin(self.tool_phase) * 0.5) / scale, Qt.DashLine))
            painter.drawRoundedRect(box, 9 / scale, 9 / scale)
        painter.restore()

    def wheelEvent(self, event):
        scale = 1.14 if event.angleDelta().y() > 0 else 1 / 1.14
        current = self.transform().m11()
        if 0.18 <= current * scale <= 3.5:
            self.scale(scale, scale)
            self.editor.set_status(f"Zoom {int(self.transform().m11() * 100)}%")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.space_down = True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
        elif event.key() == Qt.Key_Escape:
            self.editor.cancel_wire()
            self.editor.pending_kind = None
            self.editor.set_tool(None)
            self.editor.set_status("Ready")
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.space_down = False
            if self.editor.active_tool:
                self.setCursor(self.tool_cursors[self.editor.active_tool])
            else:
                self.unsetCursor()
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        point = event.position().toPoint()
        clicked = self.itemAt(point)
        blank_pan = (event.button() == Qt.LeftButton and clicked is None
                     and not event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier)
                     and not self.editor.pending_kind and not self.editor.wire_start)
        if event.button() == Qt.MiddleButton or (self.space_down and event.button() == Qt.LeftButton) or blank_pan:
            self.panning = True
            self.pan_from_blank = blank_pan
            self.pan_moved = False
            self.pan_start = point
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if self.editor.active_tool and event.button() == Qt.LeftButton:
            self.hover_target = self.resolve_tool_target(clicked)
            self.use_tool(self.hover_target)
            self.viewport().update()
            event.accept()
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        if self.editor.pending_kind and event.button() == Qt.LeftButton:
            self.editor.place_component(self.editor.pending_kind, scene_pos)
            event.accept()
            return
        if self.editor.wire_start and event.button() == Qt.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if not isinstance(item, PinItem):
                self.editor.add_wire_bend(scene_pos)
                event.accept()
                return
        item = clicked
        self.drag_snapshot = None if isinstance(item, PinItem) else json.dumps(self.editor.circuit.to_dict(), sort_keys=True)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.panning:
            delta = event.position().toPoint() - self.pan_start
            if delta.manhattanLength() > 2:
                self.pan_moved = True
            self.pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
        elif self.editor.active_tool:
            if not self.held_force:
                self.hover_target = self.resolve_tool_target(self.itemAt(event.position().toPoint()))
            self.setCursor(self.tool_cursors[self.editor.active_tool])
            self.viewport().update()
            event.accept()
        else:
            super().mouseMoveEvent(event)
            if self.editor.wire_start:
                self.editor.update_preview(self.mapToScene(event.position().toPoint()))
            elif not self.editor.pending_kind:
                self.setCursor(Qt.OpenHandCursor if self.itemAt(event.position().toPoint()) is None else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.panning:
            self.panning = False
            if self.pan_from_blank and not self.pan_moved:
                self.editor.scene.clearSelection()
            self.setCursor(self.tool_cursors[self.editor.active_tool] if self.editor.active_tool else Qt.OpenHandCursor)
            event.accept()
            return
        if self.editor.active_tool and event.button() == Qt.LeftButton:
            self.cancel_tool_hold()
            self.hover_target = self.resolve_tool_target(self.itemAt(event.position().toPoint()))
            self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.drag_snapshot and self.drag_snapshot != json.dumps(self.editor.circuit.to_dict(), sort_keys=True):
            self.editor.push_history(self.drag_snapshot)
        self.drag_snapshot = None

    def focusOutEvent(self, event):
        self.cancel_tool_hold()
        super().focusOutEvent(event)

    def hideEvent(self, event):
        self.cancel_tool_hold()
        super().hideEvent(event)

    def leaveEvent(self, event):
        if not self.held_force:
            self.hover_target = None
            self.viewport().update()
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        if self.itemAt(event.pos()) is not None:
            return super().contextMenuEvent(event)
        menu = QMenu(self)
        open_manager = menu.addAction("Open Testbench Manager…")
        run_all = menu.addAction("Run all testbenches")
        run_all.setEnabled(bool(self.editor.circuit.testbenches and
                                self.editor.circuit.testbenches.get("items")))
        chosen = menu.exec(event.globalPos())
        if chosen == open_manager:
            self.editor.open_testbench_manager()
        elif chosen == run_all:
            self.editor.open_testbench_manager(run_all=True)
        event.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(COMPONENT_MIME):
            kind = bytes(event.mimeData().data(COMPONENT_MIME)).decode("utf-8")
            if (kind in CATALOG or (kind.startswith("BLOCK:") and kind[6:] in self.editor.circuit.blocks)
                    or (kind.startswith("LIB:") and any(e["id"] == kind[4:] for e in self.editor.global_library.list_entries()))):
                self.clear_drag_ghost()
                self.drag_ghost = QGraphicsPixmapItem(component_preview(self.editor, kind))
                self.drag_ghost.setZValue(100)
                self.drag_ghost.setFlag(QGraphicsItem.ItemIgnoresTransformations)
                self.drag_ghost.setOpacity(0.94)
                self.scene().addItem(self.drag_ghost)
                self.drop_target = QGraphicsEllipseItem(-6, -6, 12, 12)
                self.drop_target.setZValue(101)
                self.drop_target.setFlag(QGraphicsItem.ItemIgnoresTransformations)
                self.drop_target.setBrush(QColor("#132539"))
                self.drop_target.setPen(QPen(BLUE, 2))
                self.scene().addItem(self.drop_target)
                self.drag_phase = 0
                self.drag_timer.start()
                self.move_drag_ghost(event.position().toPoint())
                event.acceptProposedAction()
                return
            event.ignore()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(COMPONENT_MIME):
            self.move_drag_ghost(event.position().toPoint())
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.clear_drag_ghost()
        self.editor.set_status("Drag a component from the library onto the canvas")
        event.accept()

    def move_drag_ghost(self, viewport_point):
        if not self.drag_ghost:
            return
        point = self.mapToScene(viewport_point)
        if self.editor.snap:
            point = QPointF(round(point.x() / 20) * 20, round(point.y() / 20) * 20)
        self.drag_ghost.setPos(point - QPointF(15, 12))
        if self.drop_target:
            self.drop_target.setPos(point)
        self.editor.set_status("Release to place · Esc to cancel")

    def pulse_drag_ghost(self):
        if not self.drag_ghost:
            self.drag_timer.stop()
            return
        self.drag_phase += 0.22
        self.drag_ghost.setOpacity(0.88 + 0.1 * math.sin(self.drag_phase))
        if self.drop_target:
            self.drop_target.setScale(1 + 0.12 * math.sin(self.drag_phase))

    def clear_drag_ghost(self):
        self.drag_timer.stop()
        if self.drag_ghost:
            self.scene().removeItem(self.drag_ghost)
            self.drag_ghost = None
        if self.drop_target:
            self.scene().removeItem(self.drop_target)
            self.drop_target = None

    def dropEvent(self, event):
        if event.mimeData().hasFormat(COMPONENT_MIME):
            kind = bytes(event.mimeData().data(COMPONENT_MIME)).decode("utf-8")
            if (kind in CATALOG or (kind.startswith("BLOCK:") and kind[6:] in self.editor.circuit.blocks)
                    or (kind.startswith("LIB:") and any(e["id"] == kind[4:] for e in self.editor.global_library.list_entries()))):
                point = self.mapToScene(event.position().toPoint())
                self.clear_drag_ghost()
                self.editor.cancel_wire()
                self.editor.place_component(kind, point)
                event.acceptProposedAction()
                return
            self.clear_drag_ghost()
        super().dropEvent(event)


class ComponentSettingsForm(QWidget):
    def __init__(self, component, parent=None):
        super().__init__(parent)
        self.controls = {}
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        kind = component.kind
        specs = []
        if kind in ("Clock Generator", "Oscillator"): specs = [("period", "Period (ticks)", 2, 10000, 4), ("running", "Running", None, None, True)]
        elif kind in ("D Flip-Flop", "JK Flip-Flop", "T Flip-Flop", "Register", "Shift Register", "Binary Counter", "Up Counter", "Down Counter", "Clock Divider", "Program Counter", "Instruction Register", "Register File"):
            specs = [("edge", "Clock edge", None, None, "rising")]
            if kind in ("Register", "Shift Register", "Binary Counter", "Up Counter", "Down Counter", "Program Counter", "Instruction Register"): specs.append(("width", "Bits", 1, 32, 4))
            if kind == "Register File":
                specs.extend((("registers", "Registers", 2, 32, 8), ("data_bits", "Data bits", 1, 32, 8),
                              ("read_ports", "Read ports", 1, 2, 2)))
            if kind == "Clock Divider": specs.append(("divide", "Divide by", 2, 1000, 2))
        elif kind in ("Adder", "Subtractor", "Multiplier", "Divider", "ALU"):
            specs = [("width", "Bits", 1, 32, 4)]
        elif kind in ("RAM", "ROM", "SRAM", "DRAM", "EEPROM", "Flash Memory"):
            specs = [("address_bits", "Address bits", 1, 8, 4), ("data_bits", "Data bits", 1, 32, 4),
                     ("depth", "Addresses", 1, 1 << int(component.params.get("address_bits", 4)),
                      1 << int(component.params.get("address_bits", 4)))]
            if kind in ("RAM", "ROM"):
                specs += [("read_mode", "Read mode", None, None, "async" if kind == "ROM" else "legacy"),
                          ("read_enable", "Read enable pin", None, None, False),
                          ("edge", "Clock edge", None, None, "rising")]
            if kind == "RAM":
                specs.append(("read_during_write", "Read during write", None, None, "new"))
            if kind == "DRAM": specs.append(("retention_ticks", "Retention (ticks)", 1, 100000, 64))
        elif kind == "Address Decoder":
            specs = [("address_bits", "Address bits", 1, 5, 3), ("outputs", "Select outputs", 2, 32, 8)]
        elif kind == "Control Unit":
            specs = [("opcode_bits", "Opcode bits", 4, 8, 4)]
        elif kind in ("Timer", "Pulse Generator"):
            specs = [("duration", "Duration (ticks)", 1, 10000, 5)]
        elif kind in ("INPUT", "CONST"):
            specs = [("value", "Value (decimal)", 0, (1 << bit_width(component)) - 1,
                      0 if kind == "INPUT" else 1)]
        elif kind == "Bit Selector":
            specs = [("index", "Selected bit", 0, bit_width(component) - 1, 0)]
        elif kind in ("Lamp", "LED"):
            specs = [("color", "Light color", None, None, "Warm white" if kind == "Lamp" else "Red")]
        if kind in BIT_WIDTH_KINDS:
            maximum = 8 if kind in ("INPUT", "OUTPUT", "CONST") else 32
            specs = [("width", "Bit width", 2 if kind in BUS_COMPONENTS else 1, maximum, bit_width(component)) if key == "width" else
                     (key, label, minimum, maximum, default)
                     for key, label, minimum, maximum, default in specs]
            if not any(key == "width" for key, *_ in specs):
                specs.insert(0, ("width", "Bit width", 2 if kind in BUS_COMPONENTS else 1, maximum, bit_width(component)))
        if kind in ("INPUT", "OUTPUT"):
            self.label_control = QLineEdit(str(component.params.get("label", "")))
            self.label_control.setPlaceholderText("Optional terminal name")
            form.addRow("Terminal name", self.label_control)
        else:
            self.label_control = None
        for key, label, minimum, maximum, default in specs:
            current = component.params.get(key, default)
            if isinstance(default, bool):
                control = QCheckBox()
                control.setChecked(bool(current))
            elif key == "edge":
                control = QComboBox()
                control.addItems(["rising", "falling"])
                control.setCurrentText(str(current))
            elif key == "read_mode":
                control = QComboBox()
                control.addItems(["async", "sync"] if kind == "ROM" else ["legacy", "async", "sync"])
                control.setCurrentText(str(current))
            elif key == "read_during_write":
                control = QComboBox()
                control.addItems(["new", "old", "no_change"])
                control.setCurrentText(str(current))
            elif key == "color":
                control = QComboBox()
                control.addItems(list(LAMP_COLORS))
                control.setCurrentText(str(current))
            elif key == "width" and kind in BUS_COMPONENTS:
                control = QComboBox()
                for width in BUS_WIDTHS: control.addItem(str(width), width)
                control.setCurrentIndex(control.findData(int(current)))
            elif key == "opcode_bits":
                control = QComboBox()
                for width in (4, 8): control.addItem(str(width), width)
                control.setCurrentIndex(control.findData(int(current)))
            else:
                control = QSpinBox()
                control.setRange(minimum, maximum)
                control.setValue(int(current))
            form.addRow(label, control)
            self.controls[key] = control
        if "width" in self.controls and "value" in self.controls:
            self.controls["width"].valueChanged.connect(
                lambda width: self.controls["value"].setRange(0, (1 << width) - 1))
        if "address_bits" in self.controls and "depth" in self.controls:
            self.controls["address_bits"].valueChanged.connect(
                lambda width: self.controls["depth"].setMaximum(1 << width))
        if kind == "Address Decoder":
            self.controls["address_bits"].valueChanged.connect(
                lambda width: self.controls["outputs"].setMaximum(1 << width))
        self.bus_value = None
        if kind == "Bus Input":
            bits = component.params.get("_bit_values")
            if bits is None:
                bits = [(int(component.params.get("value", 0)) >> index) & 1
                        for index in range(bit_width(component))]
            self.bus_value = QLineEdit("0b" + "".join("X" if bit is None else str(bit) for bit in reversed(bits)))
            self.bus_value.setPlaceholderText("0b1010, 0xA, decimal 10 or 0b10X0")
            form.addRow("Input value", self.bus_value)
        self.exposed_bits = None
        if kind == "Bus Splitter":
            self.exposed_bits = QLineEdit(", ".join(str(index) for index in component.params.get(
                "expose", list(range(bit_width(component))))))
            form.addRow("Exposed bit indices", self.exposed_bits)
        self.bus_format = None
        if kind in ("Bus Input", "Bus Output", "Bus Probe"):
            self.bus_format = QComboBox()
            self.bus_format.addItems(("binary", "hex", "decimal"))
            self.bus_format.setCurrentText(component.params.get("display", "binary"))
            form.addRow("Display", self.bus_format)
        self.show_bits = None
        if kind in BUS_COMPONENTS or (kind in BIT_WIDTH_KINDS and bit_width(component) >= 16) or kind in (
                "RAM", "ROM", "SRAM", "DRAM", "EEPROM", "Flash Memory", "Register File",
                "ISA Control Unit"):
            self.show_bits = QCheckBox()
            self.show_bits.setChecked(bool(component.params.get("show_bits", False)))
            form.addRow("Show individual bit pins", self.show_bits)
        if kind == "Bit Selector":
            width_control = self.controls["width"]
            width_control.currentIndexChanged.connect(
                lambda: self.controls["index"].setMaximum(width_control.currentData() - 1))
        if kind in BIT_WIDTH_KINDS:
            if kind in BUS_COMPONENTS:
                form.addRow("Bit order", QLabel("Bit 0 = least significant (fixed)"))
            note = QLabel("Native bus ports appear at 2, 4, 8, 16 or 32 bits. Bit 0 is LSB.")
            note.setWordWrap(True)
            form.addRow(note)
        self.contents_key = "contents" if kind == "ROM" else "init" if kind == "RAM" else "microcode" if kind == "Control Unit" else None
        if self.contents_key:
            self.contents = QTextEdit()
            self.contents.setPlaceholderText('{"0": 3, "1": 7}' if kind in ("ROM", "RAM") else '{"0": {"alu": 0, "REG_WE": 1}}')
            default_contents = {} if kind in ("ROM", "RAM") else DEFAULT_MICROCODE
            self.contents.setPlainText(json.dumps(component.params.get(self.contents_key, default_contents), indent=2))
            self.contents.setFixedHeight(110)
            form.addRow("Contents (JSON)" if kind == "ROM" else "Initial data (JSON)" if kind == "RAM" else "Microcode (JSON)", self.contents)
        else:
            self.contents = None
        if kind in ANALOG:
            form.addRow(QLabel("Visual placeholder. No electrical simulation."))
        self.has_settings = bool(self.controls or self.label_control or self.contents or self.bus_value or self.exposed_bits)
        if not self.has_settings and kind not in ANALOG:
            form.addRow(QLabel("No configurable settings."))
        try:
            self.initial_values = self.values() if self.has_settings else {}
        except (ValueError, TypeError):
            self.initial_values = None

    def values(self):
        result = {}
        for key, control in self.controls.items():
            if isinstance(control, QCheckBox): result[key] = control.isChecked()
            elif isinstance(control, QComboBox): result[key] = control.currentData() if key in ("width", "opcode_bits") else control.currentText()
            else: result[key] = control.value()
        if self.bus_value is not None:
            width = result["width"]
            raw = self.bus_value.text().strip().replace("_", "")
            if raw.lower().startswith("0b") or "X" in raw.upper():
                binary = raw[2:] if raw.lower().startswith("0b") else raw
                if len(binary) != width or any(char not in "01Xx" for char in binary):
                    raise ValueError(f"Bus Input: enter exactly {width} binary digits (0, 1 or X)")
                result["_bit_values"] = [None if char.upper() == "X" else int(char)
                                         for char in reversed(binary)]
                result["value"] = 0
            else:
                try: value = int(raw, 16 if raw.lower().startswith("0x") else 10)
                except ValueError: raise ValueError("Bus Input: enter binary, hexadecimal or decimal value") from None
                if not 0 <= value < (1 << width):
                    raise ValueError(f"Bus Input: value must fit in {width} bits")
                result["value"] = value
                result["_bit_values"] = [(value >> index) & 1 for index in range(width)]
        if self.exposed_bits is not None:
            try: result["expose"] = [int(text.strip()) for text in self.exposed_bits.text().split(",")]
            except ValueError: raise ValueError("Bus Splitter: use comma-separated bit indices") from None
        if self.bus_format is not None:
            result["display"] = self.bus_format.currentText()
        if self.show_bits is not None:
            result["show_bits"] = self.show_bits.isChecked()
        if self.contents:
            contents = json.loads(self.contents.toPlainText() or "{}")
            if not isinstance(contents, dict):
                raise ValueError("Contents must be a JSON object")
            result[self.contents_key] = contents
        if self.label_control:
            result["label"] = self.label_control.text().strip()
        return result


class Editor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "resources" / "logicspace.png")))
        self.setWindowTitle("LogicSpace — Untitled")
        self.resize(1440, 900)
        self.circuit = Circuit()
        self.sim = Simulator(self.circuit)
        self.global_library = ComponentLibrary()
        self.timing_history = TimingHistory()
        self.trace_history = TraceHistory(self.timing_history.limit)
        self.time_history = SimulationHistory(self.sim)
        self.breakpoints = BreakpointManager()
        self.last_break_events = []
        self.cpu_breakpoints = CpuBreakpointManager()
        self.last_cpu_events = []
        self._syncing_time_cursor = False
        self.trace_components, self.trace_wires = set(), set()
        self.trace_active_components, self.trace_active_wires = set(), set()
        self._trace_refresh_suppressed = False
        self.path = None
        self.dirty = False
        self.snap = True
        self.active_tool = None
        self.tool_buttons = {}
        self.designer_windows = []
        self.history, self.future = [], []
        self.clipboard = None
        self.paste_count = 0
        self.pending_kind = None
        self.wire_start = None
        self.wire_bends = []
        self.component_items = {}
        self.wire_items = {}
        self.preview = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.timer.setInterval(250)
        self._build_ui()
        self._build_actions()
        self.render()
        self.show_experience("welcome")
        self.updates = UpdateController(self)
        self.updates.schedule_startup()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        vertical = QVBoxLayout(root)
        vertical.setContentsMargins(0, 0, 0, 0)
        vertical.setSpacing(0)
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(62)
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(20, 10, 20, 10)
        bar.setSpacing(8)
        logo_icon = QLabel()
        logo_icon.setPixmap(self.windowIcon().pixmap(29, 29))
        bar.addWidget(logo_icon)
        logo = QLabel("LogicSpace")
        logo.setObjectName("logo")
        bar.addWidget(logo)
        bar.addSpacing(25)
        for label, callback, obj in (("▶ Run", self.toggle_run, "run"), ("Step", self.step, "step"), ("Reset", self.reset, "reset")):
            button = QPushButton(label)
            button.setObjectName(obj)
            button.clicked.connect(callback)
            bar.addWidget(button)
            if obj == "run": self.run_button = button
        bar.addSpacing(15)
        bar.addWidget(QLabel("Speed"))
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(1, 20)
        self.speed.setValue(4)
        self.speed.setFixedWidth(110)
        self.speed.valueChanged.connect(lambda n: self.timer.setInterval(max(25, 1000 // n)))
        bar.addWidget(self.speed)
        bar.addStretch()
        self.snap_button = QPushButton("⌗  Snap on")
        self.snap_button.clicked.connect(self.toggle_snap)
        bar.addWidget(self.snap_button)
        save_button = QPushButton("Save")
        save_button.setObjectName("primary")
        save_button.clicked.connect(self.save)
        bar.addWidget(save_button)
        vertical.addWidget(toolbar)

        content = QSplitter(Qt.Horizontal)
        self.content_splitter = content
        content.setChildrenCollapsible(False)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(270)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(9, 10, 6, 9)
        side.setSpacing(0)
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setObjectName("sidebarTabs")
        side.addWidget(self.sidebar_tabs)
        component_page = QWidget()
        component_layout = QVBoxLayout(component_page)
        component_layout.setContentsMargins(5, 12, 4, 4)
        component_layout.setSpacing(9)
        heading = QLabel("COMPONENTS")
        heading.setObjectName("overline")
        component_layout.addWidget(heading)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search components…")
        self.search.textChanged.connect(self.populate_library)
        component_layout.addWidget(self.search)
        self.library = ComponentTree(self)
        self.library.setHeaderHidden(True)
        self.library.setIndentation(13)
        self.library.setIconSize(QSize(22, 22))
        self.library.setDragEnabled(True)
        self.library.setDragDropMode(QTreeWidget.DragOnly)
        self.library.itemDoubleClicked.connect(self.choose_component)
        component_layout.addWidget(self.library)
        hint = QLabel("Drag onto the canvas. Select a component to configure it in Inspector. Drag empty space to pan; click pins to wire.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        component_layout.addWidget(hint)
        self.sidebar_tabs.addTab(component_page, "Components")
        project_page = QWidget()
        project_layout = QVBoxLayout(project_page)
        project_layout.setContentsMargins(5, 12, 4, 4)
        project_layout.addWidget(QLabel("FIND IN CIRCUIT"))
        self.project_search = QLineEdit()
        self.project_search.setPlaceholderText("Component, label or pin…")
        self.project_search.textChanged.connect(self.update_project_search)
        self.project_search.returnPressed.connect(self.focus_first_project_result)
        project_layout.addWidget(self.project_search)
        self.project_results = QTreeWidget()
        self.project_results.setHeaderHidden(True)
        self.project_results.itemActivated.connect(self.focus_project_result)
        self.project_results.itemDoubleClicked.connect(self.focus_project_result)
        project_layout.addWidget(self.project_results, 1)
        self.project_search_hint = QLabel("Search components and connected signals in this project.")
        self.project_search_hint.setWordWrap(True)
        project_layout.addWidget(self.project_search_hint)
        self.sidebar_tabs.addTab(project_page, "Project")
        tools_page = QWidget()
        tools_layout = QVBoxLayout(tools_page)
        tools_layout.setContentsMargins(6, 15, 7, 7)
        tools_layout.setSpacing(8)
        tools_heading = QLabel("CANVAS TOOLS")
        tools_heading.setObjectName("overline")
        tools_layout.addWidget(tools_heading)
        for name, title, description in (
                ("flip", "Flip Probe", "Hold on a pin to invert 0 ↔ 1. Release to restore."),
                ("erase", "Eraser", "Click a component or wire to remove it."),
                ("cut", "Wire Cutters", "Click one wire to disconnect it.")):
            button = QPushButton(title)
            button.setObjectName("toolCard")
            button.setCheckable(True)
            button.setIcon(QIcon(tool_pixmap(name, 36)))
            button.setIconSize(QSize(34, 34))
            button.setMinimumHeight(49)
            button.clicked.connect(lambda checked, tool=name: self.set_tool(tool if checked else None))
            self.tool_buttons[name] = button
            tools_layout.addWidget(button)
            detail = QLabel(description)
            detail.setObjectName("hint")
            detail.setWordWrap(True)
            tools_layout.addWidget(detail)
            tools_layout.addSpacing(11)
        tools_layout.addStretch()
        tools_hint = QLabel("Middle mouse or Space + drag pans. Esc returns to the normal cursor.")
        tools_hint.setObjectName("hint")
        tools_hint.setWordWrap(True)
        tools_layout.addWidget(tools_hint)
        self.sidebar_tabs.addTab(tools_page, "Tools")
        content.addWidget(sidebar)

        self.scene = CircuitScene(self)
        self.canvas = Canvas(self)
        content.addWidget(self.canvas)

        inspector = QFrame()
        inspector.setObjectName("inspector")
        inspector.setMinimumWidth(210)
        inspect_layout = QVBoxLayout(inspector)
        self.inspector_frame = inspector
        self.inspector_layout = inspect_layout
        inspect_layout.setContentsMargins(16, 19, 16, 16)
        inspect_layout.setSpacing(10)
        title = QLabel("INSPECTOR")
        title.setObjectName("overline")
        inspect_layout.addWidget(title)
        self.inspect_name = QLabel("Nothing selected")
        self.inspect_name.setObjectName("inspectName")
        self.inspect_name.setWordWrap(True)
        inspect_layout.addWidget(self.inspect_name)
        self.inspect_detail = QLabel("Select a component to view its pins and settings.")
        self.inspect_detail.setWordWrap(True)
        self.inspect_detail.setObjectName("hint")
        inspect_layout.addWidget(self.inspect_detail)
        self.inspect_trace_button = QPushButton("Trace selected signal")
        self.inspect_trace_button.clicked.connect(self.trace_selected)
        self.inspect_trace_button.setEnabled(False)
        inspect_layout.addWidget(self.inspect_trace_button)
        self.inspect_hdl_button = QPushButton("Show HDL source")
        self.inspect_hdl_button.clicked.connect(self.show_selected_hdl_source)
        self.inspect_hdl_button.hide()
        inspect_layout.addWidget(self.inspect_hdl_button)
        self.inspector_component_id = None
        self.settings_form = None
        self.config_panel = QWidget()
        config_layout = QVBoxLayout(self.config_panel)
        config_layout.setContentsMargins(0, 7, 0, 0)
        config_layout.setSpacing(8)
        config_heading = QLabel("CONFIGURATION")
        config_heading.setObjectName("overline")
        config_layout.addWidget(config_heading)
        self.config_scroll = QScrollArea()
        self.config_scroll.setWidgetResizable(True)
        self.config_scroll.setFrameShape(QFrame.NoFrame)
        self.config_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        config_layout.addWidget(self.config_scroll, 1)
        self.apply_settings_button = QPushButton("Apply changes")
        self.apply_settings_button.setObjectName("primary")
        self.apply_settings_button.clicked.connect(self.apply_component_settings)
        config_layout.addWidget(self.apply_settings_button)
        self.config_error = QLabel("")
        self.config_error.setObjectName("error")
        self.config_error.setWordWrap(True)
        self.config_error.hide()
        config_layout.addWidget(self.config_error)
        inspect_layout.addWidget(self.config_panel, 1)
        self.config_panel.hide()
        inspect_layout.addStretch(0)
        self.tick_label = QLabel("TICK  0")
        self.tick_label.setObjectName("overline")
        inspect_layout.addWidget(self.tick_label)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName("error")
        inspect_layout.addWidget(self.error_label)
        content.addWidget(inspector)
        content.setSizes([240, 1000, 225])
        self.workspace_splitter = QSplitter(Qt.Vertical)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.addWidget(content)
        self.timing_panel = TimingPanel(self, self.timing_history)
        self.workspace_splitter.addWidget(self.timing_panel)
        self.timing_panel.hide()
        vertical.addWidget(self.workspace_splitter, 1)
        self.trace_dock = QDockWidget("Signal Tracing", self)
        self.trace_dock.setObjectName("signalTracingDock")
        self.trace_dock.setMinimumWidth(320)
        self.trace_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.trace_panel = SignalTracingPanel(self, self.trace_dock)
        self.trace_dock.setWidget(self.trace_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.trace_dock)
        self.trace_dock.hide()
        self.trace_dock.visibilityChanged.connect(self._trace_visibility_changed)
        self.timing_panel.view.cursorChanged.connect(self.trace_panel.on_timing_cursor)
        self.timing_panel.view.cursorChanged.connect(self._timing_cursor_time_travel)
        self.time_dock = QDockWidget("Time Travel Debugger", self)
        self.time_dock.setObjectName("timeTravelDock")
        self.time_dock.setMinimumWidth(345)
        self.time_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.time_panel = TimeTravelPanel(self, self.time_dock)
        self.time_dock.setWidget(self.time_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.time_dock)
        self.time_dock.hide()
        self.analyzer_dock = QDockWidget("Logic Analyzer", self)
        self.analyzer_dock.setObjectName("logicAnalyzerDock")
        self.analyzer_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.analyzer_dock.setMinimumWidth(380)
        self.analyzer_panel = LogicAnalyzerPanel(self, self.analyzer_dock)
        self.analyzer_dock.setWidget(self.analyzer_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.analyzer_dock)
        self.analyzer_dock.hide()
        self.debug_dock = QDockWidget("Advanced Debugger", self)
        self.debug_dock.setObjectName("advancedDebuggerDock")
        self.debug_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.debug_dock.setMinimumWidth(340)
        self.debug_panel = AdvancedDebuggerPanel(self, self.debug_dock)
        self.debug_dock.setWidget(self.debug_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.debug_dock)
        self.debug_dock.hide()
        self.cpu_dock = QDockWidget("CPU / Assembly", self)
        self.cpu_dock.setObjectName("cpuAssemblyDock")
        self.cpu_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.cpu_dock.setMinimumWidth(460)
        self.cpu_panel = CpuAssemblyPanel(self, self.cpu_dock)
        self.cpu_dock.setWidget(self.cpu_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.cpu_dock)
        self.cpu_dock.hide()
        self.hdl_dock = QDockWidget("HDL / Verilog", self)
        self.hdl_dock.setObjectName("hdlVerilogDock")
        self.hdl_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.hdl_dock.setMinimumWidth(470)
        self.hdl_panel = HDLPanel(self, self.hdl_dock)
        self.hdl_dock.setWidget(self.hdl_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.hdl_dock)
        self.hdl_dock.hide()
        self.memory_dock = QDockWidget("Memory Inspector", self)
        self.memory_dock.setObjectName("memoryInspectorDock")
        self.memory_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.memory_dock.setMinimumWidth(340)
        self.memory_panel = MemoryInspector(self, self.memory_dock)
        self.memory_dock.setWidget(self.memory_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.memory_dock)
        self.memory_dock.hide()
        self.fpga_dock = QDockWidget("FPGA Workflow", self)
        self.fpga_dock.setObjectName("fpgaWorkflowDock")
        self.fpga_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.fpga_dock.setMinimumWidth(440)
        self.fpga_panel = FPGAWorkflowPanel(self, self.fpga_dock)
        self.fpga_dock.setWidget(self.fpga_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.fpga_dock)
        self.fpga_dock.hide()
        self.experience_dock = QDockWidget("Start & Learn", self)
        self.experience_dock.setObjectName("startLearnDock")
        self.experience_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.experience_dock.setMinimumWidth(420)
        self.experience_panel = ExperiencePanel(self, self.experience_dock)
        self.experience_dock.setWidget(self.experience_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.experience_dock)
        self.experience_dock.hide()
        self.status = QLabel("Ready · Drag a component from the library onto the canvas")
        self.status.setObjectName("status")
        self.status.setFixedHeight(32)
        vertical.addWidget(self.status)
        self.populate_library()

    def _build_actions(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        edit_menu = menu.addMenu("Edit")
        circuit_menu = menu.addMenu("Circuit")
        library_menu = menu.addMenu("Component Library")
        project_menu = menu.addMenu("Projects")
        view_menu = menu.addMenu("View")
        settings_menu = menu.addMenu("Settings")
        help_menu = menu.addMenu("Help")
        def action(target, title, shortcut, callback):
            a = QAction(title, self)
            if shortcut: a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(callback)
            target.addAction(a)
            self.addAction(a)
        action(file_menu, "New", "Ctrl+N", self.new_file)
        action(file_menu, "Open…", "Ctrl+O", self.open_file)
        action(file_menu, "Save", "Ctrl+S", self.save)
        action(file_menu, "Save As…", "Ctrl+Shift+S", self.save_as)
        file_menu.addSeparator()
        action(file_menu, "Import into workspace…", None, self.import_file)
        action(file_menu, "Import as reusable block…", None, self.import_block)
        action(file_menu, "Export selected…", None, self.export_selected)
        file_menu.addSeparator()
        action(file_menu, "Import project ZIP…", None, lambda: self.show_experience("package"))
        action(file_menu, "Export project ZIP…", None, lambda: self.show_experience("package"))
        action(edit_menu, "Undo", "Ctrl+Z", self.undo)
        action(edit_menu, "Redo", "Ctrl+Shift+Z", self.redo)
        edit_menu.addSeparator()
        action(edit_menu, "Copy", "Ctrl+C", self.copy)
        action(edit_menu, "Paste", "Ctrl+V", self.paste)
        action(edit_menu, "Duplicate", "Ctrl+D", self.duplicate)
        action(edit_menu, "Delete", "Delete", self.delete_selected)
        action(edit_menu, "Find in circuit…", "Ctrl+F", self.focus_project_search)
        action(circuit_menu, "Save selection as block…", None, self.save_selection_block)
        action(circuit_menu, "New Custom Block…", "Ctrl+Shift+B", self.new_block_designer)
        action(circuit_menu, "Design selection as block…", None, self.design_selection_as_block)
        action(library_menu, "Create New Component…", None, self.new_block_designer)
        action(library_menu, "Manage Library…", None, self.open_library_manager)
        action(project_menu, "Welcome…", None, lambda: self.show_experience("welcome"))
        action(project_menu, "New from Template…", "Ctrl+Shift+N", lambda: self.show_experience("templates"))
        action(project_menu, "Tutorials…", None, lambda: self.show_experience("tutorials"))
        action(project_menu, "HDL Tutorials…", None, lambda: self.show_experience("hdl"))
        action(project_menu, "Circuit Benchmark…", None, lambda: self.show_experience("benchmark"))
        action(project_menu, "Project Gallery…", None, lambda: self.show_experience("gallery"))
        action(view_menu, "Component Library…", "Ctrl+Shift+L", self.open_library_manager)
        action(view_menu, "Signal Tracing…", "Ctrl+Shift+T", self.show_tracing)
        action(view_menu, "Time Travel Debugger…", "Ctrl+Shift+H", self.show_time_debugger)
        action(view_menu, "Logic Analyzer…", "Ctrl+Shift+A", self.show_logic_analyzer)
        action(view_menu, "Advanced Debugger…", "Ctrl+Shift+D", self.show_advanced_debugger)
        action(view_menu, "CPU / Assembly…", "Ctrl+Shift+P", self.show_cpu_assembly)
        action(view_menu, "HDL / Verilog…", "Ctrl+Shift+V", self.show_hdl)
        action(view_menu, "Memory Inspector…", "Ctrl+Shift+M", self.show_memory_inspector)
        action(view_menu, "FPGA Workflow…", "Ctrl+Shift+F", self.show_fpga_workflow)
        action(view_menu, "Testbench Manager…", "Ctrl+Shift+E", self.open_testbench_manager)
        action(settings_menu, "Check for Updates…", None, lambda: self.updates.manual_check())
        action(settings_menu, "Update Settings…", None, lambda: self.updates.show_settings())
        action(help_menu, "Quick guide…", "F1", self.show_quick_guide)
        action(help_menu, "About LogicSpace…", None, self.show_about)
        action(circuit_menu, "Step", "F6", self.step)
        action(circuit_menu, "Run / Pause", "F5", self.toggle_run)
        action(circuit_menu, "Reset", "F7", self.reset)
        self.timing_action = QAction("Timing Diagram", self)
        self.timing_action.setCheckable(True)
        self.timing_action.setShortcut(QKeySequence("Ctrl+T"))
        self.timing_action.toggled.connect(self.show_timing)
        view_menu.addAction(self.timing_action)
        self.addAction(self.timing_action)
        exit_tool = QAction("Leave canvas tool", self)
        exit_tool.setShortcut(QKeySequence("Esc"))
        exit_tool.triggered.connect(lambda: self.set_tool(None))
        self.addAction(exit_tool)

    def show_timing(self, visible=True):
        if self.timing_action.isChecked() != visible:
            self.timing_action.setChecked(visible)
        self.timing_panel.setVisible(visible)
        if visible:
            self.workspace_splitter.setSizes([max(300, self.height() - 380), 340])
            self.timing_panel.view.update_ranges(follow=True)
            self.timing_panel.update_cursor_label()

    def show_quick_guide(self):
        guide = QDialog(self)
        guide.setWindowTitle("LogicSpace guide")
        guide.resize(780, 600)
        layout = QVBoxLayout(guide)
        document = QTextEdit()
        document.setReadOnly(True)
        try:
            document.setMarkdown((Path(__file__).resolve().parent / "README.md").read_text(encoding="utf-8"))
        except OSError as error:
            document.setPlainText(f"Guide unavailable: {error}")
        layout.addWidget(document)
        close = QPushButton("Close")
        close.clicked.connect(guide.accept)
        layout.addWidget(close)
        guide.exec()

    def show_about(self):
        QMessageBox.about(self, "About LogicSpace",
                          f"LogicSpace {APP_VERSION} · digital circuit editor and logical simulator\n"
                          "Python / PySide6 · local projects and optional external HDL tools\n\n"
                          "Simulation steps are logical events, not measured hardware time.\n"
                          "Open Help → Quick guide for supported HDL and workflow limits.")

    def show_hdl(self):
        self.hdl_dock.show()
        self.hdl_dock.raise_()

    def show_memory_inspector(self):
        self.memory_panel.refresh()
        self.memory_dock.show()
        self.memory_dock.raise_()

    def show_fpga_workflow(self):
        self.experience_dock.hide()
        self.fpga_panel.sync_circuit()
        self.fpga_dock.show()
        self.fpga_dock.raise_()

    def add_timing_signal(self, ref):
        self.timing_panel.add_refs([ref])

    def show_tracing(self):
        self.trace_dock.show()
        self.trace_dock.raise_()
        if self.trace_panel.ref is None:
            self.trace_selected()
        self.trace_panel.refresh()

    def show_time_debugger(self):
        self.time_dock.show()
        self.time_dock.raise_()
        self.time_panel.refresh_panel()

    def show_logic_analyzer(self):
        self.analyzer_panel.sync_tracks()
        self.analyzer_dock.show()
        self.analyzer_dock.raise_()

    def show_advanced_debugger(self):
        self.debug_panel.update_sequential()
        self.debug_dock.show()
        self.debug_dock.raise_()

    def show_cpu_assembly(self):
        self.experience_dock.hide()
        self.cpu_panel.sync_circuit()
        self.cpu_panel.refresh_state(force=True)
        self.cpu_dock.show()
        self.cpu_dock.raise_()

    def show_experience(self, tab="welcome"):
        self.experience_panel.show_tab(tab)
        self.experience_dock.show()
        self.experience_dock.raise_()

    def _sync_time_branch(self):
        frames = [self.time_history.snapshots[uid].frame
                  for uid in self.time_history.branch.states.values()
                  if uid in self.time_history.snapshots]
        self.timing_history.replace_from_frames(frames, self.circuit)
        self.trace_history.frames = deque(frames[-self.trace_history.limit:])
        self.timing_panel.view.update_ranges()
        self.timing_panel.update_cursor_label()
        self.analyzer_panel.clear_analysis_markers()
        self.analyzer_panel.sync_tracks()

    def _timing_cursor_time_travel(self):
        if self._syncing_time_cursor or self.timing_panel.view.cursor_step is None:
            return
        view = self.timing_panel.view
        if view.follow_latest or view.cursor_step is None:
            return
        step = view.cursor_step
        if self.time_history.current and self.time_history.current.step == step:
            return
        if step not in self.time_history.branch.states:
            self.time_panel.difference_status.setText(f"Step {step} is outside retained simulation history")
            return
        try:
            self.navigate_time(step)
        except ValueError as error:
            self.time_panel.difference_status.setText(str(error))

    def _analyzer_cursor_time_travel(self):
        if not hasattr(self, "analyzer_panel") or self._syncing_time_cursor or self.analyzer_panel.view.follow_latest:
            return
        step = self.analyzer_panel.view.cursor_step
        if step is None or self.time_history.current and self.time_history.current.step == step:
            return
        if step not in self.time_history.branch.states:
            self.analyzer_panel.cursor.setText(f"Step {step} is outside retained debugger history")
            return
        try:
            self.navigate_time(step)
        except ValueError as error:
            self.analyzer_panel.cursor.setText(str(error))

    def navigate_time(self, step, branch_id=None):
        selected_branch = branch_id or self.time_history.active_branch
        if self.time_history.snapshot_at(selected_branch, step) is None:
            raise ValueError(f"Simulation step {step} is unavailable in this branch")
        self.timer.stop()
        self.run_button.setText("▶ Run")
        self.canvas.cancel_tool_hold()
        previous_branch = self.time_history.active_branch
        snapshot = self.time_history.navigate(self.sim, step, branch_id)
        sync_active_from_clocks(self.circuit)
        self.cpu_panel.sync_circuit()
        self.breakpoints.arm(self.sim)
        self.cpu_breakpoints.arm(self.circuit)
        retained = self.time_history.available_steps()
        first_visible = retained[max(0, len(retained) - self.timing_history.limit)]
        needs_waveform_sync = (self.timing_history.tracks and
                               (self.timing_history.first_step != first_visible or
                                self.timing_history.last_step != retained[-1] or
                                any(track.start_step > first_visible
                                    for track in self.timing_history.tracks.values())))
        if previous_branch != self.time_history.active_branch or needs_waveform_sync:
            self._sync_time_branch()
        self._trace_refresh_suppressed = True
        self.refresh()
        self._syncing_time_cursor = True
        view = self.timing_panel.view
        view.follow_latest = False
        view.cursor_step = step
        view.update_ranges()
        self.timing_panel.update_cursor_label()
        analyzer_view = self.analyzer_panel.view
        analyzer_view.follow_latest = False
        analyzer_view.cursor_step = step
        analyzer_view.update_ranges()
        self.analyzer_panel.follow.setChecked(False)
        self.analyzer_panel.update_cursor()
        self._syncing_time_cursor = False
        self._trace_refresh_suppressed = False
        if self.trace_dock.isVisible():
            self.trace_panel.refresh()
        self.time_panel.refresh_panel()
        if self.cpu_dock.isVisible(): self.cpu_panel.refresh_state(force=True)
        self.set_status(f"Viewing {self.time_history.branch.name} · simulation step {step}")
        return snapshot

    def trace_signal(self, ref, tab=0):
        self.trace_dock.show()
        self.trace_dock.raise_()
        self.trace_panel.select_signal(ref, tab)

    def trace_selected(self):
        wires = self.selected_wires()
        if wires:
            self.trace_signal(SignalRef.wire(wires[0]))
            return
        components = self.selected_components()
        if components:
            cid = components[0]
            inputs, outputs = pins(self.circuit.components[cid], self.circuit.blocks)
            if outputs or inputs:
                self.trace_signal(SignalRef.component_pin(cid, (outputs or inputs)[0],
                                                          "output" if outputs else "input"))

    def _trace_visibility_changed(self, visible):
        self.inspector_frame.setVisible(not visible)
        if not visible:
            self.clear_trace_highlight()
        elif self.trace_panel.ref is not None:
            self.trace_panel.refresh()

    def set_trace_highlight(self, components, wires, active_components=(), active_wires=()):
        self.trace_components = set(components)
        self.trace_wires = set(wires)
        self.trace_active_components = set(active_components)
        self.trace_active_wires = set(active_wires)
        for item in self.component_items.values(): item.update()
        for item in self.wire_items.values(): item.update_path()

    def clear_trace_highlight(self):
        self.set_trace_highlight((), ())

    def focus_trace_ref(self, ref):
        if not ref.valid(self.circuit): return
        item = self.wire_items.get(ref.wire_id) if ref.kind in ("wire", "wire_bit") else self.component_items.get(ref.component_id)
        if item is None: return
        self.scene.clearSelection()
        item.setSelected(True)
        self.canvas.centerOn(item)

    def show_selected_hdl_source(self):
        selected = self.selected_components()
        if len(selected) == 1:
            self.hdl_panel.open_source_for_component(self.circuit.components[selected[0]])

    def focus_project_search(self):
        self.sidebar_tabs.setCurrentIndex(1)
        self.project_search.setFocus()
        self.project_search.selectAll()

    def update_project_search(self):
        if not hasattr(self, "project_results"):
            return
        query = self.project_search.text().strip().lower()
        self.project_results.clear()
        if not query:
            self.project_search_hint.setText("Search components and connected signals in this project.")
            return
        count = 0
        for component in self.circuit.components.values():
            label = str(component.params.get("label", ""))
            interface = pins(component, self.circuit.blocks)
            haystack = " ".join((component.kind, label, *interface[0], *interface[1])).lower()
            if query not in haystack: continue
            item = QTreeWidgetItem([f"{label or nice_name(component.kind)} · {component.kind}"])
            item.setData(0, Qt.UserRole, ("component", component.id))
            self.project_results.addTopLevelItem(item)
            count += 1
            if count >= 300: break
        if count < 300:
            for wire in self.circuit.wires.values():
                source = self.circuit.components.get(wire.source)
                target = self.circuit.components.get(wire.target)
                if source is None or target is None: continue
                text = (f"{source.params.get('label') or source.kind}.{wire.source_pin} → "
                        f"{target.params.get('label') or target.kind}.{wire.target_pin}")
                if query not in text.lower(): continue
                item = QTreeWidgetItem([text])
                item.setData(0, Qt.UserRole, ("wire", wire.id))
                self.project_results.addTopLevelItem(item)
                count += 1
                if count >= 300: break
        self.project_search_hint.setText(f"{count} match(es)" + (" · showing first 300" if count >= 300 else ""))

    def focus_first_project_result(self):
        item = self.project_results.topLevelItem(0)
        if item is not None:
            self.focus_project_result(item)

    def focus_project_result(self, item, column=0):
        kind, identifier = item.data(0, Qt.UserRole)
        graphic = (self.component_items if kind == "component" else self.wire_items).get(identifier)
        if graphic is None: return
        self.scene.clearSelection()
        graphic.setSelected(True)
        self.canvas.centerOn(graphic)

    def open_library_manager(self):
        dialog = LibraryManager(self, self.global_library)
        dialog.exec()
        self.populate_library()

    def open_testbench_manager(self, run_all=False):
        from testbench_view import TestbenchManager
        existing = getattr(self, "testbench_manager", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            if run_all:
                QTimer.singleShot(0, existing.run_all)
            return
        dialog = TestbenchManager(self)
        self.testbench_manager = dialog
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        if run_all:
            QTimer.singleShot(0, dialog.run_all)
        dialog.show()

    def _show_designer(self, **kwargs):
        from block_designer import BlockDesigner
        try:
            designer = BlockDesigner(self, **kwargs)
            self.designer_windows.append(designer)
            designer.show()
            return designer
        except (ValueError, TypeError, KeyError) as error:
            QMessageBox.warning(self, "Cannot open Block Designer", str(error))
            return None

    def new_block_designer(self):
        return self._show_designer()

    def design_selection_as_block(self):
        ids = self.selected_components()
        if not ids:
            self.set_status("Select components, including INPUT and OUTPUT terminals")
            return None
        return self._show_designer(circuit=self._selection_circuit(ids))

    def open_block_designer(self, component_id):
        component = self.circuit.components.get(component_id)
        if not component or not component.kind.startswith("BLOCK:"):
            return None
        name = component.kind[6:]
        return self._show_designer(definition=self.circuit.blocks[name], name=name)

    def open_library_designer(self, library_id):
        return self._show_designer(entry=self.global_library.get(library_id))

    def set_tool(self, tool):
        if tool not in (None, "flip", "erase", "cut"):
            raise ValueError("Unknown canvas tool")
        self.active_tool = tool
        self.pending_kind = None
        self.cancel_wire()
        for name, button in self.tool_buttons.items():
            button.setChecked(name == tool)
        self.canvas.set_active_tool(tool)
        guidance = {None: "Ready", "flip": "Flip Probe · hold on a 0 or 1 pin",
                    "erase": "Eraser · click a component or wire",
                    "cut": "Wire Cutters · click one wire"}
        self.set_status(guidance[tool])

    def erase_tool_target(self, target, wires_only=False):
        if isinstance(target, WireItem):
            wid = target.wire.id
            if wid not in self.circuit.wires:
                return
            self.push_history()
            self.circuit.wires.pop(wid)
            self.render()
            self.set_status("Wire cut" if wires_only else "Wire erased")
        elif isinstance(target, ComponentItem) and not wires_only:
            cid = target.component.id
            if cid not in self.circuit.components:
                return
            self.push_history()
            self.circuit.remove(cid)
            self.render()
            self.set_status("Component erased")
        else:
            self.set_status("Point at a wire" if wires_only else "Point at a component or wire")

    def set_status(self, text):
        self.status.setText(text)

    def populate_library(self):
        query = self.search.text().lower().strip()
        self.library.clear()
        grouped = {}
        for kind, spec in CATALOG.items():
            if query and query not in kind.lower() and query not in spec[0].lower(): continue
            grouped.setdefault(spec[0], []).append(kind)
        if not query or query in "alu cpu":
            grouped.setdefault("CPU", []).insert(0, "ALU")
        for name in sorted(self.circuit.blocks):
            if not query or query in name.lower():
                grouped.setdefault("Custom Blocks", []).append("BLOCK:" + name)
        global_entries = {"LIB:" + entry["id"]: entry for entry in self.global_library.list_entries()}
        for kind, entry in global_entries.items():
            if not query or query in (entry["name"] + " " + entry["category"] + " " + entry["description"]).lower():
                grouped.setdefault("Library · " + entry["category"], []).append(kind)
                if entry["favorite"]:
                    grouped.setdefault("★ Favorites", []).append(kind)
        categories = sorted(grouped, key=lambda category: (0 if category == "★ Favorites" else
                                                           1 if category.startswith("Library · ") else
                                                           2 if category == "Custom Blocks" else 3, category))
        for category in categories:
            kinds = grouped[category]
            parent = QTreeWidgetItem([category])
            parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
            self.library.addTopLevelItem(parent)
            for kind in kinds:
                entry = global_entries.get(kind)
                item = QTreeWidgetItem([entry["name"] if entry else nice_name(kind)])
                item.setData(0, Qt.UserRole, kind)
                item.setIcon(0, component_icon("BLOCK:" + entry["name"] if entry else kind))
                item.setToolTip(0, (f"{entry['description']} · v{entry['version']} · Drag onto canvas" if entry else
                                    "Drag onto canvas · select to configure bit width in Inspector" if kind in BIT_WIDTH_KINDS else "Drag onto canvas"))
                if kind in ANALOG: item.setForeground(0, QBrush(UNKNOWN))
                parent.addChild(item)
            parent.setExpanded(True)

    def choose_component(self, item):
        kind = item.data(0, Qt.UserRole)
        if kind:
            self.set_tool(None)
            self.pending_kind = kind
            self.set_status(f"Click canvas to place {item.text(0)} · Esc to cancel")

    def selected_components(self):
        return [i.component.id for i in self.scene.selectedItems() if isinstance(i, ComponentItem)]

    def selected_wires(self):
        return [i.wire.id for i in self.scene.selectedItems() if isinstance(i, WireItem)]

    def selection_changed(self):
        for wire_item in getattr(self, "wire_items", {}).values():
            for handle in wire_item.handles:
                handle.setVisible(wire_item.isSelected())
        selected = self.selected_components()
        if hasattr(self, "inspect_trace_button"):
            self.inspect_trace_button.setEnabled(bool(selected or self.selected_wires()))
        selected_id = selected[0] if len(selected) == 1 else None
        if hasattr(self, "inspect_hdl_button"):
            component = self.circuit.components.get(selected_id)
            reference = component.params.get("_hdl_source_ref") if component else None
            self.inspect_hdl_button.setVisible(bool(reference and reference in (self.circuit.hdl_sources or {})))
        if selected_id != self.inspector_component_id:
            self.inspector_component_id = selected_id
            self.config_error.hide()
            if selected_id:
                self.settings_form = ComponentSettingsForm(self.circuit.components[selected_id])
                self.config_scroll.setWidget(self.settings_form)
                self.apply_settings_button.setVisible(self.settings_form.has_settings)
                self.config_panel.show()
            else:
                self.config_panel.hide()
                self.settings_form = None
        if len(selected) == 1:
            c = self.circuit.components[selected[0]]
            ins, outs = pins(c, self.circuit.blocks)
            self.inspect_name.setText(nice_name(c.kind))
            input_values = self.sim.inputs.get(c.id, {})
            output_values = {p: self.sim.outputs.get((c.id, p)) for p in outs}
            def fmt(v): return "X" if v is None else str(v)
            lines = [f"Inputs  {', '.join(f'{p}:{fmt(input_values.get(p))}' for p in ins) or '—'}",
                     f"Outputs  {', '.join(f'{p}:{fmt(output_values[p])}' for p in outs) or '—'}"]
            for direction, ports in bus_ports(c, self.circuit.blocks).items():
                for port, names in ports.items():
                    values = [input_values.get(pin) if direction == "input" else output_values.get(pin)
                              for pin in names]
                    lines.append(f"Bus {port}[{len(names) - 1}:0]  {format_bus(values, 'binary')}"
                                 + (f" · {format_bus(values, 'hex')}" if None not in values else ""))
            if c.kind in BIT_WIDTH_KINDS:
                lines.insert(0, f"Bit width  {bit_width(c)}")
            elif c.kind in ("RAM", "ROM", "SRAM", "DRAM", "EEPROM", "Flash Memory"):
                lines.insert(0, f"Address  {c.params.get('address_bits', 4)} bits · Data  {c.params.get('data_bits', 4)} bits")
            elif c.kind == "Register File":
                lines.insert(0, f"{c.params.get('registers', 8)} registers · {c.params.get('data_bits', 8)} data bits · {c.params.get('read_ports', 2)} read port(s)")
            elif c.kind == "Address Decoder":
                lines.insert(0, f"Address  {c.params.get('address_bits', 3)} bits · {c.params.get('outputs', 8)} selects")
            elif c.kind == "Control Unit":
                lines.insert(0, f"Opcode  {c.params.get('opcode_bits', 4)} bits · microcode table")
            elif c.kind not in ANALOG:
                lines.insert(0, "Pin width  1 bit (fixed)")
            if c.kind in ANALOG: lines.append("Visual placeholder · no electrical behavior")
            self.inspect_detail.setText("\n".join(lines))
        elif selected:
            self.inspect_name.setText(f"{len(selected)} components selected")
            self.inspect_detail.setText("Move, copy, duplicate, delete, or save as a reusable block.")
        elif self.selected_wires():
            wires = self.selected_wires()
            if len(wires) == 1:
                wire = self.circuit.wires[wires[0]]
                source = self.circuit.components[wire.source]
                target = self.circuit.components[wire.target]
                value = SignalRef.wire(wire.id).value(self.sim)
                self.inspect_name.setText(f"{wire.width}-bit Bus" if isinstance(wire, BusWire) else "Wire")
                self.inspect_detail.setText(
                    f"{nice_name(source.kind)}.{wire.source_pin} → {nice_name(target.kind)}.{wire.target_pin}\n"
                    f"Signal  {format_bus(value) if isinstance(value, tuple) else ('X' if value is None else value)}"
                    + (f" · {format_bus(value, 'hex')}" if isinstance(value, tuple) and None not in value else ""))
            else:
                self.inspect_name.setText(f"{len(wires)} wires selected")
                self.inspect_detail.setText("Trace or delete the selected wires.")
        else:
            self.inspect_name.setText("Nothing selected")
            self.inspect_detail.setText("Select a component to view its pins and settings.")

    def render(self):
        self.trace_history.clear()
        self.clear_trace_highlight()
        self.canvas.cancel_tool_hold()
        self.scene.blockSignals(True)
        self.scene.clear()
        self.component_items, self.wire_items = {}, {}
        for c in self.circuit.components.values():
            item = ComponentItem(self, c)
            self.scene.addItem(item)
            self.component_items[c.id] = item
        for w in self.circuit.wires.values():
            item = WireItem(self, w)
            self.scene.addItem(item)
            self.wire_items[w.id] = item
        self.preview = QGraphicsPathItem()
        self.preview.setPen(QPen(BLUE, 2, Qt.DashLine))
        self.preview.setZValue(1)
        self.scene.addItem(self.preview)
        self.scene.blockSignals(False)
        self.update_project_search()
        self._trace_refresh_suppressed = True
        self.refresh()
        self.selection_changed()
        self.timing_panel.sync_circuit(reset=True)
        self.time_history.reset(self.sim)
        self.time_panel.reset_for_circuit()
        self.debug_panel.reset_for_circuit()
        self.analyzer_panel.clear_analysis_markers()
        self.analyzer_panel.sync_tracks()
        self.cpu_panel.sync_circuit()
        self.cpu_panel.refresh_state(force=True)
        if self.timing_history.tracks:
            self.trace_history.record(self.sim)
        self._trace_refresh_suppressed = False
        if self.trace_panel.ref is not None:
            self.trace_panel.refresh()

    def refresh(self):
        self.sim.evaluate()
        for item in self.component_items.values():
            for (direction, pin), pin_item in item.pin_items.items():
                if direction == "output":
                    value = self.sim.outputs.get((item.component.id, pin))
                    connected = any(w.source == item.component.id and any(source == pin for source, _ in wire_bit_pairs(w))
                                    for w in self.circuit.wires.values())
                    forced = (item.component.id, pin) in self.sim.forced_outputs
                else:
                    value = self.sim.inputs.get(item.component.id, {}).get(pin)
                    connected = any(w.target == item.component.id and any(target == pin for _, target in wire_bit_pairs(w))
                                    for w in self.circuit.wires.values())
                    forced = (item.component.id, pin) in self.sim.forced_inputs
                pin_item.setBrush(QBrush(signal_color(value) if connected or forced else BG))
                pin_item.setPen(QPen(TOOL_COLORS["flip"] if forced else
                                     (signal_color(value) if connected else BLUE), 3 if forced else 2))
            for (direction, port), bus_item in item.bus_pin_items.items():
                names = item.bus_ports[direction][port]
                connected = any((w.source == item.component.id and w.source_pin == port if direction == "output" else
                                 w.target == item.component.id and w.target_pin == port)
                                for w in self.circuit.wires.values() if isinstance(w, BusWire))
                values = (self.sim.outputs if direction == "output" else self.sim.inputs.get(item.component.id, {}))
                bits = [values.get((item.component.id, pin)) if direction == "output" else values.get(pin)
                        for pin in names]
                color = UNKNOWN if None in bits else (LOW if not any(bits) else
                        GREEN if all(bits) else QColor("#65d7bd"))
                bus_item.setBrush(QBrush(color if connected else BG))
                bus_item.setPen(QPen(QColor("#65d7bd") if connected else BLUE, 2.5))
            item.update()
        for item in self.wire_items.values(): item.update_path()
        self.tick_label.setText(f"TICK  {self.circuit.tick}")
        notices = self.sim.errors or self.sim.warnings
        self.error_label.setText("\n".join(notices[:4]) +
                                 (f"\n… {len(notices) - 4} more" if len(notices) > 4 else ""))
        self.selection_changed()
        if (hasattr(self, "trace_dock") and self.trace_dock.isVisible()
                and not self._trace_refresh_suppressed):
            self.trace_panel.refresh()

    def pin_position(self, cid, direction, pin):
        item = self.component_items.get(cid)
        target = (item.pin_items.get((direction, pin)) or item.bus_pin_items.get((direction, pin))) if item else None
        return target.scenePos() if target else None

    def raw_wire_points(self, wire):
        start = self.pin_position(wire.source, "output", wire.source_pin)
        end = self.pin_position(wire.target, "input", wire.target_pin)
        if start is None or end is None: return []
        waypoints = [start] + [QPointF(*p) for p in wire.bends] + [end]
        if not wire.bends and start.x() != end.x() and start.y() != end.y():
            middle_x = round((start.x() + end.x()) / 2 / 10) * 10
            return [start, QPointF(middle_x, start.y()), QPointF(middle_x, end.y()), end]
        result = [start]
        for a, b in zip(waypoints, waypoints[1:]):
            if a.x() != b.x() and a.y() != b.y(): result.append(QPointF(b.x(), a.y()))
            result.append(b)
        return result

    def update_wires_for(self, cid):
        # Crossings can change for wires that do not touch the moved component.
        for item in self.wire_items.values(): item.update_path()

    def push_history(self, snapshot=None):
        self.history.append(snapshot or json.dumps(self.circuit.to_dict()))
        if len(self.history) > 100: self.history.pop(0)
        self.future.clear()
        self.dirty = True
        self._title()

    def _title(self):
        self.setWindowTitle("LogicSpace — " + (Path(self.path).name if self.path else "Untitled") + (" •" if self.dirty else ""))

    def undo(self):
        if not self.history: return
        if not self._confirm_testbench_editor(): return
        self._close_testbench_editor()
        self.future.append(json.dumps(self.circuit.to_dict()))
        self.circuit = Circuit.from_dict(json.loads(self.history.pop()))
        self.sim = Simulator(self.circuit)
        self.render()

    def redo(self):
        if not self.future: return
        if not self._confirm_testbench_editor(): return
        self._close_testbench_editor()
        self.history.append(json.dumps(self.circuit.to_dict()))
        self.circuit = Circuit.from_dict(json.loads(self.future.pop()))
        self.sim = Simulator(self.circuit)
        self.render()

    def place_component(self, kind, point):
        x = round(point.x() / 20) * 20 if self.snap else point.x()
        y = round(point.y() / 20) * 20 if self.snap else point.y()
        if kind.startswith("LIB:"):
            try:
                entry = self.global_library.get(kind[4:])
                self.push_history()
                name = self.global_library.install_into(self.circuit, entry["id"])
                self.circuit.add("BLOCK:" + name, x, y)
                label = entry["name"]
            except (ValueError, OSError, KeyError, TypeError) as error:
                QMessageBox.warning(self, "Cannot place library component", str(error))
                return
        else:
            self.push_history()
            self.circuit.add(kind, x, y)
            label = nice_name(kind)
        self.pending_kind = None
        self.render()
        self.set_status(f"Placed {label}")

    def pin_clicked(self, pin):
        cid, direction, name = pin.owner.component.id, pin.direction, pin.name
        if self.wire_start is None:
            if direction != "output":
                self.set_status("Start a wire from an output pin")
                return
            self.wire_start = (cid, name, pin.is_bus)
            self.wire_bends = []
            self.set_status(f"Wiring from {nice_name(pin.owner.component.kind)} · click input pin, or canvas for a corner")
        elif direction == "input":
            source, source_pin, source_is_bus = self.wire_start
            try:
                if source_is_bus != pin.is_bus:
                    raise ValueError("Connect a bus port to another bus port of the same width; use a splitter for individual bits")
                snapshot = json.dumps(self.circuit.to_dict())
                if source_is_bus:
                    self.circuit.connect_bus(source, source_pin, cid, name, self.wire_bends)
                else:
                    self.circuit.connect(source, source_pin, cid, name, self.wire_bends)
                self.push_history(snapshot)
                self.cancel_wire()
                self.render()
                self.set_status("Bus connected" if source_is_bus else "Wire connected")
            except ValueError as e:
                self.set_status(str(e))
        else:
            self.wire_start = (cid, name, pin.is_bus)
            self.wire_bends = []
            self.set_status("Wiring from output")

    def start_branch(self, wire, point):
        self.wire_start = (wire.source, wire.source_pin, isinstance(wire, BusWire))
        points = self.raw_wire_points(wire)
        best, prefix = float("inf"), []
        for index, (a, b) in enumerate(zip(points, points[1:])):
            if a.x() == b.x():
                candidate = QPointF(a.x(), max(min(point.y(), max(a.y(), b.y())), min(a.y(), b.y())))
            else:
                candidate = QPointF(max(min(point.x(), max(a.x(), b.x())), min(a.x(), b.x())), a.y())
            distance = (candidate.x() - point.x()) ** 2 + (candidate.y() - point.y()) ** 2
            if distance < best:
                best = distance
                prefix = points[1:index + 1] + [candidate]
        self.wire_bends = [point_tuple(p) for p in prefix]
        self.set_status("Branch selected · click an input pin")

    def add_wire_bend(self, point):
        if self.snap: point = QPointF(round(point.x() / 20) * 20, round(point.y() / 20) * 20)
        self.wire_bends.append(point_tuple(point))
        self.update_preview(point)
        self.set_status("Corner added · click an input pin to finish · Esc to cancel")

    def update_preview(self, target):
        if not self.wire_start or not self.preview: return
        start = self.pin_position(self.wire_start[0], "output", self.wire_start[1])
        if not start: return
        path = QPainterPath(start)
        points = [start] + [QPointF(*p) for p in self.wire_bends] + [target]
        for a, b in zip(points, points[1:]):
            if a.x() != b.x() and a.y() != b.y(): path.lineTo(b.x(), a.y())
            path.lineTo(b)
        self.preview.setPath(path)

    def cancel_wire(self):
        self.wire_start = None
        self.wire_bends = []
        if self.preview: self.preview.setPath(QPainterPath())

    def toggle_input(self, cid):
        c = self.circuit.components[cid]
        self.time_panel.external = None
        self.push_history()
        mask = (1 << bit_width(c)) - 1
        c.params["value"] = 0 if c.params.get("value", 0) else mask
        self.refresh()
        self.time_history.record_mutation(self.sim)
        self._sync_time_branch()
        self.time_panel.refresh_panel()
        if self.inspector_component_id == cid:
            self.inspector_component_id = None
            self.selection_changed()

    def configure_selected(self):
        ids = self.selected_components()
        if len(ids) == 1: self.edit_component(ids[0])

    def edit_component(self, cid):
        item = self.component_items.get(cid)
        if item:
            if not item.isSelected():
                self.scene.clearSelection()
                item.setSelected(True)
            control = next(iter(self.settings_form.controls.values()), None) if self.settings_form else None
            (control or self.config_scroll).setFocus()

    def apply_component_settings(self):
        cid = self.inspector_component_id
        if not cid or cid not in self.circuit.components or self.settings_form is None:
            return
        c = self.circuit.components[cid]
        try:
            values = self.settings_form.values()
            if values == self.settings_form.initial_values:
                self.config_error.hide()
                return
            tentative = deepcopy(c)
            tentative.params.update(values)
            new_in, new_out = pins(tentative, self.circuit.blocks)
            new_bus = bus_ports(tentative, self.circuit.blocks)
            changes = []
            def mapped_pin(old_pin, valid):
                if old_pin in valid: return old_pin
                if old_pin + "0" in valid: return old_pin + "0"
                if old_pin + "_0" in valid: return old_pin + "_0"
                if old_pin.endswith("_0") and old_pin[:-2] in valid: return old_pin[:-2]
                if old_pin.endswith("0") and old_pin[:-1] in valid: return old_pin[:-1]
                return old_pin
            for w in self.circuit.wires.values():
                if isinstance(w, BusWire) and (w.source == cid or w.target == cid):
                    if (w.source == cid and tuple(w.source_bits) != new_bus["output"].get(w.source_pin) or
                            w.target == cid and tuple(w.target_bits) != new_bus["input"].get(w.target_pin)):
                        raise ValueError("This change would invalidate a connected bus; disconnect it first")
                    changes.append((w, w.source_pin, w.target_pin))
                    continue
                source_pin = mapped_pin(w.source_pin, new_out) if w.source == cid else w.source_pin
                target_pin = mapped_pin(w.target_pin, new_in) if w.target == cid else w.target_pin
                if w.source == cid and source_pin not in new_out or w.target == cid and target_pin not in new_in:
                    raise ValueError("This width would remove a pin with a connected wire")
                changes.append((w, source_pin, target_pin))
            self.push_history()
            c.params.update(values)
            for wire, source_pin, target_pin in changes:
                wire.source_pin = source_pin
                wire.target_pin = target_pin
            self.render()
            self.component_items[cid].setSelected(True)
            self.set_status(f"Updated {nice_name(c.kind)}")
        except (ValueError, TypeError) as e:
            self.config_error.setText(str(e))
            self.config_error.show()

    def delete_selected(self):
        ids, wires = self.selected_components(), self.selected_wires()
        if not ids and not wires: return
        self.push_history()
        for cid in ids: self.circuit.remove(cid)
        for wid in wires: self.circuit.wires.pop(wid, None)
        self.render()

    def copy(self):
        ids = self.selected_components()
        if not ids: return
        selected = set(ids)
        self.clipboard = {
            "components": [deepcopy(vars(self.circuit.components[cid])) for cid in ids],
            "wires": [wire_to_dict(w) for w in self.circuit.wires.values() if w.source in selected and w.target in selected],
            "blocks": deepcopy(self.circuit.blocks),
        }
        self.paste_count = 0
        self.set_status(f"Copied {len(ids)} component(s)")

    def paste(self):
        if not self.clipboard: return
        self.push_history()
        self.paste_count += 1
        offset = 40 * self.paste_count
        mapping = {}
        for name, definition in self.clipboard["blocks"].items():
            self.circuit.blocks.setdefault(name, definition)
        for data in self.clipboard["components"]:
            c = Component(**deepcopy(data))
            original = c.id
            c.id = new_id()
            c.x += offset
            c.y += offset
            mapping[original] = c.id
            self.circuit.components[c.id] = c
        for data in self.clipboard["wires"]:
            w = wire_from_dict(data)
            w.id = new_id()
            w.source = mapping[w.source]
            w.target = mapping[w.target]
            w.bends = [[x + offset, y + offset] for x, y in w.bends]
            self.circuit.wires[w.id] = w
        self.render()
        for cid in mapping.values(): self.component_items[cid].setSelected(True)
        self.set_status(f"Pasted {len(mapping)} component(s)")

    def duplicate(self):
        ids = self.selected_components()
        if not ids: return
        self.push_history()
        created = copy_selection(self.circuit, ids)
        self.render()
        for cid in created: self.component_items[cid].setSelected(True)

    def toggle_snap(self):
        self.snap = not self.snap
        self.snap_button.setText("⌗  Snap on" if self.snap else "⌗  Snap off")

    def toggle_run(self):
        self.time_panel.pause_replay()
        self.time_panel.external = None
        if self.timer.isActive():
            self.timer.stop()
            self.run_button.setText("▶ Run")
            self.set_status("Simulation paused")
        else:
            self.timer.start(max(25, 1000 // self.speed.value()))
            self.run_button.setText("Ⅱ Pause")
            self.set_status("Simulation running")

    def step(self):
        self.time_panel.pause_replay()
        self.time_panel.external = None
        if not self.time_history.matches(self.sim):
            self.time_history.record_mutation(self.sim)
            self._sync_time_branch()
        elif self.time_history.is_historical:
            self.time_history.fork()
            self._sync_time_branch()
        self.sim.step()
        if self.debug_dock.isVisible(): self.debug_panel.update_sequential()
        self.last_break_events = self.breakpoints.check(self.sim)
        self.last_cpu_events = self.cpu_breakpoints.check(self.sim)
        self.time_history.record(self.sim)
        if self.circuit.components:
            self.dirty = True
            self._title()
        self._trace_refresh_suppressed = True
        self.refresh()
        self.timing_panel.record_step()
        if self.analyzer_dock.isVisible():
            self.analyzer_panel.on_step()
        if self.timing_history.tracks or self.trace_dock.isVisible():
            self.trace_history.record(self.sim)
        self._trace_refresh_suppressed = False
        if self.trace_dock.isVisible():
            self.trace_panel.refresh()
        cpu_halted = False
        workspace = get_active_binding(self.circuit) or {}
        controller = self.circuit.components.get(workspace.get("ids", {}).get("control"))
        if controller is not None and controller.kind == "ISA Control Unit":
            cpu_halted = controller.state.get("phase") == "HALT"
        if self.sim.errors or self.last_break_events or self.last_cpu_events or cpu_halted:
            self.timer.stop()
            self.run_button.setText("▶ Run")
        if self.last_break_events or self.last_cpu_events:
            events = self.last_break_events + self.last_cpu_events
            self.debug_panel.on_events(events)
            self.set_status(f"Breakpoint at step {self.circuit.tick}: {events[0].label}")
        elif cpu_halted and controller.state.get("fault"):
            self.set_status("CPU fault: " + controller.state["fault"])
        elif cpu_halted:
            self.set_status("CPU halted")
        self.time_panel.refresh_panel()
        if self.cpu_dock.isVisible(): self.cpu_panel.refresh_state()

    def step_clock_cycle(self, ref, max_steps=10000):
        if not ref.valid(self.circuit) or isinstance(ref.value(self.sim), tuple):
            raise ValueError("Choose a valid one-bit clock signal")
        self.timer.stop()
        self.run_button.setText("▶ Run")
        self._clock_cycle_cancelled = False
        previous = ref.value(self.sim)
        for index in range(max_steps):
            self.step()
            current = ref.value(self.sim)
            if self.last_break_events or previous == 0 and current == 1:
                return self.circuit.tick
            previous = current
            if index % 32 == 31:
                QApplication.processEvents()
                if self._clock_cycle_cancelled:
                    raise ValueError("Clock cycle stepping cancelled")
        raise ValueError(f"No rising clock edge within {max_steps} simulation steps")

    def reset(self):
        self.timer.stop()
        self.canvas.cancel_tool_hold()
        self.run_button.setText("▶ Run")
        self.sim.reset()
        self.breakpoints.arm(self.sim, clear_events=True)
        self.cpu_breakpoints.arm(self.circuit)
        self.last_cpu_events = []
        self.debug_panel.events.clear()
        self.time_history.reset(self.sim)
        self.time_panel.reset_for_circuit()
        if self.circuit.components:
            self.dirty = True
            self._title()
        self._trace_refresh_suppressed = True
        self.refresh()
        self.timing_panel.reset_history()
        self.analyzer_panel.clear_analysis_markers()
        if self.cpu_dock.isVisible(): self.cpu_panel.refresh_state(force=True)
        self._trace_refresh_suppressed = False
        if self.trace_dock.isVisible():
            self.trace_panel.refresh()
        self.set_status("Simulation reset")

    def new_file(self):
        if not self._confirm_discard(): return
        self._close_testbench_editor()
        self.timer.stop()
        self.run_button.setText("▶ Run")
        self.circuit = Circuit()
        self.sim = Simulator(self.circuit)
        self.timing_panel.sync_circuit(clear=True)
        self.path = None
        self.dirty = False
        self.history.clear()
        self.future.clear()
        self.render()
        self.populate_library()
        self.setWindowTitle("LogicSpace — Untitled")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open circuit", "", "LogicSpace circuits (*.json)")
        if not path: return
        if not self._confirm_discard(): return
        try:
            circuit = Circuit.load(path)
            self._close_testbench_editor()
            self.timer.stop()
            self.circuit, self.sim, self.path = circuit, Simulator(circuit), path
            self.timing_panel.sync_circuit(clear=True)
            self.dirty = False
            self.history.clear()
            self.future.clear()
            self.render()
            self.populate_library()
            self.setWindowTitle("LogicSpace — " + Path(path).name)
            self.set_status(f"Opened {Path(path).name}")
            self.experience_dock.hide()
        except (OSError, ValueError, TypeError, KeyError) as e:
            QMessageBox.warning(self, "Cannot open circuit", str(e))

    def save(self):
        if not self.path: return self.save_as()
        try:
            if self.time_history.is_historical:
                head = self.time_history.snapshot_at(self.time_history.active_branch,
                                                     self.time_history.latest_step)
                if head is None:
                    raise ValueError("Latest simulation state is unavailable")
                data = deepcopy(self.circuit.to_dict())
                data["tick"] = head.step
                for item in data["components"]:
                    item["state"] = deepcopy(head.states[item["id"]])
                    item["params"] = deepcopy(head.params[item["id"]])
                with open(self.path, "w", encoding="utf-8") as file:
                    json.dump(data, file, indent=2)
            else:
                self.circuit.save(self.path)
            self.dirty = False
            self._title()
            self.set_status(f"Saved {Path(self.path).name}")
            return True
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Cannot save circuit", str(e))
            return False

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save circuit", self.path or "circuit.json", "LogicSpace circuits (*.json)")
        if not path: return False
        self.path = path if path.endswith(".json") else path + ".json"
        return self.save()

    def _confirm_testbench_editor(self):
        manager = getattr(self, "testbench_manager", None)
        if manager is None or not manager.dirty:
            return True
        choice = QMessageBox.question(self, "Unsaved testbenches", "Save testbench changes to the project?",
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                      QMessageBox.Save)
        if choice == QMessageBox.Cancel:
            return False
        if choice == QMessageBox.Save:
            return bool(manager.commit())
        manager.dirty = False
        return True

    def _close_testbench_editor(self):
        manager = getattr(self, "testbench_manager", None)
        if manager is not None:
            if manager.running:
                manager.stop()
            manager.dirty = False
            manager.close()

    def _confirm_discard(self):
        if not self._confirm_testbench_editor(): return False
        if not self.dirty: return True
        choice = QMessageBox.question(self, "Unsaved circuit", "Save changes to the current circuit?",
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                      QMessageBox.Save)
        if choice == QMessageBox.Cancel: return False
        if choice == QMessageBox.Save: return bool(self.save())
        return True

    def closeEvent(self, event):
        if self._confirm_discard() and self.hdl_panel._confirm_discard():
            if hasattr(self, "updates"): self.updates.stop()
            self.experience_panel.cancel_benchmark()
            worker = self.experience_panel.worker
            if worker is not None and worker.isRunning(): worker.wait(5000)
            hdl_worker = self.hdl_panel.worker
            if hdl_worker is not None and hdl_worker.isRunning(): hdl_worker.wait(12000)
            event.accept()
        else: event.ignore()

    def _merge(self, other):
        if len(self.circuit.hdl_sources or {}) + len(other.hdl_sources or {}) > 64:
            raise ValueError("This project can retain at most 64 imported HDL source snapshots")
        self.push_history()
        source_ids = {}
        if other.hdl_sources:
            if self.circuit.hdl_sources is None:
                self.circuit.hdl_sources = {}
            for source_id, record in other.hdl_sources.items():
                replacement = new_id()
                while replacement in self.circuit.hdl_sources:
                    replacement = new_id()
                source_ids[source_id] = replacement
                self.circuit.hdl_sources[replacement] = deepcopy(record)
        for name, definition in other.blocks.items():
            if name in self.circuit.blocks and self.circuit.blocks[name] != definition:
                new_name = name + " imported"
                while new_name in self.circuit.blocks: new_name += " 2"
                for c in other.components.values():
                    if c.kind == "BLOCK:" + name: c.kind = "BLOCK:" + new_name
                name = new_name
            self.circuit.blocks[name] = deepcopy(definition)
        mapping = {}
        for c in other.components.values():
            clone = deepcopy(c)
            clone.id = new_id()
            reference = clone.params.get("_hdl_source_ref")
            if reference in source_ids:
                clone.params["_hdl_source_ref"] = source_ids[reference]
            clone.x += 80
            clone.y += 80
            mapping[c.id] = clone.id
            self.circuit.components[clone.id] = clone
        for w in other.wires.values():
            clone = deepcopy(w)
            clone.id = new_id()
            clone.source = mapping[w.source]
            clone.target = mapping[w.target]
            clone.bends = [[x + 80, y + 80] for x, y in clone.bends]
            self.circuit.wires[clone.id] = clone
        self.render()
        self.populate_library()
        for cid in mapping.values(): self.component_items[cid].setSelected(True)

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import circuit into workspace", "", "LogicSpace circuits (*.json)")
        if not path: return
        try:
            self._merge(Circuit.load(path))
            self.set_status(f"Imported {Path(path).name}")
        except (OSError, ValueError, TypeError, KeyError) as e:
            QMessageBox.warning(self, "Cannot import", str(e))

    def _selection_circuit(self, ids):
        selected = set(ids)
        sub = Circuit()
        sub.blocks = deepcopy(self.circuit.blocks)
        sub.components = {cid: deepcopy(self.circuit.components[cid]) for cid in ids}
        sub.wires = {w.id: deepcopy(w) for w in self.circuit.wires.values() if w.source in selected and w.target in selected}
        return sub

    def export_selected(self):
        ids = self.selected_components()
        if not ids:
            self.set_status("Select components to export")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export selection", "selection.json", "LogicSpace circuits (*.json)")
        if not path: return
        try:
            self._selection_circuit(ids).save(path if path.endswith(".json") else path + ".json")
            self.set_status("Selection exported")
        except OSError as e:
            QMessageBox.warning(self, "Cannot export", str(e))

    def _make_block(self, sub, name):
        if not name or name in self.circuit.blocks:
            raise ValueError("Choose a unique block name")
        definition = block_definition_from_circuit(sub)
        self.push_history()
        self.circuit.blocks[name] = definition
        self.populate_library()
        self.set_status(f"Saved reusable block {name}")

    def save_selection_block(self):
        ids = self.selected_components()
        if not ids:
            self.set_status("Select the circuit for the block, including its INPUT and OUTPUT terminals")
            return
        dialog = SaveBlockDialog(self.global_library, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        name = dialog.name.text().strip()
        try:
            sub = self._selection_circuit(ids)
            definition = block_definition_from_circuit(sub)
            if dialog.project.isChecked() and name in self.circuit.blocks:
                raise ValueError("Choose a unique project block name")
            if dialog.global_library.isChecked():
                self.global_library.save(name, definition, dialog.category.currentText(),
                                         dialog.description.toPlainText())
            if dialog.project.isChecked():
                self._make_block(sub, name)
            else:
                self.populate_library()
                self.set_status(f"Saved {name} to global library")
        except (ValueError, TypeError, KeyError, OSError) as error:
            QMessageBox.warning(self, "Cannot create block", str(error))

    def import_block(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import circuit as reusable block", "", "LogicSpace circuits (*.json)")
        if not path: return
        from PySide6.QtWidgets import QInputDialog
        try:
            sub = Circuit.load(path)
            name, ok = QInputDialog.getText(self, "Block name", "Name", text=Path(path).stem)
            if ok: self._make_block(sub, name.strip())
        except (OSError, ValueError, TypeError, KeyError) as e:
            QMessageBox.warning(self, "Cannot import block", str(e))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LogicSpace")
    app.setDesktopFileName("logicspace")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "resources" / "logicspace.png")))
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget { color: #e7edf7; background: #171d26; font: 10pt 'Inter', 'Ubuntu', sans-serif; }
        QMainWindow { background: #11151c; }
        QMenuBar { background: #171d26; padding: 3px 10px; }
        QMenuBar::item:selected, QMenu::item:selected { background: #304660; }
        QMenu { background: #202936; border: 1px solid #394657; padding: 5px; }
        QMenu::item { padding: 6px 22px; }
        #toolbar { background: #171d26; border-bottom: 1px solid #2b3543; }
        #logo { font-size: 16pt; font-weight: 700; color: #e7edf7; }
        #sidebar, #inspector { background: #171d26; }
        #sidebarTabs::pane { border: none; background: #171d26; }
        #sidebarTabs QTabBar::tab { background: #202936; color: #91a5bd; padding: 7px 4px; border: 1px solid #334255; }
        #sidebarTabs QTabBar::tab:selected { background: #304660; color: #e7edf7; border-bottom: 2px solid #6ea8fe; }
        #toolCard { text-align: left; padding: 7px 10px; }
        #toolCard:checked { background: #294a51; border: 1px solid #6ce4cf; color: #d8fff3; }
        #sidebar { border-right: 1px solid #2b3543; }
        #inspector { border-left: 1px solid #2b3543; }
        #overline { color: #8596ae; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
        #hint { color: #8292a9; font-size: 9pt; }
        #inspectName { font-size: 13pt; font-weight: 600; }
        #error { color: #e7aa60; font-size: 9pt; }
        #status { color: #8292a9; background: #171d26; border-top: 1px solid #2b3543; padding: 7px 16px; font-size: 9pt; }
        QPushButton { background: #263243; border: 1px solid #3c4d62; border-radius: 7px; padding: 7px 12px; }
        QPushButton:hover { background: #33445b; }
        QPushButton:pressed { background: #3a5270; }
        QPushButton:disabled { color: #66758a; background: #202a36; }
        #primary, #run { background: #3d6fae; border-color: #5288ca; font-weight: 600; }
        #primary:hover, #run:hover { background: #4d83c5; }
        QLineEdit, QSpinBox, QComboBox, QTextEdit { background: #202936; border: 1px solid #3b4a5e; border-radius: 7px; padding: 7px; }
        QTreeWidget { background: transparent; border: none; outline: none; }
        QTreeWidget::item { padding: 5px 3px; border-radius: 5px; }
        QTreeWidget::item:selected { background: #304660; }
        QTreeWidget::item:hover { background: #283546; }
        QSlider::groove:horizontal { background: #36475b; height: 4px; border-radius: 2px; }
        QSlider::handle:horizontal { background: #6ea8fe; width: 13px; margin: -5px 0; border-radius: 6px; }
    """)
    window = Editor()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

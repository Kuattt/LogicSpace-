"""Vector component bodies for the circuit canvas.

The electronic parts use familiar schematic silhouettes. Larger functional
blocks use their own package shapes; their pins remain at the model positions.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QBrush, QFont, QLinearGradient, QPainter, QPainterPath, QPen

from engine import CATALOG, ANALOG, DISPLAYS, LOGIC_GATES


def _gradient(top, bottom, y1, y2):
    g = QLinearGradient(0, y1, 0, y2)
    g.setColorAt(0, QColor(top))
    g.setColorAt(1, QColor(bottom))
    return QBrush(g)


def _path(painter, path, stroke, fill, width=2):
    painter.setPen(QPen(QColor(stroke), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(fill)
    painter.drawPath(path)


def _name(painter, text, rect, color="#e7edf7", size=10, bold=True):
    painter.setPen(QColor(color))
    painter.setFont(QFont("Sans Serif", size, QFont.DemiBold if bold else QFont.Normal))
    painter.drawText(rect, Qt.AlignCenter, text)


def _paint_sliced(painter, kind, width, height, selected, params, pin_positions):
    """A rack of compact bit slices instead of one vertically stretched symbol."""
    count = max(1, min(8, int(params.get("width", 1))))
    pitch = 34 if kind == "NOT" else 38
    accent = "#91c3ff" if selected else "#648bb3"
    for i in range(count):
        cy = 63 + i * pitch
        painter.setPen(QPen(QColor("#273746"), 1))
        painter.drawLine(QPointF(29, cy + pitch * .47), QPointF(width - 29, cy + pitch * .47))
        if kind in LOGIC_GATES:
            x0, x1, y0, y1 = 102, 168, cy - 14, cy + 14
            path = QPainterPath()
            if kind == "NOT":
                path.moveTo(x0, y0); path.lineTo(x0, y1)
                path.lineTo(x1 - 6, cy); path.closeSubpath()
            elif kind in ("AND", "NAND"):
                path.moveTo(x0, y0); path.lineTo(x0 + 27, y0)
                path.cubicTo(x1 + 6, y0, x1 + 6, y1, x0 + 27, y1)
                path.lineTo(x0, y1); path.closeSubpath()
            else:
                path.moveTo(x0, y0)
                path.cubicTo(x0 + 29, y0, x0 + 54, y0 + 4, x1, cy)
                path.cubicTo(x0 + 54, y1 - 4, x0 + 29, y1, x0, y1)
                path.cubicTo(x0 + 13, cy + 7, x0 + 13, cy - 7, x0, y0)
            _path(painter, path, accent, _gradient("#2b4660", "#142a3e", y0, y1), 1.8)
            if kind in ("XOR", "XNOR"):
                extra = QPainterPath(QPointF(x0 - 5, y0))
                extra.cubicTo(x0 + 7, cy - 7, x0 + 7, cy + 7, x0 - 5, y1)
                painter.setPen(QPen(QColor(accent), 1.5))
                painter.drawPath(extra)
            if kind in ("NAND", "NOR", "XNOR", "NOT"):
                painter.setPen(QPen(QColor(accent), 1.6))
                painter.setBrush(QColor("#16293a"))
                painter.drawEllipse(QPointF(173, cy), 3.5, 3.5)
            glyph = {"AND": "∧", "NAND": "∧", "OR": "≥1", "NOR": "≥1",
                     "XOR": "=1", "XNOR": "=1", "NOT": "¬"}[kind]
            _name(painter, glyph, QRectF(118, cy - 12, 31, 24), "#ddecff", 10)
        elif kind in ("Adder", "Subtractor", "Multiplier", "Divider", "ALU"):
            path = QPainterPath()
            path.moveTo(107, cy - 14); path.lineTo(154, cy - 14)
            path.lineTo(168, cy); path.lineTo(154, cy + 14)
            path.lineTo(107, cy + 14); path.lineTo(94, cy); path.closeSubpath()
            _path(painter, path, "#efb573" if not selected else "#ffdaab",
                  _gradient("#4c3523", "#241d1b", cy - 14, cy + 14), 1.7)
            glyph = {"Adder": "+", "Subtractor": "−", "Multiplier": "×",
                     "Divider": "÷", "ALU": "A"}[kind]
            _name(painter, glyph, QRectF(116, cy - 12, 31, 24), "#ffe0ac", 13)
        else:
            path = QPainterPath()
            path.moveTo(99, cy - 14); path.lineTo(151, cy - 14)
            path.lineTo(169, cy); path.lineTo(151, cy + 14)
            path.lineTo(99, cy + 14); path.closeSubpath()
            _path(painter, path, "#bba3e5" if not selected else "#d9c6ff",
                  _gradient("#3c3154", "#201c35", cy - 14, cy + 14), 1.7)
            glyph = {"Multiplexer": "2:1", "Demultiplexer": "1:2", "Comparator": "="}[kind]
            _name(painter, glyph, QRectF(111, cy - 11, 43, 22), "#eadbff", 9)
    if kind in ("Adder", "Subtractor"):
        painter.setPen(QPen(QColor("#b88750"), 1.5, Qt.DotLine))
        painter.drawLine(QPointF(182, 63), QPointF(182, 63 + (count - 1) * pitch))
    if kind in ("Multiplexer", "Demultiplexer", "ALU"):
        painter.setPen(QPen(QColor("#a495cc"), 1.5, Qt.DotLine))
        painter.drawLine(QPointF(87, 63), QPointF(87, 63 + (count - 1) * pitch))
    painter.setPen(QPen(QColor("#314c61"), 1))
    painter.drawLine(QPointF(27, 37), QPointF(width - 27, 37))


def paint_component_body(painter: QPainter, kind: str, width: float, height: float,
                         selected: bool, params: dict, pin_positions=None):
    """Paint a component without pin labels or live signal overlays."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    if pin_positions is not None:
        _paint_sliced(painter, kind, width, height, selected, params, pin_positions)
        painter.restore()
        return
    stroke = "#83b8ff" if selected else "#56718e"
    category = CATALOG.get(kind, ("Custom Blocks",))[0]
    y0, y1 = 28, height - 5
    cy = (y0 + y1) / 2

    if kind in ("AND", "NAND", "OR", "NOR", "XOR", "XNOR", "NOT"):
        left, right = 23, 136
        p = QPainterPath()
        if kind == "NOT":
            p.moveTo(left, y0 + 3)
            p.lineTo(left, y1 - 3)
            p.lineTo(right - 5, cy)
            p.closeSubpath()
        elif kind in ("AND", "NAND"):
            p.moveTo(left, y0)
            p.lineTo(76, y0)
            p.cubicTo(145, y0, 145, y1, 76, y1)
            p.lineTo(left, y1)
            p.closeSubpath()
        else:
            p.moveTo(left, y0)
            p.cubicTo(81, y0, 112, y0 + 6, right, cy)
            p.cubicTo(112, y1 - 6, 81, y1, left, y1)
            p.cubicTo(46, cy + 13, 46, cy - 13, left, y0)
        _path(painter, p, stroke, _gradient("#263f59", "#162636", y0, y1), 2.2)
        if kind in ("XOR", "XNOR"):
            painter.setPen(QPen(QColor(stroke), 2))
            extra = QPainterPath(QPointF(left - 8, y0))
            extra.cubicTo(left + 14, cy - 14, left + 14, cy + 14, left - 8, y1)
            painter.drawPath(extra)
        if kind in ("NAND", "NOR", "XNOR", "NOT"):
            painter.setBrush(QColor("#172635"))
            painter.setPen(QPen(QColor(stroke), 2))
            painter.drawEllipse(QPointF(142, cy), 5, 5)
        symbol = {"AND": "∧", "NAND": "∧", "OR": "≥1", "NOR": "≥1",
                  "XOR": "=1", "XNOR": "=1", "NOT": "1"}[kind]
        _name(painter, symbol, QRectF(52, cy - 15, 52, 30), "#d8eaff", 15)

    elif kind == "INPUT":
        width = int(params.get("width", 1))
        if width > 1:
            painter.setPen(QPen(QColor("#6485a6"), 1.7))
            painter.setBrush(_gradient("#283d50", "#142638", y0, y1))
            painter.drawRoundedRect(QRectF(34, 33, 98, height - 41), 7, 7)
            value = params.get("value", 0)
            for i in range(min(width, 8)):
                yy = 47 + 24 * i
                on = value is not None and bool(value & (1 << i))
                painter.setPen(QPen(QColor("#55728e"), 1))
                painter.setBrush(QColor("#12202d"))
                painter.drawRoundedRect(QRectF(43, yy - 8, 27, 16), 4, 4)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#63d39b") if on else QColor("#748da3"))
                painter.drawEllipse(QPointF(60 if on else 51, yy), 5, 5)
        else:
            painter.setPen(QPen(QColor("#6e8bac"), 3, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(24, cy), QPointF(38, cy))
            painter.drawLine(QPointF(118, cy), QPointF(152, cy))
            painter.setBrush(QColor("#1b3245"))
            painter.setPen(QPen(QColor("#83b8ff" if selected else "#6e8bac"), 2))
            painter.drawEllipse(QPointF(43, cy), 6, 6)
            painter.drawEllipse(QPointF(112, cy), 6, 6)
            on = params.get("value", 0) == 1
            painter.setPen(QPen(QColor("#63d39b" if on else "#88a2bd"), 4, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(43, cy), QPointF(104, cy - 18 if on else cy + 13))
            _name(painter, "ON" if on else "OFF", QRectF(64, cy + 16, 42, 18),
                  "#63d39b" if on else "#8da1b6", 8)

    elif kind == "CONST":
        painter.setPen(QPen(QColor("#7895ad"), 2))
        painter.setBrush(_gradient("#3d5363", "#1a2c38", y0, y1))
        if int(params.get("width", 1)) > 1:
            painter.drawRoundedRect(QRectF(37, 34, 79, height - 42), 11, 11)
        else:
            painter.drawEllipse(QPointF(84, cy), 30, 30)
            painter.drawEllipse(QPointF(84, cy), 24, 24)
            painter.drawLine(QPointF(114, cy), QPointF(156, cy))

    elif kind == "OUTPUT":
        painter.setPen(QPen(QColor("#7794ad"), 2))
        if int(params.get("width", 1)) > 1:
            painter.setBrush(_gradient("#233845", "#101e2b", y0, y1))
            painter.drawRoundedRect(QRectF(73, 34, 74, height - 42), 8, 8)
            painter.drawRoundedRect(QRectF(79, 39, 62, 33), 4, 4)
        else:
            painter.drawLine(QPointF(0, 47), QPointF(80, 47))
            painter.setBrush(QColor("#1c2d3b"))
            painter.drawEllipse(QPointF(120, 51), 23, 23)

    elif kind in DISPLAYS:
        if kind == "Seven-segment Display":
            painter.setPen(QPen(QColor("#8b4d48" if not selected else "#ff9b82"), 2))
            painter.setBrush(_gradient("#291e27", "#160f17", y0, y1))
            painter.drawRoundedRect(QRectF(81, 39, 65, 142), 12, 12)
            painter.setPen(QPen(QColor("#3a3945"), 1))
            painter.drawRoundedRect(QRectF(86, 45, 55, 130), 7, 7)
        else:
            cy_bulb = 72 if kind.startswith("RGB") else 59
            r = 24 if "Lamp" in kind or kind == "RGB" else 19
            painter.setPen(QPen(QColor("#9caebf" if selected else "#546b7f"), 2))
            painter.setBrush(_gradient("#263641", "#17242f", cy_bulb - r, cy_bulb + r))
            painter.drawEllipse(QPointF(119, cy_bulb), r, r)
            painter.setPen(QPen(QColor("#597189"), 2))
            for i in range(3 if kind.startswith("RGB") else 1):
                yy = 47 + 24 * i
                painter.drawLine(QPointF(0, yy), QPointF(74, yy))

    elif category == "Bus":
        # A ribbon/data-path motif makes native bus components distinct from ICs.
        painter.setPen(QPen(QColor("#69cfbd" if selected else "#3d8f90"), 2.2))
        painter.setBrush(_gradient("#173d46", "#10242d", y0, y1))
        body = QPainterPath()
        body.moveTo(27, y0); body.lineTo(width - 33, y0)
        body.lineTo(width - 19, cy); body.lineTo(width - 33, y1)
        body.lineTo(27, y1); body.lineTo(16, cy); body.closeSubpath()
        painter.drawPath(body)
        painter.setPen(QPen(QColor("#4a9ba0"), 1.4))
        if kind in ("Bus Input", "Bus Output", "Bus Probe"):
            painter.drawLine(QPointF(42, y0 + 35), QPointF(width - 48, y0 + 35))
        else:
            for offset in (-5, 0, 5):
                painter.drawLine(QPointF(42, cy + offset), QPointF(width - 48, cy + offset))
        symbol = {"Bus Input": "IN", "Bus Output": "OUT", "Bus Probe": "PROBE",
                  "Bus Splitter": "1 → n", "Bus Merger": "n → 1", "Bit Selector": "BIT"}.get(kind, "BUS")
        _name(painter, symbol, QRectF(40, y0 + 10, width - 80, 24), "#b3f2e3", 10)

    elif category == "Timing":
        radius = min(37, max(27, (height - 40) / 2))
        center = QPointF(91, cy)
        painter.setPen(QPen(QColor("#75bfc6" if not selected else "#a3f5ff"), 3))
        painter.setBrush(_gradient("#203d47", "#102731", cy - radius, cy + radius))
        painter.drawEllipse(center, radius, radius)
        painter.setPen(QPen(QColor("#7fdbe4"), 2, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(center.x(), center.y()), QPointF(center.x(), center.y() - radius * .65))
        painter.drawLine(QPointF(center.x(), center.y()), QPointF(center.x() + radius * .48, center.y() + radius * .25))
        painter.setBrush(QColor("#bdeef2"))
        painter.drawEllipse(center, 3, 3)
        tag = {"Clock Generator": "CLK", "Oscillator": "OSC", "Clock Divider": "÷",
               "Timer": "T", "Pulse Generator": "P"}.get(kind, "CLK")
        _name(painter, tag, QRectF(105, cy + radius * .35, 35, 18), "#a9e7e8", 8)

    elif category in ("Memory", "Memory Elements", "Registers and Counters"):
        # Physical IC package with a molded notch and leads aligned to pins.
        rect = QRectF(18, y0, width - 36, y1 - y0)
        tint = "#26343b" if category == "Memory" else ("#2a2c42" if category == "Memory Elements" else "#253d39")
        painter.setBrush(_gradient(tint, "#111a23", y0, y1))
        painter.setPen(QPen(QColor("#8496a7" if selected else "#4a5b6b"), 2))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QPen(QColor("#6b7e8b"), 2))
        painter.drawArc(QRectF(width / 2 - 8, y0 - 8, 16, 16), 180 * 16, 180 * 16)
        for i in range(max(3, min(20, int((height - 35) / 24)))):
            yy = 47 + i * 24
            if yy < y1 - 3:
                painter.setPen(QPen(QColor("#7c8d98"), 3, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(7, yy), QPointF(18, yy))
                painter.drawLine(QPointF(width - 18, yy), QPointF(width - 7, yy))
        band = {"RAM": "#5abbd6", "ROM": "#9db8ff", "Register File": "#73d3b4",
                "Address Decoder": "#e3a9df", "SRAM": "#73d3b4", "DRAM": "#8ad4c5",
                "EEPROM": "#d5b174", "Flash Memory": "#e79d61"}.get(kind, "#a79dde")
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(band))
        painter.drawRoundedRect(QRectF(27, y0 + 8, 4, max(18, y1 - y0 - 16)), 2, 2)
        short = {"D Flip-Flop": "D ▸ Q", "JK Flip-Flop": "JK ▸ Q", "T Flip-Flop": "T ▸ Q",
                 "SR Latch": "S R ▸ Q", "D Latch": "D E ▸ Q",
                 "Shift Register": "⇢ ⇢ ⇢", "Register File": "R0  R1  R2",
                 "Address Decoder": "ADDR → SEL", "Binary Counter": "0 1 2 3",
                 "Up Counter": "↑ 0 1 2", "Down Counter": "↓ 3 2 1"}.get(kind, kind.upper())
        name_y = y0 + 10 if height > 160 else cy - 14
        _name(painter, short, QRectF(width / 2 - 47, name_y, 94, 27),
              "#b9e7e1" if category == "Registers and Counters" else "#d3d9f1", 10)
        if category == "Memory" and height > 160:
            painter.setPen(QPen(QColor("#496374"), 1))
            for row in range(5):
                for col in range(4):
                    painter.setBrush(QColor("#1c3540") if (row + col) % 2 else QColor("#29404b"))
                    painter.drawRoundedRect(QRectF(width / 2 - 29 + col * 15,
                                                   cy - 25 + row * 14, 10, 8), 2, 2)
        elif category == "Registers and Counters" and height > 160:
            for i in range(2, min(8, int(params.get("width", 4)))):
                yy = 47 + i * 24
                painter.setPen(QPen(QColor("#62847e"), 1))
                painter.setBrush(QColor("#18312d"))
                painter.drawRoundedRect(QRectF(width / 2 - 9, yy - 5, 18, 10), 3, 3)

    elif category == "CPU":
        # Datapath controls use a notched chip with a distinctive center trace.
        chip = QPainterPath()
        chip.moveTo(20, y0 + 9); chip.lineTo(30, y0); chip.lineTo(width - 30, y0)
        chip.lineTo(width - 20, y0 + 9); chip.lineTo(width - 20, y1 - 9)
        chip.lineTo(width - 30, y1); chip.lineTo(30, y1)
        chip.lineTo(20, y1 - 9); chip.closeSubpath()
        _path(painter, chip, "#e4b979" if selected else "#9c805c",
              _gradient("#403528", "#1c252d", y0, y1), 2)
        painter.setPen(QPen(QColor("#bd9c6a"), 1.3))
        painter.drawLine(QPointF(34, y0 + 14), QPointF(width - 34, y0 + 14))
        painter.drawLine(QPointF(34, y1 - 14), QPointF(width - 34, y1 - 14))
        symbol = {"Program Counter": "PC +1", "Instruction Register": "IR ▸",
                  "Control Unit": "CTRL", "ISA Control Unit": "μCTRL"}.get(kind, "CPU")
        _name(painter, symbol, QRectF(31, cy - 17, width - 62, 34), "#f7d7a5", 15)
        _name(painter, "8-BIT DATAPATH" if kind != "Control Unit" else "MICROCODE",
              QRectF(34, cy + 21, width - 68, 17), "#b99b79", 8, False)

    elif category == "Arithmetic":
        p = QPainterPath()
        p.moveTo(40, y0); p.lineTo(115, y0); p.lineTo(140, cy - 9)
        p.lineTo(140, cy + 9); p.lineTo(115, y1); p.lineTo(40, y1)
        p.lineTo(15, cy + 9); p.lineTo(15, cy - 9); p.closeSubpath()
        _path(painter, p, "#e7ae68" if not selected else "#ffd598",
              _gradient("#493425", "#241c1b", y0, y1), 2.4)
        operator = {"Adder": "+", "Subtractor": "−", "Multiplier": "×",
                    "Divider": "÷", "ALU": "ALU"}[kind]
        _name(painter, operator, QRectF(44, cy - 21, 68, 42), "#ffd291", 24 if kind != "ALU" else 14)

    elif category == "Basic Circuits":
        p = QPainterPath()
        p.moveTo(23, y0); p.lineTo(118, y0); p.lineTo(140, y0 + 20)
        p.lineTo(140, y1 - 14); p.lineTo(118, y1); p.lineTo(23, y1)
        p.lineTo(15, y1 - 10); p.lineTo(15, y0 + 10); p.closeSubpath()
        _path(painter, p, "#a691dd" if not selected else "#cebaff",
              _gradient("#372f4b", "#1d1c2f", y0, y1), 2.2)
        symbols = {"Half Adder": "½ Σ", "Full Adder": "Σ", "Half Subtractor": "½ Δ",
                   "Full Subtractor": "Δ", "Comparator": "< = >", "Multiplexer": "2 → 1",
                   "Demultiplexer": "1 → 2", "Decoder": "2 → 4", "Encoder": "4 → 2"}
        _name(painter, symbols.get(kind, kind), QRectF(42, cy - 16, 78, 32), "#e1d2ff", 13)

    elif kind in ANALOG:
        painter.setPen(QPen(QColor("#d6b373"), 2.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(QPointF(0, 47), QPointF(30, 47))
        painter.drawLine(QPointF(126, 47), QPointF(156, 47))
        if kind == "Resistor":
            p = QPainterPath(QPointF(30, 47))
            for x, y in ((43, 47), (51, 35), (64, 59), (77, 35), (90, 59), (103, 35), (113, 47), (126, 47)):
                p.lineTo(x, y)
            painter.drawPath(p)
        elif kind == "Capacitor":
            painter.drawLine(QPointF(61, 28), QPointF(61, 66))
            painter.drawLine(QPointF(93, 28), QPointF(93, 66))
            painter.drawLine(QPointF(30, 47), QPointF(61, 47))
            painter.drawLine(QPointF(93, 47), QPointF(126, 47))
        elif kind in ("Diode",):
            p = QPainterPath(QPointF(50, 31)); p.lineTo(50, 63); p.lineTo(94, 47); p.closeSubpath()
            _path(painter, p, "#d6b373", QBrush(QColor("#382d23")), 2)
            painter.drawLine(QPointF(96, 28), QPointF(96, 66))
        elif kind == "Crystal Oscillator":
            painter.drawRect(QRectF(59, 34, 35, 26))
            painter.drawLine(QPointF(53, 29), QPointF(53, 65))
            painter.drawLine(QPointF(100, 29), QPointF(100, 65))
        elif kind == "MOSFET":
            painter.drawLine(QPointF(48, 29), QPointF(48, 67))
            painter.drawLine(QPointF(66, 28), QPointF(66, 66))
            painter.drawLine(QPointF(66, 34), QPointF(109, 34))
            painter.drawLine(QPointF(66, 61), QPointF(109, 61))
            painter.drawLine(QPointF(30, 47), QPointF(48, 47))
            painter.drawLine(QPointF(109, 34), QPointF(109, 47))
            painter.drawLine(QPointF(109, 61), QPointF(109, 47))
        elif kind in ("BJT", "Transistor"):
            painter.drawEllipse(QPointF(78, 47), 27, 27)
            painter.drawLine(QPointF(44, 47), QPointF(67, 47))
            painter.drawLine(QPointF(67, 31), QPointF(67, 63))
            painter.drawLine(QPointF(67, 38), QPointF(97, 23))
            painter.drawLine(QPointF(67, 56), QPointF(97, 71))
            if kind == "BJT":
                painter.drawLine(QPointF(91, 62), QPointF(97, 71))
                painter.drawLine(QPointF(87, 69), QPointF(97, 71))
            else:
                painter.drawEllipse(QPointF(97, 71), 3, 3)
        else:
            painter.drawEllipse(QPointF(78, 47), 24, 24)
            painter.drawLine(QPointF(64, 33), QPointF(89, 61))
            painter.drawLine(QPointF(64, 61), QPointF(90, 34))
        _name(painter, "VISUAL ONLY", QRectF(30, height - 29, 100, 17), "#bd9862", 7)

    else:  # Reusable custom block: socketed module, distinct from ICs.
        p = QPainterPath()
        p.moveTo(18, y0); p.lineTo(62, y0); p.cubicTo(62, y0 + 15, 94, y0 + 15, 94, y0)
        p.lineTo(138, y0); p.lineTo(138, y1); p.lineTo(18, y1); p.closeSubpath()
        _path(painter, p, "#6fb7bd" if not selected else "#a6f7fc",
              _gradient("#21434b", "#13262d", y0, y1), 2)
        _name(painter, "CUSTOM", QRectF(37, cy - 14, 82, 28), "#b2e8e7", 10)

    painter.restore()

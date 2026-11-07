"""Shared external appearance for designer previews and placed custom blocks."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen, QBrush, QPainter


def block_geometry(definition):
    design = definition.get("designer", {})
    appearance = design.get("appearance", {})
    width = max(100, min(520, int(appearance.get("width", 180))))
    height = max(100, min(520, int(appearance.get("height", 120))))
    return width, height


def terminal_positions(definition, width, height):
    layout = definition.get("designer", {}).get("terminals", {})
    by_side = {side: [] for side in ("LEFT", "RIGHT", "TOP", "BOTTOM")}
    for direction, names, default in (("input", definition["inputs"], "LEFT"),
                                      ("output", definition["outputs"], "RIGHT")):
        for original_index, name in enumerate(names):
            info = layout.get(name, {})
            side = info.get("side", default)
            if side not in by_side: side = default
            by_side[side].append((int(info.get("order", original_index)), original_index, direction, name))
    result = {}
    for side, items in by_side.items():
        items.sort()
        for index, (_, _, direction, name) in enumerate(items):
            fraction = (index + 1) / (len(items) + 1)
            if side == "LEFT": point = QPointF(0, 30 + fraction * (height - 45))
            elif side == "RIGHT": point = QPointF(width, 30 + fraction * (height - 45))
            elif side == "TOP": point = QPointF(18 + fraction * (width - 36), 27)
            else: point = QPointF(18 + fraction * (width - 36), height)
            result[direction, name] = (point, side)
    return result


def paint_designed_block(painter, definition, name, width, height, positions, selected=False):
    appearance = definition.get("designer", {}).get("appearance", {})
    body = QColor(appearance.get("body_color", "#29465a"))
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#a7d1e8") if selected else QColor("#78a5c0"), 2))
    painter.setBrush(QBrush(body))
    painter.drawRoundedRect(QRectF(8, 29, width - 16, height - 40), 11, 11)
    painter.setPen(QColor("#e7f3ff"))
    painter.setFont(QFont("Sans Serif", 11, QFont.DemiBold))
    label = appearance.get("label") or name
    painter.drawText(QRectF(19, 35, width - 38, 26), Qt.AlignCenter,
                     painter.fontMetrics().elidedText(label, Qt.ElideRight, width - 40))
    short = appearance.get("short_description", "")
    if short:
        painter.setPen(QColor("#b4cfdb"))
        painter.setFont(QFont("Sans Serif", 8))
        painter.drawText(QRectF(20, 65, width - 40, 25), Qt.AlignCenter,
                         painter.fontMetrics().elidedText(short, Qt.ElideRight, width - 45))
    painter.setFont(QFont("Sans Serif", 8))
    for (direction, pin), (point, side) in positions.items():
        painter.setPen(QPen(QColor("#80aec7"), 2))
        if side == "LEFT":
            painter.drawLine(point, point + QPointF(20, 0))
            text_rect, alignment = QRectF(25, point.y() - 9, min(65, width / 2 - 25), 18), Qt.AlignVCenter
        elif side == "RIGHT":
            painter.drawLine(point - QPointF(20, 0), point)
            text_rect, alignment = QRectF(width - 90, point.y() - 9, 65, 18), Qt.AlignVCenter | Qt.AlignRight
        elif side == "TOP":
            painter.drawLine(point, point + QPointF(0, 17))
            text_rect, alignment = QRectF(point.x() - 25, 46, 50, 18), Qt.AlignCenter
        else:
            painter.drawLine(point - QPointF(0, 17), point)
            text_rect, alignment = QRectF(point.x() - 25, height - 33, 50, 18), Qt.AlignCenter
        painter.setPen(QColor("#d5e7f1"))
        painter.drawText(text_rect, alignment, painter.fontMetrics().elidedText(pin, Qt.ElideRight, int(text_rect.width())))
    painter.restore()

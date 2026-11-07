"""Small vector icons for canvas tools; no external image assets required."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

TOOL_COLORS = {"flip": QColor("#6ce4cf"), "erase": QColor("#f392a5"),
               "cut": QColor("#f4bd73")}


def tool_pixmap(tool, size=40):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 40, size / 40)
    color = TOOL_COLORS[tool]
    painter.setPen(QPen(color, 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    if tool == "flip":
        painter.drawEllipse(QPointF(20, 20), 14, 14)
        painter.setBrush(QColor("#173c3f"))
        painter.drawEllipse(QPointF(20, 20), 10, 10)
        path = QPainterPath(QPointF(23, 8))
        path.lineTo(17, 20)
        path.lineTo(22, 20)
        path.lineTo(17, 32)
        painter.setPen(QPen(QColor("#d8fff3"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)
    elif tool == "erase":
        path = QPainterPath(QPointF(9, 25))
        path.lineTo(22, 9)
        path.quadTo(25, 7, 28, 10)
        path.lineTo(34, 16)
        path.quadTo(36, 18, 33, 21)
        path.lineTo(22, 33)
        path.lineTo(15, 33)
        path.closeSubpath()
        painter.setBrush(QColor("#583342"))
        painter.drawPath(path)
        painter.drawLine(QPointF(17, 17), QPointF(27, 27))
        painter.setPen(QPen(QColor("#ffd5df"), 2))
        painter.drawLine(QPointF(7, 33), QPointF(34, 33))
    else:
        painter.setPen(QPen(color, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawEllipse(QPointF(11, 28), 4.5, 4.5)
        painter.drawEllipse(QPointF(27, 28), 4.5, 4.5)
        painter.drawLine(QPointF(14, 24), QPointF(30, 8))
        painter.drawLine(QPointF(24, 24), QPointF(8, 8))
        painter.setBrush(QColor("#ffe3b6"))
        painter.drawEllipse(QPointF(19, 18), 2, 2)
    painter.end()
    return pixmap

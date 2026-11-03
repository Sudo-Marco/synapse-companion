from __future__ import annotations

from dataclasses import dataclass
import math

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class TeleportStyle:
    name: str
    duration_ms: int
    color: str
    glyphs: tuple[str, ...]
    arc_fraction: float
    shake_px: float = 0.0
    overshoot: float = 0.05


STYLES = {
    "curious": TeleportStyle("curious", 560, "#42dce8", (".", "+", "*", ":"), 0.15),
    "happy": TeleportStyle("happy", 680, "#f0bd39", ("+", "*", "✦", "."), 0.20,
                           overshoot=0.09),
    "stress": TeleportStyle("stress", 460, "#ef896e", ("!", ":", "/", "+"), 0.06,
                            shake_px=5.0, overshoot=0.015),
    "sleepy": TeleportStyle("sleepy", 900, "#90a9d0", ("z", ".", "·", "z"), 0.04,
                            overshoot=0.015),
    "communicate": TeleportStyle("communicate", 620, "#83e6d0", ("+", ".", "*"), 0.10,
                                 overshoot=0.04),
}


def quadratic_point(start: QPointF, end: QPointF, amount: float,
                    arc_px: float) -> QPointF:
    t = max(0.0, min(1.0, float(amount)))
    control = QPointF((start.x() + end.x()) * 0.5,
                      (start.y() + end.y()) * 0.5 - float(arc_px))
    inverse = 1.0 - t
    return QPointF(inverse * inverse * start.x()
                   + 2.0 * inverse * t * control.x() + t * t * end.x(),
                   inverse * inverse * start.y()
                   + 2.0 * inverse * t * control.y() + t * t * end.y())


def _smooth(value: float) -> float:
    t = max(0.0, min(1.0, value))
    return t * t * (3.0 - 2.0 * t)


def teleport_geometry(start: QRect, destination: QRect, progress: float,
                      style: TeleportStyle) -> tuple[QRect, float]:
    """Return the animated pet rectangle and opacity for one normalized frame."""
    p = max(0.0, min(1.0, float(progress)))
    if p <= 0.0:
        return QRect(start), 1.0
    if p >= 1.0:
        return QRect(destination), 1.0
    start_center = QPointF(start.center())
    end_center = QPointF(destination.center())
    arc = max(0.0, math.hypot(end_center.x() - start_center.x(),
                              end_center.y() - start_center.y())
              * style.arc_fraction)

    if p < 0.20:
        phase = _smooth(p / 0.20)
        center = start_center
        scale = 1.0 - 0.56 * phase
        opacity = 1.0 - 0.82 * phase
    elif p < 0.78:
        phase = _smooth((p - 0.20) / 0.58)
        center = quadratic_point(start_center, end_center, phase, arc)
        scale = 0.44
        opacity = 0.18 + 0.12 * math.sin(math.pi * phase)
    else:
        phase = _smooth((p - 0.78) / 0.22)
        center = end_center
        scale = 0.44 + (1.0 - 0.44) * phase
        scale += style.overshoot * math.sin(math.pi * phase)
        opacity = min(1.0, 0.18 + 0.82 * phase)

    width = max(80, round(start.width() * scale))
    height = max(52, round(start.height() * scale))
    x = round(center.x() - width * 0.5)
    y = round(center.y() - height * 0.5)
    if style.shake_px and 0.20 <= p <= 0.78:
        shake = (1.0 - abs(p - 0.49) / 0.29) * style.shake_px
        x += round(math.sin(p * 119.0) * shake)
        y += round(math.cos(p * 137.0) * shake * 0.55)
    return QRect(x, y, width, height), max(0.0, min(1.0, opacity))


class TeleportTrail(QWidget):
    """Short-lived, transparent, mouse-pass-through ASCII particle trail."""

    def __init__(self, start: QPointF, end: QPointF, style: TeleportStyle,
                 duration_ms: int, parent: QWidget | None = None) -> None:
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                 Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.WindowTransparentForInput |
                 Qt.WindowType.NoDropShadowWindowHint)
        super().__init__(parent, flags)
        self.start = QPointF(start)
        self.end = QPointF(end)
        self.style = style
        self.duration_ms = max(1, int(duration_ms))
        self.progress = 0.0
        margin = 48
        left = math.floor(min(start.x(), end.x())) - margin
        top = math.floor(min(start.y(), end.y())) - margin
        right = math.ceil(max(start.x(), end.x())) + margin
        bottom = math.ceil(max(start.y(), end.y())) + margin
        self.origin = QPointF(left, top)
        self.setGeometry(left, top, max(1, right - left), max(1, bottom - top))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_progress(self, progress: float) -> None:
        self.progress = max(0.0, min(1.0, float(progress)))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        color = QColor(self.style.color)
        start = self.start - self.origin
        end = self.end - self.origin
        arc = math.hypot(end.x() - start.x(), end.y() - start.y()) * self.style.arc_fraction
        count = 9
        for index in range(count):
            t = self.progress - index * 0.045
            if t < 0.0 or t > 1.0:
                continue
            point = quadratic_point(start, end, t, arc)
            alpha = int(235 * (1.0 - index / count) * (0.45 + 0.55 * self.progress))
            color.setAlpha(alpha)
            painter.setPen(QPen(color))
            glyph = self.style.glyphs[index % len(self.style.glyphs)]
            painter.drawText(round(point.x()), round(point.y()), glyph)

        if self.progress < 0.24:
            fade = 1.0 - self.progress / 0.24
            for index in range(7):
                angle = index * (2.0 * math.pi / 7.0)
                radius = 18.0 + 25.0 * fade
                x = start.x() + math.cos(angle) * radius * fade
                y = start.y() + math.sin(angle) * radius * fade
                color.setAlpha(int(210 * fade))
                painter.setPen(QPen(color))
                painter.drawText(round(x), round(y), self.style.glyphs[index % len(self.style.glyphs)])

        if self.progress > 0.78:
            bloom = (self.progress - 0.78) / 0.22
            for index in range(8):
                angle = index * (2.0 * math.pi / 8.0)
                radius = 10.0 + 34.0 * bloom
                x = end.x() + math.cos(angle) * radius
                y = end.y() + math.sin(angle) * radius
                color.setAlpha(int(190 * (1.0 - bloom) + 40))
                painter.setPen(QPen(color))
                painter.drawText(round(x), round(y), self.style.glyphs[index % len(self.style.glyphs)])
        painter.end()

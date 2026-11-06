from __future__ import annotations

import time

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRectF, Qt,
                            QPropertyAnimation, QTimer)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTransform
from PySide6.QtWidgets import QWidget

from ..runtime.autonomy import StoredPostIt


POSTIT_COLORS = {
    "estressado": ("#342820", "#f2bb74"),
    "entediado": ("#302a35", "#d2b8ec"),
    "curioso": ("#173238", "#80e3df"),
    "atencao": ("#263329", "#c8e5a0"),
}


class PostItWindow(QWidget):
    """A small template-only note window that never takes keyboard focus."""

    def __init__(self, note: StoredPostIt, text: str, *, quick_dismiss_s: float,
                 on_interact, on_close, parent: QWidget | None = None,
                 pixel_theme: bool = False,
                 origin: QPoint | None = None, animate: bool = True) -> None:
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                 Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.WindowDoesNotAcceptFocus |
                 Qt.WindowType.NoDropShadowWindowHint)
        super().__init__(parent, flags)
        self.note = note
        self.text = str(text)
        self.pixel_theme = bool(pixel_theme)
        self.quick_dismiss_s = max(0.0, float(quick_dismiss_s))
        self.on_interact = on_interact
        self.on_close = on_close
        self._drag_offset: QPoint | None = None
        self._close_reason = "dismissed"
        self._created_at = note.created_at
        self._rotation = {"estressado": -2.0, "entediado": 1.7,
                          "curioso": -1.2, "atencao": 1.4}.get(note.emotion, 0.8)
        if self.pixel_theme:
            self._rotation = 0.0
        self.setFixedSize(286, 132)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("Synapse Pet — nota")
        self._color, self._accent = POSTIT_COLORS.get(
            note.emotion, ("#222d32", "#9adbd5"))
        self._expiry = QTimer(self)
        self._expiry.setSingleShot(True)
        self._expiry.timeout.connect(self._expire)
        self._expiry.start(max(1, round((note.expires_at - time.time()) * 1000)))
        destination = QPoint(note.x, note.y)
        if origin is not None and animate:
            self.move(origin)
        else:
            self.move(destination)
        self.show()
        self.raise_()
        if origin is not None and animate:
            animation = QPropertyAnimation(self, b"pos", self)
            animation.setDuration(540)
            animation.setStartValue(origin)
            animation.setKeyValueAt(0.88, destination + QPoint(0, -6))
            animation.setEndValue(destination)
            animation.setEasingCurve(QEasingCurve.Type.OutBack)
            animation.start()
            self._arrival_animation = animation

    def _expire(self) -> None:
        self._close_reason = "expired"
        self.close()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing,
                              not self.pixel_theme)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._rotation)
        card = QRectF(-130, -52, 260, 104)
        painter.setPen(QPen(QColor(self._accent),
                            2 if self.pixel_theme else 1.2))
        painter.setBrush(QColor(self._color))
        if self.pixel_theme:
            painter.drawRect(card)
        else:
            painter.drawRoundedRect(card, 8, 8)
        painter.setPen(QPen(QColor(self._accent)))
        font_family = "Silkscreen" if self.pixel_theme else "Consolas"
        painter.setFont(QFont(font_family, 8, QFont.Weight.Bold))
        painter.drawText(QRectF(-112, -39, 195, 17), "POST-IT · " + self.note.emotion.upper())
        body_font = "Silkscreen" if self.pixel_theme else "Segoe UI"
        painter.setFont(QFont(body_font, 9 if self.pixel_theme else 10))
        painter.setPen(QPen(QColor("#e8eeee")))
        painter.drawText(QRectF(-112, -17, 224, 47),
                         Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self.text)
        painter.setPen(QPen(QColor(self._accent)))
        painter.setFont(QFont(body_font, 8, QFont.Weight.DemiBold))
        if self.pixel_theme:
            painter.drawRect(QRectF(48, 28, 62, 20))
        else:
            painter.drawRoundedRect(QRectF(48, 28, 62, 20), 5, 5)
        painter.drawText(QRectF(48, 28, 62, 20), Qt.AlignmentFlag.AlignCenter, "Entendi")
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(112, -46, 18, 18), Qt.AlignmentFlag.AlignCenter, "×")
        painter.end()

    def _unrotate(self, point: QPointF) -> QPointF:
        relative = point - QPointF(self.width() / 2, self.height() / 2)
        inverse = QTransform().rotate(-self._rotation)
        transformed = inverse.map(relative)
        return transformed + QPointF(self.width() / 2, self.height() / 2)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        local = self._unrotate(event.position())
        centered = local - QPointF(self.width() / 2, self.height() / 2)
        if QRectF(48, 28, 62, 20).contains(centered):
            self.on_interact(self.note.note_id)
            self._close_reason = "interacted"
            self.close()
            return
        if QRectF(108, -50, 23, 24).contains(centered):
            self._close_reason = "dismissed"
            self.close()
            return
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.on_close(self.note.note_id, "moved", self.pos(), self._created_at,
                          self.quick_dismiss_s)

    def closeEvent(self, event) -> None:
        self._expiry.stop()
        self.on_close(self.note.note_id, self._close_reason, self.pos(), self._created_at,
                      self.quick_dismiss_s)
        event.accept()


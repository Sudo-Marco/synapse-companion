from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QWidget

from ..runtime.visual_state import StateAnimator, VisualState
from .ascii_renderer import AsciiRenderer
from .interaction import AffectionDragTracker


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


class CpuEyeWidget(QWidget):
    petRequested = Signal()

    def __init__(self, width: int, height: int, ascii_columns: int,
                 ascii_rows: int, palette: str, parent: QWidget | None = None,
                 affection_drag_min_s: float = 1.0) -> None:
        super().__init__(parent)
        self.setMinimumSize(700, 390)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.internal_width = max(320, width)
        self.internal_height = max(240, height)
        self.state = VisualState()
        self.target_state = self.state
        self.animator = StateAnimator(self.state)
        self._opening_value = 0.84
        self._opening_time = 0.0
        self.rendered_frames = 0
        self.mode = "shader"
        self.gaze = (0.0, 0.0)
        self._drag_tracker = AffectionDragTracker(affection_drag_min_s)
        self._ascii = AsciiRenderer(ascii_columns, ascii_rows, palette,
                                   self.internal_width, self.internal_height)
        self._rng = random.Random(9137)
        self._stars = [(self._rng.random(), self._rng.random(),
                        self._rng.uniform(0.3, 1.0)) for _ in range(90)]
        self.setToolTip(
            f"Mova para direcionar o olhar; arraste sobre o olho por {affection_drag_min_s:g}s "
            "ou use CARINHO.")

    def set_state(self, state: VisualState) -> None:
        self.target_state = state
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def mouseMoveEvent(self, event) -> None:
        point = event.position()
        self.gaze = (_clamp(point.x() / max(1, self.width()) * 2.0 - 1.0, -1.0, 1.0),
                     _clamp(point.y() / max(1, self.height()) * 2.0 - 1.0, -1.0, 1.0))
        if self._drag_tracker.move(
                point.x(), point.y(), self.width(), self.height(),
                bool(event.buttons() & Qt.MouseButton.LeftButton)):
            self.petRequested.emit()
        self.update()
        super().mouseMoveEvent(event)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)

    def mousePressEvent(self, event) -> None:
        self._drag_tracker.press(
            event.position().x(), event.position().y(), self.width(), self.height(),
            event.button() == Qt.MouseButton.LeftButton)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drag_tracker.release():
                self.petRequested.emit()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._drag_tracker.cancel()
        super().leaveEvent(event)

    def _opening(self, now: float) -> tuple[float, float]:
        state = self.state
        target = 0.42 + 0.54 * _clamp(state.energy)
        if state.expression_override == "aberto":
            target = 0.88
        elif state.expression_override == "semicerrado":
            target = 0.54
        elif state.expression_override == "arregalado":
            target = 1.04
        if state.emotion == "alegre":
            target = 0.89 - 0.08 * max(0.0, math.sin(now * 4.2))
        elif state.emotion == "estressado":
            target = 0.67 + 0.035 * math.sin(now * 24.0)
        elif state.emotion == "triste":
            target = 0.62
        elif state.emotion == "curioso":
            target = 1.0
        elif state.emotion == "sonolento":
            target = 0.42
        elif state.emotion == "aberto":
            target = 0.88
        elif state.emotion == "semicerrado":
            target = 0.54
        elif state.emotion == "arregalado":
            target = 1.04
        elif state.emotion == "piscar":
            target = 0.92
        dt = 1.0 / 30.0 if self._opening_time == 0 else max(0.0, min(0.5, now - self._opening_time))
        self._opening_time = now
        blend = 1.0 - math.exp(-dt / 0.15)
        self._opening_value += (target - self._opening_value) * blend
        opening = self._opening_value
        phase = now % (5.2 if state.emotion == "triste" else 4.1)
        blink = max(0.0, 1.0 - abs(phase - 0.11) / 0.12)
        if state.emotion == "alegre":
            blink = max(blink, 1.0 - abs(phase - 0.31) / 0.11)
        elif state.emotion == "piscar":
            blink = max(blink, 0.96 * (0.5 + 0.5 * math.sin(now * 5.0)))
        return opening * (1.0 - _clamp(blink) * 0.95), blink

    def _eye_path(self, opening: float) -> QPainterPath:
        left, right, cy, ry = 88.0, 912.0, 305.0, 155.0
        path = QPainterPath(QPointF(left, cy))
        path.cubicTo(left + 130, cy - 2.0 * ry * opening,
                     right - 130, cy - 2.0 * ry * opening, right, cy)
        path.cubicTo(right - 140, cy + 1.72 * ry * opening,
                     left + 140, cy + 1.72 * ry * opening, left, cy)
        path.closeSubpath()
        return path

    def _paint_scene(self, painter: QPainter, width: int, height: int) -> None:
        painter.save()
        painter.scale(width / 1000.0, height / 600.0)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(QRectF(0, 0, 1000, 600), QColor("#050a10"))

        grid_pen = QPen(QColor(20, 45, 55, 70), 1)
        painter.setPen(grid_pen)
        for x in range(20, 1000, 34):
            painter.drawLine(x, 0, x, 600)
        for y in range(18, 600, 28):
            painter.drawLine(0, y, 1000, y)
        frame_time = time.monotonic()
        for x, y, strength in self._stars:
            alpha = int(35 + 48 * strength * (0.5 + 0.5 * math.sin(frame_time * 2 + x * 11)))
            painter.setPen(QPen(QColor(53, 203, 218, alpha), 1))
            painter.drawPoint(QPointF(x * 1000, y * 600))

        painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        painter.setPen(QColor("#35d7e1"))
        painter.drawText(28, 34, "> SYSTEM: ONLINE")
        painter.setPen(QColor("#e9b725"))
        painter.drawText(625, 34, "OCULUS  /  NOCTURNE")
        painter.setFont(QFont("Consolas", 8))
        painter.setPen(QColor("#66838b"))
        painter.drawText(28, 52, f"> STATE: {self.state.emotion.upper()}")

        now = time.monotonic()
        opening, blink = self._opening(now)
        eye = self._eye_path(opening)
        microsaccade = min(4.0, max(0.0, self.state.firing_rate) * 36.0)
        center_x = (500.0 + self.gaze[0] * 16
                    + math.sin(now * 13.0) * microsaccade)
        center_y = (305.0 + self.gaze[1] * 9
                    + math.cos(now * 11.0) * microsaccade * 0.55)
        iris_radius = 107.0
        eye_bounds = QRectF(88, 150, 824, 310)

        socket = QPainterPath()
        socket.addEllipse(eye_bounds.adjusted(-18, -15, 18, 15))
        socket_gradient = QRadialGradient(QPointF(500, 305), 490)
        socket_gradient.setColorAt(0.0, QColor("#1b333a"))
        socket_gradient.setColorAt(0.78, QColor("#10191e"))
        socket_gradient.setColorAt(1.0, QColor("#04090d"))
        painter.fillPath(socket, QBrush(socket_gradient))
        painter.setPen(QPen(QColor("#39cbd4"), 2.0))
        painter.drawPath(eye)

        painter.save()
        painter.setClipPath(eye)
        sclera = QLinearGradient(0, 145, 0, 460)
        sclera.setColorAt(0.0, QColor("#9cb7b5"))
        sclera.setColorAt(0.38, QColor("#e0e7dc"))
        sclera.setColorAt(1.0, QColor("#78918f"))
        painter.fillPath(eye, QBrush(sclera))

        # Delicate branching veins are more visible at the corners of the sclera.
        for side in (-1.0, 1.0):
            for index in range(7):
                y = 262 + index * 10
                path = QPainterPath(QPointF(500 + side * 270, y))
                path.cubicTo(500 + side * 326, y - 8, 500 + side * 346, y + 5,
                            500 + side * 378, y - 3 + index * 0.4)
                painter.setPen(QPen(QColor(144, 99, 100, 35 + index * 2), 1.0))
                painter.drawPath(path)

        # Iris depth, limbus and radial fibers.
        iris_rect = QRectF(center_x - iris_radius, center_y - iris_radius,
                           iris_radius * 2, iris_radius * 2)
        iris_gradient = QRadialGradient(QPointF(center_x - 20, center_y - 25), iris_radius * 1.3)
        base = QColor.fromRgbF(0.06 + self.state.happiness * 0.11,
                               0.23 + self.state.happiness * 0.22,
                               0.30 + self.state.curiosity * 0.19)
        if self.state.emotion == "estressado":
            base = QColor("#b86437")
        elif self.state.emotion == "triste":
            base = QColor("#357c9b")
        iris_gradient.setColorAt(0.0, QColor("#081219"))
        iris_gradient.setColorAt(0.27, base.lighter(150))
        iris_gradient.setColorAt(0.66, base)
        iris_gradient.setColorAt(0.93, base.darker(160))
        iris_gradient.setColorAt(1.0, QColor("#081118"))
        painter.setPen(QPen(QColor("#d5a948"), 2.0))
        painter.setBrush(QBrush(iris_gradient))
        painter.drawEllipse(iris_rect)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for ring, color, pen_width in ((0.94, QColor("#080f17"), 5),
                                       (0.78, QColor("#49aeb3"), 1),
                                       (0.56, QColor("#d7a846"), 1),
                                       (0.43, QColor("#3eabb6"), 2)):
            radius = iris_radius * ring
            painter.setPen(QPen(color, pen_width))
            painter.drawEllipse(QRectF(center_x - radius, center_y - radius,
                                       radius * 2, radius * 2))
        for index in range(96):
            angle = math.tau * index / 96
            inner = iris_radius * (0.48 + 0.07 * math.sin(index * 3.9))
            outer = iris_radius * (0.90 if index % 4 else 0.97)
            p1 = QPointF(center_x + math.cos(angle) * inner,
                         center_y + math.sin(angle) * inner)
            p2 = QPointF(center_x + math.cos(angle) * outer,
                         center_y + math.sin(angle) * outer)
            tone = QColor("#e1b447") if index % 8 == 0 else QColor("#54c9cc")
            tone.setAlpha(190 if index % 3 else 235)
            painter.setPen(QPen(tone, 2 if index % 8 == 0 else 1))
            painter.drawLine(p1, p2)
        for index in range(22):
            angle = math.tau * index / 22 + 0.08
            r0, r1 = iris_radius * 0.33, iris_radius * (0.39 + (index % 3) * 0.04)
            painter.setPen(QPen(QColor(231, 187, 78, 170), 1))
            painter.drawLine(QPointF(center_x + math.cos(angle) * r0,
                                     center_y + math.sin(angle) * r0),
                             QPointF(center_x + math.cos(angle) * r1,
                                     center_y + math.sin(angle) * r1))

        pupil_radius = iris_radius * (0.28 + 0.14 * _clamp(self.state.stress))
        pupil_gradient = QRadialGradient(QPointF(center_x - 12, center_y - 15), pupil_radius * 1.4)
        pupil_gradient.setColorAt(0.0, QColor("#000307"))
        pupil_gradient.setColorAt(0.72, QColor("#02080c"))
        pupil_gradient.setColorAt(1.0, QColor("#07161b"))
        painter.setPen(QPen(QColor("#78dfe5"), 2))
        painter.setBrush(QBrush(pupil_gradient))
        painter.drawEllipse(QRectF(center_x - pupil_radius, center_y - pupil_radius,
                                   pupil_radius * 2, pupil_radius * 2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(241, 250, 243, 238))
        painter.drawEllipse(QRectF(center_x - 32, center_y - 45, 17, 20))
        painter.setBrush(QColor(246, 194, 69, 228))
        painter.drawEllipse(QRectF(center_x + 26, center_y + 17, 8, 8))

        # Curved lid shadows close over the eye to form each expression.
        upper = QPainterPath(QPointF(70, 100))
        upper.lineTo(930, 100)
        upper.lineTo(912, 305)
        upper.cubicTo(770, 305 - 2 * 155 * opening,
                     230, 305 - 2 * 155 * opening, 88, 305)
        upper.closeSubpath()
        upper_gradient = QLinearGradient(0, 100, 0, 310)
        upper_gradient.setColorAt(0, QColor("#090e14"))
        upper_gradient.setColorAt(1, QColor(19, 50, 57, 235))
        painter.fillPath(upper, QBrush(upper_gradient))
        lower = QPainterPath(QPointF(88, 305))
        lower.cubicTo(230, 305 + 1.72 * 155 * opening,
                     770, 305 + 1.72 * 155 * opening, 912, 305)
        lower.lineTo(930, 510)
        lower.lineTo(70, 510)
        lower.closeSubpath()
        lower_gradient = QLinearGradient(0, 305, 0, 510)
        lower_gradient.setColorAt(0, QColor(17, 50, 57, 226))
        lower_gradient.setColorAt(1, QColor("#080e13"))
        painter.fillPath(lower, QBrush(lower_gradient))
        lid_color = QColor("#ed986a") if self.state.emotion == "estressado" else QColor("#39cad5")
        painter.setPen(QPen(lid_color, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._eye_path(opening))

        for index in range(27):
            s = 0.04 + 0.92 * index / 26
            x = 88 + 824 * s
            y = 305 - 155 * opening * math.sin(math.pi * s) ** 0.68 - 0.035 * (x - 500)
            length = 16 + 14 * (1.0 - abs(s - 0.5) * 2.0)
            painter.setPen(QPen(QColor("#132a32"), 2 if index % 4 == 0 else 1.4,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(x, y), QPointF(x + (s - 0.5) * 15, y - length))

        if self.state.emotion == "triste":
            tear_y = 346 + (now * 29.0 % 115)
            tear_rect = QRectF(500 + 142, tear_y, 9, 20)
            painter.setPen(QPen(QColor("#d8fdff"), 1))
            painter.setBrush(QColor(83, 210, 238, 210))
            painter.drawEllipse(tear_rect)
        if self.state.emotion == "alegre":
            for index in range(8):
                angle = math.tau * index / 8 + now * 0.2
                x = 500 + math.cos(angle) * 355
                y = 305 + math.sin(angle) * 188
                painter.setPen(QPen(QColor("#f1c55b"), 2))
                painter.drawLine(QPointF(x - 5, y), QPointF(x + 5, y))
                painter.drawLine(QPointF(x, y - 5), QPointF(x, y + 5))

        # Real recent SNN spikes become low-count luminous particles.
        for spike_id in self.state.spike_ids[:48]:
            angle = spike_id * 2.399963
            radial = 0.68 + 0.28 * ((spike_id * 0.61803398875) % 1.0)
            x = 500 + math.cos(angle) * 420 * radial
            y = 305 + math.sin(angle) * 178 * radial
            radius = 2 + (spike_id % 3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(89, 221, 239, 155))
            painter.drawEllipse(QPointF(x, y), radius * 3, radius * 3)
            painter.setBrush(QColor("#c4faff"))
            painter.drawEllipse(QPointF(x, y), radius, radius)
        painter.restore()

        painter.setPen(QPen(QColor("#23464e"), 1))
        painter.drawLine(28, 548, 972, 548)
        painter.setFont(QFont("Consolas", 9))
        painter.setPen(QColor("#bad1d0"))
        painter.drawText(28, 578, "> THE EYE IS A WINDOW")
        painter.setPen(QColor("#38b9c7"))
        painter.drawText(805, 578, f"SNN // {self.state.tick_count:06d}")
        painter.restore()

    def render_frame(self) -> object:
        from PySide6.QtGui import QImage
        self.state = self.animator.advance(self.target_state, time.monotonic())
        image = QImage(self.internal_width, self.internal_height,
                       QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        self._paint_scene(painter, self.internal_width, self.internal_height)
        painter.end()
        if self.mode == "ascii":
            return self._ascii.render(image)
        return image

    def paintEvent(self, _event) -> None:
        self.rendered_frames += 1
        image = self.render_frame()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.mode != "ascii")
        painter.drawImage(self.rect(), image)
        if self.mode == "hud":
            self._draw_hud(painter)
        painter.end()

    def _draw_hud(self, painter: QPainter) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(49, 215, 228, 170), 1))
        painter.setBrush(QColor(4, 12, 18, 170))
        painter.drawRoundedRect(QRectF(18, 18, 215, 102), 8, 8)
        painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        painter.setPen(QColor("#3ddbe5"))
        painter.drawText(30, 43, "SYNAPTIC LINK  //  LOCAL")
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(30, 65, f"MOOD {self.state.happiness:0.0%}   ENERGY {self.state.energy:0.0%}")
        painter.drawText(30, 84, f"STRESS {self.state.stress:0.0%}   RATE {self.state.firing_rate:0.3f}")
        painter.drawText(30, 103, f"TICK {self.state.tick_count:08d}   SPIKES {len(self.state.spike_ids):02d}")
        painter.setPen(QColor("#e9b725"))
        painter.drawText(self.width() - 220, 33,
                         f"{time.strftime('%H:%M:%S')}  {self.state.render_fps:02.0f} FPS")
        painter.restore()

from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
import math
import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QStaticText,
    QTransform,
)

from ..runtime.visual_state import VisualState


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


@lru_cache(maxsize=1)
def windows_uses_light_theme() -> bool:
    """Read only Windows' app-theme preference; never sample the screen."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(int(value))
    except (OSError, ValueError, TypeError):
        return False


@lru_cache(maxsize=1)
def _monospace_family() -> str:
    """Register Consolas on Windows; use Qt's fixed-width fallback elsewhere."""
    if sys.platform == "win32":
        from pathlib import Path

        font_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "consola.ttf"
        if font_path.exists():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                return families[0]
    fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
    return fixed or "monospace"


def _eye_path(width: float, height: float) -> QPainterPath:
    path = QPainterPath()
    cy = height * 0.5
    path.moveTo(width * 0.055, cy)
    path.cubicTo(width * 0.23, height * 0.075,
                 width * 0.77, height * 0.075,
                 width * 0.945, cy)
    path.cubicTo(width * 0.77, height * 0.925,
                 width * 0.23, height * 0.925,
                 width * 0.055, cy)
    path.closeSubpath()
    return path


def _curve(start: QPointF, control1: QPointF, control2: QPointF,
           end: QPointF) -> QPainterPath:
    path = QPainterPath(start)
    path.cubicTo(control1, control2, end)
    return path


class SpectralEyeRenderer:
    """Cached QPainter eye silhouette with small animated spectral details."""

    _CACHE_LIMIT = 8

    def __init__(self, glow_strength: float = 0.82, rune_count: int = 10,
                 smoke_density: float = 0.62) -> None:
        self.glow_strength = _clamp(glow_strength)
        self.rune_count = max(0, min(12, int(rune_count)))
        self.smoke_density = _clamp(smoke_density)
        self._base_cache: OrderedDict[tuple[int, int, bool, int, str], QPixmap] = OrderedDict()
        self._iris_cache: OrderedDict[tuple[int, int, int, bool], QPixmap] = OrderedDict()
        self._rune_cache: OrderedDict[tuple[int, int, bool], QPixmap] = OrderedDict()
        self._font_cache: OrderedDict[int, QFont] = OrderedDict()
        self._text_cache: OrderedDict[tuple[str, int], QStaticText] = OrderedDict()
        self._font_family = _monospace_family()

    def _font(self, pixel_size: int) -> QFont:
        pixel_size = max(5, int(pixel_size))
        cached = self._font_cache.get(pixel_size)
        if cached is not None:
            self._font_cache.move_to_end(pixel_size)
            return cached
        font = QFont(self._font_family)
        font.setBold(True)
        font.setPixelSize(pixel_size)
        self._font_cache[pixel_size] = font
        self._font_cache.move_to_end(pixel_size)
        while len(self._font_cache) > 12:
            self._font_cache.popitem(last=False)
        return font

    def _static_text(self, text: str, pixel_size: int) -> QStaticText:
        key = (text, max(5, int(pixel_size)))
        cached = self._text_cache.get(key)
        if cached is not None:
            self._text_cache.move_to_end(key)
            return cached
        static_text = QStaticText(text)
        static_text.setTextFormat(Qt.TextFormat.PlainText)
        static_text.setPerformanceHint(QStaticText.PerformanceHint.ModerateCaching)
        static_text.prepare(QTransform(), self._font(key[1]))
        self._text_cache[key] = static_text
        self._text_cache.move_to_end(key)
        while len(self._text_cache) > 64:
            self._text_cache.popitem(last=False)
        return static_text

    @property
    def cached_size_count(self) -> int:
        return len(self._base_cache)

    def _base_pixmap(self, width: int, height: int, light_theme: bool,
                     style: str) -> QPixmap:
        glow_level = round(self.glow_strength * 100)
        key = (width, height, light_theme, glow_level, style)
        cached = self._base_cache.get(key)
        if cached is not None:
            self._base_cache.move_to_end(key)
            return cached

        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        path = _eye_path(width, height)
        cx, cy = width * 0.5, height * 0.5
        strength = self.glow_strength

        shadow = QTransform()
        shadow.translate(cx, cy + height * 0.025)
        shadow.scale(1.055, 1.20)
        shadow.translate(-cx, -cy)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(11, 31, 42, 108))
        painter.drawPath(shadow.map(path))

        if style == "spectral":
            for width_fraction, opacity in ((0.105, 25), (0.060, 53)):
                painter.setPen(QPen(QColor(95, 230, 240,
                                            round(opacity * strength)),
                                    max(2.0, height * width_fraction),
                                    Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap,
                                    Qt.PenJoinStyle.RoundJoin))
                painter.drawPath(path)

        sclera_alpha = 51 if style == "spectral" else 224
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(223, 251, 255, sclera_alpha))
        painter.drawPath(path)

        painter.save()
        painter.setClipPath(path)
        shade = QLinearGradient(0, 0, 0, height * 0.53)
        shade.setColorAt(0.0, QColor(11, 31, 42, 108 if style == "spectral" else 70))
        shade.setColorAt(1.0, QColor(11, 31, 42, 0))
        painter.fillRect(QRectF(0, 0, width, height * 0.54), shade)
        painter.restore()

        # One fine dark matte line plus a pale core keeps the contour legible on
        # both extremes without outlining individual ASCII characters.
        matte = QTransform()
        matte.translate(cx, cy)
        matte.scale(1.008, 1.018)
        matte.translate(-cx, -cy)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(11, 31, 42, 238), max(1.0, height * 0.004),
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(matte.map(path))
        painter.setPen(QPen(QColor("#BFFBFF"), max(2.5, height * 0.010),
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)

        if style == "vector":
            painter.setPen(QPen(QColor(30, 143, 163, 155), max(1.0, height * 0.006)))
            lower = _curve(QPointF(width * 0.22, height * 0.71),
                           QPointF(width * 0.39, height * 0.83),
                           QPointF(width * 0.61, height * 0.83),
                           QPointF(width * 0.78, height * 0.71))
            painter.drawPath(lower)
        painter.end()

        self._base_cache[key] = pixmap
        self._base_cache.move_to_end(key)
        while len(self._base_cache) > self._CACHE_LIMIT:
            self._base_cache.popitem(last=False)
        return pixmap

    def _iris_pixmap(self, eye_height: float, happiness: float, stress: float,
                     curiosity: float, light_theme: bool) -> QPixmap:
        diameter = max(1, round(eye_height * 0.60))
        happiness_bucket = round(_clamp(happiness) * 16)
        pupil_radius = eye_height * (0.60 * 0.5) * (
            0.38 + 0.17 * _clamp(stress) + 0.035 * _clamp(curiosity))
        pupil_radius = min(eye_height * 0.22, pupil_radius)
        pupil_radius = max(1.0, round(pupil_radius))
        key = (diameter, happiness_bucket, int(pupil_radius), light_theme)
        cached = self._iris_cache.get(key)
        if cached is not None:
            self._iris_cache.move_to_end(key)
            return cached

        pixmap = QPixmap(diameter, diameter)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = diameter * 0.5
        iris = self._iris_color(happiness_bucket / 16.0, light_theme)
        gradient = QRadialGradient(QPointF(radius - radius * 0.20,
                                           radius - radius * 0.28),
                                   radius * 1.55)
        gradient.setColorAt(0.0, QColor(115, 228, 235))
        gradient.setColorAt(0.40, iris.lighter(122))
        gradient.setColorAt(0.78, iris)
        gradient.setColorAt(1.0, QColor(13, 56, 71))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(191, 251, 255, 215), max(1.0, eye_height * 0.009)))
        painter.drawEllipse(QRectF(0, 0, diameter, diameter))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(191, 251, 255, 190), max(1.0, eye_height * 0.008)))
        inset = diameter * 0.16
        painter.drawEllipse(QRectF(inset, inset, diameter - inset * 2,
                                   diameter - inset * 2))
        pupil_diameter = pupil_radius * 2
        pupil_rect = QRectF(radius - pupil_radius, radius - pupil_radius,
                            pupil_diameter, pupil_diameter)
        painter.setBrush(QColor("#0A1A22"))
        painter.setPen(QPen(QColor(4, 20, 27, 245), max(1.0, eye_height * 0.008)))
        painter.drawEllipse(pupil_rect)
        self._draw_highlight(painter, radius - eye_height * 0.10,
                             radius - eye_height * 0.11,
                             eye_height * 0.12, eye_height * 0.16)
        self._draw_highlight(painter, radius + eye_height * 0.07,
                             radius + eye_height * 0.035,
                             eye_height * 0.07, eye_height * 0.095)
        painter.end()

        self._iris_cache[key] = pixmap
        self._iris_cache.move_to_end(key)
        while len(self._iris_cache) > 16:
            self._iris_cache.popitem(last=False)
        return pixmap

    def _rune_pixmap(self, eye_height: float, count: int,
                     light_theme: bool) -> QPixmap:
        diameter = max(24, round(eye_height * 0.88))
        key = (diameter, max(0, count), light_theme)
        cached = self._rune_cache.get(key)
        if cached is not None:
            self._rune_cache.move_to_end(key)
            return cached

        pixmap = QPixmap(diameter, diameter)
        pixmap.fill(Qt.GlobalColor.transparent)
        if count > 0:
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setPen(QColor("#1E8FA3" if light_theme else "#5FE6F0"))
            font_size = max(6, round(eye_height * 0.074))
            radius = eye_height * 0.60 * 0.5 * 1.28
            cx = cy = diameter * 0.5
            glyphs = "+.:*o"
            for index in range(count):
                angle = math.tau * index / count
                px = cx + math.cos(angle) * radius
                py = cy + math.sin(angle) * radius
                static_text = self._static_text(glyphs[index % len(glyphs)],
                                                font_size)
                size = static_text.size()
                painter.drawStaticText(QPointF(px - size.width() * 0.5,
                                               py - size.height() * 0.5),
                                       static_text)
            painter.end()

        self._rune_cache[key] = pixmap
        self._rune_cache.move_to_end(key)
        while len(self._rune_cache) > 8:
            self._rune_cache.popitem(last=False)
        return pixmap

    def draw(self, image, state: VisualState, now: float, opening: float,
             gaze: tuple[float, float], *, style: str = "spectral") -> None:
        if image.isNull() or style not in {"spectral", "vector"}:
            return
        image_width, image_height = image.width(), image.height()
        eye_height = max(1, min(round(image_height * 0.78), round(image_width * 0.82 / 2)))
        eye_width = eye_height * 2
        x = (image_width - eye_width) / 2
        y = (image_height - eye_height) / 2
        light_theme = windows_uses_light_theme()
        base = self._base_pixmap(eye_width, eye_height, light_theme, style)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.drawPixmap(QRectF(x, y, eye_width, eye_height),
                           base, QRectF(base.rect()))

        local = QRectF(x, y, eye_width, eye_height)
        eye_path = _eye_path(eye_width, eye_height).translated(x, y)
        opening = _clamp(opening)
        emotion = state.emotion
        sleeping = emotion == "dormindo"
        center_x = local.center().x() + _clamp(gaze[0], -1.0, 1.0) * eye_width * 0.026
        center_y = local.center().y() + _clamp(gaze[1], -1.0, 1.0) * eye_height * 0.045
        stress = _clamp(state.stress)
        jitter = math.sin(now * 19.0) * stress * (eye_height * 0.008
                                                  if emotion == "estressado"
                                                  else eye_height * 0.0015)
        center_x += jitter

        if sleeping or opening < 0.105:
            painter.save()
            painter.setClipPath(eye_path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(11, 31, 42, 116 if style == "spectral" else 60))
            painter.drawPath(eye_path)
            painter.restore()
            self._draw_closed_lid(painter, local, state, now)
            if style == "spectral" and sleeping:
                self._draw_sleep_z(painter, local, now, light_theme)
            painter.end()
            return

        visible_height = eye_height * max(0.10, opening)
        top_cover = (eye_height - visible_height) * 0.5
        painter.save()
        painter.setClipPath(eye_path)
        painter.setPen(Qt.PenStyle.NoPen)
        lid_color = QColor(11, 31, 42, round(120 * (1.0 - opening)))
        painter.setBrush(lid_color)
        if top_cover > 0.5:
            painter.drawRect(QRectF(x, y, eye_width, top_cover + 2))
            painter.drawRect(QRectF(x, y + eye_height - top_cover - 2,
                                    eye_width, top_cover + 2))
        painter.setClipRect(QRectF(x, y + top_cover, eye_width, visible_height),
                            Qt.ClipOperation.IntersectClip)

        iris_diameter = eye_height * 0.60
        iris_radius = iris_diameter * 0.5
        iris_center_y = center_y + eye_height * (0.02 if emotion == "triste" else 0.0)
        iris_rect = QRectF(center_x - iris_radius,
                           iris_center_y - iris_radius * min(1.0, opening),
                           iris_diameter, iris_diameter * min(1.0, opening))
        iris_pixmap = self._iris_pixmap(eye_height, state.happiness,
                                        state.stress, state.curiosity,
                                        light_theme)
        painter.drawPixmap(iris_rect, iris_pixmap, QRectF(iris_pixmap.rect()))

        if style == "spectral":
            blink_fade = _clamp((opening - 0.10) / 0.55)
            self._draw_runes(painter, center_x, iris_center_y, eye_height,
                             now, state, blink_fade, light_theme)

        if emotion in {"feliz", "alegre"} or state.affection > 0.72:
            self._draw_blush(painter, local, eye_height, state.affection)
        if emotion == "triste":
            self._draw_tear(painter, center_x + iris_radius * 0.92,
                            iris_center_y + iris_radius * 0.25, eye_height)

        painter.restore()
        if style == "spectral":
            self._draw_smoke(painter, local, now, state, light_theme)
            self._draw_spikes(painter, center_x, iris_center_y, iris_radius,
                              eye_height, now, state)
        self._draw_lid_lines(painter, local, opening, emotion)
        painter.end()

    @staticmethod
    def _iris_color(happiness: float, light_theme: bool) -> QColor:
        target = QColor("#2E9DB3" if light_theme else "#39B6C6")
        base = QColor("#1A6374")
        amount = _clamp(happiness)
        return QColor(round(base.red() + (target.red() - base.red()) * amount),
                      round(base.green() + (target.green() - base.green()) * amount),
                      round(base.blue() + (target.blue() - base.blue()) * amount))

    @staticmethod
    def _draw_highlight(painter: QPainter, cx: float, cy: float,
                        white_diameter: float, outer_diameter: float) -> None:
        painter.setPen(QPen(QColor(10, 26, 34, 225), max(1.0, outer_diameter * 0.12)))
        painter.setBrush(QColor(10, 26, 34, 205))
        painter.drawEllipse(QRectF(cx - outer_diameter * 0.5,
                                   cy - outer_diameter * 0.5,
                                   outer_diameter, outer_diameter))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(cx - white_diameter * 0.5,
                                   cy - white_diameter * 0.5,
                                   white_diameter, white_diameter))

    def _draw_runes(self, painter: QPainter, cx: float, cy: float,
                    eye_height: float, now: float,
                    state: VisualState, fade: float,
                    light_theme: bool) -> None:
        if self.rune_count <= 0 or fade <= 0.01:
            return
        if eye_height < 96:
            count = min(6, self.rune_count)
        elif eye_height < 192:
            count = min(8, self.rune_count)
        else:
            count = self.rune_count
        rate = _clamp(state.firing_rate / 20.0)
        pulse = 0.56 + 0.25 * math.sin(now * 1.35) + 0.19 * rate
        phase = now * 0.075
        rune_pixmap = self._rune_pixmap(eye_height, count, light_theme)
        painter.save()
        painter.setOpacity(_clamp(pulse * fade))
        painter.translate(cx, cy)
        painter.rotate(math.degrees(phase))
        painter.drawPixmap(-rune_pixmap.width() * 0.5,
                           -rune_pixmap.height() * 0.5, rune_pixmap)
        painter.restore()

    def _draw_smoke(self, painter: QPainter, bounds: QRectF, now: float,
                    state: VisualState, light_theme: bool) -> None:
        eye_height = bounds.height()
        if eye_height < 45 or self.smoke_density <= 0.01:
            return
        drive = _clamp(0.28 + 0.45 * state.stress + 0.27 * (1.0 - state.energy))
        density = self.smoke_density * drive
        max_count = 2 if eye_height < 96 else (4 if eye_height < 192 else 7)
        count = max(1, min(max_count, round(max_count * density)))
        color = QColor("#1E8FA3" if light_theme else "#5FE6F0")
        font_size = max(5, round(eye_height * 0.074))
        glyphs = ":.*"
        for index in range(count):
            phase = (now * 0.14 + index / count) % 1.0
            side = -1.0 if index % 2 == 0 else 1.0
            base_x = bounds.center().x() + side * bounds.width() * (0.40 + 0.035 * (index % 3))
            drift = math.sin(now * 0.38 + index * 1.7) * eye_height * 0.035
            rise = phase * eye_height * 0.16
            if index % 3 == 0:
                py = bounds.top() - rise - eye_height * 0.035
            else:
                py = bounds.bottom() + rise
            alpha = round(210 * density * (1.0 - phase) * (0.56 if index else 0.80))
            painter.setPen(QColor(color.red(), color.green(), color.blue(), alpha))
            painter.drawStaticText(QPointF(base_x + drift, py),
                                   self._static_text(glyphs[index % len(glyphs)],
                                                     font_size))

    def _draw_spikes(self, painter: QPainter, cx: float, cy: float,
                     iris_radius: float, eye_height: float, now: float,
                     state: VisualState) -> None:
        for index, neuron_id in enumerate(state.spike_ids[:8]):
            angle = (int(neuron_id) * 2.399963229728653 + now * 0.28)
            radius = iris_radius * (1.42 + 0.06 * math.sin(now * 2.0 + index))
            px = cx + math.cos(angle) * radius
            py = cy + math.sin(angle) * radius * 0.85
            size = max(1.0, eye_height * 0.009)
            alpha = round(100 + 110 * (0.5 + 0.5 * math.sin(now * 2.3 + index)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(95, 230, 240, alpha))
            painter.drawEllipse(QRectF(px - size, py - size, size * 2, size * 2))

    @staticmethod
    def _draw_blush(painter: QPainter, bounds: QRectF, eye_height: float,
                    affection: float) -> None:
        opacity = round(45 + 50 * _clamp(affection))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 155, 191, opacity))
        radius = eye_height * 0.025
        for side in (-1, 1):
            cx = bounds.center().x() + side * bounds.width() * 0.34
            cy = bounds.center().y() + eye_height * 0.20
            painter.drawEllipse(QRectF(cx - radius * 1.8, cy - radius,
                                       radius * 3.6, radius * 2))

    @staticmethod
    def _draw_tear(painter: QPainter, x: float, y: float, eye_height: float) -> None:
        r = eye_height * 0.025
        tear = QPainterPath(QPointF(x, y - r))
        tear.cubicTo(x - r * 1.15, y + r * 0.25,
                     x - r * 0.60, y + r * 1.65, x, y + r * 1.65)
        tear.cubicTo(x + r * 0.60, y + r * 1.65,
                     x + r * 1.15, y + r * 0.25, x, y - r)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#9CECF2"))
        painter.drawPath(tear)

    @staticmethod
    def _draw_lid_lines(painter: QPainter, bounds: QRectF,
                        opening: float, emotion: str) -> None:
        w, h = bounds.width(), bounds.height()
        x, y = bounds.x(), bounds.y()
        path = QPainterPath()
        y_peak = y + h * (0.06 + 0.10 * (1.0 - opening))
        left = QPointF(x + w * 0.08, y + h * 0.48)
        right = QPointF(x + w * 0.92, y + h * 0.48)
        path.moveTo(left)
        path.cubicTo(QPointF(x + w * 0.27, y_peak),
                     QPointF(x + w * 0.73, y_peak), right)
        color = QColor("#BFFBFF")
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, max(1.2, h * 0.010),
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(path)
        if emotion in {"feliz", "alegre"}:
            smile = _curve(QPointF(x + w * 0.25, y + h * 0.77),
                           QPointF(x + w * 0.40, y + h * 0.88),
                           QPointF(x + w * 0.60, y + h * 0.88),
                           QPointF(x + w * 0.75, y + h * 0.77))
            painter.setPen(QPen(QColor(191, 251, 255, 155), max(1.0, h * 0.007),
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(smile)

    def _draw_closed_lid(self, painter: QPainter, bounds: QRectF,
                         state: VisualState, now: float) -> None:
        w, h = bounds.width(), bounds.height()
        x, y = bounds.x(), bounds.y()
        line_y = y + h * 0.47
        arc = _curve(QPointF(x + w * 0.055, line_y),
                     QPointF(x + w * 0.27, y + h * 0.63),
                     QPointF(x + w * 0.73, y + h * 0.63),
                     QPointF(x + w * 0.945, line_y))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#BFFBFF"), max(2.2, h * 0.012),
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(arc)
        lower = _curve(QPointF(x + w * 0.19, line_y + h * 0.11),
                       QPointF(x + w * 0.40, line_y + h * 0.18),
                       QPointF(x + w * 0.60, line_y + h * 0.18),
                       QPointF(x + w * 0.81, line_y + h * 0.11))
        painter.setPen(QPen(QColor(95, 230, 240, 115), max(1.0, h * 0.006),
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(lower)

    def _draw_sleep_z(self, painter: QPainter, bounds: QRectF,
                      now: float, light_theme: bool) -> None:
        h = bounds.height()
        font_size = max(8, round(h * 0.10))
        color = QColor("#1E8FA3" if light_theme else "#5FE6F0")
        for index in range(3):
            progress = (now * 0.13 + index * 0.28) % 1.0
            px = bounds.center().x() + h * (0.20 + index * 0.11)
            # Keep the rising Zs inside the image even in the compact PET
            # window, where the margin above the eye is only a few pixels.
            py = bounds.top() + h * (0.08 - progress * 0.12)
            alpha = round(85 + 135 * (1.0 - progress))
            painter.setPen(QColor(color.red(), color.green(), color.blue(), alpha))
            painter.drawStaticText(QPointF(px, py), self._static_text("z", font_size))

from __future__ import annotations

import ctypes
from datetime import datetime
import math
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..runtime.visual_state import StateAnimator, VisualState
from .interaction import AffectionDragTracker


Color = tuple[int, int, int]


def _mix(first: Color, second: Color, amount: float) -> Color:
    amount = max(0.0, min(1.0, amount))
    return tuple(round(a + (b - a) * amount) for a, b in zip(first, second))


def _smoothstep(low: float, high: float, value: float) -> float:
    if high <= low:
        return float(value >= high)
    t = max(0.0, min(1.0, (value - low) / (high - low)))
    return t * t * (3.0 - 2.0 * t)


def _focused_caret_screen_position() -> tuple[int, int] | None:
    """Read only the foreground caret rectangle; never reads keys or text."""
    if sys.platform != "win32":
        return None
    try:
        from ctypes import wintypes

        class GuiThreadInfo(ctypes.Structure):
            _fields_ = (
                ("cbSize", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT),
            )

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetGUIThreadInfo.argtypes = (wintypes.DWORD, ctypes.POINTER(GuiThreadInfo))
        user32.GetGUIThreadInfo.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
        user32.ClientToScreen.restype = wintypes.BOOL
        info = GuiThreadInfo()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetGUIThreadInfo(0, ctypes.byref(info)) or not info.hwndCaret:
            return None
        point = wintypes.POINT(
            int((info.rcCaret.left + info.rcCaret.right) / 2),
            int((info.rcCaret.top + info.rcCaret.bottom) / 2),
        )
        if not user32.ClientToScreen(info.hwndCaret, ctypes.byref(point)):
            return None
        return int(point.x), int(point.y)
    except Exception:
        return None


class AnimatedAsciiEyeWidget(QWidget):
    """Direct character-grid eye and parallax scene for the live Qt window."""

    petRequested = Signal()
    panelRequested = Signal()
    activityDetected = Signal()
    animationStarted = Signal()
    CELL_WIDTH = 8
    CELL_HEIGHT = 8
    GLYPHS = "".join(chr(codepoint) for codepoint in range(32, 127)) + "♥"

    def __init__(self, columns: int = 100, rows: int = 56,
                 scene_time: str = "auto", design: str = "A",
                 max_particles: int = 8,
                 parent: QWidget | None = None,
                 max_columns: int = 170, max_rows: int = 96,
                 affection_drag_min_s: float = 1.0,
                 compact: bool = False) -> None:
        super().__init__(parent)
        self.compact = bool(compact)
        min_columns = 28 if self.compact else 72
        min_rows = 16 if self.compact else 42
        self.base_columns = max(min_columns, min(240, int(columns)))
        self.base_rows = max(min_rows, min(135, int(rows)))
        self.max_columns = max(self.base_columns, min(300, int(max_columns)))
        self.max_rows = max(self.base_rows, min(180, int(max_rows)))
        self.columns = self.base_columns
        self.rows = self.base_rows
        self.scene_time = str(scene_time).strip().lower()
        self.design = "B" if str(design).strip().upper() == "B" else "A"
        self.max_particles = max(0, min(48, int(max_particles)))
        self.setMinimumSize(80, 52) if self.compact else self.setMinimumSize(700, 390)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setToolTip(
            "Clique duas vezes para abrir o painel; clique direito para opções. "
            f"Mova para direcionar o olhar; arraste sobre o olho por "
            f"{affection_drag_min_s:g}s ou use CARINHO.")

        self.target_state = VisualState()
        self.state = self.target_state
        self.animator = StateAnimator(self.state, seconds=0.24)
        self.mode = "ascii"
        self.rendered_frames = 0
        self.gaze_target = (0.0, 0.0)
        self.gaze = (0.0, 0.0)
        self._last_pointer: tuple[int, int] | None = None
        self._last_pointer_move = 0.0
        self._next_caret_poll = 0.0
        self._last_caret_position: tuple[int, int] | None = None
        self._typing_look_until = 0.0
        self._last_glance = (0.0, 0.0)
        self._attention_source = "idle"
        self._sparkle_until = 0.0
        self._attention_anim_until = 0.0
        self._opening = 0.84
        self._last_time = 0.0
        self._drag_tracker = AffectionDragTracker(affection_drag_min_s)
        self._rng = random.Random()
        self._next_glance = time.monotonic() + self._rng.uniform(1.0, 2.4)
        self._next_blink = time.monotonic() + self._rng.uniform(1.8, 3.2)
        self._blink_started: float | None = None
        self._blink_duration = 0.19
        self._last_frame = QImage()
        self._glyph_ids, self._glyph_atlas = self._build_glyph_atlas()
        self._glyph_lut = np.zeros(0x10000, dtype=np.uint8)
        for glyph, index in self._glyph_ids.items():
            self._glyph_lut[ord(glyph)] = index
        self._stars = tuple(
            (self._rng.randrange(2, self.columns - 2),
             self._rng.randrange(4, max(8, self.rows // 2 - 1)),
             self._rng.random() * math.tau,
             self._rng.uniform(0.55, 1.55))
            for _ in range(max(32, self.columns // 2)))
        self._resize_resolution()

    def _build_glyph_atlas(self) -> tuple[dict[str, int], np.ndarray]:
        font_root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        font = None
        for name in ("consola.ttf", "cour.ttf", "lucon.ttf"):
            path = font_root / name
            if path.exists():
                font = ImageFont.truetype(str(path), self.CELL_HEIGHT)
                break
        if font is None:
            try:
                font = ImageFont.truetype("DejaVuSansMono.ttf", self.CELL_HEIGHT)
            except OSError:
                font = ImageFont.load_default()
        masks = []
        for glyph in self.GLYPHS:
            tile = Image.new("L", (self.CELL_WIDTH, self.CELL_HEIGHT), 0)
            ImageDraw.Draw(tile).text((1, -1), glyph, fill=255, font=font)
            masks.append(np.asarray(tile, dtype=np.uint8) > 32)
        return ({glyph: index for index, glyph in enumerate(self.GLYPHS)},
                np.stack(masks))

    def _resize_resolution(self) -> None:
        if not hasattr(self, "_stars") or self.width() <= 1 or self.height() <= 1:
            return
        dpr = max(1.0, float(self.devicePixelRatioF()))
        physical_width = max(1, round(self.width() * dpr))
        physical_height = max(1, round(self.height() * dpr))
        columns = max(28 if self.compact else 72, min(
            self.max_columns,
            round(physical_width / self.CELL_WIDTH * self.base_columns / 100.0),
        ))
        rows = max(16 if self.compact else 42, min(
            self.max_rows,
            round(physical_height / self.CELL_HEIGHT * self.base_rows / 56.0),
        ))
        if (columns, rows) == (self.columns, self.rows):
            return
        self.columns, self.rows = columns, rows
        self._stars = tuple(
            (self._rng.randrange(2, self.columns - 2),
             self._rng.randrange(4, max(8, self.rows // 2 - 1)),
             self._rng.random() * math.tau,
             self._rng.uniform(0.55, 1.55))
            for _ in range(max(32, self.columns // 2)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_resolution()

    def event(self, event) -> bool:
        result = super().event(event)
        if event.type() in {QEvent.Type.DevicePixelRatioChange,
                            QEvent.Type.ScreenChangeInternal}:
            self._resize_resolution()
            self.update()
        return result

    def _gaze_for_global(self, point) -> tuple[float, float]:
        local = self.mapFromGlobal(point)
        return (
            max(-1.0, min(1.0, local.x() / max(1, self.width()) * 2.0 - 1.0)),
            max(-1.0, min(1.0, local.y() / max(1, self.height()) * 2.0 - 1.0)),
        )

    def _update_attention(self, now: float) -> None:
        pointer = QCursor.pos()
        position = (pointer.x(), pointer.y())
        if self._last_pointer is None:
            self._last_pointer = position
        elif position != self._last_pointer:
            self._last_pointer = position
            self._last_pointer_move = now
            self.gaze_target = self._gaze_for_global(pointer)
            self._attention_source = "mouse"
            self.activityDetected.emit()

        if now - self._last_pointer_move < 1.25:
            return

        if self.state.emotion == "curioso":
            if now >= self._next_caret_poll:
                self._next_caret_poll = now + 0.12
                caret = _focused_caret_screen_position()
                if caret is None:
                    self._last_caret_position = None
                    self._typing_look_until = 0.0
                elif self._last_caret_position is None:
                    self._last_caret_position = caret
                elif caret != self._last_caret_position:
                    self._last_caret_position = caret
                    self._typing_look_until = now + 1.8
                    self._attention_anim_until = max(self._attention_anim_until, now + 0.55)
                    self.activityDetected.emit()
            if (self._last_caret_position is not None
                    and now < self._typing_look_until):
                from PySide6.QtCore import QPoint

                self.gaze_target = self._gaze_for_global(QPoint(*self._last_caret_position))
                self._attention_source = "typing"
                return
        else:
            self._typing_look_until = 0.0

        if now < self._next_glance:
            return
        glances = (
            (-0.82, -0.72), (0.78, -0.68), (-0.92, -0.10), (0.91, 0.12),
            (-0.74, 0.58), (0.76, 0.62), (0.02, -0.82), (-0.04, 0.78),
        )
        choices = tuple(point for point in glances if point != self._last_glance)
        target = self._rng.choice(choices or glances)
        self._last_glance = target
        self.gaze_target = target
        self._attention_source = "wander"
        self._next_glance = now + self._rng.uniform(2.0, 4.4)
        self._attention_anim_until = max(self._attention_anim_until, now + 0.85)
        self.animationStarted.emit()
        if self._rng.random() < 0.42:
            self._sparkle_until = now + self._rng.uniform(0.45, 0.9)
        if self._rng.random() < 0.18 and self._blink_started is None:
            self._blink_started = now
            self._blink_duration = self._rng.uniform(0.30, 0.40)
            self._next_blink = now + self._blink_duration + 0.18
            self._attention_anim_until = max(
                self._attention_anim_until, now + self._blink_duration)

    def set_state(self, state: VisualState) -> None:
        if state.emotion != self.target_state.emotion:
            now = time.monotonic()
            self._attention_anim_until = max(self._attention_anim_until, now + 0.65)
            self.activityDetected.emit()
        self.target_state = state
        self.update()

    @property
    def attention_animating(self) -> bool:
        now = time.monotonic()
        blinking = (self._blink_started is not None
                    and now < self._blink_started + self._blink_duration)
        return now < self._attention_anim_until or blinking

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in {"ascii", "hud", "pet"} else "ascii"
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, self.mode != "pet")
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if (self.mode == "pet"
                and event.button() == Qt.MouseButton.LeftButton):
            self.panelRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:
        point = event.globalPosition().toPoint()
        self._last_pointer = (point.x(), point.y())
        self._last_pointer_move = time.monotonic()
        self._attention_source = "mouse"
        self.gaze_target = self._gaze_for_global(point)
        local = event.position()
        if self._drag_tracker.move(
                local.x(), local.y(), self.width(), self.height(),
                bool(event.buttons() & Qt.MouseButton.LeftButton)):
            self.petRequested.emit()
        self.activityDetected.emit()
        self.update()
        super().mouseMoveEvent(event)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)

    def mousePressEvent(self, event) -> None:
        local = event.position()
        self._drag_tracker.press(
            local.x(), local.y(), self.width(), self.height(),
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

    def _cycle(self, local_time: datetime) -> tuple[dict[str, Color], float, float, str]:
        hour = (local_time.hour + local_time.minute / 60.0
                + local_time.second / 3600.0)
        sun_height = math.cos((hour - 12.0) * math.pi / 12.0)
        daylight = _smoothstep(-0.12, 0.22, sun_height)
        twilight = max(0.0, 1.0 - abs(sun_height) / 0.36) ** 1.5
        setting = self.scene_time
        if setting in {"dia", "day"}:
            daylight, twilight = 1.0, 0.0
            label = "DIA"
        elif setting in {"noite", "night"}:
            daylight, twilight = 0.0, 0.0
            label = "NOITE"
        elif setting in {"entardecer", "dusk", "sunset"}:
            daylight, twilight = 0.0, 1.0
            label = "ENTARDECER"
        elif twilight > 0.27:
            label = "AMANHECER" if hour < 12.0 else "ENTARDECER"
        else:
            label = "DIA" if daylight >= 0.42 else "NOITE"

        night_sky = (5, 10, 21)
        day_sky = (25, 48, 61)
        dusk_sky = (31, 21, 42)
        sky = _mix(_mix(night_sky, dusk_sky, twilight * 0.92), day_sky, daylight)
        night_hill = (18, 43, 57)
        day_hill = (37, 76, 83)
        dusk_hill = (59, 49, 74)
        palette = {
            "sky": sky,
            "star": _mix((63, 160, 184), (154, 196, 186), daylight * 0.8),
            "moon": (202, 218, 211),
            "sun": (250, 201, 119),
            "cloud": _mix((47, 91, 112), (106, 151, 157), daylight * 0.72),
            "far_hill": _mix(_mix(night_hill, dusk_hill, twilight), day_hill, daylight),
            "near_hill": _mix((12, 29, 43), (24, 53, 61), daylight),
            "water": _mix((20, 59, 77), (45, 97, 102), daylight),
            "sclera": _mix((82, 144, 157), (109, 165, 176), daylight * 0.55),
            "iris": (59, 189, 199),
            "iris_dark": (29, 112, 133),
            "amber": (243, 190, 106),
            "rose": (234, 143, 177),
            "white": (252, 250, 238),
            "pupil": (9, 29, 40),
            "ink": (38, 83, 101),
            "accent": _mix((49, 183, 194), (66, 154, 157), daylight * 0.32),
        }
        return palette, daylight, twilight, label

    def _new_grid(self, sky: Color) -> tuple[list[list[str]], list[list[Color]]]:
        chars = [[" " for _ in range(self.columns)] for _ in range(self.rows)]
        colors = [[sky for _ in range(self.columns)] for _ in range(self.rows)]
        return chars, colors

    def _put(self, chars: list[list[str]], colors: list[list[Color]],
             x: int, y: int, char: str, color: Color) -> None:
        if 0 <= x < self.columns and 0 <= y < self.rows and char:
            chars[y][x] = char[0]
            colors[y][x] = color

    def _text(self, chars: list[list[str]], colors: list[list[Color]],
              x: int, y: int, value: str, color: Color,
              limit: int | None = None) -> None:
        text = value if limit is None else value[:limit]
        for index, char in enumerate(text):
            self._put(chars, colors, x + index, y, char, color)

    def _draw_sky(self, chars: list[list[str]], colors: list[list[Color]],
                  palette: dict[str, Color], daylight: float,
                  twilight: float, label: str, local_time: datetime,
                  now: float) -> None:
        night_factor = max(0.04, 1.0 - daylight * 0.94)
        for index, (x, y, phase, speed) in enumerate(self._stars):
            if y < 4 or (x < 21 and y < 7):
                continue
            twinkle = 0.32 + 0.68 * (0.5 + 0.5 * math.sin(now * speed + phase))
            color = _mix(palette["sky"], palette["star"], night_factor * twinkle)
            glyph = "+" if index % 13 == 0 and twinkle > 0.62 else "."
            self._put(chars, colors, x, y, glyph, color)

        hour = local_time.hour + local_time.minute / 60.0
        if daylight > 0.08 or twilight > 0.64:
            progress = max(0.0, min(1.0, (hour - 5.0) / 14.0))
            sx = round(self.columns * (0.20 + 0.60 * progress))
            sy = round(self.rows * 0.18 - self.rows * 0.06 * math.sin(math.pi * progress))
            if self.scene_time in {"entardecer", "dusk", "sunset"}:
                sx = round(self.columns * 0.23)
            sun_color = _mix(palette["sky"], palette["sun"], max(daylight, twilight * 0.76))
            for dx, dy, glyph in ((0, 0, "@"), (-1, 0, "+"), (1, 0, "+"),
                                  (0, -1, "+"), (0, 1, "+"), (-1, -1, "."),
                                  (1, 1, ".")):
                self._put(chars, colors, sx + dx, sy + dy, glyph, sun_color)
        if daylight < 0.78 and twilight < 0.84:
            moon_x = round(self.columns * (0.18 + 0.64 * ((hour + 5.0) % 24.0) / 24.0))
            moon_y = 10
            moon_color = _mix(palette["sky"], palette["moon"], night_factor * 0.90)
            for dy, glyph in ((-2, "."), (-1, ")"), (0, ")"), (1, ")"), (2, ".")):
                self._put(chars, colors, moon_x, moon_y + dy, glyph, moon_color)
            self._put(chars, colors, moon_x - 1, moon_y, ".", moon_color)

        # Clouds drift at two parallax speeds and use only a few soft ASCII marks.
        cloud_color = _mix(palette["sky"], palette["cloud"], 0.68)
        for layer, (speed, base_y, width) in enumerate(((0.45, 12, 15), (0.27, 17, 11))):
            travel = (now * speed + layer * 39.0) % (self.columns + width)
            x0 = round(travel) - width
            outline = ".-.__.-."
            self._text(chars, colors, x0 + 2, base_y, outline, cloud_color)
            self._text(chars, colors, x0, base_y + 1, "(~~~~~)", cloud_color)
            self._text(chars, colors, x0 + 1, base_y + 2, "'-----'", cloud_color)

    def _draw_landscape(self, chars: list[list[str]], list_colors: list[list[Color]],
                        palette: dict[str, Color], daylight: float,
                        twilight: float, now: float) -> None:
        far = self.rows - 14
        near = self.rows - 10
        water_color = _mix(palette["sky"], palette["water"], 0.66)
        far_color = _mix(palette["sky"], palette["far_hill"], 0.75)
        near_color = _mix(palette["sky"], palette["near_hill"], 0.90)
        for x in range(self.columns):
            far_y = far + round(1.8 * math.sin(x * 0.15 + now * 0.07)
                                + 1.2 * math.sin(x * 0.061 + 1.8))
            slope = math.cos(x * 0.15 + now * 0.07) * 0.27
            self._put(chars, list_colors, x, far_y,
                      "/" if slope < -0.18 else "\\" if slope > 0.18 else "_", far_color)
            near_y = near + round(1.25 * math.sin(x * 0.105 + 1.0))
            near_slope = math.cos(x * 0.105 + 1.0) * 0.13
            self._put(chars, list_colors, x, near_y,
                      "/" if near_slope < -0.08 else "\\" if near_slope > 0.08 else "_",
                      near_color)

        horizon = self.rows - 7
        for x in range(2, self.columns - 2):
            self._put(chars, list_colors, x, horizon, "-", water_color)
        for band in range(4):
            y = horizon + 1 + band
            if y >= self.rows - 2:
                break
            phase = now * (0.62 + band * 0.10) + band * 1.7
            stride = 12 + band * 4
            offset = round((now * (1.4 + band * 0.26)) % stride)
            for start in range(-stride + offset, self.columns, stride):
                length = 3 + (band % 2) + int(2 * (0.5 + 0.5 * math.sin(phase + start)))
                color = _mix(palette["sky"], palette["water"],
                             0.38 + 0.13 * (0.5 + 0.5 * math.sin(phase + start * 0.3)))
                for x in range(start, min(self.columns, start + length)):
                    self._put(chars, list_colors, x, y, "~" if (x + band) % 3 else "-", color)

        firefly_factor = max(0.14, 1.0 - daylight * 0.74)
        for index in range(7):
            x = (index * 19 + round(now * (0.25 + index * 0.018))) % self.columns
            y = self.rows - 13 + round(1.6 * math.sin(now * 0.72 + index * 2.1))
            pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(now * 1.7 + index))
            color = _mix(palette["sky"], palette["amber"], firefly_factor * pulse)
            self._put(chars, list_colors, x, y, "." if pulse < 0.72 else "+", color)

    def _blink(self, now: float, emotion: str) -> float:
        if now >= self._next_blink:
            self._blink_started = now
            self._blink_duration = (0.32 if emotion == "alegre"
                                    else self._rng.uniform(0.32, 0.42))
            self._next_blink = now + (0.43 if self._rng.random() < 0.16 else
                                      self._rng.uniform(2.7, 5.2))
            self._attention_anim_until = max(
                self._attention_anim_until, now + self._blink_duration)
            self.animationStarted.emit()
        if emotion == "piscar" and self._blink_started is None:
            self._blink_started = now
            self._blink_duration = 0.34
            self._next_blink = now + 0.82
        if self._blink_started is None:
            return 0.0
        progress = (now - self._blink_started) / max(0.12, self._blink_duration)
        if progress >= 1.0:
            self._blink_started = None
            return 0.0
        return max(0.0, math.sin(math.pi * progress)) ** 1.35

    def _draw_eye(self, chars: list[list[str]], colors: list[list[Color]],
                  palette: dict[str, Color], now: float) -> None:
        emotion = self.state.emotion
        target_open = 0.76 + 0.17 * max(0.0, min(1.0, self.state.energy))
        if emotion == "alegre":
            target_open = 0.77 + 0.035 * math.sin(now * 1.2)
        elif emotion == "triste":
            target_open = 0.67
        elif emotion == "estressado":
            target_open = 0.72
        elif emotion == "curioso":
            target_open = 0.95
        elif emotion == "sonolento":
            target_open = 0.43
        elif emotion == "dormindo":
            target_open = 0.035
        elif emotion in {"aberto", "arregalado"}:
            target_open = 0.98 if emotion == "aberto" else 1.0
        elif emotion == "semicerrado":
            target_open = 0.54
        dt = (1.0 / 30.0 if self._last_time == 0.0 else
              max(0.0, min(0.5, now - self._last_time)))
        self._last_time = now
        smooth = 1.0 - math.exp(-dt / 0.18)
        self._opening += (target_open - self._opening) * smooth
        blink = self._blink(now, emotion)
        if emotion == "piscar":
            blink = max(blink, 0.94)
        opening = self._opening * (1.0 - blink * 0.98)

        gaze_blend = 1.0 - math.exp(-dt / 0.22)
        gx = self.gaze[0] + (self.gaze_target[0] - self.gaze[0]) * gaze_blend
        gy = self.gaze[1] + (self.gaze_target[1] - self.gaze[1]) * gaze_blend
        self.gaze = (gx, gy)

        breath = 1.0 + 0.012 * math.sin(now * 0.82)
        stress = max(0.0, min(1.0, self.state.stress))
        tremble = stress * (0.18 if emotion == "estressado" else 0.035)
        cx = self.columns * 0.5 + gx * 2.9 + math.sin(now * 19.0) * tremble
        cy = self.rows * 0.50 + gy * 1.45 + math.sin(now * 0.58) * 0.22
        rx = self.columns * (0.34 if self.design == "A" else 0.35) * breath
        ry = self.rows * (0.285 if self.design == "A" else 0.265) * breath

        if opening < 0.105:
            for x in range(round(cx - rx), round(cx + rx) + 1):
                u = (x - cx) / max(1.0, rx)
                arch = max(0.0, 1.0 - u * u)
                y = round(cy - 2.0 * arch)
                char = "/" if u < -0.12 else "\\" if u > 0.12 else "_"
                self._put(chars, colors, x, y, char, palette["iris"])
            for index, (xoff, glyph) in enumerate(((-2, "z"), (1, "Z"), (4, "z"))):
                bob = math.sin(now * 1.5 + index * 1.7) * 1.2
                glow = 0.58 + 0.32 * (0.5 + 0.5 * math.sin(now * 2.0 + index))
                color = _mix(palette["sky"], palette["white"], glow)
                self._put(chars, colors, round(cx + rx * 0.36 + xoff),
                          round(cy - 8 - xoff * 0.22 - bob), glyph, color)
            return

        for x in range(max(0, math.floor(cx - rx)), min(self.columns, math.ceil(cx + rx))):
            u = (x - cx) / max(1.0, rx)
            envelope = max(0.0, 1.0 - u * u) ** 0.66
            half = ry * envelope * opening
            if half < 0.55:
                continue
            top, bottom = math.ceil(cy - half), math.floor(cy + half)
            slope = -1.32 * u * (max(0.05, 1.0 - u * u) ** -0.34)
            for y in range(max(0, top), min(self.rows, bottom + 1)):
                ratio = abs((y - cy) / max(0.1, half))
                if ratio > 0.89:
                    if abs(u) > 0.88:
                        glyph = "<" if u < 0 else ">"
                    elif abs(slope) < 0.33:
                        glyph = "_"
                    elif (y < cy) == (slope < 0):
                        glyph = "\\"
                    else:
                        glyph = "/"
                    self._put(chars, colors, x, y, glyph, palette["ink"])
                else:
                    self._put(chars, colors, x, y,
                              ":" if ratio > 0.68 else ".", palette["sclera"])

        iris_radius = self.rows * (0.225 if self.design == "A" else 0.207)
        ix = cx + gx * 2.1
        iy = cy + gy * 1.0
        pupil_radius = max(3.2, min(5.3, iris_radius *
                                   (0.39 - 0.14 * stress + 0.045 * self.state.curiosity)))
        for x in range(round(ix - iris_radius), round(ix + iris_radius) + 1):
            for y in range(round(iy - iris_radius), round(iy + iris_radius) + 1):
                if not (0 <= x < self.columns and 0 <= y < self.rows):
                    continue
                u = (x - ix) / iris_radius
                v = (y - iy) / iris_radius
                radius = math.hypot(u, v)
                if radius > 1.0:
                    continue
                half = ry * max(0.0, 1.0 - ((x - cx) / rx) ** 2) ** 0.66 * opening
                if abs(y - cy) > half * 0.91:
                    continue
                dx, dy = x - ix, y - iy
                if abs(dx + 2) <= 1 and abs(dy + 3) <= 1:
                    self._put(chars, colors, x, y, "@" if (dx, dy) == (-2, -3) else ".",
                              palette["white"])
                elif abs(dx - 2) <= 1 and abs(dy - 1) <= 1 and (dx + dy) % 2 == 0:
                    self._put(chars, colors, x, y, "o", palette["white"])
                elif abs(dx - 4) <= 1 and dy == -2:
                    self._put(chars, colors, x, y, ".", palette["white"])
                elif radius <= pupil_radius / iris_radius:
                    self._put(chars, colors, x, y,
                              "@" if radius < pupil_radius * 0.55 / iris_radius else "o",
                              palette["pupil"])
                elif abs(radius - 0.91) < 0.045:
                    self._put(chars, colors, x, y, "o", palette["iris_dark"])
                elif abs(radius - 0.70) < 0.055:
                    self._put(chars, colors, x, y, ":", palette["amber"])
                elif abs(radius - 0.48) < 0.05:
                    self._put(chars, colors, x, y, "+", palette["iris"])
                else:
                    tone = (x + y) % 5
                    glyph = (".", ":", ",", ";", ":")[tone]
                    self._put(chars, colors, x, y, glyph,
                              palette["iris"] if radius < 0.68 else palette["iris_dark"])

        if self.state.affection > 0.82 or emotion == "amoroso":
            heart = (" @ @ ", "@@@@@", " @@@ ", "  @  ")
            for row_index, row in enumerate(heart):
                for column_index, glyph in enumerate(row):
                    if glyph != " ":
                        self._put(chars, colors, round(ix) - 2 + column_index,
                                  round(iy) - 2 + row_index, glyph, palette["rose"])

        # Keep two readable catchlights even at the compact character scale.
        for dx, dy in ((-3, -4), (-2, -4), (-3, -3), (-2, -3)):
            self._put(chars, colors, round(ix) + dx, round(iy) + dy,
                      "@", palette["white"])
        self._put(chars, colors, round(ix) + 2, round(iy) + 1, "o", palette["white"])
        self._put(chars, colors, round(ix) + 4, round(iy) - 2, ".", palette["white"])

        if now < self._sparkle_until:
            sparkle_phase = (self._sparkle_until - now) / 0.9
            sparkle_color = _mix(palette["sky"], palette["white"], sparkle_phase)
            self._put(chars, colors, round(ix - iris_radius * 0.88),
                      round(iy - iris_radius * 0.86), "*", sparkle_color)
            self._put(chars, colors, round(ix + iris_radius * 0.90),
                      round(iy - iris_radius * 0.58), "+", palette["amber"])

        lash_count = 3 if self.design == "A" else 4
        for index in range(lash_count):
            fraction = (index + 1) / (lash_count + 1)
            u = fraction * 1.62 - 0.81
            x = round(cx + u * rx)
            y = round(cy - ry * max(0.0, 1.0 - u * u) ** 0.66 * opening)
            glyph = "/" if u < -0.18 else "\\" if u > 0.18 else "'"
            self._put(chars, colors, x, y - 1, glyph, palette["ink"])

        if emotion == "curioso":
            brow_y = round(cy - ry - 3)
            self._text(chars, colors, round(cx - 2), brow_y, "~^~", palette["amber"])
        elif emotion == "triste":
            tear_x = round(cx + rx * 0.85)
            tear_y = round(cy + ry * 0.40 + (now * 4.2 % 2.0))
            self._put(chars, colors, tear_x, tear_y, "o", palette["iris"])
            self._put(chars, colors, tear_x, tear_y + 1, ".", palette["white"])
        elif emotion == "estressado":
            self._put(chars, colors, round(cx + rx * 0.91), round(cy - 2), "!",
                      palette["amber"])
        elif emotion == "alegre":
            for offset, glyph in ((-1, "+"), (1, "+")):
                self._put(chars, colors, round(cx + offset * rx * 1.08),
                          round(cy - ry * 0.9 - 2), glyph, palette["amber"])

        blush_strength = max(0.0, min(1.0, self.state.affection * 0.72
                                      + (0.30 if emotion in {"alegre", "amoroso"} else 0.0)))
        if blush_strength > 0.17:
            cheek_color = _mix(palette["sky"], palette["rose"], blush_strength)
            for sign in (-1, 1):
                x = round(cx + sign * (rx + 2.0))
                y = round(cy + 3.0)
                self._put(chars, colors, x, y, ".", cheek_color)
                self._put(chars, colors, x + sign, y, ".", cheek_color)

        for index, neuron_id in enumerate(self.state.spike_ids[:self.max_particles]):
            angle = neuron_id * 2.399963229728653 + now * 0.20
            radius = rx + 4.0 + 1.1 * math.sin(now * 1.7 + index)
            px = round(cx + math.cos(angle) * radius)
            py = round(cy + math.sin(angle) * radius * 0.54)
            self._put(chars, colors, px, py, "+" if index % 2 else ".",
                      palette["star"])

        if self.state.affection > 0.72:
            rise = int((now * 2.1) % 4)
            for sign in (-1, 1):
                self._put(chars, colors, round(cx + sign * rx * 0.86),
                          round(cy - ry - 3 - rise), "♥", palette["rose"])

    def _render_cells(self, chars: list[list[str]], colors: list[list[Color]],
                      background: Color, *, transparent: bool = False) -> QImage:
        cell_colors = np.asarray(colors, dtype=np.uint8)
        codepoints = np.asarray(chars, dtype="<U1").view(np.uint32)
        glyph_ids = self._glyph_lut[codepoints]
        tiles = self._glyph_atlas[glyph_ids]
        mask = tiles.transpose(0, 2, 1, 3).reshape(
            self.rows * self.CELL_HEIGHT, self.columns * self.CELL_WIDTH)
        glyph_rgb = np.repeat(np.repeat(cell_colors, self.CELL_HEIGHT, axis=0),
                              self.CELL_WIDTH, axis=1)
        output = np.zeros((*mask.shape, 4), dtype=np.uint8)
        if not transparent:
            output[:, :, :3] = background
            output[:, :, 3] = 255
        else:
            # The floating pet sits over arbitrary desktop content. A one-pixel
            # ink edge keeps pale glyphs legible on bright wallpapers without
            # changing the eye's colors or adding a solid backdrop.
            outline_mask = np.zeros_like(mask)
            outline_mask[1:, 1:] |= mask[:-1, :-1]
            outline_mask[1:, :] |= mask[:-1, :]
            outline_mask[1:, :-1] |= mask[:-1, 1:]
            outline_mask[:, 1:] |= mask[:, :-1]
            outline_mask[:, :-1] |= mask[:, 1:]
            outline_mask[:-1, 1:] |= mask[1:, :-1]
            outline_mask[:-1, :] |= mask[1:, :]
            outline_mask[:-1, :-1] |= mask[1:, 1:]
            outline = outline_mask & ~mask
            output[outline, :3] = (5, 12, 20)
            output[outline, 3] = 230
        output[mask, :3] = glyph_rgb[mask]
        output[mask, 3] = 255
        return QImage(output.data, output.shape[1], output.shape[0],
                      output.shape[1] * 4, QImage.Format.Format_RGBA8888).copy()

    def render_frame(self, now: float | None = None,
                     local_time: datetime | None = None) -> QImage:
        now = time.monotonic() if now is None else float(now)
        local_time = datetime.now().astimezone() if local_time is None else local_time
        self._update_attention(now)
        self.state = self.animator.advance(self.target_state, now)
        palette, daylight, twilight, label = self._cycle(local_time)
        chars, colors = self._new_grid(palette["sky"])
        if self.mode == "pet":
            self._draw_eye(chars, colors, palette, now)
        else:
            self._draw_sky(chars, colors, palette, daylight, twilight, label,
                           local_time, now)
            self._draw_landscape(chars, colors, palette, daylight, twilight, now)
            self._draw_eye(chars, colors, palette, now)
            accent = palette["accent"]
            muted = _mix(palette["sky"], palette["star"], 0.58)
            self._text(chars, colors, 2, 2, f"> OCULUS  /  {label}", accent,
                       self.columns // 2)
            clock_text = local_time.strftime("%H:%M:%S")
            self._text(chars, colors, self.columns - len(clock_text) - 3, 2,
                       clock_text, palette["amber"])
        if self.mode == "hud":
            state_label = self.state.emotion.upper()[:12]
            self._text(chars, colors, 2, 4, f"> HUMOR {self.state.happiness:.0%}", muted)
            self._text(chars, colors, 2, 5, f"> ESTADO {state_label}", muted)
            fps_text = f"{self.state.render_fps:02.0f} FPS"
            self._text(chars, colors, self.columns - len(fps_text) - 3, 4,
                       fps_text, muted)
        if self.mode != "pet":
            legend = "O OLHO E UMA JANELA"
            self._text(chars, colors, max(2, (self.columns - len(legend)) // 2),
                       self.rows - 2, legend, muted)
        self._last_frame = self._render_cells(
            chars, colors, palette["sky"], transparent=self.mode == "pet")
        self.rendered_frames += 1
        return self._last_frame

    def paintEvent(self, _event) -> None:
        image = self.render_frame()
        painter = QPainter(self)
        if self.mode == "pet":
            # A translucent glassy eye rim gives the transparent avatar a
            # stable silhouette over both bright and dark desktop backgrounds.
            width, height = float(self.width()), float(self.height())
            rim = QPainterPath()
            rim.moveTo(width * 0.045, height * 0.50)
            rim.cubicTo(width * 0.18, height * 0.15, width * 0.82,
                        height * 0.15, width * 0.955, height * 0.50)
            rim.cubicTo(width * 0.82, height * 0.85, width * 0.18,
                        height * 0.85, width * 0.045, height * 0.50)
            rim.closeSubpath()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillPath(rim, QColor(5, 15, 23, 58))
            painter.setPen(QPen(QColor(3, 12, 21, 205), 5.0))
            painter.drawPath(rim)
            painter.setPen(QPen(QColor(62, 216, 227, 190), 2.4))
            painter.drawPath(rim)
            painter.setPen(QPen(QColor(235, 246, 238, 155), 0.8))
            painter.drawPath(rim)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(self.rect(), image)
        painter.end()

    def current_frame(self) -> QImage:
        if self._last_frame.isNull():
            return self.render_frame()
        return self._last_frame

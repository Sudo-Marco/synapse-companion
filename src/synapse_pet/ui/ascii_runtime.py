from __future__ import annotations

import ctypes
from collections import OrderedDict
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
    GLYPHS = "".join(chr(codepoint) for codepoint in range(32, 127)) + "♥█▓▒░▀▄"

    def __init__(self, columns: int = 100, rows: int = 56,
                 scene_time: str = "auto", design: str = "A",
                 max_particles: int = 8,
                 parent: QWidget | None = None,
                 max_columns: int = 170, max_rows: int = 96,
                 affection_drag_min_s: float = 1.0,
                 compact: bool = False,
                 outline: dict[str, object] | None = None,
                 density: str = "normal") -> None:
        super().__init__(parent)
        self.compact = bool(compact)
        self.outline_config = dict(outline or {})
        self.density = (str(density).lower() if str(density).lower() in
                        {"bold", "normal", "fine"} else "normal")
        self.density_profile = {
            "bold": {"sclera_period": 3, "iris_period": 3,
                     "pupil_period": 3, "fill": 0.82},
            "normal": {"sclera_period": 5, "iris_period": 5,
                       "pupil_period": 5, "fill": 0.66},
            "fine": {"sclera_period": 7, "iris_period": 7,
                     "pupil_period": 7, "fill": 0.48},
        }[self.density]
        self.min_cell_px = max(8, min(32, int(
            self.outline_config.get("min_cell_px", 8))))
        self.outline_thickness = max(1, min(2, int(
            self.outline_config.get("thickness_px", 1))))
        self.double_outline = bool(self.outline_config.get("double", True))
        self.outline_dark = self._color_option("dark", (7, 13, 23))
        self.outline_light = self._color_option("light", (250, 252, 255))
        self.theme_is_light = self._windows_light_theme()
        self.outline_outer, self.outline_inner = self._resolve_outline_order()
        self.plate_alpha = max(0.0, min(0.75, float(
            self.outline_config.get("plate_alpha", 0.42))))
        self.plate_dark = self._color_option("plate_dark", (12, 20, 32))
        self.plate_light = self._color_option("plate_light", (235, 242, 246))
        # Oppose the Windows app theme so the translucent silhouette remains
        # distinct on the corresponding light or dark desktop.
        self.plate_color = self.plate_dark if self.theme_is_light else self.plate_light
        self._eye_geometry: tuple[float, float, float, float, float] | None = None
        min_columns = 6 if self.compact else 72
        min_rows = 6 if self.compact else 42
        self.base_columns = max(min_columns, min(240, int(columns)))
        self.base_rows = max(min_rows, min(135, int(rows)))
        self.max_columns = max(self.base_columns, min(300, int(max_columns)))
        self.max_rows = max(self.base_rows, min(180, int(max_rows)))
        self.columns = self.base_columns
        self.rows = self.base_rows
        self.lod_level = "large"
        self.lod_detail_weight = 1.0
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
        self._iris_geometry: tuple[float, float, float] | None = None
        self._pupil_geometry: tuple[float, float, float] | None = None
        self._render_palette: dict[str, Color] | None = None
        self._iris_bitmap_cache: OrderedDict[tuple[int, Color], QImage] = OrderedDict()
        (self._glyph_ids, self._glyph_atlas, self._glyph_dark_rings,
         self._glyph_light_rings) = self._build_glyph_atlas()
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

    def _color_option(self, name: str, default: Color) -> Color:
        value = self.outline_config.get(name, default)
        if not isinstance(value, (tuple, list)) or len(value) != 3:
            return default
        return tuple(max(0, min(255, int(channel))) for channel in value)  # type: ignore[return-value]

    @staticmethod
    def _windows_light_theme() -> bool:
        """Read only the Windows app-theme preference; never inspect the desktop."""
        if sys.platform != "win32":
            return False
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return bool(value)
        except (OSError, ImportError):
            return False

    def _resolve_outline_order(self) -> tuple[Color, Color]:
        if not bool(self.outline_config.get("theme_auto", True)):
            return self.outline_light, self.outline_dark
        return ((self.outline_dark, self.outline_light) if self.theme_is_light
                else (self.outline_light, self.outline_dark))

    def _build_glyph_atlas(self) -> tuple[dict[str, int], np.ndarray,
                                           np.ndarray, np.ndarray]:
        font_root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        font = None
        font_size = max(6, min(18, int(self.outline_config.get("font_size", 7))))
        for name in ("consola.ttf", "cour.ttf", "lucon.ttf",
                     "consolab.ttf", "courbd.ttf"):
            path = font_root / name
            if path.exists():
                font = ImageFont.truetype(str(path), font_size)
                break
        if font is None:
            try:
                font = ImageFont.truetype("DejaVuSansMono.ttf", font_size)
            except OSError:
                font = ImageFont.load_default()
        masks = []
        yy, xx = np.indices((self.CELL_HEIGHT, self.CELL_WIDTH))
        for glyph in self.GLYPHS:
            if glyph == "█":
                masks.append(np.ones((self.CELL_HEIGHT, self.CELL_WIDTH), dtype=bool))
                continue
            if glyph == "▓":
                masks.append(((xx + yy) % 4 != 0))
                continue
            if glyph == "▒":
                masks.append(((xx + yy) % 2 == 0))
                continue
            if glyph == "░":
                masks.append(((xx + yy) % 4 == 0))
                continue
            if glyph == "▀":
                masks.append(yy < (self.CELL_HEIGHT + 1) // 2)
                continue
            if glyph == "▄":
                masks.append(yy >= self.CELL_HEIGHT // 2)
                continue
            tile = Image.new("L", (self.CELL_WIDTH, self.CELL_HEIGHT), 0)
            draw = ImageDraw.Draw(tile)
            bounds = draw.textbbox((0, 0), glyph, font=font)
            width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
            position = ((self.CELL_WIDTH - width) // 2 - bounds[0],
                        (self.CELL_HEIGHT - height) // 2 - bounds[1])
            draw.text(position, glyph, fill=255, font=font)
            masks.append(np.asarray(tile, dtype=np.uint8) > 32)
        atlas = np.stack(masks)
        dark_rings, light_rings = [], []
        def rounded_dilation(mask: np.ndarray, radius: int) -> np.ndarray:
            expanded = np.zeros_like(mask, dtype=bool)
            height, width = mask.shape
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx * dx + dy * dy > radius * radius:
                        continue
                    sy0, sy1 = max(0, -dy), min(height, height - dy)
                    sx0, sx1 = max(0, -dx), min(width, width - dx)
                    dy0, dy1 = sy0 + dy, sy1 + dy
                    dx0, dx1 = sx0 + dx, sx1 + dx
                    expanded[dy0:dy1, dx0:dx1] |= mask[sy0:sy1, sx0:sx1]
            return expanded

        for mask in atlas:
            inner = rounded_dilation(mask, self.outline_thickness)
            outer = rounded_dilation(mask, self.outline_thickness + 1)
            dark_rings.append(inner & ~mask)
            light_rings.append(outer & ~inner)
        for index, glyph in enumerate(self.GLYPHS):
            if glyph in {"█", "▓", "▒", "░", "▀", "▄"}:
                dark_rings[index].fill(False)
                light_rings[index].fill(False)
            elif glyph in ".,:;'":
                # Fine punctuation gets only the dark 1px keyline. A second
                # halo turns a dot into a square at compact pet dimensions.
                light_rings[index].fill(False)
        return ({glyph: index for index, glyph in enumerate(self.GLYPHS)},
                atlas, np.stack(dark_rings), np.stack(light_rings))

    def _resize_resolution(self) -> None:
        if not hasattr(self, "_stars") or self.width() <= 1 or self.height() <= 1:
            return
        dpr = max(1.0, float(self.devicePixelRatioF()))
        physical_width = max(1, round(self.width() * dpr))
        physical_height = max(1, round(self.height() * dpr))
        self.lod_detail_weight = _smoothstep(96.0, 128.0, physical_height)
        if self.compact:
            # Keep the standard 320x180 pet near its existing 24x14 grid while
            # scaling down to >=8px cells at tiny sizes and adding cells on
            # larger displays. This caps CPU without undersampling the eye.
            target_cell = max(
                float(self.min_cell_px),
                min(13.3, physical_height / 14.0, physical_width / 24.0),
            )
            self.effective_cell_px = target_cell
            columns = max(6, min(self.max_columns,
                                 int(physical_width / target_cell)))
            rows = max(6, min(self.max_rows,
                              int(physical_height / target_cell)))
            self.lod_level = ("small" if physical_height < 112 else
                              "medium" if physical_height < 224 else "large")
        else:
            columns = max(72, min(
                self.max_columns,
                round(physical_width / self.CELL_WIDTH * self.base_columns / 100.0),
            ))
            rows = max(42, min(
                self.max_rows,
                round(physical_height / self.CELL_HEIGHT * self.base_rows / 56.0),
            ))
            self.lod_level = "large"
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
            # Cool light-gray keeps white catchlights legible on the sclera
            # while the dark eye keyline protects contrast against any desktop.
            "sclera": (137, 150, 158),
            "iris": (58, 106, 130),
            "iris_dark": (28, 63, 86),
            "amber": (255, 187, 79),
            "rose": (236, 123, 159),
            "white": (255, 255, 250),
            "pupil": (5, 12, 24),
            "ink": (15, 31, 48),
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
        self._iris_geometry = None
        self._pupil_geometry = None
        self._render_palette = palette
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
        if self.compact:
            size_blend = _smoothstep(80.0, 144.0, self.height()
                                     * max(1.0, float(self.devicePixelRatioF())))
            horizontal_scale = 0.47 + (0.34 - 0.47) * size_blend
            rx = self.columns * horizontal_scale * breath
            vertical_scale = 0.38 - 0.095 * size_blend
            vertical_floor = 3.35 - 0.50 * size_blend
            ry = max(vertical_floor, self.rows * vertical_scale) * breath
        else:
            rx = self.columns * (0.34 if self.design == "A" else 0.35) * breath
            ry = self.rows * (0.285 if self.design == "A" else 0.265) * breath
        self._eye_geometry = (cx, cy, rx, ry, max(opening, 0.055))

        if self.compact and self.lod_level == "small":
            self._draw_small_eye(chars, colors, palette, now, cx, cy, rx, ry,
                                 opening, gx, gy, stress)
            return

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
            envelope = max(0.0, 1.0 - u * u) ** 0.5
            half = ry * envelope * opening
            if half < 0.55:
                continue
            top, bottom = math.ceil(cy - half), math.floor(cy + half)
            slope = -1.32 * u * (max(0.05, 1.0 - u * u) ** -0.34)
            for y in range(max(0, top), min(self.rows, bottom + 1)):
                ratio = abs((y - cy) / max(0.1, half))
                if ratio > 0.89:
                    if abs(u) > 0.88:
                        glyph = "."
                    elif abs(slope) < 0.33:
                        glyph = "_"
                    elif (y < cy) == (slope < 0):
                        glyph = "\\"
                    else:
                        glyph = "/"
                    self._put(chars, colors, x, y, glyph, palette["ink"])
                else:
                    edge_tone = ratio > 0.78
                    # Dense blocks establish the sclera mass; punctuation stays
                    # visible as the fine ASCII grain layered over it.
                    texture = ((x * 17 + y * 31)
                               % self.density_profile["sclera_period"])
                    fill_cut = round(self.density_profile["fill"]
                                     * self.density_profile["sclera_period"]
                                     * self.lod_detail_weight)
                    if texture < fill_cut:
                        glyph = ("▒" if texture == 0 else
                                 "░" if texture % 3 == 0 else
                                 ":" if edge_tone else ".")
                        tone = _mix(palette["sclera"], palette["sky"],
                                    0.12 if edge_tone else 0.16)
                        self._put(chars, colors, x, y, glyph, tone)

        iris_radius = max(2.45, self.rows * (0.225 if self.design == "A" else 0.207))
        ix = cx + gx * 2.1
        iy = cy + gy * 1.0
        pupil_radius = max(1.55, min(4.0, iris_radius *
                                   (0.28 - 0.08 * stress + 0.02 * self.state.curiosity)))
        self._iris_geometry = (ix, iy, iris_radius)
        self._pupil_geometry = (ix, iy, pupil_radius)
        for x in range(round(ix - iris_radius), round(ix + iris_radius) + 1):
            for y in range(round(iy - iris_radius), round(iy + iris_radius) + 1):
                if not (0 <= x < self.columns and 0 <= y < self.rows):
                    continue
                u = (x - ix) / iris_radius
                v = (y - iy) / iris_radius
                radius = math.hypot(u, v)
                if radius > 1.0:
                    continue
                half = ry * max(0.0, 1.0 - ((x - cx) / rx) ** 2) ** 0.5 * opening
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
                    pupil_pattern = ((x * 11 + y * 7)
                                     % self.density_profile["pupil_period"])
                    if pupil_pattern == 0:
                        self._put(chars, colors, x, y, "░", palette["pupil"])
                    else:
                        self._put(chars, colors, x, y,
                                  "." if pupil_pattern == 1 else ":",
                                  palette["pupil"])
                elif abs(radius - 0.91) < 0.045:
                    self._put(chars, colors, x, y, ".", palette["iris_dark"])
                elif abs(radius - 0.70) < 0.055:
                    if (x + y) % 3:
                        self._put(chars, colors, x, y, ".", palette["amber"])
                else:
                    fiber_phase = math.sin(math.atan2(v, u) * 32.0 + radius * 47.0)
                    fiber = fiber_phase > 0.82 and radius > 0.43
                    if fiber:
                        angle = math.atan2(v, u)
                        glyph = "|" if abs(math.sin(angle)) < 0.30 else (
                            "/" if math.cos(angle) * math.sin(angle) < 0 else "\\")
                        fiber_color = (palette["amber"] if (x + y) % 7 == 0
                                       else palette["iris_dark"])
                        self._put(chars, colors, x, y, glyph, fiber_color)
                    else:
                        tone = ((x * 3 + y * 5)
                                % self.density_profile["iris_period"])
                        if tone == 0:
                            self._put(chars, colors, x, y, "░",
                                      _mix(palette["iris"], palette["sky"], 0.24))
                        else:
                            glyph = "." if tone in {1, 2} else ":"
                            iris_color = (palette["iris"] if radius < 0.78
                                          else palette["iris_dark"])
                            self._put(chars, colors, x, y, glyph, iris_color)

        if self.state.affection > 0.82 or emotion == "amoroso":
            heart = (" @ @ ", "@@@@@", " @@@ ", "  @  ")
            for row_index, row in enumerate(heart):
                for column_index, glyph in enumerate(row):
                    if glyph != " ":
                        self._put(chars, colors, round(ix) - 2 + column_index,
                                  round(iy) - 2 + row_index, glyph, palette["rose"])

        # Enlarged, rounded ASCII catchlights: one large and one medium.
        large_x = round(-pupil_radius * 0.5)
        large_y = round(-pupil_radius * 0.5)
        for dx, dy, glyph in ((0, 0, "@"), (1, 0, "@"),
                              (0, 1, "@"), (1, 1, "o"),
                              (2, 1, ".")):
            self._put(chars, colors, round(ix) + large_x + dx,
                      round(iy) + large_y + dy,
                      glyph, palette["white"])
        medium_x = round(pupil_radius * 0.45)
        medium_y = round(pupil_radius * 0.20)
        for dx, dy, glyph in ((0, 0, "o"), (1, 0, "."), (0, 1, ".")):
            self._put(chars, colors, round(ix) + medium_x + dx,
                      round(iy) + medium_y + dy,
                      glyph, palette["white"])

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
            self._put(chars, colors, x, y - (1 if u < -0.18 or u > 0.18 else 0),
                      glyph, palette["ink"])

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
                x = round(cx + sign * rx * 0.73)
                y = round(cy + ry * 0.46)
                self._put(chars, colors, x, y, ":", cheek_color)
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

        self._small_lod_metrics = {
            "pupil_cell_count": max(9, round(math.pi * pupil_radius ** 2)),
            "pupil_width_cells": max(3, math.floor(2 * pupil_radius) + 1),
            "pupil_height_cells": max(3, math.floor(2 * pupil_radius) + 1),
            "iris_ring_cells": max(1, round(2 * math.pi
                                              * (iris_radius - pupil_radius))),
            "main_reflection_cells": 5,
            "secondary_reflection_cells": 3,
            "outline_is_closed": bool(rx > 1.0 and ry * opening > 1.0),
        }

    def _draw_small_eye(self, chars: list[list[str]], colors: list[list[Color]],
                        palette: dict[str, Color], now: float, cx: float, cy: float,
                        rx: float, ry: float, opening: float, gx: float, gy: float,
                        stress: float) -> None:
        """Dedicated coarse ASCII eye with readable pupil and catchlights."""
        if opening < 0.105:
            for x in range(max(0, math.floor(cx - rx)),
                           min(self.columns, math.ceil(cx + rx) + 1)):
                u = (x - cx) / max(1.0, rx)
                y = round(cy - 0.9 * (1.0 - u * u))
                self._put(chars, colors, x, y,
                          "/" if u < -0.18 else "\\" if u > 0.18 else "_",
                          palette["ink"])
            self._put(chars, colors, round(cx + rx * 0.34),
                      max(0, round(cy - ry + 0.6)), "z", palette["sky"])
            return

        sample_offsets = (0.125, 0.375, 0.625, 0.875)
        coverage = np.zeros((self.rows, self.columns), dtype=np.uint8)
        half_height = max(1.0, ry * opening)
        for y in range(self.rows):
            for x in range(self.columns):
                count = 0
                for oy in sample_offsets:
                    for ox in sample_offsets:
                        u = (x + ox - cx) / max(1.0, rx)
                        if abs(u) > 1.0:
                            continue
                        half = half_height * math.sqrt(max(0.0, 1.0 - u * u))
                        if abs(y + oy - cy) <= half:
                            count += 1
                coverage[y, x] = count

        ix = float(round(cx + max(-rx * 0.12, min(rx * 0.12, gx * 0.35)) + 0.5)
                    - 0.5)
        iy = float(round(cy + gy * 0.18 + 0.5) - 0.5)
        iris_radius = max(2.15, min(rx * 0.48, self.rows * 0.45,
                                    ry * opening * 0.88))
        pupil_radius = max(1.38, min(1.48, iris_radius * 0.58))

        # The vector base stays rounded; a close-value fill reads as ASCII
        # grain. Keep it outside the iris so the pupil and catchlights stay clean.
        for y in range(self.rows):
            for x in range(self.columns):
                amount = int(coverage[y, x])
                outside_iris = math.hypot(x + 0.5 - ix, y + 0.5 - iy) > iris_radius + 0.3
                if (amount >= 10 and outside_iris
                        and (x * 7 + y * 5) % 4 == 0):
                    tone = _mix(palette["sclera"], palette["white"], 0.04)
                    self._put(chars, colors, x, y, "░", tone)
        self._iris_geometry = (ix, iy, iris_radius)
        self._pupil_geometry = (ix, iy, pupil_radius)
        iris_cells: list[tuple[int, int]] = []
        pupil_cells: list[tuple[int, int]] = []
        radial_samples = (0.125, 0.375, 0.625, 0.875)
        for y in range(max(0, math.floor(iy - iris_radius - 0.5)),
                       min(self.rows, math.ceil(iy + iris_radius + 0.5))):
            for x in range(max(0, math.floor(ix - iris_radius - 0.5)),
                           min(self.columns, math.ceil(ix + iris_radius + 0.5))):
                if coverage[y, x] == 0:
                    continue
                iris_coverage = pupil_coverage = 0
                for oy in radial_samples:
                    for ox in radial_samples:
                        radius = math.hypot(x + ox - ix, y + oy - iy)
                        iris_coverage += radius <= iris_radius
                        pupil_coverage += radius <= pupil_radius
                if iris_coverage == 0:
                    continue
                radius = math.hypot(x + 0.5 - ix, y + 0.5 - iy)
                iris_cells.append((x, y))
                if pupil_coverage:
                    pupil_cells.append((x, y))
                    # Keep the small pupil clean so both catchlights remain open.
                else:
                    tone = (palette["iris"] if (x + y) % 3 else
                            palette["iris_dark"])
                    if (x * 5 + y * 3) % 5 == 0:
                        self._put(chars, colors, x, y,
                                  ":" if (x + y) % 2 else ".", tone)

        # Vector catchlights below provide the 2x2 and 1x1 physical highlights.
        center_x, center_y = round(ix - 0.5), round(iy - 0.5)
        main_reflection = (((center_x - 1, center_y - 1), "@"),
                           ((center_x, center_y - 1), "@"),
                           ((center_x - 1, center_y), "@"),
                           ((center_x, center_y), "@"))
        secondary_reflection = (center_x + 1, center_y + 1)

        pupil_x = [x for x, _ in pupil_cells]
        pupil_y = [y for _, y in pupil_cells]
        self._small_lod_metrics = {
            "pupil_cell_count": len(pupil_cells),
            "pupil_width_cells": max(pupil_x, default=0) - min(pupil_x, default=0) + 1,
            "pupil_height_cells": max(pupil_y, default=0) - min(pupil_y, default=0) + 1,
            "iris_ring_cells": len(iris_cells) - len(pupil_cells),
            "main_reflection_cells": len(main_reflection),
            "secondary_reflection_cells": 1,
            "outline_is_closed": bool(rx > 1.0 and ry * opening > 1.0
                                       and rx < self.columns * 0.5
                                       and ry * opening < self.rows * 0.5),
        }
        if self.lod_detail_weight > 0.0:
            protected = set(iris_cells)
            protected.update((x, y) for (x, y), _ in main_reflection)
            protected.add(secondary_reflection)
            texture_budget = round(self.lod_detail_weight * 2.0)
            if texture_budget:
                for y in range(self.rows):
                    for x in range(self.columns):
                        if (coverage[y, x] and (x, y) not in protected
                                and (x * 11 + y * 7) % 12 < texture_budget):
                            self._put(chars, colors, x, y, ".",
                                      _mix(palette["sclera"], palette["sky"], 0.24))

    def _render_cells(self, chars: list[list[str]], colors: list[list[Color]],
                      background: Color, *, transparent: bool = False) -> QImage:
        char_grid = np.asarray(chars, dtype="<U1")
        glyph_ids = self._glyph_lut[char_grid.view(np.uint32)]
        glyph_tiles = self._glyph_atlas[glyph_ids]
        glyph_mask = glyph_tiles.transpose(0, 2, 1, 3).reshape(
            self.rows * self.CELL_HEIGHT, self.columns * self.CELL_WIDTH)
        dark_tiles = self._glyph_dark_rings[glyph_ids]
        dark_glyph_ring = dark_tiles.transpose(0, 2, 1, 3).reshape(glyph_mask.shape)
        light_tiles = self._glyph_light_rings[glyph_ids]
        light_glyph_ring = light_tiles.transpose(0, 2, 1, 3).reshape(glyph_mask.shape)
        color_grid = np.asarray(colors, dtype=np.uint8)
        glyph_rgb = np.repeat(np.repeat(color_grid, self.CELL_HEIGHT, axis=0),
                              self.CELL_WIDTH, axis=1)
        output = np.empty((*glyph_mask.shape, 4), dtype=np.uint8)
        height, width = output.shape[:2]
        if not transparent:
            output[:, :, :3] = background
            output[:, :, 3] = 255
        else:
            output[:, :, :3] = 0
            output[:, :, 3] = 0
        np.copyto(output[:, :, :3], np.asarray(self.outline_inner, dtype=np.uint8),
                  where=dark_glyph_ring[:, :, None])
        np.copyto(output[:, :, 3], 255, where=dark_glyph_ring)
        if self.double_outline:
            np.copyto(output[:, :, :3], np.asarray(self.outline_outer, dtype=np.uint8),
                      where=light_glyph_ring[:, :, None])
            np.copyto(output[:, :, 3], 255, where=light_glyph_ring)
        np.copyto(output[:, :, :3], glyph_rgb, where=glyph_mask[:, :, None])
        np.copyto(output[:, :, 3], 255, where=glyph_mask)
        return QImage(output.data, width, height, width * 4,
                      QImage.Format.Format_RGBA8888).copy()

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

    def _paint_pet_plate(self, painter: QPainter) -> None:
        if self._eye_geometry is None or self.plate_alpha <= 0.0:
            return
        cx, cy, rx, ry, opening = self._eye_geometry
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        left, right = (cx - rx) * self.CELL_WIDTH, (cx + rx) * self.CELL_WIDTH
        middle_x, middle_y = cx * self.CELL_WIDTH, cy * self.CELL_HEIGHT
        half_height = max(0.5, ry * opening * self.CELL_HEIGHT)
        if opening < 0.105:
            path.moveTo(left, middle_y)
            path.cubicTo(left + rx * 0.40 * self.CELL_WIDTH,
                         middle_y - half_height,
                         middle_x + rx * 0.42 * self.CELL_WIDTH,
                         middle_y - half_height, right, middle_y)
        else:
            # Smooth oval silhouette instead of pointed or stepped ends.
            path.addEllipse(left, middle_y - half_height,
                            right - left, half_height * 2.0)
        painter.setPen(Qt.PenStyle.NoPen)
        small_eye = (self.compact and self.lod_level == "small"
                     and self.mode == "pet" and opening >= 0.105)
        palette = self._render_palette or {}
        fill = QColor(*(palette.get("sclera", self.plate_color)
                        if small_eye else self.plate_color))
        fill.setAlphaF(0.96 if small_eye else self.plate_alpha)
        painter.fillPath(path, fill)
        if self.double_outline:
            # Two thin strokes create one dark inner and one light outer pixel.
            outer_pen = QPen(QColor(*self.outline_outer), 2.0)
            outer_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            outer_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(outer_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        inner_pen = QPen(QColor(*self.outline_inner),
                         float(self.outline_thickness))
        inner_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        inner_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(inner_pen)
        painter.drawPath(path)
        if small_eye and self._iris_geometry and self._pupil_geometry:
            ix, iy, iris_radius = self._iris_geometry
            _, _, pupil_radius = self._pupil_geometry
            iris_rect = QPainterPath()
            iris_rect.addEllipse((ix - iris_radius) * self.CELL_WIDTH,
                                 (iy - iris_radius) * self.CELL_HEIGHT,
                                 iris_radius * 2 * self.CELL_WIDTH,
                                 iris_radius * 2 * self.CELL_HEIGHT)
            painter.setPen(QPen(QColor(*palette.get("iris_dark", (28, 63, 86))),
                                1.0))
            painter.setBrush(QColor(*palette.get("iris", (58, 106, 130))))
            painter.drawPath(iris_rect)

            # A restrained ring and a few radial strokes preserve iris detail
            # without turning the tiny eye into a block mosaic.
            center_x, center_y = ix * self.CELL_WIDTH, iy * self.CELL_HEIGHT
            for index in range(12):
                angle = math.tau * index / 12.0
                inner = iris_radius * (0.48 if index % 3 else 0.42)
                outer = iris_radius * 0.82
                color = (palette.get("amber", (235, 180, 64)) if index % 4 == 0
                         else palette.get("iris_dark", (28, 63, 86)))
                pen = QPen(QColor(*color), 0.8 if index % 3 else 1.0)
                painter.setPen(pen)
                painter.drawLine(
                    round(center_x + math.cos(angle) * inner * self.CELL_WIDTH),
                    round(center_y + math.sin(angle) * inner * self.CELL_HEIGHT),
                    round(center_x + math.cos(angle) * outer * self.CELL_WIDTH),
                    round(center_y + math.sin(angle) * outer * self.CELL_HEIGHT),
                )
            painter.setPen(QPen(QColor(*palette.get("amber", (235, 180, 64))),
                                1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            collar = iris_radius * 0.48
            painter.drawEllipse(center_x - collar * self.CELL_WIDTH,
                                center_y - collar * self.CELL_HEIGHT,
                                collar * 2 * self.CELL_WIDTH,
                                collar * 2 * self.CELL_HEIGHT)

            pupil_rect = QPainterPath()
            pupil_rect.addEllipse((ix - pupil_radius) * self.CELL_WIDTH,
                                  (iy - pupil_radius) * self.CELL_HEIGHT,
                                  pupil_radius * 2 * self.CELL_WIDTH,
                                  pupil_radius * 2 * self.CELL_HEIGHT)
            painter.setPen(QPen(QColor(3, 8, 17), 1.0))
            painter.setBrush(QColor(*palette.get("pupil", (5, 12, 24))))
            painter.drawPath(pupil_rect)

            # Big and medium rounded reflections are key to the friendly look.
            main_size = max(8.0, self.CELL_WIDTH * 1.55)
            main_x = center_x - pupil_radius * self.CELL_WIDTH * 0.50
            main_y = center_y - pupil_radius * self.CELL_HEIGHT * 0.56
            painter.setPen(QPen(QColor(35, 52, 64, 110), 0.8))
            painter.setBrush(QColor(*palette.get("white", (255, 255, 250))))
            painter.drawEllipse(main_x, main_y, main_size, main_size)
            secondary_size = max(5.0, self.CELL_WIDTH * 0.88)
            painter.drawEllipse(center_x + pupil_radius * self.CELL_WIDTH * 0.32,
                                center_y + pupil_radius * self.CELL_HEIGHT * 0.32,
                                secondary_size, secondary_size)
        if opening > 0.16 and self._iris_geometry:
            if small_eye:
                return
            ix, iy, iris_radius = self._iris_geometry
            diameter = max(1, round(iris_radius * 2 * self.CELL_WIDTH))
            color = (self._render_palette or {}).get("iris", (73, 137, 158))
            painter.drawImage(
                (ix - iris_radius) * self.CELL_WIDTH,
                (iy - iris_radius) * self.CELL_HEIGHT,
                self._iris_underlay(diameter, color))

    def _composite_pet_plate(self, glyph_layer: QImage) -> QImage:
        if self._eye_geometry is None or self.plate_alpha <= 0.0 or glyph_layer.isNull():
            return glyph_layer
        plate = QImage(glyph_layer.size(), QImage.Format.Format_RGBA8888)
        plate.fill(Qt.GlobalColor.transparent)
        painter = QPainter(plate)
        self._paint_pet_plate(painter)
        painter.end()

        composite = QImage(glyph_layer.size(), QImage.Format.Format_RGBA8888)
        composite.fill(Qt.GlobalColor.transparent)
        painter = QPainter(composite)
        painter.drawImage(0, 0, plate)
        painter.drawImage(0, 0, glyph_layer)
        painter.end()
        return composite

    def _iris_underlay(self, diameter: int, color: Color) -> QImage:
        key = (diameter, color)
        cached = self._iris_bitmap_cache.get(key)
        if cached is not None:
            self._iris_bitmap_cache.move_to_end(key)
            return cached
        scale = 3
        mask = Image.new("L", (diameter * scale, diameter * scale), 0)
        ImageDraw.Draw(mask).ellipse(
            (0, 0, diameter * scale - 1, diameter * scale - 1), fill=255)
        mask = mask.resize((diameter, diameter), Image.Resampling.LANCZOS)
        alpha = np.asarray(mask, dtype=np.uint8).copy()
        rgba = np.zeros((diameter, diameter, 4), dtype=np.uint8)
        rgba[:, :, :3] = color
        rgba[:, :, 3] = (alpha.astype(np.uint16) * 56 // 255).astype(np.uint8)
        image = QImage(rgba.data, diameter, diameter, diameter * 4,
                       QImage.Format.Format_RGBA8888).copy()
        self._iris_bitmap_cache[key] = image
        while len(self._iris_bitmap_cache) > 4:
            self._iris_bitmap_cache.popitem(last=False)
        return image

    def paintEvent(self, _event) -> None:
        image = self.render_frame()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        if self.mode == "pet":
            painter.save()
            painter.scale(self.width() / max(1, image.width()),
                          self.height() / max(1, image.height()))
            self._paint_pet_plate(painter)
            painter.restore()
        painter.drawImage(self.rect(), image)
        painter.end()

    def current_frame(self) -> QImage:
        if self._last_frame.isNull():
            return self.render_frame()
        return self._last_frame

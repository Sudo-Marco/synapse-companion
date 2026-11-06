from __future__ import annotations

from datetime import datetime
from dataclasses import replace
import json
import math
from pathlib import Path
import random
import time

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (QBitmap, QColor, QFont, QFontDatabase, QImage,
                           QPainter, QPen, QRegion)
from PySide6.QtWidgets import QWidget

from ..runtime.visual_state import StateAnimator, VisualState
from .day_cycle import (moon_phase, moon_position, period_name, scene_palette,
                        sun_position, sun_times)
from .interaction import AffectionDragTracker
from .pet_motion import MotionFrame, PetMotionController


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "pixel"
FONT_PATH = (Path(__file__).resolve().parents[1] / "assets" / "fonts"
             / "silkscreen" / "Silkscreen-Bold.ttf")


class PixelPetWidget(QWidget):
    """Nearest-neighbour Piu renderer with data-driven sprite animation."""

    petRequested = Signal()
    panelRequested = Signal()
    activityDetected = Signal()
    animationStarted = Signal()
    rendererChanged = Signal(str)
    spriteMaskChanged = Signal()

    def __init__(self, *, scene_time: str = "auto", compact: bool = False,
                 affection_drag_min_s: float = 1.0, seed: int = 41,
                 depth_in_pet_mode: bool = False,
                 depth_config: dict[str, object] | None = None,
                 day_cycle_config: dict[str, object] | None = None,
                 weather_config: dict[str, object] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.compact = bool(compact)
        self.depth_in_pet_mode = bool(depth_in_pet_mode)
        depth_config = depth_config or {}
        self.depth_far_fraction = max(0.05, min(
            0.45, float(depth_config.get("far_fraction", 0.18))))
        self.depth_min_scale = max(0.2, min(
            1.0, float(depth_config.get("min_scale", 0.42))))
        self.scene_time = str(scene_time).strip().lower()
        self.day_cycle_config = dict(day_cycle_config or {})
        weather_config = weather_config or {}
        self.weather_mode = str(weather_config.get("mode", "none")).strip().lower()
        if self.weather_mode not in {"none", "rain", "fog", "wind"}:
            self.weather_mode = "none"
        self.weather_density = max(0.0, min(
            1.0, float(weather_config.get("density", 0.22))))
        self.mode = "pet" if compact else "ascii"
        self.rendered_frames = 0
        self.current_renderer = "Piu pixel art · QPainter nearest-neighbour"
        self.state = VisualState()
        self.animator = StateAnimator(self.state, seconds=0.20)
        self._manifest = json.loads((ASSET_DIR / "animations.json").read_text(
            encoding="utf-8"))
        self._sheets: dict[str, QImage] = {}
        for animation in self._manifest["animations"].values():
            name = animation["sheet"]
            if name not in self._sheets:
                self._sheets[name] = QImage(str(ASSET_DIR / name))
        lod = self._manifest["lod"]
        self._sheets[lod["sheet"]] = QImage(str(ASSET_DIR / lod["sheet"]))
        self._font_family = self._load_font()
        self.motion = PetMotionController(
            pivot=tuple(self._manifest.get("pivot_canvas", [16, 40])))
        self._last_render_time: float | None = None
        self._last_local_time: datetime | None = None
        self._blink_until = 0.0
        self._next_blink_at = time.monotonic() + 3.5
        self._rng = random.Random(int(seed) ^ 0x504955)
        self._next_idle_action = time.monotonic() + 9.0
        self._gaze_target = (0.5, 0.5)
        self._pointer_over = False
        self._drag_tracker = AffectionDragTracker(affection_drag_min_s)
        self._motion_blocked = False
        self._world_travel_action: str | None = None
        self._world_depth = 0.0
        self._world_direction = 1
        self._world_stride_phase = 0.0
        self._behavior_action: str | None = None
        self._audio_microphone_enabled = False
        self._audio_loopback_enabled = False
        self._audio_voice_active = False
        self._audio_music_active = False
        self._audio_bpm = 0.0
        self._audio_beat_phase = 0.0
        self._audio_level = 0.0
        self._audio_badge_rects: list[QRect] = []
        self._current_source: tuple[str, QRect] | None = None
        self._current_frame_entry: dict[str, object] = {}
        self._current_destination = QRect()
        self._current_frame_size = QSize()
        self._current_mirror = False
        self._mask_geometry_key: tuple[object, ...] | None = None
        self._scene_cache: QImage | None = None
        self._scene_cache_key: tuple[object, ...] | None = None
        self._frame_buffer: QImage | None = None
        self._hud_cache: QImage | None = None
        self._hud_cache_key: tuple[object, ...] | None = None
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, compact)
        self.setMinimumSize(80, 52) if compact else self.setMinimumSize(700, 390)
        self.setToolTip(
            "Clique duas vezes para abrir o painel; clique direito para opções. "
            "Arraste o Piu por pelo menos "
            f"{affection_drag_min_s:g}s para demonstrar carinho.")

    @staticmethod
    def _load_font() -> str:
        if FONT_PATH.exists():
            font_id = QFontDatabase.addApplicationFont(str(FONT_PATH))
            families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                return families[0]
        return QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont).family()

    @property
    def attention_animating(self) -> bool:
        return self.motion.moving or self.state.emotion in {
            "curioso", "alegre", "estressado", "sonolento"}

    def set_state(self, state: VisualState) -> None:
        self.state = state
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = str(mode)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,
                          self.mode == "pet")
        # Panel and floating pet have different widget dimensions. Discard the
        # previous rectangle so the first floating mask matches its new frame.
        self._current_source = None
        self._current_frame_size = QSize()
        self._mask_geometry_key = None
        self.update()

    def set_motion_blocked(self, *, dragging: bool = False,
                           proposal_pending: bool = False) -> None:
        self._motion_blocked = bool(dragging or proposal_pending)
        self.motion.set_blocked(dragging=dragging,
                                proposal_pending=proposal_pending)

    def request_move(self, target: str | tuple[float, float], style: str = "walk") -> bool:
        accepted = self.motion.request_move(
            target, style, dragging=self._motion_blocked,
            proposal_pending=self._motion_blocked)
        if accepted:
            self.animationStarted.emit()
            self.update()
        return accepted

    def set_world_travel(self, action: str | None, *, depth: float = 0.0,
                         direction: int = 1,
                         stride_delta_px: float = 0.0) -> None:
        """Animate the bird in-place while its transparent window moves on desktop."""
        action = None if action is None else str(action)
        if action not in {None, "walk", "run", "away", "return", "fly"}:
            action = None
        self._world_travel_action = action
        self._world_depth = max(0.0, min(1.0, float(depth)))
        self._world_direction = -1 if direction < 0 else 1
        if action is not None:
            self._world_stride_phase += max(0.0, float(stride_delta_px)) * 8.0 / 24.0
        if action is None:
            self._world_stride_phase = 0.0
        self.update()

    def set_behavior_action(self, action: str | None) -> None:
        action = None if action is None else str(action)
        if action not in {None, "think", "rest", "listen", "caught", "fall",
                          "peek", "dance_sway", "dance_hop", "dance_head"}:
            action = None
        self._behavior_action = action
        self.update()

    def set_audio_status(self, *, microphone_enabled: bool = False,
                         loopback_enabled: bool = False,
                         voice_active: bool = False,
                         music_active: bool = False, bpm: float = 0.0,
                         beat_phase: float = 0.0, level: float = 0.0) -> None:
        previous = (self._audio_microphone_enabled, self._audio_loopback_enabled)
        self._audio_microphone_enabled = bool(microphone_enabled)
        self._audio_loopback_enabled = bool(loopback_enabled)
        self._audio_voice_active = bool(voice_active)
        self._audio_music_active = bool(music_active)
        self._audio_bpm = max(0.0, float(bpm))
        self._audio_beat_phase = max(0.0, min(1.0, float(beat_phase)))
        self._audio_level = max(0.0, min(1.0, float(level)))
        if previous != (self._audio_microphone_enabled,
                        self._audio_loopback_enabled):
            self._mask_geometry_key = None
            self.spriteMaskChanged.emit()
        self.update()

    @staticmethod
    def _clock_palette(local_time: datetime, setting: str,
                       day_cycle_config: dict | None = None
                       ) -> tuple[QColor, QColor, QColor, QColor, float]:
        palette = scene_palette(local_time, setting, day_cycle_config)
        return (QColor(palette.sky), QColor(palette.horizon),
                QColor(palette.far), QColor(palette.near),
                palette.night_weight)

    def render_frame(self, now: float | None = None,
                     local_time: datetime | None = None) -> QImage:
        now = time.monotonic() if now is None else float(now)
        local_time = local_time or datetime.now().astimezone()
        width, height = max(1, self.width()), max(1, self.height())
        image = self._render_half_resolution(width, height, now, local_time)
        return image.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.FastTransformation)

    def paintEvent(self, _event) -> None:
        now = time.monotonic()
        image = self._render_half_resolution(
            max(1, self.width()), max(1, self.height()), now,
            datetime.now().astimezone())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(self.rect(), image)
        painter.end()

    def _render_half_resolution(self, width: int, height: int, now: float,
                                local_time: datetime) -> QImage:
        """Paint at half resolution, then nearest-neighbour upscale in paintEvent.

        Pixel cells and sprite scale stay even, so the displayed art is still an
        integer multiple of the approved source pixels while reducing fill cost.
        """
        internal_width, internal_height = max(1, (width + 1) // 2), max(1, (height + 1) // 2)
        if (self._frame_buffer is None
                or self._frame_buffer.size().width() != internal_width
                or self._frame_buffer.size().height() != internal_height):
            self._frame_buffer = QImage(
                internal_width, internal_height,
                QImage.Format.Format_ARGB32_Premultiplied)
        self._frame_buffer.fill(Qt.GlobalColor.transparent if self.mode == "pet"
                                else QColor("#7faebd"))
        painter = QPainter(self._frame_buffer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.scale(0.5, 0.5)
        self._draw_frame(painter, QRect(0, 0, width, height), now, local_time)
        painter.end()
        return self._frame_buffer

    def _draw_frame(self, painter: QPainter, bounds: QRect, now: float,
                    local_time: datetime) -> None:
        self._current_frame_size = bounds.size()
        dt = (0.0 if self._last_render_time is None else
              max(0.0, min(0.25, now - self._last_render_time)))
        self._last_render_time = now
        self._last_local_time = local_time
        state = self.animator.advance(self.state, now)
        emotion = state.expression_override or state.emotion
        if (emotion not in {"dormindo", "sleeping", "sonolento", "sleepy"}
                and self.motion.frame.view != "back" and now >= self._next_blink_at):
            self._blink_until = now + 0.16
            self._next_blink_at = now + self._rng.uniform(3.7, 6.8)
        if self.mode != "pet":
            self._draw_scene(painter, bounds, now, local_time)
        else:
            painter.fillRect(bounds, Qt.GlobalColor.transparent)

        scale = self._draw_scale(bounds)
        motion = self.motion.advance(
            dt, viewport_width=bounds.width(), sprite_scale=scale)
        if self.mode == "pet" and self._world_travel_action is not None:
            if self._world_travel_action == "away":
                view = "back"
            elif self._world_travel_action == "return":
                view = "front"
            else:
                view = "back" if self._world_depth > 0.78 else "profile"
            minimum = 20 if self.depth_min_scale <= (20 / 48) + 0.01 else 32
            far_threshold = 1.0 - self.depth_far_fraction
            lod = (minimum if self._world_depth >= far_threshold else
                   32 if self._world_depth > 0.43 else 48)
            motion = replace(motion, action=self._world_travel_action,
                             view=view, depth=self._world_depth,
                             lod_size=lod, facing=self._world_direction,
                             stride_phase=self._world_stride_phase)
        elif self._behavior_action is not None:
            motion = replace(motion, action=self._behavior_action)
        scene_depth = motion.depth
        if (self.mode != "pet" and not self._motion_blocked
                and not self.motion.moving and now >= self._next_idle_action):
            self._schedule_mood_motion(state, now)
        if self.mode == "pet" and not self.depth_in_pet_mode:
            motion = replace(motion, depth=0.0, lod_size=48)
        group, index, use_lod = self._select_pose(state, motion, now)
        source_sheet, source_rect = self._source_rect(group, index, use_lod,
                                                      motion)
        if source_rect is None:
            self.rendered_frames += 1
            return

        art_scale = scale
        native_width, native_height = source_rect.width(), source_rect.height()
        dest_width, dest_height = native_width * art_scale, native_height * art_scale
        pivot = self._current_frame_entry.get(
            "pivot", [native_width // 2, native_height])
        pivot_x, pivot_y = map(int, pivot)
        anchor_x = round(bounds.left() + motion.x * bounds.width())
        x = anchor_x - pivot_x * art_scale
        ground_y = (bounds.bottom() - 3 - 4 * art_scale if self.mode == "pet"
                    else round(bounds.top() + bounds.height() * 0.83))
        bob = round(math.sin(now * 1.7) * (0 if motion.action != "idle" else 1))
        depth_lift = (motion.depth * 26.0 if self.mode != "pet"
                      or self.depth_in_pet_mode else
                      min(scene_depth, 0.6) * 26.0
                      if motion.action == "away" else 0.0)
        stress_wobble = (round(math.sin(now * 42.0) * min(2.0, state.stress * 2.0))
                         if state.stress >= 0.62 else 0)
        x += stress_wobble * art_scale
        y = round(ground_y - pivot_y * art_scale - motion.height * dest_height
                  - depth_lift + bob)
        destination = QRect(x, y, dest_width, dest_height)
        previous_mask_key = self._mask_geometry_key
        self._current_source = (source_sheet, source_rect)
        self._current_destination = destination
        is_run_group = group.startswith("corrida_")
        self._current_mirror = motion.facing < 0 and is_run_group
        self._mask_geometry_key = (
            source_sheet, source_rect.x(), source_rect.y(),
            source_rect.width(), source_rect.height(),
            destination.x(), destination.y(), destination.width(),
            destination.height(), self._current_mirror)

        if self.mode != "pet":
            self._draw_shadow(painter, destination, motion, local_time)
        painter.save()
        if self._current_mirror:
            painter.translate(destination.left() * 2 + destination.width(), 0)
            painter.scale(-1.0, 1.0)
            draw_rect = destination
        else:
            draw_rect = destination
        painter.drawImage(draw_rect, self._sheets[source_sheet], source_rect)
        painter.restore()
        if self._current_mirror and group == "corrida_lateral":
            for px, py, color in ((20, 18, "#ffd93b"), (23, 19, "#ffd93b"),
                                  (8, 19, "#fff3a0"), (11, 18, "#ffffff")):
                painter.fillRect(destination.left() + px * art_scale,
                                 destination.top() + py * art_scale,
                                 art_scale, art_scale, QColor(color))
        if self.mode == "pet":
            self._draw_pet_tint(painter, destination, local_time)
        self._draw_snn_sparks(painter, destination, state, now)
        if self.mode != "pet":
            self._draw_depth_occlusion(painter, bounds, motion)
        if state.affection >= 0.60 and now % 1.7 < 0.12:
            self._draw_pixel_heart(painter, destination, now)
        if self.mode == "hud":
            self._draw_hud(painter, bounds, state, local_time)
        self._draw_audio_badges(painter, bounds)
        if self.mode == "pet" and self._mask_geometry_key != previous_mask_key:
            self.spriteMaskChanged.emit()
        self.rendered_frames += 1

    def _draw_scale(self, bounds: QRect) -> int:
        if self.mode == "pet":
            # A 48 px source sprite fills about three quarters of the floating
            # window while leaving transparent breathing room around it.
            return max(2, min(8, round(bounds.height() * 0.75 / 48)))
        # Keep the actor between 15% and 25% of the scene height. The half-size
        # render buffer is nearest-neighbour enlarged, so this integer factor
        # retains crisp pixels without oversized panel sprites.
        return max(1, min(8, round(bounds.height() * 0.20 / 48)))

    def _draw_audio_badges(self, painter: QPainter, bounds: QRect) -> None:
        self._audio_badge_rects = []
        if self.mode != "pet" or not (self._audio_microphone_enabled
                                       or self._audio_loopback_enabled):
            return
        sources = []
        if self._audio_microphone_enabled:
            sources.append(("MIC", QColor("#ff6371"), self._audio_voice_active))
        if self._audio_loopback_enabled:
            sources.append(("♪", QColor("#ffd166"), self._audio_music_active))
        badge_width, badge_height, gap = 32, 22, 5
        total_width = badge_width * len(sources) + gap * (len(sources) - 1)
        left = bounds.right() - total_width - 7
        top = bounds.top() + 7
        painter.save()
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        for index, (label, accent, detected) in enumerate(sources):
            rect = QRect(left + index * (badge_width + gap), top,
                         badge_width, badge_height)
            self._audio_badge_rects.append(rect)
            painter.setPen(QPen(accent, 2 if detected else 1))
            painter.setBrush(QColor(7, 19, 27, 230))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(accent)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _draw_scene(self, painter: QPainter, bounds: QRect, now: float,
                    local_time: datetime) -> None:
        sky, horizon, far, near, night_weight = self._clock_palette(
            local_time, self.scene_time, self.day_cycle_config)
        night = night_weight >= 0.55
        w, h = bounds.width(), bounds.height()
        palette_key = tuple(tuple((component // 4) * 4 for component in
                                  (color.red(), color.green(), color.blue()))
                            for color in (sky, horizon, far, near))
        key = (w, h, palette_key)
        if self._scene_cache is None or self._scene_cache_key != key:
            self._scene_cache = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            self._scene_cache.fill(sky)
            background = QPainter(self._scene_cache)
            background.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            self._draw_static_scene(background, w, h, sky, horizon, far, near,
                                    night_weight)
            background.end()
            self._scene_cache_key = key
        painter.drawImage(bounds.topLeft(), self._scene_cache)

        # Solar bodies and weather stay local, deterministic and network-free.
        self._draw_solar_objects(painter, bounds, local_time, sky,
                                 night_weight, now)
        cloud_speed = 18.0 if self.weather_mode == "wind" else 8.0
        cloud_x = int((now * cloud_speed) % max(1, w // 3)) + int(w * 0.08)
        cloud = QColor("#d6eff0" if not night else "#62779a")
        for cx, cy in ((bounds.left() + cloud_x, bounds.top() + int(h * 0.25)),
                       (bounds.left() + int(w * 0.72)
                        - int((now * cloud_speed * 0.5) % max(1, w // 8)),
                        bounds.top() + int(h * 0.39))):
            painter.fillRect(cx + 10, cy, 28, 7, cloud)
            painter.fillRect(cx + 18, cy - 5, 14, 5, cloud)
            painter.fillRect(cx + 4, cy + 7, 40, 4, cloud)
        self._draw_weather(painter, bounds, now)
        if night_weight > 0.12:
            alpha = round(180 * night_weight)
            for index in range(5):
                fx = bounds.left() + (index * 173 + int(now * (7 + index))) % max(1, w)
                fy = bounds.top() + int(h * (0.64 + 0.08 * math.sin(now * 1.3 + index)))
                firefly = QColor("#d7e990" if index % 2 else "#a5ded1")
                firefly.setAlpha(alpha)
                painter.fillRect(fx, fy, 3, 3, firefly)
        elif period_name(local_time, self.day_cycle_config) in {"manha", "tarde"}:
            for index in range(3):
                phase = now * 1.8 + index * 2.1
                bx = bounds.left() + int(w * (0.18 + 0.27 * ((now * 0.025 + index * 0.31) % 1.0)))
                by = bounds.top() + int(h * (0.42 + 0.07 * math.sin(phase)))
                self._draw_butterfly(painter, bx, by, phase)

    @staticmethod
    def _draw_static_scene(painter: QPainter, w: int, h: int,
                           sky: QColor, horizon: QColor, far: QColor,
                           near: QColor, night_weight: float) -> None:
        night = night_weight >= 0.55
        painter.fillRect(0, int(h * 0.31), w, max(1, int(h * 0.27)), horizon)
        sky_band_height = max(2, int(h * 0.31) // 6)
        for band in range(1, 6):
            shade = QColor(sky)
            shade.setAlpha(13 if band % 2 else 8)
            y = band * sky_band_height
            painter.fillRect(0, y, w, sky_band_height, shade)
        # A sparse, deterministic dither softens the sky bands without adding
        # texture to the bird or foreground art.
        dot_step = max(7, h // 42)
        dot = QColor("#eef7e5" if not night else "#b6cde5")
        dot.setAlpha(24)
        for row in range(5, max(6, int(h * 0.30)), dot_step):
            offset = (row // dot_step * 5) % 17
            for column in range(offset, w, 17):
                if (column // 17 + row // dot_step) % 3 == 0:
                    painter.fillRect(column, row, 1, 1, dot)
        # Three overlapping landscape planes add depth without moving the Piu.
        far_y = int(h * 0.65)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(far)
        painter.drawPolygon([
            QPoint(0, far_y + 20), QPoint(int(w * 0.20), far_y - 24),
            QPoint(int(w * 0.37), far_y + 4), QPoint(int(w * 0.61), far_y - 30),
            QPoint(int(w * 0.83), far_y + 9), QPoint(w, far_y - 12),
            QPoint(w, h), QPoint(0, h)])
        middle = QColor(far)
        middle.setRed(max(0, min(255, middle.red() - (12 if night else 8))))
        middle.setGreen(max(0, min(255, middle.green() - (8 if night else 4))))
        middle.setBlue(max(0, min(255, middle.blue() + (3 if night else 0))))
        painter.setBrush(middle)
        painter.drawPolygon([
            QPoint(0, int(h * 0.75)), QPoint(int(w * 0.19), int(h * 0.68)),
            QPoint(int(w * 0.36), int(h * 0.73)), QPoint(int(w * 0.58), int(h * 0.66)),
            QPoint(int(w * 0.78), int(h * 0.74)), QPoint(w, int(h * 0.68)),
            QPoint(w, int(h * 0.80)), QPoint(0, int(h * 0.80))])
        # Distant cottage with a warm pixel window.
        house_x, house_y = int(w * 0.70), int(h * 0.59)
        painter.fillRect(house_x, house_y + 12, 34, 25, QColor("#b99877"))
        painter.setBrush(QColor("#684c55" if night else "#8c5d57"))
        painter.drawPolygon([QPoint(house_x - 4, house_y + 13),
                             QPoint(house_x + 17, house_y),
                             QPoint(house_x + 38, house_y + 13)])
        painter.fillRect(house_x + 7, house_y + 20, 7, 8,
                         QColor("#ffe5a1" if night else "#87c7d0"))
        painter.fillRect(house_x + 22, house_y + 20, 7, 17, QColor("#694b48"))
        # Layered tree silhouettes frame the view.
        for tx, ty, size in ((int(w * 0.12), int(h * 0.64), 1.0),
                             (int(w * 0.88), int(h * 0.61), 0.82)):
            trunk_h = int(36 * size)
            painter.fillRect(tx + 9, ty + 19, 5, trunk_h, QColor("#70503f"))
            foliage = QColor("#3e725b" if not night else "#375a59")
            painter.fillRect(tx, ty + 7, 22, 16, foliage)
            painter.fillRect(tx + 4, ty, 15, 22, foliage)
            painter.fillRect(tx + 2, ty + 12, 20, 11, foliage)
        painter.fillRect(0, int(h * 0.79), w, int(h * 0.21), near)
        grass = QColor("#a2c978" if not night else "#597856")
        painter.fillRect(0, int(h * 0.79), w, 5, grass)
        # Branch and two pixel foliage clusters are the Piu's consistent landing perch.
        branch_y = int(h * 0.815)
        painter.fillRect(0, branch_y, w, 7, QColor("#72533e"))
        painter.fillRect(0, branch_y + 7, w, 2, QColor("#4b3b3c"))
        for fx in range(28, w, max(45, w // 11)):
            leaf = QColor("#7aae66" if not night else "#496b69")
            painter.fillRect(fx, branch_y - 9, 8, 5, leaf)
            painter.fillRect(fx + 4, branch_y - 13, 7, 5, leaf)
        # Short fence and three flower shapes sit on the near plane.
        fence_y = int(h * 0.755)
        painter.fillRect(int(w * 0.36), fence_y + 8, int(w * 0.18), 3,
                         QColor("#92745b"))
        painter.fillRect(int(w * 0.36), fence_y + 17, int(w * 0.18), 3,
                         QColor("#92745b"))
        for fx in (int(w * 0.37), int(w * 0.42), int(w * 0.49), int(w * 0.53)):
            painter.fillRect(fx, fence_y, 3, 23, QColor("#a18567"))
        stream_y = int(h * 0.775)
        painter.fillRect(int(w * 0.57), stream_y, int(w * 0.18), 6,
                         QColor("#578fa0" if night else "#76c9d2"))
        painter.fillRect(int(w * 0.60), stream_y + 1, int(w * 0.09), 2,
                         QColor("#b6e7dc"))
        for fx, flower in ((int(w * 0.08), "#f7cb81"),
                           (int(w * 0.61), "#ef9eaa"),
                           (int(w * 0.82), "#e5d889")):
            flower_y = int(h * 0.79) - 9
            painter.fillRect(fx + 3, flower_y + 5, 2, 8, QColor("#396b4d"))
            painter.fillRect(fx + 1, flower_y + 1, 3, 3, QColor(flower))
            painter.fillRect(fx + 5, flower_y + 1, 3, 3, QColor(flower))
            painter.fillRect(fx + 3, flower_y - 1, 3, 3, QColor(flower))
            painter.fillRect(fx + 3, flower_y + 2, 3, 3, QColor("#fff0bd"))
        for fx in range(20, w, max(71, w // 8)):
            painter.fillRect(fx, int(h * 0.91), 3, 7, QColor("#2f604c"))
            painter.fillRect(fx - 3, int(h * 0.90), 9, 3, QColor("#f7cb81"))
            painter.fillRect(fx - 1, int(h * 0.895), 4, 4, QColor("#fff0bd"))
        # A small post-it on the post marks the companion's home without stealing focus.
        post_x, post_y = int(w * 0.91), int(h * 0.55)
        painter.fillRect(post_x, post_y, 5, int(h * 0.25), QColor("#76563e"))
        painter.fillRect(post_x - 12, post_y + 8, 24, 18, QColor("#fff0a0"))
        painter.fillRect(post_x - 8, post_y + 12, 14, 2, QColor("#917a4e"))
        painter.fillRect(post_x - 8, post_y + 17, 10, 2, QColor("#917a4e"))

    def _draw_solar_objects(self, painter: QPainter, bounds: QRect,
                            local_time: datetime, sky: QColor,
                            night_weight: float, now: float) -> None:
        w, h = bounds.width(), bounds.height()
        sun = sun_position(local_time, self.day_cycle_config)
        if sun is not None:
            fraction, altitude = sun
            x = bounds.left() + int(w * (0.07 + 0.86 * fraction))
            y = bounds.top() + int(h * (0.34 - 0.22 * altitude))
            halo = QColor("#ffe8a0")
            halo.setAlpha(40)
            painter.fillRect(x - 20, y - 20, 40, 40, halo)
            painter.fillRect(x - 14, y - 14, 28, 28, QColor("#f9ca77"))
            painter.fillRect(x - 9, y - 9, 18, 18, QColor("#fff0a1"))
            painter.fillRect(x - 15, y - 5, 30, 10, QColor("#fff0a1"))
        moon = moon_position(local_time, self.day_cycle_config)
        if moon is not None:
            fraction, altitude = moon
            x = bounds.left() + int(w * (0.09 + 0.82 * fraction))
            y = bounds.top() + int(h * (0.34 - 0.20 * altitude))
            size = 20
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#f8edc6"))
            painter.drawEllipse(x - size // 2, y - size // 2, size, size)
            illumination = (1.0 - math.cos(2.0 * math.pi
                                           * moon_phase(local_time))) / 2.0
            shadow_width = round(size * (1.0 - illumination))
            if shadow_width > 0:
                waxing = moon_phase(local_time) < 0.5
                shadow_x = x - size // 2 + (0 if waxing else size - shadow_width)
                painter.setBrush(sky)
                painter.drawEllipse(shadow_x, y - size // 2,
                                    max(1, shadow_width), size)
        star_alpha = round(max(0.0, min(1.0, night_weight)) * 210)
        if star_alpha:
            for index in range(22):
                sx = bounds.left() + (index * 97 + 23) % max(1, w)
                sy = bounds.top() + (index * 43 + 17) % max(1, int(h * 0.52))
                star = QColor("#ffe9a3" if index % 3 == 0 else "#d4ecdb")
                star.setAlpha(star_alpha)
                size = 2 if index % 4 == 0 else 1
                painter.fillRect(sx, sy, size, size, star)

    def _draw_weather(self, painter: QPainter, bounds: QRect, now: float) -> None:
        density = self.weather_density
        if self.weather_mode == "rain":
            painter.save()
            rain = QColor("#d5efff")
            rain.setAlpha(100)
            painter.setPen(QPen(rain, 1))
            count = max(1, round(18 * density))
            for index in range(count):
                x = bounds.left() + (index * 67 + int(now * 74)) % max(1, bounds.width())
                y = bounds.top() + (index * 41 + int(now * 130)) % max(1, bounds.height())
                painter.drawLine(x, y, x - 2, y + 6)
            painter.restore()
        elif self.weather_mode == "fog":
            fog = QColor(220, 235, 232, round(75 * density))
            painter.fillRect(bounds.left(), bounds.top() + int(bounds.height() * 0.52),
                             bounds.width(), int(bounds.height() * 0.24), fog)

    @staticmethod
    def _draw_butterfly(painter: QPainter, x: int, y: int,
                        phase: float) -> None:
        wing = QColor("#e8b6dc" if math.sin(phase) > 0 else "#f0d887")
        painter.fillRect(x - 3, y, 3, 3, wing)
        painter.fillRect(x + 1, y, 3, 3, wing)
        painter.fillRect(x, y, 2, 4, QColor("#59445f"))

    def _schedule_mood_motion(self, state: VisualState, now: float) -> None:
        self._next_idle_action = now + self._rng.uniform(8.0, 14.0)
        if state.emotion == "alegre" and self._rng.random() < 0.38:
            self.request_move("center", "jump")
        elif state.emotion == "curioso" and self._rng.random() < 0.55:
            self.request_move("far" if self.motion.frame.depth < 0.4 else "camera",
                              "away" if self.motion.frame.depth < 0.4 else "return")
        elif state.emotion == "estressado" and self._rng.random() < 0.32:
            side = "left" if self.motion.frame.x > 0.5 else "right"
            self.request_move(side, "run")

    def _select_pose(self, state: VisualState, motion: MotionFrame,
                     now: float) -> tuple[str, int, bool]:
        routes = self._manifest.get("routes", {})
        action_route = routes.get("actions", {}).get(motion.action)
        if action_route is not None:
            return self._route_frame(action_route, motion, now)

        emotion = state.expression_override or state.emotion
        if now < self._blink_until:
            emotion = "piscar"
        aliases = {"sleeping": "dormindo", "sleepy": "sonolento",
                   "blink": "piscar", "happy": "alegre",
                   "stressed": "estressado", "curious": "curioso",
                   "startled": "assustado", "sad": "triste"}
        emotion = aliases.get(str(emotion).lower(), str(emotion).lower())
        if emotion == "alegre" and state.dopamine > 0.1:
            emotion = "cantando"
        if emotion == "curioso":
            gaze_x, _gaze_y = self._gaze_target
            if self._pointer_over and gaze_x < 0.38:
                emotion = "curioso_esquerda"
            elif self._pointer_over and gaze_x > 0.62:
                emotion = "curioso_direita"
        emotion_route = routes.get("emotions", {}).get(emotion)
        if emotion_route is not None:
            return self._route_frame(emotion_route, motion, now)
        view_route = routes.get("views", {}).get(motion.view)
        if view_route is not None:
            return self._route_frame(view_route, motion, now)
        return self._route_frame(routes.get("default", {
            "animation": "virada_vistas", "frame": "perfil"}), motion, now)

    def _route_frame(self, route: dict[str, object], motion: MotionFrame,
                     now: float) -> tuple[str, int, bool]:
        """Resolve an animation mapping from the editable JSON manifest."""
        group = str(route.get("animation", ""))
        animation = self._manifest.get("animations", {}).get(group)
        if not animation or not animation.get("frames"):
            fallback = self._manifest.get("routes", {}).get("default", {})
            fallback_group = str(fallback.get("animation", "virada_vistas"))
            animation = self._manifest["animations"][fallback_group]
            group = fallback_group
            route = fallback
        frames = animation["frames"]
        mode = str(route.get("mode", "frame"))
        candidates = list(range(len(frames)))
        if "frame" in route:
            frame_name = str(route["frame"]).lower()
            named = [position for position, frame in enumerate(frames)
                     if frame.get("label_key", "") == frame_name]
            if named:
                candidates = named
        if bool(route.get("match_lod", False)):
            nearest = min(abs(int(frames[position].get("native_size", 32))
                              - motion.lod_size) for position in candidates)
            candidates = [position for position in candidates
                          if abs(int(frames[position].get("native_size", 32))
                                 - motion.lod_size) == nearest]
            # Do not allow malformed metadata to turn a valid route into an
            # empty candidate set.
            if not candidates:
                candidates = [0]
        if mode == "progress":
            offset = min(len(candidates) - 1,
                         int(motion.progress * len(candidates)))
            index = candidates[offset]
        elif mode == "time_loop":
            if (self._audio_music_active and self._audio_bpm > 0.0
                    and group.startswith("danca_")):
                offset = min(len(candidates) - 1,
                             int(self._audio_beat_phase * len(candidates)))
                index = candidates[offset]
            else:
                durations = [max(1, int(frames[position].get("duration_ms", 100)))
                             for position in candidates]
                elapsed = int(max(0.0, now) * 1000.0) % sum(durations)
                offset = 0
                for offset, duration in enumerate(durations):
                    if elapsed < duration:
                        break
                    elapsed -= duration
                index = candidates[offset]
        elif mode == "stride":
            index = candidates[PetMotionController.frame_index(
                motion, len(candidates))]
        elif "frame" in route:
            index = candidates[0]
        else:
            index = candidates[0]
        return group, index, False

    def _source_rect(self, group: str, index: int, use_lod: bool,
                     motion: MotionFrame) -> tuple[str, QRect | None]:
        if use_lod:
            view = {"profile": "profile", "back": "back", "front": "front"}.get(
                motion.view, "profile")
            action = "run" if motion.action == "run" else "idle"
            entries = self._manifest["lod"]["entries"][f"{view}_{action}"]
            selected = min(entries, key=lambda item: abs(item["size"] - motion.lod_size))
            self._current_frame_entry = selected
            return self._manifest["lod"]["sheet"], QRect(*selected["rect"])
        entry = self._manifest["animations"][group]["frames"][index]
        self._current_frame_entry = entry
        return self._manifest["animations"][group]["sheet"], QRect(*entry["rect"])

    def _draw_shadow(self, painter: QPainter, destination: QRect,
                     motion: MotionFrame, local_time: datetime) -> None:
        width = max(12, int(destination.width() * (0.50 - motion.depth * 0.18)))
        height = max(3, destination.height() // 24)
        x = destination.center().x() - width // 2
        y = destination.bottom() - height // 2
        alpha = max(45, 110 - int(motion.height * 300))
        period = period_name(local_time, self.day_cycle_config)
        shadow = (QColor("#182b49") if period in {"madrugada", "noite"} else
                  QColor("#604c55") if period == "entardecer" else
                  QColor("#293d40"))
        shadow.setAlpha(alpha)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        highlight = QColor(shadow)
        highlight.setAlpha(alpha // 2)
        painter.setBrush(highlight)
        painter.drawEllipse(QRect(x + 2, y + height, width - 4, 3))
        painter.setBrush(shadow)
        painter.drawEllipse(QRect(x, y, width, height))
        painter.restore()

    def _draw_pet_tint(self, painter: QPainter, destination: QRect,
                       local_time: datetime) -> None:
        period = period_name(local_time, self.day_cycle_config)
        tone = (QColor("#aac9ff") if period in {"madrugada", "noite"} else
                QColor("#ffd1a1") if period == "entardecer" else
                QColor("#dcfff0"))
        tone.setAlpha(9 if period in {"madrugada", "noite"} else 7)
        painter.save()
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceAtop)
        painter.fillRect(destination, tone)
        painter.restore()

    def _draw_depth_occlusion(self, painter: QPainter, bounds: QRect,
                              motion: MotionFrame) -> None:
        w, h = bounds.width(), bounds.height()
        # The post-it post is behind the bird nearby and in front when the bird
        # is farther away and crosses its horizontal span.
        post_x, post_y = int(w * 0.91), int(h * 0.55)
        near_post = abs(motion.x - 0.91) < 0.12
        if motion.depth > 0.56 and near_post:
            painter.fillRect(post_x, post_y, 5, int(h * 0.25), QColor("#76563e"))
            painter.fillRect(post_x - 12, post_y + 8, 24, 18, QColor("#fff0a0"))
            painter.fillRect(post_x - 8, post_y + 12, 14, 2, QColor("#917a4e"))
            painter.fillRect(post_x - 8, post_y + 17, 10, 2, QColor("#917a4e"))
        if motion.depth < 0.3:
            for fx, fy in ((0.15, 0.86), (0.72, 0.89), (0.94, 0.87)):
                if abs(motion.x - fx) < 0.17:
                    x, y = int(w * fx), int(h * fy)
                    green = QColor("#386744")
                    for dx, dy in ((0, 0), (4, -5), (-4, -7), (1, -11)):
                        painter.fillRect(x + dx, y + dy, 3, 8, green)

    @staticmethod
    def _draw_pixel_heart(painter: QPainter, rect: QRect, now: float) -> None:
        x = rect.center().x() + int(math.sin(now * 2.0) * rect.width() * 0.28)
        y = rect.top() + int(rect.height() * 0.24)
        color = QColor("#f28b91")
        for dx, dy in ((1, 0), (3, 0), (0, 1), (1, 1), (2, 1), (3, 1),
                       (4, 1), (1, 2), (2, 2), (3, 2), (2, 3)):
            painter.fillRect(x + dx * 2, y + dy * 2, 2, 2, color)

    @staticmethod
    def _draw_snn_sparks(painter: QPainter, rect: QRect,
                         state: VisualState, now: float) -> None:
        for index, neuron_id in enumerate(state.spike_ids[:12]):
            phase = (int(neuron_id) * 1.618 + now * (1.5 + index * 0.02)) % 6.28
            radius = 0.58 + 0.08 * (index % 3)
            x = rect.center().x() + int(math.cos(phase) * rect.width() * radius)
            y = rect.center().y() + int(math.sin(phase) * rect.height() * radius)
            color = QColor("#fff0a1" if index % 2 else "#b6f1ec")
            painter.fillRect(x, y, 2, 2, color)

    def _draw_hud(self, painter: QPainter, bounds: QRect,
                  state: VisualState, local_time: datetime) -> None:
        key = (bounds.size(), state.emotion, round(state.happiness * 100),
               local_time.hour, local_time.minute)
        if self._hud_cache is None or self._hud_cache_key != key:
            self._hud_cache = QImage(
                bounds.size(), QImage.Format.Format_ARGB32_Premultiplied)
            self._hud_cache.fill(Qt.GlobalColor.transparent)
            cache_painter = QPainter(self._hud_cache)
            cache_painter.fillRect(12, 12, 240, 45, QColor(20, 33, 56, 210))
            cache_painter.setPen(QPen(QColor("#e8d48d"), 1))
            cache_painter.drawRect(12, 12, 240, 45)
            font = QFont(self._font_family, 9)
            cache_painter.setFont(font)
            cache_painter.setPen(QColor("#f5edcf"))
            period = period_name(local_time, self.day_cycle_config).upper()
            period = period.replace("MANHA", "MANHÃ")
            cache_painter.drawText(22, 31, f"PIU  /  {period[:15]}")
            cache_painter.drawText(
                22, 48, f"HUMOR {round(state.happiness * 100):02d}%  "
                f"{local_time:%H:%M}")
            cache_painter.end()
            self._hud_cache_key = key
        painter.drawImage(bounds.topLeft(), self._hud_cache)

    def sprite_mask(self, size: QSize | None = None) -> QRegion:
        """Return a click-through mask from the currently displayed sprite alpha."""
        bounds = QRect(QPoint(0, 0), size) if size is not None else self.rect()
        if bounds.isEmpty():
            return QRegion()
        # PetWindow asks for its native mask while entering floating mode,
        # before Qt has resized the stacked child to the floating window. Render
        # once at the requested mask size so the alpha region and first frame
        # share the same coordinates.
        if (self._current_source is None
                or self._current_frame_size != bounds.size()
                or self._mask_geometry_key is None):
            self._render_half_resolution(
                bounds.width(), bounds.height(), time.monotonic(),
                datetime.now().astimezone())
        if self._current_source is None:
            return QRegion()
        image = QImage(bounds.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        sheet_name, source_rect = self._current_source
        destination = self._current_destination
        if self._current_mirror:
            painter.translate(destination.left() * 2 + destination.width(), 0)
            painter.scale(-1.0, 1.0)
        painter.drawImage(destination, self._sheets[sheet_name], source_rect)
        painter.end()
        alpha_mask = image.createAlphaMask()
        bitmap = QBitmap.fromImage(alpha_mask)
        region = QRegion(bitmap)
        for badge_rect in self._audio_badge_rects:
            region = region.united(QRegion(badge_rect))
        return region

    def current_frame(self) -> QImage:
        return self.render_frame()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.panelRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:
        point = event.position()
        self._pointer_over = self.rect().contains(point.toPoint())
        self._gaze_target = (point.x() / max(1, self.width()),
                             point.y() / max(1, self.height()))
        if self._drag_tracker.move(
                point.x(), point.y(), self.width(), self.height(),
                bool(event.buttons() & Qt.MouseButton.LeftButton)):
            self.petRequested.emit()
        self.activityDetected.emit()
        self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        point = event.position()
        self._drag_tracker.press(
            point.x(), point.y(), self.width(), self.height(),
            event.button() == Qt.MouseButton.LeftButton)
        if event.button() == Qt.MouseButton.RightButton:
            self.panelRequested.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_tracker.release():
            self.petRequested.emit()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._pointer_over = False
        self._drag_tracker.cancel()
        super().leaveEvent(event)

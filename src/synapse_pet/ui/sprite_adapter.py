from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage, QPainter


@dataclass(frozen=True, slots=True)
class SpriteFrame:
    animation: str
    index: int
    source: QRect
    destination: QRect
    flipped: bool


class SpriteAdapter:
    """Time-based nearest-neighbour renderer for a row-based sprite atlas."""

    def __init__(self, asset_dir: Path) -> None:
        self.asset_dir = Path(asset_dir)
        self.atlas_path = self.asset_dir / "pet_atlas.json"
        self.atlas = json.loads(self.atlas_path.read_text(encoding="utf-8"))
        self.frame_width = int(self.atlas["frame_width"])
        self.frame_height = int(self.atlas["frame_height"])
        self.anchor_x = int(self.atlas["anchor_x"])
        self.anchor_y = int(self.atlas["anchor_y"])
        self.columns = int(self.atlas["columns"])
        self.rows = int(self.atlas["rows"])
        self.animations: dict[str, dict[str, object]] = self.atlas["animations"]
        sheet_name = str(self.atlas["sheet"])
        self.sheet_name = sheet_name
        self.sheet = QImage(str(self.asset_dir / sheet_name))
        if self.sheet.isNull():
            raise FileNotFoundError(self.asset_dir / sheet_name)
        expected_size = (self.columns * self.frame_width,
                         self.rows * self.frame_height)
        if (self.sheet.width(), self.sheet.height()) != expected_size:
            raise ValueError(
                f"Sprite sheet size {self.sheet.width()}x{self.sheet.height()} "
                f"does not match atlas grid {expected_size[0]}x{expected_size[1]}.")
        self._validate_animations()

        self._requested_animation: str | None = None
        self._base_animation: str | None = None
        self._base_started_at = 0.0
        self._completed_request: str | None = None
        self._fallback_animation = "idle"
        self._override_animation: str | None = None
        self._override_started_at = 0.0
        self._completed_override: str | None = None
        self._flip = False
        self.last_draw: SpriteFrame | None = None

    def _validate_animations(self) -> None:
        for name, entry in self.animations.items():
            row = int(entry["row"])
            frames = int(entry["frames"])
            fps = float(entry["fps"])
            if (not 0 <= row < self.rows or not 1 <= frames <= self.columns
                    or not math.isfinite(fps) or fps <= 0):
                raise ValueError(f"Invalid sprite animation metadata: {name}")

    @staticmethod
    def normalize_scale(scale: float) -> float:
        """Quantize to half-pixel scale steps to keep pixel art crisp."""
        value = max(0.5, min(8.0, float(scale)))
        return round(value * 2.0) / 2.0

    def play(self, animation_name: str, now: float | None = None,
             *, fallback: str = "idle") -> bool:
        """Select a base animation without restarting an animation already playing."""
        now = 0.0 if now is None else float(now)
        if animation_name not in self.animations:
            animation_name = "idle"
        if fallback not in self.animations:
            fallback = "idle"
        if animation_name != self._requested_animation:
            self._requested_animation = animation_name
            self._completed_request = None
        self._fallback_animation = fallback
        if self._completed_request == animation_name:
            if self._base_animation != fallback:
                self._base_animation = fallback
                self._base_started_at = now
            return False
        if self._base_animation != animation_name:
            self._base_animation = animation_name
            self._base_started_at = now
        return True

    def set_override(self, animation_name: str | None,
                     now: float | None = None) -> None:
        """Temporarily play an action animation over the mapped state animation."""
        now = 0.0 if now is None else float(now)
        if animation_name is None:
            self._override_animation = None
            self._completed_override = None
            return
        if animation_name not in self.animations:
            return
        if animation_name != self._completed_override:
            if animation_name != self._override_animation:
                self._override_animation = animation_name
                self._override_started_at = now
                self._completed_override = None

    def flip(self, enabled: bool) -> None:
        self._flip = bool(enabled)

    def _frame_index(self, animation_name: str, started_at: float,
                     now: float) -> tuple[int, bool]:
        entry = self.animations[animation_name]
        frames = int(entry["frames"])
        fps = float(entry["fps"])
        elapsed = max(0.0, now - started_at)
        raw_index = int(math.floor(elapsed * fps))
        if bool(entry.get("loop", True)):
            return raw_index % frames, False
        if raw_index >= frames:
            return frames - 1, True
        return raw_index, False

    def draw(self, painter: QPainter, position: QPoint | tuple[float, float],
             scale: float, now: float, animation_name: str | None = None,
             *, fallback: str = "idle",
             frame_index_override: int | None = None) -> SpriteFrame:
        """Draw one frame with ``position`` at the feet/atlas anchor.

        The source image stays loaded and frames are cropped directly from it;
        no scaled or per-tick QImage allocations are made.
        """
        now = float(now)
        if animation_name is not None:
            self.play(animation_name, now, fallback=fallback)
        if self._base_animation is None:
            self.play("idle", now)

        if self._override_animation is not None:
            active_name = self._override_animation
            active_started = self._override_started_at
            active_index, complete = self._frame_index(active_name, active_started, now)
            if complete:
                self._completed_override = active_name
                self._override_animation = None

        if self._override_animation is None:
            active_name = self._base_animation or "idle"
            active_started = self._base_started_at
            active_index, complete = self._frame_index(active_name, active_started, now)
            if complete:
                self._completed_request = self._requested_animation
                self._base_animation = self._fallback_animation
                self._base_started_at = now
                active_name = self._base_animation
                active_index = 0

        entry = self.animations[active_name]
        if frame_index_override is not None:
            active_index = max(0, min(int(entry["frames"]) - 1,
                                      int(frame_index_override)))
        row = int(entry["row"])
        frame_width, frame_height = self.frame_width, self.frame_height
        source = QRect(active_index * frame_width, row * frame_height,
                       frame_width, frame_height)
        quantized_scale = self.normalize_scale(scale)
        dest_width = round(frame_width * quantized_scale)
        dest_height = round(frame_height * quantized_scale)
        anchor_x, anchor_y = position if isinstance(position, tuple) else (
            position.x(), position.y())
        destination = QRect(round(anchor_x - self.anchor_x * quantized_scale),
                            round(anchor_y - self.anchor_y * quantized_scale),
                            dest_width, dest_height)

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.save()
        if self._flip:
            painter.translate(destination.left() + destination.width(),
                              destination.top())
            painter.scale(-1.0, 1.0)
            painter.drawImage(QRect(0, 0, dest_width, dest_height),
                              self.sheet, source)
        else:
            painter.drawImage(destination, self.sheet, source)
        painter.restore()

        result = SpriteFrame(active_name, active_index, source,
                             destination, self._flip)
        self.last_draw = result
        return result

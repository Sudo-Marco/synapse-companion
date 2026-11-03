from __future__ import annotations

import math
import time


class AffectionDragTracker:
    """Recognize a deliberate left-button drag held over the eye for long enough."""

    def __init__(self, minimum_seconds: float = 1.0, minimum_distance_px: float = 6.0) -> None:
        self.minimum_seconds = max(0.1, float(minimum_seconds))
        self.minimum_distance_px = max(1.0, float(minimum_distance_px))
        self.started_at: float | None = None
        self.origin: tuple[float, float] | None = None
        self.moved = False
        self.triggered = False

    @staticmethod
    def _over_eye(x: float, y: float, width: float, height: float) -> bool:
        if width <= 0 or height <= 0:
            return False
        nx, ny = x / width, y / height
        return 0.12 <= nx <= 0.88 and 0.20 <= ny <= 0.88

    def press(self, x: float, y: float, width: float, height: float,
              left_button: bool, now: float | None = None) -> None:
        self.cancel()
        if left_button and self._over_eye(x, y, width, height):
            self.started_at = time.monotonic() if now is None else float(now)
            self.origin = (float(x), float(y))

    def move(self, x: float, y: float, width: float, height: float,
             left_button: bool, now: float | None = None) -> bool:
        if self.started_at is None or self.origin is None or not left_button:
            return False
        if not self._over_eye(x, y, width, height):
            self.cancel()
            return False
        x, y = float(x), float(y)
        if math.hypot(x - self.origin[0], y - self.origin[1]) >= self.minimum_distance_px:
            self.moved = True
        current = time.monotonic() if now is None else float(now)
        if (self.moved and not self.triggered
                and current - self.started_at >= self.minimum_seconds):
            self.triggered = True
            return True
        return False

    def release(self, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else float(now)
        qualifies = (
            self.started_at is not None and self.moved and not self.triggered
            and current - self.started_at >= self.minimum_seconds)
        self.cancel()
        return qualifies

    def cancel(self) -> None:
        self.started_at = None
        self.origin = None
        self.moved = False
        self.triggered = False

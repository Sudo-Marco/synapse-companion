from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True, slots=True)
class WorkArea:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


def clamp_window_top_left(x: int, y: int, window_width: int,
                          window_height: int, area: WorkArea) -> tuple[int, int]:
    """Keep the full pet window inside a monitor's taskbar-free work area."""
    max_x = area.right - max(1, int(window_width))
    max_y = area.bottom - max(1, int(window_height))
    return (max(area.left, min(int(x), max_x)),
            max(area.top, min(int(y), max_y)))


def desktop_depth(center_y: int, area: WorkArea) -> float:
    """Map the top of a work area to far (1) and the bottom to near (0)."""
    if area.height <= 1:
        return 0.0
    fraction = (int(center_y) - area.top) / (area.height - 1)
    return max(0.0, min(1.0, 1.0 - fraction))


def choose_work_area_target(areas: list[WorkArea], current: tuple[int, int],
                            window_size: tuple[int, int], rng: random.Random,
                            *, far: bool | None = None) -> tuple[int, int, int]:
    """Choose a valid top-left point and return the chosen monitor index."""
    if not areas:
        raise ValueError("at least one work area is required")
    width, height = map(int, window_size)
    index = rng.randrange(len(areas))
    area = areas[index]
    x = rng.randint(area.left, max(area.left, area.right - width))
    if far is True:
        y = round(area.top + area.height * rng.uniform(0.10, 0.32))
    elif far is False:
        y = round(area.top + area.height * rng.uniform(0.62, 0.86))
    else:
        y = round(area.top + area.height * rng.uniform(0.16, 0.80))
    x, y = clamp_window_top_left(x, y, width, height, area)
    if math.hypot(x - current[0], y - current[1]) < 90 and len(areas) == 1:
        x, y = clamp_window_top_left(x + 120, y + 45, width, height, area)
    return index, x, y


class DesktopBehaviorSelector:
    """Deterministic utility selector with per-action cooldown and hourly cap."""

    WINDOW = 3600.0

    def __init__(self, config: dict[str, object] | None = None,
                 *, seed: int = 41) -> None:
        config = config or {}
        self.enabled = bool(config.get("enabled", True))
        self.max_per_hour = max(1, int(config.get("max_actions_per_hour", 8)))
        self.cooldowns = {str(key): max(0.0, float(value)) for key, value in
                          dict(config.get("cooldowns_s", {})).items()}
        self.behaviors = dict(config.get("actions", config.get("behaviors", {})))
        self.rng = random.Random(int(seed) ^ 0x504555)
        self._recent: deque[tuple[float, str]] = deque()
        self._last: dict[str, float] = {}

    def choose(self, emotion: str, stamina: float, now: float, *,
               window_available: bool = False) -> str | None:
        if not self.enabled:
            return None
        while self._recent and now - self._recent[0][0] >= self.WINDOW:
            self._recent.popleft()
        if len(self._recent) >= self.max_per_hour:
            return None
        choices: list[tuple[str, float]] = []
        for name, raw in self.behaviors.items():
            behavior = dict(raw)
            weight = max(0.0, float(behavior.get("weight", 0.0)))
            if weight == 0.0:
                continue
            if stamina < float(behavior.get("min_stamina", 0.0)):
                continue
            if stamina > float(behavior.get("max_stamina", 1.0)):
                continue
            emotions = tuple(str(value) for value in behavior.get("emotions", ()))
            if emotions and emotion not in emotions:
                continue
            if behavior.get("requires_window", False) and not window_available:
                continue
            cooldown = max(float(behavior.get("cooldown_s", 0.0)),
                           self.cooldowns.get(str(name), 0.0))
            if now - self._last.get(str(name), -math.inf) < cooldown:
                continue
            choices.append((str(name), weight))
        total = sum(weight for _, weight in choices)
        if total <= 0.0:
            return None
        pick = self.rng.random() * total
        for name, weight in choices:
            pick -= weight
            if pick <= 0.0:
                self._last[name] = float(now)
                self._recent.append((float(now), name))
                return name
        return None


__all__ = ["DesktopBehaviorSelector", "WorkArea", "choose_work_area_target",
           "clamp_window_top_left", "desktop_depth"]

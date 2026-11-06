from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class MotionFrame:
    x: float = 0.5
    depth: float = 0.08
    height: float = 0.0
    action: str = "idle"
    view: str = "profile"
    lod_size: int = 32
    facing: int = 1
    stride_phase: float = 0.0
    traveled_px: float = 0.0
    progress: float = 0.0


class PetMotionController:
    """Small deterministic scene-space movement controller for the pixel pet."""

    TARGETS = {
        "left": (0.18, 0.08), "right": (0.82, 0.08),
        "center": (0.50, 0.08), "far": (0.50, 0.92),
        "camera": (0.50, 0.04),
    }
    ACTIONS = {"walk", "run", "jump", "away", "return", "fly"}
    SPEED = {"walk": 90.0, "run": 180.0, "jump": 120.0,
             "away": 150.0, "return": 150.0, "fly": 130.0}
    STRIDE_DISTANCE_PX = 24.0

    def __init__(self, *, pivot: tuple[int, int] = (16, 40)) -> None:
        self.pivot = tuple(map(int, pivot))
        self._frame = MotionFrame()
        self._start = (self._frame.x, self._frame.depth)
        self._target = self._start
        self._elapsed = 0.0
        self._duration = 0.0
        self._style = "walk"
        self._blocked = False

    @property
    def frame(self) -> MotionFrame:
        return self._frame

    @property
    def moving(self) -> bool:
        return self._duration > 0.0

    @property
    def blocked(self) -> bool:
        return self._blocked

    def set_blocked(self, *, dragging: bool = False,
                    proposal_pending: bool = False) -> None:
        self._blocked = bool(dragging or proposal_pending)

    def request_move(self, target: str | tuple[float, float], style: str = "walk",
                     *, dragging: bool = False,
                     proposal_pending: bool = False) -> bool:
        self.set_blocked(dragging=dragging, proposal_pending=proposal_pending)
        action = str(style).strip().lower()
        if self._blocked or action not in self.ACTIONS:
            return False
        if isinstance(target, str):
            if target not in self.TARGETS:
                return False
            tx, td = self.TARGETS[target]
        else:
            if len(target) != 2:
                return False
            tx, td = map(float, target)
        tx = max(0.04, min(0.96, tx))
        td = max(0.0, min(1.0, td))
        self._start = (self._frame.x, self._frame.depth)
        self._target = (tx, td)
        self._elapsed = 0.0
        pixel_distance = math.hypot((tx - self._frame.x) * 800.0,
                                    (td - self._frame.depth) * 180.0)
        minimum_duration = 0.55 if action in {"jump", "fly"} else 0.18
        self._duration = max(minimum_duration, pixel_distance / self.SPEED[action])
        self._style = action
        view = "back" if action == "away" else "front" if action == "return" else "profile"
        facing = -1 if tx < self._frame.x else 1
        self._frame = MotionFrame(
            x=self._frame.x, depth=self._frame.depth, height=0.0,
            action=action, view=view, lod_size=self._frame.lod_size,
            facing=facing, stride_phase=self._frame.stride_phase,
            traveled_px=self._frame.traveled_px, progress=0.0)
        return True

    def advance(self, dt_s: float, *, viewport_width: int = 800,
                sprite_scale: int = 1) -> MotionFrame:
        dt = max(0.0, min(0.25, float(dt_s)))
        if self._duration <= 0.0 or self._blocked:
            return self._frame
        previous_x, previous_depth = self._frame.x, self._frame.depth
        self._elapsed = min(self._duration, self._elapsed + dt)
        linear = self._elapsed / max(self._duration, 1e-6)
        eased = linear * linear * (3.0 - 2.0 * linear)
        x = self._start[0] + (self._target[0] - self._start[0]) * eased
        depth = self._start[1] + (self._target[1] - self._start[1]) * eased
        scale = max(1, int(sprite_scale))
        distance = (abs(x - previous_x) * max(1, int(viewport_width))
                    + abs(depth - previous_depth) * 180.0) * scale
        traveled = self._frame.traveled_px + distance
        phase = (traveled / (self.STRIDE_DISTANCE_PX * scale)) * 8.0
        height = (math.sin(math.pi * linear) * 0.18
                  if self._style in {"jump", "fly"} else 0.0)

        # Hysteresis prevents a sprite from flickering at LOD boundaries.
        size = self._frame.lod_size
        if size == 32 and depth > 0.43:
            size = 24
        elif size == 24:
            if depth < 0.35:
                size = 32
            elif depth > 0.75:
                size = 16
        elif size == 16 and depth < 0.67:
            size = 24

        action = self._style
        view = "back" if action == "away" else "front" if action == "return" else "profile"
        if linear >= 1.0:
            self._duration = 0.0
            action = "idle"
            # Keep the destination-facing view for the settled pose.
        self._frame = MotionFrame(x=x, depth=depth, height=height,
                                  action=action, view=view, lod_size=size,
                                  facing=-1 if self._target[0] < self._start[0] else 1,
                                  stride_phase=phase, traveled_px=traveled,
                                  progress=linear)
        return self._frame

    @classmethod
    def frame_index(cls, frame: MotionFrame, frame_count: int) -> int:
        if frame_count <= 0:
            return 0
        return int(math.floor(frame.stride_phase)) % frame_count

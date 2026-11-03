from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
import time
from .manifest import ToolManifest

@dataclass
class PermissionManager:
    max_automatic_per_hour: int = 6
    _actions: deque[float] = field(default_factory=deque)
    silence_until: float = 0.0

    def authorize(self, tool: ToolManifest, *, accepted: bool = False,
                  explicit: bool = False, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else now
        while self._actions and t - self._actions[0] >= 3600:
            self._actions.popleft()
        if tool.risk == "high":
            return explicit
        if tool.risk == "medium":
            return accepted
        if explicit:
            return True
        if t < self.silence_until or len(self._actions) >= self.max_automatic_per_hour:
            return False
        self._actions.append(t)
        return True

    def feedback(self, accepted: bool, now: float | None = None) -> None:
        t = time.monotonic() if now is None else now
        if not accepted:
            self.silence_until = max(self.silence_until, t + 120.0)

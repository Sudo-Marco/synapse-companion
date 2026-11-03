from __future__ import annotations
from dataclasses import dataclass

@dataclass
class RuntimeScheduler:
    active_timeout_s: float = 20.0
    last_stimulus_s: float = 0.0

    def stimulus(self, now_s: float) -> None:
        self.last_stimulus_s = now_s

    def regime(self, now_s: float, sleeping: bool = False) -> str:
        if sleeping:
            return "sono"
        return "ativo" if now_s - self.last_stimulus_s < self.active_timeout_s else "repouso"

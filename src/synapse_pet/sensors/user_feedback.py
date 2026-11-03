from __future__ import annotations
from dataclasses import dataclass

@dataclass
class UserFeedback:
    """Small explicit-feedback adapter used by the GUI and command line."""
    reward: float = 0.0

    def give(self, value: float) -> None:
        self.reward = max(-1.0, min(1.0, value))

    def consume(self) -> float:
        value, self.reward = self.reward, 0.0
        return value

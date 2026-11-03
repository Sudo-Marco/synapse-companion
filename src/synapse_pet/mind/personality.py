from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np

TRAITS = ("reward_sensitivity", "punishment_sensitivity", "curiosity", "sociability",
          "startle", "persistence", "initiative", "caution")

@dataclass
class Personality:
    reward_sensitivity: float = 0.55
    punishment_sensitivity: float = 0.55
    curiosity: float = 0.60
    sociability: float = 0.50
    startle: float = 0.45
    persistence: float = 0.50
    initiative: float = 0.35
    caution: float = 0.70
    seed: int = 41

    @classmethod
    def seeded(cls, seed: int = 41, preset: dict[str, float] | None = None) -> "Personality":
        rng = np.random.default_rng(seed)
        values = {name: float(np.clip(rng.normal(0.5, 0.12), 0, 1)) for name in TRAITS}
        values.update(preset or {})
        return cls(**values, seed=seed)

    def update(self, reward: float, action_was_suggestion: bool = False,
               days_elapsed: float = 1.0) -> None:
        rate = min(0.01, max(0.0, 0.001 * days_elapsed))
        if reward > 0:
            self.sociability += rate * reward * 0.1
            self.reward_sensitivity += rate * reward * 0.05
        elif action_was_suggestion:
            self.caution += rate * min(1.0, abs(reward)) * 0.1
            self.initiative -= rate * min(1.0, abs(reward)) * 0.1
        for name in TRAITS:
            setattr(self, name, float(np.clip(getattr(self, name), 0, 1)))

    def snapshot(self) -> dict[str, float | int]:
        return asdict(self)

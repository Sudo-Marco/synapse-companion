from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class ActionCandidate:
    name: str
    neural_score: float
    risk: str = "low"
    context: str = "default"

@dataclass
class ActionSelector:
    threshold: float = 0.2
    initiative_threshold: float = 0.5
    neural_score_scale_hz: float = 15.0
    min_silence_s: float = 120.0
    feedback_rate: float = 0.30
    preferences: dict[tuple[str, str], float] = field(default_factory=dict)
    refusal_streak: int = 0

    def choose(self, candidates: list[ActionCandidate], initiative: float,
               explicit: bool = False) -> ActionCandidate | None:
        eligible = [c for c in candidates if c.neural_score >= self.threshold]
        if not eligible or (initiative < self.initiative_threshold and not explicit):
            return None
        def score(c: ActionCandidate) -> float:
            scale = max(1e-6, float(self.neural_score_scale_hz))
            neural = min(1.0, max(0.0, c.neural_score / scale))
            return neural + self.preferences.get((c.context, c.name), 0.0)
        return max(eligible, key=score)

    def feedback(self, context: str, action: str, reward: float) -> None:
        key = (context, action)
        rate = max(0.0, float(self.feedback_rate))
        self.preferences[key] = max(-1.0, min(1.0, self.preferences.get(key, 0.0) + rate * reward))
        self.refusal_streak = self.refusal_streak + 1 if reward < 0 else 0
        if self.refusal_streak >= 3:
            self.min_silence_s = min(3600.0, self.min_silence_s * 1.5)

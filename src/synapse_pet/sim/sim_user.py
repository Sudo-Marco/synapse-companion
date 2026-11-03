from __future__ import annotations
from dataclasses import dataclass
from ..mind.action_selection import ActionCandidate, ActionSelector

@dataclass
class SimEpisode:
    context: str
    preferred: str
    rejected: str

class SimUser:
    """Toy user for fast contextual preference and reversal experiments."""
    def run(self, episodes: int = 300, reverse_at: int | None = None) -> tuple[ActionSelector, list[float]]:
        selector = ActionSelector(threshold=0.0)
        correctness: list[float] = []
        for i in range(episodes):
            preferred = "A" if reverse_at is None or i < reverse_at else "B"
            options = [ActionCandidate("A", .5, context="X"), ActionCandidate("B", .5, context="X")]
            choice = selector.choose(options, initiative=1.0, explicit=True)
            assert choice is not None
            good = float(choice.name == preferred)
            selector.feedback("X", choice.name, 1.0 if good else -1.0)
            correctness.append(good)
        return selector, correctness

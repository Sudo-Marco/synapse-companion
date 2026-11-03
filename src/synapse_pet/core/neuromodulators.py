from __future__ import annotations
from dataclasses import dataclass
from math import exp


@dataclass
class Neuromodulators:
    dopamine: float = 0.0
    stress: float = 0.15
    mood: float = 0.5
    energy: float = 0.8
    expected_reward: dict[str, float] | None = None
    mood_fast_component: float | None = None
    mood_slow_component: float | None = None

    def __post_init__(self) -> None:
        if self.expected_reward is None:
            self.expected_reward = {}
        if self.mood_fast_component is None:
            self.mood_fast_component = float(self.mood) - 0.5
        if self.mood_slow_component is None:
            self.mood_slow_component = 0.0

    def prediction_error(self, context_key: str, reward: float, rate: float = 0.05) -> float:
        """Return the reward prediction error and update that context's expectation."""
        assert self.expected_reward is not None
        rate = min(1.0, max(0.0, float(rate)))
        expected = self.expected_reward.get(context_key, 0.0)
        error = float(reward - expected)
        self.expected_reward[context_key] = expected + rate * error
        self.dopamine = error
        return error

    def _sync_mood_components(self) -> None:
        assert self.mood_fast_component is not None
        assert self.mood_slow_component is not None
        represented = 0.5 + self.mood_fast_component + self.mood_slow_component
        if abs(float(self.mood) - represented) > 1e-8:
            self.mood_fast_component += float(self.mood) - represented

    def add_mood_impulse(self, amount: float, slow_fraction: float = 0.2) -> float:
        """Add a mood impulse with a soft ceiling and fast/slow decay components."""
        self._sync_mood_components()
        amount = float(amount)
        if amount > 0.0:
            amount *= max(0.0, 1.0 - float(self.mood))
        amount = max(-float(self.mood), min(1.0 - float(self.mood), amount))
        slow_fraction = min(1.0, max(0.0, float(slow_fraction)))
        assert self.mood_fast_component is not None
        assert self.mood_slow_component is not None
        self.mood_fast_component += amount * (1.0 - slow_fraction)
        self.mood_slow_component += amount * slow_fraction
        self.mood = min(1.0, max(0.0,
                                  0.5 + self.mood_fast_component
                                  + self.mood_slow_component))
        return amount

    def update(self, dt_s: float, activity: float = 0.0,
               relax_fast_tau_s: float = 240.0,
               relax_slow_tau_s: float = 1800.0,
               positive_mood_budget: float | None = None) -> float:
        """Relax mood through fast/slow components; return positive dopamine mood used."""
        dt_s = max(0.0, float(dt_s))
        if (self.dopamine == 0.0 and self.mood == 0.5
                and self.mood_fast_component == 0.0
                and self.mood_slow_component == 0.0):
            self.stress = min(1.0, max(0.0,
                self.stress + 0.02 * activity * dt_s - 0.01 * dt_s))
            self.energy = min(1.0, max(0.0,
                self.energy - 0.001 * activity * dt_s + 0.0005 * dt_s))
            return 0.0
        self._sync_mood_components()
        fast_tau = max(1.0, float(relax_fast_tau_s))
        slow_tau = max(fast_tau, float(relax_slow_tau_s))
        self.dopamine *= exp(-dt_s / 0.35)
        self.stress = min(1.0, max(0.0,
            self.stress + 0.02 * activity * dt_s - 0.01 * dt_s))
        assert self.mood_fast_component is not None
        assert self.mood_slow_component is not None
        if abs(self.mood_fast_component) > 1e-10:
            self.mood_fast_component *= exp(-dt_s / fast_tau)
        if abs(self.mood_slow_component) > 1e-10:
            self.mood_slow_component *= exp(-dt_s / slow_tau)
        mood_gain = 0.002 * self.dopamine * dt_s
        if mood_gain > 0.0:
            mood_gain *= max(0.0, 1.0 - float(self.mood))
            if positive_mood_budget is not None:
                mood_gain = min(mood_gain, max(0.0, float(positive_mood_budget)))
        self.mood_fast_component += mood_gain
        self.mood = min(1.0, max(0.0,
            0.5 + self.mood_fast_component + self.mood_slow_component))
        self.energy = min(1.0, max(0.0,
            self.energy - 0.001 * activity * dt_s + 0.0005 * dt_s))
        return max(0.0, mood_gain)

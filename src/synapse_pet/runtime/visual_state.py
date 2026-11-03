from __future__ import annotations

from dataclasses import dataclass, replace
import math
import time


@dataclass(frozen=True, slots=True)
class VisualState:
    """Immutable UI snapshot published by the simulation thread."""

    happiness: float = 0.5
    energy: float = 0.8
    stress: float = 0.15
    curiosity: float = 0.5
    boredom: float = 0.2
    affection: float = 0.3
    trust: float = 0.5
    dopamine: float = 0.0
    firing_rate: float = 0.0
    spike_ids: tuple[int, ...] = ()
    active_neurons: tuple[int, ...] = ()
    rates: tuple[tuple[str, float], ...] = ()
    tick_count: int = 0
    render_fps: float = 0.0
    neuron_count: int = 0
    recurrent_edges: int = 0
    output_start: int = 0
    expression_override: str = ""
    active: bool = False
    updated_at: float = 0.0

    @property
    def emotion(self) -> str:
        if self.expression_override:
            return self.expression_override
        if self.stress >= 0.62:
            return "estressado"
        if self.happiness >= 0.72:
            return "alegre"
        if self.happiness <= 0.32 or self.boredom >= 0.82:
            return "triste"
        if self.energy <= 0.18:
            return "sonolento"
        if self.curiosity >= 0.78:
            return "curioso"
        return "observando"

    @classmethod
    def from_engine(cls, engine: object, spikes, firing_rate: float,
                    active: bool) -> VisualState:
        emotions = engine.emotions
        rates = tuple(sorted((str(key), float(value))
                             for key, value in engine.last_rates.items()))
        maximum = max(0, int(engine.visual_config.get("max_particles", 48)))
        active_ids = tuple(int(i) for i in spikes.nonzero()[0])
        ids = active_ids[:maximum]
        return cls(
            happiness=float(emotions.happiness),
            energy=float(emotions.energy),
            stress=float(emotions.fear),
            curiosity=float(emotions.curiosity),
            boredom=float(emotions.boredom),
            affection=float(emotions.affection),
            trust=float(emotions.trust),
            dopamine=float(engine.neuromodulators.dopamine),
            firing_rate=float(firing_rate),
            spike_ids=ids,
            active_neurons=active_ids,
            rates=rates,
            tick_count=int(engine.network.tick_count),
            neuron_count=int(engine.network.population.size),
            recurrent_edges=len(engine.network.recurrent.weights),
            output_start=int(engine.network.output_start),
            active=bool(active),
            updated_at=time.monotonic(),
        )


class StateAnimator:
    """Exponential interpolation for emotional uniforms between SNN snapshots."""

    SMOOTH_FIELDS = ("happiness", "energy", "stress", "curiosity", "boredom",
                     "affection", "dopamine", "firing_rate")

    def __init__(self, initial: VisualState | None = None, seconds: float = 0.16) -> None:
        self.value = initial or VisualState()
        self.seconds = max(0.02, seconds)
        self.last_time: float | None = None

    def advance(self, target: VisualState, now: float) -> VisualState:
        dt = 1.0 / 30.0 if self.last_time is None else max(0.0, min(0.5, now - self.last_time))
        self.last_time = now
        blend = 1.0 - math.exp(-dt / self.seconds)
        changes = {name: getattr(self.value, name)
                   + (getattr(target, name) - getattr(self.value, name)) * blend
                   for name in self.SMOOTH_FIELDS}
        self.value = replace(target, **changes)
        return self.value

from __future__ import annotations
from dataclasses import dataclass
from math import exp
from ..core.neuromodulators import Neuromodulators

@dataclass
class EmotionState:
    happiness: float = 0.5
    energy: float = 0.8
    fear: float = 0.1
    curiosity: float = 0.5
    boredom: float = 0.2
    affection: float = 0.3
    trust: float = 0.5
    contact_comfort: float = 0.0
    recent_contact: float = 0.0

    def update(self, mod: Neuromodulators, activity: float, social_drive: float,
               dt_s: float = 0.25, contacted: bool = False,
               affect_impulse: float = 0.0,
               affect_happiness_gain: float = 0.10,
               curiosity_impulse: float = 0.0,
               curiosity_base: float = 0.25,
               curiosity_inactivity_gain: float = 0.40,
               curiosity_energy_gain: float = 0.15) -> None:
        clamp = lambda x: min(1.0, max(0.0, float(x)))
        if contacted:
            self.contact_comfort = 1.0
            self.affection = clamp(self.affection + 0.12 * (1.0 - self.affection))
            self.recent_contact = 1.0
        else:
            self.contact_comfort *= exp(-max(0.0, dt_s) / 180.0)
            self.recent_contact *= exp(-max(0.0, dt_s) / 4.0)
        dopamine_mood = 0.5 + mod.dopamine * 0.2
        affection_mood = 0.5 + (self.affection - 0.3)
        happiness_base = (
            0.50 * mod.mood + 0.35 * dopamine_mood + 0.15 * affection_mood)
        happiness_impulse = affect_happiness_gain * max(
            -1.0, min(1.0, affect_impulse))
        if happiness_impulse > 0.0:
            happiness_impulse *= 1.0 - self.happiness
        self.happiness = clamp(happiness_base + happiness_impulse)
        self.energy = clamp(mod.energy)
        self.fear = clamp(mod.stress)
        curiosity_baseline = (
            curiosity_base + curiosity_inactivity_gain * (1.0 - activity)
            + curiosity_energy_gain * mod.energy)
        self.curiosity = clamp(curiosity_baseline + max(0.0, curiosity_impulse))
        self.boredom = clamp(1.0 - activity - 0.25 * social_drive
                             - 0.45 * self.contact_comfort)
        self.trust = clamp(0.995 * self.trust + 0.005 * (0.5 + mod.dopamine))

from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Drives:
    social: float = 0.3
    stimulation: float = 0.4
    rest: float = 0.1
    seconds_since_contact: float = 0.0

    def update(self, dt_s: float, activity: float, contacted: bool = False) -> None:
        self.seconds_since_contact = 0.0 if contacted else self.seconds_since_contact + dt_s
        self.social = min(1.0, self.social + dt_s / 7200.0)
        self.stimulation = min(1.0, max(0.0, self.stimulation + dt_s / 3600.0 - activity * dt_s / 1800.0))
        self.rest = min(1.0, max(0.0, self.rest + activity * dt_s / 7200.0 - (1.0 - activity) * dt_s / 14400.0))
        if contacted:
            self.social *= 0.2

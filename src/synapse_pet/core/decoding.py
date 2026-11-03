from __future__ import annotations
import numpy as np
from numpy.typing import NDArray

class RateDecoder:
    """Exponential moving-average firing-rate decoder by named neuron group.

    ``update`` accepts spike counts accumulated over the full observation window,
    so the measured rate does not depend on the final integration step.
    """
    def __init__(self, groups: dict[str, NDArray[np.int32]], tau_s: float = 0.25) -> None:
        self.groups = groups
        self.tau_s = tau_s
        self.rates = {name: 0.0 for name in groups}

    def update(self, spikes: NDArray[np.number], dt_s: float) -> dict[str, float]:
        alpha = 1.0 - np.exp(-dt_s / self.tau_s)
        for name, indices in self.groups.items():
            sample = float(spikes[indices].mean() / dt_s) if len(indices) else 0.0
            self.rates[name] += alpha * (sample - self.rates[name])
        return dict(self.rates)

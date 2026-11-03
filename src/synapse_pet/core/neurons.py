from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float32]
BoolArray = NDArray[np.bool_]

@dataclass
class LIFPopulation:
    """Vectorized leaky integrate-and-fire state for one population."""
    size: int
    tau_m_ms: float = 20.0
    threshold: float = 1.0
    reset: float = 0.0
    refractory_ms: float = 2.0
    adaptive_increment: float = 0.05
    adaptive_tau_ms: float = 200.0

    def __post_init__(self) -> None:
        self.voltage: FloatArray = np.zeros(self.size, dtype=np.float32)
        self.threshold_offset: FloatArray = np.zeros(self.size, dtype=np.float32)
        self.refractory: FloatArray = np.zeros(self.size, dtype=np.float32)
        self.spikes: BoolArray = np.zeros(self.size, dtype=np.bool_)
        self.rng = np.random.default_rng()

    def step(self, current: FloatArray, dt_ms: float, rng: np.random.Generator,
             noise_std: float = 0.0, gain: float = 1.0) -> BoolArray:
        if current.shape != (self.size,):
            raise ValueError(f"current must have shape ({self.size},)")
        active = self.refractory <= 0.0
        self.voltage *= np.float32(np.exp(-dt_ms / self.tau_m_ms))
        if gain == 1.0:
            self.voltage += current
        else:
            self.voltage += current * np.float32(gain)
        if noise_std:
            noise = rng.standard_normal(self.size, dtype=np.float32)
            noise *= np.float32(noise_std)
            self.voltage += noise
        # Refractory cells remain at reset despite vectorized integration above.
        self.voltage[~active] = self.reset
        self.threshold_offset *= np.float32(np.exp(-dt_ms / self.adaptive_tau_ms))
        np.greater_equal(self.voltage, self.threshold + self.threshold_offset, out=self.spikes)
        np.logical_and(self.spikes, active, out=self.spikes)
        fired = self.spikes
        self.voltage[fired] = self.reset
        self.threshold_offset[fired] += self.adaptive_increment
        np.subtract(self.refractory, np.float32(dt_ms), out=self.refractory)
        np.maximum(self.refractory, 0.0, out=self.refractory)
        self.refractory[fired] = self.refractory_ms
        return self.spikes.copy()

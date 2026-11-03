from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .neurons import LIFPopulation
from .synapses import SparseProjection

@dataclass
class Homeostasis:
    target_hz: float = 5.0
    low_hz: float = 1.0
    high_hz: float = 15.0
    window_s: float = 5.0
    _count: float = 0.0
    _elapsed: float = 0.0

    def update(self, population: LIFPopulation, spikes: np.ndarray, dt_s: float,
               projections: tuple[SparseProjection, ...] = ()) -> list[str]:
        self._count += float(spikes.sum())
        self._elapsed += dt_s
        if self._elapsed < self.window_s:
            return []
        hz = self._count / max(self._elapsed * population.size, 1e-9)
        events: list[str] = []
        if hz > self.high_hz:
            population.threshold = min(2.0, population.threshold + 0.02)
            for projection in projections:
                projection.weights *= np.float32(0.98)
            events.append("epilepsia_detectada")
        elif hz < self.low_hz:
            population.threshold = max(0.5, population.threshold - 0.01)
            for projection in projections:
                projection.weights *= np.float32(1.02)
            events.append("silencio_detectado")
        else:
            # Slow intrinsic adaptation toward the firing-rate target.
            population.threshold = float(np.clip(
                population.threshold + (hz - self.target_hz) * 0.001, 0.5, 2.0))
        for projection in projections:
            projection.weights[:] = np.clip(projection.weights, -1.0, 1.0)
            projection.enforce_dale()
        self._count = self._elapsed = 0.0
        return events

from __future__ import annotations
import hashlib
import numpy as np
from numpy.typing import NDArray

class PopulationEncoder:
    """Encode numeric and categorical context as Poisson spike trains."""
    def __init__(self, groups: dict[str, int], seed: int = 0,
                 min_rate_hz: float = 0.1, max_rate_hz: float = 80.0) -> None:
        self.groups = dict(groups)
        self.offsets: dict[str, slice] = {}
        start = 0
        for key, count in self.groups.items():
            if count < 1:
                raise ValueError("each encoding group must contain at least one neuron")
            self.offsets[key] = slice(start, start + count)
            start += count
        self.size = start
        self.rng = np.random.default_rng(seed)
        self.min_rate_hz, self.max_rate_hz = min_rate_hz, max_rate_hz

    def rates(self, context: dict[str, object]) -> NDArray[np.float32]:
        result = np.full(self.size, self.min_rate_hz, dtype=np.float32)
        for key, span in self.offsets.items():
            count = span.stop - span.start
            value = context.get(key, 0.0)
            if isinstance(value, str):
                # Two independent hash projections make categorical collisions
                # much less likely than a single one-hot index in small groups.
                digest = hashlib.blake2b(f"{key}:{value}".encode(), digest_size=8).digest()
                first = int.from_bytes(digest[:4], "little") % count
                second = int.from_bytes(digest[4:], "little") % count
                if second == first:
                    second = (second + 1) % count
                local = np.full(count, self.min_rate_hz, dtype=np.float32)
                local[first] = self.max_rate_hz
                local[second] = self.min_rate_hz + (self.max_rate_hz - self.min_rate_hz) * 0.65
            else:
                x = float(np.clip(float(value), 0.0, 1.0))
                centers = np.linspace(0.0, 1.0, count)
                local = self.min_rate_hz + (self.max_rate_hz - self.min_rate_hz) * np.exp(-((centers - x) ** 2) / 0.04)
            result[span] = local
        return result

    def encode(self, context: dict[str, object], dt_ms: float) -> NDArray[np.bool_]:
        probability = np.clip(self.rates(context) * (dt_ms / 1000.0), 0.0, 1.0)
        return self.rng.random(self.size) < probability

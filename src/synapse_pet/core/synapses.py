from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from numpy.typing import NDArray

@dataclass
class SparseProjection:
    """CSR sparse projection whose data array is the plastic weight vector."""
    n_pre: int
    n_post: int
    pre: NDArray[np.int32]
    post: NDArray[np.int32]
    weights: NDArray[np.float32]
    source_sign: NDArray[np.float32]
    name: str = "projection"
    _matrix: object | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.rebuild()

    @classmethod
    def random(cls, n_pre: int, n_post: int, probability: float,
               rng: np.random.Generator, source_sign: NDArray[np.float32] | None = None,
               scale: float = 0.12, name: str = "projection") -> "SparseProjection":
        post, pre = np.nonzero(rng.random((n_post, n_pre)) < probability)
        pre, post = pre.astype(np.int32), post.astype(np.int32)
        signs = np.ones(n_pre, dtype=np.float32) if source_sign is None else source_sign.astype(np.float32)
        weights = rng.uniform(0.02, scale, len(pre)).astype(np.float32) * signs[pre]
        return cls(n_pre, n_post, pre, post, weights, signs, name)

    def rebuild(self) -> None:
        """Build CSR once; learning then mutates its data array directly."""
        try:
            from scipy.sparse import csr_matrix
        except ImportError:
            self._matrix = None
            return
        matrix = csr_matrix((self.weights, (self.post, self.pre)),
                            shape=(self.n_post, self.n_pre), dtype=np.float32)
        matrix.sum_duplicates()
        matrix.sort_indices()
        self._matrix = matrix
        self.weights = matrix.data
        self.pre = matrix.indices.astype(np.int32, copy=False)
        self.post = np.repeat(np.arange(self.n_post, dtype=np.int32),
                              np.diff(matrix.indptr)).astype(np.int32, copy=False)

    def bind_weights(self, weights: NDArray[np.float32]) -> None:
        """Swap weight data without rebuilding the shared sparse topology."""
        if weights.shape != self.weights.shape:
            raise ValueError("weight vector shape does not match sparse projection")
        self.weights = weights
        if self._matrix is not None:
            self._matrix.data = weights

    def currents(self, spikes: NDArray[np.bool_]) -> NDArray[np.float32]:
        if len(spikes) != self.n_pre:
            raise ValueError("spike vector does not match projection input size")
        if self._matrix is not None:
            return np.asarray(self._matrix @ spikes, dtype=np.float32).reshape(-1)
        return np.bincount(self.post, weights=self.weights * spikes[self.pre],
                           minlength=self.n_post).astype(np.float32)

    def enforce_dale(self) -> None:
        self.weights[:] = np.abs(self.weights) * self.source_sign[self.pre]

    def grow_targets(self, count: int) -> None:
        if count < 0:
            raise ValueError("count must be non-negative")
        self.n_post += count
        self.rebuild()

    def normalize(self, target_l1: float, limits: tuple[float, float]) -> None:
        sums = np.bincount(self.post, weights=np.abs(self.weights), minlength=self.n_post)
        factors = np.divide(target_l1, sums, out=np.ones_like(sums), where=sums > 1e-8)
        self.weights *= factors[self.post].astype(np.float32)
        self.weights[:] = np.clip(self.weights, limits[0], limits[1])
        self.enforce_dale()

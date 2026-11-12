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
    _source_indptr: NDArray[np.int32] | None = field(
        default=None, init=False, repr=False
    )
    _source_order: NDArray[np.int32] | None = field(
        default=None, init=False, repr=False
    )

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
        # Source-oriented indexing is derived only from topology. Invalidate it
        # whenever CSR is rebuilt; weight rebinding does not need invalidation.
        self._source_indptr = None
        self._source_order = None
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

    def source_index(self) -> tuple[NDArray[np.int32], NDArray[np.int32]]:
        """Return a lazy source-oriented edge index without copying weights.

        ``source_order`` contains indices into the canonical CSR data arrays,
        stably grouped by presynaptic neuron. It stores one int32 per edge and
        is invalidated by ``rebuild``; the plastic weight vector remains shared.
        """
        if self._source_indptr is None or self._source_order is None:
            if self.pre.shape != self.weights.shape:
                raise ValueError("presynaptic indices do not match sparse weights")
            if self.pre.size and (
                int(self.pre.min()) < 0 or int(self.pre.max()) >= self.n_pre
            ):
                raise ValueError("presynaptic index is outside projection bounds")
            if self.post.shape != self.weights.shape:
                raise ValueError("postsynaptic indices do not match sparse weights")
            if self.post.size and (
                int(self.post.min()) < 0 or int(self.post.max()) >= self.n_post
            ):
                raise ValueError("postsynaptic index is outside projection bounds")
            order = np.argsort(self.pre, kind="stable").astype(
                np.int32, copy=False
            )
            counts = np.bincount(self.pre, minlength=self.n_pre).astype(
                np.int32, copy=False
            )
            indptr = np.empty(self.n_pre + 1, dtype=np.int32)
            indptr[0] = 0
            np.cumsum(counts, dtype=np.int32, out=indptr[1:])
            self._source_order = order
            self._source_indptr = indptr
        return self._source_indptr, self._source_order

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

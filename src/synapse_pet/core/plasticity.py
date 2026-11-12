from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray
from .synapses import SparseProjection

@dataclass
class RewardSTDP:
    learning_rate: float = 5e-4
    eligibility_tau_s: float = 3.0
    a_plus: float = 0.01
    a_minus: float = 0.012

    def __post_init__(self) -> None:
        self.pre_trace: NDArray[np.float32] | None = None
        self.post_trace: NDArray[np.float32] | None = None
        self.eligibility: NDArray[np.float32] | None = None
        self._pre_spike_float: NDArray[np.float32] | None = None
        self._post_spike_float: NDArray[np.float32] | None = None

    def initialize(self, projection: SparseProjection) -> None:
        self.pre_trace = np.zeros(projection.n_pre, dtype=np.float32)
        self.post_trace = np.zeros(projection.n_post, dtype=np.float32)
        self.eligibility = np.zeros(len(projection.weights), dtype=np.float32)
        self._pre_spike_float = np.empty(projection.n_pre, dtype=np.float32)
        self._post_spike_float = np.empty(projection.n_post, dtype=np.float32)

    def mark(self, projection: SparseProjection, pre_spikes: NDArray[np.bool_],
             post_spikes: NDArray[np.bool_], dt_s: float) -> None:
        if (self.eligibility is None
                or self.eligibility.size != len(projection.weights)
                or self._pre_spike_float is None
                or self._pre_spike_float.shape != (projection.n_pre,)
                or self._post_spike_float is None
                or self._post_spike_float.shape != (projection.n_post,)):
            self.initialize(projection)
        assert (self.pre_trace is not None and self.post_trace is not None
                and self.eligibility is not None
                and self._pre_spike_float is not None
                and self._post_spike_float is not None)
        # Preserve the original float32 arithmetic without allocating two
        # converted spike arrays on every simulation substep.
        np.copyto(self._pre_spike_float, pre_spikes, casting="unsafe")
        np.copyto(self._post_spike_float, post_spikes, casting="unsafe")
        decay = np.float32(np.exp(-dt_s / self.eligibility_tau_s))
        self.pre_trace *= decay
        self.post_trace *= decay
        pre, post = self._pre_spike_float, self._post_spike_float
        self.eligibility *= decay
        self.eligibility += self.a_plus * self.pre_trace[projection.pre] * post[projection.post]
        self.eligibility -= self.a_minus * self.post_trace[projection.post] * pre[projection.pre]
        self.pre_trace += pre
        self.post_trace += post

    def apply_reward(self, projection: SparseProjection, dopamine: float,
                     limits: tuple[float, float] = (-1.0, 1.0)) -> None:
        if dopamine == 0.0 or self.eligibility is None:
            return
        if len(self.eligibility) != len(projection.weights):
            self.initialize(projection)
            return
        projection.weights += (self.learning_rate * dopamine * self.eligibility).astype(np.float32)
        projection.weights[:] = np.clip(projection.weights, limits[0], limits[1])
        projection.enforce_dale()

    def apply_action_credit(self, projection: SparseProjection, dopamine: float,
                            post_indices: NDArray[np.int32], pre_activity: NDArray[np.float32],
                            learning_rate: float,
                            limits: tuple[float, float] = (-1.0, 1.0)) -> None:
        """Associate recent presynaptic activity with the rewarded action output.

        The selected output group provides the missing action-specific credit
        assignment. Positive RPE strengthens active input to that group; negative
        RPE weakens it. Dale's law is re-applied after every update.
        """
        if dopamine == 0.0 or len(pre_activity) != projection.n_pre or not len(post_indices):
            return
        # Action groups normally contain valid output IDs. A dense lookup table
        # avoids np.isin's general-purpose setup cost and supports duplicate or
        # unsorted IDs. Keep np.isin as the compatibility path for out-of-range
        # values so they retain its non-raising behavior.
        if (post_indices.dtype.kind in "iu"
                and int(post_indices.min()) >= 0
                and int(post_indices.max()) < projection.n_post):
            selected = np.zeros(projection.n_post, dtype=np.bool_)
            selected[post_indices] = True
            post_mask = selected[projection.post]
        else:
            post_mask = np.isin(projection.post, post_indices, assume_unique=False)
        if not np.any(post_mask):
            return
        active_pre = np.clip(pre_activity[projection.pre], 0.0, 1.0)
        delta = (float(learning_rate) * float(dopamine)
                 * active_pre * post_mask.astype(np.float32))
        projection.weights += delta.astype(np.float32)
        projection.weights[:] = np.clip(projection.weights, limits[0], limits[1])
        projection.enforce_dale()

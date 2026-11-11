from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from .numpy_backend import NumpyBackend

if TYPE_CHECKING:
    from ..core.plasticity import RewardSTDP
    from ..core.synapses import SparseProjection


class CythonBackendUnavailable(RuntimeError):
    """Raised when the optional compiled STDP module cannot be loaded."""


class CythonBackend(NumpyBackend):
    """NumPy backend with the STDP update implemented by an optional Cython kernel.

    Neuron integration, sparse propagation, reward application and homeostasis
    intentionally remain the established NumPy operations in this phase.
    """

    name = "cython"

    def __init__(self, *, deterministic: bool = True) -> None:
        super().__init__(deterministic=deterministic)
        try:
            self._stdp = importlib.import_module(
                "synapse_pet.neural_backend._stdp"
            )
        except (ImportError, OSError) as exc:
            raise CythonBackendUnavailable(
                "The optional compiled Cython STDP kernel is unavailable; "
                "install/build the native extra or use the NumPy fallback."
            ) from exc

    def update_stdp(
        self,
        learner: RewardSTDP,
        projection: SparseProjection,
        pre_spikes: NDArray[np.bool_],
        post_spikes: NDArray[np.bool_],
        dt_s: float,
    ) -> None:
        # Mirror RewardSTDP.mark's shape guard and buffer initialization exactly.
        if (learner.eligibility is None
                or learner.eligibility.size != len(projection.weights)
                or learner._pre_spike_float is None
                or learner._pre_spike_float.shape != (projection.n_pre,)
                or learner._post_spike_float is None
                or learner._post_spike_float.shape != (projection.n_post,)):
            learner.initialize(projection)

        assert (learner.pre_trace is not None
                and learner.post_trace is not None
                and learner.eligibility is not None
                and learner._pre_spike_float is not None
                and learner._post_spike_float is not None)

        arrays = (
            projection.pre,
            projection.post,
            learner.pre_trace,
            learner.post_trace,
            learner.eligibility,
            learner._pre_spike_float,
            learner._post_spike_float,
        )
        expected_dtypes = (
            np.dtype(np.int32),
            np.dtype(np.int32),
            np.dtype(np.float32),
            np.dtype(np.float32),
            np.dtype(np.float32),
            np.dtype(np.float32),
            np.dtype(np.float32),
        )
        if not all(
            array.flags.c_contiguous and array.dtype == dtype
            for array, dtype in zip(arrays, expected_dtypes, strict=True)
        ):
            # Preserve support for unusual externally supplied views without
            # adding copies to the normal contiguous CSR hot path.
            super().update_stdp(
                learner, projection, pre_spikes, post_spikes, dt_s
            )
            return

        np.copyto(learner._pre_spike_float, pre_spikes, casting="unsafe")
        np.copyto(learner._post_spike_float, post_spikes, casting="unsafe")
        decay = np.float32(np.exp(-dt_s / learner.eligibility_tau_s))
        self._stdp.update_stdp(
            learner.pre_trace,
            learner.post_trace,
            learner.eligibility,
            learner._pre_spike_float,
            learner._post_spike_float,
            projection.pre,
            projection.post,
            decay,
            learner.a_plus,
            learner.a_minus,
        )

    def apply_reward(
        self,
        learner: RewardSTDP,
        projection: SparseProjection,
        dopamine: float,
    ) -> None:
        if dopamine == 0.0 or learner.eligibility is None:
            return
        if len(learner.eligibility) != len(projection.weights):
            learner.initialize(projection)
            return

        arrays = (
            projection.weights,
            projection.pre,
            projection.source_sign,
            learner.eligibility,
        )
        expected_dtypes = (
            np.dtype(np.float32),
            np.dtype(np.int32),
            np.dtype(np.float32),
            np.dtype(np.float32),
        )
        if not all(
            array.flags.c_contiguous and array.dtype == dtype
            for array, dtype in zip(arrays, expected_dtypes, strict=True)
        ):
            super().apply_reward(learner, projection, dopamine)
            return

        # Compute the Python-float product before its float32 conversion, as in
        # RewardSTDP.apply_reward's ``learning_rate * dopamine * eligibility``.
        scale = np.float32(learner.learning_rate * dopamine)
        self._stdp.apply_reward(
            projection.weights,
            learner.eligibility,
            projection.pre,
            projection.source_sign,
            scale,
            -1.0,
            1.0,
        )

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from .numpy_backend import NumpyBackend

if TYPE_CHECKING:
    from ..core.neurons import LIFPopulation
    from ..core.plasticity import RewardSTDP
    from ..core.synapses import SparseProjection


class CythonBackendUnavailable(RuntimeError):
    """Raised when the optional compiled neural modules cannot be loaded."""


class CythonBackend(NumpyBackend):
    """NumPy backend with optional Cython kernels for STDP, LIF and CSR.

    Action credit and homeostasis remain established NumPy operations.
    """

    name = "cython"
    # CI microbenchmarks show active-source traversal beats SciPy in at least
    # 89% of cases through 60% activity on both platforms; row CSR wins at 100%.
    ACTIVE_PROPAGATION_MAX_RATE = 0.60

    def __init__(self, *, deterministic: bool = True) -> None:
        super().__init__(deterministic=deterministic)
        try:
            self._stdp = importlib.import_module(
                "synapse_pet.neural_backend._stdp"
            )
            self._lif = importlib.import_module(
                "synapse_pet.neural_backend._lif"
            )
            self._sparse = importlib.import_module(
                "synapse_pet.neural_backend._sparse"
            )
        except (ImportError, OSError) as exc:
            raise CythonBackendUnavailable(
                "The optional compiled Cython STDP/LIF/CSR kernels are unavailable; "
                "install/build the native extra or use the NumPy fallback."
            ) from exc

    def propagate(
        self, projection: SparseProjection, spikes: NDArray[np.bool_]
    ) -> NDArray[np.float32]:
        if len(spikes) != projection.n_pre:
            raise ValueError("spike vector does not match projection input size")

        if (
            projection._matrix is None
            or not projection._compiled_csr_compatible
        ):
            return super().propagate(projection, spikes)
        if not (
            isinstance(spikes, np.ndarray)
            and spikes.dtype == np.bool_
            and spikes.ndim == 1
            and spikes.flags.c_contiguous
        ):
            return super().propagate(projection, spikes)

        matrix = projection._matrix
        active_count = int(np.count_nonzero(spikes))
        if active_count == 0:
            return np.zeros(projection.n_post, dtype=np.float32)
        if active_count / projection.n_pre <= self.ACTIVE_PROPAGATION_MAX_RATE:
            source_indptr, source_order = projection.source_index()
            return self._sparse.propagate_active(
                source_indptr,
                source_order,
                projection.post,
                projection.weights,
                spikes,
                projection.n_post,
            )

        return self._sparse.propagate_csr(
            matrix.indptr, matrix.indices, matrix.data, spikes
        )

    def step_neurons(
        self,
        population: LIFPopulation,
        current: NDArray[np.float32],
        dt_ms: float,
        rng: np.random.Generator,
        noise_std: float = 0.0,
        gain: float = 1.0,
    ) -> NDArray[np.bool_]:
        if current.shape != (population.size,):
            raise ValueError(f"current must have shape ({population.size},)")

        state_arrays = (
            population.voltage,
            population.threshold_offset,
            population.refractory,
            population.spikes,
        )
        if any(array.shape != (population.size,) for array in state_arrays):
            return super().step_neurons(
                population, current, dt_ms, rng, noise_std, gain
            )

        if not (
            population.voltage.flags.c_contiguous
            and population.voltage.dtype == np.float32
            and population.threshold_offset.flags.c_contiguous
            and population.threshold_offset.dtype == np.float32
            and population.refractory.flags.c_contiguous
            and population.refractory.dtype == np.float32
            and population.spikes.flags.c_contiguous
            and population.spikes.dtype == np.bool_
            and all(array.flags.owndata for array in state_arrays)
            and current.flags.c_contiguous
            and current.dtype == np.float32
        ):
            return super().step_neurons(
                population, current, dt_ms, rng, noise_std, gain
            )
        # Keep NumPy's sequential alias semantics when input reuses a state
        # buffer; independently owned states cannot alias each other.
        if any(np.shares_memory(current, state) for state in state_arrays[:3]):
            return super().step_neurons(
                population, current, dt_ms, rng, noise_std, gain
            )

        use_noise = bool(noise_std)
        noise = (
            rng.standard_normal(population.size, dtype=np.float32)
            if use_noise else current
        )
        decay = np.float32(np.exp(-dt_ms / population.tau_m_ms))
        adaptive_decay = np.float32(
            np.exp(-dt_ms / population.adaptive_tau_ms)
        )
        self._lif.step_lif(
            population.voltage,
            population.threshold_offset,
            population.refractory,
            population.spikes,
            current,
            noise,
            use_noise,
            decay,
            adaptive_decay,
            np.float32(dt_ms),
            np.float32(population.reset),
            np.float32(population.threshold),
            np.float32(population.adaptive_increment),
            np.float32(population.refractory_ms),
            np.float32(noise_std),
            np.float32(gain),
            gain != 1.0,
        )
        return population.spikes.copy()

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

        if not (
            projection.pre.flags.c_contiguous
            and projection.pre.dtype == np.int32
            and projection.post.flags.c_contiguous
            and projection.post.dtype == np.int32
            and learner.pre_trace.flags.c_contiguous
            and learner.pre_trace.dtype == np.float32
            and learner.post_trace.flags.c_contiguous
            and learner.post_trace.dtype == np.float32
            and learner.eligibility.flags.c_contiguous
            and learner.eligibility.dtype == np.float32
            and learner._pre_spike_float.flags.c_contiguous
            and learner._pre_spike_float.dtype == np.float32
            and learner._post_spike_float.flags.c_contiguous
            and learner._post_spike_float.dtype == np.float32
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

        if not (
            projection.weights.flags.c_contiguous
            and projection.weights.dtype == np.float32
            and projection.pre.flags.c_contiguous
            and projection.pre.dtype == np.int32
            and projection.source_sign.flags.c_contiguous
            and projection.source_sign.dtype == np.float32
            and learner.eligibility.flags.c_contiguous
            and learner.eligibility.dtype == np.float32
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

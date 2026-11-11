from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from .interface import NeuralBackend

if TYPE_CHECKING:
    from ..core.homeostasis import Homeostasis
    from ..core.neurons import LIFPopulation
    from ..core.plasticity import RewardSTDP
    from ..core.synapses import SparseProjection


class NumpyBackend(NeuralBackend):
    """Reference adapter around the established NumPy/SciPy implementation."""

    name = "numpy"

    def step_neurons(
        self,
        population: LIFPopulation,
        current: NDArray[np.float32],
        dt_ms: float,
        rng: np.random.Generator,
        noise_std: float = 0.0,
        gain: float = 1.0,
    ) -> NDArray[np.bool_]:
        return population.step(current, dt_ms, rng, noise_std, gain=gain)

    def propagate(
        self, projection: SparseProjection, spikes: NDArray[np.bool_]
    ) -> NDArray[np.float32]:
        return projection.currents(spikes)

    def update_stdp(
        self,
        learner: RewardSTDP,
        projection: SparseProjection,
        pre_spikes: NDArray[np.bool_],
        post_spikes: NDArray[np.bool_],
        dt_s: float,
    ) -> None:
        learner.mark(projection, pre_spikes, post_spikes, dt_s)

    def apply_reward(
        self, learner: RewardSTDP, projection: SparseProjection, dopamine: float
    ) -> None:
        learner.apply_reward(projection, dopamine)

    def apply_action_credit(
        self,
        learner: RewardSTDP,
        projection: SparseProjection,
        dopamine: float,
        post_indices: NDArray[np.int32],
        pre_activity: NDArray[np.float32],
        learning_rate: float,
    ) -> None:
        learner.apply_action_credit(
            projection,
            dopamine,
            post_indices,
            pre_activity,
            learning_rate=learning_rate,
        )

    def update_homeostasis(
        self,
        homeostasis: Homeostasis,
        population: LIFPopulation,
        spikes: NDArray[np.bool_],
        dt_s: float,
        projections: tuple[SparseProjection, ...] = (),
    ) -> list[str]:
        return homeostasis.update(population, spikes, dt_s, projections)

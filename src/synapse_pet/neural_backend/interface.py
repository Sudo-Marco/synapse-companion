from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from ..core.homeostasis import Homeostasis
    from ..core.neurons import LIFPopulation
    from ..core.plasticity import RewardSTDP
    from ..core.synapses import SparseProjection


class NeuralBackend(ABC):
    """Contract for numerical kernels used by the network and runtime.

    Implementations receive the existing NumPy-backed state objects. A backend
    must mutate only the same state that the reference operation mutates and
    must preserve the return ownership contract (notably copied spike output).
    """

    name = "abstract"
    precision = "float32"

    def __init__(self, *, deterministic: bool = True) -> None:
        self.deterministic = bool(deterministic)

    @abstractmethod
    def step_neurons(
        self,
        population: LIFPopulation,
        current: NDArray[np.float32],
        dt_ms: float,
        rng: np.random.Generator,
        noise_std: float = 0.0,
        gain: float = 1.0,
    ) -> NDArray[np.bool_]:
        """Advance a population by one fixed integration step."""

    @abstractmethod
    def propagate(
        self, projection: SparseProjection, spikes: NDArray[np.bool_]
    ) -> NDArray[np.float32]:
        """Compute postsynaptic current for one sparse projection."""

    @abstractmethod
    def update_stdp(
        self,
        learner: RewardSTDP,
        projection: SparseProjection,
        pre_spikes: NDArray[np.bool_],
        post_spikes: NDArray[np.bool_],
        dt_s: float,
    ) -> None:
        """Update STDP traces and eligibility for one integration step."""

    @abstractmethod
    def apply_reward(
        self,
        learner: RewardSTDP,
        projection: SparseProjection,
        dopamine: float,
    ) -> None:
        """Apply reward-modulated eligibility to a projection."""

    @abstractmethod
    def apply_action_credit(
        self,
        learner: RewardSTDP,
        projection: SparseProjection,
        dopamine: float,
        post_indices: NDArray[np.int32],
        pre_activity: NDArray[np.float32],
        learning_rate: float,
    ) -> None:
        """Apply reward to selected output edges."""

    @abstractmethod
    def update_homeostasis(
        self,
        homeostasis: Homeostasis,
        population: LIFPopulation,
        spikes: NDArray[np.bool_],
        dt_s: float,
        projections: tuple[SparseProjection, ...] = (),
    ) -> list[str]:
        """Run the current population homeostasis update."""

from __future__ import annotations

from .interface import NeuralBackend


class CythonBackendUnavailable(RuntimeError):
    """Raised until a compiled kernel implementation is installed."""


class CythonBackend(NeuralBackend):
    """Reserved adapter for optional compiled kernels.

    Phase 3 defines backend selection and the stable call contract. Numerical
    Cython kernels are intentionally introduced in the following kernel phases;
    selecting this backend therefore raises a clear availability error and lets
    the factory apply the configured NumPy fallback.
    """

    name = "cython"

    def __init__(self, *, deterministic: bool = True) -> None:
        raise CythonBackendUnavailable(
            "Cython kernels are not implemented yet; use the NumPy fallback "
            "or continue with the dedicated kernel phases."
        )

    def step_neurons(self, *args, **kwargs):
        raise CythonBackendUnavailable("Cython kernels are not available.")

    def propagate(self, *args, **kwargs):
        raise CythonBackendUnavailable("Cython kernels are not available.")

    def update_stdp(self, *args, **kwargs):
        raise CythonBackendUnavailable("Cython kernels are not available.")

    def apply_reward(self, *args, **kwargs):
        raise CythonBackendUnavailable("Cython kernels are not available.")

    def apply_action_credit(self, *args, **kwargs):
        raise CythonBackendUnavailable("Cython kernels are not available.")

    def update_homeostasis(self, *args, **kwargs):
        raise CythonBackendUnavailable("Cython kernels are not available.")

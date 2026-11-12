from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .cython_backend import CythonBackend, CythonBackendUnavailable
from .interface import NeuralBackend
from .numpy_backend import NumpyBackend


@dataclass(frozen=True)
class BackendSelection:
    """Resolved backend plus explicit information about any fallback."""

    backend: NeuralBackend
    requested_engine: str
    active_engine: str
    fallback: str
    fallback_reason: str | None
    precision: str
    deterministic: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "requested_engine": self.requested_engine,
            "active_engine": self.active_engine,
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
            "precision": self.precision,
            "deterministic": self.deterministic,
        }


def create_neural_backend(config: Mapping[str, object] | None = None) -> BackendSelection:
    """Resolve `numpy`, `cython`, or `auto` without hiding unavailable kernels.

    NumPy remains the stable reference path. Cython optionally accelerates LIF,
    STDP and CSR propagation; action credit and homeostasis remain NumPy.
    """
    settings = dict(config or {})
    requested = str(settings.get("engine", "numpy")).strip().lower()
    fallback = str(settings.get("fallback", "numpy")).strip().lower()
    precision = str(settings.get("precision", "float32")).strip().lower()
    deterministic = settings.get("deterministic", True)

    if requested not in {"numpy", "cython", "auto"}:
        raise ValueError("neural_backend.engine must be 'numpy', 'cython', or 'auto'")
    if fallback != "numpy":
        raise ValueError("neural_backend.fallback currently supports only 'numpy'")
    if precision != "float32":
        raise ValueError("only float32 precision is supported by the current SNN")
    if not isinstance(deterministic, bool):
        raise ValueError("neural_backend.deterministic must be a boolean")

    if requested == "numpy":
        backend = NumpyBackend(deterministic=deterministic)
        return BackendSelection(backend, requested, backend.name, fallback, None,
                                precision, deterministic)

    try:
        backend = CythonBackend(deterministic=deterministic)
    except CythonBackendUnavailable as exc:
        backend = NumpyBackend(deterministic=deterministic)
        return BackendSelection(backend, requested, backend.name, fallback,
                                str(exc), precision, deterministic)

    return BackendSelection(backend, requested, backend.name, fallback, None,
                            precision, deterministic)

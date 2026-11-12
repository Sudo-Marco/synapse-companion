"""Backend selection and kernel contracts for the SNN core.

The NumPy implementation is the reference and default backend. Compiled
kernels are optional and must preserve the same state transition semantics.
"""

from .factory import BackendSelection, create_neural_backend
from .interface import NeuralBackend
from .numpy_backend import NumpyBackend

__all__ = ["BackendSelection", "NeuralBackend", "NumpyBackend",
           "create_neural_backend"]

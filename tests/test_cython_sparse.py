from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip(
    "synapse_pet.neural_backend._stdp",
    reason="optional Cython extensions have not been built",
)
pytest.importorskip(
    "synapse_pet.neural_backend._lif",
    reason="optional Cython LIF extension has not been built",
)
pytest.importorskip(
    "synapse_pet.neural_backend._sparse",
    reason="optional Cython CSR extension has not been built",
)

from synapse_pet.core.synapses import SparseProjection
from synapse_pet.neural_backend.cython_backend import CythonBackend
from synapse_pet.neural_backend.numpy_backend import NumpyBackend


def _projection(
    n_pre: int, n_post: int, density: float, seed: int, *, recurrent: bool = False
):
    rng = np.random.default_rng(seed)
    if recurrent:
        assert n_pre == n_post
    post, pre = np.nonzero(rng.random((n_post, n_pre)) < density)
    source_sign = np.where(
        np.arange(n_pre) % 3 == 0, -1.0, 1.0
    ).astype(np.float32)
    weights = rng.uniform(0.01, 0.14, len(pre)).astype(np.float32)
    weights *= source_sign[pre]
    return SparseProjection(
        n_pre,
        n_post,
        pre.astype(np.int32),
        post.astype(np.int32),
        weights,
        source_sign,
        name="recurrent_test" if recurrent else "feedforward_test",
    )


@pytest.mark.parametrize(
    "n_pre,n_post,density,recurrent",
    [
        (24, 19, 0.0, False),
        (64, 64, 0.08, True),
        (96, 41, 0.35, False),
        (384, 384, 0.10, True),
        (160, 640, 0.10, False),
    ],
)
@pytest.mark.parametrize("rate", [0.0, 0.01, 0.08, 0.15, 0.4, 1.0])
def test_cython_sparse_strategies_are_bitwise_equal_to_scipy(
    n_pre, n_post, density, recurrent, rate
):
    projection = _projection(
        n_pre, n_post, density, seed=n_pre * 31 + n_post,
        recurrent=recurrent,
    )
    rng = np.random.default_rng(837)
    spikes = rng.random(n_pre) < rate
    backend = CythonBackend()

    expected = NumpyBackend().propagate(projection, spikes)
    actual = backend.propagate(projection, spikes)
    np.testing.assert_array_equal(actual, expected)

    source_indptr, source_order = projection.source_index()
    csr = backend._sparse.propagate_csr(
        projection._matrix.indptr,
        projection._matrix.indices,
        projection.weights,
        spikes,
    )
    active = backend._sparse.propagate_active(
        source_indptr,
        source_order,
        projection.post,
        projection.weights,
        spikes,
        projection.n_post,
    )
    np.testing.assert_array_equal(csr, expected)
    np.testing.assert_array_equal(active, expected)
    assert not np.shares_memory(actual, projection.weights)
    assert not np.shares_memory(actual, spikes)


def test_source_index_is_lazy_cached_and_rebuilt_with_topology():
    projection = _projection(32, 27, 0.2, seed=100)
    assert projection._compiled_csr_compatible
    assert projection._source_indptr is None
    assert projection._source_order is None
    original_weights = projection.weights
    first = projection.source_index()
    second = projection.source_index()
    assert first[0] is second[0]
    assert first[1] is second[1]
    assert len(first[1]) == len(projection.weights)
    assert np.shares_memory(original_weights, projection._matrix.data)
    assert not np.shares_memory(first[1], projection.weights)

    replacement = projection.weights.copy()
    projection.bind_weights(replacement)
    assert projection._compiled_csr_compatible
    assert projection._source_order is first[1]
    spikes = np.ones(projection.n_pre, dtype=np.bool_)
    np.testing.assert_array_equal(
        CythonBackend().propagate(projection, spikes),
        NumpyBackend().propagate(projection, spikes),
    )

    projection.grow_targets(3)
    assert projection._source_indptr is None
    assert projection._source_order is None
    rebuilt = projection.source_index()
    assert len(rebuilt[0]) == projection.n_pre + 1
    assert projection._compiled_csr_compatible


def test_duplicate_edges_are_canonicalized_before_source_indexing():
    projection = SparseProjection(
        3,
        2,
        np.array([0, 0, 1, 2], dtype=np.int32),
        np.array([1, 1, 0, 1], dtype=np.int32),
        np.array([0.125, 0.25, -0.5, 0.75], dtype=np.float32),
        np.array([1.0, -1.0, 1.0], dtype=np.float32),
    )
    spikes = np.array([True, True, False], dtype=np.bool_)
    expected = NumpyBackend().propagate(projection, spikes)
    actual = CythonBackend().propagate(projection, spikes)
    np.testing.assert_array_equal(actual, expected)
    assert len(projection.weights) == 3


def test_noncontiguous_spikes_fall_back_to_numpy_and_keep_shape_error():
    projection = _projection(18, 11, 0.3, seed=19)
    backing = np.zeros(36, dtype=np.bool_)
    backing[::2] = np.arange(18) % 4 == 0
    spikes = backing[::2]
    assert not spikes.flags.c_contiguous
    np.testing.assert_array_equal(
        CythonBackend().propagate(projection, spikes),
        NumpyBackend().propagate(projection, spikes),
    )

    with pytest.raises(
        ValueError,
        match="spike vector does not match projection input size",
    ):
        CythonBackend().propagate(
            projection, np.zeros(projection.n_pre - 1, dtype=np.bool_)
        )


def test_incompatible_rebound_weights_select_numpy_fallback():
    projection = _projection(18, 11, 0.3, seed=20)
    strided = np.repeat(projection.weights, 2)[::2]
    assert not strided.flags.c_contiguous
    projection.bind_weights(strided)
    assert not projection._compiled_csr_compatible
    spikes = np.arange(projection.n_pre) % 3 == 0
    np.testing.assert_array_equal(
        CythonBackend().propagate(projection, spikes),
        NumpyBackend().propagate(projection, spikes),
    )


def test_backend_selects_csr_when_activity_is_above_crossover():
    projection = _projection(100, 73, 0.12, seed=55)
    spikes = np.ones(100, dtype=np.bool_)
    backend = CythonBackend()
    calls: list[str] = []
    original_csr = backend._sparse.propagate_csr
    original_active = backend._sparse.propagate_active

    class Spy:
        def propagate_csr(self, *args):
            calls.append("csr")
            return original_csr(*args)

        def propagate_active(self, *args):
            calls.append("active")
            return original_active(*args)

    backend._sparse = Spy()
    actual = backend.propagate(projection, spikes)
    expected = NumpyBackend().propagate(projection, spikes)
    np.testing.assert_array_equal(actual, expected)
    assert calls == ["csr"]


@pytest.mark.parametrize("active_count", [30, 60])
def test_backend_selects_active_sources_through_measured_crossover(active_count):
    projection = _projection(100, 73, 0.12, seed=56)
    spikes = np.zeros(100, dtype=np.bool_)
    spikes[:active_count] = True
    backend = CythonBackend()
    calls: list[str] = []
    original_active = backend._sparse.propagate_active

    class Spy:
        def propagate_active(self, *args):
            calls.append("active")
            return original_active(*args)

    backend._sparse = Spy()
    actual = backend.propagate(projection, spikes)
    expected = NumpyBackend().propagate(projection, spikes)
    np.testing.assert_array_equal(actual, expected)
    assert calls == ["active"]

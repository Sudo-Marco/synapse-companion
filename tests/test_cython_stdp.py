from __future__ import annotations

import numpy as np
import pytest

from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.core.synapses import SparseProjection
from synapse_pet.neural_backend.cython_backend import CythonBackend
from synapse_pet.neural_backend.numpy_backend import NumpyBackend
from synapse_pet.neural_backend import create_neural_backend


pytest.importorskip(
    "synapse_pet.neural_backend._stdp",
    reason="optional Cython extension has not been built",
)


def test_factory_selects_compiled_cython_backend_when_extension_is_present():
    selection = create_neural_backend({"engine": "cython"})
    assert isinstance(selection.backend, CythonBackend)
    assert selection.active_engine == "cython"
    assert selection.fallback_reason is None


def _projection(n_pre: int, n_post: int, seed: int) -> SparseProjection:
    rng = np.random.default_rng(seed)
    post, pre = np.nonzero(rng.random((n_post, n_pre)) < 0.18)
    signs = rng.choice(np.array([-1.0, 1.0], dtype=np.float32), size=n_pre)
    weights = (rng.random(len(pre), dtype=np.float32) * signs[pre])
    return SparseProjection(
        n_pre,
        n_post,
        pre.astype(np.int32),
        post.astype(np.int32),
        weights,
        signs,
    )


@pytest.mark.parametrize("shape", [(8, 5), (64, 23), (384, 96)])
def test_cython_stdp_is_bitwise_equal_to_numpy_for_traces_and_eligibility(shape):
    n_pre, n_post = shape
    numpy_projection = _projection(n_pre, n_post, seed=n_pre + n_post)
    cython_projection = SparseProjection(
        numpy_projection.n_pre,
        numpy_projection.n_post,
        numpy_projection.pre.copy(),
        numpy_projection.post.copy(),
        numpy_projection.weights.copy(),
        numpy_projection.source_sign.copy(),
    )
    numpy_learner = RewardSTDP()
    cython_learner = RewardSTDP()
    numpy_learner.initialize(numpy_projection)
    cython_learner.initialize(cython_projection)
    numpy_backend = NumpyBackend()
    cython_backend = CythonBackend()
    rng = np.random.default_rng(0x5D7 + n_pre)

    for step in range(180):
        if step % 19 == 0:
            pre = np.zeros(n_pre, dtype=np.bool_)
            post = np.zeros(n_post, dtype=np.bool_)
        elif step % 23 == 0:
            pre = np.ones(n_pre, dtype=np.bool_)
            post = np.ones(n_post, dtype=np.bool_)
        else:
            pre = rng.random(n_pre) < 0.07
            post = rng.random(n_post) < 0.11
        dt_s = (0.001, 0.002, 0.005)[step % 3]
        numpy_backend.update_stdp(
            numpy_learner, numpy_projection, pre, post, dt_s
        )
        cython_backend.update_stdp(
            cython_learner, cython_projection, pre, post, dt_s
        )

        np.testing.assert_array_equal(cython_learner.pre_trace,
                                      numpy_learner.pre_trace)
        np.testing.assert_array_equal(cython_learner.post_trace,
                                      numpy_learner.post_trace)
        np.testing.assert_array_equal(cython_learner.eligibility,
                                      numpy_learner.eligibility)

    numpy_backend.apply_reward(numpy_learner, numpy_projection, 0.37)
    cython_backend.apply_reward(cython_learner, cython_projection, 0.37)
    np.testing.assert_array_equal(cython_projection.weights,
                                  numpy_projection.weights)


@pytest.mark.parametrize("dopamine", [-1.0, -0.37, 0.0, 0.37, 1.0])
def test_cython_reward_application_is_bitwise_equal_to_numpy(dopamine):
    numpy_projection = _projection(48, 19, seed=725)
    numpy_projection.weights[: min(4, len(numpy_projection.weights))] = np.array(
        [-1.2, -0.4, 0.4, 1.2][: min(4, len(numpy_projection.weights))],
        dtype=np.float32,
    )
    cython_projection = SparseProjection(
        numpy_projection.n_pre,
        numpy_projection.n_post,
        numpy_projection.pre.copy(),
        numpy_projection.post.copy(),
        numpy_projection.weights.copy(),
        numpy_projection.source_sign.copy(),
    )
    numpy_learner = RewardSTDP(learning_rate=0.0037)
    cython_learner = RewardSTDP(learning_rate=0.0037)
    numpy_learner.initialize(numpy_projection)
    cython_learner.initialize(cython_projection)
    rng = np.random.default_rng(412)
    numpy_learner.eligibility[:] = rng.normal(
        size=len(numpy_projection.weights)
    ).astype(np.float32)
    cython_learner.eligibility[:] = numpy_learner.eligibility
    numpy_backend = NumpyBackend()
    cython_backend = CythonBackend()

    numpy_backend.apply_reward(numpy_learner, numpy_projection, dopamine)
    cython_backend.apply_reward(cython_learner, cython_projection, dopamine)

    np.testing.assert_array_equal(cython_projection.weights,
                                  numpy_projection.weights)

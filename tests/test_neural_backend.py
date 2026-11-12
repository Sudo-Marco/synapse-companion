from __future__ import annotations

import numpy as np
import pytest

from synapse_pet.core.network import SpikingNetwork
from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.core.synapses import SparseProjection
from synapse_pet.neural_backend import NumpyBackend, create_neural_backend
from synapse_pet.neural_backend.cython_backend import CythonBackendUnavailable
from synapse_pet.runtime.config import load_config


def test_numpy_is_the_default_reference_backend_and_preserves_network_hash():
    selection = create_neural_backend({})
    assert isinstance(selection.backend, NumpyBackend)
    assert selection.active_engine == "numpy"
    assert selection.fallback_reason is None


def test_default_yaml_selects_deterministic_float32_numpy():
    settings = load_config()["neural_backend"]
    assert settings == {
        "engine": "numpy",
        "fallback": "numpy",
        "precision": "float32",
        "deterministic": True,
    }


@pytest.mark.parametrize("requested", ["cython", "auto"])
def test_unavailable_cython_extension_falls_back_to_numpy_with_reason(
    requested: str, monkeypatch: pytest.MonkeyPatch
):
    import synapse_pet.neural_backend.factory as factory

    def unavailable(*, deterministic: bool):
        raise CythonBackendUnavailable("simulated missing compiled extension")

    monkeypatch.setattr(factory, "CythonBackend", unavailable)
    selection = create_neural_backend({
        "engine": requested,
        "fallback": "numpy",
        "precision": "float32",
        "deterministic": True,
    })

    assert isinstance(selection.backend, NumpyBackend)
    assert selection.requested_engine == requested
    assert selection.active_engine == "numpy"
    assert "simulated missing" in (selection.fallback_reason or "")
    assert selection.as_dict()["deterministic"] is True


@pytest.mark.parametrize("config", [
    {"engine": "cuda"},
    {"engine": "numpy", "fallback": "auto"},
    {"engine": "numpy", "precision": "float64"},
    {"engine": "numpy", "deterministic": "false"},
])
def test_backend_factory_rejects_unsupported_configuration(config):
    with pytest.raises(ValueError):
        create_neural_backend(config)


def test_numpy_backend_step_matches_direct_reference_exactly():
    direct = SpikingNetwork(600, seed=882, noise=0.015)
    adapted = SpikingNetwork(600, seed=882, noise=0.015,
                             backend=NumpyBackend(deterministic=True))
    rng = np.random.default_rng(712)

    for _ in range(32):
        sensor_current = rng.random(direct.n_sensor, dtype=np.float32)
        expected = direct.step(sensor_current)
        actual = adapted.step(sensor_current)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(adapted.population.voltage,
                                      direct.population.voltage)
        np.testing.assert_array_equal(adapted.hidden_to_output.weights,
                                      direct.hidden_to_output.weights)


def test_numpy_backend_stdp_reward_and_action_credit_match_direct_calls():
    backend = NumpyBackend()
    first = SparseProjection(
        3, 4,
        np.array([0, 1, 2, 0, 2], dtype=np.int32),
        np.array([0, 1, 1, 2, 3], dtype=np.int32),
        np.array([0.2, 0.3, 0.4, 0.5, 0.6], dtype=np.float32),
        np.ones(3, dtype=np.float32),
    )
    second = SparseProjection(
        first.n_pre, first.n_post, first.pre.copy(), first.post.copy(),
        first.weights.copy(), first.source_sign.copy())
    routed = RewardSTDP()
    direct = RewardSTDP()
    routed.initialize(first)
    direct.initialize(second)
    pre = np.array([True, False, True])
    post = np.array([False, True, False, True])

    backend.update_stdp(routed, first, pre, post, 0.002)
    direct.mark(second, pre, post, 0.002)
    backend.apply_reward(routed, first, 0.4)
    direct.apply_reward(second, 0.4)
    activity = np.array([0.75, 0.1, 1.0], dtype=np.float32)
    selected = np.array([3, 1], dtype=np.int32)
    backend.apply_action_credit(routed, first, -0.2, selected, activity, 0.1)
    direct.apply_action_credit(second, -0.2, selected, activity, learning_rate=0.1)

    np.testing.assert_array_equal(routed.pre_trace, direct.pre_trace)
    np.testing.assert_array_equal(routed.post_trace, direct.post_trace)
    np.testing.assert_array_equal(routed.eligibility, direct.eligibility)
    np.testing.assert_array_equal(first.weights, second.weights)

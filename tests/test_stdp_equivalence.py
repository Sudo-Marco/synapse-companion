from __future__ import annotations

import numpy as np
import pytest

from synapse_pet.core.network import SpikingNetwork
from synapse_pet.core.plasticity import RewardSTDP


def _reference_mark(learner: RewardSTDP, projection, pre_spikes: np.ndarray,
                   post_spikes: np.ndarray, dt_s: float) -> None:
    """Original float32-conversion implementation kept as an exact oracle."""
    assert learner.pre_trace is not None
    assert learner.post_trace is not None
    assert learner.eligibility is not None
    decay = np.float32(np.exp(-dt_s / learner.eligibility_tau_s))
    learner.pre_trace *= decay
    learner.post_trace *= decay
    pre = pre_spikes.astype(np.float32)
    post = post_spikes.astype(np.float32)
    learner.eligibility *= decay
    learner.eligibility += (
        learner.a_plus * learner.pre_trace[projection.pre] * post[projection.post])
    learner.eligibility -= (
        learner.a_minus * learner.post_trace[projection.post] * pre[projection.pre])
    learner.pre_trace += pre
    learner.post_trace += post


@pytest.mark.parametrize("projection_name", [
    "sensor_to_hidden", "recurrent", "hidden_to_output",
])
def test_mark_matches_original_float32_equations_exactly(projection_name: str):
    network = SpikingNetwork(600, seed=92)
    projection = getattr(network, projection_name)
    learner = RewardSTDP(learning_rate=0.0005, eligibility_tau_s=3.0,
                         a_plus=0.01, a_minus=0.012)
    reference = RewardSTDP(learning_rate=learner.learning_rate,
                           eligibility_tau_s=learner.eligibility_tau_s,
                           a_plus=learner.a_plus, a_minus=learner.a_minus)
    learner.initialize(projection)
    reference.initialize(projection)

    rng = np.random.default_rng(1907)
    assert learner.pre_trace is not None
    assert learner.post_trace is not None
    assert learner.eligibility is not None
    assert reference.pre_trace is not None
    assert reference.post_trace is not None
    assert reference.eligibility is not None
    learner.pre_trace[:] = rng.random(projection.n_pre, dtype=np.float32)
    learner.post_trace[:] = rng.random(projection.n_post, dtype=np.float32)
    learner.eligibility[:] = rng.uniform(
        -0.5, 0.5, len(projection.weights)).astype(np.float32)
    reference.pre_trace[:] = learner.pre_trace
    reference.post_trace[:] = learner.post_trace
    reference.eligibility[:] = learner.eligibility

    for tick in range(40):
        if tick == 0:
            pre_spikes = np.zeros(projection.n_pre, dtype=np.bool_)
            post_spikes = np.zeros(projection.n_post, dtype=np.bool_)
        elif tick == 1:
            pre_spikes = np.ones(projection.n_pre, dtype=np.bool_)
            post_spikes = np.ones(projection.n_post, dtype=np.bool_)
        else:
            pre_spikes = rng.random(projection.n_pre) < 0.04
            post_spikes = rng.random(projection.n_post) < 0.03

        dt_s = 0.002 if tick % 3 else 0.005
        _reference_mark(reference, projection, pre_spikes, post_spikes, dt_s)
        learner.mark(projection, pre_spikes, post_spikes, dt_s)

        np.testing.assert_array_equal(learner.pre_trace, reference.pre_trace)
        np.testing.assert_array_equal(learner.post_trace, reference.post_trace)
        np.testing.assert_array_equal(learner.eligibility, reference.eligibility)

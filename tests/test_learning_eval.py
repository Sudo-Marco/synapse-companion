from __future__ import annotations

import numpy as np

from synapse_pet.core.encoding import PopulationEncoder
from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.core.synapses import SparseProjection
from synapse_pet.mind.action_selection import ActionCandidate, ActionSelector
from synapse_pet.sim.learning_eval import softmax_probabilities


def test_softmax_is_stable_and_sums_to_one():
    probabilities = softmax_probabilities({"a": 1000.0, "b": 999.0, "c": 998.0})

    assert all(np.isfinite(value) for value in probabilities.values())
    assert np.isclose(sum(probabilities.values()), 1.0)
    assert probabilities["a"] > probabilities["b"] > probabilities["c"]


def test_action_credit_updates_only_the_selected_output_and_active_inputs():
    projection = SparseProjection(
        2, 3,
        np.array([0, 0, 1], dtype=np.int32),
        np.array([0, 1, 1], dtype=np.int32),
        np.array([0.2, 0.3, 0.4], dtype=np.float32),
        np.ones(2, dtype=np.float32),
    )
    learner = RewardSTDP()
    learner.initialize(projection)
    before = projection.weights.copy()

    learner.apply_action_credit(
        projection, dopamine=1.0,
        post_indices=np.array([1], dtype=np.int32),
        pre_activity=np.array([1.0, 0.0], dtype=np.float32),
        learning_rate=0.1,
    )

    assert projection.weights[1] > before[1]
    np.testing.assert_array_equal(projection.weights[[0, 2]], before[[0, 2]])


def test_categorical_encoder_uses_two_hash_features_for_small_groups():
    encoder = PopulationEncoder({"window_category": 24}, seed=3)
    codes = []
    for category in ("X", "Y", "Z"):
        rates = encoder.rates({"window_category": category})
        codes.append(frozenset(np.flatnonzero(rates > encoder.min_rate_hz)))

    assert all(len(code) == 2 for code in codes)
    assert len(set(codes)) == 3


def test_rate_decoder_uses_spike_counts_across_the_tick():
    from synapse_pet.core.decoding import RateDecoder

    decoder = RateDecoder({"tool:a": np.array([0, 1], dtype=np.int32)}, tau_s=0.1)
    rates = decoder.update(np.array([2.0, 0.0], dtype=np.float32), dt_s=0.1)

    assert rates["tool:a"] > 0.0


def test_selector_compares_neural_hz_and_preference_on_a_shared_scale():
    selector = ActionSelector(neural_score_scale_hz=15.0)
    selector.preferences[("X", "eval_b")] = 0.5
    selected = selector.choose(
        [ActionCandidate("eval_a", 12.0, context="X"),
         ActionCandidate("eval_b", 6.0, context="X")],
        initiative=1.0,
    )

    assert selected is not None
    assert selected.name == "eval_b"

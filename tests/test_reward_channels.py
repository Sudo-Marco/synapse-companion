from __future__ import annotations

from math import ceil, log
from pathlib import Path

import numpy as np

from synapse_pet.runtime.config import load_config
from synapse_pet.runtime.engine import PetEngine


def _all_weights(engine: PetEngine) -> tuple[np.ndarray, ...]:
    return tuple(projection.weights.copy() for projection in (
        engine.network.sensor_to_hidden,
        engine.network.recurrent,
        engine.network.hidden_to_output,
    ))


def _set_eligibility(engine: PetEngine) -> None:
    for learner in engine.learners.values():
        assert learner.eligibility is not None
        learner.eligibility.fill(1.0)


def test_affection_reacts_even_after_reward_is_predicted(tmp_path):
    engine = PetEngine(seed=5, data_dir=tmp_path)
    engine.neuromodulators.expected_reward["affection:manual:carinho"] = 1.0
    engine.emotions.happiness = 0.5
    _set_eligibility(engine)
    weights_before = _all_weights(engine)

    rpe = engine.reward("manual", 1.0, "carinho", source="affection")
    engine.tick({}, duration_ms=250.0, active=False)

    assert rpe == 0.0
    assert engine.affect_impulse > 0.4
    assert engine.emotions.happiness > 0.5
    for before, after in zip(weights_before, _all_weights(engine)):
        np.testing.assert_array_equal(before, after)


def test_repeated_affection_keeps_affect_but_learning_rpe_decays(tmp_path):
    engine = PetEngine(seed=6, data_dir=tmp_path)
    _set_eligibility(engine)
    reward_values = []
    weights_by_click = []
    config = load_config()
    prediction_rate = float(config["learning"]["prediction_rate"])
    deadband = float(config["learning"]["rpe_deadband"])
    event_limit = ceil(log(deadband) / log(1.0 - prediction_rate)) + 2

    for _ in range(event_limit):
        reward_values.append(engine.reward("manual", 1.0, "carinho",
                                           source="affection"))
        engine.tick({}, duration_ms=250.0, active=False, contacted=True)
        weights_by_click.append(_all_weights(engine))

    assert reward_values[0] > 0.9
    assert reward_values[-1] == 0.0
    assert 0.0 < engine.affect_impulse < 0.2
    assert engine.emotions.happiness > 0.8
    first_zero = next(index for index, value in enumerate(reward_values)
                      if value == 0.0)
    for later in range(first_zero + 1, len(weights_by_click)):
        for before, after in zip(weights_by_click[first_zero], weights_by_click[later]):
            np.testing.assert_array_equal(before, after)


def test_unexpected_reward_changes_weights(tmp_path):
    engine = PetEngine(seed=7, data_dir=tmp_path)
    _set_eligibility(engine)
    engine._last_hidden_activity.fill(1.0)
    before = _all_weights(engine)

    rpe = engine.reward("editor", 1.0, "pausa", source="feedback_positive")

    assert rpe > 0.9
    assert any(np.any(old != new) for old, new in zip(before, _all_weights(engine)))


def test_zero_baseline_rpe_does_not_change_weights(tmp_path):
    engine = PetEngine(seed=8, data_dir=tmp_path)
    _set_eligibility(engine)
    before = _all_weights(engine)

    rpe = engine.reward("quiet", 0.0, source="feedback_positive")

    assert rpe == 0.0
    for old, new in zip(before, _all_weights(engine)):
        np.testing.assert_array_equal(old, new)


def test_negative_feedback_has_negative_rpe_and_affect(tmp_path):
    engine = PetEngine(seed=10, data_dir=tmp_path)
    _set_eligibility(engine)

    rpe = engine.reward("editor", -1.0, source="feedback_negative")

    assert rpe < 0.0
    assert engine.affect_impulse < 0.0


def test_reward_sources_are_configured_as_two_channels():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs" / "default.yaml")
    sources = config["reward_channels"]
    assert set(sources) == {
        "affection", "feedback_positive", "feedback_negative",
        "proposal_accepted", "proposal_rejected", "tool_success",
        "tool_failure", "curiosity",
    }
    for channel in sources.values():
        assert set(channel) == {"affect_impulse", "learning_reward"}
        assert np.isfinite(channel["affect_impulse"])
        assert np.isfinite(channel["learning_reward"])


def test_encoder_size_scales_with_network_sensor_population(tmp_path):
    engine = PetEngine(seed=9, neurons=1000, data_dir=tmp_path)
    assert engine.encoder.size == engine.network.n_sensor
    engine.tick({"input_rate": 0.5, "window_category": "editor"},
                duration_ms=50.0, active=True)


def test_affection_submission_queues_separate_affect_source(tmp_path):
    engine = PetEngine(seed=11, data_dir=tmp_path)
    engine.submit_affection()

    assert engine.events.get_nowait() == {
        "_reward_source": "affection", "_contacted": True,
    }

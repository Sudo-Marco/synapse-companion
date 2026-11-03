from __future__ import annotations

import numpy as np

from synapse_pet.runtime.engine import PetEngine
from synapse_pet.ui.interaction import AffectionDragTracker


def test_sixty_seconds_of_hover_only_changes_gaze_curiosity(tmp_path):
    engine = PetEngine(seed=101, data_dir=tmp_path)
    start_mood = engine.neuromodulators.mood
    start_happiness = engine.emotions.happiness

    def forbidden_reward(*_args, **_kwargs):
        raise AssertionError("mouse novelty must never call reward()")

    engine.reward = forbidden_reward
    for tick in range(240):
        engine.process_curiosity_observation(
            "mouse", "near_moving", now=tick * 0.25)
        engine.tick({}, duration_ms=250.0, active=False)

    assert abs(engine.neuromodulators.mood - start_mood) <= 0.05
    assert abs(engine.emotions.happiness - start_happiness) <= 0.05
    assert engine.learning_rpe == 0.0
    assert engine.neuromodulators.dopamine == 0.0
    assert engine.affect_impulse == 0.0
    assert engine.curiosity_impulse <= 0.05


def test_deliberate_affection_still_raises_mood(tmp_path):
    engine = PetEngine(seed=102, data_dir=tmp_path)
    mood_before = engine.neuromodulators.mood
    engine.reward("manual", 1.0, "carinho", source="affection")
    engine.tick({}, duration_ms=50.0, active=True, contacted=True)
    assert engine.neuromodulators.mood > mood_before
    assert engine.emotions.happiness > 0.5
    assert engine.affect_impulse > 0.0


def test_repeated_mouse_novelty_habituates_and_recovers_slowly(tmp_path):
    engine = PetEngine(seed=103, data_dir=tmp_path)
    first = engine.process_curiosity_observation("mouse", "near_moving", now=0.0)
    second = engine.process_curiosity_observation("mouse", "near_moving", now=0.5)
    recovered = engine.process_curiosity_observation(
        "mouse", "near_moving", now=180.5)

    assert first > second > 0.0
    assert recovered > second
    assert engine.learning_rpe == 0.0
    assert engine.affect_impulse == 0.0


def test_mouse_novelty_rate_cap_is_per_source_per_minute(tmp_path):
    engine = PetEngine(seed=104, data_dir=tmp_path)
    granted = sum(engine.process_curiosity_observation(
        "mouse", "far_moving", now=1.0) for _ in range(30))
    cap = engine.curiosity_config["per_minute_cap"]["mouse"]
    assert granted <= cap + 1e-9
    assert engine.affect_impulse == 0.0
    assert engine.neuromodulators.dopamine == 0.0


def test_reset_affect_keeps_learned_weights(tmp_path):
    engine = PetEngine(seed=105, data_dir=tmp_path)
    engine.network.recurrent.weights[0] = np.float32(0.4242)
    before = tuple(projection.weights.copy() for projection in (
        engine.network.sensor_to_hidden, engine.network.recurrent,
        engine.network.hidden_to_output))
    engine.affect_impulse = 0.7
    engine.curiosity_impulse = 0.04
    engine.neuromodulators.mood = 0.9
    engine.emotions.happiness = 0.9
    engine.emotions.affection = 0.8

    engine.reset_affect_to_neutral(save=True)

    after = tuple(projection.weights for projection in (
        engine.network.sensor_to_hidden, engine.network.recurrent,
        engine.network.hidden_to_output))
    for old, new in zip(before, after):
        np.testing.assert_array_equal(old, new)
    assert engine.neuromodulators.mood == 0.5
    assert engine.neuromodulators.dopamine == 0.0
    assert engine.affect_impulse == 0.0
    assert engine.curiosity_impulse == 0.0
    assert engine.emotions.happiness == 0.5
    assert engine.emotions.affection == 0.3
    restored, _ = engine.store.load()
    assert np.array_equal(restored.recurrent.weights, before[1])


def test_nondeliberate_mood_budget_caps_rise_per_minute(tmp_path):
    engine = PetEngine(seed=106, data_dir=tmp_path)
    before = engine.neuromodulators.mood
    engine._last_rpe_is_deliberate = False

    for _ in range(240):
        engine.neuromodulators.dopamine = 1.0
        engine.tick({}, duration_ms=250.0, active=False)

    cap = engine.affect_config["non_deliberate_mood_per_minute"]
    assert 0.0 <= engine.neuromodulators.mood - before <= cap + 1e-6


def test_positive_mood_impulse_soft_caps_near_one():
    from synapse_pet.core.neuromodulators import Neuromodulators

    ordinary = Neuromodulators(mood=0.5)
    near_ceiling = Neuromodulators(mood=0.9)
    ordinary_gain = ordinary.add_mood_impulse(0.12)
    capped_gain = near_ceiling.add_mood_impulse(0.12)
    assert np.isclose(ordinary_gain, 0.06)
    assert np.isclose(capped_gain, 0.012)
    assert capped_gain < ordinary_gain


def test_affection_drag_requires_motion_and_minimum_hold():
    tracker = AffectionDragTracker(minimum_seconds=1.0)
    tracker.move(60, 50, 100, 100, True, now=2.0)
    tracker.press(50, 50, 100, 100, True, now=10.0)
    assert not tracker.move(57, 50, 100, 100, True, now=10.5)
    assert not tracker.release(now=10.9)

    tracker.press(50, 50, 100, 100, True, now=20.0)
    assert not tracker.move(58, 50, 100, 100, True, now=20.4)
    assert tracker.release(now=21.1)

    tracker.press(50, 50, 100, 100, True, now=30.0)
    assert not tracker.release(now=32.0)

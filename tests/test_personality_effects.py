from synapse_pet.mind.action_selection import ActionCandidate
from synapse_pet.runtime.engine import PetEngine


def test_personality_traits_change_bounded_decision_parameters(tmp_path):
    engine = PetEngine(seed=23, data_dir=tmp_path)
    try:
        engine.personality.initiative = 1.0
        engine.personality.caution = 0.0
        engine.personality.reward_sensitivity = 0.0
        engine._apply_personality_effects()
        low_threshold = engine.selector.initiative_threshold
        low_feedback = engine.selector.feedback_rate

        engine.personality.initiative = 0.0
        engine.personality.caution = 1.0
        engine.personality.reward_sensitivity = 1.0
        engine._apply_personality_effects()
        high_threshold = engine.selector.initiative_threshold
        high_feedback = engine.selector.feedback_rate

        assert low_threshold < 0.5 < high_threshold
        assert 0.0 <= low_threshold <= 1.0
        assert 0.0 <= high_threshold <= 1.0
        assert high_feedback > low_feedback
        # The mapped initiative threshold gates the same candidate differently.
        candidates = [ActionCandidate("abrir_url", 1.0)]
        assert engine.selector.choose(candidates, initiative=0.5) is None
        engine.personality.initiative = 1.0
        engine.personality.caution = 0.0
        engine._apply_personality_effects()
        assert engine.selector.choose(candidates, initiative=0.5) is not None
    finally:
        engine.stop()


def test_personality_effects_can_be_disabled(tmp_path):
    engine = PetEngine(seed=24, data_dir=tmp_path)
    try:
        engine.personality_config = {"enabled": False,
                                     "initiative_threshold_base": 0.5}
        engine.personality.initiative = 1.0
        engine.personality.reward_sensitivity = 1.0
        engine._apply_personality_effects()

        assert engine.selector.initiative_threshold == 0.5
        assert engine.selector.feedback_rate == engine.learning_config[
            "action_preference_rate"]
    finally:
        engine.stop()

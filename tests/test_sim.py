from synapse_pet.sim.sim_user import SimUser

def test_contextual_preference_learns_and_adapts_after_reversal():
    _, history = SimUser().run(episodes=500, reverse_at=250)
    assert sum(history[200:250]) / 50 > .85
    assert sum(history[-50:]) / 50 > .85

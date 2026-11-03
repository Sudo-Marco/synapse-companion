from synapse_pet.runtime.engine import PetEngine


def test_reinforced_aggregate_pattern_emits_habit_learned_once(tmp_path):
    engine = PetEngine(seed=44, data_dir=tmp_path)
    for _ in range(5):
        engine.reward("manual", 1.0, "carinho", source="affection")

    events = []
    while not engine.action_results.empty():
        events.append(engine.action_results.get_nowait())
    learned = [event for event in events if event.get("operation") == "habit_learned"]
    assert len(learned) == 1
    assert learned[0]["context"] == "manual"
    assert learned[0]["action"] == "carinho"
    assert engine.memory.habits(10)[0][:3] == ("manual", "carinho", 5)


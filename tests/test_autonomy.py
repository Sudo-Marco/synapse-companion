import sqlite3

from synapse_pet.runtime.autonomy import AutonomyController, PostItStore
from synapse_pet.runtime.engine import PetEngine
from synapse_pet.runtime.visual_state import VisualState


def test_postit_autonomy_uses_state_map_cooldown_and_hour_budget():
    controller = AutonomyController({
        "enabled": True,
        "max_actions_per_hour": 1,
        "cooldowns_s": {"alerta": 300},
        "state_behaviors": {"estressado": "alerta"},
        "behaviors": {"postits": True},
        "postits": {"enabled": True, "stress_threshold": 0.7},
    })
    state = VisualState(stress=0.8)

    assert controller.choose_postit(
        state, {}, 10.0, enabled=True, quiet=False,
        proposal_pending=False) == "alerta"
    assert controller.choose_postit(
        state, {}, 11.0, enabled=True, quiet=False,
        proposal_pending=False) is None
    assert controller.choose_postit(
        state, {}, 4000.0, enabled=False, quiet=False,
        proposal_pending=False) is None


def test_postit_store_persists_only_template_metadata_and_expires(tmp_path):
    path = tmp_path / "postits.sqlite3"
    store = PostItStore(path)
    note = store.add("alerta", "estressado", 12, 34, 60, now=100.0)
    store.move(note.note_id, 56, 78)

    active = store.active(now=120.0)
    assert len(active) == 1
    assert (active[0].x, active[0].y) == (56, 78)
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(postits)")}
    assert "text" not in columns and "message" not in columns

    assert store.active(now=161.0) == []


def test_postit_feedback_uses_learning_rpe_and_aggregates_habit(tmp_path):
    engine = PetEngine(seed=17, data_dir=tmp_path)

    rpes = [engine.reward("postit_interaction", 0.15,
                          source="feedback_positive") for _ in range(4)]

    assert all(rpe > 0.0 for rpe in rpes)
    habit = next(row for row in engine.memory.habits()
                 if row[0] == "postit" and row[1] == "feedback_positive")
    assert habit[2] == 4
    assert habit[3] > 0.015
    assert engine.memory.top_rpe(1)[0][0] == "postit_interaction"


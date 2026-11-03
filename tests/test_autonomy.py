import sqlite3

from synapse_pet.runtime.autonomy import AutonomyController, PostItStore
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


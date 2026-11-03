import sqlite3

from synapse_pet.core.network import SpikingNetwork
from synapse_pet.core.neuromodulators import Neuromodulators
from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.mind.episodic_memory import EpisodicMemory
from synapse_pet.mind.sleep import SleepConsolidator

def test_sleep_replay_is_bounded_and_recovers_state(tmp_path):
    network = SpikingNetwork(600, seed=5)
    memory = EpisodicMemory(tmp_path / "episodes.sqlite3")
    memory.add("codigo", "pausa", .5)
    learners = {"sensor_hidden": RewardSTDP(), "recurrent": RewardSTDP(),
                "hidden_output": RewardSTDP()}
    learners["sensor_hidden"].initialize(network.sensor_to_hidden)
    learners["recurrent"].initialize(network.recurrent)
    learners["hidden_output"].initialize(network.hidden_to_output)
    modulators = Neuromodulators(stress=.8, energy=.5)
    sleep = SleepConsolidator(max_replay_episodes=2, replay_enabled=True)
    old_edges = len(network.recurrent.weights)
    assert sleep.consolidate(network, memory, learners, modulators) == 1
    assert len(network.recurrent.weights) >= old_edges
    assert modulators.stress == .4
    assert modulators.energy == .65
    assert network.dale_is_respected()


def test_sleep_replay_is_disabled_by_default(tmp_path):
    memory = EpisodicMemory(tmp_path / "episodes.sqlite3")
    memory.add("codigo", "pausa", .8, rpe=.05)
    sleep = SleepConsolidator()
    assert sleep.replay_enabled is False
    assert memory.top_rpe(1)[0][2] == .05


def test_sleep_uses_highest_absolute_rpe_first(tmp_path):
    memory = EpisodicMemory(tmp_path / "episodes.sqlite3")
    memory.add("codigo", "acao_a", .9, rpe=.1)
    memory.add("navegador", "acao_b", .1, rpe=-.9)
    assert memory.top_rpe(1)[0][1:3] == ("acao_b", -.9)


def test_episode_database_migrates_to_rpe_column(tmp_path):
    path = tmp_path / "episodes.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE episodes(id INTEGER PRIMARY KEY, context TEXT NOT NULL, "
                   "action TEXT, reward REAL NOT NULL, timestamp TEXT, emotion TEXT)")
        db.execute("INSERT INTO episodes(context,action,reward) VALUES('codigo','a',.5)")
    memory = EpisodicMemory(path)
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(episodes)")}
        rpe = db.execute("SELECT rpe FROM episodes").fetchone()[0]
    assert "rpe" in columns and rpe == 0.0
    assert memory.top_rpe() == []

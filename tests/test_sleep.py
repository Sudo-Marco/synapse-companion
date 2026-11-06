import sqlite3
import hashlib

import numpy as np

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


def test_replay_candidates_mix_high_and_recent_reward_events(tmp_path):
    memory = EpisodicMemory(tmp_path / "episodes.sqlite3")
    memory.add("old", "good_old", .8, rpe=.9)
    memory.add("old", "bad", .1, rpe=-1.0)
    memory.add("recent_a", "good_a", .8, rpe=.2)
    memory.add("recent_b", "good_b", .8, rpe=.3)
    memory.add("recent_c", "good_c", .8, rpe=.4)

    candidates = memory.replay_candidates(4)

    assert len(candidates) == 4
    assert all(row[2] != 0 for row in candidates)
    assert len({(row[0], row[1]) for row in candidates}) == 4
    assert ("old", "good_old") in {(row[0], row[1]) for row in candidates}
    assert ("recent_c", "good_c") in {(row[0], row[1]) for row in candidates}


def test_sleep_replay_uses_the_episode_context_projection_and_restores_active(
        tmp_path, monkeypatch):
    network = SpikingNetwork(600, seed=16)
    network.add_tool_group("alpha")
    network.configure_context_output_projections(max_contexts=4)
    def context_id(context):
        return hashlib.blake2b(context.encode("utf-8"), digest_size=16).hexdigest()
    network.activate_output_context(context_id("X"), np.array([1.0, 0.0], np.float32))
    before_x = network.context_output_weights[context_id("X")].weights.copy()
    network.activate_output_context(context_id("Y"), np.array([0.0, 1.0], np.float32))
    before_y = network.context_output_weights[context_id("Y")].weights.copy()
    memory = EpisodicMemory(tmp_path / "episodes.sqlite3")
    memory.add("X", "alpha", .5, rpe=.8)
    learners = {"sensor_hidden": RewardSTDP(), "recurrent": RewardSTDP(),
                "hidden_output": RewardSTDP()}
    learners["sensor_hidden"].initialize(network.sensor_to_hidden)
    learners["recurrent"].initialize(network.recurrent)
    learners["hidden_output"].initialize(network.hidden_to_output)

    def active_step(_current=None):
        spikes = np.zeros(network.population.size, dtype=np.bool_)
        spikes[network.hidden_start:network.output_start] = True
        spikes[network.output_groups["tool:alpha"]] = True
        network.population.spikes[:] = spikes
        return spikes
    monkeypatch.setattr(network, "step", active_step)
    sleep = SleepConsolidator(max_replay_episodes=1, replay_enabled=True,
                              replay_noise=0.0, replay_steps=1)
    assert sleep.consolidate(network, memory, learners, Neuromodulators()) == 1

    assert not np.array_equal(network.context_output_weights[context_id("X")].weights,
                              before_x)
    assert np.array_equal(network.context_output_weights[context_id("Y")].weights,
                          before_y)
    assert network._active_output_context == context_id("Y")
    topology_size = len(network.hidden_to_output.pre)
    assert len(network._base_hidden_output_weights) == topology_size
    assert len(network.hidden_to_output.weights) == topology_size
    assert all(len(state.weights) == topology_size
               for state in network.context_output_weights.values())


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

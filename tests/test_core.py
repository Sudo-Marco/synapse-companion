import numpy as np
from synapse_pet.core.neurons import LIFPopulation
from synapse_pet.core.network import SpikingNetwork
from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.core.synapses import SparseProjection

def test_lif_is_deterministic_for_fixed_seed():
    def run():
        p = LIFPopulation(8); rng = np.random.default_rng(12); trace = []
        for _ in range(100):
            trace.append(p.step(np.full(8, .12, np.float32), 2.0, rng, 0.0))
        return np.stack(trace)
    assert np.array_equal(run(), run())

def test_dale_law_and_weight_bounds():
    net = SpikingNetwork(600, seed=7)
    assert net.dale_is_respected()
    net.recurrent.weights[:] = np.clip(np.linspace(-5, 5, len(net.recurrent.weights)), -1, 1)
    net.recurrent.enforce_dale()
    assert net.dale_is_respected()
    assert np.max(np.abs(net.recurrent.weights)) <= 1

def test_zero_dopamine_keeps_weights_and_reward_changes_them():
    proj = SparseProjection(2, 1, np.array([0], np.int32), np.array([0], np.int32),
                            np.array([.2], np.float32), np.ones(2, np.float32))
    learner = RewardSTDP(); learner.initialize(proj); learner.eligibility[:] = 1
    before = proj.weights.copy()
    learner.apply_reward(proj, 0.0)
    assert np.array_equal(before, proj.weights)
    learner.apply_reward(proj, 1.0)
    assert proj.weights[0] > before[0]

def test_neurogenesis_keeps_old_group_and_weights():
    net = SpikingNetwork(600, seed=3)
    old = net.add_tool_group("notes").copy()
    weights = net.hidden_to_output.weights.copy()
    new = net.add_tool_group("pomodoro")
    assert np.array_equal(old, net.output_groups["tool:notes"])
    assert np.array_equal(weights, net.hidden_to_output.weights[:len(weights)])
    assert len(new) == net.tool_group_size

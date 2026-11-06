import hashlib
import json

import numpy as np

from synapse_pet.core.network import SpikingNetwork
from synapse_pet.runtime.persistence import SnapshotStore


def test_similar_context_reuses_projection_as_independent_copy():
    network = SpikingNetwork(600, seed=10)
    network.configure_context_output_projections(max_contexts=4, similarity_threshold=0.9)
    source = network.activate_output_context("alpha", np.array([1.0, 0.0], dtype=np.float32))
    assert source == "base"
    alpha = network.context_output_weights["alpha"].weights.copy()

    source = network.activate_output_context("beta", np.array([0.99, 0.01], dtype=np.float32))
    assert source == "alpha"
    assert np.array_equal(network.context_output_weights["beta"].weights, alpha)
    network.hidden_to_output.weights[0] += np.float32(0.01)
    assert not np.array_equal(network.context_output_weights["beta"].weights,
                              network.context_output_weights["alpha"].weights)


def test_context_projection_lru_eviction_respects_limit():
    network = SpikingNetwork(600, seed=11)
    network.configure_context_output_projections(max_contexts=2, similarity_threshold=0.99)
    network.activate_output_context("a", np.array([1.0, 0.0], dtype=np.float32))
    network.activate_output_context("b", np.array([0.0, 1.0], dtype=np.float32))
    network.activate_existing_output_context("a")
    network.activate_output_context("c", np.array([-1.0, 0.0], dtype=np.float32))
    assert set(network.context_output_weights) == {"a", "c"}
    assert len(network.context_output_weights) == 2


def test_dynamic_tool_group_extends_base_and_context_weights():
    network = SpikingNetwork(600, seed=12)
    network.configure_context_output_projections(max_contexts=3)
    network.activate_output_context("ctx", np.array([1.0, 0.0], dtype=np.float32))
    network.add_tool_group("late_plugin")
    assert network.hidden_to_output.weights is network.context_output_weights["ctx"].weights
    assert len(network._base_hidden_output_weights) == len(network.hidden_to_output.weights)
    assert len(network.context_output_weights["ctx"].weights) == len(network.hidden_to_output.weights)
    assert network.hidden_to_output.n_post == len(network.population.voltage) - network.output_start


def test_tool_output_inhibition_is_opt_in_and_suppresses_only_losing_groups():
    network = SpikingNetwork(600, seed=15)
    alpha = network.add_tool_group("alpha") - network.output_start
    beta = network.add_tool_group("beta") - network.output_start
    gamma = network.add_tool_group("gamma") - network.output_start
    assert network.tool_output_inhibition_enabled is False

    currents = np.zeros(network.hidden_to_output.n_post, dtype=np.float32)
    currents[alpha] = 1.0
    currents[beta] = 0.8
    currents[gamma] = 0.6
    network.tool_output_inhibition_strength = 0.5
    network._apply_tool_output_inhibition(currents)

    assert np.all(currents[alpha] == 1.0)
    assert np.all(currents[beta] < 0.8)
    assert np.all(currents[gamma] < currents[beta])
    assert network.tool_output_inhibition_enabled is False


def test_context_projections_round_trip_with_shared_topology(tmp_path):
    network = SpikingNetwork(600, seed=13)
    network.add_tool_group("notes")
    network.configure_context_output_projections(max_contexts=4)
    network.activate_output_context("ctx-a", np.array([1.0, 0.0], dtype=np.float32))
    network.hidden_to_output.weights[0] += np.float32(0.02)
    network.activate_output_context("ctx-b", np.array([0.0, 1.0], dtype=np.float32))
    network.hidden_to_output.weights[-1] -= np.float32(0.02)

    store = SnapshotStore(tmp_path / "creature")
    store.save(network)
    restored, _ = store.load()

    assert np.array_equal(restored.hidden_to_output.pre, network.hidden_to_output.pre)
    assert np.array_equal(restored.hidden_to_output.post, network.hidden_to_output.post)
    assert np.array_equal(restored._base_hidden_output_weights,
                          network._base_hidden_output_weights)
    assert set(restored.context_output_weights) == {"ctx-a", "ctx-b"}
    for context_id in restored.context_output_weights:
        assert np.array_equal(restored.context_output_weights[context_id].weights,
                              network.context_output_weights[context_id].weights)
        assert np.array_equal(restored.context_output_weights[context_id].signature,
                              network.context_output_weights[context_id].signature)
    assert restored.hidden_to_output.weights is restored._base_hidden_output_weights


def test_v1_snapshot_migrates_legacy_output_weights_to_base(tmp_path):
    network = SpikingNetwork(600, seed=14)
    network.configure_context_output_projections(max_contexts=4)
    network.activate_output_context("legacy-active", np.array([1.0, 0.0], dtype=np.float32))
    legacy_weights = network.hidden_to_output.weights.copy()

    store = SnapshotStore(tmp_path / "creature")
    store.save(network)
    manifest = store.path.with_suffix(".json")
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    npz_path = store.path.parent / metadata["npz_file"]
    with np.load(npz_path, allow_pickle=False) as source:
        arrays = {key: source[key].copy() for key in source.files}
    arrays["hidden_output_weights"] = legacy_weights
    np.savez_compressed(npz_path, **arrays)
    metadata["version"] = 1
    metadata.pop("context_output_projections", None)
    metadata["digest"] = hashlib.sha256(npz_path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(metadata), encoding="utf-8")

    restored, _ = store.load()
    assert not restored.context_output_weights
    assert np.array_equal(restored._base_hidden_output_weights, legacy_weights)

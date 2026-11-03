import numpy as np
from synapse_pet.core.network import SpikingNetwork
from synapse_pet.runtime.persistence import SnapshotStore

def test_save_reload_continuation_is_identical(tmp_path):
    original = SpikingNetwork(600, seed=123)
    for _ in range(5): original.step()
    path = tmp_path / "creature"
    SnapshotStore(path).save(original)
    restored, _ = SnapshotStore(path).load()
    for _ in range(10):
        assert np.array_equal(original.step(), restored.step())
    assert np.array_equal(original.population.voltage, restored.population.voltage)

def test_dynamic_tool_group_survives_snapshot(tmp_path):
    original = SpikingNetwork(600, seed=321)
    original.add_tool_group("notes")
    path = tmp_path / "creature"
    SnapshotStore(path).save(original)
    restored, _ = SnapshotStore(path).load()
    assert np.array_equal(original.output_groups["tool:notes"], restored.output_groups["tool:notes"])
    assert np.array_equal(original.hidden_to_output.pre, restored.hidden_to_output.pre)
    assert np.array_equal(original.hidden_to_output.post, restored.hidden_to_output.post)
    assert np.array_equal(original.hidden_to_output.weights, restored.hidden_to_output.weights)

def test_export_import_zip_round_trip(tmp_path):
    network = SpikingNetwork(600, seed=999)
    network.configure_context_output_projections(max_contexts=4)
    network.activate_output_context("editor", np.array([1.0, 0.0], dtype=np.float32))
    network.hidden_to_output.weights[0] += np.float32(0.01)
    source = SnapshotStore(tmp_path / "source" / "creature")
    source.save(network, {"marker": "local"})
    archive = tmp_path / "creature.zip"
    source.export_zip(archive)
    target = SnapshotStore(tmp_path / "target" / "creature")
    state = target.import_zip(archive)
    restored, _ = target.load()
    assert state == {"marker": "local"}
    assert np.array_equal(network.recurrent.weights, restored.recurrent.weights)
    assert np.array_equal(network.context_output_weights["editor"].weights,
                          restored.context_output_weights["editor"].weights)

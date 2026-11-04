import copy
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse import csr_matrix

from synapse_pet.core.network import SpikingNetwork, grow_population, _merge_projection
from synapse_pet.runtime.persistence import SnapshotStore, _migration_blockers
from synapse_pet.runtime.engine import PetEngine


def test_migration_600_to_800_expands_populations(tmp_path):
    orig = SpikingNetwork(600, seed=42)
    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    migrated, _ = store.migrate(800, allow_growth=True, seed=42)
    assert migrated.population.size == 800
    assert migrated.n_sensor == 128
    assert migrated.n_hidden == 512
    assert migrated.n_output == 160
    assert migrated.hidden_start == 128
    assert migrated.output_start == 640
    assert migrated.dale_is_respected()


def test_migration_preserves_weights_semantically(tmp_path):
    orig = SpikingNetwork(600, seed=101)
    for _ in range(3):
        orig.step()

    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    old_s2h = csr_matrix((orig.sensor_to_hidden.weights,
                          (orig.sensor_to_hidden.post, orig.sensor_to_hidden.pre)),
                         shape=(orig.n_hidden, orig.n_sensor))
    old_rec = csr_matrix((orig.recurrent.weights,
                          (orig.recurrent.post, orig.recurrent.pre)),
                         shape=(orig.n_hidden, orig.n_hidden))
    old_h2o = csr_matrix((orig._base_hidden_output_weights,
                          (orig.hidden_to_output.post, orig.hidden_to_output.pre)),
                         shape=(orig.n_output, orig.n_hidden))

    migrated, _ = store.migrate(800, allow_growth=True, seed=202)

    new_s2h = csr_matrix((migrated.sensor_to_hidden.weights,
                          (migrated.sensor_to_hidden.post, migrated.sensor_to_hidden.pre)),
                         shape=(migrated.n_hidden, migrated.n_sensor))
    new_rec = csr_matrix((migrated.recurrent.weights,
                          (migrated.recurrent.post, migrated.recurrent.pre)),
                         shape=(migrated.n_hidden, migrated.n_hidden))
    new_h2o = csr_matrix((migrated._base_hidden_output_weights,
                          (migrated.hidden_to_output.post, migrated.hidden_to_output.pre)),
                         shape=(migrated.n_output, migrated.n_hidden))

    # All connections in old network must exist with identical weights in migrated network
    for post, pre in zip(orig.sensor_to_hidden.post, orig.sensor_to_hidden.pre):
        assert abs(new_s2h[post, pre] - old_s2h[post, pre]) < 1e-6
    for post, pre in zip(orig.recurrent.post, orig.recurrent.pre):
        assert abs(new_rec[post, pre] - old_rec[post, pre]) < 1e-6
    for post, pre in zip(orig.hidden_to_output.post, orig.hidden_to_output.pre):
        assert abs(new_h2o[post, pre] - old_h2o[post, pre]) < 1e-6


def test_migration_preserves_neuronal_states(tmp_path):
    orig = SpikingNetwork(600, seed=77)
    # Set distinctive membrane potentials and adaptation
    orig.population.voltage[10] = 0.45
    orig.population.threshold_offset[120] = 0.15
    orig.population.refractory[485] = 1.5
    orig.population.spikes[486] = True

    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    migrated, _ = store.migrate(800, allow_growth=True, seed=88)

    # Sensor neuron 10
    assert migrated.population.voltage[10] == pytest.approx(0.45)
    # Hidden neuron 120 (old hidden start was 96, relative was 24; new hidden start 128 -> 128 + 24 = 152)
    assert migrated.population.threshold_offset[128 + (120 - 96)] == pytest.approx(0.15)
    # Output neuron 485 (old output start was 480, relative was 5; new output start 640 -> 640 + 5 = 645)
    assert migrated.population.refractory[640 + (485 - 480)] == pytest.approx(1.5)
    assert migrated.population.spikes[640 + (486 - 480)] is np.True_

    # Newly added neurons should be at rest
    assert migrated.population.voltage[96] == 0.0  # new sensor
    assert migrated.population.voltage[512] == 0.0  # new hidden
    assert migrated.population.voltage[760] == 0.0  # new output


def test_migration_preserves_context_output_projections(tmp_path):
    orig = SpikingNetwork(600, seed=55)
    orig.configure_context_output_projections(max_contexts=4)
    orig.activate_output_context("ctx_alpha", np.array([1.0, 0.0], dtype=np.float32))
    orig.hidden_to_output.weights[0] += np.float32(0.04)

    orig.activate_output_context("ctx_beta", np.array([0.0, 1.0], dtype=np.float32))
    orig.hidden_to_output.weights[-1] -= np.float32(0.03)

    old_alpha_w = orig.context_output_weights["ctx_alpha"].weights.copy()
    old_beta_w = orig.context_output_weights["ctx_beta"].weights.copy()

    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    migrated, _ = store.migrate(800, allow_growth=True, seed=66)

    assert set(migrated.context_output_weights) == {"ctx_alpha", "ctx_beta"}
    assert migrated.context_output_weights["ctx_alpha"].weights.shape == migrated.hidden_to_output.weights.shape
    assert migrated.context_output_weights["ctx_beta"].weights.shape == migrated.hidden_to_output.weights.shape

    # Check semantic weight preservation for context alpha
    old_alpha_mat = csr_matrix((old_alpha_w, (orig.hidden_to_output.post, orig.hidden_to_output.pre)),
                               shape=(orig.n_output, orig.n_hidden))
    new_alpha_mat = csr_matrix((migrated.context_output_weights["ctx_alpha"].weights,
                                (migrated.hidden_to_output.post, migrated.hidden_to_output.pre)),
                               shape=(migrated.n_output, migrated.n_hidden))
    for post, pre in zip(orig.hidden_to_output.post, orig.hidden_to_output.pre):
        assert abs(new_alpha_mat[post, pre] - old_alpha_mat[post, pre]) < 1e-6

    # Test context activation on migrated network
    migrated.activate_existing_output_context("ctx_alpha")
    assert migrated._active_output_context == "ctx_alpha"
    assert np.array_equal(migrated.hidden_to_output.weights,
                          migrated.context_output_weights["ctx_alpha"].weights)

    migrated.use_base_output_context()
    assert migrated._active_output_context is None
    assert np.array_equal(migrated.hidden_to_output.weights, migrated._base_hidden_output_weights)


def test_verifiable_backup_created_before_migration(tmp_path):
    orig = SpikingNetwork(600, seed=12)
    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    manifest = path.with_suffix(".json")
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    orig_digest = meta["digest"]

    migrated, _ = store.migrate(800, allow_growth=True, seed=34)

    # Check that backup was created and is verifiable
    backup_files = list(tmp_path.glob("*backup*"))
    assert len(backup_files) >= 2

    # Standard backup pair
    bak_json = tmp_path / "creature_backup.json"
    bak_npz = tmp_path / "creature_backup.npz"
    assert bak_json.exists()
    assert bak_npz.exists()
    assert store.verify_migration_backup(bak_json, bak_npz)

    # The backup snapshot must load cleanly as the original 600 network
    bak_store = SnapshotStore(tmp_path / "creature_backup")
    bak_net, _ = bak_store.load()
    assert bak_net.population.size == 600
    assert bak_net.n_sensor == 96
    assert bak_net.n_hidden == 384


def test_backup_failure_aborts_without_corrupting_original(tmp_path, monkeypatch):
    orig = SpikingNetwork(600, seed=13)
    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    manifest = path.with_suffix(".json")
    orig_json_bytes = manifest.read_bytes()
    meta = json.loads(orig_json_bytes.decode("utf-8"))
    npz_path = tmp_path / meta["npz_file"]
    orig_npz_bytes = npz_path.read_bytes()

    def fail_backup():
        raise PermissionError("Simulated backup disk full / permission error")

    monkeypatch.setattr(store, "create_migration_backup", fail_backup)

    with pytest.raises(PermissionError):
        store.migrate(800, allow_growth=True)

    # Original files must be byte-for-byte identical
    assert manifest.read_bytes() == orig_json_bytes
    assert npz_path.read_bytes() == orig_npz_bytes

    # Original snapshot still loads cleanly
    loaded, _ = store.load()
    assert loaded.population.size == 600


def test_migration_failure_aborts_without_corrupting_original(tmp_path, monkeypatch):
    orig = SpikingNetwork(600, seed=14)
    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    manifest = path.with_suffix(".json")
    orig_json_bytes = manifest.read_bytes()
    meta = json.loads(orig_json_bytes.decode("utf-8"))
    npz_path = tmp_path / meta["npz_file"]
    orig_npz_bytes = npz_path.read_bytes()

    def fail_grow(self, target, seed=41):
        raise RuntimeError("Simulated crash during neuron growth")

    # Monkeypatch SpikingNetwork.grow_population to fail
    monkeypatch.setattr(SpikingNetwork, "grow_population", fail_grow)

    with pytest.raises(RuntimeError):
        store.migrate(800, allow_growth=True)

    # Original files must remain byte-for-byte identical
    assert manifest.read_bytes() == orig_json_bytes
    assert npz_path.read_bytes() == orig_npz_bytes

    # Still loads properly
    loaded, _ = store.load()
    assert loaded.population.size == 600


def test_migration_is_idempotent(tmp_path):
    orig = SpikingNetwork(600, seed=15)
    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    net1, _ = store.migrate(800, allow_growth=True, seed=50)
    assert net1.population.size == 800

    # Running migrate again on the 800 snapshot should be a no-op
    net2, _ = store.migrate(800, allow_growth=True, seed=50)
    assert net2.population.size == 800
    assert np.array_equal(net1.population.voltage, net2.population.voltage)
    assert np.array_equal(net1.sensor_to_hidden.weights, net2.sensor_to_hidden.weights)
    assert np.array_equal(net1.recurrent.weights, net2.recurrent.weights)
    assert np.array_equal(net1.hidden_to_output.weights, net2.hidden_to_output.weights)


def test_default_config_disallows_migration(tmp_path):
    orig = SpikingNetwork(600, seed=16)
    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    # Without allow_growth=True, loading with target_neurons=800 must keep the 600 network
    net, _ = store.load(target_neurons=800, allow_growth=False)
    assert net.population.size == 600
    assert net.n_hidden == 384


def test_reduction_attempt_keeps_larger_network(tmp_path):
    orig = SpikingNetwork(800, seed=17)
    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    # Attempting to migrate to a smaller size raises ValueError
    with pytest.raises(ValueError, match="cannot shrink"):
        store.migrate(600, allow_growth=True)

    # Attempting to load with target_neurons=600 maintains the 800 network safely
    loaded, _ = store.load(target_neurons=600, allow_growth=True)
    assert loaded.population.size == 800
    assert loaded.n_hidden == 512


def test_migration_determinism_same_seed(tmp_path):
    orig = SpikingNetwork(600, seed=18)
    for _ in range(5):
        orig.step()

    path_a = tmp_path / "a" / "creature"
    path_b = tmp_path / "b" / "creature"
    store_a = SnapshotStore(path_a)
    store_b = SnapshotStore(path_b)
    store_a.save(orig)
    store_b.save(orig)

    migrated_a, _ = store_a.migrate(800, allow_growth=True, seed=999)
    migrated_b, _ = store_b.migrate(800, allow_growth=True, seed=999)

    assert np.array_equal(migrated_a.population.voltage, migrated_b.population.voltage)
    assert np.array_equal(migrated_a.population.threshold_offset, migrated_b.population.threshold_offset)
    assert np.array_equal(migrated_a.population.refractory, migrated_b.population.refractory)
    assert np.array_equal(migrated_a.population.spikes, migrated_b.population.spikes)
    assert np.array_equal(migrated_a.hidden_sign, migrated_b.hidden_sign)
    assert np.array_equal(migrated_a.sensor_to_hidden.weights, migrated_b.sensor_to_hidden.weights)
    assert np.array_equal(migrated_a.recurrent.weights, migrated_b.recurrent.weights)
    assert np.array_equal(migrated_a.hidden_to_output.weights, migrated_b.hidden_to_output.weights)


def test_dynamic_tool_groups_and_replay_persistence(tmp_path):
    orig = SpikingNetwork(600, seed=19)
    orig.add_tool_group("notes")
    orig.configure_context_output_projections(max_contexts=3)
    orig.activate_output_context("work", np.array([1.0, 0.0], dtype=np.float32))

    # Output group before migration: 600 base + 8 tool neurons = 608 neurons total
    assert orig.population.size == 608
    assert np.array_equal(orig.output_groups["tool:notes"], np.arange(600, 608))

    path = tmp_path / "creature"
    store = SnapshotStore(path)
    store.save(orig)

    # Migrated to 800 base: should have 800 base + 8 tool neurons = 808 neurons total
    migrated, _ = store.migrate(800, allow_growth=True, seed=20)
    assert migrated.population.size == 808
    assert migrated.n_output == 168  # 160 base output + 8 tool
    assert migrated.output_start == 640
    assert np.array_equal(migrated.output_groups["tool:notes"], np.arange(800, 808))

    # Tool output neurons must be mapped to post indices [160 .. 167]
    tool_posts = migrated.hidden_to_output.post[migrated.hidden_to_output.post >= 160]
    assert len(tool_posts) > 0
    assert np.all(tool_posts >= 160) and np.all(tool_posts < 168)

    # Step the migrated network
    migrated.step()

    # Save and reload round trip
    store.save(migrated)
    reloaded, _ = store.load()
    assert reloaded.population.size == 808
    assert np.array_equal(reloaded.output_groups["tool:notes"], np.arange(800, 808))
    assert "work" in reloaded.context_output_weights

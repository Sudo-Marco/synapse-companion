from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid
import zipfile
from copy import deepcopy
from dataclasses import dataclass
import numpy as np
from ..core.network import SpikingNetwork


@dataclass(slots=True)
class SnapshotPayload:
    """Detached copies of runtime arrays and metadata ready for disk I/O."""

    arrays: dict[str, np.ndarray]
    metadata: dict[str, object]


class SnapshotStore:
    """Versioned NPZ+JSON snapshots with checksum and atomic manifest replace."""
    VERSION = 2

    def __init__(self, path: Path, backups: int = 5) -> None:
        self.path = path
        self.backups = backups

    def capture(self, network: SpikingNetwork,
                state: dict[str, object] | None = None) -> SnapshotPayload:
        """Copy a consistent runtime snapshot; callers should use the engine thread."""
        projections = {
            "sensor_hidden": network.sensor_to_hidden,
            "recurrent": network.recurrent,
            "hidden_output": network.hidden_to_output,
        }
        arrays = {name: getattr(network.population, name).copy() for name in
                  ("voltage", "threshold_offset", "refractory", "spikes")}
        for name, projection in projections.items():
            arrays[f"{name}_pre"] = projection.pre
            arrays[f"{name}_post"] = projection.post
            arrays[f"{name}_weights"] = (
                network._base_hidden_output_weights
                if name == "hidden_output" else projection.weights).copy()
            arrays[f"{name}_pre"] = arrays[f"{name}_pre"].copy()
            arrays[f"{name}_post"] = arrays[f"{name}_post"].copy()
        context_metadata = []
        for index, (context_id, context_state) in enumerate(
                network.context_output_weights.items()):
            array_key = f"context_output_{index:04d}_weights"
            arrays[array_key] = context_state.weights.copy()
            context_metadata.append({
                "context_id": context_id,
                "signature": context_state.signature.tolist(),
                "last_used": context_state.last_used,
                "reused_from": context_state.reused_from,
                "array_key": array_key,
            })
        tool_names = [key[5:] for key in network.output_groups if key.startswith("tool:")]
        metadata = {
            "version": self.VERSION,
            "seed_state": deepcopy(network.rng.bit_generator.state),
            "tick_count": network.tick_count, "dt_ms": network.dt_ms,
            "noise": network.noise, "connectivity": network.connectivity,
            "n_sensor": network.n_sensor, "n_hidden": network.n_hidden, "n_output": network.n_output,
            "population_params": {"tau_m_ms": network.population.tau_m_ms,
                "threshold": network.population.threshold, "reset": network.population.reset,
                "refractory_ms": network.population.refractory_ms,
                "adaptive_increment": network.population.adaptive_increment,
                "adaptive_tau_ms": network.population.adaptive_tau_ms},
            "base_n_output": network.hidden_to_output.n_post - len(tool_names) * network.tool_group_size,
            "tool_group_size": network.tool_group_size, "tool_groups": tool_names,
            "hidden_sign": network.hidden_sign.tolist(),
            "context_output_projections": context_metadata,
            "state": deepcopy(state or {}),
        }
        return SnapshotPayload(arrays, metadata)

    def write_snapshot(self, snapshot: SnapshotPayload) -> None:
        """Compress and atomically publish a detached snapshot."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_npz: Path | None = None
        tmp_json: Path | None = None
        snapshot_npz_name = f"{self.path.stem}.{uuid.uuid4().hex}.npz"
        json_path = self.path.with_suffix(".json")
        try:
            fd, tmp_npz_name = tempfile.mkstemp(dir=self.path.parent, suffix=".npz.tmp")
            os.close(fd)
            tmp_npz = Path(tmp_npz_name)
            with tmp_npz.open("wb") as stream:
                np.savez_compressed(stream, **snapshot.arrays)
            digest = hashlib.sha256(tmp_npz.read_bytes()).hexdigest()
            metadata = deepcopy(snapshot.metadata)
            metadata["digest"] = digest
            metadata["npz_file"] = snapshot_npz_name
            fd, tmp_json_name = tempfile.mkstemp(dir=self.path.parent, suffix=".json.tmp")
            os.close(fd)
            tmp_json = Path(tmp_json_name)
            tmp_json.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp_npz, self.path.parent / snapshot_npz_name)
            tmp_npz = None
            os.replace(tmp_json, json_path)
            tmp_json = None
            self._prune()
        finally:
            if tmp_npz is not None:
                tmp_npz.unlink(missing_ok=True)
            if tmp_json is not None:
                tmp_json.unlink(missing_ok=True)

    def save(self, network: SpikingNetwork, state: dict[str, object] | None = None) -> None:
        self.write_snapshot(self.capture(network, state))

    def _prune(self) -> None:
        backups = sorted(self.path.parent.glob(f"{self.path.stem}.*.npz"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for item in backups[self.backups:]:
            item.unlink(missing_ok=True)

    def export_zip(self, destination: Path, memory_path: Path | None = None) -> None:
        metadata = json.loads(self.path.with_suffix(".json").read_text(encoding="utf-8"))
        network_file = self.path.parent / metadata["npz_file"]
        self.load()  # Verify the manifest and checksum before exporting.
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(self.path.with_suffix(".json"), "creature.json")
            archive.write(network_file, metadata["npz_file"])
            if memory_path is not None and memory_path.exists():
                archive.write(memory_path, "episodes.sqlite3")

    def import_zip(self, source: Path, memory_path: Path | None = None) -> dict[str, object]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source, "r") as archive:
            names = archive.namelist()
            npz_members = [name for name in names if name.endswith(".npz")]
            if len(names) > 3 or any(Path(name).name != name for name in names):
                raise ValueError("backup contains unexpected paths")
            if "creature.json" not in names or len(npz_members) != 1 or not set(names).issubset(
                    {"creature.json", "episodes.sqlite3", npz_members[0]}):
                raise ValueError("backup has unexpected members")
            if sum(item.file_size for item in archive.infolist()) > 200 * 1024 * 1024:
                raise ValueError("backup is larger than the import limit")
            metadata = json.loads(archive.read("creature.json").decode("utf-8"))
            npz_name = metadata.get("npz_file")
            if not isinstance(npz_name, str) or Path(npz_name).name != npz_name or npz_name not in names:
                raise ValueError("backup snapshot data file is missing")
            with tempfile.TemporaryDirectory(dir=self.path.parent) as temporary:
                temp_dir = Path(temporary)
                (temp_dir / "creature.json").write_bytes(archive.read("creature.json"))
                (temp_dir / npz_name).write_bytes(archive.read(npz_name))
                verified = SnapshotStore(temp_dir / "creature")
                _, state = verified.load()
                new_name = f"{self.path.stem}.{uuid.uuid4().hex}.npz"
                metadata["npz_file"] = new_name
                final_npz = self.path.parent / new_name
                os.replace(temp_dir / npz_name, final_npz)
                fd, temp_json_name = tempfile.mkstemp(dir=self.path.parent, suffix=".json.tmp")
                os.close(fd)
                temp_json = Path(temp_json_name)
                temp_json.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
                if memory_path is not None and "episodes.sqlite3" in names:
                    fd, temp_memory_name = tempfile.mkstemp(dir=memory_path.parent, suffix=".sqlite.tmp")
                    os.close(fd)
                    temp_memory = Path(temp_memory_name)
                    temp_memory.write_bytes(archive.read("episodes.sqlite3"))
                    os.replace(temp_memory, memory_path)
                os.replace(temp_json, self.path.with_suffix(".json"))
        self._prune()
        return state

    def load(self) -> tuple[SpikingNetwork, dict[str, object]]:
        json_path = self.path.with_suffix(".json")
        metadata = json.loads(json_path.read_text(encoding="utf-8"))
        version = metadata.get("version")
        if version not in (1, self.VERSION):
            raise ValueError("unsupported snapshot version")
        npz_name = metadata.get("npz_file")
        if not isinstance(npz_name, str) or Path(npz_name).name != npz_name:
            raise ValueError("invalid snapshot data filename")
        npz_path = self.path.parent / npz_name
        if hashlib.sha256(npz_path.read_bytes()).hexdigest() != metadata["digest"]:
            raise ValueError("snapshot checksum mismatch")
        total = metadata["n_sensor"] + metadata["n_hidden"] + metadata["base_n_output"]
        net = SpikingNetwork(total, connectivity=metadata.get("connectivity", .1),
                             dt_ms=metadata["dt_ms"], seed=0, noise=metadata["noise"],
                             tool_group_size=metadata["tool_group_size"])
        for key, value in metadata.get("population_params", {}).items():
            setattr(net.population, key, value)
        for name in metadata["tool_groups"]:
            net.add_tool_group(name)
        projections = {"sensor_hidden": net.sensor_to_hidden, "recurrent": net.recurrent,
                       "hidden_output": net.hidden_to_output}
        with np.load(npz_path, allow_pickle=False) as data:
            for key in ("voltage", "threshold_offset", "refractory", "spikes"):
                getattr(net.population, key)[:] = data[key]
            for name, projection in projections.items():
                projection.pre = data[f"{name}_pre"].astype(np.int32, copy=True)
                projection.post = data[f"{name}_post"].astype(np.int32, copy=True)
                projection.weights = data[f"{name}_weights"].astype(np.float32, copy=True)
                projection.rebuild()
            net.restore_base_output_weights(net.hidden_to_output.weights)
            if version >= 2:
                for item in metadata.get("context_output_projections", []):
                    array_key = item.get("array_key")
                    if not isinstance(array_key, str) or array_key not in data:
                        raise ValueError("snapshot context projection weights are missing")
                    net.restore_context_output_weights(
                        str(item["context_id"]),
                        np.asarray(item["signature"], dtype=np.float32),
                        data[array_key], int(item.get("last_used", 0)),
                        item.get("reused_from"))
        net.hidden_sign[:] = metadata["hidden_sign"]
        net.recurrent.source_sign[:] = net.hidden_sign
        net.hidden_to_output.source_sign[:] = net.hidden_sign
        net.rng.bit_generator.state = metadata["seed_state"]
        net.tick_count = int(metadata["tick_count"])
        return net, metadata.get("state", {})

from __future__ import annotations

"""Reproducible component-level baseline for the current NumPy/SciPy SNN.

This is measurement tooling only. It does not modify model parameters or source
code, and runs against the checked-out implementation.
"""

import argparse
import cProfile
import copy
import gc
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import pstats
import statistics
import sys
import tempfile
import time
import tracemalloc

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synapse_pet.core.decoding import RateDecoder
from synapse_pet.core.homeostasis import Homeostasis
from synapse_pet.core.network import SpikingNetwork
from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.runtime.engine import PetEngine
from synapse_pet.runtime.persistence import SnapshotStore

SEED = 20261102
CONTEXT = {"input_rate": 0.72, "window_category": "editor",
           "activity": 0.35, "hour": 0.62}


def _summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(array)),
        "stddev": float(np.std(array)),
        "p50": float(np.percentile(array, 50)),
        "p95": float(np.percentile(array, 95)),
        "p99": float(np.percentile(array, 99)),
    }


def _measure(function, repeats: int, warmup: int = 10) -> dict[str, object]:
    for _ in range(warmup):
        function()
    wall_ms: list[float] = []
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(repeats):
            wall_start = time.perf_counter_ns()
            function()
            wall_ms.append((time.perf_counter_ns() - wall_start) / 1_000_000.0)
    finally:
        if was_enabled:
            gc.enable()

    # Windows thread_time resolution can be coarser than a short NumPy call.
    # Time batches sized to ~50 ms, then divide by the operation count. This
    # avoids reporting a quantized 0.0 ms for sub-millisecond components.
    estimated_ms = max(float(np.mean(wall_ms)), 1e-4)
    batch_size = max(1, min(5000, int(np.ceil(50.0 / estimated_ms))))
    cpu_ms: list[float] = []
    for _ in range(20):
        cpu_start = time.thread_time_ns()
        for _ in range(batch_size):
            function()
        cpu_ms.append((time.thread_time_ns() - cpu_start)
                      / 1_000_000.0 / batch_size)

    # Allocation tracing is a separate pass so tracemalloc does not distort
    # latency samples. It reports net live blocks/bytes and peak traced bytes;
    # short-lived allocations freed during a call are not represented in the
    # net delta.
    allocation_repeats = max(3, min(20, repeats // 5))
    gc.collect()
    tracemalloc.start()
    before = tracemalloc.take_snapshot()
    _, peak_before = tracemalloc.get_traced_memory()
    for _ in range(allocation_repeats):
        function()
    after = tracemalloc.take_snapshot()
    _, peak_after = tracemalloc.get_traced_memory()
    differences = after.compare_to(before, "lineno")
    live_blocks = sum(item.count_diff for item in differences)
    live_bytes = sum(item.size_diff for item in differences)
    tracemalloc.stop()

    return {
        "wall_ms": _summary(wall_ms),
        "cpu_ms": _summary(cpu_ms),
        "allocation_probe": {
            "operations": allocation_repeats,
            "net_live_blocks_per_operation": live_blocks / allocation_repeats,
            "net_live_bytes_per_operation": live_bytes / allocation_repeats,
            "peak_traced_bytes_delta_per_operation": max(
                0, peak_after - peak_before) / allocation_repeats,
            "note": "Net live deltas omit short-lived allocations that are freed within an operation.",
        },
        "samples": repeats,
        "warmup": warmup,
        "cpu_batch_operations": batch_size,
    }


def _unique_array_bytes(root: object) -> int:
    seen: set[int] = set()
    total = 0

    def visit(value: object) -> None:
        nonlocal total
        if isinstance(value, np.ndarray):
            if id(value) not in seen:
                seen.add(id(value))
                total += int(value.nbytes)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
        elif hasattr(value, "__dict__"):
            for item in vars(value).values():
                visit(item)

    visit(root)
    return total


def _network_counts(network: SpikingNetwork) -> dict[str, object]:
    projections = (network.sensor_to_hidden, network.recurrent,
                   network.hidden_to_output)
    return {
        "requested_neurons": network.population.size,
        "sensor_neurons": network.n_sensor,
        "hidden_neurons": network.n_hidden,
        "output_neurons": network.hidden_to_output.n_post,
        "connection_counts": {projection.name: len(projection.weights)
                              for projection in projections},
        "connections_total": int(sum(len(p.weights) for p in projections)),
        "numpy_array_bytes_unique": _unique_array_bytes(network),
    }


def _hardware() -> dict[str, object]:
    memory = psutil.virtual_memory()
    try:
        frequency = psutil.cpu_freq()
    except Exception:
        frequency = None
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
        "logical_cpus": psutil.cpu_count(logical=True),
        "physical_cpus": psutil.cpu_count(logical=False),
        "cpu_frequency_mhz": (None if frequency is None else frequency.current),
        "ram_total_mib": memory.total / (1024 * 1024),
    }


def _profile(engine: PetEngine, steps: int, output: Path) -> list[dict[str, object]]:
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(steps):
        engine.tick(CONTEXT, 50.0, active=True)
    profiler.disable()
    output.parent.mkdir(parents=True, exist_ok=True)
    profiler.dump_stats(str(output))
    stats = pstats.Stats(profiler).strip_dirs().sort_stats("cumtime")
    rows: list[dict[str, object]] = []
    for (filename, line, function), values in stats.stats.items():
        primitive, total, own, cumulative, _callers = values
        rows.append({"function": function, "file": filename, "line": line,
                     "calls": int(total), "primitive_calls": int(primitive),
                     "self_seconds": float(own),
                     "cumulative_seconds": float(cumulative)})
    rows.sort(key=lambda row: float(row["cumulative_seconds"]), reverse=True)
    return rows[:30]


def run(samples: int, output: Path, profile_dir: Path) -> dict[str, object]:
    process = psutil.Process()
    results: dict[str, object] = {}
    rss_before = process.memory_info().rss
    start = time.perf_counter_ns()
    cold_cpu_start = time.thread_time_ns()
    network = SpikingNetwork(600, connectivity=0.10, dt_ms=2.0,
                             seed=SEED, noise=0.015)
    initialization_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    cold_initialization_cpu_ms = (
        time.thread_time_ns() - cold_cpu_start) / 1_000_000.0
    results["network_initialization_600_warm"] = _measure(
        lambda: SpikingNetwork(600, connectivity=0.10, dt_ms=2.0,
                               seed=SEED, noise=0.015),
        max(10, samples // 5), warmup=2)
    counts = _network_counts(network)
    rng = np.random.default_rng(SEED)
    lif = network.population
    current = np.full(lif.size, np.float32(0.02), dtype=np.float32)
    pre = rng.random(network.n_hidden) < 0.04
    post = rng.random(network.n_hidden) < 0.03
    sensor_pre = rng.random(network.n_sensor) < 0.04
    output_post = rng.random(network.hidden_to_output.n_post) < 0.03
    synaptic_spikes = {
        network.sensor_to_hidden.name: sensor_pre,
        network.recurrent.name: pre,
        network.hidden_to_output.name: pre,
    }
    projections = (network.sensor_to_hidden, network.recurrent,
                   network.hidden_to_output)
    learners = {projection.name: RewardSTDP() for projection in projections}
    for projection in projections:
        learners[projection.name].initialize(projection)
    decoder = RateDecoder(network.output_groups)
    homeostasis = Homeostasis()
    full_spikes = np.zeros(network.population.size, dtype=np.bool_)
    full_spikes[:network.n_sensor] = sensor_pre
    full_spikes[network.hidden_start:network.output_start] = pre
    full_spikes[network.output_start:network.output_start + len(output_post)] = output_post

    # Warm the reusable model-state cases before collecting distributions.
    cases: dict[str, tuple[object, int]] = {
        "lif_update_600_runtime_population": (
            lambda: lif.step(current, network.dt_ms, network.rng,
                             noise_std=network.noise), samples),
        "sparse_propagation_all_three_projections": (
            lambda: [projection.currents(synaptic_spikes[projection.name])
                     for projection in projections], samples),
        "stdp_mark_all_three_projections": (
            lambda: [
                learners["sensor_hidden"].mark(
                    network.sensor_to_hidden, sensor_pre, pre,
                    network.dt_ms / 1000.0),
                learners["recurrent"].mark(
                    network.recurrent, pre, post, network.dt_ms / 1000.0),
                learners["hidden_output"].mark(
                    network.hidden_to_output, pre, output_post,
                    network.dt_ms / 1000.0),
            ], samples),
        "reward_application_all_three_projections": (
            lambda: [learners[p.name].apply_reward(p, 0.10)
                     for p in projections], samples),
        "homeostasis_update_250ms": (
            lambda: homeostasis.update(network.population, full_spikes, 0.25,
                                       projections), samples),
        "decoder_update": (
            lambda: decoder.update(full_spikes.astype(np.float32), 0.05), samples),
    }

    with tempfile.TemporaryDirectory(prefix="synapse_component_baseline_") as folder:
        engine = PetEngine(seed=SEED, neurons=600, data_dir=Path(folder))
        network_runtime = engine.network
        context = dict(CONTEXT)
        cases["full_tick_active_50ms_25_substeps"] = (
            lambda: engine.tick(context, 50.0, active=True), samples)
        cases["full_tick_rest_250ms_one_substep"] = (
            lambda: engine.tick({}, 250.0, active=False), samples)
        cases["stimulus_encoding_rates_and_poisson_spikes"] = (
            lambda: engine.encoder.encode(context, 2.0), samples)

        for name, (function, count) in cases.items():
            results[name] = _measure(function, count,
                                     warmup=min(10, max(2, count // 10)))

        # Measure growth on an independent copy so each sample starts from the
        # same 600-neuron sparse topology; copying is intentionally outside the
        # timed interval, while growth itself is timed.
        growth_template = SpikingNetwork(600, connectivity=0.10, dt_ms=2.0,
                                         seed=SEED, noise=0.015)
        def grow_once() -> None:
            candidate = copy.deepcopy(growth_template)
            candidate.grow_population(800, seed=SEED + 1)
        results["network_growth_600_to_800_excludes_template_copy"] = _measure(
            grow_once, max(8, samples // 5), warmup=2)

        store = SnapshotStore(Path(folder) / "creature")
        state = engine._snapshot_state()
        def save_once() -> None:
            store.save(network_runtime, state)
        results["snapshot_save_capture_compress_atomic_write"] = _measure(
            save_once, max(8, samples // 5), warmup=2)
        store.save(network_runtime, state)
        load_duration: list[float] = []
        load_cpu: list[float] = []
        for _ in range(max(8, samples // 5)):
            wall_start = time.perf_counter_ns()
            cpu_start = time.thread_time_ns()
            store.load()
            load_cpu.append((time.thread_time_ns() - cpu_start) / 1_000_000.0)
            load_duration.append((time.perf_counter_ns() - wall_start) / 1_000_000.0)
        results["snapshot_load_checksum_rebuild"] = {
            "wall_ms": _summary(load_duration), "cpu_ms": _summary(load_cpu),
            "samples": len(load_duration), "warmup": 0,
        }

        profile_rows = _profile(
            engine, max(30, min(120, samples)),
            profile_dir / "baseline_active.prof")
        engine_summary = {
            "network": _network_counts(network_runtime),
            "memory_rss_after_engine_mib": process.memory_info().rss / (1024 * 1024),
            "profile_top_30_cumulative": profile_rows,
        }
        engine.stop()

    results["network_initialization_600_first_instance"] = {
        "wall_ms": {"mean": initialization_ms, "stddev": 0.0,
                    "p50": initialization_ms, "p95": initialization_ms,
                    "p99": initialization_ms},
        "cpu_ms": {"mean": cold_initialization_cpu_ms, "stddev": 0.0,
                    "p50": cold_initialization_cpu_ms,
                    "p95": cold_initialization_cpu_ms,
                    "p99": cold_initialization_cpu_ms},
        "samples": 1,
        "note": "single cold construction measurement; import time excluded",
    }
    results["memory"] = {
        "rss_before_mib": rss_before / (1024 * 1024),
        "rss_after_initial_network_mib": process.memory_info().rss / (1024 * 1024),
        "network_array_bytes_unique": counts["numpy_array_bytes_unique"],
        "network_structure": counts,
        "runtime_engine": engine_summary,
    }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/baseline_components.json")
    parser.add_argument("--profile-dir", type=Path,
                        default=ROOT / "benchmarks/profile")
    args = parser.parse_args()
    if args.samples < 10:
        parser.error("--samples must be at least 10")
    results: dict[str, object] = {
        "schema": 1,
        "measurement_kind": "phase1_components_before_optimization",
        "timestamp_local": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": _hardware(),
        "libraries": {"numpy": np.__version__, "psutil": psutil.__version__},
        "configuration": {
            "seed": SEED, "requested_neurons": 600, "connectivity": 0.10,
            "dt_ms": 2.0, "background_noise": 0.015,
            "active_tick_ms": 50.0, "rest_tick_ms": 250.0,
            "active_substeps": 25, "rest_substeps": 1,
            "samples": args.samples,
        },
        "timing_units": "milliseconds; perf_counter wall and thread_time CPU are separate",
        "results": {},
    }
    for package in ("scipy", "PyYAML", "PySide6_Essentials", "Pillow"):
        try:
            results["libraries"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            results["libraries"][package] = None
    results["results"] = run(args.samples, args.output, args.profile_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "profile": str(args.profile_dir / "baseline_active.prof"),
                      "components": list(results["results"])}, indent=2))


if __name__ == "__main__":
    main()

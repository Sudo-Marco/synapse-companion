from __future__ import annotations

import argparse
import cProfile
import gc
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import pstats
import subprocess
import sys
import tempfile
import time
import tracemalloc

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synapse_pet.core.encoding import PopulationEncoder
from synapse_pet.runtime.engine import PetEngine
from synapse_pet.sim.determinism import reference_snapshot


def _measure_ticks(engine: PetEngine, regime: str, count: int) -> dict[str, object]:
    context = ({"input_rate": 0.72, "window_category": "editor",
                "activity": 0.35, "hour": 0.62} if regime == "active" else {})
    duration_ms = 50.0 if regime == "active" else 250.0
    active = regime == "active"

    def tick() -> None:
        engine.tick(context, duration_ms, active=active,
                    contacted=False)

    for _ in range(20):
        tick()

    wall_ms: list[float] = []
    cpu_ms: list[float] = []
    cpu_before = time.thread_time_ns()
    for _ in range(count):
        wall_start = time.perf_counter_ns()
        thread_start = time.thread_time_ns()
        tick()
        cpu_ms.append((time.thread_time_ns() - thread_start) / 1_000_000.0)
        wall_ms.append((time.perf_counter_ns() - wall_start) / 1_000_000.0)
    cpu_ms_total = (time.thread_time_ns() - cpu_before) / 1_000_000.0

    tracemalloc.start()
    before = tracemalloc.take_snapshot()
    _, peak_before = tracemalloc.get_traced_memory()
    for _ in range(count):
        tick()
    after = tracemalloc.take_snapshot()
    current_after, peak_after = tracemalloc.get_traced_memory()
    allocation_stats = after.compare_to(before, "lineno")
    live_blocks_delta = sum(item.count_diff for item in allocation_stats)
    live_bytes_delta = sum(item.size_diff for item in allocation_stats)
    tracemalloc.stop()

    # Sleep runs the same low-duty network tick as rest, then waits between ticks.
    # Consolidation is measured separately because it occurs once on sleep entry.
    if regime == "sleep":
        engine.sleep.sleeping = True
        if engine.sleep.replay_enabled and not engine.memory.top_rpe(1):
            for index in range(engine.sleep.max_replay_episodes):
                engine.memory.add(f"benchmark_context_{index % 3}", "benchmark_action",
                                  .5, rpe=(.8 if index % 2 else -.8))
        started = time.thread_time_ns()
        engine.sleep.consolidate(engine.network, engine.memory,
                                 engine.learners, engine.neuromodulators)
        consolidation_cpu_ms = (time.thread_time_ns() - started) / 1_000_000.0
    else:
        consolidation_cpu_ms = None

    return {
        "ticks": count,
        "simulated_ms_per_tick": duration_ms,
        "mean_cpu_ms": cpu_ms_total / count,
        "cpu_ms": _summary(cpu_ms),
        "wall_ms": _summary(wall_ms),
        "p95_wall_ms": float(np.percentile(wall_ms, 95)),
        "mean_wall_ms": float(np.mean(wall_ms)),
        "live_traced_blocks_delta_per_tick": live_blocks_delta / count,
        "live_traced_bytes_delta_per_tick": live_bytes_delta / count,
        "peak_traced_bytes_delta_per_tick": max(0, peak_after - peak_before) / count,
        "sleep_entry_consolidation_cpu_ms": consolidation_cpu_ms,
    }


def _summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(array)),
        "stddev": float(np.std(array)),
        "p50": float(np.percentile(array, 50)),
        "p95": float(np.percentile(array, 95)),
        "p99": float(np.percentile(array, 99)),
    }


def _array_bytes(network) -> int:
    arrays = [network.population.voltage, network.population.threshold_offset,
              network.population.refractory, network.population.spikes,
              network.hidden_sign, network.sensor_to_hidden.pre,
              network.sensor_to_hidden.post, network.sensor_to_hidden.weights,
              network.recurrent.pre, network.recurrent.post,
              network.recurrent.weights, network.hidden_to_output.pre,
              network.hidden_to_output.post, network.hidden_to_output.weights,
              network._base_hidden_output_weights]
    for context in network.context_output_weights.values():
        arrays.extend((context.signature, context.weights))
    for projection in (network.sensor_to_hidden, network.recurrent,
                       network.hidden_to_output):
        matrix = getattr(projection, "_matrix", None)
        if matrix is not None:
            arrays.extend((matrix.data, matrix.indices, matrix.indptr))
    return sum(int(array.nbytes) for array in {id(item): item for item in arrays}.values())


def _environment() -> dict[str, object]:
    memory = psutil.virtual_memory()
    try:
        frequency = psutil.cpu_freq()
    except Exception:
        frequency = None
    packages = {}
    for package in ("numpy", "scipy", "psutil", "PyYAML", "PySide6_Essentials", "Pillow"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    try:
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--short"], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.splitlines()
    except Exception:
        branch, head, status = None, None, []
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
        "logical_cpus": psutil.cpu_count(logical=True),
        "physical_cpus": psutil.cpu_count(logical=False),
        "cpu_frequency_mhz": None if frequency is None else frequency.current,
        "ram_total_mib": memory.total / (1024 * 1024),
        "libraries": packages,
        "git": {"branch": branch, "head": head, "dirty": bool(status),
                "status_short": status},
    }


def _measure_spike_activity(engine: PetEngine, regime: str,
                            count: int) -> dict[str, object]:
    network = engine.network
    accumulated = np.zeros(3, dtype=np.int64)
    simulated_seconds = 0.0
    original_step = network.step

    def step_and_count(current=None):
        nonlocal simulated_seconds
        spikes = original_step(current)
        hidden = slice(network.hidden_start, network.output_start)
        outputs = slice(network.output_start,
                        network.output_start + network.hidden_to_output.n_post)
        accumulated[0] += int(spikes[:network.n_sensor].sum())
        accumulated[1] += int(spikes[hidden].sum())
        accumulated[2] += int(spikes[outputs].sum())
        simulated_seconds += network.dt_ms / 1000.0
        return spikes

    network.step = step_and_count
    try:
        for _ in range(count):
            context = ({"input_rate": 0.72, "window_category": "editor",
                        "activity": 0.35, "hour": 0.62}
                       if regime == "active" else {})
            engine.tick(context, 50.0 if regime == "active" else 250.0,
                        active=(regime == "active"))
    finally:
        network.step = original_step

    sizes = (network.n_sensor, network.n_hidden, network.hidden_to_output.n_post)
    labels = ("sensor", "hidden", "output")
    return {
        "rates_hz": {label: float(spikes / (max(simulated_seconds, 1e-9) * size))
                     for label, spikes, size in zip(labels, accumulated, sizes)},
        "spikes": {label: int(spikes)
                   for label, spikes in zip(labels, accumulated)},
        "neurons": {label: int(size) for label, size in zip(labels, sizes)},
        "simulated_seconds": simulated_seconds,
        "samples": count,
    }


def _profile_top_five(engine: PetEngine, steps: int,
                      profile_path: Path | None = None) -> list[dict[str, object]]:
    profiler = cProfile.Profile()
    context = {"input_rate": 0.72, "window_category": "editor",
               "activity": 0.35, "hour": 0.62}
    profiler.enable()
    for _ in range(steps):
        engine.tick(context, 50.0, active=True)
    profiler.disable()
    if profile_path is not None:
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(profile_path))
    stats = pstats.Stats(profiler).strip_dirs().sort_stats("cumtime")
    return _sorted_profile_rows(stats, limit=5)


def _sorted_profile_rows(stats: pstats.Stats, limit: int) -> list[dict[str, object]]:
    rows = []
    for (filename, line, function), values in stats.stats.items():
        primitive_calls, total_calls, total_seconds, cumulative_seconds, _callers = values
        rows.append({"function": function, "file": filename, "line": line,
                     "calls": int(total_calls),
                     "total_seconds": float(total_seconds),
                     "cumulative_seconds": float(cumulative_seconds)})
    rows.sort(key=lambda row: float(row["cumulative_seconds"]), reverse=True)
    return rows[:limit]


def _memory_probe(neurons: int) -> None:
    temporary = tempfile.TemporaryDirectory(prefix="synapse_snn_mem_")
    engine = PetEngine(neurons=neurons, data_dir=Path(temporary.name))
    process = psutil.Process()
    result = {
        "neurons_requested": neurons,
        "neurons_total_with_tools": engine.network.population.size,
        "rss_mib": process.memory_info().rss / (1024 * 1024),
        "connections": int(len(engine.network.sensor_to_hidden.weights)
                           + len(engine.network.recurrent.weights)
                           + len(engine.network.hidden_to_output.weights)),
        "connections_by_projection": {
            projection.name: int(len(projection.weights)) for projection in
            (engine.network.sensor_to_hidden, engine.network.recurrent,
             engine.network.hidden_to_output)},
        "numpy_array_bytes_unique": _array_bytes(engine.network),
    }
    # PetEngine installs a rotating file handler on a process-global logger.
    # Close it before TemporaryDirectory removes the data folder on Windows.
    engine.stop()
    del engine
    gc.collect()
    temporary.cleanup()
    print(json.dumps(result))


def _run_idle_cpu_probe(seconds: float,
                        tool_output_inhibition: bool = False) -> dict[str, float]:
    with tempfile.TemporaryDirectory(prefix="synapse_snn_idle_") as folder:
        engine = PetEngine(data_dir=Path(folder))
        engine.network.tool_output_inhibition_enabled = tool_output_inhibition
        process = psutil.Process()
        engine.start()
        cpu_before = process.cpu_times()
        process_cpu_before = time.process_time()
        wall_before = time.perf_counter()
        time.sleep(seconds)
        elapsed = time.perf_counter() - wall_before
        process_cpu_elapsed = time.process_time() - process_cpu_before
        cpu_after = process.cpu_times()
        result = {"seconds": elapsed,
                  "single_core_cpu_percent": 100.0 * (
                      process_cpu_elapsed / max(elapsed, 1e-9)),
                  "psutil_single_core_cpu_percent_quantized": 100.0 * (
                      (cpu_after.user - cpu_before.user)
                      + (cpu_after.system - cpu_before.system)) / max(elapsed, 1e-9)}
        engine.stop()
        del engine
        gc.collect()
        return result


def _child_memory(neurons: int) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--memory-probe", str(neurons)],
        capture_output=True, text=True, check=True, cwd=ROOT,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _percent_change(before: float, after: float) -> float | None:
    if abs(before) < 1e-12:
        return None
    return (after - before) / abs(before) * 100.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure baseline CPU/RAM and determinism for the SNN")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks" / "results" / "snn_baseline.json")
    parser.add_argument("--compare", type=Path,
                        help="compare numeric phase metrics against a previous JSON report")
    parser.add_argument("--ticks", type=int, default=160)
    parser.add_argument("--profile-steps", type=int, default=120)
    parser.add_argument("--idle-seconds", type=float, default=4.0)
    parser.add_argument("--profile-dir", type=Path,
                        default=ROOT / "benchmarks" / "profile")
    parser.add_argument("--tool-output-inhibition", action="store_true",
                        help="measure the optional tool-output competition path")
    parser.add_argument("--sleep-replay", action="store_true",
                        help="measure bounded replay at sleep entry")
    parser.add_argument("--memory-probe", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.memory_probe:
        _memory_probe(args.memory_probe)
        return

    results: dict[str, object] = {
        "schema": 1,
        "baseline_kind": "phase1_pre_optimization" if not args.compare else "comparison_run",
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "environment": _environment(),
        "seed": 20261102,
        "tick_samples": args.ticks,
        "experimental_features": {
            "tool_output_inhibition": bool(args.tool_output_inhibition),
            "sleep_replay": bool(args.sleep_replay),
        },
        "determinism": reference_snapshot(),
        "memory": {"600": _child_memory(600), "1000": _child_memory(1000)},
    }

    with tempfile.TemporaryDirectory(prefix="synapse_snn_bench_") as folder:
        engine = PetEngine(seed=20261102, neurons=600, data_dir=Path(folder))
        engine.network.tool_output_inhibition_enabled = args.tool_output_inhibition
        engine.network.tool_output_inhibition_strength = max(0.0, float(
            engine.config.get("network", {}).get(
                "tool_output_inhibition_strength", 0.35)))
        engine.sleep.replay_enabled = args.sleep_replay
        tick_cost: dict[str, object] = {}
        rates: dict[str, object] = {}
        spike_activity: dict[str, object] = {}
        for regime in ("active", "rest", "sleep"):
            tick_cost[regime] = _measure_ticks(engine, regime, args.ticks)
            activity_sample = _measure_spike_activity(
                engine, regime, min(args.ticks, 80))
            rates[regime] = activity_sample["rates_hz"]
            spike_activity[regime] = activity_sample
        tick_cost_1000: dict[str, object] = {}
        with tempfile.TemporaryDirectory(prefix="synapse_snn_1000_") as folder_1000:
            engine_1000 = PetEngine(seed=20261102, neurons=1000,
                                    data_dir=Path(folder_1000))
            engine_1000.network.tool_output_inhibition_enabled = args.tool_output_inhibition
            engine_1000.network.tool_output_inhibition_strength = max(0.0, float(
                engine_1000.config.get("network", {}).get(
                    "tool_output_inhibition_strength", 0.35)))
            engine_1000.sleep.replay_enabled = args.sleep_replay
            # Engine currently hard-codes 24 inputs per group (96 total). Scale
            # the probe encoder to the network sensor population while keeping
            # the production runtime unchanged during phase-0 baseline capture.
            sensor_count = engine_1000.network.n_sensor
            base, remainder = divmod(sensor_count, 4)
            groups = {name: base + (index < remainder)
                      for index, name in enumerate(
                          ("input_rate", "window_category", "activity", "hour"))}
            engine_1000.encoder = PopulationEncoder(groups, seed=20261102)
            tick_cost_1000["active"] = _measure_ticks(engine_1000, "active", args.ticks)
            activity_sample = _measure_spike_activity(
                engine_1000, "active", min(args.ticks, 80))
            rates["1000_active"] = activity_sample["rates_hz"]
            spike_activity["1000_active"] = activity_sample
            tick_cost_1000["mean_cpu_ms_50ms_simulated"] = tick_cost_1000[
                "active"]["mean_cpu_ms"]
            engine_1000.stop()
            del engine_1000
            gc.collect()
        results["tick_cost_600"] = tick_cost
        results["tick_cost_1000"] = tick_cost_1000
        results["configuration"] = {
            "seed": 20261102,
            "network": {key: engine.config.get("network", {}).get(key)
                        for key in ("neurons", "recurrent_connectivity", "dt_ms",
                                    "tick_active_ms", "tick_idle_ms",
                                    "background_noise", "synaptic_gain",
                                    "tool_output_inhibition",
                                    "allow_neuron_growth_migration")},
            "runtime": {key: engine.config.get("runtime", {}).get(key)
                        for key in ("idle_tick_interval_s", "pet_idle_tick_interval_s",
                                    "active_timeout_s", "sleep_after_s")},
            "component_metrics_file": "baseline_components.json",
        }
        results["encoder_probe_note"] = (
            "The harness uses four encoder groups scaled to n_sensor for both 600 and "
            "1000-neuron comparisons. Phase 0 exposed that the original runtime hard-coded "
            "4x24 sensors; phase 1 now derives these group sizes from the network.")
        results["firing_rate_hz"] = rates
        results["spike_activity"] = spike_activity
        results["top_profile_costs"] = _profile_top_five(
            engine, args.profile_steps,
            args.profile_dir / "legacy_active.prof")
        engine.stop()
        del engine
        gc.collect()

    results["idle_process_cpu"] = _run_idle_cpu_probe(
        args.idle_seconds, tool_output_inhibition=args.tool_output_inhibition)
    results["allocation_metric_note"] = (
        "Python tracemalloc reports net live traced blocks/bytes per tick and peak traced bytes; "
        "it does not count short-lived allocations that are freed inside each tick.")
    results["regime_note"] = (
        "Active uses 50 ms simulated with 25 LIF steps. Rest and sleep each use one 250 ms "
        "low-duty LIF step; sleep adds a one-time consolidation measurement and the runtime "
        "waits 500 ms between sleep ticks.")

    if args.compare:
        before = json.loads(args.compare.read_text(encoding="utf-8"))
        changes = {}
        paths = (
            ("tick_cost_600.active.mean_cpu_ms", before["tick_cost_600"]["active"]["mean_cpu_ms"],
             results["tick_cost_600"]["active"]["mean_cpu_ms"]),
            ("tick_cost_1000.active.mean_cpu_ms", before["tick_cost_1000"]["active"]["mean_cpu_ms"],
             results["tick_cost_1000"]["active"]["mean_cpu_ms"]),
            ("idle_process_cpu.single_core_cpu_percent", before["idle_process_cpu"]["single_core_cpu_percent"],
             results["idle_process_cpu"]["single_core_cpu_percent"]),
            ("memory.600.rss_mib", before["memory"]["600"]["rss_mib"],
             results["memory"]["600"]["rss_mib"]),
            ("memory.1000.rss_mib", before["memory"]["1000"]["rss_mib"],
             results["memory"]["1000"]["rss_mib"]),
        )
        for name, old, new in paths:
            changes[name] = {"before": old, "after": new,
                             "change_percent": _percent_change(float(old), float(new))}
        results["comparison"] = changes

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "600_active_mean_cpu_ms": results["tick_cost_600"]["active"]["mean_cpu_ms"],
        "1000_active_mean_cpu_ms": results["tick_cost_1000"]["active"]["mean_cpu_ms"],
        "idle_cpu_percent_one_core": results["idle_process_cpu"]["single_core_cpu_percent"],
        "memory_600_mib": results["memory"]["600"]["rss_mib"],
        "memory_1000_mib": results["memory"]["1000"]["rss_mib"],
    }, indent=2))
    if "comparison" in results:
        print(json.dumps(results["comparison"], indent=2))
    profile_path = args.profile_dir / "baseline_profile.md"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_lines = ["# Profiling da SNN", "",
                     f"Relatório gerado por `{args.output.name}`.", "",
                     "Cinco maiores custos por tempo cumulativo durante ticks ativos:", ""]
    for index, item in enumerate(results["top_profile_costs"], 1):
        profile_lines.append(
            f"{index}. `{item['function']}` em `{item['file']}:{item['line']}` — "
            f"{item['cumulative_seconds']:.4f} s cumulativos, "
            f"{item['calls']} chamadas.")
    profile_path.write_text("\n".join(profile_lines) + "\n", encoding="utf-8")
    print(f"Profiling: {profile_path}")


if __name__ == "__main__":
    main()

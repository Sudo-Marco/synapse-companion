from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import psutil
import scipy

from synapse_pet.core.network import SpikingNetwork
from synapse_pet.neural_backend.cython_backend import CythonBackend
from synapse_pet.neural_backend.numpy_backend import NumpyBackend


def _state_equal(left: SpikingNetwork, right: SpikingNetwork) -> None:
    for name in ("voltage", "threshold_offset", "refractory", "spikes"):
        np.testing.assert_array_equal(
            getattr(left.population, name), getattr(right.population, name)
        )
    assert left.rng.bit_generator.state == right.rng.bit_generator.state
    assert left.tick_count == right.tick_count


def _run(network: SpikingNetwork, inputs: np.ndarray) -> int:
    spike_count = 0
    for sensory in inputs:
        spike_count += int(network.step(sensory).sum())
    return spike_count


def _validated_run(network: SpikingNetwork, inputs: np.ndarray):
    output_hash = hashlib.sha256()
    spike_count = 0
    population_counts = {"sensor": 0, "hidden": 0, "output": 0}
    for sensory in inputs:
        output = network.step(sensory)
        output_hash.update(output.tobytes())
        spike_count += int(output.sum())
        population_counts["sensor"] += int(output[:network.n_sensor].sum())
        population_counts["hidden"] += int(
            output[network.hidden_start:network.output_start].sum()
        )
        population_counts["output"] += int(
            output[network.output_start:].sum()
        )
    return spike_count, output_hash.hexdigest(), population_counts


def _measure(
    factory, inputs: np.ndarray, warmup: int, repeats: int, loops_per_sample: int
):
    wall_samples: list[float] = []
    cpu_samples: list[float] = []
    spikes = 0
    for _ in range(repeats):
        network = factory()
        _run(network, inputs[:warmup])
        cpu_start = time.process_time()
        wall_start = time.perf_counter()
        spikes = sum(_run(network, inputs) for _ in range(loops_per_sample))
        wall_samples.append(time.perf_counter() - wall_start)
        cpu_samples.append(time.process_time() - cpu_start)

    network = factory()
    _run(network, inputs[:warmup])
    tracemalloc.start()
    tracemalloc.reset_peak()
    for _ in range(loops_per_sample):
        _run(network, inputs)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "wall_seconds_mean": statistics.mean(wall_samples),
        "wall_seconds_median": statistics.median(wall_samples),
        "wall_seconds_p95": float(np.percentile(wall_samples, 95)),
        "cpu_seconds_mean": statistics.mean(cpu_samples),
        "wall_ms_per_tick_mean": (
            statistics.mean(wall_samples) * 1000
            / (len(inputs) * loops_per_sample)
        ),
        "cpu_ms_per_tick_mean": (
            statistics.mean(cpu_samples) * 1000
            / (len(inputs) * loops_per_sample)
        ),
        "python_traced_peak_bytes": int(peak_bytes),
        "spikes_across_network_last_sample": spikes,
        "wall_samples_seconds": wall_samples,
        "timed_ticks_per_sample": len(inputs) * loops_per_sample,
    }


def _measure_size(
    size: int,
    steps: int,
    warmup: int,
    repeats: int,
    loops_per_sample: int,
    seed: int,
):
    input_rng = np.random.default_rng(seed + 10)
    inputs = input_rng.normal(
        0.0, 0.22, size=(steps, int(size * 0.16))
    ).astype(np.float32)
    numpy_factory = lambda: SpikingNetwork(
        total_neurons=size, seed=seed, noise=0.025, backend=NumpyBackend()
    )
    cython_factory = lambda: SpikingNetwork(
        total_neurons=size, seed=seed, noise=0.025, backend=CythonBackend()
    )

    # Verify exact results before measuring any timings.
    numpy_check, cython_check = numpy_factory(), cython_factory()
    numpy_warmup = _validated_run(numpy_check, inputs[:warmup])
    cython_warmup = _validated_run(cython_check, inputs[:warmup])
    assert cython_warmup == numpy_warmup
    _state_equal(cython_check, numpy_check)

    numpy_result = _measure(
        numpy_factory, inputs, warmup, repeats, loops_per_sample
    )
    cython_result = _measure(
        cython_factory, inputs, warmup, repeats, loops_per_sample
    )

    # Re-run the entire sequence and compare end states, output count and RNG.
    numpy_check, cython_check = numpy_factory(), cython_factory()
    numpy_spikes, numpy_output_hash, population_counts = _validated_run(
        numpy_check, inputs
    )
    cython_spikes, cython_output_hash, cython_population_counts = _validated_run(
        cython_check, inputs
    )
    assert cython_spikes == numpy_spikes
    assert cython_output_hash == numpy_output_hash
    assert cython_population_counts == population_counts
    _state_equal(cython_check, numpy_check)
    population_sizes = {
        "sensor": numpy_check.n_sensor,
        "hidden": numpy_check.n_hidden,
        "output": numpy_check.population.size - numpy_check.output_start,
    }
    population_rates = {
        name: count / (steps * population_sizes[name])
        for name, count in population_counts.items()
    }

    return {
        "neurons": size,
        "sensor_neurons": int(size * 0.16),
        "ticks_per_sample": steps,
        "warmup_ticks": min(warmup, steps),
        "loops_per_timed_sample": loops_per_sample,
        "repeats": repeats,
        "seed": seed,
        "spikes_across_network_over_validation_sequence": numpy_spikes,
        "spike_vector_sha256": numpy_output_hash,
        "population_spikes_over_validation_sequence": population_counts,
        "population_sizes": population_sizes,
        "population_spikes_per_neuron_per_tick": population_rates,
        "numpy": numpy_result,
        "cython": cython_result,
        "speedup_wall": (
            numpy_result["wall_ms_per_tick_mean"]
            / cython_result["wall_ms_per_tick_mean"]
        ),
        "speedup_cpu": (
            numpy_result["cpu_ms_per_tick_mean"]
            / cython_result["cpu_ms_per_tick_mean"]
        ),
        "cpu_regression_fraction": (
            cython_result["cpu_ms_per_tick_mean"]
            / numpy_result["cpu_ms_per_tick_mean"] - 1.0
        ),
        "wall_regression_fraction": (
            cython_result["wall_ms_per_tick_mean"]
            / numpy_result["wall_ms_per_tick_mean"] - 1.0
        ),
        "exact_trajectory_match": True,
    }


def run(args):
    process = psutil.Process()
    rss_before = process.memory_info().rss
    sizes = [_measure_size(size, args.steps, args.warmup, args.repeats,
                           args.loops_per_sample, args.seed + index * 1009)
             for index, size in enumerate(args.neurons)]
    rss_after = process.memory_info().rss
    budget_met = all(
        case["cpu_regression_fraction"] <= args.max_regression
        for case in sizes
    )
    return {
        "benchmark": "cython_lif_full_network_tick",
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "cython": __import__("Cython").__version__,
            "rss_bytes_before": rss_before,
            "rss_bytes_after": rss_after,
            "rss_delta_bytes": rss_after - rss_before,
        },
        "cases": sizes,
        "performance_budget": {
            "max_cpu_regression_fraction": args.max_regression,
            "passed": budget_met,
        },
        "notes": [
            "CPU and wall values cover complete SpikingNetwork.step calls, including unchanged sparse propagation.",
            "RSS is process-wide; tracemalloc excludes native allocations and reports Python-tracked peak only.",
            "Per-step spike totals are diagnostics, not a target for changing the SNN.",
            "Exact trajectory includes spike outputs, LIF state, tick count, and network RNG state.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--neurons", type=int, nargs="+", default=[600, 1000])
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--loops-per-sample", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--max-regression", type=float, default=0.03)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args)
    serialized = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if not result["performance_budget"]["passed"]:
        raise SystemExit(
            "Cython LIF exceeded the configured tick regression budget; see the JSON result."
        )


if __name__ == "__main__":
    main()

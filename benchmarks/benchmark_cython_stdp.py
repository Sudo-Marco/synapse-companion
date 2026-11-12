from __future__ import annotations

import argparse
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

from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.core.synapses import SparseProjection
from synapse_pet.neural_backend.cython_backend import CythonBackend
from synapse_pet.neural_backend.numpy_backend import NumpyBackend


def _projection(n_pre: int, n_post: int, density: float, seed: int):
    rng = np.random.default_rng(seed)
    post, pre = np.nonzero(rng.random((n_post, n_pre)) < density)
    source_sign = rng.choice(
        np.array([-1.0, 1.0], dtype=np.float32), size=n_pre
    )
    weights = rng.uniform(0.02, 0.12, size=len(pre)).astype(np.float32)
    weights *= source_sign[pre]
    return SparseProjection(
        n_pre,
        n_post,
        pre.astype(np.int32),
        post.astype(np.int32),
        weights,
        source_sign,
    )


def _make_spikes(n_pre: int, n_post: int, steps: int, seed: int):
    rng = np.random.default_rng(seed)
    pre = rng.random((steps, n_pre)) < 0.035
    post = rng.random((steps, n_post)) < 0.055
    return pre, post


def _run_mark(backend, projection, learner, pre_spikes, post_spikes):
    learner.initialize(projection)
    for pre, post in zip(pre_spikes, post_spikes, strict=True):
        backend.update_stdp(learner, projection, pre, post, 0.002)


def _measure(backend, projection, learner, pre_spikes, post_spikes, repeats):
    wall_samples = []
    cpu_samples = []
    for _ in range(repeats):
        learner.initialize(projection)
        cpu_start = time.process_time()
        wall_start = time.perf_counter()
        _run_mark(backend, projection, learner, pre_spikes, post_spikes)
        wall_samples.append(time.perf_counter() - wall_start)
        cpu_samples.append(time.process_time() - cpu_start)

    learner.initialize(projection)
    tracemalloc.start()
    tracemalloc.reset_peak()
    _run_mark(backend, projection, learner, pre_spikes, post_spikes)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "wall_seconds_mean": statistics.mean(wall_samples),
        "wall_seconds_median": statistics.median(wall_samples),
        "wall_seconds_p95": float(np.percentile(wall_samples, 95)),
        "cpu_seconds_mean": statistics.mean(cpu_samples),
        "ns_per_update_mean": (
            statistics.mean(wall_samples) * 1e9 / len(pre_spikes)
        ),
        "python_traced_peak_bytes": int(peak_bytes),
        "wall_samples_seconds": wall_samples,
    }


def _measure_reward(backend, projection, learner, repeats, calls):
    base_weights = projection.weights.copy()
    learner.initialize(projection)
    rng = np.random.default_rng(2026)
    base_eligibility = rng.normal(
        size=len(projection.weights)
    ).astype(np.float32)
    wall_samples = []
    cpu_samples = []

    def restore():
        projection.weights[:] = base_weights
        learner.initialize(projection)
        learner.eligibility[:] = base_eligibility

    def apply_many():
        for _ in range(calls):
            backend.apply_reward(learner, projection, 0.37)

    for _ in range(repeats):
        restore()
        cpu_start = time.process_time()
        wall_start = time.perf_counter()
        apply_many()
        wall_samples.append(time.perf_counter() - wall_start)
        cpu_samples.append(time.process_time() - cpu_start)

    restore()
    tracemalloc.start()
    tracemalloc.reset_peak()
    apply_many()
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "calls_per_sample": calls,
        "wall_seconds_mean": statistics.mean(wall_samples),
        "wall_seconds_median": statistics.median(wall_samples),
        "wall_seconds_p95": float(np.percentile(wall_samples, 95)),
        "cpu_seconds_mean": statistics.mean(cpu_samples),
        "ns_per_update_mean": (
            statistics.mean(wall_samples) * 1e9 / calls
        ),
        "python_traced_peak_bytes": int(peak_bytes),
        "wall_samples_seconds": wall_samples,
    }


def _arrays_equal(left_learner, right_learner):
    for name in ("pre_trace", "post_trace", "eligibility"):
        np.testing.assert_array_equal(
            getattr(left_learner, name), getattr(right_learner, name)
        )


def run(args):
    numpy_projection = _projection(
        args.pre, args.post, args.density, args.seed
    )
    cython_projection = SparseProjection(
        numpy_projection.n_pre,
        numpy_projection.n_post,
        numpy_projection.pre.copy(),
        numpy_projection.post.copy(),
        numpy_projection.weights.copy(),
        numpy_projection.source_sign.copy(),
    )
    pre_spikes, post_spikes = _make_spikes(
        args.pre, args.post, args.steps, args.seed + 1
    )
    numpy_backend = NumpyBackend()
    cython_backend = CythonBackend()
    numpy_learner = RewardSTDP()
    cython_learner = RewardSTDP()

    _run_mark(
        numpy_backend, numpy_projection, numpy_learner,
        pre_spikes[: min(args.warmup, args.steps)],
        post_spikes[: min(args.warmup, args.steps)],
    )
    _run_mark(
        cython_backend, cython_projection, cython_learner,
        pre_spikes[: min(args.warmup, args.steps)],
        post_spikes[: min(args.warmup, args.steps)],
    )
    _arrays_equal(numpy_learner, cython_learner)

    numpy_projection = _projection(
        args.pre, args.post, args.density, args.seed
    )
    cython_projection = SparseProjection(
        numpy_projection.n_pre,
        numpy_projection.n_post,
        numpy_projection.pre.copy(),
        numpy_projection.post.copy(),
        numpy_projection.weights.copy(),
        numpy_projection.source_sign.copy(),
    )
    numpy_learner = RewardSTDP()
    cython_learner = RewardSTDP()
    numpy_result = _measure(
        numpy_backend, numpy_projection, numpy_learner,
        pre_spikes, post_spikes, args.repeats,
    )
    cython_result = _measure(
        cython_backend, cython_projection, cython_learner,
        pre_spikes, post_spikes, args.repeats,
    )
    numpy_reward = _measure_reward(
        numpy_backend, numpy_projection, numpy_learner,
        args.repeats, args.reward_calls,
    )
    cython_reward = _measure_reward(
        cython_backend, cython_projection, cython_learner,
        args.repeats, args.reward_calls,
    )
    np.testing.assert_array_equal(
        cython_projection.weights, numpy_projection.weights
    )

    # Final exact state check across the complete benchmark input sequence.
    _run_mark(numpy_backend, numpy_projection, numpy_learner,
              pre_spikes, post_spikes)
    _run_mark(cython_backend, cython_projection, cython_learner,
              pre_spikes, post_spikes)
    _arrays_equal(numpy_learner, cython_learner)

    process = psutil.Process()
    result = {
        "benchmark": "cython_stdp_mark",
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "cython": __import__("Cython").__version__,
            "rss_bytes_after": process.memory_info().rss,
        },
        "workload": {
            "pre_neurons": args.pre,
            "post_neurons": args.post,
            "edges": int(len(numpy_projection.weights)),
            "density": args.density,
            "updates_per_sample": args.steps,
            "warmup_updates": min(args.warmup, args.steps),
            "repeats": args.repeats,
            "seed": args.seed,
            "input_arrays_bytes": int(pre_spikes.nbytes + post_spikes.nbytes),
            "trace_arrays_bytes": int(
                numpy_learner.pre_trace.nbytes
                + numpy_learner.post_trace.nbytes
                + numpy_learner.eligibility.nbytes
                + numpy_learner._pre_spike_float.nbytes
                + numpy_learner._post_spike_float.nbytes
            ),
        },
        "kernels": {
            "update_stdp": {
                "numpy": numpy_result,
                "cython": cython_result,
                "speedup_wall_mean": (
                    numpy_result["wall_seconds_mean"]
                    / cython_result["wall_seconds_mean"]
                ),
            },
            "apply_reward": {
                "numpy": numpy_reward,
                "cython": cython_reward,
                "speedup_wall_mean": (
                    numpy_reward["wall_seconds_mean"]
                    / cython_reward["wall_seconds_mean"]
                ),
            },
        },
        "exact_equivalence": True,
        "notes": [
            "Memory is Python tracemalloc peak for the update loop; native RSS is process-wide.",
            "LIF and CSR remain NumPy; both STDP marking and reward application are measured.",
        ],
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre", type=int, default=712)
    parser.add_argument("--post", type=int, default=304)
    parser.add_argument("--density", type=float, default=0.08)
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--reward-calls", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run(args)
    serialized = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()

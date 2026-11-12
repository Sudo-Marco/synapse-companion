from __future__ import annotations

"""Compare the original RewardSTDP.mark equations with the production method."""

import argparse
import gc
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synapse_pet.core.network import SpikingNetwork
from synapse_pet.core.plasticity import RewardSTDP


SEED = 20261102
DT_S = 0.002


def _legacy_mark(learner: RewardSTDP, projection, pre_spikes: np.ndarray,
                 post_spikes: np.ndarray, dt_s: float) -> None:
    """Reference implementation as measured before the scratch-buffer change."""
    if learner.eligibility is None or len(learner.eligibility) != len(projection.weights):
        learner.initialize(projection)
    assert learner.pre_trace is not None
    assert learner.post_trace is not None
    assert learner.eligibility is not None
    decay = np.float32(np.exp(-dt_s / learner.eligibility_tau_s))
    learner.pre_trace *= decay
    learner.post_trace *= decay
    pre = pre_spikes.astype(np.float32)
    post = post_spikes.astype(np.float32)
    learner.eligibility *= decay
    learner.eligibility += (
        learner.a_plus * learner.pre_trace[projection.pre] * post[projection.post])
    learner.eligibility -= (
        learner.a_minus * learner.post_trace[projection.post] * pre[projection.pre])
    learner.pre_trace += pre
    learner.post_trace += post


def _stats(values: list[float]) -> dict[str, float]:
    values_array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(values_array)),
        "stddev": float(np.std(values_array)),
        "p50": float(np.percentile(values_array, 50)),
        "p95": float(np.percentile(values_array, 95)),
        "p99": float(np.percentile(values_array, 99)),
    }


def run(samples: int, iterations: int) -> dict[str, object]:
    network = SpikingNetwork(600, connectivity=0.10, dt_ms=2.0,
                             seed=SEED, noise=0.015)
    projections = (network.sensor_to_hidden, network.recurrent,
                   network.hidden_to_output)
    rng = np.random.default_rng(SEED + 1)
    spike_pairs = [
        (rng.random(projection.n_pre) < 0.04,
         rng.random(projection.n_post) < 0.03)
        for projection in projections
    ]
    learners = {
        name: [RewardSTDP() for _ in projections]
        for name in ("legacy_astype", "production_mark")
    }
    for index, projection in enumerate(projections):
        for group in learners.values():
            group[index].initialize(projection)

    def make_call(name: str):
        def call() -> None:
            for index, (projection, (pre_spikes, post_spikes)) in enumerate(
                    zip(projections, spike_pairs)):
                learner = learners[name][index]
                if name == "legacy_astype":
                    _legacy_mark(learner, projection, pre_spikes, post_spikes, DT_S)
                else:
                    learner.mark(projection, pre_spikes, post_spikes, DT_S)
        return call

    calls = {name: make_call(name) for name in learners}
    for _ in range(200):
        calls["legacy_astype"]()
        calls["production_mark"]()

    samples_by_name = {
        name: {"wall_ms": [], "thread_cpu_ms": []}
        for name in learners
    }
    was_gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for sample in range(samples):
            order = list(calls.items())
            if sample % 2:
                order.reverse()
            for name, call in order:
                cpu_start = time.thread_time_ns()
                wall_start = time.perf_counter_ns()
                for _ in range(iterations):
                    call()
                samples_by_name[name]["wall_ms"].append(
                    (time.perf_counter_ns() - wall_start) / 1e6 / iterations)
                samples_by_name[name]["thread_cpu_ms"].append(
                    (time.thread_time_ns() - cpu_start) / 1e6 / iterations)
    finally:
        if was_gc_enabled:
            gc.enable()

    reference, production = learners["legacy_astype"], learners["production_mark"]
    exact = all(
        np.array_equal(left.pre_trace, right.pre_trace)
        and np.array_equal(left.post_trace, right.post_trace)
        and np.array_equal(left.eligibility, right.eligibility)
        for left, right in zip(reference, production)
    )
    return {
        "schema": 1,
        "measurement_kind": "phase2_stdp_mark_same_process_comparison",
        "timestamp_local": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "python": sys.version,
        "numpy": np.__version__,
        "seed": SEED,
        "configuration": {
            "requested_neurons": 600,
            "connectivity": 0.10,
            "dt_s": DT_S,
            "projections": {
                projection.name: len(projection.weights)
                for projection in projections
            },
            "warmup_calls_per_variant": 200,
            "samples": samples,
            "iterations_per_sample": iterations,
        },
        "exact_equivalence": exact,
        "variants": {
            name: {
                "wall_ms": _stats(values["wall_ms"]),
                "thread_cpu_ms": _stats(values["thread_cpu_ms"]),
            }
            for name, values in samples_by_name.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/phase2_stdp_comparison.json")
    args = parser.parse_args()
    if args.samples < 10 or args.iterations < 10:
        parser.error("--samples and --iterations must both be at least 10")
    result = run(args.samples, args.iterations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "exact_equivalence": result["exact_equivalence"],
                      "variants": result["variants"]}, indent=2))


if __name__ == "__main__":
    main()

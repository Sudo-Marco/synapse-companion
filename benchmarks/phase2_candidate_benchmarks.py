from __future__ import annotations

"""Compare Python alternatives for action-credit masks and sparse propagation."""

import argparse
import copy
import gc
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synapse_pet.core.network import SpikingNetwork
from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.core.synapses import SparseProjection


SEED = 20261102


def _summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {"mean": float(np.mean(array)), "stddev": float(np.std(array)),
            "p50": float(np.percentile(array, 50)),
            "p95": float(np.percentile(array, 95)),
            "p99": float(np.percentile(array, 99))}


def _measure(function, samples: int, iterations: int) -> dict[str, object]:
    for _ in range(20):
        function()
    wall, cpu = [], []
    was_gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(samples):
            cpu_start = time.thread_time_ns()
            wall_start = time.perf_counter_ns()
            for _ in range(iterations):
                function()
            wall.append((time.perf_counter_ns() - wall_start) / 1e6 / iterations)
            cpu.append((time.thread_time_ns() - cpu_start) / 1e6 / iterations)
    finally:
        if was_gc_enabled:
            gc.enable()
    return {"wall_ms": _summary(wall), "thread_cpu_ms": _summary(cpu),
            "samples": samples, "iterations_per_sample": iterations}


def _action_credit_variant(projection: SparseProjection,
                           learner: RewardSTDP,
                           post_indices: np.ndarray,
                           pre_activity: np.ndarray,
                           dopamine: float,
                           learning_rate: float,
                           mask_method: str) -> None:
    if dopamine == 0.0 or len(pre_activity) != projection.n_pre or not len(post_indices):
        return
    if mask_method == "isin":
        post_mask = np.isin(projection.post, post_indices, assume_unique=False)
    elif mask_method == "lookup":
        selected = np.zeros(projection.n_post, dtype=np.bool_)
        selected[post_indices] = True
        post_mask = selected[projection.post]
    elif mask_method == "sorted_runs":
        post_mask = np.zeros(len(projection.post), dtype=np.bool_)
        starts = np.searchsorted(projection.post, post_indices, side="left")
        ends = np.searchsorted(projection.post, post_indices, side="right")
        for start, end in zip(starts, ends):
            post_mask[start:end] = True
    else:
        raise ValueError(mask_method)
    if not np.any(post_mask):
        return
    active_pre = np.clip(pre_activity[projection.pre], 0.0, 1.0)
    delta = (float(learning_rate) * float(dopamine)
             * active_pre * post_mask.astype(np.float32))
    projection.weights += delta.astype(np.float32)
    projection.weights[:] = np.clip(projection.weights, -1.0, 1.0)
    projection.enforce_dale()


def run(samples: int, iterations: int) -> dict[str, object]:
    network = SpikingNetwork(600, connectivity=0.10, dt_ms=2.0,
                             seed=SEED, noise=0.015)
    network.add_tool_group("phase2_benchmark")
    projection = network.hidden_to_output
    post_indices = (network.output_groups["tool:phase2_benchmark"]
                    - network.output_start).astype(np.int32)
    pre_rng = np.random.default_rng(SEED + 1)
    pre_activity = pre_rng.random(projection.n_pre, dtype=np.float32)
    mask_expected = np.isin(projection.post, post_indices, assume_unique=False)
    masks = {
        method: (np.isin(projection.post, post_indices, assume_unique=False)
                 if method == "isin"
                 else (lambda selected: selected[projection.post])(
                     np.isin(np.arange(projection.n_post), post_indices)))
        for method in ("isin", "lookup")
    }
    sorted_mask = np.zeros(len(projection.post), dtype=np.bool_)
    starts = np.searchsorted(projection.post, post_indices, side="left")
    ends = np.searchsorted(projection.post, post_indices, side="right")
    for start, end in zip(starts, ends):
        sorted_mask[start:end] = True
    masks["sorted_runs"] = sorted_mask
    if not np.all(np.diff(projection.post) >= 0):
        raise AssertionError("the CSR projection posts must be sorted for sorted_runs")

    action_credit = {}
    post_mask_exact = {}
    weight_exact = {}
    variants = ("isin", "lookup", "sorted_runs", "production")
    for method in variants:
        candidate_projection = copy.deepcopy(projection)
        candidate_learner = RewardSTDP()
        candidate_learner.initialize(candidate_projection)
        if method == "production":
            def production_credit(p=candidate_projection, l=candidate_learner):
                l.apply_action_credit(p, 0.25, post_indices, pre_activity, 0.10)
            action_credit[method] = _measure(production_credit, samples, iterations)
            production_mask = np.isin(
                projection.post, post_indices, assume_unique=False)
            post_mask_exact[method] = bool(
                np.array_equal(mask_expected, production_mask))
        else:
            action_credit[method] = _measure(
                lambda m=method, p=candidate_projection, l=candidate_learner:
                    _action_credit_variant(p, l, post_indices, pre_activity,
                                           0.25, 0.10, m),
                samples, iterations)
            post_mask_exact[method] = bool(np.array_equal(
                mask_expected, masks[method]))
    # Validate full weight results by replaying a fixed number of updates.
    reference_projection = copy.deepcopy(projection)
    reference_learner = RewardSTDP()
    reference_learner.initialize(reference_projection)
    for _ in range(50):
        _action_credit_variant(reference_projection, reference_learner,
                               post_indices, pre_activity, 0.25, 0.10, "isin")
    for method in variants:
        candidate_projection = copy.deepcopy(projection)
        candidate_learner = RewardSTDP()
        candidate_learner.initialize(candidate_projection)
        for _ in range(50):
            if method == "production":
                candidate_learner.apply_action_credit(
                    candidate_projection, 0.25, post_indices, pre_activity, 0.10)
            else:
                _action_credit_variant(candidate_projection, candidate_learner,
                                       post_indices, pre_activity, 0.25, 0.10, method)
        weight_exact[method] = bool(np.array_equal(
            reference_projection.weights, candidate_projection.weights))

    propagation = {}
    propagation_equivalence = {}
    for projection in (network.sensor_to_hidden, network.recurrent,
                       network.hidden_to_output):
        for rate in (0.01, 0.05, 0.20):
            rng = np.random.default_rng(SEED + int(rate * 1000)
                                        + len(propagation))
            spikes = rng.random(projection.n_pre) < rate
            key = f"{projection.name}_spike_rate_{rate:.2f}"

            def scipy_csr(p=projection, s=spikes):
                return p.currents(s)

            def bincount(p=projection, s=spikes):
                return np.bincount(
                    p.post, weights=p.weights * s[p.pre],
                    minlength=p.n_post).astype(np.float32)

            expected = scipy_csr()
            candidate = bincount()
            propagation_equivalence[key] = {
                "array_equal": bool(np.array_equal(expected, candidate)),
                "allclose_1e-6": bool(np.allclose(expected, candidate,
                                                  rtol=1e-6, atol=1e-7)),
                "max_abs_difference": float(np.max(
                    np.abs(expected - candidate), initial=0.0)),
            }
            propagation[key] = {
                "scipy_csr": _measure(scipy_csr, samples, iterations),
                "numpy_bincount": _measure(bincount, samples, iterations),
            }

    return {
        "schema": 1,
        "measurement_kind": "phase2_action_credit_and_csr_alternatives",
        "timestamp_local": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "seed": SEED,
        "configuration": {
            "requested_neurons": 600,
            "tool_group_size": network.tool_group_size,
            "hidden_to_output_edges": len(network.hidden_to_output.weights),
            "selected_output_count": len(post_indices),
            "samples": samples,
            "iterations_per_sample": iterations,
        },
        "action_credit": {
            "mask_methods": action_credit,
            "mask_exact_against_isin": post_mask_exact,
            "weights_exact_after_50_updates": weight_exact,
        },
        "propagation": propagation,
        "propagation_equivalence": propagation_equivalence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/phase2_candidates.json")
    args = parser.parse_args()
    if args.samples < 10 or args.iterations < 10:
        parser.error("--samples and --iterations must both be at least 10")
    result = run(args.samples, args.iterations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "action_credit": result["action_credit"],
                      "propagation_equivalence": result["propagation_equivalence"]}, indent=2))


if __name__ == "__main__":
    main()

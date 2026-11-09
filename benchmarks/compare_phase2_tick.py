from __future__ import annotations

"""Same-process A/B of the Phase 2 Python hot-path changes."""

import argparse
import gc
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
from types import MethodType

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synapse_pet.core.network import SpikingNetwork
from synapse_pet.runtime.engine import PetEngine


SEED = 20261102
CONTEXT = {"input_rate": 0.72, "window_category": "editor",
           "activity": 0.35, "hour": 0.62}


def _legacy_mark(learner, projection, pre_spikes, post_spikes, dt_s):
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


def _legacy_network_step(network: SpikingNetwork, sensor_current=None):
    n = network.population.size
    current = np.zeros(n, dtype=np.float32)
    if sensor_current is not None:
        if len(sensor_current) != network.n_sensor:
            raise ValueError("sensor_current length does not match sensory population")
        current[:network.n_sensor] += sensor_current
    spikes = network.population.spikes
    h = slice(network.hidden_start, network.output_start)
    current[h] += (network.sensor_to_hidden.currents(spikes[:network.n_sensor])
                   * np.float32(network.synaptic_gain))
    current[h] += (network.recurrent.currents(spikes[h])
                   * np.float32(network.synaptic_gain))
    output_current = network.hidden_to_output.currents(spikes[h]) * np.float32(
        network.synaptic_gain)
    if (network.tool_output_inhibition_enabled
            and network.tick_count % max(1, int(
                network.tool_output_inhibition_interval_steps)) == 0):
        network._apply_tool_output_inhibition(output_current)
    current[network.output_start:
            network.output_start + network.hidden_to_output.n_post] += output_current
    out = network.population.step(
        current, network.dt_ms, network.rng, network.noise,
        gain=1.0 + 0.5 * getattr(network, "stress", 0.0))
    network.tick_count += 1
    return out


def _state_digest(engine: PetEngine) -> str:
    digest = hashlib.sha256()
    arrays = [
        engine.network.population.voltage,
        engine.network.population.threshold_offset,
        engine.network.population.refractory,
        engine.network.population.spikes,
        engine.network.sensor_to_hidden.weights,
        engine.network.recurrent.weights,
        engine.network.hidden_to_output.weights,
    ]
    for learner in engine.learners.values():
        arrays.extend((learner.pre_trace, learner.post_trace, learner.eligibility))
    for array in arrays:
        if array is not None:
            digest.update(np.ascontiguousarray(array).tobytes())
    digest.update(json.dumps(engine.network.rng.bit_generator.state,
                             sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def _attach_legacy_paths(engine: PetEngine) -> None:
    engine.network.step = MethodType(_legacy_network_step, engine.network)
    for learner in engine.learners.values():
        learner.mark = MethodType(_legacy_mark, learner)


def _summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {"mean": float(np.mean(array)), "stddev": float(np.std(array)),
            "p50": float(np.percentile(array, 50)),
            "p95": float(np.percentile(array, 95)),
            "p99": float(np.percentile(array, 99))}


def _compare_size(requested_neurons: int, samples: int,
                  ticks_per_sample: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="synapse_phase2_ab_") as tmp:
        root = Path(tmp)
        legacy = PetEngine(seed=SEED, neurons=requested_neurons,
                           data_dir=root / "legacy")
        production = PetEngine(seed=SEED, neurons=requested_neurons,
                               data_dir=root / "production")
        _attach_legacy_paths(legacy)
        # Warm up while comparing exact outputs and state after every active tick.
        for _ in range(40):
            old_out = legacy.tick(CONTEXT, 50.0, active=True)
            new_out = production.tick(CONTEXT, 50.0, active=True)
            if old_out != new_out or _state_digest(legacy) != _state_digest(production):
                raise AssertionError("reference and production state diverged during warmup")
        for _ in range(20):
            old_out = legacy.tick({}, 250.0, active=False)
            new_out = production.tick({}, 250.0, active=False)
            if old_out != new_out or _state_digest(legacy) != _state_digest(production):
                raise AssertionError("reference and production state diverged during rest warmup")

        timings = {
            regime: {
                "legacy_reference": {"wall_ms": [], "thread_cpu_ms": []},
                "production": {"wall_ms": [], "thread_cpu_ms": []},
            }
            for regime in ("active", "rest")
        }
        was_gc_enabled = gc.isenabled()
        gc.disable()
        try:
            for sample in range(samples):
                order = [
                    ("active", "legacy_reference", legacy, CONTEXT, 50.0, True),
                    ("active", "production", production, CONTEXT, 50.0, True),
                    ("rest", "legacy_reference", legacy, {}, 250.0, False),
                    ("rest", "production", production, {}, 250.0, False),
                ]
                if sample % 2:
                    order = tuple(reversed(order))
                for regime, name, engine, context, duration_ms, active in order:
                    cpu_start = time.thread_time_ns()
                    wall_start = time.perf_counter_ns()
                    for _ in range(ticks_per_sample):
                        engine.tick(context, duration_ms, active=active)
                    timings[regime][name]["wall_ms"].append(
                        (time.perf_counter_ns() - wall_start) / 1e6 / ticks_per_sample)
                    timings[regime][name]["thread_cpu_ms"].append(
                        (time.thread_time_ns() - cpu_start) / 1e6 / ticks_per_sample)
                if _state_digest(legacy) != _state_digest(production):
                    raise AssertionError("reference and production state diverged after sample")
        finally:
            if was_gc_enabled:
                gc.enable()
            legacy.stop()
            production.stop()

        final_state_sha256 = _state_digest(production)
        result = {
            "requested_neurons": requested_neurons,
            "actual_neurons_with_tools": production.network.population.size,
            "connections": int(sum(len(p.weights) for p in (
                production.network.sensor_to_hidden,
                production.network.recurrent,
                production.network.hidden_to_output))),
            "exact_state_equivalence": True,
            "final_state_sha256": final_state_sha256,
            "timings": {
                regime: {
                    name: {
                        "wall_ms": _summary(values["wall_ms"]),
                        "thread_cpu_ms": _summary(values["thread_cpu_ms"]),
                    }
                    for name, values in regimes.items()
                }
                for regime, regimes in timings.items()
            },
        }
        del old_out, new_out, order, engine, legacy, production
        gc.collect()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neurons", type=int, nargs="+", default=[600, 1000])
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--ticks-per-sample", type=int, default=10)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/phase2_tick_ab.json")
    args = parser.parse_args()
    if args.samples < 10 or args.ticks_per_sample < 2:
        parser.error("--samples must be >=10 and --ticks-per-sample >=2")
    result = {
        "schema": 1,
        "measurement_kind": "phase2_same_process_full_tick_ab",
        "timestamp_local": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "cpu": platform.processor() or psutil.cpu_freq().current,
        "seed": SEED,
        "simulated_context": CONTEXT,
        "configuration": {
            "samples": args.samples,
            "ticks_per_sample": args.ticks_per_sample,
            "warmup_ticks": 40,
            "order": "alternating per sample to reduce clock/load bias",
        },
        "sizes": [_compare_size(size, args.samples, args.ticks_per_sample)
                  for size in args.neurons],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "sizes": result["sizes"]}, indent=2))


if __name__ == "__main__":
    main()

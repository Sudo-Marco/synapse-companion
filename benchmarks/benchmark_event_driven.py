#!/usr/bin/env python3
"""Compare fixed-step and experimental quiet-block fast-forward costs."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

import numpy as np

from synapse_pet.core.homeostasis import Homeostasis
from synapse_pet.core.network import SpikingNetwork
from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.runtime.event_driven import try_fast_forward_quiet


def make_state(total_neurons: int, seed: int):
    network = SpikingNetwork(total_neurons, connectivity=0.10, seed=seed,
                             noise=0.0)
    network.population.voltage.fill(0.2)
    network.population.threshold_offset.fill(0.1)
    network.population.refractory.fill(0.0)
    network.population.spikes.fill(False)
    learners = {
        "sensor_hidden": RewardSTDP(),
        "recurrent": RewardSTDP(),
        "hidden_output": RewardSTDP(),
    }
    projections = (network.sensor_to_hidden, network.recurrent,
                   network.hidden_to_output)
    for learner, projection in zip(learners.values(), projections):
        learner.initialize(projection)
        learner.pre_trace.fill(0.05)
        learner.post_trace.fill(0.05)
        learner.eligibility.fill(0.005)
    homeostasis = Homeostasis(window_s=1000.0)
    return network, learners, homeostasis, projections


def fixed_block(state, steps: int, collect_spikes: bool = False) -> bytes:
    network, learners, homeostasis, projections = state
    dt_s = network.dt_ms / 1000.0
    h = slice(network.hidden_start, network.output_start)
    out = slice(network.output_start,
                network.output_start + network.hidden_to_output.n_post)
    stimulus = np.zeros(network.n_sensor, dtype=np.float32)
    sequence = bytearray() if collect_spikes else None
    for _ in range(steps):
        spikes = network.step(stimulus)
        if sequence is not None:
            sequence.extend(spikes.tobytes())
        learners["sensor_hidden"].mark(
            network.sensor_to_hidden, spikes[:network.n_sensor], spikes[h], dt_s)
        learners["recurrent"].mark(
            network.recurrent, spikes[h], spikes[h], dt_s)
        learners["hidden_output"].mark(
            network.hidden_to_output, spikes[h], spikes[out], dt_s)
        homeostasis.update(network.population, spikes, dt_s, projections)
    return bytes(sequence) if sequence is not None else b""


def measure(total_neurons: int, steps: int, repeats: int, blocks: int,
            use_event_driven: bool) -> dict[str, object]:
    samples = []
    skipped_blocks = 0
    for repeat in range(repeats):
        state = make_state(total_neurons, 20261120 + repeat)
        network = state[0]
        stimulus = np.zeros(network.n_sensor, dtype=np.float32)
        started = time.perf_counter()
        for _ in range(blocks):
            if (use_event_driven
                    and try_fast_forward_quiet(
                        network, state[1], state[2], steps, stimulus)):
                skipped_blocks += 1
            else:
                fixed_block(state, steps)
        samples.append((time.perf_counter() - started) * 1000.0
                       / (blocks * steps))
    return {
        "mean_ms_per_neural_step": statistics.mean(samples),
        "median_ms_per_neural_step": statistics.median(samples),
        "samples_ms_per_neural_step": samples,
        "skipped_blocks": skipped_blocks,
        "total_blocks": repeats * blocks,
    }


def run(total_neurons: int, steps: int, repeats: int, blocks: int):
    fixed = measure(total_neurons, steps, repeats, blocks, False)
    event = measure(total_neurons, steps, repeats, blocks, True)
    reference_state = make_state(total_neurons, 20261120)
    event_state = make_state(total_neurons, 20261120)
    stimulus = np.zeros(reference_state[0].n_sensor, dtype=np.float32)
    for _ in range(blocks):
        fixed_block(reference_state, steps)
        assert try_fast_forward_quiet(
            event_state[0], event_state[1], event_state[2], steps, stimulus)
    np.testing.assert_array_equal(reference_state[0].population.spikes,
                                  event_state[0].population.spikes)
    np.testing.assert_allclose(reference_state[0].population.voltage,
                               event_state[0].population.voltage,
                               rtol=2e-6, atol=2e-7)
    return {
        "neurons": total_neurons,
        "steps_per_block": steps,
        "repeats": repeats,
        "blocks_per_repeat": blocks,
        "fixed_step": fixed,
        "event_driven_quiet": event,
        "speedup": (fixed["mean_ms_per_neural_step"]
                    / event["mean_ms_per_neural_step"]),
        "spike_equivalence": "exact",
        "scope": "isolated noise-free network; no PetEngine, UI, or live sensors",
    }


def run_injected_activity(total_neurons: int, spike_fraction: float,
                          steps: int, repeats: int, blocks: int):
    def measure_path(use_event_driven: bool):
        samples = []
        skipped = 0
        output_hashes = []
        for repeat in range(repeats):
            state = make_state(total_neurons, 20261130 + repeat)
            network, learners, homeostasis, _ = state
            stimulus = np.zeros(network.n_sensor, dtype=np.float32)
            injected = min(network.population.size, int(round(
                network.population.size * spike_fraction)))
            sequence = bytearray()
            started = time.perf_counter()
            for _ in range(blocks):
                network.population.spikes.fill(False)
                network.population.spikes[:injected] = True
                used = (use_event_driven and try_fast_forward_quiet(
                    network, learners, homeostasis, steps, stimulus))
                skipped += int(bool(used))
                if not used:
                    sequence.extend(fixed_block(state, steps, collect_spikes=True))
            samples.append((time.perf_counter() - started) * 1000.0
                           / (blocks * steps))
            output_hashes.append(hashlib.sha256(sequence).hexdigest())
        return {
            "mean_ms_per_neural_step": statistics.mean(samples),
            "median_ms_per_neural_step": statistics.median(samples),
            "samples_ms_per_neural_step": samples,
            "skipped_blocks": skipped,
            "total_blocks": repeats * blocks,
            "output_hashes": output_hashes,
        }

    fixed = measure_path(False)
    event = measure_path(True)
    if fixed["output_hashes"] != event["output_hashes"]:
        raise AssertionError("fixed-step and event fallback outputs differ")
    return {
        "neurons": total_neurons,
        "injected_spike_fraction": spike_fraction,
        "steps_per_block": steps,
        "fixed_step": fixed,
        "event_mode_with_fallback": event,
        "guarded_fallback_overhead_ratio": (
            event["mean_ms_per_neural_step"]
            / fixed["mean_ms_per_neural_step"]),
        "output_hashes_match": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--neurons", nargs="+", type=int, default=[600, 1000])
    parser.add_argument("--steps", type=int, default=25)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--blocks", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = {
        "benchmark": "event_driven_quiet_block_prototype",
        "parameters": {"steps": args.steps, "repeats": args.repeats,
                       "blocks": args.blocks},
        "quiet_cases": [run(size, args.steps, args.repeats, args.blocks)
                        for size in args.neurons],
        "injected_activity_cases": [
            run_injected_activity(size, rate, args.steps,
                                  args.repeats, args.blocks)
            for size in args.neurons
            for rate in (0.01, 0.05, 0.15, 0.30)
        ],
        "notes": [
            "The experimental path only skips a block when its preconditions prove the block is silent.",
            "Fixed-step remains the reference; noise, sensory input, pending spikes, refractory cells, or a homeostasis boundary force fallback.",
            "The measured event mode is a prototype, not a desktop runtime performance claim.",
        ],
    }
    output = json.dumps(results, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()

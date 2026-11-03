from __future__ import annotations

import hashlib

import numpy as np

from ..core.encoding import PopulationEncoder
from ..core.network import SpikingNetwork
from ..core.plasticity import RewardSTDP


SEED = 20261102
STEPS = 4096


def reference_snapshot() -> dict[str, object]:
    """Run a fixed input/reward trace and summarize the resulting SNN state."""
    network = SpikingNetwork(600, connectivity=0.10, dt_ms=2.0,
                             seed=SEED, noise=0.015)
    encoder = PopulationEncoder(
        {"input_rate": 24, "window_category": 24, "activity": 24, "hour": 24},
        seed=SEED,
    )
    projections = (network.sensor_to_hidden, network.recurrent,
                   network.hidden_to_output)
    learners = [RewardSTDP() for _ in projections]
    for learner, projection in zip(learners, projections):
        learner.initialize(projection)

    spike_digest = hashlib.sha256()
    state_digest = hashlib.sha256()
    total_spikes = np.zeros(3, dtype=np.int64)
    samples: dict[str, list[int]] = {}
    sample_steps = {0, 1, 2, 127, 511, 1023, 2047, 4095}
    input_current = np.empty(network.n_sensor, dtype=np.float32)

    for step in range(STEPS):
        phase = step // 1024
        context = {
            "input_rate": (0.15, 0.85, 0.35, 0.65)[phase],
            "window_category": ("editor", "browser", "terminal", "editor")[phase],
            "activity": (0.2, 0.7, 0.1, 0.45)[phase],
            "hour": 0.625,
        }
        encoded = encoder.encode(context, network.dt_ms)
        np.multiply(encoded, np.float32(1.5), out=input_current,
                    casting="unsafe")
        spikes = network.step(input_current)
        hidden = slice(network.hidden_start, network.output_start)
        outputs = slice(network.output_start,
                        network.output_start + network.hidden_to_output.n_post)
        groups = (spikes[:network.n_sensor], spikes[hidden], spikes[outputs])
        for index, values in enumerate(groups):
            total_spikes[index] += int(values.sum())
        spike_digest.update(np.packbits(spikes).tobytes())
        if step in sample_steps:
            samples[str(step)] = np.flatnonzero(spikes).astype(int).tolist()

        learners[0].mark(network.sensor_to_hidden, spikes[:network.n_sensor],
                         spikes[hidden], network.dt_ms / 1000.0)
        learners[1].mark(network.recurrent, spikes[hidden], spikes[hidden],
                         network.dt_ms / 1000.0)
        learners[2].mark(network.hidden_to_output, spikes[hidden], spikes[outputs],
                         network.dt_ms / 1000.0)
        if step % 128 == 127:
            reward = 0.4 if (step // 128) % 2 == 0 else -0.2
            for learner, projection in zip(learners, projections):
                learner.apply_reward(projection, reward)

    for values in (network.population.voltage,
                   network.population.threshold_offset,
                   network.population.refractory,
                   network.sensor_to_hidden.weights,
                   network.recurrent.weights,
                   network.hidden_to_output.weights):
        state_digest.update(np.asarray(values).tobytes())

    return {
        "seed": SEED,
        "steps": STEPS,
        "spike_sha256": spike_digest.hexdigest(),
        "state_sha256": state_digest.hexdigest(),
        "spike_counts_by_population": {
            "sensor": int(total_spikes[0]),
            "hidden": int(total_spikes[1]),
            "output": int(total_spikes[2]),
        },
        "spike_samples": samples,
        "weights": {
            "sensor_hidden": int(len(network.sensor_to_hidden.weights)),
            "recurrent": int(len(network.recurrent.weights)),
            "hidden_output": int(len(network.hidden_to_output.weights)),
        },
    }

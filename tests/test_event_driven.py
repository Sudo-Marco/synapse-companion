from __future__ import annotations

import copy
import numpy as np
import pytest

from synapse_pet.core.homeostasis import Homeostasis
from synapse_pet.core.network import SpikingNetwork
from synapse_pet.core.plasticity import RewardSTDP
from synapse_pet.runtime.event_driven import try_fast_forward_quiet


def _state(seed: int = 901):
    network = SpikingNetwork(600, connectivity=0.05, seed=seed, noise=0.0)
    rng = np.random.default_rng(seed + 1)
    network.population.voltage[:] = rng.uniform(-0.05, 0.20,
                                                network.population.size)
    network.population.threshold_offset[:] = rng.uniform(
        0.0, 0.2, network.population.size)
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
        learner.pre_trace[:] = rng.uniform(0.0, 0.1, learner.pre_trace.size)
        learner.post_trace[:] = rng.uniform(0.0, 0.1, learner.post_trace.size)
        learner.eligibility[:] = rng.uniform(
            0.0, 0.01, learner.eligibility.size)
    homeostasis = Homeostasis(_count=7.0, _elapsed=0.25)
    return network, learners, homeostasis, projections


def _fixed_quiet_steps(network, learners, homeostasis, projections, steps):
    dt_s = network.dt_ms / 1000.0
    h = slice(network.hidden_start, network.output_start)
    out = slice(network.output_start,
                network.output_start + network.hidden_to_output.n_post)
    stimulus = np.zeros(network.n_sensor, dtype=np.float32)
    for _ in range(steps):
        spikes = network.step(stimulus)
        learners["sensor_hidden"].mark(
            network.sensor_to_hidden, spikes[:network.n_sensor], spikes[h], dt_s)
        learners["recurrent"].mark(
            network.recurrent, spikes[h], spikes[h], dt_s)
        learners["hidden_output"].mark(
            network.hidden_to_output, spikes[h], spikes[out], dt_s)
        homeostasis.update(network.population, spikes, dt_s, projections)


def test_quiet_fast_forward_preserves_spikes_and_state_within_float_tolerance():
    fixed, fixed_learners, fixed_homeostasis, fixed_projections = _state()
    event, event_learners, event_homeostasis, event_projections = _state()
    steps = 25

    _fixed_quiet_steps(fixed, fixed_learners, fixed_homeostasis,
                       fixed_projections, steps)
    assert try_fast_forward_quiet(
        event, event_learners, event_homeostasis, steps,
        np.zeros(event.n_sensor, dtype=np.float32))

    assert event.tick_count == fixed.tick_count == steps
    np.testing.assert_array_equal(event.population.spikes,
                                  fixed.population.spikes)
    np.testing.assert_allclose(event.population.voltage,
                               fixed.population.voltage, rtol=2e-6, atol=2e-7)
    np.testing.assert_allclose(event.population.threshold_offset,
                               fixed.population.threshold_offset,
                               rtol=2e-6, atol=2e-7)
    assert event_homeostasis._elapsed == fixed_homeostasis._elapsed
    assert event_homeostasis._count == fixed_homeostasis._count
    for name in fixed_learners:
        for field in ("pre_trace", "post_trace", "eligibility"):
            np.testing.assert_allclose(
                getattr(event_learners[name], field),
                getattr(fixed_learners[name], field), rtol=2e-6, atol=2e-8)

    # The small accumulated float32 decay difference does not change the next
    # deliberately strong sensory event or the resulting spike vector.
    drive = np.full(event.n_sensor, 1.5, dtype=np.float32)
    np.testing.assert_array_equal(fixed.step(drive), event.step(drive))


@pytest.mark.parametrize("unsafe", [
    "stochastic_noise", "sensory_current", "pending_spike",
    "refractory_cell", "homeostasis_boundary", "sensor_shape",
])
def test_unsafe_interval_falls_back_without_mutating_state(unsafe):
    network, learners, homeostasis, _ = _state()
    stimulus = np.zeros(network.n_sensor, dtype=np.float32)
    if unsafe == "stochastic_noise":
        network.noise = 0.015
    elif unsafe == "sensory_current":
        stimulus[0] = 0.1
    elif unsafe == "pending_spike":
        network.population.spikes[0] = True
    elif unsafe == "refractory_cell":
        network.population.refractory[0] = network.dt_ms
    elif unsafe == "sensor_shape":
        stimulus = np.zeros(network.n_sensor + 1, dtype=np.float32)
    else:
        homeostasis._elapsed = homeostasis.window_s - 0.01

    before_voltage = network.population.voltage.copy()
    before_adaptation = network.population.threshold_offset.copy()
    before_trace = learners["sensor_hidden"].pre_trace.copy()
    before_elapsed = homeostasis._elapsed
    before_tick = network.tick_count

    assert not try_fast_forward_quiet(
        network, learners, homeostasis, 25, stimulus)
    np.testing.assert_array_equal(network.population.voltage, before_voltage)
    np.testing.assert_array_equal(network.population.threshold_offset,
                                  before_adaptation)
    np.testing.assert_array_equal(learners["sensor_hidden"].pre_trace,
                                  before_trace)
    assert homeostasis._elapsed == before_elapsed
    assert network.tick_count == before_tick


def test_default_simulation_configuration_keeps_event_driven_disabled():
    from synapse_pet.runtime.config import load_config

    config = load_config()
    assert config["simulation"] == {
        "mode": "fixed_step",
        "event_driven": False,
    }


def test_engine_uses_experimental_fast_forward_only_when_explicitly_enabled(
        monkeypatch, tmp_path):
    from synapse_pet.runtime import engine as engine_module

    original_loader = engine_module.load_config

    def event_config():
        config = copy.deepcopy(original_loader())
        config["network"]["background_noise"] = 0.0
        config["simulation"] = {"mode": "event_driven", "event_driven": True}
        return config

    monkeypatch.setattr(engine_module, "load_config", event_config)
    engine = engine_module.PetEngine(seed=77, data_dir=tmp_path)
    try:
        engine.tick({}, duration_ms=50.0, active=True)
        assert engine.last_event_driven_used
        assert engine.network.tick_count == 25
    finally:
        engine.stop()

from __future__ import annotations

import copy

import numpy as np
import pytest

pytest.importorskip(
    "synapse_pet.neural_backend._stdp",
    reason="optional Cython extensions have not been built",
)
pytest.importorskip(
    "synapse_pet.neural_backend._lif",
    reason="optional Cython LIF extension has not been built",
)

from synapse_pet.core.neurons import LIFPopulation
from synapse_pet.core.network import SpikingNetwork
from synapse_pet.neural_backend.cython_backend import CythonBackend
from synapse_pet.neural_backend.numpy_backend import NumpyBackend


def _population(size: int, seed: int) -> LIFPopulation:
    source = np.random.default_rng(seed)
    population = LIFPopulation(
        size,
        tau_m_ms=19.7,
        threshold=0.93,
        reset=0.07,
        refractory_ms=2.4,
        adaptive_increment=0.037,
        adaptive_tau_ms=173.0,
    )
    population.voltage[:] = source.uniform(-0.2, 1.2, size).astype(np.float32)
    population.threshold_offset[:] = source.uniform(0.0, 0.3, size).astype(np.float32)
    population.refractory[:] = source.choice(
        np.array([-0.2, 0.0, 0.4, 1.9, 3.2], dtype=np.float32), size=size
    )
    return population


def _assert_same_state(left: LIFPopulation, right: LIFPopulation) -> None:
    for name in ("voltage", "threshold_offset", "refractory", "spikes"):
        np.testing.assert_array_equal(getattr(left, name), getattr(right, name))


@pytest.mark.parametrize(
    "size,noise_std,gain,dt_ms",
    [
        (50, 0.0, 1.0, 1.0),
        (600, 0.015, 1.0, 2.0),
        (1000, 0.037, 0.73, 0.5),
        (712, 0.11, 1.21, 4.0),
    ],
)
def test_cython_lif_is_bitwise_equal_to_numpy(size, noise_std, gain, dt_ms):
    numpy_population = _population(size, seed=size + 19)
    cython_population = _population(size, seed=size + 19)
    numpy_backend = NumpyBackend()
    cython_backend = CythonBackend()
    numpy_rng = np.random.default_rng(1401)
    cython_rng = np.random.default_rng(1401)
    current_rng = np.random.default_rng(2202)

    for step in range(240):
        current = current_rng.normal(0.0, 0.3, size).astype(np.float32)
        if step % 31 == 0:
            current[::7] += np.float32(1.1)
        numpy_spikes = numpy_backend.step_neurons(
            numpy_population, current, dt_ms, numpy_rng, noise_std, gain
        )
        cython_spikes = cython_backend.step_neurons(
            cython_population, current, dt_ms, cython_rng, noise_std, gain
        )

        np.testing.assert_array_equal(cython_spikes, numpy_spikes)
        _assert_same_state(cython_population, numpy_population)
        assert cython_rng.bit_generator.state == numpy_rng.bit_generator.state

    # The API returns an owned copy, not the mutable scratch array.
    returned = cython_backend.step_neurons(
        cython_population,
        np.zeros(size, dtype=np.float32),
        dt_ms,
        cython_rng,
        noise_std,
        gain,
    )
    returned[:] = False
    assert not np.shares_memory(returned, cython_population.spikes)


def test_cython_lif_preserves_numpy_fallback_for_noncontiguous_arrays():
    numpy_population = _population(16, seed=23)
    cython_population = _population(16, seed=23)
    for population in (numpy_population, cython_population):
        for name, dtype in (
            ("voltage", np.float32),
            ("threshold_offset", np.float32),
            ("refractory", np.float32),
            ("spikes", np.bool_),
        ):
            backing = np.zeros(32, dtype=dtype)
            backing[::2] = getattr(population, name)
            setattr(population, name, backing[::2])

    backing_current = np.linspace(-0.2, 0.7, 32, dtype=np.float32)
    current = backing_current[::2]
    numpy_rng = np.random.default_rng(42)
    cython_rng = np.random.default_rng(42)
    expected = NumpyBackend().step_neurons(
        numpy_population, current, 1.75, numpy_rng, 0.03, 0.81
    )
    actual = CythonBackend().step_neurons(
        cython_population, current, 1.75, cython_rng, 0.03, 0.81
    )
    np.testing.assert_array_equal(actual, expected)
    _assert_same_state(cython_population, numpy_population)
    assert cython_rng.bit_generator.state == numpy_rng.bit_generator.state


def test_cython_lif_falls_back_when_current_aliases_population_state():
    numpy_population = _population(12, seed=91)
    cython_population = _population(12, seed=91)
    numpy_rng = np.random.default_rng(87)
    cython_rng = np.random.default_rng(87)
    expected = NumpyBackend().step_neurons(
        numpy_population,
        numpy_population.voltage,
        2.0,
        numpy_rng,
        noise_std=0.0,
    )
    actual = CythonBackend().step_neurons(
        cython_population,
        cython_population.voltage,
        2.0,
        cython_rng,
        noise_std=0.0,
    )
    np.testing.assert_array_equal(actual, expected)
    _assert_same_state(cython_population, numpy_population)
    assert cython_rng.bit_generator.state == numpy_rng.bit_generator.state


def test_invalid_lif_current_shape_fails_before_consuming_randomness():
    population = _population(10, seed=17)
    rng = np.random.default_rng(5)
    state_before = copy.deepcopy(rng.bit_generator.state)
    with pytest.raises(ValueError, match=r"current must have shape \(10,\)"):
        CythonBackend().step_neurons(
            population,
            np.zeros(9, dtype=np.float32),
            2.0,
            rng,
            noise_std=0.1,
        )
    assert rng.bit_generator.state == state_before


def test_cython_lif_clamps_negative_zero_refractory_like_numpy():
    numpy_population = _population(8, seed=16)
    cython_population = _population(8, seed=16)
    numpy_population.refractory.fill(np.float32(-0.0))
    cython_population.refractory.fill(np.float32(-0.0))
    current = np.zeros(8, dtype=np.float32)
    numpy_spikes = NumpyBackend().step_neurons(
        numpy_population, current, 0.0, np.random.default_rng(1), 0.0
    )
    cython_spikes = CythonBackend().step_neurons(
        cython_population, current, 0.0, np.random.default_rng(1), 0.0
    )
    np.testing.assert_array_equal(cython_spikes, numpy_spikes)
    _assert_same_state(cython_population, numpy_population)
    assert not np.signbit(cython_population.refractory).any()


@pytest.mark.parametrize("size", [600, 1000])
def test_cython_lif_keeps_full_network_trajectory_bitwise_equal(size):
    numpy_network = SpikingNetwork(total_neurons=size, seed=2107, noise=0.025)
    cython_network = SpikingNetwork(total_neurons=size, seed=2107, noise=0.025)
    cython_network.set_backend(CythonBackend())
    sensor_rng = np.random.default_rng(4102)

    for step in range(120):
        sensory = sensor_rng.normal(
            0.0, 0.22, numpy_network.n_sensor
        ).astype(np.float32)
        if step % 17 == 0:
            sensory[::5] += np.float32(0.8)
        expected = numpy_network.step(sensory)
        actual = cython_network.step(sensory)
        np.testing.assert_array_equal(actual, expected)
        _assert_same_state(cython_network.population, numpy_network.population)
        assert cython_network.rng.bit_generator.state == numpy_network.rng.bit_generator.state
        assert cython_network.tick_count == numpy_network.tick_count

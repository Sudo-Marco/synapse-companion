from __future__ import annotations

import numpy as np

from synapse_pet.core.network import SpikingNetwork


def test_step_reuses_private_current_buffer_and_keeps_returned_spikes_owned():
    network = SpikingNetwork(600, seed=481, noise=0.0)
    sensor_current = np.zeros(network.n_sensor, dtype=np.float32)
    other = SpikingNetwork(600, seed=481, noise=0.0)

    first = network.step(sensor_current)
    expected_first = other.step(sensor_current)
    buffer = network._current_buffer
    saved_first = first.copy()

    # A dirty scratch array must be cleared before the next integration step.
    network._current_buffer.fill(np.float32(100.0))
    actual_second = network.step(sensor_current)
    expected_second = other.step(sensor_current)

    assert network._current_buffer is buffer
    np.testing.assert_array_equal(first, expected_first)
    np.testing.assert_array_equal(first, saved_first)
    np.testing.assert_array_equal(actual_second, expected_second)
    assert not np.shares_memory(actual_second, network._current_buffer)
    assert not np.shares_memory(actual_second, network.population.spikes)


def test_step_resizes_current_buffer_after_dynamic_output_growth():
    network = SpikingNetwork(600, seed=482, noise=0.0)
    old_buffer = network._current_buffer
    network.add_tool_group("scratch_buffer_test")

    network.step(np.zeros(network.n_sensor, dtype=np.float32))

    assert network._current_buffer is not old_buffer
    assert network._current_buffer.shape == network.population.spikes.shape

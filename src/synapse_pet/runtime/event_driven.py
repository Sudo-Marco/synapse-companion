"""Experimental fast-forward for provably quiet fixed-step intervals.

This is deliberately a narrow optimization, not an asynchronous neuron model.
It is disabled by default and falls back to ordinary integration whenever an
input, stochastic term, pending spike, refractory cell, or homeostasis boundary
could make skipping a step observable.
"""
from __future__ import annotations

import numpy as np

from ..core.homeostasis import Homeostasis
from ..core.network import SpikingNetwork
from ..core.plasticity import RewardSTDP


def try_fast_forward_quiet(
    network: SpikingNetwork,
    learners: dict[str, RewardSTDP],
    homeostasis: Homeostasis,
    steps: int,
    sensor_current: np.ndarray | None = None,
) -> bool:
    """Advance a silent, noise-free interval without running each neural step.

    Returns ``False`` without mutating state when any precondition is unsafe.
    LIF and STDP decays use a single float32 factor for the interval, so this
    experimental mode is deterministic but may differ from repeated float32
    rounding by a few ULPs. The fixed-step mode remains the reference.
    """
    count = int(steps)
    if count < 2 or network.noise != 0.0 or network.population.reset != 0.0:
        return False
    if not np.isfinite(network.dt_ms) or network.dt_ms <= 0.0:
        return False
    if sensor_current is not None:
        if np.shape(sensor_current) != (network.n_sensor,):
            return False
        if np.any(sensor_current):
            return False

    population = network.population
    if (np.any(population.spikes)
            or not np.all(np.isfinite(population.refractory))
            or np.any(population.refractory > 0.0)):
        return False
    if (not np.isfinite(population.tau_m_ms)
            or not np.isfinite(population.adaptive_tau_ms)
            or not np.isfinite(population.threshold)
            or population.tau_m_ms <= 0.0
            or population.adaptive_tau_ms <= 0.0
            or population.tau_m_ms >= population.adaptive_tau_ms
            or population.threshold <= 0.0
            or not np.all(np.isfinite(population.voltage))
            or not np.all(np.isfinite(population.threshold_offset))
            or np.any(population.threshold_offset < 0.0)):
        return False
    if np.any(population.voltage >= population.threshold + population.threshold_offset):
        return False

    dt_s = network.dt_ms / 1000.0
    # Leave any block that could trigger the homeostasis window to the normal
    # loop, preserving its weight and threshold update ordering exactly.
    if (not np.isfinite(homeostasis._elapsed)
            or homeostasis._elapsed < 0.0
            or not np.isfinite(homeostasis.window_s)
            or homeostasis.window_s <= 0.0
            or homeostasis._elapsed + count * dt_s >= homeostasis.window_s):
        return False
    expected_projection = {
        "sensor_hidden": network.sensor_to_hidden,
        "recurrent": network.recurrent,
        "hidden_output": network.hidden_to_output,
    }
    for name, learner in learners.items():
        if (learner.pre_trace is None or learner.post_trace is None
                or learner.eligibility is None
                or not np.isfinite(learner.eligibility_tau_s)
                or learner.eligibility_tau_s <= 0.0
                or not np.all(np.isfinite(learner.pre_trace))
                or not np.all(np.isfinite(learner.post_trace))
                or not np.all(np.isfinite(learner.eligibility))):
            return False
        projection = expected_projection.get(name)
        if (projection is not None
                and (learner.pre_trace.shape != (projection.n_pre,)
                     or learner.post_trace.shape != (projection.n_post,)
                     or learner.eligibility.shape != (len(projection.weights),))):
            return False

    membrane_decay = np.float32(np.exp(-network.dt_ms / population.tau_m_ms))
    adaptation_decay = np.float32(np.exp(
        -network.dt_ms / population.adaptive_tau_ms))
    membrane_factor = np.float32(float(membrane_decay) ** count)
    adaptation_factor = np.float32(float(adaptation_decay) ** count)
    np.multiply(population.voltage, membrane_factor, out=population.voltage)
    np.multiply(population.threshold_offset, adaptation_factor,
                out=population.threshold_offset)
    population.spikes.fill(False)

    for learner in learners.values():
        decay = np.float32(np.exp(-dt_s / learner.eligibility_tau_s))
        factor = np.float32(float(decay) ** count)
        np.multiply(learner.pre_trace, factor, out=learner.pre_trace)
        np.multiply(learner.post_trace, factor, out=learner.post_trace)
        np.multiply(learner.eligibility, factor, out=learner.eligibility)

    # No spikes occur in the skipped interval, so the accumulated count is
    # unchanged. Use the same sequence of scalar additions as the reference.
    for _ in range(count):
        homeostasis._elapsed += dt_s
    network.tick_count += count
    return True

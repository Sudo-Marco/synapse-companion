# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False

"""Float32 adaptive leaky integrate-and-fire update."""

import numpy as np
cimport numpy as cnp

cnp.import_array()


def step_lif(
    float[::1] voltage,
    float[::1] threshold_offset,
    float[::1] refractory,
    cnp.npy_bool[::1] spikes,
    const float[::1] current,
    const float[::1] noise,
    bint use_noise,
    float decay,
    float adaptive_decay,
    float dt_ms,
    float reset,
    float threshold,
    float adaptive_increment,
    float refractory_ms,
    float noise_std,
    float gain,
    bint apply_gain,
):
    """Mutate LIF state in the exact order of ``LIFPopulation.step``."""
    cdef Py_ssize_t i
    cdef float v
    cdef float offset
    cdef float remaining_refractory
    cdef float input_current
    cdef float scaled_noise
    cdef float threshold_with_offset
    cdef bint active
    cdef bint fired

    for i in range(voltage.shape[0]):
        active = refractory[i] <= 0.0
        v = voltage[i] * decay
        if apply_gain:
            input_current = current[i] * gain
        else:
            input_current = current[i]
        v = v + input_current
        if use_noise:
            # Keep the intermediate float32 rounding used by NumPy's separate
            # multiply and add ufuncs (the build also disables FP contraction).
            scaled_noise = noise[i] * noise_std
            v = v + scaled_noise
        if not active:
            v = reset

        offset = threshold_offset[i] * adaptive_decay
        threshold_with_offset = threshold + offset
        fired = active and v >= threshold_with_offset
        if fired:
            v = reset
            offset = offset + adaptive_increment

        remaining_refractory = refractory[i] - dt_ms
        if remaining_refractory <= 0.0:
            remaining_refractory = 0.0
        if fired:
            remaining_refractory = refractory_ms

        voltage[i] = v
        threshold_offset[i] = offset
        refractory[i] = remaining_refractory
        spikes[i] = fired

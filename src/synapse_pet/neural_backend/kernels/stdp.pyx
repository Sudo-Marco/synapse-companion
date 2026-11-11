# cython: language_level=3
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

"""Float32 reward-STDP trace and eligibility update."""

from libc.math cimport fabsf


def update_stdp(
    float[::1] pre_trace,
    float[::1] post_trace,
    float[::1] eligibility,
    const float[::1] pre_spikes,
    const float[::1] post_spikes,
    const int[::1] edge_pre,
    const int[::1] edge_post,
    float decay,
    float a_plus,
    float a_minus,
):
    """Mutate the existing float32 arrays in RewardSTDP.mark operation order."""
    cdef Py_ssize_t i
    cdef Py_ssize_t edge_count = edge_pre.shape[0]
    cdef float plus_term
    cdef float minus_term

    for i in range(pre_trace.shape[0]):
        pre_trace[i] = pre_trace[i] * decay
    for i in range(post_trace.shape[0]):
        post_trace[i] = post_trace[i] * decay

    for i in range(edge_count):
        eligibility[i] = eligibility[i] * decay
        plus_term = a_plus * pre_trace[edge_pre[i]]
        plus_term = plus_term * post_spikes[edge_post[i]]
        eligibility[i] = eligibility[i] + plus_term
        minus_term = a_minus * post_trace[edge_post[i]]
        minus_term = minus_term * pre_spikes[edge_pre[i]]
        eligibility[i] = eligibility[i] - minus_term

    for i in range(pre_trace.shape[0]):
        pre_trace[i] = pre_trace[i] + pre_spikes[i]
    for i in range(post_trace.shape[0]):
        post_trace[i] = post_trace[i] + post_spikes[i]


def apply_reward(
    float[::1] weights,
    const float[::1] eligibility,
    const int[::1] edge_pre,
    const float[::1] source_sign,
    float learning_rate_times_dopamine,
    float lower_limit,
    float upper_limit,
):
    """Apply eligibility, clip weights, then re-enforce Dale's law in-place."""
    cdef Py_ssize_t i
    cdef float delta
    cdef float weight

    for i in range(weights.shape[0]):
        delta = learning_rate_times_dopamine * eligibility[i]
        weight = weights[i] + delta
        if weight < lower_limit:
            weight = lower_limit
        elif weight > upper_limit:
            weight = upper_limit
        weights[i] = fabsf(weight) * source_sign[edge_pre[i]]

# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False

"""Deterministic float32 sparse propagation for canonical CSR projections."""

import numpy as np
cimport numpy as cnp

cnp.import_array()


def propagate_csr(
    const int[::1] indptr,
    const int[::1] indices,
    const float[::1] weights,
    const cnp.npy_bool[::1] spikes,
):
    """Traditional row-oriented CSR propagation, one output row at a time."""
    cdef Py_ssize_t n_post = indptr.shape[0] - 1
    cdef cnp.ndarray[cnp.float32_t, ndim=1] result = np.empty(
        n_post, dtype=np.float32
    )
    cdef float[::1] output = result
    cdef Py_ssize_t row, edge
    cdef float total

    with nogil:
        for row in range(n_post):
            total = 0.0
            for edge in range(indptr[row], indptr[row + 1]):
                if spikes[indices[edge]]:
                    total = total + weights[edge]
            output[row] = total
    return result


def propagate_active(
    const int[::1] source_indptr,
    const int[::1] source_order,
    const int[::1] post,
    const float[::1] weights,
    const cnp.npy_bool[::1] spikes,
    Py_ssize_t n_post,
):
    """Traverse outgoing edges of firing neurons using an int32 edge index.

    Source neurons are visited in ascending order. For any target, this is the
    same addition order as canonical CSR sorted by presynaptic index, preserving
    float32 results while skipping every edge from a silent source neuron.
    """
    cdef cnp.ndarray[cnp.float32_t, ndim=1] result = np.empty(
        n_post, dtype=np.float32
    )
    cdef float[::1] output = result
    cdef Py_ssize_t row, source, cursor, edge

    with nogil:
        for row in range(n_post):
            output[row] = 0.0
        for source in range(source_indptr.shape[0] - 1):
            if spikes[source]:
                for cursor in range(source_indptr[source],
                                    source_indptr[source + 1]):
                    edge = source_order[cursor]
                    row = post[edge]
                    output[row] = output[row] + weights[edge]
    return result

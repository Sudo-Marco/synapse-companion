from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import psutil
import scipy

from synapse_pet.core.synapses import SparseProjection
from synapse_pet.neural_backend.cython_backend import CythonBackend
from synapse_pet.neural_backend.numpy_backend import NumpyBackend


def _make_projection(n_pre: int, n_post: int, density: float, seed: int):
    rng = np.random.default_rng(seed)
    post, pre = np.nonzero(rng.random((n_post, n_pre)) < density)
    signs = np.where(np.arange(n_pre) % 3 == 0, -1.0, 1.0).astype(np.float32)
    weights = rng.uniform(0.01, 0.14, len(pre)).astype(np.float32) * signs[pre]
    return SparseProjection(
        n_pre,
        n_post,
        pre.astype(np.int32),
        post.astype(np.int32),
        weights,
        signs,
    )


def _measure(operation, calls: int, repeats: int):
    for _ in range(min(10, calls)):
        operation()
    wall_samples = []
    cpu_samples = []
    for _ in range(repeats):
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        for _ in range(calls):
            operation()
        cpu_samples.append(time.process_time() - cpu_start)
        wall_samples.append(time.perf_counter() - wall_start)

    tracemalloc.start()
    tracemalloc.reset_peak()
    for _ in range(calls):
        operation()
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "wall_ms_per_call_mean": statistics.mean(wall_samples) * 1000 / calls,
        "cpu_ms_per_call_mean": statistics.mean(cpu_samples) * 1000 / calls,
        "wall_samples_seconds": wall_samples,
        "python_traced_peak_bytes": int(peak_bytes),
    }


def _case(
    n_pre: int,
    n_post: int,
    density: float,
    rate: float,
    seed: int,
    calls: int,
    repeats: int,
    backend: CythonBackend,
):
    projection = _make_projection(n_pre, n_post, density, seed)
    rng = np.random.default_rng(seed + 1)
    count = int(round(rate * n_pre))
    spikes = np.zeros(n_pre, dtype=np.bool_)
    if count:
        spikes[rng.choice(n_pre, size=count, replace=False)] = True

    csr_matrix = projection._matrix
    source_build_start = time.perf_counter()
    source_indptr, source_order = projection.source_index()
    source_build_seconds = time.perf_counter() - source_build_start
    numpy_call = lambda: projection.currents(spikes)
    csr_call = lambda: backend._sparse.propagate_csr(
        csr_matrix.indptr, csr_matrix.indices, csr_matrix.data, spikes
    )
    active_call = lambda: backend._sparse.propagate_active(
        source_indptr,
        source_order,
        projection.post,
        projection.weights,
        spikes,
        n_post,
    )
    auto_call = lambda: backend.propagate(projection, spikes)

    reference = numpy_call()
    for name, operation in (
        ("cython_csr", csr_call),
        ("cython_active", active_call),
        ("cython_auto", auto_call),
    ):
        np.testing.assert_array_equal(operation(), reference, err_msg=name)

    measurements = {
        "numpy_scipy_csr": _measure(numpy_call, calls, repeats),
        "cython_csr": _measure(csr_call, calls, repeats),
        "cython_active": _measure(active_call, calls, repeats),
        "cython_auto": _measure(auto_call, calls, repeats),
    }
    active_ms = measurements["cython_active"]["wall_ms_per_call_mean"]
    csr_ms = measurements["cython_csr"]["wall_ms_per_call_mean"]
    auto_ms = measurements["cython_auto"]["wall_ms_per_call_mean"]
    numpy_ms = measurements["numpy_scipy_csr"]["wall_ms_per_call_mean"]
    actual_rate = count / n_pre if n_pre else 0.0
    selected = (
        "active"
        if actual_rate <= backend.ACTIVE_PROPAGATION_MAX_RATE and count > 0
        else "zero" if count == 0 else "csr"
    )
    return {
        "n_pre": n_pre,
        "n_post": n_post,
        "edges": int(len(projection.weights)),
        "density": density,
        "requested_spike_rate": rate,
        "active_spikes": count,
        "actual_spike_rate": actual_rate,
        "selected_strategy": selected,
        "source_index_build_ms": source_build_seconds * 1000,
        "source_index_bytes": int(source_indptr.nbytes + source_order.nbytes),
        "weight_bytes": int(projection.weights.nbytes),
        "weights_shared_with_csr": bool(
            np.shares_memory(projection.weights, csr_matrix.data)
        ),
        "measurements": measurements,
        "active_vs_csr_speedup": csr_ms / active_ms if active_ms else None,
        "auto_vs_numpy_speedup": numpy_ms / auto_ms if auto_ms else None,
        "bitwise_equal": True,
    }


def run(args):
    backend = CythonBackend()
    cases = []
    for neurons in args.neurons:
        n_sensor = int(neurons * 0.16)
        n_hidden = int(neurons * 0.64)
        n_output = neurons - n_sensor - n_hidden
        projections = (
            ("sensor_to_hidden", n_sensor, n_hidden),
            ("recurrent", n_hidden, n_hidden),
            ("hidden_to_output", n_hidden, n_output),
        )
        for projection_name, n_pre, n_post in projections:
            for density in args.densities:
                for rate in args.spike_rates:
                    case = _case(
                        n_pre,
                        n_post,
                        density,
                        rate,
                        args.seed + neurons * 17 + n_pre * 7 + int(rate * 10000),
                        args.calls,
                        args.repeats,
                        backend,
                    )
                    case["network_size"] = neurons
                    case["projection"] = projection_name
                    cases.append(case)

    return {
        "benchmark": "cython_sparse_propagation",
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "cython": __import__("Cython").__version__,
            "rss_bytes_after": psutil.Process().memory_info().rss,
        },
        "workload": {
            "network_sizes": args.neurons,
            "densities": args.densities,
            "spike_rates": args.spike_rates,
            "calls_per_sample": args.calls,
            "repeats": args.repeats,
            "seed": args.seed,
            "active_crossover": backend.ACTIVE_PROPAGATION_MAX_RATE,
        },
        "cases": cases,
        "notes": [
            "The active-source index adds one int32 edge permutation and one int32 source indptr; it does not duplicate weights.",
            "Source indices are stably grouped by source, preserving the ascending presynaptic accumulation order of canonical CSR.",
            "Microbenchmarks report output-allocation cost for every call; source-index construction is measured separately.",
            "Full-network tick timing is provided by benchmark_cython_lif.py in the same CI job.",
            "RSS is process-wide and tracemalloc excludes native allocations.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--neurons", type=int, nargs="+", default=[600, 1000])
    parser.add_argument("--densities", type=float, nargs="+", default=[0.05, 0.10, 0.20])
    parser.add_argument(
        "--spike-rates", type=float, nargs="+",
        default=[0.0, 0.01, 0.05, 0.15, 0.30, 0.60, 1.0],
    )
    parser.add_argument("--calls", type=int, default=50)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261112)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args)
    serialized = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()

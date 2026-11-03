from __future__ import annotations
import json
import os
import time
import gc
import numpy as np
try:
    import psutil
except ImportError:
    psutil = None
from synapse_pet.core.network import SpikingNetwork

def rss_bytes() -> int:
    if psutil is not None:
        return int(psutil.Process(os.getpid()).memory_info().rss)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.WorkingSetSize)
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if os.uname().sysname == "Darwin" else value * 1024)

def main() -> None:
    net = SpikingNetwork(1000, seed=123)
    sensor = np.zeros(net.n_sensor, dtype=np.float32)
    wall_samples = []
    cpu_start = time.process_time()
    for _ in range(100):
        start = time.perf_counter()
        for _ in range(25):
            net.step(sensor)
        wall_samples.append((time.perf_counter() - start) * 1000)
    mean_cpu_ms = (time.process_time() - cpu_start) * 10.0
    import tempfile
    from pathlib import Path
    from synapse_pet.runtime.engine import PetEngine
    with tempfile.TemporaryDirectory(prefix="synapse-pet-bench-") as directory:
        engine = PetEngine(neurons=600, data_dir=Path(directory))
        engine.start()
        idle_wall_start = time.perf_counter()
        time.sleep(10.0)
        engine.stop()
        idle_wall = time.perf_counter() - idle_wall_start
        idle_cpu = engine.simulation_cpu_seconds
        rss = rss_bytes()
        del engine
        gc.collect()
    print(json.dumps({"neurons_benchmarked": len(net.population.voltage),
        "recurrent_edges": len(net.recurrent.weights),
        "tick_50ms_cpu_ms_mean": mean_cpu_ms,
        "tick_50ms_wall_ms_p95": sorted(wall_samples)[94],
        "idle_simulation_thread_one_core_percent": 100*idle_cpu/idle_wall,
        "process_rss_mb": rss/(1024*1024),
        "targets": {"idle_percent_lt": 3, "rss_mb_lt": 150, "tick_ms_lt": 10}}, indent=2))

if __name__ == "__main__":
    main()

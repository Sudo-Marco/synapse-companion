from __future__ import annotations

import time

from synapse_pet.runtime.engine import PetEngine


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def test_user_pause_stops_ticks_without_watchdog_and_can_resume(tmp_path):
    engine = PetEngine(seed=81, data_dir=tmp_path)
    engine.start()
    try:
        assert _wait_until(lambda: engine.network.tick_count > 0)
        engine.set_paused(True)
        assert _wait_until(lambda: engine.health_snapshot()["status"] == "paused")
        paused_tick = engine.network.tick_count
        time.sleep(0.4)
        assert engine.network.tick_count == paused_tick
        engine.set_paused(False)
        assert _wait_until(lambda: engine.network.tick_count > paused_tick)
        assert engine.health_snapshot()["status"] == "running"
    finally:
        engine.stop()


def test_autonomy_can_be_silenced_independently_of_simulation(tmp_path):
    engine = PetEngine(seed=82, data_dir=tmp_path)

    engine.set_autonomy_enabled(False)

    assert not engine.autonomy_enabled
    assert engine.action_results.get_nowait() == {
        "operation": "runtime", "status": "autonomy_off"}

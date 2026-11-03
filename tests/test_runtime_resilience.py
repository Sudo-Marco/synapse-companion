from __future__ import annotations

import threading
import time

from synapse_pet.mind.action_selection import ActionCandidate
from synapse_pet.runtime.engine import PetEngine


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def drain_results(engine: PetEngine) -> list[dict[str, object]]:
    results = []
    while True:
        try:
            results.append(engine.action_results.get_nowait())
        except Exception:
            return results


def test_exploration_accept_save_sequence_keeps_ticks_running(tmp_path):
    engine = PetEngine(seed=301, data_dir=tmp_path)
    engine._pending_tools["resumo_arquivos_alterados"] = time.monotonic() + 10.0
    engine.start()
    try:
        engine.submit_affection()
        assert wait_until(lambda: engine.network.tick_count >= 1)
        engine.submit_tool_response(
            "resumo_arquivos_alterados", True, "explorar ambiente")
        engine.submit_save()
        assert wait_until(lambda: engine.store.path.with_suffix(".json").exists())
        tick_after_save = engine.network.tick_count
        assert wait_until(lambda: engine.network.tick_count > tick_after_save)
        assert engine._thread is not None and engine._thread.is_alive()
        assert engine.health_snapshot()["status"] == "running"
    finally:
        engine.stop()


def test_slow_save_disk_io_does_not_pause_simulation_ticks(tmp_path):
    engine = PetEngine(seed=302, data_dir=tmp_path)
    entered_writer = threading.Event()
    release_writer = threading.Event()
    real_writer = engine.store.write_snapshot

    def slow_writer(payload):
        entered_writer.set()
        assert release_writer.wait(5.0)
        real_writer(payload)

    engine.store.write_snapshot = slow_writer
    engine.start()
    try:
        engine.submit_context(window_category="save-context")
        assert wait_until(lambda: bool(engine.network.context_output_weights))
        engine.submit_save()
        assert entered_writer.wait(5.0)
        before = engine.network.tick_count
        assert wait_until(lambda: engine.network.tick_count > before)
        assert engine._thread is not None and engine._thread.is_alive()
    finally:
        release_writer.set()
        engine.stop()
    restored, _ = engine.store.load()
    assert restored.context_output_weights


def test_save_exception_is_logged_and_does_not_kill_simulation(tmp_path):
    engine = PetEngine(seed=303, data_dir=tmp_path)

    def failing_writer(_payload):
        raise OSError("forced save failure")

    engine.store.write_snapshot = failing_writer
    engine.start()
    try:
        engine.submit_save()
        assert wait_until(lambda: any(
            result.get("operation") == "save" and result.get("status") == "error"
            for result in drain_results(engine)))
        before = engine.network.tick_count
        assert wait_until(lambda: engine.network.tick_count > before)
        assert engine._thread is not None and engine._thread.is_alive()
    finally:
        engine.stop()
    log_text = engine.log_path.read_text(encoding="utf-8")
    assert "forced save failure" in log_text
    assert "Traceback" in log_text


def test_tick_exception_restores_checkpoint_and_loop_recovers(tmp_path):
    engine = PetEngine(seed=304, data_dir=tmp_path)
    engine.save()
    tick = engine.tick
    failed_once = False

    def fail_first_tick(*args, **kwargs):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise RuntimeError("forced simulation failure")
        return tick(*args, **kwargs)

    engine.tick = fail_first_tick
    engine.start()
    try:
        assert wait_until(lambda: failed_once and engine.network.tick_count > 0)
        assert engine._thread is not None and engine._thread.is_alive()
        assert engine.health_snapshot()["status"] == "running"
    finally:
        engine.stop()
    log_text = engine.log_path.read_text(encoding="utf-8")
    assert "forced simulation failure" in log_text
    assert "Traceback" in log_text
    assert "restaurado do snapshot" in log_text


def test_watchdog_marks_stall_and_restarts_from_checkpoint(tmp_path):
    engine = PetEngine(seed=306, data_dir=tmp_path)
    engine.save()
    original_tick = engine.tick
    entered_tick = threading.Event()
    release_tick = threading.Event()
    first = True
    engine._watchdog_timeout_s = 1.0

    def hold_first_tick(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            entered_tick.set()
            assert release_tick.wait(5.0)
        return original_tick(*args, **kwargs)

    engine.tick = hold_first_tick
    engine.start()
    first_thread = engine._thread
    try:
        assert entered_tick.wait(5.0)
        assert wait_until(lambda: engine.health_snapshot()["status"] == "stalled",
                          timeout=3.0)
        assert wait_until(engine.stop_event.is_set, timeout=1.0)
        release_tick.set()
        assert wait_until(lambda: engine._thread is not first_thread
                          and engine._thread is not None
                          and engine._thread.is_alive()
                          and not engine.stop_event.is_set(), timeout=5.0)
    finally:
        release_tick.set()
        engine.stop()
    log_text = engine.log_path.read_text(encoding="utf-8")
    assert "Watchdog: tick parado" in log_text
    assert "Thread de simulação morreu; tentando recuperar" in log_text


def test_pending_proposal_times_out_without_stopping_ticks(tmp_path):
    engine = PetEngine(seed=305, data_dir=tmp_path)
    engine._proposal_timeout_s = 0.15
    engine._pending_tools["proposta_lenta"] = time.monotonic() + 0.15
    engine.proposals.put(ActionCandidate(
        "proposta_lenta", 0.5, risk="medium", context="teste"))
    engine.start()
    try:
        assert wait_until(lambda: "proposta_lenta" not in engine._pending_tools)
        before = engine.network.tick_count
        assert wait_until(lambda: engine.network.tick_count > before)
        assert engine._thread is not None and engine._thread.is_alive()
        assert any(result.get("status") == "timeout"
                   for result in drain_results(engine))
    finally:
        engine.stop()

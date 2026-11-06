from __future__ import annotations

import random
import time

from PySide6.QtCore import QPoint, QSettings

from synapse_pet.ui.desktop_motion import (DesktopBehaviorSelector, WorkArea,
                                          choose_work_area_target,
                                          clamp_window_top_left, desktop_depth)
from synapse_pet.sensors.window_geometry import covers_monitor
from synapse_pet.runtime.visual_state import VisualState
from synapse_pet.ui.qt_app import PetWindow, ensure_application


def test_window_is_clamped_inside_workarea_including_negative_monitor_origin():
    area = WorkArea(-1920, 0, 1920, 1040)
    assert clamp_window_top_left(-3000, 1100, 320, 180, area) == (-1920, 860)
    assert clamp_window_top_left(900, -40, 320, 180, area) == (-320, 0)


def test_depth_uses_workarea_vertical_position():
    area = WorkArea(-1200, 100, 1200, 900)
    assert desktop_depth(100, area) == 1.0
    assert desktop_depth(999, area) == 0.0
    assert 0.45 < desktop_depth(550, area) < 0.55


def test_random_destination_respects_monitor_and_taskbar_free_area():
    areas = [WorkArea(0, 0, 1920, 1040), WorkArea(-1280, 120, 1280, 900)]
    index, x, y = choose_work_area_target(
        areas, (200, 200), (320, 180), random.Random(4), far=True)
    area = areas[index]
    assert area.left <= x <= area.right - 320
    assert area.top <= y <= area.bottom - 180
    assert y < area.top + area.height * 0.4


def test_behavior_selector_applies_emotion_stamina_cooldown_and_hour_budget():
    selector = DesktopBehaviorSelector({
        "max_actions_per_hour": 1,
        "actions": {
            "think": {"weight": 1, "emotions": ["curioso"], "cooldown_s": 30},
            "rest": {"weight": 1, "max_stamina": 0.2},
            "window": {"weight": 1, "requires_window": True},
        },
    }, seed=11)
    assert selector.choose("alegre", 0.9, 1.0) is None
    first = selector.choose("curioso", 0.9, 2.0)
    assert first == "think"
    assert selector.choose("curioso", 0.9, 3.0) is None
    assert selector.choose("neutro", 0.1, 3603.0) == "rest"


def test_fullscreen_detection_uses_geometry_and_no_window_text():
    monitor = (-1920, 0, 0, 1080)
    assert covers_monitor(monitor, monitor)
    assert covers_monitor((-1910, 4, -10, 1072), monitor)
    assert not covers_monitor((-1800, 60, -100, 1000), monitor)


def test_desktop_motion_stops_for_pending_proposal_and_user_drag(tmp_path, monkeypatch):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path / "settings"))
    ensure_application()
    monkeypatch.setattr(PetWindow, "_start_global_panel_hotkey", lambda _self: None)
    from synapse_pet.runtime.engine import PetEngine

    engine = PetEngine(seed=313, data_dir=tmp_path / "pet-data")
    engine.config["pet"].update({"mode": "floating", "render_style": "pixel"})
    window = PetWindow(engine)
    try:
        window._enter_floating_mode()
        window.move(100, 100)
        start = QPoint(window.pos())
        assert window._start_desktop_travel(
            start.x() + 120, start.y(), "walk", behavior="wander", duration_s=1.0)
        window._consider_desktop_motion(
            VisualState(), {"status": "running", "pending_proposals": 1,
                            "proposal_queue": 0}, time.monotonic())
        assert window._desktop_animation is None

        assert window._start_desktop_travel(
            start.x() + 120, start.y(), "walk", behavior="wander", duration_s=1.0)
        window._pet_drag_offset = QPoint(1, 1)
        window._consider_desktop_motion(
            VisualState(), {"status": "running", "pending_proposals": 0,
                            "proposal_queue": 0}, time.monotonic())
        assert window._desktop_animation is None
    finally:
        window._requested_exit = True
        window.close()
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline and not window._really_close:
            ensure_application().processEvents()

from __future__ import annotations

from datetime import datetime
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import yaml
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QImage

from synapse_pet.runtime.visual_state import VisualState
from synapse_pet.ui.gl_renderer import EyeCanvas
from synapse_pet.ui.pixel_renderer import ASSET_DIR, PixelPetWidget
from synapse_pet.ui.qt_app import PetWindow, ensure_application


def test_pixel_style_is_default_and_old_styles_remain_selectable():
    ensure_application()
    config_path = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    pet = yaml.safe_load(config_path.read_text(encoding="utf-8"))["pet"]
    assert pet["render_style"] == "pixel"
    assert pet["depth_in_pet_mode"] is False
    for style in ("spectral", "ascii", "vector"):
        canvas = EyeCanvas("cpu", 800, 450, 80, 45, "cyan_amber_white", 8,
                           render_style=style, compact=True)
        try:
            assert canvas.render_style == style
        finally:
            canvas.close()


def test_pixel_pet_mode_is_transparent_and_uses_sprite_alpha_mask():
    ensure_application()
    widget = PixelPetWidget(compact=True)
    widget.resize(320, 180)
    widget.set_mode("pet")
    widget.show()
    ensure_application().processEvents()
    frame = widget.render_frame(4.0, datetime(2026, 11, 5, 12))
    pixels = np.frombuffer(frame.constBits().tobytes(), dtype=np.uint8).reshape(
        frame.height(), frame.width(), 4)
    assert frame.format() == QImage.Format.Format_ARGB32_Premultiplied
    assert pixels[0, 0, 3] == 0
    assert pixels[:, :, 3].max() == 255
    mask = widget.sprite_mask()
    assert not mask.isEmpty()
    assert mask.contains(widget.rect().center())
    assert not mask.contains(widget.rect().topLeft())
    widget.close()


def test_pixel_expressions_sleep_and_scene_time_render_differently():
    ensure_application()
    widget = PixelPetWidget()
    widget.resize(800, 450)
    widget.show()
    ensure_application().processEvents()
    local_noon = datetime(2026, 11, 5, 12)
    neutral_image = widget.render_frame(1.0, local_noon)
    neutral = bytes(neutral_image.constBits().tobytes())
    widget.set_state(VisualState(happiness=0.9, dopamine=0.2))
    happy_image = widget.render_frame(1.2, local_noon)
    happy = bytes(happy_image.constBits().tobytes())
    widget.set_state(VisualState(expression_override="dormindo", energy=0.0))
    sleeping_image = widget.render_frame(1.4, local_noon)
    sleeping = bytes(sleeping_image.constBits().tobytes())
    widget.set_mode("hud")
    hud_image = widget.render_frame(1.6, datetime(2026, 11, 5, 23))
    hud_night = bytes(hud_image.constBits().tobytes())
    assert len({neutral, happy, sleeping, hud_night}) == 4
    widget.close()


def test_pixel_canvas_switches_without_losing_state_or_mode():
    ensure_application()
    canvas = EyeCanvas("ascii", 800, 450, 80, 45, "cyan_amber_white", 8,
                       compact=True, render_style="pixel")
    try:
        canvas.resize(320, 180)
        canvas.set_state(VisualState(happiness=0.88))
        canvas.set_mode("pet")
        assert canvas._pixel is not None
        assert canvas._ascii_eye is None
        assert canvas.mode == "pet"
        assert canvas.current_renderer.startswith("Piu pixel art")
        canvas._pixel.render_frame(1.0, datetime(2026, 11, 5, 12))
        before = canvas.sprite_mask()
        assert not before.isEmpty()
        assert canvas.request_move("right", "run")
        canvas._pixel.render_frame(1.2, datetime(2026, 11, 5, 12))
        after = canvas.sprite_mask()
        assert not after.isEmpty()
        assert after != before
        assert canvas.request_move("right", "run")
    finally:
        canvas.close()


def test_new_emotion_pose_can_be_added_through_manifest_data():
    ensure_application()
    widget = PixelPetWidget()
    try:
        widget._manifest["routes"]["emotions"]["novo_estado"] = {
            "animation": "frente", "frame": "feliz"}
        group, index, use_lod = widget._select_pose(
            VisualState(expression_override="novo_estado"),
            widget.motion.frame, 1.0)
        assert (group, index, use_lod) == ("frente", 2, False)
        widget._manifest["routes"]["emotions"]["novo_loop"] = {
            "animation": "corrida_lateral", "mode": "time_loop"}
        group, index, use_lod = widget._select_pose(
            VisualState(expression_override="novo_loop"),
            widget.motion.frame, 1.2)
        assert group == "corrida_lateral" and 0 <= index < 8 and not use_lod
    finally:
        widget.close()


def test_v03_view_routes_select_exact_native_lod_and_keep_panel_scale():
    ensure_application()
    widget = PixelPetWidget()
    try:
        route = widget._manifest["routes"]["views"]["back"]
        for size in (48, 32, 20):
            motion = replace(widget.motion.frame, view="back", lod_size=size)
            group, index, use_lod = widget._route_frame(route, motion, 1.0)
            assert group == "idle_costas" and not use_lod
            entry = widget._manifest["animations"][group]["frames"][index]
            assert entry["native_size"] == size

        widget.resize(800, 450)
        widget.render_frame(5.0, datetime(2026, 11, 5, 12))
        sprite_height = widget._current_destination.height()
        assert 0.15 <= sprite_height / 450 <= 0.25
    finally:
        widget.close()


def test_world_travel_selects_back_lod_and_rest_uses_manifest_pose():
    ensure_application()
    widget = PixelPetWidget(compact=True, depth_in_pet_mode=True)
    try:
        widget.resize(320, 180)
        widget.set_mode("pet")
        widget.set_world_travel("away", depth=0.9)
        widget.render_frame(8.0, datetime(2026, 11, 5, 12))
        assert widget._current_frame_entry["view"] == "costas"
        assert widget._current_frame_entry["native_size"] == 20
        widget.set_world_travel(None)
        widget.set_behavior_action("rest")
        widget.render_frame(8.2, datetime(2026, 11, 5, 12))
        assert widget._current_frame_entry["view"] == "frente"
        assert widget._current_frame_entry["native_size"] == 48
    finally:
        widget.close()


def test_audio_badges_join_pet_mask_and_music_phase_drives_dance_frames():
    ensure_application()
    widget = PixelPetWidget(compact=True)
    try:
        widget.resize(320, 180)
        widget.set_mode("pet")
        widget.set_audio_status(microphone_enabled=True,
                                loopback_enabled=True,
                                music_active=True, bpm=120.0,
                                beat_phase=0.05, level=0.4)
        widget.set_behavior_action("dance_sway")
        widget.render_frame(2.0, datetime(2026, 11, 5, 12))
        first_index = widget._current_frame_entry["label_key"]
        assert len(widget._audio_badge_rects) == 2
        mask = widget.sprite_mask()
        assert all(mask.contains(rect.center())
                   for rect in widget._audio_badge_rects)

        widget.set_audio_status(microphone_enabled=True,
                                loopback_enabled=True,
                                music_active=True, bpm=120.0,
                                beat_phase=0.85, level=0.4)
        widget.render_frame(2.1, datetime(2026, 11, 5, 12))
        second_index = widget._current_frame_entry["label_key"]
        assert first_index != second_index
    finally:
        widget.close()


def test_audio_controls_are_opt_in_and_update_tray_indicator(tmp_path, monkeypatch):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path / "settings"))
    ensure_application()
    monkeypatch.setattr(PetWindow, "_start_global_panel_hotkey", lambda _self: None)
    from synapse_pet.runtime.engine import PetEngine

    engine = PetEngine(seed=94, data_dir=tmp_path / "pet-data")
    window = PetWindow(engine)
    try:
        assert not window._audio_enabled["microphone"]
        assert not window._audio_enabled["loopback"]
        assert window.audio_service.active_sources == ()
        started = []
        monkeypatch.setattr(window.audio_service, "start",
                            lambda source: started.append(source) or True)
        window.audio_actions["microphone"].setChecked(True)
        assert started == ["microphone"]
        assert "microfone" in window._tray_icon.toolTip()
        window.audio_actions["microphone"].setChecked(False)
        assert not window._audio_enabled["microphone"]
        assert "microfone" not in window._tray_icon.toolTip()
    finally:
        window._requested_exit = True
        window.close()
        deadline = __import__("time").monotonic() + 6.0
        while __import__("time").monotonic() < deadline and not window._really_close:
            ensure_application().processEvents()


def test_floating_panel_can_use_pixel_sprite_mask_and_return_to_pixel_pet(tmp_path, monkeypatch):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path / "settings"))
    ensure_application()
    monkeypatch.setattr(PetWindow, "_start_global_panel_hotkey", lambda _self: None)
    from synapse_pet.runtime.engine import PetEngine

    engine = PetEngine(seed=93, data_dir=tmp_path / "pet-data")
    engine.config["pet"].update({"mode": "floating", "render_style": "pixel"})
    window = PetWindow(engine)
    try:
        window._enter_floating_mode()
        ensure_application().processEvents()
        assert window.canvas.render_style == "pixel"
        assert window._is_floating
        assert not window.mask().isEmpty()
        assert window.mask().contains(window.rect().center())
        window._show_panel()
        ensure_application().processEvents()
        assert not window._is_floating
        assert window.canvas.mode == "ascii"
        window._enter_floating_mode()
        ensure_application().processEvents()
        assert window._is_floating and window.canvas.mode == "pet"
    finally:
        window._requested_exit = True
        window.close()
        deadline = __import__("time").monotonic() + 6.0
        while __import__("time").monotonic() < deadline and not window._really_close:
            ensure_application().processEvents()

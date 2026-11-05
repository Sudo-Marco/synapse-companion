from __future__ import annotations

import os
from datetime import datetime
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtTest import QTest

from synapse_pet.runtime.engine import PetEngine
from synapse_pet.ui.ascii_runtime import AnimatedAsciiEyeWidget
from synapse_pet.ui.qt_app import PetWindow, ensure_application


def test_compact_pet_mode_renders_only_eye_on_transparent_buffer():
    ensure_application()
    widget = AnimatedAsciiEyeWidget(columns=40, rows=22, compact=True,
                                    max_columns=48, max_rows=30)
    widget.resize(320, 180)
    widget.set_mode("pet")
    frame = widget.render_frame(now=12.0, local_time=datetime.now().astimezone())

    assert frame.format().name == "Format_RGBA8888"
    pixels = np.frombuffer(frame.bits().tobytes(), dtype=np.uint8).reshape(
        frame.height(), frame.width(), 4)
    alpha = pixels[:, :, 3]
    assert alpha[0, 0] == 0
    assert alpha.max() == 255
    assert np.count_nonzero(alpha) < alpha.size


def test_ascii_lod_minimum_features_and_eight_pixel_cells_all_sizes():
    from scripts.legibility_lod_review import HEIGHTS, render_eye, new_widget

    expected_levels = {
        48: "small", 64: "small", 96: "small",
        128: "medium", 192: "medium", 256: "large",
    }
    detail_weights = []
    for height in HEIGHTS:
        width = round(height * 1.9)
        widget = new_widget(width, height)
        render_eye(widget, width, height)
        assert widget.lod_level == expected_levels[height]
        assert width / widget.columns >= 8.0
        assert height / widget.rows >= 8.0
        metrics = widget._small_lod_metrics
        assert metrics["pupil_width_cells"] >= 3
        assert metrics["pupil_height_cells"] >= 3
        assert metrics["main_reflection_cells"] >= 4
        assert metrics["secondary_reflection_cells"] >= 1
        assert metrics["outline_is_closed"]
        iris_radius = widget._iris_geometry[2]
        pupil_radius = widget._pupil_geometry[2]
        assert iris_radius - pupil_radius >= 1.0
        detail_weights.append(widget.lod_detail_weight)
    assert detail_weights == sorted(detail_weights)


def test_ascii_lod_transition_has_no_large_geometry_jump():
    from datetime import datetime

    eye_sizes = []
    for height in range(104, 121, 2):
        width = round(height * 1.9)
        widget = AnimatedAsciiEyeWidget(
            columns=max(6, width // 8), rows=max(6, height // 8), compact=True,
            max_columns=max(64, width // 8 + 20), max_rows=max(40, height // 8 + 20),
            scene_time="day", density="normal",
            outline={"theme_auto": False, "double": True, "thickness_px": 1,
                     "font_size": 7, "dark": [7, 13, 23],
                     "light": [250, 252, 255], "plate_alpha": 0.42},
        )
        widget.resize(width, height)
        widget._resize_resolution()
        widget.set_mode("pet")
        widget._update_attention = lambda _now: None
        widget._next_glance = float("inf")
        widget._next_blink = float("inf")
        widget.render_frame(now=1_000.0, local_time=datetime.now().astimezone())
        _cx, _cy, _rx, ry, opening = widget._eye_geometry
        iris_radius = widget._iris_geometry[2]
        pupil_radius = widget._pupil_geometry[2]
        eye_sizes.append((2 * ry * opening * height / widget.rows,
                          2 * iris_radius * height / widget.rows,
                          2 * pupil_radius * height / widget.rows))

    for previous, current in zip(eye_sizes, eye_sizes[1:]):
        for before_size, after_size in zip(previous, current):
            assert abs(after_size - before_size) / max(after_size, before_size) < 0.12


def test_pet_rebuilds_ascii_resolution_when_display_dpi_changes(monkeypatch):
    ensure_application()
    widget = AnimatedAsciiEyeWidget(columns=24, rows=14, compact=True,
                                    max_columns=100, max_rows=60)
    widget.resize(320, 180)
    widget._resize_resolution()
    before = (widget.columns, widget.rows)
    monkeypatch.setattr(widget, "devicePixelRatioF", lambda: 2.0)

    widget.event(QEvent(QEvent.Type.DevicePixelRatioChange))

    assert widget.columns > before[0]
    assert widget.rows > before[1]


def test_ascii_lod_contrast_targets_on_six_backgrounds_at_six_heights():
    from PIL import Image
    from scripts.legibility_lod_review import (
        BACKGROUNDS, HEIGHTS, contrast_metrics, make_backgrounds, new_widget,
        render_eye,
    )

    for height in HEIGHTS:
        width = round(height * 1.9)
        widget = new_widget(width, height)
        eye = render_eye(widget, width, height)
        backgrounds = make_backgrounds(width, height)
        composed = {
            name: Image.alpha_composite(background.convert("RGBA"), eye).convert("RGB")
            for name, background in backgrounds.items()
        }
        rows = contrast_metrics(widget, eye, backgrounds, composed)
        assert [row["background"] for row in rows] == list(BACKGROUNDS)
        assert all(row["silhouette_vs_background_p05"] >= 3.0 for row in rows)
        assert all(row["pupil_vs_iris"] >= 3.0 for row in rows)
        assert all(row["reflection_vs_sclera"] >= 3.0 for row in rows)


def test_floating_pet_switches_to_panel_and_back(tmp_path, monkeypatch):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path / "settings"))
    ensure_application()
    monkeypatch.setattr(PetWindow, "_start_global_panel_hotkey", lambda _self: None)
    engine = PetEngine(seed=92, data_dir=tmp_path / "pet-data")
    engine.config["pet"].update({"mode": "floating", "anchor": "bottom_right"})
    window = PetWindow(engine)
    try:
        window._enter_floating_mode()
        assert window._is_floating
        assert window.canvas.mode == "pet"
        assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert window.windowFlags() & Qt.WindowType.Tool
        assert not window.mask().isEmpty()
        assert window.mask().contains(window.rect().center())
        assert not window.mask().contains(window.rect().topLeft())
        tray_actions = {action.text() for action in window._tray_icon.contextMenu().actions()}
        assert {"Abrir painel", "Pausar simulação", "Silenciar autonomia",
                "Iniciar com o Windows", "Sair"} <= tray_actions
        original_position = window.pos()

        eye = window.canvas._stack.currentWidget()
        geometry_before_hover = window.geometry()
        window.eventFilter(eye, QEvent(QEvent.Type.Enter))
        assert window.geometry() == geometry_before_hover
        window.eventFilter(eye, QEvent(QEvent.Type.Leave))
        QTest.mouseDClick(eye, Qt.MouseButton.LeftButton,
                          pos=eye.rect().center())
        assert not window._is_floating
        assert window.canvas.mode == "ascii"
        assert window.mask().isEmpty()

        window.move(original_position.x() + 120, original_position.y() + 90)
        window._enter_floating_mode()
        assert window._is_floating
        assert window.pos() == original_position
        assert window.isVisible()

        base_geometry = window.geometry()
        window._begin_jump("happy", 24, 640)
        window._jump_frame(0.25, "happy", 24)
        assert window.y() < base_geometry.y()
        window._stop_jump(restore_start=True)
        assert window.geometry() == base_geometry

        window._begin_jump("sad", 4, 900)
        window._jump_frame(0.5, "sad", 4)
        assert window.y() > base_geometry.y()
        window._stop_jump(restore_start=True)
    finally:
        window._requested_exit = True
        window.close()
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline and not window._really_close:
            ensure_application().processEvents()
            time.sleep(0.01)

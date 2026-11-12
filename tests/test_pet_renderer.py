from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
import yaml

from synapse_pet.runtime.engine import PetEngine
from synapse_pet.runtime.visual_state import VisualState
from synapse_pet.ui.ascii_runtime import AnimatedAsciiEyeWidget
from synapse_pet.ui.gl_renderer import EyeCanvas
from synapse_pet.ui.qt_app import PetWindow, ensure_application
from synapse_pet.ui.spectral_eye import SpectralEyeRenderer


def test_pixel_style_is_default_and_legacy_styles_remain_documented():
    config_path = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    pet = config["pet"]

    assert pet["render_style"] == "pixel"
    assert pet["depth_in_pet_mode"] is False
    assert 0 <= pet["spectral"]["glow_strength"] <= 1
    assert 0 <= pet["spectral"]["rune_count"] <= 12
    assert 0 <= pet["spectral"]["smoke_density"] <= 1


def test_eye_canvas_selects_each_render_style_without_changing_pet_mode():
    ensure_application()
    for style in ("spectral", "ascii", "vector"):
        canvas = EyeCanvas("auto", 800, 450, 80, 45, "cyan_amber_white", 8,
                           compact=True, render_style=style)
        try:
            assert canvas._ascii_eye is not None
            assert canvas._ascii_eye.render_style == style
            canvas.set_mode("pet")
            frame = canvas._ascii_eye.render_frame(
                now=4.0, local_time=datetime(2026, 11, 5, 12).astimezone())
            assert frame.format().name == "Format_RGBA8888"
            # Font rasterization and grid-cell alignment vary by platform; the
            # geometric center may be a transparent glyph cell. Verify the
            # whole transparent frame contains rendered pixels instead.
            pixels = np.frombuffer(
                frame.constBits().tobytes(), dtype=np.uint8
            ).reshape(frame.height(), frame.width(), 4)
            assert pixels[:, :, 3].max() > 0
        finally:
            canvas.close()


def test_spectral_renderer_draws_emotional_states_and_caches_static_base():
    ensure_application()
    renderer = SpectralEyeRenderer(glow_strength=0.82, rune_count=10,
                                   smoke_density=0.62)
    open_image = QImage(640, 360, QImage.Format.Format_ARGB32_Premultiplied)
    open_image.fill(Qt.GlobalColor.transparent)
    renderer.draw(open_image, VisualState(happiness=0.82, affection=0.8),
                  3.0, 0.9, (0.0, 0.0), style="spectral")
    open_bytes = open_image.bits().tobytes()

    sleeping_image = QImage(640, 360, QImage.Format.Format_ARGB32_Premultiplied)
    sleeping_image.fill(Qt.GlobalColor.transparent)
    renderer.draw(sleeping_image,
                  VisualState(expression_override="dormindo", energy=0.0),
                  3.0, 0.0, (0.0, 0.0), style="spectral")
    sleeping_bytes = sleeping_image.bits().tobytes()

    assert open_bytes != sleeping_bytes
    sleep_rgba = sleeping_image.convertToFormat(QImage.Format.Format_RGBA8888)
    sleep_pixels = np.frombuffer(sleep_rgba.constBits().tobytes(),
                                 dtype=np.uint8).reshape(360, 640, 4)
    sleep_cyan = ((sleep_pixels[:, :, 1] > 100)
                  & (sleep_pixels[:, :, 2] > 120)
                  & (sleep_pixels[:, :, 0] < 120))
    assert sleep_cyan[:70].any()  # The animated Zs stay visible above the eye.
    assert renderer.cached_size_count == 1
    assert len(renderer._iris_cache) == 1
    assert len(renderer._rune_cache) == 1

    # Reusing a cached size does not add another static silhouette entry.
    for _ in range(5):
        renderer.draw(open_image, VisualState(), 3.1, 0.9,
                      (0.1, -0.1), style="spectral")
    assert renderer.cached_size_count == 1
    assert len(renderer._rune_cache) == 1

    # The cache remains bounded while the window is resized repeatedly.
    for width in range(120, 140):
        renderer._base_pixmap(width, width // 2, False, "spectral")
    assert renderer.cached_size_count <= renderer._CACHE_LIMIT


def test_legacy_ascii_renderer_remains_distinct_from_spectral_eye():
    ensure_application()
    images = {}
    for style in ("ascii", "spectral"):
        widget = AnimatedAsciiEyeWidget(columns=40, rows=22, compact=True,
                                        max_columns=48, max_rows=30,
                                        render_style=style)
        widget.resize(320, 180)
        widget.set_mode("pet")
        images[style] = widget.render_frame(
            now=8.0, local_time=datetime(2026, 11, 5, 12).astimezone())
        pixels = np.frombuffer(images[style].constBits().tobytes(), dtype=np.uint8)
        assert pixels[3::4].max() > 0
        widget.close()

    assert images["ascii"].bits().tobytes() != images["spectral"].bits().tobytes()


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
        assert window.canvas.render_style == "pixel"
        assert window.canvas._pixel is not None
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

        # The feet meet the top of the taskbar work area. A downward motion
        # from the floor is clamped there; from above the floor it still falls.
        window._begin_jump("sad", 4, 900)
        window._jump_frame(0.5, "sad", 4)
        assert window.y() == base_geometry.y()
        window._stop_jump(restore_start=True)

        window.move(base_geometry.x(), base_geometry.y() - 12)
        window._begin_jump("sad", 4, 900)
        fall_start_y = window.y()
        window._jump_frame(0.5, "sad", 4)
        assert window.y() > fall_start_y
        assert window.y() <= base_geometry.y()
        window._stop_jump(restore_start=True)
    finally:
        window._requested_exit = True
        window.close()
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline and not window._really_close:
            ensure_application().processEvents()
            time.sleep(0.01)

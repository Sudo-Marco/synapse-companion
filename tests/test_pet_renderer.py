from __future__ import annotations

import os
from datetime import datetime
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QSettings, Qt
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
        assert not window.mask().isEmpty()
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

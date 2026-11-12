from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage, QPainter

from synapse_pet.runtime.visual_state import VisualState
from synapse_pet.ui.pixel_renderer import PET_SPRITE_DIR, PixelPetWidget
from synapse_pet.ui.qt_app import ensure_application
from synapse_pet.ui.sprite_adapter import SpriteAdapter


def test_atlas_grid_anchor_and_assets_are_consistent():
    adapter = SpriteAdapter(PET_SPRITE_DIR)
    assert (adapter.sheet.width(), adapter.sheet.height()) == (384, 1296)
    assert (adapter.frame_width, adapter.frame_height) == (48, 48)
    assert (adapter.anchor_x, adapter.anchor_y) == (24, 43)
    assert len(adapter.animations) == 27


def test_adapter_uses_anchor_nearest_neighbor_and_does_not_restart_same_loop():
    ensure_application()
    adapter = SpriteAdapter(PET_SPRITE_DIR)
    image = QImage(192, 192, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    first = adapter.draw(painter, QPoint(96, 172), 4, 0.0, "idle")
    assert first.destination == QRect(0, 0, 192, 192)
    adapter.draw(painter, QPoint(96, 172), 4, 0.35, "idle")
    later = adapter.draw(painter, QPoint(96, 172), 4, 0.50, "idle")
    painter.end()
    assert later.index == 3
    assert SpriteAdapter.normalize_scale(3.7) == 3.5


def test_non_loop_emotion_finishes_then_holds_fallback_until_state_changes():
    ensure_application()
    adapter = SpriteAdapter(PET_SPRITE_DIR)
    image = QImage(192, 192, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    assert adapter.draw(painter, (96, 172), 4, 0.0, "surprised").animation == "surprised"
    assert adapter.draw(painter, (96, 172), 4, 0.6, "surprised").animation == "idle"
    assert adapter.draw(painter, (96, 172), 4, 1.1, "surprised").animation == "idle"
    assert adapter.draw(painter, (96, 172), 4, 1.2, "happy").animation == "happy"
    painter.end()


def test_sprite_override_returns_to_mapped_emotion_after_one_shot():
    ensure_application()
    adapter = SpriteAdapter(PET_SPRITE_DIR)
    image = QImage(192, 192, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    adapter.draw(painter, (96, 172), 4, 0.0, "sad")
    adapter.set_override("land", 0.1)
    assert adapter.draw(painter, (96, 172), 4, 0.2, "sad").animation == "land"
    assert adapter.draw(painter, (96, 172), 4, 0.6, "sad").animation == "sad"
    painter.end()


def test_floating_pet_uses_new_atlas_for_idle_walking_and_emotions():
    ensure_application()
    widget = PixelPetWidget(compact=True, sprite_scale=4)
    try:
        widget.resize(192, 192)
        widget.set_mode("pet")
        idle = widget.render_frame(1.0, datetime(2026, 11, 8, 12))
        assert idle.size().width() == 192
        assert widget._current_frame_entry["animation"] == "idle"

        widget.set_state(VisualState(happiness=0.95))
        widget.render_frame(1.4, datetime(2026, 11, 8, 12))
        assert widget._current_frame_entry["animation"] == "happy"

        assert widget.request_move("left", "run")
        widget.render_frame(1.5, datetime(2026, 11, 8, 12))
        assert widget.motion.frame.x < 0.5
        assert widget._current_frame_entry["animation"] == "run_side_left"

        widget.set_state(VisualState(expression_override="dormindo", energy=0.0))
        widget.render_frame(1.8, datetime(2026, 11, 8, 12))
        assert widget._current_frame_entry["animation"] == "run_side_left"
        widget.set_world_travel(None)
        widget.set_behavior_action("rest")
        widget.render_frame(2.0, datetime(2026, 11, 8, 12))
        assert widget._current_frame_entry["animation"] == "sleep"
    finally:
        widget.close()

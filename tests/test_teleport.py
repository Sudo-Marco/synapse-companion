from PySide6.QtCore import QPointF, QRect

from synapse_pet.ui.teleport import (
    STYLES,
    quadratic_point,
    teleport_geometry,
)


def test_quadratic_path_preserves_endpoints():
    start = QPointF(-200, 40)
    end = QPointF(500, 240)
    assert quadratic_point(start, end, 0.0, 90) == start
    assert quadratic_point(start, end, 1.0, 90) == end


def test_teleport_shrinks_travels_and_materializes_at_destination():
    start = QRect(-300, 120, 320, 180)
    destination = QRect(900, 620, 320, 180)
    style = STYLES["curious"]

    initial, initial_opacity = teleport_geometry(start, destination, 0.0, style)
    travelling, travel_opacity = teleport_geometry(start, destination, 0.5, style)
    final, final_opacity = teleport_geometry(start, destination, 1.0, style)

    assert initial == start
    assert initial_opacity == 1.0
    assert travelling.size().width() < start.width()
    assert travelling.center() != start.center()
    assert 0.0 <= travel_opacity <= 1.0
    assert final == destination
    assert final_opacity == 1.0

    shrinking, shrinking_opacity = teleport_geometry(start, destination, 0.1, style)
    materializing, materializing_opacity = teleport_geometry(
        start, destination, 0.9, style)
    assert (shrinking.center() - start.center()).manhattanLength() <= 1
    assert shrinking.size().width() < start.width()
    assert shrinking_opacity < 1.0
    assert (materializing.center() - destination.center()).manhattanLength() <= 2
    assert materializing.size().width() > travelling.size().width()
    assert materializing.size().width() < destination.width()
    assert materializing_opacity > travel_opacity


def test_emotion_styles_stay_within_requested_duration():
    assert set(STYLES) == {"curious", "happy", "stress", "sleepy", "communicate"}
    assert all(400 <= style.duration_ms <= 900 for style in STYLES.values())
    assert STYLES["stress"].shake_px > 0
    assert STYLES["happy"].overshoot > STYLES["curious"].overshoot
    assert STYLES["sleepy"].duration_ms == max(
        style.duration_ms for style in STYLES.values())


from __future__ import annotations

from synapse_pet.ui.pet_motion import PetMotionController


def test_move_requests_obey_drag_and_pending_proposal_locks():
    controller = PetMotionController()
    assert not controller.request_move("right", "run", dragging=True)
    assert not controller.request_move("right", "run", proposal_pending=True)
    assert not controller.request_move("unknown", "run")
    assert not controller.request_move("right", "teleport")
    assert controller.request_move("right", "run")


def test_far_and_return_moves_change_view_and_hysteretic_lod():
    controller = PetMotionController()
    assert controller.request_move("far", "away")
    assert controller.frame.view == "back"
    for _ in range(8):
        frame = controller.advance(0.2)
    assert frame.depth > 0.75
    assert frame.lod_size == 16
    assert frame.view == "back"

    assert controller.request_move("camera", "return")
    assert controller.frame.view == "front"
    for _ in range(8):
        frame = controller.advance(0.2)
    assert frame.depth < 0.35
    assert frame.lod_size == 32
    assert frame.view == "front"


def test_run_phase_matches_declared_stride_distance_and_keeps_pivot():
    controller = PetMotionController(pivot=(16, 40))
    assert controller.request_move("right", "run")
    for _ in range(4):
        frame = controller.advance(0.10, viewport_width=800, sprite_scale=4)
    expected_cycles = frame.traveled_px / (
        controller.STRIDE_DISTANCE_PX * 4)
    assert frame.stride_phase == expected_cycles * 8
    assert PetMotionController.frame_index(frame, 8) == int(frame.stride_phase) % 8
    assert controller.pivot == (16, 40)


def test_blocking_pauses_current_motion_without_changing_scene_position():
    controller = PetMotionController()
    controller.request_move("right", "run")
    before = controller.advance(0.1)
    controller.set_blocked(dragging=True)
    blocked = controller.advance(0.2)
    assert (blocked.x, blocked.depth) == (before.x, before.depth)
    controller.set_blocked()
    after = controller.advance(0.1)
    assert after.x > before.x

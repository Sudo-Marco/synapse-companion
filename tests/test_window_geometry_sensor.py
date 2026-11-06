from __future__ import annotations

import ctypes

from synapse_pet.sensors.window_geometry import WindowGeometryObserver


class FakeUser32:
    def __init__(self, *, pid=456, minimized=False, rect=(-1920, 0, 0, 1080)):
        self.pid = pid
        self.minimized = minimized
        self.rect = rect

    def GetForegroundWindow(self):
        return 77

    def IsWindowVisible(self, _hwnd):
        return True

    def IsIconic(self, _hwnd):
        return self.minimized

    def GetWindowThreadProcessId(self, _hwnd, process_pointer):
        ctypes.cast(process_pointer, ctypes.POINTER(ctypes.c_ulong)).contents.value = self.pid
        return 1

    def GetWindowRect(self, _hwnd, rect_pointer):
        rect = rect_pointer._obj
        rect.left, rect.top, rect.right, rect.bottom = self.rect
        return True

    def MonitorFromWindow(self, _hwnd, _flags):
        return 1

    def GetMonitorInfoW(self, _monitor, info_pointer):
        info = info_pointer._obj
        info.rcMonitor.left, info.rcMonitor.top = -1920, 0
        info.rcMonitor.right, info.rcMonitor.bottom = 0, 1080
        info.rcWork.left, info.rcWork.top = -1920, 0
        info.rcWork.right, info.rcWork.bottom = 0, 1040
        return True


def test_observer_returns_only_geometry_and_flags_fullscreen():
    observer = WindowGeometryObserver(user32=FakeUser32(), own_pid=123)
    snapshot = observer.poll()
    assert snapshot is not None
    assert (snapshot.left, snapshot.top, snapshot.right, snapshot.bottom) == (
        -1920, 0, 0, 1080)
    assert snapshot.fullscreen
    assert not hasattr(snapshot, "title")


def test_observer_ignores_own_process_and_minimized_windows():
    assert WindowGeometryObserver(user32=FakeUser32(pid=123), own_pid=123).poll() is None
    assert WindowGeometryObserver(
        user32=FakeUser32(minimized=True), own_pid=123).poll() is None


def test_observer_ignores_nonfullscreen_rect_and_has_no_text_reader():
    api = FakeUser32(rect=(-1800, 80, -120, 1000))
    snapshot = WindowGeometryObserver(user32=api, own_pid=123).poll()
    assert snapshot is not None and not snapshot.fullscreen
    assert not hasattr(api, "GetWindowTextW")

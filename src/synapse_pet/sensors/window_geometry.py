from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
import sys
from ctypes import wintypes


@dataclass(frozen=True, slots=True)
class WindowGeometry:
    """A foreground-window rectangle; contains no title, text, or contents."""

    left: int
    top: int
    right: int
    bottom: int
    fullscreen: bool = False

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2,
                (self.top + self.bottom) // 2)


def covers_monitor(window: tuple[int, int, int, int],
                   monitor: tuple[int, int, int, int],
                   threshold: float = 0.94) -> bool:
    """Whether a window is large enough to count as fullscreen/presentation."""
    left, top, right, bottom = window
    m_left, m_top, m_right, m_bottom = monitor
    width, height = max(0, right - left), max(0, bottom - top)
    monitor_width, monitor_height = max(1, m_right - m_left), max(1, m_bottom - m_top)
    overlap_width = max(0, min(right, m_right) - max(left, m_left))
    overlap_height = max(0, min(bottom, m_bottom) - max(top, m_top))
    return (width >= monitor_width * threshold
            and height >= monitor_height * threshold
            and overlap_width >= monitor_width * threshold
            and overlap_height >= monitor_height * threshold)


class WindowGeometryObserver:
    """Read only the active HWND rectangle, at the caller's requested cadence.

    It deliberately never calls GetWindowText or reads accessibility/UI text.
    The UI polls this object only after the user enables the sensor.
    """

    MONITOR_DEFAULTTONEAREST = 2

    def __init__(self, *, user32=None, own_pid: int | None = None) -> None:
        self._user32 = user32
        self.own_pid = os.getpid() if own_pid is None else int(own_pid)

    @staticmethod
    def _structures():
        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

        return RECT, MONITORINFO

    def poll(self) -> WindowGeometry | None:
        if self._user32 is None:
            if sys.platform != "win32":
                return None
            try:
                self._user32 = ctypes.windll.user32
                self._user32.GetForegroundWindow.restype = wintypes.HWND
            except (AttributeError, OSError):
                return None
        user32 = self._user32
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return None
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) == self.own_pid:
                return None
            RECT, MONITORINFO = self._structures()
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            if rect.right <= rect.left or rect.bottom <= rect.top:
                return None
            monitor = user32.MonitorFromWindow(hwnd, self.MONITOR_DEFAULTTONEAREST)
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                return WindowGeometry(rect.left, rect.top, rect.right, rect.bottom)
            monitor_rect = (info.rcMonitor.left, info.rcMonitor.top,
                            info.rcMonitor.right, info.rcMonitor.bottom)
            window_rect = (rect.left, rect.top, rect.right, rect.bottom)
            return WindowGeometry(*window_rect,
                                  fullscreen=covers_monitor(window_rect, monitor_rect))
        except (AttributeError, OSError, TypeError, ValueError):
            return None


__all__ = ["WindowGeometry", "WindowGeometryObserver", "covers_monitor"]

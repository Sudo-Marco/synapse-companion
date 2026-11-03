from __future__ import annotations
from pathlib import Path
from .base import Sensor, SensorEvent

class ActiveWindowCategorySensor(Sensor):
    """Reads process executable name and emits only a configured category."""
    def __init__(self, rules: dict[str, list[str]], enabled: bool = False) -> None:
        super().__init__(enabled)
        self.rules = {k: tuple(v) for k, v in rules.items()}

    def sample(self) -> SensorEvent | None:
        if not self.enabled:
            return None
        try:
            import ctypes
            import psutil
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            name = Path(psutil.Process(pid.value).name()).stem.lower()
        except Exception:
            return None
        category = "outro"
        for group, words in self.rules.items():
            if any(word.lower() in name for word in words):
                category = group
                break
        return SensorEvent("window_category", category)

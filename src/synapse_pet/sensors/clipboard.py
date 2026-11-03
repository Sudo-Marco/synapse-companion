from __future__ import annotations
import hashlib
from .base import Sensor, SensorEvent

class ClipboardSensor(Sensor):
    """Opt-in clipboard counter; contents are never returned or persisted."""
    def __init__(self, enabled: bool = False) -> None:
        super().__init__(enabled)
        self._last_digest: bytes | None = None

    def sample(self) -> SensorEvent | None:
        if not self.enabled:
            return None
        try:
            import tkinter as tk
            root = tk.Tk(); root.withdraw()
            value = root.clipboard_get()
            root.destroy()
            digest = hashlib.blake2b(value.encode("utf-8", errors="replace"), digest_size=8).digest()
            if digest == self._last_digest:
                return None
            self._last_digest = digest
            return SensorEvent("clipboard_chars", len(value))
        except Exception:
            return None

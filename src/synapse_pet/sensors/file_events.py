from __future__ import annotations
from pathlib import Path
from .base import Sensor, SensorEvent

class FileEventsSensor(Sensor):
    def __init__(self, folder: Path, enabled: bool = False) -> None:
        super().__init__(enabled)
        self.folder = folder
        self._known: dict[str, int] = {}

    def sample(self) -> SensorEvent | None:
        if not self.enabled or not self.folder.exists():
            return None
        current = {p.name: p.stat().st_mtime_ns for p in self.folder.iterdir() if p.is_file()}
        changed = len(set(current.items()) ^ set(self._known.items()))
        self._known = current
        return SensorEvent("changed_file_count", changed)

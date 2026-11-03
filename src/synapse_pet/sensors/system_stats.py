from __future__ import annotations
from .base import Sensor, SensorEvent

class SystemStatsSensor(Sensor):
    def sample(self) -> SensorEvent | None:
        if not self.enabled:
            return None
        try:
            import psutil
            return SensorEvent("system_stats", {"cpu": psutil.cpu_percent(interval=None),
                                               "memory": psutil.virtual_memory().percent})
        except Exception:
            return None

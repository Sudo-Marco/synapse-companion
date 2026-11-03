from __future__ import annotations
from datetime import datetime
from .base import Sensor, SensorEvent

class ClockSensor(Sensor):
    def __init__(self) -> None:
        super().__init__(True)

    def sample(self) -> SensorEvent:
        now = datetime.now()
        return SensorEvent("clock", {"hour": now.hour, "weekday": now.weekday()})

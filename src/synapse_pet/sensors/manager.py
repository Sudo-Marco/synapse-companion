from __future__ import annotations
from pathlib import Path
from typing import Any
from .active_window import ActiveWindowCategorySensor
from .base import Sensor
from .clipboard import ClipboardSensor
from .clock import ClockSensor
from .file_events import FileEventsSensor
from .input_activity import InputActivitySensor
from .system_stats import SystemStatsSensor

class SensorManager:
    """Starts only sensors explicitly enabled in configuration or by the user."""
    NAMES = ("input_activity", "active_window", "file_events", "clipboard", "system_stats")

    def __init__(self, data_dir: Path, sensor_config: dict[str, Any],
                 window_rules: dict[str, list[str]]) -> None:
        self.sensors: dict[str, Sensor] = {
            "input_activity": InputActivitySensor(),
            "active_window": ActiveWindowCategorySensor(window_rules),
            "file_events": FileEventsSensor(data_dir / "monitored"),
            "clipboard": ClipboardSensor(),
            "system_stats": SystemStatsSensor(),
            "clock": ClockSensor(),
        }
        self.last_window_category: str | None = None
        self.activity_detected = False
        for name in self.NAMES:
            self.set_enabled(name, bool(sensor_config.get(name, False)), start=False)

    def start_enabled(self) -> None:
        for name, sensor in self.sensors.items():
            if sensor.enabled:
                start = getattr(sensor, "start", None)
                if callable(start):
                    start()

    def set_enabled(self, name: str, enabled: bool, *, start: bool = True) -> None:
        sensor = self.sensors[name]
        if sensor.enabled == enabled:
            return
        sensor.enabled = enabled
        if start and enabled:
            begin = getattr(sensor, "start", None)
            if callable(begin):
                begin()
        elif not enabled:
            stop = getattr(sensor, "stop", None)
            if callable(stop):
                stop()

    def sample_context(self) -> dict[str, object]:
        context: dict[str, object] = {}
        self.activity_detected = False
        for name, sensor in self.sensors.items():
            event = sensor.sample()
            if event is None:
                continue
            if name == "clock":
                context["hour"] = float(event.value["hour"]) / 23.0
            elif name == "input_activity" and float(event.value) > 0:
                context["input_rate"] = min(1.0, float(event.value) / 10.0)
                self.activity_detected = True
            elif name == "active_window":
                category = str(event.value)
                context["window_category"] = category
                if category != self.last_window_category:
                    self.activity_detected = True
                    self.last_window_category = category
            elif name == "file_events" and int(event.value) > 0:
                context["activity"] = min(1.0, int(event.value) / 10.0)
                self.activity_detected = True
            elif name == "clipboard" and int(event.value) > 0:
                context["activity"] = min(1.0, int(event.value) / 1000.0)
                self.activity_detected = True
            elif name == "system_stats":
                context["activity"] = min(1.0, float(event.value["cpu"]) / 100.0)
                self.activity_detected = True
        return context

    def stop(self) -> None:
        for sensor in self.sensors.values():
            stop = getattr(sensor, "stop", None)
            if callable(stop):
                stop()

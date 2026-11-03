from __future__ import annotations
import time
from .base import Sensor, SensorEvent

class InputActivitySensor(Sensor):
    """Counts keyboard/mouse events per second; never captures key identity or text."""
    def __init__(self, enabled: bool = False) -> None:
        super().__init__(enabled)
        self._count = 0
        self._last = time.monotonic()
        self._listeners: list[object] = []

    def start(self) -> None:
        if not self.enabled:
            return
        try:
            from pynput import keyboard, mouse
        except ImportError:
            return
        self._listeners = [keyboard.Listener(on_press=self._on_key), mouse.Listener(on_click=self._on_click)]
        for listener in self._listeners:
            listener.start()

    def _on_key(self, _key: object) -> None:
        self._count += 1

    def _on_click(self, _x: int, _y: int, _button: object, pressed: bool) -> None:
        if pressed:
            self._count += 1

    def sample(self) -> SensorEvent | None:
        now = time.monotonic()
        if not self.enabled or now - self._last < 1.0:
            return None
        rate = self._count / (now - self._last)
        self._count, self._last = 0, now
        return SensorEvent("input_rate", rate)

    def stop(self) -> None:
        for listener in self._listeners:
            listener.stop()
        self._listeners.clear()

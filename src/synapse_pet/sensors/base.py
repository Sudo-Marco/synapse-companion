from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class SensorEvent:
    kind: str
    value: object

class Sensor(ABC):
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    @abstractmethod
    def sample(self) -> SensorEvent | None:
        raise NotImplementedError

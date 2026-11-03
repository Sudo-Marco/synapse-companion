from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable

ToolFn = Callable[[dict[str, Any]], dict[str, Any]]

@dataclass(frozen=True)
class ToolManifest:
    name: str
    description: str
    risk: str
    tags: tuple[str, ...]
    cost: float = 0.1
    run: ToolFn | None = None
    undo: ToolFn | None = None

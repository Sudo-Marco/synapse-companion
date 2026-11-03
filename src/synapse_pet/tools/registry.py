from __future__ import annotations
import importlib.util
from pathlib import Path
from typing import Any
from .manifest import ToolManifest

class ToolRegistry:
    """Registry for built-ins and explicitly installed trusted Python plugins."""
    def __init__(self) -> None:
        self._tools: dict[str, ToolManifest] = {}

    def register(self, manifest: ToolManifest) -> None:
        if not manifest.name or manifest.risk not in {"low", "medium", "high"}:
            raise ValueError("tool needs a name and low/medium/high risk")
        self._tools[manifest.name] = manifest

    def get(self, name: str) -> ToolManifest:
        return self._tools[name]

    def all(self) -> tuple[ToolManifest, ...]:
        return tuple(self._tools.values())

    def load_user_plugins(self, folder: Path) -> list[str]:
        loaded = []
        for path in sorted(folder.glob("*.py")) if folder.exists() else []:
            spec = importlib.util.spec_from_file_location(f"synapse_user_tool_{path.stem}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            manifest = getattr(module, "MANIFEST", None)
            if isinstance(manifest, ToolManifest):
                self.register(manifest); loaded.append(manifest.name)
        return loaded

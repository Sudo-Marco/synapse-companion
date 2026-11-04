from __future__ import annotations
from pathlib import Path
from typing import Any
import ast

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "configs"

def _scalar(value: str) -> Any:
    value = value.strip()
    if value in {"", "null", "None", "~"}:
        return None
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        return [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return value.strip("'\"")

def _minimal_yaml(text: str) -> dict[str, Any]:
    """Parse the simple nested mappings and inline lists used by bundled configs."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, sep, value = line.strip().partition(":")
        if not sep:
            continue
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not value.strip():
            child: dict[str, Any] = {}
            parent[key.strip()] = child
            stack.append((indent, child))
        else:
            parent[key.strip()] = _scalar(value)
    return root

def _read_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        return _minimal_yaml(text)
    return yaml.safe_load(text) or {}

def load_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or CONFIG_DIR / "default.yaml"
    if not path.exists():
        return {"seed": 41, "network": {"neurons": 600, "dt_ms": 2.0,
                "recurrent_connectivity": .1, "background_noise": .015, "tool_group_size": 8,
                "allow_neuron_growth_migration": False},
                "privacy": {"sensors": {}},"tools": {}}
    return _read_yaml(path)

def load_window_rules(config_path: Path | None = None) -> dict[str, list[str]]:
    path = config_path or CONFIG_DIR / "window_rules.yaml"
    return _read_yaml(path) if path.exists() else {}

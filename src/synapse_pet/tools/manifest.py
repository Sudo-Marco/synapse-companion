from __future__ import annotations
from dataclasses import dataclass, field
import math
from typing import Any, Callable, Mapping

ToolFn = Callable[[dict[str, Any]], dict[str, Any]]
_MISSING = object()


class ToolParameterError(ValueError):
    """A tool request failed its manifest schema before reaching the tool."""

    def __init__(self, message: str, *, missing: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.missing = missing


@dataclass(frozen=True)
class ToolParameter:
    value_type: type | tuple[type, ...]
    required: bool = False
    default: Any = _MISSING
    minimum: int | float | None = None
    maximum: int | float | None = None
    max_length: int | None = None
    item_type: type | tuple[type, ...] | None = None

    def default_value(self) -> Any:
        if self.default is _MISSING:
            return _MISSING
        return self.default() if callable(self.default) else self.default

@dataclass(frozen=True)
class ToolManifest:
    name: str
    description: str
    risk: str
    tags: tuple[str, ...]
    cost: float = 0.1
    run: ToolFn | None = None
    undo: ToolFn | None = None
    parameters: Mapping[str, ToolParameter] = field(default_factory=dict)

    def prepare_parameters(self, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if params is None:
            supplied: dict[str, Any] = {}
        elif isinstance(params, Mapping):
            supplied = dict(params)
        else:
            raise ToolParameterError("parâmetros devem ser um objeto")
        if any(not isinstance(name, str) for name in supplied):
            raise ToolParameterError("nomes de parâmetros devem ser texto")
        unknown = sorted(set(supplied) - set(self.parameters))
        if unknown:
            raise ToolParameterError(f"parâmetros não reconhecidos: {', '.join(unknown)}")

        prepared: dict[str, Any] = {}
        missing: list[str] = []
        for name, spec in self.parameters.items():
            if name in supplied:
                value = supplied[name]
            else:
                value = spec.default_value()
            if value is _MISSING or (spec.required and
                                     (value is None or value == "")):
                if spec.required:
                    missing.append(name)
                continue

            if not _matches_type(value, spec.value_type):
                raise ToolParameterError(f"parâmetro '{name}' tem tipo inválido")
            if spec.minimum is not None and value < spec.minimum:
                raise ToolParameterError(f"parâmetro '{name}' abaixo do mínimo")
            if spec.maximum is not None and value > spec.maximum:
                raise ToolParameterError(f"parâmetro '{name}' acima do máximo")
            if spec.max_length is not None and len(value) > spec.max_length:
                raise ToolParameterError(f"parâmetro '{name}' excede o tamanho permitido")
            if spec.item_type is not None and any(
                    not _matches_type(item, spec.item_type) for item in value):
                raise ToolParameterError(f"itens de '{name}' têm tipo inválido")
            prepared[name] = value

        if missing:
            names = tuple(missing)
            raise ToolParameterError(
                f"faltam parâmetros obrigatórios: {', '.join(names)}", missing=names)
        return prepared


def _matches_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    accepted = expected if isinstance(expected, tuple) else (expected,)
    if isinstance(value, bool) and bool not in accepted:
        return False
    if isinstance(value, float) and any(candidate in (int, float)
                                        for candidate in accepted):
        if not math.isfinite(value):
            return False
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, expected)

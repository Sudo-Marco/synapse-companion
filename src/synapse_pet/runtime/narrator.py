from __future__ import annotations
from typing import Protocol

class NarratorProvider(Protocol):
    def say(self, intent: str, context: dict[str, object]) -> str: ...

class TemplateNarrator:
    templates = {
        "hello": ("Oi! Estou por aqui.", "Pronto para acompanhar você."),
        "pause": ("Você está há um tempo em atividade. Uma pausa pode ajudar.",),
        "curious": ("Esse contexto é novo para mim.",),
        "thanks": ("Obrigado pelo carinho!",),
    }
    def say(self, intent: str, context: dict[str, object] | None = None) -> str:
        choices = self.templates.get(intent, ("Estou acompanhando.",))
        index = int(context.get("variant", 0)) if context else 0
        return choices[index % len(choices)]

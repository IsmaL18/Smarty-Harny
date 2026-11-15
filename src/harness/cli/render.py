"""Rendu d'un événement : ligne-titre (CA-12) ou détail complet (CA-13).

Le mode détaillé est un état du REPL, pas du noyau (ADR-0008 §4).
"""

import json

from harness.events import (
    AssistantMessage,
    LimitReached,
    ProviderFailed,
    StepCompleted,
    ToolCallFinished,
    ToolCallStarted,
)

_TITLE_WIDTH = 100


def _short(text: str, width: int = _TITLE_WIDTH) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return (
        line if len(line) <= width and "\n" not in text.strip() else line[:width] + "…"
    )


def render(event: object, detail: bool) -> str | None:
    """Texte à afficher pour l'événement, ou None s'il ne s'affiche pas."""
    match event:
        case ToolCallStarted(name, arguments):
            if detail:
                return f"appel de l'outil {name} :\n{json.dumps(arguments, ensure_ascii=False, indent=2)}"
            target = arguments.get("path") or arguments.get("command") or ""
            return f"appel de l'outil {name} : {_short(str(target))}"
        case ToolCallFinished(name, result):
            if detail:
                kind = "erreur" if result.is_error else "résultat"
                shown = f"{kind} de {name} :\n{result.content}"
                return f"{shown}\n{result.detail}" if result.detail else shown
            if result.is_error:
                return f"erreur de {name} : {_short(result.content)}"
            if result.title:
                return f"résultat de {name} : {result.title}"
            return f"résultat de {name} : ok ({len(result.content)} caractères)"
        case AssistantMessage(text):
            # Jamais tronquée, dans les deux modes (CA-12 amendé) : c'est la sortie utile.
            return f"réponse :\n{text}"
        case LimitReached(_, summary):
            return summary
        case ProviderFailed(error):
            return f"{error.message_fr}\nVotre conversation est conservée : renvoyez un message pour réessayer."
        case StepCompleted():
            return None
    return None

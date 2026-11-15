"""Contrat des outils et point d'exécution unique (ADR-0002).

Notion : tool-calling (docs/notions/tool-calling.md).

Principe central : une erreur d'outil est un *résultat* renvoyé au modèle, pas une
exception. `ToolRegistry.execute` garantit donc exactement un `ToolResult` par appel,
quoi qu'il arrive (outil inconnu, JSON illisible, arguments invalides, exception).
Seule `CancelledError` (Ctrl+C, ADR-0005) traverse : c'est la boucle qui la traite.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import jsonschema

from harness.tools.arguments import coerce_arguments
from harness.tools.environment import Environment


@dataclass(frozen=True)
class ToolResult:
    content: str  # ce que voit le modèle
    is_error: bool
    # Réservés à l'utilisateur (ADR-0010 §12) : ligne-titre et détail (diff) affichés par
    # le REPL ; le modèle ne les voit jamais.
    title: str | None = None
    detail: str | None = None


class Tool(Protocol):
    name: str
    description: str
    parameters: dict  # schéma JSON des paramètres, écrit à la main (ADR-0002 §1)

    async def run(self, args: dict, env: Environment) -> ToolResult: ...


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool], environment: Environment):
        self._tools = {tool.name: tool for tool in tools}
        self._environment = environment

    def specs(self) -> list[dict]:
        """Description des outils au format OpenAI, transmise au modèle à chaque appel."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    async def execute(self, tool_call: dict) -> ToolResult:
        function = tool_call.get("function", {})
        name = function.get("name", "")
        tool = self._tools.get(name)
        if tool is None:
            known = ", ".join(self._tools)
            return ToolResult(
                f"error: unknown tool '{name}' (available: {known})", True
            )
        try:
            args = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError as exc:
            return ToolResult(f"error: invalid arguments: not valid JSON ({exc})", True)
        # Formes corrigées d'après le schéma (ADR-0009 §5), puis validation stricte.
        if isinstance(args, dict):
            args = coerce_arguments(args, tool.parameters)
        try:
            jsonschema.validate(args, tool.parameters)
        except jsonschema.ValidationError as exc:
            return ToolResult(_describe_invalid(exc), True)
        try:
            return await tool.run(args, self._environment)
        except Exception as exc:  # noqa: BLE001 - toute erreur d'outil devient un résultat
            return ToolResult(f"error: {type(exc).__name__}: {exc}", True)


def _describe_invalid(exc: jsonschema.ValidationError) -> str:
    """Message qui nomme l'argument fautif et la forme attendue (ADR-0009 §7)."""
    name = ""
    for part in exc.absolute_path:
        name += (
            f"[{part}]" if isinstance(part, int) else f".{part}" if name else str(part)
        )
    if not name:
        return f"error: invalid arguments: {exc.message}"
    if exc.validator == "type":
        got = json.dumps(exc.instance, ensure_ascii=False)
        return f"error: invalid argument '{name}': expected {exc.validator_value}, got {got}"
    return f"error: invalid argument '{name}': {exc.message}"

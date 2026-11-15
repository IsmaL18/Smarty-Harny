"""Contrat des outils et point d'exécution unique (ADR-0002).

Notion : tool-calling (docs/notions/tool-calling.md).

Principe central : une erreur d'outil est un *résultat* renvoyé au modèle, pas une
exception. `ToolRegistry.execute` garantit donc exactement un `ToolResult` par appel,
quoi qu'il arrive (outil inconnu, JSON illisible, arguments invalides, exception).
Seule `CancelledError` (Ctrl+C, ADR-0005) traverse : c'est la boucle qui la traite.
"""

import json
from dataclasses import dataclass
from typing import Protocol

import jsonschema

from harness.tools.environment import Environment


@dataclass(frozen=True)
class ToolResult:
    content: str
    is_error: bool


class Tool(Protocol):
    name: str
    description: str
    parameters: dict  # schéma JSON des paramètres, écrit à la main (ADR-0002 §1)

    async def run(self, args: dict, env: Environment) -> ToolResult: ...


class ToolRegistry:
    def __init__(self, tools: list[Tool], environment: Environment):
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
        try:
            jsonschema.validate(args, tool.parameters)
        except jsonschema.ValidationError as exc:
            return ToolResult(f"error: invalid arguments: {exc.message}", True)
        try:
            return await tool.run(args, self._environment)
        except Exception as exc:  # noqa: BLE001 - toute erreur d'outil devient un résultat
            return ToolResult(f"error: {type(exc).__name__}: {exc}", True)

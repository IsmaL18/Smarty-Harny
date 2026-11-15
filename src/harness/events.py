"""Événements typés émis par le noyau vers l'interface (ADR-0001, ADR-0008 §4).

Notion : boucle-agent (docs/notions/boucle-agent.md).
"""

from dataclasses import dataclass
from typing import Literal

from harness.models.base import ProviderError
from harness.tools.base import ToolResult

TurnEndReason = Literal[
    "done", "step_limit", "budget_limit", "interrupted", "provider_error"
]
LimitKind = Literal["step", "budget"]


@dataclass(frozen=True)
class ToolCallStarted:
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolCallFinished:
    name: str
    result: ToolResult


@dataclass(frozen=True)
class AssistantMessage:
    text: str


@dataclass(frozen=True)
class StepCompleted:
    usage: dict
    cost_usd: float | None


@dataclass(frozen=True)
class LimitReached:
    kind: LimitKind
    summary: str


@dataclass(frozen=True)
class ProviderFailed:
    error: ProviderError


@dataclass(frozen=True)
class TurnEnded:
    reason: TurnEndReason

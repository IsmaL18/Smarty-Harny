"""Protocole ModelClient : le seul contrat que le noyau connaît d'un fournisseur (ADR-0003).

Notion : abstraction-multi-provider.
"""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ModelResponse:
    message: dict  # message assistant au format OpenAI chat
    finish_reason: str
    usage: dict  # tokens entrée/sortie
    cost_usd: float | None  # None = coût inconnu (jamais 0, ADR-0004)


class ProviderError(Exception):
    def __init__(
        self,
        kind: Literal["auth", "unreachable", "context_too_long", "other"],
        message_fr: str,
    ):
        super().__init__(message_fr)
        self.kind = kind
        self.message_fr = message_fr


class ModelClient(Protocol):
    async def complete(
        self, messages: list[dict], tools: list[dict]
    ) -> ModelResponse: ...

    async def check(self) -> None:
        """Lève ProviderError si la clé manque ou le serveur est injoignable."""
        ...

"""CostTracker : coût cumulé de la session, prix inconnu compris (ADR-0004).

Notion : comptage-du-cout. Un coût inconnu (`None`) n'est jamais compté comme 0 :
il incrémente `unknown_calls` et ne consomme pas le budget.
"""

from dataclasses import dataclass


@dataclass
class CostTracker:
    known_usd: float = 0.0
    unknown_calls: int = 0
    known_calls: int = 0
    tokens: int = 0

    def add(self, cost_usd: float | None, usage: dict) -> None:
        if cost_usd is None:
            self.unknown_calls += 1
        else:
            self.known_calls += 1
            self.known_usd += cost_usd
        self.tokens += int(usage.get("prompt_tokens", 0)) + int(
            usage.get("completion_tokens", 0)
        )

    def display(self) -> str:
        """Texte affiché à l'utilisateur (ADR-0004 §5)."""
        if self.unknown_calls == 0:
            return f"coût : {format_usd(self.known_usd)}"
        if self.known_calls == 0:
            tokens = f"{self.tokens:,}".replace(",", " ")
            return f"coût : non estimé ({self.unknown_calls} appels, {tokens} tokens)"
        return (
            f"coût : {format_usd(self.known_usd)} + {self.unknown_calls} "
            f"appels non estimés"
        )


def format_usd(amount: float) -> str:
    return f"{amount:.4f}".replace(".", ",") + " $"

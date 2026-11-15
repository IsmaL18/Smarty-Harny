"""Coupe au milieu d'une sortie trop longue (ADR-0011 §1-§3).

Notion : context-engineering (docs/notions/).

Garder seulement le début d'une sortie perd ce qui compte le plus souvent : la fin
(dernière erreur, résumé de tests). On garde donc le début *et* la fin, à la limite de
lignes entières, et un en-tête dit précisément ce qui est omis et comment le lire.
"""

from dataclasses import dataclass
from typing import Literal

# Répartition début / fin du budget (constantes de code, ADR-0011 §1) :
# une commande échoue à la fin, un fichier se lit autant par le haut que par le bas.
COMMAND_HEAD_SHARE = 0.4
FILE_HEAD_SHARE = 0.5


@dataclass(frozen=True)
class Truncation:
    unit: Literal["lines", "characters"]
    first: int  # premier élément omis, à partir de 1
    last: int  # dernier élément omis
    total: int
    saved_path: str | None = None
    saved_incomplete: bool = False


def count_lines(text: str) -> int:
    return text.count("\n") + (0 if not text or text.endswith("\n") else 1)


def tail_size(budget: int, head_share: float) -> int:
    return budget - int(budget * head_share)


def cut_middle(
    first: str,
    window: str,
    total_chars: int,
    total_lines: int,
    budget: int,
    head_share: float,
) -> tuple[str, str, Truncation]:
    """Découpe début / fin d'une sortie de `total_chars` caractères (> budget).

    `first` contient au moins les premiers caractères de la sortie ; `window` au moins
    les `tail_size + 1` derniers (le caractère de plus sert à savoir si la fin commence
    sur une limite de ligne). On n'a donc pas besoin de garder la sortie entière.
    """
    head_budget = int(budget * head_share)
    tail_budget = tail_size(budget, head_share)
    head_raw = first[:head_budget]
    tail_raw = window[-tail_budget:] if tail_budget else ""
    before = window[-tail_budget - 1 : -tail_budget] if tail_budget else ""

    head = head_raw[: head_raw.rfind("\n") + 1]
    if before == "\n" or not tail_raw:
        tail = tail_raw
    else:
        tail = tail_raw[tail_raw.find("\n") + 1 :] if "\n" in tail_raw else ""

    if not head or not tail:
        # Une ligne plus grande que le budget (fichier minifié) : coupe au caractère.
        return (
            head_raw,
            tail_raw,
            Truncation(
                "characters",
                len(head_raw) + 1,
                total_chars - len(tail_raw),
                total_chars,
            ),
        )
    kept_head = count_lines(head)
    kept_tail = count_lines(tail)
    return (
        head,
        tail,
        Truncation("lines", kept_head + 1, total_lines - kept_tail, total_lines),
    )


def cut_text(
    text: str, budget: int, head_share: float
) -> tuple[str, str, Truncation] | None:
    """`cut_middle` pour un texte déjà entièrement en mémoire ; None s'il tient."""
    if len(text) <= budget:
        return None
    window = text[-(tail_size(budget, head_share) + 1) :]
    return cut_middle(text, window, len(text), count_lines(text), budget, head_share)


def header(truncation: Truncation, kind: Literal["file", "command"]) -> str:
    """En-tête inséré entre le début et la fin. Les marqueurs sont stables (ADR-0011 §2)."""
    t = truncation
    omitted = f"{t.unit} {t.first}-{t.last} of {t.total} omitted"
    if t.saved_path:
        how = f"full output saved in {t.saved_path}"
        if t.unit == "lines":
            how += f" (read it with read_file, offset={t.first}, limit=...)"
        if t.saved_incomplete:
            how += "; the saved file stops at the disk cap and is incomplete"
    elif kind == "file" and t.unit == "lines":
        how = f"read them with read_file (offset={t.first}, limit=...)"
    elif kind == "file":
        how = "the line is too long to read by range; use the shell (cut, head -c)"
    else:
        how = "no saved copy"
    return f"[TRUNCATED: {omitted} — {how}]"


def assemble(head: str, marker: str, tail: str) -> str:
    separator = "" if not head or head.endswith("\n") else "\n"
    return f"{head}{separator}{marker}\n{tail}"

"""Outil edit_file : remplacements de texte exact dans un fichier lu (ADR-0010).

Notion : tool-calling (docs/notions/tool-calling.md).

Garde-fous, dans l'ordre : dossier réservé, fichier lisible et texte, fichier lu au
préalable et inchangé depuis, puis chaque `old_text` apparié (exact d'abord, tolérant
ensuite). Tout ou rien : un seul remplacement refusé et le fichier n'est pas touché.
"""

import difflib
import re
from dataclasses import dataclass
from itertools import pairwise

from harness.tools.base import ToolResult
from harness.tools.environment import Environment
from harness.tools.filestate import (
    RESERVED_MESSAGE,
    FileTracker,
    decode_text,
    is_reserved,
)

_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "File path"},
        "edits": {
            "type": "array",
            "description": (
                "Replacements, each matched against the file as it was before this call"
            ),
            "items": {
                "type": "object",
                "properties": {
                    "old_text": {
                        "type": "string",
                        "description": "Text to replace; must match exactly one place",
                    },
                    "new_text": {"type": "string", "description": "Replacement text"},
                },
                "required": ["old_text", "new_text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["path", "edits"],
    "additionalProperties": False,
}

_QUOTES = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "−": "-",
    }
)


@dataclass(frozen=True)
class _Normalized:
    text: str
    starts: list[int]  # début, dans l'original, du caractère normalisé i
    ends: list[int]  # fin (exclue) dans l'original


def _normalize(text: str) -> _Normalized:
    """Texte débarrassé de ce qui varie sans changer le sens, avec la table de positions.

    CRLF → LF ; espaces et tabulations de fin de ligne retirés ; guillemets et tirets
    typographiques → ASCII ; indentation retirée (ADR-0010 §8). Chaque caractère gardé
    sait d'où il vient, pour reporter une correspondance sur l'original.
    """
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    position = 0
    for raw in re.split(r"(?<=\n)", text):
        if not raw:
            continue
        has_newline = raw.endswith("\n")
        body = raw[:-1] if has_newline else raw
        if has_newline and body.endswith("\r"):
            body = body[:-1]
        stripped = body.strip(" \t")
        if stripped:
            lead = len(body) - len(body.lstrip(" \t"))
            for i, char in enumerate(stripped):
                out.append(char.translate(_QUOTES))
                starts.append(position + lead + i)
                ends.append(position + lead + i + 1)
            ends[-1] = position + len(
                body
            )  # les espaces de fin suivent le dernier caractère
            newline_start = position + len(body)
        else:
            newline_start = position
        if has_newline:
            out.append("\n")
            starts.append(newline_start)
            ends.append(position + len(raw))
        position += len(raw)
    return _Normalized("".join(out), starts, ends)


def _occurrences(haystack: str, needle: str) -> list[int]:
    found = []
    index = haystack.find(needle)
    while index != -1:
        found.append(index)
        index = haystack.find(needle, index + 1)
    return found


def _on_line_boundaries(text: str, start: int, needle: str) -> bool:
    end = start + len(needle)
    starts_line = start == 0 or text[start - 1] == "\n"
    ends_line = needle.endswith("\n") or end == len(text) or text[end] == "\n"
    return starts_line and ends_line


@dataclass(frozen=True)
class _Match:
    start: int
    end: int
    tolerant: bool


class _Refusal(Exception):
    pass


def _find(text: str, normalized: _Normalized, old_text: str, rank: int) -> _Match:
    exact = _occurrences(text, old_text)
    if len(exact) == 1:  # une correspondance exacte unique l'emporte toujours
        return _Match(exact[0], exact[0] + len(old_text), tolerant=False)
    if len(exact) > 1:
        raise _Refusal(_ambiguous(rank, len(exact)))
    needle = _normalize(old_text).text
    found = _occurrences(normalized.text, needle) if needle.strip() else []
    if "\n" in needle:
        # Un old_text multi-ligne désigne des lignes entières : un appariement qui
        # commence ou finit en milieu de ligne remplacerait un morceau de ligne et
        # recollerait les lignes voisines (ADR-0010 §8).
        found = [i for i in found if _on_line_boundaries(normalized.text, i, needle)]
    if not found:
        raise _Refusal(
            f"error: edit {rank}: old_text not found in the file; read the file again "
            "and copy the text exactly"
        )
    if len(found) > 1:
        raise _Refusal(_ambiguous(rank, len(found)))
    first = found[0]
    last = first + len(needle) - 1
    return _Match(normalized.starts[first], normalized.ends[last], tolerant=True)


def _ambiguous(rank: int, count: int) -> str:
    return (
        f"error: edit {rank}: old_text matches {count} places in the file; "
        "include more surrounding lines so that it matches exactly one"
    )


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _adapt_new_text(text: str, match: _Match, old_text: str, new_text: str) -> str:
    """Indentation du nouveau texte après un appariement tolérant (ADR-0010 §10)."""
    old_lines = old_text.replace("\r\n", "\n").split("\n")
    new_lines = new_text.replace("\r\n", "\n").split("\n")
    line_start = text.rfind("\n", 0, match.start) + 1
    prefix = text[line_start : match.start]
    table: dict[str, str] = {}
    if not prefix.strip(" \t"):
        # La correspondance commence après l'indentation du fichier : elle reste en place.
        old_first = _indent(old_lines[0])
        table[old_first] = prefix
        new_lines[0] = new_lines[0].removeprefix(old_first)
    matched_lines = text[match.start : match.end].split("\n")
    if len(matched_lines) == len(old_lines):
        for old_line, file_line in zip(old_lines[1:], matched_lines[1:], strict=True):
            if old_line.strip() and file_line.strip():
                table.setdefault(_indent(old_line), _indent(file_line))
    if all(old == new for old, new in table.items()):
        return "\n".join(new_lines)
    for i in range(1, len(new_lines)):
        line = new_lines[i]
        if not line.strip():
            continue
        indent = _indent(line)
        known = [key for key in table if indent.startswith(key)]
        if known:
            key = max(known, key=len)
            new_lines[i] = table[key] + line[len(key) :]
    return "\n".join(new_lines)


def _uses_crlf(text: str) -> bool:
    crlf = text.count("\r\n")
    return crlf > 0 and crlf >= text.count("\n") - crlf


class EditFile:
    name = "edit_file"
    description = (
        "Replace exact text in an existing file you have already read (with read_file). "
        "Pass a list of edits, each {old_text, new_text}; every old_text is searched in "
        "the file as it was before this call and must match exactly one place, so include "
        "enough surrounding lines. All edits are applied or none. Minor differences in "
        "indentation, trailing spaces, line endings or typographic quotes are tolerated."
    )
    parameters = _PARAMETERS

    def __init__(self, tracker: FileTracker):
        self._tracker = tracker

    async def run(self, args: dict, env: Environment) -> ToolResult:
        path = args["path"]
        if is_reserved(env, path):
            return ToolResult(RESERVED_MESSAGE, True)
        try:
            data = await env.read_bytes(path)
        except OSError as exc:
            return ToolResult(f"error: {exc.strerror or exc}: {path}", True)
        text = decode_text(data)
        if text is None:
            return ToolResult("error: binary file, not edited", True)
        verdict = self._tracker.check(env, path, data)
        if verdict == "unread":
            return ToolResult(
                f"error: {path} has not been read yet; read it with read_file before editing",
                True,
            )
        if verdict == "changed":
            return ToolResult(
                f"error: {path} changed since you read it; read it again with read_file "
                "before editing",
                True,
            )
        edits = args["edits"]
        if not edits:
            return ToolResult("error: edits is empty; give at least one edit", True)
        try:
            new_text = self._apply(text, edits)
        except _Refusal as refusal:
            return ToolResult(str(refusal), True)

        new_data = new_text.encode("utf-8")
        await env.write_bytes(path, new_data)
        await self._tracker.record(env, path, new_data)
        count = len(edits)
        diff = "\n".join(
            difflib.unified_diff(
                text.splitlines(), new_text.splitlines(), path, path, n=1, lineterm=""
            )
        )
        return ToolResult(
            f"edited {path}: {count} replacement{'s' if count > 1 else ''}",
            False,
            title=f"{path} : {count} remplacement{'s' if count > 1 else ''}",
            detail=diff,
        )

    def _apply(self, text: str, edits: list[dict]) -> str:
        normalized = _normalize(text)
        crlf = _uses_crlf(text)
        matches: list[tuple[int, _Match, str]] = []
        for rank, edit in enumerate(edits, start=1):
            old_text, new_text = edit["old_text"], edit["new_text"]
            if not old_text:
                raise _Refusal(f"error: edit {rank}: old_text is empty")
            if old_text == new_text:
                raise _Refusal(
                    f"error: edit {rank}: old_text and new_text are identical"
                )
            match = _find(text, normalized, old_text, rank)
            if match.tolerant:
                new_text = _adapt_new_text(text, match, old_text, new_text)
            if crlf:
                new_text = new_text.replace("\r\n", "\n").replace("\n", "\r\n")
            matches.append((rank, match, new_text))

        ordered = sorted(matches, key=lambda item: item[1].start)
        for (rank_a, a, _), (rank_b, b, _) in pairwise(ordered):
            if b.start < a.end:
                low, high = sorted((rank_a, rank_b))
                raise _Refusal(
                    f"error: edits {low} and {high} overlap; merge them into one edit"
                )
        # De la fin vers le début : les positions des remplacements restants ne bougent pas.
        for _, match, replacement in reversed(ordered):
            text = text[: match.start] + replacement + text[match.end :]
        return text

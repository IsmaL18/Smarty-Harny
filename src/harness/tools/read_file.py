"""Outil read_file (ADR-0002 §3, ADR-0011 §1-§4) : fichier entier ou plage de lignes."""

from dataclasses import replace

from harness.tools.base import ToolResult
from harness.tools.environment import Environment
from harness.tools.filestate import FileTracker, decode_text, split_lines
from harness.tools.truncate import FILE_HEAD_SHARE, assemble, cut_text, header

_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "File path"},
        "offset": {
            "type": "integer",
            "minimum": 1,
            "description": "First line to read, numbered from 1",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "description": "Maximum number of lines to read",
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}


class ReadFile:
    name = "read_file"
    description = (
        "Read a text file and return its content. Relative paths start from the working "
        "directory. Use offset and limit to read a range of lines. Binary files are "
        "refused; long output is cut in the middle (start and end are kept) and the "
        "header says which lines to read next."
    )
    parameters = _PARAMETERS

    def __init__(self, max_read_chars: int, tracker: FileTracker):
        self._max_read_chars = max_read_chars
        self._tracker = tracker

    async def run(self, args: dict, env: Environment) -> ToolResult:
        path = args["path"]
        try:
            data = await env.read_bytes(path)
        except OSError as exc:
            return ToolResult(f"error: {exc.strerror or exc}: {path}", True)
        text = decode_text(data)
        if text is None:
            return ToolResult("error: binary file, not read", True)
        # Toute lecture compte, même tronquée ou par plage (ADR-0010 §3).
        await self._tracker.record(env, path, data)

        offset, limit = args.get("offset"), args.get("limit")
        lines = split_lines(text)
        total = len(lines)
        base = 0
        selected: list[str] = []
        ranged = offset is not None or limit is not None
        if ranged:
            start = offset or 1
            if start > total:
                return ToolResult(
                    f"error: offset {start} is beyond the end of the file "
                    f"({total} lines)",
                    True,
                )
            selected = lines[start - 1 : start - 1 + limit if limit else None]
            base = start - 1
            text = "".join(selected)

        cut = cut_text(text, self._max_read_chars, FILE_HEAD_SHARE)
        if cut is not None:
            head, tail, truncation = cut
            if truncation.unit == "lines":
                truncation = replace(
                    truncation,
                    first=truncation.first + base,
                    last=truncation.last + base,
                    total=total if ranged else truncation.total,
                )
            return ToolResult(assemble(head, header(truncation, "file"), tail), False)
        if ranged:
            end = base + len(selected)
            if text and not text.endswith("\n"):
                text += "\n"
            return ToolResult(f"{text}[lines {base + 1}-{end} of {total}]", False)
        return ToolResult(text, False)

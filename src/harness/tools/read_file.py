"""Outil read_file (ADR-0002 §3)."""

from harness.tools.base import ToolResult
from harness.tools.environment import Environment

BINARY_SNIFF_BYTES = 8192


_PARAMETERS = {
    "type": "object",
    "properties": {"path": {"type": "string", "description": "File path"}},
    "required": ["path"],
    "additionalProperties": False,
}


class ReadFile:
    name = "read_file"
    description = (
        "Read a text file and return its content. Relative paths start from the working "
        "directory. Binary files are refused; long files are truncated."
    )
    parameters = _PARAMETERS

    def __init__(self, max_read_chars: int):
        self._max_read_chars = max_read_chars

    async def run(self, args: dict, env: Environment) -> ToolResult:
        try:
            data = await env.read_bytes(args["path"])
        except OSError as exc:
            return ToolResult(f"error: {exc.strerror or exc}: {args['path']}", True)
        if b"\x00" in data[:BINARY_SNIFF_BYTES]:
            return ToolResult("error: binary file, not read", True)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ToolResult("error: binary file, not read", True)
        if len(text) > self._max_read_chars:
            shown = text[: self._max_read_chars]
            marker = (
                f"[TRUNCATED: showing first {len(shown)} of {len(text)} characters]"
            )
            return ToolResult(f"{shown}\n{marker}", False)
        return ToolResult(text, False)

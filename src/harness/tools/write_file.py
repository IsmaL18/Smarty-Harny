"""Outil write_file (ADR-0002 §3) : écrit un fichier entier, crée les dossiers, écrase."""

from harness.tools.base import ToolResult
from harness.tools.environment import Environment
from harness.tools.filestate import RESERVED_MESSAGE, FileTracker, is_reserved

_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "File path"},
        "content": {"type": "string", "description": "Complete new content"},
    },
    "required": ["path", "content"],
    "additionalProperties": False,
}


class WriteFile:
    name = "write_file"
    description = (
        "Write a whole file (parent folders are created, an existing file is overwritten "
        "without asking). Relative paths start from the working directory."
    )
    parameters = _PARAMETERS

    def __init__(self, tracker: FileTracker):
        self._tracker = tracker

    async def run(self, args: dict, env: Environment) -> ToolResult:
        if is_reserved(env, args["path"]):
            return ToolResult(RESERVED_MESSAGE, True)
        content = args["content"]
        data = content.encode("utf-8")
        try:
            await env.write_bytes(args["path"], data)
        except OSError as exc:
            return ToolResult(f"error: {exc.strerror or exc}: {args['path']}", True)
        # Un fichier écrit en entier par l'agent se modifie sans relecture (ADR-0010 §3).
        await self._tracker.record(env, args["path"], data)
        return ToolResult(f"wrote {len(content)} characters to {args['path']}", False)

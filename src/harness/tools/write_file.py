"""Outil write_file (ADR-0002 §3) : écrit un fichier entier, crée les dossiers, écrase."""

from harness.tools.base import ToolResult
from harness.tools.environment import Environment

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

    async def run(self, args: dict, env: Environment) -> ToolResult:
        content = args["content"]
        try:
            await env.write_bytes(args["path"], content.encode("utf-8"))
        except OSError as exc:
            return ToolResult(f"error: {exc.strerror or exc}: {args['path']}", True)
        return ToolResult(f"wrote {len(content)} characters to {args['path']}", False)

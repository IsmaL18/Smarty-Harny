"""Outil shell (ADR-0002 §3, §6) : `bash -c`, sans état entre deux appels."""

from harness.tools.base import ToolResult
from harness.tools.environment import Environment
from harness.tools.filestate import FileTracker
from harness.tools.outputs import OutputStore
from harness.tools.truncate import assemble, header

_PARAMETERS = {
    "type": "object",
    "properties": {"command": {"type": "string", "description": "Command line"}},
    "required": ["command"],
    "additionalProperties": False,
}


class Shell:
    name = "shell"
    description = (
        "Run a shell command with bash in the working directory. stdin is closed, stderr is "
        "merged into stdout, and no state persists between calls (a `cd` does not survive). "
        "Long output is cut in the middle (start and end are kept) and the full output is "
        "saved to a file named in the header; commands are killed after a timeout."
    )
    parameters = _PARAMETERS

    def __init__(
        self, command_timeout_s: float, tracker: FileTracker, store: OutputStore
    ):
        self._timeout = command_timeout_s
        self._tracker = tracker
        self._store = store

    async def run(self, args: dict, env: Environment) -> ToolResult:
        # Les fichiers que la commande modifie ne doivent pas bloquer la modification
        # suivante, mais un changement extérieur antérieur reste signalé (ADR-0010 §5).
        clean = await self._tracker.clean_files(env)
        try:
            outcome = await env.run(args["command"], self._timeout, self._store)
        finally:
            await self._tracker.absorb(env, clean)
        text = outcome.text
        if outcome.truncation is not None:
            text = assemble(text, header(outcome.truncation, "command"), outcome.tail)
        parts = [text]
        if outcome.timed_out:
            parts.append(f"[TIMEOUT: killed after {self._timeout:g}s]")
            return ToolResult("\n".join(parts), True)
        parts.append(f"[exit code: {outcome.exit_code}]")
        return ToolResult("\n".join(parts), outcome.exit_code != 0)

"""Outil shell (ADR-0002 §3, §6) : `bash -c`, sans état entre deux appels."""

from harness.tools.base import ToolResult
from harness.tools.environment import Environment

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
        "Long output is truncated; commands are killed after a timeout."
    )
    parameters = _PARAMETERS

    def __init__(self, command_timeout_s: float):
        self._timeout = command_timeout_s

    async def run(self, args: dict, env: Environment) -> ToolResult:
        outcome = await env.run(args["command"], self._timeout)
        parts = [outcome.output]
        if outcome.discarded_chars:
            parts.append(
                f"[TRUNCATED: showing first {len(outcome.output)} characters, "
                f"{outcome.discarded_chars} more omitted]"
            )
        if outcome.timed_out:
            parts.append(f"[TIMEOUT: killed after {self._timeout:g}s]")
            return ToolResult("\n".join(parts), True)
        parts.append(f"[exit code: {outcome.exit_code}]")
        return ToolResult("\n".join(parts), outcome.exit_code != 0)

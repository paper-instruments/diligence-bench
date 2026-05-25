"""Shell capability with a default per-call output cap.

Without a cap, an agent can `cat large_file.html` (or pipe a multi-MB filing
through `python -c`) and the entire blob is returned into the conversation,
blowing past the model's context window on the next turn. The SDK's
ExecCommandTool already supports `max_output_tokens` per call, but defaults
to None (unlimited) — so we inject a default when the model omits it.
"""

from __future__ import annotations

import json

from agents.sandbox.capabilities.shell import ShellToolSet
from agents.sandbox.capabilities.tools.shell_tool import ExecCommandTool, WriteStdinTool

DEFAULT_EXEC_MAX_OUTPUT_TOKENS = 8000


def configure_shell(toolset: ShellToolSet) -> None:
    """Install default `max_output_tokens` on exec_command and write_stdin."""
    _install_default_cap(toolset.exec_command, DEFAULT_EXEC_MAX_OUTPUT_TOKENS)
    if toolset.write_stdin is not None:
        _install_default_cap(toolset.write_stdin, DEFAULT_EXEC_MAX_OUTPUT_TOKENS)


def _install_default_cap(tool: ExecCommandTool | WriteStdinTool, default_cap: int) -> None:
    original_invoke = tool._invoke

    async def _invoke(ctx: object, raw_input: str) -> str:
        try:
            payload = json.loads(raw_input) if raw_input else {}
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and payload.get("max_output_tokens") is None:
            payload["max_output_tokens"] = default_cap
            raw_input = json.dumps(payload)
        try:
            return await original_invoke(ctx, raw_input)
        except Exception as exc:
            return f"Error running tool {tool.name}: {exc}"

    tool._invoke = _invoke  # type: ignore[method-assign]
    tool.on_invoke_tool = _invoke  # type: ignore[assignment]

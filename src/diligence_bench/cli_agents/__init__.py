"""Vanilla CLI-agent registry.

Each entry is a coroutine that runs the agent's CLI as a subprocess against an
instruction text in a workspace directory. The registry is parallel to
`diligence_bench.agents` (which holds OpenAI Agents SDK SandboxAgent builders);
the runner dispatches based on which registry the agent name comes from.

Contract:
    async def run(
        instruction: str,
        model: str,
        workdir: Path,
        *,
        timeout: float,
    ) -> CliAgentResult

`CliAgentResult.answer` is the agent's final memo (the contents of
`workdir / "answer.md"` if present, otherwise the CLI's stdout).
"""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from typing import Protocol

from diligence_bench.cli_agents.base import CliAgentResult
from diligence_bench.cli_agents.claude_code import run as run_claude_code
from diligence_bench.cli_agents.codex import run as run_codex
from diligence_bench.cli_agents.gemini import run as run_gemini


class CliAgentRunner(Protocol):
    def __call__(
        self,
        instruction: str,
        model: str,
        workdir: Path,
        *,
        timeout: float,
    ) -> Awaitable[CliAgentResult]: ...


CLI_AGENTS: dict[str, CliAgentRunner] = {
    "claude-code": run_claude_code,
    "codex": run_codex,
    "gemini": run_gemini,
}

__all__ = ["CLI_AGENTS", "CliAgentResult", "CliAgentRunner"]

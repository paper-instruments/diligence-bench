"""Sandbox harness (H2): generic CLI-style agent with shell + file ops."""

from __future__ import annotations

from pathlib import Path

from agents.mcp import MCPServer, MCPServerStdio
from agents.sandbox import SandboxAgent
from agents.sandbox.capabilities import Shell

from diligence_bench.agents._mcp import mcp_stdio_params, tool_spec
from diligence_bench.agents._shell_caps import configure_shell

_DIR = Path(__file__).parent
_SYSTEM_PROMPT_PATH = _DIR / "system_prompt.md"
_MCP_TOOL_IDS = ("web_search",)


def build_agent(workdir: Path) -> SandboxAgent:
    from diligence_bench.tools.apply_patch import apply_patch

    mcp_servers: list[MCPServer] = [
        MCPServerStdio(
            name=tool_id,
            params=mcp_stdio_params(tool_id, tool_spec(tool_id)),
            client_session_timeout_seconds=30.0,
        )
        for tool_id in _MCP_TOOL_IDS
    ]

    return SandboxAgent(
        name="diligence-bench-sandbox",
        instructions=_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip(),
        tools=[apply_patch],
        mcp_servers=mcp_servers,
        capabilities=[
            Shell(configure_tools=configure_shell),
        ],
    )


__all__ = ["build_agent"]

"""Loop harness (H1): bare baseline with web tools and final_answer only."""

from __future__ import annotations

from pathlib import Path

from agents.mcp import MCPServer, MCPServerStdio
from agents.sandbox import SandboxAgent

from diligence_bench.agents._mcp import mcp_stdio_params, tool_spec

_DIR = Path(__file__).parent
_SYSTEM_PROMPT_PATH = _DIR / "system_prompt.md"
_MCP_TOOL_IDS = ("web_search",)


def build_agent(workdir: Path) -> SandboxAgent:
    from diligence_bench.tools.final_answer import final_answer

    mcp_servers: list[MCPServer] = [
        MCPServerStdio(
            name=tool_id,
            params=mcp_stdio_params(tool_id, tool_spec(tool_id)),
            client_session_timeout_seconds=30.0,
        )
        for tool_id in _MCP_TOOL_IDS
    ]

    return SandboxAgent(
        name="diligence-bench-loop",
        instructions=_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip(),
        tools=[final_answer],
        mcp_servers=mcp_servers,
        capabilities=[],
    )


__all__ = ["build_agent"]

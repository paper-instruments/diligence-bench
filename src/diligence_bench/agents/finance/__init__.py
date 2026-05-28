"""Finance harness (H3): SEC filing tools and domain prompt."""

from __future__ import annotations

from pathlib import Path

from agents.mcp import MCPServer, MCPServerStdio
from agents.sandbox import SandboxAgent
from agents.sandbox.capabilities import Shell

from diligence_bench.agents._mcp import mcp_stdio_params, tool_spec
from diligence_bench.agents._shell_caps import configure_shell

_DIR = Path(__file__).parent
_SYSTEM_PROMPT_PATH = _DIR / "system_prompt.md"
_AGENTS_PATH = _DIR / "AGENTS.md"
_MCP_TOOL_IDS = ("sec_edgar", "web_search")
_SEC_EDGAR_TOOLS = [
    "sec_filings",
    "sec_filing_content",
    "sec_financials",
    "sec_resolve_company",
    "sec_filing_search",
]


def build_agent(workdir: Path) -> SandboxAgent:
    from diligence_bench.tools.apply_patch import apply_patch

    mcp_servers: list[MCPServer] = [
        MCPServerStdio(
            name=tool_id,
            params=mcp_stdio_params(tool_id, tool_spec(tool_id)),
            tool_filter={"allowed_tool_names": _SEC_EDGAR_TOOLS}
            if tool_id == "sec_edgar"
            else None,
            client_session_timeout_seconds=30.0,
        )
        for tool_id in _MCP_TOOL_IDS
    ]

    return SandboxAgent(
        name="diligence-bench-finance",
        instructions=_instructions(),
        tools=[apply_patch],
        mcp_servers=mcp_servers,
        capabilities=[Shell(configure_tools=configure_shell)],
    )


def _instructions() -> str:
    parts = [_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()]
    if _AGENTS_PATH.exists():
        parts.append("# Always-loaded Rules\n\n" + _AGENTS_PATH.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts)


__all__ = ["build_agent"]

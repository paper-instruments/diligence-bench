"""Web search MCP server launch spec."""

from __future__ import annotations

import sys
from pathlib import Path


def mcp_stdio_spec() -> dict[str, object]:
    """Return the stdio launch spec for the web search MCP server."""

    return {
        "command": sys.executable,
        "args": [str(Path(__file__).parent / "server.py")],
        "env_allowlist": [
            "EXA_API_KEY",
            "TOOL_OUTPUT_CHAR_BUDGET",
            "WEB_SEARCH_CACHE_SIZE",
            "PATH",
            "HOME",
        ],
    }


__all__ = ["mcp_stdio_spec"]

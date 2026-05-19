"""SEC EDGAR MCP server launch spec."""

from __future__ import annotations

import sys
from pathlib import Path


def mcp_stdio_spec() -> dict[str, object]:
    """Return the stdio launch spec for the SEC EDGAR MCP server."""

    return {
        "command": sys.executable,
        "args": [str(Path(__file__).parent / "server.py")],
        "env_allowlist": [
            "SEC_USER_AGENT",
            "TOOL_OUTPUT_CHAR_BUDGET",
            "SEC_EDGAR_CACHE_SIZE",
            "PATH",
            "HOME",
        ],
    }


__all__ = ["mcp_stdio_spec"]

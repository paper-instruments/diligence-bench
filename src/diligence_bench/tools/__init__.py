"""Tool server registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from diligence_bench.tools.sec_edgar import mcp_stdio_spec as sec_edgar_mcp_stdio_spec
from diligence_bench.tools.web_search import mcp_stdio_spec as web_search_mcp_stdio_spec


class ToolSpecFactory(Protocol):
    def __call__(self) -> dict[str, object]: ...

    def mcp_stdio_spec(self) -> dict[str, object]: ...


class _ToolSpec:
    def __init__(self, factory: Callable[[], dict[str, object]]) -> None:
        self._factory = factory

    def mcp_stdio_spec(self) -> dict[str, object]:
        return self._factory()

    def __call__(self) -> dict[str, object]:
        return self.mcp_stdio_spec()


TOOLS: dict[str, ToolSpecFactory] = {
    "sec_edgar": _ToolSpec(sec_edgar_mcp_stdio_spec),
    "web_search": _ToolSpec(web_search_mcp_stdio_spec),
}


def get_mcp_spec(tool_id: str) -> dict[str, object]:
    """Return a fresh MCP stdio spec for a registered tool id."""

    try:
        return TOOLS[tool_id]()
    except KeyError as exc:
        available = ", ".join(TOOLS)
        raise KeyError(f"Unknown MCP tool {tool_id!r}. Available tools: {available}") from exc


__all__ = ["TOOLS", "ToolSpecFactory", "get_mcp_spec"]

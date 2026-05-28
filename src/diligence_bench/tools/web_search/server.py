from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import sys
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

DEFAULT_CACHE_SIZE = 1000
DEFAULT_TOOL_OUTPUT_CHAR_BUDGET = 8000
TRUNCATION_SENTINEL = "... [truncated; use bash with grep -A/-B /path to inspect]"
WORKSPACE_ROOT = "/workspace"


class WebSearchClient(Protocol):
    async def search(self, query: str, k: int) -> list[dict[str, Any]]:
        """Return normalized web search results."""


class ExaWebSearchClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("EXA_API_KEY", "")
        if not self._api_key:
            raise RuntimeError("EXA_API_KEY is required for web_search")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def search(self, query: str, k: int) -> list[dict[str, Any]]:
        response = await self._client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": self._api_key, "content-type": "application/json"},
            json={"query": query, "numResults": k},
        )
        response.raise_for_status()
        return [_normalize_result(item) for item in response.json().get("results", [])]

    async def close(self) -> None:
        await self._client.aclose()


class MissingWebSearchClient:
    async def search(self, query: str, k: int) -> list[dict[str, Any]]:
        del query, k
        raise RuntimeError("EXA_API_KEY is required for web_search")


class _LRUCache:
    def __init__(self, max_size: int) -> None:
        self._max_size = max(max_size, 1)
        self._items: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any | None:
        if key not in self._items:
            return None
        value = self._items.pop(key)
        self._items[key] = value
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._items:
            self._items.pop(key)
        self._items[key] = value
        if len(self._items) > self._max_size:
            self._items.popitem(last=False)


@dataclass
class _ServerContext:
    web_search_client: WebSearchClient
    search_cache: _LRUCache
    fetch_cache: _LRUCache
    tool_output_char_budget: int

    async def close(self) -> None:
        close = getattr(self.web_search_client, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result


_context: _ServerContext | None = None


@asynccontextmanager
async def _lifespan(server: FastMCP):
    del server
    try:
        yield _get_context()
    finally:
        if _context is not None:
            await _context.close()


mcp = FastMCP("web-search", lifespan=_lifespan)


@mcp.tool()
async def web_search(query: str, k: int = 5) -> str:
    """Search the web and return cached normalized results."""

    context = _get_context()
    cache_key = _cache_key(f"{query}\0{k}")
    cached = context.search_cache.get(cache_key)
    if cached is not None:
        return str(cached)

    try:
        results = await context.web_search_client.search(query, k)
        bounded = [
            {
                **result,
                "snippet": _truncate(
                    str(result.get("snippet", "")),
                    context.tool_output_char_budget,
                ),
            }
            for result in results[:k]
        ]
        payload = _truncate(json.dumps(bounded), context.tool_output_char_budget)
        context.search_cache.set(cache_key, payload)
        return payload
    except Exception as exc:
        logger.warning("web_search failed for query %s: %s", query, exc)
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def web_fetch(url: str, save_as: str) -> str:
    """Fetch a URL and return a preview of its content."""

    context = _get_context()
    workspace_path = _workspace_path(save_as)
    cache_key = _cache_key(url)

    try:
        cached = context.fetch_cache.get(cache_key)
        if cached is None:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": _web_fetch_user_agent(),
                    "Accept-Encoding": "gzip, deflate",
                },
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
            raw = response.content
            context.fetch_cache.set(cache_key, raw)
        else:
            raw = bytes(cached)

        saved = _should_write_workspace_file()
        if saved:
            _write_workspace_file(workspace_path, raw)
        text = raw.decode(errors="replace")
        return json.dumps(
            {
                "path": workspace_path if saved else None,
                "saved": saved,
                "size": len(raw),
                "first_chars": _truncate(text, context.tool_output_char_budget),
            }
        )
    except Exception as exc:
        logger.warning("web_fetch failed for url %s: %s", url, exc)
        return json.dumps({"error": str(exc)})


def main() -> None:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        sys.stdout.write("Run this module as a FastMCP stdio server.\n")
        return

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("httpx", "httpcore", "mcp", "mcp.server", "mcp.server.lowlevel.server"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    mcp.run(transport="stdio")


def build_web_search_client() -> WebSearchClient:
    try:
        return ExaWebSearchClient()
    except RuntimeError:
        return MissingWebSearchClient()


def _get_context() -> _ServerContext:
    global _context
    if _context is None:
        _context = _build_context_from_env()
    return _context


def _build_context_from_env() -> _ServerContext:
    cache_size = _parse_int_env("WEB_SEARCH_CACHE_SIZE", DEFAULT_CACHE_SIZE)
    return _ServerContext(
        web_search_client=build_web_search_client(),
        search_cache=_LRUCache(cache_size),
        fetch_cache=_LRUCache(cache_size),
        tool_output_char_budget=_parse_int_env(
            "TOOL_OUTPUT_CHAR_BUDGET",
            DEFAULT_TOOL_OUTPUT_CHAR_BUDGET,
        ),
    )


def _normalize_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "snippet": item.get("text") or item.get("snippet") or "",
        "published_date": item.get("publishedDate") or item.get("published_date"),
    }


def _truncate(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    return text[:budget] + TRUNCATION_SENTINEL


def _cache_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _workspace_path(save_as: str) -> str:
    relative = PurePosixPath(save_as.lstrip("/"))
    parts = [part for part in relative.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("save_as must be a relative path under /workspace")
    return str(PurePosixPath(WORKSPACE_ROOT).joinpath(*parts))


def _write_workspace_file(workspace_path: str, raw: bytes) -> None:
    target = Path(workspace_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def _should_write_workspace_file() -> bool:
    return os.getenv("DILIGENCE_BENCH_WEB_FETCH_WRITE") == "1"


def _web_fetch_user_agent() -> str:
    contact = os.getenv("SEC_USER_AGENT", "research@example.com")
    return f"Diligence Bench Research {contact}"


def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid integer env var %s=%s; using %d", name, raw, default)
        return default


if __name__ == "__main__":
    main()

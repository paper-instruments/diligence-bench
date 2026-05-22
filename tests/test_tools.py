from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from agents import FunctionTool


def test_registry_shape() -> None:
    from diligence_bench.tools import TOOLS, get_mcp_spec

    assert set(TOOLS) == {"sec_edgar", "web_search"}, f"Unexpected tool registry: {TOOLS}"
    for tool_id in TOOLS:
        spec = get_mcp_spec(tool_id)
        assert isinstance(spec["command"], str), f"{tool_id} command must be a string"
        assert isinstance(spec["args"], list), f"{tool_id} args must be a list"
        assert spec["args"], f"{tool_id} args must include the server path"
        assert Path(str(spec["args"][0])).exists(), f"{tool_id} server path does not exist"
        assert isinstance(
            spec["env_allowlist"],
            list,
        ), f"{tool_id} env_allowlist must be a list"

    sec_allowlist = cast(list[str], get_mcp_spec("sec_edgar")["env_allowlist"])
    web_allowlist = cast(list[str], get_mcp_spec("web_search")["env_allowlist"])
    assert "SEC_USER_AGENT" in sec_allowlist
    assert "EXA_API_KEY" in web_allowlist
    with pytest.raises(KeyError):
        get_mcp_spec("missing")


def test_final_answer_is_function_tool() -> None:
    from diligence_bench.tools.final_answer import FINAL_ANSWER_TOOL_NAME, final_answer

    assert FINAL_ANSWER_TOOL_NAME == "final_answer"
    assert isinstance(final_answer, FunctionTool), "final_answer must be an SDK function tool"
    assert final_answer.name == FINAL_ANSWER_TOOL_NAME


def test_final_answer_tool_schema_requires_memo() -> None:
    from diligence_bench.tools.final_answer import final_answer

    schema = cast(FunctionTool, final_answer).params_json_schema
    assert "memo" in schema.get("properties", {})
    assert "memo" in schema.get("required", [])


@pytest.mark.anyio
async def test_web_search_server_registers_expected_tools() -> None:
    from diligence_bench.tools.web_search import server

    tools = await server.mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert tool_names == {"web_search", "web_fetch"}


@pytest.mark.anyio
async def test_web_fetch_writes_saved_file(tmp_path, monkeypatch) -> None:
    from diligence_bench.tools.web_search import server

    monkeypatch.setenv("DILIGENCE_BENCH_WEB_FETCH_WRITE", "1")
    context = server._ServerContext(
        web_search_client=server.MissingWebSearchClient(),
        search_cache=server._LRUCache(10),
        fetch_cache=server._LRUCache(10),
        tool_output_char_budget=100,
    )
    context.fetch_cache.set(server._cache_key("https://example.test/report"), b"report body")
    monkeypatch.setattr(server, "_context", context)
    monkeypatch.setattr(server, "WORKSPACE_ROOT", str(tmp_path))

    payload = json.loads(await server.web_fetch("https://example.test/report", "data/report.txt"))

    assert payload["path"] == str(tmp_path / "data" / "report.txt")
    assert payload["saved"] is True
    assert (tmp_path / "data" / "report.txt").read_bytes() == b"report body"


@pytest.mark.anyio
async def test_web_fetch_does_not_claim_unsaved_workspace_file(tmp_path, monkeypatch) -> None:
    from diligence_bench.tools.web_search import server

    monkeypatch.delenv("DILIGENCE_BENCH_WEB_FETCH_WRITE", raising=False)
    context = server._ServerContext(
        web_search_client=server.MissingWebSearchClient(),
        search_cache=server._LRUCache(10),
        fetch_cache=server._LRUCache(10),
        tool_output_char_budget=100,
    )
    context.fetch_cache.set(server._cache_key("https://example.test/report"), b"report body")
    monkeypatch.setattr(server, "_context", context)
    monkeypatch.setattr(server, "WORKSPACE_ROOT", str(tmp_path))

    payload = json.loads(await server.web_fetch("https://example.test/report", "data/report.txt"))

    assert payload["path"] is None
    assert payload["saved"] is False
    assert not (tmp_path / "data" / "report.txt").exists()


def test_web_fetch_rejects_paths_outside_workspace() -> None:
    from diligence_bench.tools.web_search.server import _workspace_path

    with pytest.raises(ValueError, match="under /workspace"):
        _workspace_path("../escape.txt")


def test_bundle_tools_copies_canonical_sources_into_task_dir(tmp_path: Path) -> None:
    """The Harbor adapter copies tool sources from the canonical tools/ tree
    at build-tasks time. There is no checked-in second copy to drift."""
    from diligence_bench.harbor.adapter import TOOLS_DIR, _bundle_tools

    task_dir = tmp_path / "task"
    task_dir.mkdir()

    _bundle_tools(task_dir)

    for tool_id in ("sec_edgar", "web_search"):
        bundled_root = task_dir / "environment" / "diligence_bench" / "tools" / tool_id
        for source_file in (TOOLS_DIR / tool_id).rglob("*.py"):
            relative = source_file.relative_to(TOOLS_DIR / tool_id)
            bundled_file = bundled_root / relative
            assert bundled_file.exists(), f"missing {bundled_file}"
            assert bundled_file.read_bytes() == source_file.read_bytes(), bundled_file


@pytest.mark.anyio
async def test_sec_edgar_server_registers_expected_tools() -> None:
    from diligence_bench.tools.sec_edgar import server

    tools = await server.mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert tool_names == {
        "sec_filings",
        "sec_filing_content",
        "sec_financials",
        "sec_resolve_company",
        "sec_filing_search",
    }

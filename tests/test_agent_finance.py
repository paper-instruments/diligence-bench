from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from agents.mcp import MCPServerStdio
from agents.sandbox import SandboxAgent
from agents.sandbox.capabilities import Shell, Skills

from diligence_bench.agents import AGENTS
from diligence_bench.agents.finance import build_agent
from diligence_bench.tools import TOOLS


def test_agent_registry_exposes_three_harnesses() -> None:
    assert AGENTS["finance"] is build_agent
    assert {"loop", "sandbox", "finance"}.issubset(AGENTS), AGENTS.keys()


def test_build_agent_configures_finance_sandbox_agent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(
        TOOLS,
        "sec_edgar",
        lambda: {
            "launch_cmd": sys.executable,
            "launch_args": ["-m", "diligence_bench.tools.sec_edgar.server"],
            "env_allowlist": ["SEC_USER_AGENT"],
        },
    )
    monkeypatch.setitem(
        TOOLS,
        "web_search",
        lambda: {
            "command": sys.executable,
            "args": ["-m", "diligence_bench.tools.web_search.server"],
            "env": {"EXA_API_KEY": "test"},
        },
    )

    agent = build_agent(tmp_path)

    assert isinstance(agent, SandboxAgent)
    assert agent.name == "diligence-bench-finance"
    assert "senior equity-research analyst" in str(agent.instructions)
    tool_names = {tool.name for tool in agent.tools}
    assert "final_answer" not in tool_names
    assert "apply_patch" in tool_names

    assert len(agent.mcp_servers) == 2
    assert all(isinstance(server, MCPServerStdio) for server in agent.mcp_servers)
    assert [server.name for server in agent.mcp_servers] == ["sec_edgar", "web_search"]
    first_server = cast(MCPServerStdio, agent.mcp_servers[0])
    second_server = cast(MCPServerStdio, agent.mcp_servers[1])
    assert first_server.params.command == sys.executable
    assert second_server.params.env == {"EXA_API_KEY": "test"}

    assert any(isinstance(capability, Shell) for capability in agent.capabilities)
    assert not any(isinstance(capability, Skills) for capability in agent.capabilities)

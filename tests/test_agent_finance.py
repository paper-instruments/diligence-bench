from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from agents import function_tool
from agents.mcp import MCPServerStdio
from agents.sandbox import SandboxAgent
from agents.sandbox.capabilities import Shell, Skills
from agents.sandbox.entries import LocalDir

import diligence_bench.tools.final_answer as final_answer_module
from diligence_bench.agents import AGENTS
from diligence_bench.agents.finance import build_agent
from diligence_bench.tools import TOOLS


def test_agent_registry_exposes_three_harnesses() -> None:
    assert AGENTS["finance"] is build_agent
    assert {"loop", "sandbox", "finance"}.issubset(AGENTS), AGENTS.keys()


def test_build_agent_configures_finance_sandbox_agent(monkeypatch, tmp_path: Path) -> None:
    @function_tool
    def final_answer(text: str) -> str:
        """Record the final memo text."""
        return text

    monkeypatch.setattr(final_answer_module, "final_answer", final_answer, raising=False)
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
    assert "final_answer" in tool_names
    assert "apply_patch" in tool_names

    assert len(agent.mcp_servers) == 2
    assert all(isinstance(server, MCPServerStdio) for server in agent.mcp_servers)
    assert [server.name for server in agent.mcp_servers] == ["sec_edgar", "web_search"]
    first_server = cast(MCPServerStdio, agent.mcp_servers[0])
    second_server = cast(MCPServerStdio, agent.mcp_servers[1])
    assert first_server.params.command == sys.executable
    assert second_server.params.env == {"EXA_API_KEY": "test"}

    assert any(isinstance(capability, Shell) for capability in agent.capabilities)

    skills_capabilities = [
        capability for capability in agent.capabilities if isinstance(capability, Skills)
    ]
    assert len(skills_capabilities) == 1

    local_dir = cast(LocalDir, skills_capabilities[0].from_)
    skills_root = local_dir.src
    assert skills_root is not None
    skill_names = {path.parent.name for path in skills_root.glob("*/SKILL.md")}
    assert skill_names == {
        "equity-research-memo-format",
        "financial-claim-grounding",
        "risk-assessment-structure",
        "sec-filing-citation-discipline",
        "stop-slop",
    }

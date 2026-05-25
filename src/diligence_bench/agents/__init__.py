"""Reference agent registry."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from diligence_bench.agents.finance import build_agent as build_finance_agent
from diligence_bench.agents.loop import build_agent as build_loop_agent
from diligence_bench.agents.sandbox import build_agent as build_sandbox_agent

AgentBuilder = Callable[[Path], Any]

AGENTS: dict[str, AgentBuilder] = {
    "loop": build_loop_agent,
    "sandbox": build_sandbox_agent,
    "finance": build_finance_agent,
}

__all__ = ["AGENTS", "AgentBuilder"]

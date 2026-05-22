"""Reference agent registry."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from diligence_bench.agents.finance import build_agent as build_finance_agent
from diligence_bench.agents.finance_pro import build_agent as build_finance_pro_agent

AgentBuilder = Callable[[Path], Any]

AGENTS: dict[str, AgentBuilder] = {
    "finance": build_finance_agent,
    "finance-pro": build_finance_pro_agent,
}

__all__ = ["AGENTS", "AgentBuilder"]

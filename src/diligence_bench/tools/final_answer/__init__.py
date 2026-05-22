"""Final-answer function tool package.

The tool writes the agent's memo directly to ``/workspace/answer.md`` in the
run's sandbox. That file is the single source of truth for the grader; no
out-of-band fallback is needed when the agent calls this tool correctly.
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents import RunContextWrapper, function_tool

FINAL_ANSWER_TOOL_NAME = "final_answer"
ANSWER_PATH = Path("/workspace/answer.md")

logger = logging.getLogger(__name__)


@dataclass
class FinalAnswerContext:
    """Run-scoped context passed to the final_answer tool."""

    sandbox: Any


@function_tool(name_override=FINAL_ANSWER_TOOL_NAME)
async def final_answer(ctx: RunContextWrapper[FinalAnswerContext], memo: str) -> str:
    """Record your final memo. Call this exactly once when you are done; this writes the memo to /workspace/answer.md, which is what the grader reads."""

    if not memo or not memo.strip():
        return json.dumps(
            {
                "status": "rejected",
                "error": "memo is empty — pass your full analysis text as the memo argument",
            }
        )
    sandbox = getattr(ctx.context, "sandbox", None)
    if sandbox is None:
        logger.warning("final_answer called without a sandbox in context")
        return json.dumps({"status": "error", "reason": "sandbox unavailable"})
    await sandbox.write(ANSWER_PATH, io.BytesIO(memo.encode("utf-8")))
    return json.dumps({"status": "recorded"})


__all__ = ["FINAL_ANSWER_TOOL_NAME", "FinalAnswerContext", "ANSWER_PATH", "final_answer"]

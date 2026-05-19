"""Final-answer function tool package."""

from __future__ import annotations

import json

from agents import function_tool

FINAL_ANSWER_TOOL_NAME = "final_answer"


@function_tool(name_override=FINAL_ANSWER_TOOL_NAME)
async def final_answer(memo: str) -> str:
    """Record your final memo. Call this exactly once when you are done; the grader reads this text only if /workspace/answer.md is empty."""

    return final_answer_payload(memo)


def final_answer_payload(memo: str) -> str:
    return json.dumps({"status": "recorded", "memo": memo})


__all__ = ["FINAL_ANSWER_TOOL_NAME", "final_answer", "final_answer_payload"]

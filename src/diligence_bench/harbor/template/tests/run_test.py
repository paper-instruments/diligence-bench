"""Self-contained per-criterion verifier for Harbor task containers.

Runs inside the Harbor verifier container after the agent finishes. Reads the
agent's memo from `/workspace/answer.md` and the criterion list from
`/tests/rubric.json`, calls the LLM judge once via
`rubric.PerCriterionOneShotGrader` + `litellm`, and writes the weighted reward
to `/logs/verifier/reward.txt` plus per-criterion verdicts to
`/logs/verifier/judgments.json`.

The judge prompt is the rubric package default. The in-process runner shipped
with this benchmark uses the same package and the same prompt, so the two
verification paths are byte-identical.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path
from typing import Any

import litellm
from rubric import Rubric
from rubric.autograders import PerCriterionOneShotGrader
from rubric.autograders.schemas import OneShotOutput

ANSWER_PATH = Path("/workspace/answer.md")
RUBRIC_PATH = Path("/tests/rubric.json")
OUTPUT_DIR = Path("/logs/verifier")
INSTRUCTION_CANDIDATES = (Path("/instruction.md"), Path("/workspace/instruction.md"))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    answer = ANSWER_PATH.read_text(encoding="utf-8").strip() if ANSWER_PATH.exists() else ""
    criteria = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    if not isinstance(criteria, list) or not criteria:
        raise SystemExit("rubric.json must be a non-empty list of criteria")

    score, judgments = asyncio.run(_grade(answer, criteria, _instruction_text()))
    (OUTPUT_DIR / "reward.txt").write_text(f"{score:.6f}\n", encoding="utf-8")
    (OUTPUT_DIR / "judgments.json").write_text(
        json.dumps(judgments, indent=2) + "\n",
        encoding="utf-8",
    )


async def _grade(
    answer: str, criteria: list[dict[str, Any]], query: str
) -> tuple[float, list[dict[str, Any]]]:
    grader = PerCriterionOneShotGrader(generate_fn=_make_generate_fn())
    report = await Rubric.from_dict(criteria).grade(
        to_grade=answer,
        autograder=grader,
        query=query or None,
    )
    reports = report.report or []
    judgments = [
        {
            "criterion_id": criterion.get("id"),
            "section_id": criterion.get("section_id"),
            "requirement": getattr(item, "requirement", criterion.get("requirement")),
            "weight": getattr(item, "weight", criterion.get("weight", 0)),
            "verdict": getattr(item, "verdict", "UNMET"),
            "reason": getattr(item, "reason", ""),
        }
        for criterion, item in zip(criteria, reports, strict=False)
    ]
    return float(report.score), judgments


def _make_generate_fn():
    model = os.getenv("MODEL_NAME", "openai/gpt-5.5")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")

    async def generate(system_prompt: str, user_prompt: str, **_kwargs: Any) -> OneShotOutput:
        response = litellm.completion(
            model=model,
            api_key=api_key,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=1.0,
        )
        if inspect.isawaitable(response):
            response = await response
        content = response["choices"][0]["message"]["content"]
        return OneShotOutput.model_validate_json(_strip_code_fence(content))

    return generate


def _instruction_text() -> str:
    for path in INSTRUCTION_CANDIDATES:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


if __name__ == "__main__":
    main()

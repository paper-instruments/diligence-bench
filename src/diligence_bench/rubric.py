from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from rubric import Rubric
from rubric.autograders import PerCriterionOneShotGrader
from rubric.autograders.schemas import OneShotOutput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoreResult:
    score: float
    section_scores: dict[str, float]
    verdicts: list[dict[str, Any]]


async def score(
    answer: str,
    criteria: list[dict[str, Any]],
    query: str | None,
    *,
    judge_client: Any,
    judge_model: str,
    judge_sampling_args: dict[str, Any] | None = None,
) -> ScoreResult:
    valid_criteria = _criteria(criteria)
    if not valid_criteria:
        return ScoreResult(score=0.0, section_scores={}, verdicts=[])

    grader = PerCriterionOneShotGrader(
        generate_fn=_make_generate_fn(
            judge_client,
            judge_model,
            judge_sampling_args or {},
        ),
    )
    report = await Rubric.from_dict(valid_criteria).grade(
        to_grade=answer,
        autograder=grader,
        query=query,
    )
    reports = report.report or []
    return ScoreResult(
        score=float(report.score),
        section_scores=_section_scores(valid_criteria, reports),
        verdicts=_verdicts(valid_criteria, reports),
    )


def _criteria(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    criteria: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping) and item.get("requirement"):
            criteria.append(dict(item))
    return criteria


def _make_generate_fn(
    judge_client: Any,
    judge_model: str,
    judge_sampling_args: dict[str, Any],
):
    async def generate(system_prompt: str, user_prompt: str, **kwargs: Any) -> OneShotOutput:
        call_args = _normalize_judge_args(judge_sampling_args)
        if "/" in judge_model:
            extra_body = dict(call_args.get("extra_body") or {})
            extra_body.setdefault("provider", {"order": ["Bedrock"], "allow_fallbacks": True})
            call_args["extra_body"] = extra_body
        response = judge_client.chat.completions.parse(
            model=judge_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=OneShotOutput,
            **call_args,
        )
        if inspect.isawaitable(response):
            response = await response

        parsed = response.choices[0].message.parsed
        if not isinstance(parsed, OneShotOutput):
            raise TypeError("judge response did not parse as OneShotOutput")
        return parsed

    return generate


def _verdicts(criteria: list[dict[str, Any]], reports: list[Any]) -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []
    for criterion, report in zip(criteria, reports, strict=False):
        verdicts.append(
            {
                "criterion_id": criterion.get("id"),
                "section_id": criterion.get("section_id"),
                "requirement": report.requirement,
                "weight": report.weight,
                "verdict": report.verdict,
                "reason": report.reason,
            }
        )
    return verdicts


def _section_scores(criteria: list[dict[str, Any]], reports: list[Any]) -> dict[str, float]:
    reports_by_index = dict(enumerate(reports))
    section_ids = []
    for criterion in criteria:
        section_id = criterion.get("section_id")
        if section_id not in section_ids:
            section_ids.append(section_id)

    scores: dict[str, float] = {}
    for section_id in section_ids:
        key = str(section_id)
        section_reports = [
            report
            for index, criterion in enumerate(criteria)
            if criterion.get("section_id") == section_id
            for report in [reports_by_index.get(index)]
            if report is not None
        ]
        positive_total = sum(max(0.0, float(report.weight)) for report in section_reports)
        negative_total = sum(
            abs(float(report.weight)) for report in section_reports if report.weight < 0
        )
        raw = sum(float(report.weight) for report in section_reports if report.verdict == "MET")

        if positive_total > 0:
            scores[key] = _clamp(raw / positive_total)
        elif negative_total > 0:
            scores[key] = _clamp(1.0 + raw / negative_total)
        else:
            scores[key] = 0.0
    return scores


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


_EXTRA_BODY_KEYS = {"reasoning"}


def _normalize_judge_args(args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args or {})
    if "max_tokens" in normalized:
        value = normalized.pop("max_tokens")
        if value is not None:
            normalized["max_completion_tokens"] = value
    if normalized.get("max_completion_tokens") is None:
        normalized.pop("max_completion_tokens", None)

    extra_body: dict[str, Any] = {}
    for key in list(normalized):
        if key in _EXTRA_BODY_KEYS:
            extra_body[key] = normalized.pop(key)
    if extra_body:
        normalized["extra_body"] = extra_body

    return {key: value for key, value in normalized.items() if value is not None}

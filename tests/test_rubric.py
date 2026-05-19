from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from rubric.autograders.per_criterion_one_shot_grader import DEFAULT_SYSTEM_PROMPT
from rubric.autograders.schemas import CriterionEvaluation, OneShotOutput

from diligence_bench.rubric import score


class StubCompletions:
    def __init__(self, parsed: OneShotOutput) -> None:
        self.parsed = parsed
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(parsed=self.parsed),
                )
            ]
        )


class StubJudgeClient:
    def __init__(self, parsed: OneShotOutput) -> None:
        self.completions = StubCompletions(parsed)
        self.chat = SimpleNamespace(completions=self.completions)


class FailingCompletions:
    async def parse(self, **kwargs: Any) -> Any:
        del kwargs
        raise RuntimeError("judge unavailable")


class FailingJudgeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FailingCompletions())


@pytest.mark.anyio
async def test_score_returns_overall_section_scores_and_verdicts() -> None:
    client = StubJudgeClient(
        OneShotOutput(
            criteria_evaluations=[
                CriterionEvaluation(
                    criterion_number=1,
                    criterion_status="MET",
                    explanation="The thesis is explicit.",
                ),
                CriterionEvaluation(
                    criterion_number=2,
                    criterion_status="MET",
                    explanation="The error is present.",
                ),
                CriterionEvaluation(
                    criterion_number=3,
                    criterion_status="UNMET",
                    explanation="The error is absent.",
                ),
            ]
        )
    )
    criteria = [
        {
            "id": "c1",
            "section_id": "thesis",
            "weight": 2.0,
            "requirement": "States the thesis.",
        },
        {
            "id": "c2",
            "section_id": "thesis",
            "weight": -1.0,
            "requirement": "Claims results are guaranteed.",
        },
        {
            "id": "c3",
            "section_id": "risk",
            "weight": -2.0,
            "requirement": "Ignores refinancing risk.",
        },
    ]

    result = await score(
        "The memo states the thesis but guarantees results.",
        criteria,
        "Analyze the company.",
        judge_client=client,
        judge_model="judge-model",
        judge_sampling_args={
            "temperature": 0,
            "max_tokens": 200,
            "reasoning": {"effort": "low"},
            "metadata": None,
        },
    )

    assert result.score == 0.5
    assert result.section_scores == {"thesis": 0.5, "risk": 1.0}
    assert result.verdicts == [
        {
            "criterion_id": "c1",
            "section_id": "thesis",
            "requirement": "States the thesis.",
            "weight": 2.0,
            "verdict": "MET",
            "reason": "The thesis is explicit.",
        },
        {
            "criterion_id": "c2",
            "section_id": "thesis",
            "requirement": "Claims results are guaranteed.",
            "weight": -1.0,
            "verdict": "MET",
            "reason": "The error is present.",
        },
        {
            "criterion_id": "c3",
            "section_id": "risk",
            "requirement": "Ignores refinancing risk.",
            "weight": -2.0,
            "verdict": "UNMET",
            "reason": "The error is absent.",
        },
    ]

    call = client.completions.calls[0]
    assert call["model"] == "judge-model"
    assert call["messages"][0] == {"role": "system", "content": DEFAULT_SYSTEM_PROMPT}
    assert call["response_format"] is OneShotOutput
    assert call["temperature"] == 0
    assert call["max_completion_tokens"] == 200
    assert call["extra_body"] == {"reasoning": {"effort": "low"}}
    assert "metadata" not in call


@pytest.mark.anyio
async def test_score_returns_zero_without_criteria() -> None:
    client = StubJudgeClient(
        OneShotOutput(
            criteria_evaluations=[
                CriterionEvaluation(
                    criterion_number=1,
                    criterion_status="MET",
                    explanation="Unused.",
                )
            ]
        )
    )

    result = await score(
        "Answer",
        [],
        "Query",
        judge_client=client,
        judge_model="judge-model",
    )

    assert result.score == 0.0
    assert result.section_scores == {}
    assert result.verdicts == []
    assert client.completions.calls == []


@pytest.mark.anyio
async def test_score_propagates_judge_failures() -> None:
    with pytest.raises(RuntimeError, match="judge unavailable"):
        await score(
            "Answer",
            [{"id": "c1", "section_id": "memo", "weight": 1, "requirement": "Has memo"}],
            "Query",
            judge_client=FailingJudgeClient(),
            judge_model="judge-model",
        )


def test_harbor_verifier_imports_rubric_package() -> None:
    """Both grading paths must consume the rubric package's default prompt.

    The in-container verifier (`harbor/template/tests/run_test.py`) and the
    in-process runner both construct PerCriterionOneShotGrader without a
    custom system_prompt, so DEFAULT_SYSTEM_PROMPT applies to both.
    """
    from pathlib import Path

    verifier_path = (
        Path(__file__).resolve().parents[1]
        / "src/diligence_bench/harbor/template/tests/run_test.py"
    )
    source = verifier_path.read_text(encoding="utf-8")
    assert "from rubric import Rubric" in source, (
        "Harbor in-container verifier must import the rubric package"
    )
    assert "PerCriterionOneShotGrader(generate_fn=" in source, (
        "Harbor in-container verifier must construct the package's grader"
    )
    assert "system_prompt=" not in source, (
        "Harbor in-container verifier must use the package's default prompt"
    )

from __future__ import annotations

import json

import pytest

from diligence_bench.results import EvalResult, ResultsWriter


def test_eval_result_truncates_query() -> None:
    result = EvalResult(
        run_id="run",
        model="model",
        dataset_id="row",
        query="x" * 501,
        answer="answer",
        score=1.0,
        section_scores={},
        verdicts=[],
        num_turns=1,
    )

    assert result.query == ("x" * 500) + "..."


@pytest.mark.anyio
async def test_results_writer_writes_scores_and_trajectories(tmp_path) -> None:
    writer = ResultsWriter(tmp_path, "run-1")
    result = EvalResult(
        run_id="run-1",
        model="model-a",
        dataset_id="example-1",
        query="query",
        answer="answer",
        score=0.75,
        section_scores={"summary": 1.0},
        verdicts=[{"criterion_id": "c1", "verdict": "MET"}],
        num_turns=3,
        judge_model="judge",
        underlying_model="underlying",
        harness="finance",
    )
    trajectory = [{"role": "assistant", "content": "answer"}]

    await writer.write(result, trajectory)

    score_path = tmp_path / "run-1" / "model-a" / "scores" / "example-1.json"
    trajectory_path = tmp_path / "run-1" / "model-a" / "trajectories" / "example-1.json"
    assert json.loads(score_path.read_text(encoding="utf-8"))["score"] == 0.75
    assert json.loads(trajectory_path.read_text(encoding="utf-8")) == trajectory
    assert writer.read_successful("model-a", "example-1") == result


@pytest.mark.anyio
async def test_results_writer_read_successful_ignores_errors_and_blank_answers(tmp_path) -> None:
    writer = ResultsWriter(tmp_path, "run-1")
    error_result = EvalResult(
        run_id="run-1",
        model="model-a",
        dataset_id="error",
        query="query",
        answer="answer",
        score=0.0,
        section_scores={},
        verdicts=[],
        num_turns=1,
        error="failed",
    )
    blank_result = EvalResult(
        run_id="run-1",
        model="model-a",
        dataset_id="blank",
        query="query",
        answer=" ",
        score=0.0,
        section_scores={},
        verdicts=[],
        num_turns=1,
    )

    await writer.write(error_result)
    await writer.write(blank_result)

    assert writer.read_successful("model-a", "error") is None
    assert writer.read_successful("model-a", "blank") is None


@pytest.mark.anyio
async def test_results_writer_sanitizes_dataset_id_for_paths(tmp_path) -> None:
    writer = ResultsWriter(tmp_path, "run-1")
    result = EvalResult(
        run_id="run-1",
        model="model-a",
        dataset_id="../nested/id",
        query="query",
        answer="answer",
        score=1.0,
        section_scores={},
        verdicts=[],
        num_turns=1,
    )

    await writer.write(result, trajectory=[])

    score_files = list((tmp_path / "run-1" / "model-a" / "scores").glob("*.json"))
    trajectory_files = list((tmp_path / "run-1" / "model-a" / "trajectories").glob("*.json"))
    assert len(score_files) == 1
    assert len(trajectory_files) == 1
    assert score_files[0].parent == tmp_path / "run-1" / "model-a" / "scores"
    assert json.loads(score_files[0].read_text(encoding="utf-8"))["dataset_id"] == "../nested/id"
    assert writer.read_successful("model-a", "../nested/id") == result

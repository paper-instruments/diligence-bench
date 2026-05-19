from __future__ import annotations

import csv
import json

from diligence_bench.ablations import (
    ABLATION_FIELDNAMES,
    AblationRow,
    append_ablation_row,
    build_ablation_row,
    variant_name,
)
from diligence_bench.results import EvalResult


def test_ablation_row_csv_schema_and_float_formatting(tmp_path) -> None:
    row = AblationRow(
        ablation_name="phase-1",
        run_id="run",
        variant="finance__model",
        harness="finance",
        underlying_model="model",
        judge_model="judge",
        dataset="diligence-bench",
        examples=5,
        completed=4,
        errors=1,
        mean_score=0.25,
        median_score=0.125,
        min_score=0.0,
        max_score=1.0,
        mean_turns=3.5,
        section_scores={"risk": 0.75, "summary": 0.5},
        run_dir=tmp_path / "run",
        timestamp="2026-05-18T00:00:00+00:00",
    )

    csv_row = row.to_csv_row()

    assert list(csv_row) == ABLATION_FIELDNAMES
    assert csv_row["mean_score"] == "0.250000"
    assert csv_row["mean_turns"] == "3.500000"
    assert json.loads(csv_row["section_scores_json"]) == {"risk": 0.75, "summary": 0.5}


def test_build_ablation_row_aggregates_successful_results(tmp_path) -> None:
    results = [
        EvalResult(
            run_id="run",
            model="model",
            dataset_id="a",
            query="query",
            answer="answer",
            score=1.0,
            section_scores={"risk": 0.5, "summary": 1.0},
            verdicts=[],
            num_turns=2,
        ),
        EvalResult(
            run_id="run",
            model="model",
            dataset_id="b",
            query="query",
            answer="answer",
            score=0.0,
            section_scores={"risk": 1.0},
            verdicts=[],
            num_turns=4,
        ),
        EvalResult(
            run_id="run",
            model="model",
            dataset_id="c",
            query="query",
            answer="",
            score=0.0,
            section_scores={"risk": 0.0},
            verdicts=[],
            num_turns=9,
            error="failed",
        ),
    ]

    row = build_ablation_row(
        results,
        ablation_name="phase-1",
        run_id="run",
        variant="finance__model",
        harness="finance",
        underlying_model="model",
        judge_model="judge",
        dataset="diligence-bench",
        examples=3,
        run_dir=tmp_path / "run",
    )

    assert row.completed == 3
    assert row.errors == 1
    assert row.mean_score == 0.5
    assert row.median_score == 0.5
    assert row.min_score == 0.0
    assert row.max_score == 1.0
    assert row.mean_turns == 3.0
    assert row.section_scores == {"risk": 0.75, "summary": 1.0}


def test_append_ablation_row_writes_header_and_deduplicates(tmp_path) -> None:
    path = tmp_path / "results" / "ablations.csv"
    row = AblationRow(
        ablation_name="phase-1",
        run_id="run",
        variant="finance__model",
        harness="finance",
        underlying_model="model",
        judge_model="judge",
        dataset="diligence-bench",
        examples=1,
        completed=1,
        errors=0,
        mean_score=1.0,
        median_score=1.0,
        min_score=1.0,
        max_score=1.0,
        mean_turns=2.0,
        section_scores={},
        run_dir=tmp_path / "run",
        timestamp="2026-05-18T00:00:00+00:00",
    )

    assert append_ablation_row(path, row) is True
    assert append_ablation_row(path, row) is False

    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run"


def test_variant_name_slugs_components() -> None:
    assert variant_name("finance agent", "openai/gpt-5") == "finance_agent__openai_gpt-5"

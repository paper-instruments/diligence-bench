from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from diligence_bench.results import EvalResult

ABLATION_FIELDNAMES = [
    "ablation_name",
    "run_id",
    "variant",
    "harness",
    "underlying_model",
    "judge_model",
    "dataset",
    "examples",
    "completed",
    "errors",
    "mean_score",
    "median_score",
    "min_score",
    "max_score",
    "mean_turns",
    "section_scores_json",
    "run_dir",
    "timestamp",
    "sampling_temperature",
    "sampling_reasoning_effort",
    "sampling_verbosity",
    "total_input_tokens",
    "total_output_tokens",
    "total_tokens",
    "mean_total_tokens",
]


@dataclass(frozen=True)
class AblationRow:
    ablation_name: str
    run_id: str
    variant: str
    harness: str
    underlying_model: str
    judge_model: str
    dataset: str
    examples: int
    completed: int
    errors: int
    mean_score: float
    median_score: float
    min_score: float
    max_score: float
    mean_turns: float
    section_scores: dict[str, float]
    run_dir: Path
    timestamp: str
    sampling_temperature: float = 1.0
    sampling_reasoning_effort: str = "medium"
    sampling_verbosity: str = "medium"
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    mean_total_tokens: float = 0.0

    def to_csv_row(self) -> dict[str, str]:
        return {
            "ablation_name": self.ablation_name,
            "run_id": self.run_id,
            "variant": self.variant,
            "harness": self.harness,
            "underlying_model": self.underlying_model,
            "judge_model": self.judge_model,
            "dataset": self.dataset,
            "examples": str(self.examples),
            "completed": str(self.completed),
            "errors": str(self.errors),
            "mean_score": _fmt_float(self.mean_score),
            "median_score": _fmt_float(self.median_score),
            "min_score": _fmt_float(self.min_score),
            "max_score": _fmt_float(self.max_score),
            "mean_turns": _fmt_float(self.mean_turns),
            "section_scores_json": json.dumps(self.section_scores, sort_keys=True),
            "run_dir": str(self.run_dir),
            "timestamp": self.timestamp,
            "sampling_temperature": _fmt_float(self.sampling_temperature),
            "sampling_reasoning_effort": self.sampling_reasoning_effort,
            "sampling_verbosity": self.sampling_verbosity,
            "total_input_tokens": str(self.total_input_tokens),
            "total_output_tokens": str(self.total_output_tokens),
            "total_tokens": str(self.total_tokens),
            "mean_total_tokens": _fmt_float(self.mean_total_tokens),
        }


def build_ablation_row(
    results: list[EvalResult],
    *,
    ablation_name: str,
    run_id: str,
    variant: str,
    harness: str,
    underlying_model: str,
    judge_model: str,
    dataset: str,
    examples: int,
    run_dir: Path,
    sampling_temperature: float = 1.0,
    sampling_reasoning_effort: str = "medium",
    sampling_verbosity: str = "medium",
) -> AblationRow:
    successful = [result for result in results if result.error is None]
    scores = [float(result.score or 0.0) for result in successful]
    turns = [int(result.num_turns or 0) for result in successful]
    total_tokens = [int(result.total_tokens or 0) for result in successful]
    return AblationRow(
        ablation_name=ablation_name,
        run_id=run_id,
        variant=variant,
        harness=harness,
        underlying_model=underlying_model,
        judge_model=judge_model,
        dataset=dataset,
        examples=examples,
        completed=len(results),
        errors=len(results) - len(successful),
        mean_score=_mean(scores),
        median_score=_median(scores),
        min_score=min(scores) if scores else 0.0,
        max_score=max(scores) if scores else 0.0,
        mean_turns=_mean(turns),
        section_scores=_mean_section_scores(successful),
        run_dir=run_dir,
        timestamp=datetime.now(UTC).isoformat(),
        sampling_temperature=sampling_temperature,
        sampling_reasoning_effort=sampling_reasoning_effort,
        sampling_verbosity=sampling_verbosity,
        total_input_tokens=sum(int(result.input_tokens or 0) for result in successful),
        total_output_tokens=sum(int(result.output_tokens or 0) for result in successful),
        total_tokens=sum(total_tokens),
        mean_total_tokens=_mean(total_tokens),
    )


def append_ablation_row(path: Path, row: AblationRow) -> bool:
    """Upsert one aggregate row keyed by (ablation_name, run_id, variant).

    On a resume run the same key already exists with stale numbers; overwrite
    it so the aggregate matches the per-task score files actually on disk.
    Returns ``True`` if a new row was added, ``False`` if an existing row was
    replaced.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    key = (row.ablation_name, row.run_id, row.variant)

    existing_rows: list[dict[str, str]] = []
    replaced = False
    if path.exists():
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for existing in reader:
                existing_key = (
                    existing.get("ablation_name", ""),
                    existing.get("run_id", ""),
                    existing.get("variant", ""),
                )
                if existing_key == key:
                    replaced = True
                    continue
                existing_rows.append(existing)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ABLATION_FIELDNAMES)
        writer.writeheader()
        for existing in existing_rows:
            writer.writerow({key: existing.get(key, "") for key in ABLATION_FIELDNAMES})
        writer.writerow(row.to_csv_row())
    return not replaced


def variant_name(harness: str, underlying_model: str) -> str:
    return f"{_slug(harness)}__{_slug(underlying_model)}"


def _mean(values: list[float] | list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _mean_section_scores(results: list[EvalResult]) -> dict[str, float]:
    by_section: dict[str, list[float]] = {}
    for result in results:
        for section, score in result.section_scores.items():
            by_section.setdefault(section, []).append(float(score))
    return {section: round(_mean(scores), 6) for section, scores in sorted(by_section.items())}


def _fmt_float(value: float) -> str:
    return f"{value:.6f}"


def _slug(value: str) -> str:
    result = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            result.append(char)
        else:
            result.append("_")
    slug = "".join(result).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "unknown"

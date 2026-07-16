from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

QUERY_TRUNCATION_LENGTH = 500


@dataclass
class EvalResult:
    run_id: str
    model: str
    dataset_id: str
    query: str
    answer: str
    score: float
    section_scores: dict[str, float]
    verdicts: list[dict[str, Any]]
    num_turns: int
    judge_model: str = ""
    error: str | None = None
    underlying_model: str | None = None
    harness: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if len(self.query) > QUERY_TRUNCATION_LENGTH:
            self.query = self.query[:QUERY_TRUNCATION_LENGTH] + "..."


class ResultsWriter:
    """Async-safe writer for score JSON and compact trajectories."""

    def __init__(self, output_dir: Path, run_id: str) -> None:
        self._run_dir = output_dir / run_id
        self._lock = asyncio.Lock()
        self._run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    def read_successful(self, model: str, dataset_id: str) -> EvalResult | None:
        path = self._score_path(model, dataset_id)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            result = EvalResult(**data)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("could not read existing result %s: %s", path, exc)
            return None
        if result.error is not None or not result.answer.strip():
            return None
        return result

    async def write(
        self,
        result: EvalResult,
        trajectory: list[dict[str, Any]] | None = None,
    ) -> None:
        model_dir = self._run_dir / result.model
        scores_dir = model_dir / "scores"
        trajectories_dir = model_dir / "trajectories"

        async with self._lock:
            scores_dir.mkdir(parents=True, exist_ok=True)
            score_path = self._score_path(result.model, result.dataset_id)
            with score_path.open("w", encoding="utf-8") as handle:
                json.dump(asdict(result), handle, indent=2, default=str)
                handle.flush()

            if trajectory is not None:
                trajectories_dir.mkdir(parents=True, exist_ok=True)
                traj_path = trajectories_dir / f"{_safe_filename(result.dataset_id)}.json"
                with traj_path.open("w", encoding="utf-8") as handle:
                    json.dump(trajectory, handle, indent=2, default=str)
                    handle.flush()

    def _score_path(self, model: str, dataset_id: str) -> Path:
        return self._run_dir / model / "scores" / f"{_safe_filename(dataset_id)}.json"


def _safe_filename(value: str) -> str:
    if (
        value
        and not value.startswith(".")
        and all(char.isalnum() or char in {"-", "_", "."} for char in value)
    ):
        return value
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value)
    slug = "-".join(part for part in slug.split("-") if part)
    suffix = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:40]}-{suffix}" if slug else suffix

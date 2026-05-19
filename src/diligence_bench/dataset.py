from __future__ import annotations

import logging
from typing import Any

from datasets import Dataset, load_dataset

logger = logging.getLogger(__name__)

HF_DATASET_ID = "tldc/diligence-bench"
HF_SPLIT = "test"


def load_diligence_bench(num_examples: int = -1) -> Dataset:
    """Load diligence-bench rows in the canonical verifier task shape."""
    dataset = load_dataset(HF_DATASET_ID, split=HF_SPLIT)
    assert isinstance(dataset, Dataset)

    formatted = dataset.map(format_diligence_bench_row).select_columns(["prompt", "info"])
    if num_examples != -1:
        formatted = formatted.select(range(min(num_examples, len(formatted))))

    logger.info("Loaded %d diligence-bench example(s)", len(formatted))
    return formatted


def format_diligence_bench_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": [{"role": "user", "content": row["query"]}],
        "info": {
            "datasetId": str(row["datasetId"]),
            "rubric": _flatten_rubric(row["rubric"]),
        },
    }


def _flatten_rubric(rubric: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(rubric, list):
        return [dict(criterion) for criterion in rubric]

    criteria: list[dict[str, Any]] = []
    for section in rubric.get("sections", []):
        for criterion in section.get("criteria", []):
            criteria.append(
                {
                    "id": criterion["id"],
                    "section_id": section["id"],
                    "weight": criterion["weight"],
                    "requirement": criterion["requirement"],
                }
            )
    return criteria

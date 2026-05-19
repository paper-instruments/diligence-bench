from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import TextIO


def print_summary(run_dir: str | Path, *, stream: TextIO) -> None:
    rows = _read_results(Path(run_dir))
    by_variant: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_variant[(str(row.get("harness") or ""), str(row["model"]))].append(row)
    if not by_variant:
        stream.write("No results.\n")
        return

    stream.write("harness model completed errors mean median min max mean_turns\n")
    for (harness, model), model_rows in sorted(
        by_variant.items(),
        key=lambda item: _mean([float(row.get("score", 0.0) or 0.0) for row in item[1]]),
        reverse=True,
    ):
        scores = [float(row.get("score", 0.0) or 0.0) for row in model_rows if not row.get("error")]
        turns = [int(row.get("num_turns", 0) or 0) for row in model_rows if not row.get("error")]
        errors = len([row for row in model_rows if row.get("error")])
        stream.write(
            f"{harness or 'unknown'} {model} {len(model_rows)} {errors} "
            f"{_mean(scores):.3f} {median(scores) if scores else 0.0:.3f} "
            f"{min(scores) if scores else 0.0:.3f} {max(scores) if scores else 0.0:.3f} "
            f"{_mean(turns):.1f}\n"
        )


def _read_results(run_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(run_dir.glob("*/scores/*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def _mean(values: list[float] | list[int]) -> float:
    return sum(values) / len(values) if values else 0.0

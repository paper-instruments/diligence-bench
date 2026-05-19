from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def load_tasks_from_dir(tasks_dir: str | Path, *, limit: int = -1) -> list[dict[str, Any]]:
    root = Path(tasks_dir)
    if not root.exists():
        raise FileNotFoundError(f"Task directory does not exist: {root}")

    tasks = list(_iter_task_dirs(root))
    if limit != -1:
        tasks = tasks[: max(0, limit)]
    return [_load_task_dir(task_dir) for task_dir in tasks]


def _iter_task_dirs(root: Path) -> Iterator[Path]:
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "instruction.md").exists():
            yield child


def _load_task_dir(task_dir: Path) -> dict[str, Any]:
    instruction = (task_dir / "instruction.md").read_text(encoding="utf-8")
    rubric = json.loads((task_dir / "tests" / "rubric.json").read_text(encoding="utf-8"))
    dataset_id = _dataset_id(task_dir)
    return {
        "prompt": [{"role": "user", "content": instruction}],
        "info": {
            "datasetId": dataset_id,
            "task_id": task_dir.name,
            "task_dir": str(task_dir),
            "rubric": rubric,
        },
    }


def _dataset_id(task_dir: Path) -> str:
    try:
        import tomllib

        data = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        value = data.get("metadata", {}).get("dataset_id")
        if value:
            return str(value)
    except (OSError, ValueError):
        pass
    return task_dir.name

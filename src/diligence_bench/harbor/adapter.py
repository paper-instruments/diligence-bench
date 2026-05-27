from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

import tomli_w
import yaml

from diligence_bench.dataset import load_diligence_bench

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("datasets/diligence-bench")
DEFAULT_VERIFIER_MODEL = "openrouter/openai/gpt-5.5"
TEMPLATE_DIR = Path(__file__).parent / "template"
TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
ANSWER_PATH = "/workspace/answer.md"
_BUNDLED_TOOL_IDS = ("sec_edgar", "web_search")


class DiligenceBenchAdapter:
    def __init__(
        self,
        out_dir: str | Path = DEFAULT_OUTPUT_DIR,
        num_examples: int = -1,
        verifier_model: str = DEFAULT_VERIFIER_MODEL,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.num_examples = num_examples
        self.verifier_model = verifier_model

    def generate(self) -> list[Path]:
        rows = load_diligence_bench(num_examples=self.num_examples)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        _clear_generated_tasks(self.out_dir)
        generated: list[Path] = []
        for row in rows:
            generated.append(self._write_row(row))
        logger.info("Generated %d Harbor task(s) in %s", len(generated), self.out_dir)
        return generated

    def _write_row(self, row: Mapping[str, Any]) -> Path:
        info = _mapping(row.get("info"))
        prompt = _prompt_text(row.get("prompt"))
        dataset_id = str(info.get("datasetId") or _task_hash(prompt))
        task_id = make_task_id(dataset_id, prompt)
        task_dir = self.out_dir / task_id
        if task_dir.exists():
            shutil.rmtree(task_dir)
        shutil.copytree(TEMPLATE_DIR, task_dir)

        _bundle_tools(task_dir)
        _write_instruction(task_dir, prompt)
        _write_rubric(task_dir, info)
        _write_task_toml(task_dir, task_id, dataset_id, self.verifier_model)
        _write_docker_compose(task_dir)
        return task_dir


def make_task_id(dataset_id: str, prompt: str = "") -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in dataset_id)
    slug = "-".join(part for part in slug.split("-") if part)
    suffix = _task_hash(f"{dataset_id}\n{prompt}")[:10]
    if slug:
        return f"dilbench-{slug[:40]}-{suffix}"
    return f"dilbench-{suffix}"


def _write_instruction(task_dir: Path, prompt: str) -> None:
    template = (task_dir / "instruction.md").read_text(encoding="utf-8")
    (task_dir / "instruction.md").write_text(
        template.replace("{{QUERY}}", prompt).replace("{{ANSWER_PATH}}", ANSWER_PATH),
        encoding="utf-8",
    )


def _write_rubric(task_dir: Path, info: Mapping[str, Any]) -> None:
    rubric = info.get("rubric", [])
    if not isinstance(rubric, list):
        raise ValueError("row info.rubric must be a list of criteria")
    (task_dir / "tests" / "rubric.json").write_text(
        json.dumps(rubric, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_task_toml(
    task_dir: Path,
    task_id: str,
    dataset_id: str,
    verifier_model: str,
) -> None:
    data = {
        "version": "1.0",
        "metadata": {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "benchmark": "diligence-bench",
        },
        "agent": {
            "timeout_sec": 3600,
            "user": "agent",
            "env": {
                "EXA_API_KEY": "${EXA_API_KEY:-}",
                "OPENAI_API_KEY": "${OPENAI_API_KEY:-}",
                "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY:-}",
                "SEC_USER_AGENT": "${SEC_USER_AGENT:-The LLM Data Company diligence-bench contact@example.com}",
                "DILIGENCE_BENCH_WEB_FETCH_WRITE": "1",
            },
        },
        "verifier": {
            "timeout_sec": 900,
            "user": "verifier",
            "env": {
                "MODEL_NAME": verifier_model,
                "OPENAI_API_KEY": "${OPENAI_API_KEY:-}",
                "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY:-}",
            },
        },
        "environment": {
            "build_timeout_sec": 600,
            "cpus": 2,
            "memory_mb": 4096,
            "storage_mb": 4096,
            "gpus": 0,
            "allow_internet": True,
            "mcp_servers": [
                {
                    "name": "sec_edgar",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["/usr/lib/diligence_bench/tools/sec_edgar/server.py"],
                },
                {
                    "name": "web_search",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["/usr/lib/diligence_bench/tools/web_search/server.py"],
                },
            ],
        },
    }
    (task_dir / "task.toml").write_bytes(tomli_w.dumps(data).encode("utf-8"))


def _write_docker_compose(task_dir: Path) -> None:
    data = {
        "services": {
            "main": {
                "environment": [
                    "EXA_API_KEY=${EXA_API_KEY:-}",
                    "OPENAI_API_KEY=${OPENAI_API_KEY:-}",
                    "OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}",
                    "MODEL_NAME=${MODEL_NAME:-openrouter/openai/gpt-5.5}",
                    "SEC_USER_AGENT=${SEC_USER_AGENT:-The LLM Data Company diligence-bench contact@example.com}",
                    "DILIGENCE_BENCH_WEB_FETCH_WRITE=1",
                ],
            },
        },
    }
    (task_dir / "environment" / "docker-compose.yaml").write_text(
        yaml.dump(data, sort_keys=False),
        encoding="utf-8",
    )


def _prompt_text(prompt: object) -> str:
    if not isinstance(prompt, Iterable) or isinstance(prompt, str | bytes):
        raise ValueError("row prompt must be a list of messages")
    for message in reversed(list(prompt)):
        if isinstance(message, Mapping):
            typed_message = cast(Mapping[str, Any], message)
            if typed_message.get("role") != "user":
                continue
            content = typed_message.get("content", "")
            return str(content)
    raise ValueError("row prompt must contain a user message")


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("row info must be a mapping")
    return cast(Mapping[str, Any], value)


def _task_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clear_generated_tasks(out_dir: Path) -> None:
    for child in out_dir.iterdir():
        if child.is_dir() and child.name.startswith("dilbench-"):
            shutil.rmtree(child)


def _bundle_tools(task_dir: Path) -> None:
    """Copy MCP tool sources from the canonical tools/ tree into the task.

    Harbor task directories are self-contained — at runtime, the Dockerfile
    bakes `environment/diligence_bench/tools/` into `/usr/lib/diligence_bench/`.
    Maintaining a checked-in second copy of the tool implementations would
    drift. Instead, we copy from the single source of truth at build time.
    """
    dest_root = task_dir / "environment" / "diligence_bench" / "tools"
    dest_root.mkdir(parents=True, exist_ok=True)
    init = dest_root.parent / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
    init_inner = dest_root / "__init__.py"
    if not init_inner.exists():
        init_inner.write_text("", encoding="utf-8")
    for tool_id in _BUNDLED_TOOL_IDS:
        src = TOOLS_DIR / tool_id
        dest = dest_root / tool_id
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))

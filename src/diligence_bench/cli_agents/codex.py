"""Codex CLI runner.

Invokes `codex exec` non-interactively with the instruction on stdin. Accepts
OpenRouter or OpenAI model ids. By default, points Codex at OpenRouter via
`-c model_provider=openrouter` when the model id is namespaced
(e.g. `openai/gpt-5.5`), and falls back to the CLI's default provider for
bare model ids.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from diligence_bench.cli_agents.base import (
    CliAgentResult,
    prepare_workspace,
    read_answer,
    run_subprocess,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SEC = 1800.0
_PASSTHROUGH_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BENCHMARK_API_KEY",
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
)


async def run(
    instruction: str,
    model: str,
    workdir: Path,
    *,
    timeout: float = _DEFAULT_TIMEOUT_SEC,
) -> CliAgentResult:
    answer_path = prepare_workspace(workdir, instruction)
    env = _subprocess_env()

    args: list[str] = ["codex", "exec", "--skip-git-repo-check"]
    args += ["--model", _model_id(model)]
    args += _provider_overrides(model)
    args += ["--cd", str(workdir)]
    args += ["--sandbox", "workspace-write"]

    exit_code, stdout, stderr = await run_subprocess(
        args,
        cwd=workdir,
        env=env,
        timeout=timeout,
        stdin=(workdir / "instruction.md").read_text(encoding="utf-8"),
    )
    answer = read_answer(workdir, fallback=stdout.strip())
    error = None
    if exit_code != 0:
        error = f"codex exited {exit_code}: {stderr.strip()[:500]}"
    elif not answer:
        error = "codex produced no answer"

    extras = {}
    if answer_path.exists():
        extras["answer_path"] = str(answer_path)

    return CliAgentResult(
        answer=answer,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        error=error,
        extras=extras,
    )


def _subprocess_env() -> dict[str, str]:
    env: dict[str, str] = {
        key: os.environ[key] for key in _PASSTHROUGH_ENV_KEYS if key in os.environ
    }
    if "OPENROUTER_API_KEY" not in env:
        bench_key = os.environ.get("OPENROUTER_BENCHMARK_API_KEY")
        if bench_key:
            env["OPENROUTER_API_KEY"] = bench_key
    return env


def _model_id(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def _provider_overrides(model: str) -> list[str]:
    if "/" not in model:
        return []
    provider = model.split("/", 1)[0]
    if provider != "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
        return []
    return [
        "-c",
        "model_provider=openrouter",
        "-c",
        'model_providers.openrouter.name="OpenRouter"',
        "-c",
        'model_providers.openrouter.base_url="https://openrouter.ai/api/v1"',
        "-c",
        'model_providers.openrouter.env_key="OPENROUTER_API_KEY"',
        "-c",
        'model_providers.openrouter.wire_api="responses"',
    ]

"""Claude Code CLI runner.

Invokes `claude -p` with the instruction on stdin, model id, and a generous
turn budget. Authenticates via `ANTHROPIC_API_KEY` from the host env. The CLI
handles its own filesystem, shell, MCP, and skill discovery — we hand it the
workspace and let it write `answer.md`.

Model ids follow the CLI's own conventions: `sonnet`, `opus`, `haiku`, or full
ids like `claude-sonnet-4-6`. For OpenRouter routing, set the model to a
specific id and ensure the CLI is configured upstream — this runner does not
override the auth path.
"""

from __future__ import annotations

import json
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
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
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
    args = [
        "claude",
        "--print",
        "--model",
        _strip_provider_prefix(model),
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--add-dir",
        str(workdir),
    ]
    exit_code, stdout, stderr = await run_subprocess(
        args,
        cwd=workdir,
        env=env,
        timeout=timeout,
        stdin=(workdir / "instruction.md").read_text(encoding="utf-8"),
    )
    parsed = _parse_json_output(stdout)
    fallback_value = parsed.get("result") if parsed else None
    fallback = str(fallback_value).strip() if fallback_value is not None else stdout.strip()
    answer = read_answer(workdir, fallback=fallback)
    error = None
    if exit_code != 0:
        error = f"claude exited {exit_code}: {stderr.strip()[:500]}"
    elif not answer:
        error = "claude produced no answer"

    extras = {}
    if parsed:
        for key in ("session_id", "duration_ms", "total_cost_usd", "num_turns"):
            value = parsed.get(key)
            if value is not None:
                extras[key] = str(value)
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
    env.setdefault("CLAUDE_CODE_DISABLE_TELEMETRY", "1")
    return env


def _strip_provider_prefix(model: str) -> str:
    if model.startswith("anthropic/"):
        return model.split("/", 1)[1]
    return model


def _parse_json_output(stdout: str) -> dict[str, object] | None:
    if not stdout.strip():
        return None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None

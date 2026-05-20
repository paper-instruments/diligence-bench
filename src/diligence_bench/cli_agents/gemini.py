"""Gemini CLI runner.

Invokes ``gemini -p`` non-interactively with the instruction text, the model id,
and yolo approval mode so tool calls are auto-approved. Authenticates via
``GEMINI_API_KEY`` from the host env (Google AI Studio key).

Model ids follow the Gemini CLI's own conventions (e.g. ``gemini-3-pro``,
``gemini-2.5-flash``). Strips a leading ``google/`` provider prefix if present.
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
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
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
    env: dict[str, str] = {
        key: os.environ[key] for key in _PASSTHROUGH_ENV_KEYS if key in os.environ
    }
    args = [
        "gemini",
        "-p",
        (workdir / "instruction.md").read_text(encoding="utf-8"),
        "-m",
        _strip_provider_prefix(model),
        "--approval-mode",
        "yolo",
        "-o",
        "json",
        "--include-directories",
        str(workdir),
    ]
    exit_code, stdout, stderr = await run_subprocess(
        args,
        cwd=workdir,
        env=env,
        timeout=timeout,
    )
    parsed = _parse_json_output(stdout)
    fallback_value = parsed.get("response") if parsed else None
    fallback = str(fallback_value).strip() if fallback_value is not None else stdout.strip()
    answer = read_answer(workdir, fallback=fallback)
    error = None
    if exit_code != 0:
        error = f"gemini exited {exit_code}: {stderr.strip()[:500]}"
    elif not answer:
        error = "gemini produced no answer"

    extras: dict[str, str] = {}
    if parsed:
        session_id = parsed.get("session_id")
        if session_id is not None:
            extras["session_id"] = str(session_id)
        stats = parsed.get("stats") or {}
        if isinstance(stats, dict):
            models = stats.get("models") or {}
            if isinstance(models, dict):
                for model_name, model_stats in models.items():
                    if not isinstance(model_stats, dict):
                        continue
                    api = model_stats.get("api") or {}
                    tokens = model_stats.get("tokens") or {}
                    if isinstance(api, dict):
                        if "totalLatencyMs" in api:
                            extras["duration_ms"] = str(api["totalLatencyMs"])
                        if "totalRequests" in api:
                            extras["num_turns"] = str(api["totalRequests"])
                    if isinstance(tokens, dict):
                        if "input" in tokens:
                            extras[f"{model_name}_input_tokens"] = str(tokens["input"])
                        if "output" in tokens:
                            extras[f"{model_name}_output_tokens"] = str(tokens["output"])
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


def _strip_provider_prefix(model: str) -> str:
    if "/" in model:
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

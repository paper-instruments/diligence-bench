"""Shared types + helpers for CLI-agent runners."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_ANSWER_FILENAME = "answer.md"
_INSTRUCTION_FOOTER = (
    "\n\n---\n\n"
    "When you are done, write your final memo to `answer.md` in the current "
    "working directory. The verifier reads only that file. Do not narrate the "
    "process — write the memo directly."
)


@dataclass(frozen=True)
class CliAgentResult:
    answer: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    error: str | None = None
    extras: dict[str, str] = field(default_factory=dict)


def prepare_workspace(workdir: Path, instruction: str) -> Path:
    """Write the instruction into the workspace and return the answer path."""
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "instruction.md").write_text(instruction + _INSTRUCTION_FOOTER, encoding="utf-8")
    return workdir / _ANSWER_FILENAME


def read_answer(workdir: Path, *, fallback: str = "") -> str:
    answer_path = workdir / _ANSWER_FILENAME
    if not answer_path.exists():
        return fallback
    text = answer_path.read_text(encoding="utf-8").strip()
    return text or fallback


async def run_subprocess(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    stdin: str | None = None,
) -> tuple[int, str, str]:
    """Run a subprocess and return (exit_code, stdout, stderr).

    stdin is encoded as UTF-8. On timeout, the process is killed and the
    partial stdout/stderr captured so far is returned with exit code 124.
    """
    logger.info("CLI agent: %s", " ".join(args))
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        env=env,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        raw_stdout, raw_stderr = await asyncio.wait_for(
            process.communicate(stdin.encode("utf-8") if stdin is not None else None),
            timeout=timeout,
        )
    except TimeoutError:
        process.kill()
        raw_stdout, raw_stderr = await process.communicate()
        return (
            124,
            raw_stdout.decode("utf-8", errors="replace"),
            raw_stderr.decode("utf-8", errors="replace"),
        )
    return (
        process.returncode or 0,
        raw_stdout.decode("utf-8", errors="replace"),
        raw_stderr.decode("utf-8", errors="replace"),
    )

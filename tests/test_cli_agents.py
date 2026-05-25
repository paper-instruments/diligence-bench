"""Tests for the vanilla CLI-agent runners.

We never launch claude or codex for real — we monkey-patch
diligence_bench.cli_agents.base.run_subprocess so the runner gets a
deterministic (exit_code, stdout, stderr) and we can assert on the args list,
the workspace contents, and the resulting CliAgentResult.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from diligence_bench.cli_agents import CLI_AGENTS, CliAgentResult
from diligence_bench.cli_agents import claude_code as claude_code_module
from diligence_bench.cli_agents import codex as codex_module


def test_registry_lists_both_agents() -> None:
    assert set(CLI_AGENTS) == {"claude-code", "codex", "gemini"}


@pytest.mark.anyio
async def test_claude_code_writes_instruction_and_passes_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    async def fake_subprocess(args, *, cwd, env, timeout, stdin=None):
        captured["args"] = list(args)
        captured["cwd"] = Path(cwd)
        captured["stdin"] = stdin
        captured["env_keys"] = sorted(env.keys())
        (Path(cwd) / "answer.md").write_text("# Test memo\n\nAnswer body.\n")
        stdout = json.dumps(
            {
                "result": "ignored fallback",
                "session_id": "s-1",
                "duration_ms": 42,
                "num_turns": 3,
            }
        )
        return 0, stdout, ""

    monkeypatch.setattr(claude_code_module, "run_subprocess", fake_subprocess)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    result = await claude_code_module.run(
        "What is the AQR for Q1 2020?",
        "anthropic/claude-sonnet-4-6",
        tmp_path,
        timeout=60.0,
    )

    assert isinstance(result, CliAgentResult)
    assert result.error is None
    assert result.exit_code == 0
    assert result.answer.startswith("# Test memo")
    assert "ANTHROPIC_API_KEY" in captured["env_keys"]
    assert captured["args"][0] == "claude"
    assert "--print" in captured["args"]
    assert "claude-sonnet-4-6" in captured["args"]
    assert "--add-dir" in captured["args"]
    assert (tmp_path / "instruction.md").read_text().startswith("What is the AQR for Q1 2020?")
    assert "answer.md" in (tmp_path / "instruction.md").read_text()
    assert result.extras["session_id"] == "s-1"
    assert result.extras["num_turns"] == "3"


@pytest.mark.anyio
async def test_claude_code_falls_back_to_stdout_when_no_answer_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_subprocess(args, *, cwd, env, timeout, stdin=None):
        del args, cwd, env, timeout, stdin
        return 0, json.dumps({"result": "Direct memo from stdout"}), ""

    monkeypatch.setattr(claude_code_module, "run_subprocess", fake_subprocess)

    result = await claude_code_module.run(
        "Some question",
        "sonnet",
        tmp_path,
        timeout=60.0,
    )

    assert result.answer == "Direct memo from stdout"
    assert result.error is None


@pytest.mark.anyio
async def test_claude_code_marks_error_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_subprocess(args, *, cwd, env, timeout, stdin=None):
        del args, cwd, env, timeout, stdin
        return 1, "", "boom: rate limited"

    monkeypatch.setattr(claude_code_module, "run_subprocess", fake_subprocess)

    result = await claude_code_module.run("q", "sonnet", tmp_path, timeout=60.0)
    assert result.exit_code == 1
    assert result.error is not None
    assert "rate limited" in result.error


@pytest.mark.anyio
async def test_codex_uses_openrouter_overrides_when_namespaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    async def fake_subprocess(args, *, cwd, env, timeout, stdin=None):
        captured["args"] = list(args)
        (Path(cwd) / "answer.md").write_text("memo body")
        return 0, "stdout text", ""

    monkeypatch.setattr(codex_module, "run_subprocess", fake_subprocess)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

    result = await codex_module.run(
        "Question", "openrouter/anthropic/claude-sonnet-4.5", tmp_path, timeout=60.0
    )

    assert result.answer == "memo body"
    args = captured["args"]
    assert args[0] == "codex"
    assert args[1] == "exec"
    assert "--model" in args
    # provider prefix stripped before -m flag
    model_idx = args.index("--model")
    assert args[model_idx + 1] == "anthropic/claude-sonnet-4.5"
    assert "model_provider=openrouter" in args
    # workdir + sandbox flags
    assert "--cd" in args
    assert "--sandbox" in args


@pytest.mark.anyio
async def test_codex_no_overrides_for_bare_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    async def fake_subprocess(args, *, cwd, env, timeout, stdin=None):
        captured["args"] = list(args)
        (Path(cwd) / "answer.md").write_text("memo")
        return 0, "", ""

    monkeypatch.setattr(codex_module, "run_subprocess", fake_subprocess)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_BENCHMARK_API_KEY", raising=False)

    await codex_module.run("Question", "gpt-5.5", tmp_path, timeout=60.0)
    args = captured["args"]
    assert "model_provider=openrouter" not in args


@pytest.mark.anyio
async def test_runner_dispatches_cli_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: build_harness with a CLI agent name skips Modal entirely."""
    from diligence_bench import runner as runner_module
    from diligence_bench.cli_agents import claude_code as claude_code_mod

    rubric_criteria = [
        {
            "id": "c1",
            "section_id": "s1",
            "weight": 1,
            "requirement": "Answer mentions revenue.",
        }
    ]
    task_dir = tmp_path / "dilbench-test"
    task_dir.mkdir()
    (task_dir / "instruction.md").write_text("Summarize Q1.")
    (task_dir / "tests").mkdir()
    (task_dir / "tests" / "rubric.json").write_text(json.dumps(rubric_criteria))

    async def fake_subprocess(args, *, cwd, env, timeout, stdin=None):
        del args, env, timeout, stdin
        (Path(cwd) / "answer.md").write_text("Revenue grew 12% YoY.")
        return 0, "", ""

    monkeypatch.setattr(claude_code_mod, "run_subprocess", fake_subprocess)

    async def fake_score(answer, criteria, query, **_kwargs):
        del answer, criteria, query
        from diligence_bench.rubric import ScoreResult

        return ScoreResult(
            score=0.75,
            section_scores={"s1": 0.75},
            verdicts=[
                {
                    "criterion_id": "c1",
                    "section_id": "s1",
                    "weight": 1,
                    "requirement": "...",
                    "verdict": "MET",
                    "reason": "ok",
                }
            ],
        )

    monkeypatch.setattr(runner_module, "score_answer", fake_score)

    harness = runner_module.build_harness(
        agent_name="claude-code",
        model="sonnet",
        judge_client=None,
        max_turns=1,
    )

    import verifiers.v1 as vf

    state = await harness.run(
        vf.Task(
            {
                "task_id": "dilbench-test",
                "prompt": [{"role": "user", "content": "Summarize Q1."}],
                "info": {
                    "task_dir": str(task_dir),
                    "datasetId": "dilbench-test",
                    "rubric": rubric_criteria,
                },
            }
        )
    )

    assert state["answer"] == "Revenue grew 12% YoY."
    assert state["reward"] == pytest.approx(0.75)
    run_items = state.get("run_items", [])
    assert len(run_items) == 1
    assert run_items[0]["item_type"] == "cli_subprocess"

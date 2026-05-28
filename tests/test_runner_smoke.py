from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from agents.sandbox import WorkspaceReadNotFoundError

from diligence_bench.harbor import DiligenceBenchAdapter
from diligence_bench.runner import _sdk_model, run_eval


@dataclass
class _FakeResult:
    final_output: str
    new_items: list
    raw_responses: list
    _current_turn: int = 1


class _FakeSandbox:
    def __init__(self) -> None:
        self.answer = "File answer"

    async def start(self) -> None:
        raise AssertionError("program should use the sandbox context manager")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def aclose(self) -> None:
        raise AssertionError("program should use the sandbox context manager")

    async def read(self, path: Path):
        assert str(path) == "/workspace/answer.md"
        return io.BytesIO(self.answer.encode("utf-8"))


class _MissingAnswerSandbox(_FakeSandbox):
    def __init__(self) -> None:
        super().__init__()
        self.answer = ""

    async def read(self, path: Path):
        assert str(path) == "/workspace/answer.md"
        if not self.answer:
            raise WorkspaceReadNotFoundError(path=path)
        return io.BytesIO(self.answer.encode("utf-8"))

    async def write(self, path: Path, data: io.BytesIO) -> None:
        assert str(path) == "/workspace/answer.md"
        self.answer = data.read().decode("utf-8")


class _FakeClient:
    def __init__(self, sandbox=None) -> None:
        self.sandbox = sandbox or _FakeSandbox()

    async def create(self, **kwargs):
        return self.sandbox


class _FakeJudge:
    pass


@pytest.mark.anyio
async def test_runner_writes_score_and_trajectory(tmp_path, monkeypatch):
    rows = [
        {
            "prompt": [{"role": "user", "content": "Question"}],
            "info": {
                "datasetId": "sample",
                "rubric": [
                    {
                        "id": "c1",
                        "section_id": "thesis",
                        "weight": 1,
                        "requirement": "Has answer",
                    }
                ],
            },
        }
    ]
    monkeypatch.setattr("diligence_bench.harbor.adapter.load_diligence_bench", lambda **_: rows)
    task_root = tmp_path / "tasks"
    DiligenceBenchAdapter(out_dir=task_root).generate()
    monkeypatch.setattr("diligence_bench.runner.build_modal_sandbox_client", lambda: _FakeClient())
    monkeypatch.setattr(
        "diligence_bench.runner.build_modal_sandbox_options", lambda timeout: object()
    )
    monkeypatch.setattr(
        "diligence_bench.runner._run_agent",
        lambda *_, **__: _async_result(_FakeResult("Model answer", [], [])),
    )
    monkeypatch.setattr(
        "diligence_bench.runner.score_answer",
        lambda *_, **__: _async_result(
            type(
                "Report",
                (),
                {
                    "score": 1.0,
                    "section_scores": {"thesis": 1.0},
                    "verdicts": [{"criterion_id": "c1", "verdict": "MET"}],
                },
            )()
        ),
    )

    results = await run_eval(
        agent_name="finance",
        model="openai/gpt-5",
        tasks_dir=task_root,
        judge_client=_FakeJudge(),
        output_dir=tmp_path / "results",
        run_id="run",
        concurrency=1,
    )

    assert results[0].score == 1.0
    score_files = list((tmp_path / "results" / "run").glob("*/scores/*.json"))
    assert len(score_files) == 1


@pytest.mark.anyio
async def test_runner_scores_zero_when_answer_file_is_empty(tmp_path, monkeypatch):
    """No chat-text fallback: an empty /workspace/answer.md is an error."""

    rows = [
        {
            "prompt": [{"role": "user", "content": "Question"}],
            "info": {
                "datasetId": "sample",
                "rubric": [
                    {"id": "c1", "section_id": "memo", "weight": 1, "requirement": "Has memo"}
                ],
            },
        }
    ]
    monkeypatch.setattr("diligence_bench.harbor.adapter.load_diligence_bench", lambda **_: rows)
    task_root = tmp_path / "tasks"
    DiligenceBenchAdapter(out_dir=task_root).generate()
    sandbox = _MissingAnswerSandbox()
    monkeypatch.setattr(
        "diligence_bench.runner.build_modal_sandbox_client",
        lambda: _FakeClient(sandbox),
    )
    monkeypatch.setattr(
        "diligence_bench.runner.build_modal_sandbox_options", lambda timeout: object()
    )
    monkeypatch.setattr(
        "diligence_bench.runner._run_agent",
        lambda *_, **__: _async_result(_FakeResult("Chat-only answer", [], [])),
    )

    results = await run_eval(
        agent_name="finance",
        model="openai/gpt-5",
        tasks_dir=task_root,
        judge_client=_FakeJudge(),
        output_dir=tmp_path / "results",
        run_id="run",
        concurrency=1,
    )

    assert results[0].answer == ""
    assert results[0].score == 0.0
    assert sandbox.answer == ""


@pytest.mark.anyio
async def test_run_eval_rejects_zero_concurrency(tmp_path):
    with pytest.raises(ValueError, match="concurrency"):
        await run_eval(
            agent_name="finance",
            model="openai/gpt-5",
            tasks_dir=tmp_path,
            judge_client=_FakeJudge(),
            run_id="run",
            concurrency=0,
        )


@pytest.mark.anyio
async def test_run_eval_marks_missing_rubric_as_error(tmp_path, monkeypatch):
    rows = [
        {
            "prompt": [{"role": "user", "content": "Question"}],
            "info": {"datasetId": "sample", "rubric": []},
        }
    ]
    monkeypatch.setattr("diligence_bench.harbor.adapter.load_diligence_bench", lambda **_: rows)
    task_root = tmp_path / "tasks"
    DiligenceBenchAdapter(out_dir=task_root).generate()
    monkeypatch.setattr("diligence_bench.runner.build_modal_sandbox_client", lambda: _FakeClient())
    monkeypatch.setattr(
        "diligence_bench.runner.build_modal_sandbox_options", lambda timeout: object()
    )
    monkeypatch.setattr(
        "diligence_bench.runner._run_agent",
        lambda *_, **__: _async_result(_FakeResult("Model answer", [], [])),
    )

    results = await run_eval(
        agent_name="finance",
        model="openai/gpt-5",
        tasks_dir=task_root,
        judge_client=_FakeJudge(),
        output_dir=tmp_path / "results",
        run_id="run",
        concurrency=1,
    )

    assert results[0].score == 0.0
    assert results[0].error is not None
    assert "missing a non-empty rubric" in results[0].error


@pytest.mark.anyio
async def test_run_eval_marks_blank_file_answer_as_error(tmp_path, monkeypatch):
    rows = [
        {
            "prompt": [{"role": "user", "content": "Question"}],
            "info": {
                "datasetId": "sample",
                "rubric": [
                    {"id": "c1", "section_id": "memo", "weight": 1, "requirement": "Has memo"}
                ],
            },
        }
    ]
    monkeypatch.setattr("diligence_bench.harbor.adapter.load_diligence_bench", lambda **_: rows)
    task_root = tmp_path / "tasks"
    DiligenceBenchAdapter(out_dir=task_root).generate()
    sandbox = _MissingAnswerSandbox()
    monkeypatch.setattr(
        "diligence_bench.runner.build_modal_sandbox_client",
        lambda: _FakeClient(sandbox),
    )
    monkeypatch.setattr(
        "diligence_bench.runner.build_modal_sandbox_options", lambda timeout: object()
    )
    # No file answer AND no model final_output → real "no answer" failure.
    monkeypatch.setattr(
        "diligence_bench.runner._run_agent",
        lambda *_, **__: _async_result(_FakeResult("", [], [])),
    )

    results = await run_eval(
        agent_name="finance",
        model="openai/gpt-5",
        tasks_dir=task_root,
        judge_client=_FakeJudge(),
        output_dir=tmp_path / "results",
        run_id="run",
        concurrency=1,
    )

    assert results[0].score == 0.0
    assert results[0].error == "agent produced no answer at /workspace/answer.md"


async def _async_result(value):
    return value


def test_openrouter_model_ids_use_chat_completions_model(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setenv("OPENROUTER_API_KEY", "key")

    model = _sdk_model("anthropic/claude-opus-4.7", FakeChatModel, FakeClient)

    assert isinstance(model, FakeChatModel)
    assert model.kwargs["model"] == "anthropic/claude-opus-4.7"
    assert model.kwargs["openai_client"].kwargs["base_url"] == "https://openrouter.ai/api/v1"


def test_namespaced_model_without_openrouter_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_BENCHMARK_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER"):
        _sdk_model("openai/gpt-5", object, object)


def test_bare_model_without_openai_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        _sdk_model("gpt-5", object, object)


def test_bare_model_with_openai_key_returns_id(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    assert _sdk_model("gpt-5", object, object) == "gpt-5"


@pytest.mark.anyio
async def test_run_agent_connects_mcp_servers_before_runner_run(monkeypatch):
    """Catch the connect-not-called class of bug at unit-test time.

    The OpenAI Agents SDK requires every MCPServerStdio passed to a
    SandboxAgent to be entered via async context before Runner.run lists its
    tools. A regression here surfaces in production as
    `UserError: Server not initialized. Make sure you call connect() first.`
    """
    import diligence_bench.runner as runner_module
    import diligence_bench.tools.final_answer  # noqa: F401

    server_states: list[dict] = []

    class FakeMCPServer:
        def __init__(self, name: str) -> None:
            self.name = name
            self.connected = False
            self.disconnected = False

        async def __aenter__(self):
            self.connected = True
            server_states.append({"name": self.name, "phase": "enter", "agent_running": False})
            return self

        async def __aexit__(self, *exc):
            self.disconnected = True
            return False

    class FakeAgent:
        def __init__(self) -> None:
            self.mcp_servers = [FakeMCPServer("sec_edgar"), FakeMCPServer("web_search")]

    captured = {}

    async def fake_run(agent, *, input, max_turns, run_config, **_kwargs):
        del input, max_turns, run_config
        captured["agent"] = agent
        for server in agent.mcp_servers:
            assert server.connected, f"{server.name} not connected before Runner.run"
        return SimpleNamespace(final_output="ok", new_items=[])

    class FakeRunner:
        run = staticmethod(fake_run)
        run_streamed = None

    monkeypatch.setattr(runner_module, "_sdk_model", lambda *_args, **_kwargs: "gpt-5")
    fake_agents = SimpleNamespace(
        OpenAIChatCompletionsModel=object,
        Runner=FakeRunner,
        RunContextWrapper=object,
        function_tool=lambda **_: lambda fn: fn,
    )
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    monkeypatch.setitem(
        sys.modules,
        "agents.run",
        SimpleNamespace(RunConfig=lambda **kwargs: kwargs),
    )
    monkeypatch.setitem(
        sys.modules,
        "agents.run_error_handlers",
        SimpleNamespace(RunErrorHandlerResult=lambda **kwargs: kwargs),
    )
    monkeypatch.setitem(
        sys.modules,
        "agents.sandbox",
        SimpleNamespace(SandboxRunConfig=lambda **kwargs: kwargs),
    )
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=object))

    sandbox = SimpleNamespace(
        read=lambda _path: (_ for _ in ()).throw(FileNotFoundError()),
        write=lambda *_: _async_result(None),
    )
    agent = FakeAgent()
    from diligence_bench.sampling import SamplingPolicy

    result = await runner_module._run_agent(agent, "task", "gpt-5", sandbox, 5, SamplingPolicy())

    assert result.final_output == "ok"
    assert all(server.connected for server in agent.mcp_servers)
    assert all(server.disconnected for server in agent.mcp_servers)


@pytest.mark.anyio
async def test_run_eval_resumes_completed_tasks(tmp_path, monkeypatch, caplog):
    """Re-running with the same run_id must skip tasks that already have a
    successful score JSON on disk."""
    import logging

    rows = [
        {
            "prompt": [{"role": "user", "content": f"Question {i}"}],
            "info": {
                "datasetId": f"sample-{i}",
                "rubric": [
                    {"id": "c1", "section_id": "memo", "weight": 1, "requirement": "Has memo"}
                ],
            },
        }
        for i in range(3)
    ]
    monkeypatch.setattr("diligence_bench.harbor.adapter.load_diligence_bench", lambda **_: rows)
    task_root = tmp_path / "tasks"
    DiligenceBenchAdapter(out_dir=task_root).generate()

    monkeypatch.setattr("diligence_bench.runner.build_modal_sandbox_client", lambda: _FakeClient())
    monkeypatch.setattr(
        "diligence_bench.runner.build_modal_sandbox_options", lambda timeout: object()
    )
    monkeypatch.setattr(
        "diligence_bench.runner._run_agent",
        lambda *_, **__: _async_result(_FakeResult("Model answer", [], [])),
    )
    monkeypatch.setattr(
        "diligence_bench.runner.score_answer",
        lambda *_, **__: _async_result(
            type(
                "Report",
                (),
                {"score": 0.5, "section_scores": {"memo": 0.5}, "verdicts": []},
            )()
        ),
    )

    common = dict(
        agent_name="finance",
        model="openai/gpt-5",
        tasks_dir=task_root,
        judge_client=_FakeJudge(),
        output_dir=tmp_path / "results",
        run_id="resume-run",
        concurrency=2,
    )

    first = await run_eval(**common)
    assert len(first) == 3
    assert all(result.score == 0.5 for result in first)

    caplog.set_level(logging.INFO, logger="diligence_bench.runner")
    second = await run_eval(**common)

    assert len(second) == 3
    assert all(result.score == 0.5 for result in second)
    skip_logs = [
        record.message for record in caplog.records if record.message.startswith("skip sample-")
    ]
    assert len(skip_logs) == 3, f"expected 3 skip logs, got {skip_logs}"
    resume_logs = [record.message for record in caplog.records if "Resuming run" in record.message]
    assert len(resume_logs) == 1

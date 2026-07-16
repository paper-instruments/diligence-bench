from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import verifiers.v1 as vf
from agents.sandbox import WorkspaceReadNotFoundError

from diligence_bench.ablations import variant_name
from diligence_bench.agents import AGENTS
from diligence_bench.cli_agents import CLI_AGENTS, CliAgentResult
from diligence_bench.harbor.loader import load_tasks_from_dir
from diligence_bench.results import EvalResult, ResultsWriter
from diligence_bench.rubric import score as score_answer
from diligence_bench.sampling import (
    SamplingPolicy,
    build_model_settings,
    resolve_sampling,
)
from diligence_bench.sandbox import (
    build_modal_sandbox_client,
    build_modal_sandbox_options,
)

logger = logging.getLogger(__name__)

ANSWER_PATH = Path("/workspace/answer.md")
DEFAULT_JUDGE_MODEL = "openai/gpt-5.5"


def build_harness(
    agent_name: str,
    model: str,
    *,
    judge_client: Any,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    judge_sampling_args: Mapping[str, Any] | None = None,
    sampling_policy: SamplingPolicy | None = None,
    max_turns: int = 200,
) -> vf.Harness:
    policy = sampling_policy if sampling_policy is not None else resolve_sampling(model)
    if agent_name in CLI_AGENTS:
        program = _build_cli_program(agent_name, model, max_turns)
    elif agent_name in AGENTS:
        program = _build_sandbox_agent_program(agent_name, model, max_turns, policy)
    else:
        raise KeyError(
            f"Unknown agent {agent_name!r}. Known: {sorted(set(AGENTS) | set(CLI_AGENTS))}"
        )

    async def reward(task: vf.Task, state: vf.State) -> float:
        del task
        info = state.get("info", {})
        if not isinstance(info, Mapping):
            raise ValueError("task info is missing or malformed")
        criteria = info.get("rubric")
        if not isinstance(criteria, list) or not criteria:
            dataset_id = info.get("datasetId") or info.get("task_id") or "unknown"
            raise ValueError(f"task {dataset_id!r} is missing a non-empty rubric")
        agent_error = state.get("agent_error")
        if agent_error:
            state["diligence_error"] = str(agent_error)
            return 0.0
        if not str(state.get("answer", "")).strip():
            state["diligence_error"] = "agent produced no answer at /workspace/answer.md"
            return 0.0
        query = _query_from_state(state)
        report = await score_answer(
            str(state.get("answer", "")),
            criteria,
            query,
            judge_client=judge_client,
            judge_model=judge_model,
            judge_sampling_args=dict(judge_sampling_args or {}),
        )
        state["judge_verdicts"] = report.verdicts
        state["section_scores"] = report.section_scores
        return report.score

    return vf.Harness(
        program=program,
        rewards=[reward],
        model=model,
        max_turns=max_turns,
    )


async def run_eval(
    *,
    agent_name: str,
    model: str,
    tasks_dir: str | Path,
    judge_client: Any,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    output_dir: str | Path = "results",
    run_id: str,
    examples: int = -1,
    concurrency: int = 3,
    judge_sampling_args: Mapping[str, Any] | None = None,
    sampling_overrides: Mapping[str, Any] | None = None,
    progress_stream: Any = None,
) -> list[EvalResult]:
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    tasks = load_tasks_from_dir(tasks_dir, limit=examples)
    result_model = variant_name(agent_name, model)
    writer = ResultsWriter(Path(output_dir), run_id)
    policy = resolve_sampling(model, cli_overrides=dict(sampling_overrides or {}))
    logger.info("Sampling policy [%s]: %s", result_model, policy.describe())
    harness = build_harness(
        agent_name,
        model,
        judge_client=judge_client,
        judge_model=judge_model,
        judge_sampling_args=judge_sampling_args,
        sampling_policy=policy,
    )
    semaphore = asyncio.Semaphore(concurrency)

    already_done = sum(
        1
        for task in tasks
        if writer.read_successful(result_model, str(task["info"]["datasetId"])) is not None
    )
    remaining = len(tasks) - already_done
    if already_done:
        logger.info(
            "Resuming run %s [%s]: %d/%d already complete, %d remaining",
            run_id,
            result_model,
            already_done,
            len(tasks),
            remaining,
        )
    else:
        logger.info("Run %s [%s]: %d task(s) to process", run_id, result_model, len(tasks))
    progress = _Progress(total=len(tasks), stream=progress_stream)

    async def run_one(task: Mapping[str, Any]) -> EvalResult:
        async with semaphore:
            dataset_id = str(task["info"]["datasetId"])
            existing = writer.read_successful(result_model, dataset_id)
            if existing is not None:
                logger.info(
                    "skip %s [%s]: existing score %.3f",
                    dataset_id,
                    result_model,
                    existing.score,
                )
                progress.tick(dataset_id, status="skip")
                return existing
            try:
                state = await harness.run(task)
                result = _result_from_state(
                    state,
                    run_id=run_id,
                    model=result_model,
                    underlying_model=model,
                    harness=harness_label(agent_name),
                    judge_model=judge_model,
                )
                await writer.write(result, trajectory=_trajectory_from_state(state))
                progress.tick(dataset_id, status="done", score=result.score)
                return result
            except Exception as exc:
                logger.exception("Task %s failed for model %s", dataset_id, model)
                result = EvalResult(
                    run_id=run_id,
                    model=result_model,
                    dataset_id=dataset_id,
                    query=_query_from_task(task),
                    answer="",
                    score=0.0,
                    section_scores={},
                    verdicts=[],
                    num_turns=0,
                    judge_model=judge_model,
                    error=str(exc) or type(exc).__name__,
                    underlying_model=model,
                    harness=harness_label(agent_name),
                )
                await writer.write(result, trajectory=[])
                progress.tick(dataset_id, status="error")
                return result

    try:
        results = await asyncio.gather(*(run_one(task) for task in tasks))
        return list(results)
    finally:
        progress.finish()
        await harness.teardown()


async def _run_agent(
    agent: Any,
    instruction: str,
    model: str,
    sandbox: Any,
    max_turns: int,
    sampling_policy: SamplingPolicy,
) -> Any:
    from contextlib import AsyncExitStack

    from agents import OpenAIChatCompletionsModel, Runner
    from agents.model_settings import ModelSettings
    from agents.run import RunConfig
    from agents.run_error_handlers import RunErrorHandlerResult
    from agents.sandbox import SandboxRunConfig
    from openai import AsyncOpenAI

    from diligence_bench.tools.final_answer import FinalAnswerContext

    final_answer_context = FinalAnswerContext(sandbox=sandbox)

    run_config = RunConfig(
        model=_sdk_model(model, OpenAIChatCompletionsModel, AsyncOpenAI),
        sandbox=SandboxRunConfig(session=sandbox),
        workflow_name="diligence-bench eval",
        model_settings=_openrouter_model_settings(model, ModelSettings, sampling_policy),
    )

    async def _compaction_handler(_inp: Any) -> RunErrorHandlerResult:
        return RunErrorHandlerResult(final_output=_COMPACTION_SENTINEL, include_in_history=False)

    error_handlers = {"max_turns": _compaction_handler}

    async with AsyncExitStack() as stack:
        for server in getattr(agent, "mcp_servers", None) or []:
            await stack.enter_async_context(server)

        current_input: Any = instruction
        aggregated_new_items: list[Any] = []
        usage_totals = _new_usage_totals()
        last_result: Any = None
        turns_remaining = max_turns
        while turns_remaining > 0:
            batch = min(_BATCH_TURNS, turns_remaining)
            result = await Runner.run(
                agent,
                input=current_input,
                max_turns=batch,
                run_config=run_config,
                error_handlers=error_handlers,
                context=final_answer_context,
            )
            last_result = result
            aggregated_new_items.extend(getattr(result, "new_items", []) or [])
            _accumulate_usage(usage_totals, result)
            turns_remaining -= batch
            if getattr(result, "final_output", None) is not _COMPACTION_SENTINEL:
                if await _read_answer(sandbox) or turns_remaining <= 0:
                    break
                logger.warning(
                    "agent stopped without answer.md (%d turns remaining); nudging",
                    turns_remaining,
                )
            next_input = result.to_input_list()
            if _estimated_input_chars(next_input) > _COMPACTION_CHAR_BUDGET:
                next_input = _compact_input_items(next_input, keep_recent=_KEEP_RECENT_TOOL_OUTPUTS)
            if not await _read_answer(sandbox):
                next_input = _append_turn_budget_nudge(next_input, turns_remaining)
            current_input = next_input

        if last_result is not None:
            with contextlib.suppress(AttributeError, TypeError):
                last_result.new_items = aggregated_new_items  # type: ignore[attr-defined]
            with contextlib.suppress(AttributeError, TypeError):
                last_result._diligence_usage = usage_totals  # type: ignore[attr-defined]
        return last_result


_USAGE_FIELDS = ("input_tokens", "output_tokens", "total_tokens")


def _new_usage_totals() -> dict[str, int]:
    return dict.fromkeys(_USAGE_FIELDS, 0)


def _accumulate_usage(totals: dict[str, int], result: Any) -> None:
    usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
    if usage is None:
        return
    for field in _USAGE_FIELDS:
        totals[field] += int(getattr(usage, field, 0) or 0)


_COMPACTION_SENTINEL = object()
_BATCH_TURNS = 40
_COMPACTION_CHAR_BUDGET = 600_000  # ~150K tokens, well under Gemini's 1M cap
_KEEP_RECENT_TOOL_OUTPUTS = 8
_TRIMMED_OUTPUT_STUB = (
    "[earlier tool output trimmed to fit context window — re-call the tool if you need it again]"
)
_TURN_BUDGET_NUDGE_SOFT = (
    "You stopped without writing your final memo to /workspace/answer.md. "
    "Write the complete memo there now."
)
_TURN_BUDGET_NUDGE_HARD = (
    "You are almost out of turns and have not written your memo to "
    "/workspace/answer.md. Write it now."
)


def _append_turn_budget_nudge(input_items: Any, turns_remaining: int) -> list[Any]:
    items = list(input_items) if isinstance(input_items, list) else [input_items]
    nudge = (
        _TURN_BUDGET_NUDGE_HARD if turns_remaining <= _BATCH_TURNS // 2 else _TURN_BUDGET_NUDGE_SOFT
    )
    items.append({"role": "user", "content": nudge})
    logger.warning("injected turn-budget nudge (%d turns remaining)", turns_remaining)
    return items


def _estimated_input_chars(items: Sequence[Any]) -> int:
    total = 0
    for item in items:
        if isinstance(item, Mapping):
            for key in ("content", "output", "text"):
                value = item.get(key)
                if isinstance(value, str):
                    total += len(value)
                elif isinstance(value, list):
                    for piece in value:
                        if isinstance(piece, Mapping):
                            text = piece.get("text") or piece.get("output") or ""
                            if isinstance(text, str):
                                total += len(text)
    return total


def _compact_input_items(items: Sequence[Any], *, keep_recent: int) -> list[Any]:
    items_list = list(items)
    tool_output_idxs = [
        i
        for i, it in enumerate(items_list)
        if isinstance(it, Mapping) and it.get("type") == "function_call_output"
    ]
    trim_until = max(0, len(tool_output_idxs) - keep_recent)
    targets = set(tool_output_idxs[:trim_until])
    compacted: list[Any] = []
    for i, item in enumerate(items_list):
        if i in targets and isinstance(item, Mapping):
            new_item = dict(item)
            new_item["output"] = _TRIMMED_OUTPUT_STUB
            compacted.append(new_item)
        else:
            compacted.append(item)
    return compacted


def _openrouter_model_settings(
    model: str,
    model_settings_cls: Any,
    policy: SamplingPolicy,
) -> Any:
    """Build ModelSettings carrying our sampling policy plus provider routing."""
    return build_model_settings(model, policy, model_settings_cls)


def _sdk_model(model: str, chat_model_cls: Any, client_cls: Any) -> Any:
    """Build an SDK model object for the requested model id.

    Routing rules:
    - ``provider/model`` ids (anything containing ``/``) require an OpenRouter
      key in the environment. We route through OpenRouter using the full id
      verbatim.
    - bare model ids (``gpt-5``, ``claude-opus-4.7``) require ``OPENAI_API_KEY``
      and use the SDK's default OpenAI client.
    - in either case, missing credentials raise immediately so a 50-task batch
      doesn't silently fail at the first model call.
    """
    if "/" in model:
        api_key = os.getenv("OPENROUTER_BENCHMARK_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                f"model {model!r} is provider-namespaced but neither "
                "OPENROUTER_BENCHMARK_API_KEY nor OPENROUTER_API_KEY is set"
            )
        return chat_model_cls(
            model=model,
            openai_client=client_cls(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            ),
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            f"model {model!r} is a bare id; set OPENAI_API_KEY or use a "
            "namespaced id like 'openai/gpt-5' to route through OpenRouter"
        )
    return model


async def _read_answer(sandbox: Any) -> str:
    try:
        data = await sandbox.read(ANSWER_PATH)
    except (FileNotFoundError, WorkspaceReadNotFoundError):
        return ""
    raw = data.read()
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace").strip()
    return str(raw).strip()


def _result_from_state(
    state: Mapping[str, Any],
    *,
    run_id: str,
    model: str,
    underlying_model: str,
    harness: str,
    judge_model: str,
) -> EvalResult:
    info = state.get("info", {})
    dataset_id = str(info.get("datasetId", "")) if isinstance(info, Mapping) else ""
    usage = state.get("usage", {}) if isinstance(state.get("usage"), Mapping) else {}
    return EvalResult(
        run_id=run_id,
        model=model,
        dataset_id=dataset_id,
        query=_query_from_state(state),
        answer=str(state.get("answer", "")),
        score=float(state.get("reward", 0.0) or 0.0),
        section_scores=dict(state.get("section_scores", {}) or {}),
        verdicts=list(state.get("judge_verdicts", []) or []),
        num_turns=int(state.get("num_turns", 0) or 0),
        judge_model=judge_model,
        error=_state_error(state),
        underlying_model=underlying_model,
        harness=harness,
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        total_tokens=int(usage.get("total_tokens", 0) or 0),
    )


def _query_from_state(state: Mapping[str, Any]) -> str:
    prompt = state.get("prompt", [])
    if isinstance(prompt, Sequence) and not isinstance(prompt, str | bytes):
        return _content_from_messages(prompt)
    info = state.get("info", {})
    if isinstance(info, Mapping) and info.get("task_dir"):
        return (Path(str(info["task_dir"])) / "instruction.md").read_text(encoding="utf-8")
    return ""


def _query_from_task(task: Mapping[str, Any]) -> str:
    prompt = task.get("prompt", [])
    if isinstance(prompt, Sequence) and not isinstance(prompt, str | bytes):
        return _content_from_messages(prompt)
    return ""


def _content_from_messages(messages: Sequence[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, Mapping) and message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _trajectory_from_state(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = state.get("run_items", [])
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _state_error(state: Mapping[str, Any]) -> str | None:
    error = state.get("diligence_error") or state.get("error")
    if error:
        return str(error)
    return None


def _serializable_run_items(items: object) -> list[dict[str, Any]]:
    if not isinstance(items, Sequence) or isinstance(items, str | bytes):
        return []
    serialized = []
    for item in items:
        dump = getattr(item, "model_dump", None)
        if callable(dump):
            value = dump()
        elif isinstance(item, Mapping):
            value = dict(item)
        else:
            value = {"item": str(item)}
        if isinstance(value, dict):
            serialized.append(value)
    return serialized


def _num_turns(result: Any) -> int:
    value = getattr(result, "_current_turn", None)
    if isinstance(value, int):
        return value
    raw_responses = getattr(result, "raw_responses", None)
    if isinstance(raw_responses, Sequence):
        return len(raw_responses)
    return 0


def harness_label(agent_name: str) -> str:
    if agent_name in CLI_AGENTS:
        return f"cli-{agent_name}"
    return agent_name


def _build_sandbox_agent_program(
    agent_name: str,
    model: str,
    max_turns: int,
    sampling_policy: SamplingPolicy,
):
    async def program(task: vf.Task, state: vf.State) -> vf.State:
        task_dir = Path(str(task["info"]["task_dir"]))
        instruction = (task_dir / "instruction.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="diligence-bench-agent-") as tempdir:
            agent = AGENTS[agent_name](Path(tempdir))
            client = build_modal_sandbox_client()
            options = build_modal_sandbox_options(timeout=max_turns * 60)
            sandbox = await client.create(
                manifest=getattr(agent, "default_manifest", None),
                options=options,
            )
            async with sandbox:
                result = await _run_agent(
                    agent,
                    instruction,
                    model,
                    sandbox,
                    max_turns,
                    sampling_policy,
                )
                answer = await _read_answer(sandbox)

        state["answer"] = answer
        state["completion"] = [{"role": "assistant", "content": answer}]
        state["run_items"] = _serializable_run_items(getattr(result, "new_items", None))
        state["num_turns"] = _num_turns(result)
        state["usage"] = getattr(result, "_diligence_usage", None) or {}
        state["info"] = dict(task["info"])
        return state

    return program


def _build_cli_program(agent_name: str, model: str, max_turns: int):
    runner = CLI_AGENTS[agent_name]
    timeout_sec = max_turns * 60.0

    async def program(task: vf.Task, state: vf.State) -> vf.State:
        task_dir = Path(str(task["info"]["task_dir"]))
        instruction = (task_dir / "instruction.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="diligence-bench-cli-") as tempdir:
            workdir = Path(tempdir)
            cli_result: CliAgentResult = await runner(
                instruction, model, workdir, timeout=timeout_sec
            )

        state["answer"] = cli_result.answer
        state["completion"] = [{"role": "assistant", "content": cli_result.answer}]
        state["run_items"] = [_cli_run_item(cli_result)]
        state["num_turns"] = int(cli_result.extras.get("num_turns") or 0)
        if cli_result.error:
            state["agent_error"] = cli_result.error
        state["info"] = dict(task["info"])
        return state

    return program


def _cli_run_item(result: CliAgentResult) -> dict[str, Any]:
    return {
        "item_type": "cli_subprocess",
        "exit_code": result.exit_code,
        "stdout_preview": result.stdout[-2000:],
        "stderr_preview": result.stderr[-2000:],
        "error": result.error,
        "extras": result.extras,
    }


class _Progress:
    """ASCII progress reporter for batch eval runs.

    Renders a single-line bar to ``stream`` (defaults to stderr) that updates
    in place after each task completes. Each tick logs a structured line as
    well so the final answer JSON files reveal a per-task audit trail.
    """

    _BAR_WIDTH = 30

    def __init__(self, *, total: int, stream: Any = None) -> None:
        import sys

        self._total = total
        self._done = 0
        self._stream = stream or sys.stderr
        self._closed = False

    def tick(
        self,
        dataset_id: str,
        *,
        status: str,
        score: float | None = None,
    ) -> None:
        self._done += 1
        score_part = f" score={score:.3f}" if score is not None else ""
        logger.info("[%d/%d] %s %s%s", self._done, self._total, status, dataset_id, score_part)
        self._render()

    def finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._render(final=True)

    def _render(self, *, final: bool = False) -> None:
        if self._total <= 0:
            return
        ratio = min(self._done / self._total, 1.0)
        filled = int(self._BAR_WIDTH * ratio)
        bar = "#" * filled + "-" * (self._BAR_WIDTH - filled)
        line = f"\r  [{bar}] {self._done}/{self._total} ({ratio * 100:.0f}%)"
        end = "\n" if final else ""
        try:
            self._stream.write(line + end)
            self._stream.flush()
        except Exception:  # pragma: no cover - defensive
            pass

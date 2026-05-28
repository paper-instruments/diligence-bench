from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

from diligence_bench.ablations import append_ablation_row, build_ablation_row, variant_name
from diligence_bench.agents import AGENTS
from diligence_bench.cli_agents import CLI_AGENTS
from diligence_bench.harbor import DiligenceBenchAdapter
from diligence_bench.harbor.adapter import DEFAULT_VERIFIER_MODEL
from diligence_bench.report import generate_report
from diligence_bench.runner import DEFAULT_JUDGE_MODEL, harness_label, run_eval
from diligence_bench.summary import print_summary

_AGENT_DESCRIPTIONS: dict[str, str] = {
    "loop": "H1: bare baseline (web tools + final_answer, no capabilities)",
    "sandbox": "H2: generic CLI agent (web + Shell + apply_patch)",
    "finance": "H3: domain agent (H2 + SEC MCP + skills + finance prompt)",
    "claude-code": "Claude Code CLI (vanilla, model picked via --models)",
    "codex": "Codex CLI (vanilla, model picked via --models)",
    "gemini": "Gemini CLI (vanilla, model picked via --models)",
}

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    load_dotenv(override=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in (
        "httpx",
        "httpcore",
        "mcp",
        "mcp.server",
        "mcp.server.lowlevel.server",
        "openai.agents.tracing",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    args = build_parser().parse_args(argv)
    if args.command == "build-tasks":
        DiligenceBenchAdapter(
            out_dir=args.out,
            num_examples=args.examples,
            verifier_model=args.verifier_model,
        ).generate()
        return
    if args.command == "list-agents":
        for name in sorted(set(AGENTS) | set(CLI_AGENTS)):
            print(f"{name}\t{_AGENT_DESCRIPTIONS.get(name, '')}")
        return
    if args.command == "eval":
        asyncio.run(_run_eval_command(args))
        return
    raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="diligence-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_tasks = subparsers.add_parser("build-tasks")
    build_tasks.add_argument("--out", default="datasets/diligence-bench")
    build_tasks.add_argument("--examples", type=int, default=-1)
    build_tasks.add_argument("--verifier-model", default=DEFAULT_VERIFIER_MODEL)

    evaluate = subparsers.add_parser("eval")
    evaluate.add_argument(
        "--agent",
        default="finance",
        choices=sorted(set(AGENTS) | set(CLI_AGENTS)),
    )
    evaluate.add_argument("--models", required=True)
    evaluate.add_argument("--tasks-dir", default="datasets/diligence-bench")
    evaluate.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    evaluate.add_argument("--concurrency", type=_positive_int, default=3)
    evaluate.add_argument("--output", default="results")
    evaluate.add_argument("--ablation-name", default=None)
    evaluate.add_argument("--run-id", default=None)
    evaluate.add_argument("--examples", type=int, default=-1)
    evaluate.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Override sampling temperature for all models in this run.",
    )
    evaluate.add_argument(
        "--reasoning-effort",
        choices=["minimal", "low", "medium", "high"],
        default=None,
        help="Override reasoning effort for all models in this run.",
    )
    evaluate.add_argument(
        "--verbosity",
        choices=["low", "medium", "high"],
        default=None,
        help="Override verbosity for all models in this run.",
    )
    subparsers.add_parser("list-agents")
    return parser


async def _run_eval_command(args: argparse.Namespace) -> None:
    from openai import AsyncOpenAI

    from diligence_bench.sampling import resolve_sampling

    models = [model.strip() for model in args.models.split(",") if model.strip()]
    if not models:
        raise SystemExit("--models must include at least one model")
    run_id = args.run_id or _run_id()
    output_dir = Path(args.output)
    judge_client = _judge_client(AsyncOpenAI, args.judge_model)
    sampling_overrides = _sampling_overrides_from_args(args)
    all_results = []
    for model in models:
        policy = resolve_sampling(model, cli_overrides=sampling_overrides)
        results = await run_eval(
            agent_name=args.agent,
            model=model,
            tasks_dir=args.tasks_dir,
            judge_client=judge_client,
            judge_model=args.judge_model,
            output_dir=output_dir,
            run_id=run_id,
            examples=args.examples,
            concurrency=args.concurrency,
            judge_sampling_args={"temperature": 1.0, "reasoning": {"effort": "minimal"}},
            sampling_overrides=sampling_overrides,
            progress_stream=sys.stderr,
        )
        all_results.extend(results)
        row = build_ablation_row(
            results,
            ablation_name=args.ablation_name or run_id,
            run_id=run_id,
            variant=variant_name(args.agent, model),
            harness=harness_label(args.agent),
            underlying_model=model,
            judge_model=args.judge_model,
            dataset="diligence-bench",
            examples=len(results),
            run_dir=output_dir / run_id,
            sampling_temperature=policy.temperature,
            sampling_reasoning_effort=policy.reasoning_effort,
            sampling_verbosity=policy.verbosity,
        )
        append_ablation_row(output_dir / "ablations.csv", row)
    del all_results
    print_summary(output_dir / run_id, stream=sys.stdout)

    report_path = generate_report(output_dir / run_id)
    if report_path:
        logger.info("HTML report: %s", report_path)


def _judge_client(client_cls, judge_model: str):
    api_key = os.getenv("OPENROUTER_BENCHMARK_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if api_key:
        return client_cls(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    if "/" in judge_model:
        raise SystemExit(
            "OpenRouter-style judge models require OPENROUTER_BENCHMARK_API_KEY "
            "or OPENROUTER_API_KEY; otherwise use a provider-native OpenAI model id."
        )
    return client_cls()


def _sampling_overrides_from_args(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if args.temperature is not None:
        overrides["temperature"] = args.temperature
    if args.reasoning_effort is not None:
        overrides["reasoning_effort"] = args.reasoning_effort
    if args.verbosity is not None:
        overrides["verbosity"] = args.verbosity
    return overrides


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%f")
    return f"{stamp}-{uuid4().hex[:8]}"


if __name__ == "__main__":
    main()

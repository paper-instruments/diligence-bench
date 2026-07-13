# diligence-bench

Public benchmark runner for [Diligence Bench](https://huggingface.co/datasets/tldc/diligence-bench)
— an agentic financial diligence benchmark.

The repo has two outputs:

- A Harbor task suite under `datasets/diligence-bench/`.
- A reference eval runner built on `verifiers.v1.Harness`. It supports both
  OpenAI Agents SDK `SandboxAgent`s on Modal (under `agents/`) and vendor CLI
  agents like Claude Code and Codex (under `cli_agents/`).

## Quickstart

```bash
uv sync
cp .env.example .env
uv run diligence-bench build-tasks --examples 5
uv run diligence-bench eval --models openai/gpt-5.5 --examples 5
```

Required for real eval runs:

- `OPENAI_API_KEY` or `OPENROUTER_API_KEY` for the model and judge.
- `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` for Modal sandboxes.
- `EXA_API_KEY` for web search.
- `SEC_USER_AGENT` with a contact address for SEC EDGAR requests.

## Commands

```bash
uv run diligence-bench build-tasks --out datasets/diligence-bench --examples 5
uv run diligence-bench eval --models openai/gpt-5.5,anthropic/claude-opus-4.7
```

`build-tasks` converts HuggingFace rows into Harbor task directories. `eval`
reads those same task directories, runs the selected agent, writes per-example
JSON under `results/<run-id>/`, and appends aggregate rows to
`results/ablations.csv`.

### Picking an agent

`--agent` defaults to `finance` (the OpenAI Agents SDK reference agent on
Modal). To run a vendor CLI agent instead:

```bash
uv run diligence-bench eval --agent claude-code --models anthropic/claude-opus-4.7
uv run diligence-bench eval --agent codex --models openai/gpt-5.5
uv run diligence-bench eval --agent gemini --models google/gemini-3-pro
```

### Sweeping models

Pass a comma-separated list to `--models`. Each model runs as its own variant
under the same `run-id` and gets its own row in `ablations.csv`:

```bash
uv run diligence-bench eval \
  --agent finance \
  --models openai/gpt-5.5,anthropic/claude-opus-4.7,google/gemini-3-pro \
  --ablation-name model-sweep-2026-06
```

### Sampling overrides

Override sampling for every model in the run with `--temperature`,
`--reasoning-effort` (`minimal|low|medium|high`), or `--verbosity`
(`low|medium|high`). Defaults are resolved per-model in `sampling.py`.

### Other useful flags

- `--examples N` — cap the number of tasks (default: all).
- `--concurrency N` — parallel tasks per model (default: 3).
- `--judge-model` — override the rubric judge model.
- `--tasks-dir` — read tasks from a non-default directory.
- `--ablation-name` — label this run in `ablations.csv` (defaults to run id).
- `--output` — results root (default: `results`).

### Resuming a run

Pass `--run-id <id>` to reuse an existing run directory. Tasks that already
have a non-error score JSON under `results/<id>/<variant>/scores/` are skipped
and reported as `skip` in the progress log; remaining tasks run normally:

```bash
uv run diligence-bench eval --models openai/gpt-5.5 --run-id 2026-05-18T05-13-10-926339-b31e96b3
# Resuming run 2026-05-18T05-13-10-926339-b31e96b3 [finance__openai_gpt-5.5]: 23/50 already complete, 27 remaining
#   [############------------------] 23/50 (46%)
# skip dilbench-rubicon-... [finance__openai_gpt-5.5]: existing score 0.421
```

Per-task progress is rendered to stderr.

## Development

```bash
uv run pytest
uv run ruff check src tests
```

## License

Released under [Apache-2.0](LICENSE).

© 2026 Paper Instruments, Inc. and Thoughtful Lab, Inc.

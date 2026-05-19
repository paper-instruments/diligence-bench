# diligence-bench

Public benchmark runner for `tldc/diligence-bench`.

The repo has two outputs:

- A Harbor task suite under `datasets/diligence-bench/`.
- A reference eval runner that uses one path: `verifiers.v1.Harness` plus an
  OpenAI Agents SDK `SandboxAgent` running on `ModalSandboxClient`.

## Quickstart

```bash
uv sync
cp .env.example .env
uv run diligence-bench build-tasks --examples 5
uv run diligence-bench eval --models openai/gpt-5 --examples 5
```

Required for real eval runs:

- `OPENAI_API_KEY` or `OPENROUTER_API_KEY` for the model and judge.
- `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` for Modal sandboxes.
- `EXA_API_KEY` for web search.
- `SEC_USER_AGENT` with a contact address for SEC EDGAR requests.

## Commands

```bash
uv run diligence-bench list-agents
uv run diligence-bench build-tasks --out datasets/diligence-bench --examples 5
uv run diligence-bench eval --models openai/gpt-5,anthropic/claude-opus-4.7
```

`build-tasks` converts HuggingFace rows into Harbor task directories. `eval`
reads those same task directories, runs the `finance` reference agent, writes
per-example JSON under `results/<run-id>/`, and appends aggregate rows to
`results/ablations.csv`.

### Resuming a run

Pass `--run-id <id>` to reuse an existing run directory. Tasks that already
have a non-error score JSON under `results/<id>/<variant>/scores/` are skipped
and reported as `skip` in the progress log; remaining tasks run normally. Use
this after a crash, ctrl-C, or rate-limit storm:

```bash
uv run diligence-bench eval --models openai/gpt-5 --run-id 2026-05-18T05-13-10-926339-b31e96b3
# Resuming run 2026-05-18T05-13-10-926339-b31e96b3 [finance__openai_gpt-5]: 23/50 already complete, 27 remaining
#   [############------------------] 23/50 (46%)
# skip dilbench-rubicon-... [finance__openai_gpt-5]: existing score 0.421
# ...
```

Per-task progress is rendered to stderr.

## Architecture

See:

- [docs/architecture.md](docs/architecture.md)
- [docs/adding-an-agent.md](docs/adding-an-agent.md)
- [docs/adding-a-tool.md](docs/adding-a-tool.md)
- [docs/verifiers-vs-sdk.md](docs/verifiers-vs-sdk.md)

## Development

```bash
uv run pytest
uv run ruff check src tests
```

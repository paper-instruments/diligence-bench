# diligence-bench

A public benchmark for agentic financial diligence. Loads `tldc/diligence-bench`
from HuggingFace, publishes it as a Harbor task suite, and ships a reference
OpenAI Agents SDK `SandboxAgent` that runs each task on Modal and is graded
against a per-criterion rubric.

## Quick commands

```bash
uv sync                                                    # install
uv run diligence-bench list-agents                         # list agents
uv run diligence-bench build-tasks --examples 5            # generate Harbor tasks
uv run diligence-bench eval --models openai/gpt-5 --examples 5
uv run pytest                                              # tests
uv run ruff check src/ tests/                              # lint
uv run ruff format src/ tests/                             # format
```

## Repo map

```
src/diligence_bench/
  cli.py                   build-tasks | eval | list-agents
  dataset.py               HF loader → canonical rows
  rubric.py                per-criterion judge (MET/UNMET, weighted, sections)
  results.py               EvalResult + ResultsWriter
  ablations.py             AblationRow + append-only CSV
  runner.py                vf.harness program: read task dir, run SandboxAgent, score
  sandbox.py               build_modal_sandbox_client()
  agents/
    finance/               build_agent(workdir) → SandboxAgent (OpenAI Agents SDK)
  cli_agents/
    claude_code.py         vanilla Claude Code CLI (subprocess)
    codex.py               vanilla Codex CLI (subprocess)
  tools/
    sec_edgar/             FastMCP server, hits data.sec.gov
    web_search/             FastMCP server, hits Exa
    final_answer/          native function tool
  harbor/
    adapter.py             DiligenceBenchAdapter: HF rows → task dirs
    template/              static task.toml + Dockerfile + tests/run_test.py
tests/
.claude/                   rules + hooks for Claude Code sessions
datasets/                  generated Harbor tasks (gitignored)
results/                   eval outputs (gitignored)
```

## Cross-cutting rules

- **Two agent kinds.** `agents/<name>/` returns a `SandboxAgent` and runs on
  Modal via the OpenAI Agents SDK. `cli_agents/<name>.py` shells out to a
  vendor CLI (Claude Code, Codex) as a local subprocess and reads the
  agent's `answer.md`. The runner dispatches based on which registry the
  `--agent` name lives in. Both feed the same per-criterion rubric.
- **Modal-only sandbox** (for `SandboxAgent` agents). `ModalSandboxClient`
  from `agents.extensions.sandbox`. No Docker, no UnixLocal.
- **Harbor task directories are the canonical artifact.** Build them with
  `build-tasks`; both this repo's runner and any external Harbor agent
  consume the same directories.
- **Final-answer contract:** the agent writes its memo to
  `/workspace/answer.md`. Both the in-process runner and the Harbor task
  verifier read only that file.
- **`ABLATION_FIELDNAMES` is a public schema.** Don't reorder, rename, or
  change types of columns.
- **Async everywhere** in agent / runner / rubric paths. Sync for CLI,
  file IO, template rendering.
- **Logger, never print** in library code (see `.claude/rules/python.md`).
- **Tests use `pytest.mark.anyio`** with the asyncio backend pinned in
  `tests/conftest.py` (see `.claude/rules/tests.md`).

## Python rules

### Logging

- Always use `logger`, never `print()`
- %-style formatting (defers interpolation, aids log aggregation):
  `logger.info("Processing %s items", count)` — NOT f-strings
- One logger per module: `logger = logging.getLogger(__name__)`
- Levels: `DEBUG` (dev diagnostics), `INFO` (state transitions), `WARN` (degraded), `ERROR` (failures)

### Self-documenting code

- If code needs a comment to explain what it does, rewrite the code
- Comments explain *why*, not *what*
- No "narrating" comments (`# iterate over items` before a for loop)

### Module layout

- Public API at the top of each file
- Private helpers (prefixed with `_`) at the bottom
- Imports: stdlib -> third-party -> local (enforced by ruff `I` rules)

### No band-aid helpers

Every helper function must:
- Solve a real, recurring problem, OR
- Be called from more than one site

If neither applies, inline the logic.

### Config-driven

- Behavior differences go in config, not code branches
- Feature flags via config, not `if environment == "production"` scattered through code

## Test rules

### Philosophy

Only write tests that earn their keep — tests that protect against realistic failure modes.

Do NOT test:
- Trivial getters/setters
- Implementation details (private methods, internal state)
- Scenarios that can't happen in practice
- Framework behavior (argparse parsing, dataclass field access)

### Naming

- Files: `test_<module>.py`
- Functions: `test_<behavior_being_tested>`
- Classes: `Test<Component>` (group related tests)

### Structure

- Fixtures in `conftest.py` (prefer factory functions)
- Use `tmp_path` for file-based tests
- Plain `assert` with descriptive messages: `assert result.status == "active", f"Expected active, got {result.status}"`

### Async

- `pytest.mark.anyio` for async tests (not `pytest.mark.asyncio`)
- Restrict anyio to the asyncio backend via a root `conftest.py` fixture:
  ```python
  @pytest.fixture
  def anyio_backend():
      return "asyncio"
  ```

### Test commands

```bash
uv run pytest                              # all tests
uv run pytest tests/test_foo.py            # single file
uv run pytest tests/test_foo.py::test_bar  # single test
uv run pytest -v                           # verbose
uv run pytest --tb=short                   # short tracebacks
```

## License

Apache-2.0.

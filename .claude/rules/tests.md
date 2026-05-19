# Test rules

## Philosophy

Only write tests that earn their keep — tests that protect against realistic failure modes.

Do NOT test:
- Trivial getters/setters
- Implementation details (private methods, internal state)
- Scenarios that can't happen in practice
- Framework behavior (argparse parsing, dataclass field access)

## Naming

- Files: `test_<module>.py`
- Functions: `test_<behavior_being_tested>`
- Classes: `Test<Component>` (group related tests)

## Structure

- Fixtures in `conftest.py` (prefer factory functions)
- Use `tmp_path` for file-based tests
- Plain `assert` with descriptive messages: `assert result.status == "active", f"Expected active, got {result.status}"`

## Async

- `pytest.mark.anyio` for async tests (not `pytest.mark.asyncio`)
- Restrict anyio to the asyncio backend via a root `conftest.py` fixture:
  ```python
  @pytest.fixture
  def anyio_backend():
      return "asyncio"
  ```

## Commands

```bash
uv run pytest                              # all tests
uv run pytest tests/test_foo.py            # single file
uv run pytest tests/test_foo.py::test_bar  # single test
uv run pytest -v                           # verbose
uv run pytest --tb=short                   # short tracebacks
```

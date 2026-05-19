# Python rules

## Logging

- Always use `logger`, never `print()`
- %-style formatting (defers interpolation, aids log aggregation):
  `logger.info("Processing %s items", count)` — NOT f-strings
- One logger per module: `logger = logging.getLogger(__name__)`
- Levels: `DEBUG` (dev diagnostics), `INFO` (state transitions), `WARN` (degraded), `ERROR` (failures)

## Self-documenting code

- If code needs a comment to explain what it does, rewrite the code
- Comments explain *why*, not *what*
- No "narrating" comments (`# iterate over items` before a for loop)

## Module layout

- Public API at the top of each file
- Private helpers (prefixed with `_`) at the bottom
- Imports: stdlib -> third-party -> local (enforced by ruff `I` rules)

## No band-aid helpers

Every helper function must:
- Solve a real, recurring problem, OR
- Be called from more than one site

If neither applies, inline the logic.

## Config-driven

- Behavior differences go in config, not code branches
- Feature flags via config, not `if environment == "production"` scattered through code

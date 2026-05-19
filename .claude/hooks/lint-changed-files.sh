#!/bin/bash
# Runs ruff on Python files changed since last commit.
# Used as a TaskCompleted hook to catch formatting issues deterministically.

cd "$CLAUDE_PROJECT_DIR" || exit 0

FILES=$(git diff --name-only HEAD 2>/dev/null)
[ -z "$FILES" ] && exit 0

echo "$FILES" | grep -E '\.py$' | while read -r f; do
  [ -f "$f" ] && uv run ruff check --fix "$f" 2>/dev/null && uv run ruff format "$f" 2>/dev/null
done

exit 0

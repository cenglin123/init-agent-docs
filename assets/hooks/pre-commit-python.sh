#!/bin/bash
# Pre-commit hook — Python stack.
# Install: cp this to .githooks/pre-commit && chmod +x .githooks/pre-commit && git config core.hooksPath .githooks
set -e

echo "=== Pre-commit: Python ==="

STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.py$' || true)
if [ -n "$STAGED" ]; then
    if command -v ruff >/dev/null 2>&1; then
        echo "$STAGED" | xargs ruff check
        echo "$STAGED" | xargs ruff format --check
    elif command -v flake8 >/dev/null 2>&1; then
        echo "$STAGED" | xargs flake8
    else
        echo "[pre-commit] WARN — no ruff/flake8 on PATH; skipping Python lint" >&2
    fi
fi

# Hardlink consistency
if [ -f scripts/agent_links.py ]; then
    if ! python scripts/agent_links.py check >/dev/null; then
        python scripts/agent_links.py repair
        git add AGENTS.md CLAUDE.md GEMINI.md 2>/dev/null || true
    fi
fi

echo "=== OK ==="

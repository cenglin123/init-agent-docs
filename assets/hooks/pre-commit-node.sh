#!/bin/bash
# Pre-commit hook — Node / TypeScript stack.
# Install: cp this to .githooks/pre-commit && chmod +x .githooks/pre-commit && git config core.hooksPath .githooks
set -e

echo "=== Pre-commit: Node/TS ==="

STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(js|jsx|ts|tsx|mjs|cjs)$' || true)
if [ -n "$STAGED" ]; then
    if [ -f node_modules/.bin/eslint ] || command -v eslint >/dev/null 2>&1; then
        echo "$STAGED" | xargs npx --no-install eslint
    else
        echo "[pre-commit] WARN — eslint not available; skipping JS/TS lint" >&2
    fi

    if [ -f .prettierrc ] || [ -f .prettierrc.json ] || [ -f .prettierrc.js ] || [ -f prettier.config.js ]; then
        echo "$STAGED" | xargs npx --no-install prettier --check
    fi
fi

if [ -f scripts/agent_links.py ]; then
    if ! python scripts/agent_links.py check >/dev/null; then
        python scripts/agent_links.py repair
        git add AGENTS.md CLAUDE.md GEMINI.md 2>/dev/null || true
    fi
fi

echo "=== OK ==="

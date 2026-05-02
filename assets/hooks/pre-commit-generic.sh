#!/bin/bash
# Pre-commit hook — generic scaffold. Fill in lint/format commands for your stack.
# Install: cp this to .githooks/pre-commit && chmod +x .githooks/pre-commit && git config core.hooksPath .githooks
set -e

echo "=== Pre-commit ==="

# Example: lint only staged files
# STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(py|js|ts)$' || true)
# if [ -n "$STAGED" ]; then
#     echo "$STAGED" | xargs your-linter
# fi

if [ -f scripts/agent_links.py ]; then
    if ! python scripts/agent_links.py check >/dev/null; then
        python scripts/agent_links.py repair
        git add AGENTS.md CLAUDE.md GEMINI.md 2>/dev/null || true
    fi
fi

echo "=== OK ==="

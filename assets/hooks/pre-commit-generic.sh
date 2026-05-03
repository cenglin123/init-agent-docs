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
    if ! python scripts/agent_links.py check; then
        echo ""
        echo "AGENTS.md / CLAUDE.md / GEMINI.md inconsistent."
        echo "Edit only AGENTS.md, then run: python scripts/agent_links.py repair"
        exit 1
    fi
fi

echo "=== OK ==="

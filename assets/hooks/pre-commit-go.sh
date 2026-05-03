#!/bin/bash
# Pre-commit hook — Go stack.
# Install: cp this to .githooks/pre-commit && chmod +x .githooks/pre-commit && git config core.hooksPath .githooks
set -e

echo "=== Pre-commit: Go ==="

STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.go$' || true)
if [ -n "$STAGED" ]; then
    UNFORMATTED=$(echo "$STAGED" | xargs gofmt -l)
    if [ -n "$UNFORMATTED" ]; then
        echo "[pre-commit] FAIL — gofmt changes required in:" >&2
        echo "$UNFORMATTED" >&2
        exit 1
    fi
    go vet ./...
fi

if [ -f scripts/agent_links.py ]; then
    if ! python scripts/agent_links.py check; then
        echo ""
        echo "AGENTS.md / CLAUDE.md / GEMINI.md inconsistent."
        echo "Edit only AGENTS.md, then run: python scripts/agent_links.py repair"
        exit 1
    fi
fi

echo "=== OK ==="

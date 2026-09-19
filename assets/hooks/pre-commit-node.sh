#!/bin/bash
# Pre-commit hook — Node / TypeScript stack.
# Install: cp this to .githooks/pre-commit && chmod +x .githooks/pre-commit && git config core.hooksPath .githooks
set -e

echo "=== Pre-commit: Node/TS ==="

STAGED=()
while IFS= read -r file; do
    [ -n "$file" ] && STAGED+=("$file")
done < <(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(js|jsx|ts|tsx|mjs|cjs)$' || true)

if [ ${#STAGED[@]} -gt 0 ]; then
    if [ -f node_modules/.bin/eslint ] || command -v eslint >/dev/null 2>&1; then
        npx --no-install eslint "${STAGED[@]}"
    else
        echo "[pre-commit] WARN — eslint not available; skipping JS/TS lint" >&2
    fi

    if [ -f .prettierrc ] || [ -f .prettierrc.json ] || [ -f .prettierrc.js ] || [ -f prettier.config.js ]; then
        npx --no-install prettier --check "${STAGED[@]}"
    fi
fi

check_memory_structure() {
    # Only check if memory directory exists (medium+ projects)
    [ -d ".agents/memory" ] || return 0

    if [ ! -f ".agents/memory/MEMORY.md" ]; then
        echo "[pre-commit] FAIL — .agents/memory/ exists but MEMORY.md is missing" >&2
        return 1
    fi

    if [ ! -s ".agents/memory/MEMORY.md" ]; then
        echo "[pre-commit] FAIL — .agents/memory/MEMORY.md is empty" >&2
        return 1
    fi

    if ! grep -q ".agents/memory/MEMORY.md" AGENTS.md 2>/dev/null; then
        echo "[pre-commit] WARN — AGENTS.md missing pointer to .agents/memory/MEMORY.md" >&2
    fi

    return 0
}

check_governance_changes() {
    # Detect staged changes to governance documents (AGENTS.md, hooks, scripts, memory)
    # WARN only — does not block commit. This is a reminder, not a gate.
    STAGED_FILES=$(git diff --cached --name-only)
    GOV_PATTERNS="^AGENTS\.md$|^docs/STRUCTURE\.md$|^scripts/|^.githooks/|^.agents/memory/|^docs/audit-checklist\.md$"

    GOV_FILES=""
    while IFS= read -r path; do
        if echo "$path" | grep -qE "$GOV_PATTERNS"; then
            GOV_FILES="$GOV_FILES  - $path"$'\n'
        fi
    done <<< "$STAGED_FILES"

    if [ -n "$GOV_FILES" ]; then
        # Detect whether converge is available on this device
        CONVERGE_AVAILABLE=0
        if [ -d "$HOME/.claude/skills/converge" ] || [ -d "$HOME/.agents/skills/converge" ]; then
            CONVERGE_AVAILABLE=1
        elif [ -d ".converge" ]; then
            CONVERGE_AVAILABLE=1
        elif command -v converge >/dev/null 2>&1; then
            CONVERGE_AVAILABLE=1
        fi

        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "📋 检测到治理文档变更"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "以下治理文档（AGENTS.md / hooks / scripts / 记忆索引等）已变更："
        echo "$GOV_FILES"

        if [ "$CONVERGE_AVAILABLE" -eq 1 ]; then
            echo ""
            echo "建议走 converge 流程进行独立审查："
            echo "  准则段改动（行为规则/禁止事项）→ ultraverge（≥3 Reviewer）"
            echo "  其他治理文档修改（导航/说明）→ 标准 converge"
        else
            echo ""
            echo "当前环境未检测到 converge 工具。降级方案："
            echo "  在提交前，至少启动一个独立上下文的子 agent，"
            echo "  让它全面审计本次修改——检查规则一致性、边界条件、遗漏项。"
            echo "  不要依赖执行者自检。"
        fi
        echo ""
        echo "本次提交不会因此被拒绝。"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
    fi
    return 0
}

if ! check_memory_structure; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ".agents/memory/ 目录结构不完整。"
    echo ""
    echo "这可能是因为："
    echo "  1. .agents/memory/ 目录存在但 MEMORY.md 缺失或为空"
    echo "  2. 记忆文件被误删"
    echo ""
    echo "修复：重新创建 .agents/memory/MEMORY.md 或从模板恢复。"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

check_governance_changes

echo "=== OK ==="

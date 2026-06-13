#!/bin/bash
# Pre-commit hook — Go stack.
# Install: cp this to .githooks/pre-commit && chmod +x .githooks/pre-commit && git config core.hooksPath .githooks
set -e

echo "=== Pre-commit: Go ==="

STAGED=()
while IFS= read -r file; do
    [ -n "$file" ] && STAGED+=("$file")
done < <(git diff --cached --name-only --diff-filter=ACM | grep -E '\.go$' || true)

if [ ${#STAGED[@]} -gt 0 ]; then
    UNFORMATTED=$(gofmt -l "${STAGED[@]}")
    if [ -n "$UNFORMATTED" ]; then
        echo "[pre-commit] FAIL — gofmt changes required in:" >&2
        echo "$UNFORMATTED" >&2
        exit 1
    fi
    go vet ./...
fi

# AGENTS.md / CLAUDE.md / GEMINI.md 一致性检查
# 优先使用 agent_links.py；不可用时 fallback 到内联 MD5（兼容 md5sum / md5）
AGENTS_FILE="AGENTS.md"
CLAUDE_FILE="CLAUDE.md"
GEMINI_FILE="GEMINI.md"

check_agents_sync() {
    PYTHON_CMD=""
    if command -v python >/dev/null 2>&1; then
        PYTHON_CMD="python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_CMD="python3"
    fi
    if [ -f scripts/agent_links.py ] && [ -n "$PYTHON_CMD" ]; then
        $PYTHON_CMD scripts/agent_links.py check
        return $?
    fi

    if [ ! -f "$AGENTS_FILE" ] || [ ! -f "$CLAUDE_FILE" ] || [ ! -f "$GEMINI_FILE" ]; then
        echo "[pre-commit] FAIL — AGENTS.md / CLAUDE.md / GEMINI.md 存在缺失文件" >&2
        return 1
    fi

    if command -v md5sum >/dev/null 2>&1; then
        AGENTS_MD5=$(md5sum "$AGENTS_FILE" | awk '{print $1}')
        CLAUDE_MD5=$(md5sum "$CLAUDE_FILE" | awk '{print $1}')
        GEMINI_MD5=$(md5sum "$GEMINI_FILE" | awk '{print $1}')
    elif command -v md5 >/dev/null 2>&1; then
        AGENTS_MD5=$(md5 -q "$AGENTS_FILE")
        CLAUDE_MD5=$(md5 -q "$CLAUDE_FILE")
        GEMINI_MD5=$(md5 -q "$GEMINI_FILE")
    else
        echo "[pre-commit] WARN — 无法检查 AGENTS.md 同步（未找到 python/md5sum/md5）" >&2
        return 0
    fi

    if [ "$AGENTS_MD5" != "$CLAUDE_MD5" ] || [ "$AGENTS_MD5" != "$GEMINI_MD5" ]; then
        return 1
    fi
    return 0
}

check_memory_structure() {
    # Only check if memory directory exists (medium+ projects)
    [ -d ".agent/memory" ] || return 0

    if [ ! -f ".agent/memory/MEMORY.md" ]; then
        echo "[pre-commit] FAIL — .agent/memory/ exists but MEMORY.md is missing" >&2
        return 1
    fi

    if [ ! -s ".agent/memory/MEMORY.md" ]; then
        echo "[pre-commit] FAIL — .agent/memory/MEMORY.md is empty" >&2
        return 1
    fi

    if ! grep -q ".agent/memory/MEMORY.md" AGENTS.md 2>/dev/null; then
        echo "[pre-commit] WARN — AGENTS.md missing pointer to .agent/memory/MEMORY.md" >&2
    fi

    return 0
}

check_governance_changes() {
    # Detect staged changes to governance documents (AGENTS.md, hooks, scripts, memory)
    # WARN only — does not block commit. This is a reminder, not a gate.
    STAGED_FILES=$(git diff --cached --name-only)
    GOV_PATTERNS="^AGENTS\.md$|^CLAUDE\.md$|^GEMINI\.md$|^STRUCTURE\.md$|^scripts/|^.githooks/|^.agent/memory/|^docs/audit-checklist\.md$"

    GOV_FILES=""
    while IFS= read -r path; do
        if echo "$path" | grep -qE "$GOV_PATTERNS"; then
            GOV_FILES="$GOV_FILES  - $path"$'\n'
        fi
    done <<< "$STAGED_FILES"

    if [ -n "$GOV_FILES" ]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "📋 检测到治理文档变更"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "以下治理文档（AGENTS.md / hooks / scripts / 记忆索引等）已变更："
        echo "$GOV_FILES"
        echo "治理文档定义项目的行为规则和强制机制，修改后请确认已进行独立审查。"
        echo "本次提交不会因此被拒绝。"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
    fi
    return 0
}

if ! check_agents_sync; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "AGENTS.md / CLAUDE.md / GEMINI.md 三个文件的内容不一致。"
    echo ""
    echo "这可能是因为："
    echo "  1. 你修改了 AGENTS.md 但忘记运行同步脚本"
    echo "  2. 你直接修改了 CLAUDE.md 或 GEMINI.md（这是错误的）"
    echo ""
    echo "正确的流程："
    echo "  1. 编辑 AGENTS.md（不要编辑 CLAUDE.md 或 GEMINI.md）"
    echo "  2. 运行：python3 scripts/agent_links.py repair（或 python）"
    echo "  3. 重新 stage 并提交"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

if ! check_memory_structure; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ".agent/memory/ 目录结构不完整。"
    echo ""
    echo "这可能是因为："
    echo "  1. .agent/memory/ 目录存在但 MEMORY.md 缺失或为空"
    echo "  2. 记忆文件被误删"
    echo ""
    echo "修复：重新创建 .agent/memory/MEMORY.md 或从模板恢复。"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

check_governance_changes

echo "=== OK ==="

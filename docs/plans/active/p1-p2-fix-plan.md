# P1/P2 修复计划

> 状态：已审计，待执行  
> 审计人：subagent（general-purpose）  
> 计划时间：2026-05-06

---

## 背景

本计划针对 `init-agent-docs` skill 在 subagent 审计和 eval 测试中发现的 P1（高优先级健壮性问题）和 P2（维护性/测试覆盖问题）进行修复。所有 P0 问题已修复并验证通过（16 tests passed）。

---

## 问题清单与修复方案

### P1-1：python3 fallback in pre-commit hooks

**问题描述**  
4 个 pre-commit hook 模板使用 `command -v python` 探测 Python 解释器。在大量 Linux/macOS 环境中，系统仅提供 `python3` 而无 `python` 符号链接，导致 hook 跳过 `agent_links.py` 检查且无任何警告。

**影响范围**  
- `assets/hooks/pre-commit-generic.sh`  
- `assets/hooks/pre-commit-python.sh`  
- `assets/hooks/pre-commit-node.sh`  
- `assets/hooks/pre-commit-go.sh`

**修复方案**  
在每个 hook 的 `check_agents_sync()` 函数中，将探测逻辑改为 `python` → `python3` fallback：

```bash
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
```

**同步修改**  
hook 底部诊断信息中的命令提示，从：
```
  2. 运行：python scripts/agent_links.py repair
```
改为：
```
  2. 运行：python3 scripts/agent_links.py repair（或 python）
```

**审计意见**  
- 可进一步简化为 `for cmd in python python3; do ... break; done`，但当前写法可读性更好，予以保留。
- 错误提示同步更新已纳入计划。

---

### P1-2：xargs 空格不安全

**问题描述**  
hook 中使用 `echo "$STAGED" | xargs <linter>` 传递文件名。当 staged 文件路径包含空格时，`xargs` 将其拆分为多个参数，导致 linter 收到无效路径。

**影响范围**  
同上 4 个 hook。

**修复方案**  
统一改用 bash 数组 + 进程替代（process substitution）。经审计确认，`< <(...)` 在 macOS 默认 bash 3.2 和 Linux bash 4+ 均可工作。

以 `pre-commit-python.sh` 为例（其余 3 个同构替换）：

```bash
STAGED=()
while IFS= read -r file; do
    [ -n "$file" ] && STAGED+=("$file")
done < <(git diff --cached --name-only --diff-filter=ACM | grep -E '\.py$' || true)

if [ ${#STAGED[@]} -gt 0 ]; then
    if command -v ruff >/dev/null 2>&1; then
        ruff check "${STAGED[@]}"
        ruff format --check "${STAGED[@]}"
    elif command -v flake8 >/dev/null 2>&1; then
        flake8 "${STAGED[@]}"
    else
        echo "[pre-commit] WARN — no ruff/flake8 on PATH; skipping Python lint" >&2
    fi
fi
```

各 hook 的差异仅在于：
- **go**：`grep -E '\.go$'` → `gofmt -l "${STAGED[@]}"` + `go vet ./...`
- **node**：`grep -E '\.(js|jsx|ts|tsx|mjs|cjs)$'` → `eslint "${STAGED[@]}"` + `prettier --check "${STAGED[@]}"`
- **generic**：同步更新注释示例为新模板

**审计意见**  
- 空数组时 `[ ${#STAGED[@]} -gt 0 ]` 保护有效，避免 `gofmt -l` 无参数时从 stdin 读取。
- `pre-commit-generic.sh` 的注释示例必须同步更新，不能留旧模板误导用户。
- `pre-commit-node.sh` 的 `prettier --check` 部分也要覆盖，不能漏。

---

### P1-3：repair 后二次校验

**问题描述**  
`agent_links.py` 的 `command_repair()` 在修复完成后仅通过 `detect_mode()` 做全局校验。在 hardlink 模式下，`detect_mode()` 检查 inode 一致性，但未逐目标验证；若某个 target 写入/链接失败但其他 target 正常，全局校验可能无法定位具体故障文件。

**影响范围**  
- `assets/scripts/agent_links.py`

**修复方案（审计优化版）**  
不添加无差别的 MD5 重算（审计指出 copy 模式下 `detect_mode()` 已调用 `is_content_equal()` 做全局 MD5 校验）。改为在 `command_repair()` 末尾、return 前增加轻量逐目标校验：

```python
# Ensure all targets exist and (for hardlink mode) share the source inode
source_key = link_key(source)
for target in targets:
    if not target.exists():
        print("\n".join(describe()), file=sys.stderr)
        raise SystemExit(f"repair failed: {target.name} missing")
    if mode == "hardlink" and link_key(target) != source_key:
        print("\n".join(describe()), file=sys.stderr)
        raise SystemExit(f"repair failed: {target.name} is not hardlinked to source")
```

**设计理由**  
- copy 模式：不做额外 IO，`detect_mode()` 已覆盖。
- hardlink 模式：验证 `link_key()`（inode 比较），比重新计算 MD5 更高效。
- 同时覆盖"文件缺失"这一极端故障场景。

**审计意见**  
- 原方案（全 MD5 比对）在 copy 模式下冗余，已采纳优化建议。
- `repair_target()` 中 copy 模式已有提前返回的 MD5 比对，正常情况下不会出错；post-verification 主要防 partial write / crash。

---

### P2-1：测试覆盖默认 copy 模式

**问题描述**  
现有 `test_copy_mode_repair_then_check` 显式传入 `--mode=copy`，缺少验证"裸 `repair`（无参数）默认走 copy"的测试。

**影响范围**  
- `tests/test_agent_links.py`

**修复方案**  
新增测试：

```python
def test_repair_defaults_to_copy(self) -> None:
    result = self.run_script("repair")
    self.assertEqual(result.returncode, 0, result.stderr)
    # Verify not hardlinked (copy mode uses separate inodes)
    agents_inode = (self.tmp / "AGENTS.md").stat().st_ino
    claude_inode = (self.tmp / "CLAUDE.md").stat().st_ino
    self.assertNotEqual(agents_inode, claude_inode, "default repair should use copy")
    # Verify auto check passes
    result = self.run_script("check")
    self.assertEqual(result.returncode, 0, result.stderr)
```

**审计意见**  
- 在支持和不支持 hardlink 的文件系统上均会通过（auto 逻辑：`mode = "hardlink" if current == "hardlink" else "copy"`，初始 broken 状态必选 copy）。
- 测试设计合理，非 flaky。

---

### P2-2：changelog.py `--match` limit 逻辑

**问题描述**  
`command_show()` 的 `--match` 分支中，`if printed >= args.limit:` 在 `--limit=0` 时立即触发（`printed >= 0` 恒真），导致无任何输出。且 `limit=0` 语义与 `command_titles()` 不一致（后者表示"无限制"）。

**影响范围**  
- `assets/scripts/changelog.py`

**修复方案**  
在 `--match` 分支的两处 limit 检查（第 148 行、第 154 行附近），统一改为：

```python
if args.limit and printed >= args.limit:
```

这样 `limit=0` 表示"无限制"，与 `command_titles()` 保持一致，同时保留默认 `limit=3` 的行为不变。

**审计意见**  
- fix 正确且充分。`command_show()` 的 `--date` 路径不使用 limit，不受影响。

---

### P2-3：copy 模式内容分叉测试

**问题描述**  
缺少显式测试验证 copy 模式下三个文件内容不一致时 `check --mode=copy` 能正确拒绝。

**影响范围**  
- `tests/test_agent_links.py`

**修复方案**  
新增测试（审计建议加强 stderr 断言）：

```python
def test_check_rejects_diverged_content_in_copy_mode(self) -> None:
    self.run_script("repair", "--mode=copy")
    # Modify one copy to diverge
    (self.tmp / "CLAUDE.md").write_text("diverged\n", encoding="utf-8")
    result = self.run_script("check", "--mode=copy")
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("expected mode=copy", result.stderr)
```

**审计意见**  
- 基本合理，stderr 断言已采纳。
- 与现有 `test_check_rejects_diverged_content`（默认 auto 模式）不冗余，因为显式指定 `--mode=copy` 可确保测试意图清晰。

---

## 涉及文件汇总

| 序号 | 文件路径 | 修改项 |
|------|----------|--------|
| 1 | `assets/hooks/pre-commit-generic.sh` | P1-1, P1-2 |
| 2 | `assets/hooks/pre-commit-python.sh` | P1-1, P1-2 |
| 3 | `assets/hooks/pre-commit-node.sh` | P1-1, P1-2 |
| 4 | `assets/hooks/pre-commit-go.sh` | P1-1, P1-2 |
| 5 | `assets/scripts/agent_links.py` | P1-3 |
| 6 | `assets/scripts/changelog.py` | P2-2 |
| 7 | `tests/test_agent_links.py` | P2-1, P2-3 |

---

## 验收标准

1. 执行 `python -m pytest tests/ -v`，所有测试通过（预期 18 项：现有 16 + 新增 2）。
2. 4 个 hook 脚本在 `shellcheck`（如有）中无致命错误；至少通过 bash 语法检查。
3. `agent_links.py repair` 在 hardlink 模式下若 target 未正确链接，能输出明确的 `repair failed: X is not hardlinked to source` 错误。
4. `changelog.py show --match X --limit=0` 能正确输出所有匹配结果而不被截断。

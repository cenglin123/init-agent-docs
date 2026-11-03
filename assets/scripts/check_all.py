#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""高频完工检查器——每次任务完成后跑一次，**无输出 = 全部通过**。

设计原则：
1. --quiet 模式下，无输出 = 全部通过（不消耗 agent 注意力）
2. 每条 FAIL 自带修复指引（agent 不需要记忆"失败后做什么"）
3. CHECKS 列表是检查项的单一权威源——AGENTS.md 只引用本脚本，不枚举覆盖范围
4. 只检查"本次任务是否遗漏了必做项"（~4项），不属于深度审计；深度审计交给 audit.py

与 audit.py 的分工：
    check_all.py  → 高频完工检查（每次任务后跑，静默，~4 项）
    audit.py      → 深度定期审计（每 ~20 次任务或每月跑，详实输出，~15 项）

用法：
    python scripts/check_all.py            # 全量输出
    python scripts/check_all.py --quiet    # 静默模式（完工清单默认用这个）
    python scripts/check_all.py --small    # 小型项目模式（跳过记忆检查）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent.parent if SCRIPTS_DIR.parent.name == '.meta' else SCRIPTS_DIR.parent
SCRIPTS_REL = '.meta/scripts' if SCRIPTS_DIR.parent.name == '.meta' else 'scripts'

def _has_file(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _read_nonblank_utf8(rel: str) -> tuple[bool, str]:
    try:
        text = (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False, f"{rel} 不存在或无法按 UTF-8 解码"
    if not text.strip():
        return False, f"{rel} 为空白文件"
    return True, text


def _run(name: str, cmd: list[str]) -> tuple[bool, str]:
    """Run a subprocess check. Returns (ok, stdout+stderr)."""
    proc = subprocess.run(
        [sys.executable, *cmd],
        cwd=str(ROOT),
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


# 检查项：每个条目为 (名称, 判定函数, 修复指引)
# 判定函数返回 (ok: bool, detail: str)
CHECKS: list[tuple[str, callable, str]] = []


def _check_changelog():
    if not _has_file("docs/CHANGELOG.md"):
        return False, "docs/CHANGELOG.md 不存在"
    ok, detail = _run("CHANGELOG", [f"{SCRIPTS_REL}/changelog.py", "titles", "--limit", "1"])
    if not ok or not detail.strip():
        return False, detail or f"CHANGELOG 无条目——本次任务如有值得记录的内容，用 {SCRIPTS_REL}/changelog.py add 追加"
    return True, detail

CHECKS.append(("CHANGELOG", _check_changelog,
              f"python {SCRIPTS_REL}/changelog.py add --title \"...\" --body \"...\""))


def _check_line_budget():
    ok, text = _read_nonblank_utf8("AGENTS.md")
    if not ok:
        return False, text
    lines = len(text.splitlines())
    ok = lines <= 250
    detail = f"AGENTS.md: {lines} 行"
    return ok, detail

CHECKS.append(("行数", _check_line_budget,
              "恢复非空 UTF-8 AGENTS.md；超过 250 行时将内容下沉到 docs/ 或删除"))


def _has_explicit_medium_large_profile() -> tuple[bool, str]:
    """Reuse audit's birth-record parser to detect a configured project size."""
    candidates = (
        "docs/initialization.md",
        "docs/plans/active/initialization.md",
        "docs/plans/completed/initialization.md",
    )
    if not any((ROOT / rel).is_file() for rel in candidates):
        return False, ""
    try:
        from . import audit as audit_module
    except ImportError:
        try:
            import audit as audit_module
        except ImportError as exc:
            return False, f"无法加载 audit.py 检查初始化档案: {exc}"

    try:
        prior_root, prior_scripts_dir = audit_module.ROOT, audit_module.SCRIPTS_DIR
        audit_module.ROOT = ROOT
        audit_module.SCRIPTS_DIR = SCRIPTS_DIR
        rows = audit_module._check_birth_record()
        unreadable = next((
            row for row in rows
            if row.get("status") == "invalid"
            and row.get("error_code") == "read_error"
        ), None)
        if unreadable:
            return False, f"无法读取初始化档案 {unreadable['path']}: {unreadable['detail']}"
        found = any(
            row.get("size") in ("medium", "large")
            or any(size in ("medium", "large") for size in row.get("sizes", []))
            for row in rows
        )
        return found, ""
    except (OSError, UnicodeDecodeError) as exc:
        return False, f"无法读取初始化档案: {exc}"
    finally:
        if "prior_root" in locals():
            audit_module.ROOT = prior_root
            audit_module.SCRIPTS_DIR = prior_scripts_dir


def _check_memory_touch():
    """检查已配置的记忆索引是否存在且可读。"""
    mem_dir = ROOT / (".meta" if SCRIPTS_DIR.parent.name == ".meta" or (ROOT / ".meta" / "memory").is_dir() else ".agents") / "memory"
    if not mem_dir.is_dir():
        if SCRIPTS_DIR.parent.name == ".meta":
            return False, ".meta/memory/ 不存在——知识库记忆系统缺失"
        profile_exists, profile_error = _has_explicit_medium_large_profile()
        if profile_error:
            return False, profile_error
        if profile_exists:
            return False, f"{mem_dir.relative_to(ROOT).as_posix()}/ 不存在——显式中大型项目需要记忆系统"
        return True, ""  # 小型项目，无记忆系统
    mem_file = mem_dir / "MEMORY.md"
    if not mem_file.is_file():
        return False, f"{mem_dir.relative_to(ROOT).as_posix()}/MEMORY.md 不存在——中型+项目需要记忆系统"
    try:
        content = mem_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False, f"{mem_file.relative_to(ROOT).as_posix()} 无法按 UTF-8 解码"
    if not content.strip():
        return False, f"{mem_file.relative_to(ROOT).as_posix()} 为空白文件"
    return True, f"{mem_file.relative_to(ROOT).as_posix()} 存在且可读"

CHECKS.append(("记忆", _check_memory_touch,
              "恢复当前记忆目录的非空 UTF-8 MEMORY.md；内容有效性由 Agent 审查，不为年龄消警修改"))


def _check_dead_links():
    if not _has_file(f"{SCRIPTS_REL}/audit.py"):
        return False, f"{SCRIPTS_REL}/audit.py 不存在——无法执行死链审计"
    ok, detail = _run("死链", [f"{SCRIPTS_REL}/audit.py", "dead-links"])
    return ok, detail

CHECKS.append(("死链", _check_dead_links,
              "恢复 audit.py 并检查标记 dead 的链接目标是否确实不存在"))


def main() -> int:
    ap = argparse.ArgumentParser(description="高频完工检查器——无输出即通过")
    ap.add_argument("--quiet", action="store_true",
                    help="静默模式：只在有失败时输出")
    ap.add_argument("--small", action="store_true",
                    help="小型项目模式（跳过记忆检查）")
    args = ap.parse_args()

    # 如果是小型项目，跳过记忆检查
    checks_to_run = CHECKS
    if args.small:
        checks_to_run = [c for c in CHECKS if c[0] != "记忆"]

    failed: list[tuple[str, str]] = []
    for name, fn, guide in checks_to_run:
        ok, detail = fn()
        if not ok:
            failed.append((name, guide))
        if not args.quiet or not ok:
            status = "OK" if ok else "FAIL"
            if not args.quiet:
                print(f"\n[{status}] {name}")
                if detail:
                    print("    " + "\n    ".join(detail.splitlines()))
            elif not ok:
                print(f"\n[{status}] {name}")
                if detail:
                    print("    " + "\n    ".join(detail.splitlines()))

    if not failed:
        if not args.quiet:
            print(f"\n[PASS] 全部 {len(checks_to_run)} 项通过")
        return 0

    print(f"\n{'=' * 50}")
    print(f"共 {len(failed)} 项未通过，修复后重跑：")
    for name, guide in failed:
        print(f"  [{name}] → {guide}")
    print(f"{'=' * 50}")
    return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

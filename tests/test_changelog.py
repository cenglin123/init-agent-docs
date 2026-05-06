"""Subprocess-based smoke tests for assets/scripts/changelog.py."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "assets" / "scripts" / "changelog.py"

INITIAL_CHANGELOG = """# CHANGELOG

## 2026-04-17

### 初始化文档体系

- 创建 agent-first 文档结构：AGENTS.md（含硬链接）+ STRUCTURE.md + docs/ 层级
- 配置 scripts/changelog.py 与 scripts/agent_links.py，脚本化维护日志和硬链接
"""


class ChangelogTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="changelog_"))
        self.changelog = self.tmp / "CHANGELOG.md"
        self.changelog.write_text(INITIAL_CHANGELOG, encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--changelog", str(self.changelog), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

    def test_titles_lists_dates(self) -> None:
        result = self.run_script("titles")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2026-04-17", result.stdout)
        self.assertIn("初始化文档体系", result.stdout)

    def test_show_by_date(self) -> None:
        result = self.run_script("show", "--date", "2026-04-17")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("初始化文档体系", result.stdout)

    def test_show_by_match(self) -> None:
        result = self.run_script("show", "--match", "硬链接")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("初始化文档体系", result.stdout)

    def test_add_to_existing_date(self) -> None:
        # Use os.linesep-agnostic separator: pass a single line. Multi-line bodies
        # in argv are unreliable on Windows (CommandLineToArgvW handles literal
        # newlines inconsistently). The script's splitlines() behavior is unit-
        # tested separately at the import level.
        result = self.run_script(
            "add",
            "--date", "2026-04-17",
            "--title", "增补条目",
            "--body", "新增内容",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        text = self.changelog.read_text(encoding="utf-8")
        self.assertIn("### 增补条目", text)
        self.assertIn("- 新增内容", text)
        # Original section must still be present
        self.assertIn("### 初始化文档体系", text)

    def test_format_add_block_splits_multiline_body(self) -> None:
        # Direct in-process test for the multi-line body path; avoids passing
        # a literal newline through subprocess argv on Windows.
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import importlib

            mod = importlib.import_module("changelog")
            ns = type("Args", (), {})()
            ns.title = "增补"
            ns.body = "A\nB"
            ns.migration = ""
            block = mod.format_add_block(ns, "zh")
            self.assertIn("- A", block)
            self.assertIn("- B", block)
        finally:
            sys.path.remove(str(SCRIPT.parent))

    def test_add_creates_new_date_block_at_top(self) -> None:
        future = "2099-01-01"
        result = self.run_script(
            "add",
            "--date", future,
            "--title", "未来变更",
            "--body", "内容",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        text = self.changelog.read_text(encoding="utf-8")
        future_idx = text.index(f"## {future}")
        existing_idx = text.index("## 2026-04-17")
        self.assertLess(future_idx, existing_idx, "newer date must come first")

    def test_add_today_when_date_omitted(self) -> None:
        result = self.run_script("add", "--title", "今日条目", "--body", "x")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.changelog.read_text(encoding="utf-8")
        today = date.today().isoformat()
        self.assertIn(f"## {today}", text)

    def test_show_requires_date_or_match(self) -> None:
        result = self.run_script("show")
        self.assertNotEqual(result.returncode, 0)

    def test_add_to_empty_shell(self) -> None:
        # Bootstrap case: a freshly scaffolded CHANGELOG has only the H1 and a
        # comment block. The first add must succeed (placing the new date block
        # right after the H1) instead of failing with "no date heading".
        empty_shell = "# CHANGELOG\n\n<!-- description placeholder -->\n"
        self.changelog.write_text(empty_shell, encoding="utf-8")
        result = self.run_script(
            "add",
            "--date", "2026-04-17",
            "--title", "初始化文档体系",
            "--body", "建立 agent-first 文档结构",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.changelog.read_text(encoding="utf-8")
        self.assertIn("## 2026-04-17", text)
        self.assertIn("### 初始化文档体系", text)
        # The new block must come AFTER the H1, not before it
        h1_idx = text.index("# CHANGELOG")
        date_idx = text.index("## 2026-04-17")
        self.assertLess(h1_idx, date_idx)

    def test_add_to_completely_empty_file(self) -> None:
        # Defensive case: even a totally empty file should not crash.
        self.changelog.write_text("", encoding="utf-8")
        result = self.run_script(
            "add",
            "--date", "2026-04-17",
            "--title", "初始化",
            "--body", "x",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.changelog.read_text(encoding="utf-8")
        self.assertIn("## 2026-04-17", text)


if __name__ == "__main__":
    unittest.main()

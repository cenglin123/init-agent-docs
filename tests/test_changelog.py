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

- 创建 agent-first 文档结构：AGENTS.md（唯一入口）+ docs/STRUCTURE.md + docs/ 层级
- 配置 scripts/changelog.py，脚本化维护日志
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
        result = self.run_script("show", "--match", "唯一入口")
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

    def test_titles_stream_preserves_splitlines_unicode_separators(self) -> None:
        import importlib.util

        self.changelog.write_text(
            "# CHANGELOG\n\n## 2026-04-17\n### 第一块\u2028### 第二块\n正文\n",
            encoding="utf-8",
        )
        spec = importlib.util.spec_from_file_location("changelog_split_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        streamed = mod.iter_title_blocks_from_file(self.changelog)
        lines = mod.read_lines(self.changelog)
        legacy = []
        for start, end, day, title in mod.iter_date_blocks(lines):
            sections = [
                section_title
                for section_start, _section_end, section_title
                in mod.iter_sections(lines[start:end])
                if section_start != 0
            ]
            legacy.append((day, title, sections))

        self.assertEqual(streamed, legacy)
        self.assertEqual(streamed[0][2], ["第一块", "第二块"])

    def test_titles_stream_does_not_cache_large_block_body(self) -> None:
        import importlib.util

        self.changelog.write_text(
            "# CHANGELOG\n\n## 2026-01-01\n### 第一块\n"
            + ("正文行\n" * 5000)
            + "## 2026-01-02\n### 第二块\n",
            encoding="utf-8",
        )
        spec = importlib.util.spec_from_file_location("changelog_large_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        first = mod.iter_title_blocks_from_file(self.changelog, limit=1)
        second = mod.iter_title_blocks_from_file(self.changelog, limit=2)

        self.assertEqual(first, [("2026-01-01", "", ["第一块"])])
        self.assertEqual(
            second,
            [("2026-01-01", "", ["第一块"]), ("2026-01-02", "", ["第二块"])],
        )
        self.assertNotIn("正文行", repr(first))

    def test_titles_limit_really_stops_before_invalid_tail(self) -> None:
        import importlib.util

        prefix = (
            "# CHANGELOG\n\n## 2026-01-01\n### 第一块\n\n"
            "## 2026-01-02\n### 第二块\n\n"
        )
        self.changelog.write_bytes(
            prefix.encode("utf-8")
            + (("正文\n" * 50000).encode("utf-8"))
            + b"\xff\xff"
        )
        spec = importlib.util.spec_from_file_location("changelog_tail_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        blocks = mod.iter_title_blocks_from_file(self.changelog, limit=1)

        self.assertEqual(blocks, [("2026-01-01", "", ["第一块"])])
        # The unread tail is deliberately outside the bounded contract.
        with self.assertRaises(UnicodeDecodeError):
            mod.iter_title_blocks_from_file(self.changelog, limit=0)

    def test_titles_limit_stops_before_invalid_next_physical_line(self) -> None:
        import importlib.util

        self.changelog.write_bytes(
            b"# CHANGELOG\n\n## 2026-01-01\n### First\n\n"
            b"## 2026-01-02\n\xff\xfe\n"
        )
        spec = importlib.util.spec_from_file_location("changelog_binary_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        blocks = mod.iter_title_blocks_from_file(self.changelog, limit=1)

        self.assertEqual(blocks, [("2026-01-01", "", ["First"])])
        with self.assertRaises(UnicodeDecodeError):
            mod.iter_title_blocks_from_file(self.changelog, limit=0)

    def test_titles_limit_stops_before_invalid_after_bare_cr(self) -> None:
        import importlib.util

        self.changelog.write_bytes(
            b"# CHANGELOG\r\r## 2026-01-01\r### First\r\r"
            b"## 2026-01-02\r\xff"
            + (b"tail\r" * 100000)
        )
        spec = importlib.util.spec_from_file_location("changelog_cr_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        blocks = mod.iter_title_blocks_from_file(self.changelog, limit=1)

        self.assertEqual(blocks, [("2026-01-01", "", ["First"])])
        with self.assertRaises(UnicodeDecodeError):
            mod.iter_title_blocks_from_file(self.changelog, limit=0)

    def test_titles_limit_stops_before_invalid_after_u2028(self) -> None:
        import importlib.util

        self.changelog.write_bytes(
            b"# CHANGELOG\n\n## 2026-01-01\n### First\n\n## 2026-01-02"
            b"\xe2\x80\xa8\xff" + (b"tail\n" * 100000)
        )
        spec = importlib.util.spec_from_file_location("changelog_u2028_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        blocks = mod.iter_title_blocks_from_file(self.changelog, limit=1)

        self.assertEqual(blocks, [("2026-01-01", "", ["First"])])
        with self.assertRaises(UnicodeDecodeError):
            mod.iter_title_blocks_from_file(self.changelog, limit=0)

    def test_titles_streams_many_unicode_separators_in_one_physical_line(self) -> None:
        import importlib.util

        sections = "\u2028".join(f"### S{index}" for index in range(2000))
        self.changelog.write_text(
            "# CHANGELOG\n\n## 2026-01-01\n" + sections + "\n",
            encoding="utf-8",
        )
        spec = importlib.util.spec_from_file_location("changelog_sep_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        blocks = mod.iter_title_blocks_from_file(self.changelog)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][2], [f"S{index}" for index in range(2000)])

    def test_titles_single_long_line_scans_linearly(self) -> None:
        import importlib.util

        payload = (
            b"# CHANGELOG\n\n## 2026-01-01\n### Long\n"
            + (b"x" * (1024 * 1024))
            + b"\n## 2026-01-02\n### Next\n"
        )
        self.changelog.write_bytes(payload)
        spec = importlib.util.spec_from_file_location("changelog_linear_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        real_re = mod._UTF8_LINE_BREAK_BYTES_RE
        scanned_bytes = 0

        class CountingPattern:
            def search(self, buf, pos=0):
                nonlocal scanned_bytes
                scanned_bytes += max(0, len(buf) - pos)
                return real_re.search(buf, pos)

        mod._UTF8_LINE_BREAK_BYTES_RE = CountingPattern()
        blocks = mod.iter_title_blocks_from_file(self.changelog, limit=1)

        self.assertEqual(blocks, [("2026-01-01", "", ["Long"])])
        self.assertLess(scanned_bytes, len(payload) * 2)

    def test_titles_limit_output_matches_first_block_only(self) -> None:
        self.changelog.write_text(
            INITIAL_CHANGELOG
            + """
## 2026-04-16

### 后续条目
""",
            encoding="utf-8",
        )
        result = self.run_script("titles", "--limit", "1")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2026-04-17", result.stdout)
        self.assertIn("初始化文档体系", result.stdout)
        self.assertNotIn("2026-04-16", result.stdout)
        self.assertNotIn("后续条目", result.stdout)


if __name__ == "__main__":
    unittest.main()

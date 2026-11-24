"""Regression tests for completion checks in project and knowledge-base layouts."""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from assets.scripts import check_all


class CheckAllTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.agents = self.root / "AGENTS.md"
        self.agents.write_text("# Project\n", encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def check_with_layout(self, scripts):
        with patch.object(check_all, "ROOT", self.root), patch.object(check_all, "SCRIPTS_DIR", scripts):
            return check_all._check_line_budget(), check_all._check_memory_touch()

    def test_valid_agents_and_old_memory_pass(self):
        memory = self.root / ".agents" / "memory"
        memory.mkdir(parents=True)
        index = memory / "MEMORY.md"
        index.write_text("# Existing memory\n", encoding="utf-8")
        old = 946684800
        import os
        os.utime(index, (old, old))

        agents_result, memory_result = self.check_with_layout(self.scripts)

        self.assertTrue(agents_result[0], agents_result[1])
        self.assertTrue(memory_result[0], memory_result[1])
        self.assertNotIn("天前", memory_result[1])

    def test_agents_missing_blank_and_invalid_utf8_fail(self):
        cases = (
            ("missing", None),
            ("blank", b" \n\t"),
            ("invalid", b"\xff"),
        )
        for label, content in cases:
            with self.subTest(label=label):
                self.agents.unlink(missing_ok=True)
                if content is not None:
                    self.agents.write_bytes(content)
                result, _ = self.check_with_layout(self.scripts)
                self.assertFalse(result[0])

    def test_agents_over_250_lines_fail(self):
        self.agents.write_text("line\n" * 251, encoding="utf-8")
        result, _ = self.check_with_layout(self.scripts)
        self.assertFalse(result[0])
        self.assertIn("251", result[1])

    def test_memory_missing_blank_and_invalid_utf8_fail_when_directory_exists(self):
        memory = self.root / ".agents" / "memory"
        memory.mkdir(parents=True)
        index = memory / "MEMORY.md"
        for label, content in (("missing", None), ("blank", b" \n"), ("invalid", b"\xff")):
            with self.subTest(label=label):
                index.unlink(missing_ok=True)
                if content is not None:
                    index.write_bytes(content)
                _, result = self.check_with_layout(self.scripts)
                self.assertFalse(result[0])

    def test_default_small_project_without_memory_skips_memory_check(self):
        _, result = self.check_with_layout(self.scripts)
        self.assertTrue(result[0], result[1])
        self.assertEqual("", result[1])

    def test_explicit_medium_profile_requires_memory_directory(self):
        active = self.root / "docs" / "plans" / "active"
        active.mkdir(parents=True)
        (active / "initialization.md").write_text(
            "---\nstatus: in_progress\nsize: ' MEDIUM '\n---\n", encoding="utf-8")

        _, result = self.check_with_layout(self.scripts)

        self.assertFalse(result[0])
        self.assertIn("显式中大型项目", result[1])

    def test_explicit_small_profile_without_memory_still_skips(self):
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "initialization.md").write_text("---\nsize: small\n---\n", encoding="utf-8")

        _, result = self.check_with_layout(self.scripts)

        self.assertTrue(result[0], result[1])

    def test_unreadable_profile_fails_memory_check_cleanly(self):
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "initialization.md").write_bytes(b"\xff")

        _, result = self.check_with_layout(self.scripts)

        self.assertFalse(result[0])
        self.assertIn("无法读取初始化档案", result[1])

    def run_completion_check(self, agents_text, profile=False, include_audit=True, small=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        scripts = root / "scripts"
        scripts.mkdir()
        names = ["check_all.py", "changelog.py"]
        if include_audit:
            names.append("audit.py")
        for name in names:
            shutil.copyfile(Path(__file__).resolve().parents[1] / "assets" / "scripts" / name,
                            scripts / name)
        docs = root / "docs"
        docs.mkdir()
        (docs / "CHANGELOG.md").write_text("# CHANGELOG\n## 2026-01-01\n", encoding="utf-8")
        (root / "AGENTS.md").write_text(agents_text, encoding="utf-8")
        if profile:
            active = docs / "plans" / "active"
            active.mkdir(parents=True)
            (active / "initialization.md").write_text(
                "---\nstatus: in_progress\nsize: medium\nrepository_mode: no-git\n---\n",
                encoding="utf-8")
        args = [sys.executable, str(scripts / "check_all.py"), "--quiet"]
        if small:
            args.append("--small")
        return subprocess.run(
            args,
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"})

    def test_overall_check_fails_on_dead_memory_link_without_profile(self):
        result = self.run_completion_check("# Project\n[Memory](.agents/memory/MEMORY.md)\n")

        self.assertEqual(result.returncode, 1)
        self.assertIn("死链", result.stdout)

    def test_overall_check_fails_memory_component_for_medium_profile_without_link(self):
        result = self.run_completion_check("# Project\n", profile=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn("记忆", result.stdout)
        self.assertNotIn("死链", result.stdout)

    def test_missing_audit_fails_even_in_small_mode(self):
        result = self.run_completion_check("# Project\n", include_audit=False, small=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn("死链", result.stdout)
        self.assertIn("audit.py 不存在", result.stdout)

    def test_meta_layout_requires_nonblank_utf8_memory_index(self):
        scripts = self.root / ".meta" / "scripts"
        scripts.mkdir(parents=True)
        agents_result, result = self.check_with_layout(scripts)
        self.assertTrue(agents_result[0], agents_result[1])
        self.assertFalse(result[0])

        memory = self.root / ".meta" / "memory"
        memory.mkdir()
        index = memory / "MEMORY.md"
        for label, content in (("missing", None), ("blank", b"\n"), ("invalid", b"\xff")):
            with self.subTest(label=label):
                index.unlink(missing_ok=True)
                if content is not None:
                    index.write_bytes(content)
                _, result = self.check_with_layout(scripts)
                self.assertFalse(result[0])

    def install_scripts(self, *names):
        for name in names:
            shutil.copyfile(
                Path(__file__).resolve().parents[1] / "assets" / "scripts" / name,
                self.scripts / name,
            )

    def patch_completion_root(self):
        patchers = [
            patch.object(check_all, "ROOT", self.root),
            patch.object(check_all, "SCRIPTS_DIR", self.scripts),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_changelog_and_dead_links_run_without_subprocess(self):
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "CHANGELOG.md").write_text(
            "# CHANGELOG\n\n## 2026-01-01\n\n### 条目\n\n- 变更\n", encoding="utf-8"
        )
        self.install_scripts("changelog.py", "audit.py")
        self.patch_completion_root()

        with patch.object(check_all.subprocess, "run", side_effect=AssertionError("subprocess")):
            changelog_ok, changelog_detail = check_all._check_changelog()
            links_ok, links_detail = check_all._check_dead_links()

        self.assertTrue(changelog_ok, changelog_detail)
        self.assertIn("2026-01-01", changelog_detail)
        self.assertIn("  - 条目", changelog_detail)
        self.assertTrue(links_ok, links_detail)

    def test_changelog_boundaries_still_fail_cleanly(self):
        docs = self.root / "docs"
        docs.mkdir()
        self.install_scripts("changelog.py")
        self.patch_completion_root()
        changelog = docs / "CHANGELOG.md"

        cases = (
            ("missing", None, "不存在"),
            ("empty", "", "无条目"),
            ("no-date", "# CHANGELOG\n", "无条目"),
            ("invalid-utf8", b"\xff", "UTF-8"),
        )
        with patch.object(check_all.subprocess, "run", side_effect=AssertionError("subprocess")):
            for label, content, expected in cases:
                with self.subTest(label=label):
                    changelog.unlink(missing_ok=True)
                    if content is not None:
                        if isinstance(content, bytes):
                            changelog.write_bytes(content)
                        else:
                            changelog.write_text(content, encoding="utf-8")
                    ok, detail = check_all._check_changelog()
                    self.assertFalse(ok)
                    self.assertIn(expected, detail)

    def test_missing_audit_keeps_existing_diagnostic(self):
        self.patch_completion_root()

        with patch.object(check_all.subprocess, "run", side_effect=AssertionError("subprocess")):
            ok, detail = check_all._check_dead_links()

        self.assertFalse(ok)
        self.assertEqual(detail, "scripts/audit.py 不存在——无法执行死链审计")

    def test_syntax_error_sibling_fails_one_check_and_keeps_going(self):
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "CHANGELOG.md").write_text(
            "# CHANGELOG\n\n## 2026-01-01\n\n### 条目\n", encoding="utf-8"
        )
        self.install_scripts("audit.py")
        (self.scripts / "changelog.py").write_text("def broken(:\n", encoding="utf-8")
        self.patch_completion_root()

        ok, detail = check_all._check_changelog()

        self.assertFalse(ok)
        self.assertIn("CHANGELOG 检查失败", detail)
        self.assertTrue(check_all._check_line_budget()[0])
        self.assertTrue(check_all._check_dead_links()[0])

    def test_legacy_changelog_interface_is_supported(self):
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "CHANGELOG.md").write_text(
            "# CHANGELOG\n\n## 2026-01-01\n\n### 旧条目\n", encoding="utf-8"
        )
        (self.scripts / "changelog.py").write_text(
            "import re\n"
            "DATE_HEADING_RE = re.compile(r'^## (\\d{4}-\\d{2}-\\d{2})(?:[：:](.*))?\\s*$')\n"
            "SECTION_HEADING_RE = re.compile(r'^###\\s+(.+?)\\s*$')\n"
            "def read_lines(path):\n"
            "    return path.read_text(encoding='utf-8').splitlines()\n"
            "def iter_date_blocks(lines):\n"
            "    starts = [i for i, line in enumerate(lines) if DATE_HEADING_RE.match(line)]\n"
            "    blocks = []\n"
            "    for pos, start in enumerate(starts):\n"
            "        m = DATE_HEADING_RE.match(lines[start])\n"
            "        end = starts[pos + 1] if pos + 1 < len(starts) else len(lines)\n"
            "        blocks.append((start, end, m.group(1), (m.group(2) or '').strip()))\n"
            "    return blocks\n"
            "def iter_sections(block_lines):\n"
            "    starts = [i for i, line in enumerate(block_lines) if SECTION_HEADING_RE.match(line)]\n"
            "    sections = []\n"
            "    for pos, start in enumerate(starts):\n"
            "        m = SECTION_HEADING_RE.match(block_lines[start])\n"
            "        end = starts[pos + 1] if pos + 1 < len(starts) else len(block_lines)\n"
            "        sections.append((start, end, m.group(1)))\n"
            "    return sections\n",
            encoding="utf-8",
        )
        self.patch_completion_root()

        ok, detail = check_all._check_changelog()

        self.assertTrue(ok, detail)
        self.assertIn("2026-01-01", detail)
        self.assertIn("  - 旧条目", detail)

    def test_sibling_loads_leave_no_modules_or_bytecode(self):
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "CHANGELOG.md").write_text(
            "# CHANGELOG\n\n## 2026-01-01\n\n### 条目\n", encoding="utf-8"
        )
        self.install_scripts("changelog.py", "audit.py")
        self.patch_completion_root()

        self.assertTrue(check_all._check_changelog()[0])
        self.assertTrue(check_all._check_dead_links()[0])

        self.assertFalse([
            name for name in sys.modules if name.startswith("_iad_check_all_")
        ])
        self.assertFalse((self.scripts / "__pycache__").exists())

    def run_main_with_systemexit(self, broken_name: str):
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "CHANGELOG.md").write_text(
            "# CHANGELOG\n\n## 2026-01-01\n\n### 条目\n", encoding="utf-8"
        )
        other = "audit.py" if broken_name == "changelog.py" else "changelog.py"
        self.install_scripts(other)
        (self.scripts / broken_name).write_text("raise SystemExit(2)\n", encoding="utf-8")
        self.patch_completion_root()
        out = io.StringIO()
        with patch.object(sys, "argv", ["check_all.py"]), redirect_stdout(out):
            rc = check_all.main()
        return rc, out.getvalue()

    def test_systemexit_in_changelog_is_one_failed_check(self):
        rc, output = self.run_main_with_systemexit("changelog.py")

        self.assertEqual(rc, 1, output)
        self.assertIn("CHANGELOG", output)
        self.assertIn("死链", output)
        self.assertIn("[OK] 死链", output)
        self.assertIn("共 1 项未通过", output)

    def test_systemexit_in_audit_is_one_failed_check(self):
        rc, output = self.run_main_with_systemexit("audit.py")

        self.assertEqual(rc, 1, output)
        self.assertIn("死链", output)
        self.assertIn("[FAIL] 死链", output)
        self.assertIn("[OK] CHANGELOG", output)
        self.assertIn("共 1 项未通过", output)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for completion checks in project and knowledge-base layouts."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()

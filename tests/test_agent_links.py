"""Subprocess-based smoke tests for assets/scripts/agent_links.py.

Tests cover the three flows that matter in practice:
- Hardlink mode: repair creates hardlinks, check verifies same inode
- Copy mode: repair copies content, check accepts content equality
- Source override: when AGENTS.md is missing, --from=claude rebuilds from CLAUDE.md

Skipped on filesystems without hardlink support to keep CI green on Windows runners.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "assets" / "scripts" / "agent_links.py"


def hardlinks_supported(directory: Path) -> bool:
    src = directory / "_hl_probe"
    dst = directory / "_hl_probe_link"
    src.write_text("x", encoding="utf-8")
    try:
        os.link(src, dst)
    except OSError:
        return False
    finally:
        for p in (src, dst):
            if p.exists():
                p.unlink()
    return True


class AgentLinksTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="agent_links_"))
        self.scripts_dir = self.tmp / "scripts"
        self.scripts_dir.mkdir()
        shutil.copy(SCRIPT, self.scripts_dir / "agent_links.py")
        (self.tmp / "AGENTS.md").write_text("hello\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        return subprocess.run(
            [sys.executable, str(self.scripts_dir / "agent_links.py"), *args],
            cwd=self.tmp,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

    def test_hardlink_repair_then_check(self) -> None:
        if not hardlinks_supported(self.tmp):
            self.skipTest("filesystem does not support hardlinks")

        result = self.run_script("repair", "--mode=hardlink")
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.run_script("check", "--verbose")
        self.assertEqual(result.returncode, 0, result.stderr)

        agents_inode = (self.tmp / "AGENTS.md").stat().st_ino
        claude_inode = (self.tmp / "CLAUDE.md").stat().st_ino
        gemini_inode = (self.tmp / "GEMINI.md").stat().st_ino
        self.assertEqual(agents_inode, claude_inode)
        self.assertEqual(agents_inode, gemini_inode)

    def test_copy_mode_repair_then_check(self) -> None:
        result = self.run_script("repair", "--mode=copy")
        self.assertEqual(result.returncode, 0, result.stderr)

        agents_inode = (self.tmp / "AGENTS.md").stat().st_ino
        claude_inode = (self.tmp / "CLAUDE.md").stat().st_ino
        self.assertNotEqual(agents_inode, claude_inode, "copy mode should not hardlink")

        result = self.run_script("check", "--mode=copy", "--verbose")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_repair_defaults_to_copy(self) -> None:
        result = self.run_script("repair")
        self.assertEqual(result.returncode, 0, result.stderr)
        agents_inode = (self.tmp / "AGENTS.md").stat().st_ino
        claude_inode = (self.tmp / "CLAUDE.md").stat().st_ino
        self.assertNotEqual(agents_inode, claude_inode, "default repair should use copy")
        result = self.run_script("check")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_copy_breaks_equal_content_full_hardlink_group(self) -> None:
        if not hardlinks_supported(self.tmp):
            self.skipTest("filesystem does not support hardlinks")
        self.assertEqual(self.run_script("repair", "--mode=hardlink").returncode, 0)
        result = self.run_script("repair")
        self.assertEqual(result.returncode, 0, result.stderr)
        keys = [(self.tmp / name).stat().st_ino for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md")]
        self.assertEqual(len(set(keys)), 3, keys)
        self.assertEqual(self.run_script("check", "--mode=copy").returncode, 0)

    def test_copy_breaks_partial_hardlink_group(self) -> None:
        if not hardlinks_supported(self.tmp):
            self.skipTest("filesystem does not support hardlinks")
        os.link(self.tmp / "AGENTS.md", self.tmp / "CLAUDE.md")
        (self.tmp / "GEMINI.md").write_text("hello\n", encoding="utf-8")
        self.assertNotEqual(self.run_script("check", "--mode=copy").returncode, 0)
        result = self.run_script("repair", "--mode=copy")
        self.assertEqual(result.returncode, 0, result.stderr)
        keys = [(self.tmp / name).stat().st_ino for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md")]
        self.assertEqual(len(set(keys)), 3, keys)

    def test_non_force_refuses_divergence_before_touching_other_targets(self) -> None:
        self.assertEqual(self.run_script("repair", "--mode=hardlink").returncode, 0)
        (self.tmp / "GEMINI.md").unlink()
        (self.tmp / "GEMINI.md").write_text("review me\n", encoding="utf-8")
        claude_inode = (self.tmp / "CLAUDE.md").stat().st_ino
        result = self.run_script("repair", "--mode=copy")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.tmp / "CLAUDE.md").stat().st_ino, claude_inode)
        self.assertEqual((self.tmp / "GEMINI.md").read_text(encoding="utf-8"), "review me\n")

    def test_force_copy_overwrites_reviewed_targets(self) -> None:
        (self.tmp / "CLAUDE.md").write_text("old\n", encoding="utf-8")
        (self.tmp / "GEMINI.md").write_text("old\n", encoding="utf-8")
        result = self.run_script("repair", "--mode=copy", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_script("check", "--mode=copy").returncode, 0)

    def test_declared_mode_is_machine_readable(self) -> None:
        (self.tmp / "AGENTS.md").write_text(
            "<!-- agent-docs-sync-mode: copy -->\nhello\n", encoding="utf-8")
        self.assertEqual(self.run_script("repair", "--mode=copy", "--force").returncode, 0)
        self.assertEqual(self.run_script("check", "--mode=declared").returncode, 0)

    def test_check_rejects_diverged_content_in_copy_mode(self) -> None:
        self.run_script("repair", "--mode=copy")
        (self.tmp / "CLAUDE.md").write_text("diverged\n", encoding="utf-8")
        result = self.run_script("check", "--mode=copy")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected mode=copy", result.stderr)

    def test_check_rejects_missing_files(self) -> None:
        result = self.run_script("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing file(s)", result.stderr)

    def test_check_rejects_diverged_content(self) -> None:
        if not hardlinks_supported(self.tmp):
            self.skipTest("filesystem does not support hardlinks")
        self.run_script("repair")
        # Break the hardlink by replacing CLAUDE.md with a new inode + new content
        (self.tmp / "CLAUDE.md").unlink()
        (self.tmp / "CLAUDE.md").write_text("diverged\n", encoding="utf-8")

        result = self.run_script("check")
        self.assertNotEqual(result.returncode, 0)

    def test_repair_from_claude_when_agents_missing(self) -> None:
        if not hardlinks_supported(self.tmp):
            self.skipTest("filesystem does not support hardlinks")

        # Wipe everything and start with only CLAUDE.md
        for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            p = self.tmp / name
            if p.exists():
                p.unlink()
        (self.tmp / "CLAUDE.md").write_text("from-claude\n", encoding="utf-8")

        # Default repair should refuse because AGENTS.md missing
        result = self.run_script("repair")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--from=claude", result.stderr)

        # With --from=claude it should rebuild AGENTS.md (GEMINI.md still missing → fine)
        result = self.run_script("repair", "--from=claude")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.tmp / "AGENTS.md").read_text(encoding="utf-8"),
            "from-claude\n",
        )

    def test_check_mode_mismatch_is_rejected(self) -> None:
        if not hardlinks_supported(self.tmp):
            self.skipTest("filesystem does not support hardlinks")
        self.run_script("repair", "--mode=copy")
        result = self.run_script("check", "--mode=hardlink")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()

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

        result = self.run_script("repair")
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

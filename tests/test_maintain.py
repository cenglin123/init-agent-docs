"""Functional tests for assets/scripts/maintain.py on a synthetic project."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_SCRIPT = REPO_ROOT / "assets" / "scripts" / "maintain.py"

MEMORY_MD = """# 项目记忆索引

## 记忆条目索引

<!-- memory-index:start -->
（占位）
<!-- memory-index:end -->

## 记忆规则
"""


class MaintainPipelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "scripts").mkdir()
        shutil.copy(ASSET_SCRIPT, self.root / "scripts" / "maintain.py")
        mem = self.root / ".agent" / "memory"
        (mem / "user").mkdir(parents=True)
        (mem / "feedback").mkdir()
        (mem / "MEMORY.md").write_text(MEMORY_MD, encoding="utf-8")
        (mem / "user" / "role.md").write_text("# 用户画像\n\n称呼：测试\n", encoding="utf-8")
        (mem / "feedback" / "20260101-prefer-lf.md").write_text(
            "# 偏好 LF 行尾\n\nWindows 下注意。\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_maintain(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, PYTHONUTF8="1")
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / "maintain.py"), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=60,
        )

    def test_memory_index_rebuild_and_idempotency(self) -> None:
        first = self.run_maintain("--memory-index")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        content = (self.root / ".agent" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("禁止手工编辑", content)
        self.assertIn("### user", content)
        self.assertIn("### feedback", content)
        self.assertIn("[role.md](user/role.md)", content)
        self.assertIn("[20260101-prefer-lf.md](feedback/20260101-prefer-lf.md)", content)
        self.assertIn("## 记忆规则", content)

        second = self.run_maintain("--memory-index")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("up to date", second.stdout)

    def test_check_detects_stale_index(self) -> None:
        self.assertEqual(self.run_maintain("--memory-index").returncode, 0)
        index = self.root / ".agent" / "memory" / "MEMORY.md"
        text = index.read_text(encoding="utf-8").replace(
            "[role.md](user/role.md)", "[role.md](user/role.md) — 手改"
        )
        index.write_text(text, encoding="utf-8")

        check = self.run_maintain("--check")
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        self.assertIn("out of date", check.stdout)

        healed = self.run_maintain("--check")
        # --check 不写文件，仍然 stale
        self.assertEqual(healed.returncode, 1)
        self.assertEqual(self.run_maintain("--memory-index").returncode, 0)
        self.assertEqual(self.run_maintain("--check").returncode, 0)

    def test_full_run_skips_missing_sibling_scripts(self) -> None:
        result = self.run_maintain()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("audit.py not found", result.stdout)
        self.assertIn("agent_links.py not found", result.stdout)

    def test_missing_memory_md_fails(self) -> None:
        (self.root / ".agent" / "memory" / "MEMORY.md").unlink()
        result = self.run_maintain("--memory-index")
        self.assertEqual(result.returncode, 1)
        check = self.run_maintain("--check")
        self.assertEqual(check.returncode, 1)


if __name__ == "__main__":
    unittest.main()

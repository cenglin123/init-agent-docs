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

    def test_no_markers_fails(self) -> None:
        index = self.root / ".agent" / "memory" / "MEMORY.md"
        index.write_text("# 项目记忆索引\n\n无标记段的旧版文件。\n", encoding="utf-8")
        result = self.run_maintain("--memory-index")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("memory-index:start", result.stdout)
        check = self.run_maintain("--check")
        self.assertEqual(check.returncode, 1)

    def test_small_project_skip(self) -> None:
        import shutil as _shutil

        _shutil.rmtree(self.root / ".agent")
        result = self.run_maintain("--memory-index")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("small project", result.stdout)
        full = self.run_maintain()
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        check = self.run_maintain("--check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_staleness_uses_git_commit_time_over_mtime(self) -> None:
        """git 不保留 mtime：fresh clone 后活性统计应以最后提交时间为准。"""
        from datetime import datetime, timedelta

        def git(*args: str, env: dict[str, str] | None = None) -> None:
            proc = subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                cwd=self.root,
                capture_output=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))

        old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S")
        commit_env = dict(
            os.environ,
            GIT_AUTHOR_DATE=old_date,
            GIT_COMMITTER_DATE=old_date,
        )
        git("init")
        git("add", ".")
        git("commit", "-m", "old memory", env=commit_env)
        # 模拟 fresh clone：所有记忆文件 mtime 刷成现在
        for p in (self.root / ".agent" / "memory").rglob("*.md"):
            os.utime(p)

        result = self.run_maintain()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("memory untouched", result.stdout)


if __name__ == "__main__":
    unittest.main()

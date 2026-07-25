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
AUDIT_SCRIPT = REPO_ROOT / "assets" / "scripts" / "audit.py"

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

    def run_audit(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, PYTHONUTF8="1")
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / "audit.py"), *args],
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

    def test_bugfix_index_section(self) -> None:
        """docs/problems/bugfix/ 存在时，索引段追加 bugfix 分区（frontmatter 驱动）。"""
        bugfix_dir = self.root / "docs" / "problems" / "bugfix"
        bugfix_dir.mkdir(parents=True)
        (bugfix_dir / "_template.md").write_text("# 模板\n", encoding="utf-8")
        (bugfix_dir / "login-timeout.md").write_text(
            "---\n"
            "title: 登录接口超时后前端重复提交\n"
            "status: fixed\n"
            "severity: high\n"
            "liveness: active\n"
            "updated_at: 2026-07-20\n"
            "---\n\n# 登录接口超时后前端重复提交\n",
            encoding="utf-8",
        )
        (bugfix_dir / "no-frontmatter.md").write_text("# 裸标题文档\n", encoding="utf-8")

        result = self.run_maintain("--memory-index")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        content = (self.root / ".agent" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("### bugfix（docs/problems/bugfix/）", content)
        self.assertIn(
            "[登录接口超时后前端重复提交](../../docs/problems/bugfix/login-timeout.md)"
            " — fixed · high · active · 更新于 2026-07-20",
            content,
        )
        self.assertIn(
            "[裸标题文档](../../docs/problems/bugfix/no-frontmatter.md)", content
        )
        self.assertNotIn("_template.md", content)

        # 幂等：第二次重建应报 up to date
        second = self.run_maintain("--memory-index")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("up to date", second.stdout)

        # 活性统计把 bugfix 文档计入经验总量
        full = self.run_maintain()
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        self.assertIn("含 2 bugfix", full.stdout)

    def test_memory_entry_liveness_marker(self) -> None:
        """记忆条目索引行展示 liveness 活性标记；无 frontmatter 的旧记忆文件不追加（向后兼容）。"""
        (self.root / ".agent" / "memory" / "feedback" / "20260101-prefer-lf.md").write_text(
            "---\n"
            "liveness: active\n"
            "last_confirmed: \"\"\n"
            "confirmed_count: 0\n"
            "---\n\n# 偏好 LF 行尾\n\nWindows 下注意。\n",
            encoding="utf-8",
        )
        result = self.run_maintain("--memory-index")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        content = (self.root / ".agent" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
        feedback_line = next(
            line for line in content.splitlines() if "20260101-prefer-lf.md" in line
        )
        role_line = next(line for line in content.splitlines() if "[role.md]" in line)
        self.assertTrue(feedback_line.rstrip().endswith("· active"), feedback_line)
        self.assertNotIn("· active", role_line)

    def test_audit_handles_bugfix_directory(self) -> None:
        """audit.py 适配 docs/problems/bugfix/：目录行不 [MISS]、逐篇不 [ORPHAN]、目录链接不 [DEAD]；
        并锁定 _frontmatter_value 空值不串读到下一行。"""
        shutil.copy(AUDIT_SCRIPT, self.root / "scripts" / "audit.py")
        docs = self.root / "docs"
        bugfix_dir = docs / "problems" / "bugfix"
        bugfix_dir.mkdir(parents=True)
        (docs / "STRUCTURE.md").write_text(
            "# 文档结构索引\n\n"
            "| 需要了解 | 文件 |\n"
            "|---------|------|\n"
            "| 系统主线 | [overview.md](overview.md) |\n"
            "| Bugfix 档案 | [problems/bugfix/](problems/bugfix/) |\n",
            encoding="utf-8",
        )
        (docs / "overview.md").write_text("# 项目总览\n", encoding="utf-8")
        (bugfix_dir / "_template.md").write_text("# 模板\n", encoding="utf-8")
        (bugfix_dir / "login-timeout.md").write_text(
            "---\n"
            "title: 登录接口超时后前端重复提交\n"
            "status: fixed\n"
            "---\n\n# 登录接口超时后前端重复提交\n",
            encoding="utf-8",
        )

        structure = self.run_audit("structure")
        self.assertEqual(structure.returncode, 0, structure.stdout + structure.stderr)
        dead_links = self.run_audit("dead-links")
        self.assertEqual(dead_links.returncode, 0, dead_links.stdout + dead_links.stderr)

        # audit.py memory：索引段重建后，bugfix 链接（../../docs/problems/bugfix/...）
        # 相对 MEMORY.md 所在目录解析，不应误报 dead_link。
        # 合成项目没有 AGENTS.md，_check_memory 跳过 AGENTS 指针检查，不影响本子命令。
        self.assertEqual(self.run_maintain("--memory-index").returncode, 0)
        memory = self.run_audit("memory")
        self.assertEqual(memory.returncode, 0, memory.stdout + memory.stderr)
        self.assertNotIn("dead_link", memory.stdout + memory.stderr)

        # _frontmatter_value 边界：title 空值不得串读到下一行字段，标题回退到 ATX 启发式
        (bugfix_dir / "empty-title.md").write_text(
            "---\n"
            "title:\n"
            "status: fixed\n"
            "severity: low\n"
            "---\n\n# 空标题回退\n",
            encoding="utf-8",
        )
        result = self.run_maintain("--memory-index")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        content = (self.root / ".agent" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("[空标题回退](../../docs/problems/bugfix/empty-title.md)", content)
        self.assertNotIn("[status: fixed]", content)

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

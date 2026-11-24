"""Functional tests for assets/scripts/maintain.py on a synthetic project."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

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
        mem = self.root / ".agents" / "memory"
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

    def install_failing_git_sentinel(self) -> Path:
        bin_dir = self.root / "sentinel-bin"
        bin_dir.mkdir()
        if os.name == "nt":
            sentinel = bin_dir / "git.cmd"
            sentinel.write_text("@echo sentinel-git-invoked 1>&2\r\n@exit /b 97\r\n", encoding="utf-8")
        else:
            sentinel = bin_dir / "git"
            sentinel.write_text("#!/bin/sh\necho sentinel-git-invoked >&2\nexit 97\n", encoding="utf-8")
            sentinel.chmod(0o755)
        return bin_dir

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
        content = (self.root / ".agents" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
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
        index = self.root / ".agents" / "memory" / "MEMORY.md"
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
        self.assertNotIn("agent_links", result.stdout)

    def test_missing_memory_md_fails(self) -> None:
        (self.root / ".agents" / "memory" / "MEMORY.md").unlink()
        result = self.run_maintain("--memory-index")
        self.assertEqual(result.returncode, 1)
        check = self.run_maintain("--check")
        self.assertEqual(check.returncode, 1)

    def test_invalid_utf8_memory_index_and_entry_fail_without_tracebacks(self) -> None:
        paths = (
            self.root / ".agents" / "memory" / "MEMORY.md",
            self.root / ".agents" / "memory" / "user" / "role.md",
            self.root / "docs" / "problems" / "bugfix" / "broken.md",
        )
        for path in paths:
            with self.subTest(path=path.name):
                (self.root / ".agents" / "memory" / "MEMORY.md").write_text(
                    MEMORY_MD, encoding="utf-8")
                (self.root / ".agents" / "memory" / "user" / "role.md").write_text(
                    "# 用户画像\n", encoding="utf-8")
                broken = self.root / "docs" / "problems" / "bugfix" / "broken.md"
                broken.unlink(missing_ok=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"\xff")
                shutil.copy(AUDIT_SCRIPT, self.root / "scripts" / "audit.py")
                for args in (("--memory-index",), ("--check",), ()):
                    result = self.run_maintain(*args)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(path.relative_to(self.root).as_posix(), result.stdout)
                    self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_check_reports_invalid_utf8_docs_and_plans_without_traceback(self) -> None:
        shutil.copy(AUDIT_SCRIPT, self.root / "scripts" / "audit.py")
        docs = self.root / "docs"
        (docs / "plans" / "active").mkdir(parents=True)
        (self.root / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
        (docs / "STRUCTURE.md").write_text("# Index\n", encoding="utf-8")
        cases = (
            (docs / "initialization.md", b"# broken\n\xff"),
            (docs / "notes.md", b"# note\n\xff"),
            (docs / "audit-checklist.md", b"# checklist\n\xff"),
            (docs / "plans" / "active" / "plan.md", b"---\nstatus: in_progress\n---\n\xff"),
        )
        for path, content in cases:
            with self.subTest(path=path.relative_to(self.root).as_posix()):
                for candidate, _ in cases:
                    candidate.unlink(missing_ok=True)
                path.write_bytes(content)
                result = self.run_maintain("--check")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(path.relative_to(self.root).as_posix(), result.stdout)
                self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_no_markers_fails(self) -> None:
        index = self.root / ".agents" / "memory" / "MEMORY.md"
        index.write_text("# 项目记忆索引\n\n无标记段的旧版文件。\n", encoding="utf-8")
        result = self.run_maintain("--memory-index")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("memory-index:start", result.stdout)
        check = self.run_maintain("--check")
        self.assertEqual(check.returncode, 1)

    def test_small_project_skip(self) -> None:
        import shutil as _shutil

        _shutil.rmtree(self.root / ".agents")
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
        content = (self.root / ".agents" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
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
        (self.root / ".agents" / "memory" / "feedback" / "20260101-prefer-lf.md").write_text(
            "---\n"
            "liveness: active\n"
            "last_confirmed: \"\"\n"
            "confirmed_count: 0\n"
            "---\n\n# 偏好 LF 行尾\n\nWindows 下注意。\n",
            encoding="utf-8",
        )
        result = self.run_maintain("--memory-index")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        content = (self.root / ".agents" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
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
        content = (self.root / ".agents" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
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
        for p in (self.root / ".agents" / "memory").rglob("*.md"):
            os.utime(p)

        result = self.run_maintain()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("memory untouched", result.stdout)

    def test_no_git_project_never_invokes_git_for_memory_or_recent_context(self) -> None:
        bin_dir = self.install_failing_git_sentinel()
        env = dict(os.environ, PYTHONUTF8="1", PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "maintain.py")],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("sentinel-git-invoked", result.stdout + result.stderr)
        self.assertIn("文件时间", result.stdout)

    def test_nested_no_git_root_does_not_inherit_parent_git_capability(self) -> None:
        import importlib.util
        from unittest.mock import patch

        spec = importlib.util.spec_from_file_location("nested_maintain", ASSET_SCRIPT)
        maintain = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(maintain)
        (self.root / ".git").mkdir()
        child = self.root / "nested-no-git"
        child.mkdir()
        entry = child / "memory.md"
        entry.write_text("# Memory\n", encoding="utf-8")
        with patch.object(maintain, "ROOT", child), patch.object(maintain, "BUGFIX_DIR", child / "absent"), patch.object(maintain.subprocess, "run") as run:
            self.assertFalse(maintain._is_git_repo())
            self.assertEqual(maintain._git_recent(), [])
            self.assertEqual(maintain._memory_last_update_ts([entry]), entry.stat().st_mtime)
            run.assert_not_called()
        # A worktree pointer file at the target root still declares Git capability.
        (child / ".git").write_text("gitdir: ../.git/worktrees/child\n", encoding="utf-8")
        with patch.object(maintain, "ROOT", child):
            self.assertTrue(maintain._is_git_repo())

    def test_delegated_audit_failure_propagates(self) -> None:
        (self.root / "scripts" / "audit.py").write_text(
            "raise SystemExit(7)\n", encoding="utf-8")
        result = self.run_maintain()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("audit.py check (exit 7)", result.stdout)

    def test_old_plan_age_warnings_do_not_fail_maintenance_check(self) -> None:
        shutil.copy(AUDIT_SCRIPT, self.root / "scripts" / "audit.py")
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "STRUCTURE.md").write_text(
            "# Index\n\n| Document | Description |\n|---|---|\n"
            "| [Initialization](initialization.md) | Birth record |\n",
            encoding="utf-8")
        (docs / "initialization.md").write_text(
            "---\nsize: small\nstatus: in_progress\nrepository_mode: no-git\n---\n",
            encoding="utf-8")
        (self.root / "AGENTS.md").write_text(
            "# Project\n.agents/memory/MEMORY.md\n## 项目记忆\n", encoding="utf-8")

        completed = docs / "plans" / "completed"
        completed.mkdir(parents=True)
        old_done = completed / "historical.md"
        old_done.write_text("---\nstatus: done\n---\n", encoding="utf-8")
        os.utime(old_done, (946684800, 946684800))
        self.assertEqual(self.run_maintain("--memory-index").returncode, 0)
        self.assertEqual(self.run_maintain("--check").returncode, 0)

        active = docs / "plans" / "active"
        active.mkdir()
        old_active = active / "ongoing.md"
        old_active.write_text("---\nstatus: in_progress\n---\n", encoding="utf-8")
        os.utime(old_active, (946684800, 946684800))
        check = self.run_maintain("--check")

        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("WARN", check.stdout)
        self.assertIn("ongoing.md", check.stdout)


    def install_real_audit_project(
        self, *, check_status: str = "ok", check_rc: int = 0,
        build_status: str = "built",
    ) -> Path:
        """Install the real audit.py and a controllable repo_graph.py stand-in."""
        shutil.copy(AUDIT_SCRIPT, self.root / "scripts" / "audit.py")
        graph_dir = self.root / ".agents" / "repo-graph"
        graph_dir.mkdir(parents=True, exist_ok=True)
        (graph_dir / "manifest.json").write_text("{}", encoding="utf-8")
        (self.root / "scripts" / "repo_graph_config.json").write_text(
            json.dumps({
                "check_status": check_status,
                "check_rc": check_rc,
                "build_status": build_status,
            }),
            encoding="utf-8",
        )
        calls = self.root / "scripts" / "repo_graph_calls.txt"
        calls.unlink(missing_ok=True)
        (self.root / "scripts" / "repo_graph.py").write_text(
            "import json, pathlib, sys\n"
            "here = pathlib.Path(__file__).resolve().parent\n"
            "with (here / 'repo_graph_calls.txt').open('a', encoding='utf-8') as stream:\n"
            "    stream.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "config = json.loads((here / 'repo_graph_config.json').read_text(encoding='utf-8'))\n"
            "if sys.argv[1:2] == ['check']:\n"
            "    status = config['check_status']; rc = config['check_rc']\n"
            "else:\n"
            "    status = config['build_status']; rc = 0\n"
            "print(json.dumps({'status': status, 'detail': 'repo graph ' + status}))\n"
            "raise SystemExit(rc)\n",
            encoding="utf-8",
        )
        docs = self.root / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "STRUCTURE.md").write_text(
            "# Index\n\n| Document | Description |\n|---|---|\n"
            "| [Initialization](initialization.md) | Birth record |\n",
            encoding="utf-8",
        )
        (docs / "initialization.md").write_text(
            "---\nsize: small\nstatus: done\nrepository_mode: no-git\n---\n",
            encoding="utf-8",
        )
        (self.root / "AGENTS.md").write_text(
            "# Rules\n.agents/memory/MEMORY.md\n## 项目记忆\n", encoding="utf-8"
        )
        return calls

    def run_audit_check(self) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, PYTHONUTF8="1")
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / "audit.py"), "check"],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=60,
        )

    def test_check_validates_repo_graph_once_with_real_audit(self) -> None:
        self.assertEqual(self.run_maintain("--memory-index").returncode, 0)
        calls = self.install_real_audit_project(check_status="ok", check_rc=0)

        result = self.run_maintain("--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls.read_text(encoding="utf-8").splitlines(), ["check --json"])
        self.assertIn("repo graph", result.stdout)

    def test_built_is_invalid_for_both_maintain_and_audit(self) -> None:
        self.assertEqual(self.run_maintain("--memory-index").returncode, 0)
        calls = self.install_real_audit_project(check_status="built", check_rc=0)

        result = self.run_maintain("--check")
        maintain_calls = calls.read_text(encoding="utf-8").splitlines()
        audit = self.run_audit_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("INVALID", result.stdout)
        self.assertEqual(audit.returncode, 1, audit.stdout + audit.stderr)
        self.assertIn("not usable", audit.stdout)
        self.assertEqual(maintain_calls, ["check --json"])

    def test_check_propagates_stale_and_invalid_repo_graph_statuses(self) -> None:
        for status, rc, expected in (("stale", 1, "STALE"), ("invalid", 1, "INVALID")):
            with self.subTest(status=status):
                self.assertEqual(self.run_maintain("--memory-index").returncode, 0)
                calls = self.install_real_audit_project(check_status=status, check_rc=rc)

                result = self.run_maintain("--check")
                maintain_calls = calls.read_text(encoding="utf-8").splitlines()
                audit = self.run_audit_check()

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertEqual(
                    audit.returncode, 0 if status == "stale" else 1,
                    audit.stdout + audit.stderr,
                )
                self.assertEqual(maintain_calls, ["check --json"])

    def test_deep_json_repo_graph_output_is_invalid_without_traceback(self) -> None:
        self.assertEqual(self.run_maintain("--memory-index").returncode, 0)
        self.install_real_audit_project(check_status="ok")
        (self.root / "scripts" / "repo_graph.py").write_text(
            "print('[' * 5000 + ']' * 5000)\nraise SystemExit(0)\n",
            encoding="utf-8",
        )

        result = self.run_maintain("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("INVALID", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_check_uses_in_process_audit_when_graph_result_exists(self) -> None:
        self.assertEqual(self.run_maintain("--memory-index").returncode, 0)
        calls = self.install_real_audit_project(check_status="ok")
        (self.root / "scripts" / "audit.py").write_text(
            "import pathlib\n"
            "def run_check_in_process(*, repo_graph_prefetched=None):\n"
            "    here = pathlib.Path(__file__).resolve().parent\n"
            "    (here / 'audit_inproc.txt').write_text(\n"
            "        repr(repo_graph_prefetched), encoding='utf-8')\n"
            "    return 0, 'in-process audit'\n"
            "if __name__ == '__main__':\n"
            "    here = pathlib.Path(__file__).resolve().parent\n"
            "    (here / 'audit_cli.txt').write_text('cli', encoding='utf-8')\n"
            "    raise SystemExit(0)\n",
            encoding="utf-8",
        )

        result = self.run_maintain("--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("in-process audit", result.stdout)
        self.assertTrue((self.root / "scripts" / "audit_inproc.txt").is_file())
        self.assertFalse((self.root / "scripts" / "audit_cli.txt").exists())
        self.assertEqual(calls.read_text(encoding="utf-8").splitlines(), ["check --json"])

    def test_write_maintenance_keeps_post_write_repo_graph_verification(self) -> None:
        calls = self.install_real_audit_project(check_status="ok", build_status="built")

        result = self.run_maintain()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            calls.read_text(encoding="utf-8").splitlines(),
            ["build --json", "check --json"],
        )
        self.assertIn("repo graph", result.stdout)


class MaintainSingleReadTestCase(unittest.TestCase):
    """Index rebuild and search read each source file exactly once."""

    def setUp(self) -> None:
        import importlib.util
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        scripts = self.root / "scripts"
        scripts.mkdir()
        self.memory = self.root / ".agents" / "memory"
        (self.memory / "user").mkdir(parents=True)
        (self.memory / "feedback").mkdir()
        self.bugfix = self.root / "docs" / "problems" / "bugfix"
        self.bugfix.mkdir(parents=True)
        self.index = self.memory / "MEMORY.md"
        self.index.write_text(MEMORY_MD, encoding="utf-8")
        (self.memory / "user" / "role.md").write_text(
            "# 用户画像\n\n称呼：测试\n", encoding="utf-8"
        )
        (self.memory / "feedback" / "prefer-lf.md").write_text(
            "---\nliveness: active\n---\n\n# 偏好 LF 行尾\n\nWindows 下注意。\n",
            encoding="utf-8",
        )
        (self.bugfix / "login.md").write_text(
            "---\ntitle: 登录超时\nstatus: fixed\nseverity: high\n"
            "updated_at: 2026-07-20\n---\n\n# 登录超时\n",
            encoding="utf-8",
        )
        (self.bugfix / "plain.md").write_text(
            "# 裸标题文档\n\nWindows 相关。\n", encoding="utf-8"
        )
        self.entries = [
            self.memory / "user" / "role.md",
            self.memory / "feedback" / "prefer-lf.md",
            self.bugfix / "login.md",
            self.bugfix / "plain.md",
        ]

        spec = importlib.util.spec_from_file_location(
            "maintain_single_read", ASSET_SCRIPT
        )
        self.maintain = importlib.util.module_from_spec(spec)
        sys.modules["maintain_single_read"] = self.maintain
        spec.loader.exec_module(self.maintain)
        self.addCleanup(sys.modules.pop, "maintain_single_read", None)
        patcher = patch.multiple(
            self.maintain,
            ROOT=self.root,
            MEMORY_DIR=self.memory,
            MEMORY_INDEX=self.index,
            MEMORY_REL=".agents/memory",
            BUGFIX_DIR=self.bugfix,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def counting_read(self):
        calls: list[Path] = []
        original = self.maintain._read

        def read(path: Path) -> str:
            calls.append(Path(path))
            return original(path)

        return calls, read

    def test_rebuild_reads_each_source_once_and_renders_same_index(self) -> None:
        calls, read = self.counting_read()
        with patch.object(self.maintain, "_read", side_effect=read):
            status, detail = self.maintain.rebuild_memory_index(check_only=True)

        self.assertEqual(status, "stale", detail)
        counts = Counter(calls)
        self.assertEqual(counts[self.index], 1)
        for path in self.entries:
            self.assertEqual(counts[path], 1, path)

        memory_entries, bugfix_entries, invalid = self.maintain._load_index_entries(
            self.maintain._memory_files(), self.maintain._bugfix_files()
        )
        self.assertIsNone(invalid)
        section = self.maintain._render_index_section(memory_entries, bugfix_entries)
        self.assertIn("### user", section)
        self.assertIn("[role.md](user/role.md) — 用户画像", section)
        self.assertIn("· active", section)
        self.assertIn("[登录超时](../../docs/problems/bugfix/login.md)", section)
        self.assertIn("[裸标题文档](../../docs/problems/bugfix/plain.md)", section)
        self.assertLess(section.index("### feedback"), section.index("### user"))

    def test_search_reads_each_source_once_and_preserves_bounded_output(self) -> None:
        calls, read = self.counting_read()
        out = io.StringIO()
        with patch.object(self.maintain, "_read", side_effect=read), redirect_stdout(out):
            rc = self.maintain.search_memory("Windows", 1)

        self.assertEqual(rc, 0)
        counts = Counter(calls)
        for path in self.entries:
            self.assertEqual(counts[path], 1, path)
        self.assertNotIn(self.index, counts)
        text = out.getvalue()
        self.assertIn("命中 2 条；显示 1 条；截断：是", text)
        self.assertEqual(text.count("- ["), 1)

    def test_search_missing_title_falls_back_without_rereading(self) -> None:
        calls, read = self.counting_read()
        out = io.StringIO()
        with patch.object(self.maintain, "_read", side_effect=read), redirect_stdout(out):
            rc = self.maintain.search_memory("裸标题", 5)

        self.assertEqual(rc, 0)
        self.assertEqual(Counter(calls)[self.bugfix / "plain.md"], 1)
        self.assertIn("裸标题文档", out.getvalue())

    def test_bounded_push_never_exceeds_limit_and_keeps_smallest(self) -> None:
        heap = []
        for index in range(100):
            self.maintain._bounded_push(heap, (index, f"rel{index}"), 3)
            self.assertLessEqual(len(heap), 3)
        self.assertEqual([key[0] for key in sorted(w.key for w in heap)], [0, 1, 2])

    def test_search_ties_follow_relative_path_order(self) -> None:
        (self.memory / "user" / "alpha.md").write_text(
            "# Alpha\n\nneedle\n", encoding="utf-8"
        )
        (self.memory / "user" / "beta.md").write_text(
            "# Beta\n\nneedle\n", encoding="utf-8"
        )
        out = io.StringIO()
        with redirect_stdout(out):
            rc = self.maintain.search_memory("needle", 1)

        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("命中 2 条；显示 1 条；截断：是", text)
        self.assertIn("alpha.md", text)
        self.assertNotIn("beta.md", text)

    def test_search_excerpt_maps_casefold_expansion_back_to_original(self) -> None:
        body = "ABCD" + "x" * 38 + "ß" + "signal"
        (self.memory / "user" / "sharp.md").write_text(
            "# 展开\n\n" + body + "\n", encoding="utf-8"
        )
        out = io.StringIO()
        with redirect_stdout(out):
            rc = self.maintain.search_memory("signal", 1)

        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("命中 1 条", text)
        excerpt = text.split(" — ", 1)[1].splitlines()[0]
        # Correct origin is original index 3 ('D'); a raw casefold index would
        # start at 4 ('x') because 'ß' expanded to 'ss'.
        self.assertTrue(excerpt.startswith("D"), excerpt)
        self.assertIn("signal", excerpt)

    def test_search_reports_total_and_only_five_error_samples(self) -> None:
        for index in range(7):
            (self.memory / "user" / f"broken-{index}.md").write_bytes(b"\xff")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = self.maintain.search_memory("Windows", 5)

        self.assertEqual(rc, 1)
        text = out.getvalue()
        self.assertIn("7 个文件无法读取 UTF-8", text)
        self.assertEqual(text.count("broken-"), 5)

    def test_run_full_small_project_does_not_enumerate_memory(self) -> None:
        absent = self.root / "absent-memory"
        out = io.StringIO()
        with patch.multiple(
            self.maintain, MEMORY_DIR=absent, MEMORY_REL=".agents/memory"
        ), patch.object(
            self.maintain, "_memory_files", side_effect=AssertionError("scanned memory")
        ), patch.object(
            self.maintain, "_bugfix_files", side_effect=AssertionError("scanned bugfix")
        ), redirect_stdout(out):
            rc = self.maintain.run_full(check_only=True)

        self.assertEqual(rc, 0, out.getvalue())

    def test_search_skips_casefold_mapping_for_zero_hit_and_ascii(self) -> None:
        (self.memory / "user" / "big.md").write_text(
            "# Big\n\n" + ("A" * 200000) + " markerword\n", encoding="utf-8"
        )
        out = io.StringIO()
        with patch.object(
            self.maintain, "_casefold_index_to_original",
            side_effect=AssertionError("built a casefold mapping"),
        ), redirect_stdout(out):
            self.assertEqual(self.maintain.search_memory("nonexistentterm", 5), 0)
            self.assertEqual(self.maintain.search_memory("markerword", 5), 0)

        self.assertIn("markerword", out.getvalue())

    def test_kb_run_full_reuses_one_memory_enumeration(self) -> None:
        kb_dir = self.root / ".meta" / "memory"
        (kb_dir / "user").mkdir(parents=True)
        (kb_dir / "user" / "entry.md").write_text("# Entry\n", encoding="utf-8")
        index = kb_dir / "MEMORY.md"
        index.write_text("# KB\n", encoding="utf-8")
        scripts = self.root / "scripts"
        (scripts / "memory_index.py").write_text("", encoding="utf-8")
        counts = {"memory": 0, "bugfix": 0}
        original_memory = self.maintain._memory_files
        original_bugfix = self.maintain._bugfix_files

        def memory_files():
            counts["memory"] += 1
            return original_memory()

        def bugfix_files():
            counts["bugfix"] += 1
            return original_bugfix()

        out = io.StringIO()
        with patch.multiple(
            self.maintain,
            MEMORY_DIR=kb_dir,
            MEMORY_INDEX=index,
            MEMORY_REL=".meta/memory",
            SCRIPTS_DIR=scripts,
        ), patch.object(
            self.maintain, "_memory_files", side_effect=memory_files
        ), patch.object(
            self.maintain, "_bugfix_files", side_effect=bugfix_files
        ), patch.object(
            self.maintain, "_run_script", return_value=(0, "kb ok")
        ), redirect_stdout(out):
            rc = self.maintain.run_full(check_only=True)

        self.assertEqual(rc, 0, out.getvalue())
        self.assertEqual(counts, {"memory": 1, "bugfix": 1})


if __name__ == "__main__":
    unittest.main()

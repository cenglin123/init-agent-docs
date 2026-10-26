"""Functional contracts for assets/scripts/audit.py.

R1 (bugfix eval records) and the legacy checks are Git-free. R2
(eval-baseline behavior-surface scoring) is conditionally Git-dependent:
it activates only when assets/references/eval-baseline.md and .git both
exist, and its tests explicitly build a temporary git repository fixture.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets" / "scripts" / "audit.py"


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        shutil.copy(ASSET, self.root / "scripts" / "audit.py")

    def tearDown(self):
        self.tmp.cleanup()

    def run_audit(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / "audit.py"), *args],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"})

    def write_common(self):
        (self.root / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "STRUCTURE.md").write_text("# Index\n", encoding="utf-8")

    def test_dead_links_discovers_root_and_scripts_readmes_and_all_plans(self):
        self.write_common()
        (self.root / "README.md").write_text("[bad](missing-root.md)\n", encoding="utf-8")
        (self.root / "scripts" / "README-tools.md").write_text("[bad](missing-script.md)\n", encoding="utf-8")
        for folder in ("active", "completed"):
            target = self.root / "docs" / "plans" / folder
            target.mkdir(parents=True)
            (target / "p.md").write_text(
                "---\nstatus: in_progress\n---\n[bad](missing-plan.md)\n", encoding="utf-8")
        result = self.run_audit("dead-links", "--json")
        self.assertEqual(result.returncode, 1)
        sources = {item["source"] for item in json.loads(result.stdout)}
        self.assertIn("README.md", sources)
        self.assertIn("scripts/README-tools.md", sources)
        self.assertIn("docs/plans/active/p.md", sources)
        self.assertIn("docs/plans/completed/p.md", sources)

    def test_plan_directory_and_canonical_legacy_statuses(self):
        self.write_common()
        active = self.root / "docs" / "plans" / "active"
        completed = self.root / "docs" / "plans" / "completed"
        active.mkdir(parents=True)
        completed.mkdir()
        (active / "ok.md").write_text("---\nstatus: in_progress\n---\n", encoding="utf-8")
        (active / "legacy-bad.md").write_text("> 状态：已完成\n", encoding="utf-8")
        (completed / "ok.md").write_text("---\nstatus: done\n---\n", encoding="utf-8")
        (completed / "legacy.md").write_text("---\nstatus: completed\n---\n", encoding="utf-8")
        (completed / "bad.md").write_text("---\nstatus: in_progress\n---\n", encoding="utf-8")
        result = self.run_audit("plans", "--json")
        self.assertEqual(result.returncode, 1)
        rows = json.loads(result.stdout)
        bad = {Path(row["file"]).name: row["status"] for row in rows if row["status"] != "ok"}
        self.assertEqual(bad["legacy-bad.md"], "stale")
        self.assertEqual(bad["bad.md"], "misplaced")
        self.assertNotIn("legacy.md", bad)

    def test_birth_record_location_is_bound_to_size(self):
        self.write_common()
        small = self.root / "docs" / "initialization.md"
        small.write_text("---\nsize: small\nrepository_mode: no-git\n---\n", encoding="utf-8")
        result = self.run_audit("check", "--json")
        rows = json.loads(result.stdout)
        self.assertTrue(any(row["kind"] == "birth_record" and row["status"] == "found" for row in rows))

        small.unlink()
        completed = self.root / "docs" / "plans" / "completed"
        completed.mkdir(parents=True)
        (completed / "initialization.md").write_text(
            "---\nstatus: done\nsize: small\nrepository_mode: no-git\n---\n", encoding="utf-8")
        result = self.run_audit("check", "--json")
        rows = json.loads(result.stdout)
        self.assertTrue(any(row["kind"] == "birth_record" and row["status"] == "invalid" for row in rows))

    def test_medium_birth_record_requires_completed_location(self):
        self.write_common()
        completed = self.root / "docs" / "plans" / "completed"
        completed.mkdir(parents=True)
        (completed / "initialization.md").write_text(
            "---\nstatus: done\nsize: medium\nrepository_mode: git\n---\n", encoding="utf-8")
        rows = json.loads(self.run_audit("check", "--json").stdout)
        self.assertTrue(any(row["kind"] == "birth_record" and row["status"] == "found" for row in rows))


class BugfixEvalRecordTest(AuditTest):
    """R1：status: fixed 的 bugfix 档案必须携带 eval 记录（Git-free）。"""

    def write_bugfix(self, name: str, frontmatter: str) -> None:
        bugfix_dir = self.root / "docs" / "problems" / "bugfix"
        bugfix_dir.mkdir(parents=True, exist_ok=True)
        (bugfix_dir / name).write_text(
            f"---\n{frontmatter}\n---\n\n# t\n", encoding="utf-8")

    def eval_rows(self):
        stdout = self.run_audit("check", "--json").stdout
        return [r for r in json.loads(stdout) if r["kind"] == "eval_record"]

    def test_fixed_without_eval_record_is_error(self):
        self.write_bugfix("b1.md", "status: fixed\ncreated_at: 2026-10-28")
        rows = self.eval_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "error")
        self.assertEqual(rows[0]["file"], "docs/problems/bugfix/b1.md")

    def test_skipped_with_reason_passes(self):
        self.write_bugfix(
            "b1.md",
            "status: fixed\ncreated_at: 2026-10-28\n"
            "eval: skipped\neval_skip_reason: hardware-only failure, not replayable")
        self.assertEqual(self.eval_rows()[0]["status"], "ok")

    def test_skipped_without_reason_is_error(self):
        self.write_bugfix("b1.md", "status: fixed\ncreated_at: 2026-10-28\neval: skipped")
        self.assertEqual(self.eval_rows()[0]["status"], "error")

    def test_scored_passes(self):
        self.write_bugfix(
            "b1.md",
            "status: fixed\ncreated_at: 2026-10-28\neval: scored\n"
            "eval_fixture: bed\neval_command: cmd\neval_expect: ok\n"
            "eval_last_scored: 2026-10-28")
        self.assertEqual(self.eval_rows()[0]["status"], "ok")

    def test_created_at_placeholder_is_exempt_with_warn(self):
        self.write_bugfix("b1.md", "status: fixed\ncreated_at: [YYYY-MM-DD]")
        rows = self.eval_rows()
        self.assertEqual([r["status"] for r in rows], ["warn"])

    def test_created_at_missing_is_exempt_with_warn(self):
        self.write_bugfix("b1.md", "status: fixed")
        rows = self.eval_rows()
        self.assertEqual([r["status"] for r in rows], ["warn"])

    def test_grandfathered_doc_is_fully_exempt(self):
        self.write_bugfix("b1.md", "status: fixed\ncreated_at: 2026-01-01")
        self.assertEqual(self.eval_rows(), [])

    def test_template_and_non_fixed_docs_are_ignored(self):
        self.write_bugfix("_template.md", "status: fixed\ncreated_at: 2026-10-28")
        self.write_bugfix("open.md", "status: investigating\ncreated_at: 2026-10-28")
        self.assertEqual(self.eval_rows(), [])


class EvalBaselineTest(AuditTest):
    """R2：回归表 anchor 之后的行为面改动必须记分（临时 git 仓库 fixture）。"""

    SHA1 = "a" * 40
    SHA2 = "b" * 40

    def git(self, *args: str) -> None:
        proc = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def write_baseline(self, shas=(SHA1,)) -> None:
        refs = self.root / "assets" / "references"
        refs.mkdir(parents=True, exist_ok=True)
        rows = "\n".join(f"| `{s}` | 2026-10-27 | | | | | | | | |" for s in shas)
        (refs / "eval-baseline.md").write_text(
            "# eval\n\n| 版本 / commit |\n|---|\n" + rows + "\n", encoding="utf-8")

    def bootstrap(self) -> None:
        """Initial commit touching the table rows — anchor = init commit."""
        self.write_common()
        (self.root / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
        self.write_baseline()
        self.git("init")
        self.git("add", "-A")
        self.git("commit", "-m", "init")

    def commit_behavior(self, count: int) -> None:
        """每次提交都触碰行为面文件（SKILL.md）。"""
        skill = self.root / "SKILL.md"
        for i in range(count):
            skill.write_text(f"# Skill v{i + 2}\n", encoding="utf-8")
            self.git("add", "-A")
            self.git("commit", "-m", f"behavior {i + 1}")

    def eval_rows(self):
        stdout = self.run_audit("check", "--json").stdout
        return [r for r in json.loads(stdout) if r["kind"] == "eval_baseline"]

    def test_gate_skips_without_ledger_or_git(self):
        # 有账本、无 .git → skip
        self.write_common()
        self.write_baseline()
        rows = self.eval_rows()
        self.assertEqual(rows[0]["status"], "skip")
        # 有 .git、无账本 → skip
        self.git("init")
        (self.root / "assets" / "references" / "eval-baseline.md").unlink()
        rows = self.eval_rows()
        self.assertEqual(rows[0]["status"], "skip")

    def test_empty_table_skips_even_with_pending_commits(self):
        self.write_common()
        refs = self.root / "assets" / "references"
        refs.mkdir(parents=True)
        (refs / "eval-baseline.md").write_text(
            "# eval\n\n| 版本 / commit |\n|---|\n| 当前 main | | | | | | | | | |\n",
            encoding="utf-8")
        self.git("init")
        self.git("add", "-A")
        self.git("commit", "-m", "init")
        self.commit_behavior(2)
        rows = self.eval_rows()
        self.assertEqual(rows[0]["status"], "skip")

    def test_one_pending_commit_warns(self):
        self.bootstrap()
        self.commit_behavior(1)
        rows = self.eval_rows()
        self.assertEqual(rows[0]["status"], "warn")
        self.assertEqual(rows[0]["pending"], 1)

    def test_two_pending_commits_error(self):
        self.bootstrap()
        self.commit_behavior(2)
        rows = self.eval_rows()
        self.assertEqual(rows[0]["status"], "error")
        self.assertEqual(rows[0]["pending"], 2)

    def test_score_row_resets_anchor(self):
        self.bootstrap()
        self.commit_behavior(2)  # 未记分 → error
        refs = self.root / "assets" / "references" / "eval-baseline.md"
        refs.write_text(
            refs.read_text(encoding="utf-8")
            + f"| `{self.SHA2}` | 2026-10-28 | L1 partial: scope=readme | | | | | | 补记 | |\n",
            encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-m", "score")  # 只触碰表行 → 新 anchor
        rows = self.eval_rows()
        self.assertEqual(rows[0]["status"], "ok")

    def test_prose_edit_does_not_reset_anchor(self):
        self.bootstrap()
        self.commit_behavior(1)
        ledger = self.root / "assets" / "references" / "eval-baseline.md"
        ledger.write_text(
            ledger.read_text(encoding="utf-8") + "护栏：纯散文修订，不是表行。\n",
            encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-m", "prose only")  # 不触碰表行 → anchor 不动
        rows = self.eval_rows()
        self.assertEqual(rows[0]["status"], "warn")
        self.assertEqual(rows[0]["pending"], 1)

    def test_history_without_table_row_commits_skips_with_rebuild_hint(self):
        # 现状文件有 SHA 行，但当前历史中没有任何提交触碰过表行——
        # anchor 每次运行时从 git log 重算，历史被改写（rebase/amend）后
        # 「anchor 不在当前历史」即呈现为此形态 → skip + 提示重建基线。
        self.write_common()
        (self.root / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
        self.write_baseline()
        self.git("init")
        self.git("add", "AGENTS.md")
        self.git("add", "docs")
        self.git("add", "SKILL.md")
        self.git("add", "scripts")
        self.git("commit", "-m", "init without ledger")
        # 行为面提交只触碰 SKILL.md，账本保持未跟踪（不在任何历史提交中）
        (self.root / "SKILL.md").write_text("# Skill v2\n", encoding="utf-8")
        self.git("add", "SKILL.md")
        self.git("commit", "-m", "behavior")
        rows = self.eval_rows()
        self.assertEqual(rows[0]["status"], "skip")
        self.assertIn("rebuild", rows[0]["detail"])


class CheckCommandContractTest(unittest.TestCase):
    """_cmd_check 退出码（warn 放行 / error 退 1）与 _format_text 分支可见性。"""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("audit_under_test", ASSET)
        cls.audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.audit)

    def exit_code_of(self, rows):
        original = self.audit._run_all
        self.audit._run_all = lambda: rows
        try:
            try:
                self.audit._cmd_check(argparse.Namespace(json=True, verbose=False))
                return 0
            except SystemExit as exc:
                return exc.code
        finally:
            self.audit._run_all = original

    def test_check_tolerates_warn_and_skip_but_fails_on_error(self):
        self.assertEqual(self.exit_code_of([
            {"kind": "eval_baseline", "status": "warn", "detail": "x"},
            {"kind": "eval_baseline", "status": "skip", "detail": "y"},
            {"kind": "line_budget", "status": "warn", "lines": 1, "words": 1},
        ]), 0)
        self.assertEqual(self.exit_code_of([
            {"kind": "eval_record", "status": "error", "file": "f.md", "detail": "x"},
        ]), 1)

    def test_format_text_renders_new_kinds(self):
        out = self.audit._format_text([
            {"kind": "eval_record", "status": "error", "file": "docs/problems/bugfix/x.md",
             "detail": "missing eval record"},
            {"kind": "eval_record", "status": "warn", "file": "docs/problems/bugfix/y.md",
             "detail": "fill created_at"},
            {"kind": "eval_baseline", "status": "warn", "detail": "1 unscored commit"},
            {"kind": "eval_baseline", "status": "skip", "detail": "gate closed"},
        ])
        self.assertIn("missing eval record", out)
        self.assertIn("fill created_at", out)
        self.assertIn("1 unscored commit", out)
        self.assertIn("gate closed", out)


if __name__ == "__main__":
    unittest.main()

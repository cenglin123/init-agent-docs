"""Worktree task CLI tests against throwaway Git repositories.

Covers the 8 remaining subcommands (create/check/integrate/cleanup/list,
claim-main/release-main/main-claim) and the mechanical refusal of the removed
handshake subcommands.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.test_worktree_task_asset import (
    RepoFixture, SCRIPT, commit_file, git, wtask,
)


class CoordinationTests(RepoFixture):
    def named(self, name="Alpha Site", owner="agent-a"):
        payload, rc = wtask.create(self.repo, self.wt_root, name=name, owner=owner)
        self.assertEqual(rc, 0, payload)
        return payload

    def test_create_name_owner_derives_branch_and_directory(self):
        task = self.named()
        self.assertEqual(task["branch"], f"task/{task['id']}-alpha-site")
        self.assertEqual(task["path"].replace("\\", "/").rsplit("/", 1)[-1],
                         f"wt-{task['id']}-alpha-site")
        self.assertEqual(task["owner"], "agent-a")
        other = self.named(name="Alpha Site", owner="agent-b")
        self.assertNotEqual(task["id"], other["id"])
        self.assertNotEqual(task["branch"], other["branch"])
        self.assertNotEqual(task["path"], other["path"])

    def test_list_reports_linked_tasks_and_claim_state(self):
        a = self.named()
        b, rc = wtask.create(self.repo, self.wt_root)
        self.assertEqual(rc, 0, b)
        payload, rc = wtask.list_tasks(self.repo)
        self.assertEqual(rc, 0, payload)
        self.assertFalse(payload["main_claim"]["claimed"])
        branches = {item["branch"] for item in payload["tasks"]}
        self.assertEqual(branches, {a["branch"], b["branch"]})
        self.assertNotIn(str(self.repo), {item["path"] for item in payload["tasks"]})
        for item in payload["tasks"]:
            self.assertTrue(item["clean"])

    def test_list_handles_space_path_and_filters_non_task_branches(self):
        space_root = self.root / "wt root with space"
        space_root.mkdir()
        task, rc = wtask.create(self.repo, space_root, name="Space Task",
                                owner="agent-a")
        self.assertEqual(rc, 0, task)
        self.assertIn(" ", task["path"])
        other = self.root / "other-worktree"
        git(self.repo, "worktree", "add", "-b", "feature/not-a-task",
            str(other), self.base)
        payload, rc = wtask.list_tasks(self.repo)
        self.assertEqual(rc, 0, payload)
        branches = {item["branch"] for item in payload["tasks"]}
        self.assertIn(task["branch"], branches)
        self.assertNotIn("feature/not-a-task", branches)
        recorded = next(item for item in payload["tasks"]
                        if item["branch"] == task["branch"])
        self.assertEqual(wtask._norm(recorded["path"]), wtask._norm(task["path"]))
        self.assertTrue(recorded["path"].endswith("wt-" + task["id"] + "-space-task"))

    def test_check_reports_main_claim(self):
        task = self.named()
        wtask.claim_main(self.repo, "primary", ttl_minutes=30)
        payload, rc = wtask.check(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        self.assertTrue(payload["main_claim"]["claimed"])
        self.assertEqual(payload["main_claim"]["owner"], "primary")
        wtask.release_main(self.repo, "primary")

    def test_cli_resolves_relative_wt_root_against_cwd(self):
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "create", "--repo", str(self.repo),
             "--wt-root", "relative-root", "--name", "Relative Task",
             "--owner", "agent-rel"],
            capture_output=True, text=True, encoding="utf-8", cwd=str(self.root),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        task = json.loads(proc.stdout)
        expected_root = (self.root / "relative-root").resolve()
        self.assertEqual(Path(task["path"]).parent, expected_root)
        self.assertTrue(Path(task["path"]).is_absolute())
        self.assertTrue(Path(task["path"]).is_dir())

    def test_claim_release_and_status(self):
        claimed, rc = wtask.claim_main(self.repo, "primary", ttl_minutes=30)
        self.assertEqual(rc, 0, claimed)
        self.assertTrue(claimed["owner"] == "primary")
        self.assertEqual(wtask.main_claim_status(self.repo)["owner"], "primary")
        refused, rc = wtask.claim_main(self.repo, "fork-agent", ttl_minutes=30)
        self.assertEqual(rc, 1, refused)
        self.assertEqual(refused["result"], "refused")
        self.assertEqual(refused["holder"], "primary")
        self.assertEqual(wtask.release_main(self.repo, "fork-agent")[1], 1)
        self.assertEqual(wtask.main_claim_status(self.repo)["owner"], "primary")
        released, rc = wtask.release_main(self.repo, "primary")
        self.assertEqual(rc, 0, released)
        self.assertFalse(wtask.main_claim_status(self.repo)["claimed"])

    def test_integrate_refused_by_foreign_main_claim(self):
        task = self.named()
        commit_file(task["path"], "work.md", "w\n", "task commit")
        wtask.claim_main(self.repo, "primary", ttl_minutes=30)
        payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "refused")
        self.assertEqual(payload["holder"], "primary")
        self.assertNotEqual(
            git(self.repo, "rev-parse", "refs/heads/main").stdout_text,
            git(self.repo, "rev-parse", task["branch"]).stdout_text,
        )
        wtask.release_main(self.repo, "primary")
        self.assertEqual(wtask.integrate(self.repo, self.wt_root, task["id"])[1], 0)

    def test_cleanup_refuses_ignored_user_data(self):
        task = self.named()
        commit_file(task["path"], ".gitignore", "private.tmp\n", "ignore rule")
        self.assertEqual(wtask.integrate(self.repo, self.wt_root, task["id"])[1], 0)
        private = Path(task["path"]) / "private.tmp"
        private.write_text("fixture only", encoding="utf-8")
        try:
            result, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
            self.assertEqual(rc, 1, result)
            self.assertIn("ignored", result["detail"])
            self.assertTrue(private.exists())
        finally:
            private.unlink(missing_ok=True)

    def test_removed_handshake_subcommands_rejected(self):
        for action in ("register", "resume", "intent", "review", "coordinate",
                       "admit", "close"):
            with self.subTest(action=action):
                proc = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), action, "abcd",
                     "--repo", str(self.repo)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_public_cli_forward_flow(self):
        def cli(*args):
            proc = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                  capture_output=True, text=True, encoding="utf-8")
            return json.loads(proc.stdout), proc.returncode

        task, rc = cli("create", "--repo", str(self.repo), "--wt-root", str(self.wt_root),
                       "--name", "Forward Flow", "--owner", "agent-forward")
        self.assertEqual(rc, 0, task)
        listed, rc = cli("list", "--repo", str(self.repo))
        self.assertEqual(rc, 0, listed)
        self.assertIn(task["branch"], {item["branch"] for item in listed["tasks"]})
        checked, rc = cli("check", task["id"], "--repo", str(self.repo),
                          "--wt-root", str(self.wt_root))
        self.assertEqual(rc, 0, checked)
        self.assertEqual(checked["branch"], task["branch"])
        self.assertEqual(cli("claim-main", "--repo", str(self.repo),
                             "--owner", "agent-forward")[1], 0)
        self.assertEqual(cli("main-claim", "--repo", str(self.repo))[0]["owner"],
                         "agent-forward")
        self.assertEqual(cli("release-main", "--repo", str(self.repo),
                             "--owner", "agent-forward")[1], 0)
        commit_file(task["path"], "note.md", "changed\n", "task commit")
        self.assertEqual(cli("integrate", task["id"], "--repo", str(self.repo),
                             "--wt-root", str(self.wt_root))[1], 0)
        self.assertEqual(cli("cleanup", task["id"], "--repo", str(self.repo),
                             "--wt-root", str(self.wt_root))[1], 0)

    def test_help_is_console_encoding_safe(self):
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--help"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.isascii())
        for removed in ("register", "resume", "intent", "review", "coordinate",
                        "admit", "close"):
            self.assertNotIn(removed, proc.stdout)

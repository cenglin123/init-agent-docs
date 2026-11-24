"""Fixture-based tests for assets/scripts/worktree_task.py + reference-transaction.sh.

Uses throwaway git repos in temp dirs; never touches the skill repo itself.
Covers: create/check/integrate/cleanup identity & failure semantics, task
listing, the common-dir no-takeover lock, and the optional fast-forward hook.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "assets" / "scripts" / "worktree_task.py"
HOOK = REPO_ROOT / "assets" / "hooks" / "reference-transaction.sh"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

spec = importlib.util.spec_from_file_location("worktree_task_asset", SCRIPT)
wtask = importlib.util.module_from_spec(spec)
sys.modules["worktree_task_asset"] = wtask
spec.loader.exec_module(wtask)


def find_bash() -> str:
    if os.name == "nt":
        git_path = shutil.which("git")
        if git_path:
            # git.exe 可能位于 Git/cmd、Git/bin 或 Git/mingw64/bin，
            # 向上逐层找 bin/bash.exe 或 usr/bin/bash.exe
            for ancestor in Path(git_path).resolve().parents:
                for cand in (ancestor / "bin" / "bash.exe",
                             ancestor / "usr" / "bin" / "bash.exe"):
                    if cand.exists():
                        return str(cand)
    return "bash"


GIT_BASH = find_bash()

# hook 环境下继承的 GIT_* 变量会劫持 fixture 仓库定位
_ENV_BLOCKLIST = {
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX", "GIT_QUARANTINE_PATH",
}


def clean_env():
    return {k: v for k, v in os.environ.items() if k not in _ENV_BLOCKLIST}


def git(repo, *args, check=True, input_bytes=None):
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, input=input_bytes,
        env=clean_env(), creationflags=_NO_WINDOW,
    )
    r.stdout_text = r.stdout.decode("utf-8", errors="replace").strip()
    r.stderr_text = r.stderr.decode("utf-8", errors="replace").strip()
    if check and r.returncode != 0:
        raise AssertionError(f"git {args} failed: {r.stderr_text}")
    return r


def commit_file(repo, rel, content, message="commit"):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", rel)
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout_text


def init_repo(root: Path, branch="main"):
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", branch, str(root)],
        check=True, capture_output=True,
        env=clean_env(), creationflags=_NO_WINDOW,
    )
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "config", "commit.gpgsign", "false")
    return root


class RepoFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = init_repo(self.root / "repo")
        self.wt_root = self.root / "wt"
        self.wt_root.mkdir()
        self.base = commit_file(self.repo, "note.md", "base\n", "base commit")
        long_rel = "deep/" + "a" * 60 + "/" + "b" * 60 + "/" + "c" * 40 + ".md"
        self.long_rel = long_rel
        commit_file(self.repo, long_rel, "long path\n", "long path file")
        self.addCleanup(self._tmp.cleanup)

    def create_task(self):
        payload, rc = wtask.create(self.repo, self.wt_root)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["result"], "created")
        return payload

    def named_task(self, name="Alpha Site", owner="agent-a"):
        payload, rc = wtask.create(self.repo, self.wt_root, name=name, owner=owner)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["result"], "created")
        return payload

    def integrated_task(self):
        task = self.create_task()
        commit_file(Path(task["path"]), f"w-{task['id']}.md", "x\n", "task commit")
        payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        return task


class CreateTests(RepoFixture):
    def test_unique_identity_full_checkout_and_isolation(self):
        a = self.create_task()
        b = self.create_task()
        self.assertNotEqual(a["id"], b["id"])
        self.assertNotEqual(a["branch"], b["branch"])
        self.assertNotEqual(a["path"], b["path"])
        self.assertEqual(a["branch"], "task/" + a["id"])
        self.assertEqual(Path(a["path"]).name, "wt-" + a["id"])
        self.assertEqual(a["canonical"], "refs/heads/main")
        self.assertTrue((Path(a["path"]) / self.long_rel).exists())
        (Path(a["path"]) / "note.md").write_text("edit in A\n", encoding="utf-8")
        self.assertEqual(
            (Path(b["path"]) / "note.md").read_text(encoding="utf-8"), "base\n"
        )

    def test_concurrent_create_unique(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda _: wtask.create(self.repo, self.wt_root), range(2)
            ))
        payloads = [p for p, rc in results if rc == 0]
        if len(payloads) < 2:
            payloads.append(self.create_task())
        ids = {p["id"] for p in payloads}
        self.assertEqual(len(ids), len(payloads))

    def test_refuses_off_canonical_branch(self):
        git(self.repo, "checkout", "-b", "side")
        payload, rc = wtask.create(self.repo, self.wt_root)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "not-canonical")

    def test_custom_canonical_ref_via_config(self):
        git(self.repo, "config", "worktree-task.canonicalRef", "refs/heads/side")
        git(self.repo, "checkout", "-b", "side")
        payload, rc = wtask.create(self.repo, self.wt_root)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["canonical"], "refs/heads/side")

    def test_named_create_derives_slugged_branch_and_directory(self):
        task = self.named_task()
        self.assertEqual(task["branch"], f"task/{task['id']}-alpha-site")
        self.assertEqual(Path(task["path"]).name, f"wt-{task['id']}-alpha-site")
        self.assertEqual(task["owner"], "agent-a")
        self.assertEqual(task["name"], "Alpha Site")
        self.assertTrue((Path(task["path"]) / "note.md").exists())
        self.assertEqual(
            git(self.repo, "symbolic-ref", "HEAD").stdout_text, "refs/heads/main"
        )

    def test_named_create_requires_owner_with_name(self):
        payload, rc = wtask.create(self.repo, self.wt_root, name="Only Name")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "refused")


class CheckTests(RepoFixture):
    def test_ahead_behind_and_integrated(self):
        task = self.create_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        payload, rc = wtask.check(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["ahead"], 1)
        self.assertEqual(payload["behind"], 0)
        self.assertFalse(payload["integrated"])
        self.assertFalse(payload["is_ancestor"])
        self.assertTrue(payload["clean"])
        self.assertEqual(payload["main_claim"], {"claimed": False})
        self.assertIsNone(payload["reg_error"])

    def test_named_task_resolves_from_short_id(self):
        task = self.named_task()
        payload, rc = wtask.check(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["branch"], task["branch"])
        self.assertTrue(payload["registered"])

    def test_unknown_id(self):
        payload, rc = wtask.check(self.repo, self.wt_root, "nope")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "not-found")

    def test_read_only_creates_no_state(self):
        task = self.create_task()
        state = self.repo / ".git" / "worktree-task"
        before = {p.name for p in state.iterdir()} if state.exists() else set()
        first, rc = wtask.check(self.repo, self.wt_root, task["id"])
        second, rc2 = wtask.check(self.repo, self.wt_root, task["id"])
        self.assertEqual((rc, rc2), (0, 0))
        self.assertEqual(first, second)
        after = {p.name for p in state.iterdir()} if state.exists() else set()
        self.assertEqual(before, after)
        self.assertFalse((state / "mutation.lock").exists())
        self.assertFalse((state / "tasks").exists())
        self.assertFalse((state / "main-claim.json").exists())


class ListTests(RepoFixture):
    def test_lists_linked_tasks_and_claim_state(self):
        plain = self.create_task()
        named = self.named_task()
        payload, rc = wtask.list_tasks(self.repo)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["main_claim"], {"claimed": False})
        by_branch = {item["branch"]: item for item in payload["tasks"]}
        self.assertEqual(set(by_branch), {plain["branch"], named["branch"]})
        self.assertEqual(by_branch[plain["branch"]]["id"], plain["id"])
        self.assertEqual(by_branch[named["branch"]]["id"],
                         named["branch"][len("task/"):])
        self.assertTrue(by_branch[named["branch"]]["clean"])

    def test_claim_status_and_cleanup_disappear_from_list(self):
        task = self.integrated_task()
        wtask.claim_main(self.repo, "agent-a", ttl_minutes=30)
        self.assertEqual(wtask.list_tasks(self.repo)[0]["main_claim"]["owner"], "agent-a")
        wtask.release_main(self.repo, "agent-a")
        self.assertEqual(wtask.cleanup(self.repo, self.wt_root, task["id"])[1], 0)
        self.assertEqual(wtask.list_tasks(self.repo)[0]["tasks"], [])


class IntegrateTests(RepoFixture):
    def test_fast_forward(self):
        task = self.create_task()
        tip = commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["result"], "integrated")
        self.assertEqual(payload["canonical_tip"], tip)
        self.assertEqual(
            git(self.repo, "rev-parse", "refs/heads/main").stdout_text, tip
        )

    def test_merge_uses_exact_sha_and_reports_actual_tip(self):
        task = self.create_task()
        tip = commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        calls = []
        original = wtask._git

        def spy(repo, *args):
            calls.append(args)
            return original(repo, *args)

        with patch.object(wtask, "_git", spy):
            payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        self.assertIn(("merge", "--ff-only", tip), calls)
        self.assertEqual(payload["canonical_tip"], tip)
        self.assertEqual(
            git(self.repo, "rev-parse", "refs/heads/main").stdout_text, tip
        )

    def test_retry_after_response_loss(self):
        task = self.integrated_task()
        payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0)
        self.assertEqual(payload["result"], "already-integrated")

    def test_needs_rebase_preserves_task(self):
        task = self.create_task()
        tip = commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        moved = commit_file(self.repo, "other.md", "m\n", "main moved")
        payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "needs-rebase")
        self.assertEqual(
            git(self.repo, "rev-parse", "refs/heads/main").stdout_text, moved
        )
        self.assertEqual(
            git(self.repo, "rev-parse", task["branch"]).stdout_text, tip
        )
        self.assertTrue(Path(task["path"]).exists())

    def test_head_drift_aborts(self):
        task = self.create_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        drifted = {}

        def inject():
            drifted["oid"] = commit_file(self.repo, "d.md", "d\n", "drift")

        payload, rc = wtask.integrate(
            self.repo, self.wt_root, task["id"], _before_merge=inject
        )
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "head-drift")
        self.assertEqual(
            git(self.repo, "rev-parse", "refs/heads/main").stdout_text,
            drifted["oid"],
        )

    def test_lock_busy(self):
        task = self.create_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        d = wtask._lock_dir(self.repo)
        d.mkdir()
        (d / "pid").write_text(str(os.getpid()), encoding="utf-8")
        (d / "ts").write_text(str(time.time()), encoding="utf-8")
        (d / "owner").write_text("other", encoding="utf-8")
        try:
            payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
            self.assertEqual(rc, 1)
            self.assertEqual(payload["result"], "lock-busy")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_foreign_main_claim_refused(self):
        task = self.create_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        wtask.claim_main(self.repo, "primary", ttl_minutes=30)
        payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "refused")
        self.assertEqual(payload["holder"], "primary")

    def test_dirty_task_refused(self):
        task = self.create_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        (Path(task["path"]) / "work.md").write_text("dirty\n", encoding="utf-8")
        payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "not-clean")


class CleanupTests(RepoFixture):
    def test_cleanup_and_repeat(self):
        task = self.integrated_task()
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["result"], "cleaned")
        self.assertFalse(Path(task["path"]).exists())
        self.assertIsNone(wtask._rev_parse(self.repo, "refs/heads/" + task["branch"]))
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0)
        self.assertEqual(payload["result"], "already-cleaned")

    def test_named_task_cleanup_removes_branch(self):
        task = self.named_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        self.assertEqual(wtask.integrate(self.repo, self.wt_root, task["id"])[1], 0)
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["result"], "cleaned")
        self.assertIsNone(wtask._rev_parse(self.repo, "refs/heads/" + task["branch"]))

    def test_refuses_dirty_and_not_integrated(self):
        task = self.integrated_task()
        (Path(task["path"]) / "note.md").write_text("dirty\n", encoding="utf-8")
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "refused")
        task2 = self.create_task()
        commit_file(Path(task2["path"]), "work.md", "w\n", "task commit")
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task2["id"])
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "refused")

    def test_partial_state_fails_closed(self):
        task = self.integrated_task()
        git(self.repo, "worktree", "remove", "--force", task["path"])
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "partial-state")

    def test_cleanup_lock_busy(self):
        task = self.integrated_task()
        d = wtask._lock_dir(self.repo)
        d.mkdir()
        (d / "owner").write_text("other", encoding="utf-8")
        try:
            payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
            self.assertEqual(rc, 1)
            self.assertEqual(payload["result"], "lock-busy")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_orphan_directory_reports_partial_state(self):
        task = self.integrated_task()
        git(self.repo, "worktree", "remove", "--force", task["path"])
        git(self.repo, "branch", "-D", task["branch"])
        Path(task["path"]).mkdir(parents=True)
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "partial-state")
        self.assertTrue(Path(task["path"]).exists())

    def test_slugged_orphan_directory_reports_partial_state(self):
        task = self.named_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        self.assertEqual(wtask.integrate(self.repo, self.wt_root, task["id"])[1], 0)
        git(self.repo, "worktree", "remove", "--force", task["path"])
        git(self.repo, "branch", "-D", task["branch"])
        Path(task["path"]).mkdir(parents=True)
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "partial-state")
        self.assertTrue(Path(task["path"]).exists())


class PathBoundaryTests(RepoFixture):
    def test_wrong_wt_root_integrate_refused_and_preserved(self):
        task = self.named_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        tip = git(self.repo, "rev-parse", "refs/heads/main").stdout_text
        wrong = self.root / "wrong-root"
        wrong.mkdir()
        payload, rc = wtask.integrate(self.repo, wrong, task["id"])
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "partial-state")
        self.assertTrue(Path(task["path"]).exists())
        self.assertIsNotNone(
            wtask._rev_parse(self.repo, "refs/heads/" + task["branch"]))
        self.assertEqual(
            git(self.repo, "rev-parse", "refs/heads/main").stdout_text, tip)

    def test_wrong_wt_root_cleanup_refused_and_preserved(self):
        task = self.named_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        self.assertEqual(wtask.integrate(self.repo, self.wt_root, task["id"])[1], 0)
        wrong = self.root / "wrong-root"
        wrong.mkdir()
        payload, rc = wtask.cleanup(self.repo, wrong, task["id"])
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "partial-state")
        self.assertTrue(Path(task["path"]).exists())
        self.assertIsNotNone(
            wtask._rev_parse(self.repo, "refs/heads/" + task["branch"]))

    def test_foreign_manual_worktree_refused(self):
        outside = self.root / "outside-task"
        git(self.repo, "worktree", "add", "-b", "task/manual01",
            str(outside), self.base)
        commit_file(outside, "w.md", "w\n", "manual commit")
        payload, rc = wtask.integrate(self.repo, self.wt_root, "manual01")
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "partial-state")
        payload, rc = wtask.cleanup(self.repo, self.wt_root, "manual01")
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "partial-state")
        self.assertTrue(outside.exists())
        self.assertIsNotNone(
            wtask._rev_parse(self.repo, "refs/heads/task/manual01"))

    def test_symlinked_worktree_path_refused(self):
        task = self.named_task()
        outside = self.root / "link-target"
        outside.mkdir()
        shutil.rmtree(task["path"])
        try:
            os.symlink(str(outside), task["path"], target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "partial-state")
        self.assertTrue(os.path.islink(task["path"]))
        self.assertIsNotNone(
            wtask._rev_parse(self.repo, "refs/heads/" + task["branch"]))

    def test_worktree_branch_drift_refused(self):
        task = self.named_task()
        git(task["path"], "checkout", "-b", "feature/drift")
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "partial-state")
        self.assertTrue(Path(task["path"]).exists())
        self.assertIsNotNone(
            wtask._rev_parse(self.repo, "refs/heads/" + task["branch"]))

    def test_foreign_common_dir_refused(self):
        task = self.named_task()
        original = wtask._git_dir_pair

        def fake(repo):
            if wtask._norm(repo) == wtask._norm(task["path"]):
                return ("C:/elsewhere/.git", "C:/elsewhere/.git")
            return original(repo)

        with patch.object(wtask, "_git_dir_pair", fake):
            payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["result"], "partial-state")
        self.assertIn("common directory", payload["detail"])
        self.assertTrue(Path(task["path"]).exists())
        self.assertIsNotNone(
            wtask._rev_parse(self.repo, "refs/heads/" + task["branch"]))


class LockMatrixTests(RepoFixture):
    def _make_lock(self, owner="x"):
        d = wtask._lock_dir(self.repo)
        d.parent.mkdir(exist_ok=True)
        d.mkdir(exist_ok=True)
        (d / "owner").write_text(owner, encoding="utf-8")
        return d

    def tearDown(self):
        shutil.rmtree(wtask._lock_dir(self.repo), ignore_errors=True)

    def test_existing_lock_is_busy_without_timeout_takeover(self):
        d = self._make_lock()
        self.assertFalse(wtask.lock_acquire(self.repo))
        self.assertTrue((d / "owner").exists())

    def test_incomplete_metadata_not_stealable(self):
        d = wtask._lock_dir(self.repo)
        d.parent.mkdir(exist_ok=True)
        d.mkdir(exist_ok=True)
        self.assertFalse(wtask.lock_acquire(self.repo))
        self.assertTrue(d.exists())

    def test_dual_contender_atomic_acquire(self):
        wtask._lock_dir(self.repo).parent.mkdir(exist_ok=True)
        barrier = threading.Barrier(2)
        results = {}

        def contender(name):
            barrier.wait()
            results[name] = wtask.lock_acquire(self.repo)
            if results[name]:
                time.sleep(0.1)
                wtask.lock_release(self.repo)

        threads = [threading.Thread(target=contender, args=(n,)) for n in "ab"]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results.values()), [False, True])
        self.assertFalse(wtask._lock_dir(self.repo).exists())

    def test_release_only_own(self):
        d = self._make_lock(owner="other-token")
        wtask._LOCK_TOKENS.values = {wtask._norm(d): "my-token"}
        wtask.lock_release(self.repo)
        self.assertTrue(d.exists())
        wtask._LOCK_TOKENS.values = {}

    def test_tokens_for_two_repositories_do_not_overlap(self):
        other = init_repo(self.root / 'other')
        self.assertTrue(wtask.lock_acquire(self.repo))
        self.assertTrue(wtask.lock_acquire(other))
        wtask.lock_release(self.repo)
        self.assertFalse(wtask._lock_dir(self.repo).exists())
        self.assertTrue(wtask._lock_dir(other).exists())
        wtask.lock_release(other)
        self.assertFalse(wtask._lock_dir(other).exists())


class SeparateGitDirTests(RepoFixture):
    def test_canonical_identification_gitfile_layout(self):
        gd = self.root / "separate.git"
        wt = self.root / "separate-wt"
        subprocess.run(
            ["git", "init", "-b", "main", f"--separate-git-dir={gd}", str(wt)],
            check=True, capture_output=True,
            env=clean_env(), creationflags=_NO_WINDOW,
        )
        git(wt, "config", "user.email", "test@example.com")
        git(wt, "config", "user.name", "Test")
        commit_file(wt, "a.md", "a\n", "init")
        self.assertIsNone(wtask.canonical_error(wt))
        git(wt, "worktree", "add", str(self.root / "linked"), "-b", "task/x")
        self.assertIsNotNone(wtask.canonical_error(self.root / "linked"))


class GovernanceHookPatternTests(unittest.TestCase):
    """Bash hooks match governance paths without spawning `grep` per file."""

    HOOKS = (
        REPO_ROOT / ".githooks" / "pre-commit",
        REPO_ROOT / "assets" / "hooks" / "pre-commit-python.sh",
        REPO_ROOT / "assets" / "hooks" / "pre-commit-node.sh",
        REPO_ROOT / "assets" / "hooks" / "pre-commit-go.sh",
        REPO_ROOT / "assets" / "hooks" / "pre-commit-generic.sh",
    )
    PATHS = (
        "AGENTS.md",
        "agents.md",
        "AGENTSxmd",
        "SKILL.md",
        "README.md",
        "docs/STRUCTURE.md",
        "scripts/audit.py",
        "assets/scripts/audit.py",
        "assets/scripts/my file.py",
        "assets/scripts/a\\nb.py",
        '"assets/scripts/a\\nb.py"',
        "assets/templates/zh/AGENTS.md.tpl",
        ".githooks/pre-commit",
        "Xgithooks/pre-commit",
        "assets/hooks/pre-commit-python.sh",
        ".agents/memory/MEMORY.md",
        "docs/audit-checklist.md",
        "unrelated.txt",
        "",
    )

    def setUp(self):
        if not Path(GIT_BASH).exists() and shutil.which(GIT_BASH) is None:
            self.skipTest("bash unavailable")

    def pattern_of(self, text):
        match = re.search(r'GOV_PATTERNS="([^"]+)"', text)
        self.assertIsNotNone(match, "GOV_PATTERNS not found")
        return match.group(1)

    def bash_differential(self, pattern, *, start_nocasematch: int):
        paths_literal = " ".join(shlex.quote(path) for path in self.PATHS)
        script = (
            "set -e\n"
            f"PATHS=( {paths_literal} )\n"
            f"start_nocase={1 if start_nocasematch else 0}\n"
            f"pattern={shlex.quote(pattern)}\n"
            'if [ "$start_nocase" -eq 1 ]; then shopt -s nocasematch; else shopt -u nocasematch; fi\n'
            "_HAD_NOCASEMATCH=0\n"
            "if shopt -q nocasematch; then _HAD_NOCASEMATCH=1; fi\n"
            "shopt -u nocasematch\n"
            'for p in "${PATHS[@]}"; do\n'
            "    old=0\n"
            '    if echo "$p" | grep -qE "$pattern"; then old=1; fi\n'
            "    new=0\n"
            '    if [[ "$p" =~ $pattern ]]; then new=1; fi\n'
            "    printf '%s%s\\n' \"$old\" \"$new\"\n"
            "done\n"
            'if [ "$_HAD_NOCASEMATCH" -eq 1 ]; then shopt -s nocasematch; fi\n'
            'if [ "$_HAD_NOCASEMATCH" -eq 1 ]; then\n'
            "    shopt -q nocasematch || exit 8\n"
            "else\n"
            "    ! shopt -q nocasematch || exit 9\n"
            "fi\n"
        )
        proc = subprocess.run(
            [GIT_BASH, "-c", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=clean_env(), creationflags=_NO_WINDOW,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.splitlines()

    def test_hooks_use_bash_regex_and_parse_cleanly(self):
        for hook in self.HOOKS:
            with self.subTest(hook=hook.name):
                text = hook.read_text(encoding="utf-8")
                self.assertIn('[[ "$path" =~ $GOV_PATTERNS ]]', text)
                self.assertIn("shopt -u nocasematch", text)
                self.assertIn('if [ "$_HAD_NOCASEMATCH" -eq 1 ]; then shopt -s nocasematch; fi', text)
                self.assertNotIn('echo "$path" | grep', text)
                parsed = subprocess.run(
                    [GIT_BASH, "-n", str(hook)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    env=clean_env(), creationflags=_NO_WINDOW,
                )
                self.assertEqual(parsed.returncode, 0, parsed.stderr)

    def test_matching_results_match_legacy_grep_pipeline(self):
        for hook in self.HOOKS:
            with self.subTest(hook=hook.name):
                pattern = self.pattern_of(hook.read_text(encoding="utf-8"))
                for start_nocase in (0, 1):
                    pairs = self.bash_differential(
                        pattern, start_nocasematch=start_nocase
                    )
                    self.assertEqual(
                        [line[0] for line in pairs],
                        [line[1] for line in pairs],
                        f"grep/new mismatch under nocasematch={start_nocase}",
                    )
                    expected = [
                        "1" if re.search(pattern, path) else "0"
                        for path in self.PATHS
                    ]
                    self.assertEqual([line[1] for line in pairs], expected)


class HookFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = init_repo(self.root / "repo")
        self.base = commit_file(self.repo, "a.md", "a\n", "c1")
        self.hooks = self.root / "hooks"
        self.hooks.mkdir()
        shutil.copy(HOOK, self.hooks / "reference-transaction")
        git(self.repo, "config", "core.hooksPath", str(self.hooks))
        self.addCleanup(self._tmp.cleanup)

    def main_oid(self):
        return git(self.repo, "rev-parse", "refs/heads/main").stdout_text

    def run_hook(self, phase, stdin_text):
        hook_path = str(self.hooks / "reference-transaction").replace("\\", "/")
        r = subprocess.run(
            [GIT_BASH, hook_path, phase],
            input=stdin_text.encode("utf-8"), capture_output=True,
            cwd=str(self.repo), env=clean_env(), creationflags=_NO_WINDOW,
        )
        r.stderr_text = r.stderr.decode("utf-8", errors="replace").strip()
        return r


class HookAcceptTests(HookFixture):
    def test_ordinary_commit_accepted(self):
        oid = commit_file(self.repo, "b.md", "b\n", "c2")
        self.assertEqual(self.main_oid(), oid)

    def test_ff_merge_accepted(self):
        git(self.repo, "checkout", "-b", "task/one")
        tip = commit_file(self.repo, "t.md", "t\n", "task c1")
        git(self.repo, "checkout", "main")
        git(self.repo, "merge", "--ff-only", "task/one")
        self.assertEqual(self.main_oid(), tip)

    def test_task_branch_amend_allowed(self):
        git(self.repo, "checkout", "-b", "task/free")
        commit_file(self.repo, "t.md", "t\n", "task c1")
        r = git(self.repo, "commit", "--amend", "-m", "amended", check=False)
        self.assertEqual(r.returncode, 0, r.stderr_text)


class HookRejectTests(HookFixture):
    def test_amend_rejected(self):
        c2 = commit_file(self.repo, "b.md", "b\n", "c2")
        r = git(self.repo, "commit", "--amend", "-m", "rewritten", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.main_oid(), c2)

    def test_deletion_rejected(self):
        tip = self.main_oid()
        r = git(self.repo, "update-ref", "-d", "refs/heads/main", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.main_oid(), tip)

    def test_non_ff_update_ref_rejected(self):
        commit_file(self.repo, "b.md", "b\n", "c2")
        tip = self.main_oid()
        r = git(self.repo, "update-ref", "refs/heads/main", self.base, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.main_oid(), tip)

    def test_direct_invocation(self):
        zero = "0" * 40
        c2 = commit_file(self.repo, "b.md", "b\n", "c2")
        r = self.run_hook("prepared", f"{c2} {zero} refs/heads/main\n")
        self.assertNotEqual(r.returncode, 0)
        r = self.run_hook("prepared", f"{c2} refs/heads/main\n")
        self.assertNotEqual(r.returncode, 0)
        r = self.run_hook("prepared", f"{self.base} {c2} refs/heads/main\n")
        self.assertEqual(r.returncode, 0, r.stderr_text)
        r = self.run_hook("prepared", f"{zero} {zero} refs/heads/task/x\n")
        self.assertEqual(r.returncode, 0, r.stderr_text)
        r = self.run_hook("committed", f"{zero} {zero} refs/heads/main\n")
        self.assertEqual(r.returncode, 0, r.stderr_text)


if __name__ == "__main__":
    unittest.main()

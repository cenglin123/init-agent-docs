"""Fixture-based tests for assets/scripts/worktree_task.py + reference-transaction.sh.

Uses throwaway git repos in temp dirs; never touches the skill repo itself.
Covers: create/check/integrate/cleanup identity & failure semantics, the
canonical-writer lock matrix, and the fast-forward gate hook.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


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
        self.assertTrue(a["branch"].startswith("task/"))
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


class CheckTests(RepoFixture):
    def test_ahead_behind_and_integrated(self):
        task = self.create_task()
        commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        payload, rc = wtask.check(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["ahead"], 1)
        self.assertEqual(payload["behind"], 0)
        self.assertFalse(payload["integrated"])

    def test_unknown_id(self):
        payload, rc = wtask.check(self.repo, self.wt_root, "nope")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["result"], "not-found")


class IntegrateTests(RepoFixture):
    def test_fast_forward(self):
        task = self.create_task()
        tip = commit_file(Path(task["path"]), "work.md", "w\n", "task commit")
        payload, rc = wtask.integrate(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["result"], "integrated")
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
        payload, rc = wtask.cleanup(self.repo, self.wt_root, task["id"])
        self.assertEqual(rc, 0)
        self.assertEqual(payload["result"], "already-cleaned")

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


class LockMatrixTests(RepoFixture):
    def _make_lock(self, pid, ts_offset=0, owner="x"):
        d = wtask._lock_dir(self.repo)
        d.mkdir(exist_ok=True)
        (d / "pid").write_text(str(pid), encoding="utf-8")
        (d / "ts").write_text(str(time.time() - ts_offset), encoding="utf-8")
        (d / "owner").write_text(owner, encoding="utf-8")
        return d

    def tearDown(self):
        shutil.rmtree(wtask._lock_dir(self.repo), ignore_errors=True)

    def test_live_owner_expired_ts_is_busy(self):
        d = self._make_lock(os.getpid(), ts_offset=wtask.LOCK_TTL + 100)
        self.assertFalse(wtask.lock_acquire(self.repo))
        self.assertTrue((d / "owner").exists())

    def test_incomplete_metadata_not_stealable(self):
        d = wtask._lock_dir(self.repo)
        d.mkdir(exist_ok=True)
        (d / "pid").write_text("99999999", encoding="utf-8")
        self.assertFalse(wtask.lock_acquire(self.repo))
        self.assertTrue(d.exists())

    def test_dead_expired_takeover(self):
        self._make_lock(99999999, ts_offset=wtask.LOCK_TTL + 100)
        self.assertTrue(wtask.lock_acquire(self.repo))
        wtask.lock_release(self.repo)
        self.assertFalse(wtask._lock_dir(self.repo).exists())

    def test_dual_contender_atomic_takeover(self):
        self._make_lock(99999999, ts_offset=wtask.LOCK_TTL + 100, owner="old")
        barrier = threading.Barrier(2)
        results = {}

        def contender(name):
            barrier.wait()
            results[name] = wtask.lock_acquire(self.repo)

        threads = [threading.Thread(target=contender, args=(n,)) for n in "ab"]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results.values()), [False, True])
        self.assertTrue((wtask._lock_dir(self.repo) / "owner").exists())

    def test_release_only_own(self):
        d = self._make_lock(os.getpid(), owner="other-token")
        wtask._LOCK_TOKEN = "my-token"
        wtask.lock_release(self.repo)
        self.assertTrue(d.exists())
        wtask._LOCK_TOKEN = None


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

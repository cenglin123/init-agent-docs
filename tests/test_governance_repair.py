"""Behavior regressions for bounded retrieval and the source maintenance gate."""
from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_GIT_LOCATION_VARS = {
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX", "GIT_QUARANTINE_PATH",
}


def run(root, *args):
    env = {key: value for key, value in os.environ.items()
           if key not in _GIT_LOCATION_VARS}
    return subprocess.run(args, cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=90,
                          env={**env, "PYTHONUTF8": "1"})


def install(root, rel, dest=None):
    target = root / (dest or rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / rel, target)


def write(root, rel, text):
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def python(root, script, *args):
    return run(root, sys.executable, "-X", "utf8", script, *args)


def test_bounded_search_finds_old_entries_and_refresh_preserves_manual_sections(tmp_path):
    install(tmp_path, "assets/scripts/maintain.py", "scripts/maintain.py")
    index = write(tmp_path, ".agents/memory/MEMORY.md",
                  "# Manual context\nkeep this\n<!-- memory-index:start -->\n<!-- memory-index:end -->\n# Rules\nkeep that\n")
    for i in range(140):
        write(tmp_path, f".agents/memory/project/entry-{i:03}.md", f"# topic {i}\nshared " + "x" * 1000)
    old = write(tmp_path, ".agents/memory/project/old.md", "# 古老经验\nrare-old SQLite 教训\n")
    os.utime(old, (946684800, 946684800))
    result = python(tmp_path, "scripts/maintain.py", "--memory-search", "shared")
    assert result.returncode == 0, result.stderr
    assert "命中 140 条；显示 5 条；截断：是" in result.stdout
    assert result.stdout.count("\n- [") == 5
    assert len(result.stdout) < 2000
    result = python(tmp_path, "scripts/maintain.py", "--memory-search", "rare-old", "--limit", "1")
    assert "古老经验" in result.stdout and "project/old.md" in result.stdout
    new = write(tmp_path, "docs/problems/bugfix/new.md", "# 新经验\nnew-lesson 验证\n")
    assert python(tmp_path, "scripts/maintain.py", "--memory-index").returncode == 0
    assert "keep this" in index.read_text(encoding="utf-8")
    assert "keep that" in index.read_text(encoding="utf-8")
    assert "new.md" in index.read_text(encoding="utf-8")
    assert "新经验" in python(tmp_path, "scripts/maintain.py", "--memory-search", "new-lesson").stdout
    new.rename(new.with_name("moved.md"))
    assert python(tmp_path, "scripts/maintain.py", "--memory-index").returncode == 0
    assert "moved.md" in index.read_text(encoding="utf-8")
    new.with_name("moved.md").unlink()
    assert python(tmp_path, "scripts/maintain.py", "--memory-index").returncode == 0
    assert "moved.md" not in index.read_text(encoding="utf-8")
    missing = python(tmp_path, "scripts/maintain.py", "--memory-search", "new-lesson")
    assert missing.returncode == 0 and "未找到相关经验" in missing.stdout
    assert python(tmp_path, "scripts/maintain.py", "--memory-search", "shared", "--limit", "0").returncode != 0


def test_drift_advisory_does_not_hide_real_errors(tmp_path):
    install(tmp_path, "assets/scripts/audit.py", "scripts/audit.py")
    install(tmp_path, "assets/scripts/maintain.py", "scripts/maintain.py")
    write(tmp_path, "AGENTS.md", "# App\n")
    write(tmp_path, "docs/initialization.md", "---\nsize: small\nstatus: in_progress\n---\n")
    write(tmp_path, "pyproject.toml", '[project]\nname = "app"\n')
    write(tmp_path, "docs/overview.md", "# Decisions\nPython standard library SQLite is used.\n")
    write(tmp_path, "docs/deployment.md", "# Deployment\nExternal Redis and PostgreSQL are managed outside this application.\n")
    for script, args in (("scripts/audit.py", ("drift",)),
                         ("scripts/audit.py", ("check",)),
                         ("scripts/maintain.py", ("--check",)),
                         ("scripts/maintain.py", ())):
        result = python(tmp_path, script, *args)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "WARN" in result.stdout
    write(tmp_path, "README.md", "[lost](missing.md)\n")
    assert python(tmp_path, "scripts/audit.py", "check").returncode == 1
    (tmp_path / "README.md").unlink()
    (tmp_path / "docs/overview.md").write_bytes(b"\xff")
    result = python(tmp_path, "scripts/audit.py", "drift")
    assert result.returncode == 1 and "overview.md" in result.stdout
    assert "Traceback" not in result.stderr


def test_search_excerpts_use_body_for_body_title_and_tag_matches(tmp_path):
    install(tmp_path, "assets/scripts/maintain.py", "scripts/maintain.py")
    write(tmp_path, ".agents/memory/project/entry.md",
          "---\ntitle: title-only\ntags: [tag-only]\nconfirmed_count: 37\n---\n"
          "# Experience\n" + "older context " * 40 + "body-needle repair evidence\n")
    body_hit = python(tmp_path, "scripts/maintain.py", "--memory-search", "body-needle")
    assert body_hit.returncode == 0
    assert "body-needle repair evidence" in body_hit.stdout
    assert "confirmed_count" not in body_hit.stdout
    for term in ("title-only", "tag-only", "confirmed_count"):
        result = python(tmp_path, "scripts/maintain.py", "--memory-search", term)
        assert result.returncode == 0 and "命中 1 条" in result.stdout
        excerpt = result.stdout.split(" — ", 1)[1]
        assert "Experience" in excerpt and "older context" in excerpt
        assert "confirmed_count" not in excerpt and "tags:" not in excerpt


def git(root, *args):
    result = run(root, "git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def source_fixture(root):
    install(root, "assets/scripts/audit.py")
    install(root, "scripts/check_source.py")
    install(root, ".githooks/pre-commit")
    write(root, "tests/test_smoke.py", "from pathlib import Path\ndef test_source_asset():\n    assert Path('assets/scripts/audit.py').is_file()\n")
    write(root, "SKILL.md", "# Entry\n")
    write(root, "assets/references/eval-baseline.md", "# Method\n\n| Version | Result |\n|---|---|\n| `" + "a" * 40 + "` | L1 |\n")
    git(root, "init")
    git(root, "add", ".")
    git(root, "commit", "-m", "baseline")
    for i in range(2):
        write(root, "SKILL.md", f"# Entry {i}\n")
        git(root, "add", "SKILL.md")
        git(root, "commit", "-m", f"behavior {i}")


def test_source_gate_legacy_migration_and_real_precommit(tmp_path):
    source_fixture(tmp_path)
    result = python(tmp_path, "scripts/check_source.py")
    assert result.returncode == 1 and '"pending": 2' in result.stdout
    # Method prose and non-score tables do not reset the legacy anchor.
    method = tmp_path / "assets/references/eval-baseline.md"
    method.write_text(method.read_text(encoding="utf-8") + "\n| profile | method wording |\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "method wording")
    assert python(tmp_path, "scripts/check_source.py").returncode == 1
    write(tmp_path, "README.md", "candidate\n")
    git(tmp_path, "add", "README.md")
    rejected = run(tmp_path, "git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=.githooks", "commit", "-m", "unscored")
    assert rejected.returncode != 0 and '"pending": 2' in rejected.stdout + rejected.stderr
    write(tmp_path, "evals/results.md", "# Results\n| Version | Result |\n|---|---|\n| `" + "b" * 40 + "` | L1 actual |\n")
    git(tmp_path, "add", "evals/results.md")
    git(tmp_path, "-c", "core.hooksPath=.githooks", "commit", "-m", "score candidate")  # real hook runs pytest + shared R2
    assert python(tmp_path, "scripts/check_source.py").returncode == 0
    # After migration, method edits do not conceal new behavior commits either.
    for i in range(2):
        write(tmp_path, "SKILL.md", f"# New {i}\n")
        git(tmp_path, "add", "SKILL.md")
        git(tmp_path, "commit", "-m", f"new behavior {i}")
    write(tmp_path, "assets/references/eval-baseline.md", "# Updated current method\n| Profile | Rules |\n|---|---|\n| Small | concise |\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "method only")
    result = python(tmp_path, "scripts/check_source.py")
    assert result.returncode == 1 and '"pending": 2' in result.stdout
    worktree = tmp_path / "linked"
    git(tmp_path, "worktree", "add", "--detach", str(worktree))
    assert (worktree / ".git").is_file()
    result = python(worktree, "scripts/check_source.py")
    assert result.returncode == 1 and '"pending": 2' in result.stdout


def test_header_only_results_uses_scored_legacy_until_results_are_scored(tmp_path):
    source_fixture(tmp_path)
    ledger = write(tmp_path, "evals/results.md", "# Results\n| Version | Result |\n|---|---|\n")
    git(tmp_path, "add", "evals/results.md")
    git(tmp_path, "commit", "-m", "prepare results header")
    result = python(tmp_path, "scripts/check_source.py")
    assert result.returncode == 1 and '"pending": 2' in result.stdout
    result = python(tmp_path, "scripts/check_source.py", "--staged")
    assert result.returncode == 1 and '"pending": 2' in result.stdout
    # An unstaged new score cannot cover a staged candidate.
    ledger.write_text(ledger.read_text(encoding="utf-8") + "| `" + "b" * 40 + "` | verified |\n", encoding="utf-8")
    result = python(tmp_path, "scripts/check_source.py", "--staged")
    assert result.returncode == 1 and '"pending": 2' in result.stdout
    git(tmp_path, "add", "evals/results.md")
    # The selected staged ledger still works when its working copy differs.
    ledger.write_text("# Unstaged header only\n", encoding="utf-8")
    result = python(tmp_path, "scripts/check_source.py", "--staged")
    assert result.returncode == 0 and "staged score row" in result.stdout
    git(tmp_path, "commit", "-m", "score migrated results")
    git(tmp_path, "restore", "evals/results.md")
    assert python(tmp_path, "scripts/check_source.py").returncode == 0


def test_invalid_results_utf8_cannot_fall_back_to_legacy(tmp_path):
    source_fixture(tmp_path)
    ledger = write(tmp_path, "evals/results.md", "")
    ledger.write_bytes(b"# Results\n\xff")
    for staged in (False, True):
        if staged:
            git(tmp_path, "add", "evals/results.md")
        result = python(tmp_path, "scripts/check_source.py", *(("--staged",) if staged else ()))
        assert result.returncode == 1 and "Traceback" not in result.stderr
        rows = json.loads(result.stdout)
        assert rows[0]["error_code"] == "read_error"
        assert rows[0]["path"] == "evals/results.md"


def test_target_check_ignores_same_named_source_ledger(tmp_path):
    install(tmp_path, "assets/scripts/audit.py", "scripts/audit.py")
    write(tmp_path, "AGENTS.md", "# Rules\n")
    write(tmp_path, "docs/initialization.md", "---\nsize: small\nstatus: in_progress\n---\n")
    ledger = write(tmp_path, "evals/results.md", "# App results\n| Version | Result |\n|---|---|\n| `" + "a" * 40 + "` | baseline |\n")
    git(tmp_path, "init")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "target baseline")
    for i in range(2):
        write(tmp_path, "README.md", f"# Target {i}\n")
        git(tmp_path, "add", "README.md")
        git(tmp_path, "commit", "-m", f"target behavior {i}")
    for invalid in (False, True):
        if invalid:
            ledger.write_bytes(b"\xff")
        result = python(tmp_path, "scripts/audit.py", "check", "--json")
        assert result.returncode == 0, result.stdout + result.stderr
        assert all(row["kind"] != "eval_baseline" for row in json.loads(result.stdout))


def test_historical_rows_preserved_in_order():
    if not (ROOT / ".git").exists():
        pytest.skip("source package has no local Git metadata for the historical comparison")
    top = run(ROOT, "git", "rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != ROOT.resolve():
        pytest.skip("historical comparison requires this source repository's own Git metadata")
    baseline = run(ROOT, "git", "show", "7a1e2a2230df890b4497d629cc607e0e4a11d38c:assets/references/eval-baseline.md")
    if baseline.returncode != 0:
        pytest.skip("historical baseline 7a1e2a2 is unavailable (for example, in a shallow clone)")
    start = baseline.stdout.index("| 版本 / commit（完整 40 位 SHA）")
    table = baseline.stdout[start:baseline.stdout.index("\n6. **迭代**", start)].rstrip()
    assert table in (ROOT / "evals/results.md").read_text(encoding="utf-8")
    assert "2026-11-03 |" not in (ROOT / "assets/references/eval-baseline.md").read_text(encoding="utf-8")

"""Git-free functional contracts for assets/scripts/audit.py."""
from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()

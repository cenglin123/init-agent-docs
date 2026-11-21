"""Contracts for the opt-in Python structure evidence layer.

Every integration test installs repo_graph.py / audit.py / maintain.py into a
temporary target project and runs the installed copies; assets/scripts/ is
never used as if it were the target project.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS = REPO_ROOT / "assets" / "scripts"
SCRIPTS = ("repo_graph.py", "audit.py", "maintain.py")


class RepoGraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        for name in SCRIPTS:
            shutil.copy(ASSETS / name, self.root / "scripts" / name)
        self.env = {
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def tearDown(self):
        self.tmp.cleanup()

    # -- helpers ---------------------------------------------------------

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def write_project(self) -> None:
        self.write("AGENTS.md", "# Rules\n")
        self.write(
            "docs/STRUCTURE.md",
            "# Index\n\n| Document | Description |\n|---|---|\n"
            "| [Initialization](initialization.md) | Birth record |\n",
        )
        self.write(
            "docs/initialization.md",
            "---\nsize: small\nstatus: in_progress\nrepository_mode: no-git\n---\n",
        )
        self.write("pkg/__init__.py", "")
        self.write(
            "pkg/core.py",
            "import os\n\n"
            "def helper():\n"
            "    return 1\n\n"
            "class Engine:\n"
            "    def start(self):\n"
            "        return self.stop()\n\n"
            "    def stop(self):\n"
            "        return 0\n",
        )
        self.write(
            "pkg/app.py",
            "from pkg.core import helper, Engine\n\n"
            "def main():\n"
            "    helper()\n"
            "    engine = Engine()\n"
            "    engine.start()\n"
            "    return os.getcwd()\n",
        )
        self.write(
            "tools_cli.py",
            "from pkg.app import main\n\n"
            "def entry():\n"
            "    main()\n",
        )

    def run_script(self, script: str, *args: str,
                   env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / script), *args],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env or self.env, timeout=120,
        )

    def repo(self, *args: str):
        return self.run_script("repo_graph.py", *args)

    def audit(self, *args: str):
        return self.run_script("audit.py", *args)

    def maintain(self, *args: str, env: dict[str, str] | None = None):
        return self.run_script("maintain.py", *args, env=env)

    def build(self):
        result = self.repo("build", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def graph(self):
        return json.loads((self.root / ".agents/repo-graph/graph.json").read_text(encoding="utf-8"))

    def manifest(self):
        return json.loads((self.root / ".agents/repo-graph/manifest.json").read_text(encoding="utf-8"))

    def snapshot(self):
        snap = {}
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                rel = path.relative_to(self.root).as_posix()
                snap[rel] = (
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    path.stat().st_mtime_ns,
                )
        return snap

    def audit_rows(self):
        result = self.audit("check", "--json")
        return result, json.loads(result.stdout)

    def graph_edges(self, kind=None, source=None):
        edges = self.graph()["edges"]
        return [
            edge for edge in edges
            if (kind is None or edge["kind"] == kind)
            and (source is None or edge["source"] == source)
        ]

    # -- opt-in / unchanged defaults ------------------------------------

    def test_uninitialized_project_keeps_audit_and_maintain_unchanged(self):
        self.write_project()
        before, rows = self.audit_rows()
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)
        self.assertFalse(any(row["kind"] == "repo_graph" for row in rows))

        maintain = self.maintain()
        self.assertEqual(maintain.returncode, 0, maintain.stdout + maintain.stderr)
        self.assertFalse((self.root / ".agents" / "repo-graph").exists())
        self.assertNotIn("repo graph", maintain.stdout)

        after, rows_after = self.audit_rows()
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
        self.assertEqual(rows, rows_after)

    def test_build_is_idempotent_and_has_no_time_identity(self):
        self.write_project()
        self.build()
        graph_path = self.root / ".agents/repo-graph/graph.json"
        manifest_path = self.root / ".agents/repo-graph/manifest.json"
        first = (graph_path.read_bytes(), manifest_path.read_bytes())
        self.build()
        second = (graph_path.read_bytes(), manifest_path.read_bytes())
        self.assertEqual(first, second)

        manifest = self.manifest()
        self.assertNotIn("generated_at", manifest)
        self.assertNotIn("created_at", manifest)
        self.assertEqual(manifest["schema"], "iad-repo-graph/1")
        self.assertEqual(manifest["generator_version"], "1")
        self.assertEqual(len(manifest["graph_digest"]), 64)
        self.assertEqual(len(manifest["inputs_digest"]), 64)
        self.assertTrue(manifest["inputs"])
        for item in manifest["inputs"]:
            self.assertEqual(len(item["sha256"]), 64)
        self.assertEqual(
            manifest["inputs"],
            sorted(manifest["inputs"], key=lambda item: item["path"]),
        )

    # -- read-only checks and audit -------------------------------------

    def test_check_is_strictly_read_only(self):
        self.write_project()
        self.build()
        before = self.snapshot()
        for _ in range(2):
            result = self.repo("check", "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "ok")
        self.assertEqual(before, self.snapshot())

    def test_audit_is_read_only_and_reports_enabled_graph(self):
        self.write_project()
        self.build()
        before = self.snapshot()
        result, rows = self.audit_rows()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        graph_rows = [row for row in rows if row["kind"] == "repo_graph"]
        self.assertEqual(len(graph_rows), 1)
        self.assertEqual(graph_rows[0]["status"], "ok")
        self.assertEqual(before, self.snapshot())

    # -- evidence model ---------------------------------------------------

    def test_imports_calls_and_unknown_relations_are_graded(self):
        self.write_project()
        self.build()
        graph = self.graph()
        self.assertIn("pkg/app.py", graph["scope"]["files"])
        self.assertIn("__pycache__", graph["scope"]["excluded_dirs"])
        self.assertTrue(any("not a runtime call graph" in note for note in graph["notes"]))
        self.assertTrue(any("Built-in skipped directories" in note for note in graph["notes"]))
        self.assertTrue(any("project-root .py modules as local" in note for note in graph["notes"]))
        self.assertEqual(graph["notes"], self.manifest()["notes"])

        symbols = {symbol["id"]: symbol for symbol in graph["symbols"]}
        self.assertEqual(symbols["pkg/core.py::helper"]["kind"], "function")
        self.assertEqual(symbols["pkg/core.py::Engine"]["kind"], "class")
        self.assertEqual(symbols["pkg/core.py::Engine"]["public_methods"], ["start", "stop"])

        imports = self.graph_edges("import", "pkg/app.py")
        import_targets = {(edge["target"], edge["evidence"]) for edge in imports}
        self.assertIn(("pkg/core.py", "direct"), import_targets)
        external = self.graph_edges("import", "pkg/core.py")
        self.assertTrue(any(edge["names"] == ["os"] and edge["evidence"] == "external"
                            for edge in external))

        calls = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/app.py")
        }
        helper = calls[("main", "helper")]
        self.assertEqual(helper["target"], "pkg/core.py::helper")
        self.assertEqual(helper["evidence"], "direct")
        engine = calls[("main", "Engine")]
        self.assertEqual(engine["target"], "pkg/core.py::Engine")
        self.assertEqual(engine["evidence"], "direct")
        unknown = calls[("main", "engine.start")]
        self.assertIsNone(unknown["target"])
        self.assertEqual(unknown["evidence"], "unknown")

        core_calls = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/core.py")
        }
        inferred = core_calls[("Engine.start", "self.stop")]
        self.assertEqual(inferred["target"], "pkg/core.py::Engine.stop")
        self.assertEqual(inferred["evidence"], "inferred")

    def test_repeated_import_and_top_level_rebinding_stay_unknown(self):
        self.write_project()
        self.write(
            "pkg/rebind.py",
            "from pkg.core import helper as repeated\n"
            "from pkg.core import Engine as repeated\n"
            "from pkg.core import helper as overwritten\n"
            "overwritten = None\n"
            "import pkg.core\n"
            "pkg = None\n\n"
            "try:\n"
            "    from pkg.core import helper as excepted\n"
            "except ImportError:\n"
            "    excepted = None\n\n"
            "from pkg.core import helper as matched\n"
            "match 1:\n"
            "    case int() as matched:\n"
            "        pass\n\n"
            "def use():\n"
            "    repeated()\n"
            "    overwritten()\n"
            "    return pkg.core.helper()\n\n"
            "def use_except():\n"
            "    excepted()\n\n"
            "def use_match():\n"
            "    matched()\n",
        )
        self.build()

        calls = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/rebind.py")
        }
        expected_unknown = (
            ("use", "repeated"),
            ("use", "overwritten"),
            ("use", "pkg.core.helper"),
            ("use_except", "excepted"),
            ("use_match", "matched"),
        )
        for scope, expression in expected_unknown:
            with self.subTest(expression=expression):
                self.assertIsNone(calls[(scope, expression)]["target"])
                self.assertEqual(calls[(scope, expression)]["evidence"], "unknown")
        # The untouched direct examples still resolve.
        app_calls = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/app.py")
        }
        self.assertEqual(app_calls[("main", "helper")]["target"], "pkg/core.py::helper")

    def test_attribute_root_requires_direct_module_alias_evidence(self):
        self.write_project()
        self.write(
            "pkg/config.py",
            "def load():\n"
            "    return 1\n\n"
            "settings = object()\n",
        )
        self.write(
            "pkg/settings_user.py",
            "from pkg.config import settings\n\n"
            "def use():\n"
            "    return settings.load()\n",
        )
        self.build()

        calls = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/settings_user.py")
        }
        imported_symbol = calls[("use", "settings.load")]
        self.assertIsNone(imported_symbol["target"])
        self.assertEqual(imported_symbol["evidence"], "unknown")

        # A real module alias remains a direct module-chain call.
        relative = self.write(
            "pkg/module_user.py",
            "import pkg.core\n\n"
            "def use():\n"
            "    return pkg.core.helper()\n",
        )
        self.assertTrue(relative.is_file())
        self.build()
        direct = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/module_user.py")
        }
        self.assertEqual(direct[("use", "pkg.core.helper")]["target"], "pkg/core.py::helper")
        self.assertEqual(direct[("use", "pkg.core.helper")]["evidence"], "direct")

    def test_call_edges_cover_decorators_defaults_annotations_and_class_heads(self):
        self.write_project()
        self.write(
            "pkg/calls.py",
            "from pkg.core import helper\n\n"
            "def deco(fn):\n"
            "    return fn\n\n"
            "def make_base():\n"
            "    return object\n\n"
            "@deco()\n"
            "def decorated():\n"
            "    return helper()\n\n"
            "@deco()\n"
            "class Decorated(make_base()):\n"
            "    def method(self):\n"
            "        return helper()\n\n"
            "def annotated(value: helper() = helper()) -> helper():\n"
            "    return value\n\n"
            "def outer():\n"
            "    def inner():\n"
            "        return helper()\n"
            "    return inner()\n\n"
            "lambda_default = lambda value=helper(): value\n",
        )
        self.build()
        calls = self.graph_edges("call", "pkg/calls.py")

        decorators = [edge for edge in calls
                      if edge["expression"] == "deco" and edge["scope"] is None]
        self.assertEqual(len(decorators), 2)
        self.assertTrue(all(edge["target"] == "pkg/calls.py::deco" for edge in decorators))

        bases = [edge for edge in calls
                 if edge["expression"] == "make_base" and edge["scope"] is None]
        self.assertEqual(len(bases), 1)
        self.assertEqual(bases[0]["target"], "pkg/calls.py::make_base")

        outer_helper = [edge for edge in calls
                        if edge["expression"] == "helper" and edge["scope"] is None]
        self.assertEqual(len(outer_helper), 4)  # default + 3 annotations/defaults
        self.assertTrue(all(edge["target"] == "pkg/core.py::helper" for edge in outer_helper))

        nested = [edge for edge in calls
                  if edge["expression"] == "helper" and edge["scope"] == "outer.inner"]
        self.assertEqual(len(nested), 1)
        self.assertEqual(nested[0]["target"], "pkg/core.py::helper")

        shown = json.loads(
            self.repo("show", "--path", "pkg/calls.py::outer", "--json").stdout
        )
        expressions = {edge["expression"] for edge in shown["relations"]["calls"]}
        self.assertIn("inner", expressions)
        self.assertIn("helper", expressions)  # nested def is contained consistently

    def test_package_attribute_wins_over_same_named_submodule(self):
        self.write_project()
        self.write("pkg/__init__.py", "def mod():\n    return 1\n")
        self.write("pkg/mod.py", "def mod():\n    return 2\n")
        self.write(
            "pkg/user.py",
            "from pkg import mod\n\n"
            "def use():\n"
            "    return mod()\n",
        )
        self.write("pkg2/__init__.py", "")
        self.write("pkg2/mod.py", "def mod():\n    return 3\n")
        self.write(
            "pkg2/user.py",
            "from pkg2 import mod\n\n"
            "def use():\n"
            "    return mod.mod()\n",
        )
        self.build()

        conflict_imports = self.graph_edges("import", "pkg/user.py")
        self.assertEqual([edge["target"] for edge in conflict_imports], ["pkg/__init__.py"])
        conflict_calls = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/user.py")
        }
        self.assertEqual(conflict_calls[("use", "mod")]["target"], "pkg/__init__.py::mod")
        self.assertEqual(conflict_calls[("use", "mod")]["evidence"], "direct")

        fallback_imports = self.graph_edges("import", "pkg2/user.py")
        self.assertEqual([edge["target"] for edge in fallback_imports], ["pkg2/mod.py"])
        fallback_calls = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg2/user.py")
        }
        self.assertEqual(fallback_calls[("use", "mod.mod")]["target"], "pkg2/mod.py::mod")

    def test_nested_class_self_inference_stays_unknown(self):
        self.write_project()
        self.write(
            "pkg/nested.py",
            "class Outer:\n"
            "    def helper(self):\n"
            "        return 1\n\n"
            "    class Inner:\n"
            "        def run(self):\n"
            "            return self.helper()\n",
        )
        self.build()
        calls = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/nested.py")
        }
        nested = calls[("Outer.Inner.run", "self.helper")]
        self.assertIsNone(nested["target"])
        self.assertEqual(nested["evidence"], "unknown")

        # The top-level class positive case remains inferred.
        engine = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/core.py")
        }
        self.assertEqual(engine[("Engine.start", "self.stop")]["target"], "pkg/core.py::Engine.stop")
        self.assertEqual(engine[("Engine.start", "self.stop")]["evidence"], "inferred")

    def test_relative_and_module_attribute_imports_resolve_directly(self):
        self.write_project()
        self.write("pkg/sub/__init__.py", "")
        self.write(
            "pkg/sub/use.py",
            "from ..core import helper\n"
            "import pkg.core\n\n"
            "def use():\n"
            "    helper()\n"
            "    return pkg.core.helper()\n",
        )
        self.build()

        imports = self.graph_edges("import", "pkg/sub/use.py")
        self.assertTrue(imports)
        self.assertTrue(all(edge["target"] == "pkg/core.py" for edge in imports))
        self.assertTrue(all(edge["evidence"] == "direct" for edge in imports))

        calls = {
            (edge["scope"], edge["expression"]): edge
            for edge in self.graph_edges("call", "pkg/sub/use.py")
        }
        self.assertEqual(calls[("use", "helper")]["target"], "pkg/core.py::helper")
        self.assertEqual(calls[("use", "pkg.core.helper")]["target"], "pkg/core.py::helper")
        self.assertEqual(calls[("use", "pkg.core.helper")]["evidence"], "direct")

    # -- staleness / corruption -----------------------------------------

    def test_stale_and_corrupt_are_reported_without_auto_rebuild(self):
        self.write_project()
        self.build()
        graph_path = self.root / ".agents/repo-graph/graph.json"
        built_bytes = graph_path.read_bytes()

        self.write("pkg/core.py", (self.root / "pkg/core.py").read_text(encoding="utf-8") + "# changed\n")
        check = self.repo("check", "--json")
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        stale = json.loads(check.stdout)
        self.assertEqual(stale["status"], "stale")
        self.assertIn("python scripts/repo_graph.py build", stale["repair"])

        audit, rows = self.audit_rows()
        self.assertEqual(audit.returncode, 0, audit.stdout + audit.stderr)
        graph_rows = [row for row in rows if row["kind"] == "repo_graph"]
        self.assertEqual([row["status"] for row in graph_rows], ["warn"])
        self.assertIn("repo_graph.py build", graph_rows[0]["detail"])
        self.assertEqual(graph_path.read_bytes(), built_bytes)  # audit did not rebuild

        graph_path.write_text("{broken", encoding="utf-8")
        corrupt = self.repo("check", "--json")
        self.assertEqual(corrupt.returncode, 1)
        self.assertEqual(json.loads(corrupt.stdout)["status"], "invalid")
        audit, rows = self.audit_rows()
        self.assertEqual(audit.returncode, 1, audit.stdout + audit.stderr)
        graph_rows = [row for row in rows if row["kind"] == "repo_graph"]
        self.assertEqual([row["status"] for row in graph_rows], ["invalid"])
        self.assertIn("repo_graph.py build", graph_rows[0]["detail"])

        # Unreadable manifest bytes are also structured invalidity, not a crash.
        (self.root / ".agents/repo-graph/manifest.json").write_bytes(b"\xff")
        unreadable = self.repo("check", "--json")
        self.assertEqual(unreadable.returncode, 1)
        self.assertEqual(json.loads(unreadable.stdout)["status"], "invalid")
        self.assertNotIn("Traceback", unreadable.stdout + unreadable.stderr)

    # -- bounded queries --------------------------------------------------

    def test_show_and_impacted_are_bounded_and_one_hop_only(self):
        self.write_project()
        self.write(
            "pkg/unresolved.py",
            "import pkg.core\n\n"
            "def use():\n"
            "    return pkg.core.not_defined()\n",
        )
        for index in range(60):
            self.write(
                f"fan/m{index:02d}.py",
                "from pkg.core import helper\n\n"
                "def use():\n"
                "    return helper()\n",
            )
        self.build()

        shown = self.repo("show", "--path", "pkg/core.py", "--limit", "5", "--json")
        self.assertEqual(shown.returncode, 0, shown.stdout + shown.stderr)
        payload = json.loads(shown.stdout)
        self.assertEqual(payload["object"]["id"], "pkg/core.py")
        self.assertEqual(len(payload["relations"]["called_by"]), 5)
        self.assertTrue(payload["truncated"])
        self.assertGreater(payload["omitted"]["called_by"], 0)

        show_text = self.repo("show", "--path", "pkg/core.py", "--limit", "5")
        self.assertEqual(show_text.returncode, 0, show_text.stdout + show_text.stderr)
        self.assertIn("truncated", show_text.stdout)
        self.assertIn("omitted", show_text.stdout)

        app = json.loads(self.repo("show", "--path", "pkg/app.py", "--limit", "5", "--json").stdout)
        self.assertEqual(app["object"]["id"], "pkg/app.py")
        # Direct relations only: tools_cli calls app; entry is not reached.
        self.assertFalse(any(edge.get("scope") == "entry" for edge in app["relations"]["calls"]))
        self.assertEqual({edge["source"] for edge in app["relations"]["called_by"]}, {"tools_cli.py"})

        impacted = self.repo("impacted", "--paths", "pkg/core.py", "--limit", "100", "--json")
        self.assertEqual(impacted.returncode, 0, impacted.stdout + impacted.stderr)
        impact = json.loads(impacted.stdout)
        self.assertFalse(impact["transitive"])
        self.assertFalse(impact["truncated"])
        self.assertEqual(impact["omitted"], 0)
        impacted_ids = {row["id"] for row in impact["impacted"]}
        self.assertNotIn("tools_cli.py", impacted_ids)  # transitive caller must not appear
        self.assertTrue(any(row["id"] == "pkg/app.py" for row in impact["impacted"]))

        bounded = json.loads(
            self.repo("impacted", "--paths", "pkg/core.py", "--limit", "10", "--json").stdout
        )
        self.assertEqual(len(bounded["impacted"]), 10)
        self.assertTrue(bounded["truncated"])
        self.assertEqual(bounded["omitted"], len(impact["impacted"]) - 10)

        impact_text = self.repo("impacted", "--paths", "pkg/core.py", "--limit", "5")
        self.assertEqual(impact_text.returncode, 0, impact_text.stdout + impact_text.stderr)
        self.assertIn("truncated", impact_text.stdout)
        self.assertIn("omitted", impact_text.stdout)

        symbol_impact = json.loads(
            self.repo("impacted", "--paths", "pkg/core.py::helper", "--json").stdout
        )
        self.assertTrue(symbol_impact["impacted"])
        self.assertTrue(all(
            reason.startswith("calls:")
            for row in symbol_impact["impacted"]
            for reason in row["reasons"]
        ))
        self.assertTrue(all(row["evidence"] for row in symbol_impact["impacted"]))
        self.assertNotIn(
            "pkg/unresolved.py",
            {row["id"] for row in symbol_impact["impacted"]},
            "unknown call targets must not be counted as direct impact",
        )

    # -- no Git + change cycle -------------------------------------------

    def test_no_git_fixture_builds_checks_and_recovers_after_change(self):
        self.write_project()
        self.assertFalse((self.root / ".git").exists())
        self.build()
        self.assertEqual(json.loads(self.repo("check", "--json").stdout)["status"], "ok")
        self.assertEqual(self.repo("show", "--path", "pkg/app.py", "--json").returncode, 0)
        self.assertEqual(self.repo("impacted", "--paths", "pkg/core.py", "--json").returncode, 0)

        self.write("pkg/app.py", (self.root / "pkg/app.py").read_text(encoding="utf-8") + "\n\ndef extra():\n    return 1\n")
        self.assertEqual(json.loads(self.repo("check", "--json").stdout)["status"], "stale")
        self.build()
        self.assertEqual(json.loads(self.repo("check", "--json").stdout)["status"], "ok")
        self.assertIn("extra", self.graph()["modules"][
            next(i for i, module in enumerate(self.graph()["modules"])
                 if module["path"] == "pkg/app.py")
        ]["public_functions"])

    # -- exception paths --------------------------------------------------

    def test_exception_paths_are_structured_and_leave_old_graph_intact(self):
        self.write_project()
        self.build()
        graph_path = self.root / ".agents/repo-graph/graph.json"
        old_graph = graph_path.read_bytes()

        self.write("bad_syntax.py", "def broken(:\n    pass\n")
        failed = self.repo("build", "--json")
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        payload = json.loads(failed.stdout)
        self.assertEqual(payload["error"], "parse_error")
        self.assertEqual(payload["path"], "bad_syntax.py")
        self.assertNotIn("Traceback", failed.stdout + failed.stderr)
        self.assertEqual(graph_path.read_bytes(), old_graph)

        (self.root / "bad_syntax.py").unlink()
        self.write("bad_utf8.py", "\u00ff")
        (self.root / "bad_utf8.py").write_bytes(b"\xff")
        failed = self.repo("build", "--json")
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(json.loads(failed.stdout)["error"], "read_error")

        missing = self.repo("show", "--path", "pkg/missing.py", "--json")
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(json.loads(missing.stdout)["error"], "not_found")

        unknown = self.repo("impacted", "--paths", "pkg/missing.py", "--json")
        self.assertEqual(unknown.returncode, 0, unknown.stdout + unknown.stderr)
        self.assertEqual(json.loads(unknown.stdout)["unknown_inputs"], ["pkg/missing.py"])

        shutil.rmtree(self.root / ".agents")
        not_initialized = self.repo("check", "--json")
        self.assertEqual(not_initialized.returncode, 0)
        self.assertEqual(json.loads(not_initialized.stdout)["status"], "not_initialized")

    def test_maintain_only_refreshes_an_initialized_graph(self):
        self.write_project()
        self.assertEqual(self.maintain().returncode, 0)
        self.assertFalse((self.root / ".agents" / "repo-graph").exists())

        self.build()
        graph_path = self.root / ".agents/repo-graph/graph.json"
        before = graph_path.read_bytes()
        self.write("pkg/core.py", (self.root / "pkg/core.py").read_text(encoding="utf-8") + "# changed\n")

        check = self.maintain("--check")
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        self.assertIn("repo graph", check.stdout)
        self.assertIn("repo_graph.py build", check.stdout)
        self.assertEqual(graph_path.read_bytes(), before)  # --check never rebuilds

        full = self.maintain()
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        self.assertIn("repo graph", full.stdout)
        self.assertEqual(json.loads(self.repo("check", "--json").stdout)["status"], "ok")

    def test_full_maintain_recovers_corrupt_graph_without_check_writes(self):
        self.write_project()
        self.build()
        graph_path = self.root / ".agents/repo-graph/graph.json"
        graph_path.write_text("{broken", encoding="utf-8")
        before = self.snapshot()

        check = self.maintain("--check")
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        self.assertEqual(before, self.snapshot())  # --check stays read-only
        self.assertEqual(graph_path.read_text(encoding="utf-8"), "{broken")

        full = self.maintain()
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        self.assertIn("repo graph", full.stdout)
        self.assertEqual(json.loads(self.repo("check", "--json").stdout)["status"], "ok")
        self.assertNotEqual(graph_path.read_text(encoding="utf-8"), "{broken")

    def test_full_maintain_fails_build_error_without_overwriting_old_graph(self):
        self.write_project()
        self.build()
        graph_path = self.root / ".agents/repo-graph/graph.json"
        old_graph = graph_path.read_bytes()
        self.write("bad_syntax.py", "def broken(:\n    pass\n")

        full = self.maintain()
        self.assertEqual(full.returncode, 1, full.stdout + full.stderr)
        self.assertIn("parse_error", full.stdout + full.stderr)
        self.assertEqual(graph_path.read_bytes(), old_graph)
        self.assertEqual(json.loads(self.repo("check", "--json").stdout)["status"], "stale")

    def test_maintain_ignores_stderr_noise_when_stdout_json_succeeds(self):
        self.write_project()
        self.build()
        with tempfile.TemporaryDirectory() as noise_dir:
            noise = Path(noise_dir)
            (noise / "sitecustomize.py").write_text(
                "import sys\nprint('sitecustomize warning', file=sys.stderr)\n",
                encoding="utf-8",
            )
            env = dict(self.env)
            env["PYTHONPATH"] = str(noise) + os.pathsep + env.get("PYTHONPATH", "")

            check = self.maintain("--check", env=env)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn("repo graph", check.stdout)
            self.assertIn("fresh", check.stdout)
            self.assertNotIn("INVALID", check.stdout)

            self.write("pkg/core.py", (self.root / "pkg/core.py").read_text(encoding="utf-8") + "# changed\n")
            full = self.maintain(env=env)
            self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
            self.assertIn("repo graph rebuilt", full.stdout)
            self.assertNotIn("INVALID", full.stdout)
            self.assertEqual(json.loads(self.repo("check", "--json").stdout)["status"], "ok")


if __name__ == "__main__":
    unittest.main()

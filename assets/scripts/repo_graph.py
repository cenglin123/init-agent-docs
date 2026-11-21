"""repo_graph.py — deterministic Python structure evidence (opt-in, read-only checks).

Builds a static structure graph for local Python modules using only the
standard library ``ast``. The graph is evidence, not semantics:

- it records local modules, public top-level functions/classes, import edges
  and static call sites;
- each relation is graded ``direct`` (uniquely resolved from syntax),
  ``inferred`` (one explicit static inference, e.g. ``self.method`` inside the
  defining class), ``external`` (outside the local module set) or ``unknown``;
- it does not model runtime dispatch, types, side effects or business meaning,
  and it is not an AOCI Baseline or an F/R/A/S authoring input.

Artifacts live in ``.agents/repo-graph/`` and are only created by an explicit
``build``. ``check`` never writes. Identity fields contain no timestamps, so an
unchanged input set rebuilds byte-identical output.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "iad-repo-graph/1"
GENERATOR = "repo_graph.py"
GENERATOR_VERSION = "1"
GRAPH_DIR_REL = ".agents/repo-graph"
GRAPH_FILE = "graph.json"
MANIFEST_FILE = "manifest.json"
DEFAULT_LIMIT = 50
MAX_LIMIT = 500

# Supports <project_root>/scripts/ and <project_root>/.meta/scripts/.
SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = (
    SCRIPTS_DIR.parent.parent
    if SCRIPTS_DIR.parent.name in (".meta", "assets")
    else SCRIPTS_DIR.parent
)
SCRIPTS_REL = ".meta/scripts" if SCRIPTS_DIR.parent.name == ".meta" else "scripts"
GRAPH_DIR = ROOT / GRAPH_DIR_REL
GRAPH_PATH = GRAPH_DIR / GRAPH_FILE
MANIFEST_PATH = GRAPH_DIR / MANIFEST_FILE
REPAIR = f"python {SCRIPTS_REL}/repo_graph.py build"

_EXCLUDED_DIRS = {
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "site-packages",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
}
_UNKNOWN_NOTE = "Relations that syntax cannot prove are reported as evidence=unknown; no guessing."
_SCOPE_NOTE = "Python AST evidence only; not a runtime call graph, type model or business-semantic index."
_LOCAL_PRECEDENCE_NOTE = (
    "Static module resolution treats project-root .py modules as local and prefers them; "
    "same-name standard-library or third-party packages are not disambiguated."
)
_EXCLUDED_NOTE = (
    "Built-in skipped directories: "
    + ", ".join(sorted(_EXCLUDED_DIRS))
    + "; every dot-prefixed directory is skipped."
)
_MATCH_BINDING_TYPES = tuple(
    node_type for node_type in (
        getattr(ast, "MatchAs", None),
        getattr(ast, "MatchStar", None),
    ) if node_type is not None
)
_MATCH_MAPPING_TYPE = getattr(ast, "MatchMapping", None)


class RepoGraphError(Exception):
    """Expected, reportable failure with a stable error code and project path."""

    def __init__(self, code: str, path: str, detail: str):
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{path}: {detail}")


# ---------------------------------------------------------------------------
# deterministic IO
# ---------------------------------------------------------------------------

def _serialize(value: Any) -> bytes:
    """Canonical UTF-8 JSON: sorted keys, two-space indent, LF, trailing LF."""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    return text.encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RepoGraphError("read_error", _rel(path), f"cannot read file ({exc})") from exc


def _read_json(path: Path) -> Any:
    data = _read_bytes(path)
    try:
        return json.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise RepoGraphError("read_error", _rel(path), f"not UTF-8 ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise RepoGraphError("invalid_json", _rel(path), f"invalid JSON at line {exc.lineno}") from exc


# ---------------------------------------------------------------------------
# input discovery
# ---------------------------------------------------------------------------

def _keep_dir(name: str) -> bool:
    return not name.startswith(".") and name not in _EXCLUDED_DIRS


def _iter_py_files() -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if _keep_dir(name))
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            found.append(path.relative_to(ROOT).as_posix())
    return sorted(found)


def _scan_inputs() -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []
    for rel in _iter_py_files():
        data = _read_bytes(ROOT / rel)
        inputs.append({"path": rel, "sha256": _sha256(data), "bytes": len(data)})
    return inputs


def _digest_inputs(inputs: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(inputs, key=lambda row: row["path"]):
        digest.update(item["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(item["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# module / symbol extraction
# ---------------------------------------------------------------------------

def _module_name(path: str) -> str:
    stem = path[:-3] if path.endswith(".py") else path
    parts = stem.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_package(path: str) -> bool:
    return path == "__init__.py" or path.endswith("/__init__.py")


def _package_of(module: str, is_package: bool) -> str:
    if is_package:
        return module
    return module.rsplit(".", 1)[0] if "." in module else ""


def _top_level_defs(tree: ast.Module) -> tuple[list[str], list[str], dict[str, list[str]]]:
    functions: list[str] = []
    classes: list[str] = []
    class_methods: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
            class_methods[node.name] = sorted(
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return functions, classes, class_methods


def _public(names: list[str]) -> list[str]:
    return sorted(name for name in names if not name.startswith("_"))


def _ambiguous_top_level_names(tree: ast.Module) -> set[str]:
    """Names bound more than once at module scope.

    A later import or top-level assignment can invalidate an earlier import
    binding. Without dataflow, a repeated binding is not proven unique, so
    call sites through that name (including attribute roots) stay unknown.
    Nested function/class/lambda scopes bind their own names and are not
    module-level events; comprehension targets and assignment expressions are
    counted conservatively because assignment expressions can bind the
    enclosing module scope.
    """
    counts: dict[str, int] = {}

    def add(name: str) -> None:
        counts[name] = counts.get(name, 0) + 1

    def walk(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            add(node.name)
            return
        if isinstance(node, ast.Lambda):
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.asname or alias.name.split(".")[0])
            return
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    add(alias.asname or alias.name)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            add(node.id)
        if isinstance(node, ast.ExceptHandler) and node.name:
            add(node.name)
        if _MATCH_BINDING_TYPES and isinstance(node, _MATCH_BINDING_TYPES) and node.name:
            add(node.name)
        if _MATCH_MAPPING_TYPE is not None and isinstance(node, _MATCH_MAPPING_TYPE) and node.rest:
            add(node.rest)
        for child in ast.iter_child_nodes(node):
            walk(child)

    for statement in tree.body:
        walk(statement)
    return {name for name, count in counts.items() if count > 1}


def _function_locals(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> set[str]:
    """Names that shadow outer bindings inside one lexical function/lambda."""
    names = {arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
    if node.args.vararg:
        names.add(node.args.vararg.arg)
    if node.args.kwarg:
        names.add(node.args.kwarg.arg)

    def walk(current: ast.AST, top: bool = False) -> None:
        if not top and isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(current, ast.Name) and isinstance(current.ctx, ast.Store):
            names.add(current.id)
        elif isinstance(current, (ast.Import, ast.ImportFrom)):
            for alias in current.names:
                if alias.name == "*":
                    continue
                names.add(alias.asname or alias.name.split(".")[0])
        for child in ast.iter_child_nodes(current):
            walk(child)

    walk(node, top=True)
    return names


# ---------------------------------------------------------------------------
# import resolution
# ---------------------------------------------------------------------------

def _import_targets(
    node: ast.Import | ast.ImportFrom,
    source_path: str,
    module: str,
    is_package: bool,
    module_map: dict[str, str],
    defs_by_module: dict[str, set[str]],
    scope: str | None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return (edges, top-level bindings) for one import statement."""
    edges: list[dict[str, Any]] = []
    bindings: dict[str, dict[str, Any]] = {}

    def add_edge(
        target_module: str | None,
        target: str | None,
        names: list[str],
        evidence: str,
    ) -> None:
        edges.append({
            "kind": "import",
            "source": source_path,
            "source_module": module,
            "scope": scope,
            "lineno": node.lineno,
            "names": sorted(set(names)),
            "target_module": target_module,
            "target": target,
            "evidence": evidence,
        })

    def bind(name: str, *, module_name: str | None = None,
             module_path: str | None = None, symbol: str | None = None,
             evidence: str = "direct") -> None:
        bindings[name] = {
            "module_name": module_name,
            "module_path": module_path,
            "symbol": symbol,
            "evidence": evidence,
        }

    if isinstance(node, ast.Import):
        for alias in node.names:
            target_path = module_map.get(alias.name)
            names = [alias.name]
            if target_path:
                add_edge(alias.name, target_path, names, "direct")
                if alias.asname:
                    bind(alias.asname, module_name=alias.name, module_path=target_path)
                else:
                    root = alias.name.split(".")[0]
                    root_path = module_map.get(root)
                    bind(root, module_name=root, module_path=root_path,
                         evidence="direct" if root_path else "unknown")
            else:
                add_edge(None, None, names, "external")
                if alias.asname:
                    bind(alias.asname, evidence="unknown")
        return edges, bindings

    if node.level:
        package = _package_of(module, is_package)
        parts = package.split(".") if package else []
        ascend = node.level - 1
        if ascend > len(parts):
            module_base = ""
        else:
            parts = parts[: len(parts) - ascend] if ascend else parts
            module_base = ".".join(parts)
        base = ".".join(part for part in (module_base, node.module or "") if part)
        if not base:
            add_edge(None, None, [a.name for a in node.names], "unknown")
            for alias in node.names:
                if alias.name != "*":
                    bind(alias.asname or alias.name, evidence="unknown")
            return edges, bindings
    else:
        base = node.module or ""

    base_path = module_map.get(base)
    base_symbols = defs_by_module.get(base, set())

    for alias in node.names:
        if alias.name == "*":
            if base_path:
                add_edge(base, base_path, ["*"], "direct")
            else:
                add_edge(None, None, ["*"], "external")
            continue
        submodule = f"{base}.{alias.name}" if base else alias.name
        submodule_path = module_map.get(submodule)
        bound_name = alias.asname or alias.name
        # Runtime `from pkg import name` prefers a package attribute. Only when
        # that attribute is not a statically known top-level symbol do we fall
        # back to a same-named submodule.
        if base_path and alias.name in base_symbols:
            add_edge(base, base_path, [alias.name], "direct")
            bind(bound_name, module_name=base, module_path=base_path,
                 symbol=f"{base_path}::{alias.name}")
        elif submodule_path:
            add_edge(submodule, submodule_path, [alias.name], "direct")
            bind(bound_name, module_name=submodule, module_path=submodule_path)
        elif base_path:
            # The base is local but this imported name is not a top-level def:
            # keep the import edge as direct evidence and the binding unknown.
            add_edge(base, base_path, [alias.name], "direct")
            bind(bound_name, module_name=base, module_path=base_path, evidence="unknown")
        else:
            add_edge(None, None, [alias.name], "external")
            bind(bound_name, evidence="unknown")
    return edges, bindings


# ---------------------------------------------------------------------------
# call resolution
# ---------------------------------------------------------------------------

def _resolve_callee(
    func: ast.AST,
    module: str,
    path: str,
    scope: str,
    bindings: dict[str, dict[str, Any]],
    module_map: dict[str, str],
    defs_by_module: dict[str, set[str]],
    class_methods_by_module: dict[str, dict[str, list[str]]],
    active_locals: set[str],
    ambiguous_names: set[str],
) -> dict[str, Any]:
    unknown = {"target": None, "target_module": None, "evidence": "unknown"}

    if isinstance(func, ast.Name):
        name = func.id
        if name in active_locals or name in ambiguous_names:
            return unknown
        if name in defs_by_module.get(module, set()):
            return {"target": f"{path}::{name}", "target_module": path, "evidence": "direct"}
        binding = bindings.get(name)
        if not binding:
            return unknown
        if binding.get("symbol"):
            return {
                "target": binding["symbol"],
                "target_module": binding.get("module_path"),
                "evidence": binding.get("evidence", "direct"),
            }
        return {
            "target": None,
            "target_module": binding.get("module_path"),
            "evidence": "unknown",
        }

    if isinstance(func, ast.Attribute):
        attrs: list[str] = []
        root: ast.AST = func
        while isinstance(root, ast.Attribute):
            attrs.append(root.attr)
            root = root.value
        attrs.reverse()

        # self.method(...) inside a top-level class method: one explicit static
        # inference. Nested classes/functions cannot be mapped uniquely, so
        # they stay unknown rather than borrowing an outer class's method.
        if isinstance(root, ast.Name) and root.id == "self" and attrs and scope:
            scope_parts = scope.split(".")
            if len(scope_parts) != 2:
                return unknown
            class_name = scope_parts[0]
            methods = class_methods_by_module.get(module, {}).get(class_name, [])
            if attrs[0] in methods:
                return {
                    "target": f"{path}::{class_name}.{attrs[0]}",
                    "target_module": path,
                    "evidence": "inferred",
                }
            return unknown

        if not isinstance(root, ast.Name) or root.id in active_locals or root.id in ambiguous_names:
            return unknown
        binding = bindings.get(root.id)
        if (
            not binding
            or binding.get("symbol")
            or binding.get("evidence") != "direct"
            or not binding.get("module_name")
        ):
            return unknown
        base_module = binding["module_name"]
        base_path = binding.get("module_path")
        if not base_path and base_module not in module_map:
            return unknown
        # module.attr() or module.sub.attr(): resolve the module chain first.
        module_chain = [base_module, *attrs[:-1]]
        candidate = ".".join(module_chain)
        candidate_path = module_map.get(candidate)
        if not candidate_path:
            return unknown
        last = attrs[-1] if attrs else ""
        if last in defs_by_module.get(candidate, set()):
            return {
                "target": f"{candidate_path}::{last}",
                "target_module": candidate_path,
                "evidence": "direct",
            }
        return {"target": None, "target_module": candidate_path, "evidence": "unknown"}

    return unknown


def _call_edges(
    tree: ast.Module,
    path: str,
    module: str,
    bindings: dict[str, dict[str, Any]],
    module_map: dict[str, str],
    defs_by_module: dict[str, set[str]],
    class_methods_by_module: dict[str, dict[str, list[str]]],
    ambiguous_names: set[str],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    active_locals: set[str] = set()

    def visit(node: ast.AST, scope: str) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Decorators, defaults and annotations are evaluated in the
            # enclosing scope; only the body uses the function scope.
            for decorator in node.decorator_list:
                visit(decorator, scope)
            for default in (*node.args.defaults, *node.args.kw_defaults):
                if default is not None:
                    visit(default, scope)
            arguments = [
                *node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
            ]
            if node.args.vararg:
                arguments.append(node.args.vararg)
            if node.args.kwarg:
                arguments.append(node.args.kwarg)
            for argument in arguments:
                if argument.annotation is not None:
                    visit(argument.annotation, scope)
            if node.returns is not None:
                visit(node.returns, scope)
            child_scope = f"{scope}.{node.name}" if scope else node.name
            local = _function_locals(node)
            added = local - active_locals
            active_locals.update(local)
            try:
                for child in node.body:
                    visit(child, child_scope)
            finally:
                active_locals.difference_update(added)
            return
        if isinstance(node, ast.Lambda):
            for default in (*node.args.defaults, *node.args.kw_defaults):
                if default is not None:
                    visit(default, scope)
            child_scope = f"{scope}.<lambda>" if scope else "<lambda>"
            local = _function_locals(node)
            added = local - active_locals
            active_locals.update(local)
            try:
                visit(node.body, child_scope)
            finally:
                active_locals.difference_update(added)
            return
        if isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                visit(decorator, scope)
            for base in node.bases:
                visit(base, scope)
            for keyword in node.keywords:
                visit(keyword.value, scope)
            child_scope = f"{scope}.{node.name}" if scope else node.name
            for child in node.body:
                visit(child, child_scope)
            return
        if isinstance(node, ast.Call):
            try:
                expression = ast.unparse(node.func)
            except (ValueError, AttributeError):
                expression = "<unparseable>"
            resolved = _resolve_callee(
                node.func, module, path, scope, bindings, module_map,
                defs_by_module, class_methods_by_module, active_locals, ambiguous_names,
            )
            edges.append({
                "kind": "call",
                "source": path,
                "scope": scope or None,
                "lineno": node.lineno,
                "expression": expression,
                "target": resolved["target"],
                "target_module": resolved["target_module"],
                "evidence": resolved["evidence"],
            })
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    for node in tree.body:
        visit(node, "")
    return edges


# ---------------------------------------------------------------------------
# graph build
# ---------------------------------------------------------------------------

def _build_graph(parsed: dict[str, ast.Module], inputs: list[dict[str, Any]]) -> dict[str, Any]:
    paths = sorted(parsed)
    module_map = {_module_name(path): path for path in paths if _module_name(path)}
    defs_by_module: dict[str, set[str]] = {}
    class_methods_by_module: dict[str, dict[str, list[str]]] = {}
    public_functions: dict[str, list[str]] = {}
    public_classes: dict[str, list[str]] = {}
    ambiguous_names: dict[str, set[str]] = {}

    for path in paths:
        module = _module_name(path)
        functions, classes, class_methods = _top_level_defs(parsed[path])
        defs_by_module[module] = set(functions) | set(classes)
        class_methods_by_module[module] = class_methods
        public_functions[path] = _public(functions)
        public_classes[path] = _public(classes)
        ambiguous_names[path] = _ambiguous_top_level_names(parsed[path])

    modules: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for path in paths:
        module = _module_name(path)
        is_pkg = _is_package(path)
        modules.append({
            "path": path,
            "module": module,
            "package": _package_of(module, is_pkg),
            "is_package": is_pkg,
            "public_functions": public_functions[path],
            "public_classes": public_classes[path],
            "class_methods": {
                name: _public(methods)
                for name, methods in sorted(class_methods_by_module[module].items())
            },
        })
        for name in public_functions[path]:
            symbols.append({
                "id": f"{path}::{name}",
                "path": path,
                "module": module,
                "name": name,
                "kind": "function",
            })
        for name in public_classes[path]:
            symbols.append({
                "id": f"{path}::{name}",
                "path": path,
                "module": module,
                "name": name,
                "kind": "class",
                "public_methods": _public(class_methods_by_module[module].get(name, [])),
            })

        # Collect imports first: module-level bindings feed call resolution.
        # Names with repeated top-level bindings are deliberately omitted; the
        # ambiguity set keeps their call sites unknown rather than reusing a
        # stale import.
        top_level_ids = {id(node) for node in parsed[path].body}
        bindings: dict[str, dict[str, Any]] = {}
        import_edges: list[dict[str, Any]] = []
        for node in ast.walk(parsed[path]):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                scope = None
                # Only top-level imports establish module bindings. Imports in
                # functions/classes still produce edges with their lexical scope.
                if id(node) not in top_level_ids:
                    scope = _scope_for_node(parsed[path], node)
                node_edges, node_bindings = _import_targets(
                    node, path, module, is_pkg, module_map, defs_by_module, scope,
                )
                import_edges.extend(node_edges)
                if scope is None:
                    for name, binding in node_bindings.items():
                        if name not in ambiguous_names[path]:
                            bindings.setdefault(name, binding)
        edges.extend(import_edges)
        edges.extend(_call_edges(
            parsed[path], path, module, bindings, module_map,
            defs_by_module, class_methods_by_module, ambiguous_names[path],
        ))

    edges.sort(key=lambda edge: (
        edge["kind"],
        edge["source"],
        edge.get("lineno", 0),
        edge.get("scope") or "",
        edge.get("expression") or "",
        edge.get("target") or "",
        edge["evidence"],
    ))

    counts = {
        "modules": len(modules),
        "symbols": len(symbols),
        "import_edges": sum(1 for edge in edges if edge["kind"] == "import"),
        "call_edges": sum(1 for edge in edges if edge["kind"] == "call"),
        "direct_edges": sum(1 for edge in edges if edge["evidence"] == "direct"),
        "inferred_edges": sum(1 for edge in edges if edge["evidence"] == "inferred"),
        "unknown_edges": sum(1 for edge in edges if edge["evidence"] == "unknown"),
        "external_edges": sum(1 for edge in edges if edge["evidence"] == "external"),
    }

    return {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "language_scope": ["python"],
        "scope": {
            "files": paths,
            "excluded_dirs": sorted(_EXCLUDED_DIRS),
            "hidden_dirs": "all dot-prefixed directories are skipped",
        },
        "notes": [_SCOPE_NOTE, _UNKNOWN_NOTE, _LOCAL_PRECEDENCE_NOTE, _EXCLUDED_NOTE],
        "modules": modules,
        "symbols": symbols,
        "edges": edges,
        "counts": counts,
        "inputs_digest": _digest_inputs(inputs),
    }


def _scope_for_node(tree: ast.Module, target: ast.AST) -> str | None:
    """Best-effort lexical scope label for a nested import node."""

    def walk(node: ast.AST, scope: str) -> str | None:
        if node is target:
            return scope or None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            child = f"{scope}.{node.name}" if scope else node.name
            for child_node in node.body:
                found = walk(child_node, child)
                if found is not None:
                    return found
            return None
        if isinstance(node, ast.ClassDef):
            child = f"{scope}.{node.name}" if scope else node.name
            for child_node in node.body:
                found = walk(child_node, child)
                if found is not None:
                    return found
            return None
        if isinstance(node, ast.Lambda):
            child = f"{scope}.<lambda>" if scope else "<lambda>"
            return walk(node.body, child)
        for child_node in ast.iter_child_nodes(node):
            found = walk(child_node, scope)
            if found is not None:
                return found
        return None

    return walk(tree, "")


def _manifest(inputs: list[dict[str, Any]], graph_bytes: bytes,
              graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "language_scope": ["python"],
        "inputs": inputs,
        "inputs_digest": _digest_inputs(inputs),
        "graph_path": f"{GRAPH_DIR_REL}/{GRAPH_FILE}",
        "graph_bytes": len(graph_bytes),
        "graph_digest": _sha256(graph_bytes),
        "counts": graph["counts"],
        "notes": [_SCOPE_NOTE, _UNKNOWN_NOTE, _LOCAL_PRECEDENCE_NOTE, _EXCLUDED_NOTE],
    }


def build() -> dict[str, Any]:
    inputs = _scan_inputs()
    parsed: dict[str, ast.Module] = {}
    for item in inputs:
        rel = item["path"]
        data = _read_bytes(ROOT / rel)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RepoGraphError("read_error", rel, f"not UTF-8 ({exc})") from exc
        try:
            parsed[rel] = ast.parse(text, filename=rel)
        except SyntaxError as exc:
            location = f"line {exc.lineno}" if exc.lineno else "unknown line"
            raise RepoGraphError("parse_error", rel, f"{location}: {exc.msg}") from exc

    graph = _build_graph(parsed, inputs)
    graph_bytes = _serialize(graph)
    manifest = _manifest(inputs, graph_bytes, graph)
    manifest_bytes = _serialize(manifest)

    _atomic_write(GRAPH_PATH, graph_bytes)
    _atomic_write(MANIFEST_PATH, manifest_bytes)
    return {
        "status": "built",
        "graph": f"{GRAPH_DIR_REL}/{GRAPH_FILE}",
        "manifest": f"{GRAPH_DIR_REL}/{MANIFEST_FILE}",
        "inputs": len(inputs),
        "graph_digest": manifest["graph_digest"],
        "inputs_digest": manifest["inputs_digest"],
        "counts": graph["counts"],
    }


# ---------------------------------------------------------------------------
# freshness check (strictly read-only)
# ---------------------------------------------------------------------------

def _invalid(detail: str, path: str = f"{GRAPH_DIR_REL}/{MANIFEST_FILE}") -> dict[str, Any]:
    return {"status": "invalid", "path": path, "detail": detail, "repair": REPAIR}


def check() -> tuple[dict[str, Any], int]:
    if not MANIFEST_PATH.is_file():
        return {
            "status": "not_initialized",
            "path": f"{GRAPH_DIR_REL}/{MANIFEST_FILE}",
            "detail": "repo graph is not initialized; audit skips it",
        }, 0
    try:
        manifest = _read_json(MANIFEST_PATH)
    except RepoGraphError as exc:
        return _invalid(f"{exc.code}: {exc.detail}"), 1
    if not isinstance(manifest, dict):
        return _invalid("manifest root must be an object"), 1
    if manifest.get("schema") != SCHEMA:
        return _invalid("manifest schema does not match this generator"), 1
    if manifest.get("generator_version") != GENERATOR_VERSION:
        return {
            "status": "stale",
            "path": f"{GRAPH_DIR_REL}/{MANIFEST_FILE}",
            "detail": "generator version changed; rebuild the graph",
            "repair": REPAIR,
        }, 1
    if manifest.get("graph_path") != f"{GRAPH_DIR_REL}/{GRAPH_FILE}":
        return _invalid("manifest graph_path is not the expected graph file"), 1

    if not GRAPH_PATH.is_file():
        return _invalid("graph file is missing"), 1
    try:
        graph_bytes = _read_bytes(GRAPH_PATH)
    except RepoGraphError as exc:
        return _invalid(f"{exc.code}: {exc.detail}", exc.path), 1
    if _sha256(graph_bytes) != manifest.get("graph_digest"):
        return _invalid("graph digest does not match manifest (corrupt or partially written)"), 1
    try:
        graph = json.loads(graph_bytes.decode("utf-8"))
    except UnicodeDecodeError:
        return _invalid("graph file is not UTF-8"), 1
    except json.JSONDecodeError as exc:
        return _invalid(f"graph file is invalid JSON at line {exc.lineno}"), 1
    if not isinstance(graph, dict) or graph.get("schema") != SCHEMA:
        return _invalid("graph schema does not match this generator"), 1

    declared = manifest.get("inputs")
    if not isinstance(declared, list):
        return _invalid("manifest inputs must be a list"), 1
    try:
        current = _scan_inputs()
    except RepoGraphError as exc:
        return _invalid(f"{exc.code}: {exc.detail}", exc.path), 1
    if declared != current:
        return {
            "status": "stale",
            "path": f"{GRAPH_DIR_REL}/{MANIFEST_FILE}",
            "detail": "input files changed since the last build; rebuild the graph",
            "repair": REPAIR,
        }, 1
    if manifest.get("inputs_digest") != _digest_inputs(declared):
        return _invalid("manifest inputs_digest does not match its own input list"), 1
    if graph.get("inputs_digest") != manifest.get("inputs_digest"):
        return _invalid("graph input summary does not match manifest"), 1
    return {
        "status": "ok",
        "path": f"{GRAPH_DIR_REL}/{MANIFEST_FILE}",
        "detail": f"repo graph is fresh ({len(current)} Python inputs)",
        "graph_digest": manifest.get("graph_digest"),
    }, 0


# ---------------------------------------------------------------------------
# query model (show / impacted)
# ---------------------------------------------------------------------------

def _load_graph() -> tuple[dict[str, Any], dict[str, Any]]:
    if not MANIFEST_PATH.is_file() or not GRAPH_PATH.is_file():
        raise RepoGraphError(
            "not_built", f"{GRAPH_DIR_REL}/{GRAPH_FILE}",
            f"repo graph is not built; run: {REPAIR}",
        )
    manifest = _read_json(MANIFEST_PATH)
    graph_bytes = _read_bytes(GRAPH_PATH)
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise RepoGraphError("invalid_manifest", f"{GRAPH_DIR_REL}/{MANIFEST_FILE}",
                             "manifest schema does not match this generator")
    if _sha256(graph_bytes) != manifest.get("graph_digest"):
        raise RepoGraphError("invalid_graph", f"{GRAPH_DIR_REL}/{GRAPH_FILE}",
                             "graph digest does not match manifest")
    try:
        graph = json.loads(graph_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepoGraphError("invalid_graph", f"{GRAPH_DIR_REL}/{GRAPH_FILE}",
                             f"graph is not valid UTF-8 JSON ({exc})") from exc
    if not isinstance(graph, dict) or graph.get("schema") != SCHEMA:
        raise RepoGraphError("invalid_graph", f"{GRAPH_DIR_REL}/{GRAPH_FILE}",
                             "graph schema does not match this generator")
    return graph, manifest


def _normalize_path(value: str, graph: dict[str, Any]) -> str | None:
    raw = value.replace("\\", "/").strip()
    if not raw:
        return None
    candidate = Path(raw)
    try:
        absolute = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
        rel = absolute.relative_to(ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return None
    paths = {module["path"] for module in graph.get("modules", [])}
    if rel in paths:
        return rel
    # Fall back to an exact module-name lookup for convenience.
    for module in graph.get("modules", []):
        if module.get("module") == raw.rstrip("/"):
            return module["path"]
    return None


def _module_index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {module["path"]: module for module in graph.get("modules", [])}


def _symbol_index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {symbol["id"]: symbol for symbol in graph.get("symbols", [])}


def _resolve_object(value: str, graph: dict[str, Any]) -> dict[str, Any] | None:
    if "::" in value:
        raw_path, raw_name = value.split("::", 1)
        path = _normalize_path(raw_path, graph)
        if not path:
            return None
        symbol = _symbol_index(graph).get(f"{path}::{raw_name}")
        if symbol:
            return {"kind": symbol["kind"], "id": symbol["id"], "path": path,
                    "name": raw_name, "module": symbol.get("module")}
        module = _module_index(graph).get(path)
        if not module:
            return None
        methods = module.get("class_methods", {})
        if raw_name in methods:
            return {"kind": "class", "id": f"{path}::{raw_name}", "path": path,
                    "name": raw_name, "module": module.get("module"),
                    "public_methods": methods.get(raw_name, [])}
        if "." in raw_name:
            class_name, method_name = raw_name.split(".", 1)
            if method_name in methods.get(class_name, []):
                return {"kind": "method", "id": f"{path}::{raw_name}", "path": path,
                        "name": method_name, "class": class_name,
                        "module": module.get("module")}
            return None
        candidates = [
            (class_name, method_name)
            for class_name, names in methods.items()
            for method_name in names
            if method_name == raw_name
        ]
        if len(candidates) == 1:
            class_name, method_name = candidates[0]
            return {"kind": "method", "id": f"{path}::{class_name}.{method_name}",
                    "path": path, "name": method_name, "class": class_name,
                    "module": module.get("module")}
        return None
    path = _normalize_path(value, graph)
    if not path:
        return None
    module = _module_index(graph).get(path)
    return {
        "kind": "module",
        "id": path,
        "path": path,
        "module": module.get("module"),
        "public_functions": module.get("public_functions", []),
        "public_classes": module.get("public_classes", []),
        "class_methods": module.get("class_methods", {}),
    }


def _bound(items: list[Any], limit: int) -> tuple[list[Any], bool]:
    return items[:limit], len(items) > limit


def show(value: str, limit: int) -> dict[str, Any]:
    graph, _manifest_data = _load_graph()
    obj = _resolve_object(value, graph)
    if obj is None:
        raise RepoGraphError("not_found", value,
                             "path or object is not in the repo graph; run build after adding it")
    path = obj["path"]
    edges = graph.get("edges", [])
    imports = sorted(
        (edge for edge in edges if edge["kind"] == "import" and edge["source"] == path),
        key=lambda edge: (edge.get("lineno", 0), edge["target"] or "", edge["names"]),
    )
    imported_by = sorted(
        (edge for edge in edges if edge["kind"] == "import" and edge["target"] == path),
        key=lambda edge: (edge["source"], edge.get("lineno", 0)),
    )
    calls = sorted(
        (edge for edge in edges if edge["kind"] == "call" and edge["source"] == path
         and _call_in_scope(edge, obj)),
        key=lambda edge: (edge.get("lineno", 0), edge["expression"], edge["evidence"]),
    )
    called_by = sorted(
        (edge for edge in edges if edge["kind"] == "call" and _call_targets(edge, obj)),
        key=lambda edge: (edge["source"], edge.get("lineno", 0), edge["expression"]),
    )

    relations: dict[str, Any] = {}
    omitted: dict[str, int] = {}
    for name, rows in (
        ("imports", imports),
        ("imported_by", imported_by),
        ("calls", calls),
        ("called_by", called_by),
    ):
        bounded, truncated = _bound(rows, limit)
        relations[name] = bounded
        if truncated:
            omitted[name] = len(rows) - limit
    return {
        "schema": "iad-repo-graph/show/1",
        "object": obj,
        "relations": relations,
        "limits": {"per_relation": limit},
        "truncated": bool(omitted),
        "omitted": omitted,
    }


def _call_in_scope(edge: dict[str, Any], obj: dict[str, Any]) -> bool:
    if obj["kind"] == "module":
        return True
    scope = edge.get("scope") or ""
    if obj["kind"] == "function":
        return scope == obj["name"] or scope.startswith(obj["name"] + ".")
    if obj["kind"] == "class":
        return scope == obj["name"] or scope.startswith(obj["name"] + ".")
    if obj["kind"] == "method":
        method = obj["id"].split("::", 1)[1]
        return scope == method or scope.startswith(method + ".")
    return False


def _call_targets(edge: dict[str, Any], obj: dict[str, Any]) -> bool:
    target = edge.get("target") or ""
    if obj["kind"] == "module":
        return edge.get("target_module") == obj["path"]
    if obj["kind"] == "class":
        return target == obj["id"] or target.startswith(obj["id"] + ".")
    return target == obj["id"]


def impacted(values: list[str], limit: int) -> dict[str, Any]:
    graph, _manifest_data = _load_graph()
    changed: list[dict[str, Any]] = []
    unknown: list[str] = []
    changed_modules: set[str] = set()
    changed_symbols: set[str] = set()

    for raw in values:
        obj = _resolve_object(raw, graph)
        if obj is None:
            unknown.append(raw)
            continue
        changed.append({"input": raw, "id": obj["id"], "kind": obj["kind"], "path": obj["path"]})
        if obj["kind"] == "module":
            changed_modules.add(obj["path"])
        else:
            changed_symbols.add(obj["id"])

    reasons: dict[str, set[str]] = {}
    evidence_by_object: dict[str, set[str]] = {}
    objects: dict[str, dict[str, Any]] = {}

    def add(obj_id: str, kind: str, reason: str, evidence: str) -> None:
        objects.setdefault(obj_id, {"id": obj_id, "kind": kind})
        reasons.setdefault(obj_id, set()).add(reason)
        evidence_by_object.setdefault(obj_id, set()).add(evidence)

    for edge in graph.get("edges", []):
        if edge["kind"] == "import" and edge.get("target") in changed_modules:
            if edge["source"] not in changed_modules:
                add(edge["source"], "module", f"imports:{edge['target']}",
                    edge.get("evidence", "unknown"))
        elif edge["kind"] == "call":
            # Only resolved direct/inferred call targets count as direct impact;
            # unknown receivers are not evidence of a real dependency.
            if edge.get("evidence") not in ("direct", "inferred"):
                continue
            target = edge.get("target")
            if not target:
                continue
            target_module = edge.get("target_module")
            if target in changed_symbols or target_module in changed_modules:
                if edge["source"] not in changed_modules:
                    add(edge["source"], "module", f"calls:{target}", edge["evidence"])

    impacted_rows = [
        {
            **objects[obj_id],
            "reasons": sorted(reasons[obj_id]),
            "evidence": sorted(evidence_by_object[obj_id]),
        }
        for obj_id in sorted(objects)
    ]
    bounded, truncated = _bound(impacted_rows, limit)
    return {
        "schema": "iad-repo-graph/impacted/1",
        "changed": sorted(changed, key=lambda row: row["id"]),
        "unknown_inputs": unknown,
        "impacted": bounded,
        "limits": {"objects": limit},
        "truncated": truncated,
        "omitted": max(0, len(impacted_rows) - limit),
        "transitive": False,
        "notes": [
            "One direct hop only; importers and callers are separate evidence, not a runtime impact claim.",
            "Only imports and direct/inferred call targets are counted as direct impact; unknown calls are excluded.",
            f"Run: {REPAIR} after changing files.",
        ],
    }


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def _emit(value: dict[str, Any], as_json: bool, human: str) -> None:
    if as_json:
        sys.stdout.write(_serialize(value).decode("utf-8"))
    else:
        print(human)


def _error_payload(exc: RepoGraphError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": exc.code,
        "path": exc.path,
        "detail": exc.detail,
        "repair": REPAIR if exc.code != "parse_error" else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic Python structure evidence for init-agent-docs projects"
    )
    sub = parser.add_subparsers(dest="command")

    p_build = sub.add_parser("build", help="Generate .agents/repo-graph artifacts")
    p_build.add_argument("--json", action="store_true", help="Output JSON")

    p_check = sub.add_parser("check", help="Read-only freshness check")
    p_check.add_argument("--json", action="store_true", help="Output JSON")

    p_show = sub.add_parser("show", help="Show one object and its direct relations")
    p_show.add_argument("--path", required=True, help="Project-relative .py path or object id")
    p_show.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Relations per list, 1-{MAX_LIMIT} (default {DEFAULT_LIMIT})")
    p_show.add_argument("--json", action="store_true", help="Output JSON")

    p_impact = sub.add_parser("impacted", help="Show one-hop direct impact")
    p_impact.add_argument("--paths", nargs="+", required=True,
                          help="Changed project-relative paths or object ids")
    p_impact.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                          help=f"Impacted objects, 1-{MAX_LIMIT} (default {DEFAULT_LIMIT})")
    p_impact.add_argument("--json", action="store_true", help="Output JSON")

    return parser


def _limit(value: int) -> int:
    if not 1 <= value <= MAX_LIMIT:
        raise SystemExit(f"--limit must be between 1 and {MAX_LIMIT}")
    return value


def _truncation_label(result: dict[str, Any]) -> str:
    omitted = result.get("omitted")
    if not omitted:
        return ""
    if isinstance(omitted, dict):
        detail = ", ".join(f"{name} omitted {count}" for name, count in sorted(omitted.items()))
    else:
        detail = f"omitted {omitted}"
    return f"; truncated: {detail}"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "command") or args.command is None:
        parser.print_help()
        return 1
    try:
        if args.command == "build":
            result = build()
            _emit(result, args.json,
                  f"built {result['graph']} and {result['manifest']} "
                  f"({result['inputs']} Python inputs)")
            return 0
        if args.command == "check":
            result, code = check()
            _emit(result, args.json,
                  f"[{result['status'].upper()}] {result.get('detail', '')}")
            return code
        if args.command == "show":
            result = show(args.path, _limit(args.limit))
            _emit(result, args.json,
                  f"{result['object']['kind']} {result['object']['id']}: "
                  f"{len(result['relations']['calls'])} calls, "
                  f"{len(result['relations']['called_by'])} callers"
                  f"{_truncation_label(result)}")
            return 0
        if args.command == "impacted":
            result = impacted(args.paths, _limit(args.limit))
            _emit(result, args.json,
                  f"{len(result['impacted'])} directly impacted object(s), "
                  f"{len(result['unknown_inputs'])} unknown input(s)"
                  f"{_truncation_label(result)}")
            return 0
        parser.print_help()
        return 1
    except RepoGraphError as exc:
        payload = _error_payload(exc)
        if getattr(args, "json", False):
            sys.stdout.write(_serialize(payload).decode("utf-8"))
        else:
            print(f"[ERROR] {exc.path}: {exc.detail}", file=sys.stderr)
            if payload.get("repair"):
                print(f"repair: {payload['repair']}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main(sys.argv[1:]))

"""audit.py — 文档一致性机械检查 (token-light, read-only).

Checks that init-agent-docs initialized files have not rotted:
dead links, STRUCTURE index completeness, tech-stack drift between docs
and manifests, birth-record presence, AGENTS.md line budget, memory
structure health and optional bugfix eval records (R1, Git-free).
The source-only R2 scoring checker is invoked explicitly by check_source.py;
generated-project audit commands do not activate it.

All subcommands are read-only — this tool never modifies files.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

# Supports <project_root>/scripts/ and <project_root>/.meta/scripts/. The skill
# repo itself keeps audit.py at <repo>/assets/scripts/ — resolve ROOT to the
# repo root there too, so R2 (eval-baseline scoring) can bind the skill repo
# itself, its only intended subject.
SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent.parent if SCRIPTS_DIR.parent.name in ('.meta', 'assets') else SCRIPTS_DIR.parent
SCRIPTS_REL = '.meta/scripts' if SCRIPTS_DIR.parent.name == '.meta' else 'scripts'

MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
FENCED_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
INLINE_CODE_RE = re.compile(r"`[^`]+`")
HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")


def _strip_noise(text: str) -> str:
    """Remove fenced code blocks, inline code, and HTML comments."""
    text = FENCED_BLOCK_RE.sub("", text)
    text = INLINE_CODE_RE.sub("", text)
    text = HTML_COMMENT_RE.sub("", text)
    return text

# Root-level instruction files always checked.
_ROOT_DOC_FILES = [
    "AGENTS.md",
    "docs/STRUCTURE.md",
]

# Dynamic discovery: all .md files under docs/ (excluding plans/ and __pycache__).
def _discover_doc_files() -> list[str]:
    """Discover all markdown files to check for dead links."""
    files = list(_ROOT_DOC_FILES)
    # Root-level README files (README.md, README-tools.md, etc.)
    for f in sorted(ROOT.glob("README*.md")):
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        if rel not in files:
            files.append(rel)
    # scripts/ README files
    scripts_dir = SCRIPTS_DIR
    if scripts_dir.is_dir():
        for f in sorted(scripts_dir.glob("README*.md")):
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            if rel not in files:
                files.append(rel)
    docs_dir = ROOT / "docs"
    if docs_dir.is_dir():
        for f in sorted(docs_dir.rglob("*.md")):
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            # Include plan files (active + completed) for dead link checking.
            files.append(rel)
    return files

MANIFEST_GLOBS = [
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "requirements*.txt",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "composer.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
]

# Keyword matches are advisory investigation hints, not dependency judgments.
# The agent checks standard-library and externally deployed facilities as well as
# manifests; extending a dictionary cannot replace that interpretation.
DRIFT_PATTERNS: dict[str, list[str]] = {
    "SQLite":            ["sqlite", "aiosqlite", "better-sqlite3", "sql.js"],
    "PostgreSQL":        ["postgres", "postgresql", "psycopg2", "psycopg", "pg", "pg-promise"],
    "MySQL":             ["mysql", "mariadb", "pymysql", "mysql2"],
    "MongoDB":           ["mongo", "mongodb", "mongoose", "pymongo"],
    "Redis":             ["redis", "ioredis", "aioredis"],
    "RabbitMQ":          ["rabbitmq", "amqp", "pika"],
    "Kafka":             ["kafka", "kafkajs", "confluent-kafka"],
    "Docker":            ["docker", "docker-compose", "dockerfile"],
    "Kubernetes":        ["kubernetes", "k8s", "kubectl", "helm"],
    "Elasticsearch":     ["elasticsearch", "elastic"],
    "GraphQL":           ["graphql", "apollo", "gql", "relay"],
    "gRPC":              ["grpc", "protobuf", "proto"],
    "WebSocket":         ["websocket", "ws", "socket.io", "sockjs"],
    "Celery":            ["celery"],
    "RQ":                ["rq", "django-rq"],
    "Nginx":             ["nginx"],
    "Caddy":             ["caddy"],
    "S3":                ["s3", "boto3", "minio", "aws-sdk"],
    "JWT":               ["jwt", "pyjwt", "jsonwebtoken", "jose"],
    "OAuth":             ["oauth", "oauth2", "oidc", "openid"],
    "Sentry":            ["sentry"],
    "Prometheus":        ["prometheus", "prom-client"],
    "Grafana":           ["grafana"],
    "Terraform":         ["terraform", "opentofu"],
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class DocumentReadError(OSError):
    """Expected failure while reading a project document as UTF-8."""

    def __init__(self, path: Path, cause: OSError | UnicodeDecodeError):
        self.document_path = path
        self.cause = cause
        super().__init__(str(cause))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DocumentReadError(path, exc) from exc


def _lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return _read(path).splitlines()


def _exists(rel: str) -> bool:
    # 索引目标可以是目录（如 problems/bugfix/、plans/ 目录行）
    return (ROOT / rel).exists()


def _resolve(target: str, source_dir: Path) -> Path:
    """Resolve a markdown link target relative to the source file's directory.

    Per CommonMark spec, all paths are relative to the containing file except
    those starting with '/'. Absolute paths (/) are resolved against ROOT.
    """
    target = unquote(target)
    if target.startswith("/"):
        return (ROOT / target.lstrip("/")).resolve()
    return (source_dir / target).resolve()


def _find_manifests() -> list[Path]:
    found: list[Path] = []
    for g in MANIFEST_GLOBS:
        found.extend(ROOT.glob(g))
    return sorted(set(found))


# ---------------------------------------------------------------------------
# frontmatter
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL
)


# Blockquote metadata pattern: lines starting with "> key : value" in the first 5 lines.
# Supports both ASCII colon (:) and full-width colon (：).
_BLOCKQUOTE_META_RE = re.compile(r"^>\s*(\S[^:：]+?)\s*[:：]\s*(.+)$")


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse frontmatter from a plan file.

    Tries two formats in order:
    1. YAML frontmatter between --- delimiters (preferred, see plan.md.tpl).
    2. Blockquote metadata lines ("> key: value") within first 10 lines (legacy
       format from init-agent-docs < 2026-07-29).

    Returns a plain dict with lowercase keys. This is intentionally NOT a full
    YAML parser — it handles the subset used in plan files: key: value pairs.
    Multi-line values and YAML lists are NOT supported.
    """
    fm: dict[str, Any] = {}

    # Try format 1: YAML frontmatter (--- delimiters)
    m = _FRONTMATTER_RE.match(text)
    if m:
        for line in m.group(1).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" not in stripped:
                continue
            key, _, val = stripped.partition(":")
            # Strip inline YAML comments (e.g., "# in_progress | done | cancelled")
            clean_val = val.strip().split(" #", 1)[0].rstrip()
            k = key.strip().lower()
            # Normalize status values (Chinese → canonical, legacy aliases → canonical)
            if k == "status":
                clean_val = _normalize_status(clean_val)
            fm[k] = clean_val
        # If frontmatter has status, return now. Otherwise fall through so
        # blockquote metadata can supply the missing status field.
        if "status" in fm:
            return fm

    # Try format 2: blockquote metadata within first 10 lines (legacy).
    # 10 lines covers both standalone blockquote (lines 1-4) and the case
    # where YAML frontmatter pushes content down (lines 4-7).
    # Merges into fm — does not overwrite existing keys from format 1.
    _KEY_MAP_CN: dict[str, str] = {
        "状态": "status",
        "创建时间": "created_at",
        "模式": "mode",
        "协调人": "coordinator",
    }
    for line in text.splitlines()[:10]:
        bm = _BLOCKQUOTE_META_RE.match(line)
        if bm:
            raw_key, val = bm.group(1).strip(), bm.group(2).strip()
            mapped = _KEY_MAP_CN.get(raw_key)
            if not mapped:
                continue
            if mapped in fm:
                continue  # format 1 already has this key, don't overwrite
            if mapped == "status":
                fm["status"] = _normalize_status(val)
            else:
                fm[mapped] = val

    return fm


_STATUS_MAP: dict[str, str] = {
    "进行中": "in_progress",
    "已完成": "done",
    "已取消": "cancelled",
    # Legacy English aliases
    "completed": "done",
    "proposed": "in_progress",
}


def _normalize_status(val: str) -> str:
    """Normalize quoted, case-insensitive status values to machine-readable keys."""
    scalar = _normalize_scalar(val)
    return _STATUS_MAP.get(scalar, scalar)


def _read_error(path: Path, exc: Exception, kind: str) -> dict[str, Any]:
    cause = exc.cause if isinstance(exc, DocumentReadError) else exc
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    return {
        "kind": kind,
        "status": "invalid",
        "error_code": "read_error",
        "path": rel,
        "detail": f"cannot read or decode UTF-8; inspect and repair file bytes ({cause})",
    }


def _normalize_scalar(val: str) -> str:
    """Normalize the simple quoted scalar subset used by project metadata."""
    scalar = val.strip()
    if len(scalar) >= 2 and scalar[0] == scalar[-1] and scalar[0] in ("'", '"'):
        scalar = scalar[1:-1].strip()
    return scalar.casefold()


# ---------------------------------------------------------------------------
# link extraction
# ---------------------------------------------------------------------------

def _extract_file_links(text: str) -> list[tuple[str, str, int]]:
    """Return (target_path, display_text, line_number) for every local file link.

    Strips code blocks, inline code, and HTML comments before extraction to
    avoid false positives from example links and commented-out references.
    Line numbers are preserved relative to the original text.
    """
    clean = _strip_noise(text)
    links: list[tuple[str, str, int]] = []
    for lineno, line in enumerate(clean.splitlines(), 1):
        for m in MARKDOWN_LINK_RE.finditer(line):
            target = m.group(2).strip()
            if target.startswith(("http://", "https://", "#")):
                continue
            links.append((target, m.group(1).strip(), lineno))
    return links


# ---------------------------------------------------------------------------
# dead-links
# ---------------------------------------------------------------------------

def _check_dead_links() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for doc_rel in _discover_doc_files():
        path = ROOT / doc_rel
        if not path.is_file():
            continue
        source_dir = path.parent
        try:
            text = _read(path)
        except (OSError, UnicodeDecodeError) as exc:
            results.append(_read_error(path, exc, "read_error"))
            continue
        for target, _label, lineno in _extract_file_links(text):
            resolved = _resolve(target, source_dir)
            # 目录不算死链（docs/plans/、docs/problems/bugfix/ 等目录链接）
            exists = resolved.exists()
            results.append({
                "kind": "dead_link",
                "status": "ok" if exists else "dead",
                "source": doc_rel,
                "line": lineno,
                "target": target,
            })
    return results


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------

def _structure_table_links() -> list[tuple[str, str, int]]:
    """Parse docs/STRUCTURE.md index table: return (rel_path, label, lineno)."""
    path = ROOT / "docs" / "STRUCTURE.md"
    if not path.is_file():
        return []
    entries: list[tuple[str, str, int]] = []
    in_table = False
    for lineno, line in enumerate(_lines(path), 1):
        stripped = line.strip()
        if stripped.startswith("|") and "---" not in stripped.replace(" ", ""):
            if not in_table:
                in_table = True
                continue
            for m in MARKDOWN_LINK_RE.finditer(line):
                target = m.group(2).strip()
                if target.startswith(("http://", "https://", "#")):
                    continue
                entries.append((target, m.group(1).strip(), lineno))
        elif in_table and not stripped.startswith("|"):
            in_table = False
    return entries


def _check_structure() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    if not _exists("docs/STRUCTURE.md"):
        return results

    try:
        index_entries = _structure_table_links()
    except (OSError, UnicodeDecodeError) as exc:
        return [_read_error(ROOT / "docs" / "STRUCTURE.md", exc, "structure")]
    # 索引表目标相对于 docs/（STRUCTURE.md 所在目录）；
    # 孤儿判定统一换算为仓库根相对路径再比较。
    indexed_paths = {"docs/" + e[0] for e in index_entries}

    # Check each indexed target exists.
    for target, _label, lineno in index_entries:
        if not _exists("docs/" + target):
            results.append({
                "kind": "structure",
                "status": "missing",
                "source": "docs/STRUCTURE.md",
                "line": lineno,
                "target": target,
            })
        else:
            results.append({
                "kind": "structure",
                "status": "ok",
                "source": "docs/STRUCTURE.md",
                "line": lineno,
                "target": target,
            })

    # Check for orphan files in docs/ not in index.
    docs_dir = ROOT / "docs"
    if docs_dir.is_dir():
        for f in sorted(docs_dir.rglob("*.md")):
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            if rel in indexed_paths:
                continue
            # Skip STRUCTURE.md itself — 索引表不登记自身。
            if rel == "docs/STRUCTURE.md":
                continue
            # Skip plan files — they are transient by design.
            if rel.startswith("docs/plans/"):
                continue
            # Skip audit-checklist itself.
            if rel == "docs/audit-checklist.md":
                continue
            # Skip bugfix docs — 逐篇索引由 maintain.py 派生到 MEMORY.md 索引段，
            # 与 plans/ 同理不逐篇登记进 STRUCTURE.md。
            if rel.startswith("docs/problems/bugfix/"):
                continue
            results.append({
                "kind": "structure",
                "status": "orphan",
                "source": "docs/STRUCTURE.md",
                "line": 0,
                "target": rel,
            })

    return results


# ---------------------------------------------------------------------------
# drift
# ---------------------------------------------------------------------------

def _drift_check() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    manifests = _find_manifests()
    if not manifests:
        return results

    manifest_text = ""
    for m in manifests:
        try:
            manifest_text += " " + _read(m).lower()
        except DocumentReadError as exc:
            results.append(_read_error(m, exc, "drift"))

    doc_text = ""
    for doc_rel in ["docs/overview.md", "docs/deployment.md"]:
        p = ROOT / doc_rel
        if p.is_file():
            try:
                doc_text += " " + _read(p).lower()
            except (OSError, UnicodeDecodeError) as exc:
                results.append(_read_error(p, exc, "drift"))

    # Doc mentions → check manifest.
    for tech, keywords in DRIFT_PATTERNS.items():
        in_docs = tech.lower() in doc_text or any(kw in doc_text for kw in keywords)
        if not in_docs:
            continue
        in_manifest = any(kw in manifest_text for kw in keywords)
        if not in_manifest:
            results.append({
                "kind": "drift",
                "status": "warn",
                "tech": tech,
                "detail": f'Docs mention "{tech}" but no matching dependency found in manifests',
            })
        else:
            results.append({
                "kind": "drift",
                "status": "ok",
                "tech": tech,
                "detail": f'"{tech}" found in both docs and manifests',
            })

    # Manifest has → doc silent.
    for tech, keywords in DRIFT_PATTERNS.items():
        in_manifest = any(kw in manifest_text for kw in keywords)
        if not in_manifest:
            continue
        in_docs = tech.lower() in doc_text or any(kw in doc_text for kw in keywords)
        if not in_docs:
            results.append({
                "kind": "drift",
                "status": "warn",
                "tech": tech,
                "detail": f'Manifest has "{keywords[0]}" but docs never mention "{tech}"',
            })

    return results


# ---------------------------------------------------------------------------
# misc checks
# ---------------------------------------------------------------------------

def _check_birth_record() -> list[dict[str, Any]]:
    small_path = "docs/initialization.md"
    completed_path = "docs/plans/completed/initialization.md"
    active_path = "docs/plans/active/initialization.md"
    candidates = [p for p in (small_path, completed_path, active_path) if _exists(p)]
    if len(candidates) > 1:
        sizes: list[str] = []
        for candidate in candidates:
            try:
                fm = _parse_frontmatter(_read(ROOT / candidate))
            except (OSError, UnicodeDecodeError):
                continue
            size = _normalize_scalar(fm["size"]) if "size" in fm else ""
            if size in ("medium", "large"):
                sizes.append(size)
        return [{
            "kind": "birth_record",
            "status": "conflict",
            "path": ", ".join(candidates),
            "sizes": sizes,
            "detail": "multiple initialization records exist; keep one canonical record",
        }]
    if not candidates:
        return [{
            "kind": "birth_record",
            "status": "missing",
            "path": f"{active_path}, {completed_path}, or {small_path}",
        }]

    candidate = candidates[0]
    if len(candidates) == 1:
        try:
            text = _read(ROOT / candidate)
        except (OSError, UnicodeDecodeError) as exc:
            return [_read_error(ROOT / candidate, exc, "birth_record")]
    if not text.strip():
        return [{
            "kind": "birth_record",
            "status": "invalid",
            "path": candidate,
            "detail": "initialization record is empty",
        }]

    fm = _parse_frontmatter(text)
    size_val = _normalize_scalar(fm["size"]) if "size" in fm else ""
    status_val = fm.get("status", "")
    row: dict[str, Any] = {
        "kind": "birth_record",
        "status": "found",
        "path": candidate,
        "size": size_val or ("small" if candidate == small_path else ""),
    }

    if "size" in fm and size_val not in ("small", "medium", "large"):
        row.update(status="invalid", detail=f"unknown size {fm['size']!r}; expected small, medium, or large")
    elif status_val and status_val not in ("in_progress", "done", "cancelled"):
        row.update(
            status="invalid",
            detail=f"unknown status {fm['status']!r}; expected in_progress, done, or cancelled",
        )
    elif candidate == completed_path and size_val == "small":
        row.update(status="invalid", detail="small birth record in plans/completed/ (should be docs/initialization.md)")
    elif candidate == small_path and size_val in ("medium", "large"):
        row.update(status="invalid", detail=f"{size_val} birth record in docs/ (should be {completed_path})")
    elif candidate == active_path and size_val and size_val not in ("medium", "large"):
        row.update(status="invalid", detail="active birth record must have size medium or large")
    elif candidate == active_path and status_val and status_val != "in_progress":
        row.update(status="invalid", detail="active birth record must have status in_progress")
    elif candidate == completed_path and status_val == "in_progress":
        row.update(status="invalid", detail="in_progress birth record belongs in plans/active/")
    elif not size_val or not status_val:
        row.update(
            status="warn",
            detail="legacy record missing size or status; compatible for history, not completion evidence",
        )
    else:
        row["detail"] = f"status: {status_val}"
    return [row]


def _check_line_budget() -> list[dict[str, Any]]:
    p = ROOT / "AGENTS.md"
    if not p.is_file():
        return [{"kind": "line_budget", "status": "missing", "lines": 0, "words": 0}]
    try:
        text = _read(p)
    except (OSError, UnicodeDecodeError) as exc:
        return [_read_error(p, exc, "line_budget")]
    line_count = len(text.splitlines())
    word_count = len(text.split())
    lines_ok = line_count <= 250
    words_ok = word_count <= 400
    if lines_ok and words_ok:
        status = "ok"
    else:
        status = "warn"
    return [{"kind": "line_budget", "status": status, "lines": line_count, "words": word_count}]


# ---------------------------------------------------------------------------
# memory
# ---------------------------------------------------------------------------

def _check_memory() -> list[dict[str, Any]]:
    """Check .agents/memory/ structure health.

    Small projects (no .agents/memory/ dir) are not an error — they skip.
    For projects with the directory, we verify:
    - MEMORY.md exists and is non-empty
    - AGENTS.md contains the pointer and inline section
    - Links in MEMORY.md resolve to existing files
    """
    results: list[dict[str, Any]] = []
    memory_rel = ".meta/memory" if SCRIPTS_DIR.parent.name == ".meta" or (ROOT / ".meta" / "memory").is_dir() else ".agents/memory"
    memory_dir = ROOT / memory_rel

    # Small projects: memory dir absence is OK
    if not memory_dir.is_dir():
        required_profile = next((
            row for row in _check_birth_record()
            if row.get("size") in ("medium", "large")
            or any(size in ("medium", "large") for size in row.get("sizes", []))
        ), None)
        if required_profile:
            profile_sizes = required_profile.get("sizes", [])
            profile_size = required_profile.get("size") or next(
                (size for size in profile_sizes if size in ("medium", "large")),
                "medium/large",
            )
            results.append({
                "kind": "memory",
                "status": "missing",
                "detail": f"{memory_rel}/ directory required by explicit {profile_size} profile",
            })
            return results
        results.append({
            "kind": "memory",
            "status": "missing" if memory_rel == ".meta/memory" else "skip",
            "detail": f"No {memory_rel}/ directory",
        })
        return results

    # Check MEMORY.md exists
    mem_index = memory_dir / "MEMORY.md"
    if not mem_index.is_file():
        results.append({
            "kind": "memory",
            "status": "missing",
            "detail": f"{memory_rel}/MEMORY.md missing",
        })
        return results

    # Check MEMORY.md is readable UTF-8 and contains non-whitespace content.
    try:
        memory_text = mem_index.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        results.append({
            "kind": "memory",
            "status": "invalid",
            "detail": f"{memory_rel}/MEMORY.md is not readable UTF-8",
        })
        return results
    if not memory_text.strip():
        results.append({
            "kind": "memory",
            "status": "empty",
            "detail": f"{memory_rel}/MEMORY.md is empty or whitespace-only",
        })
        return results

    # Check AGENTS.md contains memory pointer and inline section
    agents_md = ROOT / "AGENTS.md"
    if agents_md.is_file():
        try:
            content = _read(agents_md)
        except (OSError, UnicodeDecodeError) as exc:
            results.append(_read_error(agents_md, exc, "memory"))
            return results
        if f"{memory_rel}/MEMORY.md" not in content:
            results.append({
                "kind": "memory",
                "status": "unlinked",
                "detail": f"AGENTS.md missing pointer to {memory_rel}/MEMORY.md",
            })
        if "## 项目记忆" not in content:
            results.append({
                "kind": "memory",
                "status": "unlinked",
                "detail": "AGENTS.md missing inline memory section",
            })

    # Check referenced memory files exist
    for target, _label, lineno in _extract_file_links(memory_text):
        resolved = _resolve(target, mem_index.parent)
        if not resolved.is_file():
            results.append({
                "kind": "memory",
                "status": "dead_link",
                "source": f"{memory_rel}/MEMORY.md",
                "line": lineno,
                "target": target,
            })

    if not results:
        results.append({
            "kind": "memory",
            "status": "ok",
            "detail": f"{memory_rel}/ structure healthy",
        })

    return results


# ---------------------------------------------------------------------------
# plans — check for stale plans in docs/plans/active/
# ---------------------------------------------------------------------------

_STALE_DAYS = 30  # plans older than this without modification are candidates


def _check_plans() -> list[dict[str, Any]]:
    """Check docs/plans/active/ and docs/plans/completed/ for misplaced or stale plans.

    Flags:
    - STALE (status=stale): plan in active/ with done/completed/cancelled status
      or legacy blockquote metadata format — should be moved or reformatted.
    - MISPLACED (status=misplaced): plan in completed/ with in_progress status
      — should be in active/.
    - LINGER (status=linger): plan is older than _STALE_DAYS without
      recent modification — possible candidate for archival review.
    """
    results: list[dict[str, Any]] = []
    plans_root = ROOT / "docs" / "plans"
    if not plans_root.is_dir():
        return results

    now = datetime.now(timezone.utc).timestamp()

    # Statuses valid in each directory.
    _DIR_VALID: dict[str, set[str]] = {
        "active": {"in_progress"},
        "completed": {"done", "cancelled"},
    }

    for folder in ("active", "completed"):
        folder_path = plans_root / folder
        if not folder_path.is_dir():
            continue
        valid_statuses = _DIR_VALID[folder]

        for f in sorted(folder_path.glob("*.md")):
            if f.name == ".gitkeep":
                continue
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            try:
                text = _read(f)
            except (OSError, UnicodeDecodeError) as exc:
                results.append(_read_error(f, exc, "plans"))
                continue
            fm = _parse_frontmatter(text)
            status_val = fm.get("status", "")

            # Check 1: status not valid for this directory → misplaced or stale
            if status_val and status_val not in valid_statuses:
                target_dir = "completed/" if status_val in ("done", "cancelled") else "active/"
                kind = "stale" if folder == "active" else "misplaced"
                results.append({
                    "kind": "plans",
                    "status": kind,
                    "file": rel,
                    "detail": f'Frontmatter status="{status_val}" in {folder}/'
                              f' — move to docs/plans/{target_dir}',
                })
                continue

            # Check 2: legacy blockquote metadata format in active/ → stale
            if folder == "active" and not _FRONTMATTER_RE.match(text):
                if any(_BLOCKQUOTE_META_RE.match(line) for line in text.splitlines()[:10]):
                    results.append({
                        "kind": "plans",
                        "status": "stale",
                        "file": rel,
                        "detail": "Legacy blockquote metadata format — migrate to YAML frontmatter",
                    })
                    continue

            # Completed records are historical evidence; age does not invalidate them.
            # Active records only get a review hint when old.
            try:
                mtime = f.stat().st_mtime
                age_days = (now - mtime) / 86400
            except OSError:
                age_days = 0.0

            if folder == "active" and age_days > _STALE_DAYS:
                results.append({
                    "kind": "plans",
                    "status": "warn",
                    "file": rel,
                    "detail": f'File not modified in {int(age_days)} days'
                              f' (threshold: {_STALE_DAYS}d) — review status and progress',
                })
                continue

            # All clear
            results.append({
                "kind": "plans",
                "status": "ok",
                "file": rel,
                "detail": "",
            })

    return results


# ---------------------------------------------------------------------------
# eval record (R1) — validate explicitly enabled replay records
# ---------------------------------------------------------------------------

def _check_bugfix_eval_record() -> list[dict[str, Any]]:
    """R1: validate explicit eval records in fixed bugfix documents.

    Fixed docs require non-empty `eval_fixture`, `eval_command`,
    `eval_expect`, and `eval_last_scored` fields when `eval: scored`.
    `eval_score` is optional. Alternatively, `eval: skipped` requires a
    non-empty `eval_skip_reason`.

    Projects enable replay records explicitly; absence of eval is valid.
    The rule is independent of creation dates. Scan scope is
    docs/problems/bugfix/*.md excluding _template.md; a missing directory
    is a no-op.
    """
    results: list[dict[str, Any]] = []
    bugfix_dir = ROOT / "docs" / "problems" / "bugfix"
    if not bugfix_dir.is_dir():
        return results
    for f in sorted(bugfix_dir.glob("*.md")):
        if f.name == "_template.md":
            continue
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        try:
            fm = _parse_frontmatter(_read(f))
        except (OSError, UnicodeDecodeError) as exc:
            results.append(_read_error(f, exc, "eval_record"))
            continue
        if fm.get("status", "") != "fixed":
            continue
        eval_val = _normalize_scalar(str(fm.get("eval", "")))
        if not eval_val:
            continue
        skip_reason = _normalize_scalar(str(fm.get("eval_skip_reason", "")))
        scored_fields = ("eval_fixture", "eval_command", "eval_expect", "eval_last_scored")
        scored_complete = eval_val == "scored" and all(
            _normalize_scalar(str(fm.get(key, ""))) for key in scored_fields
        )
        if scored_complete or (eval_val == "skipped" and skip_reason):
            results.append({"kind": "eval_record", "status": "ok", "file": rel, "detail": ""})
        else:
            if eval_val == "skipped":
                detail = "eval: skipped requires eval_skip_reason"
            elif eval_val == "scored":
                missing = [key for key in scored_fields
                           if not _normalize_scalar(str(fm.get(key, "")))]
                detail = "eval: scored missing non-empty " + ", ".join(missing)
            else:
                detail = "explicit eval must be scored or skipped"
            results.append({"kind": "eval_record", "status": "error", "file": rel, "detail": detail})
    return results


# ---------------------------------------------------------------------------
# eval baseline (R2) — behavior-surface commits must be scored in the ledger
# ---------------------------------------------------------------------------

# 行为面清单：plan 显式枚举，不复用 GOV_PATTERNS 作为单一事实源——GOV_PATTERNS
# 在仓库有 5 处定义、2 套内容（.githooks/pre-commit 与 assets/hooks/pre-commit-*.sh
# 各异），运行时解析不成立。治理面（GOV_PATTERNS，提交时提醒人工复查）≠ 行为面
# （此处，强制 eval 记分）：两套词表语义不同，对照关系以本注释为准。
# 排除项及理由：assets/scripts/**、assets/hooks/**、.githooks/**、assets/plugins/**
# 由 pytest 门控、不改变 skill 产出质量，不入 eval 义务（强行记分是 Goodhart 诱因）；
# assets/pitch/** 非运行时产物。方法文档及记分账本不入被考对象。
_EVAL_BASELINE_REL = "evals/results.md"
_EVAL_LEGACY_REL = "assets/references/eval-baseline.md"
_EVAL_SURFACE_PATHS = [
    "AGENTS.md",
    "SKILL.md",
    "README.md",
    "assets/templates/zh",
    "assets/references",
]
_EVAL_SURFACE_EXCLUDE = ":(exclude)" + _EVAL_LEGACY_REL
_SHA40_RE = re.compile(r"\b[0-9a-f]{40}\b")
_SHA40_LINE_RE = re.compile(r"^[0-9a-f]{40}$")
_TABLE_ROW_DIFF_RE = re.compile(r"^[+-]\|.*\b[0-9a-f]{40}\b")


def _git_lines(*args: str) -> list[str]:
    """Run a git command in ROOT; return stdout lines (empty on failure)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return proc.stdout.splitlines()


def _check_eval_baseline(*, staged: bool = False) -> list[dict[str, Any]]:
    """R2: behavior-surface commits after the last ledger touch must be scored.

    Transitional mechanism — retires once a fixture-replay runner makes
    scoring continuous (see README 评测义务 and eval-baseline.md). Semantics:

    - Called explicitly by the source entry point, never target audit check.
      Prefer results.md with scored rows, otherwise the scored legacy ledger.
      Read errors fail rather than silently selecting another ledger.
    - anchor = newest commit whose diff on the selected ledger adds/removes
      score rows carrying a full SHA; prose-only edits of
      the ledger do not move the anchor. Writing a score row moves the
      anchor, so a commit that both changes behavior surface and records
      the score anchors itself — self-consistent.
    - Empty table (no data row carrying a full 40-hex SHA) → skip until
      the first record.
    - anchor SHA no longer reachable from HEAD (rebase/amend) → degraded
      skip + rebuild hint; no mtime fallback (philosophy #10).
    - behavior-surface commits after anchor: 1 → warn, >=2 → error.
    """
    if not (ROOT / ".git").exists():
        return [{
            "kind": "eval_baseline",
            "status": "skip",
            "detail": ".git absent — source results-ledger behavior-surface "
                      "scoring check not active",
        }]

    # Inspect the same content that the gate is checking. In pre-commit mode,
    # an unstaged score row must not cover the candidate staged commit.
    baseline = None
    for ledger_rel in (_EVAL_BASELINE_REL, _EVAL_LEGACY_REL):
        candidate = ROOT / ledger_rel
        try:
            if staged:
                proc = subprocess.run(
                    ["git", "-C", str(ROOT), "show", f":{ledger_rel}"],
                    capture_output=True, timeout=60,
                )
                if proc.returncode != 0:  # ledger absent from the index
                    continue
                lines = proc.stdout.decode("utf-8").splitlines()
            elif candidate.is_file():
                lines = _lines(candidate)
            else:
                continue
        except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired) as exc:
            return [_read_error(candidate, exc, "eval_baseline")]
        if any(_SHA40_RE.search(ln) for ln in lines if ln.lstrip().startswith("|")):
            baseline = candidate
            break
    if baseline is None:
        return [{
            "kind": "eval_baseline",
            "status": "skip",
            "detail": "no ledger has a scored row (full 40-hex SHA) — "
                      "skip until first record",
        }]
    # Only the active ledger's added score row covers a candidate commit.
    if staged and any(line.startswith("+") and _TABLE_ROW_DIFF_RE.match(line)
                      for line in _git_lines("diff", "--cached", "-U0", "--",
                                             baseline.relative_to(ROOT).as_posix())):
        return [{"kind": "eval_baseline", "status": "ok", "pending": 0,
                 "detail": "staged score row covers the candidate commit"}]
    # Per-commit diffs of the ledger: newest commit touching table rows is
    # the anchor. With `-p -U0` every diff line is prefixed (+/-/@/space/
    # header), so a bare 40-hex line can only be a commit header.
    anchor: str | None = None
    # Prefer the results ledger's history. The legacy method file is only a
    # migration fallback; subsequent method rewrites must not move the anchor.
    selected_rel = baseline.relative_to(ROOT).as_posix()
    history_paths = ((selected_rel, _EVAL_LEGACY_REL)
                     if selected_rel == _EVAL_BASELINE_REL else (selected_rel,))
    for ledger_rel in history_paths:
        current_sha: str | None = None
        touched_table = False
        for line in _git_lines("log", "--format=%H", "-p", "-U0", "--", ledger_rel):
            if _SHA40_LINE_RE.match(line):
                if current_sha is not None and touched_table:
                    anchor = current_sha
                    break
                current_sha = line
                touched_table = False
            elif _TABLE_ROW_DIFF_RE.match(line):
                touched_table = True
        if anchor is None and current_sha is not None and touched_table:
            anchor = current_sha
        if anchor is not None:
            break
    if anchor is None:
        return [{
            "kind": "eval_baseline",
            "status": "skip",
            "detail": "no commit found touching regression-table rows — "
                      "rebuild the baseline record",
        }]

    # History rewritten under the anchor (rebase/amend) → degraded skip.
    # git log only reports commits reachable from HEAD, so a recomputed
    # anchor is always reachable — this check is a defensive guard for
    # future changes (e.g. stored anchors) and documents the degraded
    # intent explicitly.
    reach = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", anchor, "HEAD"],
        capture_output=True, timeout=60,
    )
    if reach.returncode != 0:
        return [{
            "kind": "eval_baseline",
            "status": "skip",
            "detail": f"anchor {anchor[:12]} no longer reachable from HEAD "
                      "(history rewritten) — rebuild the baseline record",
        }]

    pending = [
        ln for ln in _git_lines(
            "log", "--format=%H", f"{anchor}..HEAD", "--",
            *_EVAL_SURFACE_PATHS, _EVAL_SURFACE_EXCLUDE,
        )
        if _SHA40_LINE_RE.match(ln)
    ]
    n = len(pending)
    if n == 0:
        return [{"kind": "eval_baseline", "status": "ok", "anchor": anchor, "pending": 0,
                 "detail": "no unscored behavior-surface commits"}]
    return [{
        "kind": "eval_baseline",
        "status": "warn" if n == 1 else "error",
        "anchor": anchor,
        "pending": n,
        "detail": f"{n} behavior-surface commit(s) after last ledger touch — "
                  f"run L1 and add a score row to {_EVAL_BASELINE_REL}",
    }]


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------

def _run_all() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for checker in (
        _check_dead_links, _check_structure, _drift_check, _check_birth_record,
        _check_line_budget, _check_memory, _check_plans,
        _check_bugfix_eval_record,
    ):
        try:
            results.extend(checker())
        except DocumentReadError as exc:
            results.append(_read_error(exc.document_path, exc, checker.__name__))
    return results


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

_STATUS_GLYPHS: dict[str, str] = {
    "ok":          "OK",
    "dead":        "DEAD",
    "missing":     "MISS",
    "orphan":      "ORPHAN",
    "drift":       "DRIFT",
    "undocumented":"UNDOC",
    "warn":        "WARN",
    "found":       "FOUND",
    "skip":        "SKIP",
    "empty":       "EMPTY",
    "unlinked":    "UNLINK",
    "stale":       "STALE",
    "linger":      "LINGER",
    "misplaced":   "MISPLACED",
    "invalid":     "INVALID",
    "error":       "ERROR",
}


def _format_text(results: list[dict[str, Any]], verbose: bool = False) -> str:
    lines_out: list[str] = []
    for r in results:
        if not verbose and r["status"] in ("ok", "found"):
            continue
        glyph = _STATUS_GLYPHS.get(r["status"], r["status"].upper())
        kind = r["kind"]
        if r["status"] == "invalid":
            lines_out.append(
                f"[{glyph:<6}] {r.get('path', r.get('file', ''))}: {r['detail']}"
            )
            continue

        if kind == "dead_link":
            lines_out.append(
                f"[{glyph:<6}] {r['source']}:{r['line']} -> {r['target']}"
            )
        elif kind == "structure":
            if r["status"] == "orphan":
                lines_out.append(
                    f"[{glyph:<6}] docs/STRUCTURE.md — not in index: {r['target']}"
                )
            elif r["status"] == "missing":
                lines_out.append(
                    f"[{glyph:<6}] docs/STRUCTURE.md:{r['line']} -> {r['target']} (file missing)"
                )
        elif kind == "drift":
            lines_out.append(f"[{glyph:<6}] {r['detail']}")
        elif kind == "birth_record":
            if r["status"] == "missing":
                lines_out.append(f"[{glyph:<6}] Birth record missing: {r['path']}")
            else:
                detail = f" — {r['detail']}" if r.get("detail") else ""
                lines_out.append(f"[{glyph:<6}] Birth record: {r['path']}{detail}")
        elif kind == "line_budget":
            if r["status"] == "missing":
                lines_out.append("[MISS  ] AGENTS.md not found")
            elif r["status"] == "invalid":
                lines_out.append(f"[{glyph:<6}] {r['path']}: {r['detail']}")
            elif r["status"] == "warn":
                lines_out.append(
                    f"[WARN   ] AGENTS.md: {r['lines']} lines / {r['words']} words (limit 250/400)"
                )
            else:
                lines_out.append(
                    f"[OK    ] AGENTS.md: {r['lines']} lines / {r['words']} words (limit 250/400)"
                )
        elif kind == "memory":
            if r["status"] == "skip":
                lines_out.append(f"[SKIP   ] memory ({r['detail']})")
            elif r["status"] == "ok":
                if verbose:
                    lines_out.append("[OK    ] memory structure healthy")
            elif r["status"] == "dead_link":
                lines_out.append(
                    f"[DEAD   ] {r['source']}:{r['line']} -> {r['target']}"
                )
            else:
                lines_out.append(f"[{glyph:<6}] memory: {r['detail']}")
        elif kind == "plans":
            if r["status"] == "stale":
                lines_out.append(f"[STALE  ] {r['file']}: {r['detail']}")
            elif r["status"] == "misplaced":
                lines_out.append(f"[MISPL  ] {r['file']}: {r['detail']}")
            elif r["status"] == "linger":
                lines_out.append(f"[LINGER ] {r['file']}: {r['detail']}")
            elif r["status"] == "warn":
                lines_out.append(f"[WARN   ] {r['file']}: {r['detail']}")
            elif r["status"] == "ok" and verbose:
                lines_out.append(f"[OK    ] {r['file']}")
        elif kind == "eval_record":
            if r["status"] == "ok" and verbose:
                lines_out.append(f"[OK    ] eval record: {r['file']}")
            else:
                lines_out.append(f"[{glyph:<6}] eval record: {r['file']} — {r['detail']}")
        elif kind == "eval_baseline":
            lines_out.append(f"[{glyph:<6}] source results ledger: {r['detail']}")
        elif r.get("status") == "invalid":
            lines_out.append(f"[{glyph:<6}] {r.get('path', r.get('file', ''))}: {r['detail']}")
    return "\n".join(lines_out)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def _cmd_check(args: argparse.Namespace) -> None:
    results = _run_all()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(_format_text(results, verbose=args.verbose))

    # warn is advisory (eval_baseline R2 with one unscored behavior-surface
    # commit, AGENTS.md line_budget over budget) and tolerated for exit-code
    # purposes; error still fails. This deliberately relaxes line_budget
    # from exit-1 to pass-with-hint — an accepted trade-off recorded in
    # README「评测义务」.
    has_issues = any(r["status"] not in ("ok", "found", "skip", "warn") for r in results)
    if has_issues:
        raise SystemExit(1)


def _cmd_dead_links(args: argparse.Namespace) -> None:
    results = _check_dead_links()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(_format_text(results, verbose=args.verbose))
    if any(r["status"] != "ok" for r in results):
        raise SystemExit(1)


def _cmd_structure(args: argparse.Namespace) -> None:
    results = _check_structure()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(_format_text(results, verbose=args.verbose))
    if any(r["status"] != "ok" for r in results):
        raise SystemExit(1)


def _cmd_drift(args: argparse.Namespace) -> None:
    results = _drift_check()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(_format_text(results, verbose=args.verbose))
    if any(r["status"] not in ("ok", "warn") for r in results):
        raise SystemExit(1)


def _cmd_plans(args: argparse.Namespace) -> None:
    results = _check_plans()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(_format_text(results, verbose=args.verbose))
    has_issues = any(r["status"] not in ("ok", "warn") for r in results)
    if has_issues:
        raise SystemExit(1)


def _cmd_memory(args: argparse.Namespace) -> None:
    results = _check_memory()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(_format_text(results, verbose=args.verbose))
    if any(r["status"] not in ("ok", "skip") for r in results):
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="init-agent-docs document consistency mechanical checks"
    )
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="Run all checks")
    p_check.add_argument("--json", action="store_true", help="Output JSON")
    p_check.add_argument("--verbose", action="store_true", help="Show OK entries")
    p_check.set_defaults(func=_cmd_check)

    p_dead = sub.add_parser("dead-links", help="Dead link check only")
    p_dead.add_argument("--json", action="store_true", help="Output JSON")
    p_dead.add_argument("--verbose", action="store_true", help="Show OK entries")
    p_dead.set_defaults(func=_cmd_dead_links)

    p_struct = sub.add_parser("structure", help="STRUCTURE index check only")
    p_struct.add_argument("--json", action="store_true", help="Output JSON")
    p_struct.add_argument("--verbose", action="store_true", help="Show OK entries")
    p_struct.set_defaults(func=_cmd_structure)

    p_drift = sub.add_parser("drift", help="Dependency drift check only")
    p_drift.add_argument("--json", action="store_true", help="Output JSON")
    p_drift.add_argument("--verbose", action="store_true", help="Show OK entries")
    p_drift.set_defaults(func=_cmd_drift)

    p_mem = sub.add_parser("memory", help="Memory structure check only")
    p_mem.add_argument("--json", action="store_true", help="Output JSON")
    p_mem.add_argument("--verbose", action="store_true", help="Show OK entries")
    p_mem.set_defaults(func=_cmd_memory)

    p_plans = sub.add_parser("plans", help="Check for stale/unarchived plans only")
    p_plans.add_argument("--json", action="store_true", help="Output JSON")
    p_plans.add_argument("--verbose", action="store_true", help="Show OK entries")
    p_plans.set_defaults(func=_cmd_plans)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(1)
    args.func(args)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    main(sys.argv[1:])

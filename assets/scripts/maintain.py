"""maintain.py — 文档体系自动化维护管线（init-agent-docs，中型及以上项目）。

每次维护执行：
1. 重建 .agents/memory/MEMORY.md 的索引标记段
   （agent 只负责记忆的沉淀与检索；索引是纯派生信息，由本脚本机械维护。
    索引覆盖两类经验载体：.agents/memory/ 记忆条目 + docs/problems/bugfix/ 文档——
    后者是经验检索统一入口的一部分，bugfix 目录不存在时自动跳过）
2. 运行 audit.py check（死链 / 结构完整性 / 依赖漂移 / 记忆健康）
3. 记忆活性统计（30 天未更新预警，统计范围含 bugfix 文档）
4. 审计触发器（距上次审计裁决超过 30 天则 WARN 提醒；机械化的是"该审计了"，
   不是"文档是否陈旧"——治理文档正确性是事件驱动的，mtime 对比只会产生假警报）
5. 近期上下文摘要（git log + CHANGELOG 标题树，辅助 agent 快速恢复脉络）

用法：
    python scripts/maintain.py                 # 完整维护：重建索引 + 全部检查 + 报告
    python scripts/maintain.py --check         # 只读校验（不修改文件），异常时退出码非 0
    python scripts/maintain.py --memory-index  # 仅重建 MEMORY.md 索引标记段
    python scripts/maintain.py --memory-search QUERY --limit 5  # 有界经验检索

无第三方依赖。小型项目（无 .agents/memory/ 目录）自动跳过记忆相关步骤。
"""

from __future__ import annotations

import argparse
import heapq
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Supports <project_root>/scripts/ and <project_root>/.meta/scripts/.
SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent.parent if SCRIPTS_DIR.parent.name == '.meta' else SCRIPTS_DIR.parent
SCRIPTS_REL = '.meta/scripts' if SCRIPTS_DIR.parent.name == '.meta' else 'scripts'
MEMORY_REL = ".meta/memory" if SCRIPTS_DIR.parent.name == ".meta" or (ROOT / ".meta" / "memory").is_dir() else ".agents/memory"
MEMORY_DIR = ROOT / MEMORY_REL
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
BUGFIX_DIR = ROOT / "docs" / "problems" / "bugfix"
# 索引段中 bugfix 条目的链接前缀：相对当前 memory/MEMORY.md 所在目录解析
# （audit.py 死链检查按链接所在文件自身目录解析相对路径）
BUGFIX_LINK_PREFIX = "../../docs/problems/bugfix"

INDEX_START = "<!-- memory-index:start -->"
INDEX_END = "<!-- memory-index:end -->"
STALE_DAYS = 30
AUDIT_CHECKLIST = ROOT / "docs" / "audit-checklist.md"
AUDIT_STALE_DAYS = 30
MAX_TITLE_LEN = 60
GIT_LOG_LIMIT = 10
REPO_GRAPH_MANIFEST = ROOT / ".agents" / "repo-graph" / "manifest.json"


def _is_git_repo() -> bool:
    """Detect the target root's Git capability without probing ancestors."""
    return (ROOT / ".git").exists()

_REBUILT_LINE_RE = re.compile(r"^> 最近重建：.*\n?", re.MULTILINE)


# ---------------------------------------------------------------------------
# memory index
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _memory_files() -> list[Path]:
    if not MEMORY_DIR.is_dir():
        return []
    return sorted(
        p for p in MEMORY_DIR.rglob("*.md")
        if p.name != "MEMORY.md" and "__pycache__" not in p.parts
    )


def _memory_utf8_problem(
    memory_files: list[Path] | None = None,
    bugfix_files: list[Path] | None = None,
) -> str | None:
    """Return the first unreadable memory Markdown path, if any."""
    paths = ([MEMORY_INDEX] if MEMORY_INDEX.is_file() else []) + (
        _memory_files() if memory_files is None else memory_files
    ) + (_bugfix_files() if bugfix_files is None else bugfix_files)
    for path in paths:
        try:
            path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return str(path.relative_to(ROOT)).replace("\\", "/")
    return None


def _entry_title_from_text(text: str, fallback_stem: str) -> str:
    """First ATX heading, else first non-empty line, else filename stem.

    跳过开头的 YAML frontmatter 块（--- ... ---），否则 frontmatter 文档
    的标题回退会取到 "---" 分隔线本身。
    """
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1:]
                break
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^#+\s*(.+)$", stripped)
        title = (m.group(1) if m else stripped).strip()
        return title[:MAX_TITLE_LEN]
    return fallback_stem


def _entry_title(path: Path) -> str:
    """Read-once wrapper retained for external callers/tests."""
    try:
        return _entry_title_from_text(_read(path), path.stem)
    except (OSError, UnicodeDecodeError):
        return path.stem


def _fmt_date(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


class _ReverseKey:
    """Wrap a match key so a min-heap keeps the largest key at the root."""

    __slots__ = ("key",)

    def __init__(self, key):
        self.key = key

    def __lt__(self, other: "_ReverseKey") -> bool:
        return self.key > other.key


def _bounded_push(heap: list[_ReverseKey], key: tuple, limit: int) -> None:
    """Keep at most ``limit`` smallest keys in ``heap`` (never grows past it)."""
    if limit <= 0:
        return
    if len(heap) < limit:
        heapq.heappush(heap, _ReverseKey(key))
    elif key < heap[0].key:
        heapq.heapreplace(heap, _ReverseKey(key))


def _casefold_index_to_original(text: str, target: int) -> int:
    """Map a folded index to its source index, stopping at ``target``.

    Used only for already-matched bodies whose casefold length differs from the
    original (``ß`` -> ``ss``, ``İ`` -> ``i\\u0307``). It scans forward until
    the requested folded offset is reached and builds no mapping table.
    """
    if target <= 0:
        return 0
    folded_pos = 0
    for index, char in enumerate(text):
        if folded_pos >= target:
            return index
        next_pos = folded_pos + len(char.casefold())
        if next_pos > target:
            return index
        folded_pos = next_pos
    return len(text)


_FRONTMATTER_BODY_RE = re.compile(
    r"\A---\s*\n.*?\n---[^\S\n]*(?:\n|$)", re.DOTALL
)


def _split_frontmatter_body(text: str) -> tuple[str, str]:
    match = _FRONTMATTER_BODY_RE.match(text)
    if match is None:
        return "", text
    return text[:match.end()], text[match.end():]


def search_memory(query: str, limit: int) -> int:
    """Search all retained entries; bound output and candidate memory."""
    terms = list(dict.fromkeys(query.casefold().split()))
    if not terms:
        print("请输入非空检索关键词。")
        return 1
    heap: list[_ReverseKey] = []
    total_matches = 0
    error_count = 0
    error_samples: list[str] = []
    for path in _memory_files() + _bugfix_files():
        try:
            text = _read(path)
        except (OSError, UnicodeDecodeError):
            error_count += 1
            if len(error_samples) < 5:
                error_samples.append(path.relative_to(ROOT).as_posix())
            continue
        # Fold each component once; never re-read for a missing title.
        title = _frontmatter_value(text, "title") or _entry_title_from_text(text, path.stem)
        title_cf = title.casefold()
        rel = path.relative_to(ROOT).as_posix()
        rel_cf = rel.casefold()
        head, body = _split_frontmatter_body(text)
        head_cf = head.casefold()
        body_cf = body.casefold()
        score = sum(
            term in rel_cf or term in head_cf or term in body_cf for term in terms
        )
        if not score:
            continue
        score += sum(term in title_cf for term in terms)
        # Match the retained full entry, but show experience prose rather than
        # YAML metadata. Title/tag-only matches fall back to the body's start.
        positions = [body_cf.find(term) for term in terms]
        min_pos = min((p for p in positions if p >= 0), default=0)
        if min_pos and len(body_cf) != len(body):
            original_pos = _casefold_index_to_original(body, min_pos)
        else:
            original_pos = min_pos
        start = max(0, original_pos - 40)
        excerpt = " ".join(body[start:start + 160].split())
        total_matches += 1
        _bounded_push(
            heap, (-score, rel, title[:MAX_TITLE_LEN], excerpt), limit
        )
    shown = sorted(wrapper.key for wrapper in heap)
    print(f"命中 {total_matches} 条；显示 {len(shown)} 条；截断：{'是' if total_matches > limit else '否'}。链接相对项目根。")
    for _, rel, title, excerpt in shown:
        print(f"- [{title}]({rel}) — {excerpt}")
    if not total_matches:
        print("未找到相关经验；可换关键词或按需读取完整索引。")
    if error_count:
        print(f"检索不完整：{error_count} 个文件无法读取 UTF-8：" + ", ".join(error_samples))
    return 1 if error_count else 0


# ---------------------------------------------------------------------------
# bugfix index (docs/problems/bugfix/)
# ---------------------------------------------------------------------------

def _bugfix_files() -> list[Path]:
    """Bugfix 文档清单；`_` 开头的文件（如 _template.md）是模板，不入索引。"""
    if not BUGFIX_DIR.is_dir():
        return []
    return sorted(
        p for p in BUGFIX_DIR.glob("*.md")
        if not p.name.startswith("_") and "__pycache__" not in p.parts
    )


def _frontmatter_value(text: str, key: str) -> str | None:
    """从文件开头的 YAML frontmatter 提取标量字段（零依赖，只认 `key: value` 行）。"""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    # 只认同行标量；空值返回 None（\s 会吞换行导致串读到下一行）
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", text[3:end], re.MULTILINE)
    if not m or not m.group(1):
        return None
    return m.group(1).strip("\"'")


def _bugfix_meta_from_text(text: str, fallback_stem: str) -> dict[str, str]:
    """提取索引行所需字段；frontmatter 缺失时回退到标题启发式。"""
    meta: dict[str, str] = {}
    for key in ("title", "status", "severity", "liveness", "updated_at", "created_at"):
        value = _frontmatter_value(text, key)
        if value:
            meta[key] = value
    meta.setdefault("title", _entry_title_from_text(text, fallback_stem))
    return meta


def _bugfix_meta(path: Path) -> dict[str, str]:
    """Read-once wrapper retained for external callers/tests."""
    try:
        text = _read(path)
    except OSError:
        return {"title": path.stem}
    return _bugfix_meta_from_text(text, path.stem)


def _load_index_entries(
    memory_paths: list[Path], bugfix_paths: list[Path]
) -> tuple[list[dict], list[dict], Path | None]:
    """Read every index source exactly once (one stat + one read per file).

    Returns lightweight metadata only; the entry text is released immediately.
    The third item is the first file that cannot be read as UTF-8, preserving
    the caller's `invalid` diagnostic path.
    """
    memory_entries: list[dict] = []
    for path in memory_paths:
        try:
            mtime = path.stat().st_mtime
            text = _read(path)
        except (OSError, UnicodeDecodeError):
            return [], [], path
        memory_entries.append({
            "path": path,
            "mtime": mtime,
            "title": _entry_title_from_text(text, path.stem),
            "liveness": _frontmatter_value(text, "liveness"),
        })

    bugfix_entries: list[dict] = []
    for path in bugfix_paths:
        try:
            mtime = path.stat().st_mtime
            text = _read(path)
        except (OSError, UnicodeDecodeError):
            return memory_entries, [], path
        bugfix_entries.append({
            "path": path,
            "mtime": mtime,
            "meta": _bugfix_meta_from_text(text, path.stem),
        })
    return memory_entries, bugfix_entries, None


def _render_index_section(
    files: list[dict], bugfix: list[dict]
) -> str:
    """Render the marker content from already-loaded metadata."""
    lines = [
        f"> 本段由 `python {SCRIPTS_REL}/{Path(__file__).name}` 自动重建，禁止手工编辑。",
        f"> 最近重建：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    if not files and not bugfix:
        lines.append("（暂无记忆条目）")
        return "\n".join(lines).rstrip()

    groups: dict[str, list[dict]] = {}
    for entry in files:
        rel = entry["path"].relative_to(MEMORY_DIR)
        group = rel.parts[0] if len(rel.parts) > 1 else "未分类"
        groups.setdefault(group, []).append(entry)

    for group in sorted(groups):
        lines.append(f"### {group}")
        entries = sorted(groups[group], key=lambda entry: entry["mtime"], reverse=True)
        for entry in entries:
            path = entry["path"]
            rel = str(path.relative_to(MEMORY_DIR)).replace("\\", "/")
            line = (
                f"- [{path.name}]({rel}) — {entry['title']} · 更新于 {_fmt_date(entry['mtime'])}"
            )
            # 活性标记：有 frontmatter liveness 时追加；无 frontmatter 的旧记忆文件不追加（向后兼容）
            if entry["liveness"]:
                line += f" · {entry['liveness']}"
            lines.append(line)
        lines.append("")

    if bugfix:
        lines.append("### bugfix（docs/problems/bugfix/）")
        entries = sorted(bugfix, key=lambda entry: entry["mtime"], reverse=True)
        for entry in entries:
            path = entry["path"]
            meta = entry["meta"]
            flags = " · ".join(
                meta[k] for k in ("status", "severity", "liveness") if meta.get(k)
            )
            date = meta.get("updated_at") or meta.get("created_at") or _fmt_date(entry["mtime"])
            line = f"- [{meta['title'][:MAX_TITLE_LEN]}]({BUGFIX_LINK_PREFIX}/{path.name})"
            if flags:
                line += f" — {flags}"
            line += f" · 更新于 {date}"
            lines.append(line)
        lines.append("")
    return "\n".join(lines).rstrip()


def build_index_section() -> str:
    """Render the content that belongs between the index markers."""
    files = _memory_files()
    bugfix = _bugfix_files()
    memory_entries, bugfix_entries, invalid = _load_index_entries(files, bugfix)
    if invalid is not None:
        raise OSError(f"unreadable memory source: {invalid}")
    return _render_index_section(memory_entries, bugfix_entries)


def _normalize(text: str) -> str:
    """Strip the volatile rebuild timestamp so content comparison is stable."""
    return _REBUILT_LINE_RE.sub("", text)


def _splice_index(text: str, section: str) -> str | None:
    """Return updated MEMORY.md text, or None if markers are absent."""
    start = text.find(INDEX_START)
    end = text.find(INDEX_END)
    if start == -1 or end == -1 or end < start:
        return None
    end += len(INDEX_END)
    return text[:start] + INDEX_START + "\n" + section + "\n" + INDEX_END + text[end:]


def rebuild_memory_index(
    *, check_only: bool, memory_files: list[Path] | None = None,
    bugfix_files: list[Path] | None = None,
) -> tuple[str, str]:
    """Rebuild the MEMORY.md index marker section.

    Returns (status, detail); status ∈
    ok / rebuilt / stale / missing / no-markers / invalid / skip.
    ``memory_files`` / ``bugfix_files`` let run_full reuse one enumeration.
    """
    # A knowledge base has exactly one index writer: memory_index.py. Its
    # UTF-8 preflight stays separate from the non-KB single-read pipeline.
    indexer = SCRIPTS_DIR / "memory_index.py"
    if MEMORY_REL == ".meta/memory":
        if MEMORY_DIR.is_dir():
            invalid_path = _memory_utf8_problem(memory_files, bugfix_files)
            if invalid_path:
                return "invalid", f"{invalid_path} is not readable UTF-8; repair this file before rebuilding"
        if not MEMORY_INDEX.is_file() or not indexer.is_file():
            return "missing", ".meta/memory/MEMORY.md or memory_index.py missing"
        result = _run_script(f"{SCRIPTS_REL}/memory_index.py", *(["--check"] if check_only else []))
        if result is None:
            return "missing", "knowledge-base memory_index.py not available"
        rc, out = result
        return ("ok" if rc == 0 else ("stale" if check_only else "missing")), out or "knowledge-base memory index"
    if not MEMORY_DIR.is_dir():
        return "skip", "no .agents/memory/ directory (small project)"

    files = _memory_files() if memory_files is None else memory_files
    bugfix = _bugfix_files() if bugfix_files is None else bugfix_files

    current: str | None = None
    if MEMORY_INDEX.is_file():
        try:
            current = _read(MEMORY_INDEX)
        except (OSError, UnicodeDecodeError):
            invalid_path = MEMORY_INDEX.relative_to(ROOT).as_posix()
            return "invalid", f"{invalid_path} is not readable UTF-8; repair this file before rebuilding"

    memory_entries, bugfix_entries, invalid = _load_index_entries(files, bugfix)
    if invalid is not None:
        invalid_path = invalid.relative_to(ROOT).as_posix()
        return "invalid", f"{invalid_path} is not readable UTF-8; repair this file before rebuilding"
    if current is None:
        return "missing", f"{MEMORY_REL}/MEMORY.md not found"

    updated = _splice_index(current, _render_index_section(memory_entries, bugfix_entries))
    if updated is None:
        return "no-markers", f"MEMORY.md missing {INDEX_START} / {INDEX_END} markers"
    if _normalize(updated) == _normalize(current):
        return "ok", "memory index up to date"
    if check_only:
        return "stale", f"memory index out of date — run: python {SCRIPTS_REL}/{Path(__file__).name} --memory-index"
    MEMORY_INDEX.write_text(updated, encoding="utf-8", newline="\n")
    return "rebuilt", "memory index rebuilt"


# ---------------------------------------------------------------------------
# memory staleness
# ---------------------------------------------------------------------------

def _memory_last_update_ts(
    files: list[Path], bugfix_files: list[Path] | None = None
) -> float:
    """Last memory-update timestamp.

    git 不保留 mtime（fresh clone / checkout 会把 mtime 刷成当前时间），
    因此优先取 git 最后提交时间；非 git 环境回退到文件 mtime。
    """
    if _is_git_repo():
        try:
            proc = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--",
                 MEMORY_REL + "/", "docs/problems/bugfix/"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return float(proc.stdout.strip())
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
    pool = files + (bugfix_files if bugfix_files is not None else _bugfix_files())
    if not pool:
        return 0.0
    return max(p.stat().st_mtime for p in pool)


def memory_staleness(
    memory_files: list[Path] | None = None,
    bugfix_files: list[Path] | None = None,
) -> tuple[str, str]:
    """Returns (status, detail); status ∈ ok / stale / empty / skip."""
    if not MEMORY_DIR.is_dir():
        return "skip", "no .agents/memory/ directory (small project)"
    files = _memory_files() if memory_files is None else memory_files
    bugfix = _bugfix_files() if bugfix_files is None else bugfix_files
    if not files and not bugfix:
        return "empty", "no memory entries yet — 目录存在但从未沉淀记忆"
    age = datetime.now() - datetime.fromtimestamp(_memory_last_update_ts(files, bugfix))
    total = len(files) + len(bugfix)
    time_source = "文件时间" if not _is_git_repo() else "git"
    if age > timedelta(days=STALE_DAYS):
        return (
            "stale",
            f"memory untouched for {age.days} days (> {STALE_DAYS}) — "
            "沉淀新记忆或考虑裁剪记忆系统",
        )
    return "ok", f"newest memory update {age.days}d ago ({total} entries, 含 {len(bugfix)} bugfix, {time_source})"


def audit_recency() -> tuple[str, str]:
    """审计触发器：距上次审计裁决超过阈值则提醒（WARN，不阻塞）。

    机械化的是"该做审计了"这个提醒，不是"文档是否陈旧"——治理文档的
    正确性是事件驱动的（环境变了才需要改），mtime 对比会产生假警报并
    诱发凑数编辑（Goodhart）。状态唯一来源是 audit-checklist.md 末尾
    「审计记录」段的日期：裁决过就追加记录，"已判断 = 已销警"。

    Returns (status, detail); status ∈ ok / warn / skip / invalid.
    """
    if not AUDIT_CHECKLIST.is_file():
        return "skip", "no docs/audit-checklist.md"
    try:
        text = _read(AUDIT_CHECKLIST)
    except (OSError, UnicodeDecodeError) as exc:
        return "invalid", f"{AUDIT_CHECKLIST.relative_to(ROOT).as_posix()}: cannot read or decode UTF-8; inspect and repair file bytes ({exc})"
    marker = "## 审计记录"
    section = text[text.find(marker):] if marker in text else text
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", section)
    if not dates:
        return (
            "warn",
            "审计记录段无任何日期——从未记录审计，请按 docs/audit-checklist.md 执行首次裁决",
        )
    last = max(datetime.strptime(d, "%Y-%m-%d") for d in dates)
    age = (datetime.now() - last).days
    if age > AUDIT_STALE_DAYS:
        return (
            "warn",
            f"距上次审计 {age} 天（> {AUDIT_STALE_DAYS}）——请按 docs/audit-checklist.md "
            "逐项裁决：过时就更新/删除，仍准确则只需在审计记录追加当日条目",
        )
    return "ok", f"last audit {age}d ago ({last.strftime('%Y-%m-%d')})"


# ---------------------------------------------------------------------------
# delegated checks (audit.py)
# ---------------------------------------------------------------------------

def _run_script(rel: str, *args: str) -> tuple[int, str] | None:
    """Run a sibling script; None means the script is absent."""
    script = ROOT / rel
    if not script.is_file():
        return None
    try:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 2, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _run_script_split(rel: str, *args: str) -> tuple[int, str, str] | None:
    """Run a sibling script with separate stdout/stderr streams."""
    script = ROOT / rel
    if not script.is_file():
        return None
    try:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 2, "", str(exc)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _run_audit_in_process(
    repo_graph_prefetched: tuple[int, str] | None = None,
) -> tuple[int, str] | None:
    """Load sibling audit.py and run its check in this process.

    Returns None when audit.py is absent (same as the subprocess "skip" path),
    ``(2, str(exc))`` on load/execution failure, and audit's own
    ``(exit_code, text)`` on success. The synthesized module entry is removed
    and bytecode writing is disabled so maintenance leaves no residue.
    """
    script = SCRIPTS_DIR / "audit.py"
    if not script.is_file():
        return None
    module_name = "_iad_maintain_audit"
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        return 2, f"cannot load {SCRIPTS_REL}/audit.py"
    module = importlib.util.module_from_spec(spec)
    prior_dont_write = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        runner = getattr(module, "run_check_in_process", None)
        if runner is None:
            return 2, f"{SCRIPTS_REL}/audit.py lacks run_check_in_process"
        prior_root = getattr(module, "ROOT", None)
        prior_scripts_dir = getattr(module, "SCRIPTS_DIR", None)
        prior_scripts_rel = getattr(module, "SCRIPTS_REL", None)
        try:
            module.ROOT = ROOT
            module.SCRIPTS_DIR = SCRIPTS_DIR
            if prior_scripts_rel is not None:
                module.SCRIPTS_REL = SCRIPTS_REL
            return runner(repo_graph_prefetched=repo_graph_prefetched)
        finally:
            module.ROOT = prior_root
            module.SCRIPTS_DIR = prior_scripts_dir
            if prior_scripts_rel is not None:
                module.SCRIPTS_REL = prior_scripts_rel
    except (Exception, SystemExit) as exc:
        return 2, str(exc)
    finally:
        sys.dont_write_bytecode = prior_dont_write
        sys.modules.pop(module_name, None)


def refresh_repo_graph(
    *, check_only: bool, raw_out: dict | None = None
) -> tuple[str, str] | None:
    """Refresh an already initialized repo graph; never create the opt-in.

    Returns None when .agents/repo-graph/manifest.json is absent, so default
    maintenance stays silent and side-effect free for projects that never ran
    ``repo_graph.py build``. JSON success is parsed from stdout only; stderr
    warnings do not change the success decision.

    ``raw_out`` receives ``{"returncode": rc, "stdout": stdout}`` whenever the
    repo graph script actually ran. run_full --check hands that raw result to
    audit.py so both layers apply the identical verdict.
    """
    if not REPO_GRAPH_MANIFEST.is_file():
        return None
    rel = f"{SCRIPTS_REL}/repo_graph.py"
    if not (ROOT / rel).is_file():
        return "invalid", f"repo graph is initialized but {rel} is missing"
    args = ("check", "--json") if check_only else ("build", "--json")
    result = _run_script_split(rel, *args)
    if result is None:
        return "invalid", f"repo graph is initialized but {rel} is not available"
    rc, stdout, stderr = result
    if raw_out is not None:
        raw_out["returncode"] = rc
        raw_out["stdout"] = stdout
    payload: dict = {}
    try:
        parsed = json.loads(stdout)
        payload = parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, RecursionError):
        payload = {}
    status = payload.get("status")
    error = str(payload.get("error") or "")
    detail = str(payload.get("detail") or "")
    if error and error not in detail:
        detail = f"{error}: {detail}" if detail else error
    if rc == 0 and status == "ok":
        if check_only:
            return "ok", f"repo graph: {detail or 'repo graph is fresh'}"
        return "ok", detail or "repo graph rebuilt"
    if not check_only and rc == 0 and status == "built":
        return "ok", detail or "repo graph rebuilt"
    if status == "stale":
        message = f"{detail or 'repo graph is stale'} — run: python {rel} build"
        if check_only:
            message = f"repo graph: {message}"
        return "stale", message
    reason = detail or stdout or f"exit {rc}"
    if stderr:
        reason = f"{reason} (stderr: {stderr[:300]})"
    return "invalid", f"repo graph: {reason}"


# ---------------------------------------------------------------------------
# recent-context digest
# ---------------------------------------------------------------------------

def _git_recent(limit: int = GIT_LOG_LIMIT) -> list[str]:
    if not _is_git_repo():
        return []
    try:
        proc = subprocess.run(
            ["git", "log", "--oneline", f"-{limit}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _changelog_recent() -> str | None:
    result = _run_script(f"{SCRIPTS_REL}/changelog.py", "recent", "--days", "30")
    if result is None:
        return None
    rc, out = result
    return out if rc == 0 and out else None


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

_GLYPHS = {
    "ok": "OK",
    "rebuilt": "REBUILD",
    "stale": "STALE",
    "missing": "MISS",
    "invalid": "INVALID",
    "no-markers": "NOMARK",
    "empty": "EMPTY",
    "skip": "SKIP",
    "fail": "FAIL",
    "warn": "WARN",
}


def _line(status: str, detail: str) -> str:
    return f"[{_GLYPHS.get(status, status.upper()):<8}] {detail}"


def run_full(*, check_only: bool) -> int:
    failures = 0
    print("== maintain.py 文档体系维护 ==")
    if check_only:
        print("（只读校验模式，不修改任何文件）")

    # Enumerate once for any existing memory directory; index rebuild and
    # activity stats share the lists. KB preflight reuses them as well, and a
    # small project without the directory never scans bugfix files.
    memory_files = None
    bugfix_files = None
    if MEMORY_DIR.is_dir():
        memory_files = _memory_files()
        bugfix_files = _bugfix_files()

    idx_status, idx_detail = rebuild_memory_index(
        check_only=check_only, memory_files=memory_files, bugfix_files=bugfix_files
    )
    print(_line(idx_status, f"memory index: {idx_detail}"))
    if idx_status in ("missing", "no-markers", "invalid") or (check_only and idx_status == "stale"):
        failures += 1
    if idx_status == "invalid":
        print()
        print("维护完成：1 项需要处理")
        return 1

    graph_raw: dict | None = {} if check_only else None
    graph = refresh_repo_graph(check_only=check_only, raw_out=graph_raw)
    if graph is not None:
        graph_status, graph_detail = graph
        print(_line(graph_status, graph_detail))
        if graph_status in ("stale", "invalid"):
            failures += 1

    if check_only and graph is not None and graph_raw:
        audit = _run_audit_in_process((
            graph_raw["returncode"], graph_raw["stdout"]
        ))
    else:
        audit = _run_script(f"{SCRIPTS_REL}/audit.py", "check")
    if audit is None:
        print(_line("skip", "audit.py not found"))
    else:
        rc, out = audit
        print(_line("ok" if rc == 0 else "fail", f"audit.py check (exit {rc})"))
        if out:
            for line in out.splitlines():
                print(f"           {line}")
        if rc != 0:
            failures += 1

    mem_status, mem_detail = memory_staleness(memory_files, bugfix_files)
    glyph_status = {"stale": "warn"}.get(mem_status, mem_status)
    print(_line(glyph_status, f"memory activity: {mem_detail}"))

    rec_status, rec_detail = audit_recency()
    print(_line(rec_status, f"audit recency: {rec_detail}"))
    if rec_status == "invalid":
        failures += 1

    if not check_only:
        git_lines = _git_recent()
        if git_lines:
            print("\n近期 git 提交：")
            for line in git_lines:
                print(f"  {line}")
        changelog = _changelog_recent()
        if changelog:
            print("\n近期 CHANGELOG：")
            for line in changelog.splitlines():
                print(f"  {line}")

    print()
    if failures:
        print(f"维护完成：{failures} 项需要处理")
        return 1
    print("维护完成：无异常")
    return 0


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="init-agent-docs 文档体系自动化维护管线"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只读校验：不修改文件，索引过期或检查失败时退出码非 0",
    )
    parser.add_argument(
        "--memory-index",
        action="store_true",
        help="仅重建 MEMORY.md 索引标记段",
    )
    parser.add_argument("--memory-search", metavar="QUERY", help="检索全部记忆和 bugfix，默认最多输出 5 条")
    parser.add_argument("--limit", type=int, default=5, help="检索输出条数，1–50，默认 5")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.memory_search is not None:
        if args.memory_index or args.check:
            parser.error("--memory-search 不能与维护选项同时使用")
        if not 1 <= args.limit <= 50:
            parser.error("--limit 必须在 1–50 之间")
        return search_memory(args.memory_search, args.limit)
    if args.memory_index:
        status, detail = rebuild_memory_index(check_only=False)
        print(_line(status, f"memory index: {detail}"))
        return 0 if status in ("ok", "rebuilt", "skip") else 1
    return run_full(check_only=args.check)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main(sys.argv[1:]))

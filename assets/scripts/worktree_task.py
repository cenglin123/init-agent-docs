#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Git worktree isolation helper with one lightweight canonical-worktree claim.

Subcommands:
  create        create task/<id>[-<slug>] at wt-<id>[-<slug>]
  check         read-only branch / registration / ahead-behind report
  integrate     fast-forward a clean task branch into the canonical branch
  cleanup       remove an integrated, clean task worktree and its branch
  list          list linked task/* worktrees + main-claim state
  claim-main    claim the canonical worktree for one owner
  release-main  release the claim owned by that owner
  main-claim    read-only claim status

Task identity comes only from the Git worktree list and the task/* branch name;
there is no registry and no handshake state machine. Mutations and
`git merge --ff-only` share one Git common-dir lock. No lock, owner or claim is
taken over by time or PID: a conflicting lock returns `lock-busy`, and another
agent's active claim is refused (`--force` included). Read-only actions never
create lock or state files.

canonical 分支解析顺序：
  git config worktree-task.canonicalRef
  → refs/heads/main（存在时）
  → refs/heads/master（存在时）
  → 当前 symbolic HEAD（attached）

worktree 根目录解析顺序：
  git config worktree-task.worktreeRoot
  → <仓库父目录>/<仓库名>.worktrees

Results are JSON on stdout (stable result enum), exit code 0/1.
需要 git >= 2.31（--path-format=absolute）。
"""
import argparse
import json
import os
import re
import stat
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

BRANCH_PREFIX = 'task/'
STATE_DIRECTORY = 'worktree-task'
MAIN_CLAIM_FILE = 'main-claim.json'
MAIN_CLAIM_TTL_MINUTES = 180
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

RESULT_CREATED = 'created'
RESULT_OK = 'ok'
RESULT_NOT_FOUND = 'not-found'
RESULT_INTEGRATED = 'integrated'
RESULT_ALREADY_INTEGRATED = 'already-integrated'
RESULT_NEEDS_REBASE = 'needs-rebase'
RESULT_HEAD_DRIFT = 'head-drift'
RESULT_LOCK_BUSY = 'lock-busy'
RESULT_CLEANED = 'cleaned'
RESULT_ALREADY_CLEANED = 'already-cleaned'
RESULT_PARTIAL_STATE = 'partial-state'
RESULT_REFUSED = 'refused'
RESULT_NOT_CANONICAL = 'not-canonical'
RESULT_NOT_CLEAN = 'not-clean'
RESULT_IDENTITY_MISMATCH = 'identity-mismatch'

# hook / CI 环境下继承的 GIT_* 变量会劫持仓库定位，必须隔离
_GIT_ENV_BLOCKLIST = {
    'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
    'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
    'GIT_PREFIX', 'GIT_QUARANTINE_PATH',
}


# ─── Git 事实读取 ────────────────────────────────────────────────────────────

def _clean_env():
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_BLOCKLIST}


def _git(repo, *args):
    r = subprocess.run(
        ['git', '-C', str(repo), *args],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        env=_clean_env(), creationflags=_NO_WINDOW,
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _git_raw(repo, *args):
    r = subprocess.run(
        ['git', '-C', str(repo), *args],
        capture_output=True, env=_clean_env(), creationflags=_NO_WINDOW,
    )
    return r.returncode, r.stdout


def _norm(p) -> str:
    return os.path.normcase(os.path.realpath(str(p))).replace('\\', '/')


def _rev_parse(repo, ref):
    rc, out, _ = _git(repo, 'rev-parse', '--verify', ref)
    return out if rc == 0 else None


def _symbolic_ref(repo):
    rc, out, _ = _git(repo, 'symbolic-ref', 'HEAD')
    return out if rc == 0 else None


def _is_ancestor(repo, old, new) -> bool:
    return _git(repo, 'merge-base', '--is-ancestor', old, new)[0] == 0


def _worktree_clean(path) -> bool:
    rc, out, _ = _git(path, 'status', '--porcelain')
    return rc == 0 and not out


def _worktree_disposable(path) -> bool:
    """Cleanup must not silently discard ignored files such as local secrets."""
    rc, out, _ = _git(path, 'status', '--porcelain', '--ignored',
                      '--untracked-files=all')
    return rc == 0 and not out


def _worktree_list(repo):
    """Parse `--porcelain -z`: NUL fields, an extra NUL between records.

    NUL framing preserves paths containing spaces or newlines, unlike the
    line-oriented form.
    """
    rc, out = _git_raw(repo, 'worktree', 'list', '--porcelain', '-z')
    if rc != 0:
        return []
    entries, cur = [], None
    for field in out.decode('utf-8', errors='replace').split('\0'):
        if field.startswith('worktree '):
            if cur:
                entries.append(cur)
            cur = {'path': field[len('worktree '):], 'head': None, 'branch': None}
        elif cur is not None and field.startswith('HEAD '):
            cur['head'] = field[len('HEAD '):]
        elif cur is not None and field.startswith('branch '):
            cur['branch'] = field[len('branch '):]
    if cur:
        entries.append(cur)
    return entries


def _canonical_ref(repo) -> str | None:
    rc, out, _ = _git(repo, 'config', 'worktree-task.canonicalRef')
    if rc == 0 and out:
        return out
    for cand in ('refs/heads/main', 'refs/heads/master'):
        if _rev_parse(repo, cand):
            return cand
    return _symbolic_ref(repo)


def _git_dir_pair(repo):
    """(git-dir, common-dir)，均绝对化；非仓库返回 (None, None)。"""
    rc, gd, _ = _git(repo, 'rev-parse', '--path-format=absolute', '--git-dir')
    if rc != 0:
        return None, None
    rc, cd, _ = _git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    if rc != 0:
        return None, None
    return gd, cd


def canonical_error(repo, canonical_ref=None) -> str | None:
    """None = canonical 主工作树且 HEAD 在 canonical 分支；否则返回原因。"""
    gd, cd = _git_dir_pair(repo)
    if not gd:
        return 'not a git worktree'
    if _norm(gd) != _norm(cd):
        return 'linked worktree (git-dir != common-dir)'
    symref = _symbolic_ref(repo)
    if symref is None:
        return 'detached HEAD'
    canonical = canonical_ref or _canonical_ref(repo)
    if canonical and symref != canonical:
        return f'HEAD is {symref}, not {canonical}'
    return None


def _default_wt_root(repo) -> Path:
    resolved_repo = Path(repo).resolve()
    rc, out, _ = _git(resolved_repo, 'config', 'worktree-task.worktreeRoot')
    if rc == 0 and out:
        cfg = Path(out)
        return (cfg if cfg.is_absolute() else resolved_repo / cfg).resolve()
    return resolved_repo.parent / f'{resolved_repo.name}.worktrees'


# ─── 任务身份：仅 Git worktree 列表 + task/* 分支名 ────────────────────────

def _is_link_or_junction(path: Path) -> bool:
    """True for a symlink or Windows junction; a missing path is not a link."""
    p = Path(path)
    try:
        if p.is_symlink():
            return True
    except OSError:
        return True
    isjunction = getattr(os.path, 'isjunction', None)
    if isjunction is not None:
        try:
            return bool(isjunction(str(p)))
        except OSError:
            return True
    if os.name == 'nt':
        reparse = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
        if reparse:
            try:
                attrs = getattr(os.lstat(str(p)), 'st_file_attributes', 0)
                return bool(attrs & reparse)
            except FileNotFoundError:
                return False
            except OSError:
                return True
    return False


def _link_components(wt_root, path) -> bool:
    """True unless path is a direct child of wt_root with no link component."""
    root = Path(wt_root).resolve()
    p = Path(path)
    if _norm(p.parent) != _norm(root):
        return True
    return _is_link_or_junction(root / p.name)


def _suffix(entry) -> str:
    return entry['branch'][len('refs/heads/' + BRANCH_PREFIX):]


def _linked_tasks(repo):
    worktrees = _worktree_list(repo)
    if not worktrees:
        return []
    primary = _norm(worktrees[0]['path'])
    return [e for e in worktrees
            if _norm(e['path']) != primary
            and (e['branch'] or '').startswith('refs/heads/' + BRANCH_PREFIX)]


def _branch_suffixes(repo):
    rc, out, _ = _git(repo, 'for-each-ref', '--format=%(refname)',
                      'refs/heads/' + BRANCH_PREFIX)
    prefix = 'refs/heads/' + BRANCH_PREFIX
    return [ref[len(prefix):] for ref in out.splitlines()
            if rc == 0 and ref.startswith(prefix)]


def _registration_error(repo, entry, branch, expected, wt_root):
    """Reject foreign paths, links, wrong common-dir, and wrong checked-out branch."""
    raw = Path(entry['path'])
    if _norm(raw) != _norm(expected) or _link_components(wt_root, raw):
        return f"worktree registered at foreign path: {entry['path']}"
    if _is_link_or_junction(raw):
        return 'worktree path is a symlink or junction'
    _, common = _git_dir_pair(raw)
    _, repo_common = _git_dir_pair(repo)
    if not common or not repo_common or _norm(common) != _norm(repo_common):
        return 'worktree common directory mismatch'
    if _symbolic_ref(raw) != 'refs/heads/' + branch:
        return 'worktree checked-out branch mismatch'
    return None


def _task_state(repo, wt_root, task_id):
    """Resolve one task from Git facts; returns (state, ambiguous)."""
    root = Path(wt_root).resolve()

    def match(suffix):
        return suffix == task_id or suffix.startswith(task_id + '-')

    hits = [e for e in _linked_tasks(repo) if match(_suffix(e))]
    suffixes = [s for s in _branch_suffixes(repo) if match(s)]
    reg = hits[0] if len(hits) == 1 else None
    ambiguous = len(hits) > 1 or (reg is None and len(suffixes) > 1)
    if reg is not None:
        branch = reg['branch'][len('refs/heads/'):]
    else:
        branch = BRANCH_PREFIX + (suffixes[0] if len(suffixes) == 1 else task_id)
    suffix = branch[len(BRANCH_PREFIX):]
    expected = root / ('wt-' + suffix)
    # 兼容旧版无 --name 创建在 <wt_root>/<id> 的工作树，仍严格限定在 wt_root 直接子目录下。
    if suffix == task_id:
        legacy = root / task_id
        if (reg is not None and _norm(Path(reg['path'])) == _norm(legacy)) or (
            reg is None and not (expected.exists() or expected.is_symlink())
            and (legacy.exists() or legacy.is_symlink())
        ):
            expected = legacy
    branch_ref = 'refs/heads/' + branch
    branch_tip = _rev_parse(repo, branch_ref)
    canonical = _canonical_ref(repo)
    canonical_tip = _rev_parse(repo, canonical) if canonical else None
    reg_error = _registration_error(repo, reg, branch, expected, root) if reg else None
    exists = expected.exists() or expected.is_symlink()
    state = {
        'id': task_id, 'branch': branch, 'branch_tip': branch_tip,
        'registered': reg is not None,
        'reg_path': reg['path'] if reg else None,
        'reg_branch': reg['branch'] if reg else None,
        'reg_head': reg['head'] if reg else None,
        'reg_error': reg_error,
        'foreign_reg_path': (reg['path'] if reg_error and
                             reg_error.startswith('worktree registered at foreign')
                             else None),
        'expected_path': str(expected),
        'path': str(expected), 'path_exists': exists,
        'clean': (_worktree_clean(expected)
                  if reg is not None and reg_error is None and exists else None),
        'canonical': canonical, 'canonical_tip': canonical_tip,
    }
    if branch_tip and canonical_tip:
        rc, out, _ = _git(repo, 'rev-list', '--left-right', '--count',
                          f'{canonical}...{branch_ref}')
        if rc == 0:
            behind, ahead = out.split()
            state['ahead'], state['behind'] = int(ahead), int(behind)
        integrated = _is_ancestor(repo, branch_tip, canonical_tip)
        state['integrated'] = state['is_ancestor'] = integrated
    return state, ambiguous


def _slug(name):
    words = re.findall(r'[a-z0-9]+', name.lower())
    return '-'.join(words)[:48].strip('-') or 'task'


def _token(value, label):
    if not isinstance(value, str) or not value or len(value) > 100 \
            or any(c in value for c in '\r\n\0'):
        raise ValueError(f'invalid {label}')
    return value


# ─── Git common-dir 共享锁；无按时间或 PID 自动夺取 ────────────────────────

_LOCK_TOKENS = threading.local()


def _lock_dir(repo) -> Path:
    _, cd = _git_dir_pair(repo)
    if not cd:
        raise ValueError('not a Git repository')
    return Path(cd) / STATE_DIRECTORY / 'mutation.lock'


def lock_acquire(repo) -> bool:
    d = _lock_dir(repo)
    if d.parent.is_symlink():
        return False
    d.parent.mkdir(exist_ok=True)
    token = f"{os.getpid()}-{uuid.uuid4().hex}"
    try:
        d.mkdir()
    except OSError:
        return False
    try:
        (d / 'owner').write_text(token, encoding='utf-8')
    except OSError:
        # An incomplete lock remains for explicit inspection and recovery.
        return False
    tokens = getattr(_LOCK_TOKENS, 'values', {})
    tokens[_norm(d)] = token
    _LOCK_TOKENS.values = tokens
    return True


def lock_release(repo):
    d = _lock_dir(repo)
    tokens = getattr(_LOCK_TOKENS, 'values', {})
    token = tokens.get(_norm(d))
    if not token:
        return
    try:
        owner = (d / 'owner').read_text(encoding='utf-8').strip()
    except Exception:
        return
    if owner != token:
        return
    del tokens[_norm(d)]
    (d / 'owner').unlink()
    d.rmdir()


@contextmanager
def mutation_lock(repo):
    """Atomic common-dir lock; a conflict is reported, never waited out."""
    if not lock_acquire(repo):
        raise RuntimeError('worktree task lock is busy; inspect before manual recovery')
    try:
        yield
    finally:
        lock_release(repo)


# ─── 主工作树占用声明（main-claim）───────────────────────────────────────
# 主工作树只属于持有活动 claim 的 agent（通常是主对话）；其他 agent 入场时
# 工具层机械拒绝，替代依赖记忆与 git status 时点快照的旧做法（2026-10-20 撞车）。

def _main_claim_file(repo) -> Path | None:
    """claim 状态放 common git dir：对所有 worktree 全局可见。"""
    _, cd = _git_dir_pair(repo)
    return Path(cd) / STATE_DIRECTORY / MAIN_CLAIM_FILE if cd else None


def _stamp(offset_minutes=0) -> str:
    return (datetime.now() + timedelta(minutes=offset_minutes)).strftime(
        '%Y-%m-%d %H:%M:%S')


def _read_claim(path) -> dict | None:
    """Read a claim mapping; corrupted or non-dict JSON is treated as absent."""
    try:
        claim = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    return claim if isinstance(claim, dict) else None


def _load_main_claim(repo) -> dict | None:
    """未过期 claim 才有效；过期条目视为不存在（不主动删除）。"""
    path = _main_claim_file(repo)
    if not path or not path.is_file():
        return None
    claim = _read_claim(path)
    if not claim:
        return None
    try:
        expires = datetime.strptime(claim.get('expires_at', ''),
                                    '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None
    return claim if expires > datetime.now() else None


def _write_claim(path, claim) -> bool:
    """Same-directory temp file + os.replace; links/junctions are refused."""
    if _is_link_or_junction(path.parent) or _is_link_or_junction(path):
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
        try:
            with tmp.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(claim, stream, ensure_ascii=False, sort_keys=True,
                          indent=2)
                stream.write('\n')
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def main_claim_status(repo) -> dict:
    claim = _load_main_claim(repo)
    if not claim:
        return {'claimed': False}
    return {'claimed': True, 'owner': claim.get('owner'),
            'claimed_at': claim.get('claimed_at'),
            'expires_at': claim.get('expires_at')}


def claim_main(repo, owner: str, ttl_minutes: int = MAIN_CLAIM_TTL_MINUTES,
               force: bool = False) -> dict:
    """声明主工作树占用。

    他人持有**未过期** claim 时一律拒绝（--force 不豁免：强夺他人活动占用等于
    绕过协调，2026-10-20 独立审计 high）。同 owner 再次 claim 视为续期：到期时间
    重置为 now + ttl（不叠加），claimed_at 保留首次时刻（审计链）。
    读-判-写全程持 mutation_lock，锁冲突返回 lock-busy。"""
    repo = Path(repo)
    path = _main_claim_file(repo)
    if not path:
        return _result(RESULT_REFUSED, 1, id='main-worktree',
                       detail='not a git repository')
    try:
        with mutation_lock(repo):
            return _claim_main_locked(repo, path, owner, ttl_minutes)
    except RuntimeError as exc:
        return _result(RESULT_LOCK_BUSY, 1, id='main-worktree', detail=str(exc))


def _claim_main_locked(repo, path, owner, ttl_minutes):
    existing = _load_main_claim(repo)
    previous_owner = existing.get('owner') if existing else None
    if previous_owner and previous_owner != owner:
        return _result(RESULT_REFUSED, 1, id='main-worktree',
                       holder=previous_owner,
                       expires_at=existing.get('expires_at'),
                       detail='canonical worktree claimed by another agent')
    renewed = previous_owner == owner
    claimed_at = existing.get('claimed_at') if renewed else _stamp()
    expires_at = _stamp(ttl_minutes)
    if not _write_claim(path, {
            'owner': owner, 'claimed_at': claimed_at,
            'expires_at': expires_at, 'ttl_minutes': ttl_minutes}):
        return _result(RESULT_REFUSED, 1, id='main-worktree',
                       detail='main-claim path is linked or unavailable')
    return _result(RESULT_OK, 0, id='main-worktree', owner=owner,
                   expires_at=expires_at, renewed=renewed)


def release_main(repo, owner: str) -> dict:
    """释放本人持有的占用；无占用 not-found，他人持有拒绝（防误删）。"""
    repo = Path(repo)
    path = _main_claim_file(repo)
    if not path:
        return _result(RESULT_NOT_FOUND, 1, id='main-worktree')
    try:
        with mutation_lock(repo):
            return _release_main_locked(path, owner)
    except RuntimeError as exc:
        return _result(RESULT_LOCK_BUSY, 1, id='main-worktree', detail=str(exc))


def _release_main_locked(path, owner):
    if _is_link_or_junction(path):
        return _result(RESULT_REFUSED, 1, id='main-worktree',
                       detail='main-claim path is a symlink or junction')
    claim = _read_claim(path)
    if not claim:
        return _result(RESULT_NOT_FOUND, 1, id='main-worktree')
    if claim.get('owner') != owner:
        return _result(RESULT_REFUSED, 1, id='main-worktree',
                       holder=claim.get('owner'),
                       detail='main-claim held by another agent')
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        return _result(RESULT_REFUSED, 1, id='main-worktree', detail=str(exc))
    return _result(RESULT_OK, 0, id='main-worktree', released=True)


def main_claim_blocks(repo, except_owner: str | None = None) -> dict | None:
    """存在他人持有的活动占用时返回该 claim（供 integrate 拒绝）。"""
    claim = _load_main_claim(repo)
    if not claim or (except_owner and claim.get('owner') == except_owner):
        return None
    return claim


# ─── 五动作 ──────────────────────────────────────────────────────────────────

def _result(result, rc, **extra):
    payload = {'result': result}
    payload.update(extra)
    return payload, rc


def _fail(result, task_id, detail=None, **extra):
    if detail:
        extra['detail'] = detail
    return _result(result, 1, id=task_id, **extra)


def create(repo, wt_root=None, name=None, owner=None, base=None):
    repo = Path(repo)
    wt_root = Path(wt_root).resolve() if wt_root else _default_wt_root(repo)
    canonical = _canonical_ref(repo)
    err = canonical_error(repo, canonical)
    if err:
        return _result(RESULT_NOT_CANONICAL, 1, detail=err)
    if bool(name) != bool(owner):
        return _result(RESULT_REFUSED, 1,
                       detail='name and owner must be supplied together')
    try:
        if name:
            _token(name, 'name')
            _token(owner, 'owner')
        task_id = (uuid.uuid4().hex[:8] if name else
                   datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
        suffix = f'{task_id}-{_slug(name)}' if name else task_id
        branch = BRANCH_PREFIX + suffix
        base = base or _rev_parse(repo, canonical)
        if not base or not re.fullmatch(r'[0-9a-fA-F]{40,64}', base) \
                or _rev_parse(repo, base + '^{commit}') != base:
            return _result(RESULT_NOT_CANONICAL, 1,
                           detail='base must be an immutable commit SHA')
        wt_path = wt_root / ('wt-' + suffix)
        try:
            with mutation_lock(repo):
                wt_root.mkdir(parents=True, exist_ok=True)
                if wt_path.exists() or wt_path.is_symlink() \
                        or _is_link_or_junction(wt_path) \
                        or _rev_parse(repo, 'refs/heads/' + branch):
                    return _result(RESULT_REFUSED, 1,
                                   detail='task worktree or branch already exists')
                rc, _, stderr = _git(repo, 'worktree', 'add', str(wt_path),
                                     '-b', branch, base)
                if rc != 0:
                    return _result(RESULT_REFUSED, 1, id=task_id, detail=stderr)
        except RuntimeError as exc:
            return _result(RESULT_LOCK_BUSY, 1, detail=str(exc))
        except OSError as exc:
            return _result(RESULT_REFUSED, 1,
                           detail=f'worktree root unavailable: {exc}')
    except ValueError as exc:
        return _result(RESULT_REFUSED, 1, detail=str(exc))
    return _result(RESULT_CREATED, 0, id=task_id, branch=branch,
                   path=str(wt_path), base=base, canonical=canonical,
                   name=name, owner=owner)


def check(repo, wt_root=None, task_id=None):
    repo = Path(repo)
    wt_root = Path(wt_root).resolve() if wt_root else _default_wt_root(repo)
    st, ambiguous = _task_state(repo, wt_root, task_id)
    if ambiguous:
        return _fail(RESULT_REFUSED, task_id,
                     'task ID is ambiguous; pass the full branch suffix')
    if not st['branch_tip'] and not st['registered']:
        return _fail(RESULT_NOT_FOUND, task_id)
    keys = ('id', 'branch', 'branch_tip', 'registered', 'reg_path', 'reg_branch',
            'reg_head', 'reg_error', 'foreign_reg_path', 'expected_path',
            'path', 'path_exists', 'clean', 'canonical_tip',
            'ahead', 'behind', 'integrated', 'is_ancestor')
    return _result(RESULT_OK, 0, canonical=st['canonical'],
                   main_claim=main_claim_status(repo),
                   **{k: st.get(k) for k in keys})


def list_tasks(repo):
    tasks = []
    for entry in _linked_tasks(Path(repo)):
        tasks.append(dict(
            id=_suffix(entry), branch=entry['branch'][len('refs/heads/'):],
            path=entry['path'], head=entry['head'],
            clean=_worktree_clean(entry['path'])))
    return _result(RESULT_OK, 0, tasks=tasks, main_claim=main_claim_status(repo))


def integrate(repo, wt_root=None, task_id=None, _before_merge=None):
    repo = Path(repo)
    wt_root = Path(wt_root).resolve() if wt_root else _default_wt_root(repo)
    canonical = _canonical_ref(repo)
    err = canonical_error(repo, canonical)
    if err:
        return _fail(RESULT_NOT_CANONICAL, task_id, err)
    if not _worktree_clean(repo):
        return _fail(RESULT_NOT_CLEAN, task_id, 'canonical worktree dirty')
    st, ambiguous = _task_state(repo, wt_root, task_id)
    if ambiguous:
        return _fail(RESULT_IDENTITY_MISMATCH, task_id, 'task ID is ambiguous')
    if st['reg_error']:
        return _fail(RESULT_PARTIAL_STATE, task_id, st['reg_error'])
    if not st['branch_tip'] or not st['registered']:
        return _fail(RESULT_IDENTITY_MISMATCH, task_id,
                     'task branch or worktree registration missing')
    if st['reg_branch'] != 'refs/heads/' + st['branch'] \
            or st['reg_head'] != st['branch_tip']:
        return _fail(RESULT_IDENTITY_MISMATCH, task_id, 'task identity mismatch')
    if not st['clean']:
        return _fail(RESULT_NOT_CLEAN, task_id, 'task worktree dirty')
    if not st.get('integrated') and not _is_ancestor(repo, st['canonical_tip'], st['branch_tip']):
        return _fail(RESULT_NEEDS_REBASE, task_id,
                     'task does not contain current canonical tip')
    try:
        with mutation_lock(repo):
            return _integrate_locked(repo, canonical, wt_root, st, task_id,
                                     _before_merge)
    except RuntimeError as exc:
        return _fail(RESULT_LOCK_BUSY, task_id, str(exc))


def _integrate_locked(repo, canonical, wt_root, st, task_id, before_merge):
    # main-claim 必须在锁内复核：锁外看到的空闲状态可能已被其他进程改写。
    claim = main_claim_blocks(repo)
    if claim:
        return _fail(RESULT_REFUSED, task_id,
                     'canonical worktree claimed by another agent; coordinate or wait for expiry',
                     holder=claim.get('owner'), expires_at=claim.get('expires_at'))
    fresh, ambiguous = _task_state(repo, wt_root, task_id)
    if ambiguous or fresh['branch'] != st['branch'] \
            or fresh['reg_error'] or not fresh['registered']:
        return _fail(RESULT_PARTIAL_STATE, task_id,
                     fresh['reg_error'] or 'task identity changed before integration')
    err = canonical_error(repo, canonical)
    if err:
        return _fail(RESULT_NOT_CANONICAL, task_id, err)
    if not _worktree_clean(repo):
        return _fail(RESULT_NOT_CLEAN, task_id, 'canonical worktree dirty')
    m1 = _rev_parse(repo, canonical)
    t1 = _rev_parse(repo, 'refs/heads/' + st['branch'])
    if not m1 or not t1 or t1 != st['branch_tip']:
        return _fail(RESULT_HEAD_DRIFT, task_id, 'ref changed before integration')
    if before_merge is not None:
        before_merge()
    m2 = _rev_parse(repo, canonical)
    t2 = _rev_parse(repo, 'refs/heads/' + st['branch'])
    if m2 != m1 or t2 != t1:
        return _fail(RESULT_HEAD_DRIFT, task_id,
                     f'canonical {m1}->{m2} / task {t1}->{t2}')
    if _is_ancestor(repo, t2, m2):
        return _result(RESULT_ALREADY_INTEGRATED, 0, id=task_id,
                       canonical_tip=m2)
    if not _is_ancestor(repo, m2, t2):
        return _fail(RESULT_NEEDS_REBASE, task_id)
    rc, _, stderr = _git(repo, 'merge', '--ff-only', t2)
    if rc != 0:
        return _fail(RESULT_NEEDS_REBASE, task_id, stderr)
    new_tip = _rev_parse(repo, canonical)
    if not new_tip:
        return _fail(RESULT_PARTIAL_STATE, task_id,
                     'merge completed but canonical tip is unreadable')
    return _result(RESULT_INTEGRATED, 0, id=task_id, canonical_tip=new_tip)


def cleanup(repo, wt_root=None, task_id=None):
    repo = Path(repo)
    wt_root = Path(wt_root).resolve() if wt_root else _default_wt_root(repo)
    try:
        with mutation_lock(repo):
            return _cleanup_locked(repo, wt_root, task_id)
    except RuntimeError as exc:
        return _fail(RESULT_LOCK_BUSY, task_id, str(exc))


def _orphan_dirs(wt_root, task_id):
    root = Path(wt_root)
    base = 'wt-' + task_id
    try:
        return [p for p in root.iterdir()
                if p.name == base or p.name.startswith(base + '-')]
    except OSError:
        return []


def _cleanup_locked(repo, wt_root, task_id):
    st, ambiguous = _task_state(repo, wt_root, task_id)
    if ambiguous:
        return _fail(RESULT_REFUSED, task_id, 'task ID is ambiguous')
    if not st['branch_tip'] and not st['registered']:
        if st['path_exists'] or _orphan_dirs(wt_root, task_id):
            return _fail(RESULT_PARTIAL_STATE, task_id,
                         'orphan worktree directory remains; inspect before cleanup')
        return _result(RESULT_ALREADY_CLEANED, 0, id=task_id)
    if st['reg_error']:
        return _fail(RESULT_PARTIAL_STATE, task_id, st['reg_error'])
    if bool(st['branch_tip']) != st['registered']:
        return _fail(RESULT_PARTIAL_STATE, task_id,
                     'only one of branch / worktree registration exists')
    if st['reg_branch'] != 'refs/heads/' + st['branch'] \
            or st['reg_head'] != st['branch_tip'] or not st['path_exists']:
        return _fail(RESULT_REFUSED, task_id, 'identity mismatch')
    if not st['clean']:
        return _fail(RESULT_REFUSED, task_id, 'task worktree dirty')
    if not _worktree_disposable(st['reg_path']):
        return _fail(RESULT_REFUSED, task_id,
                     'task worktree has untracked or ignored data; inspect and preserve it')
    if not st.get('integrated'):
        return _fail(RESULT_REFUSED, task_id,
                     'task tip is not an ancestor of canonical')
    rc, _, stderr = _git(repo, 'worktree', 'remove', st['reg_path'])
    if rc != 0:
        return _fail(RESULT_REFUSED, task_id, stderr)
    rc, _, stderr = _git(repo, 'branch', '-d', st['branch'])
    if rc != 0:
        return _fail(RESULT_PARTIAL_STATE, task_id,
                     f'worktree removed but branch delete failed: {stderr}')
    return _result(RESULT_CLEANED, 0, id=task_id)


# ─── CLI ────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='worktree task helper and canonical worktree claim')
    parser.add_argument('action', choices=['create', 'check', 'integrate',
                                           'cleanup', 'list', 'claim-main',
                                           'release-main', 'main-claim'])
    parser.add_argument('id', nargs='?', default=None)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--wt-root', default=None,
                        help='override the task worktree root')
    parser.add_argument('--name')
    parser.add_argument('--owner')
    parser.add_argument('--ttl-minutes', type=int, default=MAIN_CLAIM_TTL_MINUTES,
                        help='main-claim time-to-live in minutes')
    parser.add_argument('--force', action='store_true',
                        help='claim-main: accepted but never overrides an active claim')
    parser.add_argument('--base')
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    wt_root = Path(args.wt_root).resolve() if args.wt_root else None

    if args.action in ('claim-main', 'release-main') and not args.owner:
        parser.error(f'{args.action} requires --owner')
    if args.action not in ('create', 'list', 'claim-main', 'release-main',
                           'main-claim') and not args.id:
        parser.error(f'{args.action} requires <id>')
    try:
        if args.action == 'create':
            payload, rc = create(repo, wt_root, args.name, args.owner, args.base)
        elif args.action == 'check':
            payload, rc = check(repo, wt_root, args.id)
        elif args.action == 'integrate':
            payload, rc = integrate(repo, wt_root, args.id)
        elif args.action == 'cleanup':
            payload, rc = cleanup(repo, wt_root, args.id)
        elif args.action == 'list':
            payload, rc = list_tasks(repo)
        elif args.action == 'claim-main':
            payload, rc = claim_main(repo, args.owner,
                                     ttl_minutes=args.ttl_minutes, force=args.force)
        elif args.action == 'release-main':
            payload, rc = release_main(repo, args.owner)
        else:
            payload, rc = main_claim_status(repo), 0
    except (ValueError, RuntimeError, OSError, TypeError) as exc:
        payload, rc = _result(RESULT_REFUSED, 1, detail=str(exc))
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return rc


if __name__ == '__main__':
    sys.exit(main())

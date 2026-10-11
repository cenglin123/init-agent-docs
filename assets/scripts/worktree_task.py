#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Git worktree isolation and cooperative task-admission CLI.

The four Git actions create/check/integrate/cleanup remain callable. A task
created with --name and --owner gains a stable common-dir record; register can
attach an existing linked worktree. Resume verifies owner/generation, intent
records free scope, review shows all open peers, coordinate records a current
pair protocol, and admit binds the review snapshot. Agents call check --write
before work. This tool does not intercept direct file writes or authenticate
owner labels. Optional hooks are separate and never installed by this script.

Mutations and fast-forward integration (`git merge --ff-only`) share one Git common-dir lock. No lock
or owner is taken over by time or PID. A failed create retains its creating
record for inspection. Read-only actions do not create registry state.

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
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

BRANCH_PREFIX = 'task/'
STATE_DIRECTORY = 'worktree-task'

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
RESULT_REVIEW_STALE = 'review-stale'


# ─── Git 事实读取 ─────────────────────────────────────────────────────────────

# hook / CI 环境下继承的 GIT_* 变量会劫持仓库定位，必须隔离
_GIT_ENV_BLOCKLIST = {
    'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
    'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
    'GIT_PREFIX', 'GIT_QUARANTINE_PATH',
}


def _clean_env():
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_BLOCKLIST}


def _git(repo, *args):
    r = subprocess.run(
        ['git', '-C', str(repo), *args],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        env=_clean_env(), creationflags=_NO_WINDOW,
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _norm(p) -> str:
    return os.path.normcase(os.path.realpath(str(p))).replace('\\', '/')


def _rev_parse(repo, ref):
    rc, out, _ = _git(repo, 'rev-parse', '--verify', ref)
    return out if rc == 0 else None


def _symbolic_ref(repo):
    rc, out, _ = _git(repo, 'symbolic-ref', 'HEAD')
    return out if rc == 0 else None


def _is_ancestor(repo, old, new) -> bool:
    rc, _, _ = _git(repo, 'merge-base', '--is-ancestor', old, new)
    return rc == 0


def _worktree_clean(path) -> bool:
    rc, out, _ = _git(path, 'status', '--porcelain')
    return rc == 0 and not out


def _worktree_disposable(path) -> bool:
    """Cleanup must not silently discard ignored files such as local secrets."""
    rc, out, _ = _git(path, 'status', '--porcelain', '--ignored', '--untracked-files=all')
    return rc == 0 and not out


def _worktree_list(repo):
    rc, out, _ = _git(repo, 'worktree', 'list', '--porcelain')
    if rc != 0:
        return []
    entries = []
    cur = None
    for line in out.splitlines():
        if line.startswith('worktree '):
            if cur:
                entries.append(cur)
            cur = {'path': line[len('worktree '):], 'head': None, 'branch': None}
        elif cur is not None and line.startswith('HEAD '):
            cur['head'] = line[len('HEAD '):]
        elif cur is not None and line.startswith('branch '):
            cur['branch'] = line[len('branch '):]
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
    rc, out, _ = _git(repo, 'config', 'worktree-task.worktreeRoot')
    if rc == 0 and out:
        return Path(out)
    repo = Path(repo).resolve()
    return repo.parent / f'{repo.name}.worktrees'


def _task_state(repo, wt_root, task_id, canonical_ref):
    record = _read_task(repo, task_id)
    branch = record['branch'] if record else BRANCH_PREFIX + task_id
    branch_ref = 'refs/heads/' + branch
    branch_tip = _rev_parse(repo, branch_ref)
    wt_path = Path(record['path']) if record else Path(wt_root) / task_id
    reg = None
    foreign_reg = None
    for entry in _worktree_list(repo):
        if _norm(entry['path']) == _norm(wt_path):
            reg = entry
        elif entry['branch'] == branch_ref:
            foreign_reg = entry
    state = {
        'id': task_id,
        'branch': branch,
        'branch_tip': branch_tip,
        'registered': reg is not None,
        'reg_path': reg['path'] if reg else None,
        'reg_branch': reg['branch'] if reg else None,
        'reg_head': reg['head'] if reg else None,
        'foreign_reg_path': foreign_reg['path'] if foreign_reg else None,
        'path': str(wt_path),
        'path_exists': wt_path.exists(),
        'clean': _worktree_clean(wt_path) if reg and wt_path.exists() else None,
    }
    tip = _rev_parse(repo, canonical_ref)
    state['canonical_tip'] = tip
    if branch_tip and tip:
        rc, out, _ = _git(
            repo, 'rev-list', '--left-right', '--count',
            f'{canonical_ref}...{branch_ref}',
        )
        if rc == 0:
            behind, ahead = out.split()
            state['ahead'] = int(ahead)
            state['behind'] = int(behind)
        state['integrated'] = _is_ancestor(repo, branch_tip, tip)
    return state


# ─── 协作登记：仅 Git common-dir 状态，非调度或身份认证服务 ───────────────────

def _registry_dir(repo) -> Path:
    _, common = _git_dir_pair(repo)
    if not common:
        raise ValueError('not a Git repository')
    return Path(common) / STATE_DIRECTORY / 'tasks'


def _task_file(repo, task_id) -> Path:
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{3,63}', task_id or ''):
        raise ValueError('invalid task ID')
    return _registry_dir(repo) / f'{task_id}.json'


def _read_task(repo, task_id):
    path = _task_file(repo, task_id)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError('task record is linked or not a file')
    row = json.loads(path.read_text(encoding='utf-8'))
    if row.get('id') != task_id or row.get('common') != _norm(_registry_dir(repo).parent.parent):
        raise ValueError('task record identity mismatch')
    return row


def _write_task(repo, row):
    path = _task_file(repo, row['id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('linked registry path')
    tmp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        with tmp.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(row, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _records(repo):
    directory = _registry_dir(repo)
    if not directory.exists():
        return []
    if directory.is_symlink():
        raise ValueError('linked registry directory')
    return [_read_task(repo, path.stem) for path in sorted(directory.glob('*.json'))]


def _snapshot(repo):
    """Optimistic read without creating a lock or registry directory."""
    directory = _registry_dir(repo)
    for _ in range(20):
        if _lock_dir(repo).exists():
            time.sleep(0.01)
            continue
        try:
            files = sorted(directory.glob('*.json')) if directory.exists() else []
            if directory.is_symlink() or any(path.is_symlink() for path in files):
                raise ValueError('linked registry path')
            before = [(path.name, path.read_bytes()) for path in files]
            worktrees = _worktree_list(repo)
            after_files = sorted(directory.glob('*.json')) if directory.exists() else []
            after = [(path.name, path.read_bytes()) for path in after_files]
        except FileNotFoundError:
            time.sleep(0.01)
            continue
        if before == after and worktrees == _worktree_list(repo) and not _lock_dir(repo).exists():
            if not worktrees:
                raise ValueError('Git worktree list unavailable')
            rows = [json.loads(content.decode('utf-8')) for _, content in after]
            for (name, _), row in zip(after, rows):
                if row.get('id') != Path(name).stem or row.get('common') != _norm(directory.parent.parent):
                    raise ValueError('task record repository mismatch')
            return rows, worktrees
        time.sleep(0.01)
    raise RuntimeError('registry changed during read or is locked')


def _all_open(repo, rows=None, worktrees=None):
    if rows is None or worktrees is None:
        rows, worktrees = _snapshot(repo)
    open_rows = [row for row in rows if row['status'] != 'closed']
    known_paths = {_norm(row['path']) for row in rows}
    known_branches = {'refs/heads/' + row['branch'] for row in rows}
    primary = _norm(worktrees[0]['path']) if worktrees else None
    for wt in worktrees:
        if _norm(wt['path']) == primary or not (wt['branch'] or '').startswith('refs/heads/task/'):
            continue
        if _norm(wt['path']) in known_paths or wt['branch'] in known_branches:
            continue
        branch = wt['branch'] or 'detached'
        key = hashlib.sha256((_norm(wt['path']) + branch).encode('utf-8')).hexdigest()[:12]
        open_rows.append(dict(id='legacy-' + key, name=branch, branch=branch,
                              path=wt['path'], status='unknown', generation=0,
                              owner=None, intent=None, coordination={}))
    return sorted(open_rows, key=lambda row: row['id'])


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 8192 or '\0' in value:
        raise ValueError(f'{label} must be nonempty text up to 8192 characters')
    return value


def _token(value, label):
    if not isinstance(value, str) or not value or len(value) > 100 or any(c in value for c in '\r\n\0'):
        raise ValueError(f'invalid {label}')
    return value


def _slug(name):
    words = re.findall(r'[a-z0-9]+', name.lower())
    return '-'.join(words)[:48].strip('-') or 'task'


def _path_hint(value):
    value = value.replace('\\', '/')
    if (not value or value.startswith('/') or value.endswith('/') or
            '//' in value or '*' in value or '?' in value or ':' in value or
            any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('path hint must be a literal repository-relative path')
    return value.casefold()


def _identity(row, owner, generation):
    if not row or row['status'] != 'active' or row['owner'] != owner or row['generation'] != generation:
        raise ValueError('task owner, generation, or active status mismatch')


def _verify_task(repo, row):
    path = Path(row['path'])
    if not path.is_dir() or path.is_symlink():
        raise ValueError('task worktree missing or linked')
    if _norm(path) == _norm(_worktree_list(repo)[0]['path']):
        raise ValueError('canonical worktree cannot be registered as a task')
    _, common = _git_dir_pair(path)
    if _norm(common or '') != row['common']:
        raise ValueError('task Git common directory mismatch')
    if _symbolic_ref(path) != 'refs/heads/' + row['branch']:
        raise ValueError('task branch mismatch')
    if _norm(path) not in {_norm(wt['path']) for wt in _worktree_list(repo)}:
        raise ValueError('task worktree is not registered in Git')
    if not _is_ancestor(path, row['base'], 'HEAD'):
        raise ValueError('task base is not an ancestor of HEAD')


# ─── Git common-dir 共享锁；无按时间或 PID 自动夺取 ──────────────────────────

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
    deadline = time.monotonic() + 10
    while not lock_acquire(repo):
        if time.monotonic() >= deadline:
            raise RuntimeError('worktree task registry is locked; inspect before manual recovery')
        time.sleep(0.02)
    try:
        yield
    finally:
        lock_release(repo)


def _scope_revision(row):
    return (row.get('intent') or {}).get('revision', 0)


def _overlap(left, right):
    hits = []
    for a in (left.get('intent') or {}).get('paths', []):
        for b in (right.get('intent') or {}).get('paths', []):
            if a == b or a.startswith(b + '/') or b.startswith(a + '/'):
                hits.append([a, b])
    return hits


def _affected(left, right):
    li, ri = left.get('intent'), right.get('intent')
    if not li or not ri:
        return True
    return bool(_overlap(left, right) or
                any(dep['id'] == right['id'] for dep in li.get('depends_on', [])) or
                any(dep['id'] == left['id'] for dep in ri.get('depends_on', [])) or
                right['id'] in left.get('coordination', {}) or
                left['id'] in right.get('coordination', {}))


def _digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _pair_digest(left, right):
    return _digest({left['id']: left.get('coordination', {}).get(right['id']),
                    right['id']: right.get('coordination', {}).get(left['id'])})


def _review_state(row, peers):
    details = []
    for peer in peers:
        if peer['id'] == row['id']:
            continue
        intent = peer.get('intent') or {}
        details.append(dict(id=peer['id'], name=peer['name'], status=peer['status'],
                            generation=peer['generation'], revision=_scope_revision(peer),
                            goal=intent.get('goal'), non_goal=intent.get('non_goal'),
                            scope=intent.get('scope', []), paths=intent.get('paths', []),
                            depends_on=intent.get('depends_on', []),
                            path_overlap=_overlap(row, peer), affected=_affected(row, peer),
                            own_conclusion=row.get('coordination', {}).get(peer['id']),
                            peer_conclusion=peer.get('coordination', {}).get(row['id'])))
    payload = dict(id=row['id'], revision=_scope_revision(row),
                   own_dependencies=(row.get('intent') or {}).get('depends_on', []),
                   peers=details)
    payload['digest'] = _digest(payload)
    return payload


def _pair_confirmed(row, peer):
    entry = row.get('coordination', {}).get(peer['id'])
    if not entry or entry.get('own_revision') != _scope_revision(row) or entry.get('peer_revision') != _scope_revision(peer):
        return False
    if entry.get('override'):
        return bool(entry.get('authorized_by') and entry.get('reason') and entry.get('boundary'))
    other = peer.get('coordination', {}).get(row['id'])
    return bool(other and not other.get('override') and
                other.get('own_revision') == _scope_revision(peer) and
                other.get('peer_revision') == _scope_revision(row) and
                entry.get('protocol') and entry.get('protocol') == other.get('protocol'))


def _admission(row, peers):
    admitted = row.get('admission')
    if not row.get('intent') or not admitted or admitted.get('own_revision') != _scope_revision(row):
        raise ValueError('task intent is not admitted')
    seen = admitted.get('peers', {})
    advisory = []
    for peer in peers:
        if peer['id'] == row['id']:
            continue
        identity = [peer['generation'], _scope_revision(peer)]
        if _affected(row, peer):
            if seen.get(peer['id']) != identity or not _pair_confirmed(row, peer):
                raise ValueError(f'peer {peer["id"]} needs current coordination and admission')
            if admitted.get('pair_digests', {}).get(peer['id']) != _pair_digest(row, peer):
                raise ValueError(f'peer {peer["id"]} coordination changed')
        elif seen.get(peer['id']) != identity:
            advisory.append(peer['id'])
    return dict(coordinated=True, review_refresh=advisory)


def _cooperative_row(repo, task_id, owner, generation, *, snapshot=False):
    row = next((r for r in _snapshot(repo)[0] if r['id'] == task_id), None) if snapshot else _read_task(repo, task_id)
    _identity(row, owner, generation)
    _verify_task(repo, row)
    return row


def register(repo, task_id, name, owner, path, base):
    _token(name, 'name')
    _token(owner, 'owner')
    if not path:
        raise ValueError('register requires --worktree-path')
    if not re.fullmatch(r'[a-z0-9]{4,16}', task_id or ''):
        raise ValueError('cooperative task ID must be 4–16 lowercase letters/digits')
    branch_ref = _symbolic_ref(path)
    if not branch_ref or not branch_ref.startswith('refs/heads/'):
        raise ValueError('register requires an attached task branch')
    branch = branch_ref[len('refs/heads/'):]
    if not re.fullmatch(r'[0-9a-fA-F]{40,64}', base or '') or _rev_parse(repo, base + '^{commit}') != base:
        raise ValueError('base must be a full immutable commit SHA')
    row = dict(id=task_id, name=name, owner=owner, generation=1, status='active',
               branch=branch, path=str(Path(path).resolve()), base=base,
               common=_norm(_registry_dir(repo).parent.parent), coordination={})
    _verify_task(repo, row)
    with mutation_lock(repo):
        if _task_file(repo, task_id).exists():
            raise ValueError('task ID already registered; resume instead')
        for existing in _records(repo):
            if _norm(existing['path']) == _norm(path) or existing['branch'] == branch:
                raise ValueError('task worktree or branch already registered')
        _verify_task(repo, row)
        _write_task(repo, row)
    return _result(RESULT_OK, 0, **row)


def resume(repo, task_id, owner, generation):
    row = _cooperative_row(repo, task_id, owner, generation, snapshot=True)
    return _result(RESULT_OK, 0, **row)


def list_tasks(repo):
    rows, worktrees = _snapshot(repo)
    return _result(RESULT_OK, 0, tasks=_all_open(repo, rows, worktrees))


def intent(repo, task_id, owner, generation, goal, non_goal, scope=(), paths=(), depends_on=()):
    contents = dict(goal=_text(goal, 'goal'), non_goal=_text(non_goal, 'non-goal'),
                    scope=[_text(value, 'scope') for value in scope],
                    paths=sorted({_path_hint(value) for value in paths}), depends_on=[])
    for value in depends_on:
        peer_id, sep, sha = value.partition('@')
        _task_file(repo, peer_id)
        if (not sep or peer_id == task_id or not re.fullmatch(r'[0-9a-fA-F]{40,64}', sha or '') or
                _rev_parse(repo, sha + '^{commit}') != sha):
            raise ValueError('dependency must be peer-id@full-committed-SHA')
        peer = _read_task(repo, peer_id)
        if not peer:
            raise ValueError('dependency peer is not registered')
        if not (_is_ancestor(repo, sha, 'refs/heads/' + peer['branch']) or
                _is_ancestor(repo, sha, _canonical_ref(repo))):
            raise ValueError('dependency SHA is not in peer or canonical history')
        contents['depends_on'].append(dict(id=peer_id, sha=sha))
    contents['depends_on'] = sorted(contents['depends_on'], key=lambda value: value['id'])
    with mutation_lock(repo):
        row = _cooperative_row(repo, task_id, owner, generation)
        for dep in contents['depends_on']:
            peer = _read_task(repo, dep['id'])
            if not peer:
                raise ValueError('dependency peer is not registered')
            if not (_is_ancestor(repo, dep['sha'], 'refs/heads/' + peer['branch']) or
                    _is_ancestor(repo, dep['sha'], _canonical_ref(repo))):
                raise ValueError('dependency SHA changed relative to peer history')
        previous = row.get('intent') or {}
        if any(previous.get(key) != value for key, value in contents.items()):
            contents['revision'] = previous.get('revision', 0) + 1
            row['intent'] = contents
            row.pop('admission', None)
            _write_task(repo, row)
        return _result(RESULT_OK, 0, intent=row['intent'])


def review(repo, task_id, owner, generation):
    rows, worktrees = _snapshot(repo)
    row = next((item for item in rows if item['id'] == task_id), None)
    _identity(row, owner, generation)
    _verify_task(repo, row)
    if not row.get('intent'):
        raise ValueError('task intent required before review')
    return _result(RESULT_OK, 0, **_review_state(row, _all_open(repo, rows, worktrees)))


def coordinate(repo, task_id, owner, generation, peer_id, peer_revision,
               protocol=None, *, authorized_by=None, reason=None, boundary=None):
    with mutation_lock(repo):
        row = _cooperative_row(repo, task_id, owner, generation)
        if not row.get('intent'):
            raise ValueError('task intent required before coordination')
        peer = next((item for item in _all_open(repo, _records(repo), _worktree_list(repo))
                     if item['id'] == peer_id), None)
        if not peer or peer_id == task_id or _scope_revision(peer) != peer_revision:
            raise ValueError('peer missing or revision changed; review again')
        if authorized_by or reason or boundary:
            if not all((authorized_by, reason, boundary)):
                raise ValueError('override requires authorized-by, reason, and boundary')
            entry = dict(override=True, authorized_by=_token(authorized_by, 'authorized-by'),
                         reason=_text(reason, 'reason'), boundary=_text(boundary, 'boundary'))
        else:
            if not peer.get('intent'):
                raise ValueError('peer intent unknown; use scoped override or ask peer to register intent')
            entry = dict(override=False, protocol=_text(protocol, 'protocol'))
        entry.update(own_revision=_scope_revision(row), peer_revision=peer_revision)
        row.setdefault('coordination', {})[peer_id] = entry
        row.pop('admission', None)
        _write_task(repo, row)
        return _result(RESULT_OK, 0, peer=peer_id, conclusion=entry)


def admit(repo, task_id, owner, generation, review_digest):
    with mutation_lock(repo):
        row = _cooperative_row(repo, task_id, owner, generation)
        if not row.get('intent'):
            raise ValueError('task intent required before admission')
        peers = _all_open(repo, _records(repo), _worktree_list(repo))
        current = _review_state(row, peers)
        if current['digest'] != review_digest:
            raise ValueError('review snapshot changed; review again')
        for peer in peers:
            if peer['id'] != task_id and _affected(row, peer) and not _pair_confirmed(row, peer):
                raise ValueError(f'peer {peer["id"]} needs bilateral protocol or scoped override')
        row['admission'] = dict(own_revision=_scope_revision(row), digest=review_digest,
                                peers={peer['id']: [peer['generation'], _scope_revision(peer)]
                                       for peer in peers if peer['id'] != task_id},
                                pair_digests={peer['id']: _pair_digest(row, peer) for peer in peers
                                              if peer['id'] != task_id and _affected(row, peer)})
        _write_task(repo, row)
        return _result(RESULT_OK, 0, admitted=True, admission=row['admission'])


def close(repo, task_id, owner, generation):
    with mutation_lock(repo):
        row = _cooperative_row(repo, task_id, owner, generation)
        state = _task_state(repo, _default_wt_root(repo), task_id, _canonical_ref(repo))
        if not state.get('integrated') or not state.get('clean'):
            raise ValueError('close requires an integrated commit and clean task worktree')
        row['status'] = 'closed'
        row['generation'] += 1
        _write_task(repo, row)
        return _result(RESULT_OK, 0, **row)


# ─── 四动作 ───────────────────────────────────────────────────────────────────

def _result(result, rc, **extra):
    payload = {'result': result}
    payload.update(extra)
    return payload, rc


def create(repo, wt_root=None, name=None, owner=None, base=None):
    repo = Path(repo)
    wt_root = Path(wt_root) if wt_root else _default_wt_root(repo)
    canonical = _canonical_ref(repo)
    err = canonical_error(repo, canonical)
    if err:
        return _result(RESULT_NOT_CANONICAL, 1, detail=err)
    if bool(name) != bool(owner):
        return _result(RESULT_REFUSED, 1, detail='name and owner must be supplied together')
    cooperative = bool(name)
    if cooperative:
        _token(name, 'name')
        _token(owner, 'owner')
    with mutation_lock(repo):
        try:
            wt_root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return _result(RESULT_REFUSED, 1, detail=f'worktree root unavailable: {e}')
        task_id = uuid.uuid4().hex[:8] if cooperative else datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
        suffix = f'{task_id}-{_slug(name)}' if cooperative else task_id
        branch = BRANCH_PREFIX + suffix
        base = base or _rev_parse(repo, canonical)
        if not base or not re.fullmatch(r'[0-9a-fA-F]{40,64}', base) or _rev_parse(repo, base + '^{commit}') != base:
            return _result(RESULT_NOT_CANONICAL, 1, detail='base must be an immutable commit SHA')
        wt_path = wt_root / (f'wt-{suffix}' if cooperative else task_id)
        if wt_path.exists() or wt_path.is_symlink() or _rev_parse(repo, 'refs/heads/' + branch):
            return _result(RESULT_REFUSED, 1, detail='task worktree or branch already exists')
        row = None
        if cooperative:
            row = dict(id=task_id, name=name, owner=owner, generation=1, status='creating',
                       branch=branch, path=str(wt_path.resolve()), base=base,
                       common=_norm(_registry_dir(repo).parent.parent), coordination={})
            _write_task(repo, row)
        rc, _, stderr = _git(repo, 'worktree', 'add', str(wt_path), '-b', branch, base)
        if rc != 0:
            return _result(RESULT_REFUSED, 1, id=task_id, detail=stderr + '; inspect retained state')
        if cooperative:
            row['status'] = 'active'
            _write_task(repo, row)
        return _result(RESULT_CREATED, 0, id=task_id, branch=branch,
                       path=str(wt_path), base=base, canonical=canonical,
                       owner=owner if cooperative else None,
                       generation=1 if cooperative else None)


def check(repo, wt_root=None, task_id=None, *, owner=None, generation=None, write=False):
    repo = Path(repo)
    wt_root = Path(wt_root) if wt_root else _default_wt_root(repo)
    canonical = _canonical_ref(repo)
    rows, worktrees = _snapshot(repo)
    st = _task_state(repo, wt_root, task_id, canonical)
    if not st['branch_tip'] and not st['registered']:
        return _result(RESULT_NOT_FOUND, 1, id=task_id)
    keys = ('id', 'branch', 'branch_tip', 'registered', 'reg_path', 'reg_branch',
            'reg_head', 'foreign_reg_path', 'path', 'path_exists', 'clean',
            'canonical_tip', 'ahead', 'behind', 'integrated')
    extra = {}
    if write:
        row = next((item for item in rows if item['id'] == task_id), None)
        _identity(row, owner, generation)
        _verify_task(repo, row)
        if _norm(repo) != _norm(row['path']):
            raise ValueError('write check requires task worktree')
        extra = _admission(row, _all_open(repo, rows, worktrees))
    return _result(RESULT_OK, 0, canonical=canonical,
                   **{k: st.get(k) for k in keys}, **extra)


def integrate(repo, wt_root=None, task_id=None, _before_merge=None):
    repo = Path(repo)
    wt_root = Path(wt_root) if wt_root else _default_wt_root(repo)
    canonical = _canonical_ref(repo)
    err = canonical_error(repo, canonical)
    if err:
        return _result(RESULT_NOT_CANONICAL, 1, id=task_id, detail=err)
    if not _worktree_clean(repo):
        return _result(RESULT_NOT_CLEAN, 1, id=task_id,
                       detail='canonical worktree dirty')
    st = _task_state(repo, wt_root, task_id, canonical)
    if not st['branch_tip'] or not st['registered']:
        return _result(RESULT_IDENTITY_MISMATCH, 1, id=task_id,
                       detail='task branch or worktree registration missing')
    if st['foreign_reg_path']:
        return _result(RESULT_IDENTITY_MISMATCH, 1, id=task_id,
                       detail=f"task registered at foreign path: {st['foreign_reg_path']}")
    if st['reg_branch'] != 'refs/heads/' + st['branch'] \
            or st['reg_head'] != st['branch_tip']:
        return _result(RESULT_IDENTITY_MISMATCH, 1, id=task_id,
                       detail='task identity mismatch')
    if not st['clean']:
        return _result(RESULT_NOT_CLEAN, 1, id=task_id, detail='task worktree dirty')
    if st['integrated']:
        return _result(RESULT_ALREADY_INTEGRATED, 0, id=task_id,
                       canonical_tip=st['canonical_tip'])
    if not _is_ancestor(repo, st['canonical_tip'], st['branch_tip']):
        return _result(RESULT_NEEDS_REBASE, 1, id=task_id,
                       detail='task does not contain current canonical tip')

    if not lock_acquire(repo):
        return _result(RESULT_LOCK_BUSY, 1, id=task_id)
    try:
        err = canonical_error(repo, canonical)
        if err:
            return _result(RESULT_NOT_CANONICAL, 1, id=task_id, detail=err)
        m1 = _rev_parse(repo, canonical)
        t1 = _rev_parse(repo, 'refs/heads/' + st['branch'])
        if not m1 or not t1 or t1 != st['branch_tip']:
            return _result(RESULT_HEAD_DRIFT, 1, id=task_id,
                           detail='ref changed before integration')
        if _before_merge is not None:
            _before_merge()
        m2 = _rev_parse(repo, canonical)
        t2 = _rev_parse(repo, 'refs/heads/' + st['branch'])
        if m2 != m1 or t2 != t1:
            return _result(RESULT_HEAD_DRIFT, 1, id=task_id,
                           detail=f'canonical {m1}->{m2} / task {t1}->{t2}')
        if _is_ancestor(repo, t2, m2):
            return _result(RESULT_ALREADY_INTEGRATED, 0, id=task_id,
                           canonical_tip=m2)
        if not _is_ancestor(repo, m2, t2):
            return _result(RESULT_NEEDS_REBASE, 1, id=task_id)
        rc, _, stderr = _git(repo, 'merge', '--ff-only', 'refs/heads/' + st['branch'])
        if rc != 0:
            return _result(RESULT_NEEDS_REBASE, 1, id=task_id, detail=stderr)
        new_tip = _rev_parse(repo, canonical)
        if new_tip == m2:
            return _result(RESULT_ALREADY_INTEGRATED, 0, id=task_id,
                           canonical_tip=m2)
    finally:
        lock_release(repo)
    return _result(RESULT_INTEGRATED, 0, id=task_id, canonical_tip=new_tip)


def cleanup(repo, wt_root=None, task_id=None):
    with mutation_lock(repo):
        return _cleanup_locked(repo, wt_root, task_id)


def _cleanup_locked(repo, wt_root=None, task_id=None):
    repo = Path(repo)
    wt_root = Path(wt_root) if wt_root else _default_wt_root(repo)
    canonical = _canonical_ref(repo)
    st = _task_state(repo, wt_root, task_id, canonical)
    record = _read_task(repo, task_id)
    any_reg = st['registered'] or bool(st['foreign_reg_path'])
    if record and record['status'] == 'closed' and st['branch_tip'] and not any_reg and not st['path_exists']:
        return _result(RESULT_ALREADY_CLEANED, 0, id=task_id, branch_retained=True)
    if not st['branch_tip'] and not any_reg:
        return _result(RESULT_ALREADY_CLEANED, 0, id=task_id)
    if bool(st['branch_tip']) != any_reg:
        return _result(RESULT_PARTIAL_STATE, 1, id=task_id,
                       detail='only one of branch / worktree registration exists')
    if st['foreign_reg_path'] or not st['registered']:
        return _result(RESULT_REFUSED, 1, id=task_id,
                       detail=f"worktree at foreign path: {st['foreign_reg_path']}")
    if st['reg_branch'] != 'refs/heads/' + st['branch'] \
            or st['reg_head'] != st['branch_tip'] \
            or not st['path_exists']:
        return _result(RESULT_REFUSED, 1, id=task_id, detail='identity mismatch')
    if not st['clean']:
        return _result(RESULT_REFUSED, 1, id=task_id, detail='task worktree dirty')
    if not _worktree_disposable(st['reg_path']):
        return _result(RESULT_REFUSED, 1, id=task_id,
                       detail='task worktree has untracked or ignored data; inspect and preserve it')
    if not st['integrated']:
        return _result(RESULT_REFUSED, 1, id=task_id,
                       detail='task tip is not an ancestor of canonical')
    if record and record['status'] != 'closed':
        return _result(RESULT_REFUSED, 1, id=task_id,
                       detail='cooperative task must be closed before cleanup')
    rc, _, stderr = _git(repo, 'worktree', 'remove', st['reg_path'])
    if rc != 0:
        return _result(RESULT_REFUSED, 1, id=task_id, detail=stderr)
    if record:
        # Keep its branch and common-dir record as auditable task evidence.
        return _result(RESULT_CLEANED, 0, id=task_id, branch_retained=True)
    rc, _, stderr = _git(repo, 'branch', '-d', st['branch'])
    if rc != 0:
        return _result(RESULT_PARTIAL_STATE, 1, id=task_id,
                       detail=f'worktree removed but branch delete failed: {stderr}')
    return _result(RESULT_CLEANED, 0, id=task_id)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='worktree task helper and cooperative admission')
    parser.add_argument('action', choices=['create', 'check', 'integrate', 'cleanup',
                                           'register', 'resume', 'list', 'intent',
                                           'review', 'coordinate', 'admit', 'close'])
    parser.add_argument('id', nargs='?', default=None)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--wt-root', default=None,
                        help='override the task worktree root')
    parser.add_argument('--name')
    parser.add_argument('--owner')
    parser.add_argument('--generation', type=int)
    parser.add_argument('--base')
    parser.add_argument('--worktree-path')
    parser.add_argument('--goal')
    parser.add_argument('--non-goal')
    parser.add_argument('--scope', action='append', default=[])
    parser.add_argument('--path', action='append', default=[])
    parser.add_argument('--depends-on', action='append', default=[], metavar='PEER-ID@COMMIT-SHA')
    parser.add_argument('--peer')
    parser.add_argument('--peer-revision', type=int)
    parser.add_argument('--protocol')
    parser.add_argument('--authorized-by')
    parser.add_argument('--reason')
    parser.add_argument('--boundary')
    parser.add_argument('--review-digest')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    wt_root = Path(args.wt_root) if args.wt_root else None

    if args.action not in ('create', 'list') and not args.id:
        parser.error(f'{args.action} requires <id>')
    try:
        if args.action == 'create':
            payload, rc = create(repo, wt_root, args.name, args.owner, args.base)
        elif args.action == 'check':
            payload, rc = check(repo, wt_root, args.id, owner=args.owner,
                                generation=args.generation, write=args.write)
        elif args.action == 'integrate':
            payload, rc = integrate(repo, wt_root, args.id)
        elif args.action == 'cleanup':
            payload, rc = cleanup(repo, wt_root, args.id)
        elif args.action == 'register':
            payload, rc = register(repo, args.id, args.name, args.owner,
                                   args.worktree_path, args.base)
        elif args.action == 'resume':
            payload, rc = resume(repo, args.id, args.owner, args.generation)
        elif args.action == 'list':
            payload, rc = list_tasks(repo)
        elif args.action == 'intent':
            payload, rc = intent(repo, args.id, args.owner, args.generation,
                                 args.goal, args.non_goal, args.scope, args.path,
                                 args.depends_on)
        elif args.action == 'review':
            payload, rc = review(repo, args.id, args.owner, args.generation)
        elif args.action == 'coordinate':
            payload, rc = coordinate(repo, args.id, args.owner, args.generation,
                                     args.peer, args.peer_revision, args.protocol,
                                     authorized_by=args.authorized_by,
                                     reason=args.reason, boundary=args.boundary)
        elif args.action == 'admit':
            payload, rc = admit(repo, args.id, args.owner, args.generation,
                                args.review_digest)
        else:
            payload, rc = close(repo, args.id, args.owner, args.generation)
    except (ValueError, RuntimeError, OSError, TypeError) as exc:
        payload, rc = _result(RESULT_REFUSED, 1, detail=str(exc))
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return rc


if __name__ == '__main__':
    sys.exit(main())

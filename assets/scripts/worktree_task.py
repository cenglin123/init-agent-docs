#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""worktree_task.py — 多 Agent worktree 最小运行时（四动作 helper）

    python scripts/worktree_task.py create
    python scripts/worktree_task.py check <id>
    python scripts/worktree_task.py integrate <id>
    python scripts/worktree_task.py cleanup <id>

create    从当前 canonical 分支创建 task/<id> 分支与独立 linked worktree；
          每次调用生成新的不透明 ID（重复派单也得新身份）。
check     只读报告 task branch / worktree registration / clean / ahead-behind /
          是否已是 canonical 分支祖先。
integrate 取得 per-repo 共享锁，校验 canonical 主工作树、symbolic-ref、clean
          canonical 与 task 身份，复核 ref 未漂移后 git merge --ff-only。
cleanup   仅在 task tip 已是 canonical 祖先、task worktree clean、身份完全
          匹配时移除 worktree 再删除分支；半缺失状态 fail closed。

本 helper 只是 Git wrapper：不保存任务描述、生命周期或恢复记录；
Git branch / worktree registration / history 是唯一事实源。响应丢失后
不认领原调用——重试 create 生成新 ID，旧对象经 Git 列表可发现；重试
integrate 经 merge-base ancestry 返回 already-integrated。

canonical 分支解析顺序：
  git config worktree-task.canonicalRef
  → refs/heads/main（存在时）
  → refs/heads/master（存在时）
  → 当前 symbolic HEAD（attached）

worktree 根目录解析顺序：
  git config worktree-task.worktreeRoot
  → <仓库父目录>/<仓库名>.worktrees

结果经 stdout 以 JSON 返回（result 字段为稳定枚举），exit code 0/1。
需要 git >= 2.31（--path-format=absolute）。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

BRANCH_PREFIX = 'task/'
LOCK_TTL = 1800
_MAX_ACQUIRE_ATTEMPTS = 4

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
    branch = BRANCH_PREFIX + task_id
    branch_ref = 'refs/heads/' + branch
    branch_tip = _rev_parse(repo, branch_ref)
    wt_path = Path(wt_root) / task_id
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


# ─── per-repo 共享锁（PID 三态 + 原子 stale takeover + owner 校验 release） ────

_LOCK_TOKEN = None


def _lock_dir(repo) -> Path:
    _, cd = _git_dir_pair(repo)
    key = hashlib.sha1(_norm(cd or repo).encode('utf-8')).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f'worktree-task-{key}.lock'


def _pid_state(pid: int) -> str:
    """live / dead / unverifiable。"""
    if pid <= 0:
        return 'dead'
    try:
        if os.name == 'nt':
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not h:
                err = ctypes.GetLastError()
                return 'dead' if err == 87 else 'unverifiable'
            try:
                exit_code = ctypes.c_ulong()
                ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
                if not ok:
                    return 'unverifiable'
                return 'live' if exit_code.value == 259 else 'dead'
            finally:
                ctypes.windll.kernel32.CloseHandle(h)
        else:
            os.kill(pid, 0)
            return 'live'
    except ProcessLookupError:
        return 'dead'
    except PermissionError:
        return 'live'
    except Exception:
        return 'unverifiable'


def _lock_meta(d):
    try:
        pid_raw = (d / 'pid').read_text(encoding='utf-8').strip()
        ts_raw = (d / 'ts').read_text(encoding='utf-8').strip()
        owner = (d / 'owner').read_text(encoding='utf-8').strip()
        if not owner:
            return None
        try:
            ctime_ns = os.stat(d).st_ctime_ns
        except OSError:
            ctime_ns = None
        return {'pid': int(pid_raw), 'ts': float(ts_raw),
                'pid_raw': pid_raw, 'ts_raw': ts_raw,
                'owner': owner, 'ctime_ns': ctime_ns}
    except Exception:
        return None


def _lock_observe(d):
    if not d.exists():
        return 'absent', None
    meta = _lock_meta(d)
    if meta is None:
        return 'busy', None  # 元数据不完整 → 不可窃取
    state = _pid_state(meta['pid'])
    expired = (time.time() - meta['ts']) > LOCK_TTL
    if state == 'dead' and expired:
        return 'stale', meta
    return 'busy', meta  # live / unverifiable / dead 未过期 → 忙


def _lock_claim_stale(d, observed):
    tombstone = d.with_name(f"{d.name}.tombstone-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    try:
        os.rename(d, tombstone)
    except OSError:
        return None
    claimed = _lock_meta(tombstone)
    same = (
        claimed is not None
        and claimed['pid_raw'] == observed['pid_raw']
        and claimed['ts_raw'] == observed['ts_raw']
        and (os.name != 'nt'
             or claimed['ctime_ns'] is None
             or claimed['ctime_ns'] == observed['ctime_ns'])
    )
    if not same:
        try:
            os.rename(tombstone, d)
        except OSError:
            pass
        return None
    return tombstone


def lock_acquire(repo) -> bool:
    global _LOCK_TOKEN
    d = _lock_dir(repo)
    for _ in range(_MAX_ACQUIRE_ATTEMPTS):
        state, meta = _lock_observe(d)
        if state == 'busy':
            return False
        if state == 'stale':
            tombstone = _lock_claim_stale(d, meta)
            if tombstone is None:
                continue
            shutil.rmtree(tombstone, ignore_errors=True)
            continue
        token = f"{os.getpid()}-{uuid.uuid4().hex}"
        try:
            d.mkdir(parents=False)
        except FileExistsError:
            continue
        except OSError:
            return False
        _LOCK_TOKEN = token
        try:
            (d / 'pid').write_text(str(os.getpid()), encoding='utf-8')
            (d / 'ts').write_text(str(time.time()), encoding='utf-8')
            (d / 'owner').write_text(token, encoding='utf-8')
        except Exception:
            pass
        return True
    return False


def lock_release(repo):
    global _LOCK_TOKEN
    if not _LOCK_TOKEN:
        return
    d = _lock_dir(repo)
    try:
        owner = (d / 'owner').read_text(encoding='utf-8').strip()
    except Exception:
        return
    if owner != _LOCK_TOKEN:
        return
    _LOCK_TOKEN = None
    shutil.rmtree(d, ignore_errors=True)


# ─── 四动作 ───────────────────────────────────────────────────────────────────

def _result(result, rc, **extra):
    payload = {'result': result}
    payload.update(extra)
    return payload, rc


def create(repo, wt_root=None):
    repo = Path(repo)
    wt_root = Path(wt_root) if wt_root else _default_wt_root(repo)
    canonical = _canonical_ref(repo)
    err = canonical_error(repo, canonical)
    if err:
        return _result(RESULT_NOT_CANONICAL, 1, detail=err)
    try:
        wt_root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return _result(RESULT_REFUSED, 1, detail=f'worktree root unavailable: {e}')
    task_id = datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    branch = BRANCH_PREFIX + task_id
    base = _rev_parse(repo, canonical)
    if not base:
        return _result(RESULT_NOT_CANONICAL, 1, detail='canonical ref unresolvable')
    wt_path = wt_root / task_id
    rc, _, stderr = _git(repo, 'worktree', 'add', str(wt_path), '-b', branch, base)
    if rc != 0:
        return _result(RESULT_REFUSED, 1, detail=stderr)
    return _result(RESULT_CREATED, 0, id=task_id, branch=branch,
                   path=str(wt_path), base=base, canonical=canonical)


def check(repo, wt_root=None, task_id=None):
    repo = Path(repo)
    wt_root = Path(wt_root) if wt_root else _default_wt_root(repo)
    canonical = _canonical_ref(repo)
    st = _task_state(repo, wt_root, task_id, canonical)
    if not st['branch_tip'] and not st['registered']:
        return _result(RESULT_NOT_FOUND, 1, id=task_id)
    keys = ('id', 'branch', 'branch_tip', 'registered', 'reg_path', 'reg_branch',
            'reg_head', 'foreign_reg_path', 'path', 'path_exists', 'clean',
            'canonical_tip', 'ahead', 'behind', 'integrated')
    return _result(RESULT_OK, 0, canonical=canonical,
                   **{k: st.get(k) for k in keys})


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
    repo = Path(repo)
    wt_root = Path(wt_root) if wt_root else _default_wt_root(repo)
    canonical = _canonical_ref(repo)
    st = _task_state(repo, wt_root, task_id, canonical)
    any_reg = st['registered'] or bool(st['foreign_reg_path'])
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
    if not st['integrated']:
        return _result(RESULT_REFUSED, 1, id=task_id,
                       detail='task tip is not an ancestor of canonical')
    rc, _, stderr = _git(repo, 'worktree', 'remove', st['reg_path'])
    if rc != 0:
        return _result(RESULT_REFUSED, 1, id=task_id, detail=stderr)
    rc, _, stderr = _git(repo, 'branch', '-d', st['branch'])
    if rc != 0:
        return _result(RESULT_PARTIAL_STATE, 1, id=task_id,
                       detail=f'worktree removed but branch delete failed: {stderr}')
    return _result(RESULT_CLEANED, 0, id=task_id)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='worktree task helper（四动作）')
    parser.add_argument('action', choices=['create', 'check', 'integrate', 'cleanup'])
    parser.add_argument('id', nargs='?', default=None)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--wt-root', default=None,
                        help='覆盖 worktree 根目录（默认见模块 docstring）')
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    wt_root = Path(args.wt_root) if args.wt_root else None

    if args.action == 'create':
        payload, rc = create(repo, wt_root)
    else:
        if not args.id:
            parser.error(f'{args.action} 需要 <id>')
        payload, rc = {
            'check': check,
            'integrate': integrate,
            'cleanup': cleanup,
        }[args.action](repo, wt_root, args.id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return rc


if __name__ == '__main__':
    sys.exit(main())

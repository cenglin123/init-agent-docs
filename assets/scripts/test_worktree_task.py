"""worktree_task.py 主工作树占用声明（main-claim）的单元测试。

用临时 GIT 仓隔离，不触碰真实主工作树与任务登记。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / 'worktree_task.py'


def _run(repo, *args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), '--repo', str(repo), *args],
        capture_output=True, text=True, encoding='utf-8',
    )
    assert proc.returncode in (0, 1), f'unexpected crash: {proc.stderr}'
    import json as m
    return m.loads(proc.stdout)


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / 'repo'
    r.mkdir()
    def git(*a):
        subprocess.run(['git', *a], cwd=r, check=True, capture_output=True)
    git('init', '-b', 'master')
    git('config', 'user.email', 't@example.test')
    git('config', 'user.name', 't')
    (r / 'f.txt').write_text('x', encoding='utf-8')
    git('add', 'f.txt')
    git('commit', '-m', 'init')
    return r


def test_claim_then_others_refused(repo):
    first = _run(repo, 'claim-main', '--owner', 'primary', '--ttl-minutes', '60')
    assert first['result'] == 'ok'
    second = _run(repo, 'claim-main', '--owner', 'fork-agent', '--ttl-minutes', '60')
    assert second['result'] == 'refused'
    assert second['holder'] == 'primary'


def test_same_owner_renews(repo):
    _run(repo, 'claim-main', '--owner', 'primary', '--ttl-minutes', '60')
    renewed = _run(repo, 'claim-main', '--owner', 'primary', '--ttl-minutes', '60')
    assert renewed['result'] == 'ok'
    assert renewed['renewed'] is True


def test_release_and_status(repo):
    _run(repo, 'claim-main', '--owner', 'primary')
    st = _run(repo, 'main-claim')
    assert st['claimed'] is True and st['owner'] == 'primary'
    released = _run(repo, 'release-main', '--owner', 'primary')
    assert released['result'] == 'ok' and released['released'] is True
    st = _run(repo, 'main-claim')
    assert st['claimed'] is False


def test_release_refused_for_other_owner(repo):
    _run(repo, 'claim-main', '--owner', 'primary')
    refused = _run(repo, 'release-main', '--owner', 'fork-agent')
    assert refused['result'] == 'refused'
    assert refused['holder'] == 'primary'


def test_expired_claim_allows_takeover(repo):
    _run(repo, 'claim-main', '--owner', 'primary', '--ttl-minutes', '0')
    taken = _run(repo, 'claim-main', '--owner', 'fork-agent', '--ttl-minutes', '60')
    assert taken['result'] == 'ok'
    st = _run(repo, 'main-claim')
    assert st['owner'] == 'fork-agent'


def test_requires_owner(repo):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), '--repo', str(repo), 'claim-main'],
        capture_output=True, text=True, encoding='utf-8',
    )
    assert proc.returncode == 2


def test_force_rejected_on_active_others(repo):
    """--force 不豁免：他人持有未过期 claim 时强夺被拒（独立审计 high：
    原实现 --force 无条件覆盖他人活动占用，等于绕过协调）。"""
    _run(repo, 'claim-main', '--owner', 'primary', '--ttl-minutes', '60')
    forced = _run(repo, 'claim-main', '--owner', 'fork-agent', '--force')
    assert forced['result'] == 'refused'
    assert forced['holder'] == 'primary'
    st = _run(repo, 'main-claim')
    assert st['owner'] == 'primary'


def test_renewal_keeps_claimed_at_resets_expiry(repo):
    """同 owner 续期：claimed_at 保留首次时刻（审计链），expires 重置为 now+ttl
    （独立审计 high：原实现把 ttl 叠加到旧到期时间上，窗口无上限累加）。"""
    from datetime import datetime as dt
    _run(repo, 'claim-main', '--owner', 'primary', '--ttl-minutes', '60')
    first = _run(repo, 'main-claim')
    renewed = _run(repo, 'claim-main', '--owner', 'primary', '--ttl-minutes', '60')
    assert renewed['renewed'] is True
    st = _run(repo, 'main-claim')
    assert st['claimed_at'] == first['claimed_at']
    exp = dt.strptime(st['expires_at'], '%Y-%m-%d %H:%M:%S')
    now = dt.now()
    assert now + __import__('datetime').timedelta(minutes=55) <= exp <= now + __import__('datetime').timedelta(minutes=65)


def test_corrupted_json_tolerated(repo):
    """损坏的状态文件按无占用容错：status 正常返回、claim 正常覆盖（独立审计 high：
    原实现对非 dict JSON 抛 AttributeError，四个动作全崩）。"""
    claim_file = repo / '.git' / 'worktree-task' / 'main-claim.json'
    claim_file.parent.mkdir(parents=True, exist_ok=True)
    claim_file.write_text('[1, 2, 3', encoding='utf-8')
    st = _run(repo, 'main-claim')
    assert st['claimed'] is False
    ok = _run(repo, 'claim-main', '--owner', 'primary', '--ttl-minutes', '60')
    assert ok['result'] == 'ok'
    st = _run(repo, 'main-claim')
    assert st['claimed'] is True


@pytest.mark.parametrize('bad', ['null', '[]', '123', '"text"'])
def test_non_dict_json_tolerated_for_status_and_release(repo, bad):
    """P3-1：非 dict 的合法 JSON 一律视作无占用，release 不抛 AttributeError。"""
    claim_file = repo / '.git' / 'worktree-task' / 'main-claim.json'
    claim_file.parent.mkdir(parents=True, exist_ok=True)
    claim_file.write_text(bad, encoding='utf-8')
    assert _run(repo, 'main-claim')['claimed'] is False
    released = _run(repo, 'release-main', '--owner', 'primary')
    assert released['result'] == 'not-found'
    claim_file.write_text(bad, encoding='utf-8')
    assert _run(repo, 'claim-main', '--owner', 'primary')['result'] == 'ok'


def test_claim_and_release_report_lock_busy(repo):
    """P2-1：claim-main / release-main 与 integrate 共用 mutation_lock。"""
    lock = repo / '.git' / 'worktree-task' / 'mutation.lock'
    lock.mkdir(parents=True)
    (lock / 'owner').write_text('other', encoding='utf-8')
    assert _run(repo, 'claim-main', '--owner', 'primary')['result'] == 'lock-busy'
    assert _run(repo, 'release-main', '--owner', 'primary')['result'] == 'lock-busy'


def test_claim_write_leaves_no_temp_file(repo):
    """P2-1：同目录临时文件 + os.replace 原子写入，不残留 .tmp。"""
    _run(repo, 'claim-main', '--owner', 'primary')
    state = repo / '.git' / 'worktree-task'
    assert not [p for p in state.iterdir() if p.name.endswith('.tmp')]
    assert json.loads((state / 'main-claim.json').read_text(encoding='utf-8'))['owner'] == 'primary'

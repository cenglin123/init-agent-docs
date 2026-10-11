"""Cooperative admission tests against throwaway Git repositories."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.test_worktree_task_asset import RepoFixture, SCRIPT, commit_file, git, wtask


class CoordinationTests(RepoFixture):
    def task(self, name, owner):
        payload, rc = wtask.create(self.repo, self.wt_root, name=name, owner=owner)
        self.assertEqual(rc, 0, payload)
        self.assertIn(name.lower().replace(' ', '-'), payload['branch'])
        return payload

    def scope(self, task, owner, path, goal='Work'):
        payload, rc = wtask.intent(self.repo, task['id'], owner, 1, goal,
                                   'Do not edit unrelated files', ['module scope'], [path])
        self.assertEqual(rc, 0, payload)
        return payload['intent']['revision']

    def digest(self, task, owner, repo=None):
        payload, rc = wtask.review(repo or self.repo, task['id'], owner, 1)
        self.assertEqual(rc, 0, payload)
        return payload

    def test_display_name_once_and_read_only_across_entries(self):
        a = self.task('Alpha Site', 'agent-a')
        b = self.task('Beta Docs', 'agent-b')
        self.assertEqual(wtask.resume(self.repo, a['id'], 'agent-a', 1)[1], 0)
        self.assertRaises(ValueError, wtask.resume, self.repo, a['id'], 'agent-b', 1)
        self.scope(a, 'agent-a', 'site/index.html')
        self.scope(b, 'agent-b', 'docs/guide.md')
        registry = wtask._registry_dir(self.repo)
        before = {p.name: p.read_bytes() for p in registry.glob('*.json')}
        self.assertFalse(wtask._lock_dir(self.repo).exists())
        from_main = wtask.list_tasks(self.repo)[0]['tasks']
        from_a = wtask.list_tasks(Path(a['path']))[0]['tasks']
        from_b = wtask.list_tasks(Path(b['path']))[0]['tasks']
        self.assertEqual(from_main, from_a)
        self.assertEqual(from_main, from_b)
        review_a = self.digest(a, 'agent-a', Path(a['path']))
        self.assertEqual(review_a['peers'][0]['id'], b['id'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in registry.glob('*.json')})
        self.assertFalse(wtask._lock_dir(self.repo).exists())
        self.assertEqual(wtask.admit(self.repo, a['id'], 'agent-a', 1, review_a['digest'])[1], 0)
        self.assertEqual(wtask.check(Path(a['path']), self.wt_root, a['id'],
                                     owner='agent-a', generation=1, write=True)[1], 0)
        self.scope(b, 'agent-b', 'docs/new-guide.md')
        result, rc = wtask.check(Path(a['path']), self.wt_root, a['id'],
                                 owner='agent-a', generation=1, write=True)
        self.assertEqual(rc, 0, result)
        self.assertEqual(result['review_refresh'], [b['id']])

    def test_overlap_requires_same_current_protocol(self):
        a = self.task('Alpha Site', 'agent-a')
        b = self.task('Beta Docs', 'agent-b')
        self.scope(a, 'agent-a', 'site/index.html')
        self.scope(b, 'agent-b', 'site')
        first = self.digest(a, 'agent-a')
        self.assertEqual(first['peers'][0]['path_overlap'], [['site/index.html', 'site']])
        with self.assertRaises(ValueError):
            wtask.admit(self.repo, a['id'], 'agent-a', 1, first['digest'])
        wtask.coordinate(self.repo, a['id'], 'agent-a', 1, b['id'], 1, 'A owns markup; B owns copy')
        wtask.coordinate(self.repo, b['id'], 'agent-b', 1, a['id'], 1, 'Conflicting protocol')
        with self.assertRaises(ValueError):
            wtask.admit(self.repo, a['id'], 'agent-a', 1, self.digest(a, 'agent-a')['digest'])
        wtask.coordinate(self.repo, b['id'], 'agent-b', 1, a['id'], 1, 'A owns markup; B owns copy')
        self.assertEqual(wtask.admit(self.repo, a['id'], 'agent-a', 1,
                                     self.digest(a, 'agent-a')['digest'])[1], 0)
        self.assertEqual(wtask.check(Path(a['path']), self.wt_root, a['id'],
                                     owner='agent-a', generation=1, write=True)[1], 0)
        wtask.coordinate(self.repo, b['id'], 'agent-b', 1, a['id'], 1, 'Changed protocol')
        with self.assertRaises(ValueError):
            wtask.check(Path(a['path']), self.wt_root, a['id'],
                        owner='agent-a', generation=1, write=True)

    def test_related_revision_and_legacy_unknown_override(self):
        a = self.task('Alpha Site', 'agent-a')
        self.scope(a, 'agent-a', 'site/index.html')
        legacy, rc = wtask.create(self.repo, self.wt_root)
        self.assertEqual(rc, 0, legacy)
        view = self.digest(a, 'agent-a')
        self.assertEqual(view['peers'][0]['status'], 'unknown')
        peer_id = view['peers'][0]['id']
        with self.assertRaises(ValueError):
            wtask.admit(self.repo, a['id'], 'agent-a', 1, view['digest'])
        wtask.coordinate(self.repo, a['id'], 'agent-a', 1, peer_id, 0,
                         authorized_by='project-lead', reason='Legacy owner unavailable',
                         boundary='Only site/index.html; no legacy changes copied')
        current = self.digest(a, 'agent-a')
        self.assertEqual(wtask.admit(self.repo, a['id'], 'agent-a', 1, current['digest'])[1], 0)
        self.scope(a, 'agent-a', 'site/new.html')
        with self.assertRaises(ValueError):
            wtask.check(Path(a['path']), self.wt_root, a['id'],
                        owner='agent-a', generation=1, write=True)

    def test_dependency_needs_committed_sha(self):
        a = self.task('Alpha Site', 'agent-a')
        b = self.task('Beta Docs', 'agent-b')
        with self.assertRaises(ValueError):
            wtask.intent(self.repo, a['id'], 'agent-a', 1, 'A', 'Not B', [], [], [b['id']])
        with self.assertRaises(ValueError):
            wtask.intent(self.repo, a['id'], 'agent-a', 1, 'A', 'Not B', [], [],
                         ['missing1@' + self.base])
        payload, rc = wtask.intent(self.repo, a['id'], 'agent-a', 1, 'A', 'Not B', [], [],
                                   [b['id'] + '@' + self.base])
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload['intent']['depends_on'][0]['sha'], self.base)
        self.assertEqual(self.digest(a, 'agent-a')['own_dependencies'][0]['id'], b['id'])

    def test_literal_path_hints_are_conservative(self):
        self.assertEqual(wtask._path_hint('Site\\Index.HTML'), 'site/index.html')
        self.assertEqual(wtask._path_hint('.agents/memory/MEMORY.md'),
                         '.agents/memory/memory.md')
        for bad in ('/outside', '../outside', 'a/../b', 'C:/outside', 'a/*'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                wtask._path_hint(bad)

    def test_related_revision_invalidates_admission(self):
        a = self.task('Alpha Site', 'agent-a')
        b = self.task('Beta Docs', 'agent-b')
        self.scope(a, 'agent-a', 'site/index.html')
        self.scope(b, 'agent-b', 'site')
        protocol = 'A edits markup; B edits prose'
        wtask.coordinate(self.repo, a['id'], 'agent-a', 1, b['id'], 1, protocol)
        wtask.coordinate(self.repo, b['id'], 'agent-b', 1, a['id'], 1, protocol)
        self.assertEqual(wtask.admit(self.repo, a['id'], 'agent-a', 1,
                                     self.digest(a, 'agent-a')['digest'])[1], 0)
        self.scope(b, 'agent-b', 'site/new.html')
        with self.assertRaises(ValueError):
            wtask.check(Path(a['path']), self.wt_root, a['id'],
                        owner='agent-a', generation=1, write=True)

    def test_closed_committed_dependency_remains_visible_to_owner(self):
        a = self.task('Alpha Site', 'agent-a')
        b = self.task('Beta Docs', 'agent-b')
        self.assertEqual(wtask.close(self.repo, b['id'], 'agent-b', 1)[1], 0)
        self.assertEqual(wtask.intent(self.repo, a['id'], 'agent-a', 1, 'A', 'Not B',
                                      [], ['site/index.html'], [b['id'] + '@' + self.base])[1], 0)
        view = self.digest(a, 'agent-a')
        self.assertEqual(view['peers'], [])
        self.assertEqual(view['own_dependencies'][0]['id'], b['id'])
        self.assertEqual(wtask.admit(self.repo, a['id'], 'agent-a', 1, view['digest'])[1], 0)

    def test_close_requires_integrated_clean_and_keeps_audit_branch(self):
        a = self.task('Alpha Site', 'agent-a')
        commit_file(Path(a['path']), 'alpha.md', 'alpha\n', 'alpha')
        with self.assertRaises(ValueError):
            wtask.close(self.repo, a['id'], 'agent-a', 1)
        self.assertEqual(wtask.integrate(self.repo, self.wt_root, a['id'])[1], 0)
        self.assertEqual(wtask.close(self.repo, a['id'], 'agent-a', 1)[1], 0)
        self.assertRaises(ValueError, wtask.resume, self.repo, a['id'], 'agent-a', 1)
        cleaned, rc = wtask.cleanup(self.repo, self.wt_root, a['id'])
        self.assertEqual(rc, 0, cleaned)
        self.assertTrue(cleaned['branch_retained'])
        self.assertIsNotNone(wtask._rev_parse(self.repo, 'refs/heads/' + a['branch']))
        self.assertEqual(wtask.cleanup(self.repo, self.wt_root, a['id'])[0]['result'],
                         'already-cleaned')

    def test_register_existing_managed_worktree_without_renaming_branch(self):
        managed = self.root / 'managed-worktree'
        git(self.repo, 'worktree', 'add', '-b', 'feature/owned-by-other-host',
            str(managed), self.base)
        row, rc = wtask.register(self.repo, 'managed1', 'Managed Task', 'agent-managed',
                                 managed, self.base)
        self.assertEqual(rc, 0, row)
        self.assertEqual(row['branch'], 'feature/owned-by-other-host')
        self.assertEqual(wtask.resume(managed, 'managed1', 'agent-managed', 1)[1], 0)
        with self.assertRaises(ValueError):
            wtask.register(self.repo, 'managed2', 'Another Task', 'agent-other',
                           managed, self.base)

    def test_cleanup_refuses_ignored_user_data(self):
        a = self.task('Alpha Site', 'agent-a')
        commit_file(Path(a['path']), '.gitignore', 'private.tmp\n', 'ignore rule')
        self.assertEqual(wtask.integrate(self.repo, self.wt_root, a['id'])[1], 0)
        self.assertEqual(wtask.close(self.repo, a['id'], 'agent-a', 1)[1], 0)
        private = Path(a['path']) / 'private.tmp'
        private.write_text('fixture only', encoding='utf-8')
        result, rc = wtask.cleanup(self.repo, self.wt_root, a['id'])
        self.assertEqual(rc, 1, result)
        self.assertTrue(private.exists())
        self.assertIn('ignored', result['detail'])

    def test_public_cli_forward_flow(self):
        def cli(*args):
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                                  capture_output=True, text=True)
            return json.loads(proc.stdout), proc.returncode
        task, rc = cli('create', '--repo', str(self.repo), '--wt-root', str(self.wt_root),
                       '--name', 'Forward Flow', '--owner', 'agent-forward')
        self.assertEqual(rc, 0, task)
        self.assertEqual(cli('resume', task['id'], '--repo', str(self.repo),
                             '--owner', 'agent-forward', '--generation', '1')[1], 0)
        self.assertEqual(cli('intent', task['id'], '--repo', str(self.repo),
                             '--owner', 'agent-forward', '--generation', '1',
                             '--goal', 'Edit a file', '--non-goal', 'Other files',
                             '--path', 'note.md')[1], 0)
        review, rc = cli('review', task['id'], '--repo', str(task['path']),
                         '--owner', 'agent-forward', '--generation', '1')
        self.assertEqual(rc, 0, review)
        self.assertEqual(cli('admit', task['id'], '--repo', str(task['path']),
                             '--owner', 'agent-forward', '--generation', '1',
                             '--review-digest', review['digest'])[1], 0)
        self.assertEqual(cli('check', task['id'], '--repo', str(task['path']),
                             '--wt-root', str(self.wt_root), '--owner', 'agent-forward',
                             '--generation', '1', '--write')[1], 0)

    def test_help_is_console_encoding_safe(self):
        proc = subprocess.run([sys.executable, '-B', str(SCRIPT), '--help'],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.isascii())

"""Run the public document tools after relocating them to a knowledge base."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'scripts'


class KnowledgeBaseLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / '测试库'
        self.scripts = self.root / '.meta' / 'scripts'
        self.scripts.mkdir(parents=True)
        for name in ('audit.py', 'changelog.py', 'check_all.py', 'maintain.py'):
            shutil.copyfile(ASSETS / name, self.scripts / ('docs_maintain.py' if name == 'maintain.py' else name))
        (self.root / 'docs').mkdir()
        (self.root / 'docs' / 'initialization.md').write_text('# Initialization\n', encoding='utf-8')
        (self.root / 'docs' / 'CHANGELOG.md').write_text('# CHANGELOG\n', encoding='utf-8')
        (self.root / 'AGENTS.md').write_text('# Test\n## 项目记忆\n.meta/memory/MEMORY.md\n', encoding='utf-8')
        mem = self.root / '.meta' / 'memory'
        (mem / 'user').mkdir(parents=True)
        (mem / 'user' / 'role.md').write_text('# 用户\nPreserved prose.\n', encoding='utf-8')
        self.index = mem / 'MEMORY.md'
        self.index.write_text('# Memory\n<!-- memory-index:start -->\nKB unique section\n<!-- memory-index:end -->\n', encoding='utf-8')
        self.run_tool('changelog.py', 'add', '--title', 'Initialization', '--body', 'Test')

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, name, *args, expected=0):
        env = dict(os.environ, PYTHONUTF8='1')
        result = subprocess.run([sys.executable, str(self.scripts / name), *args], cwd=self.root,
                                capture_output=True, text=True, encoding='utf-8', env=env)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result.stdout

    def test_changelog_and_completion_tools_find_real_root(self):
        self.assertIn('Initialization', self.run_tool('changelog.py', 'titles'))
        self.run_tool('audit.py', 'check')
        self.run_tool('check_all.py', '--quiet')
        self.assertFalse((self.root / 'scripts').exists())

    def test_audit_checks_meta_memory_instead_of_skipping(self):
        self.index.unlink()
        output = self.run_tool('audit.py', 'memory', expected=1)
        self.assertIn('.meta/memory/MEMORY.md', output)

    def test_missing_meta_memory_directory_fails_all_document_checks(self):
        shutil.rmtree(self.index.parent)
        self.run_tool('audit.py', 'memory', expected=1)
        self.run_tool('check_all.py', '--quiet', expected=1)
        self.run_tool('docs_maintain.py', '--check', expected=1)

    def test_docs_maintainer_delegates_index_without_overwriting(self):
        (self.scripts / 'memory_index.py').write_text("print('KB index checked')\n", encoding='utf-8')
        before = self.index.read_bytes()
        self.assertIn('KB index checked', self.run_tool('docs_maintain.py', '--check'))
        self.run_tool('docs_maintain.py', '--memory-index')
        self.assertEqual(before, self.index.read_bytes())

    def test_failed_kb_index_is_not_reported_as_healthy(self):
        (self.scripts / 'memory_index.py').write_text("raise SystemExit(1)\n", encoding='utf-8')
        self.run_tool('docs_maintain.py', '--check', expected=1)
        self.run_tool('docs_maintain.py', '--memory-index', expected=1)


if __name__ == '__main__':
    unittest.main()

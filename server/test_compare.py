"""Behavioral coverage using real Git repositories; no provider calls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import app
import git_compare as gc
import python_imports
from python_imports import extract_imports


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'core.autocrlf', 'false')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL).decode().strip()

    def write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('w', encoding='utf-8', newline='') as stream:
            stream.write(text)

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def history(self):
        self.write('pkg/__init__.py', '')
        self.write('pkg/main.py', 'from . import old\nfrom . import util\n')
        self.write('pkg/old.py', 'value = 1\n')
        self.write('pkg/util.py', 'value = 1\n')
        self.write('pkg/moved.py', 'def stable():\n    return 42\n')
        self.write('README.md', 'Example\n')
        base = self.commit('baseline')
        self.git('checkout', '-b', 'feature')
        self.git('mv', 'pkg/moved.py', 'pkg/renamed.py')
        self.git('rm', 'pkg/old.py')
        self.write('pkg/new.py', 'value = 2\n')
        self.write('pkg/main.py', 'from . import new\nfrom . import util\nimport missing_library\n')
        self.write('pkg/util.py', 'value = 2\n')
        head = self.commit('change dependencies')
        self.git('checkout', 'main')
        self.write('only_on_main.py', 'x = 1\n')
        self.commit('base advances')
        return base, head

    def compare(self, base='main', head='feature', **kwargs):
        return gc.compare_repository(str(self.repo), base, head, [self.repo], **kwargs)

    def test_merge_base_graph_evidence_rename_and_dirty_worktree(self):
        base, head = self.history()
        self.write('README.md', 'dirty staged\n')
        self.git('add', 'README.md')
        self.write('pkg/util.py', 'dirty unstaged\n')
        self.write('untracked.py', 'not part of snapshot\n')
        status = self.git('status', '--porcelain=v1')
        with patch('urllib.request.urlopen', side_effect=AssertionError('No network')):
            result = self.compare()
        self.assertEqual(result['mergeBaseSha'], base)
        self.assertEqual(result['headSha'], head)
        self.assertNotEqual(result['baseSha'], base)
        self.assertEqual(self.git('status', '--porcelain=v1'), status)
        nodes = {n['afterPath'] or n['beforePath']: n for n in result['nodes']}
        self.assertNotIn('only_on_main.py', nodes)
        self.assertNotIn('untracked.py', nodes)
        self.assertEqual(nodes['pkg/util.py']['status'], 'modified')
        self.assertEqual(nodes['pkg/old.py']['status'], 'removed')
        self.assertEqual(nodes['pkg/new.py']['status'], 'added')
        self.assertEqual(nodes['pkg/renamed.py']['beforePath'], 'pkg/moved.py')
        self.assertTrue(nodes['pkg/renamed.py']['renamed'])
        self.assertEqual(nodes['pkg/renamed.py']['status'], 'modified')
        edges = {(e['source'], e['target']): e for e in result['edges']}
        source = nodes['pkg/main.py']['id']
        self.assertEqual(edges[source, nodes['pkg/old.py']['id']]['status'], 'removed')
        added = edges[source, nodes['pkg/new.py']['id']]
        self.assertEqual(added['status'], 'added')
        self.assertEqual(added['after'][0]['revision'], head)
        self.assertEqual(added['after'][0]['startLine'], 1)
        self.assertTrue(any('missing_library' in n['reason'] for n in result['notices']))
        self.assertTrue(any(n['path'] == 'README.md' for n in result['notices']))
        deleted = gc.comparison_detail(result, nodes['pkg/old.py']['id'])
        self.assertIsNone(deleted['after'])
        self.assertIn('-value = 1', deleted['diff'])
        self.assertEqual(deleted['before']['revision'], base)
        detail = gc.comparison_detail(result, nodes['pkg/util.py']['id'])
        self.assertEqual(detail['after']['content'], 'value = 2\n')
        self.assertIn('+value = 2', detail['diff'])
        public = gc.public_comparison(result)
        self.assertFalse(any(k.startswith('_') for k in public))
        self.assertNotIn('dirty unstaged', json.dumps(public))
        with self.assertRaises(ValueError):
            gc.comparison_detail(result, '../../.env')

    def test_validation_scope_exclusions_and_limits(self):
        self.history()
        with self.assertRaisesRegex(ValueError, 'configured'):
            gc.compare_repository(str(self.repo), 'main', 'feature', [self.repo / 'other'])
        for ref in ['--help', 'not-a-revision', 'HEAD\x00']:
            with self.assertRaises(ValueError):
                self.compare(head=ref)
        for root in ['../', '/', '/tmp', 'C:/tmp', 'pkg/../', 'missing']:
            with self.assertRaises(ValueError):
                self.compare(source_root=root)
        self.write('.env', 'must never return\n')
        self.write('pkg/secrets.py', 'must never return\n')
        self.write('binary.py', '\x00bad')
        self.write('vendor.js', 'const x = 1;\n')
        self.commit('excluded inputs')
        result = self.compare(head='main')
        self.assertNotIn('must never return', json.dumps(result))
        self.assertTrue(any('binary' in n['reason'] for n in result['notices']))
        scoped = self.compare(head='main', source_root='pkg')
        self.assertTrue(all((n['afterPath'] or n['beforePath']).startswith('pkg/') for n in scoped['nodes']))
        with patch.object(gc, 'MAX_FILE', 8):
            with self.assertRaisesRegex(ValueError, 'limit'):
                self.compare()

    def test_missing_ancestry_and_no_changes(self):
        self.history()
        self.git('checkout', '--orphan', 'unrelated')
        self.git('rm', '-rf', '.')
        self.write('other.py', 'pass\n')
        self.commit('unrelated root')
        with self.assertRaisesRegex(ValueError, 'ancestor|merge base'):
            self.compare(head='unrelated')
        result = self.compare(base='feature', head='feature')
        self.assertTrue(all(n['status'] == 'unchanged' for n in result['nodes']))
        self.assertTrue(all(e['status'] == 'unchanged' for e in result['edges']))

    def test_python_resolution_is_conservative_and_has_line_evidence(self):
        files = {p: {'content': content} for p, content in {
            'src/pkg/__init__.py': 'from . import helper\n',
            'src/pkg/helper.py': 'VALUE = 3\n',
            'src/pkg/use.py': 'from pkg.helper import VALUE\nfrom . import helper\nfrom pkg import unknown\nimport pkg.helper\nimport importlib\nimportlib.import_module("pkg.helper")\n',
            'src/dup.py': '', 'src/dup/__init__.py': '',
            'src/bad.py': 'import dup\nfrom ... import escape\n',
            'src/syntax.py': 'def !\n',
        }.items()}
        edges, notices = extract_imports(files, 'revision', 'src')
        refs = [e for e in edges if e['source'] == 'src/pkg/use.py' and e['target'] == 'src/pkg/helper.py']
        self.assertEqual([e['startLine'] for e in refs], [1, 2, 4])
        self.assertTrue(all(e['revision'] == 'revision' and e['endLine'] >= e['startLine'] for e in edges))
        self.assertTrue(any('ambiguous' in n['reason'].lower() for n in notices))
        self.assertTrue(any('syntax' in n['reason'].lower() for n in notices))
        self.assertTrue(any('unknown' in n['reason'] for n in notices))
        self.assertTrue(any('dynamic' in n['reason'].lower() for n in notices))

    def test_http_compare_protection_and_snapshot_detail(self):
        self.history()
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        server.roots, server.origin = [self.repo], 'http://127.0.0.1:5173'
        server.projects, server.comparisons, server.lock = {}, {}, threading.Lock()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}'
        def post(path, body, origin=server.origin):
            req = urllib.request.Request(url + path, data=json.dumps(body).encode(), headers={
                'Origin': origin, 'X-CodeMap-Request': '1', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req) as response:
                return json.load(response)
        body = {'path': str(self.repo), 'base': 'main', 'head': 'feature'}
        with self.assertRaises(urllib.error.HTTPError) as error:
            post('/api/compare', body, 'https://example.test')
        self.assertEqual(error.exception.code, 403)
        result = post('/api/compare', body)
        self.assertNotIn('_before', result)
        node = next(n for n in result['nodes'] if n['afterPath'] == 'pkg/util.py')
        detail = post('/api/compare/detail', {'id': result['id'], 'nodeId': node['id']})
        self.assertEqual(detail['id'], result['id'])
        self.assertIn('+value = 2', detail['diff'])
        with self.assertRaises(urllib.error.HTTPError):
            post('/api/compare/detail', {'id': 'expired', 'nodeId': node['id']})

    def test_git_controls_symlinks_and_resource_bounds(self):
        self.history()
        # A tracked symlink can be created without filesystem symlink privileges.
        oid = subprocess.check_output(['git', '-C', str(self.repo), 'hash-object', '-w', '--stdin'], input=b'../outside.py').decode().strip()
        self.git('update-index', '--add', '--cacheinfo', '120000,' + oid + ',linked.py')
        self.git('commit', '-m', 'tracked symlink')
        self.git('config', 'diff.external', 'this-command-must-not-run')
        with patch.dict(os.environ, {'GIT_DIR': str(self.repo / 'nonexistent')}):
            result = self.compare(head='main')
        self.assertTrue(any(n['path'] == 'linked.py' and 'Symlink' in n['reason'] for n in result['notices']))
        self.assertFalse(any(n['afterPath'] == 'linked.py' for n in result['nodes']))
        with patch.object(gc, 'MAX_FILES', 2):
            with self.assertRaisesRegex(ValueError, 'limit'):
                self.compare()
        with patch.object(gc, 'MAX_TOTAL', 4):
            with self.assertRaisesRegex(ValueError, 'limit'):
                self.compare()
        with self.assertRaisesRegex(ValueError, 'limit'):
            gc.git(self.repo, 'log', '--oneline', limit=1)

    def test_analysis_output_is_bounded_and_module_ancestors_are_checked(self):
        files = {'main.py': {'content': 'import helper\nimport helper\nimport helper\n'}, 'helper.py': {'content': ''}}
        with patch.object(python_imports, 'MAX_REFERENCES', 2):
            with self.assertRaisesRegex(ValueError, 'limit'):
                extract_imports(files, 'revision')
        with patch.object(python_imports, 'MAX_NOTICES', 2):
            with self.assertRaisesRegex(ValueError, 'limit'):
                extract_imports({'main.py': {'content': 'import a\nimport b\nimport c\n'}}, 'revision')
        edges, notices = extract_imports({
            'main.py': {'content': 'import blocked.child\n'},
            'blocked.py': {'content': ''}, 'blocked/child.py': {'content': ''},
        }, 'revision')
        self.assertEqual(edges, [])
        self.assertTrue(any('package' in n['reason'] for n in notices))


if __name__ == '__main__':
    unittest.main()

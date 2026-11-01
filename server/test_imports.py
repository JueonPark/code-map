import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from app import Handler
from app import import_path, import_zip, analyze


def archive(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name, value in entries.items():
            info = zipfile.ZipInfo()
            info.filename = name  # Preserve malicious backslashes on Windows too.
            z.writestr(info, value)
    return buf.getvalue()


class ImportTests(unittest.TestCase):
    def test_path_zip_equivalence_and_exclusions(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'main.py').write_text('print(42)')
            (root / '.env').write_text('SECRET=hidden')
            (root / 'image.png').write_bytes(b'\x00binary')
            a = import_path(str(root), [root])
            b = import_zip(archive({'project/main.py': 'print(42)', 'project/.env': 'SECRET=hidden', 'project/image.png': b'\x00binary'}), 'project.zip')
            self.assertEqual(a['files'], b['files'])
            self.assertEqual(len(a['excluded']), 2)
            self.assertFalse(a['approved'])

    def test_invalid_and_escaping_inputs(self):
        for name in ['../evil.py', '/evil.py', 'C:/evil.py', 'a/../../evil.py', 'a\\evil.py']:
            with self.assertRaises(ValueError):
                import_zip(archive({name: 'bad'}), 'bad.zip')
        for value in [b'not zip', archive({}), archive({'a.png': b'\x00'})]:
            with self.assertRaises(ValueError):
                import_zip(value, 'bad.zip')
        with self.assertRaises(ValueError):
            import_zip(archive({'.ssh/private.py': 'private data'}), 'hidden.zip')
        with self.assertRaises(ValueError):
            import_path('/this-path-does-not-exist-codemap', [Path('/')])
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                import_path(str(Path(d).parent), [Path(d)])

    def test_links_and_limits(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            info = zipfile.ZipInfo('link.py')
            info.external_attr = 0o120777 << 16
            z.writestr(info, '/etc/passwd')
        with self.assertRaises(ValueError):
            import_zip(buf.getvalue(), 'link.zip')
        with patch('app.MAX_TOTAL', 4):
            with self.assertRaises(ValueError):
                import_zip(archive({'main.py': '12345'}), 'large.zip')

    def test_analysis_requires_approval_and_configuration(self):
        p = import_zip(archive({'main.py': 'print(42)'}), 'demo.zip')
        with patch('app.urllib.request.urlopen') as upstream:
            with self.assertRaises(ValueError):
                analyze(p, {'prompt': 'explain'})
            p['approved'] = True
            with patch.dict('os.environ', {}, clear=True):
                with self.assertRaises(ValueError):
                    analyze(p, {'prompt': 'explain'})
            upstream.assert_not_called()

    def test_provider_receives_only_selected_snapshot(self):
        p = import_zip(archive({'main.py': 'only_this_project()', '.env': 'NEVER_SEND'}), 'demo.zip')
        p['approved'] = True
        response = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'diagram'}]}]}
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key', 'OPENAI_MODEL': 'test-model'}):
            with patch('app.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as upstream:
                self.assertEqual(analyze(p, {'prompt': 'graph', 'history': [{'role': 'user', 'content': 'earlier question'}]}), 'diagram')
                payload = json.loads(upstream.call_args.args[0].data)
                self.assertIn('only_this_project()', payload['input'][0]['content'])
                self.assertNotIn('NEVER_SEND', json.dumps(payload))
                self.assertFalse(payload['store'])
                self.assertEqual(payload['input'][-1]['content'], 'graph')

    def test_http_origin_and_preview(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.origin, server.roots, server.projects, server.lock = 'http://127.0.0.1:5173', [], {}, threading.Lock()
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/api/import/zip'
            body = archive({'main.py': 'print(42)'})
            for headers in [{}, {'Origin': 'https://attacker.example', 'X-CodeMap-Request': '1'}]:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers))
                self.assertEqual(error.exception.code, 403)
            headers = {'Origin': server.origin, 'X-CodeMap-Request': '1'}
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers)) as response:
                preview = json.load(response)
            self.assertFalse(preview['approved'])
            self.assertNotIn('content', preview['files'][0])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import json
import os
import struct
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from app import Handler
from app import import_path, import_zip, analyze
import app


def archive(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name, value in entries.items():
            info = zipfile.ZipInfo()
            info.filename = name  # Preserve malicious backslashes on Windows too.
            z.writestr(info, value)
    return buf.getvalue()


class ImportTests(unittest.TestCase):
    def test_directory_and_zip_above_legacy_size_limits(self):
        # 45 x 256 KiB exceeds both the old 2 MiB source and 10 MiB upload caps.
        content = b'#' * (256 * 1024)
        entries = {f'file_{i}.py': content for i in range(45)}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, raw in entries.items():
                (root / name).write_bytes(raw)
            directory = import_path(str(root), [root])
            zipped = import_zip(archive(entries), 'large.zip')
        self.assertEqual(directory['size'], 11796480)
        self.assertEqual(directory['files'], zipped['files'])

    def test_enough_entries_to_reach_one_gib_with_per_file_cap(self):
        # 4,096 files at the retained 256 KiB cap can hold 1 GiB.
        project = import_zip(archive({f'file_{i}.py': 'x' for i in range(4096)}), 'many.zip')
        self.assertEqual(len(project['files']), 4096)

    def test_source_and_upload_exact_boundaries(self):
        with tempfile.TemporaryDirectory() as d, patch('app.MAX_TOTAL', 8):
            root = Path(d)
            (root / 'a.py').write_bytes(b'1234')
            (root / 'b.py').write_bytes(b'5678')
            self.assertEqual(import_path(str(root), [root])['size'], 8)
            self.assertEqual(import_zip(archive({'a.py': '1234', 'b.py': '5678'}), 'exact.zip')['size'], 8)
            (root / 'b.py').write_bytes(b'56789')
            with self.assertRaisesRegex(ValueError, 'source limit'):
                import_path(str(root), [root])
            with self.assertRaisesRegex(ValueError, 'uncompressed'):
                import_zip(archive({'a.py': '1234', 'b.py': '56789'}), 'over.zip')
        raw = archive({'a.py': 'ok'})
        with patch('app.MAX_UPLOAD', len(raw)):
            self.assertEqual(import_zip(raw, 'exact.zip')['size'], 2)
            with self.assertRaisesRegex(ValueError, 'upload limit'):
                import_zip(raw + b'x', 'over.zip')

    def test_zip_stream_handles_short_reads_and_truncation(self):
        class ShortReads(io.BytesIO):
            def read(self, size=-1):
                if size < 0 or size > 1024 * 1024:
                    raise AssertionError('Upload must be read in bounded chunks')
                return super().read(min(size, 31))
        raw = archive({'a.py': 'print(42)'})
        project = app.receive_zip(ShortReads(raw), len(raw))
        self.assertEqual(project['files'][0]['content'], 'print(42)')
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            app.receive_zip(ShortReads(raw[:-1]), len(raw))
        with tempfile.TemporaryFile() as upload:
            upload.write(raw)
            self.assertEqual(import_zip(upload, 'disk.zip')['size'], 9)

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

    def test_corrupt_compressed_data_is_a_validation_error(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('main.py', 'print(42)')
        raw = bytearray(buf.getvalue())
        filename_size, extra_size = struct.unpack_from('<HH', raw, 26)
        raw[30 + filename_size + extra_size] = 7  # Invalid DEFLATE block type.
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            import_zip(bytes(raw), 'corrupt.zip')

    @unittest.skipIf(os.name == 'nt', 'Symlink creation requires Windows privileges; Linux race regression')
    def test_file_swap_cannot_read_outside_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'project'
            root.mkdir()
            source, outside = root / 'main.py', Path(d) / 'outside.py'
            source.write_text('allowed')
            outside.write_text('PRIVATE_OUTSIDE_ROOT')
            real_open = os.open
            def swap(path, flags, *args, **kwargs):
                if Path(path) == source:
                    source.unlink()
                    source.symlink_to(outside)
                return real_open(path, flags, *args, **kwargs)
            with patch('app.os.open', side_effect=swap):
                with self.assertRaises(ValueError):
                    import_path(str(root), [root])

    @unittest.skipIf(os.name == 'nt', 'Symlink creation requires Windows privileges; Linux race regression')
    def test_parent_swap_cannot_read_outside_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'project'
            folder = root / 'src'
            outside = Path(d) / 'outside'
            folder.mkdir(parents=True)
            outside.mkdir()
            (folder / 'main.py').write_text('allowed')
            (outside / 'main.py').write_text('PRIVATE_OUTSIDE_ROOT')
            real_open = os.open
            def swap(path, flags, *args, **kwargs):
                if Path(path) == folder / 'main.py':
                    folder.rename(root / 'old-src')
                    folder.symlink_to(outside, target_is_directory=True)
                return real_open(path, flags, *args, **kwargs)
            with patch('app.os.open', side_effect=swap):
                with self.assertRaises(ValueError):
                    import_path(str(root), [root])

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
            # Exercise the real HTTP upload path above the previous 10 MiB cap.
            large = archive({f'f{i}.py': b'x' * (256 * 1024) for i in range(41)})
            with urllib.request.urlopen(urllib.request.Request(url, data=large, headers=headers)) as response:
                self.assertEqual(json.load(response)['size'], 10747904)
            # Reject advertised >1 GiB uploads before reading/allocating their body.
            for endpoint, length in [('import/zip', 1073741825), ('import/path', 10485761)]:
                request = urllib.request.Request(url.replace('import/zip', endpoint), data=b'', headers={**headers, 'Content-Length': str(length)})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 400)
                self.assertIn('exceeds', json.load(error.exception)['error'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()

"""Opt-in real 1 GiB import boundary check. Needs ~2 GiB RAM and ~1.1 GiB disk."""
import gc
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from app import import_path, import_zip, receive_zip


def main():
    with tempfile.TemporaryDirectory(prefix='codemap-1gib-') as directory:
        base = Path(directory)
        root = base / 'project'
        root.mkdir()
        archive = base / 'project.zip'
        content = b'#' * 262144
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zipped:
            for i in range(4096):
                name = f'file_{i:04}.py'
                (root / name).write_bytes(content)
                zipped.writestr(name, content)
        project = import_path(str(root), [root])
        assert project['size'] == 1073741824 and len(project['files']) == 4096
        del project
        gc.collect()
        print('PASS: directory containing exactly 1 GiB of source', flush=True)

        with archive.open('rb') as stream:
            project = receive_zip(stream, archive.stat().st_size)
        assert project['size'] == 1073741824 and len(project['files']) == 4096
        del project
        gc.collect()
        print('PASS: streamed ZIP containing exactly 1 GiB of source', flush=True)

        (root / 'over.py').write_bytes(b'x')
        with zipfile.ZipFile(archive, 'a', compression=zipfile.ZIP_DEFLATED) as zipped:
            zipped.writestr('over.py', b'x')
        for label in ('directory', 'ZIP'):
            try:
                if label == 'directory':
                    import_path(str(root), [root])
                else:
                    with archive.open('rb') as stream:
                        import_zip(stream, 'over.zip')
            except ValueError as error:
                assert 'limit' in str(error), error
            else:
                raise AssertionError(f'{label} accepted 1 GiB + 1 byte')
            print(f'PASS: {label} rejects 1 GiB + 1 byte', flush=True)


if __name__ == '__main__':
    main()

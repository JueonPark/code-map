"""Bounded committed-source comparisons. Never checks out, executes, or fetches code."""
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import subprocess
import tempfile
import threading

from python_imports import extract_imports

MAX_FILES = 2000
MAX_FILE = 256 * 1024
MAX_TOTAL = 2 * 1024 * 1024
MAX_TREE = 1024 * 1024
GIT_TIMEOUT = 20


def git(repo, *args, data=None, limit=MAX_TREE, allow_failure=False):
    # Discard inherited Git overrides (including injected config/worktree paths).
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
               GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1', GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
    command = ['git', '--no-pager', '-c', 'core.fsmonitor=false', '-c', 'core.quotePath=false',
               '-c', 'core.hooksPath=' + os.devnull, '-C', str(repo), *args]
    timed_out = threading.Event()
    with tempfile.TemporaryFile() as input_file:
        if data:
            input_file.write(data)
        input_file.seek(0)
        try:
            process = subprocess.Popen(command, stdin=input_file, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except FileNotFoundError as exc:
            raise ValueError('Git is not installed or is not available on the local service PATH.') from exc
        def stop():
            timed_out.set()
            process.kill()
        timer = threading.Timer(GIT_TIMEOUT, stop)
        timer.start()
        try:
            output = process.stdout.read(limit + 1)
            if len(output) > limit:
                process.kill()
                raise ValueError('Git output exceeds the comparison limit; choose a smaller repository or source directory.')
            return_code = process.wait()
            if timed_out.is_set():
                raise ValueError('Git comparison timed out; choose a smaller repository.')
            if return_code and not allow_failure:
                raise ValueError('Git could not read the requested committed objects. Check repository permissions and local history; no fetch was attempted.')
            return output
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()


def resolve_ref(repo, ref):
    if not isinstance(ref, str) or not ref or len(ref) > 255 or ref.startswith('-') or any(ord(c) < 32 for c in ref):
        raise ValueError('Enter a valid Git revision (branch, tag, or commit).')
    raw = git(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}', allow_failure=True)
    sha = raw.decode('ascii', errors='replace').strip()
    if len(sha) not in (40, 64) or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError(f'Revision {ref!r} is not a locally available commit. Fetch it yourself, then retry.')
    return sha


def source_directory(value):
    if not isinstance(value, str) or '\\' in value or ':' in value or any(ord(c) < 32 for c in value):
        raise ValueError('Source directory must be a relative repository path using forward slashes.')
    value = value.strip()
    if value.startswith('/'):
        raise ValueError('Source directory must stay inside the repository.')
    value = value.rstrip('/')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Source directory must stay inside the repository.')
    return '' if value in ('', '.') else p.as_posix()


def snapshot(repo, revision, root):
    # Share the importer's source policy without executing the application entry point.
    from app import excluded
    entries = git(repo, 'ls-tree', '-r', '-l', '-z', revision).split(b'\0')
    files, notices, selected, total, outside, count = {}, [], [], 0, 0, 0
    for entry in filter(None, entries):
        meta, raw_path = entry.split(b'\t', 1)
        path = raw_path.decode('utf-8', errors='replace')
        if root and not path.startswith(root + '/'):
            outside += 1
            continue
        count += 1
        if count > MAX_FILES:
            raise ValueError(f'Snapshot exceeds the {MAX_FILES}-entry limit; choose a smaller source directory.')
        mode, kind, oid, size = meta.split()
        reason = excluded(path)
        if raw_path.decode('utf-8', errors='replace').encode('utf-8') != raw_path or any(ord(c) < 32 for c in path):
            reason = 'Unsupported filename encoding or control characters.'
        if mode not in (b'100644', b'100755') or kind != b'blob':
            reason = 'Symlink or submodule: contents are not followed.'
        if reason:
            notices.append({'revision': revision, 'path': path, 'reason': reason})
            continue
        size = int(size)
        total += size
        if size > MAX_FILE or total > MAX_TOTAL:
            raise ValueError(f'Snapshot exceeds source limit ({MAX_FILE} bytes/file, {MAX_TOTAL} bytes total); choose a smaller source directory.')
        selected.append((path, oid.decode(), size))
    if root and not count:
        notices.append({'revision': revision, 'path': root, 'reason': 'Source directory has no tracked files in this revision.'})
    if outside:
        notices.append({'revision': revision, 'path': '(outside source directory)', 'reason': f'{outside} tracked entries excluded by the selected source directory.'})
    if not selected:
        return files, notices
    raw = git(repo, 'cat-file', '--batch', data=('\n'.join(oid for _, oid, _ in selected) + '\n').encode(),
              limit=MAX_TOTAL + MAX_FILES * 128)
    offset = 0
    for path, oid, size in selected:
        end = raw.index(b'\n', offset)
        if raw[offset:end].split() != [oid.encode(), b'blob', str(size).encode()]:
            raise ValueError('Git object response was inconsistent; retry the comparison.')
        content = raw[end + 1:end + 1 + size]
        offset = end + size + 2
        try:
            text = content.decode('utf-8-sig')
            if '\x00' in text:
                raise UnicodeError()
        except UnicodeError:
            notices.append({'revision': revision, 'path': path, 'reason': 'binary or non-UTF-8'})
            continue
        files[path] = {'content': text, 'size': size, 'oid': oid}
    return files, notices


def stable_id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:24]


def compare_repository(path, base, head, roots, source_root=''):
    if not isinstance(path, str) or not path.strip():
        raise ValueError('Enter a local Git repository path.')
    try:
        repo = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError('Repository path does not exist or is inaccessible.') from exc
    if not repo.is_dir() or not any(repo.is_relative_to(p.resolve()) for p in roots):
        raise ValueError('Choose a Git repository inside a configured --root.')
    top = git(repo, 'rev-parse', '--show-toplevel', allow_failure=True).decode('utf-8', errors='replace').strip()
    if not top or Path(top).resolve() != repo:
        raise ValueError('Choose the root directory of a non-bare Git repository.')
    root = source_directory(source_root)
    base_sha, head_sha = resolve_ref(repo, base), resolve_ref(repo, head)
    bases = git(repo, 'merge-base', '--all', base_sha, head_sha, allow_failure=True).decode().split()
    if not bases:
        raise ValueError('No merge base/common ancestor is available. Histories may be unrelated or shallow; fetch the required history yourself.')
    if len(bases) != 1:
        raise ValueError('Multiple merge bases are ambiguous for this MVP; select revisions with a single common ancestor.')
    before_sha = bases[0]
    before, before_notices = snapshot(repo, before_sha, root)
    after, after_notices = snapshot(repo, head_sha, root)
    if not before and not after:
        raise ValueError('No supported source files in either snapshot; check the source directory and exclusions.')
    # Git's rename result is similarity-based, so expose its score rather than claiming semantic identity.
    changes = git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--name-status', '-z', '--find-renames=50%',
                  '-l2000', before_sha, head_sha, '--').split(b'\0')
    renames, i = {}, 0
    while i < len(changes) and changes[i]:
        status = changes[i].decode()
        old = changes[i + 1].decode('utf-8', errors='replace')
        i += 2
        if status.startswith('R'):
            new = changes[i].decode('utf-8', errors='replace')
            i += 1
            if old in before and new in after and old not in after and new not in before:
                renames[old] = (new, int(status[1:]))
    nodes, before_ids, after_ids = [], {}, {}
    for old in sorted(before):
        new, score = renames.get(old, (old if old in after else None, None))
        node_id = stable_id('file', old)
        state = 'removed' if new is None else 'modified' if new != old or before[old]['oid'] != after[new]['oid'] else 'unchanged'
        nodes.append({'id': node_id, 'beforePath': old, 'afterPath': new, 'status': state, 'renamed': new is not None and old != new,
                      'renameScore': score, 'module': str(PurePosixPath(old).parent), 'language': 'python' if old.endswith('.py') else 'unsupported'})
        before_ids[old] = node_id
        if new:
            after_ids[new] = node_id
    for new in sorted(set(after) - set(after_ids)):
        node_id = stable_id('file', new)
        nodes.append({'id': node_id, 'beforePath': None, 'afterPath': new, 'status': 'added', 'renamed': False,
                      'renameScore': None, 'module': str(PurePosixPath(new).parent), 'language': 'python' if new.endswith('.py') else 'unsupported'})
        after_ids[new] = node_id
    before_edges, before_gaps = extract_imports(before, before_sha, root)
    after_edges, after_gaps = extract_imports(after, head_sha, root)
    edges = {}
    for side, entries, ids in [('before', before_edges, before_ids), ('after', after_edges, after_ids)]:
        for evidence in entries:
            source, target = ids[evidence['source']], ids[evidence['target']]
            edge_id = stable_id(source, target, evidence['kind'])
            edge = edges.setdefault(edge_id, {'id': edge_id, 'source': source, 'target': target, 'kind': 'import', 'before': [], 'after': []})
            edge[side].append(evidence)
    for edge in edges.values():
        old = [e['textHash'] for e in edge['before']]
        new = [e['textHash'] for e in edge['after']]
        edge['status'] = 'added' if not old else 'removed' if not new else 'modified' if old != new else 'unchanged'
    notices = before_notices + after_notices + before_gaps + after_gaps
    for node in nodes:
        if node['renamed']:
            notices.append({'revision': head_sha, 'path': node['afterPath'], 'reason': f"Git similarity-based rename ({node['renameScore']}%): {node['beforePath']}. Review this identity match; it is not semantic proof."})
    return {'id': secrets.token_urlsafe(24), 'name': repo.name, 'sourceRoot': root, 'baseRef': base, 'headRef': head,
            'baseSha': base_sha, 'headSha': head_sha, 'mergeBaseSha': before_sha, 'nodes': nodes,
            'edges': sorted(edges.values(), key=lambda e: e['id']), 'notices': notices,
            'limits': {'files': MAX_FILES, 'fileBytes': MAX_FILE, 'totalBytes': MAX_TOTAL},
            '_before': before, '_after': after}


def public_comparison(comparison):
    return {k: v for k, v in comparison.items() if not k.startswith('_')}


def comparison_detail(comparison, node_id):
    node = next((n for n in comparison['nodes'] if n['id'] == node_id), None)
    if node is None:
        raise ValueError('File is not part of this comparison.')
    old, new = node['beforePath'], node['afterPath']
    before, after = comparison['_before'].get(old), comparison['_after'].get(new)
    before_text, after_text = before['content'] if before else '', after['content'] if after else ''
    diff = '\n'.join(difflib.unified_diff(before_text.splitlines(), after_text.splitlines(),
                    fromfile='a/' + old if old else '/dev/null', tofile='b/' + new if new else '/dev/null', lineterm=''))
    if node['renamed']:
        diff = f'rename from {old}\nrename to {new}\n' + diff
    if not diff and node['status'] == 'modified':
        diff = 'File bytes changed without a visible line change (for example encoding or final newline).'
    def source(file, path, revision):
        return {'path': path, 'revision': revision, 'content': file['content']} if file else None
    return {'id': comparison['id'], 'nodeId': node_id, 'before': source(before, old, comparison['mergeBaseSha']),
            'after': source(after, new, comparison['headSha']), 'diff': diff or 'No line changes.'}

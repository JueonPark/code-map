"""Conservative, non-executing Python import analysis for a single source root."""
import ast
import hashlib
from pathlib import PurePosixPath

MAX_REFERENCES = 10000
MAX_NOTICES = 10000


def extract_imports(files, revision, source_root=''):
    modules, parsed, edges, notices = {}, {}, [], []
    prefix = source_root.rstrip('/') + '/' if source_root else ''

    def notice(path, reason, line=None):
        if len(notices) >= MAX_NOTICES:
            raise ValueError('Python analysis notice limit exceeded; select a smaller source directory.')
        notices.append({'revision': revision, 'path': path, 'reason': reason, 'line': line})

    for path, file in sorted(files.items()):
        if not path.endswith('.py'):
            notice(path, 'Dependency analysis unsupported: Python static imports only; file changes are still shown.')
            continue
        rel = path[len(prefix):]
        parts = list(PurePosixPath(rel).with_suffix('').parts)
        if parts[-1] == '__init__':
            parts.pop()
        if not parts or not all(part.isidentifier() for part in parts):
            notice(path, 'No importable module name under the selected source root.')
            continue
        module = '.'.join(parts)
        modules.setdefault(module, []).append(path)
        try:
            parsed[path] = (module, ast.parse(file['content'], filename=path))
        except (SyntaxError, ValueError, RecursionError) as exc:
            notice(path, 'Python syntax could not be analyzed: ' + type(exc).__name__, getattr(exc, 'lineno', None))

    def resolve(name, path, line, quiet=False):
        parts = name.split('.')
        for end in range(1, len(parts)):
            parent = '.'.join(parts[:end])
            candidates = modules.get(parent, [])
            if len(candidates) > 1:
                notice(path, f'Ambiguous package {parent}: no target selected for {name}.', line)
                return None
            if candidates and not candidates[0].endswith('/__init__.py'):
                notice(path, f'Unresolved import {name}: {parent} is a module, not a package.', line)
                return None
        candidates = modules.get(name, [])
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            notice(path, f'Ambiguous module {name}: multiple files match; no target selected.', line)
        elif not quiet:
            notice(path, f'Unresolved or external import: {name}.', line)
        return None

    def declared(path, name, before_line=None):
        if path not in parsed:
            return False
        for item in parsed[path][1].body:
            # Inside a package initializer, its current/later import cannot yet
            # establish the attribute used to resolve that very import.
            if before_line is not None and item.lineno >= before_line:
                continue
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and item.name == name:
                return True
            targets = item.targets if isinstance(item, ast.Assign) else [item.target] if isinstance(item, ast.AnnAssign) else []
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return True
            if isinstance(item, (ast.Import, ast.ImportFrom)) and any((a.asname or a.name.split('.')[0]) == name for a in item.names):
                return True
        return False

    for path, (module, tree) in sorted(parsed.items()):
        lines = files[path]['content'].splitlines()
        for node in sorted(ast.walk(tree), key=lambda n: getattr(n, 'lineno', 0)):
            targets = set()
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = resolve(alias.name, path, node.lineno)
                    if target:
                        targets.add(target)
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ''
                if node.level:
                    package = module.split('.') if path.endswith('/__init__.py') else module.split('.')[:-1]
                    if node.level > len(package):
                        notice(path, 'Relative import escapes the selected Python source root.', node.lineno)
                        continue
                    name = '.'.join(package[:len(package) - node.level + 1] + ([name] if name else []))
                for alias in node.names:
                    child = name + '.' + alias.name if name else alias.name
                    parents = modules.get(name, [])
                    parent = parents[0] if len(parents) == 1 else None
                    if parent and alias.name != '*' and declared(parent, alias.name, node.lineno if parent == path else None):
                        target = parent
                        if child in modules:
                            notice(path, f'Imported name {child} is declared by {parent}; the parent dependency is recorded instead of assuming the child file is imported.', node.lineno)
                    elif alias.name != '*' and child in modules:
                        target = resolve(child, path, node.lineno)
                    else:
                        target = resolve(name, path, node.lineno)
                        if target and (alias.name == '*' or not declared(target, alias.name)):
                            notice(path, f'Imported name {child} is unresolved as an attribute/re-export; only its module dependency is recorded.', node.lineno)
                    if target:
                        targets.add(target)
            elif isinstance(node, ast.Call) and (
                isinstance(node.func, ast.Name) and node.func.id == '__import__'
                or isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module'
            ):
                notice(path, 'Possible dynamic import: target is not resolved by static analysis.', node.lineno)
            for target in sorted(targets):
                if len(edges) >= MAX_REFERENCES:
                    raise ValueError('Python dependency reference limit exceeded; select a smaller source directory.')
                text = '\n'.join(lines[node.lineno - 1:node.end_lineno])
                edges.append({'source': path, 'target': target, 'kind': 'import', 'revision': revision,
                              'path': path, 'startLine': node.lineno, 'endLine': node.end_lineno,
                              'text': text[:512], 'textHash': hashlib.sha256(text.encode()).hexdigest()})
    return edges, notices

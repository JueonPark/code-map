# Review structural changes between Git revisions

Open **Review structural changes** from the project import page, or visit `/compare`. This workflow runs locally without an API key. It reads committed Git objects; it does not check out branches, modify the worktree/index, fetch commits, execute project code, or call an AI provider.

## Setup and comparison

1. Install Git on the local service's PATH and use Python 3.10 or newer.
2. Start the service: `python server/app.py --root /path/to/projects`.
3. In `frontend`, run `npm ci` and `npm run dev`. Open `http://127.0.0.1:5173/compare`.
4. Enter a non-bare repository's root directory, a base ref, and a head ref. Refs can be branches, tags, or commit expressions such as `HEAD~1`.
5. Optionally enter a **Python source directory**, relative to the repository, such as `src` or `python`. This both limits included files and defines the Python import root. Leave it empty for imports rooted at the repository root. Use forward slashes.
6. Select **Compare revisions**. The displayed before snapshot is the single merge base of the resolved base/head commits; the after snapshot is the resolved head commit. The requested base's SHA is shown separately because it may have advanced since the branches diverged.

Windows paths work with a Windows service. For a WSL repository, run the service inside WSL and enter its Linux path, with a matching `--root`. Use the existing [import setup](project-import.md) for the frontend and local service configuration. Native Windows access to WSL UNC Git repositories has not been independently validated; running Git and the service inside WSL was validated.

Refs must already be available locally. Missing/shallow history and multiple merge bases produce explicit errors. Git replacement objects are disabled for the comparison so the recorded SHA always identifies the original committed contents; repository replacement settings are not changed. Uncommitted edits and untracked files are excluded. Re-running a comparison resolves current refs again; an existing result and its evidence stay pinned to the recorded SHAs even if branches move. Eight comparison snapshots are retained in memory; the oldest is evicted when a ninth is added, and restarting the service clears them.

## Reading the map

- Nodes are included source/text files grouped by directory, using the original directory for matched files in both views. Added files use their new directory. This is a deterministic grouping, not an inferred business architecture.
- Green means added, red means removed, amber means modified, and gray means unchanged. Content-only changes are still modified even when no import edge changes.
- Arrows point from importer to imported file. The default view includes changed files/edges and their immediate resolved neighbors. Turn off **Changed neighborhood** to inspect the whole analyzed scope, or filter by file/directory name.
- **Changes map**, **Before map**, and **After map** use the same union layout. Absent elements fade rather than moving the remaining nodes. Deleted files remain selectable.
- Select a file for its unified diff and both source versions. Select an arrow for the exact import statement ranges and pinned revision; choose a source tab to highlight those lines. Related files link to their own evidence without leaving the comparison.
- Git-detected renames keep one identity, display both paths, and expose the similarity score. Similarity is a heuristic, not proof of semantic identity. Renames Git cannot match may appear as a deletion and an addition.
- Direct importers are **review candidates**. An edge does not prove that an import executes or that downstream runtime behavior changed.

## Analysis coverage and limits

The first extractor uses Python's standard-library AST parser. It records syntactic `import` and `from ... import ...` dependencies to uniquely resolved files under one selected source root. It supports absolute and relative imports, `.py` modules, package `__init__.py` files, and unambiguous namespace directories. A `from` import first checks declared attributes/re-exports on its parent module, then an existing child module; otherwise it records the parent with an unresolved-name notice. An attribute that shadows a child file produces a notice rather than an invented child dependency. Inside a package initializer, the current and later statements do not count as already declared attributes. Imported symbols are not followed to their eventual definitions.

Conditional, function-local, and type-checking-only imports are included as source observations. No interpreter or build is run. The analysis does not evaluate `sys.path`, installation metadata, multiple source roots, package initialization effects, `__all__`, runtime monkeypatching, or native-extension loading. Recognizable dynamic imports, ambiguous module names, external/unresolved imports, and parse errors appear under **Analysis coverage**. No resolved edge is not proof of no dependency. Files in other supported text formats remain visible, with an unsupported-dependency-analysis notice; JavaScript/TypeScript/C++ call or import resolution is not implemented.

The path/ZIP import exclusions also apply here: secret-like filenames, dependency/build directories, binary/non-UTF-8 content, and unsupported file types are reported and excluded. Tracked symlinks and submodules are reported and never followed. Source evidence is served only for files in the cached comparison; arbitrary paths cannot be requested.

Per snapshot: at most 2,000 scoped entries, 256 KiB per included file, and 2 MiB total included bytes. Git tree/diff metadata output is capped at 1 MiB, each Git process has a 20-second timeout, and Python extraction is capped at 10,000 import references and 10,000 analysis notices per snapshot. Exceeding a limit fails explicitly; choose a smaller source directory or repository. The metadata cap applies to the repository even with a source-directory filter. Evidence previews are capped at 512 characters while retaining full source ranges and a statement hash for change classification. Full included source is available in the detail view.

## Verification

Backend tests create real temporary Git histories and a loopback HTTP service:

```bash
python -m unittest discover -s server -v
```

For browser checks, run Vite on `127.0.0.1:5174` (`npm run dev -- --port 5174`). Install Playwright in your test environment, or set `CODEMAP_PLAYWRIGHT` to its module path. Set `CODEMAP_CHROME` to a Chromium/Chrome executable if needed.

```bash
node tests/compare-browser.cjs
python tests/compare-live.py
node tests/import-browser.cjs
```

`compare-browser.cjs` uses controlled API replies to test graph position stability, source highlights, deleted evidence, errors, and delayed-response isolation. `compare-live.py` requires port 8765 to be free and drives a real disposable Git repository through the Python HTTP service, Vite proxy, and Chrome, including rename evidence, committed-only content, filtering, and a narrow viewport. It cleans up its fixture afterward. The existing import browser regression still exercises path/ZIP analysis with mocked provider responses.

Build with `npm run build`. Targeted lint: `npx eslint src/features/structural-compare src/features/project-import/index.tsx src/routes/index.tsx` from `frontend`. The repository-wide TypeScript check still reports pre-existing prompt-name errors in unused `gpt/usage` examples; they are outside this change.

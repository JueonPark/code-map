# Import a local project

Requires Python 3.10+ and Node.js 20+. Run the service and Vite on the same OS (both Windows or both WSL) so loopback networking is predictable.

1. Install the frontend: `cd frontend` then `npm ci`.
2. From the repository root, start `python server/app.py --root /home/user/projects` (Linux/WSL), or `py server/app.py --root "C:\projects"` (Windows). Repeat `--root` for additional permitted roots. The service listens only on `127.0.0.1:8765`.
3. In another terminal, run `cd frontend` then `npm run dev`. Open **http://127.0.0.1:5173** (use this exact origin, not localhost).
4. Enter an accessible directory path or choose a ZIP. Review the included and excluded files. Importing does not make any external AI requests.
5. To enable analysis, set `OPENAI_API_KEY` and `OPENAI_MODEL` in the **service terminal** and restart it before importing. Select a Responses-compatible model available to your API project. Never put the API key in a `VITE_` variable. Check the consent box and choose Business Components or Function Call. Subsequent graphs, explanations and chat requests include the selected source snapshot.

On PowerShell, set environment variables using `$env:OPENAI_API_KEY = '...'` and `$env:OPENAI_MODEL = '...'`. On Linux/WSL use `export OPENAI_API_KEY=...` and `export OPENAI_MODEL=...`. No API key is needed for import/preview. Existing Assistant IDs and sample-project environment variables are no longer used by the application.

## Windows and WSL paths

Paths are interpreted by the Python service, not the browser. A service inside Ubuntu can read `/home/user/project`; configure `--root /home/user` accordingly. A Windows service can read `C:\projects\app` or an accessible `\\wsl.localhost\Ubuntu\home\user\project` UNC path; explicitly allow its parent using `--root`. Do not enter a Windows UNC path into a Linux service. ZIP upload works independently of the browser's filesystem path conventions.

## Preview and limits

Both methods produce the same relative-path/source model. A ZIP's single wrapping directory is removed. ZIP uploads are streamed in chunks of at most 1 MiB into a temporary archive file, which is deleted after import succeeds or fails; archive entries are never extracted to filesystem paths. Allow up to 1 GiB of free space in the service's temporary directory for an upload. Symlinks and ZIP traversal paths are rejected. Source files remain unchanged.

Before reading, the service validates the actual opened file handle and its regular-file type, so replacing a source path or ancestor with a symlink during import cannot read outside the project. Linux requires `/proc/self/fd`; Windows uses `GetFinalPathNameByHandleW`.

Model-generated SVG links and resource/event attributes are removed before insertion. Provider failures and malformed graph/explanation output show a retry action in place, including local-node analyses.

- Up to 10,000 entries, 256 KiB per included source file, **1 GiB (1,024 MiB / 1,073,741,824 bytes)** of included source per project. ZIP upload and total uncompressed size are each limited to 1 GiB; the uncompressed limit includes excluded entries. The higher entry count allows projects to reach 1 GiB while retaining the per-file cap. JSON API requests retain their separate 10 MiB limit.
- UTF-8 source/documentation/configuration formats listed in `server/app.py`; unsupported, binary and non-UTF-8 files are excluded.
- `.git`, dependency/virtualenv/cache directories, common build directories, `.aws`, `.ssh`, `.env*`, `id_*`, credential/secret filenames and key/certificate extensions are excluded by default. These filename rules cannot identify secrets embedded in ordinary source; review the preview and prepare a clean directory/archive when needed.
- At most eight immutable snapshots are retained in service memory; restart the service to clear them. Decoded source, snapshot metadata, and analysis payloads still consume memory and can require several times the source byte count. Streaming the ZIP avoids an additional full archive buffer; it does not make snapshots disk-backed. This also invalidates browser project IDs; reimport after a restart. Snapshots are not watched for changes.

Analysis sends the complete approved source snapshot, task prompt and (for chat) up to 18 previous messages to OpenAI's Responses API with `store: false`. There is no vector-store upload or remote Assistant mutation. The 1 GiB limit is an import/preview allowance, not a model context allowance: this patch does not add chunking or indexing for monorepo analysis. Select a smaller source directory for analysis. Provider access/quota/context errors are displayed; a successful import does not guarantee the configured model can analyze a project of that size. API calls may incur charges. The provider key and errors containing provider response bodies are never sent to the browser.

These limits apply to project imports only. Git structural comparison retains its separate limits documented in `docs/structural-comparison.md`.

Switching projects performs a full navigation after approval, clearing in-memory Zustand graph/selection caches and chat history. The current project name and switch link remain in the analysis header. Use the import home page to review again or select another project.

The Vite proxy forwards `/api` to the loopback service. The service checks the exact Host, configured Origin and custom request header, and does not enable CORS. For an alternate Vite port, pass `--origin http://127.0.0.1:PORT` to the service. This is a local single-user development app, not a multi-user hosted server. `vite preview` alone does not provide the API proxy.

## Tests

`python -m unittest discover -s server -v` checks path/ZIP equivalence, exclusions, malformed/escaping/symlink archives, limits, request origin checks, approval gating, provider payloads and errors.

Optional full-size check: `python tests/import-large.py` generates 4,096 temporary source files, imports exactly 1 GiB through directory and streamed ZIP paths, and checks that adding one byte is rejected. Allow roughly 2 GiB of free RAM and 1.1 GiB of temporary disk space. Fixtures are removed automatically. The regular suite uses smaller boundary fixtures and a real HTTP ZIP upload above the old 10 MiB cap.

`cd frontend && npm run build` builds the app. The original prototype has unrelated type errors in unused `gpt/usage` examples; Vite build does not type-check those examples.

Browser integration: with Vite on port 5174, run `node tests/import-browser.cjs`. Set `CODEMAP_PLAYWRIGHT` to a resolvable Playwright module and optionally `CODEMAP_CHROME` to Chrome's executable. API responses are mocked in this test; it verifies preview/consent, both analysis routes, project isolation and visible error handling without paid calls.

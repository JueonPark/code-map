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

Both methods produce the same relative-path/source model. A ZIP's single wrapping directory is removed. ZIP contents are read in memory and never extracted to disk. Symlinks and ZIP traversal paths are rejected. Source files remain unchanged.

- Up to 2,000 entries, 256 KiB per included source file, 2 MiB of included source per project; ZIP total uncompressed size is also limited to 2 MiB (including excluded entries). ZIP upload limit: 10 MiB.
- UTF-8 source/documentation/configuration formats listed in `server/app.py`; unsupported, binary and non-UTF-8 files are excluded.
- `.git`, dependency/virtualenv/cache directories, common build directories, `.aws`, `.ssh`, `.env*`, `id_*`, credential/secret filenames and key/certificate extensions are excluded by default. These filename rules cannot identify secrets embedded in ordinary source; review the preview and prepare a clean directory/archive when needed.
- At most eight immutable snapshots are retained in service memory; restart the service to clear them. This also invalidates browser project IDs; reimport after a restart. Snapshots are not watched for changes.

Analysis sends the complete approved source snapshot, task prompt and (for chat) up to 18 previous messages to OpenAI's Responses API with `store: false`. There is no vector-store upload or remote Assistant mutation. Provider access/quota/context errors are displayed; a successful import does not guarantee the configured model can analyze a project of that size. API calls may incur charges. The provider key and errors containing provider response bodies are never sent to the browser.

Switching projects performs a full navigation after approval, clearing in-memory Zustand graph/selection caches and chat history. The current project name and switch link remain in the analysis header. Use the import home page to review again or select another project.

The Vite proxy forwards `/api` to the loopback service. The service checks the exact Host, configured Origin and custom request header, and does not enable CORS. For an alternate Vite port, pass `--origin http://127.0.0.1:PORT` to the service. This is a local single-user development app, not a multi-user hosted server. `vite preview` alone does not provide the API proxy.

## Tests

`python -m unittest discover -s server -v` checks path/ZIP equivalence, exclusions, malformed/escaping/symlink archives, limits, request origin checks, approval gating, provider payloads and errors.

`cd frontend && npm run build` builds the app. The original prototype has unrelated type errors in unused `gpt/usage` examples; Vite build does not type-check those examples.

Browser integration: with Vite on port 5174, run `node tests/import-browser.cjs`. Set `CODEMAP_PLAYWRIGHT` to a resolvable Playwright module and optionally `CODEMAP_CHROME` to Chrome's executable. API responses are mocked in this test; it verifies preview/consent, both analysis routes, project isolation and visible error handling without paid calls.

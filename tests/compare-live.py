"""Start a disposable real Git fixture/service and exercise it through Vite + Chrome.

Start Vite on 127.0.0.1:5174 first; port 8765 must be free. Set CODEMAP_PLAYWRIGHT
and CODEMAP_CHROME if Playwright/Chromium are not on the normal module/browser paths.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import app
from test_compare import CompareTests


fixture = CompareTests()
fixture.setUp()
server = None
try:
    before, head = fixture.history()
    fixture.write('README.md', 'uncommitted work must survive\n')
    original = fixture.git('status', '--porcelain=v1')
    server = app.ThreadingHTTPServer(('127.0.0.1', 8765), app.Handler)
    server.origin, server.roots = 'http://127.0.0.1:5174', [fixture.repo]
    server.projects, server.comparisons, server.lock = {}, {}, threading.Lock()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, CODEMAP_LIVE_FIXTURE=json.dumps({'path': str(fixture.repo), 'mergeBaseSha': before, 'headSha': head}))
    subprocess.run(['node', str(ROOT / 'tests' / 'compare-live-browser.cjs')], env=env, cwd=ROOT, check=True)
    assert fixture.git('status', '--porcelain=v1') == original
    print('PASS: real Git -> Python HTTP -> Vite proxy -> Chrome; dirty worktree preserved.')
finally:
    if server:
        server.shutdown()
        server.server_close()
    fixture.doCleanups()

const assert = require('node:assert/strict');
const { chromium } = require(process.env.CODEMAP_PLAYWRIGHT || 'playwright');
const sha = letter => letter.repeat(40);
const node = (id, beforePath, afterPath, status) => ({id, beforePath, afterPath, status, renamed: !!beforePath && !!afterPath && beforePath !== afterPath, renameScore: null, module: 'pkg', language: 'python'});
const evidence = (target, revision, text) => ({source: 'pkg/main.py', target, kind: 'import', revision, path: 'pkg/main.py', startLine: 1, endLine: 1, text});
const first = {id: 'comparison-one', name: 'fixture', sourceRoot: '', baseRef: 'main', headRef: 'feature', baseSha: sha('a'), headSha: sha('b'), mergeBaseSha: sha('c'),
  nodes: [node('main', 'pkg/main.py', 'pkg/main.py', 'modified'), node('old', 'pkg/old.py', null, 'removed'), node('new', null, 'pkg/new.py', 'added'), node('util', 'pkg/util.py', 'pkg/util.py', 'modified'), node('stable', 'pkg/stable.py', 'pkg/stable.py', 'unchanged')],
  edges: [
    {id: 'removed-edge', source: 'main', target: 'old', kind: 'import', status: 'removed', before: [evidence('pkg/old.py', sha('c'), 'from . import old')], after: []},
    {id: 'added-edge', source: 'main', target: 'new', kind: 'import', status: 'added', before: [], after: [evidence('pkg/new.py', sha('b'), 'from . import new')]},
  ], notices: [{revision: sha('b'), path: 'native.cpp', reason: 'Dependency analysis unsupported: Python static imports only.'}], limits: {files: 2000, fileBytes: 262144, totalBytes: 2097152}};
const second = {...first, id: 'comparison-two', headRef: 'feature-two', nodes: [node('second', null, 'pkg/second.py', 'added')], edges: [], notices: []};

(async () => {
  const browser = await chromium.launch({headless: true, ...(process.env.CODEMAP_CHROME ? {executablePath: process.env.CODEMAP_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1050}});
    const errors = [], calls = [];
    let holdDetail = false, releaseDetail, detailStarted;
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/api/**', async route => {
      const endpoint = route.request().url().split('/api/')[1];
      const body = route.request().postDataJSON();
      calls.push(endpoint);
      if (endpoint === 'status') return route.fulfill({json: {ready: false, roots: ['/projects'], model: ''}});
      if (endpoint === 'compare') {
        if (body.head === 'missing') return route.fulfill({status: 400, json: {error: 'Revision is not locally available.'}});
        assert.equal(body.path, '/projects/fixture');
        return route.fulfill({json: body.head === 'feature-two' ? second : first});
      }
      assert.equal(endpoint, 'compare/detail', 'Comparison must never call AI endpoints');
      if (holdDetail) { holdDetail = false; detailStarted(); await new Promise(resolve => {releaseDetail = resolve;}); }
      const data = body.id === second.id ? second : first;
      const file = data.nodes.find(n => n.id === body.nodeId);
      const source = (path, revision, content) => path ? {path, revision, content} : null;
      await route.fulfill({json: {id: body.id, nodeId: file.id,
        before: source(file.beforePath, sha('c'), file.id === 'main' ? 'from . import old\n' : 'value = 1\n'),
        after: source(file.afterPath, sha('b'), file.id === 'main' ? 'from . import new\n' : 'value = 2\n'),
        diff: file.id === 'main' ? '-from . import old\n+from . import new' : file.id === 'old' ? '-value = 1' : '-value = 1\n+value = 2'}});
    });
    await page.goto(process.env.CODEMAP_TEST_URL || 'http://127.0.0.1:5174');
    await page.getByRole('link', {name: 'Review structural changes'}).click();
    await page.getByLabel('Git repository path').fill('/projects/fixture');
    await page.getByLabel('Base ref', {exact: true}).fill('main');
    await page.getByLabel('Head ref', {exact: true}).fill('feature');
    await page.getByRole('button', {name: 'Compare revisions'}).click();
    await page.getByRole('heading', {name: 'fixture — structural changes'}).waitFor();
    const graphNode = page.locator('[data-node-id="main"]');
    const position = await graphNode.getAttribute('transform');
    await page.getByRole('button', {name: 'Before map', exact: true}).click();
    assert.equal(await graphNode.getAttribute('transform'), position);
    await page.getByRole('button', {name: 'After map', exact: true}).click();
    assert.equal(await graphNode.getAttribute('transform'), position);
    await page.getByRole('button', {name: 'Changes map', exact: true}).click();
    await page.getByRole('button', {name: 'Inspect pkg/util.py', exact: true}).click();
    await page.getByTestId('source-detail').getByText('+value = 2', {exact: false}).waitFor();
    await page.getByRole('button', {name: 'Inspect import pkg/main.py → pkg/new.py', exact: true}).click();
    await page.getByRole('button', {name: 'After source', exact: true}).click();
    await page.locator('[data-source-line="1"].evidence-line').waitFor();
    assert.match(await page.getByTestId('source-detail').innerText(), /from \. import new/);
    await page.getByRole('button', {name: 'Inspect pkg/old.py', exact: true}).click();
    await page.getByRole('button', {name: 'Before source', exact: true}).click();
    await page.getByTestId('source-detail').getByText('value = 1', {exact: true}).waitFor();
    await page.getByRole('button', {name: 'After source', exact: true}).click();
    await page.getByText('This file does not exist in this revision.').waitFor();
    await page.getByRole('button', {name: 'Diff', exact: true}).click();
    await page.getByTestId('source-detail').getByText('-value = 1', {exact: true}).waitFor();
    await page.getByText('Analysis coverage', {exact: false}).click();
    await page.getByText(/Dependency analysis unsupported/).waitFor();
    await page.screenshot({path: 'test-results/structural-comparison.png', fullPage: true});
    const started = new Promise(resolve => { detailStarted = resolve; });
    holdDetail = true;
    await page.getByRole('button', {name: 'Inspect pkg/main.py', exact: true}).click();
    await started;
    await page.getByLabel('Head ref', {exact: true}).fill('feature-two');
    await page.getByRole('button', {name: 'Compare revisions'}).click();
    await page.getByRole('button', {name: 'Inspect pkg/second.py', exact: true}).waitFor();
    releaseDetail();
    await page.getByRole('button', {name: 'Inspect pkg/second.py', exact: true}).click();
    await page.getByTestId('source-detail').getByText('+value = 2', {exact: false}).waitFor();
    assert.ok(!(await page.getByTestId('source-detail').innerText()).includes('pkg/main.py'));
    assert.equal(await page.locator('[data-node-id="main"]').count(), 0);
    await page.getByLabel('Head ref', {exact: true}).fill('missing');
    await page.getByRole('button', {name: 'Compare revisions'}).click();
    await page.getByRole('alert').getByText('Revision is not locally available.').waitFor();
    assert.equal(await page.getByTestId('source-detail').count(), 0);
    assert.deepEqual(errors, []);
    console.log('PASS: comparison entry, stable layout, source/diff evidence, deletion, coverage, stale response isolation, errors; no AI calls.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exit(1);});

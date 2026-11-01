const assert = require('node:assert/strict');
const { chromium } = require(process.env.CODEMAP_PLAYWRIGHT || 'playwright');
(async () => {
  const browser = await chromium.launch({headless: true, ...(process.env.CODEMAP_CHROME ? {executablePath: process.env.CODEMAP_CHROME} : {})});
  try {
    const page = await browser.newPage();
    const errors = [], calls = [];
    let id = 'project-A', approved = false, fail = false, malformed = false;
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/api/**', async route => {
      const endpoint = route.request().url().split('/api/')[1];
      let result;
      if (endpoint === 'status') result = {ready: true, model: 'test-model', roots: ['/projects']};
      else if (endpoint.startsWith('import/')) { approved = false; result = {id, name: id, files: [{path: 'main.py', size: 9}], excluded: [{path: '.env', reason: 'potential secret'}], size: 9}; }
      else if (endpoint === 'approve') { approved = true; result = {ok: true}; }
      else {
        const body = route.request().postDataJSON();
        assert.equal(approved, true);
        assert.equal(body.id, id);
        calls.push(body);
        if (fail) { await route.fulfill({status: 400, json: {error: 'Provider unavailable'}}); return; }
        if (malformed) { await route.fulfill({json: {text: 'No graph was generated.'}}); return; }
        result = {text: '```json\n{"projectOverview":{"summary":"'+id+'"},"keyModules":{},"projectArchitectureGuide":[]}\n```\n```dot\ndigraph G { main [label="'+id+'", URL="javascript:window.__codemapInjected=true"]; }\n```'};
      }
      await route.fulfill({json: result});
    });
    await page.goto('http://127.0.0.1:5174');
    await page.getByLabel('Local directory path').fill('/projects/a');
    await page.getByRole('button', {name: 'Preview directory'}).click();
    await page.getByText('project-A — import complete').waitFor();
    assert.equal(calls.length, 0);
    assert.equal(await page.getByRole('button', {name: 'Analyze Business Components'}).isDisabled(), true);
    await page.getByRole('checkbox').check();
    await page.getByRole('button', {name: 'Analyze Business Components'}).click();
    await page.getByRole('button', {name: 'Regenerate this graph'}).waitFor();
    await page.locator('#graph-container svg').waitFor();
    assert.equal(await page.locator('#graph-container svg').evaluate(svg => [...svg.querySelectorAll('*')].some(el => [...el.attributes].some(a => /href$/i.test(a.name) && /^javascript:/i.test(a.value)))), false, 'model-generated SVG must not contain executable links');
    assert.ok(calls.some(c => c.prompt.includes('system structure')));
    assert.equal(calls.length, 1, 'graph and overview should share one in-flight request');
    await page.evaluate(async () => {
      const { default: chat } = await import('/gpt/chatService.ts');
      await chat.sendMessage('Explain main.py', () => {});
      await chat.sendMessage('What calls it?', () => {});
    });
    assert.equal(calls.at(-1).history.length, 2);
    await page.getByRole('button', {name: /Import \/ switch project/}).click();
    id = 'project-B';
    await page.getByLabel('ZIP archive', {exact: true}).setInputFiles({name: 'demo.zip', mimeType: 'application/zip', buffer: Buffer.from('mock transport fixture')});
    await page.getByText('project-B — import complete').waitFor();
    await page.getByRole('checkbox').check();
    const before = calls.length;
    await page.getByRole('button', {name: 'Analyze Function Call'}).click();
    await page.getByRole('button', {name: 'Regenerate this graph'}).waitFor();
    await page.locator('#graph-container svg').waitFor();
    assert.ok(calls.length > before);
    assert.ok(calls.slice(before).every(c => c.id === 'project-B'));
    assert.ok(!(await page.locator('#graph-container').innerText()).includes('project-A'));
    await page.evaluate(async () => {
      const { default: chat } = await import('/gpt/chatService.ts');
      await chat.sendMessage('Explain this project', () => {});
    });
    assert.equal(calls.at(-1).history.length, 0, 'switching projects resets conversation');
    fail = true;
    await page.getByRole('button', {name: 'Regenerate this graph'}).click();
    await page.getByText('Error: Provider unavailable').waitFor();
    fail = false;
    malformed = true;
    await page.getByRole('button', {name: 'Retry analysis'}).click();
    await page.getByText('Error: Analysis did not contain a DOT graph. Please retry.').waitFor();
    malformed = false;
    await page.getByRole('button', {name: 'Retry analysis'}).click();
    await page.getByRole('button', {name: 'Regenerate this graph'}).waitFor();
    assert.deepEqual(errors, []);
    console.log('PASS: path/ZIP preview, consent gate, both graph modes, project switch, provider errors');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});

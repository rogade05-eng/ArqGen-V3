// Built-shell Chromium test: disposable worker, replay, tamper rejection and offline import.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { chromium } from 'playwright-core';

const browserPath = process.env.ARQGEN_CHROMIUM_PATH;
const baseUrl = process.env.ARQGEN_E2E_URL || 'http://127.0.0.1:4173/'; // Node runner only.
const launch = () => chromium.launch({ executablePath: browserPath, headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--single-process'] });

async function ready(page) {
  assert.equal((await page.goto(baseUrl, { waitUntil: 'load' }))?.status(), 200);
  await page.waitForFunction(() => !document.querySelector('#explore-start')?.disabled);
  assert.equal(await page.locator('#result-status').textContent(), 'VIABLES');
}

async function start(page, count = '4') {
  await page.locator('#explore-count').selectOption(count);
  await page.locator('#explore-start').click();
  await page.waitForFunction(() => document.querySelector('#explore-status')?.textContent?.includes('Lote calculado'));
  assert.equal(await page.locator('#explore-status').getAttribute('data-state'), 'ok');
  assert.equal(await page.locator('.explore-card').count(), 3);
  assert.equal(await page.locator('.explore-plan').first().evaluate((img) => img.complete && img.naturalWidth > 0), true);
  assert.match(await page.locator('#explore-summary').textContent(), /192 variantes ensayadas.*Pareto 1 del lote/);
}

test('lote cancelable: replay íntegro, rechazo atómico de adulteración y apertura offline', { timeout: 90_000 }, async () => {
  assert.ok(browserPath, 'Configura ARQGEN_CHROMIUM_PATH con un navegador local.');
  const browser = await launch();
  try {
    const context = await browser.newContext({ acceptDownloads: true, serviceWorkers: 'allow' });
    const page = await context.newPage();
    const errors = [];
    const dialogs = [];
    let acceptOverwrite = false;
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('dialog', async (dialog) => {
      dialogs.push(dialog.type());
      if (acceptOverwrite) await dialog.accept(); else await dialog.dismiss();
    });
    await ready(page);
    await start(page);
    assert.equal(await page.locator('#portfolio-count').textContent(), '0 / 8 PROYECTOS');
    assert.match(await page.locator('#history-count').textContent(), /^1 \/ 1/);

    const download = page.waitForEvent('download');
    await page.locator('#explore-export').click();
    const backup = JSON.parse(await readFile(await (await download).path(), 'utf8'));
    assert.equal(backup.format, 'arqgen-illustrative-seed-exploration-v1');
    assert.equal(backup.seed_count, 4);
    assert.equal(backup.exploration.seed_runs.length, 4);
    assert.equal(backup.exploration.generated, 192);
    assert.equal(backup.exploration.alternatives.length, 3);
    const current = await page.locator('.explore-plan').first().getAttribute('src');
    const altered = structuredClone(backup);
    altered.exploration.alternatives[1].candidate.svg += '<script>alert(1)</script>';
    await page.locator('#explore-file').setInputFiles({
      name: 'lote-falso.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(altered)),
    });
    await page.waitForFunction(() => document.querySelector('#explore-status')?.dataset.state === 'error');
    assert.match(await page.locator('#explore-status').textContent(), /no coincide íntegramente/);
    assert.equal(await page.locator('.explore-card').count(), 3, 'Failed replay never replaces a valid earlier batch.');
    assert.equal(await page.locator('.explore-plan').first().getAttribute('src'), current);
    assert.equal(await page.locator('input[name="width"]').inputValue(), '18');
    assert.deepEqual(dialogs, [], 'A forged batch is rejected before any overwrite prompt.');

    await page.locator('input[name="width"]').fill('19');
    assert.equal(await page.locator('.explore-card').count(), 0);
    assert.equal(await page.locator('#explore-export').isEnabled(), false);
    assert.equal(await page.locator('#explore-start').isEnabled(), false);
    assert.equal(await page.locator('#result-status').textContent(), 'SIN REGENERAR');
    await page.locator('#explore-file').setInputFiles({
      name: 'lote-verificado.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(backup)),
    });
    await page.waitForFunction(() => document.querySelector('#explore-status')?.textContent?.includes('Apertura cancelada'));
    assert.equal(await page.locator('input[name="width"]').inputValue(), '19');
    assert.equal(await page.locator('.explore-card').count(), 0);
    assert.deepEqual(dialogs, ['confirm'], 'Replay completes before asking to replace unsaved edits.');
    acceptOverwrite = true;
    await page.locator('#explore-file').setInputFiles({
      name: 'lote-verificado.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(backup)),
    });
    await page.waitForFunction(() => document.querySelector('#explore-status')?.textContent?.includes('reproducido y comparado íntegramente'));
    assert.equal(await page.locator('input[name="width"]').inputValue(), '18');
    assert.equal(await page.locator('.explore-card').count(), 3);
    assert.deepEqual(dialogs, ['confirm', 'confirm'], 'Replacing unsaved edits requires explicit acceptance.');
    assert.match(await page.locator('#history-count').textContent(), /^1 \/ 1/);
    assert.equal(await page.locator('#portfolio-count').textContent(), '0 / 8 PROYECTOS');

    await page.waitForFunction(() => document.querySelector('#offline-label')?.textContent === 'Disponible sin conexión');
    await page.reload({ waitUntil: 'load' });
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    await page.waitForFunction(() => !document.querySelector('#explore-start')?.disabled);
    assert.equal(await page.locator('.explore-card').count(), 0, 'No implicit persistence on reload.');
    await context.setOffline(true);
    await page.reload({ waitUntil: 'load' });
    await page.waitForFunction(() => !document.querySelector('#explore-start')?.disabled);
    await page.locator('#explore-file').setInputFiles({
      name: 'offline.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(backup)),
    });
    await page.waitForFunction(() => document.querySelector('#explore-status')?.textContent?.includes('reproducido y comparado íntegramente'));
    assert.equal(await page.locator('.explore-card').count(), 3);
    await context.setOffline(false);
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('cancelling a blocked worker never commits an old result', { timeout: 45_000 }, async () => {
  assert.ok(browserPath);
  const browser = await launch();
  try {
    const context = await browser.newContext({ serviceWorkers: 'block' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await ready(page);
    let requests = 0;
    await context.route('**/assets/explorer.worker-*.js', async (route) => {
      requests++;
      await new Promise((resolve) => setTimeout(resolve, 800));
      try { await route.continue(); } catch { /* cancelled worker has no consumer */ }
    });
    await page.locator('#explore-start').click();
    await page.waitForFunction(() => !document.querySelector('#explore-cancel')?.disabled);
    await page.locator('#explore-cancel').click();
    assert.equal(await page.locator('#explore-cancel').isEnabled(), false);
    assert.equal(await page.locator('.explore-card').count(), 0);
    assert.equal(await page.locator('#result-status').textContent(), 'VIABLES');
    await page.waitForTimeout(1100);
    assert.ok(requests >= 1);
    assert.equal(await page.locator('.explore-card').count(), 0);
    assert.match(await page.locator('#explore-status').textContent(), /cancelada/);
    await context.unrouteAll({ behavior: 'wait' });
    await start(page);
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

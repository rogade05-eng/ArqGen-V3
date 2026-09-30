// Browser smoke of explicit-Z UI and separate JSON replay, including offline.
// Requires a locally available Chromium; no browser download in npm scripts.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';
import { unzipSync } from 'fflate';

const browserPath = process.env.ARQGEN_CHROMIUM_PATH;
const baseUrl = process.env.ARQGEN_E2E_URL || 'http://127.0.0.1:4173/';
const fixture = JSON.parse(await readFile(new URL('../../examples/declared-vertical-v1-request.json', import.meta.url), 'utf8'));

async function getDownload(page, selector) {
  const event = page.waitForEvent('download');
  await page.locator(selector).click();
  const file = await event;
  return { name: file.suggestedFilename(), bytes: await readFile(await file.path()) };
}

async function declareHeights(page) {
  await page.locator('#vertical-floor').fill('0');
  await page.locator('#vertical-wall').fill('3.1');
  await page.locator('#vertical-entry').fill('2.15');
  for (const [room, sill] of Object.entries(fixture.declared_vertical.window_sill_above_floor_m)) {
    await page.locator(`#vertical-sill-${room}`).fill(String(sill));
  }
}

test('UI: cotas explícitas ↔ Rust, descarga/replay atómico y shell offline sin mezclar planos A3',
  { timeout: 120_000 }, async () => {
    assert.ok(browserPath, 'Configura ARQGEN_CHROMIUM_PATH para QA de navegador real.');
    const browser = await chromium.launch({ executablePath: browserPath, headless: true,
      args: ['--no-sandbox', '--disable-dev-shm-usage', '--single-process'] });
    try {
      const context = await browser.newContext({ acceptDownloads: true, serviceWorkers: 'allow' });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      assert.equal((await page.goto(baseUrl, { waitUntil: 'load' }))?.status(), 200);
      await page.locator('#result-view').waitFor({ state: 'visible' });
      await page.locator('#vertical-panel summary').click();
      assert.equal(await page.locator('#vertical-export').isEnabled(), false);
      assert.equal(await page.locator('#vertical-floor').inputValue(), '');
      assert.equal(await page.locator('#vertical-sills input').count(), 7);
      await page.locator('#vertical-generate').click();
      assert.match(await page.locator('#vertical-status').textContent(), /No se modelaron cotas: Declara/);
      assert.equal(await page.locator('#vertical-model').isVisible(), false);
      await declareHeights(page);
      await page.locator('#vertical-generate').click();
      assert.equal(await page.locator('#vertical-status').getAttribute('data-state'), 'ok');
      assert.equal(await page.locator('#vertical-export').isEnabled(), true);
      assert.match(await page.locator('#vertical-model').textContent(), /NO APTO PARA OBRA/);
      assert.equal(await page.locator('#vertical-model tbody tr').count(), 8);
      const download = await getDownload(page, '#vertical-export');
      assert.match(download.name, /^arqgen-cotas-L0-CONCEPTUAL-cand-.*\.json$/);
      const archive = JSON.parse(download.bytes.toString('utf8'));
      assert.equal(archive.format, 'arqgen-declared-vertical-archive-v1');
      assert.deepEqual(archive.request, fixture);
      assert.equal(archive.model.status, 'ok');
      assert.equal(archive.model.levels[0].floor_z_m, 0);
      assert.equal(archive.model.levels[0].wall_top_z_m, 3.1);
      assert.equal(archive.model.facades, null);
      assert.equal(archive.model.roof, null);
      const originalHash = archive.model.model_hash;
      const run = JSON.parse((await getDownload(page, '#export-json')).bytes.toString('utf8'));
      assert.equal(run.generation.input_hash, archive.model.source.input_hash);
      const zip = unzipSync((await getDownload(page, '#export-drawings')).bytes);
      const level2d = JSON.parse(new TextDecoder().decode(zip['nivel-0-2d.json']));
      assert.equal(level2d.level.elevation_m, null, 'El ZIP A3 sigue SIN cotas Z.');

      await page.locator('#vertical-sill-bathroom-1').fill('1.5');
      assert.equal(await page.locator('#vertical-export').isEnabled(), false);
      assert.equal(await page.locator('#vertical-model').isVisible(), false);
      assert.equal(await page.locator('#export-json').isEnabled(), true, 'Editar solo Z no invalida v8.');
      await page.locator('#vertical-generate').click();
      const changed = JSON.parse((await getDownload(page, '#vertical-export')).bytes.toString('utf8'));
      assert.notEqual(changed.model.model_hash, originalHash);
      assert.equal(changed.model.source.input_hash, archive.model.source.input_hash);

      const tampered = structuredClone(archive);
      tampered.model.levels[0].openings[0].top_z_m += 0.1;
      await page.locator('#vertical-file').setInputFiles({ name: 'falso.json', mimeType: 'application/json',
        buffer: Buffer.from(JSON.stringify(tampered)) });
      await page.waitForFunction(() => /No se abrió|difiere/.test(document.querySelector('#vertical-status')?.textContent || ''));
      assert.equal(await page.locator('#vertical-export').isEnabled(), false);
      assert.equal(await page.locator('#result-status').textContent(), 'VIABLES');
      await page.locator('#vertical-file').setInputFiles({ name: 'original.json', mimeType: 'application/json',
        buffer: download.bytes });
      await page.waitForFunction(() => document.querySelector('#vertical-export')?.disabled === false);
      assert.equal(await page.locator('#vertical-sill-bathroom-1').inputValue(), '1.4');
      assert.match(await page.locator('#vertical-status').textContent(), /replay íntegro/);

      await page.locator('#alt-tab-1').click();
      assert.equal(await page.locator('#vertical-export').isEnabled(), false);
      assert.equal(await page.locator('#vertical-floor').inputValue(), '');
      await page.locator('#vertical-file').setInputFiles({ name: 'otro-candidato.json', mimeType: 'application/json',
        buffer: download.bytes });
      await page.waitForFunction(() => /no corresponde/.test(document.querySelector('#vertical-status')?.textContent || ''));
      assert.equal(await page.locator('#vertical-export').isEnabled(), false);
      await page.locator('#alt-tab-0').click();
      await page.locator('#vertical-file').setInputFiles({ name: 'original-otra-vez.json', mimeType: 'application/json',
        buffer: download.bytes });
      await page.waitForFunction(() => document.querySelector('#vertical-export')?.disabled === false);
      await page.evaluate(() => navigator.serviceWorker?.ready);
      await context.setOffline(true);
      await page.reload({ waitUntil: 'load' });
      await page.locator('#result-view').waitFor({ state: 'visible' });
      await page.locator('#vertical-panel summary').click();
      assert.equal(await page.locator('#vertical-export').isEnabled(), false, 'No hay autosave de cotas.');
      await page.locator('#vertical-file').setInputFiles({ name: 'offline.json', mimeType: 'application/json',
        buffer: download.bytes });
      await page.waitForFunction(() => document.querySelector('#vertical-export')?.disabled === false);
      assert.equal(await page.locator('#vertical-model tbody tr').count(), 8);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });

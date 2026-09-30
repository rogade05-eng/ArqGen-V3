// Optional real-browser smoke test of the production bundle. It needs a
// locally installed Chromium/Chrome; npm never downloads a browser binary.
// Start `npm run preview --prefix web -- --port 4173` after building, then set
// ARQGEN_CHROMIUM_PATH and run `npm run test:e2e --prefix web`.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { chromium } from 'playwright-core';
import { unzipSync } from 'fflate';

const browserPath = process.env.ARQGEN_CHROMIUM_PATH;
const baseUrl = process.env.ARQGEN_E2E_URL || 'http://127.0.0.1:4173/'; // Only the test driver runs locally.

async function exportJson(page, selector) {
  const download = page.waitForEvent('download');
  await page.locator(selector).click();
  const file = await download;
  assert.match(file.suggestedFilename(), /\.json$/);
  return JSON.parse(await readFile(await file.path(), 'utf8'));
}

async function expectResult(page) {
  await page.locator('#result-view').waitFor({ state: 'visible' });
  assert.equal(await page.locator('#result-status').textContent(), 'VIABLES');
  assert.equal(await page.locator('#scope-status').textContent(), 'NO EVALUADO');
}

test('bundle real: láminas A3, dos recortes/zonas, replay, IndexedDB y recarga offline', { timeout: 120_000 }, async () => {
  assert.ok(browserPath, 'Configura ARQGEN_CHROMIUM_PATH con un Chromium/Chrome local (sin descarga implícita).');
  const browser = await chromium.launch({
    executablePath: browserPath,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--single-process'],
  });
  try {
    const context = await browser.newContext({ acceptDownloads: true, serviceWorkers: 'allow' });
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    const response = await page.goto(baseUrl, { waitUntil: 'load' });
    assert.equal(response?.status(), 200, 'El test debe ejecutarse contra el build servido por Vite preview.');
    await expectResult(page);
    assert.equal(await page.locator('#drawing-preview').isVisible(), true);
    await page.locator('#drawing-preview summary').click();
    await page.waitForFunction(() => {
      const images = [...document.querySelectorAll('.drawing-preview-card img')];
      return images.length === 4 && images.every((image) => image.complete && image.naturalWidth > 0);
    });
    const captions = await page.locator('.drawing-preview-card figcaption').allTextContents();
    assert.deepEqual(captions.map((text) => text.slice(0, 4)), ['A-01', 'A-02', 'A-03', 'A-04']);
    for (const caption of captions) assert.match(caption, /1:(50|100|200|500|1000|2000|5000)$/);
    const sheetsDownloaded = page.waitForEvent('download');
    await page.locator('#export-drawings').click();
    const sheetZip = await sheetsDownloaded;
    assert.match(sheetZip.suggestedFilename(), /^arqgen-laminas-CONCEPTUAL-cand-.*\.zip$/);
    const files = unzipSync(await readFile(await sheetZip.path()));
    const sheetManifest = JSON.parse(new TextDecoder().decode(files['manifest.json']));
    assert.deepEqual(sheetManifest.sheets.map((sheet) => sheet.number), ['A-01', 'A-02', 'A-03', 'A-04']);
    assert.equal(sheetManifest.format, 'arqgen-conceptual-svg-sheets-v2');
    assert.match(new TextDecoder().decode(files['A-03-planta-cotas.svg']), /NO APTO PARA OBRA/);
    assert.match(new TextDecoder().decode(files['A-04-envolvente-2d.svg']), /P01/);
    const level = JSON.parse(new TextDecoder().decode(files['nivel-0-2d.json']));
    assert.equal(level.source_candidate_id, sheetManifest.candidate_id);
    assert.equal(level.level.elevation_m, null);
    assert.ok(level.footprint.vertices.length >= 4 && level.perimeter_openings.length > 1);
    assert.equal(JSON.parse(new TextDecoder().decode(files['origen-v8.json'])).generation.status, 'ok');
    assert.equal(await page.locator('#export-feedback').getAttribute('data-state'), 'ok');
    await page.locator('input[name="plot_notch_enabled"]').check();
    assert.equal(await page.locator('#export-drawings').isEnabled(), false, 'Cambiar la entrada invalida la exportación.');
    assert.equal(await page.locator('#drawing-preview').isVisible(), false, 'Un croquis obsoleto no mantiene su vista previa habilitada.');
    await page.locator('input[name="plot_notch_2_enabled"]').check();
    await page.locator('input[name="notch_2_depth"]').fill('10');
    await page.locator('input[name="reserve_enabled"]').check();
    await page.locator('input[name="reserve_2_enabled"]').check();
    await page.locator('input[name="reserve_2_x"]').fill('14');
    await page.locator('input[name="reserve_2_y"]').fill('16'); // touches the right cut at x=15, no intrusion
    await page.locator('input[name="reserve_2_width"]').fill('1');
    await page.locator('#generate-button').click();
    await expectResult(page);
    assert.match(await page.locator('#site-plot-summary').textContent(), /326/);
    const exported = await exportJson(page, '#export-json');
    assert.equal(exported.generation.status, 'ok');
    assert.equal(exported.generation.site_plot.shape, 'rear_both_corners_notched');
    assert.equal(exported.generation.site_plot.vertices.length, 8);
    assert.deepEqual(exported.generation.site_plot.rear_notches.map((notch) => notch.side), ['left', 'right']);
    assert.equal(exported.generation.site.plot_area, 326);
    assert.equal(exported.generation.site.unreserved_buildable_area, 208);
    assert.equal(exported.generation.site_reservations.areas.length, 2);
    assert.equal(exported.generation.alternatives.length, 3);
    assert.ok(exported.generation.alternatives[0].svg.includes('<svg'));

    await page.locator('#save-scenario').click();
    assert.match(await page.locator('#comparison-count').textContent(), /^1 \/ 3/);
    await page.locator('input[name="fan_reference_pressure_pa"]').fill('45');
    await page.locator('#generate-button').click();
    await expectResult(page);
    await page.locator('#save-scenario').click();
    assert.match(await page.locator('#comparison-count').textContent(), /^2 \/ 3/);
    const comparison = await exportJson(page, '#export-comparison');
    assert.equal(comparison.format, 'arqgen-illustrative-comparison-v8');
    assert.equal(comparison.scenarios.length, 2);
    const altered = structuredClone(comparison);
    altered.scenarios[0].generation.site_plot.vertices[4].x += 1;
    await page.locator('#import-file').setInputFiles({
      name: 'croquis-falsificado.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(altered)),
    });
    await page.waitForFunction(() => document.querySelector('#import-feedback')?.dataset.state === 'error');
    assert.match(await page.locator('#import-feedback').textContent(), /No se importó/);
    assert.match(await page.locator('#comparison-count').textContent(), /^2 \/ 3/, 'Una importación alterada no reemplaza el cuaderno.');

    await page.locator('#import-file').setInputFiles({
      name: 'comparativa-v8.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(comparison)),
    });
    await page.waitForFunction(() => document.querySelector('#import-feedback')?.dataset.state === 'ok');
    assert.match(await page.locator('#comparison-count').textContent(), /^2 \/ 3/);
    assert.equal(await page.locator('input[name="fan_reference_pressure_pa"]').inputValue(), '60',
      'Una comparativa verificada enfoca por defecto su primera corrida.');
    await page.getByRole('button', { name: 'Regenerar y examinar escenario 2' }).click();
    await expectResult(page);
    assert.equal(await page.locator('input[name="fan_reference_pressure_pa"]').inputValue(), '45');
    await page.locator('#save-local').click();
    await page.waitForFunction(() => document.querySelector('#local-feedback')?.textContent?.includes('Copia guardada'));
    assert.equal(await page.locator('#local-feedback').getAttribute('data-state'), 'ok');

    // Give the service worker time to cache the exact four production files,
    // then reload online to ensure this page is actually under SW control.
    await page.waitForFunction(() => document.querySelector('#offline-label')?.textContent === 'Disponible sin conexión');
    await page.reload({ waitUntil: 'load' });
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    await expectResult(page);
    assert.match(await page.locator('#comparison-count').textContent(), /^0 \/ 3/, 'El cuaderno no se auto-restaura al arrancar.');
    await context.setOffline(true);
    await page.reload({ waitUntil: 'load' });
    await expectResult(page);
    await page.locator('#load-local').click();
    await page.waitForFunction(() => document.querySelector('#local-feedback')?.textContent?.includes('Copia reabierta'));
    assert.match(await page.locator('#comparison-count').textContent(), /^2 \/ 3/);
    assert.equal(await page.locator('input[name="plot_notch_2_enabled"]').isChecked(), true);
    assert.equal(await page.locator('input[name="reserve_2_enabled"]').isChecked(), true);
    assert.equal(await page.locator('input[name="fan_reference_pressure_pa"]').inputValue(), '45');
    if (!await page.locator('#drawing-preview').evaluate((element) => element.open))
      await page.locator('#drawing-preview summary').click();
    await page.waitForFunction(() => [...document.querySelectorAll('.drawing-preview-card img')].length === 4 &&
      [...document.querySelectorAll('.drawing-preview-card img')].every((image) => image.complete && image.naturalWidth > 0));
    const offlineDownload = page.waitForEvent('download');
    await page.locator('#export-drawings').click();
    const offlineZip = unzipSync(await readFile(await (await offlineDownload).path()));
    assert.deepEqual(JSON.parse(new TextDecoder().decode(offlineZip['manifest.json'])).sheets.map((sheet) => sheet.number),
      ['A-01', 'A-02', 'A-03', 'A-04'], 'ZIP y miniaturas funcionan tras recargar y reabrir una copia sin red.');
    assert.deepEqual(pageErrors, [], 'Sin errores JavaScript durante generación, importación o recarga offline.');
    await context.setOffline(false);
  } finally {
    await browser.close();
  }
});

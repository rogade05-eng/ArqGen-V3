// Optional Chromium E2E against the BUILT preview, not against Vite dev.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { chromium } from 'playwright-core';

const browserPath = process.env.ARQGEN_CHROMIUM_PATH;
const baseUrl = process.env.ARQGEN_E2E_URL || 'http://127.0.0.1:4173/'; // Node test driver only.

async function expectResult(page) {
  await page.locator('#result-view').waitFor({ state: 'visible' });
  assert.equal(await page.locator('#result-status').textContent(), 'VIABLES');
  assert.equal(await page.locator('#scope-status').textContent(), 'NO EVALUADO');
}
async function waitCount(page, value) {
  await page.waitForFunction((prefix) => document.querySelector('#portfolio-count')?.textContent?.startsWith(prefix), `${value} / 8`);
}

const forgedName = '<svg onload=alert(1)>';
test('cartera: varios proyectos, backup íntegro, conflicto entre pestañas, corrupción y reabrir offline', { timeout: 120_000 }, async () => {
  assert.ok(browserPath, 'Configura ARQGEN_CHROMIUM_PATH con un Chromium/Chrome local.');
  const browser = await chromium.launch({
    executablePath: browserPath, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--single-process'],
  });
  try {
    const context = await browser.newContext({ acceptDownloads: true, serviceWorkers: 'allow' });
    const page = await context.newPage();
    const pageErrors = [];
    const dialogs = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    page.on('dialog', async (dialog) => { dialogs.push(dialog.type()); await dialog.accept(); });
    assert.equal((await page.goto(baseUrl, { waitUntil: 'load' }))?.status(), 200);
    await expectResult(page);
    await waitCount(page, 0);
    await page.locator('#approve').click();
    assert.match(await page.locator('#choice-title').textContent(), /Preferencia preliminar/);
    await page.locator('#portfolio-name').fill('Patio A');
    await page.locator('#portfolio-create').click();
    await waitCount(page, 1);
    assert.match(await page.locator('#portfolio-status').textContent(), /Patio A.*creado/);
    assert.equal(await page.locator('#choice-title').textContent(), 'Tu criterio es el último paso.',
      'A new project never inherits an old hash-matched preference.');
    assert.match(await page.locator('#history-count').textContent(), /^1 \/ 1/);
    await page.locator('input[name="seed"]').fill('43');
    await page.locator('#generate-button').click();
    await expectResult(page);
    assert.match(await page.locator('#history-count').textContent(), /^2 \/ 2/);
    await page.locator('#history-undo').click();
    assert.equal(await page.locator('input[name="seed"]').inputValue(), '42');
    await page.locator('#history-redo').click();
    assert.equal(await page.locator('input[name="seed"]').inputValue(), '43');
    await page.locator('#history-undo').click();
    await page.locator('input[name="seed"]').fill('44');
    await page.locator('#history-undo').click(); // stale edit discarded, not a step backward
    assert.equal(await page.locator('input[name="seed"]').inputValue(), '42');
    assert.equal(await page.locator('#history-redo').isEnabled(), true);

    // A second independent job: two rear cuts, two voluntary areas, two runs.
    await page.locator('input[name="plot_notch_enabled"]').check();
    await page.locator('input[name="plot_notch_2_enabled"]').check();
    await page.locator('input[name="notch_2_depth"]').fill('10');
    await page.locator('input[name="reserve_enabled"]').check();
    await page.locator('input[name="reserve_2_enabled"]').check();
    await page.locator('input[name="reserve_2_x"]').fill('14');
    await page.locator('input[name="reserve_2_y"]').fill('16');
    await page.locator('input[name="reserve_2_width"]').fill('1');
    await page.locator('#generate-button').click();
    await expectResult(page);
    await page.locator('#save-scenario').click();
    await page.locator('input[name="fan_reference_pressure_pa"]').fill('45');
    await page.locator('#generate-button').click();
    await expectResult(page);
    await page.locator('#save-scenario').click();
    assert.match(await page.locator('#comparison-count').textContent(), /^2 \/ 3/);
    await page.locator('#portfolio-name').fill(forgedName);
    await page.locator('#portfolio-create').click();
    await waitCount(page, 2);
    assert.equal(await page.locator('#portfolio-list').locator('svg').count(), 0,
      'El nombre malicioso se muestra como texto, no como contenido HTML.');
    assert.deepEqual(dialogs, []);

    const download = page.waitForEvent('download');
    await page.locator('#portfolio-export').click();
    const file = await download;
    const backup = JSON.parse(await readFile(await file.path(), 'utf8'));
    assert.equal(backup.format, 'arqgen-illustrative-portfolio-v1');
    assert.equal(backup.entries.length, 2);
    assert.equal(backup.entries.find((entry) => entry.name === forgedName).snapshot.focus.generation.site.plot_area, 326);
    assert.equal(backup.entries.find((entry) => entry.name === 'Patio A').snapshot.focus.generation.site.plot_area, 396);
    assert.equal(backup.entries.find((entry) => entry.name === forgedName).snapshot.scenarios.length, 2);

    await page.getByRole('button', { name: 'Borrar Patio A' }).click();
    await waitCount(page, 1);
    assert.deepEqual(dialogs, ['confirm']);
    const corrupted = structuredClone(backup);
    corrupted.entries.find((entry) => entry.name === forgedName).snapshot.scenarios[1].generation.site_plot.vertices[4].x += 1;
    await page.locator('#portfolio-file').setInputFiles({
      name: 'falsificado.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(corrupted)),
    });
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.dataset.state === 'error');
    assert.match(await page.locator('#portfolio-status').textContent(), /No se restauró la cartera/);
    await waitCount(page, 1);
    assert.equal(dialogs.length, 1, 'Un respaldo adulterado no abre el diálogo de reemplazo.');

    await page.locator('#portfolio-file').setInputFiles({
      name: 'respaldo-verificado.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(backup)),
    });
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('restaurados atómicamente'));
    await waitCount(page, 2);
    assert.equal(dialogs.length, 2);
    assert.equal(await page.locator('input[name="plot_notch_2_enabled"]').isChecked(), true,
      'Restaurar la cartera no sustituye el plano en pantalla.');
    await page.getByRole('button', { name: 'Abrir y verificar Patio A' }).click();
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('Proyecto «Patio A» abierto'));
    await expectResult(page);
    assert.equal(await page.locator('input[name="plot_notch_enabled"]').isChecked(), false);
    assert.match(await page.locator('#comparison-count').textContent(), /^0 \/ 3/);
    await page.getByRole('button', { name: `Abrir y verificar ${forgedName}` }).click();
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('Proyecto «<svg onload=alert(1)>» abierto'));
    await expectResult(page);
    assert.equal(await page.locator('input[name="plot_notch_2_enabled"]').isChecked(), true);
    assert.match(await page.locator('#comparison-count').textContent(), /^2 \/ 3/);

    // A locally corrupted saved result cannot replace the visible (still
    // verified) plan, and it also blocks export rather than leaking a forgery.
    await page.evaluate(async (key) => new Promise((resolve, reject) => {
      const open = indexedDB.open('arqgen-portfolio-v1', 1);
      open.onerror = () => reject(open.error);
      open.onsuccess = () => {
        const db = open.result;
        const tx = db.transaction('projects', 'readwrite');
        const store = tx.objectStore('projects');
        const get = store.get(key);
        get.onsuccess = () => {
          const altered = get.result;
          altered.snapshot.focus.generation.site.plot_area += 1;
          store.put(altered);
        };
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onabort = () => { db.close(); reject(tx.error); };
      };
    }), backup.entries.find((entry) => entry.name === 'Patio A').id);
    await page.getByRole('button', { name: 'Abrir y verificar Patio A' }).click();
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('No se abrió el proyecto'));
    assert.equal(await page.locator('input[name="plot_notch_2_enabled"]').isChecked(), true);
    await page.locator('#portfolio-export').click();
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('No se descargó la cartera'));
    await page.locator('#portfolio-file').setInputFiles({
      name: 'reponer.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(backup)),
    });
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('restaurados atómicamente'));

    // Optimistic concurrency: another tab can update a project, but an older
    // tab must never overwrite it under the same name/ID by accident.
    await page.getByRole('button', { name: 'Abrir y verificar Patio A' }).click();
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('Proyecto «Patio A» abierto'));
    const otherTab = await context.newPage();
    otherTab.on('pageerror', (error) => pageErrors.push(error.message));
    await otherTab.goto(baseUrl, { waitUntil: 'load' });
    await expectResult(otherTab);
    await waitCount(otherTab, 2);
    await otherTab.getByRole('button', { name: 'Abrir y verificar Patio A' }).click();
    await otherTab.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('Proyecto «Patio A» abierto'));
    await otherTab.locator('input[name="fan_reference_pressure_pa"]').fill('45');
    await otherTab.locator('#generate-button').click();
    await expectResult(otherTab);
    await otherTab.locator('#portfolio-update').click();
    await otherTab.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('actualizado'));
    await page.locator('#portfolio-name').fill('Patio A editado desde pestaña antigua');
    await page.locator('#portfolio-update').click();
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('Conflicto:'));
    assert.equal(await page.locator('#portfolio-status').getAttribute('data-state'), 'error');

    // Installed service worker serves the app offline; the portfolio stays
    // opt-in and reopening still replays the same Rust WASM core.
    await page.waitForFunction(() => document.querySelector('#offline-label')?.textContent === 'Disponible sin conexión');
    await page.reload({ waitUntil: 'load' });
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    await expectResult(page);
    await waitCount(page, 2);
    await context.setOffline(true);
    await page.reload({ waitUntil: 'load' });
    await expectResult(page);
    await waitCount(page, 2);
    await page.getByRole('button', { name: 'Abrir y verificar Patio A' }).click();
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('Proyecto «Patio A» abierto'));
    assert.equal(await page.locator('input[name="fan_reference_pressure_pa"]').inputValue(), '45');
    assert.deepEqual(pageErrors, []);
    await context.setOffline(false);
  } finally { await browser.close(); }
});

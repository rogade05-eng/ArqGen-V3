// Native Tauri/Windows smoke test. NOT part of `npm test` or Chromium E2E.
// This command MUST fail on Linux/macOS; a real WebView2 + EdgeDriver session
// is the only acceptable proof. See docs/QA_WINDOWS_WEBVIEW2.md.
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { NativeWebDriver } from './native/webdriver.mjs';
import { callCore } from '../src/core-client.js';
import { makeExplorationArchive } from '../src/exploration.js';
import { makeVerticalArchive } from '../src/vertical.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const web = resolve(root, 'web');
const reportDir = resolve(web, 'webview2-qa'); // ignored; may contain a screenshot
const driverUrl = 'http://127.0.0.1:4444';
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

async function until(label, probe, timeout = 30_000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const value = await probe();
    if (value) return value;
    await sleep(200);
  }
  throw new Error(`Tiempo agotado esperando ${label} en WebView2 (${timeout} ms).`);
}

export async function buildArchives(dir, packedPath = resolve(root, 'dist/web/core.wasm')) {
  // The input/result is manufactured by the same versioned WASM and is
  // intentionally NOT loaded as a cached response by the desktop UI.
  const wasm = await readFile(resolve(web, 'public/core.wasm'));
  const packed = await readFile(packedPath);
  assert.equal(createHash('sha256').update(wasm).digest('hex'),
    createHash('sha256').update(packed).digest('hex'), 'Bundled WASM must match tested WASM.');
  const { instance } = await WebAssembly.instantiate(wasm);
  const input = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
  input.rules = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
  const result = callCore(instance.exports, 'arq_explore', { input, seed_count: 2 });
  assert.equal(result.status, 'ok');
  assert.equal(result.generated, 96);
  const document = makeExplorationArchive(input, 2, result);
  const valid = join(dir, 'lote-verificado.json');
  const forged = join(dir, 'lote-falso.json');
  await writeFile(valid, JSON.stringify(document));
  const changed = structuredClone(document);
  changed.exploration.alternatives[0].candidate.svg += '<script>forged</script>';
  await writeFile(forged, JSON.stringify(changed));
  const verticalRequest = JSON.parse(await readFile(resolve(root, 'examples/declared-vertical-v1-request.json'), 'utf8'));
  const verticalModel = callCore(instance.exports, 'arq_vertical', verticalRequest);
  assert.equal(verticalModel.status, 'ok');
  const verticalArchive = makeVerticalArchive(verticalRequest, verticalModel);
  const verticalValid = join(dir, 'cotas-verificadas.json');
  const verticalForged = join(dir, 'cotas-falsas.json');
  await writeFile(verticalValid, JSON.stringify(verticalArchive));
  const alteredVertical = structuredClone(verticalArchive);
  alteredVertical.model.levels[0].openings[0].top_z_m += 0.1;
  await writeFile(verticalForged, JSON.stringify(alteredVertical));
  return { valid, forged, verticalRequest, verticalValid, verticalForged };
}

async function upload(driver, path, selector = '#explore-file') {
  // Hidden file input: temporarily expose it to *WebDriver*; use native file
  // sendKeys rather than modifying File/Blob APIs or trusting a saved model.
  await driver.execute(`document.querySelector('${selector}').hidden = false; return true;`);
  try { await driver.sendFile(selector, path); }
  finally { await driver.execute(`document.querySelector('${selector}').hidden = true; return true;`); }
}

async function openVerticalPanel(driver) {
  if (!(await driver.execute('return document.querySelector("#vertical-panel")?.open === true;'))) {
    await driver.click('#vertical-panel summary');
  }
}

async function scenario(driver, files) {
  const initial = await until('respuesta Rust/WASM inicial', () => driver.execute(`
    const result = document.querySelector('#result-view');
    if (!result || result.hidden) return null;
    return {
      status: document.querySelector('#result-status')?.textContent,
      scope: document.querySelector('#scope-status')?.textContent,
      svg: !!document.querySelector('#plan svg'),
      context: typeof window.isTauri === 'function' && window.isTauri(),
      noGlobalApi: typeof window.__TAURI__ === 'undefined',
      mode: document.querySelector('#offline-label')?.textContent,
      host: location.host,
      protocol: location.protocol,
      userAgent: navigator.userAgent,
      portfolio: document.querySelector('#portfolio-count')?.textContent,
    };
  `), 45_000);
  assert.equal(initial.status, 'VIABLES');
  assert.equal(initial.scope, 'NO EVALUADO');
  assert.equal(initial.svg, true, 'SVG from bundled Rust/WASM must render.');
  assert.equal(initial.context, true, 'Tauri context is required; browser mode is forbidden.');
  assert.equal(initial.noGlobalApi, true, 'Global Tauri API must remain disabled.');
  assert.match(initial.mode, /Aplicación de escritorio · sin nube/);
  assert.ok(initial.host === 'tauri.localhost' || initial.protocol === 'tauri:',
    `Not the bundled Tauri protocol: ${initial.protocol}//${initial.host}`);
  assert.match(initial.userAgent, /Edg\//, 'The renderer must be native Edge WebView2.');
  assert.match(initial.portfolio, /^0 \/ 8/, 'QA requires an empty isolated WebView2 profile.');
  console.log(`OK: WebView2 nativo, ${initial.protocol}//${initial.host}, Rust/WASM y ámbito NO EVALUADO.`);
  await driver.execute(`
    window.__qaIssues = [];
    window.addEventListener('error', (e) => window.__qaIssues.push(e.message));
    window.addEventListener('unhandledrejection', (e) => window.__qaIssues.push(String(e.reason)));
    window.addEventListener('securitypolicyviolation', (e) => window.__qaIssues.push('CSP: ' + e.violatedDirective));
    return true;
  `);

  await openVerticalPanel(driver);
  const emptyZ = await driver.execute('return document.querySelector("#vertical-floor").value === "";');
  assert.equal(emptyZ, true, 'WebView2 must not prefill a guessed Z.');
  const sillCount = await driver.execute(`
    const heights = arguments[0];
    function fill(id, value) {
      const field = document.querySelector(id);
      if (!field) throw new Error('Falta ' + id);
      field.value = String(value);
      field.dispatchEvent(new Event('input', { bubbles: true }));
    }
    fill('#vertical-floor', heights.floor_z_m);
    fill('#vertical-wall', heights.wall_top_z_m);
    fill('#vertical-entry', heights.entry_head_above_floor_m);
    for (const [room, sill] of Object.entries(heights.window_sill_above_floor_m)) {
      fill('#vertical-sill-' + room, sill);
    }
    return document.querySelectorAll('#vertical-sills input').length;
  `, [files.verticalRequest.declared_vertical]);
  assert.equal(sillCount, 7);
  await driver.click('#vertical-generate');
  const zModel = await until('cotas Z explícitas de Rust en WebView2', () => driver.execute(`
    const status = document.querySelector('#vertical-status');
    if (status?.dataset.state === 'error') throw new Error(status.textContent);
    return status?.dataset.state === 'ok' && !document.querySelector('#vertical-export')?.disabled ? {
      openings: document.querySelectorAll('#vertical-model tbody tr').length,
      title: document.querySelector('#vertical-model')?.textContent,
    } : null;
  `));
  assert.equal(zModel.openings, 8);
  assert.match(zModel.title, /NO APTO PARA OBRA/);
  await upload(driver, files.verticalForged, '#vertical-file');
  const badZ = await until('rechazo de archivo vertical adulterado en WebView2', () => driver.execute(`
    const status = document.querySelector('#vertical-status');
    return status?.dataset.state === 'error' ? {
      message: status.textContent,
      exportDisabled: document.querySelector('#vertical-export')?.disabled,
      v8: document.querySelector('#result-status')?.textContent,
    } : null;
  `));
  assert.match(badZ.message, /difiere del replay íntegro/);
  assert.equal(badZ.exportDisabled, true);
  assert.equal(badZ.v8, 'VIABLES');
  await upload(driver, files.verticalValid, '#vertical-file');
  const reopenedZ = await until('replay de cotas Z en WebView2', () => driver.execute(`
    const status = document.querySelector('#vertical-status');
    if (status?.dataset.state === 'error') throw new Error(status.textContent);
    return status?.textContent?.includes('replay íntegro') &&
      !document.querySelector('#vertical-export')?.disabled ?
      document.querySelectorAll('#vertical-model tbody tr').length : null;
  `));
  assert.equal(reopenedZ, 8);
  console.log('OK: Z explícita en WebView2; archivo adulterado rechazado y JSON separado reabierto con Rust.');

  await driver.execute(`document.querySelector('#explore-count').value = '2'; return true;`);
  await driver.click('#explore-start');
  const explored = await until('worker Rust multisemilla', () => driver.execute(`
    const status = document.querySelector('#explore-status');
    if (status?.dataset.state === 'error') throw new Error(status.textContent);
    return status?.textContent?.includes('Lote calculado') &&
      document.querySelectorAll('.explore-card').length === 3 &&
      [...document.querySelectorAll('.explore-plan')].every((img) => img.complete) ? {
      text: document.querySelector('#explore-summary')?.textContent,
      count: document.querySelectorAll('.explore-card').length,
      image: [...document.querySelectorAll('.explore-plan')]
        .every((img) => img.naturalWidth > 0),
      issues: window.__qaIssues,
    } : null;
  `));
  assert.match(explored.text, /96 variantes ensayadas/);
  assert.equal(explored.count, 3);
  assert.equal(explored.image, true, 'All worker SVG thumbnails must load in WebView2.');
  assert.deepEqual(explored.issues, [], 'No JS or CSP errors while loading worker/WASM/SVG.');
  console.log('OK: worker, CSP, 96 variantes y tres imágenes SVG nativas.');

  await upload(driver, files.forged);
  const rejected = await until('rechazo de lote falsificado', () => driver.execute(`
    const status = document.querySelector('#explore-status');
    return status?.dataset.state === 'error' ? {
      message: status.textContent,
      count: document.querySelectorAll('.explore-card').length,
      seed: document.querySelector('input[name="seed"]').value,
    } : null;
  `));
  assert.match(rejected.message, /no coincide íntegramente/);
  assert.equal(rejected.count, 3, 'Failed replay must not replace the displayed plans.');
  assert.equal(rejected.seed, '42');
  console.log('OK: lote alterado rechazado sin mutación de planos/encargo.');

  await upload(driver, files.valid);
  const reopened = await until('replay completo del lote válido', () => driver.execute(`
    const status = document.querySelector('#explore-status');
    if (status?.dataset.state === 'error') throw new Error(status.textContent);
    return status?.textContent?.includes('reproducido y comparado íntegramente') &&
      document.querySelectorAll('.explore-card').length === 3 ? {
      count: document.querySelectorAll('.explore-card').length,
      history: document.querySelector('#history-count')?.textContent,
      seed: document.querySelector('input[name="seed"]').value,
      issues: window.__qaIssues,
    } : null;
  `));
  assert.equal(reopened.count, 3);
  assert.match(reopened.history, /^1 \/ 1/);
  assert.equal(reopened.seed, '42');
  assert.deepEqual(reopened.issues, []);
  console.log('OK: importación/replay completo del lote con WebView2; no se heredó aprobación.');

  await driver.execute(`
    const field = document.querySelector('#portfolio-name');
    field.value = 'QA WebView2 temporal';
    field.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  `);
  await driver.click('#portfolio-create');
  await until('guardado explícito IndexedDB', () => driver.execute(`
    return document.querySelector('#portfolio-count')?.textContent?.startsWith('1 / 8') || false;
  `));
  console.log('OK: cartera local optativa en IndexedDB de WebView2.');

  await driver.refresh();
  const afterReload = await until('recarga Tauri sin servidor de desarrollo', () => driver.execute(`
    if (document.querySelector('#result-view')?.hidden ||
        !document.querySelector('#portfolio-count')?.textContent?.startsWith('1 / 8')) return null;
    return {
      status: document.querySelector('#result-status')?.textContent,
      portfolio: document.querySelector('#portfolio-count')?.textContent,
      count: document.querySelectorAll('.explore-card').length,
      host: location.host,
    };
  `), 45_000);
  assert.equal(afterReload.status, 'VIABLES');
  assert.match(afterReload.portfolio, /^1 \/ 8/);
  assert.equal(afterReload.count, 0, 'Batch is memory-only across reload.');
  assert.equal(afterReload.host, initial.host);
  await driver.click('#portfolio-list .portfolio-item button[aria-label^="Abrir y verificar"]');
  const opened = await until('reapertura del proyecto con replay Rust', () => driver.execute(`
    return document.querySelector('#portfolio-status')?.textContent?.includes('Proyecto «QA WebView2 temporal» abierto') || false;
  `));
  assert.equal(opened, true);
  assert.equal(await driver.execute('return document.querySelector("#result-status").textContent;'), 'VIABLES');
  const zNotInPortfolio = await driver.execute('return document.querySelector("#vertical-export").disabled;');
  assert.equal(zNotInPortfolio, true, 'La cartera v8 no guarda hipótesis Z.');
  await driver.execute(`
    window.__qaIssues = [];
    window.addEventListener('error', (e) => window.__qaIssues.push(e.message));
    window.addEventListener('unhandledrejection', (e) => window.__qaIssues.push(String(e.reason)));
    window.addEventListener('securitypolicyviolation', (e) => window.__qaIssues.push('CSP: ' + e.violatedDirective));
    return true;
  `);
  await openVerticalPanel(driver);
  await upload(driver, files.verticalValid, '#vertical-file');
  const afterZReload = await until('archivo Z separado tras abrir cartera WebView2', () => driver.execute(`
    const status = document.querySelector('#vertical-status');
    if (status?.dataset.state === 'error') throw new Error(status.textContent);
    return status?.textContent?.includes('replay íntegro') &&
      !document.querySelector('#vertical-export')?.disabled ?
      document.querySelectorAll('#vertical-model tbody tr').length : null;
  `));
  assert.equal(afterZReload, 8);
  assert.deepEqual(await driver.execute('return window.__qaIssues || [];'), [], 'No se permiten errores JS/CSP tras abrir Z.');
  console.log('OK: recarga/cartera v8 sin Z implícita; archivo vertical reabierto aparte tras replay Rust.');
}

async function run() {
  if (process.platform !== 'win32') {
    throw new Error('QA Nativo NO EJECUTADO: se exige Windows real con Tauri/WebView2; Chromium/Linux no cuenta.');
  }
  const binary = process.env.ARQGEN_TAURI_BINARY;
  if (!binary || !isAbsolute(binary) || !binary.toLowerCase().endsWith('.exe') || !existsSync(binary)) {
    throw new Error('Define ARQGEN_TAURI_BINARY con la ruta absoluta del .exe Tauri ya compilado en Windows.');
  }
  const driverBin = process.env.ARQGEN_TAURI_DRIVER || join(homedir(), '.cargo', 'bin', 'tauri-driver.exe');
  if (!existsSync(driverBin)) throw new Error(`Falta tauri-driver.exe: ${driverBin}. Instálalo antes del QA nativo.`);
  const edgeDriver = process.env.ARQGEN_EDGEDRIVER;
  if (!edgeDriver || !isAbsolute(edgeDriver) || !existsSync(edgeDriver)) {
    throw new Error('Define ARQGEN_EDGEDRIVER con msedgedriver.exe compatible con Edge/WebView2 de este Windows.');
  }
  // Fail closed if another WebDriver already occupies the port.
  try {
    const res = await fetch(`${driverUrl}/status`, { signal: AbortSignal.timeout(1000) });
    if (res) throw new Error('Puerto 4444 ocupado; no se usaría un driver nativo inequívoco.');
  } catch (error) {
    if (error.message.includes('Puerto 4444 ocupado')) throw error;
    // Connection refused is expected before starting tauri-driver.
  }

  const dir = await mkdtemp(join(tmpdir(), 'arqgen-webview2-'));
  const profile = join(dir, 'profile');
  let processDriver;
  let driver;
  let logs = '';
  let spawnError;
  let passed = false;
  try {
    const files = await buildArchives(dir);
    processDriver = spawn(driverBin, ['--native-driver', edgeDriver], {
      windowsHide: true,
      env: { ...process.env, WEBVIEW2_USER_DATA_FOLDER: profile },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    processDriver.on('error', (error) => { spawnError = error; });
    processDriver.stdout.on('data', (chunk) => { logs = (logs + chunk).slice(-24_000); });
    processDriver.stderr.on('data', (chunk) => { logs = (logs + chunk).slice(-24_000); });
    await until('tauri-driver (Windows)', async () => {
      if (spawnError) throw spawnError;
      if (processDriver.exitCode !== null || processDriver.signalCode !== null) {
        throw new Error(`tauri-driver terminó (${processDriver.exitCode || processDriver.signalCode}): ${logs}`);
      }
      try {
        const status = await fetch(`${driverUrl}/status`, { signal: AbortSignal.timeout(2000) });
        return status.ok;
      } catch { return false; }
    }, 30_000);
    driver = new NativeWebDriver(driverUrl);
    await driver.open(binary);
    await scenario(driver, files);
    passed = true;
  } catch (error) {
    console.error('QA NATIVO WEBVIEW2: FALLÓ; no se sustituye por Chromium.');
    console.error(error);
    if (logs) console.error(`Último registro de tauri-driver:\n${logs}`);
    if (driver?.sessionId) {
      try {
        const png = await driver.screenshot();
        await mkdir(reportDir, { recursive: true });
        await writeFile(join(reportDir, 'failure.png'), Buffer.from(png, 'base64'));
        console.error(`Captura de fallo: ${join(reportDir, 'failure.png')}`);
      } catch (captureError) { console.error(`No se pudo capturar pantalla: ${captureError.message}`); }
    }
    throw error;
  } finally {
    try { await driver?.close(); } catch (error) { console.warn(`Cierre de sesión: ${error.message}`); }
    if (processDriver?.pid) {
      spawnSync('taskkill', ['/PID', String(processDriver.pid), '/T', '/F'], { windowsHide: true });
    }
    try { await rm(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 }); }
    catch (error) { console.warn(`Limpia el perfil temporal ${dir} cuando WebView2 cierre: ${error.message}`); }
  }
  if (passed) console.log('QA NATIVO WEBVIEW2: PASÓ el smoke de aplicación ejecutable (NO instalador ni normas).');
}

// Unit tests may import buildArchives on Linux; only direct invocation attempts
// the real native session, and that invocation fails closed outside Windows.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  run().catch((error) => { console.error(error.message); process.exitCode = 1; });
}

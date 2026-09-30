#!/usr/bin/env node
// Experimental distribution only: Zig/Win32 launcher + bundled web/WASM in
// the user's EXTERNAL browser. NEVER present it as the Tauri/WebView2 app.
// The Rust core is a previously versioned WASM, NOT rebuilt in this script.
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { copyFile, mkdir, mkdtemp, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import http from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { inspectWindowsGuiX64 } from './package-windows.mjs';
import { callCore } from '../web/src/core-client.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const web = join(root, 'web');
const dist = join(root, 'dist/web');
const zig = process.env.ARQGEN_ZIG || '/tmp/arqgen-zig/node_modules/@ryoppippi/zig-linux-x64/zig';
const source = join(root, 'native/zig-browser-launcher.c');
const version = JSON.parse(await readFile(join(web, 'package.json'), 'utf8')).version;
const folderName = `ARQ-GEN-LOCAL-NO-TAURI-Windows-x64-${version}`;
const zipName = `${folderName}.zip`;
// The WASM must have been built/tested separately with Rust 1.88 and the
// declared-vertical-v1 ABI. This launcher script never invokes Cargo itself.
const wasmDigest = '4d2cde571b6706b6beafa7f25bf9f1fa18dd90951cf3e4ceacea4dd6c0b7ed01';
const sha = (data) => createHash('sha256').update(data).digest('hex');

function command(file, args, options = {}) {
  const result = spawnSync(file, args, { cwd: root, encoding: 'utf8', stdio: 'inherit', ...options });
  if (result.error || result.status !== 0) {
    throw new Error(`${file} terminó con error ${result.error?.message || result.status}`);
  }
}

async function getAssets() {
  const publicWasm = await readFile(join(web, 'public/core.wasm'));
  assert.equal(sha(publicWasm), wasmDigest,
    'WASM diferente del corte previamente validado; no empaquetar con Rust no recompilado.');
  const builtWasm = await readFile(join(dist, 'core.wasm'));
  assert.equal(sha(builtWasm), wasmDigest, 'El bundle debe contener el MISMO WASM versionado.');
  const { instance } = await WebAssembly.instantiate(publicWasm);
  const input = JSON.parse(await readFile(join(root, 'examples/rectangular.json'), 'utf8'));
  input.rules = JSON.parse(await readFile(join(root, 'knowledge/generic-house.json'), 'utf8'));
  const generation = callCore(instance.exports, 'arq_generate', input);
  assert.equal(generation.status, 'ok', 'El núcleo WASM debe generar el caso de prueba real.');
  assert.ok(generation.alternatives[0].svg.includes('NO APTO PARA OBRA'));
  const verticalRequest = JSON.parse(await readFile(join(root, 'examples/declared-vertical-v1-request.json'), 'utf8'));
  const verticalModel = callCore(instance.exports, 'arq_vertical', verticalRequest);
  const expectedModel = JSON.parse(await readFile(join(root, 'examples/declared-vertical-v1-model.json'), 'utf8'));
  assert.deepEqual(verticalModel, expectedModel, 'El WASM embebido debe verificar Z sin cambiar la salida v8.');

  const bundled = (await readdir(join(dist, 'assets'))).sort();
  assert.ok(bundled.length >= 3 && bundled.length <= 12 &&
    bundled.every((name) => /^[A-Za-z0-9._-]+\.(?:js|css)$/.test(name)),
  'El bundle solo admite JS/CSS propios y WASM; ninguna ruta dinámica.');
  const names = ['index.html', 'sw.js', 'core.wasm', ...bundled.map((name) => `assets/${name}`)];
  const assets = await Promise.all(names.map(async (name) => {
    const data = await readFile(join(dist, name));
    assert.ok(data.length > 0 && data.length < 2_000_000, `Recurso no admitido: ${name}`);
    return { path: `/${name}`, data, mime: name.endsWith('.wasm') ? 'application/wasm' :
      name.endsWith('.css') ? 'text/css; charset=utf-8' :
      name.endsWith('.js') ? 'text/javascript; charset=utf-8' : 'text/html; charset=utf-8' };
  }));
  assert.ok(assets.reduce((sum, asset) => sum + asset.data.length, 0) < 4_000_000);
  return assets;
}

async function writeAssetsHeader(directory, assets) {
  const lines = [
    '#ifndef ARQ_GEN_EMBEDDED_ASSETS_H', '#define ARQ_GEN_EMBEDDED_ASSETS_H',
    '#include <stddef.h>',
    'typedef struct { const char *path; const char *mime; const unsigned char *bytes; unsigned int size; } embedded_asset;',
  ];
  for (const [index, asset] of assets.entries()) {
    lines.push(`static const unsigned char asset_${index}[] = {`);
    for (let offset = 0; offset < asset.data.length; offset += 24) {
      lines.push(`  ${Array.from(asset.data.subarray(offset, offset + 24),
        (byte) => `0x${byte.toString(16).padStart(2, '0')}`).join(', ')},`);
    }
    lines.push('};');
  }
  lines.push('static const embedded_asset embedded_assets[] = {');
  for (const [index, asset] of assets.entries()) {
    lines.push(`  { ${JSON.stringify(asset.path)}, ${JSON.stringify(asset.mime)}, asset_${index}, sizeof(asset_${index}) },`);
  }
  lines.push('};',
    'static const size_t embedded_assets_count = sizeof(embedded_assets) / sizeof(embedded_assets[0]);',
    '#endif');
  await writeFile(join(directory, 'embedded_assets.h'), lines.join('\n'), 'utf8');
}

function hostileHostRequest(baseUrl) {
  return new Promise((fulfill, reject) => {
    const target = new URL(baseUrl);
    const req = http.get({ hostname: target.hostname, port: target.port, path: '/',
      headers: { Host: 'attacker.invalid' } }, (res) => {
      res.resume(); res.on('end', () => fulfill(res.statusCode));
    });
    req.on('error', reject);
  });
}

async function startLinuxServer(executable) {
  const child = spawn(executable, [], { env: { ...process.env, ARQGEN_TEST_PORT: '0' },
    stdio: ['ignore', 'pipe', 'pipe'] });
  let output = '';
  let errors = '';
  child.stderr.on('data', (chunk) => { errors += chunk; });
  const baseUrl = await new Promise((fulfill, reject) => {
    const timer = setTimeout(() => reject(new Error(`Servidor de prueba no arrancó: ${errors}`)), 8_000);
    child.stdout.on('data', (chunk) => {
      output += chunk;
      const match = output.match(/ARQGEN_LOCAL_URL=(http:\/\/127\.0\.0\.1:\d+\/)\s/);
      if (match) { clearTimeout(timer); fulfill(match[1]); }
    });
    child.once('error', (error) => { clearTimeout(timer); reject(error); });
    child.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Servidor salió (${code}): ${errors}`)); });
  });
  return { child, baseUrl };
}

async function testBrowser(baseUrl) {
  const { chromium } = await import('../web/node_modules/playwright-core/index.mjs');
  const browser = await chromium.launch({
    executablePath: process.env.ARQGEN_CHROMIUM_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--single-process', '--no-zygote'],
  });
  try {
    const context = await browser.newContext({ acceptDownloads: true, serviceWorkers: 'allow' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.addInitScript(() => {
      window.__qaCsp = [];
      window.addEventListener('securitypolicyviolation', (event) =>
        window.__qaCsp.push(`${event.violatedDirective}: ${event.blockedURI}`));
    });
    const response = await page.goto(baseUrl, { waitUntil: 'load' });
    assert.equal(response?.status(), 200);
    await page.locator('#result-view').waitFor({ state: 'visible', timeout: 30_000 });
    assert.equal(await page.locator('#result-status').textContent(), 'VIABLES');
    assert.equal(await page.locator('#scope-status').textContent(), 'NO EVALUADO');
    await page.waitForFunction(() => document.querySelector('#offline-label')?.textContent === 'Disponible sin conexión',
      null, { timeout: 15_000 });
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null,
      null, { timeout: 15_000 });
    const verticalRequest = JSON.parse(await readFile(join(root, 'examples/declared-vertical-v1-request.json'), 'utf8'));
    await page.locator('#vertical-panel summary').click();
    assert.equal(await page.locator('#vertical-floor').inputValue(), '', 'No atribuir altura por defecto.');
    await page.locator('#vertical-floor').fill(String(verticalRequest.declared_vertical.floor_z_m));
    await page.locator('#vertical-wall').fill(String(verticalRequest.declared_vertical.wall_top_z_m));
    await page.locator('#vertical-entry').fill(String(verticalRequest.declared_vertical.entry_head_above_floor_m));
    for (const [room, sill] of Object.entries(verticalRequest.declared_vertical.window_sill_above_floor_m)) {
      await page.locator(`#vertical-sill-${room}`).fill(String(sill));
    }
    await page.locator('#vertical-generate').click();
    assert.equal(await page.locator('#vertical-export').isEnabled(), true);
    const verticalDownload = page.waitForEvent('download');
    await page.locator('#vertical-export').click();
    const verticalFile = await verticalDownload;
    const verticalArchiveBytes = await readFile(await verticalFile.path());
    const verticalArchive = JSON.parse(verticalArchiveBytes.toString('utf8'));
    assert.equal(verticalArchive.model.facades, null);
    assert.equal(verticalArchive.model.levels[0].openings.length, 8);
    await page.locator('#explore-count').selectOption('2');
    await page.locator('#explore-start').click();
    await page.waitForFunction(() => document.querySelector('#explore-status')?.textContent?.includes('Lote calculado'));
    assert.equal(await page.locator('.explore-card').count(), 3);
    assert.equal(await page.locator('.explore-plan').first().evaluate((image) => image.complete && image.naturalWidth > 0), true);
    await page.locator('#portfolio-name').fill('QA Zig navegador externo');
    await page.locator('#portfolio-create').click();
    await page.waitForFunction(() => document.querySelector('#portfolio-count')?.textContent?.startsWith('1 / 8'));
    assert.deepEqual(await page.evaluate(() => window.__qaCsp), [], 'No debe haber CSP violada antes de recargar.');
    await context.setOffline(true);
    await page.reload({ waitUntil: 'load' });
    await page.waitForFunction(() => document.querySelector('#portfolio-count')?.textContent?.startsWith('1 / 8'));
    await page.locator('#portfolio-list .portfolio-item button[aria-label^="Abrir y verificar"]').click();
    await page.waitForFunction(() => document.querySelector('#portfolio-status')?.textContent?.includes('abierto:'));
    assert.equal(await page.locator('#result-status').textContent(), 'VIABLES');
    await page.locator('#vertical-panel summary').click();
    assert.equal(await page.locator('#vertical-export').isEnabled(), false, 'Cotas no se guardan en cartera.');
    await page.locator('#vertical-file').setInputFiles({ name: 'hipotesis-offline.json',
      mimeType: 'application/json', buffer: verticalArchiveBytes });
    await page.waitForFunction(() => document.querySelector('#vertical-export')?.disabled === false);
    assert.equal(await page.locator('#vertical-model tbody tr').count(), 8);
    assert.deepEqual(await page.evaluate(() => window.__qaCsp), [], 'El shell no debe violar la CSP local.');
    assert.deepEqual(errors, [], 'No debe haber errores JS en Chromium/Linux.');
    console.log('Chromium/Linux: WASM v8/Z, Worker/CSP, SVG, SW offline, cartera e importación vertical: OK (NO QA Windows).');
    await context.close();
  } finally { await browser.close(); }
}

async function testLinuxServer(executable, assets) {
  const { child, baseUrl } = await startLinuxServer(executable);
  try {
    for (const asset of assets) {
      const response = await fetch(new URL(asset.path, baseUrl), { signal: AbortSignal.timeout(5_000) });
      assert.equal(response.status, 200, asset.path);
      assert.equal(response.headers.get('content-type'), asset.mime);
      assert.match(response.headers.get('content-security-policy'), /worker-src 'self'/);
      assert.equal(response.headers.get('access-control-allow-origin'), null);
      assert.equal(sha(Buffer.from(await response.arrayBuffer())), sha(asset.data), asset.path);
    }
    const rootPage = await fetch(baseUrl);
    assert.equal(rootPage.status, 200);
    assert.equal(sha(Buffer.from(await rootPage.arrayBuffer())), sha(assets.find((a) => a.path === '/index.html').data));
    const wasmHead = await fetch(new URL('/core.wasm', baseUrl), { method: 'HEAD' });
    assert.equal(wasmHead.status, 200);
    assert.equal(Number(wasmHead.headers.get('content-length')), assets.find((a) => a.path === '/core.wasm').data.length);
    assert.equal((await fetch(new URL('/%2e%2e%2fsecret', baseUrl))).status, 404);
    assert.equal((await fetch(new URL('/no-existe', baseUrl))).status, 404);
    assert.equal((await fetch(baseUrl, { method: 'POST' })).status, 405);
    assert.equal(await hostileHostRequest(baseUrl), 403);
    console.log(`Servidor equivalente Linux: ${assets.length} recursos idénticos, CSP, host y métodos comprobados.`);
    if (process.env.ARQGEN_CHROMIUM_PATH) await testBrowser(baseUrl);
    else console.log('Prueba Chromium/Linux opcional no ejecutada (define ARQGEN_CHROMIUM_PATH).');
  } finally {
    child.kill('SIGTERM');
    if (child.exitCode === null && child.signalCode === null) {
      let timer;
      await Promise.race([
        new Promise((done) => child.once('exit', done)),
        new Promise((done) => { timer = setTimeout(() => { child.kill('SIGKILL'); done(); }, 3_000); }),
      ]);
      clearTimeout(timer);
    }
  }
}

async function packageAlternative(temp, windowsExe) {
  const base = join(temp, 'package');
  const inside = join(base, folderName);
  await mkdir(inside, { recursive: true });
  const binary = await readFile(windowsExe);
  inspectWindowsGuiX64(binary); // PE32+ x64 GUI header; no claim of runtime QA
  const exeName = 'ARQ-GEN-Navegador.exe';
  await copyFile(windowsExe, join(inside, exeName));
  await writeFile(join(inside, 'SHA256SUMS.txt'), `${sha(binary)}  ${exeName}\n`);
  await writeFile(join(inside, 'LEEME-ANTES-DE-USAR.txt'), [
    `ARQ GEN ${version} - EXPERIMENTO WINDOWS EN NAVEGADOR EXTERNO`,
    'IMPORTANTE: NO ES TAURI, NO EMBEBE WEBVIEW2, NO ESTÁ PROBADO EN WINDOWS.',
    '',
    'Este EXE fue compilado cruzadamente desde Linux con Zig 0.13.0 (paquete npm de terceros).',
    'Incorpora web 0.22 y WASM Rust 0.17 recompilado y verificado ANTES de empaquetar.',
    'El script Zig no recompila Rust: comprueba SHA-256 y ejecución v8 + cotas Z declaradas.',
    'Las cotas Z son JSON separado e hipotético; las láminas A3 siguen SOLO 2D/sin Z.',
    'Al abrirlo reserva SOLO 127.0.0.1:48765, sirve recursos de una lista cerrada',
    'y abre el navegador predeterminado. Mantén abierta la pequeña ventana de control;',
    'Cerrar servidor apaga el proceso. Si el puerto está ocupado, no arranca.',
    'Sin navegador moderno/WebAssembly no funcionará. No incluye instalador ni firma.',
    'Los proyectos IndexedDB quedan en el perfil de ESE navegador, ligados al puerto 48765;',
    'descarga un respaldo JSON; cambiar/limpiar navegador o puerto puede perder acceso a ellos.',
    'El service worker puede requerir una segunda recarga al sustituir una versión anterior.',
    'La prueba automatizada solo cubrió el servidor equivalente en Linux y la cabecera PE;',
    'ejecuta y verifica este EXE en Windows antes de usarlo. No sustituye QA Tauri/WebView2.',
    '',
    'SOLO ANTEPROYECTO CONCEPTUAL. NO APTO PARA OBRA. Sin normas cubanas verificadas,',
    'sin caudal efectivo ni aprobación profesional. No pongas datos sensibles.',
    '',
    `SHA-256 del EXE: ${sha(binary)}`,
    `SHA-256 del WASM incorporado: ${wasmDigest}`,
    '',
  ].join('\r\n'), 'utf8');
  const outputDir = join(root, 'artifacts');
  await mkdir(outputDir, { recursive: true });
  const output = join(outputDir, zipName);
  const partial = `${output}.partial.zip`;
  await rm(partial, { force: true });
  try {
    command('zip', ['-q', '-X', '-r', partial, folderName], { cwd: base });
    const extracted = join(temp, 'unpacked');
    await mkdir(extracted);
    command('unzip', ['-q', partial, '-d', extracted]);
    assert.equal(sha(await readFile(join(extracted, folderName, exeName))), sha(binary));
    await rm(output, { force: true });
    await copyFile(partial, output);
    console.log(`ZIP EXE ALTERNATIVO (NO TAURI): ${output}\nSHA-256 EXE: ${sha(binary)}\nSHA-256 ZIP: ${sha(await readFile(output))}`);
    return output;
  } finally { await rm(partial, { force: true }); }
}

async function build() {
  if (process.platform !== 'linux') throw new Error('Esta ruta experimental se preparó solo para host Linux.');
  if (!existsSync(zig)) throw new Error('Falta Zig 0.13.0. Instala @ryoppippi/zig-linux-x64@0.13.0 en /tmp/arqgen-zig o define ARQGEN_ZIG.');
  command(zig, ['version']);
  command('npm', ['ci', '--prefix', 'web', '--no-audit', '--no-fund']);
  // Build ONLY the frontend; npm run build would recompile Rust, unavailable.
  command(process.execPath, ['node_modules/vite/bin/vite.js', 'build'], { cwd: web });
  command(process.execPath, ['../scripts/write-offline.mjs'], { cwd: web });
  const assets = await getAssets();
  const temp = await mkdtemp(join(tmpdir(), 'arqgen-zig-browser-'));
  try {
    await writeAssetsHeader(temp, assets);
    const linux = join(temp, 'arqgen-local-linux-smoke');
    command('gcc', ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-I', temp, source, '-o', linux], { cwd: temp });
    await testLinuxServer(linux, assets);
    const windows = join(temp, 'ARQ-GEN-Navegador.exe');
    command(zig, ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
      '-target', 'x86_64-windows-gnu', '-Wl,--subsystem,windows', '-I', temp,
      source, '-o', windows, '-lws2_32', '-lshell32', '-luser32'],
    { cwd: temp, timeout: 180_000, env: {
      ...process.env, ZIG_LOCAL_CACHE_DIR: join(temp, 'zig-cache'),
      ZIG_GLOBAL_CACHE_DIR: join(tmpdir(), 'arqgen-zig-cache'),
    } });
    assert.ok((await stat(windows)).size > 64 * 1024);
    return await packageAlternative(temp, windows);
  } finally { await rm(temp, { recursive: true, force: true }); }
}

build().catch((error) => { console.error(`FALLÓ la recompilación del EXE alternativo; no se validaron artefactos anteriores: ${error.stack || error.message}`); process.exitCode = 1; });

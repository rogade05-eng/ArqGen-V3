// Linux can validate the W3C transport, but NEVER mark the Windows/WebView2
// scenario itself as passed. That scenario is a separate Windows-only command.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawnSync } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { NativeWebDriver } from './native/webdriver.mjs';
import { buildArchives } from './webview2.native.mjs';
import { callCore } from '../src/core-client.js';
import { verifyExplorationArchive } from '../src/exploration.js';
import { verifyVerticalArchive } from '../src/vertical.js';

test('native QA transport requires loopback, W3C session, native element actions and explicit teardown', async () => {
  assert.throws(() => new NativeWebDriver('https://example.com'), /localhost/);
  assert.throws(() => new NativeWebDriver('http://0.0.0.0:4444'), /localhost/);
  const calls = [];
  const server = createServer(async (req, res) => {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    const json = raw ? JSON.parse(raw) : undefined;
    calls.push({ method: req.method, path: req.url, json });
    res.setHeader('content-type', 'application/json');
    if (req.url === '/status') res.end(JSON.stringify({ value: { ready: true } }));
    else if (req.url === '/session') res.end(JSON.stringify({ value: { sessionId: 'native-1', capabilities: {} } }));
    else if (req.url?.endsWith('/element')) res.end(JSON.stringify({ value: { 'element-6066-11e4-a52e-4f735466cecf': 'button-1' } }));
    else if (req.url?.endsWith('/execute/sync')) res.end(JSON.stringify({ value: 'tauri.localhost' }));
    else if (req.url?.endsWith('/screenshot')) res.end(JSON.stringify({ value: 'YWJj' }));
    else res.end(JSON.stringify({ value: null }));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    const driver = new NativeWebDriver(`http://127.0.0.1:${server.address().port}`);
    assert.equal((await driver.command('GET', '/status')).ready, true);
    await driver.open('C:\\test\\arqgen-desktop.exe');
    assert.equal(await driver.execute('return location.host'), 'tauri.localhost');
    await driver.click('#explore-start');
    await driver.sendFile('#explore-file', 'C:\\temp\\archivo.json');
    assert.equal(await driver.screenshot(), 'YWJj');
    await driver.refresh();
    await driver.close();
    assert.throws(() => driver.route('/refresh'), /No hay sesión WebView2/);
    assert.deepEqual(calls.map(({ method, path }) => `${method} ${path}`), [
      'GET /status', 'POST /session', 'POST /session/native-1/execute/sync',
      'POST /session/native-1/element', 'POST /session/native-1/element/button-1/click',
      'POST /session/native-1/element', 'POST /session/native-1/element/button-1/value',
      'GET /session/native-1/screenshot', 'POST /session/native-1/refresh', 'DELETE /session/native-1',
    ]);
    assert.equal(calls[1].json.capabilities.alwaysMatch.browserName, 'wry');
    assert.equal(calls[1].json.capabilities.alwaysMatch['tauri:options'].application, 'C:\\test\\arqgen-desktop.exe');
    assert.equal(calls[6].json.text, 'C:\\temp\\archivo.json');
  } finally { await new Promise((resolve) => server.close(resolve)); }
});

test('native QA fixture uses real WASM and fails closed on a forged SVG', async () => {
  const wasmPath = fileURLToPath(new URL('../public/core.wasm', import.meta.url));
  const dir = await mkdtemp(join(tmpdir(), 'arqgen-qa-fixture-'));
  try {
    // A local fixture test can reuse public WASM as "bundle". The real
    // Windows invocation instead *requires* dist/web/core.wasm from Tauri build.
    const { valid, forged, verticalValid, verticalForged } = await buildArchives(dir, wasmPath);
    const [good, bad, goodZ, badZ, knowledge, bytes] = await Promise.all([
      readFile(valid, 'utf8').then(JSON.parse),
      readFile(forged, 'utf8').then(JSON.parse),
      readFile(verticalValid, 'utf8').then(JSON.parse),
      readFile(verticalForged, 'utf8').then(JSON.parse),
      readFile(fileURLToPath(new URL('../../knowledge/generic-house.json', import.meta.url)), 'utf8').then(JSON.parse),
      readFile(wasmPath),
    ]);
    const { instance } = await WebAssembly.instantiate(bytes);
    const replay = (input, seed_count) => callCore(instance.exports, 'arq_explore', { input, seed_count });
    assert.equal(verifyExplorationArchive(good, knowledge, replay).result.generated, 96);
    assert.throws(() => verifyExplorationArchive(bad, knowledge, replay), /no coincide íntegramente/);
    const vertical = (request) => callCore(instance.exports, 'arq_vertical', request);
    assert.equal(verifyVerticalArchive(goodZ, knowledge, vertical).model.levels[0].openings.length, 8);
    assert.throws(() => verifyVerticalArchive(badZ, knowledge, vertical), /difiere del replay íntegro/);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('native QA explicitly fails instead of running Chromium on non-Windows',
  { skip: process.platform === 'win32' }, () => {
    const run = spawnSync(process.execPath, [new URL('./webview2.native.mjs', import.meta.url).pathname],
      { encoding: 'utf8' });
    assert.equal(run.status, 1);
    assert.match(run.stderr, /NO EJECUTADO.*Windows real.*Chromium\/Linux no cuenta/);
  });

test('native QA transport rejects WebDriver error responses, never turning a driver failure into pass', async () => {
  const server = createServer((req, res) => {
    res.statusCode = 500;
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ value: { error: 'session not created', message: 'WebView2 failed to start' } }));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    const driver = new NativeWebDriver(`http://127.0.0.1:${server.address().port}`);
    await assert.rejects(driver.open('C:\\test\\arqgen-desktop.exe'), /WebView2 failed to start/);
    assert.equal(driver.sessionId, null);
  } finally { await new Promise((resolve) => server.close(resolve)); }
});

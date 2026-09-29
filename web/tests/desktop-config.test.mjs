import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir, stat } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const tauri = resolve(fileURLToPath(new URL('../src-tauri/', import.meta.url)));
const config = JSON.parse(await readFile(resolve(tauri, 'tauri.conf.json'), 'utf8'));
const pkg = JSON.parse(await readFile(resolve(tauri, '../package.json'), 'utf8'));

test('desktop shell bundles this same offline web app with no granted native IPC', async () => {
  assert.equal(config.version, pkg.version);
  assert.equal(config.build.frontendDist, '../../dist/web');
  assert.equal(config.build.beforeBuildCommand, 'npm run build');
  assert.equal(config.build.devUrl, 'http://localhost:5173');
  assert.deepEqual(config.app.security.capabilities, []);
  // With an empty capabilities config, Tauri would auto-include capability
  // files if somebody added them later. Guard that directory as well.
  const capabilities = await readdir(resolve(tauri, 'capabilities')).catch((error) => {
    if (error.code === 'ENOENT') return [];
    throw error;
  });
  assert.deepEqual(capabilities, []);
  assert.equal(config.app.withGlobalTauri, false);
  assert.match(config.app.security.csp, /wasm-unsafe-eval/);
  assert.doesNotMatch(config.app.security.csp, /'unsafe-eval'/);
  assert.deepEqual(config.bundle.targets, ['nsis']);
  assert.equal(config.bundle.windows.webviewInstallMode.type, 'offlineInstaller');
  assert.ok((await stat(resolve(tauri, 'icons/icon.ico'))).size > 0);
  const main = await readFile(resolve(tauri, 'src/main.rs'), 'utf8');
  assert.doesNotMatch(main, /invoke_handler|\.plugin\(/);
  assert.match(main, /tauri::Builder::default\(\)/);
});

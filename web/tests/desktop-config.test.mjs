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

test('el icono del shell puede decodificarse con tauri-codegen (PNG de 8 bits)', async () => {
  // El runner Windows falló con «Unsupported PNG bit depth: Sixteen» dentro de
  // `generate_context!`: los PNG incrustados en el ICO deben ser de 8 bits.
  const ico = await readFile(resolve(tauri, 'icons/icon.ico'));
  assert.equal(ico.readUInt16LE(0), 0);
  assert.equal(ico.readUInt16LE(2), 1);
  const count = ico.readUInt16LE(4);
  assert.ok(count >= 1, 'El ICO debe contener al menos una imagen.');
  for (let i = 0; i < count; i += 1) {
    const entry = 6 + i * 16;
    const size = ico.readUInt32LE(entry + 8);
    const start = ico.readUInt32LE(entry + 12);
    const data = ico.subarray(start, start + size);
    assert.equal(data.length, size, 'La entrada del ICO está completa.');
    if (data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) {
      assert.equal(data[24], 8, 'El PNG incrustado debe tener 8 bits por canal.');
    } else {
      assert.equal(data.readUInt32LE(0), 40, 'Las entradas sin PNG son mapas de bits de Windows.');
    }
  }
  const png = await readFile(resolve(tauri, 'icons/icon.png'));
  assert.equal(png[24], 8, 'icon.png también debe ser de 8 bits por canal.');
});

test('el shell fija las versiones transitivas probadas por Tauri 2.11.5', async () => {
  // Sin Cargo.lock versionado, una resolución nueva elige versiones
  // incompatibles y el build de Windows falla. Estas son las versiones del
  // árbol probado por el repositorio de Tauri en tauri-v2.11.5.
  const manifest = await readFile(resolve(tauri, 'Cargo.toml'), 'utf8');
  const expected = {
    tauri: '2.11.5',
    'tauri-build': '2.6.3',
    muda: '0.19.1',
    tao: '0.35.0',
    wry: '0.55.0',
    'tauri-runtime': '2.11.3',
    'tauri-runtime-wry': '2.11.4',
    'tauri-macros': '2.6.3',
    'tauri-utils': '2.9.3',
  };
  for (const [name, version] of Object.entries(expected)) {
    assert.match(manifest, new RegExp(`^${name} = \\{ version = "=${version.replace(/\./g, '\\.')}"`,
      'm'), `Falta el pin exacto de ${name} en Cargo.toml`);
  }
});

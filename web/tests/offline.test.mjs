import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { writeOfflineAssets } from '../../scripts/write-offline.mjs';

test('offline shell is versioned by bytes and pre-caches only HTML, CSS, JS and WASM', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'arqgen-offline-'));
  try {
    await mkdir(join(directory, 'assets'));
    await writeFile(join(directory, 'index.html'), '<html>app</html>');
    await writeFile(join(directory, 'core.wasm'), Buffer.from([0, 97, 115, 109]));
    await writeFile(join(directory, 'assets/index-1.js'), 'app();');
    await writeFile(join(directory, 'assets/index-1.css'), 'body {}');
    await writeFile(join(directory, 'assets/notes.json'), '{"project":"private"}');
    await writeFile(join(directory, 'project.json'), '{"project":"private"}');

    const first = await writeOfflineAssets(directory);
    assert.deepEqual(first.assets, [
      './index.html', './core.wasm', './assets/index-1.css', './assets/index-1.js',
    ]);
    const script = await readFile(join(directory, 'sw.js'), 'utf8');
    assert.match(script, new RegExp(`arqgen-shell-${first.version}`));
    assert.match(script, /cache\.addAll\(ASSETS\.map/);
    assert.match(script, /if \(!ASSETS\.includes\(asset\)\) return;/);
    assert.doesNotMatch(script, /notes\.json|project\.json/);
    assert.deepEqual(await writeOfflineAssets(directory), first);

    await writeFile(join(directory, 'core.wasm'), Buffer.from([0, 97, 115, 110]));
    assert.notEqual((await writeOfflineAssets(directory)).version, first.version);
    await writeFile(join(directory, 'index.html'), '<html>changed</html>');
    assert.notEqual((await writeOfflineAssets(directory)).version, first.version);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

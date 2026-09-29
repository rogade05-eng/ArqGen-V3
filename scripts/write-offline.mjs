// After `vite build`, pre-cache only the built application shell and Rust WASM.
// No projects, imported documents, or arbitrary HTTP responses enter CacheStorage.
import { createHash } from 'node:crypto';
import { readFile, readdir, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = resolve(root, 'dist/web');

export async function writeOfflineAssets(directory) {
  const names = (await readdir(join(directory, 'assets')))
    .filter((name) => /\.(?:js|css)$/.test(name)).sort();
  if (!names.length) throw new Error('Faltan los assets compilados de Vite.');
  const files = ['index.html', 'core.wasm', ...names.map((name) => `assets/${name}`)];
  const hash = createHash('sha256');
  for (const name of files) {
    hash.update(name);
    hash.update(await readFile(join(directory, name)));
  }
  const version = hash.digest('hex').slice(0, 16);
  const assets = files.map((name) => `./${name}`);
  const content = `// Generated from the static build. No project data is cached.
const CACHE = 'arqgen-shell-${version}';
const ASSETS = ${JSON.stringify(assets)};
self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(ASSETS.map((path) => new URL(path, self.registration.scope)));
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith('arqgen-shell-') && name !== CACHE)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET' || !request.url.startsWith(self.registration.scope)) return;
  const relative = './' + request.url.slice(self.registration.scope.length).split(/[?#]/)[0];
  const asset = request.mode === 'navigate' ? './index.html' : relative;
  if (!ASSETS.includes(asset)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    return await cache.match(new URL(asset, self.registration.scope)) || fetch(request);
  })());
});
`;
  await writeFile(join(directory, 'sw.js'), content, 'utf8');
  return { version, assets };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { version, assets } = await writeOfflineAssets(output);
  console.log(`Shell offline ${version}: ${assets.length} archivos de aplicación precargados.`);
}

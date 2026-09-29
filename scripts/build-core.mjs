import { spawnSync } from 'node:child_process';
import { chmodSync, copyFileSync, mkdirSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const compiled = spawnSync('cargo', ['build', '--release', '--offline', '--locked', '--target', 'wasm32-unknown-unknown', '-p', 'arqgen-core'], {
  cwd: root, stdio: 'inherit', env: process.env,
});
if (compiled.error) {
  console.error('Cargo no disponible. Instala Rust y el target wasm32-unknown-unknown (rustup target add wasm32-unknown-unknown).');
  process.exit(1);
}
if (compiled.status !== 0) process.exit(compiled.status || 1);
// Match Cargo's output directory, including isolated QA environments that
// set CARGO_TARGET_DIR instead of writing build products into the checkout.
const target = resolve(root, process.env.CARGO_TARGET_DIR || 'target');
const from = resolve(target, 'wasm32-unknown-unknown/release/arqgen_core.wasm');
const to = resolve(root, 'web/public/core.wasm');
mkdirSync(dirname(to), { recursive: true });
copyFileSync(from, to);
// Cargo's WASM output can carry an executable mode. Distribute as a read-only asset.
chmodSync(to, 0o644);
console.log(`Núcleo WASM: ${to} (${(statSync(to).size / 1024).toFixed(0)} KiB)`);

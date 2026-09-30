#!/usr/bin/env node
// Regenerate the *illustrative* drawing-package fixture from the versioned
// Rust WASM; no sample image is adopted as geometry, and Rust is not rebuilt.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { callCore } from '../web/src/core-client.js';
import { buildDrawingPackage } from '../web/src/drawing-package.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const wasm = await readFile(join(root, 'web/public/core.wasm'));
const sha = createHash('sha256').update(wasm).digest('hex');
assert.equal(sha, 'fe95bb201e1bcb92574e09bc196670062fdc75da3b13502f7e2cb56dc6ba0874',
  'El fixture requiere el WASM Rust v8 versionado; reconstruir/revalidar antes de regenerarlo.');
const input = JSON.parse(await readFile(join(root, 'examples/rectangular.json'), 'utf8'));
input.rules = JSON.parse(await readFile(join(root, 'knowledge/generic-house.json'), 'utf8'));
const { instance } = await WebAssembly.instantiate(wasm);
const generation = callCore(instance.exports, 'arq_generate', input);
assert.equal(generation.status, 'ok');
const pkg = buildDrawingPackage(input, generation, 0);
const directory = join(root, 'examples/laminas-conceptuales');
await mkdir(directory, { recursive: true });
await writeFile(join(directory, 'muestra-vivienda-A3.zip'), pkg.bytes);
for (const sheet of pkg.sheets) await writeFile(join(directory, sheet.filename), sheet.svg, 'utf8');
await writeFile(join(directory, 'nivel-0-2d.json'), JSON.stringify(pkg.envelope, null, 2), 'utf8');
console.log(`Cuatro SVG A3 + modelo 2D + ZIP de vivienda CONCEPTUAL; seed ${input.seed}, candidato ${pkg.manifest.candidate_id}, SHA-256 ZIP ${createHash('sha256').update(pkg.bytes).digest('hex')}`);

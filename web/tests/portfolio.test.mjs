import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { indexedDB, IDBObjectStore } from 'fake-indexeddb';
import { portfolioFormat, portfolioLimit, maxPortfolioBytes, projectName, newProject,
  revisedProject, exportPortfolio, verifyPortfolio, parsePortfolioText, listProjects,
  readProject, saveProject, deleteProject, replacePortfolio } from '../src/portfolio.js';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const { instance } = await WebAssembly.instantiate(await readFile(resolve(root, 'web/public/core.wasm')));
const core = instance.exports;
const example = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const demo = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
const request = () => ({ ...structuredClone(example), rules: structuredClone(demo) });
const testDate = '2026-09-26T08:15:00.000Z';
const id = (index) => `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`;

function generate(input) {
  const bytes = new TextEncoder().encode(JSON.stringify(input));
  const pointer = core.arq_alloc(bytes.length);
  assert.ok(pointer);
  new Uint8Array(core.memory.buffer, pointer, bytes.length).set(bytes);
  let packed;
  try { packed = core.arq_generate(pointer, bytes.length); }
  finally { core.arq_free(pointer, bytes.length); }
  const ptr = Number(packed & 0xffffffffn);
  const length = Number(packed >> 32n);
  let text;
  try { text = new TextDecoder().decode(new Uint8Array(core.memory.buffer, ptr, length)); }
  finally { core.arq_free(ptr, length); }
  return JSON.parse(text);
}
function job(index, name = `Proyecto ${index}`) {
  const input = request();
  input.seed = index + 40;
  if (index % 2) {
    input.site.plot_outline = { provenance: 'user_sketch_unverified',
      shape: 'rear_both_corners_notched', rear_notches: [
        { side: 'left', width: 4, depth: 10 }, { side: 'right', width: 3, depth: 10 },
      ] };
    input.site.reserved_areas = [
      { x: 4.5, y: 12, width: 2, depth: 2 }, { x: 14, y: 16, width: 1, depth: 2 },
    ];
  }
  const evaluated = { input, generation: generate(input) };
  assert.equal(evaluated.generation.status, 'ok');
  return newProject(name, evaluated, [evaluated], {
    id: id(index), edit_token: id(index + 100), updated_at: testDate,
  });
}
const eraseDatabase = () => new Promise((resolve, reject) => {
  const open = indexedDB.deleteDatabase('arqgen-portfolio-v1');
  open.onsuccess = resolve;
  open.onerror = () => reject(open.error);
});

test('portfolio backup replays every project independently and never promotes sketch to survey', () => {
  const entries = [job(1, '<svg onload=alert(1)>'), job(2)];
  let calls = 0;
  const backup = exportPortfolio(entries, demo, (input) => { calls++; return generate(input); }, testDate);
  assert.equal(calls, 4, 'One focus and one comparison run per project are replayed.');
  assert.equal(backup.format, portfolioFormat);
  assert.equal(backup.engine_version, entries[0].snapshot.engine_version);
  assert.equal(backup.entries.length, 2);
  assert.equal(backup.entries[0].name, '<svg onload=alert(1)>'); // UI uses textContent.
  const restored = verifyPortfolio(parsePortfolioText(JSON.stringify(backup)), demo, generate);
  assert.deepEqual(restored, entries);
  assert.equal(restored[0].snapshot.focus.generation.site.plot_area, 326);
  assert.equal(restored[0].snapshot.focus.generation.site.unreserved_buildable_area, 208);
  assert.equal(restored[0].snapshot.focus.generation.applicability.status, 'not_evaluated');
});

test('unknown format, forged result in any entry, changed rules/geometry and duplicate IDs fail closed', () => {
  const original = exportPortfolio([job(1), job(2)], demo, generate, testDate);
  const altered = (fn) => { const file = structuredClone(original); fn(file); return file; };
  const forgery = altered((file) => { file.entries[1].snapshot.scenarios[0].generation.alternatives[0].svg += '<script/>'; });
  assert.throws(() => verifyPortfolio(forgery, demo, generate), /difiere/);
  const hidden = altered((file) => { file.entries[1].snapshot.focus.input.site.plot_outline.rear_notches = [{ side: 'left', width: 2, depth: 3 }]; });
  assert.throws(() => verifyPortfolio(hidden, demo, generate));
  const inventedRule = altered((file) => { file.entries[1].snapshot.focus.input.rules.id = 'NC-598-official'; });
  assert.throws(() => verifyPortfolio(inventedRule, demo, generate), /Reglas incompatibles/);
  assert.throws(() => verifyPortfolio(altered((file) => { file.entries[1].id = file.entries[0].id; }), demo, generate), /repite/);
  assert.throws(() => verifyPortfolio(altered((file) => { file.entries[0].snapshot.focus.selection = { kind: 'approved' }; }), demo, generate), /estructura/);
  assert.throws(() => verifyPortfolio(altered((file) => { file.entries[1].snapshot.format = 'arqgen-local-workspace-v7'; }), demo, generate), /antiguo|anterior/);
  assert.throws(() => verifyPortfolio(altered((file) => { file.entries[1].name += '\nclaim'; }), demo, generate), /nombre/);
  assert.throws(() => verifyPortfolio(altered((file) => { file.entries[0].extra_claim = 'legal'; }), demo, generate), /metadatos/);
  assert.throws(() => verifyPortfolio(altered((file) => { file.engine_version = 'authoritative'; }), demo, generate), /versión/);
  assert.throws(() => verifyPortfolio(altered((file) => { file.format = 'arqgen-illustrative-portfolio-v0'; }), demo, generate), /desconocido/);
  assert.throws(() => verifyPortfolio(altered((file) => { file.exported_at = 'yesterday'; }), demo, generate), /desconocido/);
  assert.throws(() => verifyPortfolio(altered((file) => { file.entries = Array(portfolioLimit + 1).fill(file.entries[0]); }), demo, generate), /admite/);
  assert.throws(() => parsePortfolioText('x'.repeat(maxPortfolioBytes + 1)), /16 MiB/);
  assert.throws(() => parsePortfolioText('{'), /JSON válido/);
  assert.throws(() => projectName(' \t'), /nombre/);
  assert.throws(() => projectName('x'.repeat(81)), /nombre/);
});

test('IndexedDB writes are explicit, bounded, atomic and compare edit tokens across tabs', async () => {
  globalThis.indexedDB = indexedDB;
  await eraseDatabase();
  try {
    const first = job(1);
    const second = job(2);
    assert.deepEqual(await listProjects(), []);
    await saveProject(first);
    await saveProject(second);
    assert.equal((await listProjects()).length, 2);
    assert.deepEqual(await readProject(first.id), first);
    await assert.rejects(() => saveProject(first), /Conflicto/);
    const a = revisedProject(first, 'Casa patio', { input: first.snapshot.focus.input,
      generation: first.snapshot.focus.generation }, first.snapshot.scenarios, { edit_token: id(1011), updated_at: '2026-09-26T08:15:01.000Z' });
    await saveProject(a, first.edit_token);
    assert.equal((await readProject(first.id)).name, 'Casa patio');
    await assert.rejects(() => saveProject(revisedProject(first, 'Copia obsoleta',
      { input: first.snapshot.focus.input, generation: first.snapshot.focus.generation }, [],
      { edit_token: id(1012) }), first.edit_token), /Conflicto/);
    await assert.rejects(() => deleteProject(first.id, first.edit_token), /Conflicto/);
    const backup = exportPortfolio(await listProjects(), demo, generate, testDate);
    const tampered = structuredClone(backup);
    tampered.entries[1].snapshot.focus.generation.site.plot_area += 1;
    assert.throws(() => replacePortfolio(tampered, demo, generate), /difiere/);
    assert.deepEqual(await readProject(first.id), a, 'No project was replaced by a failed import.');
    assert.equal((await listProjects()).length, 2);
    // Simulate a quota/I/O failure AFTER clear() and the first add(). The
    // readwrite transaction must roll back the whole replacement.
    const originalAdd = IDBObjectStore.prototype.add;
    let additions = 0;
    IDBObjectStore.prototype.add = function (...args) {
      if (++additions === 2) throw new Error('fallo de cuota simulado');
      return originalAdd.apply(this, args);
    };
    try { await assert.rejects(() => replacePortfolio(backup, demo, generate), /fallo de cuota/); }
    finally { IDBObjectStore.prototype.add = originalAdd; }
    assert.deepEqual(await readProject(first.id), a, 'Atomic import cannot erase the old portfolio on mid-transaction failure.');
    assert.equal((await listProjects()).length, 2);
    const imported = await replacePortfolio(backup, demo, generate);
    assert.equal(imported.length, 2);
    assert.equal((await readProject(first.id)).snapshot.focus.generation.input_hash, a.snapshot.focus.generation.input_hash);
    await assert.rejects(() => saveProject(revisedProject(a, 'Otra pestaña',
      { input: a.snapshot.focus.input, generation: a.snapshot.focus.generation }, [],
      { edit_token: id(1013) }), a.edit_token), /Conflicto/);
    const newToken = (await readProject(first.id)).edit_token;
    await deleteProject(first.id, newToken);
    assert.equal(await readProject(first.id), null);
    assert.equal((await listProjects()).length, 1);
  } finally { delete globalThis.indexedDB; }
});

test('8-project limit and concurrent creation with the same ID never silently overwrites', async () => {
  globalThis.indexedDB = indexedDB;
  await eraseDatabase();
  try {
    const jobs = Array.from({ length: portfolioLimit }, (_, i) => job(i + 1));
    const [created, conflicted] = await Promise.allSettled([saveProject(jobs[0]), saveProject({ ...jobs[0], edit_token: id(999) })]);
    assert.equal(created.status, 'fulfilled');
    assert.equal(conflicted.status, 'rejected');
    for (const entry of jobs.slice(1)) await saveProject(entry);
    assert.equal((await listProjects()).length, portfolioLimit);
    await assert.rejects(() => saveProject(job(99)), /admite/);
    assert.equal((await listProjects()).length, portfolioLimit);
  } finally { delete globalThis.indexedDB; }
});

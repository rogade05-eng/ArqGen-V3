import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { callCore } from '../src/core-client.js';
import { explorationLimit, explorationFormat, makeExplorationArchive, verifyExplorationArchive } from '../src/exploration.js';
import { sameJson } from '../src/archive.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const wasm = (await WebAssembly.instantiate(await readFile(resolve(root, 'web/public/core.wasm')))).instance.exports;
const input = { ...JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8')),
  rules: JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8')) };
const explore = (brief, count) => callCore(wasm, 'arq_explore', { input: brief, seed_count: count });
const generate = (brief) => callCore(wasm, 'arq_generate', brief);
function rawExplore(brief, count) {
  const bytes = new TextEncoder().encode(JSON.stringify({ input: brief, seed_count: count }));
  const ptr = wasm.arq_alloc(bytes.length);
  assert.ok(ptr);
  new Uint8Array(wasm.memory.buffer, ptr, bytes.length).set(bytes);
  let packed;
  try { packed = wasm.arq_explore(ptr, bytes.length); } finally { wasm.arq_free(ptr, bytes.length); }
  const outPtr = Number(packed & 0xffffffffn);
  const outSize = Number(packed >> 32n);
  let response;
  try { response = new TextDecoder().decode(new Uint8Array(wasm.memory.buffer, outPtr, outSize)); }
  finally { wasm.arq_free(outPtr, outSize); }
  return response;
}

test('WASM/CLI-bound Rust scans all candidates across seeds without changing single-run semantics', () => {
  const original = generate(input);
  assert.equal(original.status, 'ok');
  const batch = explore(input, 2);
  assert.equal(batch.status, 'ok');
  assert.equal(batch.seed_count, 2);
  assert.equal(batch.generated, 96);
  assert.equal(batch.valid + batch.rejected, batch.generated);
  assert.equal(batch.rejection_summary.reduce((sum, row) => sum + row.count, 0), batch.rejected);
  assert.equal(batch.seed_runs.length, 2);
  assert.equal(batch.seed_runs[0].input_hash, original.input_hash);
  assert.deepEqual(batch.seed_runs.map(({ seed }) => seed), [42, 43]);
  assert.equal(batch.exploration_method, 'bounded-seed-sweep-v1');
  assert.deepEqual(batch.objectives, [
    'area_fit', 'circulation_score', 'privacy_score', 'service_score', 'east_bedroom_score',
  ]);
  assert.ok(batch.pareto_front_size > 0);
  assert.ok(batch.alternatives.length >= 1 && batch.alternatives.length <= 3);
  const shown = new Set(batch.seed_runs.flatMap(({ seed }) =>
    generate({ ...input, seed }).alternatives.map(({ id }) => id)));
  assert.ok(batch.alternatives.some(({ candidate }) => !shown.has(candidate.id)),
    'The batch truly ranks all validated variants, not just the top three of each seed.');
  for (const { seed, candidate } of batch.alternatives) {
    assert.ok([42, 43].includes(seed));
    assert.equal(candidate.bathroom_ventilation_status, 'not_evaluated');
    assert.match(candidate.svg, /NO APTO PARA OBRA/);
    assert.ok(candidate.id.includes(batch.seed_runs[seed - 42].input_hash));
  }
  assert.ok(sameJson(original, generate(input)), 'The old v8 single-run replay remains identical.');
  assert.deepEqual(batch, explore(input, 2));
});

test('old v8 runs are byte-equivalent after the Rust scan refactor; CLI and WASM batches agree', async () => {
  // SHA-256 of JSON.stringify(parsed WASM outputs captured before this release.
  // A single-run protocol change must use a NEW engine_version, not silently
  // invalidate a saved v8 project under the same version string.
  for (const [seed, expected] of [
    [0, 'ae9240e016d8f9a5c547adc064ab910ed8831a297619b32eadc6e6b6ade02a59'],
    [42, '4b9d1650f5dcbc11ec6080ccb90f6fd19a77d4870e56feddbf904ef5c30d0c38'],
    [43, '7a363cfcc16091e39e7e942042018b22cd0fb611a929dc57ed5d3960d2f1a739'],
    [4294967295, 'e136562c39cf11c97628a14d2e0e5d337f89049aa772077d4877a429b746ab32'],
  ]) {
    const current = generate({ ...input, seed });
    assert.equal(current.engine_version, 'mvp0.18-rust-0.15.0');
    assert.equal(createHash('sha256').update(JSON.stringify(current)).digest('hex'), expected);
  }
  const dir = await mkdtemp(resolve(tmpdir(), 'arqgen-explore-parity-'));
  try {
    const brief = resolve(dir, 'brief.json');
    const { rules: _, ...withoutRules } = input;
    await writeFile(brief, JSON.stringify(withoutRules));
    const run = spawnSync('cargo', ['run', '--offline', '--locked', '--quiet', '-p', 'arqgen-core',
      '--bin', 'arqgen-explore', '--', brief, '--rules', resolve(root, 'knowledge/generic-house.json'), '--count', '4'],
    { cwd: root, encoding: 'utf8' });
    assert.equal(run.status, 0, run.stderr || String(run.error));
    assert.equal(run.stdout.trimEnd(), rawExplore(input, 4), 'CLI/WASM batch JSON is byte-identical.');
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('bounds, wrap, infeasible scans and malformed envelopes fail closed', () => {
  const rolled = explore({ ...input, seed: 4294967295 }, explorationLimit);
  assert.deepEqual(rolled.seed_runs.slice(0, 3).map(({ seed }) => seed), [4294967295, 0, 1]);
  assert.equal(rolled.generated, 576);
  const noPlan = explore({ ...input, site: { ...input.site, width: 4 } }, 2);
  assert.equal(noPlan.status, 'infeasible');
  assert.equal(noPlan.generated, 0);
  assert.equal(noPlan.pareto_front_size, 0);
  assert.deepEqual(noPlan.alternatives, []);
  assert.ok(noPlan.reasons.length > 0);
  for (const count of [0, 1, 13, 2.5, '8', null]) assert.equal(explore(input, count).status, 'error');
  assert.equal(callCore(wasm, 'arq_explore', { input, seed_count: 2, legal_claim: true }).status, 'error');
  assert.equal(explore({ ...input, request_schema: 'arqgen-brief-v7' }, 2).status, 'error');
});

test('exploration JSON is opt-in, bounded, and replayed atomically before adoption', () => {
  const result = explore(input, 4);
  const archive = makeExplorationArchive(input, 4, result);
  assert.equal(archive.format, explorationFormat);
  let calls = 0;
  const replay = (brief, count) => { calls++; return explore(brief, count); };
  const verified = verifyExplorationArchive(JSON.parse(JSON.stringify(archive)), input.rules, replay);
  assert.equal(calls, 1, 'All seeds replay in one bounded Rust call.');
  assert.deepEqual(verified, { input, seed_count: 4, result });
  assert.notEqual(verified.result, archive.exploration, 'Never return the archived SVG/claims.');

  for (const change of [
    (doc) => { doc.exploration.alternatives[0].candidate.svg += '<script>bad</script>'; },
    (doc) => { doc.exploration.rejection_summary.push({ reason: 'falso', count: 1 }); },
    (doc) => { doc.exploration.seed_runs[2].input_hash = 'falsificado'; },
    (doc) => { doc.exploration.pareto_front_size++; },
    (doc) => { doc.exploration.alternatives[0].seed++; },
    (doc) => { doc.exploration.engine_version = 'otro'; },
  ]) {
    const bad = structuredClone(archive);
    change(bad);
    assert.throws(() => verifyExplorationArchive(bad, input.rules, replay), /no coincide íntegramente/);
  }
  const afterReplays = calls;
  for (const change of [
    (doc) => { doc.seed_count = 13; },
    (doc) => { doc.seed_count = 2.5; },
    (doc) => { doc.format = 'arqgen-illustrative-seed-exploration-v0'; },
    (doc) => { doc.extra = 'falso'; },
    (doc) => { doc.input.rules.setbacks.front += 1; },
    (doc) => { doc.input.request_schema = 'arqgen-brief-v7'; },
  ]) {
    const bad = structuredClone(archive);
    change(bad);
    assert.throws(() => verifyExplorationArchive(bad, input.rules, replay));
  }
  assert.equal(calls, afterReplays, 'Invalid schema or fixed rules never trigger a costly replay.');
  const huge = structuredClone(archive);
  huge.exploration.notice += 'x'.repeat(8 * 1024 * 1024);
  assert.throws(() => verifyExplorationArchive(huge, input.rules, replay), /8 MiB/);
  assert.throws(() => makeExplorationArchive(input, 13, result), /válida/);
});

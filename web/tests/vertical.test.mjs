import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { callCore } from '../src/core-client.js';
import { makeVerticalRequest, makeVerticalArchive, verifyVerticalArchive,
  verticalArchiveFormat, verticalModelFormat } from '../src/vertical.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const { instance } = await WebAssembly.instantiate(readFileSync(resolve(root, 'web/public/core.wasm')));
const wasm = instance.exports;
const example = JSON.parse(readFileSync(resolve(root, 'examples/declared-vertical-v1-request.json')));
const modelFixture = JSON.parse(readFileSync(resolve(root, 'examples/declared-vertical-v1-model.json')));
const rules = JSON.parse(readFileSync(resolve(root, 'knowledge/generic-house.json')));
const vertical = (request) => callCore(wasm, 'arq_vertical', request);
const generate = (input) => callCore(wasm, 'arq_generate', input);
const assertError = (response) => {
  assert.equal(response.status, 'error');
  assert.deepEqual(response.levels, []);
  assert.equal(response.model_hash, undefined);
  assert.equal(response.source, undefined);
};

test('Rust WASM/CLI use the same declared Z contract and exactly replay the v8 source', () => {
  assert.equal(typeof wasm.arq_vertical, 'function');
  const generated = generate(example.input);
  assert.equal(generated.status, 'ok');
  assert.equal(generated.input_hash, modelFixture.source.input_hash);
  assert.equal(generated.alternatives[0].id, example.candidate_id);
  const result = vertical(example);
  assert.equal(result.format, verticalModelFormat);
  assert.deepEqual(result, modelFixture);
  assert.equal(result.levels.length, 1);
  assert.equal(result.levels[0].openings.length, 8);
  assert.equal(result.facades, null);
  assert.equal(result.roof, null);
  for (const [i, opening] of result.levels[0].openings.entries()) {
    const source = i === 0 ? generated.alternatives[0].entrance.opening
      : generated.alternatives[0].rooms.find(({ id }) => id === opening.room_id).window.opening;
    assert.deepEqual(opening.plan_opening_v8, source);
    assert.ok(opening.bottom_z_m >= result.levels[0].floor_z_m);
    assert.ok(opening.top_z_m <= result.levels[0].wall_top_z_m);
  }
  const cli = spawnSync('cargo', ['run', '--offline', '--locked', '--quiet', '-p', 'arqgen-core',
    '--bin', 'arqgen-vertical', '--', 'examples/declared-vertical-v1-request.json'],
  { cwd: root, encoding: 'utf8' });
  assert.equal(cli.status, 0, cli.stderr || String(cli.error));
  assert.equal(cli.stdout.trim(), readFileSync(resolve(root, 'examples/declared-vertical-v1-model.json'), 'utf8').trim(),
    'WASM and native CLI are byte-identical on the same declared request.');
});

test('web builds a request only from explicit user heights; never seeds inferred architectural heights', () => {
  const generated = generate(example.input);
  const { floor_z_m, wall_top_z_m, entry_head_above_floor_m, window_sill_above_floor_m } = example.declared_vertical;
  const heights = { floor_z_m, wall_top_z_m, entry_head_above_floor_m, window_sill_above_floor_m };
  assert.deepEqual(makeVerticalRequest(example.input, generated, 0, heights), example);
  assert.deepEqual(vertical(makeVerticalRequest(example.input, generated, 0, heights)), modelFixture);
  const noSill = structuredClone(heights);
  delete noSill.window_sill_above_floor_m['bathroom-1'];
  assert.throws(() => makeVerticalRequest(example.input, generated, 0, noSill), /alféizar/);
  assert.throws(() => makeVerticalRequest(example.input, generated, 0,
    { ...heights, wall_top_z_m: NaN }), /tres cotas Z/);
  assert.throws(() => makeVerticalRequest(example.input, generated, 99, heights), /alternativa/);
  const other = makeVerticalRequest(example.input, generated, 1, heights);
  assert.equal(other.candidate_id, generated.alternatives[1].id);
  assert.notEqual(other.candidate_id, example.candidate_id);
});

test('invalid heights, nonexistent candidate or unsupported type never produce partial floors', () => {
  for (const change of [
    (r) => { r.candidate_id = 'cand-ab3376d8fef08f3b-9999'; },
    (r) => { r.typology = 'hospital'; },
    (r) => { r.typology = 'hotel'; },
    (r) => { r.declared_vertical.wall_top_z_m = 2.3; },
    (r) => { r.declared_vertical.entry_head_above_floor_m = -1; },
    (r) => { r.declared_vertical.entry_head_above_floor_m = 1e-12; },
    (r) => { r.declared_vertical.window_sill_above_floor_m['bathroom-1'] = 2.2; },
    (r) => { r.declared_vertical.window_sill_above_floor_m['fake-stair'] = 1; },
    (r) => { delete r.declared_vertical.window_sill_above_floor_m['bathroom-1']; },
    (r) => { r.input.site.width = 4; },
    (r) => { r.generation = { forged: true }; },
    (r) => { r.declared_vertical.height_provenance = 'surveyed'; },
  ]) {
    const request = structuredClone(example);
    change(request);
    assertError(vertical(request));
  }
  const changed = structuredClone(example);
  changed.declared_vertical.window_sill_above_floor_m['bathroom-1'] = 1.5;
  const result = vertical(changed);
  assert.equal(result.status, 'ok');
  assert.equal(result.source.input_hash, modelFixture.source.input_hash);
  assert.notEqual(result.model_hash, modelFixture.model_hash);
  assert.notEqual(result.levels[0].openings[1].bottom_z_m, modelFixture.levels[0].openings[1].bottom_z_m);
});

test('the vertical JSON archive is opt-in, bounded and imported only after complete Rust replay', () => {
  const archive = makeVerticalArchive(example, modelFixture);
  assert.equal(archive.format, verticalArchiveFormat);
  assert.deepEqual(archive, JSON.parse(readFileSync(resolve(root, 'examples/declared-vertical-v1-archive.json'))));
  assert.deepEqual(verifyVerticalArchive(archive, rules, vertical), { request: example, model: modelFixture });
  const altered = structuredClone(archive);
  altered.model.levels[0].openings[0].top_z_m += 0.1;
  assert.throws(() => verifyVerticalArchive(altered, rules, vertical), /difiere/);
  const extra = structuredClone(archive);
  extra.model.fake_facade = '<svg>invented</svg>';
  assert.throws(() => verifyVerticalArchive(extra, rules, vertical), /difiere/);
  const dishonest = structuredClone(archive);
  dishonest.request.declared_vertical.floor_z_m = 0.2;
  assert.throws(() => verifyVerticalArchive(dishonest, rules, vertical), /difiere/);
  const falseCandidate = structuredClone(archive);
  falseCandidate.request.candidate_id = 'fake';
  assert.throws(() => verifyVerticalArchive(falseCandidate, rules, vertical), /Rust|candidate_id/);
  const fakeRule = structuredClone(archive);
  fakeRule.request.input.rules.id = 'nc-cuba-ficticia';
  assert.throws(() => verifyVerticalArchive(fakeRule, rules, vertical), /Reglas incompatibles/);
  const old = structuredClone(archive);
  old.format = 'arqgen-declared-vertical-archive-v0';
  assert.throws(() => verifyVerticalArchive(old, rules, vertical), /desconocido/);
  assert.throws(() => makeVerticalArchive({ ...example, roof: { top_z_m: 5 } }, modelFixture), /Solicitud/);
});

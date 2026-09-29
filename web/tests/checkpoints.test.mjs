import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createCheckpoints, checkpointLimit, maxCheckpointBytes } from '../src/checkpoints.js';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const { instance } = await WebAssembly.instantiate(await readFile(resolve(root, 'web/public/core.wasm')));
const core = instance.exports;
const example = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const demo = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
function generate(input) {
  const bytes = new TextEncoder().encode(JSON.stringify(input));
  const ptr = core.arq_alloc(bytes.length);
  assert.ok(ptr);
  new Uint8Array(core.memory.buffer, ptr, bytes.length).set(bytes);
  let packed;
  try { packed = core.arq_generate(ptr, bytes.length); }
  finally { core.arq_free(ptr, bytes.length); }
  const outPtr = Number(packed & 0xffffffffn);
  const outLen = Number(packed >> 32n);
  let text;
  try { text = new TextDecoder().decode(new Uint8Array(core.memory.buffer, outPtr, outLen)); }
  finally { core.arq_free(outPtr, outLen); }
  return JSON.parse(text);
}
function evaluated(seed = 42, pressure = 60) {
  const input = { ...structuredClone(example), rules: structuredClone(demo), seed };
  input.rules.bath_pressure.fan_reference_pressure_pa = pressure;
  return { input, generation: generate(input) };
}

test('undo/redo replays Rust and restores the evaluated comparison book, not uncommitted input', () => {
  const history = createCheckpoints(demo, generate);
  const first = evaluated();
  const other = evaluated(42, 45);
  assert.equal(first.generation.status, 'ok');
  assert.equal(other.generation.status, 'ok');
  assert.deepEqual(history.status(), { position: 0, total: 0, canUndo: false, canRedo: false });
  history.reset(first, [first]);
  history.record(other, [first, other]);
  assert.deepEqual(history.status(), { position: 2, total: 2, canUndo: true, canRedo: false });
  let replays = 0;
  const checked = createCheckpoints(demo, (request) => { replays++; return generate(request); });
  checked.reset(first, [first]);
  checked.record(other, [first, other]);
  const previous = checked.prepare(-1);
  assert.equal(previous.focus.input.rules.bath_pressure.fan_reference_pressure_pa, 60);
  assert.equal(previous.records.length, 1);
  assert.equal(replays, 2, 'One Rust replay for focus and one for saved comparison.');
  assert.equal(checked.status().position, 2, 'Preparing does not mutate history.');
  checked.commit(previous);
  assert.equal(checked.prepare(1).focus.input.rules.bath_pressure.fan_reference_pressure_pa, 45);
  assert.equal(checked.prepare(0).focus.generation.status, 'ok', 'A pending form edit can be discarded into the latest checkpoint.');
  assert.deepEqual(first.input, checked.prepare(0).focus.input);
});

test('new branch drops redo; unchanged runs are deduplicated and failed replay cannot move cursor', () => {
  let forged = false;
  const history = createCheckpoints(demo, (input) => {
    const result = generate(input);
    if (forged) result.input_hash = 'forged';
    return result;
  });
  const first = evaluated();
  const other = evaluated(42, 45);
  history.reset(first, []);
  history.record(other, []);
  forged = true;
  assert.throws(() => history.prepare(-1), /difiere/);
  assert.equal(history.status().position, 2);
  forged = false;
  history.commit(history.prepare(-1));
  assert.equal(history.status().canRedo, true);
  history.record(first, []);
  assert.equal(history.status().canRedo, true, 'An identical regenerated input does not create a new branch.');
  const branch = evaluated(43);
  history.record(branch, []);
  assert.deepEqual(history.status(), { position: 2, total: 2, canUndo: true, canRedo: false });
  assert.throws(() => history.prepare(1), /No hay otra/);
  assert.throws(() => history.prepare(2), /inválido/);
});

test('history is bounded to 12 validated checkpoints and resets on a different project', () => {
  const history = createCheckpoints(demo, generate);
  for (let index = 0; index < checkpointLimit + 5; index++) {
    const run = evaluated(100 + index);
    assert.ok(['ok', 'infeasible'].includes(run.generation.status));
    history.record(run, []);
  }
  assert.equal(history.status().total, checkpointLimit);
  let steps = 0;
  while (history.status().canUndo) { history.commit(history.prepare(-1)); steps++; }
  assert.equal(steps, checkpointLimit - 1);
  assert.equal(history.prepare(0).focus.input.seed, 105, 'Oldest five runs have been evicted.');
  history.reset(evaluated(999), []);
  assert.deepEqual(history.status(), { position: 1, total: 1, canUndo: false, canRedo: false });
});

test('memory history evicts oldest checkpoints before exceeding 16 MiB', () => {
  const history = createCheckpoints(demo, generate);
  assert.equal(maxCheckpointBytes, 16 * 1024 * 1024);
  for (let index = 0; index < 5; index++) {
    const run = evaluated(500 + index);
    run.generation.notice = 'x'.repeat(4 * 1024 * 1024); // deliberately bulky, not a trusted archive
    history.record(run, []);
  }
  assert.ok(history.status().total <= 3);
  assert.equal(history.status().position, history.status().total);
});

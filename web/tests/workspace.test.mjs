import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifyWorkspace, snapshotWorkspace } from '../src/workspace.js';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const { instance } = await WebAssembly.instantiate(await readFile(resolve(root, 'web/public/core.wasm')));
const core = instance.exports;
const sample = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const demoRules = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
const input = () => ({ ...structuredClone(sample), rules: structuredClone(demoRules) });

function generate(request) {
  const bytes = new TextEncoder().encode(JSON.stringify(request));
  const pointer = core.arq_alloc(bytes.length);
  assert.ok(pointer);
  new Uint8Array(core.memory.buffer, pointer, bytes.length).set(bytes);
  let packed;
  try { packed = core.arq_generate(pointer, bytes.length); }
  finally { core.arq_free(pointer, bytes.length); }
  const ptr = Number(packed & 0xffffffffn);
  const len = Number(packed >> 32n);
  let text;
  try { text = new TextDecoder().decode(new Uint8Array(core.memory.buffer, ptr, len)); }
  finally { core.arq_free(ptr, len); }
  return JSON.parse(text);
}

function fixture() {
  const base = input();
  const partial = input(); partial.rules.bath_pressure.fan_reference_flow_m3h = 20;
  const impossible = input(); impossible.rules.bath_pressure.fan_reference_pressure_pa = 10;
  return [base, partial, impossible].map((request) => ({ input: request, generation: generate(request) }));
}

test('an opt-in local snapshot restores 0–3 scenarios and the focus only after replaying Rust', () => {
  const [base, partial, impossible] = fixture();
  assert.deepEqual([base, partial, impossible].map((r) => r.generation.rejected), [0, 12, 48]);
  const snapshot = snapshotWorkspace(impossible, [base, partial, impossible]);
  assert.equal(snapshot.focus.selection, null);
  assert.equal(snapshot.engine_version, base.generation.engine_version);
  let replays = 0;
  const verified = verifyWorkspace(snapshot, demoRules, (request) => { replays++; return generate(request); });
  assert.equal(replays, 4);
  assert.deepEqual(verified.records.map(({ generation }) => generation.status), ['ok', 'ok', 'infeasible']);
  assert.equal(verified.focus.generation.status, 'infeasible');
  assert.deepEqual(verified.records[0].generation, base.generation);
  assert.equal(verifyWorkspace(snapshotWorkspace(base, []), demoRules, generate).records.length, 0);
});

test('corrupted, incompatible or oversized local copies fail as a whole', () => {
  const [base, partial] = fixture();
  const snapshot = snapshotWorkspace(base, [base, partial]);
  const tamper = (update) => { const copy = structuredClone(snapshot); update(copy); return copy; };
  const badSvg = tamper((copy) => { copy.scenarios[1].generation.alternatives[0].svg += '<script/>'; });
  assert.throws(() => verifyWorkspace(badSvg, demoRules, generate), /difiere/);
  assert.equal(snapshot.scenarios[1].generation.alternatives[0].svg, partial.generation.alternatives[0].svg);
  assert.throws(() => verifyWorkspace(tamper((d) => { d.engine_version = 'old'; }), demoRules, generate), /versión/);
  for (const previous of ['arqgen-local-workspace-v1', 'arqgen-local-workspace-v2', 'arqgen-local-workspace-v3', 'arqgen-local-workspace-v4', 'arqgen-local-workspace-v5', 'arqgen-local-workspace-v6', 'arqgen-local-workspace-v7']) {
    assert.throws(() => verifyWorkspace(tamper((d) => { d.format = previous; }), demoRules, generate), /versión anterior/);
  }
  assert.throws(() => verifyWorkspace(tamper((d) => { d.focus.input.project_context.occupants = 4; }), demoRules, generate), /difiere/);
  assert.throws(() => verifyWorkspace(tamper((d) => { d.extra_claim = 'certified'; }), demoRules, generate), /estructura/);
  assert.throws(() => verifyWorkspace(tamper((d) => { d.focus.selection = { kind: 'approved' }; }), demoRules, generate), /estructura/);
  assert.throws(() => verifyWorkspace(tamper((d) => { d.focus.input.rules.id = 'new'; }), demoRules, generate), /Reglas incompatibles/);
  assert.throws(() => verifyWorkspace(tamper((d) => { d.scenarios[1].input.site.width += 1; }), demoRules, generate), /difiere/);
  assert.throws(() => verifyWorkspace(tamper((d) => { d.scenarios.push(d.scenarios[0], d.scenarios[0]); }), demoRules, generate), /estructura/);
  assert.throws(() => snapshotWorkspace(base, [base, { ...partial, input: { ...partial.input, seed: 123 } }]));
});

test('opt-in workspace preserves the site sketch through replay without making it an authoritative boundary', () => {
  const withArea = input();
  withArea.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }];
  withArea.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_corner_notch',
    rear_notches: [{ side: 'left', width: 4, depth: 10 }] };
  withArea.site.front_approach.width = 1.5;
  const record = { input: withArea, generation: generate(withArea) };
  assert.equal(record.generation.status, 'ok');
  const snapshot = snapshotWorkspace(record, [record]);
  assert.equal(snapshot.format, 'arqgen-local-workspace-v8');
  const replayed = verifyWorkspace(snapshot, demoRules, generate);
  assert.deepEqual(replayed.focus.input.site.reserved_areas, withArea.site.reserved_areas);
  assert.deepEqual(replayed.focus.input.site.plot_outline, withArea.site.plot_outline);
  assert.deepEqual(replayed.focus.input.site.front_approach, withArea.site.front_approach);
  assert.equal(replayed.records[0].generation.site_approach.width, 1.5);
  assert.equal(replayed.records[0].generation.alternatives[0].front_approach.segments[0].width, 1.5);
  assert.deepEqual(replayed.records[0].generation.site_reservations.areas, withArea.site.reserved_areas);
  assert.equal(replayed.records[0].generation.site_plot.geometry_status, 'orthogonal_plot_sketch_2d_only');
  const forged = structuredClone(snapshot);
  forged.focus.generation.site_reservations.provenance = 'official_survey';
  assert.throws(() => verifyWorkspace(forged, demoRules, generate), /difiere/);
  const falseLandArea = structuredClone(snapshot);
  falseLandArea.focus.generation.site.plot_area += 200;
  assert.throws(() => verifyWorkspace(falseLandArea, demoRules, generate), /difiere/);
  const conflict = structuredClone(snapshot);
  conflict.scenarios[0].input.site.plot_outline.rear_notches[0].side = 'right';
  assert.throws(() => verifyWorkspace(conflict, demoRules, generate), /difiere/);
  const wrongBand = structuredClone(snapshot);
  wrongBand.focus.generation.alternatives[0].front_approach.segments[0].x += 0.5;
  assert.throws(() => verifyWorkspace(wrongBand, demoRules, generate), /difiere/);
  const newBand = structuredClone(snapshot);
  newBand.scenarios[0].input.site.front_approach.width = 1.4;
  assert.throws(() => verifyWorkspace(newBand, demoRules, generate), /difiere/);
});

test('v8 workspace replays both posterior cuts and fails atomically for a changed second corner', () => {
  const request = input();
  request.site.plot_outline = { provenance: 'user_sketch_unverified',
    shape: 'rear_both_corners_notched', rear_notches: [
      { side: 'left', width: 4, depth: 10 }, { side: 'right', width: 3, depth: 10 },
    ] };
  const run = { input: request, generation: generate(request) };
  assert.equal(run.generation.status, 'ok');
  const snapshot = snapshotWorkspace(run, [run]);
  assert.equal(snapshot.format, 'arqgen-local-workspace-v8');
  const checked = verifyWorkspace(snapshot, demoRules, generate);
  assert.deepEqual(checked.focus.input.site.plot_outline.rear_notches,
    request.site.plot_outline.rear_notches);
  assert.equal(checked.records[0].generation.site_plot.vertices.length, 8);
  const forged = structuredClone(snapshot);
  forged.scenarios[0].input.site.plot_outline.rear_notches[1].depth += 1;
  assert.throws(() => verifyWorkspace(forged, demoRules, generate), /difiere/);
  const legacy = structuredClone(snapshot); legacy.format = 'arqgen-local-workspace-v7';
  assert.throws(() => verifyWorkspace(legacy, demoRules, generate), /versión anterior/);
});

test('local copy verifies two zones and cannot promote a forged exclusion to a plan', () => {
  const request = input();
  request.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
    { x: 14, y: 16, width: 1, depth: 2 }];
  const run = { input: request, generation: generate(request) };
  assert.equal(run.generation.status, 'ok');
  const snapshot = snapshotWorkspace(run, [run]);
  assert.equal(snapshot.format, 'arqgen-local-workspace-v8');
  const checked = verifyWorkspace(snapshot, demoRules, generate);
  assert.deepEqual(checked.focus.input.site.reserved_areas, request.site.reserved_areas);
  const invalid = structuredClone(snapshot);
  invalid.scenarios[0].input.site.reserved_areas[1].x = 6.49999999;
  assert.throws(() => verifyWorkspace(invalid, demoRules, generate));
  const forged = structuredClone(snapshot);
  forged.focus.generation.site.unreserved_buildable_area += 2;
  assert.throws(() => verifyWorkspace(forged, demoRules, generate), /difiere/);
});

test('local snapshot replays a declared detour and rejects altered corner geometry', () => {
  const site = input();
  site.site.reserved_areas = [{ x: 8.5, y: 0.5, width: 1, depth: 0.5 }];
  site.site.front_approach = { provenance: 'user_sketch_unverified',
    shape: 'orthogonal_front_detour', width: 1.2, front_x: 11.5, turn_y: 1.6 };
  const run = { input: site, generation: generate(site) };
  assert.equal(run.generation.status, 'ok');
  const snapshot = snapshotWorkspace(run, [run]);
  const opened = verifyWorkspace(snapshot, demoRules, generate);
  assert.equal(opened.records[0].generation.alternatives[0].front_approach.turns.length, 2);
  assert.deepEqual(opened.focus.input.site.front_approach, site.site.front_approach);
  const corrupted = structuredClone(snapshot);
  corrupted.focus.generation.alternatives[0].front_approach.segments[2].y -= 0.1;
  assert.throws(() => verifyWorkspace(corrupted, demoRules, generate), /difiere/);
  const changed = structuredClone(snapshot);
  changed.scenarios[0].input.site.front_approach.turn_y = 1.8;
  assert.throws(() => verifyWorkspace(changed, demoRules, generate), /difiere/);
});

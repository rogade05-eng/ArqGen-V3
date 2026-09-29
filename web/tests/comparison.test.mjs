import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { archiveScenario, comparisonKey, comparisonReport } from '../src/comparison.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const wasm = await readFile(resolve(root, 'web/public/core.wasm'));
const { instance } = await WebAssembly.instantiate(wasm);
const core = instance.exports;
const sample = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const rules = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
const req = () => ({ ...structuredClone(sample), rules: structuredClone(rules) });

function generate(input) {
  const bytes = new TextEncoder().encode(JSON.stringify(input));
  const pointer = core.arq_alloc(bytes.length);
  assert.ok(pointer);
  new Uint8Array(core.memory.buffer, pointer, bytes.length).set(bytes);
  let response;
  try { response = core.arq_generate(pointer, bytes.length); }
  finally { core.arq_free(pointer, bytes.length); }
  const start = Number(response & 0xffffffffn);
  const length = Number(response >> 32n);
  let text;
  try { text = new TextDecoder().decode(new Uint8Array(core.memory.buffer, start, length)); }
  finally { core.arq_free(start, length); }
  return JSON.parse(text);
}

test('archives viable, partially rejected and infeasible hypotheses without mixing requests', () => {
  const baseline = req();
  const partial = req();
  partial.rules.bath_pressure.fan_reference_flow_m3h = 20;
  const blocked = req();
  blocked.rules.bath_pressure.fan_reference_pressure_pa = 10;
  const before = [generate(baseline), generate(partial), generate(blocked)];
  assert.deepEqual(before.map(({ status }) => status), ['ok', 'ok', 'infeasible']);
  assert.deepEqual(before.map(({ rejected }) => rejected), [0, 12, 48]);
  assert.equal(comparisonKey(baseline), comparisonKey(partial));
  assert.equal(comparisonKey(partial), comparisonKey(blocked));
  let saved = [];
  for (const [input, result] of [[baseline, before[0]], [partial, before[1]], [blocked, before[2]]]) {
    const attempt = archiveScenario(saved, input, result);
    assert.equal(attempt.reason, 'saved');
    saved = attempt.records;
  }
  const report = comparisonReport(saved);
  assert.equal(report.format, 'arqgen-illustrative-comparison-v8');
  assert.equal(report.ventilation_status, 'not_evaluated');
  assert.deepEqual(report.varying_assumptions, [
    'fan_reference_pressure_pa', 'fan_reference_flow_m3h', 'assumed_reserve_pa',
  ]);
  assert.deepEqual(report.scenarios.map(({ generation }) => generation.rejected), [0, 12, 48]);
  assert.deepEqual(report.scenarios.map(({ input }) => input.rules.bath_pressure.fan_reference_flow_m3h), [90, 20, 90]);
  assert.deepEqual(report.scenarios[2].generation.alternatives, []);
  assert.equal(report.scenarios[0].generation.alternatives[0].bathroom_ventilation_status, 'not_evaluated');
  assert.equal(JSON.parse(JSON.stringify(report)).scenarios[1].generation.rejection_summary
    .reduce((total, item) => total + item.count, 0), 12);
  assert.equal(archiveScenario(saved, partial, before[1]).reason, 'duplicate');
  const fourth = req(); fourth.rules.bath_pressure.assumed_reserve_pa = 30;
  assert.equal(archiveScenario(saved, fourth, generate(fourth)).reason, 'full');
  partial.rules.bath_pressure.fan_reference_flow_m3h = 55;
  before[1].rejected = 99;
  assert.equal(comparisonReport(saved).scenarios[1].input.rules.bath_pressure.fan_reference_flow_m3h, 20);
  assert.equal(comparisonReport(saved).scenarios[1].generation.rejected, 12);
});

test('rejects mismatched briefs, seeds, fixed rules, malformed results and duplicate hashes', () => {
  const base = req();
  const result = generate(base);
  const saved = archiveScenario([], base, result).records;
  assert.throws(() => comparisonReport(saved), /entre 2 y 3/);
  const alternatives = [
    (input) => { input.seed += 1; },
    (input) => { input.site.width = 17; },
    (input) => { input.site.front_approach.width = 1.5; },
    (input) => { input.site.front_approach = {
      provenance: 'user_sketch_unverified', shape: 'orthogonal_front_detour',
      width: 1.2, front_x: 11.5, turn_y: 1.6,
    }; },
    (input) => { input.site.plot_outline = { provenance: 'user_sketch_unverified',
      shape: 'rear_corner_notch', rear_notches: [{ side: 'left', width: 4, depth: 10 }] }; },
    (input) => { input.site.plot_outline = { provenance: 'user_sketch_unverified',
      shape: 'rear_both_corners_notched', rear_notches: [
        { side: 'left', width: 4, depth: 10 }, { side: 'right', width: 3, depth: 10 },
      ] }; },
    (input) => { input.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }]; },
    (input) => { input.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
      { x: 14, y: 16, width: 1, depth: 2 }]; },
    (input) => { input.program.bathrooms = 1; },
    (input) => { input.project_context.jurisdiction = 'CU'; },
    (input) => { input.project_context.occupants = 4; },
    (input) => { input.rules.bath_pressure.assumed_darcy_factor = 0.05; },
  ];
  for (const change of alternatives) {
    const input = req(); change(input);
    assert.notEqual(comparisonKey(input), comparisonKey(base));
    const attempt = archiveScenario(saved, input, generate(input));
    assert.equal(attempt.reason, 'different_brief');
    assert.strictEqual(attempt.records, saved);
  }
  const incoherent = req(); incoherent.rules.bath_pressure.fan_reference_flow_m3h = 120;
  assert.equal(generate(incoherent).status, 'error');
  assert.equal(archiveScenario(saved, incoherent, generate(incoherent)).reason, 'invalid');
  const corrupt = structuredClone(result);
  corrupt.rejection_summary = [{ reason: '<img src=x onerror=alert(1)>', count: 1 }];
  assert.equal(archiveScenario(saved, base, corrupt).reason, 'invalid');
  corrupt.rejection_summary = [null];
  assert.equal(archiveScenario(saved, base, corrupt).reason, 'invalid');
  const clash = structuredClone(base); clash.rules.bath_pressure.assumed_reserve_pa = 30;
  assert.equal(archiveScenario(saved, clash, result).reason, 'hash_conflict');
  const drift = structuredClone(result); drift.engine_version = 'otro-motor';
  assert.equal(archiveScenario(saved, clash, drift).reason, 'different_brief');
  const changedResult = structuredClone(result); changedResult.notice = 'otra respuesta';
  assert.equal(archiveScenario(saved, base, changedResult).reason, 'hash_conflict');
  const reordered = { seed: base.seed, rules: base.rules, program: base.program,
    project_context: { provenance: base.project_context.provenance,
      occupants: base.project_context.occupants, housing_class: base.project_context.housing_class,
      jurisdiction: base.project_context.jurisdiction,
      accessibility_needs: base.project_context.accessibility_needs },
    site: base.site, request_schema: base.request_schema };
  assert.equal(comparisonKey(reordered), comparisonKey(base));
});

test('zero-variant infeasibility is recorded only as a standalone brief', () => {
  const tooNarrow = req(); tooNarrow.site.width = 7; tooNarrow.site.depth = 9;
  const infeasible = generate(tooNarrow);
  assert.equal(infeasible.status, 'infeasible');
  assert.equal(infeasible.generated, 0);
  assert.equal(infeasible.rejected, 0);
  assert.deepEqual(infeasible.rejection_summary, []);
  const alone = archiveScenario([], tooNarrow, infeasible);
  assert.equal(alone.reason, 'saved');
  assert.equal(archiveScenario(alone.records, req(), generate(req())).reason, 'different_brief');
});

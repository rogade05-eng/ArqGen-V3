import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { maxArchiveBytes, parseArchiveText, sameJson, verifyArchive } from '../src/archive.js';
import { archiveScenario, comparisonReport } from '../src/comparison.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const wasm = await readFile(resolve(root, 'web/public/core.wasm'));
const { instance } = await WebAssembly.instantiate(wasm);
const core = instance.exports;
const sample = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const demo = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
const request = () => ({ ...structuredClone(sample), rules: structuredClone(demo) });

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

function single(input = request()) {
  return { input, generation: generate(input), selection: null };
}
function comparison() {
  let records = [];
  for (const [field, value] of [
    [null, null], ['fan_reference_flow_m3h', 20], ['fan_reference_pressure_pa', 10],
  ]) {
    const input = request();
    if (field) input.rules.bath_pressure[field] = value;
    const result = archiveScenario(records, input, generate(input));
    assert.equal(result.reason, 'saved');
    records = result.records;
  }
  return comparisonReport(records);
}

test('single JSON roundtrip replays through Rust; imported selection never authorizes a plan', () => {
  const document = single();
  const alt = document.generation.alternatives[1];
  document.selection = {
    input_hash: document.generation.input_hash, candidate_id: alt.id,
    kind: 'user_preference_preliminary', chosen_at: '2026-09-25T14:30:00.000Z',
  };
  let replays = 0;
  const checked = verifyArchive(parseArchiveText(JSON.stringify(document)), demo, (input) => {
    replays++; return generate(input);
  });
  assert.equal(replays, 1);
  assert.equal(checked.kind, 'single');
  assert.deepEqual(checked.records, []);
  assert.equal(checked.focus.generation.input_hash, document.generation.input_hash);
  assert.equal(checked.focus.generation.alternatives[1].id, alt.id);
  assert.equal(checked.focus.generation.alternatives[1].bathroom_ventilation_status, 'not_evaluated');
  assert.equal('selection' in checked, false); // Never promote an imported preference.
  document.generation.alternatives[1].svg = '<svg onload="alert(1)"/>';
  document.input.site.width = 7;
  assert.notEqual(checked.focus.generation.alternatives[1].svg, document.generation.alternatives[1].svg);
  assert.equal(checked.focus.input.site.width, sample.site.width);
  const reordered = { selection: null, generation: checked.focus.generation, input: checked.focus.input };
  assert.equal(verifyArchive(reordered, demo, generate).kind, 'single');
});

test('comparison JSON replays all three scenarios, including partial and impossible; no cached plan is trusted', () => {
  const report = comparison();
  let replays = 0;
  const checked = verifyArchive(parseArchiveText(JSON.stringify(report, null, 2)), demo, (input) => {
    replays++; return generate(input);
  });
  assert.equal(replays, 3);
  assert.equal(checked.kind, 'comparison');
  assert.deepEqual(checked.records.map(({ generation }) => generation.rejected), [0, 12, 48]);
  assert.deepEqual(checked.records.map(({ generation }) => generation.status), ['ok', 'ok', 'infeasible']);
  assert.deepEqual(checked.records[2].generation.alternatives, []);
  assert.ok(sameJson(checked.records, report.scenarios));
  assert.equal(checked.focus.input.rules.bath_pressure.fan_reference_flow_m3h, 90);
  report.scenarios[0].generation.alternatives[0].svg = '<svg><script>alert(1)</script></svg>';
  assert.throws(() => verifyArchive(report, demo, generate), /respuesta guardada difiere/);
});

test('tampered results, unsupported rules, forged approval and format changes fail closed', () => {
  const baseline = single();
  const mutators = [
    (file) => { file.generation.rejected = 3; },
    (file) => { file.generation.engine_version = 'other'; },
    (file) => { file.generation.alternatives[0].svg += '<script>alert(1)</script>'; },
    (file) => { file.generation.ventilation_verified = true; },
    (file) => { file.input.rules.version = '0.6.0'; },
    (file) => { file.input.rules.bath_pressure.assumed_darcy_factor = 0.05; },
    (file) => { file.input.project_context.jurisdiction = 'CU'; },
    (file) => { file.input.site.plot_outline = { provenance: 'user_sketch_unverified',
      shape: 'rear_corner_notch', rear_notches: [{ side: 'left', width: 4, depth: 10 }] }; },
    (file) => { file.input.site.plot_outline.provenance = 'official_survey'; },
    (file) => { file.input.site.front_approach.width = 1.5; },
    (file) => { file.input.site.front_approach.provenance = 'certified_road'; },
    (file) => { file.generation.site_approach.geometry_status = 'road_access_verified'; },
    (file) => { file.generation.alternatives[0].front_approach.segments[0].x += 0.5; },
    (file) => { file.generation.site_plot.geometry_status = 'surveyed_parcel'; },
    (file) => { file.generation.site_plot.vertices[0].x += 4; },
    (file) => { file.input.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }]; },
    (file) => { file.input.site.reservation_provenance = 'official_cadastral'; },
    (file) => { file.generation.site_reservations.geometry_status = 'legal_setback_verified'; },
    (file) => { file.generation.applicability.declared_scope = 'complies'; },
    (file) => { file.selection = { kind: 'certified', input_hash: baseline.generation.input_hash,
      candidate_id: baseline.generation.alternatives[0].id, chosen_at: '2026-09-25T14:30:00.000Z' }; },
    (file) => { file.extra = 'cumple normativa'; },
    (file) => { delete file.input.rules; },
  ];
  for (const change of mutators) {
    const file = structuredClone(baseline);
    change(file);
    assert.throws(() => verifyArchive(file, demo, generate));
  }
  const badReport = comparison();
  badReport.scenarios[1].generation.rejected += 1;
  let replays = 0;
  assert.throws(() => verifyArchive(badReport, demo, (input) => {
    replays++; return generate(input);
  }), /respuesta guardada difiere/);
  assert.equal(replays, 2); // No partial comparison is returned.
  const claim = comparison(); claim.ventilation_status = 'verified';
  assert.throws(() => verifyArchive(claim, demo, generate), /metadatos/);
  const duplicate = comparison(); duplicate.scenarios[1] = structuredClone(duplicate.scenarios[0]);
  assert.throws(() => verifyArchive(duplicate, demo, generate), /incompatibles/);
  assert.throws(() => verifyArchive({ format: 'unknown' }, demo, generate), /Formato/);
  const oldSingle = single(); delete oldSingle.input.request_schema;
  assert.throws(() => verifyArchive(oldSingle, demo, generate), /Entrada antigua/);
  for (const previous of ['arqgen-illustrative-comparison-v1', 'arqgen-illustrative-comparison-v2', 'arqgen-illustrative-comparison-v3', 'arqgen-illustrative-comparison-v4', 'arqgen-illustrative-comparison-v5', 'arqgen-illustrative-comparison-v6', 'arqgen-illustrative-comparison-v7']) {
    const oldComparison = comparison(); oldComparison.format = previous;
    assert.throws(() => verifyArchive(oldComparison, demo, generate), /versión anterior/);
  }
  for (const previous of ['arqgen-brief-v2', 'arqgen-brief-v3', 'arqgen-brief-v4', 'arqgen-brief-v5', 'arqgen-brief-v6', 'arqgen-brief-v7']) {
    const oldSchema = single(); oldSchema.input.request_schema = previous;
    assert.throws(() => verifyArchive(oldSchema, demo, generate), /Entrada antigua/);
  }
  assert.throws(() => parseArchiveText('{ this is not JSON'), /JSON válido/);
  assert.throws(() => parseArchiveText(' '.repeat(maxArchiveBytes + 1)), /8 MiB/);
  assert.equal(sameJson({ b: 2, a: 1 }, { a: 1, b: 2 }), true);
  assert.equal(sameJson({ a: 1 }, { a: 2 }), false);
});

test('a saved site sketch replays only through current Rust and survives a comparison without legal claims', () => {
  const first = request();
  first.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }];
  first.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_corner_notch',
    rear_notches: [{ side: 'left', width: 4, depth: 10 }] };
  first.site.front_approach.width = 1.5;
  const one = single(first);
  assert.equal(one.generation.status, 'ok');
  const imported = verifyArchive(one, demo, generate);
  assert.deepEqual(imported.focus.input.site.reserved_areas, first.site.reserved_areas);
  assert.equal(imported.focus.generation.site_reservations.geometry_status,
    'footprint_exclusion_2d_only');
  assert.equal(imported.focus.generation.site_plot.geometry_status, 'orthogonal_plot_sketch_2d_only');
  assert.deepEqual(imported.focus.input.site.plot_outline, first.site.plot_outline);
  assert.deepEqual(imported.focus.input.site.front_approach, first.site.front_approach);
  assert.equal(imported.focus.generation.alternatives[0].front_approach.width, 1.5);
  const second = structuredClone(first);
  second.rules.bath_pressure.fan_reference_flow_m3h = 20;
  const firstSaved = archiveScenario([], first, one.generation);
  assert.equal(firstSaved.reason, 'saved');
  const secondSaved = archiveScenario(firstSaved.records, second, generate(second));
  assert.equal(secondSaved.reason, 'saved');
  const checked = verifyArchive(comparisonReport(secondSaved.records), demo, generate);
  assert.equal(checked.kind, 'comparison');
  assert.equal(checked.records.length, 2);
  const changed = structuredClone(first);
  changed.site.reserved_areas = [{ x: 8, y: 3, width: 2, depth: 3 }];
  const blocked = generate(changed);
  assert.equal(blocked.status, 'infeasible');
  assert.equal(archiveScenario(firstSaved.records, changed, blocked).reason, 'different_brief');
  const changedOutline = structuredClone(first);
  changedOutline.site.plot_outline.rear_notches[0].side = 'right';
  assert.equal(archiveScenario(firstSaved.records, changedOutline,
    generate(changedOutline)).reason, 'different_brief');
  const changedBand = structuredClone(first);
  changedBand.site.front_approach.width = 1.2;
  assert.equal(archiveScenario(firstSaved.records, changedBand,
    generate(changedBand)).reason, 'different_brief');
  assert.equal(verifyArchive({ input: changed, generation: blocked, selection: null },
    demo, generate).focus.generation.status, 'infeasible');
  const tampered = structuredClone(one);
  tampered.input.site.reserved_areas[0].x = 4.8;
  assert.throws(() => verifyArchive(tampered, demo, generate), /difiere/);
});

test('an archived blocked straight front band replays as infeasible, not as a certified route', () => {
  const input = request();
  input.site.reserved_areas = [{ x: 8.5, y: 1, width: 1, depth: 1 }];
  const output = generate(input);
  assert.equal(output.status, 'infeasible');
  assert.ok(output.rejection_summary.some(({ reason }) => reason.includes('franja frontal recta')));
  const saved = { input, generation: output, selection: null };
  assert.equal(verifyArchive(saved, demo, generate).focus.generation.status, 'infeasible');
  const forged = structuredClone(saved);
  forged.generation.site_approach.provenance = 'public_road_verified';
  assert.throws(() => verifyArchive(forged, demo, generate), /difiere/);
  const prior = structuredClone(saved);
  prior.input.request_schema = 'arqgen-brief-v4';
  assert.throws(() => verifyArchive(prior, demo, generate), /Entrada antigua/);
});

test('v8 files replay both zones and reject altered second-zone coordinates atomically', () => {
  const input = request();
  input.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
    { x: 14, y: 16, width: 1, depth: 2 }];
  const saved = single(input);
  assert.equal(saved.generation.status, 'ok');
  const reopened = verifyArchive(saved, demo, generate);
  assert.deepEqual(reopened.focus.input.site.reserved_areas, input.site.reserved_areas);
  assert.equal(reopened.focus.generation.alternatives[0].decisions.filter(({ rule }) =>
    rule === 'site.reserved_areas@user_sketch_unverified').length, 2);
  const tampered = structuredClone(saved);
  tampered.input.site.reserved_areas[1].x = 13;
  assert.throws(() => verifyArchive(tampered, demo, generate), /difiere/);
  const overlapping = structuredClone(saved);
  overlapping.input.site.reserved_areas[1].x = 6.49999999;
  overlapping.input.site.reserved_areas[1].y = 12;
  assert.throws(() => verifyArchive(overlapping, demo, generate), /validación/);
});

test('v8 exports two opposite rear cuts; forged second cut or eight-vertex echo never survives replay', () => {
  const input = request();
  input.site.plot_outline = { provenance: 'user_sketch_unverified',
    shape: 'rear_both_corners_notched', rear_notches: [
      { side: 'right', width: 3, depth: 10 }, { side: 'left', width: 4, depth: 10 },
    ] };
  const archived = single(input);
  assert.equal(archived.generation.status, 'ok');
  const checked = verifyArchive(archived, demo, generate);
  assert.deepEqual(checked.focus.generation.site_plot.rear_notches, input.site.plot_outline.rear_notches);
  assert.equal(checked.focus.generation.site_plot.vertices.length, 8);
  const changed = structuredClone(archived);
  changed.input.site.plot_outline.rear_notches[1].width += 0.1;
  assert.throws(() => verifyArchive(changed, demo, generate), /difiere/);
  const fakePlan = structuredClone(archived);
  fakePlan.generation.site_plot.vertices[4].x = 14;
  assert.throws(() => verifyArchive(fakePlan, demo, generate), /difiere/);
  const oldSchema = structuredClone(archived);
  oldSchema.input.request_schema = 'arqgen-brief-v7';
  assert.throws(() => verifyArchive(oldSchema, demo, generate), /Entrada antigua/);
  const contrast = structuredClone(input);
  contrast.rules.bath_pressure.fan_reference_flow_m3h = 20;
  const one = archiveScenario([], input, archived.generation);
  const two = archiveScenario(one.records, contrast, generate(contrast));
  assert.equal(one.reason, 'saved');
  assert.equal(two.reason, 'saved');
  const comparison = comparisonReport(two.records);
  assert.equal(comparison.format, 'arqgen-illustrative-comparison-v8');
  assert.equal(verifyArchive(comparison, demo, generate).records.length, 2);
});

test('v8 detour survives replay while changed bends, bands and fake legal status fail atomically', () => {
  const input = request();
  input.site.reserved_areas = [{ x: 8.5, y: 0.5, width: 1, depth: 0.5 }];
  const blocked = single(input);
  assert.equal(blocked.generation.status, 'infeasible');
  input.site.front_approach = { provenance: 'user_sketch_unverified',
    shape: 'orthogonal_front_detour', width: 1.2, front_x: 11.5, turn_y: 1.6 };
  const saved = single(input);
  assert.equal(saved.generation.status, 'ok');
  const reopened = verifyArchive(saved, demo, generate);
  assert.deepEqual(reopened.focus.input.site.front_approach, input.site.front_approach);
  assert.equal(reopened.focus.generation.alternatives[0].front_approach.segments.length, 3);
  const second = structuredClone(input);
  second.rules.bath_pressure.assumed_reserve_pa = 30;
  const records = archiveScenario([], input, saved.generation).records;
  const report = comparisonReport(archiveScenario(records, second, generate(second)).records);
  assert.equal(report.format, 'arqgen-illustrative-comparison-v8');
  assert.equal(verifyArchive(report, demo, generate).records.length, 2);
  for (const mutate of [
    (copy) => { copy.input.site.front_approach.turn_y = 1.7; },
    (copy) => { copy.input.site.front_approach.front_x = 10.5; },
    (copy) => { copy.input.site.front_approach.front_x = null; },
    (copy) => { copy.generation.site_approach.right_of_way_status = 'verified'; },
    (copy) => { copy.generation.alternatives[0].front_approach.turns[0].y += 0.1; },
    (copy) => { copy.generation.alternatives[0].front_approach.segments[1].depth += 0.1; },
  ]) {
    const copy = structuredClone(saved);
    mutate(copy);
    assert.throws(() => verifyArchive(copy, demo, generate));
    assert.equal(copy.selection, null);
  }
});

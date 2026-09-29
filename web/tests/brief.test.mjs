import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readBriefForm, writeBriefForm, requestSchema } from '../src/brief.js';
import { hypothesisFields } from '../src/comparison.js';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const sample = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const rules = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
const fields = () => Object.fromEntries([
  'width', 'depth', 'front_orientation', 'notch_side', 'notch_width', 'notch_depth', 'notch_2_width', 'notch_2_depth',
  'approach_shape', 'approach_width', 'approach_front_x', 'approach_turn_y',
  'reserve_x', 'reserve_y', 'reserve_width', 'reserve_depth',
  'reserve_2_x', 'reserve_2_y', 'reserve_2_width', 'reserve_2_depth',
  'bedrooms', 'bathrooms', 'target_built_area', 'project_jurisdiction', 'housing_class',
  'occupants', 'accessibility_needs', 'seed', ...hypothesisFields,
].map((name) => [name, { value: '' }]).concat([
  ['plot_notch_enabled', { checked: false }], ['plot_notch_2_enabled', { checked: false }],
  ['reserve_enabled', { checked: false }],
  ['reserve_2_enabled', { checked: false }],
]));

test('form mapping preserves version, unknowns, declarations and all fixed demo rules', () => {
  assert.equal(sample.request_schema, requestSchema);
  const controls = fields();
  const expected = { ...structuredClone(sample), rules: structuredClone(rules) };
  writeBriefForm(controls, expected, hypothesisFields);
  assert.equal(controls.occupants.value, ''); // null remains unknown, not zero
  assert.equal(controls.plot_notch_enabled.checked, false);
  assert.equal(controls.approach_width.value, '1.2');
  assert.deepEqual(readBriefForm(controls, rules, hypothesisFields), expected);
  controls.project_jurisdiction.value = 'CU';
  controls.housing_class.value = 'urban_social';
  controls.occupants.value = '4';
  controls.accessibility_needs.value = 'declared';
  controls.fan_reference_flow_m3h.value = '20';
  controls.plot_notch_enabled.checked = true;
  controls.notch_side.value = 'right';
  controls.notch_width.value = '4';
  controls.notch_depth.value = '10';
  controls.approach_width.value = '1.5';
  controls.reserve_enabled.checked = true;
  controls.reserve_x.value = '4.5';
  controls.reserve_y.value = '12';
  controls.reserve_width.value = '2';
  controls.reserve_depth.value = '2';
  const changed = readBriefForm(controls, rules, hypothesisFields);
  assert.deepEqual(changed.site.reserved_areas, [{ x: 4.5, y: 12, width: 2, depth: 2 }]);
  assert.equal(changed.site.reservation_provenance, 'user_sketch_unverified');
  assert.deepEqual(changed.site.plot_outline, {
    provenance: 'user_sketch_unverified', shape: 'rear_corner_notch',
    rear_notches: [{ side: 'right', width: 4, depth: 10 }],
  });
  assert.deepEqual(changed.site.front_approach, {
    provenance: 'user_sketch_unverified', shape: 'straight_front_strip', width: 1.5,
    front_x: null, turn_y: null,
  });
  assert.deepEqual(changed.project_context, {
    jurisdiction: 'CU', housing_class: 'urban_social', occupants: 4,
    accessibility_needs: 'declared', provenance: 'self_reported_unverified',
  });
  assert.equal(changed.rules.bath_pressure.fan_reference_flow_m3h, 20);
  assert.equal(rules.bath_pressure.fan_reference_flow_m3h, 90); // snapshot, not a global mutation
  assert.equal(changed.rules.spaces.bathroom.window_ratio, 0.05);
  const restored = fields();
  writeBriefForm(restored, changed, hypothesisFields);
  assert.equal(restored.reserve_enabled.checked, true);
  assert.equal(restored.plot_notch_enabled.checked, true);
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields), changed);
  restored.reserve_enabled.checked = false;
  restored.plot_notch_enabled.checked = false;
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields).site.reserved_areas, []);
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields).site.plot_outline,
    { provenance: 'user_sketch_unverified', shape: 'rectangle', rear_notches: [] });
  writeBriefForm(restored, changed, hypothesisFields);
  const old = structuredClone(changed); delete old.request_schema;
  assert.throws(() => writeBriefForm(restored, old, hypothesisFields), /versión anterior/);
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields), changed);
  const forged = structuredClone(changed);
  forged.site.reservation_provenance = 'official_cadastral';
  assert.throws(() => writeBriefForm(restored, forged, hypothesisFields), /rectángulos voluntarios/);
  const multiple = structuredClone(changed);
  multiple.site.reserved_areas.push(structuredClone(multiple.site.reserved_areas[0]),
    structuredClone(multiple.site.reserved_areas[0]));
  assert.throws(() => writeBriefForm(restored, multiple, hypothesisFields), /hasta dos rectángulos/);
  const fakePlot = structuredClone(changed);
  fakePlot.site.plot_outline.provenance = 'verified_cadastre';
  assert.throws(() => writeBriefForm(restored, fakePlot, hypothesisFields), /recortes posteriores/);
  fakePlot.site.plot_outline.provenance = 'user_sketch_unverified';
  fakePlot.site.plot_outline.rear_notches[0].side = 'all_sides';
  assert.throws(() => writeBriefForm(restored, fakePlot, hypothesisFields), /recortes posteriores/);
  const falseApproach = structuredClone(changed);
  falseApproach.site.front_approach.provenance = 'legal_right_of_way';
  assert.throws(() => writeBriefForm(restored, falseApproach, hypothesisFields), /franja recta o un rodeo ortogonal/);
  falseApproach.site.front_approach.provenance = 'user_sketch_unverified';
  falseApproach.site.front_approach.width = 30;
  assert.throws(() => writeBriefForm(restored, falseApproach, hypothesisFields), /franja recta o un rodeo ortogonal/);
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields), changed);
});

test('form writes and reads two optional zones without leaking disabled second-slot values', () => {
  const controls = fields();
  const original = { ...structuredClone(sample), rules: structuredClone(rules) };
  writeBriefForm(controls, original, hypothesisFields);
  assert.equal(controls.reserve_enabled.checked, false);
  assert.equal(controls.reserve_2_enabled.checked, false);
  controls.reserve_enabled.checked = true;
  controls.reserve_2_enabled.checked = true;
  const combined = readBriefForm(controls, rules, hypothesisFields);
  assert.deepEqual(combined.site.reserved_areas, [
    { x: 4.5, y: 12, width: 2, depth: 2 },
    { x: 13, y: 12, width: 2, depth: 2 },
  ]);
  const restored = fields();
  writeBriefForm(restored, combined, hypothesisFields);
  assert.equal(restored.reserve_enabled.checked, true);
  assert.equal(restored.reserve_2_enabled.checked, true);
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields), combined);
  restored.reserve_enabled.checked = false;
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields).site.reserved_areas, []);
  restored.reserve_enabled.checked = true;
  restored.reserve_2_enabled.checked = false;
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields).site.reserved_areas,
    [combined.site.reserved_areas[0]]);
  writeBriefForm(restored, original, hypothesisFields);
  assert.equal(restored.reserve_2_x.value, '13');
  assert.equal(restored.reserve_2_enabled.checked, false);
});

test('form maps an explicit two-turn sketch without confusing it with a legal route', () => {
  const controls = fields();
  const initial = { ...structuredClone(sample), rules: structuredClone(rules) };
  writeBriefForm(controls, initial, hypothesisFields);
  controls.approach_shape.value = 'orthogonal_front_detour';
  controls.approach_front_x.value = '11.5';
  controls.approach_turn_y.value = '1.6';
  controls.reserve_enabled.checked = true;
  controls.reserve_x.value = '8.5';
  controls.reserve_y.value = '0.5';
  controls.reserve_width.value = '1';
  controls.reserve_depth.value = '0.5';
  const detour = readBriefForm(controls, rules, hypothesisFields);
  assert.deepEqual(detour.site.front_approach, {
    provenance: 'user_sketch_unverified', shape: 'orthogonal_front_detour',
    width: 1.2, front_x: 11.5, turn_y: 1.6,
  });
  const restored = fields();
  writeBriefForm(restored, detour, hypothesisFields);
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields), detour);
  restored.approach_shape.value = 'straight_front_strip';
  const straight = readBriefForm(restored, rules, hypothesisFields);
  assert.deepEqual(straight.site.front_approach, {
    provenance: 'user_sketch_unverified', shape: 'straight_front_strip',
    width: 1.2, front_x: null, turn_y: null,
  });
  for (const mutate of [
    (a) => { a.front_x = null; },
    (a) => { a.turn_y = '1.6'; },
    (a) => { a.front_x = 0.1; },
    (a) => { a.extra_claim = true; },
    (a) => { a.provenance = 'surveyed'; },
  ]) {
    const bad = structuredClone(detour);
    mutate(bad.site.front_approach);
    assert.throws(() => writeBriefForm(restored, bad, hypothesisFields), /franja recta o un rodeo ortogonal/);
  }
});


test('form maps two opposite rear cuts, keeps input order and never leaks disabled B', () => {
  const original = { ...structuredClone(sample), rules: structuredClone(rules) };
  const controls = fields();
  writeBriefForm(controls, original, hypothesisFields);
  assert.equal(controls.plot_notch_2_enabled.checked, false);
  controls.plot_notch_enabled.checked = true;
  controls.notch_side.value = 'right';
  controls.plot_notch_2_enabled.checked = true;
  const both = readBriefForm(controls, rules, hypothesisFields);
  assert.deepEqual(both.site.plot_outline, {
    provenance: 'user_sketch_unverified', shape: 'rear_both_corners_notched',
    rear_notches: [{ side: 'right', width: 4, depth: 10 },
      { side: 'left', width: 3, depth: 9 }],
  });
  const restored = fields();
  writeBriefForm(restored, both, hypothesisFields);
  assert.equal(restored.plot_notch_2_enabled.checked, true);
  assert.equal(restored.notch_side.value, 'right');
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields), both);
  restored.plot_notch_enabled.checked = false;
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields).site.plot_outline,
    { provenance: 'user_sketch_unverified', shape: 'rectangle', rear_notches: [] });
  restored.plot_notch_enabled.checked = true;
  restored.plot_notch_2_enabled.checked = false;
  assert.deepEqual(readBriefForm(restored, rules, hypothesisFields).site.plot_outline.rear_notches,
    [both.site.plot_outline.rear_notches[0]]);
  for (const mutate of [
    (plot) => { plot.rear_notches[1].side = 'right'; },
    (plot) => { plot.shape = 'rectangle'; },
    (plot) => { plot.rear_notches.push({ side: 'left', width: 1, depth: 1 }); },
    (plot) => { plot.survey = true; },
  ]) {
    const bad = structuredClone(both);
    mutate(bad.site.plot_outline);
    assert.throws(() => writeBriefForm(restored, bad, hypothesisFields), /recortes posteriores/);
  }
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const wasm = await readFile(resolve(root, 'web/public/core.wasm'));
const { instance } = await WebAssembly.instantiate(wasm);
const core = instance.exports;
const sample = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const rules = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));

function generate(input) {
  const bytes = new TextEncoder().encode(JSON.stringify(input));
  const ptr = core.arq_alloc(bytes.length);
  assert.ok(ptr);
  new Uint8Array(core.memory.buffer, ptr, bytes.length).set(bytes);
  let packed;
  try { packed = core.arq_generate(ptr, bytes.length); }
  finally { core.arq_free(ptr, bytes.length); }
  const outPtr = Number(packed & 0xffffffffn);
  const outSize = Number(packed >> 32n);
  assert.ok(outPtr && outSize);
  let text;
  try { text = new TextDecoder().decode(new Uint8Array(core.memory.buffer, outPtr, outSize)); }
  finally { core.arq_free(outPtr, outSize); }
  return text;
}

function req() { return { ...structuredClone(sample), rules: structuredClone(rules) }; }

function checkRejections(result) {
  assert.ok(Array.isArray(result.rejection_summary));
  if (result.status === 'error') {
    assert.deepEqual(result.rejection_summary, []);
    return;
  }
  assert.ok(Number.isInteger(result.generated) && Number.isInteger(result.rejected));
  assert.ok(result.generated >= result.rejected && result.rejected >= 0);
  assert.equal(result.rejection_summary.reduce((total, row) => total + row.count, 0), result.rejected);
  result.rejection_summary.forEach((row, index) => {
    assert.ok(typeof row.reason === 'string' && row.reason.length > 0);
    assert.ok(Number.isInteger(row.count) && row.count > 0);
    if (index > 0) {
      const prev = result.rejection_summary[index - 1];
      assert.ok(prev.count > row.count || (prev.count === row.count && prev.reason < row.reason));
    }
  });
  if (result.status === 'infeasible') {
    assert.equal(result.rejected, result.generated);
    assert.deepEqual(result.alternatives, []);
  }
}

test('WASM Rust produces three validated alternatives and stable output', () => {
  const input = req();
  const text = generate(input);
  assert.equal(generate(input), text);
  const result = JSON.parse(text);
  assert.equal(result.status, 'ok');
  assert.equal(result.alternatives.length, 3);
  assert.equal(result.regulatory_status, 'illustrative_not_certified');
  assert.equal(result.engine_version, 'mvp0.18-rust-0.15.0');
  assert.equal(result.request_schema, 'arqgen-brief-v8');
  assert.deepEqual(result.project_context, input.project_context);
  assert.equal(result.applicability.status, 'not_evaluated');
  assert.equal(result.applicability.declared_scope, 'undetermined');
  assert.equal(result.applicability.source_status, 'no_verified_cuban_ruleset');
  assert.deepEqual(result.site_reservations, {
    areas: [], geometry_status: 'footprint_exclusion_2d_only', provenance: 'user_sketch_unverified',
  });
  assert.deepEqual(result.site_plot, {
    provenance: 'user_sketch_unverified', geometry_status: 'orthogonal_plot_sketch_2d_only',
    shape: 'rectangle', rear_notches: [],
    vertices: [{ x: 0, y: 0 }, { x: input.site.width, y: 0 },
      { x: input.site.width, y: input.site.depth }, { x: 0, y: input.site.depth }],
  });
  assert.deepEqual(result.site_approach, {
    provenance: 'user_sketch_unverified', geometry_status: 'declared_front_trace_sketch_2d_only',
    shape: 'straight_front_strip', width: 1.2, front_x: null, turn_y: null,
    street_connection_status: 'not_evaluated', right_of_way_status: 'not_evaluated',
    accessibility_status: 'not_evaluated',
  });
  assert.equal(result.site.plot_area, input.site.width * input.site.depth);
  assert.equal(result.site.unreserved_buildable_area,
    result.site.buildable.width * result.site.buildable.depth);
  assert.deepEqual(result.applicability.missing_context,
    ['jurisdiction', 'housing_class', 'occupants', 'accessibility_needs']);
  assert.equal(result.rule_version, rules.version);
  checkRejections(result);
  for (const alt of result.alternatives) {
    assert.equal(alt.rooms.filter((room) => room.type === 'bedroom').length, 3);
    assert.equal(alt.rooms.filter((room) => room.type === 'bathroom').length, 2);
    assert.ok(alt.built_area <= result.site.max_footprint + 1e-7);
    assert.ok(alt.built_area <= result.site.max_built_area + 1e-7);
    assert.ok(Math.abs(alt.built_area - alt.usable_area - alt.wall_allowance_area) < 1e-5);
    assert.ok(alt.wall_zones.length > 0 && alt.corridor_usable_segments.length > 0);
    assert.equal(alt.bathroom_ventilation_status, 'not_evaluated');
    assert.equal(alt.bathroom_exhaust_status, 'geometry_reserved_only');
    assert.equal(alt.bathroom_airflow_status, 'nominal_precheck_only');
    assert.equal(alt.bathroom_pressure_status, 'hypothetical_pressure_screen_only');
    assert.deepEqual(alt.front_approach, {
      geometry_status: 'strip_clear_of_declared_exclusions_2d_only', shape: 'straight_front_strip', width: 1.2,
      segments: [{ x: 8.4, y: 0, width: 1.2, depth: 3 }], turns: [],
      front_contact: { x: 9, y: 0 }, door_contact: { x: 9, y: 3 },
    });
    assert.match(alt.svg, /class="front-approach-strip"/);
    assert.ok(alt.decisions.some(({ rule }) => rule === 'site.front_approach@user_sketch_unverified'));
    assert.match(alt.svg, /PRESIÓN SUPUESTA/);
    assert.match(alt.svg, /CAUDAL ENTREGADO NO EVALUADO/);
    assert.match(alt.svg, /NO APTO PARA OBRA/);
    assert.match(alt.svg, /class="fixture"/);
    assert.match(alt.svg, /class="exhaust-outlet"/);
    for (const room of alt.rooms) {
      assert.equal(room.area, room.usable_area);
      assert.ok(room.usable_area < room.gross_cell_area);
      assert.equal(room.door.opening.depth, room.door.width);
      assert.equal(room.furnishing_status, 'illustrative_geometric_fit');
      assert.equal(room.furnishings.length, { living_dining: 2, kitchen: 2, bedroom: 1, bathroom: 3 }[room.type]);
      assert.equal(room.access_route.length, 2);
      assert.ok(room.access_route[0].width >= rules.furnishings.min_aisle - 1e-7);
      if (room.type === 'bathroom') {
        assert.equal(room.daylight_status, 'not_evaluated');
        assert.equal(room.window_geometry_status, 'exterior_opening_drawn_only');
        assert.ok(room.window);
        assert.ok(room.window.width * room.window.height >= room.usable_area * rules.spaces.bathroom.window_ratio - 1e-7);
        assert.ok(room.window.y < room.bath_exhaust.outlet.y);
        assert.ok(room.bath_exhaust.outlet.y - (room.window.opening.y + room.window.opening.depth) >= rules.openings.corner_clearance - 1e-7);
        const shower = room.furnishings.find((fixture) => fixture.type === 'shower').footprint;
        const exterior = room.side === 'left'
          ? shower.x - room.usable_rect.x
          : room.usable_rect.x + room.usable_rect.width - (shower.x + shower.width);
        assert.ok(exterior >= 0.20 - 1e-7);
        assert.equal(room.ventilation_status, 'not_evaluated');
        assert.equal(room.bath_exhaust.mode, 'direct_exterior_exhaust_reservation');
        assert.equal(room.bath_exhaust.airflow_status, 'not_evaluated');
        assert.ok(room.bath_exhaust.run_length <= rules.bath_exhaust.max_run + 1e-7);
        assert.equal(room.bath_exhaust.outlet.depth, rules.bath_exhaust.outlet_span);
        assert.equal(room.bath_exhaust.route.depth, rules.bath_exhaust.route_band);
        const check = room.bath_airflow;
        assert.equal(check.status, 'nominal_precheck_only');
        assert.equal(check.delivered_flow_status, 'not_evaluated');
        assert.equal(check.target_ach, rules.bath_airflow.target_ach);
        assert.equal(check.assumed_ceiling_height_m, rules.bath_airflow.assumed_ceiling_height);
        const flow = room.usable_area * check.assumed_ceiling_height_m * check.target_ach;
        assert.ok(Math.abs(check.target_flow_m3h - flow) < 1e-6);
        assert.ok(flow <= check.fan_reference_free_air_rating_m3h + 1e-7);
        const transferArea = room.door.width * rules.bath_airflow.door_undercut;
        assert.ok(Math.abs(check.transfer.assumed_free_area_m2 - transferArea) < 1e-7);
        assert.ok(Math.abs(check.transfer.velocity_at_target_mps - flow / (3600 * transferArea)) < 1e-7);
        assert.ok(check.transfer.velocity_at_target_mps <= check.transfer.max_velocity_mps + 1e-7);
        const duct = check.duct;
        const width = Math.min(room.bath_exhaust.route.depth, room.bath_exhaust.outlet.depth);
        assert.ok(Math.abs(duct.assumed_width_m - width) < 1e-7);
        assert.equal(duct.assumed_height_m, rules.bath_airflow.duct_height);
        const section = width * duct.assumed_height_m;
        assert.ok(Math.abs(duct.assumed_section_m2 - section) < 1e-7);
        assert.ok(Math.abs(duct.velocity_at_target_mps - flow / (3600 * section)) < 1e-7);
        assert.ok(duct.velocity_at_target_mps <= duct.max_velocity_mps + 1e-7);
        assert.ok(duct.assumed_bottom_m >= duct.min_headroom_m - 1e-7);
        assert.ok(duct.assumed_top_m <= check.assumed_ceiling_height_m + 1e-7);
        const scenario = room.bath_pressure;
        assert.equal(scenario.status, 'hypothetical_pressure_screen_only');
        assert.equal(scenario.delivered_flow_status, 'not_evaluated');
        const a = scenario.assumptions;
        const reference = scenario.fan_reference;
        const p = scenario.pressure_budget;
        assert.equal(reference.free_air_flow_m3h, rules.bath_airflow.fan_free_air_rating);
        assert.equal(reference.reference_pressure_pa, rules.bath_pressure.fan_reference_pressure_pa);
        assert.ok(reference.reference_flow_m3h < reference.free_air_flow_m3h);
        assert.ok(Math.abs(p.target_flow_m3h - flow) < 1e-7);
        const length = room.bath_exhaust.run_length + room.bath_exhaust.outlet.width;
        const diameter = 2 * duct.assumed_width_m * duct.assumed_height_m /
          (duct.assumed_width_m + duct.assumed_height_m);
        const dynamic = 0.5 * a.air_density_kg_m3 * duct.velocity_at_target_mps ** 2;
        const straight = a.darcy_factor * length / diameter * dynamic;
        const bends = a.bend_count * a.bend_k * dynamic;
        const outlet = a.outlet_k * dynamic;
        const budget = straight + bends + outlet + a.reserve_pa;
        assert.ok(Math.abs(p.assumed_straight_length_m - length) < 1e-7);
        assert.ok(Math.abs(p.assumed_hydraulic_diameter_m - diameter) < 1e-7);
        assert.ok(Math.abs(p.assumed_dynamic_pressure_pa - dynamic) < 1e-7);
        assert.ok(Math.abs(p.assumed_straight_loss_pa - straight) < 1e-7);
        assert.ok(Math.abs(p.assumed_bend_loss_pa - bends) < 1e-7);
        assert.ok(Math.abs(p.assumed_outlet_loss_pa - outlet) < 1e-7);
        assert.ok(Math.abs(p.assumed_total_pa - budget) < 1e-7);
        assert.ok(budget <= reference.reference_pressure_pa + 1e-7);
        const capacity = reference.free_air_flow_m3h +
          (reference.reference_flow_m3h - reference.free_air_flow_m3h) *
          budget / reference.reference_pressure_pa;
        assert.ok(Math.abs(reference.assumed_linear_capacity_at_budget_m3h - capacity) < 1e-7);
        assert.ok(capacity + 1e-7 >= flow);
        assert.ok(alt.wall_zones.some((wall) => wall.x <= room.bath_exhaust.outlet.x &&
          wall.x + wall.width >= room.bath_exhaust.outlet.x + room.bath_exhaust.outlet.width));
      } else {
        assert.equal(room.bath_exhaust, null);
        assert.equal(room.bath_airflow, null);
        assert.equal(room.bath_pressure, null);
      }
    }
    assert.equal(alt.decisions.length, alt.rooms.length + 3 + 3 * alt.rooms.filter((room) => room.type === 'bathroom').length);
    assert.equal(alt.decisions.filter((decision) => decision.rule.includes('.bath_airflow@')).length, 2);
    assert.equal(alt.decisions.filter((decision) => decision.rule.includes('.bath_pressure@')).length, 2);
  }
});

test('infeasible and malformed requests never return a plan', () => {
  const tiny = req();
  tiny.site.width = 7;
  tiny.site.depth = 9;
  const result = JSON.parse(generate(tiny));
  assert.equal(result.status, 'infeasible');
  assert.deepEqual(result.project_context, tiny.project_context);
  assert.equal(result.applicability.status, 'not_evaluated');
  checkRejections(result);
  assert.equal(result.generated, 0);
  assert.deepEqual(result.rejection_summary, []);
  assert.deepEqual(result.alternatives, []);
  const blocked = req();
  blocked.rules.doors.bathroom = 2;
  const doors = JSON.parse(generate(blocked));
  assert.equal(doors.status, 'infeasible');
  assert.deepEqual(doors.alternatives, []);
  const fake = req();
  fake.rules.regulatory_status = 'certified';
  const error = JSON.parse(generate(fake));
  assert.equal(error.status, 'error');
  checkRejections(error);
  assert.deepEqual(error.alternatives, []);
  const missingWalls = req();
  delete missingWalls.rules.walls;
  assert.equal(JSON.parse(generate(missingWalls)).status, 'error');
  const missingFurniture = req();
  delete missingFurniture.rules.furnishings;
  assert.equal(JSON.parse(generate(missingFurniture)).status, 'error');
  const hugeBed = req();
  hugeBed.rules.furnishings.bed.width = 4.0;
  const noFit = JSON.parse(generate(hugeBed));
  assert.equal(noFit.status, 'infeasible');
  assert.deepEqual(noFit.alternatives, []);
  assert.ok(noFit.reasons.some((reason) => reason.includes('equipamiento')));
  const missingExhaust = req();
  delete missingExhaust.rules.bath_exhaust;
  assert.equal(JSON.parse(generate(missingExhaust)).status, 'error');
  const missingAirflow = req();
  delete missingAirflow.rules.bath_airflow;
  assert.equal(JSON.parse(generate(missingAirflow)).status, 'error');
  const unknownAirflow = req();
  unknownAirflow.rules.bath_airflow.certified_flow = true;
  assert.equal(JSON.parse(generate(unknownAirflow)).status, 'error');
  const missingPressure = req();
  delete missingPressure.rules.bath_pressure;
  assert.equal(JSON.parse(generate(missingPressure)).status, 'error');
  const fakeCurve = req();
  fakeCurve.rules.bath_pressure.verified_curve = true;
  assert.equal(JSON.parse(generate(fakeCurve)).status, 'error');
  const badPair = req();
  badPair.rules.bath_pressure.fan_reference_flow_m3h = rules.bath_airflow.fan_free_air_rating;
  assert.equal(JSON.parse(generate(badPair)).status, 'error');
  const fractionalBends = req();
  fractionalBends.rules.bath_pressure.assumed_bend_count = 2.5;
  assert.equal(JSON.parse(generate(fractionalBends)).status, 'error');
  const blockedExhaust = req();
  blockedExhaust.rules.bath_exhaust.route_band = 0.4;
  const noOutlet = JSON.parse(generate(blockedExhaust));
  assert.equal(noOutlet.status, 'infeasible');
  assert.deepEqual(noOutlet.alternatives, []);
  assert.ok(noOutlet.reasons.some((reason) => reason.includes('extracción')));
  const tooLong = req();
  tooLong.rules.bath_exhaust.max_run = 0.5;
  assert.equal(JSON.parse(generate(tooLong)).status, 'infeasible');
  for (const [field, value] of [
    ['fan_free_air_rating', 10],
    ['max_transfer_velocity', 0.2],
    ['max_duct_velocity', 0.2],
  ]) {
    const blockedAirflow = req();
    blockedAirflow.rules.bath_airflow[field] = value;
    if (field === 'fan_free_air_rating') blockedAirflow.rules.bath_pressure.fan_reference_flow_m3h = 5;
    const infeasible = JSON.parse(generate(blockedAirflow));
    assert.equal(infeasible.status, 'infeasible', field);
    assert.deepEqual(infeasible.alternatives, []);
    assert.ok(infeasible.reasons.some((reason) => reason.includes('predimensionado nominal')));
  }
  const noHeadroom = req();
  noHeadroom.rules.bath_airflow.min_headroom = 2.4;
  assert.equal(JSON.parse(generate(noHeadroom)).status, 'error');
  const beyondSpan = req();
  beyondSpan.rules.bath_pressure.fan_reference_pressure_pa = 10;
  const noInterpolation = JSON.parse(generate(beyondSpan));
  assert.equal(noInterpolation.status, 'infeasible');
  checkRejections(noInterpolation);
  assert.equal(noInterpolation.generated, 48);
  assert.deepEqual(noInterpolation.alternatives, []);
  assert.ok(noInterpolation.reasons.some((reason) => reason.includes('no se extrapola')));
  const tooWeakAtPressure = req();
  tooWeakAtPressure.rules.bath_pressure.fan_reference_flow_m3h = 1;
  tooWeakAtPressure.rules.bath_pressure.fan_reference_pressure_pa = 25;
  const noCapacity = JSON.parse(generate(tooWeakAtPressure));
  assert.equal(noCapacity.status, 'infeasible');
  checkRejections(noCapacity);
  assert.deepEqual(noCapacity.alternatives, []);
  assert.ok(noCapacity.reasons.some((reason) => reason.includes('capacidad de referencia')));
});

test('impossible bath window targets reject plans; zero target preserves explicit windowless mode', () => {
  const impossible = req(); impossible.rules.spaces.bathroom.window_ratio = 0.5;
  const rejected = JSON.parse(generate(impossible));
  assert.equal(rejected.status, 'infeasible');
  checkRejections(rejected);
  assert.deepEqual(rejected.alternatives, []);
  assert.ok(rejected.reasons.some((reason) => reason.includes('ventana')));
  assert.equal(rejected.applicability.daylight_status, 'not_evaluated');
  const windowless = req(); windowless.rules.spaces.bathroom.window_ratio = 0;
  const drawn = JSON.parse(generate(windowless));
  assert.equal(drawn.status, 'ok');
  assert.notEqual(drawn.input_hash, JSON.parse(generate(req())).input_hash);
  for (const room of drawn.alternatives[0].rooms.filter((r) => r.type === 'bathroom')) {
    assert.equal(room.window, null);
    assert.equal(room.window_geometry_status, 'not_drawn');
    assert.equal(room.daylight_status, 'not_evaluated');
  }
});

test('a voluntary site sketch filters gross footprints and never becomes a verified legal setback', () => {
  const original = JSON.parse(generate(req()));
  const partial = req();
  partial.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }];
  const result = JSON.parse(generate(partial));
  assert.equal(result.status, 'ok');
  assert.notEqual(result.input_hash, original.input_hash);
  assert.equal(result.generated, 48);
  assert.ok(result.rejected > 0 && result.rejected < 48);
  checkRejections(result);
  assert.equal(result.site_reservations.provenance, 'user_sketch_unverified');
  assert.equal(result.site_reservations.geometry_status, 'footprint_exclusion_2d_only');
  assert.deepEqual(result.site_reservations.areas, partial.site.reserved_areas);
  assert.ok(Math.abs(result.site.unreserved_buildable_area -
    (result.site.buildable.width * result.site.buildable.depth - 4)) < 1e-7);
  assert.equal(result.applicability.status, 'not_evaluated');
  const zone = partial.site.reserved_areas[0];
  const overlaps = (rect) => rect.x < zone.x + zone.width - 1e-7 &&
    zone.x < rect.x + rect.width - 1e-7 && rect.y < zone.y + zone.depth - 1e-7 &&
    zone.y < rect.y + rect.depth - 1e-7;
  for (const alt of result.alternatives) {
    assert.equal(overlaps(alt.corridor), false);
    assert.ok(alt.rooms.every((room) => !overlaps(room.rect)));
    assert.match(alt.svg, /class="site-reserved-area"/);
    assert.match(alt.svg, /CROQUIS 2D NO VERIFICADO/);
    assert.ok(alt.decisions.some(({ rule }) => rule === 'site.reserved_areas@user_sketch_unverified'));
  }
  const blocked = req(); blocked.site.reserved_areas = [{ x: 8, y: 3, width: 2, depth: 3 }];
  const infeasible = JSON.parse(generate(blocked));
  assert.equal(infeasible.status, 'infeasible');
  assert.equal(infeasible.generated, 48);
  assert.deepEqual(infeasible.alternatives, []);
  assert.ok(infeasible.reasons.some((reason) => reason.includes('reserva voluntaria')));
  assert.deepEqual(infeasible.site_reservations.areas, blocked.site.reserved_areas);
  const invalid = req(); invalid.site.reserved_areas = [{ x: 17.9, y: 3, width: 1, depth: 1 }];
  assert.equal(JSON.parse(generate(invalid)).status, 'error');
  invalid.site.reserved_areas = [];
  invalid.site.reservation_provenance = 'official_legal_setback';
  assert.equal(JSON.parse(generate(invalid)).status, 'error');
});

test('WASM verifies two disjoint zones with exact area and full-width route checks', () => {
  const input = req();
  input.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
    { x: 14, y: 16, width: 1, depth: 2 }];
  const result = JSON.parse(generate(input));
  assert.equal(result.status, 'ok');
  assert.equal(result.site.unreserved_buildable_area,
    result.site.buildable.width * result.site.buildable.depth - 6);
  assert.deepEqual(result.site_reservations.areas, input.site.reserved_areas);
  assert.equal(result.alternatives[0].decisions.filter(({ rule }) =>
    rule === 'site.reserved_areas@user_sketch_unverified').length, 2);
  assert.equal((result.alternatives[0].svg.match(/class="site-reserved-area"/g) || []).length, 2);
  const tangent = req();
  tangent.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
    { x: 6.5, y: 12, width: 1, depth: 1 }];
  assert.notEqual(JSON.parse(generate(tangent)).status, 'error');
  tangent.site.reserved_areas[1].x -= 1e-8;
  const overlap = JSON.parse(generate(tangent));
  assert.equal(overlap.status, 'error');
  assert.equal(overlap.site_reservations, undefined);
  const second = req();
  second.site.reserved_areas = [{ x: 0, y: 0, width: 1, depth: 1 },
    { x: 8.5, y: 0.5, width: 1, depth: 0.5 }];
  assert.equal(JSON.parse(generate(second)).status, 'infeasible');
  second.site.front_approach = { provenance: 'user_sketch_unverified',
    shape: 'orthogonal_front_detour', width: 1.2, front_x: 11.5, turn_y: 1.6 };
  const detour = JSON.parse(generate(second));
  assert.equal(detour.status, 'ok');
  assert.equal(detour.alternatives[0].front_approach.segments.length, 3);
  assert.deepEqual(detour.site_reservations.areas, second.site.reserved_areas);
});

test('a self-reported rear-corner L plot excludes only outside 2D ground, not legal setbacks', () => {
  const original = JSON.parse(generate(req()));
  const notch = { side: 'left', width: 4, depth: 10 };
  const input = req();
  input.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_corner_notch', rear_notches: [notch] };
  const result = JSON.parse(generate(input));
  assert.equal(result.status, 'ok');
  assert.notEqual(result.input_hash, original.input_hash);
  assert.equal(result.generated, 48);
  assert.equal(result.rejected, 9);
  assert.equal(result.alternatives.length, 3);
  assert.equal(result.site.plot_area, input.site.width * input.site.depth - notch.width * notch.depth);
  assert.equal(result.site.max_built_area, result.site.plot_area * input.rules.max_far);
  assert.equal(result.site.unreserved_buildable_area, 222);
  assert.equal(result.site_plot.provenance, 'user_sketch_unverified');
  assert.equal(result.site_plot.geometry_status, 'orthogonal_plot_sketch_2d_only');
  assert.equal(result.site_plot.shape, 'rear_corner_notch');
  assert.deepEqual(result.site_plot.rear_notches, [notch]);
  assert.deepEqual(result.site_plot.vertices,
    [{ x: 0, y: 0 }, { x: 18, y: 0 }, { x: 18, y: 22 },
      { x: 4, y: 22 }, { x: 4, y: 12 }, { x: 0, y: 12 }]);
  assert.ok(result.rejection_summary.some((item) => item.reason.includes('recorte posterior')));
  const cut = { x: 0, y: 12, width: notch.width, depth: notch.depth };
  const collides = (r) => r.x < cut.x + cut.width - 1e-7 && cut.x < r.x + r.width - 1e-7 &&
    r.y < cut.y + cut.depth - 1e-7 && cut.y < r.y + r.depth - 1e-7;
  for (const alt of result.alternatives) {
    assert.equal(collides(alt.corridor), false);
    assert.ok(alt.rooms.every((room) => !collides(room.rect)));
    assert.ok(alt.wall_zones.every((wall) => !collides(wall)));
    assert.match(alt.svg, /class="site-plot-outline"/);
    assert.match(alt.svg, /clip-path="url\(#site-plot-clip\)"/);
    assert.match(alt.svg, /FUERA DEL CROQUIS/);
    assert.match(alt.svg, /RETIROS DEL ENTRANTE NO EVALUADOS/);
    assert.ok(alt.decisions.some(({ rule }) => rule === 'site.plot_outline@user_sketch_unverified'));
    assert.ok(alt.warnings.some((note) => note.includes('NO un levantamiento de linderos')));
  }
  assert.equal(result.applicability.status, 'not_evaluated');
  const flipped = req();
  flipped.site.plot_outline = { ...input.site.plot_outline, rear_notches: [{ ...notch, side: 'right' }] };
  const right = JSON.parse(generate(flipped));
  assert.equal(right.status, 'ok');
  assert.notEqual(right.input_hash, result.input_hash);
  assert.equal(right.site.plot_area, result.site.plot_area);
  assert.equal(right.rejected, result.rejected);
  assert.deepEqual(right.site_plot.vertices,
    [{ x: 0, y: 0 }, { x: 18, y: 0 }, { x: 18, y: 12 },
      { x: 14, y: 12 }, { x: 14, y: 22 }, { x: 0, y: 22 }]);
  const blocked = req();
  blocked.site.plot_outline = { ...input.site.plot_outline,
    rear_notches: [{ side: 'right', width: 7, depth: 12 }] };
  const infeasible = JSON.parse(generate(blocked));
  assert.equal(infeasible.status, 'infeasible');
  assert.equal(infeasible.generated, 48);
  assert.deepEqual(infeasible.alternatives, []);
  assert.equal(infeasible.site_plot.shape, 'rear_corner_notch');
  assert.ok(infeasible.reasons.some((reason) => reason.includes('recorte posterior')));
  const consumed = req(); consumed.site.plot_outline = { ...input.site.plot_outline,
    rear_notches: [{ side: 'left', width: 17, depth: 21 }] };
  const zero = JSON.parse(generate(consumed));
  assert.equal(zero.status, 'infeasible');
  assert.equal(zero.generated, 0);
  assert.deepEqual(zero.alternatives, []);
  const invalid = req(); invalid.site.plot_outline = { ...input.site.plot_outline,
    rear_notches: [{ side: 'left', width: 18, depth: 3 }] };
  assert.equal(JSON.parse(generate(invalid)).status, 'error');
  const overlap = req(); overlap.site.plot_outline = structuredClone(input.site.plot_outline);
  overlap.site.reserved_areas = [{ x: 1, y: 18, width: 2, depth: 2 }];
  assert.equal(JSON.parse(generate(overlap)).status, 'error');
  overlap.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }];
  assert.equal(JSON.parse(generate(overlap)).site.unreserved_buildable_area, 218);
});

test('WASM validates two opposite rear cut-outs as an eight-vertex sketch without double subtraction', () => {
  const first = { side: 'left', width: 4, depth: 10 };
  const second = { side: 'right', width: 3, depth: 10 };
  const input = req();
  input.site.plot_outline = { provenance: 'user_sketch_unverified',
    shape: 'rear_both_corners_notched', rear_notches: [first, second] };
  const result = JSON.parse(generate(input));
  assert.equal(result.status, 'ok');
  assert.equal(result.site.plot_area, 326);
  assert.equal(result.site.unreserved_buildable_area, 214);
  assert.equal(result.site.max_built_area, 326 * input.rules.max_far);
  assert.deepEqual(result.site_plot.rear_notches, [first, second]);
  assert.deepEqual(result.site_plot.vertices,
    [{ x: 0, y: 0 }, { x: 18, y: 0 }, { x: 18, y: 12 }, { x: 15, y: 12 },
      { x: 15, y: 22 }, { x: 4, y: 22 }, { x: 4, y: 12 }, { x: 0, y: 12 }]);
  for (const alt of result.alternatives) {
    const outside = [{ x: 0, y: 12, width: 4, depth: 10 },
      { x: 15, y: 12, width: 3, depth: 10 }];
    const overlaps = (r, cut) => Math.max(0, Math.min(r.x + r.width, cut.x + cut.width) - Math.max(r.x, cut.x)) *
      Math.max(0, Math.min(r.y + r.depth, cut.y + cut.depth) - Math.max(r.y, cut.y));
    for (const cut of outside) for (const gross of [alt.corridor, ...alt.rooms.map((room) => room.rect), ...alt.wall_zones]) {
      assert.equal(overlaps(gross, cut), 0);
    }
    assert.equal((alt.svg.match(/FUERA DEL CROQUIS/g) || []).length, 2);
    assert.match(alt.svg, /DOS RECORTES.*NO VERIFICADOS/);
    assert.equal(alt.decisions.filter(({ rule }) => rule === 'site.plot_outline@user_sketch_unverified').length, 2);
  }
  const all = req(); all.site.plot_outline = structuredClone(input.site.plot_outline);
  all.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
    { x: 14, y: 16, width: 1, depth: 2 }];
  const combined = JSON.parse(generate(all));
  assert.equal(combined.status, 'ok');
  assert.equal(combined.site.unreserved_buildable_area, 208);
  assert.equal(combined.rejected, 40);
  assert.equal(combined.site_reservations.areas.length, 2);
  const reverse = req(); reverse.site.plot_outline = { ...input.site.plot_outline, rear_notches: [second, first] };
  const reordered = JSON.parse(generate(reverse));
  assert.equal(reordered.status, 'ok');
  assert.notEqual(reordered.input_hash, result.input_hash);
  assert.deepEqual(reordered.site_plot.vertices, result.site_plot.vertices);
  const touching = req(); touching.site.plot_outline = structuredClone(input.site.plot_outline);
  touching.site.reserved_areas = [{ x: 14, y: 16, width: 1, depth: 2 }];
  assert.notEqual(JSON.parse(generate(touching)).status, 'error');
  touching.site.reserved_areas[0].width += 1e-8;
  const overlap = JSON.parse(generate(touching));
  assert.equal(overlap.status, 'error');
  assert.equal(overlap.site_plot, undefined);
  const wrongSide = req(); wrongSide.site.plot_outline = {
    ...input.site.plot_outline, rear_notches: [first, first],
  };
  assert.equal(JSON.parse(generate(wrongSide)).status, 'error');
  const tooNarrow = req(); tooNarrow.site.plot_outline = { ...input.site.plot_outline,
    rear_notches: [{ side: 'left', width: 10.00000001, depth: 10 },
      { side: 'right', width: 7, depth: 9 }] };
  assert.equal(JSON.parse(generate(tooNarrow)).status, 'error');
  const blocked = req(); blocked.site.plot_outline = { ...input.site.plot_outline,
    rear_notches: [{ side: 'left', width: 1, depth: 1 },
      { side: 'right', width: 10.2, depth: 21 }] };
  const infeasible = JSON.parse(generate(blocked));
  assert.equal(infeasible.status, 'infeasible');
  assert.equal(infeasible.rejected, 48);
  assert.deepEqual(infeasible.alternatives, []);
  assert.equal(infeasible.site_plot.vertices.length, 8);
});

test('editable hypotheses change the hash; partial rejections remain visible next to valid plans', () => {
  const baseline = JSON.parse(generate(req()));
  for (const [key, value] of [
    ['fan_reference_pressure_pa', 80],
    ['fan_reference_flow_m3h', 20],
    ['assumed_reserve_pa', 30],
  ]) {
    const input = req();
    input.rules.bath_pressure[key] = value;
    const text = generate(input);
    const result = JSON.parse(text);
    checkRejections(result);
    assert.notEqual(result.input_hash, baseline.input_hash, key);
    assert.equal(generate(input), text, `salida determinista: ${key}`);
    assert.equal(result.status, 'ok', key);
    for (const alt of result.alternatives) for (const room of alt.rooms.filter((r) => r.type === 'bathroom')) {
      const scenario = room.bath_pressure;
      assert.equal(scenario.delivered_flow_status, 'not_evaluated');
      const actual = key === 'fan_reference_pressure_pa' ? scenario.fan_reference.reference_pressure_pa :
        key === 'fan_reference_flow_m3h' ? scenario.fan_reference.reference_flow_m3h : scenario.assumptions.reserve_pa;
      assert.equal(actual, value);
    }
    if (key === 'fan_reference_flow_m3h') {
      assert.equal(result.generated, 48);
      assert.equal(result.rejected, 12);
      assert.ok(result.rejection_summary.some(({ reason }) => reason.includes('presión')));
      assert.equal(result.alternatives.length, 3);
    }
  }
  assert.equal(rules.bath_pressure.fan_reference_flow_m3h, 90);
});

test('WASM versioned self-report affects the hash but cannot assert legal scope or ventilation', () => {
  const baseline = JSON.parse(generate(req()));
  const claimed = req();
  Object.assign(claimed.project_context, {
    jurisdiction: 'CU', housing_class: 'urban_social', occupants: 4, accessibility_needs: 'declared',
  });
  const result = JSON.parse(generate(claimed));
  assert.equal(result.status, 'ok');
  assert.notEqual(result.input_hash, baseline.input_hash);
  assert.equal(result.generated, baseline.generated);
  assert.deepEqual(result.project_context, claimed.project_context);
  assert.equal(result.applicability.declared_scope, 'candidate_from_self_report_only');
  assert.deepEqual(result.applicability.missing_context, []);
  for (const field of ['status', 'daylight_status', 'ventilation_status']) {
    assert.equal(result.applicability[field], 'not_evaluated');
  }
  for (const [key, value] of [['jurisdiction', 'outside_CU'], ['housing_class', 'other'],
    ['occupants', 1], ['accessibility_needs', 'none_declared']]) {
    const changed = req(); changed.project_context[key] = value;
    assert.notEqual(JSON.parse(generate(changed)).input_hash, baseline.input_hash, key);
    assert.equal(JSON.parse(generate(changed)).applicability.declared_scope, 'undetermined');
  }
  const forged = req(); forged.project_context.provenance = 'official';
  assert.equal(JSON.parse(generate(forged)).status, 'error');
  const legacy = req(); delete legacy.request_schema;
  const error = JSON.parse(generate(legacy));
  assert.equal(error.status, 'error');
  assert.match(error.message, /request_schema/);
  assert.equal('applicability' in error, false);
});

test('WASM buffers can be freed and reused across sessions', () => {
  for (let i = 0; i < 50; i += 1) {
    const input = req();
    input.seed = i;
    assert.equal(JSON.parse(generate(input)).status, 'ok');
  }
});

test('CLI and WASM are byte-identical for site sketches, windows, pressure and context', async () => {
  const folder = await mkdtemp(resolve(tmpdir(), 'arqgen-parity-'));
  try {
    for (const scenario of ['demo', 'site_reservation_partial', 'site_reservation_blocked',
      'site_reservation_invalid', 'L_left_partial', 'L_right_blocked', 'L_invalid', 'L_reserved',
      'front_blocked', 'front_touch', 'front_wide', 'front_invalid', 'front_notch', 'front_zero',
      'front_detour', 'front_detour_blocked', 'front_detour_invalid', 'front_detour_nospace',
      'zones_double_ok', 'zones_overlap', 'zones_second_front_block', 'zones_detour',
      'U_both_ok', 'U_blocked', 'U_invalid_gap', 'U_reserved', 'U_reordered', 'U_all_exclusions',
      'bath_window_disabled', 'bath_window_impossible',
      'pressure_partial', 'reserve_adjusted', 'airflow_infeasible',
      'pressure_no_extrapolation', 'pressure_weak_point', 'invalid_pair',
      'context_cu_candidate', 'context_not_cu', 'invalid_context']) {
      const input = req();
      if (scenario === 'site_reservation_partial') {
        input.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }];
      } else if (scenario === 'site_reservation_blocked') {
        input.site.reserved_areas = [{ x: 8, y: 3, width: 2, depth: 3 }];
      } else if (scenario === 'site_reservation_invalid') {
        input.site.reserved_areas = [{ x: 17.9, y: 3, width: 1, depth: 1 }];
      } else if (scenario === 'zones_double_ok') {
        input.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
          { x: 14, y: 16, width: 1, depth: 2 }];
      } else if (scenario === 'zones_overlap') {
        input.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
          { x: 6.49999999, y: 12, width: 1, depth: 1 }];
      } else if (['zones_second_front_block', 'zones_detour'].includes(scenario)) {
        input.site.reserved_areas = [{ x: 0, y: 0, width: 1, depth: 1 },
          { x: 8.5, y: 0.5, width: 1, depth: 0.5 }];
        if (scenario === 'zones_detour') input.site.front_approach = {
          provenance: 'user_sketch_unverified', shape: 'orthogonal_front_detour',
          width: 1.2, front_x: 11.5, turn_y: 1.6 };
      } else if (scenario.startsWith('U_')) {
        const left = { side: 'left', width: scenario === 'U_invalid_gap' ? 10.00000001 :
          scenario === 'U_blocked' ? 1 : 4, depth: scenario === 'U_blocked' ? 1 : 10 };
        const right = { side: 'right', width: scenario === 'U_invalid_gap' ? 7 :
          scenario === 'U_blocked' ? 10.2 : 3, depth: scenario === 'U_blocked' ? 21 : 10 };
        input.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_both_corners_notched',
          rear_notches: scenario === 'U_reordered' ? [right, left] : [left, right] };
        if (scenario === 'U_reserved') input.site.reserved_areas = [{ x: 14, y: 16, width: 1, depth: 2 }];
        if (scenario === 'U_all_exclusions') input.site.reserved_areas = [
          { x: 4.5, y: 12, width: 2, depth: 2 }, { x: 14, y: 16, width: 1, depth: 2 },
        ];
      } else if (['L_left_partial', 'L_right_blocked', 'L_invalid', 'L_reserved'].includes(scenario)) {
        input.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_corner_notch',
          rear_notches: [{ side: scenario === 'L_right_blocked' ? 'right' : 'left',
            width: scenario === 'L_invalid' ? 18 : scenario === 'L_right_blocked' ? 7 : 4,
            depth: scenario === 'L_right_blocked' ? 12 : 10 }] };
        if (scenario === 'L_reserved') {
          input.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }];
        }
      } else if (['front_blocked', 'front_touch', 'front_wide'].includes(scenario)) {
        input.site.reserved_areas = [{ x: scenario === 'front_touch' ? 9.6 : scenario === 'front_wide' ? 7 : 8.5,
          y: 1, width: 1, depth: 1 }];
        if (scenario === 'front_wide') input.site.front_approach.width = 4;
      } else if (scenario === 'front_invalid') {
        input.site.front_approach.provenance = 'official_right_of_way';
      } else if (scenario === 'front_notch') {
        input.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_corner_notch',
          rear_notches: [{ side: 'right', width: 10.2, depth: 21 }] };
      } else if (scenario === 'front_zero') {
        input.rules.setbacks.front = 0;
      } else if (scenario.startsWith('front_detour')) {
        input.site.front_approach = { provenance: 'user_sketch_unverified',
          shape: 'orthogonal_front_detour', width: 1.2,
          front_x: scenario === 'front_detour_invalid' ? 0.1 : 11.5, turn_y: 1.6 };
        input.site.reserved_areas = [{ x: 8.5,
          y: scenario === 'front_detour_blocked' ? 1 : 0.5, width: 1,
          depth: scenario === 'front_detour_blocked' ? 1 : 0.5 }];
        if (scenario === 'front_detour_nospace') input.rules.setbacks.front = 0;
      } else if (scenario === 'bath_window_disabled') {
        input.rules.spaces.bathroom.window_ratio = 0;
      } else if (scenario === 'bath_window_impossible') {
        input.rules.spaces.bathroom.window_ratio = 0.5;
      } else if (scenario === 'pressure_partial') {
        input.rules.bath_pressure.fan_reference_flow_m3h = 20;
      } else if (scenario === 'reserve_adjusted') {
        input.rules.bath_pressure.assumed_reserve_pa = 30;
      } else if (scenario === 'airflow_infeasible') {
        input.rules.bath_airflow.fan_free_air_rating = 10;
        input.rules.bath_pressure.fan_reference_flow_m3h = 5;
      } else if (scenario === 'pressure_no_extrapolation') {
        input.rules.bath_pressure.fan_reference_pressure_pa = 10;
      } else if (scenario === 'pressure_weak_point') {
        input.rules.bath_pressure.fan_reference_pressure_pa = 25;
        input.rules.bath_pressure.fan_reference_flow_m3h = 1;
      } else if (scenario === 'invalid_pair') {
        input.rules.bath_pressure.fan_reference_flow_m3h = 120;
      } else if (scenario === 'context_cu_candidate') {
        Object.assign(input.project_context, { jurisdiction: 'CU', housing_class: 'urban_social',
          occupants: 4, accessibility_needs: 'declared' });
      } else if (scenario === 'context_not_cu') {
        Object.assign(input.project_context, { jurisdiction: 'outside_CU', housing_class: 'other',
          occupants: 2, accessibility_needs: 'none_declared' });
      } else if (scenario === 'invalid_context') {
        input.project_context.provenance = 'official_verified';
      }
      const rulesPath = resolve(folder, 'rules.json');
      const briefPath = resolve(folder, 'brief.json');
      const brief = structuredClone(input);
      delete brief.rules;
      await writeFile(rulesPath, JSON.stringify(input.rules));
      await writeFile(briefPath, JSON.stringify(brief));
      const cli = spawnSync('cargo', [
        'run', '--offline', '--quiet', '-p', 'arqgen-core', '--bin', 'arqgen', '--',
        briefPath, '--rules', rulesPath,
      ], { cwd: root, encoding: 'utf8' });
      assert.equal(cli.error, undefined, String(cli.error));
      assert.equal(cli.status, ['demo', 'site_reservation_partial', 'L_left_partial', 'L_reserved',
        'front_touch', 'front_zero', 'front_detour', 'zones_double_ok', 'zones_detour',
        'U_both_ok', 'U_reserved', 'U_reordered', 'U_all_exclusions',
        'bath_window_disabled', 'pressure_partial', 'reserve_adjusted',
        'context_cu_candidate', 'context_not_cu'].includes(scenario) ? 0 : 1, cli.stderr);
      const output = generate(input);
      checkRejections(JSON.parse(output));
      assert.equal(cli.stdout.trimEnd(), output, `desacuerdo CLI/WASM en ${scenario}`);
    }
  } finally {
    await rm(folder, { recursive: true, force: true });
  }
});

test('WASM front strip filters only the declared 2D route; boundary touch and zero setback are explicit', () => {
  const baseline = JSON.parse(generate(req()));
  const blocked = req();
  blocked.site.reserved_areas = [{ x: 8.5, y: 1, width: 1, depth: 1 }];
  const infeasible = JSON.parse(generate(blocked));
  assert.equal(infeasible.status, 'infeasible');
  assert.equal(infeasible.generated, 48);
  assert.equal(infeasible.rejected, 48);
  assert.deepEqual(infeasible.alternatives, []);
  assert.equal(infeasible.rejection_summary.length, 1);
  assert.match(infeasible.rejection_summary[0].reason, /franja frontal recta/);
  assert.equal(infeasible.site_approach.geometry_status, 'declared_front_trace_sketch_2d_only');
  assert.equal(infeasible.site, undefined);
  const tangent = req(); tangent.site.reserved_areas = [{ x: 9.6, y: 1, width: 1, depth: 1 }];
  assert.equal(JSON.parse(generate(tangent)).status, 'ok');
  tangent.site.reserved_areas[0].x = 9.59999999;
  assert.equal(JSON.parse(generate(tangent)).status, 'infeasible');
  const inset = req(); inset.site.plot_outline = { provenance: 'user_sketch_unverified',
    shape: 'rear_corner_notch', rear_notches: [{ side: 'left', width: 10.2, depth: 21 }] };
  const noRoute = JSON.parse(generate(inset));
  assert.equal(noRoute.status, 'infeasible');
  assert.ok(noRoute.rejection_summary.some(({ reason }) => reason.includes('franja frontal recta sale del croquis')));
  const wider = req(); wider.site.front_approach.width = 1.5;
  const widthResult = JSON.parse(generate(wider));
  assert.equal(widthResult.status, 'ok');
  assert.notEqual(widthResult.input_hash, baseline.input_hash);
  assert.equal(widthResult.alternatives[0].front_approach.segments[0].width, 1.5);
  const zero = req(); zero.rules.setbacks.front = 0;
  const frontDoor = JSON.parse(generate(zero));
  assert.equal(frontDoor.status, 'ok');
  assert.deepEqual(frontDoor.alternatives[0].front_approach.segments, []);
  assert.equal(frontDoor.alternatives[0].front_approach.geometry_status, 'door_at_front_boundary_2d_only');
  assert.match(frontDoor.alternatives[0].svg, /class="front-approach-contact"/);
  const bad = req(); bad.site.front_approach.provenance = 'surveyed_easement';
  const error = JSON.parse(generate(bad));
  assert.equal(error.status, 'error');
  assert.equal(error.site_approach, undefined);
});

test('WASM lets a declared two-turn band clear only the drawn obstacle, never an invented access', () => {
  const input = req();
  input.site.reserved_areas = [{ x: 8.5, y: 0.5, width: 1, depth: 0.5 }];
  const noStraight = JSON.parse(generate(input));
  assert.equal(noStraight.status, 'infeasible');
  input.site.front_approach = { provenance: 'user_sketch_unverified',
    shape: 'orthogonal_front_detour', width: 1.2, front_x: 11.5, turn_y: 1.6 };
  Object.assign(input.project_context, { jurisdiction: 'CU', housing_class: 'urban_social',
    occupants: 4, accessibility_needs: 'declared' });
  const result = JSON.parse(generate(input));
  assert.equal(result.status, 'ok');
  assert.equal(result.generated, 48);
  assert.equal(result.rejected, 0);
  assert.notEqual(result.input_hash, noStraight.input_hash);
  assert.equal(result.applicability.status, 'not_evaluated');
  assert.deepEqual([result.site_approach.street_connection_status,
    result.site_approach.right_of_way_status, result.site_approach.accessibility_status],
  ['not_evaluated', 'not_evaluated', 'not_evaluated']);
  for (const alt of result.alternatives) {
    assert.equal(alt.front_approach.geometry_status,
      'orthogonal_detour_clear_of_declared_exclusions_2d_only');
    assert.deepEqual(alt.front_approach.segments, [
      { x: 10.9, y: 0, width: 1.2, depth: 1.6 },
      { x: 9, y: 1, width: 2.5, depth: 1.2 },
      { x: 8.4, y: 1.6, width: 1.2, depth: 1.4 },
    ]);
    assert.deepEqual(alt.front_approach.turns,
      [{ x: 11.5, y: 1.6 }, { x: 9, y: 1.6 }]);
    assert.equal((alt.svg.match(/class="front-approach-strip"/g) || []).length, 3);
    assert.match(alt.svg, /RODEO FRONTAL ≠ ACCESO REAL/);
    assert.equal(alt.bathroom_ventilation_status, 'not_evaluated');
  }
  input.site.front_approach.turn_y = 1.59999999;
  const tinyCrossing = JSON.parse(generate(input));
  assert.equal(tinyCrossing.status, 'infeasible');
  assert.equal(tinyCrossing.rejected, 48);
  assert.deepEqual(tinyCrossing.alternatives, []);
  const zero = req(); zero.rules.setbacks.front = 0;
  zero.site.front_approach = { provenance: 'user_sketch_unverified',
    shape: 'orthogonal_front_detour', width: 1.2, front_x: 11.5, turn_y: 1.6 };
  assert.equal(JSON.parse(generate(zero)).status, 'infeasible');
  zero.site.front_approach.front_x = 0.1;
  const error = JSON.parse(generate(zero));
  assert.equal(error.status, 'error');
  assert.equal(error.site_approach, undefined);
});

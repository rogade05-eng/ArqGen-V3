import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { reviewSanitaryScope, describeDeclaredContext } from '../src/source-review.js';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const sources = JSON.parse(await readFile(resolve(root, 'knowledge/source-manifest.json'), 'utf8'));
const sample = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const rules = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
const { instance } = await WebAssembly.instantiate(await readFile(resolve(root, 'web/public/core.wasm')));
const core = instance.exports;
const input = () => ({ ...structuredClone(sample), rules: structuredClone(rules) });

function generate(request) {
  const bytes = new TextEncoder().encode(JSON.stringify(request));
  const ptr = core.arq_alloc(bytes.length);
  assert.ok(ptr);
  new Uint8Array(core.memory.buffer, ptr, bytes.length).set(bytes);
  let packed;
  try { packed = core.arq_generate(ptr, bytes.length); }
  finally { core.arq_free(ptr, bytes.length); }
  const out = Number(packed & 0xffffffffn);
  const size = Number(packed >> 32n);
  let text;
  try { text = new TextDecoder().decode(new Uint8Array(core.memory.buffer, out, size)); }
  finally { core.arq_free(out, size); }
  return JSON.parse(text);
}

test('real Rust plans count schematic bathroom openings without converting NC 598 into a rule', () => {
  const request = input();
  const result = generate(request);
  assert.equal(result.status, 'ok');
  assert.equal(result.alternatives.length, 3);
  let totalWith = 0;
  for (const alternative of result.alternatives) {
    const review = reviewSanitaryScope(request, result, alternative, sources);
    assert.equal(review.regulatory_status, 'not_evaluated');
    assert.equal(review.daylight_status, 'not_evaluated');
    assert.equal(review.scope, 'undetermined');
    assert.deepEqual(review.approach.segments, [{ x: 8.4, y: 0, width: 1.2, depth: 3 }]);
    assert.deepEqual(review.context, request.project_context);
    assert.deepEqual(review.missing_context,
      ['jurisdiction', 'housing_class', 'occupants', 'accessibility_needs']);
    assert.match(describeDeclaredContext(review), /Cuba es objetivo del inventario/);
    assert.equal(review.source.id, 'NC 598:2009');
    assert.equal(review.source.source_commit, sources.source_commit);
    assert.deepEqual(review.dependencies.map((ref) => ref.id),
      ['NC 337:2004', 'NC 391-1:2004', 'NC 391-2:2004']);
    assert.ok(review.dependencies.every((ref) => ref.status === 'third_party_preview_unverified'));
    assert.equal(review.bathrooms.total, request.program.bathrooms);
    assert.equal(review.bathrooms.with_drawn_window.length, 2);
    assert.equal(review.bathrooms.without_window.length, 0);
    assert.equal(review.bathrooms.unknown.length, 0);
    totalWith += review.bathrooms.with_drawn_window.length;
    assert.equal(result.regulatory_status, 'illustrative_not_certified');
    assert.equal(alternative.bathroom_ventilation_status, 'not_evaluated');
  }
  assert.equal(totalWith, 6);
  assert.equal(request.rules.spaces.bathroom.window_ratio, 0.05); // ilustrativo, NO NC 598
});

test('no feasible alternative means no fabricated room/daylight observation', () => {
  const request = input();
  request.rules.bath_pressure.fan_reference_pressure_pa = 10;
  const result = generate(request);
  assert.equal(result.status, 'infeasible');
  const review = reviewSanitaryScope(request, result, null, sources);
  assert.equal(review.regulatory_status, 'not_evaluated');
  assert.equal(review.bathrooms, null);
  assert.throws(() => reviewSanitaryScope(request, result, { rooms: [] }, sources), /alternativa/);
  assert.throws(() => reviewSanitaryScope(request, { status: 'error' }, null, sources), /entrada/);
});

test('self-reported Cuba and social housing are candidates to STUDY, never automatic legal findings', () => {
  const request = input();
  Object.assign(request.project_context, {
    jurisdiction: 'CU', housing_class: 'urban_social', occupants: 4, accessibility_needs: 'declared',
  });
  const result = generate(request);
  const review = reviewSanitaryScope(request, result, result.alternatives[0], sources);
  assert.equal(review.scope, 'candidate_from_self_report_only');
  assert.deepEqual(review.missing_context, []);
  assert.equal(review.regulatory_status, 'not_evaluated');
  assert.equal(review.ventilation_status, 'not_evaluated');
  assert.match(describeDeclaredContext(review), /posible ámbito a estudiar/);
  assert.match(describeDeclaredContext(review), /NO su aplicabilidad legal/);
  const outside = input();
  Object.assign(outside.project_context, {
    jurisdiction: 'outside_CU', housing_class: 'other', occupants: 2,
    accessibility_needs: 'none_declared',
  });
  const response = generate(outside);
  const report = reviewSanitaryScope(outside, response, response.alternatives[0], sources);
  assert.equal(report.scope, 'undetermined');
  assert.match(describeDeclaredContext(report), /NO equivale a exención/);
  assert.match(describeDeclaredContext(report), /NO implica exención/);
});

test('a drawn opening is not evidence of effective daylight; missing/invalid windows remain unknown', () => {
  const request = input();
  const result = generate(request);
  const altered = structuredClone(result);
  const alt = altered.alternatives[0];
  const [first, second] = alt.rooms.filter((room) => room.type === 'bathroom');
  let review = reviewSanitaryScope(request, altered, alt, sources);
  assert.deepEqual(review.bathrooms.with_drawn_window, [first.id, second.id]);
  assert.equal(review.daylight_status, 'not_evaluated');
  second.window = null; // claim still says drawn: contradictory observation, not proof of absence
  review = reviewSanitaryScope(request, altered, alt, sources);
  assert.deepEqual(review.bathrooms.unknown, [second.id]);
  second.window_geometry_status = 'not_drawn';
  review = reviewSanitaryScope(request, altered, alt, sources);
  assert.deepEqual(review.bathrooms.without_window, [second.id]);
  delete second.window;
  review = reviewSanitaryScope(request, altered, alt, sources);
  assert.deepEqual(review.bathrooms.unknown, [second.id]);
  first.window.opening.width = 0;
  review = reviewSanitaryScope(request, altered, alt, sources);
  assert.equal(review.bathrooms.with_drawn_window.length, 0);
  assert.equal(review.bathrooms.unknown.length, 2);
  first.daylight_status = 'verified';
  assert.throws(() => reviewSanitaryScope(request, altered, alt, sources), /luz natural/);
  assert.throws(() => reviewSanitaryScope(request, altered, structuredClone(alt), sources), /alternativa/);
  alt.rooms.splice(alt.rooms.indexOf(second), 1);
  assert.throws(() => reviewSanitaryScope(request, altered, alt, sources), /número de baños/);
});

test('untrusted editions, executable sources and unversioned project context fail closed', () => {
  const request = input();
  const result = generate(request);
  const alt = result.alternatives[0];
  const tamper = (change) => {
    const manifest = structuredClone(sources);
    change(manifest);
    assert.throws(() => reviewSanitaryScope(request, result, alt, manifest));
  };
  tamper((manifest) => { manifest.documents[0].runtime_eligible = true; });
  tamper((manifest) => { manifest.documents[0].jurisdiction = 'EC-Quito'; });
  tamper((manifest) => { manifest.documents.push(structuredClone(manifest.documents[0])); });
  tamper((manifest) => { manifest.external_leads[1].status = 'official_current'; });
  tamper((manifest) => { manifest.external_leads[1].url = 'javascript:alert(1)'; });
  tamper((manifest) => { manifest.external_leads[1].url = 'https://es.scribd.com.evil.tld/document/1/x'; });
  tamper((manifest) => { manifest.external_leads.push(structuredClone(manifest.external_leads[0])); });
  const unversioned = input();
  unversioned.program.occupants = 4;
  assert.throws(() => reviewSanitaryScope(unversioned, result, alt, sources), /entrada/);
  const fake = structuredClone(result);
  fake.regulatory_status = 'verified_with_source';
  assert.throws(() => reviewSanitaryScope(request, fake, fake.alternatives[0], sources), /entrada/);
  const withoutSchema = input(); delete withoutSchema.request_schema;
  assert.throws(() => reviewSanitaryScope(withoutSchema, result, alt, sources), /entrada/);
  const mismatched = structuredClone(result);
  mismatched.project_context.jurisdiction = 'CU';
  assert.throws(() => reviewSanitaryScope(request, mismatched, mismatched.alternatives[0], sources), /Contexto/);
  const forgedScope = structuredClone(result);
  forgedScope.applicability.declared_scope = 'complies';
  assert.throws(() => reviewSanitaryScope(request, forgedScope, forgedScope.alternatives[0], sources), /Contexto/);
  const falsePlot = structuredClone(result);
  falsePlot.site_plot.provenance = 'official_survey';
  assert.throws(() => reviewSanitaryScope(request, falsePlot, falsePlot.alternatives[0], sources), /Contorno de parcela/);
  const brokenOutline = structuredClone(result);
  brokenOutline.site_plot.vertices[2].y += 3;
  assert.throws(() => reviewSanitaryScope(request, brokenOutline,
    brokenOutline.alternatives[0], sources), /Vértices o área/);
  const mismatch = structuredClone(request);
  mismatch.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_corner_notch',
    rear_notches: [{ side: 'left', width: 4, depth: 10 }] };
  assert.throws(() => reviewSanitaryScope(mismatch, result, alt, sources), /Contorno de parcela/);
  const fakeRoad = structuredClone(result);
  fakeRoad.site_approach.geometry_status = 'legal_frontage_verified';
  assert.throws(() => reviewSanitaryScope(request, fakeRoad, fakeRoad.alternatives[0], sources), /Trazado frontal/);
  const fakeStreet = structuredClone(result);
  fakeStreet.site_approach.street_connection_status = 'verified';
  assert.throws(() => reviewSanitaryScope(request, fakeStreet,
    fakeStreet.alternatives[0], sources), /Trazado frontal/);
  const fakeBand = structuredClone(result);
  fakeBand.alternatives[0].front_approach.segments[0].x += 0.5;
  assert.throws(() => reviewSanitaryScope(request, fakeBand, fakeBand.alternatives[0], sources), /bandas frontales/);
  const fakeAccess = structuredClone(request);
  fakeAccess.site.front_approach.width = 1.5;
  assert.throws(() => reviewSanitaryScope(fakeAccess, result, alt, sources), /Trazado frontal/);
  const fakeBlocked = structuredClone(request);
  fakeBlocked.site.reserved_areas = [{ x: 8.5, y: 1, width: 1, depth: 1 }];
  const dishonest = structuredClone(result);
  dishonest.site_reservations.areas = structuredClone(fakeBlocked.site.reserved_areas);
  assert.throws(() => reviewSanitaryScope(fakeBlocked, dishonest,
    dishonest.alternatives[0], sources), /banda frontal cruza/);
  const falseSurvey = structuredClone(result);
  falseSurvey.site_reservations.provenance = 'official_survey';
  assert.throws(() => reviewSanitaryScope(request, falseSurvey, falseSurvey.alternatives[0], sources), /Croquis de reserva/);
  const falseSetback = structuredClone(result);
  falseSetback.site_reservations.geometry_status = 'legal_setback';
  assert.throws(() => reviewSanitaryScope(request, falseSetback, falseSetback.alternatives[0], sources), /Croquis de reserva/);
  const mismatchedSketch = structuredClone(request);
  mismatchedSketch.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }];
  assert.throws(() => reviewSanitaryScope(mismatchedSketch, result, alt, sources), /Croquis de reserva/);
  const fakeVentilation = structuredClone(result);
  fakeVentilation.alternatives[0].bathroom_ventilation_status = 'verified';
  assert.throws(() => reviewSanitaryScope(request, fakeVentilation, fakeVentilation.alternatives[0], sources), /ventilación/);
});

test('independent web review rejects double-counting or forged geometry of two voluntary zones', () => {
  const request = input();
  request.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
    { x: 14, y: 16, width: 1, depth: 2 }];
  const result = generate(request);
  assert.equal(result.status, 'ok');
  assert.equal(reviewSanitaryScope(request, result, result.alternatives[0], sources).regulatory_status,
    'not_evaluated');
  const madeUp = structuredClone(result);
  madeUp.site.unreserved_buildable_area += 1;
  assert.throws(() => reviewSanitaryScope(request, madeUp, madeUp.alternatives[0], sources),
    /área disponible/);
  const overlap = structuredClone(request);
  overlap.site.reserved_areas[1].x = 6.49999999;
  overlap.site.reserved_areas[1].y = 12;
  const dishonest = structuredClone(result);
  dishonest.site_reservations.areas = structuredClone(overlap.site.reserved_areas);
  assert.throws(() => reviewSanitaryScope(overlap, dishonest, dishonest.alternatives[0], sources),
    /Croquis de reserva/);
  const out = structuredClone(request);
  out.site.reserved_areas[1].x = 17.00000001;
  dishonest.site_reservations.areas = structuredClone(out.site.reserved_areas);
  assert.throws(() => reviewSanitaryScope(out, dishonest, dishonest.alternatives[0], sources),
    /Croquis de reserva/);
});

test('web shell exposes the same not-evaluated scope and provenance without fetching sources', async () => {
  const html = await readFile(resolve(root, 'web/index.html'), 'utf8');
  const client = await readFile(resolve(root, 'web/src/main.js'), 'utf8');
  const mapping = await readFile(resolve(root, 'web/src/brief.js'), 'utf8');
  for (const id of ['scope-review', 'scope-status', 'scope-context', 'scope-daylight', 'scope-leads', 'empty-scope', 'scope-stale']) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  for (const field of ['project_jurisdiction', 'housing_class', 'occupants', 'accessibility_needs']) {
    assert.ok(html.includes(`name="${field}"`), field);
    assert.ok(mapping.includes(`fields.${field}.value`), field);
  }
  for (const field of ['plot_notch_enabled', 'notch_side', 'notch_width', 'notch_depth',
    'plot_notch_2_enabled', 'notch_2_width', 'notch_2_depth',
    'approach_shape', 'approach_width', 'approach_front_x', 'approach_turn_y',
    'reserve_enabled', 'reserve_x', 'reserve_y', 'reserve_width', 'reserve_depth',
    'reserve_2_enabled', 'reserve_2_x', 'reserve_2_y', 'reserve_2_width', 'reserve_2_depth']) {
    assert.ok(html.includes(`name="${field}"`), field);
  }
  assert.match(html, /Hasta dos rectángulos voluntarios del solicitante/);
  assert.match(html, /id="reservation-2-fields" disabled hidden/);
  assert.match(html, /Ambos recortes quedan FUERA del croquis/);
  assert.match(html, /id="plot-notch-2-fields" disabled hidden/);
  assert.match(client, /reflectPlotFields\(\)/);
  assert.match(client, /site-plot-summary/);
  assert.match(client, /site-approach-summary/);
  assert.match(html, /Motor v8[\s\S]*Web 0\.22/);
  assert.match(html, /cotas Z supuestas optativas/);
  assert.match(html, /Trazado frontal elegido/);
  assert.match(client, /reflectReservationFields\(\)/);
  assert.match(client, /site-reservation-summary/);
  assert.match(client, /reviewSanitaryScope\(runInput, run, alt, sources\)/);
  assert.match(client, /scope-review'\)\.classList\.toggle\('stale', stale\)/);
  assert.match(client, /scope-stale'\)\.hidden = !stale/);
  assert.match(client, /link\.rel = 'noopener noreferrer'/);
  assert.match(client, /link\.referrerPolicy = 'no-referrer'/);
});

test('an L-shaped plot and a declared Cuba/social-housing context never turn the sketch into legal applicability', () => {
  const request = input();
  Object.assign(request.project_context, {
    jurisdiction: 'CU', housing_class: 'urban_social', occupants: 4,
    accessibility_needs: 'declared',
  });
  request.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_corner_notch',
    rear_notches: [{ side: 'right', width: 4, depth: 10 }] };
  const result = generate(request);
  assert.equal(result.status, 'ok');
  const review = reviewSanitaryScope(request, result, result.alternatives[0], sources);
  assert.equal(review.scope, 'candidate_from_self_report_only');
  assert.equal(review.regulatory_status, 'not_evaluated');
  assert.equal(review.daylight_status, 'not_evaluated');
  assert.equal(review.ventilation_status, 'not_evaluated');
  assert.match(describeDeclaredContext(review), /NO su aplicabilidad legal/);
  request.site.plot_outline.rear_notches[0].width = 7;
  request.site.plot_outline.rear_notches[0].depth = 12;
  const blocked = generate(request);
  assert.equal(blocked.status, 'infeasible');
  const withoutPlan = reviewSanitaryScope(request, blocked, null, sources);
  assert.equal(withoutPlan.scope, 'candidate_from_self_report_only');
  assert.equal(withoutPlan.regulatory_status, 'not_evaluated');
  assert.equal(withoutPlan.bathrooms, null);
});

test('independent review verifies both rear cuts, their polygon and available demo area without a legal inference', () => {
  const request = input();
  request.site.plot_outline = { provenance: 'user_sketch_unverified',
    shape: 'rear_both_corners_notched', rear_notches: [
      { side: 'right', width: 3, depth: 10 }, { side: 'left', width: 4, depth: 10 },
    ] };
  const result = generate(request);
  assert.equal(result.status, 'ok');
  const alt = result.alternatives[0];
  assert.equal(reviewSanitaryScope(request, result, alt, sources).regulatory_status, 'not_evaluated');
  const badEcho = structuredClone(result);
  badEcho.site_plot.rear_notches[1].width += 1;
  assert.throws(() => reviewSanitaryScope(request, badEcho, badEcho.alternatives[0], sources), /Recortes posteriores/);
  const reordered = structuredClone(result);
  reordered.site_plot.rear_notches.reverse();
  assert.throws(() => reviewSanitaryScope(request, reordered, reordered.alternatives[0], sources), /Recortes posteriores/);
  const badVertices = structuredClone(result);
  badVertices.site_plot.vertices[4].x -= 0.01;
  assert.throws(() => reviewSanitaryScope(request, badVertices, badVertices.alternatives[0], sources), /Vértices o área/);
  const fakeArea = structuredClone(result);
  fakeArea.site.unreserved_buildable_area += 1;
  assert.throws(() => reviewSanitaryScope(request, fakeArea, fakeArea.alternatives[0], sources), /área disponible/);
  const fakeRegion = structuredClone(request);
  fakeRegion.site.plot_outline.rear_notches[1].width = 15;
  assert.throws(() => reviewSanitaryScope(fakeRegion, result, alt, sources), /Recortes posteriores/);
  const fakeReserve = structuredClone(request);
  fakeReserve.site.reserved_areas = [{ x: 14.99999999, y: 16, width: 1, depth: 1 }];
  const fakeEcho = structuredClone(result);
  fakeEcho.site_reservations.areas = structuredClone(fakeReserve.site.reserved_areas);
  assert.throws(() => reviewSanitaryScope(fakeReserve, fakeEcho, fakeEcho.alternatives[0], sources),
    /zonas solapadas, fuera del contorno o en el recorte/);
});

test('declaring Cuba cannot turn a blocked front strip into a real accessible route', () => {
  const request = input();
  Object.assign(request.project_context, {
    jurisdiction: 'CU', housing_class: 'urban_social', occupants: 4,
    accessibility_needs: 'declared',
  });
  request.site.reserved_areas = [{ x: 8.5, y: 1, width: 1, depth: 1 }];
  const result = generate(request);
  assert.equal(result.status, 'infeasible');
  assert.equal(result.alternatives.length, 0);
  const review = reviewSanitaryScope(request, result, null, sources);
  assert.equal(review.approach, null); // intent echoed, no validated candidate or route
  assert.equal(review.scope, 'candidate_from_self_report_only');
  assert.equal(review.regulatory_status, 'not_evaluated');
  assert.equal(review.daylight_status, 'not_evaluated');
  assert.equal(review.ventilation_status, 'not_evaluated');
  assert.equal(review.bathrooms, null);
  assert.match(describeDeclaredContext(review), /NO su aplicabilidad legal/);
});

test('review independently checks both turns, full-width bands and the unresolved legal statuses', () => {
  const request = input();
  request.site.reserved_areas = [{ x: 8.5, y: 0.5, width: 1, depth: 0.5 }];
  request.site.front_approach = { provenance: 'user_sketch_unverified',
    shape: 'orthogonal_front_detour', width: 1.2, front_x: 11.5, turn_y: 1.6 };
  Object.assign(request.project_context, { jurisdiction: 'CU', housing_class: 'urban_social',
    occupants: 4, accessibility_needs: 'declared' });
  const result = generate(request);
  assert.equal(result.status, 'ok');
  const alt = result.alternatives[0];
  const review = reviewSanitaryScope(request, result, alt, sources);
  assert.equal(review.scope, 'candidate_from_self_report_only');
  assert.equal(review.regulatory_status, 'not_evaluated');
  assert.equal(review.approach.shape, 'orthogonal_front_detour');
  assert.equal(review.approach.segments.length, 3);
  assert.deepEqual(review.approach.turns, [{ x: 11.5, y: 1.6 }, { x: 9, y: 1.6 }]);
  for (const change of [
    (r) => { r.site_approach.accessibility_status = 'accessible'; },
    (r) => { r.site_approach.turn_y = 1.7; },
    (r) => { r.alternatives[0].front_approach.front_contact.x = 9; },
    (r) => { r.alternatives[0].front_approach.turns[1].x += 0.2; },
    (r) => { r.alternatives[0].front_approach.segments[0].y += 0.1; },
    (r) => { r.alternatives[0].front_approach.segments[1].depth = 0.01; },
    (r) => { r.alternatives[0].front_approach.segments[2].width += 1; },
  ]) {
    const fake = structuredClone(result);
    change(fake);
    assert.throws(() => reviewSanitaryScope(request, fake, fake.alternatives[0], sources));
  }
  const swapped = structuredClone(request);
  swapped.site.front_approach.turn_y = 2;
  assert.throws(() => reviewSanitaryScope(swapped, result, alt, sources));
  const almost = structuredClone(result);
  almost.alternatives[0].front_approach.segments[1].y -= 1e-8;
  assert.throws(() => reviewSanitaryScope(request, almost,
    almost.alternatives[0], sources), /banda frontal cruza/); // tiny positive overlap
  const fakeCrossing = structuredClone(result);
  const collision = [{ x: 10, y: 2.0, width: 0.3, depth: 0.1 }]; // outside y=1.6 centreline
  const madeUpInput = structuredClone(request);
  madeUpInput.site.reserved_areas = collision;
  fakeCrossing.site_reservations.areas = collision;
  assert.throws(() => reviewSanitaryScope(madeUpInput, fakeCrossing,
    fakeCrossing.alternatives[0], sources), /banda frontal cruza/);
});

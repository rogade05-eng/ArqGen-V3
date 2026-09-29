import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { conceptualReport } from '../src/report.js';
import { verifyArchive } from '../src/archive.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const wasm = await readFile(resolve(root, 'web/public/core.wasm'));
const { instance } = await WebAssembly.instantiate(wasm);
const core = instance.exports;
const sample = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const rules = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
const sources = JSON.parse(await readFile(resolve(root, 'knowledge/source-manifest.json'), 'utf8'));
const input = () => ({ ...structuredClone(sample), rules: structuredClone(rules) });
const report = (brief, result, index) => conceptualReport(brief, result, index, sources);
const rounded = (value, digits = 2) => new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: digits, maximumFractionDigits: digits,
}).format(value);

function generate(request) {
  const bytes = new TextEncoder().encode(JSON.stringify(request));
  const pointer = core.arq_alloc(bytes.length);
  assert.ok(pointer);
  new Uint8Array(core.memory.buffer, pointer, bytes.length).set(bytes);
  let packed;
  try { packed = core.arq_generate(pointer, bytes.length); }
  finally { core.arq_free(pointer, bytes.length); }
  const ptr = Number(packed & 0xffffffffn);
  const size = Number(packed >> 32n);
  let text;
  try { text = new TextDecoder().decode(new Uint8Array(core.memory.buffer, ptr, size)); }
  finally { core.arq_free(ptr, size); }
  return JSON.parse(text);
}

test('conceptual plain-text sheet transcribes validated areas, bathrooms and decisions without real-ventilation claims', () => {
  const request = input();
  const result = generate(request);
  const first = result.alternatives[0];
  const sheet = report(request, result, 0);
  assert.equal(sheet, report(request, generate(request), 0));
  assert.match(sheet, /NO APTO PARA OBRA/);
  assert.match(sheet, /NC 598:2009 · NO EVALUADA/);
  assert.match(sheet, /Baños con vano de fachada dibujado: 2\/2/);
  assert.match(sheet, /Baños sin ventana dibujada: 0\/2/);
  assert.match(sheet, /NO es umbral NC 598/);
  assert.match(sheet, /Iluminación natural: NO EVALUADA/);
  assert.match(sheet, /NO EVALUAD[OA]/);
  assert.match(sheet, /No hay equipo de extracción identificado/);
  assert.match(sheet, new RegExp(result.input_hash));
  assert.match(sheet, new RegExp(first.id));
  assert.ok(sheet.includes(`área construida máxima por FAR demo: ${rounded(result.site.max_built_area)} m²`));
  assert.ok(sheet.includes(`Huella bruta elegida: ${rounded(first.built_area)} m²`));
  assert.ok(sheet.includes(`reserva para muros y vanos: ${rounded(first.wall_allowance_area)} m²`));
  for (const room of first.rooms) {
    assert.ok(sheet.includes(`${room.label} (${room.id}): ${rounded(room.usable_area)} m²`));
  }
  for (const d of first.decisions) assert.ok(sheet.includes(d.rule));
  for (const room of first.rooms.filter(({ type }) => type === 'bathroom')) {
    assert.ok(sheet.includes(`${rounded(room.bath_airflow.target_flow_m3h, 1)} m³/h`));
    assert.ok(sheet.includes(`${rounded(room.bath_pressure.pressure_budget.assumed_total_pa)} Pa`));
  }
  assert.match(sheet, /0; alternativas mostradas: 3/);
  assert.doesNotMatch(sheet, /cumple la normativa|caudal entregado medido: \d|ventilación efectiva: VERIFICADA/i);
  const verified = verifyArchive({ input: request, generation: result, selection: null }, rules, generate);
  assert.equal(report(verified.focus.input, verified.focus.generation, 0), sheet);
});

test('TXT transcribes self-reported context without converting it into NC 598 compliance', () => {
  const request = input();
  Object.assign(request.project_context, {
    jurisdiction: 'CU', housing_class: 'urban_social', occupants: 4,
    accessibility_needs: 'none_declared',
  });
  const result = generate(request);
  const text = report(request, result, 0);
  assert.match(text, /Entrada: arqgen-brief-v8/);
  assert.match(text, /NC 598:2009 · NO EVALUADA/);
  assert.match(text, /Cuba \(declaración sin comprobar\)/);
  assert.match(text, /4 \(declaración sin comprobar\)/);
  assert.match(text, /posible ámbito a estudiar/);
  assert.match(text, /NO implica exención/);
  assert.doesNotMatch(text, /NC 598:2009.*cumple|accesibilidad verificada/i);
  const without = input(); without.project_context.jurisdiction = 'outside_CU';
  const outsideText = report(without, generate(without), 0);
  assert.match(outsideText, /NO equivale a exención/);
});

test('partial rejection reasons appear on the sheet, and no sheet exists for infeasible or unverified claims', () => {
  const partial = input(); partial.rules.bath_pressure.fan_reference_flow_m3h = 20;
  const result = generate(partial);
  const sheet = report(partial, result, 1);
  assert.match(sheet, /descartadas: 12/);
  for (const { reason, count } of result.rejection_summary) {
    assert.ok(sheet.includes(`${count} × ${reason}`));
  }
  assert.throws(() => report(partial, result, -1));
  assert.throws(() => report(partial, result, 3));
  const impossible = input(); impossible.rules.bath_pressure.fan_reference_pressure_pa = 10;
  assert.throws(() => report(impossible, generate(impossible), 0));
  const wrongRules = input(); wrongRules.rules.version = 'fake';
  assert.throws(() => report(wrongRules, result, 0));
  assert.throws(() => conceptualReport(partial, result, 0), /Inventario/);
  const fakeSources = structuredClone(sources);
  fakeSources.external_leads[0].runtime_eligible = true;
  assert.throws(() => conceptualReport(partial, result, 0, fakeSources), /Inventario/);
  const fake = structuredClone(result);
  fake.alternatives[0].rooms.find(({ type }) => type === 'bathroom').bath_pressure.delivered_flow_status = 'measured';
  assert.throws(() => report(partial, fake, 0), /ventilación/);
});

test('TXT exposes the self-reported site rectangle and never implies a verified setback or buildability', () => {
  const request = input();
  request.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 }];
  const result = generate(request);
  assert.equal(result.status, 'ok');
  const sheet = report(request, result, 0);
  assert.match(sheet, /Croquis voluntario de parcela: rectángulo x=4,50, y=12,00, ancho=2,00, fondo=2,00 m/);
  assert.match(sheet, /NO levantamiento, lindero ni derecho verificado/);
  assert.match(sheet, /envolvente demo dentro del croquis y no reservada: .* NO edificabilidad legal/);
  assert.match(sheet, /site\.reserved_areas@user_sketch_unverified/);
  assert.match(sheet, /Aproximación frontal: franja recta de 1,20 m centrada en la puerta dibujada/);
  assert.match(sheet, /NO certifica vía pública, derecho de paso, cota, pavimento, obstáculos, accesibilidad ni acceso efectivo/);
  assert.match(sheet, /site\.front_approach@user_sketch_unverified/);
  assert.match(sheet, /NC 598:2009 · NO EVALUADA/);
  assert.match(sheet, /Iluminación natural: NO EVALUADA/);
  const forged = structuredClone(result);
  forged.site_reservations.geometry_status = 'verified_setback';
  assert.throws(() => report(request, forged, 0), /Croquis de reserva/);
});

test('TXT transcribes both drawn zones without a legal or access claim', () => {
  const request = input();
  request.site.reserved_areas = [{ x: 4.5, y: 12, width: 2, depth: 2 },
    { x: 14, y: 16, width: 1, depth: 2 }];
  const result = generate(request);
  assert.equal(result.status, 'ok');
  const sheet = report(request, result, 0);
  assert.match(sheet, /zona 1: rectángulo x=4,50, y=12,00, ancho=2,00, fondo=2,00 m/);
  assert.match(sheet, /zona 2: rectángulo x=14,00, y=16,00, ancho=1,00, fondo=2,00 m/);
  assert.match(sheet, /NO levantamiento, lindero ni derecho verificado/);
  assert.match(sheet, /site\.reserved_areas@user_sketch_unverified/);
  assert.match(sheet, /derecho de paso.*acceso efectivo/);
  const forged = structuredClone(result);
  forged.site.unreserved_buildable_area += 2;
  assert.throws(() => report(request, forged, 0), /área disponible/);
});

test('TXT for an L-shaped sketch names the removed corner and the non-surveyed FAR denominator', () => {
  const request = input();
  request.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_corner_notch',
    rear_notches: [{ side: 'right', width: 4, depth: 10 }] };
  const result = generate(request);
  assert.equal(result.status, 'ok');
  const sheet = report(request, result, 0);
  assert.match(sheet, /Contorno de parcela declarado: forma en L con recorte posterior derecho de 4,00 × 10,00 m FUERA de la parcela dibujada/);
  assert.match(sheet, /Retiros ilustrativos solo desde la caja exterior, NO desde los entrantes/);
  assert.match(sheet, /Área del croquis de parcela: 356,00 m² \(NO superficie catastral\)/);
  assert.match(sheet, /site\.plot_outline@user_sketch_unverified/);
  assert.match(sheet, /Aproximación frontal: franja recta de 1,20 m/);
  assert.match(sheet, /NO levantamiento, catastro, linderos ni derechos verificados/);
  assert.match(sheet, /NC 598:2009 · NO EVALUADA/);
  assert.match(sheet, /Iluminación natural: NO EVALUADA/);
  const forged = structuredClone(result);
  forged.site_plot.geometry_status = 'surveyed_plot';
  assert.throws(() => report(request, forged, 0), /Contorno de parcela incompatible/);
  const falseArea = structuredClone(result);
  falseArea.site.plot_area += 20;
  assert.throws(() => report(request, falseArea, 0), /Vértices o área/);
});

test('TXT enumerates both rear cuts, demo area and unverified interior setbacks', () => {
  const request = input();
  request.site.plot_outline = { provenance: 'user_sketch_unverified',
    shape: 'rear_both_corners_notched', rear_notches: [
      { side: 'left', width: 4, depth: 10 }, { side: 'right', width: 3, depth: 10 },
    ] };
  const result = generate(request);
  assert.equal(result.status, 'ok');
  const sheet = report(request, result, 0);
  assert.match(sheet, /dos esquinas posteriores recortadas FUERA de la parcela dibujada: 1 izquierda 4,00 × 10,00 m; 2 derecha 3,00 × 10,00 m/);
  assert.match(sheet, /Área del croquis de parcela: 326,00 m²/);
  assert.match(sheet, /no se acredita acceso exterior real/);
  assert.match(sheet, /NO desde los entrantes/);
  assert.doesNotMatch(sheet, /catastro verificado|retiro legal medido|acceso accesible verificado/i);
});

test('TXT refuses a forged access band and treats a zero setback as mere boundary contact', () => {
  const request = input();
  const result = generate(request);
  const forged = structuredClone(result);
  forged.alternatives[0].front_approach.segments[0].depth += 0.5;
  assert.throws(() => report(request, forged, 0), /bandas frontales/);
  const fakeRoad = structuredClone(result);
  fakeRoad.site_approach.provenance = 'verified_highway';
  assert.throws(() => report(request, fakeRoad, 0), /Trazado frontal/);
  const touching = input(); touching.rules.setbacks.front = 0;
  const atEdge = generate(touching);
  assert.equal(atEdge.status, 'ok');
  const text = report(touching, atEdge, 0);
  assert.match(text, /puerta en el borde frontal del croquis: no hay franja exterior modelada/);
  assert.match(text, /NO certifica vía pública, derecho de paso/);
});

test('TXT states the declared two-turn sketch and never turns it into an accessible right of way', () => {
  const request = input();
  request.site.reserved_areas = [{ x: 8.5, y: 0.5, width: 1, depth: 0.5 }];
  request.site.front_approach = { provenance: 'user_sketch_unverified',
    shape: 'orthogonal_front_detour', width: 1.2, front_x: 11.5, turn_y: 1.6 };
  request.project_context.jurisdiction = 'CU';
  const result = generate(request);
  assert.equal(result.status, 'ok');
  const sheet = report(request, result, 0);
  assert.match(sheet, /Aproximación frontal: rodeo ortogonal de 1,20 m con dos giros declarados/);
  assert.match(sheet, /borde x=11,50, y=0; giro a y=1,60; puerta x=9,00, y=3,00 m/);
  assert.match(sheet, /Sus tres bandas completas no cruzan las exclusiones dibujadas/);
  assert.match(sheet, /NO certifica vía pública, derecho de paso, cota, pavimento, obstáculos, accesibilidad ni acceso efectivo/);
  assert.match(sheet, /NC 598:2009 · NO EVALUADA/);
  assert.doesNotMatch(sheet, /accesibilidad verificada|cumple NC 391/i);
  const forged = structuredClone(result);
  forged.alternatives[0].front_approach.turns[0].y = 2;
  assert.throws(() => report(request, forged, 0), /bandas frontales/);
  const noPlan = structuredClone(request);
  noPlan.site.front_approach.turn_y = 2.4; // y=1.8..3.0: still fits but crosses no reserve
  noPlan.site.reserved_areas = [{ x: 8.5, y: 2.0, width: 1, depth: 0.5 }];
  const impossible = generate(noPlan);
  assert.equal(impossible.status, 'infeasible');
  assert.throws(() => report(noPlan, impossible, 0));
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { callCore } from '../src/core-client.js';
import { extractPlanEnvelope, outlineRectUnion, planEnvelopeFormat } from '../src/plan-envelope.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const { instance } = await WebAssembly.instantiate(await readFile(resolve(root, 'web/public/core.wasm')));
const base = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const rules = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
const input = () => ({ ...structuredClone(base), rules: structuredClone(rules) });
const generate = (i) => callCore(instance.exports, 'arq_generate', i);

function polygonArea(points) {
  return points.reduce((total, p, index) => {
    const next = points[(index + 1) % points.length];
    return total + p.x * next.y - next.x * p.y;
  }, 0) / 2;
}

test('la unión L conserva quiebros, área y largo exactos, nunca usa la caja exterior', () => {
  const shape = outlineRectUnion([
    { x: 0, y: 0, width: 2, depth: 1 },
    { x: 0, y: 1, width: 1, depth: 1 },
  ], 3);
  assert.deepEqual(shape.vertices, [
    { x: 0, y: 0 }, { x: 2, y: 0 }, { x: 2, y: 1 },
    { x: 1, y: 1 }, { x: 1, y: 2 }, { x: 0, y: 2 },
  ]);
  assert.equal(shape.gross_area_m2, 3); // bounding box would be 4
  assert.equal(shape.perimeter_m, 8);
  assert.deepEqual(shape.sides.map((s) => s.length_m), [2, 1, 1, 1, 1, 2]);
  assert.deepEqual(shape.sides.map((s) => s.plan_side),
    ['top', 'right', 'bottom', 'right', 'bottom', 'left']);
  assert.equal(polygonArea(shape.vertices), 3);
});

test('pequeñas diferencias flotantes cierran; solapes, islas y patios NO se presentan como polígono único', () => {
  const almost = outlineRectUnion([
    { x: 0, y: 0, width: 1, depth: 1 },
    { x: 1 + 1e-9, y: 0, width: 1, depth: 1 },
  ], 2);
  assert.equal(almost.vertices.length, 4);
  assert.ok(Math.abs(almost.perimeter_m - 6) < 1e-6);
  assert.throws(() => outlineRectUnion([
    { x: 0, y: 0, width: 2, depth: 1 },
    { x: 1, y: 0, width: 2, depth: 1 },
  ], 3), /solapadas/);
  assert.throws(() => outlineRectUnion([
    { x: 0, y: 0, width: 1, depth: 1 },
    { x: 3, y: 0, width: 1, depth: 1 },
  ], 2), /cuerpos separados/);
  assert.throws(() => outlineRectUnion([
    { x: 0, y: 0, width: 3, depth: 1 },
    { x: 0, y: 1, width: 1, depth: 1 },
    { x: 2, y: 1, width: 1, depth: 1 },
    { x: 0, y: 2, width: 3, depth: 1 },
  ], 8), /huecos, patios/);
  assert.throws(() => outlineRectUnion([
    { x: 0, y: 0, width: 1, depth: 1 },
    { x: 1, y: 1, width: 1, depth: 1 },
  ], 2), /vértice ambiguo/);
  assert.throws(() => outlineRectUnion([{ x: 0, y: 0, width: 2, depth: 2 }], 5), /superficie bruta incoherente/);
});

test('48 candidatas reales: contorno/vanos coherentes para orientaciones y semillas distintas', () => {
  let checked = 0;
  for (const front of ['S', 'N', 'E', 'W']) {
    for (const seed of [1, 42, 123, 999]) {
      const brief = input();
      brief.site.front_orientation = front;
      brief.seed = seed;
      const run = generate(brief);
      assert.equal(run.status, 'ok');
      for (const alt of run.alternatives) {
        const envelope = extractPlanEnvelope(alt, front);
        assert.equal(envelope.format, planEnvelopeFormat);
        assert.equal(envelope.level.elevation_m, null);
        assert.equal(envelope.source_candidate_id, alt.id);
        assert.ok(envelope.footprint.vertices.length >= 4);
        assert.ok(Math.abs(envelope.footprint.gross_area_m2 - alt.built_area) < 1e-5);
        assert.ok(Math.abs(polygonArea(envelope.footprint.vertices) - alt.built_area) < 1e-5);
        assert.equal(envelope.perimeter_openings.length, alt.rooms.filter((r) => r.window).length + 1);
        assert.equal(envelope.perimeter_openings[0].world_orientation_declared, front);
        for (const opening of envelope.perimeter_openings) {
          const edge = envelope.footprint.sides.find((s) => s.id === opening.segment_id);
          assert.ok(edge, 'Cada vano encuentra exactamente un segmento del perímetro.');
          assert.ok(opening.offset_m >= -1e-7 && opening.offset_m + opening.span_m <= edge.length_m + 1e-7);
          assert.ok(opening.span_m > 0);
        }
        checked++;
      }
    }
  }
  assert.equal(checked, 48);
});

test('rechaza vanos desplazados, orientaciones falsas y áreas inventadas', () => {
  const brief = input();
  const alt = generate(brief).alternatives[0];
  const moved = structuredClone(alt);
  moved.rooms[0].window.opening.x += 0.25;
  assert.throws(() => extractPlanEnvelope(moved, 'S'), /separada de su propio local/);
  const wrongDirection = structuredClone(alt);
  wrongDirection.rooms[0].window.direction = 'N';
  assert.throws(() => extractPlanEnvelope(wrongDirection, 'S'), /orientación\/ancho/);
  const fakeArea = structuredClone(alt);
  fakeArea.built_area += 0.1;
  assert.throws(() => extractPlanEnvelope(fakeArea, 'S'), /superficie bruta incoherente/);
  const shortDoor = structuredClone(alt);
  shortDoor.entrance.width -= 0.1;
  assert.throws(() => extractPlanEnvelope(shortDoor, 'S'), /orientación\/ancho/);
});

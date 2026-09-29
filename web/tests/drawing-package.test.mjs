import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { unzipSync } from 'fflate';
import { callCore } from '../src/core-client.js';
import { buildDrawingPackage, drawingPackageFormat } from '../src/drawing-package.js';
import { verifyArchive } from '../src/archive.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const { instance } = await WebAssembly.instantiate(await readFile(resolve(root, 'web/public/core.wasm')));
const sample = JSON.parse(await readFile(resolve(root, 'examples/rectangular.json'), 'utf8'));
const demoRules = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));
const input = () => ({ ...structuredClone(sample), rules: structuredClone(demoRules) });
const generate = (i) => callCore(instance.exports, 'arq_generate', i);
const decoded = (zip, filename) => new TextDecoder().decode(unzipSync(zip)[filename]);

function inspectPackage(brief, generation, choice = 0) {
  const result = buildDrawingPackage(brief, generation, choice);
  const files = unzipSync(result.bytes);
  assert.deepEqual(Object.keys(files), [
    'A-01-emplazamiento.svg', 'A-02-planta-amueblada.svg', 'A-03-planta-cotas.svg',
    'manifest.json', 'origen-v8.json', 'LEEME-ANTES-DE-USAR.txt',
  ]);
  assert.equal(result.sheets.length, 3);
  assert.ok(result.bytes.length < 2_000_000);
  assert.match(result.filename, /^arqgen-laminas-CONCEPTUAL-cand-[a-f0-9]{16}-\d+\.zip$/);
  const manifest = JSON.parse(decoded(result.bytes, 'manifest.json'));
  assert.deepEqual(manifest, result.manifest);
  assert.equal(manifest.format, drawingPackageFormat);
  assert.equal(manifest.input_hash, generation.input_hash);
  assert.equal(manifest.candidate_id, generation.alternatives[choice].id);
  assert.equal(manifest.status, 'illustrative_not_certified');
  assert.equal(manifest.model, 'single_floor_housing_schematic');
  assert.ok(manifest.excluded_not_modelled.includes('hospital') && manifest.excluded_not_modelled.includes('sections'));
  for (const sheet of manifest.sheets) {
    const svg = decoded(result.bytes, sheet.filename);
    assert.equal(result.sheets.find((s) => s.number === sheet.number)?.svg, svg);
    assert.match(svg, /<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" width="297mm" height="420mm"/);
    assert.match(svg, new RegExp(`data-candidate-id="${manifest.candidate_id}"`));
    assert.match(svg, new RegExp(`data-engine-hash="${manifest.input_hash}"`));
    assert.match(svg, /NO APTO PARA OBRA/);
    assert.doesNotMatch(svg.replace('xmlns="http://www.w3.org/2000/svg"', ''),
      /<(script|image|foreignObject)\b|https?:\/\//i, 'Autocontenido, sin cargas de imágenes externas.');
    assert.equal(sheet.paper, 'ISO_A3_portrait_297x420mm');
    assert.match(sheet.nominal_scale, /^1:(50|100|200|500|1000|2000|5000)$/);
  }
  assert.match(decoded(result.bytes, 'LEEME-ANTES-DE-USAR.txt'), /NO APTO PARA OBRA/);
  const archive = JSON.parse(decoded(result.bytes, 'origen-v8.json'));
  assert.deepEqual(archive, { input: brief, generation, selection: null });
  const restored = verifyArchive(archive, demoRules, generate); // full local Rust replay
  assert.equal(restored.kind, 'single');
  assert.deepEqual(restored.focus.generation, generation);
  return result;
}

test('A3 conceptual ZIP: tres vistas del MISMO candidato Rust y archivo importable con replay', () => {
  const brief = input();
  const generated = generate(brief);
  assert.equal(generated.status, 'ok');
  const first = inspectPackage(brief, generated);
  assert.deepEqual(first.bytes, buildDrawingPackage(brief, generated, 0).bytes, 'ZIP reproducible, sin fecha de reloj.');
  const site = first.sheets[0];
  const furnished = first.sheets[1];
  const dimensions = first.sheets[2];
  assert.equal(site.denominator, 100);
  assert.equal(furnished.denominator, 50);
  assert.equal(dimensions.denominator, 50);
  assert.match(site.svg, /18\.00 m · parcela declarada/);
  assert.match(site.svg, /22\.00 m · parcela/);
  assert.ok(!site.svg.includes('class="fixture"'), 'Ninguna decoración amueblada en el emplazamiento.');
  assert.match(furnished.svg, /ALTERNATIVA cand-/);
  assert.match(furnished.svg, /Estancias y muebles ilustrativos/i);
  assert.match(dimensions.svg, /COTAS ÚTILES DE LOCALES/);
  for (const room of generated.alternatives[0].rooms) {
    assert.ok(dimensions.svg.includes(`${room.usable_rect.width.toFixed(2)} × ${room.usable_rect.depth.toFixed(2)} m · ${room.usable_area.toFixed(2)} m²`));
    assert.ok(dimensions.svg.includes(`data-room-id="${room.id}"`));
  }
  assert.notEqual(first.manifest.sheets[0].nominal_scale, first.manifest.sheets[1].nominal_scale,
    'Escala nominal adaptada independientemente al croquis del solar y a la planta del edificio.');
  const second = inspectPackage(brief, generated, 1);
  assert.equal(second.manifest.input_hash, first.manifest.input_hash);
  assert.notEqual(second.manifest.candidate_id, first.manifest.candidate_id);
});

test('el ejemplo entregado en el repositorio coincide byte a byte con el WASM versionado', async () => {
  const brief = input();
  const pkg = buildDrawingPackage(brief, generate(brief), 0);
  const directory = resolve(root, 'examples/laminas-conceptuales');
  assert.deepEqual(Buffer.from(pkg.bytes), await readFile(resolve(directory, 'muestra-vivienda-A3.zip')));
  for (const sheet of pkg.sheets) {
    assert.equal(sheet.svg, await readFile(resolve(directory, sheet.filename), 'utf8'));
  }
});

test('cotas, huella y norte se derivan de la geometría incluso con dos recortes', () => {
  const brief = input();
  brief.site.plot_outline = { provenance: 'user_sketch_unverified', shape: 'rear_both_corners_notched',
    rear_notches: [{ side: 'left', width: 4, depth: 10 }, { side: 'right', width: 3, depth: 10 }] };
  const generated = generate(brief);
  assert.equal(generated.status, 'ok');
  assert.equal(generated.site_plot.vertices.length, 8);
  const { sheets } = inspectPackage(brief, generated);
  const markers = [...sheets[0].svg.matchAll(/\bM \d+\.\d+ \d+\.\d+ L /g)];
  assert.ok(markers.length >= 1, 'El sitio se dibuja como path de vértices Rust, no como caja del terreno.');
  assert.match(sheets[0].svg, /class="[^"]*"|CROQUIS|HUELLA OSCURA/); // visible site legend
  assert.notEqual(sheets[0].svg, sheets[1].svg);
  assert.match(sheets[2].svg, /ext\. huella/);
});

test('no crea planos de entradas inviables, resultados falsificados ni áreas incoherentes', () => {
  const brief = input();
  const result = generate(brief);
  const narrow = input();
  narrow.site.width = 4;
  assert.equal(generate(narrow).status, 'infeasible');
  assert.throws(() => buildDrawingPackage(narrow, generate(narrow), 0), /Solo se documenta/);
  assert.throws(() => buildDrawingPackage(brief, result, 99), /Solo se documenta/);
  const forged = structuredClone(result);
  forged.alternatives[0].rooms[0].usable_area += 1;
  assert.throws(() => buildDrawingPackage(brief, forged, 0), /área validada/);
  const wrong = structuredClone(result);
  wrong.alternatives[0].wall_zones[0].x = -0.5;
  assert.throws(() => buildDrawingPackage(brief, wrong, 0), /fuera del croquis/);
  const wrongId = structuredClone(result);
  wrongId.alternatives[0].id = 'cand-false-1';
  assert.throws(() => buildDrawingPackage(brief, wrongId, 0), /geometría v8 íntegra/);
  const changedBrief = structuredClone(brief);
  changedBrief.site.width += 1;
  assert.throws(() => buildDrawingPackage(changedBrief, result, 0), /no corresponden al encargo vigente/);
  const hostileLabel = structuredClone(result);
  hostileLabel.alternatives[0].label = '<script>alert(1)</script>&';
  const svg = buildDrawingPackage(brief, hostileLabel, 0).sheets[1].svg;
  assert.match(svg, /&lt;script&gt;alert\(1\)&lt;\/script&gt;&amp;/);
  assert.doesNotMatch(svg, /<script>/);
});

// A SEPARATE, versioned Rust/WASM vertical request/JSON archive. No geometry is
// inferred in JS: every imported/saved model must replay byte-equivalent JSON
// through arq_vertical. The v8 archive/workspace and the SVG v2 ZIP are unchanged.
import { checkWebInput, maxArchiveBytes, sameJson } from './archive.js';

export const verticalRequestFormat = 'arqgen-declared-vertical-request-v1';
export const verticalModelFormat = 'arqgen-declared-vertical-model-v1';
export const verticalArchiveFormat = 'arqgen-declared-vertical-archive-v1';

const keysAre = (value, names) => value !== null && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).length === names.length && names.every((key) => Object.hasOwn(value, key));
const bytes = (value) => new TextEncoder().encode(JSON.stringify(value)).length;

export function makeVerticalRequest(input, generation, index, heights) {
  if (input?.request_schema !== 'arqgen-brief-v8' || generation?.status !== 'ok' ||
      !Number.isInteger(index) || !generation.alternatives?.[index] ||
      typeof generation.input_hash !== 'string') {
    throw new Error('Genera y selecciona primero una alternativa de vivienda v8 vigente.');
  }
  const candidate = generation.alternatives[index];
  if (!candidate?.id?.startsWith(`cand-${generation.input_hash}-`) || !Array.isArray(candidate.rooms)) {
    throw new Error('La alternativa no corresponde al encargo v8 vigente.');
  }
  if (!keysAre(heights, ['floor_z_m', 'wall_top_z_m', 'entry_head_above_floor_m', 'window_sill_above_floor_m']) ||
      ![heights.floor_z_m, heights.wall_top_z_m, heights.entry_head_above_floor_m].every(Number.isFinite)) {
    throw new Error('Declara las tres cotas Z numéricas: piso, coronación y cabeza del acceso.');
  }
  const withWindows = candidate.rooms.filter((room) => room.window);
  const expected = withWindows.map((room) => room.id).sort();
  const actual = keysAre(heights.window_sill_above_floor_m, expected);
  if (!actual || !expected.every((roomId) =>
    Number.isFinite(heights.window_sill_above_floor_m[roomId]) && heights.window_sill_above_floor_m[roomId] >= 0)) {
    throw new Error('Declara un alféizar numérico no negativo por cada local con ventana; no faltan ni sobran locales.');
  }
  const request = structuredClone({
    format: verticalRequestFormat, typology: 'single_family_house', input,
    candidate_id: candidate.id,
    declared_vertical: {
      datum: 'assumed_local_datum_not_surveyed',
      height_provenance: 'illustrative_assumption_not_measured',
      ...heights,
    },
  });
  if (bytes(request) > 256 * 1024) throw new Error('La solicitud vertical supera 256 KiB.');
  return request;
}

function checkModel(request, model) {
  if (model?.status !== 'ok' || model.format !== verticalModelFormat ||
      model.typology !== 'single_family_house' || model.source?.candidate_id !== request.candidate_id ||
      model.source?.request_schema !== 'arqgen-brief-v8' ||
      typeof model.source?.input_hash !== 'string' ||
      !/^[0-9a-f]{16}$/.test(model.source.input_hash) ||
      typeof model.model_hash !== 'string' || !/^[0-9a-f]{16}$/.test(model.model_hash) ||
      !Array.isArray(model.levels) || model.levels.length !== 1 || model.levels[0]?.level_id !== 'L0' ||
      !Array.isArray(model.levels[0].openings) ||
      model.roof !== null || model.vertical_connections !== null || model.facades !== null || model.sections !== null) {
    throw new Error(model?.message || 'El núcleo Rust no devolvió un modelo vertical v1 válido para esta alternativa.');
  }
}

export function makeVerticalArchive(request, model) {
  if (!keysAre(request, ['format', 'typology', 'input', 'candidate_id', 'declared_vertical']) ||
      request.format !== verticalRequestFormat) throw new Error('Solicitud vertical desconocida.');
  checkModel(request, model);
  const archive = structuredClone({ format: verticalArchiveFormat, request, model });
  if (bytes(archive) > maxArchiveBytes) throw new Error('El archivo vertical supera 8 MiB.');
  return archive;
}

// `runVertical` MUST call the local arq_vertical WASM; never use the saved
// model as a source of geometry. Caller may adopt only AFTER full equality.
export function verifyVerticalArchive(document, demoRules, runVertical) {
  if (!keysAre(document, ['format', 'request', 'model']) || document.format !== verticalArchiveFormat ||
      !keysAre(document.request, ['format', 'typology', 'input', 'candidate_id', 'declared_vertical']) ||
      document.request.format !== verticalRequestFormat || bytes(document) > maxArchiveBytes) {
    throw new Error('Archivo vertical desconocido, antiguo o demasiado grande.');
  }
  checkWebInput(document.request.input, demoRules);
  const actual = runVertical(document.request); // strict validation and replay of the v8 source in Rust
  checkModel(document.request, actual);
  if (!sameJson(document.model, actual)) {
    throw new Error('El modelo vertical guardado difiere del replay íntegro de Rust; no se abrió.');
  }
  return { request: structuredClone(document.request), model: actual };
}

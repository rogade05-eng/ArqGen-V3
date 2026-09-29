// Separate, opt-in batch format. Not a workspace/portfolio record: it never
// silently saves or changes a project, and every import replays ALL seeds in Rust.
import { checkWebInput, maxArchiveBytes, sameJson } from './archive.js';

export const explorationLimit = 12;
export const explorationFormat = 'arqgen-illustrative-seed-exploration-v1';

function onlyKeys(value, names) {
  return value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === names.length && names.every((key) => Object.hasOwn(value, key));
}
function validCount(value) { return Number.isInteger(value) && value >= 2 && value <= explorationLimit; }
function withinLimit(value) {
  if (new TextEncoder().encode(JSON.stringify(value)).length > maxArchiveBytes) {
    throw new Error('La exploración supera 8 MiB; el archivo no se admite.');
  }
}

export function makeExplorationArchive(input, seedCount, result) {
  if (input?.request_schema !== 'arqgen-brief-v8' || !validCount(seedCount) ||
      !['ok', 'infeasible'].includes(result?.status) || result.seed_count !== seedCount ||
      result.base_seed !== input.seed || result.exploration_method !== 'bounded-seed-sweep-v1') {
    throw new Error('No hay una exploración válida para descargar.');
  }
  const document = structuredClone({ format: explorationFormat, input, seed_count: seedCount, exploration: result });
  withinLimit(document);
  return document;
}

// `explore` MUST call arq_explore in local WASM; no archive SVG is rendered.
// The caller commits only this newly regenerated result after the whole replay.
export function verifyExplorationArchive(document, demoRules, explore) {
  if (!onlyKeys(document, ['format', 'input', 'seed_count', 'exploration']) ||
      document.format !== explorationFormat || !validCount(document.seed_count)) {
    throw new Error('Archivo de exploración desconocido, antiguo o con estructura inválida.');
  }
  withinLimit(document);
  checkWebInput(document.input, demoRules);
  const actual = explore(document.input, document.seed_count);
  if (!['ok', 'infeasible'].includes(actual?.status) || !sameJson(document.exploration, actual)) {
    throw new Error('El lote no coincide íntegramente con la ejecución Rust local: no se abrió.');
  }
  return { input: structuredClone(document.input), seed_count: document.seed_count, result: actual };
}

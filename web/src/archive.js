// Imported files are untrusted. Never render their SVG or adopt their claims:
// re-run every input through the local Rust WASM core and use ONLY its response.
import { archiveScenario, comparisonReport, hypothesisFields } from './comparison.js';

export const maxArchiveBytes = 8 * 1024 * 1024;

function hasOnlyKeys(value, expected) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const keys = Object.keys(value).sort();
  const allowed = [...expected].sort();
  return keys.length === allowed.length && keys.every((key, i) => key === allowed[i]);
}

// Structural equality independent of JSON object-key order; bounded and iterative
// so a crafted, deeply nested result cannot overflow the JS call stack.
export function sameJson(a, b) {
  const pending = [[a, b]];
  let visited = 0;
  while (pending.length) {
    if (++visited > 150_000) throw new Error('Archivo demasiado complejo.');
    const [left, right] = pending.pop();
    if (left === right) continue;
    if (!left || !right || typeof left !== 'object' || typeof right !== 'object' ||
        Array.isArray(left) !== Array.isArray(right)) return false;
    if (Array.isArray(left)) {
      if (left.length !== right.length) return false;
      for (let i = 0; i < left.length; i++) pending.push([left[i], right[i]]);
    } else {
      const keys = Object.keys(left).sort();
      const other = Object.keys(right).sort();
      if (keys.length !== other.length || keys.some((key, i) => key !== other[i])) return false;
      for (const key of keys) pending.push([left[key], right[key]]);
    }
  }
  return true;
}

export function parseArchiveText(text) {
  if (typeof text !== 'string' || !text || new TextEncoder().encode(text).length > maxArchiveBytes) {
    throw new Error('Archivo vacío o mayor de 8 MiB.');
  }
  try { return JSON.parse(text); }
  catch { throw new Error('El archivo no contiene JSON válido.'); }
}

export function checkWebInput(input, demoRules) {
  if (input?.request_schema !== 'arqgen-brief-v8') {
    throw new Error('Entrada antigua o incompatible: se requiere arqgen-brief-v8; no se migra automáticamente.');
  }
  if (!hasOnlyKeys(input, ['request_schema', 'site', 'program', 'project_context', 'seed', 'rules']) ||
      !hasOnlyKeys(input.site,
        ['width', 'depth', 'front_orientation', 'plot_outline', 'front_approach', 'reservation_provenance', 'reserved_areas']) ||
      !hasOnlyKeys(input.site.front_approach, ['provenance', 'shape', 'width', 'front_x', 'turn_y']) ||
      input.site.front_approach.provenance !== 'user_sketch_unverified' ||
      !Number.isFinite(input.site.front_approach.width) ||
      !((input.site.front_approach.shape === 'straight_front_strip' &&
          input.site.front_approach.front_x === null && input.site.front_approach.turn_y === null) ||
        (input.site.front_approach.shape === 'orthogonal_front_detour' &&
          Number.isFinite(input.site.front_approach.front_x) &&
          Number.isFinite(input.site.front_approach.turn_y))) ||
      !hasOnlyKeys(input.site.plot_outline, ['provenance', 'shape', 'rear_notches']) ||
      input.site.plot_outline.provenance !== 'user_sketch_unverified' ||
      !Array.isArray(input.site.plot_outline.rear_notches) ||
      input.site.plot_outline.rear_notches.length > 2 ||
      input.site.plot_outline.shape !== ['rectangle', 'rear_corner_notch', 'rear_both_corners_notched'][input.site.plot_outline.rear_notches.length] ||
      input.site.plot_outline.rear_notches.some((cut) => !hasOnlyKeys(cut, ['side', 'width', 'depth']) ||
        !['left', 'right'].includes(cut.side)) ||
      (input.site.plot_outline.rear_notches.length === 2 &&
        input.site.plot_outline.rear_notches[0].side === input.site.plot_outline.rear_notches[1].side) ||
      input.site.reservation_provenance !== 'user_sketch_unverified' ||
      !Array.isArray(input.site.reserved_areas) || input.site.reserved_areas.length > 2 ||
      input.site.reserved_areas.some((area) => !hasOnlyKeys(area, ['x', 'y', 'width', 'depth'])) ||
      !hasOnlyKeys(input.project_context,
        ['jurisdiction', 'housing_class', 'occupants', 'accessibility_needs', 'provenance']) ||
      !input.rules || typeof input.rules !== 'object' || Array.isArray(input.rules) ||
      !input.rules.bath_pressure || typeof input.rules.bath_pressure !== 'object' ||
      Array.isArray(input.rules.bath_pressure) || !demoRules?.bath_pressure) {
    throw new Error('Entrada incompleta o desconocida.');
  }
  const fixed = structuredClone(input.rules);
  const demo = structuredClone(demoRules);
  for (const field of hypothesisFields) {
    delete fixed.bath_pressure[field];
    delete demo.bath_pressure[field];
  }
  if (!sameJson(fixed, demo)) {
    throw new Error('Reglas incompatibles: esta interfaz solo puede editar tres hipótesis del ruleset demo actual.');
  }
}

function replayScenario(record, demoRules, generate) {
  if (!hasOnlyKeys(record, ['input', 'generation'])) {
    throw new Error('Faltan entrada y respuesta de un escenario.');
  }
  checkWebInput(record.input, demoRules);
  const actual = generate(record.input);
  if (!['ok', 'infeasible'].includes(actual?.status)) {
    throw new Error('La entrada no pasa la validación del núcleo Rust actual.');
  }
  if (!sameJson(record.generation, actual)) {
    throw new Error('La respuesta guardada difiere del núcleo Rust actual; no se importó ningún plano.');
  }
  return { input: structuredClone(record.input), generation: actual };
}

function checkSelection(selection, result) {
  if (selection === null) return;
  if (!hasOnlyKeys(selection, ['input_hash', 'candidate_id', 'kind', 'chosen_at']) ||
      selection.input_hash !== result.input_hash ||
      selection.kind !== 'user_preference_preliminary' ||
      !result.alternatives.some(({ id }) => id === selection.candidate_id) ||
      typeof selection.chosen_at !== 'string' ||
      !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(selection.chosen_at) ||
      Number.isNaN(Date.parse(selection.chosen_at))) {
    throw new Error('La preferencia guardada es incoherente o pretende una aprobación no reconocida.');
  }
}

// All-or-nothing: callers update UI state only AFTER this function returns.
// generate(input) must call the actual local Rust core; never supply a cache.
export function verifyArchive(document, demoRules, generate) {
  if (!document || typeof document !== 'object' || Array.isArray(document)) {
    throw new Error('El archivo debe contener un objeto JSON.');
  }
  if (['arqgen-illustrative-comparison-v1', 'arqgen-illustrative-comparison-v2', 'arqgen-illustrative-comparison-v3', 'arqgen-illustrative-comparison-v4', 'arqgen-illustrative-comparison-v5', 'arqgen-illustrative-comparison-v6', 'arqgen-illustrative-comparison-v7'].includes(document.format)) {
    throw new Error('Comparativa de versión anterior: no se migra automáticamente.');
  }
  if (document.format === 'arqgen-illustrative-comparison-v8') {
    if (!Array.isArray(document.scenarios) || document.scenarios.length < 2 || document.scenarios.length > 3) {
      throw new Error('Una comparativa contiene exactamente 2 o 3 corridas.');
    }
    let records = [];
    for (const entry of document.scenarios) {
      const verified = replayScenario(entry, demoRules, generate);
      const attempt = archiveScenario(records, verified.input, verified.generation);
      if (attempt.reason !== 'saved') throw new Error(`Corridas incompatibles: ${attempt.reason}.`);
      records = attempt.records;
    }
    if (!sameJson(document, comparisonReport(records))) {
      throw new Error('Los metadatos de la comparativa no coinciden con las corridas verificadas.');
    }
    return { kind: 'comparison', records, focus: records[0] };
  }
  if (!hasOnlyKeys(document, ['input', 'generation', 'selection'])) {
    throw new Error('Formato de archivo desconocido o contiene declaraciones adicionales.');
  }
  const verified = replayScenario({ input: document.input, generation: document.generation }, demoRules, generate);
  if (archiveScenario([], verified.input, verified.generation).reason !== 'saved') {
    throw new Error('Respuesta no apta para restaurar una corrida.');
  }
  checkSelection(document.selection, verified.generation);
  return { kind: 'single', records: [], focus: verified };
}

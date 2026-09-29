// Explicit, opt-in local snapshots. Stored results are never trusted on reopening:
// each one must match a fresh execution of the current Rust WASM engine.
import { maxArchiveBytes, verifyArchive } from './archive.js';
import { archiveScenario, comparisonKey, comparisonLimit } from './comparison.js';

export const workspaceFormat = 'arqgen-local-workspace-v8';
const databaseName = 'arqgen-workspace-v1';
const storeName = 'snapshots';
const slot = 'current';

function keysAre(value, names) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const keys = Object.keys(value).sort();
  const expected = [...names].sort();
  return keys.length === expected.length && keys.every((key, index) => key === expected[index]);
}

function withinLimit(value) {
  if (new TextEncoder().encode(JSON.stringify(value)).length > maxArchiveBytes) {
    throw new Error('La copia supera 8 MiB. Descarga los JSON por separado.');
  }
}

export function snapshotWorkspace(evaluated, records) {
  if (!evaluated || !Array.isArray(records) || records.length > comparisonLimit ||
      !['ok', 'infeasible'].includes(evaluated.generation?.status)) {
    throw new Error('No hay una corrida actual válida para guardar.');
  }
  const version = evaluated.generation.engine_version;
  let checked = [];
  for (const { input, generation } of records) {
    const attempt = archiveScenario(checked, input, generation);
    if (attempt.reason !== 'saved' || generation.engine_version !== version ||
        comparisonKey(input) !== comparisonKey(evaluated.input)) {
      throw new Error('El cuaderno no corresponde al encargo y motor actuales.');
    }
    checked = attempt.records;
  }
  const document = structuredClone({
    format: workspaceFormat,
    engine_version: version,
    focus: { input: evaluated.input, generation: evaluated.generation, selection: null },
    scenarios: checked,
  });
  withinLimit(document);
  return document;
}

// Fail atomically. Only caller commits the returned, freshly generated values to UI.
export function verifyWorkspace(document, demoRules, generate) {
  if (['arqgen-local-workspace-v1', 'arqgen-local-workspace-v2', 'arqgen-local-workspace-v3', 'arqgen-local-workspace-v4', 'arqgen-local-workspace-v5', 'arqgen-local-workspace-v6', 'arqgen-local-workspace-v7'].includes(document?.format)) {
    throw new Error('Copia local de versión anterior: no se migra automáticamente. Descarga sus archivos con la versión original si necesitas conservarlos.');
  }
  if (!keysAre(document, ['format', 'engine_version', 'focus', 'scenarios']) ||
      document.format !== workspaceFormat ||
      !Array.isArray(document.scenarios) || document.scenarios.length > comparisonLimit ||
      !keysAre(document.focus, ['input', 'generation', 'selection']) || document.focus.selection !== null) {
    throw new Error('Copia local desconocida o con estructura inválida.');
  }
  withinLimit(document);
  const focus = verifyArchive(document.focus, demoRules, generate).focus;
  if (document.engine_version !== focus.generation.engine_version) {
    throw new Error('La versión del motor de la copia no coincide.');
  }
  let records = [];
  for (const entry of document.scenarios) {
    if (!keysAre(entry, ['input', 'generation'])) throw new Error('Escenario guardado desconocido.');
    const checked = verifyArchive({ ...entry, selection: null }, demoRules, generate).focus;
    const attempt = archiveScenario(records, checked.input, checked.generation);
    if (attempt.reason !== 'saved' || checked.generation.engine_version !== document.engine_version ||
        comparisonKey(checked.input) !== comparisonKey(focus.input)) {
      throw new Error('La copia mezcla encargos, corridas o versiones incompatibles.');
    }
    records = attempt.records;
  }
  return { focus, records };
}

function transact(mode, action) {
  if (typeof indexedDB === 'undefined') {
    return Promise.reject(new Error('El almacenamiento local no está disponible en este navegador.'));
  }
  return new Promise((resolve, reject) => {
    const open = indexedDB.open(databaseName, 1);
    open.onupgradeneeded = () => { open.result.createObjectStore(storeName); };
    open.onerror = () => reject(open.error || new Error('No se pudo abrir el almacenamiento local.'));
    open.onsuccess = () => {
      const db = open.result;
      let request;
      try {
        const transaction = db.transaction(storeName, mode);
        request = action(transaction.objectStore(storeName));
        transaction.oncomplete = () => { db.close(); resolve(request.result ?? null); };
        transaction.onabort = () => { db.close(); reject(transaction.error || new Error('Operación local cancelada.')); };
        transaction.onerror = () => { db.close(); reject(transaction.error || new Error('Error al acceder a la copia local.')); };
      } catch (error) {
        db.close();
        reject(error);
      }
    };
  });
}

export const saveLocalWorkspace = (document) => transact('readwrite', (store) => store.put(document, slot));
export const readLocalWorkspace = () => transact('readonly', (store) => store.get(slot));
export const removeLocalWorkspace = () => transact('readwrite', (store) => store.delete(slot));

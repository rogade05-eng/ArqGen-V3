// A bounded, opt-in portfolio of independent conceptual jobs. Metadata is
// untrusted; no stored SVG or result is displayed until every saved run has
// been reproduced by the current Rust WASM engine. No approval/audit claim.
import { sameJson } from './archive.js';
import { snapshotWorkspace, verifyWorkspace, workspaceFormat } from './workspace.js';

export const portfolioFormat = 'arqgen-illustrative-portfolio-v1';
export const portfolioLimit = 8;
export const maxPortfolioBytes = 16 * 1024 * 1024;
const databaseName = 'arqgen-portfolio-v1'; // Separate from the legacy single snapshot.
const storeName = 'projects';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const keysAre = (value, names) => value && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).length === names.length && names.every((name) => Object.hasOwn(value, name));
const newId = () => {
  if (!globalThis.crypto?.randomUUID) throw new Error('Este origen no ofrece identificadores aleatorios seguros.');
  return crypto.randomUUID();
};

function sizeOf(value) {
  const serialized = JSON.stringify(value);
  if (!serialized) throw new Error('Documento de cartera inválido.');
  return new TextEncoder().encode(serialized).byteLength;
}
function withinLimit(value) {
  if (sizeOf(value) > maxPortfolioBytes) throw new Error('La cartera supera 16 MiB. Exporta y libera proyectos antes de guardar.');
}
function validDate(value) {
  return typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value) &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}
export function projectName(value) {
  if (typeof value !== 'string') throw new Error('Escribe un nombre de proyecto.');
  const name = value.trim();
  if (!name || name.length > 80 || /[\u0000-\u001f\u007f]/.test(name)) {
    throw new Error('El nombre debe tener entre 1 y 80 caracteres y no contener saltos de línea ni controles.');
  }
  return name;
}
function checkEntry(entry) {
  if (!keysAre(entry, ['id', 'edit_token', 'name', 'updated_at', 'snapshot']) ||
      typeof entry.id !== 'string' || !uuid.test(entry.id) ||
      typeof entry.edit_token !== 'string' || !uuid.test(entry.edit_token) ||
      projectName(entry.name) !== entry.name || !validDate(entry.updated_at) ||
      entry.snapshot?.format !== workspaceFormat) {
    throw new Error('Proyecto desconocido, antiguo o con metadatos inválidos: no se usa su contenido.');
  }
}
function checkList(entries, allowEmpty = true) {
  if (!Array.isArray(entries) || entries.length > portfolioLimit || (!allowEmpty && !entries.length)) {
    throw new Error(`La cartera admite entre 1 y ${portfolioLimit} proyectos para exportar.`);
  }
  withinLimit(entries);
  const seen = new Set();
  for (const entry of entries) {
    checkEntry(entry);
    if (seen.has(entry.id)) throw new Error('La cartera repite un identificador de proyecto.');
    seen.add(entry.id);
  }
  return entries;
}

export function newProject(name, evaluated, records, options = {}) {
  const entry = {
    id: options.id ?? newId(), edit_token: options.edit_token ?? newId(),
    name: projectName(name), updated_at: options.updated_at ?? new Date().toISOString(),
    snapshot: snapshotWorkspace(evaluated, records),
  };
  checkList([entry], false);
  return entry;
}
export function revisedProject(previous, name, evaluated, records, options = {}) {
  checkEntry(previous);
  const entry = newProject(name, evaluated, records, {
    id: previous.id, edit_token: options.edit_token ?? newId(),
    updated_at: options.updated_at ?? new Date().toISOString(),
  });
  if (entry.edit_token === previous.edit_token) throw new Error('La revisión necesita un identificador de edición nuevo.');
  return entry;
}

// Export and import are both fail-closed: replay ALL entries before returning
// any data. The names/dates are labels, not authenticated authorship.
function replayEntries(entries, demoRules, generate) {
  checkList(entries, false);
  let engineVersion = null;
  const verified = entries.map((entry) => {
    const { focus, records } = verifyWorkspace(entry.snapshot, demoRules, generate);
    if (engineVersion && entry.snapshot.engine_version !== engineVersion) {
      throw new Error('La cartera mezcla versiones distintas del motor.');
    }
    engineVersion = entry.snapshot.engine_version;
    const canonical = snapshotWorkspace(focus, records);
    if (!sameJson(entry.snapshot, canonical)) throw new Error('El proyecto difiere de las corridas regeneradas.');
    return structuredClone({ ...entry, snapshot: canonical });
  });
  return { engineVersion, verified };
}
export function exportPortfolio(entries, demoRules, generate, exportedAt = new Date().toISOString()) {
  if (!validDate(exportedAt)) throw new Error('Fecha de exportación inválida.');
  const { engineVersion, verified } = replayEntries(entries, demoRules, generate);
  const document = { format: portfolioFormat, engine_version: engineVersion, exported_at: exportedAt, entries: verified };
  withinLimit(document);
  return document;
}
export function verifyPortfolio(document, demoRules, generate) {
  if (!keysAre(document, ['format', 'engine_version', 'exported_at', 'entries']) ||
      document.format !== portfolioFormat || !validDate(document.exported_at)) {
    throw new Error('Respaldo de cartera desconocido; no se migran formatos anteriores.');
  }
  withinLimit(document);
  const { engineVersion, verified } = replayEntries(document.entries, demoRules, generate);
  if (document.engine_version !== engineVersion) throw new Error('La versión declarada no coincide con las corridas.');
  return verified;
}
export function parsePortfolioText(text) {
  if (typeof text !== 'string' || !text || new TextEncoder().encode(text).byteLength > maxPortfolioBytes) {
    throw new Error('Respaldo vacío o mayor de 16 MiB.');
  }
  try { return JSON.parse(text); }
  catch { throw new Error('El respaldo no contiene JSON válido.'); }
}

// IndexedDB transactions are the commit boundary. A read-modify-write occurs
// inside ONE readwrite transaction; edit_token prevents silent lost updates in
// another tab. Failed imports abort without deleting previous projects.
function transaction(mode, action) {
  if (typeof indexedDB === 'undefined') {
    return Promise.reject(new Error('IndexedDB no está disponible en este navegador.'));
  }
  return new Promise((resolve, reject) => {
    let open;
    try { open = indexedDB.open(databaseName, 1); }
    catch (error) { reject(error); return; }
    open.onupgradeneeded = () => { open.result.createObjectStore(storeName, { keyPath: 'id' }); };
    open.onerror = () => reject(open.error || new Error('No se pudo abrir la cartera.'));
    open.onsuccess = () => {
      const db = open.result;
      let problem;
      let result;
      let tx;
      try { tx = db.transaction(storeName, mode); }
      catch (error) { db.close(); reject(error); return; }
      tx.oncomplete = () => { db.close(); resolve(result); };
      tx.onabort = () => { db.close(); reject(problem || tx.error || new Error('Operación de cartera cancelada.')); };
      const fail = (error) => {
        problem = error instanceof Error ? error : new Error(String(error));
        try { tx.abort(); } catch { /* already aborted */ }
      };
      const done = (value) => { result = value; };
      try { action(tx.objectStore(storeName), done, fail); }
      catch (error) { fail(error); }
    };
  });
}
export async function listProjects() {
  const entries = await transaction('readonly', (store, done) => {
    store.getAll().onsuccess = (event) => { done(event.target.result); };
  });
  checkList(entries);
  return entries.sort((a, b) => b.updated_at.localeCompare(a.updated_at) || a.id.localeCompare(b.id));
}
export async function readProject(id) {
  if (typeof id !== 'string' || !uuid.test(id)) throw new Error('Identificador de proyecto inválido.');
  const entry = await transaction('readonly', (store, done) => {
    store.get(id).onsuccess = (event) => { done(event.target.result ?? null); };
  });
  if (entry) checkEntry(entry);
  return entry;
}
export function saveProject(entry, expectedToken = null) {
  checkList([entry], false);
  if (expectedToken !== null && (typeof expectedToken !== 'string' || !uuid.test(expectedToken))) {
    throw new Error('Revisión anterior inválida.');
  }
  return transaction('readwrite', (store, done, fail) => {
    store.getAll().onsuccess = (event) => {
      try {
        const entries = checkList(event.target.result);
        const existing = entries.find((item) => item.id === entry.id);
        if ((expectedToken === null && existing) || (expectedToken !== null && existing?.edit_token !== expectedToken)) {
          throw new Error('Conflicto: este proyecto fue cambiado o eliminado en otra pestaña. Reábrelo antes de actualizar.');
        }
        checkList([...entries.filter((item) => item.id !== entry.id), entry], false);
        store.put(entry);
        done(entry);
      } catch (error) { fail(error); }
    };
  });
}
export function deleteProject(id, expectedToken) {
  if (typeof id !== 'string' || !uuid.test(id) || typeof expectedToken !== 'string' || !uuid.test(expectedToken)) {
    throw new Error('Identificador o revisión inválidos.');
  }
  return transaction('readwrite', (store, done, fail) => {
    store.get(id).onsuccess = (event) => {
      const entry = event.target.result;
      if (!entry || entry.edit_token !== expectedToken) {
        fail(new Error('Conflicto: el proyecto cambió en otra pestaña; no se borró.')); return;
      }
      store.delete(id);
      done(true);
    };
  });
}
export function replacePortfolio(document, demoRules, generate) {
  const verified = verifyPortfolio(document, demoRules, generate);
  // Invalidate bindings held by other tabs (import never silently overwrites an
  // ongoing edit from a tab still holding its old edit_token).
  const entries = verified.map((entry) => ({ ...entry, edit_token: newId() }));
  checkList(entries, false);
  return transaction('readwrite', (store, done) => {
    store.clear();
    for (const entry of entries) store.add(entry);
    done(entries);
  });
}

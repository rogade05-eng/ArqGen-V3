// One bounded binary bridge for single runs, worker-only multi-seed runs,
// and versioned, explicitly declared vertical data (never part of v8 replay).
// Never trust a saved output; the caller must replay through the local WASM.
export async function loadCore() {
  // With Vite base './', a built worker lives under assets/ whereas the
  // document is at the app root. Resolve from the worker URL, not its cwd.
  const path = typeof document === 'undefined'
    ? new URL('../core.wasm', self.location.href).href
    : `${import.meta.env.BASE_URL}core.wasm`;
  const response = await fetch(path);
  if (!response.ok) throw new Error(`No se encontró ${path}. Ejecuta npm run build:core.`);
  const { instance } = await WebAssembly.instantiate(await response.arrayBuffer());
  return instance.exports;
}

export function callCore(engine, operation, input) {
  if (!['arq_generate', 'arq_explore', 'arq_vertical'].includes(operation) || typeof engine?.[operation] !== 'function') {
    throw new Error('Operación no disponible en el núcleo Rust local.');
  }
  const bytes = new TextEncoder().encode(JSON.stringify(input));
  if (!bytes.length || bytes.length > 256 * 1024) throw new Error('La solicitud supera 256 KiB.');
  const pointer = engine.arq_alloc(bytes.length);
  if (!pointer) throw new Error('No se reservó memoria para la solicitud.');
  new Uint8Array(engine.memory.buffer, pointer, bytes.length).set(bytes);
  let packed;
  try { packed = engine[operation](pointer, bytes.length); }
  finally { engine.arq_free(pointer, bytes.length); }
  const outPointer = Number(packed & 0xffffffffn);
  const outLength = Number(packed >> 32n);
  if (!outPointer || outLength < 1 || outLength > 2_000_000) {
    // A corrupt/oversize WASM response cannot be consumed. The caller drops
    // this module instance; no malformed output may be adopted by the UI.
    throw new Error('Respuesta de motor inválida o mayor de 2 MB.');
  }
  let output;
  try { output = new TextDecoder('utf-8', { fatal: true }).decode(new Uint8Array(engine.memory.buffer, outPointer, outLength)); }
  finally { engine.arq_free(outPointer, outLength); }
  return JSON.parse(output);
}

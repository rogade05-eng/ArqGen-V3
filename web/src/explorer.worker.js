// Disposable worker: termination really interrupts the synchronous Rust sweep.
// Loading, generation and replay remain off the editor's main thread.
import knowledge from '../../knowledge/generic-house.json';
import { loadCore, callCore } from './core-client.js';
import { verifyExplorationArchive } from './exploration.js';

self.onmessage = async ({ data }) => {
  try {
    const core = await loadCore();
    const explore = (input, count) => callCore(core, 'arq_explore', { input, seed_count: count });
    if (data?.type === 'explore') {
      const result = explore(data.input, data.seed_count);
      if (!['ok', 'infeasible'].includes(result?.status)) {
        throw new Error(result?.message || 'Rust rechazó el lote.');
      }
      self.postMessage({ type: 'explore', result });
    } else if (data?.type === 'verify') {
      const verified = verifyExplorationArchive(data.document, knowledge, explore);
      self.postMessage({ type: 'verify', verified });
    } else throw new Error('Operación de exploración desconocida.');
  } catch (error) {
    self.postMessage({ type: 'error', message: error instanceof Error ? error.message : String(error) });
  }
};

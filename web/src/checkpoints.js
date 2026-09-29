// Bounded UNPERSISTED history of fully evaluated checkpoints, not a keystroke
// editor or an approval/audit log. Every restored state is replayed by Rust.
import { sameJson } from './archive.js';
import { snapshotWorkspace, verifyWorkspace } from './workspace.js';

export const checkpointLimit = 12;
export const maxCheckpointBytes = 16 * 1024 * 1024;
export function createCheckpoints(demoRules, generate) {
  let states = [];
  let cursor = -1;
  const capture = (evaluated, records) => {
    const document = snapshotWorkspace(evaluated, records);
    return { document, bytes: new TextEncoder().encode(JSON.stringify(document)).byteLength };
  };
  const status = () => ({ position: cursor + 1, total: states.length,
    canUndo: cursor > 0, canRedo: cursor >= 0 && cursor < states.length - 1 });
  return {
    status,
    reset(evaluated, records) {
      states = [capture(evaluated, records)];
      cursor = 0;
      return status();
    },
    record(evaluated, records) {
      const step = capture(evaluated, records);
      if (cursor >= 0 && sameJson(states[cursor].document, step.document)) return status();
      states = states.slice(0, cursor + 1);
      states.push(step);
      let bytes = states.reduce((total, entry) => total + entry.bytes, 0);
      while (states.length > 1 && (states.length > checkpointLimit || bytes > maxCheckpointBytes)) {
        bytes -= states.shift().bytes;
      }
      cursor = states.length - 1;
      return status();
    },
    // prepare() has no side effects. A failed replay or a failed form render
    // cannot advance the cursor and leave UI and history out of sync.
    prepare(delta) {
      if (![-1, 0, 1].includes(delta)) throw new Error('Paso de historial inválido.');
      const target = cursor + delta;
      if (target < 0 || target >= states.length) throw new Error('No hay otra corrida validada en esa dirección.');
      const { focus, records } = verifyWorkspace(states[target].document, demoRules, generate);
      return { focus, records, target };
    },
    commit(prepared) {
      if (!Number.isInteger(prepared?.target) || prepared.target < 0 || prepared.target >= states.length) {
        throw new Error('Paso de historial inexistente.');
      }
      cursor = prepared.target;
      return status();
    },
  };
}

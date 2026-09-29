// Check provenance of already supplied reference PDFs without storing copies in
// the app or treating any reference as an executable regulatory ruleset.
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

export async function auditSources(directory, inventory) {
  if (!Array.isArray(inventory?.documents)) throw new Error('Inventario de fuentes inválido.');
  const results = [];
  for (const entry of inventory.documents) {
    if (typeof entry.file !== 'string' || !entry.file || basename(entry.file) !== entry.file ||
        !/^[a-f0-9]{64}$/.test(entry.sha256)) throw new Error('Nombre o digest de fuente inválido.');
    let bytes;
    try { bytes = await readFile(join(directory, entry.file)); }
    catch (error) {
      if (error.code !== 'ENOENT') throw error;
      results.push({ file: entry.file, status: 'missing' });
      continue;
    }
    const hash = createHash('sha256').update(bytes).digest('hex');
    results.push({ file: entry.file,
      status: bytes.subarray(0, 5).toString() === '%PDF-' && hash === entry.sha256 ? 'matches' : 'mismatch' });
  }
  return results;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const inventory = JSON.parse(await readFile(join(root, 'knowledge/source-manifest.json'), 'utf8'));
  const directory = resolve(process.argv[2] || root);
  const result = await auditSources(directory, inventory);
  for (const { file, status } of result) console.log(`${status.padEnd(9)} ${file}`);
  console.log(`${result.filter((row) => row.status === 'matches').length}/${result.length} PDF coinciden con el inventario; esto NO verifica vigencia ni aplicación normativa.`);
  if (result.some((row) => row.status !== 'matches')) process.exitCode = 1;
}

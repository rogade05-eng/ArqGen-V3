// A synthetic PE header tests ONLY the ZIP packager; it is not an executable
// product and never leaves the OS temp directory. Native app QA stays separate.
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { inspectWindowsGuiX64, packageWindowsRelease } from '../../scripts/package-windows.mjs';

function syntheticHeader({ machine = 0x8664, subsystem = 2 } = {}) {
  const bytes = Buffer.alloc(68 * 1024);
  bytes.write('MZ', 0, 'ascii');
  bytes.writeUInt32LE(0x80, 0x3c);
  bytes.write('PE\0\0', 0x80, 'binary');
  bytes.writeUInt16LE(machine, 0x84);
  bytes.writeUInt16LE(1, 0x86); // one section (a structural fixture only)
  bytes.writeUInt16LE(240, 0x94); // PE32+ optional header length
  bytes.writeUInt16LE(2, 0x96); // executable flag
  bytes.writeUInt16LE(0x20b, 0x98); // PE32+ format
  bytes.writeUInt16LE(subsystem, 0x80 + 24 + 68);
  return bytes;
}

test('Windows ZIP refuses missing, non-PE, x86 and debug/console binaries', async () => {
  assert.throws(() => inspectWindowsGuiX64(Buffer.from('EXE de texto')), /No es un ejecutable PE/);
  assert.throws(() => inspectWindowsGuiX64(syntheticHeader({ machine: 0x14c })), /Windows x64/);
  assert.throws(() => inspectWindowsGuiX64(syntheticHeader({ subsystem: 3 })), /RELEASE/);
  const temp = await mkdtemp(join(tmpdir(), 'arqgen-zip-test-'));
  try {
    const exe = join(temp, 'no-existe.exe');
    await assert.rejects(packageWindowsRelease({ exePath: exe, targetDir: temp, outputPath: join(temp, 'salida.zip') }),
      { code: 'ENOENT' });
  } finally { await rm(temp, { recursive: true, force: true }); }
});

test('Windows ZIP preserves bytes and includes a directory, checksum and prototype warning', async () => {
  const temp = await mkdtemp(join(tmpdir(), 'arqgen-zip-test-'));
  try {
    const targetDir = join(temp, 'target');
    const releaseDir = join(targetDir, 'release');
    await mkdir(releaseDir, { recursive: true });
    const exe = join(releaseDir, 'arqgen-desktop.exe');
    await writeFile(exe, syntheticHeader()); // NEVER presented as a real app
    const zipPath = join(temp, 'artifacts', 'prueba.zip');
    const result = await packageWindowsRelease({ exePath: exe, outputPath: zipPath, targetDir });
    assert.equal(result.zip, zipPath);
    assert.match(result.exeSha256, /^[a-f0-9]{64}$/);
    assert.match(result.zipSha256, /^[a-f0-9]{64}$/);
    assert.equal((await readFile(zipPath)).toString('ascii', 0, 2), 'PK');
    if (process.platform !== 'win32') {
      const files = spawnSync('unzip', ['-Z1', zipPath], { encoding: 'utf8' });
      assert.equal(files.status, 0, files.stderr);
      assert.match(files.stdout, /ARQ-GEN-Windows-x64-0\.21\.0\/arqgen-desktop\.exe/);
      assert.match(files.stdout, /SHA256SUMS\.txt/);
      assert.match(files.stdout, /LEEME-ANTES-DE-USAR\.txt/);
      const doc = spawnSync('unzip', ['-p', zipPath, 'ARQ-GEN-Windows-x64-0.21.0/LEEME-ANTES-DE-USAR.txt'], { encoding: 'utf8' });
      assert.match(doc.stdout, /NO APTO PARA OBRA/);
      assert.match(doc.stdout, /no un instalador/);
    }
  } finally { await rm(temp, { recursive: true, force: true }); }
});

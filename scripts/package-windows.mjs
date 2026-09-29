#!/usr/bin/env node
// Package ONLY a completed Windows x64 *release* Tauri executable. This script
// does not compile an .exe, emulate Windows, or certify that it runs in WebView2.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFile, mkdir, mkdtemp, readFile, realpath, rename, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, dirname, extname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const config = JSON.parse(await readFile(resolve(root, 'web/src-tauri/tauri.conf.json'), 'utf8'));
const name = 'arqgen-desktop.exe';
const folder = `ARQ-GEN-Windows-x64-${config.version}`;
const defaultTarget = resolve(root, 'web/src-tauri/target');
const defaultExe = resolve(defaultTarget, 'release', name);
const defaultZip = resolve(root, 'artifacts', `${folder}.zip`);
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');

/** Checks the PE header only; it does NOT prove provenance, signature or runtime behavior. */
export function inspectWindowsGuiX64(exe) {
  if (exe.length < 64 * 1024 || exe.length >= 1024 * 1024 * 1024 || exe.toString('ascii', 0, 2) !== 'MZ') {
    throw new Error('No es un ejecutable PE de Windows x64: cabecera MZ/tamaño inválidos.');
  }
  const offset = exe.readUInt32LE(0x3c);
  if (offset < 0x40 || offset + 24 + 70 > exe.length || exe.toString('binary', offset, offset + 4) !== 'PE\0\0') {
    throw new Error('No es un ejecutable PE: firma o desplazamiento PE inválido.');
  }
  if (exe.readUInt16LE(offset + 4) !== 0x8664 || exe.readUInt16LE(offset + 6) < 1 ||
      !(exe.readUInt16LE(offset + 22) & 0x0002) || exe.readUInt16LE(offset + 20) < 70 ||
      exe.readUInt16LE(offset + 24) !== 0x20b) {
    throw new Error('Se exige un PE32+ ejecutable para Windows x64 (no archivo web ni otra arquitectura).');
  }
  if (exe.readUInt16LE(offset + 24 + 68) !== 2) {
    throw new Error('El .exe debe ser una build RELEASE de interfaz Windows; debug/console no se distribuye.');
  }
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', maxBuffer: 1024 * 1024, ...options });
  if (result.error || result.status !== 0) {
    throw new Error(`${command} no creó/verificó el ZIP: ${result.error?.message || result.stderr || result.stdout || result.status}`);
  }
}

function psLiteral(value) { return `'${value.replaceAll("'", "''")}'`; }

/** targetDir override is ONLY for isolated unit tests; the CLI always uses this repo's target. */
export async function packageWindowsRelease({ exePath = defaultExe, outputPath = defaultZip, targetDir = defaultTarget } = {}) {
  const output = resolve(outputPath);
  if (extname(output).toLowerCase() !== '.zip') throw new Error('La salida debe ser un archivo .zip.');
  const path = await realpath(exePath); // refuses absent or dangling binary
  const target = await realpath(targetDir);
  const segments = relative(target, path).split(sep);
  if (basename(path).toLowerCase() !== name || !(
    (segments.length === 2 && segments[0] === 'release') ||
    (segments.length === 3 && segments[0] === 'x86_64-pc-windows-msvc' && segments[1] === 'release')
  )) {
    throw new Error('El .exe debe proceder de src-tauri/target/[x86_64-pc-windows-msvc/]release/arqgen-desktop.exe.');
  }
  if (output === path || output.startsWith(`${target}${sep}`)) throw new Error('No guardes el ZIP sobre el binario ni en target/.');
  const exe = await readFile(path);
  inspectWindowsGuiX64(exe);
  const digest = hash(exe);
  const staging = await mkdtemp(join(tmpdir(), 'arqgen-exe-zip-'));
  const stagedFolder = join(staging, folder);
  // Compress-Archive insists on a .zip destination; stage an atomic .zip.
  const partial = `${output}.partial.zip`;
  try {
    await mkdir(stagedFolder);
    await mkdir(dirname(output), { recursive: true });
    await copyFile(path, join(stagedFolder, name));
    await writeFile(join(stagedFolder, 'SHA256SUMS.txt'), `${digest}  ${name}\n`, 'utf8');
    await writeFile(join(stagedFolder, 'LEEME-ANTES-DE-USAR.txt'), [
      `ARQ GEN Experimental ${config.version} | Windows x64 | PROTOTIPO SIN CERTIFICAR`,
      '',
      `Este ZIP contiene ${name}, no un instalador. Necesita WebView2 instalado en Windows.`,
      'El runtime de WebView2 y el instalador NSIS offline NO vienen en este ZIP.',
      'Extrae la carpeta completa y verifica SHA256SUMS.txt antes de abrir el ejecutable.',
      'Este archivo no acredita firma de código, QA en tu Windows ni instalación sin internet.',
      'Anteproyecto conceptual: NO APTO PARA OBRA. Sin cumplimiento cubano ni ventilación verificada.',
      '',
      `SHA-256 del .exe: ${digest}`,
      '',
    ].join('\r\n'), 'utf8');
    await rm(partial, { force: true });
    if (process.platform === 'win32') {
      run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
        `$ErrorActionPreference='Stop'; Compress-Archive -Path ${psLiteral(stagedFolder)} -DestinationPath ${psLiteral(partial)} -CompressionLevel Optimal -Force`]);
      const check = join(staging, 'verificado');
      run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
        `$ErrorActionPreference='Stop'; Expand-Archive -LiteralPath ${psLiteral(partial)} -DestinationPath ${psLiteral(check)} -Force`]);
      assert.equal(hash(await readFile(join(check, folder, name))), digest, 'El EXE del ZIP debe conservar sus bytes.');
    } else {
      run('zip', ['-X', '-q', '-r', partial, folder], { cwd: staging });
      const check = join(staging, 'verificado');
      await mkdir(check);
      run('unzip', ['-q', partial, '-d', check]);
      assert.equal(hash(await readFile(join(check, folder, name))), digest, 'El EXE del ZIP debe conservar sus bytes.');
    }
    assert.ok((await stat(partial)).size > 0);
    await rm(output, { force: true });
    await rename(partial, output);
    return { zip: output, exeSha256: digest, zipSha256: hash(await readFile(output)) };
  } catch (error) {
    await rm(partial, { force: true });
    throw error;
  } finally { await rm(staging, { recursive: true, force: true }); }
}

function parseCli(args) {
  if (args.length % 2) throw new Error('Uso: node scripts/package-windows.mjs [--exe ruta/release/arqgen-desktop.exe] [--output ruta.zip]');
  const result = {};
  for (let i = 0; i < args.length; i += 2) {
    if (args[i] === '--exe' && !result.exePath) result.exePath = args[i + 1];
    else if (args[i] === '--output' && !result.outputPath) result.outputPath = args[i + 1];
    else throw new Error(`Parámetro desconocido o duplicado: ${args[i]}`);
    if (!result[args[i] === '--exe' ? 'exePath' : 'outputPath']) throw new Error('Falta una ruta de entrada/salida.');
  }
  return result;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  packageWindowsRelease(parseCli(process.argv.slice(2))).then(({ zip, exeSha256, zipSha256 }) => {
    console.log(`ZIP del .exe compilado: ${zip}\nSHA-256 .exe: ${exeSha256}\nSHA-256 ZIP: ${zipSha256}`);
  }).catch((error) => { console.error(`No se empaquetó ningún .exe: ${error.message}`); process.exitCode = 1; });
}

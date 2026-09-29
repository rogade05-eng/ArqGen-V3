#!/usr/bin/env bash
# Build the *actual* Tauri Windows x64 release on a Linux/macOS host using
# the officially documented MSVC target + cargo-xwin. Wine is not involved.
# This script never invents an EXE/ZIP when its toolchain is incomplete.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { printf 'CROSS-BUILD WINDOWS: NO REALIZADO: %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Linux|Darwin) ;;
  *) fail 'Usa Linux/macOS para cross-build; en Windows usa las instrucciones de docs/COMPILACION_WINDOWS_ZIP.md.' ;;
esac

# The ZIP packager only accepts web/src-tauri/target/..; a custom target dir
# could cause it to package an old build instead of the just-compiled binary.
[[ -z "${CARGO_TARGET_DIR:-}" ]] || fail 'Quita CARGO_TARGET_DIR: el empaquetador usa web/src-tauri/target/.'

for tool in node npm cargo rustc rustup cargo-xwin clang llvm-rc lld-link zip unzip; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    fail "Falta $tool. Instala Rust + cargo-xwin, LLVM/LLD y Node; ver docs/COMPILACION_WINDOWS_ZIP.md."
  fi
done

for target in wasm32-unknown-unknown x86_64-pc-windows-msvc; do
  if ! rustup target list --installed | grep -Fxq "$target"; then
    fail "Falta target Rust $target. Ejecuta: rustup target add $target"
  fi
done

printf 'Host: %s | Rust: %s | cargo-xwin: %s\n' "$(uname -s)" "$(rustc --version)" "$(cargo-xwin --version)"
export XWIN_CACHE_DIR="${XWIN_CACHE_DIR:-${HOME}/.cache/arqgen-xwin}"
mkdir -p "$XWIN_CACHE_DIR"

npm ci --prefix web
cargo test --locked --workspace
npm test --prefix web

# The Tauri beforeBuildCommand compiles the Rust core to WASM offline, builds
# the web resources and only then cross-compiles src-tauri to Windows MSVC.
npm run tauri --prefix web -- build --no-bundle --runner cargo-xwin --target x86_64-pc-windows-msvc

exe='web/src-tauri/target/x86_64-pc-windows-msvc/release/arqgen-desktop.exe'
[[ -s "$exe" ]] || fail "La build terminó sin el .exe esperado: $exe"
node scripts/package-windows.mjs --exe "$exe"
printf 'ZIP real generado solo tras la build; prueba su arranque en Windows/WebView2, no con Wine.\n'

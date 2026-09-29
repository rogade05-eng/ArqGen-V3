# Compilación Windows y ZIP del ejecutable

**Fecha: 2026-09-29. Estado: EXE Y ZIP TAURI NO GENERADOS en esta sesión.** No existe aquí un ejecutable Windows **del shell Tauri/WebView2**. Se compiló por separado una [alternativa Zig con navegador externo](EXE_ALTERNATIVO_ZIG.md) que **no** cumple ese criterio. `scripts/package-windows.mjs` **se niega** a producir un ZIP sin un `.exe` Tauri real de `release/`; nunca rellena el ZIP con un archivo ficticio, un script o el bundle web. Un test utiliza una cabecera PE sintética **solo en un directorio temporal** para comprobar el mecanismo ZIP y la borra al terminar; no es un producto.

## Comprobación solicitada: Wine en este contenedor Linux

- `wine`/`wine64`, `cargo`, `rustc`, `rustup`, `cargo-xwin`, LLVM y el target `x86_64-pc-windows-msvc` **no están instalados**. `npm run tauri --prefix web -- build --no-bundle --target x86_64-pc-windows-msvc --runner cargo-xwin` falla en `cargo metadata: No such file or directory`. `npm run build --prefix web` falla por ausencia de Cargo antes de compilar el núcleo.
- Se intentó instalar dependencias desde Debian (`sudo apt-get update`): los repositorios `deb.debian.org` devolvieron `Connection failed`. Las descargas directas de `static.rust-lang.org`, `index.crates.io`, `static.crates.io` y los assets de GitHub usados para distribuir Wine tampoco son accesibles desde este contenedor. No se instaló Wine ni se ejecutó un programa con Wine.
- Wine **no compila** una aplicación Tauri: solo intentaría ejecutar un binario Windows ya generado. Tauri documenta el cross-build Windows desde Linux con **Rust target MSVC + LLVM/LLD + cargo-xwin + SDK Windows**, y NSIS para el instalador; faltan esas herramientas/descargas aquí. Incluso con Wine disponible, una ventana WebView2 en Wine no equivale al QA nativo en Windows. Véanse la [guía oficial de cross-build Tauri](https://v2.tauri.app/distribute/windows-installer/#build-windows-apps-on-linux-and-macos) y el [QA nativo pendiente](QA_WINDOWS_WEBVIEW2.md).
- Sí se ensambló **solo el frontend web** mediante Vite con el WASM previamente versionado; cinco recursos offline y SHA-256 de `web/public/core.wasm` = `dist/web/core.wasm` = `fe95bb201e1bcb92574e09bc196670062fdc75da3b13502f7e2cb56dc6ba0874`. **No recompila el núcleo Rust ni crea un `.exe`** y no se presenta como tal.
- GitHub está autenticado, pero `permissions.push=false` y su API de Actions devuelve HTTP 403; por tanto **no fue posible despachar el runner Windows ni publicar/descargar el ZIP** desde esta rama. No se intentó publicar en otra rama ni crear una versión falsa.

## Alternativa real: cross-build Linux/macOS → Windows x64 sin Wine

Tauri 2 [documenta](https://v2.tauri.app/distribute/windows-installer/#build-windows-apps-on-linux-and-macos) el target **`x86_64-pc-windows-msvc`** con `cargo-xwin`, LLVM/LLD y SDK de Windows descargado por `cargo-xwin`. **No** equivale a construir un target MinGW/GNU con Wine; Wine tampoco aporta WebView2 fiable para QA. Para obtener **un ZIP del EXE** no hace falta NSIS; para generar el instalador offline sí se requieren NSIS y dependencias adicionales.

En una máquina Linux/macOS **externa con acceso a Rust, npm, crates.io y SDK de Microsoft**, instalar Node 22, Rust estable reciente (≥1.88 para el núcleo; Tauri y sus dependencias pueden exigir más) y las herramientas LLVM `clang`, `llvm-rc` y `lld-link` (en Ubuntu/Debian: `clang lld llvm zip unzip`; en macOS: `brew install llvm` y agregar su `bin` al `PATH`). Luego, desde la raíz de **esta rama**:

```bash
rustup target add wasm32-unknown-unknown x86_64-pc-windows-msvc
cargo install --locked cargo-xwin
./scripts/cross-build-windows.sh
```

El script comprueba los prerrequisitos, instala dependencias npm mediante el lock, pasa pruebas Rust/web, ejecuta `tauri build --no-bundle --runner cargo-xwin --target x86_64-pc-windows-msvc` y solo si existe un **PE GUI release x64 verificable** empaqueta `artifacts/ARQ-GEN-Windows-x64-0.21.0.zip`. No escribe ese ZIP si faltan herramientas o falla la build. Reserva los SDKs en `~/.cache/arqgen-xwin` mediante `XWIN_CACHE_DIR`; no persistas toolchains/SDKs en Git. Si el host usa `CARGO_TARGET_DIR`, quítalo para evitar empaquetar un EXE viejo fuera de `web/src-tauri/target/`. **No se pudo ejecutar aquí:** el preflight falla de forma explícita por `cargo` ausente y tampoco hay Docker/Podman/LLVM ni descargas de Rust/crates disponibles. Una imagen Docker con estas herramientas sería el *mismo* método `cargo-xwin`, no un atajo para este contenedor.

La compilación cruzada no prueba que el programa arranque: después, validar en **Windows real con WebView2** y revisar dependencias, firma y contexto legal del producto; consulta [QA nativo](QA_WINDOWS_WEBVIEW2.md). No presentar una ejecución Wine o una prueba sintética del empaquetador como ese QA.

## Camino operativo para obtener el ZIP auténtico

En un Windows x64 con **MSVC/C++ Build Tools, Rust estable/target WASM, Node 22, npm, WebView2 y acceso a dependencias**, trabajar sobre esta misma rama. Desde la raíz del repositorio en PowerShell:

```powershell
rustup target add wasm32-unknown-unknown
npm ci --prefix web
cargo test --locked --workspace
npm test --prefix web
npm run tauri --prefix web -- build --no-bundle
node scripts/package-windows.mjs
Get-FileHash artifacts/ARQ-GEN-Windows-x64-0.21.0.zip -Algorithm SHA256
```

`npm run tauri ... build --no-bundle` recompila el WASM, el frontend y el **Tauri release** antes de empaquetar. El packager admite **solo** `web/src-tauri/target/release/arqgen-desktop.exe` o su ruta MSVC cross `target/x86_64-pc-windows-msvc/release/`; verifica firma estructural PE32+ x64, subsistema GUI/release y ruta del binario; copia el exe a `ARQ-GEN-Windows-x64-0.21.0/` dentro del ZIP con `SHA256SUMS.txt` y advertencias, vuelve a extraerlo y coteja SHA-256. No demuestra por sí mismo que el exe arranque, que esté firmado ni que el binario provenga de una cadena de suministro segura. El ZIP está en `artifacts/` (ignorado por Git), con el **exe + documentación**, **no** el runtime WebView2 ni el instalador offline.

El workflow `.github/workflows/windows-webview2.yml` ejecutará una build debug seguida de QA nativo WebView2, una build release `--no-bundle`, empaquetará el exe en ZIP y subirá el ZIP como **artefacto de Actions**, antes de intentar construir NSIS. Necesita que la integración GitHub se reconecte en Arena con permisos de push/Actions para **esta** rama; no compartir tokens ni contraseñas. El instalador NSIS es un artefacto distinto; construirlo no valida su instalación desconectada. El shell aún no tiene `web/src-tauri/Cargo.lock` versionado (en el runner se genera como diagnóstico); fijarlo y auditar dependencias transitivas antes de una distribución reproducible.

**Uso previsto:** el ZIP es un prototipo sin firma configurada, requiere WebView2 en Windows y **no** autoriza obra ni acredita normativa cubana, ventilación efectiva o aprobación profesional. Para validar el programa, ejecutar también el [smoke nativo y pruebas de instalación offline](QA_WINDOWS_WEBVIEW2.md) en Windows; Wine no las sustituye.

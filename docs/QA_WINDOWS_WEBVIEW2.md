# QA nativo Windows / WebView2 · protocolo y estado

**Preparado 2026-09-26; actualizado 2026-10-01. Estado: PENDIENTE DE EJECUCIÓN NATIVA.** El workflow ya se ejecuta en `windows-latest` y la compuerta de regresión está en verde; el flujo se detiene en el build Tauri debug, así que **el smoke WebView2 todavía no se ha ejecutado** (véase la evidencia de abajo). Esta sesión usa Linux: no existe aquí un binario Windows ejecutable **de Tauri**, [ZIP del shell Tauri](COMPILACION_WINDOWS_ZIP.md) ni un WebView2. La [alternativa Zig/navegador externo 0.22](EXE_ALTERNATIVO_ZIG.md) es un PE Windows compilado pero **no es el shell ni se ejecutó en Windows**. El transporte W3C simulado y los E2E Chromium/Linux **no** aprueban este criterio; NSIS offline y firma siguen pendientes. Tras obtener temporalmente Rust 1.88/WASM fuera de Git pasaron Rust **85/85**, web **89/89** y Chromium/Linux **5/5**; el contrato WebDriver/fixtures está probado, pero el comando nativo termina con código 1 en Linux, como debe ser. Ningún resultado de esta página implica QA Windows aprobado.

## Evidencia observada de ejecuciones reales (2026-10-01)

Las ejecuciones existen y son consultables por API; el registro crudo de cada paso **no** es descargable desde el entorno del agente, así que el workflow publica la causa de cada fallo como **anotación** (`::error::`), legible por la API de comprobaciones. Hechos verificados:

- `67f0967` (2026-09-29): la compuerta de regresión pasó y el flujo falló en **Build the actual Windows Tauri app (debug, no installer)**; entonces no se capturaba la causa.
- `0bce1ea` y `b1f82c5` (2026-09-30): la compuerta falló en **`npm test --prefix web`** con **1 de 89** pruebas en rojo.
- `64f8fde`, `1eb3c24`, `64ff7ef` (2026-10-01): la instrumentación publicó como anotación el nombre de la prueba (`drawing-package.test.mjs`) y su bloque de error. Causa: el checkout del runner convierte a **CRLF** los archivos de texto con varias líneas, y la comparación byte a byte de `examples/laminas-conceptuales/nivel-0-2d.json` fallaba solo en Windows (los SVG de ejemplo son de una línea y el ZIP es binario).
- **Corrección aplicada:** `.gitattributes` fija `* text=auto eol=lf` (con binarios explícitos y `ARQ GEN TAURI.txt` marcado `-text`), y la prueba del ejemplo normaliza el fin de línea del texto leído, con prueba de regresión propia. Se reprodujo el fallo exacto en Linux con una copia convertida a CRLF y se comprobó la suite **90/90** tanto con LF como con CRLF.
- `1153093` (2026-10-01): **primera compuerta completa en verde en Windows** (formato Rust, `cargo test --locked --workspace`, `npm test --prefix web`). El flujo avanza y vuelve a fallar en el **build Tauri debug**, con la misma firma que en `67f0967`.
- `388df75` y `913c424`: los pasos de build debug, instalación de drivers, smoke, release, ZIP y NSIS anotan su salida (encabezado, líneas de error y cola) y la captura usa la redirección de `cmd`, porque el CLI de Tauri no entregaba su `stderr` a través del oleoducto de PowerShell.
- `f679b9b` (2026-10-01): **el shell Tauri debug compila y produce `arqgen-desktop.exe` en Windows** (la compuerta de regresión y el build pasaron). El flujo se detiene ahora en la **instalación de los drivers** (`tauri-driver 2.0.6` y `msedgedriver-tool`), aún sin causa publicada; ese paso y el smoke se instrumentaron para anotar también los comandos sueltos y las excepciones. Después del smoke quedan release, ZIP y NSIS, todos sin ejecutar todavía.
- `79714c6` (2026-10-01): con el árbol transitivo fijado, Tauri, `muda`, `tao`, `wry` y `tauri-runtime` **compilaron** en Windows; el siguiente fallo fue el icono del shell: `generate_context!` no puede decodificar un PNG incrustado de **16 bits** («Unsupported PNG bit depth: Sixteen»). `web/src-tauri/icons/icon.ico` y `icon.png` se regeneraron a **8 bits** y una prueba verifica los mapas de bits y PNG del ICO.
- `3b77f6b` (2026-10-01): con la captura corregida se leyó la causa real del bloqueo: el **frontend offline se construye bien** en Windows (`npm run build` genera los cinco recursos) y el fallo está en la **compilación Rust del shell**, dentro del árbol de `tauri 2.11.5`: `UnexpectedMenuKind` (macro de `muda` contra `tauri::Error`) y `Option<Monitor>` frente a `Result<_, Error>`. Es resolución de dependencias, no código propio. Corrección: `web/src-tauri/Cargo.toml` fija las versiones del árbol probado por Tauri en `tauri-v2.11.5`, con prueba de regresión; el próximo ciclo dirá si el shell compila.

**No acreditado:** el smoke WebView2 nunca se ha ejecutado (todo lo posterior al build queda `skipped`), no hay `.exe` Tauri ni instalador, y ninguna anotación de este repositorio equivale a QA nativo aprobado.

## Qué se automatizó, sin modificar el shell distribuible

- `web/tests/webview2.native.mjs` exige `process.platform === 'win32'`, un `.exe` Tauri existente, `tauri-driver.exe` y `msedgedriver.exe` **compatible con el WebView2 local**. No puede caer a Chromium/Playwright ni usar el servidor Vite. Conecta **solo a `127.0.0.1:4444`** mediante `web/tests/native/webdriver.mjs` (WebDriver W3C); crea sesión `browserName: wry` con `tauri:options.application` apuntando al `.exe` real. No se agrega ningún plugin, permiso o comando IPC a producción.
- Crea un perfil de WebView2 temporal con `WEBVIEW2_USER_DATA_FOLDER` y exige cartera vacía **antes** de escribir nada; utilícese únicamente en una cuenta/runner desechable. Genera con **el WASM de la misma build**, no con respuestas mock, un lote íntegro/alterado y **un archivo vertical íntegro/alterado**. Comprueba que los SHA-256 del WASM público y del bundle coinciden.
- Aserta origen/protocolo Tauri, `window.isTauri`, UA de Edge, respuesta Rust/WASM inicial, aviso `NO EVALUADO`. Con WebDriver declara todas las cotas Z (sin valores por defecto), verifica ocho huecos, rechaza JSON Z adulterado sin mutar v8 y abre uno íntegro. También ejecuta el Worker multisemilla (96 variantes, tres imágenes), rechaza el lote alterado **sin mutación** y lo acepta solo tras replay íntegro; crea proyecto IndexedDB, recarga el shell y lo reabre con Rust, **sin Z implícita en la cartera**, e importa Z por separado. Falla ante errores JS/CSP observados, timeout, archivo faltante, sesión fallida, WebView2 ausente o desajuste de motor. Captura `web/webview2-qa/failure.png` si puede (ignorado por Git). **El smoke ampliado todavía no se ha ejecutado en Windows.**
- `web/tests/native-webdriver.test.mjs` prueba **el transporte con un servidor simulado**, genera/reproduce los archivos de lote y Z con WASM real y verifica que Linux no devuelve éxito para el comando nativo. Estos tests no cuentan como WebView2.
- `.github/workflows/windows-webview2.yml` define un runner `windows-latest`: test Rust/web, build **Tauri debug --no-bundle**, drivers nativos, smoke WebView2, build **release --no-bundle** con [ZIP del `.exe` verificado](COMPILACION_WINDOWS_ZIP.md) como artefacto descargable y build **NSIS offlineInstaller** por separado. Driver Tauri fijado a `2.0.6`; fuente de `msedgedriver-tool` fijada a `8c4b34f51b45f5cf08013366d703de464ab871d1`, que descarga desde Microsoft el ejecutable correspondiente a la versión de **WebView2** del runner. La workflow deja el `Cargo.lock` generado del shell y captura de fallo como diagnósticos; publica **solo el ZIP de prototipo sin firma**, no el instalador NSIS.

Referencias de integración: [Tauri · WebDriver manual](https://v2.tauri.app/develop/tests/webdriver/manual-setup/) y [Tauri · CI](https://v2.tauri.app/develop/tests/webdriver/ci/). La fuente del descargador de EdgeDriver está fijada a una revisión concreta, pero sus binarios y el runtime requieren igualmente revisión de procedencia antes de distribuir.

## Ejecutar en Windows x64 limpio, con acceso a crates/npm/Microsoft

Prerequisitos: Windows 10/11 o Windows Server con interfaz gráfica y WebView2, MSVC/C++ Build Tools compatibles con Tauri 2, Rust estable con `wasm32-unknown-unknown`, Node 22 y npm; Git y ancho de banda para instalar dependencias. Usar una **cuenta/VM descartable** y abrir PowerShell en la raíz de este checkout. El artefacto `web/src-tauri/Cargo.lock` aún no está versionado: antes de aprobar una entrega deberá generarse, auditarse y fijarse, no confundir un build con dependencia flotante con una distribución reproducible.

```powershell
rustup target add wasm32-unknown-unknown
npm ci --prefix web
cargo fmt --all -- --check
cargo test --locked --workspace
npm test --prefix web
npm run tauri --prefix web -- build --debug --no-bundle
cargo install tauri-driver --version 2.0.6 --locked
tauri-driver --help   # `tauri-driver` no acepta --version; la ayuda basta como comprobación
cargo install --git https://github.com/chippers/msedgedriver-tool --rev 8c4b34f51b45f5cf08013366d703de464ab871d1 --locked
$folder = Join-Path $env:TEMP 'arqgen-native-driver'
New-Item -ItemType Directory -Force $folder | Out-Null
Push-Location $folder
msedgedriver-tool
Pop-Location
$env:ARQGEN_TAURI_BINARY = (Resolve-Path 'web/src-tauri/target/debug/arqgen-desktop.exe').Path
$env:ARQGEN_TAURI_DRIVER = (Get-Command tauri-driver).Source
$env:ARQGEN_EDGEDRIVER = (Resolve-Path "$folder/msedgedriver.exe").Path
npm run test:webview2 --prefix web
```

**Una sola ejecución `npm run test:webview2 --prefix web` con salida `QA NATIVO WEBVIEW2: PASÓ` y código 0** acredita únicamente el smoke del `.exe` en la versión de WebView2/Windows identificada en el registro. Conservar SHA-256 del `.exe` y los cuatro valores de versión (Windows, WebView2, EdgeDriver y `tauri-driver`) junto con el resultado, un runner/build reproducible y la captura si falla. Un error, timeout o ejecución en Linux/macOS = **no aprobado**; no reemplazarlo por Chromium. Verificar también manualmente cancellation del Worker, selección/descargas del diálogo nativo, cuota y conflictos IndexedDB, formularios de geometría, cierre/reinicio completo de la app y ausencia de errores CSP en DevTools; el smoke no agota esos casos.

En GitHub: cada `push` a esta rama que toque el workflow, `core/`, `examples/`, `knowledge/`, `scripts/` o `web/` dispara `Windows Tauri / WebView2 native QA`; también puede despacharse desde Actions. La rama se ha subido y el workflow **sí se ejecuta** en `windows-latest`; lo observado está en la sección de evidencia. Publicar el código no es aprobar QA. **El siguiente bloqueo es el build Tauri debug**: hasta que compile y sus pasos posteriores se ejecuten, el QA nativo sigue pendiente. No compartir credenciales por chat.

## Instalador offline ≠ smoke de la aplicación

El workflow intenta **producir** NSIS con `offlineInstaller`, pero esto **no prueba la instalación**. Antes de distribuirlo, verificar en una VM Windows compatible **sin WebView2 preinstalado y con la red desconectada**, por separado: firma/autor del instalador, hash e inventario del redistribuible WebView2 incluido, instalación completa sin descargar nada, arranque del programa instalado y de Worker/WASM, copia/recuperación y desinstalación; registrar versión exacta y evidencias. Después, repetir en la matriz de Windows objetivo, permisos de usuario restringido y políticas corporativas. En GitHub Actions el runner ya trae WebView2; la construcción de NSIS no acredita el caso de máquina sin runtime. El shell no está firmado ni listo para distribución profesional.

## Límites del criterio

Aun cuando este smoke pase, **no** se habrá demostrado cumplimiento cubano, acceso legal/real, ventilación efectiva, óptimo global ni aptitud para obra. El proyecto sigue siendo un prototipo conceptual: datos de equipos verificables, normas cubanas oficiales aplicables y revisión profesional permanecen pendientes. Ver [estado del producto](ESTADO_PRODUCTO.md) y [shell experimental](DESKTOP_EXPERIMENTAL.md).

# QA nativo Windows / WebView2 · protocolo y estado

**Preparado 2026-09-26; actualizado 2026-09-30. Estado: PENDIENTE DE EJECUCIÓN NATIVA.** Esta sesión usa Linux: no existe aquí un binario Windows ejecutable **de Tauri**, [ZIP del shell Tauri](COMPILACION_WINDOWS_ZIP.md) ni un WebView2. La [alternativa Zig/navegador externo 0.22](EXE_ALTERNATIVO_ZIG.md) es un PE Windows compilado pero **no es el shell ni se ejecutó en Windows**. El transporte W3C simulado y los E2E Chromium/Linux **no** aprueban este criterio; NSIS offline y firma siguen pendientes. Tras obtener temporalmente Rust 1.88/WASM fuera de Git pasaron Rust **85/85**, web **89/89** y Chromium/Linux **5/5**; el contrato WebDriver/fixtures está probado, pero el comando nativo termina con código 1 en Linux, como debe ser. Ningún resultado de esta página implica QA Windows aprobado.

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

En GitHub: subir **esta rama** y comprobar si corre `Windows Tauri / WebView2 native QA` por el trigger `push`; también puede despacharse manualmente desde Actions si se tienen permisos. Publicar el código no significa que se haya ejecutado o aprobado el workflow. **Hasta observar logs, versiones y resultado verificable del runner Windows, el QA nativo permanece pendiente.** No compartir credenciales por chat.

## Instalador offline ≠ smoke de la aplicación

El workflow intenta **producir** NSIS con `offlineInstaller`, pero esto **no prueba la instalación**. Antes de distribuirlo, verificar en una VM Windows compatible **sin WebView2 preinstalado y con la red desconectada**, por separado: firma/autor del instalador, hash e inventario del redistribuible WebView2 incluido, instalación completa sin descargar nada, arranque del programa instalado y de Worker/WASM, copia/recuperación y desinstalación; registrar versión exacta y evidencias. Después, repetir en la matriz de Windows objetivo, permisos de usuario restringido y políticas corporativas. En GitHub Actions el runner ya trae WebView2; la construcción de NSIS no acredita el caso de máquina sin runtime. El shell no está firmado ni listo para distribución profesional.

## Límites del criterio

Aun cuando este smoke pase, **no** se habrá demostrado cumplimiento cubano, acceso legal/real, ventilación efectiva, óptimo global ni aptitud para obra. El proyecto sigue siendo un prototipo conceptual: datos de equipos verificables, normas cubanas oficiales aplicables y revisión profesional permanecen pendientes. Ver [estado del producto](ESTADO_PRODUCTO.md) y [shell experimental](DESKTOP_EXPERIMENTAL.md).

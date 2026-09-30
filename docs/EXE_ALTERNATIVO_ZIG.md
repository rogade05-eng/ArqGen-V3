# EXE Windows alternativo · Zig + navegador externo (NO Tauri)

**Actualización 2026-09-30 — versión web 0.22:** [ZIP Windows x64 con EXE alternativo](../downloads/ARQ-GEN-LOCAL-NO-TAURI-Windows-x64-0.22.0.zip), SHA-256 `1accad9604846e14b3e9de77990f5ffa91ada10e046a44c6bf900d4543e43069` (EXE SHA-256 `d4708746abbb326dd2b53af7e97d7e8e1850cb37b180a207acce2ed5051f2277`). Se compiló de nuevo con Zig 0.13.0 en Linux tras compilar/validar Rust 1.88 → WASM 0.17 por separado; incluye **las cuatro hojas A3 en planta** y **el nuevo panel de cotas Z L0 exportables como JSON independiente**. El script exige el SHA-256 `4d2cde571b6706b6beafa7f25bf9f1fa18dd90951cf3e4ceacea4dd6c0b7ed01` del WASM y ensaya v8 + vertical antes de empaquetar. QA hecho: estructura PE GUI x64, ZIP extraído/hashes, servidor C equivalente en Linux (seis recursos, CSP, host y métodos) y Chromium/Linux **offline** con Worker, cartera, Z e importación. **No se ejecutó el EXE en Windows; no es Tauri/WebView2 ni un instalador.** [Límites y descargas](../downloads/LEEME.md).

## Historial: corte anterior 0.21.0 (sin láminas v2 ni Z)

**2026-09-29 — Artefacto experimental anterior:** [`downloads/ARQ-GEN-LOCAL-NO-TAURI-Windows-x64-0.21.0.zip`](../downloads/ARQ-GEN-LOCAL-NO-TAURI-Windows-x64-0.21.0.zip). Contiene un **PE32+ x64 de subsistema GUI** `ARQ-GEN-Navegador.exe`, `SHA256SUMS.txt` y `LEEME-ANTES-DE-USAR.txt`. SHA-256 EXE de la recompilación actual: `7448aacff1b36bcf7591c639d7a51abcfb9b0d28df722d95cb9373c4362b1ac2`; SHA-256 ZIP de la recompilación actual: `12af8add0b0998923c339be3c1f41d42a65d78d1c24c89a94f04bcd2660ba6c2`. El ZIP se reconstruyó para compartirlo; sus hashes difieren de los de la entrega anterior. `artifacts/` está ignorado por Git; la copia histórica rastreada está en `downloads/` de esta rama, no en un release oficial.

**NO es el shell Tauri/WebView2, no es un instalador y no se ejecutó en Windows.** Nunca se contará como QA nativo Windows ni como cierre del producto maestro. La v0.21 se creó como alternativa solicitada cuando el toolchain Rust/MSVC y GitHub Actions no estaban accesibles aquí; **en aquel corte** `web/src-tauri/` no se modificó. La configuración experimental Tauri se alineó posteriormente a web 0.22, todavía sin ejecutarse en Windows.

## Funcionamiento y límites

El código de `native/zig-browser-launcher.c` abre una ventana Win32 pequeña con **Abrir interfaz** y **Cerrar servidor**. Incorpora como bytes los seis archivos de `dist/web/` (HTML, JS, CSS, worker, service worker y WASM preexistente) y sirve **solo** esas rutas, sin datos ni endpoints mutables, por HTTP en `127.0.0.1:48765`. Abre el **navegador predeterminado** de Windows, *no* WebView2 embebido. Si el puerto está ocupado, no abre un sitio de otro proceso: muestra error y termina. Requiere un navegador actual con WebAssembly, Worker, IndexedDB y descarga de archivos; Internet no se necesita para servir el bundle. Mantén abierta la ventana de control y ciérrala para apagar el servidor.

El origen `127.0.0.1:48765` es fijo para que IndexedDB y el service worker tengan el mismo origen entre lanzamientos; sus datos viven en **ese perfil de navegador**, no dentro del EXE. Limpieza del perfil, cambio de navegador o conflicto del puerto afectan las copias locales; descarga JSON como respaldo y **no uses datos sensibles**. El servidor restringe Host, métodos y rutas; incluye CSP, `nosniff` y `CORP: same-origin`. No dispone de la seguridad/evaluación de una app de escritorio profesional ni se ha realizado una auditoría de seguridad del binario.

Zig **0.13.0 desde el paquete npm tercero `@ryoppippi/zig-linux-x64`**, integridad declarada `sha512-I4csxVyW7ck+iwkt7xHeI+0NmHFV2yYEhu/mAKyeJU5TUvf36OH3Z8oUsosQokPMQw0kQbQDcUuajXi90Wsulg==`, compiló el launcher desde Linux. El frontend se reconstruyó con el lock npm; **Rust no se recompiló** por carecer de Cargo. Se empaquetó `web/public/core.wasm` previamente versionado y contrastado con `dist/web/core.wasm`, SHA-256 `fe95bb201e1bcb92574e09bc196670062fdc75da3b13502f7e2cb56dc6ba0874`. Si cambia Rust, no usar este método hasta recompilar/verificar el WASM oficial y actualizar el hash fijado en `scripts/build-zig-browser.mjs`.

## Evidencia realizada y pendiente

- **Hecho en Linux:** Vite compiló el frontend, WASM produjo un ejemplo `status: ok`, el servidor equivalente GCC entregó los seis recursos idénticos byte a byte en localhost; HEAD y rechazo de POST, rutas no listadas y Host ajeno funcionaron. Zig produjo un PE x64 GUI de 773 632 bytes; `unzip -t` correcto, SHA del EXE extraído coincide con el empaquetado. `objdump` muestra dependencias Win32 esperadas, incluida UCRT de Windows moderno.
- **Hecho en Chromium/Linux:** prueba automatizada contra el servidor C equivalente: generación WASM, worker bajo la CSP sin violaciones, SVG, Service Worker offline, cartera IndexedDB, persistencia tras recargar y reapertura del proyecto. Para repetir esta prueba opcional, definir `ARQGEN_CHROMIUM_PATH` apuntando a un Chromium Linux compatible (con sus bibliotecas); sin esa variable el script la omite. Esto **no prueba el PE en Windows**.
- **Pendiente:** iniciar **ese** EXE en Windows 10/11, observar que abre el navegador, comprobar `core.wasm`, el worker bajo la CSP, la cartera IndexedDB tras cerrar/reabrir, descargas JSON y cierre limpio; probar antivirus/SmartScreen, firma, políticas corporativas y actualizaciones. Este Linux no dispone de Wine y una prueba con Wine tampoco sustituiría Windows real. **No hay evidencia de ejecución Windows** ni de aptitud para distribución profesional.
- **Producto principal:** sigue faltando compilar/probar `web/src-tauri` y su NSIS; el [QA Windows/WebView2](QA_WINDOWS_WEBVIEW2.md) permanece pendiente. Un ZIP del EXE alternativo nunca se confundirá con el [ZIP Tauri proyectado](COMPILACION_WINDOWS_ZIP.md).

## Recompilar la alternativa actual en Linux

**Nota histórica:** las cifras/hash v0.21 anteriores describen exclusivamente el corte anterior; el script actual tiene fijado el WASM v0.17 y produce **v0.22.0**, no reconstruye v0.21. Requiere el WASM nuevo compilado y probado previamente con Rust 1.88 + target WASM (o el binario versionado idéntico). Requiere Node 22/npm, GCC, `zip`/`unzip` y acceso a npm. Instala Zig **fuera** del repositorio y ejecuta:

```bash
npm install --prefix /tmp/arqgen-zig --no-save --ignore-scripts @ryoppippi/zig-linux-x64@0.13.0
ARQGEN_ZIG=/tmp/arqgen-zig/node_modules/@ryoppippi/zig-linux-x64/zig node scripts/build-zig-browser.mjs
```

El script instala dependencias web desde `web/package-lock.json`, reconstruye Vite con el WASM versionado, genera un header C **temporal** de rutas/bytes, compila y prueba un servidor equivalente Linux y compila el PE Windows con Zig; **solo tras estas validaciones** genera el ZIP. Los datos normativos y prestaciones del proyecto siguen siendo ilustrativos: **NO APTO PARA OBRA**; no se acredita normativa cubana, ventilación efectiva, acceso real u óptimo global.

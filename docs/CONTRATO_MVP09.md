# Contrato correctivo — MVP-0.9: copia local optativa, nunca un plano confiado

**Estado:** implementado en la web (2026-09-25). Amplía [MVP-0.8](CONTRATO_MVP08.md). Web `0.10.0`; núcleo Rust `0.7.0`, `engine_version = "mvp0.6-rust-0.7.0"` y ruleset demo `knowledge/generic-house.json@0.7.0` **sin cambios**. No se convierte el prototipo en herramienta profesional por ofrecer almacenamiento.

## Copia local explícita, de una ranura

El cuaderno activo sigue en memoria. «Guardar copia local» requiere una corrida actual regenerada (`ok` o `infeasible`) y sin cambios pendientes en el formulario. Guarda mediante **una transacción IndexedDB** una sola ranura del origen web:

```text
{ format: "arqgen-local-workspace-v1", engine_version,
  focus: { input, generation, selection: null },
  scenarios: [{ input, generation }, ...] } // 0–3 corridas comparables
```

Se guardan la respuesta original y la entrada exacta de Rust, incluido el ruleset demo y los tres supuestos editables. Antes de escribir, se comprueba que las corridas del cuaderno no mezclen parcela, programa, semilla, reglas fijas ni versión de motor. Límite de **8 MiB**. No hay autosave, sincronización, varias versiones, copias programadas ni historial/undo-redo: **un guardado posterior reemplaza la única copia**. «Borrar copia» pide confirmación y elimina esa ranura sin borrar la pantalla ni descargas JSON; limpiar los datos del navegador también puede borrarla. Es una comodidad local, **no un backup**: hay que exportar archivos JSON si se necesita retención fuera del navegador.

## Reapertura verificada, todo o nada

«Reabrir copia» lee IndexedDB y **vuelve a ejecutar cada entrada** (`focus` y las 0–3 corridas) con el WASM Rust actual; contrasta estructuralmente las respuestas **completas** con las guardadas y comprueba esquema, versión, reglas fijas y comparabilidad usando la misma política de [importación de archivos](CONTRATO_MVP08.md). Un dato alterado, viejo o incompatible no cambia formulario, planos ni cuaderno: las respuestas del almacenamiento **jamás** se renderizan como planos. Si el formulario se edita mientras se lee, se cancela la operación; importar un archivo y reabrir una copia no pueden aplicar dos estados concurrentes. Se restaura la corrida actual (también si era `infeasible`) y las columnas, pero **no** una aprobación importada. La preferencia preliminar almacenada aparte en `localStorage`, si existe para el mismo hash, tampoco es validación profesional.

El service worker **solo** precarga los archivos estáticos del build (`HTML/JS/CSS/WASM`), no este documento; IndexedDB lo conserva separadamente y se puede reabrir sin conexión tras la primera visita completa al sitio de producción servido por HTTPS o localhost. En desarrollo, el servidor local debe seguir encendido. `file://` no soporta este flujo.

## Evidencia y límites

`web/tests/workspace.test.mjs` cubre replay íntegro de tres corridas (0/48, 12/48, 48/48), foco inviable, formatos y versiones incompatibles, ruleset y SVG adulterados y rechazo sin resultados parciales. `web/tests/offline.test.mjs` comprueba la lista de shell y la versión por bytes. Pruebas reales con Chromium: copia de tres corridas guardada, página recargada **sin red**, reapertura con Rust, SVG manipulado en IndexedDB rechazado sin sustituir el cuaderno y eliminación confirmada. En total, tras añadir una prueba **estática** de configuración Tauri y dos de inventario de fuentes: **37 pruebas Rust** y **19 web**, más build Vite/WASM. Esa prueba no equivale a una ejecución de WebView2. Reproducir: `cargo fmt --all -- --check`, `cargo test --offline --workspace`, `npm test --prefix web`, `npm run build --prefix web` y `npm run preview --prefix web`.

**Pendiente para la visión maestra:** compilar, firmar y verificar nativamente el [shell Tauri 2/Windows experimental](DESKTOP_EXPERIMENTAL.md) y su instalador, persistencia de proyecto más amplia, edición fina/undo-redo/auditoría, refinamiento generativo convergente y ocho criterios independientes, planos/documentos profesionales, jurisdicción y datos verificables de equipos. No existe cálculo ni medición de caudal entregado, validación de ventilación real ni cumplimiento normativo. Para detalles, consultar [estado del producto](ESTADO_PRODUCTO.md).

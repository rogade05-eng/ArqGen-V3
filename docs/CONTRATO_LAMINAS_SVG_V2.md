# Paquete SVG v2 — perímetro y vanos verificables en planta

**2026-09-30 · segundo corte incremental.** Sigue siendo un generador de **vivienda unifamiliar esquemática de una planta**; [v1](CONTRATO_LAMINAS_SVG_V1.md) documenta el paquete previo de tres hojas. Hospitales y hoteles están confirmados como **tipologías funcionales futuras**, no son nuevas opciones del formulario. El objetivo visual se documenta [aquí](OBJETIVO_VISUAL_VARIANTES_PLANOS.md). [Ejemplo v2 descargable](../examples/laminas-conceptuales/README.md).

## Qué cambia en el modelo, no solo en el color

`web/src/plan-envelope.js` construye una **única envolvente ortogonal bruta 2D** a partir de las *celdas de muro, corredor útil y locales útiles* ya validadas por el núcleo Rust/WASM v8. Divide la rejilla en cada borde de celda, comprueba que las celdas no se solapen, recorre una sola frontera cerrada, elimina vértices colineales y contrasta por área de polígono la **huella bruta informada por Rust**. No usa la caja envolvente para simular una fachada. Rechaza huecos/patios, cuerpos separados o contactos solo por vértice: necesitan un esquema posterior con varios contornos. Acepta pequeñas diferencias de coma flotante (≤0,0000001 m), **no** disimula un solape ni una superficie incoherente.

La entrada y las ventanas dibujadas se asocian a **segmentos precisos del perímetro**. Para cada una se comprueba ancho, ubicación sobre el borde, pertenencia de la ventana a su propio local, dirección cardinal respecto al frente **declarado** y ausencia de solape con otros vanos. Una entrada que no toca el corredor frontal o una ventana que se salga de su segmento impiden producir el paquete. Es solo topología **en planta**: el vano no demuestra exterior libre, luz, fachada ejecutable o ventilación. No hay cota de antepecho/cabezal; que Rust tenga una altura *nominal* de ventana para su pantalla demo no permite fijar su posición vertical.

El ZIP pasa a formato **`arqgen-conceptual-svg-sheets-v2`** e incluye **ocho archivos**:

1. `A-01-emplazamiento.svg`: silueta **poligonal** de la huella bruta comprobada frente al mismo croquis de parcela.
2. `A-02-planta-amueblada.svg`: plan Rust con equipos esquemáticos, sin añadir espacios.
3. `A-03-planta-cotas.svg`: plan sin muebles, cotas útiles locales y extensión de la huella (las dos últimas siguen siendo la **caja exterior**, no una cadena de fachada).
4. `A-04-envolvente-2d.svg`: bordes brutos `P01…`, longitudes de los tramos legibles, entrada y ventanas dibujadas, índice de anchos **en planta**. Los tramos que no admiten rótulo legible en papel permanecen en el JSON. **No es un alzado**.
5. `nivel-0-2d.json`: contrato `arqgen-plan-envelope-2d-v1` con vértices, segmentos orientados, longitudes/área/perímetro y vanos asociados por ID/posición. `level.index = 0` es una **identidad lógica**, `elevation_m = null`: no se conoce ninguna cota Z; otros niveles, cubierta y fachadas se declaran `not_modelled`. Es un **derivado del resultado v8**, no se reabre solo ni sustituye a Rust.
6. `manifest.json`: identidad de la candidata, lista de cuatro hojas, formato del modelo 2D y exclusiones explícitas.
7. `origen-v8.json`: entrada/salida originales, **reabribles tras replay íntegro por Rust**, como antes.
8. `LEEME-ANTES-DE-USAR.txt`: límites de uso y escala de impresión.

Todas las hojas son SVG autónomos ISO A3 con escala **nominal**, rótulo de candidato/`input_hash`, orientación, advertencia **NO APTO PARA OBRA**. El ZIP no se importa directamente: para reconstruir la candidata se importa `origen-v8.json`, sujeto a replay. La exportación de datos alterados o inviables se bloquea. No hay servicios o fuentes remotas; el shell se puede recargar offline tras precache. El SVG histórico `candidate.svg`, el esquema v8, `engine_version` y **`web/public/core.wasm` no se modifican**; los archivos v8 antiguos mantienen su replay.

**Ejemplo reproducible:** parcela declarada 18 × 22 m, candidata `cand-ab3376d8fef08f3b-22`, huella Rust ≈94,858 m². La extracción da un contorno en L de **6 vértices y 6 lados**, área del polígono ≈94,858 m², perímetro ≈43,070 m y **8 vanos dibujados** (7 ventanas y entrada). Son datos del motor **demo**, no medidas del inmueble ni conformidad de Cuba. La imagen A-04 permite inspeccionarlos sin convertirlos en elevación o render. Los futuros hospitales y hoteles requerirán su **propio programa, generación geométrica y validación**, no reutilizar la lista de dormitorios ni dibujar “alas” en estas hojas.

## Próximo contrato geométrico que aún falta

**Etapa posterior al ZIP v2:** se implementó un [modelo Rust/CLI/WASM y formulario web de Z declarada solo para la planta L0](CONTRATO_VERTICAL_DECLARADO_V1.md), con **JSON separado** y replay; **no se incorpora al ZIP A3**. Para un **modelo completo y versionado por tipología y nivel** aún faltan alturas de pisos/cubierta y suelo medidos o declarados con sus fuentes, relación entre niveles, escaleras/núcleos y programa funcional; sus invariantes deberán pasar antes de renderizar un alzado/corte. En el ZIP v2 **no** hay altura legal de edificación, topografía ni un segundo nivel; no se deben calcular cortes/fachadas/3D a partir de `nivel-0-2d.json`. Para hospital/hotel además faltan relaciones de servicios, circulaciones, seguridad, accesibilidad, fuentes cubanas pertinentes vigentes y validación profesional. Nada de este corte sustituye QA nativo Windows/Tauri ni habilita obra.

## Pruebas

- `node --test web/tests/plan-envelope.test.mjs web/tests/drawing-package.test.mjs`: **8/8**, contorno L/no caja, área/perímetro, 48 candidatas Rust reales con cuatro orientaciones, ventana ↔ local ↔ borde, rechazo de huecos/cuerpos separados/solapes/áreas o vanos falsos, ZIP reproducible y replay v8 íntegro.
- `node scripts/generate-sample-sheets.mjs` regenera ZIP, cuatro SVG y JSON del **WASM versionado**; la suite exige coincidencia byte a byte. SHA-256 ZIP de ejemplo: `95f28e4d2142db81306ba4696e7f7580d715833d77afb35c67c7485168d5d4bd`. Se verificaron XML/ZIP y se rasterizaron A-01/A-04 para detectar solapamientos de rótulos.
- `npm test --prefix web`: **83/85**. Los únicos dos fallos son pruebas CLI↔WASM preexistentes bloqueadas por **`spawnSync cargo ENOENT`** en este entorno, no fallos del perímetro. `vite build && node ../scripts/write-offline.mjs` pasó; el WASM publicado y copiado al shell conservó SHA-256 `fe95bb201e1bcb92574e09bc196670062fdc75da3b13502f7e2cb56dc6ba0874`.
- E2E Chromium headless/Linux en el bundle de producción: **1/1**, cuatro miniaturas y ZIP con cuarta hoja/JSON 2D; replay del origen, invalidación al editar y descarga/miniaturas tras recarga **sin red**. Cargo y QA nativo Windows/Tauri son comprobaciones separadas, no presumidas por probar la web.

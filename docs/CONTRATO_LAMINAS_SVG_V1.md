# Primer paquete de planos SVG — vivienda conceptual, sin alterar el núcleo Rust

> **Histórico (v1):** el [paquete vigente v2](CONTRATO_LAMINAS_SVG_V2.md) añade una cuarta lámina y un modelo de perímetro/vanos 2D. El ejemplo enlazado a continuación se regenera ahora en formato v2; este documento conserva las pruebas y límites del corte original de tres hojas.

**2026-09-29 · implementado como corte de presentación web** tras la confirmación del usuario: **hospitales y hoteles son tipologías funcionales futuras**, no meras referencias visuales. Este corte **no** las genera, no amplía el modelo 2D ni cambia el esquema v8, el `engine_version` o `web/public/core.wasm`. Ver las [11 referencias y hoja de ruta](OBJETIVO_VISUAL_VARIANTES_PLANOS.md) y el [ejemplo descargable](../examples/laminas-conceptuales/README.md).

## Salida implementada

Desde una corrida vigente `status:ok`, la interfaz permite expandir una **vista previa de las tres hojas** y el nuevo botón **«↓ Láminas SVG · ZIP»** exporta **solo la alternativa seleccionada**, no tres alternativas ficticias. Las miniaturas son imágenes SVG aisladas, no HTML importado; al cambiar el encargo se ocultan hasta volver a generar:

- **A-01 — emplazamiento declarado:** contorno de 4/6/8 vértices entregado por Rust, zonas voluntarias, trazado frontal elegido, silueta formada por los muros/locales/circulación de la misma alternativa y orientación dibujada. Terreno/derechos/retiros reales NO verificados.
- **A-02 — planta amueblada:** muros, locales, giros, vanos y equipamiento **ilustrativo** tomados de las coordenadas de Rust; color y rotulación son solo presentación.
- **A-03 — planta con cotas esquemáticas:** exactamente la misma geometría **sin mobiliario**, con anchura y profundidad de rectángulos útiles, segmentos útiles por local y extensión de la huella bruta (bounding box del candidato; no es el perímetro de fachada). No se han modelado cadenas de ejes, detalles de muro o cotas de altura.

Cada hoja es SVG vectorial autocontenido con tamaño físico **ISO A3 vertical 297 × 420 mm**, escala nominal escogida para que el croquis quepa (1:50 a 1:5000), escala gráfica, norte según orientación declarada, rótulo de hoja, `input_hash` y `candidate_id`, superficies tal como las calculó Rust y advertencia **NO APTO PARA OBRA**. Se debe imprimir al 100 % y comprobar la escala: los visores pueden ajustar la página. La escala física es de **los datos esquemáticos declarados**, no prueba que la parcela o los locales existan con esas medidas.

El ZIP incluye `manifest.json` con procedencia y lista explícita de disciplinas/vistas **no modeladas**, `origen-v8.json` con el mismo formato de exportación individual (`selection:null`) que la web puede importar **tras repetir la generación Rust y comparar toda la salida**, y `LEEME-ANTES-DE-USAR.txt`. No hay HTTP adicional ni assets remotos, PDF o imágenes ajenas. `fflate@0.8.2` se empaqueta en el JS offline; ZIP/SVG son reproducibles sin fecha de reloj. El SVG v8 histórico de cada candidato **no se modifica**, protegiendo la reapertura de archivos previos. La hoja se dibuja únicamente desde la salida actual de WASM o una importación revalidada; formulario modificado o `infeasible` deshabilitan la exportación.

## Límites explícitos y evolución

Esta etapa **mejora la presentación, no la diversidad arquitectónica**: siguen los 48 intentos de un pasillo central y estancias rectangulares en **una sola planta**, y las reglas demo no son normativa cubana. Las cotas locales proceden de `room.usable_rect`; las exteriores proceden de la caja envolvente de huella; no implican geometría catastral, cadena continua de fachadas ni aprobación profesional. No se generan cortes, elevaciones, planta de cubierta, render 3D, elementos estructurales, perfiles de terreno, plantas superiores ni hospital/hotel: faltan niveles, alturas, cubierta, modelo de fachadas, topologías/programas/reglas específicos y verificaciones correspondientes. **No** habilita obra, acredita acceso real, iluminación/ventilación efectiva ni sustituye QA Windows/Tauri.

**Siguiente salto del producto maestro:** modelo geométrico por niveles y tipología versionado en Rust; nuevas familias de huella/zonificación/circulación (no solo espejo/jitter) con rechazo de imposibles, y después vistas/cortes/fachadas derivados del **mismo edificio con alturas y huecos**. Hotel y hospital requerirán catálogos funcionales y validaciones distintas, más fuentes oficiales aplicables antes de afirmar cumplimiento; no se alcanzan añadiendo etiquetas al SVG de vivienda.

## Verificación reproducible

- `node --test web/tests/drawing-package.test.mjs`: **4/4**, incluyendo SVG/ZIP determinista, identidad entre hojas, geometría de dos recortes, áreas/cotas derivadas, rechazo de artefactos incoherentes y replay íntegro de `origen-v8.json` con WASM.
- `npm test --prefix web`: **79/81** en este sandbox. Los **dos fallos** preexistentes de comparación CLI↔WASM requieren ejecutar `cargo`, ausente aquí; los otros 79 pasaron. El proyecto Rust y el WASM versionado no se cambiaron. No se debe llamar a esto 81/81 ni aludir a QA Windows.
- `./node_modules/.bin/vite build && node ../scripts/write-offline.mjs` desde `web/`: **pasó**; `dist/web/core.wasm` coincide en SHA-256 con el versionado `fe95bb201e1bcb92574e09bc196670062fdc75da3b13502f7e2cb56dc6ba0874`.
- Chromium headless/Linux sobre el bundle de producción: **1/1** prueba ampliada, miniaturas cargadas y descarga ZIP con 3 hojas, manifest y JSON reabrible; vista y exportación deshabilitadas tras editar el encargo; las miniaturas y el ZIP también funcionan **sin red después de recargar desde el caché y reabrir una copia local con replay Rust**. SVG XML analizado y vistas renderizadas localmente para inspección visual. Ni eso ni el ZIP de ejemplo prueban el EXE Tauri/Windows. El EXE Zig/navegador entregado **antes** de este corte tampoco contiene estas nuevas láminas hasta que se reconstruya.

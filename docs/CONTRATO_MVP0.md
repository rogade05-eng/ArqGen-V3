# Contrato correctivo — MVP-0 de ARQ GEN

> **Histórico:** documenta el primer corte sin muros. Para áreas, muros y vanos de MVP-0.1, leer [`CONTRATO_MVP01.md`](CONTRATO_MVP01.md); para equipamiento, [`CONTRATO_MVP02.md`](CONTRATO_MVP02.md); para el corte actual, [`CONTRATO_MVP05.md`](CONTRATO_MVP05.md). Sus definiciones sustituyen las de esta página cuando difieren.

**Estado:** implementado parcialmente en este repositorio (núcleo experimental). **Fecha:** 2026-09-25.

Este contrato sustituye, **solo para el primer corte ejecutable**, las partes incompatibles de `ARQ GEN TAURI.txt`. La especificación maestra sigue describiendo la visión del producto; no debe confundirse con las funcionalidades ya implementadas.

## 1. Alcance y límites

- Una **vivienda unifamiliar de una planta**, en **parcela rectangular**, con **acceso frontal centrado**, terreno plano y orientado por una de cuatro direcciones cardinales. No se generan parcelas irregulares, escaleras, patios interiores, estacionamiento ni estructuras.
- Programa estructurado: sala-comedor, cocina, **1–4 dormitorios** y **1–2 baños**. Área objetivo **construida orientativa**, no una orden para reducir áreas mínimas. Se dibujan habitaciones, corredor, puertas y ventanas obligatorias. Los baños no se consideran ventilados/verificados por este prototipo.
- Reglas **genéricas, ilustrativas y no certificadas**, leídas desde `knowledge/generic-house.json`. No se emiten declaraciones de conformidad legal, licencias, plantas de obra, memoria normativa ni DXF/PDF. El SVG es un **esquema conceptual**.
- Motor en **Rust 2021 sin dependencias externas**, reutilizado en CLI y compilado a WebAssembly para la interfaz offline. La interfaz Web aún **no es** Tauri: Tauri 2/SQLite/sidecar Python y el soporte YAML son siguientes hitos. JSON es el formato puente explícito del MVP-0; el conocimiento permanece en datos editables, no en código. No se representa esta etapa como el MVP-1 completo.

## 2. Modelo geométrico y de área

Coordenadas en metros: `x` de izquierda a derecha y `y` desde el frente hacia el fondo. La parcela mide `width × depth`. La envolvente edificable es el rectángulo tras aplicar los retiros configurados; **no** representa la huella elegida. La huella es la **unión sin superposiciones interiores** de los locales y el corredor; no se rellena automáticamente toda la envolvente.

- `plot_area = width × depth`.
- `max_footprint = min(buildable_area, plot_area × max_coverage)`.
- `max_built_area = plot_area × max_far`; para una sola planta, el área construida del esquema coincide con su huella modelada.
- `built_area = Σ área de locales + área del corredor`. Las áreas **no incluyen espesores de muro** en este primer corte; se informa expresamente al usuario. No se añade superficie construida para el acceso exterior. Antes de una documentación profesional debe añadirse el espesor de muros y recalcular áreas bruta y útil de forma separada.
- La orientación de fachada permite mostrar el norte y registrar el lado de las ventanas; **no** equivale a un estudio solar ni de ventilación.

No se deriva un supuesto máximo de plantas mediante `FAR / max_footprint`; el motor soporta **exactamente una**. Si los límites no permiten la huella, se devuelve inviabilidad, no una planta inválida.

## 3. Entrada/salida y validación

El motor recibe un JSON con `site {width, depth, front_orientation}`, `program {bedrooms, bathrooms, target_built_area}`, `seed` y un snapshot `rules`. Se validan los rangos y todas las claves obligatorias. `rules` incluye identidad/versión/estado ilustrativo, retiros, ocupación, FAR, anchuras de puertas y corredor, recorrido máximo y mínimos de locales. El CLI lee el encargo y el archivo de conocimiento por separado; la UI adjunta el mismo JSON de conocimiento en memoria.

La salida tiene `status = "ok" | "infeasible" | "error"`; solo `ok` incluye alternativas. **Nunca** se selecciona un candidato con una restricción dura incumplida. Reglas duras del corte: geometría dentro de la envolvente y sin solapamiento de interiores; cardinalidad exacta; mínimos dimensionales/áreas; corredor y puertas de anchura suficiente; todos los locales accesibles desde el acceso por el corredor; ventanas exteriores suficientes en sala, cocina y dormitorios; recorrido de evacuación bajo el umbral genérico; límites de huella y FAR. Las heurísticas blandas (área deseada, concentración de servicios, circulación) se muestran como métricas/avisos y **no** se confunden con normativa.

Se generan variantes con una semilla explícita. Los IDs y el orden, las razones de colocación y la geometría son estables para el mismo input, snapshot de reglas y versión del motor; no se introducen fechas ni UUID aleatorios en la salida semántica. Se devuelven **hasta tres alternativas válidas y geométricamente distintas**. Si no existen tres, se muestran menos con explicación. `infeasible` incluye razones sin fabricar propuestas: significa **sin solución hallada dentro de los esquemas de dos franjas y las variantes evaluadas**, no una prueba matemática de que ningún diseño pueda funcionar en esa parcela. Cualquier aprobación en la UI es **preferencia preliminar** del arquitecto, no una certificación.

## 4. Cambios de contrato respecto de la especificación maestra

| Hallazgo del informe | Resolución de este corte |
| --- | --- |
| P0-1 candidatos parciales presentables | El filtrado de factibilidad precede a la comparación; 0–3 propuestas, sin `unwrap` sobre listas vacías. |
| P0-2 dos plantas / irregular | Diferido; nivel único y terreno rectangular son restricciones explícitas de entrada. |
| P0-3 límites de área | Envolvente, huella elegida y FAR independientes; nunca se infiere `max_floors` del cociente de áreas. |
| P0-4 `count` frente a IDs | Se crean instancias `bedroom-1`, `bedroom-2`... y una decisión por instancia. |
| P0-5 circulación sin reserva | El pasillo longitudinal se reserva **antes** de colocar salas y dormitorios; cada local se coloca junto a él. |
| P0-6 cumplimiento normativo | Reglas demo no certificadas, descargo visible y ausencia de afirmaciones legales. |
| P1-1 contratos en conflicto | `core/src/model.rs` es la fuente de verdad implementada para este corte. |
| P1-2 YAML/DSL sin esquema | Se usa JSON pequeño y validado en el núcleo; no se interpreta ni se simula el DSL general. YAML queda para un hito posterior. |
| P1-3 reproducibilidad | Hash canónico del input y reglas, IDs derivados, ningún timestamp/ID aleatorio en el resultado. No hay recarga parcial. |
| P1-4 trazabilidad tardía | Cada candidato incluye decisiones ya desde el primer corte. |

## 5. Criterios de aceptación del corte

1. `cargo test --offline` valida geometría, restricciones, cardinalidad, determinismo, entradas inviables y escaping de salida.
2. CLI: `cargo run --offline -p arqgen-core --bin arqgen -- examples/rectangular.json --rules knowledge/generic-house.json` emite JSON reproducible; `--svg ruta.svg` exporta la primera alternativa **si existe**.
3. El frontend usa **el mismo motor Rust compilado a WASM**; `npm run dev` sirve una interfaz offline (sin peticiones a servicios remotos). Las URL al motor son relativas.
4. En ningún resultado se afirma validez legal o de obra. En el UI son visibles alcance, fuentes de reglas y límites del cálculo.

## Siguientes hitos (no implementados aquí)

Primero: espesores de muro y áreas útiles/brutas, mobiliario y holguras, puertas accesibles y encuentros geométricos complejos, catálogo/rulesets validados con procedencia por artículo, persistencia SQLite y undo/redo. Después: múltiples niveles y parcelas irregulares con un modelo multipolígono, YAML versionado, IPC Tauri 2 y empaquetado Windows; por último documentación profesional bajo revisión colegiada. Cada hito debe mantener la regla de no presentar diseños inviables.

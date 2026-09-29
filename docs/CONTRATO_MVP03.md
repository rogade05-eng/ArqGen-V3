# Contrato correctivo — MVP-0.3 de extracción de baños en planta

> **Histórico:** describe la reserva 2D previa al predimensionado nominal. El corte actual está en [`CONTRATO_MVP05.md`](CONTRATO_MVP05.md), que amplía el [predimensionado MVP-0.4](CONTRATO_MVP04.md); ambos usan hipótesis, **no** caudal entregado ni ventilación efectiva. Las reglas geométricas aquí descritas siguen vigentes.

**Estado:** implementado en Rust nativo, CLI, WebAssembly y cliente web. **Fecha:** 2026-09-25. Complementa [`CONTRATO_MVP02.md`](CONTRATO_MVP02.md) (equipamiento y franjas de uso) y [`CONTRATO_MVP01.md`](CONTRATO_MVP01.md) (áreas, muros y vanos). Solo se generan viviendas de una planta en parcelas rectangulares, mediante dos franjas de locales; los valores de `knowledge/generic-house.json` son **ilustrativos, no certificados**.

## 1. Qué se reserva, y qué NO se asegura

Cada baño de una alternativa `ok` tiene `bath_exhaust` con `mode: "direct_exterior_exhaust_reservation"`, `geometry_status: "outlet_and_route_reserved"`, `airflow_status: "not_evaluated"` y cinco datos geométricos: `outlet` (rectángulo que atraviesa el muro lateral exterior), `route` (proyección horizontal **en planta** desde la cara interior de fachada hacia el local), `pickup` (cuadro interior conectado a la ruta), `run_length` (distancia en planta hasta el centro de la toma) y `direction` cardinal de la fachada. Los demás locales tienen `bath_exhaust: null`. El valor agregado `bathroom_exhaust_status: "geometry_reserved_only"` **no** significa que los baños estén ventilados: `bathroom_ventilation_status` y `room.ventilation_status` **permanecen** `"not_evaluated"`.

El ruleset obligatorio `rules.bath_exhaust` contiene `outlet_span`, `route_band`, `fixture_gap` y `max_run` (metros). En la demostración son respectivamente **0,16 / 0,16 / 0,02 / 3,00 m**. Son hipótesis geométricas de reserva, no caudal, área libre efectiva, diámetro de conducto instalado ni parámetros reglamentarios. Un ancho de 0,16 m **en planta** no afirma una sección hidráulica ni que el equipo suministre ventilación suficiente. El punto interior se fija a media anchura útil, y la banda transversal se centra en la holgura **entre ducha e inodoro**; el conjunto se refleja según el lado del pasillo.

## 2. Validación dura y cobertura

Antes de seleccionar/puntuar/exportar un candidato, Rust rederiva el trazado desde el mismo ruleset, compara todos sus rectángulos, longitud y dirección, y exige:

- Espacio transversal para `max(outlet_span, route_band) + 2 × fixture_gap` entre las huellas de ducha e inodoro; `run_length ≤ max_run`.
- `route` y `pickup` válidos, dentro de `room.usable_rect` y conectados con solape positivo completo; la ruta no invade huellas sólidas ni el barrido de la puerta. El trazado **puede cruzar la banda peatonal o una zona de uso**: es una reserva hipotética en otro plano, cuya separación vertical **NO se verifica**.
- `outlet` en el muro exterior del propio baño, con jambas `rules.openings.corner_clearance` a los extremos; contacto exacto entre la ruta y la cara interior de la fachada. Cuando existe ventana de baño, la salida deja entre ambos vanos una franja continua de muro de al menos `corner_clearance`.
- El conjunto de **todos** los vanos —entrada, puertas de habitaciones, ventanas y nuevas salidas— se comprueba contra las franjas de muro y frente a solapamientos mutuos. `wall_allowance_area` sigue contando esas franjas **incluidos los huecos**, sin tratarlas como volumen de material eliminado; el balance bruto/útil no cambia.

Una regla ausente o mal formada produce `status="error"`; falta de espacio, salida conflictiva o tramo superior al máximo producen `status="infeasible"` con `alternatives: []` si ninguna de las 48 variantes limitadas puede pasar. La CLI **no escribe** un SVG nuevo cuando no hay alternativa; no se inventan alternativas parciales. `infeasible` no demuestra imposibilidad para otros patrones o equipos.

**Fuera de alcance y NO acreditado:** equipo extractor, activación y alimentación, caudal y renovaciones/hora, pérdidas de carga, rejillas/área libre, sección/altura/recorrido real del conducto, interferencias en techo o estructura, condensados, suministro de aire de reposición, compatibilidad del vertido con distancias a vecinos/ventanas, habitabilidad, ventilación legal, accesibilidad y aprobación profesional. La ruta es una **proyección en planta**, no un conducto ejecutable. No debe instalarse ni presupuestarse a partir del esquema.

## 3. Datos, interfaz y verificaciones

El corte cambia a `engine_version = "mvp0.3-rust-0.4.0"` y `rules.version = "0.4.0"`. El hash cubre el ruleset íntegro y la versión del motor; las preferencias anteriores se invalidan. JSON, SVG, traza de reglas y vista web representan el mismo trazado validado. El SVG marca salidas/recorridos en violeta y conserva el rótulo «NO APTO PARA OBRA»; la interfaz dice **«extracción reservada»** y **«caudal no evaluado»**, nunca «baño ventilado».

Reproducir: `cargo fmt --all -- --check`, `cargo test --offline --workspace`, `npm run build --prefix web` (regenera `web/public/core.wasm`) y `npm test --prefix web`. Las pruebas reconstruyen áreas y comprueban cada abertura sobre muro, rutas/extracción serializadas, las cuatro orientaciones, espesores variables, programas y parcela; ejercitan reglas de extracción imposibles, conflictos ventana/salida, entrada antigua/malformada, mutaciones de salida/ruta/toma/reglas y el mismo motor en CLI y WASM. El ejemplo semilla 42 conserva tres alternativas y la primera ronda **94,9 m² brutos = 82,8 m² útiles + 12,1 m² de reserva de muros y vanos**.

### Trabajo posterior (aún pendiente para ventilación efectiva)

[MVP-0.4](CONTRATO_MVP04.md) calcula un objetivo **nominal e ilustrativo**, pero para afirmar **ventilación efectiva** siguen haciendo falta equipos/catálogo verificables, caudal realmente entregado con pérdidas de carga y aire de reposición, conductos 3D con alturas y encuentros, descarga segura y reglas con ámbito/procedencia. `not_evaluated` permanece para ventilación. Fuera de este corte siguen Tauri 2/SQLite, normativa certificada, parcelas irregulares y varias plantas.

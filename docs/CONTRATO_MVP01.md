# Contrato correctivo — MVP-0.1 de ARQ GEN

> **Histórico:** describe el corte sin equipamiento. Para mobiliario/aparatos y zonas de uso, leer [`CONTRATO_MVP02.md`](CONTRATO_MVP02.md); el corte actual se describe en [`CONTRATO_MVP05.md`](CONTRATO_MVP05.md). Las definiciones de muros, vanos y áreas de este documento siguen vigentes.

**Estado:** primer modelo geométrico ejecutable de muros/vanos, Rust + WASM. **Fecha:** 2026-09-25. Este contrato **amplía y prevalece**, para las áreas y las aberturas del corte actual, sobre [`CONTRATO_MVP0.md`](CONTRATO_MVP0.md). Los restantes límites de MVP-0 continúan: vivienda de una planta en parcela rectangular, reglas ilustrativas **no certificadas** y revisión profesional obligatoria.

## 1. Geometría y significado de las superficies

Coordenadas en metros. El frente de la parcela está arriba (`y` creciente hacia el fondo). La **huella bruta** es la unión de las celdas *sin solapamiento interior* (`room.rect` + `corridor`) colocadas enteramente dentro de la envolvente. La suma de esas celdas es `built_area` y se contrasta con ocupación máxima y FAR. El objetivo `program.target_built_area` compara contra **esa huella bruta**; sigue siendo una preferencia blanda.

El ruleset `generic_house_demo@0.2.0` incluye `walls.exterior` y `walls.partition` (m) y `openings.corner_clearance` / `openings.swing_clearance` (m). Los valores iniciales son 0,18 m de muro exterior y 0,12 m de tabique; son **supuestos geométricos de prueba, no detalles constructivos aprobados**.

- Cada habitación tiene `rect` (celda bruta) y `usable_rect`/`usable_area` (rectángulo libre). La cara exterior consume `walls.exterior`; entre dos celdas que comparten pared cada una reserva **medio tabique**. Primera/última habitación de una franja: muro exterior en el frente/fondo; entre habitaciones: medio tabique por cada lado. `room.area` se mantiene como alias de `usable_area` **desde esta versión**; `gross_cell_area` permite comparar la diferencia.
- El pasillo tiene una celda bruta continua. `corridor_usable_segments` la divide en bandas longitudinales libres que se estrechan donde el pasillo da al exterior; cada segmento tiene al menos `corridor.min_width` libres. Frente y fondo consumen muro exterior. No se dibuja ni contabiliza como interior el acceso exterior.
- `wall_zones` son **franjas 2D disjuntas** que completan la diferencia entre celdas brutas y zonas libres. `wall_allowance_area` incluye la proyección en planta de **los vanos** (puertas/ventanas); NO equivale al volumen de material del muro. La identidad verificada en cada alternativa es `built_area = usable_area + wall_allowance_area`, siendo `usable_area = Σ room.usable_area + circulation_usable_area`. No se atribuye doblemente la superficie compartida de los tabiques.
- Se modelan únicamente muros idealizados, no esquinas estructurales, espesores variables, alturas/sillas, cimentaciones, instalaciones ni resistencia/materialidad. El balance no sustituye un cómputo constructivo o un plano de obra.

## 2. Puertas, ventanas y validación dura

`door.opening`/`window.opening`/`entrance.opening` son rectángulos de vano que deben quedar **cubiertos por una franja de muro** y no solaparse entre sí. Todas las puertas de locales abren al pasillo, con un barrido conservador de 90° representado por `door.swing`, de lado igual a la luz de puerta y contenido en el rectángulo libre de un local vacío. Se validan anchura, separación a esquinas, margen al muro opuesto y que la **totalidad del umbral** colinde con un tramo libre de pasillo. La puerta principal tiene vano de fachada y un barrido interior comprobado contra los segmentos libres del pasillo con margen lateral. Las ventanas de sala, cocina y dormitorios atraviesan fachada exterior, dejan jambas a esquinas y superan el cociente ilustrativo `ancho × alto / área útil del local`.

La trayectoria desde el acceso al extremo más alejado de cada local se aproxima por una ruta Manhattan conservadora y se contrasta con el **umbral de ejemplo**, sin considerarla cálculo de evacuación reglamentario. Cada alternativa se vuelve a validar **antes** de puntuarse o seleccionarse: áreas útiles/dimensiones, huella bruta, solapamientos, balance de franjas, acceso, vanos y recorridos. `infeasible` significa que no se halló una configuración válida en esta **búsqueda acotada**, no que toda arquitectura de la parcela sea inviable. Nunca se exporta una alternativa con una restricción dura incumplida.

**Sin validación en este corte:** ocupación por muebles/aparatos, holguras de uso de baños, accesibilidad normativa, recorrido de evacuación legal, ventilación de baños, ventilación cruzada, iluminación suficiente conforme a una jurisdicción, estructura, colindancias o protección contra incendios. `bathroom_ventilation_status = "not_evaluated"` y el aviso visible **no** se convierten en `ok` por disponer de un rectángulo libre. Ninguna regla de demostración puede declararse certificada.

## 3. Versionado, interfaz y pruebas

La entrada `rules.walls` y `rules.openings` es **obligatoria**; paquetes antiguos sin ellas dan `status="error"` sin planos. `engine_version = "mvp0.1-rust-0.2.0"` y el snapshot `rules.version = "0.2.0"` cambian el `input_hash` y evitan reutilizar preferencias de versiones anteriores. El JSON y el SVG se obtienen del mismo layout validado; el SVG dibuja zonas útiles, franjas de muro y vanos, y se rotula «no apto para obra». La interfaz muestra la igualdad de áreas, cuadro de locales **útiles**, anchos de puerta y advertencias; la preferencia guardada es preliminar.

Para reproducir, desde la raíz: `cargo fmt --all -- --check`, `cargo test --offline --workspace`, `npm run build --prefix web`, `npm test --prefix web`. El fixture `examples/rectangular.json` con reglas demo genera tres alternativas en la semilla 42; pruebas Rust/WASM comprueban balance, límites, puertas demasiado grandes, ventanas inviables, muros inválidos, variaciones de programa y entrada imposible sin SVG. Un caso del fixture ronda **94,9 m² brutos = 82,8 m² útiles + 12,1 m² de franjas de muro/vano** (valores mostrados redondeados).

### Queda para hitos posteriores

Mobiliario y aparatos reales con holguras normativas, paredes estructurales y encuentros complejos, área de muros/materiales real, ventilación verificable, catálogo legal con procedencia por artículo/jurisdicción, persistencia SQLite/undo y empaquetado Tauri/Windows. Múltiples niveles y parcelas no rectangulares requieren contratos geométricos independientes.

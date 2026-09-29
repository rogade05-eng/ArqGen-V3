# Contrato correctivo — MVP-0.2 de equipamiento geométrico

> **Histórico:** describe el corte anterior a la reserva de extracción de baños. Para el contrato actual, leer [`CONTRATO_MVP05.md`](CONTRATO_MVP05.md) (posterior al predimensionado [`CONTRATO_MVP04.md`](CONTRATO_MVP04.md) y a la reserva [`CONTRATO_MVP03.md`](CONTRATO_MVP03.md)); las comprobaciones de equipamiento aquí descritas siguen vigentes.

**Estado:** implementado en Rust nativo, CLI, WebAssembly y cliente web. **Fecha:** 2026-09-25. Amplía [`CONTRATO_MVP01.md`](CONTRATO_MVP01.md), que sigue siendo la referencia para muros, áreas brutas/útiles y vanos. Una vivienda de **una planta, parcela rectangular y dos franjas de locales**, con reglas **ilustrativas no certificadas**, sigue siendo el único alcance ejecutable. La especificación `ARQ GEN TAURI.txt` describe una visión posterior, no funcionalidades ya disponibles.

## 1. Contrato de objetos y uso

El snapshot obligatorio `rules.furnishings` contiene `min_aisle` (m) y dimensiones `width` × `depth` (m) de `sofa`, `dining_table`, `counter`, `refrigerator`, `bed`, `shower`, `toilet` y `basin`. El ruleset demo `generic_house_demo@0.3.0` fija **0,55 m** como ancho de comprobación geométrica de ejemplo; no representa un mínimo universal ni un ancho reglamentario accesible. Las dimensiones son huellas esquemáticas, no un catálogo de fabricantes. El contrato de entrada rechaza claves desconocidas, valores fuera de rango y rulesets antiguos sin esta sección; **no** acepta `regulatory_status = certified`.

Cada `room` ahora publica:

- `furnishings[]`: ID derivado del local (`bedroom-1-bed`, etc.), tipo, nombre, `footprint` sólido y una o más `use_zones` libres. Se colocan **sofá y mesa** en sala-comedor; **encimera y frigorífico** en cocina; **cama** con acceso lateral y a los pies en cada dormitorio; **ducha, inodoro y lavabo** en cada baño.
- `access_route[0..2]`: rectángulo longitudinal de **ancho `min_aisle`** y ramal transversal desde él hasta la porción central del umbral interior. Ambos se superponen en un cuadrado de al menos `min_aisle²` y enlazan con cada zona de uso con ese mismo solape mínimo. La banda y las zonas se representan en **planta**; no hay cálculo de recorrido accesible/evacuación con mobiliario.
- `furnishing_status: "illustrative_geometric_fit"` **solo en alternativas ya verificadas**. No es una declaración legal.

Las coordenadas se generan desde la fachada exterior de la habitación y se reflejan a derecha/izquierda para mantener una disposición determinista. El motor implementa **una disposición por tipo de local**, no una optimización ni búsqueda exhaustiva de amueblamiento; no se fabrican muebles alternativos si esta plantilla falla. `room.usable_area` **no descuenta** los muebles: sigue siendo área arquitectónica interior después de reservar muros y antes de ocuparla con objetos. La igualdad `built_area = usable_area + wall_allowance_area` sigue intacta.

## 2. Restricciones duras y límites

Antes de puntuar, seleccionar o exportar una alternativa, el motor **rederiva** huellas, zonas y recorrido del ruleset suministrado, contrasta el candidato y verifica que: (a) todos los rectángulos son válidos y están dentro de `room.usable_rect` (por tanto, fuera de franjas de muro); (b) ninguna huella colisiona con otra huella, el barrido de puerta ni el recorrido; (c) las zonas de uso no colisionan con ninguna huella ni barrido; (d) cada zona enlaza con el recorrido libre y el ramal desemboca en el ancho central de la puerta; (e) las huellas dejan sin ocupar una franja de **0,20 m** proyectada hacia dentro desde las ventanas modeladas. Las zonas libres **pueden compartir superficie entre sí**; esto no equivale a permitir un sólido dentro de una holgura. El recorrido **puede cruzar el barrido** durante la apertura/cierre, porque comienza precisamente en la puerta; el barrido sí impide ocupar físicamente esa zona con muebles o zonas de uso fijas.

Si un objeto no cabe, un ruleset cambia de modo incompatible o se alteran las zonas/recorrido tras construir el candidato, se descarta **toda esa variante**. Si ninguna de las 48 variantes de la búsqueda acotada pasa, la respuesta es `infeasible` con `alternatives: []` y razones; no se escribe SVG desde la CLI. «Sin alternativa» no demuestra imposibilidad arquitectónica fuera de estas dos franjas y plantillas.

**No se verifican**: altura, ergonomía real, giro de silla de ruedas, accesibilidad legal, dimensiones de fabricantes, radio real de hoja curva, personas en movimiento, incendios, evacuación reglamentaria, ventanas operables, extracción, renovación de aire, ventilación cruzada, instalaciones, agua/saneamiento, impermeabilización, estructura ni detalles de encuentros. Una ventana geométrica **no** demuestra iluminación o ventilación legal. `bathroom_ventilation_status` y `room.ventilation_status` de baños siguen en `not_evaluated`; los baños demo no tienen ventana/extractor modelado. Las métricas previas de «distancia Manhattan hasta esquina» siguen orientativas **sin** ponderar desvíos por muebles, no son rutas de evacuación verificadas.

## 3. Versionado, vista y pruebas

`engine_version = "mvp0.2-rust-0.3.0"` y `rules.version = "0.3.0"`. Junto con el snapshot íntegro de reglas, cambian `input_hash` y los IDs de alternativa; se invalida la preferencia local anterior. JSON, traza y SVG representan las **mismas huellas y zonas verificadas**; la interfaz permite consultar el listado por habitación y mostrar/ocultar los trazos de holgura y paso sin modificar la geometría ni el SVG exportado. El aviso «NO APTO PARA OBRA» permanece en el SVG y el navegador. Ningún estado `ok` certifica normas profesionales.

Ejecutar `cargo fmt --all -- --check`, `cargo test --offline --workspace`, `npm run build --prefix web` (regenera `web/public/core.wasm`) y `npm test --prefix web`. Las pruebas Rust y WASM comprueban las 3 alternativas del ejemplo, geometría leída de vuelta del JSON, áreas, rutas y zonas, reglas ausentes, una cama que no cabe, anchos imposibles, corrupción de huella/zona/recorrido y cambios posteriores de reglas. El ejemplo semilla 42 conserva aproximadamente **94,9 m² brutos = 82,8 m² útiles + 12,1 m² de reserva de muros y vanos** en la primera opción.

### Para cortes posteriores

Ventilación y condiciones reales de baños (extracción/aberturas con prestaciones), catálogo de equipamiento de fabricantes y maniobra accesible, instalaciones y encuentros constructivos, normas con procedencia por jurisdicción/artículo, persistencia SQLite con undo/redo y shell Tauri 2. Parcelas irregulares y multipiso requieren contratos adicionales; mantener la regla de no exportar candidatos con restricciones duras incumplidas.

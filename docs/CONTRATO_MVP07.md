# Contrato correctivo — MVP-0.7: cuaderno de escenarios comparables

**Estado:** implementado en la interfaz web (2026-09-25). Amplía [MVP-0.6](CONTRATO_MVP06.md), pero **no cambia** el algoritmo de generación ni la validación Rust. El núcleo CLI/WASM conserva `engine_version: "mvp0.6-rust-0.7.0"`, `core.version: "0.7.0"` y `knowledge/generic-house.json@0.7.0`; solo la aplicación web pasa a `0.8.0`. Por ello, los hashes de las mismas entradas y sus preferencias anteriores no se invalidan artificialmente.

## 1. Flujo y comparabilidad

1. Generar normalmente. Guardar explícitamente una corrida `ok` o `infeasible` en el **cuaderno en memoria**; `error` no tiene hash ni variantes evaluadas y no se guarda. Tras editar una hipótesis, **regenerar con Rust** antes de poder guardar. Se admiten **hasta tres** corridas distintas; repetir una entrada idéntica no añade columna.
2. Las columnas admiten diferencias **solo** en los tres campos de `rules.bath_pressure`: presión y caudal del segundo punto nominal y reserva de presión. Deben coincidir **parcela, programa, semilla, todo el resto de las reglas** (incluyendo la versión), y `engine_version`. La clave de comparabilidad se construye sobre esa entrada restante de forma canónica; el núcleo sigue originando cada `generation` y su `input_hash`. Las colisiones de hash con entradas distintas se rechazan en el cuaderno, que no considera el hash una firma criptográfica.
3. Al cambiar parcela, programa u orientación o semilla desde el formulario, las columnas se **limpian** para impedir una comparación ceteris paribus engañosa. Cambiar solo las tres hipótesis mantiene los escenarios anteriores, pero marca la vista actual como **sin regenerar** e impide guardar/exportar o aprobar esa **corrida actual**. La comparativa de escenarios ya guardados puede exportarse independientemente.
4. Cada columna muestra la pareja y reserva exactas, `generated`, `rejected`, número de alternativas **mostradas** (no el total de variantes aceptadas), estado `ok`/`infeasible`, motivos completos y `input_hash`. Los motivos son primeros rechazos de las variantes ensayadas, no causas normativas o mediciones. La ausencia de variantes por fallo previo al bucle queda en `generated: 0` con el motivo previo. **No** se asigna una puntuación global, no se declara un «ganador» ni se infiere rendimiento de un ventilador.
5. «Regenerar y examinar» restaura los campos guardados y **vuelve a ejecutar el WASM Rust**. No presenta una respuesta cacheada como si fuera una validación nueva. Eliminar una columna o limpiar el cuaderno no cambia las reglas base ni la generación del panel principal.

El cuaderno es **volátil**: no escribe entradas, planos ni reglas en `localStorage`, SQLite o una red; al cerrar o recargar la pestaña se pierden las columnas. La preferencia preliminar de una alternativa individual continúa siendo un mecanismo separado, asociado al hash, **no** una aprobación técnica.

## 2. Exportación y alcance técnico

Solo con **dos o tres** corridas guardadas puede exportarse un JSON de comparación:

```json
{
  "format": "arqgen-illustrative-comparison-v1",
  "engine_version": "mvp0.6-rust-0.7.0",
  "varying_assumptions": ["fan_reference_pressure_pa", "fan_reference_flow_m3h", "assumed_reserve_pa"],
  "ventilation_status": "not_evaluated",
  "scenarios": [ { "input": "encargo y reglas completos", "generation": "respuesta Rust completa" } ]
}
```

La línea `scenarios` anterior es **esquemática**: se requieren **dos o tres objetos**, cada uno con su `input` JSON real y la `generation` Rust completa, incluidos histogramas y SVG de alternativas válidas. No se recalcula ni se inventa una alternativa para `infeasible`; sus `alternatives` permanecen vacías. El archivo puede contener información introducida en el encargo: **no incorporar secretos**. Para reproducir una columna por CLI, extraer `input.rules` como archivo de `--rules` y pasar `input.site`, `input.program`, `input.seed` como encargo. La comparación no reemplaza el JSON individual `{input, generation, selection}` ni es un informe normativo.

**Límite obligatorio:** los puntos son supuestos de demostración; `bath_pressure.status` sigue en `hypothetical_pressure_screen_only`, `delivered_flow_status` y ventilación siguen en `not_evaluated`. «Más alternativas» o «menos descartes» significa solo que **este generador, con esas hipótesis, pasó más cribados**, nunca que un sistema real entregue más caudal. No se selecciona equipo, ni se obtiene curva de fabricante, red 3D, pérdidas reales, punto de operación, aire de reposición o ventilación certificada. Revisión profesional antes de cualquier obra.

## 3. Comprobaciones

`web/tests/comparison.test.mjs` llama al mismo WASM y prueba el caso `0/48`, el parcial `12/48`, el inviable `48/48` y el fallo previo `0/0`; igualdad canónica de reglas restantes, rechazo de cambios de encargo/semilla/reglas fijas, duplicados y colisiones, límite de tres, snapshot inmutable, rechazo de `error` y `rejection_summary` corrupto, y exportación reproducible. Se mantienen las **37 pruebas Rust** y las pruebas previas de paridad **byte a byte CLI/WASM**, pues el motor no cambió. La interacción web se verificó también en escritorio y móvil: guardado, bloqueo por cambios pendientes, exportación, regeneración de una columna, inviabilidad y limpieza por semilla.

Desde la raíz: `cargo fmt --all -- --check`, `cargo test --offline --workspace`, `npm run build --prefix web`, `npm test --prefix web`. Para la vista local: `npm run dev --prefix web`. Browser, Node y Cargo son herramientas de desarrollo, **no servicios necesarios al usuario final** de la web estática.

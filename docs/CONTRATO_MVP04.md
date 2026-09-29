# Contrato correctivo — MVP-0.4: predimensionado nominal de extracción de baños

> **Histórico:** describe el corte previo a la pantalla de presión [MVP-0.5](CONTRATO_MVP05.md). Sus reglas de caudal objetivo, holgura y sección supuestas siguen vigentes; el nuevo corte no acredita pérdidas reales ni caudal entregado.

**Estado:** implementado en el núcleo Rust, CLI, WASM y cliente web (2026-09-25). Amplía el contrato histórico [MVP-0.3](CONTRATO_MVP03.md) sin sustituir su reserva de extracción **en planta**. Sigue vigente el balance de áreas [MVP-0.1](CONTRATO_MVP01.md) y el equipamiento ilustrativo [MVP-0.2](CONTRATO_MVP02.md). Solo hay una planta, parcela rectangular y una búsqueda limitada de dos franjas; las reglas son de demostración **sin carácter normativo ni fuente de fabricante**.

## 1. Hipótesis versionadas y unidades

El objeto **obligatorio** `rules.bath_airflow` tiene nueve campos numéricos positivos, sin claves extras. El motor los valida estrictamente y los incluye en el hash canónico del encargo:

| Campo | Demo | Interpretación exclusivamente ilustrativa |
| --- | ---: | --- |
| `assumed_ceiling_height` | 2,60 m | Altura interior supuesta para calcular volumen y envolvente vertical. |
| `target_ach` | 4,0 h⁻¹ | Objetivo de renovaciones por hora, **no** renovación alcanzada ni mínimo legal. |
| `fan_free_air_rating` | 120 m³/h | Referencia **nominal en aire libre**, sin ventilador elegido, conducto ni curva presión–caudal. |
| `door_undercut` | 0,025 m | Holgura libre supuesta bajo una puerta ideal, no medida ni garantizada. |
| `max_transfer_velocity` | 1,6 m/s | Límite de velocidad **hipotético** para ese paso de reposición. |
| `duct_height` | 0,16 m | Alto supuesto de una sección rectangular ideal. No es un conducto instalado. |
| `duct_bottom` | 2,30 m | Altura supuesta desde suelo hasta la base de esa sección. |
| `min_headroom` | 2,10 m | Gálibo supuesto que debe quedar bajo ella; **no** accesibilidad certificada. |
| `max_duct_velocity` | 2,0 m/s | Límite de velocidad hipotético para la sección ideal. |

Estos valores **no** proceden de una norma local ni de ensayos del equipo. Los rangos de entrada del parser solo evitan entradas absurdas: altura 2,20–4,00 m; objetivo 0,50–12 h⁻¹; referencia 10–500 m³/h; holgura 0,005–0,04 m; velocidad de transferencia 0,20–3,0 m/s; alto de sección 0,10–0,60 m; base 1,80–3,60 m; gálibo 1,80–2,50 m y velocidad en sección 0,20–5,0 m/s. Un valor **dentro** de esos intervalos sigue siendo solo una hipótesis. Una configuración con `duct_bottom < min_headroom` o `duct_bottom + duct_height > assumed_ceiling_height` es **entrada incoherente**, no un plano alternativo.

## 2. Cálculo por baño y restricción de candidatos

Tras dimensionar el baño útil (sin franjas de muro), colocar equipamiento y diseñar su reserva `bath_exhaust` en planta, el motor calcula, **para cada baño por separado** (la revalidación posterior comprueba primero la reserva y después el cálculo):

```text
volumen_supuesto_m3 = room.usable_rect.area() × assumed_ceiling_height
Q_objetivo_m3h      = volumen_supuesto_m3 × target_ach
A_reposición_m2     = room.door.width × door_undercut
v_reposición_mps    = Q_objetivo_m3h / (3600 × A_reposición_m2)
ancho_sección_m     = min(bath_exhaust.route.depth, bath_exhaust.outlet.depth)
A_sección_m2        = ancho_sección_m × duct_height
v_sección_mps       = Q_objetivo_m3h / (3600 × A_sección_m2)
```

Los datos de la ruta son *anchos en planta*; multiplicarlos por una altura supuesta **solo permite ensayar una sección idealizada**. No determina la sección libre de una rejilla, la forma de la salida, el diámetro equivalente ni la continuidad construible de un conducto. El motor descarta una variante si `Q_objetivo > fan_free_air_rating`, `v_reposición > max_transfer_velocity` o `v_sección > max_duct_velocity`. Comprueba también que la base supuesta alcance el gálibo y que el extremo superior no supere el techo supuesto. Recalcula resultados, reglas y geometría para detectar mutaciones antes de evaluar, seleccionar o exportar una alternativa; ningún valor derivado se toma como autoridad sin verificar. Al cambiar un ancho reservado o de puerta, un área útil o una regla, hay que volver a generar.

Una referencia nominal **en aire libre** puede ser superior al objetivo y aun así ser incapaz de vencer la pérdida de presión de la instalación: esta desigualdad **no acredita el caudal entregado**, la eficacia de la extracción ni la suficiencia legal. La holgura real puede desaparecer por umbral, acabado o puerta cerrada; tampoco se prueba que el aire de reposición exista aguas arriba. La banda 2D puede cruzar áreas de uso o paso: solo se cotejan alturas **numéricas supuestas**, sin sólidos 3D, coordinación con estructura, hueco real de fachada, tamaño de rejillas, descarga segura, ruido, condensados, suministro eléctrico, activación ni puesta en marcha.

## 3. Estados, trazabilidad y salidas

En una alternativa `ok`, **cada** baño tiene `bath_airflow` con `status: "nominal_precheck_only"` y `delivered_flow_status: "not_evaluated"`. Expone `target_ach`, `assumed_ceiling_height_m`, `room_volume_m3`, `target_flow_m3h`, `fan_reference_free_air_rating_m3h`, `transfer` (holgura, área y velocidad frente al límite) y `duct` (ancho/alto, sección, velocidades, base, coronación y gálibo supuestos). Los locales no-baño llevan `bath_airflow: null`. A escala de alternativa `bathroom_airflow_status: "nominal_precheck_only"`; **no cambia** `bathroom_exhaust_status: "geometry_reserved_only"`, `bathroom_ventilation_status: "not_evaluated"`, `room.ventilation_status: "not_evaluated"` ni el antiguo `bath_exhaust.airflow_status: "not_evaluated"` (este último refiere a caudal efectivo/entregado, no al objetivo numérico). No existe campo `delivered_flow_m3h`.

La traza incluye una decisión `generic_house_demo.bath_airflow@0.5.0` por baño con fórmula, área, límites y advertencias. El SVG conserva la proyección de reserva con etiqueta **«CAUDAL OBJETIVO NOMINAL · CAUDAL ENTREGADO NO EVALUADO · NO APTO PARA OBRA»**; la UI muestra por baño el *objetivo* junto a la referencia **en aire libre**, velocidades idealizadas y advertencias. No se dibuja un conducto 3D ni se lo llama extractor instalado. Solo `status="ok"` puede contener alternativas/SVG; reglas ausentes, desconocidas o incoherentes dan `error` sin planos; límites numéricos imposibles en todas las 48 variantes exploradas dan `infeasible`, `alternatives: []` y diagnóstico, sin SVG de CLI. «Inviable» no es una imposibilidad universal para otros esquemas/equipos.

El corte usa `engine_version = "mvp0.4-rust-0.5.0"`, `rules.version = "0.5.0"`, paquete Rust/web `0.5.0`. El hash incluye ambas versiones y **todo** el ruleset, invalidando preferencias locales anteriores. El ejemplo semilla 42 devuelve tres variantes; la primera conserva aprox. **94,9 m² brutos = 82,8 m² útiles + 12,1 m² muros/vanos**, y cada baño de esa variante tiene aprox. **6,55 m² útiles → 68,1 m³/h de objetivo nominal** (no entrega medida). Tests Rust/CLI/WASM verifican el mismo JSON, fórmulas independientes, mutaciones, reglas inviables, ausencia de SVG, determinismo y paridad byte a byte.

Reproducir desde raíz: `cargo fmt --all -- --check`, `cargo test --offline --workspace`, `npm run build --prefix web` (regenera `web/public/core.wasm`) y `npm test --prefix web`.

## 4. Lo que falta para afirmar ventilación

Seleccionar equipos con curvas y prestaciones verificables, calcular pérdidas de presión, redes y aire de reposición real; comprobar conducto/rejillas en 3D con encuentros, alturas, ruido y descarga segura, y verificar requisitos locales con normativa y procedencia, instalación y puesta en marcha. Hasta entonces el estado de ventilación **sigue** `not_evaluated`. Tauri/SQLite, varias plantas y parcelas irregulares permanecen fuera de este corte.

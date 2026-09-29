# Contrato correctivo — MVP-0.5: presupuesto de presión exclusivamente hipotético

**Estado:** implementado en Rust nativo, CLI, WebAssembly y cliente web (2026-09-25). Amplía [MVP-0.4](CONTRATO_MVP04.md) (caudal **objetivo** nominal), [MVP-0.3](CONTRATO_MVP03.md) (reserva **2D**) y los contratos previos de geometría/equipamiento. Sigue habiendo solo **una planta, parcela rectangular, dos franjas de locales y 48 variantes exploradas**. Ninguna regla demo es una norma ni proviene de una ficha de fabricante. Este corte **no selecciona un ventilador ni calcula caudal entregado**.

## 1. Referencias e hipótesis obligatorias

`rules.bath_pressure` es un objeto obligatorio de ocho campos, con claves y tipos estrictos. En el demo `generic_house_demo@0.6.0`:

| Campo | Demo | Significado **hipotético** |
| --- | ---: | --- |
| `fan_reference_pressure_pa` | 60 Pa | Presión estática del **segundo** punto nominal no verificado. El primero es `(0 Pa, rules.bath_airflow.fan_free_air_rating)`; no hay curva de fabricante. |
| `fan_reference_flow_m3h` | 90 m³/h | Caudal nominal **supuesto** a 60 Pa; debe ser estrictamente menor que el valor supuesto de 120 m³/h en aire libre. |
| `assumed_air_density_kg_m3` | 1,20 kg/m³ | Densidad para una presión dinámica *idealizada* a la velocidad objetivo. |
| `assumed_darcy_factor` | 0,04 | Factor de rozamiento Darcy **supuesto**, no determinado por material/rugosidad/Reynolds. |
| `assumed_bend_count` | 2 | Número entero supuesto de codos; no se han trazado/colocado en 3D. |
| `assumed_bend_k` | 1,5 | Coeficiente local supuesto **por codo**. |
| `assumed_outlet_k` | 2,0 | Coeficiente local supuesto de salida; **no** caracteriza una rejilla, equipo o descarga real. |
| `assumed_reserve_pa` | 20 Pa | Reserva adicional supuesta, **no** sustituto de pérdidas no modeladas. |

Rangos **de entrada, no normativos**: presión de segundo punto 5–500 Pa; caudal del segundo punto 1–500 m³/h; densidad 0,90–1,40 kg/m³; factor Darcy 0,005–0,20; 0–12 codos **enteros**; K por codo 0–5; K de salida 0–10; reserva 0–100 Pa. `fan_reference_flow_m3h >= fan_free_air_rating` es **error de reglas incoherentes**, no una variante viable. También se rechazan datos ausentes, sobrantes, fraccionales donde corresponde entero, no finitos o fuera de rango. Todas las hipótesis y versiones participan en `input_hash`.

## 2. Cálculo por cada baño, límites de rechazo

Después de diseñar el trazado y la sección nominal del [MVP-0.4](CONTRATO_MVP04.md), y antes de revalidar el candidato completo, para cada baño se utiliza la **velocidad a su Q objetivo** (no una velocidad medida):

```text
ancho_ideal = min(bath_exhaust.route.depth, bath_exhaust.outlet.depth)
alto_ideal  = rules.bath_airflow.duct_height
D_h        = 2 × ancho_ideal × alto_ideal / (ancho_ideal + alto_ideal)
L_supuesto = bath_exhaust.run_length + rules.walls.exterior
v_objetivo = bath_airflow.duct.velocity_at_target_mps
p_din      = 0,5 × assumed_air_density_kg_m3 × v_objetivo²
p_recto    = assumed_darcy_factor × (L_supuesto / D_h) × p_din
p_codos    = assumed_bend_count × assumed_bend_k × p_din
p_salida   = assumed_outlet_k × p_din
P_supuesto = p_recto + p_codos + p_salida + assumed_reserve_pa
Q_ref(P)   = Q_aire_libre + (fan_reference_flow_m3h − Q_aire_libre) × P / fan_reference_pressure_pa
```

**Solo se interpola** cuando `0 ≤ P_supuesto ≤ fan_reference_pressure_pa`. Si el presupuesto supera ese intervalo se **descarta la variante**: no se extrapola. Si `Q_ref(P_supuesto) < bath_airflow.target_flow_m3h` también se descarta. Se comprueban finitud y positividad de magnitudes geométricas antes de dividir. `Q_ref` es **capacidad de referencia lineal bajo datos supuestos**, nunca caudal de operación, entrega, medida, predicción del ventilador real ni prueba de que el sistema vencerá esas pérdidas. El presupuesto usa el tramo **en planta** hasta la toma más el espesor de muro: NO incluye ductos posteriores/compartidos, rejillas reales, encuentros, sección libre, codos colocados, curva presión–caudal de catálogo, rendimiento, ruido o efecto de la instalación. Los coeficientes dados **no se deducen** del plano, del caudal real ni de la ficha de un equipo.

Como escenario fijo **a Q objetivo**, no se resuelve la intersección entre curva de ventilador y curva de sistema (que además no existen para un equipo instalado). Que la desigualdad pase **no acredita ventilación**. El motor rederiva el presupuesto desde geometría, objetivo y ruleset actual y coteja todos los intermedios y supuestos antes de evaluar, seleccionar o exportar. Se rechazan mutaciones posteriores, cálculos ausentes en un baño o sobrantes en otros locales. `infeasible` significa solo que **ninguna variante de esta búsqueda** supera los supuestos; no imposibilidad universal.

## 3. Estados, salida y trazabilidad

- Por baño: `bath_pressure.status: "hypothetical_pressure_screen_only"`, `bath_pressure.delivered_flow_status: "not_evaluated"`. Incluye `fan_reference` (dos puntos y capacidad lineal interpolada), `assumptions` (densidad, Darcy, codos, K, reserva), `pressure_budget` (objetivo, longitud/diámetro hidráulico y presiones supuestos). Los demás locales: `bath_pressure: null`.
- Por alternativa: `bathroom_pressure_status: "hypothetical_pressure_screen_only"`. Se mantienen `bathroom_exhaust_status: "geometry_reserved_only"`, `bathroom_airflow_status: "nominal_precheck_only"`, `bathroom_ventilation_status` y `room.ventilation_status` de baños en **`"not_evaluated"`**. No existe un `delivered_flow_m3h`.
- Trazabilidad: decisión `generic_house_demo.bath_pressure@0.6.0` **por baño**, con intermedios y limitaciones. Interfaz: objetivo nominal y pantalla de presión separados, siempre «hipotética» y «capacidad de referencia». SVG: plano sin conducto 3D y marca **«PRESIÓN SUPUESTA · CAUDAL ENTREGADO NO EVALUADO · NO APTO PARA OBRA»**. Solo `ok` tiene planos; `error` e `infeasible` devuelven `alternatives: []`, y la CLI no escribe SVG nuevo en esos casos.

`engine_version = "mvp0.5-rust-0.6.0"`, reglas demo `version = "0.6.0"`, paquetes Rust/web `0.6.0`; cambian hash y preferencias anteriores. El ejemplo de semilla 42 mantiene tres alternativas; en la primera **94,9 m² brutos = 82,8 útiles + 12,1 muros/vanos**. Cada baño de esa alternativa presenta **68,1 m³/h objetivo**, un presupuesto **hipotético** ≈ **21,8 Pa** y una capacidad **lineal de referencia** ≈ **109,1 m³/h**. **Ninguno de esos números es el caudal realmente entregado.**

Pruebas Rust recomputan desde el JSON las fórmulas de geometría, caudal, presupuesto e interpolación; incluyen reglas inválidas/incoherentes, límites imposibles, mutaciones de cada campo, ausencia de SVG y matriz de escenarios. Tests WASM prueban las mismas cuentas, estados y paridad **byte a byte CLI/WASM** en entradas viables, inviables e inválidas. Reproducir desde raíz: `cargo fmt --all -- --check`, `cargo test --offline --workspace`, `npm run build --prefix web`, `npm test --prefix web`.

## 4. Para evaluar ventilación real

Faltan equipo identificado y ensayado con curva verificable, conductos y accesorios instalables en **3D**, pérdidas de presión derivadas del trazado y del caudal, cálculo de punto de operación, aire de reposición real, descarga segura, requisitos legales con fuente/jurisdicción, puesta en marcha y **medición de caudal entregado**. Mientras tanto, ventilación permanece **`not_evaluated`**. Tauri/SQLite, varias plantas, parcela irregular y reglas normativas certificadas siguen pendientes.

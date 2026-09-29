# Revisión técnica de ARQ GEN v3.0

**Fecha:** 25 de septiembre de 2026

**Fuente:** [`ARQ GEN TAURI.txt`](ARQ%20GEN%20TAURI.txt) (especificación maestra y contratos anexos). Las referencias `:inicio–fin` indican líneas de este archivo.

**Alcance:** revisión estática de coherencia, implementabilidad y riesgos del MVP. Al realizar la revisión, el repositorio todavía no contenía código ni archivos YAML ejecutables; el estado actual del primer corte se describe en [`README.md`](README.md) y sus contratos correctivos en [`docs/CONTRATO_MVP0.md`](docs/CONTRATO_MVP0.md). No es una auditoría de la normativa cubana ni una prueba de rendimiento.

## Dictamen

La visión es clara: un generador arquitectónico offline, explicable y supervisado por un profesional. Sin embargo, **la especificación aún no es un contrato único y seguro para implementar el MVP tal como se promete**. Las prioridades son (1) impedir que se aprueben planos con restricciones duras incumplidas, (2) fijar un alcance geométrico realizable y (3) unificar el modelo de áreas, instancias y circulación. Los fragmentos Rust/YAML deben leerse hoy como *pseudocódigo*, no como interfaces compilables.

**Estado de los cortes (25-09-2026):** P0-1 a P0-6 se delimitaron para **MVP-0** mediante su contrato correctivo: una planta rectangular, 0–3 alternativas sin violaciones geométricas detectadas, instancias únicas, corredor reservado y reglas ilustrativas. **MVP-0.1** añade franjas de muro, cómputo bruto/útil y vanos con barridos y jambas; véase [`docs/CONTRATO_MVP01.md`](docs/CONTRATO_MVP01.md). **MVP-0.2** añade huellas ilustrativas de muebles y aparatos, zonas libres y acceso interior comprobados; véase [`docs/CONTRATO_MVP02.md`](docs/CONTRATO_MVP02.md). **MVP-0.3** reserva salidas y trazados de extracción de baños hacia fachada en planta, sin verificar caudal ni instalación; véase [`docs/CONTRATO_MVP03.md`](docs/CONTRATO_MVP03.md). **MVP-0.4** añade predimensionado nominal ilustrativo por baño: objetivo volumétrico de caudal comparado con referencia de ventilador en aire libre y velocidades/altura supuestas, **sin caudal entregado ni ventilación efectiva**; véase [`docs/CONTRATO_MVP04.md`](docs/CONTRATO_MVP04.md). **MVP-0.5** añade exclusivamente un presupuesto de presión **hipotético** (sección, longitud y pérdidas supuestas) contrastado con **dos puntos nominales sin equipo identificado** y sin extrapolar; no calcula caudal real; véase [`docs/CONTRATO_MVP05.md`](docs/CONTRATO_MVP05.md). Sigue habiendo un cliente web offline, preferencia local y trazabilidad. Esto **no cierra** los contratos originales de dos plantas, parcela irregular, YAML/DSL, normativa certificada, shell Tauri, ventilación legal/efectiva, mobiliario real/accesibilidad ni persistencia. Para comandos y límites reales, véase el `README.md`.

## Hallazgos bloqueantes — P0

### P0-1. Es posible seleccionar y presentar candidatos inválidos

**Evidencia:** la reparación acepta resultados parciales por defecto (`ARQ GEN TAURI.txt:2225–2228`); `Partial` y `Success` reciben el mismo estado `Repaired`, y luego todos pasan a `Evaluated` (`:2311–2327`). El filtro de selección solo comprueba que exista `score`, no que no haya infracciones (`:2455–2467`); el vector de Pareto omite `rule_violations` (`:2787–2790`, `:3044–3059`). Además, `frontier[0]` y `unwrap()` fallan si hay menos de tres candidatos en el frente (`:2465–2475`), mientras la salida exige `[Uuid; 3]` (`:1545–1551`). Tres candidatos viables tampoco implican tres no dominados.

**Riesgo:** una propuesta con fallo de evacuación, acceso o área mínima puede aparecer como alternativa aprobable; los encargos imposibles pueden terminar en un fallo de ejecución.

**Resolver:** separar explícitamente `feasible / hard_invalid / soft_warning`; validar geometría, programa y reglas duras antes de Pareto y de la aprobación. Devolver `Result` con diagnóstico de inviabilidad y permitir 0–2 alternativas justificadas cuando no haya tres seguras. Añadir pruebas para cero candidatos, frente de tamaño uno, reparación parcial y violación normativa con buen score.

### P0-2. El alcance de «dos plantas y parcela irregular» no tiene representación completa

**Evidencia:** el MVP declara 1–2 plantas y parcelas rectangulares o irregulares (`:131–141`), pero el contrato de layout recibe un solo `buildable_polygon` (`:1504–1537`) y `SpacePlacement` no tiene `level_id` (`:1584–1596`). Los retiros se describen como cuatro bordes (`:6127–6159`) y el cálculo devuelve un único polígono (`:6186–6209`). Hay pruebas para escaleras y varias plantas (`:3803–3808`) y láminas multipiso (`:4649–4652`), pero no un contrato de reparto por nivel ni de huecos de escalera. El criterio de cierre se reduce a parcela rectangular (`:1396–1398`).

**Resolver:** o bien definir **primer corte: vivienda de una planta en parcela rectangular** y posponer el resto con hitos propios, o añadir desde el inicio `LevelId`, envolvente/huella por nivel, escaleras y reservas verticales, acceso entre niveles, límites de área por planta, y geometría `MultiPolygon`/huecos para parcelas irregulares. No prometer ambos sin esos contratos y sus casos de prueba.

### P0-3. Edificabilidad y áreas confunden envolvente, huella y superficie construida

**Evidencia:** `compute_max_volume` usa `plot_area` sin recibirlo, calcula `max_floors = floor(max_built_area / max_footprint)` y deriva la **altura máxima** de la **altura mínima** de planta (`:6213–6228`). Por ejemplo, parcela de 100 m², huella permitida de 80 m² y FAR de 0,6: la fórmula devuelve **cero plantas**, aunque una vivienda de 60 m² en una planta sería posible. La zonificación reparte todo el polígono edificable (`:6856–6860`, `:7192–7210`), mientras sus proporciones provienen de la suma de áreas de locales (`:7038–7053`) sin presupuestar muros, circulaciones adicionales o patios; tampoco garantiza que la huella elegida respete `max_footprint`.

**Resolver:** distinguir parcela, envolvente legal, **huella elegida**, área útil, área de circulación, espesor de muros, área construida por nivel y área exterior. Exigir `footprint ≤ max_footprint` y `Σ built_area(level) ≤ max_built_area`, y limitar el número de plantas por reglas de altura y tipología; FAR no determina por sí solo el número máximo de plantas. Reservar superficies para muros y circulación antes de repartir locales. Documentar qué significa «120 m²» en la entrada y en la memoria.

### P0-4. `count` no equivale a instancias identificables de locales

**Evidencia:** `SpaceRequirement` agrupa `count` locales bajo un solo `id` (`:6431–6441`), pero el grafo crea un nodo por requisito (`:6734–6737`) y el layout coloca por `space.id` (`:1910–1917`, `:1943–1949`). Así, pedir tres dormitorios no define tres nodos, tres geometrías ni tres decisiones de colocación. La definición maestra de `SpaceRequirement` ni siquiera contiene `id` (`:652–660`).

**Resolver:** separar `SpaceRequirementGroup { type, count, ranges }` de `SpaceInstance { stable_id, type, level?, ... }`; expandir los grupos antes de construir el grafo, las zonas y el layout. Precisar la semántica de relaciones entre tipos («cada dormitorio conecta con un pasillo» frente a «al menos uno»). Probar con tres dormitorios y dos baños, además de referencias a instancias individuales.

### P0-5. La circulación se intenta crear cuando el espacio ya está ocupado

**Evidencia:** el pipeline coloca anclas, propaga y rellena antes de trazar circulación (`:2292–2305`). El grafo de accesibilidad solo crea aristas entre locales que comparten pared (`:3309–3349`), pero el paso siguiente incluye casos de locales **no adyacentes** y corredores que pasan entre ellos (`:3442–3460`). El trazado geométrico evita locales existentes (`:3465–3482`), sin reservar ancho o modificar el reparto previo; el MST no puede conectar nodos ausentes del grafo.

**Riesgo:** un plano completamente rellenado puede ser topológicamente conectable en abstracto pero imposible de recorrer con pasillos y puertas de anchura reglamentaria.

**Resolver:** reservar una red de circulación y conexiones exteriores durante zonificación/layout, o generar conjuntamente locales y corredores con retroceso geométrico. Recalcular áreas, colisiones y accesibilidad tras cualquier corredor o reparación. Diferenciar grafo funcional (deseos), grafo de accesibilidad potencial y grafo físico final; declarar inviabilidad cuando no exista camino.

### P0-6. «Verificación normativa» requiere una procedencia y cobertura que no están especificadas

**Evidencia:** se promete una sección de verificación normativa en la memoria (`:1130–1145`, `:4409–4465`), mientras el ejemplo de ruleset contiene números y fuentes genéricas sin artículo, ámbito municipal, condiciones de aplicación ni evidencia de validación (`:5350–5363`, `:5366–5391`, `:5413–5439`). Hay una fecha de vigencia ejemplificada, pero no un procedimiento de actualización o aprobación profesional del paquete de reglas.

**Resolver:** tratar los valores del documento como **ejemplos no certificados**. Definir por regla norma, artículo, edición, jurisdicción/localidad, vigencia, hipótesis y revisor; distinguir `verificado`, `no evaluado`, `no aplicable` y `fallido` en el informe. No presentar «cumplimiento normativo» completo ni expedir documentación para trámite hasta validar la cobertura con un arquitecto y fuentes jurídicas vigentes. Mantener explícita la revisión profesional.

## Riesgos importantes — P1

### P1-1. Hay varios contratos incompatibles para las mismas entidades

`EvaluationScore` aparece con `overall` y `circulation_ratio` en el modelo maestro (`:448–468`), luego con otras propiedades (`:994–1024`) y finalmente con `circulation_ratio_score` y doce criterios (`:2769–2797`). `ZonePlacement` se declara con `zone` (`:826–840`) y se construye con `kind` (`:1765–1778`). `Candidate.spaces` es `Vec<SpacePlacement>` (`:1554–1565`), pero otros ejemplos iteran sobre él como si fuera un mapa (`:2483–2496`, `:3318–3334`). El contrato de regeneración usa `functional_graph` y `pinned_positions` en `LayoutInput` sin declararlos ahí (`:1504–1537`, `:7964–8009`).

**Resolver:** publicar un único esquema canónico de entidades/DTO y errores (Rust tipado + serialización versionada), y convertir ejemplos a pruebas de compilación o marcarlos inequívocamente como pseudocódigo. Cambios a contratos deben actualizar todos los consumidores.

### P1-2. Los «schemas» YAML y el DSL todavía no son validables como se describe

`_schema.yaml` contiene marcadores como `id: string` y `min: number`, que son un **ejemplo de forma**, no un JSON Schema (`:4756–4785`); el cargador espera un `JsonSchema` (`:5605–5633`). Se pide ID en *kebab-case*, pero los ejemplos usan `single_family_house` y `bedroom_master` (`:4673–4683`, `:5063–5072`). El ruleset repite la clave `version` (`:5283–5295`, `:5352–5364`). Para cuatro dormitorios coinciden dos reglas de cantidad de baños (`:5074–5082`); `then` usa texto libre sin una semántica formal de precedencia (`:6566–6588`).

**Resolver:** crear schemas reales empaquetados localmente (URI como identificador, sin acceso a internet), definir IDs y versiones de esquema/contenido por separado, AST tipado para condiciones/consecuencias y política de conflictos/prioridades. Probar que todos los ejemplos del MVP cargan, que sus referencias cruzadas existen y que duplicados de claves se rechazan.

### P1-3. Reproducibilidad y caché no abarcan todas las dependencias

Se afirma que semilla + entrada reproducen candidatos (`:2503–2517`) y que el `EvaluationScore` es idéntico byte a byte (`:3145–3152`), pero hay `Uuid::new_v4()` (`:7128–7132`, `:3570–3578`) y campos de fecha (`:2792–2796`, `:7241–7251`). La evaluación depende de programa, sitio, tipología, DNA, reglas y pesos (`:2751–2764`), mientras el hash de caché solo cubre el candidato (`:3152`). La recarga de YAML aplica archivos uno a uno y permite éxitos parciales (`:5702–5734`).

**Resolver:** generar IDs estables por ejecución, separar timestamps de auditoría de los datos comparados, fijar snapshot/hash de **todas** las dependencias y versión del motor por sesión, e invalidar cachés por ese hash. Validar el grafo completo de conocimiento y sustituirlo atómicamente; una generación activa no debe cambiar de ruleset a mitad de proceso. Distinguir objetivo de tiempo de corte por reloj (que compromete reproducibilidad).

### P1-4. Las fases retrasan dependencias y mezclan dos definiciones de «terminado»

Las fases 01–18 llaman «generador funcional» al corte, pero el registro de decisiones llega en la fase 31 y el sidecar Python requerido por la arquitectura, en la 36 (`:1285–1332`); el criterio de «núcleo terminado» también exige documentación, aprobación, trazabilidad y uso offline (`:1396–1418`). Además, «nada se ejecuta sin aprobación» (`:1090–1107`) es incompatible literalmente con generar centenares de mutaciones automáticas antes de presentar alternativas.

**Resolver:** diferenciar **núcleo experimental** (CLI, datos, validación y traza mínima) de **MVP de producto** (UI, aprobación, exportación). Llevar decisiones/trace al pipeline desde el primer candidato. Decidir si las reglas iniciales se ejecutan en Rust hasta introducir Python o adelantar el sidecar. La aprobación humana debe aplicarse a cambios persistidos, ajustes del encargo y emisión de documentación; la exploración interna puede proponer sin pedir permiso por cada mutación.

### P1-5. Algunos algoritmos ejemplificados rompen invariantes básicas

`fill_remaining` puede elegir el **mismo local** para varios huecos, porque no lo quita de `remaining` (`:2015–2041`); la propagación busca franjas respecto a la zona, sin descontar todos los locales colocados (`:1909–1954`). `generate_zoning` hace `unwrap()` si no hay esquemas (`:6995–7031`) y `compute_zone_proportions` divide por cero si no hay área (`:7038–7053`). Las reglas de programa pueden producir mínimos/máximos contradictorios al unificar (`:6592–6613`).

**Resolver:** especificar pre/postcondiciones geométricas y de unicidad, errores de dominio para entradas inviables y pruebas de propiedades: interiores disjuntos, unión dentro de huella, suma de áreas coherente, instancias únicas y cero panics con entradas vacías/degradadas. No convertir estos fragmentos directamente en código de producción.

## Decisiones recomendadas antes del primer módulo

1. **Cerrar el alcance del primer caso vertical:** una planta rectangular, programa explícito y ruleset genérico *no certificado*, o financiar los contratos multipiso e irregular de verdad.
2. **Publicar invariantes y contratos canónicos:** superficies útiles/construidas, IDs por instancia, estados de candidato, errores de inviabilidad y frontera de aprobación.
3. **Entregar un fixture completo y verificable:** parcela con norte/acceso, programa de tres dormitorios, YAML válidos, reglas con procedencia, áreas esperadas y casos imposibles.
4. **Construir una prueba end-to-end pequeña antes de optimizar:** sitio → programa → huella/zones → locales + circulación → validación dura → 0–3 alternativas → decisión trazable. Añadir documentación solo sobre una alternativa validada.
5. **Definir la salida de calidad:** tres propuestas es un objetivo de presentación, nunca motivo para inventar propuestas inválidas. Medir tiempos en el hardware objetivo solo después de fijar las invariantes.

**Orden de corrección sugerido:** P0-1/P0-6 (seguridad de salidas), P0-2/P0-3 (alcance y áreas), P0-4/P0-5 (modelo y geometría), P1-1/P1-2 (contratos/datos), P1-3/P1-4 (reproducibilidad y plan), P1-5 (algoritmos y pruebas).

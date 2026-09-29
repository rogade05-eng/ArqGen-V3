# Contrato correctivo — MVP-0.15: franja frontal recta sobre un croquis, NO acceso certificado

**Estado:** implementado el 2026-09-26, después del [MVP-0.14](CONTRATO_MVP14.md). Motor `mvp0.15-rust-0.12.0`, web/shell experimental `0.16.0`, ruleset demo **sin cambios** `generic_house_demo@0.8.0`. El objetivo de producto sigue siendo el [producto maestro completo para Cuba](ESTADO_PRODUCTO.md); esto **no** es una regla cubana, un análisis vial ni una prueba de accesibilidad.

## Problema acotado

Una reserva voluntaria podía estar por delante de la vivienda y **no tocar su huella**, pero tapar el único acceso recto desde el borde frontal dibujado hasta la puerta centrada. Afirmar que ese plano tiene entrada exterior sería improcedente. Este corte comprueba **solo una franja rectangular recta 2D, centrada en el vano principal, desde `y=0` hasta el paramento exterior de la vivienda (`y=rules.setbacks.front`)**. El borde frontal continuo **se supone** hacia un exterior desconocido; no se ha comprobado que exista calle, conexión con ella, autorización para cruzarla o transición entre cotas. No se buscan desvíos ni varios accesos. Una franja que no cabe implica **`infeasible` solo en esta búsqueda**: puede haber otro diseño o un rodeo que el generador no explora.

## Entrada, salida y rechazo

- Esquema obligatorio `request_schema: "arqgen-brief-v5"`. Conservar `site.plot_outline` y `site.reserved_areas` tal como en v4; añadir:

```json
"front_approach": {
  "provenance": "user_sketch_unverified",
  "shape": "straight_front_strip",
  "width": 1.2
}
```

  `width` es **anchura dibujada**, no paso libre construido ni umbral normativo: se acepta de 0,90 m a `min(6 m, site.width)` y debe cubrir al menos el vano principal **del mismo ruleset ilustrativo** (`rules.doors.main`). No se introduce un umbral de accesibilidad. Se rechazan claves extra, procedencia que alegue levantamiento/servidumbre, otro trazado, ancho no numérico, degenerado o incompatible; `error` no emite croquis de acceso validado. El formulario informa estos límites, pero **Rust valida** el JSON de CLI/WASM.
- Respuesta `ok` o `infeasible`: `site_approach` devuelve procedencia, forma, anchura y `geometry_status: "straight_front_strip_sketch_2d_only"`. Los tres estados `street_connection_status`, `right_of_way_status` y `accessibility_status` son **`not_evaluated` en todos los casos**. Este eco expresa el *supuesto de entrada*, NO que la franja sea transitable. Solo una alternativa `ok` incluye `alternative.front_approach`, con rectángulo `strip` y dos contactos (`front_contact` y `door_contact`) y `geometry_status: "strip_clear_of_declared_exclusions_2d_only"`. No es una validación de viabilidad real, constructibilidad ni norma. Si `rules.setbacks.front=0`, la puerta toca el borde frontal del dibujo: `strip:null`, `geometry_status: "door_at_front_boundary_2d_only"`. **No se inventa un rectángulo de altura cero ni se presume calle.**
- La revalidación de **cada candidato** comprueba que toda la franja quede dentro del contorno voluntario y **no interseque en área positiva** el recorte posterior ni la reserva voluntaria. Se admite contacto exacto de bordes; una invasión diminuta también se rechaza. Además se revalida la puerta contra el corredor y el muro frontal del plano. El área de la franja es **exterior y no construido**: no se añade ni resta a huella, FAR, `site.unreserved_buildable_area` o cobertura. Los histogramas siguen registrando el **primer** motivo de rechazo por variante; otras incompatibilidades pueden aparecer antes. Si ninguna propuesta sobrevive, no hay alternativa ni SVG/ficha exportable; la CLI no escribe un SVG solicitado.
- Para la muestra de **18×22 m**, sin recorte/reserva y con retiro frontal demo de **3 m**, la franja de **1,2×3 m** va de `x=8,4` a `x=9,6` y termina en el vano centrado en `x=9`; los 48 ensayos y tres alternativas previos permanecen. Una reserva **x=8,5, y=1, 1×1 m** queda fuera de la huella de vivienda pero cruza la franja: 48/48 descartes, `infeasible`. Mover esa reserva a `x=9,6` **toca** el borde y vuelve a permitir la búsqueda. Ampliar la franja puede bloquear un encargo antes compatible. Una L profunda que corta esta traza también impide una alternativa; no significa inviabilidad de la parcela real.

## Interfaz, fuentes, archivo y límites

- Web: entrada obligatoria para anchura dibujada, franja diferenciada en el SVG/leyenda/panel, aviso en inviabilidad, decisión trazable y TXT que **niega** conexión vial/derecho de paso/accesibilidad. Nunca se dibuja un recorrido exterior si no pasó Rust. No hay ensayo de pendientes, escalones, barreras, cerramiento/portón, estacionamiento, drenaje, señalización, seguridad, carga ni iluminación exterior. El supuesto de frente no otorga *frente legal*.
- La franja forma parte del **encargo y del `input_hash`**, no de las tres hipótesis matemáticas del ventilador. Cambiarla limpia el cuaderno de comparaciones. JSON individual sigue `{input,generation,selection}`; comparativa `arqgen-illustrative-comparison-v5` y copia local optativa `arqgen-local-workspace-v5`. Al importar/reabrir se **regenera todo** con Rust/WASM actual y se compara la respuesta antes de mostrar planos. Esquemas y archivos v1–v4 se rechazan explícitamente sin migración automática; una preferencia no se eleva a aprobación.
- Fuentes Cuba: las **12 copias PDF inventariadas** (en `main` remoto) y las vistas aportadas de **NC 337, NC 391-1 y NC 391-2** no aportan ninguna dimensión o derecho de paso ejecutable. `applicability`, iluminación y ventilación efectiva permanecen `not_evaluated`; la ubicación o necesidades autodeclaradas no convierten la franja en accesible.
- QA: casos de franja libre, obstruida fuera de la huella, borde compartido/sub-EPS, anchura variable, recorte en L, cero retiro frontal, JSON malicioso, cambio posterior de reserva sobre una planta ya generada, CLI sin SVG, eco/adulteración/archivo/replay/copia/TXT y paridad byte a byte CLI↔WASM. El [estado](ESTADO_PRODUCTO.md) registra resultados y limitaciones del entorno.

**Pendiente:** levantamiento y linderos, calle y conexión real, derecho/servidumbre de paso, accesos acodados, alturas, escaleras, pendientes, gálibo exterior, accesibilidad y reglas cubanas oficiales cotejadas por profesional; también luz/ventilación medibles, fichas/curvas de extractores y QA nativo Windows/WebView2. **NO apto para obra ni producto maestro terminado.**

# Contrato correctivo — MVP-0.11: contexto declarado y entrada versionada

**Estado:** implementado y comprobado el 2026-09-26. Amplía [MVP-0.10](CONTRATO_MVP10.md). Núcleo Rust `0.8.0`, `engine_version: "mvp0.11-rust-0.8.0"`, web/shell experimental `0.12.0`; ruleset **ilustrativo** `generic_house_demo@0.7.0` sin nuevos umbrales. Cuba es el objetivo del producto, **no** la ubicación asumida de cada proyecto. Este corte recopila datos **autodeclarados y no comprobados** para un estudio posterior: no determina la aplicabilidad legal de NC 598 ni evalúa cumplimiento, iluminación natural, accesibilidad o ventilación efectiva.

## Entrada Rust, CLI y WASM

La entrada **validada por Rust** tiene exactamente `request_schema`, `site`, `program`, `project_context`, `seed` y `rules` como claves raíz. El siguiente ejemplo es el **archivo de encargo CLI**, que omite `rules` porque la CLI lo recibe por `--rules` y adjunta el objeto completo antes de validar. La web sí adjunta el ruleset demo completo y solo permite variar tres hipótesis de presión:

```json
{
  "request_schema": "arqgen-brief-v2",
  "site": { "width": 18, "depth": 22, "front_orientation": "S" },
  "program": { "bedrooms": 3, "bathrooms": 2, "target_built_area": 95 },
  "project_context": {
    "jurisdiction": "unreported",
    "housing_class": "unreported",
    "occupants": null,
    "accessibility_needs": "unreported",
    "provenance": "self_reported_unverified"
  },
  "seed": 42
}
```

| Campo del contexto | Valores admitidos | Alcance |
| --- | --- | --- |
| `jurisdiction` | `unreported`, `CU`, `outside_CU` | Lugar **declarado**, no geolocalizado ni comprobado; `outside_CU` no constituye dictamen de exención. |
| `housing_class` | `unreported`, `urban_social`, `other` | Clasificación **declarada** de la vivienda, no constatada por documentación. |
| `occupants` | `null` o entero **1–20** | Dato opcional. El rango es un **límite de captura del prototipo, no un umbral normativo**; no altera programa ni cuantía de aparatos. |
| `accessibility_needs` | `unreported`, `declared`, `none_declared` | Necesidades comunicadas por el solicitante; `none_declared` **no** significa conformidad ni ausencia de obligaciones de accesibilidad. |
| `provenance` | solo `self_reported_unverified` | Marca que el registro de formulario/archivo **no equivale a evidencia externa**; aun si todos los campos están llenos, ninguna declaración está verificada. |

Todos los campos, incluidos `null` y el discriminador de esquema, son **obligatorios como claves**. Rust rechaza claves desconocidas, valores fuera de dominio, ocupantes fraccionarios/fuera del límite, procedencia falsificada, reglas con pretensiones normativas y entradas sin versión; jamás rellena el contexto faltante con «Cuba». Los valores iniciales del formulario son `unreported`/`null`. No hay tratamiento de datos personales nominales: **no introducir nombres o secretos** en campos/exportaciones.

## Salida sin conclusión normativa

En `status: "ok"` **y** `"infeasible"` el resultado devuelve `request_schema`, una copia tipada de `project_context` y un objeto `applicability` derivado por Rust:

```json
{
  "status": "not_evaluated",
  "declared_scope": "undetermined",
  "missing_context": ["jurisdiction", "housing_class", "occupants", "accessibility_needs"],
  "source_status": "no_verified_cuban_ruleset",
  "daylight_status": "not_evaluated",
  "ventilation_status": "not_evaluated"
}
```

Solo cuando se **declaran** conjuntamente `jurisdiction: "CU"` y `housing_class: "urban_social"`, `declared_scope` pasa a `candidate_from_self_report_only`: **candidatura para estudiar**, no prueba de ámbito legal. En cualquier otro caso queda `undetermined`, **nunca** `not_applicable`. `missing_context` enumera los datos no declarados; una lista vacía no cambia `status: "not_evaluated"`. No hay camino desde un enlace Scribd, una ventana dibujada o el estado «sin necesidades declaradas» a `verified`, `complies`, `failed` o una exención. `error` no ecoa contexto de una entrada inválida. La propiedad histórica `regulatory_status: "illustrative_not_certified"` sigue presente **solo** en `ok`; el resto de trazas, geometría y cribado nominal/hipotético conservan sus limitaciones.

El panel, el aviso de inviabilidad y la ficha TXT presentan **el contexto que devolvió Rust**, tras contrastarlo con la entrada y sus estados. Cuenta vanos de baño solo en una alternativa válida; un hueco dibujado **no** comprueba luz natural efectiva. La copia SHA-256 de NC 598:2009 y las tres pistas Scribd continúan en un inventario bibliográfico **no ejecutable**, fuera del ruleset y del hash. La lectura de fuentes no solicita contenido externo durante la generación.

`input_hash` cubre la entrada canónica **incluido este contexto**, snapshot de reglas y versión del motor; no es firma criptográfica. Cambiar cualquiera de los cuatro datos autodeclarados altera el hash, sin que ello por sí solo modifique los cálculos de planta. Los IDs/exportaciones de la versión anterior cambian deliberadamente.

## Archivos y compatibilidad explícita

- Corrida individual: `{input, generation, selection}` con `input.request_schema: "arqgen-brief-v2"` y salida del motor `0.8.0`. Una preferencia importada **no** autoriza nada.
- Comparativa: `format: "arqgen-illustrative-comparison-v2"`; de 2–3 corridas. Solo pueden diferir los tres parámetros web de `rules.bath_pressure`; **ubicación, clase, ocupantes, necesidades, parcela, programa, semilla y reglas fijas deben coincidir**. Cambiar el contexto en el formulario invalida la corrida y limpia el cuaderno.
- Copia opcional IndexedDB: `format: "arqgen-local-workspace-v2"` en la ranura actual. Al reabrir, cada escenario se **regenera en el WASM local y se compara íntegramente** antes de tocar la UI. No se hace autosave ni constituye respaldo: descargar JSON sigue siendo aconsejable.
- Archivos antiguos sin `request_schema`, comparativas `-v1` y copias `-v1` se **rechazan con mensaje explícito, sin migración silenciosa ni renderizar planos guardados**. La copia local vieja permanece disponible para borrar; si se necesita recuperar su contenido hay que usar la versión original del software. Al cambiar el WASM, ninguna generación previa se atribuye al motor actual.

## Evidencia y siguientes puertas

Con Rust 1.88 y `wasm32-unknown-unknown` temporales, aislados de credenciales: el build previo de la misma fuente reprodujo el WASM anterior **byte a byte** antes de modificarla; después se ejecutaron **39/39 pruebas Rust**, **29/29 pruebas web** (incluida paridad CLI/WASM con contexto, inviabilidad y entradas inválidas) y el build íntegro Rust → WASM → Vite → shell offline. El WASM compilado coincide por SHA-256 con `web/public/core.wasm` y el distribuido en el build (`253e6712d6fb1754066991661d6832ce31ee7d264c634c0e5bb206973b78a2ee`). El compilador se reconstruyó temporalmente a partir de componentes de npm de un **empaquetador tercero** y no forma parte de la distribución. No se han ejecutado ensayos nativos de Tauri/Windows ni una nueva prueba E2E de navegador en este corte.

Pendiente antes de cualquier regla cubana: edición/vigencia oficial, licencias y ámbito contrastados por profesional, dependencias NC 337/391 resueltas, fuente y cláusula por regla, datos de sitio comprobables, pruebas adversas de luz natural y accesibilidad. Pendiente antes de afirmar ventilación: equipo identificado, curva verificable, red tridimensional instalable, aire de reposición y medición/puesta en marcha. [Estado frente al producto maestro](ESTADO_PRODUCTO.md).

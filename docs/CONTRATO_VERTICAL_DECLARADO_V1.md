# Cotas Z declaradas para L0 de vivienda · contrato v1

**Estado: integrado y probado en Rust nativo, `core.wasm` y web experimental 0.22.** Es un modelo **de datos**, independiente de la generación v8 y del ZIP SVG A3 v2. Solo **una planta de vivienda unifamiliar**; no presenta un alzado inventado como plano verificable. **NO APTO PARA OBRA.** No es diseño arquitectónico completo ni acredita normativa cubana.

## Qué se calcula y qué NO

La solicitud contiene el encargo **v8 completo y snapshot de reglas**, el `candidate_id` de una de sus alternativas publicadas y una declaración de alturas. Rust **vuelve a generar el v8** y busca ese ID exacto: nunca acepta coordenadas de una supuesta candidata suministrada por el cliente. Para la planta `L0` vincula el rectángulo 2D original de la puerta y de **cada ventana existente** a cotas Z inferior/superior:

- Piso `floor_z_m` y coronación `wall_top_z_m`: **cotas locales supuestas**, no niveles levantados del terreno ni rasante.
- Cabeza de entrada `entry_head_above_floor_m` y alféizar **por local con ventana** `window_sill_above_floor_m`: hipótesis **explícitas**, no inferidas por el programa. La puerta arranca en el piso.
- Altura nominal de cada ventana: procede de la **regla demo v8** del candidato. `top_z_m = floor_z_m + sill + window.height`. No demuestra luz natural, ventana instalada ni altura medida.
- `plan_opening_v8` conserva sin transformación el rectángulo de planta Rust; **no es un polígono de fachada**, ni vano constructivo 3D. Las sumas Z se serializan sin ruido flotante menor que 10⁻⁹ m: esto NO atribuye precisión topográfica.

El modelo devuelve **exactamente un nivel** y `roof`, `vertical_connections`, `sections` y `facades` como **`null` (no modelados)**. No hay forjados, suelo/terreno, alturas libres normativas, interferencias 3D, cubiertas, escaleras, otros pisos, alzados ni cortes. **Hospital y hotel siguen siendo tipos de edificio generables futuros** que requieren programa y geometría propios; este contrato los **rechaza**, no los degrada a vivienda.

## Solicitud, respuesta y archivo

[Solicitud completa](../examples/declared-vertical-v1-request.json) · [modelo reproducido](../examples/declared-vertical-v1-model.json) · **[archivo web descargable/reabrible](../examples/declared-vertical-v1-archive.json)**. Los números del ejemplo son **hipótesis inventadas y rotuladas como tales**, no extraídos de fotografías, planos oficiales ni mediciones. Resumen, NO un archivo ejecutable (usar la solicitud completa enlazada):

```json
{
  "format": "arqgen-declared-vertical-request-v1",
  "typology": "single_family_house",
  "input": { "request_schema": "arqgen-brief-v8", "...": "encargo y reglas demo completos" },
  "candidate_id": "cand-ab3376d8fef08f3b-22",
  "declared_vertical": {
    "datum": "assumed_local_datum_not_surveyed",
    "height_provenance": "illustrative_assumption_not_measured",
    "floor_z_m": 0,
    "wall_top_z_m": 3.1,
    "entry_head_above_floor_m": 2.15,
    "window_sill_above_floor_m": {
      "living-dining": 0.8, "kitchen": 0.95,
      "bedroom-1": 0.9, "bedroom-2": 0.9, "bedroom-3": 0.9,
      "bathroom-1": 1.4, "bathroom-2": 1.4
    }
  }
}
```

La respuesta `arqgen-declared-vertical-model-v1` conserva `source` (`request_schema`, `engine_version`, `input_hash`, `candidate_id`), `model_hash`, `levels[0]` (`level_id=L0`) y vanos con `bottom_z_m`, `top_z_m`, `height_source`, rectángulo 2D original. `model_hash` es FNV-1a 64 sobre JSON canónico **de la solicitud completa** prefijado por la versión del modelo; cambia si cambian las alturas y **no es firma criptográfica**. `input_hash` v8 permanece intacto si solo cambian las alturas.

El archivo web es **`{format:"arqgen-declared-vertical-archive-v1", request, model}`**, separado de `{input,generation,selection}` v8 y del ZIP de cuatro láminas. Sin la **solicitud** no se puede reproducir el modelo; solo se reabre después de replay íntegro `arq_vertical` en WASM y comparación de toda la salida. La importación exige que la corrida v8 y la **misma alternativa** ya estén abiertas en la UI: un archivo de otro candidato no sustituye un plano o proyecto vigente. Los datos Z no se guardan automáticamente en IndexedDB/cartera; al editar el encargo o cambiar de candidata se borran los campos/resultado y hay que verificar de nuevo. **El ZIP A3 sigue con `nivel-0-2d.json.level.elevation_m = null`**: las cotas no se añaden furtivamente a láminas previas.

La validación Rust falla **atómicamente** (`status: error`, `levels: []`, sin `source` ni `model_hash`) ante formato/tipo desconocido, encargo v8 inválido/inviable, ID no publicado, cotas no finitas/incoherentes, falta o sobra un alféizar por local o un vano que supera la coronación. El parser Rust de solicitudes rechaza claves duplicadas. Los límites locales (piso ±1000 m, muro entre 0,000001 y 100 m, entrada ≥0,000001 m dentro del muro) son controles **numéricos/de datos**, **no mínimos ni alturas normativas**; no se aceptan etiquetas que presenten hipótesis como medidas o certificadas. En web los campos empiezan **vacíos**: no se atribuye altura, alféizar ni nivel por defecto.

## Ejecutar y probar

Requisitos para compilar desde la raíz: Rust estable ≥1.88 con `wasm32-unknown-unknown` y Node compatible con Vite. El feature Rust `declared-vertical-v1` está activado **por defecto** en el crate 0.17; `arq_vertical` tiene ABI independiente. `arq_generate` y `arq_explore` mantienen formato/salida v8 anterior. El WASM compilado se distribuye en `web/public/core.wasm` (~413 KiB). Se puede usar sin recompilar mediante `npm ci --prefix web` y el servidor web; el build íntegro sí necesita el target WASM.

```bash
cargo fmt --all -- --check
cargo test --offline --locked --workspace
cargo run --offline --locked -p arqgen-core --bin arqgen-vertical -- \
  examples/declared-vertical-v1-request.json > vertical-model.json
npm ci --prefix web
npm test --prefix web
npm run build --prefix web
# QA navegador opcional: npm run preview --prefix web -- --host 0.0.0.0 --port 4173
# ARQGEN_CHROMIUM_PATH=/ruta/a/chromium npm run test:e2e --prefix web
```

**Uso web:** genera/selecciona una alternativa → despliega **«Cotas Z explícitas para esta planta»** → rellena piso/coronación/cabeza y **todos** los alféizares → **«Verificar cotas en Rust»** → consulta tabla de alturas y descarga JSON separado. **«Abrir JSON y verificar»** reproduce el archivo con Rust local; no toma un resultado importado por verdadero sin replay. La CLI escribe JSON solo para `ok`; errores a stderr y código 1.

**QA de este incremento:** Rust `85/85` pruebas (7 nuevas), web `89/89` (4 nuevas), y **5/5** E2E Chromium/Linux del bundle de producción, incluido formulario sin alturas predeterminadas, importación adulterada rechazada, cambio de candidata, ZIP A3 intacto y recarga/importación **sin red**. La salida del ejemplo CLI y WASM coincidió **byte a byte**; cuatro SHA-256 históricos de respuestas v8 permanecieron iguales, y el ZIP SVG v2 anterior conservó su SHA-256. `core.wasm` nuevo: SHA-256 `4d2cde571b6706b6beafa7f25bf9f1fa18dd90951cf3e4ceacea4dd6c0b7ed01`. Para QA local en este entorno se usaron Rust 1.88/target WASM empaquetados por **terceros** (`@rustbin`) y Chromium headless (`@sparticuz/chromium`), instalados **fuera de Git**; esto no certifica su cadena oficial de suministro ni equivale a QA nativo Windows/WebView2.

**Siguiente contrato que falta:** superficie de fachada verificable a partir del perímetro 2D + datos verticales + relaciones de muro/niveles y cubierta, con validación de intersecciones antes de crear alzados/cortes. Después: plantas y núcleos funcionales multiescala, programas específicos hotel/hospital, reglas aplicables y expediente revisado. No se marca ninguno como terminado aquí. El [paquete SVG v2](CONTRATO_LAMINAS_SVG_V2.md) sigue siendo **solo planta 2D**.

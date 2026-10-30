# ARQ GEN — FASE C: flujo generativo web sobre Tauri (v3.50.0)

La FASE A (v3.48.0) demostró el canal; la FASE B (v3.49.0) aceleró el
motor; la **FASE C ofrece el flujo generativo web**: la pestaña web genera
las formas del motor y exporta archivos reales. La interfaz clásica Tkinter
sigue disponible junto a la web. La web todavía no sustituye todas las
herramientas de la GUI clásica; vea los límites al final.

## Qué hay en la FASE C

| Pieza | Archivo | Qué hace |
|---|---|---|
| Sidecar RPC | `app/rpc_server.py` | 20 métodos JSON-RPC, incluidos vista, edición, historial e importación 3D |
| Sesión LRU | `app/rpc_server.py` | Los análisis íntegros viven en el sidecar (máx. 8, por id `an1…`); la web solo guarda el id |
| UI web | `src/index.html` + `app.css` + `app.js` | 7 vistas: Inicio · Programa · Contorno · Forma · Resultado · Exportar · Proyecto |
| Shell Tauri | `src-tauri/src/main.rs` | `rpc`, `motor_ruta` y **`carpeta_descargas`** (path resolver núcleo, sin plugins) |
| Pruebas | `tests/test_191_fase_c_ui_web.py` | 31 pruebas: contrato de las 6 formas, determinismo, sesión LRU, errores con `data`, exportación real, sidecar POR PROCESO, empaquetado |
| Selftest | checks 101–103 | Catálogo/radial por RPC · exportación real IFC+DXF+XLSX desde la sesión · compuestos aplicados y exportados |

## Las 6 formas de generar (pestaña Forma)

| Modo | Método RPC | Motor |
|---|---|---|
| Encaje simple | `generar_quick` / `generar_edificacion` | `ajustar()` con ajuste ideal/minimo/medio/estricto, patio y chaflanes |
| Radial | `generar_radial` | `plan_radial()` — sectores anulares con núcleo circular (el programa lleva vestíbulo/entrada) |
| Torre en Y | `generar_y` | `plan_y()` — núcleo + alas radiantes, largos desiguales opcionales |
| Hospital en X | `generar_x` | `plan_x()` — dos barras cruzadas, ángulo configurable |
| Multi-ala | `generar_zonas` | `ajustar_zonas()` — N contornos con rol, hubs al ala principal |
| Rejilla tipo | `generar_rejilla` | `repartir_rejilla()` — la unidad repetida en celdas con corredor central |

## Navegación y edición 3D

Tras generar, pulse **Mostrar vista 3D** en Resultado:

- Botón central arrastrado: orbitar. Mayús + central: desplazar.
- Rueda: acercar/alejar hacia el cursor. Derecho arrastrado: desplazar;
  clic derecho sin arrastrar: quitar la selección. Izquierdo: seleccionar.
- También están disponibles los botones de cámara, proyección, nivel y
  separación. Es una navegación inspirada en SketchUp, no una réplica completa.

Las caras se asocian al identificador real de la entidad; las plataformas
sintéticas no son seleccionables. El panel edita propiedades concretas de
muros, mobiliario, puertas/ventanas/vanos, locales, cubiertas, rampas,
barandillas, ascensores, parasoles, pieles y escaleras existentes. Solo se
editan los campos que muestra el panel. Seleccione una escalera o mueble y
arrástrelo con Mayús + botón izquierdo para moverlo en XY, tanto en proyección
ortográfica como en perspectiva. Ctrl + Mayús + izquierdo mueve su cota Z;
el panel también permite introducirla. El movimiento se confirma al soltar y
se conserva en la instantánea; para escaleras también se exporta a IFC.
Arrastrar cerca del horizonte o del plano de recorte se rechaza. El panel
permite borrar una escalera con confirmación; no borra otros elementos.

Para **añadir una escalera**, elija recta, L, U o caracol y pulse «Añadir al
nivel seleccionado» (con «Todos», usa el primer nivel). No reemplaza otras
escaleras. Se puede editar su posición, giro, tipología, ancho, desnivel,
contrahuella objetivo y huella; se regeneran la planta y los peldaños. Los
avisos de dimensionado se muestran en el panel. Si no encuentra un hueco de
escalera en el nivel, se coloca en el origen y hay que situarla manualmente.
La geometría es aproximada; el hueco, las conexiones y barandillas no se
recalculan. El panel comprueba prismas 3D de muebles, peldaños y mesetas
contra muros con sus vanos rectangulares y contra otros muebles y escaleras,
incluso en niveles distintos. Advierte si un vértice sale del recinto asociado.
Es una aproximación: no incluye estructura, instalaciones, superficies curvas
exactas ni espacios libres. La ausencia de avisos no garantiza seguridad ni
cumplimiento: revise colisiones, accesibilidad y normativa profesionalmente.

**Deshacer/Rehacer cambio 3D** actúa sobre las últimas 100 ediciones de
propiedades y creaciones o borrados de escaleras de la sesión, no sobre las operaciones
de la GUI clásica ni sobre ediciones anteriores a la apertura de un archivo.
Una edición nueva descarta el historial de rehacer. Ambos usan auditoría y
revisiones nuevas; el historial se pierde al cerrar la sesión.

Para continuar un proyecto, en **Proyecto** seleccione una instantánea
`ARQ_GEN_SNAPSHOT` (hasta 16 MiB) y pulse **Abrir en editor 3D**. Se crea
una copia temporal de sus entidades arquitectónicas; los cálculos y cantidades
no se restauran automáticamente. Al exportar, la instantánea conserva las
escaleras y permite volver a editarlas. DXF R2010/R12 y SVG incluyen su
contorno y huellas en planta; el IFC incluye `IfcStair` con peldaños y
mesetas aproximados, situado en su nivel. El IFC exportado por ARQ GEN incorpora
parámetros propios que permiten reimportar y editar esas escaleras. Otros IFC
sin dichos parámetros no se reconstruyen como escaleras editables y se avisa;
no incluye barandillas ni huecos de escalera.
Los demás tipos pueden tener cobertura diferente según el formato: conserve
siempre la instantánea JSON y revise los archivos producidos.

`vista_3d` mantiene un SQLite temporal por sesión y `editar_3d` actualiza
propiedades con revisión, auditoría e invalidación. Las ediciones se pierden
al salir/reiniciar el sidecar o al expirar la sesión LRU: exporte la
instantánea JSON antes. Las métricas y planta del resultado generado siguen
siendo las del análisis original, no un recálculo de las ediciones.

El modelo usa muros y mobiliario automáticos. Si se editó, la exportación
utiliza el mismo proyecto y exige **muros activados y mobiliario automático**;
no regenera silenciosamente otro modelo. Sin ediciones, las opciones de
exportación pueden producir un modelo diferente al de la vista.

## Exportar desde la web

`aplicar_exportar {id, carpeta, nombre_base, formatos, trazar_muros,
mobiliario, con_proyecto}`:

1. si no hay ediciones 3D, crea un proyecto temporal y aplica el plan;
   si las hay, reutiliza el proyecto editado de la sesión,
2. escribe los formatos pedidos con `ExportService.exportar_todo`
   (IFC · DXF · DXF_R12 · JSON · CSV · XLSX · SVG),
3. opcionalmente guarda `nombre_base_proyecto.json` (instantánea),
4. devuelve rutas y tamaños. El modelo de sesión se cierra al expirar o salir.

La carpeta se propone con el comando Tauri `carpeta_descargas`
(normalmente `C:\Users\<tú>\Downloads\ARQ_GEN`); también se puede
escribir cualquier ruta absoluta a mano.

## Cómo probar el canal sin la ventana Tauri

```bat
:: 1) el sidecar a mano (protocolo 1 línea = 1 petición)
python main.py rpc
-> {"jsonrpc":"2.0","id":1,"method":"catalogo","params":{}}

:: 2) las pruebas del flujo y del editor 3D
python -m unittest tests.test_191_fase_c_ui_web tests.test_193_vista_3d_web tests.test_194_edicion_3d_web tests.test_195_escaleras_editor_3d -v

:: 3) el selftest (103 checks)
python main.py selftest
```

## Cómo compilar la app de escritorio (Windows)

```bat
python -m PyInstaller --noconfirm --clean ARQ_GEN.spec   :: motor (dist\ARQ_GEN)
cargo install tauri-cli --version "^2" --locked             :: una vez
cargo tauri build                                        :: instalador NSIS + portable
```

En GitHub Actions el workflow «Compilar ARQ GEN Tauri (Windows)»
(`.github/workflows/compilar_tauri.yml`, todas las `uses:` pinned a SHA
completo por la política del repo) lo hace en la nube y publica
instalador + portable como artefactos.

## Contrato del canal (lo que la web consume)

- Petición: `{"jsonrpc":"2.0","id":1,"method":"...","params":{...}}`
  (1 línea UTF-8). Respuesta: 1 línea con `result` o `error`.
- Errores: `-32601` método desconocido · `-32602` parámetros/domain
  (con `data.codigo` tipo `ARQ-DDI-012` y `data.accion`) · `-32603`
  interno · `-32700` JSON inválido. El canal NUNCA muere.
- `generar_*` devuelve `{tipo, id, niveles, dentro_del_contorno,
  totales, reparto:[{nivel, pasillo{nombre,area_m2,rect,poligono?},
  pasillos[]?, escalera, patio, locales[{nombre,area_m2,flujo,poligono}],
  dentro}], chaflanes, avisos, metricas}`; los compuestos añaden
  `zonas:[{rol, area_m2, contorno, reparto, totales, avisos}]` y la
  rejilla `pasillo_central` + `contorno`.
- Determinismo: sin el campo `id`, la misma petición produce la misma
  respuesta byte a byte (vigilado por test_189 y test_191).

## Límites honestos de la FASE C/1

- La web cubre el flujo generativo, la vista previa 3D del resultado,
  la exportación y la edición de snapshots arquitectónicos. Un editor CAD completo,
  las disciplinas y el presupuesto se
  siguen manejando en la GUI clásica (`09_GUI.bat`) o por CLI.
- La compilación y una prueba de arranque del shell instalado deben
  verificarse en Windows; que los tests del canal Python pasen no demuestra
  por sí solo que el instalador o la ventana Tauri funcionen. El workflow
  de Tauri compila el shell y ejecuta la suite antes de publicar.
- La sesión LRU guarda 8 análisis; al expirar uno también se pierde su
  modelo 3D temporal y cualquier edición no exportada.

# ARQ GEN — FASE C: la UI web completa sobre Tauri (v3.50.0)

La FASE A (v3.48.0) demostró el canal; la FASE B (v3.49.0) aceleró el
motor; la **FASE C convierte el canal en la INTERFAZ COMPLETA**: la
pestaña web ya genera TODAS las formas del motor y exporta archivos
reales. El motor Python (63.255 líneas) y la GUI clásica Tkinter quedan
intactos: la web es la nueva cara, no un reemplazo destructivo.

## Qué hay en la FASE C

| Pieza | Archivo | Qué hace |
|---|---|---|
| Sidecar RPC v3.50 | `app/rpc_server.py` | 13 métodos JSON-RPC: los 5 de FASE A + `catalogo`, `generar_radial`, `generar_y`, `generar_x`, `generar_zonas`, `generar_rejilla`, `aplicar_exportar`, `proyecto_abrir` |
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

## Exportar desde la web

`aplicar_exportar {id, carpeta, nombre_base, formatos, trazar_muros,
mobiliario, con_proyecto}`:

1. crea un proyecto temporal headless (SQLite),
2. aplica el plan (`aplicar_plan` o `aplicar_zonas` si es compuesto),
3. escribe los formatos pedidos con `ExportService.exportar_todo`
   (IFC · DXF · DXF_R12 · JSON · CSV · XLSX · SVG),
4. guarda la instantánea `nombre_base_proyecto.json` (reabrible con
   `proyecto_abrir` o `ARQ_GEN import`),
5. devuelve rutas y tamaños y borra el proyecto temporal.

La carpeta se propone con el comando Tauri `carpeta_descargas`
(normalmente `C:\Users\<tú>\Downloads\ARQ_GEN`); también se puede
escribir cualquier ruta absoluta a mano.

## Cómo probar el canal sin la ventana Tauri

```bat
:: 1) el sidecar a mano (protocolo 1 línea = 1 petición)
python main.py rpc
-> {"jsonrpc":"2.0","id":1,"method":"catalogo","params":{}}

:: 2) la suite completa
python -m unittest discover -s tests -p "test_191*.py" -v

:: 3) el selftest (103 checks)
python main.py selftest
```

## Cómo compilar la app de escritorio (Windows)

```bat
python -m PyInstaller --noconfirm --clean ARQ_GEN.spec   :: motor (dist\ARQ_GEN)
cargo install tauri-cli --version 2 --locked             :: una vez
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

- La web cubre el FLUJO GENERATIVO completo + exportación + lectura de
  snapshots. El editor CAD del dibujo de entrada (boceto interactivo),
  el 3D, las disciplinas y el presupuesto se siguen manejando en la GUI
  clásica (`09_GUI.bat`) o por CLI — quedan para una FASE C/2.
- El shell Rust sigue sin compilarse en este sandbox (falta webkit2gtk);
  su primera compilación real ocurre en el runner de GitHub (como en
  FASE A). El canal Python sí está probado extremo a extremo por proceso.
- La sesión LRU guarda 8 análisis; si genera 9 formas distintas y quiere
  exportar la primera, vuélvala a generar antes de exportar.

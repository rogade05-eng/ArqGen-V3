# ARQ GEN — FASE A: Tauri 2 + Sidecar Python (arquitectura del «ARQ GEN TAURI.txt» v3.0)

Esta iteración entrega la FASE A aprobada: el **canal completo Tauri ↔ motor**
probado de extremo a extremo y el **esqueleto del shell**, sin tocar el motor
generativo (63.255 líneas y 2.598 pruebas intactas).

```
┌─────────────────────────────┐          ┌──────────────────────────────┐
│  Shell Tauri 2 (Rust)       │  invoke  │  Ventana web (WebView2)      │
│  src-tauri/src/main.rs      │◄────────►│  src/ (HTML+CSS+JS vanilla)  │
│  lanza / relanza el motor   │          │  quick-spec + plano SVG      │
└──────────────┬──────────────┘          └──────────────────────────────┘
               │ stdin/stdout: JSON-RPC 2.0 (1 línea por mensaje, UTF-8)
┌──────────────▼──────────────┐
│  Motor Python (sidecar)     │
│  ARQ_GEN.exe rpc            │
│  app/rpc_server.py          │
│  63.255 líneas, offline     │
└─────────────────────────────┘
```

## Ficheros de la FASE A

| Fichero | Qué es |
|---|---|
| `app/rpc_server.py` | Servidor JSON-RPC 2.0 del sidecar (nuevo, con suite `tests/test_189_rpc_sidecar.py`) |
| `main.py` + `app/cli.py` | Subcomando `rpc` que arranca el servidor LEAN (sin bootstrap del catálogo) |
| `src-tauri/` | Shell Tauri 2: `Cargo.toml`, `build.rs`, `tauri.conf.json`, `capabilities/`, `src/main.rs` |
| `src/` | Frontend de prueba (HTML/CSS/JS vanilla, **sin npm ni build**): estado del motor, quick-spec, contornos preset, chaflanes, plano SVG por nivel con la paleta de flujos |
| `.github/workflows/compilar_tauri.yml` | CI que compila instalador NSIS + zip portable con todo dentro |
| `selftest` check 97 | El selftest del ejecutable valida el canal RPC (ping, -32601, generar_quick con polígonos) |

## Contrato JSON-RPC (fuente de verdad)

Cada línea de stdin es una petición; cada línea de stdout es una respuesta.
`stderr` queda reservado para diagnóstico (el shell lo silencia).

```
-> {"jsonrpc":"2.0","id":1,"method":"ping","params":{}}
<- {"jsonrpc":"2.0","id":1,"result":{"pong":true,"app_version":"3.48.0"}}

-> {"jsonrpc":"2.0","id":2,"method":"generar_quick","params":{
     "texto":"dormitorio, bano, cocina, sala, patio",
     "contorno":[[0,0],[24,0],[24,12],[0,12]],
     "ajuste":"ideal","chaflanes":true}}
<- {"jsonrpc":"2.0","id":2,"result":{
     "niveles":1,"dentro_del_contorno":true,"sala_distribuidora":false,
     "totales":{"area_programa":57.5,...,"aprovechamiento_pct":47.92,...},
     "reparto":[{"nivel":1,"pasillo":{"nombre":...,"rect":[[x,y]...]},
                "escalera":null,"patio":null,
                "locales":[{"nombre":"Sala","area_m2":32.41,
                            "poligono":[[x,y]×5o6],...}]}],
     "chaflanes":[...],"avisos":[...],"circulacion":[...]}}
```

| Método | Params | Devuelve |
|---|---|---|
| `ping` | — | `{pong, app_version}` (latido para el chip de estado) |
| `version` | — | `{app_version, python, plataforma}` |
| `selftest` | — | `{ok, checks}` (los 97 checks; pesado) |
| `generar_quick` | `texto`, `contorno`, `ajuste`?, `chaflanes`? | planta resumida al contrato de la UI |
| `generar_edificacion` | `fichas[{space_type,cantidad}]`, `nombre`, `contorno`, ... | planta resumida |

Errores JSON-RPC completos: `-32700` JSON inválido · `-32600` petición mal
formada · `-32601` método desconocido · `-32602` params inválidos (contorno
corto, texto vacío, fichas ausentes) · `-32603` interno. **Un fallo no tumba
el canal**: el siguiente `ping` sigue respondiendo.

## Cómo resuelve Rust el binario del motor

Cadena de fallback en `ruta_motor()`:
1. `<resource_dir>/engine/ARQ_GEN.exe` — así lo empaqueta `tauri.conf.json`
   (`bundle.resources: {"../dist/ARQ_GEN/": "engine/"}`), tanto el instalador
   NSIS como el zip portable.
2. `<exe_dir>/engine/ARQ_GEN.exe` — modo portable.
3. `<exe_dir>/ARQ_GEN.exe` — modo acoplado, solo si el shell tiene otro nombre.
4. `<exe_dir>/dist/ARQ_GEN/ARQ_GEN.exe` — dist de desarrollo.
5. `ARQ_ENGINE_PATH` — escape manual.

En todos los casos se rechaza el propio shell (incluidos enlaces a él),
para evitar lanzarlo recursivamente si falta el sidecar. Si no se puede
identificar el ejecutable actual, se informa del error en vez de adivinar.

El proceso se lanza con `CREATE_NO_WINDOW` (sin consola parpadeante en
Windows) y nace perezoso en la primera invocación; si muere, el siguiente
comando lo relanza.

## Compilar en Windows (local)

```bat
:: 1) motor sidecar (igual que siempre)
python -m pip install -r requirements.txt -r requirements-build.txt
python -m PyInstaller --noconfirm --clean ARQ_GEN.spec

:: 2) shell Tauri (requiere Rust estable: rustup)
cargo install tauri-cli --version "^2" --locked
cargo tauri build
:: -> src-tauri\target\release\bundle\nsis\ARQ_GEN_3.48.0_x64-setup.exe
```

El canal también funciona SIN compilar nada (pruebas y depuración):
```bat
echo {"jsonrpc":"2.0","id":1,"method":"ping","params":{}} | python main.py rpc
```

## Compilar en la nube (GitHub Actions)

Pestaña **Actions → Compilar ARQ GEN Tauri (Windows) → Run workflow** (o push
de una etiqueta `v*`). El workflow: valida el canal con un ping real, compila
el sidecar con PyInstaller, le pasa el selftest completo, instala
`tauri-cli` y produce dos artefactos:
- **ARQ_GEN_Tauri_Installer** — instalador NSIS autocontenido.
- **ARQ_GEN_Tauri_Portable** — zip con `ARQ_GEN.exe` + `engine/`.

Por la política del repositorio (actions pinned a SHA completo), ambos
workflows usan SHAs fijados al remoto oficial: checkout `v4.4.0`,
setup-python `v5.6.0`, upload-artifact `v4.6.2`, download-artifact `v4.3.0`,
gh-release `v2.6.2`.

## Qué queda para FASE B (no empieza sin aprobación)

- Puertos selectivos del motor a Rust (geometría caliente), validados contra
  las mismas pruebas doradas.
- Exportadores en Rust (`rust_xlsxwriter`); el DXF/IFC sigue en el sidecar
  mientras `ezdxf` no tenga equivalente maduro en Rust.
- Persistencia SQLite (WAL) en el shell y UI completa por fases (el frontend
  de la FASE A es una pantalla de prueba, no reemplaza aún a la Tkinter).

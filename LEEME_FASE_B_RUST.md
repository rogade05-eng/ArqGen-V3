# ARQ GEN — FASE B: puertos selectivos a Rust (v3.49.0)

Esta iteración entrega la FASE B aprobada: las **piezas calientes del
motor corren ahora también en Rust**, sin tocar ni un resultado del
modo por defecto. Es la continuación natural de la FASE A (Tauri 2 +
sidecar): el crate que aquí nace como *acelerador de Python* es el
mismo núcleo que en el futuro shell Tauri se compila dentro del
binario Rust.

```
┌──────────────────────────────────────────────────────────┐
│  Motor Python (63.255 líneas, sidecar FASE A)            │
│                                                          │
│  domain/encaje.py ── switch usar_rust ──► core/acelerador│
│  exporters/xlsx_exporter.py ────────────►     │          │
└───────────────────────────────────────────────┼──────────┘
                    modo python (por defecto)   │ modo rust (opt-in)
┌───────────────────────────────────────────────▼──────────┐
│  arqgen_core (Rust + PyO3, rust/arqgen_core)             │
│  • geometría de encaje 1:1 (seccion_en, contenedores,    │
│    rectángulo inscrito, área, comparten_banda)           │
│  • escritor XLSX nativo (cabecera 2F5496, freeze A2)     │
└──────────────────────────────────────────────────────────┘
```

## Qué se portó y por qué

| Pieza | Original | Puerto Rust | Motivo |
|---|---|---|---|
| Geometría de encaje | `domain/encaje.py` | `arqgen_core` (seccion_en, contenedores_ortogonales, rectangulo_inscrito, area_poligono, comparten_banda, es_ortogonal) | `_seccion_en` se llama O(niveles² × 7) veces dentro del rectángulo inscrito: era el cuello de botella real del «Desde dibujo» con contornos ricos. **Medido: ~49× más rápido** (60 llamadas sobre contorno de 40 vértices: 1.245 ms → 25,7 ms) |
| Export XLSX | `exporters/xlsx_exporter.py` (openpyxl) | `arqgen_core.xlsx_escribir` (OOXML nativo con `zip`) | `rust_xlsxwriter` no existe como binding Python en PyPI; el equivalente funcional se escribió dentro del crate: mismo formato (cabecera azul 2F5496 con fuente blanca en negrita y centrada, pane congelado A2, anchos) y legible por openpyxl |

NO se portó (deliberadamente): el resto del motor (63.255 líneas),
la UI Tkinter, el sidecar RPC. El motor generativo queda intacto.

## Política de activación (opt-in)

- **Modo por defecto: PYTHON.** El determinismo del v3.48.0 no cambia;
  la suite completa corre sobre el camino clásico como siempre.
- **Activación:** variable de entorno `ARQ_GEN_ACELERADOR=rust` o
  parámetro `usar_rust=True` en `encaje.contenedores_de()` /
  `XLSXExporter.export()`.
- **Sin crate instalado nada se rompe:** el switch cae a Python sin
  explotar (vigiado por tests).
- Paridad Rust ↔ Python: `tests/test_190_fase_b_rust.py` (15 pruebas:
  piezas, nivel alto con estrategia/avisos, XLSX con formato) y
  checks 98-100 del selftest (100 checks en total).

## Cómo compilar el crate

Requisitos: Rust (rustup) y `pip install maturin`.

```bat
cd rust\arqgen_core
maturin build --release
pip install target\wheels\arqgen_core-3.49.0-*.whl
python -c "import arqgen_core; print(arqgen_core.version())"
```

En Linux/macOS el mismo comando produce la extensión de la plataforma.
El módulo instalado se llama `arqgen_core` y expone:

| Función | Firmas |
|---|---|
| `es_ortogonal(poligono, tol=None)` | bool |
| `seccion_en(poligono, y)` | [(x0,x1), ...] |
| `contenedores_ortogonales(poligono, margen=0.0, min_lado=1.0)` | dicts |
| `rectangulo_inscrito(poligono, margen=0.0)` | dict o None |
| `comparten_banda(a, b, min_len=1.0, tol=1e-6)` | bool |
| `area_poligono(poligono)` | float |
| `xlsx_escribir(ruta, hojas)` | nº celdas; hojas = [{titulo, headers, filas, anchos}] |
| `version()` | «3.49.0» |

## Reglas de paridad (por qué da lo mismo)

El puerto copia el algoritmo Python **línea a línea**: mismo orden de
operaciones, `round(x,4)` estilo Python (half-to-even, replicado en
`redondea4`), sort de contenedores por el área YA redondeada y estable,
`max(key=...)` que toma el primero máximo. La paridad se exige a 1e-9
en los tests; las únicas diferencias concebibles serían el último
dígito del redondeo a 4 decimales en midpoints decimales exactos
(caso que no aparece con geometría real y que el test vigila).

## CI (GitHub Actions)

`compilar.yml` ganó el paso **«Acelerador Rust FASE B (opcional)»**:
instala maturin, compila el wheel en el runner Windows y lo instala
antes de PyInstaller, de modo que **el exe compilado en la nube lleva
el acelerador dentro** cuando el toolchain coopera. El paso es
`continue-on-error`: si Rust falla, el run sigue en verde y el exe se
compila en modo Python puro (todo funciona; solo pierde la
aceleración). El resumen del run muestra el check 98 del selftest del
exe, que informa honestamente el modo.

Sin actions nuevas → la política SHA-pinning del repo sigue cumplida.

## Límites honestos

- El acelerador solo cubre encaje + XLSX; el resto del motor sigue en
  Python (era el objetivo de FASE B: puertos SELECTIVOS).
- El XLSX de Rust no soporta fórmulas, gráficos ni estilos por celda:
  lo que el exportador usaba (3 hojas, cabecera, freeze, anchos) sí.
- `comparten_banda` espera dicts con las 4 claves x0/y0/x1/y1.
- El ejecutable sin el crate es 100% funcional (modo python).

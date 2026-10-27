# modules/

Carpeta reservada por la especificación maestra (§4). Los módulos de dominio
se entregaron como plugins en `plugins/builtin` + servicios; esta carpeta
conserva el mapa de estado del plan maestro (§108 del spec).

## Estado completo del plan maestro (§108)

- **FASES 01–09 (v1.0.0)**: CORE, DATABASE, GEOMETRY, PROJECT MODEL,
  RULE ENGINE, GRAPH ENGINE, SPATIAL REASONING, ARCHITECTURE, DRAWING/DXF.
- **FASES 26, 28, 29 (v1.0.0)**: QTO, PRICING, BUDGET.
- **FASES 36–39, 42–43 (base v1.0.0, cierre v1.3.0)**: AUDIT
  (filtros/estadísticas/exportación), VERSIONING (compare/export/branch),
  BACKUP/RECOVERY (autosave, incremental, journal, verify, recover),
  PLUGIN SYSTEM (validate/info/new), PACKAGING (PyInstaller onedir) y
  FINAL QA (305 pruebas + selftest 23).
- **FASES 10–13 (v1.1.0)**: INSTALLATIONS CORE (§24-25), ROUTING (§26),
  ELECTRICAL (§27), SANITARY (§28), HVAC (§29).
- **FASES 14–16 (v1.2.0)**: STORMWATER (§30), GAS (§31), TELECOM (§32);
  comandos `plu`, `gas`, `tel`.
- **FASES 17 (v1.2.0)**: STRUCTURE (§33-34); comandos `struct`.
- **FASES 18–23 (v1.2.0)**: SECURITY (§37-49): FOV, CCTV, FIRE,
  INTRUSION, ACCESS, PERIMETER; comandos `sec`.
- **FASES 24–25 (v1.2.0)**: COORDINATION + CLASH (§35-36); comandos `clash`.
- **FASES 30–31 (v1.2.0)**: PRECONS + SIECONS-LIKE (§59-60);
  comandos `precons`.
- **FASES 32–33 (v1.2.0)**: BIM + IFC (§63-67); `export --format ifc`,
  comandos `bim`.
- **FASES 34–35 (v1.3.0)**: DOCUMENTATION (§68-70: motor de planos,
  documentos paramétricos, memorias/cuadros/listados/informes y
  documentación automática §106) + OPTIMIZATION (§19: 12 objetivos,
  Pareto sin score mágico); comandos `docs` y `optimize`.
- **FASES 40–41 (v1.3.0)**: PERFORMANCE (benchmark determinista de 8
  operaciones + inventario de cachés §87) y REGRESSION (suite dorada:
  TEST-021 Documentación y TEST-024 Recovery incluidos); comandos
  `benchmark run|caches`.

- **Registro de plugins §88 + GAS §31 (v1.4.0)**: los 12 plugins
  del §88 están cargados como builtin (architecture, structure,
  installations, cctv, fire, intrusion, access, perimeter, qto,
  budget, bim, documentation) más gas (plugin del sistema de
  instalaciones según §31), coordination y precons; contrato §89
  verificado contra la CLI, el registro QTO y los rulesets de
  resources (`tests/test_095_plugins_spec88.py`, selftest 24).

## FASE 90 (v1.5.0) — UI gráfica (§90-93)

- Ventana principal §90 en Tkinter (sin dependencias externas):
  menú/barra · EXPLORADOR | LIENZO | PROPIEDADES · AVISOS/LOG/ESTADO
  DE CÁLCULOS; comando `main.py gui [archivo] [--demo]` y 08_GUI.bat.
- Navegación §91 (13 disciplinas sobre el mismo proyecto), buscador
  §92 (ID/código/nombre/descripción/tipo/disciplina/nivel/zona/
  etiqueta) y sistema de estados §93 (transiciones DRAFT→…→ARCHIVED
  con auditoría y eventos; estados de cálculo en el panel).
- Modelos headless verificables sin display: selftest 25 comprobaciones
  (GUI omitida con elegancia si no hay pantalla).

## FASE 90.1 (v1.6.0) — GUI editable

- PropertyEditor con lista blanca de campos por tipo (verificada contra
  los dataclasses del dominio): cada edición audita UPDATE_ENTITY con
  snapshots completos old/new y es reversible con el undo persistente
  §77 (misma mecánica que la CLI).
- EditService: creación declarativa (CREATE_SPECS: local, muro, puerta,
  ventana, nivel, zona, material, sección, elemento, red, nodo) y
  borrado por fachada con cascadas muro→vanos, nodo→tramos, red→todo
  y planos de documentación; todo con auditoría y eventos §75.
- Lienzo: zoom anclado al cursor, desplazamiento con botón central,
  coordenadas de mundo en la barra de estado, doble clic para encuadrar.
- Atajos de teclado §90 (Ctrl+N/O/S/Z/Y/F/E, Supr, +/−, F, Escape, F1)
  documentados en Ayuda → Atajos; ACCELERATORS verificado por tests.
- 32 pruebas nuevas (tests/test_097_gui_edicion.py); selftest 26
  comprobaciones (nueva: edición GUI auditada + creación + undo).

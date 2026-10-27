# ui/

Interfaz gráfica de escritorio (FASE 90, spec §90-93), entregada en
v1.5.0 con Tkinter (sin dependencias externas) y editable desde v1.6.0:

- `ui/disciplines.py` — las 13 disciplinas de la navegación (§91).
- `ui/models.py` — modelos headless: explorador, buscador de los 9
  campos (§92), propiedades, sistema de estados de entidades (§93),
  primitivas del lienzo, viewport (zoom/pan/zoom_at/encuadre) y estado
  de cálculos (§93). Desde v1.6.0 añade PropertyEditor (edición con
  lista blanca, auditoría UPDATE_ENTITY y undo §77), CREATE_SPECS +
  EditService (creación declarativa y borrado por fachadas con
  cascadas). Verificables sin display (tests/test_096_gui.py y
  tests/test_097_gui_edicion.py).
- `ui/app_window.py` — ventana principal §90 (MENU/TOOLBAR ·
  EXPLORADOR | LIENZO | PROPIEDADES · AVISOS/LOG/ESTADO DE CÁLCULOS)
  sobre las fachadas de servicios, más `main.py gui` y 08_GUI.bat.

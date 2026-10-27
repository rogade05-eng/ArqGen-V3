"""Main window of ARQ GEN (FASE 90, spec sections 90-93).

Layout §90: MENU/TOOLBAR · PROJECT EXPLORER | CANVAS | PROPERTIES ·
WARNINGS/LOG/CALCULATION STATUS. Navigation by the 13 disciplines of
§91, search box with the 9 fields of §92, and the §93 state system
(entity states via the StateService, calculation states in the status
panel). All logic lives in ui.models; this module is only widgets.

Mejora UX v1.7.1: tema oscuro con letras claras (ui.theme), ayuda
dinámica en cada control (ui.help: globos + barra de estado), mensajes
orientadores al abrir cada menú, panel de bienvenida en proyectos
vacíos y sugerencias del siguiente paso tras cada acción.
"""

from __future__ import annotations

import math
import os
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Dict, List, Optional, Sequence

from core import APP_VERSION
from core.geometry import engine as geom
from core.geometry import representation as rep
from core.geometry import structural as st
from app.autosave import AutoSaveService
from ui import help as help_mod
from ui import icons, prefs, theme
from ui import presets as upres
from ui.disciplines import DISCIPLINES, discipline_label
from ui.help import (FIELD_HINTS, GUIDE_STEPS,
                     Tooltip, attach_menu_hints, next_hint)
from ui.models import (CanvasModel, CREATE_SPECS, EditService,
                       EntityStateFlow, ExplorerModel, ObjectRow, SEARCH_FIELDS,
                       PropertiesModel, PropertyEditor, SearchEngine,
                       StateService, StatusModel, Viewport,
                       calc_type_label, choice_values, status_label)
from ui.theme import CANVAS_DARK, ENTITY_COLORS, menu_kwargs
from ui import wizard as wiz
from ui import building_wizard as bwiz
from ui import cad_tools as cad
from ui import dibujo_cad as dib
from ui import cursor_acad, editor_espacios, keymap
from ui import coords_entrada as crd
from ui import linea_comandos as lc
from ui import navegacion as nav
from ui import variant_budget as vbudget
from ui.wizard import LocalWizardData, WIZARD_STEPS

# Paleta determinista por tipo/sistema: tonos del tema oscuro ajustados
# para contrastar sobre el lienzo profundo (los originales siguen
# disponibles vía ENTITY_COLORS invertidos si se necesitara).
PALETTE: Dict[str, str] = dict(ENTITY_COLORS)
PALETTE.update({
    "selection": CANVAS_DARK["selection"],
    "grid": CANVAS_DARK["grid"],
    "axis": CANVAS_DARK["axis"],
    # Concepción de espacios (v3.15.0)
    "furniture": "#c9a86a",      # mobiliario (madera cálida)
    "roof": "#7f8ea3",           # contorno del alero de la cubierta
    "roof_ridge": "#a8b6c8",     # cumbrera
    "ramp": "#7fb069",           # rampa accesible
    "handrail": "#e07a5f",       # barandilla / barra de apoyo
    # Escaleras por tipología y aberturas (v3.19.0)
    "stair": "#c9b8a3",          # contorno de la escalera (piedra)
    "stair_tread": "#9a8a76",    # líneas de huella de los peldaños
})

# Atajos de teclado §90 (documentados en Ayuda → Atajos y verificables
# headless desde tests/test_097).
ACCELERATORS: Dict[str, str] = {
    "<Control-n>": "new_project",
    "<Control-o>": "open_project_dialog",
    "<Control-s>": "save_project",
    "<Control-z>": "undo",
    "<Control-y>": "redo",
    "<Control-f>": "focus_search",
    "<Control-e>": "edit_property_dialog",
    "<Delete>": "delete_selection",
    "<Key-plus>": "zoom_in",
    "<Key-minus>": "zoom_out",
    "<Escape>": "clear_search",
    "<F1>": "show_quick_guide",
    "<Shift-F1>": "what_is_this",
    "<Control-Key-1>": "toggle_panel_explorer",
    "<Control-Key-2>": "toggle_panel_props",
    "<Control-Key-3>": "toggle_panel_bottom",
    "<Control-Key-0>": "reset_layout",
    "<Control-t>": "toggle_theme",
}

# Ventanas secundarias ajustables (v3.7.0): geometría por defecto y
# tamaño mínimo por diálogo. La geometría elegida por el usuario se
# recuerda en prefs["dialogs"][clave] al cerrar cada ventana.
DIALOG_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "catalogo": {"geometry": "1000x660", "min": (720, 480)},
    "detalles": {"geometry": "1020x680", "min": (760, 500)},
    "presupuesto": {"geometry": "1060x640", "min": (760, 500)},
    "importar_catalogo": {"geometry": "760x540", "min": (620, 420)},
    "importar_dxf": {"geometry": "760x560", "min": (620, 440)},
    "importar_ifc": {"geometry": "780x560", "min": (640, 450)},
    "building_wizard": {"geometry": "1120x760", "min": (900, 620)},
    "design_wizard": {"geometry": "640x640", "min": (520, 480)},
    "guia": {"geometry": "640x620", "min": (500, 460)},
    "regen": {"geometry": "1060x720", "min": (860, 560)},
    "vista_3d": {"geometry": "1000x680", "min": (780, 540)},
    "cad_herramientas": {"geometry": "", "min": (200, 360)},
    "modificaciones": {"geometry": "960x700", "min": (800, 580)},
    "diseno_espacios": {"geometry": "1080x680", "min": (860, 540)},
    "puntero_rejilla": {"geometry": "", "min": (380, 340)},
    "editor_local": {"geometry": "880x620", "min": (740, 540)},
    "estado": {"geometry": "", "min": (420, 320)},
    "editar": {"geometry": "", "min": (380, 260)},
    "nuevo_objeto": {"geometry": "", "min": (380, 320)},
    "tipo_objeto": {"geometry": "", "min": (360, 200)},
    "desde_dibujo": {"geometry": "980x780", "min": (820, 600)},
    "servicios": {"geometry": "900x740", "min": (760, 560)},
}

# Separadores de FÁBRICA de la ventana principal (v3.9.1): afinados
# para darle al plano el mayor espacio posible sin ahogar los paneles.
#   explorer       → ancho del panel explorador (px)
#   props_margin   → distancia del segundo separador al borde derecho
#                    (el panel de propiedades queda de margin − 10 px)
#   bottom_margin  → distancia del separador inferior al borde inferior
#                    (el panel de avisos queda de margin − 10 px)
SASH_DEFAULT_EXPLORER = 240
SASH_DEFAULT_PROPS_MARGIN = 300
SASH_DEFAULT_BOTTOM_MARGIN = 120


def geometry_size(text: Any) -> str:
    """Valida una geometría Tk («1020x680+40+30» → tal cual).

    Tolerante: devuelve «» si el texto no trae un tamaño WxH entero
    decente (mínimo 200x160), para no restaurar basura guardada.
    Acepta posiciones positivas y negativas (+40+30 / -10-20).
    """
    if not isinstance(text, str) or "x" not in text:
        return ""
    head = text.lstrip("=")
    size_part = head
    for cut in (head.find("+"), head.find("-")):
        if cut > 0:
            size_part = head[:cut]
            break
    try:
        width, height = size_part.split("x", 1)
        if int(width) < 200 or int(height) < 160:
            return ""
    except (ValueError, TypeError):
        return ""
    return text


class ARQGenWindow(tk.Tk):
    """Ventana principal §90 sobre las fachadas de servicios."""

    def __init__(self, context: Any, application: Any = None) -> None:
        super().__init__()
        self.ctx = context
        self.application = application
        self.prefs = prefs.load_prefs()
        self.title(f"ARQ GEN {APP_VERSION} — {context.project.name}")
        self.geometry("1280x800")
        # La ventana nunca colapsa: mínimo cómodo para el plano (v3.7.0).
        self.minsize(960, 600)
        theme.apply(self, self.prefs.get("theme", "dark"))
        # Ícono y logo de la marca: el de 256 px SOLO para la barra de
        # título; la barra de herramientas usa el logo pequeño (22 px,
        # v3.9.0) — el gigante le robaba al plano ~200 px de alto.
        self._logo_photo = icons.window_icon(self)
        self._logo_small = icons.toolbar_logo(22, master=self)

        self.explorer = ExplorerModel(context)
        self.search_engine = SearchEngine(self.explorer)
        self.canvas_model = CanvasModel(context, self.explorer)
        self.state_service = StateService(context)
        self.edit_service = EditService(context, self.explorer)
        self.status_model = StatusModel(context)
        self.viewport = Viewport()

        self.current_discipline = "ARCHITECTURE"
        self.selection: Optional[ObjectRow] = None
        self._primitives: List[Any] = []
        self._result_rows: List[ObjectRow] = []
        self._pan_start: Optional[tuple[float, float]] = None
        self._coord_var: Optional[Any] = None
        self._status_base = ""
        self._tooltips: List[Tooltip] = []
        # Autoguardado: guarda solo ante cada cambio (preferencia del
        # usuario, persistida en prefs).
        self.autosave = AutoSaveService(
            context, enabled=self.prefs.get("autosave", True))
        # Registro de paneles colapsables (aprovechamiento del espacio).
        self._panel_frames: Dict[str, Any] = {}
        self._panel_panes: Dict[str, Any] = {}
        self._panel_visible: Dict[str, bool] = {
            "explorer": True, "props": True, "bottom": True}
        self._help_mode: bool = False
        # Herramientas de edición tipo CAD (v3.14.0): herramienta
        # activa, pasos dados, entidad elegida y paleta/asistente.
        self._cad_tool: Optional[str] = None
        self._cad_pasos: List[tuple[float, float]] = []
        self._cad_ref: Optional[tuple[str, str]] = None
        self._cad_datos: Dict[str, Any] = {}
        self._cad_paso: int = 0
        self._cad_palette: Optional[tk.Toplevel] = None
        self._servicios_dialog: Optional[tk.Toplevel] = None
        self._dd_dialog: Optional[tk.Toplevel] = None
        # Teclado, puntero y portapapeles estilo AutoCAD (v3.16.0)
        from ui import keymap as _keymap, cursor_acad as _cursor_acad
        self.teclas = _keymap.TecladoAutoCAD()
        self._acad = _cursor_acad.config_de_datos(
            self.prefs.get("cursor") if hasattr(self, "prefs") else None)
        self._pan_temporal = False
        self._portapapeles: Optional[Tuple[str, str]] = None
        self._acad_marcador: Optional[Tuple[float, float, str]] = None
        self._mod_dialog: Optional[tk.Toplevel] = None
        # Tags del lienzo que son DIBUJO, no objetos: la mira que sigue
        # al raton y la capa temporal de una orden CAD (v3.19.1). Sin
        # esto la mira robaba el «current» y NADA se podia seleccionar.
        self._TAGS_SUPERPUESTOS = frozenset({"acad_mira", "cadoverlay"})
        # Linea de comandos y navegación clasica (v3.38.0): historial,
        # pila de vistas para ZOOM ANTERIOR, zoom por ventana, marco de
        # selección (ventana azul / cruce verde), orto con Mayus y la
        # rejilla anidada adaptativa.
        self._cmd = lc.LineaComandos(keymap.ALIAS_COMANDOS)
        self._cmd_entry: Optional[tk.Entry] = None
        self._pila_vistas = nav.PilaVistas()
        self._zoom_marco: Optional[tuple[float, float]] = None
        self._zoom_orden = False        # la orden Z espera sus esquinas
        self._marco_sel: Optional[tuple[float, float]] = None
        self._marco_activo = False      # el arrastre paso los 4 px
        self._seleccion_multi: List[Any] = []
        self._orto_shift = False        # Mayus mantiene = orto temporal
        self._nivel_rejilla = 0         # nivel anidado visible de la rejilla
        self._rejilla_datos: Optional[Dict[str, Any]] = None

        self._build_menu()
        self._build_toolbar()
        self._build_layout()
        self._build_statusbar()
        self._wire_canvas()
        self._bind_accelerators()
        # Modo «¿Qué es esto?»: explicación al próximo clic (bind en
        # captura de liberación, sin interferir con los gestos normales).
        self.bind_all("<ButtonRelease-1>", self._help_mode_click, add="+")
        self._subscribe_events()
        self._apply_saved_panels()
        self.geometry_restored = False
        geometry = self.prefs.get("geometry") or ""
        if isinstance(geometry, str) and "x" in geometry:
            try:
                self.geometry(geometry)
                self.geometry_restored = True
            except Exception:  # noqa: BLE001 - geometría inválida
                pass
        # Separadores: restaurar los recordados (o colocar los de
        # defecto) cuando la ventana ya tenga su tamaño definitivo. Se
        # aplica DOS VECES (80 y 260 ms): un Configure tardío del X
        # server re-distribuye por pesos y pisaría la primera pasada.
        # Último intento de restauración (v3.8.0): qué PanedWindow se
        # aplicó y cuál se descartó por cambiar las cuentas de paneles.
        self._sashes_last: Dict[str, bool] = {}
        self._sashes_after = self.after(80, self._apply_saved_sashes)
        self._sashes_after2 = self.after(260, self._apply_saved_sashes)
        self._autosave_loop()
        self.refresh_all(fit=True)
        self._say("Bienvenido a ARQ GEN. Pasa el cursor por cualquier "
                  "botón para ver qué hace.",
                  next_hint(**self._project_stats()))

    # -- construcción de la UI (§90) -------------------------------------
    def _bind_accelerators(self) -> None:
        for sequence, method_name in ACCELERATORS.items():
            handler = getattr(self, method_name, None)
            if callable(handler):
                self.bind_all(sequence, lambda _e, h=handler: h())

    def _build_menu(self) -> None:
        old = self.cget("menu")
        if old:
            try:
                self.nametowidget(old).destroy()
            except Exception:  # noqa: BLE001 - menú ya destruido
                pass
        menubar = tk.Menu(self, **menu_kwargs())

        m_file = tk.Menu(menubar, **menu_kwargs())
        m_file.add_command(label="Nuevo proyecto…",
                           command=self.new_project,
                           accelerator="Ctrl+N")
        m_file.add_command(label="Abrir…", command=self.open_project_dialog,
                           accelerator="Ctrl+O")
        m_file.add_command(label="Proyecto de demostración",
                           command=self.open_demo)
        m_file.add_separator()
        m_file.add_command(label="Guardar\tCtrl+S", command=self.save_project)
        m_file.add_separator()
        export_menu = tk.Menu(m_file, **menu_kwargs())
        for fmt in ("DXF", "JSON", "XLSX", "CSV", "IFC", "SVG"):
            export_menu.add_command(
                label=f"Exportar {fmt}…",
                command=lambda f=fmt: self.export(f))
        export_menu.add_command(
            label="Exportar DXF R12 (compatibilidad)…",
            command=self.export_dxf_r12)
        export_menu.add_separator()
        export_menu.add_command(
            label="Exportar TODO (BIM + planos)…",
            command=self.exportar_todo_paquete)
        m_file.add_cascade(label="Exportar", menu=export_menu)
        m_file.add_separator()
        m_file.add_command(label="Salir", command=self.on_close)
        menubar.add_cascade(label="Archivo", menu=m_file)

        m_edit = tk.Menu(menubar, **menu_kwargs())
        m_edit.add_command(label="Deshacer\tCtrl+Z", command=self.undo)
        m_edit.add_command(label="Rehacer\tCtrl+Y", command=self.redo)
        m_edit.add_separator()
        m_edit.add_command(label="Nuevo objeto…",
                           command=self.new_object_dialog)
        m_edit.add_command(label="Editar propiedad…\tCtrl+E",
                           command=self.edit_property_dialog)
        m_edit.add_command(label="Estado de la entidad…",
                           command=self.change_state_dialog)
        m_edit.add_separator()
        m_edit.add_command(label="Eliminar selección\tSupr",
                           command=self.delete_selection)
        menubar.add_cascade(label="Editar", menu=m_edit)

        m_view = tk.Menu(menubar, **menu_kwargs())
        m_view.add_command(label="Zoom +\t+", command=lambda: self.zoom(1.25))
        m_view.add_command(label="Zoom −\t−", command=lambda: self.zoom(0.8))
        m_view.add_command(label="Encuadrar todo\tF",
                           command=self.fit_view)
        m_view.add_command(label="Vista 3D del edificio…",
                           command=self.open_view3d_dialog)
        m_view.add_checkbutton(label="Cuadrícula", onvalue=True,
                               offvalue=False, variable=self._grid_var(),
                               command=self.redraw)
        m_view.add_separator()
        m_view.add_command(label="Alternar tema oscuro/claro\tCtrl+T",
                           command=self.toggle_theme)
        m_view.add_checkbutton(label="Autoguardado (guarda solo ante cada "
                                    "cambio)",
                               onvalue=True, offvalue=False,
                               variable=self._autosave_var(),
                               command=self.toggle_autosave)
        m_view.add_separator()
        m_view.add_checkbutton(label="Explorador del proyecto\tCtrl+1",
                               onvalue=True, offvalue=False,
                               variable=self._panel_var("explorer"),
                               command=lambda: self.toggle_panel("explorer"))
        m_view.add_checkbutton(label="Panel de propiedades\tCtrl+2",
                               onvalue=True, offvalue=False,
                               variable=self._panel_var("props"),
                               command=lambda: self.toggle_panel("props"))
        m_view.add_checkbutton(label="Panel inferior (avisos/registro)\tCtrl+3",
                               onvalue=True, offvalue=False,
                               variable=self._panel_var("bottom"),
                               command=lambda: self.toggle_panel("bottom"))
        m_view.add_separator()
        m_view.add_command(label="Restaurar disposición por defecto\tCtrl+0",
                           command=self.reset_layout)
        menubar.add_cascade(label="Ver", menu=m_view)

        m_tools = tk.Menu(menubar, **menu_kwargs())
        m_tools.add_command(label="Asistente de edificación (edificio "
                                  "completo paso a paso)…",
                            command=self.open_building_wizard)
        m_tools.add_command(label="Validar vivienda (catálogo §54: "
                                  "VIV001-030)…",
                            command=self.validar_vivienda_informe)
        m_tools.add_command(label="Validar centro comercial / oficinas "
                                  "(documento CC/OF)…",
                            command=self.validar_comercial_informe)
        m_tools.add_command(label="Validar escuela / círculo infantil / "
                                  "albergue (documento ED)…",
                            command=self.validar_educacion_informe)
        m_tools.add_command(label="Alternativas de vivienda (catálogo "
                                  "§62-63)…",
                            command=self.alternativas_vivienda_informe)
        m_tools.add_command(label="Modulación constructiva (catálogo "
                                  "§56)…",
                            command=self.modulacion_informe)
        m_tools.add_command(label="Solar fotovoltaica (catálogo §38)…",
                            command=self.solar_informe)
        m_tools.add_command(label="Piscina (catálogo §45)…",
                            command=self.piscina_dialogo)
        m_tools.add_command(label="Acústica de la vivienda (catálogo "
                                  "§46)…",
                            command=self.acustica_informe)
        m_tools.add_command(label="Plan domótico (catálogo §39)…",
                            command=self.domotica_informe)
        m_tools.add_command(label="Regenerar edificación (mover, añadir, "
                                  "quitar y retrazar todo)…",
                            command=self.open_regen_dialog)
        m_tools.add_command(label="Panel de herramientas CAD (mover, "
                                  "copiar, reflejar, recortar…)…",
                            command=self.open_cad_palette)
        m_tools.add_command(label="Panel de dibujo (muros, espacios, "
                                  "zonas y vanos)…",
                            command=self.open_dibujo_palette)
        m_tools.add_command(label="Asistente de servicios (servicios "
                                  "completos por temática)…",
                            command=self.open_servicios_dialog)
        m_tools.add_command(label="Desde dibujo (contorno -> "
                                  "edificación o servicio)…",
                            command=self.open_desde_dibujo_dialog)
        m_tools.add_command(label="Asistente de modificaciones (edición "
                                  "guiada con vista previa)…",
                            command=self.open_mod_wizard)
        m_tools.add_command(label="Concepción de espacios (mobiliario, "
                                  "cubiertas y accesibilidad)…",
                            command=self.open_diseno_dialog)
        m_tools.add_command(label="Asistente de local (modificar: "
                                  "identidad, geometría, vanos, "
                                  "instalaciones y mobiliario)…",
                            command=self.open_editor_local_dialog)
        m_tools.add_command(label="Puntero y rejilla (mira, F3/F7/F8/F9, "
                                  "color)…",
                            command=self.open_puntero_dialog)
        m_tools.add_command(label="Asistente de diseño (local paso a "
                                  "paso)…",
                            command=self.open_design_wizard)
        m_tools.add_command(label="Catálogo PRECONS III (precios "
                                  "oficiales)…",
                            command=self.open_catalogo_precons)
        m_tools.add_command(label="Detalles constructivos (biblioteca "
                                  "regional)…",
                            command=self.open_detalles)
        m_tools.add_command(label="Presupuesto con catálogo PRECONS "
                                  "III…",
                            command=self.open_presupuesto_precons)
        m_tools.add_command(label="Importar catálogo de precios "
                                  "(asistente §94)…",
                            command=self.open_importar_catalogo)
        m_tools.add_command(label="Importar plano DXF/DWG (§94)…",
                            command=self.open_importar_dxf)
        m_tools.add_command(label="Importar modelo IFC…",
                            command=self.open_importar_ifc)
        m_tools.add_separator()
        m_tools.add_command(label="Validar proyecto",
                            command=self.run_validation)
        m_tools.add_command(label="Calcular cantidades (QTO)",
                            command=self.run_qto)
        m_tools.add_command(label="Calcular presupuesto",
                            command=self.run_budget)
        m_tools.add_command(label="Recalcular todo (QTO + presupuesto)",
                            command=self.run_recompute_all)
        m_tools.add_separator()
        m_tools.add_command(label="Informe descriptivo (Markdown)…",
                            command=self.export_report)
        m_tools.add_command(label="Informe descriptivo (PDF)…",
                            command=lambda: self.export_report("pdf"))
        menubar.add_cascade(label="Herramientas", menu=m_tools)

        m_help = tk.Menu(menubar, **menu_kwargs())
        m_help.add_command(label="Guía rápida…", accelerator="F1",
                           command=self.show_quick_guide)
        m_help.add_command(label="¿Qué es esto? (pulsa un control)\tMayús+F1",
                           command=self.what_is_this)
        m_help.add_command(label="Atajos de teclado…",
                           command=self.show_shortcuts)
        m_help.add_command(label="Acerca de…", command=self.about)
        menubar.add_cascade(label="Ayuda", menu=m_help)
        self.config(menu=menubar)
        attach_menu_hints(menubar, self.status_var_for_menus())

    def status_var_for_menus(self) -> tk.StringVar:
        """Barra de estado aunque los menús se construyan antes."""
        if not hasattr(self, "status_var"):
            self.status_var = tk.StringVar(value="")
        return self.status_var

    def _grid_var(self) -> tk.BooleanVar:
        if not hasattr(self, "_show_grid"):
            self._show_grid = tk.BooleanVar(value=True)
        return self._show_grid

    def _autosave_var(self) -> tk.BooleanVar:
        if not hasattr(self, "_autosave_enabled"):
            self._autosave_enabled = tk.BooleanVar(
                value=bool(self.autosave.enabled))
        return self._autosave_enabled

    def _panel_var(self, name: str) -> tk.BooleanVar:
        store = getattr(self, "_panel_vars", None)
        if store is None:
            store = self._panel_vars = {}
        if name not in store:
            store[name] = tk.BooleanVar(
                value=self._panel_visible.get(name, True))
        return store[name]

    def _build_toolbar(self) -> None:
        """Barra de herramientas en DOS filas (v3.9.0).

        La primera concentra las ACCIONES (asistentes, edición y tema);
        la segunda, la NAVEGACIÓN del lienzo y los FILTROS (encuadre,
        zoom, buscador y nivel). Antes todo cabía —mal— en una sola
        fila: con la escala de Windows el extremo derecho (el filtro
        «Nivel:») quedaba fuera de la ventana y no se veía. En dos
        filas compactas nada se corta y el plano gana espacio.
        """
        # -- Fila A · acciones -------------------------------------------
        bar = ttk.Frame(self, padding=(6, 2))
        bar.pack(side="top", fill="x")

        # Marca discreta: el logo pequeño basta (el nombre completo ya
        # vive en la barra de título y en la barra de tareas).
        if self._logo_small is not None:
            logo = ttk.Label(bar, image=self._logo_small)
            logo.pack(side="left", padx=(0, 6))
            self._tip(logo, "building_wizard")

        # Los asistentes van PRIMEROS y destacados: son la puerta de
        # entrada para «irme armando la edificación» sin saber nada de
        # la app. El de EDIFICACIÓN completa va al frente (v1.8.0).
        self._tip(ttk.Button(bar, text=icons.label(
                                 "building_wizard",
                                 "Asistente de edificación"),
                             style="Accent.TButton",
                             command=self.open_building_wizard),
                  "building_wizard").pack(side="left")

        self._tip(ttk.Button(bar, text=icons.label("local_wizard",
                                                   "Asistente de local"),
                             style="Accent.TButton",
                             command=self.open_editor_local_dialog),
                  "asistente_local").pack(side="left", padx=(6, 0))

        self._tip(ttk.Button(bar, text=icons.label("guide", "Guía rápida"),
                             style="Guide.TButton",
                             command=self.show_quick_guide),
                  "guide").pack(side="left", padx=(8, 0))

        # Botones de edición rápida (FASE 90.1)
        self._tip(ttk.Button(bar,
                             text=icons.label("new_object", "Objeto"),
                             style="Accent.TButton",
                             command=self.new_object_dialog),
                  "new_object").pack(side="left", padx=(10, 2))
        self._tip(ttk.Button(bar, text=icons.label("edit", "Editar"),
                             command=self.edit_property_dialog),
                  "edit").pack(side="left", padx=2)
        self._tip(ttk.Button(bar, text=icons.label("save", "Guardar"),
                             command=self.save_project),
                  "save_btn").pack(side="left", padx=2)

        # Vista 3D axonométrica (v3.11.0): el edificio generado se
        # gira, se separa en niveles y se exporta en PNG.
        self._tip(ttk.Button(bar, text=icons.label("vista3d", "Vista 3D"),
                             style="Accent.TButton",
                             command=self.open_view3d_dialog),
                  "vista3d").pack(side="left", padx=(10, 2))

        # Herramientas CAD (v3.14.0): paleta de edición con iconos
        # (mover, copiar, reflejar, girar, recortar, chaflán...).
        self._tip(ttk.Button(bar, text=icons.label(
                                 "cad_herramientas", "Herramientas CAD"),
                             style="Accent.TButton",
                             command=self.open_cad_palette),
                  "cad_herramientas").pack(side="left", padx=(10, 2))

        # Dibujo (v3.33.0): muros, espacios, zonas y vanos a dos clics
        # como ArchiCAD/AutoCAD, con las reglas del proyecto vivas.
        self._tip(ttk.Button(bar, text=icons.label("dibujo", "Dibujar"),
                             style="Accent.TButton",
                             command=self.open_dibujo_palette),
                  "dibujo").pack(side="left", padx=(10, 2))

        # Asistente de servicios (v3.33.0): servicios completos por
        # temática (anatomía patológica, hemodiálisis...) sin generar
        # la edificación entera.
        self._tip(ttk.Button(bar, text=icons.label("servicios",
                                                   "Servicios"),
                             style="Accent.TButton",
                             command=self.open_servicios_dialog),
                  "servicios").pack(side="left", padx=(10, 2))

        # Desde dibujo (v3.34.0): el camino al revés — del contorno
        # del área (dibujado o importado de DXF) a la edificación o
        # al servicio completo, con crecimiento en altura si no cabe.
        self._tip(ttk.Button(bar, text=icons.label("desde_dibujo",
                                                   "Desde dibujo"),
                             style="Accent.TButton",
                             command=self.open_desde_dibujo_dialog),
                  "desde_dibujo").pack(side="left", padx=(10, 2))

        # Concepción de espacios (v3.15.0): mobiliario, cubiertas y
        # accesibilidad sobre la edificación generada.
        self._tip(ttk.Button(bar, text=icons.label(
                                 "diseno_espacios", "Diseño de espacios"),
                             style="Accent.TButton",
                             command=self.open_diseno_dialog),
                  "diseno_espacios").pack(side="left", padx=(10, 2))

        # Tema claro/oscuro al alcance de un clic (v3.0.0).
        self.theme_button = ttk.Button(bar, text=icons.label(
            "theme", "Modo claro" if theme.current_mode() == "dark"
            else "Modo oscuro"),
            command=self.toggle_theme)
        self._tip(self.theme_button, "theme_toggle")
        self.theme_button.pack(side="right")

        # -- Fila B · navegación del lienzo + filtros --------------------
        # Siempre visible: al ir en su propia fila, ni ventanas
        # estrechas ni escalas altas de Windows la cortan (el filtro
        # «Nivel:» era la víctima habitual del desbordamiento).
        bar_filters = ttk.Frame(self, padding=(6, 2))
        bar_filters.pack(side="top", fill="x")

        self._tip(ttk.Button(bar_filters,
                             text=icons.label("fit", "Encuadrar (F)"),
                             command=self.fit_view),
                  "fit").pack(side="left")
        self._tip(ttk.Button(bar_filters,
                             text=icons.label("zoom_in", "Zoom +"),
                             command=lambda: self.zoom(1.25)),
                  "zoom_in").pack(side="left", padx=(8, 2))
        self._tip(ttk.Button(bar_filters,
                             text=icons.label("zoom_out", "Zoom −"),
                             command=lambda: self.zoom(0.8)),
                  "zoom_out").pack(side="left")

        # Buscador §92: campo + texto
        ttk.Separator(bar_filters, orient="vertical").pack(
            side="left", fill="y", padx=8)
        self.search_field = ttk.Combobox(bar_filters,
                                         values=list(SEARCH_FIELDS),
                                         width=9, state="readonly")
        self.search_field.set("Todo")
        self.search_field.pack(side="left")
        self._tip(self.search_field, "search_field")
        self.search_entry = ttk.Entry(bar_filters, width=18)
        self.search_entry.pack(side="left", padx=4)
        self.search_entry.bind("<Return>", lambda _e: self.run_search())
        self._tip(self.search_entry, "search_entry")
        self._tip(ttk.Button(bar_filters,
                             text=icons.label("search", "Buscar"),
                             command=self.run_search),
                  "search_btn").pack(side="left")
        self._tip(ttk.Button(bar_filters, text="Limpiar",
                             command=self.clear_search),
                  "clear_btn").pack(side="left", padx=2)

        # Filtro de nivel (solo disciplinas espaciales)
        ttk.Separator(bar_filters, orient="vertical").pack(
            side="left", fill="y", padx=8)
        ttk.Label(bar_filters, text="Nivel:").pack(side="left")
        self.level_var = tk.StringVar(value="")
        self.level_combo = ttk.Combobox(bar_filters,
                                        textvariable=self.level_var,
                                        width=12, state="readonly",
                                        values=["(todos)"])
        self.level_combo.current(0)
        self.level_combo.bind("<<ComboboxSelected>>",
                              lambda _e: self.refresh_all())
        self.level_combo.pack(side="left", padx=2)
        self._tip(self.level_combo, "level_combo")

    # -- ayuda dinámica -------------------------------------------------------
    def _tip(self, widget: Any, key: str) -> Any:
        """Registra un globo de ayuda + eco en la barra de estado."""
        text = help_mod.TOOLTIPS.get(key, "")
        if not text:
            return widget
        self._tooltips.append(Tooltip(widget, text,
                                      self.status_var_for_menus(),
                                      restore=lambda: self._status_base))
        return widget

    def _say(self, message: str, hint: str = "") -> None:
        """Mensaje orientador en la barra de estado.

        Combina lo que acaba de pasar (message) con el paso siguiente
        sugerido (hint); también actualiza la línea base que los
        tooltips restauran al salir el cursor.
        """
        base = message if not hint else f"{message} → {hint}"
        self._status_base = base
        self.status_var.set(base)

    def _build_layout(self) -> None:
        # Contenedor vertical: plano (con laterales) arriba y panel de
        # avisos abajo — ambos redimensionables con el ratón.
        outer = ttk.PanedWindow(self, orient="vertical")
        outer.pack(side="top", fill="both", expand=True)
        self._outer_paned = outer

        paned = ttk.PanedWindow(outer, orient="horizontal")
        outer.add(paned, weight=4)
        self._paned = paned

        # -- Explorador de proyecto (§90 izquierda, §91) -----------------
        left = ttk.Frame(paned)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(left, orient="vertical",
                                    command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Button-3>", self._tree_context_menu)
        paned.add(left, weight=1)
        self._panel_frames["explorer"] = left
        self._panel_panes["explorer"] = (paned, 1)

        # -- Canvas (§90 centro) ------------------------------------------
        center = ttk.Frame(paned)
        self.canvas = tk.Canvas(center, bg=theme.COL_CANVAS,
                                highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self._tip(self.canvas, "canvas")
        hint = ttk.Label(center,
                         text="Rueda: zoom · Mayús+rueda: mover · "
                              "Clic derecho: menú o mover · Clic: "
                              "seleccionar · Doble clic: editar",
                         style="Hint.TLabel")
        hint.pack(side="bottom", fill="x")
        self._tip(hint, "hint_bar")
        paned.add(center, weight=4)

        # -- Propiedades (§90 derecha) --------------------------------------
        right = ttk.Frame(paned)
        self.props = ttk.Treeview(right, columns=("valor",), show="headings",
                                  selectmode="none", height=20)
        self.props.heading("valor", text="Valor")
        # Columnas afinadas (v3.9.0) para caber en el panel más
        # estrecho (290 px de fábrica): «valor» se estira al espacio
        # real disponible cuando el usuario amplíe el panel.
        self.props.column("#0", width=116, stretch=False)
        self.props.column("valor", width=150, stretch=True)
        props_scroll = ttk.Scrollbar(right, orient="vertical",
                                     command=self.props.yview)
        self.props.configure(yscrollcommand=props_scroll.set)
        self.props.pack(side="top", fill="both", expand=True)
        props_scroll.pack(side="right", fill="y")
        self.props.bind("<Button-3>", self._props_context_menu)
        self._tip(ttk.Button(right, text="Editar propiedad… (Ctrl+E)",
                             command=self.edit_property_dialog),
                  "props_edit").pack(side="bottom", fill="x", pady=2)
        self._tip(ttk.Button(right, text="Estado de la entidad…",
                             command=self.change_state_dialog),
                  "state_btn").pack(side="bottom", fill="x", pady=2)
        paned.add(right, weight=1)
        self._panel_frames["props"] = right
        self._panel_panes["props"] = (paned, 1)

        # -- Panel inferior: avisos / log / cálculos (§90 abajo) ------------
        # height=100 (v3.9.1): era el panel que MÁS espacio le robaba
        # al plano (y el que más se desbordaba con las prefs heredadas
        # de la v3.8.0), así que pide muy poco alto de fábrica; el
        # usuario puede ampliarlo con el separador o colapsarlo con
        # doble clic.
        bottom = ttk.Notebook(outer, height=100)
        self.warnings_text = tk.Text(bottom, height=3, state="disabled",
                                     wrap="word", font=("TkFixedFont", 9),
                                     background=theme.COL_FIELD,
                                     foreground=theme.COL_TEXT,
                                     insertbackground=theme.COL_TEXT,
                                     relief="flat", padx=8, pady=6)
        bottom.add(self.warnings_text, text="Avisos")
        self.log_text = tk.Text(bottom, height=3, state="disabled",
                                wrap="word", font=("TkFixedFont", 9),
                                background=theme.COL_FIELD,
                                foreground=theme.COL_TEXT,
                                insertbackground=theme.COL_TEXT,
                                relief="flat", padx=8, pady=6)
        bottom.add(self.log_text, text="Registro")
        calc_frame = ttk.Frame(bottom)
        self.calc_tree = ttk.Treeview(
            calc_frame, columns=("tipo", "estado", "objetos", "ms", "fecha"),
            show="headings", selectmode="none", height=4)
        for column, text, width in (
                ("tipo", "Cálculo", 150), ("estado", "Estado", 100),
                ("objetos", "Objetos", 70), ("ms", "ms", 60),
                ("fecha", "Fecha", 170)):
            self.calc_tree.heading(column, text=text)
            self.calc_tree.column(column, width=width, anchor="w")
        calc_scroll = ttk.Scrollbar(calc_frame, orient="vertical",
                                    command=self.calc_tree.yview)
        self.calc_tree.configure(yscrollcommand=calc_scroll.set)
        self.calc_tree.pack(side="left", fill="both", expand=True)
        calc_scroll.pack(side="right", fill="y")
        bottom.add(calc_frame, text="Estado de cálculos")
        outer.add(bottom, weight=1)
        self._panel_frames["bottom"] = bottom
        self._panel_panes["bottom"] = (outer, 1)
        # Ayuda dinámica en las pestañas del panel inferior
        for tab_widget, key in ((self.warnings_text, "warnings_tab"),
                                (self.log_text, "log_tab"),
                                (self.calc_tree, "calc_tab")):
            self._tip(tab_widget, key)
        # Doble clic sobre un separador: colapsa el panel contiguo
        # (v3.8.0) — la forma más rápida de darle TODO el espacio al
        # plano; el menú Ver (o Ctrl+1/2/3) lo trae de vuelta.
        for _pw in (paned, outer):
            _pw.bind("<Double-Button-1>", self._on_sash_double_click)

    def _build_statusbar(self) -> None:
        self.status_var_for_menus()  # garantiza una única instancia
        bar = ttk.Frame(self, padding=(2, 0))
        bar.pack(side="bottom", fill="x")
        # Línea de comandos (v3.38.0): abajo, como siempre. Alias,
        # coordenadas (10,5 / @10,5 / @10<45 / 25), =expresiones y
        # las opciones; flechas para el historial, F2 la ventana.
        cmd_bar = ttk.Frame(bar)
        cmd_bar.pack(side="left", fill="x")
        ttk.Label(cmd_bar, text="Comandos:").pack(side="left")
        self._cmd_entry = ttk.Entry(cmd_bar, width=38)
        self._cmd_entry.pack(side="left", padx=(4, 8))
        self._cmd_entry.bind("<Return>", self._cmd_submit)
        self._cmd_entry.bind("<KP_Enter>", self._cmd_submit)
        self._cmd_entry.bind("<Up>", self._cmd_flecha_arriba)
        self._cmd_entry.bind("<Down>", self._cmd_flecha_abajo)
        self._cmd_entry.bind("<Escape>", self._cmd_escape)
        self._tip(self._cmd_entry, "cmd_line")
        left = ttk.Label(bar, textvariable=self.status_var, anchor="w",
                         padding=(6, 3))
        left.pack(side="left", fill="x", expand=True)
        self._info_var = tk.StringVar(value="")
        middle = ttk.Label(bar, textvariable=self._info_var, anchor="e",
                           padding=(6, 3))
        middle.pack(side="right")
        self._coord_var = tk.StringVar(value="x: —, y: —")
        right = ttk.Label(bar, textvariable=self._coord_var, anchor="e",
                          padding=(6, 3), width=24)
        right.pack(side="right")
        # Indicador de autoguardado (v3.0.0): el usuario siempre sabe
        # cuándo fue la última vez que todo quedó a salvo.
        self._autosave_var_text = tk.StringVar(
            value=f"💾 {self.autosave.status_text()}")
        autosave_label = ttk.Label(bar, textvariable=self._autosave_var_text,
                                   anchor="e", padding=(6, 3))
        autosave_label.pack(side="right")
        self._tip(autosave_label, "autosave_toggle")

    # -- ventanas y separadores ajustables (v3.7.0) -------------------------
    def _prepare_dialog(self, dialog: tk.Toplevel, key: str,
                        remember: bool = True) -> None:
        """Ventana secundaria con bordes ajustables (v3.7.0).

        Aplica la geometría recordada (prefs["dialogs"][key]) o la de
        defecto, fija un tamaño mínimo razonable y garantiza que la
        ventana sea redimensionable tirando de sus bordes. Con
        ``remember`` la geometría elegida se guarda al cerrar la
        ventana (también al salir de la app) para la próxima sesión.
        """
        conf = DIALOG_DEFAULTS.get(key, {})
        remembered = ""
        if remember:
            dialogs = self.prefs.get("dialogs")
            if isinstance(dialogs, dict):
                remembered = geometry_size(dialogs.get(key, ""))
        try:
            dialog.geometry(remembered or conf.get("geometry", ""))
        except Exception:  # noqa: BLE001 - geometría inválida: la de defecto
            dialog.geometry(conf.get("geometry", ""))
        min_size = conf.get("min", (480, 360))
        dialog.minsize(*min_size)
        dialog.resizable(True, True)
        if remember:
            def _remember(event: Any) -> None:
                if event.widget is not dialog:
                    return  # <Destroy> también llega por los hijos
                try:
                    dialogs = self.prefs.setdefault("dialogs", {})
                    if isinstance(dialogs, dict):
                        dialogs[key] = dialog.geometry()
                    self._save_prefs_now()
                except Exception:  # noqa: BLE001 - cierre best-effort
                    pass
            dialog.bind("<Destroy>", _remember)

    def _apply_saved_sashes(self) -> None:
        """Posiciones de los separadores arrastrables de la ventana

        principal: restaura las recordadas (prefs["sashes"]) o coloca
        unas de defecto amables — explorador 240 px, propiedades 300 px
        y panel inferior 120 px (v3.9.1) — para que el plano quede
        grande. Es tolerante: si un panel está oculto cambian las
        cuentas y se descarta la restauración de ese PanedWindow.

        Migración one-shot (v3.9.1): las preferencias heredadas de
        versiones anteriores podían traer el separador inferior a
        media ventana (colocación fija a 400 px de la era v3.8.0),
        así que la primera sesión que aplica sashes marca
        prefs["bottom_compact"] y se impone el default compacto; a
        partir de ahí manda lo que el usuario coloque.
        """
        paned = getattr(self, "_paned", None)
        outer = getattr(self, "_outer_paned", None)
        if paned is None or outer is None:
            return
        # Sin ventana mapeada, el primer Configure del PanedWindow
        # re-distribuye TODO por pesos y pisaría las posiciones: se
        # difiere hasta que el mapeo haya pasado.
        if not self.winfo_ismapped() or not paned.winfo_ismapped():
            try:
                self._sashes_after = self.after(40, self._apply_saved_sashes)
            except Exception:  # noqa: BLE001 - ventana cerrada ya
                pass
            return
        # Con el maquetado al día, sashpos no se ve recortado por los
        # tamaños pedidos de los hijos (fuentes recién calibradas…).
        try:
            self.update_idletasks()
        except Exception:  # noqa: BLE001
            pass
        # Observable del mecanismo (v3.8.0): refleja el ÚLTIMO intento,
        # no los píxeles finales — Tk puede recortar un sashpos por los
        # tamaños pedidos de los hijos según fuente/DPI de la plataforma.
        self._sashes_last = {"paned": False, "outer": False}
        saved = self.prefs.get("sashes") or {}
        width = max(self.winfo_width(), 1280)
        height = max(self.winfo_height(), 800)
        try:
            if len(paned.panes()) == 3:
                positions = saved.get("paned")
                if not (isinstance(positions, (list, tuple))
                        and len(positions) == 2):
                    positions = (SASH_DEFAULT_EXPLORER,
                                 max(620, width - SASH_DEFAULT_PROPS_MARGIN))
                for index, value in enumerate(positions[:2]):
                    paned.sashpos(index, int(value))
                self._sashes_last["paned"] = True
            if len(outer.panes()) == 2:
                saved_outer = saved.get("outer")
                if not self.prefs.get("bottom_compact"):
                    # Migración ONE-SHOT (v3.9.1): el panel de avisos
                    # de sesiones anteriores podía quedar a media
                    # ventana; UNA sola vez se impone el default
                    # compacto y queda marcado (después manda lo que
                    # el usuario coloque con el separador). Se BORRA
                    # el guardado heredado para que los re-apliques
                    # posteriores (hay dos after() en el arranque y
                    # reset_layout) no lo revivan.
                    self.prefs["bottom_compact"] = True
                    saved_outer = None
                    sashes = self.prefs.get("sashes")
                    if isinstance(sashes, dict):
                        sashes.pop("outer", None)
                if (isinstance(saved_outer, (list, tuple))
                        and len(saved_outer) == 1):
                    positions = (int(saved_outer[0]),)
                else:
                    positions = (max(300,
                                     height - SASH_DEFAULT_BOTTOM_MARGIN),)
                outer.sashpos(0, positions[0])
                self._sashes_last["outer"] = True
        except Exception:  # noqa: BLE001 - separadores best-effort
            pass

    def _collect_sashes(self) -> None:
        """Guarda en prefs las posiciones actuales de los sashes."""
        sashes = self.prefs.setdefault("sashes", {})
        if not isinstance(sashes, dict):
            sashes = self.prefs["sashes"] = {}
        paned = getattr(self, "_paned", None)
        outer = getattr(self, "_outer_paned", None)
        if paned is not None:
            sashes["paned"] = [int(paned.sashpos(i))
                               for i in range(len(paned.panes()) - 1)]
        if outer is not None:
            sashes["outer"] = [int(outer.sashpos(i))
                               for i in range(len(outer.panes()) - 1)]

    # -- restaurar disposición + doble clic en separadores (v3.8.0) ----------
    def _sash_panel_map(self, paned: Any) -> Dict[int, str]:
        """Mapa «índice de separador → panel que colapsa».

        El criterio es el natural: doble clic sobre el separador
        colapsa el panel lateral contiguo (explorador a la izquierda,
        propiedades a la derecha, avisos abajo). Los índices se
        deducen de los paneles VISIBLES ahora mismo, así el mapa
        sigue siendo correcto aunque ya haya un panel oculto.
        """
        mapping: Dict[int, str] = {}
        if paned is None:
            return mapping
        try:
            panes = [str(p) for p in paned.panes()]
        except Exception:  # noqa: BLE001
            return mapping
        frames = {name: str(frame)
                  for name, frame in self._panel_frames.items()}
        for index in range(len(panes) - 1):
            before, after = panes[index], panes[index + 1]
            if paned is self._paned:
                if before == frames.get("explorer"):
                    mapping[index] = "explorer"
                elif after == frames.get("props"):
                    mapping[index] = "props"
            elif paned is self._outer_paned:
                if after == frames.get("bottom"):
                    mapping[index] = "bottom"
        return mapping

    def _on_sash_double_click(self, event: Any) -> None:
        """Doble clic sobre un separador: colapsa el panel contiguo.

        El separador NO es un widget (no admite bind directo), así se
        escucha el doble clic del PanedWindow y ``identify(x, y)``
        decide si la pulsación cayó sobre un sash — y cuál. Tk 9
        devuelve el índice directamente (o -1); Tk 8.6 devolvía la
        tupla ("sash", índice): se aceptan las dos formas.
        """
        paned = getattr(event, "widget", None)
        try:
            ident = paned.identify(event.x, event.y)
        except Exception:  # noqa: BLE001 — sash best-effort
            return
        indice: Optional[int] = None
        if isinstance(ident, (tuple, list)) and len(ident) >= 2 \
                and str(ident[0]) == "sash":
            indice = int(ident[1])  # Tk 8.6: ("sash", índice)
        elif isinstance(ident, int) and not isinstance(ident, bool) \
                and ident >= 0:
            indice = ident  # Tk 9: índice del sash, o -1 fuera de uno
        if indice is None:
            return
        name = self._sash_panel_map(paned).get(indice)
        if name:
            self.toggle_panel(name)

    def reset_layout(self) -> None:
        """Vuelve a la disposición de fábrica (v3.8.0).

        Muestra otra vez los tres paneles, borra las posiciones
        guardadas de los separadores y aplica las de defecto
        (explorador 240 px, propiedades al borde derecho, avisos al
        fondo — v3.9.1). Las preferencias quedan coherentes: lo que
        veas tras llamar aquí es lo que habrá en la próxima sesión.
        """
        for name in ("explorer", "props", "bottom"):
            frame = self._panel_frames.get(name)
            info = self._panel_panes.get(name)
            if frame is None or info is None:
                continue
            paned, weight = info
            if str(frame) not in [str(p) for p in paned.panes()]:
                paned.add(frame, weight=weight)
            self._panel_visible[name] = True
            self._panel_var(name).set(True)
        panels = self.prefs.setdefault("panels", {})
        if isinstance(panels, dict):
            panels.update({"explorer": True, "props": True,
                           "bottom": True})
        self.prefs["sashes"] = {}
        self._apply_saved_sashes()
        self._save_prefs_now()
        self._say(
            "Disposición restaurada: paneles visibles y separadores "
            "de fábrica.",
            "Arrastra los separadores a tu gusto (o doble clic sobre "
            "uno para colapsar su panel); la app lo recordará")

    # -- eventos del lienzo -------------------------------------------------
    def _wire_canvas(self) -> None:
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.canvas.bind("<Button-2>", self.on_pan_start)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_end)
        self.canvas.bind("<B2-Motion>", self.on_pan_move)
        # Clic derecho V3: menú contextual al pulsar; si el usuario
        # ARRASTRA, se convierte en desplazamiento del plano.
        self.canvas.bind("<Button-3>", self._on_right_press)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_release)
        self.canvas.bind("<B3-Motion>", self._on_right_motion)
        # Rueda del ratón: zoom (Windows/macOS <MouseWheel>, Linux
        # Button-4/5). Con Mayús: desplaza el plano en horizontal.
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._zoom_at_event(1.1, e))
        self.canvas.bind("<Button-5>", lambda e: self._zoom_at_event(1 / 1.1, e))
        self.canvas.bind("<Shift-MouseWheel>", self._on_wheel_pan)
        self.canvas.bind("<Shift-Button-4>",
                         lambda e: self._pan_at_event(-35, e))
        self.canvas.bind("<Shift-Button-5>",
                         lambda e: self._pan_at_event(35, e))
        self.canvas.bind("<Motion>", self._on_motion)
        # Teclado estilo AutoCAD (v3.16.0): F3/F7/F8/F9/F10 globales y
        # alias/espacio/flechas cuando el LIENZO tiene el foco (para
        # no robar teclas a los campos de texto).
        for sec in ("<F3>", "<F7>", "<F8>", "<F9>", "<F10>", "<F12>"):
            self.bind_all(sec, self._tecla_modo, add="+")
        # F2: ventana de texto con el historial (v3.38.0), global.
        self.bind_all("<F2>", lambda _e: self._ventana_historial(), add="+")
        # Mayus mantenido = orto temporal mientras dibuja (v3.38.0).
        for sec in ("<KeyPress-Shift_L>", "<KeyPress-Shift_R>"):
            self.canvas.bind(sec, self._shift_pulsado, add="+")
        for sec in ("<KeyRelease-Shift_L>", "<KeyRelease-Shift_R>"):
            self.canvas.bind(sec, self._shift_soltado, add="+")
        # Fin del arrastre: ventana azul / cruce verde (v3.38.0).
        self.canvas.bind("<ButtonRelease-1>", self._on_click_suelta,
                         add="+")
        self.canvas.bind("<Key>", self._tecla_canvas)
        self.canvas.bind("<Control-c>", self._portapapeles_copiar_evento)
        self.canvas.bind("<Control-x>", self._portapapeles_cortar_evento)
        self.canvas.bind("<Control-v>", self._portapapeles_pegar_evento)
        # Esc cancela la herramienta CAD activa (v3.14.0).
        self.canvas.bind("<Escape>", self._cad_cancelar)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())

    def _on_wheel(self, event) -> None:
        # Delta con signo en Windows; delta crudo en macOS.
        # 1.2 por muesca de 120, anclado al cursor (v3.38.0).
        muescas = max(-3.0, min(3.0, event.delta / 120.0))
        factor = 1.2 ** muescas if muescas else 1.2
        self._zoom_at_event(factor, event)

    def _on_wheel_pan(self, event) -> None:
        # Mayús + rueda: desplazamiento horizontal suave.
        self._pan_at_event(-30 if event.delta > 0 else 30, event)

    def _pan_at_event(self, dx_pixels: float, event) -> None:
        """Desplaza el viewport en píxeles de pantalla (rueda con Mayús)."""
        self.viewport.pan_by(dx_pixels, 0)
        self.redraw()

    # -- clic derecho: menú contextual o desplazamiento ----------------------
    def _on_right_press(self, event) -> None:
        self._right_origin = (event.x, event.y)
        self._right_dragged = False

    def _on_right_motion(self, event) -> None:
        origin = getattr(self, "_right_origin", None)
        if origin is None:
            return
        if not self._right_dragged and (
                abs(event.x - origin[0]) + abs(event.y - origin[1])) > 4:
            self._right_dragged = True
            self._pan_start = origin  # el pan hereda la posición original
        if self._right_dragged:
            self.on_pan_move(event)

    def _on_right_release(self, event) -> None:
        dragged = getattr(self, "_right_dragged", False)
        self._right_origin = None
        self._right_dragged = False
        if dragged:
            self.on_pan_end(event)
        else:
            self._canvas_context_menu(event)

    def _on_motion(self, event) -> None:
        """Coordenadas de mundo bajo el cursor (lectura en la barra)."""
        if self._coord_var is None:
            return
        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 600)
        wx, wy = self.viewport.from_screen(event.x, event.y, width, height)
        self._coord_var.set(f"x: {wx:.2f} m, y: {wy:.2f} m")
        if self._cad_tool:
            self._cad_overlay(event)
        # Zoom por ventana en curso: marco vivo (v3.38.0)
        if self._zoom_marco is not None:
            self.canvas.delete("zoommarco")
            self.canvas.create_rectangle(
                self._zoom_marco[0], self._zoom_marco[1],
                event.x, event.y, outline="#5a8cff", width=1,
                tags=("zoommarco",))
        # Selección por arrastre: ventana azul / cruce verde (v3.38.0)
        if self._marco_sel is not None:
            dx = event.x - self._marco_sel[0]
            dy = event.y - self._marco_sel[1]
            if not self._marco_activo and math.hypot(dx, dy) >= 4.0:
                self._marco_activo = True
            if self._marco_activo:
                self._dibuja_marco_seleccion(event.x, event.y)
        # Mira y referencias estilo AutoCAD (v3.16.0)
        self._mira_redibuja(event)

    # -- línea de comandos (v3.38.0) ---------------------------------------
    # Abajo, como siempre: alias, coordenadas (10,5 / @10,5 / @10<45 /
    # 25), =expresiones y Enter vacío que repite. Las flechas recorren
    # el historial y F2 abre la ventana de texto.

    def _cmd_flecha_arriba(self, _evento=None):
        """Flecha arriba: la entrada anterior del historial."""
        if self._cmd_entry is None:
            return None
        texto = self._cmd.flecha_arriba(self._cmd_entry.get())
        self._cmd_entry.delete(0, "end")
        self._cmd_entry.insert(0, texto)
        return "break"      # el Entry no mueve el cursor de sitio

    def _cmd_flecha_abajo(self, _evento=None):
        """Flecha abajo: la entrada siguiente (o lo que se escribía)."""
        if self._cmd_entry is None:
            return None
        texto = self._cmd.flecha_abajo() or ""
        self._cmd_entry.delete(0, "end")
        self._cmd_entry.insert(0, texto)
        return "break"

    def _cmd_escape(self, _evento=None):
        """Esc en la línea de comandos: limpia y cancela la orden."""
        if self._cmd_entry is not None:
            self._cmd_entry.delete(0, "end")
        self._cad_cancelar()
        return "break"

    def _cmd_submit(self, _evento=None) -> None:
        """Enter en la línea de comandos: interpreta y despacha.

        El alias completo SIEMPRE gana; las coordenadas tecleadas
        BYPASS de referencias/orto/rejilla (el teclado no se imanta,
        como en el clásico); =expresión devuelve el valor y Enter sin
        texto repite la última orden.
        """
        if self._cmd_entry is None:
            return
        texto = self._cmd_entry.get()
        self._cmd_entry.delete(0, "end")
        resultado = self._cmd.interpretar(
            texto,
            ultimo_punto=self._cad_pasos[-1] if self._cad_pasos else None)
        tipo = resultado.get("tipo")
        if tipo == "vacio":
            if self.teclas.ultima_accion:
                self._ejecutar_accion_cad("repetir")
            else:
                self._say("Línea de comandos: un alias (MU, M, Z...), "
                          "coordenadas 10,5 / @10,5 / @10<45, o "
                          "=expresión", "")
            return
        if tipo == "orden":
            self._cmd.push(str(resultado.get("texto", "")))
            self._say(f"{resultado['accion']}", "")
            self._ejecutar_accion_cad(resultado["accion"])
            return
        if tipo == "coordenada":
            self._cmd.push(str(resultado.get("texto", "")))
            if resultado.get("error"):
                self._say(resultado["error"], "")
                return
            self._punto_tecleado(resultado["punto"])
            return
        if tipo == "expresion":
            self._cmd.push(str(resultado.get("texto", "")))
            if resultado.get("error"):
                self._say(resultado["error"], "")
            else:
                self._say(f"= {resultado['valor']:.4f}",
                          "El resultado quedó en el historial (F2)")
            return
        # desconocido
        sugerencia = resultado.get("sugerencia") or ""
        self._say(f"No se entiende «{texto}».",
                  f"¿Quisiste decir «{sugerencia}»?" if sugerencia else
                  "Ejemplos: MU muro, M mover, Z zoom ventana, 10,5")

    def _punto_tecleado(self, punto) -> None:
        """Un punto tecleado entra a la herramienta armada SIN
        referencias ni orto ni rejilla. Sin herramienta armada, o con
        una orden que exige elegir entidad a clic, se informa honesto."""
        tool = self._cad_tool
        if not tool:
            self._say("No hay orden armada: escribe un alias (MU, ES, "
                      "M...) y después las coordenadas", "")
            return
        if tool in dib.ES_VANO_DIBUJO:
            self._say("La puerta y la ventana van con un clic sobre un "
                      "muro: las coordenadas no eligen muro", "")
            return
        prompts = cad.PROMPTS.get(tool) \
            or dib.PROMPTS_DIBUJO.get(tool, ("",))
        if tool in dib.PUNTOS_DIBUJO:
            self._cad_pasos.append((float(punto[0]), float(punto[1])))
            if len(self._cad_pasos) < dib.PUNTOS_DIBUJO.get(tool, 2):
                self._cad_paso = len(self._cad_pasos)
                indice = min(len(self._cad_pasos), len(prompts) - 1)
                self._say(crd.texto_punto(punto), prompts[indice])
                self._cad_overlay()
                return
            self._cad_ejecuta()
            return
        if not self._cad_ref:
            self._say("Primero elige el objeto con un clic (el teclado "
                      "no elige entidades)", prompts[0])
            return
        self._cad_pasos.append((float(punto[0]), float(punto[1])))
        if len(self._cad_pasos) < self._CAD_PUNTOS.get(tool, 0):
            indice = min(1 + self._cad_paso, len(prompts) - 1)
            self._cad_paso += 1
            self._say(crd.texto_punto(punto), prompts[indice])
            self._cad_overlay()
            return
        self._cad_ejecuta()

    def _ventana_historial(self) -> None:
        """F2: ventana de texto con el historial de la línea."""
        dialog = tk.Toplevel(self)
        dialog.title("Historial de comandos")
        self._prepare_dialog(dialog, "cmd_history")
        lista = tk.Listbox(dialog, activestyle="none")
        for linea in self._cmd.historial:
            lista.insert("end", linea)
        lista.pack(fill="both", expand=True, padx=6, pady=6)
        barra = ttk.Scrollbar(dialog, orient="vertical",
                              command=lista.yview)
        barra.pack(side="right", fill="y")
        lista.configure(yscrollcommand=barra.set)
        lista.see("end")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    # -- orto temporal con Mayús (v3.38.0) ----------------------------------

    def _shift_pulsado(self, _evento=None) -> None:
        self._orto_shift = True

    def _shift_soltado(self, _evento=None) -> None:
        self._orto_shift = False

    def _zoom_at_event(self, factor: float, event) -> None:
        """Zoom anclado al cursor (FASE 90.1); la vista anterior queda
        en la pila para ZP (v3.38.0)."""
        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 600)
        self._push_vista()
        self.viewport.zoom_at(factor, event.x, event.y, width, height)
        self.redraw()

    # -- navegación clásica (v3.38.0) ---------------------------------------

    def _push_vista(self) -> None:
        """Guarda la vista ACTUAL antes de un zoom/pan/encuadre."""
        self._pila_vistas.push(self.viewport.center_x,
                               self.viewport.center_y,
                               self.viewport.scale)

    def _zoom_anterior(self) -> None:
        """ZP: restaura la vista anterior de la pila (hasta 32)."""
        vista = self._pila_vistas.pop()
        if vista is None:
            self._say("No hay vista anterior: la pila (32) está vacía.",
                      "Cada zoom, pan o encuadre guarda la vista")
            return
        cx, cy, escala = vista
        self.viewport.center_x = cx
        self.viewport.center_y = cy
        self.viewport.scale = escala
        self.redraw()
        self._say("Zoom anterior restaurado.", "")

    def _zoom_ventana(self) -> None:
        """Z: arma el ZOOM Ventana (dos clics con marco azul)."""
        self._zoom_orden = True
        self._zoom_marco = None
        self._say("ZOOM Ventana: clic en la primera esquina",
                  "El segundo clic encuadra el rectángulo; ESC sale")

    def _zoom_ventana_clic(self, event) -> None:
        """Un clic con el ZOOM Ventana armado: ancla o completa."""
        if self._zoom_marco is None:
            self._zoom_marco = (event.x, event.y)
            self._say("Segunda esquina del zoom", "")
            return
        x0, y0 = self._zoom_marco
        self._zoom_marco = None
        self._zoom_orden = False
        self.canvas.delete("zoommarco")
        if abs(event.x - x0) < 4 or abs(event.y - y0) < 4:
            self._say("Ventana demasiado pequeña: repite Z",
                      "Arrastra de una esquina a la opuesta")
            return
        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 600)
        wx0, wy0 = self.viewport.from_screen(x0, y0, width, height)
        wx1, wy1 = self.viewport.from_screen(event.x, event.y,
                                             width, height)
        self._push_vista()
        self.viewport.fit((min(wx0, wx1), min(wy0, wy1),
                           max(wx0, wx1), max(wy0, wy1)),
                          width, height)
        self.redraw()

    def _on_click_suelta(self, event) -> None:
        """Fin del arrastre de selección: VENTANA (izq->der, dentro) o
        CRUCE (der->izq, toca), con los colores clásicos. Un clic sin
        arrastre no toca nada: la selección de siempre ya actuó."""
        if self._marco_sel is None:
            return
        x0, y0 = self._marco_sel
        self._marco_sel = None
        self.canvas.delete("marcoseleccion")
        if not self._marco_activo:
            return
        self._marco_activo = False
        ventana = event.x >= x0 and event.y >= y0
        modo = "ventana" if ventana else "cruce"
        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 600)
        wx0, wy0 = self.viewport.from_screen(min(x0, event.x),
                                             min(y0, event.y),
                                             width, height)
        wx1, wy1 = self.viewport.from_screen(max(x0, event.x),
                                             max(y0, event.y),
                                             width, height)
        rect = (min(wx0, wx1), min(wy0, wy1), max(wx0, wx1),
                max(wy0, wy1))
        elegidas = self._seleccion_por_marco(rect, ventana)
        self._seleccion_multi = elegidas
        if elegidas:
            self.selection = elegidas[0]
        else:
            self.selection = None
        self.refresh_properties()
        self.redraw()
        self._say(f"{len(elegidas)} seleccionado(s) por {modo}.",
                  "Esc deselecciona; Borrar (E) los elimina")

    def _dibuja_marco_seleccion(self, x: float, y: float) -> None:
        """El marco vivo: azul sólido (ventana) o verde discontinuo
        (cruce), según la dirección del arrastre."""
        self.canvas.delete("marcoseleccion")
        if self._marco_sel is None:
            return
        x0, y0 = self._marco_sel
        ventana = x >= x0 and y >= y0
        if ventana:
            self.canvas.create_rectangle(
                x0, y0, x, y, outline="#5a8cff", fill="#4682ff",
                stipple="gray25", width=1,
                tags=("marcoseleccion",))
        else:
            self.canvas.create_rectangle(
                x0, y0, x, y, outline="#5adc78", fill="#50dc6e",
                stipple="gray25", width=1, dash=(6, 3),
                tags=("marcoseleccion",))

    def _seleccion_por_marco(self, rect, ventana: bool) -> List[Any]:
        """Filas dentro del rectángulo: VENTANA = todos los puntos del
        contorno dentro (el objeto entero); CRUCE = algún punto dentro
        o la caja del objeto toca el rectángulo."""
        x0, y0, x1, y1 = rect
        elegidas: List[Any] = []
        vistos = set()
        for primitive in self._primitives:
            row = getattr(primitive, "row", None)
            coords = getattr(primitive, "coords", None)
            if row is None or not coords:
                continue
            if row.uid in vistos:
                continue
            xs = [p[0] for p in coords]
            ys = [p[1] for p in coords]
            dentro = all(x0 <= x <= x1 and y0 <= y <= y1
                         for x, y in zip(xs, ys))
            toca = dentro or not (max(xs) < x0 or min(xs) > x1
                                  or max(ys) < y0 or min(ys) > y1)
            if (ventana and dentro) or (not ventana and toca):
                fila = self._find_row(row.uid)
                if fila is not None:
                    elegidas.append(fila)
                    vistos.add(row.uid)
        return elegidas

    # -- tema, autoguardado, paneles y menús contextuales (v3.0.0) --------
    def toggle_theme(self) -> None:
        """Alterna oscuro ↔ claro EN VIVO y recuerda la preferencia."""
        mode = theme.toggle()
        theme.restyle_tk_tree(self)
        self._rebuild_palette()
        self._build_menu()  # los menús tk se recrean con los colores nuevos
        if hasattr(self, "theme_button"):
            self.theme_button.configure(text=icons.label(
                "theme", "Modo claro" if mode == "dark"
                else "Modo oscuro"))
        self.redraw()
        self.prefs["theme"] = mode
        self._save_prefs_now()
        self._say(
            f"Modo {'oscuro' if mode == 'dark' else 'claro'} aplicado: "
            "toda la interfaz cambió al instante y lo recordaré la "
            "próxima vez.")

    def _rebuild_palette(self) -> None:
        """Sincroniza la PALETTE del lienzo con el tema activo.

        Mutación en el sitio: las importaciones por valor (test_100)
        siguen viendo el cambio.
        """
        PALETTE.clear()
        PALETTE.update(ENTITY_COLORS)
        PALETTE.update({
            "selection": CANVAS_DARK["selection"],
            "grid": CANVAS_DARK["grid"],
            "axis": CANVAS_DARK["axis"],
        })

    def toggle_autosave(self) -> None:
        """Activa o pausa el autoguardado (preferencia persistida)."""
        enabled = bool(self._autosave_var().get())
        self.autosave.enabled = enabled
        if enabled:
            self.autosave.cancel()
        self._update_autosave_indicator()
        self.prefs["autosave"] = enabled
        self._save_prefs_now()
        if enabled:
            self._say("Autoguardado activado: cada cambio se guarda solo, "
                      "1,2 segundos después de que dejas de trabajar.")
        else:
            self._say("Autoguardado en pausa: recuerda guardar con "
                      "Ctrl+S antes de cerrar.")

    def toggle_panel(self, name: str) -> None:
        """Muestra u oculta un panel para darle aire al plano."""
        frame = self._panel_frames.get(name)
        info = self._panel_panes.get(name)
        if frame is None or info is None:
            return
        paned, weight = info
        paths = [str(p) for p in paned.panes()]
        was_visible = str(frame) in paths
        if was_visible:
            paned.remove(frame)
        else:
            paned.add(frame, weight=weight)
        now_visible = not was_visible
        self._panel_visible[name] = now_visible
        self._panel_var(name).set(now_visible)
        panels = self.prefs.setdefault("panels", {})
        if isinstance(panels, dict):
            panels[name] = now_visible
        self._save_prefs_now()
        labels = {"explorer": "Explorador", "props": "Propiedades",
                  "bottom": "Panel inferior"}
        self._say(
            f"{labels.get(name, name)} "
            f"{'mostrado' if now_visible else 'oculto'}: "
            "el menú Ver (o Ctrl+1/2/3) lo trae de vuelta.")

    def toggle_panel_explorer(self) -> None:
        self.toggle_panel("explorer")

    def toggle_panel_props(self) -> None:
        self.toggle_panel("props")

    def toggle_panel_bottom(self) -> None:
        self.toggle_panel("bottom")

    def _apply_saved_panels(self) -> None:
        """Restaura los paneles ocultos guardados en preferencias."""
        saved = self.prefs.get("panels") or {}
        for name, visible in saved.items():
            if name in self._panel_frames and visible is False \
                    and self._panel_visible.get(name, True):
                self.toggle_panel(name)

    # -- autoguardado ---------------------------------------------------------
    def _autosave_loop(self) -> None:
        """Sondeo suave del autoguardado (cadena única de after)."""
        try:
            before = self.autosave.save_count
            self.autosave.flush()
            if self.autosave.save_count != before or \
                    self.autosave.stats()["pending"]:
                self._update_autosave_indicator()
        except Exception:  # noqa: BLE001 - la UI sobrevive al autosave
            pass
        try:
            self._autosave_after_id = self.after(250, self._autosave_loop)
        except Exception:  # noqa: BLE001 - ventana destruida
            pass

    def destroy(self) -> None:  # noqa: D102 - tk.Tk
        # Cancela el temporizador del autoguardado para que Tcl no
        # intente invocar un comando ya eliminado.
        try:
            after_id = getattr(self, "_autosave_after_id", None)
            if after_id:
                self.after_cancel(after_id)
        except Exception:  # noqa: BLE001
            pass
        super().destroy()

    def _update_autosave_indicator(self) -> None:
        try:
            self._autosave_var_text.set(
                f"💾 {self.autosave.status_text()}")
        except Exception:  # noqa: BLE001 - barra aún no construida
            pass

    # -- menús contextuales (clic derecho) -------------------------------------
    def _popup_menu(self, menu: tk.Menu, event) -> None:
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _hit_uid(self, event) -> Optional[str]:
        """uid del objeto del lienzo bajo el cursor (None = vacío).

        Recorre los objetos de ARRIBA hacia ABAJO y devuelve el primer
        tag que resuelve a una fila real del explorador. Los
        superpuestos de dibujo (mira estilo AutoCAD, capa de la orden
        CAD, rejilla y tarjetas sin uid) NO se pueden seleccionar: así
        la cruz que sigue al ratón nunca roba el clic (v3.19.1).
        """
        try:
            items = self.canvas.find_overlapping(
                event.x - 2, event.y - 2, event.x + 2, event.y + 2)
            for item in reversed(items):
                tags = self.canvas.gettags(item)
                if self._TAGS_SUPERPUESTOS.intersection(tags):
                    continue  # mira / overlay de CAD: no es seleccionable
                for tag in tags:
                    if tag and tag != "current" \
                            and self._find_row(tag) is not None:
                        return tag
        except Exception:  # noqa: BLE001 - lienzo sin coordenadas válidas
            pass
        return None

    def _canvas_context_menu(self, event) -> None:
        """Menú del lienzo: propiedades/edición sobre lo pulsado, o
        acciones de vista si el clic fue en vacío."""
        uid = self._hit_uid(event)
        if uid:
            row = self._find_row(uid)
            if row is not None:
                self.selection = row
                self.refresh_properties()
                self.redraw()
        menu = tk.Menu(self, **menu_kwargs())
        if uid and self.selection is not None:
            name = (self.selection.name or self.selection.code or
                    "objeto")
            menu.add_command(label=f"Editar «{name}»…\tCtrl+E",
                             command=self.edit_property_dialog)
            if self.selection.type == "SPACE":
                menu.add_command(
                    label="Asistente de local (modificar «" + name
                          + "»)…",
                    command=lambda: self.open_editor_local_dialog())
            menu.add_command(label="Estado de la entidad…",
                             command=self.change_state_dialog)
            menu.add_separator()
            menu.add_command(label="Eliminar\tSupr",
                             command=self.delete_selection)
            menu.add_separator()
        menu.add_command(label="Zoom +", command=lambda: self.zoom(1.25))
        menu.add_command(label="Zoom −", command=lambda: self.zoom(0.8))
        menu.add_command(label="Encuadrar todo\tF",
                         command=self.fit_view)
        menu.add_separator()
        menu.add_command(label="＋ Nuevo objeto…",
                         command=self.new_object_dialog)
        menu.add_command(label="🏠 Asistente de edificación…",
                         command=self.open_building_wizard)
        menu.add_command(label="♻ Regenerar edificación…",
                         command=self.open_regen_dialog)
        menu.add_command(label="🛋 Diseño de espacios…",
                         command=self.open_diseno_dialog)
        menu.add_command(label="🧊 Vista 3D…",
                         command=self.open_view3d_dialog)
        self._popup_menu(menu, event)
        self._say("Menú contextual del lienzo: edición sobre el objeto "
                  "pulsado o vistas si fue en vacío.")

    def _tree_context_menu(self, event) -> None:
        """Menú del explorador: crear en la disciplina, editar o
        eliminar el objeto apuntado."""
        iid = self.tree.identify_row(event.y)
        menu = tk.Menu(self, **menu_kwargs())
        if iid and iid.startswith("disc:"):
            disc = iid.split(":", 1)[1]
            self.current_discipline = disc
            menu.add_command(
                label=f"＋ Nuevo objeto en {discipline_label(disc)}…",
                command=self.new_object_dialog)
            menu.add_command(label="🔎 Buscar en el proyecto…",
                             command=self.focus_search)
        elif iid and not iid.startswith(("results", "res:")):
            row = self._find_row(iid)
            if row is not None:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                name = row.name or row.code or "objeto"
                menu.add_command(label=f"Editar «{name}»…\tCtrl+E",
                                 command=self.edit_property_dialog)
                menu.add_command(label="Estado de la entidad…",
                                 command=self.change_state_dialog)
                menu.add_separator()
                menu.add_command(label="Eliminar\tSupr",
                                 command=self.delete_selection)
        else:
            menu.add_command(label="＋ Nuevo objeto…",
                             command=self.new_object_dialog)
        self._popup_menu(menu, event)
        self._say("Menú contextual del explorador: acciones directas "
                  "sobre lo que apuntaste.")

    def _props_context_menu(self, event) -> None:
        menu = tk.Menu(self, **menu_kwargs())
        menu.add_command(label="Editar propiedad…\tCtrl+E",
                         command=self.edit_property_dialog)
        menu.add_command(label="Estado de la entidad…",
                         command=self.change_state_dialog)
        self._popup_menu(menu, event)
        self._say("Menú contextual de propiedades: edición rápida del "
                  "objeto seleccionado.")

    # -- modo «¿Qué es esto?» -----------------------------------------------------
    def what_is_this(self) -> None:
        """Ayuda bajo demanda: el próximo clic explica el control."""
        self._help_mode = True
        try:
            self.configure(cursor="question_arrow")
        except Exception:  # noqa: BLE001 - cursor no disponible
            pass
        self._say("Modo «¿Qué es esto?» activo: pulsa cualquier control "
                  "y te explico para qué sirve. Escape para salir.")

    def _help_mode_click(self, event) -> None:
        if not self._help_mode:
            return
        self._help_mode = False
        try:
            self.configure(cursor="")
        except Exception:  # noqa: BLE001
            pass
        text = ""
        current = getattr(event, "widget", None)
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            for tip in self._tooltips:
                if tip.widget is current:
                    text = tip.text
                    break
            if text:
                break
            current = getattr(current, "master", None)
        if not text:
            text = ("ARQ GEN es tu herramienta de arquitectura offline: "
                    "explora a la izquierda, dibuja y consulta en el "
                    "centro, edita a la derecha. Pasa el cursor por "
                    "cualquier botón y la barra inferior explica qué "
                    "hace; F1 abre la guía rápida.")
        self._explain_card(text)
        self._say("¿Dudas con algo más? Pulsa «¿Qué es esto?» cuando "
                  "quieras repetir la explicación.")

    def _explain_card(self, text: str) -> None:
        """Tarjeta de explicación NO modal con autocierre (7 s).

        A diferencia de un messagebox, no bloquea el flujo: se puede
        seguir trabajando y desaparece sola.
        """
        try:
            card = tk.Toplevel(self)
        except Exception:  # noqa: BLE001 - ventana ya cerrada
            return
        card.title("¿Qué es esto?")
        card.transient(self)
        card.resizable(False, False)
        card.attributes("-topmost", True)
        header = ttk.Frame(card, style="Panel.TFrame", padding=(14, 8))
        header.pack(fill="x")
        ttk.Label(header, text="¿Qué es esto?", style="Title.TLabel",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        body = ttk.Frame(card, padding=(14, 8))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=text, style="Guide.TLabel", wraplength=380,
                  justify="left").pack(anchor="w")
        ttk.Button(card, text="Entendido", style="Accent.TButton",
                   command=card.destroy).pack(pady=(0, 10))
        try:
            card.after(7000, card.destroy)
        except Exception:  # noqa: BLE001
            pass

    def _subscribe_events(self) -> None:
        self.ctx.event_bus.subscribe("*", self._on_bus_event)

    def _on_bus_event(self, event) -> None:
        try:
            self.after(0, self._handle_bus_event, event)
        except Exception:  # noqa: BLE001 - ventana ya destruida
            pass

    def _handle_bus_event(self, event) -> None:
        # Autoguardado: cualquier cambio del proyecto marca pendiente;
        # el bucle _autosave_loop vuelca a SQLite tras la calma.
        try:
            if self.autosave.on_event(event):
                self._update_autosave_indicator()
        except Exception:  # noqa: BLE001 - la UI sobrevive al autosave
            pass
        self.refresh_log()
        self.refresh_statusbar()

    # -- datos: explorador, canvas, propiedades -----------------------------
    def _level_filter(self) -> str:
        value = self.level_var.get()
        if not value or value == "(todos)":
            return ""
        for level_id, name in self.explorer._level_names.items():
            if name == value:
                return level_id
        return ""

    def refresh_all(self, fit: bool = False) -> None:
        self.refresh_levels()
        self.refresh_tree()
        self.redraw(fit=fit)
        self.refresh_properties()
        self.refresh_log()
        self.refresh_calcs()
        self.refresh_statusbar()

    def refresh_levels(self) -> None:
        self.explorer._refresh_names()
        names = ["(todos)"] + sorted(
            (n for n in self.explorer._level_names.values() if n))
        current = self.level_var.get() or "(todos)"
        self.level_combo.configure(values=names)
        if current in names:
            self.level_combo.set(current)
        else:
            self.level_combo.set("(todos)")

    def refresh_tree(self) -> None:
        search = self.search_entry.get().strip()
        self.tree.delete(*self.tree.get_children())
        if search:
            self._fill_tree_results()
        else:
            self._fill_tree_disciplines()

    def _fill_tree_disciplines(self) -> None:
        level_id = self._level_filter()
        for discipline in DISCIPLINES:
            node = self.tree.insert("", "end",
                                    iid=f"disc:{discipline.key}",
                                    text=f"{discipline.label} "
                                         f"({discipline.key})",
                                    open=(discipline.key
                                          == self.current_discipline))
            for row in self.explorer.rows_for(discipline.key, level_id):
                if self.tree.exists(row.uid):
                    continue  # defensive: same entity listed twice
                text = f"{row.code} — {row.name}".strip(" —")
                if row.summary:
                    text = f"{text}  [{row.summary}]"
                self.tree.insert(node, "end", iid=row.uid,
                                 text=text or row.uid)

    def _fill_tree_results(self) -> None:
        results = self._result_rows
        root = self.tree.insert("", "end", iid="results",
                                text=f"Resultados ({len(results)})",
                                open=True)
        for index, row in enumerate(results):
            text = (f"[{discipline_label(row.discipline)}] "
                    f"{row.type} · {row.code} {row.name}").strip()
            self.tree.insert(root, "end", iid=f"res:{index}",
                             text=text or row.uid)

    def redraw(self, fit: bool = False) -> None:
        self.canvas.delete("all")
        level_id = self._level_filter()
        self._primitives = self.canvas_model.primitives(
            self.current_discipline, level_id)
        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 600)
        if fit:
            bounds = self.viewport.bounds_of(self._primitives)
            # v3.38.0: sin nada que encuadrar, el rectángulo honesto
            # (-50..50 m) para que el lienzo nunca enmarque el caos
            self.viewport.fit(nav.encuadre_de(bounds), width, height)
        if self._grid_var().get():
            self._draw_grid(width, height)
        self._draw_primitives(width, height)
        if not self._primitives:
            self._draw_welcome(width, height)

    def _draw_welcome(self, width: int, height: int) -> None:
        """Tarjeta de bienvenida cuando el lienzo está vacío.

        En lugar de un plano en blanco, ofrece los tres primeros pasos
        del flujo para que la app se explique sola (no abruma: son
        solo acciones, sin tecnicismos).
        """
        searching = bool(self.search_entry.get().strip()) if \
            hasattr(self, "search_entry") else False
        if searching:
            self.canvas.create_text(
                width // 2, height // 2,
                text="Sin resultados para esta búsqueda",
                fill=CANVAS_DARK["welcome_text"],
                font=("TkDefaultFont", 12), justify="center")
            return
        card_w, card_h = 460, 250
        x0, y0 = width // 2 - card_w // 2, height // 2 - card_h // 2
        self.canvas.create_rectangle(
            x0, y0, x0 + card_w, y0 + card_h,
            fill=CANVAS_DARK["welcome_card"],
            outline=CANVAS_DARK["welcome_border"], width=2)
        cx = width // 2
        self.canvas.create_text(
            cx, y0 + 36, text="Empecemos con tu proyecto",
            fill=CANVAS_DARK["welcome_title"],
            font=("TkDefaultFont", 14, "bold"))
        steps = (
            "1 · Genera la edificación con «Asistente de edificación» y "
            "retoca cada local con «Asistente de local»\n"
            "2 · O crea objetos sueltos (muros, puertas, niveles…) con "
            "«+ Objeto»\n"
            "3 · Calcula con Herramientas ▸ Recalcular todo\n"
            "4 · Exporta o genera el informe cuando estés listo")
        self.canvas.create_text(
            cx, y0 + 112, text=steps,
            fill=CANVAS_DARK["space_text"], font=("TkDefaultFont", 11),
            justify="left")
        self.canvas.create_text(
            cx, y0 + card_h - 42,
            text="¿Prefieres ver un ejemplo?\n"
                 "Archivo ▸ Proyecto de demostración",
            fill=CANVAS_DARK["welcome_text"], font=("TkDefaultFont", 10),
            justify="center")

    def _draw_grid(self, width: int, height: int) -> None:
        """Rejilla ANIDADA adaptativa (v3.38.0): líneas finas cada
        paso y una línea MAYOR cada 5 pasos (la trama clásica que se
        anida al alejar y se subdividi al acercar, con banda antiflip
        para que una muesca de rueda no salte de nivel)."""
        self._calcula_rejilla()
        datos = self._rejilla_datos or {}
        color_major = PALETTE.get("grid_major", PALETTE["axis"])
        for x, es_major in datos.get("lineas_x", []):
            px = self.viewport.to_screen(x, 0, width, height)[0]
            if abs(x) < 1e-9:
                color = PALETTE["axis"]
            elif es_major:
                color = color_major
            else:
                color = PALETTE["grid"]
            self.canvas.create_line(px, 0, px, height, fill=color)
        for y, es_major in datos.get("lineas_y", []):
            py = self.viewport.to_screen(0, y, width, height)[1]
            if abs(y) < 1e-9:
                color = PALETTE["axis"]
            elif es_major:
                color = color_major
            else:
                color = PALETTE["grid"]
            self.canvas.create_line(0, py, width, py, fill=color)

    def _draw_primitives(self, width: int, height: int) -> None:
        for primitive in self._primitives:
            color = PALETTE.get(primitive.color_key, PALETTE["wall"])
            points: List[float] = []
            for x, y in primitive.coords:
                px, py = self.viewport.to_screen(x, y, width, height)
                points.extend((px, py))
            if primitive.kind == "space":
                self.canvas.create_polygon(
                    points, fill=CANVAS_DARK["space_fill"], outline=color,
                    width=1, tags=(primitive.row.uid,))
                self._space_label(primitive, width, height)
            elif primitive.kind == "wall":
                self.canvas.create_polygon(
                    points, fill=color, outline="", tags=(primitive.row.uid,))
            elif primitive.kind == "opening":
                self.canvas.create_line(
                    points, fill=color, width=4,
                    capstyle="round", tags=(primitive.row.uid,))
            elif primitive.kind == "node":
                px, py = self.viewport.to_screen(
                    primitive.coords[0][0], primitive.coords[0][1],
                    width, height)
                self.canvas.create_oval(
                    px - 6, py - 6, px + 6, py + 6, fill=color,
                    outline="", tags=(primitive.row.uid,))
            elif primitive.kind in ("segment", "element"):
                self.canvas.create_line(
                    points, fill=color,
                    width=3 if primitive.kind == "element" else 2,
                    tags=(primitive.row.uid,))
            elif primitive.kind == "furniture":
                # pieza de mobiliario: contorno con relleno tenue y
                # etiqueta corta al acercar (v3.15.0)
                self.canvas.create_polygon(
                    points, fill=CANVAS_DARK["space_fill"],
                    outline=color, width=2,
                    tags=(primitive.row.uid,))
                if self.viewport.scale >= 12:
                    xs = [p[0] for p in primitive.coords]
                    ys = [p[1] for p in primitive.coords]
                    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
                    px, py = self.viewport.to_screen(cx, cy, width, height)
                    self.canvas.create_text(
                        px, py, text=primitive.row.name,
                        font=("TkDefaultFont", 7),
                        fill=CANVAS_DARK["space_text"],
                        tags=(primitive.row.uid,))
            elif primitive.kind == "roof":
                # alero de la cubierta: polígono a trazos (v3.15.0)
                self.canvas.create_polygon(
                    points, fill="", outline=color, width=2,
                    dash=(6, 3), tags=(primitive.row.uid,))
            elif primitive.kind == "roof_ridge":
                self.canvas.create_line(
                    points, fill=color, width=3, capstyle="round",
                    tags=(primitive.row.uid,))
            elif primitive.kind == "ramp":
                self.canvas.create_polygon(
                    points, fill="", outline=color, width=2,
                    tags=(primitive.row.uid,))
                if len(primitive.coords) >= 4:
                    # flecha de SUBIDA: del borde del pie hacia el alto
                    pie_x = (primitive.coords[0][0]
                             + primitive.coords[1][0]) / 2.0
                    pie_y = (primitive.coords[0][1]
                             + primitive.coords[1][1]) / 2.0
                    alto_x = (primitive.coords[2][0]
                              + primitive.coords[3][0]) / 2.0
                    alto_y = (primitive.coords[2][1]
                              + primitive.coords[3][1]) / 2.0
                    p1 = self.viewport.to_screen(pie_x, pie_y, width, height)
                    p2 = self.viewport.to_screen(alto_x, alto_y,
                                                 width, height)
                    self.canvas.create_line(
                        p1[0], p1[1], p2[0], p2[1], fill=color, width=2,
                        arrow="last", tags=(primitive.row.uid,))
            elif primitive.kind == "handrail":
                self.canvas.create_line(
                    points, fill=color, width=3, capstyle="round",
                    tags=(primitive.row.uid,))
            elif primitive.kind == "stair":
                # escalera por tipología: contorno con relleno tenue y
                # etiqueta con el tipo (v3.19.0)
                self.canvas.create_polygon(
                    points, fill=CANVAS_DARK["space_fill"],
                    outline=color, width=2,
                    tags=(primitive.row.uid,))
                if self.viewport.scale >= 12:
                    xs = [p[0] for p in primitive.coords]
                    ys = [p[1] for p in primitive.coords]
                    px, py = self.viewport.to_screen(
                        sum(xs) / len(xs), sum(ys) / len(ys),
                        width, height)
                    self.canvas.create_text(
                        px, py, text=primitive.row.name,
                        font=("TkDefaultFont", 7),
                        fill=CANVAS_DARK["space_text"],
                        tags=(primitive.row.uid,))
            elif primitive.kind == "stair_tread":
                self.canvas.create_line(
                    points, fill=color, width=1, tags=(primitive.row.uid,))
            elif primitive.kind == "abertura_simbolo":
                # símbolo de planos por tipología: arco, corredera,
                # zigzag plegable... (v3.19.0)
                self.canvas.create_line(
                    points, fill=color, width=2, capstyle="round",
                    tags=(primitive.row.uid,))
        if self.selection is not None:
            self._highlight_selection(width, height)

    def _space_label(self, primitive, width: int, height: int) -> None:
        xs = [p[0] for p in primitive.coords]
        ys = [p[1] for p in primitive.coords]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        px, py = self.viewport.to_screen(cx, cy, width, height)
        text = primitive.row.name
        if self.viewport.scale >= 10:
            text = f"{text}\n{primitive.row.summary or ''}".strip()
        self.canvas.create_text(px, py, text=text, justify="center",
                                font=("TkDefaultFont", 8),
                                fill=CANVAS_DARK["space_text"])

    def _highlight_selection(self, width: int, height: int) -> None:
        uids = {self.selection.uid} if self.selection is not None \
            else set()
        # Selección por ventana/cruce (v3.38.0): todo el marco resalta
        for fila in self._seleccion_multi:
            uids.add(fila.uid)
        for primitive in self._primitives:
            if primitive.row.uid not in uids:
                continue
            points: List[float] = []
            for x, y in primitive.coords:
                px, py = self.viewport.to_screen(x, y, width, height)
                points.extend((px, py))
            if primitive.kind in ("node",):
                px, py = self.viewport.to_screen(
                    primitive.coords[0][0], primitive.coords[0][1],
                    width, height)
                self.canvas.create_oval(px - 9, py - 9, px + 9, py + 9,
                                        outline=PALETTE["selection"],
                                        width=2)
            elif len(points) >= 4:
                self.canvas.create_line(
                    points, fill=PALETTE["selection"], width=2,
                    dash=(4, 2))
                if primitive.kind in ("space", "wall"):
                    self.canvas.create_polygon(points, fill="",
                                               outline=PALETTE["selection"],
                                               width=2)

    # -- interacción ---------------------------------------------------------
    def on_tree_select(self, _event=None) -> None:
        iid = self.tree.focus()
        if not iid or iid.startswith(("disc:", "results", "res:")):
            return
        row = self._find_row(iid)
        if row is None:
            return
        if iid.startswith("res:"):
            # Un resultado de búsqueda cambia a su disciplina.
            self.current_discipline = row.discipline
            self.search_entry.delete(0, "end")
            self._result_rows = []
            self.refresh_all()
            self.tree.selection_set(row.uid)
            self.tree.focus(row.uid)
            return
        self.selection = row
        self.refresh_properties()
        self.redraw()

    def _find_row(self, uid: str) -> Optional[ObjectRow]:
        if self._result_rows:
            index = uid[len("res:"):] if uid.startswith("res:") else None
            if index is not None and index.isdigit():
                return self._result_rows[int(index)]
        level_id = self._level_filter()
        for row in self.explorer.rows_for(self.current_discipline, level_id):
            if row.uid == uid:
                return row
        return None

    def on_canvas_click(self, event) -> None:
        self.canvas.focus_set()
        # PAN temporal (tecla P, como AutoCAD): el clic arrastra la vista.
        if self._pan_temporal:
            self.on_pan_start(event)
            return
        # ZOOM Ventana armado (Z): los clics van al marco (v3.38.0)
        if self._zoom_orden:
            self._zoom_ventana_clic(event)
            return
        # Herramienta CAD activa: el clic la alimenta y no selecciona.
        if self._cad_tool:
            self._cad_click(event)
            return
        # Arrastre de selección: guarda el ancla del marco (v3.38.0);
        # si no hay arrastre (menos de 4 px) es el clic de siempre.
        self._marco_sel = (event.x, event.y)
        self._marco_activo = False
        # Picking robusto (v3.19.1): find_overlapping + salto de la
        # mira/overlay, en vez de «current» (la cruz que sigue al raton
        # era SIEMPRE el objeto «current» y se comia el clic).
        uid = self._hit_uid(event)
        if not uid:
            return
        row = self._find_row(uid)
        if row is None:
            return
        self.selection = row
        self.refresh_properties()
        self.redraw()

    def _zoom_armando(self) -> bool:
        """Compat: el armado vive en _zoom_orden desde v3.38.0."""
        return getattr(self, "_zoom_orden", False)

    def on_canvas_double_click(self, event) -> None:
        """Doble clic sobre un objeto: sus propiedades; sobre vacío: encuadrar."""
        uid = self._hit_uid(event)
        if not uid:
            self.fit_view()
            return
        row = self._find_row(uid)
        if row is None:
            return
        self.selection = row
        self.refresh_properties()
        self.redraw()
        self.edit_property_dialog()

    def on_pan_start(self, event) -> None:
        self._push_vista()
        self._pan_start = (event.x, event.y)

    def on_pan_move(self, event) -> None:
        if self._pan_start is None:
            return
        dx = event.x - self._pan_start[0]
        dy = event.y - self._pan_start[1]
        self._pan_start = (event.x, event.y)
        self.viewport.center_x -= dx / self.viewport.scale
        self.viewport.center_y += dy / self.viewport.scale
        self.redraw()

    def on_pan_end(self, _event=None) -> None:
        self._pan_start = None

    def zoom(self, factor: float) -> None:
        self._push_vista()
        self.viewport.zoom(factor)
        self.redraw()

    def fit_view(self) -> None:
        self._push_vista()
        self.redraw(fit=True)

    # -- buscador §92 ----------------------------------------------------------
    def run_search(self) -> None:
        query = self.search_entry.get()
        field = self.search_field.get()
        self._result_rows = self.search_engine.search(
            query, field, level_id=self._level_filter())
        self.refresh_tree()
        if self._result_rows:
            self._say(
                f"Búsqueda «{query}»: {len(self._result_rows)} "
                "resultado(s)",
                next_hint(searching=True))
        else:
            self._say(
                f"Sin resultados para «{query}». Prueba con otro término "
                "o cambia el campo de búsqueda (por ejemplo, «Nombre»).",
                "Pulsa Escape o «Limpiar» para volver al árbol")

    def clear_search(self) -> None:
        if self._help_mode:
            self._help_mode = False
            try:
                self.configure(cursor="")
            except Exception:  # noqa: BLE001
                pass
            self._say("Modo «¿Qué es esto?» desactivado. Vuelves al "
                      "trabajo normal.")
            return
        self.search_entry.delete(0, "end")
        self._result_rows = []
        self.refresh_tree()
        self._say("Búsqueda limpia: de nuevo ves el árbol completo del "
                  "proyecto.",
                  next_hint(**self._project_stats()))

    # -- propiedades ---------------------------------------------------------------
    def refresh_properties(self) -> None:
        self.props.delete(*self.props.get_children())
        if self.selection is None:
            self.props.insert("", "end", iid="prop:hint",
                              values=("Selecciona un objeto en el "
                                      "explorador o en el plano y sus "
                                      "datos aparecerán aquí",))
            return
        row = self.selection
        editable = set()
        if row.entity is not None:
            editable = set(PropertyEditor.EDITABLE_FIELDS.get(
                row.entity.ENTITY_TYPE, ()))
        for field_name, value in PropertiesModel.properties(row):
            mark = "✎ " if field_name in editable else ""
            self.props.insert("", "end", iid=f"prop:{field_name}",
                              text=mark + field_name, values=(value,))
        if editable:
            self.props.bind("<Double-1>", self._on_prop_double_click)

    def _on_prop_double_click(self, _event=None) -> None:
        iid = self.props.focus()
        if iid.startswith("prop:"):
            self.edit_property_dialog(iid[len("prop:"):])

    # -- estados §93 ------------------------------------------------------------------
    def change_state_dialog(self) -> None:
        if self.selection is None or self.selection.entity is None:
            messagebox.showinfo(
                "Estado de la entidad",
                "Selecciona antes un objeto (no un grupo ni un cálculo): "
                "los estados describen su ciclo de vida, de borrador a "
                "archivado.", parent=self)
            return
        entity = self.selection.entity
        current = (entity.status.value if hasattr(entity.status, "value")
                   else str(entity.status))
        options = EntityStateFlow.next_states(current)
        if not options:
            messagebox.showinfo(
                "Estado de la entidad",
                f"El estado «{status_label(current)}» es final: no "
                "admite más transiciones.",
                parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Estado de la entidad")
        dialog.transient(self)
        dialog.grab_set()
        self._prepare_dialog(dialog, "estado", remember=False)
        ttk.Label(dialog, text=f"{self.selection.code} — estado actual: "
                               f"{status_label(current)}").pack(
            anchor="w", padx=10, pady=(10, 4))
        ttk.Label(dialog,
                  text="Elige el siguiente estado del objeto:",
                  style="Dim.TLabel").pack(anchor="w", padx=10)
        chosen = tk.StringVar(value=options[0])
        for option in options:
            # Mostramos la etiqueta en español; el valor interno sigue
            # siendo el del spec (DRAFT, ACTIVE…) para el servicio.
            ttk.Radiobutton(dialog, text=status_label(option),
                            value=option, variable=chosen).pack(
                anchor="w", padx=16)
        def apply() -> None:
            try:
                self.state_service.change_status(self.selection, chosen.get())
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Estado de la entidad", str(exc),
                                     parent=dialog)
                return
            dialog.destroy()
            self.refresh_all()
            self._say(f"Estado de {self.selection.code} cambiado a "
                      f"{status_label(chosen.get())}.",
                      "El historial del objeto queda registrado en la "
                      "auditoría")
        ttk.Button(dialog, text="Aplicar", style="Accent.TButton",
                   command=apply).pack(
            side="right", padx=10, pady=10)
        ttk.Button(dialog, text="Cancelar",
                   command=dialog.destroy).pack(side="right")

    # -- herramientas -------------------------------------------------------------
    def _project_stats(self) -> Dict[str, int]:
        """Resumen del proyecto para el motor de sugerencias."""
        rows = self.explorer.all_rows()
        def _count(discipline: str, type_name: str) -> int:
            return sum(1 for r in rows.get(discipline, [])
                       if r.type == type_name)
        calcs = len(self.status_model.calculation_rows(limit=50))
        return {"spaces": _count("ARCHITECTURE", "SPACE"),
                "walls": _count("ARCHITECTURE", "WALL"),
                "doors": _count("ARCHITECTURE", "DOOR") +
                         _count("ARCHITECTURE", "WINDOW"),
                "calculations": calcs}

    def run_validation(self) -> None:
        lines = self.status_model.validation_warnings()
        self.warnings_text.configure(state="normal")
        self.warnings_text.delete("1.0", "end")
        self.warnings_text.insert("1.0", "\n".join(lines) or
                                  "Sin hallazgos: el proyecto pasa la "
                                  "validación sin incidencias.")
        self.warnings_text.configure(state="disabled")
        stats = self._project_stats()
        stats["warnings"] = len(lines)
        if lines:
            self._say(f"Validación: {len(lines)} hallazgo(s) en la "
                      "pestaña «Avisos».", next_hint(**stats))
        else:
            self._say("Validación limpia: todo en orden.",
                      next_hint(**stats))

    def run_qto(self) -> None:
        from services.quantity_service import QuantityService
        stats = QuantityService(self.ctx).compute_all()
        self.refresh_calcs()
        self.refresh_statusbar()
        processed = stats.get('objects_processed', 0)
        self._say(f"Cantidades calculadas para {processed} objeto(s).",
                  "Abre la disciplina «Cantidades» en el explorador "
                  "para ver los resultados")

    def run_budget(self) -> None:
        from services.budget_service import BudgetService
        total = BudgetService(self.ctx).compute()
        self.refresh_calcs()
        self._say(f"Presupuesto calculado: {total:,.2f} "
                  f"{self.ctx.project.currency}.",
                  "Abre la disciplina «Presupuesto» en el explorador "
                  "para ver el desglose")

    def undo(self) -> None:
        from app.undo_service import PersistentUndoService
        try:
            result = PersistentUndoService(self.ctx).undo()
            self.ctx.commit()
            self.refresh_all()
            self._say(f"Deshecho: {result['command']}.",
                      "¿Te arrepientes? Ctrl+Y vuelve a rehacerlo")
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("Deshacer", str(exc), parent=self)

    def redo(self) -> None:
        from app.undo_service import PersistentUndoService
        try:
            result = PersistentUndoService(self.ctx).redo()
            self.ctx.commit()
            self.refresh_all()
            self._say(f"Rehecho: {result['command']}.",
                      "Ctrl+Z lo vuelve a deshacer si lo necesitas")
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("Rehacer", str(exc), parent=self)

    # -- atajos y acciones rápidas (FASE 90.1) ---------------------------------
    def save_project(self) -> None:
        self.ctx.commit()
        self.autosave.cancel()
        self.autosave.last_saved = time.strftime("%H:%M:%S")
        self.autosave.save_count += 1
        self._update_autosave_indicator()
        self._say("Proyecto guardado: todos los cambios están a salvo "
                  "(SQLite).",
                  next_hint(**self._project_stats()))

    def focus_search(self) -> None:
        self.search_field.focus_set()
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def zoom_in(self) -> None:
        self.zoom(1.25)

    def zoom_out(self) -> None:
        self.zoom(0.8)

    # -- atajos y ayuda -----------------------------------------------------------
    def show_quick_guide(self) -> None:
        """Recorrido de 4 pasos: qué hace esta pantalla y en qué orden."""
        dialog = tk.Toplevel(self)
        dialog.title("Guía rápida de ARQ GEN")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(background=theme.COL_BG_ALT)
        self._prepare_dialog(dialog, "guia")
        header = ttk.Frame(dialog, style="Panel.TFrame", padding=(16, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Todo lo que necesitas son 4 pasos",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(header,
                  text="Pasa el cursor por cualquier botón y la barra "
                       "inferior te explicará qué hace.",
                  style="Dim.TLabel").pack(anchor="w", pady=(2, 0))
        body = ttk.Frame(dialog, padding=(16, 8))
        body.pack(fill="both", expand=True)
        for title, text in GUIDE_STEPS:
            card = ttk.Frame(body, style="Card.TFrame", padding=(12, 8))
            card.pack(fill="x", pady=4)
            ttk.Label(card, text=title, style="Accent.TLabel",
                      font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
            ttk.Label(card, text=text, style="Guide.TLabel",
                      wraplength=520, justify="left").pack(anchor="w",
                                                          pady=(2, 0))
        ttk.Button(dialog, text="Entendido, a trabajar",
                   style="Accent.TButton",
                   command=dialog.destroy).pack(pady=(4, 12))
        dialog.wait_window()

    def show_shortcuts(self) -> None:
        labels = {
            "Ctrl+N": "Nuevo proyecto", "Ctrl+O": "Abrir proyecto",
            "Ctrl+S": "Guardar (además, autoguardado activo)",
            "Ctrl+Z / Ctrl+Y": "Deshacer / Rehacer",
            "Ctrl+C / X / V": "Copiar / cortar / pegar local o muro",
            "Ctrl+F": "Buscador", "Ctrl+E": "Editar propiedad",
            "Supr": "Eliminar selección",
            "+ / −": "Zoom", "Ctrl+0": "Encuadrar todo",
            "Ctrl+T": "Tema oscuro <-> claro",
            "Ctrl+1/2/3": "Explorador / Propiedades / Panel inferior",
            "Mayús+F1": "¿Qué es esto? (pulsa un control)",
            "Escape": "Cancelar orden / limpiar buscador",
            "F1": "Guía rápida",
            "F3": "Referencias a extremos y puntos medios",
            "F7": "Rejilla visible", "F8": "Modo orto",
            "F9": "Imantar a la rejilla", "F10": "Seguimiento polar",
            "F2": "Historial de comandos",
            "F12": "Pantalla dinámica (distancia y ángulo)",
            "MU ES ZO PU VE": "Dibujar muro, espacio, zona, puerta, ventana",
            "Z ZE ZP": "Zoom ventana, encuadrar todo, zoom anterior",
            "10,5 / @10,5 / @10<45": "Coordenadas en la línea de comandos",
            "ESPACIO": "Repetir la última orden",
            "M CO MI RO": "Mover, copiar, reflejar, girar (como AutoCAD)",
            "TR EX CHA": "Recortar, alargar, chaflán",
            "DIV S O E": "Dividir, estirar, paralela, borrar",
            "U / P": "Deshacer / Pan arrastrando",
            "Arrastrar en vacío": "Seleccionar: ventana azul (dentro) o cruce verde (toca)",
            "Flechas": "Pan fino del plano",
            "Rueda del ratón": "Zoom en el plano",
            "Mayús+rueda": "Mover el plano en horizontal",
            "Clic derecho": "Menú contextual (menú si es clic, pan si "
                            "arrastras)",
            "3D: flechas": "Girar e inclinar; +/− zoom; Home resetea",
        }
        lines = "\n".join(f"{key:>16}  {label}" for key, label in
                          labels.items())
        messagebox.showinfo("Atajos de teclado y gestos", lines,
                            parent=self)

    # -- edición de propiedades (FASE 90.1) -------------------------------------
    def edit_property_dialog(self, field_name: str = "") -> None:
        if self.selection is None or self.selection.entity is None:
            messagebox.showinfo(
                "Editar propiedad",
                "Primero selecciona un objeto (en el explorador o en el "
                "plano). Los campos que admiten edición aparecen marcados "
                "con ✎ en el panel derecho.", parent=self)
            return
        entity = self.selection.entity
        fields = PropertyEditor.editable_fields(entity)
        if not fields:
            messagebox.showinfo(
                "Editar propiedad",
                f"Los objetos de tipo {entity.ENTITY_TYPE} no admiten "
                "edición de campos: sus datos se calculan solos.",
                parent=self)
            return
        if not field_name:
            field_name = fields[0][0]
        current = PropertyEditor.format_value(getattr(entity, field_name))
        dialog = tk.Toplevel(self)
        dialog.title(f"Editar {entity.ENTITY_TYPE}.{field_name}")
        dialog.transient(self)
        dialog.grab_set()
        self._prepare_dialog(dialog, "editar", remember=False)
        ttk.Label(dialog, text=f"{self.selection.code} · {field_name}",
                  font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", padx=10, pady=(10, 2))
        entry = ttk.Entry(dialog, width=34)
        entry.insert(0, current)
        entry.pack(anchor="w", padx=10, pady=4)
        entry.select_range(0, "end")
        field_hint = FIELD_HINTS.get(
            field_name,
            "El valor debe ser válido para el tipo del campo "
            "(texto o número).")
        ttk.Label(dialog, text=field_hint, style="Dim.TLabel",
                  wraplength=300, justify="left").pack(
            anchor="w", padx=10, pady=(0, 4))

        def apply() -> None:
            try:
                self.edit_service.edit(self.selection, field_name,
                                       entry.get())
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Editar propiedad", str(exc),
                                     parent=dialog)
                return
            dialog.destroy()
            self.refresh_tree()
            self.refresh_properties()
            self.redraw()
            self._say(f"Editado {self.selection.code}.{field_name} = "
                      f"{entry.get()}.",
                      "Los cambios ya están en el diario; Ctrl+S los "
                      "consolida")
        entry.bind("<Return>", lambda _e: apply())
        ttk.Button(dialog, text="Aplicar", command=apply).pack(
            side="right", padx=10, pady=10)
        ttk.Button(dialog, text="Cancelar",
                   command=dialog.destroy).pack(side="right")
        entry.focus_set()

    # -- borrado (FASE 90.1) ------------------------------------------------------
    def delete_selection(self) -> None:
        if self.selection is None or self.selection.entity is None:
            messagebox.showinfo(
                "Eliminar selección",
                "Primero selecciona un objeto real (creado por ti) para "
                "eliminar. Si no es lo que buscabas, la operación se "
                "puede deshacer con Ctrl+Z.", parent=self)
            return
        row = self.selection
        if not messagebox.askyesno(
                "Eliminar selección",
                f"¿Eliminar {row.type} {row.code} — {row.name}?\n\n"
                "Tranquilidad: la operación queda registrada y puedes "
                "deshacerla con Ctrl+Z.", parent=self):
            return
        try:
            code = self.edit_service.delete(row)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Eliminar selección", str(exc), parent=self)
            return
        self.selection = None
        self.refresh_all()
        self._say(f"Eliminado {row.type} {code}.",
                  "¿Fue un error? Ctrl+Z lo recupera al instante")

    # -- creación de objetos (FASE 90.1) -------------------------------------------
    def new_object_dialog(self) -> None:
        entity_type = self._ask_entity_type()
        if not entity_type:
            return
        spec = CREATE_SPECS[entity_type][1]
        dialog = tk.Toplevel(self)
        dialog.title(f"Nuevo objeto — {entity_type}")
        dialog.transient(self)
        dialog.grab_set()
        self._prepare_dialog(dialog, "nuevo_objeto", remember=False)
        ttk.Label(dialog,
                  text="Los campos con * son obligatorios; el resto puede "
                       "dejarlos como están.",
                  style="Dim.TLabel", wraplength=340,
                  justify="left").pack(anchor="w", padx=10, pady=(8, 4))
        entries: Dict[str, Any] = {}
        for index, (param, label, kind, required, options,
                    default) in enumerate(spec):
            row_frame = ttk.Frame(dialog)
            row_frame.pack(fill="x", padx=10, pady=2)
            mark = "* " if required else ""
            ttk.Label(row_frame, text=mark + label, width=28).pack(side="left")
            if kind == "choice":
                # v1.7.2: «options» puede ser tupla fija o el nombre de
                # una fuente dinámica («levels», «walls»…). Antes se
                # hacía list("levels") y el desplegable mostraba letras
                # sueltas: por eso el nivel recién creado nunca
                # aparecía al crear un muro. Ahora se consulta SIEMPRE
                # en el momento de abrir el formulario.
                values = choice_values(options,
                                       self.edit_service.choices)
                combo = ttk.Combobox(row_frame, values=values, width=24,
                                     state="readonly")
                if default and default in values:
                    combo.set(default)
                elif len(values) == 1:
                    combo.set(values[0])  # única opción: preseleccionar
                combo.pack(side="left", fill="x", expand=True)
                entries[param] = combo
                self._field_tip(combo, param)
                continue
            entry = ttk.Entry(row_frame, width=26)
            if default not in ("", None):
                entry.insert(0, str(default))
            entry.pack(side="left", fill="x", expand=True)
            entries[param] = entry
            self._field_tip(entry, param)

        def apply() -> None:
            values = {param: widget.get() for param, widget in entries.items()}
            try:
                entity = self.edit_service.create(entity_type, values)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Nuevo objeto", str(exc), parent=dialog)
                return
            dialog.destroy()
            self.refresh_all()
            self._say(f"Creado {entity_type} "
                      f"{getattr(entity, 'code', '')}.",
                      "Sigue construyendo con «+ Objeto» o edítalo con "
                      "doble clic")

        ttk.Button(dialog, text="Crear", style="Accent.TButton",
                   command=apply).pack(
            side="right", padx=10, pady=10)
        ttk.Button(dialog, text="Cancelar",
                   command=dialog.destroy).pack(side="right")

    def _field_tip(self, widget: Any, param: str) -> None:
        """Ayuda específica del campo en formularios de creación."""
        hint = FIELD_HINTS.get(param)
        if hint:
            self._tooltips.append(Tooltip(widget, hint,
                                          self.status_var_for_menus(),
                                          restore=lambda: self._status_base))

    # -- asistente de diseño «arma tu local» (v1.7.2) ---------------------------
    def open_design_wizard(self) -> None:
        """Asistente dinámico en 4 pasos: pide los datos mínimos y va
        armando el local (nivel, medidas, muros, puerta y ventana).

        Toda la lógica vive en ui.wizard (headless); aquí solo se
        dibujan los formularios. El diálogo queda accesible en
        ``self._wizard_dialog`` para las pruebas.
        """
        data = LocalWizardData()
        # Preselección amable: el nivel del filtro actual, o el único
        # nivel del proyecto, o el primero que exista.
        levels = self.edit_service.choices("levels")
        current = self._level_filter()
        if current:
            for level_id, name in self.explorer._level_names.items():
                if level_id == current and name:
                    data.level_ref = name
        elif len(levels) == 1:
            data.level_ref = levels[0]
        elif levels:
            data.level_ref = levels[0]

        dialog = tk.Toplevel(self)
        dialog.title("Asistente de diseño — arma tu local")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        dialog.grab_set()
        self._prepare_dialog(dialog, "design_wizard")
        self._wizard_dialog = dialog

        header = ttk.Frame(dialog, style="Panel.TFrame", padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Vamos a armar tu local juntos",
                  style="Title.TLabel").pack(anchor="w")
        step_var = tk.StringVar()
        ttk.Label(header, textvariable=step_var,
                  style="Accent.TLabel").pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(dialog, padding=(14, 8))
        body.pack(fill="both", expand=True)
        footer = ttk.Frame(dialog, padding=(14, 8))
        footer.pack(fill="x")

        def _row(parent: Any, label: str, tip_key: str = "") -> ttk.Entry:
            frame = ttk.Frame(parent)
            frame.pack(fill="x", pady=2)
            ttk.Label(frame, text=label, width=26).pack(side="left")
            entry = ttk.Entry(frame, width=22)
            entry.pack(side="left", fill="x", expand=True)
            if tip_key:
                self._tip(entry, tip_key)
            return entry

        # -- Paso 1: ¿dónde? -------------------------------------------------
        frame1 = ttk.Frame(body)
        ttk.Label(frame1, text=WIZARD_STEPS[0][2], style="Dim.TLabel",
                  wraplength=430, justify="left").pack(
            anchor="w", pady=(0, 6))
        level_row = ttk.Frame(frame1)
        level_row.pack(fill="x", pady=2)
        ttk.Label(level_row, text="Nivel", width=26).pack(side="left")
        level_combo = ttk.Combobox(level_row, width=27, state="readonly",
                                   values=levels + [wiz.NUEVO_NIVEL])
        level_combo.set(data.level_ref if data.level_ref else
                        (wiz.NUEVO_NIVEL if not levels else ""))
        level_combo.pack(side="left", fill="x", expand=True)
        self._tip(level_combo, "level_ref")
        new_level_row = ttk.Frame(frame1)
        name_entry = _row(frame1, "* Nombre del local", "name")
        type_entry = _row(frame1, "Tipo de local (opcional)",
                          "space_type")
        type_entry.insert(0, "ROOM")
        new_level_name = _row(new_level_row, "* Nombre del nivel nuevo",
                              "name")
        new_level_elev = _row(new_level_row, "Cota del nivel (m)",
                              "elevation_m")

        def _sync_new_level(_event: Any = None) -> None:
            creating = level_combo.get() == wiz.NUEVO_NIVEL
            data.new_level = creating
            if creating:
                new_level_row.pack(fill="x", before=level_row,
                                   padx=(24, 0))
                name_entry.focus_set()
            else:
                new_level_row.pack_forget()
        level_combo.bind("<<ComboboxSelected>>", _sync_new_level)

        # -- Paso 2: ¿tamaño? --------------------------------------------------
        frame2 = ttk.Frame(body)
        ttk.Label(frame2, text=WIZARD_STEPS[1][2], style="Dim.TLabel",
                  wraplength=430, justify="left").pack(
            anchor="w", pady=(0, 6))
        x0_entry = _row(frame2, "Posición X de la esquina (m)", "x")
        y0_entry = _row(frame2, "Posición Y de la esquina (m)", "y")
        width_entry = _row(frame2, "Ancho del local (m)", "width_m")
        depth_entry = _row(frame2, "Fondo del local (m)", "depth_m")
        thick_entry = _row(frame2, "Espesor de los muros (m)",
                           "thickness_m")
        width_entry.insert(0, "4,0")
        depth_entry.insert(0, "3,0")
        thick_entry.insert(0, "0,2")

        # -- Paso 3: ¿vanos? ------------------------------------------------------
        frame3 = ttk.Frame(body)
        ttk.Label(frame3, text=WIZARD_STEPS[2][2], style="Dim.TLabel",
                  wraplength=430, justify="left").pack(
            anchor="w", pady=(0, 6))
        door_var = tk.BooleanVar(value=True)
        window_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame3, text="Incluir puerta",
                        variable=door_var).pack(anchor="w")
        door_w = _row(frame3, "   Ancho de la puerta (m)", "width_m")
        door_h = _row(frame3, "   Alto de la puerta (m)", "height_m")
        door_w.insert(0, "0,9")
        door_h.insert(0, "2,1")
        door_side_row = ttk.Frame(frame3)
        door_side_row.pack(fill="x", pady=2)
        ttk.Label(door_side_row, text="   Lado de la puerta",
                  width=26).pack(side="left")
        door_side = ttk.Combobox(door_side_row, values=list(wiz.DOOR_SIDES),
                                 state="readonly", width=20)
        door_side.set("Frente")
        door_side.pack(side="left")
        ttk.Checkbutton(frame3, text="Incluir ventana",
                        variable=window_var).pack(anchor="w", pady=(6, 0))
        win_w = _row(frame3, "   Ancho de la ventana (m)", "width_m")
        win_h = _row(frame3, "   Alto de la ventana (m)", "height_m")
        win_sill = _row(frame3, "   Antepecho (m)", "sill_height_m")
        win_w.insert(0, "1,2")
        win_h.insert(0, "1,2")
        win_sill.insert(0, "0,9")
        win_side_row = ttk.Frame(frame3)
        win_side_row.pack(fill="x", pady=2)
        ttk.Label(win_side_row, text="   Lado de la ventana",
                  width=26).pack(side="left")
        win_side = ttk.Combobox(win_side_row, values=list(wiz.DOOR_SIDES),
                                state="readonly", width=20)
        win_side.set("Fondo")
        win_side.pack(side="left")

        # -- Paso 4: resumen -------------------------------------------------------
        frame4 = ttk.Frame(body)
        summary = tk.Text(frame4, height=9, width=52, wrap="word",
                          background=theme.COL_FIELD,
                          foreground=theme.COL_TEXT, relief="flat",
                          padx=10, pady=8)
        summary.pack(fill="both", expand=True)
        summary.configure(state="disabled")

        frames = (frame1, frame2, frame3, frame4)
        state = {"step": 0}

        def _collect(step: int) -> List[str]:
            """Vuelca el formulario del paso en data y da errores."""
            if step == 0:
                values = {
                    "new_level": level_combo.get() == wiz.NUEVO_NIVEL,
                    "level_ref": ("" if level_combo.get()
                                  == wiz.NUEVO_NIVEL
                                  else level_combo.get()),
                    "new_level_name": new_level_name.get(),
                    "new_level_elevation_m": new_level_elev.get(),
                    "name": name_entry.get(),
                    "space_type": type_entry.get(),
                }
            elif step == 1:
                values = {"x0_m": x0_entry.get(), "y0_m": y0_entry.get(),
                          "width_m": width_entry.get(),
                          "depth_m": depth_entry.get(),
                          "thickness_m": thick_entry.get()}
            else:
                values = {"with_door": door_var.get(),
                          "door_width_m": door_w.get(),
                          "door_height_m": door_h.get(),
                          "door_side": door_side.get(),
                          "with_window": window_var.get(),
                          "window_width_m": win_w.get(),
                          "window_height_m": win_h.get(),
                          "window_sill_m": win_sill.get(),
                          "window_side": win_side.get()}
            return wiz.data_from_values(step, values, data)

        def _show(step: int) -> None:
            state["step"] = step
            title, subtitle = WIZARD_STEPS[step][1], WIZARD_STEPS[step][2]
            step_var.set(f"Paso {step + 1} de {len(frames)} · {title} — "
                         f"{subtitle}")
            for index, frame in enumerate(frames):
                frame.pack_forget()
                if index == step:
                    frame.pack(fill="both", expand=True)
            back_btn.configure(
                state="normal" if step > 0 else "disabled")
            next_btn.configure(
                text="Crear local ✨" if step == len(frames) - 1
                else "Siguiente ›")
            if step == len(frames) - 1:
                summary.configure(state="normal")
                summary.delete("1.0", "end")
                summary.insert("1.0", wiz.step_summary(data))
                summary.configure(state="disabled")

        def _go_next() -> None:
            errors = _collect(state["step"]) + \
                wiz.validate_step(state["step"], data)
            if errors:
                messagebox.showwarning(
                    "Asistente de diseño",
                    "Antes de continuar, revisa esto:\n\n"
                    + "\n".join(f"· {e}" for e in errors), parent=dialog)
                return
            if state["step"] < len(frames) - 1:
                _show(state["step"] + 1)
            else:
                _create()

        def _go_back() -> None:
            if state["step"] > 0:
                _collect(state["step"])  # no perder lo tecleado
                _show(state["step"] - 1)

        def _create() -> None:
            try:
                created = wiz.apply_plan(data, self.ctx)
            except Exception as exc:  # noqa: BLE001 - mensaje amable
                messagebox.showerror("Asistente de diseño",
                                     f"No pude crear el local:\n{exc}",
                                     parent=dialog)
                return
            dialog.destroy()
            self.refresh_all(fit=True)
            parts = [f"Local «{created['local_name']}» creado con "
                     f"{len(created['walls'])} muros"]
            if created.get("door"):
                parts.append("puerta")
            if created.get("window"):
                parts.append("ventana")
            inst = created.get("instalaciones") or {}
            if inst.get("equipos"):
                parts.append(f"quedó conectado a {inst['redes']} red(es) "
                             f"de instalaciones ({inst['equipos']} equipos "
                             f"y {inst['tramos']} tramos)")
            self._say(f"{' y '.join(parts) if len(parts) > 1 else parts[0]}.",
                      "Ya está en el plano: haz clic sobre él para ver "
                      "sus datos, o vuelve a abrir el asistente para "
                      "añadir otro local")

        back_btn = ttk.Button(footer, text="‹ Atrás", command=_go_back)
        back_btn.pack(side="left")
        ttk.Button(footer, text="Cancelar",
                   command=dialog.destroy).pack(side="right")
        next_btn = ttk.Button(footer, text="Siguiente ›",
                              style="Accent.TButton", command=_go_next)
        next_btn.pack(side="right", padx=(0, 10))

        # Ganchos para pruebas y accesibilidad: widgets y funciones del
        # asistente expuestos en el Toplevel.
        dialog._wiz_widgets = {
            "level_combo": level_combo, "new_level_name": new_level_name,
            "new_level_elev": new_level_elev, "name": name_entry,
            "space_type": type_entry, "x0": x0_entry, "y0": y0_entry,
            "width": width_entry, "depth": depth_entry,
            "thickness": thick_entry, "door_width": door_w,
            "door_height": door_h, "door_side": door_side,
            "window_width": win_w, "window_height": win_h,
            "window_sill": win_sill, "window_side": win_side,
            "door_var": door_var, "window_var": window_var,
            "next_btn": next_btn, "back_btn": back_btn,
            "summary": summary,
        }
        dialog._wiz_state = state
        dialog._wiz_data = data
        dialog._wiz_step_var = step_var
        dialog._wiz_next = _go_next
        dialog._wiz_back = _go_back
        dialog._wiz_show = _show

        _sync_new_level()
        _show(0)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    # -- asistente de EDIFICACIÓN completa (v1.8.0) ----------------------
    # -- catálogo PRECONS III (v1.9.0) -------------------------------------
    CATALOGO_RULESET = "precons_iii_rospres_330"

    def _catalogo_ruleset(self) -> Any:
        """Ruleset del catálogo completo, cargado una sola vez (cache)."""
        cached = getattr(self, "_catalog_ruleset", None)
        if cached is not None:
            return cached
        from app.paths import resource_path
        from engines.precons_engine import PreconsRuleset
        ruleset = PreconsRuleset.from_file(
            resource_path("rulesets", f"{self.CATALOGO_RULESET}.json"))
        self._catalog_ruleset = ruleset
        return ruleset

    def open_catalogo_precons(self) -> None:
        """Navegador del catálogo PRECONS III: búsqueda por sección o
        texto y precio oficial CUP con desglose por categoría.

        El diálogo queda en ``self._catalogo_dialog`` con ganchos
        ``_cat_*`` para pruebas. El catálogo se parsea una vez y queda
        en cache (15981 renglones)."""
        dialog = tk.Toplevel(self)
        dialog.title("Catálogo PRECONS III — precios oficiales (CUP)")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "catalogo")
        self._catalogo_dialog = dialog

        header = ttk.Frame(dialog, style="Panel.TFrame", padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Catálogo PRECONS III — 15981 renglones "
                               "oficiales",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(header,
                  text="Busca por código o descripción (sin acentos), "
                       "elige una sección y toca un renglón para ver su "
                       "precio oficial con desglose de materiales, mano "
                       "de obra y equipos.",
                  style="Dim.TLabel", wraplength=700,
                  justify="left").pack(anchor="w", pady=(2, 0))

        toolbar = ttk.Frame(dialog, padding=(14, 6))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Sección:").pack(side="left")
        section_combo = ttk.Combobox(toolbar, state="readonly", width=44)
        section_combo.pack(side="left", padx=(6, 12))
        self._tip(section_combo, "cat_section")
        ttk.Label(toolbar, text="Buscar:").pack(side="left")
        search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=search_var, width=28)
        search_entry.pack(side="left", padx=(6, 8))
        self._tip(search_entry, "cat_search")
        count_var = tk.StringVar(value="Cargando catálogo…")
        ttk.Label(toolbar, textvariable=count_var,
                  style="Dim.TLabel").pack(side="left", padx=(8, 0))

        columns = ("code", "name", "unit", "total")
        tree = ttk.Treeview(dialog, columns=columns, show="headings",
                            height=16)
        for col, text, width, anchor in (
                ("code", "Código", 92, "w"),
                ("name", "Descripción", 520, "w"),
                ("unit", "Unidad", 70, "center"),
                ("total", "Precio CUP", 110, "e")):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor=anchor)
        tree.pack(fill="both", expand=True, padx=14, pady=(4, 4))
        self._tip(tree, "cat_results")

        detail = ttk.Frame(dialog, style="Panel.TFrame", padding=(14, 8))
        detail.pack(fill="x")
        detail_var = tk.StringVar(
            value="Selecciona un renglón para ver su desglose oficial.")
        ttk.Label(detail, textvariable=detail_var, wraplength=680,
                  justify="left").pack(side="left", fill="x", expand=True)
        qty_frame = ttk.Frame(detail)
        qty_frame.pack(side="right")
        ttk.Label(qty_frame, text="Cantidad:").pack(side="left")
        qty_var = tk.StringVar(value="1")
        qty_entry = ttk.Entry(qty_frame, textvariable=qty_var, width=9)
        qty_entry.pack(side="left", padx=4)
        self._tip(qty_entry, "cat_qty")
        total_var = tk.StringVar(value="")
        ttk.Label(qty_frame, textvariable=total_var,
                  style="Accent.TLabel").pack(side="left", padx=(4, 8))
        add_btn = ttk.Button(qty_frame, text="Añadir al presupuesto →",
                             command=lambda: self._cat_add())
        add_btn.pack(side="left")
        self._tip(add_btn, "cat_add_budget")

        # ganchos para pruebas (contrato test_103)
        self._cat_section = section_combo
        self._cat_search = search_entry
        self._cat_tree = tree
        self._cat_count = count_var
        self._cat_detail = detail_var
        self._cat_qty = qty_var
        self._cat_qty_entry = qty_entry
        self._cat_total = total_var

        def _fill_sections() -> None:
            ruleset = self._catalogo_ruleset()
            sections = ruleset.sections()
            values = ["(Todas las secciones)"] + \
                [f"{s['code']} — {s['name']}" for s in sections]
            section_combo["values"] = values
            section_combo.current(0)

        def _section_code() -> str:
            value = section_combo.get()
            return value.split(" — ")[0].strip() \
                if " — " in value else ""

        def _apply_qty(price_total: float) -> None:
            try:
                quantity = float(str(qty_var.get()).replace(",", "."))
            except ValueError:
                total_var.set("")
                return
            amount = f"{price_total * quantity:,.2f}".replace(",", "@") \
                .replace(".", ",").replace("@", " ")
            total_var.set(f"= {amount} CUP")

        def _show_detail(_event=None) -> None:
            selection = tree.selection()
            if not selection:
                return
            code = selection[0]
            try:
                ruleset = self._catalogo_ruleset()
                price = ruleset.official_price(code)
                item = ruleset.item(code)
            except Exception:  # noqa: BLE001 — renglón fuera del catálogo
                return
            line = (f"{code} — {item.get('name', '')} "
                    f"[{item.get('unit', '')}]\n"
                    f"Materiales {price['material']:.2f} · Mano de obra "
                    f"{price['labor']:.2f} · Equipos "
                    f"{price['equipment']:.2f} · Unitario oficial "
                    f"{price['total']:.2f} {price['currency']}")
            detail_var.set(line)
            _apply_qty(price["total"])

        def _do_search(_event=None) -> None:
            ruleset = self._catalogo_ruleset()
            section = _section_code()
            rows = ruleset.search(search_var.get(), section=section,
                                  limit=200)
            children = tree.get_children()
            if children:
                tree.delete(*children)
            for item in rows:
                price_cell = f"{item.get('price_ref', 0.0):,.2f}" \
                    .replace(",", "@").replace(".", ",") \
                    .replace("@", " ")
                tree.insert("", "end", iid=item["code"], values=(
                    item["code"], item.get("name", ""),
                    item.get("unit", ""), price_cell))
            total = len(ruleset.search(search_var.get(), section=section,
                                       limit=len(ruleset.work_items)))
            count_var.set(f"{total} coincidencias — mostrando {len(rows)}")
            if not rows:
                detail_var.set("Sin resultados: prueba otra palabra o "
                               "la sección «(Todas las secciones)».")

        search_entry.bind("<Return>", _do_search)
        tree.bind("<<TreeviewSelect>>", _show_detail)
        qty_entry.bind("<Return>", lambda _e: _show_detail())
        # ganchos para pruebas (contrato test_103)
        self._cat_run_search = _do_search
        self._cat_show_detail = _show_detail

        def _add_selection_to_budget() -> None:
            selection = tree.selection()
            if not selection:
                detail_var.set("Selecciona primero un renglón del "
                               "catálogo para añadirlo.")
                return
            try:
                quantity = float(str(qty_var.get()).replace(",", "."))
            except ValueError:
                quantity = 1.0
            self.add_to_presupuesto(selection[0], quantity)
            if hasattr(self, "_presupuesto_dialog") and \
                    self._presupuesto_dialog.winfo_exists():
                self._presupuesto_refresh()
            detail_var.set(f"Renglón {selection[0]} añadido al "
                           "presupuesto (Herramientas → Presupuesto "
                           "con catálogo PRECONS III).")

        self._cat_add = _add_selection_to_budget
        self._cat_add_btn = add_btn

        def _load() -> None:
            try:
                _fill_sections()
                _do_search()
                self._say("Catálogo PRECONS III cargado: 15981 renglones "
                          "oficiales. Busca y toca un renglón para ver "
                          "su precio.")
            except Exception as exc:  # noqa: BLE001 — catálogo ausente
                count_var.set("Catálogo no disponible")
                detail_var.set(f"No se pudo cargar el catálogo: {exc}")

        dialog.after(40, _load)

    # -- biblioteca de detalles constructivos (v3.5.0) ---------------------
    def open_detalles(self, tipologia: str = "") -> None:
        """Navegador de la biblioteca de detalles constructivos por
        ediciones regionales: filtra por edición, categoría, texto y
        TIPOLOGÍA CONSTRUCTIVA del asistente (v3.6.0); muestra la ficha
        con el corte por capas y exporta el esquema acotado del detalle
        en SVG, PNG y PDF.

        El diálogo queda en ``self._det_dialog`` con ganchos ``_det_*``
        y cierres ``_det_run_search`` / ``_det_show`` / ``_det_export``
        (+ ``_det_export_png`` / ``_det_export_pdf``; contrato de
        pruebas de test_122 y test_123)."""
        from domain.detalles import (CATEGORIA_NOMBRE, get_registry,
                                     sin_acentos, tipologias)
        registry = get_registry()

        dialog = tk.Toplevel(self)
        dialog.title("Biblioteca de detalles constructivos")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "detalles")
        self._det_dialog = dialog

        header = ttk.Frame(dialog, style="Panel.TFrame", padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Biblioteca de detalles constructivos",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(header,
                  text="El corte que explica cómo se construye el muro, "
                       "la losa o la cubierta: capas, espesores, "
                       "materiales y norma. Elige la edición regional "
                       "de tu obra y la tipología constructiva de tu "
                       "edificio; toca un detalle para ver su ficha y "
                       "exporta el esquema acotado en SVG, PNG o PDF.",
                  style="Dim.TLabel", wraplength=760,
                  justify="left").pack(anchor="w", pady=(2, 0))

        toolbar = ttk.Frame(dialog, padding=(14, 6))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Edición:").pack(side="left")
        region_combo = ttk.Combobox(toolbar, state="readonly", width=32)
        region_combo.pack(side="left", padx=(6, 12))
        self._tip(region_combo, "det_region")
        ttk.Label(toolbar, text="Categoría:").pack(side="left")
        cat_combo = ttk.Combobox(toolbar, state="readonly", width=24)
        cat_combo.pack(side="left", padx=(6, 12))
        self._tip(cat_combo, "det_cat")
        ttk.Label(toolbar, text="Buscar:").pack(side="left")
        search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=search_var,
                                 width=24)
        search_entry.pack(side="left", padx=(6, 8))
        self._tip(search_entry, "det_search")
        ttk.Label(toolbar, text="Tipología:").pack(side="left")
        tip_combo = ttk.Combobox(toolbar, state="readonly", width=36)
        tip_combo.pack(side="left", padx=(6, 12))
        self._tip(tip_combo, "det_tipo")
        count_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=count_var,
                  style="Dim.TLabel").pack(side="left", padx=(8, 0))

        columns = ("id", "categoria", "nombre", "espesor")
        tree = ttk.Treeview(dialog, columns=columns, show="headings",
                            height=10)
        for col, text, width, anchor in (
                ("id", "Id", 250, "w"),
                ("categoria", "Categoría", 120, "w"),
                ("nombre", "Detalle", 400, "w"),
                ("espesor", "Espesor", 90, "e")):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor=anchor)
        tree.pack(fill="both", expand=True, padx=14, pady=(4, 4))
        self._tip(tree, "det_tree")

        detail = ttk.Frame(dialog, padding=(14, 6))
        detail.pack(fill="both", expand=True)
        text = tk.Text(detail, height=9, wrap="word", relief="flat",
                       background=theme.COL_BG_ALT,
                       foreground=theme.COL_TEXT)
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", "Selecciona un detalle para ver su ficha "
                           "completa.")
        text.configure(state="disabled")
        self._tip(text, "det_text")
        actions = ttk.Frame(detail)
        actions.pack(side="right", fill="y", padx=(10, 0))
        btn_svg = ttk.Button(actions, text="⤓ SVG",
                             command=lambda: _export("svg"))
        btn_svg.pack(anchor="n")
        self._tip(btn_svg, "det_svg")
        btn_png = ttk.Button(actions, text="⤓ PNG",
                             command=lambda: _export("png"))
        btn_png.pack(anchor="n", pady=(6, 0))
        self._tip(btn_png, "det_png")
        btn_pdf = ttk.Button(actions, text="⤓ PDF",
                             command=lambda: _export("pdf"))
        btn_pdf.pack(anchor="n", pady=(6, 0))
        self._tip(btn_pdf, "det_pdf")

        # ganchos para pruebas (contrato test_122 / test_123)
        self._det_region = region_combo
        self._det_cat = cat_combo
        self._det_search = search_entry
        self._det_tipologia = tip_combo
        self._det_tree = tree
        self._det_count = count_var
        self._det_text = text
        self._det_registry = registry

        region_values = ["Base (biblioteca universal)"]
        codes = ["base"]
        for info in registry.available_regions():
            label = (f"{info['nombre']} — {info['edicion']}"
                     if info["edicion"] else info["nombre"])
            region_values.append(label)
            codes.append(info["codigo"])
        region_combo["values"] = region_values
        region_combo.current(0)
        self._det_codes = codes

        tip_values = ["(Todas las tipologías)"] + list(tipologias())
        tip_combo["values"] = tip_values
        tip_combo.current(0)

        def _tipologia_code() -> str:
            value = tip_combo.get()
            if not value or value.startswith("("):
                return ""
            return value

        def _region_code() -> str:
            index = region_combo.current()
            return codes[index] if 0 <= index < len(codes) else "base"

        def _categoria_code() -> str:
            value = cat_combo.get()
            if not value or value.startswith("("):
                return ""
            for code, nombre in CATEGORIA_NOMBRE.items():
                if nombre == value:
                    return code
            return ""

        def _run_search(_event=None) -> None:
            registry.set_region(_region_code())
            cat_values = ["(Todas las categorías)"] + [
                CATEGORIA_NOMBRE[c] for c in registry.categories()]
            cat_combo["values"] = cat_values
            if cat_combo.current() < 0:
                cat_combo.current(0)
            tipo = _tipologia_code()
            recomendados = None
            if tipo:
                from domain.detalles import detalles_para_tipologia
                recomendados = [d.id for d in detalles_para_tipologia(
                    registry, tipo)]
            rows = registry.list_details(
                categoria=_categoria_code(), texto=search_var.get(),
                ids=recomendados)
            children = tree.get_children()
            if children:
                tree.delete(*children)
            for item in rows:
                espesor = (f"{item.espesor_total_mm:g} mm"
                           if float(item.espesor_total_mm).is_integer()
                           else f"{item.espesor_total_mm:.1f} mm")
                tree.insert("", "end", iid=item.id, values=(
                    item.id, CATEGORIA_NOMBRE.get(item.categoria,
                                                  item.categoria),
                    item.nombre + (" *" if item.regional else ""),
                    espesor))
            if tipo:
                count_var.set(
                    f"{len(rows)} recomendados para «{tipo}»"
                    f"{registry.region_tag()} — limpia el filtro "
                    f"para ver toda la edición")
            else:
                count_var.set(
                    f"{len(rows)} detalles{registry.region_tag()}"
                    f" — los * son de la edición regional")
            if not rows:
                text.configure(state="normal")
                text.delete("1.0", "end")
                texto = ("Sin recomendados para esa tipología, "
                         "categoría y búsqueda: prueba a limpiar el "
                         "filtro de tipología."
                         if tipo else
                         "Sin resultados: prueba otra palabra o "
                         "todas las categorías.")
                text.insert("1.0", texto)
                text.configure(state="disabled")

        def _show_detail(_event=None) -> None:
            selection = tree.selection()
            if not selection:
                return
            item = registry.get(selection[0])
            if item is None:
                return
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", item.ficha())
            text.configure(state="disabled")

        def _export(fmt: str) -> None:
            """Exporta el detalle elegido en svg|png|pdf (v3.6.0)."""
            selection = tree.selection()
            if not selection:
                messagebox.showinfo(
                    "Exportar detalle",
                    "Selecciona primero un detalle de la lista.",
                    parent=dialog)
                return
            item = registry.get(selection[0])
            if item is None:
                return
            specs = {
                "svg": ("Esquema SVG", "*.svg"),
                "png": ("PNG imagen", "*.png"),
                "pdf": ("PDF imprimible", "*.pdf"),
            }
            desc, pattern = specs.get(fmt, specs["svg"])
            default = item.id.replace("/", "_").replace(os.sep, "_")
            path = filedialog.asksaveasfilename(
                parent=dialog, defaultextension=f".{fmt}",
                initialfile=f"{default}.{fmt}",
                filetypes=[(desc, pattern),
                           ("Todos los archivos", "*.*")])
            if not path:
                return
            try:
                from exporters.detalle_export import export_detalle
                export_detalle(item, path,
                               region_label=registry.region_name)
            except Exception as exc:  # noqa: BLE001 — aviso amable
                messagebox.showerror(
                    "Exportar detalle",
                    f"No se pudo exportar el esquema {fmt.upper()}:\n"
                    f"{exc}",
                    parent=dialog)
                return
            self._say(f"Esquema {fmt.upper()} del detalle "
                      f"«{item.nombre}» generado: {path}")

        self._det_run_search = _run_search
        self._det_show = _show_detail
        self._det_export = lambda: _export("svg")
        self._det_export_png = lambda: _export("png")
        self._det_export_pdf = lambda: _export("pdf")

        search_entry.bind("<Return>", _run_search)
        tree.bind("<<TreeviewSelect>>", _show_detail)
        region_combo.bind("<<ComboboxSelected>>",
                          lambda _e: (_run_search(), _show_detail()))
        cat_combo.bind("<<ComboboxSelected>>", _run_search)
        tip_combo.bind("<<ComboboxSelected>>", _run_search)
        # tipología pedida desde el asistente de edificación (v3.6.0)
        if tipologia:
            wanted = sin_acentos(tipologia)
            for index, value in enumerate(tip_values[1:], 1):
                if sin_acentos(value) == wanted:
                    tip_combo.current(index)
                    break
            else:
                try:
                    from domain.detalles import buscar_tipologia
                    resuelta = buscar_tipologia(tipologia)
                except ValueError:
                    resuelta = ""
                if resuelta and resuelta in tip_values:
                    tip_combo.current(tip_values.index(resuelta))
        _run_search()

    # -- presupuesto PRECONS III (v2.0.0) ---------------------------------
    def _presupuesto_service(self):
        """Servicio de presupuesto con el catálogo completo (cache)."""
        cached = getattr(self, "_presupuesto_svc", None)
        if cached is not None:
            return cached
        from services.precons_budget_service import PreconsBudgetService
        service = PreconsBudgetService(self.ctx)
        try:
            service.ruleset = self._catalogo_ruleset()
        except Exception:  # noqa: BLE001 — catálogo ausente
            service.load_ruleset()
        self._presupuesto_svc = service
        return service

    def add_to_presupuesto(self, item_code: str, quantity: float) -> None:
        """Añade un renglón del catálogo al presupuesto del proyecto."""
        service = self._presupuesto_service()
        view = service.add_item(item_code, quantity)
        self._say(f"Renglón {view['code']} añadido al presupuesto "
                  f"({view['quantity']:g} {view['unit']} = "
                  f"{view['amount']:,.2f} CUP).",
                  "Ábrelo desde Herramientas → Presupuesto con catálogo "
                  "PRECONS III para ajustar cantidades y exportar.")

    def _comparar_variantes(self, state: Dict[str, Any],
                            parent: Any = None) -> None:
        """Matriz comparativa de las variantes generadas (v3.29.0).

        Reutiliza el takeoff PRECONS vivo (``variant.cost``) ya
        adjuntado: puntos, área, coste y coste/m2 de CADA variante en
        una sola tabla, con export CSV (utf-8-sig, «;») para Excel.
        Sólo lectura: comparar no toca la geometría ni el proyecto.
        """
        variantes = state.get("variants") or []
        padre = parent or self
        if not variantes:
            messagebox.showinfo(
                "Comparar variantes",
                "Aún no hay variantes que comparar: pulsa primero "
                "«Generar variantes de planta».", parent=padre)
            return
        tabla = vbudget.tabla_comparacion_variantes(variantes)
        dialog = tk.Toplevel(padre)
        dialog.title("Comparación de variantes de planta")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(padre)
        self._prepare_dialog(dialog, "comparar_variantes")
        self._comparar_dialogo = dialog
        dialog._comparar_state = state
        cabecera = ttk.Frame(dialog, style="Panel.TFrame",
                             padding=(14, 10))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text=f"{len(variantes)} variantes de planta",
                  style="Title.TLabel").pack(anchor="w")
        mejores = tabla["mejores"]
        texto_resumen = "Mejor puntuación: " + \
            (mejores["puntos"] or "—")
        if mejores["con_coste"]:
            texto_resumen += "   ·   Menor coste/m2: " \
                + mejores["coste_m2"]
        else:
            texto_resumen += \
                "   ·   (sin coste adjunto todavía)"
        ttk.Label(cabecera, style="Accent.TLabel",
                  text=texto_resumen).pack(anchor="w", pady=(2, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        columnas = tabla["columnas"]
        tree = ttk.Treeview(cuerpo, show="headings", height=12,
                            columns=columnas)
        anchos = {"#": 34, "Variante": 300, "Esquema": 110,
                  "Cabe en lote": 90, "Puntos": 60, "Área m2": 90,
                  "Coste": 110, "Coste/m2": 100, "Avisos": 60}
        for col in columnas:
            tree.heading(col, text=col)
            tree.column(col, width=anchos.get(col, 80), anchor="w")
        tree.pack(fill="both", expand=True)
        for indice in tabla["orden"]:  # mejor puntuada arriba
            tree.insert("", "end", values=tabla["filas"][indice - 1])
        self._tip(tree, "cmp_variants")
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")

        def _guardar_csv() -> None:
            destino = filedialog.asksaveasfilename(
                title="Guardar comparación CSV",
                defaultextension=".csv",
                initialfile="comparacion_variantes.csv",
                filetypes=[("CSV (Excel)", "*.csv"),
                           ("Todos los archivos", "*.*")],
                parent=dialog)
            if not destino:
                return
            try:
                with open(destino, "w", encoding="utf-8-sig",
                          newline="") as fh:
                    fh.write(
                        vbudget.csv_comparacion_variantes(variantes))
            except OSError as exc:
                messagebox.showerror(
                    "Comparar variantes",
                    f"No pude escribir el CSV:\n\n{exc}",
                    parent=dialog)
                return
            messagebox.showinfo(
                "Comparar variantes",
                "Comparación escrita:\n\n" + destino, parent=dialog)
            self._say("Comparación de variantes exportada: " + destino)

        self._tip(ttk.Button(botones, text="Guardar CSV...",
                             command=_guardar_csv),
                  "cmp_variants_csv").pack(side="left")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        self._say("Comparación lista: puntos, área, coste PRECONS y "
                  "avisos de cada variante, mejor puntuada arriba.")

    def _variantes_costear(self, data: Any, variantes: Sequence[Any],
                           calidad: str) -> bool:
        """Adjunta la estimación PRECONS viva a cada variante (v3.12.0).

        Silenciosa y a prueba de catálogos ausentes: si el catálogo no
        puede cargarse (o la estimación falla por cualquier motivo),
        las variantes quedan sin coste y la GUI muestra «—» sin
        romper nada. Devuelve True si el coste quedó adjunto.
        """
        try:
            ruleset = self._catalogo_ruleset()
        except Exception:  # noqa: BLE001 — catálogo ausente o corrupto
            return False
        try:
            vbudget.attach_costs(data, variantes, ruleset, calidad)
        except Exception:  # noqa: BLE001 — estimar nunca bloquea
            return False
        return True

    def open_presupuesto_precons(self) -> None:
        """Presupuesto por catálogo PRECONS III: renglones oficiales,
        cantidades editables, totales con coeficientes y exportación
        CSV / PDF / gráfico PNG.

        El diálogo queda en ``self._presupuesto_dialog`` con ganchos
        ``_pb_*`` para pruebas."""
        service = self._presupuesto_service()
        dialog = tk.Toplevel(self)
        dialog.title("Presupuesto con catálogo PRECONS III (CUP)")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "presupuesto")
        self._presupuesto_dialog = dialog

        header = ttk.Frame(dialog, style="Panel.TFrame", padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Presupuesto con precios oficiales "
                               "PRECONS III",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(header,
                  text="Añade renglones desde el catálogo (botón "
                       "«Añadir al presupuesto»), ajusta cantidades "
                       "doble-tocando la fila y exporta el resultado a "
                       "CSV, PDF o un gráfico PNG.",
                  style="Dim.TLabel", wraplength=720,
                  justify="left").pack(anchor="w", pady=(2, 0))

        toolbar = ttk.Frame(dialog, padding=(14, 6))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Código:").pack(side="left")
        code_var = tk.StringVar()
        code_entry = ttk.Entry(toolbar, textvariable=code_var, width=12)
        code_entry.pack(side="left", padx=(6, 4))
        ttk.Label(toolbar, text="Cantidad:").pack(side="left")
        qty_var = tk.StringVar(value="1")
        qty_entry = ttk.Entry(toolbar, textvariable=qty_var, width=9)
        qty_entry.pack(side="left", padx=(6, 8))
        btn_add = ttk.Button(toolbar, text="Añadir",
                             command=lambda: _do_add())
        btn_add.pack(side="left")
        btn_set = ttk.Button(toolbar, text="Fijar cantidad",
                             command=lambda: _do_set_qty())
        btn_set.pack(side="left", padx=(6, 0))
        btn_remove = ttk.Button(toolbar, text="Quitar",
                                command=lambda: _do_remove())
        btn_remove.pack(side="left", padx=(6, 0))
        btn_clear = ttk.Button(toolbar, text="Vaciar",
                               command=lambda: _do_clear())
        btn_clear.pack(side="left", padx=(6, 0))
        status_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=status_var,
                  style="Dim.TLabel").pack(side="left", padx=(10, 0))

        columns = ("code", "name", "unit", "qty", "price", "amount")
        tree = ttk.Treeview(dialog, columns=columns, show="headings",
                            height=15)
        for col, text, width, anchor in (
                ("code", "Código", 92, "w"),
                ("name", "Descripción", 470, "w"),
                ("unit", "Ud", 52, "center"),
                ("qty", "Cantidad", 90, "e"),
                ("price", "P. unitario", 110, "e"),
                ("amount", "Importe", 120, "e")):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor=anchor)
        tree.pack(fill="both", expand=True, padx=14, pady=(2, 2))
        self._tip(tree, "pb_tree")

        totals_frame = ttk.Frame(dialog, style="Panel.TFrame",
                                 padding=(14, 8))
        totals_frame.pack(fill="x")
        direct_var = tk.StringVar(value="Directo: —")
        transport_var = tk.StringVar(value="Transporte: —")
        indirect_var = tk.StringVar(value="Indirectos: —")
        benefit_var = tk.StringVar(value="Beneficio: —")
        total_var = tk.StringVar(value="TOTAL: —")
        ttk.Label(totals_frame, textvariable=direct_var).pack(
            side="left", padx=(0, 12))
        ttk.Label(totals_frame, textvariable=transport_var).pack(
            side="left", padx=(0, 12))
        ttk.Label(totals_frame, textvariable=indirect_var).pack(
            side="left", padx=(0, 12))
        ttk.Label(totals_frame, textvariable=benefit_var).pack(
            side="left", padx=(0, 12))
        ttk.Label(totals_frame, textvariable=total_var,
                  style="Accent.TLabel").pack(side="right")

        footer = ttk.Frame(dialog, padding=(14, 6))
        footer.pack(fill="x")
        ttk.Label(footer,
                  text="Exportar:", style="Dim.TLabel").pack(side="left")
        for text, handler in (
                ("CSV…", lambda: _export_csv()),
                ("PDF…", lambda: _export_pdf()),
                ("Gráfico PNG…", lambda: _export_png())):
            ttk.Button(footer, text=text, command=handler).pack(
                side="left", padx=(6, 0))

        # ganchos para pruebas
        self._pb_tree = tree
        self._pb_status = status_var
        self._pb_totals = (direct_var, transport_var, indirect_var,
                           benefit_var, total_var)
        self._pb_code = code_entry
        self._pb_qty = qty_entry

        def _fmt(value: float) -> str:
            return f"{value:,.2f}".replace(",", "@").replace(".", ",") \
                .replace("@", " ")

        def _refresh() -> None:
            try:
                data = service.tree()
            except Exception as exc:  # noqa: BLE001
                status_var.set(f"Catálogo no disponible: {exc}")
                return
            children = tree.get_children()
            if children:
                tree.delete(*children)
            for chapter in data.get("chapters", []):
                for item in chapter.get("items", []):
                    tree.insert("", "end", iid=item["code"], values=(
                        item["code"], item["description"], item["unit"],
                        f"{item['quantity']:g}", _fmt(item["unit_price"]),
                        _fmt(item["amount"])))
            direct_var.set(f"Directo: {_fmt(data.get('direct', 0.0))} CUP")
            transport_var.set(
                f"Transporte: {_fmt(data.get('transport', 0.0))} CUP")
            indirect_var.set(
                f"Indirectos: {_fmt(data.get('indirect', 0.0))} CUP")
            benefit_var.set(
                f"Beneficio: {_fmt(data.get('benefit', 0.0))} CUP")
            total_var.set(f"TOTAL: {_fmt(data.get('total', 0.0))} CUP")
            count = sum(len(c.get("items", []))
                        for c in data.get("chapters", []))
            status_var.set(f"{count} renglones · "
                           f"{len(data.get('chapters', []))} secciones")

        self._presupuesto_refresh = _refresh

        def _parse_qty() -> float:
            try:
                return float(str(qty_var.get()).replace(",", "."))
            except ValueError:
                return 1.0

        def _do_add() -> None:
            code = code_var.get().strip()
            if not code:
                status_var.set("Escribe el código del renglón del "
                               "catálogo (p. ej. 011111).")
                return
            try:
                service.add_item(code, _parse_qty())
                _refresh()
                status_var.set(f"Renglón {code} añadido.")
            except Exception as exc:  # noqa: BLE001
                status_var.set(f"No se pudo añadir {code}: {exc}")

        def _do_set_qty() -> None:
            selection = tree.selection()
            code = code_var.get().strip() or \
                (selection[0] if selection else "")
            if not code:
                status_var.set("Selecciona una fila o escribe el código.")
                return
            try:
                service.set_quantity(code, _parse_qty())
                _refresh()
                status_var.set(f"Cantidad de {code} actualizada.")
            except Exception as exc:  # noqa: BLE001
                status_var.set(f"No se pudo actualizar {code}: {exc}")

        def _do_remove() -> None:
            selection = tree.selection()
            code = code_var.get().strip() or \
                (selection[0] if selection else "")
            if not code:
                status_var.set("Selecciona la fila a quitar.")
                return
            try:
                service.remove_item(code)
                _refresh()
                status_var.set(f"Renglón {code} quitado.")
            except Exception as exc:  # noqa: BLE001
                status_var.set(f"No se pudo quitar {code}: {exc}")

        def _do_clear() -> None:
            if messagebox.askyesno(
                    "Vaciar presupuesto",
                    "¿Quitar todos los renglones del presupuesto?"):
                service.clear()
                _refresh()
                status_var.set("Presupuesto vaciado.")

        def _export_csv() -> None:
            path = filedialog.asksaveasfilename(
                title="Exportar presupuesto CSV", defaultextension=".csv")
            if not path:
                return
            service.save_csv(path)
            self._say(f"Presupuesto exportado a CSV: "
                      f"{os.path.basename(path)}.")

        def _export_pdf() -> None:
            path = filedialog.asksaveasfilename(
                title="Exportar presupuesto PDF", defaultextension=".pdf")
            if not path:
                return
            from exporters.pdf_exporter import export_budget_pdf
            export_budget_pdf(service.tree(), path, self.ctx.project.name)
            self._say(f"Presupuesto exportado a PDF: "
                      f"{os.path.basename(path)}.",
                      "El PDF incluye desglose por secciones y el "
                      "resumen con coeficientes.")

        def _export_png() -> None:
            path = filedialog.asksaveasfilename(
                title="Exportar gráfico del presupuesto (PNG)",
                defaultextension=".png")
            if not path:
                return
            from exporters.png_exporter import export_budget_chart_png
            export_budget_chart_png(service.tree(), path,
                                    self.ctx.project.name)
            self._say(f"Gráfico exportado: {os.path.basename(path)}.",
                      "Barras por sección del catálogo con importes "
                      "oficiales.")

        tree.bind("<Double-1>", lambda _e: _do_set_qty())
        dialog.after(60, _refresh)

    # -- asistente de importación §94 (v2.0.0, brecha #2) ------------------
    def open_importar_catalogo(self) -> None:
        """Asistente para importar catálogos de precios externos
        (.xlsx/.csv/.json, spec §94) e instalarlos como rulesets.

        El diálogo queda en ``self._importar_dialog`` con ganchos
        ``_imp_*`` para pruebas."""
        dialog = tk.Toplevel(self)
        dialog.title("Importar catálogo de precios (§94)")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "importar_catalogo")
        self._importar_dialog = dialog

        header = ttk.Frame(dialog, style="Panel.TFrame", padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Importar un catálogo de precios",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(header,
                  text="Elige un libro Excel/CSV/JSON con hojas de "
                       "secciones, renglones y recursos. ARQ GEN "
                       "analiza las columnas, valida los datos y "
                       "instala el catálogo como un ruleset más, "
                       "listo para el presupuesto.",
                  style="Dim.TLabel", wraplength=640,
                  justify="left").pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(dialog, padding=(14, 6))
        body.pack(fill="both", expand=True)

        row_file = ttk.Frame(body)
        row_file.pack(fill="x")
        ttk.Label(row_file, text="Archivo:").pack(side="left")
        path_var = tk.StringVar()
        path_entry = ttk.Entry(row_file, textvariable=path_var)
        path_entry.pack(side="left", fill="x", expand=True, padx=6)
        self._tip(path_entry, "imp_file")
        ttk.Button(row_file, text="Examinar…",
                   command=lambda: _browse()).pack(side="left")

        row_opts = ttk.Frame(body)
        row_opts.pack(fill="x", pady=(6, 0))
        ttk.Label(row_opts, text="Código:").pack(side="left")
        code_var = tk.StringVar(value="catalogo_importado")
        code_entry = ttk.Entry(row_opts, textvariable=code_var, width=24)
        code_entry.pack(side="left", padx=(6, 12))
        ttk.Label(row_opts, text="Nombre:").pack(side="left")
        name_var = tk.StringVar(value="Catálogo importado")
        name_entry = ttk.Entry(row_opts, textvariable=name_var, width=28)
        name_entry.pack(side="left", padx=(6, 0))

        progress = ttk.Progressbar(body, mode="indeterminate")

        report = tk.Text(body, height=14, wrap="word", state="disabled",
                         background=theme.COL_BG_ALT,
                         foreground="#d8d8e0")
        report.pack(fill="both", expand=True, pady=(8, 0))

        status_var = tk.StringVar(value="Sin archivo analizado.")
        ttk.Label(body, textvariable=status_var,
                  style="Dim.TLabel").pack(anchor="w", pady=(6, 0))

        # ganchos para pruebas
        self._imp_path = path_entry
        self._imp_code = code_entry
        self._imp_name = name_entry
        self._imp_status = status_var
        self._imp_report = report
        self._imp_analyze = lambda: _analyze()
        self._imp_apply = lambda: _apply()
        self._imp_result: Dict[str, Any] = {}

        def _browse() -> None:
            path = filedialog.askopenfilename(
                title="Catálogo de precios (.xlsx/.csv/.txt/.json)",
                filetypes=[("Catálogos", "*.xlsx *.xlsm *.csv *.txt *.json"),
                           ("Todos", "*.*")])
            if path:
                path_var.set(path)

        def _show(text: str) -> None:
            report.configure(state="normal")
            report.delete("1.0", "end")
            report.insert("1.0", text)
            report.configure(state="disabled")

        def _analyze() -> None:
            from importers.catalog import CatalogImporter
            path = path_var.get().strip()
            if not path or not os.path.exists(path):
                status_var.set("Elige un archivo .xlsx/.csv/.json "
                               "existente.")
                return
            progress.pack(fill="x", pady=(8, 0))
            progress.start(12)
            status_var.set("Analizando columnas y datos…")
            holder: Dict[str, Any] = {}

            def work() -> None:
                try:
                    payload, report_data, prices = \
                        CatalogImporter().convert(path)
                    holder["ok"] = (payload, report_data, prices)
                except Exception as exc:  # noqa: BLE001
                    holder["error"] = str(exc)

            def done() -> None:
                progress.stop()
                progress.pack_forget()
                if "error" in holder:
                    status_var.set("No se pudo analizar el archivo.")
                    _show(f"ERROR\n{holder['error']}")
                    return
                _payload, report_data, prices = holder["ok"]
                self._imp_result = report_data
                counts = report_data.get("counts", {})
                summary = "\n".join(
                    f"  {key}: {value}" for key, value in counts.items())
                warnings = report_data.get("warnings", [])
                errors = report_data.get("errors", [])
                text = ("ANÁLISIS COMPLETADO\n\nConteos:\n" + summary +
                        "\n\nAvisos:\n" +
                        ("\n".join(f"  · {w}" for w in warnings)
                         if warnings else "  (ninguno)") +
                        "\n\nErrores:\n" +
                        ("\n".join(f"  ! {e}" for e in errors)
                         if errors else "  (ninguno)"))
                _show(text)
                status_var.set(
                    f"Listo para aplicar: {counts.get('work_items', 0)} "
                    f"partidas, {counts.get('resources', 0)} recursos. "
                    "Pulsa «Aplicar e instalar».")

            def poll() -> None:
                if "ok" in holder or "error" in holder:
                    done()
                else:
                    dialog.after(120, poll)

            import threading
            threading.Thread(target=work, daemon=True).start()
            dialog.after(120, poll)

        def _apply() -> None:
            from importers.catalog import CatalogImporter
            path = path_var.get().strip()
            if not path or not os.path.exists(path):
                status_var.set("Primero analiza un archivo válido.")
                return
            code = "".join(
                ch if ch.isalnum() or ch == "_" else "_"
                for ch in code_var.get().strip()) or "catalogo_importado"
            name = name_var.get().strip() or "Catálogo importado"
            from app.paths import resource_path
            out_dir = os.path.dirname(
                resource_path("rulesets", "x.json"))
            out_path = os.path.join(out_dir, f"{code}.json")
            progress.pack(fill="x", pady=(8, 0))
            progress.start(12)
            status_var.set("Aplicando e instalando el ruleset…")
            holder: Dict[str, Any] = {}

            def work() -> None:
                try:
                    CatalogImporter().apply(path, code=code, name=name,
                                            out_path=out_path)
                    holder["ok"] = out_path
                except Exception as exc:  # noqa: BLE001
                    holder["error"] = str(exc)

            def done() -> None:
                progress.stop()
                progress.pack_forget()
                if "error" in holder:
                    status_var.set("No se pudo aplicar el catálogo.")
                    _show(f"ERROR AL APLICAR\n{holder['error']}")
                    return
                _show(f"CATÁLOGO INSTALADO\n\nRuleset: {code}\n"
                      f"Archivo: {holder['ok']}\n\nYa puedes usarlo en "
                      "el catálogo, el presupuesto y la CLI "
                      "(--ruleset " + code + ").")
                status_var.set(f"Catálogo instalado como «{code}».")
                self._say(f"Catálogo «{code}» instalado.",
                          "Se puede usar en el presupuesto y con "
                          "--ruleset en la CLI.")

            def poll() -> None:
                if "ok" in holder or "error" in holder:
                    done()
                else:
                    dialog.after(120, poll)

            import threading
            threading.Thread(target=work, daemon=True).start()
            dialog.after(120, poll)

        buttons = ttk.Frame(dialog, padding=(14, 8))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Analizar archivo",
                   command=lambda: _analyze()).pack(side="left")
        ttk.Button(buttons, text="Aplicar e instalar",
                   command=lambda: _apply()).pack(side="left", padx=(8, 0))

    # -- importador de planos DXF §94 en GUI (v3.3.0, brecha #2) -----------
    def open_importar_dxf(self) -> None:
        """Asistente para importar un plano DXF o DWG (spec §94): LINE/
        LWPOLYLINE de capas de muros y locales se convierten en muros y
        espacios del proyecto abierto. Los .dwg se convierten antes a
        DXF con un conversor local (importers.dwg_reader.DwgGateway).

        Pipeline PREVIEW (analizar) → APLICAR (importar), transaccional y
        auditado. Ganchos ``_dxf_*`` para pruebas. Un modo síncrono
        (``self._dxf_sync``) facilita las pruebas automatizadas."""
        dialog = tk.Toplevel(self)
        dialog.title("Importar plano DXF/DWG (§94)")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "importar_dxf")
        self._dxf_dialog = dialog

        header = ttk.Frame(dialog, style="Panel.TFrame", padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Importar un plano DXF o DWG",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(header,
                  text="ARQ GEN lee las LINE de las capas de muros y las "
                       "LWPOLYLINE cerradas de las capas de locales, "
                       "muestra una vista previa con conteos y avisos y "
                       "crea los muros y espacios en el proyecto abierto "
                       "al nivel que indiques. Los .dwg se convierten "
                       "antes a DXF con un conversor local (ODA File "
                       "Converter o LibreDWG). Sin ezdxf instalado no se "
                       "puede leer el plano.",
                  style="Dim.TLabel", wraplength=640,
                  justify="left").pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(dialog, padding=(14, 6))
        body.pack(fill="both", expand=True)

        row_file = ttk.Frame(body)
        row_file.pack(fill="x")
        ttk.Label(row_file, text="Archivo:").pack(side="left")
        path_var = tk.StringVar()
        path_entry = ttk.Entry(row_file, textvariable=path_var)
        path_entry.pack(side="left", fill="x", expand=True, padx=6)
        self._tip(path_entry, "dxf_file")
        ttk.Button(row_file, text="Examinar…",
                   command=lambda: _browse()).pack(side="left")

        row_layers = ttk.Frame(body)
        row_layers.pack(fill="x", pady=(6, 0))
        ttk.Label(row_layers, text="Capa muros:").pack(side="left")
        walls_var = tk.StringVar()
        walls_entry = ttk.Entry(row_layers, textvariable=walls_var, width=16)
        walls_entry.pack(side="left", padx=(6, 12))
        self._tip(walls_entry, "dxf_walls")
        ttk.Label(row_layers, text="Capa locales:").pack(side="left")
        spaces_var = tk.StringVar()
        spaces_entry = ttk.Entry(row_layers, textvariable=spaces_var,
                                 width=16)
        spaces_entry.pack(side="left", padx=(6, 12))
        self._tip(spaces_entry, "dxf_spaces")
        ttk.Label(row_layers,
                  text="(vacío = detectar por nombre)").pack(side="left")

        row_conv = ttk.Frame(body)
        row_conv.pack(fill="x", pady=(6, 0))
        ttk.Label(row_conv,
                  text="Convertidor DWG:").pack(side="left")
        conv_var = tk.StringVar()
        conv_entry = ttk.Entry(row_conv, textvariable=conv_var)
        conv_entry.pack(side="left", fill="x", expand=True, padx=6)
        self._tip(conv_entry, "dxf_conv")

        row_opts = ttk.Frame(body)
        row_opts.pack(fill="x", pady=(6, 0))
        ttk.Label(row_opts, text="Espesor (m):").pack(side="left")
        thick_var = tk.StringVar(value="0.2")
        thick_entry = ttk.Entry(row_opts, textvariable=thick_var, width=8)
        thick_entry.pack(side="left", padx=(6, 12))
        self._tip(thick_entry, "dxf_thick")
        ttk.Label(row_opts, text="Nivel destino:").pack(side="left")
        level_var = tk.StringVar(value="Nivel DXF")
        level_entry = ttk.Entry(row_opts, textvariable=level_var, width=22)
        level_entry.pack(side="left", padx=(6, 0))
        self._tip(level_entry, "dxf_level")

        progress = ttk.Progressbar(body, mode="indeterminate")

        report = tk.Text(body, height=13, wrap="word", state="disabled",
                         background=theme.COL_BG_ALT,
                         foreground="#d8d8e0")
        report.pack(fill="both", expand=True, pady=(8, 0))

        status_var = tk.StringVar(value="Sin plano analizado.")
        ttk.Label(body, textvariable=status_var,
                  style="Dim.TLabel").pack(anchor="w", pady=(6, 0))

        # ganchos para pruebas
        self._dxf_path = path_entry
        self._dxf_layer_walls = walls_entry
        self._dxf_layer_spaces = spaces_entry
        self._dxf_thickness = thick_entry
        self._dxf_level = level_entry
        self._dxf_converter = conv_entry
        self._dxf_status = status_var
        self._dxf_report = report
        self._dxf_analyze = lambda: _analyze()
        self._dxf_apply = lambda: _apply()
        self._dxf_result: Dict[str, Any] = {}
        self._dxf_source = ""      # DXF listo para importar (dwg → temporal)
        self._dxf_dwg: Dict[str, Any] = {}   # informe de conversión del gateway
        if not hasattr(self, "_dxf_sync"):
            self._dxf_sync = False

        def _browse() -> None:
            path = filedialog.askopenfilename(
                title="Plano DXF o DWG",
                filetypes=[("Plano CAD (DXF/DWG)", "*.dxf *.dwg"),
                           ("Dibujo DXF", "*.dxf"),
                           ("Dibujo DWG", "*.dwg"),
                           ("Todos", "*.*")])
            if path:
                path_var.set(path)

        def _show(text: str) -> None:
            report.configure(state="normal")
            report.delete("1.0", "end")
            report.insert("1.0", text)
            report.configure(state="disabled")

        def _importer() -> Any:
            from importers.dxf_reader import DxfImporter
            return DxfImporter(layer_walls=walls_var.get().strip(),
                               layer_spaces=spaces_var.get().strip())

        def _run_async(work, done) -> None:
            """Ejecuta ``work`` en un hilo (o en línea si _dxf_sync)."""
            holder: Dict[str, Any] = {}

            def job() -> None:
                try:
                    holder["ok"] = work()
                except Exception as exc:  # noqa: BLE001
                    holder["error"] = str(exc)
                if self._dxf_sync:
                    done(holder)

            if self._dxf_sync:
                job()
                return
            threading.Thread(target=job, daemon=True).start()

            def poll() -> None:
                if "ok" in holder or "error" in holder:
                    done(holder)
                else:
                    dialog.after(120, poll)

            dialog.after(120, poll)

        def _analyze() -> None:
            path = path_var.get().strip()
            if not path or not os.path.exists(path):
                status_var.set("Elige un archivo .dxf o .dwg existente.")
                return
            progress.pack(fill="x", pady=(8, 0))
            progress.start(12)
            status_var.set("Leyendo el plano y detectando candidatos…")

            def work():
                source = path
                prep = None
                if source.lower().endswith(".dwg"):
                    from importers.dwg_reader import DwgGateway
                    prep = DwgGateway().prepare(
                        source, converter=conv_var.get().strip())
                    if not prep["ok"]:
                        raise RuntimeError("; ".join(prep["errors"]))
                    source = prep["dxf_path"]
                return (prep, _importer().preview(source))

            def done(holder: Dict[str, Any]) -> None:
                progress.stop()
                progress.pack_forget()
                if "error" in holder:
                    status_var.set("No se pudo analizar el plano.")
                    _show(f"ERROR\n{holder['error']}")
                    return
                prep, data = holder["ok"]
                if prep is not None:
                    self._dxf_dwg = prep
                    self._dxf_source = prep["dxf_path"]
                else:
                    self._dxf_dwg = {}
                    self._dxf_source = path
                self._dxf_result = data
                counts = data.get("counts", {})
                summary = "\n".join(f"  {k}: {v}"
                                    for k, v in counts.items())
                spaces = data.get("spaces_preview", [])
                lines = []
                if prep is not None:
                    version = prep.get("version", {})
                    lines.append("CONVERSIÓN DWG → DXF TEMPORAL\n"
                                 f"  Versión: {version.get('code', '?')} "
                                 f"({version.get('label', '?')})\n"
                                 f"  Convertidor: {prep.get('converter', '?')}\n"
                                 f"  DXF: {prep.get('dxf_path', '?')}\n")
                lines.append("ANÁLISIS COMPLETADO\n\nConteos:\n" + summary)
                unidades = data.get("unidades")
                if unidades and unidades.get("escala") not in (None, 1.0):
                    lines.append(
                        "\nUnidades del plano: {0} (escala {1:g} a "
                        "metros; coordenadas convertidas)".format(
                            unidades.get("etiqueta", "?"),
                            unidades.get("escala", 1.0)))
                if spaces:
                    lines.append("\nLocales detectados (hasta 10):")
                    lines += [f"  · {s['name']} — "
                              f"{s['area_m2']:.2f} m²" for s in spaces]
                warnings = data.get("warnings", [])
                lines.append("\nAvisos:\n" + (
                    "\n".join(f"  · {w}" for w in warnings)
                    if warnings else "  (ninguno)"))
                errors = data.get("errors", [])
                if errors:
                    lines.append("\nErrores:\n" + "\n".join(
                        f"  ! {e}" for e in errors))
                _show("\n".join(lines))
                if errors:
                    status_var.set("El plano tiene errores: revísalos "
                                   "antes de importar.")
                else:
                    status_var.set(
                        f"Listo para importar: {counts.get('walls', 0)} "
                        f"muros y {counts.get('spaces', 0)} locales. "
                        "Pulsa «Importar al proyecto».")

            _run_async(work, done)

        def _apply() -> None:
            source = self._dxf_source
            path = path_var.get().strip()
            if not source and path.lower().endswith(".dwg"):
                status_var.set("Primero analiza el plano .dwg: se convierte "
                               "a DXF temporal al analizar.")
                return
            if not source:
                source = path
            if not source or not os.path.exists(source):
                status_var.set("Primero analiza un plano válido.")
                return
            if not getattr(self.ctx, "project", None):
                status_var.set("Abre o crea un proyecto antes de "
                               "importar el plano.")
                return
            try:
                thickness = float(
                    str(thick_var.get()).replace(",", ".") or "0.2")
            except ValueError:
                thickness = 0.2
            thickness = min(max(thickness, 0.05), 2.0)
            level_ref = level_var.get().strip() or "Nivel DXF"
            progress.pack(fill="x", pady=(8, 0))
            progress.start(12)
            status_var.set("Creando muros y espacios (transaccional)…")

            def work():
                from services.architecture_service import ArchitectureService
                return _importer().apply(
                    source, ArchitectureService(self.ctx), level_ref,
                    thickness_m=thickness)

            def done(holder: Dict[str, Any]) -> None:
                progress.stop()
                progress.pack_forget()
                if "error" in holder:
                    status_var.set("La importación falló: el proyecto "
                                   "quedó sin cambios.")
                    _show(f"ERROR AL IMPORTAR\n{holder['error']}")
                    return
                data = holder["ok"]
                self._dxf_result = data
                _show("PLANO IMPORTADO\n\n"
                      f"  Muros creados: {data.get('walls', 0)}\n"
                      f"  Espacios creados: {data.get('spaces', 0)}\n"
                      f"  Nivel: {data.get('level', level_ref)}\n\n"
                      "La importación quedó auditada y deshacible "
                      "como cualquier edición.")
                status_var.set(f"Importado: {data.get('walls', 0)} muros, "
                               f"{data.get('spaces', 0)} locales en "
                               f"«{data.get('level', level_ref)}».")
                try:
                    self.refresh_all(fit=True)
                except Exception:  # noqa: BLE001 — refresco cosmético
                    pass
                self._say(
                    f"Plano DXF importado: {data.get('walls', 0)} muros y "
                    f"{data.get('spaces', 0)} locales.",
                    "Los objetos quedaron en el explorador y el lienzo; "
                    "puedes editarlos como cualquier otro.")

            _run_async(work, done)

        buttons = ttk.Frame(dialog, padding=(14, 8))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Analizar plano",
                   command=lambda: _analyze()).pack(side="left")
        ttk.Button(buttons, text="Importar al proyecto",
                   command=lambda: _apply()).pack(side="left", padx=(8, 0))

    def _exportar_informe_html(self, dialog: Any) -> None:
        """Guarda el informe del diálogo como HTML autocontenido (v3.27.0).

        El dict del informe viaja en ``dialog._informe`` (lo deja el
        diálogo al construirse) y el título en ``dialog._titulo_informe``;
        así se exporta EXACTAMENTE lo que el usuario está viendo.
        Sólo lectura del proyecto: el archivo no toca la base de datos.
        """
        informe = getattr(dialog, "_informe", None)
        if informe is None:
            messagebox.showinfo(
                "Guardar HTML",
                "Este diálogo no lleva informe exportable.",
                parent=dialog)
            return
        destino = filedialog.asksaveasfilename(
            title="Guardar informe HTML",
            defaultextension=".html",
            initialfile="informe_validacion.html",
            filetypes=[("Informe HTML", "*.html"),
                       ("Todos los archivos", "*.*")],
            parent=dialog)
        if not destino:
            return
        try:
            from exporters.informe_html import guardar_informe_html
            ruta = guardar_informe_html(
                destino, informe,
                titulo=str(getattr(dialog, "_titulo_informe",
                                   "Informe de validación")))
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Guardar informe HTML",
                "No pude escribir el informe HTML:\n\n"
                f"{exc}", parent=dialog)
            return
        messagebox.showinfo(
            "Guardar informe HTML",
            "Informe escrito:\n\n" + ruta, parent=dialog)
        self._say("Informe HTML listo para adjuntar o imprimir: "
                  + ruta)

    def validar_vivienda_informe(self) -> None:
        """Informe de validación de vivienda (catálogo §54, VIV001-030).

        Lee el proyecto (locales, vanos, cubierta, escaleras, metadata
        del asistente) y muestra las 30 comprobaciones con su estado:
        medido, pendiente (configurable del §66) o
        REQUIERE_CALCULO_ESPECIALIZADO (§81). Solo lectura.
        """
        try:
            from domain.vivienda_specs import (validar_vivienda,
                                               texto_validacion_vivienda)
            informe = validar_vivienda(self.ctx)
            texto = texto_validacion_vivienda(informe)
            # coste ligado al check (v3.31.0): instantánea del
            # presupuesto activo, sólo lectura; sin presupuesto no
            # aparece nada
            from services.coste_informe import adjuntar_coste
            bloque = adjuntar_coste(self.ctx, informe)
            if bloque:
                texto = texto + "\n\n" + bloque
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Validar vivienda",
                "No pude validar la vivienda:\n\n"
                f"{exc}", parent=self)
            self._say("Validación de vivienda no disponible: revisa el "
                      "mensaje del error.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Validación de vivienda — catálogo §54")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "validar_vivienda")
        self._validar_vivienda_dialogo = dialog
        cabecera = ttk.Frame(dialog, style="Panel.TFrame",
                             padding=(14, 10))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Las 30 comprobaciones del catálogo",
                  style="Title.TLabel").pack(anchor="w")
        resumen = informe.get("resumen", {})
        ttk.Label(cabecera, style="Accent.TLabel", text=(
            f"{resumen.get('ok', 0)} cumplen · "
            f"{resumen.get('avisos', 0)} avisos · "
            f"{resumen.get('fallos', 0)} fallos · "
            f"{resumen.get('pendientes', 0)} pendientes o de cálculo"
        )).pack(anchor="w", pady=(2, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        campo = tk.Text(cuerpo, width=86, height=30, wrap="word",
                        background=theme.COL_FIELD,
                        foreground=theme.COL_TEXT, relief="flat",
                        padx=10, pady=8)
        campo.insert("1.0", texto)
        campo.configure(state="disabled")
        campo.pack(fill="both", expand=True)
        dialog._viv_texto = campo
        dialog._informe = informe
        dialog._titulo_informe = "Validación de vivienda (catálogo §54)"
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")
        self._tip(ttk.Button(
            botones, text="Guardar HTML...",
            command=lambda: self._exportar_informe_html(dialog)),
            "val_html_save").pack(side="left")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        self._say("Validación de vivienda lista: cada punto indica si "
                  "está medido, pendiente de configuración o pide "
                  "cálculo especializado.")

    def validar_comercial_informe(self) -> None:
        """Informe CC/OF del documento comercial (v3.25.0).

        Programa mínimo del §89-90, relaciones del §78 (con las
        prohibiciones residuos/carga contra público), porcentajes del
        §81, eficiencia del §82, estacionamiento del §45, evacuación
        IBC 2024 del §17/§61, galería del §6 y el control dimensional
        de cada local, con estados honestos medido/pendiente/requiere
        cálculo (§101). Solo lectura.
        """
        try:
            from domain.comercial_specs import (validar_proyecto,
                                                texto_validacion_comercial)
            informe = validar_proyecto(self.ctx)
            texto = texto_validacion_comercial(informe)
            from services.coste_informe import adjuntar_coste
            bloque = adjuntar_coste(self.ctx, informe)
            if bloque:
                texto = texto + "\n\n" + bloque
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Validar centro comercial / oficinas",
                "No pude validar contra el documento comercial:\n\n"
                f"{exc}", parent=self)
            self._say("Validación comercial no disponible: revisa el "
                      "mensaje del error.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Validación CC/OF — documento comercial")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "validar_comercial")
        self._validar_comercial_dialogo = dialog
        cabecera = ttk.Frame(dialog, style="Panel.TFrame",
                             padding=(14, 10))
        cabecera.pack(fill="x")
        titulo = "Programa, relaciones y cotas del documento CC/OF"
        if informe.get("familias"):
            titulo += " - " + ", ".join(informe["familias"])
        ttk.Label(cabecera, text=titulo,
                  style="Title.TLabel").pack(anchor="w")
        resumen = informe.get("resumen", {})
        ttk.Label(cabecera, style="Accent.TLabel", text=(
            f"{resumen.get('ok', 0)} cumplen · "
            f"{resumen.get('avisos', 0)} avisos · "
            f"{resumen.get('fallos', 0)} fallos · "
            f"{resumen.get('pendientes', 0)} pendientes o de cálculo"
        )).pack(anchor="w", pady=(2, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        campo = tk.Text(cuerpo, width=86, height=30, wrap="word",
                        background=theme.COL_FIELD,
                        foreground=theme.COL_TEXT, relief="flat",
                        padx=10, pady=8)
        campo.insert("1.0", texto)
        campo.configure(state="disabled")
        campo.pack(fill="both", expand=True)
        dialog._com_texto = campo
        dialog._informe = informe
        dialog._titulo_informe = "Validación CC/OF (documento comercial)"
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")
        self._tip(ttk.Button(
            botones, text="Guardar HTML...",
            command=lambda: self._exportar_informe_html(dialog)),
            "val_html_save").pack(side="left")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        self._say("Validación comercial lista: lo medido, lo pendiente "
                  "de normativa y lo que pide cálculo especializado.")

    def validar_educacion_informe(self) -> None:
        """Informe educacional del documento ED (v3.26.0).

        Programa mínimo del §106-109, relaciones del §98-101, flujos
        limpio/sucio del §102, aulas vs capacidad (§4/§111), dormitorios
        (§49-51), comedor (REGLA_08), escaleras (§45), punto de reunión
        (§104-105), alturas libres (§2), seguridad infantil (§89) y el
        control dimensional de cada local, con estados honestos
        medido/pendiente/requiere cálculo. Solo lectura.
        """
        try:
            from domain.educacion_specs import (validar_proyecto,
                                                texto_validacion_educacion)
            informe = validar_proyecto(self.ctx)
            texto = texto_validacion_educacion(informe)
            from services.coste_informe import adjuntar_coste
            bloque = adjuntar_coste(self.ctx, informe)
            if bloque:
                texto = texto + "\n\n" + bloque
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Validar escuela / albergue",
                "No pude validar contra el documento educacional:\n\n"
                f"{exc}", parent=self)
            self._say("Validación educacional no disponible: revisa el "
                      "mensaje del error.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Validación ED — documento educacional")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "validar_educacion")
        self._validar_educacion_dialogo = dialog
        cabecera = ttk.Frame(dialog, style="Panel.TFrame",
                             padding=(14, 10))
        cabecera.pack(fill="x")
        titulo = "Programa, relaciones y cotas del documento educacional"
        if informe.get("familias"):
            titulo += " - " + ", ".join(informe["familias"])
        ttk.Label(cabecera, text=titulo,
                  style="Title.TLabel").pack(anchor="w")
        resumen = informe.get("resumen", {})
        ttk.Label(cabecera, style="Accent.TLabel", text=(
            f"{resumen.get('ok', 0)} cumplen · "
            f"{resumen.get('avisos', 0)} avisos · "
            f"{resumen.get('fallos', 0)} fallos · "
            f"{resumen.get('pendientes', 0)} pendientes o de cálculo"
        )).pack(anchor="w", pady=(2, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        campo = tk.Text(cuerpo, width=86, height=30, wrap="word",
                        background=theme.COL_FIELD,
                        foreground=theme.COL_TEXT, relief="flat",
                        padx=10, pady=8)
        campo.insert("1.0", texto)
        campo.configure(state="disabled")
        campo.pack(fill="both", expand=True)
        dialog._edu_texto = campo
        dialog._informe = informe
        dialog._titulo_informe = "Validación ED (documento educacional)"
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")
        self._tip(ttk.Button(
            botones, text="Guardar HTML...",
            command=lambda: self._exportar_informe_html(dialog)),
            "val_html_save").pack(side="left")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        self._say("Validación educacional lista: lo medido, lo "
                  "pendiente y lo que pide cálculo especializado.")

    # -- estudios de vivienda (v3.24.0): alternativas §62-63,
    # -- modulación §56 y solar FV §38 (catálogo maestro) -------------

    def alternativas_vivienda_informe(self) -> None:
        """Alternativas comparables de vivienda (catálogo §62-63).

        Genera A/B/C por nivel de acabado y 1/2/3/4 por sistema
        constructivo con las métricas de comparación del §63, a partir
        de la metadata del asistente (o del programa paramétrico). Solo
        lectura: no toca el presupuesto del proyecto.
        """
        try:
            from domain.vivienda_estudios import (generar_alternativas,
                                                  texto_alternativas)
            tipologia, dorm, banos, estilo, sistema = \
                self._vivienda_entrada()
            informe = generar_alternativas(
                self.ctx, dormitorios=dorm, banos=banos,
                estilo_label=estilo, tipologia=tipologia,
                sistema_label=sistema)
            texto = texto_alternativas(informe)
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Alternativas de vivienda",
                "No pude generar las alternativas:\n\n"
                f"{exc}", parent=self)
            self._say("Alternativas de vivienda no disponibles: "
                      "revisa el mensaje del error.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Alternativas de vivienda — catálogo §62-63")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "alternativas_vivienda")
        self._alternativas_dialogo = dialog
        cabecera = ttk.Frame(dialog, padding=(14, 10))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Misma entrada, siete alternativas",
                  style="Title.TLabel").pack(anchor="w")
        recomendada = str(informe.get("recomendada", ""))
        ttk.Label(cabecera, style="Accent.TLabel", text=(
            f"recomendada: alternativa {recomendada} (menor costo con "
            "compatibilidad >= 2/3)"
        )).pack(anchor="w", pady=(2, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        campo = tk.Text(cuerpo, width=92, height=28, wrap="word",
                        background=theme.COL_FIELD,
                        foreground=theme.COL_TEXT, relief="flat",
                        padx=10, pady=8)
        campo.insert("1.0", texto)
        campo.configure(state="disabled")
        campo.pack(fill="both", expand=True)
        dialog._alt_texto = campo
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        self._say("Alternativas generadas: compara costo, plazo, "
                  "materiales y vida útil antes de decidir.")

    def modulacion_informe(self) -> None:
        """Modulación constructiva (catálogo §56).

        Diálogo con el módulo a evaluar (0.60, 1.20, 1.25, 1.50 o
        personalizado) e informe de locales, muros, puertas y ventanas
        fuera de módulo con sugerencias. Solo lectura.
        """
        dialog = tk.Toplevel(self)
        dialog.title("Modulación constructiva — catálogo §56")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "modulacion")
        self._modulacion_dialogo = dialog
        cabecera = ttk.Frame(dialog, padding=(14, 10))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Evaluar piezas contra el módulo para "
                                 "reducir desperdicios",
                  style="Title.TLabel").pack(anchor="w")
        fila = ttk.Frame(cabecera)
        fila.pack(fill="x", pady=(6, 0))
        ttk.Label(fila, text="Módulo:").pack(side="left")
        valores = ["0.60", "1.20", "1.25", "1.50", "Personalizado"]
        combo = ttk.Combobox(fila, values=valores, state="readonly",
                             width=14)
        combo.current(1)
        combo.pack(side="left", padx=(6, 10))
        ttk.Label(fila, text="Personalizado (m):").pack(side="left")
        entrada = ttk.Entry(fila, width=8)
        entrada.insert(0, "0.90")
        entrada.pack(side="left", padx=(6, 0))
        texto_var = {"campo": None}

        def _evaluar() -> None:
            try:
                from domain.vivienda_estudios import (evaluar_modulacion,
                                                      texto_modulacion)
                if combo.get() == "Personalizado":
                    modulo = float(str(entrada.get())
                                   .replace(",", ".") or 0)
                else:
                    modulo = float(combo.get())
                informe = evaluar_modulacion(self.ctx, modulo)
                contenido = texto_modulacion(informe)
            except ValueError:
                messagebox.showerror(
                    "Modulación", "El módulo personalizado debe ser un "
                    "número (ej. 0.90).", parent=dialog)
                return
            except Exception as exc:  # noqa: BLE001 - amable
                messagebox.showerror(
                    "Modulación", "No pude evaluar la modulación:"
                    "\n\n" + str(exc), parent=dialog)
                return
            campo = texto_var["campo"]
            if campo is not None:
                campo.configure(state="normal")
                campo.delete("1.0", "end")
                campo.insert("1.0", contenido)
                campo.configure(state="disabled")

        ttk.Button(fila, text="Evaluar",
                   command=_evaluar).pack(side="left", padx=(12, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        campo = tk.Text(cuerpo, width=86, height=24, wrap="word",
                        background=theme.COL_FIELD,
                        foreground=theme.COL_TEXT, relief="flat",
                        padx=10, pady=8)
        campo.pack(fill="both", expand=True)
        texto_var["campo"] = campo
        dialog._mod_texto = campo
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        _evaluar()
        self._say("Modulación: el informe sugiere, no bloquea — "
                  "ajusta las piezas que más residuo dejen.")

    def solar_informe(self) -> None:
        """Dimensionado solar paramétrico (catálogo §38).

        Entradas del §38 (consumo diario, horas de sol pico, potencia
        del panel, eficiencia, pérdidas, autonomía, ocupantes) y
        salidas: paneles, potencia, batería, inversor y superficie.
        Solo cálculo: no toca el proyecto.
        """
        dialog = tk.Toplevel(self)
        dialog.title("Solar fotovoltaica — catálogo §38")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "solar")
        self._solar_dialogo = dialog
        cabecera = ttk.Frame(dialog, padding=(14, 10))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Dimensionar el sistema solar del §38",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(cabecera, text=(
            "Deja vacío un parámetro para usar el de referencia del "
            "catálogo (configurable, §66)"
        ), style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        grid = ttk.Frame(cabecera)
        grid.pack(fill="x", pady=(8, 0))
        campos = (
            ("Consumo diario (kWh)", "consumo"),
            ("Horas de sol pico", "hsp"),
            ("Potencia del panel (W)", "panel"),
            ("Eficiencia (0-1)", "ef"),
            ("Pérdidas (0-1)", "per"),
            ("Autonomía (días)", "auto"),
            ("Ocupantes", "ocup"),
        )
        entradas: Dict[str, ttk.Entry] = {}
        for i, (titulo, clave) in enumerate(campos):
            fila = i // 3
            col = (i % 3) * 2
            ttk.Label(grid, text=titulo).grid(
                row=fila, column=col, sticky="w", padx=(0, 4), pady=3)
            e = ttk.Entry(grid, width=9)
            e.grid(row=fila, column=col + 1, sticky="w",
                   padx=(0, 14), pady=3)
            entradas[clave] = e
        ttk.Label(grid, text="Sistema:").grid(row=2, column=0,
                                              sticky="w", padx=(0, 4))
        sistema_var = tk.StringVar(value="FOTOVOLTAICO")
        combo = ttk.Combobox(grid, state="readonly", width=14,
                             textvariable=sistema_var,
                             values=["FOTOVOLTAICO", "SOLAR_TERMICO",
                                     "HIBRIDO"])
        combo.grid(row=2, column=1, sticky="w", padx=(0, 14))
        bateria_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(grid, text="Con batería",
                        variable=bateria_var).grid(
            row=2, column=2, columnspan=2, sticky="w")
        texto_var = {"campo": None}

        def _dimensionar() -> None:
            def _num(clave: str) -> float:
                bruto = str(entradas[clave].get()).strip()
                if not bruto:
                    return 0.0
                return float(bruto.replace(",", "."))
            try:
                from domain.vivienda_estudios import (dimensionar_solar,
                                                      texto_solar)
                informe = dimensionar_solar(
                    consumo_diario_kwh=_num("consumo"),
                    horas_sol_pico=_num("hsp"),
                    potencia_panel_w=_num("panel"),
                    eficiencia=_num("ef"),
                    perdidas=_num("per"),
                    autonomia_dias=_num("auto"),
                    ocupantes=int(_num("ocup") or 0),
                    sistema=sistema_var.get(),
                    con_bateria=bateria_var.get())
                contenido = texto_solar(informe)
            except ValueError:
                messagebox.showerror(
                    "Solar", "Revisa los valores: deben ser números "
                    "(acepta coma decimal).", parent=dialog)
                return
            except Exception as exc:  # noqa: BLE001 - amable
                messagebox.showerror(
                    "Solar", "No pude dimensionar el sistema:\n\n"
                    + str(exc), parent=dialog)
                return
            campo = texto_var["campo"]
            if campo is not None:
                campo.configure(state="normal")
                campo.delete("1.0", "end")
                campo.insert("1.0", contenido)
                campo.configure(state="disabled")

        ttk.Button(cabecera, text="Dimensionar",
                   command=_dimensionar).pack(anchor="w", pady=(8, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        campo = tk.Text(cuerpo, width=86, height=18, wrap="word",
                        background=theme.COL_FIELD,
                        foreground=theme.COL_TEXT, relief="flat",
                        padx=10, pady=8)
        campo.pack(fill="both", expand=True)
        texto_var["campo"] = campo
        dialog._sol_texto = campo
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        _dimensionar()
        self._say("Solar §38: la instalación definitiva queda marcada "
                  "REQUIERE_CALCULO_ESPECIALIZADO (§81).")

    # -- servicios de vivienda (v3.30.0): piscina §45, acústica §46
    # -- y domótica §39 del documento de especificaciones ---------------

    def piscina_dialogo(self) -> None:
        """Dimensionado de PISCINA como sistema independiente (§45).

        Volumen, renovación y caudal de filtración, skimmers,
        impulsión, bomba estimada, iluminación submarina, checklist de
        seguridad y equipos de referencia en CUP. Solo cálculo: no
        toca el proyecto.
        """
        dialog = tk.Toplevel(self)
        dialog.title("Piscina — catálogo §45")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "piscina")
        self._piscina_dialogo = dialog
        cabecera = ttk.Frame(dialog, padding=(14, 10))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Dimensionar la piscina del §45",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(cabecera, text=(
            "Sistema independiente de la vivienda (§45). Deja vacío "
            "un parámetro para usar su valor de referencia"
        ), style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        grid = ttk.Frame(cabecera)
        grid.pack(fill="x", pady=(8, 0))
        campos = (
            ("Largo (m)", "largo", "8.0", "piscina_largo"),
            ("Ancho (m)", "ancho", "4.0", "piscina_ancho"),
            ("Profundidad mínima (m)", "prof_min", "1.0",
             "piscina_prof_min"),
            ("Profundidad máxima (m)", "prof_max", "2.0",
             "piscina_prof_max"),
            ("Altura manométrica (m)", "altura", "",
             "piscina_altura"),
            ("Renovación (horas)", "renovacion", "",
             "piscina_renovacion"),
        )
        entradas: Dict[str, ttk.Entry] = {}
        for i, (titulo, clave, defecto, tip) in enumerate(campos):
            fila = i // 3
            col = (i % 3) * 2
            ttk.Label(grid, text=titulo).grid(
                row=fila, column=col, sticky="w", padx=(0, 4), pady=3)
            e = ttk.Entry(grid, width=9)
            e.insert(0, defecto)
            e.grid(row=fila, column=col + 1, sticky="w",
                   padx=(0, 14), pady=3)
            entradas[clave] = e
            self._tip(e, tip)
        texto_var = {"campo": None, "informe": None}

        def _num(clave: str) -> float:
            bruto = str(entradas[clave].get()).strip()
            if not bruto:
                return 0.0
            return float(bruto.replace(",", "."))

        def _calcular() -> None:
            try:
                from domain.vivienda_servicios import (calcular_piscina,
                                                       texto_piscina)
                informe = calcular_piscina(
                    largo=_num("largo"), ancho=_num("ancho"),
                    prof_min=_num("prof_min"),
                    prof_max=_num("prof_max"),
                    altura_m=_num("altura"),
                    renovacion_h=_num("renovacion"))
                contenido = texto_piscina(informe)
            except ValueError:
                messagebox.showerror(
                    "Piscina", "Revisa los valores: deben ser números "
                    "(acepta coma decimal).", parent=dialog)
                return
            except Exception as exc:  # noqa: BLE001 - amable
                messagebox.showerror(
                    "Piscina", "No pude dimensionar la piscina:\n\n"
                    + str(exc), parent=dialog)
                return
            texto_var["informe"] = informe
            campo = texto_var["campo"]
            if campo is not None:
                campo.configure(state="normal")
                campo.delete("1.0", "end")
                campo.insert("1.0", contenido)
                campo.configure(state="disabled")
            boton_html.configure(state="normal")

        ttk.Button(cabecera, text="Calcular",
                   command=_calcular).pack(anchor="w", pady=(8, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        campo = tk.Text(cuerpo, width=86, height=18, wrap="word",
                        background=theme.COL_FIELD,
                        foreground=theme.COL_TEXT, relief="flat",
                        padx=10, pady=8)
        campo.pack(fill="both", expand=True)
        texto_var["campo"] = campo
        dialog._pis_texto = campo
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")
        boton_html = self._tip(ttk.Button(
            botones, text="Guardar HTML...", state="disabled",
            command=lambda: self._exportar_informe_html_guardado(
                dialog, texto_var)),
            "val_html_save")
        boton_html.pack(side="left")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        _calcular()
        self._say("Piscina §45: volumen, filtración, bomba y seguridad "
                  "como SISTEMA INDEPENDIENTE de la vivienda.")

    def _exportar_informe_html_guardado(self, dialog: Any,
                                        texto_var: Dict[str, Any]) -> None:
        """Guarda como HTML el informe guardado en ``texto_var``."""
        informe = texto_var.get("informe")
        if informe is None:
            messagebox.showinfo(
                "Guardar HTML", "Primero calcula el informe.",
                parent=dialog)
            return
        destino = filedialog.asksaveasfilename(
            title="Guardar informe HTML",
            defaultextension=".html",
            initialfile="informe_validacion.html",
            filetypes=[("Informe HTML", "*.html"),
                       ("Todos los archivos", "*.*")],
            parent=dialog)
        if not destino:
            return
        try:
            from exporters.informe_html import guardar_informe_html
            ruta = guardar_informe_html(
                destino, informe,
                titulo=str(texto_var.get(
                    "titulo", "Informe de validación")))
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Guardar informe HTML",
                "No pude escribir el informe HTML:\n\n"
                f"{exc}", parent=dialog)
            return
        messagebox.showinfo("Guardar informe HTML",
                            "Informe escrito:\n\n" + ruta,
                            parent=dialog)
        self._say("Informe HTML listo para adjuntar o imprimir: "
                  + ruta)

    def acustica_informe(self) -> None:
        """Informe acústico del §46 sobre el proyecto abierto.

        Identifica fuentes (cocina, baños, equipos) frente a
        dormitorios midiendo los muros compartidos, y establece el
        aislamiento de referencia: material, espesor, doble tabique,
        cubierta y vidrio acústico. Solo lectura.
        """
        try:
            from domain.vivienda_servicios import (analisis_acustico,
                                                   texto_acustica)
            informe = analisis_acustico(self.ctx)
            texto = texto_acustica(informe)
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Acústica de la vivienda",
                "No pude analizar la acústica:\n\n"
                f"{exc}", parent=self)
            self._say("Acústica §46 no disponible: revisa el mensaje "
                      "del error.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Acústica — catálogo §46")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "acustica")
        self._acustica_dialogo = dialog
        cabecera = ttk.Frame(dialog, style="Panel.TFrame",
                             padding=(14, 10))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Fuentes, dormitorios y aislamiento "
                                 "de referencia (§46)",
                  style="Title.TLabel").pack(anchor="w")
        resumen = informe.get("resumen", {})
        ttk.Label(cabecera, style="Accent.TLabel", text=(
            f"{resumen.get('ok', 0)} cumplen · "
            f"{resumen.get('avisos', 0)} avisos · "
            f"{resumen.get('fallos', 0)} fallos · "
            f"{resumen.get('pendientes', 0)} pendientes o de cálculo"
        )).pack(anchor="w", pady=(2, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        campo = tk.Text(cuerpo, width=86, height=30, wrap="word",
                        background=theme.COL_FIELD,
                        foreground=theme.COL_TEXT, relief="flat",
                        padx=10, pady=8)
        campo.insert("1.0", texto)
        campo.configure(state="disabled")
        campo.pack(fill="both", expand=True)
        dialog._acu_texto = campo
        dialog._informe = informe
        dialog._titulo_informe = "Acústica de la vivienda (§46)"
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")
        self._tip(ttk.Button(
            botones, text="Guardar HTML...",
            command=lambda: self._exportar_informe_html(dialog)),
            "val_html_save").pack(side="left")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        self._say("Acústica §46 lista: pares fuente-dormitorio medidos "
                  "con su solución de referencia.")

    def domotica_informe(self) -> None:
        """Plan domótico del §39 sobre el proyecto abierto.

        Los 8 sistemas del §39 con sus elementos (sensores,
        actuadores, controladores...) contados sobre el modelo y
        equipos de referencia en CUP; RED, PANEL y ALIMENTACION
        quedan como diseño (REQUIERE_CALCULO). Solo lectura.
        """
        try:
            from domain.vivienda_servicios import (plan_domotico,
                                                   texto_domotica)
            informe = plan_domotico(self.ctx)
            texto = texto_domotica(informe)
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Plan domótico",
                "No pude armar el plan domótico:\n\n"
                f"{exc}", parent=self)
            self._say("Domótica §39 no disponible: revisa el mensaje "
                      "del error.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Plan domótico — catálogo §39")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "domotica")
        self._domotica_dialogo = dialog
        cabecera = ttk.Frame(dialog, style="Panel.TFrame",
                             padding=(14, 10))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Sistemas y elementos del §39 contados "
                                 "sobre el modelo",
                  style="Title.TLabel").pack(anchor="w")
        resumen = informe.get("resumen", {})
        ttk.Label(cabecera, style="Accent.TLabel", text=(
            f"{resumen.get('ok', 0)} cumplen · "
            f"{resumen.get('avisos', 0)} avisos · "
            f"{resumen.get('fallos', 0)} fallos · "
            f"{resumen.get('pendientes', 0)} pendientes o de cálculo"
        )).pack(anchor="w", pady=(2, 0))
        cuerpo = ttk.Frame(dialog, padding=(14, 8))
        cuerpo.pack(fill="both", expand=True)
        campo = tk.Text(cuerpo, width=86, height=30, wrap="word",
                        background=theme.COL_FIELD,
                        foreground=theme.COL_TEXT, relief="flat",
                        padx=10, pady=8)
        campo.insert("1.0", texto)
        campo.configure(state="disabled")
        campo.pack(fill="both", expand=True)
        dialog._dom_texto = campo
        dialog._informe = informe
        dialog._titulo_informe = "Plan domótico (§39)"
        botones = ttk.Frame(dialog, padding=(14, 8))
        botones.pack(fill="x")
        self._tip(ttk.Button(
            botones, text="Guardar HTML...",
            command=lambda: self._exportar_informe_html(dialog)),
            "val_html_save").pack(side="left")
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        self._say("Plan domótico §39 listo: equipos de referencia por "
                  "sistema; el diseño de bus/panel pide cálculo.")

    def _vivienda_entrada(self) -> tuple:
        """(tipología, dormitorios, baños, estilo, sistema) del
        asistente para los estudios; valores por defecto si no hay
        metadata de vivienda."""
        tipologia = "Unifamiliar aislada"
        dorm, banos = 3, 2
        estilo = sistema = ""
        try:
            _edificio, edif = bwiz._wizard_building(self.ctx)
            viv = (edif or {}).get("vivienda") or {}
            if viv.get("tipologia"):
                tipologia = str(viv["tipologia"])
            if viv.get("dormitorios"):
                dorm = int(viv["dormitorios"])
            if viv.get("banos"):
                banos = int(viv["banos"])
            estilo = str((edif or {}).get("estilo_arquitectonico", "")
                         or "")
            sistema = str((edif or {}).get("tipologia_constructiva", "")
                          or "")
        except Exception:  # noqa: BLE001 — sin metadata: por defecto
            pass
        return tipologia, dorm, banos, estilo, sistema

    def open_building_wizard(self) -> None:
        """Asistente de edificación en 5 pasos: datos generales, niveles,
        locales, relaciones espaciales + vanos y resumen.

        Toda la lógica vive en ui.building_wizard (headless); aquí solo
        se dibujan formularios y árboles editables. El diálogo queda en
        ``self._building_dialog`` con ganchos ``_bld_*`` para pruebas.
        """
        data = bwiz.BuildingWizardData()
        # Preselección amable: si el proyecto ya tiene un nivel, parto
        # de él (apply reutiliza niveles existentes por nombre).
        existing = self.edit_service.choices("levels")
        if existing:
            data.levels = [bwiz.LevelSpec(name=existing[0], height_m=3.0)]
        else:
            data.levels = [bwiz.LevelSpec(name="Planta Baja",
                                          height_m=3.0)]
        dna_types = ["ROOM"]
        try:
            registry_types = self.ctx.dna_registry.types()
            dna_types += [t for t in registry_types if t != "ROOM"]
        except Exception:  # noqa: BLE001 — sin DNA, solo ROOM
            pass

        dialog = tk.Toplevel(self)
        dialog.title("Asistente de edificación — tu edificio completo")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        dialog.grab_set()
        self._prepare_dialog(dialog, "building_wizard")
        self._building_dialog = dialog

        header = ttk.Frame(dialog, style="Panel.TFrame", padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Vamos a levantar tu edificación juntos",
                  style="Title.TLabel").pack(anchor="w")
        step_var = tk.StringVar()
        ttk.Label(header, textvariable=step_var,
                  style="Accent.TLabel").pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(dialog, padding=(14, 8))
        body.pack(fill="both", expand=True)
        footer = ttk.Frame(dialog, padding=(14, 8))
        footer.pack(fill="x")

        def _row(parent: Any, label: str, tip_key: str = "",
                 width: int = 16) -> ttk.Entry:
            frame = ttk.Frame(parent)
            frame.pack(fill="x", pady=2)
            ttk.Label(frame, text=label, width=24).pack(side="left")
            entry = ttk.Entry(frame, width=width)
            entry.pack(side="left", fill="x", expand=True)
            if tip_key:
                self._tip(entry, tip_key)
            return entry

        def _combo(parent: Any, label: str, values: Sequence[str],
                   tip_key: str = "") -> ttk.Combobox:
            frame = ttk.Frame(parent)
            frame.pack(fill="x", pady=2)
            ttk.Label(frame, text=label, width=24).pack(side="left")
            combo = ttk.Combobox(frame, values=list(values),
                                 state="readonly", width=34)
            if values:
                combo.current(0)
            combo.pack(side="left", fill="x", expand=True)
            if tip_key:
                self._tip(combo, tip_key)
            return combo

        def _dim(parent: Any, text: str) -> None:
            ttk.Label(parent, text=text, style="Dim.TLabel",
                      wraplength=460, justify="left").pack(
                anchor="w", pady=(0, 6))

        def _grid_entry(parent: Any, row: int, column: int, label: str,
                        value: str, tip_key: str) -> ttk.Entry:
            ttk.Label(parent, text=label).grid(row=row, column=column,
                                               sticky="w", padx=(0, 4))
            entry = ttk.Entry(parent, width=9)
            entry.insert(0, value)
            entry.grid(row=row, column=column + 1, sticky="w",
                       padx=(0, 12), pady=2)
            if tip_key:
                self._tip(entry, tip_key)
            return entry

        # -- Paso 1 · datos generales -------------------------------------
        frame1 = ttk.Frame(body)
        _dim(frame1, bwiz.BUILDING_STEPS[0][2])
        name_entry = _row(frame1, "* Nombre de la edificación", "name")
        name_entry.insert(0, data.name)
        usage_combo = _combo(frame1, "Uso social de la edificación",
                             bwiz.USAGE_TYPES, "bld_usage")
        usage_combo.set(data.usage_type)
        # CATÁLOGO MAESTRO DE VIVIENDAS (v3.23.0): tipología del §1 y
        # programa paramétrico del §7 (solo actúan con uso «Vivienda»).
        viv_tip_combo = _combo(frame1, "Tipología de vivienda (catálogo)",
                               bwiz.vivienda_tipologia_choices(),
                               "bld_viv_tip")
        viv_tip_combo.set(data.vivienda_tipologia)
        viv_frame = ttk.Frame(frame1)
        viv_frame.pack(fill="x", pady=2)
        ttk.Label(viv_frame, text="Programa de la vivienda",
                  width=24).pack(side="left")
        viv_grid = ttk.Frame(viv_frame)
        viv_grid.pack(side="left")
        viv_dorm_entry = _grid_entry(viv_grid, 0, 0, "Dormitorios",
                                     str(data.vivienda_dormitorios),
                                     "bld_viv_dorm")
        viv_banos_entry = _grid_entry(viv_grid, 0, 2, "Baños",
                                      str(data.vivienda_banos),
                                      "bld_viv_banos")
        # DOCUMENTO COMERCIAL CC/OF (v3.25.0): tipología del §1 (solo
        # actúa con uso «Centro comercial» u «Oficinas»); el programa
        # mínimo del §89-90 sale del uso elegido.
        com_tip_combo = _combo(frame1, "Tipología CC/OF (documento)",
                               bwiz.comercial_tipologia_choices(),
                               "bld_com_tip")
        com_tip_combo.set(data.comercial_tipologia)
        # DOCUMENTO EDUCACIONAL (v3.26.0): tamaño/capacidad del §4/§9/
        # §48 (solo actúa con los cuatro usos educativos); el programa
        # mínimo del §106-109 sale del uso elegido.
        edu_tam_combo = _combo(frame1,
                               "Tamaño / capacidad (documento ED)",
                               bwiz.educacion_tamano_choices(),
                               "bld_edu_tam")
        edu_tam_combo.set(data.educacion_tamano)
        lot_frame = ttk.Frame(frame1)
        lot_frame.pack(fill="x", pady=2)
        ttk.Label(lot_frame, text="Dimensiones máximas (0 = sin límite)",
                  width=24).pack(side="left")
        lot_grid = ttk.Frame(lot_frame)
        lot_grid.pack(side="left")
        lot_w_entry = _grid_entry(lot_grid, 0, 0, "Ancho (m)",
                                  f"{data.lot_width_m:g}".replace(".", ","),
                                  "bld_lot_w")
        lot_d_entry = _grid_entry(lot_grid, 0, 2, "Fondo (m)",
                                  f"{data.lot_depth_m:g}".replace(".", ","),
                                  "bld_lot_d")
        construction_combo = _combo(frame1, "Tipología constructiva",
                                    bwiz.CONSTRUCTION_TYPES,
                                    "bld_construction")
        construction_combo.set(data.construction_type)
        shape_combo = _combo(frame1, "Forma en planta",
                             bwiz.PLAN_SHAPES, "bld_shape")
        shape_combo.set(data.plan_shape)
        style_combo = _combo(frame1, "Estilo arquitectónico",
                             bwiz.ARCHITECTURAL_STYLES, "bld_style")
        style_combo.set(data.architectural_style)
        terrain_combo = _combo(frame1, "Terreno",
                               bwiz.TERRAIN_TYPES, "bld_terrain")
        terrain_combo.set(data.terrain_type)
        stairs_combo = _combo(frame1, "Escaleras",
                              bwiz.STAIR_MODES, "bld_stairs")
        stairs_combo.set(data.stairs_mode)
        core_combo = _combo(frame1, "Núcleo rígido en esquinas",
                            bwiz.CORE_MODES, "bld_core")
        core_combo.set(data.core_mode)
        climate_combo = _combo(frame1, "Clima del lugar",
                               bwiz.CLIMATE_ZONES, "bld_climate")
        climate_combo.set(data.climate)
        system_combo = _combo(frame1, "Sistema estructural",
                              bwiz.STRUCTURAL_SYSTEMS, "bld_system")
        system_combo.set(data.structural_system)
        orientation_combo = _combo(frame1, "Fachada principal hacia",
                                   bwiz.ORIENTATIONS, "bld_orientation")
        orientation_combo.set(data.facade_orientation)
        # EDICIÓN REGIONAL DE NEUFERT (v2.8.0): el libro adaptado por
        # región (base 5.ª ed. española, Cuba, México, Argentina…).
        region_choices = bwiz.neufert_region_choices()
        region_combo = _combo(frame1, "Edición regional Neufert",
                              [label for _c, label in region_choices],
                              "bld_region")
        region_combo.set(bwiz.neufert_region_label(data.neufert_region))
        bwiz.set_neufert_region(data.neufert_region)

        def _on_region_change() -> None:
            """Activa la edición elegida y re-aplica sus defaults."""
            code = bwiz.neufert_region_code(region_combo.get())
            if code == data.neufert_region:
                return
            data.neufert_region = code
            bwiz.set_neufert_region(code)
            cambios = bwiz.apply_neufert_defaults(data)
            if cambios:
                try:
                    for entry, value in ((corridor_entry,
                                          data.corridor_width_m),
                                         (door_w_entry, data.door_width_m),
                                         (thick_entry,
                                          data.wall_thickness_m)):
                        entry.delete(0, "end")
                        entry.insert(0, f"{value:.2f}".replace(".", ","))
                except NameError:
                    pass  # los campos del paso 4 aún no existen
            nombre = bwiz.neufert_region_name(code)
            extra = (": " + ", ".join(cambios)) if cambios else "."
            self._say(f"Edición Neufert «{nombre}» activada{extra}.",
                      "La edición ajusta techos, luz de ventanas, "
                      "aleros, rampas y estacionamiento a la región; "
                      "verifica siempre la norma local vigente")
        notes_row = ttk.Frame(frame1)
        notes_row.pack(fill="x", pady=2)
        ttk.Label(notes_row, text="Notas de requerimientos",
                  width=24).pack(side="left")
        notes_text = tk.Text(notes_row, height=3, width=36, wrap="word",
                             background=theme.COL_FIELD,
                             foreground=theme.COL_TEXT, relief="flat",
                             padx=8, pady=6)
        notes_text.pack(side="left", fill="x", expand=True)
        self._tip(notes_text, "bld_notes")
        region_combo.bind("<<ComboboxSelected>>",
                          lambda _event: _on_region_change())

        # DISTRIBUCIÓN INTERIOR (v3.2.0): ortogonal / articulada / orgánica
        dist_combo = _combo(frame1, "Distribución interior",
                            [bwiz.DISTRIBUTION_LABELS[c]
                             for c in bwiz.DISTRIBUCION_CODES],
                            "bld_dist")
        dist_combo.set(bwiz.distribution_label(data.distribucion))
        organic_frame = ttk.Frame(frame1)
        organic_frame.pack(fill="x", pady=2)
        ttk.Label(organic_frame,
                  text="Gesto orgánico (curvatura y semilla)",
                  width=24).pack(side="left")
        organic_grid = ttk.Frame(organic_frame)
        organic_grid.pack(side="left")
        curv_entry = _grid_entry(organic_grid, 0, 0, "Curvatura (m)",
                                 f"{data.curvatura_m:g}".replace(".", ","),
                                 "bld_curv")
        seed_entry = _grid_entry(organic_grid, 0, 2, "Semilla",
                                 str(data.semilla), "bld_seed")

        # PRESETS DE CONFIGURACIÓN (v3.28.0): la configuración del
        # asistente (uso, tipología, tamaño ED, vanos, instalaciones,
        # cubierta...) se guarda como JSON local y se recarga en
        # cualquier proyecto. Nada de nube ni suscripción: presets/
        # junto al programa (o ARQ_GEN_PRESETS).
        presets_row = ttk.Frame(frame1)
        presets_row.pack(fill="x", pady=(6, 2))
        ttk.Label(presets_row, text="Preset de configuración",
                  width=24).pack(side="left")
        preset_combo = ttk.Combobox(presets_row, state="readonly",
                                    width=34, values=[""])
        preset_combo.pack(side="left", padx=(0, 6))
        self._tip(preset_combo, "bld_preset_combo")

        def _presets_refrescar() -> None:
            nombres = []
            for entrada in upres.listar_presets(
                    upres.carpeta_presets()):
                nombre = entrada["nombre"]
                if entrada["corrupto"]:
                    nombre += " (ilegible)"
                nombres.append(nombre)
            preset_combo.configure(values=nombres or [""])
            if nombres and preset_combo.get() not in nombres:
                preset_combo.current(0)
            if not nombres:
                preset_combo.set("")

        def _preset_guardar() -> None:
            from tkinter import simpledialog
            nombre = simpledialog.askstring(
                "Guardar preset",
                "Nombre del preset (por ejemplo, «Escuela primaria "
                "240»):", parent=dialog)
            if not nombre:
                return
            try:
                # recoger los 4 pasos con widgets para no guardar una
                # foto a medias (el programa se regenera, no viaja)
                for paso in (0, 3, 4):
                    _collect(paso)
                ruta = upres.guardar_preset(
                    upres.carpeta_presets(), nombre,
                    upres.preset_de_data(data))
            except Exception as exc:  # noqa: BLE001 - mensaje amable
                messagebox.showerror(
                    "Guardar preset",
                    "No pude guardar el preset:\n\n"
                    f"{exc}", parent=dialog)
                return
            _presets_refrescar()
            preset_combo.set(os.path.basename(ruta)[:-5])
            self._say("Preset de configuración guardado: " + ruta,
                      "El preset guarda la CONFIGURACIÓN del "
                      "asistente, no los locales: recárgalo en "
                      "cualquier proyecto y pide el programa con "
                      "«Cargar programa del uso»")

        def _preset_cargar() -> None:
            nombre = preset_combo.get().replace(" (ilegible)", "")
            if not nombre:
                messagebox.showinfo(
                    "Cargar preset",
                    "No hay preset seleccionado: guarda uno con "
                    "«Guardar» o suelta los .json en la carpeta "
                    "«presets» junto al programa.", parent=dialog)
                return
            ruta = os.path.join(upres.carpeta_presets(),
                                nombre + ".json")
            try:
                documento = upres.cargar_preset(ruta)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror(
                    "Cargar preset", f"{exc}", parent=dialog)
                return
            try:
                avisos = upres.aplicar_preset_a_data(
                    documento["datos"], data)
                _preset_refrescar_widgets()
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror(
                    "Cargar preset",
                    "El preset no se pudo aplicar:\n\n"
                    f"{exc}", parent=dialog)
                return
            if avisos:
                messagebox.showwarning(
                    "Cargar preset",
                    "Preset cargado con avisos:\n\n"
                    + "\n".join("· " + a for a in avisos),
                    parent=dialog)
            self._say("Preset «" + nombre + "» cargado: revisa el "
                      "paso 1 y pide el programa del uso.",
                      "El preset NO trae locales: genera el programa "
                      "con «Cargar programa del uso» o finaliza el "
                      "asistente")

        def _preset_borrar() -> None:
            nombre = preset_combo.get().replace(" (ilegible)", "")
            if not nombre:
                messagebox.showinfo(
                    "Eliminar preset",
                    "Selecciona primero un preset de la lista.",
                    parent=dialog)
                return
            if not messagebox.askyesno(
                    "Eliminar preset",
                    "¿Eliminar el preset «" + nombre + "»? "
                    "El proyecto abierto no se toca.", parent=dialog):
                return
            upres.eliminar_preset(os.path.join(
                upres.carpeta_presets(), nombre + ".json"))
            _presets_refrescar()
            self._say("Preset «" + nombre + "» eliminado.")

        self._tip(ttk.Button(presets_row, text="Guardar",
                             command=_preset_guardar),
                  "bld_preset_save").pack(side="left", padx=(0, 4))
        self._tip(ttk.Button(presets_row, text="Cargar",
                             command=_preset_cargar),
                  "bld_preset_load").pack(side="left", padx=(0, 4))
        self._tip(ttk.Button(presets_row, text="Eliminar",
                             command=_preset_borrar),
                  "bld_preset_del").pack(side="left")

        def _preset_refrescar_widgets() -> None:
            """Repinta los widgets del asistente desde la data tras
            cargar un preset (los del paso 1 siempre; los del 4 y 5
            sólo si ya existen)."""
            name_entry.delete(0, "end")
            name_entry.insert(0, data.name)
            usage_combo.set(data.usage_type)
            viv_tip_combo.set(data.vivienda_tipologia)
            for entrada, valor in (
                    (viv_dorm_entry, data.vivienda_dormitorios),
                    (viv_banos_entry, data.vivienda_banos),
                    (lot_w_entry, data.lot_width_m),
                    (lot_d_entry, data.lot_depth_m)):
                entrada.delete(0, "end")
                entrada.insert(0, str(valor))
            com_tip_combo.set(data.comercial_tipologia)
            edu_tam_combo.set(data.educacion_tamano)
            for combo, valor in (
                    (construction_combo, data.construction_type),
                    (shape_combo, data.plan_shape),
                    (style_combo, data.architectural_style),
                    (terrain_combo, data.terrain_type),
                    (stairs_combo, data.stairs_mode),
                    (core_combo, data.core_mode),
                    (climate_combo, data.climate),
                    (system_combo, data.structural_system),
                    (orientation_combo, data.facade_orientation)):
                combo.set(valor)
            region_combo.set(
                bwiz.neufert_region_label(data.neufert_region))
            dist_combo.set(bwiz.distribution_label(data.distribucion))
            curv_entry.delete(0, "end")
            curv_entry.insert(0, f"{data.curvatura_m:g}".replace(
                ".", ","))
            seed_entry.delete(0, "end")
            seed_entry.insert(0, str(data.semilla))
            notes_text.delete("1.0", "end")
            if data.notes:
                notes_text.insert("1.0", data.notes)
            try:  # los pasos 4 y 5 quizá aún no están construidos
                corridor_var.set(bool(data.corridor_enabled))
                cross_var.set(bool(data.cross_ventilation))
                for entrada, valor in (
                        (corridor_entry, data.corridor_width_m),
                        (thick_entry, data.wall_thickness_m),
                        (door_w_entry, data.door_width_m),
                        (door_h_entry, data.door_height_m),
                        (win_w_entry, data.window_width_m),
                        (win_h_entry, data.window_height_m),
                        (sill_entry, data.window_sill_m),
                        (eaves_entry, data.eaves_m)):
                    entrada.delete(0, "end")
                    entrada.insert(0, f"{valor:g}".replace(".", ","))
                protect_var.set(bool(data.protection_solar))
                for modulo, variable in inst_vars.items():
                    variable.set(modulo in data.installations)
            except NameError:
                pass

        # -- Paso 2 · niveles -----------------------------------------------
        # v3.32.0 (P3): cada nivel lleva su MULTIPLICADOR «xN» (planta
        # tipo repetida N veces). Al generar, el trazado, los locales,
        # los muros y las cotas de lo que sigue salen multiplicados;
        # con «x1» todo queda como siempre.
        frame2 = ttk.Frame(body)
        _dim(frame2, bwiz.BUILDING_STEPS[1][2])
        level_tree = ttk.Treeview(frame2, height=5, show="headings",
                                  columns=("nivel", "altura", "repetir",
                                           "cota"))
        for col, text, width in (("nivel", "Nivel", 150),
                                 ("altura", "Altura libre (m)", 112),
                                 ("repetir", "Repetir", 68),
                                 ("cota", "Cota (m)", 100)):
            level_tree.heading(col, text=text)
            level_tree.column(col, width=width, anchor="w")
        level_tree.pack(fill="both", expand=True)
        level_new_row = ttk.Frame(frame2)
        level_new_row.pack(fill="x", pady=(6, 2))
        level_name_entry = ttk.Entry(level_new_row, width=22)
        level_name_entry.pack(side="left")
        level_name_entry.insert(0, "Piso 1")
        level_height_entry = ttk.Entry(level_new_row, width=8)
        level_height_entry.pack(side="left", padx=(6, 2))
        level_height_entry.insert(0, "3,0")
        self._tip(level_height_entry, "height_m")
        level_repeat_entry = ttk.Entry(level_new_row, width=4)
        level_repeat_entry.pack(side="left", padx=(6, 0))
        level_repeat_entry.insert(0, "1")
        self._tip(level_repeat_entry, "repeat")
        level_summary = ttk.Label(frame2, text="", justify="left")
        level_summary.pack(anchor="w", pady=(4, 0))

        def _refresh_level_tree() -> None:
            level_tree.delete(*level_tree.get_children())
            elevs = bwiz.level_elevations(data)  # cotas YA expandidas
            idx = 0
            for lv in data.levels:
                n = bwiz.repeat_de(lv)
                level_tree.insert("", "end", values=(
                    lv.name, f"{lv.height_m:.2f}", f"x{n}",
                    f"{elevs[idx]:.2f}"))
                idx += n
            total = sum(bwiz.repeat_de(lv) * lv.height_m
                        for lv in data.levels)
            level_summary.config(
                text=f"{len(bwiz.niveles_expandidos(data))} niveles · "
                     f"altura total {total:.2f} m")

        def _add_level() -> None:
            try:
                height = bwiz.parse_float_es(level_height_entry.get(),
                                             "Altura del nivel")
            except ValueError as exc:
                messagebox.showwarning(
                    "Asistente de edificación", str(exc), parent=dialog)
                return
            rep_txt = level_repeat_entry.get().strip() or "1"
            try:
                repeat = int(rep_txt)
            except ValueError:
                messagebox.showwarning(
                    "Asistente de edificación",
                    f"El multiplicador «{rep_txt}» debe ser un número "
                    f"entero entre 1 y {bwiz.REPEAT_MAX} "
                    "(1 = planta única).",
                    parent=dialog)
                return
            if not 1 <= repeat <= bwiz.REPEAT_MAX:
                messagebox.showwarning(
                    "Asistente de edificación",
                    f"El multiplicador debe estar entre 1 y "
                    f"{bwiz.REPEAT_MAX} (1 = planta única).",
                    parent=dialog)
                return
            name = level_name_entry.get().strip() or "Nivel nuevo"
            data.levels.append(bwiz.LevelSpec(name=name, height_m=height,
                                              repeat=repeat))
            _refresh_level_tree()
            level_name_entry.focus_set()

        def _repetir_seleccionado() -> None:
            selected = level_tree.selection()
            if not selected:
                return
            index = level_tree.index(selected[0])
            from tkinter import simpledialog
            valor = simpledialog.askinteger(
                "Multiplicador de planta",
                f"¿Cuántas veces se repite "
                f"«{data.levels[index].name}»?\n"
                f"(1 = planta única; máximo {bwiz.REPEAT_MAX})",
                parent=dialog, initialvalue=bwiz.repeat_de(
                    data.levels[index]),
                minvalue=1, maxvalue=bwiz.REPEAT_MAX)
            if valor is None:
                return
            data.levels[index].repeat = valor
            _refresh_level_tree()

        def _remove_level() -> None:
            selected = level_tree.selection()
            if not selected or len(data.levels) <= 1:
                return
            index = level_tree.index(selected[0])
            data.levels.pop(index)
            _refresh_level_tree()

        level_buttons = ttk.Frame(frame2)
        level_buttons.pack(fill="x")
        ttk.Button(level_buttons, text="＋ Añadir nivel",
                   command=_add_level).pack(side="left")
        ttk.Button(level_buttons, text="− Quitar seleccionado",
                   command=_remove_level).pack(side="left", padx=(6, 0))
        ttk.Button(level_buttons, text="× Repetir seleccionado...",
                   command=_repetir_seleccionado).pack(side="left",
                                                       padx=(6, 0))

        # -- Paso 3 · locales -------------------------------------------------
        frame3 = ttk.Frame(body)
        _dim(frame3, bwiz.BUILDING_STEPS[2][2])
        room_tree = ttk.Treeview(
            frame3, height=6, show="headings",
            columns=("local", "tipo", "ancho", "fondo", "nivel",
                     "ventana"))
        for col, text, width in (("local", "Local", 120),
                                 ("tipo", "Tipo", 92),
                                 ("ancho", "Ancho", 54),
                                 ("fondo", "Fondo", 54),
                                 ("nivel", "Nivel", 96),
                                 ("ventana", "Ventana", 60)):
            room_tree.heading(col, text=text)
            room_tree.column(col, width=width, anchor="w")
        room_tree.pack(fill="both", expand=True)
        room_new_row = ttk.Frame(frame3)
        room_new_row.pack(fill="x", pady=(6, 2))
        room_name_entry = ttk.Entry(room_new_row, width=15)
        room_name_entry.pack(side="left")
        room_type_combo = ttk.Combobox(room_new_row, width=11,
                                       state="readonly",
                                       values=dna_types)
        room_type_combo.set("ROOM")
        room_type_combo.pack(side="left", padx=(4, 0))
        self._tip(room_type_combo, "space_type")
        room_width_entry = ttk.Entry(room_new_row, width=6)
        room_width_entry.insert(0, "3,0")
        room_width_entry.pack(side="left", padx=(4, 0))
        self._tip(room_width_entry, "width_m")
        room_depth_entry = ttk.Entry(room_new_row, width=6)
        room_depth_entry.insert(0, "3,0")
        room_depth_entry.pack(side="left", padx=(4, 0))
        self._tip(room_depth_entry, "y")
        room_level_combo = ttk.Combobox(room_new_row, width=14,
                                        state="readonly",
                                        values=[lv.name
                                                for lv in data.levels])
        if data.levels:
            room_level_combo.current(0)
        room_level_combo.pack(side="left", padx=(4, 0))
        self._tip(room_level_combo, "level_ref")
        room_window_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(room_new_row, text="Ventana",
                        variable=room_window_var).pack(side="left",
                                                       padx=(6, 0))

        def _refresh_room_tree() -> None:
            room_tree.delete(*room_tree.get_children())
            for r in data.rooms:
                room_tree.insert("", "end", values=(
                    r.name, r.space_type, f"{r.width_m:.2f}",
                    f"{r.depth_m:.2f}", r.level_ref,
                    "Sí" if r.with_window else "No"))

        def _add_room() -> None:
            try:
                width = bwiz.parse_float_es(room_width_entry.get(),
                                            "Ancho")
                depth = bwiz.parse_float_es(room_depth_entry.get(),
                                            "Fondo")
            except ValueError as exc:
                messagebox.showwarning(
                    "Asistente de edificación", str(exc), parent=dialog)
                return
            data.rooms.append(bwiz.RoomSpec(
                name=room_name_entry.get().strip(),
                space_type=room_type_combo.get() or "ROOM",
                width_m=width, depth_m=depth,
                level_ref=room_level_combo.get() or
                (data.levels[0].name if data.levels else ""),
                with_window=room_window_var.get()))
            _refresh_room_tree()
            room_name_entry.delete(0, "end")
            room_name_entry.focus_set()

        def _remove_room() -> None:
            selected = room_tree.selection()
            if not selected:
                return
            data.rooms.pop(room_tree.index(selected[0]))
            _refresh_room_tree()

        def _load_preset(program: str) -> None:
            level_name = data.levels[0].name if data.levels \
                else "Planta Baja"
            data.rooms = bwiz.preset_rooms(program, level_name)
            _refresh_room_tree()
            self._say(f"Programa «{program}» cargado en el paso 3: "
                      "ajusta ancho y fondo a tu gusto.",
                      "Puedes añadir, quitar o editar locales antes de "
                      "continuar")

        def _load_usage() -> None:
            """Carga el programa + relaciones del uso social del paso 1."""
            _collect(0)  # sincroniza el uso social elegido
            rooms, relations = bwiz.apply_usage_program(data)
            # Forma en planta sugerida por el uso social (v2.3.0):
            # SOLO si el usuario no eligió una propia (sigue en la
            # opción por defecto); su elección manual se respeta.
            suggested_shape: str = ""
            if data.plan_shape == bwiz.PLAN_SHAPES[0]:
                suggested_shape = bwiz.suggested_plan_shape(
                    data.usage_type)
                if suggested_shape in bwiz.PLAN_SHAPES:
                    shape_combo.set(suggested_shape)
                    data.plan_shape = suggested_shape
            # Estilo arquitectónico sugerido por el uso social
            # (v2.4.0): misma regla amable, solo si sigue el defecto.
            suggested_style: str = ""
            if data.architectural_style == bwiz.ARCHITECTURAL_STYLES[0]:
                suggested_style = bwiz.suggested_architectural_style(
                    data.usage_type)
                if suggested_style in bwiz.ARCHITECTURAL_STYLES:
                    style_combo.set(suggested_style)
                    data.architectural_style = suggested_style
            # NORMATIVA NEUFERT (v2.7.0): sube pasillo, puerta y muro a
            # lo que el libro pide para el uso (nunca baja lo pedido) y
            # sincroniza los campos del paso 4 si ya están creados.
            neufert_changes = bwiz.apply_neufert_defaults(data)
            if neufert_changes:
                try:
                    corridor_entry.delete(0, "end")
                    corridor_entry.insert(
                        0, f"{data.corridor_width_m:.2f}".replace(".", ","))
                    door_w_entry.delete(0, "end")
                    door_w_entry.insert(
                        0, f"{data.door_width_m:.2f}".replace(".", ","))
                except NameError:
                    pass  # los campos del paso 4 aún no existen
            # El programa hospitalario puede añadir niveles (v2.2.0):
            # refresca el árbol de niveles y los combos dependientes.
            room_level_combo["values"] = [lv.name for lv in data.levels]
            if data.levels:
                room_level_combo.set(data.levels[0].name)
            rel_a_combo["values"] = data.room_names()
            rel_b_combo["values"] = data.room_names()
            _refresh_level_tree()
            _refresh_room_tree()
            _refresh_relation_tree()
            extra = ""
            if suggested_shape:
                extra += f" Forma en planta sugerida: {suggested_shape}."
            if suggested_style:
                extra += f" Estilo sugerido: {suggested_style}."
            if neufert_changes:
                extra += (" Normativa Neufert aplicada: "
                          + ", ".join(neufert_changes) + ".")
            _edicion_nombre = bwiz.neufert_region_name(
                data.neufert_region)
            if (data.neufert_region
                    and data.neufert_region
                    != bwiz.NEUFERT_REGION_BASE
                    and _edicion_nombre):
                extra += f" Edición Neufert: {_edicion_nombre}."
            self._say(f"Programa del uso «{data.usage_type}» cargado: "
                      f"{rooms} locales y {relations} relaciones "
                      f"sugeridas en {len(data.levels)} nivel(es).",
                      bwiz.USAGE_HINTS.get(data.usage_type, "") + extra)

        room_buttons = ttk.Frame(frame3)
        room_buttons.pack(fill="x")
        ttk.Button(room_buttons, text="＋ Añadir local",
                   command=_add_room).pack(side="left")
        ttk.Button(room_buttons, text="− Quitar seleccionado",
                   command=_remove_room).pack(side="left", padx=(6, 0))
        ttk.Button(room_buttons, text="✨ Sugerir según el uso social",
                   command=_load_usage).pack(side="left", padx=(12, 0))
        ttk.Button(room_buttons, text="Programa: Vivienda",
                   command=lambda: _load_preset("Vivienda")).pack(
            side="left", padx=(6, 0))
        ttk.Button(room_buttons, text="Programa: Oficina",
                   command=lambda: _load_preset("Oficina")).pack(
            side="left", padx=(6, 0))
        ttk.Button(room_buttons, text="Programa: Policlínico",
                   command=lambda: _load_preset("Policlínico")).pack(
            side="left", padx=(6, 0))

        # -- Paso 4 · relaciones espaciales + vanos --------------------------
        frame4 = ttk.Frame(body)
        _dim(frame4, bwiz.BUILDING_STEPS[3][2])
        relation_tree = ttk.Treeview(frame4, height=4, show="headings",
                                     columns=("a", "b", "tipo", "puerta"))
        for col, text, width in (("a", "Local A", 110),
                                 ("b", "Local B", 110),
                                 ("tipo", "Relación", 150),
                                 ("puerta", "¿Puerta?", 70)):
            relation_tree.heading(col, text=text)
            relation_tree.column(col, width=width, anchor="w")
        relation_tree.pack(fill="both", expand=True)
        relation_new_row = ttk.Frame(frame4)
        relation_new_row.pack(fill="x", pady=(6, 2))
        rel_a_combo = ttk.Combobox(relation_new_row, width=14,
                                   state="readonly",
                                   values=[r.name for r in data.rooms])
        rel_a_combo.pack(side="left")
        rel_b_combo = ttk.Combobox(relation_new_row, width=14,
                                   state="readonly",
                                   values=[r.name for r in data.rooms])
        rel_b_combo.pack(side="left", padx=(4, 0))
        rel_kind_combo = ttk.Combobox(
            relation_new_row, width=22, state="readonly",
            values=[label for label, _kind in bwiz.RELATION_KINDS_ES])
        rel_kind_combo.current(0)
        rel_kind_combo.pack(side="left", padx=(4, 0))
        rel_door_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(relation_new_row, text="Puerta",
                        variable=rel_door_var).pack(side="left",
                                                    padx=(6, 0))

        def _refresh_relation_tree() -> None:
            relation_tree.delete(*relation_tree.get_children())
            for rel in data.relations:
                relation_tree.insert("", "end", values=(
                    rel.a_name, rel.b_name, rel.kind_es,
                    "Sí" if rel.with_door else "No"))

        def _add_relation() -> None:
            data.relations.append(bwiz.RelationSpec(
                a_name=rel_a_combo.get(), b_name=rel_b_combo.get(),
                kind_es=rel_kind_combo.get() or "Adyacente a",
                with_door=rel_door_var.get()))
            _refresh_relation_tree()

        def _remove_relation() -> None:
            selected = relation_tree.selection()
            if not selected:
                return
            data.relations.pop(relation_tree.index(selected[0]))
            _refresh_relation_tree()

        def _suggest_relations() -> None:
            _collect(3)  # sincroniza lo tecleado antes de sugerir
            for suggestion in bwiz.suggest_relations(data):
                data.relations.append(suggestion)
            _refresh_relation_tree()
            self._say("Relaciones sugeridas añadidas según el tipo de "
                      "cada local.",
                      "Revísalas en la tabla: puedes quitar las que no "
                      "quieras")

        relation_buttons = ttk.Frame(frame4)
        relation_buttons.pack(fill="x")
        ttk.Button(relation_buttons, text="＋ Añadir relación",
                   command=_add_relation).pack(side="left")
        ttk.Button(relation_buttons, text="− Quitar seleccionada",
                   command=_remove_relation).pack(side="left",
                                                  padx=(6, 0))
        ttk.Button(relation_buttons, text="Sugerir del conocimiento "
                                          "técnico",
                   command=_suggest_relations).pack(side="left",
                                                    padx=(12, 0))

        vanos_box = ttk.LabelFrame(frame4, text="Puertas, ventanas y "
                                                "reglas de trazado")
        vanos_box.pack(fill="x", pady=(8, 0))
        vanos_grid = ttk.Frame(vanos_box)
        vanos_grid.pack(fill="x", pady=2)
        corridor_var = tk.BooleanVar(value=data.corridor_enabled)
        ttk.Checkbutton(vanos_grid, text="Pasillo (conecta todos los "
                                         "locales)",
                        variable=corridor_var).grid(
            row=0, column=0, columnspan=2, sticky="w")
        thick_entry = _grid_entry(vanos_grid, 1, 0, "Espesor muros (m)",
                                  f"{data.wall_thickness_m:.2f}".replace(
                                      ".", ","), "thickness_m")
        corridor_entry = _grid_entry(vanos_grid, 1, 2,
                                     "Ancho pasillo (m)",
                                     f"{data.corridor_width_m:.2f}".replace(
                                         ".", ","), "width_m")
        door_w_entry = _grid_entry(vanos_grid, 2, 0, "Puerta · ancho (m)",
                                   f"{data.door_width_m:.2f}".replace(
                                       ".", ","), "width_m")
        door_h_entry = _grid_entry(vanos_grid, 2, 2, "Puerta · alto (m)",
                                   f"{data.door_height_m:.2f}".replace(
                                       ".", ","), "height_m")
        win_w_entry = _grid_entry(vanos_grid, 3, 0, "Ventana · ancho (m)",
                                  f"{data.window_width_m:.2f}".replace(
                                      ".", ","), "width_m")
        win_h_entry = _grid_entry(vanos_grid, 3, 2, "Ventana · alto (m)",
                                  f"{data.window_height_m:.2f}".replace(
                                      ".", ","), "height_m")
        sill_entry = _grid_entry(vanos_grid, 4, 0, "Antepecho (m)",
                                 f"{data.window_sill_m:.2f}".replace(
                                     ".", ","), "sill_height_m")

        # -- Paso 5 · bioclimática e instalaciones ---------------------------
        frame5 = ttk.Frame(body)
        _dim(frame5, bwiz.BUILDING_STEPS[4][2])
        bio_box = ttk.LabelFrame(frame5, text="Requerimientos bioclimáticos")
        bio_box.pack(fill="x", pady=(0, 8))
        cross_var = tk.BooleanVar(value=data.cross_ventilation)
        ttk.Checkbutton(bio_box, text="Ventilación cruzada "
                                      "(dos frentes de fachada)",
                        variable=cross_var).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(2, 0))
        protect_var = tk.BooleanVar(value=data.protection_solar)
        ttk.Checkbutton(bio_box, text="Protección solar con aleros "
                                      "sobre la fachada",
                        variable=protect_var).grid(
            row=1, column=0, columnspan=2, sticky="w")
        eaves_entry = _grid_entry(bio_box, 2, 0, "Alero (m)",
                                  f"{data.eaves_m:.2f}".replace(".", ","),
                                  "bld_eaves")
        inst_box = ttk.LabelFrame(frame5, text="Módulos de instalaciones "
                                                "y equipamiento")
        inst_box.pack(fill="x")
        inst_grid = ttk.Frame(inst_box)
        inst_grid.pack(fill="x", pady=4)
        inst_vars: Dict[str, tk.BooleanVar] = {}
        for _index, _module in enumerate(bwiz.INSTALLATION_MODULES):
            _var = tk.BooleanVar(value=_module in data.installations)
            inst_vars[_module] = _var
            ttk.Checkbutton(inst_grid, text=_module,
                            variable=_var).grid(
                row=_index // 2, column=_index % 2, sticky="w",
                padx=(0, 16), pady=2)

        def _suggest_installations() -> None:
            """Módulos razonables para el uso social (v2.2.0)."""
            _collect(0)  # sincroniza el uso social del paso 1
            sugeridos = bwiz.suggested_installations(data.usage_type)
            data.installations = [module for module
                                  in bwiz.INSTALLATION_MODULES
                                  if module in sugeridos]
            for module, var in inst_vars.items():
                var.set(module in data.installations)
            self._say(f"Módulos sugeridos para «{data.usage_type}»: "
                      + (", ".join(data.installations)
                         if data.installations else "ninguno"),
                      "Marca o desmarca a mano lo que quieras antes "
                      "de generar")

        ttk.Button(inst_box, text="✨ Sugerir módulos del uso social",
                   command=_suggest_installations).pack(anchor="w",
                                                       pady=(0, 4))
        self._tip(inst_box, "bld_inst")

        # -- Paso 6 · variantes de planta ------------------------------------
        frame6 = ttk.Frame(body)
        _dim(frame6, bwiz.BUILDING_STEPS[5][2])
        variant_row = ttk.Frame(frame6)
        variant_row.pack(fill="x", pady=(0, 4))
        variant_tree = ttk.Treeview(variant_row, height=6, show="headings",
                                    columns=("n", "titulo", "score",
                                             "cabe", "coste"))
        for col, text, width, anchor in (
                ("n", "#", 28, "w"),
                ("titulo", "Variante", 210, "w"),
                ("score", "Puntuación", 80, "e"),
                ("cabe", "Dimensiones", 140, "w"),
                ("coste", "Coste (CUP)", 100, "e")):
            variant_tree.heading(col, text=text)
            variant_tree.column(col, width=width, anchor=anchor)
        variant_tree.pack(side="left", fill="both", expand=True)
        self._tip(variant_tree, "bld_variants")
        cost_row = ttk.Frame(frame6)
        cost_row.pack(fill="x", pady=(2, 0))
        ttk.Label(cost_row, text="Calidad de acabados:",
                  style="Dim.TLabel").pack(side="left")
        calidad_var = tk.StringVar(value=vbudget.CALIDAD_DEFECTO)
        calidad_combo = ttk.Combobox(cost_row, textvariable=calidad_var,
                                     state="readonly", width=11,
                                     values=list(vbudget.CALIDADES))
        calidad_combo.pack(side="left", padx=(4, 8))
        self._tip(calidad_combo, "calidad_coste")
        ttk.Label(cost_row,
                  text="Coste estimado con el catálogo PRECONS III; "
                       "se recalcula al cambiarla.",
                  style="Dim.TLabel").pack(side="left")
        variant_canvas = tk.Canvas(frame6, height=240,
                                   background=theme.COL_BG,
                                   highlightthickness=1,
                                   highlightbackground=theme.COL_BORDER)
        variant_canvas.pack(fill="x", pady=(4, 4))
        variant_desc = ttk.Label(frame6, text="Pulsa «⚡ Generar variantes "
                                              "de planta» para ver las "
                                              "distribuciones posibles.",
                                 style="Dim.TLabel", wraplength=520,
                                 justify="left")
        variant_desc.pack(fill="x")

        # Selector de VISTA técnica (v2.6.0): planta, elevación,
        # corte o detalles constructivos, exportables a SVG.
        view_row = ttk.Frame(frame6)
        view_row.pack(fill="x", pady=(0, 4))
        ttk.Label(view_row, text="Vista:",
                  style="Dim.TLabel").pack(side="left")
        view_combo = ttk.Combobox(view_row, state="readonly", width=11,
                                  values=["Planta", "Elevación", "Corte",
                                          "Detalles"])
        view_combo.current(0)
        view_combo.pack(side="left", padx=(4, 10))
        aux_label = ttk.Label(view_row, text="fachada:",
                              style="Dim.TLabel")
        aux_label.pack(side="left")
        aux_combo = ttk.Combobox(view_row, state="readonly", width=13,
                                 values=["Norte", "Sur", "Este", "Oeste"])
        aux_combo.set("Norte")
        aux_combo.pack(side="left", padx=(4, 10))
        self._tip(view_combo, "bld_views")

        def _sync_aux() -> None:
            """El combo auxiliar cambia según la vista elegida."""
            view = view_combo.get()
            if view == "Elevación":
                aux_label.configure(text="fachada:")
                aux_combo.configure(values=["Norte", "Sur", "Este",
                                            "Oeste"])
                if aux_combo.get() not in ("Norte", "Sur", "Este", "Oeste"):
                    aux_combo.set("Norte")
            elif view == "Corte":
                aux_label.configure(text="eje:")
                aux_combo.configure(values=["Transversal",
                                            "Longitudinal"])
                if aux_combo.get() not in ("Transversal", "Longitudinal"):
                    aux_combo.set("Transversal")
            else:
                aux_label.configure(text="")
                aux_combo.configure(values=["—"])
                aux_combo.set("—")

        def _export_view(fmt: str) -> None:
            """Exporta la vista activa de la variante al formato pedido."""
            variant = state.get("variant")
            if variant is None or not variant.layouts:
                self._say("Genera y elige una variante antes de "
                          "exportar la vista.",
                          f"El {fmt.upper()} sale de la variante "
                          "seleccionada")
                return
            view = view_combo.get()
            suffix = aux_combo.get() if view in ("Elevación", "Corte") \
                and aux_combo.get() != "—" else ""
            base = (data.name or "edificacion").replace(" ", "_")
            initial = f"{base}_{view}_{suffix}.{fmt}".replace("__", "_")
            descriptions = {
                "svg": ("SVG vectorial", "*.svg"),
                "png": ("PNG imagen", "*.png"),
                "pdf": ("PDF imprimible", "*.pdf"),
            }
            desc, pattern = descriptions.get(fmt, descriptions["svg"])
            path = filedialog.asksaveasfilename(
                defaultextension=f".{fmt}", initialfile=initial,
                filetypes=[(desc, pattern)])
            if not path:
                return
            try:
                from exporters import view_exporter
                view_exporter.export_view(
                    variant, data, path, view=view,
                    aux=suffix if suffix else "",
                    title=f"{data.name} — {view} {suffix}".strip())
                detalles = {
                    "svg": "El SVG es vectorial: escala sin perder "
                           "calidad e imprime a la medida que quieras",
                    "png": "El PNG sirve para informes, presentaciones "
                           "y mensajería: listo para pegar",
                    "pdf": "El PDF sale a A4 apaisado con cajetín y "
                           "escala: listo para imprimir",
                }
                self._say(f"Vista «{view} {suffix}» exportada a "
                          f"{fmt.upper()}: {path}",
                          detalles.get(fmt, ""))
            except Exception as exc:  # noqa: BLE001 — aviso amable
                self._say(f"No pude exportar el {fmt.upper()} de la "
                          "vista.", str(exc))

        def _export_view_svg() -> None:
            _export_view("svg")

        def _export_view_png() -> None:
            _export_view("png")

        def _export_view_pdf() -> None:
            _export_view("pdf")

        ttk.Button(view_row, text="⤓ SVG",
                   command=_export_view_svg).pack(side="right")
        ttk.Button(view_row, text="⤓ PNG",
                   command=_export_view_png).pack(side="right",
                                                  padx=(0, 6))
        ttk.Button(view_row, text="⤓ PDF",
                   command=_export_view_pdf).pack(side="right",
                                                  padx=(0, 6))

        # VÍNCULO DETALLE ↔ TIPOLOGÍA (v3.6.0): abre la biblioteca de
        # detalles pre-filtrada a la tipología constructiva elegida en
        # el paso 1 — los recomendados, adaptados a la edición activa.
        def _open_detalles_tipologia() -> None:
            self.open_detalles(tipologia=data.construction_type)

        btn_detalles = ttk.Button(view_row, text="Detalles constructivos…",
                                  command=_open_detalles_tipologia)
        btn_detalles.pack(side="left", padx=(10, 0))
        self._tip(btn_detalles, "bld_detalles")

        def _refresh_variant_tree() -> None:
            variant_tree.delete(*variant_tree.get_children())
            for variant in state["variants"]:
                coste = getattr(variant, "cost", None)
                texto = vbudget.fmt_cup(coste.total) \
                    if coste is not None else "—"
                variant_tree.insert("", "end", iid=variant.key, values=(
                    variant.rank, variant.title,
                    f"{variant.score:.0f}", variant.fits_text, texto))
            if state["variant"] is not None:
                try:
                    variant_tree.selection_set(state["variant"].key)
                except Exception:  # noqa: BLE001 — iid no presente
                    pass

        def _render_prims(canvas: Any, drawing: "rep.Drawing") -> None:
            """Render genérico de primitivas (elevación/corte/detalles).

            Misma fuente de verdad que el exportador SVG: metros,
            eje Y hacia arriba, tramas y arcos idénticos.
            """
            canvas.delete("all")
            bx0, by0, bx1, by1 = drawing.bounds()
            width = max(canvas.winfo_width(), 380)
            height = max(canvas.winfo_height(), 200)
            margin = 18
            scale = min((width - 2 * margin) / max(bx1 - bx0, 0.1),
                        (height - 2 * margin) / max(by1 - by0, 0.1))
            ox = margin + ((width - 2 * margin) - (bx1 - bx0) * scale) / 2 \
                - bx0 * scale
            oy = height - margin - ((height - 2 * margin)
                                    - (by1 - by0) * scale) / 2 \
                + by0 * scale

            def px(value: float) -> float:
                return ox + value * scale

            def py(value: float) -> float:
                return oy - value * scale

            # Hoja de papel detrás (contraste con el tema oscuro).
            canvas.create_rectangle(px(bx0), py(by1), px(bx1), py(by0),
                                    fill="#fafafa",
                                    outline=theme.COL_BORDER, width=1)
            import math as _math
            for prim in drawing.prims:
                if isinstance(prim, rep.PLine):
                    canvas.create_line(px(prim.x1), py(prim.y1),
                                       px(prim.x2), py(prim.y2),
                                       fill=prim.color,
                                       width=max(1, round(prim.width)),
                                       dash=tuple(
                                           max(1, int(d * scale))
                                           for d in prim.dash)
                                       if prim.dash else (),
                                       tags=(prim.tag,) if prim.tag else ())
                elif isinstance(prim, rep.PRect):
                    canvas.create_rectangle(px(prim.x), py(prim.y + prim.d),
                                            px(prim.x + prim.w),
                                            py(prim.y),
                                            fill=prim.fill or "",
                                            outline=prim.stroke,
                                            width=max(1, round(
                                                prim.stroke_width)),
                                            dash=tuple(
                                                max(1, int(d * scale))
                                                for d in prim.dash)
                                            if prim.dash else (),
                                            tags=(prim.tag,)
                                            if prim.tag else ())
                    if prim.hatch:
                        pattern_color = rep.HATCH_PATTERNS[prim.hatch].color
                        for (hx1, hy1), (hx2, hy2) in \
                                rep.hatch_segments(prim.x, prim.y,
                                                   prim.w, prim.d,
                                                   prim.hatch):
                            canvas.create_line(px(hx1), py(hy1),
                                               px(hx2), py(hy2),
                                               fill=pattern_color,
                                               width=1,
                                               tags=(prim.tag,)
                                               if prim.tag else ())
                elif isinstance(prim, rep.PText):
                    size = max(7, min(14, int(prim.size * scale * 0.55)))
                    anchor = {"middle": "center", "start": "w",
                              "end": "e"}.get(prim.anchor, "center")
                    font = ("TkDefaultFont", size,
                            "bold" if prim.bold else "normal")
                    canvas.create_text(px(prim.x), py(prim.y),
                                       text=prim.text, fill=prim.color,
                                       anchor=anchor, font=font,
                                       tags=(prim.tag,) if prim.tag else ())
                elif isinstance(prim, rep.PArc):
                    tk_start = -prim.start_deg
                    tk_extent = -prim.extent_deg
                    canvas.create_arc(
                        px(prim.cx - prim.r), py(prim.cy + prim.r),
                        px(prim.cx + prim.r), py(prim.cy - prim.r),
                        start=tk_start, extent=tk_extent, style="arc",
                        outline=prim.color, width=max(1, round(prim.width)),
                        dash=tuple(max(1, int(d * scale))
                                   for d in prim.dash)
                        if prim.dash else (),
                        tags=(prim.tag,) if prim.tag else ())
            _ = _math  # reservado para futuras curvas

        def _draw_plan(canvas: Any, variant) -> None:
            """Planta técnica del primer nivel (enriquecida v2.6.0)."""
            canvas.delete("all")
            layout = variant.layouts[0]
            width = max(canvas.winfo_width(), 380)
            height = max(canvas.winfo_height(), 200)
            min_x, min_y, max_x, max_y = \
                bwiz._bounds_of_layouts(variant.layouts)
            span_w = max(max_x - min_x, 1.0)
            span_h = max(max_y - min_y, 1.0)
            margin = 22
            scale = min((width - 2 * margin) / span_w,
                        (height - 2 * margin) / span_h)

            def tx(value: float) -> float:
                return margin + (value - min_x) * scale

            def ty(value: float) -> float:
                return height - margin - (value - min_y) * scale

            for pr in layout.all_rooms:
                if pr.is_corridor:
                    fill = ("#4a5d43" if pr.space_type == "PATIO"
                            else "#3d4a5c")
                elif pr.space_type in ("KITCHEN", "BATHROOM"):
                    fill = "#37505e"
                else:
                    fill = "#546a7b"
                x0, y0 = tx(pr.x), ty(pr.y + pr.d)
                x1, y1 = tx(pr.x + pr.w), ty(pr.y)
                canvas.create_rectangle(x0, y0, x1, y1, fill=fill,
                                        outline="#e2e8f0", width=1)
                if (x1 - x0) > 34 and (y1 - y0) > 16:
                    canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2 - 7,
                                       text=pr.name, fill="#f7fafc",
                                       font=("TkDefaultFont", 8))
                    canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2 + 7,
                                       text=f"{pr.area_m2():.1f} m²",
                                       fill="#a0aec0",
                                       font=("TkDefaultFont", 7))

            # MUROS con trama según el material (v2.6.0): envolvente
            # hatched, particiones en poché claro.
            thickness = data.wall_thickness_m
            hatch_key = rep.hatch_key_for(data.construction_type)
            pattern = rep.HATCH_PATTERNS[hatch_key]
            try:
                flags = rep.exterior_wall_flags(layout)
            except Exception:  # noqa: BLE001 — sin trama si algo falla
                flags = [False] * len(layout.walls)
            for index, wall in enumerate(layout.walls):
                wx, wy, ww, wd = rep.wall_rect(wall, thickness)
                canvas.create_rectangle(
                    tx(wx), ty(wy + wd), tx(wx + ww), ty(wy),
                    fill="#e2e8f0" if flags[index] else "#8fa3b0",
                    outline="", width=0,
                    tags=("muro", "trama" if flags[index] else ""))
                if flags[index]:
                    for (hx1, hy1), (hx2, hy2) in \
                            rep.hatch_segments(wx, wy, ww, wd, hatch_key):
                        canvas.create_line(tx(hx1), ty(hy1),
                                           tx(hx2), ty(hy2),
                                           fill="#6b4f3a", width=1,
                                           tags=("muro", "trama"))

            # COLUMNAS según la tipología constructiva (v2.6.0).
            try:
                columns = st.column_placements([layout], data)
            except Exception:  # noqa: BLE001 — sin columnas si algo falla
                columns = []
            for column in columns:
                cx0, cy0 = tx(column.x), ty(column.y + column.d)
                cx1, cy1 = tx(column.x + column.w), ty(column.y)
                canvas.create_rectangle(cx0, cy0, cx1, cy1,
                                        fill="#e2e8f0",
                                        outline="#1a202c", width=1,
                                        tags=("columna",))
                canvas.create_line(cx0, cy0, cx1, cy1, fill="#1a202c",
                                   width=1, tags=("columna",))
                canvas.create_line(cx0, cy1, cx1, cy0, fill="#1a202c",
                                   width=1, tags=("columna",))

            for opening in layout.doors + layout.windows:
                if not (0 <= opening.wall_index < len(layout.walls)):
                    continue
                wall = layout.walls[opening.wall_index]
                (sx, sy), (ex, ey) = wall["start"], wall["end"]
                if abs(sy - ey) <= 1e-6:  # horizontal
                    px, py = sx + opening.offset_m, sy
                    dx, dy = opening.width_m, 0.0
                else:  # vertical
                    px, py = sx, sy + opening.offset_m
                    dx, dy = 0.0, opening.width_m
                color = "#f6ad55" if opening.is_door else "#63b3ed"
                canvas.create_line(tx(px), ty(py), tx(px + dx),
                                   ty(py + dy), fill=color, width=3,
                                   tags=("vano",))
                # ARCO de giro de puertas (v2.6.0).
                if opening.is_door:
                    arc, leaf = rep._door_arc(layout, opening, wall,
                                              thickness)
                    if arc is not None:
                        canvas.create_arc(
                            tx(arc.cx - arc.r), ty(arc.cy + arc.r),
                            tx(arc.cx + arc.r), ty(arc.cy - arc.r),
                            start=-arc.start_deg, extent=-arc.extent_deg,
                            style="arc", outline="#f6ad55", width=1,
                            dash=(3, 2), tags=("vano", "arco"))
                        canvas.create_line(tx(leaf.x1), ty(leaf.y1),
                                           tx(leaf.x2), ty(leaf.y2),
                                           fill="#f6ad55", width=1,
                                           tags=("vano", "arco"))

            # ALEROS dibujados (v2.4.0): contorno del edificio desplazado
            # hacia fuera según el alero del paso 5, solo con protección
            # solar activada; línea discontinua ámbar con leyenda.
            if data.protection_solar and data.eaves_m > 0:
                for x1, y1, x2, y2 in geom.eaves_outline_segments(
                        layout.all_rooms, data.eaves_m):
                    canvas.create_line(tx(x1), ty(y1), tx(x2), ty(y2),
                                       fill="#ecc94b", width=2,
                                       dash=(5, 3), tags=("alero",))
                canvas.create_text(10, height - 8, anchor="sw",
                                   text="– – – alero "
                                        f"{data.eaves_m:.2f} m"
                                        .replace(".", ","),
                                   fill="#ecc94b",
                                   font=("TkDefaultFont", 7),
                                   tags=("alero",))

            # NORTE (girado según la fachada principal), cotas totales
            # y escala gráfica (v2.6.0).
            import math as _math
            north_angle = _math.radians(rep._north_angle(
                data.facade_orientation))
            nx, ny = width - 26, 30
            canvas.create_line(nx, ny, nx + 11 * _math.sin(north_angle),
                               ny - 11 * _math.cos(north_angle),
                               fill="#e2e8f0", width=2,
                               arrow="last", tags=("norte",))
            canvas.create_text(nx + 2, ny + 12, text="N",
                               fill="#e2e8f0",
                               font=("TkDefaultFont", 8, "bold"),
                               tags=("norte",))
            dim_y = ty(min_y) + 14
            canvas.create_line(tx(min_x), dim_y, tx(max_x), dim_y,
                               fill="#cbd5e0", width=1,
                               arrow="both", tags=("cota",))
            canvas.create_text((tx(min_x) + tx(max_x)) / 2, dim_y + 8,
                               text=f"{span_w:.2f} m".replace(".", ","),
                               fill="#cbd5e0", font=("TkDefaultFont", 7),
                               tags=("cota",))
            scale_x0, scale_y = 12, height - 22
            for step in range(5):
                canvas.create_rectangle(scale_x0 + step * scale, scale_y,
                                        scale_x0 + (step + 1) * scale,
                                        scale_y + 5,
                                        fill="#e2e8f0"
                                        if step % 2 == 0 else "",
                                        outline="#cbd5e0", width=1,
                                        tags=("escala",))
            canvas.create_text(scale_x0 + 2.5 * scale, scale_y + 12,
                               text="escala 0–5 m", fill="#a0aec0",
                               font=("TkDefaultFont", 7),
                               tags=("escala",))

        def _draw_variant() -> None:
            """Dibuja la VISTA activa de la variante elegida (v2.6.0)."""
            canvas = variant_canvas
            variant = state.get("variant")
            if variant is None or not variant.layouts:
                canvas.delete("all")
                return
            view = view_combo.get()
            aux = aux_combo.get() if aux_combo.get() != "—" else ""
            if view == "Elevación":
                _render_prims(canvas,
                              rep.elevation_view(variant, data,
                                                 aux or "Norte"))
                return
            if view == "Corte":
                _render_prims(canvas,
                              rep.section_view(variant, data,
                                               aux or "Transversal"))
                return
            if view == "Detalles":
                from exporters import view_exporter
                _render_prims(canvas,
                              view_exporter._details_drawing(data))
                return
            _draw_plan(canvas, variant)

        def _coste_desc(variant: Any) -> str:
            """Frase de coste para la descripción de la variante."""
            coste = getattr(variant, "cost", None)
            if coste is None:
                return ""
            desglose = vbudget.desglose_texto(coste)
            extra = f" Desglose: {desglose}." if desglose else ""
            return (f" Estimación PRECONS: {vbudget.fmt_cup(coste.total)} "
                    f"CUP ({vbudget.fmt_cup(coste.cost_m2)} CUP/m²)."
                    + extra)

        def _generate_variants() -> None:
            """Calcula todas las variantes con los datos vigentes."""
            _collect(2)
            _collect(3)
            state["variants"] = bwiz.generate_variants(data)
            state["variant"] = state["variants"][0] \
                if state["variants"] else None
            self._variantes_costear(data, state["variants"],
                                    calidad_var.get())
            _refresh_variant_tree()
            _draw_variant()
            best = state["variant"]
            if best is not None:
                metrics = " · ".join(
                    f"{name} {value * 100:.0f}%"
                    for name, value in best.metrics.items())
                variant_desc.configure(
                    text=f"Recomendada: {best.title} "
                         f"({best.score:.0f}/100). {best.description} "
                         f"Métricas: {metrics}." + _coste_desc(best))
            else:
                variant_desc.configure(
                    text="No pude generar variantes: revisa el paso de "
                         "locales.")

        def _choose_variant(_event: Any = None) -> None:
            selection = variant_tree.selection()
            if not selection:
                return
            for variant in state["variants"]:
                if variant.key == selection[0]:
                    state["variant"] = variant
                    break
            _draw_variant()
            variant = state.get("variant")
            if variant is not None:
                metrics = " · ".join(
                    f"{name} {value * 100:.0f}%"
                    for name, value in variant.metrics.items())
                variant_desc.configure(
                    text=f"{variant.title} ({variant.score:.0f}/100): "
                         f"{variant.description} Métricas: {metrics}."
                         + _coste_desc(variant))

        ttk.Button(variant_row, text="⚡ Generar variantes\nde planta",
                   command=_generate_variants).pack(
            side="left", fill="y", padx=(8, 0))
        ttk.Button(variant_row, text="Comparar variantes",
                   command=lambda: self._comparar_variantes(
                       state, dialog)).pack(
            side="left", fill="y", padx=(8, 0))
        variant_tree.bind("<<TreeviewSelect>>", _choose_variant)

        def _coste_on_calidad(_event: Any = None) -> None:
            """Calidad de acabados cambiada: recostea lo generado."""
            if not state["variants"]:
                return
            self._variantes_costear(data, state["variants"],
                                    calidad_var.get())
            _refresh_variant_tree()
            if state.get("variant") is not None:
                variant = state["variant"]
                metrics = " · ".join(
                    f"{name} {value * 100:.0f}%"
                    for name, value in variant.metrics.items())
                variant_desc.configure(
                    text=f"{variant.title} ({variant.score:.0f}/100): "
                         f"{variant.description} Métricas: {metrics}."
                         + _coste_desc(variant))
            self._say(f"Calidad «{calidad_var.get()}»: costes "
                      "recalculados al vivo.")

        calidad_combo.bind("<<ComboboxSelected>>", _coste_on_calidad)
        view_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: (_sync_aux(), _draw_variant()))
        aux_combo.bind("<<ComboboxSelected>>",
                       lambda _e: _draw_variant())

        # -- Paso 7 · resumen -----------------------------------------------
        frame7 = ttk.Frame(body)
        summary = tk.Text(frame7, height=15, width=64, wrap="word",
                          background=theme.COL_FIELD,
                          foreground=theme.COL_TEXT, relief="flat",
                          padx=10, pady=8)
        summary.pack(fill="both", expand=True)
        summary.configure(state="disabled")

        frames = (frame1, frame2, frame3, frame4, frame5, frame6, frame7)
        state = {"step": 0, "variants": [], "variant": None}

        def _sync_room_level_choices() -> None:
            names = [lv.name for lv in data.levels]
            room_level_combo.configure(values=names)
            if names and room_level_combo.get() not in names:
                room_level_combo.current(0)
            rel_names = [r.name for r in data.rooms]
            rel_a_combo.configure(values=rel_names)
            rel_b_combo.configure(values=rel_names)

        def _collect(step: int) -> List[str]:
            """Vuelca el formulario/árboles del paso en data."""
            errors: List[str] = []
            if step == 0:
                values = {
                    "name": name_entry.get(),
                    "usage_type": usage_combo.get(),
                    "vivienda_tipologia": viv_tip_combo.get(),
                    "vivienda_dormitorios": viv_dorm_entry.get(),
                    "vivienda_banos": viv_banos_entry.get(),
                    "comercial_tipologia": com_tip_combo.get(),
                    "educacion_tamano": edu_tam_combo.get(),
                    "construction_type": construction_combo.get(),
                    "plan_shape": shape_combo.get(),
                    "architectural_style": style_combo.get(),
                    "terrain_type": terrain_combo.get(),
                    "stairs_mode": stairs_combo.get(),
                    "core_mode": core_combo.get(),
                    "lot_width_m": lot_w_entry.get(),
                    "lot_depth_m": lot_d_entry.get(),
                    "climate": climate_combo.get(),
                    "structural_system": system_combo.get(),
                    "facade_orientation": orientation_combo.get(),
                    "neufert_region": bwiz.neufert_region_code(
                        region_combo.get()),
                    "distribucion": bwiz.distribution_code(
                        dist_combo.get()),
                    "curvatura_m": curv_entry.get(),
                    "semilla": seed_entry.get(),
                    "notes": notes_text.get("1.0", "end").strip(),
                }
                errors.extend(bwiz.data_from_values(0, values, data))
                errors.extend(bwiz.validate_step(0, data))
            elif step == 1:
                errors.extend(bwiz.validate_step(1, data))
            elif step == 2:
                errors.extend(bwiz.validate_step(2, data))
            elif step == 3:
                values = {
                    "corridor_enabled": corridor_var.get(),
                    "cross_ventilation": cross_var.get(),
                    "corridor_width_m": corridor_entry.get(),
                    "wall_thickness_m": thick_entry.get(),
                    "door_width_m": door_w_entry.get(),
                    "door_height_m": door_h_entry.get(),
                    "window_width_m": win_w_entry.get(),
                    "window_height_m": win_h_entry.get(),
                    "window_sill_m": sill_entry.get(),
                }
                errors.extend(bwiz.data_from_values(3, values, data))
                errors.extend(bwiz.validate_step(3, data))
            elif step == 4:
                values = {
                    "protection_solar": protect_var.get(),
                    "eaves_m": eaves_entry.get(),
                    "installations": [module for module, var
                                      in inst_vars.items() if var.get()],
                }
                errors.extend(bwiz.data_from_values(4, values, data))
                errors.extend(bwiz.validate_step(4, data))
            return errors

        def _show(step: int) -> None:
            state["step"] = step
            title, subtitle = (bwiz.BUILDING_STEPS[step][1],
                               bwiz.BUILDING_STEPS[step][2])
            step_var.set(f"Paso {step + 1} de {len(frames)} · {title} — "
                         f"{subtitle}")
            _sync_room_level_choices()
            for index, frame in enumerate(frames):
                frame.pack_forget()
                if index == step:
                    frame.pack(fill="both", expand=True)
            back_btn.configure(
                state="normal" if step > 0 else "disabled")
            next_btn.configure(
                text="Generar edificación 🏗️" if step == len(frames) - 1
                else "Siguiente ›")
            if step == 5:  # variantes: genera al entrar (una sola vez)
                if not state["variants"]:
                    _generate_variants()
            if step == len(frames) - 1:
                _collect(3)  # asegurar los vanos vigentes en el resumen
                summary.configure(state="normal")
                summary.delete("1.0", "end")
                summary.insert("1.0", bwiz.step_summary(
                    data, self.ctx, state.get("variant")))
                summary.configure(state="disabled")

        def _go_next() -> None:
            errors = _collect(state["step"])
            if errors:
                messagebox.showwarning(
                    "Asistente de edificación",
                    "Antes de continuar, revisa esto:\n\n"
                    + "\n".join(f"· {e}" for e in errors), parent=dialog)
                return
            if state["step"] < len(frames) - 1:
                _show(state["step"] + 1)
            else:
                _create()

        def _go_back() -> None:
            if state["step"] > 0:
                _collect(state["step"])  # no perder lo tecleado
                _show(state["step"] - 1)

        def _create() -> None:
            errors: List[str] = []
            for step in range(6):
                errors.extend(bwiz.validate_step(step, data))
            if errors:
                messagebox.showwarning(
                    "Asistente de edificación",
                    "Antes de generar, revisa esto:\n\n"
                    + "\n".join(f"· {e}" for e in errors), parent=dialog)
                return
            try:
                created = bwiz.apply_plan(data, self.ctx,
                                          variant=state.get("variant"))
            except Exception as exc:  # noqa: BLE001 - mensaje amable
                messagebox.showerror(
                    "Asistente de edificación",
                    f"No pude generar la edificación:\n{exc}",
                    parent=dialog)
                return
            dialog.destroy()
            self.refresh_all(fit=True)
            warnings = created.get("warnings", [])
            inst = created.get("instalaciones") or {}
            parts = [
                f"Edificación «{data.name.strip()}» creada: "
                f"{created.get('levels_created', 0)} nivel(es) nuevo(s), "
                f"{created.get('spaces', 0)} locales, "
                f"{created.get('walls', 0)} muros, "
                f"{created.get('doors', 0)} puertas y "
                f"{created.get('windows', 0)} ventanas"]
            if inst.get("redes"):
                parts.append(
                    f"{inst['redes']} red(es) de instalaciones generadas "
                    f"({inst['equipos']} equipos y {inst['tramos']} tramos: "
                    + ", ".join(inst.get("nombres", [])[:6]) + ")")
            self._say(". ".join(parts) + ".",
                      "Haz clic sobre cualquier pieza para ver sus datos; "
                      "los requerimientos quedaron guardados en cada "
                      "objeto y las redes aparecen en la disciplina "
                      "Instalaciones")
            if warnings:
                messagebox.showinfo(
                    "Avisos del conocimiento técnico",
                    "La edificación se generó bien. Ten en cuenta:\n\n"
                    + "\n".join(f"· {w}" for w in warnings[:8]),
                    parent=self)

        back_btn = ttk.Button(footer, text="‹ Atrás", command=_go_back)
        back_btn.pack(side="left")
        ttk.Button(footer, text="Cancelar",
                   command=dialog.destroy).pack(side="right")
        next_btn = ttk.Button(footer, text="Siguiente ›",
                              style="Accent.TButton", command=_go_next)
        next_btn.pack(side="right", padx=(0, 10))

        # Ganchos para pruebas y accesibilidad.
        dialog._bld_widgets = {
            "name": name_entry, "usage": usage_combo,
            "lot_w": lot_w_entry, "lot_d": lot_d_entry,
            "construction": construction_combo,
            "shape": shape_combo, "style": style_combo,
            "terrain": terrain_combo, "stairs": stairs_combo,
            "core": core_combo,
            "climate": climate_combo,
            "system": system_combo, "orientation": orientation_combo,
            "region": region_combo,
            "notes": notes_text, "level_tree": level_tree,
            "level_name": level_name_entry,
            "level_height": level_height_entry,
            "room_tree": room_tree, "room_name": room_name_entry,
            "room_type": room_type_combo,
            "room_width": room_width_entry,
            "room_depth": room_depth_entry,
            "room_level": room_level_combo,
            "room_window": room_window_var,
            "relation_tree": relation_tree, "rel_a": rel_a_combo,
            "rel_b": rel_b_combo, "rel_kind": rel_kind_combo,
            "rel_door": rel_door_var, "corridor": corridor_var,
            "cross": cross_var, "thickness": thick_entry,
            "corridor_width": corridor_entry, "door_width": door_w_entry,
            "door_height": door_h_entry, "window_width": win_w_entry,
            "window_height": win_h_entry, "sill": sill_entry,
            "protect": protect_var, "eaves": eaves_entry,
            "inst_vars": inst_vars,
            "variant_tree": variant_tree,
            "variant_canvas": variant_canvas,
            "variant_desc": variant_desc,
            "calidad": calidad_combo,
            "view": view_combo, "view_aux": aux_combo,
            "summary": summary, "next_btn": next_btn,
            "back_btn": back_btn,
        }
        dialog._bld_state = state
        dialog._bld_data = data
        dialog._bld_step_var = step_var
        dialog._bld_next = _go_next
        dialog._bld_back = _go_back
        dialog._bld_show = _show
        dialog._bld_generate_variants = _generate_variants
        dialog._bld_choose_variant = _choose_variant
        dialog._bld_coste_on_calidad = _coste_on_calidad
        dialog._bld_export_view_svg = _export_view_svg
        dialog._bld_export_view_png = _export_view_png
        dialog._bld_export_view_pdf = _export_view_pdf
        dialog._bld_open_detalles = _open_detalles_tipologia
        dialog._bld_load_usage = _load_usage
        dialog._bld_refresh = {
            "levels": _refresh_level_tree, "rooms": _refresh_room_tree,
            "relations": _refresh_relation_tree,
            "variants": _refresh_variant_tree,
        }

        _refresh_level_tree()
        _refresh_room_tree()
        _refresh_relation_tree()
        _show(0)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    def _ask_entity_type(self) -> str:
        """Elige tipo de objeto: por defecto, los de la disciplina activa."""
        available = list(CREATE_SPECS)
        preferred = {
            "ARCHITECTURE": ["SPACE", "WALL", "DOOR", "WINDOW", "LEVEL",
                             "ZONE"],
            "STRUCTURE": ["ELEMENT", "MATERIAL", "SECTION"],
            "INSTALLATIONS": ["NETWORK", "NODE"],
        }.get(self.current_discipline, [])
        ordered = [t for t in preferred if t in available] + \
                  [t for t in available if t not in preferred]
        dialog = tk.Toplevel(self)
        dialog.title("Nuevo objeto")
        dialog.transient(self)
        dialog.grab_set()
        self._prepare_dialog(dialog, "tipo_objeto", remember=False)
        ttk.Label(dialog,
                  text="¿Qué quieres crear? Te proponemos primero los "
                       "objetos de la disciplina activa.",
                  style="Dim.TLabel", wraplength=320,
                  justify="left").pack(anchor="w", padx=10,
                                       pady=(10, 4))
        combo = ttk.Combobox(dialog, values=ordered, state="readonly",
                             width=24)
        if ordered:
            combo.set(ordered[0])
        combo.pack(anchor="w", padx=10, fill="x", expand=True)
        chosen: Dict[str, str] = {}

        def ok() -> None:
            chosen["type"] = combo.get()
            dialog.destroy()
        ttk.Button(dialog, text="Continuar", command=ok).pack(
            side="right", padx=10, pady=10)
        ttk.Button(dialog, text="Cancelar",
                   command=dialog.destroy).pack(side="right")
        dialog.wait_window()
        return chosen.get("type", "")

    # -- herramientas adicionales (FASE 90.1) -------------------------------------
    def run_recompute_all(self) -> None:
        from services.budget_service import BudgetService
        from services.quantity_service import QuantityService
        stats = QuantityService(self.ctx).compute_all()
        total = BudgetService(self.ctx).compute()
        self.refresh_all()
        self._say(
            f"Cálculos completos: {stats.get('objects_processed', 0)} "
            f"objetos · presupuesto {total:,.2f} "
            f"{self.ctx.project.currency}.",
            "Echa un vistazo a las disciplinas «Cantidades» y "
            "«Presupuesto» del explorador")

    # -- herramientas de edición CAD (v3.14.0) ---------------------------
    # Paleta con iconos + máquina de estados sobre el lienzo. El motor
    # (ui/cad_tools.py) no toca Tk: aquí solo hay interacción.

    _CAD_PUNTOS = {"mover": 2, "copiar": 2, "reflejar": 2, "girar": 3,
                   "recortar": 1, "alargar": 1, "chaflan": 0, "dividir": 1,
                   "estirar": 2, "paralela": 1}
    _CAD_OTRO = ("recortar", "alargar", "chaflan")

    # ==================================================================
    # Teclado, puntero y portapapeles estilo AutoCAD (v3.16.0)
    # ==================================================================

    ACCIONES_HERRAMIENTA: Dict[str, str] = {
        "mover": "mover", "copiar_objeto": "copiar", "reflejar": "reflejar",
        "girar": "girar", "recortar": "recortar", "alargar": "alargar",
        "chaflan": "chaflan", "dividir": "dividir", "estirar": "estirar",
        "paralela": "paralela", "borrar": "borrar",
        # DIBUJO (v3.38.0): las cinco herramientas de la paleta
        "dib_muro": "dib_muro", "dib_espacio": "dib_espacio",
        "dib_zona": "dib_zona", "dib_puerta": "dib_puerta",
        "dib_ventana": "dib_ventana",
    }

    def _tecla_modo(self, event) -> None:
        """F3/F7/F8/F9/F10: conmutan los modos de trabajo."""
        modo = keymap.TECLA_MODO.get(str(event.keysym).lower())
        if not modo:
            return
        if modo == "rejilla":
            casilla = self._grid_var()
            casilla.set(not casilla.get())
            self.teclas.estado["rejilla"] = casilla.get()
            self.redraw()
            _nuevo, mensaje = self.teclas.alternar("rejilla")
        else:
            _nuevo, mensaje = self.teclas.alternar(modo)
        self._say(mensaje)

    def _tecla_canvas(self, event) -> None:
        """Teclas de trabajo con el LIENZO enfocado: alias de comando,
        ESPACIO que repite y flechas de pan. Los combos Ctrl y las
        teclas de funcion van por sus atajos globales."""
        if event.state & 0x4:      # Ctrl: lo llevan los atajos globales
            return
        tecla = str(event.keysym)
        if tecla.lower() == "escape":
            if self._pan_temporal:
                self._ejecutar_accion_cad("cancelar")
            return                 # el ESC del lienzo ya cancela la CAD
        accion = self.teclas.procesar(tecla)
        if accion:
            self._ejecutar_accion_cad(accion)

    def _ejecutar_accion_cad(self, accion: str) -> None:
        """Dispatch de las acciones del teclado de trabajo."""
        herramienta = self.ACCIONES_HERRAMIENTA.get(accion)
        if herramienta:
            self._cad_set_tool(herramienta)
            return
        if accion == "cancelar":
            if self._pan_temporal:
                self._pan_temporal = False
                self._say("PAN terminado: los clics vuelven a "
                          "seleccionar.", "")
            self._cad_cancelar()
        elif accion == "repetir":
            if self.teclas.ultima_accion:
                self._ejecutar_accion_cad(self.teclas.ultima_accion)
        elif accion == "deshacer":
            self.undo()
        elif accion == "rehacer":
            self.redo()
        elif accion == "encuadrar":
            self.fit_view()
        elif accion == "zoom+":
            self.zoom(1.25)
        elif accion == "zoom-":
            self.zoom(0.8)
        elif accion == "pan":
            self._pan_temporal = True
            self._say("PAN: arrastra con el boton izquierdo; ESC sale.",
                      "El boton derecho y la rueda siguen igual")
        elif accion in ("pan_arriba", "pan_abajo", "pan_izquierda",
                        "pan_derecha"):
            dx, dy = {"pan_arriba": (0, 60), "pan_abajo": (0, -60),
                      "pan_izquierda": (60, 0),
                      "pan_derecha": (-60, 0)}[accion]
            self.viewport.pan_by(dx, dy)
            self.redraw()
        elif accion == "copiar_seleccion":
            self._portapapeles_copiar()
        elif accion == "cortar":
            self._portapapeles_cortar()
        elif accion == "pegar":
            self._portapapeles_pegar()
        elif accion == "guardar":
            self.save_project()
        elif accion == "abrir":
            self.open_project_dialog()
        elif accion == "nuevo":
            self.new_project()
        elif accion == "imprimir":
            self._say("Ctrl+P: la vista sale en PDF/PNG con "
                      "Archivo > Exportar vista.", "")
        elif accion == "zoom_ventana":
            self._zoom_ventana()
        elif accion == "zoom_anterior":
            self._zoom_anterior()
        elif accion == "historial_comandos":
            self._ventana_historial()
        elif accion == "calculadora":
            self._say("Calculadora: escribe =expresión en la línea de "
                      "comandos (por ejemplo =2*3.5+0.2); los campos "
                      "de coordenadas también aceptan operaciones",
                      "Soporta + - * / ** ( ) y pi")
        elif accion.startswith("alternar_"):
            modo = accion[len("alternar_"):]
            _nuevo, mensaje = self.teclas.alternar(modo)
            self._say(mensaje, "")
            if modo == "rejilla":
                self.redraw()

    # -- puntero (mira) y referencias ------------------------------------

    def _muros_mira(self) -> List[Any]:
        """Muros del proyecto para las referencias (osnap)."""
        try:
            return list(self.ctx.architecture.list("WALL",
                                                   self.ctx.project.id))
        except Exception:  # noqa: BLE001 - proyecto sin abrir aun
            return []

    def _locales_mira(self) -> List[Any]:
        """Locales del nivel visible para el CENTRO de la referencia
        (v3.38.0): el osnap de centroide del contorno."""
        try:
            return list(self.ctx.architecture.list("SPACE",
                                                   self.ctx.project.id))
        except Exception:  # noqa: BLE001 - proyecto sin abrir aun
            return []

    def _paso_rejilla_actual(self) -> float:
        """Paso de la rejilla ANIDADA visible (v3.38.0): niveles x5
        con celda mínima en pantalla; coincide con la rejilla dibujada
        para que la imantación caiga donde se ve."""
        if self._rejilla_datos is None:
            self._calcula_rejilla()
        return float((self._rejilla_datos or {}).get("paso", 1.0))

    def _calcula_rejilla(self) -> None:
        """La rejilla del nivel actual, con antiflip respecto al nivel
        previo (una muesca de rueda no oscila entre niveles)."""
        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 600)
        self._rejilla_datos = nav.rejilla_adaptativa(
            self.viewport.center_x, self.viewport.center_y,
            self.viewport.scale, width, height,
            paso_base=1.0, mayor_cada=5,
            nivel_previo=self._nivel_rejilla)
        self._nivel_rejilla = int(self._rejilla_datos["nivel"])

    def _punto_ayudado(self, origen, destino):
        """Referencias + orto + imantación sobre un punto de orden.
        Mayús mantenida INVIERTE el orto (orto temporal si está
        apagado, liberar si está encendido), como el Shift del clásico."""
        orto_efectivo = bool(self.teclas.estado["orto"]) != \
            bool(self._orto_shift)
        return cursor_acad.aplicar_ayudas(
            origen, tuple(destino),
            self.teclas.estado["osnap"], orto_efectivo,
            self.teclas.estado["imantacion"], self._muros_mira(),
            self._acad, self.viewport.scale,
            paso=self._paso_rejilla_actual(),
            locales=self._locales_mira())

    def _mira_redibuja(self, event=None) -> None:
        """Mira (cruz configurable) y marcador de referencia."""
        self.canvas.delete("acad_mira")
        self._acad_marcador = None
        if not self._acad.mira or event is None:
            return
        try:
            w = max(self.canvas.winfo_width(), 800)
            h = max(self.canvas.winfo_height(), 600)
        except Exception:  # noqa: BLE001 - lienzo aun sin realizar
            return
        color = cursor_acad.color_mira(self._acad.mira_color,
                                       PALETTE["axis"])
        (p1, p2, p3, p4) = cursor_acad.puntas_cruz(
            event.x, event.y, w, h, self._acad.mira_pct)
        grosor = max(1, int(self._acad.mira_grosor))
        self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=color,
                                width=grosor, tags=("acad_mira",))
        self.canvas.create_line(p3[0], p3[1], p4[0], p4[1], fill=color,
                                width=grosor, tags=("acad_mira",))
        if not self.teclas.estado["osnap"]:
            return
        wx, wy = self.viewport.from_screen(event.x, event.y, w, h)
        umbral = self._acad.umbral_osnap_px / max(self.viewport.scale,
                                                  1e-9)
        origen = self._cad_pasos[-1] if self._cad_pasos else None
        fij = cursor_acad.mejor_fijacion(self._muros_mira(), (wx, wy),
                                         umbral,
                                         locales=self._locales_mira(),
                                         origen=origen)
        if not fij:
            return
        (fx, fy), marca = fij
        sx, sy = self.viewport.to_screen(fx, fy, w, h)
        color = cursor_acad.COLOR_MARCA_DEF
        # Marcadores clasicos: cuadrado (extremo), X (interseccion),
        # triangulo (medio), circulo (centro), angulo recto
        # (perpendicular), pajarita (mas_cercano).
        if marca == "extremo":
            self.canvas.create_rectangle(sx - 5, sy - 5, sx + 5, sy + 5,
                                         outline=color, width=2,
                                         tags=("acad_mira",))
        elif marca == "interseccion":
            self.canvas.create_line(sx - 5, sy - 5, sx + 5, sy + 5,
                                    fill=color, width=2,
                                    tags=("acad_mira",))
            self.canvas.create_line(sx - 5, sy + 5, sx + 5, sy - 5,
                                    fill=color, width=2,
                                    tags=("acad_mira",))
        elif marca == "centro":
            self.canvas.create_oval(sx - 6, sy - 6, sx + 6, sy + 6,
                                    outline=color, width=2,
                                    tags=("acad_mira",))
        elif marca == "perpendicular":
            self.canvas.create_line(sx - 6, sy + 5, sx + 5, sy + 5,
                                    fill=color, width=2,
                                    tags=("acad_mira",))
            self.canvas.create_line(sx - 6, sy + 5, sx - 6, sy - 6,
                                    fill=color, width=2,
                                    tags=("acad_mira",))
        elif marca == "mas_cercano":
            self.canvas.create_line(sx - 6, sy - 6, sx + 6, sy + 6,
                                    fill=color, width=2,
                                    tags=("acad_mira",))
            self.canvas.create_line(sx - 6, sy + 6, sx + 6, sy - 6,
                                    fill=color, width=2,
                                    tags=("acad_mira",))
            self.canvas.create_line(sx + 6, sy - 6, sx - 6, sy + 6,
                                    fill=color, width=2,
                                    tags=("acad_mira",))
        else:
            self.canvas.create_polygon(sx, sy - 6, sx - 6, sy + 5,
                                       sx + 6, sy + 5, outline=color,
                                       fill="", width=2,
                                       tags=("acad_mira",))
        self._acad_marcador = (fx, fy, marca)

    # -- portapapeles ----------------------------------------------------

    def _portapapeles_copiar(self) -> None:
        fila = self.selection
        if fila is None or fila.type not in ("SPACE", "WALL"):
            self._say("Ctrl+C: selecciona un local o muro para copiarlo.",
                      "Ctrl+V lo pega desplazado 1 m")
            return
        self._portapapeles = (fila.type, fila.uid)
        self._say(f"{fila.type} {fila.code} en el portapapeles.",
                  "Ctrl+V lo pega desplazado; Ctrl+X lo corta")

    def _portapapeles_copiar_evento(self, _event) -> str:
        self._portapapeles_copiar()
        return "break"

    def _portapapeles_cortar(self) -> None:
        self._portapapeles_copiar()
        if self._portapapeles:
            self.delete_selection()

    def _portapapeles_cortar_evento(self, _event) -> str:
        self._portapapeles_cortar()
        return "break"

    def _portapapeles_pegar(self) -> None:
        if not self._portapapeles:
            self._say("Ctrl+V: el portapapeles esta vacio.",
                      "Ctrl+C sobre un local o muro primero")
            return
        tipo, ref = self._portapapeles
        try:
            resumen = cad.copiar(self.ctx, tipo, ref, 1.0, -1.0)
            cad.finalizar(self.ctx, resumen)
            self.ctx.commit()
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            self.ctx.rollback()
            accion = getattr(exc, "suggested_action", "")
            messagebox.showerror(
                "Pegar", str(getattr(exc, "message", exc))
                + (f"\n\nSugerencia: {accion}" if accion else ""),
                parent=self)
            return
        self.refresh_all()
        self._say(cad.texto_resumen(resumen),
                  "La copia entra desplazada 1 m y con undo")

    def _portapapeles_pegar_evento(self, _event) -> str:
        self._portapapeles_pegar()
        return "break"

    # ==================================================================
    # FIN TECLADO AUTOCAD
    # ==================================================================

    # -- dialogo: puntero y rejilla (v3.16.0) ----------------------------

    def open_puntero_dialog(self) -> None:
        """Ajustes del puntero (mira) y de la imantacion a rejilla."""
        dialog = tk.Toplevel(self)
        self._puntero_dialogo = dialog
        dialog.title("Puntero y rejilla (estilo AutoCAD)")
        self._prepare_dialog(dialog, "puntero_rejilla")
        dialog.transient(self)
        marco = ttk.Frame(dialog, padding=12)
        marco.pack(fill="both", expand=True)

        variables: Dict[str, Any] = {
            "mira": tk.BooleanVar(value=self._acad.mira),
            "mira_pct": tk.StringVar(value=f"{self._acad.mira_pct:.0f}"),
            "mira_grosor": tk.StringVar(
                value=f"{self._acad.mira_grosor}"),
            "mira_color": tk.StringVar(value=self._acad.mira_color),
            "paso_rejilla": tk.StringVar(
                value=f"{self._acad.paso_rejilla:g}"),
            "umbral": tk.StringVar(
                value=f"{self._acad.umbral_osnap_px:.0f}")}

        ttk.Checkbutton(marco, text="Mira (cruz) visible sobre el plano",
                        variable=variables["mira"]).pack(
            anchor="w", pady=(0, 6))
        fila = ttk.Frame(marco); fila.pack(fill="x", pady=2)
        ttk.Label(fila, text="Tamano de la mira (% del lienzo, 100 = "
                             "de punta a punta):").pack(anchor="w")
        ttk.Entry(fila, textvariable=variables["mira_pct"],
                  width=10).pack(anchor="w")
        fila = ttk.Frame(marco); fila.pack(fill="x", pady=2)
        ttk.Label(fila, text="Grosor del trazo (1-5 px):").pack(anchor="w")
        ttk.Entry(fila, textvariable=variables["mira_grosor"],
                  width=10).pack(anchor="w")
        fila = ttk.Frame(marco); fila.pack(fill="x", pady=2)
        ttk.Label(fila, text="Paso de imantacion a rejilla (m; F9 usa "
                             "el paso adaptativo dibujado):").pack(
            anchor="w")
        ttk.Entry(fila, textvariable=variables["paso_rejilla"],
                  width=10).pack(anchor="w")
        fila = ttk.Frame(marco); fila.pack(fill="x", pady=2)
        ttk.Label(fila, text="Umbral de referencia F3 (px):").pack(
            anchor="w")
        ttk.Entry(fila, textvariable=variables["umbral"],
                  width=10).pack(anchor="w")
        fila = ttk.Frame(marco); fila.pack(fill="x", pady=2)
        ttk.Label(fila, text="Color de la mira (vacio = el del tema):").pack(
            anchor="w")
        fila_color = ttk.Frame(marco); fila_color.pack(fill="x")
        ttk.Entry(fila_color, textvariable=variables["mira_color"],
                  width=14).pack(side="left")

        def _elegir_color() -> None:
            from tkinter import colorchooser
            eleccion = colorchooser.askcolor(
                variables["mira_color"].get() or "#ffffff",
                parent=dialog, title="Color de la mira")
            if eleccion and eleccion[1]:
                variables["mira_color"].set(eleccion[1])

        ttk.Button(fila_color, text="Elegir…", command=_elegir_color).pack(
            side="left", padx=6)

        def _aplicar() -> None:
            try:
                self._acad = cursor_acad.ConfigCursor(
                    mira=bool(variables["mira"].get()),
                    mira_pct=float(str(variables["mira_pct"].get())
                                   .replace(",", ".") or 100),
                    mira_grosor=int(str(variables["mira_grosor"].get())
                                    or 1),
                    mira_color=str(variables["mira_color"].get()).strip(),
                    paso_rejilla=float(str(variables["paso_rejilla"].get())
                                       .replace(",", ".") or 0.5),
                    umbral_osnap_px=float(
                        str(variables["umbral"].get())
                        .replace(",", ".") or 10)).normalizada()
            except (TypeError, ValueError):
                messagebox.showerror(
                    "Puntero y rejilla",
                    "Los valores deben ser numéricos.", parent=dialog)
                return
            self.prefs["cursor"] = cursor_acad.dict_de_config(self._acad)
            self._save_prefs_now()
            self.redraw()
            self._say("Puntero y rejilla aplicados.",
                      "Se recuerdan entre sesiones")
            dialog._puntero_aplicado = True

        botones = ttk.Frame(marco); botones.pack(fill="x", pady=(10, 0))
        self._tip(ttk.Button(botones, text="Aplicar", command=_aplicar),
                  "puntero_aplicar").pack(side="left", padx=(0, 6))
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="left")
        dialog._puntero_vars = variables
        dialog._puntero_aplicar = _aplicar
        dialog._puntero_color = _elegir_color
        self._say("Ajustes del puntero: tamano, grosor, color e "
                  "imantacion.", "Se aplican al punto y se recuerdan")

    # -- asistente de local: MODIFICAR (v3.20.0) --------------------------

    def _validar_cotas_local(self, dialog: Any, _locales_actual: Any,
                             diag: Any) -> None:
        """Control de validación dimensional del local (§19, v3.22.0)."""
        eid = _locales_actual()
        if not eid:
            messagebox.showinfo(
                "Validación del local",
                "Elige antes un local en el asistente.",
                parent=dialog)
            return
        try:
            informe = editor_espacios.validacion_local(self.ctx, eid)
        except Exception as exc:  # noqa: BLE001 - amable
            messagebox.showerror(
                "Validación del local",
                str(getattr(exc, "message", exc)),
                parent=dialog)
            return
        diag.delete("1.0", "end")
        diag.insert("1.0", editor_espacios.texto_validacion(informe))
        fallos = sum(1 for h in informe.get("hallazgos", [])
                     if h.get("severidad") == "fallo")
        avisos = sum(1 for h in informe.get("hallazgos", [])
                     if h.get("severidad") == "aviso")
        self._say(
            "Validación dimensional del local contra las cotas del "
            "uso (documento hospitalario, sección 19).",
            f"{fallos} fallo(s) y {avisos} aviso(s); la ficha PDF lo "
            "lleva impreso")

    def _ficha_local_pdf(self, dialog: Any, _locales_actual: Any) -> None:
        """Ficha imprimible del local elegido (PDF, v3.21.0)."""
        eid = _locales_actual()
        if not eid:
            messagebox.showinfo(
                "Ficha de local",
                "Elige antes un local en el asistente.",
                parent=dialog)
            return
        ruta = filedialog.asksaveasfilename(
            parent=dialog, title="Exportar ficha del local (PDF)",
            defaultextension=".pdf",
            initialfile=f"ficha_{eid}.pdf",
            filetypes=[("PDF", "*.pdf")])
        if not ruta:
            return
        try:
            from exporters.ficha_local import export_ficha_local_pdf
            export_ficha_local_pdf(self.ctx, eid, ruta)
        except Exception as exc:  # noqa: BLE001 - amable
            self.ctx.rollback()
            messagebox.showerror(
                "Ficha de local", str(getattr(exc, "message", exc)),
                parent=dialog)
            return
        self._say(f"Ficha del local exportada a PDF: {ruta}",
                  "Identidad, DNA, vanos, mobiliario, instalaciones, "
                  "planta y diagnóstico")

    def open_editor_local_dialog(self) -> None:
        """ASISTENTE DE LOCAL en modo MODIFICAR (v3.20.0): controla
        todo lo que es imputable a un local existente — identidad y
        uso (con su DNA), geometría (dimensiones, posición, espesor,
        cota del piso), vanos (crear, retocar o dar de baja),
        instalaciones (eléctrica, sanitaria, iluminación y alarma) y
        mobiliario — con diagnóstico DNA permanente."""
        dialog = tk.Toplevel(self)
        self._editor_dialogo = dialog
        dialog.title("Asistente de local (modificar)")
        self._prepare_dialog(dialog, "editor_local")
        dialog.transient(self)
        marco = ttk.Frame(dialog, padding=10)
        marco.pack(fill="both", expand=True)

        locales = [e for e in self.ctx.architecture.list(
            "SPACE", self.ctx.project.id)
            if len(getattr(e, "boundary", []) or []) >= 3]
        if not locales:
            messagebox.showinfo(
                "Asistente de local",
                "No hay locales con geometría: genera antes la "
                "edificación con el asistente de edificación.",
                parent=self)
            dialog.destroy()
            return
        etiquetas = {e.id: f"{e.code} · {e.name or e.space_type}"
                     for e in locales}
        fila_local = ttk.Frame(marco)
        fila_local.pack(fill="x")
        ttk.Label(fila_local, text="Local:").pack(side="left")
        combo = ttk.Combobox(fila_local, state="readonly",
                             values=list(etiquetas.values()), width=34)
        combo.current(0)
        combo.pack(side="left", padx=(6, 0))
        self._tip(combo, "editor_local_combo")

        cuerpo = ttk.Frame(marco)
        cuerpo.pack(fill="both", expand=True, pady=(8, 0))
        izquierda = ttk.Frame(cuerpo)
        izquierda.pack(side="left", fill="both", expand=True)
        derecha = ttk.Frame(cuerpo)
        derecha.pack(side="left", fill="both", expand=True, padx=(10, 0))

        pestañas = ttk.Notebook(izquierda)
        pestañas.pack(fill="both", expand=True)

        def _pestaña(titulo: str) -> ttk.Frame:
            pest = ttk.Frame(pestañas, padding=8)
            pestañas.add(pest, text=titulo)
            return pest

        vars_: Dict[str, Any] = {
            "nombre": tk.StringVar(), "uso": tk.StringVar(),
            "ancho": tk.StringVar(), "fondo": tk.StringVar(),
            "amueblar": tk.BooleanVar(value=True),
            "muro_acceso": tk.StringVar(),
            "muro_ventana": tk.StringVar(),
            "ancho_acceso": tk.StringVar(),
            "ancho_ventana": tk.StringVar(),
            "dx": tk.StringVar(), "dy": tk.StringVar(),
            "espesor": tk.StringVar(), "cota": tk.StringVar(),
            "vano": tk.StringVar(), "vano_ancho": tk.StringVar(),
            "vano_alto": tk.StringVar(), "vano_antepecho":
                tk.StringVar(), "vano_offset": tk.StringVar(),
            "lampara": tk.StringVar(value="led_panel"),
            "lux": tk.StringVar(), "sirena": tk.BooleanVar(value=False),
            "densidad": tk.StringVar(value="estandar")}

        dna_types = ["ROOM"]
        try:
            dna_types += [t for t in self.ctx.dna_registry.types()
                          if t != "ROOM"]
        except Exception:  # noqa: BLE001 — sin DNA, solo ROOM
            pass
        lamparas = ("led_bombilla", "led_panel", "led_downlight",
                    "led_lineal", "led_tira", "led_campana",
                    "led_proyector", "fluor_t8", "fluor_compacta",
                    "halogena", "incandescente", "sodio_ap")

        # -- pestaña LOCAL (identidad) -----------------------------------
        pest = _pestaña("Local")
        for campo, titulo in (("nombre", "Nombre del local:"),
                              ("uso", "Uso (tipo de local):")):
            fila = ttk.Frame(pest)
            fila.pack(fill="x", pady=2)
            ttk.Label(fila, text=titulo).pack(anchor="w")
            if campo == "uso":
                combo_uso = ttk.Combobox(fila, textvariable=vars_[campo],
                                         values=dna_types,
                                         state="readonly", width=22)
                combo_uso.pack(anchor="w")
                self._tip(combo_uso, "space_type")
            else:
                ttk.Entry(fila, textvariable=vars_[campo],
                          width=24).pack(anchor="w")
        ttk.Checkbutton(pest, text="Reamueblar al cambiar el uso "
                        "(mobiliario del tipo nuevo)",
                        variable=vars_["amueblar"]).pack(
            anchor="w", pady=(6, 2))
        fila_b = ttk.Frame(pest)
        fila_b.pack(fill="x", pady=(6, 0))
        self._tip(ttk.Button(fila_b, text="Aplicar identidad",
                             command=lambda: _aplicar("identidad")),
                  "editor_identidad").pack(side="left")

        # -- pestaña GEOMETRÍA --------------------------------------------
        pest = _pestaña("Geometría")
        fila = ttk.Frame(pest)
        fila.pack(fill="x", pady=2)
        for campo, titulo, ancho in (("ancho", "Ancho nuevo (m):", 8),
                                     ("fondo", "Fondo nuevo (m):", 8)):
            celda = ttk.Frame(fila)
            celda.pack(side="left", padx=(0, 10))
            ttk.Label(celda, text=titulo).pack(anchor="w")
            ttk.Entry(celda, textvariable=vars_[campo],
                      width=ancho).pack(anchor="w")
        ttk.Checkbutton(pest, text="Reamueblar al redimensionar "
                        "(mobiliario sobre la geometría nueva)",
                        variable=vars_["amueblar"]).pack(
            anchor="w", pady=(4, 2))
        self._tip(ttk.Button(pest, text="Redimensionar",
                             command=lambda: _aplicar("redimensionar")),
                  "editor_redimensionar").pack(anchor="w", pady=(2, 6))
        fila = ttk.Frame(pest)
        fila.pack(fill="x", pady=2)
        for campo, titulo in (("dx", "Desplazar en X (m):"),
                              ("dy", "Desplazar en Y (m):")):
            celda = ttk.Frame(fila)
            celda.pack(side="left", padx=(0, 10))
            ttk.Label(celda, text=titulo).pack(anchor="w")
            ttk.Entry(celda, textvariable=vars_[campo], width=8
                      ).pack(anchor="w")
        self._tip(ttk.Button(pest, text="Mover el local (con sus muros)",
                             command=lambda: _aplicar("mover")),
                  "editor_mover").pack(anchor="w", pady=(2, 6))
        fila = ttk.Frame(pest)
        fila.pack(fill="x", pady=2)
        celda = ttk.Frame(fila)
        celda.pack(side="left", padx=(0, 10))
        ttk.Label(celda, text="Espesor de sus muros (m):").pack(anchor="w")
        ttk.Entry(celda, textvariable=vars_["espesor"],
                  width=8).pack(anchor="w")
        self._tip(ttk.Button(pest, text="Cambiar espesor",
                             command=lambda: _aplicar("espesor")),
                  "editor_espesor").pack(anchor="w", pady=(2, 6))
        celda = ttk.Frame(pest)
        celda.pack(fill="x", pady=2)
        ttk.Label(celda, text="Cota del piso (m):").pack(anchor="w")
        ttk.Entry(celda, textvariable=vars_["cota"], width=8).pack(
            anchor="w")
        self._tip(ttk.Button(pest, text="Fijar cota del piso",
                             command=lambda: _aplicar("cota")),
                  "editor_cota").pack(anchor="w", pady=(2, 0))

        # -- pestaña VANOS --------------------------------------------------
        pest = _pestaña("Vanos")
        for campo, titulo in (("muro_acceso", "Muro del acceso:"),
                              ("ancho_acceso", "Ancho (vacío = el del "
                                               "uso):"),
                              ("muro_ventana", "Muro de la ventana:"),
                              ("ancho_ventana", "Ancho (vacío = el que "
                                                "pide la ventilación):")):
            fila = ttk.Frame(pest)
            fila.pack(fill="x", pady=(4, 0))
            ttk.Label(fila, text=titulo).pack(anchor="w")
            if campo.startswith("muro"):
                widget = ttk.Combobox(fila, textvariable=vars_[campo],
                                      state="readonly", width=24)
                setattr(dialog, "_editor_muro_acceso" if campo ==
                        "muro_acceso" else "_editor_muro_ventana", widget)
                widget.pack(anchor="w")
            else:
                widget = ttk.Entry(fila, textvariable=vars_[campo],
                                   width=10)
                widget.pack(anchor="w")
        fila_b = ttk.Frame(pest)
        fila_b.pack(fill="x", pady=(6, 0))
        self._tip(ttk.Button(fila_b, text="Crear acceso",
                             command=lambda: _aplicar("acceso")),
                  "editor_acceso").pack(side="left", padx=(0, 4))
        self._tip(ttk.Button(fila_b, text="Crear ventana",
                             command=lambda: _aplicar("ventana")),
                  "editor_ventana").pack(side="left")
        fila = ttk.Frame(pest)
        fila.pack(fill="x", pady=(10, 0))
        ttk.Label(fila, text="Vano a retocar:").pack(anchor="w")
        combo_vano = ttk.Combobox(fila, textvariable=vars_["vano"],
                                  state="readonly", width=24)
        dialog._editor_combo_vano = combo_vano
        combo_vano.pack(anchor="w", pady=(0, 2))
        fila = ttk.Frame(pest)
        fila.pack(fill="x")
        for campo, titulo in (("vano_ancho", "Ancho (m):"),
                              ("vano_alto", "Alto (m):"),
                              ("vano_antepecho", "Antepecho (m):"),
                              ("vano_offset", "Posición (m):")):
            celda = ttk.Frame(fila)
            celda.pack(side="left", padx=(0, 8))
            ttk.Label(celda, text=titulo).pack(anchor="w")
            ttk.Entry(celda, textvariable=vars_[campo], width=7).pack(
                anchor="w")
        fila_b = ttk.Frame(pest)
        fila_b.pack(fill="x", pady=(6, 0))
        self._tip(ttk.Button(fila_b, text="Aplicar al vano",
                             command=lambda: _aplicar("editar_vano")),
                  "editor_editar_vano").pack(side="left", padx=(0, 4))
        self._tip(ttk.Button(fila_b, text="Quitar vano",
                             command=lambda: _aplicar("quitar_vano")),
                  "editor_quitar_vano").pack(side="left")

        # -- pestaña INSTALACIONES ----------------------------------------
        pest = _pestaña("Instalaciones")
        ttk.Label(pest, text="Redes del local:").pack(anchor="w")
        self._tip(ttk.Button(pest, text="Conectar a eléctrica y sanitaria",
                             command=lambda: _aplicar("instalaciones")),
                  "editor_instalaciones").pack(anchor="w", pady=(2, 8))
        fila = ttk.Frame(pest)
        fila.pack(fill="x")
        celda = ttk.Frame(fila)
        celda.pack(side="left", padx=(0, 10))
        ttk.Label(celda, text="Lámpara:").pack(anchor="w")
        combo_lamp = ttk.Combobox(celda, textvariable=vars_["lampara"],
                                  values=lamparas, state="readonly",
                                  width=16)
        combo_lamp.pack(anchor="w")
        self._tip(combo_lamp, "editor_lampara")
        celda = ttk.Frame(fila)
        celda.pack(side="left")
        ttk.Label(celda, text="Lux (vacío = los del uso):").pack(anchor="w")
        ttk.Entry(celda, textvariable=vars_["lux"], width=8).pack(
            anchor="w")
        self._tip(ttk.Button(pest, text="Dimensionar iluminación (lúmenes)",
                             command=lambda: _aplicar("iluminar")),
                  "editor_iluminar").pack(anchor="w", pady=(6, 8))
        ttk.Checkbutton(pest, text="Sirena también al exterior",
                        variable=vars_["sirena"]).pack(anchor="w")
        self._tip(ttk.Button(pest, text="Proteger con alarma",
                             command=lambda: _aplicar("alarmar")),
                  "editor_alarmar").pack(anchor="w", pady=(2, 0))

        # -- pestaña MOBILIARIO -------------------------------------------
        pest = _pestaña("Mobiliario")
        ttk.Label(pest, text="Densidad del amueblado:").pack(anchor="w")
        combo_dens = ttk.Combobox(pest, textvariable=vars_["densidad"],
                                  values=("compacto", "estandar",
                                          "amplio"), state="readonly",
                                  width=12)
        combo_dens.pack(anchor="w", pady=(0, 4))
        self._tip(ttk.Button(pest, text="Reamueblar el local",
                             command=lambda: _aplicar("mobiliario")),
                  "editor_mobiliario").pack(anchor="w", pady=(2, 0))

        # -- diagnóstico a la derecha ---------------------------------------
        diag = tk.Text(derecha, width=46, height=22, wrap="word")
        diag.pack(fill="both", expand=True)
        boton_validar = ttk.Button(
            derecha, text="Validar cotas",
            command=lambda: self._validar_cotas_local(
                dialog, _locales_actual, diag))
        boton_validar.pack(fill="x", pady=(6, 0))
        self._tip(boton_validar, "editor_local_validar")
        boton_ficha = ttk.Button(
            derecha, text="Ficha PDF...",
            command=lambda: self._ficha_local_pdf(dialog, _locales_actual))
        boton_ficha.pack(fill="x", pady=(6, 0))
        self._tip(boton_ficha, "editor_local_ficha")
        resultado: Dict[str, Any] = {"resumen": None}

        def _locales_actual() -> Any:
            elegido = combo.get()
            for eid, etiqueta in etiquetas.items():
                if etiqueta == elegido:
                    return eid
            return None

        def _cargar() -> None:
            eid = _locales_actual()
            if not eid:
                return
            datos = editor_espacios.resumen_completo(self.ctx, eid)
            vars_["nombre"].set(datos["nombre"] or "")
            vars_["uso"].set(datos["uso"] or "ROOM")
            vars_["ancho"].set(f"{datos['ancho_m']:g}")
            vars_["fondo"].set(f"{datos['fondo_m']:g}")
            vars_["cota"].set(f"{datos.get('cota_piso_m', 0.0):g}")
            muros = datos["muros_exclusivos"] + datos["muros_compartidos"]
            combo_a = dialog._editor_muro_acceso
            combo_v = dialog._editor_muro_ventana
            combo_a["values"] = muros or [""]
            combo_v["values"] = muros or [""]
            if muros:
                combo_a.current(0)
                combo_v.current(0)
            vanos = datos["puertas"] + datos["ventanas"]
            combo_vano["values"] = vanos or [""]
            if vanos:
                if vars_["vano"].get() not in vanos:
                    combo_vano.current(0)
                elegido = self.ctx.architecture.get_by_code(
                    _kind_de(datos, vars_["vano"].get()) or "DOOR",
                    vars_["vano"].get())
                if elegido is not None:
                    vars_["vano_ancho"].set(f"{float(elegido.width_m):g}")
                    vars_["vano_alto"].set(f"{float(elegido.height_m):g}")
                    vars_["vano_antepecho"].set(
                        f"{float(getattr(elegido, 'sill_height_m', 0.0)
                                 or 0.0):g}")
                    vars_["vano_offset"].set(
                        f"{float(elegido.offset_m):g}")
            else:
                vars_["vano"].set("")
            diag.delete("1.0", "end")
            diag.insert("1.0",
                        editor_espacios.texto_resumen_completo(datos))

        def _kind_de(datos: Dict[str, Any], codigo: str) -> str:
            if codigo in datos["puertas"]:
                return "DOOR"
            if codigo in datos["ventanas"]:
                return "WINDOW"
            return "OPENING"

        def _aplicar(que: str) -> None:
            eid = _locales_actual()
            if not eid:
                return
            try:
                if que == "identidad":
                    resumen = editor_espacios.cambiar_identidad(
                        self.ctx, eid, nombre=vars_["nombre"].get(),
                        uso=vars_["uso"].get(),
                        con_mobiliario=bool(vars_["amueblar"].get()))
                elif que == "redimensionar":
                    ancho = float(str(vars_["ancho"].get())
                                  .replace(",", "."))
                    fondo = float(str(vars_["fondo"].get())
                                  .replace(",", "."))
                    resumen = editor_espacios.redimensionar_local(
                        self.ctx, eid, ancho, fondo,
                        con_mobiliario=bool(vars_["amueblar"].get()))
                elif que == "mover":
                    dx = float(str(vars_["dx"].get()).replace(",", ".")
                               or 0)
                    dy = float(str(vars_["dy"].get()).replace(",", ".")
                               or 0)
                    resumen = editor_espacios.mover_local(
                        self.ctx, eid, dx, dy)
                elif que == "espesor":
                    resumen = editor_espacios.espesor_muros_exclusivos(
                        self.ctx, eid,
                        float(str(vars_["espesor"].get())
                              .replace(",", ".")))
                elif que == "cota":
                    resumen = editor_espacios.cota_piso_local(
                        self.ctx, eid,
                        float(str(vars_["cota"].get()).replace(",", ".")))
                elif que == "acceso":
                    muro = vars_["muro_acceso"].get() or None
                    ancho_txt = str(vars_["ancho_acceso"].get()
                                    ).replace(",", ".").strip()
                    resumen = editor_espacios.crear_acceso(
                        self.ctx, eid, muro_ref=muro or None,
                        ancho=float(ancho_txt) if ancho_txt else None)
                elif que == "ventana":
                    muro = vars_["muro_ventana"].get() or None
                    ancho_txt = str(vars_["ancho_ventana"].get()
                                    ).replace(",", ".").strip()
                    resumen = editor_espacios.crear_ventana(
                        self.ctx, eid, muro_ref=muro or None,
                        ancho=float(ancho_txt) if ancho_txt else None)
                elif que == "editar_vano":
                    def _num(campo: str) -> Optional[float]:
                        txt = str(vars_[campo].get()).replace(
                            ",", ".").strip()
                        return float(txt) if txt else None
                    resumen = editor_espacios.editar_vano(
                        self.ctx, eid, vars_["vano"].get(),
                        ancho=_num("vano_ancho"),
                        alto=_num("vano_alto"),
                        antepecho=_num("vano_antepecho"),
                        offset=_num("vano_offset"))
                elif que == "quitar_vano":
                    resumen = editor_espacios.quitar_vano(
                        self.ctx, eid, vars_["vano"].get())
                elif que == "instalaciones":
                    resumen = \
                        editor_espacios.conectar_instalaciones_local(
                            self.ctx, eid)
                elif que == "iluminar":
                    lux_txt = str(vars_["lux"].get()).replace(
                        ",", ".").strip()
                    resumen = editor_espacios.iluminar_local(
                        self.ctx, eid,
                        lampara=vars_["lampara"].get() or "led_panel",
                        lux=int(float(lux_txt)) if lux_txt else None)
                elif que == "alarmar":
                    resumen = editor_espacios.alarmar_local(
                        self.ctx, eid,
                        sirena_exterior=bool(vars_["sirena"].get()))
                else:  # mobiliario
                    resumen = editor_espacios.regenerar_mobiliario_local(
                        self.ctx, eid,
                        densidad=vars_["densidad"].get() or "estandar")
            except Exception as exc:  # noqa: BLE001 - amable y rollback
                self.ctx.rollback()
                accion = getattr(exc, "suggested_action", "")
                messagebox.showerror(
                    "Asistente de local", str(getattr(exc, "message", exc))
                    + (f"\n\nSugerencia: {accion}" if accion else ""),
                    parent=dialog)
                return
            self.ctx.commit()
            self.refresh_all()
            resultado["resumen"] = resumen
            self._say(editor_espacios.resumen_texto(resumen),
                      "Ctrl+Z deshace; el diagnóstico se actualiza")
            _cargar()

        combo.bind("<<ComboboxSelected>>", lambda _e: _cargar())
        dialog._editor_locales = combo
        dialog._editor_vars = vars_
        dialog._editor_diag = diag
        dialog._editor_resultado = resultado
        dialog._editor_cargar = _cargar
        dialog._editor_aplicar = _aplicar
        dialog._editor_pestañas = pestañas
        _cargar()
        self._say("Asistente de local (modificar): identidad, "
                  "geometría, vanos, instalaciones y mobiliario del "
                  "local.", "Todo queda auditado y con Ctrl+Z")

    def open_dibujo_palette(self) -> None:
        """La misma paleta, enfocada al DIBUJO (v3.33.0)."""
        self.open_cad_palette()

    def open_cad_palette(self) -> None:
        """Paleta flotante: sección de DIBUJO (v3.33.0) + herramientas
        de edición con iconos."""
        if self._cad_palette is not None and self._cad_palette.winfo_exists():
            self._cad_palette.deiconify()
            self._cad_palette.lift()
            return
        dialog = tk.Toplevel(self)
        self._cad_palette = dialog
        dialog.title("Dibujo y herramientas (CAD)")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "cad_herramientas")
        ttk.Label(dialog,
                  text="Dibuja (muros, espacios, zonas y vanos) o edita "
                       "lo que ya hay. Esc o el botón cancelan; la barra "
                       "de estado va pidiendo cada paso.",
                  style="Hint.TLabel", wraplength=200,
                  justify="left").pack(fill="x", padx=8, pady=(6, 2))

        # -- DIBUJAR (v3.33.0): dos clics y la entidad nace real -------
        marco_dib = ttk.LabelFrame(dialog, text="Dibujar")
        marco_dib.pack(fill="x", padx=8, pady=(2, 2))
        cuadricula = ttk.Frame(marco_dib)
        cuadricula.pack(fill="x", padx=4, pady=2)
        for indice, (clave, _glifo, nombre) in enumerate(
                dib.HERRAMIENTAS_DIBUJO):
            boton = ttk.Button(
                cuadricula, text=icons.label("cad_" + clave, nombre),
                command=lambda c=clave: self._cad_set_tool(c))
            self._tip(boton, "cad_" + clave)
            boton.grid(row=indice // 2, column=indice % 2,
                       sticky="ew", padx=2, pady=1)
        cuadricula.columnconfigure(0, weight=1)
        cuadricula.columnconfigure(1, weight=1)
        config = ttk.Frame(marco_dib)
        config.pack(fill="x", padx=4, pady=(0, 4))
        self._dib_espesor = tk.StringVar(value="0.20")
        self._dib_altura = tk.StringVar(value="")
        self._dib_nombre = tk.StringVar(value="")
        self._dib_puerta_ancho = tk.StringVar(value="0.90")
        self._dib_puerta_alto = tk.StringVar(value="2.10")
        self._dib_ventana_ancho = tk.StringVar(value="1.20")
        self._dib_ventana_alto = tk.StringVar(value="1.20")
        self._dib_ventana_umbral = tk.StringVar(value="0.90")
        try:
            usos_dna = sorted(self.ctx.dna_registry.types())
        except Exception:  # noqa: BLE001 — sin DNA cargado
            usos_dna = [dib.USO_ESPACIO_DEF]
        self._dib_uso = tk.StringVar(value=dib.USO_ESPACIO_DEF)
        self._dib_kind = tk.StringVar(value=dib.KIND_ZONA_DEF)
        ttk.Label(config, text="Espesor muro (m):").grid(
            row=0, column=0, sticky="w")
        ttk.Entry(config, textvariable=self._dib_espesor,
                  width=7).grid(row=0, column=1, sticky="w", padx=2)
        ttk.Label(config, text="Altura (m):").grid(row=0, column=2,
                                                   sticky="e")
        ttk.Entry(config, textvariable=self._dib_altura,
                  width=7).grid(row=0, column=3, sticky="w", padx=2)
        ttk.Label(config, text="Uso local:").grid(row=1, column=0,
                                                  sticky="w")
        ttk.Combobox(config, textvariable=self._dib_uso,
                     values=usos_dna, width=14).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=2)
        ttk.Label(config, text="Zona:").grid(row=2, column=0,
                                             sticky="w")
        ttk.Combobox(config, textvariable=self._dib_kind,
                     values=list(dib.KINDS_ZONA), width=12,
                     state="readonly").grid(row=2, column=1,
                                            sticky="w", padx=2)
        ttk.Label(config, text="Nombre:").grid(row=3, column=0,
                                               sticky="w")
        ttk.Entry(config, textvariable=self._dib_nombre,
                  width=16).grid(row=3, column=1, columnspan=2,
                                 sticky="ew", padx=2)
        ttk.Label(config, text="Puerta a×h (m):").grid(
            row=4, column=0, sticky="w")
        ttk.Entry(config, textvariable=self._dib_puerta_ancho,
                  width=6).grid(row=4, column=1, sticky="w", padx=2)
        ttk.Entry(config, textvariable=self._dib_puerta_alto,
                  width=6).grid(row=4, column=2, sticky="w", padx=2)
        ttk.Label(config, text="Ventana a×h (m):").grid(
            row=5, column=0, sticky="w")
        ttk.Entry(config, textvariable=self._dib_ventana_ancho,
                  width=6).grid(row=5, column=1, sticky="w", padx=2)
        ttk.Entry(config, textvariable=self._dib_ventana_alto,
                  width=6).grid(row=5, column=2, sticky="w", padx=2)
        ttk.Label(config, text="Umbral (m):").grid(row=6, column=0,
                                                   sticky="w")
        ttk.Entry(config, textvariable=self._dib_ventana_umbral,
                  width=6).grid(row=6, column=1, sticky="w", padx=2)

        botones: Dict[str, ttk.Button] = {}
        for clave, _glifo, nombre in cad.HERRAMIENTAS:
            boton = ttk.Button(dialog,
                               text=icons.label("cad_" + clave, nombre),
                               command=lambda c=clave: self._cad_set_tool(c))
            self._tip(boton, "cad_" + clave)
            boton.pack(fill="x", padx=8, pady=2)
            botones[clave] = boton
        fila = ttk.Frame(dialog)
        fila.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(fila, text="Chaflán (m):").pack(side="left")
        self._cad_dist_var = tk.StringVar(value="0.50")
        ttk.Entry(fila, textvariable=self._cad_dist_var,
                  width=7).pack(side="left", padx=4)
        ttk.Button(dialog, text="✕ Cancelar herramienta (Esc)",
                   command=self._cad_cancelar).pack(fill="x", padx=8,
                                                    pady=(8, 2))
        dialog.bind("<Escape>", self._cad_cancelar)
        dialog._cad_botones = botones
        self._say("Paleta de herramientas de edición abierta.",
                  "Elige una herramienta y sigue los pasos de la barra")

    def _cad_set_tool(self, clave: str) -> None:
        """Activa (o desactiva, si ya estaba) una herramienta."""
        if self._cad_tool == clave:
            self._cad_cancelar()
            return
        self._cad_tool = clave
        self._cad_pasos = []
        self._cad_ref = None
        self._cad_datos = {}
        self._cad_paso = 0
        # ESPACIO repetirá esta orden, como la línea de comandos (v3.16.0)
        self.teclas.registrar_orden(clave)
        try:
            self.canvas.configure(cursor="crosshair")
        except Exception:  # noqa: BLE001 - lienzo aún sin realizar
            pass
        prompts = cad.PROMPTS.get(clave) \
            or dib.PROMPTS_DIBUJO.get(clave, ("",))
        self._say(f"Herramienta {prompts[0].lower()}",
                  prompts[1] if len(prompts) > 1 else "")
        self._cad_overlay()

    def _cad_cancelar(self, _evento: Any = None) -> None:
        activo = bool(self._cad_tool or self._cad_ref
                      or self._zoom_orden or self._marco_sel
                      or self._seleccion_multi)
        self._cad_tool = None
        self._cad_pasos = []
        self._cad_ref = None
        self._cad_datos = {}
        self._cad_paso = 0
        # v3.38.0: cancelar desarma tambien la navegación y el marco
        self._zoom_orden = False
        self._zoom_marco = None
        self._marco_sel = None
        self._marco_activo = False
        self._seleccion_multi = []
        try:
            self.canvas.delete("zoommarco")
            self.canvas.delete("marcoseleccion")
            self.canvas.delete("cadoverlay")
        except Exception:  # noqa: BLE001 - lienzo sin realizar aun
            pass
        try:
            self.canvas.configure(cursor="")
        except Exception:  # noqa: BLE001
            pass
        if not activo:
            return
        self._say("Orden cancelada (ESC).",
                  "Elige otra en el panel de herramientas CAD")

    def _cad_click(self, event) -> None:
        """Un clic con herramienta activa: avanza la máquina de estados."""
        tool = self._cad_tool
        if not tool:
            return
        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 600)
        punto = self.viewport.from_screen(event.x, event.y, width, height)
        uid = self._hit_uid(event)
        fila = self._find_row(uid) if uid else None
        prompts = cad.PROMPTS.get(tool) \
            or dib.PROMPTS_DIBUJO.get(tool, ("",))

        if tool in dib.PUNTOS_DIBUJO:
            self._cad_click_dibujo(tool, punto, fila, prompts)
            return

        if not self._cad_ref:
            if fila is None:
                self._say(prompts[0],
                          "Clic directamente sobre un objeto del plano")
                return
            if fila.type not in cad.TIPOS_POR_HERRAMIENTA.get(tool, ()):
                self._say(f"{prompts[0]} (ahí hay {fila.type})",
                          "Ese objeto no sirve para esta herramienta")
                return
            self._cad_ref = (fila.type, fila.uid)
            self.selection = fila
            self.refresh_properties()
            self.redraw()
            self._cad_paso = 1
            if tool == "borrar":
                self._cad_borrar_fila(fila)
                return
            self._say(f"{fila.type} {fila.code} elegido.",
                      prompts[1] if len(prompts) > 1 else "")
            self._cad_overlay()
            return

        if tool in self._CAD_OTRO and "otro" not in self._cad_datos:
            if fila is None or fila.type != "WALL":
                self._say(prompts[1], "Clic sobre un muro")
                return
            if fila.uid == self._cad_ref[1]:
                self._say(prompts[1],
                          "Elige un muro DISTINTO al primero")
                return
            self._cad_datos["otro"] = fila.uid
            self._cad_paso = 2
            self._say(f"{fila.code} elegido de cuchilla/objetivo.",
                      prompts[-1])
            self._cad_overlay()
            return

        self._cad_pasos.append(
            self._punto_ayudado(self._cad_pasos[-1]
                                if self._cad_pasos else None,
                                punto)[0])
        if len(self._cad_pasos) < self._CAD_PUNTOS.get(tool, 0):
            indice = min(1 + self._cad_paso, len(prompts) - 1)
            self._cad_paso += 1
            self._say(prompts[indice], "")
            self._cad_overlay(event)
            return
        self._cad_ejecuta()

    def _cad_lado(self, ref: str, punto) -> str:
        """«inicio» o «fin»: el extremo del muro más cercano al clic."""
        muro = cad.resolver(self.ctx, "WALL", ref)
        d_ini = math.hypot(punto[0] - muro.start[0],
                           punto[1] - muro.start[1])
        d_fin = math.hypot(punto[0] - muro.end[0], punto[1] - muro.end[1])
        return "inicio" if d_ini <= d_fin else "fin"

    def _cad_ejecuta(self) -> None:
        """Reúne los pasos y llama al motor; errores amables y rollback."""
        tool = self._cad_tool
        if tool in dib.PUNTOS_DIBUJO:
            self._cad_ejecuta_dibujo(tool)
            return
        tipo, ref = self._cad_ref
        puntos = list(self._cad_pasos)
        otro = self._cad_datos.get("otro")
        try:
            if tool in ("mover", "copiar"):
                dx = puntos[1][0] - puntos[0][0]
                dy = puntos[1][1] - puntos[0][1]
                if tool == "mover":
                    resumen = cad.mover(self.ctx, [(tipo, ref)], dx, dy)
                else:
                    resumen = cad.copiar(self.ctx, tipo, ref, dx, dy)
            elif tool == "reflejar":
                resumen = cad.reflejar(self.ctx, tipo, ref,
                                       puntos[0], puntos[1])
            elif tool == "girar":
                centro = puntos[0]
                angulo = math.degrees(
                    math.atan2(puntos[2][1] - centro[1],
                               puntos[2][0] - centro[0])
                    - math.atan2(puntos[1][1] - centro[1],
                                 puntos[1][0] - centro[0]))
                resumen = cad.girar(self.ctx, tipo, ref, centro, angulo)
            elif tool == "recortar":
                resumen = cad.recortar(self.ctx, ref, otro,
                                       self._cad_lado(ref, puntos[0]))
            elif tool == "alargar":
                resumen = cad.alargar(self.ctx, ref, otro,
                                      self._cad_lado(ref, puntos[0]))
            elif tool == "chaflan":
                distancia = float(str(self._cad_dist_var.get())
                                  .replace(",", "."))
                resumen = cad.chaflan(self.ctx, ref, otro, distancia)
            elif tool == "dividir":
                resumen = cad.dividir(self.ctx, ref, puntos[0])
            elif tool == "estirar":
                resumen = cad.estirar(self.ctx, ref,
                                      self._cad_lado(ref, puntos[0]),
                                      puntos[1])
            elif tool == "paralela":
                muro = cad.resolver(self.ctx, "WALL", ref)
                x1, y1 = muro.start
                x2, y2 = muro.end
                largo = math.hypot(x2 - x1, y2 - y1) or 1.0
                distancia = (-(puntos[0][0] - x1) * (y2 - y1)
                             + (puntos[0][1] - y1) * (x2 - x1)) / largo
                resumen = cad.paralela(self.ctx, ref, distancia)
            else:
                return
        except Exception as exc:  # noqa: BLE001 - mensaje amable y rollback
            self.ctx.rollback()
            accion = getattr(exc, "suggested_action", "")
            texto = str(getattr(exc, "message", exc))
            messagebox.showerror(
                "Herramienta de edición",
                texto + (f"\n\nSugerencia: {accion}" if accion else ""),
                parent=self)
            self._cad_pasos = []
            self._cad_datos.pop("otro", None)
            self._cad_paso = 1
            prompts = cad.PROMPTS.get(tool, ("",))
            self._say("La operación no se aplicó.",
                      prompts[1] if len(prompts) > 1 else "")
            self._cad_overlay()
            return
        self._cad_fin(resumen)

    def _cad_fin(self, resumen: Dict[str, Any]) -> None:
        """Cierra la operación: QTO, commit, refresco y mensaje."""
        try:
            cad.finalizar(self.ctx, resumen)
            self.ctx.commit()
        except Exception as exc:  # noqa: BLE001
            self.ctx.rollback()
            messagebox.showerror("Herramienta de edición", str(exc),
                                 parent=self)
            self._cad_cancelar()
            return
        self._cad_pasos = []
        self._cad_ref = None
        self._cad_datos = {}
        self._cad_paso = 0
        self.refresh_all()
        self._cad_overlay()
        texto = dib.texto_resumen_dibujo(resumen) \
            if self._cad_tool in dib.PUNTOS_DIBUJO \
            else cad.texto_resumen(resumen)
        self._say(texto,
                  "Ctrl+Z deshace paso a paso; la herramienta sigue activa")

    def _cad_borrar_fila(self, fila: ObjectRow) -> None:
        if not messagebox.askyesno(
                "Eliminar",
                f"¿Eliminar {fila.type} {fila.code} — {fila.name}?\n\n"
                "Queda registrado y puedes deshacerlo con Ctrl+Z.",
                parent=self):
            self._cad_cancelar()
            return
        try:
            self.edit_service.delete(fila)
            self.ctx.commit()
        except Exception as exc:  # noqa: BLE001
            self.ctx.rollback()
            messagebox.showerror("Eliminar", str(exc), parent=self)
        self.selection = None
        self._cad_ref = None
        self._cad_datos = {}
        self._cad_paso = 0
        self.refresh_all()
        self._say(f"Eliminado {fila.type} {fila.code}.",
                  "Ctrl+Z lo recupera; la herramienta sigue activa")

    def _cad_poligono_ref(self) -> Optional[Any]:
        """Geometría actual de la entidad elegida (para el fantasma)."""
        if not self._cad_ref:
            return None
        try:
            return cad.resolver(self.ctx, self._cad_ref[0], self._cad_ref[1])
        except Exception:  # noqa: BLE001
            return None

    def _cad_overlay(self, event: Any = None) -> None:
        """Guías de la herramienta: marcas, elástico y fantasma."""
        try:
            self.canvas.delete("cadoverlay")
        except Exception:  # noqa: BLE001
            return
        if not self._cad_tool:
            return
        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 600)
        color = "#e69138"

        def pantalla(p):
            return self.viewport.to_screen(p[0], p[1], width, height)

        for p in self._cad_pasos:
            x, y = pantalla(p)
            self.canvas.create_line(x - 5, y, x + 5, y, fill=color,
                                    tags=("cadoverlay",))
            self.canvas.create_line(x, y - 5, x, y + 5, fill=color,
                                    tags=("cadoverlay",))
        # Pantalla dinamica (DYN, F12): "d 3.42 < 45" junto al cursor
        # mientras el tramo vive (v3.38.0). Antes de los retornos de
        # cada herramienta: el DYN SIEMPRE acompana al paso vivo.
        if (self.teclas.estado.get("din") and event is not None
                and self._cad_pasos):
            mundo = self.viewport.from_screen(event.x, event.y,
                                              width, height)
            dyn = crd.texto_dinamico(self._cad_pasos[-1], mundo)
            if dyn:
                self.canvas.create_rectangle(
                    event.x + 18, event.y - 22, event.x + 148,
                    event.y - 2, fill="#fafae6", outline="#8a8a6a",
                    width=1, tags=("cadoverlay",))
                self.canvas.create_text(
                    event.x + 22, event.y - 12, anchor="w", text=dyn,
                    font=("TkDefaultFont", 8), fill="#333300",
                    tags=("cadoverlay",))
        # DIBUJO (v3.33.0): vista previa del rectángulo (espacio/zona)
        # y del muro con su espesor real.
        if self._cad_tool in ("dib_espacio", "dib_zona") \
                and len(self._cad_pasos) == 1 and event is not None:
            x1, y1 = pantalla(self._cad_pasos[0])
            self.canvas.create_rectangle(x1, y1, event.x, event.y,
                                         outline=color, dash=(4, 2),
                                         tags=("cadoverlay",))
            return
        if self._cad_tool == "dib_muro" and len(self._cad_pasos) == 1 \
                and event is not None:
            x1, y1 = pantalla(self._cad_pasos[0])
            espesor = self._dib_float(getattr(self, "_dib_espesor", None),
                                      dib.ESPESOR_MURO_DEF)
            grosor = max(2, int(espesor * self.viewport.scale))
            self.canvas.create_line(x1, y1, event.x, event.y, fill=color,
                                    width=grosor, dash=(4, 2),
                                    tags=("cadoverlay",))
            return
        if event is not None and self._cad_pasos:
            px, py = pantalla(self._cad_pasos[-1])
            self.canvas.create_line(px, py, event.x, event.y, fill=color,
                                    dash=(4, 2), tags=("cadoverlay",))
        entidad = self._cad_poligono_ref()
        if (self._cad_tool in ("mover", "copiar") and entidad is not None
                and self._cad_pasos and event is not None):
            mundo = self.viewport.from_screen(event.x, event.y,
                                              width, height)
            dx = mundo[0] - self._cad_pasos[0][0]
            dy = mundo[1] - self._cad_pasos[0][1]
            if getattr(entidad, "ENTITY_TYPE", "") == "WALL":
                x1, y1 = pantalla((entidad.start[0] + dx,
                                   entidad.start[1] + dy))
                x2, y2 = pantalla((entidad.end[0] + dx,
                                   entidad.end[1] + dy))
                grosor = max(2, int(entidad.thickness_m
                                    * self.viewport.scale))
                self.canvas.create_line(x1, y1, x2, y2, fill=color,
                                        width=grosor, dash=(3, 3),
                                        tags=("cadoverlay",))
            else:
                puntos = []
                for x, y in (entidad.boundary or []):
                    sx, sy = pantalla((x + dx, y + dy))
                    puntos += [sx, sy]
                if len(puntos) >= 6:
                    self.canvas.create_polygon(*puntos, fill="",
                                               outline=color, dash=(3, 3),
                                               tags=("cadoverlay",))

    def _cad_estado(self) -> Dict[str, Any]:
        """Estado de la herramienta (ganchos de prueba)."""
        return {"tool": self._cad_tool, "pasos": list(self._cad_pasos),
                "ref": self._cad_ref, "paso": self._cad_paso}

    # -- herramientas de DIBUJO (v3.33.0) ---------------------------------
    # Muros, espacios, zonas y vanos nacen con dos clics por los
    # caminos oficiales; ui/dibujo_cad.py aporta las reglas del DNA.

    @staticmethod
    def _dib_float(var: Any, defecto: float) -> float:
        """Float tolerante de un StringVar (admite coma decimal)."""
        try:
            texto = str(var.get()).strip().replace(",", ".")
            return float(texto) if texto else defecto
        except (TypeError, ValueError, AttributeError):
            return defecto

    def _nivel_de_dibujo(self) -> str:
        """Nivel activo para dibujar: el del filtro «Nivel:» si está
        concreto; si no, el primero del proyecto (la PB de siempre)."""
        try:
            niveles = self.ctx.architecture.list("LEVEL",
                                                 self.ctx.project.id)
        except Exception:  # noqa: BLE001 — sin proyecto cargado
            return ""
        if not niveles:
            return ""
        filtro = ""
        if getattr(self, "level_var", None) is not None:
            filtro = (self.level_var.get() or "").strip()
        if filtro and filtro != "(todos)":
            for lv in niveles:
                if lv.name == filtro or lv.code == filtro:
                    return lv.name
        return niveles[0].name

    def _cad_click_dibujo(self, tool: str, punto, fila, prompts) -> None:
        """Clic con herramienta de DIBUJO activa."""
        if tool in dib.ES_VANO_DIBUJO:
            if fila is None or fila.type != "WALL":
                self._say(prompts[0],
                          "Clic directamente sobre un muro dibujado o "
                          "generado")
                return
            self._cad_datos["muro"] = fila.uid
            self._cad_pasos = [punto]
            self._cad_ejecuta()
            return
        punto = self._punto_ayudado(
            self._cad_pasos[-1] if self._cad_pasos else None, punto)[0]
        self._cad_pasos.append(punto)
        if len(self._cad_pasos) < dib.PUNTOS_DIBUJO.get(tool, 2):
            self._cad_paso = len(self._cad_pasos)
            indice = min(len(self._cad_pasos), len(prompts) - 1)
            self._say(prompts[indice], "")
            self._cad_overlay()
            return
        self._cad_ejecuta()

    def _dib_operacion(self, tool: str) -> Dict[str, Any]:
        """Llama al motor de dibujo con la configuración de la paleta."""
        nivel = self._nivel_de_dibujo()
        if not nivel:
            raise ValueError(
                "No hay niveles en el proyecto: dibuje tras crear uno "
                "con el asistente de edificación")
        if tool in dib.ES_VANO_DIBUJO:
            muro = self._cad_datos.get("muro")
            punto = self._cad_pasos[0] if self._cad_pasos else (0.0, 0.0)
            if tool == "dib_puerta":
                return dib.dibujar_vano(
                    self.ctx, "DOOR", muro, punto,
                    ancho=self._dib_float(getattr(self, "_dib_puerta_ancho",
                                                  None),
                                          dib.PUERTA_ANCHO_DEF),
                    alto=self._dib_float(getattr(self, "_dib_puerta_alto",
                                                 None),
                                         dib.PUERTA_ALTO_DEF))
            return dib.dibujar_vano(
                self.ctx, "WINDOW", muro, punto,
                ancho=self._dib_float(getattr(self, "_dib_ventana_ancho",
                                              None),
                                      dib.VENTANA_ANCHO_DEF),
                alto=self._dib_float(getattr(self, "_dib_ventana_alto",
                                             None),
                                     dib.VENTANA_ALTO_DEF),
                sill=self._dib_float(getattr(self, "_dib_ventana_umbral",
                                             None),
                                     dib.VENTANA_UMBRAL_DEF))
        p1 = self._cad_pasos[0]
        p2 = self._cad_pasos[1]
        if tool == "dib_muro":
            altura = self._dib_float(getattr(self, "_dib_altura", None),
                                     0.0)
            return dib.dibujar_muro(
                self.ctx, nivel, p1, p2,
                espesor=self._dib_float(getattr(self, "_dib_espesor",
                                                None),
                                        dib.ESPESOR_MURO_DEF),
                altura=altura if altura > 0 else None)
        if tool == "dib_espacio":
            return dib.dibujar_espacio(
                self.ctx, nivel, p1, p2,
                nombre=(getattr(self, "_dib_nombre", None).get()
                        if getattr(self, "_dib_nombre", None) is not None
                        else "").strip(),
                uso=(getattr(self, "_dib_uso", None).get()
                     if getattr(self, "_dib_uso", None) is not None
                     else dib.USO_ESPACIO_DEF) or dib.USO_ESPACIO_DEF)
        nombre = (getattr(self, "_dib_nombre", None).get()
                  if getattr(self, "_dib_nombre", None) is not None
                  else "").strip()
        kind = (getattr(self, "_dib_kind", None).get()
                if getattr(self, "_dib_kind", None) is not None
                else dib.KIND_ZONA_DEF) or dib.KIND_ZONA_DEF
        return dib.dibujar_zona(self.ctx, nombre or "Zona dibujada",
                                p1, p2, kind=kind, nivel_ref=nivel)

    def _cad_ejecuta_dibujo(self, tool: str) -> None:
        """Ejecuta el dibujo; errores amables y rollback como en la
        edición."""
        try:
            resumen = self._dib_operacion(tool)
        except Exception as exc:  # noqa: BLE001 — mensaje amable y rollback
            self.ctx.rollback()
            accion = getattr(exc, "suggested_action", "")
            texto = str(getattr(exc, "message", exc))
            messagebox.showerror(
                "Herramienta de dibujo",
                texto + (f"\n\nSugerencia: {accion}" if accion else ""),
                parent=self)
            self._cad_pasos = []
            self._cad_datos.pop("muro", None)
            self._cad_paso = 0
            prompts = dib.PROMPTS_DIBUJO.get(tool, ("",))
            self._say("El dibujo no se aplicó.",
                      prompts[1] if len(prompts) > 1 else "")
            self._cad_overlay()
            return
        self._cad_fin(resumen)

    # -- asistente de SERVICIOS (v3.33.0) ---------------------------------
    # Servicios completos por temática (anatomía patológica, laboratorio
    # clínico, imagenología, hemodiálisis, CEyE, farmacia): parámetros
    # dinámicos del catálogo, programa dimensionado, validación
    # funcional y aplicación al proyecto por los caminos oficiales.

    def open_servicios_dialog(self) -> None:
        """Asistente dinámico de servicios completos."""
        from domain.servicios_specs import servicios_disponibles
        if self._servicios_dialog is not None \
                and self._servicios_dialog.winfo_exists():
            self._servicios_dialog.deiconify()
            self._servicios_dialog.lift()
            return
        try:
            disponibles = servicios_disponibles()
        except Exception as exc:  # noqa: BLE001 — catálogo ausente
            messagebox.showerror("Asistente de servicios", str(exc),
                                 parent=self)
            return
        dialog = tk.Toplevel(self)
        self._servicios_dialog = dialog
        dialog.title("Asistente de servicios (por temática)")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "servicios")
        marco = ttk.Frame(dialog, padding=8)
        marco.pack(fill="both", expand=True)

        ttk.Label(marco, text="Servicio:").grid(row=0, column=0,
                                                sticky="w")
        self._servicios_codigo = tk.StringVar(
            value=f"{disponibles[0][0]} - {disponibles[0][1]}"
            if disponibles else "")
        self._servicios_combo = ttk.Combobox(
            marco, textvariable=self._servicios_codigo,
            values=[f"{c} - {n}" for c, n in disponibles],
            state="readonly", width=34)
        self._servicios_combo.grid(row=0, column=1, sticky="ew", padx=6)
        self._servicios_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._servicios_carga())
        # filtro por sector del catálogo universal (v3.36.0)
        ttk.Label(marco, text="Sector:").grid(row=0, column=2,
                                              sticky="w")
        self._servicios_sector = tk.StringVar(value="Todos")
        self._servicios_filtro = ttk.Combobox(
            marco, textvariable=self._servicios_sector,
            values=self._servicios_valores_sector(), state="readonly",
            width=20)
        self._servicios_filtro.grid(row=0, column=3, sticky="w",
                                    padx=(6, 0))
        self._servicios_filtro.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._servicios_aplica_filtro())

        self._servicios_vars: List[Any] = []
        self._servicios_params = ttk.Frame(marco)
        self._servicios_params.grid(row=1, column=0, columnspan=2,
                                    sticky="ew", pady=(6, 2))

        arbol_marco = ttk.Frame(marco)
        arbol_marco.grid(row=2, column=0, columnspan=2,
                         sticky="nsew", pady=4)
        self._servicios_arbol = ttk.Treeview(
            arbol_marco,
            columns=("local", "uso", "area", "dim", "flujo", "grupo"),
            show="headings", height=9)
        for col, texto, ancho in (("local", "Local", 200),
                                  ("uso", "Uso (DNA)", 140),
                                  ("area", "Área m2", 64),
                                  ("dim", "Sugerido m", 100),
                                  ("flujo", "Flujo", 74),
                                  ("grupo", "Grupo", 96)):
            self._servicios_arbol.heading(col, text=texto)
            self._servicios_arbol.column(col, width=ancho, anchor="w")
        arbol_barra = ttk.Scrollbar(arbol_marco, orient="vertical",
                                    command=self._servicios_arbol.yview)
        self._servicios_arbol.configure(yscrollcommand=arbol_barra.set)
        self._servicios_arbol.pack(side="left", fill="both",
                                   expand=True)
        arbol_barra.pack(side="right", fill="y")

        self._servicios_total = tk.StringVar(value="")
        ttk.Label(marco, textvariable=self._servicios_total).grid(
            row=3, column=0, columnspan=2, sticky="w")

        destino = ttk.LabelFrame(marco, text="Destino")
        destino.grid(row=4, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(destino, text="Nivel:").grid(row=0, column=0,
                                               sticky="w")
        self._servicios_nivel = tk.StringVar()
        self._servicios_niveles = ttk.Combobox(
            destino, textvariable=self._servicios_nivel, width=18,
            state="readonly")
        self._servicios_niveles.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(destino, text="Origen X,Y (m):").grid(
            row=0, column=2, sticky="e", padx=(8, 0))
        self._servicios_ox = tk.StringVar(value="0")
        self._servicios_oy = tk.StringVar(value="0")
        ttk.Entry(destino, textvariable=self._servicios_ox,
                  width=6).grid(row=0, column=3, sticky="w", padx=2)
        ttk.Entry(destino, textvariable=self._servicios_oy,
                  width=6).grid(row=0, column=4, sticky="w", padx=2)
        self._servicios_muros = tk.BooleanVar(value=False)
        ttk.Checkbutton(destino, variable=self._servicios_muros,
                        text="Trazar muros de cada local (las aristas "
                             "compartidas quedan duplicadas)").grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(2, 0))

        acciones = ttk.Frame(marco)
        acciones.grid(row=5, column=0, columnspan=2, sticky="ew",
                      pady=(4, 2))
        ttk.Button(acciones, text="Recalcular programa",
                   command=self._servicios_recalcular).pack(side="left")
        ttk.Button(acciones, text="Aplicar al nivel",
                   style="Accent.TButton",
                   command=self._servicios_aplicar).pack(side="left",
                                                         padx=6)
        ttk.Label(acciones, text="Documento:").pack(side="left",
                                                     padx=(14, 2))
        self._servicios_doc = tk.StringVar(
            value="Programa y validación")
        doc_combo = ttk.Combobox(
            acciones, textvariable=self._servicios_doc, state="readonly",
            width=30, values=(
                "Programa y validación",
                "Ficha del local (seleccione en la tabla)",
                "Matriz de instalaciones",
                "Relaciones entre servicios",
                "Flujos hospitalarios",
                "Reglas de generación"))
        doc_combo.pack(side="left")
        doc_combo.bind("<<ComboboxSelected>>",
                       lambda _e: self._servicios_muestra_doc())

        texto_marco = ttk.Frame(marco)
        texto_marco.grid(row=6, column=0, columnspan=2, sticky="nsew")
        self._servicios_texto = tk.Text(texto_marco, height=12,
                                        wrap="word", width=82)
        barra = ttk.Scrollbar(texto_marco, orient="vertical",
                              command=self._servicios_texto.yview)
        self._servicios_texto.configure(yscrollcommand=barra.set)
        self._servicios_texto.pack(side="left", fill="both",
                                   expand=True)
        barra.pack(side="right", fill="y")

        marco.columnconfigure(1, weight=1)
        marco.rowconfigure(6, weight=1)
        self._servicios_refresca_niveles()
        self._servicios_carga()
        self._say("Asistente de servicios abierto.",
                  "Elige la temática, ajusta los parámetros y aplica el "
                  "servicio a un nivel")

    def _servicios_sel(self) -> str:
        """Código del servicio elegido en el combobox."""
        texto = self._servicios_codigo.get() \
            if getattr(self, "_servicios_codigo", None) is not None else ""
        return texto.split(" - ")[0].strip() if texto else ""

    def _servicios_valores_sector(self) -> List[str]:
        """Etiquetas del filtro de sector («Todos» primero)."""
        from domain.servicios_specs import servicios_por_sector
        try:
            return ["Todos"] + [et for et, _items
                                in servicios_por_sector()]
        except Exception:  # noqa: BLE001 — catálogo ausente
            return ["Todos"]

    def _servicios_aplica_filtro(self) -> None:
        """Repopular el combobox de servicios según el sector."""
        from domain.servicios_specs import servicios_por_sector
        sector = self._servicios_sector.get()
        try:
            grupos = servicios_por_sector()
        except Exception:  # noqa: BLE001 — catálogo ausente
            grupos = []
        if sector in ("", "Todos"):
            items = [(c, n) for _et, lista in grupos
                     for c, n in lista]
        else:
            items = next((lista for et, lista in grupos
                          if et == sector), [])
        valores = [f"{c} - {n}" for c, n in items]
        self._servicios_combo.configure(values=valores)
        if valores:
            self._servicios_combo.current(0)
            self._servicios_carga()
        else:
            self._servicios_codigo.set("")

    def _servicios_carga(self) -> None:
        """Reconstruye los parámetros dinámicos del servicio elegido."""
        from domain.servicios_specs import servicio
        for hijo in self._servicios_params.winfo_children():
            hijo.destroy()
        self._servicios_vars = []
        codigo = self._servicios_sel()
        if not codigo:
            return
        try:
            item = servicio(codigo)
        except Exception as exc:  # noqa: BLE001 — error amable
            messagebox.showerror("Asistente de servicios", str(exc),
                                 parent=self._servicios_dialog)
            return
        for indice, p in enumerate(item.parametros):
            etiqueta = p.nombre + (f" ({p.unidad})" if p.unidad else "")
            ttk.Label(self._servicios_params,
                      text=etiqueta + ":").grid(row=indice, column=0,
                                                sticky="w")
            if p.tipo == "bool":
                var = tk.BooleanVar(value=bool(p.defecto))
                ttk.Checkbutton(self._servicios_params,
                                variable=var).grid(row=indice, column=1,
                                                   sticky="w", padx=4)
            else:
                var = tk.StringVar(value=str(p.defecto))
                ttk.Entry(self._servicios_params, textvariable=var,
                          width=9).grid(row=indice, column=1,
                                        sticky="w", padx=4)
            self._servicios_vars.append((p, var))
        self._servicios_recalcular()

    def _servicios_params_dict(self) -> Dict[str, Any]:
        """Los parámetros del panel como diccionario sano."""
        out: Dict[str, Any] = {}
        for p, var in getattr(self, "_servicios_vars", []):
            if p.tipo == "bool":
                out[p.codigo] = bool(var.get())
            else:
                out[p.codigo] = self._dib_float(var,
                                                float(p.defecto or 0))
        return out

    def _servicios_recalcular(self) -> None:
        """Programa del servicio: tabla, totales y texto completo."""
        from domain import servicios_engine as eng
        codigo = self._servicios_sel()
        if not codigo:
            return
        try:
            programa = eng.programa_servicio(codigo,
                                             self._servicios_params_dict())
        except Exception as exc:  # noqa: BLE001 — error amable
            messagebox.showerror("Asistente de servicios", str(exc),
                                 parent=self._servicios_dialog)
            return
        self._servicios_programa = programa
        arbol = self._servicios_arbol
        for hijo in arbol.get_children():
            arbol.delete(hijo)
        for r in programa["renglones"]:
            arbol.insert("", "end", values=(
                r["nombre"] + ("  [crítico]" if r["critico"] else ""),
                r["space_type"], f"{r['area_m2']:.2f}",
                f"{r['ancho_m']:.2f} x {r['fondo_m']:.2f}",
                r["flujo"], r.get("grupo", "")))
        self._servicios_total.set(
            f"{programa['totales']['locales']} local(es) · "
            f"{programa['totales']['area_m2']:.2f} m2 · "
            + " · ".join(
                f"{g}: {d['area_m2']:.0f} m2"
                for g, d in programa["totales"].get("grupos", {})
                .items())
            if programa["totales"].get("grupos") else
            f"{programa['totales']['locales']} local(es) · "
            f"{programa['totales']['area_m2']:.2f} m2")
        self._servicios_muestra_doc()

    def _servicios_muestra_doc(self) -> None:
        """Renderiza en el cuadro de texto el documento elegido
        (programa y validación, ficha del local, matriz, relaciones,
        flujos o reglas)."""
        from domain import servicios_engine as eng
        programa = getattr(self, "_servicios_programa", None)
        if programa is None:
            return
        codigo = programa["servicio"]
        eleccion = self._servicios_doc.get() \
            if getattr(self, "_servicios_doc", None) is not None \
            else "Programa y validación"
        try:
            if eleccion == "Ficha del local (seleccione en la tabla)":
                sel = self._servicios_arbol.selection()
                if not sel:
                    texto = ("Seleccione una fila de la tabla del "
                             "programa para ver su ficha de local "
                             "(sección 30: superficies, cotas, "
                             "instalaciones, acabados, equipamiento y "
                             "relaciones).")
                else:
                    nombre = str(self._servicios_arbol.item(
                        sel[0], "values")[0]).replace("  [crítico]", "")
                    renglon = next(
                        (r for r in programa["renglones"]
                         if r["nombre"] == nombre), None)
                    texto = eng.texto_ficha_local(
                        codigo, renglon["codigo"] if renglon else "")
            elif eleccion == "Matriz de instalaciones":
                texto = eng.texto_matriz_instalaciones(codigo)
            elif eleccion == "Relaciones entre servicios":
                texto = eng.texto_relaciones_servicios(codigo)
            elif eleccion == "Flujos hospitalarios":
                texto = eng.texto_flujos(codigo)
            elif eleccion == "Reglas de generación":
                texto = eng.texto_reglas_generacion()
            else:
                texto = eng.texto_programa(programa) + "\n\n" + \
                    eng.texto_validacion(programa["validacion"])
        except Exception as exc:  # noqa: BLE001 — error amable
            texto = f"No se pudo generar el documento: {exc}"
        self._servicios_texto.configure(state="normal")
        self._servicios_texto.delete("1.0", "end")
        self._servicios_texto.insert("1.0", texto)
        self._servicios_texto.configure(state="disabled")

    def _servicios_refresca_niveles(self) -> None:
        """Niveles disponibles como destino (o aviso de creación)."""
        try:
            niveles = [lv.name for lv in
                       self.ctx.architecture.list("LEVEL",
                                                  self.ctx.project.id)]
        except Exception:  # noqa: BLE001 — sin proyecto cargado
            niveles = []
        if niveles:
            self._servicios_niveles.configure(values=niveles)
            self._servicios_niveles.current(0)
        else:
            self._servicios_niveles.configure(
                values=["(sin niveles: se creará edificio y nivel)"])
            self._servicios_nivel.set("")

    def _servicios_aplicar(self) -> None:
        """Aplica el servicio al nivel elegido y muestra la validación."""
        from domain import servicios_engine as eng
        codigo = self._servicios_sel()
        if not codigo:
            return
        nivel = (self._servicios_nivel.get() or "").strip()
        if nivel.startswith("("):
            nivel = ""
        try:
            ox = self._dib_float(self._servicios_ox, 0.0)
            oy = self._dib_float(self._servicios_oy, 0.0)
            resumen = eng.aplicar_servicio(
                self.ctx, codigo, self._servicios_params_dict(),
                nivel_ref=nivel, origen=(ox, oy),
                trazar_muros=bool(self._servicios_muros.get()))
            self.ctx.commit()
        except Exception as exc:  # noqa: BLE001 — error amable y rollback
            self.ctx.rollback()
            accion = getattr(exc, "suggested_action", "")
            messagebox.showerror(
                "Asistente de servicios",
                str(getattr(exc, "message", exc))
                + (f"\n\nSugerencia: {accion}" if accion else ""),
                parent=self._servicios_dialog)
            return
        self.refresh_all()
        texto = eng.texto_resumen_servicio(resumen) + "\n\n" + \
            eng.texto_validacion(resumen["validacion"])
        self._servicios_texto.configure(state="normal")
        self._servicios_texto.insert("1.0", texto + "\n\n")
        self._servicios_texto.configure(state="disabled")
        self._servicios_refresca_niveles()
        self._say(eng.texto_resumen_servicio(resumen),
                  "Los locales ya son entidades del proyecto: QTO, "
                  "presupuesto y validación los ven")

    # -- desde dibujo (v3.34.0): generación inversa ----------------------
    # Del contorno del área (espacio existente, rectángulo o DXF) a la
    # edificación o al servicio completo: el asistente infiere forma y
    # medidas, arma el programa según el tipo y el uso social, decide
    # si los locales entran en el área y sugiere el crecimiento en
    # altura (otros niveles) con el recinto de la escalera (Blondel).

    def open_desde_dibujo_dialog(self) -> None:
        """Asistente «Desde dibujo»: contorno -> edificación/servicio."""
        from domain.servicios_specs import servicios_disponibles
        if self._dd_dialog is not None \
                and self._dd_dialog.winfo_exists():
            self._dd_dialog.deiconify()
            self._dd_dialog.lift()
            return
        try:
            disponibles = servicios_disponibles()
        except Exception as exc:  # noqa: BLE001 — catálogo ausente
            messagebox.showerror("Desde dibujo", str(exc), parent=self)
            return
        dialog = tk.Toplevel(self)
        self._dd_dialog = dialog
        dialog.title("Desde dibujo: contorno -> edificación o servicio")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "desde_dibujo")
        marco = ttk.Frame(dialog, padding=8)
        marco.pack(fill="both", expand=True)

        # 0 · el modo del asistente (v3.39.0: básico / profesional /
        #     experto — cada modo muestra solo lo que toca)
        nivel_marco = ttk.LabelFrame(marco, text="0 · Modo del "
                                     "asistente")
        nivel_marco.pack(fill="x")
        self._dd_nivel = tk.StringVar(value="profesional")
        for valor, texto in (("basico", "Básico (lo esencial)"),
                             ("profesional",
                              "Profesional (tabla y alternativas)"),
                             ("experto",
                              "Experto (todo: espesores, patio, "
                              "historial)")):
            ttk.Radiobutton(nivel_marco, text=texto, value=valor,
                            variable=self._dd_nivel,
                            command=self._dd_nivel_cambio).pack(
                side="left", padx=(0, 8))

        # 1 · el contorno del área
        contorno = ttk.LabelFrame(marco, text="1 · El contorno del área")
        contorno.pack(fill="x")
        fila = ttk.Frame(contorno)
        fila.pack(fill="x", padx=4, pady=2)
        self._dd_origen = tk.StringVar(value="espacio")
        for valor, texto in (("espacio", "Espacio del proyecto"),
                             ("rectangulo", "Rectángulo"),
                             ("dxf", "Archivo DXF")):
            ttk.Radiobutton(fila, text=texto, value=valor,
                            variable=self._dd_origen,
                            command=self._dd_origen_cambio).pack(
                side="left", padx=(0, 8))
        self._dd_espacio = tk.StringVar()
        self._dd_espacios_combo = ttk.Combobox(
            contorno, textvariable=self._dd_espacio, width=42)
        self._dd_espacios_combo.pack(side="left", padx=4, pady=2)
        boton_refresca = ttk.Button(contorno, text="Refrescar",
                                    command=self._dd_refresca_espacios)
        boton_refresca.pack(side="left", padx=2, pady=2)
        self._dd_rec_ancho = tk.StringVar(value="20")
        self._dd_rec_fondo = tk.StringVar(value="12")
        self._dd_rec_ox = tk.StringVar(value="0")
        self._dd_rec_oy = tk.StringVar(value="0")
        self._dd_dxf_path = tk.StringVar()
        self._dd_contorno_idx = tk.StringVar()
        self._dd_contornos: List[Dict[str, Any]] = []
        self._dd_forma: Optional[Dict[str, Any]] = None
        self._dd_analisis: Optional[Dict[str, Any]] = None
        self._dd_espacios: Dict[str, Any] = {}
        # fila rectángulo
        fila_rec = ttk.Frame(contorno)
        for etiqueta, var in (("Ancho (m):", self._dd_rec_ancho),
                              ("Fondo (m):", self._dd_rec_fondo),
                              ("Origen X:", self._dd_rec_ox),
                              ("Y:", self._dd_rec_oy)):
            ttk.Label(fila_rec, text=etiqueta).pack(side="left")
            ttk.Entry(fila_rec, textvariable=var,
                      width=6).pack(side="left", padx=(2, 8))
        # fila DXF
        fila_dxf = ttk.Frame(contorno)
        ttk.Label(fila_dxf, text="DXF:").pack(side="left")
        ttk.Entry(fila_dxf, textvariable=self._dd_dxf_path).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(fila_dxf, text="Examinar…",
                   command=self._dd_dxf_examinar).pack(side="left")
        ttk.Label(fila_dxf, text="Contorno:").pack(
            side="left", padx=(6, 0))
        self._dd_contornos_combo = ttk.Combobox(
            fila_dxf, textvariable=self._dd_contorno_idx,
            state="readonly", width=24)
        self._dd_contornos_combo.pack(side="left", padx=4)
        self._dd_filas_origen = [fila_rec, fila_dxf]

        # 2 · el programa (tipo y uso social)
        programa = ttk.LabelFrame(marco,
                                  text="2 · El programa (tipo y uso "
                                       "social)")
        programa.pack(fill="x", pady=(6, 0))
        fila_modo = ttk.Frame(programa)
        fila_modo.pack(fill="x", padx=4, pady=2)
        self._dd_modo = tk.StringVar(value="servicio")
        ttk.Radiobutton(fila_modo, text="Servicio del catálogo",
                        value="servicio", variable=self._dd_modo,
                        command=self._dd_modo_cambio).pack(side="left")
        ttk.Radiobutton(fila_modo,
                        text="Edificación por usos del DNA",
                        value="edificacion", variable=self._dd_modo,
                        command=self._dd_modo_cambio).pack(
            side="left", padx=8)
        self._dd_panel_srv = ttk.Frame(programa)
        self._dd_panel_srv.pack(fill="x", padx=4)
        self._dd_servicio = tk.StringVar(
            value=f"{disponibles[0][0]} - {disponibles[0][1]}"
            if disponibles else "")
        self._dd_combo_srv = ttk.Combobox(
            self._dd_panel_srv, textvariable=self._dd_servicio,
            values=[f"{c} - {n}"
                    for c, n in disponibles],
            state="readonly", width=28)
        self._dd_combo_srv.pack(side="left")
        self._dd_combo_srv.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._dd_params_carga())
        # filtro por sector del catálogo universal (v3.36.0)
        fila_sector = ttk.Frame(self._dd_panel_srv)
        fila_sector.pack(side="left", padx=(8, 0))
        ttk.Label(fila_sector, text="Sector:").pack(side="left")
        self._dd_sector = tk.StringVar(value="Todos")
        self._dd_filtro = ttk.Combobox(
            fila_sector, textvariable=self._dd_sector,
            values=self._dd_valores_sector(), state="readonly",
            width=17)
        self._dd_filtro.pack(side="left", padx=(2, 0))
        self._dd_filtro.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._dd_aplica_filtro())
        self._dd_vars: List[Any] = []
        self._dd_params = ttk.Frame(self._dd_panel_srv)
        self._dd_params.pack(side="left", fill="x", expand=True, padx=8)
        self._dd_panel_ed = ttk.Frame(programa)
        try:
            usos_dna = sorted(self.ctx.dna_registry.types())
        except Exception:  # noqa: BLE001 — sin DNA cargado
            usos_dna = ["ROOM"]
        self._dd_uso = tk.StringVar(
            value=usos_dna[0] if usos_dna else "ROOM")
        ttk.Label(self._dd_panel_ed,
                  text="Uso:").pack(side="left")
        ttk.Combobox(self._dd_panel_ed, textvariable=self._dd_uso,
                     values=usos_dna, width=15).pack(side="left",
                                                     padx=(2, 6))
        ttk.Label(self._dd_panel_ed,
                  text="Cantidad:").pack(side="left")
        self._dd_cantidad = tk.StringVar(value="1")
        ttk.Entry(self._dd_panel_ed, textvariable=self._dd_cantidad,
                  width=4).pack(side="left", padx=(2, 6))
        ttk.Label(self._dd_panel_ed,
                  text="Área m2 (vacío = DNA):").pack(side="left")
        self._dd_area = tk.StringVar(value="")
        ttk.Entry(self._dd_panel_ed, textvariable=self._dd_area,
                  width=7).pack(side="left", padx=(2, 6))
        ttk.Button(self._dd_panel_ed, text="Añadir uso",
                   command=self._dd_uso_alta).pack(side="left")
        ttk.Button(self._dd_panel_ed, text="Quitar",
                   command=self._dd_uso_baja).pack(side="left", padx=4)
        self._dd_usos: List[Dict[str, Any]] = []
        self._dd_arbol = ttk.Treeview(
            programa, columns=("uso", "cantidad", "area"),
            show="headings", height=4)
        for col, texto, ancho in (("uso", "Uso (DNA)", 240),
                                  ("cantidad", "Cantidad", 80),
                                  ("area", "Área m2", 80)):
            self._dd_arbol.heading(col, text=texto)
            self._dd_arbol.column(col, width=ancho, anchor="w")
        self._dd_arbol.pack(fill="x", padx=4, pady=2)

        # 2-ter · locales del programa y ajuste dimensional (v3.41.0):
        #     el cambio de uso en una edificación existente NO admite
        #     el programa íntegro: se elige qué locales se aplican y
        #     cuánto pueden encogerse (mínimo/medio/estricto)
        from domain import desde_dibujo as _dd41
        self._dd_frame_prog = ttk.Frame(programa)
        self._dd_frame_prog.pack(fill="x", padx=4, pady=(2, 4))
        ttk.Button(self._dd_frame_prog,
                   text="Locales del programa...",
                   command=self._dd_locales_dialogo).pack(side="left")
        ttk.Label(self._dd_frame_prog,
                  text="Ajuste de dimensiones:").pack(side="left",
                                                      padx=(10, 2))
        self._dd_ajuste = tk.StringVar(
            value=_dd41.ETIQUETA_AJUSTE["minimo"])
        self._dd_ajuste_combo = ttk.Combobox(
            self._dd_frame_prog, textvariable=self._dd_ajuste,
            values=[_dd41.ETIQUETA_AJUSTE[k]
                    for k in _dd41.AJUSTE_NIVELES],
            state="readonly", width=36)
        self._dd_ajuste_combo.pack(side="left")
        self._dd_seleccion: Optional[Dict[str, bool]] = None
        self._dd_locales_vars: List[Any] = []

        # 2-bis · especificación rápida en una línea (v3.39.0, spec
        #     §42 sin IA): «3 dormitorios, 2 baños, garaje y 2 niveles»
        self._dd_frame_quick = ttk.Frame(programa)
        self._dd_frame_quick.pack(fill="x", padx=4, pady=(2, 4))
        ttk.Label(self._dd_frame_quick,
                  text="Especificación rápida:").pack(side="left")
        self._dd_quick = tk.StringVar()
        ttk.Entry(self._dd_frame_quick,
                  textvariable=self._dd_quick).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(self._dd_frame_quick,
                   text="Escribir en la tabla",
                   command=self._dd_quick_aplicar).pack(side="left")

        # 3 · ajuste y generación
        ajuste = ttk.LabelFrame(marco, text="3 · Ajuste y generación")
        ajuste.pack(fill="x", pady=(6, 0))
        opciones = ttk.Frame(ajuste)
        opciones.pack(fill="x", padx=4, pady=2)
        ttk.Label(opciones, text="Altura nivel (m):").pack(side="left")
        self._dd_altura = tk.StringVar(value="3.0")
        ttk.Entry(opciones, textvariable=self._dd_altura,
                  width=5).pack(side="left", padx=(2, 8))
        ttk.Label(opciones, text="Margen (m):").pack(side="left")
        self._dd_margen = tk.StringVar(value="0")
        ttk.Entry(opciones, textvariable=self._dd_margen,
                  width=5).pack(side="left", padx=(2, 8))
        ttk.Label(opciones, text="Edificio:").pack(side="left")
        self._dd_nombre = tk.StringVar(value="Edificio desde dibujo")
        ttk.Entry(opciones, textvariable=self._dd_nombre,
                  width=20).pack(side="left", padx=(2, 8))
        self._dd_muros = tk.BooleanVar(value=False)
        ttk.Checkbutton(opciones, variable=self._dd_muros,
                        text="Trazar muros").pack(side="left")
        self._dd_boceto = tk.BooleanVar(value=False)
        self._dd_chk_boceto = ttk.Checkbutton(
            opciones, variable=self._dd_boceto,
            text="El espacio de boceto se elimina al generar")
        self._dd_chk_boceto.pack(side="left", padx=6)
        acciones = ttk.Frame(ajuste)
        acciones.pack(fill="x", padx=4, pady=(2, 4))
        ttk.Button(acciones, text="Analizar contorno",
                   command=self._dd_analizar).pack(side="left")
        ttk.Button(acciones, text="¿Cabe en el área?",
                   command=self._dd_ajustar).pack(side="left", padx=6)
        ttk.Button(acciones, text="Explorar catálogo aquí",
                   command=self._dd_explorar).pack(side="left")
        ttk.Button(acciones, text="Comparar alternativas",
                   command=self._dd_alternativas).pack(side="left",
                                                       padx=6)
        ttk.Button(acciones, text="¿Por qué?",
                   command=self._dd_porque).pack(side="left")
        ttk.Button(acciones, text="Generar", style="Accent.TButton",
                   command=self._dd_aplicar).pack(side="left", padx=6)
        ttk.Button(acciones, text="Exportar BIM (IFC+DXF)",
                   command=self._dd_exportar_bim).pack(side="left")

        # 3-bis · alternativas y elección (v3.39.0, spec §25/§26)
        self._dd_frame_alt = ttk.Frame(ajuste)
        self._dd_frame_alt.pack(fill="x", padx=4)
        ttk.Label(self._dd_frame_alt,
                  text="Alternativas:").pack(side="left")
        self._dd_alt_n = tk.StringVar(value="3")
        ttk.Combobox(self._dd_frame_alt, textvariable=self._dd_alt_n,
                     values=("1", "3", "5"), state="readonly",
                     width=3).pack(side="left", padx=(2, 10))
        ttk.Label(self._dd_frame_alt,
                  text="Elegida:").pack(side="left")
        self._dd_alt_elegir = ttk.Combobox(
            self._dd_frame_alt, state="readonly", width=32,
            values=())
        self._dd_alt_elegir.pack(side="left", padx=(2, 0))
        self._dd_alt_elegir.bind("<<ComboboxSelected>>",
                                 self._dd_alt_elegida)
        self._dd_alternativas_lista: List[Dict[str, Any]] = []

        # 3-ter · opciones expertas (v3.39.0): espesores, patio y
        #     niveles deseados (spec §10 experto + §A11 patios)
        self._dd_frame_experto = ttk.LabelFrame(
            ajuste, text="Opciones expertas")
        self._dd_frame_experto.pack(fill="x", padx=4, pady=(4, 0))
        fila_exp1 = ttk.Frame(self._dd_frame_experto)
        fila_exp1.pack(fill="x", padx=4, pady=2)
        ttk.Label(fila_exp1,
                  text="Espesor contorno (m):").pack(side="left")
        self._dd_esp_cont = tk.StringVar(value="0.20")
        ttk.Entry(fila_exp1, textvariable=self._dd_esp_cont,
                  width=6).pack(side="left", padx=(2, 10))
        ttk.Label(fila_exp1,
                  text="Espesor locales (m):").pack(side="left")
        self._dd_esp_loc = tk.StringVar(value="0.15")
        ttk.Entry(fila_exp1, textvariable=self._dd_esp_loc,
                  width=6).pack(side="left", padx=(2, 10))
        ttk.Label(fila_exp1,
                  text="Niveles deseados (vacío = auto):").pack(
            side="left")
        self._dd_niveles_des = tk.StringVar(value="")
        ttk.Entry(fila_exp1, textvariable=self._dd_niveles_des,
                  width=4).pack(side="left", padx=(2, 0))
        fila_exp2 = ttk.Frame(self._dd_frame_experto)
        fila_exp2.pack(fill="x", padx=4, pady=2)
        self._dd_patio = tk.BooleanVar(value=False)
        ttk.Checkbutton(fila_exp2, variable=self._dd_patio,
                        text="Reservar patio exterior").pack(
            side="left")
        ttk.Label(fila_exp2,
                  text="Ancho del patio (m):").pack(side="left",
                                                    padx=(8, 0))
        self._dd_patio_ancho = tk.StringVar(value="3.0")
        ttk.Entry(fila_exp2, textvariable=self._dd_patio_ancho,
                  width=5).pack(side="left", padx=(2, 0))
        self._dd_encaje = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            fila_exp2, variable=self._dd_encaje,
            text="Encajar estrictamente en el polígono (v3.40)").pack(
            side="left", padx=(12, 0))
        fila_exp3 = ttk.Frame(self._dd_frame_experto)
        fila_exp3.pack(fill="x", padx=4, pady=2)
        self._dd_chaflanes = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            fila_exp3, variable=self._dd_chaflanes,
            text="Chaflanes a 45° hacia la sala (v3.43)").pack(
            side="left")
        self._dd_mobiliario = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            fila_exp3, variable=self._dd_mobiliario,
            text="Amueblar locales (v3.43)").pack(side="left",
                                                   padx=(12, 0))
        fila_exp4 = ttk.Frame(self._dd_frame_experto)
        fila_exp4.pack(fill="x", padx=4, pady=2)
        self._dd_chaflan_propio = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            fila_exp4, variable=self._dd_chaflan_propio,
            text="Chaflán propio de fachada (v3.44)").pack(
            side="left")
        ttk.Label(fila_exp4,
                  text="Distribuidora hasta (m2, vacío = 60):").pack(
            side="left", padx=(12, 0))
        self._dd_dist_max = tk.StringVar(value="")
        ttk.Entry(fila_exp4, textvariable=self._dd_dist_max,
                  width=5).pack(side="left", padx=(2, 10))
        ttk.Button(fila_exp4, text="Elevaciones (v3.44)",
                   command=self._dd_fachadas).pack(side="left",
                                                   padx=(0, 6))
        ttk.Button(fila_exp4, text="Planta radial (v3.44)",
                   command=self._dd_radial).pack(side="left",
                                                 padx=(0, 6))
        ttk.Button(fila_exp4, text="Torre en Y (v3.45)",
                   command=self._dd_torre_y).pack(side="left",
                                                  padx=(0, 6))
        ttk.Button(fila_exp4, text="Hospital en X (v3.47)",
                   command=self._dd_hospital_x).pack(side="left")

        # 3-cuarto · historial de configuraciones (v3.39.0, spec
        #     §29/§30): fotografías guardadas con el proyecto
        self._dd_frame_conf = ttk.Frame(ajuste)
        self._dd_frame_conf.pack(fill="x", padx=4, pady=(4, 0))
        ttk.Label(self._dd_frame_conf,
                  text="Configuración:").pack(side="left")
        self._dd_conf_combo = ttk.Combobox(
            self._dd_frame_conf, state="readonly", width=34,
            values=())
        self._dd_conf_combo.pack(side="left", padx=4)
        ttk.Button(self._dd_frame_conf, text="Restaurar",
                   command=self._dd_config_restaurar).pack(side="left")
        ttk.Button(self._dd_frame_conf, text="Guardar",
                   command=self._dd_config_guardar).pack(side="left",
                                                        padx=(6, 0))

        texto_marco = ttk.Frame(marco)
        texto_marco.pack(fill="both", expand=True, pady=(6, 0))
        self._dd_texto = tk.Text(texto_marco, height=13, wrap="word",
                                 width=88)
        barra = ttk.Scrollbar(texto_marco, orient="vertical",
                              command=self._dd_texto.yview)
        self._dd_texto.configure(yscrollcommand=barra.set)
        self._dd_texto.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        self._dd_refresca_espacios()
        self._dd_origen_cambio()
        self._dd_params_carga()
        self._dd_modo_cambio()
        self._dd_nivel_cambio()
        self._dd_conf_refresca()
        self._say("Asistente «Desde dibujo» abierto.",
                  "Elija el contorno (espacio dibujado, rectángulo o "
                  "DXF), defina el programa y genere la edificación "
                  "o el servicio")

    def _dd_float(self, var: Any, defecto: float) -> float:
        """Número tolerante (coma decimal, basura -> defecto)."""
        try:
            return float(str(var.get()).strip().replace(",", "."))
        except (TypeError, ValueError, tk.TclError):
            return defecto

    def _dd_origen_cambio(self) -> None:
        """Muestra solo la fila del origen de contorno elegido."""
        origen = self._dd_origen.get()
        indice = {"espacio": -1, "rectangulo": 0, "dxf": 1}.get(origen, -1)
        for i, fila in enumerate(self._dd_filas_origen):
            if i == indice:
                fila.pack(fill="x", padx=4, pady=2)
            else:
                fila.pack_forget()
        estado = "normal" if origen == "espacio" else "disabled"
        self._dd_chk_boceto.configure(state=estado)
        if origen != "espacio":
            self._dd_boceto.set(False)

    def _dd_modo_cambio(self) -> None:
        """Servicio del catálogo o edificación por usos del DNA."""
        if self._dd_modo.get() == "edificacion":
            self._dd_panel_srv.pack_forget()
            self._dd_panel_ed.pack(fill="x", padx=4)
        else:
            self._dd_panel_ed.pack_forget()
            self._dd_panel_srv.pack(fill="x", padx=4)

    def _dd_nivel_cambio(self) -> None:
        """Básico / Profesional / Experto (v3.39.0, spec §10): cada
        modo muestra solo los controles que toca. Básico = lo
        esencial; Profesional añade la línea rápida, las alternativas
        y el historial; Experto añade espesores, patio y niveles
        deseados."""
        nivel = self._dd_nivel.get()
        if nivel == "basico":
            self._dd_frame_quick.pack_forget()
            self._dd_frame_alt.pack_forget()
            self._dd_frame_conf.pack_forget()
            self._dd_frame_experto.pack_forget()
        elif nivel == "experto":
            self._dd_frame_quick.pack(fill="x", padx=4, pady=(2, 4))
            self._dd_frame_alt.pack(fill="x", padx=4)
            self._dd_frame_experto.pack(fill="x", padx=4, pady=(4, 0))
            self._dd_frame_conf.pack(fill="x", padx=4, pady=(4, 0))
        else:  # profesional (por defecto)
            self._dd_frame_quick.pack(fill="x", padx=4, pady=(2, 4))
            self._dd_frame_alt.pack(fill="x", padx=4)
            self._dd_frame_conf.pack(fill="x", padx=4, pady=(4, 0))
            self._dd_frame_experto.pack_forget()

    def _dd_niveles_pedido(self) -> Optional[int]:
        """Los niveles deseados tecleados (vacío o basura -> None)."""
        bruto = str(self._dd_niveles_des.get() or "").strip()
        if not bruto:
            return None
        try:
            return max(1, int(float(bruto.replace(",", "."))))
        except (TypeError, ValueError):
            return None

    def _dd_params_carga(self) -> None:
        """Parámetros dinámicos del servicio elegido (v3.33.0)."""
        from domain.servicios_specs import servicio
        for hijo in self._dd_params.winfo_children():
            hijo.destroy()
        self._dd_vars = []
        codigo = (self._dd_servicio.get() or "").split(" - ")[0].strip()
        if not codigo:
            return
        try:
            item = servicio(codigo)
        except Exception:  # noqa: BLE001 — error amable al aplicar
            return
        for indice, p in enumerate(item.parametros):
            fila = ttk.Frame(self._dd_params)
            fila.grid(row=indice // 4, column=indice % 4,
                      sticky="w", padx=(0, 10))
            ttk.Label(fila, text=p.nombre + ":").pack(side="left")
            if p.tipo == "bool":
                var = tk.BooleanVar(value=bool(p.defecto))
                ttk.Checkbutton(fila, variable=var).pack(
                    side="left", padx=2)
            else:
                var = tk.StringVar(value=str(p.defecto))
                ttk.Entry(fila, textvariable=var,
                          width=6).pack(side="left", padx=2)
            self._dd_vars.append((p, var))

    def _dd_valores_sector(self) -> List[str]:
        """Etiquetas del filtro de sector («Todos» primero)."""
        from domain.servicios_specs import servicios_por_sector
        try:
            return ["Todos"] + [et for et, _items
                                in servicios_por_sector()]
        except Exception:  # noqa: BLE001 — catálogo ausente
            return ["Todos"]

    def _dd_aplica_filtro(self) -> None:
        """Repopular el combobox de servicios según el sector."""
        from domain.servicios_specs import servicios_por_sector
        sector = self._dd_sector.get()
        try:
            grupos = servicios_por_sector()
        except Exception:  # noqa: BLE001 — catálogo ausente
            grupos = []
        if sector in ("", "Todos"):
            items = [(c, n) for _et, lista in grupos
                     for c, n in lista]
        else:
            items = next((lista for et, lista in grupos
                          if et == sector), [])
        valores = [f"{c} - {n}" for c, n in items]
        self._dd_combo_srv.configure(values=valores)
        if valores:
            self._dd_combo_srv.current(0)
            self._dd_params_carga()
        else:
            self._dd_servicio.set("")

    def _dd_explorar(self) -> None:
        """Prueba el contorno contra TODO el catálogo (v3.36.0)."""
        from domain import desde_dibujo as dd
        try:
            poligono = self._dd_poligono()
            resultados = dd.explorar_catalogo(
                poligono,
                altura_nivel_m=self._dd_float(self._dd_altura, 3.0),
                margen_m=self._dd_float(self._dd_margen, 0.0))
            try:
                forma = dd.inferir(poligono)
                area = float(forma["area_m2"])
            except Exception:  # noqa: BLE001 — solo informativo
                area = 0.0
            texto = dd.texto_exploracion(resultados, area)
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        self._dd_texto_set(texto)
        self._say("Catálogo explorado en el contorno.",
                  "Los servicios que caben aparecen primero; elija uno "
                  "y pulse Generar")

    def _dd_refresca_espacios(self) -> None:
        """Espacios del nivel activo como candidatos a contorno (el
        último dibujado queda seleccionado)."""
        from domain import desde_dibujo as dd
        valores: List[str] = []
        self._dd_espacios = {}
        try:
            nombre_nivel = self._nivel_de_dibujo()
            nivel = next((lv for lv in self.ctx.architecture.list(
                "LEVEL", self.ctx.project.id)
                if lv.name == nombre_nivel), None)
            for s in self.ctx.architecture.list("SPACE",
                                                self.ctx.project.id):
                if nivel is not None \
                        and getattr(s, "level_id", "") != nivel.id:
                    continue
                try:
                    area = dd.inferir(s.boundary)["area_m2"]
                except Exception:  # noqa: BLE001 — geometría rota
                    area = 0.0
                etiqueta = f"{s.name} ({area:.2f} m2)"
                self._dd_espacios[etiqueta] = s
                valores.append(etiqueta)
        except Exception:  # noqa: BLE001 — sin proyecto cargado
            valores = []
        self._dd_espacios_combo.configure(values=valores)
        if valores:
            self._dd_espacios_combo.current(len(valores) - 1)

    def _dd_dxf_examinar(self) -> None:
        """Elige el DXF y enumera sus polilíneas cerradas."""
        from domain import desde_dibujo as dd
        path = filedialog.askopenfilename(
            title="Elija el DXF con el contorno del área",
            filetypes=[("DXF", "*.dxf"), ("Todos", "*.*")],
            parent=self._dd_dialog)
        if not path:
            return
        self._dd_dxf_path.set(path)
        try:
            self._dd_contornos = dd.contornos_dxf(path)
        except Exception as exc:  # noqa: BLE001 — error amable
            messagebox.showerror(
                "Desde dibujo", str(getattr(exc, "message", exc)),
                parent=self._dd_dialog)
            self._dd_contornos = []
        self._dd_refresca_contornos()

    def _dd_refresca_contornos(self) -> None:
        """Vuelca ``_dd_contornos`` en el combobox (gancho de pruebas)."""
        self._dd_contornos_combo.configure(
            values=[c["nombre"] + (" · cerrada automáticamente"
                                   if c.get("cerrada_auto") else "")
                    for c in self._dd_contornos])
        if self._dd_contornos:
            self._dd_contornos_combo.current(0)

    def _dd_poligono(self) -> List[Any]:
        """El contorno elegido como lista de vértices (lanza amable)."""
        from core.errors import DomainError
        origen = self._dd_origen.get()
        if origen == "rectangulo":
            ancho = self._dd_float(self._dd_rec_ancho, 0.0)
            fondo = self._dd_float(self._dd_rec_fondo, 0.0)
            ox = self._dd_float(self._dd_rec_ox, 0.0)
            oy = self._dd_float(self._dd_rec_oy, 0.0)
            if ancho <= 0 or fondo <= 0:
                raise DomainError(
                    message="El rectángulo necesita ancho y fondo "
                            "positivos",
                    code="ARQ-DDI-001",
                    suggested_action="Revise las medidas del "
                                     "rectángulo.")
            return [(ox, oy), (ox + ancho, oy),
                    (ox + ancho, oy + fondo), (ox, oy + fondo)]
        if origen == "dxf":
            if not self._dd_contornos:
                raise DomainError(
                    message="No hay polilíneas cerradas en el DXF: "
                            "examine el archivo de nuevo",
                    code="ARQ-DDI-004",
                    suggested_action="El contorno debe ser una "
                                     "polilínea CERRADA del área.")
            indice = max(0, self._dd_contornos_combo.current())
            return list(self._dd_contornos[indice]["puntos"])
        espacio = self._dd_espacios.get(self._dd_espacio.get())
        if espacio is None:
            raise DomainError(
                message="Elija el espacio que delimita el área (o "
                        "dibújelo con el panel de Dibujo)",
                code="ARQ-DDI-001",
                suggested_action="El asistente puede usar cualquier "
                                 "espacio del nivel como contorno.")
        return [tuple(p) for p in (espacio.boundary or [])]

    def _dd_programa(self) -> Dict[str, Any]:
        """El programa del modo activo (servicio o edificación)."""
        from domain import desde_dibujo as dd
        from domain import servicios_engine as eng
        if self._dd_modo.get() == "edificacion":
            return dd.programa_edificacion(list(self._dd_usos))
        codigo = (self._dd_servicio.get() or "").split(" - ")[0].strip()
        params: Dict[str, Any] = {}
        for p, var in self._dd_vars:
            if p.tipo == "bool":
                params[p.codigo] = bool(var.get())
            else:
                params[p.codigo] = self._dd_float(
                    var, float(p.defecto or 0))
        return eng.programa_servicio(codigo, params)

    def _dd_uso_alta(self) -> None:
        """Añade un uso del DNA a la tabla de la edificación."""
        tipo = (self._dd_uso.get() or "").strip().upper()
        if not tipo:
            return
        area = self._dd_float(self._dd_area, 0.0)
        self._dd_usos.append({"space_type": tipo,
                              "cantidad": max(
                                  1, int(self._dd_float(
                                      self._dd_cantidad, 1.0))),
                              "area_m2": area if area > 0 else None})
        self._dd_arbol.insert("", "end", values=(
            tipo, self._dd_usos[-1]["cantidad"],
            f"{area:.2f}" if area > 0 else "(DNA)"))

    def _dd_uso_baja(self) -> None:
        """Quita el uso seleccionado de la tabla."""
        seleccion = self._dd_arbol.selection()
        if not seleccion:
            return
        indice = self._dd_arbol.index(seleccion[0])
        self._dd_arbol.delete(seleccion[0])
        if 0 <= indice < len(self._dd_usos):
            self._dd_usos.pop(indice)

    def _dd_ajuste_actual(self) -> str:
        """El nivel de ajuste dimensional elegido (v3.41.0)."""
        from domain import desde_dibujo as dd
        etiqueta = self._dd_ajuste.get()
        for clave, valor in dd.ETIQUETA_AJUSTE.items():
            if valor == etiqueta:
                return clave
        return "minimo"

    def _dd_seleccion_actual(self) -> Optional[List[str]]:
        """Códigos conservados por la selección de locales (v3.41.0);
        None = aplicarlos todos (comportamiento histórico)."""
        sel = getattr(self, "_dd_seleccion", None)
        if sel is None:
            return None
        return [c for c, v in sel.items() if v]

    def _dd_locales_aplicar(self) -> None:
        """Vuelca las casillas del diálogo de locales en la selección
        (gancho de pruebas y de los botones Todos/Ninguno)."""
        self._dd_seleccion = {codigo: bool(var.get())
                              for codigo, var in self._dd_locales_vars}

    def _dd_locales_dialogo(self) -> None:
        """v3.41.0: elige qué locales del programa se aplican en este
        proyecto. La realidad del cambio de uso en Cuba: edificaciones
        existentes donde no todo el programa cabe ni todo hace falta;
        los locales desmarcados se excluyen con aviso documentado."""
        from domain import desde_dibujo as dd
        try:
            programa = self._dd_programa()
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        dueño = self._dd_dialog
        dialog = tk.Toplevel(dueño)
        dialog.title("Locales del programa (selección)")
        dialog.transient(dueño)
        dialog.configure(background=theme.COL_BG)
        marco = ttk.Frame(dialog)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="Marque los locales que se aplican en "
                               "este proyecto; los desmarcados se "
                               "excluyen del programa:",
                  wraplength=440, justify="left").pack(
            fill="x", padx=10, pady=(8, 4))
        lienzo_frame = ttk.Frame(marco)
        lienzo_frame.pack(fill="both", expand=True, padx=10)
        lienzo = tk.Canvas(lienzo_frame, height=360, highlightthickness=0,
                           background=theme.COL_BG)
        barra = ttk.Scrollbar(lienzo_frame, orient="vertical",
                              command=lienzo.yview)
        interior = ttk.Frame(lienzo)
        interior.bind("<Configure>",
                      lambda _e: lienzo.configure(
                          scrollregion=lienzo.bbox("all")))
        ventana = lienzo.create_window((0, 0), window=interior,
                                       anchor="nw")
        lienzo.configure(yscrollcommand=barra.set)
        lienzo.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        try:
            lienzo.itemconfigure(ventana, width=430)
        except Exception:  # noqa: BLE001 — cosmético
            pass
        grupos: Dict[str, List[Dict[str, Any]]] = {}
        for r in programa.get("renglones", []):
            grupos.setdefault(str(r.get("grupo") or "General"),
                              []).append(r)
        self._dd_locales_vars = []
        sel = self._dd_seleccion
        for nombre_grupo in sorted(grupos):
            ttk.Label(interior, text=nombre_grupo,
                      style="Hint.TLabel").pack(
                anchor="w", padx=4, pady=(6, 1))
            agregados: Dict[str, Dict[str, Any]] = {}
            orden: List[str] = []
            for r in grupos[nombre_grupo]:
                codigo = str(r.get("codigo", ""))
                if codigo not in agregados:
                    agregados[codigo] = {"nombre": str(r.get("nombre",
                                                              codigo)),
                                         "copias": 0, "area": 0.0}
                    orden.append(codigo)
                agregados[codigo]["copias"] += 1
                agregados[codigo]["area"] += float(r.get("area_m2",
                                                         0.0))
            for codigo in orden:
                a = agregados[codigo]
                texto = (f"{codigo} · {a['nombre']}"
                         + (f" x{a['copias']}" if a["copias"] > 1
                            else "")
                         + f" — {a['area']:.2f} m2")
                estado = True if sel is None \
                    else bool(sel.get(codigo, False))
                var = tk.BooleanVar(value=estado)
                ttk.Checkbutton(interior, text=texto,
                                variable=var).pack(anchor="w", padx=20)
                self._dd_locales_vars.append((codigo, var))
        if not self._dd_locales_vars:
            ttk.Label(interior, text="El programa no tiene locales.") \
                .pack(anchor="w", padx=8, pady=8)
        botones = ttk.Frame(marco)
        botones.pack(fill="x", padx=10, pady=(6, 10))

        def todos(valor: bool) -> None:
            for _c, var in self._dd_locales_vars:
                var.set(valor)
            self._dd_locales_aplicar()

        ttk.Button(botones, text="Todos",
                   command=lambda: todos(True)).pack(side="left")
        ttk.Button(botones, text="Ninguno",
                   command=lambda: todos(False)).pack(side="left",
                                                      padx=6)
        ttk.Button(botones, text="Aplicar",
                   command=self._dd_locales_aplicar).pack(side="left",
                                                          padx=6)
        ttk.Button(botones, text="Cerrar",
                   command=dialog.destroy).pack(side="right")
        dialog._dd_locales_vars = self._dd_locales_vars
        self._dd_locales_dialog = dialog
        self._say("Selección de locales abierta.",
                  "Los locales desmarcados NO se aplican en este "
                  "proyecto: la exclusión queda documentada en los "
                  "avisos del informe")

    def _dd_error(self, exc: Exception) -> None:
        """Cuadro de error amable con la sugerencia si la hay."""
        accion = getattr(exc, "suggested_action", "")
        messagebox.showerror(
            "Desde dibujo",
            str(getattr(exc, "message", exc))
            + (f"\n\nSugerencia: {accion}" if accion else ""),
            parent=self._dd_dialog)

    def _dd_texto_set(self, texto: str) -> None:
        self._dd_texto.delete("1.0", "end")
        self._dd_texto.insert("1.0", texto)

    def _dd_analizar(self) -> None:
        """Infiere forma y medidas del contorno y LO VALIDA
        (v3.39.0, spec §11/§24): autointersecciones, apertura,
        dimensiones imposibles... con severidades."""
        from domain import desde_dibujo as dd
        try:
            poligono = self._dd_poligono()
            self._dd_forma = dd.inferir(poligono)
            self._dd_validacion = dd.validar_contorno(poligono)
            texto = dd.texto_inferencia(self._dd_forma) + "\n\n" + \
                dd.texto_validacion_contorno(self._dd_validacion)
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        self._dd_texto_set(texto)

    def _dd_ajustar(self) -> None:
        """¿Los locales del programa entran en el área dibujada?
        Desde v3.39.0 precedido por el checklist previa (spec §24)
        y con las opciones expertas (patio, niveles deseados)."""
        from domain import desde_dibujo as dd
        from domain import servicios_engine as eng
        try:
            programa = self._dd_programa()
            pedido = self._dd_niveles_pedido()
            poligono = self._dd_poligono()
            self._dd_analisis = dd.ajustar(
                programa, poligono,
                altura_nivel_m=self._dd_float(self._dd_altura, 3.0),
                margen_m=self._dd_float(self._dd_margen, 0.0),
                patio=bool(self._dd_patio.get()),
                patio_ancho_m=self._dd_float(self._dd_patio_ancho,
                                             3.0),
                encaje_estricto=bool(self._dd_encaje.get()),
                seleccion=self._dd_seleccion_actual(),
                ajuste=self._dd_ajuste_actual(),
                niveles_deseados=pedido,
                chaflanes=bool(self._dd_chaflanes.get()),
                distribuidora_max_m2=(
                    self._dd_float(self._dd_dist_max, 0.0) or None),
                chaflan_propio=(True
                                if self._dd_chaflan_propio.get()
                                else None))
            self._dd_validacion = dd.validar_contorno(poligono)
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        analisis = self._dd_analisis
        texto = dd.texto_inferencia(analisis["forma"]) + "\n\n" + \
            dd.texto_checklist(dd.checklist_previa(
                self._dd_validacion, analisis, pedido,
                bool(self._dd_patio.get()))) + "\n\n" + \
            dd.texto_ajuste(analisis)
        if self._dd_modo.get() == "servicio" \
                and analisis["programa"].get("validacion"):
            texto += "\n\n" + eng.texto_validacion(
                analisis["programa"]["validacion"])
        self._dd_texto_set(texto)

    def _dd_alternativas(self) -> None:
        """Compara 1/3/5 alternativas del programa en el contorno
        (v3.39.0, spec §25/§26) y deja la mejor elegida."""
        from domain import desde_dibujo as dd
        try:
            cantidad = int(self._dd_alt_n.get() or "1")
            programa = self._dd_programa()
            lista = dd.alternativas(
                programa, self._dd_poligono(), cantidad=cantidad,
                altura_nivel_m=self._dd_float(self._dd_altura, 3.0),
                margen_m=self._dd_float(self._dd_margen, 0.0),
                patio=bool(self._dd_patio.get()),
                patio_ancho_m=self._dd_float(self._dd_patio_ancho,
                                             3.0),
                seleccion=self._dd_seleccion_actual(),
                ajuste=self._dd_ajuste_actual(),
                niveles_deseados=self._dd_niveles_pedido(),
                chaflanes=bool(self._dd_chaflanes.get()),
                distribuidora_max_m2=(
                    self._dd_float(self._dd_dist_max, 0.0) or None),
                chaflan_propio=(True
                                if self._dd_chaflan_propio.get()
                                else None))
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        self._dd_alternativas_lista = lista
        self._dd_alt_elegir.configure(
            values=[f"{r['etiqueta']} - {r['estrategia']}"
                    for r in lista])
        if lista:
            self._dd_alt_elegir.current(0)
            self._dd_alt_elegida()
        self._say("Alternativas comparadas.",
                  "La A es la mejor por los pesos del diseño; elija "
                  "otra en «Elegida» si prefiere su reparto")

    def _dd_alt_elegida(self, _evento: Any = None) -> None:
        """La alternativa elegida pasa a ser el análisis a generar."""
        from domain import desde_dibujo as dd
        lista = getattr(self, "_dd_alternativas_lista", [])
        if not lista:
            return
        try:
            indice = max(0, self._dd_alt_elegir.current())
        except Exception:  # noqa: BLE001 — sin selección aún
            indice = 0
        indice = min(indice, len(lista) - 1)
        fila = lista[indice]
        if fila.get("analisis") is None:
            self._dd_texto_set(dd.texto_alternativas(lista))
            return
        self._dd_analisis = fila["analisis"]
        self._dd_texto_set(
            dd.texto_inferencia(self._dd_analisis["forma"])
            + "\n\n" + dd.texto_ajuste(self._dd_analisis)
            + "\n\n" + dd.texto_alternativas(lista))

    def _dd_porque(self) -> None:
        """«¿Por qué?» (v3.39.0, spec §32/§33): las reglas aplicadas,
        en claro y sin IA."""
        from domain import desde_dibujo as dd
        if self._dd_analisis is None:
            self._dd_ajustar()
            if self._dd_analisis is None:
                return
        self._dd_texto_set(dd.texto_decisiones(self._dd_analisis))
        self._say("Decisiones del asistente.",
                  "Cada regla aplicada queda registrada: niveles, "
                  "escalera, patio y la banda de cada local")

    def _dd_fachadas(self) -> None:
        """v3.44.0: ELEVACIONES paramétricas del contorno ajustado
        (4 pieles; DXF R12 + PNG). Pide la piel y guarda donde elija
        el usuario; con el análisis sin ajustar, ajusta primero."""
        from domain import elevaciones as fc
        from domain import desde_dibujo as dd
        if getattr(self, "_dd_analisis", None) is None:
            self._dd_ajustar()
            if getattr(self, "_dd_analisis", None) is None:
                return
        vertices = self._dd_analisis["forma"]["vertices"]
        piel = simpledialog.askstring(
            "Fachadas v3.45",
            "Piel de la fachada (panos, ventana_corrida, brise, "
            "perforada, hexagonal, diagrid, celosia, gradiente, "
            "fins, cortina, bandas, parametrica):",
            initialvalue="panos", parent=self)
        if not piel:
            return
        try:
            res = fc.elevacion(
                vertices,
                n_pisos=int(self._dd_analisis.get("niveles", 1)),
                altura_piso_m=self._dd_float(self._dd_altura, 3.0),
                piel=str(piel).strip().lower())
            destino = filedialog.asksaveasfilename(
                title="Guardar elevaciones (DXF)",
                defaultextension=".dxf",
                initialfile="fachadas.dxf",
                filetypes=[("DXF", "*.dxf"), ("Todos", "*.*")],
                parent=self)
            if not destino:
                return
            fc.exportar_elevacion_dxf(res, destino)
            png = str(destino)[:-4] + ".png" \
                if str(destino).lower().endswith(".dxf") \
                else str(destino) + ".png"
            fc.render_elevacion_png(res, png)
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        self._dd_texto_set(
            "FACHADAS PARAMETRICAS (v3.44)\n"
            f"piel: {res['piel']} · plantas: {res['n_pisos']} "
            f"· altura total: {res['altura_total_m']:.1f} m\n"
            "lados: " + ", ".join(
                f"{L:.1f} m" for L in res["lado_longitud_m"])
            + f"\nDXF: {destino}\nPNG: {png}\n"
            "Capas DXF: FACH_MURO, FACH_VENTANA, FACH_LAMAS, "
            "FACH_PERFORACION, FACH_TEXTO")
        self._say("Elevaciones generadas.",
                  "El DXF lleva las fachadas lado a lado con capas "
                  "por elemento; el PNG es la vista rápida")

    def _dd_radial(self) -> None:
        """v3.44.0: PLANTA RADIAL del programa actual: sectores
        alrededor de un núcleo circular con corredor anular; deja el
        análisis listo para «Generar» (aplicar_plan lo aplica)."""
        from domain import radial as rd
        from domain import desde_dibujo as dd
        try:
            programa = self._dd_programa()
            r_ext = simpledialog.askstring(
                "Planta radial v3.44", "Radio exterior (m):",
                initialvalue="12.0", parent=self)
            if not r_ext:
                return
            sectores = simpledialog.askstring(
                "Planta radial v3.44", "Número de sectores (3-36):",
                initialvalue="8", parent=self)
            if sectores is None:
                return
            corredor = simpledialog.askstring(
                "Planta radial v3.44", "Corredor anular (m, 0 = sin "
                "corredor):", initialvalue="1.5", parent=self)
            if corredor is None:
                return
            nucleo = simpledialog.askstring(
                "Planta radial v3.44",
                "Radio del núcleo (m, 0 = sin núcleo):",
                initialvalue="0.0", parent=self)
            if nucleo is None:
                return
            centro = (0.0, 0.0)
            try:
                poly = self._dd_poligono()
                if poly:
                    centro = (sum(float(p[0]) for p in poly)
                              / len(poly),
                              sum(float(p[1]) for p in poly)
                              / len(poly))
            except Exception:  # noqa: BLE001 — sin contorno: origen
                centro = (0.0, 0.0)
            analisis = rd.plan_radial(
                programa, centro=(centro[0], centro[1]),
                radio_ext=float(str(r_ext).strip().replace(
                    ",", ".")),
                sectores=int(str(sectores).strip() or 8),
                corredor_m=float(str(corredor).strip().replace(
                    ",", ".") or 0.0),
                radio_nucleo=float(str(nucleo).strip().replace(
                    ",", ".") or 0.0),
                altura_nivel_m=self._dd_float(self._dd_altura, 3.0))
            self._dd_analisis = analisis
            self._dd_validacion = {"bloquea": False,
                                   "errores": [], "avisos": []}
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        self._dd_texto_set(
            dd.texto_inferencia(self._dd_analisis["forma"])
            + "\n\n" + dd.texto_ajuste(self._dd_analisis))
        self._say("Planta radial lista.",
                  "Pulse Generar para crear el edificio del anillo; "
                  "el mobiliario automático se omite en la "
                  "geometría curva")

    def _dd_torre_y(self) -> None:
        """v3.45.0: TORRE EN Y REAL del programa actual: núcleo
        circular con el vestíbulo, N alas radiantes con corredor y
        locales a ambos lados; deja el análisis listo para
        «Generar» (aplicar_plan lo aplica con los corredores por
        ala)."""
        from domain import radial as rd
        from domain import desde_dibujo as dd
        try:
            programa = self._dd_programa()
            nucleo = simpledialog.askstring(
                "Torre en Y v3.45", "Radio del núcleo (m):",
                initialvalue="7.5", parent=self)
            if not nucleo:
                return
            alas = simpledialog.askstring(
                "Torre en Y v3.45",
                "Número de alas (3 = Y, 2 = barra, 4 = X):",
                initialvalue="3", parent=self)
            if alas is None:
                return
            largo = simpledialog.askstring(
                "Torre en Y v3.45", "Largo de cada ala (m):",
                initialvalue="16.0", parent=self)
            if largo is None:
                return
            ancho = simpledialog.askstring(
                "Torre en Y v3.45", "Ancho de cada ala (m):",
                initialvalue="11.0", parent=self)
            if ancho is None:
                return
            corredor = simpledialog.askstring(
                "Torre en Y v3.45", "Corredor del ala (m, 0 = sin "
                "corredor):", initialvalue="1.6", parent=self)
            if corredor is None:
                return
            cabecera = simpledialog.askstring(
                "Torre en Y v3.45",
                "Cabecera transversal al fondo del ala (m, "
                "0 = sin cabecera):", initialvalue="0.0",
                parent=self)
            if cabecera is None:
                return
            largos = simpledialog.askstring(
                "Torre en Y v3.45",
                "Largos de alas en m separados por coma "
                "(vacío = todas iguales):", initialvalue="",
                parent=self)
            if largos is None:
                return
            niveles = simpledialog.askstring(
                "Torre en Y v3.45",
                "Niveles de planta tipo (1-20, vacío = 1):",
                initialvalue="1", parent=self)
            if niveles is None:
                return
            largos_alas = None
            texto_largos = str(largos).strip()
            if texto_largos:
                largos_alas = [float(x.strip().replace(",", "."))
                               for x in texto_largos.split(",")
                               if x.strip()]
            centro = (0.0, 0.0)
            try:
                poly = self._dd_poligono()
                if poly:
                    centro = (sum(float(p[0]) for p in poly)
                              / len(poly),
                              sum(float(p[1]) for p in poly)
                              / len(poly))
            except Exception:  # noqa: BLE001 — sin contorno: origen
                centro = (0.0, 0.0)
            analisis = rd.plan_y(
                programa, centro=(centro[0], centro[1]),
                radio_nucleo=float(str(nucleo).strip().replace(
                    ",", ".")),
                n_alas=int(str(alas).strip() or 3),
                largo_ala=float(str(largo).strip().replace(
                    ",", ".")),
                ancho_ala=float(str(ancho).strip().replace(
                    ",", ".")),
                corredor_m=float(str(corredor).strip().replace(
                    ",", ".") or 0.0),
                cabecera_m=float(str(cabecera).strip().replace(
                    ",", ".") or 0.0),
                altura_nivel_m=self._dd_float(self._dd_altura, 3.0),
                largos_alas=largos_alas,
                niveles=int(str(niveles).strip() or 1))
            self._dd_analisis = analisis
            self._dd_validacion = {"bloquea": False,
                                   "errores": [], "avisos": []}
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        self._dd_texto_set(
            dd.texto_inferencia(self._dd_analisis["forma"])
            + "\n\n" + dd.texto_ajuste(self._dd_analisis))
        self._say("Torre en Y lista.",
                  "Pulse Generar para crear el edificio; cada local "
                  "queda adyacente al corredor de su ala y el "
                  "mobiliario automático se omite (geometría "
                  "radiante)")

    def _dd_hospital_x(self) -> None:
        """v3.47.0: HOSPITAL EN X REAL del programa actual: dos
        barras perpendiculares cruzadas con el hub central en el
        cruce (vestíbulo), corredor por brazo y locales a ambos
        lados; deja el análisis listo para «Generar»."""
        from domain import radial as rd
        from domain import desde_dibujo as dd
        try:
            programa = self._dd_programa()
            largo = simpledialog.askstring(
                "Hospital en X v3.47", "Largo total de cada barra "
                "(m):", initialvalue="64.0", parent=self)
            if not largo:
                return
            ancho = simpledialog.askstring(
                "Hospital en X v3.47", "Ancho de cada barra (m):",
                initialvalue="14.0", parent=self)
            if ancho is None:
                return
            corredor = simpledialog.askstring(
                "Hospital en X v3.47", "Corredor del brazo (m, "
                "0 = sin corredor):", initialvalue="2.0", parent=self)
            if corredor is None:
                return
            cabecera = simpledialog.askstring(
                "Hospital en X v3.47",
                "Cabecera transversal al fondo del brazo (m, "
                "0 = sin cabecera):", initialvalue="0.0",
                parent=self)
            if cabecera is None:
                return
            rotacion = simpledialog.askstring(
                "Hospital en X v3.47",
                "Rotación de la X en grados (45 = X diagonal, "
                "0 = cruz en +):", initialvalue="45", parent=self)
            if rotacion is None:
                return
            niveles = simpledialog.askstring(
                "Hospital en X v3.47",
                "Niveles de planta tipo (1-20, vacío = 1):",
                initialvalue="1", parent=self)
            if niveles is None:
                return
            centro = (0.0, 0.0)
            try:
                poly = self._dd_poligono()
                if poly:
                    centro = (sum(float(p[0]) for p in poly)
                              / len(poly),
                              sum(float(p[1]) for p in poly)
                              / len(poly))
            except Exception:  # noqa: BLE001 — sin contorno: origen
                centro = (0.0, 0.0)
            analisis = rd.plan_x(
                programa, centro=(centro[0], centro[1]),
                largo_barra=float(str(largo).strip().replace(
                    ",", ".")),
                ancho_barra=float(str(ancho).strip().replace(
                    ",", ".")),
                corredor_m=float(str(corredor).strip().replace(
                    ",", ".") or 0.0),
                cabecera_m=float(str(cabecera).strip().replace(
                    ",", ".") or 0.0),
                angulo=math.radians(float(
                    str(rotacion).strip().replace(",", ".") or 45.0)),
                altura_nivel_m=self._dd_float(self._dd_altura, 3.2),
                niveles=int(str(niveles).strip() or 1))
            self._dd_analisis = analisis
            self._dd_validacion = {"bloquea": False,
                                   "errores": [], "avisos": []}
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        self._dd_texto_set(
            dd.texto_inferencia(self._dd_analisis["forma"])
            + "\n\n" + dd.texto_ajuste(self._dd_analisis))
        self._say("Hospital en X listo.",
                  "Pulse Generar para crear el edificio; el cruce de "
                  "las barras es el hub con el vestíbulo y cada "
                  "local queda adyacente al corredor de su brazo")

    def _dd_aplicar(self) -> None:
        """Genera el edificio del contorno y lo deja en el proyecto.
        Desde v3.39.0 pregunta qué hacer si YA hay un edificio de
        este asistente (reemplazar / crear otro), aplica los
        espesores expertos y guarda el estado con el proyecto
        (spec §27/§28 + §30)."""
        from domain import desde_dibujo as dd
        if self._dd_analisis is None:
            self._dd_ajustar()
            if self._dd_analisis is None:
                return
        try:
            peticion = self._dd_peticion()
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        opciones: Dict[str, Any] = {
            "nombre_edificio": peticion.nombre_edificio,
            "trazar_muros": peticion.trazar_muros,
            "modo": self._dd_modo.get(),
            "espesor_contorno_m": peticion.espesor_contorno_m,
            "espesor_local_m": peticion.espesor_local_m,
            "mobiliario": bool(self._dd_mobiliario.get()),
        }
        if self._dd_origen.get() == "espacio" \
                and self._dd_boceto.get():
            espacio = self._dd_espacios.get(self._dd_espacio.get())
            if espacio is not None:
                opciones["eliminar_boceto"] = espacio.code
        previo = dd.edificio_previo(self.ctx)
        if previo is not None:
            respuesta = messagebox.askyesnocancel(
                "Desde dibujo",
                "Este asistente ya generó «"
                + str(getattr(previo, "name", previo))
                + "» en este proyecto.\n\nSÍ: lo REEMPLAZA (se "
                "eliminan sus niveles y espacios) y genera el "
                "nuevo.\nNO: crea OTRO edificio además de él.\n\n"
                "¿Reemplaza el edificio anterior?",
                parent=self._dd_dialog)
            if respuesta is None:
                return
            opciones["reemplazar_previo"] = bool(respuesta)
        try:
            resumen = dd.aplicar_plan(self.ctx, self._dd_analisis,
                                      opciones)
            dd.guardar_estado(self.ctx, peticion)
            self.ctx.commit()
        except Exception as exc:  # noqa: BLE001 — error y rollback
            self.ctx.rollback()
            self._dd_error(exc)
            return
        self.refresh_all()
        texto = dd.texto_resumen_generacion(resumen) + "\n\n" + \
            dd.texto_ajuste(self._dd_analisis)
        self._dd_texto_set(texto)
        self._say(dd.texto_resumen_generacion(resumen),
                  "Todo son entidades reales: QTO, presupuesto, "
                  "checks, DXF e informes los ven")

    def _dd_exportar_bim(self) -> None:
        """Exporta TODO el proyecto desde el asistente (v3.46.0):
        IFC4 (BIM) + DXF R2010 + DXF R12 + JSON + CSV + XLSX + SVG a
        la carpeta que elija el usuario, en un solo gesto. Si aún no
        se pulsó «Generar», lo dice amablemente en vez de fallar."""
        from services.export_service import ExportService
        tiene = bool(
            self.ctx.architecture.list("SPACE", self.ctx.project.id)
            or self.ctx.architecture.list("WALL", self.ctx.project.id))
        if not tiene:
            messagebox.showinfo(
                "Exportar BIM (IFC+DXF)",
                "Todavía no hay edificación en el proyecto.\n\n"
                "Pulse «Generar» para materializar el plano y después "
                "exporte el paquete BIM.",
                parent=self._dd_dialog)
            return
        carpeta = filedialog.askdirectory(
            title="Carpeta para el BIM (IFC) + DXF + datos",
            parent=self._dd_dialog)
        if not carpeta:
            return
        try:
            res = ExportService().exportar_todo(self.ctx, carpeta)
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        lineas = [f"{fmt}: {os.path.basename(ruta)} "
                  f"({max(1, os.path.getsize(ruta) // 1024)} KB)"
                  for fmt, ruta in sorted(res["archivos"].items())]
        lineas += [f"{fmt}: NO EXPORTADO — {msg}"
                   for fmt, msg in sorted(res["errores"].items())]
        self._say(
            f"Paquete BIM exportado: {len(res['archivos'])} "
            f"archivo(s) en {res['carpeta']}.",
            "El IFC4 se abre en visores BIM; los DXF, en cualquier CAD")
        messagebox.showinfo(
            "Exportar BIM (IFC + DXF)",
            "Carpeta:\n" + res["carpeta"] + "\n\n"
            + "\n".join(lineas), parent=self._dd_dialog)

    def _dd_peticion(self) -> Any:
        """La petición del diálogo como contrato del asistente
        (v3.39.0, spec §37): contorno, programa y opciones."""
        from domain import desde_dibujo as dd
        return dd.PlanRequest(
            contorno=[tuple(p) for p in self._dd_poligono()],
            programa=self._dd_programa(),
            altura_nivel_m=self._dd_float(self._dd_altura, 3.0),
            margen_m=self._dd_float(self._dd_margen, 0.0),
            modo=self._dd_modo.get(),
            nombre_edificio=(self._dd_nombre.get()
                             or "Edificio desde dibujo").strip(),
            trazar_muros=bool(self._dd_muros.get()),
            patio=bool(self._dd_patio.get()),
            patio_ancho_m=self._dd_float(self._dd_patio_ancho, 3.0),
            espesor_contorno_m=self._dd_float(self._dd_esp_cont, 0.20),
            espesor_local_m=self._dd_float(self._dd_esp_loc, 0.15),
            niveles_deseados=self._dd_niveles_pedido(),
            encaje_estricto=bool(self._dd_encaje.get()),
            seleccion=self._dd_seleccion_actual(),
            ajuste=self._dd_ajuste_actual(),
            chaflanes=bool(self._dd_chaflanes.get()))

    def _dd_quick_aplicar(self) -> None:
        """La especificación rápida escribe la tabla de usos
        (v3.39.0, spec §42 sin IA) y avisa de lo que no entendió."""
        from domain import desde_dibujo as dd
        try:
            qs = dd.quick_spec(self._dd_quick.get())
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        if not qs["usos"]:
            detalle = (" No reconocí: "
                       + ", ".join(qs["desconocidos"])) \
                if qs["desconocidos"] else ""
            messagebox.showwarning(
                "Desde dibujo",
                "No pude reconocer locales en la línea rápida."
                + detalle,
                parent=self._dd_dialog)
            return
        self._dd_usos = list(qs["usos"])
        self._dd_arbol_refresca()
        if qs["niveles"]:
            self._dd_niveles_des.set(str(qs["niveles"]))
        lineas = ["ESPECIFICACIÓN RÁPIDA",
                  f"«{self._dd_quick.get().strip()}»",
                  f"Usos reconocidos: {len(qs['usos'])} · "
                  f"niveles: "
                  + (str(qs["niveles"]) if qs["niveles"] else "auto")]
        for u in qs["usos"]:
            lineas.append(f"   - {u['space_type']} x{u['cantidad']}")
        for desconocido in qs["desconocidos"]:
            lineas.append(f"   ? no reconocido: {desconocido}")
        for aviso in qs["avisos"]:
            lineas.append(f"nota: {aviso}")
        lineas.append("La tabla de la sección 2 queda escrita: "
                      "revísela y pulse «¿Cabe en el área?».")
        self._dd_texto_set("\n".join(lineas))

    def _dd_arbol_refresca(self) -> None:
        """Vuelca ``self._dd_usos`` en la tabla (gancho de pruebas)."""
        for hijo in self._dd_arbol.get_children():
            self._dd_arbol.delete(hijo)
        for uso in self._dd_usos:
            area = uso.get("area_m2")
            self._dd_arbol.insert("", "end", values=(
                uso.get("space_type", ""), uso.get("cantidad", 1),
                f"{area:.2f}" if area else "(DNA)"))

    def _dd_conf_refresca(self) -> None:
        """Volca el historial de configuraciones en el combobox."""
        from domain import desde_dibujo as dd
        try:
            configs = dd.listar_configuraciones(self.ctx)
        except Exception:  # noqa: BLE001 — sin proyecto, vacío
            configs = []
        self._dd_conf_combo.configure(
            values=[f"{c.get('etiqueta', '?')} · "
                    f"{str(c.get('fecha', ''))[:19]}"
                    for c in configs])
        if configs:
            self._dd_conf_combo.current(0)

    def _dd_config_guardar(self) -> None:
        """Guarda una fotografía de la configuración actual en el
        proyecto (v3.39.0, spec §29)."""
        from domain import desde_dibujo as dd
        try:
            peticion = self._dd_peticion()
            entrada = dd.guardar_configuracion(
                self.ctx, peticion, self._dd_analisis)
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        self._dd_conf_refresca()
        self._say(f"Configuración guardada: {entrada['etiqueta']}.",
                  "El historial vive dentro del proyecto: cierre y "
                  "vuelva para retomarlo igual")

    def _dd_config_restaurar(self) -> None:
        """Restaura la configuración elegida del historial."""
        from domain import desde_dibujo as dd
        configs = dd.listar_configuraciones(self.ctx)
        if not configs:
            messagebox.showinfo(
                "Desde dibujo",
                "Todavía no hay configuraciones guardadas en este "
                "proyecto: pulse «Guardar» para crear la primera.",
                parent=self._dd_dialog)
            return
        try:
            indice = max(0, self._dd_conf_combo.current())
        except Exception:  # noqa: BLE001 — sin selección
            indice = 0
        indice = min(indice, len(configs) - 1)
        try:
            peticion = dd.restaurar_configuracion(self.ctx, indice)
            self._dd_carga_peticion(peticion)
        except Exception as exc:  # noqa: BLE001 — error amable
            self._dd_error(exc)
            return
        self._say(f"Configuración restaurada: "
                  f"{configs[indice].get('etiqueta', '?')}.",
                  "Revise el contorno y el programa, y genere de "
                  "nuevo cuando quiera")

    def _dd_carga_peticion(self, peticion: Any) -> None:
        """Carga una petición restaurada en los controles del
        diálogo (los campos que tienen control real)."""
        from domain import desde_dibujo as dd
        self._dd_altura.set(f"{float(peticion.altura_nivel_m):.2f}")
        self._dd_margen.set(f"{float(peticion.margen_m):.2f}")
        self._dd_nombre.set(str(peticion.nombre_edificio))
        self._dd_muros.set(bool(peticion.trazar_muros))
        self._dd_patio.set(bool(peticion.patio))
        self._dd_patio_ancho.set(f"{float(peticion.patio_ancho_m):.2f}")
        self._dd_esp_cont.set(f"{float(peticion.espesor_contorno_m):.2f}")
        self._dd_esp_loc.set(f"{float(peticion.espesor_local_m):.2f}")
        if hasattr(self, "_dd_encaje"):
            self._dd_encaje.set(bool(getattr(peticion,
                                             "encaje_estricto", True)))
        if hasattr(self, "_dd_ajuste_combo"):
            from domain import desde_dibujo as _dd41b
            self._dd_ajuste.set(_dd41b.ETIQUETA_AJUSTE.get(
                str(getattr(peticion, "ajuste", "ideal") or "ideal"),
                _dd41b.ETIQUETA_AJUSTE["minimo"]))
        sel_p = getattr(peticion, "seleccion", None)
        self._dd_seleccion = ({str(c).strip().upper(): True
                               for c in sel_p} if sel_p else None)
        if peticion.niveles_deseados:
            self._dd_niveles_des.set(str(int(peticion.niveles_deseados)))
        if hasattr(self, "_dd_chaflanes"):
            self._dd_chaflanes.set(bool(getattr(peticion,
                                                "chaflanes", True)))
        contorno = list(peticion.contorno or [])
        if len(contorno) == 4:
            xs = sorted({float(p[0]) for p in contorno})
            ys = sorted({float(p[1]) for p in contorno})
            if len(xs) == 2 and len(ys) == 2:
                self._dd_origen.set("rectangulo")
                self._dd_origen_cambio()
                self._dd_rec_ancho.set(f"{xs[1] - xs[0]:.2f}")
                self._dd_rec_fondo.set(f"{ys[1] - ys[0]:.2f}")
                self._dd_rec_ox.set(f"{xs[0]:.2f}")
                self._dd_rec_oy.set(f"{ys[0]:.2f}")
        if peticion.modo == "edificacion":
            self._dd_modo.set("edificacion")
            self._dd_modo_cambio()
            self._dd_usos = dd.usos_de_programa(peticion.programa)
            self._dd_arbol_refresca()

    # -- asistente de modificaciones (v3.14.0) ---------------------------
    # Edición guiada: elemento + operación + parámetros numéricos con
    # vista previa, para cuando el clic fino sobre el plano no es cómodo.

    _MOD_OPS: tuple = (("Mover", "mover"), ("Copiar", "copiar"),
                       ("Reflejar", "reflejar"), ("Girar", "girar"),
                       ("Recortar", "recortar"), ("Alargar", "alargar"),
                       ("Chaflán", "chaflan"), ("Dividir", "dividir"),
                       ("Estirar", "estirar"), ("Paralela", "paralela"),
                       ("Borrar", "borrar"))
    _MOD_OPS_LOCAL = ("Mover", "Copiar", "Reflejar", "Girar", "Borrar")

    def open_mod_wizard(self) -> None:
        """Asistente de modificaciones con parámetros numéricos."""
        if self._mod_dialog is not None and self._mod_dialog.winfo_exists():
            self._mod_dialog.deiconify()
            self._mod_dialog.lift()
            return
        dialog = tk.Toplevel(self)
        self._mod_dialog = dialog
        dialog.title("Asistente de modificaciones")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "modificaciones")
        estado: Dict[str, Any] = {"tipo": "WALL", "uid": None}
        self._mod_estado = estado
        dialog._mod_state = estado
        self._mod_campos: Dict[str, Any] = {}
        dialog._mod_campos = self._mod_campos

        ttk.Label(dialog, text="1 · Elige el elemento a modificar",
                  style="Hint.TLabel").pack(fill="x", padx=10, pady=(8, 0))
        fila1 = ttk.Frame(dialog)
        fila1.pack(fill="x", padx=10)
        tipo_var = tk.StringVar(value="Muros")
        dialog._mod_tipo_var = tipo_var
        tipo_combo = ttk.Combobox(fila1, textvariable=tipo_var, width=10,
                                  values=("Muros", "Locales"),
                                  state="readonly")
        tipo_combo.pack(side="left")
        dialog._mod_tipo_combo = tipo_combo
        ttk.Button(fila1, text="↻ Refrescar",
                   command=self._mod_refresca).pack(side="left", padx=6)

        columnas = ("codigo", "nombre", "nivel", "detalle")
        tree = ttk.Treeview(dialog, columns=columnas, show="headings",
                            height=7)
        for col, texto, ancho in (("codigo", "Código", 110),
                                  ("nombre", "Nombre", 210),
                                  ("nivel", "Nivel", 130),
                                  ("detalle", "Detalle", 170)):
            tree.heading(col, text=texto)
            tree.column(col, width=ancho, anchor="w")
        tree.pack(fill="x", padx=10, pady=4)
        dialog._mod_tree = tree
        tree.bind("<<TreeviewSelect>>", self._mod_al_seleccionar)

        ttk.Label(dialog, text="2 · Elige la operación",
                  style="Hint.TLabel").pack(fill="x", padx=10, pady=(6, 0))
        op_var = tk.StringVar(value="Mover")
        dialog._mod_op_var = op_var
        op_combo = ttk.Combobox(dialog, textvariable=op_var, width=28,
                                state="readonly")
        dialog._mod_op_combo = op_combo
        op_combo.pack(fill="x", padx=10)
        op_combo.bind("<<ComboboxSelected>>",
                      lambda _e: self._mod_pinta_params())

        ttk.Label(dialog, text="3 · Parámetros (metros y grados; coma o "
                               "punto decimal)",
                  style="Hint.TLabel").pack(fill="x", padx=10, pady=(6, 0))
        params = ttk.Frame(dialog)
        params.pack(fill="x", padx=10)
        dialog._mod_params = params

        fila_b = ttk.Frame(dialog)
        fila_b.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Button(fila_b, text="👁 Vista previa",
                   command=self._mod_preview).pack(side="left")
        ttk.Button(fila_b, text="✔ Aplicar", style="Accent.TButton",
                   command=self._mod_aplicar).pack(side="left", padx=6)
        self._mod_resultado = tk.StringVar(value="")
        dialog._mod_resultado = self._mod_resultado
        ttk.Label(dialog, textvariable=self._mod_resultado,
                  style="Hint.TLabel", wraplength=880,
                  justify="left").pack(fill="x", padx=10)

        canvas_prev = tk.Canvas(dialog, height=210, highlightthickness=0,
                                background="#232833")
        canvas_prev.pack(fill="both", expand=True, padx=10, pady=(4, 8))
        dialog._mod_canvas = canvas_prev
        # ganchos de prueba sobre el diálogo (patrón _regen_*/_vista3d_*)
        dialog._mod_elegir = self._mod_elegir
        dialog._mod_pinta_params = self._mod_pinta_params
        dialog._mod_preview = self._mod_preview
        dialog._mod_aplicar = self._mod_aplicar

        tipo_combo.bind("<<ComboboxSelected>>", self._mod_al_cambiar_tipo)
        self._mod_al_cambiar_tipo()
        self._say("Asistente de modificaciones abierto.",
                  "Elige elemento, operación y parámetros; la vista previa "
                  "enseña el resultado antes de aplicar")

    def _mod_al_cambiar_tipo(self, _evento: Any = None) -> None:
        estado = self._mod_estado
        estado["tipo"] = ("SPACE" if self._mod_dialog._mod_tipo_var.get()
                          == "Locales" else "WALL")
        estado["uid"] = None
        ops = (self._MOD_OPS_LOCAL if estado["tipo"] == "SPACE"
               else [texto for texto, _clave in self._MOD_OPS])
        self._mod_dialog._mod_op_combo.configure(values=ops)
        self._mod_dialog._mod_op_var.set(ops[0])
        self._mod_refresca()
        self._mod_pinta_params()

    def _mod_ops_clave(self) -> str:
        texto = self._mod_dialog._mod_op_var.get()
        for etiqueta, clave in self._MOD_OPS:
            if etiqueta == texto:
                return clave
        return "mover"

    def _mod_refresca(self) -> None:
        estado = self._mod_estado
        tree = self._mod_dialog._mod_tree
        tree.delete(*tree.get_children())
        niveles: Dict[str, str] = {}
        filas = []
        for ent in sorted(self.ctx.architecture.list(estado["tipo"],
                                                     self.ctx.project.id),
                          key=lambda e: e.code):
            nivel = ""
            if getattr(ent, "level_id", ""):
                if ent.level_id not in niveles:
                    lv = self.ctx.architecture.get("LEVEL", ent.level_id)
                    niveles[ent.level_id] = lv.name if lv else ""
                nivel = niveles[ent.level_id]
            if estado["tipo"] == "WALL":
                detalle = (f"{ent.length_m:.2f} m · espesor "
                           f"{ent.thickness_m:.2f} m")
                nombre = ""
            else:
                detalle = f"{ent.area_m2():.2f} m2"
                nombre = ent.name
            filas.append((ent.id, ent.code, nombre, nivel, detalle))
        for uid, codigo, nombre, nivel, detalle in filas:
            tree.insert("", "end", iid=uid,
                        values=(codigo, nombre, nivel, detalle))
        if filas:
            primero = filas[0][0]
            tree.selection_set(primero)
            tree.see(primero)

    def _mod_al_seleccionar(self, _evento: Any = None) -> None:
        tree = self._mod_dialog._mod_tree
        seleccion = tree.selection()
        if not seleccion:
            return
        self._mod_estado["uid"] = seleccion[0]
        self._mod_pinta_params()
        self._mod_preview()

    def _mod_elegir(self, uid: str) -> None:
        """Gancho de prueba: selecciona un elemento por uid."""
        self._mod_dialog._mod_tree.selection_set(uid)
        self._mod_dialog._mod_tree.see(uid)
        self._mod_al_seleccionar()

    def _mod_entidad(self) -> Optional[Any]:
        estado = self._mod_estado
        if not estado.get("uid"):
            return None
        try:
            return cad.resolver(self.ctx, estado["tipo"], estado["uid"])
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _f(texto: Any) -> float:
        return float(str(texto).strip().replace(",", "."))

    def _mod_fila_num(self, padre: Any, texto: str, valor: str) -> Any:
        fila = ttk.Frame(padre)
        fila.pack(fill="x", pady=1)
        ttk.Label(fila, text=texto, width=22,
                  anchor="w").pack(side="left")
        var = tk.StringVar(value=valor)
        ttk.Entry(fila, textvariable=var, width=12).pack(side="left")
        return var

    def _mod_fila_opciones(self, padre: Any, texto: str, valores: Any,
                           inicial: str = "") -> Any:
        fila = ttk.Frame(padre)
        fila.pack(fill="x", pady=1)
        ttk.Label(fila, text=texto, width=22,
                  anchor="w").pack(side="left")
        var = tk.StringVar(value=inicial or (valores[0] if valores else ""))
        ttk.Combobox(fila, textvariable=var, values=tuple(valores),
                     width=18, state="readonly").pack(side="left")
        return var

    def _mod_fila_radio(self, padre: Any, texto: str) -> Any:
        fila = ttk.Frame(padre)
        fila.pack(fill="x", pady=1)
        ttk.Label(fila, text=texto, width=22,
                  anchor="w").pack(side="left")
        var = tk.StringVar(value="inicio")
        ttk.Radiobutton(fila, text="inicio", value="inicio",
                        variable=var).pack(side="left")
        ttk.Radiobutton(fila, text="fin", value="fin",
                        variable=var).pack(side="left", padx=6)
        return var

    def _mod_codes_muros(self, excluir: Optional[str] = None) -> List[str]:
        codes = [w.code for w in sorted(
            self.ctx.architecture.list("WALL", self.ctx.project.id),
            key=lambda e: e.code)]
        if excluir:
            codes = [c for c in codes if c != excluir]
        return codes

    def _mod_pinta_params(self) -> None:
        """Reconstruye los parámetros según la operación elegida."""
        if not (self._mod_dialog and self._mod_dialog.winfo_exists()):
            return
        estado = self._mod_estado
        op = self._mod_ops_clave()
        padre = self._mod_dialog._mod_params
        for hijo in padre.winfo_children():
            hijo.destroy()
        self._mod_campos = {}
        dialog = self._mod_dialog
        dialog._mod_campos = self._mod_campos
        ent = self._mod_entidad()
        if estado["tipo"] == "WALL" and ent is not None:
            cx = (ent.start[0] + ent.end[0]) / 2.0
            cy = (ent.start[1] + ent.end[1]) / 2.0
            largo = ent.length_m
            ux, uy = (ent.end[0] - ent.start[0]) / max(largo, 1e-9), \
                     (ent.end[1] - ent.start[1]) / max(largo, 1e-9)
        elif estado["tipo"] == "SPACE" and ent is not None:
            xs = [p[0] for p in (ent.boundary or [])]
            ys = [p[1] for p in (ent.boundary or [])]
            cx, cy = (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else (0, 0)
            ux, uy, largo = 1.0, 0.0, 0.0
        else:
            cx = cy = 0.0
            ux, uy, largo = 1.0, 0.0, 0.0
        campos = self._mod_campos
        if op in ("mover", "copiar"):
            campos["dx"] = self._mod_fila_num(padre, "Desplazamiento dx:", "1.00")
            campos["dy"] = self._mod_fila_num(padre, "Desplazamiento dy:", "0.00")
        elif op == "reflejar":
            campos["x1"] = self._mod_fila_num(padre, "Eje: x1:", f"{cx:.2f}")
            campos["y1"] = self._mod_fila_num(padre, "Eje: y1:", f"{cy - 5.0:.2f}")
            campos["x2"] = self._mod_fila_num(padre, "Eje: x2:", f"{cx:.2f}")
            campos["y2"] = self._mod_fila_num(padre, "Eje: y2:", f"{cy + 5.0:.2f}")
            ttk.Label(padre, text="Eje vertical por defecto (arriba-abajo "
                                  "por el centro del elemento)",
                      style="Hint.TLabel").pack(anchor="w")
        elif op == "girar":
            campos["cx"] = self._mod_fila_num(padre, "Centro x:", f"{cx:.2f}")
            campos["cy"] = self._mod_fila_num(padre, "Centro y:", f"{cy:.2f}")
            campos["angulo"] = self._mod_fila_num(padre,
                                                  "Ángulo (antihorario):",
                                                  "90")
        elif op == "recortar":
            campos["cuchilla"] = self._mod_fila_opciones(
                padre, "Muro cuchilla:", self._mod_codes_muros(),
                self._mod_codes_muros(getattr(ent, "code", ""))[0]
                if self._mod_codes_muros(getattr(ent, "code", "")) else "")
            campos["lado"] = self._mod_fila_radio(padre,
                                                  "Lado a conservar:")
        elif op == "alargar":
            campos["objetivo"] = self._mod_fila_opciones(
                padre, "Muro objetivo:", self._mod_codes_muros(),
                self._mod_codes_muros(getattr(ent, "code", ""))[0]
                if self._mod_codes_muros(getattr(ent, "code", "")) else "")
            campos["extremo"] = self._mod_fila_radio(padre,
                                                     "Extremo a alargar:")
        elif op == "chaflan":
            campos["otro"] = self._mod_fila_opciones(
                padre, "Segundo muro:", self._mod_codes_muros(),
                self._mod_codes_muros(getattr(ent, "code", ""))[0]
                if self._mod_codes_muros(getattr(ent, "code", "")) else "")
            campos["distancia"] = self._mod_fila_num(padre,
                                                     "Distancia del chaflán:",
                                                     "0.50")
        elif op == "dividir":
            campos["px"] = self._mod_fila_num(padre, "Punto de corte x:",
                                              f"{cx:.2f}")
            campos["py"] = self._mod_fila_num(padre, "Punto de corte y:",
                                              f"{cy:.2f}")
        elif op == "estirar":
            campos["extremo"] = self._mod_fila_radio(padre,
                                                     "Extremo a mover:")
            campos["nx"] = self._mod_fila_num(
                padre, "Nueva x:", f"{cx + ux * 1.0:.2f}")
            campos["ny"] = self._mod_fila_num(
                padre, "Nueva y:", f"{cy + uy * 1.0:.2f}")
        elif op == "paralela":
            campos["distancia"] = self._mod_fila_num(
                padre, "Distancia (izquierda +):", "2.00")
        elif op == "borrar":
            ttk.Label(padre, text="Sin parámetros: se pedirá confirmación "
                                  "al aplicar.",
                      style="Hint.TLabel").pack(anchor="w")
        self._mod_preview()

    def _mod_leer(self, *claves: str) -> List[float]:
        valores = []
        for clave in claves:
            valores.append(self._f(self._mod_campos[clave].get()))
        return valores

    def _mod_parametro_muro(self, clave: str) -> Optional[Any]:
        code = self._mod_campos[clave].get()
        try:
            return cad.resolver(self.ctx, "WALL", code)
        except Exception:  # noqa: BLE001
            return None

    def _mod_preview(self) -> None:
        """Dibuja «antes» (gris) y «después» (naranja) en el canvas."""
        if not (self._mod_dialog and self._mod_dialog.winfo_exists()):
            return
        canvas = self._mod_dialog._mod_canvas
        canvas.delete("all")
        ent = self._mod_entidad()
        if ent is None:
            self._mod_resultado.set(
                "Elige un elemento de la lista de arriba.")
            return
        op = self._mod_ops_clave()
        if self._mod_estado["tipo"] == "WALL":
            antes = [(tuple(ent.start), tuple(ent.end))]
        else:
            antes = [list(ent.boundary or [])]
        despues: List[Any] = []
        avisos: List[str] = []
        try:
            if op in ("mover", "copiar"):
                dx, dy = self._mod_leer("dx", "dy")
                despues = [[(p[0] + dx, p[1] + dy) for p in seg]
                           for seg in antes]
            elif op == "reflejar":
                x1, y1, x2, y2 = self._mod_leer("x1", "y1", "x2", "y2")
                despues = [cad.g_reflejar(seg, (x1, y1), (x2, y2))
                           for seg in antes]
            elif op == "girar":
                cx, cy, angulo = self._mod_leer("cx", "cy", "angulo")
                despues = [cad.g_girar(seg, (cx, cy), angulo)
                           for seg in antes]
            elif op == "recortar":
                cuchilla = self._mod_parametro_muro("cuchilla")
                if cuchilla is None:
                    raise ValueError("Elige el muro cuchilla")
                nuevo = cad.g_recortar(tuple(ent.start), tuple(ent.end),
                                       tuple(cuchilla.start),
                                       tuple(cuchilla.end),
                                       self._mod_campos["lado"].get())
                despues = [list(nuevo)]
            elif op == "alargar":
                objetivo = self._mod_parametro_muro("objetivo")
                if objetivo is None:
                    raise ValueError("Elige el muro objetivo")
                nuevo = cad.g_alargar(tuple(ent.start), tuple(ent.end),
                                      tuple(objetivo.start),
                                      tuple(objetivo.end),
                                      self._mod_campos["extremo"].get())
                despues = [list(nuevo)]
            elif op == "chaflan":
                otro = self._mod_parametro_muro("otro")
                if otro is None:
                    raise ValueError("Elige el segundo muro")
                datos = cad.g_chaflan(tuple(ent.start), tuple(ent.end),
                                      tuple(otro.start), tuple(otro.end),
                                      self._f(self._mod_campos["distancia"]
                                              .get()))
                despues = [list(datos["nuevo_a"]), list(datos["nuevo_b"]),
                           list(datos["union"])]
            elif op == "dividir":
                px, py = self._mod_leer("px", "py")
                datos = cad.g_dividir(tuple(ent.start), tuple(ent.end),
                                      (px, py))
                despues = [list(datos["parte1"]), list(datos["parte2"])]
            elif op == "estirar":
                nx, ny = self._mod_leer("nx", "ny")
                nuevo = cad.g_estirar(tuple(ent.start), tuple(ent.end),
                                      self._mod_campos["extremo"].get(),
                                      (nx, ny))
                despues = [list(nuevo)]
            elif op == "paralela":
                d = self._f(self._mod_campos["distancia"].get())
                despues = [list(cad.g_paralela(tuple(ent.start),
                                               tuple(ent.end), d))]
            # op == "borrar": sin geometría "después"
        except (ValueError, Exception) as exc:  # noqa: BLE001
            avisos.append(str(getattr(exc, "message", exc)))
        puntos = [p for seg in (antes + despues) for p in seg]
        if puntos:
            xs = [p[0] for p in puntos]
            ys = [p[1] for p in puntos]
            ancho = max(canvas.winfo_width(), 320)
            alto = max(canvas.winfo_height(), 200)
            escala = min((ancho - 60) / max(max(xs) - min(xs), 1e-6),
                         (alto - 40) / max(max(ys) - min(ys), 1e-6))
            escala = min(escala, 200.0)

            def pantalla(p):
                return (ancho / 2 + (p[0] - (min(xs) + max(xs)) / 2) * escala,
                        alto / 2 - (p[1] - (min(ys) + max(ys)) / 2) * escala)

            for seg in antes:
                coords = []
                for p in seg:
                    coords += list(pantalla(p))
                if len(seg) == 2:
                    canvas.create_line(*coords, fill="#8a93a6", width=4)
                else:
                    canvas.create_polygon(*coords, fill="", outline="#8a93a6",
                                          width=3)
            for seg in despues:
                coords = []
                for p in seg:
                    coords += list(pantalla(p))
                if len(seg) == 2:
                    canvas.create_line(*coords, fill="#e69138", width=4)
                else:
                    canvas.create_polygon(*coords, fill="", outline="#e69138",
                                          width=3, dash=(4, 2))
        texto = f"{op}: {ent.code}"
        if despues:
            texto += " — gris: ahora, naranja: después"
        for aviso in avisos:
            texto += f" · aviso: {aviso}"
        self._mod_resultado.set(texto)

    def _mod_aplicar(self) -> None:
        estado = self._mod_estado
        ent = self._mod_entidad()
        if ent is None:
            messagebox.showinfo("Asistente de modificaciones",
                                "Elige primero un elemento de la lista.",
                                parent=self)
            return
        op = self._mod_ops_clave()
        try:
            if op == "mover":
                dx, dy = self._mod_leer("dx", "dy")
                resumen = cad.mover(self.ctx,
                                    [(estado["tipo"], ent.id)], dx, dy)
            elif op == "copiar":
                dx, dy = self._mod_leer("dx", "dy")
                resumen = cad.copiar(self.ctx, estado["tipo"], ent.id,
                                     dx, dy)
            elif op == "reflejar":
                x1, y1, x2, y2 = self._mod_leer("x1", "y1", "x2", "y2")
                resumen = cad.reflejar(self.ctx, estado["tipo"], ent.id,
                                       (x1, y1), (x2, y2))
            elif op == "girar":
                cx, cy, angulo = self._mod_leer("cx", "cy", "angulo")
                resumen = cad.girar(self.ctx, estado["tipo"], ent.id,
                                    (cx, cy), angulo)
            elif op == "recortar":
                cuchilla = self._mod_parametro_muro("cuchilla")
                if cuchilla is None:
                    raise ValueError("Elige el muro cuchilla")
                resumen = cad.recortar(self.ctx, ent.id, cuchilla.id,
                                       self._mod_campos["lado"].get())
            elif op == "alargar":
                objetivo = self._mod_parametro_muro("objetivo")
                if objetivo is None:
                    raise ValueError("Elige el muro objetivo")
                resumen = cad.alargar(self.ctx, ent.id, objetivo.id,
                                      self._mod_campos["extremo"].get())
            elif op == "chaflan":
                otro = self._mod_parametro_muro("otro")
                if otro is None:
                    raise ValueError("Elige el segundo muro")
                resumen = cad.chaflan(self.ctx, ent.id, otro.id,
                                      self._f(self._mod_campos["distancia"]
                                              .get()))
            elif op == "dividir":
                px, py = self._mod_leer("px", "py")
                resumen = cad.dividir(self.ctx, ent.id, (px, py))
            elif op == "estirar":
                nx, ny = self._mod_leer("nx", "ny")
                resumen = cad.estirar(self.ctx, ent.id,
                                      self._mod_campos["extremo"].get(),
                                      (nx, ny))
            elif op == "paralela":
                resumen = cad.paralela(self.ctx, ent.id,
                                       self._f(self._mod_campos["distancia"]
                                               .get()))
            elif op == "borrar":
                if not messagebox.askyesno(
                        "Borrar elemento",
                        f"¿Eliminar {ent.ENTITY_TYPE} {ent.code}?\n\n"
                        "Queda registrado y puedes deshacerlo con Ctrl+Z.",
                        parent=self):
                    return
                resumen = cad.borrar(self.ctx, estado["tipo"], ent.id)
            else:
                return
        except Exception as exc:  # noqa: BLE001 - amable y con rollback
            self.ctx.rollback()
            accion = getattr(exc, "suggested_action", "")
            messagebox.showerror(
                "Asistente de modificaciones",
                str(getattr(exc, "message", exc))
                + (f"\n\nSugerencia: {accion}" if accion else ""),
                parent=self)
            return
        try:
            cad.finalizar(self.ctx, resumen)
            self.ctx.commit()
        except Exception as exc:  # noqa: BLE001
            self.ctx.rollback()
            messagebox.showerror("Asistente de modificaciones", str(exc),
                                 parent=self)
            return
        self._mod_refresca()
        self._mod_pinta_params()
        self._mod_preview()
        self.refresh_all()
        self._say(cad.texto_resumen(resumen),
                  "Ctrl+Z deshace paso a paso")

    def export_report(self, fmt: str = "md") -> None:
        from services.documentation_service import DocumentationService
        es_pdf = fmt.lower() == "pdf"
        path = filedialog.asksaveasfilename(
            title="Informe del proyecto (PDF)" if es_pdf
            else "Informe del proyecto (Markdown)",
            defaultextension=".pdf" if es_pdf else ".md",
            filetypes=[("PDF", "*.pdf")] if es_pdf
            else [("Markdown", "*.md"), ("Texto", "*.txt")])
        if not path:
            return
        report = DocumentationService(self.ctx).generate_informe()
        if es_pdf:
            from exporters.markdown_pdf import export_markdown_pdf
            export_markdown_pdf(report, path)
        else:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(report)
        self._say(f"Informe exportado: {path}",
                  "Ábrelo con cualquier lector de PDF o editor de texto"
                  if es_pdf else
                  "Ábrelo con cualquier editor de texto o visor Markdown")

    # -- archivo -------------------------------------------------------------------
    def new_project(self) -> None:
        if self.application is None:
            return
        path = filedialog.asksaveasfilename(
            title="Nuevo proyecto", defaultextension=".arqgen",
            filetypes=[("Proyecto ARQ GEN", "*.arqgen")])
        if not path:
            return
        name = os.path.splitext(os.path.basename(path))[0]
        self.ctx.close()
        self.ctx = self.application.create_project(path, name=name)
        self._after_context_change()
        self._say(f"Proyecto «{name}» creado y listo. Está vacío: es un "
                  "lienzo en blanco.",
                  next_hint(spaces=0))

    def open_regen_dialog(self) -> None:
        """Editor REGENERATIVO de la edificación (v3.10.0).

        Lo pedido: «mover un local hacia otro lugar pero que recalcule
        y redistribuya los otros locales así como las instalaciones y
        módulos… elegir la variante que sustituya a la generada… que no
        sea un cambio huérfano sino que regenere todo».

        El diálogo reconstruye el programa de locales desde el proyecto
        (bwiz.program_from_project), lo deja editar (mover / a otro
        nivel / redimensionar / eliminar / añadir), genera las
        VARIANTES puntuadas del motor (bwiz.generate_variants) y
        SUSTITUYE la edificación generada con la variante elegida
        (bwiz.replace_plan: purga sin huérfanos + trazado nuevo +
        instalaciones recalculadas). Lo dibujado a mano se conserva.
        Ganchos de prueba: dialog._regen_*.
        """
        data, avisos = bwiz.program_from_project(self.ctx)
        building, _edif = bwiz._wizard_building(self.ctx)
        if building is None:
            messagebox.showinfo(
                "Regenerar edificación",
                "Aún no hay edificación generada por el asistente.\n\n"
                "Usa primero el «Asistente de edificación»; después este "
                "editor te deja mover, añadir, quitar o redimensionar "
                "locales y retraza TODO el edificio con variantes.",
                parent=self)
            return

        state: Dict[str, Any] = {"variantes": [], "variant": None}
        dialog = tk.Toplevel(self)
        self._regen_dialog = dialog
        dialog.title("Regenerar edificación — nada de cambios huérfanos")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "regen")

        intro = ttk.Label(
            dialog,
            text=" · ".join(avisos) + "  Se sustituye SOLO lo generado "
                 "por el asistente (locales, muros, vanos, relaciones y "
                 "terminales de instalaciones); lo dibujado a mano se "
                 "conserva.",
            style="Hint.TLabel", wraplength=1000, justify="left")
        intro.pack(fill="x", padx=8, pady=(6, 2))

        paned = ttk.PanedWindow(dialog, orient="vertical")
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        # -- programa de locales (arriba) ---------------------------------
        top = ttk.Labelframe(
            paned, text="Programa de locales (mover aquí = redistribuir "
                        "todo al regenerar)")
        cols = ("nivel", "nombre", "tipo", "ancho", "fondo")
        tree = ttk.Treeview(top, columns=cols, show="headings",
                            selectmode="browse", height=8)
        for column, text, width in (("nivel", "Nivel", 130),
                                    ("nombre", "Local", 200),
                                    ("tipo", "Tipo", 120),
                                    ("ancho", "Ancho (m)", 80),
                                    ("fondo", "Fondo (m)", 80)):
            tree.heading(column, text=text)
            tree.column(column, width=width, anchor="w")
        tree_scroll = ttk.Scrollbar(top, orient="vertical",
                                    command=tree.yview)
        tree.configure(yscrollcommand=tree_scroll.set)
        tree.pack(side="top", fill="both", expand=True, padx=4, pady=(4, 0))
        tree_scroll.pack(side="right", fill="y")

        buttons = ttk.Frame(top)
        buttons.pack(side="top", fill="x", padx=4, pady=4)

        def _selected_name() -> str:
            selection = tree.selection()
            if not selection:
                messagebox.showinfo(
                    "Regenerar edificación",
                    "Elige primero un local del programa.", parent=dialog)
                return ""
            values = tree.item(selection[0], "values")
            return str(values[1])

        def _edit_avisos(avisos_ed: list) -> None:
            for aviso in avisos_ed:
                self._say(aviso)
            state["variantes"] = []
            state["variant"] = None
            _regen_refresh()
            _regen_refresh_variants()

        def _regen_up() -> None:
            _edit_avisos(bwiz.move_room(data, _selected_name(), -1))

        def _regen_down() -> None:
            _edit_avisos(bwiz.move_room(data, _selected_name(), 1))

        def _regen_relevel() -> None:
            nombre = _selected_name()
            if not nombre:
                return
            _relevel_form(nombre)

        def _regen_resize() -> None:
            nombre = _selected_name()
            if not nombre:
                return
            room = bwiz._find_room(data, nombre)
            if room is None:
                return
            _resize_form(room)

        def _regen_remove() -> None:
            nombre = _selected_name()
            if not nombre:
                return
            _edit_avisos(bwiz.remove_room(data, nombre))

        def _regen_add() -> None:
            _add_form()

        for texto, comando, tip in (
                ("↑ Subir", _regen_up, "Mueve el local hacia el inicio "
                 "de su nivel: el trazado lo recoloca y redistribuye a "
                 "los demás"),
                ("↓ Bajar", _regen_down, "Mueve el local hacia el final "
                 "de su nivel"),
                ("A otro nivel…", _regen_relevel,
                 "Mueve el local a otro nivel (crea el nivel si falta)"),
                ("Redimensionar…", _regen_resize,
                 "Cambia ancho y fondo del local: los vecinos se "
                 "redistribuyen al regenerar"),
                ("Eliminar", _regen_remove,
                 "Quita el local del programa y sus relaciones"),
                ("＋ Añadir local…", _regen_add,
                 "Añade un local nuevo al programa")):
            self._tip(ttk.Button(buttons, text=texto, command=comando),
                      tip).pack(side="left", padx=(0, 4))
        paned.add(top, weight=3)

        # -- variantes (abajo) ---------------------------------------------
        bottom = ttk.Labelframe(
            paned, text="Variantes de planta regeneradas (elige la que "
                        "sustituirá a la actual)")
        variant_tree = ttk.Treeview(bottom,
                                    columns=("n", "esquema", "titulo",
                                             "score", "cabe", "coste"),
                                    show="headings", selectmode="browse",
                                    height=5)
        for column, text, width, anchor in (
                ("n", "#", 36, "w"),
                ("esquema", "Esquema", 150, "w"),
                ("titulo", "Variante", 240, "w"),
                ("score", "Puntos", 60, "e"),
                ("cabe", "Cabe en el lote", 170, "w"),
                ("coste", "Coste (CUP)", 110, "e")):
            variant_tree.heading(column, text=text)
            variant_tree.column(column, width=width, anchor=anchor)
        v_scroll = ttk.Scrollbar(bottom, orient="vertical",
                                 command=variant_tree.yview)
        variant_tree.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side="right", fill="y", padx=(0, 4), pady=2)
        variant_tree.pack(side="top", fill="both", expand=True,
                          padx=4, pady=2)
        cost_row = ttk.Frame(bottom)
        cost_row.pack(side="top", fill="x", padx=4, pady=(2, 0))
        ttk.Label(cost_row, text="Calidad de acabados:",
                  style="Dim.TLabel").pack(side="left")
        calidad_var = tk.StringVar(value=vbudget.CALIDAD_DEFECTO)
        calidad_combo = ttk.Combobox(cost_row, textvariable=calidad_var,
                                     state="readonly", width=11,
                                     values=list(vbudget.CALIDADES))
        calidad_combo.pack(side="left", padx=(4, 8))
        self._tip(calidad_combo, "calidad_coste")
        ttk.Label(cost_row,
                  text="El coste se recalcula al vivo con el catálogo "
                       "PRECONS III (la obra gruesa no cambia).",
                  style="Dim.TLabel").pack(side="left")
        metrics_label = ttk.Label(bottom, text="Genera variantes para ver "
                                  "el preview y las métricas.",
                                  style="Hint.TLabel")
        metrics_label.pack(side="bottom", fill="x", padx=6, pady=2)
        canvas = tk.Canvas(bottom, height=230, bg=theme.COL_CANVAS,
                           highlightthickness=0)
        canvas.pack(side="bottom", fill="both", expand=True,
                    padx=4, pady=(0, 4))
        paned.add(bottom, weight=4)

        # -- pie: sustituir -------------------------------------------------
        foot = ttk.Frame(dialog)
        foot.pack(fill="x", padx=8, pady=(0, 8))

        def _regen_close() -> None:
            dialog.destroy()

        self._tip(ttk.Button(foot, text="Cerrar", command=_regen_close),
                  "Cierra sin regenerar (nada se ha tocado aún)"
                  ).pack(side="right")
        self._tip(ttk.Button(foot, text="⤓ PNG de costes",
                             command=lambda: _regen_png_costes()),
                  "Exporta el gráfico comparativo del coste estimado "
                  "PRECONS de todas las variantes").pack(side="left")
        apply_btn = ttk.Button(foot, text="♻ Sustituir la edificación "
                               "generada", style="Accent.TButton",
                               command=lambda: _regen_apply())
        self._tip(apply_btn, "Purga lo generado por el asistente y "
                  "retraza TODO el edificio con la variante elegida; "
                  "las instalaciones se recalculan sobre la geometría "
                  "nueva").pack(side="right", padx=6)

        # -- refresco y generación -----------------------------------------
        def _regen_refresh() -> None:
            tree.delete(*tree.get_children())
            for level_name in data.level_names():
                for room in data.rooms_of_level(level_name):
                    tree.insert("", "end", values=(
                        level_name, room.name, room.space_type,
                        f"{room.width_m:g}", f"{room.depth_m:g}"))

        def _regen_refresh_variants() -> None:
            variant_tree.delete(*variant_tree.get_children())
            for variant in state["variantes"]:
                coste = getattr(variant, "cost", None)
                texto = vbudget.fmt_cup(coste.total) \
                    if coste is not None else "—"
                variant_tree.insert("", "end", iid=variant.key, values=(
                    variant.rank, variant.scheme, variant.title,
                    variant.score, variant.fits_text, texto))

        def _regen_choose(_event: Any = None) -> None:
            selection = variant_tree.selection()
            if not selection:
                return
            for variant in state["variantes"]:
                if variant.key == selection[0]:
                    state["variant"] = variant
                    break
            _regen_draw()

        def _regen_draw() -> None:
            variant = state.get("variant")
            canvas.delete("all")
            if variant is None or not variant.layouts:
                return
            rooms = variant.layouts[0].all_rooms
            if not rooms:
                return
            width = max(canvas.winfo_width(), 320)
            height = max(canvas.winfo_height(), 200)
            x0 = min(r.x for r in rooms)
            y0 = min(r.y for r in rooms)
            x1 = max(r.x + r.w for r in rooms)
            y1 = max(r.y + r.d for r in rooms)
            span_x = max(0.1, x1 - x0)
            span_y = max(0.1, y1 - y0)
            scale = min((width - 40) / span_x, (height - 30) / span_y)
            off_x = (width - span_x * scale) / 2 - x0 * scale
            off_y = (height - span_y * scale) / 2 - y0 * scale

            def _px(x: float) -> float:
                return off_x + x * scale

            def _py(y: float) -> float:
                return off_y + y * scale

            for wall in variant.layouts[0].walls:
                sx, sy = wall["start"]
                ex, ey = wall["end"]
                canvas.create_line(_px(sx), _py(sy), _px(ex), _py(ey),
                                   width=max(2, int(scale * 0.25) + 1),
                                   fill="#22262b")
            for room in rooms:
                fill = "#d8dde3"
                kind = (room.space_type or "").upper()
                if kind == "PATIO":
                    fill = "#4a5d43"
                elif kind == "CORRIDOR":
                    fill = "#3d4a5c"
                elif kind in ("STAIR", "CORE"):
                    fill = "#8a8f98"
                elif kind in ("BATHROOM", "KITCHEN", "LAUNDRY",
                              "CONSULTATION", "STERILIZATION"):
                    fill = "#b9cfd8"
                canvas.create_rectangle(_px(room.x), _py(room.y),
                                        _px(room.x + room.w),
                                        _py(room.y + room.d),
                                        fill=fill, outline="#5a6068")
                if room.w * scale > 46 and room.d * scale > 16:
                    canvas.create_text(
                        _px(room.x + room.w / 2),
                        _py(room.y + room.d / 2),
                        text=room.name, font=("TkDefaultFont", 8),
                        fill="#1b1e22")
            if state["variant"] is not None:
                variant = state["variant"]
                texto = (f"«{variant.title}» — {variant.score} puntos · "
                         + " · ".join(f"{k} {v:.2f}"
                                      for k, v in variant.metrics.items())
                         + " · " + variant.fits_text)
                coste = getattr(variant, "cost", None)
                if coste is not None:
                    texto += (f" · Estimación: {vbudget.fmt_cup(coste.total)} "
                              f"CUP ({vbudget.fmt_cup(coste.cost_m2)} "
                              "CUP/m²)")
                    desglose = vbudget.desglose_texto(coste)
                    if desglose:
                        texto += " · " + desglose
                metrics_label.config(text=texto)

        def _regen_generate() -> None:
            errores: List[str] = []
            for step in range(5):
                errores.extend(bwiz.validate_step(step, data))
            if errores:
                messagebox.showwarning(
                    "Regenerar edificación",
                    "Antes de generar variantes, revisa esto:\n\n"
                    + "\n".join(f"· {e}" for e in errores), parent=dialog)
                return
            state["variantes"] = bwiz.generate_variants(data)
            state["variant"] = state["variantes"][0] \
                if state["variantes"] else None
            if state["variantes"] and not self._variantes_costear(
                    data, state["variantes"], calidad_var.get()):
                self._say("Catálogo PRECONS III no disponible: los "
                          "costes de las variantes quedan en «—».",
                          "El resto del diálogo funciona igual.")
            _regen_refresh_variants()
            if state["variant"] is not None:
                variant_tree.selection_set(state["variant"].key)
            dialog.update_idletasks()
            _regen_draw()

        def _regen_on_calidad(_event: Any = None) -> None:
            """Cambia la calidad: el presupuesto vive sin regenerar."""
            if not state["variantes"]:
                return
            self._variantes_costear(data, state["variantes"],
                                    calidad_var.get())
            _regen_refresh_variants()
            if state.get("variant") is not None:
                try:
                    variant_tree.selection_set(state["variant"].key)
                except Exception:  # noqa: BLE001 — iid ausente
                    pass
            _regen_draw()
            self._say(f"Calidad «{calidad_var.get()}»: costes de las "
                      "variantes recalculados al vivo.")

        calidad_combo.bind("<<ComboboxSelected>>", _regen_on_calidad)

        def _regen_png_costes() -> None:
            con_coste = [v for v in state["variantes"]
                         if getattr(v, "cost", None) is not None]
            if not con_coste:
                messagebox.showinfo(
                    "Comparativa de costes",
                    "Genera variantes primero: el coste se estima con "
                    "el catálogo PRECONS III.", parent=dialog)
                return
            path = filedialog.asksaveasfilename(
                defaultextension=".png",
                initialfile=f"{(data.name or 'variantes')}"
                            "_costes.png".replace(" ", "_"),
                filetypes=[("PNG imagen", "*.png")])
            if not path:
                return
            try:
                from exporters.png_exporter import export_variant_costs_png
                export_variant_costs_png(
                    [(v.title, v.cost.total) for v in con_coste], path,
                    project_name=data.name, calidad=calidad_var.get())
                self._say("Comparativa de costes por variante exportada: "
                          f"{os.path.basename(path)}.",
                          "La barra más corta es la variante más "
                          "económica; el pie del gráfico la nombra.")
            except Exception as exc:  # noqa: BLE001 — aviso amable
                self._say("No pude exportar la comparativa de costes.",
                          str(exc))

        def _regen_apply() -> None:
            errores: List[str] = []
            for step in range(5):
                errores.extend(bwiz.validate_step(step, data))
            if errores:
                messagebox.showwarning(
                    "Regenerar edificación",
                    "Antes de sustituir, revisa esto:\n\n"
                    + "\n".join(f"· {e}" for e in errores), parent=dialog)
                return
            variant = state.get("variant")
            titulo = variant.title if variant is not None \
                else "trazado por defecto"
            if not messagebox.askyesno(
                    "Sustituir edificación",
                    "Se sustituirá TODO lo generado por el asistente "
                    "(locales, muros, vanos, relaciones y terminales de "
                    f"instalaciones) con la variante «{titulo}».\n\n"
                    "Lo dibujado a mano se conserva. ¿Continuar?",
                    parent=dialog):
                return
            try:
                resumen = bwiz.replace_plan(data, self.ctx, variant=variant)
            except Exception as exc:  # noqa: BLE001 - mensaje amable
                try:
                    self.ctx.rollback()
                except Exception:  # noqa: BLE001 - rollback best-effort
                    pass
                messagebox.showerror(
                    "Regenerar edificación",
                    f"No pude regenerar la edificación:\n{exc}",
                    parent=dialog)
                return
            dialog.destroy()
            self.refresh_all(fit=True)
            purga = resumen.get("purga", {})
            coste_txt = ""
            if variant is not None and getattr(variant, "cost", None) \
                    is not None:
                coste_txt = (f" Estimación PRECONS con acabados "
                             f"{variant.cost.calidad}: "
                             f"{vbudget.fmt_cup(variant.cost.total)} CUP "
                             f"({vbudget.fmt_cup(variant.cost.cost_m2)} "
                             "CUP/m²).")
            self._say(
                f"Edificación regenerada con «{titulo}»: "
                f"{purga.get('locales', 0)} locales, "
                f"{purga.get('muros', 0)} muros, "
                f"{purga.get('vanos', 0)} vanos, "
                f"{purga.get('relaciones', 0)} relaciones y "
                f"{purga.get('nodos', 0)} terminales anteriores "
                f"sustituidos; ahora {resumen.get('spaces', 0)} locales, "
                f"{resumen.get('walls', 0)} muros, "
                f"{resumen.get('doors', 0)} puertas y "
                f"{resumen.get('windows', 0)} ventanas. Instalaciones "
                "recalculadas sobre la geometría nueva." + coste_txt)

        # -- mini-formularios -----------------------------------------------
        def _parse_m(texto: str, default: float) -> float:
            """Metro con coma decimal tolerante; inválido → default."""
            try:
                value = float((texto or "").strip().replace(",", "."))
            except Exception:  # noqa: BLE001 — texto vacío o no numérico
                return default
            return value if value > 0 else default

        def _relevel_form(nombre: str) -> None:
            room = bwiz._find_room(data, nombre)
            if room is None:
                return
            form = tk.Toplevel(dialog)
            form.title(f"Mover «{nombre}» a otro nivel")
            form.configure(background=theme.COL_BG)
            form.transient(dialog)
            form.resizable(False, False)
            ttk.Label(form, text="Nivel destino:", style="Hint.TLabel"
                      ).pack(anchor="w", padx=10, pady=(10, 2))
            combo = ttk.Combobox(form, values=data.level_names(),
                                 state="readonly")
            combo.set(room.level_ref)
            combo.pack(fill="x", padx=10)

            def _ok() -> None:
                _edit_avisos(bwiz.move_room_to_level(
                    data, nombre, combo.get().strip() or room.level_ref))
                form.destroy()

            ttk.Button(form, text="Mover", style="Accent.TButton",
                       command=_ok).pack(fill="x", padx=10, pady=10)
            form.grab_set()

        def _resize_form(room: Any) -> None:
            form = tk.Toplevel(dialog)
            form.title(f"Redimensionar «{room.name}»")
            form.configure(background=theme.COL_BG)
            form.transient(dialog)
            form.resizable(False, False)
            row_w = ttk.Frame(form)
            row_w.pack(fill="x", padx=10, pady=(10, 2))
            ttk.Label(row_w, text="Ancho (m):", style="Hint.TLabel"
                      ).pack(side="left")
            entry_w = ttk.Entry(row_w, width=10)
            entry_w.insert(0, f"{room.width_m:g}")
            entry_w.pack(side="left", padx=(6, 16))
            ttk.Label(row_w, text="Fondo (m):", style="Hint.TLabel"
                      ).pack(side="left")
            entry_d = ttk.Entry(row_w, width=10)
            entry_d.insert(0, f"{room.depth_m:g}")
            entry_d.pack(side="left", padx=6)

            def _ok() -> None:
                _edit_avisos(bwiz.resize_room(
                    data, room.name,
                    _parse_m(entry_w.get(), room.width_m),
                    _parse_m(entry_d.get(), room.depth_m)))
                form.destroy()

            ttk.Button(form, text="Aplicar", style="Accent.TButton",
                       command=_ok).pack(fill="x", padx=10, pady=10)
            form.grab_set()

        def _add_form() -> None:
            form = tk.Toplevel(dialog)
            form.title("Añadir local nuevo")
            form.configure(background=theme.COL_BG)
            form.transient(dialog)
            form.resizable(False, False)
            dna_types = ["ROOM"]
            try:
                dna_types += [t for t in self.ctx.dna_registry.types()
                              if t != "ROOM"]
            except Exception:  # noqa: BLE001 — sin DNA, solo ROOM
                pass
            ttk.Label(form, text="Nombre:", style="Hint.TLabel"
                      ).pack(anchor="w", padx=10, pady=(10, 0))
            entry_name = ttk.Entry(form, width=28)
            entry_name.pack(fill="x", padx=10)
            row1 = ttk.Frame(form)
            row1.pack(fill="x", padx=10, pady=(6, 0))
            ttk.Label(row1, text="Tipo:", style="Hint.TLabel"
                      ).pack(side="left")
            combo_type = ttk.Combobox(row1, values=dna_types,
                                      state="readonly")
            combo_type.set("ROOM")
            combo_type.pack(side="left", padx=(6, 16))
            ttk.Label(row1, text="Nivel:", style="Hint.TLabel"
                      ).pack(side="left")
            combo_level = ttk.Combobox(row1, values=data.level_names(),
                                       state="readonly")
            combo_level.set(data.level_names()[0] if data.level_names()
                            else "Planta Baja")
            combo_level.pack(side="left", padx=6)
            row2 = ttk.Frame(form)
            row2.pack(fill="x", padx=10, pady=(6, 0))
            ttk.Label(row2, text="Ancho (m):", style="Hint.TLabel"
                      ).pack(side="left")
            entry_w = ttk.Entry(row2, width=8)
            entry_w.insert(0, "3.0")
            entry_w.pack(side="left", padx=(6, 16))
            ttk.Label(row2, text="Fondo (m):", style="Hint.TLabel"
                      ).pack(side="left")
            entry_d = ttk.Entry(row2, width=8)
            entry_d.insert(0, "3.0")
            entry_d.pack(side="left", padx=6)

            def _ok() -> None:
                nombre = entry_name.get().strip()
                if not nombre:
                    messagebox.showwarning(
                        "Añadir local", "El local necesita un nombre.",
                        parent=form)
                    return
                _edit_avisos(bwiz.add_room(data, bwiz.RoomSpec(
                    name=nombre, space_type=combo_type.get(),
                    width_m=max(0.5, _parse_m(entry_w.get(), 3.0)),
                    depth_m=max(0.5, _parse_m(entry_d.get(), 3.0)),
                    level_ref=combo_level.get())))
                form.destroy()

            ttk.Button(form, text="Añadir al programa",
                       style="Accent.TButton", command=_ok
                       ).pack(fill="x", padx=10, pady=10)
            form.grab_set()

        # -- ganchos de prueba + arranque -----------------------------------
        dialog._regen_data = data
        dialog._regen_state = state
        dialog._regen_tree = tree
        dialog._regen_variant_tree = variant_tree
        dialog._regen_canvas = canvas
        dialog._regen_refresh = _regen_refresh
        dialog._regen_refresh_variants = _regen_refresh_variants
        dialog._regen_generate = _regen_generate
        dialog._regen_apply = _regen_apply
        dialog._regen_choose_variant = _regen_choose
        dialog._regen_calidad = calidad_combo
        dialog._regen_calidad_var = calidad_var
        dialog._regen_recostear = _regen_on_calidad
        dialog._regen_png_costes = _regen_png_costes
        tree.bind("<Double-1>", lambda _e: _regen_resize())
        variant_tree.bind("<<TreeviewSelect>>", _regen_choose)
        canvas.bind("<Configure>", lambda _e: _regen_draw())
        _regen_refresh()
        for aviso in avisos:
            self._say(aviso)
        self._say("Regenerar edificación: mueve, añade, quita o "
                  "redimensiona locales, genera variantes y sustituye; "
                  "nada queda huérfano.")

    def open_diseno_dialog(self) -> None:
        """Concepción de espacios (v3.15.0 + v3.18.0 + v3.19.0): el taller de
        MOBILIARIO, CUBIERTAS, ACCESIBILIDAD, ASCENSORES, FACHADA
        (parasoles y pieles), ESCALERAS, ABERTURAS, ILUMINACIÓN y
        ALARMAS sobre la edificación generada.

        Nueve pestañas sobre los motores puros de domain/ (mismos
        caminos oficiales: auditoría, undo persistente, QTO e
        invalidación). Cada acción confirma al terminar y revierte con
        aviso amable si algo falla; después refresca el lienzo, donde
        el mobiliario, la cubierta, las rampas, las barandillas, el
        hueco del ascensor, las lamas, las pieles, la escalera y los
        símbolos de vanos ya se dibujan.
        """
        from domain import accesibilidad as dis_acc
        from domain import alarmas as alr_mod
        from domain import aberturas as dis_abe
        from domain import ascensores as dis_asc
        from domain import cubiertas as dis_cub
        from domain import escaleras as dis_esc
        from domain import fachadas as dis_fac
        from domain import iluminacion as dis_ilu
        from domain import mobiliario as dis_mob
        dialog = tk.Toplevel(self)
        self._diseno_dialog = dialog
        dialog.title("Concepción de espacios (mobiliario, cubiertas, "
                     "accesibilidad, ascensores, fachada, escaleras, "
                     "aberturas, iluminación y alarmas)")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "diseno_espacios")

        niveles = self.ctx.architecture.list("LEVEL", self.ctx.project.id)
        niveles.sort(key=lambda lv: (lv.elevation_m, lv.name))
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        # locales protegibles para la pestaña de alarmas (v3.19.0)
        alr_datos = {"locales": alr_mod.locales_protegibles(self.ctx)}

        # ================= pestaña MOBILIARIO ============================
        tab_mob = ttk.Frame(notebook, padding=(12, 10))
        notebook.add(tab_mob, text="🛋 Mobiliario")
        ttk.Label(tab_mob,
                  text="Amuebla los locales según su uso: el TEMA (uso "
                       "social/doméstico) elige el catálogo, la DENSIDAD "
                       "añade piezas cómodas y las reglas respetan el "
                       "paso entre muebles. Lo editado a mano sobrevive.",
                  style="Hint.TLabel", wraplength=640,
                  justify="left").pack(fill="x", pady=(0, 8))
        fila_amb = ttk.Frame(tab_mob)
        fila_amb.pack(fill="x", pady=2)
        ttk.Label(fila_amb, text="Tema:").pack(side="left")
        combo_ambito = ttk.Combobox(
            fila_amb, state="readonly", width=26,
            values=("auto (según el uso social)",) + dis_mob.AMBITOS[1:])
        combo_ambito.current(0)
        combo_ambito.pack(side="left", padx=(4, 12))
        ttk.Label(fila_amb, text="Densidad:").pack(side="left")
        combo_dens = ttk.Combobox(fila_amb, state="readonly", width=11,
                                  values=dis_mob.DENSIDADES)
        combo_dens.set(dis_mob.DENSIDADES[1])
        combo_dens.pack(side="left", padx=4)
        ttk.Label(fila_amb, text="Nivel:").pack(side="left", padx=(12, 0))
        combo_nivel_mob = ttk.Combobox(fila_amb, state="readonly", width=16,
                                       values=["(todos)"] +
                                       [lv.name for lv in niveles])
        combo_nivel_mob.current(0)
        combo_nivel_mob.pack(side="left", padx=4)
        salida_mob = tk.Text(tab_mob, height=14, wrap="word",
                             background=theme.get("canvas"),
                             foreground=theme.get("text"),
                             relief="flat")
        salida_mob.pack(fill="both", expand=True, pady=(8, 4))

        def _mobiliario_generar_envoltura() -> None:
            ambito = "" if combo_ambito.current() == 0 \
                else dis_mob.AMBITOS[1:][combo_ambito.current() - 1]
            nivel_id = ""
            if combo_nivel_mob.current() > 0:
                nivel_id = niveles[combo_nivel_mob.current() - 1].id
            try:
                resumen = dis_mob.generar_mobiliario(
                    self.ctx, None, ambito=ambito or "auto",
                    densidad=combo_dens.get(), nivel_id=nivel_id)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Mobiliario", str(exc), parent=dialog)
                return
            self.refresh_all()
            lineas = [dis_mob.resumen_texto(resumen), "",
                      f"Piezas creadas: {len(resumen.get('creados', []))}",
                      f"Bajas de pasadas anteriores: "
                      f"{len(resumen.get('eliminados', []))}"]
            conteo = resumen.get("conteo") or {}
            if conteo:
                lineas.append("Conteo por tipo:")
                lineas += [f"  {clave}: {n}"
                           for clave, n in sorted(conteo.items())]
            lineas.append("Avisos:")
            lineas += [f"  {a}" for a in resumen.get("avisos", [])] \
                or ["  (ninguno)"]
            self._diseno_pinta(salida_mob, lineas)
            self._say(dis_mob.resumen_texto(resumen),
                      "Ctrl+Z deshace paso a paso")

        def _mobiliario_quitar() -> None:
            try:
                bajas = dis_mob.quitar_mobiliario(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Mobiliario", str(exc), parent=dialog)
                return
            self.refresh_all()
            self._diseno_pinta(salida_mob, [
                f"Mobiliario generado retirado: {len(bajas)} pieza(s).",
                "Lo editado a mano se conserva."])
            self._say(f"Mobiliario retirado: {len(bajas)} pieza(s).", "")

        fila_btn_mob = ttk.Frame(tab_mob)
        fila_btn_mob.pack(fill="x", pady=(2, 0))
        self._tip(ttk.Button(fila_btn_mob,
                             text=icons.label("mobiliario", "Amueblar"),
                             style="Accent.TButton",
                             command=_mobiliario_generar_envoltura),
                  "mobiliario").pack(side="left")
        self._tip(ttk.Button(fila_btn_mob, text="🗑 Quitar generados",
                             command=_mobiliario_quitar),
                  "mobiliario_quitar").pack(side="left", padx=6)

        # ================= pestaña CUBIERTAS =============================
        tab_cub = ttk.Frame(notebook, padding=(12, 10))
        notebook.add(tab_cub, text="⌂ Cubiertas")
        ttk.Label(tab_cub,
                  text="Cubre la edificación: el ESTILO arquitectónico "
                       "sugiere tipología y material («auto»); puedes "
                       "fijarlos a mano con pendiente y alero propios. La "
                       "superficie real sale con la pendiente y entra en "
                       "QTO y en el estimador paramétrico.",
                  style="Hint.TLabel", wraplength=640,
                  justify="left").pack(fill="x", pady=(0, 8))
        fila_cub1 = ttk.Frame(tab_cub)
        fila_cub1.pack(fill="x", pady=2)
        ttk.Label(fila_cub1, text="Tipología:").pack(side="left")
        combo_tip = ttk.Combobox(fila_cub1, state="readonly", width=22,
                                 values=dis_cub.TIPOLOGIAS)
        combo_tip.set("auto")
        combo_tip.pack(side="left", padx=4)
        ttk.Label(fila_cub1, text="Material:").pack(side="left", padx=(10, 0))
        combo_mat = ttk.Combobox(fila_cub1, state="readonly", width=22,
                                 values=dis_cub.MATERIALES)
        combo_mat.set("auto")
        combo_mat.pack(side="left", padx=4)
        fila_cub2 = ttk.Frame(tab_cub)
        fila_cub2.pack(fill="x", pady=2)
        ttk.Label(fila_cub2, text="Pendiente % (0 = según estilo):"
                  ).pack(side="left")
        var_pend = tk.StringVar(value="0")
        ttk.Entry(fila_cub2, textvariable=var_pend, width=7).pack(
            side="left", padx=4)
        ttk.Label(fila_cub2, text="Alero m (0 = el del asistente):"
                  ).pack(side="left", padx=(10, 0))
        var_alero = tk.StringVar(value="0")
        ttk.Entry(fila_cub2, textvariable=var_alero, width=7).pack(
            side="left", padx=4)
        ttk.Label(fila_cub2, text="Estructura:").pack(side="left",
                                                      padx=(10, 0))
        combo_est = ttk.Combobox(fila_cub2, state="readonly", width=11,
                                 values=dis_cub.ESTRUCTURAS)
        combo_est.set("auto")
        combo_est.pack(side="left", padx=4)
        fila_cub3 = ttk.Frame(tab_cub)
        fila_cub3.pack(fill="x", pady=2)
        ttk.Label(fila_cub3, text="Cota de base m (0 = sobre los muros; "
                  "v3.17.0 la coloca al nivel que pidas):").pack(side="left")
        var_cota = tk.StringVar(value="0")
        ttk.Entry(fila_cub3, textvariable=var_cota, width=7).pack(
            side="left", padx=4)
        salida_cub = tk.Text(tab_cub, height=13, wrap="word",
                             background=theme.get("canvas"),
                             foreground=theme.get("text"), relief="flat")
        salida_cub.pack(fill="both", expand=True, pady=(8, 4))

        def _cubierta_generar() -> None:
            try:
                pendiente = float(str(var_pend.get()).replace(",", ".")
                                  or "0")
                alero = float(str(var_alero.get()).replace(",", ".") or "0")
                cota = float(str(var_cota.get()).replace(",", ".") or "0")
            except ValueError:
                messagebox.showerror(
                    "Cubierta", "Pendiente, alero y cota deben ser números "
                    "(coma o punto).", parent=dialog)
                return
            try:
                resumen = dis_cub.generar_cubierta(
                    self.ctx, None, tipologia=combo_tip.get(),
                    material=combo_mat.get(), pendiente_pct=pendiente,
                    alero_m=alero or None, estructura=combo_est.get(),
                    altura_base_m=cota or None)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Cubierta", str(exc), parent=dialog)
                return
            self.refresh_all()
            lineas = [dis_cub.resumen_texto(resumen), ""]
            parametros = resumen.get("parametros") or {}
            if parametros:
                lineas += [
                    f"Tipología: {parametros.get('tipologia')}",
                    f"Material: {parametros.get('material')}",
                    f"Pendiente: {parametros.get('pendiente_pct')} %",
                    f"Alero: {parametros.get('alero_m')} m",
                    f"Estructura: {parametros.get('estructura')} "
                    f"({dis_cub.ETIQUETA_ESTRUCTURA.get(parametros.get('estructura'), '')})",
                    "Cota de base: "
                    + (f"{parametros.get('altura_base_m')} m"
                       if parametros.get("altura_base_m")
                       else "sobre los muros (auto)")]
            superficie = resumen.get("superficie") or {}
            if superficie:
                lineas += [
                    f"Superficie real (con pendiente): "
                    f"{superficie.get('area_inclinada')} m2",
                    f"Proyección en planta: "
                    f"{superficie.get('area_proyectada')} m2",
                    f"Perímetro del alero: {superficie.get('perimetro')} m"]
            lineas += ["Avisos:"] + [f"  {a}" for a in
                                     resumen.get("avisos", [])] \
                or ["  (ninguno)"]
            self._diseno_pinta(salida_cub, lineas)
            self._say(dis_cub.resumen_texto(resumen),
                      "El PNG de la vista 3D la incluye de serie")

        def _cubierta_quitar() -> None:
            try:
                bajas = dis_cub.quitar_cubierta(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Cubierta", str(exc), parent=dialog)
                return
            self.refresh_all()
            self._diseno_pinta(salida_cub, [
                f"Cubierta retirada: {len(bajas)} entidad(es)."])
            self._say(f"Cubierta retirada: {len(bajas)}.", "")

        fila_btn_cub = ttk.Frame(tab_cub)
        fila_btn_cub.pack(fill="x", pady=(2, 0))
        self._tip(ttk.Button(fila_btn_cub, text=icons.label("cubiertas",
                                                            "Cubrir"),
                             style="Accent.TButton",
                             command=_cubierta_generar),
                  "cubiertas").pack(side="left")
        self._tip(ttk.Button(fila_btn_cub, text="🗑 Quitar cubierta",
                             command=_cubierta_quitar),
                  "cubiertas_quitar").pack(side="left", padx=6)

        # ================= pestaña ACCESIBILIDAD =========================
        tab_acc = ttk.Frame(notebook, padding=(12, 10))
        notebook.add(tab_acc, text="♿ Accesibilidad")
        ttk.Label(tab_acc,
                  text="Audita las barreras arquitectónicas (puertas, "
                       "pasillos, escaleras, desniveles y giro en aseos) "
                       "y APLICA soluciones reales: barandillas de "
                       "escalera a 0.90 m, rampas con pendiente normativa "
                       "y pasamanos doble (0.95 + 0.65 m), y barras de "
                       "apoyo junto a los inodoros.",
                  style="Hint.TLabel", wraplength=640,
                  justify="left").pack(fill="x", pady=(0, 8))
        salida_acc = tk.Text(tab_acc, height=16, wrap="word",
                             background=theme.get("canvas"),
                             foreground=theme.get("text"), relief="flat")
        salida_acc.pack(fill="both", expand=True, pady=(0, 4))

        def _acc_analizar() -> None:
            chequeos = dis_acc.analizar_barreras(self.ctx)
            lineas = [c.linea() for c in chequeos]
            if any(c.estado != "cumple" for c in chequeos):
                lineas += ["", "Pulsa «Aplicar soluciones» para generar "
                               "barandillas, rampas y barras de apoyo."]
            self._diseno_pinta(salida_acc, lineas or ["Sin datos aún."])
            malos = sum(1 for c in chequeos if c.estado == "incumple")
            avisos = sum(1 for c in chequeos if c.estado == "aviso")
            self._say(f"Análisis de accesibilidad: {malos} incumplimiento(s), "
                      f"{avisos} aviso(s).", "")

        def _acc_aplicar() -> None:
            try:
                resumen = dis_acc.aplicar_soluciones(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Accesibilidad", str(exc),
                                     parent=dialog)
                return
            self.refresh_all()
            lineas = [dis_acc.resumen_texto(resumen), "",
                      f"Piezas creadas: {len(resumen.get('creados', []))}",
                      "Chequeos tras aplicar:"]
            lineas += [f"  {c}" for c in resumen.get("chequeos", [])]
            lineas += ["Avisos:"] + [f"  {a}" for a in
                                     resumen.get("avisos", [])] \
                or ["  (ninguno)"]
            self._diseno_pinta(salida_acc, lineas)
            self._say(dis_acc.resumen_texto(resumen),
                      "Ctrl+Z deshace paso a paso")

        def _acc_quitar() -> None:
            try:
                bajas = dis_acc.quitar_soluciones(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Accesibilidad", str(exc),
                                     parent=dialog)
                return
            self.refresh_all()
            total = len(bajas.get("RAMP", [])) + len(bajas.get("HANDRAIL", []))
            self._diseno_pinta(salida_acc, [
                f"Soluciones generadas retiradas: {total} pieza(s).",
                "Lo editado a mano se conserva."])
            self._say(f"Soluciones retiradas: {total}.", "")

        fila_btn_acc = ttk.Frame(tab_acc)
        fila_btn_acc.pack(fill="x", pady=(2, 0))
        self._tip(ttk.Button(fila_btn_acc, text="♿ Analizar barreras",
                             command=_acc_analizar),
                  "accesibilidad_analizar").pack(side="left")
        self._tip(ttk.Button(fila_btn_acc, text="🛠 Aplicar soluciones",
                             style="Accent.TButton", command=_acc_aplicar),
                  "accesibilidad_aplicar").pack(side="left", padx=6)
        self._tip(ttk.Button(fila_btn_acc, text="🗑 Quitar soluciones",
                             command=_acc_quitar),
                  "accesibilidad_quitar").pack(side="left", padx=6)

        # ================= pestaña ASCENSORES (v3.18.0) ==================
        tab_asc = ttk.Frame(notebook, padding=(12, 10))
        notebook.add(tab_asc, text="🛗 Ascensores")
        ttk.Label(tab_asc,
                  text="Levanta el hueco del ascensor con las TABLAS DE "
                       "NEUFERT: la cabina mide por las personas que "
                       "lleva, el hueco la envuelve con sus guías y el "
                       "foso la recibe abajo. Se mete dentro de un "
                       "núcleo o escalera (puerta al pasillo) o se "
                       "adosa a la fachada que pidas.",
                  style="Hint.TLabel", wraplength=640,
                  justify="left").pack(fill="x", pady=(0, 8))
        fila_asc1 = ttk.Frame(tab_asc)
        fila_asc1.pack(fill="x", pady=2)
        ttk.Label(fila_asc1, text="Tipo:").pack(side="left")
        combo_asc_tipo = ttk.Combobox(fila_asc1, state="readonly",
                                      width=26,
                                      values=tuple(
                                          "auto (de pasajeros)",)
                                      + dis_asc.TIPOS)
        combo_asc_tipo.current(0)
        combo_asc_tipo.pack(side="left", padx=4)
        ttk.Label(fila_asc1, text="Personas:").pack(side="left",
                                                    padx=(10, 0))
        var_asc_personas = tk.StringVar(value="8")
        ttk.Entry(fila_asc1, textvariable=var_asc_personas,
                  width=5).pack(side="left", padx=4)
        ttk.Label(fila_asc1, text="Fachada (vacío = auto):").pack(
            side="left", padx=(10, 0))
        var_asc_fachada = tk.StringVar(value="")
        ttk.Entry(fila_asc1, textvariable=var_asc_fachada,
                  width=5).pack(side="left", padx=4)
        salida_asc = tk.Text(tab_asc, height=14, wrap="word",
                             background=theme.get("canvas"),
                             foreground=theme.get("text"), relief="flat")
        salida_asc.pack(fill="both", expand=True, pady=(8, 4))

        def _ascensores_generar() -> None:
            try:
                personas = int(str(var_asc_personas.get()).strip() or "8")
            except ValueError:
                messagebox.showerror(
                    "Ascensores", "Las personas deben ser un número "
                    "entero.", parent=dialog)
                return
            tipo = "" if combo_asc_tipo.current() == 0 \
                else dis_asc.TIPOS[combo_asc_tipo.current() - 1]
            fachada = str(var_asc_fachada.get()).strip().upper()
            try:
                resumen = dis_asc.generar_ascensor(
                    self.ctx, None, tipo=tipo or "pasajeros",
                    personas=personas,
                    fachada=fachada if fachada in ("N", "S", "E", "O")
                    else "")
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Ascensores", str(exc), parent=dialog)
                return
            self.refresh_all()
            lineas = [dis_asc.resumen_texto(resumen), ""]
            parametros = resumen.get("parametros") or {}
            if parametros:
                cabina = parametros.get("cabina") or (0.0, 0.0)
                hueco = parametros.get("hueco") or (0.0, 0.0)
                lineas += [
                    f"Capacidad: {parametros.get('capacidad_kg')} kg "
                    f"({parametros.get('personas')} personas)",
                    f"Cabina: {cabina[0]:.2f} x {cabina[1]:.2f} m",
                    f"Hueco: {hueco[0]:.2f} x {hueco[1]:.2f} m",
                    f"Puerta central: {parametros.get('puerta_m'):.2f} m",
                    f"Foso: {parametros.get('foso_m'):.2f} m · paso "
                    f"libre superior: "
                    f"{parametros.get('paso_libre_superior_m'):.2f} m",
                    f"Velocidad de referencia: "
                    f"{parametros.get('velocidad_m_s'):.2f} m/s",
                    f"Niveles servidos: "
                    f"{parametros.get('niveles_servidos')} · recorrido "
                    f"{parametros.get('altura_total_m'):.1f} m",
                    "Sitio: " + str(parametros.get("modo", ""))]
            lineas += ["", "Avisos:"] + [f"  {a}" for a in
                                         resumen.get("avisos", [])] \
                or ["  (ninguno)"]
            lineas += [""] + dis_asc.tabla_texto(
                (parametros or {}).get("tipo", "pasajeros"))
            self._diseno_pinta(salida_asc, lineas)
            self._say(dis_asc.resumen_texto(resumen),
                      "Ctrl+Z deshace paso a paso")

        def _ascensores_quitar() -> None:
            try:
                bajas = dis_asc.quitar_ascensores(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Ascensores", str(exc), parent=dialog)
                return
            self.refresh_all()
            self._diseno_pinta(salida_asc, [
                f"Ascensores generados retirados: {len(bajas)} hueco(s)."])
            self._say(f"Ascensores retirados: {len(bajas)}.", "")

        fila_btn_asc = ttk.Frame(tab_asc)
        fila_btn_asc.pack(fill="x", pady=(2, 0))
        self._tip(ttk.Button(fila_btn_asc,
                             text=icons.label("ascensores",
                                              "Levantar hueco"),
                             style="Accent.TButton",
                             command=_ascensores_generar),
                  "ascensores").pack(side="left")
        self._tip(ttk.Button(fila_btn_asc, text="🗑 Quitar generados",
                             command=_ascensores_quitar),
                  "ascensores_quitar").pack(side="left", padx=6)

        # ================= pestaña FACHADA (v3.18.0) =====================
        tab_fac = ttk.Frame(notebook, padding=(12, 10))
        notebook.add(tab_fac, text="🌤 Fachada")
        ttk.Label(tab_fac,
                  text="Viste la fachada en DOS capas: PARASOLES por "
                       "orientación (lamas horizontales al sur, aletas "
                       "verticales a este y oeste; al norte no hacen "
                       "falta) y la PIEL EXTERIOR moderna (doble piel "
                       "de vidrio, celosía de madera, malla metálica, "
                       "terracota, panel perforado, jardín vertical, "
                       "GRC o policarbonato) con su cámara ventilada.",
                  style="Hint.TLabel", wraplength=640,
                  justify="left").pack(fill="x", pady=(0, 8))
        fila_par1 = ttk.Frame(tab_fac)
        fila_par1.pack(fill="x", pady=2)
        ttk.Label(fila_par1, text="Parasol:").pack(side="left")
        combo_par_tipo = ttk.Combobox(fila_par1, state="readonly",
                                      width=16,
                                      values=dis_fac.TIPOS_PARASOL)
        combo_par_tipo.set("auto")
        combo_par_tipo.pack(side="left", padx=4)
        ttk.Label(fila_par1, text="Material:").pack(side="left",
                                                    padx=(8, 0))
        combo_par_mat = ttk.Combobox(fila_par1, state="readonly",
                                     width=14,
                                     values=dis_fac.MATERIALES_PARASOL)
        combo_par_mat.set("auto")
        combo_par_mat.pack(side="left", padx=4)
        ttk.Label(fila_par1, text="Lados:").pack(side="left",
                                                 padx=(8, 0))
        var_fac_lados = tk.StringVar(value="auto")
        ttk.Entry(fila_par1, textvariable=var_fac_lados,
                  width=8).pack(side="left", padx=4)
        fila_par2 = ttk.Frame(tab_fac)
        fila_par2.pack(fill="x", pady=2)
        ttk.Label(fila_par2, text="Vuelo m (0 = 0.50):").pack(side="left")
        var_par_vuelo = tk.StringVar(value="0")
        ttk.Entry(fila_par2, textvariable=var_par_vuelo,
                  width=6).pack(side="left", padx=4)
        ttk.Label(fila_par2, text="Separación m (0 = 0.60):").pack(
            side="left", padx=(10, 0))
        var_par_sep = tk.StringVar(value="0")
        ttk.Entry(fila_par2, textvariable=var_par_sep,
                  width=6).pack(side="left", padx=4)
        ttk.Label(tab_fac, text="─" * 60).pack(fill="x", pady=(6, 2))
        fila_piel1 = ttk.Frame(tab_fac)
        fila_piel1.pack(fill="x", pady=2)
        ttk.Label(fila_piel1, text="Piel:").pack(side="left")
        combo_piel_tipo = ttk.Combobox(fila_piel1, state="readonly",
                                       width=22, values=dis_fac.TIPOS_PIEL)
        combo_piel_tipo.set("auto")
        combo_piel_tipo.pack(side="left", padx=4)
        ttk.Label(fila_piel1, text="Cámara m (0 = 0.60):").pack(
            side="left", padx=(8, 0))
        var_piel_sep = tk.StringVar(value="0")
        ttk.Entry(fila_piel1, textvariable=var_piel_sep,
                  width=6).pack(side="left", padx=4)
        ttk.Label(fila_piel1, text="Lados:").pack(side="left",
                                                  padx=(8, 0))
        var_piel_lados = tk.StringVar(value="auto")
        ttk.Entry(fila_piel1, textvariable=var_piel_lados,
                  width=8).pack(side="left", padx=4)
        salida_fac = tk.Text(tab_fac, height=10, wrap="word",
                             background=theme.get("canvas"),
                             foreground=theme.get("text"), relief="flat")
        salida_fac.pack(fill="both", expand=True, pady=(8, 4))

        def _parasoles_generar() -> None:
            try:
                vuelo = float(str(var_par_vuelo.get()).replace(",", ".")
                              or "0")
                sep = float(str(var_par_sep.get()).replace(",", ".") or "0")
            except ValueError:
                messagebox.showerror(
                    "Fachada", "Vuelo y separación deben ser números "
                    "(coma o punto).", parent=dialog)
                return
            try:
                resumen = dis_fac.generar_parasoles(
                    self.ctx, None, lados=str(var_fac_lados.get()).strip(),
                    tipo=combo_par_tipo.get(), material=combo_par_mat.get(),
                    profundidad_m=vuelo, separacion_m=sep)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Fachada", str(exc), parent=dialog)
                return
            self.refresh_all()
            lineas = [dis_fac.resumen_texto_parasoles(resumen), ""]
            for d in (resumen.get("parametros") or {}).get(
                    "lados_resueltos", []):
                lineas.append(
                    f"  {dis_fac.ETIQUETA_LADO.get(d['lado'], d['lado'])}: "
                    f"{dis_fac.ETIQUETA_PARASOL.get(d['tipo'], d['tipo'])}"
                    f" · {d['n_lamas']} lamas · {d['length_m']} m de "
                    f"fachada · banda {d['altura'][0]:.2f}-"
                    f"{d['altura'][1]:.2f} m")
            lineas += ["Avisos:"] + [f"  {a}" for a in
                                     resumen.get("avisos", [])] \
                or ["  (ninguno)"]
            self._diseno_pinta(salida_fac, lineas)
            self._say(dis_fac.resumen_texto_parasoles(resumen),
                      "El 3D dibuja las lamas con su material")

        def _parasoles_quitar() -> None:
            try:
                bajas = dis_fac.quitar_parasoles(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Fachada", str(exc), parent=dialog)
                return
            self.refresh_all()
            self._diseno_pinta(salida_fac, [
                f"Parasoles generados retirados: {len(bajas)} pieza(s)."])
            self._say(f"Parasoles retirados: {len(bajas)}.", "")

        def _piel_generar() -> None:
            try:
                sep = float(str(var_piel_sep.get()).replace(",", ".")
                            or "0")
            except ValueError:
                messagebox.showerror(
                    "Fachada", "La cámara debe ser un número (coma o "
                    "punto).", parent=dialog)
                return
            try:
                resumen = dis_fac.generar_piel(
                    self.ctx, None, lados=str(var_piel_lados.get()).strip(),
                    tipo=combo_piel_tipo.get(), separacion_m=sep)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Fachada", str(exc), parent=dialog)
                return
            self.refresh_all()
            lineas = [dis_fac.resumen_texto_piel(resumen), ""]
            parametros = resumen.get("parametros") or {}
            for d in parametros.get("lados_resueltos", []):
                lineas.append(
                    f"  {dis_fac.ETIQUETA_LADO.get(d['lado'], d['lado'])}: "
                    f"{d['length_m']} m x {d['altura_m']} m de piel")
            apertura = parametros.get("apertura_pct")
            if apertura is not None:
                lineas.append(f"  apertura/aire libre: {apertura} %")
            lineas += ["Avisos:"] + [f"  {a}" for a in
                                     resumen.get("avisos", [])] \
                or ["  (ninguno)"]
            self._diseno_pinta(salida_fac, lineas)
            self._say(dis_fac.resumen_texto_piel(resumen),
                      "El estilo arquitectónico sugiere la piel en auto")

        def _piel_quitar() -> None:
            try:
                bajas = dis_fac.quitar_pieles(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Fachada", str(exc), parent=dialog)
                return
            self.refresh_all()
            self._diseno_pinta(salida_fac, [
                f"Pieles generadas retiradas: {len(bajas)} plano(s)."])
            self._say(f"Pieles retiradas: {len(bajas)}.", "")

        fila_btn_fac = ttk.Frame(tab_fac)
        fila_btn_fac.pack(fill="x", pady=(2, 0))
        self._tip(ttk.Button(fila_btn_fac,
                             text=icons.label("parasoles",
                                              "Poner parasoles"),
                             style="Accent.TButton",
                             command=_parasoles_generar),
                  "parasoles").pack(side="left")
        self._tip(ttk.Button(fila_btn_fac, text="🗑 Quitar parasoles",
                             command=_parasoles_quitar),
                  "parasoles_quitar").pack(side="left", padx=6)
        self._tip(ttk.Button(fila_btn_fac,
                             text=icons.label("piel", "Envolver con piel"),
                             style="Accent.TButton",
                             command=_piel_generar),
                  "piel").pack(side="left", padx=(12, 0))
        self._tip(ttk.Button(fila_btn_fac, text="🗑 Quitar piel",
                             command=_piel_quitar),
                  "piel_quitar").pack(side="left", padx=6)

        # ================= pestaña ESCALERAS (v3.19.0) ===================
        tab_esc = ttk.Frame(notebook, padding=(12, 10))
        notebook.add(tab_esc, text="🪜 Escaleras")
        ttk.Label(tab_esc,
                  text="Levanta la escalera por su TIPOLOGÍA: recta, en L, "
                       "en U (doble piso) o de caracol, con la fórmula de "
                       "BLONDEL del libro (2h + p = 0.60-0.64 m), meseta "
                       "cada 16 contrahuellas y la planta real dibujada "
                       "(contorno, huellas y peldaños en 3D). Busca hueco "
                       "en un recinto de escalera o núcleo.",
                  style="Hint.TLabel", wraplength=640,
                  justify="left").pack(fill="x", pady=(0, 8))
        fila_esc1 = ttk.Frame(tab_esc)
        fila_esc1.pack(fill="x", pady=2)
        ttk.Label(fila_esc1, text="Tipo:").pack(side="left")
        combo_esc_tipo = ttk.Combobox(fila_esc1, state="readonly",
                                      width=30, values=dis_esc.TIPOS)
        combo_esc_tipo.set("recta")
        combo_esc_tipo.pack(side="left", padx=4)
        ttk.Label(fila_esc1, text="Nivel:").pack(side="left", padx=(10, 0))
        combo_nivel_esc = ttk.Combobox(fila_esc1, state="readonly",
                                       width=16,
                                       values=[lv.name for lv in niveles])
        if niveles:
            combo_nivel_esc.current(0)
        combo_nivel_esc.pack(side="left", padx=4)
        fila_esc2 = ttk.Frame(tab_esc)
        fila_esc2.pack(fill="x", pady=2)
        ttk.Label(fila_esc2, text="Desnivel m (0 = altura del nivel):"
                  ).pack(side="left")
        var_esc_desnivel = tk.StringVar(value="0")
        ttk.Entry(fila_esc2, textvariable=var_esc_desnivel,
                  width=7).pack(side="left", padx=4)
        ttk.Label(fila_esc2, text="Contrahuella m (0 = auto):").pack(
            side="left", padx=(10, 0))
        var_esc_h = tk.StringVar(value="0")
        ttk.Entry(fila_esc2, textvariable=var_esc_h,
                  width=7).pack(side="left", padx=4)
        ttk.Label(fila_esc2, text="Huella m (0 = Blondel):").pack(
            side="left", padx=(10, 0))
        var_esc_p = tk.StringVar(value="0")
        ttk.Entry(fila_esc2, textvariable=var_esc_p,
                  width=7).pack(side="left", padx=4)
        fila_esc3 = ttk.Frame(tab_esc)
        fila_esc3.pack(fill="x", pady=2)
        ttk.Label(fila_esc3, text="Ancho m (0 = 1.10):").pack(side="left")
        var_esc_ancho = tk.StringVar(value="0")
        ttk.Entry(fila_esc3, textvariable=var_esc_ancho,
                  width=7).pack(side="left", padx=4)
        ttk.Label(fila_esc3, text="Giro grados (0/90/180/270):").pack(
            side="left", padx=(10, 0))
        var_esc_rot = tk.StringVar(value="0")
        ttk.Entry(fila_esc3, textvariable=var_esc_rot,
                  width=6).pack(side="left", padx=4)
        salida_esc = tk.Text(tab_esc, height=12, wrap="word",
                             background=theme.get("canvas"),
                             foreground=theme.get("text"), relief="flat")
        salida_esc.pack(fill="both", expand=True, pady=(8, 4))

        def _escalera_generar() -> None:
            try:
                desnivel = float(str(var_esc_desnivel.get()).replace(
                    ",", ".") or "0")
                h = float(str(var_esc_h.get()).replace(",", ".") or "0")
                p = float(str(var_esc_p.get()).replace(",", ".") or "0")
                ancho = float(str(var_esc_ancho.get()).replace(",", ".")
                              or "0")
                rot = float(str(var_esc_rot.get()).replace(",", ".")
                            or "0")
            except ValueError:
                messagebox.showerror(
                    "Escaleras", "Desnivel, contrahuella, huella, ancho y "
                    "giro deben ser números (coma o punto).", parent=dialog)
                return
            nivel_id = ""
            if combo_nivel_esc.current() >= 0 and niveles:
                nivel_id = niveles[combo_nivel_esc.current()].id
            try:
                resumen = dis_esc.generar_escalera(
                    self.ctx, None, tipo=combo_esc_tipo.get(),
                    desnivel_m=desnivel or None,
                    contrahuella_m=h or None, huella_m=p or None,
                    ancho_m=ancho if ancho > 0 else dis_esc.ANCHO_DEFECTO_M,
                    rot_deg=rot, nivel_id=nivel_id)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Escaleras", str(exc), parent=dialog)
                return
            self.refresh_all()
            lineas = [dis_esc.resumen_texto(resumen), ""]
            parametros = resumen.get("parametros") or {}
            if parametros:
                carac = parametros.get("caracol")
                lineas += [
                    f"Tipo: {parametros.get('etiqueta')}",
                    f"Desnivel: {parametros.get('desnivel_m'):.2f} m · "
                    f"{parametros.get('n_contrahuellas')} peldaños",
                    f"Contrahuella: {parametros.get('contrahuella_m'):.3f} m"
                    f" · huella: {parametros.get('huella_m'):.2f} m"
                    f" · Blondel: {parametros.get('blondel_m'):.3f} m"
                    + ("" if parametros.get("blondel_ok")
                       else "  (fuera de rango)"),
                    f"Tramos: {parametros.get('tramos')} · mesetas: "
                    f"{parametros.get('mesetas')} · pendiente: "
                    f"{parametros.get('pendiente_deg'):.0f} grados",
                    f"Desarrollo: {parametros.get('desarrollo_m'):.2f} m · "
                    f"huella en planta: "
                    f"{parametros.get('area_huella_m2'):.2f} m2 · "
                    f"barandilla: {parametros.get('barandilla_m'):.2f} m"]
                if carac:
                    lineas.append(
                        f"Caracol: radio {carac.get('r_exterior_m')} m · "
                        f"{carac.get('giro_peldano_deg')} grados por "
                        f"peldaño · {carac.get('vueltas')} vueltas")
            lineas += ["Avisos:"] + [f"  {a}" for a in
                                     resumen.get("avisos", [])] \
                or ["  (ninguno)"]
            lineas += [""] + dis_esc.tabla_texto()
            self._diseno_pinta(salida_esc, lineas)
            self._say(dis_esc.resumen_texto(resumen),
                      "La planta y el 3D dibujan los peldaños")

        def _escalera_quitar() -> None:
            try:
                bajas = dis_esc.quitar_escaleras(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Escaleras", str(exc), parent=dialog)
                return
            self.refresh_all()
            self._diseno_pinta(salida_esc, [
                f"Escaleras generadas retiradas: {len(bajas)} pieza(s)."])
            self._say(f"Escaleras retiradas: {len(bajas)}.", "")

        fila_btn_esc = ttk.Frame(tab_esc)
        fila_btn_esc.pack(fill="x", pady=(2, 0))
        self._tip(ttk.Button(fila_btn_esc,
                             text=icons.label("escaleras",
                                              "Levantar escalera"),
                             style="Accent.TButton",
                             command=_escalera_generar),
                  "escaleras").pack(side="left")
        self._tip(ttk.Button(fila_btn_esc, text="🗑 Quitar escaleras",
                             command=_escalera_quitar),
                  "escaleras_quitar").pack(side="left", padx=6)

        # ================= pestaña ABERTURAS (v3.19.0) ===================
        tab_abe = ttk.Frame(notebook, padding=(12, 10))
        notebook.add(tab_abe, text="🚪 Aberturas")
        ttk.Label(tab_abe,
                  text="Dale FUNCIONAMIENTO a puertas y ventanas: "
                       "abatible, doble hoja, corredera, plegable, "
                       "vaivén o pivote; practicable, oscilobatiente, "
                       "proyectante, guillotina, fija o pivotante. La "
                       "tipología se aplica a TODAS las del nivel y el "
                       "plano dibuja su símbolo (arco, corredera, "
                       "zigzag).",
                  style="Hint.TLabel", wraplength=640,
                  justify="left").pack(fill="x", pady=(0, 8))
        fila_abe1 = ttk.Frame(tab_abe)
        fila_abe1.pack(fill="x", pady=2)
        ttk.Label(fila_abe1, text="Vanos:").pack(side="left")
        combo_abe_kind = ttk.Combobox(fila_abe1, state="readonly",
                                      width=12, values=("puertas",
                                                        "ventanas"))
        combo_abe_kind.set("puertas")
        combo_abe_kind.pack(side="left", padx=4)
        ttk.Label(fila_abe1, text="Tipo:").pack(side="left", padx=(8, 0))
        combo_abe_tipo = ttk.Combobox(fila_abe1, state="readonly",
                                      width=22,
                                      values=dis_abe.tipos_puerta())
        combo_abe_tipo.set("abatible")
        combo_abe_tipo.pack(side="left", padx=4)
        ttk.Label(fila_abe1, text="Nivel:").pack(side="left", padx=(8, 0))
        combo_nivel_abe = ttk.Combobox(fila_abe1, state="readonly",
                                       width=16,
                                       values=["(todos)"] +
                                       [lv.name for lv in niveles])
        combo_nivel_abe.current(0)
        combo_nivel_abe.pack(side="left", padx=4)
        salida_abe = tk.Text(tab_abe, height=13, wrap="word",
                             background=theme.get("canvas"),
                             foreground=theme.get("text"), relief="flat")
        salida_abe.pack(fill="both", expand=True, pady=(8, 4))

        def _abe_kind_changed(_event=None) -> None:
            if combo_abe_kind.get() == "puertas":
                combo_abe_tipo["values"] = dis_abe.tipos_puerta()
                combo_abe_tipo.set("abatible")
            else:
                combo_abe_tipo["values"] = dis_abe.tipos_ventana()
                combo_abe_tipo.set("practicable")

        combo_abe_kind.bind("<<ComboboxSelected>>", _abe_kind_changed)

        def _abe_aplicar() -> None:
            kind = "DOOR" if combo_abe_kind.get() == "puertas" else "WINDOW"
            nivel_id = ""
            if combo_nivel_abe.current() > 0:
                nivel_id = niveles[combo_nivel_abe.current() - 1].id
            try:
                resumen = dis_abe.asignar_tipos(self.ctx, kind,
                                                combo_abe_tipo.get(),
                                                nivel_id=nivel_id)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Aberturas", str(exc), parent=dialog)
                return
            self.refresh_all()
            lineas = [dis_abe.resumen_texto(resumen), ""]
            for nivel, n in sorted((resumen.get("por_nivel") or {}).items()):
                lineas.append(f"  nivel {nivel}: {n} vano(s)")
            lineas.append("")
            lineas += dis_abe.recuento_texto(dis_abe.resumen_aberturas(
                self.ctx, nivel_id))
            self._diseno_pinta(salida_abe, lineas)
            self._say(dis_abe.resumen_texto(resumen),
                      "El plano dibuja el símbolo del tipo")

        def _abe_quitar() -> None:
            kind = "DOOR" if combo_abe_kind.get() == "puertas" else "WINDOW"
            nivel_id = ""
            if combo_nivel_abe.current() > 0:
                nivel_id = niveles[combo_nivel_abe.current() - 1].id
            try:
                total = dis_abe.quitar_tipos(self.ctx, kind,
                                             nivel_id=nivel_id)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Aberturas", str(exc), parent=dialog)
                return
            self.refresh_all()
            self._diseno_pinta(salida_abe, [
                f"Tipologías retiradas: {total} vano(s).",
                "Los vanos siguen existiendo, sin tipo."])
            self._say(f"Tipologías retiradas: {total}.", "")

        def _abe_recuento() -> None:
            nivel_id = ""
            if combo_nivel_abe.current() > 0:
                nivel_id = niveles[combo_nivel_abe.current() - 1].id
            lineas = dis_abe.recuento_texto(
                dis_abe.resumen_aberturas(self.ctx, nivel_id))
            self._diseno_pinta(salida_abe, lineas)
            self._say("Recuento de aberturas actualizado.", "")

        fila_btn_abe = ttk.Frame(tab_abe)
        fila_btn_abe.pack(fill="x", pady=(2, 0))
        self._tip(ttk.Button(fila_btn_abe,
                             text=icons.label("aberturas",
                                              "Aplicar tipología"),
                             style="Accent.TButton",
                             command=_abe_aplicar),
                  "aberturas").pack(side="left")
        self._tip(ttk.Button(fila_btn_abe, text="📊 Recuento",
                             command=_abe_recuento),
                  "aberturas_recuento").pack(side="left", padx=6)
        self._tip(ttk.Button(fila_btn_abe, text="🗑 Quitar tipología",
                             command=_abe_quitar),
                  "aberturas_quitar").pack(side="left", padx=6)

        # ================= pestaña ILUMINACIÓN (v3.19.0) =================
        tab_ilu = ttk.Frame(notebook, padding=(12, 10))
        notebook.add(tab_ilu, text="💡 Iluminación")
        ttk.Label(tab_ilu,
                  text="Proyecta la iluminación artificial con LÚMENES: "
                       "elige la LÁMPARA (LED en todas sus formas, "
                       "fluorescente, halógena, incandescente, sodio) y "
                       "el método de los lúmenes calcula cuántas van y "
                       "las COLOCA en retícula dentro de cada local, "
                       "como luminarias reales de la red de alumbrado.",
                  style="Hint.TLabel", wraplength=640,
                  justify="left").pack(fill="x", pady=(0, 8))
        fila_ilu1 = ttk.Frame(tab_ilu)
        fila_ilu1.pack(fill="x", pady=2)
        ttk.Label(fila_ilu1, text="Lámpara:").pack(side="left")
        combo_ilu_lamp = ttk.Combobox(fila_ilu1, state="readonly",
                                      width=24,
                                      values=dis_ilu.tipos_lampara())
        combo_ilu_lamp.set("led_panel")
        combo_ilu_lamp.pack(side="left", padx=4)
        ttk.Label(fila_ilu1, text="Lux (0 = según uso):").pack(
            side="left", padx=(8, 0))
        var_ilu_lux = tk.StringVar(value="0")
        ttk.Entry(fila_ilu1, textvariable=var_ilu_lux,
                  width=6).pack(side="left", padx=4)
        ttk.Label(fila_ilu1, text="Nivel:").pack(side="left", padx=(8, 0))
        combo_nivel_ilu = ttk.Combobox(fila_ilu1, state="readonly",
                                       width=16,
                                       values=["(todos)"] +
                                       [lv.name for lv in niveles])
        combo_nivel_ilu.current(0)
        combo_nivel_ilu.pack(side="left", padx=4)
        salida_ilu = tk.Text(tab_ilu, height=13, wrap="word",
                             background=theme.get("canvas"),
                             foreground=theme.get("text"), relief="flat")
        salida_ilu.pack(fill="both", expand=True, pady=(8, 4))

        def _iluminacion_generar() -> None:
            try:
                lux = int(str(var_ilu_lux.get()).strip() or "0")
            except ValueError:
                messagebox.showerror(
                    "Iluminación", "Los lux deben ser un número entero.",
                    parent=dialog)
                return
            nivel_id = ""
            if combo_nivel_ilu.current() > 0:
                nivel_id = niveles[combo_nivel_ilu.current() - 1].id
            try:
                resumen = dis_ilu.generar_iluminacion(
                    self.ctx, None, lampara=combo_ilu_lamp.get(),
                    nivel_id=nivel_id, lux=lux or None)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Iluminación", str(exc), parent=dialog)
                return
            self.refresh_all()
            lineas = [dis_ilu.resumen_texto(resumen), ""]
            lineas += dis_ilu.locales_texto(resumen)
            lineas += ["Avisos:"] + [f"  {a}" for a in
                                     resumen.get("avisos", [])] \
                or ["  (ninguno)"]
            self._diseno_pinta(salida_ilu, lineas)
            self._say(dis_ilu.resumen_texto(resumen),
                      "Ctrl+Z deshace paso a paso")

        def _iluminacion_comparativa() -> None:
            nivel_id = ""
            if combo_nivel_ilu.current() > 0:
                nivel_id = niveles[combo_nivel_ilu.current() - 1].id
            espacios = [e for e in dis_ilu.lista_tipos(self.ctx, "SPACE")
                        if (not nivel_id or e.level_id == nivel_id)
                        and len(getattr(e, "boundary", []) or []) >= 3]
            if not espacios:
                messagebox.showerror(
                    "Iluminación", "No hay locales todavía: genera la "
                    "edificación primero.", parent=dialog)
                return
            ref = max(espacios, key=lambda e: e.area_m2())
            try:
                lux = int(str(var_ilu_lux.get()).strip()
                          or "0") or dis_ilu.lux_para(ref.space_type)
                lineas = dis_ilu.tabla_texto(ref.area_m2(), lux)
                lineas.append(f"(local de referencia: "
                              f"{ref.name or ref.code})")
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Iluminación", str(exc), parent=dialog)
                return
            self._diseno_pinta(salida_ilu, lineas)
            self._say(f"Comparativa de lámparas a {lux} lux.", "")

        def _iluminacion_quitar() -> None:
            try:
                bajas = dis_ilu.quitar_iluminacion(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Iluminación", str(exc), parent=dialog)
                return
            self.refresh_all()
            self._diseno_pinta(salida_ilu, [
                f"Luminarias generadas retiradas: {len(bajas)} pieza(s).",
                "Lo cableado a mano se conserva."])
            self._say(f"Luminarias retiradas: {len(bajas)}.", "")

        fila_btn_ilu = ttk.Frame(tab_ilu)
        fila_btn_ilu.pack(fill="x", pady=(2, 0))
        self._tip(ttk.Button(fila_btn_ilu,
                             text=icons.label("iluminacion",
                                              "Dimensionar y colocar"),
                             style="Accent.TButton",
                             command=_iluminacion_generar),
                  "iluminacion").pack(side="left")
        self._tip(ttk.Button(fila_btn_ilu, text="📊 Comparativa",
                             command=_iluminacion_comparativa),
                  "iluminacion_comparativa").pack(side="left", padx=6)
        self._tip(ttk.Button(fila_btn_ilu, text="🗑 Quitar generadas",
                             command=_iluminacion_quitar),
                  "iluminacion_quitar").pack(side="left", padx=6)

        # ================= pestaña ALARMAS (v3.19.0) =====================
        tab_alr = ttk.Frame(notebook, padding=(12, 10))
        notebook.add(tab_alr, text="🔔 Alarmas")
        ttk.Label(tab_alr,
                  text="Protege los LOCALES QUE QUIERAS: márcalos en la "
                       "lista y el sistema coloca detectores PIR (1 por "
                       "~12 m2), contactos magnéticos en todos sus vanos "
                       "y el panel con teclado y sirena donde pidas. La "
                       "cobertura se valida con el motor de intrusión y "
                       "queda en la red INTRUSION del proyecto.",
                  style="Hint.TLabel", wraplength=640,
                  justify="left").pack(fill="x", pady=(0, 8))
        fila_alr1 = ttk.Frame(tab_alr)
        fila_alr1.pack(fill="x", pady=2)
        ttk.Label(fila_alr1, text="Locales a proteger (clic o Ctrl+clic):"
                  ).pack(side="left")
        ttk.Label(fila_alr1, text="Panel en:").pack(side="left",
                                                    padx=(12, 0))
        combo_alr_panel = ttk.Combobox(fila_alr1, state="readonly",
                                       width=22, values=())
        combo_alr_panel.pack(side="left", padx=4)
        var_alr_ext = tk.BooleanVar(value=False)
        ttk.Checkbutton(fila_alr1, text="Sirena exterior",
                        variable=var_alr_ext).pack(side="left", padx=(8, 0))
        lista_alr = tk.Listbox(tab_alr, selectmode="extended", height=7,
                               exportselection=False,
                               background=theme.get("canvas"),
                               foreground=theme.get("text"),
                               relief="flat")
        lista_alr.pack(fill="both", expand=True, pady=(6, 4))
        salida_alr = tk.Text(tab_alr, height=8, wrap="word",
                             background=theme.get("canvas"),
                             foreground=theme.get("text"), relief="flat")
        salida_alr.pack(fill="both", expand=True, pady=(0, 4))
        _prot_alr: list = alr_datos["locales"]

        def _alr_refresca_lista() -> None:
            lista_alr.delete(0, "end")
            combo_alr_panel["values"] = [
                f"{d['code']} · {d['nombre']}" for d in _prot_alr]
            if _prot_alr:
                combo_alr_panel.current(0)
            for d in _prot_alr:
                lista_alr.insert("end", f"{d['code']} · {d['nombre']} · "
                                  f"{d['area_m2']:.1f} m2 · {d['vanos']} "
                                  f"vano(s) · {d['pirs']} PIR")

        _alr_refresca_lista()

        def _alarma_generar() -> None:
            sel = lista_alr.curselection()
            if not sel:
                messagebox.showerror(
                    "Alarmas", "Marca primero los locales que quieres "
                    "proteger.", parent=dialog)
                return
            space_ids = [_prot_alr[i]["id"] for i in sel]
            panel_id = ""
            idx_panel = combo_alr_panel.current()
            if 0 <= idx_panel < len(_prot_alr):
                panel_id = _prot_alr[idx_panel]["id"]
            try:
                resumen = alr_mod.generar_alarma(
                    self.ctx, None, space_ids=space_ids,
                    panel_space_id=panel_id,
                    sirena_exterior=bool(var_alr_ext.get()))
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Alarmas", str(exc), parent=dialog)
                return
            self.refresh_all()
            lineas = [alr_mod.resumen_texto(resumen), ""]
            lineas += alr_mod.zonas_texto(resumen)
            self._diseno_pinta(salida_alr, lineas)
            self._say(alr_mod.resumen_texto(resumen),
                      "Ctrl+Z deshace paso a paso")

        def _alarma_quitar() -> None:
            try:
                bajas = alr_mod.quitar_alarmas(self.ctx)
                self.ctx.commit()
            except Exception as exc:  # noqa: BLE001
                self.ctx.rollback()
                messagebox.showerror("Alarmas", str(exc), parent=dialog)
                return
            self.refresh_all()
            self._diseno_pinta(salida_alr, [
                f"Dispositivos generados retirados: {len(bajas)}.",
                "Lo cableado a mano se conserva."])
            self._say(f"Dispositivos retirados: {len(bajas)}.", "")

        fila_btn_alr = ttk.Frame(tab_alr)
        fila_btn_alr.pack(fill="x", pady=(2, 0))
        self._tip(ttk.Button(fila_btn_alr,
                             text=icons.label("alarmas",
                                              "Proteger locales"),
                             style="Accent.TButton",
                             command=_alarma_generar),
                  "alarmas").pack(side="left")
        self._tip(ttk.Button(fila_btn_alr, text="🗑 Quitar dispositivos",
                             command=_alarma_quitar),
                  "alarmas_quitar").pack(side="left", padx=6)

        # -- ganchos de prueba + arranque ------------------------------------
        dialog._diseno_state = {
            "combo_ambito": combo_ambito, "combo_dens": combo_dens,
            "combo_nivel_mob": combo_nivel_mob, "combo_tip": combo_tip,
            "combo_mat": combo_mat, "combo_est": combo_est,
            "var_pend": var_pend, "var_alero": var_alero,
            "var_cota": var_cota,
            "combo_asc_tipo": combo_asc_tipo,
            "var_asc_personas": var_asc_personas,
            "var_asc_fachada": var_asc_fachada,
            "combo_par_tipo": combo_par_tipo,
            "combo_par_mat": combo_par_mat,
            "var_fac_lados": var_fac_lados,
            "var_par_vuelo": var_par_vuelo, "var_par_sep": var_par_sep,
            "combo_piel_tipo": combo_piel_tipo,
            "var_piel_sep": var_piel_sep,
            "var_piel_lados": var_piel_lados,
            "combo_esc_tipo": combo_esc_tipo,
            "var_esc_desnivel": var_esc_desnivel,
            "var_esc_h": var_esc_h, "var_esc_p": var_esc_p,
            "var_esc_ancho": var_esc_ancho, "var_esc_rot": var_esc_rot,
            "combo_nivel_esc": combo_nivel_esc,
            "combo_abe_kind": combo_abe_kind,
            "combo_abe_tipo": combo_abe_tipo,
            "combo_nivel_abe": combo_nivel_abe,
            "combo_ilu_lamp": combo_ilu_lamp,
            "var_ilu_lux": var_ilu_lux,
            "combo_nivel_ilu": combo_nivel_ilu,
            "lista_alr": lista_alr, "combo_alr_panel": combo_alr_panel,
            "var_alr_ext": var_alr_ext,
            "salida_mob": salida_mob, "salida_cub": salida_cub,
            "salida_acc": salida_acc, "salida_asc": salida_asc,
            "salida_fac": salida_fac, "salida_esc": salida_esc,
            "salida_abe": salida_abe, "salida_ilu": salida_ilu,
            "salida_alr": salida_alr, "notebook": notebook}
        dialog._diseno_mobiliario_generar = _mobiliario_generar_envoltura
        dialog._diseno_mobiliario_quitar = _mobiliario_quitar
        dialog._diseno_cubierta_generar = _cubierta_generar
        dialog._diseno_cubierta_quitar = _cubierta_quitar
        dialog._diseno_acc_analizar = _acc_analizar
        dialog._diseno_acc_aplicar = _acc_aplicar
        dialog._diseno_acc_quitar = _acc_quitar
        dialog._diseno_ascensores_generar = _ascensores_generar
        dialog._diseno_ascensores_quitar = _ascensores_quitar
        dialog._diseno_parasoles_generar = _parasoles_generar
        dialog._diseno_parasoles_quitar = _parasoles_quitar
        dialog._diseno_piel_generar = _piel_generar
        dialog._diseno_piel_quitar = _piel_quitar
        dialog._diseno_escalera_generar = _escalera_generar
        dialog._diseno_escalera_quitar = _escalera_quitar
        dialog._diseno_abe_aplicar = _abe_aplicar
        dialog._diseno_abe_quitar = _abe_quitar
        dialog._diseno_abe_recuento = _abe_recuento
        dialog._diseno_abe_kind_changed = _abe_kind_changed
        dialog._diseno_iluminacion_generar = _iluminacion_generar
        dialog._diseno_iluminacion_comparativa = _iluminacion_comparativa
        dialog._diseno_iluminacion_quitar = _iluminacion_quitar
        dialog._diseno_alarma_generar = _alarma_generar
        dialog._diseno_alarma_quitar = _alarma_quitar
        dialog._diseno_alarma_refresca = _alr_refresca_lista
        self._say("Concepción de espacios: amuebla, cubre, hace "
                  "accesible, sube en ascensor, viste la fachada, sube "
                  "la escalera, tipifica vanos, alumbra y protege; todo "
                  "se regenera con la edificación.")

    def _diseno_pinta(self, salida: Any, lineas: Any) -> None:
        """Vuelca líneas en un Text del taller de diseño (solo lectura)."""
        try:
            salida.configure(state="normal")
            salida.delete("1.0", "end")
            for linea in lineas:
                if linea:
                    salida.insert("end", linea + "\n")
            salida.configure(state="disabled")
        except Exception:  # noqa: BLE001 - la ventana pudo cerrarse
            pass

    def open_view3d_dialog(self) -> None:
        """Vista 3D axonométrica (v3.11.0): el edificio generado se
        gira con el ratón, se aísla por nivel, se separa en «explosión»
        y se exporta en PNG determinista — todo con el motor puro de
        ui.view3d (proyección ortográfica sin dependencias nuevas)."""
        from ui import view3d as v3
        from ui import solar as v3_solar
        from ui import terreno3d as v3_terreno
        modelo, avisos = v3.modelo3d_desde_proyecto(self.ctx)
        if not modelo.muros and not modelo.locales:
            messagebox.showinfo(
                "Vista 3D",
                "Todavía no hay muros ni locales que girar.\n\n"
                + " ".join(avisos)
                + "\n\nUsa el asistente de edificación (🏠) o regenera "
                  "la edificación (♻) y vuelve aquí.",
                parent=self)
            return
        dialog = tk.Toplevel(self)
        self._vista3d_dialog = dialog
        dialog.title("Vista 3D del edificio")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "vista_3d")

        state: Dict[str, Any] = {
            "cam": v3.Camara3D(), "modelo": modelo, "nivel_id": "",
            "colores": "tipo", "explotar_m": 0.0, "caras": 0,
            "solar": None, "terreno": None,
            "muebles": True, "cubierta": True, "accesibilidad": True}

        # -- barra de controles -------------------------------------------
        barra = ttk.Frame(dialog, padding=(8, 6))
        barra.pack(side="top", fill="x")

        def _boton(padre: Any, texto: str, accion: Any,
                   padx: int = 2) -> None:
            self._tip(ttk.Button(padre, text=texto, command=accion),
                      "vista3d").pack(side="left", padx=padx)

        ttk.Label(barra, text="Girar:").pack(side="left")
        _boton(barra, "⟲", lambda: (state["cam"].gira(-20), _render()))
        _boton(barra, "⟳", lambda: (state["cam"].gira(20), _render()))
        ttk.Separator(barra, orient="vertical").pack(
            side="left", fill="y", padx=8)
        ttk.Label(barra, text="Elevación:").pack(side="left")
        _boton(barra, "−", lambda: (state["cam"].inclina(-10), _render()))
        _boton(barra, "＋", lambda: (state["cam"].inclina(10), _render()))
        ttk.Separator(barra, orient="vertical").pack(
            side="left", fill="y", padx=8)
        ttk.Label(barra, text="Zoom:").pack(side="left")
        _boton(barra, "＋", lambda: (state["cam"].acerca(1.25), _render()))
        _boton(barra, "−", lambda: (state["cam"].acerca(0.8), _render()))
        _boton(barra, "Encuadrar", lambda: (setattr(
            state["cam"], "zoom", 1.0), _render()), padx=(8, 2))

        # -- lienzo ---------------------------------------------------------
        lienzo = tk.Canvas(dialog, background=theme.get("canvas"),
                           highlightthickness=0)
        lienzo.pack(side="top", fill="both", expand=True,
                    padx=8, pady=(0, 8))

        def _render() -> None:
            """Extruye el modelo con la cámara actual y pinta las caras
            con el MISMO orden del pintor que el PNG determinista."""
            cam = state["cam"]
            caras = v3.construir_caras(
                state["modelo"], cam, colores=state["colores"],
                explotar_m=state["explotar_m"],
                nivel_id=state["nivel_id"],
                solar=state.get("solar"), terreno=state.get("terreno"),
                mostrar_muebles=bool(state.get("muebles", True)),
                mostrar_cubierta=bool(state.get("cubierta", True)),
                mostrar_accesibilidad=bool(
                    state.get("accesibilidad", True)),
                mostrar_fachada=bool(state.get("fachada", True)))
            state["caras"] = len(caras)
            lienzo.delete("all")
            ancho = max(lienzo.winfo_width(), 320)
            alto = max(lienzo.winfo_height(), 240)
            if caras:
                minx, miny, maxx, maxy = v3.encuadre(caras, cam)
                k = min((ancho - 80) / max(maxx - minx, 1e-6),
                        (alto - 80) / max(maxy - miny, 1e-6)) * cam.zoom
                ox = ancho / 2 - (minx + maxx) / 2 * k
                oy = alto / 2 + (miny + maxy) / 2 * k
                for cara in caras:
                    pix = [(ox + sx * k, oy - sy * k)
                           for (sx, sy) in (v3.proyecta(p, cam)
                                            for p in cara.puntos)]
                    lienzo.create_polygon(
                        *[c for punto in pix for c in punto],
                        fill=cara.color,
                        outline=v3.sombrea(cara.color, 0.55), width=1)
            niveles_txt = str(len(state["modelo"].niveles))
            extra = ""
            if state.get("solar") is not None:
                extra += " · " + v3_solar.resumen_solar(state["solar"])
            if state.get("terreno") is not None:
                extra += " · terreno %d%%" % round(
                    state["terreno"].pendiente_pct)
            lienzo.create_text(
                12, 10, anchor="nw",
                text=f"azimut {cam.azimuth_deg:.0f}° · elevación "
                     f"{cam.elevacion_deg:.0f}° · "
                     f"{'perspectiva' if cam.perspectiva else 'axonométrica'}"
                     f" · {niveles_txt} nivel(es) "
                     f"· {len(caras)} caras{extra} — arrastra o usa las "
                     f"flechas del teclado para girar (P conmuta la "
                     f"perspectiva)",
                fill=theme.get("text_dim"))

        # -- combos de nivel / colores / explosión --------------------------
        opciones = ttk.Frame(dialog, padding=(8, 0))
        opciones.pack(side="top", fill="x")

        ttk.Label(opciones, text="Nivel:").pack(side="left")
        combo_nivel = ttk.Combobox(
            opciones, state="readonly", width=14,
            values=["(todos)"] + [n.name for n in modelo.niveles])
        combo_nivel.current(0)
        combo_nivel.pack(side="left", padx=(2, 10))

        ttk.Label(opciones, text="Colores:").pack(side="left")
        combo_colores = ttk.Combobox(
            opciones, state="readonly", width=11,
            values=("Por tipo", "Monocromo"))
        combo_colores.current(0)
        combo_colores.pack(side="left", padx=(2, 10))

        ttk.Label(opciones, text="Explosión:").pack(side="left")
        combo_explotar = ttk.Combobox(
            opciones, state="readonly", width=4,
            values=("0", "1", "2", "3"))
        combo_explotar.current(0)
        combo_explotar.pack(side="left", padx=(2, 10))

        # VISTA EN PERSPECTIVA (v3.17.0): además de la axonométrica de
        # siempre, la cámara puede dividir por la profundidad como un
        # objetivo real con punto de fuga.
        perspectiva_var = tk.BooleanVar(value=False)

        def _elige_perspectiva() -> None:
            cam = state["cam"]
            cam.perspectiva = bool(perspectiva_var.get())
            cam.distancia_m = 0.0   # se recalcula al encuadrar
            _render()

        self._tip(ttk.Checkbutton(opciones, text="Perspectiva",
                                  variable=perspectiva_var,
                                  command=_elige_perspectiva),
                  "vista3d").pack(side="left", padx=(2, 10))

        ttk.Button(opciones, text="💾 PNG…",
                   command=lambda: _exportar()).pack(side="right")
        ttk.Button(opciones, text="↻ Recargar",
                   command=lambda: _recargar()).pack(side="right", padx=6)

        def _elige_nivel(_e: Any = None) -> None:
            indice = combo_nivel.current()
            state["nivel_id"] = ("" if indice <= 0
                                 else modelo.niveles[indice - 1].level_id)
            _render()

        def _elige_colores(_e: Any = None) -> None:
            state["colores"] = ("tipo" if combo_colores.current() == 0
                                else "mono")
            _render()

        def _elige_explotar(_e: Any = None) -> None:
            state["explotar_m"] = float(combo_explotar.current())
            _render()

        combo_nivel.bind("<<ComboboxSelected>>", _elige_nivel)
        combo_colores.bind("<<ComboboxSelected>>", _elige_colores)
        combo_explotar.bind("<<ComboboxSelected>>", _elige_explotar)

        # -- sol y terreno (v3.13.0) -----------------------------------------
        fila_sol = ttk.Frame(dialog, padding=(8, 6, 8, 0))
        fila_sol.pack(side="top", fill="x")
        fila_ter = ttk.Frame(dialog, padding=(8, 4, 8, 0))
        fila_ter.pack(side="top", fill="x")

        sombras_var = tk.BooleanVar(value=False)
        terreno_var = tk.BooleanVar(value=False)
        latitudes = [("La Habana 23°N", 23.1), ("Madrid 40°N", 40.4),
                     ("Ciudad de México 19°N", 19.4), ("Bogotá 5°N", 4.7),
                     ("Lima 12°S", -12.0), ("Santiago 33°S", -33.4),
                     ("Buenos Aires 35°S", -34.6), ("Quito 0°", -0.2)]
        fechas = tuple(v3_solar.FECHAS_CANONICAS.items())
        horas = tuple(("%02d:00" % h, float(h)) for h in
                      (6, 8, 10, 12, 14, 16, 18))
        pendientes = (("0 %", 0.0), ("2 %", 2.0), ("5 %", 5.0),
                      ("10 %", 10.0), ("15 %", 15.0))
        rumbos = (("Norte", 0.0), ("Este", 90.0), ("Sur", 180.0),
                  ("Oeste", 270.0))
        relieves = (("Liso", 0.0), ("Suave", 0.3), ("Accidentado", 0.8))

        def _combo(padre: Any, etiqueta: str, valores: Any,
                   ancho: int) -> ttk.Combobox:
            ttk.Label(padre, text=etiqueta).pack(side="left")
            combo = ttk.Combobox(padre, state="readonly", width=ancho,
                                 values=[v[0] for v in valores])
            combo.current(0)
            combo.pack(side="left", padx=(2, 8))
            return combo

        def _recalcula_sol(_e: Any = None) -> None:
            """Arma el SolarOpts de los combos y redibuja con sombras."""
            if not sombras_var.get():
                state["solar"] = None
            else:
                state["solar"] = v3_solar.SolarOpts(
                    latitud_deg=latitudes[max(0, combo_lat.current())][1],
                    dia_anio=fechas[max(0, combo_fecha.current())][1],
                    hora=horas[max(0, combo_hora.current())][1])
            _render()

        def _recalcula_terreno(_e: Any = None) -> None:
            """Arma el TerrenoOpts de los combos y redibuja el solar."""
            if not terreno_var.get():
                state["terreno"] = None
            else:
                state["terreno"] = v3_terreno.TerrenoOpts(
                    pendiente_pct=pendientes[
                        max(0, combo_pend.current())][1],
                    direccion_deg=rumbos[
                        max(0, combo_rumbo.current())][1],
                    relieve_m=relieves[max(0, combo_rel.current())][1])
            _render()

        ttk.Checkbutton(fila_sol, text="☀ Sombras solares",
                        variable=sombras_var,
                        command=_recalcula_sol).pack(side="left")
        combo_lat = _combo(fila_sol, "Latitud:", latitudes, 17)
        combo_fecha = _combo(fila_sol, "Fecha:", fechas, 17)
        combo_hora = _combo(fila_sol, "Hora solar:", horas, 6)
        combo_hora.current(3)  # mediodía solar por defecto (12:00)

        ttk.Checkbutton(fila_ter, text="⛰ Terreno",
                        variable=terreno_var,
                        command=_recalcula_terreno).pack(side="left")
        combo_pend = _combo(fila_ter, "Pendiente:", pendientes, 4)
        combo_rumbo = _combo(fila_ter, "Baja hacia:", rumbos, 6)
        combo_rel = _combo(fila_ter, "Relieve:", relieves, 11)

        # -- capas de la concepción de espacios (v3.15.0) -----------------
        fila_dis = ttk.Frame(dialog, padding=(8, 4, 8, 0))
        fila_dis.pack(side="top", fill="x")
        muebles_var = tk.BooleanVar(value=True)
        cubierta_var = tk.BooleanVar(value=True)
        accesibilidad_var = tk.BooleanVar(value=True)
        fachada_var = tk.BooleanVar(value=True)

        def _recalcula_capas(_e: Any = None) -> None:
            state["muebles"] = bool(muebles_var.get())
            state["cubierta"] = bool(cubierta_var.get())
            state["accesibilidad"] = bool(accesibilidad_var.get())
            state["fachada"] = bool(fachada_var.get())
            _render()

        ttk.Label(fila_dis, text="Capas:").pack(side="left")
        ttk.Checkbutton(fila_dis, text="🛋 Mobiliario",
                        variable=muebles_var,
                        command=_recalcula_capas).pack(side="left")
        ttk.Checkbutton(fila_dis, text="⌂ Cubierta",
                        variable=cubierta_var,
                        command=_recalcula_capas).pack(side="left",
                                                       padx=(8, 0))
        ttk.Checkbutton(fila_dis, text="♿ Accesibilidad",
                        variable=accesibilidad_var,
                        command=_recalcula_capas).pack(side="left",
                                                       padx=(8, 0))
        self._tip(ttk.Checkbutton(fila_dis, text="🌤 Parasoles y pieles",
                                  variable=fachada_var,
                                  command=_recalcula_capas),
                  "fachada_capa").pack(side="left", padx=(8, 0))

        for _combo_sol in (combo_lat, combo_fecha, combo_hora):
            _combo_sol.bind("<<ComboboxSelected>>", _recalcula_sol)
        for _combo_ter in (combo_pend, combo_rumbo, combo_rel):
            _combo_ter.bind("<<ComboboxSelected>>", _recalcula_terreno)

        # -- gestos: arrastrar gira, rueda acerca ---------------------------
        arrastre = {"x": 0, "y": 0}

        def _presionar(evento: Any) -> None:
            arrastre["x"], arrastre["y"] = evento.x, evento.y

        def _arrastrar(evento: Any) -> None:
            cam = state["cam"]
            cam.gira((evento.x - arrastre["x"]) * 0.5)
            cam.inclina((arrastre["y"] - evento.y) * 0.3)
            arrastre["x"], arrastre["y"] = evento.x, evento.y
            _render()

        def _rueda(evento: Any) -> None:
            subir = (getattr(evento, "num", 0) == 4
                     or getattr(evento, "delta", 0) > 0)
            state["cam"].acerca(1.1 if subir else 0.9)
            _render()

        lienzo.bind("<Button-1>", _presionar)
        lienzo.bind("<B1-Motion>", _arrastrar)
        lienzo.bind("<MouseWheel>", _rueda)
        lienzo.bind("<Button-4>", _rueda)
        lienzo.bind("<Button-5>", _rueda)
        lienzo.bind("<Configure>", lambda _e: _render())

        # NAVEGACION 3D CON TECLADO (v3.16.0): flechas giran/inclinan,
        # +/- zoom y Home resetea el encuadre, como un visor CAD.
        def _tecla3d(evento: Any) -> str:
            if state["cam"].tecla(str(evento.keysym)):
                perspectiva_var.set(state["cam"].perspectiva)
                _render()
                return "break"
            return ""

        for sec in ("<Left>", "<Right>", "<Up>", "<Down>", "<plus>",
                    "<equal>", "<minus>", "<Home>", "<p>", "<P>"):
            lienzo.bind(sec, _tecla3d)
        # algunos builds de Tcl no traen los keysym del teclado
        # numérico: se intentan y si el Tcl los rechaza, se quedan fuera
        for sec in ("<kp_add>", "<kp_subtract>"):
            try:
                lienzo.bind(sec, _tecla3d)
            except tk.TclError:  # noqa: PERF203 - keysym ausente
                pass
        lienzo.bind("<Button-1>",
                    lambda e: (lienzo.focus_set(), _presionar(e)), add="+")

        # -- exportar / recargar ---------------------------------------------
        def _exportar(ruta: Optional[str] = None) -> None:
            if not ruta:
                ruta = filedialog.asksaveasfilename(
                    parent=dialog, title="Exportar vista 3D en PNG",
                    defaultextension=".png",
                    initialfile="vista_3d.png",
                    filetypes=[("PNG", "*.png")])
            if not ruta:
                return
            cam = state["cam"]
            caras = v3.construir_caras(
                state["modelo"], cam, colores=state["colores"],
                explotar_m=state["explotar_m"],
                nivel_id=state["nivel_id"],
                solar=state.get("solar"), terreno=state.get("terreno"),
                mostrar_muebles=bool(state.get("muebles", True)),
                mostrar_cubierta=bool(state.get("cubierta", True)),
                mostrar_accesibilidad=bool(
                    state.get("accesibilidad", True)),
                mostrar_fachada=bool(state.get("fachada", True)))
            info_extra = ""
            if state.get("solar") is not None:
                info_extra = v3_solar.resumen_solar(state["solar"])
            v3.export_vista3d_png(
                caras, cam, ruta,
                titulo=f"{self.ctx.project.name} - vista 3D",
                info_extra=info_extra)
            self._say("Vista 3D exportada en PNG (determinista).", ruta)
            messagebox.showinfo(
                "Vista 3D", "PNG guardado en:\n" + ruta, parent=dialog)

        def _recargar() -> None:
            modelo_nuevo, avisos_recarga = v3.modelo3d_desde_proyecto(
                self.ctx)
            state["modelo"] = modelo_nuevo
            combo_nivel["values"] = ["(todos)"] + [
                n.name for n in modelo_nuevo.niveles]
            combo_nivel.current(0)
            state["nivel_id"] = ""
            _render()
            for aviso in avisos_recarga:
                self._say(aviso)

        # -- ganchos de prueba + arranque -----------------------------------
        dialog._vista3d_state = state
        dialog._vista3d_canvas = lienzo
        dialog._vista3d_render = _render
        dialog._vista3d_export = _exportar
        dialog._vista3d_recargar = _recargar
        dialog._vista3d_gira = lambda grados: (
            state["cam"].gira(grados), _render())
        dialog._vista3d_solar_var = sombras_var
        dialog._vista3d_terreno_var = terreno_var
        dialog._vista3d_recalcula = lambda: (_recalcula_sol(),
                                             _recalcula_terreno())
        dialog._vista3d_muebles_var = muebles_var
        dialog._vista3d_cubierta_var = cubierta_var
        dialog._vista3d_accesibilidad_var = accesibilidad_var
        dialog._vista3d_perspectiva_var = perspectiva_var
        dialog._vista3d_perspectiva = _elige_perspectiva
        dialog._vista3d_tecla = _tecla3d
        _render()
        self._say("Vista 3D: arrastra o usa las flechas del teclado "
                  "para girar el edificio, elige "
                  "nivel o explosión, y exporta el PNG.")

    def open_importar_ifc(self) -> None:
        """Importa un modelo IFC4/IFC2X3 de texto (v3.13.0): analiza
        niveles, muros, locales, puertas y ventanas del archivo y los
        crea en el proyecto actual con los mismos comandos oficiales
        que la CLI (CommandBus, auditoría y códigos ARQ-XXX-nnn)."""
        from core.errors import DomainError
        from importers.ifc_reader import IfcImporter
        dialog = tk.Toplevel(self)
        dialog.title("Importar modelo IFC")
        dialog.configure(background=theme.COL_BG)
        dialog.transient(self)
        self._prepare_dialog(dialog, "importar_ifc")

        ruta_var = tk.StringVar(value="")
        estado_var = tk.StringVar(value="Elige un archivo .ifc y pulsa "
                                        "«Analizar».")
        resultado: Dict[str, Any] = {}

        cabeza = ttk.Frame(dialog, padding=(12, 10))
        cabeza.pack(side="top", fill="x")
        ttk.Label(cabeza, text="Archivo IFC:").pack(side="left")
        ttk.Entry(cabeza, textvariable=ruta_var).pack(
            side="left", fill="x", expand=True, padx=6)

        cuerpo = ttk.Frame(dialog, padding=(12, 0))
        cuerpo.pack(side="top", fill="both", expand=True)
        resumen = ttk.Frame(cuerpo)
        resumen.pack(side="top", fill="both", expand=True)

        pie = ttk.Frame(dialog, padding=(12, 8))
        pie.pack(side="bottom", fill="x")
        ttk.Label(pie, textvariable=estado_var, wraplength=680,
                  justify="left").pack(side="left", fill="x", expand=True)

        botones = ttk.Frame(dialog, padding=(12, 6))
        botones.pack(side="bottom", fill="x")

        def _limpia() -> None:
            for hijo in resumen.winfo_children():
                hijo.destroy()
            resultado.clear()

        def _examinar() -> None:
            ruta = filedialog.askopenfilename(
                parent=dialog, title="Abrir modelo IFC",
                filetypes=[("IFC (ISO-10303-21)", "*.ifc"),
                           ("Todos", "*.*")])
            if ruta:
                ruta_var.set(ruta)
                estado_var.set("Listo para analizar.")
                _limpia()

        def _analizar() -> None:
            ruta = ruta_var.get().strip()
            if not ruta:
                messagebox.showinfo(
                    "Importar IFC", "Elige primero un archivo .ifc.",
                    parent=dialog)
                return
            try:
                datos = IfcImporter().preview(ruta)
            except DomainError as exc:
                estado_var.set("No se pudo analizar: " + exc.message)
                messagebox.showerror(
                    "Importar IFC",
                    exc.message + "\n\n" + (exc.suggested_action or ""),
                    parent=dialog)
                return
            _limpia()
            resultado.update(datos)
            filas = [
                ("Esquema", datos.get("schema") or "?"),
                ("Unidades", datos.get("unidad") or "?"),
                ("Pisos (IfcBuildingStorey)", datos.get("storeys", 0)),
                ("Muros", datos.get("walls", 0)),
                ("Locales", datos.get("spaces", 0)),
                ("Puertas", datos.get("doors", 0)),
                ("Ventanas", datos.get("windows", 0)),
                ("Losas (omitidas)", datos.get("slabs", 0)),
                ("Otros productos (omitidos)", datos.get("otros", 0)),
            ]
            for indice, (clave, valor) in enumerate(filas):
                ttk.Label(resumen, text=clave + ":").grid(
                    row=indice, column=0, sticky="w", padx=(0, 10), pady=1)
                ttk.Label(resumen, text=str(valor)).grid(
                    row=indice, column=1, sticky="w", pady=1)
            avisos = datos.get("avisos", [])
            if avisos:
                ttk.Separator(resumen, orient="horizontal").grid(
                    row=len(filas), columnspan=2, sticky="ew", pady=6)
                texto = "\n".join("· " + a for a in avisos[:6])
                ttk.Label(resumen, text=texto, wraplength=680,
                          justify="left").grid(row=len(filas) + 1,
                                               columnspan=2, sticky="w")
            estado_var.set("Análisis listo: revisa el resumen y pulsa "
                           "«Importar al proyecto».")

        def _importar() -> None:
            ruta = ruta_var.get().strip()
            if not ruta:
                messagebox.showinfo(
                    "Importar IFC", "Elige primero un archivo .ifc.",
                    parent=dialog)
                return
            try:
                from services.architecture_service import (
                    ArchitectureService)
                datos = IfcImporter().apply(
                    ruta, ArchitectureService(self.ctx))
            except DomainError as exc:
                estado_var.set("No se pudo importar: " + exc.message)
                messagebox.showerror(
                    "Importar IFC",
                    exc.message + "\n\n" + (exc.suggested_action or ""),
                    parent=dialog)
                return
            estado_var.set(
                "Importado: %d nivel(es) nuevo(s), %d reutilizado(s), "
                "%d muros, %d locales, %d puertas, %d ventanas." % (
                    datos.get("niveles", 0),
                    datos.get("niveles_reutilizados", 0),
                    datos.get("muros", 0), datos.get("locales", 0),
                    datos.get("puertas", 0), datos.get("ventanas", 0)))
            self._say("IFC importado desde " + os.path.basename(ruta)
                      + ": " + estado_var.get(), ruta)
            for aviso in datos.get("avisos", []):
                self._say(aviso)
            try:
                self.redraw()
            except Exception:  # noqa: BLE001 - refresco cosmético
                pass
            messagebox.showinfo(
                "Importar IFC",
                "Modelo importado al proyecto actual.\n\n" + estado_var.get(),
                parent=dialog)

        self._tip(ttk.Button(botones, text="Examinar…",
                             command=_examinar), "importar_ifc"
                  ).pack(side="left")
        ttk.Button(botones, text="Analizar",
                   command=_analizar).pack(side="left", padx=(8, 0))
        ttk.Button(botones, text="Importar al proyecto",
                   command=_importar).pack(side="left", padx=(8, 0))

        # -- ganchos de prueba --------------------------------------------
        self._ifc_dialog = dialog
        self._ifc_ruta = ruta_var
        self._ifc_estado = estado_var
        self._ifc_resultado = resultado
        self._ifc_analizar = _analizar
        self._ifc_importar = _importar
        self._say("Importar IFC: analiza el archivo y crea niveles, "
                  "muros, locales, puertas y ventanas en este proyecto.")

    def open_project_dialog(self) -> None:
        if self.application is None:
            return
        path = filedialog.askopenfilename(
            title="Abrir proyecto", filetypes=[("Proyecto ARQ GEN",
                                                "*.arqgen")])
        if not path or not os.path.exists(path):
            return
        self.ctx.close()
        self.ctx = self.application.open_project(path)
        self._after_context_change()
        self._say(f"Proyecto abierto: {os.path.basename(path)}.",
                  next_hint(**self._project_stats()))

    def open_demo(self) -> None:
        if self.application is None:
            return
        path = os.path.join(tempfile.gettempdir(), "arqgen_gui_demo.arqgen")
        self.ctx.close()
        from app.demo import build_demo
        self.ctx = build_demo(self.application, path)
        self._after_context_change()
        self._say("Proyecto de demostración cargado: explóralo sin "
                  "compromiso; nada de lo que hagas aquí rompe nada.",
                  "Pulsa sobre cualquier objeto del plano para ver sus "
                  "datos")

    def _after_context_change(self) -> None:
        self.explorer = ExplorerModel(self.ctx)
        self.search_engine = SearchEngine(self.explorer)
        self.canvas_model = CanvasModel(self.ctx, self.explorer)
        self.state_service = StateService(self.ctx)
        self.edit_service = EditService(self.ctx, self.explorer)
        self.status_model = StatusModel(self.ctx)
        self.selection = None
        # El autoguardado sigue al proyecto activo (contexto nuevo).
        enabled = self.autosave.enabled if hasattr(self, "autosave") else \
            bool(self.prefs.get("autosave", True))
        self.autosave = AutoSaveService(self.ctx, enabled=enabled)
        self.title(f"ARQ GEN {APP_VERSION} — {self.ctx.project.name}")
        self.refresh_all(fit=True)

    def export(self, fmt: str) -> None:
        from services.export_service import ExportService
        extension = {"DXF": ".dxf", "JSON": ".json", "XLSX": ".xlsx",
                     "CSV": ".csv", "IFC": ".ifc", "SVG": ".svg"}[fmt]
        path = filedialog.asksaveasfilename(
            title=f"Exportar {fmt}", defaultextension=extension)
        if not path:
            return
        options = {"title": self.ctx.project.name} if fmt == "SVG" else None
        ExportService().export(self.ctx, fmt, path, options)
        self._say(f"Exportado {fmt}: {os.path.basename(path)}.",
                  "El archivo ya está donde elegiste; listo para "
                  "compartir")

    def export_dxf_r12(self) -> None:
        """DXF R12 ASCII (v3.31.0): máxima compatibilidad.

        El mismo plano que el DXF R2010 pero en entidades clásicas
        (LINE/ARC/TEXT, sin LWPOLYLINE) que entienden AutoCAD R12, CNC
        y visores antiguos. Sólo lectura del proyecto.
        """
        from services.export_service import ExportService
        path = filedialog.asksaveasfilename(
            title="Exportar DXF R12 (compatibilidad)",
            defaultextension=".dxf")
        if not path:
            return
        try:
            ExportService().export(self.ctx, "DXF", path,
                                   {"version": "R12"})
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Exportar DXF R12",
                "No pude exportar el DXF R12:\n\n"
                f"{exc}", parent=self)
            return
        self._say(f"Exportado DXF R12: {os.path.basename(path)}.",
                  "Entidades clásicas que entienden CAD antiguos, CNC "
                  "y visores")

    def exportar_todo_paquete(self) -> None:
        """«Exportar TODO (BIM + planos)» (v3.46.0): una carpeta con
        IFC4 (BIM), DXF R2010, DXF R12, JSON, CSV, XLSX y SVG — todo
        lo generado por cualquier asistente en un solo gesto."""
        from services.export_service import ExportService
        carpeta = filedialog.askdirectory(
            title="Carpeta para el paquete BIM + planos")
        if not carpeta:
            return
        try:
            res = ExportService().exportar_todo(self.ctx, carpeta)
        except Exception as exc:  # noqa: BLE001 - mensaje amable
            messagebox.showerror(
                "Exportar TODO",
                "No pude exportar el paquete:\n\n" + str(exc),
                parent=self)
            return
        lineas = [f"{fmt}: {os.path.basename(ruta)} "
                  f"({max(1, os.path.getsize(ruta) // 1024)} KB)"
                  for fmt, ruta in sorted(res["archivos"].items())]
        lineas += [f"{fmt}: NO EXPORTADO — {msg}"
                   for fmt, msg in sorted(res["errores"].items())]
        self._say(
            f"Paquete exportado: {len(res['archivos'])} archivo(s) "
            f"en {res['carpeta']}.",
            "El IFC se abre en visores BIM (usBIM, BIMvision, Solibri "
            "Anywhere) y los DXF en AutoCAD/BricsCAD/QGIS")
        messagebox.showinfo(
            "Exportar TODO (BIM + planos)",
            "Carpeta:\n" + res["carpeta"] + "\n\n"
            + "\n".join(lineas), parent=self)

    # -- paneles inferiores -------------------------------------------------------------
    def refresh_log(self) -> None:
        lines = self.status_model.log_lines(limit=80)
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", "\n".join(reversed(lines)))
        self.log_text.configure(state="disabled")

    def refresh_calcs(self) -> None:
        self.calc_tree.delete(*self.calc_tree.get_children())
        for row in self.status_model.calculation_rows(limit=50):
            self.calc_tree.insert("", "end", values=(
                calc_type_label(row.get("calculation_type", "")),
                row.get("status", ""),
                row.get("objects_processed", 0),
                row.get("duration_ms", 0),
                row.get("timestamp", "")))

    def refresh_statusbar(self) -> None:
        # El canal izquierdo es de ORIENTACIÓN (_say/tooltips); los datos
        # técnicos viven a la derecha para no pisar los mensajes.
        self._info_var.set(
            f"{self.ctx.project.name} · "
            f"disciplina: {discipline_label(self.current_discipline)} · "
            f"{len(self._primitives)} objetos en el plano")

    def about(self) -> None:
        messagebox.showinfo(
            "Acerca de ARQ GEN",
            f"ARQ GEN {APP_VERSION}\nBIM/BEQ offline para AEC.\n\n"
            "Una herramienta sencilla: explora, crea, calcula y exporta "
            "sin conexión. Si te pierdes, pulsa F1 y la guía rápida te "
            "orienta en 4 pasos.", parent=self)

    def on_close(self) -> None:
        # Cierre seguro: volcado final (si el autoguardado dejó algo
        # pendiente), preferencias guardadas y sesión cerrada.
        try:
            if getattr(self, "autosave", None) is not None:
                self.ctx.commit()
        except Exception:  # noqa: BLE001 - cerrar nunca debe fallar duro
            pass
        try:
            self._save_prefs_now()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.ctx.close()
        finally:
            self.destroy()

    def destroy(self) -> None:  # noqa: D102 - tk.Tk
        # Cancela la restauración pendiente de sashes: sin esto Tk 9
        # intenta ejecutarla sobre la ventana muerta (ruido en stderr).
        try:
            pending = getattr(self, "_sashes_after", None)
            if pending:
                self.after_cancel(pending)
            pending = getattr(self, "_sashes_after2", None)
            if pending:
                self.after_cancel(pending)
        except Exception:  # noqa: BLE001 - cierre best-effort
            pass
        super().destroy()

    def _save_prefs_now(self) -> None:
        """Persiste tema/autoguardado/paneles/geometría/sashes (silencioso)."""
        try:
            self.prefs["geometry"] = self.geometry()
            self._collect_sashes()
            prefs.save_prefs(self.prefs)
        except Exception:  # noqa: BLE001 - preferencias best-effort
            pass


def launch(file_path: str = "", demo: bool = False,
           width: int = 1280, height: int = 800) -> int:
    """Entry point of the GUI (`main.py gui [archivo] [--demo]`)."""
    from app.bootstrap import bootstrap

    application, _loader = bootstrap()
    if demo or not file_path:
        path = os.path.join(tempfile.gettempdir(), "arqgen_gui_demo.arqgen")
        from app.demo import build_demo
        context = build_demo(application, path)
    else:
        context = application.open_project(file_path)
    window = ARQGenWindow(context, application)
    # La geometría guardada en preferencias manda (v3.7.0); el tamaño
    # por CLI solo se usa la primera vez o si la guardada era inválida.
    if not window.geometry_restored:
        window.geometry(f"{width}x{height}")
    window.protocol("WM_DELETE_WINDOW", window.on_close)
    window.mainloop()
    return 0


__all__ = ["ARQGenWindow", "launch", "PALETTE"]

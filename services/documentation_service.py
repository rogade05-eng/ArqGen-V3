"""DocumentationService (spec sections 68, 69, 70, 106) — FASE 34.

Facade of the documentation module. Turns project data into the document
set of spec 68 (memoria descriptiva, memoria técnica, especificaciones,
cuadros, listados, informes) plus the automatic per-module documentation
of spec 106. Drawings (spec 69) and parametric templates (spec 70) are
persisted entities with audit + events like every other module.

Generated documents are deterministic: the regression suite hashes them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError
from domain.documentation import (
    DOCUMENT_KINDS, DRAWING_ELEMENTS, Drawing, DocTemplate, SHEET_SIZES,
    VIEWS,
)
from engines.documentation_engine import (
    area_table, build_titleblock, collect_placeholders, dimension_text,
    elements_table, format_table, module_doc, openings_table,
    render_html_document, render_markdown_document, render_template,
)
from services.context import ProjectContext

APP_VERSION_DOC = "1.3.0"


class DocumentationService:
    """Facade of the documentation module (spec 68-70, 106)."""

    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context

    # ------------------------------------------------------------------
    # Parametric variables (spec 70)
    # ------------------------------------------------------------------
    def variables(self) -> Dict[str, Any]:
        """Full ``{{VAR}}`` map of the project (spec 70 examples included)."""
        project = self.ctx.project
        pid = project.id
        spaces = self.ctx.architecture.list("SPACE", pid)
        walls = self.ctx.architecture.list("WALL", pid)
        openings = self.ctx.architecture.list("OPENING", pid)
        levels = self.ctx.architecture.list("LEVEL", pid)

        total_area = 0.0
        for s in spaces:
            try:
                total_area += s.area_m2()
            except Exception:  # degenerate boundary
                pass
        wall_length = 0.0
        for w in walls:
            wall_length += ((w.end[0] - w.start[0]) ** 2
                            + (w.end[1] - w.start[1]) ** 2) ** 0.5
        doors = [o for o in openings if o.kind == "DOOR"]
        windows = [o for o in openings if o.kind == "WINDOW"]

        qto = self._qto_totals()
        budget_total = self._budget_total()

        from core.entities.base import utc_now
        return {
            "PROJECT.NAME": project.name,
            "PROJECT.CODE": project.code,
            "PROJECT.CLIENT": project.client,
            "CLIENT.NAME": project.client,
            "PROJECT.ADDRESS": project.address,
            "PROJECT.DESCRIPTION": project.description,
            "PROJECT.CURRENCY": project.currency,
            "PROJECT.LEVELS": len(levels),
            "PROJECT.SPACES": len(spaces),
            "PROJECT.WALLS": len(walls),
            "PROJECT.OPENINGS": len(openings),
            "PROJECT.TOTAL_AREA": round(total_area, 2),
            # Área neta de muro del motor QTO (fórmula WALL_AREA_NET).
            "QTO.TOTAL_WALL_AREA": round(qto.get("WALL_AREA_NET", 0.0), 2),
            "QTO.TOTAL_WALL_LENGTH": round(qto.get("WALL_LENGTH", 0.0), 2),
            "QTO.TOTAL_WALL_VOLUME": round(qto.get("WALL_VOLUME", 0.0), 2),
            "QTO.DOOR_COUNT": len(doors),
            "QTO.WINDOW_COUNT": len(windows),
            "QTO.OPENING_COUNT": len(openings),
            "QTO.FLOOR_AREA": round(total_area, 2),
            "BUDGET.TOTAL": round(budget_total, 2),
            "BUDGET.CURRENCY": project.currency,
            "STRUCT.ELEMENTS": self.ctx.structure.count("ELEMENT", pid),
            "INST.NETWORKS": self.ctx.installations.count("NETWORK", pid),
            "INST.NODES": self.ctx.installations.count("NODE", pid),
            "CLASH.OPEN": sum(
                1 for c in self.ctx.clash_repo.list(pid) if c.status == "OPEN"),
            "DATE": utc_now().strftime("%Y-%m-%d"),
            "APP.VERSION": APP_VERSION_DOC,
        }

    def render_text(self, text: str) -> str:
        """Render any text against the project variable map (spec 70)."""
        return render_template(text, self.variables())

    def template_placeholders(self, template: DocTemplate) -> List[str]:
        return template.placeholder_names()

    # ------------------------------------------------------------------
    # Drawings (spec 69)
    # ------------------------------------------------------------------
    def create_drawing(self, sheet: str, sheet_size: str = "A3",
                       scale: str = "1:50", orientation: str = "LANDSCAPE",
                       view: str = "PLAN", level_ref: str = "",
                       titleblock: Optional[Dict[str, str]] = None) -> Drawing:
        level_id = None
        if level_ref:
            level = self.ctx.architecture.get_level_by_name_or_code(level_ref)
            level_id = level.id
        code = self.ctx.next_code("DOCUMENTATION", "DRAWING")
        drawing = Drawing(project_id=self.ctx.project.id, code=code,
                          sheet=sheet, sheet_size=sheet_size, scale=scale,
                          orientation=orientation, view=view,
                          level_id=level_id,
                          titleblock=dict(titleblock or {}))
        if not drawing.titleblock:
            drawing.titleblock = build_titleblock(
                {"name": self.ctx.project.name, "client": self.ctx.project.client,
                 "address": self.ctx.project.address},
                {"sheet": sheet, "scale": scale, "view": view,
                 "orientation": orientation, "sheet_size": sheet_size},
                APP_VERSION_DOC)
        self.ctx.documentation.drawings.save(drawing)
        self._audit("drawing.create", drawing, None,
                    [("DRAWING_CREATED", {"sheet": sheet, "view": view})])
        return drawing

    def list_drawings(self) -> List[Dict[str, Any]]:
        return [
            {"code": d.code, "sheet": d.sheet, "size": d.sheet_size,
             "scale": d.scale, "view": d.view, "orientation": d.orientation,
             "elements": len(d.annotations),
             "level": d.level_id or ""}
            for d in self.ctx.documentation.drawings.list(self.ctx.project.id)
        ]

    def add_drawing_element(self, drawing_ref: str, kind: str,
                            payload: Dict[str, Any]) -> Dict[str, Any]:
        drawing = self._resolve_drawing(drawing_ref)
        old = self._snapshot(drawing)
        record = drawing.add_element(kind, payload)
        self.ctx.documentation.drawings.save(drawing)
        self._audit("drawing.add_element", drawing, old,
                    [("DRAWING_CHANGED", {"kind": kind, "sheet": drawing.sheet})])
        return record

    def delete_drawing(self, drawing_ref: str) -> str:
        drawing = self._resolve_drawing(drawing_ref)
        old = self._snapshot(drawing)
        self.ctx.documentation.drawings.delete(drawing.id)
        self._audit("drawing.delete", drawing, old,
                    [("DRAWING_DELETED", {"sheet": drawing.sheet})])
        return drawing.id

    def dimension_for(self, drawing_ref: str, real_mm: float) -> str:
        """Dimension text of a real length on a given sheet (spec 69)."""
        drawing = self._resolve_drawing(drawing_ref)
        return dimension_text(real_mm, drawing.scale_denominator)

    # ------------------------------------------------------------------
    # Parametric templates (spec 70)
    # ------------------------------------------------------------------
    def create_template(self, name: str, body: str,
                        headers: str = "", footers: str = "",
                        sections: Optional[List[str]] = None,
                        tables: Optional[List[str]] = None) -> DocTemplate:
        existing = self.ctx.documentation.templates.get_by_name(name)
        if existing is not None:
            raise DomainError(
                message=f"Ya existe una plantilla con el nombre: {name}",
                code="ARQ-DOC-007",
                suggested_action="Use otro nombre o actualice la existente.")
        code = self.ctx.next_code("DOCUMENTATION", "DOC_TEMPLATE")
        template = DocTemplate(project_id=self.ctx.project.id, code=code,
                               name=name, body=body, headers=headers,
                               footers=footers, sections=list(sections or []),
                               tables=list(tables or []))
        self.ctx.documentation.templates.save(template)
        self._audit("template.create", template, None,
                    [("TEMPLATE_CREATED", {"name": name})])
        return template

    def list_templates(self) -> List[Dict[str, Any]]:
        return [
            {"code": t.code, "name": t.name,
             "placeholders": len(t.placeholder_names()),
             "sections": len(t.sections), "tables": len(t.tables)}
            for t in self.ctx.documentation.templates.list(self.ctx.project.id)
        ]

    def render_template(self, template_ref: str) -> str:
        """Render a stored template against project variables (spec 70)."""
        template = self._resolve_template(template_ref)
        body = render_template(template.body, self.variables())
        return render_markdown_document(template.name,
                                        [(s, "") for s in template.sections],
                                        header=body, footer=template.footers)

    # ------------------------------------------------------------------
    # Document generation (spec 68 / 106)
    # ------------------------------------------------------------------
    def generate_memoria(self) -> str:
        """Memoria descriptiva del proyecto."""
        v = self.variables()
        pid = self.ctx.project.id
        levels = self.ctx.architecture.list("LEVEL", pid)
        spaces = self.ctx.architecture.list("SPACE", pid)
        space_rows = []
        for s in spaces:
            try:
                area = s.area_m2()
                perimeter = s.perimeter_m()
            except Exception:
                area, perimeter = 0.0, 0.0
            space_rows.append({"name": s.name, "type": s.space_type,
                               "area": round(area, 2),
                               "perimeter": round(perimeter, 2)})
        levels_md = "\n".join(
            f"- **{lv.name}**: cota +{lv.elevation_m:.2f} m, altura {lv.height_m:.2f} m"
            for lv in levels) or "(sin niveles)"
        sections = [
            ("Objeto del documento",
             "La presente memoria descriptiva recoge la definición general del "
             "proyecto tal como consta en el modelo de ARQ GEN. Todos los datos "
             "proceden del modelo único y son reproducibles de forma determinista."),
            ("Datos generales",
             f"- Proyecto: **{v['PROJECT.NAME']}**\n"
             f"- Cliente: {v['CLIENT.NAME']}\n"
             f"- Dirección: {v['PROJECT.ADDRESS']}\n"
             f"- Divisa del presupuesto: {v['BUDGET.CURRENCY']}\n"
             f"- Fecha de emisión: {v['DATE']}"),
            ("Descripción",
             v["PROJECT.DESCRIPTION"] or "(sin descripción)"),
            ("Niveles", levels_md),
            ("Cuadro de locales", format_table(
                space_rows, ["name", "type", "area", "perimeter"])),
            ("Superficies",
             f"Superficie total de locales: **{v['PROJECT.TOTAL_AREA']} m²**. "
             f"Longitud total de muros: {v['QTO.TOTAL_WALL_LENGTH']} m. "
             f"Vanos registrados: {v['PROJECT.OPENINGS']} "
             f"({v['QTO.DOOR_COUNT']} puertas, {v['QTO.WINDOW_COUNT']} ventanas)."),
        ]
        seccion_detalles = self._detalles_seccion()
        if seccion_detalles:
            sections.append(seccion_detalles)
        return render_markdown_document(
            f"Memoria descriptiva — {v['PROJECT.NAME']}", sections)

    def generate_tecnica(self) -> str:
        """Memoria técnica: sistemas de instalaciones y estructura."""
        v = self.variables()
        pid = self.ctx.project.id
        networks = self.ctx.installations.list("NETWORK", pid)
        net_rows = []
        for n in networks:
            net_rows.append({
                "code": n.code, "name": n.name, "system": n.system,
                "nodes": len(self.ctx.installations.nodes_of(n.id)),
                "segments": len(self.ctx.installations.segments_of(n.id)),
            })
        elements = self.ctx.structure.list("ELEMENT", pid)
        el_rows = [{"code": e.code, "name": e.name, "kind": e.kind,
                    "material": e.material_id or ""} for e in elements]
        sections = [
            ("Objeto", "Memoria técnica de las instalaciones y la estructura "
                       "según el estado actual del modelo."),
            ("Redes de instalaciones", format_table(
                net_rows, ["code", "name", "system", "nodes", "segments"])),
            ("Estructura", format_table(
                el_rows, ["code", "name", "kind", "material"])),
            ("Resumen",
             f"Redes: {v['INST.NETWORKS']} ({v['INST.NODES']} nodos). "
             f"Elementos estructurales: {v['STRUCT.ELEMENTS']}. "
             f"Interferencias abiertas: {v['CLASH.OPEN']}."),
        ]
        return render_markdown_document(
            f"Memoria técnica — {v['PROJECT.NAME']}", sections)

    def generate_especificaciones(self) -> str:
        """Especificaciones por familia de obra (muros, vanos, instalaciones)."""
        v = self.variables()
        pid = self.ctx.project.id
        walls = self.ctx.architecture.list("WALL", pid)
        thicknesses = sorted({w.thickness_m for w in walls})
        heights = sorted({w.height_m for w in walls})
        openings = self.ctx.architecture.list("OPENING", pid)
        sections = [
            ("General",
             "Las presentes especificaciones se derivan del modelo y de los "
             "catálogos del proyecto. Cualquier cambio en el modelo invalida y "
             "regenera las cantidades asociadas (espec 74: grafo de dependencias)."),
            ("Fábricas y muros",
             "Espesores presentes en el modelo: "
             + ", ".join(f"{t:.2f} m" for t in thicknesses) + ". "
             + "Alturas de muro: "
             + ", ".join(f"{h:.2f} m" for h in heights) + "."),
            ("Carpinterías",
             f"Total de vanos: {len(openings)}. Puertas: {v['QTO.DOOR_COUNT']}; "
             f"ventanas: {v['QTO.WINDOW_COUNT']}. Las dimensiones de cada vano "
             "constan en el cuadro de vanos."),
            ("Instalaciones",
             f"El proyecto contiene {v['INST.NETWORKS']} redes con "
             f"{v['INST.NODES']} nodos. Los diámetros, secciones y conductos "
             "resultan de los motores de dimensionado por disciplina."),
        ]
        seccion_detalles = self._detalles_seccion()
        if seccion_detalles:
            sections.append(seccion_detalles)
        return render_markdown_document(
            f"Especificaciones — {v['PROJECT.NAME']}", sections)

    def generate_cuadros(self) -> str:
        """Cuadros: superficies y vanos."""
        pid = self.ctx.project.id
        spaces = []
        for s in self.ctx.architecture.list("SPACE", pid):
            try:
                spaces.append({"name": s.name, "area": round(s.area_m2(), 2),
                               "perimeter": round(s.perimeter_m(), 2),
                               "occupancy": float(s.metadata.get("occupancy", 0.0))})
            except Exception:
                continue
        openings = []
        hosts = {w.id: w.code for w in self.ctx.architecture.list("WALL", pid)}
        for o in self.ctx.architecture.list("OPENING", pid):
            openings.append({"code": o.code, "kind": o.kind,
                             "host": hosts.get(o.wall_id, ""),
                             "width": o.width_m, "height": o.height_m})
        areas = format_table(area_table(spaces),
                             ["name", "area", "perimeter", "occupancy",
                              "area_per_person"])
        vanos = format_table(openings_table(openings),
                             ["code", "kind", "host", "width", "height", "area"])
        return render_markdown_document(
            f"Cuadros — {self.ctx.project.name}",
            [("Cuadro de superficies", areas),
             ("Cuadro de vanos", vanos)])

    def generate_listados(self) -> str:
        """Listados de elementos del modelo."""
        pid = self.ctx.project.id
        cols = ["code", "name", "kind"]
        walls = [{"code": w.code, "name": w.code, "kind": "WALL",
                  "level": w.level_id, "thickness": w.thickness_m,
                  "height": w.height_m}
                 for w in self.ctx.architecture.list("WALL", pid)]
        openings = [{"code": o.code, "name": o.code, "kind": o.kind,
                     "level": o.level_id, "width": o.width_m,
                     "height": o.height_m}
                    for o in self.ctx.architecture.list("OPENING", pid)]
        spaces = [{"code": s.code, "name": s.name, "kind": s.space_type,
                   "level": s.level_id, "area": round(s.area_m2(), 2)}
                  for s in self.ctx.architecture.list("SPACE", pid)]
        return render_markdown_document(
            f"Listados — {self.ctx.project.name}",
            [("Muros", format_table(walls, ["code", "name", "level",
                                            "thickness", "height"])),
             ("Vanos", format_table(openings, cols + ["level", "width", "height"])),
             ("Locales", format_table(spaces, ["code", "name", "kind",
                                               "level", "area"]))])

    def generate_informe(self) -> str:
        """Informe de validación e interferencias (estado del proyecto)."""
        v = self.variables()
        pid = self.ctx.project.id
        clashes = self.ctx.clash_repo.list(pid)
        status_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        for c in clashes:
            status_counts[c.status] = status_counts.get(c.status, 0) + 1
            severity_counts[c.severity] = severity_counts.get(c.severity, 0) + 1
        clash_rows = [{"code": c.code, "type": c.type,
                       "severity": c.severity, "status": c.status,
                       "a": c.object_a_code, "b": c.object_b_code,
                       "distance": c.distance} for c in clashes[:50]]
        sections = [
            ("Resumen ejecutivo",
             f"El proyecto {v['PROJECT.NAME']} contiene {v['PROJECT.SPACES']} "
             f"locales, {v['PROJECT.WALLS']} muros y {v['PROJECT.OPENINGS']} "
             f"vanos. Presupuesto vigente: {v['BUDGET.TOTAL']} "
             f"{v['BUDGET.CURRENCY']}."),
            ("Interferencias",
             f"Total: {len(clashes)}. Por estado: {status_counts}. "
             f"Por severidad: {severity_counts}."),
            ("Detalle", format_table(
                clash_rows, ["code", "type", "severity", "status", "a", "b",
                             "distance"])),
            ("Conclusión",
             "Se recomienda resolver las interferencias de severidad HIGH y "
             "CRITICAL antes de emitir la documentación de obra. El resto de "
             "los sistemas del modelo se autovalidan mediante los motores de "
             "cada disciplina."),
        ]
        return render_markdown_document(
            f"Informe — {v['PROJECT.NAME']}", sections)

    def module_docs(self, module: str) -> str:
        """Automatic module documentation (spec 106: README/API/DATA MODEL/...)."""
        summaries = self._module_summaries()
        if module not in summaries:
            raise DomainError(
                message=f"Módulo sin documentación automática: {module}",
                code="ARQ-DOC-008",
                context={"available": sorted(summaries)},
                suggested_action="Elija uno de los módulos disponibles.")
        return module_doc(module, summaries[module])

    def available_documents(self) -> List[str]:
        return list(DOCUMENT_KINDS)

    # ------------------------------------------------------------------
    # Detalles constructivos recomendados (v3.8.0)
    # ------------------------------------------------------------------
    def tipologia_proyecto(self) -> str:
        """Tipología constructiva declarada en el asistente.

        Lee el metadata ``edificacion.tipologia_constructiva`` del
        primer BUILDING del proyecto; sin edificio (o sin tipología)
        devuelve "" y la memoria no lleva sección de detalles.
        """
        try:
            pid = self.ctx.project.id
            for building in self.ctx.architecture.list("BUILDING", pid):
                edificacion = building.metadata.get("edificacion") \
                    if isinstance(building.metadata, dict) else None
                tipo = edificacion.get("tipologia_constructiva") \
                    if isinstance(edificacion, dict) else ""
                if tipo:
                    return str(tipo)
        except Exception:  # noqa: BLE001 — sin edificio, sin aviso
            return ""
        return ""

    def detalles_recomendados(self) -> List[Dict[str, Any]]:
        """Fichas de detalles recomendados para la tipología.

        Usa la biblioteca de detalles (adaptada a la edición regional
        activa, si la hay); tipología desconocida o biblioteca ausente
        → lista vacía (aconseja, nunca bloquea).
        """
        tipo = self.tipologia_proyecto()
        if not tipo:
            return []
        try:
            from domain.detalles import (CATEGORIA_NOMBRE,
                                         detalles_para_tipologia,
                                         get_registry)
            recomendados = detalles_para_tipologia(get_registry(), tipo)
        except Exception:  # noqa: BLE001 — sin biblioteca, sin aviso
            return []
        filas: List[Dict[str, Any]] = []
        for detalle in recomendados:
            filas.append({
                "detalle": detalle.id,
                "nombre": detalle.nombre,
                "categoria": CATEGORIA_NOMBRE.get(detalle.categoria,
                                                  detalle.categoria),
                "espesor_mm": round(detalle.espesor_total_mm),
                "norma": detalle.norma,
            })
        return filas

    def _detalles_seccion(self) -> Optional[Tuple[str, str]]:
        """Sección markdown de detalles recomendados (o None)."""
        filas = self.detalles_recomendados()
        if not filas:
            return None
        tipo = self.tipologia_proyecto()
        try:
            from domain.detalles import get_registry
            registro = get_registry()
            edicion = ("biblioteca universal (sin edición regional "
                       "activa)" if registro.region_is_base() else
                       f"edición regional activa: {registro.region_name}")
            aviso = registro.disclaimer
        except Exception:  # noqa: BLE001 — sin biblioteca, sin aviso
            edicion = "biblioteca universal"
            aviso = "Verifica siempre la norma local vigente."
        tabla = format_table(
            filas, ["detalle", "nombre", "categoria", "espesor_mm"])
        cuerpo = (
            f"La tipología constructiva declarada en el asistente de "
            f"edificación es **{tipo}**; la biblioteca de detalles "
            f"recomienda las soluciones de abajo ({edicion}). La ficha "
            "completa de cada una (capas del corte, notas de obra y "
            "exportación SVG/PDF/PNG) está en Herramientas ▸ Detalles "
            "constructivos.\n\n" + tabla + "\n\n" + aviso)
        return ("Detalles constructivos recomendados", cuerpo)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def export_document(self, markdown_text: str, out_path: str,
                        fmt: str = "md") -> str:
        """Write a generated document as md/html/txt/pdf (deterministic)."""
        from core.errors import ExportError
        fmt = fmt.lower()
        if fmt == "pdf":
            from exporters.markdown_pdf import export_markdown_pdf
            return export_markdown_pdf(markdown_text, out_path)
        if fmt == "md" or fmt == "txt":
            text = markdown_text
        elif fmt == "html":
            text = render_html_document(self.ctx.project.name,
                                        markdown_text)
        else:
            raise ExportError(
                message=f"Formato de documento no soportado: {fmt}",
                code="ARQ-EXP-DOC-001",
                context={"allowed": ["md", "txt", "html", "pdf"]})
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return out_path

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _qto_totals(self) -> Dict[str, float]:
        try:
            from services.quantity_service import QuantityService
            return QuantityService(self.ctx).totals_by_formula()
        except Exception:
            return {}

    def _budget_total(self) -> float:
        try:
            from services.budget_service import BudgetService
            budget = BudgetService(self.ctx).latest_budget()
            return float(budget.get("total_cost", 0.0)) if budget else 0.0
        except Exception:
            return 0.0

    def _resolve_drawing(self, ref: str) -> Drawing:
        repo = self.ctx.documentation.drawings
        drawing = repo.get_by_code(ref) if ref else None
        if drawing is None:
            raise DomainError(
                message=f"Plano no encontrado: {ref}",
                code="ARQ-DOC-009",
                suggested_action="Liste los planos con 'docs drawing-list'.")
        return drawing

    def _resolve_template(self, ref: str) -> DocTemplate:
        repo = self.ctx.documentation.templates
        template = repo.get_by_code(ref) or repo.get_by_name(ref)
        if template is None:
            raise DomainError(
                message=f"Plantilla no encontrada: {ref}",
                code="ARQ-DOC-010",
                suggested_action="Liste las plantillas con 'docs templates'.")
        return template

    def _snapshot(self, entity: Any) -> Dict[str, Any]:
        from services.commands_impl import entity_snapshot
        return entity_snapshot(entity)

    def _audit(self, command: str, entity: Any, old: Optional[Dict[str, Any]],
               events: List[Tuple[str, Dict[str, Any]]]) -> None:
        from core.audit.models import make_audit_event
        new = self._snapshot(entity)
        event = make_audit_event(self.ctx.user, entity.id, entity.ENTITY_TYPE,
                                 command, old, new, "", "OK")
        self.ctx.audit_repo.append(event)
        for event_type, payload in events:
            self.ctx.emit(event_type, {"id": entity.id,
                                       "type": entity.ENTITY_TYPE,
                                       "code": entity.code, **payload})

    def _module_summaries(self) -> Dict[str, Dict[str, Any]]:
        """Introspection table for spec-106 automatic documentation."""
        return {
            "core": {
                "purpose": "Núcleo: entidades, errores ARQ-XXX, unidades, "
                           "eventos, comandos undo/redo transaccional.",
                "api": ["EventBus.emit", "CommandBus.execute/undo/redo",
                        "UnitRegistry.convert", "CodeAllocator.next_code"],
                "data_model": ["Entity", "AuditEvent", "Event", "Quantity"],
                "rules": ["Conversión sólo entre dimensiones compatibles",
                          "Índices nunca son identificadores (espec 6)"],
                "formulas": [],
                "tests": ["test_010_core_units_events_commands"],
                "changelog": ["1.0.0 versión inicial",
                              "1.3.0 DataError añadido a la taxonomía"],
            },
            "architecture": {
                "purpose": "Site/Building/Level/Zone/Space/Wall/Opening y "
                           "relaciones espaciales (espec 20-23).",
                "api": ["ArchitectureService.create_wall",
                        "ArchitectureService.create_space",
                        "ArchitectureService.create_opening"],
                "data_model": ["Site", "Building", "Level", "Zone", "Space",
                               "Wall", "Opening", "SpaceRelationship"],
                "rules": ["Los vanos pertenecen a un muro"],
                "formulas": ["area_m2 = área del polígono del local"],
                "tests": ["test_001_project", "test_005_architecture"],
                "changelog": ["1.0.0 versión inicial"],
            },
            "qto": {
                "purpose": "Motor de cantidades con fórmulas JSON y recálculo "
                           "incremental por input_hash (espec 51-52, 74).",
                "api": ["QuantityService.compute_all",
                        "QuantityService.compute_object",
                        "QuantityService.totals_by_formula"],
                "data_model": ["QuantityResult", "FormulaSpec"],
                "rules": ["condition SQL-like segura en fórmulas"],
                "formulas": ["WALL_AREA = length × height",
                             "WALL_VOLUME = area × thickness"],
                "tests": ["test_030_qto_budget_prices", "test_040_undo_incremental"],
                "changelog": ["1.1.0 fórmulas de instalaciones",
                              "1.2.0 fórmulas de estructura y seguridad"],
            },
            "budget": {
                "purpose": "Presupuesto por capítulos/partidas/recursos con "
                           "histórico de precios append-only (espec 53-62).",
                "api": ["BudgetService.compute_budget",
                        "PricingService.set_price",
                        "PricingService.price_history"],
                "data_model": ["Resource", "PriceList", "PriceEntry",
                               "BudgetChapter", "BudgetItem"],
                "rules": ["Los precios nunca se sobrescriben: se añaden"],
                "formulas": ["item_total = Σ resource_qty × price"],
                "tests": ["test_030_qto_budget_prices"],
                "changelog": ["1.1.0 plantilla residential_full_v1"],
            },
            "installations": {
                "purpose": "Redes Nodo→Tramo multi-disciplina con trazado, "
                           "rutas y validación (espec 24-33).",
                "api": ["InstallationsService.connect",
                        "InstallationsService.trace",
                        "InstallationsService.circuit_check"],
                "data_model": ["InstallNetwork", "InstallNode", "InstallSegment"],
                "rules": ["Redes eléctricas radiales por protección",
                          "Sumideros sólo en desagües/pluviales"],
                "formulas": ["caída de tensión 2ρLI/S (√3ρLI/S en 3φ)",
                             "Hazen-Williams, Manning, Darcy-Weisbach",
                             "método racional Q=C·i·A/3600"],
                "tests": ["test_080_installations", "test_081_electrical",
                          "test_082_sanitary_hvac", "test_083_stormwater_gas_telecom"],
                "changelog": ["1.1.0 núcleo + eléctrico + sanitario + HVAC",
                              "1.2.0 pluviales, gas, telecom, seguridad"],
            },
            "structure": {
                "purpose": "Materiales, secciones, acciones, combinaciones y "
                           "verificación de elementos (espec 33-34).",
                "api": ["StructureService.analyze_element",
                        "StructureService.solve_truss"],
                "data_model": ["Material", "Section", "Element", "LoadCase",
                               "Combination"],
                "rules": ["Combinaciones ULS/SLS normalizadas"],
                "formulas": ["pandeo de Euler Pcr=π²EI/(kL)²",
                             "flecha elástica 5wL⁴/(384EI)"],
                "tests": ["test_084_structure"],
                "changelog": ["1.2.0 versión inicial"],
            },
            "security": {
                "purpose": "CCTV, fuego, intrusión, acceso y perímetro sobre "
                           "el modelo de redes (espec 37-49).",
                "api": ["SecurityService.coverage", "SecurityService.fire_check",
                        "SecurityService.bom"],
                "data_model": ["Redes SECURITY_*", "Dispositivos FOV/CCTV/FIRE"],
                "rules": ["Matriz causa/efecto versionada en ruleset"],
                "formulas": ["cobertura FOV por ray casting",
                             "almacenamiento CCTV = cámaras × bitrate × horas"],
                "tests": ["test_085_security"],
                "changelog": ["1.2.0 versión inicial"],
            },
            "coordination": {
                "purpose": "Motor de interferencias HARD/SOFT/CLEARANCE/ACCESS/"
                           "MAINTENANCE/ROUTE y ciclo de vida (espec 35-36).",
                "api": ["CoordinationService.run_detection",
                        "CoordinationService.set_status"],
                "data_model": ["Clash"],
                "rules": ["deduplicación por par de objetos + tipo"],
                "formulas": [],
                "tests": ["test_086_clash"],
                "changelog": ["1.2.0 versión inicial"],
            },
            "documentation": {
                "purpose": "Planos, plantillas paramétricas y generación de "
                           "documentos (espec 68-70, 106).",
                "api": ["DocumentationService.generate_memoria",
                        "DocumentationService.render_template",
                        "DocumentationService.create_drawing"],
                "data_model": ["Drawing", "DocTemplate"],
                "rules": ["Las variables sin resolver son error (ARQ-DAT-DOC)"],
                "formulas": ["escala: real = papel × denominador"],
                "tests": ["test_090_documentation"],
                "changelog": ["1.3.0 versión inicial"],
            },
        }


__all__ = ["DocumentationService", "APP_VERSION_DOC"]

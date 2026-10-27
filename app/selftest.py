"""Selftest: end-to-end verification used after packaging (build pipeline).

Runs the complete chain in a temporary directory: project → geometry →
QTO → budget → exports → round-trip. Exits non-zero on any failure so
the compile .bat can stop the pipeline.
"""

from __future__ import annotations

import math
import os
import re
import struct
import sys
import tempfile
import threading
import traceback
from typing import List, Tuple

from app.lifecycle import setup_logging, get_logger


def run_selftest(console: bool = True) -> Tuple[bool, List[str]]:
    checks: List[str] = []
    ok = True
    logger = get_logger("arqgen.selftest")
    tmp = tempfile.mkdtemp(prefix="arqgen_selftest_")
    try:
        from services.context import ApplicationContext

        application = ApplicationContext()
        setup_logging(os.path.join(tmp, "logs"), level="ERROR", console=False)

        # 1) Demo end-to-end
        from app.demo import build_demo
        db_path = os.path.join(tmp, "selftest.arqgen")
        context = build_demo(application, db_path)
        checks.append("demo: OK")
        context.close()

        # 2) Reopen and verify persistence
        context = application.open_project(db_path)
        walls = context.architecture.list("WALL", context.project.id)
        assert len(walls) == 7, f"esperados 7 muros, hay {len(walls)}"
        checks.append(f"persistencia: OK ({len(walls)} muros)")

        # 3) QTO totals present
        totals = {}
        for row in context.quantities_repo.all(context.project.id):
            totals[row["formula_code"]] = totals.get(row["formula_code"], 0.0) + row["final_quantity"]
        assert totals.get("WALL_LENGTH", 0) > 0, "WALL_LENGTH ausente"
        assert totals.get("WALL_VOLUME", 0) > 0, "WALL_VOLUME ausente"
        checks.append(f"QTO: OK (WALL_VOLUME={totals.get('WALL_VOLUME', 0):.2f} m3)")

        # 4) Budget present and positive
        budget = context.budget_repo.latest_budget(context.project.id)
        assert budget and budget["total_cost"] > 0, "presupuesto ausente"
        checks.append(f"presupuesto: OK (total={budget['total_cost']:.2f} {budget['currency']})")

        # 5) Exports
        from services.export_service import ExportService
        export_service = ExportService()
        out_dir = os.path.join(tmp, "out")
        dxf_path = export_service.export(context, "DXF", os.path.join(out_dir, "selftest.dxf"))
        json_path = export_service.export(context, "JSON", os.path.join(out_dir, "selftest.json"))
        xlsx_path = export_service.export(context, "XLSX", os.path.join(out_dir, "selftest.xlsx"))
        csv_path = export_service.export(context, "CSV", os.path.join(out_dir, "selftest.csv"),
                                         options={"table": "budget"})
        for path in (dxf_path, json_path, xlsx_path, csv_path):
            assert os.path.exists(path) and os.path.getsize(path) > 0, f"export vacío: {path}"
        checks.append("exportación: OK (DXF/JSON/XLSX/CSV)")

        # 6) DXF readable (walls live in per-level layouts)
        import ezdxf
        doc = ezdxf.readfile(dxf_path)
        wall_entities = []
        for layout in doc.layouts.names():
            wall_entities.extend(
                e for e in doc.layouts.get(layout) if e.dxf.layer == "ARQ-WALL")
        assert len(wall_entities) >= 7, f"DXF sin muros suficientes: {len(wall_entities)}"
        checks.append(f"DXF legible: OK ({len(wall_entities)} entidades ARQ-WALL)")

        # 7) JSON round-trip
        from services.import_service import ImportService
        importer = ImportService(application)
        result = importer.import_snapshot(
            json_path, os.path.join(tmp, "roundtrip.arqgen"), approve=True)
        assert result["approved"] and result["inserted"]["WALL"] == 7
        checks.append("round-trip JSON: OK")

        # 8) Validation runs
        from services.analysis_service import ValidationService
        validation = ValidationService(context).validate_project()
        checks.append(f"validación: OK (estado={validation.status.value})")

        # 9) Installations networks persisted and valid (spec 24-26, 30-32)
        networks = context.installations.list("NETWORK", context.project.id)
        assert len(networks) == 12, f"esperadas 12 redes, hay {len(networks)}"
        total_nodes = sum(len(context.installations.nodes_of(n.id)) for n in networks)
        total_segments = sum(len(context.installations.segments_of(n.id)) for n in networks)
        assert total_nodes >= 75, f"nodos de instalaciones insuficientes: {total_nodes}"
        assert total_segments >= 60, f"tramos de instalaciones insuficientes: {total_segments}"
        from services.installations_service import InstallationsService
        installations_service = InstallationsService(context)
        for network in networks:
            report = installations_service.validate_network(network.code)
            assert report["status"] in ("VALID", "VALID_WITH_WARNINGS"), \
                f"red {network.code} inválida: {report['status']}"
        checks.append(f"instalaciones: OK ({len(networks)} redes, {total_nodes} nodos, "
                      f"{total_segments} tramos)")

        # 10) Electrical summary deterministic (spec 27)
        panel = [n for n in context.installations.nodes_of(networks[0].id)
                 if n.kind == "PANEL"][0]
        summary = installations_service.panel_summary(panel.code)
        assert abs(summary["total_connected_w"] - 7180.0) < 0.5, \
            f"potencia conectada inesperada: {summary['total_connected_w']}"
        checks.append(f"eléctrico: OK (7180 W en 3 circuitos, "
                      f"principal {summary['main_breaker_a']:.0f} A)")

        # 11) QTO includes installation quantities (spec 24, 51)
        install_totals = {}
        for row in context.quantities_repo.all(context.project.id):
            install_totals[row["formula_code"]] = install_totals.get(row["formula_code"], 0.0)
            install_totals[row["formula_code"]] += row["final_quantity"]
        assert install_totals.get("CONDUIT_LENGTH", 0) > 0, "CONDUIT_LENGTH ausente"
        assert install_totals.get("CONDUCTOR_LENGTH", 0) > 0, "CONDUCTOR_LENGTH ausente"
        assert install_totals.get("PIPE_LENGTH", 0) > 0, "PIPE_LENGTH ausente"
        assert install_totals.get("COOLING_UNITS", 0) >= 4, "COOLING_UNITS ausente"
        checks.append(f"QTO instalaciones: OK (CONDUIT_LENGTH="
                      f"{install_totals.get('CONDUIT_LENGTH', 0):.1f} m, "
                      f"COOLING_UNITS={install_totals.get('COOLING_UNITS', 0):.0f})")

        # 12) Stormwater sizing deterministic (spec 30)
        storm = [n for n in networks if n.system == "STORMWATER"][0]
        storm_report = installations_service.size_stormwater(storm.code)
        assert len(storm_report["rows"]) >= 4, "dimensionado pluvial incompleto"
        # 45+35 m2, C=0.90, i=100 mm/h -> Q = 0.9*100*80/3600 = 2.0 L/s
        assert abs(storm_report["captured_ls"] - 2.0) < 0.01, \
            f"captación esperada 2.0 L/s, hay {storm_report['captured_ls']}"
        assert storm_report["detention"]["volume_l"] > 0, "detención pluvial ausente"
        checks.append(f"pluvial: OK (captación={storm_report['captured_ls']:.2f} L/s, "
                      f"detención={storm_report['detention']['volume_l']:.0f} L)")

        # 13) Gas sizing + validation (spec 31)
        gas = [n for n in networks if n.system == "GAS"][0]
        gas_report = installations_service.size_gas(gas.code)
        assert len(gas_report["rows"]) == 6, "dimensionado de gas incompleto"
        assert gas_report["appliances"] == 2, "aparatos de gas inesperados"
        gas_validation = installations_service.validate_gas(gas.code)
        assert gas_validation["status"] in ("VALID", "VALID_WITH_WARNINGS"), \
            f"validación de gas: {gas_validation['status']}"
        checks.append(f"gas: OK (tramos={len(gas_report['rows'])}, "
                      f"estado={gas_validation['status']})")

        # 14) Telecom sizing (spec 32)
        telecom = [n for n in networks if n.system == "TELECOM"][0]
        telecom_report = installations_service.size_telecom(telecom.code)
        assert len(telecom_report["rows"]) == 6, "dimensionado telecom incompleto"
        assert telecom_report["racks"] and telecom_report["panels"], "resumen rack/panel ausente"
        for row in telecom_report["rows"]:
            if "fill_pct" in row:  # CONDUIT rows
                assert row["fill_pct"] <= 40.0 + 1e-9, "llenado de conducto telecom > 40 %"
        checks.append(f"telecom: OK (tramos={len(telecom_report['rows'])}, "
                      f"racks={len(telecom_report['racks'])})")

        # 15) Structure analyzed (spec 33-34)
        from services.structure_service import StructureService
        elements = context.structure.list("ELEMENT", context.project.id)
        assert len(elements) == 4, f"esperados 4 elementos estructurales, hay {len(elements)}"
        analyzed = [e for e in elements if e.num("utilization") > 0
                    or e.num("truss_max_kn") > 0]
        assert len(analyzed) == 4, "elementos estructurales sin analizar"
        assert any(e.num("utilization") <= 1.0 for e in analyzed), \
            "elemento agotado en la demo"
        structure_service = StructureService(context)
        steel = structure_service.steel_quantities()
        assert steel["steel_weight_kg"] > 0, "peso de acero ausente"
        checks.append(f"estructura: OK (4 elementos, acero "
                      f"{steel['steel_weight_kg']:.0f} kg)")

        # 16) Security systems (spec 37-49)
        from services.security_service import SecurityService
        sec_service = SecurityService(context)
        cctv_network = [n for n in networks if n.system == "CCTV"][0]
        coverage = sec_service.cctv_coverage(cctv_network.code)
        assert coverage["cameras"] >= 2, "cámaras CCTV ausentes"
        fire_network = [n for n in networks if n.system == "FIRE_ALARM"][0]
        fire_status = sec_service.fire_check(fire_network.code)["status"]
        assert fire_status in ("VALID", "VALID_WITH_WARNINGS"), \
            f"detección de incendios: {fire_status}"
        intrusion_network = [n for n in networks if n.system == "INTRUSION"][0]
        intrusion_status = sec_service.intrusion_check(intrusion_network.code)["status"]
        assert intrusion_status in ("VALID", "VALID_WITH_WARNINGS"), \
            f"intrusión: {intrusion_status}"
        access_network = [n for n in networks if n.system == "ACCESS_CONTROL"][0]
        access_status = sec_service.access_check(access_network.code)["status"]
        assert access_status in ("VALID", "VALID_WITH_WARNINGS"), \
            f"control de acceso: {access_status}"
        perimeter_network = [n for n in networks if n.system == "PERIMETER"][0]
        assert sec_service.perimeter_check(perimeter_network.code)["report"]["ok"], \
            "perímetro con huecos"
        checks.append(f"seguridad: OK (CCTV {coverage['cameras']} cámaras, fuego "
                      f"{fire_status}, intrusión {intrusion_status}, acceso "
                      f"{access_status}, perímetro OK)")

        # 17) Coordination: demo coordinada sin choques duros (spec 35-36)
        from services.coordination_service import CoordinationService
        clash_service = CoordinationService(context)
        clash_report = clash_service.run_detection()
        assert clash_report["by_type"].get("HARD", 0) == 0, \
            f"demo con choques duros: {clash_report['by_type']}"
        checks.append(f"coordinación: OK (sin HARD, abiertas "
                      f"{clash_report['open']})")

        # 18) PRECONS project analysis (spec 59-60)
        from services.precons_service import PreconsService
        precons = PreconsService(context)
        precons.load_ruleset("precons_cuba_v1")
        precons_report = precons.analyze_project()
        assert precons_report["total"] > 0, "análisis PRECONS vacío"
        assert len(precons_report["analyses"]) >= 3, "análisis PRECONS incompleto"
        checks.append(f"PRECONS: OK (total={precons_report['total']:.2f} "
                      f"{precons_report['currency']})")

        # 19) IFC export (spec 63, 67)
        ifc_path = export_service.export(
            context, "IFC", os.path.join(out_dir, "selftest.ifc"))
        assert os.path.exists(ifc_path) and os.path.getsize(ifc_path) > 1000, \
            "export IFC vacío"
        with open(ifc_path, "r", encoding="utf-8") as handle:
            ifc_text = handle.read()
        assert ifc_text.startswith("ISO-10303-21;"), "IFC sin cabecera SPF"
        assert "FILE_SCHEMA(('IFC4'))" in ifc_text, "IFC sin esquema IFC4"
        assert ifc_text.count("IFCWALL(") == 7, "IFC sin muros completos"
        assert ifc_text.count("IFCDOOR(") == 4 and \
            ifc_text.count("IFCWINDOW(") == 3, "IFC sin vanos completos"
        checks.append(f"IFC: OK ({ifc_text.count('= IFC')} entidades, "
                      f"7 muros, 4 puertas, 3 ventanas)")

        # 20) Documentación (FASE 34, spec 68-70): memoria determinista
        from services.documentation_service import DocumentationService
        docs = DocumentationService(context)
        memoria = docs.generate_memoria()
        assert "Proyecto Demo Residencial" in memoria, "memoria sin proyecto"
        assert memoria == docs.generate_memoria(), "memoria no determinista"
        template = docs.create_template("selftest", "Cliente {{CLIENT.NAME}}.")
        rendered = docs.render_template(template.code)
        assert "Cliente Demo" in rendered, "plantilla sin resolver"
        variables = docs.variables()
        assert variables["QTO.DOOR_COUNT"] == 4 and \
            variables["QTO.WINDOW_COUNT"] == 3, "variables de vanos incorrectas"
        context.commit()
        checks.append("documentación: OK (memoria determinista, plantilla, "
                      "4 puertas + 3 ventanas)")

        # 21) Optimización multiobjetivo (FASE 35, spec 19): 12 objetivos
        from engines.optimization_engine import OBJECTIVES, Variant
        from services.optimization_service import OptimizationService
        current = OptimizationService(context).evaluate_current()
        assert set(current.objectives) == set(OBJECTIVES), \
            "objetivos del spec 19 incompletos"
        assert abs(current.objectives["AREA"] - 80.0) < 0.01, \
            f"AREA esperado 80, hay {current.objectives['AREA']}"
        worse = Variant(name="PEOR", objectives={
            **current.objectives, "COST": current.objectives["COST"] + 1})
        front = OptimizationService(context).pareto([current, worse])
        assert front["pareto_front"] == ["CURRENT"], "frente de Pareto erróneo"
        checks.append(f"optimización: OK (12 objetivos, AREA="
                      f"{current.objectives['AREA']:.1f} m2, Pareto OK)")

        # 22) Backup y recuperación (FASE 38, spec 81)
        from persistence.backup.service import BackupService
        backup_service = BackupService(os.path.join(tmp, "backups"))
        backup_service.create_full_backup(db_path, label="selftest")
        incremental = backup_service.create_incremental_backup(db_path)
        assert incremental["changed"], "incremental no detecta cambios"
        assert backup_service.recover(db_path)["recovered"] is False, \
            "recuperación innecesaria"
        verified = backup_service.verify_all()
        assert verified and all(v["integrity"] == "ok" for v in verified), \
            "backups con integridad comprometida"
        checks.append(f"backup: OK ({len(verified)} copias íntegras, "
                      "incremental y journal OK)")

        # 23) Benchmark y cachés (FASE 40, spec 86-87)
        from app.benchmark import cache_inventory, run_benchmarks
        caches = {c["cache"] for c in cache_inventory()}
        assert {"geometry_cache", "rules_cache", "catalog_cache",
                "calculation_cache", "routing_cache",
                "coverage_cache"} <= caches, "cachés del spec 87 incompletas"
        bench = run_benchmarks(context, iterations={
            "geometry_area": 2, "spatial_adjacency": 1, "qto_compute_all": 1,
            "budget_compute": 1, "optimization_current": 1,
            "documentation_memoria": 1, "clash_detection": 1, "export_json": 1})
        assert len(bench) == 8, "operaciones de benchmark incompletas"
        checks.append("benchmark: OK (8 operaciones medidas, 6 cachés)")

        # 24) Registro de plugins (FASE 15/§31, §88-89): GAS como plugin
        #     de instalaciones y lista §88 completa cargada sin errores.
        from plugins.plugin_api import PluginLoader
        loader = PluginLoader(application)
        loader.load_all()
        broken = [e for e in loader.loaded if e.error or e.plugin is None]
        assert not broken, f"plugins con error de carga: {broken}"
        registry = {e.plugin.plugin_id: e.plugin for e in loader.loaded}
        assert {"architecture", "structure", "installations", "cctv",
                "fire", "intrusion", "access", "perimeter", "qto",
                "budget", "bim", "documentation",
                "gas"} <= set(registry), "lista §88 incompleta"
        assert "installations" in registry["gas"].dependencies, \
            "gas debe declarar dependencia de installations (§31)"
        checks.append(f"plugins: OK ({len(registry)} cargados, §88 + gas§31)")

        # 25) GUI (FASE 90, spec 90-93): smoke de la ventana si hay
        #     display; en entornos headless se omite sin fallar.
        try:
            import tkinter as _tk
            _probe = _tk.Tk()
            _probe.withdraw()
            _probe.destroy()
            has_display = True
        except Exception:  # noqa: BLE001
            has_display = False
        if has_display:
            from ui.app_window import ARQGenWindow
            gui_window = ARQGenWindow(context, application)
            gui_window.update()
            assert len(gui_window.tree.get_children()) == 13, \
                "la GUI debe mostrar las 13 disciplinas del spec 91"
            gui_window.search_entry.insert(0, "ARQ")
            gui_window.run_search()
            assert gui_window._result_rows, "búsqueda GUI sin resultados"
            gui_window.fit_view()
            gui_window.update()
            gui_window.destroy()
            checks.append("GUI: OK (13 disciplinas, búsqueda, lienzo)")
        else:
            checks.append("GUI: omitida (sin display)")

        # 26) Edición GUI headless (FASE 90.1): PropertyEditor y
        #     EditService por las mismas fachadas que la CLI, con
        #     auditoría UPDATE_ENTITY y undo persistente §77.
        from ui.models import ExplorerModel, PropertyEditor, EditService
        gui_explorer = ExplorerModel(context)
        gui_edit = EditService(context, gui_explorer)
        wall_row = next(r for r in gui_explorer.rows_for("ARCHITECTURE")
                        if r.type == "WALL" and r.entity is not None)
        old_thickness = wall_row.entity.thickness_m
        PropertyEditor.edit(context, wall_row, "thickness_m", "0.33")
        wall_saved = context.architecture.get("WALL", wall_row.uid)
        assert abs(wall_saved.thickness_m - 0.33) < 1e-9, \
            "la edición GUI no persistió"
        audit_rows = [e for e in context.audit_repo.recent(limit=100)
                      if e["command"] == "UPDATE_ENTITY"
                      and e["object_id"] == wall_row.uid]
        assert audit_rows, "edición GUI sin auditoría UPDATE_ENTITY"
        space_created = gui_edit.create("SPACE", {
            "level_ref": gui_edit.choices("levels")[0],
            "name": "Local selftest"})
        assert len(space_created.boundary) == 4, \
            "creación GUI de local sin contorno"
        from app.undo_service import PersistentUndoService
        PersistentUndoService(context).undo()  # revierte la creación
        context.commit()
        assert context.architecture.get("SPACE", space_created.id) is None, \
            "undo GUI no revirtió la creación"
        PropertyEditor.edit(context, wall_row, "thickness_m",
                            str(old_thickness))
        checks.append("edición GUI: OK (propiedad auditada, creación, undo)")

        # 27) Scripts .bat (solo en desarrollo; en el ejecutable congelado
        #     no viajan junto al binario). Incidencia real: los .bat con
        #     fin de linea LF de Unix se caen en Windows sin ejecutar nada
        #     y sin dejar log. Garantias: CRLF, ASCII sin BOM, pause en
        #     errores y cd /d al directorio del script.
        if getattr(sys, "frozen", False):
            checks.append("scripts .bat: omitido (ejecutable compilado)")
        else:
            bat_root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            bat_names = [
                "00_VERIFICAR_ENTORNO.bat", "01_INSTALAR_DEPENDENCIAS.bat",
                "02_PRUEBAS.bat", "03_COMPILAR.bat", "04_EJECUTAR.bat",
                "05_EJECUTAR_COMPILADO.bat", "06_DEMO.bat", "07_LIMPIAR.bat",
                "08_GUI.bat", "09_GUI_COMPILADO.bat",
            ]
            for bat_name in bat_names:
                bat_path = os.path.join(bat_root, bat_name)
                assert os.path.isfile(bat_path), f"falta {bat_name}"
                with open(bat_path, "rb") as bat_fh:
                    bat_raw = bat_fh.read()
                assert not bat_raw.startswith(b"\xef\xbb\xbf"), \
                    f"{bat_name} con BOM UTF-8"
                bat_lf = bat_raw.count(b"\n")
                assert bat_lf > 0, f"{bat_name} vacío"
                assert bat_lf == bat_raw.count(b"\r\n") == bat_raw.count(b"\r"), \
                    f"{bat_name} sin fin de linea CRLF (cmd.exe lo aborta)"
                bat_raw.decode("ascii")
                assert b"pause" in bat_raw, f"{bat_name} sin pause en errores"
                assert bat_raw.split(b"\r\n", 1)[0] == b"@echo off", \
                    f"{bat_name} sin @echo off"
            checks.append(f"scripts .bat: OK ({len(bat_names)} CRLF+ASCII+pause)")

        # 28) Importers spec 94: flat catalog auto-detection -> ruleset
        from importers.catalog import CatalogImporter
        from importers.dxf_reader import (DxfImporter, WALL_LAYER_HINTS,
                                          SPACE_LAYER_HINTS)
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.title = "BASE"
        sheet.append(["Partida", "Nombre", "UM", "Recurso", "Rendimiento", "Merma"])
        sheet.append(["E-01", "Muro de bloque", "m3", "BLOQUE", 72, 5])
        sheet.append(["E-01", "", "", "CEMENTO", 18, 3])
        cat_path = os.path.join(tmp, "selftest_catalogo.xlsx")
        book.save(cat_path)
        payload_cat, report_cat = CatalogImporter().apply(
            cat_path, code="SELFTEST",
            out_path=os.path.join(tmp, "selftest_ruleset.json"))
        assert report_cat["errors"] == [], \
            f"errores de importación: {report_cat['errors']}"
        assert len(payload_cat["work_items"]) == 1, "partida no importada"
        assert len(payload_cat["work_items"][0]["indicators"]) == 2, \
            "indicadores incompletos"
        assert os.path.getsize(os.path.join(tmp, "selftest_ruleset.json")) > 0
        assert WALL_LAYER_HINTS and SPACE_LAYER_HINTS
        _ = DxfImporter  # DXF importer available in the bundle
        checks.append("importadores §94: OK (catálogo plano -> ruleset)")

        # 29) UX v1.7.1: tema oscuro, ayuda dinámica y guía de flujo.
        #     Contratos: tooltips obligatorios, ayudas por campo de los
        #     formularios, mensajes de menú, guía de 4 pasos y el motor
        #     de siguiente paso (sin Tk: contenido puro verificable
        #     también en el ejecutable headless).
        from ui.help import (FIELD_HINTS, GUIDE_STEPS, MENU_HINTS,
                             TOOLTIPS, next_hint)
        from ui.app_window import ACCELERATORS as UX_ACCEL, PALETTE
        for key in ("guide", "new_object", "edit", "search_btn",
                    "level_combo", "canvas", "props_edit", "state_btn"):
            assert len(TOOLTIPS.get(key, "")) > 10, f"tooltip {key} vacío"
        from ui.models import CREATE_SPECS
        for entity_type, (_disc, fields) in CREATE_SPECS.items():
            for param, *_rest in fields:
                assert param in FIELD_HINTS, \
                    f"{entity_type}.{param} sin ayuda dinámica"
        for label in ("Archivo", "Editar", "Ver", "Herramientas", "Ayuda"):
            assert label in MENU_HINTS and len(MENU_HINTS[label]) > 20, \
                f"menú sin mensaje orientador: {label}"
        assert len(GUIDE_STEPS) == 4, "la guía rápida debe tener 4 pasos"
        assert UX_ACCEL.get("<F1>") == "show_quick_guide", "F1 sin guía"
        assert PALETTE["selection"] == "#FF7A88", "paleta oscura cambiada"
        assert "local" in next_hint(spaces=0) \
            and "muro" in next_hint(spaces=2, walls=0)
        checks.append("UX v1.7.1: OK (tema oscuro, ayuda dinámica, guía)")

        # 30) Asistente de diseño v1.7.2 + interfaz 100 % en español.
        #     Contratos: fix del selector de niveles (choice_values),
        #     etiquetas españolas de estados/eventos/cálculos y el
        #     asistente headless valida, planifica y crea el local con
        #     sus muros y vanos por las fachadas oficiales.
        from ui import wizard as wiz
        from ui.models import (choice_values as ux_choice_values,
                               status_label as ux_status,
                               describe_event as ux_event,
                               calc_type_label as ux_calc)
        assert ux_choice_values("levels", lambda s: ["Nivel A"]) == \
            ["Nivel A"], "choice_values no consulta la fuente dinámica"
        assert ux_status("DRAFT") == "Borrador (DRAFT)", "estado en inglés"
        assert "Objeto creado" in ux_event("OBJECT_CREATED") \
            and "OBJECT_CREATED" in ux_event("OBJECT_CREATED"), \
            "diario sin trazabilidad"
        assert ux_calc("QTO") == "Cantidades (QTO)", "cálculo en inglés"
        for entity_type in ("SPACE", "WALL"):
            spec = dict(CREATE_SPECS)[entity_type][1]
            level_field = next(f for f in spec if f[0] == "level_ref")
            assert isinstance(level_field[4], str), \
                f"{entity_type}.level_ref debe ser fuente dinámica"
        data = wiz.LocalWizardData(new_level=True,
                                   new_level_name="Nivel ST",
                                   name="Local ST", with_window=True)
        assert wiz.validate_step(0, data) == [], "paso 1 debería validar"
        assert wiz.validate_step(1, data) == [], "paso 2 debería validar"
        assert wiz.validate_step(2, data) == [], "paso 3 debería validar"
        plan = wiz.build_plan(data)
        ops = [op for op, _p in plan]
        assert ops == ["LEVEL", "SPACE", "WALL", "WALL", "WALL", "WALL",
                       "DOOR", "WINDOW"], f"plan inesperado: {ops}"
        created = wiz.apply_plan(data, context)
        assert created["level"] and created["space"], "asistente no creó"
        assert len(created["walls"]) == 4, "el local requiere 4 muros"
        assert created["door"] and created["window"], "vanos ausentes"
        assert len(context.architecture.list("WALL",
                                             context.project.id)) >= 4
        checks.append("asistente de diseño: OK (plan 4 muros + vanos, "
                      "creación auditada, UI en español)")

        # 31) Edificación completa v1.8.0: el asistente headless traza
        #     niveles, locales en fila con pasillo, muros fusionados
        #     (una pared compartida = UN muro), puertas automáticas +
        #     entrada, ventanas de fachada, relaciones espaciales y
        #     deja los requerimientos (clima/arquitectura/estructura)
        #     en el metadata de cada entidad, todo por las fachadas
        #     oficiales (CommandBus, auditoría, eventos) y transaccional.
        from ui import building_wizard as bwiz
        edif_path = os.path.join(tmp, "selftest_edificio.arqgen")
        context_edif = application.create_project(edif_path,
                                                  name="Selftest Edificio")
        try:
            datos = bwiz.BuildingWizardData(name="Casa Selftest")
            datos.levels = [bwiz.LevelSpec("Planta Baja", 3.0),
                            bwiz.LevelSpec("Piso 1", 3.0)]
            datos.rooms = bwiz.preset_rooms("Vivienda", "Planta Baja")
            datos.rooms += bwiz.preset_rooms("Vivienda", "Piso 1")
            datos.relations = [bwiz.RelationSpec("Sala", "Comedor",
                                                 "Adyacente a", True)]
            resumen = bwiz.apply_plan(datos, context_edif)
            assert resumen["building"], "edificio no creado"
            assert resumen["levels_created"] == 2, "niveles incompletos"
            # v2.5.0: dos niveles → escalera automática y núcleo rígido
            # en esquina (12 locales + escalera + 2 pasillos + 2 núcleos
            # = 17 espacios).
            assert resumen["spaces"] == 17, "locales incompletos"
            assert resumen["walls"] == 32, "muros fusionados incorrectos"
            assert resumen["doors"] == 18, "puertas incompletas"
            assert resumen["windows"] == 10, "ventanas incompletas"
            assert resumen["relations"] == 1, "relación ausente"
            pid = context_edif.project.id
            edificio = context_edif.architecture.list("BUILDING", pid)[0]
            assert "edificacion" in edificio.metadata, "req. globales"
            sala = next(s for s in
                        context_edif.architecture.list("SPACE", pid)
                        if s.name == "Sala"
                        and s.metadata.get("requerimientos"))
            req = sala.metadata["requerimientos"]
            # v3.43.0: el mínimo de la Sala baja de 12 a 9 m2 (DNA de
            # vivienda social)
            assert req["arquitectonicos"]["area_minima_m2"] == 9.0, \
                "DNA no aplicado"
            assert "portante" in next(iter(
                context_edif.architecture.list("WALL", pid))).metadata, \
                "muros sin metadata estructural"
            niveles = context_edif.architecture.list("LEVEL", pid)
            assert all(nv.building_id == edificio.id for nv in niveles), \
                "niveles sin edificio"
            avisos = bwiz.dna_advisories(datos, context_edif)
            assert any("zona húmeda" in a for a in avisos), \
                "avisos del conocimiento ausentes"
        finally:
            context_edif.close()
        checks.append("edificación completa: OK (2 niveles, 17 espacios "
                      "con escalera automática y núcleo rígido, 32 muros "
                      "fusionados, 18 puertas, 10 ventanas, "
                      "requerimientos en metadata)")

        # 32) Catálogo PRECONS III real v1.9.0: el ruleset versionado
        #     completo (RoPres 3.30) carga desde resources con 15981
        #     renglones y 4383 recursos oficiales; índices O(1),
        #     búsqueda, secciones, precio oficial con desglose,
        #     parámetros y límites normativos como datos.
        from engines.precons_engine import PreconsRuleset, official_price
        from app.paths import resource_path as _res_path
        from core.errors import DomainError as _DomainError
        ruleset_full = PreconsRuleset.from_file(_res_path(
            "rulesets", "precons_iii_rospres_330.json"))
        assert ruleset_full.code == "precons_iii_rospres_330"
        assert ruleset_full.version == "3.30", "versión RoPres"
        assert len(ruleset_full.work_items) == 15981, "renglones incompletos"
        assert len(ruleset_full.resources) == 4383, "recursos incompletos"
        kinds = {r["kind"] for r in ruleset_full.resources}
        assert kinds == {"MATERIAL", "EQUIPMENT", "LABOR"}, kinds
        assert len(ruleset_full.parameters) == 8, "parámetros ausentes"
        assert len(ruleset_full.limits) == 4, "límites ausentes"
        renglon = ruleset_full.item("011111")
        assert renglon["price_ref"] > 0 and renglon["sec"] == "01"
        desglose = official_price(ruleset_full, "011111")
        assert abs(desglose["material"] + desglose["labor"]
                   + desglose["equipment"] - desglose["total"]) < 0.011, \
            "desglose oficial inconsistente"
        assert len(ruleset_full.sections()) == 38, "secciones del índice"
        assert any("hormigon" in h["name"].lower()
                   for h in ruleset_full.search("hormigon", limit=20))
        try:
            ruleset_full.item("XX-NO-EXISTE")
            raise AssertionError("código inexistente aceptado")
        except _DomainError as err:
            assert len(err.context.get("available", [])) <= 15, \
                "contexto de error sin acotar"
        checks.append("catálogo PRECONS III: OK (15981 renglones, 4383 "
                      "recursos, 38 secciones, precio oficial con desglose)")

        # 33) Salto v2.0.0: análisis de precio oficial directo,
        #     presupuesto por catálogo, exportadores PDF/SVG/PNG y
        #     presupuesto PRECONS conviviendo con el de plantilla.
        from engines.precons_engine import price_analysis as _pa
        _analysis = _pa(ruleset_full, "011111", 100.0, {})
        assert _analysis.mode == "official", "modo oficial no activo"
        assert abs(_analysis.total_price - 2681.0) < 0.01, \
            "análisis oficial incorrecto"
        from services.precons_budget_service import PreconsBudgetService
        _svc = PreconsBudgetService(context)
        _svc.ruleset = ruleset_full
        _svc.add_item("011111", 500)
        _svc.add_item("020112", 2)
        assert len(_svc.lines()) == 2, "líneas del presupuesto"
        _tree = _svc.tree()
        assert len(_tree["chapters"]) == 2, "capítulos por sección"
        assert abs(_tree["total"] - 72849.04) < 0.05, "total presupuesto"
        _csv_path = os.path.join(tmp, "selftest_presu.csv")
        _svc.save_csv(_csv_path)
        assert os.path.exists(_csv_path), "CSV del presupuesto"
        from exporters.pdf_exporter import export_budget_pdf as _ebp
        _pdf_path = os.path.join(tmp, "selftest_presu.pdf")
        _ebp(_tree, _pdf_path, context.project.name)
        assert open(_pdf_path, "rb").read(8).startswith(b"%PDF"), "PDF"
        from exporters.png_exporter import export_budget_chart_png as _epng
        _png_path = os.path.join(tmp, "selftest_grafico.png")
        _epng(_tree, _png_path, context.project.name)
        assert open(_png_path, "rb").read(8) == \
            b"\x89PNG\r\n\x1a\n", "PNG del gráfico"
        _svg_path = os.path.join(tmp, "selftest_plano.svg")
        from exporters.svg_exporter import export_plan_svg as _esvg
        _esvg(context, _svg_path, title=context.project.name)
        assert "<svg" in open(_svg_path, encoding="utf-8").read(), "SVG"
        checks.append("salto v2.0.0: OK (análisis oficial, presupuesto "
                      "por catálogo persistente, PDF/SVG/PNG stdlib)")

        # 34) Asistente de edificación v2.1.0: uso social con programa
        #     sugerido, paso bioclimático/instalaciones y MOTOR DE
        #     VARIANTES de planta (3 esquemas × espejo, puntuados).
        from ui.building_wizard import (
            BuildingWizardData as _bwd, USAGE_TYPES as _usages,
            apply_usage_program as _aup, generate_variants as _gvar,
            suggested_installations as _sinst,
        )
        assert len(_usages) >= 9, "usos sociales"
        _bdata = _bwd()
        _bdata.usage_type = "Escuela primaria"
        _rooms, _rels = _aup(_bdata)
        assert _rooms >= 8 and _rels >= 1, "programa del uso social"
        _bdata.installations = ["Eléctrica", "Sanitaria",
                                "Energía solar"]
        _bdata.lot_width_m = 25.0
        _bdata.lot_depth_m = 18.0
        _variants = _gvar(_bdata)
        assert len(_variants) >= 6, "variantes de planta"
        assert _variants[0].rank == 1 \
            and _variants[0].score >= _variants[-1].score, \
            "orden de variantes por puntuación"
        _patio = next(v for v in _variants if v.scheme == "patio")
        assert _patio.layouts[0].corridor is not None \
            and _patio.layouts[0].corridor.space_type == "PATIO", \
            "patio central del esquema patio"
        assert len(_patio.layouts[0].doors) >= \
            len(_patio.layouts[0].rooms), \
            "cada local con puerta a la galería del patio"
        checks.append("asistente v2.1.0: OK (usos sociales con programa "
                      "sugerido, bioclimática/instalaciones, 6 variantes "
                      "de planta puntuadas)")

        # 35) TEMA HOSPITALARIO v2.2.0: usos Policlínico/Hospital,
        #     DNA de quirófano/urgencias/hospitalización, programa
        #     MULTI-NIVEL (crea niveles), puertas críticas sugeridas
        #     e instalaciones recomendadas (A/C + gas medicinal).
        assert "Policlínico" in _usages and "Hospital" in _usages, \
            "usos hospitalarios"
        _hdata = _bwd()
        _hdata.usage_type = "Hospital"
        _hrooms, _hrels = _aup(_hdata)
        assert _hrooms >= 18, "locales del programa hospitalario"
        assert len(_hdata.levels) >= 3, "niveles hospitalarios creados"
        _h_types = {r.space_type for r in _hdata.rooms}
        assert {"OPERATING_ROOM", "STERILIZATION_ROOM", "WARD",
                "EMERGENCY_ROOM", "IMAGING_ROOM", "LABORATORY",
                "PHARMACY"} <= _h_types, "tipos hospitalarios del DNA"
        assert any(rel.with_door for rel in _hdata.relations), \
            "puertas críticas hospitalarias"
        assert "Ventilación mecánica / A/C" in _sinst("Hospital") \
            and "Gas" in _sinst("Hospital"), \
            "instalaciones sugeridas del hospital"
        _hdata.installations = list(_sinst("Hospital"))
        _hvariants = _gvar(_hdata)
        assert len(_hvariants) >= 6, "variantes del hospital"
        checks.append("asistente v2.2.0: OK (tema hospitalario: policlínico "
                      "y hospital multi-nivel con quirófanos, urgencias, "
                      "esterilización, hospitalización, imagenología y "
                      "farmacia; puertas críticas e instalaciones A/C/gas)")

        # 36) FORMAS, ESTILOS, TERRENO y ESCALERAS v2.3.0: catálogos,
        #     motor de formas compuestas (L/T/U/H/cruz/articulada),
        #     desnivel por terreno (cota por local) y escalera STAIR.
        from ui.building_wizard import (
            PLAN_SHAPES as _shapes, ARCHITECTURAL_STYLES as _styles,
            TERRAIN_TYPES as _terrains, STAIR_MODES as _smodes,
            suggested_plan_shape as _sshape, stair_geometry as _sgeo,
            stairs_wanted as _swanted, generate_variants as _gvar36,
            BuildingWizardData as _bwd36, apply_usage_program as _aup36,
        )
        assert len(_shapes) >= 10 and len(_styles) >= 10, \
            "catálogos de formas y estilos"
        assert len(_terrains) >= 3 and len(_smodes) == 3, \
            "catálogos de terreno y escaleras"
        assert _sshape("Hospital") == "En H", "forma sugerida del hospital"
        _steps, _run = _sgeo(1.5)
        assert _steps >= 9 and 2.4 <= _run <= 4.8, "geometría de escalera"
        _fdata = _bwd36()
        _fdata.usage_type = "Escuela primaria"
        _aup36(_fdata)
        _fdata.terrain_type = _terrains[2]     # pendiente fuerte
        _fdata.plan_shape = "En L"
        from ui.building_wizard import build_layout as _bl36
        _flayouts, _fadv = _bl36(_fdata)
        _frises = {p.floor_rise_m for p in _flayouts[0].rooms}
        assert 1.5 in _frises, "desnivel dentro de la planta"
        assert any(p.space_type == "STAIR"
                   for p in _flayouts[0].rooms), "escalera colocada"
        assert _swanted(_fdata), "escalera automática por desnivel"
        _fdata2 = _bwd36()
        _fdata2.usage_type = "Vivienda"
        _aup36(_fdata2)
        _fdata2.plan_shape = "En L"
        _fvars = _gvar36(_fdata2)
        _enl = next(v for v in _fvars if v.scheme == "en_L")
        _lnames = [p.name for p in _enl.layouts[0].all_rooms]
        assert len(_enl.layouts[0].extra_corridors) == 0 and \
            len(_lnames) >= 7, "trazado en L con pasillo y ala"
        assert any(d.is_door for d in _enl.layouts[0].doors), \
            "puertas del trazado en L"
        checks.append("asistente v2.3.0: OK (formas en planta L/T/U/H/"
                      "cruz/articulada con 18 variantes, estilos con "
                      "consejos, terreno irregular con desnivel y cota "
                      "por local, escaleras automáticas STAIR)")

        # 37) PATIOS EN LAS ALAS, ALEROS y MÁS RELACIONES v2.4.0:
        #     las alas largas de L/T/U/cruz ganan un patio interior con
        #     puertas de galería; el contorno del alero se calcula y
        #     rodea el edificio sin atravesarlo; estilos 14 con
        #     sugerencia por uso y relaciones ampliadas (puertas
        #     críticas + adyacencias extra) en todos los usos.
        from ui.building_wizard import (
            ARCHITECTURAL_STYLES as _sty37,
            generate_variants as _gvar37,
            suggested_architectural_style as _sst37,
        )
        from core.geometry.engine import eaves_outline_segments as _eos37b
        assert len(_sty37) == 14, "estilos arquitectónicos v2.4.0"
        assert _sst37("Hospital") == "High-tech", "estilo por uso"
        _pdata = _bwd()
        _pdata.usage_type = "Policlínico"
        _aup(_pdata)
        _puvars = _gvar37(_pdata)
        _pu = next(v for v in _puvars if v.scheme == "en_U")
        _upatios = [p for p in _pu.layouts[0].all_rooms
                    if p.is_corridor and p.space_type == "PATIO"
                    and p.name.startswith("Patio de ala")]
        assert _upatios, "patio de ala en la U del policlínico"
        assert any("galería del patio" in d.note
                   for d in _pu.layouts[0].doors), "puertas de galería"
        _hdata37 = _bwd()
        _hdata37.usage_type = "Hospital"
        _aup(_hdata37)
        assert any(rel.with_door for rel in _hdata37.relations
                   if {r.space_type for r in _hdata37.rooms
                       if r.name in (rel.a_name, rel.b_name)}
                   == {"WARD", "DINING_ROOM"}), "puerta sala–estar"
        _evas = _eos37b(_pu.layouts[0].all_rooms, 0.6)
        assert _evas, "contorno del alero calculado"
        _eps37 = 1e-9
        for _x1, _y1, _x2, _y2 in _evas:
            for _i in range(5):
                _t = _i / 4.0
                _px = _x1 + (_x2 - _x1) * _t
                _py = _y1 + (_y2 - _y1) * _t
                assert not any(p.x + _eps37 < _px < p.x + p.w - _eps37
                               and p.y + _eps37 < _py < p.y + p.d - _eps37
                               for p in _pu.layouts[0].all_rooms), \
                    "el alero no atraviesa el edificio"
        checks.append("asistente v2.4.0: OK (patios en las alas con "
                      "galería, aleros dibujados en preview y SVG, 14 "
                      "estilos con sugerencia por uso, relaciones y "
                      "puertas ampliadas)")

        # 38) FORMAS COMPUESTAS + PATIO CENTRAL y NÚCLEO RÍGIDO v2.5.0:
        #     cinco esquemas nuevos (L/T/H/cruz/articulada con patio
        #     central abrazado, con galería y puertas) y el núcleo de
        #     servicios en esquina (automático/siempre/no) como las
        #     escaleras.
        from ui.building_wizard import (
            CORE_ALWAYS as _ca38, CORE_MODES as _cm38,
            CORE_NEVER as _cn38, CORE_TYPE as _ct38,
            core_wanted as _cw38,
        )
        assert len(bwiz.SCHEME_LABELS) == 14, "esquemas del motor"
        _kdata = _bwd()
        _kdata.usage_type = "Hospital"
        _aup(_kdata)
        _kvars = _gvar37(_kdata)
        _hpatio = next(v for v in _kvars
                       if v.scheme == "en_H_patio")
        _patio38 = [p for p in _hpatio.layouts[0].all_rooms
                    if p.is_corridor and p.space_type == "PATIO"
                    and p.name.startswith("Patio central")]
        assert _patio38, "patio central en la H hospitalaria"
        assert any("galería del patio" in d.note
                   for d in _hpatio.layouts[0].doors), \
            "galería del patio central con puertas"
        _kdata.core_mode = _ca38
        assert _cw38(_kdata), "núcleo siempre"
        _kvars2 = _gvar37(_kdata)
        _vlin38 = next(v for v in _kvars2
                       if v.scheme == "lineal" and not v.mirror)
        _cores38 = [p for p in _vlin38.layouts[0].rooms
                    if p.space_type == _ct38]
        assert _cores38, "núcleo rígido en la variante lineal"
        _minx38 = min(p.x for p in _vlin38.layouts[0].all_rooms)
        _maxx38 = max(p.x + p.w for p in _vlin38.layouts[0].all_rooms)
        _miny38 = min(p.y for p in _vlin38.layouts[0].all_rooms)
        _maxy38 = max(p.y + p.d for p in _vlin38.layouts[0].all_rooms)
        assert any(abs(c.x - _minx38) < 1e-6
                   or abs(c.x + c.w - _maxx38) < 1e-6
                   or abs(c.y - _miny38) < 1e-6
                   or abs(c.y + c.d - _maxy38) < 1e-6
                   for c in _cores38), "núcleo en la envolvente"
        _kdata.core_mode = _cn38
        assert not _cw38(_kdata), "núcleo vetado"
        _kvars3 = _gvar37(_kdata)
        _vlin3 = next(v for v in _kvars3
                      if v.scheme == "lineal" and not v.mirror)
        assert not any(p.space_type == _ct38
                       for p in _vlin3.layouts[0].rooms), \
            "sin núcleo cuando se veta"
        _kdata.core_mode = "En el jardín"
        assert any("núcleo rígido" in e.lower()
                   for e in bwiz.validate_step(0, _kdata)), \
            "validación del modo del núcleo"
        assert _cm38 and len(_cm38) == 3, "modos del núcleo"
        checks.append("asistente v2.5.0: OK (5 formas compuestas con "
                      "patio central y galería, núcleo rígido en "
                      "esquinas automático/siempre/no, 28 variantes)")

        # 39) REPRESENTACIÓN ARQUITECTÓNICA v2.6.0: columnas según
        #     tipología, tramas por material, elevaciones, cortes con
        #     cimentación/losas/escalera, detalles y SVG de vistas.
        from core.geometry import representation as _rep39
        from core.geometry import structural as _st39
        from exporters import view_exporter as _ve39
        _rdata = _bwd()
        _rdata.usage_type = "Vivienda"
        _rdata.construction_type = "Hormigón armado (monolítico)"
        _aup(_rdata)
        _rvar = _gvar37(_rdata)[0]
        _cols39 = _st39.column_placements(_rvar.layouts, _rdata)
        assert _cols39, "columnas de la malla de pórtico"
        assert any(c.kind == "esquina" for c in _cols39), \
            "columnas de esquina del envolvente"
        for _key39 in ("mamposteria", "hormigon", "madera", "piedra",
                       "tierra", "acero", "panel", "galvanizado"):
            _segs39 = _rep39.hatch_segments(0.0, 0.0, 0.2, 5.0, _key39)
            for (_ax1, _ay1), (_ax2, _ay2) in _segs39:
                assert -1e-9 <= _ax1 <= 0.2 + 1e-9 \
                    and -1e-9 <= _ay1 <= 5.0 + 1e-9, "trama fuera"
        for _side39 in _rep39.ELEVATION_SIDES:
            _elev = _rep39.elevation_view(_rvar, _rdata, _side39)
            assert _elev.bounds()[3] > 3.0, "elevación con altura"
        for _axis39 in _rep39.SECTION_AXES:
            _secc = _rep39.section_view(_rvar, _rdata, _axis39)
            _tags39 = {p.tag for p in _secc.prims if p.tag}
            assert "cimentacion" in _tags39 and "losa" in _tags39, \
                f"corte {_axis39} incompleto"
        _dets39 = _rep39.detail_library(_rdata)
        assert len(_dets39) >= 5, "detalles de la tipología"
        _rsvg = os.path.join(tmp, "selftest_vista.svg")
        _ve39.export_view_svg(_rvar, _rdata, _rsvg, view="Planta",
                              title="selftest v2.6.0")
        _rsvg_txt = open(_rsvg, encoding="utf-8").read()
        assert "<pattern" in _rsvg_txt, "trama como patrón SVG"
        checks.append("representación v2.6.0: OK (columnas por "
                      "tipología, tramas de material, 4 elevaciones, "
                      "2 cortes con cimentación y losas, "
                      f"{len(_dets39)} detalles, SVG de vistas)")

        # 40) NORMATIVA NEUFERT v2.7.0: catálogo cargado, escalera con
        #     la fórmula de Blondel por uso (camillas: 1,80 m), pasillo
        #     y puerta de salud, sugerencias aplicadas, avisos
        #     normativos y bloque «normativa» del metadata.
        from domain.neufert import get_registry as _gnf40
        _nf40 = _gnf40()
        assert len(_nf40) >= 10, "catálogo Neufert cargado"
        assert "Neufert" in _nf40.fuente(), "fuente del catálogo"
        _sr40 = _nf40.stair_rule("Hospital")
        assert _sr40.blondel_ok, "Blondel 2h+p entre 0,60 y 0,64"
        assert _sr40.ancho_m >= 1.8, "escalera de camillas: 1,80 m"
        assert bwiz.suggested_corridor_width("Hospital") >= 2.4, \
            "pasillo de camillas: 2,40 m"
        assert bwiz.suggested_door_width("Hospital") >= 1.2, \
            "puerta de camilla: 1,20 m"
        assert bwiz.suggested_wall_thickness("Muros de piedra") >= 0.4, \
            "muro de piedra 0,40 m (Neufert)"
        _nd40 = _bwd()
        _nd40.usage_type = "Hospital"
        _aup(_nd40)
        _cambios40 = bwiz.apply_neufert_defaults(_nd40)
        assert _cambios40 and _nd40.corridor_width_m >= 2.4, \
            "la normativa Neufert sube el pasillo hospitalario"
        _nav40 = bwiz.neufert_advisories(_nd40)
        assert any("Neufert" in a for a in _nav40), "avisos normativos"
        _nmeta40 = bwiz.neufert_normativa_block(_nd40)
        assert "escalera" in _nmeta40 and "fuente" in _nmeta40, \
            "bloque «normativa» del metadata"
        _res40 = bwiz.step_summary(_nd40)
        assert "Normativa Neufert" in _res40, \
            "línea normativa en el resumen"
        checks.append("normativa Neufert v2.7.0: OK (Blondel por uso, "
                      "camillas 1,20/2,40 m en salud, sugerencias "
                      "aplicadas, avisos normativos y metadata)")

        # 41) EDICIONES REGIONALES NEUFERT v2.8.0: el libro adaptado
        #     por región (Cuba, México, Argentina, Colombia) con fusión
        #     profunda sobre la base; la base nunca se corrompe.
        _regs41 = _nf40.available_regions()
        _cod41 = {r["codigo"] for r in _regs41}
        assert {"cuba", "mexico", "argentina", "colombia"} <= _cod41, \
            "ediciones regionales instaladas"
        _nf40.set_region("cuba")
        assert _nf40.ceiling_for("Hospital") == 3.2, "techo tropical"
        assert _nf40.window_ratio()[0] == 0.2, "luz 1/5 en Cuba"
        assert _nf40.section("bioclimatica")[
            "alero_recomendado_m"] == 1.2, "alero de portal cubano"
        _bl41 = _nf40.stair_rule("Hospital")
        assert _bl41.blondel_ok and _bl41.ancho_m >= 1.8, \
            "Blondel universal intacto"
        assert not _nf40.set_region("brasil"), \
            "región inexistente cae a la base"
        assert _nf40.ceiling_for("Hospital") == 3.0, \
            "base intacta tras el rodeo (deepcopy)"
        _nr41 = _bwd()
        _nr41.usage_type = "Hospital"
        _nr41.neufert_region = "cuba"
        _aup(_nr41)
        _nb41 = bwiz.neufert_normativa_block(_nr41)
        assert _nb41["edicion_regional"]["codigo"] == "cuba", \
            "bloque «edicion_regional» del metadata"
        assert "evacuacion" in _nb41 and "salud" in _nb41.get("por_uso",
                                                              {}), \
            "evacuación y sección del uso en el bloque"
        _rs41 = bwiz.step_summary(_nr41)
        assert "Edición: Cuba" in _rs41, "edición en el resumen"
        checks.append("ediciones regionales Neufert v2.8.0: OK ("
                      f"{len(_regs41)} ediciones, Cuba tropical con "
                      "techo 3,20/luz 1/5/alero 1,20, Blondel "
                      "universal, base intacta y metadata regional)")

        # 42) INTERFAZ MODERNA v3.0.0: temas oscuro/claro con cambio
        #     en vivo, glifos por funcionalidad, logo determinista,
        #     preferencias persistentes y autoguardado por calma.
        from ui import icons as _ic42
        from ui import prefs as _pf42
        from ui import theme as _th42
        from app.autosave import AutoSaveService as _as42
        _base42 = dict(_th42.PALETTES["dark"])
        assert set(_th42.PALETTES["light"]) == set(_base42), \
            "los dos modos comparten los mismos tokens"
        _th42.set_mode("light")
        assert _th42.current_mode() == "light", "modo claro activo"
        assert _th42.COL_BG == _th42.PALETTES["light"]["bg"] != \
            _base42["bg"], "constantes re-vinculadas al modo claro"
        assert _th42.COL_CANVAS == \
            _th42.PALETTES["light"]["canvas"], "lienzo sincronizado"
        assert _th42.CANVAS_DARK["space_fill"] == \
            _th42.PALETTES["light"]["space_fill"], \
            "paleta del lienzo mutada en el sitio"
        assert len(_th42.ENTITY_COLORS) == 30, \
            "paleta de entidades presente en claro"
        _th42.set_mode("dark")
        assert _th42.COL_BG == _base42["bg"], \
            "vuelta al modo oscuro sin deriva"
        assert all(_ic42.glyph(k) for k in _ic42.REQUIRED_ICONS), \
            "glifos por funcionalidad completos"
        _png42 = _ic42.render_logo(32)
        assert _png42[:8] == b"\x89PNG\r\n\x1a\n" and \
            _ic42.render_logo(32) == _png42, "logo PNG determinista"
        _ico42 = _ic42.ico_bytes((16, 32, 64))
        assert _ico42[:4] == b"\x00\x00\x01\x00" and \
            struct.unpack("<H", _ico42[4:6])[0] == 3, \
            "ICO con 3 imágenes embebidas"
        _p42 = _pf42.load_prefs(
            path=os.path.join(tmp, "prefs_ausentes.json"))
        assert _p42["theme"] == "dark" and _p42["autosave"] is True, \
            "preferencias por defecto tolerantes"
        _pf42.save_prefs({"theme": "light", "autosave": False},
                         path=os.path.join(tmp, "prefs.json"))
        _p42b = _pf42.load_prefs(path=os.path.join(tmp, "prefs.json"))
        assert _p42b["theme"] == "light" and _p42b["autosave"] is False, \
            "preferencias persistidas y releídas"
        _estado42 = {"n": 0, "t": 0.0}
        _ctx42 = type("Ctx42", (), {"commit": staticmethod(
            lambda: _estado42.__setitem__("n", _estado42["n"] + 1))})()
        _svc42 = _as42(_ctx42, enabled=True, delay_ms=150,
                       clock=lambda: _estado42["t"])
        assert _svc42.on_event(type("Ev42", (), {"payload": {}})()), \
            "un cambio marca el proyecto pendiente"
        assert not _svc42.flush(), "el volcado respeta el retardo de calma"
        _estado42["t"] = 0.5
        assert _svc42.flush() and _estado42["n"] == 1, \
            "autoguardado ejecuta el commit tras la calma"
        assert not _svc42.flush(), "el volcado es idempotente"
        _svc42.enabled = False
        _svc42.on_event(type("Ev42", (), {"payload": {}})())
        assert not _svc42.due(), "autoguardado desactivado no acumula"
        checks.append("interfaz moderna v3.0.0: OK (temas oscuro/claro "
                      "en vivo con paleta de entidades, glifos por "
                      "función, logo PNG/ICO determinista, preferencias "
                      "persistentes y autoguardado por calma)")

        # -- check 43: certificación del catálogo PRECONS III (v3.1.0) -------
        from services.precons_service import CATALOG_BASELINE as _cb43, \
            certificar_catalogo as _cc43
        _rep43 = _cc43("precons_iii_rospres_330")
        assert _rep43["ok"], \
            "catálogo PRECONS certificado: " + "; ".join(_rep43["failures"])
        assert _rep43["counts"] == _cb43, \
            "recuentos del catálogo en la línea base (15981/4383/38)"
        assert _rep43["version"] == "3.30", "versión oficial RoPres 3.30"
        assert re.fullmatch(r"[0-9a-f]{64}", _rep43["sha256"] or ""), \
            "SHA256 del catálogo presente"
        checks.append("catálogo PRECONS certificado v3.1.0: OK (15981 "
                      "renglones, 4383 recursos [3569 materiales / 671 "
                      "equipos / 143 MO], 38 secciones, desglose de "
                      "precios consistente y SHA256 estable)")

        # -- check 44: diseño orgánico (v3.2.0) ------------------------------
        from core.geometry.organic import arc_polyline as _arc44, \
            chamfer_points as _ch44, fillet_points as _fi44
        import ui.building_wizard as _bw44
        _a44 = _arc44((0.0, 0.0), (10.0, 0.0), 1.5, 12)
        assert abs(_a44[0][0]) < 1e-9 and abs(_a44[-1][0] - 10.0) < 1e-9 \
            and abs(_a44[len(_a44) // 2][1] - 1.5) < 0.06, \
            "arco con extremos exactos y flecha en el centro"
        _c44 = _ch44((0.0, 0.0), (5.0, 0.0), (0.0, 5.0), 1.2)
        assert abs(_c44[0][0] - 1.2) < 1e-9 and abs(_c44[1][1] - 1.2) \
            < 1e-9, "chaflán a 45° recorta ambas aristas"
        _f44 = _fi44((0.0, 0.0), (6.0, 0.0), (0.0, 6.0), 1.5, 8)
        assert abs(_f44[0][0] - 1.5) < 1e-6 and abs(_f44[-1][1] - 1.5) \
            < 1e-6, "radón tangente a las aristas"
        for _code44 in _bw44.DISTRIBUCION_CODES:
            assert _bw44.distribution_code(
                _bw44.distribution_label(_code44)) == _code44, \
                "código/etiqueta de distribución round-trip"
        _d44 = _bw44.BuildingWizardData()
        _bw44.apply_usage_program(_d44)
        _d44.name = "Selftest orgánico"
        _d44.distribucion = "organica"
        _d44.corridor_width_m = 2.0
        _d44.semilla = 7
        _lay44, _ = _bw44.build_layout(_d44)
        _notas44 = _bw44.apply_distribucion(_d44, _lay44)
        _curvos44 = sum(1 for _l44 in _lay44 for _w44 in _l44.walls
                        if _w44.get("curve"))
        assert _curvos44 > 0 and _notas44, \
            "el gesto orgánico crea muros curvos y explica el gesto"
        for _l44 in _lay44:
            for _op44 in list(_l44.doors) + list(_l44.windows):
                assert 0 <= _op44.wall_index < len(_l44.walls), \
                    "vanos con muro válido tras el gesto"
                _w44 = _l44.walls[_op44.wall_index]
                assert _op44.offset_m + _op44.width_m \
                    <= _w44["length"] + 1e-6, \
                    "cada vano cabe en su muro tras el gesto"
        checks.append("diseño orgánico v3.2.0: OK (fondos escalonados "
                      "solo crecen, radones/chaflanes en la envolvente, "
                      "fachada en arco, pasillo serpenteante con galibo "
                      "y vanos intactos, semilla reproducible)")

        # -- check 45: vistas PNG/PDF + importador DXF en GUI (v3.3.0) -------
        from exporters import view_exporter as _ve45
        from ui import building_wizard as _bw45
        _data45 = _bw45.BuildingWizardData()
        _bw45.apply_usage_program(_data45)
        _data45.name = "Selftest vistas"
        _data45.distribucion = "organica"
        _data45.semilla = 3
        _var45 = _bw45.generate_variants(_data45)[0]
        _dir45 = os.path.join(tmp, "vistas45")
        for _fmt45, _mark45 in (("pdf", b"%PDF-1.4"),
                                ("png", b"\x89PNG\r\n\x1a\n")):
            _path45 = os.path.join(_dir45, f"planta.{_fmt45}")
            _ve45.export_view(_var45, _data45, _path45, view="Planta")
            with open(_path45, "rb") as _fh45:
                _raw45 = _fh45.read()
            assert _raw45.startswith(_mark45), \
                f"cabecera {_fmt45} de vista válida"
        _svg45 = os.path.join(_dir45, "corte.svg")
        _ve45.export_view(_var45, _data45, _svg45, view="Corte",
                          aux="Transversal")
        assert os.path.getsize(_svg45) > 400, "SVG de corte generado"
        # motor DXF §94: plano mínimo (2 muros + 1 local) → preview
        import ezdxf as _ez45
        from importers.dxf_reader import DxfImporter as _dxfcls45
        _doc45 = _ez45.new("R2010")
        _msp45 = _doc45.modelspace()
        _msp45.add_line((0, 0), (6, 0), dxfattribs={"layer": "ARQ-MUROS"})
        _msp45.add_line((6, 0), (6, 4), dxfattribs={"layer": "ARQ-MUROS"})
        _msp45.add_lwpolyline([(0.2, 0.2), (5.8, 0.2), (5.8, 3.8),
                               (0.2, 3.8)], close=True,
                              dxfattribs={"layer": "ARQ-LOCAL"})
        _dxf_path45 = os.path.join(_dir45, "mini.dxf")
        _doc45.saveas(_dxf_path45)
        _rep45 = _dxfcls45().preview(_dxf_path45)
        assert _rep45["counts"]["walls"] == 2 \
            and _rep45["counts"]["spaces"] == 1, \
            "preview §94 detecta muros y locales del DXF"
        checks.append("vistas PNG/PDF + importador DXF en GUI v3.3.0: OK "
                      "(planta en PDF/PNG con cabeceras válidas, corte en "
                      "SVG, dispatcher por extensión y preview §94 de un "
                      "DXF con muros y locales)")

        # -- check 46: DWG de entrada + bundle PyInstaller (v3.4.0) ---------
        from importers.dwg_reader import DwgGateway as _gw46
        from importers.dwg_reader import read_version as _rv46
        _dwg46 = os.path.join(tmp, "entrada.dwg")
        with open(_dwg46, "wb") as _fh46:
            _fh46.write(b"AC1015" + b"\x00" * 32)
        _info46 = _rv46(_dwg46)
        assert _info46["ok"] and _info46["label"] == "AutoCAD 2000", \
            "cabecera DWG AC1015 reconocida"
        # conversor falso local que 'produce' el DXF mínimo del check 45
        if os.name == "nt":
            _cv46 = os.path.join(tmp, "fakecv.bat")
            with open(_cv46, "w", newline="") as _fh46:
                _fh46.write("@echo off\r\ncopy /y \"%s\" \"%%~2\" >nul\r\n"
                            % _dxf_path45)
        else:
            _cv46 = os.path.join(tmp, "fakecv.sh")
            with open(_cv46, "w", newline="") as _fh46:
                _fh46.write("#!/bin/sh\ncp \"%s\" \"$2\"\n" % _dxf_path45)
            os.chmod(_cv46, 0o755)
        _prep46 = _gw46(timeout_s=30).prepare(
            _dwg46, converter=_cv46, out_dir=os.path.join(tmp, "dwgout"))
        assert _prep46["ok"], "conversión DWG con conversor local: %s" % \
            _prep46["errors"]
        from importers.dxf_reader import DxfImporter as _dxf46
        _rep46 = _dxf46().preview(_prep46["dxf_path"])
        assert _rep46["counts"]["walls"] == 2 \
            and _rep46["counts"]["spaces"] == 1, \
            "el pipeline §94 acepta el DXF convertido del DWG"
        if not getattr(sys, "frozen", False):
            # paridad del bundle (en el ejecutable el spec/bat no viajan)
            _root46 = os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))
            _spec46 = open(os.path.join(_root46, "ARQ_GEN.spec"),
                           "r", encoding="utf-8").read()
            _bat46 = open(os.path.join(_root46, "03_COMPILAR.bat"),
                          "r", encoding="ascii").read()
            assert '("resources", "resources")' in _spec46 \
                and 'name="ARQ_GEN"' in _spec46, "spec del bundle"
            for _qt46 in ("PySide6", "shiboken6", "PySide2", "shiboken2",
                          "PyQt5", "PyQt6"):
                assert ('"%s"' % _qt46) in _spec46, "exclusión Qt en spec"
                assert ("--exclude-module %s" % _qt46) in _bat46, \
                    "exclusión Qt en bat"
        checks.append("DWG de entrada + bundle PyInstaller v3.4.0: OK "
                      "(cabecera AC1015 reconocida, conversión con "
                      "conversor local, pipeline §94 sobre el DXF "
                      "convertido y paridad spec/bat del bundle)")

        # -- check 47: detalles constructivos por regiones (v3.5.0) ---------
        from domain.detalles import (get_registry as _det_reg47,
                                     reset_registry as _det_reset47)
        _det_reset47()
        _reg47 = _det_reg47()
        assert len(_reg47) == 20, "biblioteca universal de 20 detalles"
        assert len(_reg47.categories()) == 8, "8 categorías constructivas"
        assert _reg47.version == "1.1", "biblioteca base v1.1"
        assert _reg47.get("muros/muro_bloque_enlucido") \
            .espesor_total_mm == 230, "espesor total = suma de capas"
        assert _reg47.get("muros/muro_piedra_mamposteria") \
            .espesor_total_mm == 430, "muro de piedra de la v3.6.0"
        assert _reg47.set_region("colombia"), "edición colombiana activa"
        _bah47 = _reg47.get("muros/bahareque_cementado")
        assert _bah47 is not None and "NSR-10" in _bah47.norma, \
            "bahareque cementado disponible en la edición colombiana"
        from exporters.detalle_svg import export_detalle_svg as _expd47
        _svg47 = os.path.join(tmp, "detalle_bahareque.svg")
        _expd47(_bah47, _svg47, region_label=_reg47.region_name)
        with open(_svg47, "rb") as _fh47:
            assert _fh47.read(5) == b"<?xml", \
                "SVG del detalle con cabecera XML válida"
        _det_reset47()
        checks.append("detalles constructivos por ediciones v3.5.0: OK "
                      "(base universal de 20 detalles en 8 categorías, "
                      "ficha de muro con espesor 230 mm, edición "
                      "colombiana con bahareque NSR-10 y esquema SVG "
                      "acotado del detalle)")

        # -- check 48: detalle PDF/PNG + vínculo tipología (v3.6.0) --------
        from domain.detalles import (TIPOLOGIA_DETALLES as _tipmap48,
                                     buscar_tipologia as _busca48,
                                     detalles_para_tipologia as _para48,
                                     get_registry as _det_reg48,
                                     reset_registry as _det_reset48)
        from ui.building_wizard import CONSTRUCTION_TYPES as _ct48
        assert set(_tipmap48) == set(_ct48) and len(_tipmap48) == 10, \
            "paridad del mapa de tipologías con el asistente"
        _det_reset48()
        _reg48 = _det_reg48()
        for _ids48 in _tipmap48.values():
            for _did48 in _ids48:
                assert _reg48.get(_did48) is not None, \
                    f"recomendado {_did48} existe en la base"
        _rec48 = _para48(_reg48, "Mampostería de bloque + losa de vigueta")
        assert len(_rec48) == 9 and _rec48[0].categoria == "cimentaciones" \
            and _rec48[-1].categoria == "acabados", \
            "recomendados del bloque en orden narrativo"
        assert _busca48("muros de piedra") == "Muros de piedra" \
            and "muros/muro_piedra_mamposteria" in [
                d.id for d in _para48(_reg48, "Muros de piedra")], \
            "tipología de piedra enlaza con su muro"
        _reg48.set_region("cuba")
        assert len(_para48(_reg48, "Panel prefabricado (sandwich)")) == 6, \
            "Cuba retira el celular de la recomendación"
        _reg48.reset_region()
        from exporters.detalle_export import (export_detalle as _expd48,
                                              export_detalle_pdf
                                              as _pdff48)
        _det48 = _reg48.get("muros/muro_bloque_enlucido")
        _pdf48 = os.path.join(tmp, "detalle_v36.pdf")
        _png48 = os.path.join(tmp, "detalle_v36.png")
        _pdff48(_det48, _pdf48, region_label=_reg48.region_name)
        _expd48(_det48, _png48, region_label=_reg48.region_name)
        with open(_pdf48, "rb") as _fh48:
            _raw48 = _fh48.read()
        assert _raw48.startswith(b"%PDF-1.4") \
            and _raw48.count(b"/Type /Page ") == 1, \
            "PDF del detalle A4 de una página"
        with open(_png48, "rb") as _fh48:
            assert _fh48.read(8) == b"\x89PNG\r\n\x1a\n", \
                "PNG del detalle con firma válida"
        _det_reset48()
        checks.append("detalle en PDF/PNG + vínculo tipología v3.6.0: "
                      "OK (paridad de las 10 tipologías del asistente, "
                      "recomendados adaptados a la edición, muro de "
                      "piedra y tierra nuevos, PDF vectorial con "
                      "círculos y cota rotada, PNG 2x determinista)")

        # -- check 49: ventanas y paneles ajustables (v3.7.0) --------------
        from ui import prefs as _prefs49
        from ui import theme as _theme49
        from ui.app_window import (DIALOG_DEFAULTS as _dd49,
                                   geometry_size as _gs49)
        assert _theme49.SASH_THICKNESS >= 8, "sash grueso y agarrable"
        assert _prefs49.DEFAULTS["sashes"] == {} \
            and _prefs49.DEFAULTS["dialogs"] == {}, \
            "preferencias de sashes y de geometrías de diálogo"
        _copia49 = _prefs49.load_prefs(os.path.join(tmp, "no_existe.json"))
        _copia49["sashes"]["paned"] = [1]
        assert _prefs49.DEFAULTS["sashes"] == {}, \
            "los defaults de prefs no se comparten entre ventanas"
        assert _gs49("1020x680+40+30") == "1020x680+40+30" \
            and _gs49("900x600-10-20") == "900x600-10-20" \
            and _gs49("150x600") == "" and _gs49("nada") == "", \
            "validador de geometrías Tk"
        for _key49 in ("catalogo", "detalles", "presupuesto",
                       "importar_catalogo", "importar_dxf",
                       "building_wizard", "design_wizard", "guia"):
            assert _key49 in _dd49, f"ventana ajustable {_key49}"
        # El TEXTO del fuente solo se verifica en desarrollo: en el
        # ejecutable PyInstaller los módulos viajan como bytecode (sin
        # el .py junto al binario) y open(__file__) daría
        # FileNotFoundError — rompía la etapa 3 del post-build. Se
        # omite con vuelo congelado, igual que los .bat del check 27;
        # el resto de las aserciones de este check sí corren en el exe.
        if not getattr(sys, "frozen", False):
            from ui import app_window as _aw49
            with open(_aw49.__file__, "r", encoding="utf-8") as _fh49:
                _src49 = _fh49.read()
            assert _src49.count("self._prepare_dialog(dialog,") >= 12, \
                "todas las ventanas pasan por el preparador ajustable"
            assert "_apply_saved_sashes" in _src49 \
                and '"sashes"' in _src49, "sashes de la ventana principal"
        from ui import help as _help49
        _pasos49 = " ".join(texto for _t, texto in _help49.GUIDE_STEPS)
        assert "separadores" in _pasos49, \
            "la guía rápida enseña a arrastrar los separadores"
        _nota49 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        checks.append("ventanas y paneles ajustables v3.7.0: OK (sash "
                      "de 10 px visible, 12 ventanas con minsize y "
                      "borde arrastrable, geometrías y sashes "
                      "recordadas en prefs sin compartir defaults)"
                      + _nota49)

        # -- check 50: layout restaurable + 3 ediciones + PDF docs (v3.8.0)
        from domain.detalles import (DetallesRegistry as _reg50,
                                     detalles_para_tipologia as _para50,
                                     reset_registry as _reset50)
        _reset50()
        from domain import detalles as _det50
        _reg50 = _det50.get_registry()
        _regs50 = {r["codigo"] for r in _reg50.available_regions()}
        assert {"espana", "peru", "chile"} <= _regs50, \
            "ediciones España/Perú/Chile instaladas (7 en total)"
        assert len(_regs50) >= 7, "siete ediciones regionales"
        assert _reg50.set_region("espana") \
            and _reg50.get("muros/muro_ladrillo_fabrica").regional \
            and round(_reg50.get(
                "muros/muro_ladrillo_fabrica").espesor_total_mm) == 260, \
            "España reemplaza el muro de fábrica (doble hoja CTE 260 mm)"
        assert _reg50.set_region("peru") \
            and _reg50.get("muros/muro_bloque_enlucido").regional, \
            "Perú reemplaza el muro (albañilería confinada E.070)"
        _rec50 = _para50(_reg50, "Mampostería de bloque + losa de vigueta")
        assert any(_d.regional for _d in _rec50), \
            "los recomendados de la tipología se adaptan a la edición"
        assert _reg50.set_region("chile") \
            and _reg50.get("muros/muro_corte_hormigon") is not None, \
            "Chile aporta el muro de corte DS 61"
        _reg50.reset_region()
        assert len(_reg50) == 20, "base intacta tras recorrer regiones"
        _reset50()

        from exporters.markdown_pdf import export_markdown_pdf as _emp50
        _md50 = ("# Prueba selftest\n\n## Sección\n\n- punto uno\n"
                 "| col_a | col_b |\n| - | - |\n| 1 | 2 |\n\nPárrafo final.")
        _pdf50 = os.path.join(tmp, "selftest_v38.pdf")
        _emp50(_md50, _pdf50)
        _raw50 = open(_pdf50, "rb").read()
        assert _raw50.startswith(b"%PDF-1.4") and len(_raw50) > 800, \
            "markdown -> PDF del selftest válido"
        # Mismo trato que el check 49: el texto del fuente solo se
        # puede leer en desarrollo (en el ejecutable no viaja el .py).
        if not getattr(sys, "frozen", False):
            with open(_aw49.__file__, "r", encoding="utf-8") as _fh50:
                _src50 = _fh50.read()
            assert "def reset_layout" in _src50 \
                and "_on_sash_double_click" in _src50 \
                and "Restaurar disposición por defecto" in _src50, \
                "reset de disposición y doble clic en separadores (v3.8.0)"

        from services.documentation_service import DocumentationService \
            as _ds50
        assert hasattr(_ds50, "tipologia_proyecto") \
            and hasattr(_ds50, "detalles_recomendados"), \
            "documentación lee la tipología y recomienda detalles"
        _nota50 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        checks.append("layout restaurable + ediciones regionales "
                      "España/Perú/Chile + PDF de documentos v3.8.0: OK "
                      "(Ctrl+0 y doble clic en separadores, 7 ediciones "
                      "regionales, memoria/pliego con detalles "
                      "recomendados, exportación PDF de documentos)"
                      + _nota50)

        # -- check 51: interfaz compacta, plano primero (v3.9.0) --------
        from ui import icons as _ic51
        from ui import theme as _th51
        from ui.app_window import (SASH_DEFAULT_EXPLORER as _sde51,
                                   SASH_DEFAULT_PROPS_MARGIN as _sdpm51,
                                   SASH_DEFAULT_BOTTOM_MARGIN as _sdbm51)
        assert (_sde51, _sdpm51, _sdbm51) == (240, 300, 120), \
            "separadores de fábrica al servicio del plano (240/300/120)"
        assert _th51.SASH_THICKNESS >= 8, \
            "el separador de paneles sigue siendo agarrable"
        assert callable(getattr(_ic51, "toolbar_logo", None)), \
            "logo pequeño para la barra de herramientas"
        from ui.prefs import PREFS_VERSION as _pv51
        assert _pv51 >= 2, "formato de preferencias v2 (panel compacto)"
        _nota51 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_aw49.__file__, "r", encoding="utf-8") as _fh51:
                _src51 = _fh51.read()
            assert "toolbar_logo(22" in _src51 \
                and "bar_filters" in _src51 \
                and "Nivel:" in _src51 \
                and "bottom_compact" in _src51, \
                "barra en dos filas + panel inferior compacto con migración"
        checks.append("interfaz compacta v3.9.1: OK (logo de 22 px en "
                      "la barra, herramientas en dos filas, filtro de "
                      "nivel siempre visible, separadores de fábrica "
                      "240/300/120, panel inferior de 100 px y "
                      "migración one-shot de prefs heredadas)"
                      + _nota51)

        # -- check 52: regeneración de la edificación (v3.10.0) ----------
        from ui import building_wizard as _bw52
        for _name52 in ("program_from_project", "move_room", "remove_room",
                        "resize_room", "add_room", "move_room_to_level",
                        "collect_generated", "purge_generated",
                        "replace_plan"):
            assert callable(getattr(_bw52, _name52, None)), _name52
        _nota52 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_bw52.__file__, "r", encoding="utf-8") as _fh52:
                _src52 = _fh52.read()
            assert "WIZARD_ORIGIN" in _src52 \
                and "program_from_project" in _src52 \
                and "purge_generated" in _src52, \
                "motor regenerativo con marca de origen y purga"
            # conductual: generar, reconstruir el programa, editar y
            # SUSTITUIR sin huérfanos (lo pesado vive en test_129)
            _data52 = _bw52.BuildingWizardData()
            _data52.levels = [_bw52.LevelSpec(name="Planta Baja",
                                              height_m=3.0)]
            _data52.usage_type = "Vivienda"
            _data52.rooms = _bw52.preset_rooms("Vivienda", "Planta Baja")
            _data52.relations = _bw52.suggest_relations(_data52)
            _data52.installations = ["Eléctrica"]
            _bw52.apply_plan(_data52, context)
            _prog52, _av52 = _bw52.program_from_project(context)
            assert _prog52.rooms, "el programa reconstruido quedó vacío"
            _bw52.remove_room(_prog52, _prog52.rooms[-1].name)
            _r2_52 = _bw52.replace_plan(_prog52, context, variant=None)
            assert _r2_52.get("regeneracion") is True, \
                "la sustitución no se marcó como regeneración"
            assert _r2_52["purga"]["locales"] >= 4, \
                "la purga no recogió los locales generados"
            assert _r2_52["spaces"] == len(_prog52.rooms) + 1, \
                "la regeneración no redistribuyó el programa editado"
        checks.append("regeneración de la edificación v3.10.0: OK "
                      "(programa editable — mover/añadir/quitar/"
                      "redimensionar locales y llevarlos a otro nivel—, "
                      "purga sin huérfanos de lo generado por el "
                      "asistente, variantes puntuadas para elegir la "
                      "que sustituye, e instalaciones recalculadas)"
                      + _nota52)

        # -- check 53: vista 3D axonométrica (v3.11.0) --------------------
        from ui import view3d as _v53
        for _name53 in ("Camara3D", "proyecta", "encuadre",
                        "construir_caras", "modelo3d_desde_proyecto",
                        "export_vista3d_png"):
            assert callable(getattr(_v53, _name53, None)), _name53
        _nota53 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_v53.__file__, "r", encoding="utf-8") as _fh53:
                _src53 = _fh53.read()
            assert "class Camara3D" in _src53 \
                and "def construir_caras" in _src53 \
                and "orden del pintor" in _src53, \
                "motor 3D con cámara, extrusión y orden del pintor"
            # conductual: modelo del proyecto vivo → caras → PNG válido
            _modelo53, _av53 = _v53.modelo3d_desde_proyecto(context)
            assert _modelo53.muros, "la vista 3D no encontró muros"
            _caras53 = _v53.construir_caras(_modelo53,
                                            _v53.Camara3D())
            assert _caras53, "la extrusión 3D no produjo caras"
            _png53 = os.path.join(tmp, "check53_vista3d.png")
            _v53.export_vista3d_png(_caras53, _v53.Camara3D(), _png53,
                                    titulo="selftest vista 3D")
            with open(_png53, "rb") as _fh53b:
                assert _fh53b.read(8) == b"\x89PNG\r\n\x1a\n", \
                    "el PNG de la vista 3D no es PNG"
        checks.append("vista 3D axonométrica v3.11.0: OK (cámara con "
                      "azimut/elevación/zoom, muros extruidos con "
                      "eliminación de caras y orden del pintor, pisos "
                      "por tipo de local, vanos a su cota real, "
                      "plataformas por nivel, explosión y aislado de "
                      "niveles, PNG determinista 100% stdlib)"
                      + _nota53)

        # -- check 54: presupuesto vivo sobre las variantes (v3.12.0) ------
        from ui import variant_budget as _vb54
        from ui import building_wizard as _bw54b
        from ui.building_wizard import (
            BuildingWizardData as _BWD54, LevelSpec as _LS54,
            RoomSpec as _RS54, RelationSpec as _Rel54)
        for _name54 in ("CALIDADES", "VariantCost", "variant_takeoff",
                        "estimate_variant_cost", "attach_costs",
                        "fmt_cup", "desglose_texto"):
            assert hasattr(_vb54, _name54), _name54
        _nota54 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_vb54.__file__, "r", encoding="utf-8") as _fh54:
                _src54 = _fh54.read()
            assert "class VariantCost" in _src54 \
                and "def variant_takeoff" in _src54 \
                and "def _longitudes_de_muros" in _src54, \
                "estimador con takeoff y clasificación geométrica"
        # conductual: programa chico → variantes → costes oficiales
        _data54 = _BWD54(name="Selftest 54")
        _data54.levels = [_LS54(name="Planta Baja", height_m=3.0),
                          _LS54(name="Alta", height_m=3.0)]
        _data54.rooms = [
            _RS54(name="Sala", space_type="ROOM", width_m=4.0, depth_m=5.0,
                  level_ref="Planta Baja", with_window=True),
            _RS54(name="Cocina", space_type="KITCHEN", width_m=3.0,
                  depth_m=2.5, level_ref="Planta Baja", with_window=True),
            _RS54(name="Bano", space_type="BATHROOM", width_m=1.8,
                  depth_m=2.0, level_ref="Planta Baja", with_window=False),
            _RS54(name="Dormitorio", space_type="ROOM", width_m=3.5,
                  depth_m=4.0, level_ref="Alta", with_window=True),
        ]
        _data54.relations = [_Rel54(a_name="Sala", b_name="Cocina",
                                    kind_es="Adyacente a", with_door=True)]
        _vars54 = _bw54b.generate_variants(_data54)
        assert len(_vars54) >= 10, "variantes insuficientes para el check 54"
        assert all(v.cost is None for v in _vars54), "coste pre-adjunto"
        _vb54.attach_costs(_data54, _vars54, ruleset_full, "Estándar")
        _con54 = [v for v in _vars54 if v.cost is not None]
        assert len(_con54) == len(_vars54), "variantes sin coste"
        assert all(v.cost.total > 0 for v in _con54), "coste no positivo"
        assert all(v.cost.rows for v in _con54), "takeoff vacío"
        assert all("Muros" in v.cost.categories for v in _con54), \
            "categoría Muros ausente"
        _tot54 = [v.cost.total for v in _con54]
        assert max(_tot54) > min(_tot54), "las variantes cuestan igual"
        # vivo: la calidad reescala los acabados sin tocar la obra gruesa
        _v54 = _con54[0]
        _est54 = _v54.cost.categories.get("Estructura", 0.0)
        _pisos54 = _v54.cost.categories.get("Pisos", 0.0)
        _prem54 = _vb54.estimate_variant_cost(_data54, _v54, ruleset_full,
                                              "Premium")
        assert _prem54.total > _v54.cost.total, "Premium no encarece"
        assert abs(_prem54.categories.get("Estructura", 0.0) - _est54) \
            < 0.01, "la obra gruesa no debe cambiar con la calidad"
        assert _prem54.categories.get("Pisos", 0.0) > _pisos54, \
            "Premium no encarece los pisos"
        # determinismo
        _otra54 = _vb54.estimate_variant_cost(_data54, _v54, ruleset_full,
                                              "Estándar")
        assert _otra54.to_dict() == _v54.cost.to_dict(), \
            "la estimación no es determinista"
        _png54 = os.path.join(tmp, "check54_costes.png")
        from exporters.png_exporter import export_variant_costs_png \
            as _evcp54
        _evcp54([(v.title, v.cost.total) for v in _con54[:8]], _png54,
                project_name="selftest", calidad="Estándar")
        with open(_png54, "rb") as _fh54b:
            assert _fh54b.read(8) == b"\x89PNG\r\n\x1a\n", \
                "el PNG de costes no es PNG"
        checks.append("presupuesto vivo sobre las variantes v3.12.0: OK "
                      "(takeoff paramétrico del trazado, precios "
                      "oficiales del catálogo PRECONS III, muros "
                      "exterior/interior por geometría, calidad de "
                      "acabados que reescala sin tocar la obra gruesa, "
                      "determinismo y PNG de comparativa)" + _nota54)

        # -- check 55: sombras solares, terreno 3D e IFC de entrada -----
        from ui import solar as _s55
        from ui import terreno3d as _t55
        from importers import ifc_reader as _ir55
        from ui.view3d import Camara3D as _Cam55
        for _name55 in ("SolarOpts", "declinacion_solar", "posicion_solar",
                        "envolvente_convexa", "poligono_sombra",
                        "caras_de_sombras", "caras_de_sol", "resumen_solar",
                        "recomendacion_orientacion"):
            assert hasattr(_s55, _name55), _name55
        for _name55 in ("TerrenoOpts", "altura_en", "malla_terreno",
                        "caras_de_terreno"):
            assert hasattr(_t55, _name55), _name55
        assert hasattr(_ir55, "IfcImporter"), "IfcImporter"
        _nota55 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_s55.__file__, "r", encoding="utf-8") as _fh55:
                _src55 = _fh55.read()
            assert "def posicion_solar" in _src55 \
                and "def _clip_con_recto" in _src55, \
                "motor solar con proyección y recorte"
            with open(_t55.__file__, "r", encoding="utf-8") as _fh55b:
                _src55b = _fh55b.read()
            assert "def malla_terreno" in _src55b \
                and "_PAD_Z" in _src55b, \
                "terreno con malla y plataforma nivelada"
            with open(_ir55.__file__, "r", encoding="utf-8") as _fh55c:
                _src55c = _fh55c.read()
            assert "class IfcImporter" in _src55c \
                and "def _muro_de_solido" in _src55c, \
                "importador IFC con reconstrucción de muros"
        # conductual: posición solar verificable a mano
        assert abs(_s55.declinacion_solar(172) - 23.44) < 0.3, "declinación"
        _az55, _el55 = _s55.posicion_solar(40.4, 80, 12.0)
        assert abs(_az55 - 180.0) < 1.0 and 45 < _el55 < 55, \
            "mediodía del equinoccio en Madrid"
        assert not _s55.sol_visible(
            _s55.posicion_solar(80, 355, 12.0)[1]), "noche polar"
        # sombras del proyecto de demostración: mediodía de diciembre
        _sol55 = _s55.SolarOpts(latitud_deg=23.1, dia_anio=355, hora=12.0)
        from ui import view3d as _v55
        _mod55, _av55 = _v55.modelo3d_desde_proyecto(context)
        _cam55 = _Cam55()
        _sombras55 = _s55.caras_de_sombras(_mod55, _sol55, _cam55)
        assert _sombras55, "sin sombras al mediodía de diciembre"
        _sombras55b = _s55.caras_de_sombras(_mod55, _sol55, _cam55)
        assert [(c.color, tuple(map(tuple, c.puntos))) for c in _sombras55] \
            == [(c.color, tuple(map(tuple, c.puntos)))
                for c in _sombras55b], "sombras no deterministas"
        _huella55 = _s55._bbox_total(_mod55)
        for _cara55 in _sombras55:
            _ys55 = [p[1] for p in _cara55.puntos]
            _xs55 = [p[0] for p in _cara55.puntos]
            _dentro55 = (max(_xs55) <= _huella55[2] + 0.08
                         and min(_xs55) >= _huella55[0] - 0.08
                         and max(_ys55) <= _huella55[3] + 0.08
                         and min(_ys55) >= _huella55[1] - 0.08)
            assert not _dentro55, "sombra dentro de la huella"
        # terreno: malla determinista con plataforma nivelada
        _ter55 = _t55.TerrenoOpts(pendiente_pct=5.0, direccion_deg=90.0,
                                  relieve_m=0.3, semilla=7)
        assert abs(_t55.altura_en(_huella55[0] + 0.1, _huella55[1] + 0.1,
                                  _ter55, _huella55) + 0.01) < 1e-9, \
            "el pad no está nivelado"
        _terreno55 = _t55.caras_de_terreno(_huella55, _ter55, _cam55)
        _terreno55b = _t55.caras_de_terreno(_huella55, _ter55, _cam55)
        assert len(_terreno55) > 100, "malla de terreno escasa"
        assert [(c.color, tuple(map(tuple, c.puntos))) for c in _terreno55] \
            == [(c.color, tuple(map(tuple, c.puntos)))
                for c in _terreno55b], "terreno no determinista"
        # IFC de entrada: roundtrip exportar → analizar → importar.
        # El contexto acumula entidades de checks anteriores, así que
        # la fidelidad se afirma RELACIONALMENTE: lo importado debe
        # igualar a lo exportado y a lo que el propio proyecto tiene.
        _muros55 = len(context.architecture.list("WALL", context.project.id))
        _locales55 = len(context.architecture.list(
            "SPACE", context.project.id))
        _pisos55 = len(context.architecture.list(
            "LEVEL", context.project.id))
        from services.bim_service import BimService as _Bim55
        _abiertos55 = _Bim55(context).bim_tree()["openings"]
        _puertas55 = sum(1 for _o55 in _abiertos55
                         if _o55.get("category") == "IfcDoor")
        _vent55 = sum(1 for _o55 in _abiertos55
                      if _o55.get("category") == "IfcWindow")
        _ifc55 = export_service.export(context, "IFC",
                                       os.path.join(tmp, "check55.ifc"))
        _prev55 = _ir55.IfcImporter().preview(_ifc55)
        assert _prev55["walls"] == _muros55 \
            and _prev55["spaces"] == _locales55 \
            and _prev55["storeys"] == _pisos55 \
            and _prev55["doors"] == _puertas55 \
            and _prev55["windows"] == _vent55, \
            "preview IFC: " + repr(_prev55)
        _app55 = ApplicationContext()
        _dest55 = _app55.create_project(
            os.path.join(tmp, "check55_destino.arqgen"), name="Destino 55")
        from services.architecture_service import ArchitectureService \
            as _Arch55
        _res55 = _ir55.IfcImporter().apply(_ifc55, _Arch55(_dest55))
        assert _res55["niveles"] == _pisos55 and _res55["muros"] == _muros55 \
            and _res55["puertas"] + _res55["ventanas"] \
            == _puertas55 + _vent55 \
            and _res55["locales"] == _locales55, \
            "apply IFC: " + repr({k: v for k, v in _res55.items()
                                  if k != "avisos"})
        _dest55.close()
        # PNG 3D con sol y terreno juntos (mismo motor del check 53)
        _caras55 = _v55.construir_caras(_mod55, _cam55, solar=_sol55,
                                        terreno=_ter55)
        assert any(c.kind == "sombra" for c in _caras55) \
            and any(c.kind == "terreno" for c in _caras55) \
            and any(c.kind == "brujula" for c in _caras55), \
            "falta sol o terreno en la escena"
        _png55 = os.path.join(tmp, "check55_vista3d.png")
        _v55.export_vista3d_png(_caras55, _cam55, _png55,
                                titulo="selftest 55",
                                info_extra=_s55.resumen_solar(_sol55))
        with open(_png55, "rb") as _fh55d:
            assert _fh55d.read(8) == b"\x89PNG\r\n\x1a\n", \
                "el PNG 3D con sombras no es PNG"
        checks.append("sombras solares, terreno 3D e IFC de entrada "
                      "v3.13.0: OK (posición solar por declinación y "
                      "ángulo horario, sombras proyectadas y recortadas "
                      "fuera de la huella, brújula y trayectoria solar, "
                      "malla de terreno con pendiente, relieve "
                      "determinista y plataforma nivelada, roundtrip "
                      "IFC exportar->importar fiel a muros, locales y "
                      "vanos)" + _nota55)

        # -- 56: herramientas de edición CAD (v3.14.0) --------------------
        from ui import cad_tools as _cad56
        _nota56 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_cad56.__file__, "r", encoding="utf-8") as _fh56:
                _src56 = _fh56.read()
            assert "def chaflan" in _src56 and "def paralela" in _src56 \
                and "def _rehospedar_vanos" in _src56 \
                and "def muros_de_local" in _src56, \
                "motor CAD con chaflán, paralela, vanos y muros exclusivos"
            from ui import app_window as _aw56
            with open(_aw56.__file__, "r", encoding="utf-8") as _fh56b:
                _src56b = _fh56b.read()
            assert "def open_cad_palette" in _src56b \
                and "def open_mod_wizard" in _src56b \
                and "def _cad_click" in _src56b, \
                "paleta CAD y asistente de modificaciones en la GUI"
            from ui import building_wizard as _bw56
            with open(_bw56.__file__, "r", encoding="utf-8") as _fh56c:
                _src56c = _fh56c.read()
            assert "editada_a_mano" in _src56c, \
                "lo editado a mano sobrevive a la regeneración"
        # conductual: mover un muro y chaflanear dos con muro de unión
        _ctx56 = ApplicationContext().create_project(
            os.path.join(tmp, "check56.arqgen"), name="Check 56")
        from services.architecture_service import ArchitectureService \
            as _Arc56
        _arq56 = _Arc56(_ctx56)
        _n56 = _arq56.create_level("Nivel 56", 0.0, 3.0)
        _w56a = _arq56.create_wall(_n56.code, (0.0, 0.0), (6.0, 0.0), 0.2)
        _w56b = _arq56.create_wall(_n56.code, (6.0, 0.0), (6.0, 4.0), 0.2)
        _cad56.mover(_ctx56, [("WALL", _w56a.id)], 0.5, 1.0)
        _w56a = _cad56.resolver(_ctx56, "WALL", _w56a.id)
        assert abs(_w56a.start[0] - 0.5) < 1e-9 \
            and abs(_w56a.start[1] - 1.0) < 1e-9, "mover muro exacto"
        assert _w56a.metadata.get("editada_a_mano") is True, \
            "marca de edición manual"
        _r56b = _cad56.chaflan(_ctx56, _w56a.code, _w56b.code, 0.5)
        assert len(_r56b["creados"]) == 1 \
            and len(_ctx56.architecture.list("WALL",
                                             _ctx56.project.id)) == 3, \
            "chaflán recorta ambos y añade el muro de unión"
        _cad56.finalizar(_ctx56, _r56b)
        _ctx56.close()
        checks.append("herramientas de edición CAD v3.14.0: OK (paleta "
                      "con iconos y asistente de modificaciones, mover, "
                      "copiar, reflejar, girar, recortar, alargar, "
                      "chaflán, dividir, estirar y paralela con "
                      "auditoría, undo, QTO e instalaciones reancladas, "
                      "y lo editado a mano sobrevive a la regeneración)"
                      + _nota56)

        # -- 57: concepción de espacios (v3.15.0) --------------------------
        from domain import mobiliario as _mob57
        from domain import cubiertas as _cub57
        from domain import accesibilidad as _acc57
        _nota57 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_mob57.__file__, "r", encoding="utf-8") as _fh57:
                _src57 = _fh57.read()
            assert "CATALOGO" in _src57 and "def generar_mobiliario" in _src57 \
                and "def colocar_en_local" in _src57, \
                "motor de mobiliario con catálogo y colocación"
            with open(_cub57.__file__, "r", encoding="utf-8") as _fh57b:
                _src57b = _fh57b.read()
            assert "def envolvente_convexa" in _src57b \
                and "def offset_convexo" in _src57b \
                and "ESTILO_CUBIERTA" in _src57b, \
                "cubiertas con geometría y estilos"
            with open(_acc57.__file__, "r", encoding="utf-8") as _fh57c:
                _src57c = _fh57c.read()
            assert "def analizar_barreras" in _src57c \
                and "def aplicar_soluciones" in _src57c \
                and "def geometria_rampa" in _src57c, \
                "accesibilidad con chequeos y soluciones"
        # conductual: amueblar, cubrir y resolver barreras en un mini
        # proyecto; QTO con las fórmulas nuevas; mensajes cp1252.
        _ctx57 = ApplicationContext().create_project(
            os.path.join(tmp, "check57.arqgen"), name="Check 57")
        from services.architecture_service import ArchitectureService \
            as _Arc57
        _arq57 = _Arc57(_ctx57)
        _n57 = _arq57.create_level("Nivel 57", 0.0, 3.0)
        _dorm57 = _arq57.create_space(_n57.code, "Dormitorio", "BEDROOM",
                                      [(0, 0), (4.6, 0), (4.6, 3.4),
                                       (0, 3.4)])
        _ = _dorm57
        _bano57 = _arq57.create_space(_n57.code, "Bano", "BATHROOM",
                                      [(4.6, 0), (7.2, 0), (7.2, 2.4),
                                       (4.6, 2.4)])
        _ = _bano57
        _esc57 = _arq57.create_space(_n57.code, "Escalera", "STAIR",
                                     [(0, 3.4), (2, 3.4), (2, 5.4),
                                      (0, 5.4)])
        _ = _esc57
        _r57mob = _mob57.generar_mobiliario(_ctx57, None, con_qto=False)
        assert len(_r57mob["creados"]) >= 5 \
            and _r57mob["conteo"].get("cama_doble", 0) == 1 \
            and _r57mob["conteo"].get("inodoro", 0) == 1, \
            "mobiliario por uso del local"
        _r57mob2 = _mob57.generar_mobiliario(_ctx57, None, con_qto=False)
        assert len(_r57mob2["creados"]) == len(_r57mob["creados"]) \
            and len(_r57mob2["eliminados"]) == len(_r57mob["creados"]), \
            "mobiliario idempotente (regenera lo suyo)"
        _r57cub = _cub57.generar_cubierta(_ctx57, None,
                                          tipologia="dos_aguas",
                                          con_qto=False)
        _roof57 = _ctx57.architecture.list("ROOF", _ctx57.project.id)
        assert len(_roof57) == 1 and _roof57[0].ridge is not None \
            and len(_roof57[0].footprint) >= 4 \
            and _r57cub["superficie"]["area_inclinada"] > 0, \
            "cubierta a dos aguas con cumbrera y superficie real"
        _r57acc = _acc57.aplicar_soluciones(_ctx57, con_qto=False)
        assert len(_ctx57.architecture.list("HANDRAIL",
                                            _ctx57.project.id)) >= 2 \
            and _acc57.pendiente_maxima_rampa(0.4) == 10.0 \
            and _acc57.pendiente_maxima_rampa(0.9) == 8.0 \
            and _acc57.pendiente_maxima_rampa(1.8) == 6.0, \
            "accesibilidad con barandillas y tabla de rampas"
        from services.quantity_service import QuantityService as _QS57
        _stats57 = _QS57(_ctx57).compute_all()
        assert _stats57.objects_processed > 0, "QTO con las fórmulas nuevas"
        _texto57 = (_mob57.resumen_texto(_r57mob) + " "
                    + _cub57.resumen_texto(_r57cub) + " "
                    + _acc57.resumen_texto(_r57acc))
        _texto57.encode("cp1252")
        _ctx57.close()
        checks.append("concepción de espacios v3.15.0: OK (mobiliario por "
                      "uso social/doméstico con catálogo y paso entre "
                      "piezas, cubierta por estilo con tipología, "
                      "material, pendiente y superficie real, y "
                      "accesibilidad con chequeos, rampas normativas, "
                      "barandillas y barras de apoyo; entidades "
                      "FURNITURE/ROOF/RAMP/HANDRAIL con QTO y undo)"
                      + _nota57)

        # -- 58: teclado y puntero AutoCAD + editor de local + cubiertas
        #        v2 (v3.16.0) -------------------------------------------
        from ui import keymap as _key58
        from ui import cursor_acad as _cur58
        from ui import editor_espacios as _edi58
        _nota58 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_key58.__file__, "r", encoding="utf-8") as _fh58:
                _src58 = _fh58.read()
            assert "ALIAS_COMANDOS" in _src58 \
                and "class TecladoAutoCAD" in _src58, \
                "teclado AutoCAD con alias y modos"
            with open(_cur58.__file__, "r", encoding="utf-8") as _fh58b:
                _src58b = _fh58b.read()
            assert "def puntas_cruz" in _src58b \
                and "def aplicar_ayudas" in _src58b \
                and "def mejor_fijacion" in _src58b, \
                "puntero con mira, referencias, orto e imantación"
            with open(_edi58.__file__, "r", encoding="utf-8") as _fh58c:
                _src58c = _fh58c.read()
            assert "def datos_local" in _src58c \
                and "def crear_acceso" in _src58c \
                and "def redimensionar_local" in _src58c, \
                "editor profundo de locales"
        # conductual: teclado (F8, M+ESPACIO, MI), mira de punta a
        # punta, orto/imantación/referencia, editor completo y cubiertas
        _t58 = _key58.TecladoAutoCAD()
        assert _t58.procesar("F8") == "alternar_orto" \
            and _t58.estado["orto"] is True, "F8 conmuta el modo orto"
        assert _t58.procesar("m") is None \
            and _t58.procesar("space") == "mover" \
            and _t58.ultima_accion == "mover", "M+ESPACIO ejecuta MOVER"
        assert _t58.procesar("m") is None \
            and _t58.procesar("i") == "reflejar", "M+I refleja"
        assert _t58.procesar("z", ctrl=True) == "deshacer", "Ctrl+Z"
        _p1, _p2, _p3, _p4 = _cur58.puntas_cruz(50, 40, 100, 80, 100.0)
        assert _p1 == (0.0, 40) and _p2 == (100.0, 40) \
            and _p3 == (50, 0.0) and _p4 == (50, 80.0), \
            "mira de punta a punta al 100 %"
        assert _cur58.aplicar_orto((0, 0), (3, 8)) == (0, 8) \
            and _cur58.imantar_rejilla((0.42, 1.61), 0.5) == (0.5, 1.5), \
            "orto endereza y la imantación redondea"

        class _Muro58:
            start = (0.0, 0.0)
            end = (10.0, 0.0)

        _ganada58 = _cur58.aplicar_ayudas(
            None, (0.05, 0.04), True, True, True, [_Muro58()],
            _cur58.ConfigCursor(), 100.0)
        assert _ganada58 == ((0.0, 0.0), "extremo"), \
            "la referencia ganada gana al orto y a la rejilla"
        _ctx58 = ApplicationContext().create_project(
            os.path.join(tmp, "check58.arqgen"), name="Check 58")
        from services.architecture_service import ArchitectureService \
            as _Arc58
        _arq58 = _Arc58(_ctx58)
        _n58 = _arq58.create_level("Nivel 58", 0.0, 3.0)
        _m58a = _arq58.create_wall(_n58.code, (0.0, 0.0), (4.0, 0.0), 0.2)
        _m58b = _arq58.create_wall(_n58.code, (0.0, 0.0), (0.0, 3.0), 0.2)
        _m58c = _arq58.create_wall(_n58.code, (0.0, 3.0), (4.0, 3.0), 0.2)
        _m58d = _arq58.create_wall(_n58.code, (4.0, 0.0), (4.0, 3.0), 0.2)
        _loc58 = _arq58.create_space(_n58.code, "Dormitorio", "BEDROOM",
                                     [(0, 0), (4, 0), (4, 3), (0, 3)])
        # vecino que comparte el muro x=4 (para que sea COMPARTIDO)
        _arq58.create_wall(_n58.code, (4.0, 0.0), (8.0, 0.0), 0.2)
        _arq58.create_wall(_n58.code, (4.0, 3.0), (8.0, 3.0), 0.2)
        _arq58.create_wall(_n58.code, (8.0, 0.0), (8.0, 3.0), 0.2)
        _arq58.create_space(_n58.code, "Sala", "LIVING_ROOM",
                            [(4, 0), (8, 0), (8, 3), (4, 3)])
        _diag58 = _edi58.datos_local(_ctx58, _loc58.id)
        assert _diag58["ancho_m"] == 4.0 and _diag58["fondo_m"] == 3.0 \
            and any("sin puerta" in a for a in _diag58["avisos"]) \
            and abs(_diag58["hueco_necesario_m2"] - 2.0) < 1e-6, \
            "diagnóstico del local con avisos y 1/6 de ventilación"
        _r58a = _edi58.crear_acceso(_ctx58, _loc58.id,
                                    muro_ref=_m58b.code)
        _puerta58 = _ctx58.architecture.list("DOOR", _ctx58.project.id)[0]
        assert abs(_puerta58.width_m - 0.9) < 1e-9, \
            "puerta con el ancho del uso (dormitorio 0.90)"
        _r58v = _edi58.crear_ventana(_ctx58, _loc58.id)
        _vent58 = _ctx58.architecture.list("WINDOW",
                                           _ctx58.project.id)[0]
        assert abs(_vent58.width_m - 1.67) < 0.01, \
            "ventana con el hueco que pide el déficit (2.0 m2 / 1.2)"
        _r58d = _edi58.redimensionar_local(_ctx58, _loc58.id, 5.0, 4.0,
                                           con_mobiliario=False)
        _diag58b = _edi58.datos_local(_ctx58, _loc58.id)
        _comp58 = _ctx58.architecture.get("WALL", _m58d.id)
        assert abs(_diag58b["ancho_m"] - 5.0) < 1e-6 \
            and abs(_diag58b["fondo_m"] - 4.0) < 1e-6 \
            and _comp58.start == (4.0, 0.0), \
            "redimensionar mueve solo los muros exclusivos"
        assert isinstance(_r58d["qto"], dict) and _r58d["qto"], \
            "QTO recalculado tras la edición"
        (_edi58.resumen_texto(_r58a) + " "
         + _edi58.resumen_texto(_r58v) + " "
         + _edi58.resumen_texto(_r58d)).encode("cp1252")
        from domain import cubiertas as _cub58
        _codo58, _h158, _tot58 = _cub58.parametros_mansarda(5.0, 60.0)
        assert abs(_codo58 - 2.75) < 1e-9 \
            and abs(_h158 - 2.75 * 1.7320508075688772) < 1e-6 \
            and _tot58 > _h158, "mansarda con codo al 55 % del semivano"
        _ajuste58 = _cub58.resolver_parametros(
            None, tipologia="dos_aguas", material="teja_curva",
            pendiente_pct=10.0)
        assert _ajuste58["pendiente_ajustada"] \
            and _ajuste58["pendiente_pct"] == 22.0, \
            "pendiente mínima por material con aviso"
        "fibrocemento" in _cub58.MATERIALES
        (_key58.resumen_atajos().__str__()).encode("cp1252")
        _ctx58.close()
        checks.append("teclado y puntero AutoCAD + editor de local + "
                      "cubiertas v2 v3.16.0: OK (F3/F7/F8/F9/F10, ESC, "
                      "ESPACIO que repite, alias M/CO/MI/RO/TR/EX/CHA/"
                      "DIV/S/O/E con ESPACIO, Ctrl+Z/C/V; mira de punta "
                      "a punta configurable con referencias a extremos y "
                      "medios, orto e imantación; editor de locales con "
                      "diagnóstico, puerta por uso, ventana 1/6-1/25 y "
                      "redimensionar con muros exclusivos; mansarda, "
                      "mariposa y dientes de sierra con pendiente "
                      "mínima por material)"
                      + _nota58)

        # -- 59: cota de implantación de la cubierta + vista en
        #        perspectiva (v3.17.0) ---------------------------------
        from domain import cubiertas as _cub59
        from ui import view3d as _v359
        _nota59 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_cub59.__file__, "r", encoding="utf-8") as _fh59:
                _src59 = _fh59.read()
            assert "altura_base_m" in _src59 \
                and "def cota_base_cubierta" in _src59, \
                "cota de implantación de la cubierta en el dominio"
            with open(_v359.__file__, "r", encoding="utf-8") as _fh59b:
                _src59b = _fh59b.read()
            assert "def prepara_perspectiva" in _src59b \
                and "PERSP_CERCA_FRACC" in _src59b, \
                "cámara en perspectiva con centro y distancia propias"
        # conductual: cubierta por defecto SOBRE los muros (ya no
        # enterrada en el piso del nivel) y cota explícita respetada
        _ctx59 = ApplicationContext().create_project(
            os.path.join(tmp, "check59.arqgen"), name="Check 59")
        from services.architecture_service import ArchitectureService \
            as _Arc59
        _arq59 = _Arc59(_ctx59)
        _n59 = _arq59.create_level("Nivel 59", 0.0, 3.0)
        _arq59.create_space(_n59.code, "Sala", "LIVING_ROOM",
                            [(0, 0), (8, 0), (8, 5), (0, 5)])
        _r59 = _cub59.generar_cubierta(_ctx59, None,
                                       tipologia="dos_aguas",
                                       pendiente_pct=30.0)
        _roof59 = _cub59.cubierta_actual(_ctx59)
        assert _roof59 is not None, "cubierta generada"
        assert not (_roof59.metadata or {}).get("altura_base_m"), \
            "sin cota explícita la metadata queda limpia"
        _niv59 = _v359.Nivel3D(_n59.id, "Nivel 59", 0.0, 3.0)
        _caras59 = _v359.caras_de_cubierta(_roof59, _niv59, 0.0,
                                           _v359.Camara3D())
        assert _caras59 and abs(min(
            p[2] for c in _caras59 for p in c.puntos) - 3.0) < 1e-6, \
            "la cubierta nace SOBRE el top de los muros (3.0 m)"
        _r59b = _cub59.generar_cubierta(_ctx59, None,
                                        tipologia="dos_aguas",
                                        pendiente_pct=30.0,
                                        altura_base_m=4.2)
        _roof59b = _cub59.cubierta_actual(_ctx59)
        assert abs(float(
            (_roof59b.metadata or {}).get("altura_base_m", 0.0)
            or 0.0) - 4.2) < 1e-9, "la cota pedida se guarda en metadata"
        _caras59b = _v359.caras_de_cubierta(_roof59b, _niv59, 0.0,
                                            _v359.Camara3D())
        assert abs(min(p[2] for c in _caras59b for p in c.puntos)
                   - 4.2) < 1e-6, "el 3D respeta la cota fijada"
        # con la explosión la cubierta acompaña a su nivel
        _caras59x = _v359.caras_de_cubierta(_roof59b, _niv59, 1.5,
                                            _v359.Camara3D())
        assert abs(min(p[2] for c in _caras59x for p in c.puntos)
                   - 5.7) < 1e-6, "la explosión desplaza la cubierta"
        _r59c = _cub59.generar_cubierta(_ctx59, None,
                                        tipologia="plana_no_transitable",
                                        altura_base_m=2.0)
        assert any("por debajo" in a for a in _r59c["avisos"]), \
            "aviso amable si la cota queda bajo el top de los muros"
        (_cub59.resumen_texto(_r59b)).encode("cp1252")
        # cámara en perspectiva: centro, distancia y división por
        # profundidad verificadas a mano (D=10, cerca crece)
        _cam59 = _v359.Camara3D()
        assert _cam59.tecla("p") and _cam59.perspectiva, \
            "P conmuta a perspectiva"
        assert _cam59.tecla("p") and not _cam59.perspectiva, \
            "P vuelve a axonométrica"
        _cam59.perspectiva = True
        _cam59.azimuth_deg = 0.0
        _cam59.elevacion_deg = 0.0
        _cam59.distancia_m = 10.0
        _cam59.centro = (0.0, 0.0, 0.0)
        assert _v359.proyecta((0.0, 0.0, 0.0), _cam59) == (0.0, 0.0), \
            "el centro se proyecta en el origen con escala 1"
        _sx_cerca, _ = _v359.proyecta((1.0, 2.0, 0.0), _cam59)
        _sx_lejos, _ = _v359.proyecta((1.0, -2.0, 0.0), _cam59)
        assert abs(_sx_cerca - 1.25) < 1e-9 \
            and abs(_sx_lejos - 10.0 / 12.0) < 1e-9 \
            and _sx_cerca > _sx_lejos, \
            "el cercano crece (10/8) y el lejano encoge (10/12)"
        _mod59, _av59 = _v359.modelo3d_desde_proyecto(_ctx59)
        _cam59b = _v359.Camara3D(perspectiva=True)
        _caras59c = _v359.construir_caras(_mod59, _cam59b)
        _v359.encuadre(_caras59c, _cam59b)
        assert _cam59b.distancia_m > 0.0 and _cam59b.centro is not None, \
            "el encuadre calcula solo centro y distancia del FOV"
        _cam59b.tecla("Home")
        assert _cam59b.distancia_m == 0.0, "Home re-encuadra la distancia"
        import tempfile as _tmp59
        _png59 = os.path.join(_tmp59.mkdtemp(), "persp.png")
        _v359.export_vista3d_png(_caras59c, _cam59b, _png59,
                                 titulo="perspectiva")
        with open(_png59, "rb") as _fh59c:
            assert _fh59c.read(8) == b"\x89PNG\r\n\x1a\n", \
                "PNG determinista también en perspectiva"
        _ctx59.close()
        checks.append("cota de cubierta + vista en perspectiva v3.17.0: "
                      "OK (la cubierta nace sobre el top de los muros o "
                      "a la cota que el usuario fije con aviso si queda "
                      "baja, la explosión la acompaña y el 3D la respeta; "
                      "cámara con punto de fuga: P conmuta, el encuadre "
                      "calcula centro y distancia del FOV, el cercano "
                      "crece y el lejano encoge, PNG determinista)"
                      + _nota59)

        # -- 60: ascensores según Neufert + parasoles y pieles de
        #        fachada (v3.18.0) -----------------------------------
        from domain import ascensores as _asc60
        from domain import fachadas as _fac60
        _nota60 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_asc60.__file__, "r", encoding="utf-8") as _fh60:
                _src60 = _fh60.read()
            assert "CATALOGO" in _src60 \
                and "def generar_ascensor" in _src60 \
                and "def dimensiones_hueco" in _src60, \
                "catálogo Neufert de ascensores en el dominio"
            with open(_fac60.__file__, "r", encoding="utf-8") as _fh60b:
                _src60b = _fh60b.read()
            assert "def generar_parasoles" in _src60b \
                and "def generar_piel" in _src60b \
                and "ESTILO_PIEL" in _src60b, \
                "parasoles y pieles de fachada en el dominio"
        # conductual: catálogo exacto del libro y hueco real en el núcleo
        assert _asc60.dimensiones_hueco("pasajeros", 630)["puerta_m"] \
            == 0.80, "hueco de 630 kg con puerta central de 0.80 m"
        assert _asc60.dimensiones_hueco("hospital", 1275)["puerta_m"] \
            == 1.20, "el hospital lleva puerta de camillas (1.20 m)"
        _ctx60 = ApplicationContext().create_project(
            os.path.join(tmp, "check60.arqgen"), name="Check 60")
        from services.architecture_service import ArchitectureService \
            as _Arc60
        _arq60 = _Arc60(_ctx60)
        _n60a = _arq60.create_level("PB 60", 0.0, 3.0)
        _n60b = _arq60.create_level("P1 60", 3.0, 3.0)
        _arq60.create_space(_n60a.code, "Nucleo", "CORE",
                            [(0, 0), (3, 0), (3, 4.2), (0, 4.2)])
        _arq60.create_space(_n60a.code, "Sala", "LIVING_ROOM",
                            [(3, 0), (9, 0), (9, 4.2), (3, 4.2)])
        _arq60.create_space(_n60b.code, "Sala1", "LIVING_ROOM",
                            [(3, 0), (9, 0), (9, 4.2), (3, 4.2)])
        _r60 = _asc60.generar_ascensor(_ctx60, None)
        _e60 = _ctx60.architecture.list("ELEVATOR",
                                        _ctx60.project.id)[0]
        assert _e60.metadata["modo"] == "nucleo" \
            and _e60.metadata["puerta_lado"] == "E" \
            and abs(_e60.width_m - 1.8) < 1e-9, \
            "hueco dentro del núcleo con la puerta a la sala (este)"
        assert abs(_e60.metadata["altura_total_m"] - 6.0) < 1e-6, \
            "la altura servida suma los dos niveles"
        (_asc60.resumen_texto(_r60)).encode("cp1252")
        _r60b = _fac60.generar_parasoles(_ctx60, None)
        _lados60 = {d["lado"]: d for d in
                    (_r60b["parametros"]["lados_resueltos"])}
        assert _lados60["S"]["tipo"] == "horizontal" \
            and _lados60["E"]["tipo"] == "vertical" \
            and "N" not in _lados60, \
            "parasoles por orientación: sur horizontal, este vertical, " \
            "norte sin parasol"
        assert any("norte" in a for a in _r60b["avisos"]), \
            "aviso amable de la fachada norte"
        (_fac60.resumen_texto_parasoles(_r60b)).encode("cp1252")
        _r60c = _fac60.generar_piel(_ctx60, None, lados="S",
                                    tipo="baguette_terracota",
                                    separacion_m=0.9)
        _s60 = _ctx60.architecture.list("SKIN", _ctx60.project.id)[0]
        assert _s60.tipo == "baguette_terracota" \
            and abs(_s60.altura_m - 6.0) < 1e-6 \
            and abs(_s60.y - (-0.9)) < 1e-6, \
            "piel de terracota con cámara de 0.9 m subiendo 6.0 m"
        (_fac60.resumen_texto_piel(_r60c)).encode("cp1252")
        from services.quantity_service import QuantityService \
            as _QS60
        _QS60(_ctx60).compute_all()
        _qto60 = {(r["object_type"], r["formula_code"]): r["final_quantity"]
                  for r in _ctx60.quantities_repo.all(_ctx60.project.id)}
        assert _qto60.get(("ELEVATOR", "ELEVATOR_COUNT")) == 1.0 \
            and abs(_qto60.get(("ELEVATOR", "ELEVATOR_TRAVEL"), 0.0)
                    - 6.0) < 1e-6, \
            "QTO cuenta el ascensor y su recorrido"
        assert _qto60.get(("PARASOL", "PARASOL_COUNT")) == 1.0 \
            and _qto60.get(("SKIN", "SKIN_LENGTH"), 0.0) > 0.0, \
            "QTO mide parasoles y pieles"
        # 3D: hueco con cabina y puerta, lamas y plano de piel
        _mod60, _av60 = _v359.modelo3d_desde_proyecto(_ctx60)
        assert len(_mod60.ascensores) == 1 \
            and len(_mod60.parasoles) == 3 \
            and len(_mod60.pieles) == 1, \
            "el modelo 3D carga ascensores, parasoles y pieles"
        _caras60 = _v359.construir_caras(_mod60, _v359.Camara3D())
        _kinds60 = {c.kind for c in _caras60}
        assert {"ascensor", "cabina", "parasol", "piel"} <= _kinds60, \
            "el 3D dibuja hueco, cabina, lamas y piel"
        _sin60 = _v359.construir_caras(_mod60, _v359.Camara3D(),
                                       mostrar_fachada=False)
        assert not any(c.kind in ("parasol", "piel") for c in _sin60), \
            "el interruptor de fachada oculta parasoles y pieles"
        import tempfile as _tmp60
        _png60 = os.path.join(_tmp60.mkdtemp(), "fachada.png")
        _v359.export_vista3d_png(_caras60, _v359.Camara3D(), _png60,
                                 titulo="ascensores y fachada")
        with open(_png60, "rb") as _fh60c:
            assert _fh60c.read(8) == b"\x89PNG\r\n\x1a\n", \
                "PNG determinista con la fachada"
        _ctx60.close()
        checks.append("ascensores y fachada v3.18.0: OK (tablas de "
                      "Neufert con puerta por tipo, hueco dentro del "
                      "núcleo con puerta al vecino y altura servida; "
                      "parasoles por orientación con aviso en el norte; "
                      "piel de terracota con cámara ventilada; QTO de "
                      "hueco, recorrido, lamas y superficie; 3D con "
                      "cabina, lamas y pieles e interruptor de capa)"
                      + _nota60)

        # -- 61: escaleras por tipología, aberturas, iluminación y
        #        alarmas por locales (v3.19.0) ----------------------------
        from domain import aberturas as _abe61
        from domain import alarmas as _alr61
        from domain import escaleras as _esc61
        from domain import iluminacion as _ilu61
        from ui import view3d as _v361
        _nota61 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_esc61.__file__, "r", encoding="utf-8") as _fh61:
                _src61 = _fh61.read()
            assert "BLONDEL_MIN_M" in _src61 \
                and "def generar_escalera" in _src61, \
                "escaleras por tipología con Blondel en el dominio"
            with open(_abe61.__file__, "r", encoding="utf-8") as _fh61b:
                _src61b = _fh61b.read()
            assert "CATALOGO_PUERTAS" in _src61b \
                and "def simbolo_puntos" in _src61b, \
                "catálogos y símbolos de aberturas"
            with open(_ilu61.__file__, "r", encoding="utf-8") as _fh61c:
                _src61c = _fh61c.read()
            assert "LAMPARAS" in _src61c \
                and "def generar_iluminacion" in _src61c, \
                "catálogo de lámparas y método de los lúmenes"
            with open(_alr61.__file__, "r", encoding="utf-8") as _fh61d:
                _src61d = _fh61d.read()
            assert "def locales_protegibles" in _src61d \
                and "def generar_alarma" in _src61d, \
                "alarmas por locales seleccionados"
        # conductual: escalera en L dentro del hueco, Blondel y peldaños
        _ctx61 = ApplicationContext().create_project(
            os.path.join(tmp, "check61.arqgen"), name="Check 61")
        from services.architecture_service import ArchitectureService \
            as _Arc61
        _arq61 = _Arc61(_ctx61)
        _n61 = _arq61.create_level("Nivel 61", 0.0, 3.0)
        _arq61.create_space(_n61.code, "Hueco", "STAIR",
                            [(0, 0), (4, 0), (4, 4.5), (0, 4.5)])
        _arq61.create_space(_n61.code, "Sala", "LIVING_ROOM",
                            [(4, 0), (10, 0), (10, 5), (4, 5)])
        _w61 = _arq61.create_wall(_n61.code, (4, 0), (10, 0))
        _arq61.create_opening("DOOR", _w61.code, 0.9, 2.1, offset_m=1.0)
        _w61b = _arq61.create_wall(_n61.code, (10, 0), (10, 5))
        _arq61.create_opening("WINDOW", _w61b.code, 1.2, 1.4,
                              offset_m=1.0, sill_height_m=0.9)
        _r61 = _esc61.generar_escalera(_ctx61, None, tipo="L")
        _st61 = _ctx61.architecture.list("STAIR", _ctx61.project.id)[0]
        assert _st61.space_id and _st61.metadata.get("pasos") \
            and _st61.metadata.get("n_contrahuellas") == 18, \
            "escalera en L dentro del hueco con 18 peldaños"
        assert abs(_st61.metadata.get("contrahuella_m", 0.0)
                   - 3.0 / 18.0) < 1e-3, \
            "Blondel: contrahuella exacta sobre el desnivel"
        assert len(_esc61.geometria("caracol", 3.0,
                                    ancho_m=1.10)["pasos"]) == 18, \
            "el caracol genera sus peldaños en abanico"
        (_esc61.resumen_texto(_r61)).encode("cp1252")
        # aberturas: tipificación + símbolo
        _r61b = _abe61.asignar_tipos(_ctx61, "DOOR", "corredera")
        assert _r61b["asignadas"] == 1, "puerta tipificada"
        _d61 = _ctx61.architecture.list("DOOR", _ctx61.project.id)[0]
        assert _d61.metadata.get("abertura", {}).get("tipo") == "corredera" \
            and _abe61.simbolo_puntos("corredera", True, (0.0, 0.0),
                                      (1.0, 0.0), 0.9), \
            "la metadata lleva el tipo y el símbolo sale"
        (_abe61.resumen_texto(_r61b)).encode("cp1252")
        # iluminación: método de los lúmenes y luminarias reales
        _sala61 = [e for e in _ctx61.architecture.list(
            "SPACE", _ctx61.project.id)
            if e.space_type == "LIVING_ROOM"][0]
        assert _ilu61.dimensionar(20.0, 300, "led_panel")[
            "n_lamparas"] == 4, \
            "método de los lúmenes: 4 paneles para 20 m2 a 300 lux"
        _r61c = _ilu61.generar_iluminacion(
            _ctx61, None, lampara="led_panel", space_ids=[_sala61.id])
        _lum61 = [n for n in _ctx61.installations.list(
            "NODE", _ctx61.project.id) if n.kind == "LUMINAIRE"]
        assert len(_lum61) == _r61c["locales"][0]["n_lamparas"] \
            and _lum61[0].attrs.get("lampara") == "led_panel", \
            "luminarias LED en la red de alumbrado con sus atributos"
        (_ilu61.resumen_texto(_r61c)).encode("cp1252")
        # alarmas: locales elegidos, PIR + contactos + panel
        _r61d = _alr61.generar_alarma(_ctx61, None,
                                      space_ids=[_sala61.id])
        assert _r61d["zonas"][0]["contactos"] == 2 \
            and _r61d["zonas"][0]["vanos"] == 2, \
            "contactos magnéticos en puerta y ventana del local"
        _sec61 = [n for n in _ctx61.installations.list(
            "NODE", _ctx61.project.id) if n.attrs.get("origen_alarma")]
        assert len(_sec61) == len(_r61d["creados"]) \
            and _r61d["parametros"]["pirs"] >= 1, \
            "panel, teclado, sirena y PIR en la red INTRUSION"
        (_alr61.resumen_texto(_r61d)).encode("cp1252")
        # QTO de la escalera
        from services.quantity_service import QuantityService as _QS61
        _QS61(_ctx61).compute_all()
        _qto61 = {(r["object_type"], r["formula_code"]): r["final_quantity"]
                  for r in _ctx61.quantities_repo.all(_ctx61.project.id)}
        assert _qto61.get(("STAIR", "STAIR_RISERS")) == 18.0 \
            and _qto61.get(("STAIR", "STAIR_COUNT")) == 1.0 \
            and _qto61.get(("STAIR", "STAIR_HANDRAIL"), 0.0) > 10.0, \
            "QTO mide peldaños, huella, desarrollo y barandilla"
        # 3D: peldaños de la escalera en caras
        _mod61, _av61 = _v361.modelo3d_desde_proyecto(_ctx61)
        assert len(_mod61.escaleras) == 1, "el modelo 3D carga la escalera"
        _caras61 = _v361.construir_caras(_mod61, _v361.Camara3D())
        assert any(c.kind == "peldano" for c in _caras61), \
            "el 3D dibuja los peldaños"
        _png61 = os.path.join(_tmp60.mkdtemp(), "escalera.png")
        _v361.export_vista3d_png(_caras61, _v361.Camara3D(), _png61,
                                 titulo="escalera, aberturas, luz y alarma")
        with open(_png61, "rb") as _fh61e:
            assert _fh61e.read(8) == b"\x89PNG\r\n\x1a\n", \
                "PNG determinista con la escalera"
        _ctx61.close()
        checks.append("escaleras, aberturas, iluminación y alarmas "
                      "v3.19.0: OK (escalera en L dentro del hueco con "
                      "Blondel exacto y caracol en abanico; símbolo de "
                      "corredera y metadata de aberturas; 4 paneles LED "
                      "para 20 m2 a 300 lux colocados en la red de "
                      "alumbrado; alarma del local elegido con PIR, "
                      "contactos en puerta y ventana, panel y batería; "
                      "QTO de peldaños y barandilla; 3D con peldaños)"
                      + _nota61)

        context.close()

        # -- 62: especialidades de salud y asistente de local en modo
        #        MODIFICAR (v3.20.0) -------------------------------------
        from domain import mobiliario as _mob62
        from ui import editor_espacios as _edi62
        from ui import building_wizard as _bw62
        _nota62 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_edi62.__file__, "r", encoding="utf-8") as _fh62:
                _src62 = _fh62.read()
            assert "def cambiar_identidad" in _src62 \
                and "def mover_local" in _src62 \
                and "def resumen_completo" in _src62, \
                "asistente de local: identidad, geometría y diagnóstico"
            with open(_mob62.__file__, "r", encoding="utf-8") as _fh62b:
                _src62b = _fh62b.read()
            assert "mesa_autopsia" in _src62b \
                and 'Regla("rack_servidor", ("fila"' in _src62b, \
                "mobiliario de salud con el anclaje fila"
            with open(_bw62.__file__, "r", encoding="utf-8") as _fh62c:
                _src62c = _fh62c.read()
            assert '"CT_ROOM"' in _src62c and '"MORGUE"' in _src62c \
                and '"PROGRESSIVE_CARE"' in _src62c, \
                "programa hospitalario con las especialidades pedidas"
        # conductual: proyecto con un local que se vuelve morgue
        _ctx62 = ApplicationContext().create_project(
            os.path.join(tmp, "check62.arqgen"), name="Check 62")
        _arq62 = _Arc61(_ctx62)
        _n62 = _arq62.create_level("Planta", 0.0, 3.0)
        for _a62, _b62 in (((0, 0), (5, 0)), ((0, 0), (0, 3.5)),
                           ((0, 3.5), (5, 3.5)), ((5, 0), (5, 3.5))):
            _arq62.create_wall(_n62.code, _a62, _b62, 0.2)
        _loc62 = _arq62.create_space(
            _n62.code, "Sala técnica", "ROOM",
            [(0.0, 0.0), (5.0, 0.0), (5.0, 3.5), (0.0, 3.5)])
        # DNA: las 9 especialidades cargan con su ficha técnica
        for _t62 in ("CT_ROOM", "FLUOROSCOPY_ROOM", "ANATOMY_PATHOLOGY",
                     "MORGUE", "PROGRESSIVE_CARE", "MICROBIOLOGY_LAB",
                     "SERVER_ROOM", "WASTE_ROOM", "WAREHOUSE"):
            assert _ctx62.dna_registry.get(_t62) is not None, \
                f"especialidad {_t62} en el DNA"
        assert _ctx62.dna_registry.get("MORGUE").metadata.get(
            "friocamara"), "la morgue lleva su cámara de frío"
        # identidad: el local se vuelve morgue y la puerta pide 1,20
        _edi62.cambiar_identidad(_ctx62, _loc62.id, nombre="Morgue",
                                 uso="MORGUE")
        _edi62.crear_acceso(_ctx62, _loc62.id)
        _puerta62 = _ctx62.architecture.list("DOOR",
                                             _ctx62.project.id)[0]
        assert abs(float(_puerta62.width_m) - 1.2) < 1e-9, \
            "puerta de camilla de 1,20 m para la morgue"
        # geometría: mover el local lleva consigo boundary y muros
        _edi62.mover_local(_ctx62, _loc62.id, 1.0, 0.5)
        _loc62b = _ctx62.architecture.get("SPACE", _loc62.id)
        assert abs(float(_loc62b.boundary[0][0]) - 1.0) < 1e-6, \
            "el local completo se desplaza con sus muros"
        # iluminación de UN local: quirófano a 1000 lux, morgue a 200
        assert _ilu61.lux_para("OPERATING_ROOM") == 1000 \
            and _ilu61.lux_para("MORGUE") == 200, \
            "lux por uso hospitalario (quirófano 1000, morgue 200)"
        _edi62.iluminar_local(_ctx62, _loc62.id, lampara="led_panel")
        _lum62 = [n for n in _ctx62.installations.list(
            "NODE", _ctx62.project.id)
            if n.kind == "LUMINAIRE" and n.space_id == _loc62.id]
        _lum62luz = [n for n in _lum62 if n.attrs.get("origen_luz")]
        assert _lum62luz, \
            "luminarias de iluminar_local en la red de alumbrado"
        # mobiliario: mesa de autopsias con el anclaje fila servido
        _mob62.generar_mobiliario(_ctx62, space_ids=[_loc62.id],
                                  ambito="ambos")
        _kinds62 = {p.kind for p in _ctx62.architecture.list(
            "FURNITURE", _ctx62.project.id)}
        assert "mesa_autopsia" in _kinds62, \
            "la morgue se amuebla con su mesa de autopsias"
        # alarma del local + diagnóstico DNA completo en cp1252
        _edi62.alarmar_local(_ctx62, _loc62.id)
        _datos62 = _edi62.resumen_completo(_ctx62, _loc62.id)
        assert _datos62["dna"]["nombre_es"].startswith("Morgue") \
            and _datos62["alarma"] >= 1, \
            "diagnóstico con DNA y dispositivos de alarma contados"
        (_edi62.texto_resumen_completo(_datos62)).encode("cp1252")
        # programa hospitalario: el hospital trae las especialidades
        _data62 = _bw62.BuildingWizardData()
        _data62.usage_type = "Hospital"
        _n62b, _rel62 = _bw62.apply_usage_program(_data62)
        _tipos62 = {r.space_type for r in _data62.rooms}
        assert _n62b >= 30 and {"CT_ROOM", "MORGUE", "PROGRESSIVE_CARE",
                                "WAREHOUSE", "WASTE_ROOM"} <= _tipos62, \
            "el hospital del asistente trae las especialidades nuevas"
        _ctx62.close()
        checks.append("especialidades de salud y asistente de local "
                      "(modificar) v3.20.0: OK (9 especialidades en el "
                      "DNA con su ficha técnica; morgue con puerta de "
                      "camilla de 1,20 m y mesa de autopsias; mover el "
                      "local lleva muros y boundary; iluminación de un "
                      "solo local con lux por uso; alarma local; "
                      "hospital con tomografía, fluoroscopio, anatomía "
                      "patológica, microbiología, nodo, PGD y almacenes)"
                      + _nota62)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # -- 63: pasillos por uso hospitalario (DNA), equipos médicos en
    #        el presupuesto vivo y ficha imprimible del local
    #        (v3.21.0) -------------------------------------------------
    try:
        from ui import variant_budget as _vb63
        from exporters import ficha_local as _fl63
        from engines.precons_engine import PreconsRuleset as _pr63
        from app.paths import resource_path as _rp63
        _nota63 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_bw62.__file__, "r", encoding="utf-8") as _fh63:
                _src63 = _fh63.read()
            assert "def suggested_corridor_width_for_rooms" in _src63 \
                and "def pasillo_minimo_de_uso" in _src63, \
                "pasillo del asistente guiado por el DNA de los locales"
            with open(_vb63.__file__, "r", encoding="utf-8") as _fh63b:
                _src63b = _fh63b.read()
            assert "EQUIPOS_POR_USO" in _src63b \
                and "CATEGORIAS_SIN_CALIDAD" in _src63b, \
                "categoría Equipos con aparatos de referencia en el " \
                "presupuesto vivo"
            with open(_fl63.__file__, "r", encoding="utf-8") as _fh63c:
                _src63c = _fh63c.read()
            assert "def export_ficha_local_pdf" in _src63c \
                and "def _planta" in _src63c, \
                "ficha imprimible del local con su planta dibujada"
        # conductual: el DNA de cada local trae su pasillo_m y el
        # pasillo sube al local más exigente, citando al culpable
        assert _bw62.pasillo_minimo_de_uso("CT_ROOM") == 2.4 \
            and _bw62.pasillo_minimo_de_uso("MORGUE") == 2.0 \
            and _bw62.pasillo_minimo_de_uso("ROOM") is None, \
            "pasillo_m en el DNA de las especialidades (2,40 camillas)"
        _ancho63, _culpable63 = _bw62.suggested_corridor_width_for_rooms(
            "Oficina", ["OFFICE", "CT_ROOM"])
        assert _ancho63 == 2.4 and _culpable63 == "CT_ROOM", \
            "el pasillo sube al DNA del local más exigente del programa"
        # presupuesto vivo: el hospital del asistente factura sus
        # aparatos (tomógrafo, arco C…) en la categoría Equipos con
        # precios de referencia y sin avisos de catálogo
        _rs63 = _pr63.from_file(_rp63("rulesets",
                                      "precons_iii_rospres_330.json"))
        _vs63 = _bw62.generate_variants(_data62)
        _filas63 = _vb63.variant_takeoff(_data62, _vs63[0])
        _eq63 = [f for f in _filas63 if f["category"] == "Equipos"]
        assert _eq63 and any("Tomógrafo" in f["concept"] for f in _eq63), \
            "el presupuesto vivo factura el tomógrafo de la tomografía"
        _costo63 = _vb63.estimate_variant_cost(_data62, _vs63[0], _rs63)
        assert _costo63.categories.get("Equipos", 0.0) > 0.0, \
            "categoría Equipos con importe en la estimación"
        _eco63 = _vb63.estimate_variant_cost(_data62, _vs63[0], _rs63,
                                             calidad="Económica")
        assert _eco63.categories.get("Equipos") == \
            _costo63.categories.get("Equipos"), \
            "la calidad de acabados no toca a los equipos"
        # ficha imprimible: proyecto propio (el 62 no hace commit:
        # el commit lo hace el GUI), local morgue con puerta y planta
        _ctx63 = ApplicationContext().create_project(
            os.path.join(tmp, "check63.arqgen"), name="Check 63")
        _arq63 = _Arc61(_ctx63)
        _n63 = _arq63.create_level("Planta", 0.0, 3.0)
        for _a63, _b63 in (((0, 0), (5, 0)), ((0, 0), (0, 3.5)),
                           ((0, 3.5), (5, 3.5)), ((5, 0), (5, 3.5))):
            _arq63.create_wall(_n63.code, _a63, _b63, 0.2)
        _loc63 = _arq63.create_space(
            _n63.code, "Morgue de prueba", "MORGUE",
            [(0.0, 0.0), (5.0, 0.0), (5.0, 3.5), (0.0, 3.5)])
        _edi62.crear_acceso(_ctx63, _loc63.id)
        _geo63 = _edi62.geometria_local(_ctx63, _loc63.id)
        assert len(_geo63["boundary"]) >= 3 and _geo63["muros"] \
            and any(v["kind"] == "DOOR" and v.get("muro")
                    for v in _geo63["vanos"]), \
            "geometría del local: muros recortados y vanos ubicados"
        _f63 = os.path.join(tmp, "check63_ficha.pdf")
        _fl63.export_ficha_local_pdf(_ctx63, _loc63.id, _f63)
        with open(_f63, "rb") as _fh63d:
            _blob63 = _fh63d.read()
        assert _blob63.startswith(b"%PDF") and len(_blob63) > 2000, \
            "ficha del local como PDF válido"
        _ctx63.close()
        checks.append("pasillos hospitalarios, equipos en el presupuesto "
                      "vivo y ficha del local v3.21.0: OK (pasillo_m en "
                      "el DNA: camillas 2,40 / carros 2,00 / laboratorio "
                      "1,80 / nodo 1,50; el asistente sube el pasillo y "
                      "cita al local culpable; el hospital factura "
                      "tomógrafo, arco C y compañía en Equipos con "
                      "precios de referencia que la calidad no toca; la "
                      "ficha del local sale en PDF con identidad, DNA, "
                      "vanos, mobiliario, instalaciones, planta dibujada "
                      "y diagnóstico)" + _nota63)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())
    finally:
        # Cleanup temp tree best-effort
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # -- 64: especificaciones técnicas hospitalarias del documento
    #        (fichas + cuadro de cotas MIN/REC + prioridad) y CONTROL
    #        DE VALIDACIÓN DIMENSIONAL por local (v3.22.0) -------------
    try:
        import tempfile as _tf64
        from domain import hospital_specs as _hs64
        from domain import iluminacion as _ilu64
        from domain import mobiliario as _mob64
        from ui import variant_budget as _vb64
        from exporters import ficha_local as _fl64
        from ui import editor_espacios as _edi64
        from services.architecture_service import ArchitectureService \
            as _Arc64
        from domain.knowledge import SpaceDNARegistry as _sdr64
        ui_appwin64 = __import__("ui.app_window", fromlist=["app_window"])
        _nota64 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_hs64.__file__, "r", encoding="utf-8") as _fh64:
                _src64 = _fh64.read()
            assert "def validar_local" in _src64 \
                and "def validar_proyecto" in _src64, \
                "motor de validación dimensional del documento"
            with open(_fl64.__file__, "r", encoding="utf-8") as _fh64b:
                _src64b = _fh64b.read()
            assert "Especificaciones técnicas del uso" in _src64b \
                and "Control de validación dimensional" in _src64b, \
                "ficha del local con la ficha técnica y el control §19"
            with open(ui_appwin64.__file__, "r", encoding="utf-8") as _fh64c:
                _src64c = _fh64c.read()
            assert "_validar_cotas_local" in _src64c, \
                "botón «Validar cotas» en el asistente de local"
        # conductual: el documento cargado y completo
        _specs64 = _hs64.cargar_specs()
        assert _specs64 is not None, \
            "hospital_specs.json presente en los recursos"
        assert len(_specs64.fichas) >= 60 \
            and len(_specs64.cotas_cuadro) >= 53 \
            and len(_specs64.checklist) >= 22 and _specs64.fuentes \
            and _specs64.advertencia, \
            "documento: 60 fichas, 53 cuadros de cotas, checklist y fuentes"
        assert _specs64.prioridad_de("OPERATING_ROOM") == "critica" \
            and _specs64.prioridad_de("OFFICE") == "baja", \
            "matriz de prioridad funcional (quirófano crítica)"
        _item64 = _specs64.item_cotas("OPERATING_ROOM")
        assert _item64 and abs(float(_item64["min_m2"]["min"]) - 37.2) \
            < 0.01, "cota del quirófano del cuadro (FGI 37,2 m2)"
        assert _specs64.ficha("MORGUE") is not None \
            and "higiene" in _specs64.ficha("MORGUE")["campos"], \
            "ficha técnica cualitativa de la morgue"
        # DNA ampliado: 40 especialidades nuevas con pasillo y puerta
        _reg64 = ApplicationContext().dna_registry
        assert len(_reg64) >= 75, "DNA ampliado a las especialidades "\
            "del documento (77 tipos)"
        assert "NICU" in _reg64.types() and "AUTOPSY_ROOM" in _reg64.types() \
            and "CATH_LAB" in _reg64.types(), \
            "especialidades nuevas en el DNA (UCI neonatal, autopsias, " \
            "hemodinamia...)"
        _nicu64 = _reg64.require("NICU")
        assert _nicu64.metadata.get("pasillo_m") == 2.4 \
            and _nicu64.metadata.get("neufert", {}).get("puerta_m") == 1.2, \
            "DNA del tipo nuevo con pasillo de camilla y puerta"
        # capas por uso: lux, mobiliario y equipos
        assert _ilu64.LUX_POR_USO.get("DELIVERY_ROOM") == 500 \
            and _ilu64.LUX_POR_USO.get("MRI_ROOM") == 150, \
            "lux por uso de las especialidades nuevas"
        assert "NICU" in _mob64.REGLAS and "LAUNDRY" in _mob64.REGLAS, \
            "mobiliario de las especialidades nuevas"
        assert "MRI_ROOM" in _vb64.EQUIPOS_POR_USO, \
            "equipos (resonancia) en el presupuesto vivo"
        # proyecto propio: morgue conforme y quirófano escaso
        _tmp64 = _tf64.mkdtemp(prefix="check64_")
        try:
            _ctx64 = ApplicationContext().create_project(
                os.path.join(_tmp64, "check64.arqgen"), name="Check 64")
            _arq64 = _Arc64(_ctx64)
            _n64 = _arq64.create_level("Planta", 0.0, 3.0)
            for _coords64 in ((((0, 0), (5, 0)), ((0, 0), (0, 3.5)),
                               ((0, 3.5), (5, 3.5)), ((5, 0), (5, 3.5))),
                              (((6, 0), (11, 0)), ((6, 0), (6, 5)),
                               ((6, 5), (11, 5)), ((11, 0), (11, 5)))):
                for _a64, _b64 in _coords64:
                    _arq64.create_wall(_n64.code, _a64, _b64, 0.2)
            _morgue64 = _arq64.create_space(
                _n64.code, "Morgue", "MORGUE",
                [(0.0, 0.0), (5.0, 0.0), (5.0, 3.5), (0.0, 3.5)])
            _qui64 = _arq64.create_space(
                _n64.code, "Quirófano escaso", "OPERATING_ROOM",
                [(6.0, 0.0), (11.0, 0.0), (11.0, 5.0), (6.0, 5.0)])
            _ctx64.commit()
            _inf64 = _edi64.validacion_local(_ctx64, _morgue64.id)
            _sev64 = {h["codigo"]: h["severidad"]
                      for h in _inf64["hallazgos"]}
            assert _sev64.get("V01") == "ok" and _inf64["prioridad"] == \
                "media" and len(_inf64["checklist"]) >= 22, \
                "morgue conforme: superficie >= mínima del cuadro y " \
                "checklist completo"
            _inf64b = _edi64.validacion_local(_ctx64, _qui64.id)
            _sev64b = {h["codigo"]: h["severidad"]
                       for h in _inf64b["hallazgos"]}
            assert _sev64b.get("V01") == "fallo" \
                and _sev64b.get("V02") == "fallo", \
                "quirófano de 5x5 señalado: 25 m2 < 37,2 del cuadro FGI"
            (_edi64.texto_validacion(_inf64b)).encode("cp1252")
            _rep64 = _hs64.validar_proyecto(_ctx64)
            assert _rep64["resumen"]["fallos"] >= 2, \
                "validación de todo el proyecto cuenta los fallos"
            _f64 = os.path.join(_tmp64, "check64_ficha.pdf")
            _fl64.export_ficha_local_pdf(_ctx64, _morgue64.id, _f64)
            with open(_f64, "rb") as _fh64d:
                _blob64 = _fh64d.read()
            assert _blob64.startswith(b"%PDF") and len(_blob64) > 4000, \
                "ficha del local con las secciones hospitalarias (PDF)"
            _ctx64.close()
        finally:
            import shutil as _sh64
            _sh64.rmtree(_tmp64, ignore_errors=True)
        checks.append("especificaciones técnicas hospitalarias y control "
                      "de validación dimensional v3.22.0: OK (documento "
                      "integrado con 60 fichas y 53 cuadros de cotas "
                      "MIN/REC tipo A-F; 40 especialidades nuevas en el "
                      "DNA con lux, mobiliario y equipos; el asistente "
                      "de local valida superficie, ancho, altura, "
                      "puertas y pasillos del local contra su uso con "
                      "el checklist de la sección 19 y la ficha PDF lo "
                      "imprime con fuentes y advertencia)" + _nota64)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # -- 65: CATÁLOGO MAESTRO DE VIVIENDAS del documento del usuario
    #        (tipologías + compatibilidad §27 + programa paramétrico §7
    #        + validación VIV001-030) y calidades 1-5 (v3.23.0) ----------
    try:
        import tempfile as _tf65
        from domain import vivienda_specs as _vs65
        from ui import building_wizard as _bw65
        from ui import variant_budget as _vb65
        from services.architecture_service import ArchitectureService \
            as _Arc65
        _nota65 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_vs65.__file__, "r", encoding="utf-8") as _fh65:
                _src65 = _fh65.read()
            assert "def validar_vivienda" in _src65 \
                and "REQUIERE_CALCULO" in _src65, \
                "motor de validación de vivienda con la marca del §81"
            with open(_bw65.__file__, "r", encoding="utf-8") as _fh65b:
                _src65b = _fh65b.read()
            assert "def aplicar_programa_vivienda" in _src65b \
                and "def vivienda_advisories" in _src65b, \
                "programa paramétrico y avisos del catálogo en el wizard"
        # conductual: el catálogo cargado y completo
        _cat65 = _vs65.cargar_catalogo()
        assert _cat65 is not None, \
            "vivienda_catalogo.json presente en los recursos"
        _res65 = _cat65.resumen()
        assert _res65["tipologias"] == 30 and _res65["sistemas_"
                                                     "constructivos"] == 25 \
            and _res65["estilos"] == 30 \
            and _res65["rangos_locales"] >= 20 \
            and _res65["validaciones"] == 30 and _res65["conflictos"] == 15, \
            "catálogo: 30 tipologías, 25 sistemas, 30 estilos, rangos, " \
            "30 validaciones y 15 conflictos"
        assert _cat65.nivel_compatibilidad("colonial", "mamposteria") == 3 \
            and _cat65.nivel_compatibilidad("minimalista", "adobe") == 0 \
            and _cat65.texto_compatibilidad(0) == "incompatible", \
            "matriz de compatibilidad estilo-sistema del §27 (0-3)"
        assert _vs65.compatibilidad_gui(
            "Colonial cubano",
            "Mampostería de bloque + losa de vigueta") == 3, \
            "compatibilidad con los nombres de la GUI"
        assert _cat65.rango("SALA")["min"] == 16.0 \
            and _cat65.rango("SALA")["max"] == 35.0, \
            "rangos de programación del §7 (sala 16-35 m2)"
        assert _cat65.nivel_de_relacion("BAÑO", "COMEDOR") == "X", \
            "relación a evitar del §8 (baño-comedor = X)"
        # calidades 1-5 del §51 en el presupuesto vivo
        assert len(_vb65.CALIDADES) == 5 \
            and "Lujo" in _vb65.CALIDADES \
            and "Media" in _vb65.CALIDADES, \
            "calidades del presupuesto vivo alineadas con el §51"
        # programa paramétrico: aislada con 4 dormitorios y 2 baños
        _data65 = _bw65.BuildingWizardData()
        _data65.usage_type = "Vivienda"
        _data65.vivienda_tipologia = "Unifamiliar aislada"
        _data65.vivienda_dormitorios = 4
        _data65.vivienda_banos = 2
        _bw65.apply_usage_program(_data65)
        _nombres65 = [r.name for r in _data65.rooms]
        assert len(_nombres65) == 13 and "Garaje" in _nombres65 \
            and "Dormitorio 4" in _nombres65 \
            and "Baño social" in _nombres65, \
            "programa paramétrico del §7 (aislada 4 dormitorios con " \
            "garaje)"
        assert any(r.with_door for r in _data65.relations), \
            "relaciones del §8 con puerta (nivel 3)"
        # proyecto propio: validación VIV completa y honesta
        _tmp65 = _tf65.mkdtemp(prefix="check65_")
        try:
            _ctx65 = ApplicationContext().create_project(
                os.path.join(_tmp65, "check65.arqgen"), name="Check 65")
            _arq65 = _Arc65(_ctx65)
            _n65 = _arq65.create_level("Planta", 0.0, 3.0)
            for _a65, _b65 in ((((0, 0), (5, 0)), ((0, 0), (0, 4)),
                                ((0, 4), (5, 4)), ((5, 0), (5, 4)))):
                _arq65.create_wall(_n65.code, _a65, _b65, 0.2)
            _arq65.create_space(
                _n65.code, "Dormitorio ciego", "BEDROOM",
                [(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)])
            _ctx65.commit()
            _inf65 = _vs65.validar_vivienda(_ctx65)
            _cod65 = [h["codigo"] for h in _inf65["hallazgos"]]
            assert len(_cod65) == 30 and len(set(_cod65)) == 30, \
                "las 30 validaciones VIV001-030 sobre el proyecto"
            _mapa65 = {h["codigo"]: h for h in _inf65["hallazgos"]}
            assert _mapa65["VIV007"]["severidad"] == "fallo" \
                and _mapa65["VIV030"]["severidad"] == "fallo", \
                "dormitorio sin vano señalado por VIV007 y VIV030"
            assert _mapa65["VIV013"]["estado"] == "requiere calculo" \
                and _mapa65["VIV017"]["estado"] == "requiere calculo", \
                ("puesta a tierra y suelo marcados "
                 "REQUIERE_CALCULO_ESPECIALIZADO (§81)")
            (_vs65.texto_validacion_vivienda(_inf65)).encode("cp1252")
            _ctx65.close()
        finally:
            import shutil as _sh65
            _sh65.rmtree(_tmp65, ignore_errors=True)
        checks.append("catálogo maestro de viviendas v3.23.0: OK "
                      "(30 tipologías, 25 sistemas constructivos, 20 "
                      "estructurales y 30 estilos del documento con la "
                      "matriz de compatibilidad 0-3 del §27; programa "
                      "paramétrico de vivienda con los rangos del §7 y "
                      "las relaciones del §8; validación VIV001-030 con "
                      "estados medido/pendiente/REQUIERE_CALCULO_"
                      "ESPECIALIZADO; calidades del presupuesto vivo "
                      "1-5)" + _nota65)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # -- 66: ESTUDIOS DE VIVIENDA del catálogo (alternativas §62-63,
    #        modulación §56 y solar FV §38) (v3.24.0) -------------------
    try:
        import tempfile as _tf66
        from domain import vivienda_estudios as _ve66
        from domain import vivienda_specs as _vs66
        from services.architecture_service import ArchitectureService \
            as _Arc66
        _nota66 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_ve66.__file__, "r", encoding="utf-8") as _fh66:
                _src66 = _fh66.read()
            assert "def generar_alternativas" in _src66 \
                and "def evaluar_modulacion" in _src66 \
                and "def dimensionar_solar" in _src66 \
                and "REQUIERE_CALCULO" in _src66, \
                "los tres estudios del catálogo con la marca del §81"
        # conductual: el catálogo v1.1 trae los bloques de los estudios
        _cat66 = _vs66.cargar_catalogo()
        assert _cat66 is not None and _cat66.version >= "1.1", \
            "vivienda_catalogo.json versión 1.1 con los bloques nuevos"
        _com66 = _cat66.comparacion_sistemas
        assert _com66.get("sistemas") == ["mamposteria_confinada",
                                          "hormigon_aporticado",
                                          "steel_framing", "modular"], \
            "cuatro sistemas comparables del §62-63"
        _ene66 = _cat66.energia_solar
        assert _ene66.get("horas_sol_pico_defecto") == 5.0 \
            and _ene66.get("area_panel_m2") == 2.0, \
            "parámetros de referencia del §38 (configurables §66)"
        # solar FV: ejemplo cerrado (5 kWh, HSP 5.0, panel 450 W)
        _sol66 = _ve66.dimensionar_solar(
            consumo_diario_kwh=5.0, horas_sol_pico=5.0,
            potencia_panel_w=450.0, eficiencia=0.20, perdidas=0.15,
            autonomia_dias=1.0)
        _fv66 = _sol66["fv"]
        assert _fv66["numero_paneles"] == 14 \
            and abs(_fv66["potencia_total_kw"] - 6.3) < 1e-9 \
            and abs(_fv66["capacidad_bateria_kwh"] - 6.25) < 1e-9, \
            "dimensionado FV del §38: 14 paneles de 6.30 kW con " \
            "batería 6.25 kWh"
        (_ve66.texto_solar(_sol66)).encode("cp1252")
        # alternativas §62-63: siete, A/B/C por nivel y 1-4 por sistema
        _alt66 = _ve66.generar_alternativas(
            dormitorios=3, banos=2, estilo_label="Colonial cubano",
            sistema_label="Mampostería de bloque + losa de vigueta")
        _claves66 = [a["clave"] for a in _alt66["alternativas"]]
        _por66 = {a["clave"]: a for a in _alt66["alternativas"]}
        assert len(_claves66) == 7 \
            and abs(_por66["A"]["costo_indice"] - 85.0) < 1e-6 \
            and abs(_por66["B"]["costo_indice"] - 100.0) < 1e-6 \
            and abs(_por66["C"]["costo_indice"] - 130.0) < 1e-6 \
            and _alt66["recomendada"] == "A", \
            "alternativas A/B/C (niveles 1/2/4 del §51) y 1-4 por " \
            "sistema con la recomendación por compatibilidad"
        (_ve66.texto_alternativas(_alt66)).encode("cp1252")
        # modulación §56 sobre proyecto propio: muro de 4.30 fuera de módulo
        _tmp66 = _tf66.mkdtemp(prefix="check66_")
        try:
            _ctx66 = ApplicationContext().create_project(
                os.path.join(_tmp66, "check66.arqgen"), name="Check 66")
            _arq66 = _Arc66(_ctx66)
            _n66 = _arq66.create_level("Planta", 0.0, 3.0)
            _arq66.create_wall(_n66.code, (0.0, 0.0), (4.3, 0.0), 0.2)
            _ctx66.commit()
            _mod66 = _ve66.evaluar_modulacion(_ctx66, 1.20)
            _fuera66 = [p for p in _mod66["piezas_fuera"]
                        if p["categoria"] == "MUROS"]
            assert len(_fuera66) == 1 \
                and abs(_fuera66[0]["sugerencias_m"][0] - 3.6) < 1e-6 \
                and abs(_fuera66[0]["sugerencias_m"][1] - 4.8) < 1e-6, \
                "modulación §56: muro de 4.30 fuera del módulo 1.20 " \
                "con sugerencias 3.60/4.80"
            (_ve66.texto_modulacion(_mod66)).encode("cp1252")
            _ctx66.close()
        finally:
            import shutil as _sh66
            _sh66.rmtree(_tmp66, ignore_errors=True)
        checks.append("estudios de vivienda v3.24.0: OK (alternativas "
                      "comparables §62-63: A/B/C por nivel de acabado "
                      "y 1/2/3/4 por sistema constructivo con las "
                      "métricas del §63 y recomendación por "
                      "compatibilidad; modulación §56 con módulos "
                      "0.60/1.20/1.25/1.50 y personalizado sobre "
                      "locales, muros, puertas y ventanas; energía "
                      "solar §38 FOTOVOLTAICO/SOLAR_TERMICO/HIBRIDO "
                      "con paneles, batería, inversor y superficie; "
                      "instalación definitiva marcada REQUIERE_CALCULO_"
                      "ESPECIALIZADO)" + _nota66)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # -- 67: CENTROS COMERCIALES Y OFICINAS del documento (programa
    #        §89-90, relaciones §78, validación CC/OF) (v3.25.0) --------
    try:
        import tempfile as _tf67
        from domain import comercial_specs as _cs67
        from ui import building_wizard as _bw67
        from services.architecture_service import ArchitectureService \
            as _Arc67
        _nota67 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_cs67.__file__, "r", encoding="utf-8") as _fh67:
                _src67 = _fh67.read()
            assert "def validar_local" in _src67 \
                and "def validar_proyecto" in _src67 \
                and "REQUIERE_CALCULO" in _src67, \
                "el validador CC/OF con la marca del §101"
            with open(_bw67.__file__, "r", encoding="utf-8") as _fh67:
                _src67b = _fh67.read()
            assert "def aplicar_programa_comercial" in _src67b \
                and "def comercial_tipologia_choices" in _src67b, \
                "el asistente carga el programa §89-90 del documento"
        # conductual: el documento versionado
        _doc67 = _cs67.cargar_specs()
        assert _doc67 is not None and _doc67.version == "1.0", \
            "comercial_specs.json v1.0 del documento CC/OF"
        _res67 = _doc67.resumen()
        assert _res67["tipologias"] == 20 and _res67["cuadros"] == 59 \
            and _res67["relaciones"] == 20 \
            and _res67["programas"] == 2, \
            "20 tipologías CC/OF, 59 cuadros MIN/REC, relaciones del " \
            "§78 y programas §89-90"
        assert _res67["prioridades"] == 12 \
            and _res67["requiere_calculo"] == 8, \
            "prioridades P01-P12 y los 8 temas de cálculo del §101"
        _min67 = _doc67.minimos_de("RETAIL_LOCAL")
        assert _min67["area"] == 15.0 and _min67["ancho"] == 3.0, \
            "cuadro del local comercial (15 m2, frente 3.00 m)"
        assert _doc67.gamas_superficie("RETAIL_LOCAL") == \
            ["15-40 m2", "40-100 m2", "100-500 m2"], \
            "las tres gamas del local comercial (§7)"
        assert _doc67.nivel_de_relacion(
            "CENTRO_COMERCIAL", "GALERIA", "LOCALES") == "3" \
            and _doc67.nivel_de_relacion(
                "CENTRO_COMERCIAL", "RESIDUOS", "PUBLICO") == "0", \
            "relación prioritaria galería-locales y prohibición " \
            "residuos-público del §78"
        # asistente: programa mínimo del §89-90 por familia
        _choices67 = _bw67.comercial_tipologia_choices()
        assert len(_choices67) == 21, \
            "combo de tipologías CC/OF (sin tipología + 20 del §1)"
        _datos67 = _bw67.BuildingWizardData()
        _datos67.usage_type = _bw67.USO_COMERCIAL_CC
        _n67, _r67 = _bw67.apply_usage_program(_datos67)
        assert _n67 == 13 and _r67 >= 6, \
            "programa mínimo de centro comercial (§89): 13 locales " \
            "con relaciones del §78"
        _tipos67 = {r.space_type for r in _datos67.rooms}
        assert {"GALLERY", "RETAIL_LOCAL", "TIENDA_ANCLA",
                "LOADING_DOCK", "WASTE_ROOM"} <= _tipos67, \
            "galería, locales, ancla, carga y residuos del §89"
        # validación sobre proyecto propio generado
        _tmp67 = _tf67.mkdtemp(prefix="check67_")
        try:
            _ctx67 = ApplicationContext().create_project(
                os.path.join(_tmp67, "check67.arqgen"), name="Check 67")
            _datos67.name = "Check 67"
            _creado67 = _bw67.apply_plan(_datos67, _ctx67)
            assert _creado67, "el plan CC/OF se genera"
            _inf67 = _cs67.validar_proyecto(_ctx67)
            assert _inf67["familias"] == ["CENTRO_COMERCIAL"], \
                "familia detectada por la metadata del asistente"
            _mapa67 = {h["codigo"]: h for h in _inf67["hallazgos"]
                       if h["codigo"].startswith("CM")}
            assert _mapa67["CM01"]["severidad"] == "ok" \
                and _mapa67["CM02"]["severidad"] == "ok" \
                and _mapa67["CM03"]["severidad"] == "ok", \
                "programa §89-90 completo, relaciones §78 trazadas y " \
                "sin prohibiciones residuos/carga contra público"
            _rc67 = [h for h in _inf67["hallazgos"]
                     if h["codigo"].startswith("RC")]
            assert len(_rc67) == 8 and all(
                h["estado"] == "requiere calculo" for h in _rc67), \
                ("los 8 temas del documento marcados "
                 "REQUIERE_CALCULO_ESPECIALIZADO (§101)")
            # un local escaso a propósito: local comercial de 4 m2
            _arq67 = _Arc67(_ctx67)
            _niv67 = _arq67.create_level("Planta Prueba", 10.0, 3.0)
            _arq67.create_space(_niv67.code, "Local escaso",
                                "RETAIL_LOCAL",
                                [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0),
                                 (0.0, 2.0)])
            _ctx67.commit()
            _locales67 = [s for s in
                          _ctx67.architecture.list(
                              "SPACE", _ctx67.project.id)
                          if getattr(s, "space_type", "") ==
                          "RETAIL_LOCAL"]
            _escaso67 = next(s for s in _locales67
                             if s.name == "Local escaso")
            _inf_escaso67 = _cs67.validar_local(_ctx67, _escaso67.id)
            _cod67 = {h["codigo"]: h
                      for h in _inf_escaso67["hallazgos"]}
            assert _cod67["C01"]["severidad"] == "fallo" \
                and "15.00" in _cod67["C01"]["mensaje"], \
                "superficie 4.00 m2 < mínima 15.00 m2 del cuadro (§7)"
            (_cs67.texto_validacion_comercial(_inf67)).encode("cp1252")
            _ctx67.close()
        finally:
            import shutil as _sh67
            _sh67.rmtree(_tmp67, ignore_errors=True)
        checks.append("documento comercial CC/OF v3.25.0: OK "
                      "(20 tipologías y 59 cuadros MIN/REC del "
                      "documento; programa mínimo §89-90 con medidas "
                      "de los cuadros y relaciones del §78 en el "
                      "asistente; validar_local/validar_proyecto con "
                      "programa, relaciones y prohibiciones "
                      "residuos/carga contra público, porcentajes §81, "
                      "eficiencia §82, estacionamiento §45, evacuación "
                      "IBC 2024 y galería §6; HVAC, rociadores, CCTV y "
                      "escaleras mecánicas marcados REQUIERE_CALCULO_"
                      "ESPECIALIZADO §101)" + _nota67)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # -- 68: ESCUELAS Y CÍRCULOS INFANTILES del documento (programa
    #        §106-109, relaciones §98-101, validación ED) (v3.26.0) -----
    try:
        import tempfile as _tf68
        from domain import educacion_specs as _ed68
        from ui import building_wizard as _bw68
        from services.architecture_service import ArchitectureService \
            as _Arc68
        _nota68 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_ed68.__file__, "r", encoding="utf-8") as _fh68:
                _src68 = _fh68.read()
            assert "def validar_local" in _src68 \
                and "def validar_proyecto" in _src68 \
                and "REQUIERE_CALCULO" in _src68, \
                "el validador educacional con la marca del §78/§83-85"
            with open(_bw68.__file__, "r", encoding="utf-8") as _fh68:
                _src68b = _fh68.read()
            assert "def aplicar_programa_educacion" in _src68b \
                and "def educacion_tamano_choices" in _src68b, \
                "el asistente carga el programa §106-109 del documento"
        # conductual: el documento versionado
        _doc68 = _ed68.cargar_specs()
        assert _doc68 is not None and _doc68.version == "1.0", \
            "educacion_specs.json v1.0 del documento educacional"
        _res68 = _doc68.resumen()
        assert _res68["tipologias"] == 4 and _res68["cuadros"] == 82 \
            and _res68["programas"] == 4, \
            "4 tipologías ED, 82 cuadros MIN/REC y programas §106-109"
        assert _res68["reglas"] == 11 and _res68["conflictos"] == 18, \
            "reglas del §111-112 y conflictos del §115"
        _min68 = _doc68.minimos_de("CLASSROOM")
        assert _min68["area"] == 40.0 and _min68["altura"] == 2.70, \
            "cuadro del aula (40 m2 de primaria, 2.70 m de altura §2/§5)"
        assert _doc68.nivel_de_relacion(
            "ESCUELA_PRIMARIA", "AULA", "SANITARIOS") == "3" \
            and _doc68.nivel_de_relacion(
                "ESCUELA_PRIMARIA", "COCINA", "BASURA") == "0", \
            "relación prioritaria aula-sanitarios y flujo prohibido " \
            "cocina-basura (§99/§102)"
        # asistente: programa paramétrico por capacidad (§4: NUM_AULAS
        # = CEIL(alumnos / alumnos por aula))
        _choices68 = _bw68.educacion_tamano_choices()
        assert _choices68[0] == _bw68.EDU_SIN_TAMANO \
            and any(c.startswith("Escuela primaria: Media")
                    for c in _choices68), \
            "combo de tamaño/capacidad del documento ED"
        _datos68 = _bw68.BuildingWizardData()
        _datos68.usage_type = "Escuela primaria"
        _datos68.educacion_tamano = \
            "Escuela primaria: Pequeña (60-180 alumnos)"
        _n68, _r68 = _bw68.apply_usage_program(_datos68)
        assert _n68 >= 20 and _r68 >= 5, \
            "programa paramétrico de primaria con aulas, patio, " \
            "gimnasio, comedor y servicio del §106"
        assert len([r for r in _datos68.rooms
                    if r.space_type == "CLASSROOM"]) == 5, \
            "120 alumnos a 25 por aula piden 5 aulas (§4/§111)"
        _meta68 = _bw68._educacion_metadata(_datos68)
        assert _meta68["familia"] == "ESCUELA_PRIMARIA" \
            and _meta68["alumnos"] == 120, \
            "metadata educacional con la capacidad para la validación"
        # validación sobre proyecto propio generado
        _tmp68 = _tf68.mkdtemp(prefix="check68_")
        try:
            _ctx68 = ApplicationContext().create_project(
                os.path.join(_tmp68, "check68.arqgen"), name="Check 68")
            _datos68.name = "Check 68"
            _creado68 = _bw68.apply_plan(_datos68, _ctx68)
            assert _creado68, "el plan educacional se genera"
            _inf68 = _ed68.validar_proyecto(_ctx68)
            assert _inf68["familias"] == ["ESCUELA_PRIMARIA"], \
                "familia detectada por la metadata del asistente"
            _mapa68 = {h["codigo"]: h for h in _inf68["hallazgos"]
                       if h["codigo"].startswith("EM")}
            assert _mapa68["EM01"]["severidad"] == "ok" \
                and _mapa68["EM02"]["severidad"] == "ok" \
                and _mapa68["EM03"]["severidad"] == "ok", \
                "programa §106-109 completo, relaciones §98-101 " \
                "trazadas y sin cruces de flujos §102"
            _rc68 = [h for h in _inf68["hallazgos"]
                     if h["codigo"].startswith("RC")]
            assert len(_rc68) == 6 and all(
                h["estado"] == "requiere calculo" for h in _rc68), \
                ("los 6 temas del documento marcados "
                 "REQUIERE_CALCULO_ESPECIALIZADO (§78/§83-85)")
            # un aula escasa a propósito: 16 m2 < 40 del cuadro
            _arq68 = _Arc68(_ctx68)
            _niv68 = _arq68.create_level("Planta Prueba", 10.0, 3.0)
            _arq68.create_space(_niv68.code, "Aula escasa", "CLASSROOM",
                                [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0),
                                 (0.0, 4.0)])
            _ctx68.commit()
            _aulas68 = [s for s in
                        _ctx68.architecture.list(
                            "SPACE", _ctx68.project.id)
                        if getattr(s, "space_type", "") == "CLASSROOM"]
            _escasa68 = next(s for s in _aulas68
                             if s.name == "Aula escasa")
            _inf_escasa68 = _ed68.validar_local(_ctx68, _escasa68.id)
            _cod68 = {h["codigo"]: h
                      for h in _inf_escasa68["hallazgos"]}
            assert _cod68["E01"]["severidad"] == "fallo" \
                and "40.00" in _cod68["E01"]["mensaje"], \
                "superficie 16.00 m2 < mínima 40.00 m2 del cuadro (§5)"
            (_ed68.texto_validacion_educacion(_inf68)).encode("cp1252")
            _ctx68.close()
        finally:
            import shutil as _sh68
            _sh68.rmtree(_tmp68, ignore_errors=True)
        checks.append("documento educacional v3.26.0: OK "
                      "(4 tipologías y 82 cuadros MIN/REC del "
                      "documento; programa paramétrico §106-109 por "
                      "capacidad con NUM_AULAS = CEIL, medidas de los "
                      "cuadros y relaciones §98-101 en el asistente; "
                      "validar_local/validar_proyecto con programa, "
                      "relaciones, flujos §102, capacidad §4/§111, "
                      "comedor REGLA_08, escaleras §45, punto de "
                      "reunión §104-105, alturas §2 y seguridad "
                      "infantil §89; HVAC, incendios, evacuación, "
                      "CCTV, acústica e instalaciones marcados "
                      "REQUIERE_CALCULO_ESPECIALIZADO)" + _nota68)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 69. Informe de validación en HTML autocontenido (v3.27.0) --------
    try:
        import tempfile as _tf69
        from exporters import informe_html as _ih69
        from domain import vivienda_specs as _vs69
        from services.context import ApplicationContext as _App69
        _nota69 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_ih69.__file__, "r", encoding="utf-8") as _fh69:
                _src69 = _fh69.read()
            assert "def informe_html" in _src69 \
                and "def guardar_informe_html" in _src69 \
                and "<!DOCTYPE html>" in _src69 \
                and "ARQ-EXP-060" in _src69, \
                "el exportador HTML con su CSS embebido y su error " \
                "amable"
        # conductual: informe REAL de vivienda -> HTML autocontenido
        _inf69 = {"edificacion": "Humo 69", "uso": "Escuela primaria",
                  "familias": ["ESCUELA_PRIMARIA"],
                  "resumen": {"ok": 1, "fallos": 1, "avisos": 0,
                              "pendientes": 0},
                  "hallazgos": [
                      {"codigo": "EM01", "severidad": "ok",
                       "mensaje": "programa completo", "estado":
                       "medido", "fuente": "doc"},
                      {"codigo": "EM07", "severidad": "fallo",
                       "mensaje": "escalera escasa", "estado":
                       "requiere calculo", "fuente": "doc"}],
                  "locales": [{"local": "Aula", "nombre":
                               "CLASSROOM", "hallazgos": []}],
                  "reglas": ["REGLA_01"], "advertencia": "aviso"}
        _html69 = _ih69.informe_html(_inf69, "Prueba 69")
        assert _html69.startswith("<!DOCTYPE html>") \
            and '<meta charset="utf-8">' in _html69 \
            and "<style>" in _html69, \
            "HTML5 con CSS embebido y UTF-8 declarado"
        assert 'href="http' not in _html69 \
            and 'src="http' not in _html69, \
            "cero recursos externos: el archivo vive solo"
        assert "EM01" in _html69 \
            and "REQUIERE_CALCULO_ESPECIALIZADO" in _html69, \
            "hallazgos con estados honestos impresos, no escondidos"
        assert "Escuela &lt;primaria&gt;" not in _html69 \
            and "Escuela primaria" in _html69, "texto escapado correcto"
        # un informe real de vivienda sobre un proyecto vacío también
        # pasa por el renderizador (hallazgos como objetos, no dicts)
        _tmp69 = _tf69.mkdtemp(prefix="check69_")
        try:
            _ctx69 = _App69().create_project(
                os.path.join(_tmp69, "check69.arqgen"), name="Check 69")
            _vreal69 = _vs69.validar_vivienda(_ctx69)
            _hreal69 = _ih69.informe_html(_vreal69,
                                          "Validación de vivienda")
            assert "Comprobaciones del edificio" in _hreal69 \
                and "VIV" in _hreal69, \
                "informe real de vivienda (hallazgos como objetos)"
            _ruta69 = _ih69.guardar_informe_html(
                os.path.join(_tmp69, "salida", "informe.html"),
                _vreal69, "Validación de vivienda")
            assert os.path.isfile(_ruta69), "el HTML se escribe a disco"
            # obstáculo: «bloqueo69» es un ARCHIVO, no una carpeta ->
            # makedirs no puede y el exportador responde ARQ-EXP-060
            with open(os.path.join(_tmp69, "bloqueo69"), "w",
                      encoding="utf-8") as _fh69b:
                _fh69b.write("no soy carpeta")
            try:
                _ih69.guardar_informe_html(
                    os.path.join(_tmp69, "bloqueo69", "y.html"),
                    _inf69, "X")
                raise AssertionError("debia fallar ARQ-EXP-060")
            except Exception as _e69:
                assert getattr(_e69, "code", "") == "ARQ-EXP-060", \
                    "error amable ARQ-EXP-060 al no poder escribir"
            _ctx69.close()
        finally:
            import shutil as _sh69
            _sh69.rmtree(_tmp69, ignore_errors=True)
        checks.append("informe HTML autocontenido v3.27.0: OK "
                      "(los informes de validación se exportan a UN "
                      "solo archivo .html con CSS embebido, cero "
                      "recursos externos y cero dependencias nuevas; "
                      "botón «Guardar HTML...» en los tres cuadros de "
                      "validación; estados honestos impresos: "
                      "(pendiente) y (REQUIERE_CALCULO_ESPECIALIZADO); "
                      "error amable ARQ-EXP-060 si la ruta no deja "
                      "escribir)" + _nota69)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 70. Presets de configuración del asistente (v3.28.0) ------------
    try:
        import tempfile as _tf70
        from core.errors import DomainError as _DE70
        from ui import presets as _pr70
        from ui.building_wizard import BuildingWizardData as _BWD70
        _nota70 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_pr70.__file__, "r", encoding="utf-8") as _fh70:
                _src70 = _fh70.read()
            assert "def guardar_preset" in _src70 \
                and "def cargar_preset" in _src70 \
                and "def preset_de_data" in _src70 \
                and "ARQ-PRE-001" in _src70 \
                and "ARQ_GEN_PRESET" in _src70, \
                "el gestor de presets con su formato versionado"
        # conductual: ciclo completo sobre una carpeta temporal
        _tmp70 = _tf70.mkdtemp(prefix="check70_")
        try:
            _car70 = os.path.join(_tmp70, "presets")
            _dat70 = _BWD70()
            _dat70.usage_type = "Escuela primaria"
            _dat70.educacion_tamano = \
                "Escuela primaria: Pequeña (60-180 alumnos)"
            _dat70.corridor_width_m = 1.4
            _dat70.installations = ["Eléctrica", "Energía solar"]
            _rut70 = _pr70.guardar_preset(
                _car70, "Escuela primaria 120",
                _pr70.preset_de_data(_dat70))
            assert os.path.isfile(_rut70), "el preset se escribe"
            _lis70 = _pr70.listar_presets(_car70)
            assert len(_lis70) == 1 \
                and _lis70[0]["uso"] == "Escuela primaria" \
                and not _lis70[0]["corrupto"], \
                "el listado muestra el preset con su uso"
            # cambia la data y restaura desde el archivo
            _dat70.usage_type = "Vivienda"
            _dat70.educacion_tamano = "(programa básico)"
            _dat70.corridor_width_m = 0.0
            _dat70.installations = []
            _doc70 = _pr70.cargar_preset(_rut70)
            assert _doc70["formato"] == "ARQ_GEN_PRESET" \
                and _doc70["version"] == 1, \
                "formato ARQ_GEN_PRESET v1"
            _av70 = _pr70.aplicar_preset_a_data(_doc70["datos"],
                                                _dat70)
            assert _av70 == [], "el preset limpio se aplica sin avisos"
            assert _dat70.usage_type == "Escuela primaria" \
                and _dat70.educacion_tamano == \
                "Escuela primaria: Pequeña (60-180 alumnos)" \
                and abs(_dat70.corridor_width_m - 1.4) < 1e-9 \
                and _dat70.installations == \
                ["Eléctrica", "Energía solar"], \
                "la configuración restaurada es idéntica"
            # valores ilegales: aviso, no ruptura
            _av70b = _pr70.aplicar_preset_a_data(
                {"usage_type": "Observatorio lunar",
                 "corridor_width_m": "no es número",
                 "installations": ["Eléctrica", "Teleportación"]},
                _dat70)
            assert len(_av70b) == 3 \
                and _dat70.usage_type == "Escuela primaria" \
                and _dat70.installations == ["Eléctrica"], \
                "valores ilegales del preset: aviso y conserva"
            # errores amables
            for _fn70, _cod70 in (
                    (lambda: _pr70.guardar_preset(
                        _car70, "  ", {"a": 1}), _pr70.COD_NOMBRE),
                    (lambda: _pr70.cargar_preset(os.path.join(
                        _car70, "no_esta.json")), _pr70.COD_AUSENTE)):
                try:
                    _fn70()
                    raise AssertionError("debía fallar " + _cod70)
                except _DE70 as _de70:
                    assert _de70.code == _cod70, _cod70
            (_pr70.resumen_preset(_doc70["datos"])).encode("cp1252")
            _pr70.eliminar_preset(_rut70)
            assert _pr70.listar_presets(_car70) == [], \
                "el preset se elimina"
        finally:
            import shutil as _sh70
            _sh70.rmtree(_tmp70, ignore_errors=True)
        checks.append("presets de configuración v3.28.0: OK "
                      "(la configuración del asistente se guarda y "
                      "carga como JSON local en «presets/» — o "
                      "ARQ_GEN_PRESETS — con formato ARQ_GEN_PRESET "
                      "v1, 43 campos de los pasos 1/4/5 y concepción "
                      "de espacios, SIN el programa: niveles, locales "
                      "y relaciones se regeneran desde el uso; "
                      "valores ilegales avisan y conservan; errores "
                      "amables ARQ-PRE-001..006; botones "
                      "Guardar/Cargar/Eliminar en el paso 1 del "
                      "asistente)" + _nota70)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 71. Comparador de variantes de planta (v3.29.0) -----------------
    try:
        from ui import variant_budget as _vb71
        from ui.building_wizard import (
            BuildingWizardData as _BWD71, LevelSpec as _LS71,
            generate_variants as _gv71, preset_rooms as _pr71,
            suggest_relations as _sr71)
        _nota71 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_vb71.__file__, "r", encoding="utf-8") as _fh71:
                _src71 = _fh71.read()
            assert "def tabla_comparacion_variantes" in _src71 \
                and "def texto_comparacion_variantes" in _src71 \
                and "def csv_comparacion_variantes" in _src71 \
                and "COLUMNAS_COMPARACION" in _src71, \
                "la matriz de comparación con su texto y su CSV"
        # conductual: variantes REALES de una vivienda del asistente
        _dat71 = _BWD71()
        _dat71.levels = [_LS71(name="Planta Baja", height_m=3.0)]
        _dat71.usage_type = "Vivienda"
        _dat71.rooms = _pr71("Vivienda", "Planta Baja")
        _dat71.relations = _sr71(_dat71)
        _var71 = _gv71(_dat71)
        assert len(_var71) >= 6, \
            "el motor entrega sus variantes para compararlas"
        _tab71 = _vb71.tabla_comparacion_variantes(_var71)
        assert len(_tab71["filas"]) == len(_var71) \
            and len(_tab71["columnas"]) == 9, \
            "una fila por variante con las 9 columnas"
        _pun71 = [int(_tab71["filas"][i - 1][4])
                  for i in _tab71["orden"]]
        assert _pun71 == sorted(_pun71, reverse=True), \
            "el orden deja arriba a la mejor puntuada"
        assert _tab71["mejores"]["puntos"], "líder por puntos"
        assert not _tab71["mejores"]["con_coste"], \
            "sin coste adjunto el comparador lo DECLARA (honradez)"
        # con costes vivos de juguete: 80 000 CUP / 100 m2 = 800
        _cos71 = _vb71.VariantCost(area_m2=100.0)
        _cos71.categories = {"Muros": 50_000.0, "Estructura": 30_000.0}
        _var71[0].cost = _cos71
        _tab71b = _vb71.tabla_comparacion_variantes(_var71)
        assert _tab71b["filas"][0][6] == "80 000" \
            and _tab71b["filas"][0][7] == "800" \
            and _tab71b["mejores"]["con_coste"], \
            "coste y coste/m2 formateados desde el takeoff vivo"
        (_vb71.texto_comparacion_variantes(_var71)).encode("cp1252")
        _csv71 = _vb71.csv_comparacion_variantes(_var71)
        assert _csv71.count("\r\n") == len(_var71) + 1 \
            and _csv71.split("\r\n")[0].startswith(
                "#;Variante;Esquema"), \
            "CSV con «;» y una fila por variante más cabecera"
        checks.append("comparador de variantes v3.29.0: OK "
                      "(matriz N variantes x 9 columnas: puntos, "
                      "área, coste PRECONS vivo, coste/m2, avisos y "
                      "cabe-en-lote, ordenada por puntuación con el "
                      "líder por coste/m2; texto cp1252 y CSV «;» "
                      "utf-8-sig; botón «Comparar variantes» en el "
                      "paso 6 del asistente junto al generador; "
                      "sin coste adjunto lo declara en vez de "
                      "inventar)" + _nota71)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 72. Servicios de vivienda: piscina §45, acústica §46 y domótica
    #     §39 (v3.30.0) ------------------------------------------------
    try:
        import tempfile as _tf72
        from ui.building_wizard import (BuildingWizardData as _BWD72,
                                        apply_usage_program as _aup72,
                                        apply_plan as _ap72)
        from domain import vivienda_servicios as _vs72
        _nota72 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_vs72.__file__, "r", encoding="utf-8") as _fh72:
                _src72 = _fh72.read()
            assert "def calcular_piscina" in _src72 \
                and "def analisis_acustico" in _src72 \
                and "def plan_domotico" in _src72 \
                and "ARQ-PIS-001" in _src72 \
                and "_vano_perimetral" in _src72, \
                "los tres motores de servicios con su geometría"
        # conductual: piscina 8x4 con profundidades 1.0-2.0 (a mano)
        _inf72 = _vs72.calcular_piscina(8.0, 4.0, 1.0, 2.0)
        assert abs(_inf72["vaso"]["volumen_m3"] - 48.0) < 1e-9 \
            and abs(_inf72["filtracion"]["caudal_m3_h"] - 8.0) < 1e-6 \
            and abs(_inf72["filtracion"]["bomba_kw"] - 0.396) < 0.01 \
            and abs(_inf72["total_equipos_cup"] - 209800.0) < 1e-9, \
            "piscina 8x4: 48 m3, 8 m3/h, bomba 0.40 kW y 209 800 CUP"
        (_vs72.texto_piscina(_inf72)).encode("cp1252")
        # acústica y domótica sobre una vivienda generada
        _tmp72 = _tf72.mkdtemp(prefix="check72_")
        try:
            _ctx72 = ApplicationContext().create_project(
                os.path.join(_tmp72, "check72.arqgen"),
                name="Check 72")
            _dat72 = _BWD72()
            _dat72.name = "Casa del check 72"
            _dat72.usage_type = "Vivienda"
            _dat72.vivienda_tipologia = "Unifamiliar aislada"
            _aup72(_dat72)
            assert _ap72(_dat72, _ctx72), "vivienda generada"
            _acu72 = _vs72.analisis_acustico(_ctx72)
            assert len(_acu72["hallazgos"]) == 7 \
                and _acu72["pares"] \
                and _acu72["hallazgos"][6]["estado"] == \
                "requiere calculo", \
                "acústica §46: ACU001-007 con pares medidos"
            assert all(p["espesor_medido_mm"] > 0
                       and p["material"] and p["rw_db"]
                       for p in _acu72["pares"]), \
                "espesor medido y solución de referencia por par"
            (_vs72.texto_acustica(_acu72)).encode("cp1252")
            from exporters.informe_html import informe_html as _ih72f
            assert "Soluciones de referencia del §46" in \
                _ih72f(_acu72, "Check 72"), \
                "tablas genéricas renderizadas en el HTML"
            _dom72 = _vs72.plan_domotico(_ctx72)
            assert len(_dom72["sistemas"]) == 8 \
                and _dom72["hallazgos"][1]["estado"] == \
                "requiere calculo" \
                and _dom72["total_equipos_cup"] == round(sum(
                    f["subtotal_cup"] for f in _dom72["filas"]), 2), \
                "domótica §39: 8 sistemas con total consistente"
            (_vs72.texto_domotica(_dom72)).encode("cp1252")
            _ctx72.close()
        finally:
            import shutil as _sh72
            _sh72.rmtree(_tmp72, ignore_errors=True)
        checks.append("servicios de vivienda v3.30.0: OK "
                      "(piscina §45 como SISTEMA INDEPENDIENTE: "
                      "volumen, renovación, caudal, bomba por "
                      "rendimiento, skimmers, impulsión, focos, "
                      "checklist de seguridad y equipos en CUP; "
                      "acústica §46: fuentes contra dormitorios con "
                      "muros compartidos MEDIDOS por solape "
                      "colineal, vano perimetral por sub-segmento, "
                      "soluciones de referencia con R_w, doble "
                      "tabique, cubierta y vidrio acústico; "
                      "domótica §39: 8 sistemas con 16 conteos "
                      "sobre el modelo, monitor doble con solar FV "
                      "y RED/PANEL/ALIMENTACION como diseño; "
                      "errores amables ARQ-PIS-001/002 y tablas "
                      "genéricas en el informe HTML)" + _nota72)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 73. P2: DXF R12 ASCII + coste ligado al check (v3.31.0) ----------
    try:
        import tempfile as _tf73
        from services.architecture_service import \
            ArchitectureService as _Arq73
        from exporters import dxf_exporter as _dxm73
        from exporters.dxf_exporter import DXFExporter as _DXF73
        from services import coste_informe as _ci73
        _nota73 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_dxm73.__file__, "r", encoding="utf-8") as _fh73:
                _src73 = _fh73.read()
            assert 'ezdxf.new("R12"' in _src73 \
                and "def _polilinea" in _src73, \
                "el exportador DXF con rama R12 propia"
            with open(_ci73.__file__, "r", encoding="utf-8") as _fh73b:
                _src73b = _fh73b.read()
            assert "def instantanea_coste" in _src73b \
                and "def adjuntar_coste" in _src73b \
                and "latest()" in _src73b, \
                "la instantánea de coste con su honradez de sólo lectura"
        # conductual: proyecto con un local -> R12 y R2010
        _tmp73 = _tf73.mkdtemp(prefix="check73_")
        try:
            _ctx73 = ApplicationContext().create_project(
                os.path.join(_tmp73, "check73.arqgen"),
                name="Check 73")
            _arq73 = _Arq73(_ctx73)
            _niv73 = _arq73.create_level("PB", 0.0, 3.0)
            for _a73, _b73 in (((0.0, 0.0), (6.0, 0.0)),
                                ((6.0, 0.0), (6.0, 4.0)),
                                ((6.0, 4.0), (0.0, 4.0)),
                                ((0.0, 4.0), (0.0, 0.0))):
                _arq73.create_wall(_niv73.code, _a73, _b73, 0.2)
            _arq73.create_space(_niv73.code, "Sala 73", "LIVING_ROOM",
                                [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0),
                                 (0.0, 4.0)])
            _r12_73 = _DXF73().export(_ctx73, os.path.join(
                _tmp73, "r12.dxf"), version="R12")
            with open(_r12_73, "r", encoding="cp437",
                      errors="replace") as _fh73c:
                _txt73 = _fh73c.read()
            assert "AC1009" in _txt73 and "LINE" in _txt73 \
                and "LWPOLYLINE" not in _txt73, \
                "R12 ASCII: cabecera AC1009 y entidades clásicas"
            _r20_73 = _DXF73().export(_ctx73, os.path.join(
                _tmp73, "r2010.dxf"))
            with open(_r20_73, "r", encoding="cp437",
                      errors="replace") as _fh73d:
                assert "AC1024" in _fh73d.read(), \
                    "el R2010 queda intacto"
            # coste ligado al check: sin presupuesto NO se inventa
            assert _ci73.instantanea_coste(_ctx73) is None, \
                "sin presupuesto la instantánea es None (no crea)"
            from services.precons_budget_service import \
                PreconsBudgetService as _PBS73
            _svc73 = _PBS73(_ctx73)
            _svc73.load_ruleset()
            _svc73.add_item("011111", 500)
            _cos73 = _ci73.instantanea_coste(_ctx73)
            assert _cos73 is not None and _cos73["renglones"] == 1 \
                and abs(_cos73["directo"] - 13405.0) < 0.01, \
                "instantánea con renglón oficial 011111 x 500"
            from exporters.informe_html import informe_html as _ih73f
            assert "Coste del proyecto" in _ih73f(
                {"hallazgos": [], "coste": _cos73}, "Check 73"), \
                "el informe HTML renderiza la sección de coste"
            (_ci73.texto_bloque_coste(_cos73)).encode("cp1252")
            _ctx73.close()
        finally:
            import shutil as _sh73
            _sh73.rmtree(_tmp73, ignore_errors=True)
        checks.append("DXF R12 y coste ligado al check v3.31.0: OK "
                      "(exporter con version='R12': AC1009, "
                      "LINE/ARC/TEXT clásicos sin LWPOLYLINE, todo al "
                      "modelspace con un bloque por nivel, y el R2010 "
                      "intacto; opción --r12 en la CLI y menú "
                      "«Exportar DXF R12 (compatibilidad)...» en "
                      "Archivo; los tres informes de validación llevan "
                      "la instantánea SOLO LECTURA del presupuesto "
                      "PRECONS activo (latest(), nunca ensure_active): "
                      "directo, transporte, indirectos, beneficio, "
                      "total y coste/m2 en el cuadro y en el HTML, y "
                      "sin presupuesto NO se inventa nada)" + _nota73)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 74. P3: multiplicadores de niveles / planta tipo (v3.32.0) ------
    try:
        from ui import building_wizard as _bw74
        from ui.building_wizard import (
            BuildingWizardData as _BWD74, LevelSpec as _LS74,
            RoomSpec as _RS74)
        _nota74 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_bw74.__file__, "r", encoding="utf-8") as _fh74:
                _src74 = _fh74.read()
            assert "def repeat_de" in _src74 \
                and "def niveles_expandidos" in _src74 \
                and "def expandir_datos" in _src74 \
                and "REPEAT_MAX = 50" in _src74 \
                and "repeat: int = 1" in _src74, \
                "el multiplicador de niveles con su expansión sana"
            with open(os.path.join(os.path.dirname(_bw74.__file__),
                                   "app_window.py"),
                      "r", encoding="utf-8") as _fh74b:
                _src74b = _fh74b.read()
            assert "× Repetir seleccionado..." in _src74b \
                and "level_repeat_entry" in _src74b, \
                "el paso 2 con la columna Repetir y su botón"
        # identidad: sin multiplicadores, EL MISMO objeto
        _ident74 = _BWD74()
        assert _bw74.expandir_datos(_ident74) is _ident74, \
            "con todos los x1 la expansión es identidad"
        # planta tipo x3: niveles, locales, cotas y plan coherentes
        _data74 = _BWD74()
        _data74.levels = [_LS74(name="Planta Baja", height_m=3.0),
                          _LS74(name="Planta Tipo", height_m=3.0,
                                repeat=3)]
        _data74.rooms = [
            _RS74(name="Sala PB", space_type="LIVING_ROOM",
                  width_m=4.0, depth_m=4.0, level_ref="Planta Baja"),
            _RS74(name="Aula 1", space_type="CLASSROOM",
                  width_m=6.0, depth_m=6.0, level_ref="Planta Tipo")]
        _data74.corridor_enabled = False
        assert [lv.name for lv in _bw74.niveles_expandidos(_data74)] == \
            ["Planta Baja", "Planta Tipo", "Planta Tipo 2",
             "Planta Tipo 3"], "copias con nombres únicos"
        assert _bw74.level_elevations(_data74) == \
            [0.0, 3.0, 6.0, 9.0], \
            "la planta tipo x3 empuja las cotas de lo que sigue"
        _plan74, _lay74, _av74 = _bw74.build_plan(_data74)
        assert _plan74[0][1]["floors"] == 4, \
            "el edificio declara los 4 niveles expandidos"
        _nombres74 = [e[1]["name"] for e in _plan74 if e[0] == "LEVEL"]
        assert _nombres74 == ["Planta Baja", "Planta Tipo",
                              "Planta Tipo 2", "Planta Tipo 3"], \
            "el plan crea las 4 copias en orden"
        _aulas74 = sum(1 for e in _plan74
                       if e[0] == "SPACE"
                       and e[1]["name"] == "Aula 1")
        assert _aulas74 == 3, \
            "el local de la planta tipo se duplica en cada copia"
        # variante sobre el edificio entero
        _var74 = _bw74.generate_variants(_data74)
        assert _var74 and len(_var74[0].layouts) == 4, \
            "las variantes se puntúan sobre el edificio entero"
        checks.append("multiplicadores de niveles / planta tipo "
                      "v3.32.0: OK (LevelSpec.repeat con expansión "
                      "sana 1..50, copias con nombres únicos «Planta "
                      "Tipo 2», «Planta Tipo 3», locales duplicados "
                      "por copia y relaciones globales intactas, "
                      "cotas que se recorren solas, build_plan y "
                      "generate_variants expanden solos, identidad "
                      "total con x1; paso 2 con columna Repetir, "
                      "entrada y «× Repetir seleccionado...», y el "
                      "resumen de niveles/altura total)" + _nota74)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 75. Dibujo CAD + asistente de servicios (v3.33.0) ----------------
    try:
        from ui import dibujo_cad as _dib75
        from domain import servicios_engine as _eng75
        from domain.servicios_specs import resumen_catalogo as _rc75
        _nota75 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_dib75.__file__, "r", encoding="utf-8") as _fh75:
                _src75 = _fh75.read()
            assert "def dibujar_muro" in _src75 \
                and "def dibujar_espacio" in _src75 \
                and "def dibujar_zona" in _src75 \
                and "def dibujar_vano" in _src75 \
                and "HERRAMIENTAS_DIBUJO" in _src75, \
                "las cinco herramientas de dibujo con sus reglas"
            _dir_ui75 = os.path.dirname(_dib75.__file__)
            with open(os.path.join(_dir_ui75, "app_window.py"),
                      "r", encoding="utf-8") as _fh75b:
                _src75b = _fh75b.read()
            assert "Panel de dibujo" in _src75b \
                and "open_servicios_dialog" in _src75b \
                and "_cad_click_dibujo" in _src75b \
                and "_servicios_aplicar" in _src75b, \
                "la paleta de dibujo y el asistente en la ventana"
            with open(os.path.join(os.path.dirname(_dir_ui75), "domain",
                                   "servicios_specs.py"),
                      "r", encoding="utf-8") as _fh75c:
                _src75c = _fh75c.read()
            assert "ARQ_GEN_SERVICIOS" in _src75c \
                and "def cargar_servicios" in _src75c, \
                "el catálogo versionado de servicios"
        # conductual: catálogo sano (6 servicios, 40+ locales)
        _cat75 = _rc75()
        assert _cat75["servicios"] >= 6 and _cat75["locales"] >= 40 \
            and _cat75["criticos"] >= 5, \
            f"catálogo completo de servicios: {_cat75}"
        # conductual: programa de anatomía patológica dimensionado
        _prog75 = _eng75.programa_servicio("ANATOMIA_PATOLOGICA",
                                           {"necropsias_dia": 3,
                                            "piezas_dia": 16,
                                            "personal": 6,
                                            "con_archivo": True})
        _nombres75 = [r["nombre"] for r in _prog75["renglones"]]
        assert "Sala de necropsias" in _nombres75 \
            and "Laboratorio de histotecnologia" in _nombres75 \
            and _prog75["totales"]["locales"] == 17, \
            "el programa trae la cadena completa del servicio " \
            "(con el filtro sanitario v3.42.0)"
        assert any(r["critico"] for r in _prog75["renglones"]), \
            "los locales críticos del servicio quedan marcados"
        assert _prog75["validacion"] and \
            any(c["codigo"] == "AREAS" for c in _prog75["validacion"]), \
            "la validación funcional del programa"
        # conductual: dibujo headless sobre proyecto temporal
        from services.context import ApplicationContext as _Ctx75
        from services.architecture_service import ArchitectureService \
            as _Arch75
        _app75 = _Ctx75()
        _ctx75 = _app75.create_project(
            os.path.join(tmp, "selftest_dibujo.arqgen"), name="Selftest")
        try:
            _arch75 = _Arch75(_ctx75)
            _arch75.create_level("PB", 0.0, 3.0)
            _m75 = _dib75.dibujar_muro(_ctx75, "PB", (0, 0), (8, 0))
            assert _m75["creados"], "el muro dibujado nace real"
            _e75 = _dib75.dibujar_espacio(_ctx75, "PB", (0, 0), (4, 3),
                                          nombre="Sala", uso="OFFICE")
            assert _e75["datos"]["area_m2"] == 12.0, \
                "el espacio dibujado nace con su área"
            _v75 = _dib75.dibujar_vano(_ctx75, "DOOR",
                                       _m75["creados"][0], (2.0, 0.0))
            assert _v75["creados"], "la puerta nace sobre el muro"
            _z75 = _dib75.dibujar_zona(_ctx75, "Zona", (0, 0), (5, 4),
                                       nivel_ref="PB")
            assert _z75["datos"]["asignados"], \
                "la zona asigna los locales dibujados dentro"
        finally:
            _ctx75.close()
        checks.append("dibujo CAD y asistente de servicios v3.33.0: "
                      "OK (muros, espacios, zonas, puertas y ventanas "
                      "a dos clics por los caminos oficiales con las "
                      "reglas del DNA avisando; paleta con sección "
                      "Dibujar y configuración de dimensiones; "
                      "catálogo versionado de 6 servicios con 40+ "
                      "locales y parámetros dinámicos, programa "
                      "dimensionado con validación funcional, y "
                      "aplicación al nivel con zona, pasillo y "
                      "relaciones)" + _nota75)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 76 · DESDE DIBUJO v3.34.0: generación inversa (contorno ->
    # edificación o servicio): inferencia de forma y medidas, ajuste
    # con crecimiento en altura y escalera (Blondel) y aplicación real.
    try:
        from domain import desde_dibujo as _dd76
        _nota76 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_dd76.__file__, "r", encoding="utf-8") as _fh76:
                _src76 = _fh76.read()
            assert "def inferir" in _src76 \
                and "def ajustar" in _src76 \
                and "def aplicar_plan" in _src76 \
                and "def contornos_dxf" in _src76 \
                and "def programa_edificacion" in _src76 \
                and "def caja_escalera" in _src76, \
                "el motor desde dibujo completo"
            _dir_ui76 = os.path.dirname(os.path.dirname(_dd76.__file__)) \
                + "/ui"
            with open(os.path.join(_dir_ui76, "app_window.py"),
                      "r", encoding="utf-8") as _fh76b:
                _src76b = _fh76b.read()
            assert "open_desde_dibujo_dialog" in _src76b \
                and "_dd_aplicar" in _src76b, \
                "el asistente desde dibujo en la ventana"
        # conductual: inferencia del contorno
        _f76 = _dd76.inferir([(0, 0), (12, 0), (12, 8), (0, 8)])
        assert _f76["forma"] == "rectangulo" \
            and abs(_f76["area_m2"] - 96.0) < 1e-6 \
            and _f76["alineado"], \
            "la forma y las medidas del dibujo se infieren"
        # conductual: no cabe -> crecimiento en altura con escalera
        _prog76 = _dd76.programa_edificacion(
            [{"space_type": "OFFICE", "cantidad": 7, "area_m2": 20.0}])
        _an76 = _dd76.ajustar(_prog76,
                              [(0, 0), (12, 0), (12, 9), (0, 9)])
        assert _an76["niveles"] >= 2 and _an76["con_escalera"] \
            and _an76["escalera"] is not None \
            and "Blondel" in _an76["escalera"]["descripcion"], \
            f"crecimiento en altura sugerido: {_an76['niveles']} niveles"
        # conductual: aplicación real en proyecto temporal
        from services.context import ApplicationContext as _Ctx76
        from services.architecture_service import ArchitectureService \
            as _Arch76
        _app76 = _Ctx76()
        _ctx76 = _app76.create_project(
            os.path.join(tmp, "selftest_desde_dibujo.arqgen"),
            name="Selftest")
        try:
            _r76 = _dd76.aplicar_plan(
                _ctx76, _an76, {"nombre_edificio": "Anexo Selftest"})
            assert len(_r76["niveles"]) == _an76["niveles"], \
                "un nivel del proyecto por cada planta del reparto"
            _esp76 = _ctx76.architecture.list(
                "SPACE", _ctx76.project.id)
            assert len(_esp76) == _an76["niveles"] * 2 + 7, \
                "pasillo, locales y escalera reales en cada nivel"
            assert _r76["relaciones"] == _an76["niveles"] + 7, \
                "relaciones adjacent_to con el pasillo"
            _ctx76.commit()
        finally:
            _ctx76.close()
        checks.append("desde dibujo, generación inversa v3.34.0: "
                      "OK (contorno por espacio dibujado, rectángulo "
                      "o polilínea cerrada de DXF; inferencia de forma "
                      "y medidas; programa por servicio del catálogo "
                      "o usos del DNA; verificación honesta de si los "
                      "locales entran en el área; crecimiento en "
                      "altura en niveles apilados con el recinto de "
                      "la escalera según Blondel; generación de "
                      "entidades reales por los caminos oficiales)"
                      + _nota76)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 77. SERVICIOS MEDICOS v3.35.0: catálogo v2.0 + documentos -------
    try:
        from domain import servicios_engine as _sm77
        from domain import servicios_specs as _sp77
        _nota77 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_sp77.__file__, "r", encoding="utf-8") as _fh77:
                _src77 = _fh77.read()
            assert "ETIQUETAS_INSTALACIONES" in _src77 \
                and "def reglas_generacion" in _src77 \
                and "NIVELES_CRITICIDAD" in _src77, \
                "el catálogo v2.0 con criticidad e instalaciones"
            with open(_sm77.__file__, "r", encoding="utf-8") as _fh77b:
                _src77b = _fh77b.read()
            assert "def texto_ficha_local" in _src77b \
                and "def texto_matriz_instalaciones" in _src77b \
                and "def texto_relaciones_servicios" in _src77b \
                and "def texto_flujos" in _src77b \
                and "def texto_reglas_generacion" in _src77b, \
                "los cinco documentos del servicio en el motor"
            _dir77 = os.path.dirname(os.path.dirname(_sp77.__file__))
            with open(os.path.join(_dir77, "ui", "app_window.py"),
                      "r", encoding="utf-8") as _fh77c:
                _src77c = _fh77c.read()
            assert "_servicios_muestra_doc" in _src77c, \
                "el selector de documentos en el asistente"
        assert _sp77.version_catalogo() == "3.0", \
            "catálogo v3.0 (universal por sectores desde v3.36.0)"
        _cat77 = _sp77.resumen_catalogo()
        assert _cat77["servicios"] >= 11 and _cat77["locales"] >= 140 \
            and _cat77["reglas"] == 20, \
            f"catálogo de servicios médicos completo: {_cat77}"
        _urg77 = _sm77.programa_servicio("URGENCIAS")
        assert _urg77["totales"]["locales"] >= 28 \
            and _urg77["totales"].get("grupos"), \
            "urgencias con grupos funcionales y subtotales"
        _ficha77 = _sm77.texto_ficha_local("ANATOMIA_PATOLOGICA",
                                           "SALA_CORTE")
        assert "SUPERFICIE_MIN" in _ficha77 \
            and "OBLIGATORIA" in _ficha77 and "PROHIBIDA" in _ficha77, \
            "ficha de local de la sección 30"
        _matriz77 = _sm77.texto_matriz_instalaciones(
            "TOMOGRAFIA_COMPUTARIZADA")
        assert "Radioproteccion" in _matriz77, \
            "matriz de instalaciones de la sección 22"
        checks.append("servicios médicos v3.35.0: OK (catálogo v2.0 "
                      "con morgue, tomografía, UCI, cuidados "
                      "intermedios y urgencias; anatomía patológica "
                      "enriquecida a 17 locales con el filtro "
                      "sanitario v3.42.0; grupos con "
                      "subtotales; criticidad por niveles; puertas y "
                      "circulación del catálogo; ficha de local, "
                      "matriz de instalaciones, relaciones entre "
                      "servicios, flujos y 20 reglas de generación)"
                      + _nota77)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 78. CATALOGO UNIVERSAL v3.36.0: 34 servicios por sectores -------
    try:
        from domain import desde_dibujo as _dd78
        from domain import servicios_engine as _sm78
        from domain import servicios_specs as _sp78
        _nota78 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_sp78.__file__, "r", encoding="utf-8") as _fh78:
                _src78 = _fh78.read()
            assert "ETIQUETAS_SECTORES" in _src78 \
                and "def servicios_por_sector" in _src78, \
                "el catálogo universal con sectores en specs"
            with open(_dd78.__file__, "r", encoding="utf-8") as _fh78b:
                _src78b = _fh78b.read()
            assert "def explorar_catalogo" in _src78b \
                and "def texto_exploracion" in _src78b \
                and "def _es_hall" in _src78b, \
                "el explorador del catálogo y los recintos-nave"
            _dir78 = os.path.dirname(os.path.dirname(_sp78.__file__))
            with open(os.path.join(_dir78, "ui", "app_window.py"),
                      "r", encoding="utf-8") as _fh78c:
                _src78c = _fh78c.read()
            assert "_servicios_aplica_filtro" in _src78c \
                and "_dd_explorar" in _src78c, \
                "el filtro de sector y el explorador en la GUI"
        _cat78 = _sp78.resumen_catalogo()
        assert _cat78["servicios"] >= 34 and _cat78["sectores"] == 8 \
            and _cat78["locales"] >= 400, \
            f"catálogo universal completo: {_cat78}"
        _grupos78 = dict(_sp78.servicios_por_sector())
        assert "Salud" in _grupos78 and len(_grupos78["Salud"]) >= 23 \
            and "Educación" in _grupos78 \
            and "Comercio y hostelería" in _grupos78, \
            "sectores del catálogo agrupados y ordenados"
        _res78 = _dd78.explorar_catalogo(
            [(0, 0), (60, 0), (60, 30), (0, 30)])
        _cod78 = {r["codigo"]: r for r in _res78}
        assert len(_res78) >= 34 \
            and _cod78["FARMACIA"]["cabe_un_nivel"] \
            and _cod78["ALMACEN_LOGISTICO"].get("error") \
                == "ARQ-DDI-003", \
            "explorador: el contorno se prueba contra todo el catálogo"
        _tx78 = _dd78.texto_exploracion(_res78, 1800.0)
        _tx78.encode("cp1252")
        assert "CABE EN 1 NIVEL" in _tx78 and "NO ENTRA" in _tx78, \
            "texto del explorador cp1252"
        _sm78.programa_servicio("QUIROFANOS")
        checks.append("catálogo universal v3.36.0: OK (34 servicios "
                      "en 8 sectores con filtro por sector en ambos "
                      "asistentes; 12 servicios de salud nuevos y 11 "
                      "de otros usos: educación, administración, "
                      "comercio y hostelería, deportivo, cultural, "
                      "residencial asistido y logística; explorador "
                      "que prueba el contorno contra todo el catálogo "
                      "en el flujo desde dibujo, con recintos-nave "
                      "para locales de superficie grande)"
                      + _nota78)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 79. DXF REAL v3.37.0: unidades $INSUNITS, cierre geométrico y
    #     desde dibujo -> servicio con la estructura del plano real --
    try:
        import importers.dxf_reader as _dr79
        from domain import desde_dibujo as _dd79
        _nota79 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_dr79.__file__, "r", encoding="utf-8") as _fh79:
                _src79 = _fh79.read()
            assert "UNIDADES_DXF" in _src79 \
                and "def escala_unidades_dxf" in _src79 \
                and "def _cierre_geometrico" in _src79, \
                "unidades y cierre geométrico en el lector DXF"
            with open(_dd79.__file__, "r", encoding="utf-8") as _fh79b:
                _src79b = _fh79b.read()
            assert "def _hueco_cierre" in _src79b \
                and "cerrada_auto" in _src79b \
                and "escala_unidades_dxf" in _src79b, \
                "cierre automático y escala de unidades en contornos_dxf"
            _dir79 = os.path.dirname(os.path.dirname(_dr79.__file__))
            with open(os.path.join(_dir79, "ui", "app_window.py"),
                      "r", encoding="utf-8") as _fh79c:
                _src79c = _fh79c.read()
            assert "_dd_refresca_contornos" in _src79c, \
                "el combobox de contornos con marca de cierre automático"
        # conductual: réplica de la estructura real de «AP Y MORGUE.dxf»
        # (polilínea abierta de 9 vértices con el primero repetido al
        # final, capa MURO, 2 MTEXT vacíos y $INSUNITS=4 milímetros)
        import ezdxf as _ez79
        _tmp79 = os.path.join(
            tempfile.gettempdir(), f"arq_selftest79_{os.getpid()}.dxf")
        _doc79 = _ez79.new("R2013")
        _doc79.header["$INSUNITS"] = 4
        _doc79.layers.add(name="A-TEXTO", color=7)
        _doc79.layers.add(name="MURO", color=3)
        _msp79 = _doc79.modelspace()
        _msp79.add_lwpolyline(
            [(178.84, 3616.82), (178.84, 15006.94),
             (6828.84, 15006.94), (6828.84, 8176.82),
             (17680.98, 8176.82), (17680.98, 36.82),
             (3803.84, 36.82), (3803.84, 3616.82),
             (178.84, 3616.82)], format="xy",
            dxfattribs={"layer": "MURO"})
        for _i79 in range(2):
            _msp79.add_mtext("", dxfattribs={"layer": "A-TEXTO"})
        _doc79.saveas(_tmp79)
        try:
            _rep79 = _dr79.DxfImporter().preview(_tmp79)
            assert _rep79["counts"]["walls"] == 8 \
                and _rep79["counts"]["textos_vacios"] == 2 \
                and _rep79["unidades"]["escala"] == 0.001, \
                f"preview del plano real: {_rep79['counts']}"
            _cs79 = _dd79.contornos_dxf(_tmp79)
            assert len(_cs79) == 1 \
                and _cs79[0]["forma"] == "ortogonal" \
                and abs(_cs79[0]["area_m2"] - 174.91) < 0.01, \
                "contorno del plano real: 174.91 m2 ortogonal, en metros"
            _res79 = _dd79.explorar_catalogo(_cs79[0]["puntos"])
            _cod79 = {r["codigo"]: r for r in _res79}
            assert len(_res79) >= 34 \
                and _cod79["FARMACIA"]["cabe_un_nivel"] \
                and _cod79["MORGUE"]["niveles"] == 3 \
                and _cod79["ALMACEN_LOGISTICO"].get("error") \
                    == "ARQ-DDI-003", \
                "desde el plano real: FARMACIA cabe, MORGUE crece a 3 " \
                "(v3.42.0: pasillo servido en cada nivel)"
            _dd79.texto_exploracion(_res79, 174.91).encode("cp1252")
        finally:
            try:
                os.remove(_tmp79)
            except OSError:  # noqa: BLE001 — cosmético
                pass
        checks.append("DXF real v3.37.0: OK (el lector del importador "
                      "escala $INSUNITS a metros, acepta el cierre "
                      "geométrico de las polilíneas del CAD, descompone "
                      "el contorno de planta de la capa de muros en "
                      "segmentos y avisa de los textos vacíos; el "
                      "asistente desde dibujo enumera el contorno real "
                      "de 174.91 m2, lo prueba contra los 34 servicios "
                      "y propone el crecimiento en altura con escalera)"
                      + _nota79)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 80. DIBUJO Y NAVEGACIÓN CLÁSICA v3.38.0: gramática de coordenadas
    #     por teclado, línea de comandos, pila de vistas, rejilla
    #     anidada adaptativa y la familia de referencias clásica --
    try:
        import math as _math80
        import ui.coords_entrada as _ce80
        import ui.linea_comandos as _lc80
        import ui.navegacion as _nv80
        import ui.cursor_acad as _ca80
        import ui.keymap as _km80
        _nota80 = "" if not getattr(sys, "frozen", False) \
            else " (verificación de fuente omitida: ejecutable)"
        if not getattr(sys, "frozen", False):
            with open(_ce80.__file__, "r", encoding="utf-8") as _fh80:
                _src80 = _fh80.read()
            assert "def parse_punto" in _src80 \
                and "def evaluar_expresion" in _src80 \
                and "def texto_dinamico" in _src80, \
                "gramática de coordenadas y expresiones seguras"
            with open(_lc80.__file__, "r", encoding="utf-8") as _fh80b:
                _src80b = _fh80b.read()
            assert "class LineaComandos" in _src80b \
                and "def interpretar" in _src80b \
                and "def completar" in _src80b, \
                "línea de comandos con historial e interpretación"
            with open(_nv80.__file__, "r", encoding="utf-8") as _fh80c:
                _src80c = _fh80c.read()
            assert "class PilaVistas" in _src80c \
                and "def rejilla_adaptativa" in _src80c \
                and "ENCUADRE_VACIO" in _src80c, \
                "pila de vistas, rejilla anidada y encuadre honesto"
            with open(_ca80.__file__, "r", encoding="utf-8") as _fh80d:
                _src80d = _fh80d.read()
            assert "interseccion" in _src80d \
                and "def fijacion_perpendicular" in _src80d \
                and "MARCAS_ACTIVAS_DEF" in _src80d, \
                "familia de referencias clásica con precedencia"
        # conductual: la gramática completa del punto tecleado
        _p80 = _ce80.parse_punto("@10,5", (100.0, 100.0))
        assert _p80 == ((110.0, 105.0), "relativo"), "relativo @10,5"
        _p80b = _ce80.parse_punto("@10<45", (0.0, 0.0))
        assert abs(_p80b[0][0] - _math80.sqrt(50)) < 1e-9 \
            and _p80b[1] == "polar_relativo", "polar relativo @10<45"
        _p80c = _ce80.parse_punto("25", (0.0, 0.0), (50.0, 0.0))
        assert _p80c == ((25.0, 0.0), "distancia_directa"), \
            "distancia directa hacia el cursor"
        assert abs(_ce80.evaluar_expresion("=2*3.5+0.2") - 7.2) < 1e-9, \
            "expresión segura =2*3.5+0.2"
        _ce80.texto_dinamico((0.0, 0.0), (3.0, 3.0)).encode("cp1252")
        # línea de comandos: alias, coordenada, expresión, historial
        _cmd80 = _lc80.LineaComandos({"mu": "dib_muro",
                                      "zp": "zoom_anterior"})
        assert _cmd80.interpretar("mu")["accion"] == "dib_muro", \
            "alias MU en la línea de comandos"
        assert _cmd80.interpretar("10,5")["punto"] == (10.0, 5.0), \
            "coordenada absoluta en la línea"
        assert abs(_cmd80.interpretar("=2*3")["valor"] - 6.0) < 1e-9, \
            "expresión en la línea de comandos"
        _cmd80.push("a")
        _cmd80.push("a")
        assert len(_cmd80.historial) == 2, "historial dedupe adyacente"
        # pila de vistas acotada a 32 y rejilla anidada adaptativa
        _pila80 = _nv80.PilaVistas()
        for _i80 in range(40):
            _pila80.push(float(_i80), 0.0, 1.0)
        assert len(_pila80) == 32 \
            and _pila80.peek() == (39.0, 0.0, 1.0), \
            "pila de vistas acotada a 32 para el zoom anterior"
        _rj80 = _nv80.rejilla_adaptativa(0.0, 0.0, 4.0, 800.0, 600.0)
        assert _rj80["nivel"] == 2 and _rj80["paso"] == 25.0, \
            "rejilla anidada: al alejar sube de nivel (x5)"
        assert _nv80.encuadre_de(None) == (-50.0, -50.0, 50.0, 50.0), \
            "encuadre honesto del lienzo vacío"
        # referencias: la intersección gana al pie más cercano
        class _Muro80:
            start = (0.0, 0.0)
            end = (10.0, 0.0)
        class _Muro80b:
            start = (5.0, -5.0)
            end = (5.0, 5.0)
        _g80 = _ca80.mejor_fijacion([_Muro80(), _Muro80b()],
                                    (5.05, 0.05), 0.5)
        assert _g80 == ((5.0, 0.0), "interseccion"), \
            "osnap de intersección con precedencia clásica"
        assert "extremo" in _ca80.MARCAS_ACTIVAS_DEF \
            and "mas_cercano" not in _ca80.MARCAS_ACTIVAS_DEF, \
            "los modos magnéticos de opt-in no vienen encendidos"
        # teclado: dibujo y navegación clásica
        assert _km80.ALIAS_COMANDOS["mu"] == "dib_muro" \
            and _km80.ALIAS_COMANDOS["ve"] == "dib_ventana" \
            and _km80.ALIAS_COMANDOS["zp"] == "zoom_anterior" \
            and _km80.TECLA_ACCION.get("f2") == "historial_comandos" \
            and "din" in _km80.ESTADO_DEFECTO, \
            "aliases de dibujo/navegación, F2 historial y F12 DYN"
        checks.append("dibujo y navegación clásica v3.38.0: OK "
                      "(gramática de coordenadas 10,5 / @10,5 / @10<45 / "
                      "25 y expresiones seguras por AST; línea de "
                      "comandos con historial, autocompletado y Enter "
                      "vacío que repite; pila de vistas de 32 para el "
                      "zoom anterior, rejilla anidada adaptativa con "
                      "banda antiflip y encuadre honesto del lienzo "
                      "vacío; referencias extremo/intersección/medio/"
                      "centro con precedencia; aliases MU/ES/ZO/PU/VE y "
                      "Z/ZE/ZP/QC, F2 historial y F12 pantalla "
                      "dinámica)"
                      + _nota80)

        # 81) ASISTENTE DESDE DIBUJO REFORZADO (v3.39.0): validación
        #     previa del contorno, quick-spec sin IA, alternativas con
        #     métricas, checklist, patio experto, reemplazo REAL del
        #     edificio previo y configuraciones guardables.
        from domain import desde_dibujo as _dd81
        _lazo81 = [(0.0, 0.0), (4.0, 4.0), (4.0, 0.0), (0.0, 4.0)]
        _val81 = _dd81.validar_contorno(_lazo81)
        assert _val81["bloquea"] and any(
            h["severidad"] == "ERROR"
            for h in _val81["hallazgos"]), \
            "autointersección del lazo detectada como ERROR"
        _qs81 = _dd81.quick_spec(
            "3 dormitorios, 2 banos, garaje y 2 niveles")
        assert _qs81["niveles"] == 2 \
            and [u["space_type"] for u in _qs81["usos"]] \
            == ["BEDROOM", "BATHROOM", "PARKING"], \
            "quick-spec: 3 dormitorios + 2 baños + garaje + 2 niveles"
        _prog81 = _dd81.programa_edificacion(_qs81["usos"])
        _rec81 = [(0.0, 0.0), (30.0, 0.0), (30.0, 16.0), (0.0, 16.0)]
        _alts81 = _dd81.alternativas(_prog81, _rec81, cantidad=2)
        assert len(_alts81) == 2 and _alts81[0]["etiqueta"] == "A" \
            and all(a["metricas"] for a in _alts81), \
            "dos alternativas con métricas"
        assert _alts81[0]["metricas"]["puntuacion"] \
            >= _alts81[1]["metricas"]["puntuacion"] - 1e-9, \
            "A es la mejor alternativa"
        _aj81 = _dd81.ajustar(_prog81, _rec81, patio=True,
                              patio_ancho_m=3.0)
        assert _aj81.get("patio") and _aj81["patio"]["area_m2"] > 0, \
            "patio experto reservado"
        assert _aj81.get("decisiones"), "decisiones registradas"
        _chk81 = _dd81.checklist_previa(
            _dd81.validar_contorno(_rec81), _aj81)
        assert any(c["estado"] == "OK" for c in _chk81), \
            "checklist previa con casillas OK"
        # conductual: reemplazo y configuraciones en proyecto temporal
        from services.context import ApplicationContext as _Ctx81
        _app81 = _Ctx81()
        _ctx81 = _app81.create_project(
            os.path.join(tmp, "selftest_dd39.arqgen"),
            name="Selftest 39")
        try:
            _r1_81 = _dd81.aplicar_plan(
                _ctx81, _aj81,
                {"nombre_edificio": "Selftest desde dibujo",
                 "reemplazar_previo": True})
            _r2_81 = _dd81.aplicar_plan(
                _ctx81, _aj81,
                {"nombre_edificio": "Selftest desde dibujo",
                 "reemplazar_previo": True})
            assert _r2_81.get("reemplazado"), \
                "el segundo generar reemplaza al primero"
            assert _dd81.edificio_previo(_ctx81) is not None, \
                "el asistente recuerda su último edificio"
            _req81 = _dd81.PlanRequest(contorno=_rec81,
                                       programa=_prog81, patio=True)
            assert _dd81.guardar_estado(_ctx81, _req81), \
                "estado del asistente guardado"
            _conf81 = _dd81.guardar_configuracion(_ctx81, _req81,
                                                  _aj81)
            assert _conf81["etiqueta"].startswith("CONFIGURACIÓN"), \
                "configuración etiquetada"
            assert len(_dd81.listar_configuraciones(_ctx81)) == 1, \
                "historial con una fotografía"
            _de81 = _dd81.cargar_estado(_ctx81)
            assert _de81 is not None and _de81.patio, \
                "estado recuperado con el patio pedido"
            _ctx81.commit()
        finally:
            _ctx81.close()
        checks.append("asistente desde dibujo reforzado v3.39.0: OK "
                      "(validación previa del contorno: autointersecciones, "
                      "abierto y dimensiones imposibles; quick-spec en una "
                      "línea sin IA; alternativas con métricas comparables "
                      "y puntuación explicada; checklist [OK]/[AVISO]/"
                      "[ERROR] antes de generar; patio exterior experto; "
                      "reemplazo del edificio previo con registro; "
                      "configuraciones y estado del asistente dentro del "
                      "proyecto)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 82) HILO SEGURO SQLITE (v3.39.1): «Importar al proyecto» del plano
    #     DXF/DWG corre ArchitectureService en un hilo de fondo mientras
    #     la conexión se abrió en el hilo principal; con el ajuste por
    #     defecto de sqlite3 eso abortaba con "SQLite objects created in
    #     a thread can only be used in that same thread". Ahora la
    #     conexión lleva check_same_thread=False y un candado reentrante
    #     serializa execute/commit/rollback/close. Conductual: el
    #     proyecto se crea aquí y DOS hilos escriben y leen a la vez.
    try:
        from services.context import ApplicationContext as _Ctx82
        _app82 = _Ctx82()
        _ctx82 = _app82.create_project(
            os.path.join(tmp, "selftest_hilo391.arqgen"),
            name="Selftest 39.1")
        _err82: list[str] = []
        _barrera82 = threading.Barrier(2, timeout=30)

        def _hilo82(_n: int) -> None:
            try:
                _barrera82.wait()
                _ctx82.settings.set(f"hilo_{_n}", f"valor_{_n}")
                _ctx82.commit()
                _v82 = _ctx82.settings.get(f"hilo_{_n}")
                if _v82 != f"valor_{_n}":
                    # v3.42.0: con la conexión compartida, el commit del
                    # COMPAÑERO puede cerrar la transacción implícita
                    # que aún contenía la lectura; la fila está
                    # comprometida (el candado serializa cada llamada)
                    # y una relectura inmediata la ve
                    _v82 = _ctx82.settings.get(f"hilo_{_n}")
                assert _v82 == f"valor_{_n}", \
                    "lectura tras commit en hilo ajeno"
            except Exception as exc82:  # noqa: BLE001
                _err82.append(f"{type(exc82).__name__}: {exc82}")

        _h82a = threading.Thread(target=_hilo82, args=(1,), daemon=True)
        _h82b = threading.Thread(target=_hilo82, args=(2,), daemon=True)
        _h82a.start(); _h82b.start()
        _h82a.join(45); _h82b.join(45)
        # y el hilo PRINCIPAL sigue usando la misma conexión sin error
        _ctx82.settings.set("hilo_principal", "ok")
        _ctx82.commit()
        _ctx82.close()
        assert not _err82, "; ".join(_err82)
        assert _h82a.is_alive() is False and _h82b.is_alive() is False, \
            "los dos hilos terminaron"
        checks.append("hilo seguro SQLite v3.39.1: OK (la conexion del "
                      "proyecto cruza hilos con check_same_thread=False y "
                      "candado reentrante; dos hilos escriben configu- "
                      "raciones a la vez sin el error 'created in a "
                      "thread'; Importar al proyecto vuelve a funcionar)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 83) ENCAJE ESTRICTO AL POLÍGONO (v3.40.0): la parcela en L se
    #     tesela en contenedores reales y NADA se sale del polígono
    #     (antes: caja envolvente + aviso de locales fuera). El ala de
    #     la L recibe locales y el informe declara el aprovechamiento.
    try:
        from domain import encaje as _enc83
        from domain import desde_dibujo as _dd83
        _L83 = [(0.0, 0.0), (20.0, 0.0), (20.0, 6.0), (10.0, 6.0),
                (10.0, 10.0), (0.0, 10.0)]
        _info83 = _enc83.contenedores_de(_L83)
        assert _info83["estrategia"] == "descompuesto" \
            and len(_info83["contenedores"]) == 2, \
            "la L se tesela en 2 contenedores"
        assert abs(_info83["area_aprovechable"] - 160.0) < 0.01, \
            "la tesela cubre los 160 m2 de la L"
        _prog83 = _dd83.programa_edificacion(
            [{"space_type": "OFFICE", "cantidad": 6, "area_m2": 20.0}])
        _aj83 = _dd83.ajustar(_prog83, _L83)
        assert _aj83["dentro_del_contorno"], \
            "todo el encaje queda dentro del polígono"
        from domain.desde_dibujo import rect_dentro as _rd83
        assert all(_rd83([tuple(q) for q in r["rect"]], _L83)
                   for r in _aj83["reparto"][0]["locales"]), \
            "verificación dura local a local"
        assert any(r.get("contenedor", 0) > 0
                   for r in _aj83["reparto"][0]["locales"]), \
            "el ala de la L se aprovecha"
        assert _aj83["totales"]["aprovechamiento_pct"] > 50.0, \
            "aprovechamiento declarado"
        _hist83 = _dd83.ajustar(_prog83, _L83, encaje_estricto=False)
        assert not _hist83["dentro_del_contorno"], \
            "el camino histórico conserva su aviso"
        checks.append("encaje estricto al polígono v3.40.0: OK (la "
                      "parcela se tesela en contenedores reales: L en 2, "
                      "U en 3; nada se sale del polígono dibujado y el "
                      "ala de la L se aprovecha; zonas compuestas para "
                      "locales más profundos que cualquier franja; "
                      "aviso honesto con polígonos inclinados; camino "
                      "histórico de caja envolvente conservado)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 84) PROGRAMA ADAPTABLE (v3.41.0): selección de locales + ajuste
    #     dimensional por niveles (mínimo/medio/estricto) para el
    #     cambio de uso en edificaciones existentes: se trabaja con
    #     lo que se tiene y las rebajas de norma quedan documentadas.
    try:
        from domain import desde_dibujo as _dd84
        from domain.desde_dibujo import rect_dentro as _rd84
        _R84 = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]

        def _prog84(ideal, norma):
            _a, _f = _dd84._dimensiones_ajuste(ideal, 2.0)
            return {"servicio": "", "nombre": "P84", "descripcion": "",
                    "parametros": {},
                    "renglones": [{"codigo": "X84",
                                   "nombre": "Local 84",
                                   "space_type": "ROOM",
                                   "area_m2": float(ideal),
                                   "ancho_m": _a, "fondo_m": _f,
                                   "flujo": "libre", "critico": False,
                                   "req": [], "adjacencias": [],
                                   "area_min": float(norma),
                                   "descripcion": "", "copia": 1}],
                    "totales": {"locales": 1,
                                "area_m2": float(ideal)},
                    "flujos": [], "notas": [], "avisos": [],
                    "validacion": []}

        _cod84 = None
        try:
            _dd84.ajustar(_prog84(30.0, 28.0), _R84, ajuste="ideal")
        except Exception as exc84:
            _cod84 = getattr(exc84, "code", "")
        assert _cod84 == "ARQ-DDI-003", "el ideal no entra tal cual"
        _cod84 = None
        try:
            _dd84.ajustar(_prog84(30.0, 28.0), _R84, ajuste="minimo")
        except Exception as exc84:
            _cod84 = getattr(exc84, "code", "")
        assert _cod84 == "ARQ-DDI-010", \
            "el mínimo NO viola la norma: se agota con ARQ-DDI-010"
        _es84 = _dd84.ajustar(_prog84(30.0, 28.0), _R84,
                              ajuste="estricto")
        _rp84 = _es84["ajuste_programa"]["reducidos"][0]
        assert _rp84["area_final"] < 28.0 and _rp84["bajo_norma"], \
            "el estricto rebasa la norma y lo documenta"
        assert _es84["dentro_del_contorno"], "el estricto entra"
        assert all(_rd84([tuple(q) for q in r["rect"]], _R84)
                   for r in _es84["reparto"][0]["locales"]), \
            "lo reducido también queda dentro del polígono"
        _tx84 = _dd84.texto_ajuste(_es84)
        assert "AJUSTE DIMENSIONAL" in _tx84 \
            and "BAJO LA NORMATIVA" in _tx84, \
            "el informe documenta la rebaja local a local"
        _L84 = [(0.0, 0.0), (20.0, 0.0), (20.0, 6.0), (10.0, 6.0),
                (10.0, 10.0), (0.0, 10.0)]
        _p84b = {"servicio": "", "nombre": "S84", "descripcion": "",
                 "parametros": {},
                 "renglones": [{"codigo": _c84, "nombre": "Local " + _c84,
                                "space_type": "ROOM", "area_m2": 18.0,
                                "ancho_m": 4.0, "fondo_m": 4.5,
                                "flujo": "libre", "critico": False,
                                "req": [], "adjacencias": [],
                                "area_min": 12.0, "descripcion": "",
                                "copia": 1}
                               for _c84 in ("A84", "B84", "C84")],
                 "totales": {"locales": 3, "area_m2": 54.0},
                 "flujos": [], "notas": [], "avisos": [],
                 "validacion": []}
        _se84 = _dd84.ajustar(_p84b, _L84, seleccion=["A84", "C84"])
        _codigos84 = sorted({r["codigo"]
                             for r in _se84["programa"]["renglones"]})
        assert _codigos84 == ["A84", "C84"], "solo los elegidos entran"
        assert any("se excluyen 1 local(es)" in a
                   for a in _se84["avisos"]), \
            "la exclusión queda documentada en los avisos"
        assert _se84["dentro_del_contorno"]
        checks.append("programa adaptable v3.41.0: OK (selección de "
                      "locales documentada; el ajuste mínimo no viola "
                      "la norma y el estricto reduce hasta entrar "
                      "declarando los locales BAJO LA NORMATIVA; todo "
                      "dentro del polígono)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 85. PASILLOS Y FILTROS v3.42.0: el plano real AP Y MORGUE con
    #     ajuste estricto queda en UN nivel teselado al 95 %+ con
    #     pasillo servido, el filtro sanitario como barrera de flujo
    #     y el orden público->sucio; la compactación baja niveles.
    try:
        from domain import desde_dibujo as _dd85
        from domain import servicios_engine as _sm85
        from domain.desde_dibujo import rect_dentro as _rd85
        # el contorno real del plano «AP Y MORGUE.dxf» (mm -> m)
        _Z85 = [(0.179, 3.617), (0.179, 15.007), (6.829, 15.007),
                (6.829, 8.177), (17.681, 8.177), (17.681, 0.037),
                (3.804, 0.037), (3.804, 3.617)]
        _pm85 = _sm85.programa_servicio("MORGUE", {})
        assert any(r["codigo"] == "FILTRO" for r in _pm85["renglones"]), \
            "el catálogo de morgue trae el filtro sanitario"
        _ideal85 = _dd85.ajustar(_sm85.programa_servicio("MORGUE", {}),
                                 _Z85, encaje_estricto=True,
                                 ajuste="ideal")
        _es85 = _dd85.ajustar(_sm85.programa_servicio("MORGUE", {}),
                              _Z85, encaje_estricto=True,
                              ajuste="estricto")
        assert _es85["niveles"] < _ideal85["niveles"], \
            "la compactación baja el número de niveles"
        assert _es85["niveles"] == 1 and _es85["dentro_del_contorno"], \
            "el servicio pequeño entra en 1 nivel dentro del polígono"
        _plan85 = _es85["reparto"][0]
        assert _plan85.get("pasillo"), "el nivel lleva pasillo"
        assert all(_rd85([tuple(q) for q in r["rect"]], _Z85)
                   for r in _plan85["locales"]), \
            "todo queda dentro del polígono real"
        _ap85 = float(_es85["totales"]["aprovechamiento_pct"])
        assert _ap85 >= 95.0, \
            f"el contorno se aprovecha casi completo ({_ap85}%)"
        _tipos85 = {r["space_type"] for r in _plan85["locales"]}
        assert "FILTER" in _tipos85, \
            "el filtro sanitario entra como barrera"
        _flujos85 = [str(r.get("flujo", "")) for r in _plan85["locales"]]
        assert _flujos85[-1] == "publico" and "sucio" in _flujos85, \
            "el orden por flujo deja lo público al final de la banda"
        _tx85 = _dd85.texto_ajuste(_es85)
        assert "CIRCULACIÓN Y FILTROS" in _tx85 \
            and "TESELADO COMPLETO" in _tx85, \
            "el informe documenta circulación, filtros y teselado"
        _tx85.encode("cp1252")
        checks.append("pasillos y filtros v3.42.0: OK (el plano real "
                      "AP Y MORGUE con ajuste estricto queda en 1 "
                      "nivel teselado con pasillo servido por locales "
                      "re-dimensionados, filtro sanitario como "
                      "barrera entre flujos y aprovechamiento del "
                      "polígono casi completo; la compactación baja "
                      "niveles y el informe lo documenta)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 86. VIVIENDA SOCIAL v3.43.0: los planos de referencia del
    #     usuario (estudio 25 m2 y casa cubana 6x8.4) salen en 1
    #     nivel con el tope duro, sala distribuidora sin pasillo,
    #     chaflanes a 45 grados y el lavadero doméstico separado del
    #     hospitalario; el mobiliario automático amuebla la casa.
    try:
        from domain import desde_dibujo as _dd86
        _B86 = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]
        _C86 = [(0.0, 0.0), (6.0, 0.0), (6.0, 8.4), (0.0, 8.4)]
        # DNA de vivienda: Sala 9, Comedor 6, lavadero doméstico
        _sala86 = _dd86.programa_quick("sala", "d86")
        assert any(r["space_type"] == "LIVING_ROOM"
                   and float(r["area_min"]) == 9.0
                   for r in _sala86["renglones"]), \
            "la Sala lleva el mínimo de vivienda social (9 m2)"
        _lav86 = _dd86.programa_quick("dormitorio, lavadero", "d86")
        assert any(r["space_type"] == "LAVADERO"
                   for r in _lav86["renglones"]), \
            "el lavadero del quick es el doméstico (no el hospitalario)"
        # estudio 25 m2: 1 nivel, sala distribuidora, sin pasillo
        _b86 = _dd86.ajustar(_dd86.programa_quick(
            "dormitorio, bano, cocina, sala", "d86"), _B86,
            encaje_estricto=True)
        assert _b86["niveles"] == 1 and _b86["dentro_del_contorno"], \
            "el estudio de 25 m2 entra en 1 nivel"
        assert _b86["sala_distribuidora"] \
            and _b86["reparto"][0]["pasillo"] is None, \
            "la casa pequeña va sin pasillo (sala distribuidora)"
        assert _b86["tope_niveles"] == 1, \
            "la vivienda se topa a 1 nivel por defecto"
        # casa cubana 6x8.4: dormitorios normativos
        _c86 = _dd86.ajustar(_dd86.programa_quick(
            "2 dormitorios, bano, sala, cocina, comedor", "d86"),
            _C86, encaje_estricto=True)
        assert _c86["niveles"] == 1 and _c86["dentro_del_contorno"], \
            "la casa cubana entra en 1 nivel"
        _dorms86 = [r for r in _c86["reparto"][0]["locales"]
                    if r["space_type"] == "BEDROOM"]
        assert len(_dorms86) == 2 and all(
            float(r["area_m2"]) >= 9.0 for r in _dorms86), \
            "los dormitorios cumplen la norma en 1 planta"
        # tope duro: el que no cabe lanza ARQ-DDI-011 NOMBRANDO
        _Z86 = [(0.0, 2.9), (2.6, 2.9), (2.6, 0.0), (6.5, 0.0),
                (6.5, 2.9), (3.9, 2.9), (3.9, 6.4), (5.5, 6.4),
                (5.5, 10.4), (0.0, 10.4)]
        _tope_ok = False
        try:
            _dd86.ajustar(_dd86.programa_quick(
                "2 dormitorios, bano, cocina, comedor, sala, lavadero",
                "d86"), _Z86, encaje_estricto=True)
        except Exception as _e86:
            _tope_ok = (getattr(_e86, "code", "") == "ARQ-DDI-011"
                        and "Lavadero" in str(getattr(_e86, "message",
                                                      "")))
        assert _tope_ok, \
            "el tope duro lanza ARQ-DDI-011 nombrando al excluido"
        # chaflanes a 45 grados en la casa Z sin lavadero
        _z86 = _dd86.ajustar(_dd86.programa_quick(
            "2 dormitorios, bano, cocina, comedor, sala", "d86"),
            _Z86, encaje_estricto=True,
            seleccion=["BEDROOM", "BATHROOM", "KITCHEN",
                       "LIVING_ROOM", "DINING_ROOM"])
        assert _z86["chaflanes"] \
            and any(r.get("poligono")
                    for r in _z86["reparto"][0]["locales"]), \
            "los chaflanes a 45 grados dejan poligonales reales"
        _tx86 = _dd86.texto_ajuste(_b86)
        assert "TOPE DE NIVELES (v3.43.0)" in _tx86 \
            and "MODO SALA DISTRIBUIDORA (v3.43.0)" in _tx86, \
            "el informe documenta el tope y el modo distribuidor"
        _tx86.encode("cp1252")
        checks.append("vivienda social v3.43.0: OK (DNA de vivienda "
                      "con Sala de 9 m2 y Comedor de 6, lavadero "
                      "domestico separado del hospitalario, «1 nivel» "
                      "como tope duro que compacta antes de crecer y "
                      "nombra lo que no cabe, modo sala distribuidora "
                      "sin pasillo en casas de <= 60 m2, chaflanes a "
                      "45 grados hacia la sala y mobiliario automatico "
                      "en los locales generados)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 87. PATIO DOMÉSTICO Y CHAFLANES v3.43.1: el «patio» del quick
    #     es el doméstico (4-9 m2, no el escolar de 300 que devoraba
    #     la villa 50x100) y los chaflanes a 45 grados disparan SIN
    #     selección de locales midiendo contra el mínimo del DNA.
    try:
        from domain import desde_dibujo as _dd87
        _p87 = _dd87.programa_quick("3 dormitorios, 3 banos, cocina, "
                                    "sala, comedor, recibidor, patio, "
                                    "1 nivel", "d87")
        assert any(r["space_type"] == "PATIO_DOMESTICO"
                   for r in _p87["renglones"]), \
            "el «patio» del quick es el doméstico (no el escolar)"
        _F87 = [(0.0, 0.0), (15.24, 0.0), (15.24, 30.48), (0.0, 30.48)]
        _f87 = _dd87.ajustar(_p87, _F87, encaje_estricto=True,
                             ajuste="ideal")
        assert _f87["niveles"] == 1 and _f87["dentro_del_contorno"], \
            "la villa 50x100 de las imágenes del usuario entra en 1 nivel"
        _pat87 = next(r for r in _f87["reparto"][0]["locales"]
                      if r["space_type"] == "PATIO_DOMESTICO")
        assert float(_pat87["area_m2"]) < 25.0, \
            "el patio de vivienda no devora la planta (era 300 m2)"
        assert _f87["chaflanes"], \
            "la villa abre esquinas a 45 grados hacia la sala"
        _G87 = [(0.0, 0.0), (4.67, 0.0), (4.67, 10.925), (0.0, 10.925)]
        _g87 = _dd87.ajustar(_dd87.programa_quick(
            "dormitorio, bano, sala", "d87"), _G87,
            encaje_estricto=True)
        assert _g87["chaflanes"] and _g87["sala_distribuidora"], \
            "la suite de 51 m2 corta esquina SIN selección de locales"
        assert any(len(r.get("poligono") or []) == 5
                   for r in _g87["reparto"][0]["locales"]), \
            "el local cortado queda con poligonal de 5 vértices"
        assert all(float(r["area_m2"])
                   >= float(r.get("area_min") or 0.0) - 1e-6
                   for r in _g87["reparto"][0]["locales"]), \
            "ningún corte baja del mínimo del DNA"
        _tx87 = _dd87.texto_ajuste(_g87)
        assert "CHAFLANES A 45 GRADOS" in _tx87, \
            "el informe documenta los chaflanes"
        _tx87.encode("cp1252")
        checks.append("patio doméstico y chaflanes v3.43.1: OK (el "
                      "«patio» del quick es el doméstico de 4-9 m2 y "
                      "no el escolar de 300 que devoraba la villa "
                      "50x100, las villas de las imágenes entran en 1 "
                      "nivel con esquinas a 45 grados hacia la sala y "
                      "los chaflanes disparan sin selección de "
                      "locales midiendo contra el mínimo del DNA: la "
                      "suite de 51 m2 corta con poligonal de 5 "
                      "vértices, la sala absorbe el triángulo y el "
                      "informe lo documenta)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 88. LOBBY Y VESTIDOR v3.44.0: VESTIDOR (W.I.C) en el DNA y
    #     palabras lobby/foyer/vestidor/wic/closet en el quick; el
    #     umbral del modo distribuidor es parametrizable (villas
    #     grandes con lobby) y sin sala el hub es el LOBBY.
    try:
        from domain import desde_dibujo as _dd88
        _p88 = _dd88.programa_quick("3 dormitorios, 2 banos, cocina, "
                                    "sala, comedor, vestidor, lobby, "
                                    "1 nivel", "d88")
        _t88 = {r["space_type"] for r in _p88["renglones"]}
        assert "VESTIDOR" in _t88 and "VESTIBULE" in _t88, \
            "vestidor/wic/closet y lobby/foyer entran al quick"
        _C88 = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        _a88 = _dd88.ajustar(
            _dd88.programa_quick("3 dormitorios, 2 banos, cocina, "
                                 "sala, comedor, 1 nivel", "d88"),
            _C88, encaje_estricto=True, ajuste="ideal",
            distribuidora_max_m2=120.0)
        assert _a88.get("sala_distribuidora"), \
            "una casa de 100 m2 con tope 120 va SIN pasillo (lobby)"
        _b88 = _dd88.ajustar(
            _dd88.programa_quick("3 dormitorios, 2 banos, cocina, "
                                 "sala, comedor, 1 nivel", "d88"),
            _C88, encaje_estricto=True, ajuste="ideal")
        assert not _b88.get("sala_distribuidora"), \
            "sin el parámetro el umbral sigue siendo 60 m2"
        _u88 = _dd88.ajustar(_dd88.programa_quick(
            "dormitorio, bano, lobby, 1 nivel", "d88"),
            [(0.0, 0.0), (6.0, 0.0), (6.0, 7.5), (0.0, 7.5)],
            encaje_estricto=True, ajuste="ideal", chaflanes=True)
        assert any(c.get("sala") and "Vest" in str(c["sala"])
                   for c in _u88.get("chaflanes", [])), \
            "sin sala, el chaflán se abre hacia el LOBBY"
        checks.append("lobby y vestidor v3.44.0: OK (VESTIDOR W.I.C "
                      "en el DNA con el DRESSING_ROOM de personal "
                      "intacto, palabras lobby/foyer/vestidor/wic/"
                      "closet en el quick, umbral del modo "
                      "distribuidor parametrizable para villas "
                      "grandes con lobby y chaflanes que se abren "
                      "hacia el lobby cuando no hay sala)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 89. CHAFLÁN PROPIO DE FACHADA v3.44.0: la esquina del local que
    #     cae en el CONTORNO se corta a 45 grados (bay window de las
    #     unidades de hotel); la pérdida la absorbe el propio local
    #     sin bajar del mínimo del DNA.
    try:
        from domain import desde_dibujo as _dd89
        _u89 = _dd89.ajustar(_dd89.programa_quick(
            "dormitorio, bano, 1 nivel", "d89"),
            [(0.0, 0.0), (4.2, 0.0), (4.2, 6.7), (0.0, 6.7)],
            encaje_estricto=True, ajuste="ideal", chaflanes=True)
        _pr89 = [c for c in _u89.get("chaflanes", [])
                 if c.get("tipo") == "propio"]
        assert len(_pr89) == 2, \
            "la unidad sin sala corta 2 esquinas propias en auto"
        _dorm89 = next(r for r in _u89["reparto"][0]["locales"]
                       if r["space_type"] == "BEDROOM")
        assert len(_dorm89.get("poligono") or []) == 6, \
            "la poligonal del bay window (2 cortes) es de 6 vértices"
        assert float(_dorm89["area_m2"]) \
            >= float(_dorm89.get("area_min") or 0.0) - 1e-6, \
            "el corte propio no baja del mínimo del DNA"
        assert not [c for c in _dd89.ajustar(
            _dd89.programa_quick("dormitorio, bano, 1 nivel", "d89"),
            [(0.0, 0.0), (4.2, 0.0), (4.2, 6.7), (0.0, 6.7)],
            encaje_estricto=True, ajuste="ideal", chaflanes=True,
            chaflan_propio=False).get("chaflanes", [])
            if c.get("tipo") == "propio"], \
            "chaflan_propio=False lo desactiva"
        _tx89 = _dd89.texto_ajuste(_u89)
        _tx89.encode("cp1252")
        checks.append("chaflán propio de fachada v3.44.0: OK (bay "
                      "window: la esquina del local que cae en el "
                      "contorno se corta a 45 grados con cateto 0.6 "
                      "m y la pérdida la absorbe el propio local; en "
                      "auto solo en niveles sin sala/lobby, "
                      "desactivable y documentado)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 90. MULTI-ALA Y MULTI-UNIDAD v3.44.0: ajustar_zonas reparte UN
    #     programa entre N alas (hubs al ala principal) y
    #     repartir_rejilla repite la MISMA unidad con corredor
    #     central (edificio tipo); aplicar_zonas crea UN edificio.
    try:
        from domain import desde_dibujo as _dd90
        _h90 = _dd90.programa_edificacion([
            {"space_type": "WARD", "cantidad": 10},
            {"space_type": "NURSE_STATION", "cantidad": 1},
            {"space_type": "BATHROOM", "cantidad": 4}],
            "Hospital en Y")
        _z90 = _dd90.ajustar_zonas(_h90, [
            {"contorno": [(0.0, 0.0), (30.0, 0.0), (30.0, 12.0),
                          (0.0, 12.0)], "rol": "ala norte"},
            {"contorno": [(0.0, 14.0), (26.0, 14.0), (26.0, 26.0),
                          (0.0, 26.0)], "rol": "ala sur"}],
            ajuste="ideal")
        assert _z90["tipo"] == "zonas" and len(_z90["zonas"]) == 2 \
            and _z90["dentro_del_contorno"], \
            "el programa se reparte entre 2 alas dentro de cada una"
        assert _z90["totales"]["aprovechamiento_pct"] > 50.0, \
            "el compuesto suma los totales de las alas"
        try:
            _dd90.ajustar_zonas(_h90, [{"contorno":
                                        [(0.0, 0.0), (5.0, 0.0),
                                         (5.0, 5.0), (0.0, 5.0)]}])
            raise AssertionError("debía lanzar ARQ-DDI-012")
        except Exception as _e90:
            assert getattr(_e90, "code", "") == "ARQ-DDI-012", \
                "menos de 2 zonas lanza ARQ-DDI-012"
        _r90 = _dd90.repartir_rejilla(
            _dd90.programa_quick("2 dormitorios, bano, cocina, "
                                 "sala, 1 nivel", "d90"),
            [(0.0, 0.0), (24.0, 0.0), (24.0, 11.5), (0.0, 11.5)],
            columnas=3, ajuste="ideal")
        assert _r90["tipo"] == "rejilla" and len(_r90["zonas"]) == 6 \
            and _r90["pasillo_central"], \
            "el edificio tipo repite la unidad en 6 celdas con " \
            "corredor central"
        checks.append("multi-ala y multi-unidad v3.44.0: OK (UN "
                      "programa en N contornos con reparto "
                      "determinista y hubs al ala principal, "
                      "ARQ-DDI-012 con el rol cuando un ala no "
                      "cabe, y edificio tipo: la misma unidad "
                      "repetida en la rejilla 2 bandas + corredor "
                      "central como la planta tipo de las imágenes)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 91. GEOMETRÍA RADIAL Y FACHADAS v3.44.0: plan_radial genera el
    #     anillo sectorial con núcleo circular y corredor anular
    #     (arcos por cuerdas) y fachadas.elevacion genera las 4
    #     pieles con DXF por capas.
    try:
        from domain import radial as _rd91
        from domain import desde_dibujo as _dd91
        _t91 = _rd91.plan_radial(_dd91.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "BEDROOM", "cantidad": 12},
            {"space_type": "BATHROOM", "cantidad": 6}],
            "Torre"), radio_ext=14.0, radio_nucleo=3.0, sectores=8,
            corredor_m=1.6)
        assert _t91["dentro_del_contorno"], \
            "todo el anillo radial queda dentro del círculo"
        _p91 = _t91["reparto"][0]
        assert _p91["pasillo"] \
            and _p91["pasillo"]["space_type"] == "CORRIDOR", \
            "el corredor anular rodea el núcleo"
        _n91 = next(r for r in _p91["locales"]
                    if r["space_type"] == "VESTIBULE")
        assert abs(float(_n91["area_m2"]) - math.pi * 9.0) < 1.5, \
            "el vestíbulo ocupa el núcleo circular"
        assert all(float(r["area_m2"])
                   >= float(r.get("area_min") or 0.0) - 1e-6
                   for r in _p91["locales"]), \
            "el crecimiento radial no baja del mínimo del DNA"
        from domain import elevaciones as _fc91
        _f91 = _fc91.elevacion([(0.0, 0.0), (10.0, 0.0),
                                (10.0, 8.0), (0.0, 8.0)],
                               n_pisos=2, piel="brise")
        assert len(_f91["fachadas"]) == 4 \
            and all(f["entidades"] for f in _f91["fachadas"]), \
            "las 4 fachadas del contorno llevan piel brise"
        import tempfile as _tf91
        import os as _os91
        with _tf91.TemporaryDirectory() as _tmp91:
            _dxf91 = _os91.path.join(_tmp91, "fachadas.dxf")
            _fc91.exportar_elevacion_dxf(_f91, _dxf91)
            assert _os91.path.getsize(_dxf91) > 1000, \
                "el DXF de fachadas se escribe"
        checks.append("geometría radial y fachadas v3.44.0: OK "
                      "(plan_radial: N sectores alrededor del "
                      "núcleo circular con corredor anular, arcos "
                      "por cuerdas dentro del círculo y mínimos "
                      "del DNA; fachadas paramétricas: 4 pieles "
                      "(panos, ventana corrida, brise, perforada) "
                      "con PNG y DXF R12 por capas)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 92. TORRE EN Y REAL v3.45.0: plan_y genera la Y con núcleo
    #     circular (vestíbulo), N alas radiantes con corredor por ala
    #     y locales a ambos lados; el contorno es la Y real por
    #     cuerdas; métricas honestas por centroide.
    try:
        from domain import radial as _rd92
        from domain import desde_dibujo as _dd92
        _t92 = _rd92.plan_y(_dd92.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "WARD", "cantidad": 9},
            {"space_type": "NURSE_STATION", "cantidad": 3},
            {"space_type": "BATHROOM", "cantidad": 6}],
            "Hospital en Y"), radio_nucleo=7.5, largo_ala=16.0,
            ancho_ala=11.0, n_alas=3, corredor_m=1.6)
        assert _t92["tipo"] == "y_radial" \
            and _t92["dentro_del_contorno"], \
            "la Y de 3 alas queda dentro del contorno Y real"
        _p92 = _t92["reparto"][0]
        assert len(_p92["pasillos"]) == 3 \
            and all(p["space_type"] == "CORRIDOR"
                    for p in _p92["pasillos"]), \
            "cada ala lleva su corredor (pasillos múltiples)"
        _n92 = next(r for r in _p92["locales"]
                    if r["space_type"] == "VESTIBULE")
        assert abs(float(_n92["area_m2"]) - math.pi * 7.5 ** 2) < 4.0, \
            "el vestíbulo ocupa el núcleo circular"
        assert all(float(r["area_m2"])
                   >= float(r.get("area_min") or 0.0) - 1e-6
                   for r in _p92["locales"]), \
            "el crecimiento de las filas no baja del mínimo del DNA"
        _m92 = _dd92.metricas_de(_t92)
        assert _m92["cumplimiento_pct"] == 100.0, \
            "las métricas cuentan las piezas poligonales por " \
            "centroide (fallback v3.45)"
        try:
            _rd92.plan_y(_dd92.programa_edificacion([
                {"space_type": "WARD", "cantidad": 9}], "Sin hub"),
                radio_nucleo=7.5)
            raise AssertionError("debía lanzar ARQ-DDI-012")
        except Exception as _e92:
            assert getattr(_e92, "code", "") == "ARQ-DDI-012", \
                "núcleo sin vestíbulo lanza ARQ-DDI-012"
        try:
            _rd92.plan_y(_t92["programa"], radio_nucleo=5.0,
                         ancho_ala=11.0, n_alas=3)
            raise AssertionError("debía lanzar ARQ-DDI-012")
        except Exception as _e92b:
            assert getattr(_e92b, "code", "") == "ARQ-DDI-012", \
                "alas solapadas por radio corto lanza ARQ-DDI-012"
        checks.append("torre en Y real v3.45.0: OK (plan_y: núcleo "
                      "circular con el vestíbulo, N alas radiantes a "
                      "120 grados con corredor por ala y locales a "
                      "ambos lados, contorno Y real por cuerdas, "
                      "cabecera transversal opcional, ARQ-DDI-012 si "
                      "las alas solapan o el núcleo no lleva "
                      "vestíbulo, y métricas honestas por centroide "
                      "para las piezas poligonales)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 93. MÁS PIELES DE FACHADA v3.45.0: el catálogo pasa de 4 a 12
    #     pieles deterministas (hexagonal, diagrid, celosia,
    #     gradiente, fins, cortina, bandas y parametrica) con PNG y
    #     DXF R12 por capas intactos.
    try:
        from domain import elevaciones as _fc93
        assert len(_fc93.PIELES) == 12, \
            "el catálogo de pieles llega a 12"
        _f93 = _fc93.elevacion([(0.0, 0.0), (10.0, 0.0),
                                (10.0, 8.0), (0.0, 8.0)],
                               n_pisos=3, piel="hexagonal")
        _l93 = [e for f in _f93["fachadas"] for e in f["entidades"]
                if e["tipo"] == "linea"
                and e.get("capa") == "FACH_PERFORACION"]
        assert _l93 and len(_l93) % 6 == 0, \
            "la malla hexagonal dibuja celdas de 6 líneas"
        _d93 = _fc93.elevacion([(0.0, 0.0), (10.0, 0.0),
                                (10.0, 8.0), (0.0, 8.0)],
                               n_pisos=3, piel="diagrid")
        _cap93 = {e.get("capa") for f in _d93["fachadas"]
                  for e in f["entidades"]}
        assert "FACH_LAMAS" in _cap93 \
            and "FACH_VENTANA" not in _cap93, \
            "el diagrid es malla pura (sin ventanas por paño)"
        _g93 = _fc93.elevacion([(0.0, 0.0), (10.0, 0.0),
                                (10.0, 8.0), (0.0, 8.0)],
                               n_pisos=3, piel="gradiente")
        _c93 = [e for f in _g93["fachadas"] for e in f["entidades"]
                if e["tipo"] == "circulo"]
        assert max(e["r"] for e in _c93) \
            > min(e["r"] for e in _c93), \
            "la perforación paramétrica decrece con la altura"
        _q93 = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]
        assert _fc93.elevacion(_q93, n_pisos=2,
                               piel="parametrica") == \
            _fc93.elevacion(_q93, n_pisos=2, piel="parametrica"), \
            "las pieles paramétricas son deterministas"
        import tempfile as _tf93
        import os as _os93
        with _tf93.TemporaryDirectory() as _tmp93:
            _dxf93 = _os93.path.join(_tmp93, "piel.dxf")
            _fc93.exportar_elevacion_dxf(_g93, _dxf93)
            assert _os93.path.getsize(_dxf93) > 1000, \
                "el DXF de la piel nueva se escribe"
        checks.append("más pieles de fachada v3.45.0: OK (12 pieles "
                      "deterministas: hexagonal con celdas de 6 "
                      "líneas, diagrid y celosia como malla pura, "
                      "gradiente con radio decreciente, fins de "
                      "aletas dobles, cortina con spandrel, bandas "
                      "con banda opaca y parametrica facetada; PNG y "
                      "DXF R12 por capas intactos)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 94. EXPORTAR TODO A BIM v3.46.0: el paquete en UNA carpeta
    #     (IFC4 + DXF R2010 + DXF R12 + JSON + CSV + XLSX + SVG) y la
    #     torre en Y ya se traza CON muros (las costuras degeneradas
    #     del contorno lanzaban ARQ-DOM-048 y bloqueaban el BIM).
    try:
        from services.export_service import ExportService as _Ex94
        from domain import radial as _rd94
        from domain import desde_dibujo as _dd94
        _prog94 = _dd94.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "WARD", "cantidad": 6},
            {"space_type": "BATHROOM", "cantidad": 2}], "Y 94")
        _aj94 = _rd94.plan_y(_prog94, radio_nucleo=6.0,
                             largo_ala=14.0, ancho_ala=10.0, n_alas=3,
                             corredor_m=1.6)
        _ctx94 = application.create_project(
            os.path.join(tmp, "selftest94.arqgen"), name="Selftest 94")
        _res94 = _dd94.aplicar_plan(
            _ctx94, _aj94, {"trazar_muros": True,
                            "mobiliario": False,
                            "nombre_edificio": "Torre Y 94"})
        assert int(_res94["muros"]) > 100, \
            "la torre en Y traza sus muros sin ARQ-DOM-048"
        _sal94 = os.path.join(tmp, "paquete94")
        _paq94 = _Ex94().exportar_todo(_ctx94, _sal94)
        assert sorted(_paq94["archivos"]) == \
            ["CSV", "DXF", "DXF_R12", "IFC", "JSON", "SVG", "XLSX"], \
            "el paquete lleva los 7 formatos"
        assert _paq94["errores"] == {}, "sin errores de exportación"
        with open(_paq94["archivos"]["IFC"], encoding="utf-8") as _fh94:
            _ifc94 = _fh94.read()
        assert _ifc94.count("IFCBUILDINGSTOREY(") == 1 \
            and _ifc94.count("IFCSPACE(") >= 12 \
            and _ifc94.count("IFCWALL(") == int(_res94["muros"]), \
            "el IFC4 lleva el nivel, los locales y los muros de la Y"
        _ctx94.close()
        checks.append("exportar todo a BIM v3.46.0: OK (paquete IFC4 + "
                      "DXF R2010 + DXF R12 + JSON + CSV + XLSX + SVG en "
                      "una carpeta con un clic; torre en Y con muros "
                      "sin ARQ-DOM-048; espacios IFC con la altura del "
                      "nivel)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 95. HOSPITAL EN X REAL v3.47.0: plan_x cruza dos barras
    #     perpendiculares con el hub central (vestíbulo en el cruce),
    #     corredor por brazo y locales a ambos lados; el contorno es
    #     la UNIÓN de las dos barras (12 vértices, totalmente
    #     ortogonal) y la planta tipo se repite en N niveles.
    try:
        from domain import radial as _rd95
        from domain import desde_dibujo as _dd95
        _prog95 = _dd95.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "EMERGENCY_ROOM", "cantidad": 2},
            {"space_type": "WARD", "cantidad": 6},
            {"space_type": "NURSE_STATION", "cantidad": 3},
            {"space_type": "BATHROOM", "cantidad": 5}],
            "Hospital en X")
        _t95 = _rd95.plan_x(_prog95, largo_barra=56.0,
                            ancho_barra=13.0, corredor_m=2.0,
                            angulo=math.radians(45.0),
                            altura_nivel_m=3.2, niveles=3)
        assert _t95["tipo"] == "x_radial" \
            and _t95["dentro_del_contorno"] and _t95["niveles"] == 3, \
            "la X con 3 plantas tipo queda dentro del contorno"
        assert len(_t95["forma"]["vertices"]) == 12, \
            "el contorno X es la unión de las dos barras (12 vértices)"
        _ar95 = [math.hypot(
            _t95["forma"]["vertices"][(i + 1) % 12][0]
            - _t95["forma"]["vertices"][i][0],
            _t95["forma"]["vertices"][(i + 1) % 12][1]
            - _t95["forma"]["vertices"][i][1])
            for i in range(12)]
        assert min(_ar95) > 1.0, \
            "el contorno X no tiene aristas degeneradas (muros OK)"
        _p95 = _t95["reparto"][0]
        assert len(_t95["reparto"]) == 3, "planta tipo en 3 niveles"
        assert len(_p95["pasillos"]) == 4, \
            "cada brazo lleva su corredor"
        _hub95 = next(r for r in _p95["locales"]
                      if r["space_type"] == "VESTIBULE")
        assert abs(float(_hub95["area_m2"]) - 13.0 * 13.0) < 1.0, \
            "el vestíbulo ocupa el cruce de las barras (hub)"
        assert all(float(r["area_m2"])
                   >= float(r.get("area_min") or 0.0) - 1e-6
                   for r in _p95["locales"]), \
            "el crecimiento de las filas no baja del mínimo del DNA"
        _m95 = _dd95.metricas_de(_t95)
        assert _m95["cumplimiento_pct"] == 100.0 \
            and _m95["niveles"] == 3, \
            "métricas honestas de la X en 3 niveles"
        try:
            _rd95.plan_x(_dd95.programa_edificacion(
                [{"space_type": "WARD", "cantidad": 6}], "Sin hub"),
                largo_barra=56.0)
            raise AssertionError("debía lanzar ARQ-DDI-012")
        except Exception as _e95:
            assert getattr(_e95, "code", "") == "ARQ-DDI-012", \
                "X sin vestíbulo lanza ARQ-DDI-012"
        try:
            _rd95.plan_x(_prog95, largo_barra=18.0, ancho_barra=13.0)
            raise AssertionError("debía lanzar ARQ-DDI-012")
        except Exception as _e95b:
            assert getattr(_e95b, "code", "") == "ARQ-DDI-012", \
                "brazo corto lanza ARQ-DDI-012"
        checks.append("hospital en X real v3.47.0: OK (plan_x: dos "
                      "barras cruzadas con el hub central en el "
                      "cruce, corredor por brazo, contorno unión de "
                      "12 vértices sin aristas degeneradas, planta "
                      "tipo repetida en N niveles, ARQ-DDI-012 si el "
                      "brazo es corto o el hub no lleva vestíbulo)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    # 96. Y DESIGUAL + NIVELES v3.47.0: plan_y acepta largos_alas
    #     (estrella radial de alas desiguales, como el hospital
    #     oncológico) y niveles de planta tipo; plan_radial también.
    try:
        from domain import radial as _rd96
        from domain import desde_dibujo as _dd96
        _prog96 = _dd96.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "LABORATORY", "cantidad": 2},
            {"space_type": "WARD", "cantidad": 4},
            {"space_type": "NURSE_STATION", "cantidad": 2},
            {"space_type": "BATHROOM", "cantidad": 4}],
            "Estrella desigual")
        _t96 = _rd96.plan_y(_prog96, radio_nucleo=9.0, ancho_ala=12.0,
                            n_alas=4, corredor_m=1.6, cabecera_m=4.0,
                            largos_alas=[18.0, 13.0, 20.0, 11.0],
                            niveles=2)
        assert _t96["dentro_del_contorno"] \
            and _t96["niveles"] == 2 \
            and len(_t96["reparto"]) == 2, \
            "la estrella desigual se repite en 2 plantas tipo"
        assert _t96["y_radial"]["largos_alas"] == [18.0, 13.0, 20.0,
                                                   11.0], \
            "los largos desiguales quedan documentados"
        _vs96 = _t96["forma"]["vertices"]
        _per96 = sum(math.hypot(
            _vs96[(i + 1) % len(_vs96)][0] - _vs96[i][0],
            _vs96[(i + 1) % len(_vs96)][1] - _vs96[i][1])
            for i in range(len(_vs96)))
        assert abs(_per96
                   - float(_t96["forma"]["perimetro_m"])) < 0.1, \
            "el contorno de la estrella desigual cierra exacto"
        _p96 = _t96["reparto"][0]
        # largo de cada corredor = area / ancho: con alas desiguales
        # los largos de los corredores son DESIGUALES también
        _largos96 = sorted({round(float(r["area_m2"])
                                  / float(r["ancho_m"]), 1)
                            for r in _p96["pasillos"]})
        assert len(_largos96) > 1, \
            "los corredores tienen largos desiguales"
        _t96r = _rd96.plan_radial(_prog96, radio_ext=12.0, sectores=8,
                                  corredor_m=1.5, radio_nucleo=3.0,
                                  niveles=2)
        assert _t96r["niveles"] == 2 \
            and len(_t96r["reparto"]) == 2, \
            "plan_radial repite la planta tipo en 2 niveles"
        try:
            _rd96.plan_y(_prog96, radio_nucleo=9.0, ancho_ala=12.0,
                         n_alas=4, largos_alas=[18.0, 13.0])
            raise AssertionError("debía lanzar ARQ-DDI-012")
        except Exception as _e96:
            assert getattr(_e96, "code", "") == "ARQ-DDI-012", \
                "largos_alas incompleto lanza ARQ-DDI-012"
        checks.append("Y desigual y niveles v3.47.0: OK (plan_y con "
                      "largos_alas desiguales y plan_radial con "
                      "niveles: la estrella radial del hospital "
                      "oncológico y la planta tipo repetida)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(f"FALLO: {type(exc).__name__}: {exc}")
        logger.error("Selftest falló: %s\n%s", exc, traceback.format_exc())

    if console:
        from core.consola import consola_segura
        consola_segura()
        print("=" * 56)
        print("ARQ GEN — SELFTEST")
        print("=" * 56)
        for check in checks:
            marker = "OK  " if not check.startswith("FALLO") else "FAIL"
            print(f"[{marker}] {check}")
        print("=" * 56)
        print("RESULTADO:", "CORRECTO" if ok else "CON FALLOS")
    return ok, checks


def main() -> int:
    ok, _ = run_selftest(console=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run_selftest", "main"]

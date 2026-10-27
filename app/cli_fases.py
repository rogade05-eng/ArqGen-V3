"""CLI commands for FASES 34-43 (v1.3.0).

    docs        documentation module (spec 68-70, 106) — FASE 34
    optimize    multiobjective engine (spec 19)          — FASE 35
    audit       filtered audit + stats + export         — FASE 36
    version     compare / export / branch               — FASE 37
    backup      autosave / incremental / journal / recover — FASE 38
    plugins     validate / info / new                   — FASE 39
    benchmark   performance suite + cache inventory     — FASE 40

Parsers are added from cli._build_parser; handlers are merged into the
HANDLERS registry. Messages in Spanish, deterministic outputs.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional


def add_parsers(sub) -> None:
    """Register the v1.3.0 subparsers on the CLI ``sub`` action."""

    # -- docs (FASE 34) -------------------------------------------------
    p = sub.add_parser("docs", help="Documentación (memorias, cuadros, planos)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    for name in ("variables", "memoria", "tecnica", "specs", "cuadros",
                 "listados", "informe"):
        pd = psub.add_parser(name)
        pd.add_argument("file")
        pd.add_argument("--out", default="",
                        help="Exportar a archivo (md/html/txt/pdf)")
    pm = psub.add_parser("module")
    pm.add_argument("file")
    pm.add_argument("--name", required=True,
                    help="Módulo a documentar (core, architecture, qto...)")
    pm.add_argument("--out", default="")
    pdr = psub.add_parser("drawing-add")
    pdr.add_argument("file")
    pdr.add_argument("--sheet", required=True)
    pdr.add_argument("--size", default="A3", choices=["A0", "A1", "A2", "A3", "A4"])
    pdr.add_argument("--scale", default="1:50")
    pdr.add_argument("--orientation", default="LANDSCAPE",
                     choices=["PORTRAIT", "LANDSCAPE"])
    pdr.add_argument("--view", default="PLAN",
                     choices=["PLAN", "SECTION", "ELEVATION", "DETAIL",
                              "SCHEMATIC", "LAYOUT", "SITE"])
    pdr.add_argument("--level", default="")
    pdr.add_argument("--text", default="", help="Texto anotado en la hoja")
    pdl = psub.add_parser("drawing-list")
    pdl.add_argument("file")
    pdd = psub.add_parser("drawing-delete")
    pdd.add_argument("file")
    pdd.add_argument("--code", required=True)
    pta = psub.add_parser("template-add")
    pta.add_argument("file")
    pta.add_argument("--name", required=True)
    pta.add_argument("--body", required=True,
                     help="Texto con variables {{PROJECT.NAME}}, ...")
    pta.add_argument("--header", default="")
    pta.add_argument("--footer", default="")
    ptr = psub.add_parser("template-render")
    ptr.add_argument("file")
    ptr.add_argument("--name", required=True)
    ptr.add_argument("--out", default="")

    # -- optimize (FASE 35) ------------------------------------------------
    p = sub.add_parser("optimize", help="Motor multiobjetivo (espec 19)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    poc = psub.add_parser("current")
    poc.add_argument("file")
    pop = psub.add_parser("pareto")
    pop.add_argument("file")
    pop.add_argument("--variants", required=True,
                     help="JSON con [{'name','objectives':{...}}, ...]")
    pop.add_argument("--with-current", action="store_true",
                     help="Incluir el proyecto abierto como variante CURRENT")
    poc2 = psub.add_parser("compare")
    poc2.add_argument("file")
    poc2.add_argument("--variants", required=True)
    poc2.add_argument("--a", required=True)
    poc2.add_argument("--b", required=True)

    # -- plugins (FASE 39) ------------------------------------------------
    p = sub.add_parser("plugins", help="Validación, información y andamiaje de plugins")
    psub = p.add_subparsers(dest="subcommand", required=True)
    ppv = psub.add_parser("validate")
    ppv.add_argument("path", help="Archivo .py del plugin externo")
    ppi = psub.add_parser("info")
    ppn = psub.add_parser("new")
    ppn.add_argument("out", help="Archivo a generar (andamiaje)")

    # -- benchmark (FASE 40) --------------------------------------------
    p = sub.add_parser("benchmark", help="Rendimiento (espec 86-87)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pbr2 = psub.add_parser("run")
    pbr2.add_argument("file")
    pbr2.add_argument("--iterations", type=int, default=0,
                      help="Multiplicador de iteraciones (0 = por defecto)")
    pbc2 = psub.add_parser("caches")

    # -- gui (FASE 90, espec 90-93) -------------------------------------
    p = sub.add_parser("gui", help="Interfaz gráfica (FASE 90: explorador, "
                                   "lienzo, propiedades, buscador, estados)")
    p.add_argument("file", nargs="?", default="",
                   help="Archivo .arqgen a abrir (opcional; por defecto demo)")
    p.add_argument("--demo", action="store_true",
                   help="Abrir siempre el proyecto de demostración")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------

def _write_out(text: str, out: str, fmt: str, context) -> None:
    if not out:
        print(text)
        return
    from services.documentation_service import DocumentationService
    service = DocumentationService(context)
    path = service.export_document(text, out, fmt)
    print(f"Documento escrito: {path}")


def _out_format(out: str) -> str:
    ext = os.path.splitext(out)[1].lower().lstrip(".")
    return ext or "md"


def cmd_docs_doc(kind: str):
    def handler(application, args) -> int:
        from services.documentation_service import DocumentationService
        context = application.open_project(args.file)
        try:
            service = DocumentationService(context)
            text = {
                "memoria": service.generate_memoria,
                "tecnica": service.generate_tecnica,
                "specs": service.generate_especificaciones,
                "cuadros": service.generate_cuadros,
                "listados": service.generate_listados,
                "informe": service.generate_informe,
            }[kind]()
            _write_out(text, args.out, _out_format(args.out), context)
        finally:
            context.close()
        return 0
    return handler


def cmd_docs_variables(application, args) -> int:
    from services.documentation_service import DocumentationService
    context = application.open_project(args.file)
    try:
        for name in sorted(DocumentationService(context).variables()):
            print(f"  {{{{{name}}}}}")
    finally:
        context.close()
    return 0


def cmd_docs_module(application, args) -> int:
    from services.documentation_service import DocumentationService
    context = application.open_project(args.file)
    try:
        text = DocumentationService(context).module_docs(args.name)
        _write_out(text, args.out, _out_format(args.out), context)
    finally:
        context.close()
    return 0


def cmd_docs_drawing_add(application, args) -> int:
    from services.documentation_service import DocumentationService
    context = application.open_project(args.file)
    context.user = args.user
    try:
        service = DocumentationService(context)
        drawing = service.create_drawing(
            args.sheet, sheet_size=args.size, scale=args.scale,
            orientation=args.orientation, view=args.view,
            level_ref=args.level)
        if args.text:
            service.add_drawing_element(drawing.code, "TEXT",
                                        {"text": args.text})
        context.commit()
        print(f"Plano creado: {drawing.code} hoja {drawing.sheet} "
              f"({drawing.sheet_size}, {drawing.scale}, {drawing.view})")
        print(f"  Elementos: {len(drawing.annotations)}")
    finally:
        context.commit()
        context.close()
    return 0


def cmd_docs_drawing_list(application, args) -> int:
    from services.documentation_service import DocumentationService
    context = application.open_project(args.file)
    try:
        rows = [[d["code"], d["sheet"], d["size"], d["scale"], d["view"],
                 str(d["elements"])]
                for d in DocumentationService(context).list_drawings()]
        from app.cli import _print_table
        _print_table(rows, ["Código", "Hoja", "Formato", "Escala", "Vista", "Elem."])
        if not rows:
            print("(sin planos)")
    finally:
        context.close()
    return 0


def cmd_docs_drawing_delete(application, args) -> int:
    from services.documentation_service import DocumentationService
    context = application.open_project(args.file)
    context.user = args.user
    try:
        DocumentationService(context).delete_drawing(args.code)
        context.commit()
        print(f"Plano eliminado: {args.code}")
    finally:
        context.commit()
        context.close()
    return 0


def cmd_docs_template_add(application, args) -> int:
    from services.documentation_service import DocumentationService
    context = application.open_project(args.file)
    context.user = args.user
    try:
        template = DocumentationService(context).create_template(
            args.name, args.body, headers=args.header, footers=args.footer)
        context.commit()
        print(f"Plantilla creada: {template.code} ({template.name})")
        print(f"  Variables referenciadas: "
              f"{', '.join(template.placeholder_names()) or '(ninguna)'}")
    finally:
        context.commit()
        context.close()
    return 0


def cmd_docs_template_render(application, args) -> int:
    from services.documentation_service import DocumentationService
    context = application.open_project(args.file)
    try:
        text = DocumentationService(context).render_template(args.name)
        _write_out(text, args.out, _out_format(args.out), context)
    finally:
        context.close()
    return 0


def cmd_optimize_current(application, args) -> int:
    from engines.optimization_engine import DIRECTIONS
    from services.optimization_service import OptimizationService
    context = application.open_project(args.file)
    try:
        variant = OptimizationService(context).evaluate_current()
        print(f"Objetivos del proyecto ({variant.name}):")
        for obj, value in variant.objectives.items():
            print(f"  {obj:<14} {value:>14,.4f}  ({DIRECTIONS[obj]})")
    finally:
        context.close()
    return 0


def cmd_optimize_pareto(application, args) -> int:
    from services.optimization_service import OptimizationService
    context = application.open_project(args.file)
    try:
        service = OptimizationService(context)
        variants = service.load_variants(args.variants,
                                         with_current=args.with_current)
        report = service.pareto(variants)
        print(f"Variantes evaluadas: {', '.join(report['variants'])}")
        print(f"Frente de Pareto  : {', '.join(report['pareto_front'])}")
        if report["dominated_by"]:
            print("Dominadas por:")
            for name, by in sorted(report["dominated_by"].items()):
                print(f"  {name} ← {by}")
        print(f"Direcciones: {report['objectives']}")
    finally:
        context.close()
    return 0


def cmd_optimize_compare(application, args) -> int:
    from services.optimization_service import OptimizationService
    context = application.open_project(args.file)
    try:
        service = OptimizationService(context)
        variants = service.load_variants(args.variants)
        by_name = {v.name: v for v in variants}
        if args.a not in by_name or args.b not in by_name:
            print(f"ERROR [ARQ-OPT-004] Variantes disponibles: "
                  f"{', '.join(sorted(by_name))}")
            return 1
        report = service.compare(by_name[args.a], by_name[args.b])
        print(f"Comparación {report['a']} vs {report['b']}:")
        for obj, row in report["comparison"].items():
            print(f"  {obj:<14} A={row['a']:>14,.4f}  B={row['b']:>14,.4f}  "
                  f"Δ={row['delta']:>14,.4f}  ({row['direction']})")
        print(f"A domina a B: {report['a_dominates_b']} | "
              f"B domina a A: {report['b_dominates_a']}")
    finally:
        context.close()
    return 0


def cmd_audit_show(application, args) -> int:
    context = application.open_project(args.file)
    try:
        rows = [[e["timestamp"][:19], e["user"], e["command"], e["object_type"],
                 e["object_id"][:8], e["result"]]
                for e in context.audit_repo.query(
                    limit=args.limit, object_id=args.object,
                    object_type=getattr(args, "object_type", "") or "",
                    user=args.user_filter, command=args.command_filter,
                    since=args.since, until=args.until)]
        from app.cli import _print_table
        _print_table(rows, ["Fecha", "Usuario", "Comando", "Tipo",
                            "Objeto", "Resultado"])
        if not rows:
            print("(sin registros de auditoría)")
    finally:
        context.close()
    return 0


def cmd_audit_stats(application, args) -> int:
    context = application.open_project(args.file)
    try:
        stats = context.audit_repo.stats()
        print(f"Total de eventos de auditoría: {stats['total']}")
        for key, label in (("by_command", "Por comando"),
                           ("by_object_type", "Por tipo de objeto"),
                           ("by_user", "Por usuario"),
                           ("by_result", "Por resultado")):
            print(f"{label}:")
            for name, count in stats[key].items():
                print(f"  {name:<28} {count:>8}")
    finally:
        context.close()
    return 0


def cmd_audit_export(application, args) -> int:
    context = application.open_project(args.file)
    try:
        events = context.audit_repo.iter_all()
        if args.format == "json":
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(events, handle, indent=2, ensure_ascii=False,
                          sort_keys=True, default=str)
        else:
            import csv
            with open(args.out, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["timestamp", "user", "object_id",
                                 "object_type", "command", "result",
                                 "reason", "old_value", "new_value"])
                for e in events:
                    writer.writerow([
                        e["timestamp"], e["user"], e["object_id"],
                        e["object_type"], e["command"], e["result"],
                        e["reason"],
                        json.dumps(e["old_value"], ensure_ascii=False)
                        if e["old_value"] is not None else "",
                        json.dumps(e["new_value"], ensure_ascii=False)
                        if e["new_value"] is not None else ""])
        print(f"Auditoría exportada ({len(events)} eventos): {args.out}")
    finally:
        context.close()
    return 0


def cmd_version_compare(application, args) -> int:
    from services.version_service import VersionService
    context = application.open_project(args.file)
    try:
        diff = VersionService(context).compare_by_numbers(args.a, args.b)
        print(f"Comparación versión #{args.a} vs #{args.b}:")
        print(f"  Tipos modificados: "
              f"{', '.join(diff['changed_types']) or '(ninguno)'}")
        for entity_type in diff["changed_types"]:
            d = diff["types"][entity_type]
            print(f"  {entity_type}: +{len(d['added'])} / -{len(d['removed'])}")
            for code in d["added"][:10]:
                print(f"    + {code}")
            for code in d["removed"][:10]:
                print(f"    - {code}")
    finally:
        context.close()
    return 0


def cmd_version_export(application, args) -> int:
    from services.version_service import VersionService
    context = application.open_project(args.file)
    try:
        path = VersionService(context).export_version(args.number, args.out)
        print(f"Snapshot de la versión #{args.number} exportado: {path}")
    finally:
        context.close()
    return 0


def cmd_version_branch(application, args) -> int:
    from services.version_service import VersionService
    context = application.open_project(args.file)
    try:
        info = VersionService(context).branch_version(args.number, args.out)
        print(f"Rama creada desde la versión #{info['version']}: {info['path']}")
        print(f"  Proyecto: {info['project']}")
    finally:
        context.close()
    return 0


def cmd_backup_autosave(application, args) -> int:
    from persistence.backup.service import BackupService
    info = BackupService(args.dir).autosave(args.file)
    print(f"Autosave creado: {info.path}")
    print(f"  Integridad: {info.integrity}")
    return 0


def cmd_backup_incremental(application, args) -> int:
    from persistence.backup.service import BackupService
    result = BackupService(args.dir).create_incremental_backup(args.file)
    if result["changed"]:
        print(f"Backup incremental creado: {result['backup']}")
        print(f"  SHA-256   : {result['sha256'][:16]}…")
        print(f"  Integridad: {result['integrity']}")
    else:
        print("Sin cambios desde el último incremental (no se copia nada).")
        print(f"  SHA-256   : {result['sha256'][:16]}…")
    return 0


def cmd_backup_journal(application, args) -> int:
    from persistence.backup.service import BackupService
    status = BackupService(default_backup_dir()).journal_status(args.file)
    print("Estado del journal (WAL):")
    print(f"  Modo            : {status['journal_mode']}")
    print(f"  WAL (bytes)     : {status['wal_bytes']}")
    print(f"  Páginas en WAL  : {status['wal_log_pages']}")
    print(f"  Páginas totales : {status['page_count']}")
    return 0


def cmd_backup_checkpoint(application, args) -> int:
    from persistence.backup.service import BackupService
    result = BackupService(default_backup_dir()).checkpoint(args.file,
                                                            mode=args.mode)
    print(f"Checkpoint {result['mode']} ejecutado: "
          f"{result['checkpointed_pages']} páginas consolidadas")
    return 0


def cmd_backup_verify(application, args) -> int:
    from persistence.backup.service import BackupService
    results = BackupService(args.dir).verify_all()
    rows = [[os.path.basename(r["path"]), f"{r['size_bytes']:,}",
             r["integrity"]] for r in results]
    from app.cli import _print_table
    _print_table(rows, ["Backup", "Tamaño", "Integridad"])
    if not results:
        print("(sin backups que verificar)")
    else:
        bad = [r for r in results if r["integrity"] != "ok"]
        print(f"{len(results)} verificados, {len(bad)} con problemas")
    return 0


def cmd_backup_recover(application, args) -> int:
    from persistence.backup.service import BackupService
    result = BackupService(args.dir).recover(args.file, force=args.force)
    if result["recovered"]:
        print(f"Proyecto recuperado desde: {result['from']}")
        print(f"  Integridad: {result['integrity']}")
    else:
        print(f"No fue necesario recuperar ({result['reason']}).")
    return 0


def cmd_plugins_validate(application, args) -> int:
    from plugins.plugin_api import validate_plugin_file
    result = validate_plugin_file(args.path)
    print(f"Validación de plugin: {args.path}")
    for warning in result["warnings"]:
        print(f"  AVISO: {warning}")
    for error in result["errors"]:
        print(f"  ERROR: {error}")
    if result["ok"]:
        print(f"  OK: plugin_id={result['plugin_id']} v{result['version']}")
        return 0
    return 1


def cmd_plugins_info(application, args) -> int:
    from app.bootstrap import bootstrap
    _, loader = bootstrap(args)
    rows = []
    for info in loader.info():
        if info["status"] != "LOADED":
            rows.append([info["source"], "ERROR", "", info["error"]])
            continue
        declarations = ", ".join(
            f"{k}={len(v)}" for k, v in info.items()
            if isinstance(v, list) and k not in ("dependencies",))
        rows.append([info["plugin_id"], f"v{info['version']}",
                     info["api_version"], declarations])
    from app.cli import _print_table
    _print_table(rows, ["Plugin", "Versión", "API", "Declaraciones"])
    return 0


def cmd_plugins_new(application, args) -> int:
    from plugins.plugin_api import scaffold_plugin
    path = scaffold_plugin(args.out)
    print(f"Plantilla de plugin generada: {path}")
    print("  Edítala y colócala en plugins/external para cargarla.")
    return 0


def cmd_benchmark_run(application, args) -> int:
    from app.benchmark import format_results, run_benchmarks
    context = application.open_project(args.file)
    try:
        multiplier = max(args.iterations, 0)
        iterations = None
        if multiplier:
            iterations = {"geometry_area": 200 * multiplier,
                          "spatial_adjacency": 20 * multiplier,
                          "qto_compute_all": 3 * multiplier,
                          "budget_compute": 2 * multiplier,
                          "optimization_current": 5 * multiplier,
                          "documentation_memoria": 5 * multiplier,
                          "clash_detection": 3 * multiplier,
                          "export_json": 5 * multiplier}
        results = run_benchmarks(context, iterations)
        print(format_results(results))
    finally:
        context.close()
    return 0


def cmd_benchmark_caches(application, args) -> int:
    from app.benchmark import cache_inventory
    rows = [[c["cache"], c["layer"], c["contents"], c["invalidation"]]
            for c in cache_inventory()]
    from app.cli import _print_table
    _print_table(rows, ["Caché", "Capa", "Contenido", "Invalidación"])
    return 0


def cmd_gui(application, args) -> int:
    """FASE 90: lanza la interfaz gráfica (spec 90-93)."""
    from ui.app_window import launch
    return launch(args.file or "", demo=args.demo,
                  width=args.width, height=args.height)


HANDLERS_13 = {
    ("docs", "variables"): cmd_docs_variables,
    ("docs", "memoria"): cmd_docs_doc("memoria"),
    ("docs", "tecnica"): cmd_docs_doc("tecnica"),
    ("docs", "specs"): cmd_docs_doc("specs"),
    ("docs", "cuadros"): cmd_docs_doc("cuadros"),
    ("docs", "listados"): cmd_docs_doc("listados"),
    ("docs", "informe"): cmd_docs_doc("informe"),
    ("docs", "module"): cmd_docs_module,
    ("docs", "drawing-add"): cmd_docs_drawing_add,
    ("docs", "drawing-list"): cmd_docs_drawing_list,
    ("docs", "drawing-delete"): cmd_docs_drawing_delete,
    ("docs", "template-add"): cmd_docs_template_add,
    ("docs", "template-render"): cmd_docs_template_render,
    ("optimize", "current"): cmd_optimize_current,
    ("optimize", "pareto"): cmd_optimize_pareto,
    ("optimize", "compare"): cmd_optimize_compare,
    ("audit", "show"): cmd_audit_show,
    ("audit", "stats"): cmd_audit_stats,
    ("audit", "export"): cmd_audit_export,
    ("version", "compare"): cmd_version_compare,
    ("version", "export"): cmd_version_export,
    ("version", "branch"): cmd_version_branch,
    ("backup", "autosave"): cmd_backup_autosave,
    ("backup", "incremental"): cmd_backup_incremental,
    ("backup", "journal"): cmd_backup_journal,
    ("backup", "checkpoint"): cmd_backup_checkpoint,
    ("backup", "verify"): cmd_backup_verify,
    ("backup", "recover"): cmd_backup_recover,
    ("plugins", "validate"): cmd_plugins_validate,
    ("plugins", "info"): cmd_plugins_info,
    ("plugins", "new"): cmd_plugins_new,
    ("benchmark", "run"): cmd_benchmark_run,
    ("benchmark", "caches"): cmd_benchmark_caches,
    (None, "gui"): cmd_gui,
}

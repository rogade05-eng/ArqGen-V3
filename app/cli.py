"""ARQ GEN CLI — professional command line interface (spec sections 90-92, 101).

All user-facing messages in Spanish; exit code 0 on success, 1 on
controlled failure, 2 on unexpected error. Every command is offline.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from app.lifecycle import setup_logging, get_logger
from app.paths import default_backup_dir, default_log_dir

PROGRAM = "ARQ_GEN"


def _print_error(code: str, message: str, suggestion: str = "") -> None:
    print(f"ERROR [{code}] {message}")
    if suggestion:
        print(f"  Sugerencia: {suggestion}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="ARQ GEN — Sistema profesional offline de arquitectura, ingeniería, "
                    "construcción y seguridad (fase P0 + Arquitectura).")
    parser.add_argument("--log-dir", default=default_log_dir(),
                        help="Directorio de logs (por defecto ./logs)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Nivel de log en consola")
    parser.add_argument("--user", default="local",
                        help="Usuario para la auditoría")
    sub = parser.add_subparsers(dest="command")

    # -- project --------------------------------------------------------
    p = sub.add_parser("project", help="Gestión de proyectos")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pc = psub.add_parser("create", help="Crear proyecto nuevo")
    pc.add_argument("file")
    pc.add_argument("--name", required=True)
    pc.add_argument("--client", default="")
    pc.add_argument("--address", default="")
    pc.add_argument("--description", default="")
    pc.add_argument("--ruleset", default="international_v1")
    pc.add_argument("--currency", default="CUP")
    pi = psub.add_parser("info", help="Información del proyecto")
    pi.add_argument("file")

    # -- level ------------------------------------------------------------
    p = sub.add_parser("level", help="Gestión de niveles")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pl = psub.add_parser("add")
    pl.add_argument("file")
    pl.add_argument("--name", required=True)
    pl.add_argument("--elevation", type=float, default=0.0)
    pl.add_argument("--height", type=float, default=3.0)
    pll = psub.add_parser("list")
    pll.add_argument("file")

    # -- zone ---------------------------------------------------------------
    p = sub.add_parser("zone", help="Gestión de zonas")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pz = psub.add_parser("add")
    pz.add_argument("file")
    pz.add_argument("--name", required=True)
    pz.add_argument("--kind", required=True,
                    choices=["PUBLIC", "PRIVATE", "SERVICE", "TECHNICAL",
                             "CIRCULATION", "EMERGENCY", "EXTERIOR"])
    pzl = psub.add_parser("list")
    pzl.add_argument("file")

    # -- space ----------------------------------------------------------------
    p = sub.add_parser("space", help="Gestión de locales")
    psub = p.add_subparsers(dest="subcommand", required=True)
    ps = psub.add_parser("add")
    ps.add_argument("file")
    ps.add_argument("--level", required=True)
    ps.add_argument("--name", required=True)
    ps.add_argument("--type", default="ROOM")
    ps.add_argument("--polygon", nargs="+", required=True,
                    help="Vértices x,y (m): 0,0 4,0 4,3 0,3")
    ps.add_argument("--zone", default="", help="Código de zona a asignar")
    psl = psub.add_parser("list")
    psl.add_argument("file")

    # -- wall -------------------------------------------------------------------
    p = sub.add_parser("wall", help="Gestión de muros")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pw = psub.add_parser("add")
    pw.add_argument("file")
    pw.add_argument("--level", required=True)
    pw.add_argument("--start", required=True, help="x,y en metros")
    pw.add_argument("--end", required=True, help="x,y en metros")
    pw.add_argument("--thickness", type=float, default=0.2)
    pw.add_argument("--height", type=float, default=None)
    pwl = psub.add_parser("list")
    pwl.add_argument("file")
    pwm = psub.add_parser("move")
    pwm.add_argument("file")
    pwm.add_argument("--wall", required=True, help="Código del muro")
    pwm.add_argument("--start", required=True)
    pwm.add_argument("--end", required=True)

    # -- door / window -------------------------------------------------------------
    for name, help_text in (("door", "Puertas"), ("window", "Ventanas")):
        p = sub.add_parser(name, help=help_text)
        psub = p.add_subparsers(dest="subcommand", required=True)
        pa = psub.add_parser("add")
        pa.add_argument("file")
        pa.add_argument("--wall", required=True, help="Código del muro")
        pa.add_argument("--width", type=float, required=True)
        pa.add_argument("--height", type=float, required=True)
        pa.add_argument("--offset", type=float, default=0.0)
        pa.add_argument("--sill", type=float, default=0.0 if name == "door" else 1.0)
        pal = psub.add_parser("list")
        pal.add_argument("file")

    # -- undo / redo ---------------------------------------------------------------
    p = sub.add_parser("undo", help="Deshacer la última operación")
    p.add_argument("file")
    p = sub.add_parser("redo", help="Rehacer la última operación deshecha")
    p.add_argument("file")

    # -- relationships ---------------------------------------------------------------
    p = sub.add_parser("relationships", help="Relaciones espaciales")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pr = psub.add_parser("recompute", help="Recalcular adyacencias por geometría")
    pr.add_argument("file")
    prl = psub.add_parser("report", help="Informe de adyacencias y DNA")
    prl.add_argument("file")

    # -- validate ----------------------------------------------------------------------
    p = sub.add_parser("validate", help="Validar el proyecto completo")
    p.add_argument("file")

    # -- instalar (v3.8.0) ------------------------------------------------------
    p = sub.add_parser(
        "instalar",
        help="Generar redes de instalaciones adaptadas a los locales "
             "(mismo motor que los asistentes)")
    p.add_argument("file")
    p.add_argument("modulos", nargs="*",
                   help="Módulos: Eléctrica, Sanitaria, "
                        "'Ventilación mecánica / A/C', "
                        "'Protección contra incendios', "
                        "'Comunicaciones (voz y datos)', Gas, "
                        "'Energía solar'")
    p.add_argument("--todo", action="store_true",
                   help="Usar TODOS los módulos disponibles")

    # -- qto -----------------------------------------------------------------------------
    p = sub.add_parser("qto", help="Cómputo de cantidades")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pq = psub.add_parser("compute")
    pq.add_argument("file")
    pq.add_argument("--mode", default="BALANCED", choices=["FAST", "BALANCED", "DEEP"])
    pqs = psub.add_parser("show")
    pqs.add_argument("file")
    pqs.add_argument("--stale-only", action="store_true")

    # -- resources / prices -----------------------------------------------------------------
    p = sub.add_parser("resource", help="Catálogo de recursos")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pra = psub.add_parser("add")
    pra.add_argument("file")
    pra.add_argument("--code", required=True)
    pra.add_argument("--name", required=True)
    pra.add_argument("--type", required=True,
                    choices=["MATERIAL", "LABOR", "EQUIPMENT", "CONSUMABLE", "TRANSPORT", "OTHER"])
    pra.add_argument("--unit", required=True)
    pra.add_argument("--category", default="")
    prl = psub.add_parser("list")
    prl.add_argument("file")
    p = sub.add_parser("price", help="Precios con histórico")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pp = psub.add_parser("set")
    pp.add_argument("file")
    pp.add_argument("--resource", required=True)
    pp.add_argument("--price", type=float, required=True)
    pp.add_argument("--list", default="GENERAL", dest="price_list")
    pp.add_argument("--date", default="", help="YYYY-MM-DD (vigencia desde)")
    pp.add_argument("--currency", default="CUP")
    pph = psub.add_parser("history")
    pph.add_argument("file")
    pph.add_argument("--resource", required=True)
    pph.add_argument("--list", default="GENERAL", dest="price_list")

    # -- budget ---------------------------------------------------------------------------------
    p = sub.add_parser("budget", help="Presupuesto")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pb = psub.add_parser("compute")
    pb.add_argument("file")
    pb.add_argument("--template", default="residential_v1")
    pb.add_argument("--name", default="")
    pbs = psub.add_parser("show")
    pbs.add_argument("file")

    # -- export / import ---------------------------------------------------------------------------
    p = sub.add_parser("export", help="Exportar el proyecto")
    p.add_argument("file")
    p.add_argument("--format", required=True,
                   choices=["dxf", "json", "xlsx", "csv", "ifc", "svg"])
    p.add_argument("--out", required=True)
    p.add_argument("--level", default="", help="Filtro de nivel para DXF")
    p.add_argument("--r12", action="store_true",
                   help="DXF R12 ASCII (máxima compatibilidad: CAD "
                        "antiguo, CNC y visores)")
    p.add_argument("--table", default="quantities", choices=["quantities", "budget"],
                   help="Tabla para CSV")
    p = sub.add_parser("import", help="Importar instantánea JSON")
    p.add_argument("file")
    p.add_argument("--out", required=True, help="Archivo nuevo .arqgen")
    p.add_argument("--approve", action="store_true",
                   help="Sin esta bandera solo muestra la vista previa")

    # -- versions -------------------------------------------------------------------------------------
    p = sub.add_parser("version", help="Versionado del proyecto")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pv = psub.add_parser("save")
    pv.add_argument("file")
    pv.add_argument("--author", default="local")
    pv.add_argument("--description", default="")
    pvl = psub.add_parser("list")
    pvl.add_argument("file")
    pvr = psub.add_parser("restore")
    pvr.add_argument("file")
    pvr.add_argument("--number", type=int, required=True)
    # FASE 37: compare / export / branch
    pvc = psub.add_parser("compare")
    pvc.add_argument("file")
    pvc.add_argument("--a", type=int, required=True)
    pvc.add_argument("--b", type=int, required=True)
    pve = psub.add_parser("export")
    pve.add_argument("file")
    pve.add_argument("--number", type=int, required=True)
    pve.add_argument("--out", required=True)
    pvb = psub.add_parser("branch")
    pvb.add_argument("file")
    pvb.add_argument("--number", type=int, required=True)
    pvb.add_argument("--out", required=True, help="Archivo nuevo .arqgen")

    # -- backup ------------------------------------------------------------------------------------------
    p = sub.add_parser("backup", help="Backups")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pbc = psub.add_parser("create")
    pbc.add_argument("file")
    pbc.add_argument("--dir", default=default_backup_dir())
    pbl = psub.add_parser("list")
    pbl.add_argument("file")
    pbl.add_argument("--dir", default=default_backup_dir())
    pbr = psub.add_parser("restore")
    pbr.add_argument("file")
    pbr.add_argument("--backup", required=True)
    pbr.add_argument("--dir", default=default_backup_dir())
    # FASE 38: autosave / incremental / journal / checkpoint / verify / recover
    pba = psub.add_parser("autosave")
    pba.add_argument("file")
    pba.add_argument("--dir", default=default_backup_dir())
    pbi = psub.add_parser("incremental")
    pbi.add_argument("file")
    pbi.add_argument("--dir", default=default_backup_dir())
    pbj = psub.add_parser("journal")
    pbj.add_argument("file")
    pbk = psub.add_parser("checkpoint")
    pbk.add_argument("file")
    pbk.add_argument("--mode", default="TRUNCATE",
                     choices=["PASSIVE", "FULL", "RESTART", "TRUNCATE"])
    pbv = psub.add_parser("verify")
    pbv.add_argument("file")
    pbv.add_argument("--dir", default=default_backup_dir())
    pbr2 = psub.add_parser("recover")
    pbr2.add_argument("file")
    pbr2.add_argument("--dir", default=default_backup_dir())
    pbr2.add_argument("--force", action="store_true")

    # -- audit / events --------------------------------------------------------------------------------------
    p = sub.add_parser("audit", help="Auditoría")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pau = psub.add_parser("show")
    pau.add_argument("file")
    pau.add_argument("--limit", type=int, default=20)
    # FASE 36: filtros de auditoría (espec 71)
    pau.add_argument("--object", default="", help="Filtrar por object_id")
    pau.add_argument("--type", dest="object_type", default="",
                     help="Filtrar por tipo de objeto (WALL, NODE...)")
    pau.add_argument("--user", dest="user_filter", default="")
    pau.add_argument("--command", dest="command_filter", default="",
                     help="Subcadena de comando")
    pau.add_argument("--since", default="", help="Fecha ISO inicial")
    pau.add_argument("--until", default="", help="Fecha ISO final")
    pas = psub.add_parser("stats")
    pas.add_argument("file")
    pae = psub.add_parser("export")
    pae.add_argument("file")
    pae.add_argument("--out", required=True)
    pae.add_argument("--format", default="csv", choices=["csv", "json"])
    p = sub.add_parser("events", help="Historial de eventos")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pev = psub.add_parser("show")
    pev.add_argument("file")
    pev.add_argument("--limit", type=int, default=20)

    # -- installations: networks / nodes / links (spec 24-26) ----------------
    p = sub.add_parser("net", help="Redes de instalaciones")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pna = psub.add_parser("add")
    pna.add_argument("file")
    pna.add_argument("--name", required=True)
    pna.add_argument("--system", required=True,
                     choices=["POWER", "LIGHTING", "EMERGENCY", "COLD_WATER", "HOT_WATER",
                              "SANITARY_DRAINAGE", "STORMWATER", "PUMPING", "STORAGE",
                              "HVAC_SUPPLY", "HVAC_RETURN", "EXHAUST", "GAS", "TELECOM"])
    pna.add_argument("--description", default="")
    pnl = psub.add_parser("list")
    pnl.add_argument("file")
    pns = psub.add_parser("show")
    pns.add_argument("file")
    pns.add_argument("--network", required=True, help="Código o nombre de la red")
    pnt = psub.add_parser("trace")
    pnt.add_argument("file")
    pnt.add_argument("--node", required=True, help="Código del nodo")
    pnp = psub.add_parser("path")
    pnp.add_argument("file")
    pnp.add_argument("--from", dest="from_ref", required=True)
    pnp.add_argument("--to", dest="to_ref", required=True)
    pnp.add_argument("--weight", default="length", choices=["length", "hops", "cost"])
    pnv = psub.add_parser("validate")
    pnv.add_argument("file")
    pnv.add_argument("--network", required=True)
    pnd = psub.add_parser("deadends")
    pnd.add_argument("file")
    pnd.add_argument("--network", required=True)

    p = sub.add_parser("node", help="Nodos de instalaciones (equipos, terminales, uniones)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pnoa = psub.add_parser("add")
    pnoa.add_argument("file")
    pnoa.add_argument("--network", required=True)
    pnoa.add_argument("--kind", required=True,
                      help="SOURCE, JUNCTION, OUTFALL, PANEL, PROTECTION, OUTLET, SWITCH, "
                           "LUMINAIRE, GROUNDING, METER, PUMP, TANK, VALVE, FIXTURE, APPLIANCE, "
                           "ROOF_DRAIN, AHU, FCU, SPLIT, DIFFUSER, GRILLE, FAN, EXHAUST, RACK, DEVICE_LV")
    pnoa.add_argument("--name", default="")
    pnoa.add_argument("--x", type=float, default=0.0)
    pnoa.add_argument("--y", type=float, default=0.0)
    pnoa.add_argument("--elevation", type=float, default=0.0, help="Cota del nodo en m")
    pnoa.add_argument("--level", default="")
    pnoa.add_argument("--space", default="", help="Código o nombre del local")
    pnoa.add_argument("--attr", nargs="*", default=[], help="Atributos k=v (power_w=100 ...)")
    pnol = psub.add_parser("list")
    pnol.add_argument("file")
    pnol.add_argument("--network", default="")
    pnom = psub.add_parser("move")
    pnom.add_argument("file")
    pnom.add_argument("--node", required=True)
    pnom.add_argument("--x", type=float, required=True)
    pnom.add_argument("--y", type=float, required=True)

    p = sub.add_parser("link", help="Tramos entre nodos (canalización, tubería, ducto)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pla = psub.add_parser("add")
    pla.add_argument("file")
    pla.add_argument("--network", required=True)
    pla.add_argument("--from", dest="from_ref", required=True)
    pla.add_argument("--to", dest="to_ref", required=True)
    pla.add_argument("--kind", default="CONDUIT",
                     choices=["CONDUIT", "CABLE_TRAY", "CONDUCTOR_RUN", "PIPE",
                              "DRAIN_PIPE", "DUCT"])
    pla.add_argument("--name", default="")
    pla.add_argument("--length", type=float, default=0.0,
                     help="0 = calcular por routing ortogonal")
    pla.add_argument("--diameter", type=float, default=0.0, help="Diámetro en mm")
    pla.add_argument("--slope", type=float, default=0.0, help="Pendiente en %%")
    pla.add_argument("--material", default="")
    pla.add_argument("--routing", default="ORTHO", choices=["ORTHO", "STRAIGHT"])
    pla.add_argument("--attr", nargs="*", default=[], help="Atributos k=v (conductors=3 ...)")
    pll = psub.add_parser("list")
    pll.add_argument("file")
    pll.add_argument("--network", required=True)
    plr = psub.add_parser("remove")
    plr.add_argument("file")
    plr.add_argument("--link", required=True)

    # -- installations: discipline engines (spec 27-29) --------------------------
    p = sub.add_parser("elec", help="Motor eléctrico")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pec = psub.add_parser("check")
    pec.add_argument("file")
    pec.add_argument("--circuit", required=True, help="Código del nodo PROTECTION")
    pes = psub.add_parser("summary")
    pes.add_argument("file")
    pes.add_argument("--panel", required=True, help="Código del nodo PANEL")
    peb = psub.add_parser("balance")
    peb.add_argument("file")
    peb.add_argument("--panel", required=True)

    p = sub.add_parser("san", help="Motor sanitario")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pss = psub.add_parser("size")
    pss.add_argument("file")
    pss.add_argument("--network", required=True)

    p = sub.add_parser("hvac", help="Motor HVAC")
    psub = p.add_subparsers(dest="subcommand", required=True)
    phl = psub.add_parser("load")
    phl.add_argument("file")
    phl.add_argument("--space", required=True, help="Código o nombre del local")
    phls = psub.add_parser("loads")
    phls.add_argument("file")
    phd = psub.add_parser("duct")
    phd.add_argument("file")
    phd.add_argument("--flow", type=float, required=True, help="Caudal en m3/h")
    phd.add_argument("--kind", default="BRANCH", choices=["MAIN", "BRANCH", "RETURN"])
    phd.add_argument("--shape", default="ROUND", choices=["ROUND", "RECT"])
    phd.add_argument("--v", type=float, default=0.0, help="Velocidad objetivo (m/s)")
    phn = psub.add_parser("size-network")
    phn.add_argument("file")
    phn.add_argument("--network", required=True)

    p = sub.add_parser("plu", help="Motor pluvial (captación, bajantes, colectores)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pls = psub.add_parser("size")
    pls.add_argument("file")
    pls.add_argument("--network", required=True)

    p = sub.add_parser("gas", help="Motor de gas (diámetros y validaciones)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pgs = psub.add_parser("size")
    pgs.add_argument("file")
    pgs.add_argument("--network", required=True)
    pgc = psub.add_parser("check")
    pgc.add_argument("file")
    pgc.add_argument("--network", required=True)

    p = sub.add_parser("tel", help="Motor de telecomunicaciones (canalización, racks, fibra)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pts = psub.add_parser("size")
    pts.add_argument("file")
    pts.add_argument("--network", required=True)

    p = sub.add_parser("struct", help="Motor estructural (secciones, viga, pilar, cercha)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    psm = psub.add_parser("material-add")
    psm.add_argument("file")
    psm.add_argument("--name", required=True)
    psm.add_argument("--kind", default="CONCRETE",
                     choices=["CONCRETE", "STEEL", "MASONRY", "TIMBER"])
    psm.add_argument("--fck", type=float, default=0.0)
    psm.add_argument("--fy", type=float, default=0.0)
    psm.add_argument("--density", type=float, default=0.0)
    pss = psub.add_parser("section-add")
    pss.add_argument("file")
    pss.add_argument("--name", required=True)
    pss.add_argument("--shape", required=True,
                     choices=["RECTANGLE", "CIRCLE", "I_PROFILE"])
    pss.add_argument("--h", type=float, default=0.0)
    pss.add_argument("--b", type=float, default=0.0)
    pss.add_argument("--tw", type=float, default=0.0)
    pss.add_argument("--tf", type=float, default=0.0)
    pss.add_argument("--d", type=float, default=0.0)
    pss.add_argument("--weight", type=float, default=0.0,
                     help="Peso propio kg/m (opcional, si no se calcula)")
    pse = psub.add_parser("element-add")
    pse.add_argument("file")
    pse.add_argument("--kind", required=True,
                     choices=["FOUNDATION", "COLUMN", "BEAM", "SLAB", "WALL",
                              "TRUSS", "BRACE", "CONNECTION", "PLATE", "BOLT", "WELD"])
    pse.add_argument("--name", required=True)
    pse.add_argument("--level", default="")
    pse.add_argument("--material", default="")
    pse.add_argument("--section", default="")
    pse.add_argument("--space", default="")
    pse.add_argument("--start", nargs=2, type=float, default=[0.0, 0.0])
    pse.add_argument("--end", nargs=2, type=float, default=[0.0, 0.0])
    pse.add_argument("--z0", type=float, default=0.0)
    pse.add_argument("--z1", type=float, default=0.0)
    pse.add_argument("--udl", type=float, default=0.0, help="Carga uniforme kN/m")
    pse.add_argument("--point", nargs=2, type=float, action="append", default=[],
                     help="Carga puntual: a_m P_kN (repetible)")
    pse.add_argument("--axial", type=float, default=0.0, help="Carga axial kN")
    pse.add_argument("--support", default="", help="SIMPLE | CANTILEVER | PIN | FIXED")
    psel = psub.add_parser("element-list")
    psel.add_argument("file")
    psel.add_argument("--kind", default="")
    psed = psub.add_parser("element-delete")
    psed.add_argument("file")
    psed.add_argument("--element", required=True)
    psc = psub.add_parser("case-add")
    psc.add_argument("file")
    psc.add_argument("--name", required=True)
    psc.add_argument("--kind", required=True,
                     choices=["DEAD", "LIVE", "WIND", "SEISMIC", "SNOW"])
    psc.add_argument("--factor", type=float, default=1.0)
    psk = psub.add_parser("combo-add")
    psk.add_argument("file")
    psk.add_argument("--name", required=True)
    psk.add_argument("--factors", required=True, help="DEAD=1.35,LIVE=1.5")
    psdf = psub.add_parser("defaults", help="Crear combinaciones ULS/SLS estándar")
    psdf.add_argument("file")
    psa = psub.add_parser("analyze", help="Analizar viga o pilar (spec 34)")
    psa.add_argument("file")
    psa.add_argument("--element", required=True)
    psa.add_argument("--combination", default="")
    pst = psub.add_parser("truss", help="Analizar cercha por método de nudos")
    pst.add_argument("file")
    pst.add_argument("--element", required=True)
    pscc = psub.add_parser("connection-check", help="Pernos y soldadura")
    pscc.add_argument("file")
    pscc.add_argument("--bolts", type=int, required=True)
    pscc.add_argument("--bolt-d", type=float, required=True)
    pscc.add_argument("--weld-length", type=float, required=True)
    pscc.add_argument("--weld-throat", type=float, required=True)
    pscc.add_argument("--demand", type=float, required=True)
    psr = psub.add_parser("report", help="Informe de utilización y acero")
    psr.add_argument("file")

    p = sub.add_parser("sec", help="Seguridad (CCTV, fuego, intrusión, acceso, perímetro)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    psn = psub.add_parser("net", help="Crear red de seguridad")
    psn.add_argument("file")
    psn.add_argument("--name", required=True)
    psn.add_argument("--system", required=True,
                     choices=["CCTV", "FIRE_ALARM", "INTRUSION",
                              "ACCESS_CONTROL", "PERIMETER"])
    psd = psub.add_parser("device-add", help="Añadir dispositivo")
    psd.add_argument("file")
    psd.add_argument("--network", required=True)
    psd.add_argument("--kind", required=True)
    psd.add_argument("--x", type=float, required=True)
    psd.add_argument("--y", type=float, required=True)
    psd.add_argument("--name", default="")
    psd.add_argument("--level", default="")
    psd.add_argument("--space", default="")
    psd.add_argument("--elevation", type=float, default=0.0)
    psd.add_argument("--attr", nargs=2, action="append", default=[],
                     metavar=("CLAVE", "VALOR"))
    pscv = psub.add_parser("coverage", help="Cobertura CCTV y puntos ciegos")
    pscv.add_argument("file")
    pscv.add_argument("--network", required=True)
    pscv.add_argument("--space", default="")
    pscn = psub.add_parser("network", help="Red CCTV: ancho de banda y almacenamiento")
    pscn.add_argument("file")
    pscn.add_argument("--network", required=True)
    pscn.add_argument("--retention", type=float, default=30.0)
    pscb = psub.add_parser("cabling", help="Cableado CCTV por cámara")
    pscb.add_argument("file")
    pscb.add_argument("--network", required=True)
    psfc = psub.add_parser("fire-check", help="Fuego: cobertura, lazo y batería")
    psfc.add_argument("file")
    psfc.add_argument("--network", required=True)
    psfm = psub.add_parser("cause-effect", help="Matriz causa/efecto (spec 44)")
    psfm.add_argument("file")
    psfm.add_argument("--network", required=True)
    psfm.add_argument("--input", required=True, help="Evento: SMOKE_DETECTOR...")
    psfm.add_argument("--var", nargs=2, action="append", default=[],
                      metavar=("CLAVE", "VALOR"))
    psic = psub.add_parser("intrusion-check", help="Intrusión: zonas y panel")
    psic.add_argument("file")
    psic.add_argument("--network", required=True)
    psac = psub.add_parser("access-check", help="Acceso: controladores y alimentación")
    psac.add_argument("file")
    psac.add_argument("--network", required=True)
    pspc = psub.add_parser("perimeter-check", help="Perímetro: sensores y cámaras")
    pspc.add_argument("file")
    pspc.add_argument("--network", required=True)
    psb = psub.add_parser("bom", help="BOM de seguridad (spec 48)")
    psb.add_argument("file")

    p = sub.add_parser("clash", help="Coordinación y detección de interferencias")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pcx = psub.add_parser("run", help="Ejecutar detección (spec 35-36)")
    pcx.add_argument("file")
    pcx.add_argument("--systems", default="", help="Filtro: POWER,CCTV,...")
    pcl = psub.add_parser("list")
    pcl.add_argument("file")
    pcl.add_argument("--status", default="")
    pcl.add_argument("--type", dest="clash_type", default="")
    pcs = psub.add_parser("status", help="Cambiar estado de una interferencia")
    pcs.add_argument("file")
    pcs.add_argument("--clash", required=True)
    pcs.add_argument("--set", required=True, dest="new_status",
                     choices=["OPEN", "REVIEWED", "ACCEPTED", "RESOLVED", "IGNORED"])
    pcs.add_argument("--notes", default="")

    p = sub.add_parser("precons", help="PRECONS III / motor tipo SIECONS (spec 59-60)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    ppr = psub.add_parser("list", help="Listar partidas del ruleset")
    ppr.add_argument("file")
    ppr.add_argument("--ruleset", default="precons_cuba_v1")
    ppr.add_argument("--seccion", default="",
                     help="filtra por código de sección (p. ej. 03)")
    ppr.add_argument("--buscar", default="",
                     help="busca texto en código o descripción")
    ppr.add_argument("--limite", type=int, default=50,
                     help="máximo de renglones a mostrar (0=todos)")
    ppp = psub.add_parser("precio",
                          help="Precio oficial de lista de un renglón (catálogo PRECONS III)")
    ppp.add_argument("file")
    ppp.add_argument("--ruleset", default="precons_iii_rospres_330")
    ppp.add_argument("--item", required=True)
    ppp.add_argument("--quantity", type=float, default=1.0)
    ppa = psub.add_parser("analyze", help="Análisis de precio de una partida")
    ppa.add_argument("file")
    ppa.add_argument("--ruleset", default="precons_cuba_v1")
    ppa.add_argument("--item", required=True)
    ppa.add_argument("--quantity", type=float, required=True)
    ppa.add_argument("--variant", default="BASE")
    ppj = psub.add_parser("project", help="Análisis del proyecto vía QTO")
    ppj.add_argument("file")
    ppj.add_argument("--ruleset", default="precons_cuba_v1")
    ppj.add_argument("--variant", default="BASE")
    ppc = psub.add_parser("compare", help="Comparar variantes de una partida")
    ppc.add_argument("file")
    ppc.add_argument("--ruleset", default="precons_cuba_v1")
    ppc.add_argument("--item", required=True)
    ppc.add_argument("--quantity", type=float, required=True)
    ppc.add_argument("--variants", default="BASE,ECONOMIC,PREMIUM")
    ppi = psub.add_parser("import", help="Importar base externa (JSON con mapa o .xlsx/.csv con autodetección)")
    ppi.add_argument("file")
    ppi.add_argument("--data", required=True, help="JSON externo (partidas) o .xlsx/.csv del catálogo")
    ppi.add_argument("--mapping", default="", help="JSON con el mapa de columnas (obligatorio solo si --data es JSON)")
    ppi.add_argument("--code", default="imported")
    ppi.add_argument("--out", default="")
    ppb = psub.add_parser("budget", help="Presupuesto por catálogo PRECONS III (precios oficiales CUP)")
    ppb.add_argument("file")
    ppb.add_argument("--ruleset", default="precons_iii_rospres_330")
    ppb.add_argument("--add", action="append", default=[],
                     help="añade renglón CODIGO:CANTIDAD (repetible)")
    ppb.add_argument("--set-qty", action="append", default=[],
                     help="fija cantidad CODIGO:CANTIDAD (repetible)")
    ppb.add_argument("--remove", action="append", default=[],
                     help="quita renglón CODIGO (repetible)")
    ppb.add_argument("--clear", action="store_true",
                     help="vacía el presupuesto")
    ppb.add_argument("--show", action="store_true", help="muestra el presupuesto")
    ppb.add_argument("--export-csv", default="", help="exporta CSV del presupuesto")
    ppb.add_argument("--export-pdf", default="", help="exporta PDF del presupuesto")
    ppb.add_argument("--chart-png", default="", help="gráfico de barras por sección (PNG)")
    pcf = psub.add_parser("certificar",
                          help="Certifica la integridad del catálogo PRECONS III embebido "
                               "(recuentos oficiales, unicidad, desglose y SHA256)")
    pcf.add_argument("--ruleset", default="precons_iii_rospres_330")

    p = sub.add_parser("detalles",
                       help="Biblioteca de detalles constructivos por "
                            "ediciones regionales (no requiere proyecto)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pdr = psub.add_parser("regiones",
                          help="Ediciones regionales instaladas")
    pdl = psub.add_parser("list", help="Listar detalles de la biblioteca")
    pdl.add_argument("--region", default="base",
                     help="edición regional (base = biblioteca universal)")
    pdl.add_argument("--categoria", default="",
                     help="filtra por categoría (cimentaciones, muros…)")
    pdl.add_argument("--buscar", default="",
                     help="busca texto sin acentos en la ficha")
    pdl.add_argument("--limite", type=int, default=50,
                     help="máximo de renglones a mostrar (0=todos)")
    pdv = psub.add_parser("ver", help="Ficha completa de un detalle")
    pdv.add_argument("id", help="id del detalle (p. ej. muros/muro_confinado_block14)")
    pdv.add_argument("--region", default="base")
    pds = psub.add_parser("svg",
                          help="Exportar el esquema SVG acotado del detalle")
    pds.add_argument("id")
    pds.add_argument("archivo", help="fichero .svg de salida")
    pds.add_argument("--region", default="base")
    pdp = psub.add_parser("pdf",
                          help="Exportar el detalle en PDF vectorial A4 "
                               "(v3.6.0)")
    pdp.add_argument("id")
    pdp.add_argument("archivo", help="fichero .pdf de salida")
    pdp.add_argument("--region", default="base")
    pdn = psub.add_parser("png",
                          help="Exportar el detalle en PNG raster 2x "
                               "(v3.6.0)")
    pdn.add_argument("id")
    pdn.add_argument("archivo", help="fichero .png de salida")
    pdn.add_argument("--region", default="base")
    pdt = psub.add_parser("tipologia",
                          help="Detalles recomendados para una tipología "
                               "constructiva del asistente (v3.6.0)")
    pdt.add_argument("tipologia",
                     help="nombre de la tipología (texto tolerante, "
                          "p. ej. «bloque», «piedra», «madera ligera»)")
    pdt.add_argument("--region", default="base")
    pdt.add_argument("--categoria", default="",
                     help="afina por categoría (cimentaciones, muros…)")

    p = sub.add_parser("importar", help="Importación de archivos externos (spec 94)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pca = psub.add_parser("catalogo", help="Catálogo PRECONS (.xlsx/.csv/.json) -> ruleset")
    pca.add_argument("archivo")
    pca.add_argument("--mapping", default="", help="JSON opcional con hojas/columnas")
    pca.add_argument("--code", default="imported")
    pca.add_argument("--nombre", default="")
    pca.add_argument("--out", default="", help="Sin esta ruta solo se muestra el PREVIEW")
    pdx = psub.add_parser("dxf", help="Entidades de un DXF (muros/locales) -> proyecto")
    pdx.add_argument("archivo")
    pdx.add_argument("--file", required=True, help="Proyecto ARQ GEN (.arq)")
    pdx.add_argument("--nivel", default="PLANTA_1")
    pdx.add_argument("--espesor", type=float, default=0.2)
    pdx.add_argument("--altura", type=float, default=0.0)
    pdx.add_argument("--capa-muros", default="")
    pdx.add_argument("--capa-locales", default="")
    pdx.add_argument("--aplicar", action="store_true", help="Sin esta bandera solo PREVIEW")
    pdw = psub.add_parser("dwg", help="Entidades de un DWG (muros/locales) -> proyecto "
                                      "(requiere un conversor local a DXF)")
    pdw.add_argument("archivo")
    pdw.add_argument("--file", required=True, help="Proyecto ARQ GEN (.arq)")
    pdw.add_argument("--nivel", default="PLANTA_1")
    pdw.add_argument("--espesor", type=float, default=0.2)
    pdw.add_argument("--altura", type=float, default=0.0)
    pdw.add_argument("--capa-muros", default="")
    pdw.add_argument("--capa-locales", default="")
    pdw.add_argument("--convertidor", default="",
                     help="Ruta de un conversor DWG->DXF (vacío = autodetectar "
                          "LibreDWG/ODA; también vale ARQGEN_DWG2DXF)")
    pdw.add_argument("--aplicar", action="store_true", help="Sin esta bandera solo PREVIEW")

    p = sub.add_parser("bim", help="Modelo BIM interno (spec 63)")
    psub = p.add_subparsers(dest="subcommand", required=True)
    pbt = psub.add_parser("tree", help="Árbol espacial Project->Site->Building->Storeys")
    pbt.add_argument("file")
    pbr = psub.add_parser("show", help="Registro BIM de un objeto (spec 63)")
    pbr.add_argument("file")
    pbr.add_argument("--ref", required=True, help="Código o tipo/id del objeto")

    # -- demo / selftest / plugins ------------------------------------------------------------------------------
    p = sub.add_parser("demo", help="Crear el proyecto de demostración")
    p.add_argument("--out", default=os.path.join("output", "demo.arqgen"))
    p = sub.add_parser("selftest", help="Verificación integral interna")
    p = sub.add_parser("rpc", help="Servidor JSON-RPC del sidecar (FASE A Tauri): "
                       "lee peticiones de stdin y responde por stdout")
    from app.cli_fases import add_parsers as add_v13_parsers
    add_v13_parsers(sub)

    return parser


# -- command implementations ------------------------------------------------
def _open(application, args):
    return application.open_project(args.file)


def cmd_project_create(application, args) -> int:
    context = application.create_project(
        args.file, args.name, client=args.client, address=args.address,
        description=args.description, ruleset_code=args.ruleset,
        currency=args.currency)
    context.user = args.user
    from services.quantity_service import QuantityService
    QuantityService(context).install_default_formulas()
    from services.analysis_service import RuleService
    try:
        RuleService(context).load_ruleset_from_resources(args.ruleset)
    except Exception:
        pass  # ruleset opcional; el error se reporta si se pide validar
    context.commit()
    print(f"Proyecto creado: {args.name}")
    print(f"  Archivo : {args.file}")
    print(f"  ID      : {context.project.id}")
    context.close()
    return 0


def cmd_project_info(application, args) -> int:
    context = application.open_project(args.file)
    project = context.project
    print(f"Proyecto   : {project.name}")
    print(f"Cliente    : {project.client}")
    print(f"Dirección  : {project.address}")
    print(f"Moneda     : {project.currency}")
    print(f"Ruleset    : {project.ruleset_code or '(sin reglas)'}")
    print(f"Creado     : {project.created_at.isoformat(timespec='seconds')}")
    for entity_type, label in (("LEVEL", "Niveles"), ("ZONE", "Zonas"),
                               ("SPACE", "Locales"), ("WALL", "Muros"),
                               ("DOOR", "Puertas"), ("WINDOW", "Ventanas")):
        print(f"{label:10s}: {context.architecture.count(entity_type, project.id)}")
    print(f"Cantidades : {context.quantities_repo.count(project.id)}")
    budgets = context.budget_repo.list_budgets(project.id)
    if budgets:
        last = budgets[-1]
        print(f"Presupuesto: {last['total_cost']:.2f} {last['currency']} ({last['name']})")
    context.close()
    return 0


def cmd_level_add(application, args) -> int:
    from services.architecture_service import ArchitectureService
    context = _open(application, args)
    context.user = args.user
    level = ArchitectureService(context).create_level(args.name, args.elevation, args.height)
    context.commit()
    print(f"Nivel creado: {level.code} — {level.name} "
          f"(cota {level.elevation_m:.2f} m, altura {level.height_m:.2f} m)")
    context.close()
    return 0


def _print_table(rows: List[List[str]], headers: List[str]) -> None:
    widths = [max(len(str(r[i])) if i < len(r) else 0 for r in rows + [headers])
              for i in range(len(headers))]
    line = "  ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def cmd_level_list(application, args) -> int:
    context = application.open_project(args.file)
    rows = [[l.code, l.name, f"{l.elevation_m:.2f}", f"{l.height_m:.2f}"]
            for l in context.architecture.list("LEVEL", context.project.id)]
    _print_table(rows, ["Código", "Nombre", "Cota (m)", "Altura (m)"])
    if not rows:
        print("(sin niveles)")
    context.close()
    return 0


def cmd_zone_add(application, args) -> int:
    from services.architecture_service import ArchitectureService
    context = _open(application, args)
    context.user = args.user
    zone = ArchitectureService(context).create_zone(args.name, args.kind)
    context.commit()
    print(f"Zona creada: {zone.code} — {zone.name} ({zone.kind})")
    context.close()
    return 0


def cmd_zone_list(application, args) -> int:
    context = application.open_project(args.file)
    rows = [[z.code, z.name, z.kind] for z in context.architecture.list("ZONE", context.project.id)]
    _print_table(rows, ["Código", "Nombre", "Tipo"])
    if not rows:
        print("(sin zonas)")
    context.close()
    return 0


def _parse_point(text: str):
    x, y = text.split(",")
    return float(x), float(y)


def cmd_space_add(application, args) -> int:
    from services.architecture_service import ArchitectureService
    context = _open(application, args)
    context.user = args.user
    service = ArchitectureService(context)
    boundary = [_parse_point(p) for p in args.polygon]
    space = service.create_space(args.level, args.name, args.type, boundary)
    if args.zone:
        space2 = service.set_space_zone(space.code, args.zone)
        space = space2
    context.commit()
    print(f"Local creado: {space.code} — {space.name} ({space.space_type}) "
          f"área {space.area_m2():.2f} m2")
    context.close()
    return 0


def cmd_space_list(application, args) -> int:
    context = application.open_project(args.file)
    rows = []
    for s in context.architecture.list("SPACE", context.project.id):
        zone_name = ""
        if s.zone_id:
            zone = context.architecture.get("ZONE", s.zone_id)
            zone_name = zone.code if zone else ""
        rows.append([s.code, s.name, s.space_type, f"{s.area_m2():.2f}",
                     f"{s.perimeter_m():.2f}", zone_name])
    _print_table(rows, ["Código", "Nombre", "Tipo", "Área (m2)", "Perím. (m)", "Zona"])
    if not rows:
        print("(sin locales)")
    context.close()
    return 0


def cmd_wall_add(application, args) -> int:
    from services.architecture_service import ArchitectureService
    context = _open(application, args)
    context.user = args.user
    wall = ArchitectureService(context).create_wall(
        args.level, _parse_point(args.start), _parse_point(args.end),
        thickness_m=args.thickness, height_m=args.height)
    context.commit()
    print(f"Muro creado: {wall.code} — longitud {wall.length_m:.2f} m, "
          f"espesor {wall.thickness_m:.2f} m, altura {wall.height_m:.2f} m")
    context.close()
    return 0


def cmd_wall_list(application, args) -> int:
    context = application.open_project(args.file)
    rows = [[w.code, f"{w.start[0]:.2f},{w.start[1]:.2f}", f"{w.end[0]:.2f},{w.end[1]:.2f}",
             f"{w.length_m:.2f}", f"{w.thickness_m:.2f}", f"{w.height_m:.2f}"]
            for w in context.architecture.list("WALL", context.project.id)]
    _print_table(rows, ["Código", "Inicio", "Fin", "Long.", "Espesor", "Altura"])
    if not rows:
        print("(sin muros)")
    context.close()
    return 0


def cmd_wall_move(application, args) -> int:
    from services.architecture_service import ArchitectureService
    context = _open(application, args)
    context.user = args.user
    wall = ArchitectureService(context).move_wall(args.wall, _parse_point(args.start),
                                                  _parse_point(args.end))
    context.commit()
    print(f"Muro movido: {wall.code} — nueva longitud {wall.length_m:.2f} m "
          f"(cantidades marcadas para recálculo)")
    context.close()
    return 0


def _cmd_opening_add(kind):
    def impl(application, args) -> int:
        from services.architecture_service import ArchitectureService
        context = _open(application, args)
        context.user = args.user
        opening = ArchitectureService(context).create_opening(
            kind, args.wall, args.width, args.height, offset_m=args.offset,
            sill_height_m=args.sill)
        context.commit()
        label = "Puerta" if kind == "DOOR" else "Ventana"
        print(f"{label} creada: {opening.code} — {opening.width_m:.2f}x{opening.height_m:.2f} m "
              f"en muro {args.wall}")
        context.close()
        return 0
    return impl


def _cmd_opening_list(kind):
    def impl(application, args) -> int:
        context = application.open_project(args.file)
        rows = []
        for o in context.architecture.list(kind, context.project.id):
            wall = context.architecture.get("WALL", o.wall_id)
            rows.append([o.code, wall.code if wall else "?",
                         f"{o.width_m:.2f}", f"{o.height_m:.2f}",
                         f"{o.offset_m:.2f}", f"{o.sill_height_m:.2f}"])
        _print_table(rows, ["Código", "Muro", "Ancho", "Alto", "Offset", "Antepecho"])
        if not rows:
            print("(sin registros)")
        context.close()
        return 0
    return impl


def cmd_undo(application, args) -> int:
    from app.undo_service import PersistentUndoService
    context = _open(application, args)
    context.user = args.user
    result = PersistentUndoService(context).undo()
    context.commit()
    print(f"Deshecho: {result['command']} sobre {result['object_type']} {result['object_id'][:8]}")
    context.close()
    return 0


def cmd_redo(application, args) -> int:
    from app.undo_service import PersistentUndoService
    context = _open(application, args)
    context.user = args.user
    result = PersistentUndoService(context).redo()
    context.commit()
    print(f"Rehecho: {result['object_type']} {result['object_id'][:8]}")
    context.close()
    return 0


def cmd_relationships_recompute(application, args) -> int:
    from services.analysis_service import SpatialService
    context = _open(application, args)
    context.user = args.user
    results = SpatialService(context).recompute_adjacencies()
    context.commit()
    print(f"Adyacencias creadas: {len(results)}")
    for r in results:
        print(f"  {r['from']} ↔ {r['to']} ({r['shared_m']:.2f} m compartidos)")
    context.close()
    return 0


def cmd_relationships_report(application, args) -> int:
    from services.analysis_service import SpatialService
    context = _open(application, args)
    spatial = SpatialService(context)
    print("— Adyacencias por geometría —")
    for line in spatial.adjacency_report():
        print(f"  {line}")
    print("— Hallazgos del DNA de locales —")
    findings = spatial.dna_findings()
    for line in findings:
        print(f"  {line}")
    if not findings:
        print("  (sin hallazgos)")
    context.close()
    return 0


def cmd_validate(application, args) -> int:
    from services.analysis_service import ValidationService
    context = _open(application, args)
    context.user = args.user
    result = ValidationService(context).validate_project()
    context.commit()
    print(f"Estado de validación: {result.status.value}")
    if result.errors:
        print(f"Errores ({len(result.errors)}):")
        for f in result.errors:
            print(f"  [ERROR] {f.code}: {f.message}")
    if result.warnings:
        print(f"Avisos ({len(result.warnings)}):")
        for f in result.warnings:
            print(f"  [AVISO] {f.code}: {f.message}")
    if result.info:
        print(f"Informativos ({len(result.info)}):")
        for f in result.info:
            print(f"  [INFO] {f.code}: {f.message}")
    if result.is_ok and not result.info:
        print("Sin hallazgos.")
    context.close()
    return 0 if result.is_ok else 1


def cmd_instalar(application, args) -> int:
    """Genera redes de instalaciones reales (v3.8.0), el motor de los
    asistentes, adaptadas a los locales ya existentes del proyecto."""
    from services.installations_generator import (
        MODULE_SYSTEMS, generate_installations)
    context = _open(application, args)
    context.user = args.user
    modulos = list(MODULE_SYSTEMS) if args.todo else list(args.modulos)
    if not modulos:
        print("Indica módulos (p. ej. 'Eléctrica' 'Sanitaria') o usa --todo.")
        context.close()
        return 1
    summary = generate_installations(context, modulos,
                                     origin="CLI instalar")
    context.commit()
    print(f"INSTALACIONES: {summary['redes']} red(es), "
          f"{summary['equipos']} equipo(s), {summary['tramos']} tramo(s)")
    for name in summary["nombres"]:
        print(f"  · {name}")
    for w in summary["warnings"]:
        print(f"  [AVISO] {w}")
    if not summary["nombres"]:
        print("No se generó ninguna red; revisa los nombres de módulos.")
    context.close()
    return 0


def cmd_qto_compute(application, args) -> int:
    from core.calculations.contracts import CalculationMode
    from services.quantity_service import QuantityService
    context = _open(application, args)
    context.user = args.user
    stats = QuantityService(context).compute_all(CalculationMode(args.mode))
    context.commit()
    print(f"Cómputo QTO completado ({args.mode}):")
    print(f"  Objetos procesados : {stats.objects_processed}")
    print(f"  Recalculados       : {stats.computed}")
    print(f"  Desde caché        : {stats.cached}")
    print(f"  Duración           : {stats.duration_ms:.1f} ms")
    context.close()
    return 0


def cmd_qto_show(application, args) -> int:
    from services.quantity_service import QuantityService
    context = application.open_project(args.file)
    rows = [[q["object_code"], q["formula_code"], f"{q['final_quantity']:.3f}", q["unit"],
             "STALE" if q["stale"] else "OK"]
            for q in QuantityService(context).quantities(only_stale=args.stale_only)]
    _print_table(rows, ["Objeto", "Fórmula", "Cantidad", "Unidad", "Estado"])
    if not rows:
        print("(sin cantidades; ejecute 'qto compute')")
    context.close()
    return 0


def cmd_resource_add(application, args) -> int:
    from services.budget_service import PricingService
    context = _open(application, args)
    context.user = args.user
    resource = PricingService(context).add_resource(
        args.code, args.name, args.type, args.unit, args.category)
    context.commit()
    print(f"Recurso creado: {resource['code']} — {resource['name']} ({resource['type']}, {resource['unit']})")
    context.close()
    return 0


def cmd_resource_list(application, args) -> int:
    from services.budget_service import PricingService
    context = application.open_project(args.file)
    rows = [[r["code"], r["name"], r["type"], r["unit"]]
            for r in PricingService(context).resources()]
    _print_table(rows, ["Código", "Nombre", "Tipo", "Unidad"])
    if not rows:
        print("(sin recursos)")
    context.close()
    return 0


def cmd_price_set(application, args) -> int:
    from services.budget_service import PricingService
    context = _open(application, args)
    context.user = args.user
    result = PricingService(context).set_price(
        args.resource, args.price, args.price_list,
        date_iso=args.date or None, currency=args.currency)
    context.commit()
    print(f"Precio registrado: {result['resource']} = {result['price']:.2f} "
          f"{result['price_list']} desde {result['valid_from']} (histórico preservado)")
    context.close()
    return 0


def cmd_price_history(application, args) -> int:
    from services.budget_service import PricingService
    context = application.open_project(args.file)
    history = PricingService(context).price_history(args.resource, args.price_list)
    rows = [[h["valid_from"], f"{h['price']:.2f}", h["currency"], h["region"] or "-", h["note"] or "-"]
            for h in history]
    _print_table(rows, ["Vigente desde", "Precio", "Moneda", "Región", "Nota"])
    if not rows:
        print("(sin histórico)")
    context.close()
    return 0


def cmd_budget_compute(application, args) -> int:
    from services.budget_service import BudgetService
    context = _open(application, args)
    context.user = args.user
    result = BudgetService(context).compute_budget(args.template, name=args.name)
    context.commit()
    print(f"Presupuesto calculado ({args.template}):")
    print(f"  Costo directo   : {result.direct_cost:,.2f} {result.currency}")
    print(f"  Costo indirecto : {result.indirect_cost:,.2f} {result.currency}")
    print(f"  Otros costos    : {result.other_cost:,.2f} {result.currency}")
    print(f"  TOTAL           : {result.total:,.2f} {result.currency}")
    context.close()
    return 0


def cmd_budget_show(application, args) -> int:
    from services.budget_service import BudgetService
    context = application.open_project(args.file)
    budget = BudgetService(context).latest_budget()
    if budget is None:
        print("(sin presupuesto; ejecute 'budget compute')")
        context.close()
        return 1
    items = context.budget_repo.budget_items_full(budget["id"])
    rows = [[item["chapter"].get("code", ""), item["code"], item["description"],
             item["unit"], f"{item['quantity']:.2f}", f"{item['direct_cost']:,.2f}"]
            for item in items]
    _print_table(rows, ["Cap.", "Partida", "Descripción", "Unidad", "Cantidad", "Costo"])
    print(f"\nDirecto: {budget['direct_cost']:,.2f}  Indirecto: {budget['indirect_cost']:,.2f}  "
          f"Otros: {budget['other_cost']:,.2f}")
    print(f"TOTAL  : {budget['total_cost']:,.2f} {budget['currency']}")
    context.close()
    return 0


def cmd_export(application, args) -> int:
    from services.export_service import ExportService
    context = application.open_project(args.file)
    context.user = args.user
    options = {}
    if args.format == "dxf" and args.level:
        options["level"] = args.level
    if args.format == "dxf" and getattr(args, "r12", False):
        options["version"] = "R12"
    if args.format == "csv":
        options["table"] = args.table
    path = ExportService().export(context, args.format, args.out, options)
    context.commit()
    print(f"Exportación completada: {path}")
    context.close()
    return 0


def cmd_import(application, args) -> int:
    from services.import_service import ImportService
    application2 = application
    importer = ImportService(application2)
    if not args.approve:
        preview = importer.preview(args.file)
        print("Vista previa de importación (sin cambios aplicados):")
        print(f"  Proyecto : {preview['project']}")
        for entity_type, count in preview["counts"].items():
            if count:
                print(f"  {entity_type}: {count}")
        if preview["errors"]:
            print(f"  ERRORES: {preview['errors']}")
            return 1
        print("Ejecute de nuevo con --approve para importar.")
        return 0
    result = importer.import_snapshot(args.file, args.out, approve=True, user=args.user)
    print(f"Importación completada en: {result['path']}")
    for entity_type, count in result["inserted"].items():
        if count:
            print(f"  {entity_type}: {count}")
    return 0


def cmd_version_save(application, args) -> int:
    from exporters.json_io import JSONExporter
    from services.version_service import VersionService
    context = _open(application, args)
    context.user = args.user
    snapshot = JSONExporter.build_snapshot(context)
    import json
    info = VersionService(context).save_version(
        args.author, args.description, json.dumps(snapshot, ensure_ascii=False))
    context.commit()
    print(f"Versión guardada: #{info['number']} por {info['author']}")
    context.close()
    return 0


def cmd_version_list(application, args) -> int:
    from services.version_service import VersionService
    context = application.open_project(args.file)
    rows = [[v["number"], v["author"], v["description"], v["created_at"][:19],
             f"{v['size']:,} B"]
            for v in VersionService(context).list_versions()]
    _print_table(rows, ["#", "Autor", "Descripción", "Fecha", "Tamaño"])
    if not rows:
        print("(sin versiones)")
    context.close()
    return 0


def cmd_version_restore(application, args) -> int:
    import json
    from exporters.json_io import JSONExporter
    from persistence.backup.service import BackupService
    from services.version_service import VersionService
    context = _open(application, args)
    context.user = args.user
    # Backup before destructive operation (spec 81)
    backup = BackupService(default_backup_dir()).create_full_backup(
        args.file, label="pre_restore")
    print(f"Backup previo: {backup.path}")
    snapshot = VersionService(context).get_snapshot(args.number)
    VersionService(context).restore_version(args.number, snapshot)
    context.commit()
    print(f"Versión #{args.number} restaurada.")
    context.close()
    return 0


def cmd_backup_create(application, args) -> int:
    from persistence.backup.service import BackupService
    service = BackupService(args.dir)
    info = service.create_full_backup(args.file)
    print(f"Backup creado: {info.path}")
    print(f"  Tamaño    : {info.size_bytes:,} B")
    print(f"  Integridad: {info.integrity}")
    return 0


def cmd_backup_list(application, args) -> int:
    from persistence.backup.service import BackupService
    for path in BackupService(args.dir).list_backups():
        print(path)
    return 0


def cmd_backup_restore(application, args) -> int:
    from persistence.backup.service import BackupService
    service = BackupService(args.dir)
    info = service.restore(args.backup, args.file)
    print(f"Backup restaurado sobre {args.file}")
    print(f"  Integridad: {info.integrity}")
    return 0


def cmd_audit_show(application, args) -> int:
    context = application.open_project(args.file)
    rows = [[e["timestamp"][:19], e["user"], e["command"], e["object_type"],
             e["object_id"][:8], e["result"]]
            for e in context.audit_repo.recent(limit=args.limit)]
    _print_table(rows, ["Fecha", "Usuario", "Comando", "Tipo", "Objeto", "Resultado"])
    if not rows:
        print("(sin registros de auditoría)")
    context.close()
    return 0


def cmd_events_show(application, args) -> int:
    context = application.open_project(args.file)
    rows = [[e["timestamp"][:19], e["type"], e["source"]]
            for e in context.events_repo.recent(limit=args.limit)]
    _print_table(rows, ["Fecha", "Evento", "Origen"])
    if not rows:
        print("(sin eventos)")
    context.close()
    return 0


def cmd_demo(application, args) -> int:
    from app.demo import build_demo
    context = build_demo(application, args.out)
    context.commit()
    print(f"Proyecto demo creado: {args.out}")
    print(f"  Locales : {context.architecture.count('SPACE', context.project.id)}")
    print(f"  Muros   : {context.architecture.count('WALL', context.project.id)}")
    print(f"  Puertas : {context.architecture.count('DOOR', context.project.id)}")
    print(f"  Ventanas: {context.architecture.count('WINDOW', context.project.id)}")
    networks = context.installations.list("NETWORK", context.project.id)
    nodes = sum(len(context.installations.nodes_of(n.id)) for n in networks)
    segments = sum(len(context.installations.segments_of(n.id)) for n in networks)
    print(f"  Redes   : {len(networks)} ({nodes} nodos, {segments} tramos)")
    context.close()
    return 0


def cmd_selftest(application, args) -> int:
    from app.selftest import run_selftest
    ok, _ = run_selftest(console=True)
    return 0 if ok else 1


def cmd_plugins(application, args) -> int:
    from app.bootstrap import bootstrap
    application2, loader = bootstrap(args)
    print("Plugins cargados:")
    for entry in loader.loaded:
        if entry.error:
            print(f"  [ERROR] {entry.source}: {entry.error}")
        else:
            p = entry.plugin
            print(f"  {p.plugin_id} v{p.version} — {p.name} ({entry.source})")
            if p.services:
                print(f"    servicios: {', '.join(p.services)}")
    return 0


# -- installations commands (spec 24-29) --------------------------------------
def _parse_attrs(pairs: List[str]) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    for item in pairs or []:
        if "=" not in item:
            raise ValueError(f"Atributo inválido '{item}': use k=v")
        key, value = item.split("=", 1)
        try:
            attrs[key.strip()] = float(value) if "." in value else int(value)
        except ValueError:
            attrs[key.strip()] = value
    return attrs


def _service(context):
    from services.installations_service import InstallationsService
    return InstallationsService(context)


def cmd_net_add(application, args) -> int:
    context = _open(application, args)
    context.user = args.user
    network = _service(context).create_network(args.name, args.system.upper(),
                                               description=args.description)
    context.commit()
    print(f"Red creada: {network.code} — {network.name} "
          f"({network.discipline}/{network.system})")
    context.close()
    return 0


def cmd_net_list(application, args) -> int:
    context = application.open_project(args.file)
    rows = [[n.code, n.name, n.discipline, n.system,
             str(len(context.installations.nodes_of(n.id))),
             str(len(context.installations.segments_of(n.id)))]
            for n in context.installations.list("NETWORK", context.project.id)]
    _print_table(rows, ["Código", "Nombre", "Disciplina", "Sistema", "Nodos", "Tramos"])
    if not rows:
        print("(sin redes)")
    context.close()
    return 0


def cmd_net_show(application, args) -> int:
    context = application.open_project(args.file)
    service = _service(context)
    network = service.resolve_network(args.network)
    print(f"Red {network.code} — {network.name} ({network.discipline}/{network.system})")
    print("Nodos:")
    for node in context.installations.nodes_of(network.id):
        print(f"  {node.code:18s} {node.kind:12s} ({node.x:.2f}, {node.y:.2f}) {node.name}")
    print("Tramos:")
    for segment in context.installations.segments_of(network.id):
        n_from = context.installations.get("NODE", segment.from_node_id)
        n_to = context.installations.get("NODE", segment.to_node_id)
        print(f"  {segment.code:18s} {segment.kind:12s} {n_from.code}->{n_to.code} "
              f"L={segment.length_m:.2f} m D={segment.diameter_mm:.0f} mm "
              f"cruces={segment.crossings}")
    context.close()
    return 0


def cmd_net_trace(application, args) -> int:
    context = _open(application, args)
    result = _service(context).trace(args.node)
    print(f"Trazo en {result['network']} desde {result['node']} "
          f"(topología {result['topology']}):")
    print("  " + " -> ".join(result["path"]))
    print(f"  Longitud acumulada: {result['length_m']:.2f} m")
    context.close()
    return 0


def cmd_net_path(application, args) -> int:
    context = _open(application, args)
    result = _service(context).find_path(args.from_ref, args.to_ref, weight=args.weight)
    if not result["path"]:
        print(f"ERROR [ARQ-MEP-022] No existe camino entre {args.from_ref} y {args.to_ref}")
        context.close()
        return 1
    print(f"Camino en {result['network']} (coste por {result['weight']}):")
    print("  " + " -> ".join(result["path"]))
    print(f"  Coste total: {result['cost']}")
    context.close()
    return 0


def cmd_net_validate(application, args) -> int:
    context = _open(application, args)
    result = _service(context).validate_network(args.network)
    print(f"Validación de {result['network']} ({result['system']}): {result['status']}")
    for error in result["errors"]:
        print(f"  ERROR  [{error['code']}] {error['message']}")
    for warning in result["warnings"]:
        print(f"  AVISO  [{warning['code']}] {warning['message']}")
    if result["dead_ends"]:
        print(f"  Finales muertos: {', '.join(result['dead_ends'])}")
    context.close()
    return 0 if result["status"] in ("VALID", "VALID_WITH_WARNINGS") else 1


def cmd_net_deadends(application, args) -> int:
    context = _open(application, args)
    result = _service(context).validate_network(args.network)
    if result["dead_ends"]:
        print("Finales muertos detectados:")
        for code in result["dead_ends"]:
            print(f"  {code}")
    else:
        print("Sin finales muertos.")
    context.close()
    return 0


def cmd_node_add(application, args) -> int:
    context = _open(application, args)
    context.user = args.user
    try:
        attrs = _parse_attrs(args.attr)
    except ValueError as exc:
        print(f"ERROR [ARQ-MEP-023] {exc}")
        context.close()
        return 1
    node = _service(context).add_node(
        args.network, args.kind.upper(), args.x, args.y, name=args.name,
        level_ref=args.level, space_ref=args.space,
        elevation_m=args.elevation, attrs=attrs)
    context.commit()
    print(f"Nodo creado: {node.code} — {node.kind} ({node.x:.2f}, {node.y:.2f}) "
          f"rol={node.role}")
    context.close()
    return 0


def cmd_node_list(application, args) -> int:
    context = application.open_project(args.file)
    if args.network:
        network = _service(context).resolve_network(args.network)
        nodes = context.installations.nodes_of(network.id)
    else:
        nodes = context.installations.list("NODE", context.project.id)
    rows = [[n.code, n.kind, n.role, n.name, f"{n.x:.2f}", f"{n.y:.2f}"]
            for n in nodes]
    _print_table(rows, ["Código", "Tipo", "Rol", "Nombre", "X", "Y"])
    if not rows:
        print("(sin nodos)")
    context.close()
    return 0


def cmd_node_move(application, args) -> int:
    context = _open(application, args)
    context.user = args.user
    node = _service(context).move_node(args.node, args.x, args.y)
    context.commit()
    print(f"Nodo movido: {node.code} a ({node.x:.2f}, {node.y:.2f})")
    context.close()
    return 0


def cmd_link_add(application, args) -> int:
    context = _open(application, args)
    context.user = args.user
    try:
        attrs = _parse_attrs(args.attr)
    except ValueError as exc:
        print(f"ERROR [ARQ-MEP-023] {exc}")
        context.close()
        return 1
    segment = _service(context).connect(
        args.network, args.from_ref, args.to_ref, kind=args.kind, name=args.name,
        length_m=args.length, diameter_mm=args.diameter, slope_pct=args.slope,
        material=args.material, routing=args.routing, attrs=attrs)
    context.commit()
    print(f"Tramo creado: {segment.code} ({segment.kind}) "
          f"L={segment.length_m:.2f} m, cruces de muro: {segment.crossings}")
    context.close()
    return 0


def cmd_link_list(application, args) -> int:
    context = _open(application, args)
    network = _service(context).resolve_network(args.network)
    nodes = {n.id: n for n in context.installations.nodes_of(network.id)}
    rows = []
    for s in context.installations.segments_of(network.id):
        n_from = nodes.get(s.from_node_id)
        n_to = nodes.get(s.to_node_id)
        rows.append([s.code, s.kind,
                     n_from.code if n_from else "?", n_to.code if n_to else "?",
                     f"{s.length_m:.2f}", f"{s.diameter_mm:.0f}",
                     f"{s.slope_pct:.2f}", str(s.crossings)])
    _print_table(rows, ["Código", "Tipo", "Desde", "Hasta", "L (m)", "D (mm)",
                        "Pend. (%)", "Cruces"])
    if not rows:
        print("(sin tramos)")
    context.close()
    return 0


def cmd_link_remove(application, args) -> int:
    context = _open(application, args)
    context.user = args.user
    _service(context).disconnect(args.link)
    context.commit()
    print(f"Tramo eliminado: {args.link}")
    context.close()
    return 0


def cmd_elec_check(application, args) -> int:
    context = _open(application, args)
    result = _service(context).circuit_check(args.circuit)
    load = result["load"]
    print(f"Circuito {result['circuit']} ({result['kind']}): "
          f"{load['devices']} dispositivos")
    print(f"  Potencia conectada : {load['connected_w']:.0f} W")
    print(f"  Potencia demanda   : {load['demand_w']:.0f} W (factor {load['demand_factor']:.2f})")
    print(f"  Corriente diseño   : {load['current_a']:.2f} A "
          f"({result['voltage']:.0f} V, {result['phases']}f, fp {result['power_factor']:.2f})")
    print(f"  Protección         : {result['breaker_standard']:.0f} A")
    print(f"  Sección máx. tramo : {result['section_mm2']:.2f} mm2 "
          f"(ampacidad {result['ampacity_a']:.0f} A, conducto {result['conduit_mm']:.0f} mm)")
    print(f"  Peor caída tensión : {result['worst_vd_pct']:.2f} %")
    for finding in result["findings"]:
        print(f"  AVISO: {finding}")
    print(f"  Estado: {'OK' if result['ok'] else 'CON AVISOS'}")
    context.close()
    return 0


def cmd_elec_summary(application, args) -> int:
    context = _open(application, args)
    result = _service(context).panel_summary(args.panel)
    print(f"Panel {result['panel']} — {result['voltage']:.0f} V, {result['phases']} fase(s), "
          f"principal {result['main_breaker_a']:.0f} A")
    rows = [[c["code"], c["kind"], str(c["devices"]),
             f"{c['connected_w']:.0f}", f"{c['demand_w']:.0f}",
             f"{c['current_a']:.1f}", f"{c['breaker_a']:.0f}", str(c["phase"])]
            for c in result["circuits"]]
    _print_table(rows, ["Circuito", "Tipo", "Disp.", "Conect. W", "Demanda W",
                        "I (A)", "Prot. (A)", "Fase"])
    print(f"Total conectado : {result['total_connected_w']:.0f} W")
    print(f"Total demanda   : {result['total_demand_w']:.0f} W")
    if result["phases"] > 1:
        print(f"Desbalance      : {result['balance']['imbalance_pct']:.1f} %")
    context.close()
    return 0


def cmd_elec_balance(application, args) -> int:
    context = _open(application, args)
    result = _service(context).panel_summary(args.panel)
    balance = result["balance"]
    print(f"Balance del panel {result['panel']}:")
    print(f"  Carga máx. fase : {balance['max_phase_w']:.0f} W")
    print(f"  Carga mín. fase : {balance['min_phase_w']:.0f} W")
    print(f"  Desbalance      : {balance['imbalance_pct']:.1f} %")
    context.close()
    return 0


def cmd_san_size(application, args) -> int:
    context = _open(application, args)
    result = _service(context).size_sanitary(args.network)
    print(f"Dimensionado de {result['network']} (sistema {result['system']})")
    headers = ["Tramo", "Desde", "Hasta", "Apar.", "Q (L/s)", "DN (mm)"]
    extra_keys = []
    if result["rows"] and "velocity_ms" in result["rows"][0]:
        extra_keys = ["v (m/s)", "Pérd. (m)"]
    elif result["rows"] and "capacity_ls" in result["rows"][0]:
        extra_keys = ["Pend. (%)", "Cap. (L/s)"]
    rows = []
    for r in result["rows"]:
        base = [r["segment"], r["from"], r["to"], str(r["fixtures"]),
                f"{r['q_ls']:.2f}", f"{r['diameter_mm']:.0f}"]
        if extra_keys and "velocity_ms" in r:
            base += [f"{r['velocity_ms']:.2f}", f"{r['head_loss_m']:.2f}"]
        elif extra_keys and "capacity_ls" in r:
            base += [f"{r['slope_pct']:.2f}", f"{r['capacity_ls']:.2f}"]
        rows.append(base)
    _print_table(rows, headers + extra_keys)
    if result.get("pump"):
        pump = result["pump"]
        print(f"Bombeo {pump['node']}: TDH {pump['tdh_m']:.1f} m, "
              f"{pump['flow_ls']:.2f} L/s -> {pump['electric_kw']:.2f} kW eléctrico")
    if result.get("tank"):
        print(f"Tanque {result['tank']['node']}: {result['tank']['volume_l']:.0f} L")
    for finding in result["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0


def cmd_plu_size(application, args) -> int:
    context = _open(application, args)
    result = _service(context).size_stormwater(args.network)
    print(f"Dimensionado pluvial de {result['network']} (sistema {result['system']})")
    print(f"  Captación total: {result['captured_ls']:.2f} L/s | "
          f"evacuación exigida: {result['outfall_required_ls']:.2f} L/s")
    rows = []
    for r in result["rows"]:
        rows.append([r["segment"], r["from"], r["to"], r["kind"],
                     f"{r['q_ls']:.2f}", f"{r['diameter_mm']:.0f}",
                     f"{r.get('capacity_ls', 0):.2f}"])
    _print_table(rows, ["Tramo", "Desde", "Hasta", "Tipo", "Q (L/s)",
                        "DN (mm)", "Cap. (L/s)"])
    for g in result.get("gutters", []):
        if g.get("suggested_width_mm"):
            print(f"  Canalón {g['node']}: entrada {g['inflow_ls']:.2f} L/s -> "
                  f"sugerido {g['suggested_width_mm']:.0f}x{g['suggested_depth_mm']:.0f} mm")
        else:
            print(f"  Canalón {g['node']}: {g['width_mm']:.0f}x{g['depth_mm']:.0f} mm, "
                  f"capacidad {g['capacity_ls']:.2f} L/s para {g['inflow_ls']:.2f} L/s")
    if result.get("detention"):
        d = result["detention"]
        print(f"  Detención {d['node']}: {d['volume_l']:.0f} L "
              f"({d['retention_min']:.0f} min a {d['flow_ls']:.2f} L/s)")
    for finding in result["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0


def cmd_gas_size(application, args) -> int:
    context = _open(application, args)
    result = _service(context).size_gas(args.network)
    print(f"Dimensionado de gas de {result['network']} "
          f"({result['appliances']} aparatos)")
    rows = [[r["segment"], r["from"], r["to"],
             f"{r['uc_served']:.1f}", f"{r['q_m3h']:.3f}",
             f"{r['diameter_mm']:.0f}", f"{r['dp_pa']:.0f}",
             f"{r['velocity_ms']:.2f}"]
            for r in result["rows"]]
    _print_table(rows, ["Tramo", "Desde", "Hasta", "UC", "Q (m3/h)",
                        "DN (mm)", "ΔP (Pa)", "V (m/s)"])
    for finding in result["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0


def cmd_gas_check(application, args) -> int:
    context = _open(application, args)
    result = _service(context).validate_gas(args.network)
    print(f"Validación de gas de {result['network']}: {result['status']}")
    for info in result["infos"]:
        print(f"  INFO: {info}")
    for warning in result["warnings"]:
        print(f"  AVISO: {warning}")
    for error in result["errors"]:
        print(f"  ERROR: {error}")
    context.close()
    return 0 if result["status"] != "INVALID" else 1


def cmd_tel_size(application, args) -> int:
    context = _open(application, args)
    result = _service(context).size_telecom(args.network)
    print(f"Dimensionado de telecomunicaciones de {result['network']}")
    rows = []
    for r in result["rows"]:
        if r["kind"] == "FIBER":
            rows.append([r["segment"], r["from"], r["to"], "FIBER",
                         f"{r['loss_db']:.2f}/{r['budget_db']:.1f} dB",
                         f"{r['length_m']:.1f} m"])
        elif r["kind"] == "CABLE":
            rows.append([r["segment"], r["from"], r["to"],
                         f"CABLE {r.get('cable_type', '')}", "-",
                         f"{r['length_m']:.1f} m"])
        else:
            rows.append([r["segment"], r["from"], r["to"], "CONDUIT",
                         f"{r.get('cables', 0)} cables",
                         f"llenado {r.get('fill_pct', 0):.0f}%"])
    _print_table(rows, ["Tramo", "Desde", "Hasta", "Tipo", "Detalle", "Info"])
    for rack in result.get("racks", []):
        print(f"  Rack {rack['rack']}: {rack['used_u']:.1f} U de "
              f"{rack['capacity_u']:.0f} U ({rack['usage_pct']:.0f} %, "
              f"{rack['devices']} equipos)")
    for panel in result.get("panels", []):
        print(f"  {panel['node']}: {panel['used']:.0f}/{panel['capacity']:.0f} "
              f"{panel['label']} ({panel['usage_pct']:.0f} %)")
    for finding in result["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0


def cmd_hvac_load(application, args) -> int:
    context = _open(application, args)
    result = _service(context).space_thermal_load(args.space)
    print(f"Carga térmica de {result['space']} ({result['area_m2']:.1f} m2, "
          f"{result['occupants']} ocupantes):")
    print(f"  Transmisión  : {result['transmission_w']:.0f} W")
    print(f"  Solar        : {result['solar_w']:.0f} W")
    print(f"  Interno      : {result['internal_sensible_w']:.0f} W sens. + "
          f"{result['internal_latent_w']:.0f} W lat.")
    print(f"  Ventilación  : {result['ventilation_w']:.0f} W")
    print(f"  Refrigeración: {result['cooling_total_w']:.0f} W "
          f"({result['cooling_btu_h']:.0f} BTU/h)")
    print(f"  Calefacción  : {result['heating_w']:.0f} W")
    print(f"  Caudal aire  : {result['airflow_m3h']:.0f} m3/h")
    equipment = result["equipment"]
    unit_label = "unidad" if equipment["units"] == 1 else "unidades"
    print(f"  Equipamiento : {equipment['units']} {unit_label} de "
          f"{equipment['unit_btu_h']:.0f} BTU/h")
    context.close()
    return 0


def cmd_hvac_loads(application, args) -> int:
    context = _open(application, args)
    results = _service(context).hvac_loads_all()
    rows = [[r.get("space", "?"), f"{r.get('area_m2', 0):.1f}",
             f"{r.get('cooling_total_w', 0):.0f}", f"{r.get('cooling_btu_h', 0):.0f}",
             f"{r.get('heating_w', 0):.0f}", f"{r.get('airflow_m3h', 0):.0f}",
             f"{r.get('equipment', {}).get('unit_btu_h', 0):.0f}x{r.get('equipment', {}).get('units', 0)}"]
            for r in results]
    _print_table(rows, ["Local", "Área m2", "Ref. W", "Ref. BTU/h",
                        "Cal. W", "Aire m3/h", "Equipo"])
    if not rows:
        print("(sin locales)")
    context.close()
    return 0


def cmd_hvac_duct(application, args) -> int:
    from engines.hvac_engine import size_duct
    try:
        sizing = size_duct(args.flow, kind=args.kind, shape=args.shape,
                           target_velocity_ms=args.v or None)
    except Exception as exc:
        from core.errors import ARQGenError
        if isinstance(exc, ARQGenError):
            _print_error(exc.code, exc.message, exc.suggested_action)
        else:
            _print_error("ARQ-HVA-010", str(exc))
        return 1
    if sizing.shape == "ROUND":
        size_label = f"DN{sizing.diameter_mm:.0f} mm"
    else:
        size_label = f"{sizing.width_mm:.0f}x{sizing.height_mm:.0f} mm"
    print(f"Ducto {sizing.kind} {sizing.shape.lower()} para {sizing.airflow_m3h:.0f} m3/h:")
    print(f"  Área requerida : {sizing.area_m2:.4f} m2")
    print(f"  Sección        : {size_label}")
    print(f"  Velocidad real : {sizing.velocity_ms:.2f} m/s")
    for finding in sizing.findings:
        print(f"  AVISO: {finding}")
    return 0


def cmd_hvac_size_network(application, args) -> int:
    context = _open(application, args)
    result = _service(context).size_hvac_network(args.network)
    print(f"Dimensionado de ductería {result['network']}:")
    rows = []
    for r in result["rows"]:
        if r.get("airflow_m3h", 0) > 0:
            size_label = (f"DN{r['diameter_mm']:.0f}" if r.get("shape") == "ROUND"
                          else f"{r.get('width_mm', 0):.0f}x{r.get('height_mm', 0):.0f}")
            rows.append([r["segment"], r.get("from", ""), r.get("to", ""),
                         f"{r['airflow_m3h']:.0f}", size_label,
                         f"{r.get('velocity_ms', 0):.2f}"])
        else:
            rows.append([r["segment"], "-", "-", "0", "-", "-"])
    _print_table(rows, ["Tramo", "Desde", "Hasta", "Aire m3/h", "Sección", "V m/s"])
    for finding in result["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0


# -- structure commands (spec 33-34) ------------------------------------------------
def _struct_service(context):
    from services.structure_service import StructureService
    return StructureService(context)


def cmd_struct_material_add(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    material = service.create_material(
        args.name, args.kind, fck_mpa=args.fck, fy_mpa=args.fy,
        density_kn_m3=args.density)
    print(f"Material creado: {material.code} ({material.kind}, "
          f"E={material.e_gpa:.0f} GPa, γ={material.density_kn_m3:.1f} kN/m3)")
    context.close()
    return 0


def cmd_struct_section_add(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    section = service.create_section(
        args.name, args.shape, h_mm=args.h, b_mm=args.b, tw_mm=args.tw,
        tf_mm=args.tf, d_mm=args.d, weight_kg_m=args.weight)
    props = service._section_properties(section)
    print(f"Sección creada: {section.code} "
          f"(A={props.area_m2*1e4:.1f} cm2, Ix={props.ix_m4*1e8:.0f} cm4, "
          f"{props.weight_kg_m:.1f} kg/m)")
    context.close()
    return 0


def cmd_struct_element_add(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    point_loads = [(a, p) for a, p in args.point]
    attrs = {}
    if args.axial:
        attrs["axial_kn"] = args.axial
    if args.support:
        attrs["support"] = args.support.upper()
    element = service.create_element(
        args.kind, args.name, level_ref=args.level, material_ref=args.material,
        section_ref=args.section, start=tuple(args.start), end=tuple(args.end),
        z0=args.z0, z1=args.z1, load_udl_kn_m=args.udl,
        point_loads=point_loads, attrs=attrs, space_ref=args.space)
    print(f"Elemento estructural creado: {element.code} ({element.kind}, "
          f"L={element.length_m:.2f} m)")
    context.close()
    return 0


def cmd_struct_element_list(application, args) -> int:
    context = _open(application, args)
    where, params = ("kind = ?", (args.kind,)) if args.kind else ("", ())
    elements = context.structure.list("ELEMENT", context.project.id, where, params)
    rows = [[e.code, e.kind, e.name, f"{e.length_m:.2f}",
             f"{e.num('axial_kn'):.1f}", f"{e.num('moment_max_knm'):.1f}",
             f"{e.num('utilization'):.2f}" if e.num("utilization") else "-"]
            for e in elements]
    _print_table(rows, ["Código", "Tipo", "Nombre", "L (m)",
                        "N (kN)", "M (kN·m)", "Util."])
    context.close()
    return 0


def cmd_struct_element_delete(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    code = service.delete_element(args.element)
    print(f"Elemento eliminado: {code}")
    context.close()
    return 0


def cmd_struct_case_add(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    load_case = service.create_load_case(args.name, args.kind, factor=args.factor)
    print(f"Acción creada: {load_case.code} ({load_case.kind}, "
          f"γ={load_case.factor:.2f})")
    context.close()
    return 0


def cmd_struct_combo_add(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    factors = {}
    for part in args.factors.split(","):
        kind, value = part.split("=")
        factors[kind.strip().upper()] = float(value)
    combination = service.create_combination(args.name, factors)
    print(f"Combinación creada: {combination.code} {combination.case_factors}")
    context.close()
    return 0


def cmd_struct_defaults(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    combinations = service.ensure_default_combinations()
    if combinations:
        for combination in combinations:
            print(f"Combinación creada: {combination.code} "
                  f"{combination.name} {combination.case_factors}")
    else:
        print("Las combinaciones estándar ya existen")
    context.close()
    return 0


def cmd_struct_analyze(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    report = service.analyze_element(args.element, combination_ref=args.combination)
    print(f"Análisis de {report['element']} ({report['kind']}, "
          f"L={report['length_m']:.2f} m)")
    if "beam" in report:
        beam = report["beam"]
        print(f"  Reacciones: A={beam['reaction_a_kn']:.2f} kN, "
              f"B={beam['reaction_b_kn']:.2f} kN")
        print(f"  Cortante máx: {beam['shear_max_kn']:.2f} kN | "
              f"Momento máx: {beam['moment_max_knm']:.2f} kN·m | "
              f"Flecha: {beam['deflection_mm']:.2f} mm")
    if "column" in report:
        column = report["column"]
        print(f"  Axil: {column['axial_kn']:.1f} kN | esbeltez "
              f"{column['slenderness']:.1f} | Ncr Euler {column['euler_critical_kn']:.0f} kN")
        print(f"  Capacidad: {column['capacity_kn']:.1f} kN | "
              f"utilización {column['utilization']:.2f} "
              f"({'OK' if column['ok'] else 'AGOTADO'})")
    if "bending" in report:
        bending = report["bending"]
        print(f"  Flexión: σ={bending['sigma_mpa']:.1f} MPa "
              f"/ {bending['allowable_mpa']:.1f} MPa -> utilización "
              f"{bending['utilization']:.2f} ({'OK' if bending['ok'] else 'AGOTADO'})")
    context.close()
    return 0


def cmd_struct_truss(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    report = service.analyze_truss(args.element)
    result = report["result"]
    print(f"Cercha {report['element']}: "
          f"({'resuelta' if result['ok'] else 'NO resuelta: ' + result['reason']})")
    if result["ok"]:
        rows = [[mid, ("Tensión" if state == "T" else "Compresión"),
                 f"{force:.2f}"]
                for mid, (state, force) in result["members"].items()]
        _print_table(rows, ["Barra", "Esfuerzo", "N (kN)"])
        for node, reaction in result["reactions"].items():
            print(f"  Reacción {node}: ({reaction[0]:.2f}, {reaction[1]:.2f}) kN")
        if report.get("steel_weight_kg"):
            print(f"  Peso de acero: {report['steel_weight_kg']:.1f} kg")
        if report.get("quantities"):
            q = report["quantities"]
            print(f"  Barras: {q['member_count']:.0f} | longitud total "
                  f"{q['total_length_m']:.1f} m | placas {q['gusset_plates']:.0f} | "
                  f"soldadura {q['weld_total_mm']:.0f} mm")
        if report.get("utilization"):
            worst = max(report["utilization"].items(), key=lambda kv: kv[1])
            print(f"  Utilización máxima: {worst[1]:.2f} (barra {worst[0]})")
    context.close()
    return 0 if result["ok"] else 1


def cmd_struct_connection_check(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    report = service.check_connection(
        args.bolts, args.bolt_d, args.weld_length, args.weld_throat, args.demand)
    print(f"Unión: pernos {report['bolt_capacity_kn']:.1f} kN | "
          f"soldadura {report['weld_capacity_kn']:.1f} kN | "
          f"gobierna {report['governing_kn']:.1f} kN")
    print(f"Demanda {report['demand_kn']:.1f} kN -> utilización "
          f"{report['utilization']:.2f} ({'OK' if report['ok'] else 'AGOTADA'})")
    context.close()
    return 0 if report["ok"] else 1


def cmd_struct_report(application, args) -> int:
    context = _open(application, args)
    service = _struct_service(context)
    report = service.utilization_report()
    print(f"Utilización de elementos ({report['count']} lineales):")
    rows = [[r["element"], r["kind"], f"{r['length_m']:.2f}",
             f"{r['axial_kn']:.1f}", f"{r['moment_knm']:.1f}",
             f"{r['utilization']:.2f}", "OK" if r["ok"] else "AGOTADO"]
            for r in report["rows"]]
    _print_table(rows, ["Elemento", "Tipo", "L (m)", "N (kN)",
                        "M (kN·m)", "Util.", "Estado"])
    quantities = service.steel_quantities()
    print(f"Acero total: {quantities['steel_weight_kg']:.1f} kg | "
          f"longitud total {quantities['total_length_m']:.1f} m")
    context.close()
    return 0


# -- security commands (spec 37-49) ---------------------------------------------------
def _security_service(context):
    from services.security_service import SecurityService
    return SecurityService(context)


def _parse_attrs(pairs) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    for key, value in pairs:
        try:
            attrs[key] = float(value) if "." in value else int(value)
        except ValueError:
            attrs[key] = value
    return attrs


def cmd_sec_net(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    network = service.create_network(args.name, args.system)
    print(f"Red de seguridad creada: {network.code} ({network.system})")
    context.close()
    return 0


def cmd_sec_device_add(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    device = service.add_device(
        args.network, args.kind.upper(), args.x, args.y, name=args.name,
        elevation_m=args.elevation, attrs=_parse_attrs(args.attr),
        level_ref=args.level, space_ref=args.space)
    print(f"Dispositivo creado: {device.code} ({device.kind}) en "
          f"({device.x:.2f}, {device.y:.2f})")
    context.close()
    return 0


def cmd_sec_coverage(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    report = service.cctv_coverage(args.network, space_ref=args.space)
    print(f"Cobertura CCTV de {report['network']} "
          f"({report['cameras']} cámaras)")
    _print_table([[r["camera"], f"{r['area_m2']:.1f}", f"{r['fov_deg']:.0f}",
                   f"{r['range_m']:.0f}", str(r["occluded_rays"])]
                  for r in report["rows"]],
                 ["Cámara", "Cobertura m2", "FOV °", "Alcance m", "Rayos cortados"])
    blind = report["blind"]
    print(f"Puntos ciegos: {blind['blind_pct']:.1f} % "
          f"({blind['target_m2']:.1f} m2 objetivo, {blind['covered_m2']:.1f} m2 cubiertos)")
    if report.get("best_camera"):
        print(f"Mejor cámara: {report['best_camera']['camera']} "
              f"({report['best_camera']['area_m2']:.1f} m2)")
    context.close()
    return 0


def cmd_sec_network(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    report = service.cctv_network(args.network, retention_days=args.retention)
    data = report["report"]
    print(f"Red CCTV de {report['network']} ({data['cameras']} cámaras):")
    print(f"  Ancho de banda: {data['bandwidth_mbps']:.1f} Mbps "
          f"(bitrate {data['total_bitrate_mbps']:.1f} Mbps + overhead)")
    print(f"  Almacenamiento: {data['storage_gb']:.0f} GB "
          f"({data['retention_days']:.0f} días)")
    print(f"  PoE: {data['poe_demand_w']:.1f} W de {data['poe_budget_w']:.0f} W | "
          f"switch {data['switch_channels']} canales, NVR {data['nvr_channels']}")
    for finding in data["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0


def cmd_sec_cabling(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    report = service.cctv_cabling(args.network)
    totals = report["totals"]
    print(f"Cableado CCTV de {report['network']} ({totals['cameras']} cámaras): "
          f"{totals['total_cable_m']:.1f} m totales")
    _print_table([[r["camera"], f"{r['route_m']:.1f}", f"{r['cable_m']:.1f}"]
                  for r in report["rows"]],
                 ["Cámara", "Ruta m", "Cable m"])
    context.close()
    return 0


def cmd_sec_fire_check(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    report = service.fire_check(args.network)
    print(f"Detección de incendios {report['network']}: {report['status']}")
    for row in report["coverage"]:
        print(f"  {row['space']}: {row['installed']}/{row['required']} "
              f"detectores ({row['area_m2']:.1f} m2, radio {row['radius_m']:.1f} m)")
    loop = report["loop"]
    print(f"  Lazo: {loop['devices']} dispositivos | reposo {loop['standby_ma']:.1f} mA | "
          f"batería {loop['battery_ah']:.2f} Ah")
    for finding in report["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0 if report["status"] != "INVALID" else 1


def cmd_sec_cause_effect(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    context_vars = {k: v for k, v in
                    ((p[0], p[1] in ("1", "true", "True")) for p in args.var)}
    report = service.fire_cause_effect(args.network, args.input, context_vars)
    result = report["result"]
    print(f"Causa/efecto {report['network']} — entrada {report['input']}: "
          f"{len(result['triggered'])} acciones")
    _print_table([[t["rule"], t["action"], t["output"],
                   f"{t['delay_s']:.0f}"] for t in result["triggered"]],
                 ["Regla", "Acción", "Salida", "Retardo s"])
    for missing in result["missing_rules"]:
        print(f"  AVISO: sin regla para {missing}")
    context.close()
    return 0 if result["ok"] else 1


def cmd_sec_intrusion_check(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    report = service.intrusion_check(args.network)
    print(f"Intrusión {report['network']}: {report['status']}")
    for row in report["zones"]:
        print(f"  {row['zone']}: {row['installed_pirs']}/{row['required_pirs']} PIR, "
              f"{row['perimeter_contacts']} contactos ({row['area_m2']:.1f} m2)")
    panel = report["panel"]
    print(f"  Panel: {panel['zones']} zonas | batería {panel['battery_ah']:.2f} Ah | "
          f"sirenas {panel['sirens']}")
    for finding in report["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0 if report["status"] != "INVALID" else 1


def cmd_sec_access_check(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    report = service.access_check(args.network)
    print(f"Control de acceso {report['network']}: {report['status']}")
    power = report["power"]
    print(f"  Demanda {power['demand_a']:.2f} A / fuente {power['supply_a']:.1f} A | "
          f"batería {power['battery_ah']:.2f} Ah")
    for finding in report["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0 if report["status"] == "VALID" else 1


def cmd_sec_perimeter_check(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    report = service.perimeter_check(args.network)
    data = report["report"]
    print(f"Perímetro {report['network']}: "
          f"{'OK' if data['ok'] else 'CON HUECOS'}")
    print(f"  Valla: {data['fence_length_m']:.1f} m en {data['segments']} tramos | "
          f"sensores {data['installed_sensors']}/{data['required_sensors']} | "
          f"cámaras {data['installed_cameras']}/{data['required_cameras']}")
    print(f"  Puertas: {data['gates']} | barreras: {data['barriers']} | "
          f"puntos de acceso: {data['access_points']}")
    for finding in data["findings"]:
        print(f"  AVISO: {finding}")
    context.close()
    return 0 if data["ok"] else 1


def cmd_sec_bom(application, args) -> int:
    context = _open(application, args)
    service = _security_service(context)
    report = service.security_bom()
    print(f"BOM de seguridad ({report['total_devices']} dispositivos):")
    _print_table([[item["kind"], str(item["count"]),
                   ", ".join(item["networks"])] for item in report["items"]],
                 ["Dispositivo", "Unidades", "Redes"])
    context.close()
    return 0


# -- coordination / clash commands (spec 35-36) ---------------------------------------
def _coordination_service(context):
    from services.coordination_service import CoordinationService
    return CoordinationService(context)


def cmd_clash_run(application, args) -> int:
    context = _open(application, args)
    service = _coordination_service(context)
    systems = [s.strip().upper() for s in args.systems.split(",") if s.strip()]
    report = service.run_detection(systems_filter=systems or None)
    print(f"Detección de interferencias: {report['created']} nuevas, "
          f"{report['duplicates_skipped']} duplicadas omitidas, "
          f"{report['open']} abiertas")
    if report["by_type"]:
        for clash_type, count in sorted(report["by_type"].items()):
            print(f"  {clash_type}: {count}")
    for row in report["clashes"]:
        print(f"  {row['code']} [{row['severity']}] {row['type']}: "
              f"{row['a']} <-> {row['b']} ({row['rule']})")
    context.close()
    return 0


def cmd_clash_list(application, args) -> int:
    context = _open(application, args)
    service = _coordination_service(context)
    rows = service.list_clashes(status=args.status, clash_type=args.clash_type)
    _print_table([[r["code"], r["type"], r["severity"], r["status"],
                   r["a"], r["b"], f"{r['distance']:.2f}"] for r in rows],
                 ["Código", "Tipo", "Severidad", "Estado", "Objeto A",
                  "Objeto B", "Dist. m"])
    context.close()
    return 0


def cmd_clash_status(application, args) -> int:
    context = _open(application, args)
    service = _coordination_service(context)
    clash = service.set_status(args.clash, args.new_status, notes=args.notes)
    print(f"Interferencia {clash.code}: estado {clash.status}")
    context.close()
    return 0


# -- PRECONS / SIECONS-like commands (spec 59-60) --------------------------------------
def _precons_service(context, ruleset_code):
    from services.precons_service import PreconsService
    service = PreconsService(context)
    service.load_ruleset(ruleset_code)
    return service


def cmd_precons_list(application, args) -> int:
    context = _open(application, args)
    service = _precons_service(context, args.ruleset)
    ruleset = service.ruleset
    if getattr(args, "seccion", "") or getattr(args, "buscar", ""):
        items = service.search_items(getattr(args, "buscar", ""),
                                     section=getattr(args, "seccion", ""),
                                     limit=max(int(getattr(args, "limite", 50)), 0)
                                     or len(ruleset.work_items))
        total = len(ruleset.search(args.buscar, section=args.seccion,
                                   limit=len(ruleset.work_items)))
        print(f"Ruleset {ruleset.code} v{ruleset.version} — "
              f"{total} coincidencias (mostrando {len(items)})")
    else:
        items = list(ruleset.work_items)
        limite = max(int(getattr(args, "limite", 0) or 0), 0)
        total = len(items)
        if limite:
            items = items[:limite]
        print(f"Ruleset {ruleset.code} v{ruleset.version} "
              f"({total} partidas, {len(ruleset.resources)} recursos)"
              + (f" — mostrando {len(items)} (use --limite 0 para todos)"
                 if limite and limite < total else ""))
    _print_table([[i["code"], i.get("name", "")[:60], i.get("unit", ""),
                   (f"{i['price_ref']:.2f}"
                    if i.get("price_ref") is not None else
                    i.get("qto_formula", "")),
                   str(len(i.get("indicators", [])))]
                  for i in items],
                 ["Partida", "Descripción", "Unidad", "Precio CUP", "Renglones"])
    context.close()
    return 0


def cmd_precons_precio(application, args) -> int:
    context = _open(application, args)
    service = _precons_service(context, args.ruleset)
    price = service.official_price(args.item)
    quantity = float(args.quantity or 1.0)
    print(f"Renglón {price['item']} — {service.ruleset.item(args.item).get('name', '')} "
          f"[{price['unit']}] — {price['section']}")
    print(f"  Precio oficial unitario: {price['total']:.2f} {price['currency']}")
    print(f"    Materiales: {price['material']:.2f} | Mano de obra: "
          f"{price['labor']:.2f} | Equipos: {price['equipment']:.2f}")
    print(f"  Cantidad {quantity:.2f} {price['unit']} -> "
          f"TOTAL {price['total'] * quantity:.2f} {price['currency']}")
    context.close()
    return 0


def cmd_precons_analyze(application, args) -> int:
    context = _open(application, args)
    service = _precons_service(context, args.ruleset)
    analysis = service.analyze_item(args.item, args.quantity, variant=args.variant)
    print(f"Análisis {analysis.item} — {analysis.name} "
          f"({analysis.quantity:.2f} {analysis.unit}, variante {analysis.variant})")
    _print_table([[line["resource"], line["name"], f"{line['quantity']:.2f}",
                   line["unit"], f"{line['price']:.2f}", f"{line['cost']:.2f}"]
                  for line in analysis.lines],
                 ["Recurso", "Nombre", "Cantidad", "Unidad", "Precio", "Costo"])
    print(f"  Directo: {analysis.direct_cost:.2f} | indirectos "
          f"{analysis.indirect_pct:.1f}% = {analysis.indirect_cost:.2f} | "
          f"beneficio {analysis.benefit_pct:.1f}% = {analysis.benefit:.2f}")
    print(f"  Precio unitario: {analysis.unit_price:.2f} {analysis.currency} | "
          f"total {analysis.total_price:.2f} {analysis.currency}")
    context.close()
    return 0


def cmd_precons_project(application, args) -> int:
    context = _open(application, args)
    service = _precons_service(context, args.ruleset)
    report = service.analyze_project(variant=args.variant)
    print(f"Análisis PRECONS del proyecto ({report['ruleset']} "
          f"v{report['version']}, variante {report['variant']}):")
    _print_table([[a["item"], a["name"], f"{a['quantity']:.2f}", a["unit"],
                   f"{a['unit_price']:.2f}", f"{a['total_price']:.2f}"]
                  for a in report["analyses"]],
                 ["Partida", "Descripción", "Cantidad", "Unidad",
                  "P. unitario", "Total"])
    for skipped in report["skipped"]:
        print(f"  OMITIDA {skipped['item']}: {skipped['reason']}")
    print(f"TOTAL PRECONS: {report['total']:.2f} {report['currency']}")
    context.close()
    return 0


def cmd_precons_compare(application, args) -> int:
    context = _open(application, args)
    service = _precons_service(context, args.ruleset)
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    report = service.compare_variants(args.item, args.quantity, variants=variants)
    _print_table([[r["variant"], r["item"], f"{r['unit_price']:.2f}",
                   f"{r['total_price']:.2f}", r["currency"]]
                  for r in report["rows"]],
                 ["Variante", "Partida", "P. unitario", "Total", "Moneda"])
    context.close()
    return 0


def cmd_precons_import(application, args) -> int:
    context = _open(application, args)
    from services.precons_service import PreconsService
    import json
    if args.data.lower().endswith((".xlsx", ".xlsm", ".csv", ".txt")):
        mapping = {}
        if args.mapping:
            with open(args.mapping, "r", encoding="utf-8") as handle:
                mapping = json.load(handle)
        mapping.setdefault("code", args.code)
        from importers.catalog import CatalogImporter
        importer = CatalogImporter(mapping=mapping)
        _, report = importer.apply(args.data, code=args.code, out_path=args.out)
        _print_import_report(report)
        context.close()
        return 1 if report["errors"] else 0
    if not args.mapping:
        print("[ERROR] --mapping es obligatorio cuando --data es JSON")
        context.close()
        return 1
    with open(args.data, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    with open(args.mapping, "r", encoding="utf-8") as handle:
        mapping = json.load(handle)
    service = PreconsService(context)
    ruleset = service.import_ruleset(data, mapping, code=args.code,
                                     out_path=args.out)
    print(f"Ruleset importado: {ruleset.code} "
          f"({len(ruleset.work_items)} partidas, {len(ruleset.resources)} recursos)")
    if args.out:
        print(f"Guardado en: {args.out}")
    context.close()
    return 0


def cmd_precons_certificar(application, args) -> int:
    """Certificación del catálogo embebido (no requiere proyecto)."""
    import json

    from services.precons_service import certificar_catalogo
    report = certificar_catalogo(getattr(args, "ruleset",
                                         "precons_iii_rospres_330"))
    public = {k: v for k, v in report.items() if k not in ("path",)}
    print(json.dumps(public, ensure_ascii=False, indent=2))
    if report["ok"]:
        print(f"CERTIFICADO: catálogo {report['code']} v{report['version']} "
              f"íntegro (sha256 {report['sha256'][:16]}…, "
              f"{report['bytes']} bytes)")
        return 0
    print("ERRORES:")
    for failure in report["failures"]:
        print(f"  - {failure}")
    return 1


def cmd_detalles_regiones(application, args) -> int:
    """Ediciones regionales instaladas (no requiere proyecto)."""
    from domain.detalles import get_registry
    registry = get_registry()
    print("BIBLIOTECA DE DETALLES CONSTRUCTIVOS — ediciones instaladas")
    print(f"  base: biblioteca universal "
          f"({len(registry)} detalles, v{registry.version or '?'})")
    regions = registry.available_regions()
    if not regions:
        print("  (sin ediciones regionales instaladas)")
        return 0
    for info in regions:
        print(f"  {info['codigo']}: {info['nombre']} — {info['edicion']} "
              f"[{info['archivo']}]")
    print("Usa --region <codigo> en `detalles list|ver|svg|pdf|png|"
          "tipologia` para activarla.")
    return 0


def cmd_detalles_list(application, args) -> int:
    """Lista de detalles de la edición activa (no requiere proyecto)."""
    from domain.detalles import get_registry
    registry = get_registry()
    if not registry.set_region(getattr(args, "region", "base")):
        print(f"ERROR [ARQ-DOM-013] Edición regional sin fichero: "
              f"{args.region}")
        print("  Sugerencia: `detalles regiones` lista las instaladas.")
        return 1
    categoria = (getattr(args, "categoria", "") or "").strip().lower()
    rows = registry.list_details(categoria=categoria,
                                 texto=getattr(args, "buscar", ""))
    tag = registry.region_tag()
    if categoria and categoria not in registry.categories():
        print(f"ERROR [ARQ-DOM-013] Categoría desconocida: {categoria}")
        print("  Sugerencia: " + ", ".join(registry.categories()))
        return 1
    print(f"DETALLES{tag}: {len(rows)} coincidencias "
          f"({registry.region_name})")
    limite = int(getattr(args, "limite", 50) or 0)
    mostrados = rows[:limite] if limite else rows
    for detalle in mostrados:
        marcador = "*" if detalle.regional else " "
        print(f" {marcador} {detalle.id} — {detalle.nombre} "
              f"[{detalle.espesor_total_mm:g} mm]")
    if limite and len(rows) > limite:
        print(f"  … {len(rows) - limite} más (usa --limite 0 para ver todos)")
    print("(*) detalle propio de la edición regional")
    return 0


def cmd_detalles_ver(application, args) -> int:
    """Ficha completa de un detalle (no requiere proyecto)."""
    from domain.detalles import get_registry
    registry = get_registry()
    if not registry.set_region(getattr(args, "region", "base")):
        print(f"ERROR [ARQ-DOM-013] Edición regional sin fichero: "
              f"{args.region}")
        return 1
    detalle = registry.get(args.id)
    if detalle is None:
        print(f"ERROR [ARQ-DOM-013] Detalle no encontrado: {args.id}"
              f"{registry.region_tag()}")
        print("  Sugerencia: `detalles list --region "
              f"{getattr(args, 'region', 'base')}` lista los disponibles.")
        return 1
    print(detalle.ficha())
    if registry.disclaimer:
        print()
        print("Aviso: " + registry.disclaimer)
    return 0


def cmd_detalles_svg(application, args) -> int:
    """Exporta el esquema SVG acotado del detalle (no requiere proyecto)."""
    from exporters.detalle_svg import export_detalle_svg
    return _cmd_detalles_dibujo("svg", export_detalle_svg,
                                "Esquema SVG del detalle generado", args)


def cmd_detalles_pdf(application, args) -> int:
    """Exporta el detalle en PDF vectorial A4 (v3.6.0)."""
    from exporters.detalle_export import export_detalle_pdf
    return _cmd_detalles_dibujo("pdf", export_detalle_pdf,
                                "PDF del detalle generado", args)


def cmd_detalles_png(application, args) -> int:
    """Exporta el detalle en PNG raster 2x (v3.6.0)."""
    from exporters.detalle_export import export_detalle_png
    return _cmd_detalles_dibujo("png", export_detalle_png,
                                "PNG del detalle generado", args)


def _cmd_detalles_dibujo(fmt: str, exportador, verbo: str, args) -> int:
    """Común de `detalles svg|pdf|png`: región + detalle + export."""
    from domain.detalles import get_registry
    registry = get_registry()
    if not registry.set_region(getattr(args, "region", "base")):
        print(f"ERROR [ARQ-DOM-013] Edición regional sin fichero: "
              f"{args.region}")
        return 1
    detalle = registry.get(args.id)
    if detalle is None:
        print(f"ERROR [ARQ-DOM-013] Detalle no encontrado: {args.id}"
              f"{registry.region_tag()}")
        return 1
    path = exportador(detalle, args.archivo,
                      region_label=registry.region_name)
    print(f"{verbo}: {path}")
    print(f"  {detalle.etiqueta_corta()} — "
          f"{detalle.espesor_total_mm:g} mm{registry.region_tag()}")
    return 0


def cmd_detalles_tipologia(application, args) -> int:
    """Recomendados de la biblioteca para una tipología del asistente
    (no requiere proyecto; v3.6.0)."""
    from domain.detalles import (TIPOLOGIA_DETALLES, buscar_tipologia,
                                 detalles_para_tipologia, get_registry,
                                 tipologias)
    registry = get_registry()
    if not registry.set_region(getattr(args, "region", "base")):
        print(f"ERROR [ARQ-DOM-013] Edición regional sin fichero: "
              f"{args.region}")
        return 1
    categoria = (getattr(args, "categoria", "") or "").strip().lower()
    if categoria and categoria not in registry.categories():
        print(f"ERROR [ARQ-DOM-013] Categoría desconocida: {categoria}")
        print("  Sugerencia: " + ", ".join(registry.categories()))
        return 1
    try:
        tipo = buscar_tipologia(args.tipologia)
    except ValueError as exc:
        print(f"ERROR [ARQ-DOM-013] {exc}")
        return 1
    if not tipo:
        print(f"ERROR [ARQ-DOM-013] Tipología no reconocida: "
              f"{args.tipologia}")
        print("  Sugerencia: " + " | ".join(tipologias()))
        return 1
    presentes = detalles_para_tipologia(registry, tipo, categoria=categoria)
    faltantes = [did for did in TIPOLOGIA_DETALLES.get(tipo, ())
                 if registry.get(did) is None]
    tag = registry.region_tag()
    print(f"RECOMENDADOS PARA «{tipo}»{tag}: "
          f"{len(presentes)} detalles ({registry.region_name})")
    for detalle in presentes:
        marcador = "*" if detalle.regional else " "
        print(f" {marcador} {detalle.id} — {detalle.nombre} "
              f"[{detalle.espesor_total_mm:g} mm]")
    if faltantes:
        print("No están en esta edición (retirados o aún sin ficha): "
              + ", ".join(faltantes))
    print("(*) detalle propio de la edición regional")
    if registry.disclaimer:
        print("Aviso: " + registry.disclaimer)
    return 0


def cmd_precons_budget(application, args) -> int:
    """Presupuesto por catálogo PRECONS III (v2.0.0)."""
    context = _open(application, args)
    from services.precons_budget_service import PreconsBudgetService
    service = PreconsBudgetService(context)
    service.load_ruleset(args.ruleset)

    def _pairs(pairs: list) -> list:
        out = []
        for raw in pairs:
            code, _, qty = raw.partition(":")
            out.append((code.strip(), float(qty.replace(",", ".") or 1.0)))
        return out

    changed = False
    if getattr(args, "clear", False):
        removed = service.clear()
        print(f"Presupuesto vaciado ({removed} líneas)")
        changed = True
    for code, quantity in _pairs(args.add):
        view = service.add_item(code, quantity)
        print(f"AÑADIDO {view['code']} × {quantity:g} {view['unit']} = "
              f"{view['amount']:.2f} {service.ruleset.currency}")
        changed = True
    for code, quantity in _pairs(args.set_qty):
        view = service.set_quantity(code, quantity)
        print(f"ACTUALIZADO {view['code']} × {quantity:g} {view['unit']} = "
              f"{view['amount']:.2f} {service.ruleset.currency}")
        changed = True
    for code in args.remove:
        service.remove_item(code)
        print(f"QUITADO {code}")
        changed = True

    totals = service.totals()
    if args.show or not (changed or args.export_csv or args.export_pdf
                         or args.chart_png):
        lines = service.lines()
        print(f"Presupuesto PRECONS III ({service.ruleset.code} "
              f"v{service.ruleset.version}) — {len(lines)} líneas:")
        _print_table(
            [[l["code"], l["description"][:52], l["unit"],
              f"{l['quantity']:g}", f"{l['unit_price']:.2f}",
              f"{l['amount']:.2f}"] for l in lines],
            ["Código", "Descripción", "Ud", "Cantidad", "P. unit",
             "Importe"])
    currency = service.ruleset.currency
    print(f"Directo {totals['direct']:.2f} | transporte "
          f"{totals['transport']:.2f} | indirectos {totals['indirect']:.2f} | "
          f"beneficio {totals['benefit']:.2f}")
    print(f"TOTAL PRESUPUESTO: {totals['total']:.2f} {currency}")
    if args.export_csv:
        path = service.save_csv(args.export_csv)
        print(f"CSV exportado: {path}")
    if args.export_pdf:
        from exporters.pdf_exporter import export_budget_pdf
        tree = service.tree()
        path = export_budget_pdf(tree, args.export_pdf,
                                 context.project.name)
        print(f"PDF exportado: {path}")
    if args.chart_png:
        from exporters.png_exporter import export_budget_chart_png
        tree = service.tree()
        path = export_budget_chart_png(tree, args.chart_png,
                                       context.project.name)
        print(f"Gráfico PNG exportado: {path}")
    context.close()
    return 0


def _print_import_report(report: dict, prices: dict | None = None) -> None:
    import json as _json
    public = {k: v for k, v in report.items() if not k.startswith("_")}
    print(_json.dumps(public, ensure_ascii=False, indent=2, default=str))
    if prices:
        print("Precios detectados (cargan con 'price set'):",
              _json.dumps(prices, ensure_ascii=False, default=str))


def cmd_importar_catalogo(application, args) -> int:
    import json
    from importers.catalog import CatalogImporter
    mapping: dict = {}
    if args.mapping:
        with open(args.mapping, "r", encoding="utf-8") as handle:
            mapping = json.load(handle)
    mapping.setdefault("code", args.code)
    if args.nombre:
        mapping["name"] = args.nombre
    importer = CatalogImporter(mapping=mapping)
    if not args.out:
        _, report, prices = importer.convert(args.archivo)
        _print_import_report(report, prices)
        return 1 if report["errors"] else 0
    _, report = importer.apply(args.archivo, code=args.code,
                               name=args.nombre, out_path=args.out)
    _print_import_report(report)
    return 1 if report["errors"] else 0


def cmd_importar_dwg(application, args) -> int:
    from importers.dwg_reader import DwgGateway
    prep = DwgGateway().prepare(args.archivo, converter=args.convertidor)
    version = prep.get("version", {})
    for note in prep.get("notes", []):
        print(f"NOTA: {note}")
    if not prep["ok"]:
        for error in prep.get("errors", []):
            print(f"ERROR: {error}")
        return 1
    print(f"DWG {version.get('code', '?')} ({version.get('label', '?')}) "
          f"convertido con {prep['converter']}")
    print(f"DXF temporal: {prep['dxf_path']}")
    args.archivo = prep["dxf_path"]
    return cmd_importar_dxf(application, args)


def cmd_importar_dxf(application, args) -> int:
    from importers.dxf_reader import DxfImporter
    from services.architecture_service import ArchitectureService
    importer = DxfImporter(layer_walls=args.capa_muros,
                           layer_spaces=args.capa_locales)
    report = importer.preview(args.archivo)
    _print_import_report(report)
    if report["errors"]:
        return 1
    if not args.aplicar:
        print("PREVIEW: ninguna entidad creada. Repita con --aplicar para importar.")
        return 0
    context = _open(application, args)
    context.user = getattr(args, "user", "local")
    try:
        counts = importer.apply(
            args.archivo, ArchitectureService(context), args.nivel,
            thickness_m=args.espesor, height_m=args.altura or None)
        context.commit()
        print(f"Importados {counts['walls']} muros y {counts['spaces']} locales "
              f"en el nivel '{counts['level']}'.")
        return 0
    except Exception:
        context.rollback()
        raise
    finally:
        context.close()


# -- BIM commands (spec 63, 67) --------------------------------------------------------
def _bim_service(context):
    from services.bim_service import BimService
    return BimService(context)


def cmd_bim_tree(application, args) -> int:
    context = _open(application, args)
    service = _bim_service(context)
    tree = service.bim_tree()
    print(f"BIM: {tree['project']['name']}")
    print(f"  IfcSite: {tree['site']['name']} | IfcBuilding: "
          f"{tree['building']['name']}")
    for storey in tree["storeys"]:
        print(f"  IfcBuildingStorey {storey['name']} "
              f"({storey['elevation_m']:.2f} m): "
              f"{len(storey['spaces'])} IfcSpace, {len(storey['walls'])} IfcWall, "
              f"{len(storey['elements'])} estructura, "
              f"{len(storey['devices'])} dispositivos")
    print(f"  Vanos: {len(tree['openings'])} (IfcDoor/IfcWindow) | "
          f"Redes: {len(tree['networks'])} (IfcDistributionSystem)")
    context.close()
    return 0


def cmd_bim_show(application, args) -> int:
    import json as _json
    context = _open(application, args)
    service = _bim_service(context)
    from services.commands_impl import _repo_for as _repo  # noqa: F401
    # Resolución por código en los repositorios conocidos.
    record = None
    for entity_type in ("WALL", "SPACE", "DOOR", "WINDOW", "LEVEL", "ZONE",
                        "NODE", "SEGMENT", "NETWORK", "ELEMENT", "MATERIAL",
                        "SECTION"):
        entity = context.architecture.get_by_code(entity_type, args.ref)
        if entity is None and entity_type in ("NODE", "SEGMENT", "NETWORK"):
            entity = context.installations.get_by_code(entity_type, args.ref)
        if entity is None and entity_type in ("ELEMENT", "MATERIAL", "SECTION"):
            entity = context.structure.get_by_code(entity_type, args.ref)
        if entity is not None:
            record = service._record(entity)
            break
    if record is None:
        for entity_type in ("NODE", "SEGMENT", "NETWORK", "ELEMENT"):
            repo = (context.installations if entity_type in
                    ("NODE", "SEGMENT", "NETWORK") else context.structure)
            entity = repo.get_by_code(entity_type, args.ref)
            if entity is not None:
                record = service._record(entity)
                break
    if record is None:
        print(f"Objeto no encontrado: {args.ref}")
        context.close()
        return 1
    print(f"Registro BIM de {record['code']} ({record['category']}, "
          f"clasificación {record['classification']}):")
    print(f"  Nombre: {record['name']} | nivel: {record['level'] or '-'} | "
          f"material: {record['material'] or '-'}")
    print(f"  Sistemas: {', '.join(record['systems']) or '-'}")
    print(f"  Geometría: {_json.dumps(record['geometry'], ensure_ascii=False)}")
    print(f"  Propiedades: {_json.dumps(record['properties'], ensure_ascii=False)[:400]}")
    for relation in record["relationships"]:
        print(f"  ↳ {relation['kind']}: {relation['target']} "
              f"({relation['category']})")
    context.close()
    return 0


# -- entry point ------------------------------------------------------------------
HANDLERS = {
    ("project", "create"): cmd_project_create,
    ("project", "info"): cmd_project_info,
    ("level", "add"): cmd_level_add,
    ("level", "list"): cmd_level_list,
    ("zone", "add"): cmd_zone_add,
    ("zone", "list"): cmd_zone_list,
    ("space", "add"): cmd_space_add,
    ("space", "list"): cmd_space_list,
    ("wall", "add"): cmd_wall_add,
    ("wall", "list"): cmd_wall_list,
    ("wall", "move"): cmd_wall_move,
    ("door", "add"): _cmd_opening_add("DOOR"),
    ("door", "list"): _cmd_opening_list("DOOR"),
    ("window", "add"): _cmd_opening_add("WINDOW"),
    ("window", "list"): _cmd_opening_list("WINDOW"),
    (None, "undo"): cmd_undo,
    (None, "redo"): cmd_redo,
    ("relationships", "recompute"): cmd_relationships_recompute,
    ("relationships", "report"): cmd_relationships_report,
    (None, "validate"): cmd_validate,
    (None, "instalar"): cmd_instalar,
    ("qto", "compute"): cmd_qto_compute,
    ("qto", "show"): cmd_qto_show,
    ("resource", "add"): cmd_resource_add,
    ("resource", "list"): cmd_resource_list,
    ("price", "set"): cmd_price_set,
    ("price", "history"): cmd_price_history,
    ("budget", "compute"): cmd_budget_compute,
    ("budget", "show"): cmd_budget_show,
    (None, "export"): cmd_export,
    (None, "import"): cmd_import,
    ("version", "save"): cmd_version_save,
    ("version", "list"): cmd_version_list,
    ("version", "restore"): cmd_version_restore,
    ("backup", "create"): cmd_backup_create,
    ("backup", "list"): cmd_backup_list,
    ("backup", "restore"): cmd_backup_restore,
    ("audit", "show"): cmd_audit_show,
    ("events", "show"): cmd_events_show,
    ("net", "add"): cmd_net_add,
    ("net", "list"): cmd_net_list,
    ("net", "show"): cmd_net_show,
    ("net", "trace"): cmd_net_trace,
    ("net", "path"): cmd_net_path,
    ("net", "validate"): cmd_net_validate,
    ("net", "deadends"): cmd_net_deadends,
    ("node", "add"): cmd_node_add,
    ("node", "list"): cmd_node_list,
    ("node", "move"): cmd_node_move,
    ("link", "add"): cmd_link_add,
    ("link", "list"): cmd_link_list,
    ("link", "remove"): cmd_link_remove,
    ("elec", "check"): cmd_elec_check,
    ("elec", "summary"): cmd_elec_summary,
    ("elec", "balance"): cmd_elec_balance,
    ("san", "size"): cmd_san_size,
    ("plu", "size"): cmd_plu_size,
    ("gas", "size"): cmd_gas_size,
    ("gas", "check"): cmd_gas_check,
    ("tel", "size"): cmd_tel_size,
    ("hvac", "load"): cmd_hvac_load,
    ("hvac", "loads"): cmd_hvac_loads,
    ("hvac", "duct"): cmd_hvac_duct,
    ("hvac", "size-network"): cmd_hvac_size_network,
    ("struct", "material-add"): cmd_struct_material_add,
    ("struct", "section-add"): cmd_struct_section_add,
    ("struct", "element-add"): cmd_struct_element_add,
    ("struct", "element-list"): cmd_struct_element_list,
    ("struct", "element-delete"): cmd_struct_element_delete,
    ("struct", "case-add"): cmd_struct_case_add,
    ("struct", "combo-add"): cmd_struct_combo_add,
    ("struct", "defaults"): cmd_struct_defaults,
    ("struct", "analyze"): cmd_struct_analyze,
    ("struct", "truss"): cmd_struct_truss,
    ("struct", "connection-check"): cmd_struct_connection_check,
    ("struct", "report"): cmd_struct_report,
    ("sec", "net"): cmd_sec_net,
    ("sec", "device-add"): cmd_sec_device_add,
    ("sec", "coverage"): cmd_sec_coverage,
    ("sec", "network"): cmd_sec_network,
    ("sec", "cabling"): cmd_sec_cabling,
    ("sec", "fire-check"): cmd_sec_fire_check,
    ("sec", "cause-effect"): cmd_sec_cause_effect,
    ("sec", "intrusion-check"): cmd_sec_intrusion_check,
    ("sec", "access-check"): cmd_sec_access_check,
    ("sec", "perimeter-check"): cmd_sec_perimeter_check,
    ("sec", "bom"): cmd_sec_bom,
    ("clash", "run"): cmd_clash_run,
    ("clash", "list"): cmd_clash_list,
    ("clash", "status"): cmd_clash_status,
    ("precons", "list"): cmd_precons_list,
    ("precons", "precio"): cmd_precons_precio,
    ("precons", "analyze"): cmd_precons_analyze,
    ("precons", "project"): cmd_precons_project,
    ("precons", "compare"): cmd_precons_compare,
    ("precons", "import"): cmd_precons_import,
    ("precons", "budget"): cmd_precons_budget,
    ("precons", "certificar"): cmd_precons_certificar,
    ("detalles", "regiones"): cmd_detalles_regiones,
    ("detalles", "list"): cmd_detalles_list,
    ("detalles", "ver"): cmd_detalles_ver,
    ("detalles", "svg"): cmd_detalles_svg,
    ("detalles", "pdf"): cmd_detalles_pdf,
    ("detalles", "png"): cmd_detalles_png,
    ("detalles", "tipologia"): cmd_detalles_tipologia,
    ("importar", "catalogo"): cmd_importar_catalogo,
    ("importar", "dxf"): cmd_importar_dxf,
    ("importar", "dwg"): cmd_importar_dwg,
    ("bim", "tree"): cmd_bim_tree,
    ("bim", "show"): cmd_bim_show,
    (None, "demo"): cmd_demo,
    (None, "selftest"): cmd_selftest,
}


# FASES 34-43: merge the v1.3.0 command handlers (docs, optimize, audit,
# version, backup, plugins, benchmark).
from app.cli_fases import HANDLERS_13 as _HANDLERS_13  # noqa: E402

HANDLERS.update(_HANDLERS_13)


def run(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args = parser.parse_args(argv)
    # FASE A Tauri: el sidecar arranca LEAN (sin bootstrap del catálogo:
    # la generación lo carga bajo demanda) y toma el control de stdin.
    if getattr(args, "command", None) == "rpc":
        from app.rpc_server import main as rpc_main
        return rpc_main()
    setup_logging(args.log_dir, level=args.log_level)
    logger = get_logger("arqgen.cli")

    from app.bootstrap import bootstrap
    application, _loader = bootstrap(args)

    if args.command is None:
        parser.print_help()
        return 0

    # Commands with subcommands use (command, subcommand); flat ones (None, command).
    if hasattr(args, "subcommand") and args.subcommand is not None:
        handler = HANDLERS.get((args.command, args.subcommand))
    else:
        handler = HANDLERS.get((None, args.command))
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler(application, args)
    except Exception as exc:  # noqa: BLE001
        from core.errors import ARQGenError
        if isinstance(exc, ARQGenError):
            _print_error(exc.code, exc.message, exc.suggested_action)
            logger.error("[%s] %s", exc.code, exc.message)
            return 1
        logger.exception("Error inesperado")
        print(f"ERROR inesperado: {type(exc).__name__}: {exc}")
        print("Consulte logs/app/errors.log para el detalle completo.")
        return 2


def main() -> int:
    # v3.13.1: la consola de Windows (cp1252) no codifica «→» y un
    # print con esa flecha tumbaba el comando con UnicodeEncodeError.
    from core.consola import consola_segura
    consola_segura()
    return run()


if __name__ == "__main__":
    sys.exit(main())

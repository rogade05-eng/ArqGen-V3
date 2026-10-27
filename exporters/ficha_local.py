"""FICHA IMPRIMIBLE DE UN LOCAL (v3.21.0).

La ficha reúne TODO lo que es imputable al local — identidad y uso
(con el DNA del uso y su ficha técnica), medidas y cota del piso,
vanos, mobiliario, instalaciones, planta dibujada y diagnóstico — en
un PDF 1.4 100 % stdlib (el mismo motor del presupuesto PRECONS III:
``exporters.pdf_exporter``).

Es la versión impresa del ASISTENTE DE LOCAL (modo modificar): el
diagnóstico que se ve en pantalla sale en papel con la planta del
local, para el expediente de obra o la carpeta del proyecto. Todo el
texto se codifica en cp1252 vía ``_winansi`` (sin emojis ni símbolos
fuera de WinAnsi).

Uso:
    from exporters.ficha_local import export_ficha_local_pdf
    export_ficha_local_pdf(ctx, "SP-001", "ficha_SP-001.pdf")
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Tuple

from exporters.pdf_exporter import (PAGE_H, MARGIN, PAGE_W, PdfReport,
                                    text_width)
from domain.hospital_specs import ETIQUETAS_CAMPO, ORDEN_CAMPOS

ANCHO_UTIL = PAGE_W - 2 * MARGIN  # 511.28 pt: el ancho de TODA tabla
PLANTA_ALTO_MAX = 300.0
PLANTA_RESERVA = 400.0            # lo que hay que asegurar en la página
                                  # (título + caja de dibujo + nota)


# nombres legibles de la ficha técnica del DNA (cp1252, sin símbolos)
_ETIQUETAS_DNA: Dict[str, str] = {
    "radiacion": "Radiación",
    "friocamara": "Frigocámara",
    "biosafety": "Bioseguridad",
    "sai": "SAI",
    "extraccion": "Extracción",
    "extraccion_forzada": "Extracción forzada",
    "segregacion": "Segregación de desechos",
    "camilla": "Pasa camilla",
    "cambios_aire_h": "Cambios de aire/h",
    "presion": "Presión",
    "oxigeno_medicinal": "Oxígeno medicinal",
    "requiere_hvac": "Climatización",
    "camas": "Camas",
    "cama_espacio_m2": "Espacio por cama (m2)",
    "carga_mercancias": "Carga de mercancías",
    "suelo_lavable": "Suelo lavable",
    "suelo_tecnico": "Suelo técnico",
    "pasillo_m": "Pasillo que pide el uso (m)",
    "neufert": "Neufert (puerta y zonas)",
}


def _valor_legible(valor: Any) -> str:
    if isinstance(valor, dict):
        partes = [f"{clave}: {_valor_legible(v)}"
                  for clave, v in valor.items()
                  if v not in (None, "", False)]
        return "; ".join(partes) if partes else "—"
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    texto = str(valor)
    return texto if texto else "—"


def _linea_de_dna(clave: str, valor: Any) -> Tuple[str, str]:
    return _ETIQUETAS_DNA.get(clave, clave), _valor_legible(valor)


def _celda(texto: str, ancho_pt: float, size: float = 8.2) -> str:
    """Recorta el texto al ancho de la columna (las celdas no envuelven)."""
    texto = str(texto)
    disponible = max(ancho_pt - 8.0, 20.0)
    if text_width(texto, size) <= disponible:
        return texto
    recorte = texto
    while recorte and text_width(recorte + "...", size) > disponible:
        recorte = recorte[:-1]
    return recorte + "..."


def _planta(report: PdfReport, geo: Dict[str, Any], nombre: str,
            area_m2: float, medidas: str) -> None:
    """Dibuja la planta del local (muros, vanos y giro de puertas)."""
    boundary: List[Tuple[float, float]] = geo.get("boundary") or []
    if len(boundary) < 3:
        report.para("(sin geometría suficiente para dibujar la planta)",
                    gray=0.45)
        return
    xs = [p[0] for p in boundary]
    ys = [p[1] for p in boundary]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    ancho_m = max(max_x - min_x, 1e-6)
    fondo_m = max(max_y - min_y, 1e-6)
    # centroide del contorno: el interior hacia el que abren las puertas
    cx_int = sum(xs) / len(xs)
    cy_int = sum(ys) / len(ys)
    # holgura: los muros, la etiqueta y el ARCO de la puerta más ancha
    arco_max = max((v.get("width_m", 0.0) for v in geo.get("vanos", [])
                    if v.get("kind") == "DOOR"), default=0.0)
    pad_m = max(ancho_m, fondo_m) * 0.12 + 0.30 + arco_max
    caja_w = ANCHO_UTIL
    caja_h = min(PLANTA_ALTO_MAX, PAGE_H * 0.34)
    escala = min(caja_w / (ancho_m + 2 * pad_m),
                 caja_h / (fondo_m + 2 * pad_m))
    report._need(caja_h + 46)

    # caja del dibujo: en coordenadas PDF (y desde abajo)
    top_pdf = PAGE_H - report.y
    bottom_pdf = top_pdf - caja_h

    def px(x: float) -> float:
        return MARGIN + (x - min_x + pad_m) * escala

    def py(y: float) -> float:
        return bottom_pdf + (y - min_y + pad_m) * escala

    doc = report.doc
    # contorno del local
    for i in range(len(boundary)):
        x1, y1 = boundary[i]
        x2, y2 = boundary[(i + 1) % len(boundary)]
        doc.line(px(x1), py(y1), px(x2), py(y2), 0.7, gray=0.55)
    # muros: exclusivo/estructural grueso, compartido fino
    for muro in geo.get("muros", []):
        (sx, sy), (ex, ey) = muro["start"], muro["end"]
        grueso = muro.get("papel") == "exclusivo"
        doc.line(px(sx), py(sy), px(ex), py(ey),
                 2.4 if grueso else 1.3, gray=0.12 if grueso else 0.45)
    # vanos: hueco blanco, arco de giro en puertas, marco en ventanas
    for vano in geo.get("vanos", []):
        (ax, ay), (bx, by) = vano["p1"], vano["p2"]
        w = math.hypot(bx - ax, by - ay)
        if w <= 1e-6:
            continue
        ux, uy = (bx - ax) / w, (by - ay) / w
        # hueco: se «borra» el muro con una línea blanca gruesa
        doc.line(px(ax), py(ay), px(bx), py(by), 4.0, gray=1.0)
        if vano["kind"] == "DOOR":
            # perpendicular que apunta HACIA DENTRO del local
            vx0, vy0 = -uy, ux
            medio_mx, medio_my = ax + ux * w / 2.0, ay + uy * w / 2.0
            if (vx0 * (cx_int - medio_mx)
                    + vy0 * (cy_int - medio_my)) < 0:
                vx0, vy0 = -vx0, -vy0
            hx, hy = ax + vx0 * w, ay + vy0 * w
            doc.line(px(ax), py(ay), px(hx), py(hy), 1.1, gray=0.3)
            pasos = 14
            anterior = (bx, by)
            for paso in range(1, pasos + 1):
                ang = (math.pi / 2.0) * (paso / pasos)
                cx_ = ax + (ux * math.cos(ang)
                            + vx0 * math.sin(ang)) * w
                cy_ = ay + (uy * math.cos(ang)
                            + vy0 * math.sin(ang)) * w
                doc.line(px(anterior[0]), py(anterior[1]),
                         px(cx_), py(cy_), 0.6, gray=0.5)
                anterior = (cx_, cy_)
        else:
            # ventana: marco fino sobre el hueco + galces en los extremos
            doc.line(px(ax), py(ay), px(bx), py(by), 1.0, gray=0.35)
            t = 0.06
            doc.line(px(ax + uy * t), py(ay - ux * t),
                     px(ax - uy * t), py(ay + ux * t), 0.8, gray=0.35)
            doc.line(px(bx + uy * t), py(by - ux * t),
                     px(bx - uy * t), py(by + ux * t), 0.8, gray=0.35)
    # nombre, medidas y área dentro de la planta
    etiqueta = f"{nombre} · {medidas} · {area_m2:g} m2".replace(".", ",")
    doc.text(px(cx_int) - text_width(etiqueta, 8.5) / 2.0,
             py(cy_int) + 3.0, 8.5, etiqueta, bold=True, gray=0.25)
    report.y += caja_h + 8
    report.para("Planta esquemática del local (escala gráfica "
                "aproximada; muro grueso: propio, muro fino: "
                "compartido).", size=8.0, gray=0.45)


def export_ficha_local_pdf(ctx: Any, ref: str, out_path: str) -> str:
    """Ficha completa del local → PDF; devuelve la ruta escrita.

    Reúne identidad, DNA del uso (con su ficha técnica), vanos,
    mobiliario, instalaciones, planta dibujada y diagnóstico: lo mismo
    que muestra el asistente de local, listo para el expediente.
    """
    from ui import cad_tools
    from ui.editor_espacios import geometria_local, resumen_completo

    datos = resumen_completo(ctx, ref)
    geo = geometria_local(ctx, ref)
    local = cad_tools.resolver(ctx, "SPACE", ref)

    proyecto = str(getattr(ctx.project, "name", "") or "")
    titulo = f"Ficha de local {datos['codigo']}"
    report = PdfReport(
        titulo,
        f"Proyecto: {proyecto} · {date.today().strftime('%d/%m/%Y')}"
        if proyecto else date.today().strftime("%d/%m/%Y"))

    # -- identidad ---------------------------------------------------------
    report.heading("Identidad y medidas")
    nivel = ""
    try:
        lv = ctx.architecture.get("LEVEL", getattr(local, "level_id", ""))
        nivel = str(getattr(lv, "name", "") or "")
    except Exception:  # noqa: BLE001 — nivel ausente en proyectos viejos
        nivel = ""
    dna = datos.get("dna") or {}
    uso_label = datos["uso"]
    if dna.get("nombre_es") and dna["nombre_es"] != datos["uso"]:
        uso_label = f"{datos['uso']} — {dna['nombre_es']}"
    ancho_valor = ANCHO_UTIL - 150.0
    filas_id = [
        ["Código", datos["codigo"]],
        ["Nombre", datos["nombre"] or "—"],
        ["Uso", uso_label],
    ]
    if nivel:
        filas_id.append(["Nivel", nivel])
    filas_id += [
        ["Cota del piso", f"{datos.get('cota_piso_m', 0.0):g} m"],
        ["Dimensiones", f"{datos['ancho_m']:g} x {datos['fondo_m']:g} m"],
        ["Área", f"{datos['area_m2']:g} m2"],
        ["Muros", f"{len(datos['muros_exclusivos'])} propios, "
                  f"{len(datos['muros_compartidos'])} compartidos"],
    ]
    report.table([("Campo", "l", 150.0), ("Valor", "l", ancho_valor)],
                 [[_celda(c, 150.0), _celda(v, ancho_valor)]
                  for c, v in filas_id])

    # -- DNA del uso -------------------------------------------------------
    report.heading("Requerimientos del uso (DNA del espacio)")
    ancho_req = ANCHO_UTIL - 190.0
    filas_dna: List[List[str]] = []
    if dna.get("area_minima"):
        filas_dna.append(["Área mínima del uso",
                          f"{float(dna['area_minima']):g} m2"])
    if dna.get("altura_min"):
        filas_dna.append(["Altura mínima",
                          f"{float(dna['altura_min']):g} m"])
    if dna.get("puerta_min"):
        filas_dna.append(["Puerta de camilla",
                          f"{float(dna['puerta_min']):g} m"])
    filas_dna.append(["Zona húmeda", "sí" if dna.get("humedo") else "no"])
    for clave, valor in (datos.get("dna_tecnico") or {}).items():
        if valor in (None, "", False):
            continue
        filas_dna.append(list(_linea_de_dna(clave, valor)))
    report.table([("Requisito", "l", 190.0), ("Valor", "l", ancho_req)],
                 [[_celda(c, 190.0), _celda(v, ancho_req)]
                  for c, v in filas_dna])

    # -- especificaciones técnicas hospitalarias (v3.22.0) --------------
    hospital = datos.get("hospital") or {}
    ficha_tecnica = hospital.get("ficha") or {}
    if ficha_tecnica:
        report.heading("Especificaciones técnicas del uso")
        if hospital.get("prioridad"):
            report.para(f"Prioridad funcional: "
                        f"{str(hospital['prioridad']).upper()} "
                        f"(matriz de prioridad del documento)",
                        gray=0.25)
        for campo in ORDEN_CAMPOS:
            contenido = ficha_tecnica.get("campos", {}).get(campo)
            if not contenido:
                continue
            texto = " ".join(str(l).strip() for l in contenido)
            report.para(f"{ETIQUETAS_CAMPO.get(campo, campo)}: "
                        f"{texto}", size=8.6, gray=0.2)

    # -- vanos ---------------------------------------------------------------
    report.heading("Vanos")
    if geo.get("vanos"):
        anchos = (70.0, 90.0, 62.0, 62.0, 76.0,
                  ANCHO_UTIL - 70.0 - 90.0 - 62.0 - 62.0 - 76.0)
        filas_v = [[
            "Puerta" if v["kind"] == "DOOR" else
            ("Ventana" if v["kind"] == "WINDOW" else "Hueco"),
            str(v["code"] or ""), f"{v['width_m']:g} m",
            f"{v['height_m']:g} m",
            f"{v['sill_m']:g} m" if v["kind"] == "WINDOW" else "—",
            str(v.get("muro") or "—"),
        ] for v in geo["vanos"]]
        cabeceras = [("Tipo", "l", anchos[0]), ("Código", "l", anchos[1]),
                     ("Ancho", "r", anchos[2]), ("Alto", "r", anchos[3]),
                     ("Antepecho", "r", anchos[4]), ("Muro", "l", anchos[5])]
        report.table(cabeceras,
                     [[_celda(valor, anchos[i]) for i, valor
                       in enumerate(fila)] for fila in filas_v])
    else:
        report.para("El local no tiene vanos.", gray=0.45)

    # -- mobiliario ------------------------------------------------------------
    report.heading("Mobiliario")
    piezas: List[List[str]] = []
    try:
        muebles = [e for e in ctx.architecture.list(
            "FURNITURE", ctx.project.id)
            if getattr(e, "space_id", None) == getattr(local, "id", "")]
    except Exception:  # noqa: BLE001 — proyectos sin mobiliario
        muebles = []
    if muebles:
        a1, a2 = 170.0, 110.0
        a3 = ANCHO_UTIL - a1 - a2
        for mueble in muebles:
            piezas.append([
                str(getattr(mueble, "kind", "") or "pieza"),
                str(getattr(mueble, "code", "") or ""),
                f"{float(getattr(mueble, 'width_m', 0.0)):g} x "
                f"{float(getattr(mueble, 'depth_m', 0.0)):g} x "
                f"{float(getattr(mueble, 'height_m', 0.0)):g} m",
            ])
        report.table([("Pieza", "l", a1), ("Código", "l", a2),
                      ("Medidas (an x f x al)", "l", a3)],
                     [[_celda(c1, a1), _celda(c2, a2), _celda(c3, a3)]
                      for c1, c2, c3 in piezas])
    else:
        report.para("Sin mobiliario colocado.", gray=0.45)

    # -- instalaciones -------------------------------------------------------
    report.heading("Instalaciones")
    report.para(
        f"Luminarias en el local: {datos.get('luminarias', 0)} · "
        f"Dispositivos de alarma: {datos.get('alarma', 0)} · "
        f"Ventilación: {datos['hueco_ventilacion_m2']:g} m2 de hueco "
        f"(necesita {datos['hueco_necesario_m2']:g} m2).")

    # -- planta: la caja de dibujo (hasta 300 pt) viaja JUNTO con su
    #    título — si no cabe entera, todas a página nueva.
    report._need(PLANTA_RESERVA)
    report.heading("Planta del local")
    _planta(report, geo, datos["nombre"] or datos["uso"],
            datos["area_m2"], f"{datos['ancho_m']:g} x "
                              f"{datos['fondo_m']:g} m")

    # -- control de validación dimensional (§19, v3.22.0) -----------------
    informe = None
    try:
        from domain.hospital_specs import validar_local as _validar
        informe = _validar(ctx, ref)
    except Exception:  # noqa: BLE001 — sin recurso hospitalario
        informe = None
    if informe is not None:
        report.heading("Cotas de referencia del uso")
        cotas = informe.get("cotas") or {}
        ancho_ref = ANCHO_UTIL - 150.0
        filas_cotas: List[List[str]] = []
        if cotas.get("min_m2"):
            filas_cotas.append(["Superficie mínima",
                                f"{float(cotas['min_m2']['min']):g} m2"])
        if cotas.get("rec_m2"):
            rec = cotas["rec_m2"]
            texto_rec = f"{float(rec['min']):g}"
            if rec.get("max"):
                texto_rec += f"-{float(rec['max']):g}"
            filas_cotas.append(["Superficie recomendada",
                                texto_rec + " m2"])
        if cotas.get("cota_tipica"):
            filas_cotas.append(["Cota típica",
                                str(cotas["cota_tipica"])])
        for nota in (cotas.get("notas") or [])[:4]:
            filas_cotas.append(["Nota del cuadro", str(nota)])
        filas_cotas.append(["Superficie real",
                            f"{datos['area_m2']:g} m2"])
        if filas_cotas:
            report.table([("Cota", "l", 150.0), ("Valor", "l", ancho_ref)],
                         [[_celda(c, 150.0), _celda(v, ancho_ref)]
                          for c, v in filas_cotas])

        report.heading("Control de validación dimensional")
        report.para("Medición del local contra las cotas del uso "
                    "(cota tipo B/C de programación; nunca normativa "
                    "sin la verificación que pide la norma local):",
                    size=8.6, gray=0.3)
        a1, a2, a3 = 46.0, 62.0, 68.0
        a4 = ANCHO_UTIL - a1 - a2 - a3
        filas_v: List[List[str]] = [[
            h["codigo"], h["severidad"],
            f"tipo {h['cota_tipo']}" if h.get("cota_tipo") else "—",
            h["mensaje"],
        ] for h in informe.get("hallazgos", [])]
        if filas_v:
            report.table([("ID", "l", a1), ("Estado", "l", a2),
                          ("Clase", "l", a3), ("Resultado", "l", a4)],
                         [[_celda(v, ancho) for v, ancho in zip(fila,
                                                                (a1, a2,
                                                                 a3, a4))]
                          for fila in filas_v])
        else:
            report.para("Sin hallazgos medibles para este uso.",
                        gray=0.45)
        report.para("Checklist del documento (sección 19) — lo "
                    "geométrico sale medido; cálculo y fabricante "
                    "quedan pendientes:", size=8.6, gray=0.3)
        simbolos = {"cumple": "[x]", "no cumple": "[ ]",
                    "revisar": "[!]", "informativo": "[i]",
                    "pendiente": "[ ]"}
        for punto in informe.get("checklist", []):
            report.para(f"{simbolos.get(punto['estado'], '[ ]')} "
                        f"{punto['punto']}"
                        + (f" — {punto['detalle']}"
                           if punto.get("detalle") else ""),
                        size=8.2, gray=0.2)

    # -- diagnóstico ------------------------------------------------------------
    report.heading("Diagnóstico")
    if datos["avisos"]:
        for aviso in datos["avisos"]:
            report.para(f"· {aviso}")
    else:
        report.para("Sin avisos: el local cumple lo que su uso pide.")

    # -- fuentes y advertencia (v3.22.0) ---------------------------------------
    informe_fuentes = informe or {}
    fuentes = informe_fuentes.get("fuentes") or []
    advertencia = str(informe_fuentes.get("advertencia") or "")
    if fuentes or advertencia:
        report.heading("Fuentes y advertencia")
        if advertencia:
            report.para(advertencia, size=8.4, gray=0.3)
        for fuente in fuentes:
            report.para(f"· {fuente}", size=8.2, gray=0.35)

    report.save(out_path)
    return out_path


__all__ = ["export_ficha_local_pdf"]

# -*- coding: utf-8 -*-
"""v3.44.0/v3.45.0 — ELEVACIONES PARAMÉTRICAS (FASE E del despliegue).

``elevacion`` genera las ELEVACIONES del edificio a partir del
contorno de la planta y parámetros de piel, con 12 pieles
predeterminadas (deterministas, offline, explicables):

  * ``panos``            — paños verticales con ventana por paño y
                           antepecho (la clásica de las villas),
  * ``ventana_corrida``  — banda de ventanas corrida por planta con
                           parteluces (torre moderna),
  * ``brise``            — paneles + lamas verticales a todo el alto
                           (brise-soleil, piel de las imágenes),
  * ``perforada``        — malla de perforaciones circulares
                           (el panel perforado de las imágenes),
  * ``hexagonal``        — v3.45: malla de CELDAS HEXAGONALES planas
                           (la piel hexagonal de las torres),
  * ``diagrid``          — v3.45: retícula DIAGONAL cruzada por
                           planta (estructura diamante),
  * ``celosia``          — v3.45: retícula de lamas verticales finas
                           y horizontales por planta (breeze block),
  * ``gradiente``        — v3.45: perforación con radio DECRECIENTE
                           con la altura (densidad paramétrica de
                           asoleamiento),
  * ``fins``             — v3.45: aletas verticales profundas (doble
                           línea) con vidrio corrido entre ellas,
  * ``cortina``          — v3.45: muro cortina con montantes finos a
                           todo el alto, travesaños por planta y
                           banda opaca (spandrel) baja,
  * ``bandas``           — v3.45: banda opaca inferior y vidrio
                           corrido con parteluces alternos,
  * ``parametrica``      — v3.45: paneles facetados con ancho
                           aparente variable (efecto de torsión).

La puerta de acceso se dibuja en el primer paño del lado 1 de las
pieles con paños (``panos``, ``brise``, ``fins``); las pieles de
malla corrida (perforada, hexagonal, gradiente, celosia, diagrid,
cortina, bandas, ventana_corrida, parametrica) no la llevan.

Cada lado del contorno es una fachada: las entidades (líneas y
círculos con capa) sirven igual para el render PNG (matplotlib) que
para el DXF (ezdxf R12: LINE/CIRCLE/TEXT). La elevación NO toca la
planta: es un módulo de pieles sobre el perímetro que el motor ya
generó (independiente del módulo de parasoles ``fachadas.py``
v3.18.0, que sigue intacto).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

PIELES = ("panos", "ventana_corrida", "brise", "perforada",
          "hexagonal", "diagrid", "celosia", "gradiente",
          "fins", "cortina", "bandas", "parametrica")

_CAPAS = {
    "FACH_MURO": 1, "FACH_VENTANA": 2, "FACH_LAMAS": 3,
    "FACH_PERFORACION": 4, "FACH_TEXTO": 5,
}


def _lado_longitud(a: Tuple[float, float],
                   b: Tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _hexagono(ent: List[Dict[str, Any]], cx: float, cy: float,
              r: float, capa: str = "FACH_PERFORACION") -> None:
    """Celda hexagonal plana de la malla: 6 líneas (v3.45)."""
    pts = []
    for k in range(6):
        ang = math.pi / 6.0 + k * math.pi / 3.0
        pts.append((round(cx + r * math.cos(ang), 3),
                    round(cy + r * math.sin(ang), 3)))
    for k in range(6):
        a = pts[k]
        b = pts[(k + 1) % 6]
        ent.append({"tipo": "linea", "x1": a[0], "y1": a[1],
                    "x2": b[0], "y2": b[1], "capa": capa})


def elevacion(contorno: List[Tuple[float, float]],
              n_pisos: int = 1,
              altura_piso_m: float = 3.0,
              piel: str = "panos",
              ritmo_m: float = 1.5,
              antepecho_m: float = 1.0,
              ventana_m: float = 1.4,
              puerta: bool = True) -> Dict[str, Any]:
    """Elevaciones paramétricas por lado del contorno. Devuelve un
    dict con las ENTIDADES de cada fachada (para PNG y DXF)."""
    if str(piel or "").lower() not in PIELES:
        raise ValueError(
            f"piel desconocida: {piel!r} (use una de {PIELES})")
    piel = str(piel).lower()
    n_pisos = max(1, int(n_pisos or 1))
    altura = max(2.2, float(altura_piso_m or 3.0))
    H = round(n_pisos * altura, 3)
    ritmo = max(0.6, float(ritmo_m or 1.5))
    antepecho = min(max(0.4, float(antepecho_m or 1.0)),
                    altura - 0.6)
    ventana = min(max(0.4, float(ventana_m or 1.4)),
                  altura - antepecho - 0.3)
    vertice = [(float(p[0]), float(p[1])) for p in contorno]
    if len(vertice) < 3:
        raise ValueError("el contorno necesita 3 vértices o más")
    fachadas: List[Dict[str, Any]] = []
    n_lados = len(vertice)
    for i in range(n_lados):
        a = vertice[i]
        b = vertice[(i + 1) % n_lados]
        L = _lado_longitud(a, b)
        ent: List[Dict[str, Any]] = []
        # contorno de la fachada + forjados
        ent.append({"tipo": "linea", "x1": 0.0, "y1": 0.0,
                    "x2": L, "y2": 0.0, "capa": "FACH_MURO"})
        ent.append({"tipo": "linea", "x1": 0.0, "y1": H,
                    "x2": L, "y2": H, "capa": "FACH_MURO"})
        ent.append({"tipo": "linea", "x1": 0.0, "y1": 0.0,
                    "x2": 0.0, "y2": H, "capa": "FACH_MURO"})
        ent.append({"tipo": "linea", "x1": L, "y1": 0.0,
                    "x2": L, "y2": H, "capa": "FACH_MURO"})
        for p in range(1, n_pisos):
            ent.append({"tipo": "linea", "x1": 0.0,
                        "y1": round(p * altura, 3),
                        "x2": L, "y2": round(p * altura, 3),
                        "capa": "FACH_MURO"})
        n_panos = max(1, int(round(L / ritmo)))
        ritmo_real = L / n_panos
        w = min(ventana, max(0.4, ritmo_real - 0.3))
        for p in range(n_pisos):
            y0 = round(p * altura + antepecho, 3)
            y1 = round(y0 + ventana, 3)
            if piel == "ventana_corrida":
                # banda corrida con parteluces cada ritmo_real
                ent.append({"tipo": "linea", "x1": 0.05, "y1": y0,
                            "x2": round(L - 0.05, 3), "y2": y0,
                            "capa": "FACH_VENTANA"})
                ent.append({"tipo": "linea", "x1": 0.05, "y1": y1,
                            "x2": round(L - 0.05, 3), "y2": y1,
                            "capa": "FACH_VENTANA"})
                for k in range(1, n_panos):
                    xk = round(k * ritmo_real, 3)
                    ent.append({"tipo": "linea", "x1": xk, "y1": y0,
                                "x2": xk, "y2": y1,
                                "capa": "FACH_VENTANA"})
            elif piel in ("perforada", "hexagonal", "gradiente"):
                # pieles de perforación (v3.44 círculos; v3.45 malla
                # hexagonal y gradiente paramétrico de asoleamiento)
                filas = 2
                for fila in range(filas):
                    cy = round(p * altura + antepecho
                               + (fila + 0.5)
                               * (altura - antepecho) / filas, 3)
                    for k in range(n_panos):
                        cx = round((k + 0.5 + (0.5 if fila % 2 else 0.0))
                                   * ritmo_real, 3)
                        cx = min(cx, round(L - 0.15, 3))
                        if piel == "perforada":
                            r = round(min(0.18, ventana / 4.0), 3)
                            ent.append({"tipo": "circulo", "cx": cx,
                                        "cy": cy, "r": r,
                                        "capa": "FACH_PERFORACION"})
                        elif piel == "gradiente":
                            r = round(min(0.22, ventana / 4.0)
                                      * (1.0 - 0.75 * cy / max(0.1, H)),
                                      3)
                            ent.append({"tipo": "circulo", "cx": cx,
                                        "cy": cy, "r": max(0.02, r),
                                        "capa": "FACH_PERFORACION"})
                        else:
                            r_h = round(min(0.30,
                                            ritmo_real * 0.32), 3)
                            _hexagono(ent, cx, cy, r_h)
            elif piel in ("diagrid", "celosia"):
                # v3.45: malla pura — el patrón global va después del
                # bucle (sin ventanas por paño ni puerta)
                pass
            elif piel == "cortina":
                # v3.45: muro cortina: montantes finos a todo el alto,
                # travesaños por planta y banda opaca (spandrel)
                paso = max(0.35, ritmo_real / 2.0)
                n_mull = max(2, int(round(L / paso)))
                for k in range(n_mull + 1):
                    xk = round(min(L, k * L / n_mull), 3)
                    ent.append({"tipo": "linea", "x1": xk, "y1": 0.0,
                                "x2": xk, "y2": H,
                                "capa": "FACH_VENTANA"})
                for yy in (round(p * altura + 0.05, 3),
                           round(p * altura + 0.95, 3)):
                    ent.append({"tipo": "linea", "x1": 0.05, "y1": yy,
                                "x2": round(L - 0.05, 3), "y2": yy,
                                "capa": "FACH_MURO"})
            elif piel == "bandas":
                # v3.45: banda opaca inferior + vidrio corrido con
                # parteluces cada dos paños
                yb = round(p * altura + antepecho * 0.35, 3)
                ent.append({"tipo": "linea", "x1": 0.0, "y1": yb,
                            "x2": L, "y2": yb, "capa": "FACH_MURO"})
                ent.append({"tipo": "linea", "x1": 0.05, "y1": y0,
                            "x2": round(L - 0.05, 3), "y2": y0,
                            "capa": "FACH_VENTANA"})
                ent.append({"tipo": "linea", "x1": 0.05, "y1": y1,
                            "x2": round(L - 0.05, 3), "y2": y1,
                            "capa": "FACH_VENTANA"})
                for k in range(0, n_panos, 2):
                    xk = round(k * ritmo_real, 3)
                    ent.append({"tipo": "linea", "x1": xk, "y1": y0,
                                "x2": xk, "y2": y1,
                                "capa": "FACH_VENTANA"})
            else:
                # panos, brise y fins: ventana por paño
                for k in range(n_panos):
                    if p == 0 and k == 0 and puerta:
                        # puerta de acceso en el primer paño
                        dh = min(2.1, altura - 0.3)
                        dw = min(0.9, ritmo_real - 0.3)
                        x0 = round(k * ritmo_real
                                   + (ritmo_real - dw) / 2.0, 3)
                        ent.append({"tipo": "linea", "x1": x0,
                                    "y1": 0.0, "x2": x0, "y2": dh,
                                    "capa": "FACH_VENTANA"})
                        ent.append({"tipo": "linea",
                                    "x1": round(x0 + dw, 3),
                                    "y1": 0.0,
                                    "x2": round(x0 + dw, 3),
                                    "y2": dh,
                                    "capa": "FACH_VENTANA"})
                        ent.append({"tipo": "linea", "x1": x0,
                                    "y1": dh,
                                    "x2": round(x0 + dw, 3),
                                    "y2": dh,
                                    "capa": "FACH_VENTANA"})
                        continue
                    x0 = round(k * ritmo_real
                               + (ritmo_real - w) / 2.0, 3)
                    ent.append({"tipo": "linea", "x1": x0, "y1": y0,
                                "x2": round(x0 + w, 3), "y2": y0,
                                "capa": "FACH_VENTANA"})
                    ent.append({"tipo": "linea", "x1": x0, "y1": y1,
                                "x2": round(x0 + w, 3), "y2": y1,
                                "capa": "FACH_VENTANA"})
                    ent.append({"tipo": "linea", "x1": x0, "y1": y0,
                                "x2": x0, "y2": y1,
                                "capa": "FACH_VENTANA"})
                    ent.append({"tipo": "linea",
                                "x1": round(x0 + w, 3), "y1": y0,
                                "x2": round(x0 + w, 3), "y2": y1,
                                "capa": "FACH_VENTANA"})
        if piel == "brise":
            # lamas verticales a todo el alto en los ejes de los
            # paños (encima de las ventanas: piel de celosía)
            for k in range(n_panos + 1):
                xk = round(min(L, k * ritmo_real), 3)
                ent.append({"tipo": "linea", "x1": xk, "y1": 0.0,
                            "x2": xk, "y2": H,
                            "capa": "FACH_LAMAS"})
        if piel == "panos":
            # juntas de paño (más finas que las lamas del brise)
            for k in range(1, n_panos):
                xk = round(k * ritmo_real, 3)
                ent.append({"tipo": "linea", "x1": xk, "y1": 0.0,
                            "x2": xk, "y2": H,
                            "capa": "FACH_MURO"})
        if piel == "fins":
            # v3.45: aletas verticales profundas (doble línea) en los
            # ejes de los paños, a todo el alto
            for k in range(n_panos + 1):
                xk = round(min(L, k * ritmo_real), 3)
                ent.append({"tipo": "linea", "x1": xk, "y1": 0.0,
                            "x2": xk, "y2": H,
                            "capa": "FACH_LAMAS"})
                ent.append({"tipo": "linea",
                            "x1": round(min(L, xk + 0.12), 3),
                            "y1": 0.0,
                            "x2": round(min(L, xk + 0.12), 3),
                            "y2": H, "capa": "FACH_LAMAS"})
        if piel == "diagrid":
            # v3.45: retícula diagonal cruzada (dos familias ±) por
            # planta, módulo 1.4x el ritmo
            dx = max(0.8, ritmo_real * 1.4)
            n_d = int(math.ceil(L / dx))
            for p2 in range(n_pisos):
                ya = p2 * altura
                yb2 = (p2 + 1) * altura
                for k in range(-1, n_d + 1):
                    xk = k * dx
                    ent.append({"tipo": "linea", "x1": round(xk, 3),
                                "y1": round(ya, 3),
                                "x2": round(xk + dx, 3),
                                "y2": round(yb2, 3),
                                "capa": "FACH_LAMAS"})
                    ent.append({"tipo": "linea", "x1": round(xk, 3),
                                "y1": round(yb2, 3),
                                "x2": round(xk + dx, 3),
                                "y2": round(ya, 3),
                                "capa": "FACH_LAMAS"})
        if piel == "celosia":
            # v3.45: retícula de lamas verticales finas + dos
            # horizontales por planta (breeze block)
            paso = max(0.18, ritmo_real * 0.35)
            n_v = max(2, int(round(L / paso)))
            for k in range(n_v + 1):
                xk = round(min(L, k * L / n_v), 3)
                ent.append({"tipo": "linea", "x1": xk, "y1": 0.0,
                            "x2": xk, "y2": H, "capa": "FACH_LAMAS"})
            for p2 in range(n_pisos):
                for fr in (0.33, 0.66):
                    yy = round(p2 * altura + fr * altura, 3)
                    ent.append({"tipo": "linea", "x1": 0.05, "y1": yy,
                                "x2": round(L - 0.05, 3), "y2": yy,
                                "capa": "FACH_LAMAS"})
        if piel == "parametrica":
            # v3.45: paneles facetados con ancho aparente variable
            # (efecto de torsión) y ventana centrada por panel
            ondas = 3.0
            x = 0.0
            while x < L - 0.05:
                w_p = ritmo_real * (0.55 + 0.45 * math.cos(
                    2.0 * math.pi * ondas * x / max(0.1, L)))
                w_p = max(0.25, min(w_p, L - x))
                xv0 = round(x + w_p * 0.25, 3)
                wv = round(w_p * 0.5, 3)
                for p2 in range(n_pisos):
                    yb2 = round(p2 * altura + antepecho, 3)
                    yv = round(yb2 + ventana, 3)
                    ent.append({"tipo": "linea", "x1": xv0, "y1": yb2,
                                "x2": round(xv0 + wv, 3), "y2": yb2,
                                "capa": "FACH_VENTANA"})
                    ent.append({"tipo": "linea", "x1": xv0, "y1": yv,
                                "x2": round(xv0 + wv, 3), "y2": yv,
                                "capa": "FACH_VENTANA"})
                    ent.append({"tipo": "linea", "x1": xv0, "y1": yb2,
                                "x2": xv0, "y2": yv,
                                "capa": "FACH_VENTANA"})
                    ent.append({"tipo": "linea",
                                "x1": round(xv0 + wv, 3), "y1": yb2,
                                "x2": round(xv0 + wv, 3), "y2": yv,
                                "capa": "FACH_VENTANA"})
                ent.append({"tipo": "linea", "x1": round(x, 3),
                            "y1": 0.0, "x2": round(x, 3), "y2": H,
                            "capa": "FACH_MURO"})
                x = round(x + w_p, 4)
        ent.append({"tipo": "texto", "x": round(L / 2.0, 3),
                    "y": round(H + 0.4, 3),
                    "texto": f"FACHADA {i + 1} ({L:.1f} m)",
                    "capa": "FACH_TEXTO"})
        fachadas.append({"lado": i, "longitud_m": round(L, 3),
                         "entidades": ent})
    return {
        "piel": piel, "n_pisos": n_pisos,
        "altura_piso_m": round(altura, 3),
        "altura_total_m": H,
        "parametros": {"ritmo_m": round(ritmo, 3),
                       "antepecho_m": round(antepecho, 3),
                       "ventana_m": round(ventana, 3),
                       "puerta": bool(puerta)},
        "lado_longitud_m": [f["longitud_m"] for f in fachadas],
        "fachadas": fachadas,
        "modulos": "elevaciones paramétricas v3.44.0"}


def render_elevacion_png(resultado: Dict[str, Any], ruta: str) \
        -> str:
    """Render de las elevaciones en una rejilla (2 columnas)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    fachs = resultado["fachadas"]
    n = len(fachs)
    cols = 2
    rows = (n + cols - 1) // cols
    H = resultado["altura_total_m"]
    fig, axes = plt.subplots(rows, cols,
                             figsize=(5.2 * cols, 4.0 * rows),
                             squeeze=False, constrained_layout=True)
    for idx, fac in enumerate(fachs):
        ax = axes[idx // cols][idx % cols]
        L = fac["longitud_m"]
        ax.add_patch(plt.Rectangle((0, 0), L, H, fill=False,
                                   edgecolor="black", lw=1.6))
        for e in fac["entidades"]:
            capa = e.get("capa", "")
            if e["tipo"] == "linea":
                lw = 1.2 if capa == "FACH_LAMAS" else 0.8
                ax.plot([e["x1"], e["x2"]], [e["y1"], e["y2"]],
                        color="#555555" if capa == "FACH_LAMAS"
                        else "#1a1a1a", lw=lw)
            elif e["tipo"] == "circulo":
                ax.add_patch(Circle((e["cx"], e["cy"]), e["r"],
                                    fill=False, edgecolor="#1a1a1a",
                                    lw=0.8))
            elif e["tipo"] == "texto":
                ax.text(e["x"], e["y"], e["texto"], ha="center",
                        fontsize=8)
        ax.set_xlim(-0.5, L + 0.5)
        ax.set_ylim(-0.8, H + 1.0)
        ax.set_aspect("equal")
        ax.set_title(f"Lado {fac['lado'] + 1} — "
                     f"{fac['longitud_m']:.1f} m", fontsize=9)
    total = rows * cols
    for idx in range(n, total):
        axes[idx // cols][idx % cols].axis("off")
    fig.suptitle(f"ELEVACIONES — piel {resultado['piel']}, "
                 f"{resultado['n_pisos']} planta(s) "
                 f"({H:.1f} m)", fontsize=11)
    fig.savefig(ruta, dpi=130)
    plt.close(fig)
    return ruta


def exportar_elevacion_dxf(resultado: Dict[str, Any],
                           ruta: str) -> str:
    """DXF R12 con las 4 fachadas lado a lado (LINE/CIRCLE/TEXT)."""
    try:
        import ezdxf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "ezdxf no está disponible para exportar la elevación") \
            from exc
    doc = ezdxf.new("R12")
    msp = doc.modelspace()
    for nombre in _CAPAS:
        if nombre not in doc.layers:
            doc.layers.add(nombre)
    x_off = 0.0
    for fac in resultado["fachadas"]:
        for e in fac["entidades"]:
            capa = e.get("capa", "FACH_MURO")
            if e["tipo"] == "linea":
                msp.add_line((e["x1"] + x_off, e["y1"]),
                             (e["x2"] + x_off, e["y2"]),
                             dxfattribs={"layer": capa})
            elif e["tipo"] == "circulo":
                msp.add_circle((e["cx"] + x_off, e["cy"]), e["r"],
                               dxfattribs={"layer": capa})
            elif e["tipo"] == "texto":
                msp.add_text(
                    e["texto"],
                    dxfattribs={"layer": capa,
                                "height": 0.25}
                    ).set_placement((e["x"] + x_off, e["y"]))
        x_off += fac["longitud_m"] + 2.0
    doc.saveas(ruta)
    return ruta

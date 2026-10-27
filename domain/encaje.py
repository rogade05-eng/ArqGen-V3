"""ENCAJE AL POLÍGONO (v3.40.0): contenedores reales de la parcela.

El asistente «Desde dibujo» empaquetaba sobre la caja envolvente del
contorno y solo AVISABA cuando un local quedaba fuera («retóquelo con
las herramientas CAD»). En parcelas en L, U o T eso garantizaba
diseños que se salían del polígono y huecos desaprovechados.

Este módulo calcula los CONTENEDORES reales donde pueden vivir locales
ortogonales:

- rectángulo alineado: un contenedor (caja) — camino rápido;
- polígono ortogonal (L, U, T, cruz...): descomposición EXACTA por
  franjas horizontales de barrido (scanline): entre dos cotas y
  consecutivas de vértices la sección del polígono es constante, así
  que las franjas fusionadas teselan el polígono sin huecos ni
  solapes; los huecos de la forma (el codo de la L, el patio de la U)
  quedan FUERA de los contenedores y por tanto nada se sale;
- polígono general (con aristas inclinadas): el mayor rectángulo
  inscrito axis-alineado, con aviso honesto (el resto de la parcela
  no admite locales ortogonales).

Cero dependencias nuevas, cero IA, puro cálculo determinista.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

PT = Tuple[float, float]

TOL = 1e-7


def _es_ortogonal(poligono: List[PT], tol: float = 1e-6) -> bool:
    """Todas las aristas paralelas a los ejes (polígono «alineado»)."""
    n = len(poligono)
    for i in range(n):
        x0, y0 = poligono[i]
        x1, y1 = poligono[(i + 1) % n]
        if abs(x1 - x0) > tol and abs(y1 - y0) > tol:
            return False
    return True


def _seccion_en(poligono: List[PT], y: float) -> List[Tuple[float, float]]:
    """Intervalos x del interior del polígono en la horizontal y
    (cruces de aristas, ordenados y emparejados)."""
    cruces: List[float] = []
    n = len(poligono)
    for i in range(n):
        x0, y0 = poligono[i]
        x1, y1 = poligono[(i + 1) % n]
        if (y0 <= y < y1) or (y1 <= y < y0):
            t = (y - y0) / (y1 - y0) if abs(y1 - y0) > TOL else 0.0
            cruces.append(x0 + t * (x1 - x0))
    cruces.sort()
    return [(cruces[i], cruces[i + 1]) for i in range(0, len(cruces) - 1, 2)]


def _mismos_intervalos(a: List[Tuple[float, float]],
                       b: List[Tuple[float, float]],
                       tol: float = 1e-6) -> bool:
    if len(a) != len(b):
        return False
    return all(abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol
               for p, q in zip(a, b))


def _fusiona_franjas(franjas: List[Dict[str, float]]) -> List[Dict[str, float]]:
    """Fusiona franjas contiguas en y con la misma sección x."""
    if not franjas:
        return []
    salida = [dict(franjas[0])]
    for f in franjas[1:]:
        ant = salida[-1]
        if abs(ant["y1"] - f["y0"]) <= TOL \
                and _mismos_intervalos(ant["_seccion"], f["_seccion"]):
            ant["y1"] = f["y1"]
        else:
            salida.append(dict(f))
    return salida


def contenedores_ortogonales(poligono: List[PT], margen: float = 0.0,
                             min_lado: float = 1.0) -> List[Dict[str, float]]:
    """Descomposición exacta del polígono ortogonal en rectángulos
    (franjas de barrido fusionadas), descontado el margen en cada
    contenedor. Los rectángulos más pequeños que min_lado en algún
    lado se descartan (no admiten locales)."""
    ys = sorted({float(p[1]) for p in poligono})
    crudos: List[Dict[str, float]] = []
    for y0, y1 in zip(ys, ys[1:]):
        if y1 - y0 <= TOL:
            continue
        seccion = _seccion_en(poligono, (y0 + y1) / 2.0)
        for x0, x1 in seccion:
            if x1 - x0 > TOL:
                crudos.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                               "_seccion": [(x0, x1)]})
    salida: List[Dict[str, float]] = []
    for f in _fusiona_franjas(crudos):
        x0 = f["x0"] + margen
        x1 = f["x1"] - margen
        y0 = f["y0"] + margen
        y1 = f["y1"] - margen
        if x1 - x0 >= min_lado and y1 - y0 >= min_lado:
            salida.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                           "ancho": round(x1 - x0, 4),
                           "fondo": round(y1 - y0, 4),
                           "area": round((x1 - x0) * (y1 - y0), 4)})
    salida.sort(key=lambda c: -c["area"])
    return salida


def _niveles_refinados(poligono: List[PT]) -> List[float]:
    """Cotas y candidatas para bandas: vértices + mediados y tercios
    entre consecutivos (la banda óptima no siempre arranca en un
    vértice: en un rombo arranca a 1/4 de la altura)."""
    ys = sorted({float(p[1]) for p in poligono})
    niveles = set(ys)
    for y0, y1 in zip(ys, ys[1:]):
        h = y1 - y0
        for f in (0.25, 1 / 3, 0.5, 2 / 3, 0.75):
            niveles.add(y0 + f * h)
    finos = sorted(niveles)
    # capo determinista por si el contorno trae decenas de vértices
    while len(finos) > 48:
        paso = 2
        finos = finos[::paso]
    return finos


def rectangulo_inscrito(poligono: List[PT],
                        margen: float = 0.0) -> Optional[Dict[str, float]]:
    """Mayor rectángulo axis-alineado inscrito en un polígono simple
    (candidatos: pares de cotas refinadas; el intervalo x común a
    varias secciones dentro de la banda acota el ancho)."""
    ys = _niveles_refinados(poligono)
    if len(ys) < 2:
        return None
    mejor: Optional[Dict[str, float]] = None
    for i in range(len(ys) - 1):
        for j in range(i + 1, len(ys)):
            yb, yt = ys[i], ys[j]
            h = yt - yb
            if h <= TOL:
                continue
            inter: Optional[List[Tuple[float, float]]] = None
            # las cotas cerradas de la banda ENTRAN: el rectángulo debe
            # caber también en la sección exacta de su borde inferior y
            # superior (si no, sus esquinas se salen del polígono)
            for t in (0.0, 0.02, 0.25, 0.5, 0.75, 0.98, 1.0):
                sec = _seccion_en(poligono, yb + t * h)
                if not sec:
                    inter = []
                    break
                if inter is None:
                    inter = sec
                else:
                    nueva = []
                    for a0, a1 in inter:
                        for b0, b1 in sec:
                            x0, x1 = max(a0, b0), min(a1, b1)
                            if x1 - x0 > TOL:
                                nueva.append((x0, x1))
                    inter = nueva
                    if not inter:
                        break
            if not inter:
                continue
            x0, x1 = max(inter, key=lambda p: p[1] - p[0])
            area = (x1 - x0) * h
            if mejor is None or area > mejor["area"]:
                mejor = {"x0": x0, "y0": yb, "x1": x1, "y1": yt,
                         "ancho": round(x1 - x0, 4),
                         "fondo": round(h, 4), "area": round(area, 4)}
    if mejor is None:
        return None
    m = max(0.0, float(margen or 0.0))
    x0, x1 = mejor["x0"] + m, mejor["x1"] - m
    y0, y1 = mejor["y0"] + m, mejor["y1"] - m
    if x1 - x0 <= 0.5 or y1 - y0 <= 0.5:
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "ancho": round(x1 - x0, 4), "fondo": round(y1 - y0, 4),
            "area": round((x1 - x0) * (y1 - y0), 4)}


def comparten_banda(a: Dict[str, float], b: Dict[str, float],
                    min_len: float = 1.0, tol: float = 1e-6) -> bool:
    """Dos contenedores axis-alineados comparten arista de longitud
    suficiente (para exigir locales alcanzables desde el núcleo)."""
    ay0, ay1 = a["y0"], a["y1"]
    by0, by1 = b["y0"], b["y1"]
    ax0, ax1 = a["x0"], a["x1"]
    bx0, bx1 = b["x0"], b["x1"]
    solape_y = min(ay1, by1) - max(ay0, by0)
    solape_x = min(ax1, bx1) - max(ax0, bx0)
    if (abs(a["x1"] - b["x0"]) <= tol or abs(a["x0"] - b["x1"]) <= tol) \
            and solape_y >= min_len:
        return True
    if (abs(a["y1"] - b["y0"]) <= tol or abs(a["y0"] - b["y1"]) <= tol) \
            and solape_x >= min_len:
        return True
    return False


def contenedores_de(poligono: List[PT], margen: float = 0.0,
                    min_lado: float = 1.0) -> Dict[str, Any]:
    """Contenedores del polígono según su naturaleza. Devuelve:
    estrategia (rectangulo | descompuesto | inscrito), contenedores
    [{x0,y0,x1,y1,ancho,fondo,area}] YA DESCONTADO EL MARGEN,
    area_contenedores (con margen), area_aprovechable (bruta, sin
    margen, lo que la descomposición tesa del polígono) y avisos
    honestos."""
    m = max(0.0, float(margen or 0.0))
    avisos: List[str] = []
    if _es_ortogonal(poligono):
        xs = sorted({float(p[0]) for p in poligono})
        es_rect = len(xs) == 2 and len(ys_unicos(poligono)) == 2
        estrategia = "rectangulo" if es_rect else "descompuesto"
        bruta = contenedores_ortogonales(poligono, 0.0, min_lado)
        area_aprovechable = round(sum(c["area"] for c in bruta), 4)
        conts = contenedores_ortogonales(poligono, m, min_lado)
        if estrategia == "descompuesto" and area_aprovechable < \
                _area(poligono) - 0.01:
            avisos.append(
                f"franjas menores de {min_lado:.2f} m descartadas "
                f"({round(_area(poligono) - area_aprovechable, 2)} m2 "
                "sin uso posible: no admiten locales)")
    else:
        estrategia = "inscrito"
        r = rectangulo_inscrito(poligono, m)
        bruta = rectangulo_inscrito(poligono, 0.0)
        area_aprovechable = float(bruta["area"]) if bruta else 0.0
        conts = [r] if r else []
        if r:
            avisos.append(
                "el polígono tiene aristas inclinadas: los locales se "
                "colocan en el mayor rectángulo inscrito "
                f"({r['ancho']:.2f} x {r['fondo']:.2f} m); el resto de "
                "la parcela no admite locales ortogonales — para "
                "aprovecharla completa dibuje un contorno ortogonal")
        else:
            avisos.append("no se halló un rectángulo útil inscrito en "
                          "el polígono: reduzca el programa o dibuje "
                          "un contorno más regular")
    area_total = round(sum(c["area"] for c in conts), 4)
    return {"estrategia": estrategia, "contenedores": conts,
            "area_contenedores": area_total,
            "area_aprovechable": area_aprovechable, "avisos": avisos}


def ys_unicos(poligono: List[PT]) -> List[float]:
    return sorted({float(p[1]) for p in poligono})


def _area(poligono: List[PT]) -> float:
    s = 0.0
    n = len(poligono)
    for i in range(n):
        x0, y0 = poligono[i]
        x1, y1 = poligono[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


__all__ = ["contenedores_de", "contenedores_ortogonales",
           "rectangulo_inscrito", "comparten_banda", "ys_unicos"]

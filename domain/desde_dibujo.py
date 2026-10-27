"""DESDE DIBUJO: GENERACIÓN INVERSA (v3.34.0) — domain/desde_dibujo.py.

El camino al revés: en vez de definir el programa y obtener la
edificación, se PARTE de un DIBUJO del área o espacio (importado de
un DXF, dibujado a dos clics con las herramientas v3.33 o dado por
un rectángulo) y el asistente dinámico:

1. INFIERE la forma y las medidas del contorno: área, dimensiones
   de la caja envolvente, perímetro, vértices normalizados
   antihorarios y clasificación (rectángulo, ortogonal o polígono
   general).
2. Ofrece el PROGRAMA según el tipo y el uso social: un servicio
   completo del catálogo v3.33 (anatomía patológica, hemodiálisis...)
   o una edificación por usos del DNA con cantidades.
3. Decide si los LOCALES del programa ENTRAN en el área suministrada:
   empaquetado honesto con pasillo de distribución a dos bandas,
   verificando que cada rectángulo queda DENTRO del contorno (no
   basta la caja envolvente).
4. Si NO entra, sugiere el CRECIMIENTO: reparte el programa en N
   niveles apilados sobre el mismo contorno (crecimiento en altura)
   y reserva el recinto de la escalera (en U, según Blondel) en
   cada nivel.
5. GENERA entidades reales por los caminos oficiales: edificio,
   niveles, pasillo, locales, escalera, zona, relaciones y (opción)
   muros del contorno y de cada local. Todo entra en QTO,
   presupuesto, validación, DXF e informes.
6. v3.39.0 — ASISTENTE REFORZADO: valida el contorno ANTES de
   ajustar (autointersecciones, abierto, dimensiones imposibles),
   checklist previa a generar con [OK]/[AVISO]/[ERROR], ALTERNATIVAS
   1/3/5 con métricas comparables y puntuación explicada, decisiones
   registradas («¿por qué este local aquí?», sin IA), reemplazo del
   edificio previo con aviso, historial de CONFIGURACIONES y estado
   guardables en el proyecto, quick-spec en una línea («3
   dormitorios, 2 baños, garaje y 2 niveles») y patio exterior como
   opción experta.
7. v3.40.0 — ENCAJE ESTRICTO: el polígono se tesela en
   contenedores reales (domain/encaje.py) y los locales se
   empaquetan DENTRO con verificación dura contra el polígono.
8. v3.41.0 — PROGRAMA ADAPTABLE (la realidad del cambio de uso en
   Cuba: edificaciones existentes, no se puede demoler a gran
   escala): SELECCIÓN de locales (programa_filtrado, el arquitecto
   elige qué locales de cada temática se aplican) y AJUSTE
   DIMENSIONAL por niveles (minimo: solo lo que la norma permite /
   medio: hasta un 15 % bajo la norma / estricto: hasta un 35 %,
   lados desde 1,50 m) con una escalera de reducción iterativa que
   re-empaqueta hasta entrar y registra local a local cuánto se
   redujo y si rebasa la normativa (ARQ-DDI-009/010).
9. v3.42.0 — PASILLOS Y FILTROS (calibrado con el plano real AP +
   morgue de un hospital pediátrico y su dibujo de la solución
   esperada): el empaquetado RESERVA PRIMERO el pasillo del
   contenedor distribuidor y los locales lo sirven cambiando FONDO
   por ANCHO conservando su área (la adaptación del cambio de uso);
   las filas de los satélites se RELLENAN hasta los bordes del
   contenedor (teselado completo, con techos del catálogo) y el
   orden de colocación sigue el FLUJO del servicio (sucio al fondo,
   público en la entrada) con el FILTRO sanitario del catálogo como
   barrera entre zonas; con ajuste medio/estricto la COMPACTACIÓN
   prueba a bajar de niveles (una morgue pequeña cabe en 1 planta
   teselada al 95 %+ como el dibujo de referencia) y nada acepta
   geometría fuera del polígono. Informe con secciones CIRCULACIÓN
   Y FILTROS y TESELADO COMPLETO.

Reutilización interna del mismo paquete: la estrategia de pasillo a
dos bandas y las dimensiones sugeridas vienen de servicios_engine
(v3.33.0) y la escala de la escalera de escaleras (Blondel, v3.19.0).

Cero Tk. Mensajes 100 % codificables en cp1252 (sin flechas: usa
«->» en los flujos).
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError
from domain import escaleras
from domain import encaje
# Reutilización interna del mismo paquete (estables y probados en
# test_166): pasillo de salud, dimensiones sugeridas y DNA por uso.
from domain.servicios_engine import (FONDO_MAX, PASILLO_ANCHO,
                                     ANCHO_MAX, PROPORCION_DEF,
                                     _dimensiones, _dna_de)
from services.architecture_service import ArchitectureService

ORIGEN_DESDE_DIBUJO = "asistente desde dibujo (v3.34.0)"

ESPESOR_CONTORNO_M = 0.20   # muro perimetral del contorno dibujado
ESPESOR_LOCAL_M = 0.15      # muros de cada local (como v3.33.0)
LARGO_PASILLO_MIN_M = 6.0   # coherente con el empaquetado v3.33.0
ANCHO_TRAMO_ESC_M = 1.20    # tramo público/salud (Neufert)
NIVELES_MAX = 50            # techo del crecimiento en altura
ENCAJE_MIN_LADO_M = 1.0     # franja menor no admite locales (v3.40.0)
MIN_BANDA_CONEX_M = 1.2     # arista mínima entre contenedores conectados

# v3.41.0: AJUSTE DIMENSIONAL DEL PROGRAMA — en una intervención
# (cambio de uso de una edificación existente) casi nunca cabe el
# programa íntegro con sus áreas ideales y casi nunca se puede
# demoler a gran escala. Tres niveles de rebaja admisible:
#   minimo   = solo lo que la norma permite (piso = area_min del
#              catálogo o del DNA); nunca la viola.
#   medio    = hasta un 15 % POR DEBAJO de la norma (documentado).
#   estricto = hasta un 35 % bajo la norma, con lados desde 1,50 m
#              (el más agresivo: se trabaja con lo que se tiene).
# La escalera de reducción prueba factores 0.95, 0.90, ... y cada
# local se detiene en su piso del nivel; las naves (recintos que se
# adaptan al contenedor) no se reducen.
AJUSTE_NIVELES = ("ideal", "minimo", "medio", "estricto")
AJUSTE_CONFIG = {
    "minimo":   {"bajo_norma": 1.00, "lado_min": 2.0, "piso_abs": 6.0},
    "medio":    {"bajo_norma": 0.85, "lado_min": 2.0, "piso_abs": 4.0},
    "estricto": {"bajo_norma": 0.65, "lado_min": 1.5, "piso_abs": 2.5},
}
ETIQUETA_AJUSTE = {
    "ideal": "Ideal (sin reducción)",
    "minimo": "Mínimo (solo lo que la norma permite)",
    "medio": "Medio (hasta 15 % bajo la norma)",
    "estricto": "Estricto (hasta 35 % bajo la norma)",
}

# v3.43.0: VIVIENDA SOCIAL — el programa es de vivienda cuando lleva
# dormitorios; la casa cubana de cambio de uso es de UNA planta y la
# sala reparte sin pasillo. Tope por defecto y umbral del modo
# distribuidor.
TOPE_VIVIENDA_NIVELES = 1
SALA_DISTRIBUIDORA_MAX_M2 = 60.0
CHAFLAN_CATETO_M = 0.9      # cateto del chaflán a 45 grados
CHAFLAN_LADO_MIN_M = 2.2    # no se corta la esquina de un local chico
CHAFLAN_TIPOS = ("BEDROOM", "DINING_ROOM", "KITCHEN", "LAVADERO",
                 "STOREROOM")
# v3.44.0: cateto del chaflán PROPIO de fachada (bay window): la
# esquina del local que cae en el CONTORNO se corta hacia dentro y
# la pérdida la absorbe el propio local (unidades de hotel)
CHAFLAN_PROPIO_CATETO_M = 0.6


def _es_vivienda(programa: Dict[str, Any]) -> bool:
    """Vivienda = el programa lleva dormitorios (BEDROOM)."""
    return any(r.get("space_type") == "BEDROOM"
               for r in (programa.get("renglones") or []))

# v3.42.0: PASILLOS Y FILTROS — como en el dibujo real de referencia
# (plano AP + morgue de hospital pediátrico): el empaquetado RESERVA
# primero el pasillo del contenedor y los locales cambian FONDO por
# ANCHO conservando su área para servirlo (adaptación dimensional,
# la misma lógica del cambio de uso); las filas de los satélites se
# RELLENAN hasta los bordes del contenedor (teselado completo) y el
# orden de colocación sigue el FLUJO (sucio al fondo, público en la
# entrada) con el FILTRO sanitario como barrera entre zonas.
RANK_FLUJO = {"publico": 0, "limpio": 1, "restringido": 2, "sucio": 3,
              "exterior": 4}
RANK_FILTRO = 2.5        # el filtro se coloca justo antes de lo sucio
TESELO_CRECIMIENTO = 1.6  # techo de crecimiento de un local sin area_max
PASILLO_FONDO_MIN_M = 1.5  # banda mínima a cada lado del pasillo
PASILLO_LADO_MIN_M = 1.2   # lado mínimo de un local en banda adaptada

# errores propios: ARQ-DDI-001..005 (importación y encaje),
# ARQ-DDI-006/007 (configuraciones), ARQ-DDI-008 (explicaciones),
# ARQ-DDI-009 (petición de programa incorrecta: selección vacía o
# nivel de ajuste desconocido) y ARQ-DDI-010 (el programa no entra
# ni con el ajuste máximo).


PT = Tuple[float, float]


# ---------------------------------------------------------------------------
# 1) GEOMETRÍA DEL CONTORNO: inferir forma y medidas
# ---------------------------------------------------------------------------

def _area_con_signo(puntos: List[PT]) -> float:
    total = 0.0
    n = len(puntos)
    for i in range(n):
        x1, y1 = puntos[i]
        x2, y2 = puntos[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _norm_poligono(puntos: List[PT]) -> List[PT]:
    """Vértices a float, sin repetidos consecutivos ni cierre duplado;
    antihorario. Menos de 3 vértices útiles -> ARQ-DDI-001."""
    pts: List[PT] = []
    for p in puntos or []:
        try:
            q = (float(p[0]), float(p[1]))
        except (TypeError, ValueError, IndexError):
            continue
        if pts and abs(q[0] - pts[-1][0]) < 1e-9 \
                and abs(q[1] - pts[-1][1]) < 1e-9:
            continue
        pts.append(q)
    while len(pts) >= 2 and abs(pts[0][0] - pts[-1][0]) < 1e-9 \
            and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts.pop()
    if len(pts) < 3:
        raise DomainError(
            message="El contorno necesita al menos 3 vértices útiles",
            code="ARQ-DDI-001",
            context={"vertices": len(pts)},
            suggested_action="Importe un DXF con una polilínea cerrada, "
                             "elija un espacio del proyecto o dibuje el "
                             "rectángulo del área.")
    if _area_con_signo(pts) < 0:
        pts.reverse()
    if abs(_area_con_signo(pts)) < 1e-9:
        raise DomainError(
            message="El contorno tiene área nula (vértices colineales)",
            code="ARQ-DDI-001",
            context={"vertices": len(pts)},
            suggested_action="Revise el dibujo: los vértices no "
                             "delimitan un área.")
    return pts


def _lado(v: PT) -> float:
    return math.hypot(v[0], v[1])


def _es_rectangulo(pts: List[PT]) -> bool:
    """Cuatro vértices con lados opuestos paralelos e iguales y
    ángulos rectos (cualquier orientación)."""
    if len(pts) != 4:
        return False
    lados = []
    for i in range(4):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % 4]
        lados.append((bx - ax, by - ay))
    for i in range(2):
        a, b = lados[i], lados[(i + 2) % 4]
        if abs(abs(a[0]) - abs(b[0])) > 1e-6 \
                or abs(abs(a[1]) - abs(b[1])) > 1e-6:
            return False
    a, b = lados[0], lados[1]
    producto = a[0] * b[0] + a[1] * b[1]
    return abs(producto) <= 1e-6 * (_lado(a) * _lado(b) + 1e-12)


def _ortogonal(pts: List[PT]) -> bool:
    """Todos los ángulos interiores rectos (forma en L, en T...)."""
    n = len(pts)
    if n < 4:
        return False
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        cx, cy = pts[(i + 2) % n]
        v1 = (bx - ax, by - ay)
        v2 = (cx - bx, cy - by)
        producto = v1[0] * v2[0] + v1[1] * v2[1]
        if abs(producto) > 1e-6 * (_lado(v1) * _lado(v2) + 1e-12):
            return False
    return True


def angulos_interiores(pts: List[PT]) -> List[float]:
    """Ángulo interior de cada vértice en grados (polígono CCW):
    convexo = el ángulo entre los vecinos; cóncavo = 360 menos ese."""
    n = len(pts)
    salida: List[float] = []
    for i in range(n):
        previo = pts[(i - 1) % n]
        actual = pts[i]
        siguiente = pts[(i + 1) % n]
        u = (previo[0] - actual[0], previo[1] - actual[1])
        v = (siguiente[0] - actual[0], siguiente[1] - actual[1])
        lu = math.hypot(u[0], u[1])
        lv = math.hypot(v[0], v[1])
        if lu < 1e-12 or lv < 1e-12:
            salida.append(0.0)
            continue
        coseno = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1])
                               / (lu * lv)))
        llano = math.degrees(math.acos(coseno))
        # cóncavo si el giro previo->actual->siguiente es horario (CCW)
        cruz = ((actual[0] - previo[0]) * (siguiente[1] - actual[1])
                - (actual[1] - previo[1]) * (siguiente[0] - actual[0]))
        salida.append(round(360.0 - llano, 2) if cruz < 0
                      else round(llano, 2))
    return salida


def concavidades_de(pts: List[PT]) -> List[int]:
    """Índices de los vértices cóncavos (reflejos) del polígono CCW."""
    n = len(pts)
    salida: List[int] = []
    for i in range(n):
        previo = pts[(i - 1) % n]
        actual = pts[i]
        siguiente = pts[(i + 1) % n]
        cruz = ((actual[0] - previo[0]) * (siguiente[1] - actual[1])
                - (actual[1] - previo[1]) * (siguiente[0] - actual[0]))
        if cruz < -1e-9:
            salida.append(i)
    return salida


def autointersecado(pts: List[PT]) -> bool:
    """True si dos aristas NO adyacentes se cruzan (forma de lazo):
    el contorno importado no delimita un área útil honesta."""
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue  # adyacentes: comparten vértice y es legal
            c, d = pts[j], pts[(j + 1) % n]
            if _segmentos_cruzan(a, b, c, d):
                return True
    return False


def inferir(puntos: List[PT]) -> Dict[str, Any]:
    """Infiere forma y medidas del contorno dibujado/importado."""
    pts = _norm_poligono(puntos)
    area = abs(_area_con_signo(pts))
    perimetro = sum(_lado((pts[(i + 1) % len(pts)][0] - pts[i][0],
                           pts[(i + 1) % len(pts)][1] - pts[i][1]))
                    for i in range(len(pts)))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    ancho = bbox[2] - bbox[0]
    fondo = bbox[3] - bbox[1]
    # centroide del polígono (fórmula estándar; caja si degenera)
    cx = cy = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        cruz = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cruz
        cy += (y1 + y2) * cruz
    if abs(area) > 1e-12:
        cx, cy = cx / (6.0 * _area_con_signo(pts)), \
            cy / (6.0 * _area_con_signo(pts))
    else:
        cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    rectangulo = _es_rectangulo(pts)
    if rectangulo:
        forma = "rectangulo"
    elif _ortogonal(pts):
        forma = "ortogonal"
    else:
        forma = "poligono"
    alineado = rectangulo and all(
        abs(v[0]) < 1e-9 or abs(v[1]) < 1e-9
        for v in ((pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]),
                  (pts[2][0] - pts[1][0], pts[2][1] - pts[1][1])))
    lados = [round(_lado((pts[(i + 1) % len(pts)][0] - pts[i][0],
                          pts[(i + 1) % len(pts)][1] - pts[i][1])), 3)
             for i in range(len(pts))]
    menor = min(ancho, fondo)
    relacion = round(max(ancho, fondo) / menor, 3) if menor > 1e-9 \
        else 999.0
    return {"vertices": [(round(x, 6), round(y, 6)) for x, y in pts],
            "area_m2": round(area, 4), "perimetro_m": round(perimetro, 4),
            "bbox": bbox, "ancho_m": round(ancho, 4),
            "fondo_m": round(fondo, 4),
            "centroide": (round(cx, 6), round(cy, 6)),
            "forma": forma, "alineado": alineado,
            "lados": lados, "angulos": angulos_interiores(pts),
            "concavidades": len(concavidades_de(pts)),
            "relacion": relacion}


# ---------------------------------------------------------------------------
# 2) VERIFICACIÓN HONESTA: ¿el rectángulo queda DENTRO del contorno?
# ---------------------------------------------------------------------------

def _orient(a: PT, b: PT, c: PT) -> int:
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(v) < 1e-12:
        return 0
    return 1 if v > 0 else -1


def _en_segmento(a: PT, b: PT, p: PT) -> bool:
    return (min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9
            and min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9)


def _segmentos_cruzan(a: PT, b: PT, c: PT, d: PT) -> bool:
    o1 = _orient(a, b, c)
    o2 = _orient(a, b, d)
    o3 = _orient(c, d, a)
    o4 = _orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _en_segmento(a, b, c):
        return True
    if o2 == 0 and _en_segmento(a, b, d):
        return True
    if o3 == 0 and _en_segmento(c, d, a):
        return True
    if o4 == 0 and _en_segmento(c, d, b):
        return True
    return False


def _punto_dentro(punto: PT, poligono: List[PT]) -> bool:
    x, y = punto
    dentro = False
    j = len(poligono) - 1
    for i in range(len(poligono)):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if (yi > y) != (yj > y):
            cruz = (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            if x < cruz:
                dentro = not dentro
        j = i
    return dentro


def _encoge_rect(rect: List[PT], margen: float) -> List[PT]:
    xs = sorted(set(p[0] for p in rect))
    ys = sorted(set(p[1] for p in rect))
    if len(xs) < 2 or len(ys) < 2:
        return rect
    return [(xs[0] + margen, ys[0] + margen),
            (xs[1] - margen, ys[0] + margen),
            (xs[1] - margen, ys[1] - margen),
            (xs[0] + margen, ys[1] - margen)]


def rect_dentro(rect: List[PT], poligono: List[PT]) -> bool:
    """El rectángulo axis-alineado queda dentro del polígono simple:
    su centro está dentro y su borde (encogido 1 mm para tolerar los
    contactos rasantes con el contorno) no cruza ninguna arista."""
    centro = (sum(p[0] for p in rect) / len(rect),
              sum(p[1] for p in rect) / len(rect))
    if not _punto_dentro(centro, poligono):
        return False
    peque = _encoge_rect(rect, 0.001)
    for i in range(4):
        a, b = peque[i], peque[(i + 1) % 4]
        for j in range(len(poligono)):
            c, d = poligono[j], poligono[(j + 1) % len(poligono)]
            if _segmentos_cruzan(a, b, c, d):
                return False
    return True


# ---------------------------------------------------------------------------
# 3) CONTORNOS DESDE DXF (polilíneas cerradas del archivo)
# ---------------------------------------------------------------------------

def contornos_dxf(path: str) -> List[Dict[str, Any]]:
    """Polilíneas cerradas del DXF (LWPOLYLINE y POLYLINE), ordenadas
    de mayor a menor área. El asistente deja elegir cuál es el
    contorno del área; el resto del dibujo (muros, líneas) se ignora
    aquí a propósito. Desde v3.37.0 sobrevive a planos reales: las
    coordenadas se escalan a metros según $INSUNITS (mm/cm/pies...),
    se acepta el cierre geométrico (primero == último, el duplicado
    habitual del CAD) y las polilíneas casi cerradas (hueco <= máx
    2 cm o 0.1 por mil de la diagonal) se cierran automáticamente con
    la marca ``cerrada_auto`` y el ``hueco_m`` detectado."""
    if not os.path.isfile(path):
        raise DomainError(
            message=f"Archivo DXF inexistente: {path}",
            code="ARQ-DDI-004", context={"path": path},
            suggested_action="Revise la ruta del archivo.")
    try:
        import ezdxf
    except ImportError as exc:  # pragma: no cover
        raise DomainError(
            message="ezdxf no está instalado; ejecute el bat de "
                    "instalación de dependencias",
            code="ARQ-DDI-005") from exc
    try:
        doc = ezdxf.readfile(path)
    except Exception as exc:  # noqa: BLE001 — archivo corrupto
        raise DomainError(
            message=f"DXF ilegible: {exc}",
            code="ARQ-DDI-005", context={"path": path}) from exc
    from importers.dxf_reader import escala_unidades_dxf
    _codigo, escala, _etiqueta = escala_unidades_dxf(doc)
    brutas: List[Tuple[str, List[PT], bool, float]] = []
    for entity in doc.modelspace():
        tipo = entity.dxftype()
        capa = str(entity.dxf.layer)
        try:
            if tipo == "LWPOLYLINE":
                pts = [(float(x) * escala, float(y) * escala)
                       for x, y in entity.get_points("xy")]
                if entity.closed:
                    brutas.append((capa, pts, False, 0.0))
                else:
                    hueco = _hueco_cierre(pts)
                    if hueco <= _tol_cierre(pts):
                        brutas.append((capa, pts, hueco > 0.0, hueco))
            elif tipo == "POLYLINE":
                # is_closed es el atributo estable en ezdxf: .closed
                # puede no existir en POLYLINEs leídas del archivo
                if getattr(entity, "is_closed", False):
                    brutas.append((capa, [(float(p[0]) * escala,
                                           float(p[1]) * escala)
                                          for p in entity.points()],
                                   False, 0.0))
        except Exception:  # noqa: BLE001 — entidad malformada
            continue
    contornos: List[Dict[str, Any]] = []
    for capa, pts, auto, hueco in brutas:
        try:
            forma = inferir(pts)
        except DomainError:
            continue
        c = {"nombre": f"Contorno {len(contornos) + 1}",
             "capa": capa, "puntos": forma["vertices"],
             "area_m2": forma["area_m2"], "ancho_m": forma["ancho_m"],
             "fondo_m": forma["fondo_m"], "forma": forma["forma"]}
        if auto:
            c["cerrada_auto"] = True
            c["hueco_m"] = round(hueco, 4)
        contornos.append(c)
    contornos.sort(key=lambda c: (-c["area_m2"], c["nombre"]))
    for i, c in enumerate(contornos, start=1):
        c["nombre"] = f"Contorno {i} ({c['capa']})"
    return contornos


def _hueco_cierre(pts: List[PT]) -> float:
    """Distancia entre el primer y el último vértice (inf si <3)."""
    if len(pts) < 3:
        return float("inf")
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    return ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5


def _tol_cierre(pts: List[PT]) -> float:
    """Hueco tolerable para cerrar un contorno solo: máx(2 cm, 1 por
    mil de la diagonal de la caja)."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5
    return max(0.02, diag * 0.001)


# ---------------------------------------------------------------------------
# 4) PROGRAMA POR USOS DEL DNA (modo edificación)
# ---------------------------------------------------------------------------

def programa_edificacion(usos: List[Dict[str, Any]],
                         nombre: str = "Edificación desde dibujo") \
        -> Dict[str, Any]:
    """Programa a partir de usos del DNA con cantidades: la misma
    estructura de renglones que programa_servicio, para reutilizar el
    ajuste, el reparto y la aplicación tal cual."""
    renglones: List[Dict[str, Any]] = []
    avisos: List[str] = []
    notas: List[str] = []
    for uso in usos or []:
        if not isinstance(uso, dict):
            avisos.append("uso ignorado (no era una ficha de uso)")
            continue
        tipo = str(uso.get("space_type", "") or "").strip().upper()
        if not tipo:
            avisos.append("uso sin tipo: ignorado")
            continue
        try:
            cantidad = max(1, int(float(uso.get("cantidad", 1) or 1)))
        except (TypeError, ValueError):
            cantidad = 1
            avisos.append(f"{tipo}: cantidad ilegible, se usa 1")
        pedido = None
        try:
            crudo = uso.get("area_m2")
            if crudo is not None and str(crudo).strip() != "":
                pedido = float(crudo)
                if pedido <= 0:
                    pedido = None
                    avisos.append(f"{tipo}: área no positiva, se usa "
                                  "la del DNA")
        except (TypeError, ValueError):
            avisos.append(f"{tipo}: área ilegible, se usa la del DNA")
        dna = _dna_de(None, tipo)
        minimo = float(getattr(dna, "minimum_area", 0.0) or 0.0) \
            if dna is not None else 0.0
        preferida = float(getattr(dna, "preferred_area", 0.0) or 0.0) \
            if dna is not None else 0.0
        area = pedido if pedido else (preferida or minimo or 25.0)
        if minimo and area + 1e-9 < minimo:
            avisos.append(
                f"{tipo}: {area:.2f} m2 por debajo del mínimo del uso "
                f"({minimo:.2f} m2), se usa el mínimo")
            area = minimo
        if dna is None:
            avisos.append(f"{tipo}: uso fuera del DNA (sin reglas "
                          "dimensionales)")
        nombre_uso = (getattr(dna, "name_es", "") or tipo) \
            if dna is not None else tipo
        for copia in range(1, cantidad + 1):
            nombre_local = nombre_uso if copia == 1 \
                else f"{nombre_uso} {copia}"
            ancho, fondo = _dimensiones(area)
            renglones.append({
                "codigo": tipo, "nombre": nombre_local,
                "space_type": tipo, "area_m2": round(area, 2),
                "ancho_m": ancho, "fondo_m": fondo, "flujo": "libre",
                "critico": False, "req": [], "adjacencias": [],
                "area_min": round(minimo, 2) if minimo else 0.0,
                "descripcion": "Uso social del DNA" if dna is not None
                else "Uso sin ficha en el DNA",
                "copia": copia})
    if not renglones:
        raise DomainError(
            message="El programa no tiene locales que encajar",
            code="ARQ-DDI-002", context={"usos": len(usos or [])},
            suggested_action="Añada al menos un uso con cantidad en el "
                             "modo edificación.")
    sin_dna = sorted({r["space_type"] for r in renglones
                      if "sin ficha en el DNA" in r["descripcion"]})
    if sin_dna:
        notas.append("Usos sin ficha en el DNA (se dimensionan con el "
                     "área pedida): " + ", ".join(sin_dna))
    total = round(sum(r["area_m2"] for r in renglones), 2)
    return {"servicio": "", "nombre": nombre,
            "descripcion": "Programa por usos sociales del DNA desde "
                           "un contorno dibujado",
            "parametros": {}, "renglones": renglones,
            "totales": {"locales": len(renglones), "area_m2": total},
            "flujos": [], "notas": notas, "avisos": avisos,
            "validacion": []}


# ---------------------------------------------------------------------------
# 5) EL NÚCLEO VERTICAL: recinto de escalera según Blondel
# ---------------------------------------------------------------------------

def caja_escalera(altura_nivel_m: float) -> Dict[str, Any]:
    """Recinto que reserva el asistente para la escalera entre
    niveles: en U hasta dos tramos (lo compacto para alturas de
    piso normales) y recta a partir de tres; el dimensionamiento
    sale de Blondel (v3.19.0)."""
    altura = max(2.0, float(altura_nivel_m or 3.0))
    d = escaleras.dimensionar(altura)
    tramo = ANCHO_TRAMO_ESC_M
    por_tramo = int(d["por_tramo"])
    huella = float(d["huella_m"])
    mesetas = int(d["mesetas"])
    tramos = int(d["tramos"])
    if tramos <= 2:
        ancho = round(2 * tramo + 0.4, 2)
        fondo = round(por_tramo * huella + mesetas * tramo + 0.2, 2)
        planta = "en U (dos tramos con meseta)"
    else:
        ancho = round(tramo + 0.4, 2)
        fondo = round(por_tramo * huella * tramos + mesetas * tramo
                      + 0.2, 2)
        planta = "recta (tres o más tramos)"
    return {"ancho_m": ancho, "fondo_m": fondo, "planta": planta,
            "dimensionar": d}


# ---------------------------------------------------------------------------
# 6) ¿CABE? empaquetado por niveles dentro del contorno
# ---------------------------------------------------------------------------

def _peso(r: Dict[str, Any]) -> float:
    """Ancho de fachada del local en su banda (criterio v3.33.0).
    Los recintos-nave (v3.36.0) aportan su ancho propio."""
    hall = float(r.get("hall_ancho") or 0.0)
    if hall > 0.0:
        return hall
    return max(float(r["ancho_m"]), float(r["area_m2"]) / FONDO_MAX)


# Recintos-nave (v3.36.0): locales de superficie grande (nave de
# almacén, sala de ventas, gimnasio, patio) cuya área no cabe en una
# celda normal de banda (ancho capado x fondo capado). Van SOLOS en
# su nivel como un rectángulo proporcional profundo junto al pasillo.
HALL_AREA_UMBRAL = ANCHO_MAX * FONDO_MAX


def _es_hall(r: Dict[str, Any]) -> bool:
    """True si el renglón es un recinto-nave (área que agotó el
    fondo capado y desborda la celda normal)."""
    return (float(r.get("fondo_m") or 0.0) >= FONDO_MAX - 1e-6
            and float(r.get("area_m2") or 0.0) > HALL_AREA_UMBRAL + 1e-6)


def _hall_dims(r: Dict[str, Any], ancho_disp: float,
               fondo_disp: float) -> Dict[str, float]:
    """Dimensiones de la nave: proporcional si cabe, y si no llena
    el fondo útil; error honesto si el contorno no la admite."""
    area = float(r["area_m2"])
    fondo = min(math.sqrt(PROPORCION_DEF * area), max(fondo_disp, 1e-6))
    ancho = area / max(fondo, 1e-6)
    if ancho > ancho_disp + 1e-9:
        raise DomainError(
            message=f"El recinto {r['nombre']} ({area:.0f} m2) no cabe "
                    f"en el contorno útil ({ancho_disp:.2f} x "
                    f"{fondo_disp:.2f} m disponibles para nave): ningún "
                    "nivel lo hace posible",
            code="ARQ-DDI-003",
            context={"local": r["nombre"], "area_m2": area},
            suggested_action="Amplíe el contorno dibujado o reduzca "
                             "el área de ese local.")
    return {"hall_ancho": round(ancho, 2),
            "hall_fondo": round(fondo, 2)}


def _asigna_niveles(programa: Dict[str, Any], envolvente: Dict[str, float],
                    con_escalera: bool, caja_esc: Dict[str, Any],
                    patio_ancho: float = 0.0) -> List[Dict[str, Any]]:
    """Reparte los renglones del programa en niveles: pasillo a dos
    bandas dentro de la caja útil; si un renglón ya no entra, se
    abre el siguiente nivel (crecimiento en altura). Desde v3.39.0
    reserva además el ancho del patio (opción experta) junto a la
    escalera en el extremo del pasillo."""
    w = envolvente["ancho_util"]
    d = envolvente["fondo_util"]
    fondo_esc = float(caja_esc["fondo_m"]) if con_escalera else 0.0
    patio_ancho = max(0.0, float(patio_ancho or 0.0))
    niveles: List[Dict[str, Any]] = []
    actual: Dict[str, List[Dict[str, Any]]] = {"norte": [], "sur": []}

    def cierra() -> None:
        if actual["norte"] or actual["sur"]:
            niveles.append(actual)

    for r in programa["renglones"]:
        ancho_r = _peso(r)
        fondo_r = float(r["fondo_m"])
        if PASILLO_ANCHO + fondo_r > d + 1e-9 \
                or (con_escalera and fondo_esc > d + 1e-9):
            raise DomainError(
                message=f"El local {r['nombre']} ({ancho_r:.2f} x "
                        f"{fondo_r:.2f} m) no cabe en el contorno útil "
                        f"({w:.2f} x {d:.2f} m): ningún nivel lo hace "
                        "posible",
                code="ARQ-DDI-003",
                context={"local": r["nombre"], "ancho_m": ancho_r,
                         "fondo_m": fondo_r},
                suggested_action="Amplíe el contorno dibujado, reduzca "
                                 "el área de ese local o divídalo en "
                                 "dos usos.")
        if ancho_r > w + 1e-9:
            # la fachada requerida excede el ancho del contorno: si el
            # renglón es un recinto-nave (v3.36.0) va SOLO en su nivel
            # como rectángulo proporcional profundo junto al pasillo;
            # si no, es imposible (comportamiento v3.34.0)
            if not _es_hall(r):
                raise DomainError(
                    message=f"El local {r['nombre']} ({ancho_r:.2f} x "
                            f"{fondo_r:.2f} m) no cabe en el contorno "
                            f"útil ({w:.2f} x {d:.2f} m): ningún nivel "
                            "lo hace posible",
                    code="ARQ-DDI-003",
                    context={"local": r["nombre"], "ancho_m": ancho_r,
                             "fondo_m": fondo_r},
                    suggested_action="Amplíe el contorno dibujado, "
                                     "reduzca el área de ese local o "
                                     "divídalo en dos usos.")
            esc = float(caja_esc["ancho_m"]) if con_escalera else 0.0
            ancho_disp = max(1.0, w - esc - patio_ancho)
            fondo_disp = max(0.0, d - PASILLO_ANCHO)
            hall = _hall_dims(r, ancho_disp, fondo_disp)
            cierra()
            niveles.append({"norte": [dict(r, **hall)], "sur": []})
            actual = {"norte": [], "sur": []}
            continue
        if not actual["norte"] and not actual["sur"]:
            actual["norte"].append(r)
            continue
        wn = sum(_peso(x) for x in actual["norte"])
        ws = sum(_peso(x) for x in actual["sur"])
        # primero la banda con menos fachada (equilibrio); si no entra,
        # se prueba la otra (banda simple: pasillo pegado a un lado)
        orden = ["sur", "norte"] if wn < ws else ["norte", "sur"]
        colocado = False
        for banda in orden:
            prueba = {"norte": list(actual["norte"]),
                      "sur": list(actual["sur"])}
            prueba[banda].append(r)
            largo = max(LARGO_PASILLO_MIN_M,
                        sum(_peso(x) for x in prueba["norte"]),
                        sum(_peso(x) for x in prueba["sur"]))
            fondo_n = max((float(x["fondo_m"])
                           for x in prueba["norte"]), default=0.0)
            fondo_s = max((float(x["fondo_m"])
                           for x in prueba["sur"]), default=0.0)
            prof = PASILLO_ANCHO + fondo_n + fondo_s
            total = largo + (float(caja_esc["ancho_m"])
                             if con_escalera else 0.0) + patio_ancho
            if total <= w + 1e-9 and prof <= d + 1e-9:
                actual = prueba
                colocado = True
                break
        if not colocado:
            cierra()
            actual = {"norte": [r], "sur": []}
    cierra()
    return niveles


def _geometria_nivel(banda_n: List[Dict[str, Any]],
                     banda_s: List[Dict[str, Any]],
                     envolvente: Dict[str, float],
                     con_escalera: bool, caja_esc: Dict[str, Any],
                     patio_ancho: float = 0.0,
                     ancho_pasillo: float = PASILLO_ANCHO) -> Dict[str, Any]:
    """Rectángulos del pasillo, de los locales, de la escalera y del
    patio (opción experta v3.39.0) de UN nivel, en coordenadas del
    dibujo. v3.42.0: ``ancho_pasillo`` permite corredores adaptados
    (2.40 m de salud, 1.50 o 1.20 m en servicios pequeños)."""
    x0 = envolvente["x0"]
    y0 = envolvente["y0"]
    d = float(envolvente["fondo_util"])
    # v3.42.0: el fondo de banda manda lo ADAPTADO (hall_fondo del
    # pasillo adaptado); sin adaptación manda fondo_m como siempre
    fondo_n = max((float(r.get("hall_fondo") or 0.0)
                   or float(r["fondo_m"]) for r in banda_n), default=0.0)
    fondo_s = max((float(r.get("hall_fondo") or 0.0)
                   or float(r["fondo_m"]) for r in banda_s), default=0.0)
    largo = max(LARGO_PASILLO_MIN_M,
                sum(_peso(r) for r in banda_n),
                sum(_peso(r) for r in banda_s))
    ys = y0 + fondo_s                      # borde sur del pasillo
    pasillo = {"nombre": "Pasillo de distribución",
               "space_type": "CORRIDOR",
               "rect": [(x0, ys), (x0 + largo, ys),
                        (x0 + largo, ys + ancho_pasillo),
                        (x0, ys + ancho_pasillo)],
               "area_m2": round(largo * ancho_pasillo, 2),
               "flujo": "publico", "critico": False, "req": [],
               "adjacencias": [], "codigo": "PASILLO", "copia": 1,
               "ancho_m": round(largo, 2), "fondo_m": ancho_pasillo,
               "descripcion": "Distribución del programa encajado"}
    colocados: List[Dict[str, Any]] = []

    def coloca(items: List[Dict[str, Any]], banda: int) -> None:
        x = x0
        for r in items:
            ancho = float(r.get("hall_ancho") or 0.0) or _peso(r)
            fondo = float(r.get("hall_fondo") or 0.0) \
                or float(r["fondo_m"])
            if banda > 0:
                rect = [(x, ys + ancho_pasillo),
                        (x + ancho, ys + ancho_pasillo),
                        (x + ancho, ys + ancho_pasillo + fondo),
                        (x, ys + ancho_pasillo + fondo)]
            else:
                rect = [(x, ys), (x + ancho, ys),
                        (x + ancho, ys - fondo), (x, ys - fondo)]
            r["rect"] = rect
            x += ancho
            colocados.append(r)

    coloca(banda_n, 1)
    coloca(banda_s, -1)
    escalera = None
    if con_escalera:
        ancho_e = float(caja_esc["ancho_m"])
        fondo_e = float(caja_esc["fondo_m"])
        # centrada en el eje del pasillo, sujetada a la caja útil
        yc = ys + ancho_pasillo / 2.0
        yc = max(y0 + fondo_e / 2.0, min(yc, y0 + d - fondo_e / 2.0))
        rect_e = [(x0 + largo, yc - fondo_e / 2.0),
                  (x0 + largo + ancho_e, yc - fondo_e / 2.0),
                  (x0 + largo + ancho_e, yc + fondo_e / 2.0),
                  (x0 + largo, yc + fondo_e / 2.0)]
        escalera = {"nombre": "Escalera", "space_type": "STAIR",
                    "rect": rect_e,
                    "area_m2": round(ancho_e * fondo_e, 2),
                    "flujo": "publico", "critico": False, "req": [],
                    "adjacencias": [], "codigo": "ESCALERA",
                    "copia": 1, "ancho_m": ancho_e, "fondo_m": fondo_e,
                    "descripcion": "Recinto reservado para la "
                                   "escalera entre niveles"}
    patio = None
    patio_ancho = max(0.0, float(patio_ancho or 0.0))
    if patio_ancho > 0.0:
        xp = x0 + largo + (float(caja_esc["ancho_m"])
                           if con_escalera else 0.0)
        patio = {"nombre": "Patio", "space_type": "PATIO",
                 "rect": [(xp, y0), (xp + patio_ancho, y0),
                          (xp + patio_ancho, y0 + d), (xp, y0 + d)],
                 "area_m2": round(patio_ancho * d, 2),
                 "flujo": "exterior", "critico": False, "req": [],
                 "adjacencias": [], "codigo": "PATIO", "copia": 1,
                 "ancho_m": round(patio_ancho, 2), "fondo_m": round(d, 2),
                 "descripcion": "Patio exterior reservado (opción "
                                "experta): ilumina y ventila sin "
                                "contar como área útil"}
    return {"pasillo": pasillo, "locales": colocados, "escalera": escalera,
            "patio": patio,
            "area_ocupada": round(
                pasillo["area_m2"]
                + sum(r["area_m2"] for r in colocados)
                + (escalera["area_m2"] if escalera else 0.0)
                + (patio["area_m2"] if patio else 0.0), 2)}


# ---------------------------------------------------------------------------
# 6b) ENCAJE ESTRICTO AL POLÍGONO (v3.40.0): los contenedores reales
#     de la parcela (domain/encaje.py) sustituyen a la caja envolvente
#     como zona de empaquetado. Nada puede quedar fuera del polígono
#     y los codos de la L, las patas de la U o los brazos de la T se
#     aprovechan con locales en vez de quedar como hueco perdido.
# ---------------------------------------------------------------------------

def _fila_prueba(estado: Dict[str, Any], r: Dict[str, Any],
                 cont: Dict[str, float], confirmar: bool) -> bool:
    """¿Cabe el local en el empaquetado por filas del contenedor?
    Prueba en el cursor las dos orientaciones; si ninguna entra,
    abre fila nueva. Con confirmar=True deja el cursor avanzado."""
    ancho = float(r.get("hall_ancho") or 0.0) or _peso(r)
    fondo = float(r.get("hall_fondo") or 0.0) or float(r["fondo_m"])
    orientaciones = ((ancho, fondo), (fondo, ancho))
    for aa, ff in orientaciones:
        if estado["x"] + aa <= cont["x1"] + 1e-9 \
                and estado["y"] + ff <= cont["y1"] + 1e-9:
            if confirmar:
                estado["items"].append(r)
                estado["fila_h"] = max(float(estado["fila_h"]), ff)
                estado["x"] = estado["x"] + aa
            return True
    # fila nueva: al borde izquierdo, sobre la fila más profunda
    y_fila = float(estado["y"]) + float(estado["fila_h"])
    for aa, ff in orientaciones:
        if cont["x0"] + aa <= cont["x1"] + 1e-9 \
                and y_fila + ff <= cont["y1"] + 1e-9:
            if confirmar:
                estado["items"].append(r)
                estado["x"] = cont["x0"] + aa
                estado["y"] = y_fila
                estado["fila_h"] = ff
            return True
    return False


def _fila_rects(items: List[Dict[str, Any]],
                cont: Dict[str, float]) -> None:
    """Rectángulos definitivos del empaquetado por filas (misma
    mecánica que _fila_prueba, aplicada a la lista confirmada)."""
    estado: Dict[str, Any] = {"items": [], "x": cont["x0"], "y": cont["y0"],
                              "fila_h": 0.0}
    for r in items:
        ancho = float(r.get("hall_ancho") or 0.0) or _peso(r)
        fondo = float(r.get("hall_fondo") or 0.0) or float(r["fondo_m"])
        for aa, ff in ((ancho, fondo), (fondo, ancho)):
            if estado["x"] + aa <= cont["x1"] + 1e-9 \
                    and estado["y"] + ff <= cont["y1"] + 1e-9:
                r["rect"] = [(estado["x"], estado["y"]),
                             (estado["x"] + aa, estado["y"]),
                             (estado["x"] + aa, estado["y"] + ff),
                             (estado["x"], estado["y"] + ff)]
                estado["fila_h"] = max(float(estado["fila_h"]), ff)
                estado["x"] = estado["x"] + aa
                break
        else:
            y_fila = float(estado["y"]) + float(estado["fila_h"])
            for aa, ff in ((ancho, fondo), (fondo, ancho)):
                if cont["x0"] + aa <= cont["x1"] + 1e-9 \
                        and y_fila + ff <= cont["y1"] + 1e-9:
                    r["rect"] = [(cont["x0"], y_fila),
                                 (cont["x0"] + aa, y_fila),
                                 (cont["x0"] + aa, y_fila + ff),
                                 (cont["x0"], y_fila + ff)]
                    estado["x"] = cont["x0"] + aa
                    estado["y"] = y_fila
                    estado["fila_h"] = ff
                    break
            else:  # pragma: no cover — la confirmación ya lo garantiza
                raise DomainError(
                    message=f"El local {r['nombre']} no reproduce su "
                            "posición de fila en el contenedor",
                    code="ARQ-DDI-003")


# ---------------------------------------------------------------------------
# 6c) PASILLOS Y FILTROS (v3.42.0): orden por flujo, pasillo adaptado
#     (el local cambia fondo por ancho conservando su área) y teselado
#     completo de las filas (rellenar el contenedor hasta los bordes).
# ---------------------------------------------------------------------------

def _orden_flujo(renglones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Orden de colocación por flujo: sucio primero (queda en la banda
    norte, la más lejana de la entrada), después el FILTRO sanitario
    como barrera, luego restringido, limpio y público. Estable: los
    locales del mismo flujo conservan el orden del catálogo.
    v3.43.0: si NADIE lleva flujo real (vivienda y edificación por
    usos del DNA, todos «libre»), el orden es por ÁREA DESCENDENTE —
    los locales grandes entran primero y las filas apilan sin
    descartar los chicos para un nivel siguiente."""
    con_flujo = any(str(r.get("flujo", "")) not in ("", "libre", None)
                    for r in renglones)
    if not con_flujo:
        # la clave es el área IDEAL (sellada antes de tocar nada): el
        # teselado crece area_m2 en cada ensayo y reordenar entre
        # reintentos rompería la convergencia de niveles
        return sorted(renglones,
                      key=lambda r: (-float(r.get("area_ideal")
                                             or r.get("area_m2") or 0.0),))
    def clave(r: Dict[str, Any]) -> float:
        if str(r.get("space_type", "")).upper() == "FILTER":
            return RANK_FILTRO
        return float(RANK_FLUJO.get(str(r.get("flujo", "")), 1.5))

    return sorted(renglones, key=lambda r: -clave(r))


def _cap_area_de(r: Dict[str, Any]) -> float:
    """Techo de área del teselado completo: el máximo del catálogo
    (si lo tiene) o 60 % sobre el área ideal del programa."""
    ideal = float(r.get("area_ideal") or r.get("area_m2") or 0.0)
    mx = float(r.get("area_max") or 0.0)
    if mx > 0.0:
        return max(mx, ideal)
    return max(ideal * TESELO_CRECIMIENTO, ideal)


def _marca_crecimiento(r: Dict[str, Any]) -> None:
    """Registra cuánto creció el local al teselar (ideal -> final)."""
    ideal = float(r.get("area_ideal") or r.get("area_m2") or 0.0)
    r.setdefault("area_ideal", round(ideal, 2))
    final = float(r["area_m2"])
    r["crecido_m2"] = round(max(0.0, final - ideal), 2)


def _dims_actuales(r: Dict[str, Any]) -> Tuple[float, float]:
    """Dimensiones vigentes del local: hall_ancho/hall_fondo si están
    (banda adaptada) o las del rect ya colocado (satélites)."""
    if float(r.get("hall_ancho") or 0.0) > 0.0 \
            and float(r.get("hall_fondo") or 0.0) > 0.0:
        return float(r["hall_ancho"]), float(r["hall_fondo"])
    x0, y0 = float(r["rect"][0][0]), float(r["rect"][0][1])
    x1, y1 = float(r["rect"][2][0]), float(r["rect"][2][1])
    return (x1 - x0, y1 - y0)


def _reparte_ancho(fila: List[Dict[str, Any]],
                   ancho_objetivo: float) -> None:
    """Reparte el ancho sobrante de UNA fila entre sus locales para
    llegar al borde del contenedor: crecimiento proporcional acotado
    por el techo de área de cada local; los que llegan a su techo se
    congelan y el resto reparte lo que queda (3 pasadas). Deja los
    anchos en hall_ancho/hall_fondo (los rects los recoloca el
    llamador: _llena_filas en satélites, _geometria_nivel en bandas)."""
    if not fila:
        return
    for _ in range(3):
        ancho_act = sum(_dims_actuales(r)[0] for r in fila)
        libres = [r for r in fila
                  if float(r.get("area_m2", 0.0)) < _cap_area_de(r) - 1e-9
                  and not _es_hall(r)]
        faltan = ancho_objetivo - ancho_act
        if faltan <= 1e-9 or not libres:
            break
        peso_total = sum(_dims_actuales(r)[0] for r in libres)
        if peso_total <= 1e-9:
            share = faltan / len(libres)
            for r in libres:
                r["_delta_ancho"] = share
        else:
            for r in libres:
                a = _dims_actuales(r)[0]
                r["_delta_ancho"] = faltan * a / peso_total
        # aplica con techo; el sobrante de un local congelado se
        # reparte en la siguiente pasada
        for r in fila:
            delta = float(r.pop("_delta_ancho", 0.0) or 0.0)
            if delta <= 1e-9:
                continue
            ancho, fondo = _dims_actuales(r)
            techo_ancho = max(0.0, _cap_area_de(r) / max(fondo, 1e-9))
            nuevo = min(ancho + delta, techo_ancho)
            if nuevo - ancho <= 1e-9:
                continue
            r["hall_ancho"] = round(nuevo, 4)
            r["hall_fondo"] = round(fondo, 4)
            r["area_m2"] = round(nuevo * fondo, 2)
            _marca_crecimiento(r)


def _llena_filas(items: List[Dict[str, Any]],
                 cont: Dict[str, float]) -> None:
    """TESELADO COMPLETO de un contenedor empaquetado por filas
    (satélites y camino sin pasillo): alinea cada fila a la
    profundidad de la fila más profunda, reparte el ancho sobrante
    hasta el borde derecho y crece la última fila hasta el borde
    superior. Nada sale del contenedor (y el contenedor es parte del
    polígono), así que la verificación dura sigue pasando."""
    if not items:
        return
    # sincroniza hall_ancho/hall_fondo con los rects ya colocados
    for r in items:
        x0, y0 = float(r["rect"][0][0]), float(r["rect"][0][1])
        x1, y1 = float(r["rect"][2][0]), float(r["rect"][2][1])
        r["hall_ancho"] = round(x1 - x0, 4)
        r["hall_fondo"] = round(y1 - y0, 4)
    filas: Dict[float, List[Dict[str, Any]]] = {}
    for r in items:
        filas.setdefault(round(float(r["rect"][0][1]), 6), []).append(r)
    claves = sorted(filas)
    # 1) alinear cada fila a su profundidad (los poco profundos crecen;
    # los recintos-nave quedan EXACTOS: se dimensionan solos)
    for y0 in claves:
        fila = filas[y0]
        h = max(float(r["hall_fondo"]) for r in fila)
        for r in fila:
            if _es_hall(r):
                continue
            ancho, fondo = float(r["hall_ancho"]), float(r["hall_fondo"])
            if fondo >= h - 1e-9:
                continue
            techo_fondo = _cap_area_de(r) / max(ancho, 1e-9)
            nuevo = min(h, max(fondo, techo_fondo))
            if nuevo - fondo <= 1e-9:
                continue
            r["hall_fondo"] = round(nuevo, 4)
            r["area_m2"] = round(ancho * nuevo, 2)
            _marca_crecimiento(r)
    # 2) ancho sobrante de cada fila
    ancho_cont = float(cont["x1"]) - float(cont["x0"])
    for y0 in claves:
        _reparte_ancho(filas[y0], ancho_cont)
    # 3) fondo restante del contenedor en la última fila
    fila_ult = filas[claves[-1]]
    tope = float(cont["y0"]) + sum(
        max(float(r["hall_fondo"]) for r in filas[y]) for y in claves)
    sobra = float(cont["y1"]) - tope
    if sobra > 0.05:
        for r in fila_ult:
            if _es_hall(r):
                continue
            ancho, fondo = float(r["hall_ancho"]), float(r["hall_fondo"])
            techo_fondo = _cap_area_de(r) / max(ancho, 1e-9)
            nuevo = min(fondo + sobra, max(fondo, techo_fondo))
            if nuevo - fondo <= 1e-9:
                continue
            r["hall_fondo"] = round(nuevo, 4)
            r["area_m2"] = round(ancho * nuevo, 2)
            _marca_crecimiento(r)
        _reparte_ancho(fila_ult, ancho_cont)
    # rects finales de izquierda a derecha por fila (los recintos-nave
    # conservan ancho_m/fondo_m propios: su identidad de nave depende
    # de fondo_m >= FONDO_MAX)
    for y0 in claves:
        x = float(cont["x0"])
        for r in filas[y0]:
            ancho = float(r["hall_ancho"])
            fondo = float(r["hall_fondo"])
            r["rect"] = [(x, y0), (x + ancho, y0), (x + ancho, y0 + fondo),
                         (x, y0 + fondo)]
            if not _es_hall(r):
                r["ancho_m"] = round(ancho, 2)
                r["fondo_m"] = round(fondo, 2)
            x += ancho


def _adapta_banda(r: Dict[str, Any], fondo_banda: float,
                  ancho_util: float) -> Optional[Tuple[float, float]]:
    """Dimensiones del local para servir el pasillo con fondo
    ``fondo_banda``: MISMA ÁREA cambiando fondo por ancho (la
    adaptación del cambio de uso). Devuelve (ancho, fondo) o None si
    no cabe en la banda (el ancho necesario rebasa el utilizable y
    el local debe ir a un satélite o compuesto). El lado nunca baja
    de 1.20 m (un filtro de paso estrecho existe; un local de 0.90 m
    no): el área que el claquo añade se registra como crecimiento."""
    area = float(r.get("area_m2") or 0.0)
    if area <= 1e-9:
        return None
    ancho = area / fondo_banda
    if ancho > ancho_util + 1e-9:
        return None
    if ancho < PASILLO_LADO_MIN_M - 1e-9:
        ancho = PASILLO_LADO_MIN_M
    return (round(ancho, 4), round(fondo_banda, 4))


def _arma_corredor(pend: List[Dict[str, Any]],
                   conts: List[Dict[str, float]], con_escalera: bool,
                   caja_esc: Dict[str, Any], patio_a: float,
                   poligono: Optional[List[PT]]) \
        -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Nivel CON pasillo servido por adaptación (v3.42.0): elige el
    contenedor que mejor sirva de distribuidor, reserva el pasillo en
    su eje y los locales de cada banda cambian fondo por ancho
    conservando su área hasta caber; los que no caben en ninguna
    banda van a satélites en filas y el SOBRANTE vuelve al llamador
    (como el camino histórico: cada nivel lleva su pasillo). Prueba
    anchos de pasillo (2.40 m de salud -> 1.50 -> 1.20) y repartos de
    fondo entre bandas (50/50, 60/40...) en ENSAYOS con restauración,
    se queda el que más locales coloque y lo REPITE para commit (el
    empaquetado es determinista). Si nada sirve, devuelve None y el
    camino histórico recibe los locales EXACTAMENTE como llegaron."""
    CLAVES = ("hall_ancho", "hall_fondo", "contenedor", "area_m2",
              "area_ideal", "crecido_m2", "ancho_m", "fondo_m")
    retrato = {id(r): {k: r.get(k) for k in CLAVES} for r in pend}

    def restaurar() -> None:
        for r in pend:
            r.update(retrato[id(r)])

    orden = sorted(range(len(conts)),
                   key=lambda i: (-float(conts[i]["area"]), i))
    esc_w = float(caja_esc["ancho_m"]) if con_escalera else 0.0
    patio_a = max(0.0, float(patio_a or 0.0))
    # anchos de pasillo a probar: el de salud y los de vivienda
    # (un corredor de 1.20 m admite carros en un servicio pequeño)
    anchos_pas = [PASILLO_ANCHO, 1.5, 1.2]
    # cortes de fondo a probar entre las dos bandas (proporción norte)
    cortes = [0.5, 0.6, 0.4, 0.7, 0.3, 0.65, 0.35, 0.75, 0.25]

    def ensayo(w_pas: float, ci: int, k: float) \
            -> Optional[Tuple[int, Dict[str, Any], List[Dict[str, Any]],
                              List[Dict[str, Any]], float, float]]:
        """UN ensayo completo (con restauración del estado si el
        llamador lo pide): devuelve (colocados, geo, satelites, resto,
        fn, fs) o None si el contenedor no admite esta combinación."""
        c = conts[ci]
        w, d = float(c["ancho"]), float(c["fondo"])
        ancho_util = w - esc_w - patio_a
        disp = d - w_pas
        if ancho_util < ENCAJE_MIN_LADO_M \
                or disp < 2 * PASILLO_FONDO_MIN_M:
            return None
        # el pasillo mide al menos LARGO_PASILLO_MIN_M y con escalera
        # el ancho debe dejar sitio al recinto reservado
        if con_escalera and ancho_util < LARGO_PASILLO_MIN_M:
            return None
        if w - patio_a < LARGO_PASILLO_MIN_M:
            return None
        fn = round(disp * k, 4)
        fs = round(disp - fn, 4)
        if min(fn, fs) < PASILLO_FONDO_MIN_M:
            return None
        norte: List[Dict[str, Any]] = []
        sur: List[Dict[str, Any]] = []
        sats: Dict[int, List[Dict[str, Any]]] = {}
        sats_abiertos: List[Dict[str, Any]] = []
        resto: List[Dict[str, Any]] = []
        wn = ws = 0.0
        for r in pend:
            colocado = False
            es_hall = _es_hall(r)
            for es_norte, lista, fondo_b in ((True, norte, fn),
                                             (False, sur, fs)):
                dims = _adapta_banda(r, fondo_b, ancho_util)
                if dims is None:
                    continue
                aa, ff = dims
                acumulado = wn if es_norte else ws
                if acumulado + aa > ancho_util + 1e-9:
                    continue
                r["hall_ancho"], r["hall_fondo"] = aa, ff
                if aa * ff > float(r["area_m2"]) + 1e-9:
                    r["area_m2"] = round(aa * ff, 2)
                    _marca_crecimiento(r)
                r["contenedor"] = ci
                lista.append(r)
                if es_norte:
                    wn += aa
                else:
                    ws += aa
                colocado = True
                break
            if colocado:
                continue
            if es_hall:
                # los recintos-nave NO van a satélites (sus dimensiones
                # capadas no los representan) ni se les crece: quedan
                # para el camino histórico, que los dimensiona solos
                # contra el contenedor (v3.36.0)
                resto.append(r)
                continue
            # satélites ya abiertos (dimensiones íntegras)
            for st in sats_abiertos:
                if _fila_prueba(st, r, conts[st["idx"]], True):
                    r["contenedor"] = st["idx"]
                    colocado = True
                    break
            if colocado:
                continue
            for idx, cc in enumerate(conts):
                if idx == ci or idx in sats:
                    continue
                if not any(encaje.comparten_banda(cc, u, MIN_BANDA_CONEX_M)
                           for u in ([c] + [conts[s["idx"]]
                                            for s in sats_abiertos])):
                    continue
                st = {"idx": idx, "items": [], "x": cc["x0"],
                      "y": cc["y0"], "fila_h": 0.0}
                if _fila_prueba(st, r, cc, True):
                    sats_abiertos.append(st)
                    sats[idx] = st["items"]
                    r["contenedor"] = idx
                    colocado = True
                    break
            if not colocado:
                resto.append(r)
        colocados = len(pend) - len(resto)
        if colocados <= 0:
            return None
        return (colocados, {"contenedor": ci, "w_pas": w_pas,
                            "fn": fn, "fs": fs, "norte": norte,
                            "sur": sur, "sats": sats,
                            "sats_abiertos": sats_abiertos},
                resto, None, fn, fs)

    mejor = None       # (colocados, orden_pref, params)
    servido = False
    try:
        for pref, w_pas in enumerate(anchos_pas):
            for ci in orden:
                vistos: set = set()
                for k in cortes:
                    fn = round((conts[ci]["fondo"] - w_pas) * k, 4)
                    fs = round(conts[ci]["fondo"] - w_pas - fn, 4)
                    if (fn, fs) in vistos:
                        continue
                    vistos.add((fn, fs))
                    res = ensayo(w_pas, ci, k)
                    restaurar()
                    if res is None:
                        continue
                    colocados = res[0]
                    if colocados == len(pend):
                        # nivel COMPLETO con esta combinación: gana ya
                        mejor = (colocados, pref, res[1])
                        break
                    if mejor is None or colocados > mejor[0]:
                        mejor = (colocados, pref, res[1])
                if mejor is not None and mejor[0] == len(pend):
                    break
            if mejor is not None and mejor[0] == len(pend):
                break
        if mejor is None:
            return None
        # COMMIT: se repite el ensayo ganador (determinista) y se
        # construye la geometría definitiva
        params = mejor[2]
        res = ensayo(params["w_pas"], params["contenedor"],
                     params["fn"] / (params["fn"] + params["fs"]))
        if res is None:
            return None
        _, datos, resto, _, fn, fs = res
        ci = datos["contenedor"]
        c = conts[ci]
        w = float(c["ancho"])
        ancho_util = w - esc_w - patio_a
        norte, sur = datos["norte"], datos["sur"]
        sats = datos["sats"]
        # rellena las bandas hasta el borde derecho (misma área ya
        # garantizada por _adapta_banda: solo crece lo diminuto); los
        # recintos-nave conservan su identidad (fondo_m >= FONDO_MAX:
        # si se la quitamos, la siguiente pasada los hace crecer como
        # locales normales y duplica su área)
        for lista, fondo_b in ((norte, fn), (sur, fs)):
            _reparte_ancho(lista, ancho_util)
            for r in lista:
                if _es_hall(r):
                    continue
                r["hall_fondo"] = fondo_b
                r["fondo_m"] = round(fondo_b, 2)
        env0 = {"x0": float(c["x0"]), "y0": float(c["y0"]),
                "ancho_util": w, "fondo_util": float(c["fondo"])}
        geo = _geometria_nivel(norte, sur, env0, con_escalera,
                               caja_esc, patio_a,
                               ancho_pasillo=params["w_pas"])
        if geo.get("pasillo"):
            geo["pasillo"]["adaptado"] = True
        locales = list(geo["locales"])
        for idx in sats:
            _fila_rects(sats[idx], conts[idx])
            _llena_filas(sats[idx], conts[idx])
            locales.extend(sats[idx])
        geo["locales"] = locales
        # v3.42.0: el área ocupada del nivel cuenta TAMBIÉN los
        # satélites (antes solo las bandas: el aprovechamiento
        # salía subestimado)
        geo["area_ocupada"] = round(
            sum(float(r["area_m2"]) for r in locales)
            + (float(geo["pasillo"]["area_m2"])
               if geo.get("pasillo") else 0.0)
            + (float(geo["escalera"]["area_m2"])
               if geo.get("escalera") else 0.0)
            + (float(geo["patio"]["area_m2"])
               if geo.get("patio") else 0.0), 2)
        geo["satelites"] = ([(st["idx"], st["items"])
                             for st in datos["sats_abiertos"]
                             if st["items"]])
        geo["bandas"] = {"norte": norte, "sur": sur}
        geo["pasillo_adaptado"] = True
        geo["pasillo_contenedor"] = ci
        servido = True
        return geo, resto
    finally:
        # si no se devolvió ningún nivel, los locales quedan EXACTOS:
        # el camino histórico (y su verificación dura) manda
        if not servido:
            restaurar()


def _arma_nivel(pend: List[Dict[str, Any]], conts: List[Dict[str, float]],
                con_escalera: bool, caja_esc: Dict[str, Any],
                patio_a: float,
                sin_pasillo: bool = False,
                poligono: Optional[List[PT]] = None) \
        -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Construye UN nivel consumiendo locales de ``pend`` (en orden).
    Primero los locales que no caben en ninguna franja sola prueban
    ZONAS COMPUESTAS (unión de dos contenedores adyacentes, siempre
    dentro del polígono) y su hueco se resta de los contenedores; el
    contenedor mayor lleva luego el pasillo a dos bandas (con escalera
    y patio si proceden) y los contenedores conectados restantes
    reciben locales en filas. Con ``sin_pasillo=True`` todos los
    contenedores conectados se llenan por filas sin pasillo. Devuelve
    (geo, resto).

    v3.42.0: antes del camino histórico, el nivel intenta el PASILLO
    ADAPTADO (_arma_corredor): el contenedor distribuidor reserva el
    pasillo y los locales cambian fondo por ancho conservando su área
    hasta servirlo; las filas de los satélites se rellenan hasta los
    bordes (_llena_filas)."""
    conts = [dict(c) for c in conts]  # copia local: las restas de las
    # zonas compuestas valen SOLO para este nivel
    compuestos: List[Dict[str, Any]] = []
    if poligono is not None:
        quedan: List[Dict[str, Any]] = []
        for r in pend:
            if not _encaje_imposible(r, conts):
                quedan.append(r)
                continue
            hueco = _compuesto_de(r, conts, poligono)
            if hueco is None:
                quedan.append(r)
                continue
            ancho = _peso(r)
            fondo = float(r["fondo_m"])
            if ancho <= hueco["ancho"] + 1e-9 \
                    and fondo <= hueco["fondo"] + 1e-9:
                aa, ff = ancho, fondo
            else:
                aa, ff = fondo, ancho
            r["rect"] = [(hueco["x0"], hueco["y0"]),
                         (hueco["x0"] + aa, hueco["y0"]),
                         (hueco["x0"] + aa, hueco["y0"] + ff),
                         (hueco["x0"], hueco["y0"] + ff)]
            r["contenedor"] = -1
            compuestos.append(r)
            conts = _resta_rect(conts, {"x0": hueco["x0"],
                                        "y0": hueco["y0"],
                                        "x1": hueco["x0"] + aa,
                                        "y1": hueco["y0"] + ff},
                                ENCAJE_MIN_LADO_M)
        pend = quedan
        if not conts and compuestos:
            if pend:
                raise DomainError(
                    message="Tras reservar las zonas compuestas del "
                            "nivel, los contenedores se agotan y "
                            f"quedan {len(pend)} local(es) sin sitio: "
                            "el programa no cabe en este contorno",
                    code="ARQ-DDI-003",
                    suggested_action="Amplíe el contorno o reduzca el "
                                     "programa.")
            geo_vacio = {"pasillo": None, "escalera": None,
                         "patio": None, "locales": list(compuestos),
                         "satelites": [(-1, list(compuestos))],
                         "bandas": {"norte": [], "sur": []},
                         "area_ocupada": round(sum(
                             float(r["area_m2"])
                             for r in compuestos), 2)}
            return geo_vacio, []
    cont0 = conts[0]
    w = float(cont0["ancho"])
    d = float(cont0["fondo"])
    esc_w = float(caja_esc["ancho_m"]) if con_escalera else 0.0
    patio_a = max(0.0, float(patio_a or 0.0))
    # v3.42.0: PASILLO ADAPTADO antes del camino histórico — el nivel
    # se arma con el pasillo servido por los locales re-dimensionados
    # (misma área, cambia fondo por ancho) y los satélites teselados.
    if poligono is not None and not sin_pasillo:
        corredor = _arma_corredor(pend, conts, con_escalera, caja_esc,
                                  patio_a, poligono)
        if corredor is not None:
            geo_c, resto_c = corredor
            if compuestos:
                geo_c["locales"] = compuestos + list(geo_c["locales"])
                geo_c["satelites"] = ([(-1, list(compuestos))]
                                      + list(geo_c["satelites"]))
                geo_c["area_ocupada"] = round(
                    float(geo_c["area_ocupada"])
                    + sum(float(r["area_m2"]) for r in compuestos), 2)
            return geo_c, resto_c
    if sin_pasillo:
        # filas en TODOS los contenedores conectados (cont0 incluido);
        # la escalera se reserva como franja a la izquierda de cont0
        work0 = dict(cont0)
        escalera = None
        if con_escalera:
            ancho_e = min(float(caja_esc["ancho_m"]), w * 0.4)
            fondo_e = float(caja_esc["fondo_m"])
            if fondo_e <= d + 1e-9 and ancho_e < w:
                escalera = {"nombre": "Escalera",
                            "space_type": "STAIR",
                            "rect": [(cont0["x0"], cont0["y0"]),
                                     (cont0["x0"] + ancho_e, cont0["y0"]),
                                     (cont0["x0"] + ancho_e,
                                      cont0["y0"] + fondo_e),
                                     (cont0["x0"],
                                      cont0["y0"] + fondo_e)],
                            "area_m2": round(ancho_e * fondo_e, 2),
                            "flujo": "publico", "critico": False,
                            "req": [], "adjacencias": [],
                            "codigo": "ESCALERA", "copia": 1,
                            "ancho_m": round(ancho_e, 2),
                            "fondo_m": fondo_e,
                            "descripcion": "Recinto reservado para la "
                                           "escalera entre niveles"}
                work0 = dict(cont0, x0=cont0["x0"] + ancho_e,
                             ancho=round(w - ancho_e, 4),
                             area=round((w - ancho_e) * d, 4))
        locales: List[Dict[str, Any]] = []
        abiertos: List[Dict[str, Any]] = []
        resto: List[Dict[str, Any]] = []

        def work_de(idx: int) -> Dict[str, float]:
            return work0 if idx == 0 else conts[idx]

        for r in pend:
            colocado = False
            for st in abiertos:
                if _fila_prueba(st, r, work_de(st["idx"]), True):
                    r["contenedor"] = st["idx"]
                    colocado = True
                    break
            if colocado:
                continue
            usados = [conts[st["idx"]] for st in abiertos] or [cont0]
            for idx, c in enumerate(conts):
                if any(st["idx"] == idx for st in abiertos):
                    continue
                if idx != 0 and not any(
                        encaje.comparten_banda(c, u, MIN_BANDA_CONEX_M)
                        for u in usados):
                    continue
                st = {"idx": idx, "items": [], "x": work_de(idx)["x0"],
                      "y": work_de(idx)["y0"], "fila_h": 0.0}
                if _fila_prueba(st, r, work_de(idx), True):
                    abiertos.append(st)
                    r["contenedor"] = idx
                    colocado = True
                    break
            if not colocado:
                resto.append(r)
        for st in abiertos:
            _fila_rects(st["items"], work_de(st["idx"]))
            _llena_filas(st["items"], work_de(st["idx"]))
            locales.extend(st["items"])
        area_ocupada = round(sum(float(r["area_m2"]) for r in locales)
                             + (escalera["area_m2"] if escalera else 0.0),
                             2)
        geo = {"pasillo": None, "escalera": escalera, "patio": None,
               "locales": compuestos + locales,
               "satelites": ([(-1, list(compuestos))]
                             if compuestos else [])
               + [(st["idx"], st["items"])
                  for st in abiertos if st["items"]],
               "bandas": {"norte": [], "sur": []},
               "area_ocupada": area_ocupada}
        if patio_a > 0.0:
            geo["aviso_patio"] = (
                "el nivel va sin pasillo, así que el patio experto no "
                "se reserva en él")
        return geo, resto
    disp_w = max(1.0, w - esc_w - patio_a)
    norte: List[Dict[str, Any]] = []
    sur: List[Dict[str, Any]] = []
    sats: List[Dict[str, Any]] = []
    resto: List[Dict[str, Any]] = []
    if not conts:
        resto = list(pend)

    def cabe(n_: List[Dict[str, Any]], s_: List[Dict[str, Any]]) -> bool:
        largo = max(LARGO_PASILLO_MIN_M,
                    sum(_peso(x) for x in n_),
                    sum(_peso(x) for x in s_))
        fn = max((float(x["fondo_m"]) for x in n_), default=0.0)
        fs = max((float(x["fondo_m"]) for x in s_), default=0.0)
        return (largo + esc_w + patio_a <= w + 1e-9
                and PASILLO_ANCHO + fn + fs <= d + 1e-9)

    for r in pend:
        ancho_r = _peso(r)
        # recinto-nave gigante: SU nivel entero (v3.36.0), dentro del
        # contenedor mayor como rectángulo proporcional
        if not norte and not sur and not sats \
                and _es_hall(r) and ancho_r > disp_w + 1e-9:
            hall = _hall_dims(r, disp_w,
                              max(0.0, d - PASILLO_ANCHO))
            norte.append(dict(r, **hall))
            r["contenedor"] = 0
            continue
        if not norte and not sur:
            if cabe([r], []):
                norte.append(r)
                r["contenedor"] = 0
                continue
        else:
            wn = sum(_peso(x) for x in norte)
            ws = sum(_peso(x) for x in sur)
            hecho = False
            for banda in (["sur", "norte"] if wn < ws
                          else ["norte", "sur"]):
                n2, s2 = list(norte), list(sur)
                (n2 if banda == "norte" else s2).append(r)
                if cabe(n2, s2):
                    norte, sur = n2, s2
                    r["contenedor"] = 0
                    hecho = True
                    break
            if hecho:
                continue
        # satélites ya abiertos
        colocado = False
        for st in sats:
            if _fila_prueba(st, r, conts[st["idx"]], True):
                r["contenedor"] = st["idx"]
                colocado = True
                break
        if colocado:
            continue
        # abrir un satélite NUEVO conectado con lo ya usado del nivel
        usados = [cont0] + [conts[st["idx"]] for st in sats]
        for idx, c in enumerate(conts):
            if idx == 0 or any(st["idx"] == idx for st in sats):
                continue
            if not any(encaje.comparten_banda(c, u, MIN_BANDA_CONEX_M)
                       for u in usados):
                continue
            st = {"idx": idx, "items": [], "x": c["x0"], "y": c["y0"],
                  "fila_h": 0.0}
            if _fila_prueba(st, r, c, True):
                sats.append(st)
                r["contenedor"] = idx
                colocado = True
                break
        if colocado:
            continue
        resto.append(r)

    env0 = {"x0": cont0["x0"], "y0": cont0["y0"],
            "ancho_util": w, "fondo_util": d}
    geo = _geometria_nivel(norte, sur, env0, con_escalera, caja_esc,
                           patio_a)
    locales = list(geo["locales"])
    for st in sats:
        c = conts[st["idx"]]
        _fila_rects(st["items"], c)
        _llena_filas(st["items"], c)
        locales.extend(st["items"])
    locales = compuestos + locales
    # v3.42.0: el área ocupada cuenta TAMBIÉN los satélites y las
    # zonas compuestas
    geo["area_ocupada"] = round(
        sum(float(r["area_m2"]) for r in locales)
        + float(geo["pasillo"]["area_m2"])
        + (float(geo["escalera"]["area_m2"])
           if geo.get("escalera") else 0.0)
        + (float(geo["patio"]["area_m2"])
           if geo.get("patio") else 0.0), 2)
    geo["locales"] = locales
    geo["satelites"] = ([( -1, list(compuestos))] if compuestos
                        else []) \
        + [(st["idx"], st["items"]) for st in sats if st["items"]]
    geo["bandas"] = {"norte": norte, "sur": sur}
    return geo, resto


def _encaje_imposible(r: Dict[str, Any], conts: List[Dict[str, float]]) \
        -> bool:
    """El local no entra en NINGÚN contenedor con ninguna orientación
    (ignorando pasillo: los satélites no lo necesitan)."""
    ancho = _peso(r)
    fondo = float(r["fondo_m"])
    for c in conts:
        if (ancho <= c["ancho"] + 1e-9 and fondo <= c["fondo"] + 1e-9) \
                or (fondo <= c["ancho"] + 1e-9
                    and ancho <= c["fondo"] + 1e-9):
            return False
    return True


def _compuesto_de(r: Dict[str, Any], conts: List[Dict[str, float]],
                  poligono: List[PT]) -> Optional[Dict[str, float]]:
    """Unión rectangular de DOS contenedores adyacentes que aloja al
    local y queda DENTRO del polígono (p. ej. la sala de necropsias
    5.68 x 7.39 del plano real AP Y MORGUE, que no cabe en ninguna
    franja sola pero sí en la unión 13.88 x 8.14 de dos apiladas).
    Devuelve el candidato de MENOR área que sirve (menos desperdicio)
    o None."""
    ancho = _peso(r)
    fondo = float(r["fondo_m"])
    mejor: Optional[Dict[str, float]] = None
    for i in range(len(conts)):
        for j in range(i + 1, len(conts)):
            a, b = conts[i], conts[j]
            solape_x = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
            solape_y = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
            if solape_x >= MIN_BANDA_CONEX_M \
                    and solape_y >= MIN_BANDA_CONEX_M:
                continue  # se solapan: la unión no es un rectángulo útil
            apilados = (abs(a["y1"] - b["y0"]) <= 1e-6
                        or abs(a["y0"] - b["y1"]) <= 1e-6)
            lado_a_lado = (abs(a["x1"] - b["x0"]) <= 1e-6
                           or abs(a["x0"] - b["x1"]) <= 1e-6)
            if apilados:
                x0 = max(a["x0"], b["x0"])
                x1 = min(a["x1"], b["x1"])
                y0 = min(a["y0"], b["y0"])
                y1 = max(a["y1"], b["y1"])
            elif lado_a_lado:
                x0 = min(a["x0"], b["x0"])
                x1 = max(a["x1"], b["x1"])
                y0 = max(a["y0"], b["y0"])
                y1 = min(a["y1"], b["y1"])
            else:
                continue
            if x1 - x0 < min(ancho, fondo) - 1e-9 \
                    or y1 - y0 < min(ancho, fondo) - 1e-9:
                continue
            uni = {"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                   "ancho": round(x1 - x0, 4), "fondo": round(y1 - y0, 4),
                   "area": round((x1 - x0) * (y1 - y0), 4)}
            if not rect_dentro([(uni["x0"], uni["y0"]),
                                (uni["x1"], uni["y0"]),
                                (uni["x1"], uni["y1"]),
                                (uni["x0"], uni["y1"])], poligono):
                continue
            cabe = ((ancho <= uni["ancho"] + 1e-9
                     and fondo <= uni["fondo"] + 1e-9)
                    or (fondo <= uni["ancho"] + 1e-9
                        and ancho <= uni["fondo"] + 1e-9))
            if cabe and (mejor is None or uni["area"] < mejor["area"]):
                mejor = uni
    return mejor


def _resta_rect(conts: List[Dict[str, float]], hueco: Dict[str, float],
                min_lado: float) -> List[Dict[str, float]]:
    """Resta el hueco ocupado por un local compuesto de los
    contenedores: cada contenedor solapado se parte en hasta 4
    sub-rectángulos; los menores que min_lado se descartan."""
    salida: List[Dict[str, float]] = []
    for c in conts:
        sx = min(c["x1"], hueco["x1"]) - max(c["x0"], hueco["x0"])
        sy = min(c["y1"], hueco["y1"]) - max(c["y0"], hueco["y0"])
        if sx <= 1e-9 or sy <= 1e-9:
            salida.append(dict(c))
            continue
        trozos = []
        if hueco["x0"] - c["x0"] >= min_lado:
            trozos.append((c["x0"], c["y0"], hueco["x0"], c["y1"]))
        if c["x1"] - hueco["x1"] >= min_lado:
            trozos.append((hueco["x1"], c["y0"], c["x1"], c["y1"]))
        if hueco["y0"] - c["y0"] >= min_lado:
            trozos.append((max(c["x0"], hueco["x0"]), c["y0"],
                           min(c["x1"], hueco["x1"]), hueco["y0"]))
        if c["y1"] - hueco["y1"] >= min_lado:
            trozos.append((max(c["x0"], hueco["x0"]), hueco["y1"],
                           min(c["x1"], hueco["x1"]), c["y1"]))
        for x0, y0, x1, y1 in trozos:
            if x1 - x0 >= min_lado and y1 - y0 >= min_lado:
                salida.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                               "ancho": round(x1 - x0, 4),
                               "fondo": round(y1 - y0, 4),
                               "area": round((x1 - x0) * (y1 - y0), 4)})
    salida.sort(key=lambda c: -c["area"])
    return salida


def _circulacion_de(reparto: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resumen de circulación v3.42.0: niveles con pasillo (y cuál
    contenedor lo sirve), niveles sin él y filtros sanitarios por
    nivel."""
    niveles_con: List[Dict[str, Any]] = []
    filtros: List[Dict[str, Any]] = []
    for plan in reparto:
        if plan.get("pasillo"):
            niveles_con.append({
                "nivel": plan["nivel"],
                "area_m2": float(plan["pasillo"]["area_m2"]),
                "adaptado": bool(plan["pasillo"].get("adaptado"))})
        for r in plan.get("locales", []):
            if str(r.get("space_type", "")).upper() == "FILTER":
                filtros.append({"nivel": plan["nivel"],
                                "nombre": str(r.get("nombre", "")),
                                "area_m2": float(r.get("area_m2", 0.0))})
    sin_pas = [int(p["nivel"]) for p in reparto if not p.get("pasillo")]
    return {"niveles_con_pasillo": niveles_con,
            "niveles_sin_pasillo": sin_pas,
            "filtros": filtros}


def _avisos_filtros(reparto: List[Dict[str, Any]],
                    circulacion: Dict[str, Any]) -> List[str]:
    """Avisos honestos de barrera sanitaria (v3.42.0): un nivel que
    mezcla locales sucios con públicos o limpios necesita al menos un
    FILTRO en ese nivel; si el programa no lo trae (o se excluyó con
    la selección), se documenta para que el proyectista decida."""
    salida: List[str] = []
    for plan in reparto:
        locales = plan.get("locales", [])
        flujos = {str(r.get("flujo", "")) for r in locales}
        tiene_filtro = any(
            str(r.get("space_type", "")).upper() == "FILTER"
            for r in locales)
        if ("sucio" in flujos
                and ({"publico", "limpio"} & flujos)
                and not tiene_filtro):
            salida.append(
                f"Planta {plan['nivel']}: el nivel mezcla flujos "
                "sucios con públicos o limpios y NO lleva filtro "
                "sanitario (el programa no lo incluye o se excluyó "
                "con la selección): considere añadir el local Filtro "
                "del catálogo")
    return salida


def _teselado_de(reparto: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resumen del teselado completo v3.42.0: locales que crecieron
    para aprovechar los contenedores hasta sus bordes."""
    crecidos: List[Dict[str, Any]] = []
    for plan in reparto:
        for r in plan.get("locales", []):
            cre = float(r.get("crecido_m2") or 0.0)
            if cre > 0.01:
                crecidos.append({
                    "nivel": plan["nivel"],
                    "nombre": str(r.get("nombre", "")),
                    "area_ideal": float(r.get("area_ideal")
                                        or r.get("area_m2", 0.0)),
                    "area_final": float(r.get("area_m2", 0.0)),
                    "crecido_m2": round(cre, 2)})
    return {"locales_crecidos": len(crecidos), "detalle": crecidos,
            "area_ganada": round(sum(c["crecido_m2"]
                                     for c in crecidos), 2)}


def _bbox_de(rect: List[PT]) -> Tuple[float, float, float, float]:
    xs = [float(p[0]) for p in rect]
    ys = [float(p[1]) for p in rect]
    return min(xs), min(ys), max(xs), max(ys)


def _esquinas_rect(rect: List[PT]) -> List[Tuple[float, float]]:
    x0, y0, x1, y1 = _bbox_de(rect)
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _chaflanes_vivienda(crudos: List[Dict[str, Any]],
                        avisos: List[str],
                        vertices_contorno: Optional[List[PT]] = None,
                        propio: Optional[bool] = None) \
        -> List[Dict[str, Any]]:
    """v3.43.0: CHAFLANES A 45 GRADOS como en los planos de referencia
    del usuario (estudio de 25 m2 y sala central del plano árabe):
    corta la ESQUINA de los locales que dan a la SALA con un triángulo
    rectángulo isósceles (cateto 0.90 m o el que el margen del local
    permita) y el triángulo pasa a la SALA: su poligonal lo absorbe
    como abertura diagonal. Ningún corte deja al local por debajo de
    la norma y cada corte queda documentado con su pérdida. Devuelve
    el registro para el informe.

    v3.43.1: el piso de cada local es su MÍNIMO DEL DNA (``area_min``):
    el corte puede dar la esquina mientras el local no quede por
    debajo de la norma (el Z de 48 m2 con dormitorios de 14 m2
    ideales puede perder 0.41 m2 hacia la sala y seguir en 13.59 ≥
    9.0). Medir contra el renglón del programa los anulaba TODOS
    (los renglones llegan ya crecidos por el teselado) y el caso Z
    disparaba por casualidad: 2 dormitorios colisionaban en el dict
    de pisos por código.

    v3.44.0: el HUB puede ser la SALA o el LOBBY (VESTIBULE) cuando
    el programa no lleva sala (villas con hall distribuidor). Y el
    CHAFLÁN PROPIO de fachada (bay window): la esquina del local que
    cae EN EL CONTORNO se corta hacia dentro con cateto 0.60 m y la
    pérdida la absorbe el PROPIO local, como las ventanas en
    saliente a 45 grados de las unidades de hotel de las imágenes;
    ``propio=True`` lo fuerza, ``None`` lo deja SOLO para los
    niveles sin sala/lobby."""
    hechos: List[Dict[str, Any]] = []
    for geo in crudos:
        locales = geo.get("locales") or []
        sala = None
        for r in locales:
            if r.get("space_type") == "LIVING_ROOM" and (
                    sala is None or float(r["area_m2"])
                    > float(sala["area_m2"])):
                sala = r
        if sala is None:
            # v3.44.0: sin sala, el LOBBY (VESTIBULE) es el hub que
            # reparte y absorbe los cortes (villas con hall)
            for r in locales:
                if r.get("space_type") == "VESTIBULE" and (
                        sala is None or float(r["area_m2"])
                        > float(sala["area_m2"])):
                    sala = r

        # ---- v3.44.0: CHAFLÁN PROPIO DE FACHADA (bay window) ----
        # en auto (None) SOLO cuando el nivel no tiene sala/lobby;
        # con True se añade además del corte hacia la sala
        propio_activo = bool(propio) if propio is not None \
            else (sala is None)
        if vertices_contorno and propio_activo:
            bordes: List[Tuple[Tuple[float, float],
                               Tuple[float, float]]] = [
                (tuple(vertices_contorno[i]),
                 tuple(vertices_contorno[(i + 1)
                       % len(vertices_contorno)]))
                for i in range(len(vertices_contorno))]

            def _en_fachada(p: Tuple[float, float]) -> bool:
                for b1, b2 in bordes:
                    ux, uy = b2[0] - b1[0], b2[1] - b1[1]
                    norma = math.hypot(ux, uy)
                    if norma < 1e-9:
                        continue
                    t = ((p[0] - b1[0]) * ux
                         + (p[1] - b1[1]) * uy) / (norma * norma)
                    if t < -1e-9 or t > 1.0 + 1e-9:
                        continue
                    cruz = (p[0] - b1[0]) * uy \
                        - (p[1] - b1[1]) * ux
                    if abs(cruz) / norma <= 1e-6:
                        return True
                return False

            hechos_propios = 0
            for local in locales:
                if hechos_propios >= 6:
                    break
                if local is sala or local.get("poligono"):
                    continue
                if local.get("space_type") not in CHAFLAN_TIPOS:
                    continue
                rect_p = [tuple(q) for q in local["rect"]]
                esq_p = _esquinas_rect(rect_p)
                xs_p = sorted(set(q[0] for q in rect_p))
                ys_p = sorted(set(q[1] for q in rect_p))
                ancho_p, fondo_p = (xs_p[1] - xs_p[0],
                                    ys_p[1] - ys_p[0])
                if ancho_p < CHAFLAN_LADO_MIN_M \
                        and fondo_p < CHAFLAN_LADO_MIN_M:
                    continue
                piso_p = float(local.get("area_min") or 0.0)
                margen_p = float(local["area_m2"]) - piso_p
                if margen_p < 0.10:
                    continue
                fachada = [i for i in range(4)
                           if _en_fachada(esq_p[i])]
                if not fachada:
                    continue
                # par de esquinas OPUESTAS preferente (la bay window
                # vive en dos esquinas de fachada enfrentadas): (0,2)
                # o (1,3); si no hay par opuesto, solo la primera
                pares = [(i, i + 2) for i in fachada
                         if (i + 2) % 4 in fachada]
                if pares:
                    i0, i1 = pares[0]
                    if i0 in (1, 3) and (i0 - 2) % 4 in fachada:
                        i0 = (i0 - 2) % 4
                        i1 = (i0 + 2) % 4
                    fachada = [i0, i1]
                else:
                    fachada = fachada[:1]
                poly_p = [tuple(q) for q in rect_p]
                cortes_p = 0
                for i in fachada:
                    if cortes_p >= 2 or hechos_propios >= 6:
                        break
                    c_p = esq_p[i]
                    prev_p = esq_p[(i - 1) % 4]
                    nxt_p = esq_p[(i + 1) % 4]
                    cateto_p = min(CHAFLAN_PROPIO_CATETO_M,
                                   ancho_p / 2.0, fondo_p / 2.0)
                    perdida_p = cateto_p * cateto_p / 2.0
                    if perdida_p > margen_p - 0.05:
                        cateto_p = math.sqrt(
                            2.0 * max(0.05, margen_p - 0.05))
                        perdida_p = cateto_p * cateto_p / 2.0
                    if cateto_p < 0.30:
                        continue

                    def _paso(desde, hacia):
                        ux, uy = (hacia[0] - desde[0],
                                  hacia[1] - desde[1])
                        n = math.hypot(ux, uy)
                        if n < 1e-9:
                            return None
                        return (desde[0] + ux / n * cateto_p,
                                desde[1] + uy / n * cateto_p)

                    a_p = _paso(c_p, prev_p)
                    b_p = _paso(c_p, nxt_p)
                    if a_p is None or b_p is None:
                        continue
                    idx_p = None
                    for k, q in enumerate(poly_p):
                        if abs(q[0] - c_p[0]) < 1e-6 \
                                and abs(q[1] - c_p[1]) < 1e-6:
                            idx_p = k
                            break
                    if idx_p is None:
                        continue
                    poly_p = (poly_p[:idx_p] + [a_p, b_p]
                              + poly_p[idx_p + 1:])
                    margen_p -= perdida_p
                    cortes_p += 1
                    hechos_propios += 1
                    hechos.append({
                        "nivel": geo.get("nivel", 1),
                        "local": local["nombre"], "sala": "",
                        "tipo": "propio",
                        "cateto_m": round(cateto_p, 2),
                        "perdida_m2": round(perdida_p, 2),
                        "esquina": [round(c_p[0], 2),
                                    round(c_p[1], 2)]})
                if cortes_p:
                    local["poligono"] = [(round(p[0], 4),
                                          round(p[1], 4))
                                         for p in poly_p]
                    local["chaflan"] = {"tipo": "propio"}
                    local["area_m2"] = round(
                        float(local["area_m2"])
                        - sum(h["perdida_m2"] for h in hechos
                              if h.get("local") == local["nombre"]
                              and h.get("tipo") == "propio"), 2)

        if sala is None:
            continue
        sx0, sy0, sx1, sy1 = _bbox_de(sala["rect"])
        lados_sala = [
            ("sur", (sx0, sy0), (sx1, sy0)),
            ("este", (sx1, sy0), (sx1, sy1)),
            ("norte", (sx0, sy1), (sx1, sy1)),
            ("oeste", (sx0, sy0), (sx0, sy1))]
        ocupados: Dict[str, List[Tuple[float, float]]] = {}
        cortes: Dict[str, List[Tuple[float, float, Tuple[float, float],
                                            Tuple[float, float],
                                            Tuple[float, float]]]] = {}

        def _intervalo_en_lado(punto: Tuple[float, float],
                               u: Tuple[float, float], lado: Tuple) \
                -> Optional[float]:
            """Distancia recorrible desde ``punto`` en la dirección
            ``u`` por el lado ``lado`` de la sala (0.0 si el segmento
            no es colineal o no solapa)."""
            nombre, p1, p2 = lado
            if abs(u[1]) < 1e-9:      # horizontal
                if abs(p1[1] - punto[1]) > 1e-6:
                    return None
                if p2[0] < p1[0]:
                    p1, p2 = p2, p1
                lo, hi = max(p1[0], punto[0]), p2[0]
            else:                     # vertical
                if abs(p1[0] - punto[0]) > 1e-6:
                    return None
                if p2[1] < p1[1]:
                    p1, p2 = p2, p1
                lo, hi = max(p1[1], punto[1]), p2[1]
            return max(0.0, hi - lo)

        for local in locales:
            if local is sala or sum(
                    1 for h in hechos if h.get("tipo") != "propio") >= 4:
                continue
            if local.get("space_type") not in CHAFLAN_TIPOS:
                continue
            rect = [tuple(q) for q in local["rect"]]
            esq = _esquinas_rect(rect)
            xs = sorted(set(p[0] for p in rect))
            ys = sorted(set(p[1] for p in rect))
            ancho, fondo = xs[1] - xs[0], ys[1] - ys[0]
            if ancho < CHAFLAN_LADO_MIN_M and fondo < CHAFLAN_LADO_MIN_M:
                continue
            # v3.43.1: el piso es el MÍNIMO DEL DNA del propio local
            # (norma dimensional): el teselado crece los renglones y
            # medir contra ellos anulaba todos los cortes
            piso = float(local.get("area_min") or 0.0)
            margen = float(local["area_m2"]) - piso
            if margen < 0.10:
                continue
            # esquinas candidatas ordenadas por cercanía al centro de
            # la sala (el corte abre el local hacia el distribuidor)
            centro_sala = ((sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0)
            orden = sorted(range(4), key=lambda i: (esq[i][0]
                             - centro_sala[0]) ** 2
                             + (esq[i][1] - centro_sala[1]) ** 2)
            hecho = None
            for i in orden:
                c = esq[i]
                prev = esq[(i - 1) % 4]
                nxt = esq[(i + 1) % 4]
                for u, lado in (
                        (((prev[0] - c[0]) or 0.0,
                          (prev[1] - c[1]) or 0.0), None),
                        (((nxt[0] - c[0]) or 0.0,
                          (nxt[1] - c[1]) or 0.0), None)):
                    norma = math.hypot(u[0], u[1])
                    if norma < 1e-9:
                        continue
                    uu = (u[0] / norma, u[1] / norma)
                    if lado is None:
                        for ld in lados_sala:
                            disp = _intervalo_en_lado(c, uu, ld)
                            if disp is not None and disp >= 0.45:
                                hecho = (c, uu, prev, nxt, ld, norma)
                                break
                    if hecho:
                        break
                if hecho:
                    break
            if hecho is None:
                continue
            c, uu, prev, nxt, lado, norma_arista = hecho
            # cateto: el pedido, capado por lados y por el margen
            cateto = min(CHAFLAN_CATETO_M, ancho / 2.0, fondo / 2.0)
            perdida = cateto * cateto / 2.0
            if perdida > margen - 0.05:
                cateto = math.sqrt(2.0 * max(0.05, margen - 0.05))
                perdida = cateto * cateto / 2.0
            if cateto < 0.45:
                continue
            a_prima = (c[0] + uu[0] * cateto, c[1] + uu[1] * cateto)
            # el otro cateto: hacia la segunda arista de la esquina
            u2 = ((nxt[0] - c[0]), (nxt[1] - c[1]))
            n2 = math.hypot(u2[0], u2[1])
            if n2 < 1e-9 or abs(u2[0] / n2 * uu[0]
                                + u2[1] / n2 * uu[1]) > 0.5:
                u2 = ((prev[0] - c[0]), (prev[1] - c[1]))
                n2 = math.hypot(u2[0], u2[1])
                if n2 < 1e-9:
                    continue
            b_prima = (c[0] + u2[0] / n2 * cateto,
                       c[1] + u2[1] / n2 * cateto)
            # poligonal del local: la esquina se sustituye por el
            # corte diagonal (5 vértices)
            poly = [tuple(q) for q in rect]
            for k, q in enumerate(poly):
                if abs(q[0] - c[0]) < 1e-6 and abs(q[1] - c[1]) < 1e-6:
                    poly[k] = None
            if None not in poly:
                continue
            idx = poly.index(None)
            poly = poly[:idx] + [a_prima, b_prima] + poly[idx + 1:]
            local["poligono"] = [(round(p[0], 4), round(p[1], 4))
                                 for p in poly]
            local["chaflan"] = {"esquina": [round(c[0], 4),
                                            round(c[1], 4)],
                                "cateto_m": round(cateto, 3),
                                "perdida_m2": round(perdida, 3)}
            local["area_m2"] = round(float(local["area_m2"]) - perdida, 2)
            # la sala absorbe el triángulo: el corte se acumula por
            # LADO (los vértices se insertan SOLO entre las dos
            # esquinas de ese lado de la sala, nunca por parámetro
            # global que matchearía esquinas de otros lados)
            nombre_lado, lp1, lp2 = lado
            if abs(lp2[0] - lp1[0]) < 1e-9:      # vertical
                t_total = lp2[1] - lp1[1]
            else:
                t_total = lp2[0] - lp1[0]
            if abs(t_total) < 1e-9:
                continue

            def _t(punto):
                if abs(lp2[0] - lp1[0]) < 1e-9:
                    return (punto[1] - lp1[1]) / t_total
                return (punto[0] - lp1[0]) / t_total

            ta, tb = sorted((_t(a_prima), _t(c)))
            if any(ta < hi and tb > lo for lo, hi
                   in ocupados.get(nombre_lado, ())):
                continue   # el lado ya tiene un corte que solapa
            ocupados.setdefault(nombre_lado, []).append((ta, tb))
            # el sentido de RECORRIDO de la sala (CCW desde la
            # esquina inferior izquierda): sur 0->1, este 1->2,
            # norte 2->3 (va hacia la izquierda), oeste 3->0 (baja)
            sentido = {"sur": 1.0, "este": 1.0, "norte": -1.0,
                       "oeste": -1.0}[nombre_lado]
            primero, segundo = ((a_prima, c) if (_t(a_prima) - _t(c))
                                * sentido <= 0 else (c, a_prima))
            cortes.setdefault(nombre_lado, []).append(
                (_t(primero), _t(segundo), primero, b_prima, segundo))
            esq_sala = [(sx0, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1)]
            nueva: List[Tuple[float, float]] = []
            for i in range(4):
                nombre_i = ("sur", "este", "norte", "oeste")[i]
                sentido_i = {"sur": 1.0, "este": 1.0, "norte": -1.0,
                             "oeste": -1.0}[nombre_i]
                nueva.append(esq_sala[i])
                for t1, t2, p1c, punta, p2c in sorted(
                        cortes.get(nombre_i, ()),
                        key=lambda h: h[0] * sentido_i):
                    nueva.extend([p1c, punta, p2c])
            # sin vértices consecutivos duplicados (un corte que remata
            # exactamente en la esquina del lado la repite)
            limpia: List[Tuple[float, float]] = []
            for p in nueva:
                if limpia and abs(p[0] - limpia[-1][0]) < 1e-6 \
                        and abs(p[1] - limpia[-1][1]) < 1e-6:
                    continue
                limpia.append(p)
            if len(limpia) >= 2 \
                    and abs(limpia[0][0] - limpia[-1][0]) < 1e-6 \
                    and abs(limpia[0][1] - limpia[-1][1]) < 1e-6:
                limpia.pop()
            sala["poligono"] = [(round(p[0], 4), round(p[1], 4))
                                for p in limpia]
            sala["area_m2"] = round(float(sala["area_m2"]) + perdida, 2)
            hechos.append({
                "nivel": geo.get("nivel", len(hechos) + 1),
                "local": local["nombre"], "sala": sala["nombre"],
                "cateto_m": round(cateto, 2),
                "perdida_m2": round(perdida, 2),
                "esquina": [round(c[0], 2), round(c[1], 2)]})
    if hechos:
        total = round(sum(h["perdida_m2"] for h in hechos), 2)
        propios = [h for h in hechos if h.get("tipo") == "propio"]
        hacia = len(hechos) - len(propios)
        texto = (f"chaflanes a 45 grados (v3.43): {hacia} esquina(s) "
                 f"abierta(s) hacia la sala")
        if propios:
            texto += (f" y {len(propios)} corte(s) propio(s) de "
                      "fachada (v3.44, bay window)")
        avisos.append(texto + f" ({total:.2f} m2 de recirculación "
                      "ganada), como en el dibujo de referencia")
    return hechos


def _ajustar_estricto(programa: Dict[str, Any], forma: Dict[str, Any],
                      altura: float, margen: float, patio_a: float,
                      caja_esc: Dict[str, Any], avisos: List[str],
                      niveles_max: int = NIVELES_MAX,
                      sala_distribuidora: bool = False,
                      chaflanes: bool = False,
                      chaflan_propio: Optional[bool] = None) \
        -> Dict[str, Any]:
    """Camino v3.40.0: el empaquetado ocurre DENTRO de los
    contenedores reales del polígono (encaje.py), así que lo generado
    no puede salirse de la parcela y su forma se aprovecha. v3.43.0:
    ``niveles_max`` es un TOPE DURO (ARQ-DDI-011 si el programa
    necesita más), ``sala_distribuidora`` reserva el nivel SIN pasillo
    (la sala reparte el acceso, como en las casas pequeñas) y
    ``chaflanes`` abre esquinas a 45 grados hacia la sala. v3.44.0:
    ``chaflan_propio`` añade el corte propio de fachada (bay
    window)."""
    info = encaje.contenedores_de(forma["vertices"], margen,
                                  ENCAJE_MIN_LADO_M)
    conts = info["contenedores"]
    if not conts:
        raise DomainError(
            message="Ninguna zona del polígono admite locales "
                    "(contenedores vacíos): amplíe el contorno o "
                    "reduzca el margen",
            code="ARQ-DDI-003",
            context={"forma": forma["forma"],
                     "area_m2": forma["area_m2"]},
            suggested_action="Dibuje un contorno con lados de al "
                             "menos "
                             f"{ENCAJE_MIN_LADO_M:.1f} m o reduzca el "
                             "margen experto.")
    avisos.extend(info["avisos"])
    if info["estrategia"] == "descompuesto":
        dims = ", ".join(f"{c['ancho']:.1f}x{c['fondo']:.1f}"
                         for c in conts[:4])
        extra = f" (+{len(conts) - 4} más)" if len(conts) > 4 else ""
        avisos.append(
            "encaje estricto: la parcela se tesela en "
            f"{len(conts)} contenedor(es) ({dims} m{extra}); "
            "todo lo generado queda dentro del polígono y su forma "
            "se aprovecha")
    for r in programa["renglones"]:
        if _es_hall(r):
            # los recintos-nave se ADAPTAN al contenedor mayor
            # (_hall_dims los dimensiona al espacio disponible)
            continue
        if _encaje_imposible(r, conts) \
                and _compuesto_de(r, conts,
                                  forma["vertices"]) is None:
            max_c = max(conts, key=lambda c: c["area"])
            raise DomainError(
                message=f"El local {r['nombre']} ({_peso(r):.2f} x "
                        f"{float(r['fondo_m']):.2f} m) no cabe en "
                        "ningún contenedor del polígono ni en la "
                        "unión de dos contiguos (el mayor mide "
                        f"{max_c['ancho']:.2f} x {max_c['fondo']:.2f} m)",
                code="ARQ-DDI-003",
                context={"local": r["nombre"], "ancho_m": _peso(r),
                         "fondo_m": float(r["fondo_m"])},
                suggested_action="Amplíe el contorno dibujado, reduzca "
                                 "el área de ese local o divídalo en "
                                 "dos usos.")
    if patio_a > 0.0 and float(conts[0]["ancho"]) \
            <= patio_a + PASILLO_ANCHO + 1.0:
        avisos.append(f"el contorno es demasiado estrecho para el "
                      f"patio de {patio_a:.2f} m: la opción se ignora "
                      "en este ajuste")
        patio_a = 0.0

    def reparte(con_escalera: bool) -> List[Dict[str, Any]]:
        # v3.42.0: el orden de colocación sigue el flujo del servicio
        # (sucio al fondo, filtro como barrera, público en la entrada)
        pend = _orden_flujo(list(programa["renglones"]))
        # el IDEAL de cada local se sella ANTES de tocar nada: el
        # teselado y la adaptación crecen locales y el informe necesita
        # el área original del programa para medir el crecimiento
        for r in pend:
            r.setdefault("area_ideal",
                         round(float(r.get("area_m2") or 0.0), 2))
        crudos: List[Dict[str, Any]] = []
        for idx in range(NIVELES_MAX):
            if not pend:
                break
            if sala_distribuidora:
                # v3.43.0: modo SALA DISTRIBUIDORA — sin pasillo
                # SIEMPRE (la sala reparte el acceso entre locales,
                # como en las casas de 25-60 m2 de los planos de
                # referencia)
                geo, resto = _arma_nivel(pend, conts, con_escalera,
                                         caja_esc, patio_a,
                                         sin_pasillo=True,
                                         poligono=forma["vertices"])
                if geo.get("aviso_patio"):
                    avisos.append(geo.pop("aviso_patio"))
            else:
                geo, resto = _arma_nivel(pend, conts, con_escalera,
                                         caja_esc, patio_a,
                                         poligono=forma["vertices"])
                bandas = len(geo["bandas"]["norte"]) \
                    + len(geo["bandas"]["sur"])
                if (not geo["bandas"]["norte"] and not geo["bandas"]["sur"]
                        and (geo["satelites"] or resto)) or bandas <= 1:
                    # el pasillo no sirve casi a nadie en este nivel
                    # (locales más profundos que pasillo + fondo del
                    # contenedor, o nivel de cola con 1 local en banda):
                    # se reempaqueta SIN pasillo; gana si tesela mejor
                    # (o igual cuando el pasillo no sirve a NADIE); si el
                    # ensayo sin pasillo se descarta, el intento con
                    # pasillo se REPITE para restaurar sus rects (los
                    # ensayos escriben sobre los mismos renglones)
                    geo2, resto2 = _arma_nivel(pend, conts, con_escalera,
                                               caja_esc, patio_a,
                                               sin_pasillo=True,
                                               poligono=forma["vertices"])
                    if geo2.get("aviso_patio"):
                        avisos.append(geo2.pop("aviso_patio"))
                    gana_sin = (len(geo2["locales"]) > len(geo["locales"])
                                or (bandas == 0 and len(geo2["locales"])
                                    >= len(geo["locales"])))
                    if gana_sin:
                        geo, resto = geo2, resto2
                    else:
                        geo, resto = _arma_nivel(pend, conts, con_escalera,
                                                 caja_esc, patio_a,
                                                 poligono=forma["vertices"])
            if not geo["locales"]:
                detalle = ("con la escalera reservada, ningún local "
                           "cabe en los contenedores del nivel"
                           if con_escalera else
                           "ningún local cabe en los contenedores "
                           "conectados del nivel")
                raise DomainError(
                    message=f"{detalle}: el programa no cabe en este "
                            "contorno",
                    code="ARQ-DDI-003",
                    suggested_action="Amplíe el contorno, reduzca el "
                                     "programa o baje la altura de "
                                     "piso para una escalera menor.")
            crudos.append(geo)
            pend = resto
            # v3.43.0: TOPE DURO de niveles — si el nivel que acaba de
            # cerrarse es el último permitido y queda programa, no se
            # sigue creciendo en altura: ARQ-DDI-011 (la escalera de
            # reducción lo captura en ``ajustar``)
            if resto and (idx + 1) >= max(1, int(niveles_max)):
                nombres = ", ".join(str(r.get("nombre", "?"))
                                     for r in resto[:6])
                raise DomainError(
                    message=f"El programa no cabe en "
                            f"{int(niveles_max)} nivel(es): quedan "
                            f"{len(resto)} local(es) fuera del tope "
                            f"pedido ({nombres})",
                    code="ARQ-DDI-011",
                    context={"niveles_pedidos": int(niveles_max),
                             "pendientes": len(resto)},
                    suggested_action="Permita más niveles (pida «2 "
                                     "niveles» en la especificación o "
                                     "«niveles deseados» del marco "
                                     "experto), excluya locales con «"
                                     "Locales del programa» o acepte un "
                                     "ajuste más agresivo.")
        if pend:
            raise DomainError(
                message=f"El programa necesita más de {NIVELES_MAX} "
                        "niveles sobre este contorno",
                code="ARQ-DDI-003",
                context={"pendientes": len(pend)},
                suggested_action="Reduzca el programa o amplíe el "
                                 "contorno del área.")
        return crudos

    crudos = reparte(False)
    con_escalera = len(crudos) >= 2
    if con_escalera:
        for _ in range(6):
            crudos = reparte(True)
            if len(crudos) == con_escalera or len(crudos) > NIVELES_MAX:
                break
            con_escalera = len(crudos)
    if len(crudos) > NIVELES_MAX:
        raise DomainError(
            message=f"El programa necesita {len(crudos)} niveles: "
                    "supera el techo del crecimiento en altura",
            code="ARQ-DDI-003",
            context={"niveles": len(crudos)},
            suggested_action="Reduzca el programa o amplíe el "
                             "contorno del área.")

    reparto: List[Dict[str, Any]] = []
    dentro_total = True
    area_disp = round(sum(float(c["area"]) for c in conts), 2)
    if any(not g.get("pasillo") for g in crudos):
        if sala_distribuidora:
            avisos.append(
                "modo SALA DISTRIBUIDORA (v3.43): sin pasillo de "
                "distribución; la sala reparte el acceso entre "
                "locales, como en las casas de los planos de "
                "referencia")
        else:
            avisos.append(
                "hay nivel(es) sin pasillo de distribución (locales más "
                "profundos que pasillo + fondo del contenedor): el acceso "
                "es entre locales y el área del contorno se aprovecha "
                "completa")
    for i, geo in enumerate(crudos, start=1):
        piezas = ([geo["pasillo"]] if geo.get("pasillo") else []) \
            + geo["locales"] \
            + ([geo["escalera"]] if geo["escalera"] else []) \
            + ([geo["patio"]] if geo.get("patio") else [])
        dentro = True
        for pieza in piezas:
            # validación SIEMPRE contra el polígono real (no la caja)
            if not rect_dentro([tuple(p) for p in pieza["rect"]],
                               forma["vertices"]):
                dentro = False
        if not dentro:
            dentro_total = False
        reparto.append({
            "nivel": i, "pasillo": geo["pasillo"],
            "escalera": geo["escalera"], "locales": geo["locales"],
            "patio": geo.get("patio"),
            "area_ocupada": geo["area_ocupada"],
            "area_disponible": area_disp,
            "dentro": dentro,
            "contenedores_usados": sorted(
                {int(r.get("contenedor", 0)) for r in geo["locales"]})})
    crude = [{"norte": g["bandas"]["norte"], "sur": g["bandas"]["sur"],
              "satelites": g["satelites"]} for g in crudos]
    # v3.43.0: CHAFLANES A 45 GRADOS hacia la sala (opción de
    # vivienda social; los cortes quedan documentados y las áreas
    # ajustadas antes de las métricas)
    chaflanes_hechos: List[Dict[str, Any]] = []
    if chaflanes:
        chaflanes_hechos = _chaflanes_vivienda(
            crudos, avisos, vertices_contorno=forma["vertices"],
            propio=chaflan_propio)

    env0 = {"ancho_util": float(conts[0]["ancho"]),
            "fondo_util": float(conts[0]["fondo"])}
    total_prog = float(programa["totales"]["area_m2"])
    area_pas = round(sum(n["pasillo"]["area_m2"]
                         for n in reparto if n.get("pasillo")), 2)
    area_esc = round(sum(n["escalera"]["area_m2"] for n in reparto
                         if n["escalera"]), 2)
    area_pat = round(sum(n["patio"]["area_m2"] for n in reparto
                         if n.get("patio")), 2)
    construida = round(sum(float(n["area_ocupada"]) for n in reparto), 2)
    # v3.42.0: CIRCULACIÓN Y FILTROS + TESELADO COMPLETO en el análisis
    circulacion = _circulacion_de(reparto)
    avisos.extend(_avisos_filtros(reparto, circulacion))
    teselado = _teselado_de(reparto)
    if teselado.get("area_ganada", 0.0) > 0.01:
        avisos.append(
            "teselado completo: "
            f"{teselado['locales_crecidos']} local(es) crecen "
            f"{teselado['area_ganada']:.2f} m2 en total para aprovechar "
            "los contenedores hasta sus bordes")
    analisis = {
        "forma": forma, "programa": programa,
        "niveles": len(reparto), "cabe_un_nivel": len(reparto) == 1,
        "con_escalera": con_escalera,
        "escalera": dict(caja_esc, descripcion=(
            f"recinto reservado {caja_esc['ancho_m']:.2f} x "
            f"{caja_esc['fondo_m']:.2f} m por nivel ({caja_esc['planta']}"
            f", contrahuella {caja_esc['dimensionar']['contrahuella_m']:.3f}"
            f" m, huella {caja_esc['dimensionar']['huella_m']:.3f} m, "
            f"Blondel {caja_esc['dimensionar']['blondel_m']:.2f} m): "
            "genere la escalera con el asistente de Escaleras dentro "
            "del recinto")) if con_escalera else None,
        "patio": ({"ancho_m": round(patio_a, 2),
                   "fondo_m": round(float(conts[0]["fondo"]), 2),
                   "area_m2": area_pat}
                  if patio_a > 0.0 else None),
        "reparto": reparto, "dentro_del_contorno": dentro_total,
        "circulacion": circulacion, "teselado": teselado,
        "sala_distribuidora": bool(sala_distribuidora),
        "chaflanes": chaflanes_hechos,
        "tope_niveles": (int(niveles_max)
                         if int(niveles_max) < NIVELES_MAX else None),
        "encaje": {
            "estrategia": info["estrategia"],
            "contenedores": [{"ancho_m": float(c["ancho"]),
                              "fondo_m": float(c["fondo"]),
                              "area_m2": float(c["area"]),
                              "x0": float(c["x0"]), "y0": float(c["y0"]),
                              "x1": float(c["x1"]), "y1": float(c["y1"])}
                             for c in conts],
            "area_aprovechable": info["area_aprovechable"]},
        "altura_nivel_m": altura,
        "decisiones": _decisiones_de(reparto, crude, programa, env0,
                                     con_escalera, caja_esc, altura,
                                     patio_a),
        "totales": {
            "area_programa": total_prog,
            "area_pasillos": area_pas, "area_escaleras": area_esc,
            "area_patio": area_pat,
            "area_contorno": forma["area_m2"],
            "area_aprovechada": construida,
            "aprovechamiento_pct": round(
                construida / (forma["area_m2"] * max(1, len(reparto)))
                * 100.0, 2) if forma["area_m2"] > 1e-9 else 0.0,
            "altura_total": round(len(reparto) * altura, 2)},
        "avisos": avisos}
    return analisis


# ---------------------------------------------------------------------------
# 7-bis) v3.41.0: PROGRAMA ADAPTABLE — selección de locales y ajuste
#        dimensional por niveles (mínimo / medio / estricto)
# ---------------------------------------------------------------------------

def programa_filtrado(programa: Dict[str, Any],
                      seleccion: Optional[List[str]]) -> Dict[str, Any]:
    """Deja en el programa SOLO los locales elegidos: ``seleccion``
    es la lista de CÓDIGOS a conservar (todas las copias de un
    código entran o salen juntas). ``None`` = el programa completo
    (comportamiento histórico). Cada local excluido sale en los
    avisos: la decisión queda documentada, sin IA. Lanza
    ARQ-DDI-009 si la selección no conserva ningún local."""
    if seleccion is None:
        return programa
    sel = {str(s).strip().upper() for s in seleccion if str(s).strip()}
    if not sel:
        raise DomainError(
            message="La selección de locales está vacía: no queda "
                    "ningún local para el proyecto",
            code="ARQ-DDI-009",
            context={"seleccion": 0},
            suggested_action="Marque al menos un local en «Locales "
                             "del programa» o limpie la selección "
                             "para aplicarlos todos.")
    renglones = _limpia_colocacion(
        [dict(r) for r in programa.get("renglones", [])
         if str(r.get("codigo", "")).strip().upper() in sel])
    if not renglones:
        raise DomainError(
            message="Ningún código de la selección existe en el "
                    "programa elegido",
            code="ARQ-DDI-009",
            context={"seleccion": len(sel)},
            suggested_action="Revise los códigos en «Locales del "
                             "programa»: se muestran tal cual el "
                             "catálogo o el DNA los define.")
    excluidos = [str(r.get("nombre", r.get("codigo", "?")))
                 for r in programa.get("renglones", [])
                 if str(r.get("codigo", "")).strip().upper() not in sel]
    salida = dict(programa)
    salida["renglones"] = renglones
    tot = dict(programa.get("totales") or {})
    tot["locales"] = len(renglones)
    tot["area_m2"] = round(sum(float(r["area_m2"]) for r in renglones), 2)
    if "grupos" in tot:
        grupos: Dict[str, Dict[str, Any]] = {}
        for r in renglones:
            g = r.get("grupo", "") or "General"
            slot = grupos.setdefault(g, {"locales": 0, "area_m2": 0.0})
            slot["locales"] += 1
            slot["area_m2"] = round(slot["area_m2"] + r["area_m2"], 2)
        tot["grupos"] = grupos
    salida["totales"] = tot
    avisos = list(programa.get("avisos") or [])
    cola = ", ".join(excluidos[:6]) \
        + (f" y {len(excluidos) - 6} más" if len(excluidos) > 6 else "")
    avisos.append("selección de locales: se excluyen "
                  f"{len(excluidos)} local(es) del programa ({cola})")
    salida["avisos"] = avisos
    if programa.get("servicio"):
        from domain.servicios_engine import validar_programa
        salida["validacion"] = validar_programa(salida)
    salida["seleccion"] = sorted(sel)
    return salida


def _dimensiones_ajuste(area: float, lado_min: float = 2.0) \
        -> Tuple[float, float]:
    """Dimensiones de un local REDUCIDO: la misma proporción de
    trabajo v3.33 pero con los pisos de lado del nivel de ajuste
    (el estricto admite lados de 1,50 m: se trabaja con lo que se
    tiene)."""
    area = max(0.0, float(area or 0.0))
    ancho = max(lado_min, min(math.sqrt(max(area, 1.0) / PROPORCION_DEF),
                              ANCHO_MAX))
    fondo = max(lado_min, min(area / ancho, FONDO_MAX))
    if fondo >= FONDO_MAX and area / fondo > ANCHO_MAX:
        ancho = ANCHO_MAX
    else:
        ancho = max(ancho, area / FONDO_MAX)
    return round(ancho, 2), round(fondo, 2)


def _piso_de(r: Dict[str, Any], cfg: Dict[str, float]) -> float:
    """Área mínima admisible del local en el nivel de ajuste: la
    norma (area_min del catálogo o del DNA) rebajada según el nivel
    (100/85/65 %); sin norma, la misma rebaja sobre el área ideal.
    Nunca por encima del área ideal (reducir no puede crecer)."""
    ideal = float(r.get("area_ideal") or r.get("area_m2") or 0.0)
    norma = float(r.get("area_min") or 0.0)
    base = norma if norma > 0.0 else ideal
    if cfg["bajo_norma"] >= 1.0:
        piso = base
    else:
        piso = max(base * cfg["bajo_norma"], cfg["piso_abs"])
    return min(ideal, piso) if ideal > 0.0 else piso


CLAVES_COLOCACION = ("hall_ancho", "hall_fondo", "rect", "contenedor",
                     "crecido_m2")


def _limpia_colocacion(renglones: List[Dict[str, Any]]) \
        -> List[Dict[str, Any]]:
    """Copias de renglones SIN los datos de una colocación anterior
    (hall_ancho/hall_fondo/rect/contenedor): los empaquetados deben
    partir de las dimensiones del programa, no de las de un nivel ya
    armado (v3.42.0: el pasillo adaptado escribe en el renglón)."""
    salida: List[Dict[str, Any]] = []
    for r in renglones:
        nuevo = dict(r)
        for k in CLAVES_COLOCACION:
            nuevo.pop(k, None)
        salida.append(nuevo)
    return salida


def _escala_programa(programa: Dict[str, Any], f: float,
                     cfg: Dict[str, float]) \
        -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Copia del programa con las áreas reducidas al factor ``f``
    (0..1) respetando el piso del nivel; las dimensiones se
    recalculan con _dimensiones_ajuste. Devuelve (programa, registro
    de reducciones local a local). Los recintos-nave no se reducen:
    se adaptan solos al contenedor."""
    renglones: List[Dict[str, Any]] = []
    registro: List[Dict[str, Any]] = []
    for r in programa.get("renglones", []):
        if _es_hall(r):
            renglones.append(_limpia_colocacion([r])[0])
            continue
        r = _limpia_colocacion([r])[0]
        ideal = float(r.get("area_ideal") or r.get("area_m2") or 0.0)
        norma = float(r.get("area_min") or 0.0)
        area = min(ideal, max(ideal * f, _piso_de(r, cfg)))
        ancho, fondo = _dimensiones_ajuste(area, cfg["lado_min"])
        nuevo = dict(r, area_m2=round(area, 2), ancho_m=ancho,
                     fondo_m=fondo, area_ideal=round(ideal, 2))
        renglones.append(nuevo)
        if area < ideal - 1e-9:
            registro.append({
                "codigo": str(r.get("codigo", "")),
                "nombre": str(r.get("nombre", "")),
                "area_ideal": round(ideal, 2),
                "area_final": round(area, 2),
                "reduccion_pct": round(
                    (1.0 - area / ideal) * 100.0, 1)
                if ideal > 1e-9 else 0.0,
                "bajo_norma": bool(norma > 0.0 and area < norma - 1e-9)})
    salida = dict(programa)
    salida["renglones"] = renglones
    tot = dict(programa.get("totales") or {})
    tot["locales"] = len(renglones)
    tot["area_m2"] = round(sum(float(r["area_m2"])
                               for r in renglones), 2)
    if "grupos" in tot:
        grupos = {}
        for r in renglones:
            g = r.get("grupo", "") or "General"
            slot = grupos.setdefault(g, {"locales": 0, "area_m2": 0.0})
            slot["locales"] += 1
            slot["area_m2"] = round(slot["area_m2"] + r["area_m2"], 2)
        tot["grupos"] = grupos
    salida["totales"] = tot
    if programa.get("servicio"):
        from domain.servicios_engine import validar_programa
        salida["validacion"] = validar_programa(salida)
    return salida, registro


def _registro_ajuste(nivel: str, registro: List[Dict[str, Any]],
                     base: Dict[str, Any],
                     escalado: Dict[str, Any]) -> Dict[str, Any]:
    """El bloque ``ajuste_programa`` del análisis: nivel usado,
    reducciones local a local y los que quedaron BAJO la norma."""
    return {"nivel": nivel, "reducidos": registro,
            "bajo_norma": [x["nombre"] for x in registro
                           if x["bajo_norma"]],
            "area_ideal_total": round(
                float(base["totales"]["area_m2"]), 2),
            "area_final_total": round(
                float(escalado["totales"]["area_m2"]), 2)}


def _compactar_niveles(programa: Dict[str, Any], contorno: List[PT],
                       cfg: Dict[str, float], nivel: str,
                       niveles_base: int, altura_nivel_m: float,
                       margen_m: float, patio: bool,
                       patio_ancho_m: float, encaje_estricto: bool,
                       niveles_max: int = NIVELES_MAX,
                       sala_distribuidora: bool = False,
                       chaflanes: bool = False,
                       chaflan_propio: Optional[bool] = None) \
        -> Optional[Dict[str, Any]]:
    """v3.42.0: con el programa ya dentro (en ``niveles_base`` niveles
    o más), prueba la escalera de reducción (0.95, 0.90, ... hasta los
    pisos del nivel) buscando MENOS NIVELES, encadenando mientras
    consigua bajar (3 -> 2 -> 1). Devuelve el MEJOR análisis compactado
    con su ``ajuste_programa`` o None si ningún factor lo consigue
    (se conserva el ajuste sin compactar). v3.43.0: el tope de
    niveles y el modo distribuidor viajan al empaquetado."""
    objetivo = niveles_base
    mejor: Optional[Dict[str, Any]] = None
    while objetivo >= 2:
        logrado: Optional[Dict[str, Any]] = None
        previo: Optional[List[float]] = None
        for paso in range(1, 16):
            factor = round(1.0 - 0.05 * paso, 2)
            escalado, registro = _escala_programa(programa, factor, cfg)
            areas = [float(r["area_m2"]) for r in escalado["renglones"]]
            if previo is not None and areas == previo:
                break   # locales ya en su piso: no hay más juego
            previo = areas
            try:
                analisis = _ajustar_base(escalado, contorno,
                                         altura_nivel_m, margen_m,
                                         patio, patio_ancho_m,
                                         encaje_estricto,
                                         niveles_max=niveles_max,
                                         sala_distribuidora=
                                         sala_distribuidora,
                                         chaflanes=chaflanes,
                                         chaflan_propio=
                                         chaflan_propio)
            except DomainError as exc:
                if getattr(exc, "code", "") not in ("ARQ-DDI-003",
                                                    "ARQ-DDI-011"):
                    raise
                continue
            if int(analisis.get("niveles", objetivo)) < objetivo \
                    and analisis.get("dentro_del_contorno"):
                # la compactación solo acepta empaquetados que quedan
                # DENTRO del polígono (un nivel menos no vale una
                # geometría fuera del contorno)
                analisis["ajuste_programa"] = _registro_ajuste(
                    nivel, registro, programa, escalado)
                logrado = analisis
                break
        if logrado is None:
            break
        logrado.setdefault("avisos", []).append(
            f"ajuste {nivel}: el programa se compacta a "
            f"{logrado['niveles']} nivel(es) reduciendo dimensiones "
            "(decisión documentada local a local en AJUSTE "
            "DIMENSIONAL)")
        mejor = logrado
        objetivo = int(logrado["niveles"])
    return mejor


def ajustar(programa: Dict[str, Any], contorno: List[PT],
            altura_nivel_m: float = 3.0, margen_m: float = 0.0,
            patio: bool = False, patio_ancho_m: float = 3.0,
            encaje_estricto: bool = True,
            seleccion: Optional[List[str]] = None,
            ajuste: str = "ideal",
            niveles_deseados: Optional[int] = None,
            chaflanes: Optional[bool] = None,
            distribuidora_max_m2: Optional[float] = None,
            chaflan_propio: Optional[bool] = None) -> Dict[str, Any]:
    """El corazón del asistente: dado el programa y el contorno
    dibujado decide si entra en un nivel, y si no, en cuántos (con
    el recinto de la escalera por nivel). Nunca toca el proyecto.

    v3.41.0 — PROGRAMA ADAPTABLE:
      * ``seleccion``: códigos de locales a conservar (None = todos;
        [] lanza ARQ-DDI-009). Los excluidos salen en los avisos.
      * ``ajuste``: ideal | minimo | medio | estricto. Con un nivel
        distinto de ideal, si el programa NO entra tal cual se
        aplica una escalera de reducción (0.95, 0.90, ...) hasta el
        piso admisible del nivel; el primer empaquetado que entre
        gana y el análisis lleva ``ajuste_programa`` con la
        reducción local a local y los locales BAJO la norma. Si ni
        el nivel máximo entra, lanza ARQ-DDI-010.

    v3.43.0 — VIVIENDA SOCIAL:
      * ``niveles_deseados`` es un TOPE DURO: con «1 nivel» el
        empaquetado COMPACTA (escalera de reducción v3.41) antes de
        crecer y nunca pasa del tope (ARQ-DDI-011 si ni así); con un
        ajuste ideal el tope autoriza la cadena mínimo -> medio ->
        estricto, documentada. Un programa de vivienda (lleva
        dormitorios) se topa a 1 nivel POR DEFECTO (pida «2 niveles»
        para crecer).
      * vivienda de <= 60 m2: MODO SALA DISTRIBUIDORA — sin pasillo,
        la sala reparte el acceso (como en los planos de referencia).
      * ``chaflanes`` (None = auto en vivienda): esquinas a 45 grados
        hacia la sala con su pérdida documentada."""
    nivel = str(ajuste or "ideal").strip().lower()
    if nivel not in AJUSTE_NIVELES:
        raise DomainError(
            message=f"Nivel de ajuste desconocido: {ajuste!r}",
            code="ARQ-DDI-009",
            context={"ajuste": str(ajuste)},
            suggested_action="Use ideal, mínimo, medio o estricto.")
    prog = programa_filtrado(programa, seleccion)
    # v3.42.0: el ajuste es AUTOCONTENIDO — parte SIEMPRE de las
    # dimensiones del programa (una colocación anterior puede haber
    # escrito hall/rect en los renglones; el empaquetado nuevo manda)
    prog = dict(prog, renglones=_limpia_colocacion(prog["renglones"]))

    # v3.43.0: tope de niveles, sala distribuidora y chaflanes
    cap: Optional[int] = None
    try:
        bruto = int(niveles_deseados) if niveles_deseados is not None \
            else None
        if bruto is not None and bruto >= 1:
            cap = bruto
    except (TypeError, ValueError):
        cap = None
    if cap is None:
        # el deseo de la especificación rápida («..., 2 niveles»)
        # también manda cuando la llamada no trae el parámetro
        deseo = (prog.get("quick") or {}).get("niveles_deseados")
        try:
            bruto = int(deseo) if deseo is not None else None
            if bruto is not None and bruto >= 1:
                cap = bruto
        except (TypeError, ValueError):
            cap = None
    vivienda = _es_vivienda(prog)
    tope_automatico = False
    if cap is None and vivienda:
        cap = TOPE_VIVIENDA_NIVELES
        tope_automatico = True
    # v3.43.0: el modo sala distribuidora se decide por el TAMAÑO DE
    # LA CASA (el contorno), no por el área ideal del programa (los
    # ideales del DNA inflan una casa pequeña): vivienda <= 60 m2.
    # v3.44.0: el umbral es PARAMETRIZABLE (distribuidora_max_m2):
    # villas grandes con LOBBY distribuidor piden el modo sin pasillo
    try:
        area_casa = float(inferir(contorno).get("area_m2", 0.0) or 0.0)
    except DomainError:
        area_casa = 0.0
    tope_dist = (float(distribuidora_max_m2)
                 if distribuidora_max_m2 is not None
                 and float(distribuidora_max_m2) > 0.0
                 else SALA_DISTRIBUIDORA_MAX_M2)
    distribuidora = bool(vivienda and cap is not None
                         and 0.0 < area_casa <= tope_dist)
    chafl = bool(vivienda) if chaflanes is None else bool(chaflanes)
    pre: List[str] = []
    if vivienda and cap is not None and tope_automatico:
        pre.append(
            f"programa de vivienda (v3.43): tope de {cap} nivel(es) "
            "por defecto; pida «2 niveles» en la especificación si "
            "quiere crecer en altura")
    elif cap is not None:
        pre.append(f"tope de niveles pedido: {cap} (v3.43, tope duro: "
                   "se compacta antes de crecer)")
    if distribuidora:
        pre.append(f"vivienda de {tope_dist:.0f} m2 o menos: MODO SALA "
                   "DISTRIBUIDORA (sin pasillo; la sala o el lobby "
                   "reparte el acceso)")
    if chafl and vivienda:
        pre.append("chaflanes a 45 grados hacia la sala activados "
                   "(v3.43)")
    if chafl and chaflan_propio:
        pre.append("chaflán propio de fachada (bay window, v3.44): "
                   "las esquinas de los locales que caen en el "
                   "contorno se cortan a 45 grados")
    if pre:
        prog = dict(prog, avisos=list(prog.get("avisos", [])) + pre)

    if nivel == "ideal" and cap is None:
        # comportamiento histórico intacto (sin tope no hay cadena)
        return _ajustar_base(prog, contorno, altura_nivel_m, margen_m,
                             patio, patio_ancho_m, encaje_estricto,
                             chaflanes=chafl)

    cadena: Tuple[str, ...] = ("ideal", "minimo", "medio", "estricto") \
        if nivel == "ideal" else (nivel,)
    ultimo: Optional[DomainError] = None
    for etapa in cadena:
        cfg = AJUSTE_CONFIG.get(etapa)
        try:
            analisis = _ajustar_base(prog, contorno, altura_nivel_m,
                                     margen_m, patio, patio_ancho_m,
                                     encaje_estricto, niveles_max=cap
                                     if cap is not None else NIVELES_MAX,
                                     sala_distribuidora=distribuidora,
                                     chaflanes=chafl,
                                     chaflan_propio=chaflan_propio)
        except DomainError as exc:
            if getattr(exc, "code", "") not in ("ARQ-DDI-003",
                                                "ARQ-DDI-011"):
                raise
            ultimo = exc
        else:
            if cap is not None \
                    and int(analisis.get("niveles", 1)) > cap:
                # camino histórico (sin 011): el tope se verifica aquí
                ultimo = DomainError(
                    message=f"El programa necesita "
                            f"{analisis.get('niveles')} niveles y el "
                            f"tope pedido es {cap}",
                    code="ARQ-DDI-011",
                    context={"niveles_pedidos": cap},
                    suggested_action="Permita más niveles, excluya "
                                     "locales o acepte un ajuste más "
                                     "agresivo.")
            else:
                # v3.42.0: COMPACTACIÓN — el servicio pequeño (y ahora
                # la vivienda con tope) prefiere MENOS NIVELES a
                # cuartos de más
                if int(analisis.get("niveles", 1)) >= 2:
                    compacto = _compactar_niveles(
                        prog, contorno, cfg, etapa,
                        int(analisis["niveles"]), altura_nivel_m,
                        margen_m, patio, patio_ancho_m, encaje_estricto,
                        niveles_max=cap if cap is not None
                        else NIVELES_MAX,
                        sala_distribuidora=distribuidora,
                        chaflanes=chafl,
                        chaflan_propio=chaflan_propio)
                    if compacto is not None:
                        return compacto
                return analisis
        # escalera de reducción con el piso de esta etapa (ideal no
        # tiene piso: su intento «tal cual» ya corrió y se pasa a la
        # etapa siguiente de la cadena)
        if cfg is None:
            continue
        previo: Optional[List[float]] = None
        for paso in range(1, 16):
            factor = round(1.0 - 0.05 * paso, 2)
            escalado, registro = _escala_programa(prog, factor, cfg)
            areas = [float(r["area_m2"]) for r in escalado["renglones"]]
            if previo is not None and areas == previo:
                break   # todos los locales ya en su piso: no hay más
            previo = areas
            try:
                analisis = _ajustar_base(escalado, contorno,
                                         altura_nivel_m, margen_m,
                                         patio, patio_ancho_m,
                                         encaje_estricto,
                                         niveles_max=cap if cap is not None
                                         else NIVELES_MAX,
                                         sala_distribuidora=distribuidora,
                                         chaflanes=chafl,
                                         chaflan_propio=chaflan_propio)
            except DomainError as exc2:
                if getattr(exc2, "code", "") not in ("ARQ-DDI-003",
                                                     "ARQ-DDI-011"):
                    raise
                ultimo = exc2
                continue
            analisis["ajuste_programa"] = _registro_ajuste(
                etapa, registro, prog, escalado)
            return analisis
    if ultimo is not None and getattr(ultimo, "code", "") \
            == "ARQ-DDI-011" and cap is not None:
        ultimo.suggested_action = \
            "Permita más niveles (pida «2 niveles» en la especificación), " \
            "excluya locales con «Locales del programa» o amplíe el " \
            "contorno dibujado."
        raise ultimo
    raise DomainError(
        message=f"El programa no entra en el contorno NI con el ajuste "
                f"{nivel.upper()} (los locales ya están en los mínimos "
                f"admisibles de ese nivel): "
                f"{getattr(ultimo, 'message', '')}",
        code="ARQ-DDI-010",
        context={"ajuste": nivel},
        suggested_action="Excluya locales con «Locales del programa» "
                         "(selección), amplíe el contorno dibujado o "
                         "acepte un programa con menos locales.")


def _ajustar_base(programa: Dict[str, Any], contorno: List[PT],
                  altura_nivel_m: float = 3.0, margen_m: float = 0.0,
                  patio: bool = False, patio_ancho_m: float = 3.0,
                  encaje_estricto: bool = True,
                  niveles_max: int = NIVELES_MAX,
                  sala_distribuidora: bool = False,
                  chaflanes: bool = False,
                  chaflan_propio: Optional[bool] = None) \
        -> Dict[str, Any]:
    """El empaquetado clásico (v3.34-v3.40), llamado por ``ajustar``
    tras la selección de locales y la escalera de reducción:
    decide si el programa entra en un nivel y cuántos necesita.
    v3.43.0: el tope de niveles, el modo sala distribuidora y los
    chaflanes solo se implantan en el encaje estricto (el camino
    recomendado); en el histórico el tope se verifica al final."""
    forma = inferir(contorno)
    altura = max(2.0, float(altura_nivel_m or 3.0))
    margen = max(0.0, float(margen_m or 0.0))
    avisos = list(programa.get("avisos", []))
    patio_a = max(0.0, float(patio_ancho_m or 0.0)) if patio else 0.0
    caja_esc = caja_escalera(altura)
    if encaje_estricto:
        return _ajustar_estricto(programa, forma, altura, margen,
                                 patio_a, caja_esc, avisos,
                                 niveles_max=niveles_max,
                                 sala_distribuidora=sala_distribuidora,
                                 chaflanes=chaflanes,
                                 chaflan_propio=chaflan_propio)
    x0, y0, x1, y1 = forma["bbox"]
    envolvente = {
        "x0": x0 + margen, "y0": y0 + margen,
        "ancho_util": max(0.0, (x1 - x0) - 2 * margen),
        "fondo_util": max(0.0, (y1 - y0) - 2 * margen)}
    if patio_a > 0.0 and envolvente["ancho_util"] \
            <= patio_a + PASILLO_ANCHO + 1.0:
        avisos.append(f"el contorno es demasiado estrecho para el "
                      f"patio de {patio_a:.2f} m: la opción se ignora "
                      "en este ajuste")
        patio_a = 0.0
    if forma["forma"] != "rectangulo":
        avisos.append(
            "el contorno no es un rectángulo: el empaquetado usa su "
            "caja envolvente y luego verifica local a local si cada "
            "uno queda dentro del polígono dibujado (active el encaje "
            "estricto para que nada se salga)")

    # pasada 1: sin escalera; si hace falta crecer, pasadas con ella
    niveles = _asigna_niveles(programa, envolvente, False, caja_esc,
                              patio_a)
    con_escalera = len(niveles) >= 2
    if con_escalera:
        for _ in range(6):
            niveles = _asigna_niveles(programa, envolvente, True,
                                      caja_esc, patio_a)
            if len(niveles) == con_escalera or len(niveles) > NIVELES_MAX:
                break
            con_escalera = len(niveles)
    if len(niveles) > NIVELES_MAX:
        raise DomainError(
            message=f"El programa necesita {len(niveles)} niveles: "
                    "supera el techo del crecimiento en altura",
            code="ARQ-DDI-003",
            context={"niveles": len(niveles)},
            suggested_action="Reduzca el programa o amplíe el "
                             "contorno del área.")

    reparto: List[Dict[str, Any]] = []
    dentro_total = True
    for i, banda in enumerate(niveles, start=1):
        geo = _geometria_nivel(banda["norte"], banda["sur"], envolvente,
                               con_escalera, caja_esc, patio_a)
        dentro = True
        piezas = [geo["pasillo"]] + geo["locales"] \
            + ([geo["escalera"]] if geo["escalera"] else []) \
            + ([geo["patio"]] if geo.get("patio") else [])
        for pieza in piezas:
            if forma["alineado"]:
                bx = forma["bbox"]
                if min(p[0] for p in pieza["rect"]) < bx[0] - 1e-6 \
                        or min(p[1] for p in pieza["rect"]) < bx[1] - 1e-6 \
                        or max(p[0] for p in pieza["rect"]) > bx[2] + 1e-6 \
                        or max(p[1] for p in pieza["rect"]) > bx[3] + 1e-6:
                    dentro = False
            else:
                if not rect_dentro(pieza["rect"], forma["vertices"]):
                    dentro = False
        if not dentro:
            dentro_total = False
        reparto.append({
            "nivel": i, "pasillo": geo["pasillo"],
            "escalera": geo["escalera"], "locales": geo["locales"],
            "patio": geo.get("patio"),
            "area_ocupada": geo["area_ocupada"],
            "area_disponible": round(
                envolvente["ancho_util"] * envolvente["fondo_util"], 2),
            "dentro": dentro})
    if not dentro_total:
        avisos.append(
            "hay locales que quedan fuera del polígono dibujado (la "
            "caja envolvente no coincide con la forma): ajuste el "
            "contorno, amplíe el área o acepte retocar la geometría "
            "con las herramientas CAD")

    total_prog = float(programa["totales"]["area_m2"])
    area_pas = round(sum(n["pasillo"]["area_m2"]
                         for n in reparto if n.get("pasillo")), 2)
    area_esc = round(sum(n["escalera"]["area_m2"] for n in reparto
                         if n["escalera"]), 2)
    area_pat = round(sum(n["patio"]["area_m2"] for n in reparto
                         if n.get("patio")), 2)
    analisis = {
        "forma": forma, "programa": programa,
        "niveles": len(reparto), "cabe_un_nivel": len(reparto) == 1,
        "con_escalera": con_escalera,
        "escalera": dict(caja_esc, descripcion=(
            f"recinto reservado {caja_esc['ancho_m']:.2f} x "
            f"{caja_esc['fondo_m']:.2f} m por nivel ({caja_esc['planta']}"
            f", contrahuella {caja_esc['dimensionar']['contrahuella_m']:.3f}"
            f" m, huella {caja_esc['dimensionar']['huella_m']:.3f} m, "
            f"Blondel {caja_esc['dimensionar']['blondel_m']:.2f} m): "
            "genere la escalera con el asistente de Escaleras dentro "
            "del recinto")) if con_escalera else None,
        "patio": ({"ancho_m": round(patio_a, 2),
                   "fondo_m": round(envolvente["fondo_util"], 2),
                   "area_m2": area_pat}
                  if patio_a > 0.0 else None),
        "reparto": reparto, "dentro_del_contorno": dentro_total,
        "altura_nivel_m": altura,
        "decisiones": _decisiones_de(reparto, niveles, programa,
                                     envolvente, con_escalera, caja_esc,
                                     altura, patio_a),
        "totales": {
            "area_programa": total_prog,
            "area_pasillos": area_pas, "area_escaleras": area_esc,
            "area_patio": area_pat,
            "area_contorno": forma["area_m2"],
            "altura_total": round(len(reparto) * altura, 2)},
        "avisos": avisos}
    return analisis


def _decisiones_de(reparto: List[Dict[str, Any]],
                   niveles: List[Dict[str, List[Dict[str, Any]]]],
                   programa: Dict[str, Any],
                   envolvente: Dict[str, float], con_escalera: bool,
                   caja_esc: Dict[str, Any], altura: float,
                   patio_a: float) -> List[Dict[str, str]]:
    """Registro EXPLICABLE de cada decisión del empaquetado (spec
    §32/§33): por qué N niveles, por qué la escalera, por qué el
    patio y por qué cada local queda en su banda. Sin IA: solo las
    reglas que el asistente acaba de aplicar, en texto cp1252."""
    decisiones: List[Dict[str, str]] = []
    w = float(envolvente["ancho_util"])
    d = float(envolvente["fondo_util"])
    total_prog = float(programa["totales"]["area_m2"])
    # banda de cada local por identidad del renglón (el reparto y las
    # bandas crudas comparten los mismos objetos); v3.40.0 añade los
    # satélites de contenedor
    banda_de: Dict[int, Tuple[str, int]] = {}
    for i, bruto in enumerate(niveles, start=1):
        for r in bruto["norte"]:
            banda_de[id(r)] = ("norte", i)
        for r in bruto["sur"]:
            banda_de[id(r)] = ("sur", i)
        for idx, items in (bruto.get("satelites") or []):
            etiqueta = (f"contenedor {idx + 1}" if idx >= 0
                        else "zona compuesta")
            for r in items:
                banda_de[id(r)] = (etiqueta, i)
    if len(reparto) <= 1:
        decisiones.append({
            "tipo": "niveles", "local": "",
            "texto": f"El programa ({total_prog:.1f} m2) cabe en 1 "
                     f"nivel sobre la caja útil ({w:.2f} x {d:.2f} m): "
                     "no hace falta escalera."})
    else:
        decisiones.append({
            "tipo": "niveles", "local": "",
            "texto": f"El programa ({total_prog:.1f} m2) no cabe en 1 "
                     f"nivel sobre la caja útil ({w:.2f} x {d:.2f} m): "
                     f"se reparte en {len(reparto)} niveles y se "
                     "reserva el recinto de la escalera en cada uno."})
    if con_escalera:
        decisiones.append({
            "tipo": "escalera", "local": "",
            "texto": f"Escalera {float(caja_esc['ancho_m']):.2f} x "
                     f"{float(caja_esc['fondo_m']):.2f} m por nivel "
                     f"({caja_esc['planta']}): dimensionada con "
                     f"Blondel para altura de piso {altura:.2f} m "
                     "(contrahuella "
                     f"{float(caja_esc['dimensionar']['contrahuella_m']):.3f}"
                     " m, huella "
                     f"{float(caja_esc['dimensionar']['huella_m']):.3f}"
                     " m)."})
    if patio_a > 0.0:
        decisiones.append({
            "tipo": "patio", "local": "",
            "texto": f"Patio de {patio_a:.2f} x {d:.2f} m reservado al "
                     "final del pasillo en cada nivel (opción "
                     "experta): se descuenta del ancho disponible "
                     "para locales y aporta luz y ventilación."})
    for plan in reparto:
        for r in plan["locales"]:
            banda, nivel_i = banda_de.get(id(r), ("norte", plan["nivel"]))
            if _es_hall(r):
                texto = (f"Es un recinto-nave ({float(r['area_m2']):.1f}"
                         " m2): ocupa su nivel entero como rectángulo "
                         "proporcional junto al pasillo.")
            elif str(banda).startswith("contenedor"):
                texto = (f"No cabía en las bandas del pasillo y "
                         f"encaja en el {banda} del nivel "
                         f"{nivel_i}: el encaje estricto aprovecha "
                         "esa zona real de la parcela (dentro del "
                         "polígono) y queda conectado con el "
                         "resto por los locales contiguos.")
            elif banda == "zona compuesta":
                texto = (f"Es más profundo que cualquier franja "
                         "sola de la parcela: ocupa la unión de "
                         "dos contenedores contiguos (zona "
                         "compuesta) en el nivel "
                         f"{nivel_i}, siempre dentro del polígono.")
            elif float(r.get("hall_ancho") or 0.0) > 0.0 \
                    and float(r.get("hall_fondo") or 0.0) > 0.0:
                # v3.42.0: local de banda ADAPTADA (el pasillo se
                # sirve cambiando fondo por ancho, misma área)
                texto = (f"Sirve el pasillo del nivel {nivel_i} desde "
                         f"la banda {banda}: cambió fondo por ancho "
                         "conservando su área (la adaptación del "
                         "cambio de uso) y cabe junto al corredor.")
            else:
                texto = (f"Cabe en la banda {banda} del nivel "
                         f"{nivel_i} junto al pasillo de "
                         "distribución: el empaquetado a dos "
                         "bandas equilibra la fachada acumulada y "
                         "el rectángulo entra sin abrir otro "
                         "nivel.")
            decisiones.append({"tipo": "local",
                               "local": str(r["nombre"]),
                               "texto": texto})
    return decisiones


# ---------------------------------------------------------------------------
# 7) APLICAR: entidades reales por los caminos oficiales
# ---------------------------------------------------------------------------

def _nombre_unico(nombre: str, usados: set) -> str:
    candidato = nombre
    n = 2
    while candidato.lower() in usados:
        candidato = f"{nombre} {n}"
        n += 1
    usados.add(candidato.lower())
    return candidato


# ---------------------------------------------------------------------------
# 7-bis) v3.39.0: REEMPLAZO DEL EDIFICIO PREVIO (spec §27/§28): el
# asistente recuerda el último edificio que generó (clave de ajustes
# del proyecto) y puede eliminarlo ANTES de generar otro, en vez de
# acumular un segundo edificio en silencio. Todo por CommandBus, así
# el reemplazo queda en la transacción y es deshacible.
# ---------------------------------------------------------------------------

CLAVE_ULTIMO_EDIFICIO = "asistente_dd.ultimo_edificio"


def edificio_previo(ctx: Any) -> Optional[Any]:
    """El último edificio generado por este asistente en el proyecto
    (o None si no lo hay o ya no existe)."""
    settings = getattr(ctx, "settings", None)
    if settings is None:
        return None
    codigo = ""
    try:
        codigo = str(settings.get(CLAVE_ULTIMO_EDIFICIO, "") or "")
    except Exception:  # noqa: BLE001 — ajustes no disponibles
        return None
    if not codigo:
        return None
    try:
        arch = ArchitectureService(ctx)
        edificio = ctx.architecture.get_by_code("BUILDING", codigo) \
            or ctx.architecture.get("BUILDING", codigo)
        return edificio
    except Exception:  # noqa: BLE001 — referencia huérfana
        return None


def _elimina_edificio(ctx: Any, arch: ArchitectureService,
                      edificio: Any) -> Dict[str, int]:
    """Elimina el edificio con su gente: primero los espacios de cada
    nivel, luego los niveles y al final el edificio (el orden importa:
    el borrado en cascada oficial cubre vanos y redes, no niveles)."""
    niveles = [lv for lv in ctx.architecture.list(
        "LEVEL", ctx.project.id)
        if getattr(lv, "building_id", "") == edificio.id]
    ids_niveles = {lv.id for lv in niveles}
    espacios = [s for s in ctx.architecture.list(
        "SPACE", ctx.project.id) if getattr(s, "level_id", "") in ids_niveles]
    for espacio in espacios:
        arch.delete_entity("SPACE", espacio.id)
    for nivel in niveles:
        arch.delete_entity("LEVEL", nivel.id)
    arch.delete_entity("BUILDING", edificio.id)
    return {"espacios": len(espacios), "niveles": len(niveles)}


def _guarda_ultimo_edificio(ctx: Any, edificio: Any) -> None:
    settings = getattr(ctx, "settings", None)
    if settings is None:
        return
    try:
        settings.set(CLAVE_ULTIMO_EDIFICIO,
                     str(getattr(edificio, "code", "") or ""))
    except Exception:  # noqa: BLE001 — el registro no bloquea el flujo
        pass


def aplicar_plan(ctx: Any, analisis: Dict[str, Any],
                 opciones: Optional[Dict[str, Any]] = None) \
        -> Dict[str, Any]:
    """Genera el edificio del contorno: edificio nuevo con un nivel
    por cada planta del reparto (crecimiento en altura real), y en
    cada nivel el pasillo, los locales, la escalera (si procede),
    la zona, las relaciones y (opción) los muros del contorno y de
    cada local. Todo por los caminos oficiales (auditoría, eventos,
    QTO). El commit lo hace la UI, como en los demás asistentes."""
    opc = {
        "nombre_edificio": "Edificio desde dibujo",
        "trazar_muros": False, "eliminar_boceto": "",
        "modo": "edificacion",
        "reemplazar_previo": False,
        "espesor_contorno_m": ESPESOR_CONTORNO_M,
        "espesor_local_m": ESPESOR_LOCAL_M,
        "mobiliario": None,   # None = auto (vivienda sí, servicios no)
    }
    opc.update(opciones or {})
    arch = ArchitectureService(ctx)
    avisos: List[str] = list(analisis.get("avisos", []))

    boceto = str(opc["eliminar_boceto"] or "").strip()
    if boceto:
        try:
            arch.delete_entity("SPACE", boceto)
            avisos.append(f"espacio de boceto eliminado ({boceto})")
        except Exception:  # noqa: BLE001 — el boceto ya no estaba
            avisos.append(f"no se pudo eliminar el boceto {boceto} "
                          "(¿ya no existe?): se continúa")

    reemplazado = ""
    if opc["reemplazar_previo"]:
        previo = edificio_previo(ctx)
        if previo is not None:
            borrado = _elimina_edificio(ctx, arch, previo)
            reemplazado = str(getattr(previo, "code", "")
                              or getattr(previo, "name", ""))
            avisos.append(
                f"edificio anterior reemplazado ({reemplazado}): "
                f"{borrado['espacios']} espacio(s) y "
                f"{borrado['niveles']} nivel(es) eliminados")

    modo = "servicio" if opc["modo"] == "servicio" else "edificacion"
    programa = analisis["programa"]
    forma = analisis["forma"]
    altura = float(analisis.get("altura_nivel_m", 3.0))
    # v3.43.0: el mobiliario automático es de VIVIENDA (ámbito
    # doméstico: cama, sofá, hornillas, sanitarios...); en un servicio
    # (morgue, quirófanos...) no hay reglas domésticas y no se toca
    # nada salvo que se pida explícitamente
    vivienda = _es_vivienda(programa)
    amueblar = bool(vivienda) if opc["mobiliario"] is None \
        else bool(opc["mobiliario"])
    # v3.44.0: las plantas RADIALES (sector anular con arcos por
    # cuerdas), la TORRE EN Y (v3.45.0) y el HOSPITAL EN X (v3.47.0)
    # no se amueblan automáticamente: el mobiliario doméstico asume
    # recintos ortogonales; el usuario lo coloca a mano
    tipo_plan = str(analisis.get("tipo") or "")
    if amueblar and tipo_plan in ("radial", "y_radial", "x_radial"):
        amueblar = False
        avisos.append("planta radial (v3.44): el mobiliario "
                      "automático se omite (geometría curva/radiante); "
                      "colóquelo a mano")
    edificio = arch.create_building(str(opc["nombre_edificio"]))
    zona = arch.create_zone(
        f"Zona {edificio.name}",
        "SERVICE" if modo == "servicio" else "PUBLIC")
    usados_niveles = {lv.name.lower()
                      for lv in ctx.architecture.list(
                          "LEVEL", ctx.project.id)}

    creados: List[str] = []
    niveles_creados: List[str] = []
    relaciones = 0
    muros = 0
    mob_creados: List[str] = []
    for plan in analisis["reparto"]:
        base = f"Planta {plan['nivel']}"
        nombre_nivel = _nombre_unico(base, usados_niveles)
        nivel = arch.create_level(
            nombre_nivel, elevation_m=round((plan["nivel"] - 1) * altura, 4),
            height_m=altura, building_id=edificio.id)
        niveles_creados.append(nivel.name)
        usados_espacios: set = set()
        # v3.45.0: la TORRE EN Y lleva VARIOS corredores (uno por
        # ala) en la clave "pasillos"; cada local se relaciona con el
        # corredor de SU ala (campo "ala" de la pieza). Los caminos
        # previos (un solo pasillo) siguen igual.
        pasillos_nivel: List[Dict[str, Any]] = list(
            plan.get("pasillos") or [])
        if not pasillos_nivel and plan.get("pasillo"):
            pasillos_nivel = [plan["pasillo"]]
        piezas = pasillos_nivel \
            + plan["locales"] \
            + ([plan["escalera"]] if plan["escalera"] else []) \
            + ([plan["patio"]] if plan.get("patio") else [])
        if not plan.get("pasillo"):
            if analisis.get("sala_distribuidora"):
                avisos.append(
                    f"{base}: MODO SALA DISTRIBUIDORA (v3.43): sin "
                    "pasillo; la sala reparte el acceso entre locales")
            else:
                avisos.append(
                    f"{base}: nivel sin pasillo de distribución "
                    "(contenedores profundos): el acceso es "
                    "entre locales; ajuste puertas a voluntad "
                    "con las herramientas CAD")
        pasillo_code = ""
        pasillo_por_ala: Dict[int, str] = {}
        ids_nivel: List[str] = []
        for pieza in piezas:
            es_pasillo = pieza["codigo"] == "PASILLO"
            nombre = _nombre_unico(pieza["nombre"], usados_espacios)
            # v3.43.0: un local con chaflán se crea con su poligonal
            # real (5 vértices: el corte diagonal incluido)
            boundary = pieza.get("poligono") or pieza["rect"]
            espacio = arch.create_space(
                nivel.name, nombre, pieza["space_type"],
                [tuple(p) for p in boundary])
            arch.set_space_zone(espacio.id, zona.id)
            ids_nivel.append(espacio.id)
            ala = pieza.get("ala")
            if es_pasillo:
                pasillo_code = espacio.code
                if ala is not None and int(ala) >= 0:
                    pasillo_por_ala[int(ala)] = espacio.code
            elif pasillo_code:
                # v3.45.0: cada local va con el corredor de su ala
                destino = pasillo_code
                if ala is not None and int(ala) >= 0:
                    destino = pasillo_por_ala.get(int(ala),
                                                  pasillo_code)
                arch.add_relationship(espacio.id, destino,
                                      "adjacent_to",
                                      source=ORIGEN_DESDE_DIBUJO)
                relaciones += 1
            creados.append(espacio.code)
        if amueblar and vivienda:
            from domain import mobiliario as _mob
            try:
                resumen_mob = _mob.generar_mobiliario(
                    ctx, space_ids=ids_nivel, ambito="domestico",
                    densidad="estandar")
                mob_creados.extend(resumen_mob.get("creados", []))
                for aviso_m in resumen_mob.get("avisos", [])[:4]:
                    avisos.append(f"mobiliario: {aviso_m}")
            except Exception as exc:  # noqa: BLE001 — sin mobiliario
                avisos.append(
                    f"mobiliario automático no pudo colocarse: {exc}")
        if opc["trazar_muros"]:
            degeneradas = 0
            for i in range(len(forma["vertices"])):
                a = forma["vertices"][i]
                b = forma["vertices"][(i + 1) % len(forma["vertices"])]
                # v3.46.0: una arista degenerada (< 0.1 mm) abortaría
                # TODO el edificio con ARQ-DOM-048; se omite y se
                # documenta (la Y/radial ya llegan limpias, esto es
                # el cinturón de seguridad para cualquier plan)
                if math.hypot(float(b[0]) - float(a[0]),
                              float(b[1]) - float(a[1])) < 1e-4:
                    degeneradas += 1
                    continue
                arch.create_wall(nivel.name, tuple(a), tuple(b),
                                 thickness_m=float(
                                     opc["espesor_contorno_m"]))
                muros += 1
            for pieza in plan["locales"]:
                # v3.43.0: la poligonal (chaflán incluido) manda sobre
                # el rectángulo si existe
                aristas = pieza.get("poligono") or pieza["rect"]
                for i in range(len(aristas)):
                    a = aristas[i]
                    b = aristas[(i + 1) % len(aristas)]
                    if math.hypot(float(b[0]) - float(a[0]),
                                  float(b[1]) - float(a[1])) < 1e-4:
                        degeneradas += 1
                        continue
                    arch.create_wall(nivel.name, tuple(a), tuple(b),
                                     thickness_m=float(
                                         opc["espesor_local_m"]))
                    muros += 1
            if degeneradas:
                avisos.append(
                    f"{base}: {degeneradas} arista(s) degenerada(s) "
                    "(< 0.1 mm) omitidas al trazar muros")

    if opc["trazar_muros"]:
        avisos.append("muros del contorno y de cada local trazados: "
                      "las aristas compartidas quedan duplicadas, "
                      "remátelas con las herramientas CAD "
                      "(recortar/alargar)")
    if amueblar and vivienda:
        avisos.append(
            f"mobiliario automático (v3.43, ámbito doméstico): "
            f"{len(mob_creados)} pieza(s) colocadas en los locales "
            "generados")
    if analisis.get("con_escalera") and analisis.get("escalera"):
        avisos.append(analisis["escalera"]["descripcion"])

    contexto = ctx
    _guarda_ultimo_edificio(contexto, edificio)
    from core.audit.models import make_audit_event
    contexto.audit_repo.append(make_audit_event(
        user=getattr(contexto, "user", "local"),
        object_id=contexto.project.id, object_type="PROJECT",
        command="GENERAR_DESDE_DIBUJO", old_value=None,
        new_value={"edificio": edificio.name, "forma": forma["forma"],
                   "area_m2": forma["area_m2"],
                   "niveles": len(niveles_creados), "locales": len(creados)},
        reason="asistente desde dibujo", result="OK"))
    contexto.emit("DOCUMENT_CHANGED", {
        "action": "GENERADO_DESDE_DIBUJO", "edificio": edificio.name,
        "niveles": len(niveles_creados), "espacios": len(creados)})

    return {
        "operacion": "generar desde dibujo",
        "edificio": edificio.name, "zona": zona.code,
        "reemplazado": reemplazado,
        "niveles": niveles_creados,
        "altura_total_m": analisis["totales"]["altura_total"],
        "forma": forma["forma"], "area_contorno_m2": forma["area_m2"],
        "espacios": creados, "relaciones": relaciones,
        "muros": muros, "modo": modo,
        "mobiliario": {"activado": amueblar and vivienda,
                       "piezas": len(mob_creados),
                       "codigos": mob_creados},
        "totales": dict(analisis["totales"]),
        "avisos": avisos,
    }


# ---------------------------------------------------------------------------
# 8) TEXTO (cp1252, sin flechas)
# ---------------------------------------------------------------------------

ETIQUETA_FORMA = {
    "rectangulo": "rectángulo alineado a ejes",
    "ortogonal": "ortogonal (en L, en T...)",
    "poligono": "polígono general",
    "circulo": "círculo (planta radial)",
    "y_radial": "torre en Y con alas radiantes",
    "x_radial": "hospital en X con barras cruzadas y hub central",
}


def texto_inferencia(forma: Dict[str, Any]) -> str:
    lineas = ["CONTORNO DEL ÁREA",
              f"Forma: {ETIQUETA_FORMA.get(forma['forma'], forma['forma'])}"
              + ("" if forma.get("alineado", True) else " (girada)"),
              f"Área: {forma['area_m2']:.2f} m2 · Caja: "
              f"{float(forma.get('ancho_m', 0.0)):.2f} x "
              f"{float(forma.get('fondo_m', 0.0)):.2f} m · "
              f"Perímetro: {float(forma.get('perimetro_m', 0.0)):.2f} m",
              f"Vértices: {len(forma['vertices'])} (antihorario)"]
    angulos = forma.get("angulos") or []
    if angulos:
        lineas.append(
            "Lados: " + str(len(forma.get("lados") or angulos))
            + " · Ángulos: " + "/".join(f"{a:.0f}" for a in angulos)
            + " grados · Concavidades: "
            + str(int(forma.get("concavidades") or 0)))
    return "\n".join(lineas)


def texto_ajuste(analisis: Dict[str, Any]) -> str:
    programa = analisis["programa"]
    tot = analisis["totales"]
    lineas = ["AJUSTE DEL PROGRAMA AL CONTORNO",
              f"Programa: {programa['nombre']} · "
              f"{programa['totales']['locales']} local(es) · "
              f"{tot['area_programa']:.2f} m2",
              f"Contorno: {tot['area_contorno']:.2f} m2 · "
              f"pasillos {tot['area_pasillos']:.2f} m2"
              + (f" · escaleras {tot['area_escaleras']:.2f} m2"
                 if tot["area_escaleras"] else ""),
              "Cabe en 1 nivel: " + ("SÍ" if analisis["cabe_un_nivel"]
                                     else "NO")
              + ("" if analisis["cabe_un_nivel"] else
                 f" -> se reparte en {analisis['niveles']} niveles "
                 f"(altura total {tot['altura_total']:.2f} m)")]
    if analisis.get("escalera"):
        lineas.append("Escalera: " + analisis["escalera"]["descripcion"])
    enc = analisis.get("encaje") or {}
    if enc.get("contenedores"):
        estrategias = {"rectangulo": "rectángulo alineado",
                       "descompuesto": "polígono teselado en "
                                       "contenedores",
                       "inscrito": "rectángulo inscrito"}
        conts_t = ", ".join(
            f"{c['ancho_m']:.1f}x{c['fondo_m']:.1f} m"
            for c in enc["contenedores"][:6])
        if len(enc["contenedores"]) > 6:
            conts_t += f" (+{len(enc['contenedores']) - 6} más)"
        lineas.append(
            "Encaje: " + estrategias.get(enc.get("estrategia", ""),
                                         enc.get("estrategia", ""))
            + f" · {len(enc['contenedores'])} contenedor(es): "
            + conts_t)
        if tot.get("aprovechamiento_pct") is not None:
            lineas.append(
                f"Aprovechamiento del polígono: "
                f"{tot['aprovechamiento_pct']:.1f}% "
                f"({tot.get('area_aprovechada', 0.0):.2f} de "
                f"{tot['area_contorno'] * max(1, analisis['niveles']):.2f}"
                " m2 ocupados)")
    aj = analisis.get("ajuste_programa") or {}
    if aj.get("reducidos"):
        lineas.append("")
        lineas.append(f"AJUSTE DIMENSIONAL ({str(aj.get('nivel', '')).upper()}): "
                      f"{len(aj['reducidos'])} local(es) reducido(s) "
                      "para entrar en el contorno")
        for item in aj["reducidos"]:
            marca = " [BAJO LA NORMATIVA]" if item.get("bajo_norma") \
                else ""
            lineas.append(
                f"   - {item['nombre']}: {item['area_ideal']:.2f} -> "
                f"{item['area_final']:.2f} m2 "
                f"(-{item['reduccion_pct']:.1f}%){marca}")
        lineas.append(
            f"Área del programa: {aj.get('area_ideal_total', 0.0):.2f} -> "
            f"{aj.get('area_final_total', 0.0):.2f} m2")
        if aj.get("bajo_norma"):
            lineas.append(
                "aviso: se rebasa el mínimo normativo en "
                f"{len(aj['bajo_norma'])} local(es): decisión del "
                "proyectista, documentada aquí")
    circ = analisis.get("circulacion") or {}
    if circ:
        lineas.append("")
        lineas.append("CIRCULACIÓN Y FILTROS (v3.42.0):")
        con_p = circ.get("niveles_con_pasillo", [])
        if con_p:
            lineas.append(
                "   - pasillo de distribución en "
                + ", ".join(f"Planta {c['nivel']}"
                            + (" (adaptado: locales re-dimensionados)"
                               if c.get("adaptado") else "")
                            for c in con_p))
        sin_p = circ.get("niveles_sin_pasillo", [])
        if sin_p:
            lineas.append(
                "   - sin pasillo en Plantas "
                + ", ".join(str(n) for n in sin_p)
                + ": el acceso es entre locales")
        filtros = circ.get("filtros", [])
        if filtros:
            lineas.append(
                "   - filtro sanitario como barrera: "
                + ", ".join(f"{f['nombre']} ({f['area_m2']:.2f} m2, "
                            f"Planta {f['nivel']})"
                            for f in filtros))
        else:
            lineas.append(
                "   - sin filtro sanitario en el programa (añádalo o "
                "revise la barrera entre flujos)")
    tes = analisis.get("teselado") or {}
    if tes.get("locales_crecidos"):
        lineas.append("")
        lineas.append(
            f"TESELADO COMPLETO: {tes['locales_crecidos']} local(es) "
            f"crecieron {tes['area_ganada']:.2f} m2 para aprovechar "
            "los contenedores hasta sus bordes")
        for item in tes.get("detalle", [])[:8]:
            lineas.append(
                f"   - {item['nombre']}: {item['area_ideal']:.2f} -> "
                f"{item['area_final']:.2f} m2 (+"
                f"{item['crecido_m2']:.2f})")
        if tes["locales_crecidos"] > 8:
            lineas.append(f"   - ... y {tes['locales_crecidos'] - 8} "
                          "más")
    if analisis.get("tope_niveles") is not None:
        lineas.append("")
        lineas.append(
            f"TOPE DE NIVELES (v3.43.0): {analisis['tope_niveles']} "
            f"nivel(es) -> empaquetado final en "
            f"{analisis['niveles']}"
            + (" (tope respetado: se compactó antes de crecer)"
               if analisis["niveles"] <= analisis["tope_niveles"] else ""))
    if analisis.get("sala_distribuidora"):
        lineas.append(
            "MODO SALA DISTRIBUIDORA (v3.43.0): sin pasillo; la sala "
            "reparte el acceso entre locales (vivienda de 60 m2 o "
            "menos, como en los planos de referencia)")
    chafl = analisis.get("chaflanes") or []
    if chafl:
        lineas.append("CHAFLANES A 45 GRADOS (v3.43.0): "
                      f"{len(chafl)} esquina(s) abierta(s) hacia la "
                      "sala")
        for h in chafl[:8]:
            lineas.append(
                f"   - {h['local']}: cateto {h['cateto_m']:.2f} m, "
                f"pérdida {h['perdida_m2']:.2f} m2 (la sala la "
                "absorbe)")
    for plan in analisis["reparto"]:
        area_locales = sum(r["area_m2"] for r in plan["locales"])
        if plan.get("pasillo"):
            cab_nivel = (f"Nivel {plan['nivel']}: pasillo "
                         f"{plan['pasillo']['ancho_m']:.2f} x "
                         f"{PASILLO_ANCHO:.2f} m · ")
        else:
            cab_nivel = (f"Nivel {plan['nivel']}: SIN pasillo "
                         "(acceso entre locales) · ")
        lineas.append(
            cab_nivel + f"{len(plan['locales'])} local(es) "
            f"({area_locales:.2f} m2) · ocupado "
            f"{plan['area_ocupada']:.2f} de {plan['area_disponible']:.2f} "
            f"m2 · dentro del contorno: "
            + ("sí" if plan["dentro"] else "NO, revise"))
        for r in plan["locales"]:
            lineas.append(f"   - {r['nombre']} "
                          f"({r['space_type']}) {r['area_m2']:.2f} m2")
    if programa.get("validacion"):
        lineas.append("")
        from domain.servicios_engine import texto_validacion
        lineas.append(texto_validacion(programa["validacion"]))
    for nota in programa.get("notas", []):
        lineas.append(f"nota: {nota}")
    for aviso in analisis.get("avisos", []):
        lineas.append(f"aviso: {aviso}")
    return "\n".join(lineas)


def texto_resumen_generacion(resumen: Dict[str, Any]) -> str:
    """Una línea amable tras generar (barra de estado)."""
    return (f"{resumen['edificio']}: {len(resumen['niveles'])} nivel(es) "
            f"({resumen['altura_total_m']:.2f} m), "
            f"{len(resumen['espacios'])} espacio(s), zona "
            f"{resumen['zona']}"
            + (f", {resumen['muros']} muro(s)"
               if resumen.get("muros") else ""))


# ---------------------------------------------------------------------------
# 8) EXPLORADOR DEL CATÁLOGO (v3.36.0): el contorno contra TODOS los
#    servicios, para el flujo «desde dibujo -> servicio»
# ---------------------------------------------------------------------------

ETIQUETAS_SECTORES_V3 = {
    "SALUD": "Salud", "EDUCACION": "Educacion",
    "ADMINISTRACION": "Administracion",
    "COMERCIO": "Comercio y hosteleria", "DEPORTIVO": "Deportivo",
    "CULTURAL": "Cultural", "RESIDENCIAL": "Residencial asistido",
    "LOGISTICA": "Logistica",
}


def explorar_catalogo(contorno: List[PT], altura_nivel_m: float = 3.0,
                      margen_m: float = 0.0) -> List[Dict[str, Any]]:
    """Prueba el contorno dibujado contra TODO el catálogo v3.0.

    Para cada servicio arma su programa con los parámetros por
    defecto y corre ``ajustar`` con el contorno: devuelve una lista
    ordenada (primero los que CABEN en 1 nivel, luego los que crecen
    a N niveles, al final los imposibles con su código de error).
    Nunca toca el proyecto ni lanza: los fallos de un servicio no
    detienen el barrido.
    """
    from domain.servicios_engine import programa_servicio
    resultados: List[Dict[str, Any]] = []
    for item in _servicios_ordenados():
        try:
            programa = programa_servicio(item.codigo, {})
        except DomainError:
            continue
        try:
            analisis = ajustar(programa, list(contorno),
                               altura_nivel_m, margen_m)
        except DomainError as exc:
            resultados.append({
                "codigo": item.codigo, "nombre": item.nombre,
                "sector": item.sector,
                "locales": int(programa["totales"]["locales"]),
                "area_m2": float(programa["totales"]["area_m2"]),
                "niveles": None, "cabe_un_nivel": False,
                "error": str(exc.code or "ARQ-DDI-001")})
            continue
        resultados.append({
            "codigo": item.codigo, "nombre": item.nombre,
            "sector": item.sector,
            "locales": int(programa["totales"]["locales"]),
            "area_m2": float(programa["totales"]["area_m2"]),
            "niveles": int(analisis["niveles"]),
            "cabe_un_nivel": bool(analisis["cabe_un_nivel"]),
            "altura_total_m": float(
                analisis["totales"]["altura_total"]),
            "dentro_del_contorno": bool(
                analisis["dentro_del_contorno"]),
            "error": ""})
    resultados.sort(key=lambda r: (
        2 if r.get("error") else (0 if r["cabe_un_nivel"] else 1),
        r["niveles"] if r.get("niveles") else 99,
        r["area_m2"]))
    return resultados


def _servicios_ordenados() -> List[Any]:
    """Servicios del catálogo agrupados por sector (SALUD primero)."""
    from domain import servicios_specs as specs
    salida: List[Any] = []
    for _etiqueta, items in specs.servicios_por_sector():
        for codigo, _nombre in items:
            try:
                salida.append(specs.servicio(codigo))
            except DomainError:
                continue
    return salida


def texto_exploracion(resultados: List[Dict[str, Any]],
                      area_contorno_m2: float = 0.0) -> str:
    """Reporte cp1252 del barrido del catálogo (sin flechas)."""
    lineas = ["EXPLORACION DEL CATALOGO EN ESTE CONTORNO"]
    if area_contorno_m2 > 0:
        lineas.append(f"Area del contorno: {area_contorno_m2:.2f} m2")
    lineas.append(f"Servicios probados: {len(resultados)} (programa "
                  "con parametros por defecto)")
    lineas.append("")
    for r in resultados:
        etiqueta = ETIQUETAS_SECTORES_V3.get(r["sector"], r["sector"])
        prefijo = f"[{etiqueta}] {r['codigo']}"
        detalle = (f"{r['locales']} local(es), {r['area_m2']:.1f} m2")
        if r.get("error"):
            lineas.append(f"{prefijo}: NO ENTRA ({r['error']}) - "
                          f"{detalle}")
        elif r["cabe_un_nivel"]:
            lineas.append(f"{prefijo}: CABE EN 1 NIVEL - {detalle}")
        else:
            lineas.append(
                f"{prefijo}: crece a {r['niveles']} niveles "
                f"(altura {r.get('altura_total_m', 0.0):.2f} m) - "
                f"{detalle}")
    lineas.append("")
    lineas.append("Elija un servicio, revise «Cabe en el area?» con "
                  "sus propios parametros y pulse Generar.")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# 9) v3.39.0: VALIDACIÓN PREVIA DEL CONTORNO (spec §11 + §24). Antes
#    de ajustar nada, el asistente examina el dibujo importado y
#    emite hallazgos por severidad: ERROR (bloquea), ADVERTENCIA y
#    RECOMENDACIÓN. Nada se adivina: cada hallazgo dice qué hacer.
# ---------------------------------------------------------------------------

AREA_MIN_ERROR_M2 = 0.5       # por debajo: dimensiones imposibles
AREA_MIN_AVISO_M2 = 4.0       # por debajo: muy pequeño para un programa
AREA_MAX_AVISO_M2 = 100000.0  # por encima: ¿unidades correctas?
RELACION_MAX_AVISO = 20.0     # caja más alargada que esto: revise
ANGULO_LLANO_TOL = 0.5        # grados alrededor de 180: casi colineal

SEVERIDADES = ("ERROR", "ADVERTENCIA", "RECOMENDACIÓN")


def _norm_sin_area(puntos: List[PT]) -> List[PT]:
    """Normalización ligera (floats, sin repetidos, sin cierre
    duplado) para detectar el lazo ANTES de que el área con signo
    nula del bowtie dispare el error de vértices colineales."""
    pts: List[PT] = []
    for p in puntos or []:
        try:
            q = (float(p[0]), float(p[1]))
        except (TypeError, ValueError, IndexError):
            continue
        if pts and abs(q[0] - pts[-1][0]) < 1e-9 \
                and abs(q[1] - pts[-1][1]) < 1e-9:
            continue
        pts.append(q)
    while len(pts) >= 2 and abs(pts[0][0] - pts[-1][0]) < 1e-9 \
            and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts.pop()
    return pts


def validar_contorno(puntos: List[PT]) -> Dict[str, Any]:
    """Examen honesto del contorno importado (spec §11): autointer-
    secciones, área cero, dimensiones imposibles, geometría
    degenerada; y datos derivados (lados, ángulos, concavidades,
    relación de caja). Nunca lanza: devuelve hallazgos con
    severidad y el flag ``bloquea`` cuando hay ERROR.

    El polígono ABIERTO de verdad lo detecta la IMPORTACIÓN
    (contornos_dxf ignora las polilíneas abiertas y cierra las casi
    cerradas con su aviso ``cerrada_auto``): aquí los vértices se
    leen siempre como polígono cerrado (el CAD implícito), así que
    la distancia entre el primer y el último vértice NO significa
    nada y no se interpreta como «abierto»."""
    hallazgos: List[Dict[str, str]] = []
    forma: Optional[Dict[str, Any]] = None
    datos: Dict[str, Any] = {}
    pts = _norm_sin_area(puntos)
    if len(pts) < 3:
        hallazgos.append({
            "severidad": "ERROR",
            "texto": "el contorno necesita al menos 3 vértices "
                     "útiles (ARQ-DDI-001): importe una polilínea "
                     "cerrada, elija un espacio del proyecto o "
                     "dibuje el rectángulo del área"})
        return {"valido": False, "bloquea": True,
                "hallazgos": hallazgos, "forma": None,
                "datos": datos}
    if autointersecado(pts):
        hallazgos.append({
            "severidad": "ERROR",
            "texto": "el contorno se cruza a sí mismo (forma de "
                     "lazo): las aristas no delimitan un área "
                     "honesta; corrija el dibujo o importe otra "
                     "polilínea cerrada"})
        return {"valido": False, "bloquea": True,
                "hallazgos": hallazgos, "forma": None,
                "datos": datos}
    try:
        forma = inferir(pts)
    except DomainError as exc:
        hallazgos.append({
            "severidad": "ERROR",
            "texto": f"{getattr(exc, 'message', exc)} "
                     f"({getattr(exc, 'code', '')})"})
        return {"valido": False, "bloquea": True,
                "hallazgos": hallazgos, "forma": None,
                "datos": datos}
    area = float(forma["area_m2"])
    datos = {"forma": forma["forma"], "area_m2": area,
             "perimetro_m": float(forma["perimetro_m"]),
             "vertices": len(forma["vertices"]),
             "lados": list(forma.get("lados") or []),
             "angulos": list(forma.get("angulos") or []),
             "concavidades": int(forma.get("concavidades") or 0),
             "ancho_m": float(forma["ancho_m"]),
             "fondo_m": float(forma["fondo_m"]),
             "relacion": float(forma.get("relacion") or 0.0)}
    if area < AREA_MIN_ERROR_M2:
        hallazgos.append({
            "severidad": "ERROR",
            "texto": f"dimensiones imposibles: {area:.3f} m2 no "
                     "alcanzan para cualquier local; revise "
                     "unidades y escala del dibujo"})
    elif area < AREA_MIN_AVISO_M2:
        hallazgos.append({
            "severidad": "ADVERTENCIA",
            "texto": f"el área ({area:.2f} m2) es muy pequeña "
                     "para un programa real; revise la escala"})
    if area > AREA_MAX_AVISO_M2:
        hallazgos.append({
            "severidad": "ADVERTENCIA",
            "texto": f"el área ({area:.0f} m2) supera las 10 ha: "
                     "¿está el dibujo en metros?"})
    relacion = float(forma.get("relacion") or 0.0)
    if relacion > RELACION_MAX_AVISO:
        hallazgos.append({
            "severidad": "ADVERTENCIA",
            "texto": f"contorno muy alargado ({forma['ancho_m']:.1f}"
                     f" x {forma['fondo_m']:.1f} m): el empaquetado "
                     "de dos bandas desperdiciará la punta; "
                     "considere partir el área"})
    llanos = sum(1 for a in (forma.get("angulos") or [])
                 if abs(a - 180.0) <= ANGULO_LLANO_TOL)
    if llanos:
        hallazgos.append({
            "severidad": "RECOMENDACIÓN",
            "texto": f"hay {llanos} vértice(s) casi colineal(es): "
                     "limpie el dibujo para que la forma "
                     "clasificada sea la verdadera"})
    valido = not any(h["severidad"] == "ERROR" for h in hallazgos)
    return {"valido": valido, "bloquea": not valido,
            "hallazgos": hallazgos, "forma": forma, "datos": datos}


def texto_validacion_contorno(validacion: Dict[str, Any]) -> str:
    """Reporte cp1252 de los hallazgos (sin flechas)."""
    lineas = ["VALIDACIÓN DEL CONTORNO"]
    if not validacion["hallazgos"]:
        lineas.append("Sin incidencias: forma, área y dimensiones "
                      "razonables. Listo para el ajuste.")
    for h in validacion["hallazgos"]:
        lineas.append(f"[{h['severidad']}] {h['texto']}")
    if validacion["bloquea"]:
        lineas.append("Corrija los ERROR antes de continuar: el "
                      "ajuste con este contorno no sería honesto.")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# 10) v3.39.0: CHECKLIST PREVIA A GENERAR (spec §24): un único bloque
#     con [OK]/[AVISO]/[ERROR] que consolida contorno, programa,
#     crecimiento, escalera, dentro del contorno y los deseos del
#     usuario (niveles pedidos, patio pedido).
# ---------------------------------------------------------------------------

def checklist_previa(validacion: Optional[Dict[str, Any]],
                     analisis: Optional[Dict[str, Any]] = None,
                     niveles_deseados: Optional[int] = None,
                     patio_pedido: bool = False) -> List[Dict[str, str]]:
    """Casillas del pre-vuelo: cada una con estado OK/AVISO/ERROR."""
    items: List[Dict[str, str]] = []
    if validacion is not None:
        for h in validacion["hallazgos"]:
            estado = {"ERROR": "ERROR", "ADVERTENCIA": "AVISO"}.get(
                h["severidad"], "OK")
            items.append({"estado": estado,
                          "texto": f"Contorno: {h['texto']}"})
        if not validacion["hallazgos"]:
            items.append({"estado": "OK",
                          "texto": "Contorno válido (forma, área y "
                                   "dimensiones razonables)"})
    if analisis is not None:
        programa = analisis["programa"]
        tot = programa.get("totales", {})
        items.append({"estado": "OK",
                      "texto": f"Programa válido: "
                               f"{int(tot.get('locales', 0))} local(es) "
                               f"({float(tot.get('area_m2', 0.0)):.1f} "
                               "m2)"})
        niveles = int(analisis["niveles"])
        if niveles >= NIVELES_MAX:
            items.append({"estado": "ERROR",
                          "texto": f"El programa necesita {niveles} "
                                   "niveles: alcanza el techo del "
                                   "crecimiento en altura"})
        elif niveles == 1:
            items.append({"estado": "OK",
                          "texto": "Cabe en 1 nivel (sin escalera)"})
        else:
            items.append({"estado": "OK",
                          "texto": f"Crece a {niveles} niveles con el "
                                   "recinto de la escalera reservado "
                                   "en cada uno (Blondel)"})
        if analisis.get("dentro_del_contorno"):
            items.append({"estado": "OK",
                          "texto": "Todos los recintos quedan dentro "
                                   "del contorno dibujado"})
        else:
            items.append({"estado": "AVISO",
                          "texto": "Hay recintos fuera del polígono "
                                   "(la caja envolvente no coincide "
                                   "con la forma): revise el reparto"})
        if niveles_deseados is not None \
                and int(niveles_deseados) != niveles:
            items.append({
                "estado": "AVISO",
                "texto": f"Pidió {int(niveles_deseados)} nivel(es) "
                         f"pero el empaquetado óptimo usa {niveles}: "
                         "ajuste áreas o el contorno si quiere "
                         "forzarlo"})
        if patio_pedido and not analisis.get("patio"):
            items.append({"estado": "AVISO",
                          "texto": "El patio pedido no cabe en este "
                                   "contorno: la opción se ignora"})
    return items


def texto_checklist(items: List[Dict[str, str]]) -> str:
    """Bloque cp1252 del pre-vuelo (sin flechas, sin unicode raro)."""
    lineas = ["CHECKLIST ANTES DE GENERAR"]
    if not items:
        lineas.append("(sin casillas: analice el contorno primero)")
    for item in items:
        lineas.append(f"[{item['estado']}] {item['texto']}")
    if any(i["estado"] == "ERROR" for i in items):
        lineas.append("Hay ERROR: no genere hasta corregirlos.")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# 11) v3.39.0: CONTRATOS ASISTENTE <-> MOTOR (spec §37-§39). El
#     asistente NUNCA dibuja: empaqueta su intención en un
#     PlanRequest serializable (contorno, programa, opciones expertas,
#     criterios) y el resultado vuelve como PlanResult con checklist,
#     métricas y decisiones. to_dict/from_dict permite guardar el
#     estado del asistente junto con el proyecto (spec §30).
# ---------------------------------------------------------------------------

def _criterios_def() -> Dict[str, float]:
    """Pesos por defecto de los criterios de diseño (spec §20)."""
    return {"funcionalidad": 100.0, "aprovechamiento": 90.0,
            "circulacion": 70.0, "simplicidad": 60.0}


@dataclass
class PlanRequest:
    """La intención arquitectónica estructurada que el asistente
    entrega al empaquetado y (tras aplicar) al motor."""
    contorno: List[PT]
    programa: Dict[str, Any]
    altura_nivel_m: float = 3.0
    margen_m: float = 0.0
    modo: str = "edificacion"
    nombre_edificio: str = "Edificio desde dibujo"
    trazar_muros: bool = False
    patio: bool = False
    patio_ancho_m: float = 3.0
    espesor_contorno_m: float = ESPESOR_CONTORNO_M
    espesor_local_m: float = ESPESOR_LOCAL_M
    niveles_deseados: Optional[int] = None
    encaje_estricto: bool = True
    seleccion: Optional[List[str]] = None
    ajuste: str = "ideal"
    chaflanes: Optional[bool] = None
    distribuidora_max_m2: Optional[float] = None
    chaflan_propio: Optional[bool] = None
    criterios: Dict[str, float] = field(default_factory=_criterios_def)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contorno": [[float(x), float(y)] for x, y in self.contorno],
            "programa": self.programa,
            "altura_nivel_m": float(self.altura_nivel_m),
            "margen_m": float(self.margen_m),
            "modo": str(self.modo),
            "nombre_edificio": str(self.nombre_edificio),
            "trazar_muros": bool(self.trazar_muros),
            "patio": bool(self.patio),
            "patio_ancho_m": float(self.patio_ancho_m),
            "espesor_contorno_m": float(self.espesor_contorno_m),
            "espesor_local_m": float(self.espesor_local_m),
            "niveles_deseados": (int(self.niveles_deseados)
                                 if self.niveles_deseados else None),
            "encaje_estricto": bool(self.encaje_estricto),
            "seleccion": ([str(s) for s in self.seleccion]
                          if self.seleccion else None),
            "ajuste": str(self.ajuste or "ideal"),
            "chaflanes": (None if self.chaflanes is None
                          else bool(self.chaflanes)),
            "distribuidora_max_m2": (None if self.distribuidora_max_m2
                                     is None
                                     else float(
                                         self.distribuidora_max_m2)),
            "chaflan_propio": (None if self.chaflan_propio is None
                               else bool(self.chaflan_propio)),
            "criterios": {k: float(v)
                          for k, v in self.criterios.items()},
        }

    @classmethod
    def from_dict(cls, datos: Optional[Dict[str, Any]]) -> "PlanRequest":
        datos = dict(datos or {})
        contorno = [(float(p[0]), float(p[1]))
                    for p in (datos.get("contorno") or [])]
        crit = _criterios_def()
        for clave, valor in dict(datos.get("criterios") or {}).items():
            if clave in crit:
                try:
                    crit[clave] = float(valor)
                except (TypeError, ValueError):
                    continue
        pedido = datos.get("niveles_deseados")
        try:
            pedido = int(pedido) if pedido not in (None, "") else None
        except (TypeError, ValueError):
            pedido = None
        try:
            esp_cont = float(datos.get("espesor_contorno_m",
                                       ESPESOR_CONTORNO_M)
                             or ESPESOR_CONTORNO_M)
        except (TypeError, ValueError):
            esp_cont = ESPESOR_CONTORNO_M
        try:
            esp_loc = float(datos.get("espesor_local_m", ESPESOR_LOCAL_M)
                            or ESPESOR_LOCAL_M)
        except (TypeError, ValueError):
            esp_loc = ESPESOR_LOCAL_M
        bruto_sel = datos.get("seleccion")
        sel_limpia = [str(s).strip() for s in bruto_sel if str(s).strip()] \
            if isinstance(bruto_sel, list) else None
        ajuste = str(datos.get("ajuste") or "ideal").strip().lower()
        if ajuste not in AJUSTE_NIVELES:
            ajuste = "ideal"
        chaflanes = datos.get("chaflanes")
        chaflanes = None if chaflanes is None else bool(chaflanes)
        dist_max = datos.get("distribuidora_max_m2")
        try:
            dist_max = (float(dist_max)
                        if dist_max not in (None, "") else None)
        except (TypeError, ValueError):
            dist_max = None
        propio = datos.get("chaflan_propio")
        propio = None if propio is None else bool(propio)
        return cls(
            contorno=contorno,
            programa=dict(datos.get("programa") or {}),
            altura_nivel_m=float(datos.get("altura_nivel_m", 3.0) or 3.0),
            margen_m=float(datos.get("margen_m", 0.0) or 0.0),
            modo=str(datos.get("modo") or "edificacion"),
            nombre_edificio=str(datos.get("nombre_edificio")
                                or "Edificio desde dibujo"),
            trazar_muros=bool(datos.get("trazar_muros", False)),
            patio=bool(datos.get("patio", False)),
            patio_ancho_m=float(datos.get("patio_ancho_m", 3.0) or 3.0),
            espesor_contorno_m=esp_cont,
            espesor_local_m=esp_loc,
            niveles_deseados=pedido,
            encaje_estricto=bool(datos.get("encaje_estricto", True)),
            seleccion=sel_limpia,
            ajuste=ajuste,
            chaflanes=chaflanes,
            distribuidora_max_m2=dist_max,
            chaflan_propio=propio,
            criterios=crit)


@dataclass
class PlanResult:
    """Lo que el empaquetado devuelve al asistente (y el asistente a
    la GUI): análisis, validación, checklist, métricas y petición."""
    peticion: PlanRequest
    validacion: Dict[str, Any]
    analisis: Dict[str, Any]
    checklist: List[Dict[str, str]]
    metricas: Dict[str, Any]


def plan_de(peticion: PlanRequest) -> PlanResult:
    """Ejecuta el ciclo completo del asistente sobre una petición:
    valida el contorno y, SOLO SI NO HAY ERROR, empaqueta el
    programa (con patio si procede) y arma checklist y métricas.
    Con el contorno bloqueado no se ajusta nada (spec §24) y las
    métricas quedan vacías con su motivo. Lanza DomainError si el
    programa no cabe (igual que ajustar)."""
    validacion = validar_contorno(peticion.contorno)
    if validacion["bloquea"]:
        checklist = checklist_previa(validacion, None,
                                     peticion.niveles_deseados,
                                     peticion.patio)
        return PlanResult(
            peticion=peticion, validacion=validacion, analisis=None,
            checklist=checklist,
            metricas={"area_construida_m2": 0.0, "area_util_m2": 0.0,
                      "circulacion_pct": 0.0, "ocupacion_pct": 0.0,
                      "cumplimiento_pct": 0.0, "locales_fuera": 0,
                      "niveles": None, "puntuacion": 0.0,
                      "motivo": "contorno con ERROR: sin métricas "
                                "hasta corregirlo"})
    analisis = ajustar(peticion.programa, list(peticion.contorno),
                       altura_nivel_m=peticion.altura_nivel_m,
                       margen_m=peticion.margen_m,
                       patio=peticion.patio,
                       patio_ancho_m=peticion.patio_ancho_m,
                       encaje_estricto=bool(
                           getattr(peticion, "encaje_estricto", True)),
                       seleccion=getattr(peticion, "seleccion", None),
                       ajuste=str(getattr(peticion, "ajuste", "ideal")
                                  or "ideal"),
                       niveles_deseados=getattr(peticion,
                                                "niveles_deseados", None),
                       chaflanes=getattr(peticion, "chaflanes", None),
                       distribuidora_max_m2=getattr(
                           peticion, "distribuidora_max_m2", None),
                       chaflan_propio=getattr(peticion,
                                              "chaflan_propio", None))
    checklist = checklist_previa(validacion, analisis,
                                 peticion.niveles_deseados,
                                 peticion.patio)
    metricas = metricas_de(analisis, peticion.criterios)
    return PlanResult(peticion=peticion, validacion=validacion,
                      analisis=analisis, checklist=checklist,
                      metricas=metricas)


def metricas_de(analisis: Dict[str, Any],
                criterios: Optional[Dict[str, float]] = None) \
        -> Dict[str, Any]:
    """Métricas comparables de un análisis (spec §25/§26): área
    construida y útil, porcentaje de circulación, ocupación,
    cumplimiento y puntuación EXPLICADA con los pesos elegidos."""
    crit = _criterios_def()
    for clave, valor in dict(criterios or {}).items():
        if clave in crit:
            try:
                crit[clave] = float(valor)
            except (TypeError, ValueError):
                continue
    tot = analisis["totales"]
    construida = round(sum(float(n["area_ocupada"])
                           for n in analisis["reparto"]), 2)
    util = round(sum(float(r["area_m2"])
                     for n in analisis["reparto"]
                     for r in n["locales"]), 2)
    circ = ((tot["area_pasillos"] + tot["area_escaleras"])
            / construida * 100.0) if construida > 1e-9 else 0.0
    # ocupación sobre el ÁREA DEL CONTORNO por nivel: así el margen
    # experto no infla la métrica y las variantes se comparan igual
    disponible = float(tot.get("area_contorno", 0.0)) \
        * max(1, int(analisis["niveles"]))
    ocupacion = (construida / disponible * 100.0) \
        if disponible > 1e-9 else 0.0
    dentro, total = _locales_dentro(analisis)
    cumplimiento = (dentro / total * 100.0) if total else 0.0
    niveles = int(analisis["niveles"])
    simple = 1.0 if niveles == 1 else max(0.5, 1.0 - 0.05 * (niveles - 1))
    pesos = sum(crit.values()) or 1.0
    puntuacion = (
        crit["funcionalidad"] * (cumplimiento / 100.0)
        + crit["aprovechamiento"] * (min(ocupacion, 100.0) / 100.0)
        + crit["circulacion"] * (1.0 - min(circ, 100.0) / 100.0)
        + crit["simplicidad"] * simple) / pesos * 100.0
    motivo = (
        f"cumplimiento {cumplimiento:.0f}% x peso funcionalidad "
        f"{crit['funcionalidad']:.0f}; ocupación "
        f"{min(ocupacion, 100.0):.0f}% x peso aprovechamiento "
        f"{crit['aprovechamiento']:.0f}; circulación {circ:.1f}% x peso "
        f"circulación {crit['circulacion']:.0f} (menor es mejor); "
        f"simplicidad {simple:.2f} x peso simplicidad "
        f"{crit['simplicidad']:.0f}")
    return {"area_construida_m2": construida,
            "area_util_m2": util,
            "circulacion_pct": round(circ, 2),
            "ocupacion_pct": round(ocupacion, 2),
            "cumplimiento_pct": round(cumplimiento, 2),
            "locales_fuera": total - dentro,
            "niveles": niveles,
            "puntuacion": round(puntuacion, 2),
            "motivo": motivo}


def _locales_dentro(analisis: Dict[str, Any]) -> Tuple[int, int]:
    """Cuenta cuántos locales del reparto quedan dentro del contorno.
    v3.40.0: con el encaje estricto la prueba es SIEMPRE contra el
    polígono real (la caja envolvente daba falsos positivos en L/U/T:
    un local fuera de la parcela pero dentro de su caja contaba como
    dentro). v3.45.0: los locales SOLO-POLIGONAL de la geometría
    radial (plan_radial/plan_y no llevan rect) se prueban por su
    CENTROIDE con el ray-casting del polígono: así las métricas de
    las torres curvas son honestas (antes contaban como fuera)."""
    forma = analisis["forma"]
    estricto = bool((analisis.get("encaje") or {}).get("contenedores"))
    dentro = total = 0
    for plan in analisis["reparto"]:
        for r in plan["locales"]:
            total += 1
            rect = r.get("rect")
            if not rect:
                poly = r.get("poligono") or []
                if poly:
                    cx = sum(float(p[0]) for p in poly) / len(poly)
                    cy = sum(float(p[1]) for p in poly) / len(poly)
                    if _punto_dentro((cx, cy), forma["vertices"]):
                        dentro += 1
                continue
            if estricto:
                ok = rect_dentro([tuple(p) for p in rect],
                                 forma["vertices"])
            elif forma["alineado"]:
                bx = forma["bbox"]
                ok = (min(p[0] for p in rect) >= bx[0] - 1e-6
                      and min(p[1] for p in rect) >= bx[1] - 1e-6
                      and max(p[0] for p in rect) <= bx[2] + 1e-6
                      and max(p[1] for p in rect) <= bx[3] + 1e-6)
            else:
                ok = rect_dentro([tuple(p) for p in rect],
                                 forma["vertices"])
            if ok:
                dentro += 1
    return dentro, total


# ---------------------------------------------------------------------------
# 12) v3.39.0: ALTERNATIVAS 1/3/5 (spec §25/§26). El mismo programa se
#     prueba en el contorno con tres estrategias honestas: tal cual,
#     girada 90 grados (empaquetado transpuesto y devuelto al sistema
#     de coordenadas del dibujo) y compacta (margen +0,5 m). Cada una
#     con sus métricas y su puntuación explicada; A es la mejor.
# ---------------------------------------------------------------------------

ETIQUETAS_ALT = "ABCDE"


def _transponer(puntos: List[PT]) -> List[PT]:
    return [(float(y), float(x)) for x, y in puntos]


def _pieza_transpuesta(pieza: Dict[str, Any]) -> Dict[str, Any]:
    """Copia de una pieza del reparto con su rectángulo (y sus
    dimensiones) devueltos al sistema de coordenadas del dibujo."""
    salida = dict(pieza)
    salida["rect"] = [(float(y), float(x))
                      for x, y in pieza["rect"]]
    if "ancho_m" in salida and "fondo_m" in salida:
        salida["ancho_m"], salida["fondo_m"] = \
            salida["fondo_m"], salida["ancho_m"]
    if "hall_ancho" in salida and "hall_fondo" in salida:
        salida["hall_ancho"], salida["hall_fondo"] = \
            salida["hall_fondo"], salida["hall_ancho"]
    return salida


def _des_transponer(analisis: Dict[str, Any]) -> Dict[str, Any]:
    """Ajuste hecho sobre el contorno transpuesto, devuelto al
    sistema de coordenadas original: forma, pasillos, locales,
    escalera, patio y la prueba 'dentro del contorno' recalculada."""
    forma_o = analisis["forma"]
    bbox_o = forma_o["bbox"]
    forma = dict(forma_o)
    forma["vertices"] = [(float(y), float(x))
                         for x, y in forma_o["vertices"]]
    forma["bbox"] = (bbox_o[1], bbox_o[0], bbox_o[3], bbox_o[2])
    forma["ancho_m"], forma["fondo_m"] = forma_o["fondo_m"], \
        forma_o["ancho_m"]
    forma["centroide"] = (float(forma_o["centroide"][1]),
                          float(forma_o["centroide"][0]))
    nuevo_reparto: List[Dict[str, Any]] = []
    dentro_total = True
    for plan in analisis["reparto"]:
        nuevo = dict(plan)
        nuevo["pasillo"] = _pieza_transpuesta(plan["pasillo"])
        nuevo["locales"] = [_pieza_transpuesta(r)
                            for r in plan["locales"]]
        nuevo["escalera"] = (_pieza_transpuesta(plan["escalera"])
                             if plan.get("escalera") else None)
        nuevo["patio"] = (_pieza_transpuesta(plan["patio"])
                          if plan.get("patio") else None)
        dentro = True
        piezas = [nuevo["pasillo"]] + nuevo["locales"] \
            + ([nuevo["escalera"]] if nuevo["escalera"] else []) \
            + ([nuevo["patio"]] if nuevo["patio"] else [])
        for pieza in piezas:
            if forma["alineado"]:
                bx = forma["bbox"]
                if min(p[0] for p in pieza["rect"]) < bx[0] - 1e-6 \
                        or min(p[1] for p in pieza["rect"]) < bx[1] - 1e-6 \
                        or max(p[0] for p in pieza["rect"]) > bx[2] + 1e-6 \
                        or max(p[1] for p in pieza["rect"]) > bx[3] + 1e-6:
                    dentro = False
            else:
                if not rect_dentro(pieza["rect"], forma["vertices"]):
                    dentro = False
        if not dentro:
            dentro_total = False
        nuevo["dentro"] = dentro
        nuevo_reparto.append(nuevo)
    salida = dict(analisis)
    salida["forma"] = forma
    salida["reparto"] = nuevo_reparto
    salida["dentro_del_contorno"] = dentro_total
    salida["avisos"] = list(analisis.get("avisos", [])) + [
        "variante girada 90 grados: el empaquetado se hizo sobre el "
        "contorno transpuesto y se devolvió al sistema de "
        "coordenadas del dibujo (las bandas norte/sur del reparto "
        "corresponden a este/oeste)"]
    return salida


def alternativas(programa: Dict[str, Any], contorno: List[PT],
                 cantidad: int = 3, altura_nivel_m: float = 3.0,
                 margen_m: float = 0.0, patio: bool = False,
                 patio_ancho_m: float = 3.0,
                 criterios: Optional[Dict[str, float]] = None,
                 seleccion: Optional[List[str]] = None,
                 ajuste: str = "ideal",
                 niveles_deseados: Optional[int] = None,
                 chaflanes: Optional[bool] = None,
                 distribuidora_max_m2: Optional[float] = None,
                 chaflan_propio: Optional[bool] = None) \
        -> List[Dict[str, Any]]:
    """Prueba el programa en el contorno con hasta ``cantidad``
    estrategias (1, 3 o 5; las disponibles: tal cual, girada 90
    grados, compacta). Ordena por puntuación descendente (los NO
    ENTRA al final) y re-etiqueta A, B, C... Orden honesto: A es la
    mejor. Nunca lanza: los fallos de una estrategia no detienen las
    demás. v3.41.0: respeta la selección de locales y el nivel de
    ajuste dimensional del diálogo. v3.43.0: respeta también el tope
    de niveles y los chaflanes. v3.44.0: respeta el umbral del modo
    distribuidor y el chaflán propio de fachada."""
    estrategias = (
        ("tal cual", None),
        ("girada 90 grados", "transpuesta"),
        ("compacta (margen +0,5 m)", "compacta"),
        ("compacta girada", "compacta_transpuesta"),
        ("holgada (margen 1 m)", "holgada"),
    )
    cantidad = max(1, min(int(cantidad or 1), len(estrategias), 5))
    salida: List[Dict[str, Any]] = []
    for indice, (nombre, modo_var) in enumerate(estrategias[:cantidad]):
        resultado: Dict[str, Any] = {
            "etiqueta": ETIQUETAS_ALT[indice], "estrategia": nombre,
            "analisis": None, "metricas": None, "niveles": None,
            "error": ""}
        try:
            margen_var = margen_m
            if modo_var == "compacta":
                margen_var = margen_m + 0.5
            elif modo_var == "holgada":
                margen_var = margen_m + 1.0
            transponer = modo_var in ("transpuesta",
                                      "compacta_transpuesta")
            base = _transponer(list(contorno)) if transponer \
                else list(contorno)
            analisis = ajustar(programa, base, altura_nivel_m,
                               margen_var, patio, patio_ancho_m,
                               seleccion=seleccion, ajuste=ajuste,
                               niveles_deseados=niveles_deseados,
                               chaflanes=chaflanes,
                               distribuidora_max_m2=
                               distribuidora_max_m2,
                               chaflan_propio=chaflan_propio)
            if transponer:
                analisis = _des_transponer(analisis)
            resultado["analisis"] = analisis
            resultado["metricas"] = metricas_de(analisis, criterios)
            resultado["niveles"] = int(analisis["niveles"])
        except DomainError as exc:
            resultado["error"] = str(getattr(exc, "code", "")
                                     or "ARQ-DDI-003")
        salida.append(resultado)
    salida.sort(key=lambda r: (
        1 if r["error"] else 0,
        -(r["metricas"]["puntuacion"] if r["metricas"] else 0.0)))
    for i, r in enumerate(salida):
        r["etiqueta"] = ETIQUETAS_ALT[i]
    return salida


def texto_alternativas(lista: List[Dict[str, Any]]) -> str:
    """Comparativa cp1252 de las alternativas (sin flechas)."""
    lineas = ["ALTERNATIVAS DEL PROGRAMA EN ESTE CONTORNO"]
    for r in lista:
        if r["error"]:
            lineas.append(f"{r['etiqueta']} - {r['estrategia']}: "
                          f"NO ENTRA ({r['error']})")
            continue
        met = r["metricas"]
        lineas.append(
            f"{r['etiqueta']} - {r['estrategia']}: "
            f"{met['niveles']} nivel(es) · construida "
            f"{met['area_construida_m2']:.1f} m2 · útil "
            f"{met['area_util_m2']:.1f} m2 · circulación "
            f"{met['circulacion_pct']:.1f} % · ocupación "
            f"{met['ocupacion_pct']:.1f} % · cumplimiento "
            f"{met['cumplimiento_pct']:.0f} % -> puntuación "
            f"{met['puntuacion']:.1f}")
    lineas.append("Puntuación = pesos del diseño sobre las métricas "
                  "(funcionalidad, aprovechamiento, circulación y "
                  "simplicidad): la A es la mejor. Elija la suya y "
                  "pulse Generar.")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# v3.44.0 — MULTI-ALA Y MULTI-UNIDAD: UN programa en N contornos
# (el hospital en alas, la residencia en Y y el edificio tipo de
# viviendas repetidas de las imágenes de referencia)
# ---------------------------------------------------------------------------

_HUBS_ZONA = ("VESTIBULE", "ENTRANCE", "LIVING_ROOM")


def _programa_de_renglones(renglones: List[Dict[str, Any]],
                           nombre: str,
                           avisos: Optional[List[str]] = None) \
        -> Dict[str, Any]:
    """Sub-programa con la estructura del motor a partir de una
    lista de renglones (ala o celda)."""
    total = round(sum(float(r["area_m2"]) for r in renglones), 2)
    return {"nombre": nombre,
            "renglones": [dict(r) for r in renglones],
            "totales": {"area_m2": total,
                        "n_espacios": len(renglones)},
            "avisos": list(avisos or [])}


def _reparte_renglones(programa: Dict[str, Any],
                       pesos: List[float]) \
        -> List[List[Dict[str, Any]]]:
    """Reparte los renglones en N grupos balanceados por área
    (determinista): orden descendente y cada renglón al grupo con más
    déficit respecto a su peso; los HUBS públicos (vestíbulo, entrada,
    sala) van SIEMPRE al grupo 0 (el ala principal), como el lobby de
    las villas de referencia."""
    n = len(pesos)
    total = float(programa["totales"]["area_m2"]) or 1.0
    deficit = [w / max(1e-9, float(sum(pesos))) * total
               for w in pesos]
    grupos: List[List[Dict[str, Any]]] = [[] for _ in range(n)]
    orden = sorted(programa["renglones"],
                   key=lambda r: -float(r["area_m2"]))
    for r in [q for q in orden
              if q.get("space_type") in _HUBS_ZONA]:
        grupos[0].append(r)
        deficit[0] -= float(r["area_m2"])
    for r in [q for q in orden
              if q.get("space_type") not in _HUBS_ZONA]:
        i = max(range(n), key=lambda k: deficit[k])
        grupos[i].append(r)
        deficit[i] -= float(r["area_m2"])
    return grupos


def ajustar_zonas(programa: Dict[str, Any],
                  zonas: List[Dict[str, Any]],
                  altura_nivel_m: float = 3.0,
                  encaje_estricto: bool = True,
                  ajuste: str = "ideal",
                  niveles_deseados: Optional[int] = None,
                  chaflanes: Optional[bool] = None,
                  chaflan_propio: Optional[bool] = None,
                  distribuidora_max_m2: Optional[float] = None) \
        -> Dict[str, Any]:
    """v3.44.0 — MULTI-ALA: reparte UN programa entre N contornos
    (alas) y ajusta cada ala por separado con el mismo motor; el
    conjunto vuelve como análisis COMPUESTO (``tipo: "zonas"``) con
    los totales sumados. Los hubs públicos van al ala principal
    (la primera o la de ``rol: "principal"``). Se aplica con
    ``aplicar_zonas``. Lanza ARQ-DDI-012 con el rol del ala cuando
    una ala no admite su parte del programa.

    ``zonas``: [{"contorno": [...], "rol": "ala norte"}, ...] (rol
    opcional). El reparto es determinista (mismo pedido -> mismo
    plan): renglones por área descendente hacia el ala con más
    déficit de área."""
    if not isinstance(zonas, list) or len(zonas) < 2:
        raise DomainError(
            message="ajustar_zonas necesita 2 o más zonas (alas)",
            code="ARQ-DDI-012",
            context={"zonas": len(zonas) if isinstance(zonas,
                                                      list) else 0},
            suggested_action="Pase una lista de al menos 2 "
                             "contornos: [{\"contorno\": [...], "
                             "\"rol\": \"ala norte\"}, ...]; para un "
                             "contorno único use ajustar().")
    preparadas: List[Tuple[str, Dict[str, Any], float]] = []
    for i, z in enumerate(zonas):
        cont = (z or {}).get("contorno") or []
        rol = str((z or {}).get("rol") or f"ala {i + 1}")
        try:
            forma = inferir([(float(c[0]), float(c[1]))
                             for c in cont])
        except DomainError as exc:
            raise DomainError(
                message=f"ala '{rol}': contorno ilegible ({exc})",
                code="ARQ-DDI-012",
                context={"rol": rol},
                suggested_action="Revise el contorno del ala "
                                 f"'{rol}'.") from exc
        area = float(forma.get("area_m2", 0.0) or 0.0)
        if area <= 0.0:
            raise DomainError(
                message=f"ala '{rol}': área nula o negativa",
                code="ARQ-DDI-012",
                context={"rol": rol, "area_m2": area},
                suggested_action="Dibuje un contorno con área "
                                 f"positiva para el ala '{rol}'.")
        preparadas.append((rol, list(cont), area))
    total_area = float(sum(p[2] for p in preparadas))
    # la ala 'principal' (o la primera) absorbe los hubs
    orden_hub = 0
    for j, (rol, _c, _a) in enumerate(preparadas):
        if rol == "principal":
            orden_hub = j
            break
    pesos = [p[2] for p in preparadas]
    grupos = _reparte_renglones(programa, pesos)
    if orden_hub:
        grupos[0], grupos[orden_hub] = (grupos[orden_hub],
                                        grupos[0])
    salida: List[Dict[str, Any]] = []
    avisos: List[str] = [
        f"MULTI-ALA (v3.44): {len(preparadas)} ala(s) con un total "
        f"de {total_area:.1f} m2; los hubs públicos van al ala "
        f"'{preparadas[orden_hub][0]}'"]
    for j, (rol, cont, area) in enumerate(preparadas):
        renglones = grupos[j]
        if not renglones:
            avisos.append(f"ala '{rol}': sin locales asignados "
                          "(sobrante de área; se deja vacía)")
            continue
        sub = _programa_de_renglones(
            renglones, f"{programa.get('nombre', 'Programa')}"
                       f" · {rol}")
        try:
            aj = ajustar(sub, cont,
                         altura_nivel_m=altura_nivel_m,
                         encaje_estricto=encaje_estricto,
                         seleccion=None,
                         ajuste=ajuste,
                         niveles_deseados=niveles_deseados,
                         chaflanes=chaflanes,
                         chaflan_propio=chaflan_propio,
                         distribuidora_max_m2=distribuidora_max_m2)
        except DomainError as exc:
            raise DomainError(
                message=f"ala '{rol}': {exc}",
                code="ARQ-DDI-012",
                context={"rol": rol,
                         "renglones": [r["nombre"]
                                       for r in renglones]},
                suggested_action="Amplíe el ala, quite locales del "
                                 "programa o reparta entre más "
                                 "alas.") from exc
        salida.append({"rol": rol, "contorno": cont,
                       "area_m2": round(area, 2),
                       "renglones": [r["nombre"]
                                     for r in renglones],
                       "analisis": aj})
    construida = round(sum(
        float(n["area_ocupada"])
        for z in salida for n in z["analisis"]["reparto"]), 2)
    niveles = max((int(z["analisis"]["niveles"]) for z in salida),
                  default=1)
    avisos.extend([a for z in salida
                   for a in z["analisis"].get("avisos", [])
                   if a not in avisos][:12])
    return {
        "tipo": "zonas", "zonas": salida,
        "programa": programa, "niveles": niveles,
        "dentro_del_contorno": all(
            bool(z["analisis"].get("dentro_del_contorno"))
            for z in salida),
        "sala_distribuidora": any(
            bool(z["analisis"].get("sala_distribuidora"))
            for z in salida),
        "chaflanes": [h for z in salida
                      for h in z["analisis"].get("chaflanes", [])],
        "avisos": avisos,
        "totales": {
            "area_programa": round(
                float(programa["totales"]["area_m2"]), 2),
            "area_contorno": round(total_area, 2),
            "area_construida": construida,
            "aprovechamiento_pct": round(
                100.0 * construida / max(0.01, total_area), 2)},
        "altura_nivel_m": float(altura_nivel_m or 3.0)}


def repartir_rejilla(programa_unidad: Dict[str, Any],
                     contorno: List[PT],
                     columnas: int = 3, filas: int = 2,
                     pasillo_m: float = 1.6,
                     altura_nivel_m: float = 3.0,
                     encaje_estricto: bool = True,
                     ajuste: str = "ideal",
                     chaflanes: Optional[bool] = None,
                     chaflan_propio: Optional[bool] = None,
                     distribuidora_max_m2: Optional[float] = None) \
        -> Dict[str, Any]:
    """v3.44.0 — MULTI-UNIDAD (edificio tipo): divide el contorno
    RECTANGULAR en una rejilla de celdas (2 bandas con corredor
    central) y repite la MISMA unidad en cada celda, como la planta
    tipo del edificio plurifamiliar ruso de las imágenes. Cada celda
    se ajusta con el modo sala distribuidora de vivienda. Devuelve un
    compuesto (``tipo: "rejilla"``) con el pasillo central reservado;
    se aplica con ``aplicar_zonas``. ARQ-DDI-012 si el contorno no es
    un rectángulo, la rejilla no cabe o una celda necesita >1
    nivel."""
    columnas = max(1, int(columnas or 1))
    filas = max(1, int(filas or 1))
    if filas != 2:
        raise DomainError(
            message="repartir_rejilla: v3.44 admite filas=2 (dos "
                    "bandas con corredor central)",
            code="ARQ-DDI-012",
            context={"filas": filas},
            suggested_action="Use filas=2 o apile plantas pidiendo "
                             "más niveles en cada unidad.")
    forma = inferir([(float(c[0]), float(c[1]))
                     for c in contorno])
    if forma.get("forma") != "rectangulo":
        raise DomainError(
            message="repartir_rejilla: el contorno debe ser un "
                    "rectángulo (edificio tipo)",
            code="ARQ-DDI-012",
            context={"forma": forma.get("forma")},
            suggested_action="Use un contorno rectangular o divida "
                             "la forma a mano con ajustar_zonas().")
    x0, y0, x1, y1 = forma["bbox"]
    ancho = float(x1 - x0)
    fondo = float(y1 - y0)
    pasillo_m = max(1.2, float(pasillo_m or 1.6))
    banda = (fondo - pasillo_m) / 2.0
    celda_w = ancho / columnas
    if banda < 1.5 or celda_w < 1.5:
        raise DomainError(
            message="repartir_rejilla: las celdas no caben "
                    f"({celda_w:.2f} x {banda:.2f} m con pasillo de "
                    f"{pasillo_m:.2f} m)",
            code="ARQ-DDI-012",
            context={"celda_ancho_m": round(celda_w, 2),
                     "celda_fondo_m": round(banda, 2)},
            suggested_action="Reduzca columnas o pasillo_m, o "
                             "amplíe el contorno.")
    ym0 = y0 + banda
    ym1 = ym0 + pasillo_m
    conts: List[List[Tuple[float, float]]] = []
    for k in range(columnas):
        xa = x0 + k * celda_w
        xb = xa + celda_w
        conts.append([(xa, ym1), (xb, ym1), (xb, y1), (xa, y1)])
    for k in range(columnas):
        xa = x0 + k * celda_w
        xb = xa + celda_w
        conts.append([(xa, y0), (xb, y0), (xb, ym0), (xa, ym0)])
    salida: List[Dict[str, Any]] = []
    avisos: List[str] = [
        f"EDIFICIO TIPO (v3.44): rejilla de {columnas}x{filas} "
        f"celdas de {celda_w:.2f} x {banda:.2f} m con corredor "
        f"central de {pasillo_m:.2f} m; la MISMA unidad se repite "
        "en cada celda"]
    for i, cont in enumerate(conts, start=1):
        sub = _programa_de_renglones(
            programa_unidad["renglones"],
            f"{programa_unidad.get('nombre', 'Unidad')} · celda {i}")
        try:
            aj = ajustar(sub, cont,
                         altura_nivel_m=altura_nivel_m,
                         encaje_estricto=encaje_estricto,
                         seleccion=None,
                         ajuste=ajuste,
                         niveles_deseados=1,
                         chaflanes=chaflanes,
                         chaflan_propio=chaflan_propio,
                         distribuidora_max_m2=distribuidora_max_m2)
        except DomainError as exc:
            raise DomainError(
                message=f"celda {i}: {exc}",
                code="ARQ-DDI-012",
                context={"celda": i,
                         "celda_ancho_m": round(celda_w, 2),
                         "celda_fondo_m": round(banda, 2)},
                suggested_action="Amplíe las celdas (menos columnas "
                                 "o contorno mayor) o simplifique "
                                 "la unidad.") from exc
        if int(aj.get("niveles", 1)) > 1:
            raise DomainError(
                message=f"celda {i}: la unidad necesita "
                        f"{aj['niveles']} niveles (v3.44 repite la "
                        "unidad en UNA planta por celda)",
                code="ARQ-DDI-012",
                context={"celda": i,
                         "niveles": int(aj["niveles"])},
                suggested_action="Amplíe las celdas o reduzca la "
                                 "unidad a una planta.")
        salida.append({"rol": f"celda {i}", "contorno": cont,
                       "area_m2": round(celda_w * banda, 2),
                       "renglones": [r["nombre"] for r in
                                     sub["renglones"]],
                       "analisis": aj})
    central = {
        "codigo": "PASILLO", "nombre": "Pasillo central",
        "space_type": "CORRIDOR", "flujo": "publico",
        "rect": [[x0, ym0], [x1, ym0], [x1, ym1], [x0, ym1]],
        "area_m2": round(ancho * pasillo_m, 2),
        "area_min": 0.0}
    construida = round(sum(
        float(n["area_ocupada"])
        for z in salida for n in z["analisis"]["reparto"]), 2) \
        + float(central["area_m2"])
    avisos.extend([a for z in salida
                   for a in z["analisis"].get("avisos", [])
                   if a not in avisos][:12])
    return {
        "tipo": "rejilla", "zonas": salida,
        "contorno": [[float(p[0]), float(p[1])]
                     for p in contorno],
        "pasillo_central": central,
        "rejilla": {"columnas": columnas, "filas": filas,
                    "pasillo_m": round(pasillo_m, 2),
                    "celda_ancho_m": round(celda_w, 2),
                    "celda_fondo_m": round(banda, 2)},
        "programa": programa_unidad, "niveles": 1,
        "dentro_del_contorno": all(
            bool(z["analisis"].get("dentro_del_contorno"))
            for z in salida),
        "sala_distribuidora": any(
            bool(z["analisis"].get("sala_distribuidora"))
            for z in salida),
        "chaflanes": [h for z in salida
                      for h in z["analisis"].get("chaflanes", [])],
        "avisos": avisos,
        "totales": {
            "area_programa": round(
                float(programa_unidad["totales"]["area_m2"])
                * len(salida) + float(central["area_m2"]), 2),
            "area_contorno": forma["area_m2"],
            "area_construida": construida,
            "aprovechamiento_pct": round(
                100.0 * construida / max(0.01,
                                         float(forma["area_m2"])),
                2)},
        "altura_nivel_m": float(altura_nivel_m or 3.0)}


def aplicar_zonas(ctx: Any, compuesto: Dict[str, Any],
                  opciones: Optional[Dict[str, Any]] = None) \
        -> Dict[str, Any]:
    """v3.44.0: APLICA un compuesto de ``ajustar_zonas`` (multi-ala)
    o ``repartir_rejilla`` (edificio tipo): UN edificio; cada ala es
    su propio nivel con sufijo de rol y, en la rejilla, TODAS las
    celdas y el corredor central comparten la planta. Por los caminos
    oficiales (auditoría, eventos, QTO); el commit lo hace la UI."""
    opc = {
        "nombre_edificio": "Edificio desde dibujo",
        "trazar_muros": False,
        "reemplazar_previo": False,
        "modo": "edificacion",
        "espesor_contorno_m": ESPESOR_CONTORNO_M,
        "espesor_local_m": ESPESOR_LOCAL_M,
        "mobiliario": None,
    }
    opc.update(opciones or {})
    arch = ArchitectureService(ctx)
    avisos = list(compuesto.get("avisos", []))
    reemplazado = ""
    if opc["reemplazar_previo"]:
        previo = edificio_previo(ctx)
        if previo is not None:
            borrado = _elimina_edificio(ctx, arch, previo)
            reemplazado = str(getattr(previo, "code", "")
                              or getattr(previo, "name", ""))
            avisos.append(
                f"edificio anterior reemplazado ({reemplazado}): "
                f"{borrado['espacios']} espacio(s) y "
                f"{borrado['niveles']} nivel(es) eliminados")
    programa = compuesto.get("programa") or {}
    vivienda = _es_vivienda(programa) if programa else False
    amueblar = bool(vivienda) if opc["mobiliario"] is None \
        else bool(opc["mobiliario"])
    es_rejilla = compuesto.get("tipo") == "rejilla"
    edificio = arch.create_building(str(opc["nombre_edificio"]))
    zona = arch.create_zone(
        f"Zona {edificio.name}",
        "SERVICE" if opc["modo"] == "servicio" else "PUBLIC")
    usados_niveles = {lv.name.lower()
                      for lv in ctx.architecture.list(
                          "LEVEL", ctx.project.id)}
    altura = float(compuesto.get("altura_nivel_m", 3.0) or 3.0)
    creados: List[str] = []
    niveles_creados: List[str] = []
    relaciones = 0
    muros = 0
    mob_creados: List[str] = []

    def _plan_a_nivel(plan: Dict[str, Any], nombre_nivel: str,
                      contorno_ala: Optional[List] = None) -> None:
        nonlocal relaciones, muros
        nivel = arch.create_level(
            nombre_nivel,
            elevation_m=round((int(plan["nivel"]) - 1) * altura, 4),
            height_m=altura, building_id=edificio.id)
        niveles_creados.append(nivel.name)
        usados_espacios: set = set()
        central = compuesto.get("pasillo_central") \
            if es_rejilla else None
        piezas = ([central] if central else []) \
            + ([plan["pasillo"]] if plan.get("pasillo") else []) \
            + plan["locales"] \
            + ([plan["escalera"]] if plan["escalera"] else []) \
            + ([plan["patio"]] if plan.get("patio") else [])
        ids_nivel: List[str] = []
        pasillo_code = ""
        for pieza in piezas:
            es_pasillo = pieza["codigo"] == "PASILLO"
            nombre = _nombre_unico(pieza["nombre"], usados_espacios)
            boundary = pieza.get("poligono") or pieza["rect"]
            espacio = arch.create_space(
                nivel.name, nombre, pieza["space_type"],
                [tuple(p) for p in boundary])
            arch.set_space_zone(espacio.id, zona.id)
            ids_nivel.append(espacio.id)
            if es_pasillo and not pasillo_code:
                pasillo_code = espacio.code
            elif pasillo_code:
                arch.add_relationship(espacio.id, pasillo_code,
                                      "adjacent_to",
                                      source=ORIGEN_DESDE_DIBUJO)
                relaciones += 1
            creados.append(espacio.code)
        if amueblar and vivienda:
            from domain import mobiliario as _mob
            try:
                resumen_mob = _mob.generar_mobiliario(
                    ctx, space_ids=ids_nivel, ambito="domestico",
                    densidad="estandar")
                mob_creados.extend(resumen_mob.get("creados", []))
            except Exception as exc:  # noqa: BLE001
                avisos.append(f"mobiliario no pudo colocarse: {exc}")
        if opc["trazar_muros"] and contorno_ala:
            for i in range(len(contorno_ala)):
                a = contorno_ala[i]
                b = contorno_ala[(i + 1) % len(contorno_ala)]
                if math.hypot(float(b[0]) - float(a[0]),
                              float(b[1]) - float(a[1])) < 1e-4:
                    continue
                arch.create_wall(
                    nivel.name, tuple(a), tuple(b),
                    thickness_m=float(opc["espesor_contorno_m"]))
                muros += 1

    zonas = compuesto.get("zonas") or []
    if es_rejilla:
        for plan in zonas[0]["analisis"]["reparto"]:
            nombre_nivel = _nombre_unico(
                f"Planta {plan['nivel']}", usados_niveles)
            _plan_a_nivel(plan, nombre_nivel,
                          [(float(p[0]), float(p[1]))
                           for p in (compuesto.get("contorno")
                                     or [])] or None)
            for z in zonas[1:]:
                for plan_z in z["analisis"]["reparto"]:
                    if int(plan_z["nivel"]) == int(plan["nivel"]):
                        # las demás celdas van en la MISMA planta:
                        # se crean sus locales en el nivel ya hecho
                        usados_espacios: set = set()
                        for pieza in (
                                ([plan_z["pasillo"]]
                                 if plan_z.get("pasillo") else [])
                                + plan_z["locales"]
                                + ([plan_z["escalera"]]
                                   if plan_z["escalera"]
                                   else [])):
                            nombre = _nombre_unico(
                                pieza["nombre"], usados_espacios)
                            boundary = (pieza.get("poligono")
                                        or pieza["rect"])
                            espacio = arch.create_space(
                                nombre_nivel, nombre,
                                pieza["space_type"],
                                [tuple(p) for p in boundary])
                            arch.set_space_zone(espacio.id, zona.id)
                            creados.append(espacio.code)
    else:
        for z in zonas:
            rol = z.get("rol") or "ala"
            cont = [(float(p[0]), float(p[1]))
                    for p in (z.get("contorno") or [])]
            for plan in z["analisis"]["reparto"]:
                base = f"Planta {plan['nivel']}"
                if len(zonas) > 1:
                    base = f"{base} · {rol}"
                nombre_nivel = _nombre_unico(base, usados_niveles)
                _plan_a_nivel(plan, nombre_nivel, cont or None)
    resumen = {
        "edificio": edificio.name,
        "espacios": len(creados), "niveles": len(niveles_creados),
        "niveles_nombres": niveles_creados,
        "relaciones": relaciones, "muros": muros,
        "mobiliario": mob_creados,
        "avisos": avisos}
    if reemplazado:
        resumen["reemplazado"] = reemplazado
    return resumen


# ---------------------------------------------------------------------------
# 13) v3.39.0: EXPLICABILIDAD (spec §32/§33). «¿Por qué este local
#     aquí?» se responde con las reglas registradas por el
#     empaquetado: cero IA, cero magia, texto cp1252.
# ---------------------------------------------------------------------------

def texto_decisiones(analisis: Dict[str, Any]) -> str:
    """Todas las decisiones del ajuste, numeradas y en claro."""
    lineas = ["DECISIONES DEL ASISTENTE (reglas registradas, sin IA)"]
    for i, d in enumerate(analisis.get("decisiones", []), start=1):
        quien = f" [{d['local']}]" if d.get("local") else ""
        lineas.append(f"{i}. {d['tipo']}{quien}: {d['texto']}")
    for aviso in analisis.get("avisos", []):
        lineas.append(f"aviso: {aviso}")
    return "\n".join(lineas)


def explicar_local(analisis: Dict[str, Any], nombre: str) -> str:
    """Respuesta estructurada a «¿por qué colocaste este local
    aquí?» usando las decisiones registradas y el renglón del
    programa (área y relaciones). Lanza ARQ-DDI-008 si no hay
    decisiones para ese nombre."""
    objetivo = str(nombre or "").strip().lower()
    propias = [d for d in analisis.get("decisiones", [])
               if d.get("tipo") == "local"
               and str(d.get("local", "")).strip().lower() == objetivo]
    if not propias:
        raise DomainError(
            message=f"No hay decisiones registradas para el local "
                    f"«{nombre}»",
            code="ARQ-DDI-008",
            context={"local": str(nombre)},
            suggested_action="Ejecute «¿Cabe en el área?» antes de "
                             "preguntar, o revise el nombre del "
                             "local (la lista está en el texto del "
                             "ajuste).")
    lineas = [f"POR QUÉ «{nombre}» ESTÁ AHÍ"]
    for i, d in enumerate(propias, start=1):
        lineas.append(f"{i}. {d['texto']}")
    renglon = None
    for plan in analisis["reparto"]:
        for r in plan["locales"]:
            if str(r["nombre"]).strip().lower() == objetivo:
                renglon = r
                break
        if renglon is not None:
            break
    if renglon is not None:
        req = [str(x) for x in (renglon.get("req") or [])]
        adj = [str(x) for x in (renglon.get("adjacencias") or [])]
        lineas.append(
            f"Área pedida: {float(renglon['area_m2']):.2f} m2 · "
            f"dimensión {float(renglon['ancho_m']):.2f} x "
            f"{float(renglon['fondo_m']):.2f} m")
        if req or adj:
            lineas.append(
                "Relaciones del programa: obligatorias "
                + (", ".join(req) if req else "(ninguna)")
                + "; adyacencias "
                + (", ".join(adj) if adj else "(ninguna)"))
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# 14) v3.39.0: QUICK-SPEC EN UNA LÍNEA (spec §42, sin IA). «3
#     dormitorios, 2 baños, garaje y 2 niveles» se convierte en usos
#     del DNA con cantidades y niveles deseados: regex + diccionario,
#     offline, explicable (lo que no reconoce lo dice).
# ---------------------------------------------------------------------------

_NUMEROS_PALABRA = {"un": 1, "una": 1, "dos": 2, "tres": 3,
                    "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
                    "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
                    "doce": 12}

# palabra normalizada (sin acentos, minúscula) -> código DNA
_QUICK_BASE = {
    "dormitorio": "BEDROOM", "habitacion": "BEDROOM",
    "recamara": "BEDROOM",
    "bano": "BATHROOM", "bano_dato": "BATHROOM",
    "aseo": "LAVATORY", "lavabo": "LAVATORY",
    "cocina": "KITCHEN",
    "sala": "LIVING_ROOM", "estar": "LIVING_ROOM",
    "salon": "LIVING_ROOM",
    "comedor": "DINING_ROOM",
    "garaje": "PARKING", "cochera": "PARKING",
    # v3.43.1: el «patio» de vivienda es el doméstico (4-9 m2, lado
    # 2.0); el PATIO escolar (100-300 m2) queda para los programas de
    # educación por la tabla de usos del asistente
    "patio": "PATIO_DOMESTICO",
    # v3.43.0: el lavadero de VIVIENDA es doméstico (2-4 m2); la
    # lavandería hospitalaria (LAUNDRY, 20-40 m2 con carros) solo
    # llega si se pide «lavandería» explícitamente
    "lavadero": "LAVADERO", "lavanderia": "LAUNDRY",
    "estudio": "OFFICE", "despacho": "OFFICE", "oficina": "OFFICE",
    "recibidor": "ENTRANCE", "entrada": "ENTRANCE",
    "vestibulo": "VESTIBULE", "hall": "VESTIBULE",
    # v3.44.0: LOBBY/foyer -> VESTIBULE (el hall grande de las villas
    # de referencia) y VESTIDOR doméstico (W.I.C / DRESS / closet)
    "lobby": "VESTIBULE", "foyer": "VESTIBULE",
    "vestidor": "VESTIDOR", "wic": "VESTIDOR", "closet": "VESTIDOR",
    "trastero": "STOREROOM", "almacen": "WAREHOUSE",
    "tienda": "RETAIL_LOCAL", "consultorio": "CONSULTATION_ROOM",
    "aula": "CLASSROOM", "habitacion_doble": "BEDROOM",
}

_QUICK_AUTO = {
    "pasillo": "El pasillo de distribución lo reserva el asistente "
               "automáticamente (no se pide en la especificación).",
    "escalera": "La escalera la reserva el asistente cuando el "
                "programa crece de nivel (no se pide en la "
                "especificación).",
}

_PALABRAS_NIVEL = {"nivel", "niveles", "planta", "plantas",
                   "piso", "pisos"}


def _normaliza_palabra(palabra: str) -> str:
    texto = unicodedata.normalize("NFD", str(palabra or "").strip())
    texto = "".join(c for c in texto
                    if not unicodedata.combining(c))
    return texto.lower()


def _diccionario_quick() -> Dict[str, str]:
    """Singular + plurales en -s y -es de cada palabra conocida."""
    dicc: Dict[str, str] = {}
    for base, codigo in _QUICK_BASE.items():
        if base.endswith("_dato") or base.endswith("_doble"):
            continue
        dicc[base] = codigo
        dicc[base + "s"] = codigo
        dicc[base + "es"] = codigo
    return dicc


_QUICK_DICCIONARIO = _diccionario_quick()


def quick_spec(texto: str) -> Dict[str, Any]:
    """Parsea una especificación en lenguaje llano y devuelve usos
    del DNA, niveles deseados y lo que NO reconoció (honesto)."""
    bruto = str(texto or "").strip()
    if not bruto:
        raise DomainError(
            message="Escriba la especificación rápida (por ejemplo: "
                    "3 dormitorios, 2 baños, garaje y 2 niveles)",
            code="ARQ-DDI-002",
            suggested_action="Separe los locales con comas y ponga la "
                             "cantidad delante de cada uso.")
    trozos = re.split(r"[,;]|\s+y\s+|\s+mas\s+", bruto,
                      flags=re.IGNORECASE)
    usos: List[Dict[str, Any]] = []
    desconocidos: List[str] = []
    avisos: List[str] = []
    niveles: Optional[int] = None
    patron = re.compile(
        r"^(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|"
        r"diez|once|doce)\s+(.+)$", re.IGNORECASE)
    for trozo in trozos:
        trozo = trozo.strip()
        if not trozo:
            continue
        m = patron.match(trozo)
        if m:
            crudo = m.group(1).lower()
            cantidad = int(crudo) if crudo.isdigit() \
                else _NUMEROS_PALABRA[crudo]
            resto = m.group(2)
        else:
            cantidad, resto = 1, trozo
        palabra = _normaliza_palabra(resto)
        if palabra in _PALABRAS_NIVEL:
            niveles = max(1, cantidad)
            continue
        if palabra in _QUICK_AUTO:
            avisos.append(_QUICK_AUTO[palabra])
            continue
        codigo = _QUICK_DICCIONARIO.get(palabra)
        if codigo is None:
            desconocidos.append(resto.strip())
            continue
        usos.append({"space_type": codigo,
                     "cantidad": max(1, cantidad),
                     "area_m2": None})
    return {"usos": usos, "niveles": niveles,
            "desconocidos": desconocidos, "avisos": avisos}


def programa_quick(texto: str,
                   nombre: str = "Edificio desde dibujo") \
        -> Dict[str, Any]:
    """Programa completo desde la línea rápida; conserva los deseos
    (niveles_deseados, desconocidos) en ``programa['quick']`` para el
    checklist y los avisos. v3.43.0: el PARKING del quick se llama
    «Garaje» en una vivienda (el «Estacionamiento (cubierta)» del DNA
    es el nombre genérico de los servicios)."""
    qs = quick_spec(texto)
    if not qs["usos"]:
        detalle = (f" (no reconocí: {', '.join(qs['desconocidos'])})"
                   if qs["desconocidos"] else "")
        raise DomainError(
            message=f"No pude reconocer locales en «{texto}»"
                    + detalle,
            code="ARQ-DDI-002",
            suggested_action="Use nombres conocidos: dormitorio, "
                             "habitación, baño, aseo, cocina, sala, "
                             "comedor, garaje, patio, lavadero, "
                             "estudio, despacho, trastero...")
    programa = programa_edificacion(qs["usos"], nombre)
    copias: Dict[str, int] = {}
    for r in programa["renglones"]:
        if r["space_type"] == "PARKING":
            n = copias.get("PARKING", 0) + 1
            copias["PARKING"] = n
            r["nombre"] = "Garaje" if n == 1 else f"Garaje {n}"
    programa["quick"] = {"niveles_deseados": qs["niveles"],
                         "desconocidos": qs["desconocidos"],
                         "avisos": qs["avisos"]}
    return programa


def usos_de_programa(programa: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Reconstruye la tabla de usos (space_type, cantidad, área) a
    partir de los renglones: sirve para restaurar configuraciones
    guardadas y para el estado del asistente."""
    usos: List[Dict[str, Any]] = []
    vistos: Dict[Tuple[str, float], int] = {}
    for r in programa.get("renglones", []):
        tipo = str(r.get("space_type") or r.get("codigo") or "")
        area = float(r.get("area_m2") or 0.0)
        clave = (tipo, round(area, 4))
        if clave in vistos:
            usos[vistos[clave]]["cantidad"] += 1
        else:
            vistos[clave] = len(usos)
            usos.append({"space_type": tipo, "cantidad": 1,
                         "area_m2": area if area > 0 else None})
    return usos


# ---------------------------------------------------------------------------
# 15) v3.39.0: HISTORIAL DE CONFIGURACIONES Y ESTADO GUARDABLE
#     (spec §29 + §30). Cada configuración es la foto de la petición
#     (contorno, programa, opciones) guardada en los ajustes del
#     PROYECTO (tabla settings): se cierra ARQ GEN y se vuelve
#     exactamente al mismo punto. Tope de CONFIGS_MAX fotografías.
# ---------------------------------------------------------------------------

CLAVE_ESTADO_DD = "asistente_dd.estado"
CLAVE_CONFIGS_DD = "asistente_dd.configs"
CONFIGS_MAX = 10


def guardar_estado(ctx: Any, peticion: Optional["PlanRequest"]) -> bool:
    """Guarda el estado ACTUAL del asistente con el proyecto (para
    continuar donde se dejó). No lanza si los ajustes no existen."""
    settings = getattr(ctx, "settings", None)
    if settings is None or peticion is None:
        return False
    try:
        settings.set(CLAVE_ESTADO_DD,
                     json.dumps(peticion.to_dict(), ensure_ascii=True))
        return True
    except (TypeError, ValueError):
        return False


def cargar_estado(ctx: Any) -> Optional["PlanRequest"]:
    """La última petición del asistente guardada en el proyecto (o
    None si nunca se guardó)."""
    settings = getattr(ctx, "settings", None)
    if settings is None:
        return None
    bruto = ""
    try:
        bruto = str(settings.get(CLAVE_ESTADO_DD, "") or "")
    except Exception:  # noqa: BLE001 — ajustes no disponibles
        return None
    if not bruto:
        return None
    try:
        return PlanRequest.from_dict(json.loads(bruto))
    except (ValueError, TypeError) as exc:
        raise DomainError(
            message="El estado guardado del asistente no se puede "
                    "leer (JSON ilegible)",
            code="ARQ-DDI-007",
            suggested_action="Vuelva a configurar el asistente: el "
                             "proyecto no se ha tocado.") from exc


def _configs_de(ctx: Any) -> List[Dict[str, Any]]:
    settings = getattr(ctx, "settings", None)
    if settings is None:
        return []
    try:
        bruto = str(settings.get(CLAVE_CONFIGS_DD, "") or "")
        datos = json.loads(bruto) if bruto else []
        return list(datos) if isinstance(datos, list) else []
    except Exception:  # noqa: BLE001 — historial corrupto se descarta
        return []


def _configs_escribe(ctx: Any, lista: List[Dict[str, Any]]) -> None:
    settings = getattr(ctx, "settings", None)
    if settings is None:
        return
    settings.set(CLAVE_CONFIGS_DD,
                 json.dumps(lista, ensure_ascii=True))


def guardar_configuracion(ctx: Any, peticion: "PlanRequest",
                          analisis: Optional[Dict[str, Any]] = None,
                          etiqueta: str = "") -> Dict[str, Any]:
    """Añade la foto de la configuración al historial del proyecto y
    devuelve la entrada con su índice (para «CONFIGURACIÓN 01»). El
    número de la etiqueta sigue creciendo aunque el tope recorte la
    lista (nunca se repite numeración)."""
    lista = _configs_de(ctx)
    ultimo = 0
    for e in lista:
        try:
            ultimo = max(ultimo, int(str(e.get("etiqueta", ""))
                                     .rsplit(" ", 1)[-1]))
        except (ValueError, IndexError):
            continue
    numero = ultimo + 1
    metricas = None
    if analisis is not None:
        try:
            metricas = metricas_de(analisis, peticion.criterios)
        except Exception:  # noqa: BLE001 — la foto no exige métricas
            metricas = None
    entrada = {
        "etiqueta": etiqueta or f"CONFIGURACIÓN {numero:02d}",
        "fecha": datetime.now().replace(microsecond=0).isoformat(),
        "request": peticion.to_dict(),
        "metricas": metricas,
        "niveles": (int(analisis["niveles"])
                    if analisis and "niveles" in analisis else None)}
    lista.append(entrada)
    if len(lista) > CONFIGS_MAX:
        lista = lista[-CONFIGS_MAX:]
    _configs_escribe(ctx, lista)
    return dict(entrada, indice=len(lista) - 1)


def listar_configuraciones(ctx: Any) -> List[Dict[str, Any]]:
    """El historial completo (etiqueta, fecha, métricas)."""
    return _configs_de(ctx)


def restaurar_configuracion(ctx: Any, indice: int) -> "PlanRequest":
    """La petición guardada en ``indice`` (0..n-1); error amable si
    no existe."""
    lista = _configs_de(ctx)
    if not isinstance(indice, int) or not (0 <= indice < len(lista)):
        raise DomainError(
            message=f"No existe la configuración número {indice}",
            code="ARQ-DDI-006",
            context={"guardadas": len(lista)},
            suggested_action="Elija una de las configuraciones "
                             "guardadas en la lista.")
    return PlanRequest.from_dict(lista[indice].get("request"))


def eliminar_configuracion(ctx: Any, indice: int) -> List[Dict[str, Any]]:
    """Quita la foto ``indice`` del historial y devuelve el resto."""
    lista = _configs_de(ctx)
    if not isinstance(indice, int) or not (0 <= indice < len(lista)):
        raise DomainError(
            message=f"No existe la configuración número {indice}",
            code="ARQ-DDI-006",
            context={"guardadas": len(lista)},
            suggested_action="Elija una de las configuraciones "
                             "guardadas en la lista.")
    lista.pop(indice)
    _configs_escribe(ctx, lista)
    return lista


__all__ = [
    "inferir", "rect_dentro", "contornos_dxf", "programa_edificacion",
    "caja_escalera", "ajustar", "aplicar_plan", "texto_inferencia",
    "texto_ajuste", "texto_resumen_generacion", "explorar_catalogo",
    "texto_exploracion", "ETIQUETA_FORMA",
    "ORIGEN_DESDE_DIBUJO", "ESPESOR_CONTORNO_M", "ESPESOR_LOCAL_M",
    "NIVELES_MAX", "ETIQUETAS_SECTORES_V3",
    # v3.39.0 — desde dibujo reforzado
    "angulos_interiores", "concavidades_de", "autointersecado",
    "validar_contorno", "texto_validacion_contorno", "checklist_previa",
    "texto_checklist", "PlanRequest", "PlanResult", "plan_de",
    "metricas_de", "alternativas", "texto_alternativas",
    "texto_decisiones", "explicar_local", "quick_spec",
    "programa_quick", "usos_de_programa", "guardar_estado",
    "cargar_estado", "guardar_configuracion", "listar_configuraciones",
    "restaurar_configuracion", "eliminar_configuracion",
    "edificio_previo", "AREA_MIN_ERROR_M2", "AREA_MIN_AVISO_M2",
    "AREA_MAX_AVISO_M2", "RELACION_MAX_AVISO", "SEVERIDADES",
    "CLAVE_ULTIMO_EDIFICIO", "CLAVE_ESTADO_DD", "CLAVE_CONFIGS_DD",
    "CONFIGS_MAX", "ETIQUETAS_ALT", "_criterios_def",
]

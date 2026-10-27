"""CUBIERTAS SEGÚN ESTILO, TIPOLOGÍA CONSTRUCTIVA Y ESTRUCTURAL (v3.15.0).

La edificación generada merece TECHO: este motor elige (o respeta) la
tipología de cubierta —plana transitable/no transitable, un agua, dos
aguas y cuatro aguas—, su material de terminación, su estructura
portante y su pendiente, y genera la GEOMETRÍA real sobre el nivel
superior: huella con alero (vuelo de eaves_m), cumbrera, faldones con
su superficie inclinada y remates. El estilo arquitectónico del
asistente la SUGIERE (colonial → teja a dos aguas, racionalista →
plana, sostenible → vegetal transitable...), y todo se recalcula al
regenerar la edificación.

- Entidad ROOF real: auditoría, undo, código ARQ-ROOF-nnn y QTO
  derivado (ROOF_AREA con pendiente, ROOF_PROJECTED_AREA).
- Geometría pura: envolvente convexa (cadena monótona) de los locales
  del nivel superior, offset CONVEXO del alero por intersección de
  rectas paralelas, y faldones resueltos con pendiente constante.
- Cero Tk. Mensajes 100 % codificables en cp1252.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.errors import DomainError
from domain.model import Roof
from domain.diseno_base import (
    alta_entidad, baja_entidad, bbox_de, cerrar_qto, es_generado_diseno,
    lista_tipos, metadata_origen,
)

PT = Tuple[float, float]

# error propio: ARQ-CUB-001 sin edificación para cubrir

TIPOLOGIAS: Tuple[str, ...] = (
    "auto", "plana_transitable", "plana_no_transitable",
    "un_agua", "dos_aguas", "cuatro_aguas",
    "mansarda", "mariposa", "serrena", "ninguna",
)
MATERIALES: Tuple[str, ...] = (
    "auto", "teja_curva", "teja_plana", "pizarra", "chapa_metalica",
    "fibrocemento", "losa_impermeabilizada", "cubierta_vegetal",
)
ESTRUCTURAS: Tuple[str, ...] = ("auto", "madera", "metalica", "hormigon")

ETIQUETA_TIPOLOGIA: Dict[str, str] = {
    "plana_transitable": "plana transitable",
    "plana_no_transitable": "plana no transitable",
    "un_agua": "a un agua",
    "dos_aguas": "a dos aguas",
    "cuatro_aguas": "a cuatro aguas",
    "mansarda": "mansarda (a la francesa)",
    "mariposa": "mariposa (aguas caidas al centro)",
    "serrena": "dientes de sierra",
}
ETIQUETA_MATERIAL: Dict[str, str] = {
    "teja_curva": "teja curva de barro",
    "teja_plana": "teja plana o francesa",
    "pizarra": "pizarra",
    "chapa_metalica": "chapa metálica galvanizada",
    "fibrocemento": "chapa de fibrocemento",
    "losa_impermeabilizada": "losa de hormigón impermeabilizada",
    "cubierta_vegetal": "cubierta vegetal (jardín)",
}
ETIQUETA_ESTRUCTURA: Dict[str, str] = {
    "madera": "par y fatiga + correas de madera",
    "metalica": "cerchas metálicas ligeras + correas",
    "hormigon": "losa/vigas de hormigón armado",
}

# Pendientes por defecto (%): planas casi horizontales con pendiente de
# evacuación; inclinadas según material (teja 30 %, chapa admite menos).
PENDIENTE_DEFECTO: Dict[str, float] = {
    "plana_transitable": 1.5,
    "plana_no_transitable": 2.0,
    "un_agua": 15.0,
    "dos_aguas": 30.0,
    "cuatro_aguas": 30.0,
    "mansarda": 60.0,
    "mariposa": 15.0,
    "serrena": 20.0,
}

# Pendiente MINIMA por material (%): por debajo, el material no
# evacua o no asegura la junta (teja 22, chapa 8). Si el usuario pide
# menos, resolver_parametros sube a la minima y lo avisa.
PENDIENTE_MINIMA: Dict[str, float] = {
    "teja_curva": 22.0,
    "teja_plana": 20.0,
    "pizarra": 20.0,
    "chapa_metalica": 8.0,
    "fibrocemento": 8.0,
    "losa_impermeabilizada": 0.0,
    "cubierta_vegetal": 0.0,
}

MATERIAL_POR_TIPOLOGIA: Dict[str, str] = {
    "plana_transitable": "losa_impermeabilizada",
    "plana_no_transitable": "losa_impermeabilizada",
    "un_agua": "chapa_metalica",
    "dos_aguas": "teja_curva",
    "cuatro_aguas": "teja_plana",
    "mansarda": "teja_plana",
    "mariposa": "chapa_metalica",
    "serrena": "chapa_metalica",
}
ESTRUCTURA_POR_MATERIAL: Dict[str, str] = {
    "teja_curva": "madera",
    "teja_plana": "madera",
    "pizarra": "madera",
    "chapa_metalica": "metalica",
    "fibrocemento": "metalica",
    "losa_impermeabilizada": "hormigon",
    "cubierta_vegetal": "hormigon",
}

# Estilo arquitectónico (asistente) → cubierta sugerida. Los estilos
# sin entrada caen en «plana_no_transitable» (contemporáneo por defecto).
ESTILO_CUBIERTA: Dict[str, Tuple[str, str, float]] = {
    # (tipología, material, pendiente %)
    "Colonial cubano": ("dos_aguas", "teja_curva", 30.0),
    "Vernáculo tropical": ("dos_aguas", "teja_curva", 35.0),
    "Modernista": ("un_agua", "chapa_metalica", 15.0),
    "Neoclásico": ("cuatro_aguas", "teja_plana", 30.0),
    "Ecléctico": ("cuatro_aguas", "teja_curva", 30.0),
    "Posmoderno": ("cuatro_aguas", "teja_plana", 25.0),
    "Orgánico": ("dos_aguas", "teja_curva", 25.0),
    "Sostenible (bioclimático)": ("plana_transitable", "cubierta_vegetal", 1.5),
    "Racionalista": ("plana_no_transitable", "losa_impermeabilizada", 2.0),
    "Brutalista": ("plana_no_transitable", "losa_impermeabilizada", 2.0),
    "Minimalista": ("plana_no_transitable", "losa_impermeabilizada", 2.0),
    "High-tech": ("plana_no_transitable", "chapa_metalica", 2.0),
    "Art déco": ("plana_no_transitable", "losa_impermeabilizada", 2.0),
    "Contemporáneo": ("plana_no_transitable", "losa_impermeabilizada", 2.0),
}


# ---------------------------------------------------------------------------
# geometría pura
# ---------------------------------------------------------------------------

def envolvente_convexa(puntos: Sequence[PT]) -> List[PT]:
    """Envolvente convexa (cadena monótona de Andrew), CCW, sin duplicados."""
    limpios = sorted({(round(float(x), 6), round(float(y), 6))
                      for x, y in puntos})
    if len(limpios) <= 2:
        return list(limpios)

    def _mitad(seq: List[PT]) -> List[PT]:
        cadena: List[PT] = []
        for punto in seq:
            while len(cadena) >= 2:
                (ox, oy), (ax, ay), (bx, by) = cadena[-2], cadena[-1], punto
                cruce = (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)
                if cruce <= 1e-12:
                    cadena.pop()
                else:
                    break
            cadena.append(punto)
        return cadena

    inferior = _mitad(limpios)
    superior = _mitad(list(reversed(limpios)))
    hull = inferior[:-1] + superior[:-1]
    return hull if len(hull) >= 3 else list(limpios)


def _rectas_offset(puntos: Sequence[PT],
                   distancia: float) -> List[Tuple[float, float, float]]:
    """Recta (a, b, c: a·x + b·y = c) paralela a cada arista, DESPLAZADA
    hacia fuera (polígono CCW: normal exterior = rotar la arista -90°)."""
    rectas: List[Tuple[float, float, float]] = []
    n = len(puntos)
    for i in range(n):
        (x1, y1), (x2, y2) = puntos[i], puntos[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        largo = math.hypot(dx, dy)
        if largo <= 1e-9:
            continue
        ux, uy = dx / largo, dy / largo
        # normal exterior de un CCW: (uy, -ux)
        nx, ny = uy, -ux
        a, b = nx, ny
        c = a * x1 + b * y1 + distancia
        rectas.append((a, b, c))
    return rectas


def _cruce(r1: Tuple[float, float, float],
           r2: Tuple[float, float, float]) -> Optional[PT]:
    a1, b1, c1 = r1
    a2, b2, c2 = r2
    denom = a1 * b2 - a2 * b1
    if abs(denom) <= 1e-12:
        return None
    x = (c1 * b2 - c2 * b1) / denom
    y = (a1 * c2 - a2 * c1) / denom
    return (x, y)


def offset_convexo(puntos: Sequence[PT], distancia: float) -> List[PT]:
    """Polígono convexo CCW agrandado «distancia» hacia fuera (alero)."""
    if distancia <= 1e-9 or len(puntos) < 3:
        return list(puntos)
    rectas = _rectas_offset(puntos, distancia)
    n = len(rectas)
    salida: List[PT] = []
    for i in range(n):
        cruce = _cruce(rectas[i], rectas[(i + 1) % n])
        if cruce is not None:
            salida.append(cruce)
    return salida if len(salida) >= 3 else list(puntos)


def area_firmada(puntos: Sequence[PT]) -> float:
    total = 0.0
    n = len(puntos)
    for i in range(n):
        x1, y1 = puntos[i]
        x2, y2 = puntos[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def area_poligono(puntos: Sequence[PT]) -> float:
    return abs(area_firmada(puntos))


def perimetro_poligono(puntos: Sequence[PT]) -> float:
    total = 0.0
    n = len(puntos)
    for i in range(n):
        x1, y1 = puntos[i]
        x2, y2 = puntos[(i + 1) % n]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def resolver_parametros(data: Any = None,
                        tipologia: str = "auto",
                        material: str = "auto",
                        pendiente_pct: float = 0.0,
                        alero_m: Optional[float] = None,
                        estructura: str = "auto") -> Dict[str, Any]:
    """Resuelve (tipología, material, pendiente, alero, estructura).

    «auto» consulta el ESTILO arquitectónico del programa y sus
    defectos; los valores explícitos del usuario ganan siempre.
    """
    if tipologia not in TIPOLOGIAS:
        raise DomainError(
            message=f"Tipología de cubierta desconocida: {tipologia}",
            code="ARQ-CUB-001",
            context={"tipologia": tipologia, "permitidas": list(TIPOLOGIAS)},
            suggested_action="Usa una de: " + ", ".join(TIPOLOGIAS))
    estilo = str(getattr(data, "architectural_style", "") or "") if data else ""
    estilo_tipo, estilo_material, estilo_pend = ESTILO_CUBIERTA.get(
        estilo, ESTILO_CUBIERTA["Contemporáneo"])
    tipologia_resuelta = estilo_tipo if tipologia == "auto" else tipologia
    material_resuelto = estilo_material if material == "auto" else material
    if material_resuelto not in MATERIALES:
        material_resuelto = MATERIAL_POR_TIPOLOGIA.get(tipologia_resuelta,
                                                       "losa_impermeabilizada")
    # el material debe compasar la tipología (plana no lleva teja)
    if tipologia_resuelta.startswith("plana") and material_resuelto in (
            "teja_curva", "teja_plana", "pizarra"):
        material_resuelto = "losa_impermeabilizada"
    if not tipologia_resuelta.startswith("plana") and material_resuelto in (
            "losa_impermeabilizada", "cubierta_vegetal"):
        material_resuelto = MATERIAL_POR_TIPOLOGIA.get(tipologia_resuelta,
                                                       "teja_curva")
    if pendiente_pct and pendiente_pct > 0:
        pendiente = float(pendiente_pct)
    else:
        pendiente = estilo_pend if tipologia == "auto" \
            else PENDIENTE_DEFECTO.get(tipologia_resuelta, 30.0)
    pendiente_ajustada = False
    pendiente_minima = PENDIENTE_MINIMA.get(material_resuelto, 0.0)
    if pendiente < pendiente_minima - 1e-9:
        pendiente = pendiente_minima
        pendiente_ajustada = True
    if alero_m is not None and alero_m > 0:
        alero = float(alero_m)
    elif data is not None and float(getattr(data, "eaves_m", 0.0) or 0.0) > 0:
        alero = float(getattr(data, "eaves_m"))
    else:
        alero = 0.6
    estructura_resuelta = estructura if estructura in ("madera", "metalica",
                                                       "hormigon") else \
        ESTRUCTURA_POR_MATERIAL.get(material_resuelto, "hormigon")
    return {"tipologia": tipologia_resuelta, "material": material_resuelto,
            "pendiente_pct": round(pendiente, 2), "alero_m": alero,
            "estructura": estructura_resuelta,
            "pendiente_ajustada": pendiente_ajustada,
            "pendiente_minima": pendiente_minima}


def parametros_mansarda(semivano: float,
                        pendiente_pct: float) -> Tuple[float, float, float]:
    """Mansarda (a la francesa): DOS pendientes por faldon.

    El codo (quiebro) esta al 55 % del semivano; el faldon bajo lleva
    la pendiente pedida y el alto la MITAD (regla clasica). Devuelve
    (codo_m, altura_codo_m, altura_total_m).
    """
    codo = 0.55 * semivano
    tan1 = math.tan(math.radians(max(pendiente_pct, 1.0)))
    tan2 = math.tan(math.radians(max(pendiente_pct * 0.5, 1.0)))
    h1 = codo * tan1
    total = h1 + (semivano - codo) * tan2
    return (codo, h1, total)


def parametros_serrena(huella: Sequence[PT],
                       pendiente_pct: float) -> Tuple[int, float, float]:
    """Dientes de sierra: n dientes de ~3 m de fondo perpendicular al
    eje largo. Devuelve (n_dientes, fondo_diente_m, altura_m)."""
    minx, miny, maxx, maxy = bbox_de(list(huella))
    ancho_x, alto_y = maxx - minx, maxy - miny
    corto = min(ancho_x, alto_y)
    n = max(1, int(round(corto / 3.0)))
    fondo_diente = corto / n
    altura = fondo_diente * math.tan(math.radians(max(pendiente_pct, 1.0)))
    return (n, fondo_diente, altura)


def _cumbrera_para(huella: Sequence[PT], tipologia: str,
                   pendiente_frac: float) -> Tuple[
        Optional[Tuple[PT, PT]], float]:
    """Cumbrera (2 puntos) y altura sobre el nivel para la tipología.

    La cumbrera corre por el EJE LARGO del recinto; en cuatro aguas se
    acorta en ambos extremos el semiancho perpendicular (quincha a 45°
    en planta, como toda agua simple).
    """
    minx, miny, maxx, maxy = bbox_de(list(huella))
    ancho_x, alto_y = maxx - minx, maxy - miny
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    vertical = alto_y > ancho_x        # cumbrera corre en Y
    semivano = (ancho_x if vertical else alto_y) / 2.0
    altura = semivano * pendiente_frac
    if tipologia == "un_agua":
        altura = semivano * 2.0 * pendiente_frac
        if vertical:
            return ((minx, maxy), (maxx, maxy)), altura  # borde superior alto
        return ((minx, maxy), (minx, miny)), altura     # borde izquierdo alto
    if tipologia == "mariposa":
        # las aguas CAEN al centro: el eje es el VALLE y la altura es
        # la de los aleros sobre el
        if vertical:
            return ((cx, miny), (cx, maxy)), altura
        return ((minx, cy), (maxx, cy)), altura
    if tipologia == "mansarda":
        _codo, _h1, total = parametros_mansarda(
            semivano, pendiente_frac * 100.0)
        altura = total
        largo = (alto_y if vertical else ancho_x)
        if vertical:
            return ((cx, cy - largo / 2.0), (cx, cy + largo / 2.0)), altura
        return ((cx - largo / 2.0, cy), (cx + largo / 2.0, cy)), altura
    if tipologia == "serrena":
        # sin cumbrera continua: n crestas paralelas al eje largo
        return None, parametros_serrena(list(huella),
                                        pendiente_frac * 100.0)[2]
    largo = (alto_y if vertical else ancho_x)
    if tipologia == "cuatro_aguas":
        largo = max(largo - 2.0 * semivano, 0.30 * largo)
    if vertical:
        ridge = ((cx, cy - largo / 2.0), (cx, cy + largo / 2.0))
    else:
        ridge = ((cx - largo / 2.0, cy), (cx + largo / 2.0, cy))
    return ridge, altura


def superficie_cubierta(roof: Any) -> Dict[str, float]:
    """Superficies DERIVADAS de la geometría guardada (QTO spec 52).

    ``area_proyectada`` es la huella con alero; ``area_inclinada`` la
    superficie REAL de faldones con la pendiente guardada (aproximación
    de pendiente constante, válida para estimación temprana).
    """
    huella = [tuple(p) for p in (getattr(roof, "footprint", []) or [])]
    if len(huella) < 3:
        return {"area_proyectada": 0.0, "area_inclinada": 0.0,
                "perimetro": 0.0}
    proyectada = area_poligono(huella)
    pendiente = float(getattr(roof, "pendiente_pct", 0.0) or 0.0)
    tipologia = str(getattr(roof, "tipologia", "") or "")
    if tipologia == "mansarda":
        # dos pendientes por faldon: promedio ponderado por el codo
        minx, miny, maxx, maxy = bbox_de(huella)
        semivano = min(maxx - minx, maxy - miny) / 2.0
        codo, _h1, _tot = parametros_mansarda(semivano, pendiente)
        tan1 = math.tan(math.radians(max(pendiente, 1.0)))
        tan2 = math.tan(math.radians(max(pendiente * 0.5, 1.0)))
        f1 = math.sqrt(1.0 + tan1 * tan1)
        f2 = math.sqrt(1.0 + tan2 * tan2)
        factor = (codo * f1 + (semivano - codo) * f2) / max(semivano, 1e-9)
    else:
        factor = math.sqrt(1.0 + (pendiente / 100.0) ** 2)
    return {
        "area_proyectada": round(proyectada, 3),
        "area_inclinada": round(proyectada * factor, 3),
        "perimetro": round(perimetro_poligono(huella), 3),
    }


# ---------------------------------------------------------------------------
# generación en el proyecto
# ---------------------------------------------------------------------------

def _nivel_superior_con_espacios(ctx: Any) -> Tuple[Optional[Any], List[Any]]:
    niveles = lista_tipos(ctx, "LEVEL")
    niveles.sort(key=lambda lv: (float(getattr(lv, "elevation_m", 0.0) or 0.0),
                                 str(getattr(lv, "name", ""))))
    espacios = lista_tipos(ctx, "SPACE")
    for nivel in reversed(niveles):
        propios = [e for e in espacios if e.level_id == nivel.id
                   and len(getattr(e, "boundary", []) or []) >= 3
                   and str(e.space_type or "").upper() not in ("PATIO",)]
        if propios:
            return nivel, propios
    return (None, []) if niveles else (None, [])


def quitar_cubierta(ctx: Any) -> List[str]:
    bajas: List[str] = []
    for cubierta in lista_tipos(ctx, "ROOF"):
        codigo = cubierta.code
        baja_entidad(ctx, "ROOF", cubierta.id)
        bajas.append(codigo)
    return bajas


def generar_cubierta(ctx: Any, data: Any = None,
                     tipologia: str = "auto", material: str = "auto",
                     pendiente_pct: float = 0.0,
                     alero_m: Optional[float] = None,
                     estructura: str = "auto",
                     altura_base_m: Optional[float] = None,
                     con_qto: bool = True) -> Dict[str, Any]:
    """Cubre la edificación: UNA ROOF sobre el nivel superior con
    espacios. Idempotente (quita la generada antes).

    ``altura_base_m`` (v3.17.0) fija la COTA de implantación de la
    cubierta sobre el datum del proyecto (0.00 = planta baja): None
    o <= 0 la apoya sobre el top de los muros del nivel cubierto
    (comportamiento clásico); un valor explícito la deja a esa cota,
    más alta (planta nueva, ático retranqueado) o más baja (mansarda
    enterrada), con aviso amable si queda por debajo del top.
    """
    resumen: Dict[str, Any] = {"operacion": "cubierta", "creados": [],
                               "eliminados": [], "avisos": [], "qto": None}
    nivel, espacios = _nivel_superior_con_espacios(ctx)
    if nivel is None or not espacios:
        resumen["avisos"].append(
            "No hay locales que cubrir: genera antes la edificación.")
        return resumen
    resumen["eliminados"] = quitar_cubierta(ctx)
    if tipologia == "ninguna":
        resumen["avisos"].append(
            "Cubierta sin tipología («ninguna»): solo se retiró la "
            "anterior.")
        return resumen
    parametros = resolver_parametros(data, tipologia=tipologia,
                                     material=material,
                                     pendiente_pct=pendiente_pct,
                                     alero_m=alero_m, estructura=estructura)
    # COTA DE IMPLANTACIÓN (v3.17.0): None/<=0 = sobre los muros.
    cota_base: Optional[float] = None
    if altura_base_m is not None:
        cota = float(altura_base_m)
        if cota > 500.0:
            raise DomainError(
                message="La cota de la cubierta no puede superar 500 m",
                code="ARQ-CUB-002",
                context={"altura_base_m": cota},
                suggested_action="Usa una cota entre 0 y 500 m sobre "
                                 "el datum del proyecto.")
        if cota > 0:
            cota_base = round(cota, 4)
            top_muros = (float(getattr(nivel, "elevation_m", 0.0) or 0.0)
                         + float(getattr(nivel, "height_m", 3.0) or 3.0))
            if cota_base < top_muros - 0.05:
                resumen["avisos"].append(
                    f"la base de la cubierta queda a {cota_base:.2f} m, "
                    f"{top_muros - cota_base:.2f} m por debajo del top "
                    f"de los muros del nivel «{getattr(nivel, 'name', '')}»")
    parametros["altura_base_m"] = cota_base
    if parametros.get("pendiente_ajustada"):
        resumen["avisos"].append(
            f"pendiente subida al {parametros['pendiente_pct']:.0f} %: "
            "es la minima que asegura el material elegido")
    puntos = [tuple(p) for espacio in espacios for p in espacio.boundary]
    hull = envolvente_convexa(puntos)
    huella = offset_convexo(hull, parametros["alero_m"])
    ridge = None
    altura = 0.0
    if not parametros["tipologia"].startswith("plana"):
        ridge, altura = _cumbrera_para(
            huella, parametros["tipologia"],
            parametros["pendiente_pct"] / 100.0)
    extra_meta: Dict[str, Any] = {
        "estilo": str(getattr(data, "architectural_style", "")
                      if data else ""),
        "niveles_cubiertos": len(espacios)}
    if parametros["tipologia"] == "serrena":
        n_dientes, _fondo, _alt = parametros_serrena(
            huella, parametros["pendiente_pct"])
        extra_meta["dientes"] = n_dientes
    if cota_base is not None:
        extra_meta["altura_base_m"] = cota_base
    entidad = Roof(
        project_id=ctx.project.id,
        code=ctx.next_code("ARCHITECTURE", "ROOF"),
        level_id=nivel.id,
        tipologia=parametros["tipologia"], material=parametros["material"],
        estructura=parametros["estructura"],
        pendiente_pct=parametros["pendiente_pct"],
        alero_m=parametros["alero_m"], altura_cumbrera_m=round(altura, 4),
        footprint=[(round(x, 4), round(y, 4)) for x, y in huella],
        ridge=((round(ridge[0][0], 4), round(ridge[0][1], 4)),
               (round(ridge[1][0], 4), round(ridge[1][1], 4)))
        if ridge else None,
        metadata=metadata_origen(
            "cubierta del asistente", extra_meta))
    alta_entidad(ctx, entidad)
    resumen["creados"].append(entidad.code)
    resumen["parametros"] = parametros
    resumen["superficie"] = superficie_cubierta(entidad)
    if con_qto:
        cerrar_qto(ctx, resumen)
    return resumen


def cota_base_cubierta(cubierta: Any, nivel_base_z: float,
                       nivel_altura_m: float) -> float:
    """Cota Z de la BASE de la cubierta (aleros o fondo de losa).

    La metadata ``altura_base_m`` manda cuando es > 0 (v3.17.0);
    si no, la cubierta nace sobre el top de los muros de su nivel
    (``nivel_base_z + nivel_altura_m``), el comportamiento clásico
    de v3.15.0/v3.16.0 corregido: antes nacía en el PISO del nivel y
    quedaba enterrada dentro de la edificación.
    """
    meta = getattr(cubierta, "metadata", {}) or {}
    try:
        cota = float(meta.get("altura_base_m", 0.0) or 0.0)
    except (TypeError, ValueError):
        cota = 0.0
    if cota > 0:
        return cota
    return float(nivel_base_z or 0.0) + float(nivel_altura_m or 0.0)


def cubierta_actual(ctx: Any) -> Optional[Any]:
    cubiertas = lista_tipos(ctx, "ROOF")
    return cubiertas[0] if cubiertas else None


def resumen_texto(resumen: Dict[str, Any]) -> str:
    """Línea cp1252 con el resultado (o el estado de la cubierta)."""
    if resumen.get("parametros"):
        p = resumen["parametros"]
        texto = (f"Cubierta {ETIQUETA_TIPOLOGIA.get(p['tipologia'], p['tipologia'])}"
                 f" de {ETIQUETA_MATERIAL.get(p['material'], p['material'])}"
                 f" al {p['pendiente_pct']:.0f} %"
                 f" ({ETIQUETA_ESTRUCTURA.get(p['estructura'], p['estructura'])})")
        if p.get("altura_base_m"):
            texto += f"; base a {float(p['altura_base_m']):.2f} m"
        sup = resumen.get("superficie") or {}
        if sup.get("area_inclinada"):
            texto += (f"; {sup['area_inclinada']:.1f} m2 reales"
                      f" ({sup['area_proyectada']:.1f} m2 en planta)")
        partes = [texto]
    else:
        partes = ["Cubierta"]
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} ROOF creada")
    if resumen.get("eliminados"):
        partes.append(f"{len(resumen['eliminados'])} baja(s)")
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


__all__ = [
    "TIPOLOGIAS", "MATERIALES", "ESTRUCTURAS", "ESTILO_CUBIERTA",
    "PENDIENTE_DEFECTO", "PENDIENTE_MINIMA", "ETIQUETA_TIPOLOGIA",
    "ETIQUETA_MATERIAL", "ETIQUETA_ESTRUCTURA", "envolvente_convexa",
    "offset_convexo", "area_poligono", "perimetro_poligono",
    "resolver_parametros", "parametros_mansarda", "parametros_serrena",
    "superficie_cubierta", "generar_cubierta", "quitar_cubierta",
    "cota_base_cubierta", "cubierta_actual", "resumen_texto",
]

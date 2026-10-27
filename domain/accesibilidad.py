"""SOLUCIÓN A BARRERAS ARQUITECTÓNICAS (v3.15.0).

«la solución a barreras arquitectónicas con rampas, barandas etc.»:
este módulo AUDITA la edificación contra reglas de accesibilidad
(inspiradas en el CTE DB-SUA1/2 y en el mobiliario de Neufert) y
APLICA soluciones generativas reales:

- Analizar: puertas < 0.80 m libres, pasillos < 1.00 m (1.20 social),
  escaleras fuera de Blondel/contrahuella/huella y sin barandilla,
  desniveles de piso sin rampa y baños sin círculo de giro de 1.50 m.
- Aplicar: barandillas en las escaleras, barandilla DOBLE (0.65 +
  0.95 m) a ambos lados de las rampas, barras de apoyo junto a los
  inodoros y la rampa de entrada que resuelve el desnivel del terreno
  (pendiente máxima 10 % con Δh ≤ 0.5 m, 8 % hasta 1.0 m y 6 % hasta
  2.0 m; más de 2.0 m pide ascensor o montaplatas).

Todo son entidades reales (RAMP y HANDRAIL: auditoría, undo,
códigos ARQ-RAMP/ARQ-HANDRAIL, QTO con RAMP_AREA/RAMP_LENGTH/
HANDRAIL_LENGTH) y la regeneración de la edificación las re-crea.
Cero Tk. Mensajes 100 % codificables en cp1252.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.errors import DomainError
from domain.model import Handrail, Ramp
from domain.diseno_base import (
    alta_entidad, baja_entidad, bbox_de, cota_piso_de, cerrar_qto,
    es_generado_diseno, lista_tipos, metadata_origen,
)

PT = Tuple[float, float]

# errores propios:
#   ARQ-ACC-001  parámetros de accesibilidad fuera de rango

# -- normativa (CTE DB-SUA1/2, valores resumidos y verificables) --------
ANCHO_PUERTA_MIN_M = 0.80      # ancho libre de puerta de local utilizable
ANCHO_PASILLO_MIN_M = 1.00     # itinerario accesible (doméstico)
ANCHO_PASILLO_SOCIAL_M = 1.20  # itinerario en edificación de uso público
ANCHO_RAMPA_MIN_M = 1.20       # ancho libre de rampa
TRAMO_RAMPA_MAX_M = 10.0       # longitud horizontal máxima por tramo
MESETA_RAMPA_M = 1.50          # reposo/meseta al final de cada tramo
ALTO_BARANDILLA_M = 0.90       # barandilla de escalera
ALTO_PASAMANOS_RAMPA_M = 0.95  # pasamanos alto de rampa
ALTO_PASAMANOS_SECUNDARIO_M = 0.65  # pasamanos bajo (silla de ruedas)
ALTO_BARRA_APOYO_M = 0.75      # barra de apoyo junto a inodoro
LARGO_BARRA_APOYO_M = 0.70
CIRCULO_GIRO_M = 1.50          # círculo de giro en aseos
CONTRAHUELLA_MAX_M = 0.175     # escalera: contrahuella
HUELLA_MIN_M = 0.28            # escalera: huella
BLONDEL_MIN_M = 0.545          # 2·CH + H mínimo
BLONDEL_MAX_M = 0.735
DESNIVEL_MIN_RAMPA_M = 0.05    # menos que esto: pequeño salto tolerable

RAMPA_TABLA: Tuple[Tuple[float, float], ...] = (
    # (desnivel máximo del tramo, pendiente máxima %)
    (0.50, 10.0), (1.00, 8.0), (2.00, 6.0),
)
DESNIVEL_MAX_RAMPA_M = 2.00


def pendiente_maxima_rampa(desnivel_m: float) -> Optional[float]:
    """Pendiente máxima (%) admisible para un desnivel; None si el
    desnivel exige ascensor/montaplata (DB-SUA1 tabla 4.1)."""
    for limite, pendiente in RAMPA_TABLA:
        if desnivel_m <= limite + 1e-9:
            return pendiente
    return None


def geometria_rampa(desnivel_m: float, ancho_m: float = ANCHO_RAMPA_MIN_M,
                    pendiente_pct: Optional[float] = None) -> Dict[str, Any]:
    """Resuelve la geometría de UNA rampa para el desnivel dado.

    Devuelve {length_m, slope_pct, tramos, mesetas, pide_ascensor}.
    La pendiente pedida se recorta a la máxima admisible y el desarrollo
    se parte en tramos de ≤ 10 m con mesetas de 1.50 m (la longitud
    total incluye las mesetas intermedias).
    """
    if desnivel_m < 0 or ancho_m <= 0:
        raise DomainError(
            message="El desnivel y el ancho de la rampa deben ser positivos",
            code="ARQ-ACC-001",
            context={"desnivel_m": desnivel_m, "ancho_m": ancho_m},
            suggested_action="Revisa el desnivel del piso del local.")
    maxima = pendiente_maxima_rampa(desnivel_m)
    if maxima is None:
        return {"length_m": 0.0, "slope_pct": 0.0, "tramos": 0,
                "mesetas": 0, "pide_ascensor": True}
    pendiente = min(float(pendiente_pct), maxima) if pendiente_pct else maxima
    desarrollo = desnivel_m / (pendiente / 100.0)
    tramos = max(1, math.ceil(desarrollo / TRAMO_RAMPA_MAX_M - 1e-9))
    mesetas = max(0, tramos - 1)
    longitud_total = desarrollo + mesetas * MESETA_RAMPA_M
    return {"length_m": round(longitud_total, 3),
            "slope_pct": round(pendiente, 2),
            "tramos": tramos, "mesetas": mesetas, "pide_ascensor": False}


# -- chequeos -------------------------------------------------------------

@dataclass
class Chequeo:
    codigo: str
    titulo: str
    estado: str          # cumple | aviso | incumple
    detalle: str
    sugerencia: str = ""
    entidad: str = ""    # "TIPO:id" de referencia

    def linea(self) -> str:
        marca = {"cumple": "[OK]   ", "aviso": "[AVISO]", "incumple": "[MAL]  "}
        return f"{marca.get(self.estado, '[   ]')} {self.codigo} {self.titulo}: {self.detalle}"


def _uso_social(ctx: Any) -> bool:
    from domain.mobiliario import AMBITO_POR_DEFECTO_SOCIAL, ambito_auto
    for edificio in lista_tipos(ctx, "BUILDING"):
        meta = getattr(edificio, "metadata", {}) or {}
        edif = meta.get("edificacion", {})
        if isinstance(edif, dict) and edif.get("uso_social"):
            return str(edif["uso_social"]) in AMBITO_POR_DEFECTO_SOCIAL
    return ambito_auto() == "social"


def _min_dim_de(espacio: Any) -> float:
    minx, miny, maxx, maxy = bbox_de(espacio.boundary)
    return max(0.0, min(maxx - minx, maxy - miny))


def _proyecto_en_segmento(p: PT, a: PT, b: PT) -> Tuple[PT, float]:
    ax, ay = b[0] - a[0], b[1] - a[1]
    largo2 = ax * ax + ay * ay
    if largo2 <= 1e-12:
        return a, 0.0
    t = ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / largo2
    t = max(0.0, min(1.0, t))
    return (a[0] + t * ax, a[1] + t * ay), t


def _aristas(boundary: Sequence[PT]) -> List[Tuple[PT, PT]]:
    n = len(boundary)
    return [(tuple(boundary[i]), tuple(boundary[(i + 1) % n]))
            for i in range(n)]


def _borde_mas_cercano(punto: PT, boundary: Sequence[PT]) -> Tuple[PT, PT]:
    mejor: Tuple[PT, PT] = _aristas(boundary)[0]
    mejor_d = 1e18
    for arista in _aristas(boundary):
        pie, _t = _proyecto_en_segmento(punto, arista[0], arista[1])
        d = math.hypot(pie[0] - punto[0], pie[1] - punto[1])
        if d < mejor_d:
            mejor_d, mejor = d, arista
    return mejor


def analizar_barreras(ctx: Any) -> List[Chequeo]:
    """Auditoría de barreras arquitectónicas de la edificación abierta."""
    chequeos: List[Chequeo] = []
    social = _uso_social(ctx)
    pasillo_min = ANCHO_PASILLO_SOCIAL_M if social else ANCHO_PASILLO_MIN_M
    pid = ctx.project.id

    # 1. Puertas: ancho libre mínimo.
    puertas_malas: List[str] = []
    for puerta in lista_tipos(ctx, "DOOR"):
        if float(puerta.width_m) + 1e-9 < ANCHO_PUERTA_MIN_M:
            puertas_malas.append(f"{puerta.code} ({puerta.width_m:.2f} m)")
    if puertas_malas:
        chequeos.append(Chequeo(
            "ARQ-ACC-101", "Ancho libre de puertas", "incumple",
            f"{len(puertas_malas)} puerta(s) con menos de "
            f"{ANCHO_PUERTA_MIN_M:.2f} m: {', '.join(puertas_malas[:4])}"
            + ("..." if len(puertas_malas) > 4 else ""),
            "Edítalas a 0.80 m o más (0.90 m en la principal)."))
    else:
        chequeos.append(Chequeo(
            "ARQ-ACC-101", "Ancho libre de puertas", "cumple",
            "Todas las puertas superan los 0.80 m libres."))

    # 2. Pasillos e itinerarios.
    pasillos_malos: List[str] = []
    for espacio in lista_tipos(ctx, "SPACE"):
        if str(espacio.space_type or "").upper() != "CORRIDOR":
            continue
        estrecho = _min_dim_de(espacio)
        if estrecho + 1e-9 < pasillo_min:
            pasillos_malos.append(f"{espacio.name} ({estrecho:.2f} m)")
    if pasillos_malos:
        chequeos.append(Chequeo(
            "ARQ-ACC-102", "Ancho de pasillos", "aviso",
            f"{len(pasillos_malos)} pasillo(s) por debajo de "
            f"{pasillo_min:.2f} m: {', '.join(pasillos_malos[:4])}",
            "Sube el ancho del pasillo en la regeneración."))
    else:
        chequeos.append(Chequeo(
            "ARQ-ACC-102", "Ancho de pasillos", "cumple",
            f"Pasillos con {pasillo_min:.2f} m o más."))

    # 3. Escaleras: Blondel + barandilla presente.
    barandillas_por_espacio: Dict[str, int] = {}
    for rail in lista_tipos(ctx, "HANDRAIL"):
        if rail.kind == "barandilla" and rail.space_id:
            barandillas_por_espacio[rail.space_id] = \
                barandillas_por_espacio.get(rail.space_id, 0) + 1
    escaleras_problema: List[str] = []
    escaleras_sin_barandilla: List[str] = []
    for espacio in lista_tipos(ctx, "SPACE"):
        if str(espacio.space_type or "").upper() != "STAIR":
            continue
        req = (getattr(espacio, "metadata", {}) or {}).get(
            "requerimientos", {})
        arquitectonicos = req.get("arquitectonicos", {}) \
            if isinstance(req, dict) else {}
        try:
            ch = float(arquitectonicos.get("contrahuella_m", 0.0) or 0.0)
            huella = float(arquitectonicos.get("huella_m", 0.0) or 0.0)
        except (TypeError, ValueError):
            ch = huella = 0.0
        if ch > 0:
            blondel = 2.0 * ch + huella
            if (ch > CONTRAHUELLA_MAX_M + 1e-9 or huella + 1e-9 < HUELLA_MIN_M
                    or not (BLONDEL_MIN_M - 1e-9 <= blondel
                            <= BLONDEL_MAX_M + 1e-9)):
                escaleras_problema.append(
                    f"{espacio.name} (CH {ch:.3f} / H {huella:.2f})")
        if barandillas_por_espacio.get(espacio.id, 0) == 0:
            escaleras_sin_barandilla.append(espacio.name)
    if escaleras_problema:
        chequeos.append(Chequeo(
            "ARQ-ACC-103", "Escaleras (Blondel/contrahuella)", "aviso",
            "Escalera(s) fuera de rango: "
            + ", ".join(escaleras_problema[:3]),
            f"CH <= {CONTRAHUELLA_MAX_M:.3f} m, huella >= "
            f"{HUELLA_MIN_M:.2f} m, Blondel 0.545-0.735 m."))
    else:
        chequeos.append(Chequeo(
            "ARQ-ACC-103", "Escaleras (Blondel/contrahuella)", "cumple",
            "Contrahuellas, huellas y Blondel dentro de rango."))
    if escaleras_sin_barandilla:
        chequeos.append(Chequeo(
            "ARQ-ACC-104", "Barandillas de escalera", "incumple",
            "Sin barandilla: " + ", ".join(escaleras_sin_barandilla[:4]),
            "Pulsa «Aplicar soluciones»: coloca barandilla a 0.90 m "
            "en ambos lados."))
    else:
        chequeos.append(Chequeo(
            "ARQ-ACC-104", "Barandillas de escalera", "cumple",
            "Toda escalera tiene barandilla."))

    # 4. Desniveles de piso sin rampa.
    rampas_por_espacio: Dict[str, int] = {}
    for rampa in lista_tipos(ctx, "RAMP"):
        if rampa.space_id:
            rampas_por_espacio[rampa.space_id] = \
                rampas_por_espacio.get(rampa.space_id, 0) + 1
    desniveles: List[str] = []
    for espacio in lista_tipos(ctx, "SPACE"):
        cota = cota_piso_de(espacio)
        if cota > DESNIVEL_MIN_RAMPA_M \
                and rampas_por_espacio.get(espacio.id, 0) == 0:
            datos = geometria_rampa(cota)
            if datos["pide_ascensor"]:
                desniveles.append(f"{espacio.name} "
                                  f"(+{cota:.2f} m: pide ascensor)")
            else:
                desniveles.append(
                    f"{espacio.name} (+{cota:.2f} m: rampa de "
                    f"{datos['length_m']:.1f} m al {datos['slope_pct']:.0f} %)")
    if desniveles:
        chequeos.append(Chequeo(
            "ARQ-ACC-105", "Desniveles sin rampa", "incumple",
            "; ".join(desniveles[:4]),
            "«Aplicar soluciones» genera la rampa con su barandilla "
            "doble."))
    else:
        chequeos.append(Chequeo(
            "ARQ-ACC-105", "Desniveles sin rampa", "cumple",
            "Sin desniveles de piso sin resolver."))

    # 5. Círculo de giro en aseos (uso social).
    if social:
        aseos_justos: List[str] = []
        for espacio in lista_tipos(ctx, "SPACE"):
            if str(espacio.space_type or "").upper() in ("BATHROOM",
                                                         "LAVATORY"):
                if _min_dim_de(espacio) + 1e-9 < CIRCULO_GIRO_M:
                    aseos_justos.append(
                        f"{espacio.name} ({_min_dim_de(espacio):.2f} m)")
        if aseos_justos:
            chequeos.append(Chequeo(
                "ARQ-ACC-106", "Círculo de giro en aseos", "aviso",
                "Aseo(s) sin giro de 1.50 m: "
                + ", ".join(aseos_justos[:4]),
                "Amplía el aseo o destina uno accesible por planta."))
        else:
            chequeos.append(Chequeo(
                "ARQ-ACC-106", "Círculo de giro en aseos", "cumple",
                "Los aseos admiten el círculo de giro de 1.50 m."))
    return chequeos


# -- soluciones generativas ------------------------------------------------

def _barandilla_de_recinto(espacio: Any, altura: float,
                           secundaria: float, kind: str,
                           nota: str) -> List[Handrail]:
    """DOS barandillas paralelas a los lados LARGOS del recinto."""
    boundary = [tuple(p) for p in espacio.boundary]
    minx, miny, maxx, maxy = bbox_de(boundary)
    ancho_x, alto_y = maxx - minx, maxy - miny
    vertical = alto_y > ancho_x        # el desarrollo corre en Y
    jiron = 0.06                       # pegada al muro, sin comerse el paso
    polilineas: List[List[PT]] = []
    if vertical:
        for x in (minx + jiron, maxx - jiron):
            polilineas.append([(x, miny), (x, maxy)])
    else:
        for y in (miny + jiron, maxy - jiron):
            polilineas.append([(minx, y), (maxx, y)])
    entidades: List[Handrail] = []
    for puntos in polilineas:
        entidades.append(Handrail(
            project_id=espacio.project_id,
            code="",           # el que llama asigna el código definitivo
            level_id=espacio.level_id, space_id=espacio.id,
            kind=kind, points=puntos, altura_m=altura,
            altura_secundaria_m=secundaria,
            metadata=metadata_origen(nota)))
    return entidades


def _barandillas_de_rampa(rampa: Ramp, altura: float,
                          secundaria: float) -> List[Handrail]:
    """Barandilla DOBLE a ambos lados de la huella de la rampa.

    Los dos lados LARGOS de la huella se eligen por longitud total
    (robusto ante cualquiera de las dos ordenaciones de esquinas)."""
    corners = [tuple(p) for p in rampa.corners]
    if len(corners) < 4:
        return []

    def _largo(a: PT, b: PT) -> float:
        return math.hypot(b[0] - a[0], b[1] - a[1])

    par_a = ((corners[0], corners[3]), (corners[1], corners[2]))
    par_b = ((corners[0], corners[1]), (corners[3], corners[2]))
    total_a = sum(_largo(s, e) for s, e in par_a)
    total_b = sum(_largo(s, e) for s, e in par_b)
    lados = par_a if total_a >= total_b else par_b
    entidades: List[Handrail] = []
    for (p1, p2) in lados:
        entidades.append(Handrail(
            project_id=rampa.project_id, code="",
            level_id=rampa.level_id, space_id=rampa.space_id,
            kind="barandilla_rampa", points=[p1, p2], altura_m=altura,
            altura_secundaria_m=secundaria,
            metadata=metadata_origen("barandilla doble de rampa (DB-SUA1)")))
    return entidades


def quitar_soluciones(ctx: Any, con_cubiertas: bool = False
                      ) -> Dict[str, List[str]]:
    """Baja las rampas/barandillas GENERADAS (lo manual se conserva)."""
    from domain.diseno_base import es_editado_a_mano
    bajas: Dict[str, List[str]] = {"RAMP": [], "HANDRAIL": []}
    for tipo in ("RAMP", "HANDRAIL"):
        for entidad in lista_tipos(ctx, tipo):
            if not es_generado_diseno(entidad):
                continue
            if es_editado_a_mano(entidad):
                continue
            codigo = entidad.code
            baja_entidad(ctx, tipo, entidad.id)
            bajas[tipo].append(codigo)
    return bajas


def aplicar_soluciones(ctx: Any, data: Any = None,
                       con_qto: bool = True) -> Dict[str, Any]:
    """Genera las soluciones: barandillas de escalera, rampas de
    desnivel con su barandilla doble y barras de apoyo en los aseos.

    Idempotente: antes quita las soluciones generadas por este motor
    (lo editado a mano sobrevive). Devuelve resumen con conteo,
    chequeos y avisos.
    """
    resumen: Dict[str, Any] = {"operacion": "accesibilidad",
                               "creados": [], "eliminados": [],
                               "conteo": {}, "avisos": [], "qto": None,
                               "chequeos": []}
    bajas = quitar_soluciones(ctx)
    resumen["eliminados"] = bajas["RAMP"] + bajas["HANDRAIL"]
    nivel_por_id = {lv.id: lv for lv in lista_tipos(ctx, "LEVEL")}
    espacios = {e.id: e for e in lista_tipos(ctx, "SPACE")}

    # 1) Barandillas de escalera (ambos lados del hueco).
    for espacio in lista_tipos(ctx, "SPACE"):
        if str(espacio.space_type or "").upper() != "STAIR":
            continue
        for rail in _barandilla_de_recinto(
                espacio, ALTO_BARANDILLA_M, 0.0, "barandilla",
                "barandilla de escalera (0.90 m, DB-SUA2)"):
            rail.code = ctx.next_code("ARCHITECTURE", "HANDRAIL")
            alta_entidad(ctx, rail)
            resumen["creados"].append(rail.code)
        resumen["conteo"]["barandillas_escalera"] = \
            resumen["conteo"].get("barandillas_escalera", 0) + 2

    # 2) Rampa de entrada donde haya desnivel de piso (terreno).
    for espacio in lista_tipos(ctx, "SPACE"):
        cota = cota_piso_de(espacio)
        if cota <= DESNIVEL_MIN_RAMPA_M:
            continue
        datos = geometria_rampa(cota)
        if datos["pide_ascensor"]:
            resumen["avisos"].append(
                f"{espacio.name}: desnivel de {cota:.2f} m: exige "
                "ascensor o montaplata (no rampa).")
            continue
        corners = _corners_rampa_entrada(espacio, datos["length_m"])
        if corners is None:
            resumen["avisos"].append(
                f"{espacio.name}: no hay borde libre para la rampa.")
            continue
        rampa = Ramp(
            project_id=ctx.project.id,
            code=ctx.next_code("ARCHITECTURE", "RAMP"),
            level_id=espacio.level_id, space_id=espacio.id,
            corners=corners, width_m=ANCHO_RAMPA_MIN_M,
            length_m=datos["length_m"], desnivel_m=cota,
            slope_pct=datos["slope_pct"],
            metadata=metadata_origen(
                "rampa de desnivel de piso",
                {"tramos": datos["tramos"], "mesetas": datos["mesetas"]}))
        alta_entidad(ctx, rampa)
        resumen["creados"].append(rampa.code)
        resumen["conteo"]["rampas"] = \
            resumen["conteo"].get("rampas", 0) + 1
        for rail in _barandillas_de_rampa(rampa, ALTO_PASAMANOS_RAMPA_M,
                                          ALTO_PASAMANOS_SECUNDARIO_M):
            rail.code = ctx.next_code("ARCHITECTURE", "HANDRAIL")
            alta_entidad(ctx, rail)
            resumen["creados"].append(rail.code)
        resumen["conteo"]["barandillas_rampa"] = \
            resumen["conteo"].get("barandillas_rampa", 0) + 2

    # 3) Barras de apoyo junto a los inodoros.
    for espacio in lista_tipos(ctx, "SPACE"):
        if str(espacio.space_type or "").upper() not in ("BATHROOM",
                                                         "LAVATORY"):
            continue
        inodoros = [p for p in lista_tipos(ctx, "FURNITURE")
                    if p.space_id == espacio.id and p.kind == "inodoro"]
        for inodoro in inodoros:
            try:
                borde = _borde_mas_cercano((inodoro.x, inodoro.y),
                                           espacio.boundary)
            except Exception:  # noqa: BLE001 - contorno degenerado
                continue
            pie, _t = _proyecto_en_segmento((inodoro.x, inodoro.y),
                                            borde[0], borde[1])
            dx, dy = borde[1][0] - borde[0][0], borde[1][1] - borde[0][1]
            largo = math.hypot(dx, dy)
            if largo <= 1e-6:
                continue
            ux, uy = dx / largo, dy / largo
            mitad = min(LARGO_BARRA_APOYO_M / 2.0, largo / 2.0 - 0.02)
            if mitad <= 0.05:
                continue
            barra = Handrail(
                project_id=ctx.project.id,
                code=ctx.next_code("ARCHITECTURE", "HANDRAIL"),
                level_id=espacio.level_id, space_id=espacio.id,
                kind="barra_apoyo",
                points=[(pie[0] - ux * mitad, pie[1] - uy * mitad),
                        (pie[0] + ux * mitad, pie[1] + uy * mitad)],
                altura_m=ALTO_BARRA_APOYO_M, altura_secundaria_m=0.0,
                metadata=metadata_origen(
                    "barra de apoyo junto a inodoro (0.75 m, DB-SUA2)"))
            alta_entidad(ctx, barra)
            resumen["creados"].append(barra.code)
        if inodoros:
            resumen["conteo"]["barras_apoyo"] = \
                resumen["conteo"].get("barras_apoyo", 0) + len(inodoros)

    resumen["chequeos"] = [c.linea() for c in analizar_barreras(ctx)]
    if con_qto:
        cerrar_qto(ctx, resumen)
    return resumen


def _corners_rampa_entrada(espacio: Any, largo: float
                           ) -> Optional[List[PT]]:
    """Huella de la rampa FUERA del local, sobre su borde más largo."""
    boundary = [tuple(p) for p in espacio.boundary]
    minx, miny, maxx, maxy = bbox_de(boundary)
    ancho_x, alto_y = maxx - minx, maxy - miny
    ancho = ANCHO_RAMPA_MIN_M
    if ancho_x >= alto_y:
        # entrada por la cara INFERIOR (y = miny), centrada
        cx = (minx + maxx) / 2.0
        medio = min(ancho / 2.0, ancho_x / 2.0 - 0.05)
        return [(cx - medio, miny), (cx + medio, miny),
                (cx + medio, miny - largo), (cx - medio, miny - largo)]
    medio = min(ancho / 2.0, alto_y / 2.0 - 0.05)
    cy = (miny + maxy) / 2.0
    return [(minx, cy - medio), (minx, cy + medio),
            (minx - largo, cy + medio), (minx - largo, cy - medio)]


def resumen_texto(resumen: Dict[str, Any]) -> str:
    partes = ["Accesibilidad"]
    conteo = resumen.get("conteo") or {}
    if conteo:
        partes.append(", ".join(f"{clave} x{n}"
                                for clave, n in sorted(conteo.items())))
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} pieza(s) creadas")
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


__all__ = [
    "Chequeo", "ANCHO_PUERTA_MIN_M", "ANCHO_PASILLO_MIN_M",
    "ANCHO_PASILLO_SOCIAL_M", "ANCHO_RAMPA_MIN_M", "TRAMO_RAMPA_MAX_M",
    "MESETA_RAMPA_M", "CIRCULO_GIRO_M", "ALTO_BARANDILLA_M",
    "pendiente_maxima_rampa", "geometria_rampa", "analizar_barreras",
    "aplicar_soluciones", "quitar_soluciones", "resumen_texto",
]

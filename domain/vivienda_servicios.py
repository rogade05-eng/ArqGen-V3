"""Servicios exteriores y sistemas de la vivienda (v3.30.0).

Integra las secciones 39 (DOMÓTICA), 45 (PISCINA) y 46 (ACÚSTICA) del
documento «Especificaciones técnicas Viviendas.txt» como datos
versionados bajo ``resources/knowledge/vivienda_servicios.json`` —
nunca hardcodeados.

Tres motores de SOLO LECTURA sobre el proyecto:

1. PISCINA (§45): calculadora independiente del edificio — volumen,
   renovación y caudal de filtración, skimmers, impulsión, bomba,
   iluminación, checklist de seguridad y equipos de referencia en CUP.
   El §45 lo pide: «La piscina debe tratarse como sistema
   independiente de la vivienda».

2. ACÚSTICA (§46): identifica fuentes (COCINA, BAÑOS, EQUIPOS, CALLES,
   VECINOS) frente a DORMITORIOS midiendo los MUROS COMPARTIDOS del
   trazado y establece AISLAMIENTO_REQUERIDO, MATERIAL, ESPESOR,
   DOBLE_TABIQUE, AISLAMIENTO_CUBIERTA y VIDRIO_ACUSTICO de
   referencia.

3. DOMÓTICA (§39): plan por SISTEMAS (8) con ELEMENTOS (SENSORES,
   ACTUADORES, CONTROLADORES...) contados sobre el modelo; RED, PANEL
   de cuadro y ALIMENTACION quedan como diseño (REQUIERE_CALCULO).

Honradez técnica: los valores numéricos del JSON son de referencia
constructiva (el documento no trae cifras); los estados de los
hallazgos distinguen medido / pendiente / requiere cálculo, igual que
el resto de los motores del dominio. Sólo LEE el proyecto: no crea
entidades ni necesita commit.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from math import ceil
from typing import Any, Dict, List, Optional, Tuple

from app.paths import resource_path
from core.errors import DomainError

_CACHE: List["ServiciosVivienda"] = []

# estados de los hallazgos (mismo lenguaje que vivienda_specs)
MEDIDO = "medido"
PENDIENTE = "pendiente"
REQUIERE_CALCULO = "requiere calculo"

# tipos técnicos que no son fuente ruidosa habitable (reutilizado del
# DNA de vivienda: pasillo, patio, escalera, núcleo)
_TECNICOS_CIRCULACION = ("CORRIDOR", "STAIR")
_TIPOS_TECNICOS = ("CORRIDOR", "PATIO", "STAIR", "CORE")

# nombres de zonas verdes reconocidas para RIEGO
_ZONAS_VERDES_TIPO = ("GARDEN", "TERRACE", "PATIO", "YARD")
_ZONAS_VERDES_NOMBRE = ("jardin", "jardín", "patio", "terraza",
                        "verde")

# tipologías de vivienda que implican medianera con vecinos
_TIPOLOGIAS_MEDIANERA = ("pareada", "adosada", "dúplex", "duplex",
                         "multifamiliar", "edificio", "continua")


class HallazgoS(dict):
    """Hallazgo de los servicios de vivienda (dict serializable)."""

    def __init__(self, codigo: str, severidad: str, mensaje: str,
                 estado: str = MEDIDO) -> None:
        super().__init__(codigo=codigo, severidad=severidad,
                         mensaje=mensaje, estado=estado,
                         fuente="Especificaciones técnicas Viviendas "
                                "(§39/§45/§46)")


@dataclass
class ServiciosVivienda:
    """Registro versionado del JSON de servicios."""

    version: str = ""
    fuente_doc: str = ""
    advertencia: str = ""
    principio: Dict[str, Any] = field(default_factory=dict)
    piscina: Dict[str, Any] = field(default_factory=dict)
    acustica: Dict[str, Any] = field(default_factory=dict)
    domotica: Dict[str, Any] = field(default_factory=dict)
    fuentes: List[str] = field(default_factory=list)

    @staticmethod
    def load_file(path: str) -> "ServiciosVivienda":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("format") != "ARQ_GEN_VIVIENDA_SERVICIOS":
            raise DomainError(
                message="El archivo de servicios de vivienda no tiene "
                        "el formato esperado",
                code="ARQ-VSR-001",
                context={"format": data.get("format")},
                suggested_action="Restaure resources/knowledge/"
                                 "vivienda_servicios.json del paquete.")
        return ServiciosVivienda(
            version=str(data.get("version", "")),
            fuente_doc=str(data.get("source", "")),
            advertencia=str(data.get("advertencia", "")),
            principio=dict(data.get("principio_seguridad", {})),
            piscina=dict(data.get("piscina", {})),
            acustica=dict(data.get("acustica", {})),
            domotica=dict(data.get("domotica", {})),
            fuentes=list(data.get("fuentes", [])),
        )

    def resumen(self) -> Dict[str, int]:
        return {
            "parametros_piscina": len(self.piscina.get("parametros",
                                                       [])),
            "equipos_piscina": len(self.piscina.get("equipos_ref", [])),
            "soluciones_acusticas": len(self.acustica.get("soluciones",
                                                          {})),
            "sistemas_domotica": len(self.domotica.get("reglas", [])),
            "reglas_domotica": sum(
                len(r.get("elementos", []))
                for r in self.domotica.get("reglas", [])),
        }


def cargar_servicios() -> Optional[ServiciosVivienda]:
    """Carga (una vez) el registro; None si falta el recurso.

    Sin el recurso el programa sigue funcionando: los servicios
    aconsejan, no bloquean (mismo criterio que el catálogo §27).
    """
    if _CACHE:
        return _CACHE[0]
    try:
        path = resource_path("knowledge", "vivienda_servicios.json")
        if not os.path.exists(path):
            return None
        registro = ServiciosVivienda.load_file(path)
        _CACHE.append(registro)
        return registro
    except Exception:  # noqa: BLE001 — recurso dañado: sin servicios
        return None


def _registro() -> ServiciosVivienda:
    registro = cargar_servicios()
    if registro is None:
        raise DomainError(
            message="No se encontró el registro de servicios de "
                    "vivienda",
            code="ARQ-VSR-002",
            suggested_action="Verifique resources/knowledge/"
                             "vivienda_servicios.json.")
    return registro


def _resumen_de(hallazgos: List[dict]) -> Dict[str, int]:
    resumen = {"ok": 0, "avisos": 0, "fallos": 0, "pendientes": 0}
    for h in hallazgos:
        if h.get("estado") != MEDIDO:
            resumen["pendientes"] += 1
        elif h["severidad"] == "ok":
            resumen["ok"] += 1
        elif h["severidad"] == "aviso":
            resumen["avisos"] += 1
        elif h["severidad"] == "fallo":
            resumen["fallos"] += 1
        else:
            resumen["pendientes"] += 1
    return resumen


def _miles(valor: float) -> str:
    """Formatea con espacio de miles (estilo del comparador)."""
    return f"{valor:,.0f}".replace(",", " ")


# ======================================================================
# PISCINA (§45)
# ======================================================================

def calcular_piscina(largo: float, ancho: float, prof_min: float,
                     prof_max: float, altura_m: float = 0.0,
                     renovacion_h: float = 0.0,
                     registro: Optional[ServiciosVivienda] = None) \
        -> Dict[str, Any]:
    """Dimensiona la piscina como SISTEMA INDEPENDIENTE (§45).

    Errores amables (DomainError): medidas no positivas o
    profundidad mínima mayor que la máxima. Los avisos de rango van
    en los hallazgos, no como error.
    """
    reg = registro or _registro()
    pis = reg.piscina
    try:
        largo = float(largo)
        ancho = float(ancho)
        prof_min = float(prof_min)
        prof_max = float(prof_max)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            message="Las medidas de la piscina deben ser números",
            code="ARQ-PIS-001", suggested_action="Use coma o punto "
            "decimal; las medidas van en metros.") from exc
    if largo <= 0 or ancho <= 0 or prof_min <= 0 or prof_max <= 0:
        raise DomainError(
            message="Las medidas del vaso deben ser positivas",
            code="ARQ-PIS-001",
            context={"largo": largo, "ancho": ancho,
                     "prof_min": prof_min, "prof_max": prof_max},
            suggested_action="Revise largo, ancho y profundidades.")
    if prof_min > prof_max:
        raise DomainError(
            message="La profundidad mínima no puede superar la máxima",
            code="ARQ-PIS-002",
            context={"prof_min": prof_min, "prof_max": prof_max})
    renov_cfg = pis.get("renovacion_horas", {})
    renovacion = float(renovacion_h or 0.0) or \
        float(renov_cfg.get("por_defecto", 6.0))
    bomba_cfg = pis.get("bomba", {})
    altura = float(altura_m or 0.0) or \
        float(bomba_cfg.get("altura_manometrica_m", 10.0))

    h: List[dict] = []
    prof_media = (prof_min + prof_max) / 2.0
    lamina = largo * ancho
    volumen = lamina * prof_media
    caudal = volumen / renovacion          # m3/h
    q_m3s = caudal / 3600.0
    potencia_kw = (1000.0 * 9.81 * q_m3s * altura
                   / float(bomba_cfg.get("rendimiento", 0.55))) / 1000.0
    skimmers = ceil(lamina / float(pis.get("skimmers", {})
                                   .get("m2_por_unidad", 35.0)))
    impulsores = ceil(lamina / float(pis.get("impulsores", {})
                                     .get("m2_por_unidad", 25.0)))
    focos = ceil(lamina / float(pis.get("iluminacion", {})
                                .get("m2_por_foco", 20.0)))

    # hallazgos honestos ------------------------------------------------
    rango = pis.get("profundidad", {})
    if prof_max < float(rango.get("min_m", 0.8)):
        h.append(HallazgoS(
            "PI001", "aviso",
            f"profundidad máxima {prof_max:.2f} m por debajo de la "
            f"referencia {float(rango.get('min_m', 0.8)):.1f} m: vaso "
            "para niños, sin zona de nado", PENDIENTE))
    elif prof_max > float(rango.get("max_m", 2.5)):
        h.append(HallazgoS(
            "PI001", "aviso",
            f"profundidad máxima {prof_max:.2f} m por encima de la "
            f"referencia {float(rango.get('max_m', 2.5)):.1f} m: vaso "
            "de salto, diseño aparte", PENDIENTE))
    else:
        h.append(HallazgoS("PI001", "ok",
                           f"vaso {largo:.2f} x {ancho:.2f} m con "
                           f"profundidades {prof_min:.2f}-{prof_max:.2f} "
                           f"m dentro de la referencia "
                           f"({rango.get('min_m', 0.8)}-"
                           f"{rango.get('max_m', 2.5)} m)"))
    if float(renov_cfg.get("min", 4.0)) <= renovacion <= \
            float(renov_cfg.get("max", 8.0)):
        h.append(HallazgoS("PI002", "ok",
                           f"renovación total cada {renovacion:.1f} h: "
                           f"caudal de filtración {caudal:.2f} m3/h "
                           f"para {volumen:.1f} m3 de agua"))
    else:
        h.append(HallazgoS("PI002", "aviso",
                           f"renovación {renovacion:.1f} h fuera de la "
                           "referencia "
                           f"({renov_cfg.get('min', 4.0)}-"
                           f"{renov_cfg.get('max', 8.0)} h): caudal "
                           f"{caudal:.2f} m3/h"))
    h.append(HallazgoS("PI003", "ok",
                       f"{skimmers} skimmer(s) para {lamina:.1f} m2 de "
                       "lámina (referencia 1 por "
                       f"{pis.get('skimmers', {}).get('m2_por_unidad', 35)} "
                       "m2)"))
    h.append(HallazgoS("PI004", "ok",
                       f"{impulsores} boquilla(s) de impulsión para "
                       "barrer el fondo hacia los skimmers"))
    ref_kw = float(bomba_cfg.get("kW_maximo_referencia", 0.5))
    if potencia_kw <= ref_kw:
        h.append(HallazgoS("PI005", "ok",
                           f"bomba estimada {potencia_kw:.2f} kW con "
                           f"H = {altura:.1f} m: la bomba de referencia "
                           f"de {ref_kw} kW alcanza"))
    else:
        h.append(HallazgoS("PI005", "aviso",
                           f"bomba estimada {potencia_kw:.2f} kW con "
                           f"H = {altura:.1f} m: la de referencia "
                           f"({ref_kw} kW) NO alcanza, elija tamaño "
                           "mayor"))
    equi = pis.get("equipotencialidad", {})
    h.append(HallazgoS("PI006", "info",
                       str(equi.get("texto", "")), REQUIERE_CALCULO))
    dren = pis.get("drenaje", {})
    h.append(HallazgoS("PI007", "info",
                       str(dren.get("texto", "")), PENDIENTE))
    h.append(HallazgoS("PI008", "aviso",
                       "seguridad del §45 (checklist): " + "; ".join(
                           pis.get("seguridad", [])), PENDIENTE))
    h.append(HallazgoS("PI009", "ok",
                       f"{focos} foco(s) LED submarino(s) (referencia 1 "
                       f"por {pis.get('iluminacion', {}).get('m2_por_foco', 20)} "
                       "m2 de lámina)"))

    # equipos de referencia en CUP ---------------------------------------
    codigos = {e["codigo"]: e for e in pis.get("equipos_ref", [])}

    def _fila(codigo: str, cantidad: float) -> Dict[str, Any]:
        eq = codigos[codigo]
        precio = float(eq.get("precio_cup", 0.0))
        return {"codigo": codigo, "descripcion": eq["descripcion"],
                "unidad": eq["unidad"], "cantidad": round(cantidad, 2),
                "precio_cup": precio,
                "subtotal_cup": round(precio * cantidad, 2)}

    filas = [
        _fila("PIS-BOMBA", 1),
        _fila("PIS-FILTRO", 1),
        _fila("PIS-SKIM", skimmers),
        _fila("PIS-IMPUL", impulsores),
        _fila("PIS-FOCO", focos),
        _fila("PIS-CERCA", round(2.0 * (largo + ancho), 2)),
        _fila("PIS-ALARMA", 1),
    ]
    total = round(sum(f["subtotal_cup"] for f in filas), 2)
    tablas = [{
        "titulo": "Equipos de referencia del §45 (CUP, sin instalación)",
        "cabeceras": ["Código", "Descripción", "Cantidad", "Unidad",
                      "Precio CUP", "Subtotal CUP"],
        "filas": [[f["codigo"], f["descripcion"],
                   f"{f['cantidad']:g}", f["unidad"],
                   _miles(f["precio_cup"]), _miles(f["subtotal_cup"])]
                  for f in filas]
        + [["", "", "", "", "TOTAL", _miles(total)]],
    }]

    return {
        "edificacion": "Piscina (sistema independiente del §45)",
        "vaso": {"largo_m": largo, "ancho_m": ancho,
                 "prof_min_m": prof_min, "prof_max_m": prof_max,
                 "prof_media_m": round(prof_media, 3),
                 "lamina_m2": round(lamina, 2),
                 "volumen_m3": round(volumen, 2)},
        "filtracion": {"renovacion_h": renovacion,
                       "caudal_m3_h": round(caudal, 3),
                       "altura_m": altura,
                       "bomba_kw": round(potencia_kw, 3)},
        "hallazgos": h,
        "resumen": _resumen_de(h),
        "equipos": filas,
        "tablas": tablas,
        "total_equipos_cup": total,
        "nota_precios": "Equipos de REFERENCIA sin calidad ni marca, "
                        "en CUP, sin instalación ni mano de obra.",
        "advertencia": reg.advertencia,
        "principio_seguridad": reg.principio,
        "fuentes": reg.fuentes,
        "catalogo": reg.resumen(),
    }


def texto_piscina(informe: Dict[str, Any]) -> str:
    """Informe de piscina listo para consola (cp1252, sin flechas)."""
    lineas: List[str] = ["PISCINA (Especificaciones técnicas Viviendas "
                         "§45)"]
    vaso = informe.get("vaso", {})
    lineas.append(
        f"vaso {vaso.get('largo_m', 0):.2f} x {vaso.get('ancho_m', 0):.2f} m, "
        f"profundidad {vaso.get('prof_min_m', 0):.2f}-"
        f"{vaso.get('prof_max_m', 0):.2f} m "
        f"(media {vaso.get('prof_media_m', 0):.2f} m)")
    lineas.append(f"lámina {vaso.get('lamina_m2', 0):.1f} m2, "
                  f"volumen {vaso.get('volumen_m3', 0):.1f} m3")
    fil = informe.get("filtracion", {})
    lineas.append(f"filtración: renovación {fil.get('renovacion_h', 0):.1f} h, "
                  f"caudal {fil.get('caudal_m3_h', 0):.2f} m3/h, bomba "
                  f"estimada {fil.get('bomba_kw', 0):.2f} kW con H = "
                  f"{fil.get('altura_m', 0):.1f} m")
    lineas.append("")
    for x in informe.get("hallazgos", []):
        marca = {"ok": "[OK]", "fallo": "[X]", "aviso": "[!]",
                 "info": "[i]"}.get(x["severidad"], "[?]")
        estado = {"medido": "", "pendiente": " (pendiente)",
                  "requiere calculo":
                      " (REQUIERE_CALCULO_ESPECIALIZADO)"}.get(
            x.get("estado", ""), "")
        lineas.append(f"{marca} {x['codigo']}: {x['mensaje']}{estado}")
    resumen = informe.get("resumen", {})
    lineas.append("")
    lineas.append(f"Resumen: {resumen.get('ok', 0)} cumplen, "
                  f"{resumen.get('avisos', 0)} avisos, "
                  f"{resumen.get('fallos', 0)} fallos, "
                  f"{resumen.get('pendientes', 0)} pendientes o de "
                  "cálculo.")
    lineas.append("")
    lineas.append("Equipos de referencia (CUP, sin instalación):")
    for f in informe.get("equipos", []):
        lineas.append(
            f"· {f['codigo']} {f['descripcion']}: {f['cantidad']:g} "
            f"{f['unidad']} x {_miles(f['precio_cup'])} = "
            f"{_miles(f['subtotal_cup'])} CUP")
    lineas.append(f"TOTAL equipos: {_miles(informe.get('total_equipos_cup', 0.0))} "
                  "CUP")
    lineas.append("")
    lineas.append(str(informe.get("advertencia") or ""))
    return "\n".join(lineas)


# ======================================================================
# helpers de lectura del modelo (sólo lectura)
# ======================================================================

def _lista(ctx: Any, kind: str) -> List[Any]:
    getter = getattr(ctx, "architecture", None)
    if getter is None:
        return []
    try:
        return list(getter.list(kind, ctx.project.id))
    except Exception:  # noqa: BLE001
        return []


def _punto_en_borde(p: Tuple[float, float],
                    boundary: List[Tuple[float, float]],
                    eps: float = 1e-6) -> bool:
    """Respaldo legado: punto sobre el borde del polígono."""
    n = len(boundary)
    for i in range(n):
        ax, ay = boundary[i]
        bx, by = boundary[(i + 1) % n]
        px, py = p
        dx, dy = bx - ax, by - ay
        largo2 = dx * dx + dy * dy
        if largo2 <= 1e-12:
            dista = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy)
                             / largo2))
            cx, cy = ax + dx * t, ay + dy * t
            dista = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
        if dista <= eps:
            return True
    return False


def _area(espacio: Any) -> float:
    """Área por fórmula del shoelace (sólo lectura)."""
    boundary = [tuple(p) for p in getattr(espacio, "boundary", []) or []]
    if len(boundary) < 3:
        return 0.0
    total = 0.0
    n = len(boundary)
    for i in range(n):
        x1, y1 = boundary[i]
        x2, y2 = boundary[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _muro_de(muros: List[Any], wall_id: str) -> Optional[Any]:
    for m in muros:
        if str(getattr(m, "id", "")) == str(wall_id):
            return m
    return None


# solape mínimo (m) para considerar que un muro/arista sirve a un local
_SOLAPE_MIN_M = 0.05


def _aristas(local: Any) -> List[Tuple[Tuple[float, float],
                                       Tuple[float, float]]]:
    boundary = [tuple(p) for p in getattr(local, "boundary", []) or []]
    if len(boundary) < 3:
        return []
    return [(boundary[i], boundary[(i + 1) % len(boundary)])
            for i in range(len(boundary))]


def _solape_segmentos(a1: Tuple[float, float], a2: Tuple[float, float],
                      b1: Tuple[float, float], b2: Tuple[float, float],
                      tol: float = 1e-6) -> float:
    """Longitud de solape (m) entre dos segmentos COLINEALES.

    0 si no son colineales o no se solapan: evita los falsos vecinos
    por esquina y sirve con muros largos que atraviesan varios locales.
    """
    ax, ay = a1
    dx, dy = a2[0] - ax, a2[1] - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return 0.0
    largo = l2 ** 0.5
    c1 = (b1[0] - ax) * dy - (b1[1] - ay) * dx
    c2 = (b2[0] - ax) * dy - (b2[1] - ay) * dx
    if abs(c1) / largo > tol or abs(c2) / largo > tol:
        return 0.0  # no están sobre la misma recta
    t1 = ((b1[0] - ax) * dx + (b1[1] - ay) * dy) / l2
    t2 = ((b2[0] - ax) * dx + (b2[1] - ay) * dy) / l2
    lo, hi = (t1, t2) if t1 <= t2 else (t2, t1)
    lo = max(0.0, lo)
    hi = min(1.0, hi)
    if hi <= lo:
        return 0.0
    return (hi - lo) * largo


def _seg_muro(muro: Any) -> Optional[Tuple[Tuple[float, float],
                                           Tuple[float, float]]]:
    try:
        return (tuple(muro.start), tuple(muro.end))
    except Exception:  # noqa: BLE001
        return None


def _solape_con_local(seg: Tuple[Tuple[float, float],
                                 Tuple[float, float]], local: Any) -> float:
    """Mayor solape del segmento con las aristas del local (m)."""
    mejor = 0.0
    for e1, e2 in _aristas(local):
        s = _solape_segmentos(seg[0], seg[1], e1, e2)
        if s > mejor:
            mejor = s
    return mejor


def _locales_bajo(seg: Tuple[Tuple[float, float],
                             Tuple[float, float]],
                  vivos: List[Any]) -> List[Any]:
    """Locales cuya frontera coincide con el segmento (>= 5 cm)."""
    return [s for s in vivos
            if _solape_con_local(seg, s) >= _SOLAPE_MIN_M]


def _es_interior(muro: Any, vivos: List[Any]) -> bool:
    """True si el muro sirve de frontera a >= 2 locales."""
    seg = _seg_muro(muro)
    if seg is None:
        return False
    return len(_locales_bajo(seg, vivos)) >= 2


def _comparten_borde(a: Any, b: Any) -> float:
    """Longitud (m) de la arista que comparten dos locales, o 0."""
    mejor = 0.0
    for e1a, e1b in _aristas(a):
        for e2a, e2b in _aristas(b):
            s = _solape_segmentos(e1a, e1b, e2a, e2b)
            if s > mejor:
                mejor = s
    return mejor


def _vano_perimetral(vano: Any, muros: List[Any], vivos: List[Any]) \
        -> bool:
    """True si el vano da al EXTERIOR del programa.

    Se prueba el TROZO de muro alrededor del punto medio del vano
    (media anchura más 5 cm a cada lado): si ese trozo sólo sirve a un
    local (o a ninguno), el vano está en fachada. Así una puerta de
    acceso en un muro largo que además reparte particiones interiores
    se detecta correctamente.
    """
    muro = _muro_de(muros, str(getattr(vano, "wall_id", "")))
    seg = _seg_muro(muro) if muro is not None else None
    if seg is None:
        return False
    (sx, sy), (ex, ey) = seg
    largo = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
    if largo <= 1e-9:
        return False
    t = (float(getattr(vano, "offset_m", 0.0) or 0.0)
         + float(getattr(vano, "width_m", 0.0) or 0.0) / 2.0) / largo
    mx, my = sx + (ex - sx) * t, sy + (ey - sy) * t
    ux, uy = (ex - sx) / largo, (ey - sy) / largo
    w = max(float(getattr(vano, "width_m", 0.0) or 0.0), 0.4) / 2.0 \
        + 0.05
    sub = ((mx - ux * w, my - uy * w), (mx + ux * w, my + uy * w))
    return len(_locales_bajo(sub, vivos)) <= 1


def _muros_del_par(a: Any, b: Any, muros: List[Any]) -> List[Any]:
    """Muros medidos sobre la línea de partición entre a y b.

    Un muro cuenta si se solapa con la arista compartida de a Y con la
    de b (misma recta): así un muro largo del pasillo NO se cuela como
    partición de un par que no lo toca.
    """
    resultado: List[Any] = []
    vistos = set()
    for e1a, e1b in _aristas(a):
        for e2a, e2b in _aristas(b):
            if _solape_segmentos(e1a, e1b, e2a, e2b) < _SOLAPE_MIN_M:
                continue
            for m in muros:
                if id(m) in vistos:
                    continue
                seg = _seg_muro(m)
                if seg is None:
                    continue
                if (_solape_segmentos(seg[0], seg[1], e1a, e1b)
                        >= _SOLAPE_MIN_M
                        and _solape_segmentos(seg[0], seg[1],
                                              e2a, e2b)
                        >= _SOLAPE_MIN_M):
                    resultado.append(m)
                    vistos.add(id(m))
    return resultado


def _metadata_edificio(ctx: Any) -> Dict[str, Any]:
    try:
        from ui.building_wizard import _wizard_building
        _edificio, edif = _wizard_building(ctx)
        return edif if isinstance(edif, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _zona_verde(s: Any) -> bool:
    tipo = str(getattr(s, "space_type", "")).upper()
    if tipo in _ZONAS_VERDES_TIPO:
        return True
    nombre = str(getattr(s, "name", "")).lower()
    return any(clave in nombre for clave in _ZONAS_VERDES_NOMBRE)


# ======================================================================
# ACÚSTICA (§46)
# ======================================================================

def analisis_acustico(ctx: Any, trafico: str = "medio",
                      registro: Optional[ServiciosVivienda] = None) \
        -> Dict[str, Any]:
    """Fuentes del §46 contra DORMITORIOS midiendo el trazado.

    Devuelve hallazgos ACU001-ACU007 con estados honestos y la tabla
    de pares fuente-receptor con la solución de referencia del JSON.
    """
    reg = registro or _registro()
    acu = reg.acustica
    tipos = acu.get("tipos_fuente", {})
    soluciones = acu.get("soluciones", {})

    espacios = _lista(ctx, "SPACE")
    muros = _lista(ctx, "WALL")
    puertas = _lista(ctx, "DOOR")
    ventanas = _lista(ctx, "WINDOW")
    cubiertas = _lista(ctx, "ROOF")

    vivos = [s for s in espacios
             if len(getattr(s, "boundary", []) or []) >= 3]
    dormitorios = [s for s in vivos
                   if str(getattr(s, "space_type", "")).upper()
                   in tipos.get("DORMITORIO", ["BEDROOM"])]
    fuentes_por_tipo: Dict[str, List[Any]] = {}
    for clave in ("COCINA", "BANOS", "EQUIPOS"):
        busqueda = tipos.get(clave, [])
        encontrados = [s for s in vivos
                       if str(getattr(s, "space_type", "")).upper()
                       in busqueda]
        if encontrados:
            fuentes_por_tipo[clave] = encontrados

    # pares fuente -> dormitorio con muros medidos ------------------------
    pares: List[Dict[str, Any]] = []
    for clave, lista_f in fuentes_por_tipo.items():
        solucion = soluciones.get(clave, {})
        for f in lista_f:
            for d in dormitorios:
                if _comparten_borde(f, d) < _SOLAPE_MIN_M:
                    continue
                compartidos = _muros_del_par(f, d, muros)
                if not compartidos:
                    continue
                espesor = sum(float(getattr(m, "thickness_m", 0.0))
                              for m in compartidos) / len(compartidos)
                pares.append({
                    "tipo_fuente": clave,
                    "fuente": str(getattr(f, "name", "") or clave),
                    "receptor": str(getattr(d, "name", "") or
                                    "Dormitorio"),
                    "muros_medidos": len(compartidos),
                    "espesor_medido_mm": round(espesor * 1000.0, 1),
                    "material": solucion.get("material", ""),
                    "espesor_mm": solucion.get("espesor_mm", ""),
                    "doble_tabique": bool(
                        solucion.get("doble_tabique", False)),
                    "rw_db": solucion.get("rw_db", ""),
                })

    h: List[dict] = []

    conteo = ", ".join(
        f"{len(v)} {clave.lower()}(s)"
        for clave, v in fuentes_por_tipo.items())
    if conteo:
        h.append(HallazgoS("ACU001", "ok",
                           f"fuentes identificadas en el programa: "
                           f"{conteo}; CALLES y VECINOS dependen del "
                           "emplazamiento"))
    else:
        h.append(HallazgoS("ACU001", "info",
                           "sin locales fuente (cocina, baños, "
                           "equipos) en el trazado actual"))

    if pares:
        detalle = "; ".join(
            f"{p['fuente']} a {p['receptor']}: {p['muros_medidos']} "
            f"muro(s), espesor medido {p['espesor_medido_mm']:.0f} mm"
            for p in pares[:4])
        extra = "" if len(pares) <= 4 else f" (+{len(pares) - 4})"
        h.append(HallazgoS("ACU002", "aviso",
                           f"{len(pares)} par(es) fuente-dormitorio "
                           f"medidos: {detalle}{extra}. Exigir la "
                           "solución de referencia y verificar el R_w "
                           "con hoja de prestaciones o ensayo",
                           PENDIENTE))
    elif dormitorios:
        h.append(HallazgoS("ACU002", "ok",
                           "ningún muro compartido entre fuentes y "
                           "dormitorios en el trazado actual"))
    else:
        h.append(HallazgoS("ACU002", "info",
                           "no hay dormitorios en el proyecto"))

    edif = _metadata_edificio(ctx)
    viv_meta = edif.get("vivienda") or {}
    tipologia = str(viv_meta.get("tipologia", "")).lower()
    sol_vec = soluciones.get("VECINOS", {})
    if any(clave in tipologia for clave in _TIPOLOGIAS_MEDIANERA):
        h.append(HallazgoS("ACU003", "aviso",
                           f"tipología «{viv_meta.get('tipologia')}» "
                           "implica medianera con vecinos: exigir "
                           f"R_w de referencia "
                           f"{sol_vec.get('rw_db', 50)} dB con "
                           f"{str(sol_vec.get('material', '')).lower()}",
                           PENDIENTE))
    else:
        h.append(HallazgoS("ACU003", "info",
                           "tipología aislada: sin medianeras con "
                           "vecinos declaradas"))

    # fachada / calles: ventanas de dormitorios al exterior ---------------
    al_exterior = 0
    for d in dormitorios:
        for v in ventanas:
            if not _vano_perimetral(v, muros, vivos):
                continue
            muro = _muro_de(muros, str(getattr(v, "wall_id", "")))
            seg = _seg_muro(muro) if muro is not None else None
            if seg is None:
                continue
            # el vano perimetral debe caer además en el borde del
            # dormitorio receptor
            if _solape_con_local(seg, d) >= _SOLAPE_MIN_M:
                al_exterior += 1
    nivel_trafico = "medio"
    fila_trafico = next((t for t in acu.get("trafico", [])
                         if t.get("nivel") == nivel_trafico),
                        {"rw_db": 36.0, "nota": ""})
    sol_cal = soluciones.get("CALLES", {})
    if dormitorios and al_exterior:
        h.append(HallazgoS("ACU004", "aviso",
                           f"{al_exterior} ventana(s) de dormitorio a "
                           "fachada (tráfico "
                           f"{nivel_trafico}: R_w de referencia "
                           f"{fila_trafico.get('rw_db')} dB): "
                           f"{str(sol_cal.get('material', '')).lower()} "
                           "(VIDRIO_ACUSTICO del §46)", PENDIENTE))
    elif dormitorios:
        h.append(HallazgoS("ACU004", "info",
                           "dormitorios sin ventanas al exterior "
                           "detectadas"))

    # cubierta: planta superior habitable ---------------------------------
    if cubiertas and vivos:
        h.append(HallazgoS("ACU005", "aviso",
                           "cubierta modelada sobre planta habitable: "
                           "aislamiento de referencia "
                           f"{acu.get('cubierta', {}).get('rw_db', 45)} "
                           "dB con "
                           f"{str(acu.get('cubierta', {}).get('material', '')).lower()}"
                           " (AISLAMIENTO_CUBIERTA del §46)",
                           PENDIENTE))
    else:
        h.append(HallazgoS("ACU005", "info",
                           "sin cubierta modelada sobre la planta "
                           "superior"))

    # puertas de dormitorios ------------------------------------------------
    if dormitorios and puertas:
        h.append(HallazgoS("ACU006", "aviso",
                           f"{len(dormitorios)} dormitorio(s) con "
                           "puerta: exigir puerta con cierre perimetral "
                           "R_w >= 30 dB (referencia)", PENDIENTE))

    h.append(HallazgoS("ACU007", "info",
                       "el aislamiento FINAL (R_w) y el ruido de "
                       "impacto exigen ensayo de laboratorio o ficha "
                       "de prestaciones: cálculo especializado",
                       REQUIERE_CALCULO))

    filas_sol = [
        [clave, str(sol.get("material", "")),
         str(sol.get("espesor_mm", "")),
         "sí" if sol.get("doble_tabique") else "no",
         str(sol.get("rw_db", ""))]
        for clave, sol in soluciones.items()
    ]
    return {
        "edificacion": str(edif.get("nombre", "") or ""),
        "uso": str(edif.get("uso_social", "") or ""),
        "tipologia": str(viv_meta.get("tipologia", "") or ""),
        "trafico": nivel_trafico,
        "hallazgos": h,
        "resumen": _resumen_de(h),
        "pares": pares,
        "tablas": [
            {"titulo": "Pares fuente-dormitorio medidos en el trazado",
             "cabeceras": ["Fuente", "Receptor", "Muros medidos",
                           "Espesor medido mm", "Solución de referencia",
                           "Espesor mm", "Doble tabique", "R_w ref dB"],
             "filas": [[p["fuente"], p["receptor"],
                        str(p["muros_medidos"]),
                        f"{p['espesor_medido_mm']:.0f}", p["material"],
                        str(p["espesor_mm"]),
                        "sí" if p["doble_tabique"] else "no",
                        str(p["rw_db"])] for p in pares]},
            {"titulo": "Soluciones de referencia del §46",
             "cabeceras": ["Fuente", "Material", "Espesor mm",
                           "Doble tabique", "R_w ref dB"],
             "filas": filas_sol},
        ],
        "nota_valores": acu.get("nota_valores", ""),
        "advertencia": reg.advertencia,
        "principio_seguridad": reg.principio,
        "fuentes": reg.fuentes,
        "catalogo": reg.resumen(),
    }


def texto_acustica(informe: Dict[str, Any]) -> str:
    """Informe acústico listo para consola (cp1252, sin flechas)."""
    cabecera = "ACÚSTICA DE LA VIVIENDA (Especificaciones técnicas §46)"
    if informe.get("edificacion"):
        cabecera += f" - {informe['edificacion']}"
    lineas = [cabecera]
    datos = []
    if informe.get("tipologia"):
        datos.append(f"tipología {informe['tipologia']}")
    if informe.get("trafico"):
        datos.append(f"tráfico {informe['trafico']}")
    if datos:
        lineas.append(", ".join(datos))
    lineas.append("")
    for x in informe.get("hallazgos", []):
        marca = {"ok": "[OK]", "fallo": "[X]", "aviso": "[!]",
                 "info": "[i]"}.get(x["severidad"], "[?]")
        estado = {"medido": "", "pendiente": " (pendiente)",
                  "requiere calculo":
                      " (REQUIERE_CALCULO_ESPECIALIZADO)"}.get(
            x.get("estado", ""), "")
        lineas.append(f"{marca} {x['codigo']}: {x['mensaje']}{estado}")
    pares = informe.get("pares", [])
    if pares:
        lineas.append("")
        lineas.append("Pares fuente-dormitorio medidos:")
        for p in pares:
            lineas.append(
                f"· {p['fuente']} a {p['receptor']}: "
                f"{p['muros_medidos']} muro(s), espesor medido "
                f"{p['espesor_medido_mm']:.0f} mm, solución: "
                f"{p['material']} ({p['espesor_mm']} mm, R_w ref "
                f"{p['rw_db']} dB)")
    resumen = informe.get("resumen", {})
    lineas.append("")
    lineas.append(f"Resumen: {resumen.get('ok', 0)} cumplen, "
                  f"{resumen.get('avisos', 0)} avisos, "
                  f"{resumen.get('fallos', 0)} fallos, "
                  f"{resumen.get('pendientes', 0)} pendientes o de "
                  "cálculo.")
    lineas.append("")
    lineas.append(str(informe.get("nota_valores") or ""))
    lineas.append(str(informe.get("advertencia") or ""))
    return "\n".join(lineas)


# ======================================================================
# DOMÓTICA (§39)
# ======================================================================

def plan_domotico(ctx: Any, sistemas: Optional[List[str]] = None,
                  registro: Optional[ServiciosVivienda] = None) \
        -> Dict[str, Any]:
    """Plan domótico por SISTEMAS y ELEMENTOS (§39) sobre el modelo.

    ``sistemas`` filtra claves del §39 (ILUMINACION, SEGURIDAD...);
    None = los ocho. Los conteos salen del trazado y del programa;
    los precios son equipos de referencia en CUP.
    """
    reg = registro or _registro()
    dom = reg.domotica

    espacios = _lista(ctx, "SPACE")
    muros = _lista(ctx, "WALL")
    puertas = _lista(ctx, "DOOR")
    ventanas = _lista(ctx, "WINDOW")
    niveles = _lista(ctx, "LEVEL")

    vivos = [s for s in espacios
             if len(getattr(s, "boundary", []) or []) >= 3]
    habitables = [s for s in vivos
                  if str(getattr(s, "space_type", "")) not in
                  _TIPOS_TECNICOS]
    pasillos = [s for s in vivos
                if str(getattr(s, "space_type", ""))
                in _TECNICOS_CIRCULACION]
    zonas_verdes = [s for s in vivos if _zona_verde(s)]

    puertas_ext = [p for p in puertas
                   if _vano_perimetral(p, muros, vivos)]
    ventanas_pb = 0
    if niveles:
        cota_min = min(float(getattr(n, "elevation", 0.0) or 0.0)
                       for n in niveles)
        pb_ids = {str(getattr(n, "id", "")) for n in niveles
                  if abs(float(getattr(n, "elevation", 0.0) or 0.0)
                         - cota_min) < 1e-9}
        for v in ventanas:
            if str(getattr(v, "level_id", "")) in pb_ids and \
                    _vano_perimetral(v, muros, vivos):
                ventanas_pb += 1

    edif = _metadata_edificio(ctx)
    instalaciones = [str(i).lower()
                     for i in (edif.get("instalaciones") or [])]
    con_solar = any("solar" in i for i in instalaciones)

    filtros = set(str(s or "").upper() for s in (sistemas or []))
    conteo = {
        "niveles": len(niveles),
        "habitables": len(habitables),
        "pasillos": len(pasillos),
        "puertas_ext": len(puertas_ext),
        "ventanas": len(ventanas),
        "ventanas_pb": ventanas_pb,
        "zonas_verdes": len(zonas_verdes),
        "banos_cocina_lavaderos": sum(
            1 for s in vivos
            if str(getattr(s, "space_type", "")).upper()
            in ("BATHROOM", "LAVATORY", "KITCHEN", "LAUNDRY")),
        "con_solar": 1 if con_solar else 0,
    }

    def _cantidad(clave: str) -> Tuple[int, str]:
        """(cantidad, base con números) según la clave de la regla."""
        if clave == "presencia":
            n = len(pasillos) + len(puertas_ext)
            return n, f"{len(pasillos)} pasillo(s)/escalera(s) + " \
                      f"{len(puertas_ext)} puerta(s) exterior(es)"
        if clave == "circuito":
            return len(habitables), \
                f"{len(habitables)} local(es) habitable(s)"
        if clave == "central" or clave == "panel":
            return 1, "1 por vivienda"
        if clave == "contactos":
            n = len(puertas_ext) + ventanas_pb
            return n, f"{len(puertas_ext)} puerta(s) exterior(es) + " \
                      f"{ventanas_pb} ventana(s) en planta de acceso"
        if clave == "volumetricos":
            n = ceil(len(habitables) / 3.0) if habitables else 0
            return n, f"ceil({len(habitables)} habitables / 3)"
        if clave == "sirena":
            return 1, "1 por vivienda"
        if clave == "termostato":
            return len(niveles), f"{len(niveles)} nivel(es)"
        if clave == "persianas":
            return len(ventanas), \
                f"{len(ventanas)} ventana(s) del proyecto"
        if clave == "programador_riego":
            n = 1 if zonas_verdes else 0
            base = (f"{len(zonas_verdes)} zona(s) verde(s) en el "
                    "programa") if n else \
                "sin zonas verdes en el programa"
            return n, base
        if clave == "electrovalvulas":
            return len(zonas_verdes), \
                f"{len(zonas_verdes)} zona(s) verde(s)"
        if clave == "monitor":
            n = 2 if con_solar else 1
            return n, "2 por haber sistema solar FV" if con_solar \
                else "1 por vivienda"
        if clave == "fugas":
            return conteo["banos_cocina_lavaderos"], \
                f"{conteo['banos_cocina_lavaderos']} local(es) húmedo(s)"
        if clave == "llave":
            return 1, "1 por vivienda"
        if clave == "videoportero":
            return 1, "1 por vivienda"
        if clave == "cerradura":
            return len(puertas_ext), \
                f"{len(puertas_ext)} puerta(s) exterior(es)"
        return 0, ""

    filas: List[Dict[str, Any]] = []
    sistemas_out: List[Dict[str, Any]] = []
    for regla in dom.get("reglas", []):
        clave_sis = str(regla.get("sistema", ""))
        if filtros and clave_sis not in filtros:
            continue
        elementos: List[Dict[str, Any]] = []
        total_sis = 0.0
        for el in regla.get("elementos", []):
            clave_regla = str(el.get("clave") or _clave_de_base(el))
            cantidad, base = _cantidad(clave_regla)
            precio = float(el.get("precio_cup", 0.0))
            subtotal = round(precio * cantidad, 2)
            total_sis += subtotal
            fila = {"sistema": clave_sis,
                    "sistema_nombre": str(regla.get("nombre", clave_sis)),
                    "elemento": str(el.get("elemento", "")),
                    "nombre": str(el.get("nombre", "")),
                    "cantidad": cantidad, "unidad": str(el.get("unidad", "ud")),
                    "base": base, "precio_cup": precio,
                    "subtotal_cup": subtotal}
            elementos.append(fila)
            filas.append(fila)
        sistemas_out.append({
            "sistema": clave_sis,
            "nombre": str(regla.get("nombre", clave_sis)),
            "elementos": elementos,
            "total_cup": round(total_sis, 2),
        })
    total_general = round(sum(s["total_cup"] for s in sistemas_out), 2)

    h: List[dict] = []
    activos = ", ".join(s["nombre"] for s in sistemas_out) or "ninguno"
    h.append(HallazgoS("DO001", "ok",
                       f"plan para {len(sistemas_out)} de los 8 "
                       f"sistemas del §39: {activos}; "
                       f"{len(filas)} tipo(s) de elemento contados "
                       "sobre el modelo"))
    h.append(HallazgoS("DO002", "info",
                       str(dom.get("nota_red", "")), REQUIERE_CALCULO))
    h.append(HallazgoS("DO003", "info",
                       str(dom.get("nota_precios", ""))))

    return {
        "edificacion": str(edif.get("nombre", "") or ""),
        "uso": str(edif.get("uso_social", "") or ""),
        "hallazgos": h,
        "resumen": _resumen_de(h),
        "sistemas": sistemas_out,
        "conteo": conteo,
        "filas": filas,
        "total_equipos_cup": total_general,
        "tablas": [
            {"titulo": "Equipos domóticos de referencia (§39)",
             "cabeceras": ["Sistema", "Elemento", "Nombre",
                           "Cantidad", "Base del conteo",
                           "Precio CUP", "Subtotal CUP"],
             "filas": [[f["sistema_nombre"], f["elemento"],
                        f["nombre"], f"{f['cantidad']:g}", f["base"],
                        _miles(f["precio_cup"]),
                        _miles(f["subtotal_cup"])] for f in filas]
             + [["", "", "", "", "TOTAL", "",
                 _miles(total_general)]]},
        ],
        "advertencia": reg.advertencia,
        "principio_seguridad": reg.principio,
        "fuentes": reg.fuentes,
        "catalogo": reg.resumen(),
    }


def _clave_de_base(el: Dict[str, Any]) -> str:
    """Clave de conteo de respaldo por nombre del elemento."""
    nombre = str(el.get("nombre", "")).lower()
    if "presencia" in nombre:
        return "presencia"
    if "circuito" in nombre:
        return "circuito"
    if "hub" in nombre or "central" in nombre:
        return "central"
    if "panel" in nombre:
        return "panel"
    if "contacto" in nombre:
        return "contactos"
    if "volumétrico" in nombre or "volumetrico" in nombre or "pir" in nombre:
        return "volumetricos"
    if "sirena" in nombre:
        return "sirena"
    if "termostato" in nombre:
        return "termostato"
    if "persiana" in nombre:
        return "persianas"
    if "programador" in nombre:
        return "programador_riego"
    if "electroválvula" in nombre or "electrovalvula" in nombre:
        return "electrovalvulas"
    if "monitor" in nombre:
        return "monitor"
    if "fuga" in nombre:
        return "fugas"
    if "llave" in nombre:
        return "llave"
    if "portero" in nombre:
        return "videoportero"
    if "cerradura" in nombre:
        return "cerradura"
    return ""


def texto_domotica(informe: Dict[str, Any]) -> str:
    """Plan domótico listo para consola (cp1252, sin flechas)."""
    cabecera = "PLAN DOMÓTICO (Especificaciones técnicas Viviendas §39)"
    if informe.get("edificacion"):
        cabecera += f" - {informe['edificacion']}"
    lineas = [cabecera]
    lineas.append("")
    for x in informe.get("hallazgos", []):
        marca = {"ok": "[OK]", "fallo": "[X]", "aviso": "[!]",
                 "info": "[i]"}.get(x["severidad"], "[?]")
        estado = {"medido": "", "pendiente": " (pendiente)",
                  "requiere calculo":
                      " (REQUIERE_CALCULO_ESPECIALIZADO)"}.get(
            x.get("estado", ""), "")
        lineas.append(f"{marca} {x['codigo']}: {x['mensaje']}{estado}")
    for sistema in informe.get("sistemas", []):
        lineas.append("")
        lineas.append(f"{sistema['nombre']} "
                      f"({_miles(sistema['total_cup'])} CUP en equipos)")
        for el in sistema["elementos"]:
            lineas.append(
                f"· [{el['elemento']}] {el['nombre']}: "
                f"{el['cantidad']:g} {el['unidad']} — {el['base']} "
                f"= {_miles(el['subtotal_cup'])} CUP")
    lineas.append("")
    lineas.append(f"TOTAL equipos: "
                  f"{_miles(informe.get('total_equipos_cup', 0.0))} CUP")
    lineas.append("")
    lineas.append(str(informe.get("advertencia") or ""))
    return "\n".join(lineas)


__all__ = [
    "ServiciosVivienda", "cargar_servicios", "calcular_piscina",
    "texto_piscina", "analisis_acustico", "texto_acustica",
    "plan_domotico", "texto_domotica", "MEDIDO", "PENDIENTE",
    "REQUIERE_CALCULO",
]

"""Estudios de vivienda (v3.24.0): alternativas, modulación y solar.

Tres estudios del «Catálogo maestro de viviendas» operativos sobre el
proyecto abierto, todos de SOLO LECTURA (no crean entidades ni tocan
el presupuesto persistido):

1. ALTERNATIVAS COMPARABLES (§62-63): para la misma entrada
   (tipología + dormitorios + baños + estilo) genera alternativas A/B/C
   por nivel de acabado (Económica/Estándar/Premium del §51) y
   1/2/3/4 por sistema constructivo (mampostería confinada, hormigón
   aporticado, steel framing y modular prefabricado), cada una con las
   métricas de comparación del §63 (superficie, costo índice, tiempo,
   hormigón, acero, mampostería, madera, consumo, mantenimiento, vida
   útil, complejidad y disponibilidad). Los datos salen del bloque
   ``comparacion_sistemas`` del catálogo (valores de referencia
   editables, §66); la compatibilidad estilo-sistema del §27 avisa sin
   bloquear y la recomendación prefiere el costo menor compatible.

2. MODULACIÓN (§56): evalúa locales, muros, puertas y ventanas contra
   el módulo elegido (MODULO_0.60, MODULO_1.20, MODULO_1.25,
   MODULO_1.50 o personalizado) para reducir desperdicios: porcentajes
   de piezas en módulo, residuo lineal acumulado y sugerencia al
   múltiplo inferior/superior de cada pieza fuera de módulo.

3. ENERGÍA SOLAR (§38): dimensiona el campo fotovoltaico
   (FOTOVOLTAICO, SOLAR_TERMICO o HIBRIDO) a partir del consumo diario
   y las horas de sol pico: número de paneles, potencia total,
   capacidad de batería, potencia de inversor y superficie requerida;
   el térmico añade colectores y tanque por ocupantes. Los parámetros
   de referencia viven en el bloque ``energia_solar`` del catálogo y
   son configurables (§66). El dimensionado DEFINITIVO de la
   instalación queda marcado REQUIERE_CALCULO_ESPECIALIZADO (§81).

Uso headless:
    from domain.vivienda_estudios import (generar_alternativas,
                                          evaluar_modulacion,
                                          dimensionar_solar)
    print(texto_alternativas(generar_alternativas(ctx)))
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.errors import DomainError

# módulos estándar del §56 (los nombres EXACTOS del catálogo)
MODULOS_ESTANDAR: tuple = (("MODULO_0.60", 0.60), ("MODULO_1.20", 1.20),
                           ("MODULO_1.25", 1.25), ("MODULO_1.50", 1.50))
TOLERANCIA_MODULO_M = 0.02   # holgura constructiva al evaluar el múltiplo

# sistemas fotovoltaicos del §38
FOTOVOLTAICO = "FOTOVOLTAICO"
SOLAR_TERMICO = "SOLAR_TERMICO"
HIBRIDO = "HIBRIDO"

# niveles del §51 que encarnan las alternativas A/B/C del §62
NIVEL_A, NIVEL_B, NIVEL_C = 1, 2, 4

# superficie de respaldo si no hay proyecto ni programa (m2)
SUPERFICIE_RESPALDO_M2 = 90.0


# ----------------------------------------------------------------------
# 1. ALTERNATIVAS COMPARABLES (§62-63)
# ----------------------------------------------------------------------

@dataclass
class AlternativaV:
    """Una alternativa comparable con las métricas del §63."""

    clave: str
    etiqueta: str
    tipo: str                    # "nivel" (A/B/C) o "sistema" (1/2/3/4)
    orden: int
    nivel_acabado: int = 0       # 1-5 del §51 (0: el nivel es el del proyecto)
    sistema_clave: str = ""      # clave del catálogo (vacío en A/B/C)
    compatibilidad: Optional[int] = None   # 0-3 del §27 con el estilo
    superficie_m2: float = 0.0
    costo_indice: float = 0.0    # índice por m2 (100 = mampostería estándar)
    costo_rel_pct: float = 0.0   # % respecto a la B (estándar) de referencia
    tiempo_meses: float = 0.0
    hormigon_m3: float = 0.0
    acero_kg: float = 0.0
    mamposteria_m2: float = 0.0
    madera_m3: float = 0.0
    consumo_kwh_m2_ano: float = 0.0
    mantenimiento_pct_anual: float = 0.0
    vida_util_anos: int = 0
    complejidad: int = 0         # 1-3
    disponibilidad: str = ""
    notas: List[str] = field(default_factory=list)

    def como_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def _superficie_programa(ctx: Any, dormitorios: int, banos: int,
                         tipologia: str) -> float:
    """Superficie de referencia para comparar (m2).

    Orden honesto: 1) la suma REAL de los locales del proyecto si ya
    hay edificación; 2) el programa paramétrico del catálogo (§7)
    generado headless con la tipología y los dormitorios pedidos;
    3) un respaldo fijo. Nunca lanza: es una estimación comparativa.
    """
    if ctx is not None:
        try:
            from domain.vivienda_specs import _lista, _TIPOS_TECNICOS
            vivos = [s for s in _lista(ctx, "SPACE")
                     if len(getattr(s, "boundary", []) or []) >= 3
                     and str(getattr(s, "space_type", ""))
                     not in _TIPOS_TECNICOS]
            if vivos:
                return max(sum(max(float(s.area_m2()), 0.0)
                               for s in vivos), 1.0)
        except Exception:  # noqa: BLE001 — sin proyecto: seguimos
            pass
    try:
        from ui.building_wizard import BuildingWizardData, \
            apply_usage_program
        data = BuildingWizardData()
        data.usage_type = "Vivienda"
        data.vivienda_tipologia = str(tipologia or "Unifamiliar aislada")
        data.vivienda_dormitorios = int(max(1, min(dormitorios, 6)))
        data.vivienda_banos = int(max(1, min(banos, 4)))
        apply_usage_program(data)
        total = sum(max(r.width_m, 0.0) * max(r.depth_m, 0.0)
                    for r in data.rooms)
        if total > 0:
            return total
    except Exception:  # noqa: BLE001 — sin catálogo/wizard: respaldo
        pass
    return SUPERFICIE_RESPALDO_M2


def _estilo_a_clave(estilo_label: str, catalogo: Any) -> str:
    from domain.vivienda_specs import MAPEO_ESTILOS_GUI
    clave = MAPEO_ESTILOS_GUI.get(str(estilo_label or ""), "")
    if clave and catalogo is not None and catalogo.estilo_por_clave(clave):
        return clave
    return clave


def _sistema_a_clave(sistema_label: str) -> str:
    from domain.vivienda_specs import MAPEO_SISTEMAS_GUI
    return MAPEO_SISTEMAS_GUI.get(str(sistema_label or ""), "")


def generar_alternativas(ctx: Any = None,
                         dormitorios: int = 3, banos: int = 2,
                         estilo_label: str = "",
                         tipologia: str = "Unifamiliar aislada",
                         sistema_label: str = "",
                         catalogo: Any = None) -> Dict[str, Any]:
    """Alternativas A/B/C por nivel y 1/2/3/4 por sistema (§62-63).

    Sólo lectura: no modifica el proyecto ni el presupuesto. Si el
    catálogo no está disponible lanza ARQ-VIV-002 (mismo criterio que
    la validación de vivienda).
    """
    if catalogo is None:
        from domain.vivienda_specs import cargar_catalogo
        catalogo = cargar_catalogo()
    if catalogo is None:
        raise DomainError(
            message="No se encontró el catálogo maestro de viviendas",
            code="ARQ-VIV-002",
            suggested_action="Verifique resources/knowledge/"
                             "vivienda_catalogo.json.")
    comparar = dict(catalogo.comparacion_sistemas or {})
    if not comparar.get("sistemas"):
        raise DomainError(
            message="El catálogo no trae los datos de comparación de "
                    "sistemas (bloque comparacion_sistemas)",
            code="ARQ-VIV-003",
            suggested_action="Actualice vivienda_catalogo.json a la "
                             "versión 1.1 o posterior.")
    superficie = _superficie_programa(ctx, dormitorios, banos, tipologia)
    estilo_clave = _estilo_a_clave(estilo_label, catalogo)

    from domain.vivienda_specs import compatibilidad_gui

    alternativas: List[AlternativaV] = []

    # --- A/B/C por NIVEL DE ACABADO (§62): el sistema es el del
    # --- proyecto (o mampostería confinada de referencia).
    sistema_base = _sistema_a_clave(sistema_label) or \
        "mamposteria_confinada"
    costo_sistema = float(comparar.get("costo_indice_m2",
                                       {}).get(sistema_base, 100.0))
    from ui.variant_budget import FACTOR_CALIDAD  # apreciación visible
    for clave, etiqueta, nivel, orden in (
            ("A", "Económica", NIVEL_A, 1),
            ("B", "Estándar", NIVEL_B, 2),
            ("C", "Premium", NIVEL_C, 3)):
        # el nombre del nivel en FACTOR_CALIDAD (misma escala §51)
        nombre_nivel = {1: "Económica", 2: "Estándar",
                        4: "Premium"}.get(nivel, "Estándar")
        factor = float(FACTOR_CALIDAD.get(nombre_nivel, 1.0))
        indice = costo_sistema * factor
        alt = AlternativaV(
            clave=clave, etiqueta=f"Alternativa {clave} - {etiqueta} "
                                  f"(nivel {nivel} del §51)",
            tipo="nivel", orden=orden, nivel_acabado=nivel,
            sistema_clave=sistema_base,
            compatibilidad=compatibilidad_gui(
                estilo_label, _etiqueta_sistema(sistema_base, comparar),
                catalogo) if estilo_clave else None,
            superficie_m2=round(superficie, 1),
            costo_indice=round(indice, 1))
        _llenar_metricas(alt, comparar, superficie)
        alt.costo_rel_pct = 0.0  # se fija al final, con la B montada
        alternativas.append(alt)

    # --- 1/2/3/4 por SISTEMA CONSTRUCTIVO (§62), al nivel B (estándar)
    for clave_sys, orden in zip(comparar.get("sistemas", []),
                                range(1, 5)):
        etiqueta_sys = str(comparar.get("etiquetas", {}).get(
            clave_sys, clave_sys))
        indice = float(comparar.get("costo_indice_m2",
                                    {}).get(clave_sys, 100.0))
        alt = AlternativaV(
            clave=str(orden), etiqueta=f"Alternativa {orden} - "
                                       f"{etiqueta_sys} (nivel 2 del §51)",
            tipo="sistema", orden=orden, nivel_acabado=NIVEL_B,
            sistema_clave=clave_sys,
            compatibilidad=catalogo.nivel_compatibilidad(
                estilo_clave, clave_sys) if estilo_clave else None,
            superficie_m2=round(superficie, 1),
            costo_indice=round(indice, 1))
        _llenar_metricas(alt, comparar, superficie)
        if clave_sys == sistema_base:
            alt.notas.append("sistema elegido en el asistente")
        alternativas.append(alt)

    # coste relativo respecto a la B (referencia 100 %)
    ref = next((a.costo_indice for a in alternativas
                if a.clave == "B"), 100.0) or 100.0
    for a in alternativas:
        a.costo_rel_pct = round(a.costo_indice / ref * 100.0, 1)

    # --- comparación §63 + recomendación -----------------------------
    ordenadas = sorted(alternativas,
                       key=lambda a: (a.costo_indice, a.orden))
    recomendada = None
    if estilo_clave:
        compatibles = [a for a in ordenadas
                       if (a.compatibilidad or 0) >= 2]
        if compatibles:
            recomendada = compatibles[0]
    if recomendada is None:
        recomendada = ordenadas[0]
    if recomendada is not None:
        recomendada.notas.append("recomendada: menor costo con "
                                 "compatibilidad >= 2/3 (§27)")

    return {
        "entrada": {
            "tipologia": str(tipologia or ""),
            "estilo": str(estilo_label or ""),
            "estilo_clave": estilo_clave,
            "sistema": str(sistema_label or ""),
            "dormitorios": int(dormitorios),
            "banos": int(banos),
            "superficie_m2": round(superficie, 1),
            "origen_superficie": _origen_superficie(ctx),
        },
        "alternativas": [a.como_dict() for a in ordenadas],
        "recomendada": recomendada.clave if recomendada else "",
        "advertencia": catalogo.advertencia,
        "nota_datos": comparar.get("nota", ""),
        "principio_seguridad": catalogo.principio,
    }


def _etiqueta_sistema(clave: str, comparar: Dict[str, Any]) -> str:
    """Etiqueta de GUI del sistema (para la compatibilidad §27)."""
    from domain.vivienda_specs import MAPEO_SISTEMAS_GUI
    inverso = {v: k for k, v in MAPEO_SISTEMAS_GUI.items()}
    etiqueta = inverso.get(clave)
    if etiqueta:
        return etiqueta
    return str((comparar.get("etiquetas", {}) or {}).get(clave, clave))


def _llenar_metricas(alt: AlternativaV, comparar: Dict[str, Any],
                     superficie: float) -> None:
    """Métricas del §63 a partir del bloque de referencia."""
    clave = alt.sistema_clave
    alt.tiempo_meses = round(
        float(comparar.get("tiempo_meses_por_100m2", {})
              .get(clave, 6.0)) * superficie / 100.0, 1)
    alt.hormigon_m3 = round(
        float(comparar.get("hormigon_m3_m2", {})
              .get(clave, 0.0)) * superficie, 1)
    alt.acero_kg = round(
        float(comparar.get("acero_kg_m2", {})
              .get(clave, 0.0)) * superficie, 0)
    alt.mamposteria_m2 = round(
        float(comparar.get("mamposteria_m2_m2", {})
              .get(clave, 0.0)) * superficie, 1)
    alt.madera_m3 = round(
        float(comparar.get("madera_m3_m2", {})
              .get(clave, 0.0)) * superficie, 2)
    alt.consumo_kwh_m2_ano = float(comparar.get("consumo_kwh_m2_ano",
                                                {}).get(clave, 0.0))
    alt.mantenimiento_pct_anual = float(
        comparar.get("mantenimiento_pct_anual", {}).get(clave, 0.0))
    alt.vida_util_anos = int(comparar.get("vida_util_anos",
                                          {}).get(clave, 0))
    alt.complejidad = int(comparar.get("complejidad_1_3",
                                       {}).get(clave, 1))
    alt.disponibilidad = str(comparar.get("disponibilidad_cuba",
                                          {}).get(clave, ""))


def _origen_superficie(ctx: Any) -> str:
    if ctx is None:
        return "programa paramétrico del catálogo (§7)"
    try:
        from domain.vivienda_specs import _lista
        if _lista(ctx, "SPACE"):
            return "suma real de los locales del proyecto"
    except Exception:  # noqa: BLE001
        pass
    return "programa paramétrico del catálogo (§7)"


def texto_alternativas(informe: Dict[str, Any]) -> str:
    """Tabla comparativa §63 lista para consola o cuadro de texto
    (cp1252, sin flechas ni emojis)."""
    entra = informe.get("entrada", {})
    lineas = ["ALTERNATIVAS DE VIVIENDA (catálogo §62-63)"]
    datos = []
    if entra.get("tipologia"):
        datos.append(f"tipología {entra['tipologia']}")
    if entra.get("estilo"):
        datos.append(f"estilo {entra['estilo']}")
    datos.append(f"{entra.get('dormitorios', '?')} dormitorios")
    datos.append(f"{entra.get('banos', '?')} baños")
    lineas.append(", ".join(datos))
    lineas.append(f"superficie de referencia "
                  f"{entra.get('superficie_m2', 0.0):.1f} m2 "
                  f"({entra.get('origen_superficie', '')})")
    lineas.append("A/B/C: niveles 1/2/4 del §51 con el sistema del "
                  "proyecto; 1/2/3/4: sistemas del catálogo al nivel "
                  "2 (Estándar)")
    lineas.append("")
    cab = (f"{'Alt':<4} {'Nivel / sistema':<26} {'Niv':>3} {'Costo':>7} "
           f"{'Rel':>7} {'Meses':>6} {'Horm':>6} {'Acero':>6} "
           f"{'Vida':>5} {'Cp':>3}")
    lineas.append(cab)
    lineas.append("-" * len(cab))
    for a in informe.get("alternativas", []):
        if a.get("tipo") == "nivel":
            nombre = {1: "Económica", 2: "Estándar",
                      4: "Premium"}.get(a.get("nivel_acabado", 0),
                                        "Estándar")
        else:
            nombre = str(a.get("etiqueta", "")).split(" - ")[-1]
            nombre = nombre.replace(" (nivel 2 del §51)", "")
        if len(nombre) > 26:
            nombre = nombre[:25] + "."
        lineas.append(
            f"{a.get('clave', ''):<4} {nombre:<26} "
            f"{a.get('nivel_acabado', 0):>3d} "
            f"{a.get('costo_indice', 0.0):>7.1f} "
            f"{a.get('costo_rel_pct', 0.0):>6.1f}% "
            f"{a.get('tiempo_meses', 0.0):>6.1f} "
            f"{a.get('hormigon_m3', 0.0):>6.1f} "
            f"{a.get('acero_kg', 0.0):>6.0f} "
            f"{a.get('vida_util_anos', 0):>5d} "
            f"{a.get('complejidad', 0):>3d}")
    lineas.append("")
    lineas.append("Unidades: costo índice por m2 (100 = mampostería "
                  "confinada estándar), rel = % frente a la "
                  "alternativa B, meses de construcción, hormigón m3, "
                  "acero kg, vida útil en años, Cp = complejidad 1-3.")
    lineas.append("")
    rec = informe.get("recomendada", "")
    if rec:
        for a in informe.get("alternativas", []):
            if a.get("clave") == rec:
                lineas.append(f"Recomendada: {a.get('etiqueta', rec)} "
                              f"(costo rel {a.get('costo_rel_pct', 0.0)}"
                              f" %, compatibilidad "
                              f"{a.get('compatibilidad', 's/d')}/3)")
                for nota in a.get("notas", []):
                    lineas.append(f"· {nota}")
                break
    if informe.get("nota_datos"):
        lineas.append("")
        lineas.append(str(informe["nota_datos"]))
    if informe.get("advertencia"):
        lineas.append("")
        lineas.append(str(informe["advertencia"]))
    return "\n".join(lineas)

# --- continuación: modulación §56, solar §38 y helpers ----------------

# ----------------------------------------------------------------------
# 2. MODULACIÓN (§56)
# ----------------------------------------------------------------------

def _etiqueta_modulo(valor: float) -> str:
    for nombre, m in MODULOS_ESTANDAR:
        if abs(m - valor) < 1e-9:
            return nombre
    return "MODULO_PERSONALIZADO"


def _en_modulo(valor: float, modulo: float) -> bool:
    """True si la dimensión cae en múltiplo del módulo (con la
    holgura constructiva del taller)."""
    if valor <= 1e-9 or modulo <= 1e-9:
        return True
    n = round(valor / modulo)
    return abs(valor - n * modulo) <= TOLERANCIA_MODULO_M


def _sugerencias_modulo(valor: float, modulo: float) -> List[float]:
    """Los dos múltiplos que encajan alrededor de la dimensión."""
    abajo = math.floor(valor / modulo + 1e-9) * modulo
    arriba = math.ceil(valor / modulo - 1e-9) * modulo
    if arriba - valor < 1e-9:
        arriba += modulo
    if valor - abajo < 1e-9:
        abajo -= modulo
    return [round(abajo, 3), round(arriba, 3)]


def evaluar_modulacion(ctx: Any = None, modulo: float = 1.20) \
        -> Dict[str, Any]:
    """Modulación §56 de locales, muros, puertas y ventanas.

    Evalúa MUROS, PANELES (losas: lados de la envolvente), BLOQUES
    (dimensiones de los locales), VENTANAS y PUERTAS (anchos) contra
    el módulo pedido para reducir desperdicios. Sólo lectura.
    Lanza ARQ-EST-001 si el módulo no es utilizable.
    """
    modulo = float(modulo)
    if not (0.05 <= modulo <= 20.0):
        raise DomainError(
            message=f"El módulo {modulo:g} m no es utilizable: usa un "
                    "valor entre 0.05 y 20.00 m",
            code="ARQ-EST-001",
            context={"modulo": modulo},
            suggested_action="Elige MODULO_0.60/1.20/1.25/1.50 o un "
                             "módulo personalizado razonable.")
    piezas: List[Dict[str, Any]] = []

    def _piezas(categoria: str, nombre: str, valor: float) -> None:
        valor = float(valor)
        if valor <= 1e-9:
            return
        en = _en_modulo(valor, modulo)
        entrada = {
            "categoria": categoria,
            "nombre": str(nombre),
            "dimension_m": round(valor, 3),
            "en_modulo": en,
            "residuo_m": round(valor - round(valor / modulo) * modulo,
                               3),
        }
        if not en:
            abajo, arriba = _sugerencias_modulo(valor, modulo)
            entrada["sugerencias_m"] = [abajo, arriba]
        piezas.append(entrada)

    if ctx is not None:
        from domain.vivienda_specs import _lista, _nombre
        for s in _lista(ctx, "SPACE"):
            boundary = [tuple(p) for p in
                        getattr(s, "boundary", []) or []]
            if len(boundary) < 3:
                continue
            xs = [p[0] for p in boundary]
            ys = [p[1] for p in boundary]
            ancho = max(xs) - min(xs)
            fondo = max(ys) - min(ys)
            _piezas("BLOQUES", _nombre(s), ancho)
            _piezas("BLOQUES", _nombre(s), fondo)
        for muro in _lista(ctx, "WALL"):
            try:
                sx, sy = muro.start
                ex, ey = muro.end
            except Exception:  # noqa: BLE001
                continue
            largo = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
            _piezas("MUROS", str(getattr(muro, "code", "") or "?"),
                    largo)
        for vano in _lista(ctx, "DOOR") + _lista(ctx, "WINDOW"):
            kind = str(getattr(vano, "kind", ""))
            categoria = "PUERTAS" if kind == "DOOR" else "VENTANAS"
            _piezas(categoria, str(getattr(vano, "code", "") or "?"),
                    float(getattr(vano, "width_m", 0.0) or 0.0))

    en_modulo = [p for p in piezas if p["en_modulo"]]
    fuera = [p for p in piezas if not p["en_modulo"]]
    desperdicio = sum(abs(p["residuo_m"]) for p in fuera)
    total = len(piezas)
    pct = round(len(en_modulo) / total * 100.0, 1) if total else 0.0
    return {
        "modulo_m": modulo,
        "modulo_nombre": _etiqueta_modulo(modulo),
        "total_piezas": total,
        "en_modulo": len(en_modulo),
        "fuera_modulo": len(fuera),
        "porcentaje_en_modulo": pct,
        "desperdicio_lineal_m": round(desperdicio, 2),
        "piezas_fuera": fuera,
        "nota": "evaluación para reducir desperdicios (§56): la "
                "modulación no bloquea el diseño, sugiere ajustes",
    }


def texto_modulacion(informe: Dict[str, Any]) -> str:
    """Informe de modulación cp1252 (sin flechas ni emojis)."""
    lineas = [f"MODULACIÓN CONSTRUCTIVA (catálogo §56) - "
              f"{informe.get('modulo_nombre', '')} = "
              f"{informe.get('modulo_m', 0.0):.2f} m"]
    lineas.append("")
    total = informe.get("total_piezas", 0)
    if not total:
        lineas.append("sin piezas trazadas en el proyecto: la "
                      "evaluación cubrirá locales, muros, puertas y "
                      "ventanas cuando existan")
    else:
        lineas.append(f"{informe.get('en_modulo', 0)} de {total} "
                      f"piezas en módulo "
                      f"({informe.get('porcentaje_en_modulo', 0.0)} %)"
                      f"; residuo lineal acumulado "
                      f"{informe.get('desperdicio_lineal_m', 0.0):.2f} m")
    fuera = informe.get("piezas_fuera", [])
    if fuera:
        lineas.append("")
        lineas.append("Piezas fuera de módulo (sugerencia al múltiplo "
                      "inferior / superior):")
        for p in fuera[:40]:
            sug = p.get("sugerencias_m", [0.0, 0.0])
            lineas.append(
                f"· [{p['categoria']}] {p['nombre']}: "
                f"{p['dimension_m']:.2f} m -> sugerido "
                f"{sug[0]:.2f} m o {sug[1]:.2f} m "
                f"(residuo {p['residuo_m']:+.2f} m)")
        if len(fuera) > 40:
            lineas.append(f"· ... y {len(fuera) - 40} más")
    if informe.get("nota"):
        lineas.append("")
        lineas.append(str(informe["nota"]))
    return "\n".join(lineas)


# ----------------------------------------------------------------------
# 3. ENERGÍA SOLAR (§38)
# ----------------------------------------------------------------------

def _parametros_solar(catalogo: Any) -> Dict[str, Any]:
    if catalogo is None:
        from domain.vivienda_specs import cargar_catalogo
        catalogo = cargar_catalogo()
    return dict((catalogo.energia_solar if catalogo is not None
                 else {}) or {})


def dimensionar_solar(consumo_diario_kwh: float = 0.0,
                      horas_sol_pico: float = 0.0,
                      potencia_panel_w: float = 0.0,
                      eficiencia: float = 0.0,
                      perdidas: float = 0.0,
                      sistema: str = FOTOVOLTAICO,
                      autonomia_dias: float = 0.0,
                      ocupantes: int = 4,
                      con_bateria: bool = True,
                      catalogo: Any = None) -> Dict[str, Any]:
    """Dimensiona el sistema solar del §38 (FOTOVOLTAICO, SOLAR_TERMICO
    o HIBRIDO) con los parámetros de referencia del catálogo
    (configurables, §66). Lanza ARQ-SOL-001 si algún parámetro no
    permite calcular. Sólo cálculo paramétrico: no toca el proyecto.
    """
    sistema = str(sistema or FOTOVOLTAICO).strip().upper()
    if sistema not in (FOTOVOLTAICO, SOLAR_TERMICO, HIBRIDO):
        raise DomainError(
            message=f"Sistema solar «{sistema}» no reconocido",
            code="ARQ-SOL-001",
            suggested_action="Usa FOTOVOLTAICO, SOLAR_TERMICO o "
                             "HIBRIDO (sección 38).")
    p = _parametros_solar(catalogo)

    def _num(valor: Any, defecto: float, nombre: str, minimo: float,
             maximo: float = 1e9) -> float:
        try:
            v = float(valor)
        except (TypeError, ValueError):
            v = 0.0
        if v <= 0.0:
            v = float(defecto)
        if not (minimo <= v <= maximo):
            raise DomainError(
                message=f"El parámetro {nombre} = {valor} está fuera "
                        f"de rango ({minimo:g} a {maximo:g})",
                code="ARQ-SOL-001",
                context={nombre: valor},
                suggested_action="Revisa el valor o deja el "
                                 "parámetro vacío para usar el de "
                                 "referencia del catálogo.")
        return v

    consumo = _num(consumo_diario_kwh,
                   p.get("consumo_diario_kwh_defecto", 6.0),
                   "consumo diario", 0.1, 1000.0)
    hsp = _num(horas_sol_pico, p.get("horas_sol_pico_defecto", 5.0),
               "horas de sol pico", 1.0, 12.0)
    panel_w = _num(potencia_panel_w,
                   p.get("potencia_panel_w_defecto", 450.0),
                   "potencia del panel", 10.0, 2000.0)
    ef = _num(eficiencia, p.get("eficiencia_defecto", 0.20),
              "eficiencia del panel", 0.05, 1.0)
    per = _num(perdidas, p.get("perdidas_defecto", 0.15),
               "pérdidas del sistema", 0.0, 0.9)
    auto = _num(autonomia_dias, p.get("autonomia_dias_defecto", 1.0),
                "autonomía", 0.0, 30.0)
    ocupantes = int(max(1, min(int(ocupantes or 4), 20)))
    dod = float(p.get("profundidad_descarga", 0.8)) or 0.8
    area_panel = float(p.get("area_panel_m2", 2.0)) or 2.0

    resultado: Dict[str, Any] = {
        "sistema": sistema,
        "entradas": {
            "consumo_diario_kwh": consumo,
            "horas_sol_pico": hsp,
            "potencia_panel_w": panel_w,
            "eficiencia": ef,
            "perdidas": per,
            "autonomia_dias": auto,
            "ocupantes": ocupantes,
            "con_bateria": bool(con_bateria),
        },
    }
    if sistema in (FOTOVOLTAICO, HIBRIDO):
        energia_panel = hsp * (panel_w / 1000.0) * ef * (1.0 - per)
        paneles = math.ceil(consumo / max(energia_panel, 1e-9))
        potencia_kw = paneles * panel_w / 1000.0
        bateria = round(consumo * auto / dod, 2) \
            if (con_bateria and auto > 0) else 0.0
        inversor = math.ceil(potencia_kw * 1.25 * 2.0) / 2.0
        resultado["fv"] = {
            "energia_panel_kwh_dia": round(energia_panel, 4),
            "numero_paneles": paneles,
            "potencia_total_kw": round(potencia_kw, 2),
            "capacidad_bateria_kwh": bateria,
            "potencia_inversor_kw": inversor,
            "superficie_requerida_m2": round(paneles * area_panel, 1),
        }
    if sistema in (SOLAR_TERMICO, HIBRIDO):
        colectores = round(ocupantes
                           * float(p.get("colector_m2_por_persona",
                                         1.0)), 1)
        tanque = int(ocupantes
                     * float(p.get("tanque_l_por_persona", 50.0)))
        resultado["termico"] = {
            "colectores_m2": colectores,
            "tanque_l": tanque,
        }
    resultado["advertencia"] = (
        "instalación definitiva: REQUIERE_CALCULO_ESPECIALIZADO "
        "(sección 81); el dimensionado preliminar no sustituye al "
        "cálculo del proyectista según la norma eléctrica adoptada")
    if p.get("nota"):
        resultado["nota_datos"] = str(p["nota"])
    return resultado


def texto_solar(informe: Dict[str, Any]) -> str:
    """Informe del dimensionado solar cp1252 (sin flechas ni emojis)."""
    nombre = {"FOTOVOLTAICO": "FOTOVOLTAICO", "SOLAR_TERMICO":
              "SOLAR TÉRMICO", "HIBRIDO": "HÍBRIDO (FV + térmico)"}.get(
        informe.get("sistema", ""), informe.get("sistema", ""))
    lineas = ["ENERGÍA SOLAR (catálogo §38) - sistema " + nombre]
    entra = informe.get("entradas", {})
    lineas.append(
        f"consumo {entra.get('consumo_diario_kwh', 0.0):.2f} kWh/día, "
        f"{entra.get('horas_sol_pico', 0.0):.1f} h de sol pico, panel "
        f"{entra.get('potencia_panel_w', 0.0):.0f} W con eficiencia "
        f"{entra.get('eficiencia', 0.0) * 100:.0f} % y pérdidas "
        f"{entra.get('perdidas', 0.0) * 100:.0f} %")
    fv = informe.get("fv")
    if fv:
        lineas.append("")
        lineas.append("Campo fotovoltaico:")
        lineas.append(f"· energía por panel: "
                      f"{fv['energia_panel_kwh_dia']:.3f} kWh/día")
        lineas.append(f"· número de paneles: {fv['numero_paneles']}")
        lineas.append(f"· potencia total: "
                      f"{fv['potencia_total_kw']:.2f} kW")
        if fv.get("capacidad_bateria_kwh", 0.0) > 0:
            lineas.append(f"· batería: "
                          f"{fv['capacidad_bateria_kwh']:.2f} kWh "
                          f"(autonomía "
                          f"{entra.get('autonomia_dias', 0.0):.1f} día/s)")
        else:
            lineas.append("· sin batería (vertida a red o solo diurno)")
        lineas.append(f"· inversor: "
                      f"{fv['potencia_inversor_kw']:.1f} kW")
        lineas.append(f"· superficie requerida: "
                      f"{fv['superficie_requerida_m2']:.1f} m2 de "
                      "techo")
    termico = informe.get("termico")
    if termico:
        lineas.append("")
        lineas.append("Solar térmico (agua caliente):")
        lineas.append(f"· colectores: {termico['colectores_m2']:.1f} m2 "
                      f"para {entra.get('ocupantes', '?')} ocupantes")
        lineas.append(f"· tanque: {termico['tanque_l']} L")
    if informe.get("advertencia"):
        lineas.append("")
        lineas.append(str(informe["advertencia"]))
    if informe.get("nota_datos"):
        lineas.append("")
        lineas.append(str(informe["nota_datos"]))
    return "\n".join(lineas)


__all__ = [
    "AlternativaV", "MODULOS_ESTANDAR", "TOLERANCIA_MODULO_M",
    "FOTOVOLTAICO", "SOLAR_TERMICO", "HIBRIDO",
    "generar_alternativas", "texto_alternativas",
    "evaluar_modulacion", "texto_modulacion",
    "dimensionar_solar", "texto_solar",
]

"""Especificaciones técnicas hospitalarias (v3.22.0).

Integra en el programa el documento «Especificaciones técnicas
integrales para locales hospitalarios» (fichas de locales, cuadro de
cotas MIN/REC, matriz de prioridad funcional, flujos, checklist de
validación dimensional y fuentes) como datos versionados bajo
``resources/knowledge/hospital_specs.json`` — nunca hardcodeados.

La pieza operativa es el CONTROL DE VALIDACIÓN DIMENSIONAL (sección 19
del documento): cada local del proyecto se comprueba contra las cotas
de su uso — superficie, ancho, altura, puerta y pasillo — y se le
adjunta el checklist completo con lo que la geometría puede decidir
(marcado «medido») y lo que corresponde a cálculo o fabricante
(marcado «pendiente», porque una cota de programación o de equipo
NUNCA se convierte automáticamente en normativa: clasificación de
cotas tipo A-F de la sección 18).

Uso headless:
    from domain.hospital_specs import cargar_specs, validar_local
    informe = validar_local(ctx, "SP-001")
    print(texto_validacion(informe))
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.paths import resource_path
from core.errors import DomainError

_SPECS_CACHE: List["HospitalSpecs"] = []

# etiquetas legibles de los campos del cuadro de cotas (cp1252)
ETIQUETAS_CAMPO: Dict[str, str] = {
    "función": "Función",
    "relaciones": "Relaciones",
    "arquitectura": "Arquitectura",
    "electricidad": "Electricidad",
    "iluminación": "Iluminación",
    "hidráulica": "Hidráulica",
    "hvac": "HVAC",
    "higiene": "Higiene",
    "equipamiento": "Equipamiento",
    "gases": "Gases medicinales",
    "radiación": "Radiación",
    "presión": "Presión",
    "seguridad": "Seguridad",
    "bioclimática": "Bioclimática",
    "dimensionamiento": "Dimensionamiento",
    "requisitos": "Requisitos",
    "subáreas": "Subáreas",
}

# campos de ficha en el orden en que salen en el PDF
ORDEN_CAMPOS: Tuple[str, ...] = (
    "función", "relaciones", "arquitectura", "electricidad",
    "iluminación", "hidráulica", "hvac", "gases", "radiación",
    "presión", "higiene", "equipamiento", "seguridad", "bioclimática",
    "dimensionamiento", "requisitos", "subáreas",
)


@dataclass
class Hallazgo:
    """Resultado de una comprobación del control dimensional."""

    codigo: str
    severidad: str          # "ok" | "aviso" | "fallo" | "info"
    mensaje: str
    cota_tipo: str = "B"    # clasificación A-F del documento
    fuente: str = ""

    def como_dict(self) -> Dict[str, Any]:
        return {"codigo": self.codigo, "severidad": self.severidad,
                "mensaje": self.mensaje, "cota_tipo": self.cota_tipo,
                "fuente": self.fuente}


@dataclass
class HospitalSpecs:
    """Registro del documento hospitalario versionado."""

    version: str = ""
    fuente_doc: str = ""
    advertencia: str = ""
    prioridad: Dict[str, str] = field(default_factory=dict)
    flujos: List[str] = field(default_factory=list)
    fichas: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cotas_cuadro: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cotas_de_tipo: Dict[str, Any] = field(default_factory=dict)
    cotas_puertas: List[Dict[str, Any]] = field(default_factory=list)
    cotas_mobiliario: List[Dict[str, Any]] = field(default_factory=list)
    checklist: List[str] = field(default_factory=list)
    fuentes: List[str] = field(default_factory=list)
    clasificacion: Dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    @staticmethod
    def load_file(path: str) -> "HospitalSpecs":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("format") != "ARQ_GEN_HOSPITAL_SPECS":
            raise DomainError(
                message="El archivo de especificaciones hospitalarias no "
                        "tiene el formato esperado",
                code="ARQ-HSP-001",
                context={"format": data.get("format")},
                suggested_action="Restaure resources/knowledge/"
                                 "hospital_specs.json del paquete.")
        return HospitalSpecs(
            version=str(data.get("version", "")),
            fuente_doc=str(data.get("source", "")),
            advertencia=str(data.get("advertencia", "")),
            prioridad=dict(data.get("prioridad", {})),
            flujos=list(data.get("flujos", [])),
            fichas=dict(data.get("fichas", {})),
            cotas_cuadro=dict(data.get("cotas_cuadro", {})),
            cotas_de_tipo=dict(data.get("cotas_de_tipo", {})),
            cotas_puertas=list(data.get("cotas_puertas", [])),
            cotas_mobiliario=list(data.get("cotas_mobiliario", [])),
            checklist=list(data.get("checklist_validacion", [])),
            fuentes=list(data.get("fuentes", [])),
            clasificacion=dict(data.get("clasificacion_cotas", {})),
        )

    # ------------------------------------------------------------------
    def ficha(self, space_type: str) -> Optional[Dict[str, Any]]:
        """Ficha técnica cualitativa del uso (o None si no consta)."""
        return self.fichas.get(str(space_type or ""))

    def cuadro(self, space_type: str) -> Optional[Dict[str, Any]]:
        """Subsección del cuadro de cotas que define al uso."""
        destino = self.cotas_de_tipo.get(str(space_type or ""))
        if not destino:
            return None
        sub, _item = destino
        return self.cotas_cuadro.get(sub)

    def item_cotas(self, space_type: str) -> Optional[Dict[str, Any]]:
        """Ítem concreto del cuadro que representa al uso (o el cuadro
        entero cuando el tipo no está atado a un solo ítem)."""
        destino = self.cotas_de_tipo.get(str(space_type or ""))
        if not destino:
            return None
        sub, item = destino
        cuadro = self.cotas_cuadro.get(sub)
        if cuadro is None:
            return None
        if item:
            for candidato in cuadro.get("items", []):
                if str(candidato.get("nombre", "")).strip().lower() \
                        == item.strip().lower():
                    return candidato
            return cuadro
        # sin ítem anclado: el primero del cuadro que traiga cotas
        for candidato in cuadro.get("items", []):
            if candidato.get("min_m2") or candidato.get("rec_m2"):
                return candidato
        return cuadro

    def prioridad_de(self, space_type: str) -> str:
        """Nivel funcional del uso: critica / alta / media / baja."""
        return self.prioridad.get(str(space_type or ""), "")

    def _nivel(self, rango: Optional[Dict[str, Any]]) -> Optional[float]:
        if not rango:
            return None
        try:
            return float(rango.get("min"))
        except (TypeError, ValueError):
            return None


# ----------------------------------------------------------------------
def cargar_specs() -> Optional[HospitalSpecs]:
    """Carga (una vez) el documento de especificaciones; None si falta.

    Sin el recurso el programa sigue funcionando como siempre: las
    especificaciones aconsejan, no bloquean.
    """
    if _SPECS_CACHE:
        return _SPECS_CACHE[0]
    try:
        path = resource_path("knowledge", "hospital_specs.json")
        if not os.path.exists(path):
            return None
        specs = HospitalSpecs.load_file(path)
        _SPECS_CACHE.append(specs)
        return specs
    except Exception:  # noqa: BLE001 — recurso dañado: reglas clásicas
        return None


def _resumen_specs(specs: HospitalSpecs) -> Dict[str, Any]:
    return {
        "fichas": len(specs.fichas),
        "cuadros": len(specs.cotas_cuadro),
        "checklist": len(specs.checklist),
        "flujos": len(specs.flujos),
        "fuentes": len(specs.fuentes),
        "tipos_con_prioridad": len(specs.prioridad),
    }


# ----------------------------------------------------------------------
# VALIDACIÓN DIMENSIONAL (sección 19 del documento)
# ----------------------------------------------------------------------

def validar_local(ctx: Any, ref: str) -> Dict[str, Any]:
    """Control de validación dimensional de UN local (§19).

    Comprueba contra las cotas del uso y del DNA: superficie, ancho,
    altura (cota del nivel), puertas y pasillos del nivel. El resto
    del checklist (equipo, HVAC, gases, radioprotección...) queda
    «pendiente»: es de cálculo o de fabricante, no de geometría.
    Sólo LEE el proyecto: no crea entidades ni necesita commit.
    """
    specs = cargar_specs()
    if specs is None:
        raise DomainError(
            message="No se encontró el documento de especificaciones "
                    "hospitalarias",
            code="ARQ-HSP-002",
            suggested_action="Verifique resources/knowledge/"
                             "hospital_specs.json.")
    from ui.editor_espacios import datos_local, _resolver_local
    datos = datos_local(ctx, ref)
    local = _resolver_local(ctx, ref)
    uso = str(datos.get("uso") or "ROOM")
    hallazgos: List[Hallazgo] = []

    # V01 superficie ----------------------------------------------------
    item = specs.item_cotas(uso)
    sup_min = None
    if item:
        sup_min = specs._nivel(item.get("min_m2"))
    dna = _dna_de(ctx, uso)
    if sup_min is None and dna is not None:
        try:
            sup_min = float(getattr(dna, "minimum_area", 0.0) or 0.0) \
                or None
        except (TypeError, ValueError):
            sup_min = None
    area = float(datos.get("area_m2") or 0.0)
    tipo_cota = "B"
    if sup_min:
        if area + 1e-9 >= sup_min:
            hallazgos.append(Hallazgo(
                "V01", "ok",
                f"superficie {area:.2f} m2 >= mínima de programación "
                f"{sup_min:.2f} m2", tipo_cota,
                "cuadro de cotas / DNA del uso"))
        else:
            hallazgos.append(Hallazgo(
                "V01", "fallo",
                f"superficie {area:.2f} m2 < mínima de programación "
                f"{sup_min:.2f} m2", tipo_cota,
                "cuadro de cotas / DNA del uso"))
    else:
        hallazgos.append(Hallazgo(
            "V01", "info",
            f"superficie {area:.2f} m2; el uso no tiene mínima en el "
            "cuadro ni en el DNA", tipo_cota))

    # V02 ancho -----------------------------------------------------------
    ancho = float(datos.get("ancho_m") or 0.0)
    ancho_min = _ancho_minimo(ctx, uso)
    if ancho_min:
        if ancho + 1e-9 >= ancho_min:
            hallazgos.append(Hallazgo(
                "V02", "ok", f"ancho {ancho:.2f} m >= {ancho_min:.2f} m",
                "B", "DNA del uso (minimum_width)"))
        else:
            hallazgos.append(Hallazgo(
                "V02", "fallo",
                f"ancho {ancho:.2f} m < {ancho_min:.2f} m del uso",
                "B", "DNA del uso (minimum_width)"))

    # V03 altura (cota del nivel) -----------------------------------------
    altura_rec = _altura_recomendada(specs, uso, ctx)
    altura_nivel = _altura_nivel(ctx, local)
    if altura_rec and altura_nivel > 0:
        if altura_rec - 1e-9 <= altura_nivel:
            hallazgos.append(Hallazgo(
                "V03", "ok",
                f"altura del nivel ({altura_nivel:.2f} m) >= "
                f"recomendada del uso ({altura_rec:.2f} m)", "C",
                "ficha del uso"))
        else:
            hallazgos.append(Hallazgo(
                "V03", "aviso",
                f"altura del nivel ({altura_nivel:.2f} m) por debajo "
                f"de la recomendada del uso ({altura_rec:.2f} m)",
                "C", "ficha del uso"))

    # V04 puertas ---------------------------------------------------------
    puerta_min = _puerta_minima(ctx, uso)
    if puerta_min:
        estrechas = [p for p in datos.get("puertas", [])
                     if _ancho_de_vano(ctx, p) is not None
                     and _ancho_de_vano(ctx, p) + 1e-9 < puerta_min]
        if not datos.get("puertas"):
            hallazgos.append(Hallazgo(
                "V04", "aviso", "el local no tiene puertas", "B",
                "control de accesos"))
        elif estrechas:
            detalle = ", ".join(
                f"{p} ({_ancho_de_vano(ctx, p) or 0.0:.2f} m)"
                for p in estrechas)
            hallazgos.append(Hallazgo(
                "V04", "fallo",
                f"puerta(s) {detalle} por debajo de "
                f"{puerta_min:.2f} m del uso", "B",
                "cuadro de cotas / DNA del uso"))
        else:
            hallazgos.append(Hallazgo(
                "V04", "ok",
                f"todas las puertas >= {puerta_min:.2f} m", "B",
                "cuadro de cotas / DNA del uso"))

    # V05 pasillo del nivel -----------------------------------------------
    pasillo_min = _pasillo_minimo(ctx, uso)
    if pasillo_min:
        estrechos = _pasillos_estrechos(ctx, datos, pasillo_min)
        if estrechos is None:
            hallazgos.append(Hallazgo(
                "V05", "info",
                "el nivel no tiene pasillos trazados que comprobar",
                "B", "DNA del uso (pasillo_m)"))
        elif estrechos:
            hallazgos.append(Hallazgo(
                "V05", "aviso",
                f"pasillo(s) {', '.join(estrechos)} por debajo de "
                f"{pasillo_min:.2f} m del uso", "B",
                "DNA del uso (pasillo_m)"))
        else:
            hallazgos.append(Hallazgo(
                "V05", "ok",
                f"pasillos del nivel >= {pasillo_min:.2f} m", "B",
                "DNA del uso (pasillo_m)"))

    # checklist completo (§19): lo medido y lo pendiente ------------------
    checklist = _checklist_de(specs, hallazgos)
    prioridad = specs.prioridad_de(uso)
    ficha = specs.ficha(uso)
    return {
        "local": datos.get("codigo"),
        "nombre": datos.get("nombre"),
        "uso": uso,
        "area_m2": area,
        "ancho_m": ancho,
        "prioridad": prioridad,
        "cotas": item,
        "ficha": ficha,
        "hallazgos": [h.como_dict() for h in hallazgos],
        "checklist": checklist,
        "advertencia": specs.advertencia,
        "fuentes": specs.fuentes,
        "specs": _resumen_specs(specs),
    }


def validar_proyecto(ctx: Any) -> Dict[str, Any]:
    """Valida TODOS los locales con geometría del proyecto (§19).

    Devuelve ``{locales: [informe...], resumen: {ok, avisos, fallos,
    pendientes}}``; un local sin especificaciones aplicables sale con
    el hallazgo informativo de siempre.
    """
    locales = list(ctx.architecture.list("SPACE", ctx.project.id))
    informes: List[Dict[str, Any]] = []
    resumen = {"ok": 0, "avisos": 0, "fallos": 0, "pendientes": 0}
    for local in locales:
        if len(getattr(local, "boundary", []) or []) < 3:
            continue
        try:
            informe = validar_local(ctx, local.id)
        except Exception:  # noqa: BLE001 — un local no debe tumbar el resto
            continue
        informes.append(informe)
        for h in informe["hallazgos"]:
            if h["severidad"] == "ok":
                resumen["ok"] += 1
            elif h["severidad"] == "aviso":
                resumen["avisos"] += 1
            elif h["severidad"] == "fallo":
                resumen["fallos"] += 1
            else:
                resumen["pendientes"] += 1
    return {"locales": informes, "resumen": resumen}


def _checklist_de(specs: HospitalSpecs,
                  hallazgos: List[Hallazgo]) -> List[Dict[str, Any]]:
    """El checklist §19 completo: cada punto, su estado y quién manda.

    Los códigos V01-V05 cubren lo geométrico; el resto queda
    «pendiente» con su clasificación de cota (cálculo/fabricante/
    especialidad), exactamente como pide el documento.
    """
    mapa = {"V01": 0, "V02": 1, "V03": 2, "V04": 3, "V05": 4}
    estados: List[Dict[str, Any]] = []
    for indice, punto in enumerate(specs.checklist):
        entrada: Dict[str, Any] = {"punto": punto, "estado": "pendiente",
                                   "detalle": "", "cota_tipo": ""}
        for codigo, posicion in mapa.items():
            if posicion != indice:
                continue
            hallado = next((h for h in hallazgos if h.codigo == codigo),
                           None)
            if hallado is None:
                break
            entrada["estado"] = {"ok": "cumple", "fallo": "no cumple",
                                 "aviso": "revisar",
                                 "info": "informativo"}[hallado.severidad]
            entrada["detalle"] = hallado.mensaje
            entrada["cota_tipo"] = hallado.cota_tipo
            break
        estados.append(entrada)
    return estados


# ----------------------------------------------------------------------
# consultas de apoyo (DNA del uso; el DNA vive en el ctx del proyecto)
# ----------------------------------------------------------------------

def _dna_de(ctx: Any, uso: str) -> Any:
    registro = getattr(ctx, "dna_registry", None)
    if registro is None:
        return None
    try:
        return registro.get(str(uso or ""))
    except Exception:  # noqa: BLE001
        return None


def _ancho_minimo(ctx: Any, uso: str) -> Optional[float]:
    dna = _dna_de(ctx, uso)
    if dna is None:
        return None
    try:
        valor = float(getattr(dna, "minimum_width", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    return valor or None


def _puerta_minima(ctx: Any, uso: str) -> Optional[float]:
    dna = _dna_de(ctx, uso)
    if dna is None:
        return None
    try:
        valor = float((dna.metadata.get("neufert") or {}).get("puerta_m")
                      or 0.0)
    except (TypeError, ValueError):
        return None
    return valor or None


def _pasillo_minimo(ctx: Any, uso: str) -> Optional[float]:
    dna = _dna_de(ctx, uso)
    if dna is None:
        return None
    try:
        valor = float(dna.metadata.get("pasillo_m") or 0.0)
    except (TypeError, ValueError):
        return None
    return valor or None


def _altura_recomendada(specs: HospitalSpecs, uso: str, ctx: Any) \
        -> Optional[float]:
    # el cuadro del documento manda (REC 2.70-3.00); si no consta, el DNA
    item = specs.item_cotas(uso)
    if item:
        for nota in item.get("notas", []):
            texto = str(nota).lower()
            if "altura" in str(item.get("nombre", "")).lower() or \
                    "altura" in texto:
                import re
                m = re.search(r"([\d.,]+)\s*(?:-\s*([\d.,]+))?\s*m", texto)
                if m:
                    try:
                        return float(m.group(1).replace(",", "."))
                    except ValueError:
                        pass
    dna = _dna_de(ctx, uso)
    if dna is None:
        return None
    try:
        valor = float(getattr(dna, "height", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    return valor or None


def _altura_nivel(ctx: Any, local: Any) -> float:
    """Altura del nivel que hospeda al local (0 si no consta)."""
    try:
        nivel = ctx.architecture.get("LEVEL", local.level_id) \
            if getattr(local, "level_id", "") else None
        if nivel is not None:
            return float(getattr(nivel, "height_m", 0.0) or 0.0)
    except Exception:  # noqa: BLE001 — nivel ausente
        pass
    return 0.0


def _ancho_de_vano(ctx: Any, codigo: str) -> Optional[float]:
    try:
        for kind in ("DOOR", "WINDOW", "OPENING"):
            entidad = ctx.architecture.get_by_code(kind, codigo)
            if entidad is not None:
                return float(entidad.width_m)
    except Exception:  # noqa: BLE001 — código inexistente
        return None
    return None


def _pasillos_estrechos(ctx: Any, datos: Dict[str, Any],
                        minimo: float) -> Optional[List[str]]:
    """Códigos de pasillos (SP de uso CORRIDOR) del nivel < mínimo.

    None cuando el nivel no tiene pasillos que comprobar.
    """
    try:
        nivel = datos.get("level_id")
        pasillos = [s for s in ctx.architecture.list("SPACE",
                                                     ctx.project.id)
                    if getattr(s, "space_type", "") == "CORRIDOR"
                    and getattr(s, "level_id", None) == nivel
                    and len(getattr(s, "boundary", []) or []) >= 3]
    except Exception:  # noqa: BLE001 — sin arquitectura cargada
        return None
    if not pasillos:
        return None
    estrechos: List[str] = []
    for pasillo in pasillos:
        try:
            ancho = float(getattr(pasillo, "width_m", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if ancho <= 0:
            continue
        if ancho + 1e-9 < minimo:
            estrechos.append(str(getattr(pasillo, "code", "?")))
    return estrechos


# ----------------------------------------------------------------------
def texto_validacion(informe: Dict[str, Any]) -> str:
    """Informe del control §19 listo para la consola o el diagnóstico
    del asistente (texto cp1252, sin flechas ni emojis)."""
    lineas: List[str] = []
    lineas.append(f"VALIDACIÓN DIMENSIONAL - {informe.get('local')}"
                  f" ({informe.get('nombre') or ''})")
    if informe.get("prioridad"):
        lineas.append(f"Prioridad funcional: "
                      f"{str(informe['prioridad']).upper()}")
    lineas.append("")
    for h in informe.get("hallazgos", []):
        marca = {"ok": "[OK]", "fallo": "[X]", "aviso": "[!]",
                 "info": "[i]"}.get(h["severidad"], "[?]")
        tipo = f" (cota tipo {h['cota_tipo']})" if h.get("cota_tipo") \
            else ""
        lineas.append(f"{marca} {h['codigo']}: {h['mensaje']}{tipo}")
    lineas.append("")
    lineas.append("Control de validación dimensional (sección 19):")
    for punto in informe.get("checklist", []):
        simbolo = {"cumple": "[x]", "no cumple": "[ ]", "revisar": "[!]",
                   "informativo": "[i]",
                   "pendiente": "[ ]"}.get(punto["estado"], "[ ]")
        lineas.append(f"{simbolo} {punto['punto']}"
                      + (f" - {punto['detalle']}"
                         if punto.get("detalle") else ""))
    lineas.append("")
    lineas.append(str(informe.get("advertencia") or ""))
    return "\n".join(lineas)


__all__ = [
    "Hallazgo", "HospitalSpecs", "cargar_specs", "validar_local",
    "validar_proyecto", "texto_validacion", "ETIQUETAS_CAMPO",
    "ORDEN_CAMPOS",
]

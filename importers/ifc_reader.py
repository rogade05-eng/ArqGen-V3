"""IFC de ENTRADA (v3.13.0) — importador IFC4/IFC2X3 SPF (ISO-10303-21).

Complemento del exportador (exporters.ifc_exporter): lee un archivo
.ifc de TEXTO (STEP Physical File), resuelve las unidades, las
colocaciones anidadas (IfcLocalPlacement), las extrusiones
(IfcExtrudedAreaSolid con perfil rectangular o poligonal) y
reconstruye NIVELES, MUROS, LOCALES, PUERTAS y VENTANAS sobre el
proyecto actual a través de services.architecture_service
(ArchitectureService) — mismos comandos, códigos ARQ-XXX-nnn,
auditoría y undo que el resto de la app. Nada de dependencias nuevas:
el parser SPF es Python puro.

Subconjunto soportado (lo que omite se cuenta en «avisos», nunca
rompe): IfcProject/IfcSite/IfcBuilding/IfcBuildingStorey, IfcWall
(también IfcWallStandardCase), IfcSlab, IfcSpace, IfcDoor/IfcWindow
con IfcOpeningElement + IfcRelVoidsElement/IfcRelFillsElement,
perfiles IfcRectangleProfileDef e IfcArbitraryClosedProfileDef
(con o sin huecos) extruidos sobre Z. Unidades: METRE (1.0),
MILLIMETRE (0.001), CENTIMETRE (0.01) y FOOT (0.3048).

Los índices de atributos respetan el esquema IFC4: los productos son
(GlobalId, OwnerHistory, Name, Description, ObjectType, ObjectPlacement,
Representation, Tag); IfcRelContainedInSpatialStructure es (…,
RelatedElements, RelatingStructure); IfcProductDefinitionShape es (…,
Representations) e IfcShapeRepresentation es (…, Items).
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.errors import DomainError

Mat4 = Tuple[Tuple[float, float, float, float], ...]

_REF_RE = re.compile(r"#(\d+)\s*=\s*")
_ESCALA_UNIDADES: Dict[str, float] = {
    "METRE": 1.0, "MILLIMETRE": 0.001, "CENTIMETRE": 0.01, "FOOT": 0.3048,
}

_CLASE_MURO = ("IFCWALL", "IFCWALLSTANDARDCASE")
_CLASE_LOSA = ("IFCSLAB",)
_CLASE_LOCAL = ("IFCSPACE",)
_CLASE_PUERTA = ("IFCDOOR",)
_CLASE_VENTANA = ("IFCWINDOW",)


# -- errores -------------------------------------------------------------------
def _ref_primera(valor: Any) -> Optional[int]:
    """Saca el id de entidad de ``#n`` o del primer ``#n`` de una lista.

    Algunos escritores envuelven referencias únicas en listas ``(#n)``
    donde el esquema pide una ref simple; esto acepta ambas formas.
    """
    if isinstance(valor, tuple) and len(valor) == 2 and valor[0] == "REF":
        return valor[1]
    if isinstance(valor, list):
        for elemento in valor:
            if isinstance(elemento, tuple) and len(elemento) == 2 \
                    and elemento[0] == "REF":
                return elemento[1]
    return None


def _error_import(message: str, code: str = "ARQ-IFC-001") -> DomainError:
    return DomainError(
        message=message, code=code,
        suggested_action="Verifica que el archivo sea un IFC de texto "
                         "(STEP, ISO-10303-21) e inténtalo de nuevo.")


# -- parser SPF ---------------------------------------------------------------
def _quitar_comentarios(texto: str) -> str:
    return re.sub(r"/\*.*?\*/", " ", texto, flags=re.S)


def _find_semicolon(texto: str, desde: int, hasta: int) -> int:
    """Próximo ';' FUERA de cadenas (los nombres pueden contener ';')."""
    i = desde
    en_cadena = False
    while i < hasta:
        ch = texto[i]
        if en_cadena:
            if ch == "'":
                if i + 1 < hasta and texto[i + 1] == "'":
                    i += 1
                else:
                    en_cadena = False
        elif ch == "'":
            en_cadena = True
        elif ch == ";":
            return i
        i += 1
    return -1


def _partir_args(cuerpo: str) -> List[str]:
    """Parte los argumentos de una entidad al nivel de paréntesis 0.

    Respeta cadenas entre apóstrofos (con '' como escape) y listas
    anidadas entre paréntesis.
    """
    tokens: List[str] = []
    actual: List[str] = []
    profundidad = 0
    en_cadena = False
    i = 0
    while i < len(cuerpo):
        ch = cuerpo[i]
        if en_cadena:
            actual.append(ch)
            if ch == "'":
                if i + 1 < len(cuerpo) and cuerpo[i + 1] == "'":
                    actual.append("'")
                    i += 1
                else:
                    en_cadena = False
        elif ch == "'":
            actual.append(ch)
            en_cadena = True
        elif ch == "(":
            profundidad += 1
            actual.append(ch)
        elif ch == ")":
            profundidad -= 1
            actual.append(ch)
        elif ch == "," and profundidad == 0:
            tokens.append("".join(actual).strip())
            actual = []
        else:
            actual.append(ch)
        i += 1
    ultimo = "".join(actual).strip()
    if ultimo:
        tokens.append(ultimo)
    return tokens


def _parsear_token(tok: str) -> Any:
    """Convierte un token crudo SPF a Python (recursivo para listas).

    ``#12`` → ("REF", 12); ``'texto'`` → str; ``.ENUM.`` → str con
    puntos; ``$`` → None; números → int/float; ``(a,b)`` → lista.
    """
    tok = tok.strip()
    if tok in ("$", ""):
        return None
    if tok == "*":
        return "*"
    if tok.startswith("'") and tok.endswith("'") and len(tok) >= 2:
        return tok[1:-1].replace("''", "'")
    if tok.startswith("(") and tok.endswith(")"):
        return [_parsear_token(t) for t in _partir_args(tok[1:-1])]
    if tok.startswith(".") and tok.endswith(".") and len(tok) >= 3:
        return tok
    if tok.startswith("#"):
        try:
            return ("REF", int(tok[1:]))
        except ValueError:
            return tok
    try:
        if re.fullmatch(r"[+-]?\d+", tok):
            return int(tok)
        return float(tok)
    except ValueError:
        return tok


class _SPF:
    """Archivo STEP físico mínimo: entidades ``#id= NOMBRE(args);``."""

    def __init__(self, texto: str) -> None:
        limpio = _quitar_comentarios(texto)
        self._crudo = texto
        if "ISO-10303-21" not in limpio[:600]:
            raise _error_import(
                "El archivo no lleva cabecera ISO-10303-21: no parece "
                "un IFC de texto.")
        if "DATA;" not in limpio:
            raise _error_import("El IFC no tiene sección DATA.",
                                "ARQ-IFC-002")
        inicio = limpio.index("DATA;") + len("DATA;")
        fin = limpio.find("ENDSEC;", inicio)
        if fin < 0:
            fin = len(limpio)
        self.entidades: Dict[int, Tuple[str, List[Any]]] = {}
        pos = inicio
        while pos < fin:
            salto = _find_semicolon(limpio, pos, fin)
            if salto < 0:
                break
            trozo = limpio[pos:salto]
            pos = salto + 1
            m = _REF_RE.search(trozo)
            if not m:
                continue
            nombre_m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(",
                                trozo[m.end():])
            if not nombre_m:
                continue
            # El cuerpo llega con el «)» de cierre de la propia llamada:
            # NAME(args) → tras cortar «NAME(» queda «args)». Se quita
            # ese UNO paréntesis para que la profundidad cuadre.
            cuerpo = trozo[m.end() + nombre_m.end():].strip()
            if cuerpo.endswith(")"):
                cuerpo = cuerpo[:-1]
            args = [_parsear_token(t) for t in _partir_args(cuerpo)]
            self.entidades[int(m.group(1))] = (nombre_m.group(1).upper(),
                                               args)

    # -- acceso -----------------------------------------------------------
    def nombre(self, ref: Optional[Any]) -> str:
        ent = self._ent(ref)
        return ent[0] if ent else ""

    def args(self, ref: Optional[Any]) -> List[Any]:
        ent = self._ent(ref)
        return ent[1] if ent else []

    def _ent(self, ref: Optional[Any]) -> Optional[Tuple[str, List[Any]]]:
        if isinstance(ref, tuple) and len(ref) == 2 and ref[0] == "REF":
            return self.entidades.get(ref[1])
        if isinstance(ref, int) and not isinstance(ref, bool):
            return self.entidades.get(ref)
        return None

    def buscar_tipo(self, tipos: Sequence[str]) -> List[int]:
        return [eid for eid, (nombre, _a) in self.entidades.items()
                if nombre in tipos]

    def schema(self) -> str:
        m = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'",
                      _quitar_comentarios(self._crudo))
        return m.group(1) if m else ""


# -- matrices de colocación ------------------------------------------------------
def _identidad4() -> Mat4:
    return ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def _multiplica(a: Mat4, b: Mat4) -> Mat4:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(4))
                       for j in range(4)) for i in range(4))


def _aplica(m: Mat4, x: float, y: float, z: float) -> Tuple[float, float,
                                                            float]:
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def _normalizado(v: Tuple[float, float, float],
                 respaldo: Tuple[float, float, float]) -> Tuple[float, ...]:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-12:
        v = respaldo
        n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def _punto3(spf: _SPF, ref: Optional[Any]) -> List[float]:
    """Coordenadas de un IFCCARTESIANPOINT (desreferenciando la ref).

    Acepta también una lista inline de números por tolerancia.
    """
    if ref is None:
        return []
    valores = _componentes(spf, ref)
    if not valores and isinstance(ref, list):
        valores = [float(v) for v in ref if isinstance(v, (int, float))]
    return valores


def _matriz_axis2pl3d(spf: _SPF, ref: Optional[Any]) -> Mat4:
    """IfcAxis2Placement3D(Location, Axis, RefDirection) → Mat4."""
    args = spf.args(ref) if ref is not None else []
    locacion = _punto3(spf, args[0]) if args and args[0] is not None else []
    lx = locacion[0] if len(locacion) > 0 else 0.0
    ly = locacion[1] if len(locacion) > 1 else 0.0
    lz = locacion[2] if len(locacion) > 2 else 0.0
    eje_z = _normalizado(
        tuple(_componentes(spf, args[1])) if len(args) > 1
        and args[1] is not None else (0.0, 0.0, 1.0), (0.0, 0.0, 1.0))
    ref_dir = tuple(_componentes(spf, args[2])) if len(args) > 2 \
        and args[2] is not None else (1.0, 0.0, 0.0)
    dot = ref_dir[0] * eje_z[0] + ref_dir[1] * eje_z[1] \
        + ref_dir[2] * eje_z[2]
    ref_orto = (ref_dir[0] - dot * eje_z[0],
                ref_dir[1] - dot * eje_z[1],
                ref_dir[2] - dot * eje_z[2])
    eje_x = _normalizado(ref_orto, (1.0, 0.0, 0.0))
    eje_y = (eje_z[1] * eje_x[2] - eje_z[2] * eje_x[1],
             eje_z[2] * eje_x[0] - eje_z[0] * eje_x[2],
             eje_z[0] * eje_x[1] - eje_z[1] * eje_x[0])
    return ((eje_x[0], eje_y[0], eje_z[0], lx),
            (eje_x[1], eje_y[1], eje_z[1], ly),
            (eje_x[2], eje_y[2], eje_z[2], lz),
            (0.0, 0.0, 0.0, 1.0))


def _componentes(spf: _SPF, ref: Optional[Any]) -> List[float]:
    """Lista de números de una IFCDIRECTION/IFCCARTESIANPOINT."""
    args = spf.args(ref) if ref is not None else []
    valores = args[0] if args and isinstance(args[0], list) else []
    return [float(v) for v in valores if isinstance(v, (int, float))]


def _matriz_axis2pl2d(spf: _SPF, ref: Optional[Any]) -> Mat4:
    """IfcAxis2Placement2D(Location, RefDirection) → Mat4 (z=0)."""
    args = spf.args(ref) if ref is not None else []
    locacion = _punto3(spf, args[0]) if args and args[0] is not None else []
    lx = locacion[0] if len(locacion) > 0 else 0.0
    ly = locacion[1] if len(locacion) > 1 else 0.0
    ref_dir = args[1] if len(args) > 1 and args[1] is not None \
        else [1.0, 0.0]
    if isinstance(ref_dir, list) and ref_dir:
        x = _normalizado((float(ref_dir[0]), float(ref_dir[1]), 0.0),
                         (1.0, 0.0, 0.0))
    else:
        x = (1.0, 0.0, 0.0)
    y = (-x[1], x[0], 0.0)
    return ((x[0], y[0], 0.0, lx),
            (x[1], y[1], 0.0, ly),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0))


@dataclass
class _Solido:
    """Sólido extruido resuelto en coordenadas del mundo (metros)."""

    eid: int = 0
    clase: str = ""
    nombre: str = ""
    etiqueta: str = ""
    contorno: List[Tuple[float, float]] = field(default_factory=list)
    z0: float = 0.0
    altura: float = 0.0
    storey_ref: int = 0


class IfcImporter:
    """Importador del subconjunto IFC → proyecto ARQ GEN."""

    # -- API pública -------------------------------------------------------
    def preview(self, path: str) -> Dict[str, Any]:
        """Analiza sin tocar el proyecto (como el importador DXF)."""
        spf = self._cargar(path)
        escala = self._escala(spf)
        solidos, avisos = self._solidos(spf, escala)
        return {
            "schema": spf.schema(),
            "unidad": _nombre_unidad(escala),
            "storeys": len(spf.buscar_tipo(("IFCBUILDINGSTOREY",))),
            "walls": sum(1 for s in solidos if s.clase == "WALL"),
            "spaces": sum(1 for s in solidos if s.clase == "SPACE"),
            "doors": sum(1 for s in solidos if s.clase == "DOOR"),
            "windows": sum(1 for s in solidos if s.clase == "WINDOW"),
            "slabs": sum(1 for s in solidos if s.clase == "SLAB"),
            "otros": sum(1 for s in solidos if s.clase == "OTRO"),
            "avisos": avisos,
        }

    def apply(self, path: str, architecture: Any) -> Dict[str, Any]:
        """Crea niveles/muros/locales/vanos en el proyecto actual.

        Los niveles con nombre ya existente se REUTILIZAN (reimportar
        no duplica plantas). Devuelve un resumen con conteos y avisos.
        """
        spf = self._cargar(path)
        escala = self._escala(spf)
        solidos, avisos = self._solidos(spf, escala)
        resumen: Dict[str, Any] = {
            "niveles": 0, "niveles_reutilizados": 0, "muros": 0,
            "locales": 0, "puertas": 0, "ventanas": 0,
            "losas_omitidas": 0, "otros_omitidos": 0, "avisos": avisos,
        }
        # -- niveles por cota -------------------------------------------
        storeys: List[Tuple[int, str, float]] = []
        for sid in spf.buscar_tipo(("IFCBUILDINGSTOREY",)):
            args = spf.args(sid)
            nombre = str(args[2]) if len(args) > 2 and isinstance(
                args[2], str) and args[2].strip() else \
                "Nivel IFC %d" % (len(storeys) + 1)
            cota = 0.0
            if len(args) > 8 and isinstance(args[8], (int, float)):
                cota = float(args[8]) * escala
            else:
                cota = self._cota_de_placement(spf, args) * escala
            storeys.append((sid, nombre, cota))
        storeys.sort(key=lambda t: (t[2], t[1]))
        niveles: Dict[int, str] = {}
        alturas: Dict[int, float] = {}
        for s in solidos:
            if s.storey_ref and s.altura > 0.0:
                alturas[s.storey_ref] = max(
                    alturas.get(s.storey_ref, 0.0), s.altura)
        existentes: Dict[str, str] = {}
        for nivel in architecture.ctx.architecture.list(
                "LEVEL", architecture.ctx.project.id):
            existentes[nivel.name.strip().lower()] = nivel.name
        for sid, nombre, cota in storeys:
            clave = nombre.strip().lower()
            if clave in existentes:
                niveles[sid] = existentes[clave]
                resumen["niveles_reutilizados"] += 1
                continue
            altura = alturas.get(sid, 0.0) or 3.0
            nivel = architecture.create_level(
                name=nombre, elevation_m=round(cota, 4),
                height_m=round(altura, 3))
            niveles[sid] = nivel.name
            existentes[clave] = nivel.name
            resumen["niveles"] += 1
        cotas: Dict[str, float] = {}
        for nivel in architecture.ctx.architecture.list(
                "LEVEL", architecture.ctx.project.id):
            cotas[nivel.name] = float(getattr(nivel, "elevation_m", 0.0)
                                      or 0.0)
        # -- muros, locales, losas/otros ---------------------------------
        muros_creados: Dict[int, Any] = {}
        for indice, solido in enumerate(solidos):
            if solido.clase == "WALL":
                if not niveles.get(solido.storey_ref):
                    avisos.append("Muro «%s» sin nivel asociado: omitido."
                                  % (solido.nombre or solido.etiqueta))
                    continue
                reconstruido = self._muro_de_solido(solido)
                if reconstruido is None:
                    avisos.append("Muro «%s» con huella no utilizable: "
                                  "omitido." % (solido.nombre
                                                or solido.etiqueta))
                    continue
                (p1, p2), espesor, altura = reconstruido
                try:
                    muro = architecture.create_wall(
                        niveles[solido.storey_ref], p1, p2,
                        thickness_m=round(espesor, 4),
                        height_m=round(altura, 3))
                except DomainError as exc:
                    avisos.append("Muro «%s» omitido: %s"
                                  % (solido.nombre or solido.etiqueta,
                                     exc.message))
                    continue
                muros_creados[indice] = muro
                resumen["muros"] += 1
            elif solido.clase == "SPACE":
                if not niveles.get(solido.storey_ref) \
                        or len(solido.contorno) < 3:
                    continue
                try:
                    architecture.create_space(
                        niveles[solido.storey_ref],
                        solido.nombre or "Local IFC", "ROOM",
                        [(round(x, 4), round(y, 4))
                         for x, y in solido.contorno])
                except DomainError as exc:
                    avisos.append("Local «%s» omitido: %s"
                                  % (solido.nombre, exc.message))
                    continue
                resumen["locales"] += 1
            elif solido.clase == "SLAB":
                resumen["losas_omitidas"] += 1
            elif solido.clase == "OTRO":
                resumen["otros_omitidos"] += 1
        puertas, ventanas = self._vanos(spf, solidos, muros_creados,
                                        architecture, niveles, cotas,
                                        avisos)
        resumen["puertas"] = puertas
        resumen["ventanas"] = ventanas
        if not (resumen["muros"] or resumen["locales"]
                or resumen["puertas"] or resumen["ventanas"]):
            avisos.append("No se encontró geometría utilizable "
                          "(muros, locales o vanos) en el archivo.")
        return resumen

    # -- carga -------------------------------------------------------------
    def _cargar(self, path: str) -> _SPF:
        if not os.path.isfile(path):
            raise _error_import("No existe el archivo IFC: %s" % path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                texto = f.read()
        except OSError as exc:
            raise _error_import(
                "No se pudo leer el IFC: %s" % exc) from exc
        return _SPF(texto)

    def _escala(self, spf: _SPF) -> float:
        """Factor a metros desde las unidades del IfcProject.

        IfcProject.UnitsInContext (atributo 8) es UNA ref a
        IfcUnitAssignment y DENTRO vienen los IfcSIUnit; por tolerancia
        se acepta también la lista de unidades directa o anidada.
        """
        for pid in spf.buscar_tipo(("IFCPROJECT",)):
            args = spf.args(pid)
            units_ref = args[8] if len(args) > 8 else None
            candidatos: List[Any] = []
            if isinstance(units_ref, tuple):
                candidatos = [units_ref]
            elif isinstance(units_ref, list):
                candidatos = [u for u in units_ref if isinstance(u, tuple)]
            refs_unidades: List[Any] = []
            for cand in candidatos:
                if spf.nombre(cand) == "IFCUNITASSIGNMENT":
                    uargs = spf.args(cand)
                    interior = uargs[0] if uargs and isinstance(
                        uargs[0], list) else []
                    if interior and isinstance(interior[0], list):
                        # lista anidada doble: ((#a,#b),)
                        for sub in interior:
                            if isinstance(sub, list):
                                refs_unidades.extend(
                                    u for u in sub if isinstance(u, tuple))
                    else:
                        refs_unidades.extend(
                            u for u in interior if isinstance(u, tuple))
                else:
                    refs_unidades.append(cand)
            for uref in refs_unidades:
                uargs = spf.args(uref)
                if len(uargs) >= 4 and uargs[1] == ".LENGTHUNIT.":
                    prefijo = uargs[2] if isinstance(uargs[2], str) else "$"
                    nombre = uargs[3] if isinstance(uargs[3], str) else ""
                    factor = _ESCALA_UNIDADES.get(nombre.strip("."))
                    if factor is None:
                        continue
                    if prefijo == ".MILLI.":
                        factor *= 0.001
                    elif prefijo == ".CENTI.":
                        factor *= 0.01
                    return factor
        return 1.0

    # -- colocaciones -------------------------------------------------------
    def _matriz_de_placement(self, spf: _SPF, ref: Optional[Any],
                             vistos: Optional[set] = None) -> Mat4:
        """IfcLocalPlacement(PlacementRelTo, RelativePlacement) → Mat4.

        Compone la cadena de padres (con guarda contra ciclos), que es
        como anclan los visores: la geometría del producto es local a
        su nivel, el nivel a su edificio…
        """
        vistos = vistos if vistos is not None else set()
        if ref is None or not isinstance(ref, tuple) or ref[1] in vistos:
            return _identidad4()
        vistos.add(ref[1])
        args = spf.args(ref)
        if spf.nombre(ref) != "IFCLOCALPLACEMENT" or len(args) < 2:
            return _identidad4()
        matriz = self._matriz_de_placement(spf, args[0], vistos) \
            if args[0] is not None else _identidad4()
        rel = args[1]
        if rel is not None:
            rnombre = spf.nombre(rel)
            if rnombre == "IFCAXIS2PLACEMENT2D":
                matriz = _multiplica(matriz,
                                     _matriz_axis2pl2d(spf, rel))
            else:
                matriz = _multiplica(matriz,
                                     _matriz_axis2pl3d(spf, rel))
        return matriz

    def _cota_de_placement(self, spf: _SPF, args: List[Any]) -> float:
        """Z de la colocación de un storey (respaldo de Elevation)."""
        if len(args) > 5 and args[5] is not None:
            matriz = self._matriz_de_placement(spf, args[5])
            return matriz[2][3]
        return 0.0

    # -- geometría ------------------------------------------------------------
    def _solidos(self, spf: _SPF,
                 escala: float) -> Tuple[List[_Solido], List[str]]:
        """Resuelve todos los productos con cuerpo extruido útil."""
        avisos: List[str] = []
        # storey de cada producto: IfcRelContainedInSpatialStructure
        # (…, RelatedElements[4], RelatingStructure[5])
        storey_de: Dict[int, int] = {}
        for rid in spf.buscar_tipo(("IFCRELCONTAINEDINSPATIALSTRUCTURE",)):
            args = spf.args(rid)
            if len(args) < 6:
                continue
            estructura = args[5] if isinstance(args[5], tuple) else None
            storey_ref = estructura[1] if estructura else 0
            for producto in (args[4] if isinstance(args[4], list) else []):
                if isinstance(producto, tuple):
                    storey_de[producto[1]] = storey_ref
        # Cadena de vanos: relleno → apertura (IfcRelFillsElement) y
        # apertura → muro (IfcRelVoidsElement); sirve para heredar el
        # nivel del muro anfitrión cuando el archivo no contiene a la
        # puerta/ventana en ningún piso.
        apertura_de: Dict[int, int] = {}
        for rid in spf.buscar_tipo(("IFCRELFILLELEMENT",)):
            args = spf.args(rid)
            if len(args) >= 6 and isinstance(args[4], tuple):
                relleno = _ref_primera(args[5])
                if relleno is not None:
                    apertura_de[relleno] = args[4][1]
        muro_de: Dict[int, int] = {}
        for rid in spf.buscar_tipo(("IFCRELVOIDSELEMENT",)):
            args = spf.args(rid)
            if len(args) >= 6 and isinstance(args[4], tuple):
                apertura = _ref_primera(args[5])
                if apertura is not None:
                    muro_de[apertura] = args[4][1]

        def _storey_de_producto(eid: int, clase: str) -> int:
            ref = storey_de.get(eid, 0)
            if ref == 0 and clase in ("DOOR", "WINDOW"):
                apertura = apertura_de.get(eid)
                muro = muro_de.get(apertura) if apertura else None
                if muro is not None:
                    ref = storey_de.get(muro, 0)
            return ref
        solidos: List[_Solido] = []
        extrusiones_raras = 0
        for eid, (nombre, args) in spf.entidades.items():
            clase = self._clase_de(nombre)
            if clase is None:
                continue
            resuelto = None
            if len(args) > 6 and args[6] is not None:
                matriz = self._matriz_de_placement(spf, args[5])
                resuelto = self._geometria_de(spf, args, matriz, escala)
            if resuelto is None:
                if clase in ("WALL", "SLAB", "SPACE", "DOOR", "WINDOW"):
                    extrusiones_raras += 1
                continue
            contorno, z0, z1 = resuelto
            solidos.append(_Solido(
                eid=eid, clase=clase,
                nombre=str(args[2]) if len(args) > 2 and isinstance(
                    args[2], str) else "",
                etiqueta=str(args[7]) if len(args) > 7 and isinstance(
                    args[7], str) else "",
                contorno=contorno, z0=z0,
                altura=max(0.0, z1 - z0),
                storey_ref=_storey_de_producto(eid, clase)))
        if extrusiones_raras:
            avisos.append(
                "%d producto(s) con geometría no extruida sobre Z se "
                "omitieron (solo perfiles rectangulares o poligonales)."
                % extrusiones_raras)
        return solidos, avisos

    @staticmethod
    def _clase_de(nombre_ifc: str) -> Optional[str]:
        if nombre_ifc in _CLASE_MURO:
            return "WALL"
        if nombre_ifc in _CLASE_LOSA:
            return "SLAB"
        if nombre_ifc in _CLASE_LOCAL:
            return "SPACE"
        if nombre_ifc in _CLASE_PUERTA:
            return "DOOR"
        if nombre_ifc in _CLASE_VENTANA:
            return "WINDOW"
        if nombre_ifc in ("IFCPROJECT", "IFCSITE", "IFCBUILDING",
                          "IFCBUILDINGSTOREY", "IFCOPENINGELEMENT",
                          "IFCGRID", "IFCANNOTATION"):
            return None
        if nombre_ifc.startswith("IFC") and len(nombre_ifc) > 3 \
                and nombre_ifc[3].isupper():
            return "OTRO"
        return None

    def _geometria_de(self, spf: _SPF, args: List[Any], matriz: Mat4,
                      escala: float) -> Optional[Tuple[
                          List[Tuple[float, float]], float, float]]:
        """Contorno (XY mundo, metros) + [z0, z1] del cuerpo del producto.

        IfcProduct.Representation[6] → IfcProductDefinitionShape(…,
        Representations[2]) → IfcShapeRepresentation(…, Items[3]) →
        IfcExtrudedAreaSolid(SweptArea[0], Position[1],
        ExtrudedDirection[2], Depth[3]).
        """
        shape = spf.args(args[6])
        reps = shape[2] if len(shape) > 2 else None
        # Representaciones: lista (#a,#b) o ref simple #a (nuestro
        # escritor usa ref simple; el esquema pide lista: se aceptan
        # ambas y también listas anidadas un nivel).
        if isinstance(reps, tuple):
            reps = [reps]
        if isinstance(reps, list) and reps and isinstance(
                reps[0], list):
            reps = [r for sub in reps for r in
                    (sub if isinstance(sub, list) else [sub])]
        items: List[Any] = []
        for rep in (reps if isinstance(reps, list) else []):
            rargs = spf.args(rep if isinstance(rep, tuple) else None)
            if len(rargs) > 3 and isinstance(rargs[3], list):
                items.extend([i for i in rargs[3] if isinstance(i, tuple)])
        mejor: Optional[Tuple[List[Tuple[float, float]], float, float]] = None
        for item in items:
            if spf.nombre(item) != "IFCEXTRUDEDAREASOLID":
                continue
            iargs = spf.args(item)
            if len(iargs) < 4 or not isinstance(iargs[3], (int, float)) \
                    or iargs[3] <= 0:
                continue
            perfil_ref, posicion_ref = iargs[0], iargs[1]
            direccion = _componentes(spf, iargs[2]) if iargs[2] is not None \
                else [0.0, 0.0, 1.0]
            if len(direccion) >= 2 and (abs(direccion[0]) > 1e-6
                                        or abs(direccion[1]) > 1e-6):
                continue  # extrusión no vertical: fuera de alcance
            puntos_perfil = self._perfil(spf, perfil_ref)
            if not puntos_perfil or len(puntos_perfil) < 3:
                continue
            m_solido = matriz
            if posicion_ref is not None:
                pnombre = spf.nombre(posicion_ref)
                if pnombre == "IFCAXIS2PLACEMENT2D":
                    m_solido = _multiplica(
                        matriz, _matriz_axis2pl2d(spf, posicion_ref))
                else:
                    m_solido = _multiplica(
                        matriz, _matriz_axis2pl3d(spf, posicion_ref))
            profundidad = float(iargs[3])
            mundo_bajo = [_aplica(m_solido, x, y, 0.0)
                          for (x, y) in puntos_perfil]
            mundo_alto = [_aplica(m_solido, x, y, profundidad)
                          for (x, y) in puntos_perfil]
            zs = [p[2] for p in mundo_bajo] + [p[2] for p in mundo_alto]
            contorno = [(x * escala, y * escala)
                        for (x, y, _z) in mundo_bajo]
            z0, z1 = min(zs) * escala, max(zs) * escala
            if mejor is None or (z1 - z0) > (mejor[2] - mejor[1]):
                mejor = (contorno, z0, z1)
        return mejor

    def _perfil(self, spf: _SPF, ref: Optional[Any]
                ) -> Optional[List[Tuple[float, float]]]:
        """Puntos del perfil en el plano del sólido (sin escala)."""
        if ref is None:
            return None
        pnombre = spf.nombre(ref)
        pargs = spf.args(ref)
        if pnombre == "IFCRECTANGLEPROFILEDEF" and len(pargs) >= 5:
            xdim = pargs[3] if isinstance(pargs[3], (int, float)) else 0.0
            ydim = pargs[4] if isinstance(pargs[4], (int, float)) else 0.0
            if xdim <= 0 or ydim <= 0:
                return None
            m = _matriz_axis2pl2d(spf, pargs[2]) if len(pargs) > 2 \
                and pargs[2] is not None else _identidad4()
            medio_x, medio_y = xdim / 2.0, ydim / 2.0
            locales = [(-medio_x, -medio_y), (medio_x, -medio_y),
                       (medio_x, medio_y), (-medio_x, medio_y)]
            return [(_aplica(m, x, y, 0.0)[0],
                     _aplica(m, x, y, 0.0)[1]) for (x, y) in locales]
        if pnombre in ("IFCARBITRARYCLOSEDPROFILEDEF",
                       "IFCARBITRARYPROFILEDEFWITHVOIDS"):
            curva = pargs[2] if len(pargs) > 2 else None
            cargs = spf.args(curva if isinstance(curva, tuple) else None)
            if spf.nombre(curva) != "IFCPOLYLINE" or not cargs:
                return None
            puntos: List[Tuple[float, float]] = []
            for pref in (cargs[0] if isinstance(cargs[0], list) else []):
                p = spf.args(pref if isinstance(pref, tuple) else None)
                if p and isinstance(p[0], list) and len(p[0]) >= 2:
                    puntos.append((float(p[0][0]), float(p[0][1])))
            if len(puntos) >= 2 and puntos[0] == puntos[-1]:
                puntos.pop()
            return puntos or None
        return None

    # -- reconstrucción -----------------------------------------------------
    @staticmethod
    def _muro_de_solido(solido: _Solido) -> Optional[Tuple[
            Tuple[Tuple[float, float], Tuple[float, float]], float, float]]:
        """Eje, espesor y altura del muro desde su huella rectangular.

        Los dos lados largos de la huella dan el eje (unión de sus
        puntos medios) y el espesor sale de los cortos; si la huella
        no es rectangular se cae a la caja envolvente alineada.
        """
        puntos = solido.contorno
        if len(puntos) < 3 or solido.altura <= 0.0:
            return None
        aristas = []
        for i in range(len(puntos)):
            (x1, y1), (x2, y2) = puntos[i], puntos[(i + 1) % len(puntos)]
            aristas.append(((x1, y1), (x2, y2), math.hypot(x2 - x1, y2 - y1)))
        aristas.sort(key=lambda a: a[2], reverse=True)
        (a1, a2, la), (b1, b2, lb) = aristas[0], aristas[1]
        if la <= 1e-9 or lb <= 1e-9:
            return None
        u1 = ((a2[0] - a1[0]) / la, (a2[1] - a1[1]) / la)
        u2 = ((b2[0] - b1[0]) / lb, (b2[1] - b1[1]) / lb)
        paralelo = abs(u1[0] * u2[0] + u1[1] * u2[1])
        if paralelo > 0.98:
            # RECTÁNGULO: los dos lados largos van en direcciones
            # OPUESTAS al recorrer el contorno, así que el eje sale de
            # la dirección del lado largo y el centro es el punto medio
            # entre ambos lados; el espesor es la distancia PERPENDICULAR
            # entre las rectas de ambos lados (NO la distancia entre sus
            # puntos medios, que sería el espesor solo por casualidad).
            u = u1
            m1 = ((a1[0] + a2[0]) / 2.0, (a1[1] + a2[1]) / 2.0)
            m2 = ((b1[0] + b2[0]) / 2.0, (b1[1] + b2[1]) / 2.0)
            centro = ((m1[0] + m2[0]) / 2.0, (m1[1] + m2[1]) / 2.0)
            largo = (la + lb) / 2.0
            seg = (m2[0] - m1[0], m2[1] - m1[1])
            a_lo = seg[0] * u[0] + seg[1] * u[1]
            espesor = math.hypot(seg[0] - a_lo * u[0],
                                 seg[1] - a_lo * u[1])
            if espesor <= 1e-6:
                espesor = (min(aristas[2][2], aristas[3][2])
                           if len(aristas) >= 4 else 0.2)
        else:
            # no rectangular: caja envolvente alineada a los ejes
            xs = [p[0] for p in puntos]
            ys = [p[1] for p in puntos]
            if max(xs) - min(xs) >= max(ys) - min(ys):
                largo = max(xs) - min(xs)
                espesor = max(ys) - min(ys)
                centro = ((min(xs) + max(xs)) / 2.0,
                          (min(ys) + max(ys)) / 2.0)
                u = (1.0, 0.0)
            else:
                largo = max(ys) - min(ys)
                espesor = max(xs) - min(xs)
                centro = ((min(xs) + max(xs)) / 2.0,
                          (min(ys) + max(ys)) / 2.0)
                u = (0.0, 1.0)
        if largo <= 1e-6 or espesor <= 1e-6:
            return None
        p1 = (centro[0] - u[0] * largo / 2.0,
              centro[1] - u[1] * largo / 2.0)
        p2 = (centro[0] + u[0] * largo / 2.0,
              centro[1] + u[1] * largo / 2.0)
        return ((p1, p2), espesor, solido.altura)

    # -- vanos --------------------------------------------------------------
    def _vanos(self, spf: _SPF, solidos: List[_Solido],
               muros_creados: Dict[int, Any], architecture: Any,
               niveles: Dict[int, str], cotas: Dict[str, float],
               avisos: List[str]) -> Tuple[int, int]:
        """Crea puertas/ventanas anclando cada vano a su muro anfitrión.

        Preferimos la relación OFICIAL del archivo
        (IfcRelFillsElement → IfcRelVoidsElement → muro anfitrión); si
        el archivo no la trae, caemos a la cercanía perpendicular (el
        muro cuyo eje pasa más cerca del vano). Devuelve (puertas,
        ventanas).
        """
        # puerta/ventana eid → apertura eid (IfcRelFillsElement:
        # RelatingOpeningElement[4], RelatedBuildingElement[5])
        apertura_de: Dict[int, int] = {}
        for rid in spf.buscar_tipo(("IFCRELFILLELEMENT",)):
            args = spf.args(rid)
            if len(args) >= 6 and isinstance(args[4], tuple):
                relleno = _ref_primera(args[5])
                if relleno is not None:
                    apertura_de[relleno] = args[4][1]
        muro_de: Dict[int, int] = {}
        for rid in spf.buscar_tipo(("IFCRELVOIDSELEMENT",)):
            args = spf.args(rid)
            if len(args) >= 6 and isinstance(args[4], tuple):
                apertura = _ref_primera(args[5])
                if apertura is not None:
                    muro_de[apertura] = args[4][1]
        solido_por_eid = {s.eid: i for i, s in enumerate(solidos)}
        puertas = ventanas = 0
        for indice, solido in enumerate(solidos):
            if solido.clase not in ("DOOR", "WINDOW"):
                continue
            if not muros_creados or not niveles.get(solido.storey_ref):
                avisos.append("Vano «%s» sin nivel o sin muros: omitido."
                              % (solido.nombre or solido.etiqueta))
                continue
            # -- anfitrión oficial, si el archivo lo declara -------------
            anfitrion: Optional[Tuple[int, Tuple]] = None
            apertura_eid = apertura_de.get(solido.eid)
            muro_eid = muro_de.get(apertura_eid) if apertura_eid else None
            if muro_eid is not None:
                m_indice = solido_por_eid.get(muro_eid)
                muro = muros_creados.get(m_indice) if m_indice is not None \
                    else None
                if muro is not None:
                    rec = self._vano_en_muro(solido, muro)
                    if rec is not None:
                        anfitrion = (m_indice, rec)
            # -- respaldo: el muro cuyo eje pasa más cerca ---------------
            if anfitrion is None:
                mejor = None
                for m_indice, muro in muros_creados.items():
                    if muro.level_id and \
                            niveles.get(solido.storey_ref) != muro.level_id:
                        continue
                    rec = self._vano_en_muro(solido, muro)
                    if rec is None:
                        continue
                    offset, ancho, altura, d_perp = rec
                    if d_perp > float(muro.thickness_m) / 2.0 + 0.25:
                        continue  # este muro no pasa por el vano
                    if mejor is None or d_perp < mejor[0]:
                        mejor = (d_perp, (m_indice, rec))
                if mejor is not None:
                    anfitrion = mejor[1]
            if anfitrion is None:
                avisos.append("Vano «%s» sin muro anfitrión: omitido."
                              % (solido.nombre or solido.etiqueta))
                continue
            m_indice, (offset, ancho, altura, _d_perp) = anfitrion
            muro = muros_creados[m_indice]
            cota_nivel = cotas.get(niveles.get(solido.storey_ref, ""), 0.0)
            sill = max(0.0, solido.z0 - cota_nivel
                       - (getattr(muro, "base_offset_m", 0.0) or 0.0))
            try:
                architecture.create_opening(
                    "DOOR" if solido.clase == "DOOR" else "WINDOW",
                    muro.code, width_m=round(ancho, 4),
                    height_m=round(altura, 3),
                    offset_m=round(offset, 4),
                    sill_height_m=round(sill, 4))
            except DomainError as exc:
                avisos.append("Vano «%s» omitido: %s"
                              % (solido.nombre or solido.etiqueta,
                                 exc.message))
                continue
            if solido.clase == "DOOR":
                puertas += 1
            else:
                ventanas += 1
        return puertas, ventanas

    @staticmethod
    def _vano_en_muro(solido: _Solido,
                      muro: Any) -> Optional[Tuple[float, float, float,
                                                   float]]:
        """(offset, ancho, altura, distancia_perpendicular) del vano.

        Proyecta el centro del vano sobre el eje del muro: el ancho es
        su extensión sobre el eje y ``distancia_perpendicular`` cuánto
        se separa del plano del muro (0 = encaja de verdad).
        """
        x1, y1 = float(muro.start[0]), float(muro.start[1])
        x2, y2 = float(muro.end[0]), float(muro.end[1])
        dx, dy = x2 - x1, y2 - y1
        largo = math.hypot(dx, dy)
        if largo <= 1e-6 or not solido.contorno:
            return None
        u = (dx / largo, dy / largo)
        xs = [p[0] for p in solido.contorno]
        ys = [p[1] for p in solido.contorno]
        centro = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
        rel = (centro[0] - x1, centro[1] - y1)
        s = rel[0] * u[0] + rel[1] * u[1]
        d_perp = abs(rel[0] * -u[1] + rel[1] * u[0])
        ext_eje = max(abs((px - x1) * u[0] + (py - y1) * u[1] - s)
                      for px, py in zip(xs, ys))
        ancho = min(2.0 * ext_eje, largo)
        altura = min(solido.altura, max(0.1, float(muro.height_m)))
        if altura <= 0.0 or ancho <= 1e-6:
            return None
        offset = max(0.0, min(s - ancho / 2.0, max(0.0, largo - ancho)))
        return (offset, ancho, altura, d_perp)


def _nombre_unidad(escala: float) -> str:
    inverso = {v: k for k, v in _ESCALA_UNIDADES.items()}
    return inverso.get(escala, "escala x%g" % escala)


__all__ = ["IfcImporter"]

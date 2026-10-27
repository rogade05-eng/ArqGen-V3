"""PARASOLES Y PIELES EXTERIORES DE FACHADA (v3.18.0).

La fachada moderna se diseña en DOS capas: la piel que envuelve
(doble piel de vidrio, celosías, malla metálica, baguettes de
terracota, panel perforado, jardín vertical, GRC o policarbonato) y
los parasoles que la rematan (brise-soleil horizontal al SUR, aletas
verticales a ESTE y OESTE; al NORTE no hacen falta: la luz es difusa,
y el libro lo confirma). Este módulo genera AMBAS sobre el recinto
real del nivel:

* ``TIPOS_PARASOL`` / ``MATERIALES``: horizontal, vertical, mixto
  (celosía en cruz) y lamas orientables, en aluminio, madera, acero
  corten, GRC, cerámica o textil.
* ``TIPOS_PIEL``: ocho pieles contemporáneas con su cámara ventilada
  y su porcentaje de perforación (QTO); el ESTILO arquitectónico del
  asistente sugiere la piel («Racionalista» -> doble piel de vidrio,
  «Sostenible» -> celosía de madera, «High-tech» -> malla...).
* ``generar_parasoles`` / ``generar_piel``: una entidad por LADO de
  la fachada (N/S/E/O), con la línea de fachada medida del recinto;
  idempotentes (quitan los suyos antes) y separables (los parasoles
  no tocan a la piel y viceversa).

Cero Tk y cero dependencias. Mensajes 100 % codificables en cp1252.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.errors import DomainError
from domain.diseno_base import (
    alta_entidad, baja_entidad, bbox_de, cerrar_qto, lista_tipos,
    metadata_origen,
)
from domain.model import FacadeSkin, Parasol

PT = Tuple[float, float]

# errores propios: ARQ-FAC-001 sin edificación, ARQ-FAC-002 lados/tipo
# desconocido, ARQ-FAC-003 parámetros fuera de rango

LADOS: Tuple[str, ...] = ("N", "S", "E", "O")
ETIQUETA_LADO: Dict[str, str] = {"N": "norte", "S": "sur", "E": "este",
                                 "O": "oeste"}

TIPOS_PARASOL: Tuple[str, ...] = ("auto", "horizontal", "vertical",
                                  "mixto", "lamas_moviles", "ninguno")
MATERIALES_PARASOL: Tuple[str, ...] = ("auto", "aluminio", "madera",
                                       "acero_corten", "hormigon_grc",
                                       "ceramica", "textil")
ETIQUETA_PARASOL: Dict[str, str] = {
    "horizontal": "lamas horizontales (brise-soleil)",
    "vertical": "aletas verticales",
    "mixto": "celosía en cruz (huevo)",
    "lamas_moviles": "lamas orientables",
}
ETIQUETA_MATERIAL: Dict[str, str] = {
    "aluminio": "aluminio anodizado",
    "madera": "madera tratada",
    "acero_corten": "acero corten",
    "hormigon_grc": "hormigón GRC",
    "ceramica": "cerámica esmaltada",
    "textil": "textil tensado",
}

TIPOS_PIEL: Tuple[str, ...] = ("auto", "doble_piel_vidrio",
                               "celosia_madera", "malla_metalica",
                               "baguette_terracota", "panel_perforado",
                               "jardin_vertical", "grc",
                               "policarbonato", "ninguno")
ETIQUETA_PIEL: Dict[str, str] = {
    "doble_piel_vidrio": "doble piel de vidrio",
    "celosia_madera": "celosía de madera",
    "malla_metalica": "malla metálica tejida",
    "baguette_terracota": "baguettes de terracota",
    "panel_perforado": "panel metálico perforado",
    "jardin_vertical": "jardín vertical",
    "grc": "paneles de GRC",
    "policarbonato": "policarbonato celular",
}
MATERIAL_POR_PIEL: Dict[str, str] = {
    "doble_piel_vidrio": "vidrio",
    "celosia_madera": "madera",
    "malla_metalica": "acero",
    "baguette_terracota": "ceramica",
    "panel_perforado": "aluminio",
    "jardin_vertical": "vegetal",
    "grc": "hormigon_grc",
    "policarbonato": "policarbonato",
}
# Perforación / aire libre de cada piel (%): la ventilación de la
# cámara y el QTO la usan (superficie ciega vs abierta).
APERTURA_POR_PIEL: Dict[str, float] = {
    "doble_piel_vidrio": 15.0,
    "celosia_madera": 60.0,
    "malla_metalica": 70.0,
    "baguette_terracota": 50.0,
    "panel_perforado": 35.0,
    "jardin_vertical": 100.0,
    "grc": 0.0,
    "policarbonato": 0.0,
}

# Estilos modernos actuales -> piel sugerida (el asistente la propone
# con «auto»; el usuario siempre puede fijarla a mano).
ESTILO_PIEL: Dict[str, str] = {
    "Racionalista": "doble_piel_vidrio",
    "Minimalista": "doble_piel_vidrio",
    "High-tech": "malla_metalica",
    "Posmoderno": "panel_perforado",
    "Brutalista": "grc",
    "Sostenible (bioclimático)": "celosia_madera",
    "Contemporáneo": "baguette_terracota",
    "Art déco": "baguette_terracota",
    "Modernista": "celosia_madera",
    "Orgánico": "jardin_vertical",
    "Colonial cubano": "celosia_madera",
    "Vernáculo tropical": "celosia_madera",
    "Neoclásico": "grc",
    "Ecléctico": "baguette_terracota",
}

SEPARACION_DEFECTO_M = 0.60   # cámara ventilada de la piel
PROFUNDIDAD_DEFECTO_M = 0.50  # vuelo de la lama del parasol
SEPARACION_LAMA_DEFECTO_M = 0.60
ANCHO_LAMA_M = 0.18           # ancho visible de cada lama/aleta
ESPESOR_LAMA_M = 0.04

# Parasol por orientación (regla solar clásica): el sol cae ALTO por
# el sur -> lamas horizontales; barre BAJO por este y oeste -> aletas
# verticales; por el norte la luz es difusa y no se necesita.
PARASOL_POR_LADO: Dict[str, str] = {
    "S": "horizontal", "E": "vertical", "O": "vertical", "N": ""}


def lados_pedidos(lados: str) -> List[str]:
    """Convierte «auto»/«S»/«S,E»/«todas» en la lista de lados."""
    texto = str(lados or "auto").strip().lower()
    if texto in ("", "auto", "todas", "todos"):
        return list(LADOS)
    pedidos: List[str] = []
    for trozo in texto.replace(";", ",").split(","):
        lado = trozo.strip().upper()
        if not lado:
            continue
        if lado not in LADOS:
            raise DomainError(
                message=f"Lado de fachada desconocido: {trozo.strip()}",
                code="ARQ-FAC-002",
                context={"lado": lado, "permitidos": list(LADOS)},
                suggested_action="Usa N, S, E u O (o «auto»).")
        if lado not in pedidos:
            pedidos.append(lado)
    return pedidos


def _recinto_del_nivel(ctx: Any, nivel_id: str) -> Optional[
        Tuple[float, float, float, float]]:
    """AABB del nivel a partir de sus locales (None si no hay)."""
    puntos = [tuple(p) for e in lista_tipos(ctx, "SPACE")
              if e.level_id == nivel_id
              for p in (getattr(e, "boundary", []) or [])]
    if len(puntos) < 3:
        return None
    return bbox_de(puntos)


def linea_fachada(recinto: Tuple[float, float, float, float],
                  lado: str) -> Tuple[float, float, float, float]:
    """Línea de fachada (centro_x, centro_y, rotación_deg, largo).

    S es el lado de y MÍNIMA (sur del plano), N el de máxima; E el de
    x máxima y O la de mínima. La rotación: 0° = la pieza corre a lo
    largo de X (fachadas S/N), 90° = a lo largo de Y (E/O).
    """
    minx, miny, maxx, maxy = recinto
    lado = (lado or "S").upper()
    if lado == "S":
        return ((minx + maxx) / 2.0, miny, 0.0, maxx - minx)
    if lado == "N":
        return ((minx + maxx) / 2.0, maxy, 0.0, maxx - minx)
    if lado == "E":
        return (maxx, (miny + maxy) / 2.0, 90.0, maxy - miny)
    if lado == "O":
        return (minx, (miny + maxy) / 2.0, 90.0, maxy - miny)
    raise DomainError(
        message=f"Lado de fachada desconocido: {lado}",
        code="ARQ-FAC-002",
        context={"lado": lado, "permitidos": list(LADOS)},
        suggested_action="Usa N, S, E u O.")


def _normal_saliente(lado: str) -> Tuple[float, float]:
    """Vector unitario que sale del edificio por ese lado."""
    return {"S": (0.0, -1.0), "N": (0.0, 1.0),
            "E": (1.0, 0.0), "O": (-1.0, 0.0)}.get(lado, (0.0, -1.0))


def _desplaza(x: float, y: float, lado: str, distancia: float
              ) -> Tuple[float, float]:
    nx, ny = _normal_saliente(lado)
    return (x + nx * distancia, y + ny * distancia)


def _n_niveles_hasta_arriba(ctx: Any, nivel_id: str) -> Tuple[int, float]:
    """(niveles desde ``nivel_id`` hasta el más alto, altura total)."""
    niveles = [lv for lv in lista_tipos(ctx, "LEVEL")]
    if not niveles:
        return (1, 3.0)
    niveles.sort(key=lambda lv: (float(getattr(lv, "elevation_m", 0.0)
                                       or 0.0), str(getattr(lv, "name", ""))))
    indice = next((i for i, lv in enumerate(niveles) if lv.id == nivel_id),
                  0)
    cola = niveles[indice:]
    altura = sum(float(getattr(lv, "height_m", 3.0) or 3.0)
                 for lv in cola)
    return (len(cola), altura)


# ---------------------------------------------------------------------------
# parasoles
# ---------------------------------------------------------------------------

def resolver_parasol(lados: str = "auto", tipo: str = "auto",
                     material: str = "auto",
                     profundidad_m: float = 0.0,
                     separacion_m: float = 0.0
                     ) -> Dict[str, Any]:
    """Resuelve el parasol por lado (la orientación manda en «auto»).

    Con ``tipo=auto`` cada lado recibe el suyo (S horizontal, E/O
    verticales, N ninguno); un tipo explícito se aplica a TODOS los
    lados pedidos. Devuelve las reglas y los valores normalizados.
    """
    if tipo not in TIPOS_PARASOL:
        raise DomainError(
            message=f"Tipo de parasol desconocido: {tipo}",
            code="ARQ-FAC-002",
            context={"tipo": tipo, "permitidos": list(TIPOS_PARASOL)},
            suggested_action="Usa uno de: " + ", ".join(TIPOS_PARASOL))
    if material not in MATERIALES_PARASOL:
        raise DomainError(
            message=f"Material de parasol desconocido: {material}",
            code="ARQ-FAC-002",
            context={"material": material,
                     "permitidos": list(MATERIALES_PARASOL)},
            suggested_action="Usa uno de: " + ", ".join(MATERIALES_PARASOL))
    if profundidad_m > 0 and not 0.15 <= profundidad_m <= 2.0:
        raise DomainError(
            message="El vuelo de la lama debe quedar entre 0.15 y 2.0 m",
            code="ARQ-FAC-003",
            context={"profundidad_m": profundidad_m})
    if separacion_m > 0 and not 0.15 <= separacion_m <= 2.0:
        raise DomainError(
            message="La separación entre lamas debe quedar entre 0.15 "
                    "y 2.0 m",
            code="ARQ-FAC-003",
            context={"separacion_m": separacion_m})
    return {
        "lados": lados_pedidos(lados),
        "tipo": tipo,
        "material": "aluminio" if material == "auto" else material,
        "profundidad_m": round(float(profundidad_m or 0.0)
                               or PROFUNDIDAD_DEFECTO_M, 3),
        "separacion_m": round(float(separacion_m or 0.0)
                              or SEPARACION_LAMA_DEFECTO_M, 3),
    }


def _tipo_para_lado(tipo: str, lado: str) -> str:
    """El tipo resuelto para un lado (auto usa la regla solar)."""
    if tipo != "auto":
        return tipo
    return PARASOL_POR_LADO.get(lado, "horizontal")


def quitar_parasoles(ctx: Any) -> List[str]:
    """Da de baja SOLO los parasoles generados."""
    bajas: List[str] = []
    for parasol in lista_tipos(ctx, "PARASOL"):
        codigo = parasol.code
        baja_entidad(ctx, "PARASOL", parasol.id)
        bajas.append(codigo)
    return bajas


def generar_parasoles(ctx: Any, data: Any = None,
                      lados: str = "auto", tipo: str = "auto",
                      material: str = "auto",
                      profundidad_m: float = 0.0,
                      separacion_m: float = 0.0,
                      nivel_id: str = "",
                      altura_inicio_m: float = -1.0,
                      altura_fin_m: float = -1.0,
                      con_qto: bool = True) -> Dict[str, Any]:
    """Viste de parasoles las fachadas del nivel (v3.18.0).

    Un PARASOL por LADO: la línea de fachada sale del recinto del
    nivel y las lamas salen hacia fuera (vuelo de ``profundidad_m``).
    En «auto» la orientación decide: SUR horizontal, ESTE y OESTE
    verticales y NORTE sin parasol (aviso amable). ``altura_inicio``/
    ``altura_fin`` cortan la banda vertical dentro del piso del nivel
    (-1 = todo el piso). Idempotente y separable de la piel.
    """
    resumen: Dict[str, Any] = {"operacion": "parasoles", "creados": [],
                               "eliminados": [], "avisos": [],
                               "qto": None}
    reglas = resolver_parasol(lados=lados, tipo=tipo, material=material,
                              profundidad_m=profundidad_m,
                              separacion_m=separacion_m)
    # nivel objetivo: el pedido o el más alto con espacios (la fachada
    # viva); sin locales no hay fachada que vestir
    nivel: Optional[Any] = None
    if nivel_id:
        nivel = next((lv for lv in lista_tipos(ctx, "LEVEL")
                      if lv.id == nivel_id), None)
    if nivel is None:
        espacios = lista_tipos(ctx, "SPACE")
        niveles = {e.level_id for e in espacios}
        candidatas = [lv for lv in lista_tipos(ctx, "LEVEL")
                      if lv.id in niveles]
        if not candidatas:
            candidatas = lista_tipos(ctx, "LEVEL")
        if candidatas:
            candidatas.sort(key=lambda lv: (
                float(getattr(lv, "elevation_m", 0.0) or 0.0),
                str(getattr(lv, "name", ""))))
            nivel = candidatas[-1]
    recinto = _recinto_del_nivel(ctx, nivel.id) if nivel else None
    if recinto is None:
        resumen["avisos"].append(
            "No hay locales para medir la fachada: genera antes la "
            "edificación.")
        return resumen
    resumen["eliminados"] = quitar_parasoles(ctx)
    _niveles, altura_total = _n_niveles_hasta_arriba(ctx, nivel.id)
    altura_piso = float(getattr(nivel, "height_m", 3.0) or 3.0)
    inicio = 0.0 if altura_inicio_m < 0 else max(0.0, float(altura_inicio_m))
    fin = altura_piso if altura_fin_m < 0 else min(
        float(altura_fin_m), altura_total)
    if fin - inicio < 0.20:
        resumen["avisos"].append(
            "la banda vertical del parasol es muy baja: se cubre todo "
            "el piso")
        inicio, fin = 0.0, altura_piso
    lados_resueltos: List[Dict[str, Any]] = []
    for lado in reglas["lados"]:
        tipo_lado = _tipo_para_lado(reglas["tipo"], lado)
        if tipo_lado in ("", "ninguno"):
            if reglas["tipo"] == "auto":
                resumen["avisos"].append(
                    f"fachada {ETIQUETA_LADO[lado]}: sin parasol (luz "
                    "difusa, no carga sol directo)")
            continue
        cx, cy, rot, largo = linea_fachada(recinto, lado)
        vuelo = reglas["profundidad_m"]
        # el eje del parasol corre a media vuelta POR FUERA de la
        # fachada: la lama nace pegada al muro y sale hacia fuera
        ex, ey = _desplaza(cx, cy, lado, vuelo / 2.0 + 0.05)
        # lamas: horizontales se APILAN en alto; verticales se reparten
        # a lo largo de la fachada; mixto hace las dos cuentas
        n_h = n_v = 0
        if tipo_lado in ("horizontal", "lamas_moviles", "mixto"):
            banda = max(fin - inicio, 0.2)
            n_h = max(1, int(math.ceil(
                (banda - 0.05) / reglas["separacion_m"])))
        if tipo_lado in ("vertical", "mixto"):
            n_v = max(1, int(largo / reglas["separacion_m"]))
        n_lamas = n_h + n_v
        if n_lamas <= 0:
            continue
        entidad = Parasol(
            project_id=ctx.project.id,
            code=ctx.next_code("ARCHITECTURE", "PARASOL"),
            level_id=nivel.id, side=lado, tipo=tipo_lado,
            material=reglas["material"],
            x=round(ex, 4), y=round(ey, 4), rotation_deg=rot,
            length_m=round(largo, 4), profundidad_m=vuelo,
            separacion_m=reglas["separacion_m"], n_lamas=n_lamas,
            altura_inicio_m=round(inicio, 3),
            altura_fin_m=round(min(fin, altura_piso), 3),
            metadata=metadata_origen(
                f"parasol {ETIQUETA_PARASOL.get(tipo_lado, tipo_lado)} "
                f"en la fachada {ETIQUETA_LADO[lado]}",
                {"material_etiqueta": ETIQUETA_MATERIAL.get(
                    reglas["material"], reglas["material"]),
                 "n_lamas_horizontales": n_h,
                 "n_lamas_verticales": n_v,
                 "angulo_deg": 45.0 if tipo_lado == "lamas_moviles"
                 else 0.0,
                 "ancho_lama_m": ANCHO_LAMA_M,
                 "espesor_lama_m": ESPESOR_LAMA_M}))
        alta_entidad(ctx, entidad)
        resumen["creados"].append(entidad.code)
        lados_resueltos.append({
            "lado": lado, "tipo": tipo_lado, "n_lamas": n_lamas,
            "length_m": round(largo, 2),
            "altura": (round(inicio, 2), round(min(fin, altura_piso), 2))})
    resumen["parametros"] = {**reglas, "nivel": getattr(nivel, "name", ""),
                             "lados_resueltos": lados_resueltos}
    if not resumen["creados"] and not resumen["avisos"]:
        resumen["avisos"].append("ningún lado pidió parasol")
    if con_qto:
        cerrar_qto(ctx, resumen)
    return resumen


# ---------------------------------------------------------------------------
# pieles exteriores
# ---------------------------------------------------------------------------

def resolver_piel(data: Any = None, lados: str = "auto",
                  tipo: str = "auto",
                  separacion_m: float = 0.0) -> Dict[str, Any]:
    """Resuelve la piel exterior (el ESTILO sugiere en «auto»).

    La cámara ventilada queda entre 0.30 y 2.00 m (0.60 m por
    defecto); el estilo arquitectónico del programa elige la piel
    contemporánea si el usuario no fija una.
    """
    if tipo not in TIPOS_PIEL:
        raise DomainError(
            message=f"Tipo de piel exterior desconocido: {tipo}",
            code="ARQ-FAC-002",
            context={"tipo": tipo, "permitidos": list(TIPOS_PIEL)},
            suggested_action="Usa uno de: " + ", ".join(TIPOS_PIEL))
    if separacion_m and not 0.30 <= separacion_m <= 2.0:
        raise DomainError(
            message="La cámara ventilada debe quedar entre 0.30 y 2.0 m",
            code="ARQ-FAC-003",
            context={"separacion_m": separacion_m})
    estilo = str(getattr(data, "architectural_style", "") or "")
    tipo_resuelto = tipo if tipo != "auto" \
        else ESTILO_PIEL.get(estilo, "doble_piel_vidrio")
    return {"lados": lados_pedidos(lados), "tipo": tipo_resuelto,
            "estilo": estilo,
            "material": MATERIAL_POR_PIEL.get(tipo_resuelto, "vidrio"),
            "separacion_m": round(
                float(separacion_m or 0.0) or SEPARACION_DEFECTO_M, 3),
            "apertura_pct": APERTURA_POR_PIEL.get(tipo_resuelto, 0.0)}


def quitar_pieles(ctx: Any) -> List[str]:
    """Da de baja SOLO las pieles generadas."""
    bajas: List[str] = []
    for piel in lista_tipos(ctx, "SKIN"):
        codigo = piel.code
        baja_entidad(ctx, "SKIN", piel.id)
        bajas.append(codigo)
    return bajas


def generar_piel(ctx: Any, data: Any = None, lados: str = "auto",
                 tipo: str = "auto", separacion_m: float = 0.0,
                 nivel_id: str = "", con_qto: bool = True
                 ) -> Dict[str, Any]:
    """Envuelve la edificación con su piel exterior (v3.18.0).

    Un SKIN por LADO: el plano de la piel corre PARALELO a la fachada
    separado la cámara ventilada (``separacion_m``) y sube desde el
    nivel base hasta el top de la edificación (doble piel completa).
    En «auto» el estilo arquitectónico elige la piel contemporánea.
    Idempotente y separable de los parasoles.
    """
    resumen: Dict[str, Any] = {"operacion": "piel", "creados": [],
                               "eliminados": [], "avisos": [],
                               "qto": None}
    reglas = resolver_piel(data, lados=lados, tipo=tipo,
                           separacion_m=separacion_m)
    if reglas["tipo"] == "ninguno":
        resumen["eliminados"] = quitar_pieles(ctx)
        resumen["avisos"].append(
            "piel sin tipo («ninguno»): solo se retiró la anterior.")
        if con_qto:
            cerrar_qto(ctx, resumen)
        return resumen
    # la piel nace en el nivel MÁS BAJO con espacios y sube hasta arriba
    espacios = lista_tipos(ctx, "SPACE")
    niveles_con = {e.level_id for e in espacios}
    candidatas = [lv for lv in lista_tipos(ctx, "LEVEL")
                  if lv.id in niveles_con] or lista_tipos(ctx, "LEVEL")
    if not candidatas:
        resumen["avisos"].append(
            "No hay edificación que vestir: genera antes los niveles.")
        return resumen
    candidatas.sort(key=lambda lv: (
        float(getattr(lv, "elevation_m", 0.0) or 0.0),
        str(getattr(lv, "name", ""))))
    nivel = next((lv for lv in candidatas if lv.id == nivel_id),
                 candidatas[0]) if nivel_id else candidatas[0]
    recinto = _recinto_del_nivel(ctx, nivel.id)
    if recinto is None:
        resumen["avisos"].append(
            "No hay locales para medir la fachada: genera antes la "
            "edificación.")
        return resumen
    resumen["eliminados"] = quitar_pieles(ctx)
    _niveles, altura_total = _n_niveles_hasta_arriba(ctx, nivel.id)
    lados_resueltos: List[Dict[str, Any]] = []
    for lado in reglas["lados"]:
        cx, cy, rot, largo = linea_fachada(recinto, lado)
        px, py = _desplaza(cx, cy, lado, reglas["separacion_m"])
        entidad = FacadeSkin(
            project_id=ctx.project.id,
            code=ctx.next_code("ARCHITECTURE", "SKIN"),
            level_id=nivel.id, side=lado, tipo=reglas["tipo"],
            material=reglas["material"],
            x=round(px, 4), y=round(py, 4), rotation_deg=rot,
            length_m=round(largo, 4),
            altura_m=round(altura_total, 3),
            separacion_m=reglas["separacion_m"],
            metadata=metadata_origen(
                f"piel {ETIQUETA_PIEL.get(reglas['tipo'], reglas['tipo'])}"
                f" en la fachada {ETIQUETA_LADO[lado]}",
                {"estilo": reglas["estilo"],
                 "apertura_pct": reglas["apertura_pct"],
                 "niveles_cubiertos": _niveles,
                 "cota_base_m": round(float(getattr(nivel, "elevation_m",
                                                    0.0) or 0.0), 3)}))
        alta_entidad(ctx, entidad)
        resumen["creados"].append(entidad.code)
        lados_resueltos.append({"lado": lado,
                                "length_m": round(largo, 2),
                                "altura_m": round(altura_total, 2)})
    resumen["parametros"] = {**reglas, "nivel": getattr(nivel, "name", ""),
                             "lados_resueltos": lados_resueltos}
    if con_qto:
        cerrar_qto(ctx, resumen)
    return resumen


# ---------------------------------------------------------------------------
# resúmenes
# ---------------------------------------------------------------------------

def _longitud_lamas(parasol: Any) -> float:
    """Desarrollo total de lamas de un parasol (QTO)."""
    n = max(int(getattr(parasol, "n_lamas", 0) or 0), 0)
    return n * float(getattr(parasol, "length_m", 0.0) or 0.0)


def _area_sombra(parasol: Any) -> float:
    """Área proyectada de sombra (lamas x vuelo), aproximación plana."""
    return _longitud_lamas(parasol) * float(
        getattr(parasol, "profundidad_m", 0.0) or 0.0)


def resumen_texto_parasoles(resumen: Dict[str, Any]) -> str:
    """Línea cp1252 con el resultado de los parasoles."""
    partes: List[str] = []
    lados_resueltos = (resumen.get("parametros") or {}).get(
        "lados_resueltos") or []
    if lados_resueltos:
        detalle = ", ".join(
            f"{ETIQUETA_LADO.get(d['lado'], d['lado'])}: "
            f"{ETIQUETA_PARASOL.get(d['tipo'], d['tipo'])} x{d['n_lamas']}"
            for d in lados_resueltos[:3])
        material = (resumen.get("parametros") or {}).get("material", "")
        partes.append("Parasoles de "
                      + ETIQUETA_MATERIAL.get(material, material)
                      + " (" + detalle + ")")
    else:
        partes.append("Parasoles")
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} PARASOL creado(s)")
    if resumen.get("eliminados"):
        partes.append(f"{len(resumen['eliminados'])} baja(s)")
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


def resumen_texto_piel(resumen: Dict[str, Any]) -> str:
    """Línea cp1252 con el resultado de la piel exterior."""
    partes: List[str] = []
    p = resumen.get("parametros") or {}
    if p.get("tipo"):
        texto = ("Piel: " + ETIQUETA_PIEL.get(p["tipo"], p["tipo"])
                 + f" · cámara {p.get('separacion_m', 0):.2f} m")
        if p.get("estilo"):
            texto += f" · sugerida por el estilo {p['estilo']}"
        partes.append(texto)
    else:
        partes.append("Piel exterior")
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} SKIN creado(s)")
    if resumen.get("eliminados"):
        partes.append(f"{len(resumen['eliminados'])} baja(s)")
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


__all__ = [
    "LADOS", "ETIQUETA_LADO", "TIPOS_PARASOL", "MATERIALES_PARASOL",
    "ETIQUETA_PARASOL", "ETIQUETA_MATERIAL", "TIPOS_PIEL", "ETIQUETA_PIEL",
    "MATERIAL_POR_PIEL", "APERTURA_POR_PIEL", "ESTILO_PIEL",
    "PARASOL_POR_LADO", "SEPARACION_DEFECTO_M", "PROFUNDIDAD_DEFECTO_M",
    "SEPARACION_LAMA_DEFECTO_M", "ANCHO_LAMA_M", "ESPESOR_LAMA_M",
    "lados_pedidos", "linea_fachada", "resolver_parasol",
    "quitar_parasoles", "generar_parasoles", "resolver_piel",
    "quitar_pieles", "generar_piel", "_longitud_lamas", "_area_sombra",
    "resumen_texto_parasoles", "resumen_texto_piel",
]

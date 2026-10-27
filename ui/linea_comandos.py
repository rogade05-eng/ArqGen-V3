"""LINEA DE COMANDOS (v3.38.0) — ui/linea_comandos.py.

El estado de la linea de comandos de la GUI, sin Tk: historial con
dedupe adyacente y tope, autocompletado por prefijo, navegacion con
las flechas y la INTERPRETACION de lo tecleado, en este orden:

1. cadena vacia                  -> ``repetir`` (Enter repite la ultima)
2. ``=expr`` o expresion         -> ``expresion`` (evaluar_expresion)
3. forma de coordenada           -> ``coordenada`` (parse_punto, la GUI
                                    decide si la herramienta la come)
4. opcion de la herramienta      -> ``opcion`` (letras entre corchetes)
5. alias de comando              -> ``orden`` (teclado de trabajo)
6. lo demas                      -> ``desconocido``

El alias SIEMPRE gana sobre la opcion si coincide entero (que ``M``
deje de ser mover por ser opcion de otro comando seria traicion);
por eso las opciones se consultan solo si el texto no es un alias
completo. Los mensajes son 100 % codificables en cp1252.

Cero Tk: el mismo motor sirve a la GUI, a la CLI y a las pruebas.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from ui import coords_entrada as crd

TOPE_HISTORIAL = 200


class LineaComandos:
    """Historial e interpretacion de la linea de comandos."""

    def __init__(self, alias: Optional[Dict[str, str]] = None) -> None:
        # alias: {texto tecleado -> orden}; por defecto, ninguno
        # (la GUI inyecta keymap.ALIAS_COMANDOS ampliado).
        self._alias: Dict[str, str] = dict(alias or {})
        self._historial: List[str] = []
        self._vista: int = 0          # indice de navegacion con flechas
        self._borrador: str = ""      # lo escrito al salir del historial

    # ------------------------------------------------------------------
    # historial
    # ------------------------------------------------------------------
    def push(self, texto: str) -> None:
        """Registra una entrada; duplicados adyacentes colapsan (la
        lista de recall de AutoCAD), el tope es 200 lineas."""
        texto = str(texto or "").strip()
        if not texto:
            return
        if self._historial and self._historial[-1] == texto:
            self._vista = len(self._historial)
            return
        self._historial.append(texto)
        if len(self._historial) > TOPE_HISTORIAL:
            del self._historial[:-TOPE_HISTORIAL]
        self._vista = len(self._historial)

    @property
    def historial(self) -> List[str]:
        return list(self._historial)

    def limpiar(self) -> None:
        self._historial.clear()
        self._vista = 0
        self._borrador = ""

    # ------------------------------------------------------------------
    # navegacion con las flechas (como el recall de AutoCAD)
    # ------------------------------------------------------------------
    def flecha_arriba(self, borrador: str = "") -> str:
        """La entrada anterior; si acababa de escribir algo, se guarda
        como borrador para no perderlo."""
        if self._vista == len(self._historial) and borrador:
            self._borrador = borrador
        if not self._historial:
            return borrador
        self._vista = max(0, self._vista - 1)
        return self._historial[self._vista]

    def flecha_abajo(self) -> Optional[str]:
        """La entrada siguiente; pasado el final devuelve el borrador
        (o cadena vacia) y suelta el ancla del historial."""
        if self._vista >= len(self._historial):
            self._vista = len(self._historial)
            return self._borrador
        self._vista += 1
        if self._vista >= len(self._historial):
            self._vista = len(self._historial)
            return self._borrador
        return self._historial[self._vista]

    # ------------------------------------------------------------------
    # autocompletado por prefijo
    # ------------------------------------------------------------------
    def completar(self, prefijo: str) -> str:
        """Mejor sugerencia para lo tecleado: el alias mas corto que
        EMPIEZA por el prefijo (insensible a mayusculas). Sin
        sugerencia devuelve cadena vacia."""
        p = str(prefijo or "").strip().lower()
        if not p:
            return ""
        candidatos = sorted(a for a in self._alias
                            if a.startswith(p))
        if candidatos:
            return min(candidatos, key=len)
        # tambien por el NOMBRE de la orden a la que apuntan
        nombres = sorted({n for n in self._alias.values()
                          if n.lower().startswith(p)})
        return min(nombres, key=len) if nombres else ""

    # ------------------------------------------------------------------
    # interpretacion
    # ------------------------------------------------------------------
    def interpretar(self, texto: str,
                    opciones: Iterable[str] = (),
                    herramienta: Optional[str] = None,
                    ultimo_punto: Any = None,
                    punto_cursor: Any = None) -> Dict[str, Any]:
        """Clasifica lo tecleado para el dispatch de la GUI.

        Devuelve un dict con ``tipo`` en: ``vacio`` (Enter sin texto ->
        repetir), ``expresion`` (``valor`` float), ``coordenada``
        (``punto`` + ``clase`` + error amable si no se pudo anclar),
        ``opcion`` (``clave``), ``orden`` (``accion``) o
        ``desconocido``. ``ultimo_punto`` ancla los relativos (@) y
        ``punto_cursor`` las distancias directas; sin ancla el error
        viaja en el dict para que la GUI lo diga amable. Nunca lanza.
        """
        texto = str(texto or "").strip()
        if not texto:
            return {"tipo": "vacio", "herramienta": herramienta}
        # expresion suelta
        if texto.startswith("="):
            try:
                return {"tipo": "expresion",
                        "valor": crd.evaluar_expresion(texto),
                        "texto": texto, "herramienta": herramienta}
            except Exception as exc:  # noqa: BLE001 — amable, no lanza
                return {"tipo": "expresion", "texto": texto,
                        "error": _mensaje(exc), "herramienta": herramienta}
        # alias completo SIEMPRE gana (mayusculas da igual)
        orden = self._alias.get(texto.lower())
        if orden is None:
            # prefijo no ambiguo: "m" solo ejecuta si no hay "mi"
            p = texto.lower()
            exactos = [a for a in self._alias if a == p]
            prefijos = [a for a in self._alias if a.startswith(p)]
            if len(exactos) == 1 and len(prefijos) == 1:
                orden = self._alias[exactos[0]]
        if orden is not None:
            self.push(texto)
            return {"tipo": "orden", "accion": orden, "texto": texto,
                    "herramienta": herramienta}
        # coordenada (forma numerica)
        if crd.es_coordenada(texto):
            try:
                punto, clase = crd.parse_punto(texto, ultimo_punto,
                                               punto_cursor)
            except Exception as exc:  # noqa: BLE001 — error amable
                return {"tipo": "coordenada", "texto": texto,
                        "error": _mensaje(exc),
                        "herramienta": herramienta}
            return {"tipo": "coordenada", "punto": punto, "clase": clase,
                    "texto": texto, "herramienta": herramienta}
        # opcion de la herramienta (letras o palabra)
        for opcion in opciones:
            if not opcion:
                continue
            if texto.lower() == str(opcion).lower():
                return {"tipo": "opcion", "clave": opcion,
                        "texto": texto, "herramienta": herramienta}
        return {"tipo": "desconocido", "texto": texto,
                "herramienta": herramienta,
                "sugerencia": self.completar(texto)}


def _mensaje(exc: Exception) -> str:
    """El mensaje del error de dominio o el generico, cp1252."""
    mensaje = getattr(exc, "message", None)
    return str(mensaje if mensaje else exc)


__all__ = ["LineaComandos", "TOPE_HISTORIAL"]

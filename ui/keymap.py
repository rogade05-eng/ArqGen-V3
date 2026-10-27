"""TECLADO ESTILO AUTOCAD (v3.16.0, v3.38.0).

La GUI ya tenia atajos de aplicacion (Ctrl+Z, Ctrl+S...); esta capa
anade el TECLADO DE TRABAJO de AutoCAD para que quien viene de el se
sienta en casa sin tocar el raton:

- F2   ventana de texto: el historial completo de la linea de comandos
- F3   referencias (osnap) a extremos y puntos medios      ON por defecto
- F7   rejilla visible en el lienzo                        ON por defecto
- F8   modo ORTO: los pasos de una orden van rectos        OFF
- F9   IMANTACION: el punto cae en la rejilla              OFF
- F10  seguimiento polar                                   OFF
- F12  pantalla dinamica (DYN): distancia y angulo junto
       al cursor mientras dibuja                           ON por defecto
- ESC  cancela la orden en curso (igual que AutoCAD)
- ESPACIO / ENTER repite la ULTIMA orden
- alias de comando con el teclado: M mover, CO copiar, MI reflejar,
  RO girar, TR recortar, EX alargar, CHA/F chaflan, DIV dividir,
  S estirar, O paralela, E borrar, U deshacer, P pan; y desde v3.38.0
  las herramientas de DIBUJO (MU muro, ES espacio, ZO zona, PU puerta,
  VE ventana) y la NAVEGACION clasica (Z zoom ventana, ZE encuadrar
  todo, ZP zoom anterior, QC calculadora)
- Ctrl+Z deshacer, Ctrl+Y / Ctrl+Shift+Z rehacer, Ctrl+C copiar,
  Ctrl+X cortar, Ctrl+V pegar, Ctrl+S guardar, Ctrl+O abrir,
  Ctrl+N nuevo, Ctrl+A seleccionar todo, Ctrl+P imprimir

Cero Tk: el mismo motor sirve a la GUI, a la CLI y a las pruebas.
Todos los mensajes son 100 % codificables en cp1252 (disciplina
v3.13.1: nada de flechas, nada de emojis).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError

# error propio: ARQ-KEY-001 modo desconocido

# Modos conmutables y su tecla de funcion (etiquetas cp1252).
MODOS: Dict[str, Tuple[str, str]] = {
    # modo: (tecla, etiqueta para la barra de estado)
    "osnap": ("F3", "referencias a extremos y puntos medios"),
    "rejilla": ("F7", "rejilla visible"),
    "orto": ("F8", "modo orto"),
    "imantacion": ("F9", "imantacion a la rejilla"),
    "polar": ("F10", "seguimiento polar"),
    "din": ("F12", "pantalla dinamica (distancia y angulo)"),
}

# Estado de fabrica (igual que la instalacion tipica de AutoCAD).
ESTADO_DEFECTO: Dict[str, bool] = {
    "osnap": True,
    "rejilla": True,
    "orto": False,
    "imantacion": False,
    "polar": False,
    "din": True,
}

# Alias de comando, letra a letra como la linea de comandos de AutoCAD:
# el buffer acumula letras y al coincidir un alias completo ejecuta.
ALIAS_COMANDOS: Dict[str, str] = {
    "m": "mover",
    "co": "copiar_objeto",
    "mi": "reflejar",
    "ro": "girar",
    "tr": "recortar",
    "ex": "alargar",
    "cha": "chaflan",
    "f": "chaflan",
    "div": "dividir",
    "s": "estirar",
    "o": "paralela",
    "e": "borrar",
    "u": "deshacer",
    "p": "pan",
    "re": "rehacer",
    # herramientas de DIBUJO (v3.38.0): las cinco de la paleta
    "mu": "dib_muro",
    "es": "dib_espacio",
    "zo": "dib_zona",
    "pu": "dib_puerta",
    "ve": "dib_ventana",
    # NAVEGACION clasica (v3.38.0): Z con marco, ZE todo, ZP anterior
    "z": "zoom_ventana",
    "ze": "encuadrar",
    "zp": "zoom_anterior",
    "qc": "calculadora",
}

# Teclas de funcion que lanzan una ACCION (no un modo conmutable).
TECLA_ACCION: Dict[str, str] = {
    "f2": "historial_comandos",
}

# Acciones que ESPACIO puede repetir (las ordenes de dibujo/edicion;
# un F8 o un Ctrl+S no son «la ultima orden» en AutoCAD).
REPETIBLES = frozenset({
    "mover", "copiar_objeto", "reflejar", "girar", "recortar",
    "alargar", "chaflan", "dividir", "estirar", "paralela", "borrar",
    "encuadrar", "zoom+", "zoom-",
    "dib_muro", "dib_espacio", "dib_zona", "dib_puerta",
    "dib_ventana",
})

# Teclas de funcion conmutables -> modo (las teclas llegan en
# minusculas: el keysym «F8» se normaliza a «f8» en procesar()).
TECLA_MODO = {datos[0].lower(): modo for modo, datos in MODOS.items()}

# Combos Ctrl+<tecla> -> accion (Shift se aparta antes).
COMBOS_CTRL: Dict[str, str] = {
    "z": "deshacer",
    "y": "rehacer",
    "c": "copiar_seleccion",
    "x": "cortar",
    "v": "pegar",
    "s": "guardar",
    "o": "abrir",
    "n": "nuevo",
    "a": "seleccionar_todo",
    "p": "imprimir",
    "0": "encuadrar",
}

# Navegacion 2D con las flechas (pan fino, igual que el raton).
FLECHAS: Dict[str, str] = {
    "up": "pan_arriba",
    "down": "pan_abajo",
    "left": "pan_izquierda",
    "right": "pan_derecha",
}


class TecladoAutoCAD:
    """Estado y traduccion del teclado de trabajo a ACCIONES.

    La GUI registra las acciones en un dispatch propio; las pruebas
    pueden usar el motor solo, sin ventana.
    """

    def __init__(self,
                 estado: Optional[Dict[str, bool]] = None) -> None:
        self.estado: Dict[str, bool] = dict(ESTADO_DEFECTO)
        if estado:
            for modo, valor in estado.items():
                if modo in self.estado:
                    self.estado[modo] = bool(valor)
        self._letras: str = ""
        self.ultima_accion: Optional[str] = None
        self.ultimo_mensaje: str = ""

    # ------------------------------------------------------------------
    # modos
    # ------------------------------------------------------------------
    def alternar(self, modo: str) -> Tuple[bool, str]:
        """Conmuta un modo y devuelve (nuevo_estado, mensaje cp1252)."""
        if modo not in self.estado:
            raise DomainError(
                message=f"Modo de teclado desconocido: {modo}",
                code="ARQ-KEY-001",
                context={"modo": modo, "permitidos": sorted(self.estado)},
                suggested_action="Usa uno de: " + ", ".join(sorted(
                    self.estado)))
        self.estado[modo] = not self.estado[modo]
        tecla, etiqueta = MODOS.get(modo, (modo.upper(), modo))
        palabra = "ACTIVADO" if self.estado[modo] else "DESACTIVADO"
        mensaje = f"<{tecla}> {etiqueta}: {palabra}"
        self.ultimo_mensaje = mensaje
        return self.estado[modo], mensaje

    def mensaje_modo(self, modo: str) -> str:
        """Linea de estado del modo tal y como queda ahora."""
        tecla, etiqueta = MODOS.get(modo, (modo.upper(), modo))
        palabra = "ACTIVADO" if self.estado.get(modo) else "DESACTIVADO"
        return f"<{tecla}> {etiqueta}: {palabra}"

    # ------------------------------------------------------------------
    # procesado de teclas
    # ------------------------------------------------------------------
    def procesar(self, tecla: str, ctrl: bool = False,
                 shift: bool = False) -> Optional[str]:
        """Traduce una pulsacion a una ACCION (o None si no toca nada).

        ``tecla`` es el keysym de Tk en minusculas: «f8», «escape»,
        «space», «m», «plus», «left»...
        """
        self.ultimo_mensaje = ""
        if not tecla:
            return None
        t = str(tecla).lower()

        if ctrl:
            base = t
            if base.startswith("key-"):
                base = base[4:]
            if shift and base == "z":
                accion = "rehacer"
            else:
                accion = COMBOS_CTRL.get(base)
            if accion:
                self._record(accion)
            return accion

        if t in TECLA_MODO:
            modo = TECLA_MODO[t]
            self.alternar(modo)
            return f"alternar_{modo}"

        accion_tecla = TECLA_ACCION.get(t)
        if accion_tecla:
            return accion_tecla

        if t in ("escape",):
            self._letras = ""
            return "cancelar"
        if t in ("space", "return", "enter"):
            # si habia un alias COMPLETO esperando (m + ESPACIO), se
            # ejecuta; si no, ESPACIO repite la ultima orden
            pendiente = ALIAS_COMANDOS.get(self._letras)
            self._letras = ""
            if pendiente is not None:
                return self._record(pendiente)
            return "repetir"
        if t == "delete":
            return "suprimir"
        if t in FLECHAS:
            return FLECHAS[t]
        if t in ("plus", "equal", "kp_add"):
            return self._record("zoom+")
        if t in ("minus", "kp_subtract"):
            return self._record("zoom-")

        # alias de comando letra a letra: si el buffer es un alias
        # COMPLETO y ademas prefijo de uno mas largo (m -> mover, pero
        # mi -> reflejar), ESPACIO lo ejecuta y la letra siguiente lo
        # alarga, igual que la linea de comandos de AutoCAD
        if len(t) == 1 and t.isalpha():
            self._letras += t
            buf = self._letras
            completo = ALIAS_COMANDOS.get(buf)
            prefijo_largo = any(alias.startswith(buf) and alias != buf
                                for alias in ALIAS_COMANDOS)
            if completo is not None and not prefijo_largo:
                self._letras = ""
                return self._record(completo)
            if completo is not None or prefijo_largo:
                return None          # esperando mas letras o ESPACIO
            self._letras = ""
            return None
        self._letras = ""
        return None

    def _record(self, accion: str) -> str:
        if accion in REPETIBLES:
            self.ultima_accion = accion
        return accion

    def registrar_orden(self, accion: str) -> None:
        """La GUI avisa de una orden ejecutada por VIA EXTERNA (paleta,
        asistente, menu) para que ESPACIO la repita igual que AutoCAD."""
        self._record(accion)

    # ------------------------------------------------------------------
    # utilidades de prueba / estado
    # ------------------------------------------------------------------
    def buffer(self) -> str:
        return self._letras

    def reiniciar(self) -> None:
        self._letras = ""
        self.ultima_accion = None
        self.ultimo_mensaje = ""


def resumen_atajos() -> List[str]:
    """Lista de lineas cp1252 para la ayuda (Ayuda -> Atajos)."""
    lineas: List[str] = []
    for modo, (tecla, etiqueta) in MODOS.items():
        defecto = "ON" if ESTADO_DEFECTO[modo] else "OFF"
        lineas.append(f"{tecla} - {etiqueta} (fabrica: {defecto})")
    lineas += [
        "F2 - historial de la linea de comandos (ventana de texto)",
        "ESC - cancela la orden en curso",
        "ESPACIO / ENTER - repite la ultima orden",
        "MU/ES/ZO/PU/VE - herramientas de dibujo",
        "M/CO/MI/RO/TR/EX/CHA/DIV/S/O/E - herramientas de edicion",
        "U deshacer, P pan, Z zoom ventana, ZE encuadrar, ZP zoom anterior",
        "QC calculadora; coordenadas 10,5 / @10,5 / @10<45 / 25",
        "flechas pan fino, +/- zoom",
        "Ctrl+Z deshacer, Ctrl+Y o Ctrl+Shift+Z rehacer",
        "Ctrl+C copiar, Ctrl+X cortar, Ctrl+V pegar",
        "Ctrl+S guardar, Ctrl+O abrir, Ctrl+N nuevo, Ctrl+P imprimir",
        "Ctrl+A seleccionar todo, Ctrl+0 encuadrar todo",
    ]
    return lineas


__all__ = [
    "MODOS", "ESTADO_DEFECTO", "ALIAS_COMANDOS", "REPETIBLES",
    "TECLA_MODO", "TECLA_ACCION", "COMBOS_CTRL", "FLECHAS",
    "TecladoAutoCAD", "resumen_atajos",
]

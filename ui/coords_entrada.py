"""ENTRADA DE COORDENADAS POR TECLADO (v3.38.0) — ui/coords_entrada.py.

La gramatica de la linea de comandos de AutoCAD para el punto que se
teclea mientras una herramienta esta armada (ideas del CAD clasico,
reimplementadas de cero para ARQ GEN):

- ``10,5``      punto ABSOLUTO (x,y en metros)
- ``@10,5``     RELATIVO al ultimo punto de la orden
- ``10<45``     polar absoluto: distancia<angulo desde el origen
- ``@10<45``    polar relativo: distancia y angulo desde el ultimo punto
- ``25``        DISTANCIA DIRECTA: 25 m desde el ultimo punto hacia
                donde apunta el cursor (necesita cursor de referencia)
- ``#10,5``     fuerza ABSOLUTO aunque DYN pida relativo (honestidad:
                ARQ GEN no activa ese modo, pero la gramatica lo soporta)
- ``2*3.5+0.2`` EXPRESION aritmetica en cualquiera de los campos
- ``=2*3.5``    expresion suelta (la linea de comandos devuelve el valor)

Los campos numericos admiten expresiones seguras evaluadas por AST
(sin nombres, sin llamadas, sin atributos): la misma disciplina que
core.rules aplica a las reglas. Los mensajes son 100 % codificables en
cp1252 (disciplina v3.13.1: sin flechas ni emojis).

Cero Tk: el mismo motor sirve a la GUI, a la CLI y a las pruebas.
"""

from __future__ import annotations

import ast
import math
from typing import Any, List, Optional, Tuple

from core.errors import DomainError

PT = Tuple[float, float]

# errores propios: ARQ-CRD-001..004

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


# ---------------------------------------------------------------------------
# expresiones aritmeticas seguras (AST, sin nombres ni llamadas)
# ---------------------------------------------------------------------------

_OPS_SEGURAS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
                ast.USub, ast.UAdd, ast.FloorDiv, ast.Mod)


def evaluar_expresion(texto: str) -> float:
    """Evalua una expresion aritmetica segura y devuelve un float.

    Soporta + - * / ** // %, parentesis, signo unario y la constante
    ``pi``. Rechaza nombres, llamadas, atributos, indices y cualquier
    otra cosa: una expresion que llega del usuario nunca puede ejecutar
    codigo. Lanza DomainError ARQ-CRD-003 si no es aritmetica pura o
    ARQ-CRD-004 si no se puede calcular (division por cero, etc.).
    """
    fuente = str(texto or "").strip()
    if fuente.startswith("="):
        fuente = fuente[1:].strip()
    if not fuente:
        raise DomainError(
            message="La expresion esta vacia",
            code="ARQ-CRD-003",
            suggested_action="Escribe una operacion, por ejemplo 2*3.5+0.2")
    fuente = fuente.replace(",", ".")
    fuente = fuente.replace("PI", "pi").replace("Pi", "pi")
    try:
        arbol = ast.parse(fuente, mode="eval")
    except SyntaxError:
        raise DomainError(
            message=f"La expresion no es valida: {fuente}",
            code="ARQ-CRD-003",
            suggested_action="Usa solo numeros, + - * / ** ( ) y pi")
    valor = _eval_nodo(arbol.body)
    if valor is None or isinstance(valor, bool) \
            or not isinstance(valor, (int, float)):
        raise DomainError(
            message=f"La expresion no es aritmetica pura: {fuente}",
            code="ARQ-CRD-003",
            suggested_action="Usa solo numeros, + - * / ** ( ) y pi")
    resultado = float(valor)
    if not math.isfinite(resultado):
        raise DomainError(
            message=f"El resultado de la expresion no es finito: {fuente}",
            code="ARQ-CRD-004",
            suggested_action="Revisa los operadores de la expresion")
    return resultado


def _eval_nodo(nodo: ast.AST) -> Any:
    """Recorre el AST rechazando todo lo que no sea aritmetica."""
    if isinstance(nodo, ast.Expression):
        return _eval_nodo(nodo.body)
    if isinstance(nodo, ast.Constant):
        if isinstance(nodo.value, (int, float)) \
                and not isinstance(nodo.value, bool):
            return nodo.value
        return None
    if isinstance(nodo, ast.Name):
        return math.pi if nodo.id == "pi" else None
    if isinstance(nodo, ast.UnaryOp) \
            and isinstance(nodo.op, (ast.USub, ast.UAdd)):
        valor = _eval_nodo(nodo.operand)
        if valor is None:
            return None
        return -valor if isinstance(nodo.op, ast.USub) else +valor
    if isinstance(nodo, ast.BinOp) \
            and isinstance(nodo.op, _OPS_SEGURAS):
        izq = _eval_nodo(nodo.left)
        der = _eval_nodo(nodo.right)
        if izq is None or der is None:
            return None
        try:
            if isinstance(nodo.op, ast.Add):
                return izq + der
            if isinstance(nodo.op, ast.Sub):
                return izq - der
            if isinstance(nodo.op, ast.Mult):
                return izq * der
            if isinstance(nodo.op, ast.Div):
                return izq / der
            if isinstance(nodo.op, ast.FloorDiv):
                return izq // der
            if isinstance(nodo.op, ast.Mod):
                return izq % der
            if isinstance(nodo.op, ast.Pow):
                if abs(der) > 64:
                    return None     # exponentes desmedidos: fuera
                return izq ** der
        except ZeroDivisionError:
            raise DomainError(
                message="La expresion divide por cero",
                code="ARQ-CRD-004",
                suggested_action="Revisa el denominador de la expresion")
        except OverflowError:
            raise DomainError(
                message="La expresion desborda",
                code="ARQ-CRD-004",
                suggested_action="Reduce los operandos de la expresion")
    return None


# ---------------------------------------------------------------------------
# parseo del punto tecleado
# ---------------------------------------------------------------------------

def _campo(texto: str) -> float:
    """Un campo numerico: numero o expresion segura."""
    texto = (texto or "").strip()
    if not texto:
        raise DomainError(
            message="Falta un valor en el punto tecleado",
            code="ARQ-CRD-001",
            suggested_action="Ejemplos: 10,5  @10,5  @10<45  25")
    try:
        return float(texto)
    except ValueError:
        return evaluar_expresion(texto)


def es_coordenada(texto: str) -> bool:
    """True si el texto TIENE FORMA de punto (numero, expresion, coma o
    <): el que llama puede decidir si tratarlo como coordenada u opcion
    sin consumir la entrada. ``10,5`` si, ``M`` no, ``2*3`` si."""
    t = str(texto or "").strip()
    if not t:
        return False
    if t.startswith(("@", "#")):
        t = t[1:]
    if not t:
        return False
    if t.startswith("="):
        return True
    if t[0].isdigit() or (t[0] in "+-." and len(t) > 1
                          and any(c.isdigit() for c in t)):
        return True
    return False


def parse_punto(texto: str,
                ultimo_punto: Optional[PT] = None,
                punto_cursor: Optional[PT] = None) -> Tuple[PT, str]:
    """Convierte el texto tecleado en un punto del plano.

    Devuelve ((x, y), clase) donde clase es una de:
    ``absoluto`` | ``relativo`` | ``polar`` | ``polar_relativo`` |
    ``distancia_directa``. Lanza DomainError ARQ-CRD-001 si el texto no
    tiene forma de coordenada y ARQ-CRD-002 si la forma elegida
    necesita un punto de referencia que no llega (ultimo punto o
    cursor). ``punto_cursor`` solo hace falta para la distancia
    directa.
    """
    t = str(texto or "").strip()
    if not t:
        raise DomainError(
            message="No hay punto que interpretar",
            code="ARQ-CRD-001",
            suggested_action="Ejemplos: 10,5  @10,5  @10<45  25")
    forzar_absoluto = t.startswith("#")
    relativo = t.startswith("@")
    if forzar_absoluto or relativo:
        t = t[1:].strip()
        if not t:
            raise DomainError(
                message="El punto tecleado esta incompleto",
                code="ARQ-CRD-001",
                suggested_action="Ejemplos: @10,5  @10<45")
    # polar: distancia<angulo
    if "<" in t:
        distancia_txt, _, angulo_txt = t.partition("<")
        distancia = _campo(distancia_txt)
        angulo = _campo(angulo_txt)
        base: PT = ultimo_punto if relativo else (0.0, 0.0)
        if relativo and ultimo_punto is None:
            raise DomainError(
                message="El punto polar relativo necesita un punto "
                        "anterior",
                code="ARQ-CRD-002",
                suggested_action="Introduce un primer punto con clic o "
                                 "coordenada absoluta, o usa 10<45")
        rad = math.radians(angulo)
        clase = "polar_relativo" if relativo else "polar"
        return ((base[0] + distancia * math.cos(rad),
                 base[1] + distancia * math.sin(rad)), clase)
    # par x,y
    if "," in t or ";" in t:
        separador = "," if "," in t else ";"
        partes = t.split(separador)
        if len(partes) != 2:
            raise DomainError(
                message="El punto tiene demasiados campos",
                code="ARQ-CRD-001",
                suggested_action="El formato es x,y (dos campos)")
        x = _campo(partes[0])
        y = _campo(partes[1])
        if (relativo or _relativo_implicito(x, y, partes)) \
                and not forzar_absoluto:
            if ultimo_punto is None:
                raise DomainError(
                    message="El punto relativo necesita un punto "
                            "anterior",
                    code="ARQ-CRD-002",
                    suggested_action="Introduce un primer punto con "
                                     "clic o coordenada absoluta, o "
                                     "usa #10,5 para forzar absoluto")
            return ((ultimo_punto[0] + x, ultimo_punto[1] + y),
                    "relativo")
        return ((x, y), "absoluto")
    # un valor solo: @25 sin direccion es un punto incompleto; 25 es
    # distancia directa hacia el cursor
    if relativo:
        raise DomainError(
            message="El punto relativo esta incompleto: falta el "
                    "angulo o la segunda coordenada",
            code="ARQ-CRD-001",
            suggested_action="Ejemplos: @10,5  @10<45")
    try:
        distancia = _campo(t)
    except DomainError:
        raise DomainError(
            message=f"El punto tecleado no se entiende: {texto}",
            code="ARQ-CRD-001",
            suggested_action="Ejemplos: 10,5  @10,5  @10<45  25")
    if distancia < 0:
        raise DomainError(
            message="La distancia directa no puede ser negativa",
            code="ARQ-CRD-001",
            suggested_action="Gira el cursor hacia el punto y repite")
    if punto_cursor is None or ultimo_punto is None:
        raise DomainError(
            message="La distancia directa necesita el cursor de "
                    "referencia y un punto anterior",
            code="ARQ-CRD-002",
            suggested_action="Mueve el cursor a la direccion deseada "
                             "antes de teclear la distancia")
    dx = punto_cursor[0] - ultimo_punto[0]
    dy = punto_cursor[1] - ultimo_punto[1]
    largo = math.hypot(dx, dy)
    if largo < 1e-12:
        raise DomainError(
            message="El cursor esta sobre el punto anterior: no hay "
                    "direccion para la distancia directa",
            code="ARQ-CRD-002",
            suggested_action="Aleja el cursor de la base y repite")
    return ((ultimo_punto[0] + dx / largo * distancia,
             ultimo_punto[1] + dy / largo * distancia),
            "distancia_directa")


def _relativo_implicito(x: float, y: float, partes: List[str]) -> bool:
    """Sin DYN relativo (ARQ GEN no lo activa), un ``10,5`` sin @ es
    SIEMPRE absoluto. La funcion existe por legibilidad del flujo."""
    return False


# ---------------------------------------------------------------------------
# pantalla dinamica (DYN)
# ---------------------------------------------------------------------------

def texto_dinamico(origen: Optional[PT], destino: PT) -> str:
    """Linea DYN junto al cursor: distancia y angulo del tramo vivo.

    ``d 3.42 < 45`` (cp1252 puro). Sin origen devuelve cadena vacia:
    antes del primer punto no hay nada que medir.
    """
    if origen is None:
        return ""
    dx = destino[0] - origen[0]
    dy = destino[1] - origen[1]
    distancia = math.hypot(dx, dy)
    angulo = math.degrees(math.atan2(dy, dx)) % 360.0
    return f"d {distancia:.2f} < {angulo:.0f}"


def texto_punto(punto: PT) -> str:
    """Coordenada legible para el historial: ``x 10.000  y 5.000``."""
    return f"x {punto[0]:.3f}  y {punto[1]:.3f}"


__all__ = [
    "evaluar_expresion", "es_coordenada", "parse_punto",
    "texto_dinamico", "texto_punto",
]

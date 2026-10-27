"""Exportador Markdown → PDF 100% stdlib (v3.8.0).

Convierte los documentos generados por DocumentationService (memoria,
especificaciones, cuadros, listados, informe) en un PDF A4 vectorial
reutilizando PdfReport (cabecera con título y fecha, saltos de página
automáticos, tablas con cabecera repetida).

Reconoce el subconjunto markdown que produce el motor de documentación:
encabezados (# / ##), listas con guion, tablas con tuberías, negritas
(**x**) y código entre acentos graves. Todo lo demás sale como
párrafo. Determinista dentro del mismo día (la cabecera lleva la
fecha).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Sequence, Tuple

from core.errors import ExportError
from exporters.pdf_exporter import MARGIN, PAGE_W, PdfReport, text_width

#: Símbolos sin cabida en WinAnsi → sustitución honesta.
_TRANSLIT: Dict[str, str] = {
    "→": "->", "⇒": "=>", "←": "<-", "≥": ">=", "≤": "<=", "≠": "!=",
    "×": "x", "÷": "/", "↑": "^", "↓": "v", "•": "-",
}


def _limpiar(texto: str) -> str:
    """Translitera símbolos y quita marcadores markdown inline."""
    texto = str(texto)
    for origen, destino in _TRANSLIT.items():
        texto = texto.replace(origen, destino)
    texto = texto.replace("**", "")
    while "`" in texto:
        texto = texto.replace("`", "", 2)
    return texto


def _celda_ajustada(texto: str, ancho: float, size: float) -> str:
    """Recorta el texto de una celda para que quepa en su columna."""
    while texto and text_width(texto, size) > ancho - 8.0:
        texto = texto[:-1]
    return texto


def _es_fila_separador(linea: str) -> bool:
    cuerpo = linea.strip().strip("|")
    if not cuerpo:
        return False
    celdas = [c.strip() for c in cuerpo.split("|")]
    return bool(celdas) and all(
        set(celda) <= set("-: ") for celda in celdas)


def _celdas(linea: str) -> List[str]:
    return [_limpiar(c.strip())
            for c in linea.strip().strip("|").split("|")]


def _ancho_columnas(tabla: List[List[str]]) -> List[float]:
    """Anchos proporcionales al contenido, con mínimo por columna."""
    disponible = PAGE_W - 2 * MARGIN
    n_cols = max(len(fila) for fila in tabla)
    pesos: List[float] = []
    for indice in range(n_cols):
        contenido = [str(fila[indice]) for fila in tabla
                     if indice < len(fila)]
        peso = max([len(c) for c in contenido] or [1])
        pesos.append(max(float(peso), 6.0))
    total = sum(pesos)
    minimo = 42.0
    escalado = [disponible * p / total for p in pesos]
    # Garantiza el mínimo re-distribuyendo el excedente.
    deficit = sum(minimo - ancho for ancho in escalado if ancho < minimo)
    if deficit > 0:
        holgura = sum(a - minimo for a in escalado if a > minimo)
        if holgura > 0:
            escalado = [
                minimo + (a - minimo) * (1 - deficit / holgura)
                if a > minimo else minimo
                for a in escalado]
    return escalado


def _flush_table(report: PdfReport, tabla: List[List[str]]) -> None:
    if not tabla:
        return
    n_cols = max(len(fila) for fila in tabla)
    tabla = [fila + [""] * (n_cols - len(fila)) for fila in tabla]
    anchos = _ancho_columnas(tabla)
    cabecera = tabla[0]
    datos = tabla[1:]
    numerica = all(
        _es_numero(fila[i]) for fila in datos
        for i in range(n_cols) if i < len(fila) and str(fila[i]).strip())
    alineaciones = ["r" if numerica else "l" for _ in range(n_cols)]
    headers: Sequence[Tuple[str, str, float]] = [
        (_celda_ajustada(cabecera[i], anchos[i], 8.2), alineaciones[i],
         anchos[i]) for i in range(n_cols)]
    filas: List[List[str]] = [
        [_celda_ajustada(str(celda), anchos[i], 8.2)
         for i, celda in enumerate(fila)] for fila in datos]
    report.table(headers, filas)


def _es_numero(texto: str) -> bool:
    candidato = str(texto).strip().replace(" ", "")
    if not candidato:
        return False
    candidato = candidato.replace(",", ".")
    try:
        float(candidato)
        return True
    except ValueError:
        return False


def export_markdown_pdf(markdown_text: str, out_path: str,
                        subtitle: str = "") -> str:
    """Convierte un documento markdown de ARQ GEN en PDF A4.

    Devuelve ``out_path``; lanza ``ExportError`` (ARQ-EXP-072) si el
    documento está vacío. Crea los directorios que falten.
    """
    texto = str(markdown_text or "")
    if not texto.strip():
        raise ExportError(
            message="El documento está vacío: no hay nada que exportar "
                    "a PDF",
            code="ARQ-EXP-072",
            context={"out_path": out_path})
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    titulo = "Documento"
    indice = 0
    while indice < len(lineas) and not lineas[indice].strip():
        indice += 1
    if indice < len(lineas) and lineas[indice].lstrip().startswith("# "):
        titulo = _limpiar(lineas[indice].lstrip()[2:].strip())
        indice += 1

    report = PdfReport(title=titulo, subtitle=subtitle)
    tabla: List[List[str]] = []

    def cierra_tabla() -> None:
        nonlocal tabla
        _flush_table(report, tabla)
        tabla = []

    for linea in lineas[indice:]:
        cruda = linea.rstrip()
        if not cruda.strip():
            cierra_tabla()
            report.spacer(4.0)
            continue
        tira = cruda.strip()
        if tira.startswith("|"):
            if _es_fila_separador(tira):
                continue
            tabla.append(_celdas(tira))
            continue
        cierra_tabla()
        if tira.startswith("### ") or tira.startswith("## "):
            report.heading(_limpiar(tira.lstrip("#").strip()))
            continue
        if tira.startswith("# "):
            report.heading(_limpiar(tira[2:].strip()))
            continue
        if tira.startswith("- ") or tira.startswith("* "):
            report.para("• " + _limpiar(tira[2:].strip()))
            continue
        tira_normalizada = tira.lstrip()
        if tira_normalizada.startswith("- "):
            report.para("• " + _limpiar(tira_normalizada[2:].strip()))
            continue
        report.para(_limpiar(tira))
    cierra_tabla()

    directorio = os.path.dirname(out_path)
    if directorio:
        os.makedirs(directorio, exist_ok=True)
    return report.save(out_path)


__all__ = ["export_markdown_pdf"]

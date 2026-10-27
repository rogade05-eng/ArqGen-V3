"""Informe de validación en HTML autocontenido (v3.27.0).

El mismo informe que la GUI muestra en el cuadro de texto, exportado
como UN SOLO archivo .html que se abre en cualquier navegador, se
adjunta a un expediente o se imprime, sin depender de ARQ_GEN:

- Cero dependencias (stdlib ``html``) y cero recursos externos: el
  CSS viaja embebido en ``<style>`` y no hay ni una URL absoluta, así
  el archivo sigue siendo fiel offline (misma disciplina que el resto
  del programa).
- Sirve para TODOS los informes del dominio (vivienda VIV001-030,
  comercial CC/OF y educacional ED): el dict del informe se recorre
  con claves opcionales — lo que falte, no se dibuja.
- Los hallazgos aceptan dicts (comercial y educacional) u objetos con
  atributos (vivienda), igual que los ``texto_validacion_*``.
- Honradez visual: cada hallazgo conserva su estado — «(pendiente)» y
  «(REQUIERE_CALCULO_ESPECIALIZADO)» se imprimen, no se esconden, y
  el pie repite que el informe no sustituye el cálculo especializado.

El HTML es UTF-8 con ``<meta charset="utf-8">`` (el límite cp1252 es
de la CONSOLA de Windows; un archivo HTML declara su juego de
caracteres y los navegadores sí saben de acentos y «§»).
"""

from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from core import APP_VERSION
from core.errors import ExportError

# -- marca/severidad (mismo lenguaje que los cuadros de texto) --------------

_ETIQUETA_SEVERIDAD = {
    "ok": "OK", "fallo": "FALLA", "aviso": "AVISO", "info": "INFO",
}
_ETIQUETA_ESTADO = {
    "medido": "",
    "pendiente": " (pendiente)",
    "requiere calculo": " (REQUIERE_CALCULO_ESPECIALIZADO)",
}
_ORDEN_RESUMEN = (
    ("ok", "cumplen"), ("fallos", "fallos"), ("avisos", "avisos"),
    ("pendientes", "pendientes o de cálculo"), ("info", "informativos"),
)

_CSS = """
:root { --ok:#1a7f37; --fallo:#c62828; --aviso:#b26a00; --info:#1565c0;
        --tinta:#1c2430; --suave:#5b6572; --linea:#d8dee6;
        --fondo:#f7f8fa; --panel:#ffffff; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 18px 40px; background: var(--fondo);
       color: var(--tinta);
       font: 15px/1.45 "Segoe UI", Arial, Helvetica, sans-serif; }
main { max-width: 980px; margin: 0 auto; background: var(--panel);
       border: 1px solid var(--linea); border-radius: 10px;
       padding: 26px 30px 30px; }
h1 { font-size: 21px; margin: 0 0 2px; }
h2 { font-size: 16px; margin: 26px 0 8px; border-bottom: 1px solid
     var(--linea); padding-bottom: 5px; }
.edificacion { color: var(--suave); font-weight: 600; font-size: 15px;
               margin: 0 0 10px; }
.chips { margin: 8px 0 2px; }
.chip { display: inline-block; background: #eef1f5; border: 1px solid
        var(--linea); border-radius: 999px; padding: 2px 11px;
        margin: 2px 4px 2px 0; font-size: 12.5px; color: var(--suave); }
.chip b { color: var(--tinta); font-weight: 600; }
.badges { margin: 10px 0 0; }
.badge { display: inline-block; border-radius: 6px; padding: 3px 10px;
         margin: 2px 6px 2px 0; font-size: 13px; font-weight: 600;
         color: #fff; }
.badge.ok { background: var(--ok); }
.badge.fallo { background: var(--fallo); }
.badge.aviso { background: var(--aviso); }
.badge.pendiente { background: var(--info); }
.nota { background: #fff8e6; border: 1px solid #eadfb2;
        border-left: 4px solid var(--aviso); border-radius: 6px;
        padding: 9px 13px; margin: 14px 0 0; font-size: 14px; }
table { border-collapse: collapse; width: 100%; margin-top: 8px;
        font-size: 13.5px; }
th, td { text-align: left; vertical-align: top;
         border-bottom: 1px solid var(--linea); padding: 6px 8px; }
th { background: #eef1f5; font-size: 12.5px; text-transform:
     uppercase; letter-spacing: .03em; color: var(--suave); }
tr.ultima td { border-bottom: 0; }
td.cod { white-space: nowrap; font-weight: 600; }
.marca { display: inline-block; min-width: 46px; text-align: center;
         border-radius: 5px; padding: 1px 7px; font-size: 12px;
         font-weight: 700; color: #fff; }
.marca.ok { background: var(--ok); }
.marca.fallo { background: var(--fallo); }
.marca.aviso { background: var(--aviso); }
.marca.info { background: var(--info); }
.estado { color: var(--suave); }
.fuente { color: var(--suave); font-size: 12px; white-space: nowrap; }
ul { margin: 6px 0 0; padding-left: 22px; }
li { margin: 3px 0; }
dl.prio { margin: 6px 0 0; }
dl.prio dt { font-weight: 600; margin-top: 7px; }
dl.prio dd { margin: 1px 0 0 0; color: var(--tinta); }
footer { margin-top: 28px; border-top: 1px solid var(--linea);
         padding-top: 10px; color: var(--suave); font-size: 12.5px; }
@media print { body { background: #fff; padding: 0; }
  main { border: 0; max-width: none; } }
"""

# claves de metadatos opcionales del informe (orden de presentación)
_META_CHIPS: Iterable[Any] = (
    ("uso", "uso"), ("familias", "familias"), ("tamano", "tamaño"),
    ("tipologia", "tipología"), ("sistema", "sistema"),
    ("estilo", "estilo"), ("clima", "clima"), ("calidad", "calidad"),
)
# secciones genéricas de listas (clave del informe → título visible)
_SECCIONES_LISTA = (
    ("reglas", "Reglas de validación del documento"),
    ("prioridades", "Prioridades del documento"),
    ("conflictos", "Conflictos del documento"),
    ("conflictos_no_geometricos", "Conflictos no geométricos"),
    ("checklist", "Checklist"),
    ("normativa", "Normativa y referencias"),
    ("documentacion", "Documentación a presentar"),
)


def _esc(valor: Any) -> str:
    """Escapa todo lo que va a parar al HTML (nada se interpola crudo)."""
    return html.escape(str(valor), quote=True)


def _campo(objeto: Any, clave: str) -> Any:
    """Lee ``clave`` de un dict o de un objeto (dict.get | getattr)."""
    if isinstance(objeto, dict):
        return objeto.get(clave)
    return getattr(objeto, clave, None)


def _lista_de(objeto: Any, clave: str) -> List[Any]:
    valor = _campo(objeto, clave)
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return list(valor)
    return [valor]


def _texto(valor: Any) -> str:
    """Une listas con «, » y devuelve str vacío si no hay nada."""
    if valor is None:
        return ""
    if isinstance(valor, (list, tuple)):
        return ", ".join(str(v) for v in valor)
    return str(valor)


def _miles_dos(valor: Any) -> str:
    """Importe con miles con espacio y 2 decimales (estilo cp1252)."""
    try:
        return f"{float(valor or 0):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(valor or "")


def _seccion_lista(titulo: str, items: Iterable[Any]) -> List[str]:
    filas = ["<h2>" + _esc(titulo) + "</h2>", "<ul>"]
    for item in items:
        filas.append("<li>" + _esc(item) + "</li>")
    filas.append("</ul>")
    return filas


def _seccion_prioridades(prioridades: Dict[str, Any]) -> List[str]:
    filas = ['<h2>Prioridades del documento</h2>', '<dl class="prio">']
    for clave in prioridades:
        filas.append("<dt>" + _esc(clave) + "</dt>")
        contenido = prioridades[clave]
        if isinstance(contenido, (list, tuple)):
            for parte in contenido:
                filas.append("<dd>" + _esc(parte) + "</dd>")
        else:
            filas.append("<dd>" + _esc(contenido) + "</dd>")
    filas.append("</dl>")
    return filas


def informe_html(informe: Dict[str, Any], titulo: str,
                 nota: str = "") -> str:
    """Convierte un informe de validación en HTML autocontenido.

    ``informe`` es el dict que devuelven ``validar_vivienda``,
    ``validar_proyecto`` (comercial/educacional) y compañía; el
    renderizador recorre claves OPCIONALES, así que sirve para
    cualquiera de los dominios sin acoplarse a ninguno.
    """
    partes: List[str] = []
    partes.append("<!DOCTYPE html>")
    partes.append('<html lang="es">')
    partes.append("<head>")
    partes.append('<meta charset="utf-8">')
    partes.append('<meta name="viewport" content="width=device-width, '
                  'initial-scale=1">')
    partes.append("<title>" + _esc(titulo) + "</title>")
    partes.append("<style>" + _CSS + "</style>")
    partes.append("</head>")
    partes.append("<body><main>")

    partes.append("<h1>" + _esc(titulo) + "</h1>")
    edificacion = _texto(informe.get("edificacion"))
    if edificacion:
        partes.append('<p class="edificacion">'
                      + _esc(edificacion) + "</p>")

    # chips de metadatos
    chips: List[str] = []
    for clave, etiqueta in _META_CHIPS:
        texto = _texto(informe.get(clave))
        if texto:
            chips.append('<span class="chip">' + _esc(etiqueta)
                         + ": <b>" + _esc(texto) + "</b></span>")
    if chips:
        partes.append('<div class="chips">' + "".join(chips) + "</div>")

    # resumen numérico
    resumen = informe.get("resumen") or {}
    if isinstance(resumen, dict) and resumen:
        badges = []
        for clave, etiqueta in _ORDEN_RESUMEN:
            if clave in resumen and resumen[clave]:
                clase = "ok" if clave == "ok" else (
                    "fallo" if clave == "fallos" else (
                        "aviso" if clave == "avisos" else "pendiente"))
                badges.append('<span class="badge ' + clase + '">'
                              + _esc(f"{resumen[clave]} {etiqueta}")
                              + "</span>")
        if badges:
            partes.append('<div class="badges">'
                          + "".join(badges) + "</div>")

    advertencia = _texto(informe.get("advertencia"))
    if advertencia:
        partes.append('<div class="nota">'
                      + _esc(advertencia) + "</div>")

    # coste ligado al check (v3.31.0): instantánea del presupuesto
    # activo; si el informe no trae coste, no se dibuja nada
    coste = informe.get("coste")
    if isinstance(coste, dict) and coste.get("total") is not None:
        moneda = _texto(coste.get("moneda")) or "CUP"
        partes.append("<h2>Coste del proyecto</h2>")
        fuente_coste = _texto(coste.get("fuente"))
        if fuente_coste:
            partes.append('<p class="estado">' + _esc(
                f"{fuente_coste} — "
                f"{int(coste.get('renglones', 0) or 0)} renglón(es)"
            ) + "</p>")
        partes.append("<table><thead><tr><th>Concepto</th><th>Importe "
                      + _esc(moneda) + "</th></tr></thead><tbody>")
        for concepto, importe in (
                ("Costo directo", coste.get("directo")),
                ("Transporte", coste.get("transporte")),
                ("Indirectos", coste.get("indirectos")),
                ("Beneficio", coste.get("beneficio"))):
            partes.append("<tr><td>" + _esc(concepto) + "</td><td>"
                          + _esc(_miles_dos(importe)) + "</td></tr>")
        partes.append('<tr class="ultima"><td><b>TOTAL</b></td>'
                      + "<td><b>" + _esc(_miles_dos(coste.get("total")))
                      + "</b></td></tr>")
        if coste.get("total_por_m2") is not None:
            partes.append(
                "<tr><td>Coste por m2 sobre "
                + _esc(f"{float(coste.get('area_m2') or 0):.1f}")
                + " m2 de locales</td><td>"
                + _esc(_miles_dos(coste.get("total_por_m2")))
                + "</td></tr>")
        partes.append("</tbody></table>")
        nota_coste = _texto(coste.get("nota"))
        if nota_coste:
            partes.append('<p class="estado">' + _esc(nota_coste)
                          + "</p>")

    # comprobaciones del edificio
    hallazgos = _lista_de(informe, "hallazgos")
    if hallazgos:
        partes.append("<h2>Comprobaciones del edificio</h2>")
        partes.append("<table><thead><tr><th>Estado</th><th>Código"
                      "</th><th>Comprobación</th><th>Fuente</th>"
                      "</tr></thead><tbody>")
        for h in hallazgos:
            severidad = str(_campo(h, "severidad") or "info")
            marca = _ETIQUETA_SEVERIDAD.get(severidad, severidad.upper())
            estado = _ETIQUETA_ESTADO.get(
                str(_campo(h, "estado") or "medido"), "")
            mensaje = _texto(_campo(h, "mensaje")) + \
                ('<span class="estado">' + _esc(estado) + "</span>"
                 if estado else "")
            partes.append("<tr><td>"
                          + f'<span class="marca {severidad}">'
                          + _esc(marca) + "</span></td><td class=\"cod\">"
                          + _esc(_campo(h, "codigo") or "")
                          + "</td><td>" + mensaje
                          + "</td><td class=\"fuente\">"
                          + _esc(_campo(h, "fuente")
                                 or "documento") + "</td></tr>")
        partes.append("</tbody></table>")

    # locales revisados (hallazgos dimensionales por local)
    locales = informe.get("locales") or []
    if locales:
        con_fallos = [l for l in locales
                      if any(str(_campo(x, "severidad")) == "fallo"
                             for x in _lista_de(l, "hallazgos"))]
        partes.append("<h2>Locales revisados</h2>")
        partes.append("<p class=\"estado\">"
                      + _esc(f"{len(locales)} locales revisados "
                             f"({len(con_fallos)} con fallos "
                             "dimensionales)") + "</p>")
        partes.append("<table><thead><tr><th>Local</th><th>Estado</th>"
                      "<th>Código</th><th>Comprobación</th></tr>"
                      "</thead><tbody>")
        for l in locales:
            nombre = _texto(_campo(l, "local"))
            detalle = _texto(_campo(l, "nombre"))
            etiqueta = nombre + (" — " + detalle if detalle else "")
            hallazgos_local = _lista_de(l, "hallazgos")
            for indice, x in enumerate(hallazgos_local):
                severidad = str(_campo(x, "severidad") or "info")
                marca = _ETIQUETA_SEVERIDAD.get(
                    severidad, severidad.upper())
                estado = _ETIQUETA_ESTADO.get(
                    str(_campo(x, "estado") or "medido"), "")
                ultima = ' class="ultima"' \
                    if indice == len(hallazgos_local) - 1 else ""
                partes.append("<tr" + ultima + "><td>"
                              + _esc(etiqueta if indice == 0 else "")
                              + "</td><td>"
                              + f'<span class="marca {severidad}">'
                              + _esc(marca) + "</span></td>"
                              + '<td class="cod">'
                              + _esc(_campo(x, "codigo") or "")
                              + "</td><td>"
                              + _esc(_campo(x, "mensaje") or "")
                              + ('<span class="estado">'
                                 + _esc(estado) + "</span>"
                                 if estado else "")
                              + "</td></tr>")
        partes.append("</tbody></table>")

    # secciones genéricas de cada dominio (solo si vienen)
    for clave, titulo_seccion in _SECCIONES_LISTA:
        if clave == "prioridades":
            prioridades = informe.get("prioridades")
            if isinstance(prioridades, dict) and prioridades:
                partes.extend(_seccion_prioridades(prioridades))
            continue
        contenido = informe.get(clave)
        if isinstance(contenido, (list, tuple)) and contenido:
            partes.extend(_seccion_lista(titulo_seccion, contenido))

    # tablas genéricas (pares acústicos, equipos, plan domótico...)
    for tabla in informe.get("tablas") or []:
        if not isinstance(tabla, dict) or not tabla.get("filas"):
            continue
        titulo_tabla = _texto(tabla.get("titulo")) or "Tabla"
        partes.append("<h2>" + _esc(titulo_tabla) + "</h2>")
        cabeceras = [_texto(c) for c in (tabla.get("cabeceras") or [])]
        partes.append("<table><thead><tr>")
        for celda in cabeceras:
            partes.append("<th>" + _esc(celda) + "</th>")
        partes.append("</tr></thead><tbody>")
        for fila in tabla.get("filas", []):
            celdas = list(fila) if isinstance(fila, (list, tuple)) \
                else [fila]
            partes.append("<tr>")
            for celda in celdas:
                partes.append("<td>" + _esc(_texto(celda)) + "</td>")
            partes.append("</tr>")
        partes.append("</tbody></table>")

    # pie: fecha, versión y la nota honesta
    partes.append("<footer>")
    partes.append(_esc(f"Generado por ARQ_GEN {APP_VERSION} el "
                       f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"
                       " — informe de sólo lectura."))
    partes.append("<br>" + _esc(nota or "El informe no sustituye los "
                                "cálculos especializados que el "
                                "documento exige (HVAC, incendios, "
                                "acústica, estructuras)."))
    partes.append("</footer>")
    partes.append("</main></body></html>")
    return "\n".join(partes)


def guardar_informe_html(ruta: str, informe: Dict[str, Any],
                         titulo: str, nota: str = "") -> str:
    """Escribe el informe HTML y devuelve la ruta absoluta escrita.

    Errores: ``ARQ-EXP-060`` si la ruta no se puede escribir (mismo
    criterio amable que el resto de los exportadores).
    """
    destino = os.path.abspath(ruta)
    contenido = informe_html(informe, titulo, nota=nota)
    try:
        carpeta = os.path.dirname(destino)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(destino, "w", encoding="utf-8") as manejador:
            manejador.write(contenido)
    except OSError as exc:
        raise ExportError(
            message=f"No se pudo escribir el informe HTML: {exc}",
            code="ARQ-EXP-060", context={"path": destino}) from exc
    return destino


__all__ = ["informe_html", "guardar_informe_html"]

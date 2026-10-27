# -*- coding: utf-8 -*-
"""v3.27.0 — INFORME DE VALIDACIÓN EN HTML AUTOCONTENIDO.

El mismo informe que la GUI muestra en los cuadros «Validar vivienda /
comercial / educacional» ahora se exporta como UN SOLO archivo .html
(``exporters/informe_html.py``): CSS embebido, cero URLs externas,
cero dependencias nuevas, con la honradez visual intacta — «(pendiente)»
y «(REQUIERE_CALCULO_ESPECIALIZADO)» se imprimen, no se esconden.
"""

from __future__ import annotations

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.base import ARQGenTestCase  # noqa: E402

from exporters.informe_html import (guardar_informe_html,  # noqa: E402
                                    informe_html)
from core.errors import ExportError  # noqa: E402


def _informe_humo() -> dict:
    """Informe de juguete con TODAS las secciones que renderiza."""
    return {
        "edificacion": "Escuela <Prueba> & Hijos",
        "uso": "Escuela primaria",
        "familias": ["ESCUELA_PRIMARIA"],
        "tamano": "Media (180-420 alumnos)",
        "tipologia": "TIPO_01",
        "sistema": "Muros de bloque",
        "estilo": "Contemporáneo",
        "clima": "Cálido húmedo",
        "resumen": {"ok": 3, "fallos": 1, "avisos": 2,
                    "pendientes": 4, "info": 1},
        "hallazgos": [
            {"codigo": "EM01", "severidad": "ok", "mensaje": "programa"
             " §106-109 completo", "estado": "medido",
             "fuente": "programa mínimo del documento"},
            {"codigo": "EM07", "severidad": "fallo", "mensaje":
             "escalera <1.20 m", "estado": "medido",
             "fuente": "cuadro ED-ESC"},
            {"codigo": "EM10", "severidad": "aviso", "mensaje":
             "seguridad infantil sin evaluar", "estado": "pendiente",
             "fuente": "§89"},
            {"codigo": "RC01", "severidad": "info", "mensaje":
             "climatización §78", "estado": "requiere calculo",
             "fuente": "§78"},
        ],
        "locales": [
            {"local": "Aula 1", "nombre": "CLASSROOM", "hallazgos": [
                {"codigo": "E01", "severidad": "fallo", "mensaje":
                 "16.00 m2 < mínima 40.00 m2", "estado": "medido",
                 "fuente": "cuadro §5"},
                {"codigo": "E02", "severidad": "ok", "mensaje":
                 "ancho correcto", "estado": "medido", "fuente": "§5"},
            ]},
        ],
        "reglas": ["REGLA_01: NUM_AULAS = CEIL(ALUMNOS/25)",
                   "REGLA_11: SI ALUMNOS>300 ..."],
        "prioridades": {"P01": ["Seguridad infantil §89"],
                        "P02": "Flujos §102"},
        "conflictos": ["El gimnasio ruido contra la biblioteca"],
        "normativa": ["OMS/UNICEF §124"],
        "documentacion": ["Planos de ubicación"],
        "advertencia": "Sin terreno exterior medido",
    }


class TestInformeHTML(unittest.TestCase):
    """El HTML es autocontenido, honrado y seguro."""

    def setUp(self) -> None:
        self.html = informe_html(_informe_humo(), "Informe <de> prueba")

    def test_es_html5_autocontenido(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))
        self.assertIn('<meta charset="utf-8">', self.html)
        self.assertIn("<style>", self.html)
        # cero recursos externos: el archivo vive solo
        self.assertNotIn('href="http', self.html)
        self.assertNotIn('src="http', self.html)
        self.assertNotIn('href="//', self.html)
        self.assertNotIn("@import", self.html)

    def test_titulo_y_edificacion_escapados(self):
        self.assertIn("<title>Informe &lt;de&gt; prueba</title>",
                      self.html)
        self.assertIn("Escuela &lt;Prueba&gt; &amp; Hijos", self.html)

    def test_chips_de_metadatos(self):
        for texto in ("uso: <b>Escuela primaria</b>",
                      "familias: <b>ESCUELA_PRIMARIA</b>",
                      "tamaño: <b>Media (180-420 alumnos)</b>",
                      "clima: <b>Cálido húmedo</b>"):
            self.assertIn(texto, self.html)

    def test_resumen_con_badges(self):
        self.assertIn("3 cumplen", self.html)
        self.assertIn("1 fallos", self.html)
        self.assertIn("2 avisos", self.html)
        self.assertIn("4 pendientes o de cálculo", self.html)
        self.assertIn('class="badge fallo"', self.html)

    def test_hallazgos_con_estados_honestos(self):
        self.assertIn("EM01", self.html)
        # el estado pendiente y el requiere-cálculo se IMPRIMEN
        self.assertIn("(pendiente)", self.html)
        self.assertIn("(REQUIERE_CALCULO_ESPECIALIZADO)", self.html)
        self.assertIn('class="marca fallo"', self.html)
        self.assertIn("FALLA", self.html)

    def test_locales_con_fallos(self):
        self.assertIn("Locales revisados", self.html)
        self.assertIn("1 locales revisados (1 con fallos"
                      " dimensionales)", self.html)
        self.assertIn("Aula 1", self.html)
        self.assertIn("16.00 m2 &lt; mínima 40.00 m2", self.html)

    def test_secciones_genericas(self):
        for texto in ("Reglas de validación del documento",
                      "REGLA_01: NUM_AULAS = CEIL(ALUMNOS/25)",
                      "Prioridades del documento", "P01",
                      "Seguridad infantil §89",
                      "Conflictos del documento",
                      "Normativa y referencias", "OMS/UNICEF §124",
                      "Documentación a presentar",
                      "Sin terreno exterior medido"):
            self.assertIn(texto, self.html)

    def test_pie_con_version_y_honradez(self):
        from core import APP_VERSION
        self.assertIn("ARQ_GEN " + APP_VERSION, self.html)
        self.assertIn("no sustituye los cálculos especializados",
                      self.html)
        self.assertIn("informe de sólo lectura", self.html)

    def test_nota_personalizada_en_el_pie(self):
        html_nota = informe_html(_informe_humo(),
                                 "Informe", nota="Nota final del estudio")
        self.assertIn("Nota final del estudio", html_nota)

    def test_informe_minimo_no_explota(self):
        vacio = informe_html({}, "Vacío")
        self.assertTrue(vacio.startswith("<!DOCTYPE html>"))
        # sin hallazgos no hay sección de comprobaciones, pero el pie sí
        self.assertNotIn("Comprobaciones del edificio", vacio)
        self.assertIn("informe de sólo lectura", vacio)


class TestGuardarInformeHTML(ARQGenTestCase):
    """La escritura al disco con errores amables ARQ-EXP-060."""

    def test_guarda_y_devuelve_ruta_absoluta(self):
        destino = os.path.join(self.tmp, "informes",
                               "vivienda.html")
        ruta = guardar_informe_html(destino, _informe_humo(),
                                    "Validación de vivienda")
        self.assertEqual(os.path.abspath(destino), ruta)
        self.assertTrue(os.path.isfile(ruta))
        with open(ruta, "r", encoding="utf-8") as fh:
            contenido = fh.read()
        self.assertGreater(len(contenido), 1000)
        self.assertIn("Validación de vivienda", contenido)
        self.assertIn("EM07", contenido)

    def test_error_amable_si_la_ruta_no_se_puede_escribir(self):
        obstaculo = os.path.join(self.tmp, "bloqueo")
        with open(obstaculo, "w", encoding="utf-8") as fh:
            fh.write("no soy una carpeta")
        destino = os.path.join(obstaculo, "informe.html")
        with self.assertRaises(ExportError) as ctx:
            guardar_informe_html(destino, _informe_humo(), "X")
        self.assertEqual(ctx.exception.code, "ARQ-EXP-060")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

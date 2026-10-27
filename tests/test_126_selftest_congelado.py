"""SELFTEST dentro del ejecutable compilado (fix v3.8.1).

La etapa 3 del pipeline (03_COMPILAR.bat) ejecuta
``dist\\ARQ_GEN\\ARQ_GEN.exe selftest``: en el bundle de PyInstaller
los módulos viajan como BYTECODE (no hay .py junto al binario), así
que los checks 49 y 50 NO pueden abrir ``ui/app_window.py`` para
verificar texto — fallaban con FileNotFoundError y tumbaban el
post-build completo.

Desde v3.8.1 esa verificación de texto se omite al vuelo congelado
(mismo criterio honesto que los scripts .bat del check 27) y la línea
OK lo declara («verificación de fuente omitida: ejecutable»). El resto
de las aserciones de esos checks (49 a 96) sí corren en el exe.

Estas pruebas SIMULAN el ejecutable (sys.frozen=True + sys._MEIPASS
apuntando a la raíz del proyecto, donde están resources/ y todo lo
demás, tal como los coloca --add-data) y exigen que el selftest
COMPLETO llegue a RESULTADO: CORRECTO sin ningún FALLO.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from tests.base import ARQGenTestCase, PROJECT_ROOT


def _run_congelado():
    """run_selftest() completo fingiendo el bundle PyInstaller."""
    from app import selftest as st
    with mock.patch.object(sys, "frozen", True, create=True), \
            mock.patch.object(sys, "_MEIPASS", PROJECT_ROOT, create=True):
        return st.run_selftest(console=False)


class TestSelftestCongelado(ARQGenTestCase):
    """El selftest del ejecutable llega a CORRECTO sin fuente .py."""

    def test_selftest_congelado_sin_fallos(self):
        ok, checks = _run_congelado()
        self.assertTrue(ok, checks)
        fallos = [c for c in checks if c.startswith("FALLO")]
        self.assertEqual(fallos, [])
        # los .bat se omiten al vuelo congelado (check 27, criterio
        # preexistente que ahora comparten los checks 49, 50 y 51)
        self.assertIn("scripts .bat: omitido (ejecutable compilado)",
                      checks)

    def test_checks_49_al_60_declaran_la_omision(self):
        ok, checks = _run_congelado()
        self.assertTrue(ok)
        fuente = [c for c in checks
                  if "verificación de fuente omitida" in c]
        self.assertEqual(len(fuente), 32, checks)
        self.assertTrue(any(c.startswith("ventanas y paneles ajustables")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("layout restaurable")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("interfaz compacta")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("regeneración de la edificación")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("vista 3D axonométrica")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("presupuesto vivo sobre las "
                                         "variantes")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("sombras solares, terreno 3D "
                                         "e IFC de entrada")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("herramientas de edición CAD")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("concepción de espacios")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("teclado y puntero AutoCAD")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("cota de cubierta + vista en "
                                         "perspectiva")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("ascensores y fachada")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("escaleras, aberturas, iluminación "
                                         "y alarmas")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("especialidades de salud y "
                                         "asistente de local")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("pasillos hospitalarios, "
                                         "equipos en el presupuesto")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("especificaciones técnicas "
                                         "hospitalarias")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("catálogo maestro de viviendas")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("estudios de vivienda")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("documento comercial CC/OF")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("documento educacional")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("informe HTML autocontenido")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("presets de configuración")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("comparador de variantes")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("servicios de vivienda")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("DXF R12 y coste ligado "
                                         "al check")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("multiplicadores de niveles")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("dibujo CAD y asistente de "
                                         "servicios")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("desde dibujo")
                            for c in fuente), checks)
        self.assertTrue(any(c.startswith("servicios médicos")
                            for c in fuente), checks)

    def test_mismo_numero_de_checks_que_en_desarrollo(self):
        ok, checks = _run_congelado()
        self.assertTrue(ok)
        # las 86 líneas de verificación salen íntegras también en el exe
        self.assertEqual(len(checks), 96)

    def test_salida_consola_sobrevive_cp1252(self):
        """v3.13.1: el selftest impreso aguanta una consola cp1252.

        La consola de Windows (cp1252) no codifica «→»: el check 55
        llevaba una en «exportar→importar» y el selftest del ejecutable
        moría al imprimir SU línea, después de 54 OK — el pipeline
        reportaba «ERROR: el selftest DEL EJECUTABLE fallo». Aquí se
        reproduce el escenario exacto: stdout cp1252 ESTRICTO y
        consola=True; sin el fix esto lanza UnicodeEncodeError.
        """
        import contextlib
        import io
        from app import selftest as st
        falsa = io.TextIOWrapper(io.BytesIO(), encoding="cp1252",
                                 errors="strict")
        with contextlib.redirect_stdout(falsa):
            ok, checks = st.run_selftest(console=True)
        falsa.flush()
        texto = falsa.buffer.getvalue().decode("cp1252")
        self.assertTrue(ok, checks)
        self.assertIn("RESULTADO: CORRECTO", texto)
        self.assertIn("sombras solares, terreno 3D e IFC de entrada",
                      texto)
        # el mensaje canónico del check 55 ya no lleva la flecha
        self.assertTrue(any("exportar->importar" in c for c in checks),
                        checks)
        # y CADA línea impresa era codificable en cp1252 sin sustituciones
        for c in checks:
            c.encode("cp1252")


class TestSelftestDesdeFuente(ARQGenTestCase):
    """En desarrollo la verificación de texto SIGUE siendo exigente."""

    def test_marcadores_presentes_en_app_window(self):
        # espejo de las aserciones que el selftest hace al fuente en
        # modo desarrollo: si desaparecieran, el check 49/50 local
        # volvería a ser mentira aunque esta batería pasara
        with open(os.path.join(PROJECT_ROOT, "ui", "app_window.py"),
                  "r", encoding="utf-8") as fh:
            src = fh.read()
        self.assertGreaterEqual(src.count("self._prepare_dialog(dialog,"),
                                12)
        self.assertIn("_apply_saved_sashes", src)
        self.assertIn("def reset_layout", src)
        self.assertIn("_on_sash_double_click", src)
        self.assertIn("Restaurar disposición por defecto", src)

    def test_selftest_desde_fuente_sigue_en_correcto(self):
        from app import selftest as st
        ok, checks = st.run_selftest(console=False)
        self.assertTrue(ok, checks)
        self.assertNotIn("scripts .bat: omitido (ejecutable compilado)",
                         checks)
        sin_omision = [c for c in checks
                       if "verificación de fuente omitida" in c]
        self.assertEqual(sin_omision, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

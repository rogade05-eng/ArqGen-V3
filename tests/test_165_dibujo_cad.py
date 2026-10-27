"""HERRAMIENTAS DE DIBUJO v3.33.0 (ui/dibujo_cad.py).

Muros, espacios, zonas, puertas y ventanas a dos clics como
ArchiCAD/AutoCAD: entidades REALES por los caminos oficiales
(ArchitectureService), reglas del DNA avisando (puerta mínima del
uso, hueco de ventana 1/6 - 1/25, área mínima del espacio, zonas que
asignan locales), imantación headless (vértices, rejilla, orto) y
resúmenes cp1252.
"""

from __future__ import annotations

import math
import os
import unittest
from types import SimpleNamespace

from core import APP_VERSION
from core.errors import DomainError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase
from ui import dibujo_cad as dib
from ui.cad_tools import texto_resumen as texto_cad


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - headless
        return False


DISPLAY = _display_available()


# ---------------------------------------------------------------------------
# geometría plana
# ---------------------------------------------------------------------------

class TestGeometria(unittest.TestCase):
    """Los helpers de dibujo: rectángulos, áreas y proyecciones."""

    def test_rectangulo_antihorario(self):
        esquinas = dib._rectangulo((4, 5), (1, 2))
        self.assertEqual(esquinas, [(1, 2), (4, 2), (4, 5), (1, 5)])
        # las aristas giran en sentido antihorario
        area = dib._area(esquinas)
        self.assertEqual(area, 9.0)

    def test_area_poligono_y_centroide(self):
        triangulo = [(0, 0), (6, 0), (0, 3)]
        self.assertAlmostEqual(dib._area(triangulo), 9.0, places=6)
        centro = dib._centroide(triangulo)
        self.assertAlmostEqual(centro[0], 2.0, places=6)
        self.assertAlmostEqual(centro[1], 1.0, places=6)

    def test_punto_en_poligono(self):
        cuadrado = [(0, 0), (10, 0), (10, 10), (0, 10)]
        self.assertTrue(dib._punto_en_poligono((5, 5), cuadrado))
        self.assertFalse(dib._punto_en_poligono((15, 5), cuadrado))
        # frontera inclusiva (la esquina cuenta como dentro)
        self.assertTrue(dib._punto_en_poligono((10, 10), cuadrado))

    def test_proyeccion_sujeta_al_segmento(self):
        self.assertAlmostEqual(dib._proyeccion((2, 1), (0, 0), (10, 0)),
                               2.0, places=6)
        # se sujeta a 0..len: lo que cae fuera, al extremo
        self.assertAlmostEqual(dib._proyeccion((-3, 0), (0, 0), (10, 0)),
                               0.0, places=6)
        self.assertAlmostEqual(dib._proyeccion((99, 0), (0, 0), (10, 0)),
                               10.0, places=6)


# ---------------------------------------------------------------------------
# imantación headless
# ---------------------------------------------------------------------------

class TestSnap(ARQGenTestCase):
    """snap_punto: vértices primero, rejilla después, orto al final."""

    def setUp(self) -> None:
        super().setUp()
        self.ctx = self.application.create_project(
            self.project_path("snap.arqgen"), name="Snap")
        self.arch = ArchitectureService(self.ctx)
        self.arch.create_level("PB", 0.0, 3.0)

    def tearDown(self) -> None:
        self.ctx.close()
        super().tearDown()

    def test_snap_a_vertice_de_muro(self):
        self.arch.create_wall("PB", (0, 0), (8, 0))
        punto, fuente = dib.snap_punto(self.ctx, "PB", (8.12, 0.09),
                                       rejilla=0.10, tol=0.35)
        self.assertEqual(fuente, "vertice")
        self.assertEqual(punto, (8.0, 0.0))

    def test_snap_a_vertice_de_local(self):
        self.arch.create_space("PB", "Sala", "ROOM",
                               [(0, 0), (5, 0), (5, 4), (0, 4)])
        punto, fuente = dib.snap_punto(self.ctx, "PB", (5.2, 3.95),
                                       rejilla=0.10, tol=0.35)
        self.assertEqual(fuente, "vertice")
        self.assertEqual(punto, (5.0, 4.0))

    def test_snap_a_rejilla_sin_vertices_cerca(self):
        punto, fuente = dib.snap_punto(self.ctx, "PB", (3.56, 2.44),
                                       rejilla=0.10, tol=0.35)
        self.assertEqual(fuente, "rejilla")
        self.assertEqual(punto, (3.6, 2.4))

    def test_orto_desde_base(self):
        punto, fuente = dib.snap_punto(self.ctx, "PB", (7.3, 5.2),
                                       rejilla=0.0, tol=0.0,
                                       base=(2.0, 3.0), orto=True)
        self.assertEqual(fuente, "rejilla")
        # domina dx (5.3 > 2.2): se proyecta sobre la horizontal de base
        self.assertEqual(punto, (7.3, 3.0))

    def test_snap_sin_niveles_no_explota(self):
        punto, fuente = dib.snap_punto(self.ctx, "NO_EXISTE",
                                       (1.23, 1.23), rejilla=0.10,
                                       tol=0.35)
        self.assertEqual(fuente, "rejilla")
        self.assertEqual(punto, (1.2, 1.2))


# ---------------------------------------------------------------------------
# dibujar: entidades reales con reglas
# ---------------------------------------------------------------------------

class TestDibujar(ARQGenTestCase):
    """Las cinco herramientas sobre un proyecto temporal."""

    def setUp(self) -> None:
        super().setUp()
        self.ctx = self.application.create_project(
            self.project_path("dibujo.arqgen"), name="Dibujo")
        self.arch = ArchitectureService(self.ctx)
        self.arch.create_level("PB", 0.0, 3.0)

    def tearDown(self) -> None:
        self.ctx.close()
        super().tearDown()

    # -- muro ------------------------------------------------------------

    def test_muro_nace_real_con_espesor_y_altura_del_nivel(self):
        resumen = dib.dibujar_muro(self.ctx, "PB", (0, 0), (10, 0),
                                   espesor=0.20)
        muro = self.ctx.architecture.get_by_code(
            "WALL", resumen["creados"][0])
        self.assertIsNotNone(muro)
        self.assertEqual(muro.start, (0.0, 0.0))
        self.assertEqual(muro.end, (10.0, 0.0))
        self.assertEqual(muro.thickness_m, 0.20)
        self.assertEqual(muro.height_m, 3.0)   # la del nivel
        self.assertEqual(resumen["muros"], [muro.code])
        self.assertEqual(resumen["avisos"], [])

    def test_muro_con_altura_propia_y_aviso_si_pasa_del_nivel(self):
        resumen = dib.dibujar_muro(self.ctx, "PB", (0, 0), (5, 0),
                                   espesor=0.15, altura=4.5)
        self.assertEqual(resumen["datos"]["altura_m"], 4.5)
        self.assertTrue(any("mayor que la del nivel" in a
                            for a in resumen["avisos"]))

    def test_muro_espesor_fino_avisa(self):
        resumen = dib.dibujar_muro(self.ctx, "PB", (0, 0), (3, 0),
                                   espesor=0.07)
        self.assertTrue(any("espesor fino" in a for a in resumen["avisos"]))

    def test_muro_espesor_no_positivo_error_amable(self):
        with self.assertRaises(DomainError) as ctxm:
            dib.dibujar_muro(self.ctx, "PB", (0, 0), (3, 0), espesor=0)
        self.assertEqual(ctxm.exception.code, "ARQ-DIB-002")

    # -- espacio ----------------------------------------------------------

    def test_espacio_nace_real_con_uso_y_area(self):
        resumen = dib.dibujar_espacio(self.ctx, "PB", (0, 0), (4, 3),
                                      nombre="Sala RX", uso="IMAGING_ROOM")
        espacio = self.ctx.architecture.get_by_code(
            "SPACE", resumen["creados"][0])
        self.assertIsNotNone(espacio)
        self.assertEqual(espacio.name, "Sala RX")
        self.assertEqual(espacio.space_type, "IMAGING_ROOM")
        self.assertAlmostEqual(espacio.area_m2(), 12.0, places=6)
        self.assertEqual(resumen["datos"]["area_m2"], 12.0)

    def test_espacio_nombre_automatico_y_duplicados(self):
        r1 = dib.dibujar_espacio(self.ctx, "PB", (0, 0), (4, 3))
        r2 = dib.dibujar_espacio(self.ctx, "PB", (6, 0), (9, 3))
        r3 = dib.dibujar_espacio(self.ctx, "PB", (10, 0), (13, 3))
        self.assertEqual(r1["datos"]["nombre"], "Local 1")
        self.assertEqual(r2["datos"]["nombre"], "Local 2")
        self.assertEqual(r3["datos"]["nombre"], "Local 3")
        r4 = dib.dibujar_espacio(self.ctx, "PB", (14, 0), (17, 3),
                                 nombre="Local 1")
        self.assertEqual(r4["datos"]["nombre"], "Local 1 2")

    def test_espacio_area_menor_que_el_minimo_del_uso_avisa(self):
        # BATHROOM pide 2.5 m2 de mínimo en el DNA
        resumen = dib.dibujar_espacio(self.ctx, "PB", (0, 0), (1, 1),
                                      uso="BATHROOM")
        self.assertTrue(any("por debajo del minimo del uso" in a
                            for a in resumen["avisos"]))

    def test_espacio_sin_area_error(self):
        with self.assertRaises(DomainError) as ctxm:
            dib.dibujar_espacio(self.ctx, "PB", (2, 2), (2, 2))
        self.assertEqual(ctxm.exception.code, "ARQ-DIB-004")

    # -- zona --------------------------------------------------------------

    def test_zona_crea_y_asigna_los_locales_dentro(self):
        self.arch.create_space("PB", "A", "ROOM",
                               [(0, 0), (3, 0), (3, 3), (0, 3)])
        self.arch.create_space("PB", "B", "ROOM",
                               [(4, 0), (7, 0), (7, 3), (4, 3)])
        resumen = dib.dibujar_zona(self.ctx, "Zona Tecnica",
                                   (0, 0), (7, 3), kind="TECHNICAL",
                                   nivel_ref="PB")
        zona = self.ctx.architecture.get_by_code(
            "ZONE", resumen["creados"][0])
        self.assertIsNotNone(zona)
        self.assertEqual(zona.kind, "TECHNICAL")
        self.assertEqual(len(resumen["datos"]["asignados"]), 2)
        for codigo in resumen["datos"]["asignados"]:
            espacio = self.ctx.architecture.get_by_code("SPACE", codigo)
            self.assertEqual(espacio.zone_id, zona.id)

    def test_zona_sin_locales_avisa_y_kind_invalido_cae_al_defecto(self):
        resumen = dib.dibujar_zona(self.ctx, "Zona vacia",
                                   (100, 100), (105, 104),
                                   kind="NO_EXISTE")
        self.assertTrue(any("ningun local" in a for a in resumen["avisos"]))
        zona = self.ctx.architecture.get_by_code(
            "ZONE", resumen["creados"][0])
        self.assertEqual(zona.kind, dib.KIND_ZONA_DEF)

    # -- vanos --------------------------------------------------------------

    def test_puerta_centrada_en_el_clic_sobre_el_muro(self):
        muro = self.arch.create_wall("PB", (0, 0), (10, 0))
        resumen = dib.dibujar_vano(self.ctx, "DOOR", muro.code,
                                   (2.0, 0.0), ancho=0.90, alto=2.10)
        puerta = self.ctx.architecture.get_by_code(
            "DOOR", resumen["creados"][0])
        self.assertIsNotNone(puerta)
        self.assertAlmostEqual(puerta.offset_m, 1.55, places=6)
        self.assertEqual(puerta.width_m, 0.90)
        self.assertEqual(puerta.height_m, 2.10)

    def test_puerta_estrecha_avisa_con_el_minimo_del_uso(self):
        # el muro limita una sala IMAGING_ROOM cuyo DNA pide 1.20 m
        self.arch.create_space("PB", "RX", "IMAGING_ROOM",
                               [(0, 0), (5, 0), (5, 4), (0, 4)])
        muro = self.arch.create_wall("PB", (0, 0), (10, 0))
        resumen = dib.dibujar_vano(self.ctx, "DOOR", muro.code,
                                   (1.0, 0.0), ancho=0.60)
        self.assertEqual(resumen["datos"]["uso"], "IMAGING_ROOM")
        self.assertTrue(any("por debajo del minimo del uso" in a
                            for a in resumen["avisos"]))

    def test_ventana_bajo_el_hueco_que_pide_el_uso_avisa(self):
        # 12 m2 de dormitorio piden 12/6 = 2.00 m2 de hueco
        self.arch.create_space("PB", "Hab", "BEDROOM",
                               [(0, 0), (4, 0), (4, 3), (0, 3)])
        muro = self.arch.create_wall("PB", (0, 0), (4, 0))
        resumen = dib.dibujar_vano(self.ctx, "WINDOW", muro.code,
                                   (2.0, 0.0), ancho=1.20, alto=1.20)
        self.assertTrue(any("pide" in a and "hueco" in a
                            for a in resumen["avisos"]))
        # y con una ventana suficiente no avisa
        resumen2 = dib.dibujar_vano(self.ctx, "WINDOW", muro.code,
                                    (2.0, 0.0), ancho=1.60, alto=1.30)
        self.assertFalse(any("pide" in a for a in resumen2["avisos"]))

    def test_vano_que_no_cabe_error_amable(self):
        muro = self.arch.create_wall("PB", (0, 0), (4, 0))
        with self.assertRaises(DomainError) as ctxm:
            dib.dibujar_vano(self.ctx, "DOOR", muro.code, (2, 0),
                             ancho=9.0)
        self.assertEqual(ctxm.exception.code, "ARQ-DIB-001")

    def test_vano_en_muro_sin_locales_queda_libre_de_reglas(self):
        muro = self.arch.create_wall("PB", (50, 0), (60, 0))
        resumen = dib.dibujar_vano(self.ctx, "DOOR", muro.code,
                                   (55, 0), ancho=0.70)
        self.assertEqual(resumen["avisos"], [])
        self.assertIn("nota", resumen["datos"])

    def test_vano_lejos_del_muro_se_sujeta_al_extremo(self):
        muro = self.arch.create_wall("PB", (0, 0), (4, 0))
        resumen = dib.dibujar_vano(self.ctx, "DOOR", muro.code,
                                   (99.0, 5.0), ancho=1.0)
        puerta = self.ctx.architecture.get_by_code(
            "DOOR", resumen["creados"][0])
        self.assertAlmostEqual(puerta.offset_m, 3.0, places=6)

    # -- cierre ---------------------------------------------------------

    def test_resumen_compatible_con_cad_y_cp1252(self):
        resumen = dib.dibujar_muro(self.ctx, "PB", (0, 0), (5, 0))
        texto = texto_cad(resumen)
        self.assertIn("dibujar muro", texto)
        self.assertIn(resumen["creados"][0], texto)
        texto.encode("cp1252")
        texto_dib = dib.texto_resumen_dibujo(resumen)
        texto_dib.encode("cp1252")
        self.assertIn(resumen["creados"][0], texto_dib)

    def test_dibujado_sobrevive_commit(self):
        dib.dibujar_muro(self.ctx, "PB", (0, 0), (5, 0))
        dib.dibujar_espacio(self.ctx, "PB", (0, 0), (3, 3))
        self.ctx.commit()
        self.assertEqual(len(self.ctx.architecture.list(
            "WALL", self.ctx.project.id)), 1)
        self.assertEqual(len(self.ctx.architecture.list(
            "SPACE", self.ctx.project.id)), 1)


# ---------------------------------------------------------------------------
# ganchos de la ventana (paleta de dibujo)
# ---------------------------------------------------------------------------

@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestGanchosVentana(ARQGenTestCase):
    """La paleta con la sección DIBUJAR y la máquina de estados."""

    def setUp(self):
        super().setUp()
        old = os.environ.get("ARQGEN_PREFS")
        self._prefs = os.path.join(self.tmp, "prefs.json")
        os.environ["ARQGEN_PREFS"] = self._prefs
        from ui.app_window import ARQGenWindow
        self.ctx = self.demo_context()
        self.window = ARQGenWindow(self.ctx, self.application)
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.ctx.close()
        os.environ["ARQGEN_PREFS"] = self._prefs if self._prefs else ""
        os.environ.pop("ARQGEN_PREFS", None)
        super().tearDown()

    def test_paleta_con_seccion_dibujar_y_configuracion(self):
        self.window.open_dibujo_palette()
        self.window.update()
        paleta = self.window._cad_palette
        self.assertTrue(paleta.winfo_exists())
        # la configuración de dimensiones quedó sobre la ventana
        self.assertEqual(self.window._dib_float(self.window._dib_espesor,
                                                0.0), 0.20)
        self.assertEqual(self.window._dib_uso.get(), "ROOM")
        self.assertIn("ROOM", self.window._dib_uso.get())

    def test_dib_float_tolera_coma_y_basura(self):
        import tkinter as tk
        var = tk.StringVar(value="0,35")
        self.assertEqual(self.window._dib_float(var, 1.0), 0.35)
        var.set("abc")
        self.assertEqual(self.window._dib_float(var, 1.0), 1.0)
        var.set("")
        self.assertEqual(self.window._dib_float(var, 1.0), 1.0)

    def test_nivel_de_dibujo_es_un_nivel_real(self):
        niveles = [lv.name for lv in
                   self.ctx.architecture.list("LEVEL",
                                              self.ctx.project.id)]
        self.assertIn(self.window._nivel_de_dibujo(), niveles)

    def test_clic_dibujo_muro_crea_el_muro_y_cierra_el_estado(self):
        antes = len(self.ctx.architecture.list("WALL",
                                               self.ctx.project.id))
        self.window._cad_set_tool("dib_muro")
        self.assertEqual(self.window._cad_estado()["tool"], "dib_muro")
        self.window._cad_pasos = [(0.0, 0.0), (6.0, 0.0)]
        self.window._cad_ejecuta_dibujo("dib_muro")
        despues = len(self.ctx.architecture.list("WALL",
                                                 self.ctx.project.id))
        self.assertEqual(despues, antes + 1)
        # la máquina queda limpia y la herramienta activa para repetir
        estado = self.window._cad_estado()
        self.assertEqual(estado["pasos"], [])
        self.assertEqual(estado["tool"], "dib_muro")

    def test_clic_dibujo_puerta_exige_un_muro_debajo(self):
        self.window._cad_set_tool("dib_puerta")
        fila_falsa = SimpleNamespace(type="SPACE", uid="XX")
        self.window._cad_click_dibujo(
            "dib_puerta", (1.0, 0.0), fila_falsa,
            dib.PROMPTS_DIBUJO["dib_puerta"])
        self.assertEqual(self.window._cad_pasos, [])
        self.assertNotIn("muro", self.window._cad_datos)

    def test_clic_dibujo_puerta_sobre_muro_crea_vano(self):
        self.arch = ArchitectureService(self.ctx)
        muro = self.arch.create_wall(
            self.window._nivel_de_dibujo(), (0, 0), (10, 0))
        fila = SimpleNamespace(type="WALL", uid=muro.id)
        self.window._cad_set_tool("dib_puerta")
        self.window._cad_click_dibujo(
            "dib_puerta", (3.0, 0.0), fila,
            dib.PROMPTS_DIBUJO["dib_puerta"])
        puertas = self.ctx.architecture.list("DOOR",
                                             self.ctx.project.id)
        self.assertTrue(any(p.wall_id == muro.id for p in puertas))

    def test_version_coherente_con_v3410(self):
        self.assertEqual(APP_VERSION, "3.47.0")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

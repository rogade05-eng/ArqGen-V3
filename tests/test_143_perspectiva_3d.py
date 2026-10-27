"""VISTA 3D EN PERSPECTIVA (v3.17.0).

* Proyección con punto de fuga sobre la MISMA cámara: giro de azimut,
  inclinación de elevación y división por la profundidad respecto al
  centro del modelo; en el plano del centro la escala es exactamente 1
  para que el encuadre automático de siempre siga funcionando.
* prepara_perspectiva fija CENTRO y DISTANCIA con el FOV de fábrica;
  el plano cercano (12 % de la distancia) evita divisiones locas.
* Tecla P conmuta axonométrica/perspectiva; Home re-encuadra.
* El PNG determinista sale igual de válido en perspectiva, y el
  diálogo 3D lleva la casilla y la tecla sincronizadas.
"""

from __future__ import annotations

import math
import os
import unittest

from tests.base import ARQGenTestCase

from ui import view3d as v3
from ui.view3d import Camara3D, Cara3D


def _display_ok() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - headless
        return False


DISPLAY = _display_ok()


class _EscenaBase(ARQGenTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.caja = Cara3D(
            puntos=[(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 6.0, 0.0),
                    (0.0, 6.0, 0.0)], color="#aeb9c4", kind="muro")


class TestProyeccionPerspectiva(_EscenaBase):

    def test_ortografica_no_cambia(self):
        cam = Camara3D(azimuth_deg=0.0, elevacion_deg=0.0)
        self.assertFalse(cam.perspectiva)
        # con distancia residual puesta a mano, sin perspectiva ignora
        cam.distancia_m = 10.0
        sx, sy = v3.proyecta((3.0, -1.0, 2.0), cam)
        self.assertAlmostEqual(sx, 3.0, places=9)
        self.assertAlmostEqual(sy, 2.0, places=9)
        # y con el azimut/elevación de fábrica la fórmula clásica se
        # mantiene exacta (rotación en planta + inclinación)
        cam2 = Camara3D()
        az = math.radians(30.0)
        el = math.radians(35.0)
        yr = 3.0 * math.sin(az) + (-1.0) * math.cos(az)
        esperado = (3.0 * math.cos(az) - (-1.0) * math.sin(az),
                    2.0 * math.cos(el) - yr * math.sin(el))
        self.assertAlmostEqual(v3.proyecta((3.0, -1.0, 2.0), cam2)[0],
                               esperado[0], places=9)
        self.assertAlmostEqual(v3.proyecta((3.0, -1.0, 2.0), cam2)[1],
                               esperado[1], places=9)

    def test_perspectiva_con_valores_a_mano(self):
        cam = Camara3D(azimuth_deg=0.0, elevacion_deg=0.0)
        cam.perspectiva = True
        cam.distancia_m = 10.0
        cam.centro = (0.0, 0.0, 0.0)
        # el centro del modelo cae en el origen de pantalla con escala 1
        self.assertEqual(v3.proyecta((0.0, 0.0, 0.0), cam), (0.0, 0.0))
        # plano del centro: escala exactamente 1
        sx, sy = v3.proyecta((1.0, 0.0, 2.0), cam)
        self.assertAlmostEqual(sx, 1.0, places=9)
        self.assertAlmostEqual(sy, 2.0, places=9)
        # el cercano (y=+2, cámara en +y) crece: 10/8 = 1.25
        sx_cerca, _ = v3.proyecta((1.0, 2.0, 0.0), cam)
        self.assertAlmostEqual(sx_cerca, 1.25, places=9)
        # el lejano (y=-2) encoge: 10/12
        sx_lejos, _ = v3.proyecta((1.0, -2.0, 0.0), cam)
        self.assertAlmostEqual(sx_lejos, 10.0 / 12.0, places=9)

    def test_el_plano_cercano_evita_divisiones_locas(self):
        cam = Camara3D(azimuth_deg=0.0, elevacion_deg=0.0)
        cam.perspectiva = True
        cam.distancia_m = 10.0
        cam.centro = (0.0, 0.0, 0.0)
        # punto DETRÁS de la cámara: se sujeta al plano cercano (1.2 m)
        sx, _ = v3.proyecta((1.0, 20.0, 0.0), cam)
        self.assertAlmostEqual(sx, 10.0 / 1.2, places=9)
        self.assertTrue(math.isfinite(sx))

    def test_el_centro_desplaza_el_origen_de_pantalla(self):
        cam = Camara3D(azimuth_deg=0.0, elevacion_deg=0.0)
        cam.perspectiva = True
        cam.distancia_m = 10.0
        cam.centro = (100.0, 50.0, 7.0)
        # el CENTRO del modelo (no el origen del mundo) manda
        self.assertEqual(v3.proyecta((100.0, 50.0, 7.0), cam),
                         (0.0, 0.0))

    def test_cercano_mayor_que_lejano_en_vertical(self):
        cam = Camara3D()          # elevación 35: la cámara mira desde arriba
        cam.perspectiva = True
        cam.distancia_m = 20.0
        cam.centro = (0.0, 0.0, 0.0)
        alto, _ = v3.proyecta((5.0, 0.0, 3.0), cam)
        bajo, _ = v3.proyecta((5.0, 0.0, -3.0), cam)
        self.assertGreater(abs(alto), abs(bajo))


class TestPreparaYEncuadre(_EscenaBase):

    def test_fija_centro_y_distancia_del_fov(self):
        cam = Camara3D(perspectiva=True)
        self.assertIsNone(cam.centro)
        self.assertEqual(cam.distancia_m, 0.0)
        v3.prepara_perspectiva([self.caja], cam)
        self.assertIsNotNone(cam.centro)
        self.assertAlmostEqual(cam.centro[0], 5.0, places=9)
        self.assertAlmostEqual(cam.centro[1], 3.0, places=9)
        self.assertGreater(cam.distancia_m, 0.0)
        # radio ~ hypot(5, 3) -> distancia = radio / tan(25°) * 1.08
        radio = math.hypot(5.0, 3.0)
        esperada = radio / math.tan(math.radians(25.0)) * 1.08
        self.assertAlmostEqual(cam.distancia_m, esperada, places=6)

    def test_no_pisa_una_distancia_fijada(self):
        cam = Camara3D(perspectiva=True)
        cam.distancia_m = 42.0
        v3.prepara_perspectiva([self.caja], cam)
        self.assertAlmostEqual(cam.distancia_m, 42.0, places=9)
        self.assertIsNotNone(cam.centro)

    def test_axonometrica_es_no_operacion(self):
        cam = Camara3D()
        v3.prepara_perspectiva([self.caja], cam)
        self.assertIsNone(cam.centro)
        self.assertEqual(cam.distancia_m, 0.0)

    def test_encuadre_cabe_toda_la_escena(self):
        cam = Camara3D(perspectiva=True)
        minx, miny, maxx, maxy = v3.encuadre([self.caja], cam)
        self.assertLess(minx, maxx)
        self.assertLess(miny, maxy)
        for punto in self.caja.puntos:
            sx, sy = v3.proyecta(punto, cam)
            self.assertGreaterEqual(sx, minx - 1e-6)
            self.assertLessEqual(sx, maxx + 1e-6)
            self.assertGreaterEqual(sy, miny - 1e-6)
            self.assertLessEqual(sy, maxy + 1e-6)

    def test_escena_vacia_no_falla(self):
        cam = Camara3D(perspectiva=True)
        v3.prepara_perspectiva([], cam)
        self.assertEqual(v3.encuadre([], cam), (0.0, 0.0, 0.0, 0.0))


class TestTeclaYModelo(ARQGenTestCase):

    def test_p_conmuta_y_home_re_encuadra(self):
        cam = Camara3D()
        self.assertTrue(cam.tecla("p"))
        self.assertTrue(cam.perspectiva)
        self.assertEqual(cam.distancia_m, 0.0)
        self.assertTrue(cam.tecla("p"))
        self.assertFalse(cam.perspectiva)
        cam.perspectiva = True
        cam.distancia_m = 15.0
        self.assertTrue(cam.tecla("Home"))
        self.assertAlmostEqual(cam.distancia_m, 0.0, places=9)
        self.assertTrue(cam.perspectiva)  # el MODO no lo toca Home
        self.assertFalse(cam.tecla("x"))

    def test_mismo_numero_de_caras_en_ambas_proyecciones(self):
        contexto = self.application.create_project(
            self.project_path("persp.arqgen"), name="Persp")
        try:
            from domain import cubiertas as cub
            from services.architecture_service import ArchitectureService
            arq = ArchitectureService(contexto)
            nivel = arq.create_level("Planta 1", 0.0, 3.0)
            arq.create_space(nivel.code, "Sala", "LIVING_ROOM",
                             [(0, 0), (8, 0), (8, 5), (0, 5)])
            cub.generar_cubierta(contexto, None, tipologia="dos_aguas",
                                 pendiente_pct=30.0, con_qto=False)
            modelo, _avisos = v3.modelo3d_desde_proyecto(contexto)
            orto = v3.construir_caras(modelo, Camara3D())
            persp = v3.construir_caras(modelo, Camara3D(perspectiva=True))
            self.assertEqual(len(orto), len(persp))
            self.assertGreater(len(persp), 0)
        finally:
            contexto.close()

    def test_png_determinista_en_perspectiva(self):
        import tempfile
        caras = [Cara3D(puntos=[(0.0, 0.0, 0.0), (8.0, 0.0, 0.0),
                                (8.0, 5.0, 3.0), (0.0, 5.0, 3.0)],
                        color="#a85d43", kind="cubierta")]
        cam = Camara3D(perspectiva=True)
        tmp = tempfile.mkdtemp()
        ruta_a = os.path.join(tmp, "a.png")
        ruta_b = os.path.join(tmp, "b.png")
        v3.export_vista3d_png(caras, cam, ruta_a, titulo="persp")
        cam2 = Camara3D(perspectiva=True)
        v3.export_vista3d_png(caras, cam2, ruta_b, titulo="persp")
        with open(ruta_a, "rb") as fh:
            self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
        with open(ruta_a, "rb") as fa, open(ruta_b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogo3DPerspectiva(_EscenaBase):

    def _ventana(self):
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        self.contexto = self.demo_context()
        return ARQGenWindow(self.contexto, self.application)

    def _cierra(self, ventana):
        try:
            if hasattr(ventana, "_vista3d_dialog"):
                try:
                    if ventana._vista3d_dialog.winfo_exists():
                        ventana._vista3d_dialog.destroy()
                except Exception:  # noqa: BLE001 - ya destruido
                    pass
            ventana.destroy()
        finally:
            self.contexto.close()

    def test_casilla_y_tecla_p_conmutan_la_proyeccion(self):
        ventana = self._ventana()
        try:
            ventana.update()
            ventana.open_view3d_dialog()
            dialogo = ventana._vista3d_dialog
            state = dialogo._vista3d_state
            self.assertFalse(state["cam"].perspectiva)
            # casilla: activa la perspectiva y redibuja
            dialogo._vista3d_perspectiva_var.set(True)
            dialogo._vista3d_perspectiva()
            self.assertTrue(state["cam"].perspectiva)
            self.assertGreater(state["caras"], 0)
            self.assertGreater(
                len(dialogo._vista3d_canvas.find_all()), 0)
            self.assertEqual(
                dialogo._vista3d_perspectiva_var.get(), True)
            # tecla P (por el handler del lienzo): vuelve a axonométrica
            # y sincroniza la casilla
            from types import SimpleNamespace
            dialogo._vista3d_tecla(SimpleNamespace(keysym="p"))
            self.assertFalse(state["cam"].perspectiva)
            self.assertEqual(
                dialogo._vista3d_perspectiva_var.get(), False)
        finally:
            self._cierra(ventana)

    def test_png_del_dialogo_en_perspectiva(self):
        from ui import app_window as aw
        ventana = self._ventana()
        try:
            ventana.update()
            ventana.open_view3d_dialog()
            dialogo = ventana._vista3d_dialog
            dialogo._vista3d_perspectiva_var.set(True)
            dialogo._vista3d_perspectiva()
            ruta = os.path.join(self.tmp, "dialogo_persp.png")
            original = aw.messagebox.showinfo
            aw.messagebox.showinfo = lambda *a, **k: None
            try:
                dialogo._vista3d_export(ruta)
            finally:
                aw.messagebox.showinfo = original
            with open(ruta, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
        finally:
            self._cierra(ventana)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

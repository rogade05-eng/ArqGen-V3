"""VISTA 3D AXONOMÉTRICA (v3.11.0) — el edificio se gira.

Cobertura de estas pruebas:

* Proyección: la isométrica clásica sale como en el libro (z hacia
  arriba, x abajo-derecha, y abajo-izquierda) y la cámara se sujeta
  (elevación 8..80, zoom 0.2..8) y envuelve el azimut módulo 360.
* Modelo: proyecto vacío → avisos amables y cero caras; el edificio
  del asistente se reconstruye con niveles apilados por cota, muros
  con su altura propia, locales y vanos.
* Extrusión: caja de muro con culling (3 caras visibles para una
  cámara concreta), vanos a su cota con color de puerta/ventana,
  explosión que separa niveles, aislado de un nivel, orden del pintor
  ascendente y modos de color distintos.
* PNG determinista: contenedor válido (IHDR/IEND/IDAT), byte a byte
  igual en dos exportaciones, distinto al cambiar la cámara, y sin
  romper con cero caras ni títulos acentuados.
* Diálogo real (Tk bajo Xvfb): sin geometría → mensaje amable y sin
  abrir; con edificio → caras en el lienzo, giro, aislado, explosión,
  recarga y export PNG de punta a punta.
"""

from __future__ import annotations

import os
import struct
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui import view3d as v3
from ui.view3d import Camara3D, Cara3D, Modelo3D, Nivel3D


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


def _consultorio(levels: int = 1):
    data = bw.BuildingWizardData()
    data.levels = [bw.LevelSpec(name="Planta Baja", height_m=3.0)]
    if levels > 1:
        data.levels.append(bw.LevelSpec(name="Planta Alta",
                                        height_m=3.0))
    data.usage_type = "Consultorio médico"
    data.rooms = bw.preset_rooms("Consultorio médico", "Planta Baja")
    if levels > 1:
        data.rooms += bw.preset_rooms("Consultorio médico", "Planta Alta")
    data.relations = bw.suggest_relations(data)
    data.installations = ["Eléctrica", "Sanitaria"]
    return data


def _muro_manual(x1: float, y1: float, x2: float, y2: float,
                 nivel: Nivel3D):
    from domain.model import Wall
    return Wall(level_id=nivel.level_id, start=(x1, y1), end=(x2, y2),
                thickness_m=0.2, height_m=nivel.height_m)


def _modelo_manual() -> Modelo3D:
    nivel = Nivel3D("L1", "Nivel 1", 0.0, 3.0, 0)
    modelo = Modelo3D(niveles=[nivel],
                      nivel_por_id={"L1": nivel})
    modelo.muros.append(_muro_manual(0.0, 0.0, 4.0, 0.0, nivel))
    return modelo


class TestProyeccion(unittest.TestCase):
    """La matemática de la cámara, verificada a mano."""

    def test_proyeccion_isometrica_clasica(self):
        cam = Camara3D(45, 35.264, 1.0)
        sx, sy = v3.proyecta((0.0, 0.0, 1.0), cam)
        self.assertAlmostEqual(sx, 0.0, places=3)
        self.assertGreater(sy, 0.8)          # z sube en pantalla
        sx, sy = v3.proyecta((1.0, 0.0, 0.0), cam)
        self.assertGreater(sx, 0.7)          # x baja a la derecha
        self.assertAlmostEqual(sy, -0.408, places=2)
        sx, sy = v3.proyecta((0.0, 1.0, 0.0), cam)
        self.assertLess(sx, -0.7)            # y baja a la izquierda
        self.assertAlmostEqual(sy, -0.408, places=2)

    def test_camara_se_sujeta_y_envuelve(self):
        cam = Camara3D()
        cam.inclina(999.0)
        self.assertEqual(cam.elevacion_deg, Camara3D.ELEV_MAX)
        cam.inclina(-999.0)
        self.assertEqual(cam.elevacion_deg, Camara3D.ELEV_MIN)
        cam.acerca(1e-6)
        self.assertEqual(cam.zoom, Camara3D.ZOOM_MIN)
        cam.acerca(1e9)
        self.assertEqual(cam.zoom, Camara3D.ZOOM_MAX)
        plano = Camara3D(0.0, 35, 1.0)
        plano.gira(400.0)
        self.assertAlmostEqual(plano.azimuth_deg, 40.0, places=6)

    def test_encuadre_envuelve_a_los_puntos(self):
        cam = Camara3D(30, 35, 1.0)
        cara = Cara3D(puntos=[(0, 0, 0), (4, 0, 0), (4, 0, 3)],
                      color="#ffffff")
        minx, miny, maxx, maxy = v3.encuadre([cara], cam)
        for punto in cara.puntos:
            sx, sy = v3.proyecta(punto, cam)
            self.assertLessEqual(minx - 1e-9, sx)
            self.assertLessEqual(sx, maxx + 1e-9)
            self.assertLessEqual(miny - 1e-9, sy)
            self.assertLessEqual(sy, maxy + 1e-9)


class TestModelo(ARQGenTestCase):
    """modelo3d_desde_proyecto: vacío amable y edificio completo."""

    def test_proyecto_vacio_da_avisos_y_cero_caras(self):
        context = self.application.create_project(
            self.project_path("vacio.arqgen"), name="Vacío 3D")
        try:
            modelo, avisos = v3.modelo3d_desde_proyecto(context)
            self.assertEqual(modelo.muros, [])
            self.assertEqual(modelo.locales, [])
            self.assertTrue(avisos)
            self.assertEqual(v3.construir_caras(modelo, Camara3D()), [])
        finally:
            context.close()

    def test_edificio_generado_reconstruido(self):
        context = self.demo_context()
        try:
            bw.apply_plan(_consultorio(levels=2), context)
            modelo, avisos = v3.modelo3d_desde_proyecto(context)
            # el demo trae «Nivel 1» propio + Planta Baja + Planta Alta
            self.assertEqual(len(modelo.niveles), 3)
            cotas = [n.base_z for n in modelo.niveles]
            self.assertEqual(cotas, sorted(cotas))
            self.assertIn(0.0, cotas)
            self.assertIn(3.0, cotas)
            self.assertEqual(modelo.niveles[-1].name, "Planta Alta")
            self.assertGreaterEqual(len(modelo.muros), 10)
            self.assertGreaterEqual(len(modelo.locales), 12)
            self.assertGreater(len(modelo.vanos), 0)
            self.assertTrue(modelo.muro_por_id)
            self.assertFalse(avisos)
        finally:
            context.close()

    def test_niveles_se_apilan_por_cota(self):
        from services.architecture_service import ArchitectureService
        context = self.demo_context()
        try:
            arch = ArchitectureService(context)
            arch.create_level(name="Sótano", elevation_m=-3.0,
                              height_m=2.8)
            arch.create_level(name="Altillo", elevation_m=6.4,
                              height_m=2.4)
            modelo, _avisos = v3.modelo3d_desde_proyecto(context)
            cotas = [n.base_z for n in modelo.niveles]
            self.assertEqual(cotas, sorted(cotas))
            self.assertIn(-3.0, cotas)
            self.assertIn(6.4, cotas)
        finally:
            context.close()


class TestCaras(ARQGenTestCase):
    """Extrusión, culling, vanos, explosión, aislado y colores."""

    def test_muro_extruido_con_culling(self):
        modelo = _modelo_manual()
        caras = v3.construir_caras(modelo, Camara3D(30, 35, 1.0),
                                   mostrar_plataformas=False)
        # para az=30 solo se ven: un lado largo, una testa y la tapa
        self.assertEqual(len(caras), 3)
        self.assertEqual({c.kind for c in caras}, {"muro", "tapa"})
        zs = [p[2] for c in caras for p in c.puntos]
        self.assertAlmostEqual(min(zs), 0.0, places=6)
        self.assertAlmostEqual(max(zs), 3.0, places=6)
        for cara in caras:
            self.assertTrue(cara.profundidad == cara.profundidad)
        # con plataformas, el nivel gana su losa de apoyo
        con_plataforma = v3.construir_caras(modelo, Camara3D(30, 35, 1.0))
        self.assertTrue(any(c.kind == "plataforma"
                            for c in con_plataforma))

    def test_vanos_a_su_cota_con_color(self):
        context = self.demo_context()
        try:
            bw.apply_plan(_consultorio(), context)
            modelo, _avisos = v3.modelo3d_desde_proyecto(context)
            caras = v3.construir_caras(modelo, Camara3D())
            colores = {c.color for c in caras if c.kind == "vano"}
            self.assertIn(v3.COLOR_VANO["DOOR"], colores)
            self.assertIn(v3.COLOR_VANO["WINDOW"], colores)
            tope = max(n.base_z + n.height_m for n in modelo.niveles)
            for cara in caras:
                if cara.kind != "vano":
                    continue
                zs = [p[2] for p in cara.puntos]
                self.assertGreaterEqual(min(zs), -1e-9)
                self.assertLessEqual(max(zs), tope + 1e-9)
        finally:
            context.close()

    def test_explosion_separa_niveles(self):
        context = self.demo_context()
        try:
            bw.apply_plan(_consultorio(levels=2), context)
            modelo, _avisos = v3.modelo3d_desde_proyecto(context)
            plano = v3.construir_caras(modelo, Camara3D())
            explotado = v3.construir_caras(modelo, Camara3D(),
                                           explotar_m=2.0)
            tope_plano = max(p[2] for c in plano for p in c.puntos)
            tope_explo = max(p[2] for c in explotado for p in c.puntos)
            self.assertGreater(tope_explo, tope_plano + 1.5)
            self.assertTrue(any(c.kind == "plataforma"
                                for c in explotado))
        finally:
            context.close()

    def test_aislar_nivel(self):
        context = self.demo_context()
        try:
            bw.apply_plan(_consultorio(levels=2), context)
            modelo, _avisos = v3.modelo3d_desde_proyecto(context)
            segundo = modelo.niveles[1]
            todo = v3.construir_caras(modelo, Camara3D())
            solo = v3.construir_caras(modelo, Camara3D(),
                                      nivel_id=segundo.level_id)
            self.assertLess(len(solo), len(todo))
            for cara in solo:
                for punto in cara.puntos:
                    self.assertGreaterEqual(punto[2],
                                            segundo.base_z - 0.16)
        finally:
            context.close()

    def test_orden_del_pintor_ascendente(self):
        context = self.demo_context()
        try:
            bw.apply_plan(_consultorio(levels=2), context)
            modelo, _avisos = v3.modelo3d_desde_proyecto(context)
            caras = v3.construir_caras(modelo, Camara3D(30, 35, 1.0))
            profundidades = [c.profundidad for c in caras]
            self.assertEqual(profundidades,
                             sorted(profundidades))
            # dos muros paralelos: el lejano se pinta primero
            nivel = modelo.niveles[0]
            lejano = _muro_manual(0.0, 0.0, 4.0, 0.0, nivel)
            cercano = _muro_manual(0.0, 5.0, 4.0, 5.0, nivel)
            modelo2 = Modelo3D(niveles=[nivel],
                               nivel_por_id={nivel.level_id: nivel})
            modelo2.muros += [lejano, cercano]
            par = v3.construir_caras(modelo2, Camara3D(30, 35, 1.0))
            visibles = [c for c in par if c.kind == "muro"]
            self.assertLess(visibles[0].profundidad,
                            visibles[-1].profundidad)
        finally:
            context.close()

    def test_colores_tipo_y_monocromo_difieren(self):
        context = self.demo_context()
        try:
            bw.apply_plan(_consultorio(), context)
            modelo, _avisos = v3.modelo3d_desde_proyecto(context)
            por_tipo = v3.construir_caras(modelo, Camara3D(),
                                          colores="tipo")
            mono = v3.construir_caras(modelo, Camara3D(), colores="mono")
            self.assertNotEqual({c.color for c in por_tipo},
                                {c.color for c in mono})
            pisos_mono = {c.color for c in mono if c.kind == "piso"}
            self.assertEqual(pisos_mono, {v3.COLOR_MONO_PISO})
        finally:
            context.close()


class TestPNG(ARQGenTestCase):
    """export_vista3d_png: contenedor, determinismo y tolerancia."""

    def _caras(self, context):
        bw.apply_plan(_consultorio(), context)
        modelo, _avisos = v3.modelo3d_desde_proyecto(context)
        return v3.construir_caras(modelo, Camara3D(30, 35, 1.0))

    def test_png_valido_determinista_y_acotado(self):
        context = self.demo_context()
        try:
            caras = self._caras(context)
            paths = [os.path.join(self.tmp, f"d{i}.png")
                     for i in range(2)]
            for path in paths:
                v3.export_vista3d_png(caras, Camara3D(30, 35, 1.0), path,
                                      titulo="Vista 3D de prueba")
            self.assertEqual(open(paths[0], "rb").read(),
                             open(paths[1], "rb").read())
            raw = open(paths[0], "rb").read()
            self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
            chunks, pos = [], 8
            while pos < len(raw):
                (length,) = struct.unpack(">I", raw[pos:pos + 4])
                chunks.append(raw[pos + 4:pos + 8].decode())
                pos += 12 + length
            self.assertEqual(chunks[0], "IHDR")
            self.assertEqual(chunks[-1], "IEND")
            self.assertIn("IDAT", chunks)
            self.assertGreater(os.path.getsize(paths[0]), 5000)
            self.assertEqual(
                struct.unpack(">II", raw[16:24]), (1600, 1000))
        finally:
            context.close()

    def test_png_otra_camara_difiere(self):
        context = self.demo_context()
        try:
            caras = self._caras(context)
            blobs = []
            for az in (30, 150):
                path = os.path.join(self.tmp, f"az{az}.png")
                v3.export_vista3d_png(caras, Camara3D(az, 35, 1.0), path)
                blobs.append(open(path, "rb").read())
            self.assertNotEqual(blobs[0], blobs[1])
        finally:
            context.close()

    def test_png_vacio_y_con_acentos_no_rompe(self):
        path = os.path.join(self.tmp, "vacio.png")
        v3.export_vista3d_png([], Camara3D(), path,
                              titulo="Edificación sin datos")
        raw = open(path, "rb").read()
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", raw[16:24]), (1600, 1000))
        # determinista también con título acentuado (des-acentúa)
        path2 = os.path.join(self.tmp, "acentos.png")
        v3.export_vista3d_png([], Camara3D(), path2,
                              titulo="Edificación sin datos")
        self.assertEqual(raw, open(path2, "rb").read())


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestDialogoVista3D(ARQGenTestCase):
    """El diálogo real: giro, aislado, explosión, recarga y PNG."""

    def _make_window(self):
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        self.context = self.demo_context()
        return ARQGenWindow(self.context, self.application)

    def test_dialogo_sin_geometria_mensaje_y_no_abre(self):
        self.context = self.application.create_project(
            self.project_path("nada.arqgen"), name="Sin geometría")
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        window = ARQGenWindow(self.context, self.application)
        try:
            from ui import app_window as aw
            original = aw.messagebox.showinfo
            capturado = {}
            aw.messagebox.showinfo = lambda *a, **k: capturado.update(
                {"args": a})
            try:
                window.open_view3d_dialog()
            finally:
                aw.messagebox.showinfo = original
            self.assertTrue(capturado, "esperaba el mensaje amable")
            self.assertFalse(hasattr(window, "_vista3d_dialog"))
        finally:
            window.destroy()
            self.context.close()

    def test_dialogo_flujo_completo_hasta_png(self):
        window = self._make_window()
        try:
            bw.apply_plan(_consultorio(levels=2), window.ctx)
            window.update()
            window.open_view3d_dialog()
            self.assertTrue(hasattr(window, "_vista3d_dialog"))
            dialog = window._vista3d_dialog
            state = dialog._vista3d_state
            self.assertGreater(state["caras"], 0)
            self.assertGreater(len(dialog._vista3d_canvas.find_all()), 0)
            caras_inicio = state["caras"]

            # girar cambia la cámara y el lienzo se re-dibuja
            dialog._vista3d_gira(30)
            self.assertAlmostEqual(
                state["cam"].azimuth_deg,
                (Camara3D().azimuth_deg + 30) % 360, places=6)
            self.assertGreater(state["caras"], 0)

            # aislado del segundo nivel reduce las caras
            modelo = state["modelo"]
            segundo = modelo.niveles[1]
            state["nivel_id"] = segundo.level_id
            dialog._vista3d_render()
            self.assertLess(state["caras"], caras_inicio)
            state["nivel_id"] = ""
            dialog._vista3d_render()

            # explosión sube el tope visible y añade plataformas
            state["explotar_m"] = 2.0
            dialog._vista3d_render()
            self.assertGreater(state["caras"], 0)
            state["explotar_m"] = 0.0
            dialog._vista3d_render()

            # recargar re-lee el proyecto y sigue habiendo caras
            dialog._vista3d_recargar()
            self.assertGreater(state["caras"], 0)

            # exportar PNG de punta a punta (sin filedialog)
            from ui import app_window as aw
            ruta = os.path.join(self.tmp, "dialogo3d.png")
            original = aw.messagebox.showinfo
            aw.messagebox.showinfo = lambda *a, **k: None
            try:
                dialog._vista3d_export(ruta)
            finally:
                aw.messagebox.showinfo = original
            raw = open(ruta, "rb").read()
            self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(os.path.getsize(ruta), 5000)
        finally:
            if hasattr(window, "_vista3d_dialog"):
                try:
                    if window._vista3d_dialog.winfo_exists():
                        window._vista3d_dialog.destroy()
                except Exception:  # noqa: BLE001 - ya destruido
                    pass
            window.destroy()
            self.context.close()

    def test_dialogo_desde_la_demo_solo(self):
        window = self._make_window()
        try:
            window.update()
            window.open_view3d_dialog()
            self.assertTrue(hasattr(window, "_vista3d_dialog"))
            state = window._vista3d_dialog._vista3d_state
            self.assertGreater(state["caras"], 0)
            # monocromo desde los combos del diálogo
            state["colores"] = "mono"
            window._vista3d_dialog._vista3d_render()
            self.assertGreater(state["caras"], 0)
        finally:
            if hasattr(window, "_vista3d_dialog"):
                try:
                    if window._vista3d_dialog.winfo_exists():
                        window._vista3d_dialog.destroy()
                except Exception:  # noqa: BLE001 - ya destruido
                    pass
            window.destroy()
            self.context.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

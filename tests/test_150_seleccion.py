"""SELECCION EN EL LIENZO (v3.19.1): la mira estilo AutoCAD y la capa
CAD no roban el clic. Pedido del usuario: «ahora no puedo seleccionar
los locales, muros, ventanas, puertas, etc.» — la cruz que sigue al
raton era SIEMPRE el objeto «current» de Tk y se comia el clic; el
picking ahora recorre find_overlapping de arriba hacia abajo, salta
los superpuestos (acad_mira/cadoverlay) y resuelve el primer tag con
fila real del explorador."""

from __future__ import annotations

import os
import types
import unittest

from tests.base import ARQGenTestCase

try:  # pragma: no cover — igual que el resto de pruebas GUI
    DISPLAY = bool(os.environ.get("DISPLAY")) and os.environ.get(
        "DISPLAY") != ""
except Exception:  # noqa: BLE001
    DISPLAY = False


class _ProyectoBase(ARQGenTestCase):

    def setUp(self) -> None:
        super().setUp()
        from services.architecture_service import ArchitectureService
        self.context = self.application.create_project(
            self.project_path("seleccion.arqgen"), name="Seleccion")
        self.arq = ArchitectureService(self.context)
        self.n1 = self.arq.create_level("PB", 0.0, 3.0)
        self.arq.create_space(self.n1.code, "Hueco", "STAIR",
                              [(0, 0), (4, 0), (4, 4.5), (0, 4.5)])
        self.sala = self.arq.create_space(
            self.n1.code, "Sala", "LIVING_ROOM",
            [(4, 0), (10, 0), (10, 5), (4, 5)])
        self.w1 = self.arq.create_wall(self.n1.code, (0, 0), (10, 0))
        self.d1 = self.arq.create_opening("DOOR", self.w1.code, 0.9, 2.1,
                                          offset_m=1.0)
        self.w2 = self.arq.create_wall(self.n1.code, (10, 0), (10, 5))
        self.v1 = self.arq.create_opening("WINDOW", self.w2.code, 1.2, 1.4,
                                          offset_m=1.0, sill_height_m=0.9)

    # -- ayudas ----------------------------------------------------------------
    def _ventana(self):
        from ui.app_window import ARQGenWindow
        from ui import theme
        theme.set_mode("dark")
        win = ARQGenWindow(self.context, self.application)
        win.current_discipline = "ARCHITECTURE"
        win.redraw(fit=True)
        win.update()
        self.addCleanup(win.destroy)
        return win

    def _tam(self, win):
        return (max(win.canvas.winfo_width(), 800),
                max(win.canvas.winfo_height(), 600))

    def _centro_screen(self, win, coords):
        w, h = self._tam(win)
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        return win.viewport.to_screen(sum(xs) / len(xs),
                                      sum(ys) / len(ys), w, h)

    def _prim_de(self, win, tipo):
        for p in win._primitives:
            if p.row.type == tipo:
                return p
        return None

    def _clic_real(self, win, px, py):
        """Motion + Button-1 reales: la mira se dibuja sobre el puntero,
        como cuando el usuario trabaja."""
        win.canvas.event_generate("<Motion>", warp=True,
                                  x=int(px), y=int(py))
        win.update()
        win.canvas.event_generate("<Button-1>", x=int(px), y=int(py))
        win.update()


class TestHitUid(_ProyectoBase):
    """_hit_uid salta la mira y la capa CAD aunque crucen el puntero."""

    @unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
    def test_tags_superpuestos_declarados(self):
        win = self._ventana()
        self.assertIn("acad_mira", win._TAGS_SUPERPUESTOS)
        self.assertIn("cadoverlay", win._TAGS_SUPERPUESTOS)

    @unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
    def test_la_mira_esta_sobre_el_muro_y_aun_asi_resuelve(self):
        win = self._ventana()
        muro = self._prim_de(win, "WALL")
        self.assertIsNotNone(muro)
        sx, sy = self._centro_screen(win, muro.coords)
        # 1) la mira se dibuja CRUZANDO el punto (asi trabaja el usuario)
        win._mira_redibuja(types.SimpleNamespace(x=sx, y=sy))
        miras = win.canvas.find_withtag("acad_mira")
        self.assertTrue(miras, "la mira deberia estar dibujada")
        # 2) Preconditions: find_overlapping SI la ve (por eso robaba)
        caja = (sx - 2, sy - 2, sx + 2, sy + 2)
        solapados = win.canvas.find_overlapping(*caja)
        self.assertTrue(
            any("acad_mira" in win.canvas.gettags(i) for i in solapados))
        # 3) el picking SALTA la mira y devuelve el muro
        uid = win._hit_uid(types.SimpleNamespace(x=sx, y=sy))
        self.assertEqual(uid, muro.row.uid)

    @unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
    def test_la_capa_cad_tampoco_tapa(self):
        win = self._ventana()
        muro = self._prim_de(win, "WALL")
        sx, sy = self._centro_screen(win, muro.coords)
        # una linea de la orden CAD encima del muro (tag cadoverlay)
        win.canvas.create_line(0, sy, win.canvas.winfo_width(), sy,
                               fill="#ff0000", tags=("cadoverlay",))
        win.update()
        uid = win._hit_uid(types.SimpleNamespace(x=sx, y=sy))
        self.assertEqual(uid, muro.row.uid)

    @unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
    def test_vacio_da_none(self):
        win = self._ventana()
        win.viewport.scale = 60.0
        win.viewport.center_x, win.viewport.center_y = 5.0, 2.5
        win.redraw()
        win.update()
        # esquina superior izquierda: a 60 px/m el mundo queda lejos
        uid = win._hit_uid(types.SimpleNamespace(x=2, y=2))
        self.assertIsNone(uid)


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestClicRealSelecciona(_ProyectoBase):
    """El clic REAL del usuario selecciona cada tipo de objeto."""

    def test_clic_selecciona_muro_local_puerta_ventana(self):
        win = self._ventana()
        self.assertTrue(win._acad.mira, "la mira viene activa de fabrica")

        # 1a fase: sin mobiliario ni escalera, el centro del local
        # esta libre para el clic del SPACE
        for tipo in ("WALL", "SPACE", "DOOR", "WINDOW"):
            prim = self._prim_de(win, tipo)
            self.assertIsNotNone(prim, f"la planta deberia dibujar {tipo}")
            sx, sy = self._centro_screen(win, prim.coords)
            self._clic_real(win, sx, sy)
            sel = win.selection
            self.assertIsNotNone(sel, f"clic sobre {tipo} no selecciono")
            self.assertEqual(sel.uid, prim.row.uid,
                             f"clic sobre {tipo} eligio {sel.type}")

        # 2a fase: mobiliario y escalera generadas, clic sobre ellas
        from domain import escaleras as esc
        from domain import mobiliario as mob
        mob.generar_mobiliario(self.context, None, nivel_id=self.n1.id)
        esc.generar_escalera(self.context, None, tipo="recta",
                             desnivel_m=3.0, x=12.0, y=8.0,
                             nivel_id=self.n1.id)
        win.redraw()
        win.update()
        vistos = {"WALL", "SPACE", "DOOR", "WINDOW"}
        for tipo in ("FURNITURE", "STAIR"):
            prim = self._prim_de(win, tipo)
            if prim is None:
                continue  # el motor decide si amuebla este uso
            sx, sy = self._centro_screen(win, prim.coords)
            self._clic_real(win, sx, sy)
            sel = win.selection
            self.assertIsNotNone(sel, f"clic sobre {tipo} no selecciono")
            self.assertEqual(sel.uid, prim.row.uid,
                             f"clic sobre {tipo} eligio {sel.type}")
            vistos.add(sel.type)
        self.assertEqual(vistos, {"WALL", "SPACE", "DOOR", "WINDOW",
                                  "FURNITURE", "STAIR"})

    def test_clic_en_vacio_conserva_la_seleccion(self):
        win = self._ventana()
        muro = self._prim_de(win, "WALL")
        sx, sy = self._centro_screen(win, muro.coords)
        self._clic_real(win, sx, sy)
        self.assertEqual(win.selection.type, "WALL")
        # lejos del dibujo: la seleccion NO se pierde
        win.viewport.scale = 60.0
        win.viewport.center_x, win.viewport.center_y = 5.0, 2.5
        win.redraw()
        win.update()
        self._clic_real(win, 2, 2)
        self.assertIsNotNone(win.selection)
        self.assertEqual(win.selection.type, "WALL")

    def test_doble_clic_abre_propiedades(self):
        win = self._ventana()
        muro = self._prim_de(win, "WALL")
        sx, sy = self._centro_screen(win, muro.coords)
        abiertos = []
        win.edit_property_dialog = lambda: abiertos.append(1)
        px, py = int(sx), int(sy)
        win.canvas.event_generate("<Motion>", warp=True, x=px, y=py)
        win.update()
        win.canvas.event_generate("<Button-1>", x=px, y=py)
        win.update()
        win.canvas.event_generate("<ButtonRelease-1>", x=px, y=py)
        win.update()
        win.canvas.event_generate("<Button-1>", x=px, y=py)
        win.update()
        self.assertTrue(abiertos, "el doble clic no abrio propiedades")
        self.assertEqual(win.selection.uid, muro.row.uid)

    def test_clic_derecho_selecciona_y_abre_menu(self):
        win = self._ventana()
        muro = self._prim_de(win, "WALL")
        sx, sy = self._centro_screen(win, muro.coords)
        capturado = {}
        win._popup_menu = lambda menu, event: capturado.update({"menu": menu})
        px, py = int(sx), int(sy)
        win.canvas.event_generate("<Motion>", warp=True, x=px, y=py)
        win.update()
        win.canvas.event_generate("<Button-3>", x=px, y=py)
        win.update()
        win.canvas.event_generate("<ButtonRelease-3>", x=px, y=py)
        win.update()
        self.assertIsNotNone(win.selection)
        self.assertEqual(win.selection.uid, muro.row.uid)
        self.assertIn("menu", capturado)

    def test_herramientas_cad_siguen_vivas(self):
        # el fix no rompe el flujo CAD: con una orden activa el clic
        # ALIMENTA la orden (MOVER elige el muro en su primer paso,
        # igual que v3.14.0) y no es el seleccionador del lienzo
        win = self._ventana()
        win._cad_set_tool("mover")
        muro = self._prim_de(win, "WALL")
        sx, sy = self._centro_screen(win, muro.coords)
        self._clic_real(win, sx, sy)
        self.assertEqual(win._cad_estado()["tool"], "mover")
        self.assertEqual(win._cad_ref, ("WALL", muro.row.uid))
        win._cad_cancelar()
        self.assertIsNone(win._cad_ref)
        # y al cancelar, el proximo clic vuelve a seleccionar
        self._clic_real(win, sx, sy)
        self.assertEqual(win.selection.type, "WALL")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

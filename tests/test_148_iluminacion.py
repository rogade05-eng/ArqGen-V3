"""ILUMINACIÓN ARTIFICIAL POR TIPOS DE LÁMPARAS (v3.19.0): catálogo
(incluye LED), método de los lúmenes, colocación en la red LIGHTING,
comparativa, undo y GUI. Pedido del usuario: «Iluminación artificial
según tipos de lámparas (incluyendo led)»."""

from __future__ import annotations

import os
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
            self.project_path("iluminacion.arqgen"), name="Iluminacion")
        self.arq = ArchitectureService(self.context)
        self.n1 = self.arq.create_level("PB", 0.0, 3.0)
        self.sala = self.arq.create_space(
            self.n1.code, "Sala", "LIVING_ROOM",
            [(0, 0), (10, 0), (10, 5), (0, 5)])
        self.cocina = self.arq.create_space(
            self.n1.code, "Cocina", "KITCHEN",
            [(10, 0), (15, 0), (15, 4), (10, 4)])

    def _lista(self, tipo):
        return self.context.architecture.list(tipo, self.context.project.id)

    def _nodos(self):
        return self.context.installations.list("NODE",
                                               self.context.project.id)


class TestCatalogo(unittest.TestCase):
    """Lámparas: LED y clásicas, con eficacia."""

    def test_doce_tipos_con_led(self):
        from domain import iluminacion as ilu
        claves = ilu.tipos_lampara()
        self.assertEqual(len(claves), 12)
        leds = [c for c in claves
                if ilu.datos_lampara(c)["tecnologia"] == "LED"]
        self.assertGreaterEqual(len(leds), 7)

    def test_eficacia_calculada(self):
        from domain import iluminacion as ilu
        self.assertAlmostEqual(
            ilu.datos_lampara("led_panel")["eficacia_lm_w"], 100.0,
            places=1)
        self.assertLess(
            ilu.datos_lampara("incandescente")["eficacia_lm_w"], 15.0)

    def test_lampara_desconocida(self):
        from core.errors import DomainError
        from domain import iluminacion as ilu
        with self.assertRaises(DomainError) as cm:
            ilu.datos_lampara("vela")
        self.assertEqual(cm.exception.code, "ARQ-ILU-001")

    def test_lux_por_uso(self):
        from domain import iluminacion as ilu
        self.assertEqual(ilu.lux_para("KITCHEN"), 300)
        self.assertEqual(ilu.lux_para("BEDROOM"), 100)
        self.assertEqual(ilu.lux_para("RARO"), 150)


class TestLumenes(unittest.TestCase):
    """El método de los lúmenes y su comparativa."""

    def test_dimensionar_exacto(self):
        from domain import iluminacion as ilu
        d = ilu.dimensionar(20.0, 300, "led_panel")
        self.assertEqual(d["n_lamparas"], 4)     # ceil(6000/1728)
        self.assertAlmostEqual(d["potencia_total_w"], 144.0, places=6)
        self.assertAlmostEqual(d["densidad_w_m2"], 7.2, places=6)

    def test_led_gana_a_incandescente(self):
        from domain import iluminacion as ilu
        led = ilu.dimensionar(20.0, 300, "led_panel")
        clasica = ilu.dimensionar(20.0, 300, "incandescente")
        self.assertGreater(clasica["potencia_total_w"],
                           led["potencia_total_w"] * 3)

    def test_errores_de_area_y_lux(self):
        from core.errors import DomainError
        from domain import iluminacion as ilu
        with self.assertRaises(DomainError) as cm:
            ilu.dimensionar(-1.0, 300, "led_panel")
        self.assertEqual(cm.exception.code, "ARQ-ILU-002")
        with self.assertRaises(DomainError) as cm:
            ilu.dimensionar(20.0, 0, "led_panel")
        self.assertEqual(cm.exception.code, "ARQ-ILU-002")

    def test_comparativa_y_tabla_cp1252(self):
        from domain import iluminacion as ilu
        comp = ilu.tabla_comparativa(20.0, 300)
        self.assertEqual(len(comp), 12)
        lineas = ilu.tabla_texto(20.0, 300)
        self.assertEqual(len(lineas), 2 + 12)
        for linea in lineas:
            linea.encode("cp1252")

    def test_reticula(self):
        from domain import iluminacion as ilu
        self.assertEqual(len(ilu._reticula(1, 5.0, 5.0)), 1)
        pts = ilu._reticula(4, 10.0, 5.0)
        self.assertEqual(len(pts), 4)
        self.assertNotEqual(pts[0], pts[1])


class TestGenerarIluminacion(_ProyectoBase):
    """Colocación de luminarias reales en la red de alumbrado."""

    def test_genera_luminarias_en_red_lighting(self):
        from domain import iluminacion as ilu
        r = ilu.generar_iluminacion(self.context, None,
                                    lampara="led_panel",
                                    space_ids=[self.sala.id])
        redes = [n for n in self.context.installations.list(
            "NETWORK", self.context.project.id) if n.system == "LIGHTING"]
        self.assertEqual(len(redes), 1)
        self.assertTrue((redes[0].metadata or {}).get("origen"))
        lum = [n for n in self._nodos() if n.kind == "LUMINAIRE"]
        self.assertEqual(len(lum), r["locales"][0]["n_lamparas"])
        self.assertEqual(lum[0].attrs.get("lampara"), "led_panel")
        self.assertEqual(lum[0].attrs.get("lux_objetivo"), 150)
        self.assertTrue(lum[0].space_id)
        # dentro del AABB del local
        xs = [p[0] for p in self.sala.boundary]
        ys = [p[1] for p in self.sala.boundary]
        for n in lum:
            self.assertGreaterEqual(n.x, min(xs) - 1e-6)
            self.assertLessEqual(n.x, max(xs) + 1e-6)
            self.assertGreaterEqual(n.y, min(ys) - 1e-6)
            self.assertLessEqual(n.y, max(ys) + 1e-6)

    def test_lux_del_uso_y_pedidos(self):
        from domain import iluminacion as ilu
        r = ilu.generar_iluminacion(self.context, None,
                                    lampara="led_bombilla",
                                    space_ids=[self.cocina.id])
        self.assertEqual(r["locales"][0]["lux"], 300)   # cocina
        r2 = ilu.generar_iluminacion(self.context, None,
                                     lampara="led_bombilla",
                                     space_ids=[self.cocina.id], lux=500)
        self.assertEqual(r2["locales"][0]["lux"], 500)

    def test_idempotente_quita_las_anteriores(self):
        from domain import iluminacion as ilu
        r1 = ilu.generar_iluminacion(self.context, None,
                                     lampara="led_panel",
                                     space_ids=[self.sala.id])
        r2 = ilu.generar_iluminacion(self.context, None,
                                     lampara="fluorescente_t8",
                                     space_ids=[self.sala.id])
        self.assertEqual(len(r2["eliminados"]), len(r1["creados"]))
        lum = [n for n in self._nodos() if n.kind == "LUMINAIRE"]
        self.assertEqual(len(lum), r2["locales"][0]["n_lamparas"])
        self.assertTrue(all(n.attrs.get("lampara") == "fluorescente_t8"
                            for n in lum))

    def test_quitar_iluminacion(self):
        from domain import iluminacion as ilu
        r = ilu.generar_iluminacion(self.context, None,
                                    lampara="led_panel",
                                    space_ids=[self.sala.id])
        bajas = ilu.quitar_iluminacion(self.context)
        self.assertEqual(len(bajas), len(r["creados"]))
        self.assertFalse([n for n in self._nodos()
                          if n.kind == "LUMINAIRE"
                          and (n.attrs or {}).get("origen_luz")])

    def test_undo_persistente(self):
        from app.undo_service import PersistentUndoService
        from domain import iluminacion as ilu
        r = ilu.generar_iluminacion(self.context, None,
                                    lampara="led_panel",
                                    space_ids=[self.sala.id])
        self.context.commit()
        # deshace el último add_node (uno de los creados)
        self.assertTrue(PersistentUndoService(self.context).undo())
        self.assertEqual(len([n for n in self._nodos()
                              if n.kind == "LUMINAIRE"]),
                         len(r["creados"]) - 1)

    def test_sin_locales_error_amable(self):
        from core.errors import DomainError
        from domain import iluminacion as ilu
        with self.assertRaises(DomainError) as cm:
            ilu.generar_iluminacion(self.context, None,
                                    lampara="led_panel",
                                    space_ids=["no-existe"])
        self.assertEqual(cm.exception.code, "ARQ-ILU-003")

    def test_resumen_cp1252(self):
        from domain import iluminacion as ilu
        r = ilu.generar_iluminacion(self.context, None,
                                    lampara="led_panel",
                                    space_ids=[self.sala.id,
                                               self.cocina.id])
        texto = ilu.resumen_texto(r)
        texto.encode("cp1252")
        lineas = ilu.locales_texto(r)
        self.assertEqual(len(lineas), 1 + 2 + 1)
        for linea in lineas:
            linea.encode("cp1252")

    def test_qto_cuenta_luminarias(self):
        from domain import iluminacion as ilu
        from services.quantity_service import QuantityService
        ilu.generar_iluminacion(self.context, None, lampara="led_panel",
                                space_ids=[self.sala.id])
        self.context.commit()
        stats = QuantityService(self.context).compute_all()
        self.assertGreaterEqual(stats.objects_processed, 1)


def r_n(ctx, space_id):
    """Nº de luminarias creadas para el local (ayudante del test)."""
    return len([n for n in ctx.installations.list("NODE", ctx.project.id)
                if n.kind == "LUMINAIRE"
                and (n.attrs or {}).get("origen_luz")])


class TestDialogoIluminacion(_ProyectoBase):

    def test_dialogo_iluminacion(self):
        from ui.app_window import ARQGenWindow
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            state = dialogo._diseno_state
            state["combo_nivel_ilu"].current(1)   # PB
            state["combo_ilu_lamp"].set("led_panel")
            dialogo._diseno_iluminacion_generar()
            self.assertTrue([n for n in self._nodos()
                             if n.kind == "LUMINAIRE"])
            self.assertIn("LUMINAIRE",
                          state["salida_ilu"].get("1.0", "end"))
            dialogo._diseno_iluminacion_comparativa()
            self.assertIn("Comparativa",
                          state["salida_ilu"].get("1.0", "end"))
            dialogo._diseno_iluminacion_quitar()
            self.assertFalse([n for n in self._nodos()
                              if n.kind == "LUMINAIRE"
                              and (n.attrs or {}).get("origen_luz")])
            # error amable: lux no numérico
            state["var_ilu_lux"].set("malo")
            from ui import app_window as aw
            original = aw.messagebox.showerror
            capturado = {}
            aw.messagebox.showerror = lambda *a, **k: capturado.update(
                {"args": a})
            try:
                dialogo._diseno_iluminacion_generar()
            finally:
                aw.messagebox.showerror = original
            self.assertTrue(capturado, "esperaba el error amable")
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

"""ALARMAS CONTRA INTRUSOS POR LOCALES (v3.19.0): locales protegibles,
generación de PIR + contactos + panel, cobertura con el motor de
intrusión, undo y GUI. Pedido del usuario: «Sistemas de alarmas contra
intrusos (poder elegir qué locales quiero proteger)»."""

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
            self.project_path("alarmas.arqgen"), name="Alarmas")
        self.arq = ArchitectureService(self.context)
        self.n1 = self.arq.create_level("PB", 0.0, 3.0)
        self.sala = self.arq.create_space(
            self.n1.code, "Sala", "LIVING_ROOM",
            [(0, 0), (10, 0), (10, 5), (0, 5)])
        self.dormitorio = self.arq.create_space(
            self.n1.code, "Dormitorio", "BEDROOM",
            [(10, 0), (18, 0), (18, 5), (10, 5)])
        self.trastero = self.arq.create_space(
            self.n1.code, "Trastero", "STORAGE",
            [(0, 5), (4, 5), (4, 8), (0, 8)])
        self.w1 = self.arq.create_wall(self.n1.code, (0, 0), (10, 0))
        self.d1 = self.arq.create_opening("DOOR", self.w1.code, 0.9, 2.1,
                                          offset_m=1.0)
        self.w2 = self.arq.create_wall(self.n1.code, (10, 0), (10, 5))
        self.v1 = self.arq.create_opening("WINDOW", self.w2.code, 1.2, 1.4,
                                          offset_m=1.0, sill_height_m=0.9)
        self.w3 = self.arq.create_wall(self.n1.code, (10, 0), (18, 0))
        self.v2 = self.arq.create_opening("WINDOW", self.w3.code, 1.0, 1.4,
                                          offset_m=2.0, sill_height_m=0.9)

    def _nodos(self):
        return self.context.installations.list("NODE",
                                               self.context.project.id)

    def _sec(self):
        return [n for n in self._nodos()
                if (n.attrs or {}).get("origen_alarma")]


class TestProtegibles(_ProyectoBase):
    """La lista de locales con área, vanos y PIR exigidos."""

    def test_lista_con_vanos_y_pirs(self):
        from domain import alarmas as alr
        datos = alr.locales_protegibles(self.context)
        self.assertEqual(len(datos), 3)
        sala = [d for d in datos if d["code"] == self.sala.code][0]
        self.assertAlmostEqual(sala["area_m2"], 50.0, places=1)
        self.assertEqual(sala["vanos"], 2)          # puerta + ventana
        self.assertEqual(sala["pirs"], 5)           # ceil(50/12)
        trastero = [d for d in datos
                    if d["code"] == self.trastero.code][0]
        self.assertEqual(trastero["vanos"], 0)

    def test_filtro_por_nivel(self):
        from domain import alarmas as alr
        n2 = self.arq.create_level("P1", 3.0, 3.0)
        self.arq.create_space(n2.code, "Alta", "LIVING_ROOM",
                              [(0, 0), (5, 0), (5, 4), (0, 4)])
        datos = alr.locales_protegibles(self.context, nivel_id=n2.id)
        self.assertEqual(len(datos), 1)


class TestGeometriaPerimetro(_ProyectoBase):
    """Vanos sobre el contorno del local (punto en borde con tolerancia)."""

    def test_punto_en_poligono(self):
        from domain import alarmas as alr
        pol = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
        self.assertTrue(alr._punto_en_poligono(2.0, 1.5, pol))
        self.assertFalse(alr._punto_en_poligono(5.0, 1.5, pol))

    def test_centro_del_vano_en_el_muro(self):
        from domain import alarmas as alr
        centro = alr._centro_vano(self.d1,
                                  {m.id: m for m in
                                   self.arq.list_summary("WALL")
                                   and []} or None)
        # con muro real desde el repositorio
        muro = self.context.architecture.get("WALL", self.w1.id)
        centro = alr._centro_vano(self.d1, muro)
        self.assertAlmostEqual(centro[0], 1.0 + 0.45, places=6)
        self.assertAlmostEqual(centro[1], 0.0, places=6)

    def test_vanos_del_perimetro(self):
        from domain import alarmas as alr
        muros = {m.id: m for m in
                 self.context.architecture.list("WALL",
                                                self.context.project.id)}
        vanos = (self.context.architecture.list("DOOR",
                                                self.context.project.id)
                 + self.context.architecture.list(
                     "WINDOW", self.context.project.id))
        propios = alr.vanos_del_perimetro(self.sala, muros, vanos)
        self.assertEqual(len(propios), 2)


class TestGenerarAlarma(_ProyectoBase):
    """El sistema completo sobre los locales elegidos."""

    def test_protege_el_local_elegido(self):
        from domain import alarmas as alr
        r = alr.generar_alarma(self.context, None,
                               space_ids=[self.sala.id])
        self.assertEqual(len(r["zonas"]), 1)
        zona = r["zonas"][0]
        self.assertEqual(zona["pirs"], 5)
        self.assertEqual(zona["contactos"], 2)
        self.assertEqual(zona["vanos"], 2)
        # panel + teclado + sirena interior + PIR + contactos
        self.assertEqual(len(r["creados"]), 3 + 5 + 2)
        self.assertEqual(r["parametros"]["panel_space"], self.sala.code)

    def test_dos_locales_dos_zonas(self):
        from domain import alarmas as alr
        r = alr.generar_alarma(self.context, None,
                               space_ids=[self.sala.id,
                                          self.dormitorio.id])
        self.assertEqual(len(r["zonas"]), 2)
        dorm = [z for z in r["zonas"]
                if "Dormitorio" in z["zona"]][0]
        # su ventana en la fachada + la ventana compartida con la Sala
        # (el muro x=10 es el borde de ambos locales: contacto en ambos)
        self.assertEqual(dorm["contactos"], 2)
        self.assertGreaterEqual(dorm["pirs"], 3)    # 40 m2

    def test_sirena_exterior(self):
        from domain import alarmas as alr
        r = alr.generar_alarma(self.context, None,
                               space_ids=[self.sala.id],
                               sirena_exterior=True)
        sirenas = [n for n in self._sec() if n.kind == "SIREN"]
        self.assertEqual(len(sirenas), 2)
        self.assertEqual(r["parametros"]["sirenas"], 2)

    def test_kinds_del_equipo(self):
        from domain import alarmas as alr
        alr.generar_alarma(self.context, None, space_ids=[self.sala.id])
        kinds = {n.kind for n in self._sec()}
        self.assertIn("INTRUSION_PANEL", kinds)
        self.assertIn("KEYPAD", kinds)
        self.assertIn("SIREN", kinds)
        self.assertIn("PIR", kinds)
        self.assertIn("MAGNETIC_CONTACT", kinds)
        red = [n for n in self.context.installations.list(
            "NETWORK", self.context.project.id)
            if n.system == "INTRUSION"]
        self.assertEqual(len(red), 1)
        self.assertTrue((red[0].metadata or {}).get("origen"))

    def test_sin_seleccion_error(self):
        from core.errors import DomainError
        from domain import alarmas as alr
        with self.assertRaises(DomainError) as cm:
            alr.generar_alarma(self.context, None, space_ids=[])
        self.assertEqual(cm.exception.code, "ARQ-ALR-001")
        with self.assertRaises(DomainError) as cm:
            alr.generar_alarma(self.context, None,
                               space_ids=["fantasma"])
        self.assertEqual(cm.exception.code, "ARQ-ALR-002")

    def test_idempotente_y_quitar(self):
        from domain import alarmas as alr
        r1 = alr.generar_alarma(self.context, None,
                                space_ids=[self.sala.id])
        r2 = alr.generar_alarma(self.context, None,
                                space_ids=[self.sala.id,
                                           self.dormitorio.id])
        self.assertEqual(len(r2["eliminados"]), len(r1["creados"]))
        self.assertEqual(len(self._sec()), len(r2["creados"]))
        bajas = alr.quitar_alarmas(self.context)
        self.assertEqual(len(bajas), len(r2["creados"]))
        self.assertEqual(len(self._sec()), 0)

    def test_undo_de_un_dispositivo(self):
        from app.undo_service import PersistentUndoService
        from domain import alarmas as alr
        r = alr.generar_alarma(self.context, None,
                               space_ids=[self.sala.id])
        self.context.commit()
        self.assertTrue(PersistentUndoService(self.context).undo())
        self.assertEqual(len(self._sec()), len(r["creados"]) - 1)

    def test_cobertura_validada_por_el_motor(self):
        """La zona pequeña queda cubierta y el informe llega limpio."""
        from domain import alarmas as alr
        r = alr.generar_alarma(self.context, None,
                               space_ids=[self.trastero.id])
        zona = r["zonas"][0]
        self.assertEqual(zona["pirs"], 1)
        self.assertTrue(zona["ok"], zona["hallazgos"])

    def test_resumen_y_zonas_cp1252(self):
        from domain import alarmas as alr
        r = alr.generar_alarma(self.context, None,
                               space_ids=[self.sala.id],
                               sirena_exterior=True)
        alr.resumen_texto(r).encode("cp1252")
        lineas = alr.zonas_texto(r)
        self.assertGreaterEqual(len(lineas), 3)
        for linea in lineas:
            linea.encode("cp1252")

    def test_bateria_informe_panel(self):
        from domain import alarmas as alr
        r = alr.generar_alarma(self.context, None,
                               space_ids=[self.sala.id])
        self.assertGreater(r["panel"]["bateria_ah"], 0.0)


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogoAlarmas(_ProyectoBase):

    def test_dialogo_alarmas(self):
        from ui.app_window import ARQGenWindow
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            state = dialogo._diseno_state
            # la lista ya viene llena con los 3 locales
            self.assertEqual(state["lista_alr"].size(), 3)
            # sin selección: error amable
            from ui import app_window as aw
            original = aw.messagebox.showerror
            capturado = {}
            aw.messagebox.showerror = lambda *a, **k: capturado.update(
                {"args": a})
            try:
                dialogo._diseno_alarma_generar()
            finally:
                aw.messagebox.showerror = original
            self.assertTrue(capturado, "esperaba el error amable")
            # selecciona la sala (fila 0) y protege
            state["lista_alr"].selection_set(0)
            state["var_alr_ext"].set(True)
            dialogo._diseno_alarma_generar()
            self.assertTrue(self._sec())
            self.assertIn("Zonas protegidas",
                          state["salida_alr"].get("1.0", "end"))
            dialogo._diseno_alarma_quitar()
            self.assertEqual(len(self._sec()), 0)
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

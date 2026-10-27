"""COTA DE IMPLANTACIÓN DE LA CUBIERTA (v3.17.0).

* La cubierta ya no nace en el PISO del nivel superior (quedaba
  enterrada dentro de la edificación): por defecto se apoya SOBRE el
  top de los muros del nivel cubierto.
* El usuario puede fijar la COTA (altura_base_m, metadata persistida):
  más arriba (ático retranqueado) o más abajo (mansarda), con aviso
  amable si queda por debajo del top de los muros y error ARQ-CUB-002
  por encima de 500 m.
* El 3D respeta la cota (caras_de_cubierta) y la explosión la
  acompaña; QTO, undo y resumen siguen intactos.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from core.errors import DomainError
from domain import cubiertas as cub
from services.architecture_service import ArchitectureService
from ui import view3d as v3


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


class _ProyectoBase(ARQGenTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("cota.arqgen"), name="Cota")
        self.arq = ArchitectureService(self.context)
        self.nivel = self.arq.create_level("Planta 1", 0.0, 3.0)

    def tearDown(self) -> None:
        try:
            self.context.close()
        except Exception:  # noqa: BLE001
            pass
        super().tearDown()

    def _edificio(self, ancho=12.0, fondo=6.0):
        self.arq.create_space(
            self.nivel.code, "Sala", "LIVING_ROOM",
            [(0.0, 0.0), (ancho, 0.0), (ancho, fondo), (0.0, fondo)])

    def _zmin_caras(self, roof, z_extra=0.0):
        nivel = v3.Nivel3D(self.nivel.id, "Planta 1", 0.0, 3.0)
        caras = v3.caras_de_cubierta(roof, nivel, z_extra, v3.Camara3D())
        return caras, min(p[2] for c in caras for p in c.puntos)


class TestCotaPorDefecto(_ProyectoBase):

    def test_sin_cota_nace_sobre_el_top_de_los_muros(self):
        self._edificio()
        cub.generar_cubierta(self.context, None, tipologia="dos_aguas",
                             pendiente_pct=30.0, con_qto=False)
        roof = cub.cubierta_actual(self.context)
        caras, zmin = self._zmin_caras(roof)
        self.assertTrue(caras)
        self.assertAlmostEqual(zmin, 3.0, places=6)
        self.assertNotIn("altura_base_m", roof.metadata or {})

    def test_plana_tambien_se_apoya_en_el_top(self):
        self._edificio()
        cub.generar_cubierta(self.context, None,
                             tipologia="plana_transitable",
                             con_qto=False)
        roof = cub.cubierta_actual(self.context)
        _caras, zmin = self._zmin_caras(roof)
        self.assertAlmostEqual(zmin, 3.0, places=6)

    def test_cota_cero_o_negativa_es_auto(self):
        self._edificio()
        for cota in (0.0, -1.5):
            resumen = cub.generar_cubierta(
                self.context, None, tipologia="dos_aguas",
                altura_base_m=cota, con_qto=False)
            self.assertIsNone(resumen["parametros"]["altura_base_m"])
            roof = cub.cubierta_actual(self.context)
            _caras, zmin = self._zmin_caras(roof)
            self.assertAlmostEqual(zmin, 3.0, places=6)

    def test_nivel_elevado_suma_su_cota(self):
        self._edificio()
        self.arq.create_level("Planta 2", 3.2, 3.0)
        self.arq.create_space(
            "Planta 2", "Dormitorio", "BEDROOM",
            [(0.0, 0.0), (8.0, 0.0), (8.0, 5.0), (0.0, 5.0)])
        cub.generar_cubierta(self.context, None, tipologia="dos_aguas",
                             con_qto=False)
        roof = cub.cubierta_actual(self.context)
        # el nivel superior (3.2 + 3.0) es el que se cubre
        nivel = v3.Nivel3D(roof.level_id, "Planta 2", 3.2, 3.0)
        caras = v3.caras_de_cubierta(roof, nivel, 0.0, v3.Camara3D())
        zmin = min(p[2] for c in caras for p in c.puntos)
        self.assertAlmostEqual(zmin, 6.2, places=6)


class TestCotaExplicita(_ProyectoBase):

    def test_cota_pedida_se_guarda_y_el_3d_la_respeta(self):
        self._edificio()
        resumen = cub.generar_cubierta(
            self.context, None, tipologia="dos_aguas", pendiente_pct=30.0,
            altura_base_m=4.2, con_qto=False)
        self.assertAlmostEqual(
            resumen["parametros"]["altura_base_m"], 4.2, places=6)
        roof = cub.cubierta_actual(self.context)
        self.assertAlmostEqual(
            float(roof.metadata["altura_base_m"]), 4.2, places=6)
        _caras, zmin = self._zmin_caras(roof)
        self.assertAlmostEqual(zmin, 4.2, places=6)

    def test_cota_por_debajo_avisa_y_se_aplica(self):
        self._edificio()
        resumen = cub.generar_cubierta(
            self.context, None, tipologia="dos_aguas",
            altura_base_m=2.0, con_qto=False)
        self.assertTrue(any("por debajo" in a
                            for a in resumen["avisos"]), resumen["avisos"])
        roof = cub.cubierta_actual(self.context)
        _caras, zmin = self._zmin_caras(roof)
        self.assertAlmostEqual(zmin, 2.0, places=6)

    def test_cota_por_encima_no_avisa(self):
        self._edificio()
        resumen = cub.generar_cubierta(
            self.context, None, tipologia="dos_aguas",
            altura_base_m=3.5, con_qto=False)
        self.assertFalse(any("por debajo" in a
                             for a in resumen["avisos"]))

    def test_cota_mayor_de_500_da_error_propio(self):
        self._edificio()
        with self.assertRaises(DomainError) as ctx:
            cub.generar_cubierta(self.context, None,
                                 tipologia="dos_aguas",
                                 altura_base_m=501.0, con_qto=False)
        self.assertEqual(ctx.exception.code, "ARQ-CUB-002")

    def test_la_explosion_acompana_a_la_cubierta(self):
        self._edificio()
        cub.generar_cubierta(self.context, None, tipologia="dos_aguas",
                             altura_base_m=4.2, con_qto=False)
        roof = cub.cubierta_actual(self.context)
        _caras, zmin = self._zmin_caras(roof, z_extra=1.5)
        self.assertAlmostEqual(zmin, 5.7, places=6)

    def test_cota_persiste_en_el_proyecto(self):
        self._edificio()
        cub.generar_cubierta(self.context, None, tipologia="dos_aguas",
                             altura_base_m=4.2, con_qto=False)
        self.context.commit()
        ruta = self.context.db_path
        self.context.close()
        self.context = self.application.open_project(ruta)
        roof = cub.cubierta_actual(self.context)
        self.assertAlmostEqual(
            float(roof.metadata["altura_base_m"]), 4.2, places=6)


class TestAyudanteCota(_ProyectoBase):

    def test_metadata_manda_sobre_el_top(self):
        self._edificio()
        roof = cub.cubierta_actual(self.context)
        self.assertIsNone(roof)
        class _Falsa:
            metadata = {"altura_base_m": 7.25}
        self.assertAlmostEqual(
            cub.cota_base_cubierta(_Falsa(), 0.0, 3.0), 7.25, places=9)

    def test_sin_metadata_devuelve_el_top_de_los_muros(self):
        class _Falsa:
            metadata = {}
        self.assertAlmostEqual(
            cub.cota_base_cubierta(_Falsa(), 1.2, 3.0), 4.2, places=9)

    def test_metadata_basura_cae_en_el_top(self):
        class _Falsa:
            metadata = {"altura_base_m": "n/d"}
        self.assertAlmostEqual(
            cub.cota_base_cubierta(_Falsa(), 0.0, 3.0), 3.0, places=9)


class TestResumenYQTO(_ProyectoBase):

    def test_resumen_menciona_la_base_y_es_cp1252(self):
        self._edificio()
        resumen = cub.generar_cubierta(
            self.context, None, tipologia="dos_aguas", pendiente_pct=30.0,
            altura_base_m=4.2)
        texto = cub.resumen_texto(resumen)
        texto.encode("cp1252")
        self.assertIn("base a 4.20 m", texto)
        self.assertIsInstance(resumen["qto"], dict)

    def test_resumen_sin_cota_no_cambia(self):
        texto = cub.resumen_texto({
            "parametros": {"tipologia": "dos_aguas",
                           "material": "teja_curva",
                           "pendiente_pct": 30.0,
                           "estructura": "madera"},
            "creados": ["ARQ-ROOF-001"], "eliminados": [],
            "avisos": [], "qto": {}})
        texto.encode("cp1252")
        self.assertNotIn("base a", texto)

    def test_undo_devuelve_al_estado_anterior(self):
        from app.undo_service import PersistentUndoService
        self._edificio()
        antes = len(self.context.architecture.list(
            "ROOF", self.context.project.id))
        cub.generar_cubierta(self.context, None, tipologia="dos_aguas",
                             altura_base_m=4.2, con_qto=False)
        self.context.commit()
        resumen_undo = PersistentUndoService(self.context).undo()
        self.assertTrue(resumen_undo.get("ok", True), resumen_undo)
        ahora = len(self.context.architecture.list(
            "ROOF", self.context.project.id))
        self.assertEqual(ahora, antes)


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogoCubiertasConCota(_ProyectoBase):

    def test_dialogo_aplica_la_cota(self):
        from ui.app_window import ARQGenWindow
        nivel = self.arq.create_level("Planta GUI", 0.0, 3.0)
        self.arq.create_space(nivel.code, "Sala", "LIVING_ROOM",
                              [(0, 0), (5, 0), (5, 4), (0, 4)])
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            state = dialogo._diseno_state
            valores = list(state["combo_tip"]["values"])
            state["combo_tip"].current(valores.index("dos_aguas"))
            state["var_cota"].set("3.8")
            dialogo._diseno_cubierta_generar()
            roofs = self.context.architecture.list(
                "ROOF", self.context.project.id)
            self.assertEqual(len(roofs), 1)
            self.assertAlmostEqual(
                float(roofs[0].metadata["altura_base_m"]), 3.8, places=6)
            texto = state["salida_cub"].get("1.0", "end")
            self.assertIn("3.8 m", texto)
            state["var_cota"].set("número malo")
            from ui import app_window as aw
            original = aw.messagebox.showerror
            capturado = {}
            aw.messagebox.showerror = lambda *a, **k: capturado.update(
                {"args": a})
            try:
                dialogo._diseno_cubierta_generar()
            finally:
                aw.messagebox.showerror = original
            self.assertTrue(capturado, "esperaba el error amable")
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

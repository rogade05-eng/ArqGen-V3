"""ASCENSORES SEGÚN NEUFERT (v3.18.0).

* Catálogo del libro: capacidad (kg/personas), cabina, hueco y puerta
  central para pasajeros, hospital, montacargas y panorámico; foso y
  paso libre superior por velocidad; recomendación de cantidad.
* Colocación real: dentro del núcleo/escalera con la puerta al vecino
  más cercano, adosado a la fachada pedida o en x/y explícitos.
* Caminos oficiales: auditoría, undo persistente, QTO (hueco,
  recorrido), persistencia y resumen cp1252; 3D del hueco con cabina
  y puerta; GUI del taller de diseño.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from core.errors import DomainError
from domain import ascensores as asc
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
            self.project_path("ascensores.arqgen"), name="Ascensores")
        self.arq = ArchitectureService(self.context)
        self.n1 = self.arq.create_level("PB", 0.0, 3.0)
        self.n2 = self.arq.create_level("P1", 3.0, 3.0)
        # núcleo de 3.0 x 4.2 (el del asistente) + sala al este
        self.arq.create_space(self.n1.code, "Nucleo", "CORE",
                              [(0, 0), (3, 0), (3, 4.2), (0, 4.2)])
        self.arq.create_space(self.n1.code, "Sala", "LIVING_ROOM",
                              [(3, 0), (9, 0), (9, 4.2), (3, 4.2)])
        self.arq.create_space(self.n2.code, "Sala1", "LIVING_ROOM",
                              [(3, 0), (9, 0), (9, 4.2), (3, 4.2)])

    def tearDown(self) -> None:
        try:
            self.context.close()
        except Exception:  # noqa: BLE001
            pass
        super().tearDown()

    def _hueco(self, **kwargs):
        resumen = asc.generar_ascensor(self.context, None, **kwargs)
        self.context.commit()
        return resumen

    def _ascensores(self):
        return self.context.architecture.list(
            "ELEVATOR", self.context.project.id)


class TestCatalogoNeufert(_ProyectoBase):

    def test_tabla_pasajeros_cubre_de_6_a_26_personas(self):
        personas = [p for _kg, p, *_r in asc.PASAJEROS]
        self.assertEqual(personas, [6, 8, 10, 13, 17, 21, 26])

    def test_dimensiones_del_hueco_630(self):
        dims = asc.dimensiones_hueco("pasajeros", 630)
        self.assertEqual(dims["personas"], 8)
        self.assertEqual(
            (dims["cabina_ancho_m"], dims["cabina_fondo_m"]), (1.60, 1.40))
        self.assertEqual(
            (dims["hueco_ancho_m"], dims["hueco_fondo_m"]), (1.80, 2.05))
        self.assertEqual(dims["puerta_m"], 0.80)

    def test_hospital_lleva_camillas_y_puerta_de_1_20(self):
        dims = asc.dimensiones_hueco("hospital", 1275)
        self.assertEqual((dims["cabina_ancho_m"], dims["cabina_fondo_m"]),
                         (2.40, 2.40))
        self.assertEqual(dims["puerta_m"], 1.20)

    def test_capacidad_inexistente_error_propio(self):
        with self.assertRaises(DomainError) as ctx:
            asc.dimensiones_hueco("pasajeros", 777)
        self.assertEqual(ctx.exception.code, "ARQ-ELE-001")

    def test_tipo_desconocido_error_propio(self):
        with self.assertRaises(DomainError) as ctx:
            asc.dimensiones_hueco("cohete", 630)
        self.assertEqual(ctx.exception.code, "ARQ-ELE-002")

    def test_capacidad_siguiente_por_personas_y_por_kg(self):
        self.assertEqual(asc.capacidad_siguiente("pasajeros", 9),
                         (800, 10))
        self.assertEqual(asc.capacidad_siguiente("montacargas", 700),
                         (1000, 0))

    def test_velocidad_y_foso_por_recursos(self):
        self.assertEqual(asc.velocidad_para(2, 3.0), 0.63)
        self.assertEqual(asc.velocidad_para(5, 3.0), 1.0)
        self.assertEqual(asc.velocidad_para(9, 3.0), 1.6)
        foso, paso = asc.foso_y_paso(10, 3.0)
        self.assertEqual((foso, paso), (asc.FOSO_BASE_M,
                                        asc.RECORRIDO_ALTO_M))

    def test_recomendar_cantidad_usa_el_factor_del_uso(self):
        self.assertEqual(
            asc.recomendar_cantidad(150, 6, "Oficina")["cantidad"], 1)
        doble = asc.recomendar_cantidad(150, 8, "Oficina")
        self.assertEqual(doble["cantidad"], 2)
        self.assertTrue(any("segundo" in n for n in doble["notas"]))
        rec = asc.recomendar_cantidad(0, 8, "Vivienda")
        self.assertEqual(rec["cantidad"], 1)
        self.assertTrue(any("accesibilidad" in n for n in rec["notas"]))

    def test_tabla_texto_cp1252(self):
        for linea in asc.tabla_texto("pasajeros"):
            linea.encode("cp1252")


class TestGeneracionAscensor(_ProyectoBase):

    def test_hueco_dentro_del_nucleo_con_puerta_al_vecino(self):
        resumen = self._hueco()
        self.assertEqual(len(resumen["creados"]), 1)
        p = resumen["parametros"]
        self.assertEqual(p["modo"], "nucleo")
        self.assertEqual(p["puerta_lado"], "E")   # la sala está al este
        self.assertEqual(p["hueco"], (1.80, 2.05))
        entidad = self._ascensores()[0]
        self.assertEqual(entidad.code, resumen["creados"][0])
        self.assertEqual(entidad.tipo, "pasajeros")
        self.assertEqual(entidad.capacidad_kg, 630)
        self.assertIn("nucleo", entidad.metadata["modo"])

    def test_hueco_central_en_el_nucleo(self):
        self._hueco()
        entidad = self._ascensores()[0]
        self.assertAlmostEqual(entidad.x, 1.5, places=4)
        self.assertAlmostEqual(entidad.y, 2.1, places=4)

    def test_personas_eligen_la_capacidad(self):
        p = self._hueco(personas=14)["parametros"]
        self.assertEqual(p["capacidad_kg"], 1275)
        self.assertEqual(p["personas"], 17)

    def test_hospital_desde_personas(self):
        p = self._hueco(tipo="hospital", personas=15)["parametros"]
        self.assertEqual(p["capacidad_kg"], 1275)
        self.assertEqual(p["puerta_m"], 1.20)

    def test_montacargas_sin_personas(self):
        p = self._hueco(tipo="montacargas", personas=500)["parametros"]
        self.assertEqual(p["capacidad_kg"], 500)
        self.assertEqual(p["personas"], 0)

    def test_niveles_servidos_y_altura_total(self):
        p = self._hueco()["parametros"]
        self.assertEqual(p["niveles_servidos"], 2)
        self.assertAlmostEqual(p["altura_total_m"], 6.0, places=3)
        self.assertAlmostEqual(p["velocidad_m_s"], 0.63, places=3)
        self.assertAlmostEqual(p["foso_m"], asc.FOSO_BASE_M, places=3)

    def test_x_y_explicitos_se_respetan(self):
        p = self._hueco(x=15.0, y=2.0)["parametros"]
        self.assertEqual(p["modo"], "manual")
        self.assertAlmostEqual(p["x"], 15.0, places=4)
        self.assertAlmostEqual(p["y"], 2.0, places=4)

    def test_sin_nucleo_se_adosa_a_la_fachada_sur(self):
        for espacio in self.context.architecture.list(
                "SPACE", self.context.project.id):
            self.arq.delete_entity("SPACE", espacio.id)
        self.arq.create_space(self.n1.code, "Sala", "LIVING_ROOM",
                              [(0, 0), (8, 0), (8, 5), (0, 5)])
        resumen = self._hueco()
        p = resumen["parametros"]
        self.assertEqual(p["modo"], "fachada")
        self.assertEqual(p["puerta_lado"], "N")   # mira al edificio
        entidad = self._ascensores()[0]
        self.assertLess(entidad.y, 0.0)           # fuera del recinto
        self.assertTrue(any("ADOSADO" in a.upper()
                            for a in resumen["avisos"]))

    def test_fachada_pedida_este(self):
        for espacio in self.context.architecture.list(
                "SPACE", self.context.project.id):
            self.arq.delete_entity("SPACE", espacio.id)
        self.arq.create_space(self.n1.code, "Sala", "LIVING_ROOM",
                              [(0, 0), (8, 0), (8, 5), (0, 5)])
        p = self._hueco(fachada="E")["parametros"]
        self.assertEqual(p["puerta_lado"], "O")
        entidad = self._ascensores()[0]
        self.assertGreater(entidad.x, 8.0)

    def test_idempotente_no_duplica(self):
        self._hueco()
        self._hueco(tipo="hospital", personas=15)
        self.assertEqual(len(self._ascensores()), 1)

    def test_qto_del_hueco_y_del_recuento(self):
        from services.quantity_service import QuantityService
        self._hueco()
        QuantityService(self.context).compute_all()
        renglones = {(r["object_type"], r["formula_code"]):
                     r["final_quantity"]
                     for r in self.context.quantities_repo.all(
                         self.context.project.id)}
        self.assertEqual(renglones[("ELEVATOR", "ELEVATOR_COUNT")], 1.0)
        self.assertAlmostEqual(
            renglones[("ELEVATOR", "ELEVATOR_SHAFT_AREA")],
            1.8 * 2.05, places=3)
        self.assertAlmostEqual(
            renglones[("ELEVATOR", "ELEVATOR_TRAVEL")], 6.0, places=3)

    def test_undo_persistente_lo_quita(self):
        antes = len(self._ascensores())
        self._hueco()
        self.assertEqual(len(self._ascensores()), antes + 1)
        from app.undo_service import PersistentUndoService
        resumen_undo = PersistentUndoService(self.context).undo()
        self.assertTrue(resumen_undo.get("ok", True), resumen_undo)
        self.assertEqual(len(self._ascensores()), antes)

    def test_quitar_ascensores_solo_los_generados(self):
        self._hueco()
        bajas = asc.quitar_ascensores(self.context)
        self.context.commit()
        self.assertEqual(len(bajas), 1)
        self.assertEqual(len(self._ascensores()), 0)

    def test_persistencia_tras_reabrir(self):
        self._hueco(tipo="hospital", personas=15)
        self.context.close()
        self.context = self.application.open_project(
            self.project_path("ascensores.arqgen"))
        ascensores = self.context.architecture.list(
            "ELEVATOR", self.context.project.id)
        self.assertEqual(len(ascensores), 1)
        self.assertEqual(ascensores[0].tipo, "hospital")
        self.assertEqual(ascensores[0].metadata["puerta_lado"], "E")

    def test_resumen_cp1252(self):
        resumen = self._hueco()
        texto = asc.resumen_texto(resumen)
        texto.encode("cp1252")
        self.assertIn("630 kg", texto)
        self.assertIn("1.80 x 2.05", texto)


class TestAscensor3D(_ProyectoBase):

    def test_caras_del_hueco_cabina_y_puerta(self):
        self._hueco()
        entidad = self._ascensores()[0]
        caras = v3.caras_de_ascensor(entidad, 0.0, 0.0, v3.Camara3D())
        kinds = [c.kind for c in caras]
        self.assertIn("ascensor", kinds)
        self.assertIn("cabina", kinds)
        self.assertIn("vano", kinds)
        # el hueco sube la altura servida (6.0 m)
        self.assertAlmostEqual(
            max(p[2] for c in caras if c.kind == "ascensor"
                for p in c.puntos), 6.0, places=3)
        # la puerta mira al este (la sala está al este del núcleo)
        puerta = next(c for c in caras if c.kind == "vano")
        self.assertAlmostEqual(
            max(p[0] for p in puerta.puntos),
            entidad.x + entidad.depth_m / 2.0, places=3)

    def test_la_explosion_acompana_al_hueco(self):
        self._hueco()
        entidad = self._ascensores()[0]
        base = v3.caras_de_ascensor(entidad, 0.0, 0.0, v3.Camara3D())
        alto = v3.caras_de_ascensor(entidad, 0.0, 1.5, v3.Camara3D())
        self.assertAlmostEqual(
            min(p[2] for c in base for p in c.puntos), 0.0, places=6)
        self.assertAlmostEqual(
            min(p[2] for c in alto for p in c.puntos), 1.5, places=6)

    def test_construir_caras_incluye_el_hueco(self):
        self._hueco()
        modelo, _avisos = v3.modelo3d_desde_proyecto(self.context)
        self.assertEqual(len(modelo.ascensores), 1)
        caras = v3.construir_caras(modelo, v3.Camara3D())
        self.assertTrue(any(c.kind == "ascensor" for c in caras))


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogoAscensores(_ProyectoBase):

    def test_dialogo_genera_y_quita(self):
        from ui.app_window import ARQGenWindow
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            state = dialogo._diseno_state
            # pestañas nuevas presentes
            pestañas = [state["notebook"].tab(i, "text")
                        for i in range(state["notebook"].index("end"))]
            self.assertTrue(any("Ascensores" in p for p in pestañas))
            self.assertTrue(any("Fachada" in p for p in pestañas))
            state["var_asc_personas"].set("14")
            dialogo._diseno_ascensores_generar()
            ascensores = self._ascensores()
            self.assertEqual(len(ascensores), 1)
            self.assertEqual(ascensores[0].capacidad_kg, 1275)
            texto = state["salida_asc"].get("1.0", "end")
            self.assertIn("1275 kg", texto)
            self.assertIn("kg", texto)   # tabla del catálogo incluida
            dialogo._diseno_ascensores_quitar()
            self.assertEqual(len(self._ascensores()), 0)
            # error amable con personas no numéricas
            state["var_asc_personas"].set("mucho")
            from ui import app_window as aw
            original = aw.messagebox.showerror
            capturado = {}
            aw.messagebox.showerror = lambda *a, **k: capturado.update(
                {"args": a})
            try:
                dialogo._diseno_ascensores_generar()
            finally:
                aw.messagebox.showerror = original
            self.assertTrue(capturado, "esperaba el error amable")
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

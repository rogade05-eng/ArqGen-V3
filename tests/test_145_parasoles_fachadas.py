"""PARASOLES Y PIELES EXTERIORES DE FACHADA (v3.18.0).

* Parasoles por orientación: lamas horizontales al SUR, aletas
  verticales a ESTE y OESTE, NORTÉ sin parasol (aviso amable); tipo
  explícito manda en todos los lados; materiales, vuelo, separación y
  banda vertical propias; lamas móviles con su ángulo.
* Pieles exteriores modernas: doble piel de vidrio, celosía de
  madera, malla metálica, baguettes de terracota, panel perforado,
  jardín vertical, GRC y policarbonato; el ESTILO arquitectónico
  sugiere en «auto»; cámara ventilada acotada (ARQ-FAC-003).
* Caminos oficiales: QTO (lamas, sombra, superficie vestida), undo
  persistente, persistencia, resúmenes cp1252, 3D (lamas, aletas,
  plano de piel con su retícula) y GUI del taller de diseño.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from core.errors import DomainError
from domain import fachadas as fac
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
            self.project_path("fachada.arqgen"), name="Fachada")
        self.arq = ArchitectureService(self.context)
        self.n1 = self.arq.create_level("PB", 0.0, 3.0)
        self.n2 = self.arq.create_level("P1", 3.0, 3.0)
        # recinto 12 x 6 en PB; solo 6 x 6 en P1 (ala retranqueada)
        self.arq.create_space(self.n1.code, "Sala", "LIVING_ROOM",
                              [(0, 0), (12, 0), (12, 6), (0, 6)])
        self.arq.create_space(self.n2.code, "Sala1", "LIVING_ROOM",
                              [(0, 0), (6, 0), (6, 6), (0, 6)])

    def tearDown(self) -> None:
        try:
            self.context.close()
        except Exception:  # noqa: BLE001
            pass
        super().tearDown()

    def _parasoles(self, **kwargs):
        resumen = fac.generar_parasoles(self.context, None, **kwargs)
        self.context.commit()
        return resumen

    def _piel(self, **kwargs):
        resumen = fac.generar_piel(self.context, None, **kwargs)
        self.context.commit()
        return resumen

    def _lista(self, tipo):
        return self.context.architecture.list(
            tipo, self.context.project.id)


class TestLineaFachada(_ProyectoBase):

    def test_lados_del_recinto(self):
        recinto = (0.0, 0.0, 12.0, 6.0)
        self.assertEqual(fac.linea_fachada(recinto, "S"),
                         (6.0, 0.0, 0.0, 12.0))
        self.assertEqual(fac.linea_fachada(recinto, "N"),
                         (6.0, 6.0, 0.0, 12.0))
        self.assertEqual(fac.linea_fachada(recinto, "E"),
                         (12.0, 3.0, 90.0, 6.0))
        self.assertEqual(fac.linea_fachada(recinto, "O"),
                         (0.0, 3.0, 90.0, 6.0))

    def test_lados_pedidos_valida(self):
        self.assertEqual(fac.lados_pedidos("auto"),
                         ["N", "S", "E", "O"])
        self.assertEqual(fac.lados_pedidos("S,E"), ["S", "E"])
        with self.assertRaises(DomainError) as ctx:
            fac.lados_pedidos("X")
        self.assertEqual(ctx.exception.code, "ARQ-FAC-002")


class TestParasoles(_ProyectoBase):

    def test_auto_por_orientacion(self):
        resumen = self._parasoles()
        lados = {d["lado"]: d for d in
                 resumen["parametros"]["lados_resueltos"]}
        self.assertEqual(lados["S"]["tipo"], "horizontal")
        self.assertEqual(lados["E"]["tipo"], "vertical")
        self.assertEqual(lados["O"]["tipo"], "vertical")
        self.assertNotIn("N", lados)
        self.assertTrue(any("norte" in a for a in resumen["avisos"]))
        entidades = {e.side: e for e in self._lista("PARASOL")}
        self.assertEqual(len(entidades), 3)

    def test_lamas_horizontales_apiladas_en_el_sur(self):
        # por defecto el parasol viste el nivel SUPERIOR con espacios
        # (el P1 de 6 x 6): el sol pega fuerte arriba
        self._parasoles(lados="S")
        parasol = self._lista("PARASOL")[0]
        self.assertEqual(parasol.tipo, "horizontal")
        self.assertAlmostEqual(parasol.length_m, 6.0, places=3)
        self.assertAlmostEqual(parasol.profundidad_m, 0.50, places=3)
        # banda 0-3 m con separación 0.6: 5 lamas
        self.assertEqual(parasol.n_lamas, 5)
        self.assertAlmostEqual(parasol.y, -0.30, places=3)  # fuera
        meta = parasol.metadata
        self.assertEqual(meta["n_lamas_horizontales"], 5)
        self.assertEqual(meta["n_lamas_verticales"], 0)

    def test_nivel_pedido_mide_su_propia_fachada(self):
        self._parasoles(lados="S", nivel_id=self.n1.id)
        parasol = self._lista("PARASOL")[0]
        self.assertEqual(parasol.level_id, self.n1.id)
        self.assertAlmostEqual(parasol.length_m, 12.0, places=3)
        self.assertEqual(parasol.n_lamas, 5)

    def test_aletas_verticales_repartidas_al_este(self):
        self._parasoles(lados="E")
        parasol = self._lista("PARASOL")[0]
        self.assertEqual(parasol.tipo, "vertical")
        self.assertAlmostEqual(parasol.length_m, 6.0, places=3)
        # 6.0 m / 0.6 m = 10 aletas
        self.assertEqual(parasol.n_lamas, 10)
        self.assertEqual(parasol.metadata["n_lamas_verticales"], 10)
        self.assertGreater(parasol.x, 6.0)   # fuera de la fachada este

    def test_tipo_explicito_manda_en_todos_los_lados(self):
        self._parasoles(tipo="mixto", lados="S,N")
        tipos = {e.side: e.tipo for e in self._lista("PARASOL")}
        self.assertEqual(tipos, {"S": "mixto", "N": "mixto"})
        sur = next(e for e in self._lista("PARASOL") if e.side == "S")
        self.assertEqual(sur.metadata["n_lamas_horizontales"], 5)
        self.assertEqual(sur.metadata["n_lamas_verticales"], 10)

    def test_lamas_moviles_guardan_el_angulo(self):
        self._parasoles(tipo="lamas_moviles", lados="S")
        parasol = self._lista("PARASOL")[0]
        self.assertAlmostEqual(parasol.metadata["angulo_deg"], 45.0,
                               places=6)

    def test_material_y_valores_propios(self):
        self._parasoles(lados="S", material="madera",
                        profundidad_m=0.8, separacion_m=0.5)
        parasol = self._lista("PARASOL")[0]
        self.assertEqual(parasol.material, "madera")
        self.assertAlmostEqual(parasol.profundidad_m, 0.8, places=3)
        self.assertAlmostEqual(parasol.separacion_m, 0.5, places=3)
        self.assertEqual(parasol.metadata["material_etiqueta"],
                         "madera tratada")

    def test_banda_vertical_recortada(self):
        self._parasoles(lados="S", altura_inicio_m=1.0, altura_fin_m=2.0)
        parasol = self._lista("PARASOL")[0]
        self.assertAlmostEqual(parasol.altura_inicio_m, 1.0, places=3)
        self.assertAlmostEqual(parasol.altura_fin_m, 2.0, places=3)
        self.assertEqual(parasol.metadata["n_lamas_horizontales"], 2)

    def test_parametros_fuera_de_rango_error_propio(self):
        with self.assertRaises(DomainError) as ctx:
            fac.resolver_parasol(profundidad_m=5.0)
        self.assertEqual(ctx.exception.code, "ARQ-FAC-003")
        with self.assertRaises(DomainError) as ctx:
            fac.resolver_parasol(tipo="griego")
        self.assertEqual(ctx.exception.code, "ARQ-FAC-002")

    def test_idempotente_y_separable_de_la_piel(self):
        self._parasoles()
        self._piel(lados="S")
        self._parasoles(lados="S", material="madera")
        self.assertEqual(len(self._lista("PARASOL")), 1)
        self.assertEqual(len(self._lista("SKIN")), 1)

    def test_quitar_solo_parasoles(self):
        self._parasoles()
        self._piel(lados="S")
        bajas = fac.quitar_parasoles(self.context)
        self.context.commit()
        self.assertEqual(len(bajas), 3)
        self.assertEqual(len(self._lista("PARASOL")), 0)
        self.assertEqual(len(self._lista("SKIN")), 1)

    def test_qto_lamas_y_sombra(self):
        from services.quantity_service import QuantityService
        self._parasoles(lados="S", material="madera")
        QuantityService(self.context).compute_all()
        renglones = {(r["object_type"], r["formula_code"]):
                     r["final_quantity"]
                     for r in self.context.quantities_repo.all(
                         self.context.project.id)}
        self.assertEqual(renglones[("PARASOL", "PARASOL_COUNT")], 1.0)
        self.assertAlmostEqual(
            renglones[("PARASOL", "PARASOL_LENGTH")], 5 * 6.0, places=3)
        self.assertAlmostEqual(
            renglones[("PARASOL", "PARASOL_SHADE_AREA")],
            5 * 6.0 * 0.5, places=3)

    def test_undo_persistente(self):
        antes = len(self._lista("PARASOL"))
        self._parasoles(lados="S")
        self.assertEqual(len(self._lista("PARASOL")), antes + 1)
        from app.undo_service import PersistentUndoService
        resumen_undo = PersistentUndoService(self.context).undo()
        self.assertTrue(resumen_undo.get("ok", True), resumen_undo)
        self.assertEqual(len(self._lista("PARASOL")), antes)

    def test_resumen_cp1252(self):
        resumen = self._parasoles()
        fac.resumen_texto_parasoles(resumen).encode("cp1252")


class TestPieles(_ProyectoBase):

    def test_estilo_sugiere_la_piel(self):
        self.assertEqual(fac.ESTILO_PIEL["Racionalista"],
                         "doble_piel_vidrio")
        self.assertEqual(fac.ESTILO_PIEL["Sostenible (bioclimático)"],
                         "celosia_madera")
        self.assertEqual(fac.ESTILO_PIEL["High-tech"], "malla_metalica")

    def test_doble_piel_completa_desde_el_nivel_base(self):
        resumen = self._piel(lados="S")
        piel = self._lista("SKIN")[0]
        self.assertEqual(piel.tipo, "doble_piel_vidrio")
        self.assertEqual(piel.material, "vidrio")
        self.assertAlmostEqual(piel.length_m, 12.0, places=3)
        # la piel nace en PB y sube hasta el top (6.0 m)
        self.assertAlmostEqual(piel.altura_m, 6.0, places=3)
        self.assertAlmostEqual(piel.y, -0.60, places=3)  # cámara 0.60
        self.assertAlmostEqual(
            piel.metadata["apertura_pct"],
            fac.APERTURA_POR_PIEL["doble_piel_vidrio"], places=3)
        self.assertEqual(piel.metadata["niveles_cubiertos"], 2)
        self.assertEqual(
            resumen["parametros"]["lados_resueltos"][0]["length_m"], 12.0)

    def test_auto_sin_estilo_uses_doble_piel(self):
        p = self._piel()["parametros"]
        self.assertEqual(p["tipo"], "doble_piel_vidrio")

    def test_terracota_por_lado_este(self):
        self._piel(lados="E", tipo="baguette_terracota")
        piel = self._lista("SKIN")[0]
        self.assertEqual(piel.material, "ceramica")
        self.assertGreater(piel.x, 12.0)

    def test_camara_ventilada_acotada(self):
        with self.assertRaises(DomainError) as ctx:
            fac.resolver_piel(separacion_m=3.0)
        self.assertEqual(ctx.exception.code, "ARQ-FAC-003")
        p = self._piel(lados="S", separacion_m=1.2)["parametros"]
        self.assertAlmostEqual(p["separacion_m"], 1.2, places=3)

    def test_ninguno_solo_retira(self):
        self._piel(lados="S")
        resumen = self._piel(tipo="ninguno")
        self.assertEqual(len(self._lista("SKIN")), 0)
        self.assertEqual(len(resumen["creados"]), 0)

    def test_idempotente(self):
        self._piel(lados="S")
        self._piel(lados="S,N", tipo="celosia_madera")
        pieles = self._lista("SKIN")
        self.assertEqual(len(pieles), 2)
        self.assertTrue(all(e.tipo == "celosia_madera" for e in pieles))

    def test_qto_superficie_vestida(self):
        from services.quantity_service import QuantityService
        self._piel(lados="S")
        QuantityService(self.context).compute_all()
        renglones = {(r["object_type"], r["formula_code"]):
                     r["final_quantity"]
                     for r in self.context.quantities_repo.all(
                         self.context.project.id)}
        self.assertAlmostEqual(
            renglones[("SKIN", "SKIN_AREA")], 12.0 * 6.0, places=3)
        self.assertAlmostEqual(
            renglones[("SKIN", "SKIN_LENGTH")], 12.0, places=3)

    def test_persistencia_tras_reabrir(self):
        self._piel(lados="S", tipo="jardin_vertical", separacion_m=0.9)
        self.context.close()
        self.context = self.application.open_project(
            self.project_path("fachada.arqgen"))
        pieles = self.context.architecture.list(
            "SKIN", self.context.project.id)
        self.assertEqual(len(pieles), 1)
        self.assertEqual(pieles[0].tipo, "jardin_vertical")
        self.assertAlmostEqual(pieles[0].separacion_m, 0.9, places=6)

    def test_resumen_cp1252(self):
        resumen = self._piel(lados="S")
        fac.resumen_texto_piel(resumen).encode("cp1252")


class TestFachada3D(_ProyectoBase):

    def test_caras_del_parasol_sur(self):
        self._parasoles(lados="S", material="madera")
        parasol = self._lista("PARASOL")[0]
        caras = v3.caras_de_parasol(parasol, 0.0, 0.0, v3.Camara3D())
        kinds = {c.kind for c in caras}
        self.assertEqual(kinds, {"parasol"})
        # 5 lamas apiladas: la última culmina a 0.6*4 + ancho/2
        zs = [p[2] for c in caras for p in c.puntos]
        self.assertGreaterEqual(min(zs), -1e-9)
        self.assertAlmostEqual(max(zs), 2.4 + 0.09, places=2)
        # la lama vuela hacia FUERA (y menor que la fachada sur y=0)
        self.assertLess(min(p[1] for c in caras for p in c.puntos), 0.0)

    def test_caras_del_parasol_este_giradas(self):
        self._parasoles(lados="E")
        parasol = next(e for e in self._lista("PARASOL")
                       if e.side == "E")
        caras = v3.caras_de_parasol(parasol, 0.0, 0.0, v3.Camara3D())
        # aletas: 10 cajas a lo largo de Y en x > 6; el back-face
        # culling deja 2 laterales + tapa por caja con la cámara de
        # fábrica (az 30, el 35)
        self.assertGreater(max(p[0] for c in caras for p in c.puntos),
                           6.0)
        self.assertEqual(len([c for c in caras if c.kind == "parasol"]),
                         10 * 3)

    def test_caras_de_la_piel_con_montantes(self):
        self._piel(lados="S", separacion_m=0.6)
        piel = self._lista("SKIN")[0]
        caras = v3.caras_de_piel(piel, 0.0, 0.0, v3.Camara3D())
        kinds = {c.kind for c in caras}
        self.assertIn("piel", kinds)
        self.assertIn("piel_pieza", kinds)
        plano = next(c for c in caras if c.kind == "piel")
        # el plano corre a 0.60 m de la fachada y sube 6.0 m
        self.assertAlmostEqual(
            max(p[1] for p in plano.puntos), -0.60, places=3)
        self.assertAlmostEqual(min(p[1] for p in plano.puntos),
                               -0.60, places=3)
        self.assertAlmostEqual(max(p[2] for p in plano.puntos),
                               6.0, places=3)

    def test_celosia_con_listones_y_mono(self):
        self._piel(lados="S", tipo="celosia_madera")
        piel = self._lista("SKIN")[0]
        caras = v3.caras_de_piel(piel, 0.0, 0.0, v3.Camara3D())
        piezas = [c for c in caras if c.kind == "piel_pieza"]
        # listones horizontales cada 0.20 m sobre 6.0 m de alto; el
        # culling deja 2 caras visibles por listón (cámara de fábrica)
        self.assertEqual(len(piezas), 30 * 2)
        caras_mono = v3.caras_de_piel(piel, 0.0, 0.0, v3.Camara3D())
        self.assertEqual(len(caras), len(caras_mono))

    def test_construir_caras_y_switch_fachada(self):
        self._parasoles(lados="S")
        self._piel(lados="S")
        modelo, _avisos = v3.modelo3d_desde_proyecto(self.context)
        self.assertEqual(len(modelo.parasoles), 1)
        self.assertEqual(len(modelo.pieles), 1)
        caras = v3.construir_caras(modelo, v3.Camara3D())
        self.assertTrue(any(c.kind == "parasol" for c in caras))
        self.assertTrue(any(c.kind == "piel" for c in caras))
        sin_fachada = v3.construir_caras(modelo, v3.Camara3D(),
                                         mostrar_fachada=False)
        self.assertFalse(any(c.kind == "parasol" for c in sin_fachada))
        self.assertFalse(any(c.kind == "piel" for c in sin_fachada))

    def test_png_determinista_con_la_fachada(self):
        import os
        import tempfile
        self._parasoles(lados="S")
        self._piel(lados="S")
        modelo, _avisos = v3.modelo3d_desde_proyecto(self.context)
        cam = v3.Camara3D()
        caras = v3.construir_caras(modelo, cam)
        tmp = tempfile.mkdtemp()
        ruta1 = os.path.join(tmp, "a.png")
        ruta2 = os.path.join(tmp, "b.png")
        v3.export_vista3d_png(caras, cam, ruta1, titulo="fachada")
        v3.export_vista3d_png(caras, cam, ruta2, titulo="fachada")
        with open(ruta1, "rb") as fh:
            datos1 = fh.read()
        with open(ruta2, "rb") as fh:
            datos2 = fh.read()
        self.assertEqual(datos1, datos2)


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogoFachada(_ProyectoBase):

    def test_dialogo_parasoles_y_piel(self):
        from ui.app_window import ARQGenWindow
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            state = dialogo._diseno_state
            state["var_fac_lados"].set("S")
            dialogo._diseno_parasoles_generar()
            self.assertEqual(len(self._lista("PARASOL")), 1)
            texto = state["salida_fac"].get("1.0", "end")
            self.assertIn("horizontal", texto)
            state["var_piel_lados"].set("S,N")
            state["combo_piel_tipo"].set("baguette_terracota")
            state["var_piel_sep"].set("0,9")
            dialogo._diseno_piel_generar()
            pieles = self._lista("SKIN")
            self.assertEqual(len(pieles), 2)
            self.assertTrue(all(e.tipo == "baguette_terracota"
                                for e in pieles))
            texto = state["salida_fac"].get("1.0", "end")
            self.assertIn("terracota", texto)
            dialogo._diseno_parasoles_quitar()
            dialogo._diseno_piel_quitar()
            self.assertEqual(len(self._lista("PARASOL")), 0)
            self.assertEqual(len(self._lista("SKIN")), 0)
            # error amable con vuelo no numérico
            state["var_par_vuelo"].set("malo")
            from ui import app_window as aw
            original = aw.messagebox.showerror
            capturado = {}
            aw.messagebox.showerror = lambda *a, **k: capturado.update(
                {"args": a})
            try:
                dialogo._diseno_parasoles_generar()
            finally:
                aw.messagebox.showerror = original
            self.assertTrue(capturado, "esperaba el error amable")
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

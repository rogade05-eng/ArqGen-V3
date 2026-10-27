"""CUBIERTAS V2 (v3.16.0) — mansarda, mariposa, dientes de sierra.

* Tipologias nuevas con geometria verificada a mano:
  - MANSARDA (a la francesa): dos pendientes por faldon, codo al
    55 % del semivano, faldon alto a la mitad de pendiente.
  - MARIPOSA: las aguas caen AL CENTRO; el eje es el valle y la
    altura guardada es la de los aleros sobre el.
  - SERRENA (dientes de sierra): n dientes de ~3 m con vidrio
    vertical al fondo; sin cumbrera continua.
* Pendiente MINIMA por material: si el usuario pide menos, sube a la
  minima y lo avisa (teja 22 %, pizarra 20 %, chapa 8 %).
* Material fibrocemento con etiqueta y estructura metalica.
* 3D: caras de cada tipologia (faldones, codos, frontones, vidrios)
  y navegacion de camara con teclado (flechas, +/-, Home).
"""

from __future__ import annotations

import math
import unittest

from tests.base import ARQGenTestCase

from domain import cubiertas as cub
from services.architecture_service import ArchitectureService
from ui import view3d as v3


class _ProyectoBase(ARQGenTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("cubiertas2.arqgen"), name="Cubiertas2")
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


class TestTipologiasNuevas(_ProyectoBase):

    def test_mansarda_por_defecto_teja_plana_y_60(self):
        p = cub.resolver_parametros(None, tipologia="mansarda")
        self.assertEqual(p["tipologia"], "mansarda")
        self.assertEqual(p["material"], "teja_plana")
        self.assertAlmostEqual(p["pendiente_pct"], 60.0)
        self.assertEqual(p["estructura"], "madera")

    def test_mariposa_y_serrena_con_chapa(self):
        p = cub.resolver_parametros(None, tipologia="mariposa")
        self.assertEqual(p["material"], "chapa_metalica")
        p2 = cub.resolver_parametros(None, tipologia="serrena")
        self.assertEqual(p2["material"], "chapa_metalica")

    def test_parametros_mansarda_valores_a_mano(self):
        # semivano 5, pendiente 60: codo 2.75,
        # h1 = 2.75*tan(60) = 4.7631..., total = h1 + 2.25*tan(30)
        codo, h1, total = cub.parametros_mansarda(5.0, 60.0)
        self.assertAlmostEqual(codo, 2.75, places=9)
        self.assertAlmostEqual(h1, 2.75 * math.tan(math.radians(60.0)),
                               places=9)
        self.assertAlmostEqual(
            total, h1 + 2.25 * math.tan(math.radians(30.0)), places=9)

    def test_parametros_serrena_dientes_de_tres_metros(self):
        n, fondo, altura = cub.parametros_serrena(
            [(0, 0), (12, 0), (12, 6), (0, 6)], 20.0)
        self.assertEqual(n, 2)          # 6 m de fondo -> 2 dientes de 3
        self.assertAlmostEqual(fondo, 3.0, places=9)
        self.assertAlmostEqual(altura, 3.0 * math.tan(math.radians(20.0)),
                               places=9)

    def test_generar_mansarda_cumbrera_y_altura(self):
        self._edificio()
        resumen = cub.generar_cubierta(self.context, tipologia="mansarda")
        roof = cub.cubierta_actual(self.context)
        self.assertIsNotNone(roof.ridge)
        minx = min(p[0] for p in roof.footprint)
        maxx = max(p[0] for p in roof.footprint)
        miny = min(p[1] for p in roof.footprint)
        maxy = max(p[1] for p in roof.footprint)
        semivano = min(maxx - minx, maxy - miny) / 2.0
        _codo, _h1, total = cub.parametros_mansarda(
            semivano, roof.pendiente_pct)
        self.assertAlmostEqual(roof.altura_cumbrera_m, total, places=3)
        self.assertGreater(len(resumen["creados"]), 0)

    def test_generar_mariposa_eje_es_el_valle(self):
        self._edificio()
        cub.generar_cubierta(self.context, tipologia="mariposa")
        roof = cub.cubierta_actual(self.context)
        self.assertIsNotNone(roof.ridge)
        # la cumbrera corre por el CENTRO y la altura es la de los
        # aleros sobre el valle: semivano de la HUELLA * pendiente
        (r1, r2) = roof.ridge
        self.assertAlmostEqual((r1[0] + r2[0]) / 2.0, 6.0, places=3)
        miny = min(p[1] for p in roof.footprint)
        maxy = max(p[1] for p in roof.footprint)
        semivano = (maxy - miny) / 2.0
        self.assertAlmostEqual(roof.altura_cumbrera_m,
                               semivano * (roof.pendiente_pct / 100.0),
                               places=3)

    def test_generar_serrena_sin_cumbrera_y_con_dientes(self):
        self._edificio()
        cub.generar_cubierta(self.context, tipologia="serrena")
        roof = cub.cubierta_actual(self.context)
        self.assertIsNone(roof.ridge)
        n = int(roof.metadata.get("dientes", 0))
        minx = min(p[0] for p in roof.footprint)
        maxx = max(p[0] for p in roof.footprint)
        miny = min(p[1] for p in roof.footprint)
        maxy = max(p[1] for p in roof.footprint)
        corto = min(maxx - minx, maxy - miny)
        self.assertEqual(n, max(1, int(round(corto / 3.0))))
        self.assertAlmostEqual(
            roof.altura_cumbrera_m,
            (corto / n) * math.tan(math.radians(roof.pendiente_pct)),
            places=3)

    def test_regenerar_mansarda_no_duplica(self):
        self._edificio()
        cub.generar_cubierta(self.context, tipologia="mansarda")
        cub.generar_cubierta(self.context, tipologia="mansarda")
        self.assertEqual(len(self.context.architecture.list(
            "ROOF", self.context.project.id)), 1)


class TestPendienteMinima(_ProyectoBase):

    def test_teja_pide_22_como_minimo(self):
        p = cub.resolver_parametros(None, tipologia="dos_aguas",
                                    material="teja_curva",
                                    pendiente_pct=10.0)
        self.assertTrue(p["pendiente_ajustada"])
        self.assertAlmostEqual(p["pendiente_pct"], 22.0)
        self.assertAlmostEqual(p["pendiente_minima"], 22.0)

    def test_chapa_pide_8_como_minimo(self):
        p = cub.resolver_parametros(None, tipologia="un_agua",
                                    material="chapa_metalica",
                                    pendiente_pct=4.0)
        self.assertTrue(p["pendiente_ajustada"])
        self.assertAlmostEqual(p["pendiente_pct"], 8.0)

    def test_lo_suficiente_no_se_toca(self):
        p = cub.resolver_parametros(None, tipologia="dos_aguas",
                                    material="teja_curva",
                                    pendiente_pct=35.0)
        self.assertFalse(p["pendiente_ajustada"])
        self.assertAlmostEqual(p["pendiente_pct"], 35.0)

    def test_generar_avisa_del_ajuste(self):
        self._edificio()
        resumen = cub.generar_cubierta(self.context,
                                       tipologia="dos_aguas",
                                       material="teja_curva",
                                       pendiente_pct=10.0)
        self.assertTrue(any("minima" in a for a in resumen["avisos"]))
        roof = cub.cubierta_actual(self.context)
        self.assertAlmostEqual(roof.pendiente_pct, 22.0)


class TestFibrocemento(_ProyectoBase):

    def test_material_etiqueta_y_estructura(self):
        self.assertIn("fibrocemento", cub.MATERIALES)
        self.assertEqual(cub.ETIQUETA_MATERIAL["fibrocemento"],
                         "chapa de fibrocemento")
        p = cub.resolver_parametros(None, tipologia="un_agua",
                                    material="fibrocemento")
        self.assertEqual(p["estructura"], "metalica")
        self.assertAlmostEqual(p["pendiente_pct"], 15.0)  # un_agua > 8

    def test_etiquetas_de_las_tipologias_nuevas(self):
        for clave in ("mansarda", "mariposa", "serrena"):
            self.assertIn(clave, cub.ETIQUETA_TIPOLOGIA)
            self.assertIn(clave, cub.TIPOLOGIAS)


class TestSuperficieY3D(_ProyectoBase):

    def _roof_ativa(self, tipologia, pendiente=60.0):
        self._edificio()
        cub.generar_cubierta(self.context, tipologia=tipologia,
                             pendiente_pct=pendiente)
        return cub.cubierta_actual(self.context)

    def test_superficie_mansarda_pondera_dos_pendientes(self):
        roof = self._roof_ativa("mansarda", 60.0)
        sup = cub.superficie_cubierta(roof)
        proyectada = sup["area_proyectada"]
        # factor simple de una sola pendiente al 60 %: sqrt(1+0.6^2)
        factor_simple = math.sqrt(1.0 + 0.6 ** 2)
        self.assertGreater(sup["area_inclinada"],
                           proyectada * factor_simple * 1.3)

    def test_caras_3d_de_las_tres_tipologias(self):
        casos = {"mariposa": 2, "mansarda": 6, "serrena": 4}
        nivel = v3.Nivel3D(level_id=self.nivel.id, name="L1",
                           base_z=0.0, height_m=3.0)
        camara = v3.Camara3D()
        for tipologia, esperado in casos.items():
            roof = self._roof_ativa(
                tipologia, 60.0 if tipologia == "mansarda" else 20.0)
            caras = v3.caras_de_cubierta(roof, nivel, 0.0, camara)
            self.assertEqual(len(caras), esperado, tipologia)

    def test_serrena_3d_lleva_vidrio_vertical(self):
        roof = self._roof_ativa("serrena", 20.0)
        nivel = v3.Nivel3D(level_id=self.nivel.id, name="L1",
                           base_z=0.0, height_m=3.0)
        caras = v3.caras_de_cubierta(roof, nivel, 0.0, v3.Camara3D())
        self.assertIn("vidrio", {c.kind for c in caras})

    def test_camara_teclado_gira_inclina_zoom_y_home(self):
        cam = v3.Camara3D()
        self.assertTrue(cam.tecla("Left"))
        self.assertAlmostEqual(cam.azimuth_deg, 20.0, places=9)
        self.assertTrue(cam.tecla("Right"))
        self.assertAlmostEqual(cam.azimuth_deg, 30.0, places=9)
        self.assertTrue(cam.tecla("Up"))
        self.assertAlmostEqual(cam.elevacion_deg, 40.0, places=9)
        self.assertTrue(cam.tecla("Down"))
        self.assertAlmostEqual(cam.elevacion_deg, 35.0, places=9)
        self.assertTrue(cam.tecla("plus"))
        self.assertAlmostEqual(cam.zoom, 1.25, places=9)
        self.assertTrue(cam.tecla("minus"))
        self.assertAlmostEqual(cam.zoom, 1.0, places=9)
        cam.gira(500.0)
        cam.tecla("Home")
        self.assertAlmostEqual(cam.azimuth_deg, 30.0, places=9)
        self.assertAlmostEqual(cam.elevacion_deg, 35.0, places=9)
        self.assertAlmostEqual(cam.zoom, 1.0, places=9)
        self.assertFalse(cam.tecla("x"))  # tecla ajena

    def test_camara_respeta_los_limites(self):
        cam = v3.Camara3D()
        for _ in range(40):
            cam.tecla("Up")
        self.assertLessEqual(cam.elevacion_deg, v3.Camara3D.ELEV_MAX)
        for _ in range(40):
            cam.tecla("plus")
        self.assertLessEqual(cam.zoom, v3.Camara3D.ZOOM_MAX)


class TestResumenCp1252(_ProyectoBase):

    def test_lineas_de_resumen_codificables(self):
        for tipologia in ("mansarda", "mariposa", "serrena"):
            self._edificio()
            resumen = cub.generar_cubierta(self.context,
                                           tipologia=tipologia)
            texto = cub.resumen_texto(resumen)
            texto.encode("cp1252")
        resumen_ajuste = cub.resumen_texto({
            "parametros": {"tipologia": "dos_aguas",
                           "material": "teja_curva", "pendiente_pct": 22,
                           "estructura": "madera"},
            "creados": ["ROOF-1"], "eliminados": [],
            "avisos": ["pendiente subida al 22 %: es la minima que "
                       "asegura el material elegido"], "qto": {}})
        resumen_ajuste.encode("cp1252")

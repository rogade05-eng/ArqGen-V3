"""ASISTENTE DE SERVICIOS v3.33.0 (domain/servicios_specs.py +
domain/servicios_engine.py).

Catálogo versionado de servicios completos por temática (anatomía
patológica, laboratorio clínico, imagenología, hemodiálisis, CEyE,
farmacia): parámetros dinámicos sanos, programa dimensionado con
áreas escaladas, validación funcional contra el DNA y aplicación al
proyecto con zona SERVICE, pasillo, locales reales y relaciones.
"""

from __future__ import annotations

import unittest

from core.errors import DomainError
from domain import servicios_engine as eng
from domain.servicios_specs import (ServicioLocal, ServicioParam,
                                    cargar_servicios,
                                    resumen_catalogo, servicio,
                                    servicios_disponibles)
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase


# ---------------------------------------------------------------------------
# catálogo
# ---------------------------------------------------------------------------

class TestCatalogo(unittest.TestCase):
    """El catálogo versionado es sano y completo."""

    def setUp(self) -> None:
        self.items = cargar_servicios()

    def test_catalogo_con_codigos_unicos(self):
        self.assertGreaterEqual(len(self.items), 11)
        codigos = [s.codigo for s in self.items]
        self.assertEqual(len(codigos), len(set(codigos)))
        for esperado in ("ANATOMIA_PATOLOGICA", "MORGUE",
                         "TOMOGRAFIA_COMPUTARIZADA", "UCI",
                         "CUIDADOS_INTERMEDIOS", "URGENCIAS"):
            self.assertIn(esperado, codigos)

    def test_parametros_sanos(self):
        for item in self.items:
            for p in item.parametros:
                self.assertIsInstance(p, ServicioParam)
                self.assertLessEqual(p.minimo, p.maximo,
                                     f"{item.codigo}.{p.codigo}")
                if p.tipo == "bool":
                    self.assertIsInstance(p.defecto, bool)
                else:
                    self.assertGreaterEqual(float(p.defecto), p.minimo)
                    self.assertLessEqual(float(p.defecto), p.maximo)
                self.assertIn(p.tipo, ("int", "bool"))

    def test_locales_sanos(self):
        for item in self.items:
            codigos = {l.codigo for l in item.locales}
            self.assertEqual(len(codigos), len(item.locales))
            for l in item.locales:
                self.assertIsInstance(l, ServicioLocal)
                self.assertGreaterEqual(l.area_max, l.area_min)
                self.assertGreater(l.area_max, 0.0)
                self.assertTrue(l.space_type)
                # las adyacencias apuntan a locales del mismo servicio
                for adj in l.adjacencias:
                    self.assertIn(adj, codigos,
                                  f"{item.codigo}.{l.codigo} -> {adj}")
                # condiciones y repetición apuntan a parámetros reales
                if l.condicion:
                    self.assertIsNotNone(item.param(l.condicion))
                if l.repite_por:
                    self.assertIsNotNone(item.param(l.repite_por))
                # todo local con área por parámetro usa parámetros reales
                for k in l.area_por:
                    self.assertIsNotNone(item.param(k))

    def test_flujos_y_checks_del_servicio_marca(self):
        ap = servicio("ANATOMIA_PATOLOGICA")
        self.assertTrue(ap.flujos)
        self.assertTrue(ap.checks)
        self.assertTrue(any("necropsias" in f.lower()
                            for f in ap.flujos))
        self.assertTrue(any(l.critico for l in ap.locales))

    def test_servicio_desconocido_error_amable(self):
        with self.assertRaises(DomainError) as ctxm:
            servicio("MASSAJE_TURISTICO")
        self.assertEqual(ctxm.exception.code, "ARQ-SRV-002")

    def test_disponibles_y_resumen(self):
        disponibles = servicios_disponibles()
        self.assertEqual(len(disponibles), len(self.items))
        resumen = resumen_catalogo()
        self.assertGreaterEqual(resumen["locales"], 40)
        self.assertGreaterEqual(resumen["criticos"], 5)
        self.assertGreaterEqual(resumen["parametros"], 15)


# ---------------------------------------------------------------------------
# programa dimensionado
# ---------------------------------------------------------------------------

class TestPrograma(unittest.TestCase):
    """programa_servicio: áreas escaladas, condiciones y repetición."""

    def test_anatomia_patologica_con_defectos(self):
        programa = eng.programa_servicio("ANATOMIA_PATOLOGICA")
        self.assertEqual(programa["servicio"], "ANATOMIA_PATOLOGICA")
        self.assertEqual(programa["totales"]["locales"], 17)
        nombres = [r["nombre"] for r in programa["renglones"]]
        for esperado in ("Sala de necropsias",
                         "Laboratorio de histotecnologia",
                         "Sala de corte (macroscopia)",
                         "Camara mortuoria",
                         "Archivo de piezas y laminas",
                         "Secretaria", "Microscopia",
                         "Almacen de reactivos"):
            self.assertIn(esperado, nombres)
        self.assertGreater(programa["totales"]["area_m2"], 150.0)
        self.assertTrue(programa["totales"]["grupos"])

    def test_el_area_escala_con_los_parametros(self):
        base = eng.programa_servicio("ANATOMIA_PATOLOGICA",
                                     {"necropsias_dia": 0})
        grande = eng.programa_servicio("ANATOMIA_PATOLOGICA",
                                       {"necropsias_dia": 6})
        area_de = lambda p, n: next(r["area_m2"] for r in p["renglones"]
                                    if r["nombre"] == n)
        self.assertGreater(
            area_de(grande, "Sala de necropsias"),
            area_de(base, "Sala de necropsias"))
        self.assertAlmostEqual(area_de(base, "Sala de necropsias"),
                               30.0, places=6)
        self.assertAlmostEqual(area_de(grande, "Sala de necropsias"),
                               66.0, places=6)

    def test_el_maximo_del_catalogo_acota_y_avisa(self):
        programa = eng.programa_servicio("ANATOMIA_PATOLOGICA",
                                         {"necropsias_dia": 12})
        area = next(r["area_m2"] for r in programa["renglones"]
                    if r["nombre"] == "Sala de necropsias")
        self.assertEqual(area, 66.0)   # area_max del catálogo
        self.assertTrue(any("NECROPSIAS" in a for a in programa["avisos"]))

    def test_condicion_bool_excluye_locales(self):
        con = eng.programa_servicio("ANATOMIA_PATOLOGICA",
                                    {"con_archivo": True})
        sin = eng.programa_servicio("ANATOMIA_PATOLOGICA",
                                    {"con_archivo": False})
        self.assertEqual(con["totales"]["locales"], 17)
        self.assertEqual(sin["totales"]["locales"], 16)
        self.assertFalse(any("Archivo" in r["nombre"]
                             for r in sin["renglones"]))

    def test_repite_por_crea_salas_numeradas(self):
        programa = eng.programa_servicio("IMAGENOLOGIA",
                                         {"equipos_rx": 3,
                                          "con_tac": False,
                                          "con_mamografia": False})
        salas = [r["nombre"] for r in programa["renglones"]
                 if r["codigo"] == "RX_GENERAL"]
        self.assertEqual(salas, ["Sala de RX general",
                                 "Sala de RX general 2",
                                 "Sala de RX general 3"])

    def test_parametros_basura_no_explotan(self):
        programa = eng.programa_servicio("FARMACIA",
                                         {"camas": "no-sé",
                                          "bogus": 3,
                                          "personal": 999})
        self.assertTrue(any("ilegible" in a for a in programa["avisos"]))
        self.assertTrue(any("ignorado" in a for a in programa["avisos"]))
        self.assertTrue(any("por encima del máximo" in a
                            for a in programa["avisos"]))
        # 5 locales del catálogo menos la farmacia estéril (opcional)
        self.assertEqual(programa["totales"]["locales"], 4)

    def test_dimensiones_sugeridas_cierran_el_area(self):
        programa = eng.programa_servicio("HEMODIALISIS",
                                         {"puestos": 6})
        for r in programa["renglones"]:
            if r["area_m2"] <= 72.0 and r["area_m2"] >= 6.0:
                # los locales diminutos (filtro v3.42) se quedan en
                # los pisos de ancho/fondo sugeridos y se les perdona
                # el producto
                producto = r["ancho_m"] * r["fondo_m"]
                self.assertGreaterEqual(producto,
                                        r["area_m2"] * 0.98,
                                        r["nombre"])
                self.assertLessEqual(producto, r["area_m2"] * 1.15,
                                     r["nombre"])

    def test_validacion_funcional_ok_con_defectos(self):
        """Con los defectos del catálogo, TODOS los servicios cumplen
        las áreas mínimas del DNA; los críticos opcionales (como la
        farmacia estéril) avisan de su ausencia."""
        for codigo, _nombre in servicios_disponibles():
            programa = eng.programa_servicio(codigo)
            areast = next(c for c in programa["validacion"]
                          if c["codigo"] == "AREAS")
            self.assertEqual(areast["estado"], "ok",
                             f"{codigo}: {areast['detalle']}")
            criticos = next(c for c in programa["validacion"]
                            if c["codigo"] == "CRITICOS")
            if codigo == "FARMACIA":
                # el único crítico es opcional (con_esteril=False)
                self.assertEqual(criticos["estado"], "aviso", codigo)
                self.assertIn("Farmacia esteril", criticos["detalle"])
            else:
                self.assertEqual(criticos["estado"], "ok", codigo)

    def test_sin_microbiologia_los_criticos_avisan(self):
        programa = eng.programa_servicio("LABORATORIO_CLINICO",
                                         {"con_microbiologia": False})
        criticos = next(c for c in programa["validacion"]
                        if c["codigo"] == "CRITICOS")
        self.assertEqual(criticos["estado"], "aviso")
        self.assertIn("Microbiologia", criticos["detalle"])

    def test_puertas_recomendadas_de_los_criticos(self):
        programa = eng.programa_servicio("ANATOMIA_PATOLOGICA")
        puertas = next(c for c in programa["validacion"]
                       if c["codigo"] == "PUERTAS")
        self.assertEqual(puertas["estado"], "info")
        self.assertIn("1.20", puertas["detalle"])


# ---------------------------------------------------------------------------
# aplicar al proyecto
# ---------------------------------------------------------------------------

class TestAplicar(ARQGenTestCase):
    """aplicar_servicio: zona, pasillo, locales y relaciones reales."""

    def setUp(self) -> None:
        super().setUp()
        self.ctx = self.application.create_project(
            self.project_path("servicio.arqgen"), name="Servicio")
        self.arch = ArchitectureService(self.ctx)

    def tearDown(self) -> None:
        self.ctx.close()
        super().tearDown()

    def test_en_proyecto_vacio_crea_edificio_y_nivel(self):
        resumen = eng.aplicar_servicio(self.ctx, "FARMACIA")
        niveles = self.ctx.architecture.list("LEVEL",
                                             self.ctx.project.id)
        self.assertEqual(len(niveles), 1)
        self.assertIn("Farmacia", niveles[0].name)
        self.assertEqual(niveles[0].name, resumen["nivel"])
        # 4 locales (sin la estéril opcional) + pasillo
        self.assertEqual(len(resumen["locales"]), 5)

    def test_aplica_en_el_nivel_pedido(self):
        self.arch.create_level("PB", 0.0, 3.0)
        resumen = eng.aplicar_servicio(self.ctx, "ANATOMIA_PATOLOGICA",
                                       nivel_ref="PB")
        self.assertEqual(resumen["nivel"], "PB")
        espacios = [s for s in self.ctx.architecture.list(
            "SPACE", self.ctx.project.id) if s.level_id]
        self.assertEqual(len(espacios), 18)            # 17 + pasillo
        self.assertEqual(len(resumen["creados"]), 18)

    def test_zona_service_pasillo_y_relaciones(self):
        self.arch.create_level("PB", 0.0, 3.0)
        resumen = eng.aplicar_servicio(self.ctx, "ANATOMIA_PATOLOGICA",
                                       nivel_ref="PB")
        zona = self.ctx.architecture.get_by_code("ZONE", resumen["zona"])
        self.assertIsNotNone(zona)
        self.assertEqual(zona.kind, "SERVICE")
        pasillo = self.ctx.architecture.get_by_code(
            "SPACE", resumen["pasillo"])
        self.assertIsNotNone(pasillo)
        self.assertEqual(pasillo.space_type, "CORRIDOR")
        self.assertEqual(resumen["relaciones"], 17)
        relaciones = self.ctx.architecture.list(
            "SPACE_RELATIONSHIP", self.ctx.project.id)
        self.assertEqual(len(relaciones), 17)
        for rel in relaciones:
            self.assertEqual(rel.kind, "adjacent_to")
            self.assertEqual(rel.source, eng.ORIGEN_SERVICIO)
        # todos los creados quedan en la zona del servicio
        for codigo in resumen["creados"]:
            espacio = self.ctx.architecture.get_by_code("SPACE", codigo)
            self.assertEqual(espacio.zone_id, zona.id)

    def test_los_locales_entran_con_su_uso_del_dna(self):
        self.arch.create_level("PB", 0.0, 3.0)
        resumen = eng.aplicar_servicio(self.ctx, "ANATOMIA_PATOLOGICA",
                                       nivel_ref="PB")
        usos = {self.ctx.architecture.get_by_code(
            "SPACE", c).space_type for c in resumen["locales"]}
        self.assertIn("AUTOPSY_ROOM", usos)
        self.assertIn("LABORATORY", usos)
        self.assertIn("CORRIDOR", usos)

    def test_empaquetado_norte_sur_respetan_el_pasillo(self):
        self.arch.create_level("PB", 0.0, 3.0)
        resumen = eng.aplicar_servicio(self.ctx, "LABORATORIO_CLINICO",
                                       nivel_ref="PB", origen=(10.0, 20.0))
        pasillo = self.ctx.architecture.get_by_code(
            "SPACE", resumen["pasillo"])
        y0, y1 = 20.0, 20.0 + eng.PASILLO_ANCHO
        for codigo in resumen["locales"]:
            if codigo == resumen["pasillo"]:
                continue
            espacio = self.ctx.architecture.get_by_code("SPACE", codigo)
            ys = [p[1] for p in espacio.boundary]
            # cada local está del todo por encima o por debajo del pasillo
            self.assertTrue(max(ys) <= y0 + 1e-6
                            or min(ys) >= y1 - 1e-6,
                            f"{espacio.name} invade el pasillo")
        # y el pasillo nace en el origen pedido
        xs = [p[0] for p in pasillo.boundary]
        self.assertAlmostEqual(min(xs), 10.0, places=6)

    def test_nombres_unicos_tras_dos_aplicaciones(self):
        self.arch.create_level("PB", 0.0, 3.0)
        r1 = eng.aplicar_servicio(self.ctx, "FARMACIA", nivel_ref="PB")
        r2 = eng.aplicar_servicio(self.ctx, "FARMACIA", nivel_ref="PB",
                                  origen=(60.0, 0.0))
        nombres = [self.ctx.architecture.get_by_code("SPACE", c).name
                   for c in r1["creados"] + r2["creados"]]
        self.assertEqual(len(nombres), len(set(nombres)))

    def test_trazar_muros_crea_wall_y_avisa_de_duplicados(self):
        self.arch.create_level("PB", 0.0, 3.0)
        resumen = eng.aplicar_servicio(self.ctx, "FARMACIA",
                                       nivel_ref="PB", trazar_muros=True)
        muros = self.ctx.architecture.list("WALL", self.ctx.project.id)
        locales_sin_pasillo = len(resumen["locales"]) - 1
        # 4 muros por local trazado
        self.assertEqual(len(muros), locales_sin_pasillo * 4)
        self.assertTrue(any("duplicadas" in a for a in resumen["avisos"]))

    def test_nivel_requerido_si_el_proyecto_ya_tiene(self):
        self.arch.create_level("PB", 0.0, 3.0)
        with self.assertRaises(DomainError) as ctxm:
            eng.aplicar_servicio(self.ctx, "FARMACIA", nivel_ref="")
        self.assertEqual(ctxm.exception.code, "ARQ-SRV-003")


# ---------------------------------------------------------------------------
# texto (cp1252)
# ---------------------------------------------------------------------------

class TestTexto(unittest.TestCase):
    """Los informes del asistente, listos para la consola Windows."""

    def setUp(self) -> None:
        self.programa = eng.programa_servicio("ANATOMIA_PATOLOGICA",
                                              {"necropsias_dia": 3})

    def test_texto_programa_cp1252_y_completo(self):
        texto = eng.texto_programa(self.programa)
        texto.encode("cp1252")   # lanza si llevara caracteres de más
        self.assertIn("PROGRAMA DEL SERVICIO", texto)
        self.assertIn("Sala de necropsias", texto)
        self.assertIn("TOTAL", texto)
        self.assertIn("Flujos funcionales", texto)
        # disciplina de la consola: nada de flechas unicode
        self.assertNotIn("\u2192", texto)

    def test_texto_validacion_cp1252(self):
        texto = eng.texto_validacion(self.programa["validacion"])
        texto.encode("cp1252")
        self.assertIn("VALIDACIÓN FUNCIONAL", texto)
        self.assertIn("[x] AREAS", texto)
        self.assertIn("[i] FLUJO1", texto)

    def test_texto_resumen_servicio_cp1252(self):
        self.programa["nivel"] = "Planta Baja"
        self.programa["zona"] = "ZONA-1"
        self.programa["pasillo"] = "SP-1"
        texto = eng.texto_resumen_servicio(self.programa)
        texto.encode("cp1252")
        self.assertIn("Anatomia Patologica", texto)
        self.assertIn("17 local(es)", texto)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

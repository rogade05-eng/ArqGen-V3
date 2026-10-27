"""SERVICIOS DE VIVIENDA (v3.30.0) — domain/vivienda_servicios.py.

Las secciones 39 (DOMÓTICA), 45 (PISCINA) y 46 (ACÚSTICA) del
documento «Especificaciones técnicas Viviendas.txt» como datos
versionados (resources/knowledge/vivienda_servicios.json) y tres
motores de solo lectura:

* PISCINA: sistema INDEPENDIENTE (§45) con volumen, filtración,
  bomba, skimmers, iluminación, seguridad y equipos en CUP.
* ACÚSTICA: fuentes del §46 contra dormitorios midiendo los muros
  compartidos del trazado, con soluciones de referencia (material,
  espesor, doble tabique, R_w) y vidrio acústico de fachada.
* DOMÓTICA: plan por SISTEMAS y ELEMENTOS del §39 con conteos sobre
  el modelo y equipos de referencia; RED/PANEL/ALIMENTACION quedan
  como diseño (REQUIERE_CALCULO_ESPECIALIZADO).

Los valores esperados de estos tests fueron calculados a mano:
vaso 8x4 con profundidades 1.0-2.0 -> lámina 32 m2, volumen 48 m3,
renovación 6 h -> caudal 8 m3/h, bomba 0.40 kW, 1 skimmer,
2 impulsiones, 2 focos y 209 800 CUP de equipos.
"""

from __future__ import annotations

import unittest

from core.errors import DomainError
from tests.base import ARQGenTestCase

from ui import building_wizard as bwiz


def _num(valor: float) -> float:
    return round(float(valor), 6)


class TestPiscina(unittest.TestCase):
    """La calculadora del §45 (no necesita proyecto)."""

    def setUp(self):
        from domain.vivienda_servicios import calcular_piscina
        self.informe = calcular_piscina(8.0, 4.0, 1.0, 2.0)

    def test_volumen_y_caudal_exactos(self):
        vaso = self.informe["vaso"]
        self.assertEqual(_num(vaso["lamina_m2"]), 32.0)
        self.assertEqual(_num(vaso["prof_media_m"]), 1.5)
        self.assertEqual(_num(vaso["volumen_m3"]), 48.0)
        fil = self.informe["filtracion"]
        self.assertEqual(_num(fil["renovacion_h"]), 6.0)
        self.assertEqual(_num(fil["caudal_m3_h"]), 8.0)

    def test_bomba_estimada_y_altura(self):
        # P = 1000 * 9.81 * (8/3600) * 10 / 0.55 = 396.4 W = 0.40 kW
        fil = self.informe["filtracion"]
        self.assertAlmostEqual(fil["bomba_kw"], 0.396, places=2)
        self.assertEqual(_num(fil["altura_m"]), 10.0)
        from domain.vivienda_servicios import calcular_piscina
        fil2 = calcular_piscina(8.0, 4.0, 1.0, 2.0,
                                altura_m=20.0)["filtracion"]
        self.assertAlmostEqual(fil2["bomba_kw"], 0.793, places=2)

    def test_skimmers_impulsores_y_focos(self):
        mensajes = {h["codigo"]: h["mensaje"]
                    for h in self.informe["hallazgos"]}
        self.assertTrue(mensajes["PI003"].startswith("1 skimmer"))
        self.assertTrue(mensajes["PI004"].startswith("2 boquilla(s)"))
        self.assertTrue(mensajes["PI009"].startswith("2 foco(s)"))

    def test_total_equipos_calculado_a_mano(self):
        # 45000 + 52000 + 6500 + 2*2200 + 2*7800 + 24*3200 + 9500
        self.assertEqual(_num(self.informe["total_equipos_cup"]),
                         209800.0)
        filas = self.informe["equipos"]
        self.assertEqual(len(filas), 7)
        cerca = next(f for f in filas if f["codigo"] == "PIS-CERCA")
        self.assertEqual(_num(cerca["cantidad"]), 24.0)
        # la tabla para el HTML repite las filas y cierra con TOTAL
        tabla = self.informe["tablas"][0]
        self.assertEqual(len(tabla["filas"]), len(filas) + 1)
        self.assertEqual(tabla["filas"][-1][-1], "209 800")

    def test_hallazgos_orden_y_estados_honestos(self):
        codigos = [h["codigo"] for h in self.informe["hallazgos"]]
        self.assertEqual(codigos, ["PI001", "PI002", "PI003", "PI004",
                                   "PI005", "PI006", "PI007", "PI008",
                                   "PI009"])
        por_codigo = {h["codigo"]: h
                      for h in self.informe["hallazgos"]}
        self.assertEqual(por_codigo["PI006"]["estado"],
                         "requiere calculo")
        self.assertIn("equipotencial", por_codigo["PI006"]["mensaje"])
        self.assertEqual(por_codigo["PI007"]["estado"], "pendiente")
        self.assertEqual(por_codigo["PI008"]["estado"], "pendiente")
        self.assertEqual(por_codigo["PI008"]["severidad"], "aviso")
        self.assertEqual(self.informe["resumen"]["ok"], 6)

    def test_profundidad_fuera_de_rango_avisa(self):
        from domain.vivienda_servicios import calcular_piscina
        bajo = calcular_piscina(8.0, 4.0, 0.3, 0.5)
        self.assertEqual(bajo["hallazgos"][0]["severidad"], "aviso")
        self.assertIn("vaso para niños", bajo["hallazgos"][0]["mensaje"])
        alto = calcular_piscina(8.0, 4.0, 1.0, 3.0)
        self.assertIn("vaso de salto", alto["hallazgos"][0]["mensaje"])

    def test_renovacion_personalizada_y_fuera_de_rango(self):
        from domain.vivienda_servicios import calcular_piscina
        rapido = calcular_piscina(8.0, 4.0, 1.0, 2.0, renovacion_h=4.8)
        self.assertEqual(
            _num(rapido["filtracion"]["caudal_m3_h"]), 10.0)
        lento = calcular_piscina(8.0, 4.0, 1.0, 2.0, renovacion_h=2.0)
        self.assertEqual(lento["hallazgos"][1]["severidad"], "aviso")

    def test_errores_amables(self):
        from domain.vivienda_servicios import calcular_piscina
        with self.assertRaises(DomainError) as ctx:
            calcular_piscina(-1.0, 4.0, 1.0, 2.0)
        self.assertEqual(ctx.exception.code, "ARQ-PIS-001")
        with self.assertRaises(DomainError) as ctx:
            calcular_piscina(8.0, 4.0, 2.0, 1.0)
        self.assertEqual(ctx.exception.code, "ARQ-PIS-002")
        with self.assertRaises(DomainError) as ctx:
            calcular_piscina("ocho", 4.0, 1.0, 2.0)
        self.assertEqual(ctx.exception.code, "ARQ-PIS-001")

    def test_texto_cp1252(self):
        from domain.vivienda_servicios import texto_piscina
        texto = texto_piscina(self.informe)
        texto.encode("cp1252")
        self.assertIn("PISCINA", texto)
        self.assertIn("TOTAL equipos: 209 800 CUP", texto)
        self.assertIn("REQUIERE_CALCULO_ESPECIALIZADO", texto)


class TestBaseProyecto(ARQGenTestCase):
    """Proyecto de vivienda generado por el asistente."""

    def setUp(self):
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("servicios.arqgen"), name="Servicios")
        data = bwiz.BuildingWizardData()
        data.name = "Casa de los servicios"
        data.usage_type = "Vivienda"
        data.vivienda_tipologia = "Unifamiliar aislada"
        bwiz.apply_usage_program(data)
        self.assertTrue(bwiz.apply_plan(data, self.context))


class TestAcustica(TestBaseProyecto):
    """El análisis del §46 sobre el trazado medido."""

    def setUp(self):
        super().setUp()
        from domain.vivienda_servicios import analisis_acustico
        self.informe = analisis_acustico(self.context)

    def test_informe_completo_y_estados(self):
        codigos = [h["codigo"] for h in self.informe["hallazgos"]]
        self.assertEqual(codigos, ["ACU001", "ACU002", "ACU003",
                                   "ACU004", "ACU005", "ACU006",
                                   "ACU007"])
        por_codigo = {h["codigo"]: h for h in self.informe["hallazgos"]}
        self.assertEqual(por_codigo["ACU007"]["estado"],
                         "requiere calculo")
        self.assertIn("ensayo", por_codigo["ACU007"]["mensaje"])
        # tipología aislada: sin medianeras declaradas
        self.assertEqual(por_codigo["ACU003"]["severidad"], "info")
        # hay ventanas de dormitorio a fachada: vidrio acústico
        self.assertEqual(por_codigo["ACU004"]["severidad"], "aviso")
        self.assertIn("VIDRIO_ACUSTICO", por_codigo["ACU004"]["mensaje"])

    def test_pares_medidos_con_espesor_real(self):
        pares = self.informe["pares"]
        self.assertTrue(pares, "el trazado generado tiene pares")
        for p in pares:
            self.assertGreaterEqual(p["muros_medidos"], 1)
            self.assertAlmostEqual(p["espesor_medido_mm"], 200.0,
                                   places=1)
            self.assertTrue(p["material"])
            self.assertIn(p["tipo_fuente"], ("COCINA", "BANOS",
                                             "EQUIPOS"))
        # los pares que tocan cocina o baño piden partición de 30 dB
        # y los que tocan equipos (garaje/depósito) 40 dB con doble
        # tabique
        tipos = {p["tipo_fuente"] for p in pares}
        self.assertTrue(tipos & {"COCINA", "BANOS"})

    def test_soluciones_de_referencia_del_json(self):
        tabla = self.informe["tablas"][1]
        self.assertEqual(tabla["titulo"],
                         "Soluciones de referencia del §46")
        self.assertEqual(len(tabla["filas"]), 5)
        vecinos = next(f for f in tabla["filas"] if f[0] == "VECINOS")
        self.assertEqual(vecinos[4], "50.0")
        self.assertEqual(vecinos[3], "sí")

    def test_proyecto_sin_dormitorios_no_revienta(self):
        context = self.application.create_project(
            self.project_path("vacio.arqgen"), name="Vacío")
        from domain.vivienda_servicios import analisis_acustico
        informe = analisis_acustico(context)
        por_codigo = {h["codigo"]: h for h in informe["hallazgos"]}
        self.assertEqual(por_codigo["ACU002"]["severidad"], "info")
        self.assertEqual(informe["pares"], [])

    def test_texto_cp1252(self):
        from domain.vivienda_servicios import texto_acustica
        texto = texto_acustica(self.informe)
        texto.encode("cp1252")
        self.assertIn("ACÚSTICA DE LA VIVIENDA", texto)
        self.assertIn("Pares fuente-dormitorio medidos:", texto)


class TestDomotica(TestBaseProyecto):
    """El plan del §39 con conteos del modelo."""

    def setUp(self):
        super().setUp()
        from domain.vivienda_servicios import plan_domotico
        self.plan = plan_domotico(self.context)
        self.por_nombre = {f["nombre"]: f
                           for f in self.plan["filas"]}

    def test_ocho_sistemas_y_hallazgos(self):
        claves = [s["sistema"] for s in self.plan["sistemas"]]
        self.assertEqual(claves, ["ILUMINACION", "SEGURIDAD",
                                  "CLIMATIZACION", "PERSIANAS",
                                  "RIEGO", "ENERGIA", "AGUA",
                                  "ACCESO"])
        codigos = [h["codigo"] for h in self.plan["hallazgos"]]
        self.assertEqual(codigos, ["DO001", "DO002", "DO003"])
        self.assertEqual(self.plan["hallazgos"][1]["estado"],
                         "requiere calculo")
        self.assertIn("RED", self.plan["hallazgos"][1]["mensaje"])

    def test_conteos_deterministas_del_modelo(self):
        conteo = self.plan["conteo"]
        self.assertEqual(
            self.por_nombre["Termostato programable"]["cantidad"],
            conteo["niveles"])
        self.assertEqual(
            self.por_nombre["Central domótica (hub)"]["cantidad"], 1)
        self.assertEqual(
            self.por_nombre["Monitor de consumo"]["cantidad"], 1)
        self.assertEqual(
            self.por_nombre["Llave motorizada de corte"]["cantidad"],
            1)
        cerradura = self.por_nombre["Cerradura electrónica"]
        self.assertEqual(cerradura["cantidad"],
                         conteo["puertas_ext"])
        self.assertGreaterEqual(cerradura["cantidad"], 1)
        presencia = self.por_nombre["Sensor de presencia"]
        self.assertEqual(presencia["cantidad"],
                         conteo["pasillos"] + conteo["puertas_ext"])
        contactos = self.por_nombre["Contacto magnético"]
        self.assertEqual(contactos["cantidad"],
                         conteo["puertas_ext"]
                         + conteo["ventanas_pb"])

    def test_riego_sin_zonas_verdes(self):
        programador = self.por_nombre["Programador de riego"]
        self.assertEqual(programador["cantidad"], 0)
        self.assertEqual(programador["subtotal_cup"], 0.0)
        self.assertIn("sin zonas verdes", programador["base"])

    def test_total_igual_a_la_suma_de_subtotales(self):
        suma = round(sum(f["subtotal_cup"]
                         for f in self.plan["filas"]), 2)
        self.assertEqual(self.plan["total_equipos_cup"], suma)
        # la tabla del HTML cierra con el TOTAL formateado
        tabla = self.plan["tablas"][0]
        self.assertEqual(len(tabla["filas"]),
                         len(self.plan["filas"]) + 1)
        self.assertEqual(tabla["filas"][-1][-1],
                         f"{suma:,.0f}".replace(",", " "))

    def test_filtro_de_sistemas(self):
        from domain.vivienda_servicios import plan_domotico
        solo = plan_domotico(self.context, sistemas=["RIEGO"])
        self.assertEqual([s["sistema"] for s in solo["sistemas"]],
                         ["RIEGO"])
        self.assertEqual(solo["total_equipos_cup"], 0.0)

    def test_monitor_doble_con_solar_fv(self):
        context = self.application.create_project(
            self.project_path("solar.arqgen"), name="Casa solar")
        data = bwiz.BuildingWizardData()
        data.name = "Casa solar"
        data.usage_type = "Vivienda"
        data.vivienda_tipologia = "Unifamiliar aislada"
        data.installations = ["Eléctrica", "Energía solar"]
        bwiz.apply_usage_program(data)
        self.assertTrue(bwiz.apply_plan(data, context))
        from domain.vivienda_servicios import plan_domotico
        plan = plan_domotico(context)
        monitor = next(f for f in plan["filas"]
                       if f["nombre"] == "Monitor de consumo")
        self.assertEqual(monitor["cantidad"], 2)
        self.assertIn("solar", monitor["base"])

    def test_texto_cp1252(self):
        from domain.vivienda_servicios import texto_domotica
        texto = texto_domotica(self.plan)
        texto.encode("cp1252")
        self.assertIn("PLAN DOMÓTICO", texto)
        self.assertIn("TOTAL equipos:", texto)


class TestInformeHtmlTablas(TestBaseProyecto):
    """Las tablas genéricas del informe HTML (v3.30.0)."""

    def test_renderiza_tablas_del_informe_acustico(self):
        from domain.vivienda_servicios import analisis_acustico
        from exporters.informe_html import informe_html
        informe = analisis_acustico(self.context)
        html = informe_html(informe, "Acústica de prueba")
        self.assertIn("Pares fuente-dormitorio medidos en el trazado",
                      html)
        self.assertIn("Soluciones de referencia del §46", html)
        # todo el contenido sale escapado (las celdas no son HTML crudo)
        self.assertNotIn("<b>Partición", html)

    def test_renderiza_tabla_de_equipos_de_piscina(self):
        from domain.vivienda_servicios import calcular_piscina
        from exporters.informe_html import informe_html
        html = informe_html(calcular_piscina(8.0, 4.0, 1.0, 2.0),
                            "Piscina de prueba")
        self.assertIn("Equipos de referencia del §45", html)
        self.assertIn("PIS-BOMBA", html)
        self.assertIn("209 800", html)

    def test_sin_tablas_no_dibuja_nada(self):
        from exporters.informe_html import informe_html
        html = informe_html({"hallazgos": []}, "Sin tablas")
        self.assertNotIn("Tabla</h2>", html)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

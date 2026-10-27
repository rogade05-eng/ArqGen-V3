"""ESTUDIOS DE VIVIENDA (v3.24.0) — domain/vivienda_estudios.py.

Tres estudios del «Catálogo maestro de viviendas» operativos y de SOLO
LECTURA sobre el proyecto:

* ALTERNATIVAS COMPARABLES (§62-63): A/B/C por nivel de acabado
  (Económica/Estándar/Premium del §51 con el sistema del proyecto) y
  1/2/3/4 por sistema constructivo (mampostería confinada, hormigón
  aporticado, steel framing, modular prefabricado), cada una con las
  métricas de comparación del §63 (superficie, costo índice, tiempo,
  hormigón, acero, mampostería, madera, consumo, mantenimiento, vida
  útil, complejidad y disponibilidad) y recomendación por costo menor
  con compatibilidad >= 2/3 (§27: advierte, no bloquea).
* MODULACIÓN (§56): módulos 0.60/1.20/1.25/1.50/personalizado contra
  locales, muros, puertas y ventanas; % en módulo, residuo lineal
  acumulado y sugerencia al múltiplo inferior/superior.
* ENERGÍA SOLAR (§38): FOTOVOLTAICO / SOLAR_TERMICO / HIBRIDO con los
  parámetros de referencia del catálogo (configurables, §66) y las
  salidas del documento: paneles, potencia, batería, inversor y
  superficie; la instalación definitiva queda REQUIERE_CALCULO_
  ESPECIALIZADO (§81).

Datos de comparación (v1.1 del catálogo): bloque comparacion_sistemas
con valores de REFERENCIA visibles y editables (§66) — apreciación de
estimación, no precio oficial (misma honradez que FACTOR_CALIDAD).
"""

from __future__ import annotations

import math
import unittest
from unittest import mock

from core.errors import DomainError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


DISPLAY = _display_available()


class _Base(ARQGenTestCase):
    """Proyecto vacío con servicio de arquitectura listo."""

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("estudios.arqgen"), name="Estudios")
        self.arq = ArchitectureService(self.context)


class TestAlternativas(_Base):
    """Generación de alternativas §62-63 con métricas §63."""

    def test_siete_alternativas_por_nivel_y_sistema(self):
        from domain.vivienda_estudios import generar_alternativas
        informe = generar_alternativas(
            dormitorios=3, banos=2,
            estilo_label="Colonial cubano",
            sistema_label="Mampostería de bloque + losa de vigueta")
        claves = [a["clave"] for a in informe["alternativas"]]
        self.assertEqual(len(claves), 7)
        self.assertEqual(sorted(claves),
                         ["1", "2", "3", "4", "A", "B", "C"])
        tipos = {a["clave"]: a["tipo"] for a in informe["alternativas"]}
        self.assertEqual(tipos["A"], "nivel")
        self.assertEqual(tipos["3"], "sistema")
        # ordenadas por costo (la comparación §63 manda)
        costos = [a["costo_indice"] for a in informe["alternativas"]]
        self.assertEqual(costos, sorted(costos))

    def test_metricas_del_63_presentes_y_escaladas(self):
        from domain.vivienda_estudios import generar_alternativas
        informe = generar_alternativas(dormitorios=3, banos=2)
        alt = next(a for a in informe["alternativas"]
                   if a["clave"] == "B")
        for campo in ("superficie_m2", "costo_indice", "tiempo_meses",
                      "hormigon_m3", "acero_kg", "mamposteria_m2",
                      "madera_m3", "consumo_kwh_m2_ano",
                      "mantenimiento_pct_anual", "vida_util_anos",
                      "complejidad", "disponibilidad"):
            self.assertIn(campo, alt)
        self.assertGreater(alt["superficie_m2"], 20.0)
        self.assertGreater(alt["tiempo_meses"], 0.0)
        self.assertGreater(alt["hormigon_m3"], 0.0)
        self.assertGreater(alt["acero_kg"], 0.0)
        self.assertEqual(alt["nivel_acabado"], 2)
        # el modular es más rápido y usa menos hormigón que la
        # mampostería (valores de referencia del §63)
        mod = next(a for a in informe["alternativas"]
                   if a["sistema_clave"] == "modular")
        mam = next(a for a in informe["alternativas"]
                   if a["sistema_clave"] == "mamposteria_confinada")
        self.assertLess(mod["tiempo_meses"], mam["tiempo_meses"])
        self.assertLess(mod["hormigon_m3"], mam["hormigon_m3"])
        self.assertLess(mod["vida_util_anos"], mam["vida_util_anos"])

    def test_factores_de_nivel_con_el_sistema_del_proyecto(self):
        """A/B/C = niveles 1/2/4 (§51) sobre el costo del sistema."""
        from domain.vivienda_estudios import generar_alternativas
        informe = generar_alternativas(
            sistema_label="Mampostería de bloque + losa de vigueta")
        por_clave = {a["clave"]: a for a in informe["alternativas"]}
        self.assertAlmostEqual(por_clave["A"]["costo_indice"], 85.0,
                               places=1)
        self.assertAlmostEqual(por_clave["B"]["costo_indice"], 100.0,
                               places=1)
        self.assertAlmostEqual(por_clave["C"]["costo_indice"], 130.0,
                               places=1)
        self.assertEqual(por_clave["A"]["nivel_acabado"], 1)
        self.assertEqual(por_clave["C"]["nivel_acabado"], 4)
        # con hormigón (120) los mismos factores se aplican encima
        informe2 = generar_alternativas(
            sistema_label="Hormigón armado (monolítico)")
        b2 = next(a for a in informe2["alternativas"]
                  if a["clave"] == "B")
        self.assertAlmostEqual(b2["costo_indice"], 120.0, places=1)

    def test_compatibilidad_con_estilo_y_recomendacion(self):
        from domain.vivienda_estudios import generar_alternativas
        informe = generar_alternativas(
            estilo_label="Colonial cubano",
            sistema_label="Mampostería de bloque + losa de vigueta")
        a = next(x for x in informe["alternativas"]
                 if x["clave"] == "A")
        self.assertEqual(a["compatibilidad"], 3)  # colonial+mampostería
        self.assertEqual(informe["recomendada"], "A")
        # con estilo minimalista, el steel framing (3/3) compite con A:
        # la recomendada sigue siendo la más barata compatible
        informe2 = generar_alternativas(
            estilo_label="Minimalista")
        rec = next(x for x in informe2["alternativas"]
                   if x["clave"] == informe2["recomendada"])
        self.assertGreaterEqual(rec["compatibilidad"] or 0, 2)
        for nota in rec["notas"]:
            self.assertIn("compatibilidad", nota)

    def test_superficie_real_del_proyecto(self):
        from domain.vivienda_estudios import (generar_alternativas,
                                              _origen_superficie)
        nivel = self.arq.create_level("PB", 0.0, 3.0)
        for a, b in (((0, 0), (6, 0)), ((6, 0), (6, 5)),
                     ((6, 5), (0, 5)), ((0, 5), (0, 0))):
            self.arq.create_wall(nivel.code, a, b, 0.2)
        self.arq.create_space(nivel.code, "Sala", "LIVING_ROOM",
                              [(0, 0), (6, 0), (6, 5), (0, 5)])
        informe = generar_alternativas(ctx=self.context)
        self.assertEqual(informe["entrada"]["origen_superficie"],
                         "suma real de los locales del proyecto")
        self.assertAlmostEqual(informe["entrada"]["superficie_m2"],
                               30.0, delta=0.5)
        # y sin proyecto el origen es el programa paramétrico (§7)
        self.assertEqual(_origen_superficie(None),
                         "programa paramétrico del catálogo (§7)")

    def test_sin_catalogo_da_error_amable(self):
        from domain import vivienda_specs
        from domain.vivienda_estudios import generar_alternativas
        vivienda_specs._CATALOGO_CACHE.clear()
        with mock.patch.object(vivienda_specs, "resource_path",
                               side_effect=lambda *a: "/no/existe.json"):
            with self.assertRaises(DomainError) as ctx:
                generar_alternativas()
        self.assertEqual(ctx.exception.code, "ARQ-VIV-002")
        vivienda_specs._CATALOGO_CACHE.clear()
        self.assertIsNotNone(vivienda_specs.cargar_catalogo())

    def test_texto_cp1252(self):
        from domain.vivienda_estudios import (generar_alternativas,
                                              texto_alternativas)
        texto = texto_alternativas(generar_alternativas(
            estilo_label="Colonial cubano"))
        codificado = texto.encode("cp1252")  # no explota
        plano = codificado.decode("cp1252")
        self.assertIn("ALTERNATIVAS DE VIVIENDA", plano)
        self.assertIn("Recomendada:", plano)
        self.assertIn("Meses", plano)


class TestModulacion(_Base):
    """Modulación §56 contra locales, muros y vanos."""

    def _proyecto_piezas(self):
        from domain.vivienda_specs import _lista
        nivel = self.arq.create_level("PB", 0.0, 3.0)
        # local 4.80 x 3.60 (ambas medidas en módulo 1.20 y 0.60)
        for a, b in (((0, 0), (4.8, 0)), ((4.8, 0), (4.8, 3.6)),
                     ((4.8, 3.6), (0, 3.6)), ((0, 3.6), (0, 0))):
            self.arq.create_wall(nivel.code, a, b, 0.2)
        espacio = self.arq.create_space(
            nivel.code, "Sala", "LIVING_ROOM",
            [(0, 0), (4.8, 0), (4.8, 3.6), (0, 3.6)])
        muros = _lista(self.context, "WALL")
        muro_largo = next(m for m in muros
                          if abs(math.dist(m.start, m.end) - 4.8) < 0.01)
        puerta = self.arq.create_opening(
            "DOOR", muro_largo.code, 0.9, 2.1, offset_m=1.0)
        return espacio, puerta

    def test_local_en_modulo_1_20(self):
        from domain.vivienda_estudios import evaluar_modulacion
        self._proyecto_piezas()
        informe = evaluar_modulacion(self.context, 1.20)
        self.assertEqual(informe["modulo_nombre"], "MODULO_1.20")
        self.assertGreater(informe["total_piezas"], 0)
        # la puerta de 0.90 queda fuera del módulo 1.20; los muros y
        # el local (4.80/3.60) sí están en módulo
        bloques = [p for p in informe["piezas_fuera"]
                   if p["categoria"] == "BLOQUES"]
        self.assertEqual(bloques, [])
        self.assertGreater(informe["fuera_modulo"], 0)
        self.assertGreater(informe["desperdicio_lineal_m"], 0.0)

    def test_muro_fuera_de_modulo_con_sugerencias(self):
        from domain.vivienda_estudios import evaluar_modulacion
        nivel = self.arq.create_level("PB", 0.0, 3.0)
        self.arq.create_wall(nivel.code, (0, 0), (4.3, 0), 0.2)
        informe = evaluar_modulacion(self.context, 1.20)
        muros = [p for p in informe["piezas_fuera"]
                 if p["categoria"] == "MUROS"]
        self.assertEqual(len(muros), 1)
        self.assertAlmostEqual(muros[0]["dimension_m"], 4.3, places=2)
        # múltiplos de 1.20 alrededor de 4.30: 3.60 y 4.80
        sugeridas = muros[0]["sugerencias_m"]
        self.assertAlmostEqual(sugeridas[0], 3.6, places=2)
        self.assertAlmostEqual(sugeridas[1], 4.8, places=2)

    def test_modulo_personalizado_0_30_acierta_la_puerta(self):
        from domain.vivienda_estudios import evaluar_modulacion
        self._proyecto_piezas()
        informe = evaluar_modulacion(self.context, 0.30)
        self.assertEqual(informe["modulo_nombre"],
                         "MODULO_PERSONALIZADO")
        puertas = [p for p in informe["piezas_fuera"]
                   if p["categoria"] == "PUERTAS"]
        self.assertEqual(puertas, [])  # 0.90 es múltiplo de 0.30

    def test_modulo_invalido_da_error_amable(self):
        from domain.vivienda_estudios import evaluar_modulacion
        with self.assertRaises(DomainError) as ctx:
            evaluar_modulacion(self.context, 0.01)
        self.assertEqual(ctx.exception.code, "ARQ-EST-001")

    def test_sin_proyecto_informe_honesto(self):
        from domain.vivienda_estudios import (evaluar_modulacion,
                                              texto_modulacion)
        informe = evaluar_modulacion(None, 1.25)
        self.assertEqual(informe["total_piezas"], 0)
        self.assertEqual(informe["porcentaje_en_modulo"], 0.0)
        texto = texto_modulacion(informe).encode("cp1252")
        self.assertIn(b"sin piezas trazadas", texto)

    def test_texto_cp1252_con_piezas(self):
        from domain.vivienda_estudios import (evaluar_modulacion,
                                              texto_modulacion)
        self._proyecto_piezas()
        texto = texto_modulacion(evaluar_modulacion(self.context, 1.20))
        plano = texto.encode("cp1252").decode("cp1252")
        self.assertIn("MODULACIÓN CONSTRUCTIVA", plano)
        self.assertIn("MODULO_1.20", plano)
        self.assertIn("sugerido", plano)


class TestSolar(_Base):
    """Dimensionado solar §38 con parámetros de referencia."""

    def test_fotovoltaico_ejemplo_cerrado(self):
        from domain.vivienda_estudios import (FOTOVOLTAICO,
                                              dimensionar_solar)
        informe = dimensionar_solar(
            consumo_diario_kwh=5.0, horas_sol_pico=5.0,
            potencia_panel_w=450.0, eficiencia=0.20, perdidas=0.15,
            sistema=FOTOVOLTAICO, autonomia_dias=1.0, ocupantes=4)
        fv = informe["fv"]
        # energía por panel: 5.0 h * 0.45 kW * 0.20 * 0.85 = 0.3825
        self.assertAlmostEqual(fv["energia_panel_kwh_dia"], 0.3825,
                               places=3)
        self.assertEqual(fv["numero_paneles"],
                         math.ceil(5.0 / 0.3825))  # 14
        self.assertAlmostEqual(fv["potencia_total_kw"], 6.30, places=2)
        # batería: 5 kWh * 1 día / DoD 0.8 = 6.25 kWh
        self.assertAlmostEqual(fv["capacidad_bateria_kwh"], 6.25,
                               places=2)
        self.assertAlmostEqual(fv["potencia_inversor_kw"], 8.0,
                               places=1)
        self.assertAlmostEqual(fv["superficie_requerida_m2"], 28.0,
                               places=1)

    def test_sin_bateria_y_parametros_por_defecto_del_catalogo(self):
        from domain.vivienda_estudios import dimensionar_solar
        informe = dimensionar_solar(con_bateria=False)  # todo por defecto
        fv = informe["fv"]
        self.assertEqual(fv["capacidad_bateria_kwh"], 0.0)
        self.assertGreater(fv["numero_paneles"], 0)
        entradas = informe["entradas"]
        self.assertEqual(entradas["horas_sol_pico"], 5.0)   # §66/§70
        self.assertEqual(entradas["potencia_panel_w"], 450.0)

    def test_solar_termico_por_ocupantes(self):
        from domain.vivienda_estudios import (SOLAR_TERMICO,
                                              dimensionar_solar)
        informe = dimensionar_solar(sistema=SOLAR_TERMICO, ocupantes=5)
        self.assertNotIn("fv", informe)
        self.assertEqual(informe["termico"]["colectores_m2"], 5.0)
        self.assertEqual(informe["termico"]["tanque_l"], 250)

    def test_hibrido_lleva_ambas_partes(self):
        from domain.vivienda_estudios import HIBRIDO, dimensionar_solar
        informe = dimensionar_solar(sistema=HIBRIDO, ocupantes=4)
        self.assertIn("fv", informe)
        self.assertIn("termico", informe)

    def test_sistema_y_rangos_invalidos(self):
        from domain.vivienda_estudios import dimensionar_solar
        with self.assertRaises(DomainError) as ctx:
            dimensionar_solar(sistema="EOLICO")
        self.assertEqual(ctx.exception.code, "ARQ-SOL-001")
        with self.assertRaises(DomainError) as ctx:
            dimensionar_solar(eficiencia=5.0)  # fuera de 0.05-1.0
        self.assertEqual(ctx.exception.code, "ARQ-SOL-001")
        with self.assertRaises(DomainError) as ctx:
            dimensionar_solar(horas_sol_pico=50.0)
        self.assertEqual(ctx.exception.code, "ARQ-SOL-001")

    def test_texto_cp1252_con_marca_del_81(self):
        from domain.vivienda_estudios import (dimensionar_solar,
                                              texto_solar)
        texto = texto_solar(dimensionar_solar(ocupantes=4))
        plano = texto.encode("cp1252").decode("cp1252")
        self.assertIn("ENERGÍA SOLAR", plano)
        self.assertIn("número de paneles", plano)
        self.assertIn("REQUIERE_CALCULO_ESPECIALIZADO", plano)


class TestCatalogoEstudios(_Base):
    """El catálogo v1.1 trae los bloques de los estudios."""

    def setUp(self):
        super().setUp()
        from domain.vivienda_specs import cargar_catalogo
        self.catalogo = cargar_catalogo()

    def test_version_y_bloques_nuevos(self):
        self.assertGreaterEqual(self.catalogo.version, "1.1")
        comparar = self.catalogo.comparacion_sistemas
        self.assertEqual(comparar["sistemas"],
                         ["mamposteria_confinada", "hormigon_aporticado",
                          "steel_framing", "modular"])
        self.assertEqual(comparar["costo_indice_m2"]
                         ["mamposteria_confinada"], 100)
        self.assertEqual(comparar["vida_util_anos"]["hormigon_aporticado"],
                         60)
        energia = self.catalogo.energia_solar
        self.assertEqual(energia["sistemas"],
                         ["FOTOVOLTAICO", "SOLAR_TERMICO", "HIBRIDO"])
        self.assertEqual(energia["horas_sol_pico_defecto"], 5.0)
        self.assertEqual(energia["colector_m2_por_persona"], 1.0)

    def test_la_validacion_viv_sigue_intacta(self):
        """Los bloques nuevos no rompen las 30 validaciones."""
        from domain.vivienda_specs import validar_vivienda
        informe = validar_vivienda(self.context)
        codigos = [h["codigo"] for h in informe["hallazgos"]]
        self.assertEqual(len(codigos), 30)


@unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
class TestDialogosEstudios(_Base):
    """Los tres estudios del menú Herramientas (GUI)."""

    def _ventana(self):
        from ui.app_window import ARQGenWindow
        from ui import theme
        theme.set_mode("dark")
        window = ARQGenWindow(self.context, self.application)
        window.update()
        self.addCleanup(window.destroy)
        return window

    def test_tooltips_de_los_tres_estudios(self):
        from ui import help
        for clave in ("tools_viv_alternativas",
                      "tools_viv_modulacion",
                      "tools_viv_solar"):
            self.assertIn(clave, help.TOOLTIPS)
            texto = help.TOOLTIPS[clave].encode("cp1252")

    def test_dialogo_alternativas(self):
        window = self._ventana()
        window.alternativas_vivienda_informe()
        dialogo = window._alternativas_dialogo
        texto = dialogo._alt_texto.get("1.0", "end")
        self.assertIn("ALTERNATIVAS DE VIVIENDA", texto)
        self.assertIn("Recomendada:", texto)
        dialogo.destroy()

    def test_dialogo_modulacion(self):
        window = self._ventana()
        window.modulacion_informe()
        dialogo = window._modulacion_dialogo
        texto = dialogo._mod_texto.get("1.0", "end")
        self.assertIn("MODULACIÓN CONSTRUCTIVA", texto)
        dialogo.destroy()

    def test_dialogo_solar(self):
        window = self._ventana()
        window.solar_informe()
        dialogo = window._solar_dialogo
        texto = dialogo._sol_texto.get("1.0", "end")
        self.assertIn("ENERGÍA SOLAR", texto)
        self.assertIn("REQUIERE_CALCULO_ESPECIALIZADO", texto)
        dialogo.destroy()


if __name__ == "__main__":
    unittest.main()

"""CATÁLOGO MAESTRO DE VIVIENDAS (v3.23.0) — domain/vivienda_specs.py,
resources/knowledge/vivienda_catalogo.json y las capas que alimentan.

El documento del usuario («Especificación técnica programable: catálogo
maestro de viviendas», 81 secciones) entra al programa como datos:

* 30 tipologías VIV-01..30, 25 sistemas constructivos TC, 20
  estructurales EST y 30 estilos con sus reglas (§26).
* Matriz de compatibilidad estilo x sistema (escala 0-3 del §27: los
  pares literales del documento más los razonados según sus reglas;
  advierte, NUNCA bloquea).
* Rangos de locales del §7 y relaciones del §8 (0-3 y X) que alimentan
  el PROGRAMA PARAMÉTRICO de vivienda del asistente de edificación,
  más la zonificación Z001-Z008 (§9).
* 30 validaciones VIV001-030 (§54) sobre el proyecto con estados
  honestos: medido, pendiente (configurable del §66) o
  REQUIERE_CALCULO_ESPECIALIZADO (§81).
* 15 conflictos del §65 con su validación equivalente, niveles de
  acabado 1-5 (§51), progresiva (§57), jurisdicciones (§69) y MODO
  CUBA (§70).
* Calidades del presupuesto vivo ampliadas a 5 (Media y Lujo).
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from core.errors import DomainError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

from ui import building_wizard as bwiz
from ui import variant_budget as vbudget


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
            self.project_path("vivienda.arqgen"), name="Vivienda")
        self.arq = ArchitectureService(self.context)


class TestCatalogo(_Base):
    """El documento integrado: listas, matriz, rangos y validaciones."""

    def setUp(self):
        super().setUp()
        from domain.vivienda_specs import cargar_catalogo
        self.catalogo = cargar_catalogo()

    def test_documento_carga_y_esta_completo(self):
        self.assertIsNotNone(self.catalogo)
        self.assertEqual(len(self.catalogo.tipologias), 30)
        self.assertEqual(len(self.catalogo.sistemas), 25)
        self.assertEqual(len(self.catalogo.estructurales), 20)
        self.assertEqual(len(self.catalogo.estilos), 30)
        self.assertEqual(len(self.catalogo.rangos), 21)
        self.assertEqual(len(self.catalogo.relaciones), 17)
        self.assertEqual(len(self.catalogo.validaciones), 30)
        self.assertEqual(len(self.catalogo.conflictos), 15)
        self.assertEqual(len(self.catalogo.zonificacion["reglas"]), 8)
        self.assertTrue(self.catalogo.advertencia)
        self.assertIn("REQUIERE_CALCULO_ESPECIALIZADO",
                      str(self.catalogo.principio.get("marca", "")))

    def test_carga_cacheada(self):
        from domain.vivienda_specs import cargar_catalogo
        self.assertIs(cargar_catalogo(), self.catalogo)

    def test_compatibilidad_escala_0_a_3(self):
        pares = self.catalogo.compatibilidad["pares"]
        self.assertEqual(pares["colonial|mamposteria"], 3)
        self.assertEqual(pares["minimalista|adobe"], 0)
        self.assertEqual(pares["moderno|madera"], 3)
        self.assertEqual(pares["industrial|acero"], 3)
        self.assertIsNone(self.catalogo.nivel_compatibilidad(
            "estilo_inexistente", "mamposteria"))
        self.assertEqual(self.catalogo.texto_compatibilidad(3),
                         "altamente compatible")
        self.assertEqual(self.catalogo.texto_compatibilidad(0),
                         "incompatible")

    def test_compatibilidad_con_los_nombres_de_la_gui(self):
        from domain.vivienda_specs import compatibilidad_gui
        self.assertEqual(compatibilidad_gui(
            "Colonial cubano",
            "Mampostería de bloque + losa de vigueta"), 3)
        self.assertEqual(compatibilidad_gui(
            "Minimalista", "Tierra (adobe o tapial)"), 0)
        self.assertIsNone(compatibilidad_gui("Posmoderno",
                                             "Tierra (adobe o tapial)"))

    def test_etiquetas_y_claves_de_tipologias(self):
        etiquetas = self.catalogo.etiquetas_tipologias()
        self.assertEqual(len(etiquetas), 30)
        duplex = self.catalogo.tipologia_de_etiqueta("Dúplex")
        self.assertEqual(duplex["clave"], "duplex")
        progresiva = self.catalogo.tipologia_de_etiqueta("Progresiva")
        self.assertEqual(progresiva["codigo"], "VIV-22")
        self.assertEqual(
            self.catalogo.tipologia_por_clave("aislada")["codigo"],
            "VIV-01")

    def test_rangos_del_parrafo_7(self):
        sala = self.catalogo.rango("SALA")
        self.assertEqual(sala["min"], 16.0)
        self.assertEqual(sala["max"], 35.0)
        self.assertEqual(sala["space_type"], "LIVING_ROOM")
        garaje = self.catalogo.rango("GARAJE")
        self.assertIn("por vehículo", garaje["texto"])
        social = self.catalogo.rango("BANOS_SOCIAL")
        self.assertEqual(social["space_type"], "BATHROOM")
        principal = self.catalogo.rango("DORMITORIO_PRINCIPAL")
        self.assertEqual(principal["min"], 14.0)

    def test_relaciones_del_parrafo_8(self):
        self.assertEqual(
            self.catalogo.nivel_de_relacion("BAÑO", "COMEDOR"), "X")
        self.assertEqual(
            self.catalogo.nivel_de_relacion("SALA", "VESTIBULO"), "3")
        self.assertEqual(
            self.catalogo.nivel_de_relacion("COCINA", "DESPENSA"), "2")
        self.assertIsNone(self.catalogo.nivel_de_relacion(
            "SALA", "PISCINA"))

    def test_validaciones_conflictos_y_progresiva(self):
        viv019 = self.catalogo.regla_validacion("VIV019")
        self.assertEqual(viv019["modo"], "medido")
        viv017 = self.catalogo.regla_validacion("VIV017")
        self.assertEqual(viv017["modo"], "calculo")
        conflicto = next(c for c in self.catalogo.conflictos
                         if c["codigo"] == "CONFLICTO_05")
        self.assertEqual(conflicto["viv"], "VIV008")
        fases = self.catalogo.progresiva["fases"]
        self.assertEqual(len(fases), 5)
        self.assertIn("mínima habitable", fases[0]["nombre"])
        self.assertIn("CUBA", self.catalogo.jurisdicciones["lista"])
        self.assertIn("PERSONALIZADA",
                      self.catalogo.jurisdicciones["lista"])
        niveles = self.catalogo.niveles_acabado["niveles"]
        self.assertEqual([n["nombre"] for n in niveles],
                         ["Económico", "Estándar", "Medio", "Premium",
                          "Lujo"])
        self.assertIn("PISOS", self.catalogo.niveles_acabado["modifica"])

    def test_formato_invalido_rechazado(self):
        from domain.vivienda_specs import ViviendaCatalogo
        malo = os.path.join(self.tmp, "malo.json")
        with open(malo, "w", encoding="utf-8") as fh:
            json.dump({"format": "OTRO"}, fh)
        with self.assertRaises(DomainError) as ctx:
            ViviendaCatalogo.load_file(malo)
        self.assertEqual(ctx.exception.code, "ARQ-VIV-001")


class TestProgramaParametrico(ARQGenTestCase):
    """El asistente de edificación genera la vivienda del catálogo."""

    def _data(self, tipologia="Unifamiliar aislada", dormitorios=4,
              banos=2):
        data = bwiz.BuildingWizardData()
        data.name = "Casa de prueba"
        data.usage_type = "Vivienda"
        data.vivienda_tipologia = tipologia
        data.vivienda_dormitorios = dormitorios
        data.vivienda_banos = banos
        return data

    def test_choices_con_clasica_y_treinta(self):
        choices = bwiz.vivienda_tipologia_choices()
        self.assertEqual(choices[0], bwiz.VIVIENDA_TIPOLOGIA_CLASICA)
        self.assertEqual(len(choices), 31)
        self.assertIn("Progresiva", choices)
        self.assertIn("Multigeneracional", choices)

    def test_programa_aislada_con_rangos_y_relaciones(self):
        data = self._data()
        locales, relaciones = bwiz.apply_usage_program(data)
        nombres = [r.name for r in data.rooms]
        self.assertEqual(locales, 13)
        self.assertGreater(relaciones, 10)
        for esperado in ("Vestíbulo", "Sala", "Comedor", "Cocina",
                         "Dormitorio principal", "Dormitorio 4",
                         "Baño principal", "Baño social", "Lavandería",
                         "Despensa", "Garaje"):
            self.assertIn(esperado, nombres)
        sala = data.room("Sala")
        area = sala.width_m * sala.depth_m
        self.assertGreaterEqual(area, 16.0 - 0.5)   # rango §7: 16-35
        self.assertLessEqual(area, 35.0 + 0.5)
        puerta_sala = next(r for r in data.relations
                           if {r.a_name, r.b_name} == {"Sala",
                                                       "Vestíbulo"})
        self.assertEqual(puerta_sala.kind_es, "Comunicado con")
        self.assertTrue(puerta_sala.with_door)
        # la relación X del §8 (baño-comedor) NO se genera
        self.assertFalse(any(
            {"Baño", "Comedor"} & {r.a_name, r.b_name}
            and {"Baño", "Comedor"} <= {r.a_name, r.b_name}
            for r in data.relations))

    def test_programa_clasico_intacto(self):
        data = self._data(tipologia=bwiz.VIVIENDA_TIPOLOGIA_CLASICA)
        bwiz.apply_usage_program(data)
        self.assertEqual(len(data.rooms), 6)
        self.assertEqual(data.room("Sala").width_m, 4.0)

    def test_duplex_parte_social_y_privada(self):
        data = self._data(tipologia="Dúplex")
        bwiz.apply_usage_program(data)
        self.assertEqual([lv.name for lv in data.levels][:2],
                         ["Planta Baja", "Planta Alta"])
        principal = data.room("Dormitorio principal")
        self.assertEqual(principal.level_ref, "Planta Alta")
        self.assertEqual(data.room("Sala").level_ref, "Planta Baja")

    def test_multigeneracional_y_progresiva_con_extras(self):
        data = self._data(tipologia="Multigeneracional", dormitorios=3)
        bwiz.apply_usage_program(data)
        nombres = [r.name for r in data.rooms]
        self.assertIn("Suite abuelos", nombres)
        self.assertIn("Baño suite abuelos", nombres)
        data2 = self._data(tipologia="Progresiva", dormitorios=1)
        bwiz.apply_usage_program(data2)
        self.assertIn("Cuarto técnico",
                      [r.name for r in data2.rooms])
        self.assertEqual(len(data2.rooms), 10)  # 1 dormitorio + 2 baños

    def test_validacion_de_entradas(self):
        data = self._data()
        data.vivienda_dormitorios = 0
        errores = bwiz.validate_step(0, data)
        self.assertTrue(any("1 a 6" in e for e in errores))
        data2 = self._data(tipologia="Tipología inventada")
        self.assertTrue(any("tipología de vivienda" in e
                            for e in bwiz.validate_step(0, data2)))
        data3 = self._data()
        errores3 = bwiz.data_from_values(0, {
            "vivienda_tipologia": "Vivienda progresiva",
            "vivienda_dormitorios": "5",
            "vivienda_banos": "3",
        }, data3)
        self.assertEqual(errores3, [])
        self.assertEqual(data3.vivienda_tipologia,
                         "Vivienda progresiva")
        self.assertEqual(data3.vivienda_dormitorios, 5)
        self.assertEqual(data3.vivienda_banos, 3)

    def test_metadata_y_roundtrip(self):
        data = self._data()
        metadata = bwiz._building_metadata(data)
        self.assertEqual(metadata["edificacion"]["vivienda"],
                         {"tipologia": "Unifamiliar aislada",
                          "dormitorios": 4, "banos": 2})


class TestAvisos(ARQGenTestCase):
    """vivienda_advisories: compatibilidad §27 y reglas de tipología."""

    def _data(self, tipologia="Unifamiliar aislada", estilo="Contemporáneo",
              sistema="Hormigón armado (monolítico)"):
        data = bwiz.BuildingWizardData()
        data.name = "Casa"
        data.usage_type = "Vivienda"
        data.vivienda_tipologia = tipologia
        data.architectural_style = estilo
        data.construction_type = sistema
        return data

    def test_compatibilidad_baja_avisa_sin_bloquear(self):
        avisos = bwiz.vivienda_advisories(self._data(
            estilo="Minimalista", sistema="Tierra (adobe o tapial)"))
        self.assertTrue(any("0/3" in a and "no bloquea" in a
                            for a in avisos))
        self.assertTrue(any("incompatible" in a for a in avisos))

    def test_compatibilidad_alta_calla(self):
        avisos = bwiz.vivienda_advisories(self._data(
            estilo="Colonial cubano",
            sistema="Mampostería de bloque + losa de vigueta"))
        self.assertFalse(any("/3" in a for a in avisos))

    def test_reglas_de_tipologia(self):
        self.assertTrue(any("medianera" in a.lower()
                            for a in bwiz.vivienda_advisories(
                                self._data(tipologia="Unifamiliar pareada"))))
        self.assertTrue(any("UFA001" in a
                            for a in bwiz.vivienda_advisories(self._data())))
        progresiva = bwiz.vivienda_advisories(
            self._data(tipologia="Vivienda progresiva"))
        self.assertTrue(any("F1" in a and "F5" in a
                            for a in progresiva))
        self.assertTrue(any("cimentación" in a for a in progresiva))

    def test_z005_bano_con_puerta_a_comedor(self):
        data = self._data()
        bwiz.apply_usage_program(data)
        data.relations.append(bwiz.RelationSpec(
            a_name="Baño principal", b_name="Comedor",
            kind_es="Comunicado con", with_door=True))
        avisos = bwiz.vivienda_advisories(data)
        self.assertTrue(any("Z005" in a for a in avisos))

    def test_clasico_y_otros_usos_callan(self):
        data = self._data(tipologia=bwiz.VIVIENDA_TIPOLOGIA_CLASICA)
        self.assertEqual(bwiz.vivienda_advisories(data), [])
        data2 = self._data()
        data2.usage_type = "Hospital"
        self.assertEqual(bwiz.vivienda_advisories(data2), [])

    def test_resumen_del_asistente_menciona_la_tipologia(self):
        data = self._data()
        bwiz.apply_usage_program(data)
        texto = bwiz.step_summary(data)
        self.assertIn("Unifamiliar aislada", texto)
        self.assertIn("3 dormitorios, 2 baños", texto)


class TestValidarVivienda(_Base):
    """Las 30 comprobaciones VIV001-030 sobre un proyecto generado."""

    def _proyecto_generado(self):
        data = bwiz.BuildingWizardData()
        data.name = "Casa de Marta"
        data.usage_type = "Vivienda"
        data.vivienda_tipologia = "Unifamiliar aislada"
        data.vivienda_dormitorios = 3
        data.vivienda_banos = 2
        data.lot_width_m = 12.0
        data.lot_depth_m = 30.0
        data.architectural_style = "Colonial cubano"
        data.construction_type = "Mampostería de bloque + losa de vigueta"
        bwiz.apply_usage_program(data)
        creado = bwiz.apply_plan(data, self.context)
        self.assertTrue(creado)
        return data

    def test_informe_completo_sobre_proyecto_generado(self):
        self._proyecto_generado()
        from domain.vivienda_specs import validar_vivienda
        informe = validar_vivienda(self.context)
        codigos = [h["codigo"] for h in informe["hallazgos"]]
        self.assertEqual(len(codigos), 30)
        self.assertEqual(len(set(codigos)), 30)
        self.assertEqual(informe["tipologia"], "Unifamiliar aislada")
        self.assertEqual(informe["estilo"], "Colonial cubano")
        self.assertEqual(informe["resumen"]["fallos"], 0)
        # VIV019: colonial + mampostería = 3 (altamente compatible)
        viv019 = next(h for h in informe["hallazgos"]
                      if h["codigo"] == "VIV019")
        self.assertEqual(viv019["severidad"], "ok")
        self.assertIn("altamente compatible", viv019["mensaje"])
        # honestidad §81: puesta a tierra, suelo y cargas piden cálculo
        for codigo in ("VIV013", "VIV017", "VIV018"):
            hallazgo = next(h for h in informe["hallazgos"]
                            if h["codigo"] == codigo)
            self.assertEqual(hallazgo["estado"], "requiere calculo")
        # dormitorios y baños con ventana -> VIV007 y VIV008 cumplen
        self.assertEqual(
            next(h for h in informe["hallazgos"]
                 if h["codigo"] == "VIV007")["severidad"], "ok")
        self.assertEqual(
            next(h for h in informe["hallazgos"]
                 if h["codigo"] == "VIV008")["severidad"], "ok")
        # locales con categoría y servidos (pasillo/relaciones)
        self.assertEqual(
            next(h for h in informe["hallazgos"]
                 if h["codigo"] == "VIV024")["severidad"], "ok")
        self.assertEqual(
            next(h for h in informe["hallazgos"]
                 if h["codigo"] == "VIV030")["severidad"], "ok")
        # parcela 12x30: huella y área libre medidas
        viv001 = next(h for h in informe["hallazgos"]
                      if h["codigo"] == "VIV001")
        self.assertEqual(viv001["severidad"], "ok")
        self.assertIn("360.0", viv001["mensaje"])

    def test_dormitorio_ciego_falla_viv007_y_viv030(self):
        """Un dormitorio sin vano alguno: VIV007 y VIV030 lo señalan."""
        from domain.vivienda_specs import validar_vivienda
        nivel = self.arq.create_level("PB", 0.0, 3.0)
        for a, b in (((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 4.0)),
                     ((5.0, 4.0), (0.0, 4.0)), ((0.0, 4.0), (0.0, 0.0))):
            self.arq.create_wall(nivel.code, a, b, 0.2)
        self.arq.create_space(nivel.code, "Dormitorio ciego", "BEDROOM",
                              [(0.0, 0.0), (5.0, 0.0), (5.0, 4.0),
                               (0.0, 4.0)])
        informe = validar_vivienda(self.context)
        viv007 = next(h for h in informe["hallazgos"]
                      if h["codigo"] == "VIV007")
        self.assertEqual(viv007["severidad"], "fallo")
        self.assertIn("Dormitorio ciego", viv007["mensaje"])
        viv030 = next(h for h in informe["hallazgos"]
                      if h["codigo"] == "VIV030")
        self.assertEqual(viv030["severidad"], "fallo")
        resumen = informe["resumen"]
        self.assertGreaterEqual(resumen["fallos"], 2)

    def test_texto_cp1252_y_resumen(self):
        self._proyecto_generado()
        from domain.vivienda_specs import (validar_vivienda,
                                           texto_validacion_vivienda)
        texto = texto_validacion_vivienda(validar_vivienda(self.context))
        codificado = texto.encode("cp1252")  # no explota
        self.assertIn("VALIDACIÓN DE VIVIENDA", codificado.decode("cp1252"))
        self.assertIn("VIV019", texto)
        self.assertIn("REQUIERE_CALCULO_ESPECIALIZADO", texto)
        self.assertIn("Resumen:", texto)

    def test_sin_catalogo_da_error_amable(self):
        from domain import vivienda_specs
        vivienda_specs._CATALOGO_CACHE.clear()
        with mock.patch.object(vivienda_specs, "resource_path",
                               side_effect=lambda *a: "/no/existe.json"):
            with self.assertRaises(DomainError) as ctx:
                vivienda_specs.validar_vivienda(self.context)
        self.assertEqual(ctx.exception.code, "ARQ-VIV-002")
        vivienda_specs._CATALOGO_CACHE.clear()
        self.assertIsNotNone(vivienda_specs.cargar_catalogo())

    def test_calidades_cinco_niveles(self):
        self.assertEqual(len(vbudget.CALIDADES), 5)
        self.assertEqual(
            vbudget.CALIDADES,
            ("Económica", "Media", "Estándar", "Premium", "Lujo"))
        self.assertEqual(vbudget.FACTOR_CALIDAD["Media"], 0.95)
        self.assertEqual(vbudget.FACTOR_CALIDAD["Lujo"], 1.60)
        self.assertEqual(vbudget.FACTOR_CALIDAD["Económica"], 0.85)
        # las tres históricas conservan su factor
        self.assertEqual(vbudget.FACTOR_CALIDAD["Premium"], 1.30)
        self.assertEqual(vbudget.FACTOR_CALIDAD["Estándar"], 1.0)


@unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
class TestDialogoValidacion(_Base):
    """El menú «Validar vivienda» muestra el informe (GUI)."""

    def _ventana(self):
        from ui.app_window import ARQGenWindow
        from ui import theme
        theme.set_mode("dark")
        window = ARQGenWindow(self.context, self.application)
        window.update()
        self.addCleanup(window.destroy)
        return window

    def test_menu_y_dialogo_con_informe(self):
        from ui import help
        self.assertIn("bld_viv_tip", help.TOOLTIPS)
        self.assertIn("bld_viv_dorm", help.TOOLTIPS)
        window = self._ventana()
        window.validar_vivienda_informe()
        dialogo = window._validar_vivienda_dialogo
        texto = dialogo._viv_texto.get("1.0", "end")
        self.assertIn("VALIDACIÓN DE VIVIENDA", texto)
        self.assertIn("VIV030", texto)
        self.assertIn("Resumen:", texto)
        dialogo.destroy()


if __name__ == "__main__":
    unittest.main()

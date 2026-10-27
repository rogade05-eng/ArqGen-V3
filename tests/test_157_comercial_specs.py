"""Documento comercial CC/OF (v3.25.0): datos, asistente, validación,
equipos de referencia y GUI.

Cubre la integración del documento «Especificaciones técnicas y
dimensionales - Centros Comerciales y Edificios de Oficinas» v2.0
(104 secciones): comercial_specs.json (20 tipologías, 59 cuadros
MIN/REC, relaciones §78 con prohibiciones, programas §89-90,
porcentajes §81, eficiencia §82, conflictos §95, prioridades P01-P12,
normativa §97 y fuentes §98 IBC 2024), los usos «Centro comercial» y
«Oficinas (torre/corporativo)» del asistente con el programa mínimo y
las relaciones, validar_local/validar_proyecto con estados honestos,
los equipos de referencia sin calidad del presupuesto y el diálogo
«Validar centro comercial / oficinas».
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from core.errors import DomainError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

from domain import comercial_specs as cs
from ui import building_wizard as bw
from ui import variant_budget as vb


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
            self.project_path("comercial.arqgen"), name="Comercial")
        self.arq = ArchitectureService(self.context)

    def _proyecto_cc(self, tipologia: str = ""):
        """Genera un centro comercial completo con el asistente."""
        data = bw.BuildingWizardData()
        data.name = "Galería del Este"
        data.usage_type = bw.USO_COMERCIAL_CC
        if tipologia:
            data.comercial_tipologia = tipologia
        bw.apply_usage_program(data)
        creado = bw.apply_plan(data, self.context)
        self.assertTrue(creado)
        return data


class TestAsistente(_Base):
    """Los usos CC/OF cargan el programa §89-90 en el asistente."""

    def test_combo_de_tipologias(self):
        choices = bw.comercial_tipologia_choices()
        self.assertEqual(len(choices), 21)
        self.assertEqual(choices[0], bw.COMERCIAL_SIN_TIPOLOGIA)
        self.assertIn("CC-01 - Galería comercial pequeña", choices)
        self.assertIn("OF-04 - Torre de oficinas", choices)

    def test_programa_de_centro_comercial(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_CC
        n, r = bw.apply_usage_program(data)
        self.assertEqual(n, 13)
        self.assertGreaterEqual(r, 6)
        tipos = {room.space_type for room in data.rooms}
        self.assertTrue({"GALLERY", "RETAIL_LOCAL", "TIENDA_ANCLA",
                         "BATHROOM", "WAREHOUSE", "LOADING_DOCK",
                         "WASTE_ROOM", "PARKING",
                         "SECURITY_ROOM"} <= tipos)
        # escaleras y núcleos no entran al árbol: los traza el motor
        self.assertNotIn("STAIR", tipos)
        self.assertNotIn("CORE", tipos)
        # relaciones del §78: galería comunicada con locales y acceso
        # en cadena con el vestíbulo
        par = {(rel.a_name, rel.b_name): rel for rel in data.relations}
        cadena = par.get(("Acceso", "Vestíbulo"))
        self.assertIsNotNone(cadena)
        self.assertTrue(cadena.with_door)
        galeria_locales = par.get(("Galería principal",
                                   "Locales comerciales"))
        self.assertIsNotNone(galeria_locales)
        self.assertTrue(galeria_locales.with_door)
        galeria_sanitarios = par.get(("Galería principal",
                                      "Sanitarios públicos"))
        self.assertIsNotNone(galeria_sanitarios)
        self.assertFalse(galeria_sanitarios.with_door)

    def test_medidas_de_los_cuadros(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_CC
        bw.apply_usage_program(data)
        por_nombre = {room.name: room for room in data.rooms}
        galeria = por_nombre["Galería principal"]
        self.assertGreaterEqual(galeria.width_m, 3.0)
        self.assertGreaterEqual(galeria.width_m * galeria.depth_m, 12.0)
        ancla = por_nombre["Tienda ancla"]
        self.assertGreaterEqual(ancla.width_m * ancla.depth_m, 500.0)
        local = por_nombre["Locales comerciales"]
        self.assertGreaterEqual(local.width_m * local.depth_m, 15.0)
        self.assertGreaterEqual(local.width_m, 3.0)
        residuos = por_nombre["Residuos"]
        self.assertFalse(residuos.with_window)
        self.assertTrue(local.with_window)

    def test_oficinas_con_planta_tipo_en_la_torre(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_OF
        data.comercial_tipologia = "OF-04 - Torre de oficinas"
        n, _r = bw.apply_usage_program(data)
        self.assertEqual(n, 16)
        self.assertEqual([lv.name for lv in data.levels],
                         ["Planta Baja", "Planta 1"])
        por_nivel: dict = {}
        for room in data.rooms:
            por_nivel.setdefault(room.level_ref, []).append(room.name)
        self.assertIn("Oficinas", por_nivel["Planta 1"])
        self.assertIn("Planta abierta", por_nivel["Planta 1"])
        self.assertIn("Recepción", por_nivel["Planta Baja"])
        # tipología no vertical: todo en planta baja
        data2 = bw.BuildingWizardData()
        data2.usage_type = bw.USO_COMERCIAL_OF
        bw.apply_usage_program(data2)
        self.assertEqual([lv.name for lv in data2.levels],
                         ["Planta Baja"])

    def test_validacion_y_parseo_de_la_tipologia(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_CC
        data.comercial_tipologia = "tipología inventada"
        errores = bw.validate_step(0, data)
        self.assertTrue(any("documento comercial" in e for e in errores))
        data.comercial_tipologia = "CC-02 - Centro comercial mediano"
        errores = bw.validate_step(0, data)
        self.assertFalse(any("documento comercial" in e for e in errores))
        # parseo del formulario del paso 1
        data2 = bw.BuildingWizardData()
        bw.data_from_values(0, {"usage_type": bw.USO_COMERCIAL_OF,
                                "comercial_tipologia":
                                    "OF-04 - Torre de oficinas"}, data2)
        self.assertEqual(data2.comercial_tipologia,
                         "OF-04 - Torre de oficinas")

    def test_metadata_y_resumen_del_asistente(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_CC
        data.comercial_tipologia = "CC-02 - Centro comercial mediano"
        metadata = bw._building_metadata(data)
        comercial = metadata["edificacion"]["comercial"]
        self.assertEqual(comercial["familia"], "CENTRO_COMERCIAL")
        self.assertEqual(comercial["tipologia"],
                         "CC-02 - Centro comercial mediano")
        resumen = bw.step_summary(data)
        self.assertIn("CC-02", resumen)
        self.assertIn("§89-90", resumen)

    def test_avisos_comerciales(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_CC
        avisos = bw.comercial_advisories(data)
        self.assertTrue(any("Escaleras mecánicas" in a for a in avisos))
        self.assertTrue(any("§78/§95" in a for a in avisos))
        data_of = bw.BuildingWizardData()
        data_of.usage_type = bw.USO_COMERCIAL_OF
        data_of.comercial_tipologia = "OF-04 - Torre de oficinas"
        avisos_of = bw.comercial_advisories(data_of)
        self.assertTrue(any("planta tipo" in a for a in avisos_of))
        self.assertTrue(any("IBC 2024" in a for a in avisos_of))
        data_mixto = bw.BuildingWizardData()
        data_mixto.usage_type = bw.USO_COMERCIAL_CC
        data_mixto.comercial_tipologia = "CC-07 - Centro comercial " \
                                         "+ oficinas"
        self.assertTrue(any("§85" in a
                            for a in bw.comercial_advisories(data_mixto)))
        data_viv = bw.BuildingWizardData()
        data_viv.usage_type = "Vivienda"
        self.assertEqual(bw.comercial_advisories(data_viv), [])

    def test_program_from_project_restaura_la_tipologia(self):
        data = self._proyecto_cc("CC-03 - Centro comercial grande")
        data2, _avisos = bw.program_from_project(self.context)
        self.assertEqual(data2.usage_type, bw.USO_COMERCIAL_CC)
        self.assertEqual(data2.comercial_tipologia,
                         "CC-03 - Centro comercial grande")


class TestValidacion(_Base):
    """validar_local y validar_proyecto con estados honestos."""

    def test_informe_del_proyecto_generado(self):
        self._proyecto_cc()
        informe = cs.validar_proyecto(self.context)
        self.assertEqual(informe["familias"], ["CENTRO_COMERCIAL"])
        self.assertEqual(informe["uso"], "Centro comercial")
        mapa = {h["codigo"]: h for h in informe["hallazgos"]}
        self.assertEqual(mapa["CM01"]["severidad"], "ok")
        self.assertIn("§89-90", mapa["CM01"]["mensaje"])
        self.assertEqual(mapa["CM02"]["severidad"], "ok")
        self.assertEqual(mapa["CM03"]["severidad"], "ok")
        self.assertIn("2.40", mapa["CM06"]["mensaje"])
        self.assertIn("3.60", mapa["CM06"]["mensaje"])
        rc = [h for h in informe["hallazgos"]
              if h["codigo"].startswith("RC")]
        self.assertEqual(len(rc), 8)
        self.assertTrue(all(h["estado"] == "requiere calculo"
                            for h in rc))
        self.assertTrue(rc[0]["mensaje"].startswith("CLIMATIZACION"))
        # prioridades, conflictos, normativa y fuentes en el informe
        self.assertEqual(informe["prioridades"]["P01"],
                         "SEGURIDAD DE VIDA")
        self.assertEqual(len(informe["conflictos"]), 7)
        self.assertIn("IBC 2024", " | ".join(informe["fuentes"]))
        # los locales entran al informe con su control dimensional
        self.assertTrue(informe["locales"])
        galeria = next(l for l in informe["locales"]
                       if l["nombre"] == "Galería principal")
        codigos = {h["codigo"]: h for h in galeria["hallazgos"]}
        self.assertEqual(codigos["C01"]["severidad"], "ok")
        self.assertEqual(codigos["C03"]["severidad"], "ok")

    def test_local_escaso_es_senalado_con_su_minimo(self):
        self._proyecto_cc()
        nivel = self.arq.create_level("Planta Prueba", 10.0, 3.0)
        self.arq.create_space(nivel.code, "Local escaso", "RETAIL_LOCAL",
                              [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0),
                               (0.0, 2.0)])
        self.context.commit()
        espacios = [s for s in self.context.architecture.list(
            "SPACE", self.context.project.id)
            if getattr(s, "space_type", "") == "RETAIL_LOCAL"]
        escaso = next(s for s in espacios if s.name == "Local escaso")
        informe = cs.validar_local(self.context, escaso.id)
        codigos = {h["codigo"]: h for h in informe["hallazgos"]}
        self.assertEqual(codigos["C01"]["severidad"], "fallo")
        self.assertIn("15.00", codigos["C01"]["mensaje"])
        self.assertIn("gamas recomendadas", codigos["C01"]["mensaje"])
        # sin puertas: aviso honesto (no fallo silencioso)
        self.assertEqual(codigos["C04"]["severidad"], "aviso")
        self.assertIn("no tiene puertas", codigos["C04"]["mensaje"])
        # el proyecto entero también lo cuenta
        global_inf = cs.validar_proyecto(self.context)
        con_fallos = [l for l in global_inf["locales"]
                      if any(h["severidad"] == "fallo"
                             for h in l["hallazgos"])]
        self.assertTrue(any(l["nombre"] == "Local escaso"
                            for l in con_fallos))

    def test_porcentajes_y_eficiencia_se_evaluan(self):
        self._proyecto_cc()
        informe = cs.validar_proyecto(self.context)
        mapa = {h["codigo"]: h for h in informe["hallazgos"]}
        self.assertIn("CM04", mapa)
        self.assertIn("CM05", mapa)
        # el porcentaje de administración del programa base queda bajo
        # el rango del §81: el documento avisa, no bloquea
        self.assertEqual(mapa["CM04"]["severidad"], "aviso")
        self.assertIn("§81", mapa["CM04"]["mensaje"])

    def test_prohibicion_residuos_contra_publico_se_senala(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_CC
        bw.apply_usage_program(data)
        data.relations.append(bw.RelationSpec(
            a_name="Residuos", b_name="Galería principal",
            kind_es="Comunicado con", with_door=True))
        bw.apply_plan(data, self.context)
        informe = cs.validar_proyecto(self.context)
        cm03 = next(h for h in informe["hallazgos"]
                    if h["codigo"] == "CM03")
        self.assertEqual(cm03["severidad"], "fallo")
        self.assertIn("§78", cm03["mensaje"])

    def test_programa_incompleto_avisaria(self):
        # proyecto a mano con galería y baño: el §89 pide más locales
        nivel = self.arq.create_level("Planta Baja", 0.0, 3.2)
        self.arq.create_space(nivel.code, "Galería", "GALLERY",
                              [(0.0, 0.0), (12.0, 0.0), (12.0, 4.0),
                               (0.0, 4.0)])
        self.arq.create_space(nivel.code, "Baño", "BATHROOM",
                              [(12.0, 0.0), (16.0, 0.0), (16.0, 2.0),
                               (12.0, 2.0)])
        self.context.commit()
        informe = cs.validar_proyecto(self.context)
        # sin metadata del asistente, la huella GALLERY infiere la familia
        self.assertEqual(informe["familias"], ["CENTRO_COMERCIAL"])
        cm01 = next(h for h in informe["hallazgos"]
                    if h["codigo"] == "CM01")
        self.assertEqual(cm01["severidad"], "aviso")
        self.assertIn("falta", cm01["mensaje"])

    def test_oficinas_sin_falsas_prohibiciones(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_OF
        data.comercial_tipologia = "OF-04 - Torre de oficinas"
        bw.apply_usage_program(data)
        bw.apply_plan(data, self.context)
        informe = cs.validar_proyecto(self.context)
        self.assertEqual(informe["familias"], ["OFICINAS"])
        mapa = {h["codigo"]: h for h in informe["hallazgos"]
                if h["codigo"].startswith("CM")}
        # la relación OFICINAS-SERVIDORES del §78 (nivel 2) NO es la
        # prohibición TECNICOS-PUBLICO: el puesto de trabajo no es público
        self.assertEqual(mapa["CM03"]["severidad"], "ok")
        self.assertEqual(mapa["CM01"]["severidad"], "ok")

    def test_texto_cp1252_del_informe(self):
        self._proyecto_cc()
        informe = cs.validar_proyecto(self.context)
        texto = cs.texto_validacion_comercial(informe)
        texto.encode("cp1252")
        self.assertIn("VALIDACIÓN DE CENTRO COMERCIAL / OFICINAS",
                      texto)
        self.assertIn("Centro comercial", texto)
        self.assertIn("Resumen:", texto)
        self.assertIn("Prioridades del documento", texto)
        self.assertIn("P01 SEGURIDAD DE VIDA", texto)
        self.assertIn("Conflictos del documento", texto)
        self.assertIn("Normativa seleccionable", texto)
        self.assertIn("REQUIERE_CALCULO_ESPECIALIZADO", texto)


class TestEquipos(_Base):
    """Equipos de referencia CC/OF: precios sin calidad."""

    def test_tabla_trae_los_equipos_del_documento(self):
        for space_type in ("TELECOM_ROOM", "SECURITY_ROOM",
                           "LOADING_DOCK", "VESTIBULE",
                           "BICYCLE_PARKING", "COMMERCIAL_KITCHEN"):
            aparatos = vb.EQUIPOS_POR_USO[space_type]
            self.assertTrue(aparatos)
            for concepto, unidad, precio in aparatos:
                self.assertEqual(unidad, "u")
                self.assertGreater(precio, 0.0)
        self.assertIn("Equipos", vb.CATEGORIAS_SIN_CALIDAD)

    def test_el_centro_comercial_factura_cctv_torniquete_y_anden(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_CC
        bw.apply_usage_program(data)
        variante = bw.generate_variants(data)[0]
        filas = vb.variant_takeoff(data, variante)
        equipos = {f["concept"]: f for f in filas
                   if f["category"] == "Equipos"}
        self.assertIn("Cámara de videovigilancia (CCTV)", equipos)
        self.assertIn("Torniquete de control de accesos", equipos)
        self.assertIn("Nivelador de andén", equipos)
        self.assertIn("Sello de andén", equipos)
        camara = equipos["Cámara de videovigilancia (CCTV)"]
        self.assertEqual(camara["code"], "")
        self.assertEqual(camara["unit_price"], 12_000.0)
        self.assertEqual(camara["fuente"], "referencia")

    def test_las_oficinas_facturan_el_rack_19(self):
        data = bw.BuildingWizardData()
        data.usage_type = bw.USO_COMERCIAL_OF
        data.comercial_tipologia = "OF-04 - Torre de oficinas"
        bw.apply_usage_program(data)
        variante = bw.generate_variants(data)[0]
        filas = vb.variant_takeoff(data, variante)
        equipos = {f["concept"]: f for f in filas
                   if f["category"] == "Equipos"}
        self.assertIn("Rack de telecomunicaciones 19 pulgadas", equipos)
        rack = equipos["Rack de telecomunicaciones 19 pulgadas"]
        self.assertEqual(rack["quantity"], 1.0)
        self.assertEqual(rack["unit_price"], 85_000.0)


@unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
class TestDialogoComercial(_Base):
    """El menú «Validar centro comercial / oficinas» (GUI)."""

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
        self.assertIn("bld_com_tip", help.TOOLTIPS)
        self.assertIn("tools_ccm_validar", help.TOOLTIPS)
        self._proyecto_cc()
        window = self._ventana()
        window.validar_comercial_informe()
        dialogo = window._validar_comercial_dialogo
        texto = dialogo._com_texto.get("1.0", "end")
        self.assertIn("VALIDACIÓN DE CENTRO COMERCIAL / OFICINAS",
                      texto)
        self.assertIn("CM01", texto)
        self.assertIn("Resumen:", texto)
        dialogo.destroy()


if __name__ == "__main__":
    unittest.main()

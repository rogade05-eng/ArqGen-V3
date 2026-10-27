# -*- coding: utf-8 -*-
"""v3.26.0 — ESCUELAS Y CÍRCULOS INFANTILES del documento del usuario.

El documento educacional (125 secciones: primaria, secundaria,
círculo infantil y albergue escolar) vive en
``resources/knowledge/educacion_specs.json`` (v1.0) y el motor
``domain/educacion_specs.py`` lo expone como consultas para el
asistente (tamaños paramétricos, cuadros MIN/REC, relaciones §98-101,
programas §106-109, reglas §111-112, conflictos §115, climas §116,
materiales §92-94 y seguridad infantil §89) y como validación honesta
validar_local/validar_proyecto con los estados medido / pendiente /
requiere cálculo (§78/§83-85).
"""

from __future__ import annotations

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.base import ARQGenTestCase  # noqa: E402
from services.architecture_service import ArchitectureService  # noqa: E402

from domain import educacion_specs as ed  # noqa: E402
from ui import building_wizard as bw  # noqa: E402
from ui import variant_budget as vb  # noqa: E402


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
            self.project_path("educacion.arqgen"), name="Educacion")
        self.arq = ArchitectureService(self.context)

    def _proyecto_ed(self, uso: str, tamano: str):
        """Genera un edificio educacional completo con el asistente."""
        data = bw.BuildingWizardData()
        data.name = "Centro Educativo Humo"
        data.usage_type = uso
        if tamano:
            data.educacion_tamano = tamano
        bw.apply_usage_program(data)
        creado = bw.apply_plan(data, self.context)
        self.assertTrue(creado)
        return data


class TestDocumento(ARQGenTestCase):
    """El documento educacional versionado está completo y cacheado."""

    def test_documento_completo_y_cacheado(self):
        specs = ed.cargar_specs()
        self.assertIsNotNone(specs)
        self.assertEqual(specs.version, "1.0")
        self.assertIn("escuelas primarias", specs.fuente_doc.lower())
        resumen = specs.resumen()
        self.assertEqual(resumen["tipologias"], 4)
        self.assertEqual(resumen["cuadros"], 82)
        self.assertEqual(resumen["programas"], 4)
        self.assertEqual(resumen["reglas"], 11)
        self.assertEqual(resumen["conflictos"], 18)
        self.assertEqual(resumen["climas"], 5)
        self.assertEqual(resumen["requiere_calculo"], 6)
        # vaciar_cache + recarga
        ed.vaciar_cache()
        self.assertEqual(ed.cargar_specs().version, "1.0")

    def test_formato_invalido_y_recurso_ausente(self):
        import json
        import tempfile
        # formato equivocado: ARQ-EDU-001
        doc = {"format": "OTRO", "version": "9"}
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False,
                                         encoding="utf-8") as fh:
            json.dump(doc, fh)
            ruta = fh.name
        try:
            with self.assertRaises(Exception) as ctx:
                ed.EducacionSpecs.load_file(ruta)
            self.assertEqual(ctx.exception.code, "ARQ-EDU-001")
        finally:
            os.unlink(ruta)
        # recurso ausente: None sin tumbar nada
        ed.vaciar_cache()
        import app.paths as paths
        original = ed._SPECS_PATH
        ed._SPECS_PATH = "no_existe_educacion.json"
        try:
            self.assertIsNone(ed.cargar_specs())
        finally:
            ed._SPECS_PATH = original
            ed.vaciar_cache()

    def test_capacidades_y_formula_de_aulas(self):
        specs = ed.cargar_specs()
        primaria = specs.capacidad("ESCUELA_PRIMARIA")
        self.assertEqual(primaria["formula_aulas"],
                         "NUM_AULAS = CEIL(NUM_ALUMNOS / ALUMNOS_POR_AULA)")
        self.assertEqual(primaria["rangos"][0]["min_alumnos"], 60)
        self.assertEqual(primaria["rangos"][3]["max_alumnos"], 1200)
        apa = primaria["alumnos_por_aula"]
        self.assertEqual(apa["rec_min"], 20.0)
        self.assertEqual(apa["rec_max"], 25.0)
        ci = specs.capacidad("CIRCULO_INFANTIL")
        self.assertEqual(len(ci["grupos_edad"]), 6)
        alb = specs.capacidad("ALBERGUE_ESCOLAR")
        self.assertEqual(alb["simultaneidad_comedor_pct"], 50)
        # nota honesta de secundaria
        self.assertIn("§4", specs.capacidad("ESCUELA_SECUNDARIA")["nota"])

    def test_minimos_de_los_cuadros(self):
        specs = ed.cargar_specs()
        aula = specs.minimos_de("CLASSROOM")
        self.assertEqual(aula["area"], 40.0)   # primaria §5
        self.assertEqual(aula["ancho"], 6.0)
        self.assertEqual(aula["altura"], 2.70)
        gamas = specs.gamas_superficie("CLASSROOM")
        self.assertEqual(gamas, ["48-60 m2", "50-65 m2"])
        inf = specs.minimos_de("AULA_INFANTIL")
        self.assertEqual(inf["area"], 40.0)
        gim = specs.minimos_de("GYMNASIO")
        self.assertEqual(gim["area"], 216.0)
        self.assertEqual(gim["altura"], 6.0)
        cuna = specs.minimos_de("SALA_CUNA")
        self.assertEqual(cuna["area"], 25.0)

    def test_relaciones_y_flujos(self):
        specs = ed.cargar_specs()
        # §99: aula-sanitarios prioritaria en primaria
        self.assertEqual(specs.nivel_de_relacion(
            "ESCUELA_PRIMARIA", "AULA", "SANITARIOS"), "3")
        # §102: cocina-basura prohibida (flujos limpio/sucio)
        self.assertEqual(specs.nivel_de_relacion(
            "ESCUELA_PRIMARIA", "COCINA", "BASURA"), "0")
        self.assertEqual(specs.nivel_de_relacion(
            "ALBERGUE_ESCOLAR", "DORMITORIOS", "RUIDO"), "0")
        self.assertEqual(specs.texto_relacion("3"), "PRIORITARIA")
        self.assertEqual(specs.texto_relacion("0"), "NO RECOMENDADA")
        # pseudo-códigos se expanden a space_types reales
        self.assertIn("CLASSROOM", ed.TIPOS_ESTUDIANTES)
        self.assertIn("KITCHEN_INSTITUTIONAL", ed.TIPOS_RUIDO)
        # override del círculo infantil: «AULA» es el aula infantil
        self.assertEqual(specs.tipo_de_relacion(
            "AULA", "CIRCULO_INFANTIL"), "AULA_INFANTIL")
        self.assertEqual(specs.tipo_de_relacion(
            "AULA", "ESCUELA_PRIMARIA"), "CLASSROOM")

    def test_programas_minimos_106_a_109(self):
        specs = ed.cargar_specs()
        primaria = specs.programa("ESCUELA_PRIMARIA")
        secundaria = specs.programa("ESCUELA_SECUNDARIA")
        circulo = specs.programa("CIRCULO_INFANTIL")
        albergue = specs.programa("ALBERGUE_ESCOLAR")
        self.assertEqual(len(primaria), 20)
        self.assertEqual(len(secundaria), 21)
        self.assertEqual(len(circulo), 22)
        self.assertEqual(len(albergue), 23)
        # evacuación y PCI son ítems no locales
        no_locales = [i["item"] for i in secundaria + albergue
                      + primaria if not i["es_local"]]
        self.assertIn("EVACUACION", no_locales)
        self.assertIn("SISTEMA_CONTRA_INCENDIOS", no_locales)
        # los exteriores van marcados (patio, juego, jardín)
        exteriores = [i["item"] for i in circulo if i["es_exterior"]]
        self.assertIn("JUEGOS_EXTERIORES", exteriores)
        self.assertIn("PATIO", exteriores)

    def test_reglas_conflictos_seguridad_y_fuentes(self):
        specs = ed.cargar_specs()
        reglas = {r["id"] for r in specs.reglas_validacion}
        self.assertIn("REGLA_11", reglas)  # la condicional del §111
        self.assertEqual(
            specs.reglas_validacion[-1]["check"], "EM04")
        self.assertEqual(len(specs.conflictos), 18)
        self.assertEqual(specs.conflictos[0]["check"], "E01")
        seg = specs.seguridad_infantil
        self.assertIn("enchufes accesibles sin protección",
                      seg["prohibido"])
        self.assertIn("control visual", seg["debe_existir"])
        self.assertTrue(any("OMS" in f for f in specs.fuentes))
        self.assertTrue(any("UNICEF" in f for f in specs.fuentes))
        self.assertEqual(specs.prioridades["P01"],
                         "SEGURIDAD INFANTIL")
        # materiales §92-94 con espesores
        pisos = specs.materiales["pisos"][0]
        self.assertEqual(pisos["espesores_mm"]["ceramico"], [8, 12])

    def test_tamanos_parametricos_y_parseo(self):
        self.assertEqual(ed.familia_de_uso("Escuela primaria"),
                         "ESCUELA_PRIMARIA")
        self.assertEqual(ed.familia_de_uso("Escuela secundaria"),
                         "ESCUELA_SECUNDARIA")
        self.assertEqual(ed.familia_de_uso("Círculo infantil"),
                         "CIRCULO_INFANTIL")
        self.assertEqual(ed.familia_de_uso("Albergue"),
                         "ALBERGUE_ESCOLAR")
        self.assertIsNone(ed.familia_de_uso("Vivienda"))
        tamanos = ed.tamanos_parametricos("Escuela primaria")
        self.assertEqual(len(tamanos), 4)
        self.assertIn("Media (181-450 alumnos)", tamanos)
        medio = ed.tamano_de_etiqueta("Escuela primaria",
                                      "Media (181-450 alumnos)")
        self.assertEqual(medio["capacidad"], 315)
        self.assertEqual(medio["por_aula_o_grupo"], 25.0)
        # un tamaño de otro uso no vale
        self.assertIsNone(ed.tamano_de_etiqueta(
            "Albergue", "Media (181-450 alumnos)"))


class TestAsistente(_Base):
    """Los cuatro usos educativos cargan el programa §106-109."""

    def test_uso_secundaria_en_la_lista(self):
        self.assertIn("Escuela secundaria", bw.USAGE_TYPES)
        self.assertIn("Escuela secundaria", bw.PROGRAM_PRESETS)
        self.assertIn("Escuela secundaria", bw.USAGE_HINTS)
        rooms = bw.preset_rooms("Escuela secundaria", "Planta Baja")
        self.assertGreaterEqual(len(rooms), 8)
        tipos = {r.space_type for r in rooms}
        self.assertIn("LAB_COMPUTACION", tipos)
        self.assertIn("TALLER_TECNOLOGICO", tipos)

    def test_combo_de_tamanos(self):
        choices = bw.educacion_tamano_choices()
        self.assertEqual(choices[0], bw.EDU_SIN_TAMANO)
        self.assertTrue(any(c.startswith("Escuela primaria: ")
                            for c in choices))
        self.assertTrue(any(c.startswith("Círculo infantil: ")
                            for c in choices))
        self.assertTrue(any(c.startswith("Albergue: ")
                            for c in choices))

    def test_primaria_parametrica_con_aulas_ceil(self):
        data = bw.BuildingWizardData()
        data.usage_type = "Escuela primaria"
        data.educacion_tamano = \
            "Escuela primaria: Pequeña (60-180 alumnos)"
        n, r = bw.apply_usage_program(data)
        self.assertGreaterEqual(n, 20)
        self.assertGreaterEqual(r, 5)
        aulas = [room for room in data.rooms
                 if room.space_type == "CLASSROOM"]
        self.assertEqual(len(aulas), 5)  # 120 alumnos a 25
        # medidas del cuadro §5: aula >= 40 m2
        for aula in aulas:
            self.assertGreaterEqual(aula.width_m * aula.depth_m, 40.0)
        tipos = {room.space_type for room in data.rooms}
        self.assertTrue({"SALA_PROFESORES", "LIBRARY", "INFIRMARY",
                         "DINING_HALL", "KITCHEN_INSTITUTIONAL",
                         "GYMNASIO", "PATIO", "WASTE_ROOM",
                         "ELECTRICAL_ROOM"} <= tipos)
        # los exteriores y técnicos sin ventana
        patio = next(room for room in data.rooms
                     if room.space_type == "PATIO")
        self.assertFalse(patio.with_window)

    def test_comedor_por_capacidad(self):
        data = bw.BuildingWizardData()
        data.usage_type = "Escuela primaria"
        data.educacion_tamano = \
            "Escuela primaria: Pequeña (60-180 alumnos)"
        bw.apply_usage_program(data)
        comedor = next(room for room in data.rooms
                       if room.space_type == "DINING_HALL")
        # 60 comensales (50% de 120) x 1.40 m2 = 84 m2
        self.assertGreaterEqual(comedor.width_m * comedor.depth_m, 84.0)

    def test_secundaria_parametrica(self):
        data = bw.BuildingWizardData()
        data.usage_type = "Escuela secundaria"
        data.educacion_tamano = \
            "Escuela secundaria: Pequeña (60-180 alumnos)"
        n, _r = bw.apply_usage_program(data)
        aulas = [room for room in data.rooms
                 if room.space_type == "CLASSROOM"]
        self.assertEqual(len(aulas), 4)  # 120 alumnos a 30
        tipos = {room.space_type for room in data.rooms}
        self.assertTrue({"LABORATORY", "LAB_COMPUTACION",
                         "TALLER_TECNOLOGICO", "SALA_ARTE",
                         "SALA_MUSICA", "DRESSING_ROOM",
                         "GYMNASIO"} <= tipos)

    def test_circulo_infantil_parametrico_por_grupos(self):
        data = bw.BuildingWizardData()
        data.usage_type = "Círculo infantil"
        data.educacion_tamano = "Círculo infantil: 3 grupos (60 niños)"
        bw.apply_usage_program(data)
        aulas = [room for room in data.rooms
                 if room.space_type == "AULA_INFANTIL"]
        higiene = [room for room in data.rooms
                   if room.space_type == "HIGIENE_CI"]
        descanso = [room for room in data.rooms
                    if room.space_type == "DORMITORIO_COLETIVO"]
        self.assertEqual(len(aulas), 3)
        self.assertEqual(len(higiene), 4)  # 3 por grupo + cambio común
        self.assertEqual(len(descanso), 3)
        self.assertEqual(bw._educacion_metadata(data)["grupos"], 3)
        # cadena del §98: aula comunicada con higiene
        pares = {(rel.a_name, rel.b_name): rel
                 for rel in data.relations}
        self.assertIsNotNone(
            pares.get(("Aulas infantiles", "Higiene")))

    def test_albergue_parametrico_dormitorios_de_8(self):
        data = bw.BuildingWizardData()
        data.usage_type = "Albergue"
        data.educacion_tamano = "Albergue: Pequeño (20-50 plazas)"
        n, _r = bw.apply_usage_program(data)
        dorms = [room for room in data.rooms
                 if room.space_type == "BEDROOM"]
        self.assertEqual(len(dorms), 5)  # 35 plazas a 8 por dormitorio
        tipos = {room.space_type for room in data.rooms}
        self.assertTrue({"SALA_ESTUDIO", "SALA_CONVIVENCIA", "LAUNDRY",
                         "MONITORES", "ISOLATION_ROOM"} <= tipos)

    def test_programa_basico_intacto(self):
        # retrocompatibilidad: sin tamaño, los programas estáticos
        data = bw.BuildingWizardData()
        data.usage_type = "Escuela primaria"
        bw.apply_usage_program(data)
        aulas = [room for room in data.rooms
                 if room.space_type == "CLASSROOM"]
        self.assertEqual(len(aulas), 3)  # el programa básico de siempre
        data2 = bw.BuildingWizardData()
        data2.usage_type = "Albergue"
        bw.apply_usage_program(data2)
        dorms = [room for room in data2.rooms
                 if room.space_type == "BEDROOM"]
        self.assertEqual(len(dorms), 3)

    def test_validacion_y_parseo_del_tamano(self):
        data = bw.BuildingWizardData()
        data.usage_type = "Escuela primaria"
        data.educacion_tamano = "Albergue: Pequeño (20-50 plazas)"
        errores = bw.validate_step(0, data)
        self.assertTrue(any("documento educacional" in e
                            for e in errores))
        # etiqueta pura también se resuelve
        data2 = bw.BuildingWizardData()
        data2.usage_type = "Albergue"
        data2.educacion_tamano = "Medio (51-150 plazas)"
        self.assertFalse(bw.validate_step(0, data2))
        # tamano_de_etiqueta devuelve el diccionario del §48
        medio = bw._resuelve_tamano("Albergue", "Medio (51-150 plazas)")
        self.assertEqual(medio["capacidad"], 100)

    def test_metadata_y_avisos(self):
        data = bw.BuildingWizardData()
        data.usage_type = "Escuela primaria"
        data.educacion_tamano = \
            "Escuela primaria: Media (181-450 alumnos)"
        bw.apply_usage_program(data)
        meta = bw._educacion_metadata(data)
        self.assertEqual(meta["familia"], "ESCUELA_PRIMARIA")
        self.assertEqual(meta["alumnos"], 315)
        self.assertEqual(meta["alumnos_por_aula"], 25.0)
        # resumen del paso 7 con la línea del documento
        texto = bw.step_summary(data)
        self.assertIn("documento educacional", texto)
        # avisos: seguridad infantil, gimnasio y comedor
        avisos = bw.educacion_advisories(data)
        self.assertTrue(any("§89" in a for a in avisos))
        self.assertTrue(any("§30" in a for a in avisos))
        self.assertTrue(any("§36" in a for a in avisos))
        self.assertTrue(any("§78" in a for a in avisos))
        # otros usos no reciben avisos educacionales
        data2 = bw.BuildingWizardData()
        data2.usage_type = "Vivienda"
        self.assertEqual(bw.educacion_advisories(data2), [])

    def test_program_from_project_restaura_el_tamano(self):
        data = self._proyecto_ed("Escuela primaria",
                                 "Escuela primaria: Pequeña (60-180 "
                                 "alumnos)")
        data2, _avisos = bw.program_from_project(self.context)
        self.assertEqual(data2.usage_type, "Escuela primaria")
        self.assertEqual(data2.educacion_tamano,
                         "Escuela primaria: Pequeña (60-180 alumnos)")


class TestValidacion(_Base):
    """validar_local y validar_proyecto con estados honestos."""

    def test_informe_del_proyecto_generado(self):
        self._proyecto_ed("Escuela primaria",
                          "Escuela primaria: Pequeña (60-180 alumnos)")
        informe = ed.validar_proyecto(self.context)
        self.assertEqual(informe["familias"], ["ESCUELA_PRIMARIA"])
        self.assertEqual(informe["uso"], "Escuela primaria")
        mapa = {h["codigo"]: h for h in informe["hallazgos"]
                if h["codigo"].startswith("EM")}
        self.assertEqual(mapa["EM01"]["severidad"], "ok")
        self.assertIn("§106-109", mapa["EM01"]["mensaje"])
        self.assertEqual(mapa["EM02"]["severidad"], "ok")
        self.assertEqual(mapa["EM03"]["severidad"], "ok")
        self.assertIn("REGLA_01/11", mapa["EM04"]["mensaje"])
        self.assertEqual(mapa["EM04"]["severidad"], "ok")
        self.assertEqual(mapa["EM05"]["severidad"], "ok")
        # punto de reunión informativo con la población de la metadata
        reunion = next(h for h in informe["hallazgos"]
                       if "AREA_REUNION" in h["mensaje"])
        self.assertEqual(reunion["estado"], "pendiente")
        self.assertIn("60", reunion["mensaje"])
        # seguridad infantil pendiente de verificación
        seguridad = next(h for h in informe["hallazgos"]
                         if "seguridad infantil" in h["mensaje"])
        self.assertEqual(seguridad["estado"], "pendiente")
        rc = [h for h in informe["hallazgos"]
              if h["codigo"].startswith("RC")]
        self.assertEqual(len(rc), 6)
        self.assertTrue(all(h["estado"] == "requiere calculo"
                            for h in rc))
        self.assertTrue(rc[0]["mensaje"].startswith("CLIMATIZACION"))
        # prioridades, conflictos, reglas, normativa y fuentes
        self.assertEqual(informe["prioridades"]["P01"],
                         "SEGURIDAD INFANTIL")
        self.assertEqual(len(informe["conflictos"]), 18)
        self.assertEqual(len(informe["reglas"]), 11)
        self.assertTrue(any("OMS" in f for f in informe["fuentes"]))
        # los locales entran al informe con su control dimensional
        self.assertTrue(informe["locales"])
        aula = next(l for l in informe["locales"]
                    if l["nombre"] == "Aulas")
        codigos = {h["codigo"]: h for h in aula["hallazgos"]}
        self.assertEqual(codigos["E01"]["severidad"], "ok")
        self.assertIn("E06", codigos)  # profundidad del aula §76

    def test_local_escaso_es_senalado_con_su_minimo(self):
        self._proyecto_ed("Escuela primaria",
                          "Escuela primaria: Pequeña (60-180 alumnos)")
        nivel = self.arq.create_level("Planta Prueba", 10.0, 3.0)
        self.arq.create_space(nivel.code, "Aula escasa", "CLASSROOM",
                              [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0),
                               (0.0, 4.0)])
        self.context.commit()
        espacios = [s for s in self.context.architecture.list(
            "SPACE", self.context.project.id)
            if getattr(s, "space_type", "") == "CLASSROOM"]
        escasa = next(s for s in espacios if s.name == "Aula escasa")
        informe = ed.validar_local(self.context, escasa.id)
        codigos = {h["codigo"]: h for h in informe["hallazgos"]}
        self.assertEqual(codigos["E01"]["severidad"], "fallo")
        self.assertIn("40.00", codigos["E01"]["mensaje"])
        self.assertIn("gamas recomendadas", codigos["E01"]["mensaje"])
        # sin puertas: aviso honesto
        self.assertEqual(codigos["E04"]["severidad"], "aviso")
        self.assertIn("no tiene puertas", codigos["E04"]["mensaje"])
        # el proyecto entero también lo cuenta
        global_inf = ed.validar_proyecto(self.context)
        con_fallos = [l for l in global_inf["locales"]
                      if any(h["severidad"] == "fallo"
                             for h in l["hallazgos"])]
        self.assertTrue(any(l["nombre"] == "Aula escasa"
                            for l in con_fallos))

    def test_capacidad_con_aulas_insuficientes(self):
        # proyecto manual: 2 aulas y metadata de 120 alumnos (5 pedidas)
        data = bw.BuildingWizardData()
        data.name = "Escuela pequeña a mano"
        data.usage_type = "Escuela primaria"
        data.educacion_tamano = \
            "Escuela primaria: Pequeña (60-180 alumnos)"
        data.rooms = [
            bw.RoomSpec(name="Aula 1", space_type="CLASSROOM",
                        width_m=7.0, depth_m=8.0),
            bw.RoomSpec(name="Aula 2", space_type="CLASSROOM",
                        width_m=7.0, depth_m=8.0),
            bw.RoomSpec(name="Baño", space_type="BATHROOM",
                        width_m=2.4, depth_m=2.2),
        ]
        bw.apply_plan(data, self.context)
        informe = ed.validar_proyecto(self.context)
        em04 = next(h for h in informe["hallazgos"]
                    if h["codigo"] == "EM04")
        self.assertEqual(em04["severidad"], "fallo")
        self.assertIn("REGLA_01/11", em04["mensaje"])

    def test_flujo_prohibido_se_senala(self):
        # cocina comunicada con el cuarto de residuos (§102)
        data = bw.BuildingWizardData()
        data.usage_type = "Escuela primaria"
        data.educacion_tamano = \
            "Escuela primaria: Pequeña (60-180 alumnos)"
        bw.apply_usage_program(data)
        data.relations.append(bw.RelationSpec(
            a_name="Cocina", b_name="Cuarto de residuos",
            kind_es="Comunicado con", with_door=True))
        bw.apply_plan(data, self.context)
        informe = ed.validar_proyecto(self.context)
        em03 = next(h for h in informe["hallazgos"]
                    if h["codigo"] == "EM03")
        self.assertEqual(em03["severidad"], "fallo")
        self.assertIn("§102", em03["mensaje"])

    def test_programa_incompleto_avisaria(self):
        # proyecto a mano con aulas y baño: el §106 pide más locales
        nivel = self.arq.create_level("Planta Baja", 0.0, 3.2)
        for i in range(3):
            self.arq.create_space(
                nivel.code, f"Aula {i + 1}", "CLASSROOM",
                [(i * 8.0, 0.0), (i * 8.0 + 7.0, 0.0),
                 (i * 8.0 + 7.0, 8.0), (i * 8.0, 8.0)])
        self.context.commit()
        informe = ed.validar_proyecto(self.context)
        # sin metadata, 3 aulas infieren la familia primaria
        self.assertEqual(informe["familias"], ["ESCUELA_PRIMARIA"])
        em01 = next(h for h in informe["hallazgos"]
                    if h["codigo"] == "EM01")
        self.assertEqual(em01["severidad"], "aviso")
        self.assertIn("falta", em01["mensaje"])

    def test_albergue_huellas_y_dormitorios(self):
        self._proyecto_ed("Albergue", "Albergue: Pequeño (20-50 plazas)")
        informe = ed.validar_proyecto(self.context)
        self.assertEqual(informe["familias"], ["ALBERGUE_ESCOLAR"])
        mapa = {h["codigo"]: h for h in informe["hallazgos"]
                if h["codigo"].startswith("EM")}
        self.assertEqual(mapa["EM01"]["severidad"], "ok")
        # los dormitorios generados cumplen el mínimo del §51
        self.assertIn("dormitorios", " | ".join(
            h["mensaje"] for h in informe["hallazgos"]))

    def test_texto_cp1252_del_informe(self):
        self._proyecto_ed("Escuela primaria",
                          "Escuela primaria: Pequeña (60-180 alumnos)")
        informe = ed.validar_proyecto(self.context)
        texto = ed.texto_validacion_educacion(informe)
        texto.encode("cp1252")
        self.assertIn("VALIDACIÓN DE ESCUELA", texto)
        self.assertIn("Reglas de validación del documento", texto)
        self.assertIn("Conflictos del documento", texto)
        self.assertIn("P12", texto)


class TestEquipos(_Base):
    """Los equipos de referencia sin calidad del documento ED."""

    def test_tabla_trae_los_equipos_nuevos(self):
        for tipo in ("LAB_COMPUTACION", "GYMNASIO", "INFIRMARY",
                     "SALA_CUNA", "DORMITORIO_COLETIVO",
                     "TALLER_TECNOLOGICO"):
            self.assertIn(tipo, vb.EQUIPOS_POR_USO, tipo)

    def test_el_laboratorio_factura_pcs(self):
        data = bw.BuildingWizardData()
        data.usage_type = "Escuela secundaria"
        data.educacion_tamano = \
            "Escuela secundaria: Pequeña (60-180 alumnos)"
        bw.apply_usage_program(data)
        variante = bw.generate_variants(data)[0]
        filas = vb.variant_takeoff(data, variante)
        equipos = {f["concept"]: f for f in filas
                   if f["category"] == "Equipos"}
        self.assertIn("PC de aula con monitor", equipos)
        pc = equipos["PC de aula con monitor"]
        self.assertEqual(pc["code"], "")
        self.assertGreater(pc["unit_price"], 0.0)
        self.assertEqual(pc["fuente"], "referencia")


@unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
class TestGUI(_Base):
    """Tooltips, menú Herramientas y diálogo del informe ED."""

    def _ventana(self):
        from ui.app_window import ARQGenWindow
        from ui import theme
        theme.set_mode("dark")
        window = ARQGenWindow(self.context, self.application)
        window.update()
        self.addCleanup(window.destroy)
        return window

    def test_tooltips_del_documento_educacional(self):
        from ui import help as ayuda
        self.assertIn("bld_edu_tam", ayuda.TOOLTIPS)
        self.assertIn("tools_edu_validar", ayuda.TOOLTIPS)
        self.assertIn("§106-109", ayuda.TOOLTIPS["bld_edu_tam"])
        self.assertIn("§89", ayuda.TOOLTIPS["tools_edu_validar"])

    def test_menu_y_dialogo_con_informe(self):
        self._proyecto_ed("Escuela primaria",
                          "Escuela primaria: Pequeña (60-180 alumnos)")
        app = self._ventana()
        app.validar_educacion_informe()
        dialogo = app._validar_educacion_dialogo
        self.assertIsNotNone(dialogo)
        texto = dialogo._edu_texto.get("1.0", "end")
        self.assertIn("VALIDACIÓN DE ESCUELA", texto)
        self.assertIn("EM01", texto)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""v3.28.0 — PRESETS DE CONFIGURACIÓN DEL ASISTENTE.

La configuración del asistente de edificación (uso, tipología,
tamaño del documento ED, cotas de vanos, instalaciones, cubierta,
mobiliario...) se guarda como JSON local en ``presets/`` y se recarga
en cualquier proyecto: ``ui/presets.py`` es puro (sin Tk), con
formato ``ARQ_GEN_PRESET`` v1 y errores amables ARQ-PRE-001..006.
Lo que otros cobran en plan Business aquí es local, gratis y
auditable.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.base import ARQGenTestCase, PROJECT_ROOT  # noqa: E402

from core.errors import DomainError  # noqa: E402
from ui import presets as pr  # noqa: E402
from ui.building_wizard import BuildingWizardData  # noqa: E402


class TestPresetDeData(unittest.TestCase):
    """La fotografía de la configuración (sin niveles ni locales)."""

    def test_incluye_la_configuracion_y_excluye_el_programa(self):
        data = BuildingWizardData()
        data.usage_type = "Escuela primaria"
        data.educacion_tamano = "Escuela primaria: Media (180-420 alumnos)"
        data.corridor_width_m = 1.4
        data.installations = ["Eléctrica", "Gas"]
        snap = pr.preset_de_data(data)
        for campo in ("usage_type", "educacion_tamano",
                      "corridor_width_m", "installations",
                      "cubierta_tipologia", "mobiliario_densidad",
                      "neufert_region", "window_sill_m"):
            self.assertIn(campo, snap)
        self.assertEqual(snap["usage_type"], "Escuela primaria")
        self.assertEqual(snap["corridor_width_m"], 1.4)
        self.assertEqual(snap["installations"], ["Eléctrica", "Gas"])
        # el PROGRAMA no viaja: se regenera desde el uso
        self.assertNotIn("levels", snap)
        self.assertNotIn("rooms", snap)
        self.assertNotIn("relations", snap)

    def test_fotografia_independiente_de_luego(self):
        data = BuildingWizardData()
        data.lot_width_m = 42.0
        snap = pr.preset_de_data(data)
        data.lot_width_m = 0.0
        self.assertEqual(snap["lot_width_m"], 42.0)

    def test_campos_cubren_los_pasos_con_widgets(self):
        # 1 y 4 y 5 (y concepción de espacios) — el contrato que la
        # GUI promete al guardar
        for campo in ("name", "vivienda_dormitorios", "comercial_tipologia",
                      "educacion_tamano", "cross_ventilation",
                      "protection_solar", "eaves_m", "installations",
                      "accesibilidad_auto", "cubierta_material"):
            self.assertIn(campo, pr.CAMPOS_PRESET)


class TestCicloPreset(ARQGenTestCase):
    """Guardar -> listar -> cargar -> aplicar -> eliminar."""

    def _datos_escuela(self) -> BuildingWizardData:
        data = BuildingWizardData()
        data.name = "Centro educativo"
        data.usage_type = "Escuela primaria"
        data.educacion_tamano = \
            "Escuela primaria: Pequeña (60-180 alumnos)"
        data.corridor_width_m = 1.4
        data.door_width_m = 1.0
        data.installations = ["Eléctrica", "Energía solar"]
        data.notes = "requerimientos del colegio"
        return data

    def test_ciclo_completo(self):
        carpeta = os.path.join(self.tmp, "presets")
        data = self._datos_escuela()
        ruta = pr.guardar_preset(carpeta, "Escuela primaria 120",
                                 pr.preset_de_data(data))
        self.assertTrue(os.path.isfile(ruta))
        self.assertEqual(os.path.basename(ruta),
                         "Escuela primaria 120.json")
        # la carpeta se crea sola
        self.assertTrue(os.path.isdir(carpeta))
        listado = pr.listar_presets(carpeta)
        self.assertEqual(len(listado), 1)
        self.assertEqual(listado[0]["nombre"], "Escuela primaria 120")
        self.assertEqual(listado[0]["uso"], "Escuela primaria")
        self.assertFalse(listado[0]["corrupto"])
        self.assertIn("Escuela primaria", listado[0]["resumen"])
        # modificar la data y restaurar
        data.usage_type = "Vivienda"
        data.educacion_tamano = "(programa básico)"
        data.corridor_width_m = 0.0
        data.door_width_m = 0.9
        data.installations = []
        data.notes = ""
        documento = pr.cargar_preset(ruta)
        self.assertEqual(documento["formato"], "ARQ_GEN_PRESET")
        self.assertEqual(documento["version"], 1)
        avisos = pr.aplicar_preset_a_data(documento["datos"], data)
        self.assertEqual(avisos, [])
        self.assertEqual(data.usage_type, "Escuela primaria")
        self.assertEqual(data.educacion_tamano,
                         "Escuela primaria: Pequeña (60-180 alumnos)")
        self.assertAlmostEqual(data.corridor_width_m, 1.4)
        self.assertAlmostEqual(data.door_width_m, 1.0)
        self.assertEqual(data.installations, ["Eléctrica",
                                              "Energía solar"])
        self.assertEqual(data.notes, "requerimientos del colegio")
        # eliminar
        self.assertTrue(pr.eliminar_preset(ruta))
        self.assertFalse(pr.eliminar_preset(ruta))
        self.assertEqual(pr.listar_presets(carpeta), [])

    def test_numero_de_vivienda_vuelve_entero(self):
        carpeta = os.path.join(self.tmp, "presets")
        data = BuildingWizardData()
        snap = pr.preset_de_data(data)
        snap["vivienda_dormitorios"] = "4"      # como llega de la GUI
        snap["vivienda_banos"] = "2,0"          # coma decimal española
        pr.guardar_preset(carpeta, "números", snap)
        documento = pr.cargar_preset(
            os.path.join(carpeta, "números.json"))
        avisos = pr.aplicar_preset_a_data(documento["datos"], data)
        self.assertEqual(avisos, [])
        self.assertEqual(data.vivienda_dormitorios, 4)
        self.assertEqual(data.vivienda_banos, 2)

    def test_valores_ilegales_avisan_y_no_rompen(self):
        data = self._datos_escuela()
        antes = data.usage_type
        avisos = pr.aplicar_preset_a_data({
            "usage_type": "Observatorio lunar",
            "distribucion": "caótica",
            "corridor_width_m": "no es un número",
            "installations": ["Eléctrica", "Teleportación"],
            "neufert_region": "MARTE",
            "campo_inventado": 42,
        }, data)
        self.assertEqual(len(avisos), 5, avisos)
        self.assertEqual(data.usage_type, antes)  # conservó el actual
        self.assertEqual(data.installations, ["Eléctrica"])
        self.assertEqual(data.comercial_tipologia,
                         "(sin tipología concreta)")

    def test_resumen_por_uso(self):
        self.assertIn("Vivienda", pr.resumen_preset(
            {"usage_type": "Vivienda", "vivienda_tipologia":
             "Unifamiliar aislada", "vivienda_dormitorios": 4,
             "vivienda_banos": 2, "climate": "Cálido húmedo"}))
        self.assertIn("Escuela primaria: Pequeña (60-180 alumnos)",
                      pr.resumen_preset(
                          {"usage_type": "Escuela primaria",
                           "educacion_tamano":
                           "Escuela primaria: Pequeña (60-180 alumnos)"}))
        self.assertIn("Tienda ancla", pr.resumen_preset(
            {"usage_type": "Centro comercial",
             "comercial_tipologia": "Tienda ancla"}))
        # cp1252: la línea de la lista nunca tumba la consola
        pr.resumen_preset({"usage_type": "Escuela secundaria",
                           "educacion_tamano": ""}).encode("cp1252")

    def test_slug_seguro(self):
        # sin separadores de ruta ni caracteres raros en el nombre
        for sucio in ("Escuela primaria/120", "a:b", "x*y", "..",
                      "nombre??"):
            limpio = pr.slug(sucio)
            self.assertNotIn("/", limpio)
            self.assertNotIn(":", limpio)
            self.assertNotIn("*", limpio)
            self.assertNotIn("?", limpio)
        self.assertEqual(pr.slug("   "), "")


class TestErroresPreset(ARQGenTestCase):
    """Errores amables ARQ-PRE-001..006."""

    def setUp(self) -> None:
        super().setUp()
        self.carpeta = os.path.join(self.tmp, "presets")

    def test_nombre_vacio(self):
        with self.assertRaises(DomainError) as ctx:
            pr.guardar_preset(self.carpeta, "   ", {"a": 1})
        self.assertEqual(ctx.exception.code, pr.COD_NOMBRE)

    def test_datos_no_dict(self):
        with self.assertRaises(DomainError) as ctx:
            pr.guardar_preset(self.carpeta, "lista", ["no"])
        self.assertEqual(ctx.exception.code, pr.COD_DATOS)

    def test_preset_ausente(self):
        with self.assertRaises(DomainError) as ctx:
            pr.cargar_preset(os.path.join(self.carpeta, "nada.json"))
        self.assertEqual(ctx.exception.code, pr.COD_AUSENTE)

    def test_json_corrupto(self):
        os.makedirs(self.carpeta, exist_ok=True)
        ruta = os.path.join(self.carpeta, "roto.json")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write("{no soy json")
        with self.assertRaises(DomainError) as ctx:
            pr.cargar_preset(ruta)
        self.assertEqual(ctx.exception.code, pr.COD_JSON)
        # el listado NO muere: marca la entrada como ilegible
        listado = pr.listar_presets(self.carpeta)
        self.assertEqual(len(listado), 1)
        self.assertTrue(listado[0]["corrupto"])

    def test_formato_desconocido(self):
        os.makedirs(self.carpeta, exist_ok=True)
        ruta = os.path.join(self.carpeta, "otro.json")
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump({"formato": "OTRO_PROGRAMA", "datos": {}}, fh)
        with self.assertRaises(DomainError) as ctx:
            pr.cargar_preset(ruta)
        self.assertEqual(ctx.exception.code, pr.COD_FORMATO)
        listado = pr.listar_presets(self.carpeta)
        self.assertTrue(listado[0]["corrupto"])
        self.assertEqual(listado[0]["error"], pr.COD_FORMATO)

    def test_version_futura_rechazada(self):
        os.makedirs(self.carpeta, exist_ok=True)
        ruta = os.path.join(self.carpeta, "futuro.json")
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump({"formato": "ARQ_GEN_PRESET", "version": 99,
                       "datos": {}}, fh)
        with self.assertRaises(DomainError) as ctx:
            pr.cargar_preset(ruta)
        self.assertEqual(ctx.exception.code, pr.COD_FORMATO)


class TestCarpetaPresets(ARQGenTestCase):
    """La carpeta se resuelve con ARQ_GEN_PRESETS o junto al app."""

    def test_env_gana(self):
        os.environ["ARQ_GEN_PRESETS"] = os.path.join(self.tmp, "mio")
        try:
            self.assertEqual(pr.carpeta_presets(),
                             os.path.join(self.tmp, "mio"))
        finally:
            del os.environ["ARQ_GEN_PRESETS"]

    def test_base_explicita(self):
        self.assertEqual(pr.carpeta_presets("/tmp/base"),
                         os.path.abspath("/tmp/base"))

    def test_defecto_junto_al_programa(self):
        esperada = os.path.join(PROJECT_ROOT, "presets")
        self.assertEqual(pr.carpeta_presets(),
                         os.path.abspath(esperada))


class TestFuentePresets(unittest.TestCase):
    """Marcadores del módulo (espejo del check 70 del selftest)."""

    def test_marcadores(self):
        with open(os.path.join(PROJECT_ROOT, "ui", "presets.py"),
                  "r", encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def guardar_preset", src)
        self.assertIn("def cargar_preset", src)
        self.assertIn("ARQ_GEN_PRESET", src)
        self.assertIn("ARQ-PRE-001", src)
        self.assertIn("ARQ-PRE-006", src)
        self.assertIn("preset_de_data", src)
        self.assertIn("aplicar_preset_a_data", src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

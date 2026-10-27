"""ASISTENTE DE LOCAL — MODIFICAR (v3.20.0) — ui/editor_espacios.py.

El asistente de local ya no solo CREA: modifica un local existente
controlando TODO lo que le es imputable:

* Identidad: nombre y uso con su DNA (área mínima se avisa; tipo
  desconocido se rechaza con mensaje amable) y reamueblado opcional.
* Geometría: mover el local completo (boundary + muros exclusivos +
  mobiliario), espesor de sus muros exclusivos y cota del piso.
* Vanos: editar ancho/alto/antepecho/posición, dar de baja, y crear
  acceso con el ancho del uso nuevo (camilla 1,20 m en tomografía).
* Instalaciones: conectar a redes, iluminar SOLO este local (el resto
  del proyecto conserva sus luminarias) y alarmar este local.
* Diagnóstico DNA: resumen_completo + texto cp1252.
* Undo persistente y persistencia al reabrir.
* GUI (Xvfb): diálogo con 5 pestañas y diagnóstico DNA en vivo.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.errors import ARQGenError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

from ui import cad_tools as cad
from ui import editor_espacios as edi


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


class _LocalBase(ARQGenTestCase):
    """Un local de 4x3 con sus 4 muros exclusivos en un nivel de 3 m."""

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("asistente.arqgen"), name="Asistente")
        self.arq = ArchitectureService(self.context)
        self.nivel = self.arq.create_level("Planta 1", 0.0, 3.0)
        self.muro_sur = self.arq.create_wall(self.nivel.code,
                                             (0.0, 0.0), (4.0, 0.0), 0.2)
        self.muro_oeste = self.arq.create_wall(self.nivel.code,
                                               (0.0, 0.0), (0.0, 3.0), 0.2)
        self.muro_norte = self.arq.create_wall(self.nivel.code,
                                               (0.0, 3.0), (4.0, 3.0), 0.2)
        self.muro_este = self.arq.create_wall(self.nivel.code,
                                              (4.0, 0.0), (4.0, 3.0), 0.2)
        self.local = self.arq.create_space(
            self.nivel.code, "Consultorio 1", "CONSULTATION_ROOM",
            [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)])

    def tearDown(self) -> None:
        try:
            self.context.close()
        except Exception:  # noqa: BLE001
            pass
        super().tearDown()


class TestIdentidad(_LocalBase):

    def test_cambia_nombre_y_uso(self):
        resumen = edi.cambiar_identidad(
            self.context, self.local.id, nombre="Tomografía (TAC)",
            uso="CT_ROOM")
        datos = edi.resumen_completo(self.context, self.local.id)
        self.assertEqual(datos["nombre"], "Tomografía (TAC)")
        self.assertEqual(datos["uso"], "CT_ROOM")
        self.assertIn("CT_ROOM", resumen["texto"])

    def test_aviso_de_area_minima_del_dna(self):
        resumen = edi.cambiar_identidad(self.context, self.local.id,
                                        uso="CT_ROOM")
        self.assertTrue(any("mínima" in a for a in resumen["avisos"]),
                        resumen["avisos"])

    def test_uso_desconocido_error_amable(self):
        with self.assertRaises(ARQGenError) as ctx:
            edi.cambiar_identidad(self.context, self.local.id,
                                  uso="NAVE_ESTELAR")
        self.assertIn("catálogo", str(ctx.exception.message))

    def test_sin_cambios_error_amable(self):
        with self.assertRaises(ARQGenError):
            edi.cambiar_identidad(self.context, self.local.id)

    def test_cambio_de_uso_reamuebla(self):
        edi.cambiar_identidad(self.context, self.local.id,
                              uso="OPERATING_ROOM",
                              con_mobiliario=True)
        piezas = [e for e in self.context.architecture.list(
            "FURNITURE", self.context.project.id)]
        self.assertTrue(any(p.kind == "mesa_operaciones" for p in piezas),
                        [p.kind for p in piezas])


class TestGeometria(_LocalBase):

    def test_mueve_boundary_muros_y_mobiliario(self):
        edi.cambiar_identidad(self.context, self.local.id, uso="MORGUE",
                              con_mobiliario=True)
        muebles_antes = [(float(e.x), float(e.y))
                         for e in self.context.architecture.list(
                             "FURNITURE", self.context.project.id)]
        resumen = edi.mover_local(self.context, self.local.id, 2.0, 1.5)
        self.assertEqual(len(resumen["muros"]), 4)
        local = cad.resolver(self.context, "SPACE", self.local.id)
        pts = [tuple(p) for p in local.boundary]
        self.assertAlmostEqual(pts[0][0], 2.0, places=6)
        self.assertAlmostEqual(pts[0][1], 1.5, places=6)
        muro = cad.resolver(self.context, "WALL", self.muro_sur.code)
        self.assertAlmostEqual(float(muro.start[0]), 2.0, places=6)
        self.assertAlmostEqual(float(muro.start[1]), 1.5, places=6)
        muebles = self.context.architecture.list(
            "FURNITURE", self.context.project.id)
        self.assertTrue(muebles)
        esperados = {(round(x + 2.0, 6), round(y + 1.5, 6))
                     for x, y in muebles_antes}
        for mueble in muebles:
            punto = (round(float(mueble.x), 6), round(float(mueble.y), 6))
            self.assertIn(punto, esperados)

    def test_desplazamiento_cero_error_amable(self):
        with self.assertRaises(ARQGenError):
            edi.mover_local(self.context, self.local.id, 0.0, 0.0)

    def test_espesor_de_los_muros_exclusivos(self):
        resumen = edi.espesor_muros_exclusivos(self.context,
                                               self.local.id, 0.3)
        self.assertEqual(len(resumen["muros"]), 4)
        for codigo in resumen["muros"]:
            muro = cad.resolver(self.context, "WALL", codigo)
            self.assertAlmostEqual(float(muro.thickness_m), 0.3, places=9)

    def test_espesor_que_se_come_el_local_error(self):
        with self.assertRaises(ARQGenError) as ctx:
            edi.espesor_muros_exclusivos(self.context, self.local.id, 2.5)
        self.assertIn("se come", str(ctx.exception.message))

    def test_cota_del_piso_en_metadata(self):
        edi.cota_piso_local(self.context, self.local.id, 0.45)
        datos = edi.resumen_completo(self.context, self.local.id)
        self.assertAlmostEqual(datos["cota_piso_m"], 0.45, places=3)
        with self.assertRaises(ARQGenError):
            edi.cota_piso_local(self.context, self.local.id, -1.0)


class TestVanos(_LocalBase):

    def test_edita_ancho_y_posicion(self):
        self.arq.create_opening("DOOR", self.muro_sur.code, 1.2, 2.1,
                                offset_m=1.0)
        vano = self.context.architecture.list(
            "DOOR", self.context.project.id)[0]
        edi.editar_vano(self.context, self.local.id, vano.code,
                        ancho=1.3, alto=2.2, antepecho=0.0, offset=1.4)
        vano = self.context.architecture.get_by_code(
            "DOOR", vano.code) or vano
        self.assertAlmostEqual(float(vano.width_m), 1.3, places=9)
        self.assertAlmostEqual(float(vano.height_m), 2.2, places=9)
        self.assertAlmostEqual(float(vano.offset_m), 1.4, places=9)

    def test_vano_que_no_cabe_error_amable(self):
        self.arq.create_opening("DOOR", self.muro_sur.code, 1.2, 2.1,
                                offset_m=1.0)
        vano = self.context.architecture.list(
            "DOOR", self.context.project.id)[0]
        with self.assertRaises(ARQGenError) as ctx:
            edi.editar_vano(self.context, self.local.id, vano.code,
                            ancho=5.0)
        self.assertIn("no cabe", str(ctx.exception.message))

    def test_vano_de_otro_local_error(self):
        otro = self.arq.create_space(
            self.nivel.code, "Otro", "ROOM",
            [(6.0, 0.0), (8.0, 0.0), (8.0, 2.0), (6.0, 2.0)])
        self.arq.create_opening("DOOR", self.muro_sur.code, 1.2, 2.1)
        vano = self.context.architecture.list(
            "DOOR", self.context.project.id)[0]
        with self.assertRaises(ARQGenError):
            edi.editar_vano(self.context, otro.id, vano.code,
                            ancho=1.0)

    def test_quitar_vano(self):
        self.arq.create_opening("WINDOW", self.muro_norte.code, 1.2, 1.2,
                                offset_m=1.0, sill_height_m=1.0)
        vano = self.context.architecture.list(
            "WINDOW", self.context.project.id)[0]
        resumen = edi.quitar_vano(self.context, self.local.id, vano.code)
        self.assertEqual(resumen["vanos_eliminados"], [vano.code])
        self.assertFalse(self.context.architecture.list(
            "WINDOW", self.context.project.id))

    def test_acceso_con_ancho_del_uso_nuevo(self):
        edi.cambiar_identidad(self.context, self.local.id, uso="CT_ROOM")
        edi.crear_acceso(self.context, self.local.id)
        puerta = self.context.architecture.list(
            "DOOR", self.context.project.id)[0]
        self.assertAlmostEqual(float(puerta.width_m), 1.2, places=9)


class TestInstalaciones(_LocalBase):

    def _dos_locales(self):
        muros_b = [self.arq.create_wall(
            self.nivel.code, a, b, 0.2) for a, b in (
            ((6.0, 0.0), (10.0, 0.0)), ((6.0, 0.0), (6.0, 3.0)),
            ((6.0, 3.0), (10.0, 3.0)), ((10.0, 0.0), (10.0, 3.0)))]
        local_b = self.arq.create_space(
            self.nivel.code, "Urgencias", "EMERGENCY_ROOM",
            [(6.0, 0.0), (10.0, 0.0), (10.0, 3.0), (6.0, 3.0)])
        return local_b

    def test_ilumina_solo_el_local_pedido(self):
        vecino = self._dos_locales()
        edi.iluminar_local(self.context, vecino.id, lampara="led_panel")
        edi.iluminar_local(self.context, self.local.id,
                           lampara="led_panel")
        nodos = self.context.installations.list(
            "NODE", self.context.project.id)
        luminarias = [n for n in nodos if n.kind == "LUMINAIRE"]
        por_local = {n.space_id for n in luminarias}
        self.assertEqual(por_local, {self.local.id, vecino.id})
        # re-iluminar UNO: el vecino conserva las suyas
        antes_vecino = len([n for n in luminarias
                            if n.space_id == vecino.id])
        edi.iluminar_local(self.context, self.local.id,
                           lampara="led_lineal")
        nodos = self.context.installations.list(
            "NODE", self.context.project.id)
        luminarias = [n for n in nodos if n.kind == "LUMINAIRE"]
        self.assertEqual(len([n for n in luminarias
                              if n.space_id == vecino.id]), antes_vecino)
        self.assertGreaterEqual(len([n for n in luminarias
                                     if n.space_id == self.local.id]), 1)

    def test_alarma_del_local(self):
        edi.alarmar_local(self.context, self.local.id)
        nodos = self.context.installations.list(
            "NODE", self.context.project.id)
        dispositivos = [n for n in nodos
                        if (n.attrs or {}).get("origen_alarma")]
        self.assertTrue(dispositivos)
        self.assertTrue(all(n.space_id == self.local.id
                            for n in dispositivos))

    def test_conectar_instalaciones(self):
        resumen = edi.conectar_instalaciones_local(self.context,
                                                   self.local.id)
        self.assertIn("instalaciones", resumen)
        self.assertGreaterEqual(resumen["instalaciones"]["equipos"], 1)


class TestDiagnosticoYDeshacer(_LocalBase):

    def test_resumen_completo_con_dna(self):
        edi.cambiar_identidad(self.context, self.local.id, uso="CT_ROOM")
        edi.crear_acceso(self.context, self.local.id, ancho=0.8)
        datos = edi.resumen_completo(self.context, self.local.id)
        self.assertEqual(datos["dna"]["nombre_es"], "Tomografía (TAC)")
        self.assertTrue(any("pide 1.20" in a or "pide 1,20" in a
                            for a in datos["avisos"]),
                        datos["avisos"])

    def test_texto_diagnostico_cp1252(self):
        edi.cambiar_identidad(self.context, self.local.id,
                              nombre="Morgue", uso="MORGUE")
        datos = edi.resumen_completo(self.context, self.local.id)
        texto = edi.texto_resumen_completo(datos)
        texto.encode("cp1252")  # sin excepción
        self.assertIn("Diagnóstico", texto)
        self.assertIn("Morgue (depósito de cadáveres)", texto)

    def test_undo_persistente_de_la_identidad(self):
        from app.undo_service import PersistentUndoService
        self.context.commit()
        edi.cambiar_identidad(self.context, self.local.id, uso="CT_ROOM")
        self.context.commit()
        PersistentUndoService(self.context).undo()
        local = self.context.architecture.get(
            "SPACE", self.local.id)
        self.assertEqual(str(local.space_type), "CONSULTATION_ROOM")

    def test_todo_persiste_al_reabrir(self):
        ruta = self.context.db_path
        edi.cambiar_identidad(self.context, self.local.id,
                              nombre="Almacén general", uso="WAREHOUSE")
        edi.cota_piso_local(self.context, self.local.id, 0.3)
        edi.espesor_muros_exclusivos(self.context, self.local.id, 0.25)
        self.context.commit()
        self.context.close()
        reabierto = self.application.open_project(ruta)
        try:
            local = reabierto.architecture.get("SPACE", self.local.id)
            self.assertEqual(str(local.space_type), "WAREHOUSE")
            self.assertEqual(str(local.name), "Almacén general")
            req = (local.metadata or {}).get("requerimientos", {})
            self.assertAlmostEqual(
                float(req["arquitectonicos"]["cota_piso_m"]), 0.3,
                places=3)
            muro = reabierto.architecture.get("WALL", self.muro_sur.id)
            self.assertAlmostEqual(float(muro.thickness_m), 0.25,
                                   places=9)
        finally:
            reabierto.close()


@unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
class TestDialogoAsistente(_LocalBase):

    def _ventana(self):
        from ui.app_window import ARQGenWindow
        from ui import theme
        theme.set_mode("dark")
        window = ARQGenWindow(self.context, self.application)
        window.update()
        self.addCleanup(window.destroy)
        return window

    def test_dialogo_abre_con_cinco_pestañas_y_diagnostico(self):
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        pestañas = dialogo._editor_pestañas
        titulos = [pestañas.tab(t, "text") for t in pestañas.tabs()]
        self.assertEqual(titulos, ["Local", "Geometría", "Vanos",
                                   "Instalaciones", "Mobiliario"])
        dialogo._editor_cargar()
        texto = dialogo._editor_diag.get("1.0", "end")
        self.assertIn("Diagnóstico", texto)
        self.assertIn("sin puerta", texto)
        dialogo.destroy()

    def test_dialogo_aplica_identidad_y_carga_dna(self):
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        dialogo._editor_vars["uso"].set("CT_ROOM")
        dialogo._editor_vars["nombre"].set("Tomografía (TAC)")
        dialogo._editor_aplicar("identidad")
        datos = edi.resumen_completo(self.context, self.local.id)
        self.assertEqual(datos["uso"], "CT_ROOM")
        self.assertIn("Tomografía (TAC)",
                      dialogo._editor_diag.get("1.0", "end"))
        dialogo.destroy()

    def test_dialogo_ilumina_el_local(self):
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        dialogo._editor_aplicar("iluminar")
        luminarias = [n for n in self.context.installations.list(
            "NODE", self.context.project.id) if n.kind == "LUMINAIRE"]
        self.assertTrue(luminarias)
        self.assertIsNotNone(dialogo._editor_resultado["resumen"])
        dialogo.destroy()

    def test_dialogo_redimensiona_desde_los_campos(self):
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        dialogo._editor_vars["ancho"].set("5.0")
        dialogo._editor_vars["fondo"].set("4.0")
        dialogo._editor_vars["amueblar"].set(False)
        dialogo._editor_aplicar("redimensionar")
        datos = edi.datos_local(self.context, self.local.id)
        self.assertAlmostEqual(datos["ancho_m"], 5.0, places=6)
        self.assertAlmostEqual(datos["fondo_m"], 4.0, places=6)
        dialogo.destroy()

    def test_error_amable_en_el_dialogo(self):
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        dialogo._editor_vars["espesor"].set("2.5")
        from ui import app_window as aw
        original = aw.messagebox.showerror
        capturado = {}
        aw.messagebox.showerror = lambda *a, **k: capturado.update(
            {"args": a})
        try:
            dialogo._editor_aplicar("espesor")  # error amable, no bloquea
        finally:
            aw.messagebox.showerror = original
        self.assertTrue(capturado, "esperaba el error amable")
        self.assertIn("se come", str(capturado["args"][1]))
        dialogo.destroy()


if __name__ == "__main__":
    unittest.main()

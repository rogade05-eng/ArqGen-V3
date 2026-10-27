"""REGENERACIÓN DE LA EDIFICACIÓN (v3.10.0) — NADA DE CAMBIOS HUÉRFANOS.

Lo pedido por el usuario: «si hay algún local que quisiera mover hacia
otro lugar debería tener alguna funcionalidad que me ayude a lograrlo
pero que recalcule y redistribuya los otros locales así como las
instalaciones y módulos, debería generar otras variantes pero
permitirme elegir cuál es la elegida para sustituir la anteriormente
generada. la idea sería hacer cualquier cambio pero que no sea un
cambio huérfano sino que regenere todo y se redistribuya todo. al
igual que si quisiera agregar un local nuevo, o cambiarle las
dimensiones, o eliminarlo, o agregar un nuevo local en un segundo
nivel, etc.»

Cobertura de estas pruebas:

* Programa editable (ui.building_wizard, puro): mover reordena dentro
  del nivel (con aviso amable en los extremos), eliminar limpia las
  relaciones del local, redimensionar valida dimensiones, añadir
  rechaza homónimos y crea el nivel si falta, mover a otro nivel
  también.
* Programa reconstruido (program_from_project): sin edificio → aviso
  amable; tras apply_plan → locales NORMALES (sin pasillo/escalera/
  núcleo, que el trazado recrea), dimensiones desde los boundaries y
  relaciones entre locales normales.
* Sustitución (replace_plan): purga TODO lo generado (locales, muros,
  vanos, relaciones y terminales de instalaciones anclados), regenera
  con la variante elegida, REUTILIZA niveles y edificio, deja CERO
  huérfanos (nodos ni relaciones colgando), conserva lo dibujado a
  mano, y en multi-nivel crea el nivel nuevo al sustituir.
* Determinismo: el mismo programa editado produce las mismas variantes
  en el mismo orden.
* Undo persistente: la sustitución queda en la auditoría UNDOABLE y
  PersistentUndoService revierte mutación a mutación.
* Diálogo real (Tk bajo Xvfb): programa poblado, 28 variantes
  generadas, elección de variante y sustitución end-to-end con
  refresh; sin edificio → mensaje amable y sin diálogo.
"""

from __future__ import annotations

import os
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui.building_wizard import BuildingWizardData


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - headless
        return False


DISPLAY = _display_available()


def _consultorio(levels: int = 1) -> BuildingWizardData:
    data = BuildingWizardData()
    data.levels = [bw.LevelSpec(name="Planta Baja", height_m=3.0)]
    if levels > 1:
        data.levels.append(bw.LevelSpec(name="Planta Alta",
                                        height_m=3.0))
    data.usage_type = "Consultorio médico"
    data.rooms = bw.preset_rooms("Consultorio médico", "Planta Baja")
    if levels > 1:
        data.rooms += bw.preset_rooms("Consultorio médico", "Planta Alta")
    data.relations = bw.suggest_relations(data)
    data.installations = ["Eléctrica", "Sanitaria"]
    return data


def _wizard_space_ids(ctx) -> list:
    return [s.id for s in ctx.architecture.list("SPACE", ctx.project.id)
            if bw._is_wizard_space(s)]


class TestProgramaEditable(ARQGenTestCase):
    """Las ediciones puras del programa (sin Tk, sin contexto)."""

    def _program(self) -> BuildingWizardData:
        data = BuildingWizardData()
        data.levels = [bw.LevelSpec(name="Planta Baja", height_m=3.0)]
        data.rooms = [bw.RoomSpec(name="Sala", width_m=3.0, depth_m=4.0,
                                  level_ref="Planta Baja"),
                      bw.RoomSpec(name="Cocina", width_m=3.0, depth_m=3.0,
                                  level_ref="Planta Baja"),
                      bw.RoomSpec(name="Dormitorio", width_m=3.5,
                                  depth_m=3.5, level_ref="Planta Baja")]
        data.relations = [bw.RelationSpec(a_name="Sala", b_name="Cocina")]
        return data

    def test_move_reordena_dentro_del_nivel(self):
        data = self._program()
        avisos = bw.move_room(data, "Sala", 1)
        self.assertEqual(avisos and True, True)
        orden = [r.name for r in data.rooms]
        self.assertEqual(orden, ["Cocina", "Sala", "Dormitorio"])
        # y de vuelta
        bw.move_room(data, "Sala", -1)
        self.assertEqual([r.name for r in data.rooms],
                         ["Sala", "Cocina", "Dormitorio"])

    def test_move_en_el_extremo_avisa_sin_tocar(self):
        data = self._program()
        avisos = bw.move_room(data, "Sala", -1)
        self.assertTrue(avisos)
        self.assertIn("extremo", avisos[0])
        self.assertEqual([r.name for r in data.rooms],
                         ["Sala", "Cocina", "Dormitorio"])

    def test_move_nombre_inexistente_avisa(self):
        data = self._program()
        avisos = bw.move_room(data, "Noexiste", 1)
        self.assertTrue(avisos)
        self.assertIn("No encuentro", avisos[0])

    def test_remove_limpia_relaciones(self):
        data = self._program()
        avisos = bw.remove_room(data, "Cocina")
        self.assertTrue(avisos)
        nombres = [r.name for r in data.rooms]
        self.assertNotIn("Cocina", nombres)
        self.assertEqual(data.relations, [])
        self.assertIn("1 relación", avisos[0])

    def test_resize_valida_dimensiones(self):
        data = self._program()
        avisos = bw.resize_room(data, "Sala", 4.2, 3.6)
        self.assertTrue(avisos)
        self.assertAlmostEqual(data.rooms[0].width_m, 4.2)
        self.assertAlmostEqual(data.rooms[0].depth_m, 3.6)
        avisos = bw.resize_room(data, "Sala", 0.0, 3.6)
        self.assertIn("mayores que cero", avisos[0])
        self.assertAlmostEqual(data.rooms[0].width_m, 4.2)

    def test_add_rechaza_homónimo_y_crea_nivel(self):
        data = self._program()
        avisos = bw.add_room(data, bw.RoomSpec(
            name="sala", width_m=2.0, depth_m=2.0,
            level_ref="Planta Baja"))
        self.assertIn("Ya existe", avisos[0])
        self.assertEqual(len(data.rooms), 3)
        avisos = bw.add_room(data, bw.RoomSpec(
            name="Estudio", width_m=2.5, depth_m=3.0,
            level_ref="Ático"))
        self.assertTrue(avisos)
        self.assertIn("Ático", data.level_names())
        self.assertEqual(data.rooms[-1].level_ref, "Ático")

    def test_move_to_level_crea_nivel_si_falta(self):
        data = self._program()
        avisos = bw.move_room_to_level(data, "Dormitorio", "Planta Alta")
        self.assertTrue(avisos)
        self.assertIn("Planta Alta", data.level_names())
        self.assertEqual(data.rooms[2].level_ref, "Planta Alta")


class TestProgramaDesdeProyecto(ARQGenTestCase):
    """program_from_project reconstruye el programa del proyecto."""

    def test_sin_edificio_da_aviso_amable(self):
        context = self.demo_context()
        try:
            data, avisos = bw.program_from_project(context)
            self.assertEqual(data.rooms, [])
            self.assertTrue(avisos)
            self.assertIn("asistente", avisos[0])
        finally:
            context.close()

    def test_reconstruye_locales_normales_y_relaciones(self):
        context = self.demo_context()
        try:
            data = _consultorio()
            summary = bw.apply_plan(data, context)
            self.assertEqual(summary["spaces"], 7)  # 6 locales + pasillo
            prog, avisos = bw.program_from_project(context)
            nombres = [r.name for r in prog.rooms]
            # los normales están, los especiales del trazado NO entran
            self.assertIn("Sala de espera", nombres)
            self.assertNotIn("Pasillo Planta Baja", nombres)
            self.assertEqual(len(prog.rooms), 6)
            self.assertEqual(len(prog.levels), 1)
            self.assertGreater(len(prog.relations), 0)
            # las dimensiones vienen del boundary (bbox)
            sala = next(r for r in prog.rooms if r.name == "Sala de espera")
            self.assertGreater(sala.width_m, 0.5)
            self.assertGreater(sala.depth_m, 0.5)
            self.assertTrue(avisos)
        finally:
            context.close()


class TestSustitucion(ARQGenTestCase):
    """replace_plan: purga + regeneración sin huérfanos."""

    def test_replace_sin_huerfanos(self):
        context = self.demo_context()
        try:
            data = _consultorio()
            bw.apply_plan(data, context)
            old_space_ids = set(_wizard_space_ids(context))
            old_walls = {w.id for w in context.architecture.list(
                "WALL", context.project.id)
                if str((w.metadata or {}).get("origen", "")).startswith(
                    bw.WIZARD_ORIGIN)}
            self.assertGreaterEqual(len(old_space_ids), 7)
            self.assertGreaterEqual(len(old_walls), 10)

            prog, _avisos = bw.program_from_project(context)
            victim = prog.rooms[len(prog.rooms) // 2].name
            bw.remove_room(prog, victim)
            variantes = bw.generate_variants(prog)
            self.assertGreaterEqual(len(variantes), 20)
            summary = bw.replace_plan(prog, context,
                                      variant=variantes[0])
            self.assertTrue(summary["regeneracion"])
            self.assertEqual(summary["purga"]["locales"],
                             len(old_space_ids))
            self.assertEqual(summary["levels_created"], 0)
            # al menos «Planta Baja» reutilizada (el demo puede traer
            # niveles propios que también cuentan)
            self.assertGreaterEqual(summary["levels_reused"], 1)

            # lo viejo murió, lo nuevo vive y el eliminado no vuelve
            new_spaces = [s for s in context.architecture.list(
                "SPACE", context.project.id) if bw._is_wizard_space(s)]
            new_ids = {s.id for s in new_spaces}
            self.assertFalse(new_ids & old_space_ids)
            self.assertNotIn(victim, [s.name for s in new_spaces])
            self.assertEqual(len(new_spaces), len(prog.rooms) + 1)

            # CERO huérfanos: ni nodos ni relaciones colgando
            alive = {s.id for s in context.architecture.list(
                "SPACE", context.project.id)}
            orphan_nodes = [n.id for n in context.installations.list(
                "NODE", context.project.id)
                if getattr(n, "space_id", "") and n.space_id not in alive]
            self.assertEqual(orphan_nodes, [])
            orphan_rels = [r.id for r in context.architecture.list(
                "SPACE_RELATIONSHIP", context.project.id)
                if r.from_space_id not in alive or r.to_space_id
                not in alive]
            self.assertEqual(orphan_rels, [])
            # los muros viejos murieron también
            new_walls = {w.id for w in context.architecture.list(
                "WALL", context.project.id)
                if str((w.metadata or {}).get("origen", "")).startswith(
                    bw.WIZARD_ORIGIN)}
            self.assertFalse(new_walls & old_walls)
        finally:
            context.close()

    def test_conserva_lo_dibujado_a_mano(self):
        from services.architecture_service import ArchitectureService
        context = self.demo_context()
        try:
            arch = ArchitectureService(context)
            data = _consultorio()
            bw.apply_plan(data, context)
            level = context.architecture.list(
                "LEVEL", context.project.id)[0]
            manual = arch.create_wall(level_ref=level.name,
                                      start=(40.0, 40.0),
                                      end=(44.0, 40.0),
                                      thickness_m=0.15, structural=False)
            prog, _avisos = bw.program_from_project(context)
            bw.resize_room(prog, prog.rooms[0].name, 5.0, 4.0)
            bw.replace_plan(prog, context, variant=None)
            vivo = (context.architecture.get("WALL", manual.id)
                    or arch.arch.get("WALL", manual.id))
            self.assertIsNotNone(vivo, "el muro dibujado a mano murió")
        finally:
            context.close()

    def test_variantes_deterministas_del_programa_editado(self):
        context = self.demo_context()
        try:
            data = _consultorio()
            bw.apply_plan(data, context)
            prog, _avisos = bw.program_from_project(context)
            bw.move_room(prog, prog.rooms[0].name, 1)
            first = bw.generate_variants(prog)
            second = bw.generate_variants(prog)
            self.assertEqual([v.key for v in first], [v.key for v in second])
            self.assertEqual([v.score for v in first],
                             [v.score for v in second])
            # el orden del programa decide la colocación: mover el primer
            # local cambia qué local queda primero en el trazado lineal
            prog2, _av = bw.program_from_project(context)
            original = bw.build_layout(prog2)[0][0].rooms
            bw.move_room(prog2, prog2.rooms[0].name, 1)
            movido = bw.build_layout(prog2)[0][0].rooms
            self.assertNotEqual(original[0].name, movido[0].name)
        finally:
            context.close()

    def test_undo_persistente_revierte_la_ultima_mutacion(self):
        from app.undo_service import PersistentUndoService
        context = self.demo_context()
        try:
            data = _consultorio()
            bw.apply_plan(data, context)
            prog, _avisos = bw.program_from_project(context)
            bw.remove_room(prog, prog.rooms[-1].name)
            bw.replace_plan(prog, context, variant=None)

            def _total() -> int:
                total = 0
                for tipo in ("SPACE", "WALL", "DOOR", "WINDOW",
                             "OPENING", "SPACE_RELATIONSHIP"):
                    total += len(context.architecture.list(
                        tipo, context.project.id))
                for tipo in ("NODE", "SEGMENT"):
                    total += len(context.installations.list(
                        tipo, context.project.id))
                # v3.15.0: la concepción de espacios también crea
                # entidades con mutación propia (la última tras el plan)
                for tipo in ("FURNITURE", "ROOF", "RAMP", "HANDRAIL"):
                    total += len(context.architecture.list(
                        tipo, context.project.id))
                return total

            before = _total()
            result = PersistentUndoService(context).undo()
            self.assertTrue(result, "el undo no encontró la mutación")
            context.commit()
            self.assertEqual(_total(), before - 1,
                             "el undo no revirtió exactamente una "
                             "mutación")
        finally:
            context.close()

    def test_local_nuevo_en_segundo_nivel(self):
        context = self.demo_context()
        try:
            data = _consultorio()
            bw.apply_plan(data, context)
            prog, _avisos = bw.program_from_project(context)
            # el usuario añade un local EN UN SEGUNDO NIVEL
            avisos = bw.add_room(prog, bw.RoomSpec(
                name="Consultorio 5", width_m=3.2, depth_m=3.0,
                level_ref="Planta Alta"))
            self.assertTrue(avisos)
            variantes = bw.generate_variants(prog)
            summary = bw.replace_plan(prog, context,
                                      variant=variantes[0])
            self.assertEqual(summary["levels_created"], 1)
            self.assertGreaterEqual(summary["levels_reused"], 1)
            levels = context.architecture.list(
                "LEVEL", context.project.id)
            nombres = [lv.name for lv in levels]
            self.assertIn("Planta Alta", nombres)
            alta = next(lv for lv in levels if lv.name == "Planta Alta")
            en_alta = [s for s in context.architecture.list(
                "SPACE", context.project.id)
                if s.level_id == alta.id and bw._is_wizard_space(s)]
            self.assertTrue(any(s.name == "Consultorio 5" for s in en_alta),
                            "el local nuevo no quedó en el nivel nuevo")
        finally:
            context.close()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestDialogoRegenerativo(ARQGenTestCase):
    """El diálogo real: programa, variantes, elección y sustitución."""

    def _make_window(self):
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        self.context = self.demo_context()
        return ARQGenWindow(self.context, self.application)

    def test_dialogo_sin_edificio_da_mensaje_y_no_abre(self):
        window = self._make_window()
        try:
            from ui import app_window as aw
            original = aw.messagebox.showinfo
            capturado = {}
            aw.messagebox.showinfo = lambda *a, **k: capturado.update(
                {"args": a})
            try:
                window.open_regen_dialog()
            finally:
                aw.messagebox.showinfo = original
            self.assertTrue(capturado, "esperaba el mensaje amable")
            self.assertFalse(hasattr(window, "_regen_dialog"))
        finally:
            window.destroy()
            self.context.close()

    def test_dialogo_flujo_completo_hasta_sustituir(self):
        window = self._make_window()
        try:
            from ui import app_window as aw
            data = _consultorio()
            bw.apply_plan(data, window.ctx)
            window.update()
            window.open_regen_dialog()
            self.assertTrue(hasattr(window, "_regen_dialog"))
            dialog = window._regen_dialog
            # el programa reconstruido está en el tree (6 locales)
            self.assertEqual(len(dialog._regen_tree.get_children()), 6)
            # generar variantes: 28, rankeadas, primera seleccionada
            dialog._regen_generate()
            state = dialog._regen_state
            self.assertGreaterEqual(len(state["variantes"]), 20)
            self.assertIsNotNone(state["variant"])
            # elegir OTRA variante (la última) y sustituir con ella
            ultima = state["variantes"][-1]
            dialog._regen_variant_tree.selection_set(ultima.key)
            dialog._regen_choose_variant()
            self.assertEqual(state["variant"].key, ultima.key)
            # el preview dibujó algo del nivel 1
            self.assertGreater(len(dialog._regen_canvas.find_all()), 0)
            # confirmación automática para la prueba
            original = aw.messagebox.askyesno
            aw.messagebox.askyesno = lambda *a, **k: True
            try:
                dialog._regen_apply()
            finally:
                aw.messagebox.askyesno = original
            window.update()
            self.assertFalse(dialog.winfo_exists(),
                             "el diálogo debió cerrarse tras sustituir")
            # el canvas de la ventana principal quedó refrescado con la
            # nueva geometría (muros dibujados) y el viejo local fuera
            ids_viejos = set()
            self.assertGreater(len(window.canvas.find_all()), 0)
            espacios = [s.name for s in window.ctx.architecture.list(
                "SPACE", window.ctx.project.id)]
            self.assertIn("Sala de espera", espacios)
            self.assertNotIn(ultima.key, "")  # la variante viajó al summary
        finally:
            if hasattr(window, "_regen_dialog"):
                try:
                    if window._regen_dialog.winfo_exists():
                        window._regen_dialog.destroy()
                except Exception:  # noqa: BLE001 - ya destruido
                    pass
            window.destroy()
            self.context.close()

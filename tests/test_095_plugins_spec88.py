"""Plugin registry compliance tests (spec sections 31, 88, 89).

Verifica que el registro de plugins builtin cubra la lista completa
del §88, que GAS esté integrado como plugin del sistema de
instalaciones (§31), que cada plugin declare el contrato §89 con
contenido verídico (calculadores existentes en QTO, rulesets en
resources, grupos de comandos en la CLI) y que cada archivo builtin
pase la validación estática de FASE 39.
"""

from __future__ import annotations

import os
import unittest

from app.paths import PROJECT_ROOT
from plugins.plugin_api import validate_plugin_file

BUILTIN_DIR = os.path.join(PROJECT_ROOT, "plugins", "builtin")


def _load_registry():
    from app.bootstrap import bootstrap

    class Args:
        log_dir = "/tmp/arqgen_plugin_logs_test"
        backup_dir = "/tmp/arqgen_plugin_backups_test"

    os.makedirs(Args.log_dir, exist_ok=True)
    os.makedirs(Args.backup_dir, exist_ok=True)
    application, loader = bootstrap(Args())
    return loader


class TestSpec88Registry(unittest.TestCase):
    """El registro builtin debe cubrir la lista completa del §88."""

    @classmethod
    def setUpClass(cls):
        cls.loader = _load_registry()
        cls.plugins = {}
        for entry in cls.loader.loaded:
            if entry.error or entry.plugin is None:
                continue
            cls.plugins[entry.plugin.plugin_id] = entry.plugin

    def test_no_loader_errors(self):
        broken = [(e.source, e.error) for e in self.loader.loaded
                  if e.error or e.plugin is None]
        self.assertFalse(broken, f"Plugins con error de carga: {broken}")

    def test_spec88_list_complete(self):
        # §88: Architecture, Structure, Installations, CCTV, Fire,
        #      Intrusion, Access, Perimeter, QTO, Budget, BIM,
        #      Documentation
        spec88 = {"architecture", "structure", "installations", "cctv",
                  "fire", "intrusion", "access", "perimeter", "qto",
                  "budget", "bim", "documentation"}
        missing = spec88 - set(self.plugins)
        self.assertFalse(missing, f"Plugins §88 ausentes: {missing}")

    def test_gas_is_installations_plugin(self):
        # §31: "Debe quedar integrado como plugin del sistema de
        # instalaciones".
        self.assertIn("gas", self.plugins)
        gas = self.plugins["gas"]
        self.assertIn("installations", gas.dependencies)
        self.assertIn("gas size", gas.commands)
        self.assertIn("gas check", gas.commands)
        self.assertIn("GAS_PIPE_LENGTH", gas.calculators)
        self.assertIn("gas_validation", gas.reports)
        # Validaciones §31 declaradas como reglas del plugin.
        for validation in ("GAS_DIAMETERS", "GAS_ROUTES", "GAS_VALVES",
                           "GAS_VENTILATION", "GAS_SEPARATION",
                           "GAS_CONSUMPTION_POINTS"):
            self.assertIn(validation, gas.rules)

    def test_installations_scope_slimmed(self):
        inst = self.plugins["installations"]
        # Las disciplinas con plugin propio ya no se declaran aquí.
        for foreign in ("gas", "struct", "sec", "clash", "precons", "bim"):
            self.assertNotIn(foreign, inst.commands)
        self.assertEqual(inst.services, ["InstallationsService"])


class TestSpec89Contract(unittest.TestCase):
    """Cada plugin declara el contrato §89 con contenido verídico."""

    @classmethod
    def setUpClass(cls):
        cls.loader = _load_registry()
        cls.plugins = {}
        for entry in cls.loader.loaded:
            if entry.error or entry.plugin is None:
                continue
            cls.plugins[entry.plugin.plugin_id] = entry.plugin

    DECLARATIONS = ("dependencies", "entities", "services", "events",
                    "commands", "rules", "calculators", "importers",
                    "exporters", "reports")

    def test_all_declarations_are_string_lists(self):
        for plugin_id, plugin in self.plugins.items():
            for name in self.DECLARATIONS:
                value = getattr(plugin, name)
                self.assertIsInstance(
                    value, list,
                    f"{plugin_id}.{name} debe ser lista")
                self.assertTrue(
                    all(isinstance(item, str) for item in value),
                    f"{plugin_id}.{name} debe contener solo str")

    def test_plugins_expose_services(self):
        # Todo plugin de dominio declara al menos un servicio o un
        # exportador (plugins puramente declarativos no admitidos).
        for plugin_id, plugin in self.plugins.items():
            self.assertTrue(
                plugin.services or plugin.exporters,
                f"El plugin {plugin_id} no declara servicios ni "
                "exportadores")

    def test_command_groups_match_cli(self):
        # Los comandos declarados son o bien comandos del bus
        # (MAYÚSCULAS_CON_GUIONES, p.ej. CREATE_ENTITY) o bien grupos
        # y subcomandos de la CLI real.
        cli_groups = {"net", "node", "link", "elec", "san", "hvac", "plu",
                      "gas", "tel", "struct", "sec", "clash", "precons",
                      "bim", "docs", "export", "qto", "budget", "price"}
        for plugin_id, plugin in self.plugins.items():
            for command in plugin.commands:
                group = command.split()[0]
                if group == group.upper():
                    continue  # comando del bus de comandos (§76)
                self.assertIn(
                    group, cli_groups,
                    f"{plugin_id} declara el comando {command!r} sin "
                    "grupo CLI correspondiente")

    def test_calculators_exist_in_qto_registry(self):
        from engines.quantity_engine import (DEFAULT_FORMULAS,
                                             INSTALL_FORMULAS,
                                             SECURITY_FORMULAS,
                                             STRUCT_FORMULAS)
        known = {f.code for f in (DEFAULT_FORMULAS + INSTALL_FORMULAS
                                  + STRUCT_FORMULAS + SECURITY_FORMULAS)}
        for plugin_id, plugin in self.plugins.items():
            for calc in plugin.calculators:
                self.assertIn(
                    calc, known,
                    f"{plugin_id} declara el calculador inexistente "
                    f"{calc!r}")

    def test_ruleset_files_exist(self):
        # Reglas en minúsculas son rulesets versionados en resources.
        for plugin_id, plugin in self.plugins.items():
            for rule in plugin.rules:
                if rule != rule.lower():
                    continue  # validaciones de motor (p.ej. GAS_*)
                path = os.path.join(PROJECT_ROOT, "resources", "rulesets",
                                    f"{rule}.json")
                self.assertTrue(
                    os.path.exists(path),
                    f"{plugin_id} declara el ruleset inexistente {rule!r}")


class TestBuiltinFilesValidate(unittest.TestCase):
    """FASE 39: cada archivo builtin pasa la validación estática."""

    def test_validate_builtin_files(self):
        names = sorted(f for f in os.listdir(BUILTIN_DIR)
                       if f.endswith(".py") and not f.startswith("_"))
        self.assertGreaterEqual(len(names), 15)
        for name in names:
            result = validate_plugin_file(os.path.join(BUILTIN_DIR, name))
            self.assertTrue(
                result["ok"],
                f"{name}: {result['errors']}")


if __name__ == "__main__":
    unittest.main()

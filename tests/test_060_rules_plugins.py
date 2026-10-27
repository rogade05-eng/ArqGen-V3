"""Rules, validation, plugins, permissions, versions compare (spec 12-13, 82, 88)."""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase


class TestRulesAndValidation(ARQGenTestCase):
    def test_ruleset_install_and_active(self):
        ctx = self.application.create_project(self.project_path(), name="Rules")
        ctx.user = "tester"
        from services.analysis_service import RuleService
        ruleset = RuleService(ctx).load_ruleset_from_resources("international_v1")
        self.assertEqual(ruleset.code, "international_v1")
        self.assertEqual(len(ruleset.rules), 5)
        installed = RuleService(ctx).list_installed()
        self.assertIn("international_v1", installed)
        active = RuleService(ctx).active_ruleset()
        self.assertIsNotNone(active)
        ctx.close()

    def test_validation_catches_thin_wall(self):
        ctx = self.application.create_project(self.project_path(), name="Val")
        ctx.user = "tester"
        from services.analysis_service import RuleService, ValidationService
        from services.architecture_service import ArchitectureService
        RuleService(ctx).load_ruleset_from_resources("international_v1")
        service = ArchitectureService(ctx)
        service.create_level("N1", 0.0, 3.0)
        service.create_wall("N1", (0, 0), (5, 0), thickness_m=0.05)  # < 0.1 min
        result = ValidationService(ctx).validate_project()
        codes = [f.code for f in result.errors]
        self.assertIn("ARQ-WALL-001", codes)
        self.assertEqual(result.status.value, "INVALID")
        ctx.close()

    def test_validation_door_accessibility(self):
        ctx = self.application.create_project(self.project_path(), name="Val2")
        ctx.user = "tester"
        from services.analysis_service import RuleService, ValidationService
        from services.architecture_service import ArchitectureService
        RuleService(ctx).load_ruleset_from_resources("international_v1")
        service = ArchitectureService(ctx)
        service.create_level("N1", 0.0, 3.0)
        wall = service.create_wall("N1", (0, 0), (5, 0))
        service.create_opening("DOOR", wall.code, 0.60, 2.1)  # < 0.75 min
        result = ValidationService(ctx).validate_project()
        self.assertTrue(any(f.code == "ARQ-DOOR-001" for f in result.errors))
        ctx.close()

    def test_validation_detects_orphan_and_overflow(self):
        ctx = self.application.create_project(self.project_path(), name="Val3")
        ctx.user = "tester"
        from services.analysis_service import ValidationService
        from services.architecture_service import ArchitectureService
        service = ArchitectureService(ctx)
        service.create_level("N1", 0.0, 3.0)
        wall = service.create_wall("N1", (0, 0), (5, 0))
        # Vano que no cabe: 4.5 + 0.9 > 5.0
        with self.assertRaises(Exception):
            service.create_opening("DOOR", wall.code, 0.9, 2.1, offset_m=4.5)
        result = ValidationService(ctx).validate_project()
        self.assertTrue(result.is_ok)
        ctx.close()

    def test_hard_block_rule_blocks(self):
        from core.rules.models import Rule, RuleSeverity, Ruleset
        rule = Rule(code="BLOCK-1", discipline="ARCHITECTURE", category="TEST",
                    severity=RuleSeverity.HARD_BLOCK, expression="thickness > 10",
                    message="imposible", parameters={})
        ruleset = Ruleset(code="blocking_v1", jurisdiction="Test", discipline="ARCHITECTURE",
                          version="1.0", effective_date="2026-01-01", source="test",
                          rules=[rule])
        ctx = self.application.create_project(self.project_path(), name="Block")
        ctx.user = "tester"
        from services.analysis_service import RuleService, ValidationService
        from services.architecture_service import ArchitectureService
        RuleService(ctx).install_ruleset(ruleset)
        service = ArchitectureService(ctx)
        service.create_level("N1", 0.0, 30.0)
        service.create_wall("N1", (0, 0), (5, 0), thickness_m=11.0, height_m=30.0)
        result = ValidationService(ctx).validate_project()
        self.assertEqual(result.status.value, "BLOCKED")
        ctx.close()


class TestPlugins(unittest.TestCase):
    def test_builtin_plugins_load(self):
        from app.bootstrap import bootstrap

        class Args:
            log_dir = "/tmp/arqgen_plugin_logs_test"
            backup_dir = "/tmp/arqgen_plugin_backups_test"

        import os
        os.makedirs(Args.log_dir, exist_ok=True)
        os.makedirs(Args.backup_dir, exist_ok=True)
        application, loader = bootstrap(Args())
        ids = {entry.plugin.plugin_id for entry in loader.loaded if not entry.error}
        self.assertIn("architecture", ids)
        self.assertIn("qto", ids)
        self.assertIn("budget", ids)
        # Contract declared (spec 89)
        for entry in loader.loaded:
            if entry.error:
                continue
            p = entry.plugin
            self.assertTrue(p.plugin_id)
            self.assertTrue(p.name)
            self.assertIsInstance(p.services, list)

    def test_external_plugin_loaded(self):
        import os
        import tempfile
        from app.bootstrap import bootstrap
        from app.paths import PROJECT_ROOT

        external_dir = os.path.join(PROJECT_ROOT, "plugins", "external")
        os.makedirs(external_dir, exist_ok=True)
        plugin_file = os.path.join(external_dir, "_test_demo_plugin.py")
        with open(plugin_file, "w", encoding="utf-8") as fh:
            fh.write(
                "from plugins.plugin_api import ARQGenPlugin\n"
                "class DemoExternal(ARQGenPlugin):\n"
                "    plugin_id = 'demo_external'\n"
                "    name = 'Demo externo'\n"
                "    version = '0.1'\n"
                "    services = ['X']\n"
            )
        try:
            from plugins.plugin_api import PluginLoader
            from services.context import ApplicationContext
            application = ApplicationContext()
            loader = PluginLoader(application, external_dir=external_dir)
            loader.load_all()
            ids = {e.plugin.plugin_id for e in loader.loaded if not e.error}
            self.assertIn("demo_external", ids)
        finally:
            os.remove(plugin_file)


class TestPermissionsAndVersions(unittest.TestCase):
    def test_permission_checks(self):
        from core.errors import PermissionDeniedError
        from core.permissions.service import Permission, PermissionService, User
        service = PermissionService()
        viewer = User("ana", {"viewer"})
        architect = User("bob", {"architect"})
        service.check(viewer, Permission.PROJECT_OPEN)
        with self.assertRaises(PermissionDeniedError):
            service.check(viewer, Permission.PRICE_EDIT)
        service.check(architect, Permission.PRICE_EDIT)

    def test_version_compare(self):
        import json
        import os
        import shutil
        import tempfile

        from app.demo import build_demo
        from exporters.json_io import JSONExporter
        from services.architecture_service import ArchitectureService
        from services.context import ApplicationContext
        from services.version_service import VersionService

        tmp = tempfile.mkdtemp(prefix="vercmp_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        application = ApplicationContext()
        ctx = build_demo(application, os.path.join(tmp, "v.arqgen"))
        snap1 = json.dumps(JSONExporter.build_snapshot(ctx), ensure_ascii=False)
        ArchitectureService(ctx).create_wall("Nivel 1", (0, 0), (3, 0))
        ctx.commit()
        snap2 = json.dumps(JSONExporter.build_snapshot(ctx), ensure_ascii=False)
        diff = VersionService(ctx).compare_versions(snap1, snap2)
        self.assertEqual(diff["types"]["WALL"]["count_a"], 7)
        self.assertEqual(diff["types"]["WALL"]["count_b"], 8)
        ctx.close()


if __name__ == "__main__":
    unittest.main()

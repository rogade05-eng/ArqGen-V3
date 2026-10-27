"""Migrations package (spec 79). Explicit imports for frozen builds."""

from persistence.migrations.m001_core import upgrade as upgrade_001, downgrade as downgrade_001, version as version_001, name as name_001
from persistence.migrations.m002_architecture import upgrade as upgrade_002, downgrade as downgrade_002, version as version_002, name as name_002
from persistence.migrations.m003_qto import upgrade as upgrade_003, downgrade as downgrade_003, version as version_003, name as name_003
from persistence.migrations.m004_budget import upgrade as upgrade_004, downgrade as downgrade_004, version as version_004, name as name_004
from persistence.migrations.m005_installations import upgrade as upgrade_005, downgrade as downgrade_005, version as version_005, name as name_005
from persistence.migrations.m006_structure import upgrade as upgrade_006, downgrade as downgrade_006, version as version_006, name as name_006
from persistence.migrations.m007_clash import upgrade as upgrade_007, downgrade as downgrade_007, version as version_007, name as name_007
from persistence.migrations.m008_documentation import upgrade as upgrade_008, downgrade as downgrade_008, version as version_008, name as name_008
from persistence.migrations.m009_diseno import upgrade as upgrade_009, downgrade as downgrade_009, version as version_009, name as name_009
from persistence.migrations.m010_fachada import upgrade as upgrade_010, downgrade as downgrade_010, version as version_010, name as name_010
from persistence.migrations.m011_escaleras import upgrade as upgrade_011, downgrade as downgrade_011, version as version_011, name as name_011


class _Migration:
    """Adapter presenting the runner's expected interface."""

    def __init__(self, version: int, name: str, upgrade, downgrade) -> None:
        self.version = version
        self.name = name
        self.upgrade = upgrade
        self.downgrade = downgrade


MIGRATIONS = [
    _Migration(version_001, name_001, upgrade_001, downgrade_001),
    _Migration(version_002, name_002, upgrade_002, downgrade_002),
    _Migration(version_003, name_003, upgrade_003, downgrade_003),
    _Migration(version_004, name_004, upgrade_004, downgrade_004),
    _Migration(version_005, name_005, upgrade_005, downgrade_005),
    _Migration(version_006, name_006, upgrade_006, downgrade_006),
    _Migration(version_007, name_007, upgrade_007, downgrade_007),
    _Migration(version_008, name_008, upgrade_008, downgrade_008),
    _Migration(version_009, name_009, upgrade_009, downgrade_009),
    _Migration(version_010, name_010, upgrade_010, downgrade_010),
    _Migration(version_011, name_011, upgrade_011, downgrade_011),
]

__all__ = ["MigrationRunner", "applied_versions", "MIGRATIONS"]

from persistence.migrations.runner import MigrationRunner, applied_versions  # noqa: E402

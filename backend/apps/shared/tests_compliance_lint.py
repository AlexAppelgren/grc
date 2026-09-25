"""The compliance lint's two setting rules (scripts/compliance_check.py).

maintenance-hatch: the setting that switches the append-only triggers off may be named only
by the migration helpers, migrations and tests, so request code cannot reach it. PostgreSQL
folds a setting name, so `CW.MAINTENANCE`, `Cw . Maintenance` and the quoted
`"CW"."MAINTENANCE"` are the same setting, and the rule reads the source case-insensitively,
across the spaces a formatter may leave around the dot and through the quotes.

library-door (H16, ADR 0058): the door the library-zone trigger reads, the constant that
holds its name and the `library_door()` that sets it may be named only by the tenancy
module, the index door, the migration helpers, migrations and tests. The app role can set
the setting itself, so opening a door anywhere else would let that module's writes through
the database's own check; the lint keeps it to the doors.

The lint is loaded by path and run over planted files in a temporary tree, never over the
source tree."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest import mock

from django.test import SimpleTestCase

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compliance_check.py"
PLANTED = {
    # Allowed: the helpers that define it, a migration, a test.
    "apps/shared/migration_helpers.py": "MAINTENANCE_SETTING = 'cw.maintenance'\n",
    "apps/library/migrations/0009_fix.py": "SQL = \"SET LOCAL cw.maintenance = 'on'\"\n",
    "apps/shared/tests_audit_on_write.py": "SQL = \"SET LOCAL cw.maintenance = 'on'\"\n",
    # Refused: request code, a test helper, settings, the constant imported, a suppression.
    "apps/library/logic.py": "SQL = \"SET LOCAL cw.maintenance = 'on'\"\n",
    "apps/library/testing.py": "SQL = \"select set_config('cw.maintenance', 'on', true)\"\n",
    "config/settings.py": "# cw.maintenance is mentioned in a comment\n",
    "apps/cases/logic.py": "from apps.shared.migration_helpers import MAINTENANCE_SETTING\n",
    "apps/home/logic.py": "SQL = \"SET LOCAL cw.maintenance = 'on'\"  # compliance: maintenance-hatch because\n",
    # Refused: the same setting in the spellings PostgreSQL accepts (H12, then the H-B
    # review for the quoted one, which is what psql prints).
    "apps/watch/curation.py": "SQL = \"SET LOCAL CW.MAINTENANCE = 'on'\"\n",
    "apps/register/logic.py": "SQL = \"SET LOCAL Cw . Maintenance = 'on'\"\n",
    "apps/proposals/logic.py": "from apps.shared.migration_helpers import maintenance_setting as s\n",
    "apps/collab/logic.py": "SQL = 'SET LOCAL \"CW\".\"MAINTENANCE\" = \\'on\\''\n",
}
DOOR_PLANTED = {
    # Allowed: the doors that set it, the helpers whose trigger reads it, a migration, a test.
    "apps/shared/tenancy.py": "LIBRARY_DOOR_SETTING = 'cw.library_door'\n",
    "apps/search/indexing.py": "from apps.shared.tenancy import library_door\n",
    "apps/shared/migration_helpers.py": "SQL = \"current_setting('cw.library_door', true)\"\n",
    "apps/shared/migrations/0008_library_write_guard.py": "TRIGGER = 'obligation_library_door'\n",
    "apps/shared/tests_library_db_guard.py": "SQL = \"SET LOCAL cw.library_door = 'seed'\"\n",
    # Refused: a door opened in request code, by a watch step, by a test builder and by the
    # proposal applier (which names its door through library_write(), never the setting);
    # the setting in settings; the constant imported; a suppression.
    "apps/library/logic.py": "SQL = \"SET LOCAL cw.library_door = 'proposal'\"\n",
    "apps/watch/curation.py": "with tenancy.library_door('watch'):\n    pass\n",
    "apps/library/testing.py": "SQL = \"select set_config('cw.library_door', 'seed', true)\"\n",
    "apps/proposals/apply.py": "from apps.shared.tenancy import library_door\n",
    "config/settings.py": "# cw.library_door is mentioned in a comment\n",
    "apps/cases/logic.py": "from apps.shared.tenancy import LIBRARY_DOOR_SETTING\n",
    "apps/home/logic.py": "SQL = \"SET LOCAL cw.library_door = 'seed'\"  # compliance: library-door because\n",
    # Refused: the spellings PostgreSQL accepts for the same setting.
    "apps/register/logic.py": "SQL = \"SET LOCAL CW.LIBRARY_DOOR = 'proposal'\"\n",
    "apps/collab/logic.py": "SQL = 'SET LOCAL \"CW\".\"LIBRARY_DOOR\" = \\'proposal\\''\n",
}


def load_lint() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compliance_check_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {spec.name: module}):  # its dataclass looks itself up
        spec.loader.exec_module(module)
    return module


def flagged(planted: dict[str, str]) -> list[tuple[str, str]]:
    """Every (path, rule) the lint reports over `planted`, written into a temporary tree."""
    lint = load_lint()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, source in planted.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(source, encoding="utf-8")
        with mock.patch.object(lint, "BACKEND", root):
            findings = lint.scan(sorted(root.rglob("*.py")))
        return sorted((finding.path.relative_to(root).as_posix(), finding.rule) for finding in findings)


class MaintenanceHatchRule(SimpleTestCase):
    def test_only_the_helpers_migrations_and_tests_may_name_the_hatch(self) -> None:
        self.assertEqual(
            flagged(PLANTED),
            [
                ("apps/cases/logic.py", "maintenance-hatch"),
                ("apps/collab/logic.py", "maintenance-hatch"),
                ("apps/home/logic.py", "maintenance-hatch"),
                ("apps/library/logic.py", "maintenance-hatch"),
                ("apps/library/testing.py", "maintenance-hatch"),
                ("apps/proposals/logic.py", "maintenance-hatch"),
                ("apps/register/logic.py", "maintenance-hatch"),
                ("apps/watch/curation.py", "maintenance-hatch"),
                ("config/settings.py", "maintenance-hatch"),
            ],
        )


class LibraryDoorRule(SimpleTestCase):
    def test_only_the_doors_the_helpers_migrations_and_tests_may_name_the_door(self) -> None:
        self.assertEqual(
            flagged(DOOR_PLANTED),
            [
                ("apps/cases/logic.py", "library-door"),
                ("apps/collab/logic.py", "library-door"),
                ("apps/home/logic.py", "library-door"),
                ("apps/library/logic.py", "library-door"),
                ("apps/library/testing.py", "library-door"),
                ("apps/proposals/apply.py", "library-door"),
                ("apps/register/logic.py", "library-door"),
                ("apps/watch/curation.py", "library-door"),
                ("config/settings.py", "library-door"),
            ],
        )

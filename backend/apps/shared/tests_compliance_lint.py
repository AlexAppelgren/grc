"""The compliance lint's maintenance-hatch rule (scripts/compliance_check.py). The setting
that switches the append-only triggers off may be named only by the migration helpers,
migrations and tests, so request code cannot reach it. PostgreSQL folds a setting name, so
`CW.MAINTENANCE` and `Cw . Maintenance` are the same setting and the rule reads the source
case-insensitively and across the spaces a formatter may leave around the dot. The lint is
loaded by path and run over planted files in a temporary tree, never over the source tree."""

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
    # Refused: the same setting in the spellings PostgreSQL accepts (H12).
    "apps/watch/logic.py": "SQL = \"SET LOCAL CW.MAINTENANCE = 'on'\"\n",
    "apps/register/logic.py": "SQL = \"SET LOCAL Cw . Maintenance = 'on'\"\n",
    "apps/proposals/logic.py": "from apps.shared.migration_helpers import maintenance_setting as s\n",
}


def load_lint() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compliance_check_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {spec.name: module}):  # its dataclass looks itself up
        spec.loader.exec_module(module)
    return module


class MaintenanceHatchRule(SimpleTestCase):
    def test_only_the_helpers_migrations_and_tests_may_name_the_hatch(self) -> None:
        lint = load_lint()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, source in PLANTED.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(source, encoding="utf-8")
            with mock.patch.object(lint, "BACKEND", root):
                findings = lint.scan(sorted(root.rglob("*.py")))
            flagged = sorted((finding.path.relative_to(root).as_posix(), finding.rule) for finding in findings)
        self.assertEqual(
            flagged,
            [
                ("apps/cases/logic.py", "maintenance-hatch"),
                ("apps/home/logic.py", "maintenance-hatch"),
                ("apps/library/logic.py", "maintenance-hatch"),
                ("apps/library/testing.py", "maintenance-hatch"),
                ("apps/proposals/logic.py", "maintenance-hatch"),
                ("apps/register/logic.py", "maintenance-hatch"),
                ("apps/watch/logic.py", "maintenance-hatch"),
                ("config/settings.py", "maintenance-hatch"),
            ],
        )

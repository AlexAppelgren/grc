"""Guard: kinds only (playbook 5, 15, VOC-01, INPUT_DELTAS §1).

Enumerates every enum class under apps/ (`enum.Enum` subclasses, including `StrEnum`,
and Django `Choices`, including `TextChoices`), plus every Postgres enum type in the
database, and demands each is in the tier-one allowlist `TIER_ONE_KINDS` with the delta
name it implements and a reason. A value an admin might add, rename or retire is a row.

Proven to fail 2026-09-19 by adding `class Urgency(enum.StrEnum)` to apps/cases/logic.py:
the test named the class, the module and the allowlist.
"""

from __future__ import annotations

import enum
import importlib
import inspect
import pkgutil
from pathlib import Path

from django.db import DEFAULT_DB_ALIAS, connections
from django.db.models import Choices
from django.test import TestCase

import apps
from apps.shared.kinds import TIER_ONE_KINDS


def production_module_names() -> list[str]:
    names = []
    for info in pkgutil.walk_packages(apps.__path__, prefix="apps."):
        parts = info.name.split(".")
        if "migrations" in parts or parts[-1].startswith("tests_") or parts[-1] == "testing":
            continue
        names.append(info.name)
    return names


def enum_classes() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for name in production_module_names():
        module = importlib.import_module(name)
        for value in vars(module).values():
            if not inspect.isclass(value) or value.__module__ != name:
                continue
            if value in (enum.Enum, enum.StrEnum, enum.IntEnum, Choices):
                continue
            if issubclass(value, enum.Enum) or issubclass(value, Choices):
                found.append((value.__name__, name))
    return found


class KindsOnlyGuard(TestCase):
    def test_every_enum_in_code_is_an_allowlisted_kind(self) -> None:
        found = enum_classes()
        self.assertGreater(len(found), 0, "no enums found; the enumeration is broken")
        unlisted = [f"{cls} in {module}" for cls, module in found if cls not in TIER_ONE_KINDS]
        self.assertEqual(
            unlisted,
            [],
            "Enums that are not tier-one kinds:\n  "
            + "\n  ".join(unlisted)
            + "\nEither make it a vocabulary row (playbook 15) or add it to apps/shared/kinds.py "
            "with the INPUT_DELTAS §1 name and a reason.",
        )

    def test_no_postgres_enum_types_exist(self) -> None:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT typname FROM pg_type WHERE typtype = 'e' ORDER BY typname")
            names = [row[0] for row in cursor.fetchall()]
        self.assertEqual(names, [], f"Postgres enum types exist: {names}. Kinds are CharFields with choices.")

    def test_the_allowlist_carries_a_delta_name_and_a_reason_for_every_entry(self) -> None:
        for cls, (delta_name, reason) in TIER_ONE_KINDS.items():
            with self.subTest(kind=cls):
                self.assertRegex(delta_name, r"^[a-z_]+$")
                self.assertGreater(len(reason), 15)

    def test_the_allowlist_file_is_plain_python(self) -> None:
        source = (Path(apps.__path__[0]) / "shared" / "kinds.py").read_text(encoding="utf-8")
        self.assertNotIn("django", source, "compliance_check.py imports kinds.py without Django")

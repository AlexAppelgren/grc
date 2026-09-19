"""Guard: schema names (playbook 5, 4.1).

Enumerates every `ninja.Schema` subclass across all apps' schemas.py modules and demands
that two apps never define divergent schemas with the same class name: Ninja flattens
components globally and the loser silently mistypes the generated client. Identical
duplicates (the same JSON schema) are allowed; the same class object imported into two
modules is one class.

Proven to fail 2026-09-19 by defining `class ProductInfo(CamelSchema): name: str` in
apps/home/schemas.py: the test named both modules and the differing fields.
"""

from __future__ import annotations

import importlib
import inspect
import json
from collections import defaultdict

from django.apps import apps
from django.test import SimpleTestCase
from ninja import Schema


def schema_classes() -> dict[str, list[type[Schema]]]:
    by_name: dict[str, list[type[Schema]]] = defaultdict(list)
    seen: set[int] = set()
    for config in apps.get_app_configs():
        if not config.name.startswith("apps."):
            continue
        try:
            module = importlib.import_module(f"{config.name}.schemas")
        except ModuleNotFoundError:
            continue
        for _, value in inspect.getmembers(module, inspect.isclass):
            if not issubclass(value, Schema) or value is Schema or id(value) in seen:
                continue
            seen.add(id(value))
            by_name[value.__name__].append(value)
    return by_name


class SchemaNamesGuard(SimpleTestCase):
    def test_no_two_apps_define_divergent_schemas_with_the_same_name(self) -> None:
        by_name = schema_classes()
        self.assertGreater(len(by_name), 0, "no schemas found; the enumeration is broken")
        conflicts: list[str] = []
        for name, classes in by_name.items():
            if len(classes) < 2:
                continue
            shapes = {json.dumps(cls.model_json_schema(), sort_keys=True) for cls in classes}
            if len(shapes) > 1:
                modules = ", ".join(cls.__module__ for cls in classes)
                conflicts.append(f"{name} defined differently in {modules}")
        self.assertEqual(
            conflicts,
            [],
            "Divergent schemas share a class name:\n  "
            + "\n  ".join(conflicts)
            + "\nPrefix the app-specific one with its app name (CasesTriageBody).",
        )

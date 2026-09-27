"""Findings of the security review of agent access and the bank's own records
(security-review-c11-access-d89, docs/reviews/CHUNK11_ACCESS_OWN_REVIEW.md) in the shared
mechanics. Each test was written first and failed before its fix.

M2: the test settings carry their own middleware list, so the scope statement
(`ScopeStatementMiddleware`, ACC-07) ran in every test and in no deployment after the wave
was merged. Every middleware the tests run must also be in the production list, in order.
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


def _production_middleware() -> list[str]:
    source = Path(settings.BASE_DIR, "config", "settings.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MIDDLEWARE" for t in node.targets):
            return [ast.literal_eval(element) for element in node.value.elts]  # type: ignore[attr-defined]
    raise AssertionError("config/settings.py names no MIDDLEWARE list")


class EveryTestedMiddlewareIsDeployed(SimpleTestCase):
    def test_the_test_list_is_the_production_list_in_its_order(self) -> None:
        production = _production_middleware()
        missing = [name for name in settings.MIDDLEWARE if name not in production]
        self.assertEqual(missing, [], "runs in tests but in no deployment")
        self.assertEqual(settings.MIDDLEWARE, [name for name in production if name in settings.MIDDLEWARE], "the order differs")

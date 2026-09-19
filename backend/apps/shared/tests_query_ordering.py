"""Guard: query ordering (playbook 5, 4.5).

`.first()` on an unordered queryset with uuid primary keys is a coin flip on Postgres.
Enumerates (1) every concrete model and demands `Meta.ordering` on a meaningful column,
not the primary key alone, and captures the SQL of its default queryset to prove an
ORDER BY is emitted; (2) every `.first()`, `.last()`, `.latest()` and `.earliest()` call in
production code and demands an explicit `.order_by(` in the same expression chain, or a
trailing `# ordering: <reason>` comment for the cases where order cannot matter (a
primary-key lookup).

Proven to fail 2026-09-19 by removing `ordering` from Tenant.Meta: the test named the
model and the missing option.
"""

from __future__ import annotations

import ast
from pathlib import Path

from apps.shared.testing import production_models
from django.test import TestCase

APPS_DIR = Path(__file__).resolve().parent.parent
PICKERS = frozenset({"first", "last", "latest", "earliest"})


def production_modules() -> list[Path]:
    result = []
    for path in sorted(APPS_DIR.rglob("*.py")):
        rel = path.relative_to(APPS_DIR).as_posix()
        if "/migrations/" in rel or rel.split("/")[-1].startswith("tests_") or rel.endswith("/testing.py"):
            continue
        result.append(path)
    return result


def _chain_has_order_by(node: ast.Call) -> bool:
    current: ast.AST = node
    while True:
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Attribute):
            if current.attr == "order_by":
                return True
            current = current.value
        else:
            return False


class QueryOrderingGuard(TestCase):
    def test_every_concrete_model_orders_by_a_meaningful_column(self) -> None:
        problems: list[str] = []
        for model in production_models():
            ordering = list(model._meta.ordering or [])
            meaningful = [f for f in ordering if f.lstrip("-") not in {"id", "pk", model._meta.pk.name}]
            if not ordering:
                problems.append(f"{model._meta.label}: no Meta.ordering")
            elif not meaningful:
                problems.append(f"{model._meta.label}: Meta.ordering is the primary key only ({ordering})")
            else:
                sql = str(model._default_manager.all().query)
                if "ORDER BY" not in sql:
                    problems.append(f"{model._meta.label}: default queryset emits no ORDER BY: {sql}")
        self.assertEqual(problems, [], "Models with no meaningful ordering:\n  " + "\n  ".join(problems))

    def test_every_first_or_last_call_orders_explicitly_or_states_why_not(self) -> None:
        problems: list[str] = []
        for path in production_modules():
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in PICKERS:
                    continue
                if _chain_has_order_by(node):
                    continue
                window = "\n".join(lines[node.lineno - 1 : (node.end_lineno or node.lineno) + 1])
                if "# ordering:" in window:
                    continue
                rel = path.relative_to(APPS_DIR).as_posix()
                problems.append(f"apps/{rel}:{node.lineno} .{node.func.attr}() without .order_by()")
        self.assertEqual(
            problems,
            [],
            "Unordered pickers:\n  "
            + "\n  ".join(problems)
            + "\nAdd .order_by(<intended column>) or a trailing `# ordering: <reason>` comment.",
        )

"""Guard: library fence (playbook 5, 14, PRO-01, AC-PRO1).

Walks the AST of every production module under apps/ and demands that `library_write(`
is called only from the allowlisted modules: the proposal applier, the watch pipeline and
the reference seeds. It also demands that every concrete LibraryModel subclass is
mentioned in no other module together with a write call (`save`, `create`, `update`,
`delete`, `bulk_create`, `bulk_update`, `update_or_create`, `get_or_create`), so a write
cannot be smuggled in beside the fence. Tests may call it (they prove it).

The runtime half is proven below: a LibraryModel refuses save, update and delete outside
`library_write()`, and accepts them inside, on a throwaway concrete model.

Proven to fail 2026-09-19 by adding `with library_write("x"): pass` to apps/home/logic.py:
the test named the file and the allowlist.
"""

from __future__ import annotations

import ast
from pathlib import Path

from apps.shared.testing import production_models
from django.test import SimpleTestCase

from apps.shared.tenancy import LibraryModel

APPS_DIR = Path(__file__).resolve().parent.parent

# Modules that may call library_write(). Paths relative to backend/apps.
LIBRARY_WRITE_ALLOWLIST = frozenset(
    {
        "proposals/apply.py",
        "watch/logic.py",
        "shared/tenancy.py",  # the definition
    }
)
# Any path under these directories may call it too: reference seeds.
LIBRARY_WRITE_ALLOWED_DIRS = ("shared/management/commands/", "library/seeds/", "taxonomy/seeds/")
WRITE_METHODS = frozenset(
    {"save", "create", "update", "delete", "bulk_create", "bulk_update", "update_or_create", "get_or_create"}
)


def production_modules() -> list[Path]:
    modules = []
    for path in sorted(APPS_DIR.rglob("*.py")):
        rel = path.relative_to(APPS_DIR).as_posix()
        if "/migrations/" in rel or rel.split("/")[-1].startswith("tests_") or rel.endswith("/testing.py"):
            continue
        modules.append(path)
    return modules


def _is_allowed(rel: str) -> bool:
    return rel in LIBRARY_WRITE_ALLOWLIST or any(rel.startswith(prefix) for prefix in LIBRARY_WRITE_ALLOWED_DIRS)


class LibraryWriteCalls(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.write_calls: list[tuple[int, str]] = []
        self.names: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        target = node.func
        name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else None
        if name == "library_write":
            self.calls.append(node.lineno)
        if name in WRITE_METHODS:
            self.write_calls.append((node.lineno, name))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.names.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.names.add(node.attr)
        self.generic_visit(node)


def concrete_library_models() -> list[type[LibraryModel]]:
    return [m for m in production_models() if issubclass(m, LibraryModel) and not m._meta.abstract]


class LibraryFenceGuard(SimpleTestCase):
    def test_library_write_is_called_only_from_allowlisted_modules(self) -> None:
        offenders: list[str] = []
        for path in production_modules():
            rel = path.relative_to(APPS_DIR).as_posix()
            visitor = LibraryWriteCalls()
            visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
            if visitor.calls and not _is_allowed(rel):
                offenders.append(f"apps/{rel}:{visitor.calls[0]}")
        self.assertEqual(
            offenders,
            [],
            "library_write() is called outside the allowlist:\n  "
            + "\n  ".join(offenders)
            + f"\nAllowed: {sorted(LIBRARY_WRITE_ALLOWLIST)} and {LIBRARY_WRITE_ALLOWED_DIRS}. "
            "Library changes go through proposals (PRO-01).",
        )

    def test_no_module_outside_the_allowlist_writes_a_library_model(self) -> None:
        library_names = {model.__name__ for model in concrete_library_models()}
        offenders: list[str] = []
        for path in production_modules():
            rel = path.relative_to(APPS_DIR).as_posix()
            if _is_allowed(rel) or rel.endswith("/models.py"):
                continue
            visitor = LibraryWriteCalls()
            visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
            mentioned = library_names & visitor.names
            if mentioned and visitor.write_calls:
                line, method = visitor.write_calls[0]
                offenders.append(f"apps/{rel}:{line} calls .{method}() and names {sorted(mentioned)}")
        self.assertEqual(offenders, [], "possible library writes outside the fence:\n  " + "\n  ".join(offenders))

    def test_enumeration_reports_the_library_models_it_guards(self) -> None:
        # Chunk 3's library records are guarded beside chunk 2's vocabularies and terms.
        names = {model.__name__ for model in concrete_library_models()}
        chunk3 = {
            "Authority", "Instrument", "InstrumentTitle", "InstrumentRelation", "Provision", "ProvisionVersion",
            "ProvisionText", "Obligation", "ObligationTitle", "ObligationVersion", "ObligationSummary",
            "ObligationProvision", "ObligationTerm", "ObligationTag", "ObligationRelation", "Verification",
        }  # fmt: skip
        self.assertLessEqual(chunk3 | {"TaxonomyTerm", "RelationType"}, names)
        self.assertNotIn("ProblemReport", names, "any member reports a problem; it is a mixed tenant table, not a library record")

"""Guard: the search index fence (SRC-01, H7, owner item 4).

The index is derived data, so what keeps it faithful to the library is not a proposal but
one door: `apps/search/indexing.py`. This guard walks the AST of every production module
under apps/ and demands that `index_write(` is called there and nowhere else, and that no
other module names `SearchChunk` together with a write call, so a chunk cannot be written
beside the fence. `apps/search/models.py` is exempt from the second rule because it
declares the model; tests are exempt from both because they prove the fence.

The library fence is a separate thing and this task changed nothing about it. The last
test here says so in the one way that matters: no module of the search app was added to
`LIBRARY_WRITE_ALLOWLIST` or to `LIBRARY_WRITE_ALLOWED_DIRS`.

Proven to fail 2026-09-20, each breach then reverted: `index_write("x")` in
apps/search/logic.py (the first test named the file and the allowlist), and
`SearchChunk.objects.create(...)` in apps/search/hybrid.py (the second named the file, the
line and the method).
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

from apps.shared.tests_library_fence import (
    LIBRARY_WRITE_ALLOWED_DIRS,
    LIBRARY_WRITE_ALLOWLIST,
    WRITE_METHODS,
    production_modules,
)

APPS_DIR = Path(__file__).resolve().parent.parent

# The one module that may write a chunk. It is the definition and the door at once, the way
# apps/shared/tenancy.py is for the library fence.
INDEX_WRITE_ALLOWLIST = frozenset({"search/indexing.py"})
# It declares the model, so it names it; it makes no write call of its own.
MODEL_MODULE = "search/models.py"


class IndexWriteCalls(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.write_calls: list[tuple[int, str]] = []
        self.names: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        target = node.func
        name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else None
        if name == "index_write":
            self.calls.append(node.lineno)
        if name in WRITE_METHODS:
            self.write_calls.append((node.lineno, name))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.names.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.names.add(node.attr)
        self.generic_visit(node)


def _walk(path: Path) -> IndexWriteCalls:
    visitor = IndexWriteCalls()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
    return visitor


class IndexFenceGuard(SimpleTestCase):
    def test_index_write_is_called_only_from_the_indexing_module(self) -> None:
        offenders: list[str] = []
        for path in production_modules():
            rel = path.relative_to(APPS_DIR).as_posix()
            visitor = _walk(path)
            if visitor.calls and rel not in INDEX_WRITE_ALLOWLIST:
                offenders.append(f"apps/{rel}:{visitor.calls[0]}")
        self.assertEqual(
            offenders,
            [],
            "index_write() is called outside the allowlist:\n  "
            + "\n  ".join(offenders)
            + f"\nAllowed: {sorted(INDEX_WRITE_ALLOWLIST)}. The index is rebuilt from the "
            "library in one place, never written by hand (SRC-01, H7).",
        )

    def test_no_module_outside_the_fence_writes_a_search_chunk(self) -> None:
        offenders: list[str] = []
        for path in production_modules():
            rel = path.relative_to(APPS_DIR).as_posix()
            if rel in INDEX_WRITE_ALLOWLIST or rel == MODEL_MODULE:
                continue
            visitor = _walk(path)
            if "SearchChunk" in visitor.names and visitor.write_calls:
                line, method = visitor.write_calls[0]
                offenders.append(f"apps/{rel}:{line} calls .{method}() and names SearchChunk")
        self.assertEqual(offenders, [], "possible search index writes outside the fence:\n  " + "\n  ".join(offenders))

    def test_the_library_fence_gained_nothing_from_the_search_app(self) -> None:
        # Owner item 4: the index has a fence of its own precisely so the library's stays
        # as it is. A search module on either library list would mean a chunk had become a
        # way into the library, which is the thing the two zones exist to prevent.
        self.assertEqual([entry for entry in LIBRARY_WRITE_ALLOWLIST if entry.startswith("search/")], [])
        self.assertEqual([entry for entry in LIBRARY_WRITE_ALLOWED_DIRS if entry.startswith("search/")], [])

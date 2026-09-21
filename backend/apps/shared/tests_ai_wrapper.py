"""Guard: one door to a model, and one writer of the log (playbook 5, 16; AUD-02).

Two AST walks over every production module under apps/:

- **The adapter.** `apps/shared/adapters/llm.py` may be imported or called from
  `apps/shared/ai.py` alone. A second caller means a model call that writes no
  `ai_generation` row, which is exactly the invariant AUD-02 turns on, and it is the kind
  of thing that arrives quietly in a feature that "just needs a summary".
- **The log.** `AiGeneration` may be created from `apps/governance/ai_log.py` alone, so
  "every model output is logged, once, with its model and its review state" cannot be
  half-done by a module that writes its own row with the fields it happened to have.

The allowlists are the whole rule: a new caller is a code review question, not a formality.
Both walks over-approximate — a name counts whether or not it is called — so they fail
closed.

Proven to fail 2026-09-21, each breach then reverted: `from apps.shared.adapters import
llm` in apps/home/logic.py (the test named the file and the allowlist); `get_llm()` called
in apps/watch/so_what_draft.py; and `AiGeneration.objects.create(...)` in
apps/governance/logic.py (the test named the file and the one writer).
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

from apps.shared.tests_library_fence import production_modules

APPS_DIR = Path(__file__).resolve().parent.parent

# The one module that may reach the LLM adapter. Everything else asks it through
# `apps/shared/ai.py:generate()`, which logs the call.
LLM_CALLER_ALLOWLIST = frozenset({"shared/ai.py", "shared/adapters/llm.py"})
# The one module that may write the log row.
AI_LOG_WRITER_ALLOWLIST = frozenset({"governance/ai_log.py"})

ADAPTER_MODULE = "apps.shared.adapters.llm"
ADAPTER_FACTORY = "get_llm"
LOG_MODEL = "AiGeneration"
WRITE_METHODS = frozenset(
    {"create", "save", "update", "delete", "bulk_create", "bulk_update", "update_or_create", "get_or_create"}
)


class _AdapterUse(ast.NodeVisitor):
    """Lines that import the adapter module or call its factory."""

    def __init__(self) -> None:
        self.lines: list[int] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == ADAPTER_MODULE:
                self.lines.append(node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        names = {alias.name for alias in node.names}
        if module == ADAPTER_MODULE or (module == "apps.shared.adapters" and "llm" in names):
            self.lines.append(node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = node.func
        name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else None
        if name == ADAPTER_FACTORY:
            self.lines.append(node.lineno)
        self.generic_visit(node)


class _LogWrite(ast.NodeVisitor):
    """Lines that name the log model beside a write call."""

    def __init__(self) -> None:
        self.names_model = False
        self.writes: list[int] = []

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == LOG_MODEL:
            self.names_model = True
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == LOG_MODEL:
            self.names_model = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = node.func
        if isinstance(target, ast.Attribute) and target.attr in WRITE_METHODS:
            self.writes.append(node.lineno)
        self.generic_visit(node)


def _walk(visitor_type: type[ast.NodeVisitor], path: Path) -> ast.NodeVisitor:
    visitor = visitor_type()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
    return visitor


class AiWrapperFenceTests(SimpleTestCase):
    def test_only_the_wrapper_reaches_the_llm_adapter(self) -> None:
        """A model call that does not go through `shared/ai.py` writes no log row (AUD-02)."""
        offenders = []
        for path in production_modules():
            rel = path.relative_to(APPS_DIR).as_posix()
            if rel in LLM_CALLER_ALLOWLIST:
                continue
            use = _walk(_AdapterUse, path)
            for line in use.lines:  # type: ignore[attr-defined]
                offenders.append(f"{rel}:{line}")
        self.assertEqual(
            offenders,
            [],
            "Only apps/shared/ai.py may import or call the LLM adapter, because that is the "
            "one place a call is logged (AUD-02). Call `apps.shared.ai.generate()` from "
            f"{offenders}, or put the module on LLM_CALLER_ALLOWLIST with a reason.",
        )

    def test_only_the_log_module_writes_a_generation_row(self) -> None:
        """One writer, so a row can never be half-filled by a module of its own (AUD-02)."""
        offenders = []
        for path in production_modules():
            rel = path.relative_to(APPS_DIR).as_posix()
            if rel in AI_LOG_WRITER_ALLOWLIST or rel == "governance/models.py":
                continue
            write = _walk(_LogWrite, path)
            if write.names_model and write.writes:  # type: ignore[attr-defined]
                offenders.append(rel)
        self.assertEqual(
            offenders,
            [],
            "AiGeneration rows are written by apps/governance/ai_log.py:log_generation() "
            f"alone (AUD-02). Call it from {offenders} instead of writing the row there.",
        )

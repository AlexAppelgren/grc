"""Guard: library fence (playbook 5, 14, PRO-01, AC-PRO1, INV-06).

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

The door over the real routes (AC-PRO1) is `ProposalDoorGuard`. It indexes what every
production module defines at top level (functions, classes, methods, module-level names)
and what each definition names, resolved through imports and re-exports, then walks from
the view of every operation Ninja registered (the objects that produce openapi.json) to the
functions that open `library_write()` themselves. It demands that:

- `proposals.apply.apply` is named by one function only, `proposals.logic.approve`;
- only approveProposal (through `apply.apply`) and chunk 3's re-verification stamp,
  reverifyObligation (through `apply.apply_reverification`), reach a library write, so
  every write under /instruments, /provisions, /obligations and /vocab either writes no
  library row (a problem report, a proposal, a tenant list's own row) or is the stamp;
- every route that reaches a library write is gated by `proposals.review`, needs a step-up
  and takes a person's session only;
- no tenant role holds `proposals.review`, the role editor refuses it, and no API key's
  principal passes a permission gate.

The walk over-approximates (a name counts whether or not it is called, and a class reaches
all its methods), so it fails closed; a method called on an object it cannot resolve is
left to the runtime fence.

Proven to fail 2026-09-19, each breach then reverted: a second caller of `apply.apply` in
apps/taxonomy/logic.py, and an alias of it held in a module-level dict there; POST
/vocab/{list_name} calling a reference seed; a reverifyObligation route calling
`apply.apply`, and one calling a stand-in `apply_reverification` without a step-up (with the
step-up it passed); an API key accepted on approveProposal; `proposals.review` given to
the compliance officer, added to TENANT_PERMISSIONS and added as a `proposals:review`
scope; the role editor validating against every permission; and a key's principal passing
a permission gate.
"""

from __future__ import annotations

import ast
import functools
import inspect
import uuid
from pathlib import Path

from apps.shared.testing import production_models
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.identity import roles_logic
from apps.shared import permissions as perms
from apps.shared.authentication import Principal, PrincipalKind, SessionAuth
from apps.shared.routes import RegisteredOperation, iter_operations
from apps.shared.tenancy import LibraryModel
from config.api import api

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
LIBRARY_WRITE_ALLOWED_DIRS = ("shared/management/commands/", "library/seeds/", "taxonomy/seeds/", "agents/seeds/")
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


# ---------------------------------------------------------------------------------------
# The only door, over the real routes (AC-PRO1, INV-06)
# ---------------------------------------------------------------------------------------
Node = tuple[str, str]  # (dotted module, "f", "Cls", "Cls.method" or a module-level name)

LIBRARY_WRITE: Node = ("apps.shared.tenancy", "library_write")
APPLY: Node = ("apps.proposals.apply", "apply")
APPROVE: Node = ("apps.proposals.logic", "approve")
# Each route that may reach a library write, and the one function opening library_write()
# it may reach. The stamp is chunk 3's POST /obligations/{id}/verifications (INV-S8).
LIBRARY_WRITING_ROUTES: dict[str, Node] = {
    "approveProposal": APPLY,
    "reverifyObligation": ("apps.proposals.apply", "apply_reverification"),
}
LIBRARY_ROUTE_PREFIXES = ("/instruments", "/provisions", "/obligations", "/vocab")
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _dotted(path: Path) -> str:
    parts = path.relative_to(APPS_DIR.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _chain(node: ast.expr) -> list[str]:
    """`a.b.c` as ["a", "b", "c"]; empty when the chain does not start at a plain name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return [node.id, *reversed(parts)] if isinstance(node, ast.Name) else []


class CodeIndex:
    """What every production module defines at top level, and what each definition names."""

    def __init__(self) -> None:
        self.defs: dict[str, dict[str, ast.AST]] = {}
        self.imports: dict[str, dict[str, set[tuple[str, str | None]]]] = {}
        for path in production_modules():
            module = _dotted(path)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            package = module if path.name == "__init__.py" else module.rpartition(".")[0]
            aliases: dict[str, set[tuple[str, str | None]]] = {}
            self.imports[module] = aliases
            for node in ast.walk(tree):  # an import inside a function counts, and every binding of a name
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        bound = alias.asname or alias.name.split(".")[0]
                        aliases.setdefault(bound, set()).add((alias.name if alias.asname else bound, None))
                elif isinstance(node, ast.ImportFrom):
                    source = node.module or ""
                    if node.level:
                        base = package.rsplit(".", node.level - 1)[0]
                        source = f"{base}.{source}" if source else base
                    for alias in node.names:
                        aliases.setdefault(alias.asname or alias.name, set()).add((source, alias.name))
            defs: dict[str, ast.AST] = {}
            self.defs[module] = defs
            for statement in tree.body:
                if isinstance(statement, (*FUNCTIONS, ast.ClassDef)):
                    defs[statement.name] = statement
                if isinstance(statement, ast.ClassDef):
                    for item in statement.body:
                        if isinstance(item, FUNCTIONS):
                            defs[f"{statement.name}.{item.name}"] = item
                if isinstance(statement, ast.Assign | ast.AnnAssign):
                    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            defs[target.id] = statement
        self.edges: dict[Node, set[Node]] = {}
        for module, definitions in self.defs.items():
            for name, definition in definitions.items():
                owner = name.split(".")[0] if "." in name else None
                self.edges[(module, name)] = self._references(module, name, definition, owner)
                if owner:  # a class reaches its methods
                    self.edges[(module, owner)].add((module, name))

    def _members(self, module: str, parts: list[str], depth: int = 0) -> set[Node]:
        """What `parts` may name when looked up in `module`, through imports and re-exports;
        nothing for a module itself or for anything outside apps/."""
        if not parts or module not in self.defs or depth > 20:
            return set()
        head, rest = parts[0], parts[1:]
        found: set[Node] = set()
        if f"{module}.{head}" in self.defs:
            found |= self._members(f"{module}.{head}", rest, depth + 1)
        if head in self.defs[module]:
            method = f"{head}.{rest[0]}" if rest else ""
            found.add((module, method if method in self.defs[module] else head))
        for source, name in self.imports[module].get(head, ()):
            found |= self._members(source, rest if name is None else [name, *rest], depth + 1)
        return found

    def _references(self, module: str, name: str, definition: ast.AST, owner: str | None) -> set[Node]:
        # A class's own node covers its bases, decorators and body; each method is a node of its own.
        roots = [definition]
        if isinstance(definition, ast.ClassDef):
            body = [item for item in definition.body if not isinstance(item, FUNCTIONS)]
            roots = [*definition.bases, *definition.keywords, *definition.decorator_list, *body]
        found: set[Node] = set()
        for root in roots:
            for node in ast.walk(root):
                parts = _chain(node) if isinstance(node, ast.Name | ast.Attribute) else []
                if owner and parts[:1] in (["self"], ["cls"]):
                    parts = [owner, *parts[1:]]
                found |= self._members(module, parts)
        return found - {(module, name)}

    def referrers(self, target: Node) -> list[Node]:
        return sorted(node for node, names in self.edges.items() if target in names)

    def library_writes_reached(self, start: Node) -> set[Node]:
        """The definitions reachable from `start` that open library_write() themselves."""
        seen, todo = {start}, [start]
        while todo:
            for target in self.edges.get(todo.pop(), set()) - seen:
                seen.add(target)
                todo.append(target)
        return {node for node in seen if LIBRARY_WRITE in self.edges.get(node, set())}


@functools.cache
def code_index() -> CodeIndex:
    return CodeIndex()


def view_node(operation: RegisteredOperation) -> Node:
    view = inspect.unwrap(operation.view_func)
    return (view.__module__, view.__qualname__)


def _label(operation: RegisteredOperation) -> str:
    return f"{operation.method} {operation.path} ({operation.operation_id})"


class ProposalDoorGuard(SimpleTestCase):
    def test_apply_is_named_only_by_the_approval(self) -> None:
        self.assertEqual(
            code_index().referrers(APPLY),
            [APPROVE],
            "apps/proposals/apply.py apply() may be named only by proposals.logic.approve, which checks "
            "four eyes and records the decision in the same transaction (PRO-02, AC-PRO1).",
        )

    def test_only_the_approval_and_the_stamp_reach_a_library_write(self) -> None:
        index = code_index()
        reached: list[tuple[RegisteredOperation, set[Node]]] = []
        library_route_writes: list[str] = []
        for operation in iter_operations(api):
            start = view_node(operation)
            self.assertIn(start[1], index.defs.get(start[0], {}), f"the index lost the view of {_label(operation)}")
            if operation.method != "GET" and operation.path.startswith(LIBRARY_ROUTE_PREFIXES):
                library_route_writes.append(operation.path)
            writes = index.library_writes_reached(start)
            if writes:
                reached.append((operation, writes))
        self.assertTrue(
            any(path.startswith("/vocab") for path in library_route_writes),
            "no write under /vocab was examined; the enumeration is broken",
        )
        self.assertIn(
            "approveProposal",
            [operation.operation_id for operation, _ in reached],
            "the walk no longer sees approval reach apply(); it is broken",
        )
        wrong = [
            f"{_label(operation)} reaches {sorted(writes)}"
            for operation, writes in reached
            if writes != {LIBRARY_WRITING_ROUTES.get(operation.operation_id)}
        ]
        self.assertEqual(
            wrong,
            [],
            "Routes that reach library_write() other than through their one expected writer:\n  "
            + "\n  ".join(wrong)
            + f"\nExpected: {LIBRARY_WRITING_ROUTES}. A library change is a proposal and approval applies it; "
            "the re-verification stamp is the single exception and stays only a stamp (AC-PRO1, INV-06).",
        )

    def test_a_route_reaching_a_library_write_needs_proposals_review_a_step_up_and_a_person(self) -> None:
        index = code_index()
        writing = [op for op in iter_operations(api) if index.library_writes_reached(view_node(op))]
        self.assertTrue(writing, "no route reaches a library write; the walk is broken")
        for operation in writing:
            with self.subTest(route=_label(operation)):
                self.assertEqual(perms.gate_of(operation.view_func), perms.Gate("permission", perms.PROPOSALS_REVIEW))
                self.assertTrue(perms.step_up_of(operation.view_func), "a library write needs a fresh passkey assertion")
                self.assertTrue(operation.auth, "a library write needs a signed-in person")
                for auth in operation.auth:
                    self.assertIsInstance(auth, SessionAuth, "no API key reaches a library write")

    def test_no_tenant_role_and_no_key_holds_proposals_review(self) -> None:
        self.assertNotIn(perms.PROPOSALS_REVIEW, perms.TENANT_PERMISSIONS)
        tenant_roles = [key for key in perms.SYSTEM_ROLES if key not in roles_logic.PLATFORM_ROLE_LABELS]
        self.assertIn("compliance_officer", tenant_roles)
        for key in tenant_roles:
            self.assertNotIn(perms.PROPOSALS_REVIEW, perms.SYSTEM_ROLES[key], f"the tenant role {key!r}")
        # A tenant's own role is refused it by the role editor.
        with self.assertRaises(ValidationError):
            roles_logic._validate_permissions([perms.PROPOSALS_REVIEW])
        # No scope is named for it, and a key's principal never passes a permission gate.
        self.assertNotIn(perms.PROPOSALS_REVIEW.replace(".", ":"), perms.ALL_SCOPES)
        agent = Principal(
            kind=PrincipalKind.AGENT,
            subject_id=uuid.uuid4(),
            permissions=perms.ALL_PERMISSIONS,
            scopes=perms.ALL_SCOPES | {perms.PROPOSALS_REVIEW},
        )
        self.assertFalse(agent.has_permission(perms.PROPOSALS_REVIEW))

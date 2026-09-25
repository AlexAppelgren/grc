"""Guard: library fence (playbook 5, 14, PRO-01, AC-PRO1, INV-06).

Walks the AST of every production module under apps/ and demands that `library_write(`
is called only from the allowlisted modules: the proposal applier, the watch door and
the reference seeds. `apps/watch/write.py` is the only module under apps/watch/ on that
list (chunk 5, ruling H), and the second allowlist below restricts who may open that
door; the door's own runtime refusal — the seven watch tables and no inventory table —
is proven in apps/watch/tests_write.py. It also demands that every concrete LibraryModel subclass is
mentioned in no other module together with a write call (`save`, `create`, `update`,
`delete`, `bulk_create`, `bulk_update`, `update_or_create`, `get_or_create`), so a write
cannot be smuggled in beside the fence. Tests may call it (they prove it).

The runtime half is proven below: a LibraryModel refuses save, update and delete outside
`library_write()`, and accepts them inside, on a throwaway concrete model.

Proven to fail 2026-09-19 by adding `with library_write("x"): pass` to apps/home/logic.py:
the test named the file and the allowlist.

The watch half proven to fail 2026-09-20, each breach then reverted: `library_write()` in
apps/watch/schemas.py (named the file and the allowlist); `watch/reading.py` added to
`LIBRARY_WRITE_ALLOWLIST` (named the second watch module); `watch_write()` in
apps/watch/api.py (named the file and the four steps that may open the door).

The door over the real routes (AC-PRO1) is `ProposalDoorGuard`. It indexes what every
production module defines at top level (functions, classes, methods, module-level names)
and what each definition names, resolved through imports and re-exports, then walks from
the view of every operation Ninja registered (the objects that produce openapi.json) to the
functions that open `library_write()` themselves. It demands that:

- `proposals.apply.apply` is named by one function only, `proposals.logic.approve`;
- every route reaches the one writer its map allows and no other: approveProposal reaches
  `apply.apply` and chunk 3's re-verification stamp, reverifyObligation, reaches
  `apply.apply_reverification` (`LIBRARY_WRITING_ROUTES`), while the watch routes reach
  `watch.write.watch_write` (`WATCH_WRITING_ROUTES`). A route in neither map that reaches
  any writer at all fails, and so does a watch route that reaches `apply`,
  `apply_reverification` or anything else that opens `library_write()`. So every write
  under /instruments, /provisions, /obligations and /vocab either writes no library row (a
  problem report, a proposal, a tenant list's own row) or is the stamp;
- every route that reaches a library write is gated by `proposals.review`, needs a step-up
  and takes a person's session only — except the watch routes, which are gated instead as
  the next paragraph says, and approveProposal, whose body gate `require_reviewer` admits a
  reviewing agent's key beside a person and whose body calls `enforce_step_up` for the
  person (PRO-S13, D-62);
- no tenant role holds `proposals.review`, the role editor refuses it, and no API key's
  principal passes a permission gate.

**The obligations inventory and the watch tables are not the same thing (D-64).** The
invariant is that a proposal approved by a second, independent principal is the only door
into the *inventory* — instruments, obligations, provisions and their versions — with the
re-verification stamp the single exception. A change is a sighting, not an inventory
record: an agent's key registers one and curates the facts it carries (WAT-02, WAT-03),
which is what the PRD has agents do and what `watch_write()` was built for. The source
registry and its coverage log are the same kind of fact — where we looked and how it went
(WAT-01) — and are a library editor's to keep. Both sit in the library zone, which is why
a guard reading "library zone" could not tell them apart. It can now. A route in
`WATCH_WRITING_ROUTES` is exempt from the `proposals.review`-and-step-up assertion, and in
its place must reach `watch_write` and nothing else and carry exactly the one gate
`WATCH_ROUTE_GATES` names for it:

- `require_change_writer` in the route body, which takes an agent's key with
  `changes:write` or a library editor's session with `proposals.review` (PRO-01);
- `@requires_scope` on a route only a key reaches: the document a run fetched, and the
  line of the coverage log saying where it looked;
- `@requires_permission` on a route only a person reaches: the source registry, which is
  `sources.manage` and no step-up, because deciding where to look is not deciding what the
  law says.

Neither claim is asserted in a comment. The permission and scope constants
`require_change_writer` itself names are read out of the index below; every scope and every
permission a watch route's gate names is checked against the table of every library model
that sits behind the proposal door, and the permission is checked to be a platform one no
tenant role holds and no key's principal can pass. Nothing is widened — the four-eyes rule
on the inventory, the AST allowlists above and the door's own runtime refusal are
untouched, and a watch route reaching an inventory writer still fails.

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

The door each writer names to the database (H16, ADR 0058) is `EachWriterNamesItsOwnDoor`:
the word a writer hands the trigger of shared 0008 decides which tables it reaches there, so
`proposal`, `reverification`, `watch` and `index` are each named by one function and no
other, and `seed`, the widest door and `library_write()`'s default, is opened, by name or by
default, only from the reference seeds' directories. Proven to fail 2026-09-23, each breach
then reverted: `door="proposal"` in `watch_write()` (the watch door named by the wrong
function), and the stamp's `door="reverification"` removed (the door named by nobody).
Proven to fail 2026-09-24, then reverted: a `library_write("a repoint helper")` naming no
door planted in apps/watch/write.py, which the database would have let reach every
inventory table (red, naming `watch/write.py::_plant`).

Platform configuration (D-102, ADR 0059) is `PlatformConfigurationGuard`: agent
definitions, agent versions and the platform agent settings they carry are named once in
`PLATFORM_CONFIGURATION`, reached by three console routes alone, each through one writer of
`agents/seeds/console.py`, behind `agent_definitions.manage`, a step-up and a person's
session. Every other model, route, proposal kind and watch module is judged as before.

The step-up edge proven to fail 2026-09-23, then reverted: approveProposal with its
`enforce_step_up` call and import removed (red here, naming the missing edge, and red in
apps/proposals/tests_decide.py, where a person's approval without an assertion and one
with a stale assertion both applied).

The second door proven to fail 2026-09-21 (H18), each breach then reverted. Against the
rule as it stood before — one map, and no gate rule for a watch route — the two tests at
the end of this file are both red; so is the first of them against the naive shape of H18,
where a watch route is exempted from the writer rule instead of held to one writer. Over
the real routes, with `watch_write()` planted in the four steps of watch/curation.py (the
state `c5-watch-curation` brings): green, then red on `apply()` planted beside that
watch write in `curation.update_change_facts` (three assertions at once), and red again on
`require_change_writer` removed from the updateChange route.

The curation confirmation's gate proven to fail 2026-09-23 (`watch-curation-confirm-backend`,
D-74), each breach then reverted: confirmChangeCuration gated by `require_change_writer`
instead of `require_curation_confirmer`, which would let the scope that files a suggestion
confirm one (red, the route named with the gate it carried); and `require_curation_confirmer`
with its `enforce_step_up` call removed (red here, naming the missing edge, and red in
apps/watch/tests_curation.py, where a person without a fresh assertion was no longer refused).

The registry's own gate proven to fail 2026-09-21 (`c5-watch-sources-coverage`), each
breach then reverted, because its three routes are the first watch routes whose gate is not
`require_change_writer`: `@requires_permission` removed from createSource (red, the route
named with the gate it should have carried); createSource gated by the `sources:write`
scope instead, so a key could have registered a source (red); `apply()` planted beside the
registry write in `sources.create_source` (red, three assertions at once); createSource and
its map entry both moved to `watch.read`, a permission every bank's member holds (red
twice — the map's own negative cases, and the platform-permission rule); and createSource
removed from WATCH_WRITING_ROUTES while still opening the door (red three times — an
unmapped writer, the two maps out of step, and the route judged as an inventory write
without `proposals.review` or a step-up).
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
from apps.shared.authentication import ApiKeyAuth, Principal, PrincipalKind, SessionAuth
from apps.shared.routes import RegisteredOperation, iter_operations
from apps.shared.tenancy import LibraryModel, library_write
from config.api import api

APPS_DIR = Path(__file__).resolve().parent.parent

# Modules that may call library_write(). Paths relative to backend/apps.
LIBRARY_WRITE_ALLOWLIST = frozenset(
    {
        "proposals/apply.py",
        "watch/write.py",  # the watch door, and the only module under apps/watch/ (ruling H)
        "shared/tenancy.py",  # the definition
    }
)
# The watch door reaches the seven watch tables and no inventory table (apps/watch/write.py).
# These four modules may open it; nothing else under apps/watch/ may write a library row.
WATCH_WRITE_ALLOWLIST = frozenset(
    {
        "watch/write.py",  # the definition
        "watch/registration.py",
        "watch/curation.py",
        "watch/sources.py",
        "watch/so_what_draft.py",
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
        self.watch_calls: list[int] = []
        self.write_calls: list[tuple[int, str]] = []
        self.names: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        target = node.func
        name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else None
        if name == "library_write":
            self.calls.append(node.lineno)
        if name == "watch_write":
            self.watch_calls.append(node.lineno)
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

    def test_only_the_watch_door_may_write_the_library_from_a_watch_module(self) -> None:
        # Ruling H: `watch/logic.py` came off this list and `watch/write.py` took its place,
        # so no module under apps/watch/ can reach an inventory table through library_write().
        watch_modules = sorted(path for path in LIBRARY_WRITE_ALLOWLIST if path.startswith("watch/"))
        self.assertEqual(watch_modules, ["watch/write.py"])
        self.assertFalse(any(prefix.startswith("watch/") for prefix in LIBRARY_WRITE_ALLOWED_DIRS))

    def test_watch_write_is_called_only_from_the_modules_that_own_a_watch_step(self) -> None:
        offenders: list[str] = []
        for path in production_modules():
            rel = path.relative_to(APPS_DIR).as_posix()
            visitor = LibraryWriteCalls()
            visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
            if visitor.watch_calls and rel not in WATCH_WRITE_ALLOWLIST:
                offenders.append(f"apps/{rel}:{visitor.watch_calls[0]}")
        self.assertEqual(
            offenders,
            [],
            "watch_write() is called outside the allowlist:\n  "
            + "\n  ".join(offenders)
            + f"\nAllowed: {sorted(WATCH_WRITE_ALLOWLIST)}. The watch door is opened by the watch "
            "pipeline's own steps only (chunk 5 plan rule 8).",
        )

    def test_the_watch_door_reaches_no_inventory_table_and_no_key_scope_names_one(self) -> None:
        from apps.watch.write import WATCH_TABLES

        inventory = {"authority", "instrument", "provision", "obligation", "provision_version", "obligation_version"}
        self.assertEqual(WATCH_TABLES & inventory, set(), "the watch door must not reach the inventory")
        resources = {scope.split(":")[0] for scope in perms.ALL_SCOPES}
        self.assertEqual(
            resources & {"instruments", "provisions", "obligations"},
            set(),
            "no API key scope names an inventory table, so no watch path reaches one (AC-PRO1)",
        )


# ---------------------------------------------------------------------------------------
# The door each writer names to the database (H16, ADR 0058)
# ---------------------------------------------------------------------------------------
# The trigger of shared 0008 opens each library-zone table to the doors it names, so the
# word a writer hands the database is what decides which tables it reaches there. `seed` is
# library_write()'s default and the widest door (every inventory table, the stamped tables
# and the reference rows), so only the reference seeds' own directories may open it, whether
# a call names it or takes it by default; every other door is named by the functions below,
# and by no other. A watch step that named `proposal` would reach the inventory in the database,
# and a stamp, or a watch door, that lost its door would fall back to `seed` and reach every
# inventory table: each fails here. `library_door()` itself is kept to its homes by the
# compliance lint's `library-door` rule.
DOOR_NAMERS: dict[str, frozenset[str]] = {
    "proposal": frozenset({"proposals/apply.py::apply"}),
    "reverification": frozenset({"proposals/apply.py::apply_reverification"}),
    # The watch door, and the re-point a merge approval makes of a watch row inside the
    # proposal door (VOC-02), which reaches the watch tables through this door alone.
    "watch": frozenset({"watch/write.py::watch_write", "watch/write.py::repoint"}),
    "index": frozenset({"search/indexing.py::index_write"}),
    "eval": frozenset({"search/eval_sets.py::create_question", "search/eval_sets.py::record_run"}),
}
# The one call that passes a door it was handed rather than one it names.
DOOR_PASSED_ON = "shared/tenancy.py::library_write"
# What a `library_write()` that names no door opens, read from its signature so the pin
# follows the code.
DEFAULT_DOOR: str = inspect.signature(library_write).parameters["door"].default


def named_doors() -> dict[str, set[str]]:
    """Every door a production call names, by `library_write(..., door=...)` or
    `library_door(...)`, and the top-level function (or `<module>`) that names it. A
    `library_write()` that names none is listed under the door it takes by default, and a
    door that is not a string literal as `<passed on>`."""
    found: dict[str, set[str]] = {}
    for path in production_modules():
        rel = path.relative_to(APPS_DIR).as_posix()
        for top in ast.parse(path.read_text(encoding="utf-8")).body:
            scope = top.name if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else "<module>"
            for node in ast.walk(top):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
                door = next((keyword.value for keyword in node.keywords if keyword.arg == "door"), None)
                if called not in {"library_write", "library_door"}:
                    continue
                if called == "library_door" and door is None and node.args:
                    door = node.args[0]
                if door is None:
                    name = DEFAULT_DOOR if called == "library_write" else "<passed on>"
                else:
                    name = door.value if isinstance(door, ast.Constant) and isinstance(door.value, str) else "<passed on>"
                found.setdefault(name, set()).add(f"{rel}::{scope}")
    return found


class EachWriterNamesItsOwnDoor(SimpleTestCase):
    def test_each_door_is_named_by_its_one_writer_and_by_no_other(self) -> None:
        found = named_doors()
        for door, namers in DOOR_NAMERS.items():
            with self.subTest(door=door):
                self.assertEqual(found.get(door, set()), set(namers), f"the {door} door is named by the wrong functions")
        self.assertEqual(found.get("<passed on>", set()), {DOOR_PASSED_ON}, "a door passed on from a variable outside library_write()")
        self.assertEqual(set(found) - set(DOOR_NAMERS) - {"seed", "<passed on>"}, set(), "a door the database does not know")

    def test_the_seed_door_named_or_taken_by_default_is_opened_by_the_reference_seeds_alone(self) -> None:
        self.assertEqual(DEFAULT_DOOR, "seed")
        seeders = named_doors().get("seed", set())
        self.assertNotEqual(seeders, set(), "the pin sees no reference seed at all")
        outside = sorted(
            namer for namer in seeders if not any(namer.startswith(prefix) for prefix in LIBRARY_WRITE_ALLOWED_DIRS)
        )
        self.assertEqual(
            outside,
            [],
            "library_write() opens the seed door (every inventory table, in the database) outside the reference "
            f"seeds {LIBRARY_WRITE_ALLOWED_DIRS}; name the writer's own door instead",
        )


# ---------------------------------------------------------------------------------------
# The only door, over the real routes (AC-PRO1, INV-06)
# ---------------------------------------------------------------------------------------
Node = tuple[str, str]  # (dotted module, "f", "Cls", "Cls.method" or a module-level name)

LIBRARY_WRITE: Node = ("apps.shared.tenancy", "library_write")
APPLY: Node = ("apps.proposals.apply", "apply")
APPLY_REVERIFICATION: Node = ("apps.proposals.apply", "apply_reverification")
APPROVE: Node = ("apps.proposals.logic", "approve")
WATCH_WRITE: Node = ("apps.watch.write", "watch_write")
CHANGE_WRITER: Node = ("apps.watch.api", "require_change_writer")
# The body-level gate on confirming a change's curated facts (D-74): an agent-bound platform
# key holding `proposals:review`, or a person holding `proposals.review` who steps up.
CURATION_CONFIRMER: Node = ("apps.watch.api", "require_curation_confirmer")
# The body-level gate `approveProposal` carries instead of a decorator (PRO-S13, D-62, ADR
# 0054): `Principal.has_permission` and `has_scope` are kind-exclusive, so no single
# decorator can express "a session holding the permission or a key holding the scope", and
# this function is the door's own word on who may pass either way.
REQUIRE_REVIEWER: Node = ("apps.proposals.api", "require_reviewer")
# The step-up a person's approval demands, called in the route body for the same reason:
# `@requires_step_up` would refuse a key, which holds no assertion to give. The runtime half
# (no assertion, and one older than STEP_UP_FRESHNESS_MINUTES, each refused with nothing
# applied) is apps/proposals/tests_decide.py.
ENFORCE_STEP_UP: Node = ("apps.shared.permissions", "enforce_step_up")
# Each route that may reach a library write, and the one function opening library_write()
# it may reach. The stamp is chunk 3's POST /obligations/{id}/verifications (INV-S8).
LIBRARY_WRITING_ROUTES: dict[str, Node] = {
    "approveProposal": APPLY,
    "reverifyObligation": APPLY_REVERIFICATION,
}
# The watch door's routes (D-64, ruling H): an agent's key registers a change it sighted
# and curates the facts that change carries (WAT-02, WAT-03, AGT-07), and the source
# registry and its coverage log record where we looked and how it went (WAT-01). Each may
# reach `watch_write` and no other writer, and none of them reaches an inventory table —
# which is what the second half of the rule, the gate each one carries, keeps true. A "So
# what?" draft route that opens the same door later belongs here too, and fails this guard
# until somebody puts it here on purpose with its own gate looked at.
WATCH_WRITING_ROUTES: dict[str, Node] = {
    "createChange": WATCH_WRITE,
    "addChangeDocument": WATCH_WRITE,
    "updateChange": WATCH_WRITE,
    "addChangeEvent": WATCH_WRITE,
    "updateChangeEvent": WATCH_WRITE,
    "replaceChangeObligations": WATCH_WRITE,
    "createSource": WATCH_WRITE,
    "updateSource": WATCH_WRITE,
    "recordSourceCheck": WATCH_WRITE,
    "confirmChangeCuration": WATCH_WRITE,
}
# The one gate each of those routes may carry, named here rather than assumed, because a
# key never steps up and so a route's gate is the whole gate for a key. Four shapes, four
# different judgements, and each is checked against the route's real decorator below:
#
# - `CHANGE_WRITER` is the logic gate in the route body (`watch/api.py`), which takes an
#   agent's key with `changes:write` or a library editor's session with `proposals.review`.
#   A change's facts are written by both and by nobody else (PRO-01).
# - A `Gate("scope", ...)` is a decorator only a key passes: a fetched page and a line of
#   the coverage log arrive from the run that fetched and checked, never from a screen.
# - A `Gate("permission", ...)` is a decorator only a person passes. The source registry is
#   a library editor's under `sources.manage`, with no step-up, because deciding where to
#   look is not deciding what the law says; the assertions below pin that the permission is
#   a platform one no bank's role holds, and that neither it nor any scope here names a
#   table behind the proposal door.
# - `CURATION_CONFIRMER` is the logic gate on confirming a change's curated facts (D-74): a
#   second, independent agent's key holding the platform-only `proposals:review`, or a
#   person holding `proposals.review` who must step up. What it names is checked below.
WATCH_ROUTE_GATES: dict[str, perms.Gate | Node] = {
    "createChange": CHANGE_WRITER,
    "addChangeDocument": perms.Gate("scope", perms.SCOPE_CHANGES_WRITE),
    "updateChange": CHANGE_WRITER,
    "addChangeEvent": CHANGE_WRITER,
    "updateChangeEvent": CHANGE_WRITER,
    "replaceChangeObligations": CHANGE_WRITER,
    "createSource": perms.Gate("permission", perms.SOURCES_MANAGE),
    "updateSource": perms.Gate("permission", perms.SOURCES_MANAGE),
    "recordSourceCheck": perms.Gate("scope", perms.SCOPE_SOURCES_WRITE),
    "confirmChangeCuration": CURATION_CONFIRMER,
}
# Platform configuration (Alex, 2026-09-25, D-102, ADR 0059). An agent definition, the
# versions it publishes and the settings bleqq runs it with are the platform's own
# configuration, not sourced facts about the law: none of them enters the inventory, so no
# proposal carries them and four eyes over the inventory does not reach them. They keep the
# fence's machinery (a write outside `library_write()` is refused in Python and in the
# database), and their door is three console routes, each writing through one function of
# `agents/seeds/console.py` behind the platform permission `agent_definitions.manage`, a
# fresh passkey step-up and a person's session (`PlatformConfigurationGuard` below). Named
# here once, by model; everything else — another model, another route, a proposal kind, a
# watch module — is judged as the library and fails closed.
PLATFORM_CONFIGURATION: dict[str, str] = {
    "Agent": "agent definitions, and the platform agent settings each one carries",
    "AgentVersion": "agent versions",
}
AGENT_CONSOLE = "apps.agents.seeds.console"
PLATFORM_CONFIGURATION_ROUTES: dict[str, Node] = {
    "publishAgentVersion": (AGENT_CONSOLE, "publish"),
    "retireAgentVersion": (AGENT_CONSOLE, "retire"),
    "updatePlatformAgentSettings": (AGENT_CONSOLE, "set_platform_settings"),
}
PLATFORM_CONFIGURATION_GATE = perms.Gate("permission", perms.AGENT_DEFINITIONS_MANAGE)
LIBRARY_ROUTE_PREFIXES = ("/instruments", "/provisions", "/obligations", "/vocab")
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def unexpected_writer(operation_id: str, writes: set[Node]) -> str | None:
    """Why this route's writers are wrong, or None. A route may reach the one writer its
    map allows it and nothing else; a route in neither map may reach none at all. A map
    says 'may', not 'must', so a route that reaches nothing yet is no complaint."""
    allowed = (
        LIBRARY_WRITING_ROUTES.get(operation_id)
        or WATCH_WRITING_ROUTES.get(operation_id)
        or PLATFORM_CONFIGURATION_ROUTES.get(operation_id)
    )
    if not writes or writes == {allowed}:
        return None
    return f"reaches {sorted(writes)}, but may reach {allowed}"


def wrong_watch_gate(operation_id: str, gate: perms.Gate | None, named: set[Node]) -> str | None:
    """Why this watch route may not open the watch door, or None. `named` is what the
    route's view names, where a body gate shows.

    Each route carries exactly the gate `WATCH_ROUTE_GATES` names for it and no other, so a
    route cannot be moved from one judgement to another — a source registered by a key, a
    coverage line written by a bank's member, a change's facts settled behind `watch.read`,
    a confirmation given behind the scope that files the suggestion — without this map
    being edited on purpose. A route with no entry at all is refused, which is what stops a
    new watch route reaching `watch_write()` ungated.
    """
    wanted = WATCH_ROUTE_GATES.get(operation_id)
    if wanted is None:
        return "is in WATCH_WRITING_ROUTES with no entry in WATCH_ROUTE_GATES; name the one gate it carries"
    if isinstance(wanted, tuple):
        body_gates = {node for node in WATCH_ROUTE_GATES.values() if isinstance(node, tuple)}
        if wanted in named and not (named & body_gates) - {wanted}:
            return None
        return f"is gated by {gate} and {sorted(named & body_gates)}, not by {wanted[1]} alone in the route body"
    if gate == wanted:
        return None
    return f"is gated by {gate}, not by the {wanted} that WATCH_ROUTE_GATES names for it"


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

    def test_only_the_approval_the_stamp_and_the_watch_door_reach_a_library_write(self) -> None:
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
            f"{_label(operation)} {complaint}"
            for operation, writes in reached
            if (complaint := unexpected_writer(operation.operation_id, writes))
        ]
        self.assertEqual(
            wrong,
            [],
            "Routes that reach library_write() other than through their one expected writer:\n  "
            + "\n  ".join(wrong)
            + f"\nExpected: {LIBRARY_WRITING_ROUTES}, {WATCH_WRITING_ROUTES} and {PLATFORM_CONFIGURATION_ROUTES}. "
            "An inventory change is a "
            "proposal and approval applies it; the re-verification stamp is the single exception and stays "
            "only a stamp; a watch route registers a sighting through the watch door and reaches nothing "
            "else (AC-PRO1, INV-06, D-64).",
        )

    def test_a_route_reaching_a_library_write_needs_proposals_review_a_step_up_and_a_person(self) -> None:
        """Amended for PRO-S13, PRO-S14 and ID-S31 (D-62, ADR 0054), strengthened rather
        than dropped: `approveProposal` is the one route the second, independent principal
        may now be an agent for, so its gate is `require_reviewer()` in the route body, not
        a decorator, and it accepts a key beside a session. A person's fresh step-up is
        `enforce_step_up()` in the same body rather than `@requires_step_up`, which would
        refuse the key; the index proves the route names it, and apps/proposals/tests_decide.py
        proves a missing or stale assertion applies nothing. Every other route that reaches
        a library write is exactly as before: `proposals.review`, a fresh step-up and a
        person's session alone."""
        index = code_index()
        # The watch routes are the exception the guard now knows (D-64): they write a sighting,
        # not the inventory, and are gated instead by the two tests below. The platform
        # configuration routes write no library row at all (D-102) and are gated by
        # `PlatformConfigurationGuard`.
        writing = [
            op
            for op in iter_operations(api)
            if index.library_writes_reached(view_node(op))
            and op.operation_id not in WATCH_WRITING_ROUTES
            and op.operation_id not in PLATFORM_CONFIGURATION_ROUTES
        ]
        self.assertTrue(writing, "no route reaches a library write; the walk is broken")
        for operation in writing:
            with self.subTest(route=_label(operation)):
                node = view_node(operation)
                if operation.operation_id == "approveProposal":
                    self.assertIsNone(
                        perms.gate_of(operation.view_func),
                        "approveProposal takes no single decorator gate: require_reviewer() decides per principal",
                    )
                    self.assertIn(
                        REQUIRE_REVIEWER,
                        index.edges[node],
                        "approveProposal must call require_reviewer(), the one function admitting a session or a reviewing key",
                    )
                    self.assertIn(
                        ENFORCE_STEP_UP,
                        index.edges[node],
                        "approveProposal must call enforce_step_up() for a person: a library write needs a fresh passkey assertion",
                    )
                    self.assertEqual(
                        {type(auth) for auth in operation.auth},
                        {SessionAuth, ApiKeyAuth},
                        "approveProposal accepts a session and a key, and nothing else",
                    )
                else:
                    self.assertEqual(perms.gate_of(operation.view_func), perms.Gate("permission", perms.PROPOSALS_REVIEW))
                    self.assertTrue(perms.step_up_of(operation.view_func), "a library write needs a fresh passkey assertion")
                    self.assertTrue(operation.auth, "a library write needs a signed-in person")
                    for auth in operation.auth:
                        self.assertIsInstance(auth, SessionAuth, "no API key reaches a library write")

    def test_a_reviewing_key_needs_the_scope_and_never_a_tenant_role_or_key(self) -> None:
        """The claims `require_reviewer()` rests on, checked rather than described: it names
        the platform-only scope for a key and the unchanged permission for a person, and
        neither is ever handed to a tenant role or, for the permission, to a key's
        principal at all (PRO-S13, ID-S31, D-62, ADR 0054)."""
        index = code_index()
        named = {
            name
            for module, name in index.edges[REQUIRE_REVIEWER]
            if module == "apps.shared.permissions" and name.isupper()
        }
        self.assertEqual(
            {"SCOPE_PROPOSALS_REVIEW", "PROPOSALS_REVIEW"} & named,
            {"SCOPE_PROPOSALS_REVIEW", "PROPOSALS_REVIEW"},
            "require_reviewer must name the scope for a key and the permission for a person",
        )
        self.assertIn(perms.SCOPE_PROPOSALS_REVIEW, perms.PLATFORM_ONLY_SCOPES, "the review scope is platform-only, like the permission")
        tenant_roles = [key for key in perms.SYSTEM_ROLES if key not in roles_logic.PLATFORM_ROLE_LABELS]
        for key in tenant_roles:
            self.assertNotIn(perms.PROPOSALS_REVIEW, perms.SYSTEM_ROLES[key], f"the tenant role {key!r}")
        with self.assertRaises(ValidationError):
            roles_logic._validate_permissions([perms.PROPOSALS_REVIEW])
        # A key's principal never passes a permission gate, whatever tenant it carries or
        # scope it lists: the scope check inside require_reviewer is the whole of its gate.
        agent = Principal(
            kind=PrincipalKind.AGENT,
            subject_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            scopes=perms.ALL_SCOPES | {perms.PROPOSALS_REVIEW},
        )
        self.assertFalse(agent.has_permission(perms.PROPOSALS_REVIEW))

    def test_a_watch_route_is_gated_as_its_map_says_and_reaches_nothing_but_the_watch_door(self) -> None:
        index = code_index()
        operations = {operation.operation_id: operation for operation in iter_operations(api)}
        self.assertEqual(
            sorted(set(WATCH_WRITING_ROUTES) - set(operations)),
            [],
            "WATCH_WRITING_ROUTES names a route nobody registered; correct the map or the route.",
        )
        self.assertEqual(
            sorted(set(WATCH_WRITING_ROUTES) & set(LIBRARY_WRITING_ROUTES)),
            [],
            "a route belongs to one door or the other, never both.",
        )
        self.assertEqual(
            sorted(set(WATCH_WRITING_ROUTES) ^ set(WATCH_ROUTE_GATES)),
            [],
            "every route that may open the watch door names the one gate it carries, and nothing "
            "names a gate for a route that may not open it.",
        )
        for operation_id, writer in WATCH_WRITING_ROUTES.items():
            operation = operations[operation_id]
            with self.subTest(route=_label(operation)):
                node = view_node(operation)
                self.assertIn(node, index.edges, f"the index lost the view of {_label(operation)}")
                self.assertEqual(
                    node[0],
                    "apps.watch.api",
                    "only a route of the watch app belongs in WATCH_WRITING_ROUTES; moving an inventory "
                    "route here would exempt it from four eyes, which is the one thing this map may not do.",
                )
                complaint = wrong_watch_gate(operation_id, perms.gate_of(operation.view_func), set(index.edges[node]))
                self.assertIsNone(
                    complaint,
                    f"{_label(operation)} {complaint}. A watch route takes no step-up, so the scope or the "
                    "permission its map names is the whole gate (WAT-01, WAT-02, WAT-03, D-64).",
                )
                self.assertEqual(
                    index.library_writes_reached(node) - {writer},
                    set(),
                    "a watch route reaches the watch door and no other writer: not apply, not "
                    "apply_reverification, not a reference seed. Those stay behind four eyes (AC-PRO1).",
                )

    def test_a_watch_route_gated_by_a_permission_takes_one_no_bank_holds(self) -> None:
        """The source registry is the one watch write a person makes and a key never does
        (WAT-01), so the claim it rests on is checked rather than described: `sources.manage`
        is a platform permission, no tenant role carries it, a tenant's own role editor
        refuses it, and no API key's principal passes a permission gate at all. Without this,
        moving a registry route behind a tenant permission would let one bank's member write
        a row every bank reads."""
        named = {gate.value for gate in WATCH_ROUTE_GATES.values() if isinstance(gate, perms.Gate) and gate.kind == "permission"}
        self.assertEqual(named, {perms.SOURCES_MANAGE}, "the registry is the one permission-gated watch write")
        tenant_roles = [key for key in perms.SYSTEM_ROLES if key not in roles_logic.PLATFORM_ROLE_LABELS]
        for permission in named:
            self.assertIn(permission, perms.PLATFORM_PERMISSIONS)
            self.assertNotIn(permission, perms.TENANT_PERMISSIONS)
            for key in tenant_roles:
                self.assertNotIn(permission, perms.SYSTEM_ROLES[key], f"the tenant role {key!r}")
            with self.assertRaises(ValidationError):
                roles_logic._validate_permissions([permission])
            self.assertNotIn(permission.replace(".", ":"), perms.ALL_SCOPES)

    def test_the_scope_a_watch_route_demands_names_no_inventory_table(self) -> None:
        """The claim the exemption rests on, proven against the definitions themselves: the
        constants `require_change_writer` names, the scope each watch route's own decorator
        names, and the table of every library model that sits behind the proposal door."""
        from apps.watch.write import WATCH_TABLES

        named = {
            name
            for module, name in code_index().edges[CHANGE_WRITER]
            if module == "apps.shared.permissions" and name.isupper()
        }
        self.assertEqual(
            named,
            {"SCOPE_CHANGES_WRITE", "PROPOSALS_REVIEW"},
            "require_change_writer must name one scope for a key and the library editor's own permission "
            "for a person, and nothing else (no tenant role holds proposals.review).",
        )
        named |= self.constants_named_by(CURATION_CONFIRMER)
        scopes = {getattr(perms, name) for name in named} & perms.ALL_SCOPES
        for operation in iter_operations(api):
            gate = perms.gate_of(operation.view_func)
            if operation.operation_id in WATCH_WRITING_ROUTES and gate and gate.kind == "scope":
                scopes.add(gate.value)
        self.assertEqual(
            scopes,
            {perms.SCOPE_CHANGES_WRITE, perms.SCOPE_SOURCES_WRITE, perms.SCOPE_PROPOSALS_REVIEW},
            "a key reaches the watch door with three scopes and no others: the change facts it sighted, "
            "the line of the coverage log saying where it looked, and an independent agent's "
            "confirmation of another agent's facts (WAT-01, WAT-02, WAT-03, D-74).",
        )
        behind_the_proposal_door = {model._meta.db_table for model in concrete_library_models()} - WATCH_TABLES
        self.assertIn("obligation", behind_the_proposal_door, "the inventory was not enumerated; the check is empty")
        self.assertIn("source", WATCH_TABLES, "the registry is a watch table, so sources:write reaches no further")
        for scope in scopes:
            resource = scope.split(":")[0].replace("-", "_")
            self.assertEqual(
                {resource, resource.removesuffix("s")} & behind_the_proposal_door,
                set(),
                f"the scope {scope!r} names a table behind the proposal door; no key scope may (AC-PRO1).",
            )

    @staticmethod
    def constants_named_by(gate: Node) -> set[str]:
        """The permission and scope constants a body gate names, read out of the index."""
        return {name for module, name in code_index().edges[gate] if module == "apps.shared.permissions" and name.isupper()}

    def test_a_curation_confirmation_needs_the_review_scope_or_a_person_who_steps_up(self) -> None:
        """The claims `require_curation_confirmer()` rests on, checked rather than described
        (D-74): it names the platform-only review scope for a key and the review permission
        for a person, nothing else, and it calls `enforce_step_up`, which refuses a key and a
        stale session. The runtime half — a tenant session, a bank's key, a key bound to no
        agent, a person without a fresh assertion, an agent confirming its own suggestion —
        is apps/watch/tests_curation.py."""
        self.assertEqual(
            self.constants_named_by(CURATION_CONFIRMER),
            {"SCOPE_PROPOSALS_REVIEW", "PROPOSALS_REVIEW"},
            "require_curation_confirmer must name the review scope for a key and the review permission for a person",
        )
        self.assertIn(ENFORCE_STEP_UP, code_index().edges[CURATION_CONFIRMER], "a person's confirmation needs a fresh passkey")
        self.assertIn(perms.SCOPE_PROPOSALS_REVIEW, perms.PLATFORM_ONLY_SCOPES, "no bank's key may hold the review scope")
        self.assertNotIn(perms.PROPOSALS_REVIEW, perms.TENANT_PERMISSIONS, "no bank's role may hold the review permission")

    def test_a_watch_route_reaching_the_applier_is_refused(self) -> None:
        # The rule itself, fed fabricated routes. A watch route that reached the proposal
        # applier would be a way into the inventory without four eyes, and a route in neither
        # map that reached any writer would be a third door nobody looked at.
        self.assertIsNone(unexpected_writer("updateChange", {WATCH_WRITE}))
        self.assertIsNotNone(unexpected_writer("updateChange", {APPLY}))
        self.assertIsNotNone(unexpected_writer("updateChange", {WATCH_WRITE, APPLY_REVERIFICATION}))
        self.assertIsNotNone(unexpected_writer("listChanges", {WATCH_WRITE}))
        self.assertIsNone(unexpected_writer("approveProposal", {APPLY}))
        self.assertIsNotNone(unexpected_writer("approveProposal", {WATCH_WRITE}))

    def test_a_watch_route_carrying_the_wrong_gate_is_refused(self) -> None:
        # The same, for the gate: a watch route curating a change behind watch.read, or behind
        # no gate at all, would let a bank's own member write a fact every bank reads; and a
        # route held to one judgement may not quietly be moved to another.
        changes_write = perms.Gate("scope", perms.SCOPE_CHANGES_WRITE)
        sources_write = perms.Gate("scope", perms.SCOPE_SOURCES_WRITE)
        sources_manage = perms.Gate("permission", perms.SOURCES_MANAGE)
        writer, confirmer, nothing = {CHANGE_WRITER}, {CURATION_CONFIRMER}, set[Node]()
        self.assertIsNone(wrong_watch_gate("updateChange", None, writer))
        self.assertIsNotNone(wrong_watch_gate("updateChange", None, nothing))
        self.assertIsNotNone(wrong_watch_gate("updateChange", changes_write, nothing))
        self.assertIsNone(wrong_watch_gate("addChangeDocument", changes_write, nothing))
        self.assertIsNotNone(wrong_watch_gate("addChangeDocument", perms.Gate("permission", perms.WATCH_READ), nothing))
        self.assertIsNotNone(wrong_watch_gate("addChangeDocument", perms.Gate("scope", perms.SCOPE_LIBRARY_READ), nothing))
        # The registry: a person's permission, never a key's scope, and never the logic gate
        # that would also admit an agent.
        self.assertIsNone(wrong_watch_gate("createSource", sources_manage, nothing))
        self.assertIsNotNone(wrong_watch_gate("createSource", sources_write, nothing))
        self.assertIsNotNone(wrong_watch_gate("createSource", None, writer))
        self.assertIsNotNone(wrong_watch_gate("createSource", perms.Gate("permission", perms.WATCH_READ), nothing))
        self.assertIsNone(wrong_watch_gate("updateSource", sources_manage, nothing))
        # The coverage log: a key's own scope, and not the one that writes a change's facts.
        self.assertIsNone(wrong_watch_gate("recordSourceCheck", sources_write, nothing))
        self.assertIsNotNone(wrong_watch_gate("recordSourceCheck", changes_write, nothing))
        self.assertIsNotNone(wrong_watch_gate("recordSourceCheck", sources_manage, nothing))
        # A confirmation (D-74): the confirmer's gate alone, never the scope that files the
        # suggestion it confirms, and a curation route never trades its gate for this one.
        self.assertIsNone(wrong_watch_gate("confirmChangeCuration", None, confirmer))
        self.assertIsNotNone(wrong_watch_gate("confirmChangeCuration", None, writer))
        self.assertIsNotNone(wrong_watch_gate("confirmChangeCuration", None, writer | confirmer))
        self.assertIsNotNone(wrong_watch_gate("confirmChangeCuration", changes_write, nothing))
        self.assertIsNotNone(wrong_watch_gate("updateChange", None, confirmer))
        # A route that reaches the door with no entry in the gate map at all.
        self.assertIsNotNone(wrong_watch_gate("listChanges", sources_manage, nothing))

    def test_no_tenant_role_and_no_key_holds_proposals_review(self) -> None:
        self.assertNotIn(perms.PROPOSALS_REVIEW, perms.TENANT_PERMISSIONS)
        tenant_roles = [key for key in perms.SYSTEM_ROLES if key not in roles_logic.PLATFORM_ROLE_LABELS]
        self.assertIn("compliance_officer", tenant_roles)
        for key in tenant_roles:
            self.assertNotIn(perms.PROPOSALS_REVIEW, perms.SYSTEM_ROLES[key], f"the tenant role {key!r}")
        # A tenant's own role is refused it by the role editor.
        with self.assertRaises(ValidationError):
            roles_logic._validate_permissions([perms.PROPOSALS_REVIEW])
        # D-62/ADR 0054: an independent agent may hold the scope now, but only a platform
        # key, never a tenant's, and a key's principal never passes a permission gate.
        self.assertIn(perms.SCOPE_PROPOSALS_REVIEW, perms.ALL_SCOPES)
        self.assertIn(perms.SCOPE_PROPOSALS_REVIEW, perms.PLATFORM_ONLY_SCOPES)
        agent = Principal(
            kind=PrincipalKind.AGENT,
            subject_id=uuid.uuid4(),
            permissions=perms.ALL_PERMISSIONS,
            scopes=perms.ALL_SCOPES | {perms.PROPOSALS_REVIEW},
        )
        self.assertFalse(agent.has_permission(perms.PROPOSALS_REVIEW))


# ---------------------------------------------------------------------------------------
# Platform configuration: the three console routes and nothing else (D-102, ADR 0059)
# ---------------------------------------------------------------------------------------
def configuration_overreach(source: str, library_names: set[str]) -> list[str]:
    """The library models a console writer's module names beyond the platform configuration.
    The console opens the seed door, which the database accepts on every inventory table, so
    what keeps it to agent rows is that its module names no other library model."""
    visitor = LibraryWriteCalls()
    visitor.visit(ast.parse(source))
    return sorted((library_names & visitor.names) - set(PLATFORM_CONFIGURATION))


def module_offences(rel: str, source: str) -> list[str]:
    """Why a production module at `rel` may not hold `source`: it opens `library_write()`
    outside the allowlist, or the watch door outside the watch steps."""
    visitor = LibraryWriteCalls()
    visitor.visit(ast.parse(source))
    offences = []
    if visitor.calls and not _is_allowed(rel):
        offences.append(f"apps/{rel} calls library_write()")
    if visitor.watch_calls and rel not in WATCH_WRITE_ALLOWLIST:
        offences.append(f"apps/{rel} calls watch_write()")
    return offences


class PlatformConfigurationGuard(SimpleTestCase):
    """Proven to fail 2026-09-25, each breach then reverted: `@requires_step_up` removed from
    retireAgentVersion (red, the route named); updatePlatformAgentSettings gated by
    `agents.manage`, a bank administrator's permission (red); and `Obligation` named beside
    a write in `agents/seeds/console.py` (red, naming the model). Before this guard the three
    routes were red in `ProposalDoorGuard` as library writes without `proposals.review`."""

    def test_the_platform_configuration_is_two_real_models_and_three_registered_routes(self) -> None:
        self.assertLessEqual(
            set(PLATFORM_CONFIGURATION),
            {model.__name__ for model in concrete_library_models()},
            "PLATFORM_CONFIGURATION names a model that is not behind the fence",
        )
        operations = {operation.operation_id: operation for operation in iter_operations(api)}
        self.assertEqual(sorted(set(PLATFORM_CONFIGURATION_ROUTES) - set(operations)), [], "a route nobody registered")
        self.assertEqual(
            set(PLATFORM_CONFIGURATION_ROUTES) & (set(LIBRARY_WRITING_ROUTES) | set(WATCH_WRITING_ROUTES)),
            set(),
            "a route belongs to one door only",
        )
        for operation_id in PLATFORM_CONFIGURATION_ROUTES:
            self.assertEqual(view_node(operations[operation_id])[0], "apps.agents.api", f"{operation_id} is the agents app's")

    def test_each_route_is_a_platform_administrators_with_a_fresh_passkey_and_reaches_its_one_writer(self) -> None:
        index = code_index()
        operations = {operation.operation_id: operation for operation in iter_operations(api)}
        for operation_id, writer in PLATFORM_CONFIGURATION_ROUTES.items():
            operation = operations[operation_id]
            with self.subTest(route=_label(operation)):
                self.assertEqual(perms.gate_of(operation.view_func), PLATFORM_CONFIGURATION_GATE)
                self.assertTrue(perms.step_up_of(operation.view_func), "platform configuration needs a fresh passkey")
                self.assertTrue(operation.auth, "platform configuration needs a signed-in person")
                for auth in operation.auth:
                    self.assertIsInstance(auth, SessionAuth, "no API key reaches platform configuration")
                self.assertEqual(index.library_writes_reached(view_node(operation)), {writer})

    def test_the_writers_are_reached_from_the_console_logic_alone(self) -> None:
        # No task, command or other route names a console writer: what reaches one is the
        # route's own logic function and nothing else.
        index = code_index()
        expected = {
            "publish": [("apps.agents.definitions", "publish_version")],
            "retire": [("apps.agents.definitions", "retire_version")],
            "set_platform_settings": [("apps.agents.platform", "update_settings")],
        }
        for writer in PLATFORM_CONFIGURATION_ROUTES.values():
            with self.subTest(writer=writer):
                self.assertEqual(index.referrers(writer), expected[writer[1]])
        self.assertEqual(
            {node[1] for node in index.edges if node[0] == AGENT_CONSOLE and LIBRARY_WRITE in index.edges[node]},
            set(expected),
            "the console module opens library_write() in its three writers and nowhere else",
        )

    def test_the_console_writes_platform_configuration_and_no_other_library_model(self) -> None:
        library_names = {model.__name__ for model in concrete_library_models()}
        source = (APPS_DIR / "agents/seeds/console.py").read_text(encoding="utf-8")
        self.assertEqual(configuration_overreach(source, library_names), [])
        self.assertEqual(module_offences("agents/seeds/console.py", source), [])

    def test_the_permission_is_one_no_bank_and_no_key_holds(self) -> None:
        permission = PLATFORM_CONFIGURATION_GATE.value
        self.assertIn(permission, perms.PLATFORM_PERMISSIONS)
        self.assertNotIn(permission, perms.TENANT_PERMISSIONS)
        for key in (key for key in perms.SYSTEM_ROLES if key not in roles_logic.PLATFORM_ROLE_LABELS):
            self.assertNotIn(permission, perms.SYSTEM_ROLES[key], f"the tenant role {key!r}")
        with self.assertRaises(ValidationError):
            roles_logic._validate_permissions([permission])
        self.assertNotIn(permission.replace(".", ":"), perms.ALL_SCOPES)
        agent = Principal(
            kind=PrincipalKind.AGENT, subject_id=uuid.uuid4(), permissions=perms.ALL_PERMISSIONS, scopes=perms.ALL_SCOPES
        )
        self.assertFalse(agent.has_permission(permission))

    def test_anything_else_is_still_refused(self) -> None:
        publish, settings = PLATFORM_CONFIGURATION_ROUTES["publishAgentVersion"], PLATFORM_CONFIGURATION_ROUTES["updatePlatformAgentSettings"]
        self.assertIsNone(unexpected_writer("publishAgentVersion", {publish}))
        # A console route reaching the inventory, the watch door or another console writer.
        self.assertIsNotNone(unexpected_writer("publishAgentVersion", {publish, APPLY}))
        self.assertIsNotNone(unexpected_writer("updatePlatformAgentSettings", {WATCH_WRITE}))
        self.assertIsNotNone(unexpected_writer("retireAgentVersion", {publish}))
        # Another route reaching a console writer: a new tenant or agent route, or a
        # proposal kind whose approval applied an agent definition.
        self.assertIsNotNone(unexpected_writer("createTenantAgent", {settings}))
        self.assertIsNotNone(unexpected_writer("approveProposal", {APPLY, publish}))
        self.assertIsNotNone(unexpected_writer("createChange", {WATCH_WRITE, settings}))
        # A new shared model the console named beside a write is not platform configuration.
        planted = "def plant(row):\n    AgentBudgetLedger.objects.create(agent=row)\n"
        self.assertEqual(configuration_overreach(planted, {"Agent", "AgentBudgetLedger"}), ["AgentBudgetLedger"])
        self.assertEqual(configuration_overreach("Obligation.objects.update(x=1)", {"Obligation"}), ["Obligation"])
        # A new watch write module, and the console writer moved out of the seeds.
        self.assertNotEqual(module_offences("watch/planted.py", "watch_write('x')"), [])
        self.assertNotEqual(module_offences("watch/planted.py", "library_write('x')"), [])
        self.assertNotEqual(module_offences("agents/seeds/console.py", "watch_write('x')"), [])
        self.assertNotEqual(module_offences("agents/console.py", "library_write('x')"), [])

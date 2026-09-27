"""Scenario stubs for the shared app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

The structural guards in this app (tests_rls.py, tests_database_role.py,
tests_route_permissions.py, tests_middleware.py, ...) prove the mechanisms; each
scenario here calls the same entry points and asserts its own Gherkin end to end,
including a planted weakening where the Gherkin says a new route or table fails.
The NFR-04 stubs wait for chunk 14.

Prefixes hosted: NFR (S1..S16), I18N (S3, S4 are @e2e only, no stub).

Operations exercised (the audit-on-write guard reads these names): createProposal.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
from unittest import skip
from urllib.parse import urlsplit, urlunsplit

import psycopg
from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from psycopg import sql

from apps.identity.models import TenantRole
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals.models import Proposal
from apps.shared import factories, tenancy
from apps.shared.audit import Actor
from apps.shared import permissions as perms
from apps.shared.db_role_guard import check_role
from apps.shared.errors import PROBLEM_CONTENT_TYPE
from apps.shared.middleware import RequestIdLogFilter
from apps.shared.migration_helpers import POLICY_NAME, TENANT_SETTING
from apps.shared.permissions import UNGATED_BY_DESIGN, Ungated, UngatedReason, gate_of
from apps.shared.routes import TENANT_SCOPED_ROUTES, RegisteredOperation, iter_operations
from apps.shared.tenancy import is_tenant_task, tenant_task
from apps.shared.testing import ScenarioTestCase, sign_in, stub_session, user_principal
from apps.shared.tests_production_guard import BOOT, SETTING_NAMES, _with_database
from apps.shared.tests_rls import tenant_scoped_models
from apps.shared.tests_tenant_isolation import EXPECTED_MINIMUM_TENANT_ROUTES, PATH_PARAMETER, fill_path
from apps.taxonomy.models import TaxonomyTerm, Urgency
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from config.api import api
from config.celery import app as celery_app

V1 = "/api/v1"
WRITE_METHODS = frozenset({"POST", "PATCH", "PUT"})
# A field that would let a person choose how a pill looks (NFR-03): the tone follows the
# slot or the row's kind, never a choice.
CHOSEN_TONE_FIELDS = ("tone", "colour", "color")
# A response property named like presentation: the API sends keys, kinds and counts, and the
# client derives the pill and the phrase (playbook 15). Matched per camelCase word, so
# `milestone` is not a tone.
PRESENTATION_WORD = re.compile(r"(tone|colou?r|pill|badge|phrase)s?")
# A vocabulary reference inside a record carries exactly these. A term's key is unique only
# within its dimension, so a term reference may also carry that dimension's key.
VOCABULARY_REFERENCE = frozenset({"key", "kind", "label"})
LIST_KEY_FIELDS = frozenset({"dimension"})


def presentation_problems(openapi: dict[str, Any]) -> list[str]:
    """Walk every response schema of an OpenAPI document and name each property that
    carries presentation, and each vocabulary reference that is not exactly {key, kind,
    label}. A record is a response's root, a root list's element or a page's `items`; an
    object nested in a record that has a `key` and a `label` references a vocabulary row."""
    components = openapi["components"]["schemas"]
    problems: set[str] = set()
    seen: set[tuple[str, bool]] = set()

    def walk(schema: dict[str, Any], where: str, record: bool) -> None:
        ref = schema.get("$ref")
        if ref is not None:
            name = ref.rsplit("/", 1)[-1]
            if (name, record) not in seen:
                seen.add((name, record))
                walk(components[name], name, record)
            return
        for combined in ("allOf", "anyOf", "oneOf"):
            for part in schema.get(combined, []):
                walk(part, where, record)
        if isinstance(schema.get("items"), dict):
            walk(schema["items"], f"{where}[]", record)
        if isinstance(schema.get("additionalProperties"), dict):
            walk(schema["additionalProperties"], f"{where}{{}}", False)
        properties = schema.get("properties", {})
        fields = set(properties)
        if not record and {"key", "label"} <= fields:
            if not VOCABULARY_REFERENCE <= fields or not fields - VOCABULARY_REFERENCE <= LIST_KEY_FIELDS:
                problems.add(f"{where} is a vocabulary reference with {sorted(fields)}, not key, kind and label")
        for name, child in properties.items():
            if any(PRESENTATION_WORD.fullmatch(word.lower()) for word in re.findall(r"[A-Za-z][a-z0-9]*", name)):
                problems.add(f"{where}.{name} names presentation; send a key, a kind or a count")
            walk(child, f"{where}.{name}", record=record and name == "items" and child.get("type") == "array")

    for path, item in openapi["paths"].items():
        for method, operation in item.items():
            for code, response in operation.get("responses", {}).items():
                for content in response.get("content", {}).values():
                    if "schema" in content:
                        walk(content["schema"], f"{method.upper()} {path} {code}", record=True)
    return sorted(problems)


def names_field(error: dict[str, str], name: str) -> bool:
    """A 422 names the refused field: the field itself, or `extra` with the key in its message."""
    field = error["field"].rsplit(".", 1)[-1]
    return field == name or (field == "extra" and name in error["message"])


# What a problem-details body may hold (playbook 4.4): anything else would be a record.
PROBLEM_FIELDS = frozenset({"type", "title", "status", "detail", "code", "errors", "requiredPermission", "instance"})

# NFR-S6: a list that answers without PageQuery says why it cannot grow past a page. Keyed by
# operationId; a reviewer can disagree with the sentence (carry-overs ND5, ND2 and ND1).
BOUNDED_BY_DESIGN = {
    "e2eMailOutbox": "Test environments only: every deployed environment answers not_found.",
    "listAuthorities": "The library's issuing authorities: a short reference list, like jurisdictions.",
    "listCalendarFeeds": "One person's own subscriptions, capped by CALENDAR_FEEDS_PER_USER (plus the few revoked ones CALENDAR_FEED_REVOKED_SHOWN keeps).",
    "getCurrentBriefing": "One week in brief, its items capped by BRIEFING_MAX_ITEMS.",
    "getBriefing": "One stored week in brief, its items capped by BRIEFING_MAX_ITEMS when it was sent.",
    "getRecordSources": "The citations of one obligation's version in force: one per field it backs.",
    "getRoadmap": "The roadmap window: open dated cases inside the scope, from today, narrowed by from and to.",
    "getSourceCoverage": "One row per watched source, the same tens of rows as listSources.",
    "listInstrumentProvisions": "One instrument's own provision tree, read whole because a tree does not page.",
    "listJurisdictions": "The library's jurisdictions: a fixed reference list the seed writes.",
    "listLanguages": "The content languages the platform serves: five rows at R1.",
    "listMemberSessions": "One member's live sessions, each ended within SESSION_ABSOLUTE_HOURS_MAX.",
    "listMyPasskeys": "The caller's own live passkeys: a person holds a handful.",
    "listMySessions": "The caller's own live sessions, each ended within SESSION_ABSOLUTE_HOURS_MAX.",
    "listPermissions": "The fixed permission catalogue in code.",
    "listRoles": "One bank's roles: the system roles and the few it adds.",
    "listSources": "The platform-curated source registry: tens of rows until a bank's own sources arrive (WAT-06).",
    "listTaxonomyDimensions": "The taxonomy's dimensions: a handful of seeded rows.",
    "listTerms": "One vocabulary's rows (the taxonomy's terms), managed by an admin and read whole by pickers.",
    "listVocabularies": "The fixed set of vocabulary lists in code.",
    "listVocabularyRows": "One vocabulary's rows, managed by an admin and read whole by pickers.",
    # c8-tenants-contract (TEN-05, COL-04).
    "getMemberOpenWork": "One row per kind of work a member holds: nine kinds at most.",
    "listPeople": "One bank's active members as ids and names, read whole by every people picker (INPUT_DELTAS section 1).",
}
# The walk proves it finds what it is meant to find on a contract with one unpaged list.
PLANTED_LISTS: dict[str, Any] = {
    "paths": {"/rows": {"get": {"operationId": "listRows", "responses": {200: {"content": {"application/json": {"schema": {"type": "array"}}}}}}}},
    "components": {"schemas": {}},
}


def list_operations(openapi: dict[str, Any]) -> tuple[dict[str, tuple[str, dict[str, Any]]], dict[str, str]]:
    """Every GET whose answer is a list, a plain array or a page's `items`: the paged ones
    with their `limit` schema, and the ones without a `limit`, by operationId."""
    components = openapi["components"]["schemas"]

    def resolved(schema: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in schema:
            schema = components[schema["$ref"].rsplit("/", 1)[-1]]
        return schema

    paged: dict[str, tuple[str, dict[str, Any]]] = {}
    unpaged: dict[str, str] = {}
    for path, item in openapi["paths"].items():
        operation = item.get("get")
        if operation is None:
            continue
        responses: dict[Any, Any] = operation.get("responses", {})
        content: dict[str, Any] = (responses.get(200) or responses.get("200") or {}).get("content", {})
        media: dict[str, Any] = next(iter(content.values()), {})
        answer = resolved(media.get("schema", {}))
        items = answer.get("properties", {}).get("items")
        if answer.get("type") != "array" and not (items and resolved(items).get("type") == "array"):
            continue
        query = {p["name"]: p.get("schema", {}) for p in operation.get("parameters", []) if p["in"] == "query"}
        if "limit" in query and "offset" in query:
            paged[operation["operationId"]] = (path, query["limit"])
        else:
            unpaged[operation["operationId"]] = path
    return paged, unpaged


def rls_problems(tables: list[str]) -> list[str]:
    """What stands between each table and forced row-level security with a tenant policy,
    read from pg_class and pg_policies, each naming the migration step that adds it."""
    problems: list[str] = []
    with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
        for table in tables:
            cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", [table])
            enabled, forced = cursor.fetchone()
            cursor.execute(
                "SELECT qual, with_check FROM pg_policies WHERE tablename = %s AND policyname = %s", [table, POLICY_NAME]
            )
            policy = cursor.fetchone()
            fix = f"append rls_operations('{table}') to its migration"
            if not enabled:
                problems.append(f"{table}: ROW LEVEL SECURITY is not enabled; {fix}")
            if not forced:
                problems.append(f"{table}: ROW LEVEL SECURITY is not forced; {fix}")
            if policy is None or not all(TENANT_SETTING in (clause or "") for clause in policy):
                problems.append(f"{table}: no {POLICY_NAME} policy reading {TENANT_SETTING}; {fix}")
    return problems


def celery_problems(tasks: dict[str, Any], schedule: dict[str, dict[str, Any]]) -> list[str]:
    """A beat entry naming no registered task, and a task that takes `tenant_id` first
    without @tenant_task (which is what makes it take the id explicitly and activate it)."""
    problems = [
        f"beat entry {name} points at {entry.get('task')}, which no task registers"
        for name, entry in schedule.items()
        if entry.get("task") not in tasks and entry.get("task") not in celery_app.tasks
    ]
    for name, task in tasks.items():
        body = getattr(task, "__wrapped__", None) or task.run
        parameters = list(inspect.signature(body).parameters)
        if parameters[:1] == ["tenant_id"] and not is_tenant_task(body):
            problems.append(f"{name} is not wrapped in @tenant_task")
        if is_tenant_task(body) and list(inspect.signature(body.__wrapped__).parameters)[:1] != ["tenant_id"]:
            problems.append(f"{name} is a tenant task that does not take tenant_id first")
    return problems


def gate_problems(operations: list[RegisteredOperation], entries: dict[tuple[str, str], Ungated]) -> list[str]:
    """Every route with neither a gate nor a reason, and every reason that names no route
    or a gated one."""
    registered = {(op.method, op.path) for op in operations}
    problems = [f"{method} {path} is ungated by design but no such route exists" for method, path in entries if (method, path) not in registered]
    for op in operations:
        if gate_of(op.view_func) is not None and (op.method, op.path) in entries:
            problems.append(f"{op.method} {op.path} is gated and also ungated by design")
        elif gate_of(op.view_func) is None and (op.method, op.path) not in entries:
            problems.append(f"{op.method} {op.path} ({op.operation_id}) has no permission gate and no reason in UNGATED_BY_DESIGN")
    return sorted(problems)


def boot_django(database_url: str) -> subprocess.CompletedProcess[str]:
    """Boot Django in a subprocess on `database_url`, as a local environment, from an
    environment built from scratch so the runner's own settings cannot leak in."""
    env = {key: value for key, value in os.environ.items() if key not in SETTING_NAMES}
    test_db = connections[DEFAULT_DB_ALIAS].settings_dict["NAME"]
    env |= {
        "ENVIRONMENT": "local",
        "DEBUG": "true",
        "DATABASE_URL": database_url,
        "MIGRATOR_DATABASE_URL": _with_database(settings.MIGRATOR_DATABASE_URL, test_db),
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(  # noqa: S603 a fixed interpreter and script, no caller input
        [sys.executable, "-c", BOOT], cwd=str(settings.BASE_DIR), env=env, capture_output=True, text=True, timeout=120, check=False
    )


class CapturingHandler(logging.Handler):
    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__()
        self.records = records

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class SharedScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.shared, one method per @integration scenario."""

    def test_nfr_s1(self) -> None:
        """NFR-S1

        A record of tenant A requested by tenant B answers 404 on every tenant route.
        """
        tenant_a = factories.tenant(slug="iso-a")
        tenant_b = factories.tenant(slug="iso-b")
        # Every tenant permission and a fresh step-up, so tenancy alone stands between the
        # request and the record: a 403 here would hide a leak.
        member_of_b = user_principal(
            subject_id=factories.member_user(tenant_b, roles=("admin",)).id,
            tenant_id=tenant_b.id,
            permissions=perms.TENANT_PERMISSIONS,
            step_up_at=timezone.now(),
        )
        registered = {(op.method, op.path) for op in iter_operations(api)}
        proven = set()
        for method, path, _model, factory_name in TENANT_SCOPED_ROUTES:
            self.assertIn((method, path), registered, "the registry names a route Ninja did not register")
            record = getattr(factories, factory_name)(tenant=tenant_a)
            with self.subTest(route=f"{method} {path}"), stub_session(member_of_b):
                response = self.client.generic(
                    method, V1 + fill_path(path, record), "{}", content_type="application/json", **self.as_user(member_of_b)
                )
                self.assertEqual(response.status_code, 404, f"{method} {path} leaked or refused instead of 404")
                self.assertEqual(response.json()["code"], "not_found")
                self.assertLessEqual(set(response.json()), PROBLEM_FIELDS, "a 404 carries the problem and never the record")
            proven.add((method, path))
        # A new route in the bank's own namespace without this proof fails: every GET, PATCH
        # and DELETE under /tenant/ that addresses one record is in the registry.
        unproven = sorted(
            f"{op.method} {op.path}"
            for op in iter_operations(api)
            if op.path.startswith("/tenant/") and "{" in op.path and op.method in {"GET", "PATCH", "DELETE"}
            and (op.method, op.path) not in proven
        )
        self.assertEqual(unproven, [], "register these in apps/shared/routes.py TENANT_SCOPED_ROUTES")
        self.assertGreaterEqual(len(proven), EXPECTED_MINIMUM_TENANT_ROUTES)

    def test_nfr_s2(self) -> None:
        """NFR-S2

        The app refuses to boot on a role that can bypass row-level security.
        """
        test_db = connections[DEFAULT_DB_ALIAS].settings_dict["NAME"]
        superuser_url = _with_database(settings.TEST_SUPERUSER_DATABASE_URL, test_db)
        # A throwaway login with BYPASSRLS and nothing else: no ownership, not a superuser.
        # Roles belong to the cluster, so the name is unique to this run and dropped after it.
        bypass_role = f"cw_nfr_s2_{uuid.uuid4().hex[:12]}"
        bypass_password = uuid.uuid4().hex
        with psycopg.connect(superuser_url, autocommit=True) as admin:
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN BYPASSRLS PASSWORD {}").format(
                    sql.Identifier(bypass_role), sql.Literal(bypass_password)
                )
            )
        try:
            parts = urlsplit(_with_database(settings.DATABASE_URL, test_db))
            bypass_url = urlunsplit(parts._replace(netloc=f"{bypass_role}:{bypass_password}@{parts.hostname}:{parts.port}"))
            boots = {
                "superuser": (superuser_url, "is a superuser"),
                "BYPASSRLS role": (bypass_url, "has BYPASSRLS"),
                "table owner": (_with_database(settings.MIGRATOR_DATABASE_URL, test_db), "owns tables"),
                "cw_app": (_with_database(settings.DATABASE_URL, test_db), None),
            }
            with ThreadPoolExecutor(max_workers=len(boots)) as pool:
                results = dict(zip(boots, pool.map(boot_django, [url for url, _ in boots.values()]), strict=True))
        finally:
            with psycopg.connect(superuser_url, autocommit=True) as admin:
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(bypass_role)))
        for name, (_url, wrong) in boots.items():
            result = results[name]
            with self.subTest(role=name):
                if wrong is None:
                    self.assertEqual(result.returncode, 0, result.stderr[-800:])
                    self.assertIn("booted", result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0, f"booted on the {name}")
                    self.assertIn("Refusing to boot", result.stderr)
                    self.assertIn(wrong, result.stderr, "the refusal names the role property that is wrong")

    def test_nfr_s3(self) -> None:
        """NFR-S3

        Every tenant table has row-level security enabled, forced and with a policy.
        """
        tables = sorted(model._meta.db_table for model in tenant_scoped_models())
        self.assertIn("membership", tables, "the enumeration of tenant tables is broken")
        self.assertEqual(rls_problems(tables), [])
        # A new tenant table without a policy fails, with the migration to add named.
        with connection.schema_editor() as editor:
            editor.execute("CREATE TABLE nfr_s3_probe (id uuid PRIMARY KEY, tenant_id uuid REFERENCES tenant (id))")
        self.assertEqual(
            rls_problems(["nfr_s3_probe"]),
            [
                "nfr_s3_probe: ROW LEVEL SECURITY is not enabled; append rls_operations('nfr_s3_probe') to its migration",
                "nfr_s3_probe: ROW LEVEL SECURITY is not forced; append rls_operations('nfr_s3_probe') to its migration",
                f"nfr_s3_probe: no {POLICY_NAME} policy reading {TENANT_SETTING}; append rls_operations('nfr_s3_probe') to its migration",
            ],
        )

    def test_nfr_s5(self) -> None:
        """NFR-S5

        Every tenant task is wrapped in @tenant_task and every beat entry exists.
        """
        celery_app.loader.import_default_modules()
        tasks = {name: task for name, task in celery_app.tasks.items() if name.startswith("apps.")}
        self.assertIn("apps.home.tasks.send_weekly_briefing", tasks, "the enumeration of tasks is broken")
        self.assertEqual(celery_problems(tasks, celery_app.conf.beat_schedule or {}), [])

        # A tenant task that is not wrapped fails, and so does a beat entry naming no task.
        def unwrapped(tenant_id: uuid.UUID) -> None:
            """Would read a bank's rows with no tenant activated."""

        @tenant_task
        def wrapped(tenant_id: uuid.UUID) -> uuid.UUID | None:
            return tenancy.database_tenant_id()

        planted_tasks = {"apps.probe.unwrapped": SimpleNamespace(run=unwrapped), "apps.probe.wrapped": SimpleNamespace(run=wrapped)}
        planted_beat = {"probe-digest": {"task": "apps.probe.digest"}}
        self.assertEqual(
            celery_problems(planted_tasks, planted_beat),
            ["beat entry probe-digest points at apps.probe.digest, which no task registers", "apps.probe.unwrapped is not wrapped in @tenant_task"],
        )
        # The wrapper takes the tenant id explicitly and runs activated on it.
        tenant = factories.tenant(slug="task-bank")
        self.assertEqual(wrapped(str(tenant.id)), tenant.id)  # type: ignore[arg-type]

    def test_nfr_s6(self) -> None:
        """NFR-S6

        Every API response carries Server-Timing and the budget is enforced.
        """
        tenant = factories.tenant(slug="budget-bank")
        member = user_principal(
            subject_id=factories.member_user(tenant, roles=("admin",)).id, tenant_id=tenant.id, permissions=perms.TENANT_PERMISSIONS
        )
        platform = user_principal(permissions=perms.PLATFORM_PERMISSIONS)

        # Every response carries Server-Timing: app with the server time, and a request id.
        def timed(path: str, headers: dict[str, Any] | None = None) -> Any:
            response = self.client.get(f"{V1}{path}", **(headers or {}))
            self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$", path)
            self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{32}$", path)
            return response

        # Over API_BUDGET_MS a WARNING names the request id and the endpoint; under it, none.
        captured: list[logging.LogRecord] = []
        handler = CapturingHandler(captured)
        handler.addFilter(RequestIdLogFilter())
        budget_log = logging.getLogger("apps.shared.middleware")
        budget_log.addHandler(handler)
        try:
            with override_settings(API_BUDGET_MS=0):
                slow = timed("/reference/product")
            with override_settings(API_BUDGET_MS=60_000):
                timed("/reference/product")
        finally:
            budget_log.removeHandler(handler)
        warnings = [record for record in captured if record.levelno == logging.WARNING]
        self.assertEqual(len(warnings), 1, "one warning, for the request over budget only")
        self.assertEqual(getattr(warnings[0], "request_id"), slow["X-Request-ID"])  # noqa: B009
        self.assertEqual(getattr(warnings[0], "route"), "api/v1/reference/product")  # noqa: B009

        # Every list in the exported contract takes PageQuery or is bounded by design.
        openapi = api.get_openapi_schema(path_prefix=V1)
        paged, unpaged = list_operations(openapi)
        self.assertIn("listMembers", paged, "the enumeration of list routes is broken")
        self.assertEqual(sorted(set(unpaged) - set(BOUNDED_BY_DESIGN)), [], "page these with PageQuery or bound them with a reason")
        self.assertEqual(sorted(set(BOUNDED_BY_DESIGN) - set(unpaged)), [], "stale BOUNDED_BY_DESIGN entries")
        self.assertEqual(list_operations(PLANTED_LISTS), ({}, {"listRows": "/rows"}), "the walk finds an unpaged list")
        refused = 0
        for operation_id, (path, limit) in sorted(paged.items()):
            with self.subTest(operation=operation_id):
                self.assertEqual(
                    (limit.get("default"), limit.get("minimum"), limit.get("maximum")),
                    (settings.API_PAGE_SIZE_DEFAULT, 1, settings.API_PAGE_SIZE_MAX),
                )
                # Parameters are read before any permission, so a caller who is signed in
                # is refused a page above the maximum on every list, whatever it may read.
                url = PATH_PARAMETER.sub(lambda m: "tenant_tag" if m.group(0) == "{list_name}" else str(uuid.uuid4()), path)
                url = f"{url.removeprefix(V1)}?limit={settings.API_PAGE_SIZE_MAX + 1}"
                for principal in (member, platform):
                    with stub_session(principal):
                        response = timed(url, self.as_user(principal))
                    if response.status_code != 403:
                        break
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["errors"][0]["field"], "query.limit")
                refused += 1
        self.assertEqual(refused, len(paged))
        # And a list asked for no limit answers the default page.
        for _ in range(settings.API_PAGE_SIZE_DEFAULT + 1):
            factories.member(tenant)
        with stub_session(member):
            page = timed("/tenant/members", self.as_user(member)).json()
        self.assertEqual((len(page["items"]), page["total"] > settings.API_PAGE_SIZE_DEFAULT), (settings.API_PAGE_SIZE_DEFAULT, True))

    def test_nfr_s10(self) -> None:
        """NFR-S10

        Tone is never chosen by a person and the API never sends a phrase.
        """
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        tenant = factories.tenant(slug="bank")
        self.activate(tenant)
        ensure_tenant_vocabularies(tenant, actor=Actor.system("test"))
        # vocab.manage for the tenant's lists, proposals.create for the library's.
        session = sign_in(factories.member(tenant, roles=("admin", "compliance_officer")).user, tenant=tenant)
        openapi = api.get_openapi_schema(path_prefix=V1)
        schemas = openapi["components"]["schemas"]

        # Every vocabulary and term write refuses a tone or a colour, at the top of its body
        # and inside `extra`, on a tenant list (risk_rating) and a library list (urgency).
        urgency = Urgency.objects.order_by("sort_order", "key").values_list("key", flat=True).first()
        term_id = str(TaxonomyTerm.objects.order_by("key").values_list("id", flat=True).first())
        slots = (
            {"{list_name}": "risk_rating", "{key}": "low", "{term_id}": term_id},
            {"{list_name}": "urgency", "{key}": str(urgency), "{term_id}": term_id},
        )
        checked = 0
        for op in iter_operations(api):
            if op.method not in WRITE_METHODS or not op.path.startswith(("/vocab/", "/taxonomy/terms")):
                continue
            operation = openapi["paths"][f"{V1}{op.path}"][op.method.lower()]
            if "requestBody" not in operation:
                continue  # takes no body, so no field can name a tone
            body = schemas[operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]]
            payloads: list[tuple[dict[str, Any], str]] = [({name: "negative"}, name) for name in CHOSEN_TONE_FIELDS]
            if "extra" in body["properties"]:
                payloads += [({"extra": {name: "negative"}}, name) for name in CHOSEN_TONE_FIELDS]
            paths = []
            for slot in slots:
                path = op.path
                for placeholder, value in slot.items():
                    path = path.replace(placeholder, value)
                paths += [path] if path not in paths else []
            for path in paths:
                for payload, name in payloads:
                    with self.subTest(operation=op.operation_id, path=path, payload=payload):
                        response = self.client.generic(
                            op.method, f"{V1}{path}", json.dumps(payload), content_type="application/json", **session
                        )
                        self.assertEqual(response.status_code, 422, response.content)
                        problem = response.json()
                        self.assertEqual(problem["code"], "validation_error")
                        self.assertTrue(any(names_field(error, name) for error in problem["errors"]), problem)
                        checked += 1
        self.assertGreaterEqual(checked, 50, "the enumeration of vocabulary writes is broken")

        # A proposal is refused when it is made, never when it is approved: from the platform
        # editor's session and from an agent's key with proposals:write alike.
        editor = sign_in(factories.platform_user(roles=("library_editor",), email="editor@bleqq.test"))
        agent = {"HTTP_X_API_KEY": factories.api_key(tenant, scopes=(perms.SCOPE_PROPOSALS_WRITE,)).plain_key}
        flag = {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}}
        for who, headers in (("editor", editor), ("agent", agent)):
            for payload in ({**flag, "tone": "positive"}, {**flag, "extra": {"colour": "green"}}):
                with self.subTest(who=who, payload=payload):
                    before = Proposal.objects.count()
                    proposal = {"kind": "vocabulary_create", "title": "Add Client money", "payload": payload}
                    response = self.client.post(f"{V1}/proposals", proposal, content_type="application/json", **headers)
                    self.assertEqual(response.status_code, 422, response.content)
                    self.assertEqual(response.json()["code"], "validation_error")
                    self.assertEqual(Proposal.objects.count(), before)
            # Without the tone the same proposal is made, so the refusal was the tone's.
            proposal = {"kind": "vocabulary_create", "title": f"Add Client money ({who})", "payload": flag}
            made = self.client.post(f"{V1}/proposals", proposal, content_type="application/json", **headers)
            self.assertEqual(made.status_code, 201, made.content)

        # No response carries a tone, a colour, a pill, a badge or a phrase, and every
        # vocabulary reference is key, kind and label.
        self.assertEqual(presentation_problems(openapi), [])
        # The walk finds what it is meant to find: a planted tone, reference and phrase.
        response_ref = {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Row"}}}}}
        planted = {
            "paths": {"/rows": {"get": {"responses": response_ref}}},
            "components": {
                "schemas": {
                    "Row": {"properties": {"pillTone": {"type": "string"}, "urgency": {"$ref": "#/components/schemas/Ref"}}},
                    "Ref": {"properties": {"key": {}, "label": {}, "phrase": {}}},
                }
            },
        }
        self.assertEqual(len(presentation_problems(planted)), 3, presentation_problems(planted))

    @skip("pending: NFR-S11 (NFR-04, chunk 14)")
    def test_nfr_s11(self) -> None:
        """NFR-S11

        An unrecognised environment name is treated as production.
        """

    @skip("pending: NFR-S12 (NFR-04, chunk 14)")
    def test_nfr_s12(self) -> None:
        """NFR-S12

        The boot guards refuse an unsafe deployed configuration.
        """

    def test_nfr_s13(self) -> None:
        """NFR-S13

        Every route is permission-gated or ungated by design with a reason.
        """
        operations = list(iter_operations(api))
        self.assertGreater(len(operations), 100, "the enumeration of operations is broken")
        self.assertEqual(gate_problems(operations, UNGATED_BY_DESIGN), [])
        # The reasons are the five shapes, and each entry says why in a sentence.
        self.assertEqual({reason.value for reason in UngatedReason}, {"self", "bootstrap", "capability", "logic-gate", "public-token"})
        for key, entry in UNGATED_BY_DESIGN.items():
            with self.subTest(route=key):
                self.assertIsInstance(entry.reason, UngatedReason)
                self.assertGreater(len(entry.note.strip()), 20)

        # A new route with neither fails the guard, and so does an entry that names no route
        # or a route that is gated after all.
        def new_route(request: object) -> None:
            """Registered with no decorator and no entry."""

        gated = next(op for op in operations if gate_of(op.view_func) is not None)
        planted = [
            RegisteredOperation("GET", "/probe", "probeRoute", new_route, auth=None),
            RegisteredOperation(gated.method, gated.path, gated.operation_id, gated.view_func, auth=None),
        ]
        entries = {
            (gated.method, gated.path): Ungated(UngatedReason.SELF, "Planted beside a permission gate."),
            ("GET", "/gone"): Ungated(UngatedReason.BOOTSTRAP, "Planted for a route nobody registered."),
        }
        self.assertEqual(
            gate_problems(planted, entries),
            sorted([
                "GET /gone is ungated by design but no such route exists",
                "GET /probe (probeRoute) has no permission gate and no reason in UNGATED_BY_DESIGN",
                f"{gated.method} {gated.path} is gated and also ungated by design",
            ]),
        )

    @skip("pending: NFR-S14 (NFR-04, chunk 14)")
    def test_nfr_s14(self) -> None:
        """NFR-S14

        /health/ names the failing component.
        """

    @skip("pending: NFR-S15 (NFR-04, chunk 14)")
    def test_nfr_s15(self) -> None:
        """NFR-S15

        Tenant content and personal data beyond name and id never reach logs or Sentry.
        """

    def test_nfr_s16(self) -> None:
        """NFR-S16

        Every error uses one shape and an empty answer is 200.
        """
        tenant = factories.tenant(slug="errors-bank")
        self.activate(tenant)
        admin = sign_in(factories.member(tenant, roles=("admin",)).user, tenant=tenant)
        reader = sign_in(factories.member(tenant, roles=("reader",)).user, tenant=tenant)
        row = f"{V1}/vocab/risk_rating/low"
        version = self.client.get(row, **admin).json()["version"]

        def problem(response: Any, status: int, code: str) -> dict[str, Any]:
            self.assertEqual(response.status_code, status, response.content)
            self.assertEqual(response["Content-Type"], PROBLEM_CONTENT_TYPE)
            body: dict[str, Any] = response.json()
            self.assertEqual((body["status"], body["code"]), (status, code))
            self.assertTrue(body["title"] and body["detail"], body)
            return body

        # A validation failure: 422 with errors[] naming the field.
        invalid = problem(self.client.patch(row, {"labels": "low"}, content_type="application/json", **admin), 422, "validation_error")
        self.assertTrue(invalid["errors"] and all(error["field"] and error["message"] for error in invalid["errors"]), invalid)
        self.assertTrue(any(error["field"].endswith("labels") for error in invalid["errors"]), invalid)
        # A denied request: 403 naming the permission it lacked.
        denied = problem(self.client.get(f"{V1}/tenant/members", **reader), 403, "permission_denied")
        self.assertEqual(denied["requiredPermission"], perms.MEMBERS_MANAGE)
        # A stale write: 409 when If-Match names a version that is no longer the row's.
        fresh = self.client.patch(row, {"labels": {"en": "Low risk"}}, content_type="application/json", HTTP_IF_MATCH=str(version), **admin)
        self.assertEqual(fresh.status_code, 200, fresh.content)
        stale = self.client.patch(row, {"labels": {"en": "Lower"}}, content_type="application/json", HTTP_IF_MATCH=str(version), **admin)
        problem(stale, 409, "stale_write")
        # A missing record: 404, with no trace in any of them.
        missing = problem(self.client.get(f"{V1}/obligations/{uuid.uuid4()}", **admin), 404, "not_found")
        for body in (invalid, denied, missing):
            self.assertNotIn("Traceback", json.dumps(body))
        # A filtered list that matches nothing answers 200 with an empty collection.
        empty = self.client.get(f"{V1}/audit-events", {"subjectId": str(uuid.uuid4())}, **admin)
        self.assertEqual(empty.status_code, 200, empty.content)
        self.assertEqual((empty.json()["items"], empty.json()["total"]), ([], 0))
        self.assertGreater(self.client.get(f"{V1}/audit-events", **admin).json()["total"], 0, "the filter, not an empty log, emptied it")


class SharedTenancyScenarioTests(TransactionTestCase):
    """The scenarios that need rows committed on one connection and read on cw_app's."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def test_nfr_s4(self) -> None:
        """NFR-S4

        An unset tenant matches no rows.
        """
        tenant_a = factories.tenant(slug="unset-a")
        tenant_b = factories.tenant(slug="unset-b")
        self.assertEqual(check_role(connections["app"]).role, "cw_app")

        def visible_roles(tenant_id: uuid.UUID | None) -> set[uuid.UUID]:
            with transaction.atomic(using="app"):
                if tenant_id is not None:
                    tenancy.activate(tenant_id, using="app")
                self.assertEqual(tenancy.database_tenant_id(using="app"), tenant_id)
                return set(TenantRole.objects.using("app").values_list("tenant_id", flat=True))

        self.assertEqual(visible_roles(None), set(), "an unset tenant must match no rows (fail closed)")
        self.assertEqual(visible_roles(tenant_a.id), {tenant_a.id})
        self.assertEqual(visible_roles(tenant_b.id), {tenant_b.id})
        # The rows are there: the migrator, which owns the table, sees both tenants once it
        # activates each, so the empty read above was the policy and not an empty table.
        with transaction.atomic():
            tenancy.activate(tenant_a.id)
            self.assertTrue(TenantRole.objects.filter(tenant=tenant_a).exists())

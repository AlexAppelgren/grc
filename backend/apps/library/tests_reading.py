"""The obligations list (INV-03, INV-04, INV-05, FP-01, FP-03, NFR-03): `GET /obligations`
with its filters, "as of", the footprint verdict and its reason, pagination, the gate, a
query count that does not grow with the page, and tenant-private rows under row-level
security as the app role sees them.

Every date is pinned: research payments version 2 takes effect 2026-10-01, and nothing
here depends on the day the suite runs."""

from __future__ import annotations

import datetime
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest import mock

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from pydantic import ValidationError

from apps.identity.models import User
from apps.library import reading
from apps.library import testing as build
from apps.library.models import Obligation
from apps.library.reading import obligation_scopes, scope_term_ids
from apps.library.schemas import ObligationRow
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.logging import JsonFormatter
from apps.shared.middleware import RequestIdLogFilter
from apps.shared.models import Tenant
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, sign_in, stub_session, user_principal
from apps.taxonomy.models import FootprintTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

URL = "/api/v1/obligations"
D = datetime.date
EARLY = D(2026, 6, 30)  # the day the fixture's library was last verified
CHANGE_DAY = D(2026, 10, 1)  # research payments version 2
FOOTPRINT = ("regime:securities", "service_type:non_advised", "service_type:execution_only", "account_type:isk")
ALL_SERVICES = (
    "service_type:advice",
    "service_type:non_advised",
    "service_type:execution_only",
    "service_type:portfolio_management",
    "service_type:custody",
    "service_type:insurance_distribution",
)
# Queries per list read with a real session, measured 2026-09-19 and pinned so an N+1 shows
# up as a number (playbook 10): the request's savepoint pair (2); the session (identity flag
# on, the session row, flag off, the tenant activation, tenant and platform role permissions,
# the latest step-up: 7); the caller's tenant and locale (2); the footprint and its restricting
# dimensions (2); the count and the page (2); the page's titles and versions (2); the scope
# (own terms, instrument regimes, the terms: 3); the tags of the page and their rows (2); one
# label query each for terms, tags, duty types and levels (4); the dimensions with their term
# counts and labels (2).
LIST_QUERIES = 2 + 7 + 2 + 2 + 2 + 2 + 3 + 2 + 4 + 2


def seed_reference() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_taxonomy_terms()


def set_footprint(tenant: Tenant, refs: tuple[str, ...]) -> None:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        for ref in refs:
            FootprintTerm.objects.create(tenant=tenant, term=build.term(ref))


def seed_obligations() -> None:
    """Six shared obligations. By tenant A's footprint: a, d, e and f are inside; b is
    outside by its service and c by its instrument's regime."""
    lvm = build.instrument(key="lvm", short_name="LVM", regime="regime:securities")
    esma = build.instrument(key="esma", short_name="ESMA guidelines", regime="regime:securities", level="eu_guidance", binding=False)
    lfd = build.instrument(key="lfd", short_name="LFD", regime="regime:insurance")
    plain = build.instrument(key="plain", short_name="Plain")
    build.obligation(
        lvm,
        key="obl-a-appropriateness",
        titles={"sv": "Bedöm om tjänsten passar kunden", "en": "Assess appropriateness"},
        ref_label="9 kap.",
        terms=("service_type:non_advised", "service_type:execution_only", "account_type:isk"),
        tags=("appropriateness",),
        versions=((None, {"sv": "Bedöm passandet.", "en": "Assess the fit."}),),
        last_verified_at=datetime.datetime(2026, 6, 30, 8, 0, tzinfo=datetime.UTC),
    )
    build.obligation(lvm, key="obl-b-advice", titles={"en": "Advise suitably"}, terms=("service_type:advice",), tags=("advice",))
    build.obligation(lfd, key="obl-c-insurance", titles={"en": "Establish demands and needs"}, duty_type="disclosure")
    build.obligation(
        lvm,
        key="obl-d-research",
        titles={"en": "Pay for research only under the permitted models"},
        ref_label="Third-party payments",
        duty_type="reporting",
        terms=("service_type:non_advised",),
        versions=((D(2025, 1, 1), {"en": "Research is paid from own resources."}), (CHANGE_DAY, {"en": "Research may be paid jointly."})),
    )
    build.obligation(esma, key="obl-e-guidance", titles={"en": "Make warnings prominent"}, terms=ALL_SERVICES)
    build.obligation(plain, key="obl-f-unscoped", titles={"en": "Keep a register"}, duty_type="record_keeping")


def keys(response: Any) -> list[str]:
    assert response.status_code == 200, response.content
    return [row["stableKey"] for row in response.json()["items"]]


def field_names(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {name for item in value.values() for name in field_names(item)}
    if isinstance(value, list):
        return {name for item in value for name in field_names(item)}
    return set()


class ObligationListTests(TestCase):
    tenant: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="list-a")
        set_footprint(cls.tenant, FOOTPRINT)
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        seed_obligations()

    def get(self, params: dict[str, Any], headers: dict[str, Any] | None = None) -> Any:
        return self.client.get(URL, params, **(headers if headers is not None else sign_in(self.reader, tenant=self.tenant)))

    def row(self, key: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.get({"outsideFootprint": "true", **params})
        self.assertEqual(response.status_code, 200, response.content)
        return next(row for row in response.json()["items"] if row["stableKey"] == key)

    def test_a_row_carries_keys_kinds_and_facts_never_a_phrase(self) -> None:
        row = self.row("obl-a-appropriateness", {"asOf": EARLY.isoformat()})
        self.assertEqual(row["refLabel"], "9 kap.")
        # The reader reads en; the title was written in sv, so en is a labelled machine translation.
        self.assertEqual(row["title"], {"text": "Assess appropriateness", "language": "en", "isOriginal": False, "isMachine": True})
        self.assertEqual(row["instrument"], {"key": "lvm", "shortName": "LVM"})
        self.assertEqual((row["bindingLevel"]["key"], row["binding"]), ("act", True))
        self.assertEqual(row["dutyType"]["key"], "conduct")
        self.assertEqual([tag["key"] for tag in row["tags"]], ["appropriateness"])
        scope = {entry["dimension"]["key"]: entry for entry in row["scope"]}
        self.assertEqual([term["key"] for term in scope["regime"]["terms"]], ["securities"], "the instrument's regime is inherited")
        self.assertEqual([term["key"] for term in scope["service_type"]["terms"]], ["non_advised", "execution_only"])
        self.assertEqual(scope["client_category"]["terms"], [], "an empty dimension is listed: it means no restriction")
        self.assertEqual(scope["jurisdiction"]["terms"], [], "no jurisdiction term is inherited")
        self.assertEqual(row["version"], {"versionNumber": 1, "effectiveFrom": None})
        self.assertIsNone(row["upcomingVersion"])
        self.assertEqual((row["inFootprint"], row["outsideReason"]), (True, []))
        self.assertEqual(row["lastVerifiedAt"], "2026-06-30T08:00:00Z")
        self.assertEqual((row["openChangeCount"], row["pendingApplicability"], row["complianceStatus"]), (0, None, None))
        self.assertTrue({"tone", "pill", "color", "colour"}.isdisjoint(field_names(self.get({}).json())))

    def test_all_selected_is_true_when_every_term_of_a_dimension_is_carried(self) -> None:
        guidance = self.row("obl-e-guidance", {})
        scope = {entry["dimension"]["key"]: entry for entry in guidance["scope"]}
        self.assertTrue(scope["service_type"]["allSelected"])
        self.assertEqual(len(scope["service_type"]["terms"]), len(ALL_SERVICES))
        self.assertFalse(scope["regime"]["allSelected"])
        self.assertFalse(scope["client_category"]["allSelected"], "an empty dimension is not all selected")
        self.assertEqual((guidance["bindingLevel"]["key"], guidance["binding"]), ("eu_guidance", False))

    def test_rows_outside_the_footprint_are_hidden_until_asked_for_with_their_reason(self) -> None:
        self.assertEqual(keys(self.get({})), ["obl-a-appropriateness", "obl-d-research", "obl-e-guidance", "obl-f-unscoped"])
        everything = self.get({"outsideFootprint": "true"}).json()
        self.assertEqual(everything["total"], 6)
        rows = {row["stableKey"]: row for row in everything["items"]}
        # The SQL filter and the Python verdict are one rule: what the default hides is what
        # the verdict calls outside.
        self.assertEqual({key for key, row in rows.items() if row["inFootprint"]}, set(keys(self.get({}))))
        advice = rows["obl-b-advice"]["outsideReason"]
        self.assertEqual([(r["dimension"]["key"], [t["key"] for t in r["terms"]]) for r in advice], [("service_type", ["advice"])])
        insurance = rows["obl-c-insurance"]["outsideReason"]
        self.assertEqual([(r["dimension"]["key"], [t["key"] for t in r["terms"]]) for r in insurance], [("regime", ["insurance"])])
        self.assertEqual(rows["obl-f-unscoped"]["outsideReason"], [], "a record with no terms matches every footprint")

    def test_the_scope_rule_and_its_sql_twin_agree(self) -> None:
        # The footprint filter runs in SQL and the verdict in Python: one rule, pinned here.
        scopes = obligation_scopes()
        sql = {row.id: set(row.term_ids) for row in Obligation.objects.annotate(term_ids=scope_term_ids())}
        python = {key: {term.id for terms in scopes.get(key, {}).values() for term in terms} for key in sql}
        self.assertEqual(python, sql)
        self.assertEqual(len(sql), 6)
        self.assertEqual(set(obligation_scopes(list(sql))), set(scopes), "for given obligations as for all of them")

    def test_the_search_never_reaches_the_logs(self) -> None:
        lines: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                lines.append(JsonFormatter().format(record))

        handler = Capture()
        handler.addFilter(RequestIdLogFilter())
        request_logger = logging.getLogger("django.request")
        request_logger.addHandler(handler)
        headers = {**sign_in(self.reader, tenant=self.tenant), "HTTP_X_REQUEST_ID": "req-obligations-1"}
        try:
            refused = self.get({"q": "fraud at branch twelve", "term": "advice"}, headers)
        finally:
            request_logger.removeHandler(handler)
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(len(lines), 1, "the refusal is logged")
        self.assertNotIn("branch", lines[0])
        self.assertIn("GET api/v1/obligations", lines[0])
        self.assertIn('"request_id": "req-obligations-1"', lines[0], "Django logs after the middleware; the id still travels")

    def test_every_row_is_validated_before_it_is_answered(self) -> None:
        # A value the database or a later change gets wrong fails the read; it never reaches
        # the wire as a 200.
        with mock.patch.object(reading, "in_force", return_value=mock.Mock(version_number="many", effective_from=None)):
            with self.assertRaises(ValidationError):
                self.get({})
        # So does a row built without validation: the page validates every row it holds.
        unchecked = ObligationRow.model_construct(id="not-a-uuid", stable_key=None)
        with mock.patch.object(reading, "obligation_page", return_value=([unchecked], 1)), self.assertRaises(ValidationError):
            self.get({})

    def test_as_of_returns_the_version_in_force_and_the_one_to_come(self) -> None:
        before = self.row("obl-d-research", {"asOf": EARLY.isoformat()})
        self.assertEqual(before["version"], {"versionNumber": 1, "effectiveFrom": {"date": "2025-01-01", "precision": "day"}})
        self.assertEqual(before["upcomingVersion"], {"versionNumber": 2, "effectiveFrom": {"date": "2026-10-01", "precision": "day"}})
        on = self.row("obl-d-research", {"asOf": CHANGE_DAY.isoformat()})
        self.assertEqual(on["version"]["versionNumber"], 2)
        self.assertIsNone(on["upcomingVersion"])
        not_yet = self.row("obl-d-research", {"asOf": "2024-12-31"})
        self.assertIsNone(not_yet["version"])
        self.assertEqual(not_yet["upcomingVersion"]["versionNumber"], 1)
        self.assertEqual(self.get({"asOf": "30 June"}).status_code, 422)

    def test_as_of_defaults_to_today_in_the_tenants_time_zone(self) -> None:
        # 22:00 UTC on 30 September is midnight on 1 October in Stockholm (CEST, UTC+2).
        headers = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}
        reader = user_principal(permissions={perms.LIBRARY_READ}, tenant_id=self.tenant.id, subject_id=self.reader.id)
        for instant, expected in ((datetime.datetime(2026, 9, 30, 21, 59, tzinfo=datetime.UTC), 1), (datetime.datetime(2026, 9, 30, 22, 0, tzinfo=datetime.UTC), 2)):
            with self.subTest(instant=instant), stub_session(reader), mock.patch("django.utils.timezone.now", return_value=instant):
                response = self.get({"outsideFootprint": "true"}, headers)
                research = next(row for row in response.json()["items"] if row["stableKey"] == "obl-d-research")
                self.assertEqual(research["version"]["versionNumber"], expected)

    def test_every_filter(self) -> None:
        self.assertEqual(keys(self.get({"instrument": "esma"})), ["obl-e-guidance"])
        self.assertEqual(keys(self.get({"instrument": "no-such-instrument"})), [], "an unknown key matches nothing")
        self.assertEqual(keys(self.get({"dutyType": "reporting"})), ["obl-d-research"])
        self.assertEqual(keys(self.get({"term": "service_type:execution_only"})), ["obl-a-appropriateness", "obl-e-guidance"])
        self.assertEqual(keys(self.get({"term": "regime:securities"})), ["obl-a-appropriateness", "obl-d-research", "obl-e-guidance"], "the regime is inherited")
        self.assertEqual(keys(self.get({"term": ["service_type:execution_only", "account_type:isk"]})), ["obl-a-appropriateness"], "every term must match")
        self.assertEqual(keys(self.get({"term": "regime:insurance", "outsideFootprint": "true"})), ["obl-c-insurance"])
        self.assertEqual(keys(self.get({"q": "PASSAR"})), ["obl-a-appropriateness"], "a title in any language, any case")
        self.assertEqual(keys(self.get({"q": "third-party"})), ["obl-d-research"], "the reference label")
        self.assertEqual(keys(self.get({"q": "nothing like this"})), [])
        self.assertEqual(self.get({"q": "x" * 201}).status_code, 422)
        malformed = self.get({"term": "advice"})
        self.assertEqual((malformed.status_code, malformed.json()["code"]), (422, "validation_error"))
        unknown = self.get({"term": ["service_type:advice", "service_type:astrology"]})
        self.assertEqual((unknown.status_code, unknown.json()["code"]), (422, "unknown_key"))
        self.assertIn("service_type:astrology", unknown.json()["detail"])
        too_many = self.get({"term": ["service_type:advice"] * (settings.LIBRARY_TERM_FILTER_MAX + 1)})
        self.assertEqual(too_many.status_code, 422)

    def test_pagination(self) -> None:
        first = self.get({"limit": 2}).json()
        self.assertEqual(([row["stableKey"] for row in first["items"]], first["total"]), (["obl-a-appropriateness", "obl-d-research"], 4))
        second = self.get({"limit": 2, "offset": 2}).json()
        self.assertEqual([row["stableKey"] for row in second["items"]], ["obl-e-guidance", "obl-f-unscoped"])
        self.assertEqual(self.get({"offset": 10}).json(), {"items": [], "total": 4}, "an empty page is 200")
        self.assertEqual(self.get({"limit": 101}).status_code, 422)
        self.assertEqual(self.get({"limit": 0}).status_code, 422)

    def test_the_query_count_does_not_grow_with_the_page(self) -> None:
        for limit in (1, 4):
            headers = sign_in(self.reader, tenant=self.tenant)
            with self.subTest(limit=limit), self.assertNumQueries(LIST_QUERIES):
                response = self.get({"limit": limit, "asOf": EARLY.isoformat()}, headers)
            self.assertEqual(len(response.json()["items"]), limit)
        # However many terms a filter names, they are resolved in one query.
        for terms in (["regime:securities"], ["regime:securities", "service_type:non_advised", "account_type:isk"]):
            headers = sign_in(self.reader, tenant=self.tenant)
            with self.subTest(terms=terms), self.assertNumQueries(LIST_QUERIES + 1):
                self.assertEqual(self.get({"term": terms, "limit": 1}, headers).status_code, 200)

    def test_a_person_needs_library_read_and_a_key_needs_library_read_scope(self) -> None:
        self.assertEqual(self.get({}, {}).status_code, 401)
        without = user_principal(permissions={perms.CASES_READ}, tenant_id=self.tenant.id)
        with stub_session(without):
            refused = self.get({}, {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"})
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.LIBRARY_READ))
        no_scope = factories.api_key(self.tenant, scopes=(perms.SCOPE_CHANGES_WRITE,))
        refused = self.get({}, {"HTTP_X_API_KEY": no_scope.plain_key})
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.SCOPE_LIBRARY_READ))
        key = factories.api_key(self.tenant, scopes=(perms.SCOPE_LIBRARY_READ,))
        self.assertEqual(keys(self.get({}, {"HTTP_X_API_KEY": key.plain_key})), keys(self.get({})), "an agent sees the tenant's footprint")


class ObligationListPerformance(TestCase):
    """NFR-02, playbook 10: a full page of heavy rows stays inside the API budget and its
    query count does not grow with the page."""

    tenant: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="list-perf")
        set_footprint(cls.tenant, FOOTPRINT)
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        build.library_of(settings.API_PAGE_SIZE_MAX + 20)

    def test_a_full_page_stays_inside_the_budget(self) -> None:
        headers = sign_in(self.reader, tenant=self.tenant)
        params: dict[str, Any] = {"outsideFootprint": "true", "limit": settings.API_PAGE_SIZE_MAX, "asOf": EARLY.isoformat()}
        with self.assertNumQueries(LIST_QUERIES):
            response = self.client.get(URL, params, **headers)
        self.assertEqual(len(response.json()["items"]), settings.API_PAGE_SIZE_MAX)
        # CPU time on the request thread, the best of five: what the read costs, without the
        # waits a loaded machine adds, so the bound holds on a busy CI runner too. The suite
        # runs under coverage, whose tracer is paused for the timed requests only; the one
        # above stays traced, so coverage is unchanged.
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                self.client.get(URL, params, **headers)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)


@contextmanager
def as_app_role() -> Iterator[None]:
    """Every query in the block, the request's own included, runs as cw_app: the default
    alias reconnects with the app role's credentials to the same test database."""
    default = connections[DEFAULT_DB_ALIAS]
    app = connections["app"].settings_dict
    saved = (default.settings_dict["USER"], default.settings_dict["PASSWORD"])
    default.close()
    default.settings_dict["USER"], default.settings_dict["PASSWORD"] = app["USER"], app["PASSWORD"]
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            assert cursor.fetchone() == (app["USER"],)
        yield
    finally:
        default.close()
        default.settings_dict["USER"], default.settings_dict["PASSWORD"] = saved


class PrivateObligationIsolation(TransactionTestCase):
    """INPUT_DELTAS §5, INV-07: as the app role, under forced row-level security, another
    tenant's private obligation is never in the list, the total, a q match or a filter."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_reference()
        self.tenant_a = factories.tenant(slug="iso-lib-a")
        self.tenant_b = factories.tenant(slug="iso-lib-b")
        set_footprint(self.tenant_a, FOOTPRINT)
        with transaction.atomic():
            seed_obligations()
        with transaction.atomic():
            tenancy.activate(self.tenant_b.id)
            build.obligation(
                build.instrument(key="bank-b-policy", regime="regime:securities", owner_tenant=self.tenant_b),
                key="obl-b-private",
                titles={"en": "Bank B's private duty"},
                terms=("service_type:non_advised",),
                owner_tenant=self.tenant_b,
            )
        self.key_a = factories.api_key(self.tenant_a, scopes=(perms.SCOPE_LIBRARY_READ,))
        self.key_b = factories.api_key(self.tenant_b, scopes=(perms.SCOPE_LIBRARY_READ,))

    def get(self, key: Any, params: dict[str, Any]) -> Any:
        response = self.client.get(URL, params, HTTP_X_API_KEY=key.plain_key)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_another_tenants_private_obligation_is_never_read(self) -> None:
        with as_app_role():
            for params in (
                {},
                {"outsideFootprint": "true"},
                {"q": "private duty", "outsideFootprint": "true"},
                {"instrument": "bank-b-policy", "outsideFootprint": "true"},
                {"term": "service_type:non_advised", "outsideFootprint": "true"},
                {"dutyType": "conduct", "outsideFootprint": "true"},
            ):
                with self.subTest(params=params):
                    page = self.get(self.key_a, params)
                    self.assertNotIn("obl-b-private", [row["stableKey"] for row in page["items"]])
                    self.assertEqual(page["total"], len(page["items"]), "the total counts only what the tenant may see")
            self.assertEqual(self.get(self.key_a, {"outsideFootprint": "true"})["total"], 6)
            # The owner sees it beside the shared library, so the proof above is not vacuous.
            own = self.get(self.key_b, {"q": "private duty", "outsideFootprint": "true"})
            self.assertEqual([row["stableKey"] for row in own["items"]], ["obl-b-private"])

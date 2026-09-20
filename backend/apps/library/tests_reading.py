"""Reading the library (INV-03..INV-06, FP-01, FP-03, NFR-03): `GET /obligations` with its
filters, "as of", the footprint verdict and its reason, pagination, the gate, a query count
that does not grow with the page; `GET /obligations/{id}`, the whole card as of a date; and
`GET /obligations/{id}/diff`, what changed between two versions. Tenant-private records are
read as the app role sees them under row-level security: neither in a list nor at an
address of their own.

Every date is pinned: research payments version 2 takes effect 2026-10-01, and nothing
here depends on the day the suite runs."""

from __future__ import annotations

import datetime
import json
import logging
import sys
import time
import uuid
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
from apps.library.models import Obligation, Provision
from apps.library.reading import obligation_scopes, scope_term_ids
from apps.library.schemas import ObligationRow
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
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
# on, the session row, flag off, the tenant activation, the tenant role permissions, the
# latest step-up: 6 — a bank session does not read the platform roles at all, hardening
# H13); the caller's tenant and locale (2); the footprint and its restricting
# dimensions (2); the count and the page (2); the page's titles and versions (2); the scope
# (own terms, instrument regimes, the terms: 3); the tags of the page and their rows (2); one
# label query each for terms, tags, duty types and levels (4); the dimensions with their term
# counts and labels (2).
LIST_QUERIES = 2 + 6 + 2 + 2 + 2 + 2 + 3 + 2 + 4 + 2
# Queries per card read, measured 2026-09-19 and pinned the same way: the savepoint pair (2);
# the session (6) and the caller's tenant and locale (2), as above; the obligation with its
# instrument, level, duty type and verifier (1); its titles, its instrument's titles, its
# versions, their summaries, its tags and the provisions it cites (6); the scope (own terms,
# instrument regimes, the terms: 3); one label query each for terms, tags, duty types and
# levels (4); the dimensions with their term counts and labels (2); the footprint and its
# restricting dimensions (2); the relations, the titles of what they point at and the
# relation types' labels (3).
DETAIL_QUERIES = 2 + 6 + 2 + 1 + 6 + 3 + 4 + 2 + 2 + 3


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
    outside by its service and c by its instrument's regime. The first one is complete: it
    states its duty, cites a provision and is filed beside another obligation."""
    lvm = build.instrument(key="lvm", short_name="LVM", regime="regime:securities")
    esma = build.instrument(key="esma", short_name="ESMA guidelines", regime="regime:securities", level="eu_guidance", binding=False)
    lfd = build.instrument(key="lfd", short_name="LFD", regime="regime:insurance")
    plain = build.instrument(key="plain", short_name="Plain")
    chapter = build.provision(lvm, key="lvm/9", ref_label="9 kap.")
    appropriateness = build.obligation(
        lvm,
        key="obl-a-appropriateness",
        titles={"sv": "Bedöm om tjänsten passar kunden", "en": "Assess appropriateness"},
        ref_label="9 kap.",
        terms=("service_type:non_advised", "service_type:execution_only", "account_type:isk"),
        tags=("appropriateness",),
        cites=(chapter,),
        versions=((None, {"sv": "Bedöm passandet.", "en": "Assess the fit."}),),
        last_verified_at=datetime.datetime(2026, 6, 30, 8, 0, tzinfo=datetime.UTC),
        product_scope="Investment services",
        trigger_frequency="Before every order",
        retention="5 years",
        sanction_exposure="FI remark, warning or sanction fee",
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
    guidance = build.obligation(esma, key="obl-e-guidance", titles={"en": "Make warnings prominent"}, terms=ALL_SERVICES)
    build.obligation(plain, key="obl-f-unscoped", titles={"en": "Keep a register"}, duty_type="record_keeping")
    build.relate(appropriateness, guidance)


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
        # Captured as the console handler writes it (settings.LOGGING): its filter, then the formatter.
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
        for written in ("fraud", "branch", "twelve", "advice", "?", "q=", "term="):
            self.assertNotIn(written, lines[0], "no search text and no query string")
        self.assertNotIn("/api/v1/obligations", lines[0], "the route pattern, never the path the caller asked for")
        line = json.loads(lines[0])
        self.assertNotIn("request", line)
        self.assertEqual(line["message"], "422 GET api/v1/obligations")
        self.assertEqual(line["request_id"], "req-obligations-1", "Django logs after the middleware; the id still travels")

    def test_every_row_is_validated_before_it_is_answered(self) -> None:
        # A value the database or a later change gets wrong fails the read: the caller gets the
        # one problem shape (config.api), never a 200 and never the value, and the log names
        # the validation error by its type, never its message (apps.shared.logging). A row
        # built without validation fails the same way: the page validates every row it holds.
        # The type is asserted because a 500 for any other reason would prove nothing.
        refused_by_validation = f"{ValidationError.__module__}.{ValidationError.__qualname__}"
        unchecked = ObligationRow.model_construct(id="unchecked-row-id", stable_key=None)
        cases = (
            ("in_force", mock.Mock(version_number="many-versions", effective_from=None), "many-versions"),
            ("obligation_page", ([unchecked], 1), "unchecked-row-id"),
        )
        for name, value, malformed in cases:
            with self.subTest(name):
                with (
                    mock.patch.object(reading, name, return_value=value),
                    self.assertLogs("config.api", "ERROR") as logs,
                    self.assertLogs("django.request", "ERROR") as django_logs,
                ):
                    response = self.get({})
                self.assertEqual((response.status_code, response.json().get("code")), (500, "internal_error"))
                self.assertNotIn(malformed, response.content.decode())
                line = JsonFormatter().format(logs.records[0])
                self.assertTrue(json.loads(line)["exc_info"].endswith(refused_by_validation), line)
                for written in (line, JsonFormatter().format(django_logs.records[0])):
                    self.assertNotIn(malformed, written)

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


class ObligationDetailTests(TestCase):
    """`GET /obligations/{id}` (INV-03..INV-06): the duty and its facets, the version in
    force on a date with the whole history beside it, the text in the reader's language,
    the provisions it cites, the obligations beside it and where it came from."""

    tenant: Tenant
    reader: User
    appropriateness: Obligation
    research: Obligation
    heavy: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="detail-a")
        set_footprint(cls.tenant, FOOTPRINT)
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        seed_obligations()
        cls.appropriateness = Obligation.objects.get(stable_key="obl-a-appropriateness")
        cls.research = Obligation.objects.get(stable_key="obl-d-research")
        # A record carrying more of everything: the query count must not notice.
        lvm = cls.appropriateness.instrument
        cls.heavy = build.obligation(
            lvm,
            key="obl-g-heavy",
            titles={"sv": "Tung skyldighet", "en": "A heavy duty"},
            terms=ALL_SERVICES,
            tags=("advice", "costs", "disclosure"),
            cites=(Provision.objects.get(stable_key="lvm/9"), build.provision(lvm, key="lvm/10", ref_label="10 kap.")),
            versions=((None, {"en": "One."}), (D(2025, 1, 1), {"en": "Two."}), (CHANGE_DAY, {"en": "Three."})),
        )
        build.relate(cls.heavy, cls.appropriateness)
        build.relate(cls.heavy, cls.research)

    def get(self, obligation: Obligation, params: dict[str, Any] | None = None) -> Any:
        return self.client.get(f"{URL}/{obligation.id}", params or {}, **sign_in(self.reader, tenant=self.tenant))

    def card(self, obligation: Obligation, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.get(obligation, params)
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def test_the_card_states_the_duty_its_facets_and_where_it_comes_from(self) -> None:
        card = self.card(self.appropriateness, {"asOf": EARLY.isoformat()})
        self.assertEqual((card["id"], card["stableKey"], card["refLabel"]), (str(self.appropriateness.id), "obl-a-appropriateness", "9 kap."))
        # The reader reads en; the title was written in sv, so en is a labelled machine translation.
        self.assertEqual(card["title"], {"text": "Assess appropriateness", "language": "en", "isOriginal": False, "isMachine": True})
        self.assertEqual(
            card["instrument"],
            {
                "key": "lvm",
                "shortName": "LVM",
                "name": {"text": "LVM", "language": "en", "isOriginal": True, "isMachine": False},
                "officialRef": "LVM",
                "implementsNote": "",
            },
        )
        self.assertEqual((card["regime"]["key"], card["bindingLevel"]["key"], card["binding"]), ("securities", "act", True))
        self.assertEqual(card["dutyType"]["key"], "conduct")
        self.assertEqual(
            (card["productScope"], card["triggerFrequency"], card["retention"], card["sanctionExposure"]),
            ("Investment services", "Before every order", "5 years", "FI remark, warning or sanction fee"),
        )
        self.assertEqual([tag["key"] for tag in card["tags"]], ["appropriateness"])
        scope = {entry["dimension"]["key"]: entry for entry in card["scope"]}
        self.assertEqual([term["key"] for term in scope["service_type"]["terms"]], ["non_advised", "execution_only"])
        self.assertEqual([term["key"] for term in scope["regime"]["terms"]], ["securities"], "the instrument's regime is inherited")
        self.assertEqual((scope["client_category"]["terms"], scope["client_category"]["allSelected"]), ([], False))
        self.assertEqual((card["inFootprint"], card["outsideReason"]), (True, []))
        chapter = Provision.objects.get(stable_key="lvm/9")
        self.assertEqual(card["provisions"], [{"id": str(chapter.id), "refLabel": "9 kap.", "path": "LVM > 9 kap."}])
        guidance = Obligation.objects.get(stable_key="obl-e-guidance")
        self.assertEqual(
            card["related"],
            [
                {
                    "id": str(guidance.id),
                    "title": {"text": "Make warnings prominent", "language": "en", "isOriginal": True, "isMachine": False},
                    "instrument": {"key": "esma", "shortName": "ESMA guidelines"},
                    "binding": False,
                    "relation": {"key": "related", "kind": None, "label": "Related"},
                }
            ],
        )
        provenance = card["provenance"]
        self.assertEqual((provenance["createdOrigin"], provenance["createdModel"]), ("user", ""))
        self.assertIsNone(provenance["verifiedBy"], "a record nobody has re-verified names no verifier")
        self.assertEqual(provenance["lastVerifiedAt"], "2026-06-30T08:00:00Z")
        self.assertEqual((provenance["sourceUrl"], provenance["sourceLabel"]), (build.SOURCE_URL, "LVM, 9 kap."))
        self.assertIsNotNone(provenance["createdAt"])
        self.assertTrue({"tone", "pill", "color", "colour"}.isdisjoint(field_names(card)))

    def test_a_record_outside_the_footprint_is_still_read_and_says_why_it_is_outside(self) -> None:
        # The card is reachable by address whatever the footprint hides from the list (FP-03).
        card = self.card(Obligation.objects.get(stable_key="obl-c-insurance"))
        self.assertFalse(card["inFootprint"])
        self.assertEqual(
            [(reason["dimension"]["key"], [term["key"] for term in reason["terms"]]) for reason in card["outsideReason"]],
            [("regime", ["insurance"])],
        )

    def test_as_of_returns_the_version_in_force_and_says_when_each_one_ended(self) -> None:
        before = self.card(self.research, {"asOf": EARLY.isoformat()})
        self.assertEqual(before["version"]["versionNumber"], 1)
        self.assertEqual(
            before["versions"],
            [
                {
                    "versionNumber": 1,
                    "effectiveFrom": {"date": "2025-01-01", "precision": "day"},
                    "effectiveTo": {"date": "2026-09-30", "precision": "day"},
                    "approvedAt": None,
                },
                {
                    "versionNumber": 2,
                    "effectiveFrom": {"date": "2026-10-01", "precision": "day"},
                    "effectiveTo": None,
                    "approvedAt": None,
                },
            ],
            "a version runs until the day before the next one takes effect; nothing stores an end date",
        )
        self.assertEqual(before["summary"]["text"], "Research is paid from own resources.")
        on = self.card(self.research, {"asOf": CHANGE_DAY.isoformat()})
        self.assertEqual((on["version"]["versionNumber"], on["summary"]["text"]), (2, "Research may be paid jointly."))
        not_yet = self.card(self.research, {"asOf": "2024-12-31"})
        self.assertIsNone(not_yet["version"], "no version was in force yet")
        self.assertIsNone(not_yet["summary"])
        self.assertEqual(not_yet["translations"], [])
        self.assertEqual(len(not_yet["versions"]), 2, "the version list is the record's history, not the date's")
        self.assertEqual(self.get(self.research, {"asOf": "30 June"}).status_code, 422)

    def test_a_same_day_correction_leaves_the_corrected_version_without_an_end(self) -> None:
        # A correction filed the day a version took effect (logic.in_force: the later number
        # wins) must not give the first version an end date before its own start.
        corrected = build.obligation(
            self.appropriateness.instrument,
            key="obl-h-corrected",
            titles={"sv": "Rättad", "en": "Corrected"},
            terms=ALL_SERVICES,
            versions=((CHANGE_DAY, {"en": "First wording."}), (CHANGE_DAY, {"en": "Corrected wording."})),
        )
        card = self.card(corrected, {"asOf": CHANGE_DAY.isoformat()})
        self.assertEqual(card["version"]["versionNumber"], 2, "the correction is the version in force")
        self.assertEqual(
            [(row["versionNumber"], row["effectiveTo"]) for row in card["versions"]],
            [(1, None), (2, None)],
            "no end date before a start date",
        )

    def test_the_summary_comes_in_the_readers_language_with_every_translation_beside_it(self) -> None:
        card = self.card(self.appropriateness)
        self.assertEqual(card["summary"], {"text": "Assess the fit.", "language": "en", "isOriginal": False, "isMachine": True})
        self.assertEqual(
            card["translations"],
            [
                {"text": "Assess the fit.", "language": "en", "isOriginal": False, "isMachine": True},
                {"text": "Bedöm passandet.", "language": "sv", "isOriginal": True, "isMachine": False},
            ],
            "every language of the version in force, so the card can offer the original",
        )

    def test_an_address_with_nothing_at_it_answers_404_and_a_malformed_one_422(self) -> None:
        missing = self.client.get(f"{URL}/{uuid.uuid4()}", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((missing.status_code, missing.json()["code"]), (404, "not_found"))
        self.assertEqual(missing.json()["detail"], reading.NOT_FOUND)
        self.assertEqual(missing.headers["Content-Type"], "application/problem+json")
        malformed = self.client.get(f"{URL}/not-a-uuid", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(malformed.status_code, 422)

    def test_a_malformed_value_fails_the_read_instead_of_reaching_the_caller(self) -> None:
        # The card is validated as it is built, natively by pydantic. A value the database or
        # a later change gets wrong is answered as the one problem shape, never as a 200 and
        # never as the value itself, and the log names the validation error by its type.
        refused_by_validation = f"{ValidationError.__module__}.{ValidationError.__qualname__}"
        with (
            mock.patch.object(reading, "localized", return_value="not-a-localized-text"),
            self.assertLogs("config.api", "ERROR") as logs,
            self.assertLogs("django.request", "ERROR") as django_logs,
        ):
            response = self.get(self.appropriateness)
        self.assertEqual((response.status_code, response.json().get("code")), (500, "internal_error"))
        self.assertNotIn("not-a-localized-text", response.content.decode())
        line = JsonFormatter().format(logs.records[0])
        self.assertTrue(json.loads(line)["exc_info"].endswith(refused_by_validation), line)
        for written in (line, JsonFormatter().format(django_logs.records[0])):
            self.assertNotIn("not-a-localized-text", written)

    def test_the_query_count_does_not_grow_with_the_record(self) -> None:
        for obligation in (self.appropriateness, self.heavy):
            headers = sign_in(self.reader, tenant=self.tenant)
            with self.subTest(key=obligation.stable_key), self.assertNumQueries(DETAIL_QUERIES):
                response = self.client.get(f"{URL}/{obligation.id}", {"asOf": EARLY.isoformat()}, **headers)
            self.assertEqual(response.status_code, 200, response.content)

    def test_a_person_needs_library_read_and_a_key_needs_library_read_scope(self) -> None:
        no_scope = factories.api_key(self.tenant, scopes=(perms.SCOPE_CHANGES_WRITE,))
        key = factories.api_key(self.tenant, scopes=(perms.SCOPE_LIBRARY_READ,))
        without = user_principal(permissions={perms.CASES_READ}, tenant_id=self.tenant.id)
        for path in (f"{URL}/{self.research.id}", f"{URL}/{self.research.id}/diff"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
                with stub_session(without):
                    refused = self.client.get(path, HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
                self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.LIBRARY_READ))
                refused = self.client.get(path, HTTP_X_API_KEY=no_scope.plain_key)
                self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.SCOPE_LIBRARY_READ))
                self.assertEqual(self.client.get(path, HTTP_X_API_KEY=key.plain_key).status_code, 200)


class ObligationDiffTests(TestCase):
    """`GET /obligations/{id}/diff` (INV-04, INV-05, AC-INV1): what changed between two
    versions, in a language both of them have, with both effective dates named."""

    tenant: Tenant
    reader: User
    research: Obligation
    single: Obligation
    apart: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="diff-a")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        lvm = build.instrument(key="lvm", short_name="LVM", regime="regime:securities")
        cls.research = build.obligation(
            lvm,
            key="obl-d-research",
            titles={"en": "Pay for research only under the permitted models"},
            versions=(
                (D(2025, 1, 1), {"sv": "Analys betalas med egna medel.", "en": "Research is paid from own resources."}),
                (
                    CHANGE_DAY,
                    {
                        "sv": "Analys betalas med egna medel. Institutet bedömer analysen varje år.",
                        "en": "Research is paid from own resources. The institution assesses the research every year.",
                    },
                ),
            ),
        )
        cls.single = build.obligation(lvm, key="obl-single")
        cls.apart = build.obligation(
            lvm, key="obl-apart", versions=((None, {"sv": "Endast svenska."}), (D(2026, 1, 1), {"en": "English only."}))
        )

    def get(self, obligation: Obligation, params: dict[str, Any] | None = None) -> Any:
        return self.client.get(f"{URL}/{obligation.id}/diff", params or {}, **sign_in(self.reader, tenant=self.tenant))

    def diff(self, obligation: Obligation, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.get(obligation, params)
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def test_the_default_compares_the_latest_version_with_the_one_before_it(self) -> None:
        body = self.diff(self.research)
        self.assertEqual((body["fromVersion"], body["toVersion"]), (1, 2))
        self.assertEqual(body["fromEffective"], {"date": "2025-01-01", "precision": "day"})
        self.assertEqual(body["toEffective"], {"date": "2026-10-01", "precision": "day"})
        self.assertEqual((body["language"], body["isMachine"]), ("en", True), "the reader reads the machine translation")
        self.assertEqual(
            body["segments"],
            [
                {"op": "equal", "text": "Research is paid from own resources."},
                {"op": "insert", "text": "The institution assesses the research every year."},
            ],
        )

    def test_a_language_can_be_asked_for_and_the_reading_order_answers_when_it_is_not_there(self) -> None:
        swedish = self.diff(self.research, {"lang": "sv"})
        self.assertEqual((swedish["language"], swedish["isMachine"]), ("sv", False), "the original, written by a person")
        self.assertEqual(
            swedish["segments"],
            [{"op": "equal", "text": "Analys betalas med egna medel."}, {"op": "insert", "text": "Institutet bedömer analysen varje år."}],
        )
        self.assertEqual(self.diff(self.research, {"lang": "fi"})["language"], "en", "a language no version has falls back")
        self.assertEqual(self.get(self.research, {"lang": "x" * 9}).status_code, 422)

    def test_two_versions_named_by_number(self) -> None:
        same = self.diff(self.research, {"from": 1, "to": 1})
        self.assertEqual((same["fromVersion"], same["toVersion"]), (1, 1))
        self.assertEqual([segment["op"] for segment in same["segments"]], ["equal"], "unchanged is never a change")
        backwards = self.diff(self.research, {"from": 2, "to": 1})
        self.assertEqual([segment["op"] for segment in backwards["segments"]], ["equal", "delete"])

    def test_a_version_number_that_is_not_there_an_id_that_is_not_there_and_one_version_only(self) -> None:
        unknown = self.get(self.research, {"from": 9})
        self.assertEqual((unknown.status_code, unknown.json()["code"]), (422, "unknown_key"))
        self.assertIn("9", unknown.json()["detail"])
        self.assertEqual(self.get(self.research, {"from": 0}).status_code, 422, "a version number starts at 1")
        only_one = self.get(self.single)
        self.assertEqual((only_one.status_code, only_one.json()["code"]), (422, "validation_error"))
        missing = self.client.get(f"{URL}/{uuid.uuid4()}/diff", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((missing.status_code, missing.json()["code"]), (404, "not_found"))

    def test_versions_sharing_no_language_are_refused_and_no_summary_reaches_the_logs(self) -> None:
        lines: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                lines.append(JsonFormatter().format(record))

        handler = Capture()
        handler.addFilter(RequestIdLogFilter())
        request_logger = logging.getLogger("django.request")
        request_logger.addHandler(handler)
        try:
            refused = self.get(self.apart)
        finally:
            request_logger.removeHandler(handler)
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "validation_error"))
        self.assertEqual(len(lines), 1, "the refusal is logged")
        for written in ("Endast", "svenska", "English only", str(self.apart.id)):
            self.assertNotIn(written, lines[0], "no library text and no record the reader asked for")
        self.assertEqual(json.loads(lines[0])["message"], "422 GET api/v1/obligations/<obligation_id>/diff")


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
            self.private = build.obligation(
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

    def test_another_tenants_private_obligation_has_no_address_either(self) -> None:
        # A record the reader cannot see is not there: the same 404 as an id that never
        # existed, so no address can be probed for what a bank holds privately (INV-07).
        with as_app_role():
            for path in (f"{URL}/{self.private.id}", f"{URL}/{self.private.id}/diff"):
                with self.subTest(path=path):
                    refused = self.client.get(path, HTTP_X_API_KEY=self.key_a.plain_key)
                    self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"))
                    self.assertEqual(refused.json()["detail"], reading.NOT_FOUND)
            own = self.client.get(f"{URL}/{self.private.id}", HTTP_X_API_KEY=self.key_b.plain_key)
            self.assertEqual((own.status_code, own.json()["stableKey"]), (200, "obl-b-private"))


class AuthorityListTests(TestCase):
    """`GET /authorities` (FP-04, AGT-02, ruling E): the short reference list the watch
    feed's authority filter, the console's Change facts queue and an agent run all read.
    A library fact, the same for every bank and for every key."""

    tenant: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        seed_authorities()
        cls.tenant = factories.tenant(slug="authority-reader")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def get(self, headers: Any) -> Any:
        return self.client.get("/api/v1/authorities", **headers)

    def test_every_authority_with_its_jurisdiction(self) -> None:
        response = self.get(sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["key"]: row for row in response.json()}
        self.assertIn("fi", rows)
        self.assertEqual(rows["fi"]["shortName"], "FI")
        self.assertEqual(rows["fi"]["name"], "Finansinspektionen")
        self.assertEqual(rows["fi"]["url"], "https://www.fi.se/")
        self.assertEqual(rows["fi"]["jurisdiction"], {"key": "se", "kind": "country", "label": "Sweden"})
        self.assertEqual(rows["esma"]["jurisdiction"]["kind"], "supranational")
        self.assertEqual([row["key"] for row in response.json()], sorted(rows), "ordered by the key a filter stores")
        self.assertEqual(sorted(rows["fi"]), ["id", "jurisdiction", "key", "name", "shortName", "url"])

    def test_one_query_for_the_rows_and_one_for_their_labels(self) -> None:
        headers = sign_in(self.reader, tenant=self.tenant)
        # The savepoint pair (2), the session (6), the caller's locale and the tenant's
        # default language (2), the authorities with their jurisdictions (1) and one query
        # for every jurisdiction label (1).
        with self.assertNumQueries(2 + 6 + 2 + 1 + 1):
            self.assertEqual(self.get(headers).status_code, 200)

    def test_a_person_needs_library_read_and_a_key_needs_the_scope(self) -> None:
        self.assertEqual(self.get({}).status_code, 401)
        without = user_principal(permissions={perms.CASES_READ}, tenant_id=self.tenant.id)
        with stub_session(without):
            refused = self.get({"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"})
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.LIBRARY_READ))
        no_scope = factories.api_key(self.tenant, scopes=(perms.SCOPE_CHANGES_WRITE,))
        self.assertEqual(self.get({"HTTP_X_API_KEY": no_scope.plain_key}).status_code, 403)
        key = factories.api_key(self.tenant, scopes=(perms.SCOPE_LIBRARY_READ,))
        self.assertEqual(self.get({"HTTP_X_API_KEY": key.plain_key}).status_code, 200)

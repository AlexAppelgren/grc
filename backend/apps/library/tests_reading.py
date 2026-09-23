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
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError

from apps.agents import testing as agents_testing
from apps.identity.models import User
from apps.library import reading
from apps.library import testing as build
from apps.library.models import Instrument, Obligation, ObligationTerm, Provision
from apps.library.reading import instrument_scope_term_ids, instrument_scopes, obligation_scopes, scope_term_ids
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
# (own terms, the obligations' instrument ids, the instruments' own regime pairs, the
# instruments' regime terms, the terms: 5, chunk3-rest-T13 — obligation_scopes() now
# inherits through instrument_scopes() so the two verdicts share one rule, at the cost of
# two more queries than the union it replaced); the tags of the page and their rows (2); one
# label query each for terms, tags, duty types, levels and, since tax-watched-inventory
# (2026-09-23, FP-04), the instruments' jurisdictions a row now names (5); the dimensions
# with their term counts and labels (2).
LIST_QUERIES = 2 + 6 + 2 + 2 + 2 + 2 + 5 + 2 + 5 + 2
# Queries per card read, measured 2026-09-19 and pinned the same way: the savepoint pair (2);
# the session (6) and the caller's tenant and locale (2), as above; the obligation with its
# instrument, level, duty type and verifier (1); its titles, its instrument's titles, its
# versions, their summaries, its tags and the provisions it cites (6); the scope (5, as
# above); one label query each for terms, tags, duty types and levels (4); the dimensions
# with their term counts and labels (2); the footprint and its restricting dimensions (2);
# the relations, the titles of what they point at and the relation types' labels (3).
DETAIL_QUERIES = 2 + 6 + 2 + 1 + 6 + 5 + 4 + 2 + 2 + 3
# Who confirmed a version the library was seeded with: nobody, since nobody approved it.
SEEDED = {"verifiedOrigin": "", "confirmedByAgent": None, "proposedByAgent": None}


def seed_reference() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_taxonomy_terms()
    seed_authorities()


def set_footprint(tenant: Tenant, refs: tuple[str, ...]) -> None:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        for ref in refs:
            FootprintTerm.objects.create(tenant=tenant, term=build.term(ref))


def seed_obligations() -> None:
    """Six shared obligations. By tenant A's footprint: a, d, e and f are inside; b is
    outside by its service and c by its instrument's regime. The first one is complete: it
    states its duty, cites a provision and is filed beside another obligation. f names no
    term of its own and carries only its instrument's regime, which every instrument has
    (D-39)."""
    lvm = build.instrument(key="lvm", short_name="LVM", regime="regime:securities")
    esma = build.instrument(key="esma", short_name="ESMA guidelines", regime="regime:securities", level="eu_guidance", binding=False)
    lfd = build.instrument(key="lfd", short_name="LFD", regime="regime:insurance")
    plain = build.instrument(key="plain", short_name="Plain", regime="regime:securities")
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
        response = self.get({"footprint": "all", **params})
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
        self.assertEqual(
            [term["key"] for term in scope["jurisdiction"]["terms"]], ["se"], "the instrument's jurisdiction is derived, never stored"
        )
        self.assertEqual(row["version"], {"versionNumber": 1, "effectiveFrom": None, **SEEDED})
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
        everything = self.get({"footprint": "all"}).json()
        self.assertEqual(everything["total"], 6)
        rows = {row["stableKey"]: row for row in everything["items"]}
        # The SQL filter and the Python verdict are one rule: what the default hides is what
        # the verdict calls outside.
        self.assertEqual({key for key, row in rows.items() if row["inFootprint"]}, set(keys(self.get({}))))
        advice = rows["obl-b-advice"]["outsideReason"]
        self.assertEqual([(r["dimension"]["key"], [t["key"] for t in r["terms"]]) for r in advice], [("service_type", ["advice"])])
        insurance = rows["obl-c-insurance"]["outsideReason"]
        self.assertEqual([(r["dimension"]["key"], [t["key"] for t in r["terms"]]) for r in insurance], [("regime", ["insurance"])])
        self.assertEqual(rows["obl-f-unscoped"]["outsideReason"], [], "a record with no terms of its own is judged by its regime alone")

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
        self.assertEqual(before["version"], {"versionNumber": 1, "effectiveFrom": {"date": "2025-01-01", "precision": "day"}, **SEEDED})
        self.assertEqual(before["upcomingVersion"], {"versionNumber": 2, "effectiveFrom": {"date": "2026-10-01", "precision": "day"}, **SEEDED})
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
                response = self.get({"footprint": "all"}, headers)
                research = next(row for row in response.json()["items"] if row["stableKey"] == "obl-d-research")
                self.assertEqual(research["version"]["versionNumber"], expected)

    def test_every_filter(self) -> None:
        self.assertEqual(keys(self.get({"instrument": "esma"})), ["obl-e-guidance"])
        self.assertEqual(keys(self.get({"instrument": "no-such-instrument"})), [], "an unknown key matches nothing")
        self.assertEqual(keys(self.get({"dutyType": "reporting"})), ["obl-d-research"])
        self.assertEqual(keys(self.get({"term": "service_type:execution_only"})), ["obl-a-appropriateness", "obl-e-guidance"])
        self.assertEqual(
            keys(self.get({"term": "regime:securities"})),
            ["obl-a-appropriateness", "obl-d-research", "obl-e-guidance", "obl-f-unscoped"],
            "the regime is inherited",
        )
        self.assertEqual(keys(self.get({"term": ["service_type:execution_only", "account_type:isk"]})), ["obl-a-appropriateness"], "every term must match")
        self.assertEqual(keys(self.get({"term": "regime:insurance", "footprint": "all"})), ["obl-c-insurance"])
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
        params: dict[str, Any] = {"footprint": "all", "limit": settings.API_PAGE_SIZE_MAX, "asOf": EARLY.isoformat()}
        with self.assertNumQueries(LIST_QUERIES):
            response = self.client.get(URL, params, **headers)
        self.assertEqual(len(response.json()["items"]), settings.API_PAGE_SIZE_MAX)
        # CPU time on the request thread, the best of fifteen: what the read costs, without
        # the waits a loaded machine adds, so the bound holds on a busy CI runner too. The
        # suite runs under coverage, whose tracer is paused for the timed requests only; the
        # one above stays traced, so coverage is unchanged.
        #
        # Fifteen rather than five because the minimum of five is too noisy to read on this
        # machine: measured 2026-09-21 over fifteen calls, the samples ran from 78 ms to
        # 312 ms in steps of 15.6 ms — Windows reports thread CPU at the scheduler's tick —
        # so a page that really costs 80 to 140 ms produced a best-of-five of 266 ms and
        # failed the budget once in two parallel runs. More samples estimate the
        # uncontended cost better; they cannot rescue a page that is genuinely over it.
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(15):
                started = time.thread_time()
                self.client.get(URL, params, **headers)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)


class JurisdictionDerivationTests(TestCase):
    """FP-04, D-28, D-29, D-38: the jurisdictions an instrument's rules reach are derived by
    the one scope rule at match time, from the mirror link and the jurisdiction's parent, and
    never stored. A Union rule reaches the Union and every country whose parent it is,
    Norway included; a national rule its own country; a standards body's jurisdiction, which
    no term mirrors, nothing. The SQL twins agree, and an obligation carries each term once."""

    tenant: Tenant
    reader: User
    instruments: dict[str, Instrument]
    obligations: dict[str, Obligation]

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="derived-jurisdictions")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.instruments = {
            key: build.instrument(key=f"derived-{key}", regime="regime:securities", jurisdiction=key) for key in ("eu", "se", "dk", "no", "intl")
        }
        cls.obligations = {key: build.obligation(instrument, key=f"obl-derived-{key}") for key, instrument in cls.instruments.items()}
        # Its own regime term as well as its instrument's: the review finding behind the
        # merge's de-duplication.
        cls.obligations["twice"] = build.obligation(cls.instruments["se"], key="obl-derived-twice", terms=("regime:securities",))

    def derived(self, scope: dict[str, list[Any]]) -> list[str]:
        return [term.key for term in scope.get("jurisdiction", [])]

    def test_a_union_rule_reaches_every_member_country_and_norway_and_a_national_rule_its_own(self) -> None:
        scopes = instrument_scopes([instrument.id for instrument in self.instruments.values()])
        self.assertEqual(
            {key: self.derived(scopes[instrument.id]) for key, instrument in self.instruments.items()},
            {"eu": ["eu", "se", "dk", "no", "fi"], "se": ["se"], "dk": ["dk"], "no": ["no"], "intl": []},
        )
        self.assertEqual({key: [term.key for term in scopes[i.id]["regime"]] for key, i in self.instruments.items()}, {key: ["securities"] for key in self.instruments})
        obligations = obligation_scopes([obligation.id for obligation in self.obligations.values()])
        self.assertEqual(self.derived(obligations[self.obligations["eu"].id]), ["eu", "se", "dk", "no", "fi"], "an obligation inherits it")
        self.assertFalse(ObligationTerm.objects.filter(term__jurisdiction__isnull=False).exists(), "nothing is stored")

    def test_an_inherited_term_the_obligation_already_carries_is_listed_once(self) -> None:
        scope = obligation_scopes([self.obligations["twice"].id])[self.obligations["twice"].id]
        self.assertEqual([term.key for term in scope["regime"]], ["securities"])

    def test_the_scope_rule_and_its_sql_twins_agree_on_every_derived_term(self) -> None:
        instruments = instrument_scopes()
        sql = {row.id: set(row.term_ids) for row in Instrument.objects.annotate(term_ids=instrument_scope_term_ids())}
        self.assertEqual({key: {term.id for terms in instruments[key].values() for term in terms} for key in sql}, sql)
        obligations = obligation_scopes()
        sql = {row.id: set(row.term_ids) for row in Obligation.objects.annotate(term_ids=scope_term_ids())}
        self.assertEqual({key: {term.id for terms in obligations[key].values() for term in terms} for key in sql}, sql)

    def test_the_scope_block_and_the_outside_reason_show_the_derived_terms(self) -> None:
        """The reading D-28 and D-29 give: the derived terms are the record's scope as the
        rule sees it, so the card lists them and names them when they hide the record."""
        set_footprint(self.tenant, ("jurisdiction:dk",))
        response = self.client.get(URL, {"footprint": "all"}, **sign_in(self.reader, tenant=self.tenant))
        rows = {row["stableKey"]: row for row in response.json()["items"]}
        union = {entry["dimension"]["key"]: entry for entry in rows["obl-derived-eu"]["scope"]}["jurisdiction"]
        self.assertEqual(([term["key"] for term in union["terms"]], union["allSelected"]), (["eu", "se", "dk", "no", "fi"], True))
        self.assertEqual((rows["obl-derived-eu"]["inFootprint"], rows["obl-derived-dk"]["inFootprint"]), (True, True))
        swedish = rows["obl-derived-se"]
        self.assertEqual(
            (swedish["inFootprint"], [(r["dimension"]["key"], [t["key"] for t in r["terms"]]) for r in swedish["outsideReason"]]),
            (False, [("jurisdiction", ["se"])]),
        )
        self.assertTrue(rows["obl-derived-intl"]["inFootprint"], "a jurisdiction no term mirrors hides nothing")


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
                    **SEEDED,
                },
                {
                    "versionNumber": 2,
                    "effectiveFrom": {"date": "2026-10-01", "precision": "day"},
                    "effectiveTo": None,
                    "approvedAt": None,
                    **SEEDED,
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
        self.assertEqual((body["fromConfirmation"], body["toConfirmation"]), (SEEDED, SEEDED), "seeded: nobody approved either")
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


class MachineConfirmedVersionTests(TestCase):
    """Who confirmed each version travels with that version (INV-05, INV-06, PRO-02, D-62):
    on the list's version and upcoming version, on the card's version list and provenance,
    and on both sides of the diff, so wording an independent agent confirmed is labelled
    wherever it shows, including before it takes effect. A person's re-verification stamp
    and a version's approval are both reported as stored, with their times; which one a
    screen reads is the screen's rule (obligation-presentation.ts)."""

    tenant: Tenant
    reader: User
    editor: User
    obligation: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="machine-a")
        set_footprint(cls.tenant, FOOTPRINT)
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        cls.obligation = build.obligation(
            build.instrument(key="lvm", short_name="LVM", regime="regime:securities"),
            key="obl-machine-confirmed",
            titles={"en": "A duty the agents keep current"},
            terms=("service_type:non_advised",),
            versions=((D(2025, 1, 1), {"en": "The duty as it first read."}),),
        )

    def agents_apply(self, effective_from: datetime.date) -> dict[str, Any]:
        """One agent proposes a new version and an independent agent confirms it, through the
        queue as production does (PRO-S13); answers the three facts the version should carry."""
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        proposer = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        confirmer = agents_testing.reviewer_api_key()
        body = {
            "kind": "new_obligation_version",
            "title": "Keep the wording current with the source",
            "targetType": "obligation",
            "targetId": str(self.obligation.id),
            "payload": {
                "summaries": {"en": f"The duty as the agents read it from {effective_from.isoformat()}."},
                "originalLanguage": "en",
                "isMachine": True,
                "effectiveFrom": effective_from.isoformat(),
                "effectiveFromPrecision": "day",
            },
            "fieldSources": {"summaries.en": build.SOURCE_URL, "effectiveFrom": build.SOURCE_URL},
            # An agent files under an open run of its own (AGT-01).
            "agentRunId": str(agents_testing.platform_run(key=proposer).id),
        }
        created = self.client.post("/api/v1/proposals", body, content_type="application/json", HTTP_X_API_KEY=proposer.plain_key)
        self.assertEqual(created.status_code, 201, created.content)
        approved = self.client.post(
            f"/api/v1/proposals/{created.json()['id']}/approve", {}, content_type="application/json", HTTP_X_API_KEY=confirmer.plain_key
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        return {
            "verifiedOrigin": "agent",
            "confirmedByAgent": {"id": str(confirmer.agent.id), "key": confirmer.agent.key},
            "proposedByAgent": {"id": str(proposer.agent.id), "key": proposer.agent.key},
        }

    def read(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.client.get(path, params, **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def queries_of(self, path: str, params: dict[str, Any]) -> int:
        headers = sign_in(self.reader, tenant=self.tenant)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(path, params, **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return len(queries.captured_queries)

    def test_a_persons_stamp_then_a_later_agent_confirmed_version_reads_agent(self) -> None:
        """Regression pin: a person re-verified the record, then agents confirmed a new
        version. The provenance names both agents, and the person's stamp beside it is older
        than that version's approval, so the stamp cannot vouch for wording no person saw."""
        stamped = self.client.post(
            f"{URL}/{self.obligation.id}/verifications", {"outcome": "no_change"}, content_type="application/json", **sign_in(self.editor, step_up=True)
        )
        self.assertEqual(stamped.status_code, 201, stamped.content)
        agents = self.agents_apply(D(2026, 1, 1))

        card = self.read(f"{URL}/{self.obligation.id}", {"asOf": EARLY.isoformat()})
        provenance, version = card["provenance"], card["version"]
        self.assertEqual(version["versionNumber"], 2, "the agents' version is the one in force")
        self.assertEqual({key: provenance[key] for key in agents}, agents)
        self.assertEqual({key: version[key] for key in agents}, agents)
        self.assertEqual(provenance["verifiedBy"]["name"], self.editor.name, "the stamp stays the person's own")
        self.assertLess(
            datetime.datetime.fromisoformat(provenance["lastVerifiedAt"]), datetime.datetime.fromisoformat(version["approvedAt"])
        )
        self.assertEqual({key: card["versions"][0][key] for key in agents}, SEEDED, "the seeded version is nobody's approval")

    def test_an_upcoming_agent_confirmed_version_is_labelled_on_the_list_the_card_and_the_diff(self) -> None:
        agents = self.agents_apply(CHANGE_DAY)

        rows = self.read(URL, {"asOf": EARLY.isoformat()})["items"]
        row = next(row for row in rows if row["stableKey"] == self.obligation.stable_key)
        self.assertEqual(row["version"], {"versionNumber": 1, "effectiveFrom": {"date": "2025-01-01", "precision": "day"}, **SEEDED})
        self.assertEqual(row["upcomingVersion"], {"versionNumber": 2, "effectiveFrom": {"date": "2026-10-01", "precision": "day"}, **agents})

        card = self.read(f"{URL}/{self.obligation.id}", {"asOf": EARLY.isoformat()})
        self.assertEqual({key: card["provenance"][key] for key in agents}, SEEDED, "the version in force was seeded")
        self.assertEqual({key: card["versions"][1][key] for key in agents}, agents, "labelled before it binds")
        self.assertIsNotNone(card["versions"][1]["approvedAt"])

        diff = self.read(f"{URL}/{self.obligation.id}/diff", {})
        self.assertEqual((diff["fromVersion"], diff["toVersion"]), (1, 2))
        self.assertEqual((diff["fromConfirmation"], diff["toConfirmation"]), (SEEDED, agents))

        on = self.read(f"{URL}/{self.obligation.id}", {"asOf": CHANGE_DAY.isoformat()})
        self.assertEqual({key: on["provenance"][key] for key in agents}, agents, "in force, the provenance names the agents too")

    def test_naming_the_agents_costs_no_query_per_version(self) -> None:
        card, page = f"{URL}/{self.obligation.id}", URL
        params = {"asOf": EARLY.isoformat()}
        before = (self.queries_of(card, params), self.queries_of(page, params))
        self.agents_apply(D(2026, 1, 1))
        self.agents_apply(CHANGE_DAY)
        self.assertEqual((self.queries_of(card, params), self.queries_of(page, params)), before)


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
                {"footprint": "all"},
                {"q": "private duty", "footprint": "all"},
                {"instrument": "bank-b-policy", "footprint": "all"},
                {"term": "service_type:non_advised", "footprint": "all"},
                {"dutyType": "conduct", "footprint": "all"},
            ):
                with self.subTest(params=params):
                    page = self.get(self.key_a, params)
                    self.assertNotIn("obl-b-private", [row["stableKey"] for row in page["items"]])
                    self.assertEqual(page["total"], len(page["items"]), "the total counts only what the tenant may see")
            self.assertEqual(self.get(self.key_a, {"footprint": "all"})["total"], 6)
            # The owner sees it beside the shared library, so the proof above is not vacuous.
            own = self.get(self.key_b, {"q": "private duty", "footprint": "all"})
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


# Queries per instrument list read, measured 2026-09-22 the same way as LIST_QUERIES: the
# savepoint pair (2); the session (6); the caller's tenant and locale (2); the footprint
# and its restricting dimensions (2); the count and the page with its titles (3); the
# scope (instrument_scopes(): the regime pairs, the regime terms: 2); one label query each
# for regimes, levels and jurisdictions (3); the dimensions with their term counts and
# labels (2); the obligation counts of the page (1).
INSTRUMENT_LIST_QUERIES = 2 + 6 + 2 + 2 + 3 + 2 + 3 + 2 + 1
# Queries per instrument card read, measured the same way: the savepoint pair (2); the
# session (6); the caller's tenant and locale (2); the instrument with its level,
# authority, jurisdiction, regime and verifier (1) and its titles (1); one label query
# each for the regime, the level and the jurisdiction (3); the lineage, both directions,
# and one label query for the relation types (3).
INSTRUMENT_DETAIL_QUERIES = 2 + 6 + 2 + 1 + 1 + 3 + 3


def seed_instruments() -> tuple[Instrument, Instrument, Instrument]:
    """Two Swedish instruments under the securities regime, one amending the other at a
    named place in each, and an insurance instrument outside tenant A's footprint with an
    obligation of its own, whose service alone would be inside it (INV-01, FP-03)."""
    fffs = build.instrument(
        key="fffs-instruments",
        short_name="FFFS 2017:2",
        regime="regime:securities",
        level="authority_regulation",
        authority="fi",
        in_force_from=D(2018, 1, 3),
        implements_note="MiFID II delegated directive (EU) 2017/593",
        last_verified_at=datetime.datetime(2026, 6, 30, 8, 0, tzinfo=datetime.UTC),
    )
    amendment = build.instrument(
        key="fffs-amendment-instruments",
        short_name="FFFS 2026:11",
        regime="regime:securities",
        level="authority_regulation",
        authority="fi",
        in_force_from=D(2026, 10, 1),
    )
    build.relate_instruments(
        amendment, fffs, relation="amends", note="Amends FFFS 2017:2, in force 1 October 2026.", from_ref="1 §", to_ref="9 kap. 6 §"
    )
    insurance = build.instrument(key="lfd-instruments", short_name="LFD", regime="regime:insurance", level="act")
    build.obligation(fffs, key="obl-instruments-inside", terms=("service_type:non_advised",))
    build.obligation(fffs, key="obl-instruments-outside", terms=("service_type:advice",))
    build.obligation(insurance, key="obl-instruments-insurance", terms=("service_type:non_advised",))
    return fffs, amendment, insurance


class InstrumentListTests(TestCase):
    tenant: Tenant
    reader: User
    fffs: Instrument
    amendment: Instrument
    insurance: Instrument

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="list-instruments")
        set_footprint(cls.tenant, FOOTPRINT)
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.fffs, cls.amendment, cls.insurance = seed_instruments()

    def get(self, params: dict[str, Any], headers: dict[str, Any] | None = None) -> Any:
        return self.client.get("/api/v1/instruments", params, **(headers if headers is not None else sign_in(self.reader, tenant=self.tenant)))

    def row(self, key: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.get({"footprint": "all", **params})
        self.assertEqual(response.status_code, 200, response.content)
        return next(row for row in response.json()["items"] if row["stableKey"] == key)

    def default_row(self, key: str) -> dict[str, Any]:
        """The row as the default, footprint-filtered list carries it: `row()` always asks
        for everything so a hidden instrument can be found at all, which would also lift
        the footprint filter `obligationCount` counts against."""
        response = self.get({})
        self.assertEqual(response.status_code, 200, response.content)
        return next(row for row in response.json()["items"] if row["stableKey"] == key)

    def test_a_row_carries_keys_kinds_and_facts_never_a_phrase(self) -> None:
        row = self.default_row("fffs-instruments")
        self.assertEqual(row["shortName"], "FFFS 2017:2")
        self.assertEqual(row["name"], {"text": "FFFS 2017:2", "language": "en", "isOriginal": True, "isMachine": False})
        self.assertEqual((row["level"]["key"], row["binding"]), ("authority_regulation", True))
        self.assertEqual(row["jurisdiction"]["key"], "se")
        self.assertEqual(row["authority"], {"key": "fi", "name": "Finansinspektionen", "shortName": "FI", "url": "https://www.fi.se/"})
        self.assertEqual(row["regime"], {"key": "securities", "kind": None, "label": "Securities"})
        self.assertEqual(row["officialRef"], "FFFS-INSTRUMENTS")
        self.assertEqual(row["inForceFrom"], {"date": "2018-01-03", "precision": "day"})
        self.assertIsNone(row["inForceTo"])
        self.assertEqual(row["implementsNote"], "MiFID II delegated directive (EU) 2017/593")
        self.assertEqual(row["obligationCount"], 1, "inside the footprint by default")
        self.assertTrue(row["inFootprint"])
        self.assertEqual(row["lastVerifiedAt"], "2026-06-30T08:00:00Z")
        self.assertEqual(row["sourceUrl"], build.SOURCE_URL)
        self.assertTrue({"tone", "pill", "color", "colour"}.isdisjoint(field_names(self.get({}).json())))

    def test_obligation_count_follows_the_footprint(self) -> None:
        inside = self.default_row("fffs-instruments")
        self.assertEqual(inside["obligationCount"], 1)
        everything = self.row("fffs-instruments", {"footprint": "all"})
        self.assertEqual(everything["obligationCount"], 2)

    def test_rows_outside_the_footprint_are_hidden_until_asked_for(self) -> None:
        self.assertEqual({row["stableKey"] for row in self.get({}).json()["items"]}, {"fffs-instruments", "fffs-amendment-instruments"})
        everything = self.get({"footprint": "all"}).json()
        self.assertEqual({row["stableKey"] for row in everything["items"]}, {"fffs-instruments", "fffs-amendment-instruments", "lfd-instruments"})
        insurance_row = next(row for row in everything["items"] if row["stableKey"] == "lfd-instruments")
        self.assertFalse(insurance_row["inFootprint"])

    def obligations(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        response = self.client.get("/api/v1/obligations", params, **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        return list(response.json()["items"])

    def test_the_instrument_and_obligation_footprint_verdicts_agree(self) -> None:
        # One rule, pinned across both reads and both ways (chunk3-rest-T13): an instrument
        # the footprint hides hides every obligation under it, even one whose own service is
        # inside, and every obligation the footprint shows sits under an instrument it shows,
        # which counts exactly the obligations the list filtered by it answers.
        instruments = {row["stableKey"]: row for row in self.get({"footprint": "all"}).json()["items"]}
        shown_instruments = {row["stableKey"]: row for row in self.get({}).json()["items"]}

        hidden = self.obligations({"instrument": "lfd-instruments", "footprint": "all"})
        self.assertFalse(instruments["lfd-instruments"]["inFootprint"])
        self.assertEqual([row["stableKey"] for row in hidden], ["obl-instruments-insurance"], "an empty list would prove nothing")
        self.assertEqual([row["inFootprint"] for row in hidden], [False])
        self.assertEqual(self.obligations({"instrument": "lfd-instruments"}), [])
        self.assertEqual(instruments["lfd-instruments"]["obligationCount"], len(hidden))

        shown = self.obligations({})
        self.assertTrue(shown, "an empty list would prove nothing")
        self.assertTrue({row["instrument"]["key"] for row in shown} <= set(shown_instruments))
        for key, row in shown_instruments.items():
            with self.subTest(instrument=key):
                self.assertTrue(row["inFootprint"])
                self.assertEqual(row["obligationCount"], len(self.obligations({"instrument": key})))

    def test_a_platform_run_key_belongs_to_no_bank_and_reads_no_instrument(self) -> None:
        # The instrument reads are made against one bank's footprint and date, so a key
        # of bleqq's own watch agents, which holds library:read but belongs to no bank,
        # answers 404 as the routes document, never an unfiltered list. The scope is
        # checked first, so the same key without library:read is refused with 403.
        with tenancy.platform_zone():
            key = agents_testing.agent_key()
            unscoped = agents_testing.agent_key(scopes=("changes:write",))
        for url in ("/api/v1/instruments", f"/api/v1/instruments/{self.fffs.id}", f"/api/v1/instruments/{self.fffs.id}/provisions"):
            with self.subTest(url=url):
                response = self.client.get(url, HTTP_X_API_KEY=key.plain_key)
                self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
                refused = self.client.get(url, HTTP_X_API_KEY=unscoped.plain_key)
                self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.SCOPE_LIBRARY_READ))

    def test_every_filter(self) -> None:
        self.assertEqual({row["stableKey"] for row in self.get({"regime": "securities", "footprint": "all"}).json()["items"]}, {"fffs-instruments", "fffs-amendment-instruments"})
        self.assertEqual(self.get({"regime": "no-such-regime"}).json()["items"], [], "an unknown key matches nothing")
        self.assertEqual({row["stableKey"] for row in self.get({"q": "FFFS 2017"}).json()["items"]}, {"fffs-instruments"})
        self.assertEqual(self.get({"q": "x" * 201}).status_code, 422)

    def test_pagination(self) -> None:
        first = self.get({"footprint": "all", "limit": 2}).json()
        self.assertEqual(len(first["items"]), 2)
        self.assertEqual(first["total"], 3)
        self.assertEqual(self.get({"limit": 101}).status_code, 422)

    def test_the_scope_rule_and_its_sql_twin_agree(self) -> None:
        scopes = instrument_scopes()
        sql = {row.id: set(row.term_ids) for row in Instrument.objects.annotate(term_ids=instrument_scope_term_ids())}
        python = {key: {term.id for terms in scopes.get(key, {}).values() for term in terms} for key in sql}
        self.assertEqual(python, sql)
        self.assertEqual(set(instrument_scopes(list(sql))), set(scopes), "for given instruments as for all of them")

    def test_the_query_count_does_not_grow_with_the_page(self) -> None:
        for limit in (1, 3):
            headers = sign_in(self.reader, tenant=self.tenant)
            with self.subTest(limit=limit), self.assertNumQueries(INSTRUMENT_LIST_QUERIES):
                response = self.get({"footprint": "all", "limit": limit}, headers)
            self.assertEqual(len(response.json()["items"]), limit)

    def test_a_person_needs_library_read_and_a_key_needs_library_read_scope(self) -> None:
        self.assertEqual(self.get({}, {}).status_code, 401)
        without = user_principal(permissions={perms.CASES_READ}, tenant_id=self.tenant.id)
        with stub_session(without):
            refused = self.get({}, {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"})
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.LIBRARY_READ))
        key = factories.api_key(self.tenant, scopes=(perms.SCOPE_LIBRARY_READ,))
        self.assertEqual(self.get({}, {"HTTP_X_API_KEY": key.plain_key}).status_code, 200)


class InstrumentDetailTests(TestCase):
    tenant: Tenant
    reader: User
    fffs: Instrument
    amendment: Instrument

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="detail-instruments")
        set_footprint(cls.tenant, FOOTPRINT)
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.fffs, cls.amendment, _insurance = seed_instruments()

    def get(self, instrument: Instrument, headers: dict[str, Any] | None = None) -> Any:
        return self.client.get(f"/api/v1/instruments/{instrument.id}", **(headers if headers is not None else sign_in(self.reader, tenant=self.tenant)))

    def card(self, instrument: Instrument) -> dict[str, Any]:
        response = self.get(instrument)
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def test_the_card_states_identity_dates_and_provenance(self) -> None:
        card = self.card(self.fffs)
        self.assertEqual((card["id"], card["stableKey"]), (str(self.fffs.id), "fffs-instruments"))
        self.assertEqual(card["shortName"], "FFFS 2017:2")
        self.assertEqual((card["level"]["key"], card["binding"], card["jurisdiction"]["key"]), ("authority_regulation", True, "se"))
        self.assertEqual(card["authority"], {"key": "fi", "name": "Finansinspektionen", "shortName": "FI", "url": "https://www.fi.se/"})
        self.assertEqual(card["regime"], {"key": "securities", "kind": None, "label": "Securities"})
        self.assertEqual(card["officialRef"], "FFFS-INSTRUMENTS")
        self.assertEqual(card["eliUri"], "", "ELI where available; empty and never null when there is none")
        self.assertEqual(card["inForceFrom"], {"date": "2018-01-03", "precision": "day"})
        self.assertEqual(card["implementsNote"], "MiFID II delegated directive (EU) 2017/593")
        self.assertEqual(card["sourceUrl"], build.SOURCE_URL)
        self.assertEqual(card["lastVerifiedAt"], "2026-06-30T08:00:00Z")
        self.assertIsNone(card["verifiedBy"], "a record nobody has re-verified names no verifier")
        self.assertTrue({"tone", "pill", "color", "colour"}.isdisjoint(field_names(card)))

    def test_lineage_names_both_directions(self) -> None:
        # The amending instrument's own card shows it going out; the amended one shows it
        # coming in, and both name the relation type and the other instrument.
        outgoing = self.card(self.amendment)
        self.assertEqual(
            [(link["relation"]["key"], link["direction"], link["instrument"]["key"]) for link in outgoing["lineage"]],
            [("amends", "outgoing", "fffs-instruments")],
        )
        incoming = self.card(self.fffs)
        self.assertEqual(
            [(link["relation"]["key"], link["direction"], link["instrument"]["key"]) for link in incoming["lineage"]],
            [("amends", "incoming", "fffs-amendment-instruments")],
        )
        self.assertEqual(incoming["lineage"][0]["note"], "Amends FFFS 2017:2, in force 1 October 2026.")
        # `fromRef` and `toRef` mean the same on both cards, as the designed relation has
        # them: the part of the amendment that amends, and the place in FFFS 2017:2 it
        # reaches. Neither swaps with the direction, so the amended instrument's own card
        # still says which of its sections is amended.
        for card in (outgoing, incoming):
            with self.subTest(direction=card["lineage"][0]["direction"]):
                self.assertEqual((card["lineage"][0]["fromRef"], card["lineage"][0]["toRef"]), ("1 §", "9 kap. 6 §"))

    def test_an_address_with_nothing_at_it_answers_404_and_a_malformed_one_422(self) -> None:
        missing = self.client.get(f"/api/v1/instruments/{uuid.uuid4()}", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((missing.status_code, missing.json()["code"]), (404, "not_found"))
        malformed = self.client.get("/api/v1/instruments/not-a-uuid", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(malformed.status_code, 422)

    def test_the_query_count_does_not_grow_with_the_lineage(self) -> None:
        for instrument in (self.fffs, self.amendment):
            headers = sign_in(self.reader, tenant=self.tenant)
            with self.subTest(key=instrument.stable_key), self.assertNumQueries(INSTRUMENT_DETAIL_QUERIES):
                response = self.get(instrument, headers)
            self.assertEqual(response.status_code, 200, response.content)

    def test_a_person_needs_library_read_and_a_key_needs_library_read_scope(self) -> None:
        no_scope = factories.api_key(self.tenant, scopes=(perms.SCOPE_CHANGES_WRITE,))
        key = factories.api_key(self.tenant, scopes=(perms.SCOPE_LIBRARY_READ,))
        without = user_principal(permissions={perms.CASES_READ}, tenant_id=self.tenant.id)
        self.assertEqual(self.get(self.fffs, {}).status_code, 401)
        with stub_session(without):
            refused = self.get(self.fffs, {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"})
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.LIBRARY_READ))
        refused = self.get(self.fffs, {"HTTP_X_API_KEY": no_scope.plain_key})
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.SCOPE_LIBRARY_READ))
        self.assertEqual(self.get(self.fffs, {"HTTP_X_API_KEY": key.plain_key}).status_code, 200)


class PrivateInstrumentIsolation(TransactionTestCase):
    """INPUT_DELTAS §5, INV-07: as the app role, under forced row-level security, another
    tenant's private instrument is never in the list, the total, a q match, a filter or
    another instrument's lineage."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_reference()
        self.tenant_a = factories.tenant(slug="iso-instruments-a")
        self.tenant_b = factories.tenant(slug="iso-instruments-b")
        set_footprint(self.tenant_a, FOOTPRINT)
        with transaction.atomic():
            self.fffs, self.amendment, self.insurance = seed_instruments()
        with transaction.atomic():
            tenancy.activate(self.tenant_b.id)
            self.private = build.instrument(key="bank-b-instrument", regime="regime:securities", owner_tenant=self.tenant_b)
            build.relate_instruments(self.private, self.fffs, relation="elaborates")
        self.key_a = factories.api_key(self.tenant_a, scopes=(perms.SCOPE_LIBRARY_READ,))
        self.key_b = factories.api_key(self.tenant_b, scopes=(perms.SCOPE_LIBRARY_READ,))

    def test_another_tenants_private_instrument_is_never_read_or_addressed(self) -> None:
        with as_app_role():
            for params in ({}, {"footprint": "all"}, {"q": "bank-b", "footprint": "all"}, {"regime": "securities", "footprint": "all"}):
                with self.subTest(params=params):
                    response = self.client.get("/api/v1/instruments", params, HTTP_X_API_KEY=self.key_a.plain_key)
                    self.assertEqual(response.status_code, 200, response.content)
                    page = response.json()
                    self.assertNotIn("bank-b-instrument", [row["stableKey"] for row in page["items"]])
                    self.assertEqual(page["total"], len(page["items"]))
            refused = self.client.get(f"/api/v1/instruments/{self.private.id}", HTTP_X_API_KEY=self.key_a.plain_key)
            self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"))
            # The private instrument's own outgoing relation to fffs never surfaces there.
            fffs_card = self.client.get(f"/api/v1/instruments/{self.fffs.id}", HTTP_X_API_KEY=self.key_a.plain_key).json()
            self.assertNotIn("bank-b-instrument", [link["instrument"]["key"] for link in fffs_card["lineage"]])
            own = self.client.get(f"/api/v1/instruments/{self.private.id}", HTTP_X_API_KEY=self.key_b.plain_key)
            self.assertEqual((own.status_code, own.json()["stableKey"]), (200, "bank-b-instrument"))


# Queries per provision tree read, measured 2026-09-22 and pinned so the tree's size
# cannot grow the count: the savepoint pair (2); the session (6); the caller's tenant and
# locale (2); the instrument (1), its provisions (1) and their kind labels (1); the
# provision versions (1) and their texts (1); the citing links with their obligations (1)
# and the cited obligations' titles (1).
PROVISION_TREE_QUERIES = 2 + 6 + 2 + 1 + 1 + 1 + 1 + 1 + 1 + 1


def seed_provision_tree() -> tuple[Instrument, Provision, Provision, Provision]:
    """A chapter with a section under it and a paragraph under that (three levels), a
    sibling chapter with no children, two versions of the section with a transitional
    note on the later one, and an obligation citing the section (INV-02)."""
    instrument = build.instrument(key="fffs-tree", short_name="FFFS Tree", regime="regime:securities")
    chapter = build.provision(instrument, key="fffs-tree/9", ref_label="9 kap.", heading="Skydd för investerare", sort_order=9)
    section = build.provision(
        instrument, key="fffs-tree/9-6", ref_label="6 §", heading="Betalning för analys", kind="section", parent=chapter, sort_order=6
    )
    paragraph = build.provision(
        instrument, key="fffs-tree/9-6-1", ref_label="första stycket", kind="paragraph", parent=section, sort_order=1
    )
    build.provision(instrument, key="fffs-tree/10", ref_label="10 kap.", heading="Produktstyrning", sort_order=10)
    build.provision_version(
        section, version_no=1, effective_from=D(2018, 1, 3), texts={"sv": "Analysbetalning enligt de äldre reglerna.", "en": "Research payment under the earlier rules."}
    )
    build.provision_version(
        section,
        version_no=2,
        effective_from=D(2026, 11, 1),
        transitional_note="The amendment binds from 1 November 2026.",
        texts={"sv": "Analysbetalning enligt de nya reglerna.", "en": "Research payment under the new rules."},
    )
    build.obligation(instrument, key="obl-tree-research", cites=(section,))
    return instrument, chapter, section, paragraph


class ProvisionTreeTests(TestCase):
    tenant: Tenant
    reader: User
    instrument: Instrument
    chapter: Provision
    section: Provision
    paragraph: Provision

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="provision-tree")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.instrument, cls.chapter, cls.section, cls.paragraph = seed_provision_tree()

    def get(self, params: dict[str, Any] | None = None, headers: dict[str, Any] | None = None) -> Any:
        return self.client.get(
            f"/api/v1/instruments/{self.instrument.id}/provisions", params or {}, **(headers if headers is not None else sign_in(self.reader, tenant=self.tenant))
        )

    def tree(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        response = self.get(params)
        self.assertEqual(response.status_code, 200, response.content)
        return list(response.json())

    def test_the_tree_has_three_levels_and_a_sibling_leaf(self) -> None:
        roots = self.tree()
        self.assertEqual({node["stableKey"] for node in roots}, {"fffs-tree/9", "fffs-tree/10"})
        chapter = next(node for node in roots if node["stableKey"] == "fffs-tree/9")
        self.assertEqual((chapter["kind"]["key"], chapter["kind"]["kind"], chapter["heading"]), ("chapter", "division", "Skydd för investerare"))
        self.assertEqual(len(chapter["children"]), 1)
        section = chapter["children"][0]
        self.assertEqual((section["stableKey"], section["refLabel"], section["kind"]["key"]), ("fffs-tree/9-6", "6 §", "section"))
        self.assertEqual(len(section["children"]), 1)
        paragraph = section["children"][0]
        self.assertEqual((paragraph["stableKey"], paragraph["kind"]["key"]), ("fffs-tree/9-6-1", "paragraph"))
        self.assertEqual(paragraph["children"], [])
        leaf = next(node for node in roots if node["stableKey"] == "fffs-tree/10")
        self.assertEqual(leaf["children"], [])
        self.assertTrue({"tone", "pill", "color", "colour"}.isdisjoint(field_names(roots)))

    def test_a_section_carries_both_versions_and_the_later_one_says_what_changed(self) -> None:
        section = next(node for node in self.tree()[0]["children"] if node["stableKey"] == "fffs-tree/9-6")
        self.assertEqual([v["versionNumber"] for v in section["versions"]], [1, 2])
        self.assertEqual(section["versions"][0]["effectiveTo"], {"date": "2026-10-31", "precision": "day"})
        self.assertIsNone(section["versions"][1]["effectiveTo"])
        self.assertEqual(section["versions"][1]["transitionalNote"], "The amendment binds from 1 November 2026.")
        self.assertEqual(section["versions"][0]["transitionalNote"], "")
        self.assertEqual(len(section["obligations"]), 1)
        self.assertEqual(section["obligations"][0]["refLabel"], "1 §")

    def _section(self, tree: list[dict[str, Any]]) -> dict[str, Any]:
        return next(node for node in tree[0]["children"] if node["stableKey"] == "fffs-tree/9-6")

    def test_as_of_picks_the_in_force_version_before_and_after_the_amendment(self) -> None:
        before = self._section(self.tree({"asOf": "2026-10-31"}))
        self.assertEqual(before["inForceVersion"], 1)
        after = self._section(self.tree({"asOf": "2026-11-01"}))
        self.assertEqual(after["inForceVersion"], 2)
        # The earlier version's own row never changes between the two reads.
        self.assertEqual(before["versions"][0], after["versions"][0])

    def test_the_diff_between_the_two_versions(self) -> None:
        response = self.client.get(f"/api/v1/provisions/{self.section.id}/diff", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body["fromVersion"], body["toVersion"]), (1, 2))
        self.assertEqual((body["fromConfirmation"], body["toConfirmation"]), (None, None), "a provision's text records no approval")
        self.assertEqual(
            body["segments"],
            [
                {"op": "delete", "text": "Research payment under the earlier rules."},
                {"op": "insert", "text": "Research payment under the new rules."},
            ],
        )

    def test_an_instrument_or_a_provision_the_caller_cannot_see_answers_404(self) -> None:
        missing_tree = self.client.get(f"/api/v1/instruments/{uuid.uuid4()}/provisions", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((missing_tree.status_code, missing_tree.json()["code"]), (404, "not_found"))
        missing_diff = self.client.get(f"/api/v1/provisions/{uuid.uuid4()}/diff", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((missing_diff.status_code, missing_diff.json()["code"]), (404, "not_found"))

    def test_the_query_count_does_not_grow_with_the_tree(self) -> None:
        headers = sign_in(self.reader, tenant=self.tenant)
        with self.assertNumQueries(PROVISION_TREE_QUERIES):
            self.assertEqual(self.get(headers=headers).status_code, 200)

    def test_a_person_needs_library_read_and_a_key_needs_library_read_scope(self) -> None:
        no_scope = factories.api_key(self.tenant, scopes=(perms.SCOPE_CHANGES_WRITE,))
        key = factories.api_key(self.tenant, scopes=(perms.SCOPE_LIBRARY_READ,))
        for path in (f"/api/v1/instruments/{self.instrument.id}/provisions", f"/api/v1/provisions/{self.section.id}/diff"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
                refused = self.client.get(path, HTTP_X_API_KEY=no_scope.plain_key)
                self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.SCOPE_LIBRARY_READ))
                self.assertEqual(self.client.get(path, HTTP_X_API_KEY=key.plain_key).status_code, 200)


class ProvisionTreeCitationIsolation(TransactionTestCase):
    """INPUT_DELTAS §5, INV-07: a provision is shared, but the obligations that cite it
    are not all shared. A private obligation of another tenant never appears in the
    tree, though it is read through the same join as the shared ones."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_reference()
        self.tenant_a = factories.tenant(slug="iso-tree-a")
        self.tenant_b = factories.tenant(slug="iso-tree-b")
        with transaction.atomic():
            self.instrument, _chapter, self.section, _paragraph = seed_provision_tree()
        with transaction.atomic():
            tenancy.activate(self.tenant_b.id)
            private = build.instrument(key="bank-b-tree-instrument", regime="regime:securities", owner_tenant=self.tenant_b)
            self.private_obligation = build.obligation(private, key="obl-bank-b-cites-shared", cites=(self.section,), owner_tenant=self.tenant_b)
        self.key_a = factories.api_key(self.tenant_a, scopes=(perms.SCOPE_LIBRARY_READ,))
        self.key_b = factories.api_key(self.tenant_b, scopes=(perms.SCOPE_LIBRARY_READ,))

    def _section_of(self, tree: list[dict[str, Any]]) -> dict[str, Any]:
        return next(node for node in tree[0]["children"] if node["stableKey"] == "fffs-tree/9-6")

    def test_a_private_citation_is_never_shown_to_another_tenant(self) -> None:
        with as_app_role():
            response = self.client.get(f"/api/v1/instruments/{self.instrument.id}/provisions", HTTP_X_API_KEY=self.key_a.plain_key)
            self.assertEqual(response.status_code, 200, response.content)
            section = self._section_of(response.json())
            visible_ids = [o["id"] for o in section["obligations"]]
            self.assertNotIn(str(self.private_obligation.id), visible_ids)
            self.assertEqual(len(visible_ids), 1, "the shared obligation from seed_provision_tree() is still there")
            # The owning tenant sees its own citation beside the shared one.
            own = self.client.get(f"/api/v1/instruments/{self.instrument.id}/provisions", HTTP_X_API_KEY=self.key_b.plain_key)
            own_section = self._section_of(own.json())
            self.assertIn(str(self.private_obligation.id), [o["id"] for o in own_section["obligations"]])


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

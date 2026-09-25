"""An agent access entry's scope (ACC-02, D-70, AC-ACC1; taxonomy 0011).

The SQL rule over a term map is pinned to the pure rule on every combination, opt-in
dimension included; then an entry's terms are derived from its departments, their units and
its products, intersected with the footprint, and the database's verdict on a record is
pinned to the pure one. Naming nothing narrows nothing; naming what derives nothing reads
nothing, with a reason; an entry the session cannot see or one revoked fails closed."""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Iterable
from typing import Any

from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.agents.models import AgentAccess, AgentAccessDepartment, AgentAccessProduct
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.shared.tenancy import library_write
from apps.taxonomy import entry_scope, matching
from apps.taxonomy.models import FootprintTerm, TaxonomyTerm, Team, TermDimension
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.tenants.models import OrgUnit, OrgUnitKind, ProductStatusKind, TenantProduct, TenantProductTerm


def seed() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_term_dimensions()
    seed_taxonomy_terms()


def term(dimension: str, key: str) -> TaxonomyTerm:
    """A library term, filed when the seed has none (product types have no seeded terms)."""
    with library_write("test"):
        row, _created = TaxonomyTerm.objects.get_or_create(dimension=TermDimension.objects.get(key=dimension), key=key)
    return row


def as_map(terms: Iterable[TaxonomyTerm]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for row in terms:
        result.setdefault(row.dimension.key, set()).add(row.key)
    return result


class EntryBank:
    """One bank's organisation, products and agent access entries, written in its own zone."""

    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant
        self.admin = factories.member(tenant, roles=("admin",)).user
        tenancy.activate(tenant.id)
        self.team = Team.objects.get(tenant=tenant, key="compliance")

    def footprint(self, *terms: TaxonomyTerm) -> None:
        tenancy.activate(self.tenant.id)
        FootprintTerm.objects.filter(tenant=self.tenant).delete()
        for row in terms:
            FootprintTerm.objects.create(tenant=self.tenant, term=row)

    def unit(self, name: str, *, parent: OrgUnit | None = None, active: bool = True) -> OrgUnit:
        tenancy.activate(self.tenant.id)
        return OrgUnit.objects.create(
            tenant=self.tenant, kind=OrgUnitKind.BUSINESS_AREA.value, name=name, parent=parent, active=active
        )

    def product(self, name: str, *terms: TaxonomyTerm, unit: OrgUnit | None = None, status: ProductStatusKind = ProductStatusKind.LIVE) -> TenantProduct:
        tenancy.activate(self.tenant.id)
        row = TenantProduct.objects.create(tenant=self.tenant, name=name, org_unit=unit, status=status.value)
        for scope_term in terms:
            TenantProductTerm.objects.create(tenant=self.tenant, product=row, term=scope_term)
        return row

    def entry(self, *, departments: Iterable[OrgUnit] = (), products: Iterable[TenantProduct] = (), name: str = "Agent") -> AgentAccess:
        tenancy.activate(self.tenant.id)
        row = AgentAccess.objects.create(
            tenant=self.tenant, name=name, purpose="Reads what applies.", owner_team=self.team, created_by=self.admin
        )
        for department in departments:
            AgentAccessDepartment.objects.create(tenant=self.tenant, agent_access=row, department=department)
        for product in products:
            AgentAccessProduct.objects.create(tenant=self.tenant, agent_access=row, product=product)
        return row

    def scope(self, entry: AgentAccess) -> entry_scope.EntryScope:
        tenancy.activate(self.tenant.id)
        return entry_scope.scope_of(self.tenant.id, entry.id)


def term_map_admits_sql(record: Iterable[TaxonomyTerm], allowed: Iterable[TaxonomyTerm]) -> bool:
    """The SQL rule over a term map: the guard of taxonomy 0011 handed to the per-row check."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT taxonomy_scope_admits(%s::uuid[], g.terms, g.dimensions, g.allowed) "
            "FROM taxonomy_term_map_guard(%s::uuid[]) AS g",
            [[str(row.id) for row in record], [str(row.id) for row in allowed]],
        )
        return bool(cursor.fetchone()[0])


class TermMapRuleMirrorsPython(TestCase):
    """FP-01 over any term map: a scope dimension, a second one, a dimension that never
    restricts and the opt-in `standard` with two terms. Every record against every map."""

    def setUp(self) -> None:
        seed()
        with library_write("test"):
            second = TaxonomyTerm.objects.create(dimension=TermDimension.objects.get(key="standard"), key="second_standard")
        self.terms = [
            term("service_type", "custody"),
            term("service_type", "advice"),
            term("client_category", "retail"),
            term("channel", "branch"),
            term("standard", "iso_iec_27001"),
            second,
        ]

    def test_every_combination_agrees(self) -> None:
        restricting = matching.restricting_dimensions()
        self.assertEqual(restricting.opt_in, {"standard"})
        subsets = [combo for n in range(len(self.terms) + 1) for combo in itertools.combinations(self.terms, n)]
        empty_dimension_passes = hidden_by_opt_in = 0
        for allowed in subsets:
            allowed_map = as_map(allowed)
            for record in subsets:
                record_map = as_map(record)
                expected = matching.in_footprint(record_map, allowed_map, restricting=restricting)
                self.assertIs(term_map_admits_sql(record, allowed), expected, f"record {record_map} map {allowed_map}")
                if "service_type" in record_map and "service_type" not in allowed_map and set(record_map) <= {"service_type", "channel"}:
                    self.assertTrue(expected, "an empty dimension does not restrict")
                    empty_dimension_passes += 1
                if "standard" in record_map and "standard" not in allowed_map:
                    self.assertFalse(expected, "an opt-in dimension matches only what the map names")
                    hidden_by_opt_in += 1
        self.assertGreater(empty_dimension_passes, 0)
        self.assertGreater(hidden_by_opt_in, 0)


class EntryScopeDerivation(TestCase):
    """The terms of an entry come from its departments, the units below them and its
    products, and never reach outside the footprint."""

    def setUp(self) -> None:
        seed()
        self.derivatives = term("product_type", "derivatives")
        self.securities = term("product_type", "securities")
        self.cards = term("product_type", "cards")
        self.issuing = term("licensed_activity", "card_issuing")
        self.custody = term("service_type", "custody")
        self.bank = EntryBank(factories.tenant(slug="entry-scope"))
        self.bank.footprint(self.derivatives, self.securities, self.cards, self.issuing, self.custody)
        self.trading = self.bank.unit("Trading")
        self.desk = self.bank.unit("Equity desk", parent=self.trading)
        self.bank.product("Futures", self.derivatives, unit=self.trading)
        self.bank.product("Equities", self.securities, self.custody, unit=self.desk)
        self.card_product = self.bank.product("Debit card", self.cards, self.issuing)

    def keys(self, scope: entry_scope.EntryScope) -> dict[str, set[str]]:
        return {dimension: set(keys) for dimension, keys in scope.terms.items()}

    def test_a_department_brings_its_products_and_those_of_every_unit_below_it(self) -> None:
        scope = self.bank.scope(self.bank.entry(departments=[self.trading]))
        self.assertTrue(scope.narrowed)
        self.assertEqual(self.keys(scope), {"product_type": {"derivatives", "securities"}, "service_type": {"custody"}})
        self.assertIsNone(scope.empty_reason)

    def test_a_named_product_adds_its_own_terms(self) -> None:
        scope = self.bank.scope(self.bank.entry(departments=[self.desk], products=[self.card_product]))
        self.assertEqual(
            self.keys(scope),
            {"product_type": {"securities", "cards"}, "service_type": {"custody"}, "licensed_activity": {"card_issuing"}},
        )

    def test_a_term_outside_the_footprint_is_never_in_scope(self) -> None:
        advice = term("service_type", "advice")
        self.bank.product("Advisory", advice, unit=self.trading)
        scope = self.bank.scope(self.bank.entry(departments=[self.trading]))
        self.assertNotIn("advice", scope.terms["service_type"])
        # A record carrying only that term is out: the footprint says so, and the entry cannot say otherwise.
        entry = self.bank.entry(departments=[self.trading], name="Second")
        self.assertFalse(entry_scope.admits_sql(self.bank.tenant.id, entry.id, [advice.id]))

    def test_retired_products_and_deactivated_units_derive_nothing(self) -> None:
        closed = self.bank.unit("Closed desk", parent=self.trading, active=False)
        self.bank.product("Old cards", self.cards, unit=closed)
        self.bank.product("Retired cards", self.cards, unit=self.trading, status=ProductStatusKind.RETIRED)
        scope = self.bank.scope(self.bank.entry(departments=[self.trading]))
        self.assertNotIn("cards", scope.terms["product_type"])

    def test_naming_nothing_is_the_footprint_exactly(self) -> None:
        scope = self.bank.scope(self.bank.entry())
        self.assertFalse(scope.narrowed)
        tenancy.activate(self.bank.tenant.id)
        self.assertEqual(self.keys(scope), matching.footprint_of(self.bank.tenant.id))

    def test_naming_what_derives_nothing_reads_nothing_with_a_reason(self) -> None:
        empty = self.bank.unit("Back office")
        entry = self.bank.entry(departments=[empty])
        scope = self.bank.scope(entry)
        self.assertEqual((scope.narrowed, scope.terms, scope.empty_reason), (True, {}, entry_scope.EMPTY_SCOPE))
        tenancy.activate(self.bank.tenant.id)
        footprint = matching.footprint_of(self.bank.tenant.id)
        restricting = matching.restricting_dimensions()
        # Not even a record carrying no term at all, which every footprint admits.
        self.assertFalse(entry_scope.admits({}, footprint, scope, restricting=restricting))
        self.assertFalse(entry_scope.admits_sql(self.bank.tenant.id, entry.id, []))

    def test_an_entry_out_of_sight_or_revoked_fails_closed(self) -> None:
        other = EntryBank(factories.tenant(slug="entry-scope-other"))
        theirs = other.entry()
        # Under this bank's zone the other bank's entry is invisible: it reads nothing, not everything.
        mine = self.bank.scope(theirs)
        self.assertEqual(mine.empty_reason, entry_scope.EMPTY_SCOPE)
        self.assertFalse(entry_scope.admits_sql(self.bank.tenant.id, theirs.id, []))
        self.assertFalse(entry_scope.admits_sql(self.bank.tenant.id, uuid.uuid4(), []))
        revoked = self.bank.entry(name="Revoked")
        AgentAccess.objects.filter(pk=revoked.pk).update(active=False, revoked_at=timezone.now(), revoked_by=self.bank.admin)
        self.assertEqual(self.bank.scope(revoked).empty_reason, entry_scope.EMPTY_SCOPE)

    def test_the_database_agrees_with_the_pure_rule_for_every_entry_and_record(self) -> None:
        advice = term("service_type", "advice")
        opt_in = term("standard", "iso_iec_27001")
        self.bank.footprint(self.derivatives, self.securities, self.cards, self.issuing, self.custody, opt_in)
        self.bank.product("Secure trading", opt_in, unit=self.desk)
        entries: list[Any] = [
            self.bank.entry(name="Everything"),
            self.bank.entry(departments=[self.trading], name="Trading"),
            self.bank.entry(departments=[self.desk], name="Desk"),
            self.bank.entry(products=[self.card_product], name="Cards"),
            self.bank.entry(departments=[self.bank.unit("Empty")], name="Empty"),
        ]
        pool = [self.derivatives, self.cards, self.issuing, self.custody, advice, opt_in]
        records = [combo for n in range(len(pool) + 1) for combo in itertools.combinations(pool, n)]
        tenancy.activate(self.bank.tenant.id)
        footprint = matching.footprint_of(self.bank.tenant.id)
        restricting = matching.restricting_dimensions()
        admitted = {entry.name: 0 for entry in entries}
        for entry in entries:
            scope = self.bank.scope(entry)
            for record in records:
                expected = entry_scope.admits(as_map(record), footprint, scope, restricting=restricting)
                actual = entry_scope.admits_sql(self.bank.tenant.id, entry.id, [row.id for row in record])
                self.assertIs(actual, expected, f"{entry.name}: {as_map(record)}")
                admitted[entry.name] += expected
        # Every narrowing reads less than the whole footprint, and the empty entry reads nothing.
        self.assertEqual(admitted["Empty"], 0)
        for name in ("Trading", "Desk", "Cards"):
            self.assertLess(admitted[name], admitted["Everything"], name)

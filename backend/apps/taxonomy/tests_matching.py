"""Footprint matching (FP-01, playbook 8.1: tests required with every change).

`in_footprint()` is exhaustively tested here as a pure function, then the SQL function
`taxonomy_in_footprint(tenant, term_ids[])` from the taxonomy migration is run against
every case with real rows and must agree. The rule: for every dimension the record
carries terms in, at least one must be in the footprint; a dimension with no terms does
not restrict; a dimension whose `restricts_footprint` is false is ignored."""

from __future__ import annotations

import itertools
import uuid

from django.db import connection
from django.test import TestCase

from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.taxonomy import matching, tenant_lists_logic
from apps.taxonomy.models import FootprintTerm, TermDimension
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

# (record terms, footprint, restricting dimensions or None for "all restrict", expected)
CASES: list[tuple[dict[str, set[str]], dict[str, set[str]], set[str] | None, bool]] = [
    # Empty record matches every footprint, including an empty one.
    ({}, {}, None, True),
    ({}, {"service_type": {"custody"}}, None, True),
    # One dimension, hit and miss.
    ({"service_type": {"custody"}}, {"service_type": {"custody"}}, None, True),
    ({"service_type": {"advice"}}, {"service_type": {"custody"}}, None, False),
    # Any one term of the dimension in the footprint is enough.
    ({"service_type": {"advice", "custody"}}, {"service_type": {"custody"}}, None, True),
    # A dimension the footprint has no terms in does not restrict.
    ({"service_type": {"custody"}, "client_category": {"retail"}}, {"service_type": {"custody"}}, None, True),
    ({"client_category": {"retail"}}, {}, None, True),
    # Every carried dimension must hit: two dimensions, one miss.
    ({"service_type": {"custody"}, "client_category": {"retail"}}, {"service_type": {"custody"}, "client_category": {"professional"}}, None, False),
    ({"service_type": {"custody"}, "client_category": {"retail"}}, {"service_type": {"custody"}, "client_category": {"retail", "professional"}}, None, True),
    # An empty footprint restricts nothing (no dimension has terms).
    ({"service_type": {"advice"}}, {}, None, True),
    # A dimension that does not restrict is ignored, whatever the footprint says about it.
    ({"channel": {"branch"}}, {"channel": {"digital"}}, {"service_type"}, True),
    ({"service_type": {"advice"}, "channel": {"digital"}}, {"service_type": {"custody"}, "channel": {"digital"}}, {"service_type"}, False),
    ({"service_type": {"custody"}, "channel": {"branch"}}, {"service_type": {"custody"}, "channel": {"digital"}}, {"service_type"}, True),
    # A record with empty term sets carries no restriction for that dimension.
    ({"service_type": set()}, {"service_type": {"custody"}}, None, True),
]


class InFootprintRule(TestCase):
    def test_every_case(self) -> None:
        for record, footprint, restricting, expected in CASES:
            with self.subTest(record=record, footprint=footprint, restricting=restricting):
                self.assertIs(matching.in_footprint(record, footprint, restricting=restricting), expected)

    def test_inputs_are_not_mutated(self) -> None:
        record = {"service_type": {"custody"}}
        footprint = {"service_type": {"custody"}}
        matching.in_footprint(record, footprint)
        self.assertEqual(record, {"service_type": {"custody"}})
        self.assertEqual(footprint, {"service_type": {"custody"}})


class SqlMirrorsPython(TestCase):
    """The SQL function must agree with the Python rule on every combination of the real
    seeded terms in three dimensions, two of which restrict."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="match")
        tenancy.activate(self.tenant.id)
        self.terms = {
            "service_type:custody": tenant_lists_logic.term_by_ref("service_type", "custody"),
            "service_type:advice": tenant_lists_logic.term_by_ref("service_type", "advice"),
            "client_category:retail": tenant_lists_logic.term_by_ref("client_category", "retail"),
            "client_category:professional": tenant_lists_logic.term_by_ref("client_category", "professional"),
            "channel:branch": tenant_lists_logic.term_by_ref("channel", "branch"),
        }
        self.restricting = matching.restricting_dimensions()
        self.assertFalse(TermDimension.objects.get(key="channel").restricts_footprint)

    def _as_dict(self, refs: tuple[str, ...]) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for ref in refs:
            dimension, key = ref.split(":")
            result.setdefault(dimension, set()).add(key)
        return result

    def test_every_combination_agrees(self) -> None:
        refs = tuple(self.terms)
        subsets = [combo for n in range(len(refs) + 1) for combo in itertools.combinations(refs, n)]
        checked = 0
        for footprint_refs in subsets:
            FootprintTerm.objects.filter(tenant=self.tenant).delete()
            for ref in footprint_refs:
                FootprintTerm.objects.create(tenant=self.tenant, term=self.terms[ref])
            footprint = matching.footprint_of(self.tenant.id)
            self.assertEqual(footprint, self._as_dict(footprint_refs))
            for record_refs in subsets:
                expected = matching.in_footprint(self._as_dict(record_refs), footprint, restricting=self.restricting)
                actual = matching.in_footprint_sql(self.tenant.id, [self.terms[ref].id for ref in record_refs])
                self.assertIs(actual, expected, f"record {record_refs} footprint {footprint_refs}")
                checked += 1
        self.assertEqual(checked, 32 * 32)

    def test_the_function_reads_the_footprint_under_row_level_security(self) -> None:
        """Another tenant's footprint never counts: the same arguments answer differently
        depending on which tenant is activated, because the policy hides the other rows.

        Rewritten 2026-09-19: the first version asserted that a tenant with an empty
        footprint matches nothing, which contradicts the rule this file pins (CASES: "an
        empty footprint restricts nothing") and the SQL function that implements it."""
        custody, advice = self.terms["service_type:custody"], self.terms["service_type:advice"]
        FootprintTerm.objects.create(tenant=self.tenant, term=advice)
        other = factories.tenant(slug="match-other")
        tenancy.activate(other.id)
        FootprintTerm.objects.create(tenant=other, term=custody)
        # As the other tenant: its custody-only footprint restricts service_type.
        self.assertTrue(matching.in_footprint_sql(other.id, [custody.id]))
        self.assertFalse(matching.in_footprint_sql(other.id, [advice.id]))
        # As this tenant: the other tenant's custody row is invisible, so it never widens this
        # tenant's advice-only footprint, and asking about the other tenant sees no footprint.
        tenancy.activate(self.tenant.id)
        self.assertFalse(matching.in_footprint_sql(self.tenant.id, [custody.id]))
        self.assertTrue(matching.in_footprint_sql(self.tenant.id, [advice.id]))
        self.assertTrue(matching.in_footprint_sql(other.id, [advice.id]))

    def test_unknown_term_ids_do_not_match_anything(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT taxonomy_in_footprint(%s, %s::uuid[])", [str(self.tenant.id), [str(uuid.uuid4())]])
            self.assertTrue(cursor.fetchone()[0], "an id that is no term carries no dimension and so restricts nothing")

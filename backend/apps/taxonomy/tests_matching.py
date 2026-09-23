"""Footprint matching (FP-01, D-36, playbook 8.1: tests required with every change).

`in_footprint()` is exhaustively tested here as a pure function, then the SQL function
`taxonomy_in_footprint(tenant, term_ids[])` from the taxonomy migrations is run against
every case with real rows and must agree. The rule: for every dimension the record
carries terms in, at least one must be in the footprint; a dimension with no terms does
not restrict, except an opt-in dimension, where a record carrying one of its terms matches
only when the footprint names that term; a dimension whose `restricts_footprint` is false
is ignored, unless it is opt-in, which restricts whatever the flag says."""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Iterable, Iterator
from typing import Any

from django.contrib.postgres.fields import ArrayField
from django.db import connection
from django.db.models import F, Func, UUIDField
from django.test import TestCase

from apps.library.reading import terms_of
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.tenancy import library_write
from apps.taxonomy import matching, tenant_lists_logic
from apps.taxonomy.models import FootprintTerm, TaxonomyTerm, TermDimension
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.terms_logic import term_by_ref
from apps.watch.keys import resolve_terms

# The restricting dimensions each pure case is decided against.
SCOPE = matching.Restricting({"service_type", "client_category"}, opt_in=())
SERVICES = matching.Restricting({"service_type"}, opt_in=())
STANDARDS = matching.Restricting({"service_type"}, opt_in={"standard"})

# (record terms, footprint, restricting dimensions, expected)
CASES: list[tuple[dict[str, set[str]], dict[str, set[str]], matching.Restricting, bool]] = [
    # Empty record matches every footprint, including an empty one.
    ({}, {}, SCOPE, True),
    ({}, {"service_type": {"custody"}}, SCOPE, True),
    # One dimension, hit and miss.
    ({"service_type": {"custody"}}, {"service_type": {"custody"}}, SCOPE, True),
    ({"service_type": {"advice"}}, {"service_type": {"custody"}}, SCOPE, False),
    # Any one term of the dimension in the footprint is enough.
    ({"service_type": {"advice", "custody"}}, {"service_type": {"custody"}}, SCOPE, True),
    # A dimension the footprint has no terms in does not restrict.
    ({"service_type": {"custody"}, "client_category": {"retail"}}, {"service_type": {"custody"}}, SCOPE, True),
    ({"client_category": {"retail"}}, {}, SCOPE, True),
    # Every carried dimension must hit: two dimensions, one miss.
    ({"service_type": {"custody"}, "client_category": {"retail"}}, {"service_type": {"custody"}, "client_category": {"professional"}}, SCOPE, False),
    ({"service_type": {"custody"}, "client_category": {"retail"}}, {"service_type": {"custody"}, "client_category": {"retail", "professional"}}, SCOPE, True),
    # An empty footprint restricts nothing (no dimension has terms).
    ({"service_type": {"advice"}}, {}, SCOPE, True),
    # A dimension that does not restrict is ignored, whatever the footprint says about it.
    ({"channel": {"branch"}}, {"channel": {"digital"}}, SERVICES, True),
    ({"service_type": {"advice"}, "channel": {"digital"}}, {"service_type": {"custody"}, "channel": {"digital"}}, SERVICES, False),
    ({"service_type": {"custody"}, "channel": {"branch"}}, {"service_type": {"custody"}, "channel": {"digital"}}, SERVICES, True),
    # A record with empty term sets carries no restriction for that dimension.
    ({"service_type": set()}, {"service_type": {"custody"}}, SCOPE, True),
    # Opt-in (D-36): a record carrying a standard matches only a footprint that names it,
    # also when the footprint is empty or has no entry for the dimension at all.
    ({"standard": {"iso_iec_27001"}}, {}, STANDARDS, False),
    ({"standard": {"iso_iec_27001"}}, {"service_type": {"custody"}}, STANDARDS, False),
    ({"standard": {"iso_iec_27001"}}, {"standard": set()}, STANDARDS, False),
    ({"standard": {"iso_iec_27001"}}, {"standard": {"iso_iec_27001"}}, STANDARDS, True),
    ({"standard": {"iso_iec_27001"}}, {"standard": {"iso_22301"}}, STANDARDS, False),
    # Any one of the record's standards named is enough, as in every other dimension.
    ({"standard": {"iso_iec_27001", "iso_22301"}}, {"standard": {"iso_22301"}}, STANDARDS, True),
    # A named standard does not rescue a miss in another dimension.
    ({"standard": {"iso_iec_27001"}, "service_type": {"advice"}}, {"standard": {"iso_iec_27001"}, "service_type": {"custody"}}, STANDARDS, False),
    # A record carrying no standard is unaffected by the opt-in dimension, and an empty scope
    # dimension still does not restrict next to it.
    ({"service_type": {"custody"}}, {"service_type": {"custody"}}, STANDARDS, True),
    ({"service_type": {"advice"}}, {"standard": {"iso_iec_27001"}}, STANDARDS, True),
    ({"standard": set()}, {}, STANDARDS, True),
    ({}, {}, STANDARDS, True),
]


def _as_dict(refs: Iterable[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for ref in refs:
        dimension, key = ref.split(":")
        result.setdefault(dimension, set()).add(key)
    return result


def _seed() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_term_dimensions()
    seed_taxonomy_terms()


class InFootprintRule(TestCase):
    def test_every_case(self) -> None:
        for record, footprint, restricting, expected in CASES:
            with self.subTest(record=record, footprint=footprint, restricting=restricting):
                self.assertIs(matching.in_footprint(record, footprint, restricting=restricting), expected)

    def test_inputs_are_not_mutated(self) -> None:
        record = {"service_type": {"custody"}, "standard": {"iso_iec_27001"}}
        footprint = {"service_type": {"custody"}}
        matching.in_footprint(record, footprint, restricting=STANDARDS)
        self.assertEqual(record, {"service_type": {"custody"}, "standard": {"iso_iec_27001"}})
        self.assertEqual(footprint, {"service_type": {"custody"}})

    def test_the_restricting_dimensions_are_required_and_must_name_the_opt_in_ones(self) -> None:
        """No caller can forget the opt-in dimensions: leaving the argument out, or passing a
        plain set of keys that cannot say which of them are opt-in, is a TypeError rather than
        a silent verdict that shows every standard to every bank."""
        with self.assertRaises(TypeError):
            matching.in_footprint({"standard": {"iso_iec_27001"}}, {})  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            matching.in_footprint({"standard": {"iso_iec_27001"}}, {}, restricting={"service_type", "standard"})
        with self.assertRaises(TypeError):
            matching.Restricting({"service_type"})  # type: ignore[call-arg]

    def test_every_opt_in_dimension_restricts(self) -> None:
        self.assertEqual(STANDARDS, {"service_type", "standard"})
        self.assertEqual(STANDARDS.opt_in, {"standard"})
        self.assertEqual(SCOPE.opt_in, frozenset())


class SqlMirrorsPython(TestCase):
    """The SQL function must agree with the Python rule on every combination of the real
    seeded terms in three dimensions, two of which restrict."""

    def setUp(self) -> None:
        _seed()
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

    def test_every_combination_agrees(self) -> None:
        refs = tuple(self.terms)
        subsets = [combo for n in range(len(refs) + 1) for combo in itertools.combinations(refs, n)]
        checked = 0
        for footprint_refs in subsets:
            FootprintTerm.objects.filter(tenant=self.tenant).delete()
            for ref in footprint_refs:
                FootprintTerm.objects.create(tenant=self.tenant, term=self.terms[ref])
            footprint = matching.footprint_of(self.tenant.id)
            self.assertEqual(footprint, _as_dict(footprint_refs))
            for record_refs in subsets:
                expected = matching.in_footprint(_as_dict(record_refs), footprint, restricting=self.restricting)
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


class OptInMirror(TestCase):
    """The opt-in half of the mirror (FP-01, D-36, migration 0006): a scope dimension and the
    seeded opt-in dimension `standard`, with a second standard beside ISO/IEC 27001 so that
    "names that term" and "names another standard" are told apart. Every combination of
    record and footprint terms must get the same answer from both, with the dimension's flag
    set as seeded and again with it cleared, and from a stored footprint that has no entry
    for the opt-in dimension at all."""

    def setUp(self) -> None:
        _seed()
        self.tenant = factories.tenant(slug="opt-in")
        tenancy.activate(self.tenant.id)
        self.standard = TermDimension.objects.get(key="standard")
        with library_write("test"):
            second = TaxonomyTerm.objects.create(dimension=self.standard, key="second_standard")
        self.terms = {
            "service_type:custody": tenant_lists_logic.term_by_ref("service_type", "custody"),
            "service_type:advice": tenant_lists_logic.term_by_ref("service_type", "advice"),
            "standard:iso_iec_27001": TaxonomyTerm.objects.get(dimension=self.standard, key="iso_iec_27001"),
            "standard:second_standard": second,
        }

    def _set_flag(self, restricts: bool) -> None:
        with library_write("test"):
            TermDimension.objects.filter(pk=self.standard.pk).update(restricts_footprint=restricts)

    def _every_combination_agrees(self) -> None:
        restricting = matching.restricting_dimensions()
        refs = tuple(self.terms)
        subsets = [combo for n in range(len(refs) + 1) for combo in itertools.combinations(refs, n)]
        hidden_by_the_opt_in_rule = 0
        for footprint_refs in subsets:
            FootprintTerm.objects.filter(tenant=self.tenant).delete()
            for ref in footprint_refs:
                FootprintTerm.objects.create(tenant=self.tenant, term=self.terms[ref])
            footprint = matching.footprint_of(self.tenant.id)
            for record_refs in subsets:
                record = _as_dict(record_refs)
                expected = matching.in_footprint(record, footprint, restricting=restricting)
                actual = matching.in_footprint_sql(self.tenant.id, [self.terms[ref].id for ref in record_refs])
                self.assertIs(actual, expected, f"record {record_refs} footprint {footprint_refs}")
                if "standard" in record and "standard" not in footprint:
                    self.assertFalse(expected, f"record {record_refs} footprint {footprint_refs}")
                    hidden_by_the_opt_in_rule += 1
        # Every record carrying a standard, against every footprint naming none: 12 x 4.
        self.assertEqual(hidden_by_the_opt_in_rule, 12 * 4)

    def test_every_combination_agrees_with_the_flag_as_seeded(self) -> None:
        self.assertTrue(self.standard.restricts_footprint)
        self.assertEqual(matching.opt_in_dimensions(), {"standard"})
        self._every_combination_agrees()

    def test_every_combination_agrees_with_the_flag_cleared(self) -> None:
        """Clearing the flag changes nothing: the kind, not the flag, makes it opt-in."""
        self._set_flag(False)
        self.assertIn("standard", matching.restricting_dimensions())
        self.assertEqual(matching.opt_in_dimensions(), {"standard"})
        self._every_combination_agrees()

    def test_a_retired_opt_in_dimension_restricts_nothing_in_either(self) -> None:
        iso = self.terms["standard:iso_iec_27001"]
        self.assertFalse(matching.in_footprint_sql(self.tenant.id, [iso.id]))
        with library_write("test"):
            TermDimension.objects.filter(pk=self.standard.pk).update(active=False)
        restricting = matching.restricting_dimensions()
        self.assertNotIn("standard", restricting)
        self.assertEqual(matching.opt_in_dimensions(), frozenset())
        self.assertTrue(matching.in_footprint({"standard": {"iso_iec_27001"}}, {}, restricting=restricting))
        self.assertTrue(matching.in_footprint_sql(self.tenant.id, [iso.id]))

    def test_restricting_dimensions_is_one_query(self) -> None:
        with self.assertNumQueries(1):
            restricting = matching.restricting_dimensions()
        self.assertEqual(restricting.opt_in, {"standard"})


class SeededStandard(TestCase):
    """The seeded standard ISO/IEC 27001 is active (D-36), now that the watch door refuses
    its term on a change whose authority is not a standards body (WAT-S11,
    `standard_term_only_on_standards`, apps/watch/tests_scenarios.py). Every door that
    resolves active terms names it: a scope request, an obligation's scope and a change's
    terms."""

    def setUp(self) -> None:
        _seed()
        self.iso = TaxonomyTerm.objects.get(dimension__key="standard", key="iso_iec_27001")

    def test_the_seeded_standard_is_active(self) -> None:
        self.assertTrue(self.iso.active)
        self.assertTrue(self.iso.dimension.active)
        self.assertEqual(matching.opt_in_dimensions(), {"standard"})

    def test_every_door_names_it(self) -> None:
        doors = {
            "a regulatory scope request": lambda: [term_by_ref("standard", "iso_iec_27001")],
            "an obligation's scope": lambda: terms_of(["standard:iso_iec_27001"]),
            "a change's terms": lambda: resolve_terms([self.iso.id]),
        }
        for door, resolve in doors.items():
            with self.subTest(door=door):
                self.assertEqual([term.id for term in resolve()], [self.iso.id])


class ListFilterReadsTheFootprintOnce(TestCase):
    """What a list filters with (`in_footprint_expression`, taxonomy 0008, NFR-02): the same
    verdict as `taxonomy_in_footprint` row by row, with the bank's guard read once per query
    rather than once per row. Before 0008 the function re-read the footprint for every row,
    which put the obligations list over its budget at 3000 obligations (r1-perf)."""

    def setUp(self) -> None:
        _seed()
        self.tenant = factories.tenant(slug="once")
        tenancy.activate(self.tenant.id)
        for ref in (("service_type", "custody"), ("client_category", "retail")):
            FootprintTerm.objects.create(tenant=self.tenant, term=tenant_lists_logic.term_by_ref(*ref))
        # Every term, read as a record carrying that one term.
        own = Func(F("id"), template="ARRAY[%(expressions)s]", output_field=ArrayField(UUIDField()))
        self.rows = TaxonomyTerm.objects.annotate(admitted=matching.in_footprint_expression(self.tenant.id, own))

    def test_it_agrees_with_the_function_on_every_term(self) -> None:
        verdicts = dict(self.rows.values_list("id", "admitted"))
        self.assertGreater(len(verdicts), 10)
        self.assertIn(False, verdicts.values(), "the footprint above hides some terms")
        for term_id, admitted in verdicts.items():
            self.assertIs(admitted, matching.in_footprint_sql(self.tenant.id, [term_id]), term_id)

    def test_the_guard_runs_once_per_query(self) -> None:
        sql, params = self.rows.query.sql_with_params()
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}", params)
            plan = cursor.fetchone()[0][0]["Plan"]
        guards = [node for node in _nodes(plan) if node.get("Function Name") == "taxonomy_footprint_guard"]
        self.assertEqual(len(guards), len(matching.GUARD_TEMPLATES))
        for node in guards:
            self.assertEqual(node["Parent Relationship"], "InitPlan")
            self.assertEqual(node["Actual Loops"], 1)
        self.assertGreater(plan["Actual Rows"], 10, "the guard ran once for many rows")


def _nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)

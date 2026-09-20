"""The chunk 5 shared fixtures (`c5-integration-scenarios`).

Ten later tasks build their scenario tests on `apps/watch/testing.py`,
`apps/cases/testing.py` and `apps/agents/testing.py`, so each builder is proved here to
produce a row the model's own constraints accept — not in each of those ten tasks, and not
by being used and hoped for.

Three properties matter beyond "it saves":

- **Deterministic.** Keys come from a counter and dates from a fixed anchor, never from
  `random` or from "now", so a fixture cannot drift into or out of a window as the clock
  moves (playbook 8.3).
- **Through the real writer.** Every library row goes through `watch_write()` and every
  tenant row is written with its tenant activated. A fixture that went round either would
  make the guard that protects production untrue in every test that used it.
- **It hides nothing.** Building a change with two banks present creates no case, because
  CAS-01's "exactly one case per bank" is `c5-cases-creation`'s to prove.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import transaction
from django.test import TestCase

from apps.agents import testing as agent_build
from apps.agents.models import AgentRun, RunStatus
from apps.cases import testing as case_build
from apps.cases.models import CaseLinkDecision, CaseObligationLink, ChangeCase
from apps.library import testing as build
from apps.library.models import Obligation
from apps.shared import tenancy
from apps.shared.tenancy import LibraryWriteRefused
from apps.taxonomy.matching import footprint_of
from apps.taxonomy.models import ChangeType, Flag, SourceKind, Urgency
from apps.watch import testing as watch_build
from apps.watch.models import (
    ChangeDocument,
    ChangeEvent,
    ChangeObligation,
    ChangeTerm,
    CheckStatus,
    RegulatoryChange,
    Source,
    SourceCheckKind,
)


@contextmanager
def _activate(tenant_id: uuid.UUID) -> Iterator[None]:
    """`tenancy.activate()` inside a transaction, as every tenant read needs: the policy
    reads `app.tenant_id` and an unset value matches no rows (playbook 14)."""
    with transaction.atomic():
        tenancy.activate(tenant_id)
        yield


def an_obligation() -> Obligation:
    """A library obligation from the prototype's own data, so a link points at something a
    person would recognise."""
    instrument = build.instrument(key="fffs-2017-2", short_name="FFFS 2017:2", regime="regime:securities")
    return build.obligation(
        instrument, key="fffs-2017-2-11-4", titles={"en": "Assess the quality of investment research paid for"}
    )


class WatchBuilderTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()

    def test_the_reference_seed_gives_every_key_chunk_five_names(self) -> None:
        """The vocabulary rows come from the product's own seeds, so no test invents a key
        the API would refuse (AC-WAT2)."""
        self.assertEqual(ChangeType.objects.filter(key="adopted").count(), 1)
        self.assertEqual(SourceKind.objects.filter(key="authority_site").count(), 1)
        self.assertEqual(Flag.objects.filter(key="advice_perimeter").count(), 1)
        self.assertEqual({row.key for row in Urgency.objects.all()} & {"act_now", "monitor"}, {"act_now", "monitor"})
        self.assertIsNotNone(watch_build.term("regime:securities"))

    def test_the_seed_is_idempotent(self) -> None:
        before = Source.objects.count()
        watch_build.seed_watch_reference()
        watch_build.seed_watch_reference()
        self.assertEqual(Source.objects.count(), before)

    def test_a_source_is_registered_with_its_cadence_and_no_owner(self) -> None:
        row = watch_build.source()
        self.assertTrue(row.active)
        self.assertEqual(row.check_frequency, "weekly")
        self.assertIsNone(row.owner_tenant_id, "WAT-06's column stays NULL in R1")

    def test_a_successful_check_carries_items_and_a_failed_one_carries_an_error(self) -> None:
        registry = watch_build.source()
        ok = watch_build.source_check(registry)
        failed = watch_build.source_check(registry, status=CheckStatus.FAILED, error="502 from the publisher")
        self.assertEqual((ok.status, ok.items_found), ("ok", 3))
        self.assertEqual((failed.status, failed.items_found), ("failed", 0))
        self.assertEqual(failed.error, "502 from the publisher")

    def test_a_recheck_names_the_record_it_re_checked_and_a_sweep_names_none(self) -> None:
        """The check constraint of `source_check` refuses either half alone, so the builder
        has to get both right (AGT-01, item 3)."""
        registry = watch_build.source()
        obligation = an_obligation()
        recheck = watch_build.source_check(registry, kind=SourceCheckKind.RECHECK, subject=obligation)
        sweep = watch_build.source_check(registry)
        self.assertEqual((recheck.subject_type, recheck.subject_id), ("obligation", obligation.id))
        self.assertEqual((sweep.subject_type, sweep.subject_id), ("", None))

    def test_a_change_is_a_valid_in_scope_record(self) -> None:
        row = watch_build.change()
        self.assertEqual(row.status, "active")
        self.assertEqual(row.origin, "agent")
        self.assertEqual(row.authority_label, "Finansinspektionen")
        self.assertEqual(getattr(row.suggested_urgency, "key", None), "act_now")

    def test_two_changes_get_two_stable_keys(self) -> None:
        """`stable_key` is unique and is the merge key of AC-WAT1, so a builder that reused
        one would turn every second build into a merge."""
        self.assertNotEqual(watch_build.change().stable_key, watch_build.change().stable_key)

    def test_the_builders_are_deterministic_and_anchored(self) -> None:
        """Nothing is derived from `now()`: two runs of the suite see the same dates."""
        row = watch_build.change_with_timeline()
        self.assertEqual(row.published_on, datetime.date(2026, 9, 15))
        self.assertEqual(row.first_seen_at, watch_build.ANCHOR)
        self.assertEqual(
            [entry.event_date for entry in row.events.all()],
            [datetime.date(2026, 6, 1), datetime.date(2026, 10, 1)],
        )

    def test_a_change_with_a_timeline_carries_its_pages_terms_and_flags(self) -> None:
        row = watch_build.change_with_timeline()
        self.assertEqual(ChangeEvent.objects.filter(change=row).count(), 2)
        self.assertEqual(ChangeDocument.objects.filter(change=row, is_primary=True).count(), 1)
        links = list(ChangeTerm.objects.filter(change=row))
        self.assertEqual(len(links), 2)
        self.assertEqual({link.term is not None for link in links}, {True, False}, "one term and one flag")

    def test_a_term_link_names_exactly_one_of_a_term_and_a_flag(self) -> None:
        row = watch_build.change()
        with self.assertRaises(ValueError):
            watch_build.term_link(row)
        with self.assertRaises(ValueError):
            watch_build.term_link(row, term_ref="regime:securities", flag_key="ai")

    def test_every_classification_arrives_as_a_suggestion(self) -> None:
        """WAT-03: an agent's classification is a suggestion with a confidence until a
        library editor confirms it, and the assertion every watch test repeats says so."""
        row = watch_build.change_with_timeline()
        for link in ChangeTerm.objects.filter(change=row):
            with self.subTest(link=str(link)):
                self.assertTrue(watch_build.is_a_suggestion(link))
        obligation_link = watch_build.obligation_link(row, an_obligation())
        self.assertTrue(watch_build.is_a_suggestion(obligation_link))
        obligation_link.refresh_from_db()
        self.assertEqual(obligation_link.confidence, Decimal("0.820"))

    def test_a_builder_cannot_write_a_watch_row_outside_the_door(self) -> None:
        """The builders open `watch_write()` and the model's own fence is what makes that
        necessary: the same create outside it is refused (PRO-01)."""
        with self.assertRaises(LibraryWriteRefused):
            RegulatoryChange.objects.create(
                stable_key="outside-the-door",
                title="No",
                change_type=ChangeType.objects.get(key="adopted"),
                authority_label="Finansinspektionen",
                source_label="x",
                source_url="https://www.fi.se/",
                origin="agent",
            )


class AgentBuilderTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()

    def test_an_agent_key_is_a_platform_key_bound_to_its_agent(self) -> None:
        """ID-10, rule 13: a key bound to an agent is the platform's, and no tenant route
        creates one, so it carries no tenant."""
        key = agent_build.agent_key()
        self.assertIsNone(key.row.tenant_id)
        self.assertEqual(key.row.agent_id, key.agent.id)
        self.assertTrue(key.plain_key)

    def test_a_platform_run_carries_no_tenant(self) -> None:
        run = agent_build.platform_run()
        self.assertIsNone(run.tenant_id)
        self.assertEqual(run.status, RunStatus.RUNNING.value)
        self.assertEqual(run.model, agent_build.SWEEPER_MODEL)

    def test_a_tenant_key_cannot_open_a_platform_run(self) -> None:
        """`AgentRun.save()` copies the key's tenant, so a tenant-bound key would quietly
        produce a tenant run — a shape R1 does not have (AGT-01, item 14)."""
        tenants = case_build.two_tenants_with_different_footprints()
        key = agent_build.tenant_key(tenants.inside)
        with self.assertRaises(ValueError):
            agent_build.platform_run(key=key)

    def test_a_watch_key_holds_no_scope_that_reaches_the_inventory(self) -> None:
        resources = {scope.split(":")[0] for scope in agent_build.WATCH_SCOPES}
        self.assertEqual(resources & {"instruments", "provisions", "obligations"}, set())

    def test_a_change_points_at_the_run_that_registered_it(self) -> None:
        run = agent_build.platform_run()
        row = watch_build.change_with_timeline(run=run)
        self.assertEqual(row.agent_run_id, run.id)
        check = watch_build.source_check(watch_build.source(), run=run)
        self.assertEqual(check.agent_run_id, run.id)
        self.assertEqual(AgentRun.objects.filter(pk=run.pk).count(), 1)


class CaseBuilderTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()

    def test_two_tenants_have_footprints_that_do_not_overlap(self) -> None:
        tenants = case_build.two_tenants_with_different_footprints()
        with _activate(tenants.inside.id):
            inside = footprint_of(tenants.inside.id)
        with _activate(tenants.outside.id):
            outside = footprint_of(tenants.outside.id)
        self.assertEqual(inside, {"regime": {"securities"}})
        self.assertEqual(outside, {"regime": {"aml"}})

    def test_building_a_change_with_two_tenants_present_creates_no_case(self) -> None:
        """CAS-01 is `c5-cases-creation`'s to prove, so the fixture must not quietly make
        the cases the scenario is supposed to assert into existence."""
        tenants = case_build.two_tenants_with_different_footprints()
        row = watch_build.change_with_timeline()
        self.assertEqual(
            set(watch_build.cases_per_tenant(row, [tenants.inside, tenants.outside]).values()), {0}
        )

    def test_a_case_is_created_in_the_new_category_with_an_unconfirmed_urgency(self) -> None:
        tenants = case_build.two_tenants_with_different_footprints()
        row = watch_build.change_with_timeline()
        built = case_build.case(tenants.inside, row)
        self.assertEqual(built.status, "new")
        self.assertFalse(built.urgency_confirmed)
        self.assertEqual(
            watch_build.cases_per_tenant(row, [tenants.inside, tenants.outside]),
            {tenants.inside: 1, tenants.outside: 0},
        )

    def test_each_bank_gets_its_own_case_and_sees_no_other(self) -> None:
        tenants = case_build.two_tenants_with_different_footprints()
        row = watch_build.change_with_timeline()
        case_build.case(tenants.inside, row, footprint_match=True)
        case_build.case(tenants.outside, row, footprint_match=False)
        self.assertEqual(
            watch_build.cases_per_tenant(row, [tenants.inside, tenants.outside]),
            {tenants.inside: 1, tenants.outside: 1},
            "one case per bank per change, each counted inside its own tenant (CAS-01)",
        )
        with _activate(tenants.inside.id):
            self.assertEqual([case.footprint_match for case in ChangeCase.objects.filter(change=row)], [True])

    def test_a_link_decision_writes_one_tenant_row_and_no_library_row(self) -> None:
        tenants = case_build.two_tenants_with_different_footprints()
        row = watch_build.change_with_timeline()
        obligation = an_obligation()
        watch_build.obligation_link(row, obligation)
        before = ChangeObligation.objects.filter(change=row).count()
        built = case_build.case(tenants.inside, row)
        decision = case_build.link_decision(built, obligation, decision=CaseLinkDecision.REMOVED)
        self.assertEqual(decision.decision, "removed")
        self.assertEqual(ChangeObligation.objects.filter(change=row).count(), before)
        with _activate(tenants.outside.id):
            self.assertEqual(CaseObligationLink.objects.count(), 0)


class NoProductionModuleImportsAFixture(TestCase):
    """The compliance lint proves it across the tree; this names the three modules chunk 5
    added, so a later task that reaches for a builder from production code fails here with
    the reason rather than in a lint run nobody reads."""

    def test_the_fixtures_are_test_only(self) -> None:
        import pathlib

        apps_dir = pathlib.Path(__file__).resolve().parent.parent
        offenders = []
        for path in sorted(apps_dir.rglob("*.py")):
            rel = path.relative_to(apps_dir).as_posix()
            if "/migrations/" in rel or rel.split("/")[-1].startswith("tests_") or rel.endswith("/testing.py"):
                continue
            source = path.read_text(encoding="utf-8")
            for module in ("apps.watch.testing", "apps.cases.testing", "apps.agents.testing"):
                if module in source:
                    offenders.append(f"apps/{rel} imports {module}")
        self.assertEqual(offenders, [], "a fixture reached production code:\n  " + "\n  ".join(offenders))

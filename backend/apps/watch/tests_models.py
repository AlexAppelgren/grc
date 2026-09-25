"""The watch tables (WAT-01 to WAT-04, WAT-07, AGT-01; schema v0.3 section 4).

Seven library tables and no tenant column: what a bank thinks about a change lives on
`change_case`, which the cases app owns. These tests pin the shape the rest of chunk 5
builds on — the vocabulary links, the suggestion columns, the partial dates, the merge
key, and the constraints that keep an agent's write honest.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.agents.models import Agent, AgentKind, AgentRun
from apps.library import testing as build
from apps.library.models import Authority, DatePrecision, Obligation, SubjectType
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals.models import OriginType
from apps.shared import factories
from apps.shared.tenancy import LibraryModel, LibraryWriteRefused, library_write
from apps.taxonomy.models import ChangeType, Flag, SourceKind, Urgency
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.watch.models import (
    WATCH_MODELS,
    ChangeDocument,
    ChangeEvent,
    ChangeObligation,
    ChangeStatus,
    ChangeTerm,
    CheckFrequency,
    CheckStatus,
    RegulatoryChange,
    Source,
    SourceCheck,
    SourceCheckKind,
)
from apps.watch.write import watch_write

D = datetime.date
REASON = "test builder"
UTC = datetime.UTC


def seed_reference() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_taxonomy_terms()
    seed_authorities()


class WatchZoneTestCase(TestCase):
    """Builders every watch test shares. Each one writes through the watch door."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()

    def source(self, **overrides: Any) -> Source:  # compliance: allow-kwargs test helper forwarding model fields
        fields: dict[str, Any] = {
            "name": "Finansinspektionen news",
            "url": "https://www.fi.se/en/published/news/",
            "kind": SourceKind.objects.get(key="authority_site"),
            "authority": Authority.objects.get(key="fi"),
            "check_frequency": CheckFrequency.WEEKLY.value,
        }
        with watch_write(REASON):
            return Source.objects.create(**{**fields, **overrides})

    def change(self, **overrides: Any) -> RegulatoryChange:  # compliance: allow-kwargs test helper forwarding model fields
        fields: dict[str, Any] = {
            "stable_key": "dora-standards",
            "title": "DORA technical standards",
            "change_type": ChangeType.objects.get(key="adopted"),
            "authority_label": "EU Council and Parliament",
            "summary": "The standards are adopted.",
            "source_label": "EUR-Lex",
            "source_url": "https://eur-lex.europa.test/dora",
            "origin": OriginType.AGENT.value,
        }
        with watch_write(REASON):
            return RegulatoryChange.objects.create(**{**fields, **overrides})

    def flag(self) -> Flag:
        return Flag.objects.get(key="ai")

    def obligation(self) -> Obligation:
        suffix = uuid.uuid4().hex[:6]
        instrument = build.instrument(key=f"lvm-{suffix}", short_name="LVM", regime="regime:securities")
        return build.obligation(instrument, key=f"lvm-{suffix}-1", titles={"en": "Keep research criteria"})

    def agent_run(self) -> AgentRun:
        with library_write(REASON):
            agent = Agent.objects.create(key=f"sweeper-{uuid.uuid4().hex[:6]}", kind=AgentKind.WATCH.value, current_version=1)
        tenant = factories.tenant(slug=f"run-{uuid.uuid4().hex[:8]}")
        key = factories.api_key(tenant, scopes=("sources:write",)).row
        return AgentRun.objects.create(agent=agent, api_key=key, model="mock", pipeline_version="0.4")


class WatchZoneTests(WatchZoneTestCase):
    """Every watch table is a library table, written only through the watch door."""

    def test_every_watch_model_is_a_library_model_with_no_tenant_column(self) -> None:
        self.assertEqual(len(WATCH_MODELS), 7)
        for model in WATCH_MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, LibraryModel))
                columns = {field.column for field in model._meta.concrete_fields}
                self.assertNotIn("tenant_id", columns, "a bank's judgement lives on change_case, never here")

    def test_only_source_carries_the_tenant_private_column_of_wat_06(self) -> None:
        # WAT-06 is R3; the column exists now so the row-level shape is final (INPUT_DELTAS §5).
        carriers = {model.__name__ for model in WATCH_MODELS if "owner_tenant_id" in {f.column for f in model._meta.concrete_fields}}
        self.assertEqual(carriers, {"Source"})
        self.assertIsNone(self.source().owner_tenant_id)

    def test_a_watch_row_is_refused_outside_the_door(self) -> None:
        with self.assertRaises(LibraryWriteRefused):
            Source.objects.create(name="Refused", kind=SourceKind.objects.get(key="authority_site"))


class SourceRegistryTests(WatchZoneTestCase):
    """WAT-01: the registry and the coverage log."""

    def test_a_source_names_its_kind_as_a_row_and_its_cadence_as_a_kind(self) -> None:
        row = self.source()
        self.assertEqual(row.kind.key, "authority_site")
        self.assertEqual(row.check_frequency, "weekly")
        self.assertTrue(row.active)

    def test_two_sources_never_share_a_name(self) -> None:
        self.source()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.source(url="https://www.fi.se/other")

    def test_a_check_records_its_run_its_result_and_what_it_found(self) -> None:
        # The source first: a shared source is written with no tenant activated, and
        # building a run activates its key's tenant for the rest of the transaction.
        source = self.source()
        run = self.agent_run()
        with watch_write(REASON):
            check = SourceCheck.objects.create(
                source=source,
                agent_run=run,
                checked_at=datetime.datetime(2026, 9, 20, 6, 0, tzinfo=UTC),
                status=CheckStatus.OK.value,
                items_found=3,
            )
        self.assertEqual(check.kind, SourceCheckKind.SWEEP.value)
        self.assertEqual(check.agent_run_id, run.id)
        self.assertEqual((check.items_found, check.error), (3, ""))

    def test_the_newest_check_comes_first(self) -> None:
        source = self.source()
        with watch_write(REASON):
            for day in (18, 20, 19):
                SourceCheck.objects.create(
                    source=source,
                    checked_at=datetime.datetime(2026, 9, day, 6, 0, tzinfo=UTC),
                    status=CheckStatus.OK.value,
                )
        self.assertEqual([check.checked_at.day for check in SourceCheck.objects.all()], [20, 19, 18])

    def test_a_recheck_names_the_library_record_it_re_checked(self) -> None:
        subject = uuid.uuid4()
        with watch_write(REASON):
            check = SourceCheck.objects.create(
                source=self.source(),
                status=CheckStatus.OK.value,
                kind=SourceCheckKind.RECHECK.value,
                subject_type=SubjectType.OBLIGATION.value,
                subject_id=subject,
            )
        self.assertEqual(check.subject_id, subject)

    def test_a_recheck_without_a_subject_is_refused(self) -> None:
        source = self.source()
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            SourceCheck.objects.create(source=source, status=CheckStatus.OK.value, kind=SourceCheckKind.RECHECK.value)

    def test_a_sweep_naming_a_subject_is_refused(self) -> None:
        source = self.source()
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            SourceCheck.objects.create(
                source=source,
                status=CheckStatus.OK.value,
                subject_type=SubjectType.OBLIGATION.value,
                subject_id=uuid.uuid4(),
            )


class RegulatoryChangeTests(WatchZoneTestCase):
    """WAT-02, WAT-07: one row per reform, keyed by a stable key, with a timeline."""

    def test_the_stable_key_is_the_merge_key(self) -> None:
        self.change()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.change(title="A second sighting of the same reform")

    def test_a_change_reads_its_type_and_urgency_from_vocabulary_rows(self) -> None:
        urgency = Urgency.objects.get(key="act_now")
        change = self.change(suggested_urgency=urgency)
        self.assertEqual(change.change_type.key, "adopted")
        self.assertEqual(change.suggested_urgency_id, urgency.pk)
        self.assertEqual(change.status, ChangeStatus.ACTIVE.value)

    def test_partial_dates_keep_their_precision(self) -> None:
        change = self.change(
            published_on=D(2026, 3, 1),
            published_precision=DatePrecision.MONTH.value,
            key_date=D(2027, 1, 1),
            key_date_precision=DatePrecision.QUARTER.value,
            key_date_label="Transition ends",
        )
        self.assertEqual((change.published_precision, change.key_date_precision), ("month", "quarter"))

    def test_a_change_with_no_key_date_yet_sorts_after_the_dated_ones(self) -> None:
        """PostgreSQL sorts nulls first on a descending column, so the default feed order
        would open with every change whose date is not known yet."""
        far = self.change(stable_key="far", key_date=D(2027, 6, 1))
        undated = self.change(stable_key="undated", key_date=None)
        near = self.change(stable_key="near", key_date=D(2026, 12, 1))
        self.assertEqual(
            [row.stable_key for row in RegulatoryChange.objects.all()],
            [far.stable_key, near.stable_key, undated.stable_key],
        )

    def test_a_change_never_supersedes_itself(self) -> None:
        change = self.change()
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            RegulatoryChange.objects.filter(pk=change.pk).update(superseded_by=change)

    def test_the_timeline_reads_in_sort_order(self) -> None:
        change = self.change()
        with watch_write(REASON):
            for order, label in ((2, "In force"), (0, "Consultation"), (1, "Adopted")):
                ChangeEvent.objects.create(change=change, label=label, sort_order=order)
        self.assertEqual([event.label for event in change.events.all()], ["Consultation", "Adopted", "In force"])

    def test_a_document_is_linked_once_per_url_and_carries_its_screening_hits(self) -> None:
        change = self.change()
        with watch_write(REASON):
            document = ChangeDocument.objects.create(
                change=change,
                url="https://eur-lex.europa.test/dora/page",
                title="The adopted standards",
                publisher="EUR-Lex",
                content_hash="0" * 64,
                is_primary=True,
                risk_flags=["embedded_instructions"],
            )
        self.assertEqual(document.risk_flags, ["embedded_instructions"])
        self.assertFalse(document.is_duplicate)
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            ChangeDocument.objects.create(change=change, url=document.url, is_duplicate=True)


class ClassificationTests(WatchZoneTestCase):
    """WAT-03, WAT-04: flags, scope terms and obligation links stay suggestions until a
    person confirms them, and each carries the agent's confidence."""

    def test_a_flag_and_a_scope_term_are_links_to_rows_and_no_column_holds_an_array_of_them(self) -> None:
        change = self.change()
        with watch_write(REASON):
            flag = ChangeTerm.objects.create(change=change, flag=self.flag(), confidence="0.900")
            scope = ChangeTerm.objects.create(change=change, term=build.term("regime:securities"), confidence="0.400")
        self.assertTrue(flag.suggested)
        self.assertTrue(scope.suggested)
        self.assertEqual([link.id for link in change.term_links.all()], [flag.id, scope.id])
        self.assertNotIn(
            "flags",
            {field.column for field in RegulatoryChange._meta.concrete_fields},
            "flags are rows of the flag list, never a text[] (INPUT_DELTAS §1)",
        )

    def test_a_link_names_exactly_one_of_a_flag_and_a_term(self) -> None:
        change = self.change()
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            ChangeTerm.objects.create(change=change)
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            ChangeTerm.objects.create(change=change, flag=self.flag(), term=build.term("regime:securities"))

    def test_the_same_term_is_linked_once(self) -> None:
        change = self.change()
        with watch_write(REASON):
            ChangeTerm.objects.create(change=change, term=build.term("regime:securities"))
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            ChangeTerm.objects.create(change=change, term=build.term("regime:securities"))

    def test_a_confidence_outside_zero_to_one_is_refused(self) -> None:
        change = self.change()
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            ChangeTerm.objects.create(change=change, flag=self.flag(), confidence="1.500")

    def test_a_suggestion_carries_no_confirmation_and_a_confirmed_link_names_the_person(self) -> None:
        change = self.change()
        person = factories.user()
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            ChangeTerm.objects.create(change=change, flag=self.flag(), confirmed_by=person)
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            ChangeTerm.objects.create(change=change, flag=self.flag(), suggested=False)
        with watch_write(REASON):
            confirmed = ChangeTerm.objects.create(
                change=change,
                flag=self.flag(),
                suggested=False,
                confirmed_by=person,
                confirmed_at=datetime.datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
            )
        self.assertEqual(confirmed.confirmed_by_id, person.id)

    def test_an_obligation_link_carries_its_origin_its_confidence_and_its_confirmation(self) -> None:
        change, obligation = self.change(), self.obligation()
        with watch_write(REASON):
            link = ChangeObligation.objects.create(
                change=change, obligation=obligation, origin=OriginType.AGENT.value, confidence="0.900"
            )
        self.assertIsNone(link.confirmed_at)
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            ChangeObligation.objects.create(change=change, obligation=obligation, origin=OriginType.USER.value)

    def test_an_obligation_link_without_a_confidence_sorts_after_the_scored_ones(self) -> None:
        """A person's link carries no confidence; on a descending sort PostgreSQL would
        otherwise put it ahead of the agent's most confident one."""
        change = self.change()
        scored, unscored = self.obligation(), self.obligation()
        with watch_write(REASON):
            ChangeObligation.objects.create(
                change=change, obligation=unscored, origin=OriginType.USER.value, confidence=None
            )
            ChangeObligation.objects.create(
                change=change, obligation=scored, origin=OriginType.AGENT.value, confidence="0.200"
            )
        self.assertEqual(
            [link.obligation_id for link in change.obligation_links.all()], [scored.pk, unscored.pk]
        )

    def test_an_obligation_link_is_confirmed_by_a_person_at_a_time(self) -> None:
        change, obligation = self.change(), self.obligation()
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write(REASON):
            ChangeObligation.objects.create(
                change=change, obligation=obligation, origin=OriginType.AGENT.value, confirmed_by=factories.user()
            )

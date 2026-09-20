"""The case tables (CAS-01, WAT-04, WAT-05; schema v0.3 `change_case`; INPUT_DELTAS §8).

Two tenant tables and nothing shared: a bank's case for a library change, and that bank's
own decision about a suggested obligation link. These tests pin the shape the rest of
chunk 5 and the whole of chunk 9 build on — one case per bank per change, an urgency that
is a vocabulary row and not an enum, a confirmation that names a person, and a link
decision that leaves the library alone.

The library half of each assertion matters as much as the tenant half: `c5-cases-creation`
and `c5-cases-so-what-and-links` must never reach `change_obligation`, so the proof that
they cannot is here, beside the models, rather than in the task that writes them.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.cases.models import CaseLinkDecision, CaseObligationLink, ChangeCase
from apps.library import testing as build
from apps.library.models import Obligation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals.models import OriginType
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.shared.tenancy import TenantModel
from apps.taxonomy.models import CaseStatusCategory, ChangeType, Urgency
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.watch.models import ChangeObligation, RegulatoryChange
from apps.watch.write import watch_write

REASON = "test builder"


class CaseZoneTestCase(TestCase):
    """Builders the case tests share. The library half goes through the watch door and the
    library builders; the tenant half is written with its tenant activated, because
    FORCE ROW LEVEL SECURITY applies to the test runner's own connection too."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        seed_authorities()

    def setUp(self) -> None:
        self.tenant_a = factories.tenant(slug=f"case-a-{uuid.uuid4().hex[:8]}")
        self.tenant_b = factories.tenant(slug=f"case-b-{uuid.uuid4().hex[:8]}")
        self.change = self.regulatory_change()
        self.urgency = Urgency.objects.get(key="act_now")

    def regulatory_change(self, **overrides: Any) -> RegulatoryChange:  # compliance: allow-kwargs test helper forwarding model fields
        fields: dict[str, Any] = {
            "stable_key": f"chg-fi-2026-research-payments-{uuid.uuid4().hex[:6]}",
            "title": "FI adopts amended rules on paying for investment research",
            "change_type": ChangeType.objects.get(key="adopted"),
            "authority_label": "Finansinspektionen",
            "summary": "FI's board decided to amend three regulations in the securities area.",
            "source_label": "Finansinspektionen",
            "source_url": "https://www.fi.se/",
            "origin": OriginType.AGENT.value,
        }
        with watch_write(REASON):
            return RegulatoryChange.objects.create(**{**fields, **overrides})

    def case(self, tenant: Tenant, **overrides: Any) -> ChangeCase:  # compliance: allow-kwargs test helper forwarding model fields
        fields: dict[str, Any] = {
            "tenant": tenant,
            "change": self.change,
            "urgency": self.urgency,
            "footprint_match": True,
        }
        with transaction.atomic():
            tenancy.activate(tenant.id)
            return ChangeCase.objects.create(**{**fields, **overrides})

    def obligation(self) -> Obligation:
        suffix = uuid.uuid4().hex[:6]
        instrument = build.instrument(key=f"fffs-2017-2-{suffix}", short_name="FFFS 2017:2", regime="regime:securities")
        return build.obligation(
            instrument, key=f"fffs-2017-2-{suffix}-1", titles={"en": "Assess the quality of investment research paid for"}
        )


class CaseZoneTests(CaseZoneTestCase):
    def test_both_tables_are_tenant_tables_carrying_a_tenant_column(self) -> None:
        for model in (ChangeCase, CaseObligationLink):
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, TenantModel))
                self.assertIn("tenant_id", {field.column for field in model._meta.concrete_fields})

    def test_exactly_one_case_per_tenant_per_change(self) -> None:
        """CAS-01 rests on this constraint: a second registration of the same change must
        find the case, never create another one."""
        self.case(self.tenant_a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            ChangeCase.objects.create(
                tenant=self.tenant_a, change=self.change, urgency=self.urgency, footprint_match=True
            )

    def test_each_tenant_has_its_own_case_for_the_same_change(self) -> None:
        own = self.case(self.tenant_a, footprint_match=True)
        other = self.case(self.tenant_b, footprint_match=False)
        self.assertNotEqual(own.id, other.id)
        self.assertEqual({own.footprint_match, other.footprint_match}, {True, False})

    def test_a_case_is_created_in_the_new_category_with_an_unconfirmed_urgency(self) -> None:
        """Alex's item 1: the card shows a suggested urgency before triage, so the case
        carries the change's suggestion and says it is not yet a person's decision."""
        case = self.case(self.tenant_a)
        self.assertEqual(case.status, CaseStatusCategory.NEW.value)
        self.assertFalse(case.urgency_confirmed)
        self.assertEqual(case.urgency.key, "act_now")

    def test_urgency_is_a_vocabulary_row_and_carries_no_tone(self) -> None:
        """Urgency is a library vocabulary an admin may extend; its tone follows the row's
        ordinal and is never stored on the case (NFR-03, playbook 15)."""
        field = ChangeCase._meta.get_field("urgency")
        self.assertEqual(field.related_model, Urgency)
        columns = {f.column for f in ChangeCase._meta.concrete_fields}
        self.assertEqual(columns & {"tone", "colour", "color", "urgency_label"}, set())

    def test_status_holds_only_the_seven_categories_and_no_sub_status(self) -> None:
        """Sub-statuses are a bank's own rows inside a category and are chunk 9; no column
        for one exists yet, so nothing can quietly start storing one (VOC-04, D-13)."""
        choices = {value for value, _ in ChangeCase._meta.get_field("status").choices or []}
        self.assertEqual(choices, {member.value for member in CaseStatusCategory})
        self.assertNotIn("sub_status", {f.column for f in ChangeCase._meta.concrete_fields})

    def test_the_chunk_nine_workflow_columns_are_not_built_yet(self) -> None:
        """R1 is creation, the footprint match and the So what. Triage, dismissal,
        sign-off and the close arrive with chunk 9 (`c9-case-models`, INPUT_DELTAS §8)."""
        columns = {f.column for f in ChangeCase._meta.concrete_fields}
        later = {
            "triaged_by_id", "triaged_at", "dismissed_reason", "dismissed_by_id", "dismissed_at",
            "signoff_requested_by_id", "signoff_requested_at", "signed_off_by_id", "close_reason",
            "closed_note", "closed_at",
        }  # fmt: skip
        self.assertEqual(columns & later, set())

    def test_the_case_carries_no_version_so_no_write_can_answer_a_stale_write(self) -> None:
        """CAS-08's concurrency is chunk 9. Until then no case write takes `If-Match`, and
        this pins that the column that would make one meaningful does not exist yet."""
        self.assertNotIn("version", {f.column for f in ChangeCase._meta.concrete_fields})


class SoWhatConfirmationTests(CaseZoneTestCase):
    def test_a_confirmed_so_what_names_the_person_and_the_time(self) -> None:
        """WAT-05: AI output stays labelled until a person confirms it, so "confirmed" can
        never be a flag with nobody behind it."""
        person = factories.member_user(self.tenant_a, roles=("compliance_officer",))
        case = self.case(self.tenant_a, so_what_text="Confirm the research criteria before 1 October.")
        self.assertFalse(case.so_what_confirmed)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            case.so_what_confirmed = True
            case.so_what_confirmed_by = person
            case.so_what_confirmed_at = timezone.now()
            case.save()
        case.refresh_from_db()
        self.assertEqual(case.so_what_confirmed_by_id, person.id)

    def test_a_confirmation_without_a_person_is_refused(self) -> None:
        case = self.case(self.tenant_a, so_what_text="A draft.")
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            ChangeCase.objects.filter(pk=case.pk).update(so_what_confirmed=True)

    def test_one_banks_confirmation_leaves_another_banks_draft_alone(self) -> None:
        person = factories.member_user(self.tenant_a, roles=("compliance_officer",))
        mine = self.case(self.tenant_a, so_what_text="The library draft.")
        theirs = self.case(self.tenant_b, so_what_text="The library draft.")
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            mine.so_what_text = "Our own words."
            mine.so_what_confirmed = True
            mine.so_what_confirmed_by = person
            mine.so_what_confirmed_at = timezone.now()
            mine.save()
        with transaction.atomic():
            tenancy.activate(self.tenant_b.id)
            theirs.refresh_from_db()
        self.assertFalse(theirs.so_what_confirmed)
        self.assertEqual(theirs.so_what_text, "The library draft.")


class CaseObligationLinkTests(CaseZoneTestCase):
    def test_a_link_decision_writes_no_library_row(self) -> None:
        """WAT-04, ruling C: the library's own link is the library editor's. A bank
        accepting or removing one on its case changes nothing in `change_obligation`."""
        obligation = self.obligation()
        with watch_write(REASON):
            library_link = ChangeObligation.objects.create(
                change=self.change, obligation=obligation, origin=OriginType.AGENT.value, confidence=None
            )
        before = ChangeObligation.objects.filter(change=self.change).count()
        case = self.case(self.tenant_a)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CaseObligationLink.objects.create(
                tenant=self.tenant_a, case=case, obligation=obligation, decision=CaseLinkDecision.REMOVED.value
            )
        library_link.refresh_from_db()
        self.assertEqual(ChangeObligation.objects.filter(change=self.change).count(), before)
        self.assertFalse(library_link.confirmed_at)
        self.assertIsNone(library_link.confirmed_by_id)

    def test_a_removal_is_stored_rather_than_deleted(self) -> None:
        """The case file has to be able to say the bank looked at the link and said no."""
        obligation = self.obligation()
        case = self.case(self.tenant_a)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CaseObligationLink.objects.create(
                tenant=self.tenant_a, case=case, obligation=obligation, decision=CaseLinkDecision.REMOVED.value
            )
            stored = list(CaseObligationLink.objects.filter(case=case))
        self.assertEqual([row.decision for row in stored], [CaseLinkDecision.REMOVED.value])

    def test_one_decision_per_link(self) -> None:
        obligation = self.obligation()
        case = self.case(self.tenant_a)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CaseObligationLink.objects.create(
                tenant=self.tenant_a, case=case, obligation=obligation, decision=CaseLinkDecision.ACCEPTED.value
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CaseObligationLink.objects.create(
                tenant=self.tenant_a, case=case, obligation=obligation, decision=CaseLinkDecision.REMOVED.value
            )

    def test_another_banks_decision_is_invisible(self) -> None:
        """NFR-01: the decision is one bank's judgement and row-level security is what keeps
        it there, not a filter in Python."""
        obligation = self.obligation()
        mine = self.case(self.tenant_a)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CaseObligationLink.objects.create(
                tenant=self.tenant_a, case=mine, obligation=obligation, decision=CaseLinkDecision.ACCEPTED.value
            )
        with transaction.atomic():
            tenancy.activate(self.tenant_b.id)
            self.assertEqual(CaseObligationLink.objects.count(), 0)
            self.assertEqual(ChangeCase.objects.filter(pk=mine.pk).count(), 0)

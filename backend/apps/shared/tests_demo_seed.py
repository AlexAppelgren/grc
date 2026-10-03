"""The public demo's seed (apps/shared/demo_seed.py, D-120; design/public/README.md "The demo").

The demo shows the real library baseline and a made-up bank on top of it. Proved here, on one
seeding of the whole baseline per class (it takes minutes, so every check reads the same run):

- every library record arrived through an approved proposal of the baseline's agent, and an
  agent of another definition approved it, so it reads machine-confirmed naming both;
- nothing in the library app was written through the seed door, or outside a door;
- the library is the baseline, record for record, and no fixture of the E2E seed is in it;
- no " (E2E" mark is anywhere a visitor could read it;
- every row of the bank names only stable keys the library holds, and every regulatory change
  is a fact of the baseline: an instrument's own date, authority, page and duties;
- the bank's cases reach every category and carry what the case screens show;
- a second run files, approves and writes nothing new.

Operations exercised (the audit-on-write guard reads these names): none; the seed writes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

from django.apps import apps as django_apps
from django.db import connection, models
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cases.models import Action, ChangeCase, Evidence
from apps.collab.models import Comment, Participant
from apps.home.models import Briefing
from apps.identity.models import Membership, MembershipRole, User, WebAuthnCredential
from apps.library.models import Authority, Instrument, Obligation, ObligationVersion, Provision
from apps.proposals import baseline
from apps.proposals.models import Proposal, ProposalKind, ProposalStatus
from apps.register.models import ComplianceAssessment, Gap, Interpretation, InternalLink, TenantObligation, TenantObligationScope
from apps.shared import demo_seed, tenancy
from apps.shared.models import AuditEvent, Tenant
from apps.taxonomy.models import CaseStatusCategory
from apps.watch.models import ChangeEvent, ChangeObligation, RegulatoryChange
from apps.tenants.models import InternalItem, OrgUnit

FIXTURE_MARK = " (E2E"


@contextmanager
def doors_watched(writes: list[tuple[str, str]]) -> Iterator[None]:
    """Every library write the ORM makes, with the door the database was told it came
    through, as the trigger reads it (ADR 0058)."""
    real = tenancy._assert_library_write

    def watching(model_name: str) -> None:
        real(model_name)
        with connection.cursor() as cursor:
            cursor.execute("SELECT coalesce(current_setting(%s, true), '')", [tenancy.LIBRARY_DOOR_SETTING])
            writes.append((model_name, cursor.fetchone()[0]))

    with mock.patch.object(tenancy, "_assert_library_write", watching):
        yield


@override_settings(E2E_MODE=True)
class TheDemoSeed(TestCase):
    writes: list[tuple[str, str]]
    counts: dict[str, int]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.writes = []
        with doors_watched(cls.writes):
            cls.counts = demo_seed.seed_public_demo()

    def setUp(self) -> None:
        self.tenant = Tenant.objects.get(slug=demo_seed.TENANT.slug)
        tenancy.activate(self.tenant.id)

    def test_every_library_record_arrived_through_a_proposal_another_agent_approved(self) -> None:
        approved = Proposal.objects.filter(status=ProposalStatus.APPROVED.value)
        filed = approved.filter(kind__in=[ProposalKind.NEW_INSTRUMENT.value, ProposalKind.NEW_OBLIGATION.value])
        self.assertEqual(set(filed.values_list("proposed_by_agent__key", flat=True)), {baseline.AGENT_KEY})
        for proposal in approved:
            self.assertIsNotNone(proposal.reviewed_by_agent_id, "an agent approved it, not a person")
            self.assertNotEqual(proposal.reviewed_by_agent_id, proposal.proposed_by_agent_id)
            self.assertNotEqual(proposal.reviewed_by_api_key_id, proposal.proposed_by_api_key_id)
        self.assertEqual(set(approved.values_list("reviewed_by_agent__key", flat=True)), {demo_seed.CONFIRMING_AGENT})
        by_kind = {kind: set(filed.filter(kind=kind).values_list("payload__key", flat=True)) for kind in (ProposalKind.NEW_INSTRUMENT.value, ProposalKind.NEW_OBLIGATION.value)}
        self.assertEqual(set(Instrument.objects.values_list("stable_key", flat=True)), by_kind[ProposalKind.NEW_INSTRUMENT.value])
        self.assertEqual(set(Obligation.objects.values_list("stable_key", flat=True)), by_kind[ProposalKind.NEW_OBLIGATION.value])
        self.assertFalse(ObligationVersion.objects.filter(applied_by_proposal__isnull=True).exists())
        self.assertFalse(ObligationVersion.objects.exclude(applied_by_proposal__status=ProposalStatus.APPROVED.value).exists())
        confirmer = demo_seed._agent(demo_seed.CONFIRMING_AGENT)
        self.assertEqual(set(Instrument.objects.values_list("verified_origin", "verified_by_agent")), {("agent", confirmer.id)})
        self.assertEqual(set(ObligationVersion.objects.values_list("verified_origin", "verified_by_agent")), {("agent", confirmer.id)})

    def test_nothing_in_the_library_was_written_through_the_seed_door(self) -> None:
        reference = {Authority.__name__}
        inventory = {model.__name__ for model in django_apps.get_app_config("library").get_models() if issubclass(model, tenancy.LibraryModel)} - reference
        doors = Counter((model, door) for model, door in self.writes if model in inventory)
        self.assertTrue(doors, "the seed wrote the library")
        self.assertEqual({door for _model, door in doors}, {"proposal"}, f"library writes by door: {dict(doors)}")
        self.assertFalse(Provision.objects.exists(), "no provision without a person's approval")

    def test_the_library_is_the_baseline_and_holds_no_fixture(self) -> None:
        entries = baseline.load()
        self.assertEqual(set(Instrument.objects.values_list("stable_key", flat=True)), {e.key for e in entries if e.kind == baseline.INSTRUMENT})
        self.assertEqual(set(Obligation.objects.values_list("stable_key", flat=True)), {e.key for e in entries if e.kind == baseline.OBLIGATION})
        self.assertFalse(Instrument.objects.filter(stable_key="fffs-2026-11").exists(), "the E2E fixture's made-up instrument")

    def test_no_fixture_mark_anywhere(self) -> None:
        """Every text column of every table, read from the bank's zone and from the platform's."""
        columns = [
            (model, column)
            for model in django_apps.get_models()
            if model._meta.managed and not model._meta.proxy
            for column in model._meta.get_fields()
            if isinstance(column, (models.CharField, models.TextField)) and column.concrete
        ]
        for zone in (self.tenant.id, None):
            if zone is None:
                tenancy.clear_tenant()
            for model, column in columns:
                marked = model._default_manager.filter(**{f"{column.name}__contains": FIXTURE_MARK})
                self.assertFalse(marked.exists(), f"{model._meta.db_table}.{column.column} holds a fixture mark")

    def test_every_row_of_the_bank_names_a_stable_key_the_library_holds(self) -> None:
        duties = {e.key for e in baseline.load() if e.kind == baseline.OBLIGATION}
        named = set(TenantObligation.objects.values_list("obligation__stable_key", flat=True))
        self.assertEqual(named, {entry.obligation for entry in demo_seed.DEMO_REGISTER.entries})
        self.assertLessEqual(named, duties)
        self.assertLessEqual(set(ChangeObligation.objects.values_list("obligation__stable_key", flat=True)), duties)
        facts = {fact.stable_key: fact for fact in demo_seed.facts()}
        cases = ChangeCase.objects.select_related("change")
        self.assertTrue(cases.exists())
        for case in cases:
            fact = facts[case.change.stable_key]
            self.assertEqual((case.change.key_date, case.change.source_url, case.change.published_on), (fact.day, fact.instrument.source_url, None))
            self.assertEqual(case.change.authority.key, fact.instrument.payload["authority"])  # type: ignore[union-attr]
            linked = set(ChangeObligation.objects.filter(change=case.change).values_list("obligation__stable_key", flat=True))
            self.assertTrue(linked and linked <= set(fact.duties), case.change.stable_key)
            applies = ChangeEvent.objects.get(change=case.change, label="Applies")
            self.assertEqual(applies.event_date, fact.day)

    def test_the_banks_cases_reach_every_category_with_what_their_screens_show(self) -> None:
        self.assertEqual(set(ChangeCase.objects.values_list("status", flat=True)), {status.value for status in CaseStatusCategory})
        self.assertEqual(set(ChangeCase.objects.values_list("footprint_match", flat=True)), {True, False})
        self.assertTrue(Action.objects.filter(done_at__isnull=True).exists() and Action.objects.filter(done_at__isnull=False).exists())
        self.assertEqual(set(Evidence.objects.values_list("scan_state", flat=True)), {"clean", "pending"})
        self.assertTrue(Comment.objects.filter(subject_type="change_case").exists())
        self.assertTrue(Participant.objects.filter(case__isnull=False, team__isnull=False).exists())
        self.assertTrue(Briefing.objects.exists(), "last week's briefing was sent")
        for change in RegulatoryChange.objects.filter(cases__isnull=False):
            self.assertLessEqual(change.first_seen_at, timezone.now(), "a change is first seen in the past")

    def test_the_register_carries_history_readings_gaps_entities_and_controls(self) -> None:
        self.assertEqual(set(TenantObligation.objects.values_list("applicability", flat=True)), {"applies", "does_not_apply"})
        self.assertGreaterEqual(ComplianceAssessment.objects.filter(tenant_obligation__obligation__stable_key=demo_seed.ALGO_KILL).count(), 2)
        self.assertTrue(Interpretation.objects.filter(superseded_at__isnull=False).exists())
        self.assertTrue(Gap.objects.exists() and TenantObligationScope.objects.exists())
        self.assertTrue(InternalLink.objects.filter(internal_item__kind__key="control").exists())
        self.assertEqual(set(OrgUnit.objects.filter(kind="legal_entity").values_list("name", flat=True)), {"Example Bank AB", "Example Liv Försäkring AB"})
        self.assertTrue(InternalItem.objects.exists())

    def test_only_the_reader_signs_in_and_reads_without_admin(self) -> None:
        self.assertEqual(list(WebAuthnCredential.objects.values_list("user__email", flat=True)), [demo_seed.DEMO_READER])
        reader = Membership.objects.get(user__email=demo_seed.DEMO_READER)
        self.assertEqual(list(MembershipRole.objects.filter(membership=reader).values_list("role__key", flat=True)), ["reader"])

    def test_a_second_run_files_approves_and_writes_nothing_new(self) -> None:
        watched: tuple[type[models.Model], ...] = (Instrument, Obligation, ObligationVersion, Proposal, RegulatoryChange, ChangeCase, Action, Evidence, Comment, Participant)
        watched += (TenantObligation, Gap, ComplianceAssessment, Interpretation, InternalItem, InternalLink, OrgUnit, User, Membership, Briefing)

        def counts() -> dict[str, int]:
            return {model.__name__: model._default_manager.count() for model in watched}

        before, audited = counts(), AuditEvent.objects.filter(action="tenant.seeded").count()
        demo_seed.seed_public_demo()
        tenancy.activate(self.tenant.id)
        self.assertEqual(counts(), before)
        self.assertEqual(AuditEvent.objects.filter(action="tenant.seeded").count(), audited)

    def test_the_seed_refuses_a_deployed_environment(self) -> None:
        from apps.shared.e2e_seed import SeedRefused

        with override_settings(IS_DEPLOYED_ENVIRONMENT=True), self.assertRaises(SeedRefused):
            demo_seed.seed_public_demo()

"""The case tables (CAS-01 to CAS-08, WAT-04, WAT-05; schema v0.3 `change_case`;
INPUT_DELTAS §8 and §18).

Tenant tables and nothing shared: a bank's case for a library change, that bank's own
decision about a suggested obligation link, and chunk 9's workflow — the assessment, actions
and the transition ledger. These tests pin the shape the case workflow builds on — one case
per bank per change, an urgency that is a vocabulary row and not an enum, a confirmation
that names a person, a link decision that leaves the library alone — and prove at the
database, as cw_app, every CHECK, every composite key and the append-only ledger, because
each of those is a promise the application code must not be the only thing keeping.

The library half of each assertion matters as much as the tenant half: `c5-cases-creation`
and `c5-cases-so-what-and-links` must never reach `change_obligation`, so the proof that
they cannot is here, beside the models, rather than in the task that writes them.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from typing import Any

from django.db import DEFAULT_DB_ALIAS, DatabaseError, IntegrityError, connections, transaction
from django.db.models import QuerySet
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.cases.models import (
    OWNED_CATEGORIES,
    Action,
    CaseLinkDecision,
    CaseObligationLink,
    CaseTransition,
    ChangeCase,
    ImpactAssessment,
    RemovedNotDeleted,
)
from apps.library import testing as build
from apps.library.models import Obligation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals.models import OriginType
from apps.shared import factories, tenancy
from apps.shared.audit import AppendOnlyRefused
from apps.shared.models import Tenant
from apps.shared.tenancy import TenantModel
from apps.shared.vocabulary import TenantListVocabulary
from apps.taxonomy.models import (
    CaseStatusCategory,
    CaseSubStatus,
    ChangeType,
    ClosureReason,
    DismissalReason,
    EffortSize,
    Urgency,
)
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.watch import testing as watch_build
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

    def test_status_holds_the_seven_categories_and_a_sub_status_is_a_banks_row(self) -> None:
        """The guards read the fixed category; a sub-status is a bank's own row inside one
        and never a second status column the guards could read (VOC-04, D-13)."""
        choices = {value for value, _ in ChangeCase._meta.get_field("status").choices or []}
        self.assertEqual(choices, {member.value for member in CaseStatusCategory})
        field = ChangeCase._meta.get_field("sub_status")
        self.assertEqual(field.related_model, CaseSubStatus)
        self.assertTrue(field.null)

    def test_the_workflow_columns_exist_and_reasons_are_rows(self) -> None:
        """CAS-02, CAS-06: triage, dismissal, the sign-off request, the sign-off and the
        close, with the dismissal and close reasons as the bank's own list rows (VOC-06)."""
        columns = {f.column for f in ChangeCase._meta.concrete_fields}
        workflow = {
            "triaged_by_id", "triaged_at", "dismissed_reason_id", "dismissed_by_id", "dismissed_at",
            "signoff_requested_by_id", "signoff_requested_at", "signed_off_by_id", "close_reason_id",
            "closed_note", "closed_at", "sub_status_id", "version",
        }  # fmt: skip
        self.assertEqual(workflow - columns, set())
        self.assertEqual(ChangeCase._meta.get_field("dismissed_reason").related_model, DismissalReason)
        self.assertEqual(ChangeCase._meta.get_field("close_reason").related_model, ClosureReason)
        self.assertEqual(ImpactAssessment._meta.get_field("effort").related_model, EffortSize)
        self.assertNotIn("closed_by_id", columns, "the closing move's transition row names who closed it")

    def test_every_versioned_record_starts_at_version_one(self) -> None:
        """CAS-08, AC-CAS2: the case, the assessment and each action carry the version their
        own writes compare under `If-Match` (INPUT_DELTAS §4)."""
        for model in (ChangeCase, ImpactAssessment, Action):
            with self.subTest(model=model.__name__):
                self.assertEqual(model._meta.get_field("version").default, 1)
        self.assertEqual(self.case(self.tenant_a).version, 1)

    def test_the_dropped_columns_stay_dropped(self) -> None:
        """Ruling 2: the contributor teams are the case's team participants, so the
        assessment has no contributor list to overwrite. Ruling 3: tickets are
        `c13-tickets-export`'s, so an action carries no ticket column yet."""
        self.assertNotIn("contributors", {f.column for f in ImpactAssessment._meta.concrete_fields})
        ticket = {"ticket_provider", "ticket_key", "ticket_url"}
        self.assertEqual({f.column for f in Action._meta.concrete_fields} & ticket, set())

    def test_the_new_tables_are_tenant_tables(self) -> None:
        for model in (ImpactAssessment, Action, CaseTransition):
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, TenantModel))
                self.assertIn("tenant_id", {field.column for field in model._meta.concrete_fields})


class NothingIsOverwrittenTests(CaseZoneTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.person = factories.member_user(self.tenant_a, roles=("compliance_officer",))
        self.row = self.case(self.tenant_a)

    def action(self) -> Action:
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            return Action.objects.create(
                tenant=self.tenant_a,
                case=self.row,
                title="Update the research payment policy",
                owner=self.person,
                due_date=timezone.localdate() + datetime.timedelta(days=30),
                created_by=self.person,
            )

    def test_an_action_is_removed_and_never_deleted(self) -> None:
        """Playbook 4.3: removal sets `removed_at` and `removed_by`, and neither the row nor
        a queryset can delete one, so the case file still shows what was planned."""
        action = self.action()
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            with self.assertRaises(RemovedNotDeleted):
                action.delete()
            with self.assertRaises(RemovedNotDeleted):
                Action.objects.filter(pk=action.pk).delete()
            action.removed_at = timezone.now()
            action.removed_by = self.person
            action.save()
            stored = Action.objects.get(pk=action.pk)
        self.assertEqual(stored.title, "Update the research payment policy")
        self.assertIsNotNone(stored.removed_at)
        self.assertEqual(str(stored), f"{self.row.pk}:Update the research payment policy")

    def test_a_transition_is_never_rewritten_from_python(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            move = CaseTransition.objects.create(
                tenant=self.tenant_a,
                case=self.row,
                from_status=CaseStatusCategory.NEW.value,
                to_status=CaseStatusCategory.ASSIGNED.value,
                by_user=self.person,
            )
            self.assertEqual(str(move), f"{self.row.pk}:new->assigned")
            move.note = "rewritten"
            with self.assertRaises(AppendOnlyRefused):
                move.save()
            with self.assertRaises(AppendOnlyRefused):
                move.delete()
            with self.assertRaises(AppendOnlyRefused):
                CaseTransition.objects.filter(pk=move.pk).update(note="rewritten")

    def test_open_actions_come_by_due_date(self) -> None:
        """`Meta.ordering`: the soonest due first, so `.first()` is the next thing due."""
        later = self.action()
        sooner = self.action()
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            Action.objects.filter(pk=sooner.pk).update(due_date=later.due_date - datetime.timedelta(days=7))
            first = Action.objects.filter(case=self.row).first()
        self.assertEqual(first.pk if first else None, sooner.pk)


class CaseDatabaseTestCase(TransactionTestCase):
    """Committed rows, proved on the `app` alias (cw_app, no ownership, forced row-level
    security) the way production writes them. Two banks, a member of each, a case of each
    on the same change. No test methods here: `tests_evidence_model.py` builds on it."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        self.tenant_a = factories.tenant(slug=f"case-db-a-{uuid.uuid4().hex[:8]}")
        self.tenant_b = factories.tenant(slug=f"case-db-b-{uuid.uuid4().hex[:8]}")
        self.owner = factories.member_user(self.tenant_a, roles=("compliance_officer",))
        self.approver = factories.member_user(self.tenant_a, roles=("approver",))
        self.outsider = factories.member_user(self.tenant_b, roles=("compliance_officer",))
        change = watch_build.change()
        self.case_a = cases_build.case(self.tenant_a, change)
        self.case_b = cases_build.case(self.tenant_b, change)

    @contextmanager
    def as_app(self, tenant: Tenant | None = None) -> Iterator[None]:
        """One cw_app transaction with the bank activated (tenant A unless named)."""
        with transaction.atomic(using="app"):
            tenancy.activate((tenant or self.tenant_a).id, using="app")
            yield

    def refused(self, write: Callable[[], object], why: str) -> None:
        with self.subTest(why), self.assertRaises(IntegrityError, msg=why), self.as_app():
            write()

    def cases(self) -> QuerySet[ChangeCase]:
        return ChangeCase.objects.using("app").filter(pk=self.case_a.pk)

    def reason(self, model: type[TenantListVocabulary], key: str) -> TenantListVocabulary:
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            return model._default_manager.get(key=key)


class CaseChecksAsTheAppRole(CaseDatabaseTestCase):
    def test_a_dismissal_names_a_reason(self) -> None:
        """CAS-02: dismissing without a reason is refused by the database itself."""
        out_of_scope = self.reason(DismissalReason, "out_of_scope")
        self.refused(lambda: self.cases().update(status=CaseStatusCategory.DISMISSED.value), "dismissed with no reason")
        with self.as_app():
            self.cases().update(
                status=CaseStatusCategory.DISMISSED.value,
                dismissed_reason=out_of_scope,
                dismissed_by=self.owner,
                dismissed_at=timezone.now(),
            )
        with self.as_app():
            self.assertEqual(self.cases().get().dismissed_reason_id, out_of_scope.pk)

    def test_every_category_between_triage_and_the_close_has_an_owner(self) -> None:
        for category in OWNED_CATEGORIES:
            self.refused(partial(self.cases().update, status=category.value), f"{category} without an owner")
        with self.as_app():
            self.cases().update(status=CaseStatusCategory.ASSIGNED.value, owner=self.owner, triaged_by=self.owner)
        with self.as_app():
            self.assertEqual(self.cases().get().status, CaseStatusCategory.ASSIGNED.value)

    def test_the_requester_cannot_sign_off_their_own_request(self) -> None:
        """Four eyes (CAS-06, AC-CAS1) as a check constraint, not a convention: the
        requester signing off is refused, and so is a sign-off nobody asked for."""
        requested = {"status": CaseStatusCategory.SIGNOFF.value, "owner": self.owner}
        self.refused(
            lambda: self.cases().update(**requested, signoff_requested_by=self.owner, signed_off_by=self.owner),
            "the requester signed off",
        )
        self.refused(lambda: self.cases().update(**requested, signed_off_by=self.approver), "signed off with no request")
        with self.as_app():
            self.cases().update(
                **requested, signoff_requested_by=self.owner, signoff_requested_at=timezone.now(), signed_off_by=self.approver
            )
        with self.as_app():
            self.assertEqual(self.cases().get().signed_off_by_id, self.approver.pk)

    def test_the_assessment_and_action_checks(self) -> None:
        """A saved assessment says why and names who saved it (CAS-03); an action has a
        title, and its completion and removal each name a person (CAS-04)."""
        due = timezone.localdate() + datetime.timedelta(days=30)

        def assessment(**fields: object) -> ImpactAssessment:  # compliance: allow-kwargs test helper forwarding model fields
            return ImpactAssessment.objects.using("app").create(tenant=self.tenant_a, case=self.case_a, **fields)

        def action(**fields: object) -> Action:  # compliance: allow-kwargs test helper forwarding model fields
            base: dict[str, object] = {"title": "Update the policy", "owner": self.owner, "due_date": due, "created_by": self.owner}
            return Action.objects.using("app").create(tenant=self.tenant_a, case=self.case_a, **{**base, **fields})

        self.refused(lambda: assessment(saved=True, saved_by=self.owner, saved_at=timezone.now()), "saved without a why")
        self.refused(lambda: assessment(saved=True, why="It changes our research policy."), "saved by nobody")
        self.refused(lambda: action(title=""), "an action with no title")
        self.refused(lambda: action(done_at=timezone.now()), "done by nobody")
        self.refused(lambda: action(removed_at=timezone.now()), "removed by nobody")
        with self.as_app():
            saved = assessment(saved=True, why="It changes our research policy.", saved_by=self.owner, saved_at=timezone.now())
            self.assertEqual(str(saved), f"{self.case_a.pk}:yes")
            action(done_at=timezone.now(), done_by=self.owner)


# Every composite key the case migrations add: (table, column, target). The database must
# refuse a row naming another bank's case or a person who is not this bank's member.
COMPOSITE_KEYS = [
    ("change_case", "owner_id", "membership"),
    ("change_case", "so_what_confirmed_by_id", "membership"),
    ("change_case", "triaged_by_id", "membership"),
    ("change_case", "dismissed_by_id", "membership"),
    ("change_case", "signoff_requested_by_id", "membership"),
    ("change_case", "signed_off_by_id", "membership"),
    # cases 0005 (c9-owner-team-and-reassign): the team beside the owner, a team of this bank.
    ("change_case", "owner_team_id", "team"),
    ("case_obligation_link", "case_id", "change_case"),
    ("case_obligation_link", "decided_by_id", "membership"),
    ("impact_assessment", "case_id", "change_case"),
    ("impact_assessment", "saved_by_id", "membership"),
    ("action", "case_id", "change_case"),
    ("action", "owner_id", "membership"),
    ("action", "done_by_id", "membership"),
    ("action", "created_by_id", "membership"),
    ("action", "removed_by_id", "membership"),
    ("case_transition", "case_id", "change_case"),
    ("case_transition", "by_user_id", "membership"),
    ("evidence", "case_id", "change_case"),
    ("evidence", "uploaded_by_id", "membership"),
]


class CompositeKeysAsTheAppRole(CaseDatabaseTestCase):
    """PostgreSQL checks a foreign key with row-level security bypassed, so a single-column
    key accepts another bank's case or a person from another bank. Only the composite
    `(tenant_id, …)` key refuses them (INPUT_DELTAS §1, D-18)."""

    def test_every_composite_key_exists(self) -> None:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                "SELECT t.relname, a.attname, r.relname FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid JOIN pg_class r ON r.oid = c.confrelid "
                "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[2] "
                "WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 2 AND t.relname = ANY(%s) "
                "AND c.conkey[1] = (SELECT attnum FROM pg_attribute WHERE attrelid = c.conrelid AND attname = 'tenant_id')",
                [sorted({table for table, _, _ in COMPOSITE_KEYS})],
            )
            found = sorted(cursor.fetchall())
        self.assertEqual(found, sorted(COMPOSITE_KEYS))

    def test_a_case_person_from_another_bank_is_refused(self) -> None:
        for column in ("owner", "so_what_confirmed_by", "triaged_by", "dismissed_by", "signoff_requested_by", "signed_off_by"):
            self.refused(partial(self.cases().update, **{column: self.outsider}), f"change_case.{column}")

    def test_a_child_naming_another_banks_case_or_person_is_refused(self) -> None:
        due = timezone.localdate() + datetime.timedelta(days=30)
        writes: dict[str, Callable[[], object]] = {
            "impact_assessment.case": lambda: ImpactAssessment.objects.using("app").create(tenant=self.tenant_a, case=self.case_b),
            "impact_assessment.saved_by": lambda: ImpactAssessment.objects.using("app").create(
                tenant=self.tenant_a, case=self.case_a, saved=True, why="Why.", saved_by=self.outsider, saved_at=timezone.now()
            ),
            "action.case": lambda: Action.objects.using("app").create(
                tenant=self.tenant_a, case=self.case_b, title="T", owner=self.owner, due_date=due, created_by=self.owner
            ),
            "transition.case": lambda: CaseTransition.objects.using("app").create(
                tenant=self.tenant_a, case=self.case_b, to_status=CaseStatusCategory.NEW.value
            ),
            "transition.by_user": lambda: CaseTransition.objects.using("app").create(
                tenant=self.tenant_a, case=self.case_a, to_status=CaseStatusCategory.NEW.value, by_user=self.outsider
            ),
        }
        for person in ("owner", "done_by", "created_by", "removed_by"):
            fields: dict[str, object] = {"owner": self.owner, "created_by": self.owner, person: self.outsider}
            if person == "done_by":
                fields["done_at"] = timezone.now()
            if person == "removed_by":
                fields["removed_at"] = timezone.now()
            writes[f"action.{person}"] = partial(
                Action.objects.using("app").create, tenant=self.tenant_a, case=self.case_a, title="T", due_date=due, **fields
            )
        for why, write in writes.items():
            self.refused(write, why)

    def test_a_link_decision_on_another_banks_case_is_refused(self) -> None:
        obligation = build.obligation(
            build.instrument(key=f"fffs-{uuid.uuid4().hex[:6]}", short_name="FFFS 2017:2", regime="regime:securities"),
            key=f"fffs-{uuid.uuid4().hex[:6]}-1",
        )
        self.refused(
            lambda: CaseObligationLink.objects.using("app").create(
                tenant=self.tenant_a, case=self.case_b, obligation=obligation, decision=CaseLinkDecision.ACCEPTED.value
            ),
            "case_obligation_link.case",
        )
        self.refused(
            lambda: CaseObligationLink.objects.using("app").create(
                tenant=self.tenant_a,
                case=self.case_a,
                obligation=obligation,
                decision=CaseLinkDecision.ACCEPTED.value,
                decided_by=self.outsider,
            ),
            "case_obligation_link.decided_by",
        )


class TheWorkflowTablesAsTheAppRole(CaseDatabaseTestCase):
    def test_another_bank_reads_none_of_them(self) -> None:
        with self.as_app():
            ImpactAssessment.objects.using("app").create(tenant=self.tenant_a, case=self.case_a)
            Action.objects.using("app").create(
                tenant=self.tenant_a,
                case=self.case_a,
                title="Update the policy",
                owner=self.owner,
                due_date=timezone.localdate(),
                created_by=self.owner,
            )
            CaseTransition.objects.using("app").create(
                tenant=self.tenant_a, case=self.case_a, to_status=CaseStatusCategory.NEW.value
            )
        for model in (ImpactAssessment, Action, CaseTransition):
            with self.subTest(model=model.__name__):
                with self.as_app():
                    self.assertEqual(model.objects.using("app").count(), 1)
                with self.as_app(self.tenant_b):
                    self.assertEqual(model.objects.using("app").count(), 0)

    def test_the_transition_ledger_is_append_only_even_with_the_hatch(self) -> None:
        """CAS-08: INSERT works for cw_app; UPDATE and DELETE are refused by the trigger,
        and `SET LOCAL cw.maintenance = 'on'` does not help the application role."""
        with self.as_app():
            move = CaseTransition.objects.using("app").create(
                tenant=self.tenant_a,
                case=self.case_a,
                from_status=CaseStatusCategory.NEW.value,
                to_status=CaseStatusCategory.ASSIGNED.value,
                by_user=self.owner,
            )
        for hatch in ("", "SET LOCAL cw.maintenance = 'on'"):
            for statement in (
                "UPDATE case_transition SET note = 'rewritten' WHERE id = %s",
                "DELETE FROM case_transition WHERE id = %s",
            ):
                with self.subTest(hatch=hatch, statement=statement), self.assertRaises(DatabaseError):
                    with self.as_app(), connections["app"].cursor() as cursor:
                        if hatch:
                            cursor.execute(hatch)
                        cursor.execute(statement, [move.pk])
        with self.as_app():
            self.assertEqual(CaseTransition.objects.using("app").get(pk=move.pk).note, "")


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

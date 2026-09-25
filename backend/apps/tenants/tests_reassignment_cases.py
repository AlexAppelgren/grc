"""Removing a member who owns cases, actions and dated duties (TEN-05, TEN-03, CAS-02, CAS-04,
REG-07; `c9-owner-team-and-reassign`).

The case half of `tests_reassignment.py`: the preview counts the member's open cases, their
live actions and their open duty occurrences, and nothing changes before the confirm; the
confirm moves each to its new owner with one audit event per item, in the one transaction
that deactivates the member. A case or an action passes to a person who may work it, never
to a team; a duty passes to either. What a team owns is never touched: a case's team stays
beside its new owner, and a case or a duty the team owns does not reach the preview when one
of its members leaves (TEN-S3). A closed case, a done or removed action and a done duty are
history and stay as they were.

Proven to fail 2026-09-25 before `reassignment.py` read cases: the preview listed none.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.cases import testing as case_build
from apps.cases.models import Action, ChangeCase
from apps.collab import testing as collab_testing
from apps.collab.models import Participant
from apps.identity.models import Membership, User
from apps.library import testing as library_testing
from apps.register.logic import ensure_register_entry
from apps.register.models import DutyOccurrence, DutyStatus
from apps.shared import factories, tenancy
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import Team

V1 = "/api/v1"


def case_work(tenant: Tenant, erik: User, officer: User) -> SimpleNamespace:
    """Erik's case work in `tenant`: two open cases (one with the team "Cards" beside him), a
    closed one, two live actions, a done and a removed one, an open and a done duty
    occurrence, and a participation in a case. "Cards" also owns a case whose person is the
    officer, and a duty of its own; Erik is in "Cards"."""
    cards = factories.team(tenant, key="cards", label="Cards", members=(erik, officer))
    factories.team(tenant, key="legal", label="Legal")
    cases = [case_build.case_on_a_new_change(tenant) for _ in range(5)]
    open_cases, closed, team_case, watched = cases[0:2], cases[2], cases[3], cases[4]
    law = collab_testing.obligation()
    duty = library_testing.recurring_duty(law)
    today = timezone.localdate()
    with transaction.atomic():
        tenancy.activate(tenant.id)
        ChangeCase.objects.filter(pk__in=[c.pk for c in open_cases]).update(status=CaseStatusCategory.ASSESSING.value, owner=erik)
        ChangeCase.objects.filter(pk=open_cases[1].pk).update(owner_team=cards)
        ChangeCase.objects.filter(pk=closed.pk).update(status=CaseStatusCategory.CLOSED.value, owner=erik)
        ChangeCase.objects.filter(pk=team_case.pk).update(status=CaseStatusCategory.ASSIGNED.value, owner=officer, owner_team=cards)
        fields = {"tenant": tenant, "case": open_cases[0], "owner": erik, "due_date": today, "created_by": officer}
        actions = [Action.objects.create(title=f"Step {n}", **fields) for n in (1, 2)]
        done = Action.objects.create(title="Done step", done_at=timezone.now(), done_by=erik, **fields)
        removed = Action.objects.create(title="Dropped step", removed_at=timezone.now(), removed_by=officer, **fields)
        entry = ensure_register_entry(tenant_id=tenant.id, obligation_id=law.id, actor=factories.user_actor(user_id=officer.id))
        dated = {"tenant": tenant, "recurring_duty": duty, "tenant_obligation": entry}
        duty_open = DutyOccurrence.objects.create(due_date=today, owner=erik, **dated)
        duty_done = DutyOccurrence.objects.create(
            due_date=today - datetime.timedelta(days=90), owner=erik, status=DutyStatus.DONE.value, completed_at=timezone.now(), completed_by=erik, **dated
        )
        duty_team = DutyOccurrence.objects.create(due_date=today + datetime.timedelta(days=90), owner_team=cards, **dated)
        watching = Participant.objects.create(tenant=tenant, case=watched, user=erik, added_by=officer)
    return SimpleNamespace(
        cards=cards,
        open_cases=open_cases,
        closed=closed,
        team_case=team_case,
        actions=actions,
        done=done,
        removed=removed,
        duty_open=duty_open,
        duty_done=duty_done,
        duty_team=duty_team,
        watching=watching,
    )


CASE_KINDS = {"case": 2, "action": 2, "duty_occurrence": 1, "participation": 1, "team_membership": 1}


class CaseWorkRemoval(TestCase):
    tenant: Tenant
    admin: User
    officer: User
    erik: User
    anna: User
    reader: User
    work: SimpleNamespace

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant(slug="case-removal")
        cls.admin = factories.member_user(cls.tenant, roles=("admin",))
        cls.officer = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.erik = factories.member(cls.tenant, roles=("compliance_officer",), user_row=factories.user(name="Erik Dahl")).user
        cls.anna = factories.member(cls.tenant, roles=("compliance_officer",), user_row=factories.user(name="Anna Berg")).user
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.work = case_work(cls.tenant, cls.erik, cls.officer)

    def headers(self) -> dict[str, Any]:
        return sign_in(self.admin, tenant=self.tenant, step_up=True)

    def remove(self, owners: list[dict[str, Any]]) -> Any:
        return self.client.post(
            f"{V1}/tenant/members/{self.erik.id}/remove",
            data={"owners": owners},
            content_type="application/json",
            **self.headers(),
        )

    def owners(self, **changes: dict[str, str]) -> list[dict[str, Any]]:
        chosen = {"case": {"userId": str(self.anna.id)}, "action": {"userId": str(self.anna.id)}, "duty_occurrence": {"teamKey": "legal"}, **changes}
        return [{"kind": kind, **owner} for kind, owner in chosen.items()]

    def snapshot(self) -> dict[str, Any]:
        tenancy.activate(self.tenant.id)
        return {
            "cases": list(ChangeCase.objects.order_by("id").values_list("id", "owner_id", "owner_team_id", "version")),
            "actions": list(Action.objects.order_by("id").values_list("id", "owner_id", "version")),
            "duties": list(DutyOccurrence.objects.order_by("id").values_list("id", "owner_id", "owner_team_id", "version")),
            "participants": list(Participant.objects.order_by("id").values_list("id", "removed_at")),
            "membership": Membership.objects.get(tenant=self.tenant, user=self.erik).deactivated_at,
            "audit": AuditEvent.objects.exclude(action="session.created").count(),
        }

    def test_the_preview_counts_open_cases_live_actions_and_open_duties_and_writes_nothing(self) -> None:
        before = self.snapshot()
        response = self.client.get(f"{V1}/tenant/members/{self.erik.id}/open-work", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({row["kind"]: row["count"] for row in response.json()["items"]}, CASE_KINDS)
        self.assertEqual(self.snapshot(), before)

    def test_a_plain_removal_is_refused_with_the_case_kinds_counted(self) -> None:
        before = self.snapshot()
        response = self.client.delete(f"{V1}/tenant/members/{self.erik.id}", **self.headers())
        self.assertEqual((response.status_code, response.json()["code"]), (422, "reassignment_required"))
        self.assertEqual({row["field"]: row["count"] for row in response.json()["errors"]}, CASE_KINDS)
        self.assertEqual(self.snapshot(), before)

    def test_the_confirm_moves_each_item_with_one_audit_event_and_leaves_the_teams_alone(self) -> None:
        response = self.remove(self.owners())
        self.assertEqual(response.status_code, 204, response.content)
        tenancy.activate(self.tenant.id)
        work = self.work
        cases = {row.pk: row for row in ChangeCase.objects.all()}
        for case in work.open_cases:
            self.assertEqual((cases[case.pk].owner_id, cases[case.pk].version), (self.anna.id, case.version + 1))
        self.assertEqual(cases[work.open_cases[1].pk].owner_team_id, work.cards.id, "the team beside the owner stays")
        self.assertEqual(cases[work.closed.pk].owner_id, self.erik.id, "a closed case is history")
        team_case = cases[work.team_case.pk]
        self.assertEqual((team_case.owner_id, team_case.owner_team_id, team_case.version), (self.officer.id, work.cards.id, work.team_case.version))
        actions = {row.pk: row for row in Action.objects.all()}
        self.assertEqual([actions[a.pk].owner_id for a in work.actions], [self.anna.id, self.anna.id])
        self.assertEqual((actions[work.done.pk].owner_id, actions[work.removed.pk].owner_id), (self.erik.id, self.erik.id))
        duties = {row.pk: row for row in DutyOccurrence.objects.all()}
        legal = Team.objects.get(key="legal").id
        self.assertEqual((duties[work.duty_open.pk].owner_id, duties[work.duty_open.pk].owner_team_id), (None, legal))
        self.assertEqual(duties[work.duty_done.pk].owner_id, self.erik.id)
        self.assertEqual((duties[work.duty_team.pk].owner_team_id, duties[work.duty_team.pk].version), (work.cards.id, 1))
        self.assertIsNotNone(Participant.objects.get(pk=work.watching.pk).removed_at, "a case participation ends")
        for action, subject_type, count in (
            ("case.reassigned", "change_case", 2),
            ("action.reassigned", "action", 2),
            ("duty_occurrence.reassigned", "duty_occurrence", 1),
            ("member.deactivated", None, 1),
        ):
            rows = AuditEvent.objects.filter(action=action, tenant_id=self.tenant.id)
            self.assertEqual(rows.count(), count, action)
            if subject_type:
                self.assertEqual({row.subject_type for row in rows}, {subject_type})
                self.assertTrue(all(row.step_up_assertion_id for row in rows), action)
        moved = AuditEvent.objects.get(action="case.reassigned", subject_id=work.open_cases[1].id)
        self.assertEqual(moved.before, {"ownerId": str(self.erik.id), "ownerTeamId": str(work.cards.id)})
        self.assertEqual(moved.after, {"ownerId": str(self.anna.id), "ownerTeamId": str(work.cards.id)})
        self.assertFalse(AuditEvent.objects.filter(subject_id__in=[work.team_case.id, work.duty_team.id, work.closed.id]).exclude(action="session.created").exists())

    def test_a_case_or_an_action_never_passes_to_a_team(self) -> None:
        before = self.snapshot()
        for kind in ("case", "action"):
            with self.subTest(kind=kind):
                response = self.remove(self.owners(**{kind: {"teamKey": "cards"}}))
                self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"), response.content)
        self.assertEqual(self.snapshot(), before)

    def test_a_case_passes_only_to_a_member_who_works_cases(self) -> None:
        before = self.snapshot()
        response = self.remove(self.owners(case={"userId": str(self.reader.id)}))
        self.assertEqual((response.status_code, response.json()["code"]), (422, "unknown_member"), response.content)
        self.assertEqual(self.snapshot(), before)

    def test_a_kind_left_unnamed_is_refused_and_nothing_moves(self) -> None:
        before = self.snapshot()
        response = self.remove(self.owners()[:2])
        self.assertEqual((response.status_code, response.json()["code"]), (422, "reassignment_required"))
        self.assertEqual([row["field"] for row in response.json()["errors"]], ["duty_occurrence"])
        self.assertEqual(self.snapshot(), before)

    def test_a_failure_after_the_moves_leaves_every_case_as_it_was(self) -> None:
        before = self.snapshot()
        with mock.patch("apps.identity.members_logic.deactivate_member", side_effect=ValidationError("boom", code="validation_error")):
            response = self.remove(self.owners())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.snapshot(), before)


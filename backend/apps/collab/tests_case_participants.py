"""Participants on a bank's case (`collab/participants.py`; COL-04, CAS-03, D-18 to D-20).
The scenarios are COL-S9 and CAS-S17, whose bodies live at the end of this module and run
from the two apps' tests_scenarios.py; these pin what they rest on.

The case half reuses the register entry's logic and adds no rule of its own beyond the
case's: adding needs `cases.contribute` and a member who can read cases, removing anyone
else's row needs `cases.contribute` while a person may always leave their own, and a closed
or dismissed case takes no new participant (`invalid_transition`, from `state.is_open`).
Every D-18 and D-19 refusal code has a test here. A change carries no bank of its own, so
"a change private to tenant A" is proved with a change tenant B has no case for, which is
exactly what makes it A's.

Proven to fail 2026-09-25: with the `is_open` check removed the closed case took a
participant, and with `can_edit` forced true a reader removed someone else's row."""

from __future__ import annotations

import re
import uuid
from types import SimpleNamespace
from typing import Any

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cases import case_file
from apps.cases import testing as case_build
from apps.cases.models import ChangeCase, ImpactAssessment
from apps.cases.tests_assessment import AssessmentClient, bank_with_a_case, body
from apps.collab import testing as collab_testing
from apps.collab.models import Participant
from apps.identity import session_logic
from apps.identity.models import Membership, TenantRole
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.authentication import PrincipalKind
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import AuditEvent, Tenant
from apps.shared.routes import iter_operations
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.watch import testing as watch_build
from config.api import api

C = CaseStatusCategory


def url(change_id: Any) -> str:
    return f"/api/v1/changes/{change_id}/participants"


def _post(case: TestCase, change_id: Any, payload: dict[str, str], headers: dict[str, Any]) -> Any:
    return case.client.post(url(change_id), payload, content_type="application/json", **headers)


def _token(headers: dict[str, Any]) -> str:
    return str(headers["HTTP_AUTHORIZATION"]).removeprefix("Bearer ")


def _bank(slug: str, category: CaseStatusCategory = C.ASSIGNED) -> SimpleNamespace:
    """A bank with an owner, a contributor, a reader, a team and one case in `category`."""
    watch_build.seed_watch_reference()
    tenant = factories.tenant(slug=slug)
    owner = factories.member_user(tenant, roles=("owner",))
    contributor = factories.member_user(tenant, roles=("contributor",))
    reader = factories.member_user(tenant, roles=("reader",))
    team = collab_testing.team(tenant, "legal", "Legal")
    row = case_build.case(tenant, watch_build.change(), owner=owner)
    case_build.in_category(row, category)
    return SimpleNamespace(tenant=tenant, owner=owner, contributor=contributor, reader=reader, team=team, case=row)


class CaseParticipantRouteGates(TestCase):
    def test_reading_needs_cases_read_adding_cases_contribute_and_removal_is_the_logics(self) -> None:
        routes = {op.operation_id: op for op in iter_operations(api) if op.path.startswith("/changes/") and "/participants" in op.path}
        gates = {name: perms.gate_of(op.view_func) for name, op in routes.items()}
        self.assertEqual(
            {name: (gate.kind, gate.value) if gate else None for name, gate in gates.items()},
            {
                "listCaseParticipants": ("permission", perms.CASES_READ),
                "addCaseParticipant": ("permission", perms.CASES_CONTRIBUTE),
                "removeCaseParticipant": None,
            },
        )
        self.assertIn(("DELETE", routes["removeCaseParticipant"].path), perms.UNGATED_BY_DESIGN)
        for name, op in routes.items():
            with self.subTest(operation=name):
                self.assertFalse(perms.step_up_of(op.view_func), "participation approves nothing")


class CaseParticipantLogic(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = _bank(f"case-participants-{uuid.uuid4().hex[:6]}")
        self.as_owner = sign_in(self.bank.owner, tenant=self.bank.tenant)
        self.change_id = self.bank.case.change_id

    def audit(self, action: str) -> list[AuditEvent]:
        self.activate(self.bank.tenant)
        return list(AuditEvent.objects.filter(action=action, subject_id=self.bank.case.id))

    def test_an_add_lands_on_the_case_audited_with_ids_only_and_lists_back(self) -> None:
        person = _post(self, self.change_id, {"userId": str(self.bank.reader.id)}, self.as_owner)
        team = _post(self, self.change_id, {"teamKey": "legal"}, self.as_owner)
        self.assertEqual((person.status_code, team.status_code), (201, 201), (person.content, team.content))
        self.assertEqual(team.json()["team"], {"key": "legal", "kind": None, "label": "Legal"})
        self.activate(self.bank.tenant)
        rows = Participant.objects.filter(case=self.bank.case)
        self.assertEqual({row.id for row in rows}, {uuid.UUID(person.json()["id"]), uuid.UUID(team.json()["id"])})
        self.assertFalse(rows.filter(tenant_obligation__isnull=False).exists())
        added = self.audit("participant.added")
        self.assertEqual(len(added), 2)
        for event in added:
            self.assertEqual(event.subject_type, "change_case")
            self.assertEqual(set(event.after or {}), {"participantId", "userId", "teamId"}, "ids only, never a name")
        listed = self.client.get(url(self.change_id), **sign_in(self.bank.reader, tenant=self.bank.tenant))
        self.assertEqual([item["id"] for item in listed.json()["items"]], [person.json()["id"], team.json()["id"]])
        self.assertEqual(listed.json()["total"], 2)

    def test_every_refusal_of_an_add_has_its_code_and_writes_nothing(self) -> None:
        tenant = self.bank.tenant
        stranger = factories.member_user(factories.tenant(slug=f"elsewhere-{uuid.uuid4().hex[:6]}"))
        gone = factories.member(tenant)
        self.activate(tenant)
        Membership.objects.filter(pk=gone.pk).update(deactivated_at=timezone.now())
        blind_role = TenantRole.objects.create(tenant=tenant, key="register-only", permissions=[perms.REGISTER_READ])
        blind = factories.member_user(tenant, roles=(blind_role.key,))
        for payload, status, code in (
            ({"userId": str(stranger.id)}, 422, "unknown_member"),
            ({"userId": str(gone.user_id)}, 422, "unknown_member"),
            ({"userId": str(uuid.uuid4())}, 422, "unknown_member"),
            ({"userId": str(blind.id)}, 422, "participant_cannot_read"),
            ({"teamKey": "no-such-team"}, 422, "unknown_key"),
            ({"teamKey": "legal", "userId": str(self.bank.reader.id)}, 422, "validation_error"),
            ({}, 422, "validation_error"),
        ):
            with self.subTest(payload=payload):
                answer = _post(self, self.change_id, payload, self.as_owner)
                self.assertEqual((answer.status_code, answer.json()["code"]), (status, code))
        self.activate(tenant)
        self.assertFalse(Participant.objects.filter(case=self.bank.case).exists())
        self.assertEqual(self.audit("participant.added"), [])

    def test_a_repeat_is_already_participant_and_the_cap_is_too_many_participants(self) -> None:
        self.assertEqual(_post(self, self.change_id, {"teamKey": "legal"}, self.as_owner).status_code, 201)
        again = _post(self, self.change_id, {"teamKey": "legal"}, self.as_owner)
        self.assertEqual((again.status_code, again.json()["code"]), (409, "already_participant"))
        with override_settings(MAX_PARTICIPANTS_PER_RECORD=2):
            self.assertEqual(_post(self, self.change_id, {"userId": str(self.bank.reader.id)}, self.as_owner).status_code, 201)
            over = _post(self, self.change_id, {"userId": str(self.bank.contributor.id)}, self.as_owner)
            self.assertEqual((over.status_code, over.json()["code"]), (422, "too_many_participants"))

    def test_a_closed_or_dismissed_case_takes_no_new_participant(self) -> None:
        for category in (C.CLOSED, C.DISMISSED):
            with self.subTest(category=category.value):
                bank = _bank(f"shut-{category.value}-{uuid.uuid4().hex[:6]}", category)
                answer = _post(self, bank.case.change_id, {"teamKey": "legal"}, sign_in(bank.owner, tenant=bank.tenant))
                self.assertEqual((answer.status_code, answer.json()["code"]), (409, "invalid_transition"))
                self.activate(bank.tenant)
                self.assertFalse(Participant.objects.filter(case=bank.case).exists())

    def test_removing_someone_else_needs_cases_contribute_and_leaving_needs_nothing(self) -> None:
        reader_row = _post(self, self.change_id, {"userId": str(self.bank.reader.id)}, self.as_owner).json()["id"]
        team_row = _post(self, self.change_id, {"teamKey": "legal"}, self.as_owner).json()["id"]
        as_reader = sign_in(self.bank.reader, tenant=self.bank.tenant)

        refused = self.client.delete(f"{url(self.change_id)}/{team_row}", **as_reader)
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["requiredPermission"], perms.CASES_CONTRIBUTE)
        self.activate(self.bank.tenant)
        self.assertIsNone(Participant.objects.get(id=team_row).removed_at)

        left = self.client.delete(f"{url(self.change_id)}/{reader_row}", **as_reader)
        self.assertEqual(left.status_code, 204, left.content)
        removed = self.client.delete(f"{url(self.change_id)}/{team_row}", **sign_in(self.bank.contributor, tenant=self.bank.tenant))
        self.assertEqual(removed.status_code, 204, removed.content)
        self.assertEqual([event.after for event in self.audit("participant.left")], [{"participantId": reader_row}])
        self.assertEqual([event.after for event in self.audit("participant.removed")], [{"participantId": team_row}])
        self.assertEqual(self.client.delete(f"{url(self.change_id)}/{team_row}", **self.as_owner).status_code, 404)
        self.assertEqual(self.client.get(url(self.change_id), **self.as_owner).json(), {"items": [], "total": 0})

    def test_a_participant_of_another_case_is_not_found_here(self) -> None:
        other = case_build.case(self.bank.tenant, watch_build.change())
        row = _post(self, other.change_id, {"teamKey": "legal"}, self.as_owner).json()["id"]
        self.assertEqual(self.client.delete(f"{url(self.change_id)}/{row}", **self.as_owner).status_code, 404)

    def test_a_change_the_bank_has_no_case_for_is_not_found_to_read_add_or_remove(self) -> None:
        caseless = watch_build.change()
        self.assertEqual(self.client.get(url(caseless.id), **self.as_owner).status_code, 404)
        self.assertEqual(_post(self, caseless.id, {"teamKey": "legal"}, self.as_owner).status_code, 404)
        self.assertEqual(self.client.delete(f"{url(caseless.id)}/{uuid.uuid4()}", **self.as_owner).status_code, 404)

    def test_taking_part_grants_nothing(self) -> None:
        """A contributor named on the case keeps exactly their session's permissions, and a
        move that needs `cases.work` still answers 403 naming it."""
        as_contributor = sign_in(self.bank.contributor, tenant=self.bank.tenant)
        before = session_logic.resolve_access_token(_token(as_contributor), want=PrincipalKind.USER)
        added = _post(self, self.change_id, {"userId": str(self.bank.contributor.id)}, self.as_owner)
        self.assertEqual(added.status_code, 201)
        after = session_logic.resolve_access_token(_token(as_contributor), want=PrincipalKind.USER)
        assert before is not None and after is not None
        self.assertEqual(after.permissions, before.permissions)
        self.activate(self.bank.tenant)
        version = ChangeCase.objects.get(pk=self.bank.case.pk).version
        refused = self.client.post(
            f"/api/v1/changes/{self.change_id}/close",
            {"reasonKey": "no_action"},
            content_type="application/json",
            HTTP_IF_MATCH=str(version),
            **as_contributor,
        )
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertEqual(refused.json()["requiredPermission"], perms.CASES_WORK)


class CaseParticipantsInTheCaseFile(ScenarioTestCase):
    def test_the_file_names_who_took_part_and_until_when_and_the_contributing_teams(self) -> None:
        bank = _bank(f"file-{uuid.uuid4().hex[:6]}")
        cards = collab_testing.team(bank.tenant, "cards", "Cards")
        as_owner = sign_in(bank.owner, tenant=bank.tenant)
        change_id = bank.case.change_id
        legal = _post(self, change_id, {"teamKey": "legal"}, as_owner).json()["id"]
        _post(self, change_id, {"teamKey": cards.key}, as_owner)
        _post(self, change_id, {"userId": str(bank.reader.id)}, as_owner)
        self.assertEqual(self.client.delete(f"{url(change_id)}/{legal}", **as_owner).status_code, 204)

        self.activate(bank.tenant)
        text = case_file.compose(tenant=bank.tenant, case_id=bank.case.id, order=["en"])
        self.assertIn("Contributing teams: Cards", text)
        section = text.split("\nParticipants\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("- Legal (team)", section)
        self.assertIn("- Cards (team)", section)
        self.assertIn(f"- {bank.reader.name}\n", section)
        self.assertRegex(
            section,
            r"- Legal \(team\)\n  Added by .+\.\n  Took part until \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC[+-]\d{2}:\d{2}, "
            + f"removed by {re.escape(bank.owner.name)}\\.",
        )
        self.assertEqual(section.count("Took part until"), 1, "only Legal was removed")


# ---------------------------------------------------------------------------------------
# COL-S9 and CAS-S17, run by the two apps' tests_scenarios.py (one method per scenario
# there). The bodies live here, beside what they rest on, so each scenario module stays a list.
# ---------------------------------------------------------------------------------------
def run_col_s9(case: ScenarioTestCase) -> None:
    bank = _bank("col-s9-a")
    anna = factories.member_user(bank.tenant, roles=("compliance_officer",))
    johan = factories.member_user(bank.tenant, roles=("reader",))
    erik = bank.contributor
    change_id = bank.case.change_id
    as_erik = sign_in(erik, tenant=bank.tenant)
    as_owner = sign_in(bank.owner, tenant=bank.tenant)
    case.activate(bank.tenant)
    case.assertNotIn(perms.REGISTER_EDIT, perms.SYSTEM_ROLES["contributor"])

    # Erik contributes to cases without editing the register: he adds Anna and removes Johan.
    johan_row = _post(case, change_id, {"userId": str(johan.id)}, as_owner).json()["id"]
    added = _post(case, change_id, {"userId": str(anna.id)}, as_erik)
    case.assertEqual(added.status_code, 201, added.content)
    removed = case.client.delete(f"{url(change_id)}/{johan_row}", **as_erik)
    case.assertEqual(removed.status_code, 204, removed.content)
    case.activate(bank.tenant)
    case.assertEqual(
        list(
            AuditEvent.objects.filter(subject_id=bank.case.id, after__participantId=johan_row)
            .order_by("created", "id")
            .values_list("action", flat=True)
        ),
        ["participant.added", "participant.removed"],
    )

    # A reader who takes part leaves on their own.
    reader_row = _post(case, change_id, {"userId": str(bank.reader.id)}, as_owner).json()["id"]
    left = case.client.delete(f"{url(change_id)}/{reader_row}", **sign_in(bank.reader, tenant=bank.tenant))
    case.assertEqual(left.status_code, 204, left.content)
    case.activate(bank.tenant)
    case.assertTrue(AuditEvent.objects.filter(action="participant.left", after__participantId=reader_row).exists())

    # A closed case takes no new participant.
    closed = _bank("col-s9-closed", C.CLOSED)
    refused = _post(case, closed.case.change_id, {"userId": str(closed.reader.id)}, sign_in(closed.owner, tenant=closed.tenant))
    case.assertEqual((refused.status_code, refused.json()["code"]), (409, "invalid_transition"))

    # Tenant B. A change only tenant A has a case for is not there for B: a change carries
    # no bank of its own, so "private to A" is a change B has no case for.
    tenant_b = factories.tenant(slug="col-s9-b")
    owner_b = factories.member_user(tenant_b, roles=("owner",))
    reader_b = factories.member_user(tenant_b, roles=("reader",))
    as_b = sign_in(owner_b, tenant=tenant_b)
    case.assertEqual(_post(case, change_id, {"userId": str(reader_b.id)}, as_b).status_code, 404)
    case.assertEqual(case.client.get(url(change_id), **as_b).status_code, 404)

    # A shared change, one case per bank: B's add lands on B's own case and A's list is unchanged.
    b_case = case_build.case(tenant_b, bank.case.change)
    a_before = case.client.get(url(change_id), **as_owner).json()["items"]
    case.activate(tenant_b)  # the audit check counts rows as the bank the request writes for
    b_added = _post(case, change_id, {"userId": str(reader_b.id)}, as_b)
    case.assertEqual(b_added.status_code, 201, b_added.content)
    case.activate(tenant_b)
    case.assertEqual(Participant.objects.get(id=b_added.json()["id"]).case_id, b_case.id)
    case.assertEqual(case.client.get(url(change_id), **as_owner).json()["items"], a_before)
    case.assertEqual([item["id"] for item in case.client.get(url(change_id), **as_b).json()["items"]], [b_added.json()["id"]])

    # B removing A's participant by its id is a 404, and A's row stays.
    a_row = a_before[0]["id"]
    gone = case.client.delete(f"{url(change_id)}/{a_row}", **as_b)
    case.assertEqual((gone.status_code, gone.json()["code"]), (404, "not_found"))
    case.activate(bank.tenant)
    case.assertIsNone(Participant.objects.get(id=a_row).removed_at)


def run_cas_s17(case: ScenarioTestCase) -> None:
    bank = bank_with_a_case(C.ASSIGNED)
    tenant: Tenant = bank.tenant
    for key, label in (("legal", "Legal"), ("retail-compliance", "Retail compliance"), ("cards", "Cards")):
        collab_testing.team(tenant, key, label)
    calls = AssessmentClient(case, bank)
    as_owner = sign_in(bank.owner, tenant=tenant)
    case.assertEqual(calls.start().status_code, 200)

    # The owner adds two contributor teams, one call each.
    legal = _post(case, bank.change_id, {"teamKey": "legal"}, as_owner)
    retail = _post(case, bank.change_id, {"teamKey": "retail-compliance"}, as_owner)
    case.assertEqual((legal.status_code, retail.status_code), (201, 201), (legal.content, retail.content))
    case.activate(tenant)
    teams = Participant.objects.filter(case_id=bank.case_id, team__isnull=False, removed_at__isnull=True)
    case.assertEqual(set(teams.values_list("team__key", flat=True)), {"legal", "retail-compliance"})
    case.assertEqual(AuditEvent.objects.filter(action="participant.added", subject_id=bank.case_id).count(), 2)
    case.assertNotIn("contributors", {field.name for field in ImpactAssessment._meta.get_fields()})

    # The owner loads the assessment; Erik adds "Cards" in between; the owner removes
    # "Legal" and saves from what they loaded. Nothing replaces the list, so "Cards" stays.
    loaded = calls.version()
    cards = _post(case, bank.change_id, {"teamKey": "cards"}, sign_in(bank.contributor, tenant=tenant))
    case.assertEqual(cards.status_code, 201, cards.content)
    case.assertEqual(case.client.delete(f"{url(bank.change_id)}/{legal.json()['id']}", **as_owner).status_code, 204)
    saved = calls.save(body(), if_match=loaded)
    case.assertEqual(saved.status_code, 200, saved.content)
    case.activate(tenant)
    case.assertEqual(set(teams.values_list("team__key", flat=True)), {"retail-compliance", "cards"})

    # The case file shows that "Legal" took part until it was removed.
    case.activate(tenant)
    text = case_file.compose(tenant=tenant, case_id=bank.case_id, order=["en"])
    section = text.split("\nParticipants\n", 1)[1]
    legal_lines = section.split("- Legal (team)\n", 1)[1].split("\n- ", 1)[0]
    case.assertIn("Took part until", legal_lines)
    case.assertIn("Contributing teams: Retail compliance, Cards", text)

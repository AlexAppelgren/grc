"""Triage, dismissal and restore over the real routes (CAS-02, CAS-08, VOC-06, D-34).

What is proved here beside the scenarios: every answer is the whole case with the moves the
state machine allows next; every write names the version it read and a stale one changes
nothing; another bank's case is a 404; the owner must be a member of the bank who works
cases; the owner is told once through `notify()` and D-34's one recipient check, so a
member whose roles cannot read cases is not told; and each move writes one transition row
and one audit row naming the person, with keys and never text in the audit values.

Proven to fail 2026-09-25 before `triage.py` was built: every test below answered 501
`not_built` or 409 `stale_write` where it expected its move.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.db import transaction

from apps.cases import testing as case_build
from apps.cases.models import CaseTransition, ChangeCase
from apps.collab.models import Notification
from apps.identity.models import TenantRole
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import CaseSubStatus, DismissalReason

V1 = "/api/v1"


def triage_bank(*, slug: str | None = None) -> SimpleNamespace:
    """A bank with a case in `new`, a compliance officer who triages, a colleague who can
    own the case, and a reader who can do neither."""
    tenant = factories.tenant(slug=slug)
    officer = factories.member(tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")).user
    owner = factories.member(tenant, roles=("compliance_officer",), user_row=factories.user(name="Johan Berg")).user
    reader = factories.member(tenant, roles=("reader",), user_row=factories.user(name="Oskar Lund")).user
    case = case_build.case_on_a_new_change(tenant)
    return SimpleNamespace(tenant=tenant, officer=officer, owner=owner, reader=reader, case=case, change_id=case.change_id)


class CaseMoves:
    """Posting a workflow move as a person and reading the case back, for any test case
    whose client is the scenario client."""

    client: Any
    assertEqual: Any

    def move(self, bank: SimpleNamespace, verb: str, body: dict[str, Any] | None, *, who: Any = None, version: Any = "current") -> Any:
        who = who if who is not None else bank.officer
        headers = sign_in(who, tenant=bank.tenant)
        if version == "current":
            version = self.case(bank).version
        if version is not None:
            headers["HTTP_IF_MATCH"] = str(version)
        return self.client.post(
            f"{V1}/changes/{bank.change_id}/{verb}", data=body or {}, content_type="application/json", **headers
        )

    def case(self, bank: SimpleNamespace) -> ChangeCase:
        with transaction.atomic():
            tenancy.activate(bank.tenant.id)
            return ChangeCase.objects.get(pk=bank.case.id)

    def ledger(self, bank: SimpleNamespace) -> list[tuple[str, str, Any]]:
        with transaction.atomic():
            tenancy.activate(bank.tenant.id)
            return [(row.from_status, row.to_status, row.by_user_id) for row in CaseTransition.objects.filter(case_id=bank.case.id)]

    def moves_audited(self, bank: SimpleNamespace) -> list[AuditEvent]:
        with transaction.atomic():
            tenancy.activate(bank.tenant.id)
            return list(AuditEvent.objects.filter(subject_id=bank.case.id, action="case.moved").order_by("created"))

    def told(self, bank: SimpleNamespace) -> list[Any]:
        with transaction.atomic():
            tenancy.activate(bank.tenant.id)
            return list(
                Notification.objects.filter(subject_id=bank.case.id, kind="assigned").values_list("user_id", flat=True)
            )

    def assertProblem(self, response: Any, status: int, code: str) -> dict[str, Any]:
        self.assertEqual(response.status_code, status, response.content)
        body: dict[str, Any] = response.json()
        self.assertEqual(body["code"], code)
        return body


class CaseRoutes(CaseMoves, ScenarioTestCase):
    pass


class Triage(CaseRoutes):
    def setUp(self) -> None:
        self.bank = triage_bank()

    def test_triage_answers_the_whole_case_assigned_with_what_it_may_do_next(self) -> None:
        response = self.move(self.bank, "triage", {"urgency": "within_3_months", "ownerId": str(self.bank.owner.id)})
        self.assertEqual(response.status_code, 200, response.content)
        case = response.json()
        self.assertEqual(case["id"], str(self.bank.case.id))
        self.assertEqual(case["changeId"], str(self.bank.change_id))
        self.assertEqual(case["status"], "assigned")
        self.assertEqual(case["urgency"]["key"], "within_3_months")
        self.assertIsNone(case["urgency"]["kind"], "a tone never leaves the API: the screen picks it from the key")
        self.assertTrue(case["urgencyConfirmed"])
        self.assertEqual(case["owner"], {"id": str(self.bank.owner.id), "name": "Johan Berg"})
        self.assertEqual(case["triagedBy"], {"id": str(self.bank.officer.id), "name": "Sara Lind"})
        self.assertIsNotNone(case["triagedAt"])
        self.assertEqual(sorted(case["allowedTransitions"]), ["assessing", "closed"])
        self.assertEqual(case["version"], self.bank.case.version + 1)
        self.assertIsNone(case["assessment"])
        self.assertEqual(case["openActionCount"], 0)
        self.assertFalse(case["canRequestSignoff"])
        self.assertEqual(self.ledger(self.bank), [("new", "assigned", self.bank.officer.id)])
        audited = self.moves_audited(self.bank)
        self.assertEqual(len(audited), 1)
        self.assertEqual(audited[0].actor_id, self.bank.officer.id)
        self.assertEqual(audited[0].after["ownerId"], str(self.bank.owner.id))
        self.assertEqual(audited[0].after["urgency"], "within_3_months")

    def test_triage_without_an_owner_is_422_naming_the_field_and_moves_nothing(self) -> None:
        response = self.move(self.bank, "triage", {"urgency": "act_now"})
        body = self.assertProblem(response, 422, "validation_error")
        self.assertTrue(any(error["field"].endswith("ownerId") for error in body["errors"]), body)
        self.assertEqual(self.case(self.bank).status, "new")
        self.assertEqual(self.ledger(self.bank), [])

    def test_an_owner_who_cannot_work_a_case_or_is_not_a_member_is_refused(self) -> None:
        stranger = factories.member_user(factories.tenant(), roles=("compliance_officer",))
        for person in (self.bank.reader, stranger):
            with self.subTest(owner=person.name):
                response = self.move(self.bank, "triage", {"urgency": "act_now", "ownerId": str(person.id)})
                self.assertProblem(response, 422, "owner_required")
        self.assertEqual(self.case(self.bank).status, "new")

    def test_an_unknown_urgency_is_422_unknown_key_listing_the_valid_keys(self) -> None:
        response = self.move(self.bank, "triage", {"urgency": "whenever", "ownerId": str(self.bank.owner.id)})
        body = self.assertProblem(response, 422, "unknown_key")
        self.assertIn("act_now", body["validKeys"])

    def test_a_sub_status_is_placed_inside_assigned_and_one_of_another_category_is_refused(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            CaseSubStatus.objects.create(tenant=self.bank.tenant, key="waiting_for_legal", kind="assessing")
            CaseSubStatus.objects.create(tenant=self.bank.tenant, key="with_owner", kind="assigned")
        refused = self.move(
            self.bank, "triage", {"urgency": "act_now", "ownerId": str(self.bank.owner.id), "subStatus": "waiting_for_legal"}
        )
        body = self.assertProblem(refused, 422, "unknown_key")
        self.assertIn("with_owner", body["validKeys"])
        self.assertNotIn("waiting_for_legal", body["validKeys"])
        placed = self.move(self.bank, "triage", {"urgency": "act_now", "ownerId": str(self.bank.owner.id), "subStatus": "with_owner"})
        self.assertEqual(placed.status_code, 200, placed.content)
        self.assertEqual(placed.json()["subStatus"]["key"], "with_owner")
        self.assertEqual(placed.json()["subStatus"]["kind"], "assigned")

    def test_the_owner_is_told_once_and_a_member_who_cannot_read_cases_is_not(self) -> None:
        response = self.move(self.bank, "triage", {"urgency": "act_now", "ownerId": str(self.bank.owner.id)})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.told(self.bank), [self.bank.owner.id])

        other = triage_bank()
        with transaction.atomic():
            tenancy.activate(other.tenant.id)
            # Works cases but cannot read them: D-34 tells only a member whose roles read the subject.
            TenantRole.objects.create(tenant=other.tenant, key="works-unseen", permissions=[perms.CASES_WORK])
        blind = factories.member(other.tenant, roles=("works-unseen",)).user
        response = self.move(other, "triage", {"urgency": "act_now", "ownerId": str(blind.id)})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.told(other), [], "chunk 9 writes no recipient rule of its own")

    def test_a_stale_or_missing_if_match_is_409_and_changes_nothing(self) -> None:
        body = {"urgency": "act_now", "ownerId": str(self.bank.owner.id)}
        current = self.case(self.bank).version
        for version in (None, current - 1, current + 1):
            with self.subTest(version=version):
                response = self.move(self.bank, "triage", body, version=version)
                problem = self.assertProblem(response, 409, "stale_write")
                self.assertEqual(problem["currentVersion"], current)
        self.assertEqual(self.case(self.bank).status, "new")
        self.assertEqual(self.told(self.bank), [])

    def test_a_case_that_is_not_new_cannot_be_triaged_again(self) -> None:
        self.assertEqual(self.move(self.bank, "triage", {"urgency": "act_now", "ownerId": str(self.bank.owner.id)}).status_code, 200)
        again = self.move(self.bank, "triage", {"urgency": "monitor", "ownerId": str(self.bank.officer.id)})
        self.assertProblem(again, 409, "invalid_transition")
        self.assertEqual(self.told(self.bank), [self.bank.owner.id], "a refused move tells nobody")


class Dismissal(CaseRoutes):
    def setUp(self) -> None:
        self.bank = triage_bank()

    def test_a_dismissal_stores_the_key_and_answers_the_label(self) -> None:
        response = self.move(self.bank, "dismiss", {"reasonKey": "duplicate"})
        self.assertEqual(response.status_code, 200, response.content)
        case = response.json()
        self.assertEqual(case["status"], "dismissed")
        self.assertEqual(case["dismissedReason"], {"key": "duplicate", "kind": None, "label": "Duplicate"})
        self.assertEqual(case["dismissedBy"]["id"], str(self.bank.officer.id))
        self.assertIsNotNone(case["dismissedAt"])
        self.assertEqual(case["allowedTransitions"], ["new"])
        self.assertEqual(getattr(self.case(self.bank).dismissed_reason, "key", None), "duplicate")
        self.assertEqual(self.moves_audited(self.bank)[0].after["reasonKey"], "duplicate")

    def test_an_unknown_or_missing_reason_is_422(self) -> None:
        body = self.assertProblem(self.move(self.bank, "dismiss", {"reasonKey": "boring"}), 422, "unknown_key")
        self.assertEqual(body["validKeys"], ["out_of_scope", "duplicate", "already_covered"])
        self.assertProblem(self.move(self.bank, "dismiss", {}), 422, "validation_error")
        self.assertEqual(self.case(self.bank).status, "new")

    def test_another_banks_reason_is_not_a_key_here(self) -> None:
        other = triage_bank()
        with transaction.atomic():
            tenancy.activate(other.tenant.id)
            DismissalReason.objects.create(tenant=other.tenant, key="their_own_reason")
        self.assertProblem(self.move(self.bank, "dismiss", {"reasonKey": "their_own_reason"}), 422, "unknown_key")

    def test_a_stale_dismissal_is_409(self) -> None:
        self.assertProblem(self.move(self.bank, "dismiss", {"reasonKey": "duplicate"}, version=None), 409, "stale_write")


class Restore(CaseRoutes):
    def setUp(self) -> None:
        self.bank = triage_bank()

    def test_restore_brings_a_dismissed_case_back_and_clears_the_dismissal(self) -> None:
        self.assertEqual(self.move(self.bank, "dismiss", {"reasonKey": "out_of_scope"}).status_code, 200)
        response = self.move(self.bank, "restore", None, who=self.bank.owner)
        self.assertEqual(response.status_code, 200, response.content)
        case = response.json()
        self.assertEqual(case["status"], "new")
        self.assertIsNone(case["dismissedReason"])
        self.assertIsNone(case["dismissedBy"])
        self.assertIsNone(case["dismissedAt"])
        self.assertEqual(sorted(case["allowedTransitions"]), ["assigned", "dismissed"])
        self.assertEqual(
            self.ledger(self.bank),
            [("new", "dismissed", self.bank.officer.id), ("dismissed", "new", self.bank.owner.id)],
        )
        self.assertEqual([row.actor_id for row in self.moves_audited(self.bank)], [self.bank.officer.id, self.bank.owner.id])

    def test_a_new_case_has_nothing_to_restore(self) -> None:
        self.assertProblem(self.move(self.bank, "restore", None), 409, "invalid_transition")

    def test_a_stale_restore_is_409(self) -> None:
        self.assertEqual(self.move(self.bank, "dismiss", {"reasonKey": "out_of_scope"}).status_code, 200)
        self.assertProblem(self.move(self.bank, "restore", None, version=1), 409, "stale_write")


class AnotherBank(CaseRoutes):
    def test_every_triage_move_on_another_banks_case_is_404_and_writes_nothing(self) -> None:
        mine = triage_bank()
        theirs = triage_bank()
        intruder = SimpleNamespace(**{**vars(theirs), "officer": mine.officer, "tenant": mine.tenant})
        for verb, body in (
            ("triage", {"urgency": "act_now", "ownerId": str(mine.owner.id)}),
            ("dismiss", {"reasonKey": "out_of_scope"}),
            ("restore", None),
            ("close", {"reasonKey": "no_action"}),
        ):
            with self.subTest(verb=verb):
                response = self.move(intruder, verb, body, version=1)
                self.assertProblem(response, 404, "not_found")
        self.assertEqual(self.case(theirs).status, "new")
        self.assertEqual(self.ledger(theirs), [])


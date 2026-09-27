"""Actions with an owner and a due date, locked while the case waits for sign-off, removed
softly (CAS-04, CAS-08; `apps/cases/actions.py`).

What is proved: a title is required and the owner defaults to the case's owner; an owner
who is not a live member of the bank is refused with `unknown_member`; the first action
moves an assessing case to implementing through the state machine, which wants a saved
why; `CASE_ACTIONS_MAX` refuses one more with `too_many_actions`; every write is refused
with `actions_locked` while the case is in the sign-off category, whatever its
sub-status, while the list still reads; each action has its own `If-Match`; a removal sets
`removed_at` and `removed_by`, keeps the row and lowers the open count; and another bank's
action is a 404 on every write.

Written before `actions.py` was built: every test below answered 501 `not_built`.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from apps.cases import logic
from apps.cases.models import Action, CaseTransition, ChangeCase, Evidence, EvidenceKind, ImpactAssessment
from apps.identity.models import Membership
from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import CaseSubStatus

V1 = "/api/v1"
C = CaseStatusCategory


def assessing(tenant: Any, owner: Any, *, why_saved: bool = True) -> ChangeCase:
    """A case in `assessing` owned by `owner`, its why saved unless told otherwise."""
    row = factories.case_change(tenant).case
    with transaction.atomic():
        tenancy.activate(tenant.id)
        ChangeCase.objects.filter(pk=row.pk).update(status=C.ASSESSING.value, owner=owner)
        ImpactAssessment.objects.create(
            tenant=tenant,
            case=row,
            why="The research we pay for must meet documented criteria." if why_saved else "",
            saved=why_saved,
            saved_by=owner if why_saved else None,
            saved_at=timezone.now() if why_saved else None,
        )
    row.refresh_from_db()
    return row


class ActionTests(ScenarioTestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.owner = factories.member(
            self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")
        ).user
        self.colleague = factories.member(self.tenant, roles=("contributor",)).user
        self.case = assessing(self.tenant, self.owner)
        self.due = timezone.localdate() + datetime.timedelta(days=14)

    # -- helpers ---------------------------------------------------------------------------
    def _headers(self, who: Any = None, tenant: Any = None) -> dict[str, Any]:
        return sign_in(who or self.owner, tenant=tenant or self.tenant)

    def _case_version(self) -> int:
        self.activate(self.tenant)
        return ChangeCase.objects.get(pk=self.case.pk).version

    def _add(self, body: dict[str, Any] | None = None, *, version: int | None = None, who: Any = None) -> Any:
        payload = {"title": "Document the annual research quality criteria", "dueDate": self.due.isoformat()}
        payload.update(body or {})
        headers = self._headers(who)
        headers["HTTP_IF_MATCH"] = str(self._case_version() if version is None else version)
        return self.client.post(
            f"{V1}/changes/{self.case.change_id}/actions", data=payload, content_type="application/json", **headers
        )

    def _patch(self, action_id: Any, body: dict[str, Any], *, version: int | None, who: Any = None, tenant: Any = None) -> Any:
        headers = self._headers(who, tenant)
        if version is not None:
            headers["HTTP_IF_MATCH"] = str(version)
        return self.client.patch(f"{V1}/actions/{action_id}", data=body, content_type="application/json", **headers)

    def _delete(self, action_id: Any, *, version: int | None, who: Any = None, tenant: Any = None) -> Any:
        headers = self._headers(who, tenant)
        if version is not None:
            headers["HTTP_IF_MATCH"] = str(version)
        return self.client.delete(f"{V1}/actions/{action_id}", **headers)

    def _list(self, who: Any = None) -> Any:
        return self.client.get(f"{V1}/changes/{self.case.change_id}/actions", **self._headers(who))

    def _open_count(self) -> int:
        self.activate(self.tenant)
        return logic.case_facts(ChangeCase.objects.get(pk=self.case.pk), actor=None).open_action_count

    def _to_signoff(self) -> None:
        """Every action done, one clean piece of evidence, and the move through
        `logic.transition()`, the real code path the sign-off request takes."""
        self.activate(self.tenant)
        Action.objects.filter(case=self.case, done_at__isnull=True).update(done_at=timezone.now(), done_by=self.owner)
        Evidence.objects.create(
            tenant=self.tenant,
            case=self.case,
            kind=EvidenceKind.LINK.value,
            name="Criteria memo",
            url="https://intranet.example.com/memo/7",
            uploaded_by=self.owner,
            scan_state="clean",
            scanned_at=timezone.now(),
        )
        case = logic.load_case(self.tenant, self.case.change_id, for_update=True)
        case.signoff_requested_by = self.owner
        case.signoff_requested_at = timezone.now()
        logic.transition(case, C.SIGNOFF, actor=Actor(kind=ActorType.USER, id=self.owner.id, label=self.owner.name), user=self.owner)

    # -- add -------------------------------------------------------------------------------
    def test_the_first_action_moves_the_case_to_implementing_and_the_owner_defaults(self) -> None:
        response = self._add()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["owner"]["id"], str(self.owner.id), "the owner defaults to the case's owner")
        self.assertEqual(body["dueDate"], self.due.isoformat())
        self.assertEqual(body["changeId"], str(self.case.change_id))
        self.assertFalse(body["done"])
        self.assertEqual(body["version"], 1)

        self.activate(self.tenant)
        case = ChangeCase.objects.get(pk=self.case.pk)
        self.assertEqual(case.status, C.IMPLEMENTING.value)
        self.assertEqual(case.version, self.case.version + 1, "the move raised the case's version")
        moved = CaseTransition.objects.get(case=case)
        self.assertEqual((moved.from_status, moved.to_status, moved.by_user_id), (C.ASSESSING.value, C.IMPLEMENTING.value, self.owner.id))
        self.assertEqual(self._open_count(), 1)
        added = AuditEvent.objects.get(action="case.action_added", subject_id=body["id"])
        self.assertEqual(added.actor_id, self.owner.id)
        self.assertEqual(added.after["ownerId"], str(self.owner.id))
        self.assertNotIn("title", added.after, "an audit value carries no text a person typed (rule m)")

    def test_a_second_action_leaves_the_case_where_it_is(self) -> None:
        self.assertEqual(self._add().status_code, 201)
        version = self._case_version()
        response = self._add({"ownerId": str(self.colleague.id), "title": "Train the desk"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["owner"]["id"], str(self.colleague.id))
        self.assertEqual(self._case_version(), version, "no move, no new case version")
        self.activate(self.tenant)
        self.assertEqual(CaseTransition.objects.filter(case=self.case).count(), 1)
        self.assertEqual(self._open_count(), 2)

    def test_the_move_needs_a_saved_why(self) -> None:
        self.case = assessing(self.tenant, self.owner, why_saved=False)
        response = self._add()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "why_required")
        self.activate(self.tenant)
        self.assertFalse(Action.objects.filter(case=self.case).exists(), "a refused move stores no action")

    def test_a_title_is_required(self) -> None:
        for title in ("", None):
            with self.subTest(title=title):
                response = self._add({"title": title})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "validation_error")

    def test_an_owner_outside_the_bank_is_refused(self) -> None:
        outsider = factories.member(factories.tenant(), roles=("compliance_officer",)).user
        departed = factories.member(self.tenant, roles=("contributor",)).user
        self.activate(self.tenant)
        Membership.objects.filter(tenant=self.tenant, user=departed).update(deactivated_at=timezone.now())
        for who in (outsider.id, departed.id, uuid.uuid4()):
            with self.subTest(owner=who):
                response = self._add({"ownerId": str(who)})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "unknown_member")

    def test_the_case_version_is_checked(self) -> None:
        response = self._add(version=self.case.version + 5)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_write")

    def test_a_case_that_is_not_worked_takes_no_action(self) -> None:
        self.activate(self.tenant)
        ChangeCase.objects.filter(pk=self.case.pk).update(status=C.ASSIGNED.value)
        response = self._add()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "invalid_transition")

    @override_settings(CASE_ACTIONS_MAX=2)
    def test_the_cap_refuses_one_more(self) -> None:
        self.assertEqual(self._add().status_code, 201)
        self.assertEqual(self._add().status_code, 201)
        response = self._add()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "too_many_actions")
        # A removed action no longer counts.
        self.activate(self.tenant)
        first = Action.objects.filter(case=self.case).first()
        assert first is not None
        self.assertEqual(self._delete(first.id, version=first.version).status_code, 204)
        self.assertEqual(self._add().status_code, 201)

    # -- list ------------------------------------------------------------------------------
    def test_the_list_holds_live_actions_by_due_date(self) -> None:
        later = self._add({"dueDate": (self.due + datetime.timedelta(days=7)).isoformat(), "title": "Later"}).json()
        sooner = self._add({"title": "Sooner"}).json()
        gone = self._add({"title": "Gone"}).json()
        self.assertEqual(self._delete(gone["id"], version=1).status_code, 204)
        response = self._list(self.colleague)
        self.assertEqual(response.status_code, 200)
        page = response.json()
        self.assertEqual([item["id"] for item in page["items"]], [sooner["id"], later["id"]])
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["items"][0]["owner"], {"id": str(self.owner.id), "name": "Sara Lind"})

    def test_an_empty_list_is_200(self) -> None:
        response = self._list()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "total": 0})

    # -- update ----------------------------------------------------------------------------
    def test_edit_complete_and_reopen_under_the_actions_own_version(self) -> None:
        action = self._add().json()
        response = self._patch(action["id"], {"title": "Sign the criteria", "dueDate": "2031-01-02"}, version=1, who=self.colleague)
        self.assertEqual(response.status_code, 200, response.content)
        edited = response.json()
        self.assertEqual((edited["title"], edited["dueDate"], edited["version"]), ("Sign the criteria", "2031-01-02", 2))
        self.assertEqual(edited["owner"]["id"], str(self.owner.id), "a field left out is kept")

        stale = self._patch(action["id"], {"done": True}, version=1, who=self.colleague)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "stale_write")
        self.assertEqual(self._patch(action["id"], {"done": True}, version=None).json()["code"], "stale_write")

        done = self._patch(action["id"], {"done": True}, version=2, who=self.colleague).json()
        self.assertTrue(done["done"])
        self.assertEqual(done["doneBy"]["id"], str(self.colleague.id))
        self.assertIsNotNone(done["doneAt"])
        self.assertEqual(self._open_count(), 0)

        reopened = self._patch(action["id"], {"done": False}, version=3).json()
        self.assertFalse(reopened["done"])
        self.assertIsNone(reopened["doneBy"])
        self.assertIsNone(reopened["doneAt"])
        self.assertEqual(self._open_count(), 1)
        self.activate(self.tenant)
        self.assertEqual(
            list(AuditEvent.objects.filter(subject_id=action["id"]).order_by("created", "id").values_list("action", flat=True)),
            ["case.action_added", "case.action_changed", "case.action_changed", "case.action_changed"],
        )

    def test_a_new_owner_must_be_a_member(self) -> None:
        action = self._add().json()
        response = self._patch(action["id"], {"ownerId": str(uuid.uuid4())}, version=1)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "unknown_member")
        moved = self._patch(action["id"], {"ownerId": str(self.colleague.id)}, version=1).json()
        self.assertEqual(moved["owner"]["id"], str(self.colleague.id))

    # -- delete ----------------------------------------------------------------------------
    def test_removal_keeps_the_row_and_lowers_the_open_count(self) -> None:
        action = self._add().json()
        self.assertEqual(self._open_count(), 1)
        self.assertEqual(self._delete(action["id"], version=None).json()["code"], "stale_write")
        response = self._delete(action["id"], version=1)
        self.assertEqual(response.status_code, 204)
        self.activate(self.tenant)
        row = Action.objects.get(pk=action["id"])
        self.assertIsNotNone(row.removed_at)
        self.assertEqual(row.removed_by_id, self.owner.id)
        self.assertEqual(self._open_count(), 0)
        removed = AuditEvent.objects.get(action="case.action_removed", subject_id=row.id)
        self.assertEqual(removed.actor_id, self.owner.id)
        self.assertEqual(self._list().json()["total"], 0)
        again = self._delete(action["id"], version=2)
        self.assertEqual(again.status_code, 404, "a removed action is never edited again")

    # -- the lock --------------------------------------------------------------------------
    def test_every_write_is_locked_in_the_signoff_category_and_the_list_still_reads(self) -> None:
        action = self._add().json()
        self._to_signoff()
        self.activate(self.tenant)
        # The lock reads the category, whatever sub-status the bank has put the case in.
        sub_status = CaseSubStatus.objects.get(tenant=self.tenant, key=C.SIGNOFF.value)
        ChangeCase.objects.filter(pk=self.case.pk).update(sub_status=sub_status)
        version = Action.objects.get(pk=action["id"]).version
        for name, response in (
            ("add", self._add()),
            ("edit", self._patch(action["id"], {"title": "Changed late"}, version=version)),
            ("reopen", self._patch(action["id"], {"done": False}, version=version)),
            ("remove", self._delete(action["id"], version=version)),
        ):
            with self.subTest(write=name):
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "actions_locked")
        self.assertEqual(self._list().status_code, 200)
        self.assertEqual(self._list().json()["total"], 1)

    # -- tenancy ---------------------------------------------------------------------------
    def test_another_banks_action_is_404_on_every_write(self) -> None:
        action = self._add().json()
        other = factories.tenant()
        stranger = factories.member(other, roles=("compliance_officer",)).user
        for name, response in (
            ("patch", self._patch(action["id"], {"done": True}, version=1, who=stranger, tenant=other)),
            ("delete", self._delete(action["id"], version=1, who=stranger, tenant=other)),
        ):
            with self.subTest(write=name):
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["code"], "not_found")
        self.activate(self.tenant)
        row = Action.objects.get(pk=action["id"])
        self.assertIsNone(row.done_at)
        self.assertIsNone(row.removed_at)

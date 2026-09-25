"""Tenant reach (ACC-08, D-72, ADR 0057; governance 0004).

Two different people holding `security.manage`, each with a fresh passkey assertion, switch
it on: one requests, the other approves, and the database refuses the requester deciding
their own request. Rejecting and switching off need the same permission and a step-up, and
off is off from the next read. `tenant_reach_on(tenant)` is what every register route will
ask."""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.governance import reach
from apps.governance.models import TenantReach, TenantReachRequest
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import ApprovalStatus

V1 = "/api/v1"
REACH = f"{V1}/tenant/reach"


class TenantReachTests(ScenarioTestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant(slug="reach")
        self.first = factories.member(self.tenant, roles=("admin",), user_row=factories.user(name="Erik Holm")).user
        self.second = factories.member(self.tenant, roles=("admin",), user_row=factories.user(name="Maria Ek")).user
        self.officer = factories.member(self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lindqvist")).user

    def post(self, path: str, user: Any, *, step_up: bool = True, **headers: Any) -> Any:
        return self.client.post(path, "{}", content_type="application/json", **sign_in(user, tenant=self.tenant, step_up=step_up), **headers)

    def ask(self) -> dict[str, Any]:
        response = self.post(f"{REACH}/requests", self.first)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def on(self) -> bool:
        self.activate(self.tenant)
        return reach.tenant_reach_on(self.tenant.id)

    def audit(self, action: str) -> AuditEvent:
        self.activate(self.tenant)
        return AuditEvent.objects.filter(tenant_id=self.tenant.id, action=action).order_by("-created").first()  # type: ignore[return-value]

    def test_off_until_a_second_person_approves_and_each_row_names_its_person_and_assertion(self) -> None:
        self.assertFalse(self.on())
        view = self.client.get(REACH, **sign_in(self.second, tenant=self.tenant)).json()
        self.assertEqual((view["enabled"], view["pending"]), (False, None))
        asked = self.ask()
        self.assertEqual((asked["status"], asked["requestedBy"]["id"]), ("pending", str(self.first.id)))
        self.assertFalse(self.on())
        self.assertEqual(self.client.get(REACH, **sign_in(self.second, tenant=self.tenant)).json()["pending"]["id"], asked["id"])
        approved = self.post(f"{REACH}/requests/{asked['id']}/approve", self.second)
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual((approved.json()["status"], approved.json()["decidedBy"]["id"]), ("approved", str(self.second.id)))
        self.assertTrue(self.on())
        requested, decided = self.audit("tenant_reach.requested"), self.audit("tenant_reach.approved")
        self.assertEqual((requested.actor_id, decided.actor_id), (self.first.id, self.second.id))
        self.assertIsNotNone(requested.step_up_assertion_id)
        self.assertIsNotNone(decided.step_up_assertion_id)
        self.assertNotEqual(requested.step_up_assertion_id, decided.step_up_assertion_id)
        self.assertEqual(decided.after["requestedBy"], str(self.first.id))
        self.assertEqual(decided.after["decidedBy"], str(self.second.id))
        view = self.client.get(REACH, **sign_in(self.first, tenant=self.tenant)).json()
        self.assertEqual((view["enabled"], view["pending"], view["changedBy"]["id"]), (True, None, str(self.second.id)))

    def test_the_requester_cannot_decide_their_own_request(self) -> None:
        asked = self.ask()
        for decision in ("approve", "reject"):
            with self.subTest(decision=decision):
                response = self.post(f"{REACH}/requests/{asked['id']}/{decision}", self.first)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "four_eyes_violation")
        self.assertFalse(self.on())

    def test_the_database_refuses_the_requester_as_decider(self) -> None:
        asked = self.ask()
        self.activate(self.tenant)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TenantReachRequest.objects.filter(pk=asked["id"]).update(decided_by=self.first, decided_at=timezone.now())

    def test_a_rejected_request_leaves_reach_off_and_is_final(self) -> None:
        asked = self.ask()
        rejected = self.post(f"{REACH}/requests/{asked['id']}/reject", self.second)
        self.assertEqual((rejected.status_code, rejected.json()["status"]), (200, "rejected"))
        self.assertFalse(self.on())
        self.assertEqual(self.audit("tenant_reach.rejected").actor_id, self.second.id)
        self.assertIsNotNone(self.audit("tenant_reach.rejected").step_up_assertion_id)
        again = self.post(f"{REACH}/requests/{asked['id']}/approve", self.second)
        self.assertEqual((again.status_code, again.json()["code"]), (409, "invalid_transition"))

    def test_switching_off_is_immediate_and_needs_no_second_person(self) -> None:
        asked = self.ask()
        self.post(f"{REACH}/requests/{asked['id']}/approve", self.second)
        self.assertTrue(self.on())
        off = self.post(f"{REACH}/off", self.first)
        self.assertEqual((off.status_code, off.json()["enabled"]), (200, False))
        self.assertFalse(self.on())
        switched = self.audit("tenant_reach.switched_off")
        self.assertEqual(switched.actor_id, self.first.id)
        self.assertIsNotNone(switched.step_up_assertion_id)
        again = self.post(f"{REACH}/off", self.first)
        self.assertEqual((again.status_code, again.json()["code"]), (409, "invalid_transition"))
        # Back on takes a new request and a second person again.
        self.assertEqual(self.ask()["status"], "pending")
        self.assertFalse(self.on())

    def test_one_pending_request_and_none_while_reach_is_on(self) -> None:
        asked = self.ask()
        duplicate = self.post(f"{REACH}/requests", self.second)
        self.assertEqual((duplicate.status_code, duplicate.json()["code"]), (409, "request_pending"))
        self.post(f"{REACH}/requests/{asked['id']}/approve", self.second)
        while_on = self.post(f"{REACH}/requests", self.second)
        self.assertEqual((while_on.status_code, while_on.json()["code"]), (409, "invalid_transition"))

    def test_every_write_needs_security_manage_and_a_step_up(self) -> None:
        asked = self.ask()
        writes = [f"{REACH}/requests", f"{REACH}/requests/{asked['id']}/approve", f"{REACH}/requests/{asked['id']}/reject", f"{REACH}/off"]
        for path in writes:
            with self.subTest(path=path):
                stale = self.post(path, self.second, step_up=False)
                self.assertEqual((stale.status_code, stale.json()["code"]), (403, "step_up_required"))
                refused = self.post(path, self.officer)
                self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, "security.manage"))
        read = self.client.get(REACH, **sign_in(self.officer, tenant=self.tenant))
        self.assertEqual((read.status_code, read.json()["requiredPermission"]), (403, "security.manage"))
        self.activate(self.tenant)
        self.assertEqual(TenantReachRequest.objects.get(pk=asked["id"]).status, ApprovalStatus.PENDING.value)

    def test_a_stale_version_is_refused(self) -> None:
        asked = self.ask()
        response = self.post(f"{REACH}/requests/{asked['id']}/approve", self.second, HTTP_IF_MATCH=str(asked["version"] + 1))
        self.assertEqual((response.status_code, response.json()["code"]), (409, "stale_write"))
        self.assertFalse(self.on())

    def test_another_banks_reach_is_neither_read_nor_decided(self) -> None:
        asked = self.ask()
        self.post(f"{REACH}/requests/{asked['id']}/approve", self.second)
        other = factories.tenant(slug="reach-other")
        outsider = factories.member(other, roles=("admin",)).user
        headers = sign_in(outsider, tenant=other, step_up=True)
        self.assertEqual(self.client.get(REACH, **headers).json()["enabled"], False)
        response = self.client.post(f"{REACH}/requests/{asked['id']}/reject", "{}", content_type="application/json", **headers)
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        tenancy.activate(other.id)
        self.assertFalse(reach.tenant_reach_on(other.id))
        self.assertFalse(reach.tenant_reach_on(self.tenant.id), "under another bank's zone the state row is invisible")
        self.assertEqual(TenantReach.objects.count(), 0)
        self.assertTrue(self.on())

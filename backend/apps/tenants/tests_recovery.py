"""The last admin's recovery through platform support (ID-05, ID-S13) leaves a trace only when
it happens (security-review-c8 M6): a refused recovery writes no support access row and no
audit row in the bank."""

from __future__ import annotations

import uuid

from django.utils import timezone

from apps.shared import factories
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.tenants.models import SupportAccess

BODY = {"reason": "Lost every passkey", "ticketRef": "SUP-42", "outOfBandCheck": "Called back on the registered number"}


class ARefusedRecoveryLeavesNoTrace(ScenarioTestCase):
    def test_a_person_who_is_not_a_live_member_is_404_and_nothing_is_recorded(self) -> None:
        bank = factories.tenant(slug="recovery-bank")
        factories.member(bank, roles=("admin",))
        gone = factories.member(bank, roles=("reader",))
        self.activate(bank)
        gone.deactivated_at = timezone.now()
        gone.save(update_fields=["deactivated_at"])
        support = factories.platform_user(roles=("platform_admin",))
        headers = sign_in(support, tenant=None, step_up=True)
        for user_id in (uuid.uuid4(), gone.user_id, factories.member_user(factories.tenant(slug="recovery-other"), roles=("admin",)).id):
            with self.subTest(user_id=user_id):
                response = self.client.post(
                    f"/api/v1/console/tenants/{bank.id}/members/{user_id}/reissue-enrolment", BODY, content_type="application/json", **headers
                )
                self.assertEqual(response.status_code, 404, response.content)
        self.activate(bank)
        self.assertFalse(SupportAccess.objects.filter(tenant=bank).exists())
        self.assertFalse(AuditEvent.objects.filter(tenant=bank, action="support_access.recorded").exists())

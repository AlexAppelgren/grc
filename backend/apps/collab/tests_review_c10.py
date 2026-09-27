"""The chunk 10 security review's fixes (security-review-c10, docs/reviews/CHUNK10_REVIEW.md).

Each class pins one finding, red before its fix:

- **M1, the delegation hop reaches the person who caused the notice.** A sign-off request
  and an assignment name the person who made the move, so an away recipient whose delegate
  is that person keeps the notice (TEN-04, CAS-06): a four-eyes request never lands only
  with the one person who may not approve it.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.test import TestCase

from apps.cases.tests_signoff import Bank
from apps.cases.tests_triage import CaseMoves, triage_bank
from apps.collab.models import Notification, NotificationKind
from apps.identity.models import Membership
from apps.library.reading import today_for
from apps.shared import tenancy
from apps.shared.testing import AuditAssertingClient


def _away(tenant: Any, person: Any, delegate: Any) -> None:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        Membership.objects.filter(tenant=tenant, user=person).update(out_of_office_until=today_for(tenant), delegate=delegate)


def _told(tenant: Any, kind: NotificationKind) -> list[tuple[Any, Any]]:
    tenancy.activate(tenant.id)
    return sorted(Notification.objects.filter(kind=kind.value).values_list("user_id", "on_behalf_of_id"))


class TheMoverIsNeverTheDelegate(CaseMoves, TestCase):
    client_class = AuditAssertingClient

    def test_a_signoff_request_stays_with_the_away_approver_whose_delegate_asked(self) -> None:
        """The approver is away and named the case's owner as delegate; the owner asks for
        sign-off. The approver keeps the request, and the owner is not told on their behalf."""
        bank = Bank()
        _away(bank.tenant, bank.approver, bank.owner)
        bank.ready_for_signoff(self.client)
        self.assertEqual(_told(bank.tenant, NotificationKind.SIGNOFF_REQUESTED), [(bank.approver.id, None)])

    def test_an_assignment_stays_with_the_away_owner_whose_delegate_triaged(self) -> None:
        """The new owner is away and named the officer as delegate; the officer triages the
        case to them. The owner keeps the assignment rather than the officer taking it."""
        bank = triage_bank()
        _away(bank.tenant, bank.owner, bank.officer)
        response = self.move(bank, "triage", {"urgency": "within_3_months", "ownerId": str(bank.owner.id)})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_told(bank.tenant, NotificationKind.ASSIGNED), [(bank.owner.id, None)])

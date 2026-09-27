"""The notification inbox (COL-02; `c10-inbox-and-my-comments`, CHUNK10_TASKS
`c10-notifications-api-b`): a person's own rows, newest first, paged, and marking them read.

Each rule is its own test: no parameter reaches another person's or another bank's row, and
such an id answers 404 in status and body; marking one is idempotent and marking all is one
UPDATE; both marks record a `notification.read` event with ids and never a title; a row whose
record the reader can no longer read keeps the title it was written with; a page of 20 costs
a pinned number of queries.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.collab import logic
from apps.collab.models import Notification, NotificationKind
from apps.identity.models import MembershipRole, TenantRole, User
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in
from apps.watch import testing as watch_build

TITLE = "FI amends the rules on research payments"
URL = "/api/v1/notifications"


def _rows(tenant: Tenant, user: User, count: int, *, start: datetime.datetime | None = None) -> list[Notification]:
    """`count` rows for `user`, one minute apart, the last one newest. Written directly,
    since the inbox only reads them: who may be told is `notify()`'s, proved in tests_notify."""
    tenancy.activate(tenant.id)
    start = start or timezone.now() - datetime.timedelta(days=1)
    rows = Notification.objects.bulk_create(
        Notification(
            tenant=tenant,
            user=user,
            kind=NotificationKind.MENTION.value,
            subject_type="change_case",
            subject_id=uuid.uuid4(),
            title=f"{TITLE} {n}",
        )
        for n in range(count)
    )
    for n, row in enumerate(rows):
        Notification.objects.filter(pk=row.pk).update(created_at=start + datetime.timedelta(minutes=n))
    return rows


class InboxTestCase(TestCase):
    tenant: Tenant
    other: Tenant
    anna: User
    erik: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant(slug="inbox")
        cls.other = factories.tenant(slug="inbox-other")
        cls.anna = factories.member_user(cls.tenant, roles=("contributor",))
        cls.erik = factories.member_user(cls.tenant, roles=("reader",))
        # Anna also belongs to another bank, where she has a row of her own.
        factories.member(cls.other, roles=("reader",), user_row=cls.anna)

    def as_person(self, user: User, tenant: Tenant | None = None) -> dict[str, Any]:
        return sign_in(user, tenant=tenant or self.tenant)

    def audit(self) -> Any:
        tenancy.activate(self.tenant.id)
        return AuditEvent.objects.filter(action="notification.read").order_by("created")


class ListNotifications(InboxTestCase):
    def test_own_rows_newest_first_in_pages(self) -> None:
        mine = _rows(self.tenant, self.anna, 3)
        _rows(self.tenant, self.erik, 2)
        _rows(self.other, self.anna, 1)
        headers = self.as_person(self.anna)

        first = self.client.get(f"{URL}?limit=2", **headers).json()
        second = self.client.get(f"{URL}?limit=2&offset=2", **headers).json()

        self.assertEqual(first["total"], 3)
        self.assertEqual([item["id"] for item in first["items"] + second["items"]], [str(row.id) for row in reversed(mine)])
        self.assertEqual(
            set(first["items"][0]),
            {"id", "kind", "subjectType", "subjectId", "title", "createdAt", "readAt"},
        )

    def test_unread_lists_only_rows_not_yet_read_and_counts_them(self) -> None:
        rows = _rows(self.tenant, self.anna, 3)
        tenancy.activate(self.tenant.id)
        Notification.objects.filter(pk=rows[0].pk).update(read_at=timezone.now())
        headers = self.as_person(self.anna)

        unread = self.client.get(f"{URL}?unread=true", **headers).json()
        everything = self.client.get(URL, **headers).json()

        self.assertEqual({item["id"] for item in unread["items"]}, {str(rows[1].id), str(rows[2].id)})
        self.assertEqual(unread["total"], 2)
        self.assertEqual(everything["total"], 3)

    def test_nothing_to_tell_is_an_empty_200(self) -> None:
        response = self.client.get(URL, **self.as_person(self.erik))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "total": 0})

    def test_a_row_whose_record_is_no_longer_readable_keeps_its_stored_title(self) -> None:
        watch_build.seed_watch_reference()
        tenancy.activate(self.tenant.id)
        case = cases_build.case(self.tenant, watch_build.change(title=TITLE))
        tenancy.activate(self.tenant.id)
        [row] = logic.notify(
            tenant_id=self.tenant.id,
            kind=NotificationKind.ASSIGNED,
            subject_type="change_case",
            subject_id=case.id,
            candidates=[(self.erik.id, "owner")],
        )
        # Erik's role no longer reads cases: the row stays, with the title he was shown.
        no_cases = TenantRole.objects.create(tenant=self.tenant, key="no-cases", permissions=[perms.REGISTER_READ])
        membership = self.erik.memberships.get(tenant=self.tenant)
        MembershipRole.objects.filter(membership=membership).delete()
        MembershipRole.objects.create(tenant=self.tenant, membership=membership, role=no_cases)

        items = self.client.get(URL, **self.as_person(self.erik)).json()["items"]

        self.assertEqual([(item["id"], item["title"]) for item in items], [(str(row.id), TITLE)])

    def test_a_page_of_twenty_costs_a_pinned_number_of_queries(self) -> None:
        """The session and its roles, the tenant, the user, the page and its count, inside
        the request's savepoint: twelve statements, and nothing per row."""
        _rows(self.tenant, self.anna, 25)
        headers = self.as_person(self.anna)
        self.client.get(URL, **headers)  # warm the session cache the first call fills
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(len(self.client.get(f"{URL}?limit=2", **headers).json()["items"]), 2)
        with CaptureQueriesContext(connection) as page:
            self.assertEqual(len(self.client.get(URL, **headers).json()["items"]), 20)
        self.assertEqual(len(page), len(small))
        with CaptureQueriesContext(connection) as unread:
            self.client.get(f"{URL}?unread=true", **headers)
        self.assertEqual(len(unread), len(page))
        self.assertEqual(len(page), 12, [q["sql"][:90] for q in page])

    def test_reading_writes_no_audit_row(self) -> None:
        _rows(self.tenant, self.anna, 2)
        self.client.get(URL, **self.as_person(self.anna))
        self.assertFalse(self.audit().exists())


class MarkOneRead(InboxTestCase):
    def test_marks_once_and_records_ids_only(self) -> None:
        row, other = _rows(self.tenant, self.anna, 2)
        headers = self.as_person(self.anna)

        response = self.client.post(f"{URL}/{row.id}/read", **headers)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        tenancy.activate(self.tenant.id)
        read_at = Notification.objects.get(pk=row.pk).read_at
        self.assertIsNotNone(read_at)
        self.assertIsNone(Notification.objects.get(pk=other.pk).read_at)
        [event] = self.audit()
        self.assertEqual(event.actor_id, self.anna.id)
        self.assertEqual(event.subject_id, row.id)
        self.assertEqual(event.after["notificationIds"], [str(row.id)])
        self.assertNotIn(TITLE, f"{event.subject_title} {event.summary} {event.after}")

    def test_marking_again_changes_nothing_and_still_answers_204(self) -> None:
        [row] = _rows(self.tenant, self.anna, 1)
        headers = self.as_person(self.anna)
        self.client.post(f"{URL}/{row.id}/read", **headers)
        tenancy.activate(self.tenant.id)
        first = Notification.objects.get(pk=row.pk).read_at

        response = self.client.post(f"{URL}/{row.id}/read", **headers)

        self.assertEqual(response.status_code, 204)
        tenancy.activate(self.tenant.id)
        self.assertEqual(Notification.objects.get(pk=row.pk).read_at, first)
        self.assertEqual(self.audit().count(), 1)

    def test_another_persons_or_another_banks_or_an_unknown_id_is_404(self) -> None:
        [eriks] = _rows(self.tenant, self.erik, 1)
        [elsewhere] = _rows(self.other, self.anna, 1)
        headers = self.as_person(self.anna)
        for name, pk in (("another person's", eriks.id), ("another bank's", elsewhere.id), ("unknown", uuid.uuid4())):
            with self.subTest(name):
                response = self.client.post(f"{URL}/{pk}/read", **headers)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["code"], "not_found")
                self.assertEqual(response.json()["status"], 404)
        tenancy.activate(self.tenant.id)
        self.assertIsNone(Notification.objects.get(pk=eriks.pk).read_at)
        tenancy.activate(self.other.id)
        self.assertIsNone(Notification.objects.get(pk=elsewhere.pk).read_at)
        self.assertFalse(self.audit().exists())


class MarkAllRead(InboxTestCase):
    def test_one_update_marks_every_unread_row_of_the_caller_and_nobody_elses(self) -> None:
        mine = _rows(self.tenant, self.anna, 4)
        eriks = _rows(self.tenant, self.erik, 2)
        elsewhere = _rows(self.other, self.anna, 1)
        tenancy.activate(self.tenant.id)
        earlier = timezone.now() - datetime.timedelta(hours=1)
        Notification.objects.filter(pk=mine[0].pk).update(read_at=earlier)
        headers = self.as_person(self.anna)

        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(f"{URL}/read-all", **headers)

        self.assertEqual(response.status_code, 204)
        updates = [q["sql"] for q in queries if q["sql"].startswith('UPDATE "notification"')]
        self.assertEqual(len(updates), 1)
        tenancy.activate(self.tenant.id)
        self.assertEqual(Notification.objects.get(pk=mine[0].pk).read_at, earlier)
        self.assertFalse(Notification.objects.filter(user=self.anna, read_at__isnull=True).exists())
        self.assertFalse(Notification.objects.filter(pk__in=[row.pk for row in eriks], read_at__isnull=False).exists())
        tenancy.activate(self.other.id)
        self.assertIsNone(Notification.objects.get(pk=elsewhere[0].pk).read_at)
        [event] = self.audit()
        self.assertEqual(event.actor_id, self.anna.id)
        self.assertEqual(sorted(event.after["notificationIds"]), sorted(str(row.id) for row in mine[1:]))
        self.assertNotIn(TITLE, f"{event.subject_title} {event.summary} {event.after}")

    def test_nothing_unread_is_204_and_records_nothing(self) -> None:
        response = self.client.post(f"{URL}/read-all", **self.as_person(self.erik))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(self.audit().exists())

    def test_the_log_carries_ids_and_never_a_title(self) -> None:
        _rows(self.tenant, self.anna, 2)
        headers = self.as_person(self.anna)
        with self.assertLogs("apps.collab.inbox", level="INFO") as logs:
            self.client.post(f"{URL}/read-all", **headers)
        records = [f"{record.getMessage()} {record.__dict__}" for record in logs.records]
        self.assertTrue(any(str(self.anna.id) in line for line in records))
        self.assertFalse(any(TITLE in line for line in records))

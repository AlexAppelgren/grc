"""My comments and mentions on My work (COL-01, HOM-05; `c10-inbox-and-my-comments`,
CHUNK10_TASKS `f03-T80a`): the caller's own comments, or other people's that name them,
newest first, paged, filtered through the subject registry.

The rules proved here, each on its own: `written` and `mentioned` list the right halves; a
role without `cases.read` gets no case comment, the kind is named in
`permissionLimitedKinds` and the total counts only what the caller may read; each row
carries its record's title in the caller's language, read today; a deleted comment and
another bank's comment are never listed; `canEdit` follows the author and the edit window;
a page costs a pinned number of queries; and the read writes no audit row and logs nothing.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.collab.models import Comment, CommentMention
from apps.identity.models import MembershipRole, TenantRole, User
from apps.library import testing as library_build
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in
from apps.watch import testing as watch_build

URL = "/api/v1/me/comments"
CHANGE_TITLE = "FI amends the rules on research payments"
TITLES = {"en": "Assess suitability before advice", "sv": "Bedöm lämplighet före rådgivning"}
SECRET = "the custody angle nobody outside the bank may read"


class MyCommentsTestCase(TestCase):
    tenant: Tenant
    other: Tenant
    anna: User
    erik: User
    johan: User
    first: Any
    second: Any
    case: Any

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="my-comments")
        cls.other = factories.tenant(slug="my-comments-other")
        cls.anna = factories.member_user(cls.tenant, roles=("contributor",))
        cls.anna.locale = factories.language("sv")
        cls.anna.save(update_fields=["locale"])
        cls.erik = factories.member_user(cls.tenant, roles=("contributor",))
        # Johan's role reads the library and the register and writes comments, but not cases.
        tenancy.activate(cls.tenant.id)
        no_cases = TenantRole.objects.create(
            tenant=cls.tenant,
            key="no-cases",
            permissions=[perms.LIBRARY_READ, perms.REGISTER_READ, perms.COMMENTS_WRITE],
        )
        membership = factories.member(cls.tenant, roles=("reader",))
        MembershipRole.objects.filter(membership=membership).delete()
        MembershipRole.objects.create(tenant=cls.tenant, membership=membership, role=no_cases)
        cls.johan = membership.user
        factories.member(cls.other, roles=("contributor",), user_row=cls.anna)

        on = library_build.instrument(key="inst-my-comments", regime="regime:securities")
        cls.first = library_build.obligation(on, key="obl-my-comments-1", titles=TITLES)
        cls.second = library_build.obligation(on, key="obl-my-comments-2", titles={"en": "Keep records of advice"})
        cls.case = cases_build.case(cls.tenant, watch_build.change(title=CHANGE_TITLE))

    def comment(
        self,
        author: User,
        subject_type: str,
        subject_id: uuid.UUID,
        *,
        minutes_ago: int,
        mentions: tuple[User, ...] = (),
        tenant: Tenant | None = None,
        deleted: bool = False,
    ) -> Comment:
        """A comment as `POST /comments` leaves it, written directly: this module only reads."""
        tenant = tenant or self.tenant
        tenancy.activate(tenant.id)
        row = Comment.objects.create(tenant=tenant, subject_type=subject_type, subject_id=subject_id, author=author, body=SECRET)
        written = timezone.now() - datetime.timedelta(minutes=minutes_ago)
        Comment.objects.filter(pk=row.pk).update(created_at=written, deleted_at=timezone.now() if deleted else None)
        for person in mentions:
            CommentMention.objects.create(tenant=tenant, comment=row, user=person)
        row.refresh_from_db()
        return row

    def read(self, user: User, query: str) -> dict[str, Any]:
        response = self.client.get(f"{URL}?{query}", **sign_in(user, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class Written(MyCommentsTestCase):
    def test_my_comments_newest_first_in_pages_with_the_record_title_in_my_language(self) -> None:
        older = self.comment(self.anna, "obligation", self.first.id, minutes_ago=90)
        newer = self.comment(self.anna, "obligation", self.second.id, minutes_ago=5, mentions=(self.erik,))
        self.comment(self.anna, "obligation", self.first.id, minutes_ago=1, deleted=True)
        self.comment(self.erik, "obligation", self.first.id, minutes_ago=2)
        self.comment(self.anna, "obligation", self.first.id, minutes_ago=3, tenant=self.other)

        first = self.read(self.anna, "about=written&limit=1")
        second = self.read(self.anna, "about=written&limit=1&offset=1")

        self.assertEqual(first["total"], 2)
        self.assertEqual(first["permissionLimitedKinds"], [])
        self.assertEqual([row["id"] for row in first["items"] + second["items"]], [str(newer.id), str(older.id)])
        row = first["items"][0]
        self.assertEqual(row["subjectType"], "obligation")
        self.assertEqual(row["subjectId"], str(self.second.id))
        self.assertEqual(row["subjectTitle"], "Keep records of advice")
        self.assertEqual(second["items"][0]["subjectTitle"], TITLES["sv"])
        self.assertEqual(row["body"], SECRET)
        self.assertEqual(row["author"], {"id": str(self.anna.id), "name": self.anna.name})
        self.assertEqual(row["mentions"], [{"id": str(self.erik.id), "name": self.erik.name}])
        self.assertIsNone(row["deletedAt"])
        self.assertTrue(row["canDelete"])

    @override_settings(COMMENT_EDIT_MINUTES=15)
    def test_can_edit_only_within_the_edit_window(self) -> None:
        recent = self.comment(self.anna, "obligation", self.first.id, minutes_ago=5)
        old = self.comment(self.anna, "obligation", self.first.id, minutes_ago=30)

        items = {row["id"]: row for row in self.read(self.anna, "about=written")["items"]}

        self.assertTrue(items[str(recent.id)]["canEdit"])
        self.assertFalse(items[str(old.id)]["canEdit"])
        self.assertTrue(items[str(old.id)]["canDelete"])

    def test_nothing_written_is_an_empty_200(self) -> None:
        self.assertEqual(self.read(self.erik, "about=written"), {"items": [], "total": 0, "permissionLimitedKinds": []})


class Mentioned(MyCommentsTestCase):
    def test_other_peoples_comments_that_name_me_with_a_link_to_the_case(self) -> None:
        on_case = self.comment(self.erik, "change_case", self.case.id, minutes_ago=10, mentions=(self.anna, self.johan))
        self.comment(self.anna, "obligation", self.first.id, minutes_ago=5, mentions=(self.anna,))
        self.comment(self.erik, "obligation", self.first.id, minutes_ago=4)

        page = self.read(self.anna, "about=mentioned")

        self.assertEqual(page["total"], 1)
        [row] = page["items"]
        self.assertEqual(row["id"], str(on_case.id))
        self.assertEqual((row["subjectType"], row["subjectId"], row["subjectTitle"]), ("change_case", str(self.case.id), CHANGE_TITLE))
        self.assertEqual(row["author"]["id"], str(self.erik.id))
        self.assertFalse(row["canEdit"])
        self.assertFalse(row["canDelete"])

    def test_a_role_without_cases_read_gets_no_case_comment_and_is_told_the_kind(self) -> None:
        self.comment(self.erik, "change_case", self.case.id, minutes_ago=10, mentions=(self.johan,))
        on_obligation = self.comment(self.erik, "obligation", self.first.id, minutes_ago=20, mentions=(self.johan,))

        page = self.read(self.johan, "about=mentioned")

        self.assertEqual([row["id"] for row in page["items"]], [str(on_obligation.id)])
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["permissionLimitedKinds"], ["change_case"])
        self.assertNotIn(str(self.case.id), str(page))
        self.assertNotIn(CHANGE_TITLE, str(page))

    def test_a_kind_is_limited_only_when_something_was_held_back(self) -> None:
        self.comment(self.erik, "obligation", self.first.id, minutes_ago=20, mentions=(self.johan,))
        self.assertEqual(self.read(self.johan, "about=mentioned")["permissionLimitedKinds"], [])

    def test_a_deleted_comment_that_named_me_is_not_listed(self) -> None:
        self.comment(self.erik, "obligation", self.first.id, minutes_ago=20, mentions=(self.anna,), deleted=True)
        self.assertEqual(self.read(self.anna, "about=mentioned")["items"], [])


class Cost(MyCommentsTestCase):
    def test_a_page_of_twenty_costs_the_same_as_a_page_of_two(self) -> None:
        """The limited kinds, the page, its mentions, the reader's language and its count, plus
        one title lookup per distinct record on the page: eighteen statements with the session,
        and nothing per comment."""
        for n in range(22):
            subject = ("obligation", self.first.id) if n % 2 else ("change_case", self.case.id)
            self.comment(self.erik, *subject, minutes_ago=n + 1, mentions=(self.anna,))
        headers = sign_in(self.anna, tenant=self.tenant)
        self.client.get(f"{URL}?about=mentioned", **headers)  # warm the session cache the first call fills
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(len(self.client.get(f"{URL}?about=mentioned&limit=2", **headers).json()["items"]), 2)
        with CaptureQueriesContext(connection) as page:
            self.assertEqual(len(self.client.get(f"{URL}?about=mentioned", **headers).json()["items"]), 20)
        self.assertEqual(len(page), len(small))
        self.assertEqual(len(page), 18, [q["sql"][:90] for q in page])

    def test_reading_writes_no_audit_row_and_logs_no_text(self) -> None:
        self.comment(self.erik, "obligation", self.first.id, minutes_ago=5, mentions=(self.anna,))
        headers = sign_in(self.anna, tenant=self.tenant)
        tenancy.activate(self.tenant.id)
        before = AuditEvent.objects.count()
        with self.assertNoLogs("apps.collab", level="DEBUG"):
            self.assertEqual(self.client.get(f"{URL}?about=mentioned", **headers).json()["items"][0]["body"], SECRET)
        tenancy.activate(self.tenant.id)
        self.assertEqual(AuditEvent.objects.count(), before)

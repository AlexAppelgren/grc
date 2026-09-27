"""Comments on a record and the mentions that notify (COL-01, COL-02; CHUNK10_TASKS rulings 3,
9, 10 and 13; `c10-comments-mentions`).

Each rule of `collab/comments.py` is its own test: who may read a record's comments and who
gets 404, the author's own edit window and the text an edit keeps, the soft delete, the
mention check with its one notification per person in the comment's own transaction, and
the pinned cost of a page. COL-S1 and COL-S5 themselves live in `tests_scenarios.py`.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Sequence
from typing import Any
from unittest import mock

from django.db import connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.collab.models import Comment, CommentMention, CommentRevision, EmailMessage, Notification
from apps.identity.models import Membership, TenantRole, User, UserStatus
from apps.library import testing as library_build
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent, OutboxEvent, Tenant
from apps.shared.testing import sign_in
from apps.watch import testing as watch_build

CHANGE_TITLE = "FI amends the custody rules for client assets"
PLANTED = "planted-marker-in-the-text"


class CommentsTestCase(TestCase):
    tenant: Tenant
    other: Tenant
    anna: User
    erik: User
    case: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="comments")
        cls.other = factories.tenant(slug="comments-other")
        cls.anna = factories.member_user(cls.tenant, roles=("contributor",))
        cls.erik = factories.member_user(cls.tenant, roles=("reader",))
        cls.case = cases_build.case(cls.tenant, watch_build.change(title=CHANGE_TITLE))

    def headers(self, user: User, tenant: Tenant | None = None) -> dict[str, Any]:
        return sign_in(user, tenant=tenant or self.tenant)

    def add(self, user: User, body: str = f"Please check the {PLANTED}.", *, mentions: Sequence[Any] = (), subject_type: str = "change_case", subject_id: Any = None, tenant: Tenant | None = None) -> Any:
        payload = {
            "subjectType": subject_type,
            "subjectId": str(subject_id or self.case.id),
            "body": body,
            "mentionUserIds": [str(getattr(person, "id", person)) for person in mentions],
        }
        return self.client.post("/api/v1/comments", data=payload, content_type="application/json", **self.headers(user, tenant))

    def listing(self, user: User, *, subject_type: str = "change_case", subject_id: Any = None, tenant: Tenant | None = None, limit: int = 20) -> Any:
        url = f"/api/v1/comments?subjectType={subject_type}&subjectId={subject_id or self.case.id}&limit={limit}"
        return self.client.get(url, **self.headers(user, tenant))

    def edit(self, user: User, comment_id: Any, body: str, tenant: Tenant | None = None) -> Any:
        return self.client.patch(
            f"/api/v1/comments/{comment_id}", data={"body": body}, content_type="application/json", **self.headers(user, tenant)
        )

    def delete(self, user: User, comment_id: Any, tenant: Tenant | None = None) -> Any:
        return self.client.delete(f"/api/v1/comments/{comment_id}", **self.headers(user, tenant))

    def written(self, response: Any) -> str:
        self.assertEqual(response.status_code, 201, response.content)
        return str(response.json()["id"])

    def refused(self, response: Any, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["code"], code)

    def in_tenant(self, tenant: Tenant | None = None) -> None:
        tenancy.activate((tenant or self.tenant).id)

    def comments(self) -> int:
        self.in_tenant()
        return Comment.objects.count()

    def limited_member(self) -> User:
        """A member of the bank whose own role cannot read a case: permissions, never role names."""
        with transaction.atomic():
            self.in_tenant()
            TenantRole.objects.get_or_create(tenant=self.tenant, key="roadmap-only", defaults={"permissions": [perms.ROADMAP_READ, perms.COMMENTS_WRITE]})
        return factories.member(self.tenant, roles=("roadmap-only",)).user


class ReadingARecordsComments(CommentsTestCase):
    def test_the_thread_reads_oldest_first_with_a_marker_where_a_comment_was_deleted(self) -> None:
        first = self.written(self.add(self.anna, "First."))
        second = self.written(self.add(self.erik, "Second.", mentions=[self.anna]))
        third = self.written(self.add(self.anna, "Third."))
        self.assertEqual(self.delete(self.anna, third).status_code, 204)

        response = self.listing(self.anna)
        self.assertEqual(response.status_code, 200, response.content)
        page = response.json()
        self.assertEqual(page["total"], 3)
        self.assertEqual([item["id"] for item in page["items"]], [first, second, third])
        by_id = {item["id"]: item for item in page["items"]}
        self.assertEqual(by_id[first]["body"], "First.")
        self.assertEqual(by_id[first]["author"], {"id": str(self.anna.id), "name": self.anna.name})
        self.assertEqual(by_id[second]["mentions"], [{"id": str(self.anna.id), "name": self.anna.name}])
        self.assertIsNone(by_id[third]["body"])
        self.assertIsNotNone(by_id[third]["deletedAt"])
        # What the caller may do is the caller's: the author edits and deletes their own only.
        self.assertEqual((by_id[first]["canEdit"], by_id[first]["canDelete"]), (True, True))
        self.assertEqual((by_id[second]["canEdit"], by_id[second]["canDelete"]), (False, False))
        self.assertEqual((by_id[third]["canEdit"], by_id[third]["canDelete"]), (False, False))

    def test_a_record_nobody_commented_on_is_an_empty_200(self) -> None:
        response = self.listing(self.anna)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "total": 0})

    def test_a_kind_the_registry_does_not_hold_is_422_on_the_read_and_the_write(self) -> None:
        self.refused(self.listing(self.anna, subject_type="change"), 422, "unsupported_subject")
        self.refused(self.add(self.anna, subject_type="change"), 422, "unsupported_subject")
        self.assertEqual(self.comments(), 0)

    def test_a_record_the_reader_may_not_read_is_404_never_403_and_never_empty(self) -> None:
        limited = self.limited_member()
        self.refused(self.listing(limited), 404, "not_found")
        self.refused(self.add(limited), 404, "not_found")
        self.assertEqual(self.comments(), 0)

    def test_another_banks_record_and_an_unknown_id_are_404(self) -> None:
        foreign = cases_build.case(self.other, watch_build.change(title=CHANGE_TITLE))
        for subject_id in (foreign.id, uuid.uuid4()):
            with self.subTest(subject_id=subject_id):
                self.refused(self.listing(self.anna, subject_id=subject_id), 404, "not_found")
                self.refused(self.add(self.anna, subject_id=subject_id), 404, "not_found")
        self.assertEqual(self.comments(), 0)

    def test_another_banks_comment_id_is_404_on_the_edit_and_the_delete(self) -> None:
        comment_id = self.written(self.add(self.anna))
        stranger = factories.member_user(self.other, roles=("compliance_officer",))
        self.refused(self.edit(stranger, comment_id, "Mine now.", tenant=self.other), 404, "not_found")
        self.refused(self.delete(stranger, comment_id, tenant=self.other), 404, "not_found")
        self.in_tenant()
        row = Comment.objects.get(pk=comment_id)
        self.assertIsNone(row.deleted_at)
        self.assertIn(PLANTED, row.body)

    def test_an_obligation_is_commented_on_under_its_library_read(self) -> None:
        on = library_build.instrument(key=f"inst-comments-{uuid.uuid4().hex[:8]}", regime="regime:securities")
        obligation = library_build.obligation(on, key=f"obl-comments-{uuid.uuid4().hex[:8]}", titles={"en": "Keep client assets apart"})
        self.written(self.add(self.anna, subject_type="obligation", subject_id=obligation.id))
        page = self.listing(self.erik, subject_type="obligation", subject_id=obligation.id).json()
        self.assertEqual([(item["subjectType"], item["subjectId"]) for item in page["items"]], [("obligation", str(obligation.id))])

    def test_a_page_of_twenty_costs_what_a_page_of_one_costs(self) -> None:
        """Pinned: the author and the mentions are fetched once per page, never per comment."""
        self.written(self.add(self.anna, "One.", mentions=[self.erik]))

        def cost() -> int:
            headers = self.headers(self.erik)
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(f"/api/v1/comments?subjectType=change_case&subjectId={self.case.id}", **headers)
            self.assertEqual(response.status_code, 200)
            return len(queries)

        one = cost()
        for n in range(24):
            self.written(self.add(self.erik if n % 2 else self.anna, f"Note {n}.", mentions=[self.anna, self.erik]))
        twenty = cost()
        self.assertEqual(twenty, one)
        # The request savepoint and the session with its roles, bank and person (10), then the
        # record, the page, its mentions, the count and the savepoint's release.
        self.assertEqual(twenty, 15)


class WritingAComment(CommentsTestCase):
    def test_the_comment_lands_on_its_record_with_one_mention_row_per_person_and_ids_only_in_the_audit(self) -> None:
        response = self.add(self.anna, f"@Erik the {PLANTED}?", mentions=[self.erik, self.erik])
        comment_id = self.written(response)
        created = response.json()
        self.assertEqual((created["subjectType"], created["subjectId"]), ("change_case", str(self.case.id)))
        self.assertEqual(created["mentions"], [{"id": str(self.erik.id), "name": self.erik.name}])
        self.assertEqual(created["undeliveredMentions"], [])
        self.assertEqual((created["canEdit"], created["canDelete"]), (True, True))

        self.in_tenant()
        row = Comment.objects.get(pk=comment_id)
        self.assertEqual((row.subject_type, row.subject_id, row.author_id, row.tenant_id), ("change_case", self.case.id, self.anna.id, self.tenant.id))
        self.assertEqual(list(CommentMention.objects.filter(comment=row).values_list("user_id", flat=True)), [self.erik.id])

        event = AuditEvent.objects.get(action="comment.added")
        self.assertEqual((event.subject_type, event.subject_id, event.subject_title), ("change_case", self.case.id, CHANGE_TITLE))
        self.assertEqual(event.after, {"commentId": comment_id, "mentionUserIds": [str(self.erik.id)]})
        self.assertEqual(event.actor_id, self.anna.id)
        self.assertTrue(OutboxEvent.objects.filter(audit_event=event).exists())
        self.assertNotIn(PLANTED, f"{event.summary} {event.after} {event.before}")

    def test_a_text_of_only_spaces_or_longer_than_the_cap_is_refused_and_writes_nothing(self) -> None:
        self.refused(self.add(self.anna, "   \n\t "), 422, "validation_error")
        with override_settings(COMMENT_MAX_CHARS=10):
            self.refused(self.add(self.anna, "x" * 11), 422, "comment_too_long")
            self.written(self.add(self.anna, "x" * 10))
        self.assertEqual(self.comments(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="comment.added").count(), 1)

    def test_a_mention_of_another_banks_member_is_refused_like_an_unknown_id_and_writes_nothing(self) -> None:
        stranger = factories.member_user(self.other, roles=("compliance_officer",))
        for person in (stranger.id, uuid.uuid4()):
            with self.subTest(person=person):
                self.refused(self.add(self.anna, mentions=[self.erik, person]), 422, "unknown_member")
        self.assertEqual(self.comments(), 0)
        self.in_tenant()
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action="comment.added").exists())


class MentionsNotify(CommentsTestCase):
    def told(self, person: User) -> list[Notification]:
        self.in_tenant()
        return list(Notification.objects.filter(user=person))

    def test_a_mentioned_member_is_told_once_with_the_records_title_and_the_author_never(self) -> None:
        self.written(self.add(self.anna, f"@Erik @Anna {PLANTED}", mentions=[self.erik, self.anna, self.erik]))
        (row,) = self.told(self.erik)
        self.assertEqual((row.kind, row.subject_type, row.subject_id, row.title), ("mention", "change_case", self.case.id, CHANGE_TITLE))
        self.assertEqual(self.told(self.anna), [])

    def test_the_people_not_reached_are_named_and_never_explained(self) -> None:
        limited = self.limited_member()
        leaver = factories.member(self.tenant, roles=("reader",))
        Membership.objects.filter(pk=leaver.pk).update(deactivated_at=timezone.now())
        muted = factories.member_user(self.tenant, roles=("reader",))
        Membership.objects.filter(tenant=self.tenant, user=muted).update(notification_prefs={"mentions": False})

        response = self.add(self.anna, mentions=[self.erik, limited, leaver.user, muted])
        self.written(response)
        undelivered = response.json()["undeliveredMentions"]
        self.assertEqual(
            sorted(undelivered, key=lambda person: person["id"]),
            sorted(({"id": str(p.id), "name": p.name} for p in (limited, leaver.user, muted)), key=lambda person: person["id"]),
        )
        self.assertEqual(len(self.told(self.erik)), 1)
        for person in (limited, leaver.user, muted):
            self.assertEqual(self.told(person), [])

    def test_an_account_that_is_not_active_is_stored_and_not_reached(self) -> None:
        person = factories.member_user(self.tenant, roles=("reader",))
        User.objects.filter(pk=person.pk).update(status=UserStatus.DEACTIVATED.value)
        response = self.add(self.anna, mentions=[person])
        self.written(response)
        self.assertEqual([p["id"] for p in response.json()["undeliveredMentions"]], [str(person.id)])

    def test_the_text_reaches_no_notification_outbox_payload_or_mail(self) -> None:
        self.written(self.add(self.anna, f"@Erik {PLANTED}", mentions=[self.erik]))
        self.in_tenant()
        titles = " ".join(Notification.objects.values_list("title", flat=True))
        payloads = " ".join(str(p) for p in OutboxEvent.objects.values_list("payload", flat=True))
        mails = " ".join(f"{m.subject} {m.error}" for m in EmailMessage.objects.all())
        self.assertNotIn(PLANTED, f"{titles} {payloads} {mails}")

    def test_a_failure_while_notifying_rolls_the_comment_back(self) -> None:
        with mock.patch("apps.collab.comments.notify", side_effect=RuntimeError("the mailer fell over")):
            response = self.add(self.anna, mentions=[self.erik])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.comments(), 0)
        self.in_tenant()
        self.assertFalse(CommentMention.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action="comment.added").exists())
        self.assertEqual(self.told(self.erik), [])


class EditingAComment(CommentsTestCase):
    def revisions(self, comment_id: str) -> list[str]:
        self.in_tenant()
        return list(CommentRevision.objects.filter(comment_id=comment_id).order_by("created_at", "id").values_list("body", flat=True))

    def test_two_edits_keep_the_two_texts_they_replaced_in_order(self) -> None:
        comment_id = self.written(self.add(self.anna, "First text.", mentions=[self.erik]))
        response = self.edit(self.anna, comment_id, "Second text.")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["body"], "Second text.")
        self.assertIsNotNone(response.json()["editedAt"])
        self.assertEqual(self.edit(self.anna, comment_id, "Third text.").status_code, 200)

        self.assertEqual(self.revisions(comment_id), ["First text.", "Second text."])
        self.in_tenant()
        self.assertEqual(Comment.objects.get(pk=comment_id).body, "Third text.")
        events = list(AuditEvent.objects.filter(action="comment.edited").order_by("created", "id"))
        revision_ids = [str(r) for r in CommentRevision.objects.filter(comment_id=comment_id).order_by("created_at", "id").values_list("id", flat=True)]
        self.assertEqual([e.after for e in events], [{"commentId": comment_id, "revisionId": r} for r in revision_ids])
        self.assertEqual({e.subject_title for e in events}, {CHANGE_TITLE})

    def test_an_edit_notifies_nobody_new_and_keeps_the_mentions(self) -> None:
        comment_id = self.written(self.add(self.anna, "Hello.", mentions=[self.erik]))
        extra = factories.member_user(self.tenant, roles=("reader",))
        response = self.edit(self.anna, comment_id, f"Hello @{extra.name}.")
        self.assertEqual(response.json()["mentions"], [{"id": str(self.erik.id), "name": self.erik.name}])
        self.in_tenant()
        self.assertEqual(Notification.objects.filter(user=self.erik).count(), 1)
        self.assertFalse(Notification.objects.filter(user=extra).exists())

    def test_only_the_author_may_edit(self) -> None:
        comment_id = self.written(self.add(self.anna, "Mine."))
        self.refused(self.edit(self.erik, comment_id, "Yours now."), 403, "not_author")
        self.assertEqual(self.revisions(comment_id), [])

    def test_after_the_window_or_once_deleted_the_edit_is_409_and_writes_nothing(self) -> None:
        comment_id = self.written(self.add(self.anna, "Mine."))
        with override_settings(COMMENT_EDIT_MINUTES=15):
            self.in_tenant()
            Comment.objects.filter(pk=comment_id).update(created_at=timezone.now() - datetime.timedelta(minutes=16))
            self.refused(self.edit(self.anna, comment_id, "Too late."), 409, "edit_window_closed")
            self.assertFalse(self.listing(self.anna).json()["items"][0]["canEdit"])
            self.assertTrue(self.listing(self.anna).json()["items"][0]["canDelete"])
        fresh = self.written(self.add(self.anna, "Fresh."))
        self.assertEqual(self.delete(self.anna, fresh).status_code, 204)
        self.refused(self.edit(self.anna, fresh, "Back from the dead."), 409, "edit_window_closed")
        self.assertEqual(self.revisions(comment_id) + self.revisions(fresh), [])
        self.assertFalse(AuditEvent.objects.filter(action="comment.edited").exists())

    def test_an_edit_of_only_spaces_or_over_the_cap_is_refused_and_keeps_nothing(self) -> None:
        comment_id = self.written(self.add(self.anna, "Mine."))
        self.refused(self.edit(self.anna, comment_id, "  "), 422, "validation_error")
        with override_settings(COMMENT_MAX_CHARS=10):
            self.refused(self.edit(self.anna, comment_id, "y" * 11), 422, "comment_too_long")
        self.assertEqual(self.revisions(comment_id), [])


class DeletingAComment(CommentsTestCase):
    def test_a_delete_is_soft_idempotent_and_the_authors_own(self) -> None:
        comment_id = self.written(self.add(self.anna, "Mine."))
        self.refused(self.delete(self.erik, comment_id), 403, "not_author")
        self.assertEqual(self.delete(self.anna, comment_id).status_code, 204)
        self.assertEqual(self.delete(self.anna, comment_id).status_code, 204)

        self.in_tenant()
        row = Comment.objects.get(pk=comment_id)
        self.assertIsNotNone(row.deleted_at)
        self.assertEqual(row.body, "Mine.", "the row is kept for the bank's export")
        (event,) = AuditEvent.objects.filter(action="comment.deleted")
        self.assertEqual(event.after, {"commentId": comment_id})
        self.assertEqual(event.subject_title, CHANGE_TITLE)

"""The collab tables (COL-01, COL-02; schema v0.3 `comment`, `notification`, `email_message`;
INPUT_DELTAS §1).

Five tenant tables and no logic: a comment on a record, the people it mentions, the text an
edit replaced, a person's notifications and the proof that a mail went out. These tests pin
what the rest of chunk 10 is allowed to rely on without checking again.

**Nobody outside the row's bank can be named on it.** Every person column (author, mention,
editor, recipient, the absent person a delegate is told on behalf of, the mail's addressee)
is a composite `(tenant_id, user_id)` foreign key to `membership`, and a mention or a
revision points at its comment through `(tenant_id, comment_id)`. A foreign-key check does
not pass through row-level security, so only the composite key makes a row naming another
bank's person, or another bank's comment, impossible (D-18).

**An edited comment keeps the text it replaced.** `comment_revision` refuses an update and a
delete in Python and in PostgreSQL, from the application role as well as the runner's own.

**Nothing the models print carries tenant text**, and `email_message` has no column that
could hold what was sent.
"""

from __future__ import annotations

import datetime
import uuid

from django.db import DEFAULT_DB_ALIAS, DatabaseError, IntegrityError, connections, transaction
from django.db.models import Model
from django.test import TestCase, TransactionTestCase

from apps.collab.models import (
    Comment,
    CommentMention,
    CommentRevision,
    EmailMessage,
    EmailStatus,
    Notification,
    NotificationKind,
)
from apps.identity.models import User
from apps.shared import factories, tenancy
from apps.shared.audit import AppendOnlyRefused
from apps.shared.kinds import TIER_ONE_KINDS
from apps.shared.models import Tenant

# Tenant text a test writes and then looks for where it must not be. Nothing in it is an id.
BODY = "Can you check the custody angle before Friday?"
REPLACED = "Can you check the custody angle?"
TITLE = "Custody of client assets"
# A fixed tenant-local day, never today (CLAUDE.md §8.3): the mail key is addressed by it.
SENT_ON = datetime.date(2026, 9, 14)
COLLAB_TABLES = ("comment", "comment_mention", "comment_revision", "notification", "email_message")
COLLAB_MODELS: tuple[type[Model], ...] = (Comment, CommentMention, CommentRevision, Notification, EmailMessage)


def comment(tenant: Tenant, author: User, *, body: str = BODY) -> Comment:
    """A comment on a record of `tenant`, written with its tenant activated: FORCE ROW LEVEL
    SECURITY applies to the test runner's own connection too."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return Comment.objects.create(
            tenant=tenant, subject_type="change_case", subject_id=uuid.uuid4(), author=author, body=body
        )


def notification(tenant: Tenant, user: User, *, on_behalf_of: User | None = None) -> Notification:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return Notification.objects.create(
            tenant=tenant,
            user=user,
            kind=NotificationKind.MENTION.value,
            subject_type="change_case",
            subject_id=uuid.uuid4(),
            title=TITLE,
            on_behalf_of=on_behalf_of,
        )


def email(tenant: Tenant, user: User | None, *, subject_id: uuid.UUID | None = None, sent_on: datetime.date = SENT_ON) -> EmailMessage:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return EmailMessage.objects.create(
            tenant=tenant,
            user=user,
            to_email="person@example-bank.test",
            template="action_due",
            subject="An action is due",
            subject_type="action" if subject_id else None,
            subject_id=subject_id,
            sent_on=sent_on,
        )


class CollabZoneTestCase(TestCase):
    """Two banks, a member of each, and a person who belongs to both only as a user row."""

    def setUp(self) -> None:
        self.tenant_a = factories.tenant(slug=f"collab-a-{uuid.uuid4().hex[:8]}")
        self.tenant_b = factories.tenant(slug=f"collab-b-{uuid.uuid4().hex[:8]}")
        self.anna = factories.member_user(self.tenant_a)
        self.erik = factories.member_user(self.tenant_a)
        self.outsider = factories.member_user(self.tenant_b)


class NobodyOutsideTheBankIsNamed(CollabZoneTestCase):
    def test_a_comment_by_someone_who_is_not_a_member_is_refused(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            Comment.objects.create(
                tenant=self.tenant_a, subject_type="change_case", subject_id=uuid.uuid4(), author=self.outsider, body=BODY
            )

    def test_a_mention_of_a_member_of_another_bank_is_refused(self) -> None:
        row = comment(self.tenant_a, self.anna)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CommentMention.objects.create(tenant=self.tenant_a, comment=row, user=self.erik)
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CommentMention.objects.create(tenant=self.tenant_a, comment=row, user=self.outsider)

    def test_a_mention_or_revision_cannot_point_at_another_banks_comment(self) -> None:
        """A single-column key would accept this: the check that the comment exists does
        not pass through row-level security, so it finds tenant B's row."""
        theirs = comment(self.tenant_b, self.outsider)
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CommentMention.objects.create(tenant=self.tenant_a, comment_id=theirs.id, user=self.erik)
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CommentRevision.objects.create(tenant=self.tenant_a, comment_id=theirs.id, body=REPLACED, edited_by=self.anna)

    def test_a_person_is_mentioned_once_per_comment(self) -> None:
        row = comment(self.tenant_a, self.anna)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CommentMention.objects.create(tenant=self.tenant_a, comment=row, user=self.erik)
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CommentMention.objects.create(tenant=self.tenant_a, comment=row, user=self.erik)

    def test_a_revision_by_someone_who_is_not_a_member_is_refused(self) -> None:
        row = comment(self.tenant_a, self.anna)
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CommentRevision.objects.create(tenant=self.tenant_a, comment=row, body=REPLACED, edited_by=self.outsider)

    def test_a_notification_reaches_members_only_on_their_own_behalf_or_a_members(self) -> None:
        notification(self.tenant_a, self.erik, on_behalf_of=self.anna)
        with self.assertRaises(IntegrityError):
            notification(self.tenant_a, self.outsider)
        with self.assertRaises(IntegrityError):
            notification(self.tenant_a, self.erik, on_behalf_of=self.outsider)

    def test_a_mail_names_a_member_or_nobody(self) -> None:
        email(self.tenant_a, self.anna)
        email(self.tenant_a, None, subject_id=uuid.uuid4())
        with self.assertRaises(IntegrityError):
            email(self.tenant_a, self.outsider, subject_id=uuid.uuid4())


class AnEditKeepsTheTextItReplaced(CollabZoneTestCase):
    def revision(self) -> CommentRevision:
        row = comment(self.tenant_a, self.anna)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            return CommentRevision.objects.create(tenant=self.tenant_a, comment=row, body=REPLACED, edited_by=self.anna)

    def test_python_refuses_to_rewrite_or_delete_a_revision(self) -> None:
        revision = self.revision()
        revision.body = "rewritten"
        with self.assertRaises(AppendOnlyRefused):
            revision.save()
        with self.assertRaises(AppendOnlyRefused):
            revision.delete()
        with self.assertRaises(AppendOnlyRefused):
            CommentRevision.objects.filter(id=revision.id).update(body="rewritten")

    def test_the_database_trigger_refuses_it_too(self) -> None:
        revision = self.revision()
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            for statement in ("UPDATE comment_revision SET body = 'rewritten' WHERE id = %s", "DELETE FROM comment_revision WHERE id = %s"):
                with self.subTest(statement=statement), self.assertRaises(DatabaseError) as caught, transaction.atomic():
                    tenancy.activate(self.tenant_a.id)
                    cursor.execute(statement, [str(revision.id)])
                self.assertIn("append-only", str(caught.exception))

    def test_the_comment_itself_is_edited_in_place_and_deleted_softly(self) -> None:
        """Ruling 10: the row the API returns is edited, and a delete stamps `deleted_at`."""
        row = comment(self.tenant_a, self.anna)
        self.assertIsNone(row.edited_at)
        self.assertIsNone(row.deleted_at)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            Comment.objects.filter(id=row.id).update(body="edited", edited_at=row.created_at)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            self.assertEqual(Comment.objects.get(id=row.id).body, "edited")


class NothingPrintedCarriesTenantText(CollabZoneTestCase):
    def test_str_and_repr_name_ids_only(self) -> None:
        row = comment(self.tenant_a, self.anna)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            revision = CommentRevision.objects.create(tenant=self.tenant_a, comment=row, body=REPLACED, edited_by=self.anna)
            mention = CommentMention.objects.create(tenant=self.tenant_a, comment=row, user=self.erik)
        rows = (row, revision, mention, notification(self.tenant_a, self.erik), email(self.tenant_a, self.anna))
        for shown_row in rows:
            for shown in (str(shown_row), repr(shown_row)):
                with self.subTest(model=type(shown_row).__name__, shown=shown):
                    for text in (BODY, REPLACED, TITLE, "custody", "person@example-bank.test", "An action is due"):
                        self.assertNotIn(text, shown)
            self.assertEqual(str(shown_row), str(shown_row.id))

    def test_email_message_has_no_column_for_what_was_sent(self) -> None:
        """The proof of a send is the template key and the subject, never the text: the
        table's own column list is read, so a later `body` or `html` column fails here."""
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'email_message'")
            columns = {name for (name,) in cursor.fetchall()}
        self.assertIn("template", columns)
        self.assertEqual(columns & {"body", "text", "html", "content", "body_text", "body_html"}, set())


class OneMailPerPersonPerEventPerDay(CollabZoneTestCase):
    def test_a_retried_worker_cannot_send_the_same_mail_twice_in_a_day(self) -> None:
        action = uuid.uuid4()
        email(self.tenant_a, self.anna, subject_id=action)
        with self.assertRaises(IntegrityError):
            email(self.tenant_a, self.anna, subject_id=action)
        email(self.tenant_a, self.anna, subject_id=action, sent_on=SENT_ON + datetime.timedelta(days=1))
        email(self.tenant_a, self.erik, subject_id=action)

    def test_a_mail_about_no_record_is_still_once_a_day(self) -> None:
        """The digest names no subject; nulls count as equal, or a retry would send twice."""
        email(self.tenant_a, self.anna)
        with self.assertRaises(IntegrityError):
            email(self.tenant_a, self.anna)

    def test_a_mail_starts_queued(self) -> None:
        self.assertEqual(email(self.tenant_a, self.anna).status, EmailStatus.QUEUED.value)


class TheInboxReadsTheIndexItNeeds(TestCase):
    def test_the_unread_index_is_partial_and_the_comment_index_leads_with_the_subject(self) -> None:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE indexname IN ('notification_inbox_idx', 'comment_subject_idx')"
            )
            found = dict(cursor.fetchall())
        self.assertIn("WHERE (read_at IS NULL)", found["notification_inbox_idx"])
        self.assertIn("(tenant_id, subject_type, subject_id, created_at)", found["comment_subject_idx"])

    def test_both_kinds_are_declared_and_the_ones_nobody_here_produces_name_their_chunk(self) -> None:
        self.assertIn("NotificationKind", TIER_ONE_KINDS)
        self.assertIn("EmailStatus", TIER_ONE_KINDS)
        reason = TIER_ONE_KINDS["NotificationKind"][1]
        for kind in NotificationKind:
            self.assertIn(kind.value, reason)
        self.assertIn("chunk 13", reason)


class CollabRowsUnderTheApplicationRole(TransactionTestCase):
    """The same rules for `cw_app`, the role the application runs as: it owns nothing and
    cannot bypass row-level security (ADR 0022). Committed rows, visible across two
    connections, so a `TransactionTestCase`."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        self.tenant_a = factories.tenant(slug=f"collab-app-a-{uuid.uuid4().hex[:8]}")
        self.tenant_b = factories.tenant(slug=f"collab-app-b-{uuid.uuid4().hex[:8]}")
        self.anna = factories.member_user(self.tenant_a)
        self.erik = factories.member_user(self.tenant_a)
        self.outsider = factories.member_user(self.tenant_b)
        self.comment = comment(self.tenant_a, self.anna)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            CommentMention.objects.create(tenant=self.tenant_a, comment=self.comment, user=self.erik)
            self.revision = CommentRevision.objects.create(
                tenant=self.tenant_a, comment=self.comment, body=REPLACED, edited_by=self.anna
            )
        notification(self.tenant_a, self.erik)
        email(self.tenant_a, self.anna)

    def _counts(self, tenant: Tenant) -> dict[str, int]:
        with transaction.atomic(using="app"):
            tenancy.activate(tenant.id, using="app")
            return {model._meta.db_table: model._default_manager.using("app").count() for model in COLLAB_MODELS}

    def test_another_bank_reads_none_of_it(self) -> None:
        self.assertEqual(self._counts(self.tenant_b), dict.fromkeys(COLLAB_TABLES, 0))
        self.assertEqual(self._counts(self.tenant_a), dict.fromkeys(COLLAB_TABLES, 1))

    def test_another_bank_cannot_write_into_this_one(self) -> None:
        with self.assertRaises(DatabaseError), transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            Comment.objects.using("app").create(
                tenant=self.tenant_a, subject_type="change_case", subject_id=uuid.uuid4(), author=self.anna, body=BODY
            )

    def test_the_application_role_cannot_name_another_banks_person(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            CommentMention.objects.using("app").create(tenant=self.tenant_a, comment=self.comment, user=self.outsider)

    def test_the_application_role_may_add_a_revision_and_never_change_or_remove_one(self) -> None:
        with connections["app"].cursor() as cursor:
            cursor.execute("SELECT current_user")
            self.assertEqual(cursor.fetchone(), ("cw_app",))
            for statement in ("UPDATE comment_revision SET body = 'rewritten' WHERE id = %s", "DELETE FROM comment_revision WHERE id = %s"):
                with self.subTest(statement=statement), self.assertRaises(DatabaseError) as caught, transaction.atomic(using="app"):
                    tenancy.activate(self.tenant_a.id, using="app")
                    cursor.execute(statement, [str(self.revision.id)])
                self.assertIn("append-only", str(caught.exception))
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            self.assertEqual(CommentRevision.objects.using("app").get(id=self.revision.id).body, REPLACED)

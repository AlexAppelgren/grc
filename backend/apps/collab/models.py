"""Models of the collab app (COL-01, COL-02; schema v0.3 `comment`, `notification`,
`email_message`; INPUT_DELTAS §1).

Five tenant tables, all `TenantModel` under enabled and forced row-level security: a
comment on a record, the people it mentions, the text an edit replaced, a person's
notifications and the proof that a mail went out. All of it is one bank's own.

Three rules are structural here rather than remembered:

- **Nobody outside the row's bank can be named on it.** Every person column is also a
  composite `(tenant_id, user_id)` foreign key to `membership`, and a mention or a revision
  points at its comment through `(tenant_id, comment_id)`. Those keys are written in collab
  0001 in SQL, because Django declares a foreign key on one column only; the single-column
  keys below stay for the ORM's joins. A foreign-key check does not pass through row-level
  security, so only the composite key refuses another bank's person or comment (D-18).
- **An edited comment keeps the text it replaced.** `comment_revision` is an
  `AppendOnlyModel` with the trigger of the same name (CHUNK10_TASKS ruling 10).
- **Nothing here prints tenant text.** Every `__str__` returns the row's id, because a
  model's repr reaches logs, shells and error pages (playbook 4.7).

`subject_type` is a plain string, as on `tagging`: which kinds a comment or a notification
may name, and who may read each, is the subject registry's (`collab/subjects.py`, ruling 3),
not a column constraint that a later chunk would have to migrate.

No logic lives here. `notify()` in `collab/logic.py` is the only writer of a notification
(ruling 1).
"""

from __future__ import annotations

import enum

from django.db import models

from apps.shared.audit import AppendOnlyModel
from apps.shared.fields import CIEmailField
from apps.shared.tenancy import TenantModel


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


class NotificationKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what a notification is about. The inbox, the
    preferences and the mail composer branch on it; its label is the client's catalog."""

    ASSIGNED = "assigned"
    MENTION = "mention"
    SIGNOFF_REQUESTED = "signoff_requested"
    APPROVAL_REQUESTED = "approval_requested"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    ESCALATION = "escalation"
    PROPOSAL_WAITING = "proposal_waiting"
    SAVED_SEARCH_HIT = "saved_search_hit"
    PARTICIPANT_ADDED = "participant_added"
    INVOLVED_ITEM_CHANGED = "involved_item_changed"
    REVIEW_DUE = "review_due"


class EmailStatus(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): where one mail is in its delivery. The delivery
    task and the provider's callback branch on it."""

    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    FAILED = "failed"


class Comment(TenantModel):
    """A comment on one record of one bank (COL-01), shared with everyone in that bank
    (D-22, D-60).

    `body` is tenant content. It never reaches a log line, a Sentry event, an audit before
    or after value, an outbox payload, a webhook, a notification title or a mail (CLAUDE.md
    §5, CHUNK10_TASKS rule 13): anything that has to say which comment carries its id.

    Edited in place: `edited_at` is stamped and the text it replaced goes to
    `CommentRevision` in the same transaction. Deleted softly: `deleted_at` is stamped, the
    row stays for the tenant export, and the API stops returning its body.
    """

    subject_type = models.CharField(max_length=64)
    subject_id = models.UUIDField()
    author = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "comment"
        # A record's thread reads oldest first, with the id as a stable tiebreak.
        ordering = ["created_at", "id"]
        # `(tenant, id)` is what the mention and the revision point at, so neither can name
        # another bank's comment.
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="comment_tenant_id_unique")]
        indexes = [
            models.Index(fields=["tenant", "subject_type", "subject_id", "created_at"], name="comment_subject_idx")
        ]

    def __str__(self) -> str:
        return str(self.id)


class CommentMention(TenantModel):
    """One person a comment mentions (COL-01). A row rather than the designed `uuid[]`,
    because an array cannot carry a composite foreign key (INPUT_DELTAS §1)."""

    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "comment_mention"
        ordering = ["comment", "user"]
        constraints = [models.UniqueConstraint(fields=["comment", "user"], name="comment_mention_unique")]

    def __str__(self) -> str:
        return str(self.id)


class CommentRevision(AppendOnlyModel, TenantModel):
    """The text one edit of a comment replaced (CHUNK10_TASKS ruling 10), written before the
    new text lands, in the same transaction.

    `body` is tenant content, exactly as on `Comment`: it never reaches a log line, a Sentry
    event, an audit value, an outbox payload, a webhook, a notification or a mail. No route
    returns a revision; they are the bank's own history, carried by its export.
    """

    comment = models.ForeignKey(Comment, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    edited_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comment_revision"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return str(self.id)


class Notification(TenantModel):
    """One thing one person is told about one record (COL-02).

    `title` is a record title and never tenant text such as a comment or a note (rule 13).
    `on_behalf_of` names the absent person when a delegate is told in their place (TEN-04);
    it is null for everyone else. `emailed_at` is stamped by the task that mailed it.
    """

    user = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=32, choices=_choices(NotificationKind))
    subject_type = models.CharField(max_length=64)
    subject_id = models.UUIDField()
    title = models.TextField()
    on_behalf_of = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification"
        # Newest first, with the id as a stable tiebreak between rows of one transaction.
        ordering = ["-created_at", "-id"]
        # The bell and the unread inbox read only unread rows.
        indexes = [
            models.Index(
                fields=["tenant", "user", "-created_at"],
                condition=models.Q(read_at__isnull=True),
                name="notification_inbox_idx",
            )
        ]

    def __str__(self) -> str:
        return str(self.id)


class EmailMessage(TenantModel):
    """The proof that one mail went to one person (schema v0.3 §21).

    No column holds what was sent: the proof is the template key and the record, never the
    text. `sent_on` is the bank's local date, and the unique key over it — nulls counting as
    equal, so the digest, which names no record, is covered too — is what stops a retried
    worker sending the same mail twice in a day. `user` is null for an address that is not
    yet a member (an invitation).
    """

    user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    to_email = CIEmailField(max_length=254)
    template = models.CharField(max_length=64)
    subject = models.TextField()
    subject_type = models.CharField(max_length=64, null=True, blank=True)
    subject_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=_choices(EmailStatus), default=EmailStatus.QUEUED.value)
    provider_message_id = models.CharField(max_length=255, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_on = models.DateField()
    error = models.TextField(blank=True)

    class Meta:
        db_table = "email_message"
        ordering = ["-queued_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "template", "subject_type", "subject_id", "sent_on"],
                name="email_message_once_a_day",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return str(self.id)

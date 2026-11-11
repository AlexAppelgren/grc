"""Models of the collab app (COL-01, COL-02, COL-04; INPUT_DELTAS §1): five tenant tables
under forced row-level security, all one bank's own.

- Nobody outside the row's bank can be named on it: each person column is also a composite
  `(tenant_id, user_id)` key to `membership`, and mentions and revisions point at their
  comment through `(tenant_id, comment_id)`, written in SQL in collab 0001. A foreign-key
  check bypasses row-level security, so only the composite key refuses another bank (D-18).
- An edited comment keeps the text it replaced: `comment_revision` is append-only by trigger.
- Nothing here prints tenant text: every `__str__` returns the id (playbook 4.7).

`subject_type` is a plain string; which kinds exist and who reads them is the subject
registry's (`collab/subjects.py`). `notify()` is the only writer of a notification.
"""

from __future__ import annotations

import enum
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.shared.audit import AppendOnlyModel
from apps.shared.fields import CIEmailField
from apps.shared.tenancy import TenantModel
from apps.shared.kinds import choices


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

    `body` is tenant content: never in a log, Sentry, audit value, outbox payload, webhook,
    notification title or mail (CHUNK10_TASKS rule 13); refer to a comment by its id. An edit
    stamps `edited_at` and moves the old text to `CommentRevision` in the same transaction; a
    delete stamps `deleted_at` and the API stops returning the body.
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
    """The text one edit of a comment replaced, written in the same transaction. `body` is
    tenant content, as on `Comment`. No route returns a revision; the export carries them.
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
    kind = models.CharField(max_length=32, choices=choices(NotificationKind))
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
    """The proof that one mail went to one person. No column holds what was sent. The unique
    key over the bank-local `sent_on` (nulls equal, so the digest is covered) stops a retried
    worker sending the same mail twice in a day. `user` is null for an invitation.
    """

    user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    to_email = CIEmailField(max_length=254)
    template = models.CharField(max_length=64)
    subject = models.TextField()
    subject_type = models.CharField(max_length=64, null=True, blank=True)
    subject_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=choices(EmailStatus), default=EmailStatus.QUEUED.value)
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


class Participant(TenantModel):
    """A person or a team named on one register entry or one case of one bank (COL-04,
    D-18), so it reaches their My work and notifications. It grants nothing.

    Exactly one subject and one participant (`num_nonnulls` CHECKs in collab 0002); every
    reference is a composite `(tenant_id, …)` key, so the database refuses another bank's
    entry, case, team or person. One live row per pair. Removal stamps `removed_at` and
    `removed_by`, so the case file (CAS-07) and history (REG-04) keep who took part."""

    tenant_obligation = models.ForeignKey(
        "register.TenantObligation", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    case = models.ForeignKey("cases.ChangeCase", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    team = models.ForeignKey("taxonomy.Team", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    added_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    added_at = models.DateTimeField(default=timezone.now)
    removed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "participant"
        # A record's list reads in the order people were added, with the id as a tiebreak.
        ordering = ["added_at", "id"]
        constraints = [
            # One live row per subject and participant. The two unused columns are null on
            # every row, so nulls count as equal here.
            models.UniqueConstraint(
                fields=["tenant_obligation", "case", "user", "team"],
                condition=models.Q(removed_at__isnull=True),
                nulls_distinct=False,
                name="participant_live_unique",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", field], condition=models.Q(removed_at__isnull=True), name=f"participant_live_{short}_idx")
            for field, short in (("user", "user"), ("team", "team"), ("case", "case"), ("tenant_obligation", "entry"))
        ]

    def __str__(self) -> str:
        return str(self.id)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        raise ValidationError("A participant is removed by stamping removed_at, never deleted.", code="remove_not_delete")

"""The shared tables: `tenant`, `audit_event`, `outbox_event`, `outbox_cursor`
(playbook 14, AUD-01).

Every model declares `Meta.ordering` on a meaningful column because `.first()` on an
unordered queryset with uuid keys is a coin flip on Postgres (playbook 4.5). JSON columns
name their Pydantic schema inline; the compliance lint checks the comment is there.

`audit_event` and `outbox_event` are mixed tables: a library row has `tenant_id` NULL and
is visible to everyone, a tenant row only to its tenant. The migration writes that policy.
`outbox_cursor` belongs to neither zone: it is the worker's own bookkeeping.
"""

from __future__ import annotations

import enum
import uuid

from django.db import models

from apps.shared.audit import ACTOR_TYPE_CHOICES, AppendOnlyModel


class TenantStatus(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py)."""

    ACTIVE = "active"
    DEACTIVATED = "deactivated"


TENANT_STATUS_CHOICES = [(kind.value, kind.value) for kind in TenantStatus]


class Tenant(models.Model):
    """One company (TEN-01). Explicit columns instead of a settings blob (chunk 1 brief):
    the default language and the ordered content languages are foreign keys to language
    rows, and `status` is a kind."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    timezone = models.CharField(max_length=64, default="Europe/Stockholm")
    status = models.CharField(max_length=16, choices=TENANT_STATUS_CHOICES, default=TenantStatus.ACTIVE.value)
    default_language = models.ForeignKey(
        "library.Language", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    content_languages = models.ManyToManyField(
        "library.Language", through="shared.TenantContentLanguage", related_name="+", blank=True
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant"
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.slug


class TenantContentLanguage(models.Model):
    """The ordered content languages of one tenant (TEN-01). A tenant table: RLS is forced
    by shared 0002."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="content_language_links")
    language = models.ForeignKey("library.Language", on_delete=models.PROTECT, related_name="+")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "tenant_content_language"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "language"], name="tenant_content_language_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.language_id}"


class AuditEvent(AppendOnlyModel):
    """AUD-01: actor, action, subject with its title at the time, summary, before, after."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events"
    )
    actor_type = models.CharField(max_length=16, choices=ACTOR_TYPE_CHOICES)
    actor_id = models.UUIDField(null=True, blank=True)
    actor_label = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=100)
    subject_type = models.CharField(max_length=64)
    subject_id = models.UUIDField(null=True, blank=True)
    subject_title = models.CharField(max_length=500, blank=True)
    summary = models.CharField(max_length=1000, blank=True)
    before = models.JSONField(default=dict, blank=True)  # schema: AuditSnapshot
    after = models.JSONField(default=dict, blank=True)  # schema: AuditSnapshot
    step_up_assertion_id = models.UUIDField(null=True, blank=True)  # ID-06, INPUT_DELTAS §6
    request_id = models.CharField(max_length=128, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_event"
        ordering = ["created", "id"]
        indexes = [
            models.Index(fields=["tenant", "created"], name="audit_event_tenant_created"),
            models.Index(fields=["subject_type", "subject_id"], name="audit_event_subject"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.subject_type}:{self.subject_id}"


class OutboxEvent(models.Model):
    """The transactional outbox (INT-01, Solution_Design). Written by record() beside its
    audit event; delivered by the worker, which is the one writer of the delivery columns.
    The database trigger lets `published_at`, `attempts` and `last_error` change and
    refuses everything else, so the payload is as append-only as the audit row."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.PROTECT, related_name="outbox_events"
    )
    audit_event = models.ForeignKey(
        AuditEvent, on_delete=models.PROTECT, related_name="outbox_events"
    )
    topic = models.CharField(max_length=100)
    payload = models.JSONField(default=dict, blank=True)  # schema: OutboxPayload
    created = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "outbox_event"
        ordering = ["created", "id"]
        indexes = [
            models.Index(fields=["published_at", "created"], name="outbox_event_pending"),
            # The cursor scans one zone at a time, oldest first, and only ever wants rows
            # that are still pending (apps/shared/outbox.py). Partial, so it holds the
            # backlog and not the whole delivered history, and leading on tenant_id so one
            # zone's scan reads its own rows and steps over everybody else's.
            models.Index(
                fields=["tenant", "created", "id"],
                name="outbox_event_zone_pending",
                condition=models.Q(published_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.topic} ({'sent' if self.published_at else 'pending'})"


class OutboxCursor(models.Model):
    """The one ordered cursor over `outbox_event` (chunk 5 ruling 9). One row: the moment
    the row at the front of the queue may be tried again, the lock two workers take turns
    on, and where the last delivered event was (`apps/shared/outbox.py`). No tenant column
    and no row-level security: it holds a position and a clock, never tenant content, and
    the events it points at carry their own zone.

    `last_created` and `last_id` are a debugging aid and nothing else: they say where the
    last batch got to, and no query reads them to decide what to deliver. What is pending
    is `published_at IS NULL` with attempts left, because two writers commit in an order of
    their own and a positional scan would step over a row that committed late. Moving them
    or clearing them changes no delivery.

    `retry_not_before` is one clock for every zone, not one per zone: a library row waiting
    out its backoff holds back the tenants' rows behind it too."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    last_created = models.DateTimeField(null=True, blank=True)
    last_id = models.UUIDField(null=True, blank=True)
    retry_not_before = models.DateTimeField(null=True, blank=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "outbox_cursor"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} at {self.last_created or 'the beginning'}"

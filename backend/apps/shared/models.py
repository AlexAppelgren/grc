"""The shared tables: `tenant`, `audit_event`, `outbox_event` (playbook 14, AUD-01).

Every model declares `Meta.ordering` on a meaningful column because `.first()` on an
unordered queryset with uuid keys is a coin flip on Postgres (playbook 4.5). JSON columns
name their Pydantic schema inline; the compliance lint checks the comment is there.

`audit_event` and `outbox_event` are mixed tables: a library row has `tenant_id` NULL and
is visible to everyone, a tenant row only to its tenant. The migration writes that policy.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.shared.audit import ACTOR_TYPE_CHOICES, AppendOnlyModel


class Tenant(models.Model):
    """One company. Minimal in Phase 0; TEN-01 adds profile, languages and onboarding."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    timezone = models.CharField(max_length=64, default="Europe/Stockholm")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant"
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.slug


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
        ]

    def __str__(self) -> str:
        return f"{self.topic} ({'sent' if self.published_at else 'pending'})"

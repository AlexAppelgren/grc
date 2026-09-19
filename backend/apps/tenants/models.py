"""Models of the tenants app. Chunk 1 adds `SupportAccess` (ID-05, TEN-06): every time
platform staff act inside a tenant, a row the tenant can see. The full grant workflow
(time-boxed reads) is chunk 8; chunk 1 writes one-shot rows for the last-admin recovery
(ID-S13). Legal entities, products and teams follow in chunk 8; `SecurityPolicy` is R2 and
deliberately not created here."""

from __future__ import annotations

import enum

from django.db import models

from apps.shared.tenancy import TenantModel


class SupportAccessLevel(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py)."""

    READ = "read"
    WRITE = "write"


class SupportAccess(TenantModel):
    platform_user = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="support_accesses")
    reason = models.TextField()
    ticket_ref = models.CharField(max_length=100, blank=True)
    access_level = models.CharField(
        max_length=8,
        choices=[(kind.value, kind.value) for kind in SupportAccessLevel],
        default=SupportAccessLevel.READ.value,
    )
    approved_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "support_access"
        ordering = ["started_at", "id"]

    def __str__(self) -> str:
        return f"{self.platform_user_id}@{self.tenant_id}"

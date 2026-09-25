"""Models of the reports app (REP-02, CAS-07; schema v0.3 `export_job`, INPUT_DELTAS §18).

One tenant table: an export job, under enabled and forced row-level security. A job is not
a ledger — its row moves from `queued` to `succeeded` or `failed` and records its first
download — so it is a plain `TenantModel`. The file itself never lives in the database: the
worker writes it through the storage seam (apps/shared/storage.py) under a key built from
the tenant id and the job id, and the download streams it back through a permission-checked,
audited route (playbook 4.6, D-11).

`ImportJob` is chunk 12's (REP-03, R3) and deliberately not here.
"""

from __future__ import annotations

import enum

from django.db import models

from apps.shared.tenancy import TenantModel


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


class JobStatus(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): a background job's lifecycle. The status
    endpoint, the download and the runner's idempotency all branch on it."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExportKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what an export contains. The runner looks the
    kind up in the exporter registry (apps/reports/exporters), so a kind is code that builds
    a file and never a row an admin adds (INPUT_DELTAS §18)."""

    CASE_FILE = "case_file"
    CASES = "cases"
    COMMITTEE_PACK = "committee_pack"
    INVENTORY = "inventory"
    CHANGES = "changes"
    AUDIT_LOG = "audit_log"
    CONFIGURATION = "configuration"
    TENANT_EXPORT = "tenant_export"


# The file formats of the designed contract (schema v0.3 `export_job.format`). Which of them
# a kind offers is its exporter's to say; this is the outer set the column accepts.
EXPORT_FORMATS = ("pdf", "txt", "json", "xlsx", "csv")


class ExportJob(TenantModel):
    """One export a person asked for, and the file the worker produced for it (REP-02).

    `storage_key`, `content_hash`, `completed_at` and `expires_at` are set together when the
    job succeeds, and never before — the constraint below makes a `succeeded` job without a
    file impossible, so a download can trust the status. `downloaded_at` is the first
    download and never moves again: the tenant exit refuses an export nobody downloaded.
    """

    kind = models.CharField(max_length=32, choices=_choices(ExportKind))
    # What the export is about when the kind is about one record: the case for a case file.
    subject_id = models.UUIDField(null=True, blank=True)
    format = models.CharField(max_length=8, choices=[(value, value) for value in EXPORT_FORMATS])
    filters = models.JSONField(default=dict, blank=True)  # schema: ExportFilters
    status = models.CharField(max_length=16, choices=_choices(JobStatus), default=JobStatus.QUEUED.value)
    storage_key = models.CharField(max_length=255, null=True, blank=True)
    # The SHA-256 of the produced file, hex encoded.
    content_hash = models.CharField(max_length=64, null=True, blank=True)
    requested_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    # User-facing text of a builder's refusal; empty unless the job failed.
    error = models.TextField(blank=True)

    class Meta:
        db_table = "export_job"
        # Newest first with the row id as a stable tiebreak (playbook 4.1).
        ordering = ["-created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=JobStatus.SUCCEEDED.value)
                    | models.Q(
                        storage_key__isnull=False,
                        content_hash__isnull=False,
                        completed_at__isnull=False,
                        expires_at__isnull=False,
                    )
                ),
                name="export_job_succeeded_has_a_file",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "-created_at"], name="export_job_tenant_newest_idx")]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.kind}:{self.status}"

    @property
    def audit_title(self) -> str:
        """What the audit log calls a job: its kind and format, never anything from the file."""
        return f"{self.kind} export ({self.format})"

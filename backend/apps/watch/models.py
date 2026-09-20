"""Models of the watch app (WAT-01 to WAT-04, WAT-07, AGT-01; schema v0.3 section 4;
INPUT_DELTAS §1, §5).

Seven library tables, all `LibraryModel`: the source registry and its coverage log, one
`regulatory_change` per reform with its timeline, its source pages, its classification
and its obligation links. None of them carries a tenant column — a bank's triage, its
"So what?" and its decision live on `change_case`, which the cases app owns — and none of
them is written outside `watch_write()` (apps/watch/write.py, the chunk 5 plan's ruling H).

What the designed schema has differently (INPUT_DELTAS §1, recorded there):

- `change_type`, `source_kind` and `urgency` are library vocabulary rows, not enums, so
  an admin adds one without a deploy. `check_status`, `change_status`, `source_check_kind`
  and `check_frequency` stay kinds in code: the rules branch on them.
- `regulatory_change.flags` is not a `text[]`. A flag and a scope term are both rows of
  `change_term`, each with the agent's `confidence` and a `suggested` marker until a
  library editor confirms it (WAT-03). `change_document.risk_flags` stays the designed
  array: its values are the screen's own findings (apps/agents/screen.py), not a list an
  admin curates.
- `source_check` gains `kind`, `subject_type` and `subject_id`, which the library
  re-check writes when it re-checks one record against its source (AGT-01, item 3).
- `source.owner_tenant` is WAT-06's tenant-private source, unused in R1 and left NULL;
  the column exists now so the row-level shape is final (INPUT_DELTAS §5).
"""

from __future__ import annotations

import enum

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from apps.library.models import DatePrecision, SubjectType
from apps.proposals.models import OriginType
from apps.shared.tenancy import LibraryModel


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


def _precision() -> models.CharField:
    return models.CharField(max_length=8, choices=_choices(DatePrecision), default=DatePrecision.DAY.value)


# ---------------------------------------------------------------------------------------
# Kinds (tier one, apps/shared/kinds.py)
# ---------------------------------------------------------------------------------------
class CheckStatus(enum.StrEnum):
    """WAT-01: how a source check ended. The coverage report and the stale rule branch."""

    OK = "ok"
    FAILED = "failed"


class SourceCheckKind(enum.StrEnum):
    """What a check was for: the sweep for new documents, or the re-check of one library
    record against the source it came from (AGT-01, Alex's item 3). A re-check names its
    subject; a sweep names none."""

    SWEEP = "sweep"
    RECHECK = "recheck"


class CheckFrequency(enum.StrEnum):
    """WAT-01: how often a source is checked. The scheduler and the stale rule branch on
    it; it is the designed `check_frequency` CHECK, which has no admin behind it."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ChangeStatus(enum.StrEnum):
    """WAT-02: a reform's lifecycle stage in the library."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


# ---------------------------------------------------------------------------------------
# WAT-01: the source registry and the coverage log
# ---------------------------------------------------------------------------------------
class Source(LibraryModel):
    """A place the agents check (schema v0.3 `source`). `active` false is a source that is
    registered but never checked automatically — how a standards body is seeded until its
    terms are cleared (WAT-07, D-45)."""

    name = models.CharField(max_length=200, unique=True)
    url = models.URLField(max_length=2000, blank=True)
    kind = models.ForeignKey("taxonomy.SourceKind", on_delete=models.PROTECT, related_name="+")
    authority = models.ForeignKey("library.Authority", null=True, blank=True, on_delete=models.PROTECT, related_name="sources")
    check_frequency = models.CharField(
        max_length=16, choices=_choices(CheckFrequency), default=CheckFrequency.WEEKLY.value
    )
    active = models.BooleanField(default=True)
    owner_tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "source"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SourceCheck(LibraryModel):
    """One check of one source (WAT-01): the answer to "how do you know you missed
    nothing". A failed check carries `error` and the stale rule reads it."""

    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="checks")
    agent_run = models.ForeignKey("agents.AgentRun", null=True, blank=True, on_delete=models.PROTECT, related_name="source_checks")
    checked_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=16, choices=_choices(CheckStatus))
    items_found = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    kind = models.CharField(max_length=16, choices=_choices(SourceCheckKind), default=SourceCheckKind.SWEEP.value)
    subject_type = models.CharField(max_length=16, choices=_choices(SubjectType), blank=True)
    subject_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "source_check"
        ordering = ["-checked_at", "id"]
        indexes = [models.Index(fields=["source", "-checked_at"], name="source_check_latest_idx")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind=SourceCheckKind.RECHECK.value)
                    & ~models.Q(subject_type="")
                    & models.Q(subject_id__isnull=False)
                )
                | (
                    ~models.Q(kind=SourceCheckKind.RECHECK.value)
                    & models.Q(subject_type="")
                    & models.Q(subject_id__isnull=True)
                ),
                name="source_check_recheck_names_a_subject",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source_id}:{self.checked_at:%Y-%m-%d}"


# ---------------------------------------------------------------------------------------
# WAT-02, WAT-07: one record per reform
# ---------------------------------------------------------------------------------------
class RegulatoryChange(LibraryModel):
    """What happened, sourced facts only (schema v0.3 `regulatory_change`). `stable_key`
    is the merge key: posting a known one adds pages to this row instead of creating a
    second (AC-WAT1). `key_date` is the one date that drives "coming up"; `so_what_draft`
    is the library's draft, copied into each tenant's case and confirmed there (WAT-05)."""

    stable_key = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=500)
    change_type = models.ForeignKey("taxonomy.ChangeType", on_delete=models.PROTECT, related_name="+")
    authority = models.ForeignKey("library.Authority", null=True, blank=True, on_delete=models.PROTECT, related_name="changes")
    authority_label = models.CharField(max_length=200)
    published_on = models.DateField(null=True, blank=True)
    published_precision = _precision()
    summary = models.TextField(blank=True)
    so_what_draft = models.TextField(blank=True)
    suggested_urgency = models.ForeignKey("taxonomy.Urgency", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    key_date = models.DateField(null=True, blank=True)
    key_date_precision = _precision()
    key_date_label = models.CharField(max_length=200, blank=True)
    recurrence_rule = models.CharField(max_length=500, blank=True)
    source_label = models.CharField(max_length=500)
    source_url = models.URLField(max_length=2000)
    status = models.CharField(max_length=16, choices=_choices(ChangeStatus), default=ChangeStatus.ACTIVE.value)
    superseded_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="supersedes")
    origin = models.CharField(max_length=16, choices=_choices(OriginType))
    agent_run = models.ForeignKey("agents.AgentRun", null=True, blank=True, on_delete=models.PROTECT, related_name="changes")
    model = models.CharField(max_length=200, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "regulatory_change"
        # The feed's order: the key date first, then when we first saw it, newest first,
        # with a stable tiebreak so a page boundary never drops or repeats a row. A change
        # with no key date yet sorts last, not first: PostgreSQL puts nulls first on a
        # descending sort, which would open the feed with the changes that have no date.
        ordering = [models.F("key_date").desc(nulls_last=True), "-first_seen_at", "id"]
        indexes = [
            models.Index(
                fields=["key_date"],
                condition=models.Q(status=ChangeStatus.ACTIVE.value),
                name="regulatory_change_key_date_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(superseded_by=models.F("id")), name="regulatory_change_not_self_superseded"
            )
        ]

    def __str__(self) -> str:
        return self.stable_key


class ChangeEvent(LibraryModel):
    """One entry of a change's timeline, consultation to in force (WAT-02). The date is a
    plain date with a precision, or none at all when it is not set yet."""

    change = models.ForeignKey(RegulatoryChange, on_delete=models.CASCADE, related_name="events")
    label = models.CharField(max_length=200)
    event_date = models.DateField(null=True, blank=True)
    date_precision = _precision()
    occurred = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    source_url = models.URLField(max_length=2000, blank=True)

    class Meta:
        db_table = "change_event"
        ordering = ["sort_order", "id"]
        indexes = [models.Index(fields=["change", "sort_order"], name="change_event_change_idx")]

    def __str__(self) -> str:
        return f"{self.change_id}:{self.label}"


class ChangeDocument(LibraryModel):
    """A source page of a change (WAT-02, AGT-07). A second sighting of the same reform
    lands here as a duplicate instead of a second change. `risk_flags` records what the
    injection screen found in the fetched text, which is stored unaltered, as data."""

    change = models.ForeignKey(RegulatoryChange, on_delete=models.CASCADE, related_name="documents")
    url = models.URLField(max_length=2000)
    title = models.CharField(max_length=500, blank=True)
    publisher = models.CharField(max_length=200, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    content_hash = models.CharField(max_length=128, blank=True)
    is_primary = models.BooleanField(default=False)
    is_duplicate = models.BooleanField(default=False)
    risk_flags = ArrayField(models.CharField(max_length=40), default=list, blank=True)

    class Meta:
        db_table = "change_document"
        ordering = ["-is_primary", "url"]
        constraints = [models.UniqueConstraint(fields=["change", "url"], name="change_document_url_unique")]

    def __str__(self) -> str:
        return f"{self.change_id}:{self.url}"


# ---------------------------------------------------------------------------------------
# WAT-03, WAT-04: what the change touches, suggested until a person confirms it
# ---------------------------------------------------------------------------------------
class ChangeTerm(LibraryModel):
    """A flag or a scope term on a change (WAT-03). Exactly one of the two: a flag is a
    row of the `flag` list and a scope term a row of a dimension, and neither is ever a
    `text[]` (INPUT_DELTAS §1). The agent's `confidence` and `suggested` travel with the
    link, so the feed can mark it as a suggestion until a library editor confirms it."""

    change = models.ForeignKey(RegulatoryChange, on_delete=models.CASCADE, related_name="term_links")
    term = models.ForeignKey("taxonomy.TaxonomyTerm", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    flag = models.ForeignKey("taxonomy.Flag", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    suggested = models.BooleanField(default=True)
    confirmed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "change_term"
        # Flags first, each list in its own order; a term row's flag sort order is null,
        # which Postgres sorts last.
        ordering = ["flag__sort_order", "term__sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["change", "term"], name="change_term_term_unique"),
            models.UniqueConstraint(fields=["change", "flag"], name="change_term_flag_unique"),
            models.CheckConstraint(
                condition=models.Q(term__isnull=True, flag__isnull=False)
                | models.Q(term__isnull=False, flag__isnull=True),
                name="change_term_one_subject",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__isnull=True) | models.Q(confidence__gte=0, confidence__lte=1),
                name="change_term_confidence_range",
            ),
            models.CheckConstraint(
                condition=models.Q(suggested=True, confirmed_by__isnull=True, confirmed_at__isnull=True)
                | models.Q(suggested=False, confirmed_by__isnull=False, confirmed_at__isnull=False),
                name="change_term_confirmation_names_a_person",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.change_id}:{self.flag_id or self.term_id}"


class ChangeObligation(LibraryModel):
    """An obligation a change affects (WAT-04). An agent's link carries its confidence and
    is a suggestion until a library editor confirms it; the tenant's own decision about
    the link lives on its case, never here."""

    change = models.ForeignKey(RegulatoryChange, on_delete=models.CASCADE, related_name="obligation_links")
    obligation = models.ForeignKey("library.Obligation", on_delete=models.PROTECT, related_name="change_links")
    origin = models.CharField(max_length=16, choices=_choices(OriginType))
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    confirmed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "change_obligation"
        # Most confident first; a link with no confidence — a person's own — sorts after
        # the agent's scored ones rather than ahead of them, which is where PostgreSQL's
        # nulls-first default on a descending sort would put it.
        ordering = [models.F("confidence").desc(nulls_last=True), "obligation__stable_key"]
        constraints = [
            models.UniqueConstraint(fields=["change", "obligation"], name="change_obligation_unique"),
            models.CheckConstraint(
                condition=models.Q(confidence__isnull=True) | models.Q(confidence__gte=0, confidence__lte=1),
                name="change_obligation_confidence_range",
            ),
            models.CheckConstraint(
                condition=models.Q(confirmed_by__isnull=True, confirmed_at__isnull=True)
                | models.Q(confirmed_by__isnull=False, confirmed_at__isnull=False),
                name="change_obligation_confirmation_names_a_person",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.change_id}:{self.obligation_id}"


# The seven tables the watch door may write (apps/watch/write.py). Nothing else under
# apps/watch/ reaches a library row, and this door reaches no inventory table.
WATCH_MODELS: tuple[type[LibraryModel], ...] = (
    Source,
    SourceCheck,
    RegulatoryChange,
    ChangeEvent,
    ChangeDocument,
    ChangeTerm,
    ChangeObligation,
)

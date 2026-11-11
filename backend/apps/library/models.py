"""Models of the library app: the content languages and jurisdictions (I18N-01), and the
shared library's instruments, provisions, obligations and their versions (INV-01 to INV-06).

`Language` and `Jurisdiction` are reference configuration, filed by the reference seed. They
are plain models rather than `LibraryModel`s, so tenant logic can name them beside its own
writes without tripping the library fence (apps/shared/tests_library_fence.py); the
database's door trigger holds them instead (shared 0008, 0010). A jurisdiction is a
`Vocabulary` whose kind is the tier-one `JurisdictionKind`; it is relabelled, retired and
restored only through an approved proposal (D-94, VOC-07), so it carries a
`LibraryVocabulary`'s version and provenance. A language is the seed's alone."""

from __future__ import annotations

import enum
import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils import timezone

from apps.proposals.models import OriginType
from apps.shared.tenancy import LibraryModel
from apps.shared.vocabulary import Vocabulary, VocabularyLabel
from apps.shared.kinds import choices


class Language(models.Model):
    """A content or UI language (I18N-01): immutable `key` (BCP 47 primary tag), a name
    in that language, the PostgreSQL text search configuration search chunks use, and an
    active flag. Seeded: en, sv, da, nb, fi."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=8, unique=True)
    name = models.CharField(max_length=80)
    text_search_config = models.CharField(max_length=40)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "language"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class JurisdictionKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): supranational (EU), country, or international
    (INV-01, INV-08, D-38) for a standards body such as ISO/IEC. `international` is left out
    of `MIRRORED_JURISDICTION_KINDS` (apps/taxonomy/seeds/__init__.py), so the footprint
    never offers "International" as an operating market."""

    SUPRANATIONAL = "supranational"
    COUNTRY = "country"
    INTERNATIONAL = "international"


class Jurisdiction(Vocabulary):
    """A jurisdiction (I18N-01): `eu`, `se`, `dk`, `no`, `fi` and `intl` (D-38), seeded with a
    parent and the language its legal texts are written in.

    `parent` is the jurisdiction whose rules reach this one (D-28, ADR 0026), not
    membership: Norway is outside the Union and still reached by EU financial rules
    through the EEA Agreement.

    `version` backs If-Match on a relabel proposal; the three provenance columns are a
    `LibraryVocabulary`'s (apps/shared/vocabulary.py, D-79, D-94), blank on a seeded row."""

    KIND_CHOICES = [(kind.value, kind.value) for kind in JurisdictionKind]

    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    default_language = models.ForeignKey(Language, on_delete=models.PROTECT, related_name="+")
    version = models.PositiveIntegerField(default=1)
    verified_origin = models.CharField(max_length=16, choices=choices(OriginType), blank=True, default="")
    verified_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    applied_by_proposal = models.ForeignKey("proposals.Proposal", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "jurisdiction"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="jurisdiction_key_unique")]


class JurisdictionLabel(VocabularyLabel):
    vocabulary = models.ForeignKey(Jurisdiction, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "jurisdiction_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="jurisdiction_label_unique")]


# --- The shared library (INV-01..INV-06; INPUT_DELTAS §1, §3, §5) ---
# Every table below but ProblemReport extends LibraryModel: no tenant column, written only
# inside library_write(). `owner_tenant` on instrument and obligation is the tenant-private
# record (INV-07) under the "shared or mine" policy. Vocabularies are rows referenced by
# foreign key; the enums here are kinds only (apps/shared/kinds.py).
class DatePrecision(enum.StrEnum):
    """A legal date is a plain date with a precision (playbook 4.3, INV-S10)."""

    DAY = "day"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class RecordStatus(enum.StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class SubjectType(enum.StrEnum):
    """What a verification or a problem report points at."""

    INSTRUMENT = "instrument"
    PROVISION = "provision"
    OBLIGATION = "obligation"


class ReportStatus(enum.StrEnum):
    """AUD-03: a "this looks wrong" report's lifecycle. A report is filed `open` and closed
    inside its own bank with one of the other three and a note; nobody outside the bank
    closes it (D-50)."""

    OPEN = "open"
    ANSWERED = "answered"
    FIXED = "fixed"
    REJECTED = "rejected"


class VerificationOutcome(enum.StrEnum):
    NO_CHANGE = "no_change"
    CHANGE_FOUND = "change_found"
    SOURCE_UNAVAILABLE = "source_unavailable"


def _precision() -> models.CharField:
    return models.CharField(max_length=8, choices=choices(DatePrecision), default=DatePrecision.DAY.value)


def _trigram(field: str, name: str) -> GinIndex:
    # The keyword leg of search matches titles and references by similarity.
    return GinIndex(fields=[field], name=name, opclasses=["gin_trgm_ops"])


class Translation(LibraryModel):
    """One text in one language (INPUT_DELTAS §3, D-12): the original, or a translation
    that stays labelled `is_machine` until a person confirms it (INV-05)."""

    language = models.ForeignKey(Language, to_field="key", on_delete=models.PROTECT, related_name="+")
    text = models.TextField()
    is_original = models.BooleanField(default=False)
    is_machine = models.BooleanField(default=False)

    class Meta:
        abstract = True
        ordering = ["language"]

    def __str__(self) -> str:
        return f"{self.language_id}: {self.text[:40]}"


def _translation_constraints(parent: str, table: str) -> list[models.BaseConstraint]:
    return [
        models.UniqueConstraint(fields=[parent, "language"], name=f"{table}_language_unique"),
        models.UniqueConstraint(fields=[parent], condition=models.Q(is_original=True), name=f"{table}_one_original"),
    ]


class Authority(LibraryModel):
    """An issuing authority (schema v0.3 `authority`), filed under a jurisdiction row."""

    key = models.SlugField(max_length=80, unique=True)
    short_name = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.PROTECT, related_name="authorities")
    url = models.URLField(max_length=2000)

    class Meta:
        db_table = "authority"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class Instrument(LibraryModel):
    """A law, regulation, guideline or edition of a standard (INV-01, INV-08). The name is
    translation rows (`InstrumentTitle`); `binding` starts from the level's default, false
    meaning guidance, comply or explain unless the level's kind is `standard`.

    `regime` is required and must be a `regime` term (D-39, INV-S12): it is the sector
    boundary, and an instrument without one would match every bank's footprint."""

    stable_key = models.SlugField(max_length=120, unique=True)
    short_name = models.CharField(max_length=120)
    official_ref = models.CharField(max_length=200)
    eli_uri = models.URLField(max_length=2000, blank=True)
    source_url = models.URLField(max_length=2000)
    level = models.ForeignKey("taxonomy.InstrumentLevel", on_delete=models.PROTECT, related_name="+")
    binding = models.BooleanField()
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.PROTECT, related_name="+")
    authority = models.ForeignKey(Authority, null=True, blank=True, on_delete=models.PROTECT, related_name="instruments")
    regime = models.ForeignKey("taxonomy.TaxonomyTerm", on_delete=models.PROTECT, related_name="+")
    in_force_from = models.DateField(null=True, blank=True)
    in_force_from_precision = _precision()
    in_force_to = models.DateField(null=True, blank=True)
    in_force_to_precision = _precision()
    implements_note = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=choices(RecordStatus), default=RecordStatus.ACTIVE.value)
    owner_tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_origin = models.CharField(max_length=16, choices=choices(OriginType))
    created_by_agent_run = models.UUIDField(null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    # Machine-confirmed provenance (INV-05, INV-06, PRO-02): who confirmed the change behind
    # the record's current state, an agent or a person, beside `verified_by`'s re-verification
    # stamp. Blank until a proposal that changes this table is applied.
    verified_origin = models.CharField(max_length=16, choices=choices(OriginType), blank=True, default="")
    verified_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "instrument"
        ordering = ["stable_key"]
        indexes = [_trigram("official_ref", "instrument_official_ref_trgm")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(in_force_to__isnull=True)
                | models.Q(in_force_from__isnull=True)
                | models.Q(in_force_to__gt=models.F("in_force_from")),
                name="instrument_in_force_order",
            )
        ]

    def __str__(self) -> str:
        return self.stable_key


class InstrumentTitle(Translation):
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name="titles")

    class Meta:
        db_table = "instrument_title"
        ordering = ["language"]
        indexes = [_trigram("text", "instrument_title_trgm")]
        constraints = _translation_constraints("instrument", "instrument_title")


class InstrumentSummary(Translation):
    """What an instrument is and what it means for a bank, in plain words, per content
    language (INV-09, D-124): written once from the instrument's own source and entered
    through an approved `new_instrument_summary` proposal like every library fact. Never
    rewritten in place: the instrument's own facts are what change (INV-01)."""

    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name="summaries")

    class Meta:
        db_table = "instrument_summary"
        ordering = ["language"]
        constraints = _translation_constraints("instrument", "instrument_summary")


class InstrumentRelation(LibraryModel):
    """Lineage between instruments (INV-01): implements, elaborates."""

    from_instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="relations_out")
    to_instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="relations_in")
    relation_type = models.ForeignKey("taxonomy.RelationType", on_delete=models.PROTECT, related_name="+")
    from_ref = models.CharField(max_length=200, blank=True)
    to_ref = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "instrument_relation"
        ordering = ["from_instrument__stable_key", "to_instrument__stable_key"]
        constraints = [
            models.UniqueConstraint(fields=["from_instrument", "to_instrument", "relation_type"], name="instrument_relation_unique"),
            models.CheckConstraint(condition=~models.Q(from_instrument=models.F("to_instrument")), name="instrument_relation_not_self"),
        ]

    def __str__(self) -> str:
        return f"{self.from_instrument_id} -> {self.to_instrument_id}"


class Provision(LibraryModel):
    """A node of an instrument's structure (INV-02): chapter, section, article. The legal
    text lives in `ProvisionVersion` rows, never on the node.

    Never under a standard (INV-08, AC-INV2, D-35): a standard's text is licensed. Triggers
    (library 0008) refuse, whatever the write path, a provision on a standard-level
    instrument or one the writer cannot see, an instrument with provisions moved onto a
    standard level, and a level made `standard` while provisions sit under it."""

    stable_key = models.CharField(max_length=200, unique=True)
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="provisions")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    kind = models.ForeignKey("taxonomy.ProvisionKind", on_delete=models.PROTECT, related_name="+")
    ref_label = models.CharField(max_length=200)
    heading = models.TextField(blank=True)
    path = models.CharField(max_length=500)
    sort_order = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=choices(RecordStatus), default=RecordStatus.ACTIVE.value)

    class Meta:
        db_table = "provision"
        ordering = ["sort_order", "stable_key"]
        indexes = [models.Index(fields=["instrument", "sort_order"], name="provision_instrument_idx")]

    def __str__(self) -> str:
        return self.stable_key


class ProvisionVersion(LibraryModel):
    """Verbatim text in force from a date (INV-02): nothing overwritten, a new row per
    amendment. A null `effective_from` means since the provision began."""

    provision = models.ForeignKey(Provision, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    effective_from = models.DateField(null=True, blank=True)
    effective_from_precision = _precision()
    effective_to = models.DateField(null=True, blank=True)
    effective_to_precision = _precision()
    transitional_note = models.TextField(blank=True)
    applied_by_proposal = models.ForeignKey("proposals.Proposal", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "provision_version"
        ordering = ["version_number"]
        indexes = [models.Index(fields=["provision", "effective_from"], name="provision_version_asof_idx")]
        constraints = [
            models.UniqueConstraint(fields=["provision", "version_number"], name="provision_version_unique"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True)
                | models.Q(effective_from__isnull=True)
                | models.Q(effective_to__gt=models.F("effective_from")),
                name="provision_version_effective_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provision_id} v{self.version_number}"


class ProvisionText(Translation):
    version = models.ForeignKey(ProvisionVersion, on_delete=models.CASCADE, related_name="texts")

    class Meta:
        db_table = "provision_text"
        ordering = ["language"]
        constraints = _translation_constraints("version", "provision_text")


class Obligation(LibraryModel):
    """A plain-language duty broken out of an instrument (INV-03), with its provenance
    (origin, model, source) and last verification (INV-06). The title is translation
    rows; the summary lives in versions."""

    stable_key = models.SlugField(max_length=120, unique=True)
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="obligations")
    ref_label = models.CharField(max_length=200)
    duty_type = models.ForeignKey("taxonomy.DutyType", on_delete=models.PROTECT, related_name="+")
    product_scope = models.TextField(blank=True)
    trigger_frequency = models.TextField(blank=True)
    retention = models.TextField(blank=True)
    sanction_exposure = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=choices(RecordStatus), default=RecordStatus.ACTIVE.value)
    owner_tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_origin = models.CharField(max_length=16, choices=choices(OriginType))
    created_by_agent_run = models.UUIDField(null=True, blank=True)
    created_model = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(max_length=2000)
    source_label = models.CharField(max_length=500)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    # Machine-confirmed provenance (INV-05, INV-06, PRO-02) of the obligation row itself,
    # blank until a proposal changing that row is applied. The current version's confirmation
    # lives on `ObligationVersion`, never overwritten.
    verified_origin = models.CharField(max_length=16, choices=choices(OriginType), blank=True, default="")
    verified_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    provisions = models.ManyToManyField(Provision, through="library.ObligationProvision", related_name="obligations")
    terms = models.ManyToManyField("taxonomy.TaxonomyTerm", through="library.ObligationTerm", related_name="+")
    tags = models.ManyToManyField("taxonomy.LibraryTag", through="library.ObligationTag", related_name="+")

    class Meta:
        db_table = "obligation"
        ordering = ["stable_key"]
        # The monthly re-verification picks the oldest first.
        indexes = [models.Index(fields=["last_verified_at"], name="obligation_verified_idx")]

    def __str__(self) -> str:
        return self.stable_key


class ObligationTitle(Translation):
    obligation = models.ForeignKey(Obligation, on_delete=models.CASCADE, related_name="titles")

    class Meta:
        db_table = "obligation_title"
        ordering = ["language"]
        indexes = [_trigram("text", "obligation_title_trgm")]
        constraints = _translation_constraints("obligation", "obligation_title")


class ObligationVersion(LibraryModel):
    """The summary in force from a date (INV-04); "as of" D is `logic.in_force()`. A change
    about to take effect is a second row with a future `effective_from`."""

    obligation = models.ForeignKey(Obligation, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    effective_from = models.DateField(null=True, blank=True)
    effective_from_precision = _precision()
    caused_by_change = models.UUIDField(null=True, blank=True)  # the regulatory change; a foreign key from chunk 5
    applied_by_proposal = models.ForeignKey("proposals.Proposal", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    approved_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    # Machine-confirmed provenance (INV-05, INV-06, PRO-02): set once, with the version, from
    # the approving proposal's two sides. `agent`: `verified_by_agent` names the confirming
    # agent (the proposer is `applied_by_proposal.proposed_by_agent`); `user`: `approved_by`.
    verified_origin = models.CharField(max_length=16, choices=choices(OriginType), blank=True, default="")
    verified_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "obligation_version"
        ordering = ["version_number"]
        indexes = [models.Index(fields=["obligation", "effective_from"], name="obligation_version_asof_idx")]
        constraints = [models.UniqueConstraint(fields=["obligation", "version_number"], name="obligation_version_unique")]

    def __str__(self) -> str:
        return f"{self.obligation_id} v{self.version_number}"


class ObligationSummary(Translation):
    version = models.ForeignKey(ObligationVersion, on_delete=models.CASCADE, related_name="summaries")

    class Meta:
        db_table = "obligation_summary"
        ordering = ["language"]
        constraints = _translation_constraints("version", "obligation_summary")


class ObligationProvision(LibraryModel):
    obligation = models.ForeignKey(Obligation, on_delete=models.PROTECT, related_name="+")
    provision = models.ForeignKey(Provision, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "obligation_provision"
        ordering = ["provision__sort_order", "provision__stable_key"]
        constraints = [models.UniqueConstraint(fields=["obligation", "provision"], name="obligation_provision_unique")]

    def __str__(self) -> str:
        return f"{self.obligation_id}:{self.provision_id}"


class ObligationTerm(LibraryModel):
    """A scope facet (FP-01): footprint matching reads these per dimension."""

    obligation = models.ForeignKey(Obligation, on_delete=models.PROTECT, related_name="+")
    term = models.ForeignKey("taxonomy.TaxonomyTerm", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "obligation_term"
        ordering = ["term__sort_order", "term__key"]
        constraints = [models.UniqueConstraint(fields=["obligation", "term"], name="obligation_term_unique")]

    def __str__(self) -> str:
        return f"{self.obligation_id}:{self.term_id}"


class ObligationTag(LibraryModel):
    obligation = models.ForeignKey(Obligation, on_delete=models.PROTECT, related_name="+")
    tag = models.ForeignKey("taxonomy.LibraryTag", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "obligation_tag"
        ordering = ["tag__sort_order", "tag__key"]
        constraints = [models.UniqueConstraint(fields=["obligation", "tag"], name="obligation_tag_unique")]

    def __str__(self) -> str:
        return f"{self.obligation_id}:{self.tag_id}"


class ObligationRelation(LibraryModel):
    from_obligation = models.ForeignKey(Obligation, on_delete=models.PROTECT, related_name="relations_out")
    to_obligation = models.ForeignKey(Obligation, on_delete=models.PROTECT, related_name="relations_in")
    relation_type = models.ForeignKey("taxonomy.RelationType", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "obligation_relation"
        ordering = ["from_obligation__stable_key", "to_obligation__stable_key"]
        constraints = [
            models.UniqueConstraint(fields=["from_obligation", "to_obligation"], name="obligation_relation_unique"),
            models.CheckConstraint(condition=~models.Q(from_obligation=models.F("to_obligation")), name="obligation_relation_not_self"),
        ]

    def __str__(self) -> str:
        return f"{self.from_obligation_id} -> {self.to_obligation_id}"


class Verification(LibraryModel):
    """Every re-verification of a record against its source, not only the latest stamp
    (INV-06): the one library write outside a proposal, still inside library_write()."""

    subject_type = models.CharField(max_length=32, choices=choices(SubjectType))
    subject_id = models.UUIDField()
    verified_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    verified_at = models.DateTimeField(default=timezone.now)
    outcome = models.CharField(max_length=32, choices=choices(VerificationOutcome))
    note = models.TextField(blank=True)

    class Meta:
        db_table = "verification"
        ordering = ["-verified_at"]
        indexes = [models.Index(fields=["subject_type", "subject_id", "-verified_at"], name="verification_subject_idx")]

    def __str__(self) -> str:
        return f"{self.subject_type}:{self.subject_id} {self.outcome}"


class RecurringDuty(LibraryModel):
    """A duty an obligation carries on a schedule (REG-07): a quarterly report, a yearly
    attestation. A public fact, so no tenant column; a bank's occurrences are register rows.
    `recurrence_rule` is an RFC 5545 RRULE validated by the proposal kind that writes it, the
    only producer (library 0010, ADR 0058). `lead_days` is how long before a due date the
    duty shows; `recipient_authority` receives it, when an authority does.

    Provenance (INV-05, D-79, D-89) is set once from the approving proposal's two sides. The
    check constraints hold the confirming agent to be another agent than the proposer, so a
    record an agent confirmed never reads as verified by a person."""

    obligation = models.ForeignKey(Obligation, on_delete=models.PROTECT, related_name="recurring_duties")
    title = models.CharField(max_length=300)
    recurrence_rule = models.CharField(max_length=500)
    due_rule_note = models.TextField(blank=True)
    recipient_authority = models.ForeignKey(Authority, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    lead_days = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=choices(RecordStatus), default=RecordStatus.ACTIVE.value)
    applied_by_proposal = models.ForeignKey("proposals.Proposal", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_origin = models.CharField(max_length=16, choices=choices(OriginType))
    created_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    verified_origin = models.CharField(max_length=16, choices=choices(OriginType), blank=True, default="")
    verified_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    approved_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recurring_duty"
        ordering = ["obligation__stable_key", "title"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(created_origin=OriginType.AGENT.value) | models.Q(created_by_agent__isnull=False),
                name="recurring_duty_agent_proposal_named",
            ),
            models.CheckConstraint(
                condition=~models.Q(verified_origin=OriginType.AGENT.value) | models.Q(verified_by_agent__isnull=False),
                name="recurring_duty_agent_confirmation_named",
            ),
            models.CheckConstraint(
                condition=~models.Q(verified_origin=OriginType.USER.value) | models.Q(approved_by__isnull=False),
                name="recurring_duty_person_confirmation_named",
            ),
            models.CheckConstraint(
                condition=models.Q(verified_by_agent__isnull=True)
                | models.Q(created_by_agent__isnull=True)
                | ~models.Q(verified_by_agent=models.F("created_by_agent")),
                name="recurring_duty_confirmer_independent",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class ProblemReport(models.Model):
    """"This looks wrong" (INV-06, AUD-03). A mixed table under forced RLS whose rows all
    carry the bank that filed them; the column stays nullable pending docs/TODO_FOR_alex.md
    (problem reports). Any member writes one, so it is not a LibraryModel. It is read and
    closed inside that bank only (D-50): the reporter or a colleague holding
    `proposals.create` sets `answered`, `fixed` or `rejected` with a note, and the check
    constraint keeps a closed report naming who closed it, when and why. No proposal links
    to a report; the watch agents' re-check corrects the library.

    `version_number` and `language` record what the reader had on screen, so a colleague
    reads the same words."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reporter = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    subject_type = models.CharField(max_length=32, choices=choices(SubjectType))
    subject_id = models.UUIDField()
    text = models.TextField()
    version_number = models.PositiveIntegerField(null=True, blank=True)
    language = models.ForeignKey(Language, to_field="key", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=choices(ReportStatus), default=ReportStatus.OPEN.value)
    resolution_note = models.TextField(blank=True, default="")
    closed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "problem_report"
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status=ReportStatus.OPEN.value, resolution_note="", closed_by__isnull=True, closed_at__isnull=True
                )
                | (
                    ~models.Q(status=ReportStatus.OPEN.value)
                    & ~models.Q(resolution_note="")
                    & models.Q(closed_by__isnull=False, closed_at__isnull=False)
                ),
                name="problem_report_closed_with_note",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.subject_type}:{self.subject_id} {self.status}"

"""Reference seeds of the taxonomy app (VOC-01, FP-01, I18N-01), run by `manage.py
seed_reference` on every deploy: idempotent, matched on the immutable key, inside
`library_write("seed_reference")` because these are library rows. Everything a proposal
can change is written once, when the seed creates the row: the labels, the usage note, the
sort order, the active flag, the default and the extra columns (VOC-07). Re-applying them
on every deploy would silently undo an approved reorder, retire, default change or term
update the next time the app deployed. The `kind` is the exception: no proposal and no
route changes it, every kind needs an active system row, so the code's kind is put back on
every run. The jurisdiction dimension's mirrored terms are the second exception: no
proposal may change one at all (FP-S12), so the seed puts back the three facts it owns on
them. A key an approved proposal already used for a row of its own stops the seed rather
than being adopted. Every row created, every kind put back and every mirrored fact put back
leaves one audit row.

Keys, labels and usage notes come from the prototype fixture
(apps/taxonomy/seeds/fixture.py) so chunk 3 loads the fixture's records against the
rows these seeds wrote. What the prototype has no rows for (provision kinds, the five
dimensions beyond the prototype's seven, the rejection reasons, the licensed activities,
the standards a bank may follow) is authored here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.library.models import Jurisdiction, JurisdictionKind
from apps.shared.audit import Actor, record
from apps.shared.tenancy import library_write
from apps.taxonomy.models import (
    ChangeLifecycleKind,
    ProvisionStructuralKind,
    TaxonomyTerm,
    TaxonomyTermLabel,
    TermDimension,
    TermDimensionKind,
)
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.seeds import fixture

SEED_REASON = "seed_reference"
ORIGINAL_LANGUAGE = "en"
ACTOR = Actor.system(SEED_REASON)
JURISDICTION_DIMENSION = "jurisdiction"
# The jurisdiction kinds the `jurisdiction` dimension mirrors (FP-04, D-28, ADR 0026). Its
# terms are the markets a bank names, so only the jurisdictions a bank can operate in get
# one; the row international standards bodies issue under is a market nobody operates in and
# is left unmirrored (D-38, ADR 0032), which is what keeps a standard visible to a tenant
# that has named its markets.
MIRRORED_JURISDICTION_KINDS = (JurisdictionKind.SUPRANATIONAL.value, JurisdictionKind.COUNTRY.value)


@dataclass(frozen=True)
class SystemRow:
    key: str
    labels: dict[str, str]
    usage_note: str = ""
    kind: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _fixture_rows(list_name: str, *, kind_of: Any = None, extra_of: Any = None) -> list[SystemRow]:
    rows = []
    for key, row in fixture.vocabulary(list_name).items():
        rows.append(
            SystemRow(
                key=key,
                labels=fixture.labels_of(row),
                usage_note=row.get("usage_note", ""),
                kind=kind_of(row) if kind_of else row.get("kind"),
                extra=extra_of(row) if extra_of else {},
            )
        )
    return rows


def _tag_rows() -> list[SystemRow]:
    return [SystemRow(tag["key"], {"en": tag["label_en"], "sv": tag["label_sv"]}) for tag in fixture.tags()]


# The twelve dimensions: the prototype's seven from the fixture (with its
# restricts_footprint flags) and five authored here. Only `theme` classifies. `standard`, the
# standards a bank follows, is opt-in (D-36): a record carrying one of its terms shows only to
# a bank whose regulatory scope names that term, whatever its restricts_footprint flag says
# (apps/taxonomy/matching.py). No E2E tenant holds one of its terms, so a standard's records
# start outside every seeded bank's scope.
_EXTRA_DIMENSIONS: list[SystemRow] = [
    SystemRow("jurisdiction", {"en": "Jurisdiction", "sv": "Jurisdiktion"}, "Where the rule applies: the Union or a country. Terms mirror the jurisdiction table.", TermDimensionKind.SCOPE.value, {"restricts_footprint": True}),
    SystemRow("theme", {"en": "Theme", "sv": "Tema"}, "What the rule is about, for browsing and briefings. Never narrows the regulatory scope.", TermDimensionKind.CLASSIFICATION.value, {"restricts_footprint": False}),
    SystemRow("licensed_activity", {"en": "Licensed activity", "sv": "Tillståndspliktig verksamhet"}, "The licence under which the firm acts: banking, securities, insurance, fund management.", TermDimensionKind.SCOPE.value, {"restricts_footprint": True}),
    SystemRow("product_type", {"en": "Product type", "sv": "Produkttyp"}, "The financial product the rule concerns.", TermDimensionKind.SCOPE.value, {"restricts_footprint": True}),
    SystemRow(
        "standard",
        {"en": "Standards followed", "sv": "Standarder vi följer"},
        "The standards within the sector scope that the bank follows by choice, by contract or because a "
        "supervisor expects it. Opt-in: a record carrying a standard shows only to a bank whose regulatory "
        "scope names that standard, also when the scope names no standard at all. Only a standard's own "
        "records carry one of these terms; a law that cites a standard never does.",
        TermDimensionKind.OPT_IN.value,
        {"restricts_footprint": True},
    ),
]

# The payment services of PSD2 Annex I point 5, as the two businesses a firm is licensed
# for (Directive (EU) 2015/2366, Annex I; lag (2010:751) om betaltjänster 1 kap. 2 § 5,
# "utgivning av betalningsinstrument eller inlösen av transaktionsbelopp"). They are terms
# of `licensed_activity`, a dimension the prototype fixture has no rows for, so they are
# authored here like the other lists the prototype does not cover.
#
# The standards a bank may follow: one term per standard and never per edition, so a bank's
# scope survives a new edition (D-36), and ISO/IEC 27001 alone for now (D-47). A standard is
# named by its reference in every language, never by its title, and the library holds none
# of its text (INV-08). The watch door refuses a standard's term on a change whose authority
# is not a standards body (WAT-S11, 422 `standard_term_only_on_standards`): an agent's key
# registers a change with no second person (D-64), and a law tagged with a standard would
# vanish from every bank that follows none. With that door in place the term is seeded
# active; a database seeded while it was held keeps it inactive, because the seed creates
# and never updates a term. apps/taxonomy/tests_matching.SeededStandard pins it.
_EXTRA_TERMS: list[dict[str, Any]] = [
    {"dimension": "licensed_activity", "key": "card_issuing", "label_en": "Card issuing", "label_sv": "Kortutgivning", "sort_order": 1},
    {"dimension": "licensed_activity", "key": "card_acquiring", "label_en": "Card acquiring", "label_sv": "Kortinlösen", "sort_order": 2},
    {
        "dimension": "standard",
        "key": "iso_iec_27001",
        "label_en": "ISO/IEC 27001",
        "label_sv": "ISO/IEC 27001",
        "usage_note": (
            "The standard ISO/IEC 27001, every edition of it. Its records sit under the regime ai_ict "
            "(AI and ICT), so a bank sees them only when its regulatory scope holds both that regime and "
            "this term."
        ),
        "sort_order": 1,
    },
]

_PROVISION_KINDS: list[SystemRow] = [
    SystemRow("part", {"en": "Part", "sv": "Avdelning"}, "A top-level division of a long instrument.", ProvisionStructuralKind.DIVISION.value),
    SystemRow("chapter", {"en": "Chapter", "sv": "Kapitel"}, "A chapter (kap.) grouping sections or articles.", ProvisionStructuralKind.DIVISION.value),
    SystemRow("section", {"en": "Section", "sv": "Paragraf"}, "A numbered section (§) of a Swedish act or regulation.", ProvisionStructuralKind.UNIT.value),
    SystemRow("article", {"en": "Article", "sv": "Artikel"}, "A numbered article of an EU instrument.", ProvisionStructuralKind.UNIT.value),
    SystemRow("paragraph", {"en": "Paragraph", "sv": "Stycke"}, "A paragraph inside an article or section.", ProvisionStructuralKind.UNIT.value),
    SystemRow("guideline", {"en": "Guideline", "sv": "Riktlinje"}, "A numbered guideline in ESA guidelines or a supervisory circular.", ProvisionStructuralKind.UNIT.value),
    SystemRow("annex", {"en": "Annex", "sv": "Bilaga"}, "An annex to an instrument.", ProvisionStructuralKind.ANNEX.value),
]

# schema v0.3's `proposal.rejection_code` CHECK, in its order; the prototype has no labels.
_REJECTION_REASONS: list[SystemRow] = [
    SystemRow("wrong_fact", {"en": "Wrong fact", "sv": "Felaktig uppgift"}, "The proposal says something the source does not."),
    SystemRow("wrong_scope", {"en": "Wrong scope", "sv": "Fel omfattning"}, "The scope terms do not match who or what the source covers."),
    SystemRow("bad_source", {"en": "Bad source", "sv": "Bristfällig källa"}, "The source is missing, outdated or not the authoritative text."),
    SystemRow("duplicate", {"en": "Duplicate", "sv": "Dubblett"}, "The library already holds this, or another proposal makes the same change."),
    SystemRow("not_relevant", {"en": "Not relevant", "sv": "Inte relevant"}, "The change is outside what the library covers."),
    # Not in the CHECK list: the PRD's sector scope as a reason of its own (PRO-01, AGT-08),
    # so a reviewer can say why an off-sector record never enters the library.
    SystemRow(
        "outside_sector_scope",
        {"en": "Outside the sector scope", "sv": "Utanför sektorsomfattningen"},
        "The record falls outside the library's sector scope: regulated financial services only (banking, "
        "payments, investment services, insurance and pension provision, and asset and wealth management), "
        "with the AML, data protection and ICT-risk regimes that apply to them and the tax and AI rules as "
        "they apply to financial firms and their products. Every record carries a regime from the regime "
        "list, which is the boundary. Other sectors, and standards outside that scope such as ISO 9001, "
        "ISO 14001 or ISO 45001, never enter the library.",
    ),
    SystemRow("poor_wording", {"en": "Poor wording", "sv": "Otydlig formulering"}, "The facts hold, but the wording needs more than a correction in review."),
    SystemRow("other", {"en": "Other", "sv": "Annat"}, "None of the above; the note says why."),
]

# list name -> (default key, rows). Order is the picker's default order.
LIBRARY_SYSTEM_ROWS: dict[str, tuple[str, list[SystemRow]]] = {
    "term_dimension": (
        "regime",
        _fixture_rows(
            "term_dimension",
            kind_of=lambda row: TermDimensionKind.SCOPE.value,
            extra_of=lambda row: {"restricts_footprint": bool(row["restricts_footprint"])},
        )
        + _EXTRA_DIMENSIONS,
    ),
    "instrument_level": ("eu_regulation", _fixture_rows("instrument_level", extra_of=lambda row: {"binding_default": bool(row["binding_default"]), "rank": int(row["rank"])})),
    "provision_kind": ("article", _PROVISION_KINDS),
    "change_type": ("adopted", _fixture_rows("change_type", kind_of=lambda row: ChangeLifecycleKind(row["kind"]).value)),
    "duty_type": ("conduct", _fixture_rows("duty_type")),
    "relation_type": ("implements", _fixture_rows("relation_type")),
    "source_kind": ("authority_site", _fixture_rows("source_kind")),
    "urgency": ("monitor", _fixture_rows("urgency", kind_of=lambda row: fixture.TONES[row["tone"]], extra_of=lambda row: {"ordinal": int(row["ordinal"]), "sla_days": row["sla_days"]})),
    "library_tag": ("advice", _tag_rows()),
    "flag": ("ai", _fixture_rows("flag")),
    "rejection_reason": ("other", _REJECTION_REASONS),
}


def _ensure_rows(list_name: str, default_key: str, rows: list[SystemRow]) -> int:
    entry = REGISTRY[list_name]
    jurisdictions = {row.key: row for row in Jurisdiction.objects.all()} if "jurisdiction" in entry.extra_fields else {}
    count = 0
    for sort_order, spec in enumerate(rows):
        defaults: dict[str, Any] = {
            "kind": spec.kind,
            "is_system": True,
            "active": True,
            "sort_order": sort_order,
            "is_default": spec.key == default_key,
            **spec.extra,
        }
        if "jurisdiction" in entry.extra_fields:
            defaults["jurisdiction"] = jurisdictions.get(spec.extra.get("jurisdiction") or "")
        row, created = entry.model._default_manager.get_or_create(key=spec.key, defaults=defaults)
        if created:
            row.usage_note = spec.usage_note
            row.save(update_fields=["usage_note"])
            for language, text in spec.labels.items():
                entry.label_model._default_manager.create(vocabulary=row, language=language, text=text, is_original=language == ORIGINAL_LANGUAGE)
            record(
                action="library.seeded",
                actor=ACTOR,
                subject_type="vocabulary",
                subject_id=row.id,
                subject_title=f"{list_name}:{spec.key}",
                summary=f"Filed the {list_name} row {spec.key} from the reference seed.",
                tenant_id=None,
                after={"list": list_name, "key": spec.key, "labels": spec.labels},
            )
        elif not row.is_system:
            raise ValidationError(
                f"{list_name}:{spec.key} is already a row of its own on that list, so the system row "
                "cannot be filed. Give that row another key first.",
                code="system_key_taken",
            )
        elif row.kind != spec.kind:
            before = row.kind
            row.kind = spec.kind
            row.version += 1
            row.save(update_fields=["kind", "version"])
            record(
                action="vocabulary.updated",
                actor=ACTOR,
                subject_type="vocabulary",
                subject_id=row.id,
                subject_title=f"{list_name}:{spec.key}",
                summary=f"Put the kind of {spec.key} on {list_name} back.",
                tenant_id=None,
                before={"kind": before},
                after={"kind": spec.kind},
            )
        count += 1
    return count


def seed_library_vocabularies() -> int:
    """Every tier-2 list's system rows (the dimensions included). Without it agents get an
    empty vocabulary read and every classification is unknown_key."""
    with transaction.atomic(), library_write(SEED_REASON):
        return sum(_ensure_rows(name, default_key, rows) for name, (default_key, rows) in LIBRARY_SYSTEM_ROWS.items())


def seed_term_dimensions() -> int:
    """The twelve dimensions alone, for callers that need them before the rest."""
    default_key, rows = LIBRARY_SYSTEM_ROWS["term_dimension"]
    with transaction.atomic(), library_write(SEED_REASON):
        return _ensure_rows("term_dimension", default_key, rows)


def taxonomy_term_specs() -> list[dict[str, Any]]:
    """The fixture's terms, then the ones authored here for dimensions the prototype has
    no rows for."""
    return [*fixture.taxonomy_terms(), *_EXTRA_TERMS]


def _mirror_back(term: TaxonomyTerm, row: Jurisdiction, parent: TaxonomyTerm | None) -> None:
    """Put back the three facts the seed owns on a mirrored term when its jurisdiction row
    has moved: the link, the term of the jurisdiction whose rules reach it, and whether it
    is still in use. One version bump and one audit row for the lot, so a reader of the log
    can see why a term changed with no proposal behind it."""
    if (term.jurisdiction_id, term.parent_id, term.active) == (row.id, parent.id if parent else None, row.active):
        return
    before = {
        "jurisdiction": str(term.jurisdiction_id) if term.jurisdiction_id else None,
        "parent": term.parent.key if term.parent is not None else None,
        "active": term.active,
    }
    term.jurisdiction = row
    term.parent = parent
    term.active = row.active
    term.version += 1
    term.save(update_fields=["jurisdiction", "parent", "active", "version"])
    record(
        action="taxonomy.term_updated",
        actor=ACTOR,
        subject_type="taxonomy_term",
        subject_id=term.id,
        subject_title=f"{JURISDICTION_DIMENSION}:{row.key}",
        summary=f"Put the jurisdiction {row.key} back on its term in {JURISDICTION_DIMENSION}.",
        tenant_id=None,
        before=before,
        after={"jurisdiction": str(row.id), "parent": parent.key if parent else None, "active": row.active},
    )


def _mirror_jurisdiction_terms(dimension: TermDimension) -> int:
    """One term per mirrored jurisdiction row (FP-04, D-28, ADR 0026), so nobody keeps two
    lists in step by hand: the same key, the row's labels, the term of the jurisdiction whose
    rules reach it as its parent, and `active` mirrored.

    The link, the parent and `active` are put back on every run, because no proposal may
    change a term of a mirrored dimension (FP-S12) and a jurisdiction that moves must take
    its term with it. The labels and the sort order are written once, like every other
    seeded term, so nothing a later deploy does can silently undo an approved translation or
    reorder; the exactness guard therefore claims the labels for a freshly seeded database
    only. A term written by hand under a mirrored key stops the seed rather than being
    adopted: the row would keep its author's meaning while the dimension lost its mirror.
    Nothing is deleted here either. A jurisdiction that goes inactive takes its term
    inactive with it, and a label the jurisdiction dropped stays on the term, since only a
    proposal may take a translation off a term."""
    # Parents first, so a country's term can point at the term of the jurisdiction whose
    # rules reach it however the rows are ordered.
    rows = sorted(
        Jurisdiction.objects.filter(kind__in=MIRRORED_JURISDICTION_KINDS).select_related("parent").prefetch_related("labels"),
        key=lambda row: (row.parent_id is not None, row.sort_order, row.key),
    )
    terms: dict[str, TaxonomyTerm] = {}
    for row in rows:
        parent = terms.get(row.parent.key) if row.parent is not None else None
        term, created = TaxonomyTerm.objects.get_or_create(
            dimension=dimension,
            key=row.key,
            defaults={"jurisdiction": row, "parent": parent, "sort_order": row.sort_order, "is_system": True, "active": row.active},
        )
        if created:
            labels = {}
            for label in row.labels.all():
                TaxonomyTermLabel.objects.create(term=term, language=label.language, text=label.text, is_original=label.is_original)
                labels[label.language] = label.text
            record(
                action="taxonomy.term_created",
                actor=ACTOR,
                subject_type="taxonomy_term",
                subject_id=term.id,
                subject_title=f"{dimension.key}:{row.key}",
                summary=f"Filed the term {row.key} in {dimension.key} from the jurisdiction of the same key.",
                tenant_id=None,
                after={"dimension": dimension.key, "key": row.key, "labels": labels},
            )
        elif not term.is_system:
            raise ValidationError(
                f"{dimension.key}:{row.key} is already a term of its own on that dimension, so the "
                f"jurisdiction {row.key} cannot be mirrored onto it. Give that term another key first.",
                code="system_key_taken",
            )
        else:
            _mirror_back(term, row, parent)
        terms[row.key] = term
    return len(terms)


def switch_on_term(dimension: str, key: str) -> None:
    """Switch one seeded term on, for a seed that needs it where the reference list keeps it
    off: seed_e2e alone, for ISO/IEC 27001 (FP-S16, D-85), on a database seeded while the
    reference list held it (a new one files it active). One version bump and one audit row
    the first time; a term already on is left alone."""
    with transaction.atomic(), library_write(SEED_REASON):
        term = TaxonomyTerm.objects.select_for_update().get(dimension__key=dimension, key=key)
        if term.active:
            return
        term.active = True
        term.version += 1
        term.save(update_fields=["active", "version"])
        record(
            action="taxonomy.term_updated",
            actor=ACTOR,
            subject_type="taxonomy_term",
            subject_id=term.id,
            subject_title=f"{dimension}:{key}",
            summary=f"Switched the term {key} in {dimension} on.",
            tenant_id=None,
            before={"active": False},
            after={"active": True},
        )


def seed_taxonomy_terms(specs: list[dict[str, Any]] | None = None) -> int:
    """The taxonomy terms per dimension, and the jurisdiction dimension's mirror of the
    jurisdiction rows. Without them no footprint can be set, no obligation can be scoped and
    no market can be named. `specs` in place of the reference list is seed_e2e's alone: the
    terms its own fixtures need and no deployed library holds (acc-e2e-seed, J-11)."""
    dimensions = {row.key: row for row in TermDimension.objects.all()}
    count = 0
    with transaction.atomic(), library_write(SEED_REASON):
        for spec in taxonomy_term_specs() if specs is None else specs:
            dimension = dimensions[spec["dimension"]]
            term, created = TaxonomyTerm.objects.get_or_create(
                dimension=dimension,
                key=spec["key"],
                defaults={
                    "sort_order": int(spec.get("sort_order", 0)),
                    "usage_note": spec.get("usage_note", ""),
                    "is_system": True,
                    "active": bool(spec.get("active", True)),
                },
            )
            if created:
                labels = {}
                for language in ("en", "sv"):
                    text = spec.get(f"label_{language}")
                    if text:
                        TaxonomyTermLabel.objects.create(term=term, language=language, text=text, is_original=language == ORIGINAL_LANGUAGE)
                        labels[language] = text
                record(
                    action="taxonomy.term_created",
                    actor=ACTOR,
                    subject_type="taxonomy_term",
                    subject_id=term.id,
                    subject_title=f"{dimension.key}:{spec['key']}",
                    summary=f"Filed the term {spec['key']} in {dimension.key} from the reference seed.",
                    tenant_id=None,
                    after={"dimension": dimension.key, "key": spec["key"], "labels": labels},
                )
            count += 1
        count += _mirror_jurisdiction_terms(dimensions[JURISDICTION_DIMENSION])
    return count

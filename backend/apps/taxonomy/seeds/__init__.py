"""Reference seeds of the taxonomy app (VOC-01, FP-01, I18N-01), run by `manage.py
seed_reference` on every deploy: idempotent, matched on the immutable key, inside
`library_write("seed_reference")` because these are library rows. Labels and usage notes
are written once (a proposal relabels them afterwards); the kind, the extra columns and
the default follow the code and the fixture.

Keys, labels and usage notes come from the prototype fixture
(apps/taxonomy/seeds/fixture.py) so chunk 3 loads the fixture's records against the
rows these seeds wrote. The lists the prototype has no rows for (provision kinds, the
four dimensions beyond the prototype's seven, the rejection reasons) are authored here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.library.models import Jurisdiction, JurisdictionKind
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
JURISDICTION_DIMENSION = "jurisdiction"
# The jurisdiction kinds the `jurisdiction` dimension mirrors (FP-04, D-28, ADR 0026). Its
# terms are markets, so only the jurisdictions a bank can operate in get one; the row for
# international standards bodies is a market nobody operates in and is left unmirrored
# (D-38, ADR 0032), which is what keeps a standard visible to a tenant that names markets.
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


# The eleven dimensions of schema v0.3: the prototype's seven from the fixture (with its
# restricts_footprint flags), the other four authored here. Only `theme` classifies.
_EXTRA_DIMENSIONS: list[SystemRow] = [
    SystemRow("jurisdiction", {"en": "Jurisdiction", "sv": "Jurisdiktion"}, "Where the rule applies: the Union or a country. Terms mirror the jurisdiction table.", TermDimensionKind.SCOPE.value, {"restricts_footprint": True}),
    SystemRow("theme", {"en": "Theme", "sv": "Tema"}, "What the rule is about, for browsing and briefings. Never narrows the footprint.", TermDimensionKind.CLASSIFICATION.value, {"restricts_footprint": False}),
    SystemRow("licensed_activity", {"en": "Licensed activity", "sv": "Tillståndspliktig verksamhet"}, "The licence under which the firm acts: banking, securities, insurance, fund management.", TermDimensionKind.SCOPE.value, {"restricts_footprint": True}),
    SystemRow("product_type", {"en": "Product type", "sv": "Produkttyp"}, "The financial product the rule concerns.", TermDimensionKind.SCOPE.value, {"restricts_footprint": True}),
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
        row, created = entry.model._default_manager.update_or_create(key=spec.key, defaults=defaults)
        if created:
            row.usage_note = spec.usage_note
            row.save(update_fields=["usage_note"])
            for language, text in spec.labels.items():
                entry.label_model._default_manager.create(vocabulary=row, language=language, text=text, is_original=language == ORIGINAL_LANGUAGE)
        count += 1
    return count


def seed_library_vocabularies() -> int:
    """Every tier-2 list's system rows (the dimensions included). Without it agents get an
    empty vocabulary read and every classification is unknown_key."""
    with library_write(SEED_REASON):
        return sum(_ensure_rows(name, default_key, rows) for name, (default_key, rows) in LIBRARY_SYSTEM_ROWS.items())


def seed_term_dimensions() -> int:
    """The eleven dimensions alone, for callers that need them before the rest."""
    default_key, rows = LIBRARY_SYSTEM_ROWS["term_dimension"]
    with library_write(SEED_REASON):
        return _ensure_rows("term_dimension", default_key, rows)


def _mirror_jurisdiction_terms(dimension: TermDimension) -> int:
    """One term per mirrored jurisdiction row (FP-04, D-28, ADR 0026): the same key, the
    same labels, the term of the jurisdiction whose rules reach it as its parent, and
    `active` mirrored. A term someone wrote by hand under the same key is adopted rather
    than duplicated, and the whole mirror is re-applied on every run, so the two lists
    cannot drift apart. Nothing is deleted here: a jurisdiction that goes inactive takes
    its term inactive with it."""
    # Parents first, so a country's term can point at the term of the jurisdiction whose
    # rules reach it however the rows are ordered.
    rows = sorted(
        Jurisdiction.objects.filter(kind__in=MIRRORED_JURISDICTION_KINDS).select_related("parent").prefetch_related("labels"),
        key=lambda row: (row.parent_id is not None, row.sort_order, row.key),
    )
    terms: dict[str, TaxonomyTerm] = {}
    for row in rows:
        term, _ = TaxonomyTerm.objects.update_or_create(
            dimension=dimension,
            key=row.key,
            defaults={
                "jurisdiction": row,
                "parent": terms.get(row.parent.key) if row.parent is not None else None,
                "sort_order": row.sort_order,
                "is_system": True,
                "active": row.active,
            },
        )
        for label in row.labels.all():
            TaxonomyTermLabel.objects.update_or_create(
                term=term, language=label.language, defaults={"text": label.text, "is_original": label.is_original}
            )
        terms[row.key] = term
    return len(terms)


def seed_taxonomy_terms() -> int:
    """The prototype's taxonomy terms per dimension, and the jurisdiction dimension's
    mirror of the jurisdiction rows. Without them no footprint can be set, no obligation
    can be scoped and no market can be named."""
    dimensions = {row.key: row for row in TermDimension.objects.all()}
    count = 0
    with library_write(SEED_REASON):
        for spec in fixture.taxonomy_terms():
            dimension = dimensions[spec["dimension"]]
            term, created = TaxonomyTerm.objects.update_or_create(
                dimension=dimension,
                key=spec["key"],
                defaults={"sort_order": int(spec.get("sort_order", 0)), "is_system": True, "active": True},
            )
            if created:
                for language in ("en", "sv"):
                    text = spec.get(f"label_{language}")
                    if text:
                        TaxonomyTermLabel.objects.create(term=term, language=language, text=text, is_original=language == ORIGINAL_LANGUAGE)
            count += 1
        count += _mirror_jurisdiction_terms(dimensions[JURISDICTION_DIMENSION])
    return count

"""Reference seeds of the taxonomy app (VOC-01, FP-01, I18N-01), run by `manage.py
seed_reference` on every deploy: idempotent, matched on the immutable key, inside
`library_write("seed_reference")` because these are library rows. Everything a proposal
can change is written once, when the seed creates the row: the labels, the usage note, the
sort order, the active flag, the default and the extra columns (VOC-07). Re-applying them
on every deploy would silently undo an approved reorder, retire, default change or term
update the next time the app deployed. The `kind` is the exception: no proposal and no
route changes it, every kind needs an active system row, so the code's kind is put back on
every run. A key an approved proposal already used for a row of its own stops the seed
rather than being adopted. Every row created and every kind put back leaves one audit row.

Keys, labels and usage notes come from the prototype fixture
(apps/taxonomy/seeds/fixture.py) so chunk 3 loads the fixture's records against the
rows these seeds wrote. What the prototype has no rows for (provision kinds, the four
dimensions beyond the prototype's seven, the rejection reasons, the licensed activities)
is authored here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.library.models import Jurisdiction
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

# The payment services of PSD2 Annex I point 5, as the two businesses a firm is licensed
# for (Directive (EU) 2015/2366, Annex I; lag (2010:751) om betaltjänster 1 kap. 2 § 5,
# "utgivning av betalningsinstrument eller inlösen av transaktionsbelopp"). They are terms
# of `licensed_activity`, a dimension the prototype fixture has no rows for, so they are
# authored here like the other lists the prototype does not cover.
_EXTRA_TERMS: list[dict[str, Any]] = [
    {"dimension": "licensed_activity", "key": "card_issuing", "label_en": "Card issuing", "label_sv": "Kortutgivning", "sort_order": 1},
    {"dimension": "licensed_activity", "key": "card_acquiring", "label_en": "Card acquiring", "label_sv": "Kortinlösen", "sort_order": 2},
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
    """The eleven dimensions alone, for callers that need them before the rest."""
    default_key, rows = LIBRARY_SYSTEM_ROWS["term_dimension"]
    with transaction.atomic(), library_write(SEED_REASON):
        return _ensure_rows("term_dimension", default_key, rows)


def taxonomy_term_specs() -> list[dict[str, Any]]:
    """The fixture's terms, then the ones authored here for dimensions the prototype has
    no rows for."""
    return [*fixture.taxonomy_terms(), *_EXTRA_TERMS]


def seed_taxonomy_terms() -> int:
    """The taxonomy terms per dimension. Without them no footprint can be set and no
    obligation can be scoped."""
    dimensions = {row.key: row for row in TermDimension.objects.all()}
    count = 0
    with transaction.atomic(), library_write(SEED_REASON):
        for spec in taxonomy_term_specs():
            dimension = dimensions[spec["dimension"]]
            term, created = TaxonomyTerm.objects.get_or_create(
                dimension=dimension,
                key=spec["key"],
                defaults={"sort_order": int(spec.get("sort_order", 0)), "is_system": True, "active": True},
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
    return count

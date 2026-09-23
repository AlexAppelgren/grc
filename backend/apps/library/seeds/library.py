"""The prototype's library as rows (chunk 3, INV-01..INV-06): authorities, instruments with
their titles and lineage, provisions with their own verbatim text versions (T8), obligations
with titles, versions, summaries, scope terms, tags, cited provisions and relations, from
apps/library/fixtures/prototype_data.json.

`seed_authorities` is a reference seed (INPUT_DELTAS §3: jurisdictions come with their
authorities) and runs on every deploy. `load_library` is demo data: `seed_demo` and
`seed_e2e` call it, never a deploy. Both are idempotent by stable key: an existing row is
left as it is (nothing overwritten; a proposal changes it), and every record created
leaves one audit row through record().

The research payment obligation's second version (in force 2026-10-01) exists in the
fixture only as the payload of the open proposal `prop-research-payments-v2`. The loader
files it as version 2 so "as of" and the diff have a future version to show
(data-model §4, INV-S4); the proposal row itself is not seeded here.

Every record carries a verified date (INV-06). The fixture dates obligations only, so an
instrument without its own date takes the latest of its obligations', or the fixture's
anchor date when it has none. `verified_by` is never loaded: the fixture's verifier is a
tenant user, and a library record is verified by a library editor (INV-S8)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from apps.library.models import (
    Authority,
    DatePrecision,
    Instrument,
    InstrumentRelation,
    InstrumentTitle,
    Jurisdiction,
    Obligation,
    ObligationProvision,
    ObligationRelation,
    ObligationSummary,
    ObligationTag,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
)
from apps.proposals.models import OriginType
from apps.shared.audit import Actor, record
from apps.shared.tenancy import library_write
from apps.taxonomy.models import DutyType, InstrumentLevel, LibraryTag, ProvisionKind, RelationType, TaxonomyTerm
from apps.taxonomy.seeds import fixture

SEED_REASON = "seed_library"
ACTOR = Actor.system(SEED_REASON)
RESEARCH_OBLIGATION = "obl-research-payments"
# The prototype writes every obligation title in English; summaries name their original.
TITLE_LANGUAGE = "en"
SUMMARY_PREFIX = "summary_"
# The provision tree's own text versions carry this prefix instead (T8), never a summary:
# a provision's verbatim text is not an obligation's plain-language duty.
PROVISION_TEXT_PREFIX = "text_"
# The fixture's proposal kind for a new obligation version (schema v0.3 `proposal_kind`);
# chunk 4 adds it to ProposalKind.
NEW_OBLIGATION_VERSION = "new_obligation_version"


def _date(value: str | None) -> datetime.date | None:
    return datetime.date.fromisoformat(value) if value else None


def _stamp(value: str | None) -> datetime.datetime | None:
    """A verification date of the prototype, at midnight in its time zone."""
    day = _date(value)
    zone = ZoneInfo(fixture.load()["_meta"]["timezone"])
    return datetime.datetime.combine(day, datetime.time(), tzinfo=zone) if day else None


def _audit(subject_type: str, row: Any, key: str) -> None:
    record(
        action="library.seeded",
        actor=ACTOR,
        subject_type=subject_type,
        subject_id=row.id,
        subject_title=key,
        summary=f"Filed the {subject_type} {key} from the sample library fixture.",
        tenant_id=None,
    )


def _authorities(specs: list[dict[str, Any]]) -> None:
    jurisdictions = {row.key: row for row in Jurisdiction.objects.all()}
    for spec in specs:
        row, created = Authority.objects.get_or_create(
            key=spec["key"],
            defaults={
                "short_name": spec["code"],
                "name": spec["name"],
                "jurisdiction": jurisdictions[spec["jurisdiction"].lower()],
                "url": spec["url"],
            },
        )
        if created:
            _audit("authority", row, row.key)


def seed_authorities() -> int:
    """The issuing authorities. Without them no instrument names who issued it."""
    specs = fixture.load()["authorities"]
    with library_write("seed_reference"):
        _authorities(specs)
    return len(specs)


def _instrument_verified_on(data: dict[str, Any]) -> dict[str, str]:
    """Instrument key -> its verified date: its own, else its obligations' latest, else the
    anchor date. ISO dates order as strings; check_prototype_data.py requires a verified
    date on every obligation."""
    latest: dict[str, str] = {}
    for spec in data["obligations"]:
        latest[spec["instrument"]] = max(latest.get(spec["instrument"], ""), spec["last_verified_at"])
    anchor: str = data["_meta"]["anchor_date"]
    return {spec["stable_key"]: spec["last_verified_at"] or latest.get(spec["stable_key"], anchor) for spec in data["instruments"]}


def _instrument(spec: dict[str, Any], terms: dict[str, TaxonomyTerm], verified_on: str) -> Instrument:
    jurisdiction = Jurisdiction.objects.select_related("default_language").get(key=spec["jurisdiction"].lower())
    row, created = Instrument.objects.get_or_create(
        stable_key=spec["stable_key"],
        defaults={
            "short_name": spec["short_name"],
            "official_ref": spec["official_ref"],
            "eli_uri": spec["eli_uri"] or "",
            "source_url": spec["source_url"],
            "level": InstrumentLevel.objects.get(key=spec["level"]),
            "binding": spec["binding"],
            "jurisdiction": jurisdiction,
            "authority": Authority.objects.get(key=spec["authority"]) if spec["authority"] else None,
            "regime": terms[spec["regime"]],
            "in_force_from": _date(spec["in_force_from"]),
            "in_force_from_precision": spec.get("in_force_from_precision") or DatePrecision.DAY.value,
            "in_force_to": _date(spec["in_force_to"]),
            "implements_note": spec["implements_note"] or "",
            "status": spec["status"],
            "created_origin": OriginType.USER.value,
            "last_verified_at": _stamp(verified_on),
        },
    )
    if created:
        # The official name is written in the jurisdiction's legal language.
        InstrumentTitle.objects.create(instrument=row, language_id=jurisdiction.default_language.key, text=spec["name"], is_original=True)
        _audit("instrument", row, row.stable_key)
    return row


def _obligation(spec: dict[str, Any], instrument: Instrument) -> Obligation:
    row, created = Obligation.objects.get_or_create(
        stable_key=spec["stable_key"],
        defaults={
            "instrument": instrument,
            "ref_label": spec["ref_label"],
            "duty_type": DutyType.objects.get(key=spec["duty_type"]),
            "product_scope": spec["product_scope"] or "",
            "trigger_frequency": spec["trigger_frequency"] or "",
            "retention": spec["retention"] or "",
            "sanction_exposure": spec["sanction_exposure"] or "",
            "status": spec["status"],
            "created_origin": spec["created_origin"],
            "created_model": spec["created_model"] or "",
            "source_url": instrument.source_url,
            "source_label": f"{instrument.official_ref}, {spec['ref_label']}",
            "last_verified_at": _stamp(spec["last_verified_at"]),
        },
    )
    if created:
        ObligationTitle.objects.create(obligation=row, language_id=TITLE_LANGUAGE, text=spec["title"], is_original=True)
        for key in spec["tags"]:
            ObligationTag.objects.create(obligation=row, tag=LibraryTag.objects.get(key=key))
        _audit("obligation", row, row.stable_key)
    return row


def _version(spec: dict[str, Any], obligation: Obligation) -> None:
    version, created = ObligationVersion.objects.get_or_create(
        obligation=obligation, version_number=spec["version_no"], defaults={"effective_from": _date(spec["effective_from"])}
    )
    if created:
        original = spec["original_language"]
        for field, text in spec.items():
            if field.startswith(SUMMARY_PREFIX):
                language = field.removeprefix(SUMMARY_PREFIX)
                ObligationSummary.objects.create(
                    version=version, language_id=language, text=text, is_original=language == original, is_machine=language != original
                )


def _provision_version(spec: dict[str, Any], provision: Provision) -> None:
    """A provision's verbatim text version (INV-02, T8): write-once, like `_version` above.
    `effective_to` is never set here; every read derives it from the version that follows."""
    version, created = ProvisionVersion.objects.get_or_create(
        provision=provision,
        version_number=spec["version_no"],
        defaults={"effective_from": _date(spec["effective_from"]), "transitional_note": spec["transitional_note"] or ""},
    )
    if created:
        original = spec["original_language"]
        for field, text in spec.items():
            if field.startswith(PROVISION_TEXT_PREFIX):
                language = field.removeprefix(PROVISION_TEXT_PREFIX)
                ProvisionText.objects.create(
                    version=version, language_id=language, text=text, is_original=language == original, is_machine=language != original
                )


def _version_specs(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The fixture's versions plus the pending second version held in a proposal payload."""
    specs: list[dict[str, Any]] = list(data["obligation_versions"])
    originals = {spec["obligation"]: spec["original_language"] for spec in specs}
    for proposal in data["proposals"]:
        if proposal["kind"] == NEW_OBLIGATION_VERSION:
            specs.append({**proposal["payload"], "obligation": proposal["target"], "original_language": originals[proposal["target"]]})
    return specs


def load_library(path: Path | None = None) -> dict[str, int]:
    """The prototype's library, or the library fixture at `path` (seed_e2e's
    e2e_standard.json), which names its own authorities and otherwise has the prototype's
    sections and references its vocabularies. Terms resolve whatever their state: a fixture
    may link an obligation to a held term without switching it on."""
    data = fixture.load() if path is None else json.loads(path.read_text(encoding="utf-8"))
    terms = {f"{term.dimension.key}:{term.key}": term for term in TaxonomyTerm.objects.select_related("dimension")}
    relation_types = {row.key: row for row in RelationType.objects.all()}
    verified_on = _instrument_verified_on(data)
    with library_write(SEED_REASON):
        if path is not None:
            _authorities(data["authorities"])
        instruments = {spec["stable_key"]: _instrument(spec, terms, verified_on[spec["stable_key"]]) for spec in data["instruments"]}
        for spec in data["instrument_relations"]:
            InstrumentRelation.objects.get_or_create(
                from_instrument=instruments[spec["from_instrument"]],
                to_instrument=instruments[spec["to_instrument"]],
                relation_type=relation_types[spec["relation"]],
                defaults={"from_ref": spec["from_ref"] or "", "to_ref": spec["to_ref"] or "", "note": spec["note"] or ""},
            )
        provisions: dict[str, Provision] = {}
        for spec in data["provisions"]:  # a parent precedes its children in the file
            row, created = Provision.objects.get_or_create(
                stable_key=spec["stable_key"],
                defaults={
                    "instrument": instruments[spec["instrument"]],
                    "parent": provisions[spec["parent"]] if spec["parent"] else None,
                    "kind": ProvisionKind.objects.get(key=spec["kind"]),
                    "ref_label": spec["ref"],
                    "heading": spec["heading"] or "",
                    "path": spec["path"],
                    "sort_order": spec["ordinal"],
                },
            )
            provisions[spec["stable_key"]] = row
            if created:
                _audit("provision", row, row.stable_key)
        for spec in data.get("provision_versions", []):
            _provision_version(spec, provisions[spec["provision"]])
        obligations = {spec["stable_key"]: _obligation(spec, instruments[spec["instrument"]]) for spec in data["obligations"]}
        versions = _version_specs(data)
        for spec in versions:
            _version(spec, obligations[spec["obligation"]])
        for spec in data["obligation_provisions"]:
            ObligationProvision.objects.get_or_create(obligation=obligations[spec["obligation"]], provision=provisions[spec["provision"]])
        for spec in data["obligation_terms"]:
            ObligationTerm.objects.get_or_create(obligation=obligations[spec["obligation"]], term=terms[spec["term"]])
        for spec in data["obligation_relations"]:
            ObligationRelation.objects.get_or_create(
                from_obligation=obligations[spec["obligation"]],
                to_obligation=obligations[spec["related_obligation"]],
                defaults={"relation_type": relation_types[spec["relation"]]},
            )
    return {"instruments": len(instruments), "provisions": len(provisions), "obligations": len(obligations), "obligation_versions": len(versions)}

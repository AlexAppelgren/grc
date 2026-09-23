"""Library builders for tests (playbook 8.1): an instrument, a provision, an obligation
with its title, scope terms, tags, cited provisions and summary versions, and a relation
between two obligations. Each builder writes inside
`library_write()` and sets every field when it creates a row; nothing here saves or
updates a row afterwards, because version, summary and text rows are append-only.

This module is the one place outside the reference seeds where a test writes a library
record: the library fence exempts `testing.py` modules (apps/shared/tests_library_fence.py),
and apps/shared/factories.py writes no library model. Terms are addressed as
`dimension:key` and vocabulary rows by key, exactly as the API addresses them."""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Mapping

from apps.library.models import (
    Authority,
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
from apps.identity.models import User
from apps.proposals.models import OriginType
from apps.shared.models import Tenant
from apps.shared.tenancy import library_write
from apps.taxonomy.models import DutyType, InstrumentLevel, LibraryTag, ProvisionKind, RelationType, TaxonomyTerm

REASON = "test builder"
SOURCE_URL = "https://www.example.test/source"
DEFAULT_VERSIONS: tuple[tuple[datetime.date | None, Mapping[str, str]], ...] = ((None, {"en": "The duty as it reads."}),)


def term(ref: str) -> TaxonomyTerm:
    """The term `dimension:key`."""
    dimension, _, key = ref.partition(":")
    return TaxonomyTerm.objects.select_related("dimension").get(dimension__key=dimension, key=key)


def instrument(
    *,
    key: str,
    short_name: str | None = None,
    regime: str,
    jurisdiction: str = "se",
    level: str = "act",
    binding: bool = True,
    owner_tenant: Tenant | None = None,
    authority: str | None = None,
    eli_uri: str = "",
    in_force_from: datetime.date | None = None,
    in_force_from_precision: str = "day",
    in_force_to: datetime.date | None = None,
    implements_note: str = "",
    last_verified_at: datetime.datetime | None = None,
    verified_by: User | None = None,
) -> Instrument:
    """An instrument titled by its short name in English, the original: Swedish unless
    `jurisdiction` names another jurisdiction by key, such as a Danish, a Norwegian or a
    Union one. `regime` is a `regime:<key>` term and required, as the database requires it
    (D-39)."""
    with library_write(REASON):
        row = Instrument.objects.create(
            stable_key=key,
            short_name=short_name or key.upper(),
            official_ref=key.upper(),
            eli_uri=eli_uri,
            source_url=SOURCE_URL,
            level=InstrumentLevel.objects.get(key=level),
            binding=binding,
            jurisdiction=Jurisdiction.objects.get(key=jurisdiction),
            authority=Authority.objects.get(key=authority) if authority else None,
            regime=term(regime),
            in_force_from=in_force_from,
            in_force_from_precision=in_force_from_precision,
            in_force_to=in_force_to,
            implements_note=implements_note,
            owner_tenant=owner_tenant,
            created_origin=OriginType.USER.value,
            last_verified_at=last_verified_at,
            verified_by=verified_by,
        )
        InstrumentTitle.objects.create(instrument=row, language_id="en", text=row.short_name, is_original=True)
    return row


def relate_instruments(
    source: Instrument, target: Instrument, *, relation: str, note: str = "", from_ref: str = "", to_ref: str = ""
) -> InstrumentRelation:
    """Files `target` beside `source` (INV-01): `source` "implements", "elaborates" or
    "amends" `target`, the direction the fixture and the lineage read both use. `from_ref`
    is the place in `source` that does it and `to_ref` the place in `target` it reaches."""
    with library_write(REASON):
        return InstrumentRelation.objects.create(
            from_instrument=source,
            to_instrument=target,
            relation_type=RelationType.objects.get(key=relation),
            note=note,
            from_ref=from_ref,
            to_ref=to_ref,
        )


def provision(on: Instrument, *, key: str, ref_label: str = "9 kap.", kind: str = "chapter", parent: Provision | None = None, heading: str = "", sort_order: int = 0) -> Provision:
    """A node of an instrument's tree, which an obligation cites and which carries its own
    verbatim text versions (`provision_version()` below), never an obligation's."""
    with library_write(REASON):
        return Provision.objects.create(
            stable_key=key,
            instrument=on,
            parent=parent,
            kind=ProvisionKind.objects.get(key=kind),
            ref_label=ref_label,
            heading=heading,
            path=f"{parent.path} > {ref_label}" if parent else f"{on.short_name} > {ref_label}",
            sort_order=sort_order,
        )


def provision_version(
    on: Provision,
    *,
    version_no: int = 1,
    effective_from: datetime.date | None = None,
    transitional_note: str = "",
    texts: Mapping[str, str] | None = None,
) -> ProvisionVersion:
    """A verbatim text version of `on` (INV-02): write-once, like an obligation's version.
    The first language given is the original; every other one is a machine translation."""
    with library_write(REASON):
        version = ProvisionVersion.objects.create(
            provision=on, version_number=version_no, effective_from=effective_from, transitional_note=transitional_note
        )
        for index, (language, text) in enumerate((texts or {"en": "The provision as it reads."}).items()):
            ProvisionText.objects.create(version=version, language_id=language, text=text, is_original=index == 0, is_machine=index > 0)
    return version


def relate(source: Obligation, target: Obligation, *, relation: str = "related") -> None:
    """Files `target` beside `source`, the direction the fixture writes a relation in."""
    with library_write(REASON):
        ObligationRelation.objects.create(
            from_obligation=source, to_obligation=target, relation_type=RelationType.objects.get(key=relation)
        )


def _texts(model: type[ObligationTitle] | type[ObligationSummary], parent: str, row: object, texts: Mapping[str, str]) -> None:
    """The first language is the original; every other one is a machine translation
    until a person confirms it (INV-05), as the seeded library has them."""
    for index, (language, text) in enumerate(texts.items()):
        model.objects.create(**{parent: row}, language_id=language, text=text, is_original=index == 0, is_machine=index > 0)


def obligation(
    on: Instrument,
    *,
    key: str,
    titles: Mapping[str, str] | None = None,
    ref_label: str = "1 §",
    duty_type: str = "conduct",
    terms: Iterable[str] = (),
    tags: Iterable[str] = (),
    cites: Iterable[Provision] = (),
    versions: Iterable[tuple[datetime.date | None, Mapping[str, str]]] = DEFAULT_VERSIONS,
    owner_tenant: Tenant | None = None,
    last_verified_at: datetime.datetime | None = None,
    product_scope: str = "",
    trigger_frequency: str = "",
    retention: str = "",
    sanction_exposure: str = "",
) -> Obligation:
    """An obligation of `on`. `versions` are `(effective_from, {language: summary})` in
    version order, numbered from 1; a null date means since always."""
    with library_write(REASON):
        row = Obligation.objects.create(
            stable_key=key,
            instrument=on,
            ref_label=ref_label,
            duty_type=DutyType.objects.get(key=duty_type),
            product_scope=product_scope,
            trigger_frequency=trigger_frequency,
            retention=retention,
            sanction_exposure=sanction_exposure,
            owner_tenant=owner_tenant,
            created_origin=OriginType.USER.value,
            source_url=SOURCE_URL,
            source_label=f"{on.official_ref}, {ref_label}",
            last_verified_at=last_verified_at,
        )
        _texts(ObligationTitle, "obligation", row, titles or {"en": key})
        for ref in terms:
            ObligationTerm.objects.create(obligation=row, term=term(ref))
        for tag in tags:
            ObligationTag.objects.create(obligation=row, tag=LibraryTag.objects.get(key=tag))
        for cited in cites:
            ObligationProvision.objects.create(obligation=row, provision=cited)
        for number, (effective_from, summaries) in enumerate(versions, start=1):
            version = ObligationVersion.objects.create(obligation=row, version_number=number, effective_from=effective_from)
            _texts(ObligationSummary, "version", version, summaries)
    return row


# The shape of a heavy page: two services, two account types, a client category, a channel
# and a lifecycle stage per obligation, two tags, sv titles with en machine translations,
# and every third obligation with a second version to come.
_REGIMES = ("regime:securities", "regime:insurance", "regime:tax", "regime:aml", "regime:data_protection")
_SERVICES = ("advice", "non_advised", "execution_only", "portfolio_management", "custody", "insurance_distribution")
_ACCOUNTS = ("isk", "af", "depa", "kf", "pension")
_STAGES = ("pre_trade", "post_trade", "ongoing", "product_lifecycle", "reporting", "onboarding")
_TAGS = ("advice", "appropriateness", "costs", "disclosure", "knowledge", "suitability", "warning")
_DUTIES = ("conduct", "disclosure", "record_keeping", "reporting", "governance")


def library_of(count: int) -> list[Obligation]:
    """`count` obligations spread over five instruments, each as heavy as the seeded
    library's heaviest rows: for the list read's performance guard."""
    instruments = [instrument(key=f"bulk-{index}", regime=regime) for index, regime in enumerate(_REGIMES)]
    return [
        obligation(
            instruments[n % len(instruments)],
            key=f"obl-bulk-{n:03d}",
            titles={"sv": f"Skyldighet {n} om kundskydd", "en": f"Duty {n} on client protection"},
            ref_label=f"{n % 12 + 1} kap.",
            duty_type=_DUTIES[n % len(_DUTIES)],
            terms=(
                f"service_type:{_SERVICES[n % 6]}",
                f"service_type:{_SERVICES[(n + 1) % 6]}",
                f"account_type:{_ACCOUNTS[n % 5]}",
                f"account_type:{_ACCOUNTS[(n + 2) % 5]}",
                f"client_category:{('retail', 'professional')[n % 2]}",
                f"channel:{('digital', 'branch')[n % 2]}",
                f"lifecycle_stage:{_STAGES[n % 6]}",
            ),
            tags=(_TAGS[n % 7], _TAGS[(n + 3) % 7]),
            versions=((None, {"sv": f"Sammanfattning {n}.", "en": f"Summary {n}."}),)
            + (((datetime.date(2026, 10, 1), {"sv": f"Ny lydelse {n}.", "en": f"New wording {n}."}),) if n % 3 == 0 else ()),
        )
        for n in range(count)
    ]

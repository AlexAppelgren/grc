"""Watched markets (FP-04, D-27, D-30, D-31): a jurisdiction a tenant names because it
wants visibility into it without operating there. Watching hides nothing, so it is a
direct, audited write rather than a footprint change request: no preview, no second
person, no step-up (D-30).

A market's level is never stored, only computed (FP-S11): operating comes first — its
mirrored jurisdiction term (FP-S12) sits in the tenant's footprint — then watching, a row
here naming it, otherwise not followed. So a market watched before it started operating
reads as watched again the moment operating stops, and footprint approval never touches a
row here.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.library.models import Jurisdiction, JurisdictionKind, JurisdictionLabel
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.taxonomy.models import FootprintTerm, WatchedMarket
from apps.taxonomy.reading import Labels, label_of
from apps.taxonomy.schemas import MarketLevel, MarketRow, TermRef

SUBJECT_TYPE = "watched_market"

OPERATING: Final = "operating"
WATCHING: Final = "watching"
NOT_FOLLOWED: Final = "not_followed"


def _country(key: str) -> Jurisdiction:
    """Only a country can be watched: the union itself is not a market a bank watches, and
    an unknown or retired key is refused rather than silently ignored."""
    jurisdiction = Jurisdiction.objects.filter(key=key).first()  # ordering: key is unique, so there is at most one row
    if jurisdiction is None or not jurisdiction.active:
        raise ValidationError(f"{key!r} is not a known, active jurisdiction.", code="unknown_key")
    if jurisdiction.kind != JurisdictionKind.COUNTRY.value:
        raise ValidationError(f"{key!r} is not a country; only a country can be watched.", code="not_a_country")
    return jurisdiction


def _operating(tenant_id: uuid.UUID) -> set[uuid.UUID]:
    """The jurisdictions the tenant operates in: those whose mirrored term sits in its
    footprint, read through the term's own link to its jurisdiction (FP-S12, D-28), never
    through a dimension key or a term key that happens to match. One query for every
    country, so a market list never costs a query per row."""
    return set(
        FootprintTerm.objects.filter(tenant_id=tenant_id, term__jurisdiction__isnull=False).values_list("term__jurisdiction_id", flat=True)
    )


def level_of(jurisdiction_id: uuid.UUID, operating: set[uuid.UUID], watched: set[uuid.UUID]) -> MarketLevel:
    """Operating first (FP-S11, D-27, D-31): the jurisdiction's mirrored term sits in the
    tenant's footprint. Otherwise watching if a watch row names it, otherwise not followed."""
    if jurisdiction_id in operating:
        return OPERATING
    if jurisdiction_id in watched:
        return WATCHING
    return NOT_FOLLOWED


def markets_of(tenant_id: uuid.UUID, order: list[str]) -> list[MarketRow]:
    """Every active country's level for the footprint read (FP-04): one row per country, in
    jurisdiction sort order. Four queries however many countries there are: the operating
    jurisdictions, the watch rows, the countries and their labels, never one more per row."""
    operating = _operating(tenant_id)
    watched = set(WatchedMarket.objects.filter(tenant_id=tenant_id).values_list("jurisdiction_id", flat=True))
    countries = list(Jurisdiction.objects.filter(active=True, kind=JurisdictionKind.COUNTRY.value).order_by("sort_order", "key"))
    labels = Labels.for_rows(JurisdictionLabel, countries)
    return [
        MarketRow(
            jurisdiction=TermRef(
                key=jurisdiction.key,
                kind=jurisdiction.kind,
                label=label_of(labels.texts(jurisdiction.id), order, original=labels.original(jurisdiction.id), key=jurisdiction.key),
            ),
            level=level_of(jurisdiction.id, operating, watched),
        )
        for jurisdiction in countries
    ]


def row_for(tenant_id: uuid.UUID, jurisdiction: Jurisdiction, order: list[str]) -> MarketRow:
    """One country's row, for a watch or unwatch route's response: read fresh so it always
    reflects the write that just happened. `_country` has already refused anything that is
    not an active country, so the country is always in the list."""
    return next(row for row in markets_of(tenant_id, order) if row.jurisdiction.key == jurisdiction.key)


def watch(*, tenant: Tenant, actor: Actor, key: str, added_by: Any = None) -> Jurisdiction:
    """One audited write, keys only (FP-S10): no preview, no second person, no step-up.
    `watched_market_unique` decides a repeat watch rather than a check-then-insert race."""
    jurisdiction = _country(key)
    try:
        with transaction.atomic():
            row = WatchedMarket.objects.create(tenant=tenant, jurisdiction=jurisdiction, added_by=added_by)
    except IntegrityError as exc:
        diag = getattr(exc.__cause__, "diag", None)
        if getattr(diag, "constraint_name", None) != "watched_market_unique":
            raise
        raise ValidationError(f"{key!r} is already watched.", code="already_watching") from exc
    record(
        action="markets.watch_added",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=key,
        summary=f"Started watching {key}.",
        tenant_id=tenant.id,
        after={"jurisdiction": key},
    )
    return jurisdiction


def unwatch(*, tenant: Tenant, actor: Actor, key: str) -> Jurisdiction:
    """Stop watching. Operating markets are untouched by this: a market's level survives an
    unwatch exactly because it is computed, never stored (FP-S11)."""
    jurisdiction = _country(key)
    row = WatchedMarket.objects.filter(tenant=tenant, jurisdiction=jurisdiction).first()  # ordering: watched_market_unique, at most one row
    if row is None:
        raise ValidationError(f"{key!r} is not watched.", code="not_found")
    row_id = row.id
    row.delete()
    record(
        action="markets.watch_removed",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row_id,
        subject_title=key,
        summary=f"Stopped watching {key}.",
        tenant_id=tenant.id,
        before={"jurisdiction": key},
    )
    return jurisdiction

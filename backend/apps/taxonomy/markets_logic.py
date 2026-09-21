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
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.library.models import Jurisdiction, JurisdictionKind, JurisdictionLabel
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.taxonomy import matching
from apps.taxonomy.models import WatchedMarket
from apps.taxonomy.reading import Labels, label_of
from apps.taxonomy.schemas import MarketRow, TermRef

JURISDICTION_DIMENSION = "jurisdiction"
SUBJECT_TYPE = "watched_market"

OPERATING = "operating"
WATCHING = "watching"
NOT_FOLLOWED = "not_followed"


def _country(key: str) -> Jurisdiction:
    """Only a country can be watched: the union itself is not a market a bank watches, and
    an unknown or retired key is refused rather than silently ignored."""
    jurisdiction = Jurisdiction.objects.filter(key=key).first()  # ordering: key is unique, so there is at most one row
    if jurisdiction is None or not jurisdiction.active:
        raise ValidationError(f"{key!r} is not a known, active jurisdiction.", code="unknown_key")
    if jurisdiction.kind != JurisdictionKind.COUNTRY.value:
        raise ValidationError(f"{key!r} is not a country; only a country can be watched.", code="not_a_country")
    return jurisdiction


def _operating(jurisdiction: Jurisdiction, footprint: dict[str, set[str]]) -> bool:
    # The mirrored jurisdiction term's key is always the jurisdiction's own key (FP-S12),
    # so this needs no query of its own: one footprint read already carries the answer for
    # every country, which is what keeps a market list from costing a query per row.
    return jurisdiction.key in footprint.get(JURISDICTION_DIMENSION, set())


def level_of(tenant_id: uuid.UUID, jurisdiction: Jurisdiction, footprint: dict[str, set[str]] | None = None) -> str:
    """Operating first (FP-S11): the jurisdiction's mirrored term sits in the tenant's
    footprint. Otherwise watching if a row here names it, otherwise not followed. `footprint`
    lets a caller listing many markets pass one read of `matching.footprint_of` in."""
    footprint = matching.footprint_of(tenant_id) if footprint is None else footprint
    if _operating(jurisdiction, footprint):
        return OPERATING
    if WatchedMarket.objects.filter(tenant_id=tenant_id, jurisdiction=jurisdiction).exists():
        return WATCHING
    return NOT_FOLLOWED


def markets_of(tenant_id: uuid.UUID, order: list[str]) -> list[MarketRow]:
    """Every active country's level for the footprint read (FP-04): one row per country, in
    jurisdiction sort order. Four queries however many countries there are: the footprint,
    the watch rows, the countries and their labels, never one more per row."""
    footprint = matching.footprint_of(tenant_id)
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
            operating=_operating(jurisdiction, footprint),
            watching=jurisdiction.id in watched,
        )
        for jurisdiction in countries
    ]


def row_for(tenant_id: uuid.UUID, jurisdiction: Jurisdiction, order: list[str]) -> MarketRow:
    """One country's row, for a watch or unwatch route's response: read fresh so it always
    reflects the write that just happened."""
    labels = Labels.for_rows(JurisdictionLabel, [jurisdiction])
    footprint = matching.footprint_of(tenant_id)
    return MarketRow(
        jurisdiction=TermRef(
            key=jurisdiction.key,
            kind=jurisdiction.kind,
            label=label_of(labels.texts(jurisdiction.id), order, original=labels.original(jurisdiction.id), key=jurisdiction.key),
        ),
        operating=_operating(jurisdiction, footprint),
        watching=WatchedMarket.objects.filter(tenant_id=tenant_id, jurisdiction=jurisdiction).exists(),
    )


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

"""What changed in the shared library since a bank last looked (PRO-03, INV-04, FP-03).

A bank does not read the queue: the queue is the platform's, and a proposal is a request
somebody made, not a fact. What a bank reads is the other end of it — the changes that were
approved and applied — and it reads them as the library's own facts:

- Every item is titled by the library record it touched, never by the proposal that carried
  it, so one bank's wording can never reach another bank as a heading.
- No person as proposer or reviewer, and no note: who asked for a change is nobody's
  business outside the console, and a bank that filed one reads its own request through
  `GET /tenant/proposals` instead. The platform agents that proposed or confirmed it are
  named by definition key (INV-05, D-62), read from the proposal itself, so a change an
  independent agent confirmed never reads as a person's approval, whatever kind it is.
- The cut to the bank's own business is `taxonomy.matching`, the one footprint rule, applied
  in the database by the same SQL function the inventory list uses, so a duty hidden from
  the inventory is hidden here too. A change to a shared list is never cut: a list belongs
  to every bank and to no footprint.

Days are the bank's own days: a change applied at 23:40 UTC is filed under the next day for
a bank in Stockholm, because that is the day its people will say it arrived.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, cast
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import BooleanField, Exists, Func, OuterRef, Q, QuerySet, UUIDField, Value
from django.utils import timezone

from apps.library.models import Obligation, ObligationVersion
from apps.library.reading import (
    RecordHeading,
    agent_ref,
    footprint_dimensions,
    obligation_headings,
    obligation_scopes,
    outside_reasons,
    partial_date,
    vocabulary_refs,
)
from apps.library.schemas import LibraryRef, OutsideReason
from apps.proposals import logic
from apps.proposals.models import OriginType, Proposal, ProposalKind, ProposalStatus
from apps.proposals.schemas import LibraryUpdateDay, LibraryUpdateRow, LibraryUpdatesPage, LibraryUpdateTarget
from apps.taxonomy import matching
from apps.taxonomy.models import TaxonomyTerm, TaxonomyTermLabel


def since_for(tenant: Any, membership: Any) -> datetime.datetime:
    """Where the list starts: the reader's own bookmark, or `LIBRARY_UPDATES_DEFAULT_DAYS`
    back for somebody who has never marked the library as seen, so a first visit shows
    something rather than nothing."""
    if membership is not None and membership.last_visit_at is not None:
        return membership.last_visit_at
    return timezone.now() - datetime.timedelta(days=settings.LIBRARY_UPDATES_DEFAULT_DAYS)


def _applied(*, since: datetime.datetime, kind: str | None, outside_footprint: bool, tenant_id: uuid.UUID) -> QuerySet[Proposal]:
    """The changes applied since `since`, newest first, cut to the footprint in the database
    rather than in Python: a duty the footprint hides is not counted, not only unprinted. A
    change to a shared list carries no target and is never cut, and neither is a new
    instrument or a provision, a record of the library rather than a duty. A new obligation has
    no target either, since it did not exist when it was proposed: it is cut through the
    first version its approval wrote."""
    from apps.library.reading import scope_term_ids

    queryset = logic.filtered(Proposal.objects.all(), status=ProposalStatus.APPROVED.value, kind=kind).filter(applied_at__gte=since)
    if not outside_footprint:
        inside = Obligation.objects.filter(
            Func(Value(tenant_id, output_field=UUIDField()), scope_term_ids(), function=matching.SQL_FUNCTION, output_field=BooleanField())
        )
        created_inside = Exists(ObligationVersion.objects.filter(applied_by_proposal=OuterRef("pk"), obligation__in=inside))
        new_obligation = Q(kind=ProposalKind.NEW_OBLIGATION.value)
        queryset = queryset.filter(
            (~Q(target_type=logic.OBLIGATION_TARGET) & ~new_obligation)
            | Q(target_id__in=inside.values("id"))
            | (new_obligation & created_inside),
        )
    return queryset.order_by("-applied_at", "-id")


def _versions(proposals: list[Proposal]) -> dict[uuid.UUID, ObligationVersion]:
    """The version each approval wrote, for the whole page in one query. Every row here was
    filed by one of these proposals, which is what the filter selects on."""
    return {
        cast(uuid.UUID, version.applied_by_proposal_id): version
        for version in ObligationVersion.objects.filter(applied_by_proposal__in=proposals)
    }


def _vocabulary_refs(proposals: list[Proposal], order: list[str]) -> dict[uuid.UUID, LibraryRef]:
    """The list row each vocabulary change touched, labelled as that row is labelled today
    (PRO-03): the library's own word for it, never the wording of the request that changed
    it, so a change one bank asked for reads to every other bank as the library reads. Two
    queries per list on the page, and none that grows with the number of changes."""
    from apps.taxonomy.registry import REGISTRY

    wanted: dict[str, dict[uuid.UUID, str]] = {}
    for proposal in proposals:
        payload = proposal.corrected_payload or proposal.payload
        name, key = payload.get("list") or payload.get("dimension"), payload.get("key")
        if proposal.target_id is None and name and key:
            wanted.setdefault(name, {})[proposal.id] = key
    refs: dict[uuid.UUID, LibraryRef] = {}
    for name, by_proposal in wanted.items():
        entry = REGISTRY.get(name)
        if entry is not None:
            rows = list(entry.model.objects.filter(key__in=set(by_proposal.values())))
            labelled = vocabulary_refs(entry.label_model, rows, order)
        else:
            # A taxonomy dimension rather than a list: the row is a term of that dimension.
            rows = list(TaxonomyTerm.objects.filter(dimension__key=name, key__in=set(by_proposal.values())))
            labelled = vocabulary_refs(TaxonomyTermLabel, rows, order, field="term")
        # Assigned one by one rather than merged with dict.update(): the library fence's
        # static guard reads a call to .update() as a write, and this module names library
        # models to read them (apps/shared/tests_library_fence.py).
        by_key = {row.key: labelled[row.id] for row in rows}
        for proposal_id, key in by_proposal.items():
            if key in by_key:
                refs[proposal_id] = by_key[key]
    return refs


def _duties(proposals: list[Proposal], versions: dict[uuid.UUID, ObligationVersion]) -> dict[uuid.UUID, uuid.UUID]:
    """The duty each change touched, by proposal: its target, or for a new obligation the
    record its approval created, read through the first version it wrote."""
    duties = {
        proposal.id: proposal.target_id
        for proposal in proposals
        if proposal.target_id is not None and proposal.target_type == logic.OBLIGATION_TARGET
    }
    for proposal in proposals:
        if proposal.kind == ProposalKind.NEW_OBLIGATION.value and proposal.id in versions:
            duties[proposal.id] = versions[proposal.id].obligation_id
    return duties


def _verdicts(
    targets: list[uuid.UUID], order: list[str], tenant_id: uuid.UUID
) -> dict[uuid.UUID, tuple[bool, list[OutsideReason]]]:
    """Whether each changed duty reaches this bank, and the facets that would hide it. The
    same rule and the same wording as the inventory list, for the whole page at once."""
    if not targets:
        return {}
    scopes = obligation_scopes(targets)
    footprint = matching.footprint_of(tenant_id)
    restricting = matching.restricting_dimensions()
    dimensions = footprint_dimensions(order)
    term_refs: dict[uuid.UUID, LibraryRef] = vocabulary_refs(
        TaxonomyTermLabel, (term for scope in scopes.values() for terms in scope.values() for term in terms), order, field="term"
    )
    verdicts = {}
    for obligation_id in targets:
        scope = scopes.get(obligation_id, {})
        outside = outside_reasons({key: {term.key for term in terms} for key, terms in scope.items()}, footprint, restricting)
        verdicts[obligation_id] = (
            not outside,
            [OutsideReason(dimension=dimensions[key][0], terms=[term_refs[term.id] for term in scope[key]]) for key in outside],
        )
    return verdicts


def _row(
    proposal: Proposal,
    *,
    duty: uuid.UUID | None,
    heading: RecordHeading | None,
    version: ObligationVersion | None,
    vocabulary: LibraryRef | None,
    verdict: tuple[bool, list[OutsideReason]],
) -> LibraryUpdateRow:
    in_footprint, outside = verdict
    target = None
    if duty is not None and heading is not None:
        target = LibraryUpdateTarget(
            id=duty,
            title=heading.title,
            reference_label=heading.reference_label,
            instrument_short_name=heading.instrument_short_name,
        )
    applied = proposal.payload if proposal.corrected_payload is None else proposal.corrected_payload
    return LibraryUpdateRow(
        id=proposal.id,
        kind=proposal.kind,
        # Applied: the queryset selects on the moment it was applied, so every row has one.
        applied_at=cast(datetime.datetime, proposal.applied_at),
        effective_from=None if version is None else partial_date(version.effective_from, version.effective_from_precision),
        version_number=None if version is None else version.version_number,
        target=target,
        # Which list changed, and the row itself as that list labels it today.
        vocabulary_list=(applied.get("list") or applied.get("dimension")) if duty is None else None,
        vocabulary=vocabulary,
        in_footprint=in_footprint,
        outside_reason=outside,
        verified_origin=(OriginType.AGENT if proposal.reviewed_by_agent_id is not None else OriginType.USER).value,
        confirmed_by_agent=agent_ref(proposal.reviewed_by_agent),
        proposed_by_agent=agent_ref(proposal.proposed_by_agent),
    )


def page(
    tenant: Any,
    order: list[str],
    membership: Any,
    *,
    kind: str | None,
    outside_footprint: bool,
    limit: int,
    offset: int,
) -> LibraryUpdatesPage:
    """What changed since this reader's bookmark, grouped by the bank's own day, newest
    first. The same number of queries whatever the page holds (playbook 10)."""
    since = since_for(tenant, membership)
    queryset = _applied(since=since, kind=kind, outside_footprint=outside_footprint, tenant_id=tenant.id)
    total = queryset.count()
    applied = list(queryset.select_related("proposed_by_agent", "reviewed_by_agent")[offset : offset + limit])
    versions = _versions(applied)
    duties = _duties(applied, versions)
    headings = obligation_headings(list(duties.values()), order)
    vocabularies = _vocabulary_refs(applied, order)
    verdicts = _verdicts(list(duties.values()), order, tenant.id)
    zone = ZoneInfo(tenant.timezone)
    days: list[LibraryUpdateDay] = []
    for proposal in applied:
        duty = duties.get(proposal.id)
        row = _row(
            proposal,
            duty=duty,
            heading=None if duty is None else headings.get(duty),
            version=versions.get(proposal.id),
            vocabulary=vocabularies.get(proposal.id),
            verdict=(True, []) if duty is None else verdicts.get(duty, (True, [])),
        )
        day = timezone.localdate(cast(datetime.datetime, proposal.applied_at), timezone=zone)
        if not days or days[-1].date != day:
            days.append(LibraryUpdateDay(date=day, items=[]))
        days[-1].items.append(row)
    return LibraryUpdatesPage(since=since, days=days, total=total)

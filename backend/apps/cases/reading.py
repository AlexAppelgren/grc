"""What a case needs to know about a library change, read in the library's zone (CAS-01).

Reads only: the library fence refuses a module that both names a library record and writes
(`tests_library_fence.py`), so `creation.py` writes and the reads live here. `ChangeFacts` is
everything that crosses into a bank's case: five facts.

A change's scope is its own terms plus the jurisdictions its authority reaches, derived at
match time and never stored (FP-04, D-28, D-29). A change with no authority is not
restricted by jurisdiction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.contrib.postgres.expressions import ArraySubquery
from django.contrib.postgres.fields import ArrayField
from django.db.models import Func, OuterRef, Subquery, UUIDField

from apps.cases.models import ChangeCase
from apps.library.models import Obligation, RecordStatus
from apps.library.reading import jurisdiction_scopes, localized, reaching
from apps.taxonomy.models import CaseStatusCategory, TaxonomyTerm, Urgency
from apps.watch.models import ChangeTerm, RegulatoryChange

# Dimension key -> the term keys the change carries in it, as the scope rule reads it.
Scope = dict[str, set[str]]


@dataclass(frozen=True)
class ChangeFacts:
    """What one registered change puts into every bank's case."""

    id: uuid.UUID
    title: str
    scope: Scope
    urgency_id: uuid.UUID
    so_what_draft: str


def change_facts(change_id: uuid.UUID) -> ChangeFacts | None:
    """The facts of the change with this id, or None when there is no such change."""
    change = (
        RegulatoryChange.objects.select_related("suggested_urgency", "authority")
        .filter(pk=change_id)
        .first()  # ordering: pk lookup, at most one row
    )
    if change is None:
        return None
    return ChangeFacts(
        id=change.id,
        title=change.title,
        scope=_scope_of(change),
        urgency_id=_urgency_for(change).id,
        so_what_draft=change.so_what_draft,
    )


def _scope_of(change: RegulatoryChange) -> Scope:
    """The change's scope as the rule reads it: terms by dimension plus the jurisdictions its
    authority reaches. A flag never scopes a change (WAT-03). An empty scope falls inside
    every footprint."""
    scope: Scope = {}
    for link in change.term_links.filter(term__isnull=False).select_related("term__dimension"):
        term = link.term
        if term is not None:  # the filter said so; the column is nullable because a flag row carries no term
            scope.setdefault(term.dimension.key, set()).add(term.key)
    if change.authority is not None:
        for term in jurisdiction_scopes([change.authority.jurisdiction_id]).get(change.authority.jurisdiction_id, []):
            scope.setdefault(term.dimension.key, set()).add(term.key)
    return scope


def _urgency_for(change: RegulatoryChange) -> Urgency:
    """The agent's suggestion, or the urgency list's default row. `change_case.urgency` is
    NOT NULL; `urgency_confirmed` stays false either way."""
    if change.suggested_urgency is not None:
        return change.suggested_urgency
    default = Urgency.objects.filter(is_default=True).first()  # ordering: Meta.ordering, ordinal first
    if default is None:  # pragma: no cover - the vocabulary guard demands a default per list
        raise RuntimeError(
            "The urgency list has no default row, so a new case has no urgency to start from. "
            "Run the reference seed (apps/shared/tests_vocabulary_integrity.py)."
        )
    return default


@dataclass(frozen=True)
class ObligationDetails:
    """What a case's own link decision shows about the obligation it names: three library
    facts and nothing more. A case never carries a copy of an obligation."""

    title: str
    instrument_short_name: str
    ref_label: str


def obligation_details(obligation_id: uuid.UUID, order: list[str]) -> ObligationDetails | None:
    """The three facts `links.py` renders, or None for an unknown or inactive obligation.
    Here because `links.py` writes (library fence); None, because the caller's 404 must look
    the same for an unknown id and a hidden one (playbook 4.4).
    """
    obligation = (
        Obligation.objects.select_related("instrument")
        .prefetch_related("titles")
        .filter(pk=obligation_id, status=RecordStatus.ACTIVE.value)
        .first()  # ordering: pk lookup, at most one row
    )
    if obligation is None:
        return None
    title = localized(obligation.titles.all(), order)
    return ObligationDetails(
        title=obligation.stable_key if title is None else title.text,
        instrument_short_name=obligation.instrument.short_name,
        ref_label=obligation.ref_label,
    )


def scope_term_ids_of_each_case() -> Func:
    """The scope term ids of each case's change as one `uuid[]`, correlated on `change_id`,
    so one statement decides a page of cases (`matching.py`): own terms plus the
    jurisdictions its authority reaches; a flag never scopes (WAT-03). No join leaves the case
    row, because the recomputation is an UPDATE.
    """
    own = ArraySubquery(
        ChangeTerm.objects.filter(change=OuterRef("change_id"), term__isnull=False).order_by().values("term_id"),
        output_field=ArrayField(UUIDField()),
    )
    jurisdiction = Subquery(
        RegulatoryChange.objects.filter(pk=OuterRef(OuterRef("change_id"))).values("authority__jurisdiction_id")[:1]
    )
    reached = ArraySubquery(
        TaxonomyTerm.objects.filter(reaching(jurisdiction)).order_by().values("id"), output_field=ArrayField(UUIDField())
    )
    return Func(own, reached, function="array_cat", output_field=ArrayField(UUIDField()))


def open_case_scopes(tenant_id: uuid.UUID) -> list[Scope]:
    """The scope of each open case's change, one entry per case, for the scope change preview
    (AC-FP1), which decides in Python with the same rule because it asks about a footprint
    not yet stored. Two queries; finished cases are not counted; a flag never scopes (WAT-03).
    """
    rows = (
        ChangeCase.objects.filter(tenant_id=tenant_id)
        .exclude(status__in=(CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value))
        .order_by()
        .values_list(
            "id",
            "change__authority__jurisdiction_id",
            "change__term_links__term__dimension__key",
            "change__term_links__term__key",
        )
    )
    scopes: dict[uuid.UUID, Scope] = {}
    jurisdictions: dict[uuid.UUID, uuid.UUID] = {}
    for case_id, jurisdiction_id, dimension, key in rows:
        scope = scopes.setdefault(case_id, {})
        if jurisdiction_id is not None:
            jurisdictions[case_id] = jurisdiction_id
        if key is not None:
            scope.setdefault(dimension, set()).add(key)
    reached = jurisdiction_scopes(set(jurisdictions.values()))
    for case_id, jurisdiction_id in jurisdictions.items():
        for term in reached.get(jurisdiction_id, []):
            scopes[case_id].setdefault(term.dimension.key, set()).add(term.key)
    return list(scopes.values())

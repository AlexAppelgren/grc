"""What a case needs to know about a library change, read in the library's zone (CAS-01).

Everything here reads and nothing writes, which is the point of the module. The library
fence refuses any production module that both names a library record and calls a write
(`apps/shared/tests_library_fence.py`), because that is how a library write gets smuggled
in beside the proposal door. So `creation.py` writes and never names a library record, and
the reads live here — the same split `apps/library/reading.py` makes for the proposals app.

`ChangeFacts` is also the honest statement of what crosses the boundary between the two
zones: five facts, and nothing else of the library travels into a bank's case.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.contrib.postgres.expressions import ArraySubquery
from django.contrib.postgres.fields import ArrayField
from django.db.models import OuterRef, UUIDField

from apps.cases.models import ChangeCase
from apps.library.models import Obligation, RecordStatus
from apps.library.reading import localized
from apps.taxonomy.models import CaseStatusCategory, Urgency
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
        RegulatoryChange.objects.select_related("suggested_urgency")
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
    """The change's scope as the rule reads it: its taxonomy terms by dimension. A flag is a
    `change_term` row too and is never a scope term — it describes the change, it does not
    say who it reaches (WAT-03). A change with no terms has an empty scope and so falls
    inside every bank's footprint."""
    scope: Scope = {}
    for link in change.term_links.filter(term__isnull=False).select_related("term__dimension"):
        term = link.term
        if term is not None:  # the filter said so; the column is nullable because a flag row carries no term
            scope.setdefault(term.dimension.key, set()).add(term.key)
    return scope


def _urgency_for(change: RegulatoryChange) -> Urgency:
    """The agent's suggestion, or the urgency list's own default row when the change carries
    none. `change_case.urgency` is NOT NULL and the case exists from the moment the change
    does, so a bank always has something to triage from; `urgency_confirmed` stays false
    either way, so neither reads as a person's decision."""
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
    """The three facts `apps/cases/links.py` renders, or None when the library holds no
    active obligation with that id.

    It lives here for the same reason `change_facts` does: `links.py` writes, so it may not
    name a library record at all (the AST half of the library fence). None rather than a
    refusal, because the caller answers 404 and an unknown id must look exactly like an id
    belonging to a record the reader may not see (playbook 4.4).
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


def scope_term_ids_of_each_case() -> ArraySubquery:
    """The scope term ids of each case's change as one `uuid[]`, for the database's own
    footprint function, correlated on `change_id` so one statement decides a whole page of
    cases (`apps/cases/matching.py`).

    A flag is a `change_term` row too and never scopes a change: it says what the reform is
    about, not who it reaches (WAT-03). It lives here rather than beside the statement that
    uses it because that module writes, and a module that writes names no library record.
    """
    return ArraySubquery(
        ChangeTerm.objects.filter(change=OuterRef("change_id"), term__isnull=False).order_by().values("term_id"),
        output_field=ArrayField(UUIDField()),
    )


def open_case_scopes(tenant_id: uuid.UUID) -> list[Scope]:
    """The scope of each open case's change in this bank, one entry per case, for the scope
    change preview (AC-FP1). The SQL function reads the stored footprint and the preview asks
    about one that does not exist yet, so the preview decides in Python with the same rule.

    One query for any number of cases: a row per case and change term, and one row with no
    term for a change that carries none. A closed or dismissed case is finished work and is
    not counted, as the recomputation leaves it alone (`apps/cases/matching.py`). A flag is a
    `change_term` row with no term and never scopes a change (WAT-03).
    """
    rows = (
        ChangeCase.objects.filter(tenant_id=tenant_id)
        .exclude(status__in=(CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value))
        .order_by()
        .values_list("id", "change__term_links__term__dimension__key", "change__term_links__term__key")
    )
    scopes: dict[uuid.UUID, Scope] = {}
    for case_id, dimension, key in rows:
        scope = scopes.setdefault(case_id, {})
        if key is not None:
            scope.setdefault(dimension, set()).add(key)
    return list(scopes.values())

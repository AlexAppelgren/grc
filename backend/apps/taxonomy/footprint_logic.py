"""The footprint and its change requests (FP-01, FP-02, AC-FP1, J-6).

A footprint change has a wide blast radius: every feed, inventory, roadmap, briefing and
report is filtered by it (FP-03). So it is never a direct write. A requester creates a
`FootprintChangeRequest` with a preview of what the change would hide and reveal; a second
person approves it with a fresh passkey assertion; the approval switches the terms, writes
one audit event and one `footprint_history` row per term, in one transaction.

This module writes, so it names no library model class: the terms it adds and removes
arrive as rows from apps/taxonomy/terms_logic.py, and the read half of the footprint lives
there too. The library fence's AST guard refuses any module that both names a
`LibraryModel` and calls a write method (apps/shared/tests_library_fence.py).

The preview counts per record kind: the obligations this bank can see and its open cases,
each by the one scope rule (apps/taxonomy/matching.py). A count carries `available`, because
"not counted" and "none" are different answers and a screen that cannot tell them apart
would lie to the person deciding (playbook 4.4); both kinds are counted, so both say true.

A request may also add and remove scope items (OWN-01, D-89, D-91): regulations the shared
library does not cover, which the bank's own agent researches once a second person approved
them. An item rides on the same request, so the same one-waiting rule, four-eyes check and
passkey decide it, and only a person's session reaches it: no key and no agent path writes a
scope item (`tests_scope_items.NoOtherWriter`). An item is not a term: it moves no count in
the preview and FP-01's matching never reads it. Its approval writes a history row and one
`scope_item.added` or `scope_item.removed` audit and outbox row carrying ids and keys only,
which is what the research worker listens for; the name and description a person typed stay
on the item row (R2_CROSS_CUTTING rule m).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, prefetch_related_objects
from django.utils import timezone
from django.utils.text import slugify

from apps.cases import reading as case_reading
from apps.library import reading
from apps.library.models import Jurisdiction, JurisdictionLabel
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.taxonomy import markets_logic, matching, terms_logic
from apps.taxonomy.models import (
    ApprovalStatus,
    FootprintAction,
    FootprintChangeAdd,
    FootprintChangeRemove,
    FootprintChangeRequest,
    FootprintChangeScopeItem,
    FootprintHistory,
    FootprintTerm,
    ScopeItem,
    ScopeItemStatus,
    TermDimensionKind,
    validate_public_https_url,
    validate_scope_item_description,
)
from apps.taxonomy.reading import Labels, label_of
from apps.taxonomy.schemas import (
    FootprintDimension,
    FootprintDryRun,
    FootprintPreview,
    FootprintPreviewCount,
    FootprintRequestRow,
    FootprintView,
    PersonRef,
    ScopeItemInput,
    ScopeItemRow,
    TermRef,
)

SUBJECT_TYPE = "footprint"
REQUEST_SUBJECT_TYPE = "footprint_change_request"
SCOPE_ITEM_SUBJECT_TYPE = "scope_item"
# The dimension a scope item's regime term comes from (the model's `regime_term`).
REGIME_DIMENSION = "regime"
SCOPE_ITEM_KEY_MAX_CHARS = 80
# How a scope item's research stands (OWN-02). Until the bank's own agent opens research
# on an item (d89-agent-research), an item in scope waits for it.
WAITING_FOR_AGENT = "waiting_for_agent"


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def view(tenant_id: uuid.UUID, order: list[str]) -> FootprintView:
    """The footprint screen's data (FP-01): every dimension, the terms this company carries
    in it, whether it restricts the footprint at all, the pending request if one waits, and
    every active country's market level (FP-04). A dimension with no terms is not an error
    and not an omission: it means "no restriction", which the screen says in words
    (playbook 4.5), except in an opt-in dimension, whose kind the reference carries: there it
    means "none followed" (D-36). An opt-in dimension restricts whatever its flag says, so
    the read says so too, as the matcher does."""
    selected = terms_logic.selected_terms_by_dimension(tenant_id, order)
    dimensions: list[FootprintDimension] = []
    for ref, restricts, term_count in terms_logic.dimensions_for_footprint(order):
        terms: list[TermRef] = selected.get(ref.key, [])
        dimensions.append(
            FootprintDimension(
                dimension=ref,
                restricts_footprint=restricts or ref.kind == TermDimensionKind.OPT_IN.value,
                terms=terms,
                all_selected=bool(term_count) and len(terms) == term_count,
            )
        )
    return FootprintView(
        dimensions=dimensions,
        pending_request=pending_row(tenant_id, order),
        markets=markets_logic.markets_of(tenant_id, order),
        scope_items=scope_item_rows(
            list(_scope_items().filter(tenant_id=tenant_id, status=ScopeItemStatus.IN_SCOPE.value).order_by("created_at", "id")),
            order,
        ),
    )


def pending(tenant_id: uuid.UUID) -> FootprintChangeRequest | None:
    return (
        FootprintChangeRequest.objects.filter(tenant_id=tenant_id, status=ApprovalStatus.PENDING.value)
        .order_by("requested_at", "id")
        .first()
    )


def pending_row(tenant_id: uuid.UUID, order: list[str]) -> FootprintRequestRow | None:
    request = pending(tenant_id)
    return None if request is None else request_row(request, order)


def requests_of(
    tenant_id: uuid.UUID, order: list[str], *, limit: int, offset: int
) -> tuple[list[FootprintRequestRow], int]:
    """One page of the request history (FP-02, NFR-02), newest first, and how many requests
    there are in all. The id settles two requests sent in the same instant, so two reads
    always agree on the order."""
    found = FootprintChangeRequest.objects.filter(tenant_id=tenant_id)
    page = found.select_related("requested_by", "decided_by").order_by("-requested_at", "id")[offset : offset + limit]
    return request_rows(list(page), order), found.count()


def _person(user: Any) -> PersonRef | None:
    # A person's name and id may be logged and shown; nothing else about them (playbook 4.7).
    return None if user is None else PersonRef(id=user.id, name=user.name)


def request_row(request: FootprintChangeRequest, order: list[str]) -> FootprintRequestRow:
    return request_rows([request], order)[0]


def request_rows(requests: list[FootprintChangeRequest], order: list[str]) -> list[FootprintRequestRow]:
    """A page of requests costs the same few queries however many it holds: the terms of all
    of them with their dimensions in one read per side, and their labels in one."""
    changes = _changes_of(requests)
    terms = {term.id: term for adds, removes in changes for term in (*adds, *removes)}
    labelled = dict(zip(terms, terms_logic.labelled_term_refs(list(terms.values()), order), strict=True))
    item_changes = _scope_item_changes_of(requests)
    items = {item.id: item for adds, removes in item_changes for item in (*adds, *removes)}
    item_rows = dict(zip(items, scope_item_rows(list(items.values()), order), strict=True))
    return [
        FootprintRequestRow(
            id=request.id,
            status=request.status,
            requested_by=_person(request.requested_by),
            requested_at=request.requested_at,
            adds=[labelled[term.id] for term in adds],
            removes=[labelled[term.id] for term in removes],
            scope_item_adds=[item_rows[item.id] for item in item_adds],
            scope_item_removes=[item_rows[item.id] for item in item_removes],
            preview=_preview_now(request, adds, removes),
            decided_by=_person(request.decided_by),
            decided_at=request.decided_at,
            decision_note=request.decision_note,
            version=request.version,
        )
        for request, (adds, removes), (item_adds, item_removes) in zip(requests, changes, item_changes, strict=True)
    ]


# ---------------------------------------------------------------------------------------
# Scope items (OWN-01, D-91)
# ---------------------------------------------------------------------------------------
def _scope_items() -> Any:
    return ScopeItem.objects.select_related("jurisdiction", "regime_term__dimension")


def scope_item(tenant_id: uuid.UUID, item_id: uuid.UUID) -> ScopeItem:
    """One of this bank's scope items, under row-level security and by its id; another
    bank's answers 404 exactly as one that does not exist."""
    found: ScopeItem | None = _scope_items().filter(tenant_id=tenant_id, pk=item_id).first()  # ordering: pk lookup, at most one row
    if found is None:
        raise ValidationError("That scope item is not here.", code="not_found")
    return found


def _research(item: ScopeItem) -> str | None:
    return WAITING_FOR_AGENT if item.status == ScopeItemStatus.IN_SCOPE.value else None


def scope_item_rows(items: list[ScopeItem], order: list[str]) -> list[ScopeItemRow]:
    """Scope items as the screen reads them, labelled in two queries however many there
    are: the jurisdictions' labels and the regime terms' labels."""
    jurisdictions = list({item.jurisdiction_id: item.jurisdiction for item in items}.values())
    labels = Labels.for_rows(JurisdictionLabel, jurisdictions)
    terms = list({item.regime_term_id: item.regime_term for item in items}.values())
    regimes = dict(zip((term.id for term in terms), terms_logic.labelled_term_refs(terms, order), strict=True))
    return [
        ScopeItemRow(
            id=None if item._state.adding else item.id,
            key=item.key,
            name=item.name,
            description=item.description,
            jurisdiction=TermRef(
                key=item.jurisdiction.key,
                kind=item.jurisdiction.kind,
                label=label_of(
                    labels.texts(item.jurisdiction_id),
                    order,
                    original=labels.original(item.jurisdiction_id),
                    key=item.jurisdiction.key,
                ),
            ),
            regime_term=regimes[item.regime_term_id],
            official_reference=item.official_reference,
            source_url=item.source_url,
            status=item.status,
            research=_research(item),
        )
        for item in items
    ]


def _scope_item_changes_of(requests: list[FootprintChangeRequest]) -> list[tuple[list[ScopeItem], list[ScopeItem]]]:
    """The scope items each request adds and removes, in one query for any number of
    requests, in the order they were asked for."""
    prefetch_related_objects(
        requests,
        Prefetch(
            "scope_item_links",
            FootprintChangeScopeItem.objects.select_related(
                "scope_item__jurisdiction", "scope_item__regime_term__dimension"
            ).order_by("created_at", "id"),
        ),
    )
    changes = []
    for request in requests:
        links = list(request.scope_item_links.all())
        changes.append(
            (
                [link.scope_item for link in links if link.action == FootprintAction.ADDED.value],
                [link.scope_item for link in links if link.action == FootprintAction.REMOVED.value],
            )
        )
    return changes


def _jurisdiction(key: str) -> Jurisdiction:
    found = Jurisdiction.objects.filter(key=key, active=True).first()  # ordering: key is unique, so there is at most one row
    if found is None:
        valid = ", ".join(Jurisdiction.objects.filter(active=True).order_by("sort_order", "key").values_list("key", flat=True))
        raise ValidationError(f"{key!r} is not an active jurisdiction. Valid keys: {valid}.", code="unknown_key")
    return found


def _key_base(name: str) -> str:
    return slugify(name).replace("-", "_")[:SCOPE_ITEM_KEY_MAX_CHARS].rstrip("_") or SCOPE_ITEM_SUBJECT_TYPE


def scope_item_drafts(tenant_id: uuid.UUID, inputs: list[ScopeItemInput]) -> list[ScopeItem]:
    """The items a request would add, validated and keyed but not stored (OWN-01): the
    jurisdiction and the regime term by key, the address as a public https page, the
    description within its cap. A key is derived from the name and never reused, a declined
    or removed item's included (playbook 4.3), so a taken one gets `_2`, `_3` and so on."""
    drafts: list[ScopeItem] = []
    bases = {_key_base(entry.name) for entry in inputs}
    taken = set(
        ScopeItem.objects.filter(tenant_id=tenant_id, key__regex=r"^(" + "|".join(bases) + r")(_[0-9]+)?$").values_list("key", flat=True)
    ) if bases else set()
    for entry in inputs:
        try:
            validate_public_https_url(entry.source_url)
        except ValidationError as exc:
            raise ValidationError(
                "sourceUrl: give the address of a public https page.", code="source_not_public"
            ) from exc
        validate_scope_item_description(entry.description)
        base = _key_base(entry.name)
        key, number = base, 1
        while key in taken:
            number += 1
            suffix = f"_{number}"
            key = base[: SCOPE_ITEM_KEY_MAX_CHARS - len(suffix)].rstrip("_") + suffix
        taken.add(key)
        drafts.append(
            ScopeItem(
                tenant_id=tenant_id,
                key=key,
                name=entry.name,
                description=entry.description,
                jurisdiction=_jurisdiction(entry.jurisdiction),
                regime_term=terms_logic.term_by_ref(REGIME_DIMENSION, entry.regime_term),
                official_reference=entry.official_reference,
                source_url=entry.source_url,
            )
        )
    return drafts


def scope_items_in_scope(tenant_id: uuid.UUID, keys: list[str]) -> list[ScopeItem]:
    """The items a request would take out, by key, in the order given: each must be in
    scope now, or 422 `unknown_key` naming the keys that would have worked."""
    if len(set(keys)) < len(keys):
        raise ValidationError("Name each scope item once in a change.", code="validation_error")
    found = {
        item.key: item
        for item in _scope_items().filter(tenant_id=tenant_id, key__in=keys, status=ScopeItemStatus.IN_SCOPE.value)
    }
    missing = [key for key in keys if key not in found]
    if missing:
        valid = ", ".join(
            ScopeItem.objects.filter(tenant_id=tenant_id, status=ScopeItemStatus.IN_SCOPE.value)
            .order_by("key")
            .values_list("key", flat=True)
        )
        raise ValidationError(
            f"{missing[0]!r} is not a scope item in the regulatory scope. Valid keys: {valid or 'none'}.",
            code="unknown_key",
        )
    return [found[key] for key in keys]


# ---------------------------------------------------------------------------------------
# The preview (AC-FP1)
# ---------------------------------------------------------------------------------------
def _after(now: dict[str, set[str]], adds: list[Any], removes: list[Any]) -> dict[str, set[str]]:
    """The footprint the change would leave behind."""
    after = {dimension: set(keys) for dimension, keys in now.items()}
    for term in adds:
        after.setdefault(term.dimension.key, set()).add(term.key)
    for term in removes:
        after.get(term.dimension.key, set()).discard(term.key)
    return after


def preview_of(tenant_id: uuid.UUID, adds: list[Any], removes: list[Any]) -> FootprintPreview:
    """What the change would hide and reveal, per record kind (AC-FP1). Hidden means in
    scope now and out of it afterwards; revealed is the other way. The count runs the pure
    matching rule twice over the scope of every obligation this company can see (the
    library's one scope rule, `reading.obligation_scopes`, under row-level security),
    because the SQL function reads the stored footprint and this asks about one that does
    not exist yet. An obligation with no scope matches both and is not listed. Cases are
    counted the same way over the scope of each open case's change (`case_reading`)."""
    now = matching.footprint_of(tenant_id)
    after = _after(now, adds, removes)
    restricting = matching.restricting_dimensions()

    def count(scopes: list[dict[str, set[str]]]) -> FootprintPreviewCount:
        hidden = revealed = 0
        for record_terms in scopes:
            was_in = matching.in_footprint(record_terms, now, restricting=restricting)
            is_in = matching.in_footprint(record_terms, after, restricting=restricting)
            if was_in and not is_in:
                hidden += 1
            elif is_in and not was_in:
                revealed += 1
        return FootprintPreviewCount(hidden=hidden, revealed=revealed, available=True)

    obligation_scopes = [
        {dimension: {term.key for term in terms} for dimension, terms in scope.items()}
        for scope in reading.obligation_scopes().values()
    ]
    return FootprintPreview(obligations=count(obligation_scopes), cases=count(case_reading.open_case_scopes(tenant_id)))


def _changes_of(requests: list[FootprintChangeRequest]) -> list[tuple[list[Any], list[Any]]]:
    """The terms each request would switch on and off, with their dimensions, in one query
    per side for any number of requests. The database orders them as the picker and the
    scope panel do (terms_logic), by its own collation."""
    in_picker_order = ("term__dimension__sort_order", "term__sort_order", "term__key")
    prefetch_related_objects(
        requests,
        Prefetch("add_links", FootprintChangeAdd.objects.select_related("term__dimension").order_by(*in_picker_order)),
        Prefetch("remove_links", FootprintChangeRemove.objects.select_related("term__dimension").order_by(*in_picker_order)),
    )
    return [
        ([link.term for link in request.add_links.all()], [link.term for link in request.remove_links.all()])
        for request in requests
    ]


def _changes(request: FootprintChangeRequest) -> tuple[list[Any], list[Any]]:
    return _changes_of([request])[0]


def _preview_now(request: FootprintChangeRequest, adds: list[Any], removes: list[Any]) -> FootprintPreview:
    """A waiting request is recounted every time it is read, so the approver decides against
    today's library rather than against whatever it held when the request was made. A
    decided request keeps the counts it was decided against."""
    if request.status == ApprovalStatus.PENDING.value:
        return preview_of(request.tenant_id, adds, removes)
    return FootprintPreview(**request.preview) if request.preview else FootprintPreview()


def dry_run(
    tenant_id: uuid.UUID,
    adds: list[Any],
    removes: list[Any],
    order: list[str],
    *,
    item_adds: Sequence[ScopeItem] = (),
    item_removes: Sequence[ScopeItem] = (),
) -> FootprintDryRun:
    """The requester's preview before sending (playbook 15: dry run, preview, commit). The
    same validation as a real request, the same preview, and nothing written: no request
    row, no scope item, no audit event, no approval started. A preview is a read that needs
    a body. Scope items move no count: they are researched, never matched."""
    _validate_change(adds, removes, item_adds, item_removes)
    return FootprintDryRun(
        adds=terms_logic.labelled_term_refs(adds, order),
        removes=terms_logic.labelled_term_refs(removes, order),
        scope_item_adds=scope_item_rows(list(item_adds), order),
        scope_item_removes=scope_item_rows(list(item_removes), order),
        preview=preview_of(tenant_id, adds, removes),
        dry_run=True,
    )


def _validate_change(adds: list[Any], removes: list[Any], item_adds: Sequence[ScopeItem], item_removes: Sequence[ScopeItem]) -> None:
    if not adds and not removes and not item_adds and not item_removes:
        raise ValidationError("Choose at least one term or scope item to add or remove.", code="validation_error")
    if len({term.id for term in adds}) < len(adds) or len({term.id for term in removes}) < len(removes):
        raise ValidationError("Name each term once in a change.", code="validation_error")
    both = {term.id for term in adds} & {term.id for term in removes}
    if both:
        raise ValidationError("A term cannot be added and removed in the same change.", code="validation_error")


# ---------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------
def _term_state(term: Any, request: FootprintChangeRequest | None) -> dict[str, str]:
    """A term event's before or after: the term, and the request that caused it when one
    did, so the audit log ties each term to its request without matching step-up ids."""
    state = {"dimension": term.dimension.key, "term": term.key}
    if request is not None:
        state["request"] = str(request.id)
    return state


def _switch_on(
    *,
    tenant: Tenant,
    actor: Actor,
    terms: list[Any],
    request: FootprintChangeRequest | None,
    step_up_assertion_id: uuid.UUID | None,
    added_by: Any = None,
) -> int:
    """Add terms to the footprint: one `footprint_term` row, one history row and one audit
    event per term (FP-02: "one audit event per term", so the log reads as decisions about
    one term each rather than a blob nobody can diff)."""
    count = 0
    for term in terms:
        row, created = FootprintTerm.objects.get_or_create(
            tenant=tenant, term=term, defaults={"added_by": added_by}
        )
        if not created:
            continue
        FootprintHistory.objects.create(
            tenant=tenant,
            term=term,
            action=FootprintAction.ADDED.value,
            request=request,
            changed_by=added_by,
            step_up_assertion_id=step_up_assertion_id,
        )
        record(
            action="footprint.term_added",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=row.id,
            subject_title=f"{term.dimension.key}:{term.key}",
            summary=f"Added {term.dimension.key}:{term.key} to the regulatory scope.",
            tenant_id=tenant.id,
            after=_term_state(term, request),
            step_up_assertion_id=step_up_assertion_id,
        )
        count += 1
    return count


def _switch_off(
    *,
    tenant: Tenant,
    actor: Actor,
    terms: list[Any],
    request: FootprintChangeRequest | None,
    step_up_assertion_id: uuid.UUID | None,
    changed_by: Any = None,
) -> int:
    count = 0
    for term in terms:
        row = FootprintTerm.objects.filter(tenant=tenant, term=term).order_by("added_at", "id").first()
        if row is None:
            continue
        row.delete()
        FootprintHistory.objects.create(
            tenant=tenant,
            term=term,
            action=FootprintAction.REMOVED.value,
            request=request,
            changed_by=changed_by,
            step_up_assertion_id=step_up_assertion_id,
        )
        record(
            action="footprint.term_removed",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=row.id,
            subject_title=f"{term.dimension.key}:{term.key}",
            summary=f"Removed {term.dimension.key}:{term.key} from the regulatory scope.",
            tenant_id=tenant.id,
            before=_term_state(term, request),
            step_up_assertion_id=step_up_assertion_id,
        )
        count += 1
    return count


def seed_terms(*, tenant: Tenant, actor: Actor, terms: list[Any]) -> int:
    """The E2E seed's way in (playbook 8.3): the same writes an approval makes, with a
    system actor and no step-up assertion, so a seeded footprint has the same history rows
    as one a person built and the "as of" reconstruction never has a hole."""
    return _switch_on(tenant=tenant, actor=actor, terms=terms, request=None, step_up_assertion_id=None)


def unseed_terms(*, tenant: Tenant, actor: Actor, terms: list[Any]) -> int:
    """`seed_terms` undone, for an E2E journey that restores the seeded footprint it
    changed (watch-standards, WAT-S10): the same writes a removal makes, history and audit
    included."""
    return _switch_off(tenant=tenant, actor=actor, terms=terms, request=None, step_up_assertion_id=None)


def create_request(
    *,
    tenant: Tenant,
    requester: Any,
    actor: Actor,
    adds: list[Any],
    removes: list[Any],
    item_adds: Sequence[ScopeItem] = (),
    item_removes: Sequence[ScopeItem] = (),
) -> FootprintChangeRequest:
    """One pending request at a time (409 `request_pending`): two people editing the same
    footprint from two previews would each approve a change the other's preview never
    counted. The partial unique constraint `footprint_change_request_one_pending` decides,
    so two requests sent at the same moment cannot both wait; the savepoint keeps the
    caller's transaction usable after the refusal. The scope items it adds are stored with
    it as `requested`, so the approver decides on exactly what was asked (D-91)."""
    _validate_change(adds, removes, item_adds, item_removes)
    try:
        with transaction.atomic():
            request = FootprintChangeRequest.objects.create(
                tenant=tenant,
                requested_by=requester,
                preview=preview_of(tenant.id, adds, removes).model_dump(by_alias=True),
            )
    except IntegrityError as exc:
        # Only our constraint means "a change already waits"; any other refusal is a fault.
        diag = getattr(exc.__cause__, "diag", None)
        if getattr(diag, "constraint_name", None) != "footprint_change_request_one_pending":
            raise
        raise ValidationError(
            "A regulatory scope change is already waiting for a decision.", code="request_pending"
        ) from exc
    for term in adds:
        FootprintChangeAdd.objects.create(tenant=tenant, request=request, term=term)
    for term in removes:
        FootprintChangeRemove.objects.create(tenant=tenant, request=request, term=term)
    for item in item_adds:
        item.tenant = tenant
        item.status = ScopeItemStatus.REQUESTED.value
        item.save()
        FootprintChangeScopeItem.objects.create(tenant=tenant, request=request, scope_item=item, action=FootprintAction.ADDED.value)
    for item in item_removes:
        FootprintChangeScopeItem.objects.create(tenant=tenant, request=request, scope_item=item, action=FootprintAction.REMOVED.value)
    # Keys and ids only: the name and description a person typed stay on the item row.
    record(
        action="footprint.change_requested",
        actor=actor,
        subject_type=REQUEST_SUBJECT_TYPE,
        subject_id=request.id,
        subject_title=f"{len(adds) + len(item_adds)} added, {len(removes) + len(item_removes)} removed",
        summary="Requested a regulatory scope change.",
        tenant_id=tenant.id,
        after={
            "adds": [f"{term.dimension.key}:{term.key}" for term in adds],
            "removes": [f"{term.dimension.key}:{term.key}" for term in removes],
            "scopeItemAdds": [_item_state(item, None) for item in item_adds],
            "scopeItemRemoves": [_item_state(item, None) for item in item_removes],
        },
    )
    return request


def _item_state(item: ScopeItem, request: FootprintChangeRequest | None) -> dict[str, str]:
    """A scope item as an audit value or an outbox payload carries it: ids and keys, never
    the text a person typed (R2_CROSS_CUTTING rule m)."""
    state = {
        "scopeItemId": str(item.id),
        "key": item.key,
        "jurisdiction": item.jurisdiction.key,
        "regimeTerm": item.regime_term.key,
    }
    if request is not None:
        state["request"] = str(request.id)
    return state


def _switch_items(
    *,
    tenant: Tenant,
    actor: Actor,
    items: list[ScopeItem],
    action: FootprintAction,
    request: FootprintChangeRequest,
    step_up_assertion_id: uuid.UUID,
    changed_by: Any,
) -> None:
    """An approved request's scope items enter or leave the scope: the item's status, one
    history row and one `scope_item.added` or `scope_item.removed` audit and outbox row
    each, with the step-up that authorised it. The outbox row is what the bank's own
    agent's research listens for (OWN-02), so its payload names the item by id and key."""
    added = action is FootprintAction.ADDED
    for item in items:
        item.status = (ScopeItemStatus.IN_SCOPE if added else ScopeItemStatus.REMOVED).value
        item.save(update_fields=["status"])
        FootprintHistory.objects.create(
            tenant=tenant,
            scope_item=item,
            action=action.value,
            request=request,
            changed_by=changed_by,
            step_up_assertion_id=step_up_assertion_id,
        )
        state = _item_state(item, request)
        record(
            action=f"scope_item.{action.value}",
            actor=actor,
            subject_type=SCOPE_ITEM_SUBJECT_TYPE,
            subject_id=item.id,
            subject_title=item.key,
            summary=f"{'Added' if added else 'Removed'} scope item {item.key} {'to' if added else 'from'} the regulatory scope.",
            tenant_id=tenant.id,
            after=state if added else None,
            before=None if added else state,
            step_up_assertion_id=step_up_assertion_id,
            payload={**state, "tenantId": str(tenant.id)},
        )


def _decidable(request: FootprintChangeRequest, expected_version: int | None) -> None:
    """Lock the row, then check status and version under the lock (FP-S6). Two decisions on
    one request queue on the lock, and the second reads what the first committed: 409
    `invalid_transition`, never a stale "pending" that lets both land."""
    request.refresh_from_db(from_queryset=FootprintChangeRequest.objects.select_for_update())
    if request.status != ApprovalStatus.PENDING.value:
        raise ValidationError(
            "This regulatory scope change has already been decided.", code="invalid_transition"
        )
    if expected_version is not None and expected_version != request.version:
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")


def approve(
    *,
    tenant: Tenant,
    request: FootprintChangeRequest,
    decider: Any,
    actor: Actor,
    note: str,
    step_up_assertion_id: uuid.UUID,
    expected_version: int | None = None,
) -> FootprintChangeRequest:
    """The second person's decision (FP-02, AC-FP1). Four eyes is checked here and by the
    `footprint_change_request_four_eyes` check constraint, which is the database's word on
    it; the API answers 409 `four_eyes_violation`."""
    _decidable(request, expected_version)
    if request.requested_by_id == decider.id:
        raise ValidationError(
            "A regulatory scope change is approved by someone other than the person who asked for it.",
            code="four_eyes_violation",
        )
    adds, removes = _changes(request)
    item_adds, item_removes = _scope_item_changes_of([request])[0]
    # A term retired while the request waited is not the library's any more: nobody may
    # switch it on, so the approver rejects the change and the requester asks again. The
    # same holds for a scope item's jurisdiction or regime term.
    if any(not term.active or not term.dimension.active for term in adds) or any(
        not item.jurisdiction.active or not item.regime_term.active for item in item_adds
    ):
        raise ValidationError(
            "A term in this change was retired after it was asked for. Reject the change so it can be asked for again.",
            code="stale_write",
        )
    # Counted before the switch, against the footprint the approver was looking at.
    counted = preview_of(tenant.id, adds, removes)
    _switch_on(
        tenant=tenant,
        actor=actor,
        terms=adds,
        request=request,
        step_up_assertion_id=step_up_assertion_id,
        added_by=decider,
    )
    _switch_off(
        tenant=tenant,
        actor=actor,
        terms=removes,
        request=request,
        step_up_assertion_id=step_up_assertion_id,
        changed_by=decider,
    )
    for items, action in ((item_adds, FootprintAction.ADDED), (item_removes, FootprintAction.REMOVED)):
        _switch_items(
            tenant=tenant,
            actor=actor,
            items=items,
            action=action,
            request=request,
            step_up_assertion_id=step_up_assertion_id,
            changed_by=decider,
        )
    return _decide(
        tenant=tenant,
        request=request,
        decider=decider,
        actor=actor,
        note=note,
        status=ApprovalStatus.APPROVED,
        action="footprint.change_approved",
        step_up_assertion_id=step_up_assertion_id,
        preview=counted,
    )


def reject(
    *,
    tenant: Tenant,
    request: FootprintChangeRequest,
    decider: Any,
    actor: Actor,
    note: str,
    expected_version: int | None = None,
) -> FootprintChangeRequest:
    _decidable(request, expected_version)
    if request.requested_by_id == decider.id:
        raise ValidationError(
            "A regulatory scope change is decided by someone other than the person who asked for it.",
            code="four_eyes_violation",
        )
    return _decide(
        tenant=tenant,
        request=request,
        decider=decider,
        actor=actor,
        note=note,
        status=ApprovalStatus.REJECTED,
        action="footprint.change_rejected",
        step_up_assertion_id=None,
        preview=preview_of(tenant.id, *_changes(request)),
    )


def withdraw(
    *,
    tenant: Tenant,
    request: FootprintChangeRequest,
    requester: Any,
    actor: Actor,
    expected_version: int | None = None,
) -> FootprintChangeRequest:
    """Only the person who asked may take it back; anyone else gets 403 (the route checks
    it), because withdrawing is not a decision and must not become a way around four eyes."""
    _decidable(request, expected_version)
    return _decide(
        tenant=tenant,
        request=request,
        decider=None,
        actor=actor,
        note="",
        status=ApprovalStatus.WITHDRAWN,
        action="footprint.change_withdrawn",
        step_up_assertion_id=None,
        preview=preview_of(tenant.id, *_changes(request)),
    )


def _decide(
    *,
    tenant: Tenant,
    request: FootprintChangeRequest,
    decider: Any,
    actor: Actor,
    note: str,
    status: ApprovalStatus,
    action: str,
    step_up_assertion_id: uuid.UUID | None,
    preview: FootprintPreview,
) -> FootprintChangeRequest:
    """Every decision — approved, rejected, withdrawn — stores the counts it was taken
    against on the request and in its audit row, so a decided request never shows the
    counts from when it was sent."""
    before = {"status": request.status, "version": request.version}
    request.status = status.value
    request.decided_by = decider
    request.decided_at = timezone.now()
    request.decision_note = note
    request.version += 1
    request.preview = preview.model_dump(by_alias=True)
    request.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "version", "preview"])
    # The note a person typed stays on the request row; the audit value carries no tenant
    # text (CHUNK10_TASKS rule 13).
    after: dict[str, Any] = {"status": status.value, "version": request.version, "preview": request.preview}
    if status is not ApprovalStatus.APPROVED:
        # The items this request asked for never entered the scope; the decision's audit
        # row names them by id and key.
        declined = list(
            ScopeItem.objects.filter(
                tenant=tenant,
                request_links__request=request,
                request_links__action=FootprintAction.ADDED.value,
                status=ScopeItemStatus.REQUESTED.value,
            ).order_by("created_at", "id")
        )
        ScopeItem.objects.filter(pk__in=[item.pk for item in declined]).update(status=ScopeItemStatus.DECLINED.value)
        if declined:
            after["scopeItemsDeclined"] = [{"scopeItemId": str(item.id), "key": item.key} for item in declined]
    record(
        action=action,
        actor=actor,
        subject_type=REQUEST_SUBJECT_TYPE,
        subject_id=request.id,
        subject_title=str(request.id),
        summary=f"Regulatory scope change {status.value}.",
        tenant_id=tenant.id,
        before=before,
        after=after,
        step_up_assertion_id=step_up_assertion_id,
    )
    return request

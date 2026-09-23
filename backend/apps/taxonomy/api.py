"""Routes of the taxonomy app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

One generic route set serves every vocabulary list (VOC-01, AC-VOC1): `{list}` is a
registry name, never an enum in the contract. A tenant list is written directly under
`vocab.manage`; a library list answers every write with 202 and a proposal (VOC-07).

Route order matters: the literal paths (`/reorder`, `/suggest`, `/suggestions`) are
registered before `/{key}`, because Django resolves URL patterns in the order Ninja adds
them and `/vocab/{list}/{key}` would otherwise swallow `/vocab/{list}/suggestions`.

Every route here is gated with `@requires_permission` or listed in `UNGATED_BY_DESIGN`
(apps/shared/permissions.py) with its reason; `answers_problems` is always innermost.
"""

from typing import Annotated, Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.proposals import logic as proposals_logic
from apps.proposals.schemas import ProposalAccepted
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy import footprint_logic, library_lists_logic, markets_logic, reading, terms_logic
from apps.taxonomy import tenant_lists_logic as lists
from apps.taxonomy.http import (
    actor_for,
    answers_problems,
    caller_tenant,
    caller_user,
    deny,
    if_match,
    principal,
    proposer_for,
    require_any,
    require_library_reader,
    require_proposer,
    uuid_or_404,
)
from apps.taxonomy.models import FootprintChangeRequest
from apps.taxonomy.schemas import (
    FootprintDecisionBody,
    FootprintDryRun,
    FootprintRequestBody,
    FootprintRequestPage,
    FootprintRequestQuery,
    FootprintRequestRow,
    FootprintView,
    JurisdictionRow,
    MarketRow,
    MarketWatchBody,
    TaxonomyDimensionPage,
    TaxonomyTermCreateBody,
    TaxonomyTermPage,
    TaxonomyTermQuery,
    TermRef,
    VocabularyCreateBody,
    VocabularyListPage,
    VocabularyMergeBody,
    VocabularyMerged,
    VocabularyMergeQuery,
    VocabularyPatchBody,
    VocabularyQuery,
    VocabularyReorderBody,
    VocabularyRestored,
    VocabularyRetireBody,
    VocabularyRetired,
    VocabularyRow,
    VocabularyRowDetail,
    VocabularyRowPage,
    VocabularySuggestBody,
    VocabularySuggestionPage,
    VocabularySuggestionRow,
)

router = Router(tags=["Taxonomy"])

SESSION = SessionAuth()
SESSION_OR_KEY = [SessionAuth(), ApiKeyAuth()]

_SUGGESTION_LIST = (
    "The name of the list whose suggestions to read, such as `tenant_tag` for the "
    "organisation's own tags: one of the names `GET /vocab` returns in `list`. The set of "
    "lists is fixed by the product, not by an admin, who adds rows to a list and never a "
    "list; a name that is not a vocabulary list answers 404 `not_found`."
)


_LIST = (
    "The list to work on, by name, such as `tenant_tag` for the organisation's own tags or `change_type` "
    "for the library's change types: one of the names `GET /vocab` returns in `list`. The set of lists is "
    "fixed by the product, not by an admin, who adds values to a list and never a list; a name that is not "
    "a vocabulary list answers 404 `not_found` with the valid names in `detail`."
)
_KEY = (
    "The key of the value, as the list gives it in `key`, such as `custody`; a retired value is found by "
    "its key too. A key the list does not hold answers 404 `not_found`."
)
_SUGGESTION_ID = (
    "The suggestion to decline, as the `id` of a row of `GET /vocab/{list}/suggestions`: a UUID. One that is "
    "not a UUID, is not on this list or is not in the caller's organisation answers 404 `not_found`."
)

ListName = Annotated[str, Path(description=_LIST)]
RowKey = Annotated[str, Path(description=_KEY)]


def _accepted(proposal: Any) -> tuple[int, ProposalAccepted]:
    return 202, ProposalAccepted(proposal=proposals_logic.row(proposal))


def _tenant_writer(request: HttpRequest) -> None:
    require_any(request, perms.VOCAB_MANAGE)


# ---------------------------------------------------------------------------------------
# The list of lists
# ---------------------------------------------------------------------------------------
@router.get(
    "/vocab",
    response=VocabularyListPage,
    auth=SESSION,
    operation_id="listVocabularies",
    by_alias=True,
    summary="See every list whose values can be picked and managed",
)
@answers_problems
def list_vocabularies(request: HttpRequest) -> VocabularyListPage:
    """Every vocabulary list the caller can read, with how many active and retired values
    each holds and which fixed kinds its values may carry, so an admin screen's index or an
    integrator's setup needs no call per list. The shared library's lists come first; a
    caller signed in to an organisation also gets its own lists, and a platform session
    outside any organisation gets the library's only.

    Not paginated: the set of lists is short and fixed by the product, so it always arrives
    whole. A read: it changes nothing and writes no audit event. Any signed-in person may
    call it; an API key is refused, and an agent reads the lists it needs by name with
    `GET /vocab/{list}`.

    Errors to branch on: `unauthenticated` (401) without a person's session.
    """
    # Ungated by design: capability (any session; the admin screens' index, VOC-02).
    items = lists.list_of_lists(principal(request).tenant_id)
    return VocabularyListPage(items=items, total=len(items))


# ---------------------------------------------------------------------------------------
# Literal sub-paths first (see the module docstring)
# ---------------------------------------------------------------------------------------
@router.post(
    "/vocab/{list_name}/reorder",
    response={200: VocabularyRowPage},
    auth=SESSION,
    operation_id="reorderVocabulary",
    by_alias=True,
    summary="Put the values of one of our lists in the order people should see them",
)
@requires_permission(perms.VOCAB_MANAGE)
@answers_problems
def reorder_vocabulary(request: HttpRequest, list_name: ListName, body: VocabularyReorderBody) -> Any:
    """What a drag on the vocabulary screen saves: the values named come first, in the order
    given, and every value not named keeps its order after them. Pickers and filters follow
    the new `sortOrder` at once. Only the organisation's own lists are reordered here; a
    library list is shared by every organisation, so its order changes only through a
    proposal (`PATCH /vocab/{list}/{key}` with `sortOrder`), and a reorder of one answers
    403.

    Answers the list's active values in their new order. No key, label or version changes
    and no record changes what it carries. Needs `vocab.manage` in the caller's organisation
    and a person's session; an API key is refused. Records one audit event,
    `vocabulary.reordered`, with every value's place before and after.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without `vocab.manage`, or on a library list, with `library_vocab.manage` as the
    permission it would need; `not_found` (404) for a name that is not a vocabulary list;
    `unknown_key` (422) when a key is not on the list, and then nothing moves;
    `validation_error` (422) for a field the body does not name.
    """
    tenant = caller_tenant(request)
    entry = lists.entry_for(list_name)
    if entry.is_library:
        raise deny(perms.LIBRARY_VOCAB_MANAGE)
    lists.reorder(list_name=list_name, tenant=tenant, actor=actor_for(request), keys=body.keys)
    items = lists.rows_of(list_name, tenant.id, reading.language_order(request, tenant=tenant))
    return 200, VocabularyRowPage(items=items, total=len(items))


@router.post(
    "/vocab/{list_name}/suggest",
    response={201: VocabularySuggestionRow, 202: ProposalAccepted},
    auth=SESSION,
    operation_id="suggestVocabularyRow",
    by_alias=True,
    summary="Ask for a value a list does not have yet",
)
@answers_problems
def suggest_vocabulary_row(request: HttpRequest, list_name: ListName, body: VocabularySuggestBody) -> Any:
    """For a member without `vocab.manage` who types a value a picker does not offer. On one
    of the organisation's own lists the suggestion waits in the admin's inbox
    (`GET /vocab/{list}/suggestions`) and answers 201 with `status` `pending`; the list itself
    does not change until an admin creates the value, which answers the suggestion, or
    declines it. On a shared library list the suggestion becomes a proposal and answers 202:
    the platform decides it, and nothing changes until a second person or agent approves it.

    Checked like a create before anything is stored: the labels are in content languages,
    the key is not taken, and the label is not a near match of a value the list has. There
    is no `force` here: a member offered a near match picks it, or asks an admin.

    Any signed-in person may suggest; a person's session is needed and an API key is
    refused. Records `vocabulary.suggested` in the organisation's audit, or the proposal's
    `proposal.created` for a library list.

    Errors to branch on: `unauthenticated` (401) without a session; `not_found` (404) for a
    name that is not a vocabulary list, or an organisation's list from a session outside
    any organisation; `duplicate_key` (409) when the key exists, with the value in
    `candidates`; `near_duplicate` (422) when the label is close to an existing value's,
    with the close matches in `candidates`; `unknown_key` (422) for a label in a language
    that is not a content language; `validation_error` (422) for no label, a key that
    normalises to nothing, a library list that is reference data, or a field the body does
    not name.
    """
    # Ungated by design: capability (any member may suggest, VOC-03 "Suggest" without vocab.manage).
    entry = lists.entry_for(list_name)
    if entry.is_library:
        proposer = proposer_for(request)
        return _accepted(
            library_lists_logic.propose_create(
                list_name=list_name, proposer=proposer, labels=body.labels, key=body.key, usage_note=body.usage_note
            )
        )
    user = caller_user(request)
    tenant = caller_tenant(request)
    row = lists.suggest(
        list_name=list_name,
        tenant=tenant,
        actor=actor_for(request, user),
        user=user,
        labels=body.labels,
        key=body.key,
        usage_note=body.usage_note,
    )
    return 201, row


@router.get(
    "/vocab/{list_name}/suggestions",
    response=VocabularySuggestionPage,
    auth=SESSION,
    operation_id="listVocabularySuggestions",
    by_alias=True,
    summary="Work through what members suggested adding to one of our lists",
)
@requires_permission(perms.VOCAB_MANAGE)
@answers_problems
def list_vocabulary_suggestions(
    request: HttpRequest, list_name: Annotated[str, Path(description=_SUGGESTION_LIST)], page: Query[PageQuery]
) -> VocabularySuggestionPage:
    """The suggestions still waiting in one of the organisation's own lists, oldest first,
    because the inbox is worked in the order it filled. A member without `vocab.manage` who
    types a value a picker does not have suggests it (`POST /vocab/{list}/suggest`); an admin
    reads them here and either creates the row, which answers every suggestion for that key,
    or declines it with `POST /vocab/{list}/suggestions/{suggestionId}/decline`. Either way
    it leaves this list.

    A shared library list has no inbox here: a suggestion for it becomes a proposal that the
    platform decides, so its inbox is always empty.

    Paginated: 20 suggestions by default and 100 at most, with a larger limit refused rather
    than quietly trimmed, and `total` counting every waiting suggestion. The order is by
    when a suggestion was sent, oldest first, and by its id where two were sent in the same
    instant, so two calls always agree on it; a suggestion answered between them shifts the
    later page, as `offset` explains. An empty inbox is a 200 with an empty list and a total
    of 0.

    A read: it changes nothing and writes no audit event. Needs `vocab.manage` in the
    caller's organisation and a person's session; an API key is refused.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without `vocab.manage`; `not_found` (404) for a list name that is not a
    vocabulary list, with the valid names in `detail`; `validation_error` (422) when the
    page size or offset is out of range.
    """
    tenant = caller_tenant(request)
    rows, total = lists.suggestions_of(list_name, tenant.id, limit=page.limit, offset=page.offset)
    return VocabularySuggestionPage(items=rows, total=total)


@router.post(
    "/vocab/{list_name}/suggestions/{suggestion_id}/decline",
    response=VocabularySuggestionRow,
    auth=SESSION,
    operation_id="declineVocabularySuggestion",
    by_alias=True,
    summary="Turn down a value a member suggested",
)
@requires_permission(perms.VOCAB_MANAGE)
@answers_problems
def decline_vocabulary_suggestion(
    request: HttpRequest, list_name: ListName, suggestion_id: Annotated[str, Path(description=_SUGGESTION_ID)]
) -> VocabularySuggestionRow:
    """Answers a waiting suggestion with no: it leaves the inbox with `status` `declined`
    and the list does not change. The suggestion itself is kept, with the member's words.
    To say yes instead, create the value with `POST /vocab/{list}` and the suggestion's key,
    which answers it as accepted.

    Needs `vocab.manage` in the caller's organisation and a person's session; an API key is
    refused. Records one audit event, `vocabulary.suggestion_declined`.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without `vocab.manage`; `not_found` (404) for a name that is not a vocabulary list
    or a suggestion that is not waiting on this list in the caller's organisation;
    `invalid_transition` (409) when the suggestion was already accepted or declined.
    """
    tenant = caller_tenant(request)
    return lists.decline_suggestion(
        list_name=list_name, tenant=tenant, actor=actor_for(request), suggestion_id=uuid_or_404(suggestion_id)
    )


# ---------------------------------------------------------------------------------------
# One list and one row
# ---------------------------------------------------------------------------------------
@router.get(
    "/vocab/{list_name}",
    response=VocabularyRowPage,
    auth=SESSION_OR_KEY,
    operation_id="listVocabularyRows",
    by_alias=True,
    summary="Read the values of one list, for a picker, a filter or an agent",
)
@answers_problems
def list_vocabulary_rows(request: HttpRequest, list_name: ListName, query: Query[VocabularyQuery]) -> VocabularyRowPage:
    """The values of one list in list order, each with its key, its fixed kind, its label
    in the caller's language, how many records carry it and the version to send back as
    `If-Match`. Store and compare the key, show the label, and never match on a label: it
    may be reworded or translated at any time. Retired values are left out unless
    `includeRetired` is true.

    A library list is read by any person's session and by an API key with the
    `library:read` scope, which is how an agent reads the values it may submit. An
    organisation's own list is read the same ways from inside that organisation only.

    Not paginated: a list is short enough to arrive whole, and a list with no values is a
    200 with an empty list. A read: it changes nothing and writes no audit event.

    Errors to branch on: `unauthenticated` (401) without a session or a key;
    `permission_denied` (403) for a key without `library:read`, or an organisation's list
    read from outside any organisation; `not_found` (404) for a name that is not a
    vocabulary list, with the valid names in `detail`; `validation_error` (422) when
    `includeRetired` is not a boolean.
    """
    # Ungated by design: logic-gate (a person's session, or an agent's key with library:read; AGT-02).
    who = require_library_reader(request)
    entry = lists.entry_for(list_name)
    if not entry.is_library and who.tenant_id is None:
        raise deny(perms.VOCAB_MANAGE)
    items = lists.rows_of(list_name, who.tenant_id, reading.language_order(request), include_retired=query.include_retired)
    return VocabularyRowPage(items=items, total=len(items))


@router.post(
    "/vocab/{list_name}",
    response={201: VocabularyRow, 202: ProposalAccepted},
    auth=SESSION,
    operation_id="createVocabularyRow",
    by_alias=True,
    summary="Add a value to a list",
)
@answers_problems
def create_vocabulary_row(request: HttpRequest, list_name: ListName, body: VocabularyCreateBody) -> Any:
    """Adds a value without a deploy: it appears in pickers, filters, pills and the agents'
    reads from the same row. On one of the organisation's own lists the value exists at once
    and the answer is 201 with it; every suggestion waiting for the same key is answered as
    accepted. On a shared library list nothing changes yet: the answer is 202 with a
    proposal, and the value exists only when a second, independent person or agent approves
    it in the console.

    Checked before either: the labels are in content languages, the key is free in any
    letter case, the kind is one the list takes, the list's own columns in `extra` are
    valid, and the label is not a near match of a value the list has, unless `force` is
    true.

    An organisation's list needs `vocab.manage` in it; a library list needs
    `proposals.create` in the caller's organisation or `library_vocab.manage` in the
    console. A person's session is needed and an API key is refused. Records
    `vocabulary.created` in the organisation's audit, or the proposal's `proposal.created`
    for a library list.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without the permission above, which `requiredPermission` names; `not_found` (404)
    for a name that is not a vocabulary list; `duplicate_key` (409) when the key exists,
    with the value in `candidates`; `near_duplicate` (422) when the label is close to an
    existing value's, with the close matches in `candidates`; `unknown_key` (422) for an
    unknown language, a kind the list does not take or a missing required kind, or a
    reference in `extra` to a value that does not exist; `validation_error` (422) for no
    label, a key that normalises to nothing, a bad `extra` value, a library list that is
    reference data, or a field the body does not name.
    """
    # Ungated by design: logic-gate (vocab.manage for a tenant list; a proposal for a library list, VOC-07).
    entry = lists.entry_for(list_name)
    if entry.is_library:
        require_proposer(request)
        return _accepted(
            library_lists_logic.propose_create(
                list_name=list_name,
                proposer=proposer_for(request),
                labels=body.labels,
                key=body.key,
                usage_note=body.usage_note,
                kind=body.kind,
                sort_order=body.sort_order,
                extra=body.extra,
                force=body.force,
            )
        )
    _tenant_writer(request)
    row = lists.create_row(
        list_name=list_name,
        tenant=caller_tenant(request),
        actor=actor_for(request),
        labels=body.labels,
        key=body.key,
        usage_note=body.usage_note,
        kind=body.kind,
        sort_order=body.sort_order,
        extra=body.extra,
        force=body.force,
        order=reading.language_order(request),
    )
    return 201, row


@router.get(
    "/vocab/{list_name}/{key}",
    response=VocabularyRowDetail,
    auth=SESSION_OR_KEY,
    operation_id="getVocabularyRow",
    by_alias=True,
    summary="Open one value of a list, with where its labels came from",
)
@answers_problems
def get_vocabulary_row(request: HttpRequest, list_name: ListName, key: RowKey) -> VocabularyRowDetail:
    """One value as a list row gives it, plus which language its labels were first written
    in and which labels a machine translated and no person has confirmed since, so an edit
    screen can mark them. A retired value is found too, so a record that still carries one
    can show what it was.

    Read like the list: a library value by any person's session or an API key with
    `library:read`, an organisation's value from inside that organisation only. A read: it
    changes nothing and writes no audit event.

    Errors to branch on: `unauthenticated` (401) without a session or a key;
    `permission_denied` (403) for a key without `library:read`; `not_found` (404) for a name
    that is not a vocabulary list, a key the list does not hold, or an organisation's list
    read from outside any organisation.
    """
    # Ungated by design: logic-gate (a person's session, or an agent's key with library:read; AGT-02).
    who = require_library_reader(request)
    return lists.row_detail(list_name, key, who.tenant_id, reading.language_order(request))


@router.patch(
    "/vocab/{list_name}/{key}",
    response={200: VocabularyRow, 202: ProposalAccepted},
    auth=SESSION,
    operation_id="updateVocabularyRow",
    by_alias=True,
    summary="Rename a value, or change its note, its place or its own columns",
)
@answers_problems
def update_vocabulary_row(request: HttpRequest, list_name: ListName, key: RowKey, body: VocabularyPatchBody) -> Any:
    """Changes only what the body sends; the key never changes, so every record that carries
    the value shows the new label and none of them is rewritten. A retired value can be
    relabelled too. Send `If-Match` with the `version` you last read, quoted or not: a value
    changed in between answers 409 `stale_write` instead of being overwritten. Without it the
    change applies to whatever is current.

    On one of the organisation's own lists the change is made at once and the answer is 200
    with the value at its new version. On a shared library list nothing changes yet: the
    answer is 202 with a proposal naming the value, applied only when a second, independent
    person or agent approves it.

    An organisation's list needs `vocab.manage` in it; a library list needs
    `proposals.create` in the caller's organisation or `library_vocab.manage` in the
    console. A person's session is needed and an API key is refused. Records
    `vocabulary.updated` with the labels and usage note before and after, or the proposal's
    `proposal.created` for a library list.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without the permission above; `not_found` (404) for an unknown list or key;
    `stale_write` (409) when `If-Match` is not the current version; `unknown_key` (422) for
    an unknown language or a reference in `extra` to a value that does not exist;
    `validation_error` (422) for an `If-Match` that is not a version, labels whose every
    text is empty, a bad `extra` value, a library list that is reference data, or a field
    the body does not name.
    """
    # Ungated by design: logic-gate (vocab.manage for a tenant list; a proposal for a library list, VOC-07).
    entry = lists.entry_for(list_name)
    expected = if_match(request)
    if entry.is_library:
        require_proposer(request)
        return _accepted(
            library_lists_logic.propose_relabel(
                list_name=list_name,
                proposer=proposer_for(request),
                key=key,
                labels=body.labels,
                usage_note=body.usage_note,
                sort_order=body.sort_order,
                extra=body.extra,
                expected_version=expected,
            )
        )
    _tenant_writer(request)
    row = lists.patch_row(
        list_name=list_name,
        tenant=caller_tenant(request),
        actor=actor_for(request),
        key=key,
        labels=body.labels,
        usage_note=body.usage_note,
        sort_order=body.sort_order,
        extra=body.extra,
        expected_version=expected,
        order=reading.language_order(request),
    )
    return 200, row


@router.post(
    "/vocab/{list_name}/{key}/retire",
    response={200: VocabularyRetired, 202: ProposalAccepted},
    auth=SESSION,
    operation_id="retireVocabularyRow",
    by_alias=True,
    summary="Stop offering a value, keeping every record that carries it",
)
@answers_problems
def retire_vocabulary_row(request: HttpRequest, list_name: ListName, key: RowKey, body: VocabularyRetireBody) -> Any:
    """Retire, never delete: pickers stop offering the value, and every record that carries
    it keeps it and still shows its label. A value records carry is retired only with
    `confirm` true, so the person decides knowing how many records keep it. A system value
    is never retired. `POST /vocab/{list}/{key}/restore` brings a retired value back.

    On one of the organisation's own lists the value is retired at once: 200, with how many
    records carry it. On a shared library list nothing changes yet: 202 with a proposal,
    applied only when a second, independent person or agent approves it.

    An organisation's list needs `vocab.manage` in it; a library list needs
    `proposals.create` in the caller's organisation or `library_vocab.manage` in the
    console. A person's session is needed and an API key is refused. Records
    `vocabulary.retired` with the usage count, or the proposal's `proposal.created` for a
    library list.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without the permission above; `not_found` (404) for an unknown list or key;
    `system_row` (409) for a system value; `in_use` (409) when records carry the value and
    `confirm` is not true, with the count in `usageCount`; `invalid_transition` (409) when
    the value is already retired; `validation_error` (422) for a library list that is
    reference data or a field the body does not name.
    """
    # Ungated by design: logic-gate (vocab.manage for a tenant list; a proposal for a library list, VOC-07).
    entry = lists.entry_for(list_name)
    if entry.is_library:
        require_proposer(request)
        return _accepted(
            library_lists_logic.propose_retire(list_name=list_name, proposer=proposer_for(request), key=key, confirm=body.confirm)
        )
    _tenant_writer(request)
    return 200, lists.retire(list_name=list_name, tenant=caller_tenant(request), actor=actor_for(request), key=key, confirm=body.confirm)


@router.post(
    "/vocab/{list_name}/{key}/restore",
    response={200: VocabularyRestored, 202: ProposalAccepted},
    auth=SESSION,
    operation_id="restoreVocabularyRow",
    by_alias=True,
    summary="Offer a retired value again",
)
@answers_problems
def restore_vocabulary_row(request: HttpRequest, list_name: ListName, key: RowKey) -> Any:
    """The inverse of a retire: pickers offer the value again, under the same key, and the
    records that kept it all along are untouched. A value merged away can be restored too,
    but the records the merge moved stay with the value they moved to. No request body.

    On one of the organisation's own lists the value is restored at once: 200, with how
    many records carry it. On a shared library list nothing changes yet: 202 with a
    proposal, applied only when a second, independent person or agent approves it.

    An organisation's list needs `vocab.manage` in it; a library list needs
    `proposals.create` in the caller's organisation or `library_vocab.manage` in the
    console. A person's session is needed and an API key is refused. Records
    `vocabulary.restored`, or the proposal's `proposal.created` for a library list.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without the permission above; `not_found` (404) for an unknown list or key;
    `invalid_transition` (409) when the value is not retired; `validation_error` (422) for a
    library list that is reference data.
    """
    # Ungated by design: logic-gate (vocab.manage for a tenant list; a proposal for a library list, VOC-07).
    entry = lists.entry_for(list_name)
    if entry.is_library:
        require_proposer(request)
        return _accepted(library_lists_logic.propose_restore(list_name=list_name, proposer=proposer_for(request), key=key))
    _tenant_writer(request)
    return 200, lists.restore(list_name=list_name, tenant=caller_tenant(request), actor=actor_for(request), key=key)


@router.post(
    "/vocab/{list_name}/{key}/merge",
    response={200: VocabularyMerged, 202: ProposalAccepted},
    auth=SESSION,
    operation_id="mergeVocabularyRow",
    by_alias=True,
    summary="Fold a duplicate value into the one to keep",
)
@answers_problems
def merge_vocabulary_row(
    request: HttpRequest, list_name: ListName, key: RowKey, body: VocabularyMergeBody, query: Query[VocabularyMergeQuery]
) -> Any:
    """Moves every record that carries the value in the path to the value named in `into`,
    then retires the value in the path, in one transaction. Preview it first with
    `dryRun=true`: a 200 with how many records carry the value and how many would move,
    which changes nothing and writes no audit event, on a library list as on the
    organisation's own. Today only the organisation's tags have records to move; on the
    other lists `repointed` is 0 and the merge retires the value.

    Without `dryRun`, on one of the organisation's own lists the merge is made at once: 200
    with the counts and `dryRun` false. On a shared library list nothing changes yet: 202
    with a proposal, applied only when a second, independent person or agent approves it. A
    system value is never merged away, though another value may be merged into one.

    An organisation's list needs `vocab.manage` in it; a library list needs
    `proposals.create` in the caller's organisation or `library_vocab.manage` in the
    console. A person's session is needed and an API key is refused. Records
    `vocabulary.merged` with the counts, or the proposal's `proposal.created` for a library
    list.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without the permission above; `not_found` (404) for an unknown list, or a key or
    `into` the list does not hold; `system_row` (409) when the value in the path is a system
    value; `validation_error` (422) when `into` is the value itself, for a library list that
    is reference data, or for a field the body does not name.
    """
    # Ungated by design: logic-gate (vocab.manage for a tenant list; a proposal for a library list, VOC-07).
    entry = lists.entry_for(list_name)
    if entry.is_library:
        require_proposer(request)
        result = library_lists_logic.propose_merge(
            list_name=list_name, proposer=proposer_for(request), key=key, into=body.into, dry_run=query.dry_run
        )
        if isinstance(result, VocabularyMerged):
            return 200, result
        return _accepted(result)
    _tenant_writer(request)
    return 200, lists.merge(
        list_name=list_name,
        tenant=caller_tenant(request),
        actor=actor_for(request),
        key=key,
        into=body.into,
        dry_run=query.dry_run,
    )


# ---------------------------------------------------------------------------------------
# Taxonomy dimensions and terms (library; writes are proposals, VOC-07)
# ---------------------------------------------------------------------------------------
@router.get("/taxonomy/dimensions", response=TaxonomyDimensionPage, auth=SESSION_OR_KEY, operation_id="listTaxonomyDimensions", by_alias=True)
@answers_problems
def list_taxonomy_dimensions(request: HttpRequest) -> TaxonomyDimensionPage:
    # Ungated by design: logic-gate (a person's session, or an agent's key with library:read; AGT-02).
    require_library_reader(request)
    items = lists.rows_of("term_dimension", None, reading.language_order(request))
    return TaxonomyDimensionPage(items=items, total=len(items))


@router.get("/taxonomy/terms", response=TaxonomyTermPage, auth=SESSION_OR_KEY, operation_id="listTerms", by_alias=True)
@answers_problems
def list_terms(request: HttpRequest, query: Query[TaxonomyTermQuery]) -> TaxonomyTermPage:
    # Ungated by design: logic-gate (a person's session, or an agent's key with library:read; AGT-02).
    require_library_reader(request)
    terms = terms_logic.terms_of(query.dimension, include_retired=query.include_retired)
    items = terms_logic.term_rows(terms, reading.language_order(request))
    return TaxonomyTermPage(items=items, total=len(items))


@router.post("/taxonomy/terms", response={202: ProposalAccepted}, auth=SESSION, operation_id="createTerm", by_alias=True)
@answers_problems
def create_term(request: HttpRequest, body: TaxonomyTermCreateBody) -> Any:
    """Ask for a new taxonomy term in the shared library (VOC-07). Nothing is written to the
    library here: the answer is 202 with the proposal this call put in the queue, and the
    term exists only once a second person approves it in the console. The proposal's
    creation is recorded in the audit log.

    Needs `proposals.create` in the caller's bank or `library_vocab.manage` in the console.

    The terms of a dimension that mirrors the jurisdiction list belong to the reference
    seed, which keeps them in step with that list, so no call adds one (FP-S12).

    Errors to branch on: `jurisdiction_term_mirrored` (422) when the dimension's terms
    mirror the jurisdiction list, whatever key is sent; `unknown_key` (422) for a dimension
    that is not one, a label in a language the platform does not hold, or a parent that is
    not a term of the dimension; `duplicate_key` (409) when the key is taken in the
    dimension, a retired term's included; `validation_error` (422) for a key that is not a
    slug or a body the schema refuses; `permission_denied` (403) without either permission;
    `unauthenticated` (401) without a session.
    """
    # Ungated by design: logic-gate (proposals.create from a tenant, library_vocab.manage from the console; VOC-07).
    require_proposer(request)
    return _accepted(
        library_lists_logic.propose_term_create(
            proposer=proposer_for(request),
            dimension=body.dimension,
            labels=body.labels,
            key=body.key,
            usage_note=body.usage_note,
            parent=body.parent,
        )
    )


@router.patch("/taxonomy/terms/{term_id}", response={202: ProposalAccepted}, auth=SESSION, operation_id="updateTerm", by_alias=True)
@answers_problems
def update_term(request: HttpRequest, term_id: str, body: VocabularyPatchBody) -> Any:
    """Ask for a change to a taxonomy term's labels, usage note or place in the list
    (VOC-07). Nothing is written to the library here: the answer is 202 with the proposal
    this call put in the queue, and the term changes only once a second person approves it
    in the console. Send `If-Match` with the version last read to be told when someone
    changed the term first. The proposal's creation is recorded in the audit log.

    Needs `proposals.create` in the caller's bank or `library_vocab.manage` in the console.

    A term that mirrors the jurisdiction list, and every other term of its dimension,
    belongs to the reference seed and is never renamed here (FP-S12).

    Errors to branch on: `jurisdiction_term_mirrored` (422) for a term of a dimension that
    mirrors the jurisdiction list; `stale_write` (409) when `If-Match` names a version that
    is no longer the term's; `unknown_key` (422) for a label in a language the platform
    does not hold; `validation_error` (422) for an `If-Match` that is not a version or a
    body the schema refuses; `not_found` (404) when no term has that id, and for anything
    that is not a UUID; `permission_denied` (403) without either permission;
    `unauthenticated` (401) without a session.
    """
    # Ungated by design: logic-gate (proposals.create from a tenant, library_vocab.manage from the console; VOC-07).
    require_proposer(request)
    return _accepted(
        library_lists_logic.propose_term_update(
            proposer=proposer_for(request),
            term_id=uuid_or_404(term_id),
            labels=body.labels,
            usage_note=body.usage_note,
            sort_order=body.sort_order,
            expected_version=if_match(request),
        )
    )


# ---------------------------------------------------------------------------------------
# Footprint (FP-01, FP-02, FP-03)
# ---------------------------------------------------------------------------------------
@router.get("/tenant/footprint", response=FootprintView, auth=SESSION, operation_id="getFootprint", by_alias=True)
@answers_problems
def get_footprint(request: HttpRequest) -> FootprintView:
    # Ungated by design: capability (any member reads the footprint every surface is filtered by, FP-03).
    tenant = caller_tenant(request)
    return footprint_logic.view(tenant.id, reading.language_order(request, tenant=tenant))


@router.get(
    "/tenant/footprint/requests",
    response=FootprintRequestPage,
    auth=SESSION,
    operation_id="listFootprintRequests",
    by_alias=True,
    summary="Read the history of changes to our regulatory scope",
)
@answers_problems
def list_footprint_requests(request: HttpRequest, page: Query[PageQuery]) -> FootprintRequestPage:
    """Every change to the organisation's regulatory scope that anyone asked for, newest
    first: the one waiting for a second person, if there is one, and every request already
    approved, rejected or withdrawn, with who asked, who decided, when and the note they
    left. Call it for the history on the Regulatory scope screen; `GET /tenant/footprint`
    carries the waiting request on its own.

    A waiting request's `preview` is counted again on every read, against today's library,
    so the approver decides on what the change would hide and reveal now. A decided request
    keeps the counts it was decided against, the same ones its decision's audit event holds.

    Paginated: 20 requests by default and 100 at most, with a larger limit refused rather
    than quietly trimmed, and `total` counting every request. The order is by when a request
    was sent, newest first, and by its id where two were sent in the same instant, so two
    calls always agree on it; a request sent between them shifts the later page by one, as
    `offset` explains. An organisation that never asked for a change gets a 200 with an
    empty list and a total of 0, never a 404.

    A read: it changes nothing and writes no audit event. Any member of the organisation
    may call it, because every member sees what the scope hides and why; it needs a
    person's session and no permission beyond membership, and an API key is refused. The
    path says `footprint`, the code's name for what the screens call the regulatory scope.

    Errors to branch on: `unauthenticated` (401) without a session; `not_found` (404) for a
    principal in no organisation; `validation_error` (422) when the page size or offset is
    out of range.
    """
    # Ungated by design: capability (any member sees what was asked and decided, FP-02).
    tenant = caller_tenant(request)
    rows, total = footprint_logic.requests_of(
        tenant.id, reading.language_order(request, tenant=tenant), limit=page.limit, offset=page.offset
    )
    return FootprintRequestPage(items=rows, total=total)


@router.post(
    "/tenant/footprint/requests",
    response={200: FootprintDryRun, 201: FootprintRequestRow},
    auth=SESSION,
    operation_id="createFootprintRequest",
    by_alias=True,
)
@requires_permission(perms.FOOTPRINT_REQUEST)
@answers_problems
def create_footprint_request(request: HttpRequest, body: FootprintRequestBody, query: Query[FootprintRequestQuery]) -> Any:
    tenant = caller_tenant(request)
    order = reading.language_order(request, tenant=tenant)
    adds = terms_logic.terms_by_selectors(body.adds)
    removes = terms_logic.terms_by_selectors(body.removes)
    if query.dry_run:
        return 200, footprint_logic.dry_run(tenant.id, adds, removes, order)
    user = caller_user(request)
    created = footprint_logic.create_request(
        tenant=tenant, requester=user, actor=actor_for(request, user), adds=adds, removes=removes
    )
    return 201, footprint_logic.request_row(created, order)


def _footprint_request(tenant: Any, request_id: str) -> FootprintChangeRequest:
    found = (
        FootprintChangeRequest.objects.filter(tenant=tenant, pk=uuid_or_404(request_id))
        .select_related("requested_by", "decided_by")
        .first()  # ordering: pk lookup, at most one row
    )
    if found is None:
        from django.core.exceptions import ValidationError

        raise ValidationError("That regulatory scope change is not here.", code="not_found")
    return found


@router.post(
    "/tenant/footprint/requests/{request_id}/approve",
    response=FootprintRequestRow,
    auth=SESSION,
    operation_id="approveFootprintRequest",
    by_alias=True,
)
@requires_permission(perms.FOOTPRINT_APPROVE)
@requires_step_up
@answers_problems
def approve_footprint_request(request: HttpRequest, request_id: str, body: FootprintDecisionBody) -> FootprintRequestRow:
    tenant = caller_tenant(request)
    user = caller_user(request)
    decided = footprint_logic.approve(
        tenant=tenant,
        request=_footprint_request(tenant, request_id),
        decider=user,
        actor=actor_for(request, user),
        note=body.note,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
        expected_version=if_match(request),
    )
    return footprint_logic.request_row(decided, reading.language_order(request, tenant=tenant))


@router.post(
    "/tenant/footprint/requests/{request_id}/reject",
    response=FootprintRequestRow,
    auth=SESSION,
    operation_id="rejectFootprintRequest",
    by_alias=True,
)
@requires_permission(perms.FOOTPRINT_APPROVE)
@answers_problems
def reject_footprint_request(request: HttpRequest, request_id: str, body: FootprintDecisionBody) -> FootprintRequestRow:
    tenant = caller_tenant(request)
    user = caller_user(request)
    decided = footprint_logic.reject(
        tenant=tenant,
        request=_footprint_request(tenant, request_id),
        decider=user,
        actor=actor_for(request, user),
        note=body.note,
        expected_version=if_match(request),
    )
    return footprint_logic.request_row(decided, reading.language_order(request, tenant=tenant))


@router.post(
    "/tenant/footprint/requests/{request_id}/withdraw",
    response=FootprintRequestRow,
    auth=SESSION,
    operation_id="withdrawFootprintRequest",
    by_alias=True,
)
@requires_permission(perms.FOOTPRINT_REQUEST)
@answers_problems
def withdraw_footprint_request(request: HttpRequest, request_id: str) -> FootprintRequestRow:
    tenant = caller_tenant(request)
    user = caller_user(request)
    found = _footprint_request(tenant, request_id)
    if found.requested_by_id != user.id:
        # Withdrawing is the requester's own act, never a decision someone else takes.
        raise deny(perms.FOOTPRINT_REQUEST)
    withdrawn = footprint_logic.withdraw(
        tenant=tenant, request=found, requester=user, actor=actor_for(request, user), expected_version=if_match(request)
    )
    return footprint_logic.request_row(withdrawn, reading.language_order(request, tenant=tenant))


_MARKET_WATCH_EXAMPLE = {
    "requestBody": {"content": {"application/json": {"example": {"jurisdiction": "no"}}}},
    "responses": {200: {"content": {"application/json": {"example": {"jurisdiction": {"key": "no", "kind": "country", "label": "Norway"}, "operating": False, "watching": True}}}}},
}


@router.post(
    "/tenant/footprint/watching",
    response=MarketRow,
    auth=SESSION,
    operation_id="watchMarket",
    by_alias=True,
    summary="Start watching a market we do not operate in",
    openapi_extra=_MARKET_WATCH_EXAMPLE,
)
@requires_permission(perms.FOOTPRINT_REQUEST)
@answers_problems
def watch_market(request: HttpRequest, body: MarketWatchBody) -> MarketRow:
    """Add a country to the "Markets we watch" list (FP-04): a direct, audited write, not a
    footprint change request, because watching hides nothing from anyone and needs no
    preview, no second person and no step-up. Watching an already-watched country answers
    409 `already_watching`; an unknown, inactive or non-country key answers 422
    `unknown_key` or `not_a_country`. Watching an operating market is allowed and changes
    nothing visible until operating stops, when the market reads as watched again.

    Requires `footprint.request` in the caller's tenant, the same permission that starts a
    footprint change. Errors: `permission_denied` without it, `unauthenticated` without a
    session, `validation_error` for a body the schema rejects.
    """
    tenant = caller_tenant(request)
    user = caller_user(request)
    jurisdiction = markets_logic.watch(tenant=tenant, actor=actor_for(request, user), key=body.jurisdiction, added_by=user)
    return markets_logic.row_for(tenant.id, jurisdiction, reading.language_order(request, tenant=tenant))


@router.post(
    "/tenant/footprint/watching/remove",
    response=MarketRow,
    auth=SESSION,
    operation_id="unwatchMarket",
    by_alias=True,
    summary="Stop watching a market",
    openapi_extra=_MARKET_WATCH_EXAMPLE,
)
@requires_permission(perms.FOOTPRINT_REQUEST)
@answers_problems
def unwatch_market(request: HttpRequest, body: MarketWatchBody) -> MarketRow:
    """Remove a country from the "Markets we watch" list (FP-04): the same direct, audited
    write as watching, with no preview, no second person and no step-up. A country that is
    operating is untouched by this even when it once had a watch row, because the level is
    computed, not stored. A country with no watch row answers 404 `not_found`; an unknown,
    inactive or non-country key answers 422 `unknown_key` or `not_a_country`.

    Requires `footprint.request` in the caller's tenant. Errors: `permission_denied`
    without it, `unauthenticated` without a session, `not_found` for a market not
    currently watched.
    """
    tenant = caller_tenant(request)
    user = caller_user(request)
    jurisdiction = markets_logic.unwatch(tenant=tenant, actor=actor_for(request, user), key=body.jurisdiction)
    return markets_logic.row_for(tenant.id, jurisdiction, reading.language_order(request, tenant=tenant))


# ---------------------------------------------------------------------------------------
# Reference reads (I18N-01)
# ---------------------------------------------------------------------------------------
@router.get("/reference/jurisdictions", response=list[JurisdictionRow], auth=SESSION, operation_id="listJurisdictions", by_alias=True)
@answers_problems
def list_jurisdictions(request: HttpRequest) -> list[JurisdictionRow]:
    # Ungated by design: capability (any session; a reference read for pickers, I18N-01).
    from apps.library.models import Jurisdiction, JurisdictionLabel
    from apps.taxonomy.reading import Labels, label_of

    order = reading.language_order(request)
    rows = list(Jurisdiction.objects.filter(active=True).select_related("parent", "default_language").order_by("sort_order", "key"))
    labels = Labels.for_rows(JurisdictionLabel, rows)
    return [
        JurisdictionRow(
            key=row.key,
            kind=row.kind,
            label=label_of(labels.texts(row.id), order, original=labels.original(row.id), key=row.key),
            parent_key=row.parent.key if row.parent is not None else None,
            default_language=TermRef(key=row.default_language.key, kind=None, label=row.default_language.name),
        )
        for row in rows
    ]

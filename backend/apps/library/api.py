"""Routes of the library app (playbook 4.1: routes only). Chunk 1 adds the language
reference read for pickers (locale, tenant languages); chunk 3 adds the library reads: the
obligations list, one obligation as of a date and what changed between two of its versions,
the instruments list and one instrument's own card, the provision tree of an instrument and
what changed between two versions of one provision, and the two writes a record accepts.

A library record read serves a person with `library.read` and an agent's key with
`library:read`, so it is a logic gate (apps/taxonomy/http.py `require_library_read`) and
listed in `UNGATED_BY_DESIGN`; `answers_problems` is always innermost.

The writes are gated in the ordinary way. "This looks wrong" needs `problems.report`,
which every member of a bank holds and nobody at bleqq does, so a report is filed inside
one bank and stays there (Alex, 2026-09-19). Re-verifying a record needs
`proposals.review` and a fresh passkey: it is the single exception to "a proposal is the
only door into the library", and the one function it may reach lives behind the fence in
apps/proposals/apply.py. Every route resolves its subject through `reading`, so a record
the caller may not read is a 404 and never a 403 that would confirm it exists.

Chunk 5 adds the two library reads it needs, under that same read gate: the authority
list, which chunk 3 cut and which the change header and the console's authority filter
both need (ruling E), and a live record's citations, which is how an agent key re-checks
the record against its source without holding any write scope (AGT-01, item 3). Neither
writes; a correction the re-check finds is a proposal (PRO-01)."""

import uuid
from typing import Annotated, Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.identity.schemas import RoleRef
from apps.library import reading, reports
from apps.library.models import Language, SubjectType
from apps.library.schemas import (
    InstrumentDetail,
    InstrumentPage,
    InstrumentProvisionsQuery,
    InstrumentQuery,
    LibraryAuthority,
    LibraryRecordSources,
    ObligationAsOfQuery,
    ObligationDetail,
    ObligationPage,
    ObligationQuery,
    ProblemReportBody,
    ProblemReportCreated,
    ProvisionNode,
    ReverificationBody,
    SAMPLE_PROVISION_TREE,
    VerificationCreated,
    VersionDiff,
    VersionDiffQuery,
)
from apps.proposals.apply import apply_reverification
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, caller_user, principal, require_library_read
from apps.taxonomy.reading import language_order
from apps.taxonomy.schemas import PersonRef

router = Router(tags=["Library"])

SESSION = SessionAuth()
SESSION_OR_KEY = [SessionAuth(), ApiKeyAuth()]

# ---------------------------------------------------------------------------------------
# What the published contract says about the writes (docs/plans/briefs/API_DOCUMENTATION.md)
# ---------------------------------------------------------------------------------------
# Long prose belongs beside the route, not inside the decorator's argument list, and the two
# report routes say the same thing about the same record. A backticked snake_case word in an
# operation description is read as an RFC 9457 code by the documentation gate, so the three
# verification outcomes appear here unquoted on purpose.
_SUBJECT_ID = (
    "The {record} the report is about, by its identifier (a UUID). It has to be one the caller "
    "can already read, so another bank's private record and an identifier that names nothing "
    "both answer 404 rather than telling you which of the two it was."
)
OBLIGATION_ID_DESCRIPTION = _SUBJECT_ID.format(record="obligation")
INSTRUMENT_ID_DESCRIPTION = _SUBJECT_ID.format(record="instrument")
REVERIFY_ID_DESCRIPTION = (
    "The obligation that was checked, by its identifier (a UUID). A library editor works in no "
    "bank and so addresses the shared library alone: a record a bank owns privately answers 404 "
    "here, exactly as an identifier that names nothing does."
)

REPORT_DESCRIPTION = (
    "Files a reader's \"this looks wrong\" report against one {record} of the shared library. "
    "Call it when someone reading a record believes a public fact is wrong. Nothing in the "
    "library changes here: a proposal is the only door into it.\n\n"
    "{extra}"
    "The report is created inside the bank the caller is signed in to and stays there. No bleqq "
    "editor, no other bank, no agent and no model ever reads it, and no console surface lists it "
    "(Alex, 2026-09-19). The loop back to the library is closed the other way round: bleqq's "
    "watch agents re-check library records against their sources on every run, find the "
    "deviation themselves, and propose the correction for a second, independent principal to "
    "approve.\n\n"
    "The reporter and the bank are taken from the caller's session and never from the body, so "
    "do not send them; versionNumber and language record which words were on screen.\n\n"
    "Needs the `problems.report` permission, which every member of a bank holds and no platform "
    "role does. Answers 201 with the report's id, its status and when it was filed, and never "
    "reads the reader's own words back. Writes one audit event, library.problem_reported, "
    "carrying the record, the report's id and the version and language on screen, and never the "
    "text itself.\n\n"
    "Errors to branch on: `unauthenticated` (401) without a session; `permission_denied` (403) "
    "without the permission, including for every platform role; `not_found` (404) when the "
    "{record} is not one this caller may read; `validation_error` (422) when the body is "
    "malformed, the text is longer than 4000 characters or the path segment is not a UUID; "
    "`description_required` (422) when the description is only whitespace; `unknown_key` (422) "
    "when the language is not an active content language."
)

REVERIFY_DESCRIPTION = (
    "Records that a library editor has read this obligation against its source, and moves the "
    "record's re-verification stamp when the source still says the same thing. This is the "
    "single sanctioned exception to \"a proposal is the only door into the library\": it writes "
    "lastVerifiedAt and verifiedBy and nothing else. It creates no record, and changes no text, "
    "date, scope or facet.\n\n"
    "What it does not mean: nobody re-approved the record's content here and no new version was "
    "written. A no_change outcome says one person looked at the source on this date and found it "
    "unchanged; a correction still has to arrive as a proposal that a second, independent "
    "principal approves.\n\n"
    "Only no_change moves the stamp. change_found and source_unavailable file the check and "
    "leave the earlier stamp standing, so a reader is never told a record was confirmed when it "
    "was not. Every check is kept, not only the most recent one.\n\n"
    "Needs the `proposals.review` permission and a fresh passkey assertion (a step-up). No "
    "tenant role holds `proposals.review`, and the route takes a person's session only, so no "
    "API key scope reaches it and an agent can never stamp a record. Writes one audit event, "
    "library.reverified, carrying the assertion the passkey produced.\n\n"
    "Errors to branch on: `unauthenticated` (401) without a session; `permission_denied` (403) "
    "without the permission; `step_up_required` (403) when the session carries no fresh passkey "
    "assertion; `not_found` (404) when the obligation is not one this caller may read; "
    "`validation_error` (422) when the body is malformed, the note is longer than 4000 "
    "characters or the path segment is not a UUID; `unknown_key` (422) when the outcome is not "
    "one of the three."
)

# ---------------------------------------------------------------------------------------
# What the published contract says about the record reads
# ---------------------------------------------------------------------------------------
READ_OBLIGATION_ID_DESCRIPTION = (
    "The obligation to read, by its identifier (a UUID), which is the `id` a row of "
    "`GET /obligations` carries. A record this caller cannot see answers 404 exactly as an "
    "identifier that names nothing does, so no id can be probed for."
)
DIFF_OBLIGATION_ID_DESCRIPTION = (
    "The obligation whose two versions are compared, by its identifier (a UUID). Both "
    "versions belong to this one record: a diff is never taken across obligations. A record "
    "this caller cannot see answers 404, never 403."
)
READ_INSTRUMENT_ID_DESCRIPTION = (
    "The instrument to read, by its identifier (a UUID), which is the `id` a row of "
    "`GET /instruments` carries. A record this caller cannot see answers 404 exactly as an "
    "identifier that names nothing does, so no id can be probed for."
)
TREE_INSTRUMENT_ID_DESCRIPTION = (
    "The instrument whose provision tree to read, by its identifier (a UUID). A record "
    "this caller cannot see answers 404 exactly as an identifier that names nothing does, "
    "so no id can be probed for."
)
DIFF_PROVISION_ID_DESCRIPTION = (
    "The provision whose two versions are compared, by its identifier (a UUID), which is "
    "the `id` a node of the provision tree carries. Both versions belong to this one "
    "record: a diff is never taken across provisions. A record this caller cannot see "
    "answers 404, never 403."
)

# The languages are a short fixed reference read answered as a plain array, so its example
# lives on the route: the gate reads it from the 200 response, as it does the authorities'.
_LANGUAGES_EXAMPLE = {
    "responses": {
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {"key": "da", "kind": None, "label": "Dansk"},
                        {"key": "en", "kind": None, "label": "English"},
                        {"key": "fi", "kind": None, "label": "Suomi"},
                        {"key": "nb", "kind": None, "label": "Norsk bokmål"},
                        {"key": "sv", "kind": None, "label": "Svenska"},
                    ]
                }
            }
        }
    }
}

# ---------------------------------------------------------------------------------------
# What the published contract says about the two chunk 5 reads
# ---------------------------------------------------------------------------------------
_OBLIGATION_ID = (
    "The library obligation whose citations to read, as a UUID. A record the caller cannot "
    "see answers 404, never 403, so no id can be probed for."
)

# The provision tree is a plain array of root nodes rather than a page, so its example
# lives on the route too; the gate reads it from the 200 response.
_PROVISIONS_EXAMPLE = {"responses": {200: {"content": {"application/json": {"example": SAMPLE_PROVISION_TREE}}}}}

# The authority list is a short fixed reference read, so its example lives on the route
# rather than on a page schema; the gate reads it from the 200 response.
_AUTHORITIES_EXAMPLE = {
    "responses": {
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11",
                            "key": "fi",
                            "shortName": "FI",
                            "name": "Finansinspektionen",
                            "jurisdiction": {"key": "se", "kind": "country", "label": "Sweden"},
                            "url": "https://www.fi.se/",
                        },
                        {
                            "id": "8e40b6d1-25af-4c73-9d08-b1f4e7a3c592",
                            "key": "esma",
                            "shortName": "ESMA",
                            "name": "European Securities and Markets Authority",
                            "jurisdiction": {"key": "eu", "kind": "union", "label": "European Union"},
                            "url": "https://www.esma.europa.eu/",
                        },
                    ]
                }
            }
        }
    }
}


@router.get(
    "/reference/languages",
    response=list[RoleRef],
    auth=SessionAuth(),
    operation_id="listLanguages",
    by_alias=True,
    summary="List the languages a record can be read in",
    openapi_extra=_LANGUAGES_EXAMPLE,
)
def list_languages(request: HttpRequest) -> list[RoleRef]:
    """Every content language the platform is serving, as key, kind and label: what fills a
    language picker on a person's profile, on a bank's default-language setting and behind
    "Show original" on a record. Swedish, Danish, Norwegian, Finnish and English are active
    on day one.

    A read: it changes nothing and writes no audit row, and any signed-in session may make
    it. There is no permission to hold, because a person has to be able to choose the
    language they read in before they can read anything else. The languages are library
    reference rows, identical for every bank; a platform admin activates or retires one
    without a deploy, so read this list rather than hard-coding the five. Every row's kind
    is null: a language belongs to no sub-kind.

    Answers a plain array in key order rather than a page, like the other short reference
    reads, and an empty array would be a 200. Errors to branch on: `unauthenticated` (401)
    without a session.
    """
    # Ungated by design: capability (any session; a reference read for pickers, I18N-01).
    return [
        RoleRef(key=language.key, kind=None, label=language.name)
        for language in Language.objects.filter(active=True).order_by("key")
    ]


@router.get(
    "/obligations",
    response=ObligationPage,
    auth=SESSION_OR_KEY,
    operation_id="listObligations",
    by_alias=True,
    summary="Browse the duties the bank has to keep",
)
@answers_problems
def list_obligations(request: HttpRequest, query: Query[ObligationQuery], page: Query[PageQuery]) -> ObligationPage:
    """The obligations inventory: every duty of the shared library whose scope overlaps this
    bank's footprint, as it stood on a date, narrowed by instrument, duty type, scope terms
    or a phrase. Call it for the inventory screen, for a picker that has to name a duty, and
    from an agent run that needs the duties an instrument carries.

    A read: it changes nothing and writes no audit row. It takes a person's session holding
    `library.read` in their bank, or an agent's key carrying the `library:read` scope. The
    rows are shared library facts, the same for every bank and changed only through an
    approved proposal. Whether a duty applies to this bank, and whether the bank complies
    with it, are separate facts a person records elsewhere; a row appearing here decides
    neither.

    Paginated: 20 rows by default and 100 at most, with a larger limit refused rather than
    quietly trimmed, and rows ordered by their stable key so paging is repeatable. Nothing
    matching the filters is a 200 with an empty items list and a total of 0, never a 404.
    Setting footprint to all adds the duties the footprint hides and says in outsideReason
    why each of them would have been hidden; setting it to watched lists only what the
    markets the bank watches add, each row naming its jurisdiction.

    Errors to branch on: `unauthenticated` (401) without a credential; `permission_denied`
    (403) without library.read or the library:read scope; `validation_error` (422) when a
    term filter is not written dimension:key, when footprint is not in, all or watched,
    when the retired outsideFootprint is sent, when the phrase is longer than 200 characters
    or when the page size or offset is out of range; `unknown_key` (422) when a term filter
    names no active term, listing every one that was not found.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-03, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    order = language_order(request, tenant=tenant)
    items, total = reading.obligation_page(tenant, order, query, limit=page.limit, offset=page.offset)
    return ObligationPage(items=items, total=total)


@router.get(
    "/obligations/{obligation_id}",
    response=ObligationDetail,
    auth=SESSION_OR_KEY,
    operation_id="getObligation",
    by_alias=True,
    summary="Open one duty and read it as of a date",
)
@answers_problems
def get_obligation(
    request: HttpRequest,
    obligation_id: Annotated[uuid.UUID, Path(description=READ_OBLIGATION_ID_DESCRIPTION)],
    query: Query[ObligationAsOfQuery],
) -> ObligationDetail:
    """One duty of the shared library as it stood on a date: the plain-language summary in
    the best language for this reader, the instrument and the provisions it was drawn from,
    every version with the dates it runs between, the duties filed beside it, the facets
    that say who it reaches, and the provenance that says where it came from and when a
    person last held it against its source. Call it for the obligation card, and from an
    agent run that needs the whole record rather than a row.

    A read: it changes nothing and writes no audit row. It takes a person's session holding
    `library.read` in their bank, or an agent's key carrying the `library:read` scope.
    Nothing in the answer is the bank's own judgement: the record says what the rule is, and
    whether it applies here and whether the bank complies are separate facts held elsewhere.

    A library record is never overwritten, so this read carries no `If-Match` and can answer
    no stale write: a correction arrives as a new version through an approved proposal, and
    the older version stays readable at its own number. Reading as of a date before the
    first version answers the record with a null version and a null summary rather than a
    404.

    Errors to branch on: `unauthenticated` (401) without a credential; `permission_denied`
    (403) without library.read or the library:read scope; `not_found` (404) when no
    obligation has that id or it is one this caller may not see, the two answering alike so
    that no id can be probed for; `validation_error` (422) when the path segment is not a
    UUID or asOf is not a date.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-03, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    return reading.obligation_detail(tenant, language_order(request, tenant=tenant), obligation_id, query)


@router.get(
    "/obligations/{obligation_id}/diff",
    response=VersionDiff,
    auth=SESSION_OR_KEY,
    operation_id="getObligationDiff",
    by_alias=True,
    summary="See what changed between two versions of a duty",
)
@answers_problems
def get_obligation_diff(
    request: HttpRequest,
    obligation_id: Annotated[uuid.UUID, Path(description=DIFF_OBLIGATION_ID_DESCRIPTION)],
    query: Query[VersionDiffQuery],
) -> VersionDiff:
    """What changed between two versions of one duty's summary, sentence by sentence: the
    sentences that stand unchanged, the ones the newer version dropped and the ones it adds.
    Call it behind "Show what changed" on the obligation card, and whenever a regulatory
    change is being assessed and somebody has to see exactly which words moved.

    By default it compares the latest version against the one before it; from and to name
    any two versions by their number. Both are versions of the same obligation: this call
    never compares one record with another, and there is no way to ask it to. The comparison
    is made in a language both versions hold, preferring the one lang asks for, and the
    answer says which language it settled on and whether either side was machine translated
    and so still unconfirmed by a person.

    A read: it changes nothing, writes no audit row and logs none of the text, which is the
    library's own content. It takes a person's session holding `library.read` in their bank,
    or an agent's key carrying the `library:read` scope. A sentence shown as removed is a
    change to the wording of the rule, never a decision that this bank may stop doing
    something.

    Errors to branch on: `unauthenticated` (401) without a credential; `permission_denied`
    (403) without library.read or the library:read scope; `not_found` (404) when no
    obligation has that id or it is one this caller may not see; `unknown_key` (422) when a
    version number is asked for that this obligation has no version for; `validation_error`
    (422) when the obligation has fewer than two versions and neither number was given, when
    the two versions share no language at all, when lang is longer than 8 characters, or
    when the path segment is not a UUID.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-04, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    return reading.obligation_diff(language_order(request, tenant=tenant), obligation_id, query)


@router.get(
    "/instruments",
    response=InstrumentPage,
    auth=SESSION_OR_KEY,
    operation_id="listInstruments",
    by_alias=True,
    summary="Browse the instruments behind the inventory",
)
@answers_problems
def list_instruments(request: HttpRequest, query: Query[InstrumentQuery], page: Query[PageQuery]) -> InstrumentPage:
    """The instruments inventory: every law, regulation or guideline of the shared library
    whose own scope (its regime) overlaps this bank's footprint, narrowed by regime or a
    phrase. Call it for the Instruments tab and its filter, or with a bank's own API key
    to read the instruments behind that bank's inventory.

    A read: it changes nothing and writes no audit row. It takes a person's session
    holding `library.read` in their bank, or a bank's own API key carrying the
    `library:read` scope. The list is read against that bank's footprint, so a platform
    key, such as the one bleqq's own watch agents run with, belongs to no bank and answers
    404 even when it carries `library:read`. The rows are shared library facts, the same
    for every bank and changed only through an approved proposal.

    Paginated: 20 rows by default and 100 at most, ordered by stable key so paging is
    repeatable. `footprint` is one value: `in` by default, `all` for every instrument, or
    `watched` for only what the markets the bank watches add. `obligationCount` counts the
    obligations this bank would see under each instrument under the same value. Jurisdiction, level, authority and
    `asOf` filters are deferred: "as of" applies to obligations only, and the Instruments
    tab lists every visible instrument with its own in-force dates.

    Errors to branch on: `unauthenticated` (401) without a credential; `permission_denied`
    (403) without library.read or the library:read scope, which is checked first, so a
    platform key without the scope gets this; `not_found` (404) when the caller is a
    platform key carrying the scope, since it belongs to no bank; `validation_error` (422)
    when footprint is not in, all or watched, when the retired outsideFootprint is sent,
    when the phrase is longer than 200 characters or the page size or offset is out of
    range.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-01, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    order = language_order(request, tenant=tenant)
    items, total = reading.instrument_page(tenant, order, query, limit=page.limit, offset=page.offset)
    return InstrumentPage(items=items, total=total)


@router.get(
    "/instruments/{instrument_id}",
    response=InstrumentDetail,
    auth=SESSION_OR_KEY,
    operation_id="getInstrument",
    by_alias=True,
    summary="Open one instrument and read its identity and lineage",
)
@answers_problems
def get_instrument(
    request: HttpRequest, instrument_id: Annotated[uuid.UUID, Path(description=READ_INSTRUMENT_ID_DESCRIPTION)]
) -> InstrumentDetail:
    """One instrument of the shared library: its identity, official reference and ELI, its
    in-force dates with their precision, the authority behind it, when a person last
    re-verified it and its lineage to other instruments (what it implements or
    elaborates, and what implements, elaborates or amends it in turn). Call it for the
    instrument card.

    A read: it changes nothing and writes no audit row. It takes a person's session
    holding `library.read` in their bank, or a bank's own API key carrying the
    `library:read` scope; a platform key belongs to no bank and answers 404 even when it
    carries `library:read`. The designed `GET /instruments/{instrumentId}/relations` is
    served here as `lineage`, and the provision tree is its own read.

    Errors to branch on: `unauthenticated` (401) without a credential; `permission_denied`
    (403) without library.read or the library:read scope, which is checked first;
    `not_found` (404) when no instrument has that id or it is one this caller may not
    see, the two answering alike so that no id can be probed for, and when the caller is
    a platform key carrying the scope; `validation_error` (422) when the path segment is
    not a UUID.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-01, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    return reading.instrument_detail(language_order(request, tenant=tenant), instrument_id)


@router.get(
    "/instruments/{instrument_id}/provisions",
    response=list[ProvisionNode],
    auth=SESSION_OR_KEY,
    operation_id="listInstrumentProvisions",
    by_alias=True,
    summary="Read an instrument's provision tree",
    openapi_extra=_PROVISIONS_EXAMPLE,
)
@answers_problems
def list_instrument_provisions(
    request: HttpRequest,
    instrument_id: Annotated[uuid.UUID, Path(description=TREE_INSTRUMENT_ID_DESCRIPTION)],
    query: Query[InstrumentProvisionsQuery],
) -> list[ProvisionNode]:
    """The verbatim provision tree of one instrument: chapters, sections, articles,
    paragraphs or whatever each node's own kind names, each with every text version it
    has ever carried, its children in the tree and the obligations that cite it. Call it
    for the instrument card's provision tree, or with a bank's own API key when an
    integration needs the law itself rather than a plain-language duty.

    A read: it changes nothing and writes no audit row. It takes a person's session
    holding `library.read` in their bank, or a bank's own API key carrying the
    `library:read` scope; a platform key belongs to no bank and answers 404 even when it
    carries `library:read`. `asOf` decides only which version each node's
    `inForceVersion` names, and defaults to today in that bank's time zone; every version
    stays in `versions` regardless, so a reader can choose an earlier or a future one by
    its own chip rather than trusting today's date. The designed
    `GET /provisions/{provisionId}/versions` is served here, embedded in each node.

    Answered as a plain array of root nodes rather than a page, because a tree has no
    natural page boundary; an instrument with no provisions yet is a 200 with an empty
    array. The number of queries does not grow with the tree's size.

    Errors to branch on: `unauthenticated` (401) without a credential; `permission_denied`
    (403) without library.read or the library:read scope, which is checked first;
    `not_found` (404) when no instrument has that id or it is one this caller may not
    see, and when the caller is a platform key carrying the scope; `validation_error`
    (422) when the path segment is not a UUID or asOf is not a date.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-02, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    return reading.provision_tree(tenant, instrument_id, language_order(request, tenant=tenant), query)


@router.get(
    "/provisions/{provision_id}/diff",
    response=VersionDiff,
    auth=SESSION_OR_KEY,
    operation_id="getProvisionDiff",
    by_alias=True,
    summary="See what changed between two versions of a provision",
)
@answers_problems
def get_provision_diff(
    request: HttpRequest,
    provision_id: Annotated[uuid.UUID, Path(description=DIFF_PROVISION_ID_DESCRIPTION)],
    query: Query[VersionDiffQuery],
) -> VersionDiff:
    """What changed between two versions of one provision's verbatim text, sentence by
    sentence: the sentences that stand unchanged, the ones the newer version dropped and
    the ones it adds. Call it behind "Show what changed" on the provision tree.

    By default it compares the latest version against the one before it; from and to
    name any two versions by their number. Both are versions of the same provision: this
    call never compares one record with another. The comparison is made in a language
    both versions hold, preferring the one lang asks for, and the answer says which
    language it settled on and whether either side was machine translated and so still
    unconfirmed by a person.

    A read: it changes nothing, writes no audit row and logs none of the text, which is
    the library's own content. It takes a person's session holding `library.read` in
    their bank, or a bank's own API key carrying the `library:read` scope; a platform key
    belongs to no bank and answers 404 even when it carries `library:read`.

    Errors to branch on: `unauthenticated` (401) without a credential; `permission_denied`
    (403) without library.read or the library:read scope, which is checked first;
    `not_found` (404) when no provision has that id or it is one this caller may not see,
    and when the caller is a platform key carrying the scope; `unknown_key` (422) when
    a version number is asked for that this provision has no version for;
    `validation_error` (422) when the provision has fewer than two versions and neither
    number was given, when the two versions share no language at all, when lang is
    longer than 8 characters, or when the path segment is not a UUID.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-04, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    return reading.provision_diff(language_order(request, tenant=tenant), provision_id, query)


@router.get(
    "/authorities",
    response=list[LibraryAuthority],
    auth=SESSION_OR_KEY,
    operation_id="listAuthorities",
    by_alias=True,
    summary="List the authorities that issue the rules we watch",
    openapi_extra=_AUTHORITIES_EXAMPLE,
)
@answers_problems
def list_authorities(request: HttpRequest) -> Any:
    """Every issuing authority the shared library knows, with its jurisdiction: the Swedish,
    Danish, Norwegian and Finnish supervisors, the EU bodies and the international standards
    publishers. Call it to fill an authority filter on the watch feed or the console's change
    queue, to label a change's issuer, and from an agent run that has to recognise the
    authority behind a page it fetched.

    A read: it changes nothing and writes no audit row. A person's session holding
    `library.read`, or an agent's key carrying the `library:read` scope. A short fixed
    reference list, answered as a plain array rather than a page, like the other reference
    reads. Library facts, the same for every bank, changed only through an approved proposal;
    an authority's `key` never changes, so store the key and never the name.

    Ordered by the authority's key, so the list a picker renders is the same on every call.
    An empty library would be a 200 with an empty array.

    Errors: `permission_denied` without `library.read` or `library:read`; `unauthenticated`
    without a credential.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; FP-04, AGT-02).
    # A short fixed reference list, answered as a plain array like the other reference reads.
    require_library_read(request)
    return reading.list_authorities(language_order(request))


@router.get(
    "/obligations/{obligation_id}/sources",
    response=LibraryRecordSources,
    auth=SESSION_OR_KEY,
    operation_id="getRecordSources",
    by_alias=True,
    summary="See which public pages an obligation was taken from",
)
@answers_problems
def get_record_sources(
    request: HttpRequest, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """The citations behind the version of an obligation in force today: which field each one
    backs, the public page it came from, the hash of that page as we last read it and when.
    Call it to show a reader where a fact came from, and from a watch run that re-checks a
    library record against its source.

    A read: it changes nothing and writes no audit row. A person's session holding
    `library.read`, or an agent's key carrying the `library:read` scope alone — which is the
    point of the route, because a run must be able to compare a record with its source
    without holding any write scope. Nothing an agent finds here may be written back: a
    record that has drifted becomes a proposal, approved by a second and independent
    principal, and never a direct edit (PRO-01). A page whose hash has changed means the page
    moved, never that the record is wrong.

    A record with no field-level citation yet is a 200 with an empty `items`, not a 404; the
    record's own `provenance` on `GET /obligations/{obligationId}` still names where it came
    from. Errors: `not_found` when no obligation has that id or the caller may not see it;
    `permission_denied` without `library.read` or `library:read`; `unauthenticated` without a
    credential.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-06, AGT-01).
    require_library_read(request)
    return reading.get_record_sources(obligation_id, reading.today_of(principal(request).tenant_id))


@router.post(
    "/obligations/{obligation_id}/problem-reports",
    response={201: ProblemReportCreated},
    auth=SESSION,
    operation_id="reportObligationProblem",
    by_alias=True,
    summary="Tell us an obligation looks wrong",
    description=REPORT_DESCRIPTION.format(
        record="obligation",
        extra=(
            "The obligation has to be one this caller can already read: a shared record, or one "
            "their own bank owns privately.\n\n"
        ),
    ),
)
@requires_permission(perms.PROBLEMS_REPORT)
@answers_problems
def report_obligation_problem(
    request: HttpRequest,
    obligation_id: Annotated[uuid.UUID, Path(description=OBLIGATION_ID_DESCRIPTION)],
    body: ProblemReportBody,
) -> Any:
    tenant = caller_tenant(request)
    reporter = caller_user(request)
    obligation = reading.obligation_subject(obligation_id)
    report = reports.create_report(
        subject_type=SubjectType.OBLIGATION,
        subject_id=obligation.id,
        subject_title=obligation.stable_key,
        tenant_id=tenant.id,
        reporter=reporter,
        actor=actor_for(request, reporter),
        description=body.description,
        version_number=body.version_number,
        language=body.language,
    )
    return 201, ProblemReportCreated(id=report.id, status=report.status, created_at=report.created_at)


@router.post(
    "/instruments/{instrument_id}/problem-reports",
    response={201: ProblemReportCreated},
    auth=SESSION,
    operation_id="reportInstrumentProblem",
    by_alias=True,
    summary="Tell us an instrument or one of its provisions looks wrong",
    description=REPORT_DESCRIPTION.format(
        record="instrument",
        extra=(
            "A provision is reported through the instrument whose card shows it, so there is no "
            "separate provision route; say which provision in the text. The instrument has to be "
            "one this caller can already read: a shared record, or one their own bank owns "
            "privately.\n\n"
        ),
    ),
)
@requires_permission(perms.PROBLEMS_REPORT)
@answers_problems
def report_instrument_problem(
    request: HttpRequest,
    instrument_id: Annotated[uuid.UUID, Path(description=INSTRUMENT_ID_DESCRIPTION)],
    body: ProblemReportBody,
) -> Any:
    tenant = caller_tenant(request)
    reporter = caller_user(request)
    instrument = reading.instrument_subject(instrument_id)
    report = reports.create_report(
        subject_type=SubjectType.INSTRUMENT,
        subject_id=instrument.id,
        subject_title=instrument.stable_key,
        tenant_id=tenant.id,
        reporter=reporter,
        actor=actor_for(request, reporter),
        description=body.description,
        version_number=body.version_number,
        language=body.language,
    )
    return 201, ProblemReportCreated(id=report.id, status=report.status, created_at=report.created_at)


@router.post(
    "/obligations/{obligation_id}/verifications",
    response={201: VerificationCreated},
    auth=SESSION,
    operation_id="reverifyObligation",
    by_alias=True,
    summary="Record that you checked an obligation against its source",
    description=REVERIFY_DESCRIPTION,
)
@requires_permission(perms.PROPOSALS_REVIEW)
@requires_step_up
@answers_problems
def reverify_obligation(
    request: HttpRequest,
    obligation_id: Annotated[uuid.UUID, Path(description=REVERIFY_ID_DESCRIPTION)],
    body: ReverificationBody,
) -> Any:
    reviewer = caller_user(request)
    # A library editor works in no bank, so row-level security shows this lookup the shared
    # library alone: a bank's own private record is nobody else's to re-verify, and asking
    # for one answers the same 404 as an id that names nothing.
    obligation = reading.obligation_subject(obligation_id)
    verification = apply_reverification(
        obligation,
        actor=actor_for(request, reviewer),
        verified_by=reviewer,
        outcome=body.outcome,
        note=body.note,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    stamped_by = obligation.verified_by
    return 201, VerificationCreated(
        id=verification.id,
        outcome=verification.outcome,
        verified_at=verification.verified_at,
        last_verified_at=obligation.last_verified_at,
        verified_by=None if stamped_by is None else PersonRef(id=stamped_by.id, name=stamped_by.name),
    )

"""Routes of the search app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

Four operations, the designed contract's (`docs/inputs/openapi.yaml`). Each one hands its
validated body to the module of the logic package that builds it — `hybrid.py` for
searching and for the agents' nearest-neighbour read, `ask.py` for the answer and its
feedback — and one that has not landed yet answers `not_built` until it does
(PARALLEL_PLAN rule 3). The gate runs first, so a caller without it is refused before it
learns whether anything is built.

Both search routes spend from a bucket of their own before anything else runs
(`limits.py`): the reader's session or the agent's key, sixty a minute each, answered 429
`rate_limited` over it. Nothing of what the caller sent reaches the refusal.

`POST /ask` answers an event stream, not one body: the budget is a first token under 2 s
(playbook 10, SRC-S9), which an answer that waits for its last sentence cannot meet. The
route declares `SSE[AskEvent]`, Django sends a `StreamingHttpResponse` of
`text/event-stream`, and `ask.py` owns every byte in it. Everything that can refuse the
call before the first byte still does: the session, the permission and the question's cap
are checked before the stream opens, and each answers a status with a problem body.

Who may call what: a person searching, asking or rating an answer holds `search.use`
(PRD §6, "everyone"). `POST /search/similar` is the agents' route, gated on the
`search:read` key scope alone (AGT-02, INPUT_DELTAS §7): no permission in the matrix
gives a person a similarity read, and a console surface that wants one comes with its own
permission and its own review. Nothing here writes, so nothing here needs step-up or
four eyes.
"""

from collections.abc import Iterator

from django.http import HttpRequest, HttpResponse
from ninja import SSE, Router

from apps.search import ask, hybrid
from apps.search.schemas import (
    AnswerFeedbackBody,
    AskEvent,
    AskRequest,
    SearchRequest,
    SearchResponse,
    SimilarRequest,
)
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_permission, requires_scope
from apps.taxonomy.http import answers_problems, principal, uuid_or_404

router = Router(tags=["Search"])

SESSION = SessionAuth()


@router.post(
    "/search",
    response=SearchResponse,
    auth=SESSION,
    operation_id="search",
    by_alias=True,
    summary="Find an obligation, a provision or a change in the shared library",
)
@requires_permission(perms.SEARCH_USE)
@answers_problems
def search(request: HttpRequest, body: SearchRequest) -> SearchResponse:
    """Find obligations, provisions and registered changes in the shared library, by
    identifier or by concept, as they stood on a chosen date (SRC-01, SRC-02).

    Who may call it: a person with `search.use`, on their own session. An API key is
    refused; agents use `POST /search/similar`.

    What comes back: one ranked page, best first. `limit` defaults to 20 and may not
    exceed 100; a larger number answers 422 naming the field and is never clamped. The
    bank's regulatory scope and any filter are applied before ranking, so an empty list
    means nothing inside the bank's view matched, not that nothing exists.

    Limits and budgets: the query is at most 500 characters (`SEARCH_QUERY_MAX_CHARS`),
    and a longer one answers 422 rather than being truncated. Each reader may search 60
    times a minute (`SEARCH_RATE_PER_USER_PER_MINUTE`), counted per person rather than per
    bank so one busy colleague cannot lock the others out. The answer arrives inside
    800 ms without the reranker and 1.5 s with it (NFR-02), reported in `Server-Timing`.

    Shape of the call: a read. It is not streamed, it needs no idempotency key, and it
    writes no audit row, because nothing changed. It is a POST so the query never travels
    in a URL: what a reader types is the bank's own text.

    Errors: `rate_limited` when that reader has searched more than the limit above in the
    last minute, which is a 429 to wait out and retry rather than a call to change;
    `unknown_key` for a `lang` that is not one of the library's language rows;
    `validation_error` for a query over the cap, a `limit` above 100 or a filter the
    contract does not name; `not_found` when the session belongs to no bank;
    `permission_denied` without `search.use`; `unauthenticated` without a session.
    """
    who = principal(request)
    return hybrid.run_search(body, tenant_id=who.tenant_id, user_id=who.subject_id)


@router.post(
    "/search/similar",
    response=SearchResponse,
    auth=ApiKeyAuth(),
    operation_id="findSimilar",
    by_alias=True,
    summary="Find the library records nearest a piece of text",
)
@requires_scope(perms.SCOPE_SEARCH_READ)
@answers_problems
def find_similar(request: HttpRequest, body: SimilarRequest) -> SearchResponse:
    """Find the shared library records nearest a piece of text, so an agent can tell
    whether a change is already tracked and can suggest obligation links (AGT-02).

    Who may call it: an API key holding the `search:read` scope, and nothing else. No
    permission in the PRD's matrix gives a person a similarity read, so a person's
    session is refused here even with `search.use`.

    What comes back: the same ranked shape `POST /search` returns, over shared library
    records only. No record of any bank's own zone is read or returned, and no bank's
    regulatory scope narrows it, because a key belongs to no bank. The text carries no
    language and no `asOf`: it is compared in every content language the library holds,
    against the records in force today. `matchKind` says which leg found each record, so
    an agent can tell a reference it recognised from a meaning it matched.

    Limits and budgets: the text is at most 8000 characters
    (`SEARCH_SIMILAR_MAX_CHARS`); longer answers 422. `limit` defaults to 20 and may not
    exceed 100. Each key may call 60 times a minute
    (`SEARCH_RATE_PER_USER_PER_MINUTE`, the same allowance a reader has), counted per key.
    The same 800 ms budget as `POST /search` applies.

    Shape of the call: a read. Not streamed, no idempotency key, no audit row. The text
    an agent sends is fetched content and is treated as untrusted: it is not stored, and
    nothing it says directs the server.

    Errors: `rate_limited` when that key has called more than the limit above in the last
    minute, a 429 to wait out and retry; `validation_error` for a text over the cap, a
    `limit` above 100 or a field the contract does not name; `permission_denied` without
    the `search:read` scope; `unauthenticated` without a key, which is also what a
    person's session gets here.
    """
    return hybrid.find_similar(body, caller_id=principal(request).subject_id)


@router.post("/ask", response=SSE[AskEvent], auth=SESSION, operation_id="ask", by_alias=True)
@requires_permission(perms.SEARCH_USE)
@answers_problems
def ask_question(request: HttpRequest, body: AskRequest, response: HttpResponse) -> Iterator[AskEvent]:
    """Answer a question in the reader's own words, grounded only in the shared library,
    every sentence carrying a citation and a pending change flagged (SRC-03).

    Who may call it: a person with `search.use`, on their own session. An API key is
    refused: Ask is a reading aid for people, and the question is tenant text.

    What comes back: an event stream (`text/event-stream`), not one body, because the
    budget is a first token under 2 s (NFR-02) and an answer that waits for its last
    sentence cannot meet it. The events are `start` carrying the answer's id, one
    `statement` per cited sentence, and then either `answer` with the whole answer or
    `problem` with a `code` to branch on. A stream that has begun cannot change its
    status, so a failure found after the first byte arrives as a `problem` event; do not
    read the status line alone as success.

    Limits and budgets: the question is at most 2000 characters
    (`ASK_QUESTION_MAX_CHARS`), and a longer one answers 422 before any stream opens. The
    first token arrives inside 2 s (NFR-02).

    Shape of the call: a read of the library and a model call. It needs no idempotency
    key, because asking twice costs two model calls and changes no record, and it writes
    no audit row, only the AI log row every model call writes (AUD-02). The question is the
    only text of the bank's own that ever reaches a model (D-07), and it reaches no log
    line, no Sentry event and no URL.
    """
    who = principal(request)
    return ask.answer_events(body, tenant_id=who.tenant_id, user_id=who.subject_id, response=response)


@router.post(
    "/answers/{answer_id}/feedback",
    response={204: None},
    auth=SESSION,
    operation_id="rateAnswer",
    by_alias=True,
    summary="Say whether an answer helped",
)
@requires_permission(perms.SEARCH_USE)
@answers_problems
def rate_answer(request: HttpRequest, answer_id: str, body: AnswerFeedbackBody) -> tuple[int, None]:
    """Record a reader's verdict on one answer — helpful or wrong, with an optional note
    — so the people who tune retrieval know where it fails (AUD-02, SRC-05).

    Who may call it: a person with `search.use`, on their own session, about an answer
    of their own bank. An answer of another bank answers 404.

    What comes back: 204 and no body.

    Limits and budgets: the note is at most 2000 characters
    (`SEARCH_FEEDBACK_NOTE_MAX_CHARS`); longer answers 422. The ordinary 250 ms API
    budget applies.

    Shape of the call: the one write in this contract. It goes through the audit trail
    like any other write, and it needs no idempotency key because it is idempotent by
    nature: the same verdict on the same answer twice leaves one row. Neither the
    question nor the answer nor the note reaches the audit summary.
    """
    ask.rate_answer(uuid_or_404(answer_id), body, user_id=principal(request).subject_id)
    return 204, None

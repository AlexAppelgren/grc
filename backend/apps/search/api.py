"""Routes of the search app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

Four operations, the designed contract's (`docs/inputs/openapi.yaml`). Each one hands its
validated body to the module that answers it — `hybrid.py` for searching and for the
agents' nearest-neighbour read, `ask.py` for the answer and its feedback. The gate runs
first, so a caller without it is refused before it learns anything.

Both search routes spend from a bucket of their own before anything else runs
(`limits.py`): the reader's session or the agent's key, sixty a minute each, answered 429
`rate_limited` over it. Nothing of what the caller sent reaches the refusal.

`POST /ask` answers an event stream, not one body: the budget is a first token under 2 s
(playbook 10, SRC-S9), which an answer that waits for its last sentence cannot meet. The
route declares `SSE[AskEvent]`, Django sends a `StreamingHttpResponse` of
`text/event-stream`, and `ask.py` owns every byte in it. Everything that can refuse the
call before the first byte still does: the session, the permission, the question's cap,
the bank's AI switch, the rate limit and the language are checked before the stream
opens, and each answers a status with a problem body.

The evaluation set's four routes at the end are the platform console's (SRC-05,
ADM-02): `eval.manage` only, and the one write, adding a question, is audited.

Who may call what: a person searching, asking or rating an answer holds `search.use`
(PRD §6, "everyone"). A bank's key holding `search:read` searches too, which is how a bank's
own agent reads (ACC-04, ACC-05); an agent access credential's search is narrowed to its
entry's scope in `hybrid.py`, and it is the one POST such a credential may send. `POST /search/similar` is the agents' route, gated on the
`search:read` key scope alone (AGT-02, INPUT_DELTAS §7): no permission in the matrix
gives a person a similarity read, and a console surface that wants one comes with its own
permission and its own review. The one write, the reader's verdict on an answer, goes
through the audit trail; playbook 4.2 lists none of these, so none needs step-up or four
eyes.
"""

from collections.abc import Iterator

from django.http import HttpRequest
from ninja import SSE, Path, Query, Router

from apps.library.reading import reader_of
from apps.search import ask, eval_sets, hybrid
from apps.search.schemas import (
    AnswerFeedbackBody,
    AskEvent,
    AskRequest,
    EvalBaselineOut,
    EvalQuestionInput,
    EvalQuestionOut,
    EvalQuestionPage,
    EvalRunPage,
    SearchRequest,
    SearchResponse,
    SimilarRequest,
)
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, PrincipalKind, SessionAuth
from apps.shared.permissions import requires_permission, requires_scope
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, deny, principal, require_any, uuid_or_404

router = Router(tags=["Search"])

SESSION = SessionAuth()
SESSION_OR_KEY = [SessionAuth(), ApiKeyAuth()]


def require_searcher(request: HttpRequest) -> None:
    """`POST /search`: a person with `search.use`, or a key with `search:read`, which is how
    a bank's own agent searches the library in its scope (SRC-01, ACC-04). The 403 names the
    scope it wanted to a key and the permission it wanted to a person."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if not who.has_scope(perms.SCOPE_SEARCH_READ):
            raise deny(perms.SCOPE_SEARCH_READ)
        return
    require_any(request, perms.SEARCH_USE)


@router.post(
    "/search",
    response=SearchResponse,
    auth=SESSION_OR_KEY,
    operation_id="search",
    by_alias=True,
    summary="Find an obligation, a provision or a change in the shared library",
)
@answers_problems
def search(request: HttpRequest, body: SearchRequest) -> SearchResponse:
    """Find obligations, provisions and registered changes in the shared library, by
    identifier or by concept, as they stood on a chosen date (SRC-01, SRC-02).

    Who may call it: a person with `search.use`, on their own session, or a bank's own key
    holding the `search:read` scope, which is how an agent the bank runs itself searches. A
    key of an agent access entry finds only what that entry may open: the bank's scope and
    then the entry's own, its departments' and products' terms, so a trading agent never
    finds a card rule, and it cannot ask for what the scope holds back (`inFootprint`
    false). A platform key belongs to no bank and gets 404; bleqq's watch agents use
    `POST /search/similar`.

    What comes back: one ranked page, best first. `limit` defaults to 20 and may not
    exceed 100; a larger number answers 422 naming the field and is never clamped. The
    bank's regulatory scope and any filter are applied before ranking, so an empty list
    means nothing inside the bank's view matched, not that nothing exists. In a bank that
    has switched its AI features off (`PUT /tenant/ai`), the query reaches no embedding
    model and no reranker: records are found by their words alone and every hit's
    `matchKind` is `keyword`.

    Limits and budgets: the query is at most 500 characters (`SEARCH_QUERY_MAX_CHARS`),
    and a longer one answers 422 rather than being truncated. Each reader may search 60
    times a minute (`SEARCH_RATE_PER_USER_PER_MINUTE`), counted per person rather than per
    bank so one busy colleague cannot lock the others out. The answer arrives inside
    800 ms without the reranker and 1.5 s with it (NFR-02), reported in `Server-Timing`.

    Shape of the call: a read. It is not streamed, it needs no idempotency key, and it
    writes no audit row, because nothing changed. It is a POST so the query never travels
    in a URL: what a reader types is the bank's own text.

    Errors: `rate_limited` when that reader or key has searched more than the limit above
    in the last minute, which is a 429 to wait out and retry rather than a call to change;
    `unknown_key` for a `lang` that is not one of the library's language rows;
    `validation_error` for a query over the cap, a `limit` above 100 or a filter the
    contract does not name; `unknown_filter` (422) when an agent access credential sends
    `inFootprint` false; `not_found` when the session or the key belongs to no bank;
    `permission_denied` without `search.use`, or a key without `search:read`;
    `unauthenticated` without a session or a key.
    """
    # Ungated by design: logic-gate (search.use in a tenant, or a key with search:read; SRC-01, ACC-04).
    require_searcher(request)
    who = principal(request)
    return hybrid.run_search(body, tenant_id=who.tenant_id, user_id=who.subject_id, reader=reader_of(who))


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
    regulatory scope narrows it. A bank's own key may hold the scope too; the text it sends
    is then the bank's own, and while that bank has switched its AI features off it reaches
    no embedding model and no reranker, so every hit's `matchKind` is `keyword`. The text carries no
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
    who = principal(request)
    return hybrid.find_similar(body, caller_id=who.subject_id, tenant_id=who.tenant_id)


@router.post(
    "/ask",
    response=SSE[AskEvent],
    auth=SESSION,
    operation_id="ask",
    by_alias=True,
    summary="Ask a question and get an answer cited to the shared library",
)
@requires_permission(perms.SEARCH_USE)
def ask_question(request: HttpRequest, body: AskRequest) -> Iterator[AskEvent]:
    """Answer a question in the reader's own words, grounded only in the shared library,
    every sentence carrying a citation and a pending change flagged (SRC-03).

    Who may call it: a person with `search.use`, on their own session, in a bank that has
    not switched its AI features off. An API key is refused: Ask is a reading aid for
    people, and the question is tenant text.

    What comes back: an event stream (`text/event-stream`), not one body, because the
    budget is a first token under 2 s (NFR-02) and an answer that waits for its last
    sentence cannot meet it. The events are `start` carrying the answer's id, one
    `statement` per cited sentence, and then either `answer` with the whole answer or
    `problem` with a `code` to branch on. A stream that has begun cannot change its
    status, so a failure found after the first byte arrives as a `problem` event; do not
    read the status line alone as success. The answer rests only on the obligations the
    reader's own search ranks first, inside the bank's regulatory scope and as they stood
    on `asOf`; when none of them answers the question, the `answer` event says `noAnswer`
    and no model is asked to guess.

    Limits and budgets: the question is at most 2000 characters
    (`ASK_QUESTION_MAX_CHARS`), and a longer one answers 422 before any stream opens. Each
    reader may ask 10 questions a minute (`ASK_RATE_PER_USER_PER_MINUTE`), counted per
    person, and may have at most 2 answers streaming at once (`ASK_STREAMS_PER_USER`); an
    answer stops counting the moment its stream closes. The model is given at most 6 passages (`ASK_RETRIEVAL_DEPTH`) and may write at
    most 1024 tokens (`ASK_MAX_TOKENS`). The first token arrives inside 2 s (NFR-02).

    Shape of the call: a read of the library and a model call. It needs no idempotency
    key, because asking twice costs two model calls and changes no record, and it writes
    no audit row, only the AI log row every model call writes (AUD-02), also when the
    reader leaves before the answer is finished. The question is the only text of the
    bank's own that ever reaches a model (D-07), and it reaches no log line, no Sentry
    event and no URL.

    Errors, each a status with a problem body before any stream opens:
    `feature_off` (403) when the reader's bank has switched its AI features off, which is
    the bank's decision and not a fault to retry; `rate_limited` (429) when that reader has
    asked more than the limit above in the last minute, or already has as many answers
    streaming as the cap above allows, to wait out and retry;
    `unknown_key` (422) for a `lang` that is not one of the library's language rows;
    `validation_error` (422) for a question over the cap or a field the contract does not
    name; `not_found` (404) when the session belongs to no bank; `permission_denied`
    (403) without `search.use`; `unauthenticated` (401) without a session. After the first
    byte, the one way a stream ends badly is a `problem` event with `model_unavailable`:
    the model could not be reached, declined or ran out of time, and asking again may
    succeed.
    """
    # No `answers_problems` here: this route answers a stream, and a problem response
    # handed back from inside it would be streamed as if it were events. Every refusal is
    # raised instead, and config/api.py turns it into the one problem shape.
    who = principal(request)
    return ask.answer_events(body, tenant_id=who.tenant_id, user_id=who.subject_id)


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
def rate_answer(
    request: HttpRequest,
    body: AnswerFeedbackBody,
    answer_id: str = Path(
        ...,
        description=(
            "The answer to rate, as a UUID: the `id` of the `start` event that `POST /ask` "
            "streamed first, which is also the answer's row in the AI log. It must be an "
            "answer the caller was given themselves. A colleague's answer, another bank's, an "
            "id that is no answer and a value that is not a UUID all answer `not_found`, never "
            "saying which."
        ),
    ),
) -> tuple[int, None]:
    """Record a reader's verdict on one answer — helpful or wrong, with an optional note
    — so the people who tune retrieval know where it fails (AUD-02, SRC-05).

    Who may call it: a person with `search.use`, on their own session, about an answer
    they were given themselves. A colleague's answer, or another bank's, answers 404, so
    nobody replaces the verdict of the person who asked.

    What comes back: 204 and no body.

    Limits and budgets: the note is at most 2000 characters
    (`SEARCH_FEEDBACK_NOTE_MAX_CHARS`); longer answers 422. The ordinary 250 ms API
    budget applies.

    Shape of the call: the one write in this contract. It goes through the audit trail
    like any other write, and it needs no idempotency key because it is idempotent by
    nature: the same verdict and note on the same answer twice leaves one row and one
    audit row. A different verdict replaces the earlier one, and the audit trail keeps
    both. Neither the question nor the answer nor the note reaches the audit row.

    Errors: `not_found` (404) for an answer the caller was not given themselves, or a
    session that belongs to no bank; `validation_error` (422) for a verdict other than
    `helpful` or `wrong`, a note over the cap or a field the contract does not name;
    `permission_denied` (403) without `search.use`; `unauthenticated` (401) without a
    session.
    """
    who = principal(request)
    ask.rate_answer(uuid_or_404(answer_id), body, tenant_id=who.tenant_id, user_id=who.subject_id)
    return 204, None


# ---------------------------------------------------------------------------------------
# The evaluation set in the platform console (SRC-05, ADM-02): platform staff holding
# `eval.manage` read the questions and the recorded runs and add a question. No bank's
# session reaches the tables at all (search 0002). Recording a run is a command, not a
# route: `POST /eval/runs` waits for chunk 14's job runner.
# ---------------------------------------------------------------------------------------
@router.get(
    "/eval/questions",
    response=EvalQuestionPage,
    auth=SESSION,
    operation_id="listEvalQuestions",
    by_alias=True,
    summary="See the questions the release gate scores search with",
)
@requires_permission(perms.EVAL_MANAGE)
def list_eval_questions(request: HttpRequest, page: Query[PageQuery]) -> EvalQuestionPage:
    """Returns the search evaluation set, ordered by key, one page at a time: each labelled
    question, the language it is asked in, the library records a good answer contains by
    stable key, what it expects to win it, and whether the release gate of this build scores
    it (`inGate`). Retired questions stay in the list with `active` false. Call it from the
    platform console's evaluation page.

    A person's session only, holding the platform permission `eval.manage`, which a library
    editor holds; no session inside a bank and no API key can read it. It changes nothing and
    writes nothing to the audit log. An empty set is a 200 with `total` 0.

    Errors: `validation_error` when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` without `eval.manage`; `unauthenticated` without a session.
    """
    items, total = eval_sets.list_questions(limit=page.limit, offset=page.offset)
    return EvalQuestionPage(items=items, total=total)


@router.post(
    "/eval/questions",
    response={201: EvalQuestionOut},
    auth=SESSION,
    operation_id="createEvalQuestion",
    by_alias=True,
    summary="Add a question to the search evaluation set",
)
@requires_permission(perms.EVAL_MANAGE)
@answers_problems
def create_eval_question(request: HttpRequest, body: EvalQuestionInput) -> tuple[int, EvalQuestionOut]:
    """Adds one labelled question to the evaluation set and answers it as stored. Call it
    when search missed something a reader needed, or to cover a language or a phrasing the
    set does not test yet.

    The question is not yet in the gate: the release gate reads
    `backend/eval/retrieval.jsonl`, so the answer says `inGate` false until someone runs the
    dump_eval_questions command, reviews the diff and ships it. Until then the
    record_eval_run command scores it, but no build fails on it.

    A person's session only, holding the platform permission `eval.manage`, which a library
    editor holds. No passkey step-up and no `If-Match`: a question is a test of search, not a
    decision about the law, and it is never edited, only added. The row and its audit row,
    which names who added it and the key but not the question's text, are written in one
    transaction, and every refusal comes first, so a refused call stores nothing.

    Errors: `duplicate_key` (409) when the set already has a question with that `key`;
    `unknown_key` (422) when `lang` names no language row; `validation_error` (422) for a
    body the schema refuses, including a key that breaks its pattern, a question over the
    cap or a field the schema does not name; `permission_denied` (403) without
    `eval.manage`; `unauthenticated` (401) without a session.
    """
    return 201, eval_sets.create_question(actor=actor_for(request), body=body)


@router.get(
    "/eval/runs",
    response=EvalRunPage,
    auth=SESSION,
    operation_id="listEvalRuns",
    by_alias=True,
    summary="See how search scored on the evaluation set, run by run",
)
@requires_permission(perms.EVAL_MANAGE)
def list_eval_runs(request: HttpRequest, page: Query[PageQuery]) -> EvalRunPage:
    """Returns the recorded runs of the evaluation set, newest first, one page at a time:
    which retrieval chain each scored and whether it was a stand-in, recall at 10 and MRR
    overall, per language and per match kind, and what every question got back. Call it
    from the platform console to see whether search got better or worse. Runs are recorded
    by the record_eval_run command; the release gate's own verdict is in CI, against its
    baseline.

    A person's session only, holding the platform permission `eval.manage`, which a library
    editor holds; no session inside a bank and no API key can read it. It changes nothing and
    writes nothing to the audit log. No run recorded yet is a 200 with `total` 0.

    Errors: `validation_error` when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` without `eval.manage`; `unauthenticated` without a session.
    """
    items, total = eval_sets.list_runs(limit=page.limit, offset=page.offset)
    return EvalRunPage(items=items, total=total)


@router.get(
    "/eval/baseline",
    response=EvalBaselineOut,
    auth=SESSION,
    operation_id="getEvalBaseline",
    by_alias=True,
    summary="See the retrieval scores the release gate holds search to",
)
@requires_permission(perms.EVAL_MANAGE)
def get_eval_baseline(request: HttpRequest) -> EvalBaselineOut:
    """Returns the release gate's accepted retrieval scores in this build, recall at 10 and
    MRR, read from `backend/eval/baseline.json`: the numbers a new build may not drop below
    beyond its tolerance. Call it from the platform console's evaluation page to set a
    run's scores beside them.

    Until a real evaluator has scored the retrieval track, `recorded` is false and every
    score is null, never zero: a zero would claim search found nothing. The baseline changes
    only through a reviewed commit that re-records it, never through this API.

    A person's session only, holding the platform permission `eval.manage`, which a library
    editor holds; no session inside a bank and no API key can read it. It changes nothing and
    writes nothing to the audit log.

    Errors: `permission_denied` without `eval.manage`; `unauthenticated` without a session.
    """
    return eval_sets.retrieval_baseline()

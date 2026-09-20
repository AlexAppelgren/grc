"""Routes of the search app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

Four operations, the designed contract's (`docs/inputs/openapi.yaml`). Each one hands its
validated body to the module of the logic package that will build it — `hybrid.py` for
searching and for the agents' nearest-neighbour read, `ask.py` for the answer and its
feedback — and each of those answers `not_built` until that package lands (PARALLEL_PLAN
rule 3). The gate runs first, so a caller without it is refused before it learns whether
anything is built.

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


@router.post("/search", response=SearchResponse, auth=SESSION, operation_id="search", by_alias=True)
@requires_permission(perms.SEARCH_USE)
@answers_problems
def search(request: HttpRequest, body: SearchRequest) -> SearchResponse:
    return hybrid.run_search(body, tenant_id=principal(request).tenant_id)


@router.post("/search/similar", response=SearchResponse, auth=ApiKeyAuth(), operation_id="findSimilar", by_alias=True)
@requires_scope(perms.SCOPE_SEARCH_READ)
@answers_problems
def find_similar(request: HttpRequest, body: SimilarRequest) -> SearchResponse:
    return hybrid.find_similar(body)


@router.post("/ask", response=SSE[AskEvent], auth=SESSION, operation_id="ask", by_alias=True)
@requires_permission(perms.SEARCH_USE)
@answers_problems
def ask_question(request: HttpRequest, body: AskRequest, response: HttpResponse) -> Iterator[AskEvent]:
    who = principal(request)
    return ask.answer_events(body, tenant_id=who.tenant_id, user_id=who.subject_id, response=response)


@router.post(
    "/answers/{answer_id}/feedback",
    response={204: None},
    auth=SESSION,
    operation_id="rateAnswer",
    by_alias=True,
)
@requires_permission(perms.SEARCH_USE)
@answers_problems
def rate_answer(request: HttpRequest, answer_id: str, body: AnswerFeedbackBody) -> tuple[int, None]:
    ask.rate_answer(uuid_or_404(answer_id), body, user_id=principal(request).subject_id)
    return 204, None

"""Ask (SRC-03): an answer grounded only in the retrieved library chunks, every statement
cited, pending changes flagged, "no answer" instead of a guess.

`POST /ask` answers a stream of the events `schemas.py` declares: `start` with the
answer's id, a `statement` per cited sentence, and either `answer` or `problem` to close
it. api.py declares the route `SSE[AskEvent]`, so everything this module yields leaves as
one `data:` frame of a `text/event-stream` `StreamingHttpResponse`, and the first token
can arrive well inside the 2 s budget (playbook 10, SRC-S9) however long the whole answer
takes. A refusal the route finds before the first byte — no session, no permission, a
question over `ASK_QUESTION_MAX_CHARS` — is still a status with a problem body.

Contract only. `c7-ask-backend` builds the answer and `c7-ai-log-backend` the
`ai_generation` row every call must write; until they land the stream carries one
`not_built` problem event and `rate_answer` raises 501, both behind the gates api.py
already applies (PARALLEL_PLAN rule 3). No model is called from here, and the question is
the only tenant text that will ever reach one (D-07).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

from django.http import HttpResponse

from apps.search.schemas import AnswerFeedbackBody, AskEvent, AskProblemEvent, AskRequest
from apps.shared.errors import ProblemError

NOT_BUILT_CODE = "not_built"
NOT_BUILT = "Ask is not switched on yet."


def answer_events(
    body: AskRequest, *, tenant_id: object, user_id: object, response: HttpResponse
) -> Iterator[AskEvent]:
    """`POST /ask`. Writes an `ai_generation` row per call (AUD-02) and streams the answer
    labelled `aiGenerated` until a person confirms it (D-04).

    The status belongs here and not in api.py because this module owns the whole stream:
    while nothing is built the stream is a 501 carrying one `not_built` problem event, and
    the package that builds the answer drops that line rather than reopening a route file
    it does not own."""
    response.status_code = 501
    return iter((AskProblemEvent(code=NOT_BUILT_CODE, detail=NOT_BUILT),))


def rate_answer(answer_id: uuid.UUID, body: AnswerFeedbackBody, *, user_id: object) -> None:
    """`POST /answers/{answerId}/feedback`. A reader's verdict on an answer, which the
    evaluation set reads back (SRC-05)."""
    raise ProblemError(status=501, code=NOT_BUILT_CODE, detail=NOT_BUILT)

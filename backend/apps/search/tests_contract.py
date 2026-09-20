"""The search and ask API contract (SRC-01 to SRC-03, chunk 7).

This is the contract package's proof: the four operations exist at their designed
paths, in their designed shape, behind their real gates, and say `not_built` until the
logic packages land (`hybrid.py` for search and similar, `ask.py` for the answer and its
feedback). The gate runs first, so an unauthenticated or unauthorised caller is refused
before it learns whether anything is built.

`POST /ask` is the one that answers a stream (`text/event-stream`), so its proof is the
content type and the events, not a JSON body; and the proof that the caps still run in
front of the stream, because a question over the cap must never open one.

The scenarios of app.md stay skipped: nothing here proves a requirement, only the
contract other packages and the frontend data layer are written against.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.conf import settings
from django.test import TestCase

from apps.shared import permissions as perms
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)

SEARCH = "/api/v1/search"
SIMILAR = "/api/v1/search/similar"
ASK = "/api/v1/ask"
FEEDBACK = f"/api/v1/answers/{uuid.uuid4()}/feedback"

SESSION_HEADERS = {"authorization": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}
KEY_HEADERS = {"x-api-key": API_KEY_FOR_TESTS}

SEARCH_BODY = {"q": "FFFS 2017:2"}
SIMILAR_BODY = {"text": "nudging in onboarding"}
ASK_BODY = {"question": "What must we report quarterly?"}
FEEDBACK_BODY = {"feedback": "helpful"}


def events_of(response: Any) -> list[dict[str, Any]]:
    """The events a `text/event-stream` response carried, in order: one `data:` frame each."""
    body = b"".join(response.streaming_content).decode()
    return [json.loads(line.removeprefix("data: ")) for line in body.splitlines() if line.startswith("data: ")]


class SearchApiTestCase(TestCase):
    """One typed way to post a body with the caller's credential."""

    def post(self, path: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
        return self.client.post(path, body, content_type="application/json", headers=headers)


class SearchContractTests(SearchApiTestCase):
    """Every search operation says not_built behind its own gate (plan rule 3)."""

    # -- the reader's three routes ------------------------------------------------------
    def test_search_answers_not_built_for_a_reader(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(SEARCH, SEARCH_BODY, SESSION_HEADERS)
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["code"], "not_built")

    def test_answer_feedback_answers_not_built_for_a_reader(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(FEEDBACK, FEEDBACK_BODY, SESSION_HEADERS)
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["code"], "not_built")

    # -- the agents' route ---------------------------------------------------------------
    def test_similar_answers_not_built_for_a_key_with_the_scope(self) -> None:
        with stub_api_key(agent_principal(scopes={perms.SCOPE_SEARCH_READ})):
            response = self.post(SIMILAR, SIMILAR_BODY, KEY_HEADERS)
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["code"], "not_built")


class AskStreamContractTests(SearchApiTestCase):
    """Ask is a stream (SRC-03, SRC-S9): the answer's first token has 2 s, which one JSON
    body cannot promise. The stub opens the stream and closes it with one problem event."""

    def test_ask_streams_one_not_built_problem_event_and_closes(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(ASK, ASK_BODY, SESSION_HEADERS)
        self.assertEqual(response.status_code, 501)
        self.assertTrue(response["Content-Type"].startswith("text/event-stream"), response["Content-Type"])
        # Nothing between the answer and the reader may hold the events back (playbook 10).
        self.assertEqual(response["X-Accel-Buffering"], "no")
        self.assertEqual(response["Cache-Control"], "no-cache")
        events = events_of(response)
        self.assertEqual([event["event"] for event in events], ["problem"])
        self.assertEqual(events[0]["code"], "not_built")

    def test_a_question_over_the_cap_never_opens_a_stream(self) -> None:
        # The cap is a trust boundary: the question is the one tenant text a model sees.
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(ASK, {"question": "x" * (settings.ASK_QUESTION_MAX_CHARS + 1)}, SESSION_HEADERS)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("event-stream", response["Content-Type"])
        self.assertEqual(response.json()["code"], "validation_error")


class SearchGateTests(SearchApiTestCase):
    """The gate runs before the stub: a caller without it never reaches the answer."""

    def test_every_route_refuses_an_unauthenticated_caller(self) -> None:
        for path, body in ((SEARCH, SEARCH_BODY), (SIMILAR, SIMILAR_BODY), (ASK, ASK_BODY), (FEEDBACK, FEEDBACK_BODY)):
            with self.subTest(path=path):
                response = self.post(path, body)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("event-stream", response["Content-Type"])

    def test_a_person_without_search_use_is_refused(self) -> None:
        for path, body in ((SEARCH, SEARCH_BODY), (ASK, ASK_BODY), (FEEDBACK, FEEDBACK_BODY)):
            with self.subTest(path=path):
                with stub_session(user_principal(permissions=frozenset(), tenant_id=uuid.uuid4())):
                    response = self.post(path, body, SESSION_HEADERS)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["requiredPermission"], perms.SEARCH_USE)

    def test_similar_refuses_a_key_without_the_search_scope(self) -> None:
        with stub_api_key(agent_principal(scopes={perms.SCOPE_LIBRARY_READ})):
            response = self.post(SIMILAR, SIMILAR_BODY, KEY_HEADERS)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["requiredPermission"], perms.SCOPE_SEARCH_READ)

    def test_similar_refuses_a_person_because_it_is_the_agents_route(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(SIMILAR, SIMILAR_BODY, SESSION_HEADERS)
        self.assertEqual(response.status_code, 401)

    def test_search_refuses_an_api_key_because_it_is_a_persons_route(self) -> None:
        with stub_api_key(agent_principal(scopes={perms.SCOPE_SEARCH_READ})):
            response = self.post(SEARCH, SEARCH_BODY, KEY_HEADERS)
        self.assertEqual(response.status_code, 401)


class SearchRequestValidationTests(SearchApiTestCase):
    """The request bodies are validated at the trust boundary, before any logic exists."""

    def test_a_search_without_a_query_is_422(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(SEARCH, {}, SESSION_HEADERS)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_a_limit_above_the_maximum_is_refused_not_clamped(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(SEARCH, {"q": "custody", "limit": 1000}, SESSION_HEADERS)
        self.assertEqual(response.status_code, 422)

    def test_an_unknown_hit_type_is_refused(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(SEARCH, {"q": "custody", "types": ["case"]}, SESSION_HEADERS)
        self.assertEqual(response.status_code, 422)

    def test_an_unknown_feedback_value_is_refused(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(FEEDBACK, {"feedback": "excellent"}, SESSION_HEADERS)
        self.assertEqual(response.status_code, 422)

    def test_a_field_the_contract_does_not_name_is_refused(self) -> None:
        # A write body forbids extras, so a tone or a filter nobody built never rides along.
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(SEARCH, {"q": "custody", "tone": "warning"}, SESSION_HEADERS)
        self.assertEqual(response.status_code, 422)

    def test_a_register_filter_the_overlay_cannot_answer_is_refused(self) -> None:
        # Applicability and compliance status arrive with the register (chunk 8). Until
        # then a filter on them is a 422, never a 200 that quietly ignored it.
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(SEARCH, {"q": "custody", "filters": {"applicability": "applies"}}, SESSION_HEADERS)
        self.assertEqual(response.status_code, 422)

    def test_the_screens_jurisdiction_and_duty_type_filters_are_accepted_as_keys(self) -> None:
        # SRC-S3 filters by jurisdiction "SE" and duty type "reporting", both keys.
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(
                SEARCH,
                {"q": "custody", "filters": {"jurisdiction": "SE", "dutyType": "reporting"}},
                SESSION_HEADERS,
            )
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["code"], "not_built")


class SearchOperationsAreRegisteredTests(TestCase):
    """The designed operation ids and paths, so a later rename is caught here and not by
    the contract-drift gate after a merge."""

    def test_the_four_designed_operations_are_registered(self) -> None:
        from apps.shared.routes import iter_operations
        from config.api import api

        registered = {(op.method, op.path): op.operation_id for op in iter_operations(api)}
        self.assertEqual(registered.get(("POST", "/search")), "search")
        self.assertEqual(registered.get(("POST", "/search/similar")), "findSimilar")
        self.assertEqual(registered.get(("POST", "/ask")), "ask")
        self.assertEqual(registered.get(("POST", "/answers/{answer_id}/feedback")), "rateAnswer")

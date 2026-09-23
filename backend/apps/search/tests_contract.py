"""The search and ask API contract (SRC-01 to SRC-03, chunk 7).

This is the contract package's proof: the four operations exist at their designed
paths, in their designed shape, behind their real gates. Search, similar and Ask answer
for real (`hybrid.py`, `ask.py`); the reader's verdict on an answer still says
`not_built` until its logic lands. The gate runs first, so an unauthenticated or
unauthorised caller is refused before it learns whether anything is built.

`POST /ask` is the one that answers a stream (`text/event-stream`), so its proof is the
content type and the events, not a JSON body; and the proof that every refusal still
runs in front of the stream, because a stream that has begun cannot change its status.

What an answer says is proved in tests_ask.py and in SRC-S4 to SRC-S6; nothing here
proves a requirement, only the contract the frontend data layer is written against.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, ClassVar

from django.conf import settings
from django.db import transaction
from django.test import TestCase

from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import Tenant
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
    """Every search operation runs behind its own gate; the one not built yet says so."""

    # -- the reader's three routes ------------------------------------------------------
    def test_search_is_built_and_runs_behind_the_readers_gate(self) -> None:
        # `POST /search` answers for real since `c7-hybrid-search-core`; what it finds is
        # proved in tests_hybrid.py and in SRC-S1 to SRC-S3. What belongs here is that the
        # gate passed and the logic ran: this principal's company does not exist, and a
        # tenant read answers a company it cannot find with 404, never 403.
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(SEARCH, SEARCH_BODY, SESSION_HEADERS)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    def test_answer_feedback_answers_not_built_for_a_reader(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(FEEDBACK, FEEDBACK_BODY, SESSION_HEADERS)
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["code"], "not_built")

    # -- the agents' route ---------------------------------------------------------------
    def test_similar_is_built_and_runs_behind_the_agents_scope(self) -> None:
        # `POST /search/similar` answers for real since `c7-search-similar-limits`; what it
        # finds is proved in tests_similar.py. What belongs here is that the scope gate
        # passed and the logic ran: nothing is indexed in this test database, and an
        # empty answer is a 200 with an empty list, never a 404 (playbook 4.4).
        with stub_api_key(agent_principal(scopes={perms.SCOPE_SEARCH_READ})):
            response = self.post(SIMILAR, SIMILAR_BODY, KEY_HEADERS)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["items"], [])


class AskStreamContractTests(SearchApiTestCase):
    """Ask is a stream (SRC-03, SRC-S9): the answer's first token has 2 s, which one JSON
    body cannot promise. Every refusal is a status and a problem body before it opens."""

    tenant: ClassVar[Tenant]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant(slug="ask-contract")

    def ask(self, body: dict[str, Any], tenant_id: uuid.UUID | None = None) -> Any:
        """One question from a reader of `tenant_id`, the contract's own bank by default."""
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=tenant_id or self.tenant.id)):
            return self.post(ASK, body, SESSION_HEADERS)

    def assert_refused_before_a_stream(self, response: Any, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.content)
        self.assertNotIn("event-stream", response["Content-Type"])
        self.assertEqual(response.json()["code"], code)

    def test_ask_streams_a_start_event_and_a_closing_answer(self) -> None:
        # This library is empty, so nothing can ground an answer and no model is asked: the
        # stream is the whole contract, `start` and then an `answer` that says so.
        response = self.ask(ASK_BODY)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/event-stream"), response["Content-Type"])
        # Nothing between the answer and the reader may hold the events back (playbook 10).
        self.assertEqual(response["X-Accel-Buffering"], "no")
        self.assertEqual(response["Cache-Control"], "no-cache")
        events = events_of(response)
        self.assertEqual([event["event"] for event in events], ["start", "answer"])
        self.assertEqual(events[0]["id"], events[1]["answer"]["id"])
        self.assertTrue(events[1]["answer"]["noAnswer"])

    def test_a_question_over_the_cap_never_opens_a_stream(self) -> None:
        # The cap is a trust boundary: the question is the one tenant text a model sees.
        response = self.ask({"question": "x" * (settings.ASK_QUESTION_MAX_CHARS + 1)})
        self.assert_refused_before_a_stream(response, 422, "validation_error")

    def test_a_language_the_library_does_not_hold_never_opens_a_stream(self) -> None:
        response = self.ask({**ASK_BODY, "lang": "xx"})
        self.assert_refused_before_a_stream(response, 422, "unknown_key")

    def test_a_bank_that_switched_its_ai_off_never_opens_a_stream(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            Tenant.objects.filter(pk=self.tenant.id).update(ai_enabled=False)
        response = self.ask(ASK_BODY)
        self.assert_refused_before_a_stream(response, 403, "feature_off")

    def test_a_session_in_no_bank_never_opens_a_stream(self) -> None:
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=None)):
            response = self.post(ASK, ASK_BODY, SESSION_HEADERS)
        self.assert_refused_before_a_stream(response, 404, "not_found")


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
        # SRC-S3 filters by jurisdiction and duty type, both keys and never labels. The
        # keys are the seeded rows' own: jurisdictions are seeded lowercased (`se`, not
        # the fixture's display form "SE"), so the contract's example is the real key.
        with stub_session(user_principal(permissions={perms.SEARCH_USE}, tenant_id=uuid.uuid4())):
            response = self.post(
                SEARCH,
                {"q": "custody", "filters": {"jurisdiction": "se", "dutyType": "reporting"}},
                SESSION_HEADERS,
            )
        # Past validation and into the logic, which then cannot find this principal's
        # company; a filter the contract did not name would have been refused at 422.
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")


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


class ContractDocumentationTests(TestCase):
    """Alex's API rule of 2026-09-20, proved over the four search operations.

    Every property of every shape this app declares says what the fact means to a bank,
    where it comes from and what a reader must not conclude from it; every value set is
    spelled out in words; every limit that matters is in words as well as in the schema
    keywords; and every shape carries a realistic example from the prototype's data.

    Proven to fail 2026-09-20 by deleting the description of `SearchHit.score` (the
    property assertion named it), by emptying `SearchMatchKind`'s member list (the kind
    assertion named `concept`), and by removing `SearchRequest`'s example.
    """

    schema: ClassVar[dict[str, Any]]
    components: ClassVar[dict[str, Any]]
    ours: ClassVar[dict[str, Any]]

    @classmethod
    def setUpTestData(cls) -> None:
        from apps.search import schemas as search_schemas
        from config.api import api

        cls.schema = api.get_openapi_schema()
        cls.components = cls.schema["components"]["schemas"]
        # Only the shapes this app declares: a shape another app owns is documented there.
        cls.ours = {
            name: body
            for name, body in cls.components.items()
            if getattr(getattr(search_schemas, name, None), "__module__", None) == search_schemas.__name__
        }

    def test_the_app_declares_the_shapes_the_contract_names(self) -> None:
        # A guard that matched nothing would pass every assertion below.
        self.assertEqual(
            set(self.ours),
            {
                "SearchHitType",
                "SearchMatchKind",
                "SearchFilters",
                "SearchRequest",
                "SimilarRequest",
                "SearchHit",
                "SearchResponse",
                "AskRequest",
                "AnswerCitation",
                "AnswerStatement",
                "Answer",
                "AskStartEvent",
                "AskStatementEvent",
                "AskAnswerEvent",
                "AskProblemEvent",
                "AnswerFeedbackKind",
                "AnswerFeedbackBody",
                # The evaluation set in the console (SRC-05, ADM-02).
                "EvalScores",
                "EvalRunConfig",
                "EvalRunMetrics",
                "EvalQuestionResult",
                "EvalQuestionInput",
                "EvalQuestionOut",
                "EvalQuestionPage",
                "EvalRunOut",
                "EvalRunPage",
                "EvalBaselineOut",
            },
        )

    def test_every_property_says_what_it_means_where_it_came_from_and_what_it_is_not(self) -> None:
        for name, body in sorted(self.ours.items()):
            for field, spec in sorted(body.get("properties", {}).items()):
                with self.subTest(schema=name, field=field):
                    description = spec.get("description", "")
                    self.assertGreater(len(description), 80, "a property needs more than a restated name")
                    self.assertIn("Source:", description, "say where the fact comes from")
                    self.assertIn("Do not ", description, "say what a reader must not conclude or do")

    def test_every_shape_carries_a_realistic_example(self) -> None:
        for name, body in sorted(self.ours.items()):
            if "properties" not in body:
                continue  # a kind is a value set, not a shape; its members are the example
            with self.subTest(schema=name):
                self.assertTrue(body.get("examples"), "every request body and every response needs an example")

    def test_every_fixed_kind_lists_every_member_in_words(self) -> None:
        for name, body in sorted(self.ours.items()):
            if "enum" not in body:
                continue
            with self.subTest(kind=name):
                description = body.get("description", "")
                for member in body["enum"]:
                    self.assertIn(f"`{member}`", description, "a kind names every member and what changes for it")

    def test_every_vocabulary_backed_key_names_its_vocabulary_and_its_seeded_keys(self) -> None:
        # A key field is not a kind: the values are rows an admin manages, so the contract
        # says which list they come from and what a bank finds there on day one.
        expected = {
            ("SearchFilters", "jurisdiction"): ("`jurisdiction` vocabulary", ["`eu`", "`se`", "`dk`", "`no`", "`fi`"]),
            ("SearchFilters", "dutyType"): (
                "`duty_type` vocabulary",
                ["`conduct`", "`disclosure`", "`record_keeping`", "`reporting`", "`governance`", "`technical`"],
            ),
            ("SearchFilters", "termIds"): ("taxonomy", ["`regime`", "`legal_entity`", "`lifecycle_stage`"]),
            ("SearchHit", "urgency"): (
                "`urgency` vocabulary",
                ["`act_now`", "`within_3_months`", "`six_months_plus`", "`monitor`", "`no_action`"],
            ),
            ("SearchRequest", "lang"): ("`Language` list", ["`en`", "`sv`", "`da`", "`nb`", "`fi`"]),
            ("AskRequest", "lang"): ("`Language` list", ["`en`", "`sv`", "`da`", "`nb`", "`fi`"]),
        }
        for (schema, field), (vocabulary, keys) in sorted(expected.items()):
            with self.subTest(schema=schema, field=field):
                description = self.components[schema]["properties"][field]["description"]
                self.assertIn(vocabulary, description)
                for key in keys:
                    self.assertIn(key, description)

    def test_the_page_size_and_the_query_caps_are_stated_in_words_as_well_as_in_the_keywords(self) -> None:
        for schema in ("SearchRequest", "SimilarRequest"):
            with self.subTest(schema=schema):
                limit = self.components[schema]["properties"]["limit"]
                self.assertEqual(limit["default"], settings.API_PAGE_SIZE_DEFAULT)
                self.assertEqual(limit["maximum"], settings.API_PAGE_SIZE_MAX)
                self.assertIn(str(settings.API_PAGE_SIZE_DEFAULT), limit["description"])
                self.assertIn(str(settings.API_PAGE_SIZE_MAX), limit["description"])
        caps = {
            ("SearchRequest", "q"): settings.SEARCH_QUERY_MAX_CHARS,
            ("SimilarRequest", "text"): settings.SEARCH_SIMILAR_MAX_CHARS,
            ("AskRequest", "question"): settings.ASK_QUESTION_MAX_CHARS,
            ("AnswerFeedbackBody", "note"): settings.SEARCH_FEEDBACK_NOTE_MAX_CHARS,
        }
        for (schema, field), cap in sorted(caps.items()):
            with self.subTest(schema=schema, field=field):
                spec = self.components[schema]["properties"][field]
                self.assertEqual(spec["maxLength"], cap)
                self.assertIn(str(cap), spec["description"])

    def test_every_operation_says_who_may_call_it_what_it_costs_and_how_it_answers(self) -> None:
        operations = {
            "/api/v1/search": ("800 ms", "not streamed", "no idempotency key"),
            "/api/v1/search/similar": ("800 ms", "Not streamed", "no idempotency key"),
            "/api/v1/ask": ("2 s", "text/event-stream", "needs no idempotency key"),
            "/api/v1/answers/{answer_id}/feedback": ("250 ms", "204", "needs no idempotency key"),
        }
        for path, phrases in sorted(operations.items()):
            with self.subTest(path=path):
                # A docstring wraps where the line ends, so compare on one line.
                description = " ".join(self.schema["paths"][path]["post"].get("description", "").split())
                self.assertIn("Who may call it", description)
                for phrase in phrases:
                    self.assertIn(phrase, description)

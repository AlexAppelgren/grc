"""The console's evaluation routes (SRC-05, ADM-02): GET and POST /eval/questions,
GET /eval/runs and GET /eval/baseline, for platform staff holding `eval.manage` and nobody else, paged, and the one
write audited.

The routes are driven through the real session and the audit-asserting client, so a 2xx
write that left no audit row fails here as well as in the guard.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

from apps.library.seeds import seed_languages
from apps.search import eval_sets
from apps.search.models import EvalQuestion
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in

V1 = "/api/v1"
ACTOR = Actor.system("tests_eval_routes")
NEW_QUESTION: dict[str, Any] = {
    "key": "r-sv-90",
    "lang": "sv",
    "question": "kostnader och avgifter före tjänsten",
    "expected": ["obl-costs-charges"],
    "matchKind": "concept",
    "notes": "Swedish phrasing of the cost disclosure.",
}


class EvalRouteTests(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        eval_sets.seed_questions(actor=ACTOR)
        self.editor = sign_in(factories.platform_user(roles=("library_editor",)))

    def _run(self, retriever: str = "stand-in") -> None:
        eval_sets.record_run(
            actor=ACTOR,
            scored={
                "config": {"retriever": retriever, "is_mock": True, "questions": 1},
                "metrics": {
                    "overall": {"recall_at_10": 0.5, "mrr": 0.25},
                    "per_language": {"en": {"recall_at_10": 0.5, "mrr": 0.25}},
                    "per_match_kind": {"keyword": {"recall_at_10": 0.5, "mrr": 0.25}},
                },
                "results": [{"question_key": "r-en-01", "returned": ["obl-costs-charges"], "recall_at_10": 0.5, "mrr": 0.25}],
            },
        )

    def test_a_library_editor_pages_through_the_set_by_key(self) -> None:
        total = EvalQuestion.objects.count()

        response = self.client.get(f"{V1}/eval/questions?limit=2&offset=1", **self.editor)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("Server-Timing", response.headers)
        body = response.json()
        self.assertEqual(body["total"], total)
        keys = sorted(EvalQuestion.objects.values_list("key", flat=True))
        self.assertEqual([item["key"] for item in body["items"]], keys[1:3])
        first = body["items"][0]
        self.assertEqual(
            set(first),
            {"id", "key", "lang", "question", "expected", "matchKind", "asOf", "via", "notes", "active", "inGate"},
        )
        self.assertTrue(first["inGate"], "a question of the gate's file is in the gate")

    def test_a_library_editor_adds_a_question_that_is_not_yet_in_the_gate(self) -> None:
        response = self.client.post(f"{V1}/eval/questions", NEW_QUESTION, content_type="application/json", **self.editor)

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["key"], body["lang"], body["matchKind"]), ("r-sv-90", "sv", "concept"))
        self.assertEqual((body["active"], body["inGate"], body["asOf"]), (True, False, None))
        stored = EvalQuestion.objects.get(key="r-sv-90")
        self.assertEqual(list(stored.expected), ["obl-costs-charges"])
        event = AuditEvent.objects.get(action=eval_sets.QUESTION_ADDED, subject_id=stored.id)
        self.assertIsNone(event.tenant_id)
        self.assertEqual(event.subject_title, "r-sv-90")
        self.assertNotIn(NEW_QUESTION["question"], f"{event.summary} {event.after}")

    def test_the_write_refuses_a_taken_key_an_unknown_language_and_a_malformed_body(self) -> None:
        cases = [
            ({**NEW_QUESTION, "key": "r-en-01"}, 409, "duplicate_key"),
            ({**NEW_QUESTION, "lang": "xx"}, 422, "unknown_key"),
            ({**NEW_QUESTION, "key": "Has Spaces"}, 422, "validation_error"),
            ({**NEW_QUESTION, "matchKind": "semantic"}, 422, "validation_error"),
            ({**NEW_QUESTION, "question": "x" * 501}, 422, "validation_error"),
            ({**NEW_QUESTION, "expected": [f"obl-{n}" for n in range(101)]}, 422, "validation_error"),
            ({**NEW_QUESTION, "tone": "positive"}, 422, "validation_error"),
        ]
        before = EvalQuestion.objects.count()
        for payload, status, code in cases:
            with self.subTest(code=code, payload=payload):
                response = self.client.post(f"{V1}/eval/questions", payload, content_type="application/json", **self.editor)
                self.assertEqual(response.status_code, status, response.content)
                self.assertEqual(response.json()["code"], code)
        self.assertEqual(EvalQuestion.objects.count(), before, "a refused call stored something")

    def test_a_library_editor_reads_the_runs_newest_first(self) -> None:
        self._run("the older run")
        self._run()

        response = self.client.get(f"{V1}/eval/runs?limit=1", **self.editor)

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["total"], 2)
        (run,) = body["items"]
        self.assertEqual(set(run), {"id", "runAt", "config", "metrics", "results"})
        self.assertEqual(run["config"], {"retriever": "stand-in", "isMock": True, "questions": 1})
        self.assertEqual(run["metrics"]["overall"], {"recallAt10": 0.5, "mrr": 0.25})
        self.assertEqual(run["metrics"]["perLanguage"], {"en": {"recallAt10": 0.5, "mrr": 0.25}})
        self.assertEqual(run["results"][0]["questionKey"], "r-en-01")

    def test_the_baseline_reads_an_unrecorded_metric_as_null_never_zero(self) -> None:
        committed = json.loads(eval_sets.BASELINE.read_text(encoding="utf-8"))
        recorded = json.loads(json.dumps(committed))
        recorded["tracks"]["retrieval"].update(recorded=True, recorded_at="2026-09-20T08:00:00+00:00")
        recorded["metrics"].update(retrieval_recall_at_10=0.0, retrieval_mrr=0.8123)
        unrecorded = json.loads(json.dumps(committed))
        unrecorded["tracks"]["retrieval"].update(recorded=False, recorded_at=None)
        unrecorded["metrics"].update(retrieval_recall_at_10=None, retrieval_mrr=None)
        cases: list[tuple[dict[str, Any], dict[str, Any]]] = [
            (unrecorded, {"recorded": False, "recordedAt": None, "recallAt10": None, "mrr": None}),
            # A recorded zero is a score, and stays a zero.
            (recorded, {"recorded": True, "recordedAt": "2026-09-20T08:00:00Z", "recallAt10": 0.0, "mrr": 0.8123}),
        ]
        for baseline, expected in cases:
            with self.subTest(recorded=expected["recorded"]), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "baseline.json"
                path.write_text(json.dumps(baseline), encoding="utf-8")
                with mock.patch.object(eval_sets, "BASELINE", path):
                    response = self.client.get(f"{V1}/eval/baseline", **self.editor)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json(), expected)

    def test_an_empty_list_is_a_200(self) -> None:
        response = self.client.get(f"{V1}/eval/runs", **self.editor)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"items": [], "total": 0})

    def test_a_page_beyond_the_maximum_is_refused(self) -> None:
        for path in ("/eval/questions", "/eval/runs"):
            with self.subTest(path=path):
                response = self.client.get(f"{V1}{path}?limit=101", **self.editor)
                self.assertEqual(response.status_code, 422, response.content)

    def test_nobody_without_eval_manage_reaches_a_route(self) -> None:
        admin = sign_in(factories.platform_user(roles=("platform_admin",)))
        requests = [("get", "/eval/questions"), ("post", "/eval/questions"), ("get", "/eval/runs"), ("get", "/eval/baseline")]
        for method, path in requests:
            with self.subTest(method=method, path=path):
                refused = getattr(self.client, method)(
                    f"{V1}{path}", *([NEW_QUESTION] if method == "post" else []), content_type="application/json", **admin
                )
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assertEqual(refused.json()["requiredPermission"], perms.EVAL_MANAGE)
                anonymous = getattr(self.client, method)(f"{V1}{path}", content_type="application/json")
                self.assertEqual(anonymous.status_code, 401, anonymous.content)
        # A bank's own administrator, last: the request leaves the bank activated.
        bank = factories.tenant(slug="eval-routes-bank")
        bank_admin = sign_in(factories.member_user(bank, roles=("admin",)), tenant=bank)
        for method, path in requests:
            with self.subTest(method=method, path=path, caller="bank"):
                refused = getattr(self.client, method)(
                    f"{V1}{path}", *([NEW_QUESTION] if method == "post" else []), content_type="application/json", **bank_admin
                )
                self.assertEqual(refused.status_code, 403, refused.content)
        tenancy.clear_tenant()
        self.assertFalse(EvalQuestion.objects.filter(key="r-sv-90").exists())

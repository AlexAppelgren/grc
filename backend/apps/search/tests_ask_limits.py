"""A reader's verdict on an answer (SRC-03, AUD-02, SRC-05): `POST /answers/{answerId}/feedback`.

What these tests hold in place:

1. **The verdict lands on the answer's own AI log row**, through the log module's one
   writer, with the audit row that records it in the same transaction: an audit row that
   fails takes the verdict with it.
2. **The audit row carries no text.** Neither the question, nor the answer, nor the
   reader's note reaches the audit row, its outbox row or a log line: the verdict is a
   kind, and the note stays beside the answer for the bank's own review.
3. **The same verdict twice is one verdict.** A repeat writes nothing and answers 204.
4. **An answer is the bank's own.** Another bank's answer, an unknown id and a model call
   that was not an answer all answer 404, and nothing is written.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, ClassVar
from unittest import mock

from django.db import transaction
from django.conf import settings
from django.test import Client, TestCase, override_settings

from apps.governance import ai_log
from apps.governance.models import AiGeneration, AiPurpose
from apps.governance.schemas import AiCitation
from apps.identity.models import User
from apps.library.seeds import seed_languages
from apps.search import ask
from apps.search.schemas import AnswerFeedbackBody, AnswerFeedbackKind
from apps.shared import factories, tenancy
from apps.shared.errors import ProblemError
from apps.shared.models import AuditEvent, OutboxEvent, Tenant
from apps.shared.testing import AuditAssertingClient, sign_in

OUTPUT = "Costs and charges are disclosed before the service is provided [1]."
NOTE = "Ekeroth also needs the itemised disclosure afterwards, not only before."
CITATION = AiCitation(label="FFFS 2017:2, 9 kap. 6 §", url="https://www.fi.se/sv/vara-register/fffs/")


def feedback_path(answer_id: object) -> str:
    return f"/api/v1/answers/{answer_id}/feedback"


class RateAnswerTests(TestCase):
    client_class = AuditAssertingClient

    tenant: ClassVar[Tenant]
    other: ClassVar[Tenant]
    reader: ClassVar[User]

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        cls.tenant = factories.tenant(slug="rate-answer")
        cls.other = factories.tenant(slug="rate-answer-other")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def setUp(self) -> None:
        # Signing in is itself an audited act, so the session opens before any count.
        self.headers = sign_in(self.reader, tenant=self.tenant)

    def answer(self, tenant: Tenant, purpose: AiPurpose = AiPurpose.ANSWER) -> AiGeneration:
        """One model call of `tenant`'s, logged the way Ask logs an answer. The test reads
        from the reader's bank afterwards, whichever bank the row was written in."""
        with transaction.atomic():
            tenancy.activate(tenant.id)  # a bank's own row is written in the bank's zone
            row = ai_log.log_generation(
                purpose=purpose,
                model="mock",
                model_version="0",
                output=OUTPUT,
                citations=[CITATION],
                tenant_id=tenant.id,
                asker_id=self.reader.id,
                prompt_template=ask.PROMPT_TEMPLATE,
                metadata_reported_by_agent=purpose is AiPurpose.SO_WHAT,
            )
        tenancy.activate(self.tenant.id)
        return row

    def rate(self, answer_id: object, body: dict[str, Any]) -> Any:
        return self.client.post(feedback_path(answer_id), body, content_type="application/json", **self.headers)

    def row(self, answer: AiGeneration) -> AiGeneration:
        assert answer.tenant_id is not None
        tenancy.activate(answer.tenant_id)
        row = AiGeneration.objects.get(pk=answer.pk)
        tenancy.activate(self.tenant.id)
        return row

    # -- the verdict ----------------------------------------------------------------------
    def test_the_verdict_and_the_note_land_on_the_answers_row_with_one_audit_row(self) -> None:
        answer = self.answer(self.tenant)
        before = AuditEvent.objects.count()

        response = self.rate(answer.id, {"feedback": "wrong", "note": NOTE})

        self.assertEqual(response.status_code, 204, response.content)
        row = self.row(answer)
        self.assertEqual((row.feedback, row.feedback_note), ("wrong", NOTE))
        self.assertEqual(AuditEvent.objects.count(), before + 1)
        event = AuditEvent.objects.get(action=ask.ANSWER_RATED)
        self.assertEqual(
            (event.action, event.subject_type, event.subject_id, event.tenant_id, event.actor_id),
            (ask.ANSWER_RATED, ask.ANSWER_SUBJECT, answer.id, self.tenant.id, self.reader.id),
        )
        self.assertEqual((event.before, event.after), ({"feedback": ""}, {"feedback": "wrong"}))

    def test_changing_the_verdict_is_a_new_audit_row_naming_both(self) -> None:
        answer = self.answer(self.tenant)
        self.rate(answer.id, {"feedback": "helpful"})

        response = self.rate(answer.id, {"feedback": "wrong"})

        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.row(answer).feedback, "wrong")
        event = AuditEvent.objects.filter(action=ask.ANSWER_RATED).order_by("-created", "-id").first()
        assert event is not None
        self.assertEqual((event.before, event.after), ({"feedback": "helpful"}, {"feedback": "wrong"}))

    def test_the_same_verdict_twice_is_one_verdict(self) -> None:
        answer = self.answer(self.tenant)
        first = self.rate(answer.id, {"feedback": "wrong", "note": NOTE})
        audit, outbox = AuditEvent.objects.count(), OutboxEvent.objects.count()

        # A plain client: the repeat is a 204 that rightly writes nothing.
        repeat = Client().post(
            feedback_path(answer.id), {"feedback": "wrong", "note": NOTE}, content_type="application/json", **self.headers
        )

        self.assertEqual((first.status_code, repeat.status_code), (204, 204))
        self.assertEqual((AuditEvent.objects.count(), OutboxEvent.objects.count()), (audit, outbox))
        self.assertEqual((self.row(answer).feedback, self.row(answer).feedback_note), ("wrong", NOTE))

    def test_a_new_note_on_the_same_verdict_is_kept(self) -> None:
        answer = self.answer(self.tenant)
        self.rate(answer.id, {"feedback": "wrong"})

        response = self.rate(answer.id, {"feedback": "wrong", "note": NOTE})

        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.row(answer).feedback_note, NOTE)

    # -- no text ---------------------------------------------------------------------------
    def test_no_question_answer_or_note_reaches_the_audit_the_outbox_or_a_log_line(self) -> None:
        answer = self.answer(self.tenant)
        records: list[logging.LogRecord] = []

        class Keep(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        loggers = [logging.getLogger(name) for name in ("", "apps", "django")]
        handler, levels = Keep(level=logging.DEBUG), [logger.level for logger in loggers]
        for logger in loggers:
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        try:
            # A budget of nothing makes the request log a line of its own, so the check
            # below reads a line that exists rather than proving an empty list.
            with override_settings(API_BUDGET_MS=0):
                response = self.rate(answer.id, {"feedback": "wrong", "note": NOTE})
        finally:
            for logger, level in zip(loggers, levels, strict=True):
                logger.removeHandler(handler)
                logger.setLevel(level)

        self.assertEqual(response.status_code, 204, response.content)
        event = AuditEvent.objects.get(action=ask.ANSWER_RATED)
        outbox = OutboxEvent.objects.get(audit_event=event)
        written = f"{event.subject_title} {event.summary} {event.before} {event.after} {outbox.payload}"
        self.assertTrue(records, "nothing was logged, so the check below would prove nothing")
        logged = " ".join(f"{record.getMessage()} {record.__dict__}" for record in records)
        for text in ("Ekeroth", "disclosed", "itemised"):
            with self.subTest(text=text):
                self.assertNotIn(text, written)
                self.assertNotIn(text, logged)

    # -- one transaction -------------------------------------------------------------------
    def test_an_audit_row_that_fails_takes_the_verdict_with_it(self) -> None:
        answer = self.answer(self.tenant)
        body = AnswerFeedbackBody(feedback=AnswerFeedbackKind.WRONG, note=NOTE)

        with mock.patch.object(ask, "record", side_effect=RuntimeError("audit refused")), self.assertRaises(RuntimeError):
            with transaction.atomic():
                tenancy.activate(self.tenant.id)
                ask.rate_answer(answer.id, body, tenant_id=self.tenant.id, user_id=self.reader.id)

        row = self.row(answer)
        self.assertEqual((row.feedback, row.feedback_note), ("", ""))

    # -- the bank's own ----------------------------------------------------------------------
    def test_another_banks_answer_is_not_found_and_stays_unrated(self) -> None:
        theirs = self.answer(self.other)
        before = AuditEvent.objects.count()

        response = self.rate(theirs.id, {"feedback": "wrong", "note": NOTE})

        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json()["code"], "not_found")
        self.assertNotIn(str(theirs.id), response.content.decode())
        self.assertEqual(AuditEvent.objects.count(), before)
        row = self.row(theirs)
        self.assertEqual((row.feedback, row.feedback_note), ("", ""))

    def test_an_unknown_answer_and_a_model_call_that_was_no_answer_are_not_found(self) -> None:
        so_what = self.answer(self.tenant, AiPurpose.SO_WHAT)
        for answer_id in (uuid.uuid4(), so_what.id):
            with self.subTest(answer_id=answer_id):
                response = self.rate(answer_id, {"feedback": "helpful"})
                self.assertEqual(response.status_code, 404, response.content)
                self.assertEqual(response.json()["code"], "not_found")
        self.assertEqual(self.row(so_what).feedback, "")

    def test_a_session_in_no_bank_finds_no_answer(self) -> None:
        answer = self.answer(self.tenant)

        with self.assertRaises(ProblemError) as refusal, transaction.atomic():
            ask.rate_answer(answer.id, AnswerFeedbackBody(feedback=AnswerFeedbackKind.HELPFUL), tenant_id=None, user_id=self.reader.id)

        self.assertEqual((refusal.exception.status, refusal.exception.code), (404, "not_found"))

    def test_a_verdict_the_contract_does_not_name_or_an_overlong_note_is_refused(self) -> None:
        answer = self.answer(self.tenant)
        for body in ({"feedback": "great"}, {"feedback": "wrong", "note": "x" * (settings.SEARCH_FEEDBACK_NOTE_MAX_CHARS + 1)}, {"feedback": "wrong", "extra": 1}):
            with self.subTest(body=body):
                response = self.rate(answer.id, body)
                self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(self.row(answer).feedback, "")

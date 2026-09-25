"""Assessment history and "How we read this rule" outside the scenario (REG-04; REG-S7 is in
tests_scenarios.py).

A save writes the next interpretation version and stamps the one before superseded, which
stays readable; a stale `If-Match` is 409 `stale_write` and stores nothing; there is no
approval step; the text never reaches an audit value, a log or the outbox; assessments read
newest first and paged; another bank's history is invisible; both reads cost a fixed number
of queries. The append-only trigger on assessments is proved as cw_app in tests_models.py.

Operations exercised: listAssessments, getInterpretation, saveInterpretation.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.library import testing as library_testing
from apps.register import history
from apps.register.logic import ensure_register_entry
from apps.register.models import AssessmentMethod, ComplianceAssessment, Interpretation
from apps.register.tests_links import RegisterWorld
from apps.shared import tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent, OutboxEvent, Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import ComplianceStatus, RiskRating

V1_OBLIGATIONS = "/api/v1/obligations"
READING = "We read this as covering every client account the bank holds, custody included."
# The obligation and its titles, then the versions with their authors.
INTERPRETATION_QUERIES = 3
# The obligation and its titles, the page, the statuses' and the ratings' labels, the total.
ASSESSMENT_QUERIES = 6


class _Captured(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{record.getMessage()} {record.__dict__}")


def assessment(
    tenant: Tenant, obligation_id: uuid.UUID, user: Any, status: str, *, days_ago: int, rationale: str
) -> ComplianceAssessment:
    """One second-line assessment of the bank's entry, `days_ago` days back. Nothing in R2's
    routes writes an assessment yet, so the history is seeded as the table holds it."""
    tenancy.activate(tenant.id)
    with transaction.atomic():
        entry = ensure_register_entry(
            tenant_id=tenant.id, obligation_id=obligation_id, actor=Actor(kind=ActorType.USER, id=user.id, label=user.name)
        )
        return ComplianceAssessment.objects.create(
            tenant=tenant,
            tenant_obligation=entry,
            method=AssessmentMethod.SECOND_LINE_REVIEW.value,
            status=ComplianceStatus.objects.get(key=status),
            risk_rating=RiskRating.objects.get(key="medium"),
            rationale=rationale,
            next_review_date=datetime.date(2027, 3, 31),
            assessed_by=user,
            assessed_at=timezone.now() - datetime.timedelta(days=days_ago),
        )


class History(RegisterWorld):
    def put(self, user: Any, tenant: Tenant, text: str, version: int | None) -> Any:
        headers = sign_in(user, tenant=tenant)
        if version is not None:
            headers["HTTP_IF_MATCH"] = f'"{version}"'
        return self.client.put(self.url("interpretation"), data={"text": text}, content_type="application/json", **headers)

    def assess(self, tenant: Tenant, user: Any, status: str, *, days_ago: int, rationale: str) -> ComplianceAssessment:
        self.activate(tenant)
        return assessment(tenant, self.w.obligation.id, user, status, days_ago=days_ago, rationale=rationale)

    def test_a_second_save_writes_version_2_supersedes_version_1_and_keeps_it_readable(self) -> None:
        first = self.put(self.w.officer, self.w.bank, "First reading.", 0)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual((first.json()["current"]["versionNo"], first.json()["earlier"]), (1, []))
        second = self.put(self.w.officer, self.w.bank, READING, 1)
        self.assertEqual(second.status_code, 200, second.content)
        body = second.json()
        self.assertEqual((body["current"]["versionNo"], body["current"]["text"]), (2, READING))
        self.assertEqual(body["current"]["author"], {"id": str(self.w.officer.id), "name": self.w.officer.name})
        self.assertEqual([(v["versionNo"], v["text"]) for v in body["earlier"]], [(1, "First reading.")])
        self.activate(self.w.bank)
        one, two = Interpretation.objects.order_by("version_number")
        self.assertIsNotNone(one.superseded_at)
        self.assertEqual((one.body, two.superseded_at), ("First reading.", None))
        read = self.client.get(self.url("interpretation"), **sign_in(self.w.reader, tenant=self.w.bank)).json()
        self.assertEqual(read, body)

    def test_a_stale_if_match_is_409_stale_write_and_stores_nothing(self) -> None:
        self.put(self.w.officer, self.w.bank, "First reading.", 0)
        response = self.put(self.w.officer, self.w.bank, READING, 0)
        self.assertEqual((response.status_code, response.json()["code"]), (409, "stale_write"))
        self.activate(self.w.bank)
        self.assertEqual(list(Interpretation.objects.values_list("version_number", "superseded_at")), [(1, None)])
        self.assertEqual(len(self.events(self.w.bank, history.INTERPRETATION_SAVED)), 1)

    def test_a_version_has_no_approval_step_and_takes_register_edit(self) -> None:
        self.assertEqual(self.put(self.w.officer, self.w.bank, READING, None).json()["current"]["versionNo"], 1)
        refused = self.put(self.w.reader, self.w.bank, READING, 1)
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, "register.edit"))

    def test_the_text_never_reaches_an_audit_value_a_log_or_the_outbox(self) -> None:
        captured = _Captured()
        loggers = [logging.getLogger(name) for name in ("", "django", "django.request", "apps")]
        levels = [logger.level for logger in loggers]
        for logger in loggers:
            logger.addHandler(captured)
            logger.setLevel(logging.DEBUG)
        try:
            self.put(self.w.officer, self.w.bank, READING, 0)
            self.put(self.w.officer, self.w.bank, READING + " Amended.", 1)
            self.put(self.w.officer, self.w.bank, READING + " Stale.", 1)  # a 409, which django.request logs
        finally:
            for logger, level in zip(loggers, levels, strict=True):
                logger.removeHandler(captured)
                logger.setLevel(level)
        [one, two] = self.events(self.w.bank, history.INTERPRETATION_SAVED)
        self.assertEqual((one.before, one.after), ({"versionNo": 0}, {"obligationId": str(self.w.obligation.id), "versionNo": 1}))
        self.assertEqual(two.after["versionNo"], 2)
        self.activate(self.w.bank)
        stored = [
            *(str([e.before, e.after, e.summary, e.subject_title]) for e in AuditEvent.objects.all()),
            *(str(o.payload) for o in OutboxEvent.objects.all()),
            *captured.lines,
        ]
        self.assertTrue(captured.lines, "the request logged nothing, so the log half proves nothing")
        self.assertFalse([line for line in stored if "client account" in line])

    def test_assessments_read_newest_first_unchanged_with_who_and_when_and_page(self) -> None:
        old = self.assess(self.w.bank, self.w.officer, "gap", days_ago=300, rationale="The log was missing.")
        new = self.assess(self.w.bank, self.w.reader, "compliant", days_ago=10, rationale="The log is automated.")
        headers = sign_in(self.w.reader, tenant=self.w.bank)
        body = self.client.get(self.url("assessments"), **headers).json()
        self.assertEqual(body["total"], 2)
        self.assertEqual([row["id"] for row in body["items"]], [str(new.id), str(old.id)])
        first = body["items"][1]
        self.assertEqual(first["assessedBy"], {"id": str(self.w.officer.id), "name": self.w.officer.name})
        self.assertEqual((first["status"]["key"], first["status"]["kind"], first["rationale"]), ("gap", "gap", "The log was missing."))
        self.assertEqual((first["method"], first["riskRating"]["key"], first["nextReviewDate"]), ("second_line_review", "medium", "2027-03-31"))
        self.assertIsNone(first["orgUnitId"])
        page = self.client.get(self.url("assessments") + "?limit=1&offset=1", **headers).json()
        self.assertEqual(([row["id"] for row in page["items"]], page["total"]), ([str(old.id)], 2))

    def test_another_bank_sees_none_of_the_history_or_the_reading(self) -> None:
        self.assess(self.w.bank, self.w.officer, "gap", days_ago=3, rationale="Ours.")
        self.put(self.w.officer, self.w.bank, READING, 0)
        headers = sign_in(self.w.other_officer, tenant=self.w.other_bank)
        self.assertEqual(self.client.get(self.url("assessments"), **headers).json(), {"items": [], "total": 0})
        self.assertEqual(
            self.client.get(self.url("interpretation"), **headers).json(),
            {"obligationId": str(self.w.obligation.id), "current": None, "earlier": []},
        )
        theirs = self.put(self.w.other_officer, self.w.other_bank, "Their own reading.", 0)
        self.assertEqual(theirs.json()["current"]["versionNo"], 1)

    def test_both_reads_cost_the_same_queries_however_long_the_history(self) -> None:
        for n in range(2):
            self.assess(self.w.bank, self.w.officer, "gap", days_ago=n + 1, rationale=f"Assessment {n}.")
            self.put(self.w.officer, self.w.bank, f"Reading {n}.", n)
        self.activate(self.w.bank)
        with self.assertNumQueries(INTERPRETATION_QUERIES):
            history.read_interpretation(tenant=self.w.bank, obligation_id=self.w.obligation.id)
        with self.assertNumQueries(ASSESSMENT_QUERIES):
            history.list_assessments(tenant=self.w.bank, order=["en"], obligation_id=self.w.obligation.id, limit=20, offset=0)
        for n in range(2, 5):
            self.assess(self.w.bank, self.w.officer, "compliant", days_ago=n + 1, rationale=f"Assessment {n}.")
            self.put(self.w.officer, self.w.bank, f"Reading {n}.", n)
        self.activate(self.w.bank)
        with self.assertNumQueries(INTERPRETATION_QUERIES):
            reading = history.read_interpretation(tenant=self.w.bank, obligation_id=self.w.obligation.id)
        with self.assertNumQueries(ASSESSMENT_QUERIES):
            page = history.list_assessments(tenant=self.w.bank, order=["en"], obligation_id=self.w.obligation.id, limit=20, offset=0)
        self.assertEqual((reading.current and reading.current.version_no, len(reading.earlier), page.total), (5, 4, 5))

    def test_an_obligation_the_bank_cannot_see_is_404(self) -> None:
        private = library_testing.obligation(
            library_testing.instrument(key="private-history-act", regime="regime:securities", owner_tenant=self.w.other_bank),
            key="private-history-duty",
            owner_tenant=self.w.other_bank,
        )
        headers = sign_in(self.w.officer, tenant=self.w.bank)
        for suffix in ("assessments", "interpretation"):
            response = self.client.get(f"{V1_OBLIGATIONS}/{private.id}/{suffix}", **headers)
            self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"), suffix)
        saved = self.client.put(
            f"{V1_OBLIGATIONS}/{private.id}/interpretation", data={"text": READING}, content_type="application/json", **headers
        )
        self.assertEqual((saved.status_code, saved.json()["code"]), (404, "not_found"))


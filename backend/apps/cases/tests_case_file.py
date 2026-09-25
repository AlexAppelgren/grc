"""The case file as text (CAS-07, NFR-01; c9-case-file-export).

What a closed case's file says and how it says it: every section, the AI label on an
unconfirmed "So what?", removed actions and evidence still printed, the bank's own time
zone with its offset, the reader's language, no internal names, a fixed number of queries
however much the case holds, and the request budget at both caps. The export's half is
`apps/reports/tests_export_case_file.py`; another bank's half is CAS-S16.
"""

from __future__ import annotations

import ast
import datetime
import re
import uuid
import zoneinfo
from pathlib import Path
from typing import Any

from django.apps import apps as django_apps
from django.conf import settings
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cases import case_file
from apps.cases.models import Action, ChangeCase, Evidence, EvidenceKind
from apps.identity.models import User
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import Tenant
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import DismissalReason

# The caps a case's children are held to (CHUNK9: CASE_ACTIONS_MAX, CASE_EVIDENCE_MAX).
ACTIONS_CAP = getattr(settings, "CASE_ACTIONS_MAX", 200)
EVIDENCE_CAP = getattr(settings, "CASE_EVIDENCE_MAX", 200)


def url(change_id: uuid.UUID) -> str:
    return f"/api/v1/changes/{change_id}/case-file"


class CaseFileText(ScenarioTestCase):
    bank: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.bank = factories.tenant(timezone="Europe/Helsinki")
        cls.reader = factories.member_user(cls.bank, roles=("reader",))

    def read(self, change_id: uuid.UUID, user: User | None = None) -> str:
        response = self.client.get(url(change_id), **sign_in(user or self.reader, tenant=self.bank))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        return response.content.decode("utf-8")

    def at(self, moment: datetime.datetime | None) -> str:
        assert moment is not None
        return moment.astimezone(zoneinfo.ZoneInfo("Europe/Helsinki")).strftime("%Y-%m-%d %H:%M UTC%:z")

    def test_a_closed_case_names_every_part_of_its_story(self) -> None:
        built = factories.closed_case(self.bank)
        case = built.case
        text = self.read(built.change_id)
        self.activate(self.bank)
        change = case.change
        for expected in (
            change.title,
            change.stable_key,
            change.authority_label,
            change.source_label,
            case.so_what_text,
            f"Confirmed by {built.owner.name}",
            "The equity desk buys research from three brokers.",
            "Written criteria for research budgets.",
            "Does it apply: Partly",
            "Effort: M",
            f"Requested by {built.owner.name} on {self.at(case.signoff_requested_at)}.",
            f"Signed off by {built.approver.name} on {self.at(case.closed_at)}.",
            str(built.step_up),
            "Reason: Signed off.",
            "Note: Checked against the minutes.",
            "Note: Signed off after the board meeting.",
            f"Waiting for sign-off to Closed, by {built.approver.name}",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertNotIn("AI agent", text, "a confirmed So what is the bank's own and carries no AI label")
        for action in Action.objects.filter(case=case):
            self.assertIn(action.title, text)
            self.assertIn(f"Due: {action.due_date.isoformat()}.", text)
        done = Action.objects.get(case=case, done_at__isnull=False)
        self.assertIn(f"Done by {built.owner.name} on {self.at(done.done_at)}.", text)
        for piece in Evidence.objects.filter(case=case, kind=EvidenceKind.FILE.value):
            self.assertIn(piece.content_hash, text)
        self.assertIn("Malware scan: passed", text)

    def test_every_time_is_the_banks_own_with_its_offset(self) -> None:
        built = factories.closed_case(self.bank)
        text = self.read(built.change_id)
        self.activate(self.bank)
        offset = built.case.closed_at.astimezone(zoneinfo.ZoneInfo("Europe/Helsinki")).strftime("%:z")
        self.assertIn(offset, ("+02:00", "+03:00"))
        stamps = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC([+-]\d{2}:\d{2})", text)
        self.assertTrue(stamps)
        self.assertEqual(set(stamps), {offset}, "no time is printed in UTC or the server's zone")

    def test_an_unconfirmed_so_what_is_labelled_as_the_ais_draft(self) -> None:
        built = factories.closed_case(self.bank, so_what_confirmed=False)
        text = self.read(built.change_id)
        self.activate(self.bank)
        lines = text.splitlines()
        at = lines.index(built.case.so_what_text)
        self.assertEqual(lines[at + 1], "Draft written by an AI agent. Nobody at the bank has confirmed it.")
        self.assertNotIn("Confirmed by", text)

    def test_removed_actions_and_evidence_stay_in_the_file_marked(self) -> None:
        built = factories.closed_case(self.bank, evidence=3)
        text = self.read(built.change_id)
        self.activate(self.bank)
        removed_action = Action.objects.get(case=built.case, removed_at__isnull=False)
        self.assertIn(removed_action.title, text)
        self.assertIn(f"Removed by {built.owner.name} on {self.at(removed_action.removed_at)}.", text)
        removed = Evidence.objects.get(case=built.case, removed_at__isnull=False)
        block = text.split(f"- {removed.name} (file)")[1].split("\n- ")[0]
        self.assertIn(removed.content_hash, block)
        self.assertIn(f"Removed on {self.at(removed.removed_at)}.", block)

    def test_a_swedish_reader_reads_it_in_swedish(self) -> None:
        swede = factories.member_user(self.bank, roles=("reader",))
        User.objects.filter(pk=swede.pk).update(locale=factories.language("sv"))
        built = factories.closed_case(self.bank)
        text = self.read(built.change_id, swede)
        self.assertTrue(text.startswith("Ärendeakt: "))
        self.assertIn("Godkänt av", text)
        self.assertIn("Skäl: Godkänd.", text, "the bank's own reason reads in the reader's language")
        self.assertNotIn("Signed off by", text)

    def test_an_untouched_case_says_what_has_not_happened_yet(self) -> None:
        change_id = factories.case_change(self.bank).id
        text = self.read(change_id)
        for expected in (
            "Stage: Needs triage",
            "suggested and not yet confirmed by a person",
            "Nobody has written what this change means for the bank.",
            "No assessment has been saved.",
            "No actions were planned.",
            "No evidence was added.",
            "Sign-off has not been requested.",
            "The case is still open.",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_a_dismissed_case_says_who_dismissed_it_and_why(self) -> None:
        row = factories.case_change(self.bank).case
        officer = factories.member_user(self.bank, roles=("compliance_officer",))
        self.activate(self.bank)
        now = timezone.now()
        ChangeCase.objects.filter(pk=row.pk).update(
            status=CaseStatusCategory.DISMISSED.value,
            dismissed_reason=DismissalReason.objects.get(key="out_of_scope"),
            dismissed_by=officer,
            dismissed_at=now,
        )
        Evidence.objects.create(
            tenant=self.bank,
            case=row,
            kind=EvidenceKind.FILE.value,
            name="Scan still running",
            storage_key="tenants/x/evidence/y",
            content_hash="ab" * 32,
            size_bytes=10,
            mime_type="application/pdf",
            uploaded_by=officer,
        )
        text = self.read(row.change_id)
        self.assertIn(f"Dismissed by {officer.name} on {self.at(now)}. Reason: Out of scope.", text)
        self.assertIn("Malware scan: not scanned yet", text)
        self.assertIn("Stage: Dismissed", text)

    def test_it_names_no_requirement_column_or_permission(self) -> None:
        built = factories.closed_case(self.bank)
        text = self.read(built.change_id)
        self.assertIsNone(re.search(r"\b[A-Z]{2,5}-\d{2}\b", text), "no requirement id")
        for permission in perms.ALL_PERMISSIONS:
            self.assertNotIn(permission, text)
        columns = {
            field.column
            for model in django_apps.get_app_config("cases").get_models()
            for field in model._meta.concrete_fields
            if field.column and "_" in field.column
        }
        for column in columns:
            with self.subTest(column=column):
                self.assertNotIn(column, text)

    def test_the_query_count_does_not_grow_with_the_case(self) -> None:
        small = factories.closed_case(self.bank, actions=2, evidence=3)
        large = factories.closed_case(self.bank, actions=40, evidence=40)
        counts = []
        for built in (small, large):
            with transaction.atomic():
                tenancy.activate(self.bank.id)
                with CaptureQueriesContext(connection) as queries:
                    case_file.compose(tenant=self.bank, case_id=built.case.id, order=["en"])
            counts.append(len(queries))
        self.assertEqual(counts[0], counts[1])
        # The case with its people, the urgency, effort and close reason labels, the
        # assessment, the actions, the evidence, the moves and the sign-off's step-up.
        self.assertEqual(counts[0], 9)

    def test_a_case_at_both_caps_is_served_inside_the_budget(self) -> None:
        built = factories.closed_case(self.bank, actions=ACTIONS_CAP, evidence=EVIDENCE_CAP)
        headers = sign_in(self.reader, tenant=self.bank)
        self.client.get(url(built.change_id), **headers)  # warm the connection and caches
        response = self.client.get(url(built.change_id), **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().count("\n- Action "), ACTIONS_CAP)
        duration = float(re.fullmatch(r"app;dur=([\d.]+)", response["Server-Timing"]).group(1))  # type: ignore[union-attr]
        self.assertLess(duration, settings.API_BUDGET_MS)


class CaseFileSource(ScenarioTestCase):
    def test_every_sentence_comes_from_the_catalog(self) -> None:
        """No literal sentence outside `_TEXTS`: the same builder serves every language."""
        tree = ast.parse(Path(case_file.__file__).read_text())
        catalog = next(
            node.value
            for node in tree.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "_TEXTS"
        )
        assert catalog is not None
        inside = {id(node) for node in ast.walk(catalog)}
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
        }
        sentences = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in inside | docstrings
            and re.search(r"[A-Za-z]+ [A-Za-z]+ [A-Za-z]+", node.value)
        ]
        self.assertEqual(sentences, [])

    def test_english_and_swedish_hold_the_same_keys(self) -> None:
        texts: Any = case_file._TEXTS
        self.assertEqual(set(texts["en"]), set(texts["sv"]))

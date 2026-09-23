"""A change's facts, its timeline, the obligations it affects and their confirmation, over
the real routes (WAT-03, WAT-04, AGT-01, AUD-01, AUD-02, D-74, D-80).

The rule every test here circles: an agent suggests and somebody else confirms. Whatever a
key files, and whatever a library editor corrects, is stored as a suggestion naming the
agent and key that filed it; only `POST /changes/{changeId}/confirmation` confirms, from an
agent-bound key of another definition holding `proposals:review` or a person holding
`proposals.review` who steps up; and the module is held to that by a reading of its own
source as well as by its behaviour, so a confirmation cannot be added quietly elsewhere.

Written before the logic (2026-09-21, and again 2026-09-23 for the confirmation): every
case below failed against the declared contract until `watch/curation.py` was built.
"""

from __future__ import annotations

import ast
import datetime
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pydantic import ValidationError as PydanticValidationError

from apps.agents import testing as agent_build
from apps.agents.models import AgentRun, RunStatus
from apps.governance.models import AiGeneration
from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.models import Instrument, Obligation
from apps.library.schemas import AgentRef, LibraryRef
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)
from apps.watch import curation, testing as watch_build
from apps.watch.models import ChangeObligation, ChangeTerm, RegulatoryChange
from apps.watch.schemas import WatchFact, WatchObligationLink
from apps.watch.write import watch_write

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

# The model call a confirming agent reports with its decision (D-80), from the prototype's
# own reform and its public source.
DECISION: dict[str, Any] = {
    "model": "claude-opus-5",
    "modelVersion": "2026-05-01",
    "promptTemplate": "library-confirmer/curation/v1",
    "output": "Confirm. The memorandum adopts the rule and it concerns the advice perimeter.",
    "citations": [{"label": "Finansinspektionen, decision memorandum", "url": "https://www.fi.se/en/published/news/2026/reporting/"}],
}


def as_agent() -> Any:
    """A platform key bound to an agent, holding the one scope these routes want."""
    return stub_api_key(agent_principal(scopes={perms.SCOPE_CHANGES_WRITE}))


def as_editor(user: Any, *, stepped_up: bool = False) -> Any:
    """A library editor's console session, with a fresh passkey assertion when asked. No
    tenant: `proposals.review` is a platform permission and no bank's role holds it
    (PRO-01)."""
    return stub_session(
        user_principal(
            permissions={perms.PROPOSALS_REVIEW}, subject_id=user.id, step_up_at=timezone.now() if stepped_up else None
        )
    )


def confirm(link: Any) -> Any:
    """A person's confirmation, planted directly through the watch door, for the tests that
    need a confirmed fact to prove curation refuses to move one; the route that gives one
    is proven in `ConfirmingCuration` below.
    """
    editor = factories.platform_user(email=f"editor-{uuid.uuid4().hex[:8]}@bleqq.example")
    with watch_write("test"):
        if isinstance(link, ChangeTerm):
            link.suggested = False
        link.confirmed_by = editor
        link.confirmed_at = watch_build.ANCHOR
        link.save()
    return link


class CurationCase(TestCase):
    """One reform of the prototype's own data, with two obligations to link it to."""

    editor: User
    instrument: Instrument
    first: Obligation
    second: Obligation
    change: RegulatoryChange

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.editor = factories.platform_user(email="library.editor@bleqq.example")
        cls.instrument = library_build.instrument(key="fffs-2017-2", regime="regime:securities")
        cls.first = library_build.obligation(
            cls.instrument,
            key="fffs-2017-2-11-4",
            titles={"en": "Assess the quality of investment research paid for"},
            ref_label="11 kap. 4 §",
        )
        cls.second = library_build.obligation(cls.instrument, key="fffs-2017-2-11-5", ref_label="11 kap. 5 §")
        cls.change = watch_build.change_with_timeline()

    def patch_change(self, body: dict[str, Any], *, change: Any = None) -> Any:
        return self.client.patch(
            f"/api/v1/changes/{(change or self.change).id}",
            data=body,
            content_type="application/json",
            **AS_KEY,
        )

    def term_links(self, *, flags: bool) -> list[ChangeTerm]:
        column = "flag" if flags else "term"
        return list(self.change.term_links.filter(**{f"{column}__isnull": False}).order_by("id"))

    def flag_keys(self) -> list[str]:
        return [link.flag.key for link in self.term_links(flags=True) if link.flag is not None]

    def term_keys(self) -> list[str]:
        return [link.term.key for link in self.term_links(flags=False) if link.term is not None]


# ---------------------------------------------------------------------------------------
# PATCH /changes/{changeId}: the classification, as a suggestion
# ---------------------------------------------------------------------------------------
class ChangeFacts(CurationCase):
    def test_a_key_files_its_classification_as_a_suggestion(self) -> None:
        with as_agent():
            response = self.patch_change(
                {"changeType": "proposal", "flags": ["ai", "advice_perimeter"], "summary": "FI re-opened the consultation."}
            )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["changeType"]["key"], "proposal")
        self.assertEqual({flag["key"] for flag in body["flags"]}, {"ai", "advice_perimeter"})
        for link in self.term_links(flags=True):
            self.assertTrue(watch_build.is_a_suggestion(link), "an agent's classification is a suggestion (WAT-03)")

    def test_an_editors_correction_is_a_suggestion_too(self) -> None:
        """Correcting is not confirming: a library editor correcting a run leaves the fact
        exactly as unconfirmed as it was, and names no suggesting agent (D-74)."""
        with as_editor(self.editor):
            response = self.client.patch(
                f"/api/v1/changes/{self.change.id}",
                data={"flags": ["ai"]},
                content_type="application/json",
                **AS_SESSION,
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.flag_keys(), ["ai"])
        self.assertTrue(all(watch_build.is_a_suggestion(link) for link in self.term_links(flags=True)))
        self.assertEqual([link.suggested_by_agent_id for link in self.term_links(flags=True)], [None])

    def test_a_new_type_is_a_suggestion_by_the_key_that_sent_it(self) -> None:
        sweeper = agent_build.agent_key(scopes=(perms.SCOPE_CHANGES_WRITE,))
        response = self.client.patch(
            f"/api/v1/changes/{self.change.id}",
            data={"changeType": "proposal", "flags": ["ai"]},
            content_type="application/json",
            HTTP_X_API_KEY=sweeper.plain_key,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.change.refresh_from_db()
        self.assertTrue(self.change.change_type_suggested)
        self.assertEqual(
            (self.change.change_type_suggested_by_agent_id, self.change.change_type_suggested_by_api_key_id),
            (sweeper.agent.id, sweeper.id),
        )
        flag = self.term_links(flags=True)[0]
        self.assertEqual((flag.suggested_by_agent_id, flag.suggested_by_api_key_id), (sweeper.agent.id, sweeper.id))

    def test_the_sets_are_replaced_and_not_added_to(self) -> None:
        with as_agent():
            self.patch_change({"termIds": [str(watch_build.term("regime:aml").id)]})
        self.assertEqual(self.term_keys(), ["aml"])

    def test_a_replacing_set_without_a_regime_is_refused_with_the_regimes_listed(self) -> None:
        """D-39, AC-AGT1: the rule a new change meets applies to the set that replaces its
        terms, so no correction can leave a change reaching every bank."""
        cases = {"an empty set": [], "a channel term alone": [str(watch_build.term("channel:digital").id)]}
        for case, term_ids in cases.items():
            with self.subTest(case=case), as_agent():
                response = self.patch_change({"title": "A better title", "termIds": term_ids})
            self.assertEqual(response.status_code, 422, response.content)
            problem = response.json()
            self.assertEqual(problem["code"], "regime_required")
            self.assertIn("aml", problem["validKeys"])
            self.assertNotIn("digital", problem["validKeys"])
        self.change.refresh_from_db()
        self.assertNotEqual(self.change.title, "A better title", "a refusal stores nothing at all")
        self.assertEqual(self.term_keys(), ["securities"])

    def test_a_standards_term_on_a_supervisors_change_is_refused(self) -> None:
        """WAT-07, D-38: a correction cannot tag FI's change with a standard, which would
        hide it from every bank that follows none; a standards body's change takes one."""
        terms = [str(watch_build.term("regime:ai_ict").id), str(watch_build.term("standard:iso_iec_27001").id)]
        with as_agent():
            response = self.patch_change({"termIds": terms})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], "standard_term_only_on_standards")
        self.assertEqual(self.term_keys(), ["securities"], "a refusal stores nothing")

        library_build.authority(key="iso-iec", short_name="ISO/IEC", jurisdiction="intl")
        standards_change = watch_build.change(authority="iso-iec", authority_label="ISO/IEC")
        with as_agent():
            response = self.patch_change({"termIds": terms}, change=standards_change)
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_call_that_leaves_the_terms_alone_needs_no_regime(self) -> None:
        with as_agent():
            response = self.patch_change({"flags": ["ai"]})
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_field_left_out_is_left_alone(self) -> None:
        with as_agent():
            self.patch_change({"title": "FI re-opens the research consultation"})
        self.change.refresh_from_db()
        self.assertEqual(self.change.title, "FI re-opens the research consultation")
        self.assertEqual(self.flag_keys(), ["advice_perimeter"])

    def test_an_unknown_key_stores_nothing(self) -> None:
        with as_agent():
            response = self.patch_change({"title": "A better title", "changeType": "ammendment"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "unknown_key")
        self.change.refresh_from_db()
        self.assertNotEqual(self.change.title, "A better title", "a refusal stores nothing at all")

    def test_an_unknown_term_is_refused_with_the_endpoint_that_lists_them(self) -> None:
        with as_agent():
            response = self.patch_change({"termIds": [str(uuid.uuid4())]})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "unknown_key")
        self.assertIn("/taxonomy/terms", response.json()["detail"])

    def test_a_change_that_is_not_there_is_404(self) -> None:
        with as_agent():
            response = self.client.patch(
                f"/api/v1/changes/{uuid.uuid4()}", data={"title": "x"}, content_type="application/json", **AS_KEY
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")


class WhatOnlyAnEditorMayMove(CurationCase):
    def test_a_key_may_not_supersede_a_change(self) -> None:
        replacement = watch_build.change()
        with as_agent():
            response = self.patch_change({"status": "superseded", "supersededBy": str(replacement.id)})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "editor_only_field")
        self.change.refresh_from_db()
        self.assertEqual(self.change.status, "active")
        self.assertIsNone(self.change.superseded_by_id)

    def test_an_editor_supersedes_a_change(self) -> None:
        replacement = watch_build.change()
        with as_editor(self.editor):
            response = self.client.patch(
                f"/api/v1/changes/{self.change.id}",
                data={"status": "superseded", "supersededBy": str(replacement.id)},
                content_type="application/json",
                **AS_SESSION,
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.change.refresh_from_db()
        self.assertEqual(self.change.superseded_by_id, replacement.id)

    def test_a_change_cannot_supersede_itself(self) -> None:
        with as_editor(self.editor):
            response = self.client.patch(
                f"/api/v1/changes/{self.change.id}",
                data={"supersededBy": str(self.change.id)},
                content_type="application/json",
                **AS_SESSION,
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_a_superseding_change_the_library_does_not_hold_is_refused(self) -> None:
        with as_editor(self.editor):
            response = self.client.patch(
                f"/api/v1/changes/{self.change.id}",
                data={"supersededBy": str(uuid.uuid4())},
                content_type="application/json",
                **AS_SESSION,
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "unknown_key")


class AConfirmedFactStands(CurationCase):
    """A confirmed fact is not moved by a correction: a key is refused outright, and a
    person overturns one only with a fresh passkey assertion, which the audit row carries
    (D-74)."""

    def setUp(self) -> None:
        super().setUp()
        self.confirmed = confirm(self.term_links(flags=True)[0])

    def test_a_key_cannot_drop_a_flag_somebody_confirmed(self) -> None:
        with as_agent():
            response = self.patch_change({"flags": ["ai"]})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "confirmed_fact")
        self.confirmed.refresh_from_db()
        self.assertFalse(self.confirmed.suggested, "the confirmation stands")

    def test_an_editor_needs_a_fresh_passkey_to_drop_a_confirmed_flag(self) -> None:
        with as_editor(self.editor):
            response = self.client.patch(
                f"/api/v1/changes/{self.change.id}",
                data={"flags": ["ai"]},
                content_type="application/json",
                **AS_SESSION,
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "step_up_required")
        self.confirmed.refresh_from_db()
        self.assertFalse(self.confirmed.suggested, "a refusal stores nothing")

    def test_an_editor_with_a_fresh_passkey_overturns_a_confirmed_flag(self) -> None:
        with as_editor(self.editor, stepped_up=True):
            response = self.client.patch(
                f"/api/v1/changes/{self.change.id}",
                data={"flags": ["ai"]},
                content_type="application/json",
                **AS_SESSION,
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.flag_keys(), ["ai"])
        self.assertFalse(ChangeTerm.objects.filter(pk=self.confirmed.pk).exists())
        audit = AuditEvent.objects.filter(action="regulatory_change.facts_updated").order_by("-created", "-id").first()
        self.assertIsNotNone(audit)
        self.assertIsNotNone(audit.step_up_assertion_id, "the overturning carries the passkey assertion")  # type: ignore[union-attr]

    def test_a_key_cannot_replace_a_confirmed_type(self) -> None:
        with watch_write("test"):
            RegulatoryChange.objects.filter(pk=self.change.pk).update(
                change_type_suggested=False, change_type_confirmed_by=self.editor, change_type_confirmed_at=watch_build.ANCHOR
            )
        with as_agent():
            response = self.patch_change({"changeType": "proposal"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "confirmed_fact")
        with as_agent():
            same = self.patch_change({"changeType": "adopted", "title": "A clearer title"})
        self.assertEqual(same.status_code, 200, "sending the type it already has moves nothing")
        self.change.refresh_from_db()
        self.assertFalse(self.change.change_type_suggested)

    def test_a_confirmed_flag_that_stays_is_left_untouched(self) -> None:
        with as_agent():
            response = self.patch_change({"flags": ["advice_perimeter", "ai"]})
        self.assertEqual(response.status_code, 200, response.content)
        self.confirmed.refresh_from_db()
        self.assertFalse(self.confirmed.suggested)
        self.assertIsNotNone(self.confirmed.confirmed_by_id)
        self.assertEqual(len(self.term_links(flags=True)), 2)

    def test_a_keys_write_deletes_no_confirmation_even_past_its_check(self) -> None:
        """The write itself holds the rule, not only the check before it: with the check
        made to find nothing — as a confirmation landing just after it would — a key's
        replacing set still deletes suggestions and nothing else (D-74). Proven red
        2026-09-24 against the delete that ran for every caller."""
        with mock.patch.object(curation, "_refuse_confirmed"), as_agent():
            response = self.patch_change({"flags": ["ai"]})
        self.assertEqual(response.status_code, 200, response.content)
        self.confirmed.refresh_from_db()
        self.assertFalse(self.confirmed.suggested, "the confirmation stands")
        self.assertEqual(sorted(self.flag_keys()), ["advice_perimeter", "ai"])

    def test_the_write_locks_the_change_before_it_reads_what_is_confirmed(self) -> None:
        """Each write that reads what is confirmed takes the change's row lock first, so a
        confirmation cannot land between its check and its write; the race itself is proven
        with two sessions in tests_curation_races.py."""
        with as_agent(), CaptureQueriesContext(connection) as queries:
            self.patch_change({"flags": ["advice_perimeter", "ai"]})
        on_the_change = [query["sql"] for query in queries if 'FROM "regulatory_change"' in query["sql"]]
        self.assertIn("FOR UPDATE", on_the_change[0])


class OnlyTheConfirmPathConfirms(TestCase):
    """Read off the source: no function of `curation.py` but `confirm_curation` writes
    `suggested = false` or puts a value in a confirmation column; clearing one to None, which
    a person's overturning does, is not a confirmation.

    A behaviour test can only prove the paths it walks; this walks the module's whole AST,
    so a confirmation cannot be added to a branch nobody tested, where it would skip the
    confirm path's gate, its independence check and its logging (D-74, D-80).
    """

    CONFIRM_PATH = "confirm_curation"
    # The columns that together say "somebody settled this", on a term or obligation link
    # and, prefixed, on the change's type, and the ORM calls that could put a value in one.
    CONFIRMATION = frozenset(
        f"{prefix}{column}"
        for prefix in ("", "change_type_")
        for column in (
            "confirmed_by",
            "confirmed_by_id",
            "confirmed_by_api_key",
            "confirmed_by_api_key_id",
            "confirmed_by_agent",
            "confirmed_by_agent_id",
            "confirmed_at",
        )
    )
    SUGGESTED = frozenset({"suggested", "change_type_suggested"})
    WRITES = frozenset({"create", "update", "update_or_create", "get_or_create", "bulk_create", "bulk_update"})

    def test_only_the_confirm_path_writes_a_confirmation(self) -> None:
        module = Path(__file__).resolve().parent / "curation.py"
        tree = ast.parse(module.read_text(encoding="utf-8"))
        written: dict[str, list[str]] = {}
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
            for node in ast.walk(function):
                for name, value in _writes(node, self.WRITES):
                    if (name in self.CONFIRMATION and not _is_none(value)) or (name in self.SUGGESTED and _is_false(value)):
                        written.setdefault(function.name, []).append(name)
        self.assertEqual(
            sorted(written),
            [self.CONFIRM_PATH],
            "apps/watch/curation.py writes a confirmation outside confirm_curation, or not at all. "
            "Confirming a change's facts goes through the one path that checks who confirms (D-74).",
        )

    def test_a_term_link_is_written_as_a_suggestion(self) -> None:
        """The other half of the rule: the one place this module puts a term link on a
        change says `suggested` true, so the AST test above is not passing on an absence."""
        source = (Path(__file__).resolve().parent / "curation.py").read_text(encoding="utf-8")
        self.assertIn('"suggested": True', source)


class AConfirmedFactSaysWhoConfirmedIt(SimpleTestCase):
    """A read that builds a confirmed fact without its provenance fails loudly rather than
    answering `confirmedOrigin: null`, which the contract defines as a suggestion, so a
    machine's confirmation can never reach a bank unlabelled (D-74). The roadmap's own
    link read did exactly that until 2026-09-24."""

    REF = LibraryRef(key="advice_perimeter", kind=None, label="Advice perimeter")
    CONFIRMER = AgentRef(id=uuid.uuid4(), key="library-confirmer")

    def link(self, *, confirmed_origin: Any = None, confirmed_by_agent: AgentRef | None = None) -> WatchObligationLink:
        return WatchObligationLink(
            obligation_id=uuid.uuid4(),
            title="A duty",
            instrument_short_name="FFFS 2017:2",
            ref_label="11 kap. 4 §",
            origin="agent",
            confidence=0.8,
            confirmed=True,
            confirmed_origin=confirmed_origin,
            confirmed_by_agent=confirmed_by_agent,
        )

    def test_a_confirmed_fact_or_link_names_who_confirmed_it(self) -> None:
        refused = {
            "a fact with no origin": lambda: WatchFact(ref=self.REF, confidence=None, suggested=False),
            "a link with no origin": lambda: self.link(),
            "a machine's confirmation naming no agent": lambda: self.link(confirmed_origin="agent"),
        }
        for what, build in refused.items():
            with self.subTest(what), self.assertRaises(PydanticValidationError):
                build()
        machine = self.link(confirmed_origin="agent", confirmed_by_agent=self.CONFIRMER)
        self.assertEqual(machine.confirmed_by_agent, self.CONFIRMER)
        self.assertIsNone(WatchFact(ref=self.REF, confidence=0.7, suggested=True).confirmed_origin, "a suggestion names nobody")


def _writes(node: ast.AST, calls: frozenset[str]) -> list[tuple[str, ast.expr]]:
    """The (column, value) pairs one AST node writes: an attribute assignment, or a keyword
    of an ORM write call."""
    if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        pairs: list[tuple[str, ast.expr]] = []
        for target in targets:
            for element in target.elts if isinstance(target, ast.Tuple) else [target]:
                if isinstance(element, ast.Attribute):
                    pairs.append((element.attr, node.value))
        return pairs
    if isinstance(node, ast.Call) and _method(node) in calls:
        return [(keyword.arg, keyword.value) for keyword in node.keywords if keyword.arg]
    return []


def _is_false(value: Any) -> bool:
    return isinstance(value, ast.Constant) and value.value is False


def _is_none(value: Any) -> bool:
    return isinstance(value, ast.Constant) and value.value is None


def _method(call: ast.Call) -> str:
    return call.func.attr if isinstance(call.func, ast.Attribute) else ""


# ---------------------------------------------------------------------------------------
# The timeline (WAT-02)
# ---------------------------------------------------------------------------------------
class Timeline(CurationCase):
    URL_SUFFIX = "/events"

    def post_event(self, body: dict[str, Any]) -> Any:
        return self.client.post(
            f"/api/v1/changes/{self.change.id}{self.URL_SUFFIX}",
            data=body,
            content_type="application/json",
            **AS_KEY,
        )

    def test_a_milestone_stores_a_plain_date_with_its_precision(self) -> None:
        with as_agent():
            response = self.post_event({"label": "Transition ends", "eventDate": "2027-03-01", "datePrecision": "month"})
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["eventDate"], "2027-03-01")
        self.assertEqual(body["datePrecision"], "month")

    def test_a_timestamp_is_refused_where_a_legal_date_belongs(self) -> None:
        with as_agent():
            response = self.post_event({"label": "Transition ends", "eventDate": "2027-03-01T09:30:00Z"})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertFalse(self.change.events.filter(label="Transition ends").exists())

    def test_a_retried_milestone_answers_the_entry_it_already_added(self) -> None:
        body = {"label": "Transition ends", "eventDate": "2027-03-01", "datePrecision": "day", "sortOrder": 3}
        with as_agent():
            first = self.post_event(body)
            again = self.post_event(body)
        self.assertEqual((first.status_code, again.status_code), (201, 201))
        self.assertEqual(first.json()["id"], again.json()["id"])
        self.assertEqual(self.change.events.filter(label="Transition ends").count(), 1)

    def test_the_same_label_with_other_dates_is_a_conflict(self) -> None:
        with as_agent():
            self.post_event({"label": "Transition ends", "eventDate": "2027-03-01"})
            response = self.post_event({"label": "Transition ends", "eventDate": "2027-06-01"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "duplicate_key")
        self.assertEqual(self.change.events.filter(label="Transition ends").count(), 1)

    def test_a_milestone_is_corrected_in_place(self) -> None:
        entry = self.change.events.get(label="In force")
        with as_editor(self.editor):
            response = self.client.patch(
                f"/api/v1/changes/{self.change.id}/events/{entry.id}",
                data={"label": "In force", "eventDate": "2026-10-01", "datePrecision": "day", "occurred": True, "sortOrder": 2},
                content_type="application/json",
                **AS_SESSION,
            )
        self.assertEqual(response.status_code, 200, response.content)
        entry.refresh_from_db()
        self.assertTrue(entry.occurred)
        self.assertEqual(entry.event_date, datetime.date(2026, 10, 1))

    def test_an_entry_of_another_change_is_404(self) -> None:
        elsewhere = watch_build.event(watch_build.change())
        with as_agent():
            response = self.client.patch(
                f"/api/v1/changes/{self.change.id}/events/{elsewhere.id}",
                data={"label": "Moved"},
                content_type="application/json",
                **AS_KEY,
            )
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------------------
# PUT /changes/{changeId}/obligations (WAT-04)
# ---------------------------------------------------------------------------------------
class ObligationLinks(CurationCase):
    def put_links(self, links: list[dict[str, Any]], *, headers: dict[str, Any] | None = None) -> Any:
        return self.client.put(
            f"/api/v1/changes/{self.change.id}/obligations",
            data=links,
            content_type="application/json",
            **(headers or AS_KEY),
        )

    def test_an_agents_links_arrive_as_suggestions_with_their_confidence(self) -> None:
        with as_agent():
            response = self.put_links(
                [{"obligationId": str(self.first.id), "confidence": 0.9}, {"obligationId": str(self.second.id), "confidence": 0.4}]
            )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual([link["confidence"] for link in body], [0.9, 0.4], "most confident first")
        self.assertTrue(all(link["origin"] == "agent" for link in body))
        self.assertFalse(any(link["confirmed"] for link in body))

    def test_a_person_setting_a_link_is_recorded_as_a_person(self) -> None:
        with as_editor(self.editor):
            response = self.put_links([{"obligationId": str(self.first.id)}], headers=AS_SESSION)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()[0]["origin"], "user")
        self.assertIsNone(response.json()[0]["confidence"])

    def test_the_body_is_the_whole_set(self) -> None:
        with as_agent():
            self.put_links([{"obligationId": str(self.first.id)}, {"obligationId": str(self.second.id)}])
            response = self.put_links([{"obligationId": str(self.second.id)}])
        self.assertEqual([link["obligationId"] for link in response.json()], [str(self.second.id)])
        self.assertEqual(self.change.obligation_links.count(), 1)

    def test_an_unknown_obligation_stores_nothing(self) -> None:
        with as_agent():
            response = self.put_links([{"obligationId": str(self.first.id)}, {"obligationId": str(uuid.uuid4())}])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "unknown_key")
        self.assertEqual(self.change.obligation_links.count(), 0)

    def test_the_same_obligation_twice_is_refused(self) -> None:
        with as_agent():
            response = self.put_links(
                [{"obligationId": str(self.first.id), "confidence": 0.9}, {"obligationId": str(self.first.id), "confidence": 0.2}]
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_a_key_cannot_remove_a_link_somebody_confirmed(self) -> None:
        confirm(watch_build.obligation_link(self.change, self.first))
        with as_agent():
            response = self.put_links([{"obligationId": str(self.second.id)}])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "confirmed_fact")
        self.assertEqual(self.change.obligation_links.count(), 1)

    def test_an_editor_needs_a_fresh_passkey_to_remove_a_confirmed_link(self) -> None:
        confirm(watch_build.obligation_link(self.change, self.first))
        with as_editor(self.editor):
            refused = self.put_links([{"obligationId": str(self.second.id)}], headers=AS_SESSION)
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["code"], "step_up_required")
        self.assertEqual(list(self.change.obligation_links.values_list("obligation_id", flat=True)), [self.first.id])
        with as_editor(self.editor, stepped_up=True):
            overturned = self.put_links([{"obligationId": str(self.second.id)}], headers=AS_SESSION)
        self.assertEqual(overturned.status_code, 200, overturned.content)
        self.assertEqual(list(self.change.obligation_links.values_list("obligation_id", flat=True)), [self.second.id])

    def test_a_keys_set_deletes_no_confirmed_link_even_past_its_check(self) -> None:
        """As for a flag: with the check made to find nothing, a key's set still leaves a
        confirmed link where it is (D-74)."""
        link = confirm(watch_build.obligation_link(self.change, self.first))
        with mock.patch.object(curation, "_refuse_confirmed"), as_agent():
            response = self.put_links([{"obligationId": str(self.second.id)}])
        self.assertEqual(response.status_code, 200, response.content)
        link.refresh_from_db()
        self.assertIsNotNone(link.confirmed_at, "the confirmation stands")
        self.assertEqual(
            sorted(str(link.obligation_id) for link in self.change.obligation_links.all()),
            sorted([str(self.first.id), str(self.second.id)]),
        )

    def test_a_confirmed_link_that_stays_keeps_its_confirmation(self) -> None:
        link = confirm(watch_build.obligation_link(self.change, self.first))
        with as_agent():
            response = self.put_links(
                [{"obligationId": str(self.first.id), "confidence": 0.1}, {"obligationId": str(self.second.id)}]
            )
        self.assertEqual(response.status_code, 200, response.content)
        link.refresh_from_db()
        self.assertIsNotNone(link.confirmed_by_id)
        self.assertEqual(float(link.confidence), 0.82, "a confirmed link is not rewritten by a later run")
        self.assertEqual(self.change.obligation_links.count(), 2)

    def test_nothing_this_route_writes_is_ever_confirmed(self) -> None:
        with as_agent():
            self.put_links([{"obligationId": str(self.first.id)}])
        for link in ChangeObligation.objects.filter(change=self.change):
            self.assertTrue(watch_build.is_a_suggestion(link))


# ---------------------------------------------------------------------------------------
# AUD-01: no fact moves without its audit row
# ---------------------------------------------------------------------------------------
class EveryWriteIsAudited(CurationCase):
    def assert_one_audit_row(self, action: str, call: Any) -> None:
        before = AuditEvent.objects.count()
        response = call()
        self.assertIn(response.status_code, (200, 201), response.content)
        self.assertEqual(AuditEvent.objects.count(), before + 1)
        latest = AuditEvent.objects.order_by("-created", "-id").first()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.action, action)  # type: ignore[union-attr]
        self.assertEqual(latest.subject_type, "regulatory_change")  # type: ignore[union-attr]
        self.assertIsNone(latest.tenant_id, "a change is a library row and belongs to no bank")  # type: ignore[union-attr]

    def test_correcting_the_facts_is_audited(self) -> None:
        with as_agent():
            self.assert_one_audit_row(
                "regulatory_change.facts_updated", lambda: self.patch_change({"flags": ["ai"]})
            )

    def test_adding_and_correcting_a_milestone_is_audited(self) -> None:
        with as_agent():
            self.assert_one_audit_row(
                "regulatory_change.event_added",
                lambda: self.client.post(
                    f"/api/v1/changes/{self.change.id}/events",
                    data={"label": "Transition ends", "eventDate": "2027-03-01"},
                    content_type="application/json",
                    **AS_KEY,
                ),
            )
            self.assert_one_audit_row(
                "regulatory_change.event_replayed",
                lambda: self.client.post(
                    f"/api/v1/changes/{self.change.id}/events",
                    data={"label": "Transition ends", "eventDate": "2027-03-01"},
                    content_type="application/json",
                    **AS_KEY,
                ),
            )

    def test_setting_the_obligation_links_is_audited(self) -> None:
        with as_agent():
            self.assert_one_audit_row(
                "regulatory_change.obligations_replaced",
                lambda: self.client.put(
                    f"/api/v1/changes/{self.change.id}/obligations",
                    data=[{"obligationId": str(self.first.id)}],
                    content_type="application/json",
                    **AS_KEY,
                ),
            )

    def test_the_audit_row_names_what_moved(self) -> None:
        with as_agent():
            self.patch_change({"flags": ["ai"]})
        latest = AuditEvent.objects.filter(action="regulatory_change.facts_updated").order_by("-created", "-id").first()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.before["flags"], ["advice_perimeter"])  # type: ignore[union-attr]
        self.assertEqual(latest.after["flags"], ["ai"])  # type: ignore[union-attr]


# ---------------------------------------------------------------------------------------
# POST /changes/{changeId}/confirmation (WAT-03, WAT-04, D-74, D-80)
# ---------------------------------------------------------------------------------------
class ConfirmingCuration(CurationCase):
    """A reform the sweeper registered in its run — its type, its flag, its scope term and
    one obligation link, each suggested by the sweeper's agent and key — and a confirming
    agent of another definition with a run of its own open."""

    sweeper: SimpleNamespace
    sweep: AgentRun
    confirmer: SimpleNamespace
    review: AgentRun
    reform: RegulatoryChange

    def setUp(self) -> None:
        super().setUp()
        tenancy.clear_tenant()
        # The sweeper holds the review scope too, so its own suggestion is the refusal
        # proven below rather than a missing scope.
        self.sweeper = agent_build.agent_key(scopes=(*agent_build.WATCH_SCOPES, perms.SCOPE_PROPOSALS_REVIEW))
        self.sweep = agent_build.platform_run(key=self.sweeper)
        self.reform = watch_build.change_with_timeline(run=self.sweep)
        watch_build.obligation_link(self.reform, self.first)
        self.confirmer = agent_build.agent_key(
            agent_row=agent_build.agent(key="library-confirmer"),
            scopes=("agent-runs:write", "library:read", perms.SCOPE_PROPOSALS_REVIEW),
        )
        self.review = agent_build.platform_run(key=self.confirmer)

    def post(self, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(
            f"/api/v1/changes/{self.reform.id}/confirmation", data=body, content_type="application/json", **headers
        )

    def as_key(self, key: SimpleNamespace, body: dict[str, Any], *, run: AgentRun | None = None) -> Any:
        """A key's confirmation, carrying its decision inside `run` (the confirmer's own by default)."""
        payload = {"decision": DECISION, "agentRunId": str((run or self.review).id), **body}
        return self.post(payload, {"HTTP_X_API_KEY": key.plain_key})

    def everything(self) -> dict[str, Any]:
        return {
            "changeType": "adopted",
            "flags": ["advice_perimeter"],
            "termIds": [str(watch_build.term("regime:securities").id)],
            "obligationIds": [str(self.first.id)],
        }

    def term_links_of(self, change: RegulatoryChange) -> list[ChangeTerm]:
        return list(change.term_links.filter(flag__isnull=False))

    def nothing_confirmed(self) -> bool:
        self.reform.refresh_from_db()
        links: list[ChangeTerm | ChangeObligation] = [*self.reform.term_links.all(), *self.reform.obligation_links.all()]
        return self.reform.change_type_suggested and all(watch_build.is_a_suggestion(link) for link in links)

    def test_an_agent_of_another_definition_confirms_and_every_fact_reads_machine_confirmed(self) -> None:
        response = self.as_key(self.confirmer, self.everything())
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()
        sweeper = {"id": str(self.sweeper.agent.id), "key": self.sweeper.agent.key}
        confirmer = {"id": str(self.confirmer.agent.id), "key": "library-confirmer"}
        for fact in [row["changeType"], *row["flags"], *row["terms"], *row["obligations"]]:
            self.assertEqual(
                (fact["confirmedOrigin"], fact["suggestedByAgent"], fact["confirmedByAgent"]), ("agent", sweeper, confirmer)
            )
        self.assertFalse(row["changeType"]["suggested"])
        self.assertTrue(row["obligations"][0]["confirmed"])
        self.assertEqual(row["unconfirmedCount"], 0)

        # Stored as a key's confirmation, naming no person: never a person's verification.
        self.reform.refresh_from_db()
        self.assertEqual(
            (
                self.reform.change_type_confirmed_by_id,
                self.reform.change_type_confirmed_by_api_key_id,
                self.reform.change_type_confirmed_by_agent_id,
            ),
            (None, self.confirmer.id, self.confirmer.agent.id),
        )
        # The decision is a model call, logged in the platform's zone against the run (D-80).
        generation = AiGeneration.objects.get(purpose="agent_review", subject_id=self.reform.id)
        self.assertEqual((generation.agent_run_id, generation.subject_type), (self.review.id, "regulatory_change"))
        self.assertTrue(generation.model_metadata_reported_by_agent)
        self.assertIsNone(generation.tenant_id)
        audit = AuditEvent.objects.get(action="regulatory_change.curation_confirmed")
        self.assertEqual(audit.after["confirmedOrigin"], "agent")
        self.assertEqual(audit.after["agentRunId"], str(self.review.id))
        self.assertEqual(len(audit.after["confirmed"]), 4)
        self.assertIsNone(audit.tenant_id)

    def test_an_agent_never_confirms_its_own_suggestion_nor_one_of_its_own_agent(self) -> None:
        own = self.as_key(self.sweeper, {"flags": ["advice_perimeter"]}, run=self.sweep)
        self.assertEqual(own.status_code, 409, own.content)
        self.assertEqual(own.json()["code"], "own_suggestion")
        sibling = agent_build.agent_key(agent_row=self.sweeper.agent, scopes=("agent-runs:write", perms.SCOPE_PROPOSALS_REVIEW))
        same = self.as_key(sibling, {"changeType": "adopted"}, run=agent_build.platform_run(key=sibling))
        self.assertEqual(same.status_code, 409, same.content)
        self.assertEqual(same.json()["code"], "same_agent")
        self.assertTrue(self.nothing_confirmed())
        self.assertFalse(AiGeneration.objects.filter(purpose="agent_review").exists(), "a refusal logs nothing")

    def test_a_key_decides_inside_an_open_run_of_its_own_with_its_model_call(self) -> None:
        body = {"flags": ["advice_perimeter"]}
        key = {"HTTP_X_API_KEY": self.confirmer.plain_key}
        undecided = self.post({**body, "agentRunId": str(self.review.id)}, key)
        self.assertEqual((undecided.status_code, undecided.json()["code"]), (422, "validation_error"))
        runless = self.post({**body, "decision": DECISION}, key)
        self.assertEqual((runless.status_code, runless.json()["code"]), (422, "run_not_open"))
        someone_elses = self.as_key(self.confirmer, body, run=self.sweep)
        self.assertEqual((someone_elses.status_code, someone_elses.json()["code"]), (404, "not_found"))
        uncited = self.post({**body, "agentRunId": str(self.review.id), "decision": {**DECISION, "citations": []}}, key)
        self.assertEqual((uncited.status_code, uncited.json()["code"]), (422, "validation_error"))
        AgentRun.objects.filter(pk=self.review.pk).update(status=RunStatus.SUCCEEDED.value, finished_at=timezone.now())
        closed = self.as_key(self.confirmer, body)
        self.assertEqual((closed.status_code, closed.json()["code"]), (422, "run_not_open"))
        self.assertTrue(self.nothing_confirmed())

    def test_no_bank_and_no_key_without_the_review_scope_confirms(self) -> None:
        body = {"flags": ["advice_perimeter"]}
        writer = self.as_key(agent_build.agent_key(scopes=agent_build.WATCH_SCOPES), body)
        self.assertEqual((writer.status_code, writer.json()["requiredPermission"]), (403, perms.SCOPE_PROPOSALS_REVIEW))
        unbound = self.as_key(self.unbound_key(), body)
        self.assertEqual((unbound.status_code, unbound.json()["code"]), (403, "agent_not_bound"))
        bank = factories.tenant()
        banks_key = agent_build.tenant_key(bank, scopes=(perms.SCOPE_PROPOSALS_REVIEW,))
        tenancy.clear_tenant()
        refused = self.as_key(banks_key, body)
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "permission_denied"))
        with stub_session(user_principal(permissions={perms.WATCH_READ, perms.APPLICABILITY_APPROVE}, tenant_id=bank.id)):
            officer = self.post(body, AS_SESSION)
        self.assertEqual((officer.status_code, officer.json()["requiredPermission"]), (403, perms.PROPOSALS_REVIEW))
        self.assertTrue(self.nothing_confirmed())

    def unbound_key(self) -> SimpleNamespace:
        """A live platform key bound to no agent definition, as a key created before keys were
        bound would be; no route creates one."""
        from apps.identity import tokens
        from apps.identity.models import ApiKey

        plain, prefix, key_hash = tokens.new_api_key()
        row = ApiKey.objects.create(
            tenant=None, agent=None, name="Unbound reviewer", key_prefix=prefix, key_hash=key_hash, scopes=[perms.SCOPE_PROPOSALS_REVIEW]
        )
        return SimpleNamespace(id=row.id, row=row, plain_key=plain)

    def test_a_person_intervenes_with_a_fresh_passkey_and_no_model_call(self) -> None:
        body = {"flags": ["advice_perimeter"], "obligationIds": [str(self.first.id)]}
        with as_editor(self.editor):
            stale = self.post(body, AS_SESSION)
        self.assertEqual((stale.status_code, stale.json()["code"]), (403, "step_up_required"))
        with as_editor(self.editor, stepped_up=True):
            with_a_decision = self.post({**body, "decision": DECISION}, AS_SESSION)
            confirmed = self.post(body, AS_SESSION)
        self.assertEqual((with_a_decision.status_code, with_a_decision.json()["code"]), (422, "validation_error"))
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        flag = confirmed.json()["flags"][0]
        self.assertEqual((flag["confirmedOrigin"], flag["confirmedByAgent"]), ("user", None))
        self.assertEqual(flag["suggestedByAgent"]["key"], self.sweeper.agent.key)
        link = self.reform.obligation_links.get()
        self.assertEqual((link.confirmed_by_id, link.confirmed_by_api_key_id), (self.editor.id, None))
        self.reform.refresh_from_db()
        self.assertTrue(self.reform.change_type_suggested, "only what was named is confirmed")
        audit = AuditEvent.objects.get(action="regulatory_change.curation_confirmed")
        self.assertIsNotNone(audit.step_up_assertion_id)
        self.assertEqual(audit.after["confirmedOrigin"], "user")
        self.assertFalse(AiGeneration.objects.filter(purpose="agent_review").exists(), "a person's confirmation is no model call")

    def test_a_person_never_confirms_what_they_filed(self) -> None:
        """D-74's independence holds for a person too: an editor who corrects a fact files a
        suggestion in their own name, and somebody else — an agent of another definition or
        another person — confirms it."""
        flags = {"flags": ["advice_perimeter", "ai"]}
        with as_editor(self.editor, stepped_up=True):
            filed = self.client.patch(f"/api/v1/changes/{self.reform.id}", data=flags, content_type="application/json", **AS_SESSION)
            own = self.post({"flags": ["ai"]}, AS_SESSION)
        self.assertEqual(filed.status_code, 200, filed.content)
        self.assertEqual((own.status_code, own.json()["code"]), (409, "own_suggestion"))
        filed_by = {(link.suggested_by_id, link.suggested_by_agent_id, link.suggested) for link in self.term_links_of(self.reform)}
        self.assertEqual(filed_by, {(self.editor.id, None, True)}, "a refusal confirms nothing")
        another = factories.platform_user(email="second.editor@bleqq.example")
        with as_editor(another, stepped_up=True):
            by_another_person = self.post({"flags": ["ai"]}, AS_SESSION)
        self.assertEqual(by_another_person.status_code, 200, by_another_person.content)
        by_an_agent = self.as_key(self.confirmer, {"flags": ["advice_perimeter"]})
        self.assertEqual(by_an_agent.status_code, 200, by_an_agent.content)

    def test_a_type_that_moved_since_it_was_checked_is_not_confirmed(self) -> None:
        """The confirmer names the type it checked; a type corrected since is refused rather
        than confirmed unread."""
        response = self.as_key(self.confirmer, {"changeType": "proposal"})
        self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))
        self.assertIn("the type proposal", response.json()["detail"])
        self.assertTrue(self.nothing_confirmed())
        self.assertFalse(AiGeneration.objects.filter(purpose="agent_review").exists(), "a refusal logs nothing")

    def test_only_what_the_change_carries_is_confirmed(self) -> None:
        for body in ({"flags": ["ai"]}, {"obligationIds": [str(self.second.id)]}, {"termIds": [str(uuid.uuid4())]}, {}):
            with self.subTest(body=body):
                response = self.as_key(self.confirmer, body)
                self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))
        self.assertTrue(self.nothing_confirmed())

    def test_a_repeated_confirmation_confirms_nothing_twice_and_writes_nothing(self) -> None:
        """A retry in the same run answers the change as it stands and writes nothing: the
        run's decision on this change is logged once, and so is the audit row."""
        self.as_key(self.confirmer, {"flags": ["advice_perimeter"]})
        first = self.reform.term_links.get(flag__key="advice_perimeter").confirmed_at
        again = self.as_key(self.confirmer, {"flags": ["advice_perimeter"]})
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["flags"][0]["confirmedOrigin"], "agent")
        self.assertEqual(self.reform.term_links.get(flag__key="advice_perimeter").confirmed_at, first)
        self.assertEqual(AiGeneration.objects.filter(purpose="agent_review", subject_id=self.reform.id).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="regulatory_change.curation_confirmed").count(), 1)
        with as_editor(self.editor, stepped_up=True):
            repeated = self.post({"flags": ["advice_perimeter"]}, AS_SESSION)
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertEqual(AuditEvent.objects.filter(action="regulatory_change.curation_confirmed").count(), 1)

    def test_another_runs_decision_on_confirmed_facts_is_still_logged(self) -> None:
        """A decision is a model call, and every model call is logged (D-80): a second run
        that finds the facts already confirmed still has its first decision on the change
        recorded, and confirms nothing."""
        self.as_key(self.confirmer, {"flags": ["advice_perimeter"]})
        later = agent_build.platform_run(key=self.confirmer)
        again = self.as_key(self.confirmer, {"flags": ["advice_perimeter"]}, run=later)
        self.assertEqual(again.status_code, 200, again.content)
        logged = AiGeneration.objects.filter(purpose="agent_review", subject_id=self.reform.id)
        self.assertEqual(sorted(str(row.agent_run_id) for row in logged), sorted([str(self.review.id), str(later.id)]))
        latest = AuditEvent.objects.filter(action="regulatory_change.curation_confirmed").order_by("-created", "-id").first()
        self.assertEqual(latest.after["confirmed"], [])  # type: ignore[union-attr]

    def test_the_database_refuses_a_confirmation_the_route_would_refuse(self) -> None:
        """The check constraints hold on their own, whatever a caller bypasses (D-74)."""
        flag = self.reform.term_links.get(flag__key="advice_perimeter")
        now = timezone.now()
        confirmer, sweeper = self.confirmer, self.sweeper
        with watch_write("test"):
            ChangeTerm.objects.filter(pk=flag.pk).update(suggested_by_id=self.editor.id)
        refused: dict[str, dict[str, Any]] = {
            "the suggesting person": {"confirmed_by_id": self.editor.id},
            "the suggesting agent": {"confirmed_by_api_key_id": confirmer.id, "confirmed_by_agent_id": sweeper.agent.id},
            "the suggesting key": {"confirmed_by_api_key_id": sweeper.id, "confirmed_by_agent_id": confirmer.agent.id},
            "a key with no agent": {"confirmed_by_api_key_id": confirmer.id},
            "a person and a key": {
                "confirmed_by_id": self.editor.id,
                "confirmed_by_api_key_id": confirmer.id,
                "confirmed_by_agent_id": confirmer.agent.id,
            },
            "nobody": {},
        }
        for who, columns in refused.items():
            with self.subTest(who=who), self.assertRaises(IntegrityError), transaction.atomic(), watch_write("test"):
                ChangeTerm.objects.filter(pk=flag.pk).update(suggested=False, confirmed_at=now, **columns)
        with watch_write("test"):
            ChangeTerm.objects.filter(pk=flag.pk).update(
                suggested=False, confirmed_at=now, confirmed_by_api_key_id=confirmer.id, confirmed_by_agent_id=confirmer.agent.id
            )
        with self.assertRaises(IntegrityError), transaction.atomic(), watch_write("test"):
            RegulatoryChange.objects.filter(pk=self.reform.pk).update(
                change_type_suggested=False,
                change_type_confirmed_at=now,
                change_type_confirmed_by_api_key_id=sweeper.id,
                change_type_confirmed_by_agent_id=sweeper.agent.id,
            )

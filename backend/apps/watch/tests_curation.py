"""A change's facts, its timeline and the obligations it affects, over the real routes
(WAT-03, WAT-04, AGT-01, AUD-01).

The one rule every test here circles: an agent proposes and a person decides. Whatever a
key files, and whatever a library editor corrects, is stored as a suggestion — `suggested`
true, nobody in `confirmed_by`, no time in `confirmed_at` — and the module is held to that
by a reading of its own source as well as by its behaviour, so a confirmation cannot be
added quietly while `q-editor-confirm` is open.

Written before the logic (2026-09-21): every case below answered 501 `not_built` against
the declared contract until `watch/curation.py` was built.
"""

from __future__ import annotations

import ast
import datetime
import uuid
from pathlib import Path
from typing import Any

from django.test import TestCase

from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.models import Instrument, Obligation
from apps.shared import factories, permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)
from apps.watch import testing as watch_build
from apps.watch.models import ChangeObligation, ChangeTerm, RegulatoryChange
from apps.watch.write import watch_write

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}


def as_agent() -> Any:
    """A platform key bound to an agent, holding the one scope these routes want."""
    return stub_api_key(agent_principal(scopes={perms.SCOPE_CHANGES_WRITE}))


def as_editor(user: Any) -> Any:
    """A library editor's console session. No tenant: `proposals.review` is a platform
    permission and no bank's role holds it (PRO-01)."""
    return stub_session(user_principal(permissions={perms.PROPOSALS_REVIEW}, subject_id=user.id))


def confirm(link: Any) -> Any:
    """A library editor's confirmation, planted directly.

    No route writes this, which is the whole point of the held task
    `c5-watch-curation-confirm`; the tests below need a confirmed fact to prove that
    curation refuses to move one, so they write it themselves through the watch door.
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
        """Until `q-editor-confirm` is answered nobody confirms a change's facts, so a
        library editor correcting a run leaves the fact exactly as unconfirmed as it was."""
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
    """The seam between this task and the held `c5-watch-curation-confirm`: nothing here
    confirms anything, and nothing here unmakes a confirmation either."""

    def setUp(self) -> None:
        super().setUp()
        self.confirmed = confirm(self.term_links(flags=True)[0])

    def test_a_key_cannot_drop_a_flag_an_editor_confirmed(self) -> None:
        with as_agent():
            response = self.patch_change({"flags": ["ai"]})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "confirmed_fact")
        self.confirmed.refresh_from_db()
        self.assertFalse(self.confirmed.suggested, "the confirmation stands")

    def test_an_editor_dropping_a_confirmed_flag_meets_the_held_half(self) -> None:
        with as_editor(self.editor):
            response = self.client.patch(
                f"/api/v1/changes/{self.change.id}",
                data={"flags": ["ai"]},
                content_type="application/json",
                **AS_SESSION,
            )
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["code"], "not_built")

    def test_a_confirmed_flag_that_stays_is_left_untouched(self) -> None:
        with as_agent():
            response = self.patch_change({"flags": ["advice_perimeter", "ai"]})
        self.assertEqual(response.status_code, 200, response.content)
        self.confirmed.refresh_from_db()
        self.assertFalse(self.confirmed.suggested)
        self.assertIsNotNone(self.confirmed.confirmed_by_id)
        self.assertEqual(len(self.term_links(flags=True)), 2)


class NothingHereConfirms(TestCase):
    """The done-condition read off the source: no code path in this task writes
    `suggested = false`, `confirmed_by` or `confirmed_at`.

    A behaviour test can only prove the paths it walks; this walks the module's whole AST,
    so a confirmation cannot be added to a branch nobody tested while `q-editor-confirm` is
    open (CLAUDE.md section 5).
    """

    # The three columns that together say "a person settled this" (`change_term`,
    # `change_obligation`), and the ORM calls that could put a value in one.
    CONFIRMATION = ("confirmed_by", "confirmed_at", "confirmed_by_id")
    WRITES = frozenset({"create", "update", "update_or_create", "get_or_create", "bulk_create", "bulk_update"})

    def test_the_curation_module_never_writes_a_confirmation(self) -> None:
        module = Path(__file__).resolve().parent / "curation.py"
        tree = ast.parse(module.read_text(encoding="utf-8"))
        written: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign | ast.AnnAssign):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    name = target.attr if isinstance(target, ast.Attribute) else ""
                    if name in self.CONFIRMATION:
                        written.append(f"{name} = ...")
                    if name == "suggested" and _is_false(node.value):
                        written.append("suggested = False")
            if isinstance(node, ast.Call) and _method(node) in self.WRITES:
                for keyword in node.keywords:
                    if keyword.arg in self.CONFIRMATION:
                        written.append(f"{_method(node)}({keyword.arg}=...)")
                    if keyword.arg == "suggested" and _is_false(keyword.value):
                        written.append(f"{_method(node)}(suggested=False)")
        self.assertEqual(
            written,
            [],
            "apps/watch/curation.py writes a confirmation. Confirming a change's library facts is "
            "the held task c5-watch-curation-confirm and waits on q-editor-confirm (CLAUDE.md section 5).",
        )

    def test_a_term_link_is_written_as_a_suggestion(self) -> None:
        """The other half of the rule: the one place this module puts a term link on a
        change says `suggested` true, so the AST test above is not passing on an absence."""
        source = (Path(__file__).resolve().parent / "curation.py").read_text(encoding="utf-8")
        self.assertIn('"suggested": True', source)


def _is_false(value: Any) -> bool:
    return isinstance(value, ast.Constant) and value.value is False


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

    def test_a_key_cannot_remove_a_link_an_editor_confirmed(self) -> None:
        confirm(watch_build.obligation_link(self.change, self.first))
        with as_agent():
            response = self.put_links([{"obligationId": str(self.second.id)}])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "confirmed_fact")
        self.assertEqual(self.change.obligation_links.count(), 1)

    def test_an_editor_removing_a_confirmed_link_meets_the_held_half(self) -> None:
        confirm(watch_build.obligation_link(self.change, self.first))
        with as_editor(self.editor):
            response = self.put_links([{"obligationId": str(self.second.id)}], headers=AS_SESSION)
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["code"], "not_built")

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

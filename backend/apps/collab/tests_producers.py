"""The participation and involved-item producers (`collab/producers.py`; COL-02, COL-04,
HOM-05, D-25, D-97). COL-S10's body lives at the end of this module and runs from
tests_scenarios.py.

Each producer is proved to make exactly one `notify()` call per event, naming candidates and
a reason and deciding nothing else; the person who acted is never a candidate; a suggestion
nobody confirmed notifies nobody; and the involved-item notices come off the one ordered
cursor, registered from the collab app's `ready()`, never from library or watch code.

Proven to fail 2026-09-25: with the adder no longer filtered out, the team add named Anna;
with `after_link_confirmed` reading the change's obligation links rather than the names the
confirmation confirmed, a flag confirmation told the people involved in a link still only
suggested; with the actor filter removed the confirming member and the reviewer were told.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from django.apps import apps as installed
from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.agents import testing as agent_build
from apps.cases import testing as case_build
from apps.collab import producers
from apps.collab import testing as collab_testing
from apps.collab.models import EmailMessage, Notification, Participant
from apps.identity.models import Membership, TenantRole, User
from apps.library import testing as library_build
from apps.library.models import Obligation
from apps.proposals.reading import VERSION_APPLIED
from apps.shared import factories, outbox, tenancy
from apps.shared import permissions as perms
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import Tenant
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.watch import testing as watch_build
from apps.watch.curation import CURATION_CONFIRMED

V1 = "/api/v1"
TITLES = {"en": "Assess the quality of investment research paid for", "sv": "Bedöm kvaliteten på betald analys"}
DECISION = {
    "model": "claude-opus-5",
    "modelVersion": "2026-05-01",
    "promptTemplate": "library-confirmer/curation/v1",
    "output": "Confirm. The decision memorandum names this duty.",
    "citations": [{"label": "Finansinspektionen, decision memorandum", "url": "https://www.fi.se/"}],
}


# ---------------------------------------------------------------------------------------
# The world COL-S10 describes, reused by the tests below
# ---------------------------------------------------------------------------------------
def involved_bank(slug: str, obligation: Obligation) -> SimpleNamespace:
    """A bank whose register entry on `obligation` Anna owns, in which Erik and the team
    "Legal" (Anna, Karin, Lisa and Johan) take part. Lisa's role lacks `register.read` and
    Johan is deactivated. Karin reads Swedish."""
    tenant = factories.tenant(slug=slug)
    anna = factories.member_user(tenant, roles=("compliance_officer",))
    erik = factories.member_user(tenant, roles=("contributor",))
    karin = factories.member_user(tenant, roles=("reader",))
    User.objects.filter(pk=karin.pk).update(locale=factories.language("sv"))
    tenancy.activate(tenant.id)
    TenantRole.objects.create(tenant=tenant, key="cases-only", permissions=[perms.CASES_READ])
    lisa = factories.member_user(tenant, roles=("cases-only",))
    johan = factories.member_user(tenant, roles=("reader",))
    tenancy.activate(tenant.id)
    Membership.objects.filter(user=johan).update(deactivated_at=timezone.now())
    legal = collab_testing.team(tenant, "legal", "Legal")
    for person in (anna, karin, lisa, johan):
        factories.team_member(tenant, legal, person)
    entry = factories.register_entry(tenant, obligation.id, first_line_owner=anna)
    tenancy.activate(tenant.id)
    Participant.objects.create(tenant=tenant, tenant_obligation=entry, user=erik, added_by=anna)
    Participant.objects.create(tenant=tenant, tenant_obligation=entry, team=legal, added_by=anna)
    return SimpleNamespace(tenant=tenant, anna=anna, erik=erik, karin=karin, lisa=lisa, johan=johan, legal=legal, entry=entry)


def shared_obligation(key: str) -> Obligation:
    watch_build.seed_watch_reference()
    tenancy.clear_tenant()
    on = library_build.instrument(key=f"inst-{key}", regime="regime:securities")
    return library_build.obligation(on, key=key, titles=TITLES)


def deliver() -> None:
    """Run the one ordered cursor until nothing is left, as the worker does."""
    while outbox.deliver_batch().delivered:
        pass


def confirm_as_person(case: TestCase, editor: User, change_id: uuid.UUID, body: dict[str, Any]) -> None:
    response = case.client.post(
        f"{V1}/changes/{change_id}/confirmation", body, content_type="application/json", **sign_in(editor, step_up=True)
    )
    case.assertEqual(response.status_code, 200, response.content)


def apply_version(case: TestCase, tenant: Tenant, obligation: Obligation, reviewer: User) -> None:
    """A new version of `obligation`, proposed through a bank's key and approved by a
    library editor with a fresh passkey: the one door a version comes through (PRO-02)."""
    key = factories.api_key(tenant, scopes=("proposals:write",))
    created = case.client.post(
        f"{V1}/proposals",
        {
            "kind": "new_obligation_version",
            "title": "Version 2, in force 1 October 2026",
            "targetType": "obligation",
            "targetId": str(obligation.id),
            "payload": {
                "summaries": {"sv": "Institutet bedömer analysen.", "en": "The institution assesses the research."},
                "originalLanguage": "sv",
                "isMachine": True,
                "effectiveFrom": "2026-10-01",
                "effectiveFromPrecision": "day",
            },
            "fieldSources": {"summaries.sv": "https://www.fi.se/", "summaries.en": "https://www.fi.se/", "effectiveFrom": "https://www.fi.se/"},
            "sourceLabel": "Finansinspektionen, board decision",
            "sourceUrl": "https://www.fi.se/",
        },
        content_type="application/json",
        HTTP_X_API_KEY=key.plain_key,
    )
    case.assertEqual(created.status_code, 201, created.content)
    approved = case.client.post(
        f"{V1}/proposals/{created.json()['id']}/approve", {}, content_type="application/json", **sign_in(reviewer, step_up=True)
    )
    case.assertEqual(approved.status_code, 200, approved.content)


def told(tenant: Tenant, kind: str) -> list[tuple[uuid.UUID, uuid.UUID]]:
    tenancy.activate(tenant.id)
    return sorted(Notification.objects.filter(kind=kind).values_list("user_id", "subject_id"))


class Counting:
    """`notify()` as the producers call it, still writing, with every call's arguments."""

    def __init__(self, case: TestCase) -> None:
        self.calls: list[dict[str, Any]] = []
        real = producers.notify

        def counted(**arguments: Any) -> Any:  # compliance: allow-kwargs test double forwarding notify()'s keyword arguments
            self.calls.append(arguments)
            return real(**arguments)

        patched = mock.patch.object(producers, "notify", counted)
        patched.start()
        case.addCleanup(patched.stop)

    def candidates(self, index: int = 0) -> set[tuple[uuid.UUID, str]]:
        return set(self.calls[index]["candidates"])


# ---------------------------------------------------------------------------------------
# participant_added
# ---------------------------------------------------------------------------------------
class ParticipantAdded(TestCase):
    def setUp(self) -> None:
        self.obligation = collab_testing.obligation()
        self.tenant = factories.tenant(slug="producers-added")
        self.anna = factories.member_user(self.tenant, roles=("compliance_officer",))
        self.erik = factories.member_user(self.tenant, roles=("contributor",))
        self.karin = factories.member_user(self.tenant, roles=("reader",))
        self.legal = collab_testing.team(self.tenant, "legal", "Legal")
        for person in (self.anna, self.karin):
            factories.team_member(self.tenant, self.legal, person)
        self.as_anna = sign_in(self.anna, tenant=self.tenant)
        self.url = f"{V1}/obligations/{self.obligation.id}/participants"

    def add(self, payload: dict[str, str]) -> Any:
        return self.client.post(self.url, payload, content_type="application/json", **self.as_anna)

    def test_a_person_added_is_one_call_naming_them_and_nobody_else(self) -> None:
        calls = Counting(self)
        self.assertEqual(self.add({"userId": str(self.erik.id)}).status_code, 201)
        self.assertEqual(len(calls.calls), 1)
        (call,) = calls.calls
        self.assertEqual(set(call), {"tenant_id", "kind", "subject_type", "subject_id", "candidates"})
        self.assertEqual((call["kind"].value, call["subject_type"]), ("participant_added", "tenant_obligation"))
        self.assertEqual(calls.candidates(), {(self.erik.id, "participant")})
        tenancy.activate(self.tenant.id)
        entry_id = Participant.objects.get(user=self.erik).tenant_obligation_id
        self.assertEqual(told(self.tenant, "participant_added"), [(self.erik.id, entry_id)])

    def test_a_team_added_reaches_its_members_and_never_the_adder(self) -> None:
        calls = Counting(self)
        self.assertEqual(self.add({"teamKey": "legal"}).status_code, 201)
        self.assertEqual(len(calls.calls), 1)
        self.assertEqual(calls.candidates(), {(self.karin.id, "team")})
        self.assertEqual([user for user, _entry in told(self.tenant, "participant_added")], [self.karin.id])

    def test_adding_yourself_tells_nobody(self) -> None:
        calls = Counting(self)
        self.assertEqual(self.add({"userId": str(self.anna.id)}).status_code, 201)
        self.assertEqual(calls.candidates(), set())
        self.assertEqual(told(self.tenant, "participant_added"), [])

    def test_a_refused_add_tells_nobody(self) -> None:
        self.assertEqual(self.add({"userId": str(self.erik.id)}).status_code, 201)
        again = self.add({"userId": str(self.erik.id)})
        self.assertEqual((again.status_code, again.json()["code"]), (409, "already_participant"))
        self.assertEqual(len(told(self.tenant, "participant_added")), 1)

    def test_it_sends_no_mail(self) -> None:
        MockMailer.reset()
        self.addCleanup(MockMailer.reset)
        self.add({"userId": str(self.erik.id)})
        self.assertEqual(MockMailer.sent, [])
        tenancy.activate(self.tenant.id)
        self.assertFalse(EmailMessage.objects.exists())

    def test_a_case_participant_is_told_about_the_case(self) -> None:
        watch_build.seed_watch_reference()
        row = case_build.case(self.tenant, watch_build.change(), owner=self.anna)
        calls = Counting(self)
        response = self.client.post(
            f"{V1}/changes/{row.change_id}/participants", {"userId": str(self.erik.id)}, content_type="application/json", **self.as_anna
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(calls.calls), 1)
        self.assertEqual(told(self.tenant, "participant_added"), [(self.erik.id, row.id)])
        tenancy.activate(self.tenant.id)
        self.assertEqual(Notification.objects.get(user=self.erik).subject_type, "change_case")


# ---------------------------------------------------------------------------------------
# involved_item_changed
# ---------------------------------------------------------------------------------------
class InvolvedItemChanged(TestCase):
    def setUp(self) -> None:
        self.obligation = shared_obligation(f"obl-producers-{uuid.uuid4().hex[:8]}")
        self.bank = involved_bank("producers-involved", self.obligation)
        self.editor = factories.platform_user(roles=("library_editor",), email=f"editor-{uuid.uuid4().hex[:6]}@bleqq.test")
        tenancy.clear_tenant()
        self.change = watch_build.change()
        watch_build.obligation_link(self.change, self.obligation)
        self.everyone = {(self.bank.anna.id, "owner"), (self.bank.erik.id, "participant")} | {
            (person.id, "team") for person in (self.bank.anna, self.bank.karin, self.bank.lisa, self.bank.johan)
        }

    def test_a_persons_confirmed_link_is_one_call_per_entry_with_every_involved_person(self) -> None:
        calls = Counting(self)
        confirm_as_person(self, self.editor, self.change.id, {"obligationIds": [str(self.obligation.id)]})
        self.assertEqual(calls.calls, [], "nothing is told inside the library's request")
        deliver()
        self.assertEqual(len(calls.calls), 1)
        (call,) = calls.calls
        self.assertEqual(set(call), {"tenant_id", "kind", "subject_type", "subject_id", "candidates"})
        self.assertEqual(
            (call["tenant_id"], call["kind"].value, call["subject_type"], call["subject_id"]),
            (self.bank.tenant.id, "involved_item_changed", "tenant_obligation", self.bank.entry.id),
        )
        self.assertEqual(calls.candidates(), self.everyone)
        self.assertEqual(
            told(self.bank.tenant, "involved_item_changed"),
            sorted((person.id, self.bank.entry.id) for person in (self.bank.anna, self.bank.erik, self.bank.karin)),
        )

    def test_the_confirming_person_is_never_a_candidate(self) -> None:
        factories.member(self.bank.tenant, roles=("reader",), user_row=self.editor)
        tenancy.activate(self.bank.tenant.id)
        Participant.objects.create(tenant=self.bank.tenant, tenant_obligation=self.bank.entry, user=self.editor, added_by=self.bank.anna)
        calls = Counting(self)
        confirm_as_person(self, self.editor, self.change.id, {"obligationIds": [str(self.obligation.id)]})
        deliver()
        self.assertEqual(calls.candidates(), self.everyone)
        self.assertNotIn(self.editor.id, [user for user, _entry in told(self.bank.tenant, "involved_item_changed")])

    def test_an_independent_agents_confirmation_counts(self) -> None:
        """D-97: a link an agent of another definition confirmed reaches the people involved."""
        tenancy.clear_tenant()
        sweeper = agent_build.agent_key(scopes=agent_build.WATCH_SCOPES)
        reform = watch_build.change(run=agent_build.platform_run(key=sweeper))
        watch_build.obligation_link(reform, self.obligation)
        confirmer = agent_build.agent_key(
            agent_row=agent_build.agent(key="library-confirmer"),
            scopes=("agent-runs:write", "library:read", perms.SCOPE_PROPOSALS_REVIEW),
        )
        run = agent_build.platform_run(key=confirmer)
        response = self.client.post(
            f"{V1}/changes/{reform.id}/confirmation",
            {"obligationIds": [str(self.obligation.id)], "decision": DECISION, "agentRunId": str(run.id)},
            content_type="application/json",
            HTTP_X_API_KEY=confirmer.plain_key,
        )
        self.assertEqual(response.status_code, 200, response.content)
        deliver()
        self.assertEqual(len(told(self.bank.tenant, "involved_item_changed")), 3)

    def test_a_suggestion_nobody_confirmed_notifies_nobody(self) -> None:
        tenancy.clear_tenant()
        key = agent_build.agent_key(scopes=agent_build.WATCH_SCOPES)
        run = agent_build.platform_run(key=key)
        reform = watch_build.change(run=run)
        response = self.client.put(
            f"{V1}/changes/{reform.id}/obligations",
            [{"obligationId": str(self.obligation.id), "confidence": 0.9}],
            content_type="application/json",
            HTTP_X_API_KEY=key.plain_key,
        )
        self.assertEqual(response.status_code, 200, response.content)
        deliver()
        self.assertEqual(told(self.bank.tenant, "involved_item_changed"), [])

    def test_confirming_a_flag_names_no_item(self) -> None:
        tenancy.clear_tenant()
        watch_build.term_link(self.change, flag_key="advice_perimeter")
        calls = Counting(self)
        confirm_as_person(self, self.editor, self.change.id, {"flags": ["advice_perimeter"]})
        deliver()
        self.assertEqual(calls.calls, [])

    def test_each_bank_hears_only_about_its_own_entry(self) -> None:
        other = involved_bank("producers-involved-other", self.obligation)
        without = factories.tenant(slug="producers-involved-none")
        factories.member_user(without, roles=("compliance_officer",))
        confirm_as_person(self, self.editor, self.change.id, {"obligationIds": [str(self.obligation.id)]})
        deliver()
        self.assertEqual({entry for _user, entry in told(self.bank.tenant, "involved_item_changed")}, {self.bank.entry.id})
        self.assertEqual({entry for _user, entry in told(other.tenant, "involved_item_changed")}, {other.entry.id})
        self.assertEqual(told(without, "involved_item_changed"), [])

    def test_a_new_version_tells_the_people_involved_and_never_the_reviewer(self) -> None:
        factories.member(self.bank.tenant, roles=("reader",), user_row=self.editor)
        tenancy.activate(self.bank.tenant.id)
        Participant.objects.create(tenant=self.bank.tenant, tenant_obligation=self.bank.entry, user=self.editor, added_by=self.bank.anna)
        calls = Counting(self)
        apply_version(self, self.bank.tenant, self.obligation, self.editor)
        self.assertEqual(calls.calls, [], "nothing is told inside the approval")
        deliver()
        self.assertEqual(len(calls.calls), 1)
        self.assertEqual(calls.candidates(), self.everyone)
        self.assertEqual(len(told(self.bank.tenant, "involved_item_changed")), 3)


class Registration(TestCase):
    def test_the_handlers_come_back_from_the_collab_apps_ready(self) -> None:
        from apps.shared.tests_outbox import only_the_consumers_are_registered

        self.addCleanup(only_the_consumers_are_registered)
        outbox._HANDLERS.clear()
        installed.get_app_config("collab").ready()
        installed.get_app_config("collab").ready()
        self.assertEqual(outbox.handlers_for(CURATION_CONFIRMED), (producers.after_link_confirmed,))
        self.assertEqual(outbox.handlers_for(VERSION_APPLIED), (producers.after_version_applied,))

    def test_no_library_or_watch_module_calls_a_producer(self) -> None:
        """The notices come off the cursor: library-zone code never reaches into collab."""
        root = Path(settings.BASE_DIR) / "apps"
        offenders = []
        for app in ("library", "watch", "proposals"):
            for path in sorted((root / app).rglob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("apps.collab"):
                        offenders.append(path.name)
        self.assertEqual(offenders, [])


# ---------------------------------------------------------------------------------------
# COL-S10, run by tests_scenarios.py (one method per scenario there)
# ---------------------------------------------------------------------------------------
def run_col_s10(case: ScenarioTestCase) -> None:
    obligation = shared_obligation("obl-col-s10")
    # Given Anna owns an obligation and Erik takes part in it
    # And the team "Legal" with members Anna, Karin, Lisa and Johan takes part in it
    # And Lisa's role lacks register.read and Johan is deactivated
    bank = involved_bank("col-s10", obligation)
    officer = factories.member_user(bank.tenant, roles=("compliance_officer",))
    editor = factories.platform_user(roles=("library_editor",), email="col-s10.editor@bleqq.test")
    # The editor who confirms the link and then approves the version is also a member of the
    # bank taking part, so "none for the confirmer" is a refusal and not an absence.
    factories.member(bank.tenant, roles=("reader",), user_row=editor)
    tenancy.activate(bank.tenant.id)
    Participant.objects.create(tenant=bank.tenant, tenant_obligation=bank.entry, user=editor, added_by=bank.anna)
    watch_build.seed_watch_reference()
    row = case_build.case(bank.tenant, watch_build.change(), owner=officer)
    MockMailer.reset()
    case.addCleanup(MockMailer.reset)

    # When Erik is added to a case
    added = case.client.post(
        f"{V1}/changes/{row.change_id}/participants",
        {"userId": str(bank.erik.id)},
        content_type="application/json",
        **sign_in(officer, tenant=bank.tenant),
    )
    case.assertEqual(added.status_code, 201, added.content)
    # Then Erik receives one "participant_added" notification linking to the case
    tenancy.activate(bank.tenant.id)
    (notice,) = Notification.objects.filter(kind="participant_added")
    case.assertEqual((notice.user_id, notice.subject_type, notice.subject_id), (bank.erik.id, "change_case", row.id))

    # When a link from a change to the obligation is confirmed
    tenancy.clear_tenant()
    change = watch_build.change()
    watch_build.obligation_link(change, obligation)
    confirm_as_person(case, editor, change.id, {"obligationIds": [str(obligation.id)]})
    deliver()
    # Then Anna, Erik and Karin each receive one "involved_item_changed" notification, Anna
    # once although she is involved twice
    involved = [bank.anna.id, bank.erik.id, bank.karin.id]
    case.assertEqual(told(bank.tenant, "involved_item_changed"), sorted((user, bank.entry.id) for user in involved))
    # And the person who confirmed it, Lisa and Johan receive none (the assertion above is
    # the whole list, so none of them is in it)

    # When a new version of the obligation is applied
    apply_version(case, bank.tenant, obligation, editor)
    deliver()
    # Then the same people are notified once each, in their own language
    case.assertEqual(
        told(bank.tenant, "involved_item_changed"), sorted((user, bank.entry.id) for user in involved for _ in range(2))
    )
    tenancy.activate(bank.tenant.id)
    titles = dict(Notification.objects.filter(kind="involved_item_changed").values_list("user_id", "title"))
    case.assertEqual(titles, {bank.anna.id: TITLES["en"], bank.erik.id: TITLES["en"], bank.karin.id: TITLES["sv"]})
    # And no notification title or email carries tenant text, only the library title and a link
    for title in Notification.objects.values_list("title", flat=True):
        case.assertIn(title, {*TITLES.values(), row.change.title})
    case.assertEqual(MockMailer.sent, [])
    case.assertFalse(EmailMessage.objects.exists())

"""Decide all, run by the worker (apps/register/decide_all.py; REG-01, D-75, D-128, AC-REG1).

One confirmed call names a company, an answer and one reason, and optionally a regulation or
ticked rows. Proved through the two routes as a real session and through the task as the
worker runs it: the targets are what nobody had answered when the call was made, each is set
through `applicability._store` with its own audit event, an answer a person gave in between
survives, and the reason reaches neither a task argument nor a log line.

Tenant A's Example Bank AB is offered six obligations. Two are answered before any run: one
the officer answered "does not apply", one a colleague deliberately left under assessment
with a reason. Four are unanswered: three that span several companies, answered on the
bank's own row, and one on banks alone, answered for the obligation as a whole.

Proven to fail 2026-11-13, each by one change put back afterwards. In `decide_all.py`: with
the decider check dropped from the chunk, the colleague's answer was overwritten here and in
REG-S20; with the reason riding in the run id, a task argument, the argument test named it,
and with a log line naming it, the log capture did; with the permission never read again,
both stop tests set every row; with the run id left unchecked, the replaced run decided
under the new run's reason; with the run's place left unchecked, a chunk delivered twice
queued a second chain; with the offered check left out of the chunk, the custody duty outside
the working inventory was answered. In `company_view.py`: with to-decide read from the answer
alone, the colleague's row left under assessment became a target (21 tests here, and the
read's own in tests_company_view.py).
"""

from __future__ import annotations

import inspect
import json
import logging
import uuid
from datetime import timedelta
from typing import Any, cast
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext, override_settings
from django.utils import timezone

from apps.identity.models import Membership, MembershipRole, User
from apps.identity.session_logic import actor_of
from apps.library import testing as library_build
from apps.library.models import Obligation, RecurringDuty
from apps.library.tests_reading import set_footprint
from apps.register import applicability, company_view, decide_all, tasks
from apps.register.applicability import APPLICABILITY_SET
from apps.register.duties import DUTY_SCHEDULED
from apps.register.logic import ENTRY_CREATED
from apps.register.models import DutyOccurrence, TenantObligation, TenantObligationScope
from apps.register.schemas import RegisterApplicabilityBody
from apps.register.tests_applicability import Bank, seed_library
from apps.register.tests_company_view import exclude
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import API_KEY_FOR_TESTS, ScenarioTestCase, agent_principal, is_tenant_task, sign_in, stub_api_key
from apps.taxonomy.models import FootprintTerm
from apps.tenants.models import OrgUnit
from config.celery import app as celery_app

V1 = "/api/v1"
ROUTE = f"{V1}/applicability/decide-all"
# A sentence nothing else in a run writes, so finding it anywhere is finding the reason.
REASON = "Covered by the securities licence the group holds since 2019."
PARKED = "Waiting for the legal opinion"
STATE_FIELDS = {
    "status", "total", "set", "skipped", "refused", "refusals", "stopped", "orgUnitId", "instrument", "applicability", "startedAt", "updatedAt",
}  # fmt: skip
IDLE = {
    "status": "idle", "total": 0, "set": 0, "skipped": 0, "refused": 0, "refusals": [], "stopped": None,
    "orgUnitId": None, "instrument": None, "applicability": None, "startedAt": None, "updatedAt": None,
}  # fmt: skip


def answer(tenant: Tenant, person: User, duty: Obligation, entity: OrgUnit | None, word: str, reason: str) -> None:
    """One confirmed answer, stored as `PUT /obligations/{obligationId}/applicability` stores it."""
    body = RegisterApplicabilityBody.model_validate({"orgUnitId": entity and str(entity.id), "applicability": word, "reason": reason})
    with transaction.atomic():
        tenancy.activate(tenant.id)
        applicability.set_applicability(tenant=tenant, actor=actor_of(person), order=["en"], obligation_id=duty.id, body=body, expected_version=None)


class _Captured(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{record.getMessage()} {record.__dict__}")


class DecideAllCase(ScenarioTestCase):
    a: Bank
    b: Bank
    colleague: User
    law: Any
    shared: Obligation
    single: Obligation
    everyone: Obligation
    parked: Obligation
    answered: Obligation
    insurers: Obligation
    outside: Obligation
    payments: Obligation
    duty: RecurringDuty

    @classmethod
    def setUpTestData(cls) -> None:
        seed_library()
        cls.a = Bank("da-a")
        cls.b = Bank("da-b")
        cls.colleague = factories.member(cls.a.tenant, roles=("compliance_officer",), user_row=factories.user(name="Erik Holm")).user
        set_footprint(cls.a.tenant, ("service_type:custody",))
        cls.law = library_build.instrument(key="da-lvm", short_name="LVM", regime="regime:securities")
        lob = library_build.instrument(key="da-lob", short_name="LOB", regime="regime:payments")
        cls.shared = library_build.obligation(
            cls.law, key="da-lvm-1-shared", ref_label="1 §", titles={"en": "Keep client assets apart"}, terms=("legal_entity:bank", "legal_entity:fund_company")
        )
        cls.single = library_build.obligation(cls.law, key="da-lvm-2-single", ref_label="2 §", titles={"en": "Report large exposures"}, terms=("legal_entity:bank",))
        cls.everyone = library_build.obligation(cls.law, key="da-lvm-3-everyone", ref_label="3 §", titles={"en": "Record client orders"})
        cls.parked = library_build.obligation(cls.law, key="da-lvm-4-parked", ref_label="4 §")
        cls.answered = library_build.obligation(cls.law, key="da-lvm-5-answered", ref_label="5 §")
        cls.insurers = library_build.obligation(cls.law, key="da-lvm-6-insurers", ref_label="6 §", terms=("legal_entity:insurer",))
        cls.outside = library_build.obligation(cls.law, key="da-lvm-7-outside", ref_label="7 §", terms=("service_type:advice",))
        cls.payments = library_build.obligation(lob, key="da-lob-1-payments", ref_label="1 §", titles={"en": "Safeguard client funds"})
        cls.duty = library_build.recurring_duty(cls.everyone)
        answer(cls.a.tenant, cls.a.officer, cls.answered, cls.a.bank_ab, "not_applicable", "No such business")
        answer(cls.a.tenant, cls.colleague, cls.parked, cls.a.bank_ab, "under_assessment", PARKED)

    def setUp(self) -> None:
        cache.clear()
        self.bank = str(self.a.bank_ab.id)
        # What a run for Example Bank AB decides, in the inventory's order.
        self.targets = [self.payments, self.shared, self.single, self.everyone]

    # --- The two routes and the worker ---
    def body(self, changes: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"orgUnitId": self.bank, "applicability": "applies", "reason": REASON, **(changes or {})}

    def start(self, changes: dict[str, Any] | None = None, *, who: Any = None, tenant: Tenant | None = None) -> Any:
        """`POST /applicability/decide-all` as the officer, committed: the run's state is kept
        and the worker, eager in tests, decides."""
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                ROUTE, data=self.body(changes), content_type="application/json", **sign_in(who or self.a.officer, tenant=tenant or self.a.tenant)
            )

    def start_held(self, changes: dict[str, Any] | None = None) -> tuple[dict[str, Any], tuple[Any, ...]]:
        """Start with the worker held back: the state the call answered, and the arguments
        its task was queued with."""
        with mock.patch.object(tasks.decide_listed, "delay") as queued:
            response = self.start(changes)
        self.assertEqual(response.status_code, 202, response.content)
        queued.assert_called_once()
        state: dict[str, Any] = response.json()
        return state, queued.call_args.args

    def work(self, args: tuple[Any, ...]) -> None:
        """The worker, from one queued task to the end of its run."""
        with self.captureOnCommitCallbacks(execute=True):
            tasks.decide_listed(*args)

    def read(self, who: Any = None, tenant: Tenant | None = None) -> dict[str, Any]:
        response = self.client.get(ROUTE, **sign_in(who or self.a.officer, tenant=tenant or self.a.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        state: dict[str, Any] = response.json()
        return state

    def state(self) -> dict[str, Any]:
        """The officer's run as the worker last wrote it, read without a session."""
        return decide_all.state_of(self.a.tenant.id, self.a.officer.id)

    def progress(self) -> tuple[Any, ...]:
        state = self.state()
        return state["status"], state["total"], state["set"], state["skipped"], state["refused"], state["stopped"]

    # --- What the bank holds ---
    def row(self, duty: Obligation, entity: OrgUnit | None = None) -> Any:
        """The row an answer lands on: one company's, or the entry for the obligation as a
        whole. None while nobody has written it."""
        self.activate(self.a.tenant)
        if entity is None:
            return TenantObligation.objects.filter(obligation=duty).first()
        return TenantObligationScope.objects.filter(tenant_obligation__obligation=duty, org_unit=entity, product__isnull=True).first()

    def answer_of(self, duty: Obligation, entity: OrgUnit | None = None) -> tuple[Any, ...] | None:
        row = self.row(duty, entity)
        if row is None:
            return None
        return row.applicability, row.applicability_reason, row.applicability_decided_by_id, row.applicability_decided_at, row.version

    def events(self, action: str) -> list[AuditEvent]:
        self.activate(self.a.tenant)
        return list(AuditEvent.objects.filter(action=action, tenant_id=self.a.tenant.id).order_by("created", "id"))

    def set_by_the_run(self) -> list[AuditEvent]:
        """The answers stored after the two the fixture gave."""
        return self.events(APPLICABILITY_SET)[2:]

    def put(self, who: Any, duty: Obligation, body: dict[str, Any]) -> Any:
        response = self.client.put(
            f"{V1}/obligations/{duty.id}/applicability", data=body, content_type="application/json", **sign_in(who, tenant=self.a.tenant)
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


# ---------------------------------------------------------------------------------------
# The start
# ---------------------------------------------------------------------------------------
class Starting(DecideAllCase):
    def test_start_reads_what_nobody_answered_at_that_moment_and_answers_202_before_anything_is_set(self) -> None:
        state, args = self.start_held()
        self.assertEqual(set(state), STATE_FIELDS)
        self.assertEqual(
            {**state, "startedAt": None, "updatedAt": None},
            {**IDLE, "status": "running", "total": 4, "orgUnitId": self.bank, "applicability": "applies"},
        )
        self.assertEqual(state["startedAt"], state["updatedAt"])
        self.assertIsNotNone(state["startedAt"])
        # The worker is handed ids and the answer: the bank, the person, the company, the
        # targets in the inventory's order and the run.
        tenant_id, user_id, org_unit_id, obligation_ids, word, run_id = args
        self.assertEqual((tenant_id, user_id, org_unit_id, word), (str(self.a.tenant.id), str(self.a.officer.id), self.bank, "applies"))
        self.assertEqual(obligation_ids, [str(duty.id) for duty in self.targets])
        self.assertTrue(run_id)
        # One audit row for the decision, with the count and the filters and never the reason.
        [decision] = self.events(decide_all.STARTED)
        self.assertEqual(
            (decision.actor_type, decision.actor_id, decision.subject_type, decision.subject_id, decision.subject_title),
            ("user", self.a.officer.id, "org_unit", self.a.bank_ab.id, "Example Bank AB"),
        )
        self.assertEqual(decision.after, {"count": 4, "orgUnitId": self.bank, "instrument": None, "applicability": "applies", "selected": False})
        self.assertNotIn(REASON, str([decision.before, decision.after, decision.summary, decision.subject_title]))
        # Nothing is set by the call itself, and the run reads as running until the worker moves.
        self.assertEqual(self.set_by_the_run(), [])
        self.assertEqual(self.read(), state)

    def test_the_total_is_what_the_what_applies_page_counts_as_to_decide(self) -> None:
        """The button says "Decide all 4" from the companies read; the run it starts lists 4."""
        reader = sign_in(self.a.owner, tenant=self.a.tenant)
        companies = {row["orgUnit"]["id"]: row for row in self.client.get(f"{V1}/applicability/companies", **reader).json()}
        for entity in (self.a.bank_ab, self.a.fonder, self.a.liv):
            with self.subTest(company=entity.name):
                cache.clear()
                state, _ = self.start_held({"orgUnitId": str(entity.id)})
                self.assertEqual(state["total"], companies[str(entity.id)]["toDecide"])
                regulations = self.client.get(f"{V1}/applicability/regulations", {"orgUnitId": str(entity.id)}, **reader).json()["items"]
                for regulation in regulations:
                    cache.clear()
                    if not regulation["toDecide"]:
                        continue
                    narrowed, _ = self.start_held({"orgUnitId": str(entity.id), "instrument": regulation["instrument"]["key"]})
                    self.assertEqual(narrowed["total"], regulation["toDecide"], regulation["instrument"]["key"])
        self.assertEqual([companies[str(entity.id)]["toDecide"] for entity in (self.a.bank_ab, self.a.fonder, self.a.liv)], [4, 5, 5])

    def test_a_regulation_narrows_the_run_to_its_own_obligations(self) -> None:
        self.assertEqual(self.start({"instrument": "da-lob"}).status_code, 202)
        state = self.read()
        self.assertEqual((state["status"], state["total"], state["set"], state["instrument"]), ("finished", 1, 1, "da-lob"))
        self.assertEqual(self.answer_of(self.payments, self.a.bank_ab)[:3], ("applies", REASON, self.a.officer.id))  # type: ignore[index]
        for duty, entity in ((self.shared, self.a.bank_ab), (self.single, None), (self.everyone, self.a.bank_ab)):
            self.assertIsNone(self.row(duty, entity), duty.stable_key)
        self.assertEqual(self.events(decide_all.STARTED)[0].after["instrument"], "da-lob")

    def test_a_selection_narrows_the_run_and_what_is_answered_in_it_is_simply_no_target(self) -> None:
        chosen = [str(duty.id) for duty in (self.everyone, self.answered, self.parked, self.shared)]
        was = {duty: self.answer_of(duty, self.a.bank_ab) for duty in (self.answered, self.parked)}
        self.assertEqual(self.start({"obligationIds": chosen}).status_code, 202)
        self.assertEqual(self.progress(), ("finished", 2, 2, 0, 0, None))
        for duty in (self.everyone, self.shared):
            self.assertEqual(self.answer_of(duty, self.a.bank_ab)[:3], ("applies", REASON, self.a.officer.id))  # type: ignore[index]
        self.assertIsNone(self.row(self.payments, self.a.bank_ab))
        self.assertIsNone(self.row(self.single))
        self.assertEqual({duty: self.answer_of(duty, self.a.bank_ab) for duty in was}, was)
        self.assertEqual(self.events(decide_all.STARTED)[0].after, {"count": 2, "orgUnitId": self.bank, "instrument": None, "applicability": "applies", "selected": True})

    def test_a_selection_naming_an_obligation_not_offered_for_the_company_is_404_and_starts_nothing(self) -> None:
        theirs = library_build.obligation(
            library_build.instrument(key="da-b-own", regime="regime:securities", owner_tenant=self.b.tenant), key="da-b-own-duty", owner_tenant=self.b.tenant
        )
        cases: dict[str, dict[str, Any]] = {
            "a duty on insurers alone": {"obligationIds": [str(self.everyone.id), str(self.insurers.id)]},
            "a duty outside the working inventory": {"obligationIds": [str(self.outside.id)]},
            "another bank's own duty": {"obligationIds": [str(theirs.id)]},
            "an id nobody has": {"obligationIds": [str(self.everyone.id), str(uuid.uuid4())]},
            "a duty of another regulation than the one named": {"instrument": "da-lob", "obligationIds": [str(self.everyone.id)]},
        }
        for case, changes in cases.items():
            with self.subTest(case), mock.patch.object(tasks.decide_listed, "delay") as queued:
                response = self.start(changes)
                self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"), response.content)
                self.assertEqual(response.headers["Content-Type"], "application/problem+json")
                queued.assert_not_called()
        self.assertEqual(self.events(decide_all.STARTED), [])
        self.assertEqual(self.read(), IDLE)
        self.assertEqual(self.set_by_the_run(), [])

    def test_nothing_to_decide_is_a_finished_run_of_none_that_queues_nothing(self) -> None:
        cases: dict[str, dict[str, Any]] = {
            "a regulation that offers the company nothing": {"instrument": "da-none"},
            "a selection already answered": {"obligationIds": [str(self.answered.id)]},
        }
        for case, changes in cases.items():
            with self.subTest(case), mock.patch.object(tasks.decide_listed, "delay") as queued:
                cache.clear()
                response = self.start(changes)
                self.assertEqual(response.status_code, 202, response.content)
                queued.assert_not_called()
                state = self.read()
                self.assertEqual((state["status"], state["total"], state["set"], state["stopped"]), ("finished", 0, 0, None))
                self.assertEqual(response.json(), state)
        self.assertEqual([event.after["count"] for event in self.events(decide_all.STARTED)], [0, 0])

    def test_a_second_start_waits_for_a_running_run_unless_its_worker_went_quiet(self) -> None:
        _, first = self.start_held()
        refused = self.start()
        self.assertEqual((refused.status_code, refused.json()["code"]), (409, "decision_running"), refused.content)
        self.assertEqual(len(self.events(decide_all.STARTED)), 1)
        # A colleague's own run is their own: mine does not hold theirs back.
        with mock.patch.object(tasks.decide_listed, "delay"):
            self.assertEqual(self.start(who=self.colleague).status_code, 202)
        # Nothing heard from the worker for longer than the setting: it stopped, so a new start runs.
        key = decide_all._key(self.a.tenant.id, self.a.officer.id)
        held = cache.get(key)
        held["state"]["updatedAt"] = (timezone.now() - timedelta(seconds=settings.REGISTER_DECIDE_ALL_STALE_S + 1)).isoformat()
        cache.set(key, held)
        _, second = self.start_held({"applicability": "not_applicable", "reason": "Decided again"})
        # The replaced run's worker wakes up late: the state it finds is another run's, so it
        # decides nothing, least of all under that run's reason, leaves the new run's state as
        # it was and records that it stopped.
        self.work(first)
        self.assertEqual(self.set_by_the_run(), [])
        self.assertEqual(self.progress(), ("running", 4, 0, 0, 0, None))
        [stopped] = self.events(decide_all.STOPPED)
        self.assertEqual((stopped.actor_id, stopped.subject_id, stopped.after), (self.a.officer.id, self.a.bank_ab.id, {"stopped": "replaced", "left": 4}))
        self.work(second)
        self.assertEqual(self.progress(), ("finished", 4, 4, 0, 0, None))
        self.assertEqual({(event.after["applicability"], event.after["reason"]) for event in self.set_by_the_run()}, {("not_applicable", "Decided again")})


class WhoMayDecide(DecideAllCase):
    def test_another_banks_company_and_what_is_no_active_legal_entity_are_404_and_start_nothing(self) -> None:
        department = factories.org_unit(self.a.tenant, name="Group Finance")
        closed = factories.legal_entity(self.a.tenant, name="Example Wound Down AB", active=False)
        cases = {"another bank's company": self.b.bank_ab.id, "a department": department.id, "an inactive legal entity": closed.id, "an id nobody has": uuid.uuid4()}
        for case, entity_id in cases.items():
            with self.subTest(case), mock.patch.object(tasks.decide_listed, "delay") as queued:
                response = self.start({"orgUnitId": str(entity_id)})
                self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"), response.content)
                queued.assert_not_called()
        self.assertEqual(self.events(decide_all.STARTED), [])
        self.assertEqual(self.set_by_the_run(), [])

    def test_a_member_without_applicability_approve_is_403_naming_it_on_both_routes(self) -> None:
        headers = sign_in(self.a.owner, tenant=self.a.tenant)
        for response in (self.client.post(ROUTE, data=self.body(), content_type="application/json", **headers), self.client.get(ROUTE, **headers)):
            self.assertEqual(response.status_code, 403, response.content)
            self.assertEqual((response.json()["code"], response.json()["requiredPermission"]), ("permission_denied", perms.APPLICABILITY_APPROVE))
        self.assertEqual(self.events(decide_all.STARTED), [])

    def test_a_key_is_refused_whatever_its_scopes_and_no_credential_is_401(self) -> None:
        credentials: tuple[dict[str, Any], ...] = ({"HTTP_X_API_KEY": API_KEY_FOR_TESTS}, {})
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES, tenant_id=self.a.tenant.id)):
            for headers in credentials:
                self.assertEqual(self.client.post(ROUTE, data=self.body(), content_type="application/json", **headers).status_code, 401)
                self.assertEqual(self.client.get(ROUTE, **headers).status_code, 401)
        self.assertEqual(self.events(decide_all.STARTED), [])

    def test_a_body_the_schema_or_the_cap_refuses_is_422_and_starts_nothing(self) -> None:
        one, two = str(self.everyone.id), str(self.shared.id)
        cases: dict[str, dict[str, Any]] = {
            "no company": {"orgUnitId": None},
            "a company that is no id": {"orgUnitId": "example-bank"},
            "parking many rows as under assessment": {"applicability": "under_assessment"},
            "an answer nobody knows": {"applicability": "maybe"},
            "no reason": {"reason": ""},
            "a reason over the longest a row keeps": {"reason": "x" * 2001},
            "a reason holding a NUL": {"reason": "Certified\x00"},
            "an empty selection": {"obligationIds": []},
            "an obligation ticked twice": {"obligationIds": [one, two, one]},
            "a selection that is no id": {"obligationIds": ["first"]},
            "a regulation that is no stable key": {"instrument": "da lvm"},
            "a regulation key over the longest": {"instrument": "x" * 121},
            "a field the body does not have": {"tone": "positive"},
        }
        with mock.patch.object(tasks.decide_listed, "delay") as queued:
            for case, changes in cases.items():
                with self.subTest(case):
                    response = self.start(changes)
                    self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"), response.content)
                    self.assertNotIn(REASON, response.content.decode())
            # The selection's cap bounds one request body, read from the setting.
            with override_settings(REGISTER_DECIDE_ALL_SELECTED_MAX=1):
                over = self.start({"obligationIds": [one, two]})
                self.assertEqual((over.status_code, over.json()["code"]), (422, "validation_error"), over.content)
                self.assertEqual(self.start({"obligationIds": [one]}).status_code, 202)
            queued.assert_called_once()
        self.assertEqual(len(self.events(decide_all.STARTED)), 1)

    def test_reading_answers_the_callers_own_latest_run_in_this_bank_and_an_idle_one_otherwise(self) -> None:
        self.assertEqual(self.read(), IDLE)
        self.start()
        mine = self.read()
        self.assertEqual(set(mine), STATE_FIELDS)
        self.assertEqual((mine["status"], mine["total"], mine["set"]), ("finished", 4, 4))
        self.assertNotIn(REASON, json.dumps(mine))
        # Each person reads their own run, and a person in two banks reads each bank's apart.
        self.assertEqual(self.read(who=self.colleague), IDLE)
        factories.member(self.b.tenant, roles=("compliance_officer",), user_row=self.a.officer)
        self.assertEqual(self.read(tenant=self.b.tenant), IDLE)
        # A read: it stores nothing and writes no audit row.
        self.activate(self.a.tenant)
        before = AuditEvent.objects.filter(action__startswith="register.").count()
        self.assertEqual(self.read(), mine)
        self.activate(self.a.tenant)
        self.assertEqual(AuditEvent.objects.filter(action__startswith="register.").count(), before)


# ---------------------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------------------
class TheWorker(DecideAllCase):
    def test_each_target_is_set_through_the_door_with_its_own_event_naming_the_person_and_the_reason(self) -> None:
        self.assertEqual(self.start().status_code, 202)
        self.assertEqual(self.progress(), ("finished", 4, 4, 0, 0, None))
        for duty, entity in ((self.payments, self.a.bank_ab), (self.shared, self.a.bank_ab), (self.single, None), (self.everyone, self.a.bank_ab)):
            stored = self.answer_of(duty, entity)
            assert stored is not None
            self.assertEqual(stored[:3], ("applies", REASON, self.a.officer.id), duty.stable_key)
            self.assertIsNotNone(stored[3])
        events = self.set_by_the_run()
        self.assertEqual(sorted(event.after["obligationId"] for event in events), sorted(str(duty.id) for duty in self.targets))
        self.assertEqual({(event.actor_type, event.actor_id, event.actor_label) for event in events}, {("user", self.a.officer.id, "Sara Lind")})
        self.assertEqual({(event.before["applicability"], event.after["applicability"], event.after["reason"]) for event in events}, {("under_assessment", "applies", REASON)})
        self.assertEqual({event.step_up_assertion_id for event in events}, {None})
        # One row for the decision beside them, none for a stop, and nothing written as the system.
        self.assertEqual(len(self.events(decide_all.STARTED)), 1)
        self.assertEqual(self.events(decide_all.STOPPED), [])
        self.activate(self.a.tenant)
        written = AuditEvent.objects.filter(tenant_id=self.a.tenant.id, action__startswith="register.")
        self.assertEqual(set(written.values_list("actor_type", flat=True)), {"user"})
        self.assertEqual(set(written.values_list("tenant_id", flat=True)), {self.a.tenant.id})

    def test_what_a_person_answered_before_the_start_is_left_alone_whatever_the_answer(self) -> None:
        """A "does not apply", and a colleague's deliberate "under assessment" with its reason."""
        was = {duty: self.answer_of(duty, self.a.bank_ab) for duty in (self.answered, self.parked)}
        self.assertEqual(was[self.parked][:3], ("not_assessed", PARKED, self.colleague.id))  # type: ignore[index]
        self.start()
        self.assertEqual({duty: self.answer_of(duty, self.a.bank_ab) for duty in was}, was)
        self.assertNotIn(str(self.parked.id), {event.after["obligationId"] for event in self.set_by_the_run()})

    def test_a_row_that_exists_with_no_answer_is_still_a_target_and_keeps_what_it_held(self) -> None:
        """A detail recorded on a company's row before anybody answered leaves a row no
        person has decided."""
        noted = self.client.patch(
            f"{V1}/obligations/{self.everyone.id}/register/entities/{self.bank}",
            data={"process": "Order desk"},
            content_type="application/json",
            HTTP_IF_MATCH='"0"',
            **sign_in(self.a.officer, tenant=self.a.tenant),
        )
        self.assertEqual(noted.status_code, 200, noted.content)
        self.assertEqual(self.answer_of(self.everyone, self.a.bank_ab)[:3], ("not_assessed", "", None))  # type: ignore[index]
        self.start()
        self.assertEqual(self.progress(), ("finished", 4, 4, 0, 0, None))
        row = self.row(self.everyone, self.a.bank_ab)
        self.assertEqual((row.applicability, row.applicability_decided_by_id, row.process), ("applies", self.a.officer.id, "Order desk"))

    def test_a_colleagues_answer_between_the_start_and_the_run_survives_and_is_counted_as_skipped(self) -> None:
        _, args = self.start_held()
        self.put(self.colleague, self.everyone, {"orgUnitId": self.bank, "applicability": "not_applicable", "reason": "Orders are taken by the group"})
        theirs = self.answer_of(self.everyone, self.a.bank_ab)
        assert theirs is not None
        self.assertEqual(theirs[:3], ("does_not_apply", "Orders are taken by the group", self.colleague.id))
        self.work(args)
        self.assertEqual(self.progress(), ("finished", 4, 3, 1, 0, None))
        self.assertEqual(self.answer_of(self.everyone, self.a.bank_ab), theirs, "answer, reason, decider, time and version")
        self.assertEqual(sorted(event.after["obligationId"] for event in self.set_by_the_run() if event.actor_id == self.a.officer.id), sorted(str(duty.id) for duty in self.targets[:3]))

    def test_a_run_whose_every_target_was_answered_meanwhile_sets_nothing(self) -> None:
        _, args = self.start_held({"obligationIds": [str(self.everyone.id)]})
        self.put(self.colleague, self.everyone, {"orgUnitId": self.bank, "applicability": "applies", "reason": "Orders are taken here"})
        theirs = self.answer_of(self.everyone, self.a.bank_ab)
        self.work(args)
        self.assertEqual(self.progress(), ("finished", 1, 0, 1, 0, None))
        self.assertEqual(self.answer_of(self.everyone, self.a.bank_ab), theirs)
        self.assertEqual([event.actor_id for event in self.set_by_the_run()], [self.colleague.id])

    def test_a_duty_on_one_company_is_answered_as_a_whole_and_one_on_several_for_the_company_alone(self) -> None:
        self.start()
        whole = self.row(self.single)
        self.assertEqual((whole.applicability, whole.applicability_decided_by_id), ("applies", self.a.officer.id))
        self.assertIsNone(self.row(self.single, self.a.bank_ab))
        entry = self.row(self.shared)
        self.assertEqual((entry.applicability, entry.applicability_reason, entry.applicability_decided_by_id), ("not_assessed", "", None))
        self.assertEqual(self.row(self.shared, self.a.bank_ab).applicability, "applies")
        self.assertIsNone(self.row(self.shared, self.a.fonder), "the fund company keeps its own answer to give")
        by_duty = {event.after["obligationId"]: event.after["orgUnitId"] for event in self.set_by_the_run()}
        self.assertEqual((by_duty[str(self.single.id)], by_duty[str(self.shared.id)]), (None, self.bank))

    def test_applies_schedules_each_recurring_duty_as_a_single_answer_does_and_not_applicable_schedules_none(self) -> None:
        self.start()
        self.activate(self.a.tenant)
        [first] = DutyOccurrence.objects.filter(recurring_duty=self.duty)
        self.assertEqual((first.tenant_obligation.obligation_id, first.org_unit_id), (self.everyone.id, self.a.bank_ab.id))
        [scheduled] = self.events(DUTY_SCHEDULED)
        self.assertEqual((scheduled.actor_id, scheduled.subject_id), (self.a.officer.id, first.id))
        # The same occurrence a single confirmed answer writes, here for the fund company.
        self.put(self.a.officer, self.everyone, {"orgUnitId": str(self.a.fonder.id), "applicability": "applies", "reason": "Funds take orders too"})
        self.activate(self.a.tenant)
        single = DutyOccurrence.objects.get(recurring_duty=self.duty, org_unit=self.a.fonder)
        self.assertEqual((single.due_date, single.status), (first.due_date, first.status))
        cache.clear()
        self.start({"orgUnitId": str(self.a.liv.id), "applicability": "not_applicable", "reason": "An insurer takes no orders"})
        self.assertEqual(self.row(self.everyone, self.a.liv).applicability, "does_not_apply")
        self.activate(self.a.tenant)
        self.assertFalse(DutyOccurrence.objects.filter(recurring_duty=self.duty, org_unit=self.a.liv).exists())

    def test_more_targets_than_a_chunk_holds_are_all_set_a_chunk_at_a_time(self) -> None:
        library_build.obligation(self.law, key="da-lvm-8-more", ref_label="8 §")
        queued: list[tuple[Any, ...]] = []
        deliver = tasks.decide_listed.delay

        def keep(*args: Any) -> Any:
            queued.append(args)
            return deliver(*args)

        with override_settings(REGISTER_BULK_MAX=2), mock.patch.object(tasks.decide_listed, "delay", side_effect=keep):
            self.assertEqual(self.start().status_code, 202)
        # Each task decides one chunk and hands on what is left, with the same ids and never more.
        self.assertEqual([len(args[3]) for args in queued], [5, 3, 1])
        self.assertEqual(queued[1][3], queued[0][3][2:])
        self.assertEqual({(args[0], args[1], args[2], args[4], args[5]) for args in queued}, {(*queued[0][:3], *queued[0][4:])})
        self.assertEqual(self.progress(), ("finished", 5, 5, 0, 0, None))
        self.assertEqual(len(self.set_by_the_run()), 5)

    def test_a_chunk_delivered_twice_is_decided_once(self) -> None:
        with override_settings(REGISTER_BULK_MAX=2):
            _, first = self.start_held()
            with mock.patch.object(tasks.decide_listed, "delay") as queued:
                self.work(first)  # the first chunk; the second waits in `queued`
                self.assertEqual(self.progress(), ("running", 4, 2, 0, 0, None))
                self.work(first)  # delivered again: its chunk is done, so it decides and queues nothing
            queued.assert_called_once()
            self.assertEqual(self.progress(), ("running", 4, 2, 0, 0, None))
            self.work(queued.call_args.args)
            self.assertEqual(self.progress(), ("finished", 4, 4, 0, 0, None))
            # And once more after the run finished.
            self.work(queued.call_args.args)
        self.assertEqual(self.progress(), ("finished", 4, 4, 0, 0, None))
        self.assertEqual(len(self.set_by_the_run()), 4)

    def test_every_target_has_its_row_before_the_run_reads_who_answered_it(self) -> None:
        """A row that does not exist has no lock to wait on, so a colleague's first answer
        written at the same moment would read as unanswered and be overwritten. The run creates
        each missing row first, once, with its one creation event, and reads the answer under
        the row's lock."""
        _, args = self.start_held()
        read: list[Any] = []
        answered = company_view.answered

        def reads(row: Any) -> bool:
            read.append(row)
            return answered(row)

        with mock.patch.object(company_view, "answered", side_effect=reads):
            self.work(args)
        self.assertEqual(len(read), 4)
        self.assertNotIn(None, read)
        self.assertEqual(self.progress(), ("finished", 4, 4, 0, 0, None))
        created = [event.after["obligationId"] for event in self.events(ENTRY_CREATED)][2:]  # after the fixture's two
        self.assertEqual(sorted(created), sorted(str(duty.id) for duty in self.targets))

    def test_a_chunk_reads_and_keeps_the_runs_state_under_the_runs_lock_before_its_commit(self) -> None:
        """Two starts at once, a chunk delivered twice at once and a stale run's chunk beside a
        new start each meet on the run's lock: each reads the state only once it holds it, and
        writes it before it lets go."""
        happened: list[str] = []
        lock = decide_all._lock_run
        held = cache.get

        def take(*ids: Any) -> None:
            happened.append("lock")
            lock(*ids)

        def read(key: str, *rest: Any) -> Any:
            if key.startswith("register:decide-all:"):  # the session's own reads are not the run's
                happened.append("read")
            return held(key, *rest)

        with override_settings(REGISTER_BULK_MAX=2), mock.patch.object(decide_all, "_lock_run", side_effect=take), mock.patch.object(decide_all.cache, "get", side_effect=read):
            _, args = self.start_held()
            self.assertEqual(happened[:2], ["lock", "read"])
            happened.clear()
            with mock.patch.object(tasks.decide_listed, "delay"), self.captureOnCommitCallbacks(execute=False):
                tasks.decide_listed(*args)
                self.assertEqual(happened[:2], ["lock", "read"])
                # Not yet committed, and its progress is already kept.
                self.assertEqual(self.progress(), ("running", 4, 2, 0, 0, None))

    def test_a_chunk_whose_task_fails_at_its_commit_ends_its_run_as_failed(self) -> None:
        with override_settings(REGISTER_BULK_MAX=2):
            _, args = self.start_held()
            with mock.patch.object(tasks.decide_listed, "delay"):
                self.work(args)
        self.assertEqual(self.progress(), ("running", 4, 2, 0, 0, None))
        # Celery calls the task's failure hook with the task's arguments.
        tasks.decide_listed.on_failure(RuntimeError("the connection went away at the commit"), "task-id", args, {}, None)
        self.assertEqual(self.progress(), ("finished", 4, 2, 0, 0, "failed"))
        self.assertEqual(cache.get(decide_all._key(self.a.tenant.id, self.a.officer.id))["reason"], "")
        # A finished run, and another run's state, are left as they are.
        before = cache.get(decide_all._key(self.a.tenant.id, self.a.officer.id))
        tasks.decide_listed.on_failure(RuntimeError("again"), "task-id", args, {}, None)
        tasks.decide_listed.on_failure(RuntimeError("another run"), "task-id", (*args[:5], uuid.uuid4().hex), {}, None)
        self.assertEqual(cache.get(decide_all._key(self.a.tenant.id, self.a.officer.id)), before)

    def test_the_work_lands_in_the_runs_own_bank_and_another_bank_reads_none_of_it(self) -> None:
        self.start()
        self.activate(self.b.tenant)
        self.assertFalse(TenantObligation.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action__startswith="register.").exists())
        theirs = self.client.get(f"{V1}/applicability/companies", **sign_in(self.b.owner, tenant=self.b.tenant)).json()
        self.assertEqual({row["offered"] - row["toDecide"] for row in theirs}, {0})


class WhatStopsARun(DecideAllCase):
    def stopped(self) -> dict[str, Any]:
        [event] = self.events(decide_all.STOPPED)
        self.assertEqual((event.actor_type, event.actor_id, event.subject_type, event.subject_id), ("user", self.a.officer.id, "org_unit", self.a.bank_ab.id))
        after: dict[str, Any] = event.after
        return after

    def test_a_run_whose_person_may_no_longer_decide_stops_with_an_audit_row_and_sets_nothing(self) -> None:
        mine = {"membership__user": self.a.officer, "membership__tenant": self.a.tenant}
        reader = MembershipRole.objects.get(membership__user=self.a.owner, membership__tenant=self.a.tenant).role
        stops = (
            ("permission_revoked", lambda: MembershipRole.objects.filter(**mine).update(role=reader)),
            ("permission_revoked", lambda: MembershipRole.objects.filter(**mine).delete()),
            ("membership_ended", lambda: Membership.objects.filter(user=self.a.officer, tenant=self.a.tenant).update(deactivated_at=timezone.now())),
            ("membership_ended", lambda: User.objects.filter(pk=self.a.officer.pk).update(deactivated_at=timezone.now())),
        )
        for why, take_away in stops:
            with self.subTest(why), transaction.atomic():
                cache.clear()
                _, args = self.start_held()
                self.activate(self.a.tenant)
                take_away()
                self.work(args)
                self.assertEqual(self.progress(), ("finished", 4, 0, 0, 0, why))
                self.assertEqual(self.stopped(), {"stopped": why, "set": 0, "skipped": 0, "refused": 0, "left": 4})
                self.assertEqual(self.set_by_the_run(), [])
                transaction.set_rollback(True)  # the grant, the run and its rows: the next case starts clean

    def test_a_grant_taken_away_part_way_stops_the_run_at_the_next_chunk_and_what_was_set_stays_set(self) -> None:
        door = applicability._store

        def store_then_lose_the_grant(**call: Any) -> Any:
            stored = door(**call)
            MembershipRole.objects.filter(membership__user=self.a.officer, membership__tenant=self.a.tenant).delete()
            return stored

        with override_settings(REGISTER_BULK_MAX=2):
            _, args = self.start_held()
            with mock.patch.object(applicability, "_store", side_effect=store_then_lose_the_grant):
                self.work(args)
        self.assertEqual(self.progress(), ("finished", 4, 2, 0, 0, "permission_revoked"))
        self.assertEqual(self.stopped(), {"stopped": "permission_revoked", "set": 2, "skipped": 0, "refused": 0, "left": 2})
        self.assertEqual(len(self.set_by_the_run()), 2)
        self.assertIsNone(self.row(self.single))
        self.assertIsNone(self.row(self.everyone, self.a.bank_ab))

    def test_a_company_no_longer_an_active_legal_entity_stops_the_run_once_with_an_audit_row(self) -> None:
        _, args = self.start_held()
        self.activate(self.a.tenant)
        OrgUnit.objects.filter(pk=self.a.bank_ab.pk).update(active=False)
        self.work(args)
        self.assertEqual(self.progress(), ("finished", 4, 0, 0, 0, "company_gone"))
        self.assertEqual(self.state()["refusals"], [])
        self.assertEqual(self.stopped(), {"stopped": "company_gone", "set": 0, "skipped": 0, "refused": 0, "left": 4})
        self.assertEqual(self.set_by_the_run(), [])

    def test_a_run_whose_reason_is_gone_when_the_worker_starts_sets_nothing_and_says_why(self) -> None:
        _, args = self.start_held()
        cache.delete(decide_all._key(self.a.tenant.id, self.a.officer.id))
        self.work(args)
        state = self.read()
        self.assertEqual(
            {**state, "updatedAt": None},
            {**IDLE, "status": "finished", "total": 4, "stopped": "reason_expired", "orgUnitId": self.bank, "applicability": "applies"},
        )
        self.assertEqual(self.stopped(), {"stopped": "reason_expired", "set": 0, "skipped": 0, "refused": 0, "left": 4})
        self.assertEqual(self.set_by_the_run(), [])

    def test_an_obligation_no_longer_offered_is_refused_with_its_reason_and_the_rest_are_set(self) -> None:
        """Two ways out between the start and the worker's turn. An approved scope request
        takes payments out of the company's own scope, which the door would refuse as well.
        The bank's regulatory scope moves off custody, which the door alone would answer: it
        checks the span and never the working inventory."""
        custody = library_build.obligation(self.law, key="da-lvm-9-custody", ref_label="9 §", titles={"en": "Reconcile custody accounts"}, terms=("service_type:custody",))
        state, args = self.start_held()
        self.assertEqual(state["total"], 5)
        exclude(self.a.tenant, self.a.bank_ab, "regime:payments")
        self.activate(self.a.tenant)
        FootprintTerm.objects.filter(tenant=self.a.tenant).delete()
        set_footprint(self.a.tenant, ("service_type:advice",))
        self.work(args)
        self.assertEqual(self.progress(), ("finished", 5, 3, 0, 2, None))
        refusals = self.state()["refusals"]
        self.assertEqual(
            [(refusal["obligationId"], refusal["title"], refusal["code"]) for refusal in refusals],
            [(str(self.payments.id), "Safeguard client funds", "not_found"), (str(custody.id), "Reconcile custody accounts", "not_found")],
        )
        self.assertTrue(all(refusal["detail"] for refusal in refusals))
        for duty in (self.payments, custody):
            self.assertIsNone(self.row(duty), "a refused row leaves nothing behind, not even an entry")
        self.assertEqual(len(self.set_by_the_run()), 3)

    def test_a_target_that_can_no_longer_be_read_is_refused_without_a_title(self) -> None:
        _, args = self.start_held()
        gone = str(uuid.uuid4())
        self.work((*args[:3], [gone, *args[3][1:]], *args[4:]))
        self.assertEqual(self.progress(), ("finished", 4, 3, 0, 1, None))
        [refusal] = self.state()["refusals"]
        self.assertEqual((refusal["obligationId"], refusal["title"], refusal["code"]), (gone, "", "not_found"))
        self.assertIsNone(self.row(self.payments, self.a.bank_ab), "the target the task did not name is left as it was")

    def test_a_row_the_door_refuses_does_not_cost_the_others_of_its_chunk(self) -> None:
        door = applicability._store

        def refuse_one(**call: Any) -> Any:
            if any(row.obligation_id == self.single.id for row in call["answers"]):
                raise ValidationError("That obligation is not here.", code="not_found")
            return door(**call)

        _, args = self.start_held()
        with mock.patch.object(applicability, "_store", side_effect=refuse_one):
            self.work(args)
        self.assertEqual(self.progress(), ("finished", 4, 3, 0, 1, None))
        self.assertEqual(
            self.state()["refusals"],
            [{"obligationId": str(self.single.id), "title": "Report large exposures", "code": "not_found", "detail": "That obligation is not here."}],
        )
        self.assertIsNone(self.row(self.single))
        self.assertEqual(sorted(event.after["obligationId"] for event in self.set_by_the_run()), sorted(str(duty.id) for duty in (self.payments, self.shared, self.everyone)))

    def test_only_the_first_refusals_are_kept_with_their_reasons_and_the_count_covers_them_all(self) -> None:
        def refuse_all(**call: Any) -> Any:
            raise ValidationError("That obligation is not here.", code="not_found")

        _, args = self.start_held()
        with mock.patch.object(decide_all, "REFUSALS_KEPT", 3), mock.patch.object(applicability, "_store", side_effect=refuse_all):
            self.work(args)
        self.assertEqual(self.progress(), ("finished", 4, 0, 0, 4, None))
        self.assertEqual([refusal["obligationId"] for refusal in self.state()["refusals"]], [str(duty.id) for duty in self.targets[:3]])

    def test_a_run_that_fails_ends_as_finished_and_says_so_with_what_its_earlier_chunks_set(self) -> None:
        door = applicability._store
        calls: list[int] = []

        def fail_the_second(**call: Any) -> Any:
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("the database went away")
            return door(**call)

        with override_settings(REGISTER_BULK_MAX=2):
            _, args = self.start_held()
            with mock.patch.object(applicability, "_store", side_effect=fail_the_second), self.assertRaises(RuntimeError):
                self.work(args)
        self.assertEqual(self.progress(), ("finished", 4, 2, 0, 0, "failed"))
        self.assertEqual(len(self.set_by_the_run()), 2)


class TheReasonStaysInTheBank(DecideAllCase):
    def test_the_task_is_a_registered_tenant_task_that_takes_ids_the_answer_and_the_run_alone(self) -> None:
        self.assertIn("apps.register.tasks.decide_listed", celery_app.tasks)
        self.assertTrue(is_tenant_task(tasks.decide_listed.run))
        self.assertEqual(
            list(inspect.signature(tasks.decide_listed.run).parameters),
            ["tenant_id", "user_id", "org_unit_id", "obligation_ids", "applicability", "run_id"],
        )

    def test_the_reason_is_kept_beside_the_state_only_while_there_is_something_left_to_set(self) -> None:
        key = decide_all._key(self.a.tenant.id, self.a.officer.id)
        _, args = self.start_held()
        self.assertEqual(cache.get(key)["reason"], REASON)
        self.assertNotIn(REASON, json.dumps(cache.get(key)["state"]))
        self.work(args)
        self.assertEqual((cache.get(key)["state"]["status"], cache.get(key)["reason"]), ("finished", ""))
        # A run with nothing to set never keeps one.
        cache.clear()
        self.start({"instrument": "da-none"})
        self.assertEqual((cache.get(key)["state"]["status"], cache.get(key)["reason"]), ("finished", ""))

    def test_the_reason_rides_in_no_task_argument_and_reaches_no_log_record(self) -> None:
        """A run of two chunks whose second fails, a refused start and a read. Celery's own line
        about a task prints the task's arguments, as a broker's and an error tracker's do: the
        line about the first chunk is captured here, with the ids and without the reason."""
        queued: list[tuple[Any, ...]] = []
        deliver = tasks.decide_listed.delay
        door = applicability._store

        def keep(*args: Any, **named: Any) -> Any:
            queued.append((*args, *named.items()))
            return deliver(*args, **named)

        def fail_the_second(**call: Any) -> Any:
            if len(queued) == 2:
                raise RuntimeError("the database went away")
            return door(**call)

        captured = _Captured()
        configured = cast("dict[str, Any]", settings.LOGGING["loggers"])
        loggers = [logging.getLogger(name) for name in ("", *configured, "celery", "celery.app.trace", "celery.task")]
        levels = [logger.level for logger in loggers]
        for logger in loggers:
            logger.addHandler(captured)
            logger.setLevel(logging.DEBUG)
        try:
            with (
                override_settings(REGISTER_BULK_MAX=2),
                mock.patch.object(tasks.decide_listed, "delay", side_effect=keep),
                mock.patch.object(applicability, "_store", side_effect=fail_the_second),
                self.assertRaises(RuntimeError),
            ):
                self.start()
            # A refused start is logged as a 4xx, and a read is a request like any other.
            self.start({"obligationIds": [str(self.insurers.id)]})
            self.read()
        finally:
            for logger, level in zip(loggers, levels, strict=True):
                logger.removeHandler(captured)
                logger.setLevel(level)
        self.assertEqual(len(queued), 2)
        self.assertEqual(self.progress(), ("finished", 4, 2, 0, 0, "failed"))
        self.assertNotIn(REASON, str(queued))
        # The capture saw Celery's line with the task's arguments, and the reason is in no line.
        self.assertTrue(
            any("decide_listed" in line and all(obligation_id in line for obligation_id in queued[0][3]) for line in captured.lines),
            "the line that prints a task's arguments was not captured",
        )
        self.assertEqual([line for line in captured.lines if REASON in line], [])


# ---------------------------------------------------------------------------------------
# The same number of queries however many targets
# ---------------------------------------------------------------------------------------
class TheSameQueriesHoweverManyTargets(DecideAllCase):
    def more(self, count: int, prefix: str) -> list[Obligation]:
        return [library_build.obligation(self.law, key=f"da-{prefix}-{number:02d}", ref_label=f"{prefix} {number} §") for number in range(count)]

    def test_start_costs_the_same_for_four_targets_and_for_twelve(self) -> None:
        def cost() -> tuple[int, int]:
            headers = sign_in(self.a.officer, tenant=self.a.tenant)
            # Never committed here, so nothing is queued; the state kept is cleared so the next
            # call starts again.
            cache.clear()
            with CaptureQueriesContext(connection) as queries:
                response = self.client.post(ROUTE, data=self.body(), content_type="application/json", **headers)
            self.assertEqual(response.status_code, 202, response.content)
            return response.json()["total"], len(queries)

        few = cost()
        self.more(8, "start")
        many = cost()
        self.assertEqual((few[0], many[0]), (4, 12))
        self.assertEqual(few[1], many[1])

    def test_one_chunk_costs_the_same_for_four_targets_and_for_eight(self) -> None:
        """Fresh duties with no recurring duty, so each chunk creates its entries and rows and
        schedules nothing: what the door spends per recurring duty is the door's own."""
        fresh = self.more(12, "chunk")

        def cost(duties: list[Obligation]) -> int:
            cache.clear()
            _, args = self.start_held({"obligationIds": [str(duty.id) for duty in duties]})
            with CaptureQueriesContext(connection) as queries:
                self.work(args)
            self.assertEqual(self.progress(), ("finished", len(duties), len(duties), 0, 0, None))
            return len(queries)

        self.assertEqual(cost(fresh[:4]), cost(fresh[4:]))

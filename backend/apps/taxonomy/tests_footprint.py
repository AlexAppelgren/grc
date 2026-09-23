"""One decision per request and one waiting request per organisation, under a real race
(FP-02, FP-S6).

Each test runs two sessions at once, each on its own cw_app connection (no ownership, no
BYPASSRLS, row-level security forced) in its own thread and transaction, the way two
requests reach production. The first session acts and holds its transaction open until
PostgreSQL reports the second one waiting on it, then commits. That is the interleaving in
which a status check on an unlocked row lets both through: the second session read
"pending" before the first committed.

Proven to fail 2026-09-19 without the row lock and the partial unique constraint: in both
decision races both decisions landed, and the second request never waited on the first, so
two requests would have waited at once.

The third class pins the other thing only the app role can prove: a scope change's preview
counts what the organisation may see and nothing else (INV-07, AC-FP1). The last pins what a
person reads when a request is refused or logged: "regulatory scope", the screen's name.
"""

from __future__ import annotations

import time
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase

from apps.identity.models import User
from apps.library import testing as build
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.tests_reading import as_app_role
from apps.shared import factories, tenancy, testing
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent
from apps.taxonomy import footprint_logic, terms_logic
from apps.taxonomy.models import ApprovalStatus, FootprintChangeRequest, FootprintHistory
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

WAIT_SECONDS = 10
LANDED = "landed"
TERM_EVENTS = ("footprint.term_added", "footprint.term_removed")
DECISION_EVENTS = ("footprint.change_approved", "footprint.change_rejected", "footprint.change_withdrawn")


def _actor(user: Any) -> Actor:
    return Actor(kind=ActorType.USER, id=user.id, label=user.name)


def _seed_library() -> None:
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()


def _session(tenant_id: uuid.UUID, work: Callable[[], object]) -> str:
    """Run `work` in one transaction on a fresh cw_app connection of this thread's own.
    Answers "landed" when it committed, or the refusal's code."""
    connections[DEFAULT_DB_ALIAS] = connections.create_connection("app")
    try:
        with transaction.atomic():
            tenancy.activate(tenant_id)
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                assert cursor.fetchone()[0] == connections.settings["app"]["USER"], "a racing session must be cw_app"
            work()
        return LANDED
    except ValidationError as refusal:
        return str(refusal.code)
    finally:
        connections[DEFAULT_DB_ALIAS].close()


def _backend_pid() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        return int(cursor.fetchone()[0])


def _hold_until_waiting_on_me(other_pid: list[int]) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if other_pid:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))", [other_pid[0]])
                if cursor.fetchone()[0]:
                    return
        time.sleep(0.01)
    raise AssertionError("the second session never waited on the first")


class FootprintRaces(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        _seed_library()
        self.tenant = factories.tenant(slug="race")
        self.officer = factories.member(self.tenant, roles=("compliance_officer",)).user
        self.approver = factories.member(self.tenant, roles=("approver",)).user
        self.advice = terms_logic.term_by_ref("service_type", "advice")
        self.retail = terms_logic.term_by_ref("client_category", "retail")
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            footprint_logic.seed_terms(tenant=self.tenant, actor=Actor.system("test"), terms=[self.advice])

    # --- helpers --------------------------------------------------------------------------
    def _request(self) -> FootprintChangeRequest:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            return self._create()

    def _create(self) -> FootprintChangeRequest:
        return footprint_logic.create_request(
            tenant=self.tenant, requester=self.officer, actor=_actor(self.officer), adds=[self.retail], removes=[self.advice]
        )

    def _load(self, request_id: uuid.UUID) -> FootprintChangeRequest:
        # What the route does: an unlocked read by id, then the decision.
        return FootprintChangeRequest.objects.select_related("requested_by", "decided_by").get(pk=request_id)

    def _approve(self, request_id: uuid.UUID) -> Callable[[], object]:
        return lambda: footprint_logic.approve(
            tenant=self.tenant,
            request=self._load(request_id),
            decider=self.approver,
            actor=_actor(self.approver),
            note="",
            step_up_assertion_id=uuid.uuid4(),
            expected_version=1,
        )

    def _withdraw(self, request_id: uuid.UUID) -> Callable[[], object]:
        return lambda: footprint_logic.withdraw(
            tenant=self.tenant,
            request=self._load(request_id),
            requester=self.officer,
            actor=_actor(self.officer),
            expected_version=1,
        )

    def _race(self, first: Callable[[], object], second: Callable[[], object]) -> tuple[str, str]:
        """`first` acts and keeps its transaction open until `second` waits on it."""
        acted = threading.Event()
        second_pid: list[int] = []

        def lead() -> None:
            first()
            acted.set()
            _hold_until_waiting_on_me(second_pid)

        def follow() -> None:
            second_pid.append(_backend_pid())
            if not acted.wait(WAIT_SECONDS):
                raise AssertionError("the first session never acted")
            second()

        with ThreadPoolExecutor(max_workers=2) as pool:
            leading = pool.submit(_session, self.tenant.id, lead)
            following = pool.submit(_session, self.tenant.id, follow)
            return leading.result(), following.result()

    def _assert_one_approval(self, request_id: uuid.UUID) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            request = FootprintChangeRequest.objects.get(pk=request_id)
            self.assertEqual((request.status, request.version), (ApprovalStatus.APPROVED.value, 2))
            history = FootprintHistory.objects.filter(tenant=self.tenant, request=request)
            self.assertEqual(sorted((h.action, h.term.key) for h in history), [("added", "retail"), ("removed", "advice")])
            events = list(AuditEvent.objects.filter(tenant=self.tenant, action__in=TERM_EVENTS).exclude(actor_type=ActorType.SYSTEM.value))
            self.assertEqual(sorted(e.action for e in events), sorted(TERM_EVENTS), "one audit event per term")
            self.assertEqual({(e.after or e.before)["request"] for e in events}, {str(request_id)})
            decisions = AuditEvent.objects.filter(tenant=self.tenant, subject_id=request_id, action__in=DECISION_EVENTS)
            self.assertEqual([e.action for e in decisions], ["footprint.change_approved"])

    # --- the races ------------------------------------------------------------------------
    def test_an_approval_and_a_withdrawal_at_once_land_one_decision(self) -> None:
        request = self._request()
        outcomes = self._race(self._approve(request.id), self._withdraw(request.id))
        self.assertEqual(outcomes, (LANDED, "invalid_transition"))
        self._assert_one_approval(request.id)

    def test_two_approvals_at_once_land_one(self) -> None:
        request = self._request()
        outcomes = self._race(self._approve(request.id), self._approve(request.id))
        self.assertEqual(outcomes, (LANDED, "invalid_transition"))
        self._assert_one_approval(request.id)

    def test_two_requests_at_once_leave_one_waiting(self) -> None:
        outcomes = self._race(self._create, self._create)
        self.assertEqual(outcomes, (LANDED, "request_pending"))
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            self.assertEqual(FootprintChangeRequest.objects.filter(tenant=self.tenant, status=ApprovalStatus.PENDING.value).count(), 1)
            self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant, action="footprint.change_requested").count(), 1)


class CreateRequestRefusals(TestCase):
    def test_another_integrity_error_is_not_reported_as_a_waiting_request(self) -> None:
        """Only footprint_change_request_one_pending means "a change already waits". Any other
        refusal on the insert is a fault and surfaces as one, never as a 409 that sends the
        person off to look for a request that does not exist."""
        _seed_library()
        tenant = factories.tenant(slug="refusal")
        retail = terms_logic.term_by_ref("client_category", "retail")
        nobody = User(email="nobody@test.example", name="Nobody")  # never saved: no user row
        tenancy.activate(tenant.id)
        with connection.cursor() as cursor:
            # Foreign keys are deferred to commit; checking them now makes the insert refuse.
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with self.assertRaises(IntegrityError) as caught:
            footprint_logic.create_request(tenant=tenant, requester=nobody, actor=Actor.system("test"), adds=[retail], removes=[])
        self.assertIn("requested_by", caught.exception.__cause__.diag.constraint_name)  # type: ignore[union-attr]


class PreviewIsolation(TransactionTestCase):
    """A scope change's preview counts only what the organisation may see (INV-07, AC-FP1):
    counted as cw_app under forced row-level security, another tenant's private obligation
    never enters it."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        _seed_library()
        self.advice = terms_logic.term_by_ref("service_type", "advice")
        custody = terms_logic.term_by_ref("service_type", "custody")
        self.tenant_a = factories.tenant(slug="preview-a")
        self.tenant_b = factories.tenant(slug="preview-b")
        with transaction.atomic():
            build.obligation(build.instrument(key="lvm", regime="regime:securities"), key="obl-shared-advice", terms=("service_type:advice",))
        with transaction.atomic():
            tenancy.activate(self.tenant_b.id)
            private = build.instrument(key="bank-b-policy", regime="regime:securities", owner_tenant=self.tenant_b)
            build.obligation(private, key="obl-b-private", terms=("service_type:advice",), owner_tenant=self.tenant_b)
        for tenant in (self.tenant_a, self.tenant_b):
            with transaction.atomic():
                tenancy.activate(tenant.id)
                footprint_logic.seed_terms(tenant=tenant, actor=Actor.system("test"), terms=[self.advice, custody])

    def _hidden_by_removing_advice(self, tenant_id: uuid.UUID) -> int:
        """What removing Advice would hide, counted on the app role's own connection."""
        with as_app_role(), transaction.atomic():
            tenancy.activate(tenant_id)
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                assert cursor.fetchone()[0] == connections.settings["app"]["USER"], "the count must read as cw_app"
            return footprint_logic.preview_of(tenant_id, [], [self.advice]).obligations.hidden

    def test_another_tenants_private_obligation_never_enters_the_counts(self) -> None:
        self.assertEqual(self._hidden_by_removing_advice(self.tenant_a.id), 1, "the shared obligation only")
        # The owner counts its own beside the shared one, so the proof above is not vacuous.
        self.assertEqual(self._hidden_by_removing_advice(self.tenant_b.id), 2)


class RefusalsSayRegulatoryScope(TestCase):
    """What a person reads names the section as the screen does: "regulatory scope", never
    "footprint" (PRD glossary; app.md, the note under the acceptance criteria). The codes,
    the audit actions and the subject types are keys a client branches on, and they keep
    the word."""

    def setUp(self) -> None:
        _seed_library()
        self.tenant = factories.tenant(slug="copy")
        self.officer = factories.member(self.tenant, roles=("compliance_officer",)).user
        self.approver = factories.member(self.tenant, roles=("approver",)).user
        self.advice = terms_logic.term_by_ref("service_type", "advice")
        self.retail = terms_logic.term_by_ref("client_category", "retail")
        tenancy.activate(self.tenant.id)
        footprint_logic.seed_terms(tenant=self.tenant, actor=Actor.system("test"), terms=[self.advice])

    def _create(self) -> FootprintChangeRequest:
        return footprint_logic.create_request(
            tenant=self.tenant, requester=self.officer, actor=_actor(self.officer), adds=[self.retail], removes=[self.advice]
        )

    def _refusal(self, act: Callable[[], object]) -> tuple[str, str]:
        with self.assertRaises(ValidationError) as caught:
            act()
        return str(caught.exception.code), caught.exception.messages[0]

    def assert_reads_regulatory_scope(self, text: str) -> None:
        self.assertIn("regulatory scope", text.lower())
        self.assertNotIn("footprint", text.lower())

    def test_every_refusal_and_audit_summary_says_regulatory_scope(self) -> None:
        waiting = self._create()
        refusals = {
            "request_pending": self._refusal(self._create),
            "approved_by_requester": self._refusal(
                lambda: footprint_logic.approve(
                    tenant=self.tenant, request=waiting, decider=self.officer, actor=_actor(self.officer), note="", step_up_assertion_id=uuid.uuid4()
                )
            ),
            "rejected_by_requester": self._refusal(
                lambda: footprint_logic.reject(tenant=self.tenant, request=waiting, decider=self.officer, actor=_actor(self.officer), note="")
            ),
        }
        footprint_logic.withdraw(tenant=self.tenant, request=waiting, requester=self.officer, actor=_actor(self.officer))
        refusals["decided_twice"] = self._refusal(
            lambda: footprint_logic.withdraw(tenant=self.tenant, request=waiting, requester=self.officer, actor=_actor(self.officer))
        )
        self.assertEqual(
            {name: code for name, (code, _) in refusals.items()},
            {
                "request_pending": "request_pending",
                "approved_by_requester": "four_eyes_violation",
                "rejected_by_requester": "four_eyes_violation",
                "decided_twice": "invalid_transition",
            },
        )
        for name, (_, text) in refusals.items():
            with self.subTest(refusal=name):
                self.assert_reads_regulatory_scope(text)
        # An approval switches one term on and one off, so every summary the log can hold is here.
        footprint_logic.approve(
            tenant=self.tenant, request=self._create(), decider=self.approver, actor=_actor(self.approver), note="", step_up_assertion_id=uuid.uuid4()
        )
        events = AuditEvent.objects.filter(tenant=self.tenant, action__startswith="footprint.")
        self.assertEqual(
            {event.action for event in events},
            {"footprint.term_added", "footprint.term_removed", "footprint.change_requested", "footprint.change_withdrawn", "footprint.change_approved"},
        )
        for event in events:
            with self.subTest(action=event.action):
                self.assert_reads_regulatory_scope(event.summary)

    def test_a_request_that_is_not_here_says_regulatory_scope(self) -> None:
        response = self.client.post(
            f"/api/v1/tenant/footprint/requests/{uuid.uuid4()}/withdraw", content_type="application/json", **testing.sign_in(self.officer, tenant=self.tenant)
        )
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        self.assert_reads_regulatory_scope(response.json()["detail"])

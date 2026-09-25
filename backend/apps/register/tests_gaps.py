"""Gaps and risk acceptance (REG-03) outside the scenarios: recording a gap through
`ensure_register_entry()`, the refusals of what a write names, `If-Match` and the status
moves, the gaps list with its filters, order, pages and pinned query count, and risk
acceptance behind four eyes: the requester refused before any write, the database's own
check behind it, the step-up assertion on the audit row and two approvals at once landing
one. Tenant B's 404 on the id routes is `apps/shared/tests_tenant_isolation.py`'s, through
`TENANT_SCOPED_ROUTES`; the one route that guard cannot reach is proved here.

Written before `gaps.py` held any logic: every test failed on the 501 `not_built` stubs.

Operations exercised: listObligationGaps, createGap, listRegisterGaps, updateGap,
requestRiskAcceptance, approveRiskAcceptance, reopenGap.
"""

from __future__ import annotations

import datetime
import sys
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, IntegrityError, connection, connections, transaction
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.identity.models import StepUpAssertion, TenantRole
from apps.library import testing as library_testing
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.register import gaps
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, Gap, TenantObligation, TenantObligationScope
from apps.register.schemas import RegisterGapBody, RegisterGapQuery, RegisterRiskAcceptanceBody
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import LANDED, RACE_WAIT_SECONDS, ScenarioTestCase, backend_pid, hold_until_waiting_on_me, sign_in
from apps.taxonomy.models import ComplianceStatus, GapSource, GapStatus, RiskAcceptanceReason, RiskRating, Team
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.tenants.models import OrgUnit, OrgUnitKind

V1 = "/api/v1"
GAPS = f"{V1}/gaps"
# One page of gaps, however many there are: the gaps, then the labels of their severity,
# source, status, owning team and acceptance reason, then the total.
GAP_PAGE_QUERIES = 7
# Words a person typed, which no audit row may carry (R2_CROSS_CUTTING (m)).
TITLE = "Evidence of reconciliation is manual"
PLAN = "Automate the daily reconciliation report."
NOTE = "The weekly custody review covers the risk until 2027."


def seed_library() -> None:
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()


class GapWorld:
    """One bank with a legal entity, two compliance officers, an owner, a reader, and two
    library obligations it can record gaps on. Shared by these tests and REG-S5 and REG-S6."""

    def __init__(self, slug: str) -> None:
        act = library_testing.instrument(key=f"{slug}-act", regime="regime:securities")
        self.obligation = library_testing.obligation(act, key=f"{slug}-duty")
        self.other_obligation = library_testing.obligation(act, key=f"{slug}-other-duty", ref_label="2 §")
        self.tenant = factories.tenant(slug=slug)
        self.officer = factories.member_user(self.tenant, roles=("compliance_officer",))
        self.second_officer = factories.member_user(self.tenant, roles=("compliance_officer",))
        self.owner = factories.member_user(self.tenant, roles=("owner",))
        self.reader = factories.member_user(self.tenant, roles=("reader",))
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            self.entity = OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name="Example Bank AB")

    def url(self, obligation: Any = None) -> str:
        return f"{V1}/obligations/{(obligation or self.obligation).id}/gaps"

    def entry(self, obligation: Any = None) -> TenantObligation:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            return ensure_register_entry(
                tenant_id=self.tenant.id, obligation_id=(obligation or self.obligation).id, actor=Actor.system("test")
            )

    def set_entry(self, obligation: Any = None, **fields: Any) -> None:
        entry = self.entry(obligation)
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            TenantObligation.objects.filter(pk=entry.pk).update(**fields)

    def status(self, key: str) -> ComplianceStatus:
        tenancy.activate(self.tenant.id)
        return ComplianceStatus.objects.get(key=key)


def gap_body(**overrides: Any) -> dict[str, Any]:
    return {
        "title": TITLE,
        "severity": "high",
        "source": "assessment",
        "targetDate": (timezone.localdate() + datetime.timedelta(days=90)).isoformat(),
        "remediation": PLAN,
        **overrides,
    }


class GapTestCase(ScenarioTestCase):
    world: GapWorld

    @classmethod
    def setUpTestData(cls) -> None:
        seed_library()
        cls.world = GapWorld("gaps")

    def as_(self, user: Any, *, step_up: bool = False) -> dict[str, Any]:
        return sign_in(user, tenant=self.world.tenant, step_up=step_up)

    def record_gap(self, headers: dict[str, Any] | None = None, obligation: Any = None, **overrides: Any) -> Any:
        return self.client.post(
            self.world.url(obligation),
            data=gap_body(**overrides),
            content_type="application/json",
            **(headers or self.as_(self.world.officer)),
        )

    def gap(self, **overrides: Any) -> dict[str, Any]:
        response = self.record_gap(**overrides)
        self.assertEqual(response.status_code, 201, response.content)
        return dict(response.json())

    def patch(self, gap: dict[str, Any], body: dict[str, Any], headers: dict[str, Any] | None = None, version: Any = None) -> Any:
        return self.client.patch(
            f"{GAPS}/{gap['id']}",
            data=body,
            content_type="application/json",
            HTTP_IF_MATCH=str(gap["version"] if version is None else version),
            **(headers or self.as_(self.world.officer)),
        )

    def events(self, action: str, subject_id: Any = None) -> list[AuditEvent]:
        self.activate(self.world.tenant)
        rows = AuditEvent.objects.filter(tenant=self.world.tenant, action=action)
        if subject_id is not None:
            rows = rows.filter(subject_id=subject_id)
        return list(rows.order_by("created", "id"))

    def stored(self, gap: dict[str, Any]) -> Gap:
        self.activate(self.world.tenant)
        return Gap.objects.get(pk=gap["id"])

    def assert_problem(self, response: Any, status: int, code: str) -> dict[str, Any]:
        self.assertEqual((response.status_code, response.json().get("code")), (status, code), response.content)
        return dict(response.json())

    def assert_typed_text_absent(self, event: AuditEvent) -> None:
        dumped = f"{event.before} {event.after}"
        for text in (TITLE, PLAN, NOTE):
            self.assertNotIn(text, dumped)


class RecordingAGap(GapTestCase):
    def test_a_gap_is_recorded_open_with_its_rows_and_the_entry_created_with_it(self) -> None:
        response = self.record_gap()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], {"key": "open", "kind": "open", "label": "Open"})
        self.assertEqual((body["severity"]["key"], body["severity"]["label"]), ("high", "High"))
        self.assertEqual(body["source"], {"key": "assessment", "kind": None, "label": "Assessment"})
        self.assertEqual(body["identifiedBy"], {"id": str(self.world.officer.id), "name": self.world.officer.name})
        self.assertEqual((body["obligationId"], body["orgUnitId"], body["unitId"]), (str(self.world.obligation.id), None, None))
        self.assertEqual((body["title"], body["remediation"], body["riskAcceptance"], body["version"]), (TITLE, PLAN, None, 1))
        self.activate(self.world.tenant)
        entry = TenantObligation.objects.get(obligation=self.world.obligation)
        self.assertEqual(self.stored(body).tenant_obligation_id, entry.id)
        self.assertEqual(len(self.events("register.entry_created", entry.id)), 1)
        [event] = self.events(gaps.GAP_RECORDED, body["id"])
        self.assertEqual((event.actor_type, event.actor_id), (ActorType.USER.value, self.world.officer.id))
        self.assertEqual(event.after["severity"], "high")
        self.assertEqual(event.after["obligationId"], str(self.world.obligation.id))
        self.assert_typed_text_absent(event)

    def test_a_gap_on_a_legal_entity_and_one_owned_by_a_team(self) -> None:
        body = self.gap(orgUnitId=str(self.world.entity.id), ownerTeam="compliance")
        self.assertEqual(body["orgUnitId"], str(self.world.entity.id))
        self.assertEqual((body["owner"], body["ownerTeam"]["key"]), (None, "compliance"))
        owned = self.gap(ownerId=str(self.world.owner.id))
        self.assertEqual((owned["owner"]["id"], owned["ownerTeam"]), (str(self.world.owner.id), None))

    def test_gaps_edit_and_register_read_alone_record_and_amend_a_gap(self) -> None:
        self.activate(self.world.tenant)
        TenantRole.objects.create(tenant=self.world.tenant, key="gap-keeper", permissions=[perms.GAPS_EDIT, perms.REGISTER_READ])
        keeper = factories.member_user(self.world.tenant, roles=("gap-keeper",))
        headers = self.as_(keeper)
        response = self.record_gap(headers)
        self.assertEqual(response.status_code, 201, response.content)
        amended = self.patch(response.json(), {"status": "remediating"}, headers)
        self.assertEqual(amended.status_code, 200, amended.content)
        self.assertEqual(self.client.get(GAPS, **headers).status_code, 200)

    def test_an_obligation_that_does_not_apply_has_no_gap(self) -> None:
        self.world.set_entry(applicability=Applicability.DOES_NOT_APPLY.value, applicability_reason="No client money")
        self.assert_problem(self.record_gap(), 409, "does_not_apply")
        self.activate(self.world.tenant)
        self.assertFalse(Gap.objects.exists())

    def test_a_legal_entity_whose_answer_is_does_not_apply_has_no_gap(self) -> None:
        entry = self.world.entry()
        with transaction.atomic():
            tenancy.activate(self.world.tenant.id)
            TenantObligationScope.objects.create(
                tenant=self.world.tenant,
                tenant_obligation=entry,
                org_unit=self.world.entity,
                applicability=Applicability.DOES_NOT_APPLY.value,
                compliance_status=ComplianceStatus.objects.get(is_default=True),
            )
        self.assert_problem(self.record_gap(orgUnitId=str(self.world.entity.id)), 409, "does_not_apply")
        self.assertEqual(self.record_gap().status_code, 201, "the obligation as a whole still takes a gap")

    def test_what_a_gap_names_must_be_the_banks_own(self) -> None:
        other = factories.tenant(slug="gaps-other")
        stranger = factories.member_user(other, roles=("owner",))
        with transaction.atomic():
            tenancy.activate(other.id)
            foreign_entity = OrgUnit.objects.create(tenant=other, kind=OrgUnitKind.LEGAL_ENTITY.value, name="Other Bank AB")
        with transaction.atomic():
            tenancy.activate(self.world.tenant.id)
            group = OrgUnit.objects.create(tenant=self.world.tenant, kind=OrgUnitKind.GROUP.value, name="Example Group")
            GapSource.objects.filter(key="incident").update(active=False)
        gone = factories.member(self.world.tenant, roles=("owner",))
        with transaction.atomic():
            tenancy.activate(self.world.tenant.id)
            type(gone).objects.filter(pk=gone.pk).update(deactivated_at=timezone.now())
        cases: list[tuple[dict[str, Any], int, str]] = [
            ({"severity": "catastrophic"}, 422, "unknown_key"),
            ({"source": "rumour"}, 422, "unknown_key"),
            ({"source": "incident"}, 422, "unknown_key"),
            ({"ownerTeam": "nobody"}, 422, "unknown_key"),
            ({"ownerId": str(stranger.id)}, 422, "unknown_member"),
            ({"ownerId": str(gone.user_id)}, 422, "unknown_member"),
            ({"ownerId": str(uuid.uuid4())}, 422, "unknown_member"),
            ({"ownerId": str(self.world.owner.id), "ownerTeam": "compliance"}, 422, "validation_error"),
            ({"orgUnitId": str(foreign_entity.id)}, 404, "not_found"),
            ({"orgUnitId": str(group.id)}, 404, "not_found"),
            ({"unitId": str(uuid.uuid4())}, 422, "unknown_unit"),  # c8-units-paste-soa: a unit the bank does not have
        ]
        headers = self.as_(self.world.officer)
        for overrides, status, code in cases:
            with self.subTest(overrides=overrides):
                problem = self.assert_problem(self.record_gap(headers, **overrides), status, code)
                if overrides.get("severity"):
                    self.assertIn("high", problem["detail"], "an unknown key names the keys the list holds")
        self.assert_problem(self.record_gap(headers, obligation=type(self.world.obligation)(id=uuid.uuid4())), 404, "not_found")
        self.activate(self.world.tenant)
        self.assertFalse(Gap.objects.exists())
        self.assertFalse(TenantObligation.objects.exists(), "a refused gap creates no entry")


class AmendingAGap(GapTestCase):
    def test_a_gap_moves_from_open_to_remediating_to_closed_each_audited(self) -> None:
        gap = self.gap()
        remediating = self.patch(gap, {"status": "remediating"})
        self.assertEqual(remediating.status_code, 200, remediating.content)
        self.assertEqual((remediating.json()["status"]["kind"], remediating.json()["version"]), ("remediating", 2))
        closed = self.patch(remediating.json(), {"status": "closed"})
        self.assertEqual(closed.json()["status"]["kind"], "closed")
        stored = self.stored(gap)
        self.assertEqual((stored.closed_by_id, stored.closed_at is not None), (self.world.officer.id, True))
        moves = [(e.before["status"], e.after["status"]) for e in self.events(gaps.GAP_AMENDED, gap["id"])]
        self.assertEqual(moves, [("open", "remediating"), ("remediating", "closed")])

    def test_the_fields_sent_change_and_the_audit_names_typed_fields_without_their_text(self) -> None:
        gap = self.gap()
        target = (timezone.localdate() + datetime.timedelta(days=30)).isoformat()
        body = {"title": "Evidence is kept by hand", "remediation": "A new plan", "severity": "low", "ownerId": str(self.world.owner.id), "targetDate": target}
        response = self.patch(gap, body)
        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()
        self.assertEqual((answer["title"], answer["remediation"], answer["severity"]["key"], answer["targetDate"]), (body["title"], "A new plan", "low", target))
        self.assertEqual(answer["owner"]["id"], str(self.world.owner.id))
        self.assertEqual(answer["source"]["key"], "assessment", "a field not sent stays as it is")
        [event] = self.events(gaps.GAP_AMENDED, gap["id"])
        self.assertEqual((event.before["severity"], event.after["severity"]), ("high", "low"))
        self.assertEqual((event.before["ownerId"], event.after["ownerId"]), (None, str(self.world.owner.id)))
        self.assertEqual(event.after["edited"], ["title", "remediation"])
        self.assertNotIn("A new plan", str(event.after))
        self.assert_typed_text_absent(event)
        team = self.patch(answer, {"ownerTeam": "compliance"})
        self.assertEqual((team.json()["owner"], team.json()["ownerTeam"]["key"]), (None, "compliance"))

    def test_a_write_without_the_current_version_is_refused_and_nothing_merges(self) -> None:
        gap = self.gap()
        self.assertEqual(self.patch(gap, {"status": "remediating"}).status_code, 200)
        self.assert_problem(self.patch(gap, {"title": "Second writer"}), 409, "stale_write")
        missing = self.client.patch(f"{GAPS}/{gap['id']}", data={"title": "No version"}, content_type="application/json", **self.as_(self.world.officer))
        self.assert_problem(missing, 409, "stale_write")
        self.assertEqual((self.stored(gap).title, self.stored(gap).version), (TITLE, 2))

    def test_moves_the_patch_does_not_make(self) -> None:
        gap = self.gap()
        self.assert_problem(self.patch(gap, {"status": "risk_accepted"}), 409, "invalid_transition")
        self.assert_problem(self.patch(gap, {"status": "maybe"}), 422, "unknown_key")
        closed = self.patch(gap, {"status": "closed"}).json()
        self.assert_problem(self.patch(closed, {"status": "remediating"}), 409, "invalid_transition")
        self.assertEqual(self.stored(gap).status.key, "closed")

    def test_closing_clears_a_waiting_acceptance(self) -> None:
        gap = self.gap()
        waiting = self.client.post(f"{GAPS}/{gap['id']}/accept-risk", data={"reason": "other"}, content_type="application/json", **self.as_(self.world.officer)).json()
        closed = self.patch(waiting, {"status": "closed"})
        self.assertEqual(closed.json()["riskAcceptance"], None)
        self.assertEqual(len(self.events(gaps.RISK_ACCEPTANCE_REQUESTED, gap["id"])), 1, "the request stays in the audit log")

    def test_a_reader_cannot_amend(self) -> None:
        gap = self.gap()
        response = self.patch(gap, {"status": "remediating"}, self.as_(self.world.reader))
        self.assertEqual(response.json()["requiredPermission"], perms.GAPS_EDIT)


class ListingGaps(GapTestCase):
    def _seed(self, count: int, **fields: Any) -> list[Gap]:
        entry = self.world.entry()
        with transaction.atomic():
            tenancy.activate(self.world.tenant.id)
            defaults = {
                "severity": RiskRating.objects.get(key="medium"),
                "source": GapSource.objects.get(key="audit"),
                "status": GapStatus.objects.get(key="open"),
                "identified_by": self.world.officer,
                **fields,
            }
            return [Gap.objects.create(tenant=self.world.tenant, tenant_obligation=entry, title=f"Gap {n}", **defaults) for n in range(count)]

    def _list(self, query: str = "", headers: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.client.get(f"{GAPS}{query}", **(headers or self.as_(self.world.reader)))
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def test_every_gap_by_target_date_then_id_with_undated_last_and_pages(self) -> None:
        today = timezone.localdate()
        late = self._seed(2, target_date=today + datetime.timedelta(days=60))
        soon = self._seed(2, target_date=today + datetime.timedelta(days=10))
        undated = self._seed(1)
        expected = [str(g.id) for g in sorted(soon, key=lambda g: g.id) + sorted(late, key=lambda g: g.id) + undated]
        self.assertEqual([item["id"] for item in self._list()["items"]], expected)
        page = self._list("?limit=2&offset=2")
        self.assertEqual(([item["id"] for item in page["items"]], page["total"]), (expected[2:4], 5))

    def test_the_filters_combine_with_and(self) -> None:
        today = timezone.localdate()
        with transaction.atomic():
            tenancy.activate(self.world.tenant.id)
            remediating = GapStatus.objects.get(key="remediating")
            high = RiskRating.objects.get(key="high")
        [target] = self._seed(1, status=remediating, severity=high, owner=self.world.owner, org_unit=self.world.entity, target_date=today)
        self._seed(1, status=remediating, severity=high, owner=self.world.owner, target_date=today)
        self._seed(1, severity=high, owner=self.world.owner, org_unit=self.world.entity, target_date=today)
        self._seed(1, status=remediating, owner=self.world.owner, org_unit=self.world.entity, target_date=today)
        self._seed(1, status=remediating, severity=high, org_unit=self.world.entity, target_date=today)
        self._seed(1, status=remediating, severity=high, owner=self.world.owner, org_unit=self.world.entity, target_date=today + datetime.timedelta(days=5))
        query = (
            f"?status=remediating&severity=high&owner={self.world.owner.id}&entity={self.world.entity.id}"
            f"&targetFrom={(today - datetime.timedelta(days=1)).isoformat()}&targetTo={today.isoformat()}"
        )
        self.assertEqual([item["id"] for item in self._list(query)["items"]], [str(target.id)])
        self.assertEqual(self._list("?status=nothing"), {"items": [], "total": 0})

    def test_one_obligations_gaps_and_an_obligation_nobody_worked_on(self) -> None:
        mine = self.gap()
        self.gap(obligation=self.world.other_obligation)
        response = self.client.get(self.world.url(), **self.as_(self.world.reader))
        self.assertEqual([item["id"] for item in response.json()["items"]], [mine["id"]])
        act = library_testing.instrument(key="gaps-untouched-act", regime="regime:securities")
        untouched = library_testing.obligation(act, key="gaps-untouched")
        empty = self.client.get(self.world.url(untouched), **self.as_(self.world.reader))
        self.assertEqual((empty.status_code, empty.json()), (200, {"items": [], "total": 0}))
        missing = self.client.get(f"{V1}/obligations/{uuid.uuid4()}/gaps", **self.as_(self.world.reader))
        self.assert_problem(missing, 404, "not_found")

    def test_gaps_stay_visible_whatever_the_applicability(self) -> None:
        gap = self.gap()
        self.world.set_entry(applicability=Applicability.DOES_NOT_APPLY.value)
        self.assertEqual([item["id"] for item in self._list()["items"]], [gap["id"]])

    def _varied(self, count: int) -> None:
        """Gaps owned by a team and gaps waiting for an acceptance, so every label query runs."""
        with transaction.atomic():
            tenancy.activate(self.world.tenant.id)
            team = Team.objects.get(key="compliance")
            reason = RiskAcceptanceReason.objects.get(key="other")
        self._seed(count, owner_team=team)
        self._seed(count, acceptance_reason=reason, acceptance_requested_by=self.world.officer, acceptance_requested_at=timezone.now())

    def test_a_page_costs_the_same_queries_however_many_gaps_there_are(self) -> None:
        tenant: Tenant = self.world.tenant
        self._varied(1)
        self.activate(tenant)
        with self.assertNumQueries(GAP_PAGE_QUERIES):
            small = gaps.list_gaps(tenant=tenant, order=["en"], filters=RegisterGapQuery(), limit=20, offset=0)
        headers = self.as_(self.world.reader)
        with CaptureQueriesContext(connection) as few:
            self._list(headers=headers)
        self._varied(8)
        self.activate(tenant)
        with self.assertNumQueries(GAP_PAGE_QUERIES):
            large = gaps.list_gaps(tenant=tenant, order=["en"], filters=RegisterGapQuery(), limit=20, offset=0)
        with CaptureQueriesContext(connection) as many:
            self._list(headers=headers)
        self.assertEqual((len(small["items"]), len(large["items"])), (2, 18))
        self.assertEqual(len(many), len(few))

    def test_a_full_page_stays_inside_the_budget(self) -> None:
        self._varied(10)
        headers = self.as_(self.world.reader)
        response = self.client.get(GAPS, **headers)
        self.assertEqual(len(response.json()["items"]), 20)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        # CPU time on the request thread, the best of five, with coverage's tracer paused, as
        # apps/home/tests_roadmap.py measures it.
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                self.client.get(GAPS, **headers)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)

    def test_another_banks_gaps_are_not_listed_and_its_gap_is_404_to_every_route(self) -> None:
        theirs = factories.gap(factories.tenant(slug="gaps-theirs"))
        self.gap()
        items = self._list()["items"]
        self.assertNotIn(str(theirs.id), [item["id"] for item in items])
        headers = self.as_(self.world.second_officer, step_up=True)
        for suffix, body in (("/accept-risk", {"reason": "other"}), ("/accept-risk/approve", None), ("/reopen", None)):
            with self.subTest(route=suffix):
                response = self.client.post(f"{GAPS}/{theirs.id}{suffix}", data=body or {}, content_type="application/json", **headers)
                self.assert_problem(response, 404, "not_found")
        self.assert_problem(self.patch({"id": theirs.id, "version": 1}, {"title": "Mine now"}, headers), 404, "not_found")


class AcceptingARisk(GapTestCase):
    def ask(self, gap: dict[str, Any], headers: dict[str, Any] | None = None, **body: Any) -> Any:
        return self.client.post(
            f"{GAPS}/{gap['id']}/accept-risk",
            data={"reason": "compensating_control", "note": NOTE, **body},
            content_type="application/json",
            **(headers or self.as_(self.world.officer)),
        )

    def approve(self, gap: dict[str, Any], user: Any, *, step_up: bool = True) -> Any:
        return self.client.post(f"{GAPS}/{gap['id']}/accept-risk/approve", **self.as_(user, step_up=step_up))

    def test_asking_waits_for_approval_without_moving_the_status(self) -> None:
        gap = self.gap()
        response = self.ask(gap)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"]["key"], "open")
        acceptance = body["riskAcceptance"]
        self.assertEqual((acceptance["reason"]["key"], acceptance["note"]), ("compensating_control", NOTE))
        self.assertEqual((acceptance["requestedBy"]["id"], acceptance["approvedBy"], acceptance["approvedAt"]), (str(self.world.officer.id), None, None))
        [event] = self.events(gaps.RISK_ACCEPTANCE_REQUESTED, gap["id"])
        self.assertEqual(event.after, {"reason": "compensating_control", "requestedBy": str(self.world.officer.id)})
        self.assert_problem(self.ask(gap), 409, "request_pending")

    def test_what_an_acceptance_request_is_refused_for(self) -> None:
        gap = self.gap()
        problem = self.assert_problem(self.ask(gap, reason="because"), 422, "unknown_key")
        self.assertIn("compensating_control", problem["detail"])
        closed = self.patch(gap, {"status": "closed"}).json()
        self.assert_problem(self.ask(closed), 409, "invalid_transition")
        self.assertEqual(self.events(gaps.RISK_ACCEPTANCE_REQUESTED), [])

    def test_the_requester_is_refused_before_any_write_and_a_second_person_accepts(self) -> None:
        gap = self.gap()
        waiting = self.ask(gap).json()
        audit_rows = len(self.events(gaps.RISK_ACCEPTED))
        self.assert_problem(self.approve(gap, self.world.officer), 409, "four_eyes_violation")
        stored = self.stored(gap)
        self.assertEqual((stored.accepted_by_id, stored.status.key, stored.version), (None, "open", waiting["version"]))
        self.assertEqual(len(self.events(gaps.RISK_ACCEPTED)), audit_rows)
        response = self.approve(gap, self.world.second_officer)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], {"key": "risk_accepted", "kind": "risk_accepted", "label": "Risk accepted"})
        self.assertEqual(body["riskAcceptance"]["approvedBy"]["id"], str(self.world.second_officer.id))
        [event] = self.events(gaps.RISK_ACCEPTED, gap["id"])
        assertion = StepUpAssertion.objects.filter(session__user=self.world.second_officer).latest("created_at")
        self.assertEqual(event.step_up_assertion_id, assertion.id)
        self.assertEqual(event.actor_id, self.world.second_officer.id)
        self.assertEqual(
            (event.after["requestedBy"], event.after["approvedBy"], event.after["reason"], event.before["status"], event.after["status"]),
            (str(self.world.officer.id), str(self.world.second_officer.id), "compensating_control", "open", "risk_accepted"),
        )
        self.assert_typed_text_absent(event)

    def test_an_approval_needs_a_waiting_request_and_a_fresh_step_up(self) -> None:
        gap = self.gap()
        self.assert_problem(self.approve(gap, self.world.second_officer), 409, "invalid_transition")
        self.ask(gap)
        self.assert_problem(self.approve(gap, self.world.second_officer, step_up=False), 403, "step_up_required")
        self.assert_problem(self.approve(gap, self.world.owner), 403, "permission_denied")
        self.assertEqual(self.approve(gap, self.world.second_officer).status_code, 200)
        self.assert_problem(self.approve(gap, self.world.second_officer), 409, "invalid_transition")

    def test_the_database_refuses_the_requester_as_approver(self) -> None:
        gap = self.gap()
        self.ask(gap)
        self.activate(self.world.tenant)
        with transaction.atomic(), self.assertRaisesMessage(IntegrityError, "gap_four_eyes"):
            Gap.objects.filter(pk=gap["id"]).update(
                accepted_by_id=self.world.officer.id, accepted_at=timezone.now(), status=GapStatus.objects.get(key="risk_accepted")
            )

    def test_reopening_clears_the_acceptance_and_keeps_it_in_the_audit_log(self) -> None:
        gap = self.gap()
        self.ask(gap)
        accepted = self.approve(gap, self.world.second_officer).json()
        self.assert_problem(self.patch(accepted, {"status": "open"}), 409, "invalid_transition")
        response = self.client.post(f"{GAPS}/{gap['id']}/reopen", **self.as_(self.world.owner))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["status"]["key"], response.json()["riskAcceptance"]), ("open", None))
        [event] = self.events(gaps.GAP_REOPENED, gap["id"])
        self.assertEqual((event.before["status"], event.after["status"]), ("risk_accepted", "open"))
        self.assertEqual(len(self.events(gaps.RISK_ACCEPTED, gap["id"])), 1)
        self.assert_problem(self.client.post(f"{GAPS}/{gap['id']}/reopen", **self.as_(self.world.owner)), 409, "invalid_transition")
        closed = self.patch(response.json(), {"status": "closed"}).json()
        reopened = self.client.post(f"{GAPS}/{closed['id']}/reopen", **self.as_(self.world.owner)).json()
        self.assertEqual(reopened["status"]["key"], "open")
        self.assertIsNone(self.stored(gap).closed_at)


# --- Two approvals at once -------------------------------------------------------------
def _session(tenant_id: uuid.UUID, work: Callable[[], object]) -> str:
    """Run `work` in one transaction on a fresh cw_app connection of this thread's own, as
    apps/taxonomy/tests_footprint.py does. Answers "landed" or the refusal's code."""
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


class RiskAcceptanceRace(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        seed_library()
        self.world = GapWorld("gaps-race")
        self.third_officer = factories.member_user(self.world.tenant, roles=("approver",))
        officer = Actor(kind=ActorType.USER, id=self.world.officer.id, label=self.world.officer.name)
        with transaction.atomic():
            tenancy.activate(self.world.tenant.id)
            gap = gaps.create_gap(
                tenant=self.world.tenant, actor=officer, order=["en"], obligation_id=self.world.obligation.id, body=RegisterGapBody(**gap_body())
            )
            gaps.request_risk_acceptance(
                tenant=self.world.tenant, actor=officer, order=["en"], gap_id=gap["id"], body=RegisterRiskAcceptanceBody(reason="other")
            )
        self.gap_id = gap["id"]

    def _approve(self, user: Any) -> Callable[[], object]:
        actor = Actor(kind=ActorType.USER, id=user.id, label=user.name)
        return lambda: gaps.approve_risk_acceptance(
            tenant=self.world.tenant, actor=actor, order=["en"], gap_id=self.gap_id, step_up_assertion_id=uuid.uuid4()
        )

    def test_two_approvals_at_once_land_one(self) -> None:
        acted = threading.Event()
        second_pid: list[int] = []

        def lead() -> None:
            self._approve(self.world.second_officer)()
            acted.set()
            hold_until_waiting_on_me(second_pid)

        def follow() -> None:
            second_pid.append(backend_pid())
            if not acted.wait(RACE_WAIT_SECONDS):
                raise AssertionError("the first session never acted")
            self._approve(self.third_officer)()

        with ThreadPoolExecutor(max_workers=2) as pool:
            leading = pool.submit(_session, self.world.tenant.id, lead)
            following = pool.submit(_session, self.world.tenant.id, follow)
            outcomes = (leading.result(), following.result())
        self.assertEqual(outcomes, (LANDED, "invalid_transition"))
        with transaction.atomic():
            tenancy.activate(self.world.tenant.id)
            gap = Gap.objects.get(pk=self.gap_id)
            self.assertEqual((gap.accepted_by_id, gap.status.key), (self.world.second_officer.id, "risk_accepted"))
            events = AuditEvent.objects.filter(tenant=self.world.tenant, action=gaps.RISK_ACCEPTED, subject_id=self.gap_id)
            self.assertEqual([e.actor_id for e in events], [self.world.second_officer.id])

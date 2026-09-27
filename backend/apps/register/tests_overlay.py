"""The register overlay on the inventory (REG-01, REG-02, INV-03): `GET /obligations` and the
card carry the caller's bank's applicability, compliance status and owner, and nothing of
another bank's; the four overlay filters and their bounds; one overlay query per page
whatever its size; a read that writes nothing; a status shown only where the duty applies,
the worst of the applying entities' by the rank `status_logic.worst_of()` also reads; and
the scope rule left in `library/reading.py`.

Proven to fail 2026-09-25 in a scratch copy: with the `answer == "applies"` guard removed
the duty that does not apply showed its kept gap; with the rank ordered descending the
entity roll-up named the best status instead of the worst. With the bank's id dropped from
`overlay._entries()` the suite stays green, because forced row-level security alone keeps
tenant A's entries from tenant B's session, which is what the tenant B test proves; the id
is defence in depth, as in `library.reading.tenant_tags()`."""

from __future__ import annotations

import ast
import inspect
import itertools
from typing import Any

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.agents import testing as agents_testing
from apps.identity.models import User
from apps.library.models import Obligation
from apps.library.tests_reading import FOOTPRINT, URL, keys, seed_obligations, seed_reference, set_footprint
from apps.register import overlay
from apps.register.models import Applicability, TenantObligation, TenantObligationScope
from apps.register.status_logic import worst_of
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import ComplianceCategory, ComplianceStatus, Team
from apps.tenants.models import OrgUnit

OVERLAY_FIELDS = ("applicability", "complianceStatus", "firstLineOwner", "ownerTeam")


def entry(
    tenant: Tenant, obligation: Obligation, applicability: str, status: str, owner: User | None = None, team: Team | None = None
) -> TenantObligation:
    tenancy.activate(tenant.id)
    return TenantObligation.objects.create(
        tenant=tenant,
        obligation=obligation,
        applicability=applicability,
        compliance_status=ComplianceStatus.objects.get(tenant=tenant, key=status),
        first_line_owner=owner,
        owner_team=team,
    )


def entity_row(tenant: Tenant, on: TenantObligation, entity: OrgUnit, applicability: str, status: str) -> TenantObligationScope:
    tenancy.activate(tenant.id)
    return TenantObligationScope.objects.create(
        tenant=tenant,
        tenant_obligation=on,
        org_unit=entity,
        applicability=applicability,
        applicability_decided_at=timezone.now(),
        compliance_status=ComplianceStatus.objects.get(tenant=tenant, key=status),
    )


class InventoryOverlay(TestCase):
    """Tenant A's footprint hides b and c. A has answered a (applies, partly, with an owner
    and a team), b (outside the footprint, applies, compliant), c (an entry nobody answered),
    d (per entity: compliant, gap, and a partly entity that does not apply) and e (does not
    apply, a gap kept); f has no entry. Tenant B answered a the other way."""

    tenant: Tenant
    other: Tenant
    reader: User
    owner: User
    other_reader: User
    by_key: dict[str, Obligation]
    rolled: TenantObligation
    entities: list[TenantObligationScope]

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="overlay-a")
        cls.other = factories.tenant(slug="overlay-b")
        set_footprint(cls.tenant, FOOTPRINT)
        set_footprint(cls.other, FOOTPRINT)
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.owner = factories.member(cls.tenant, roles=("owner",), user_row=factories.user(name="Anna Berg")).user
        cls.other_reader = factories.member_user(cls.other, roles=("reader",))
        other_owner = factories.member_user(cls.other, roles=("owner",))
        seed_obligations()
        cls.by_key = {obligation.stable_key: obligation for obligation in Obligation.objects.all()}
        a, b, c, d, e = (cls.by_key[key] for key in ("obl-a-appropriateness", "obl-b-advice", "obl-c-insurance", "obl-d-research", "obl-e-guidance"))
        applies, not_applicable, unanswered = (Applicability.APPLIES.value, Applicability.DOES_NOT_APPLY.value, Applicability.NOT_ASSESSED.value)
        tenancy.activate(cls.tenant.id)
        team = Team.objects.get(tenant=cls.tenant, key="compliance")
        entry(cls.tenant, a, applies, "partly_compliant", cls.owner, team)
        entry(cls.tenant, b, applies, "compliant")
        entry(cls.tenant, c, unanswered, "not_assessed")
        cls.rolled = entry(cls.tenant, d, unanswered, "not_assessed")
        cls.entities = [
            entity_row(cls.tenant, cls.rolled, factories.legal_entity(cls.tenant, name=name), answer, status)
            for name, answer, status in (
                ("Example Bank AB", applies, "compliant"),
                ("Example Finance AB", applies, "gap"),
                ("Example Liv AB", not_applicable, "partly_compliant"),
            )
        ]
        entry(cls.tenant, e, not_applicable, "gap")
        entry(cls.other, a, not_applicable, "gap", other_owner)
        tenancy.activate(cls.tenant.id)

    def get(self, params: dict[str, Any], url: str = URL, *, who: User | None = None, tenant: Tenant | None = None) -> Any:
        return self.client.get(url, params, **sign_in(who or self.reader, tenant=tenant or self.tenant))

    def rows(self, params: dict[str, Any] | None = None, *, who: User | None = None, tenant: Tenant | None = None) -> dict[str, dict[str, Any]]:
        response = self.get({"footprint": "all", **(params or {})}, who=who, tenant=tenant)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["stableKey"]: row for row in response.json()["items"]}

    def test_a_row_carries_the_banks_applicability_status_and_owner(self) -> None:
        rows = self.rows()
        a = rows["obl-a-appropriateness"]
        self.assertEqual(a["applicability"], "applies")
        self.assertEqual(a["complianceStatus"], {"key": "partly_compliant", "kind": "partly", "label": "Partly compliant"})
        self.assertEqual(a["firstLineOwner"], {"id": str(self.owner.id), "name": "Anna Berg"})
        self.assertEqual(a["ownerTeam"], {"key": "compliance", "kind": None, "label": "Compliance"})
        # Outside the footprint, shown under `all`: the scope hides rows, never the bank's judgement.
        self.assertFalse(rows["obl-b-advice"]["inFootprint"])
        self.assertEqual((rows["obl-b-advice"]["applicability"], rows["obl-b-advice"]["complianceStatus"]["key"]), ("applies", "compliant"))
        # One entity's yes is the duty's yes, and its pill is the worst applying entity's.
        self.assertEqual((rows["obl-d-research"]["applicability"], rows["obl-d-research"]["complianceStatus"]["key"]), ("applies", "gap"))
        # Does not apply: the kept gap is not shown.
        self.assertEqual((rows["obl-e-guidance"]["applicability"], rows["obl-e-guidance"]["complianceStatus"]), ("not_applicable", None))
        # An entry nobody answered, and no entry at all, read alike.
        for key in ("obl-c-insurance", "obl-f-unscoped"):
            with self.subTest(key=key):
                self.assertEqual([rows[key][field] for field in OVERLAY_FIELDS], ["under_assessment", None, None, None])

    def test_the_card_carries_the_rows_overlay(self) -> None:
        rows = self.rows()
        for key, obligation in self.by_key.items():
            with self.subTest(key=key):
                card = self.get({}, f"{URL}/{obligation.id}").json()
                self.assertEqual({field: card[field] for field in OVERLAY_FIELDS}, {field: rows[key][field] for field in OVERLAY_FIELDS})

    def test_another_bank_reads_its_own_answer_and_nothing_of_ours(self) -> None:
        rows = self.rows(who=self.other_reader, tenant=self.other)
        a = rows["obl-a-appropriateness"]
        self.assertEqual((a["applicability"], a["complianceStatus"], a["ownerTeam"]), ("not_applicable", None, None))
        self.assertNotEqual(a["firstLineOwner"]["id"], str(self.owner.id))
        for key in ("obl-b-advice", "obl-d-research", "obl-e-guidance"):
            with self.subTest(key=key):
                self.assertEqual([rows[key][field] for field in OVERLAY_FIELDS], ["under_assessment", None, None, None])
        card = self.get({}, f"{URL}/{self.by_key['obl-d-research'].id}", who=self.other_reader, tenant=self.other).json()
        self.assertEqual((card["applicability"], card["complianceStatus"]), ("under_assessment", None))
        self.assertEqual(keys(self.get({"footprint": "all", "complianceStatus": "gap"}, who=self.other_reader, tenant=self.other)), [])

    def test_the_overlay_filters(self) -> None:
        cases: list[tuple[dict[str, Any], list[str]]] = [
            ({"applicability": "applies"}, ["obl-a-appropriateness", "obl-b-advice", "obl-d-research"]),
            ({"applicability": "not_applicable"}, ["obl-e-guidance"]),
            ({"applicability": "under_assessment"}, ["obl-c-insurance", "obl-f-unscoped"]),
            ({"complianceStatus": "gap"}, ["obl-d-research"]),
            ({"complianceStatus": "partly_compliant"}, ["obl-a-appropriateness"]),
            ({"complianceStatus": "not_assessed"}, []),
            ({"complianceStatus": "no-such-status"}, []),
            ({"owner": str(self.owner.id)}, ["obl-a-appropriateness"]),
            ({"owner": str(self.reader.id)}, []),
            ({"ownerTeam": "compliance"}, ["obl-a-appropriateness"]),
            ({"ownerTeam": "no-such-team"}, []),
            ({"applicability": "applies", "complianceStatus": "compliant"}, ["obl-b-advice"]),
        ]
        for params, expected in cases:
            with self.subTest(params=params):
                response = self.get({"footprint": "all", **params})
                self.assertEqual(keys(response), expected)
                self.assertEqual(response.json()["total"], len(expected))
        # The footprint still decides the page first: b applies but sits outside it.
        self.assertEqual(keys(self.get({"applicability": "applies"})), ["obl-a-appropriateness", "obl-d-research"])

    def test_every_overlay_filter_is_bounded(self) -> None:
        for params in (
            {"complianceStatus": "x" * 81},
            {"ownerTeam": "x" * 81},
            {"applicability": "maybe"},
            {"owner": "not-a-uuid"},
        ):
            with self.subTest(params=params):
                refused = self.get(params)
                self.assertEqual((refused.status_code, refused.json()["code"]), (422, "validation_error"))
        self.assertEqual(keys(self.get({"complianceStatus": "x" * 80})), [], "eighty characters is still a key")

    def test_a_key_with_no_bank_is_refused_the_overlay_filters(self) -> None:
        with tenancy.platform_zone():
            key = agents_testing.agent_key(scopes=(perms.SCOPE_LIBRARY_READ,))
        for params in ({"applicability": "applies"}, {"complianceStatus": "gap"}, {"owner": str(self.owner.id)}, {"ownerTeam": "compliance"}):
            with self.subTest(params=params):
                refused = self.client.get(URL, params, HTTP_X_API_KEY=key.plain_key)
                self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_filter"))

    def test_no_row_waits_on_a_request(self) -> None:
        row = self.rows()["obl-a-appropriateness"]
        self.assertFalse([name for name in row if "pending" in name.lower() or "waiting" in name.lower()])

    def test_the_overlay_is_one_query_whatever_the_page(self) -> None:
        for params in ({}, {"applicability": "applies", "owner": str(self.owner.id)}, {"applicability": "applies"}):
            counts = []
            for limit in (1, 6):
                with self.subTest(params=params, limit=limit), CaptureQueriesContext(connection) as captured:
                    response = self.get({"footprint": "all", "limit": limit, **params})
                self.assertEqual(response.status_code, 200)
                reads = [query["sql"] for query in captured.captured_queries if query["sql"].startswith('SELECT "tenant_obligation".')]
                self.assertEqual(len(reads), 1, "one overlay read per page; the filters are subqueries of the page's own query")
                counts.append(len(captured.captured_queries))
            self.assertEqual(counts[0], counts[1])

    def test_a_read_writes_nothing(self) -> None:
        def written() -> tuple[int, int, int]:
            tenancy.activate(self.tenant.id)
            return TenantObligation.objects.count(), TenantObligationScope.objects.count(), AuditEvent.objects.filter(subject_type__startswith="tenant_obligation").count()

        before = written()
        self.rows({"applicability": "under_assessment"})
        self.get({}, f"{URL}/{self.by_key['obl-f-unscoped'].id}")
        self.assertEqual(written(), before)

    def test_the_roll_up_is_the_worst_by_the_rank_worst_of_reads(self) -> None:
        tenancy.activate(self.tenant.id)
        seeded = ("compliant", "partly_compliant", "gap", "not_assessed")
        by_kind = {status.kind: status for status in ComplianceStatus.objects.filter(tenant=self.tenant, key__in=seeded)}
        self.assertEqual(set(by_kind), {category.value for category in ComplianceCategory})
        bank, finance, _ = self.entities
        for first, second in itertools.product(ComplianceCategory, repeat=2):
            with self.subTest(first=first.value, second=second.value):
                TenantObligationScope.objects.filter(pk=bank.pk).update(compliance_status=by_kind[first.value])
                TenantObligationScope.objects.filter(pk=finance.pk).update(compliance_status=by_kind[second.value])
                shown = overlay.overlay(self.tenant, [self.rolled.obligation_id], ["en"])[self.rolled.obligation_id].compliance_status
                expected = worst_of([by_kind[first.value], by_kind[second.value]])
                assert shown is not None and expected is not None
                self.assertEqual(shown.key, expected.key)

    def test_the_register_holds_no_scope_rule_of_its_own(self) -> None:
        # The footprint decides which rows a page holds in library/reading.py alone: the
        # overlay's code names no footprint, no matching module and no library read.
        tree = ast.parse(inspect.getsource(overlay))
        named = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        named |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        named |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        for name in ("in_footprint", "in_footprint_expression", "in_view", "footprint_of", "FootprintTerm", "apps.taxonomy.matching", "apps.library.reading"):
            with self.subTest(name=name):
                self.assertNotIn(name, named)

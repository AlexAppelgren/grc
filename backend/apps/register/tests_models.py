"""The register's tables (register 0001 and 0002; REG-01 to REG-05, TEN-03), proved as cw_app
on committed rows: tenant B sees none of tenant A's register, the database refuses every
reference to another tenant's row, risk acceptance keeps four eyes in a CHECK, the
assessment history is append-only by trigger, a link is never deleted, and
`ensure_register_entry()` is the one creator of an entry, with its audit event in the same
transaction.

The cross-tenant proof walks the migrations' own `COMPOSITE_KEYS`, so a key added there is
proved here without a line of its own. Proven to fail 2026-09-25: with the composite-key
operations left out of a scratch copy of 0002 every gap, interpretation and link key went
through; with `gap_four_eyes` removed the four-eyes test named it; and with
`TenantObligation.objects.create(...)` planted in apps/register/api.py the AST guard named
the file and line."""

from __future__ import annotations

import ast
import importlib
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, DatabaseError, IntegrityError, connection, connections, transaction
from django.db.models import Model
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from apps.library import testing as library_testing
from apps.library.models import Obligation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.register import logic
from apps.register.models import (
    Applicability,
    AssessmentMethod,
    ComplianceAssessment,
    Gap,
    InternalLink,
    Interpretation,
    TenantObligation,
    TenantObligationScope,
)
from apps.shared import factories, tenancy
from apps.shared.audit import AppendOnlyRefused
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import RACE_WAIT_SECONDS, backend_pid, hold_until_waiting_on_me
from apps.shared.tests_library_fence import production_modules
from apps.taxonomy.models import ComplianceStatus, GapSource, GapStatus, RiskAcceptanceReason, RiskRating, Team
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.tenants.tests_models import Organisation

APP = "app"
APPS_DIR = Path(__file__).resolve().parent.parent
REGISTER_MODELS: tuple[type[Model], ...] = (
    TenantObligation,
    TenantObligationScope,
    ComplianceAssessment,
    Gap,
    Interpretation,
    InternalLink,
)
COMPOSITE_KEYS = (
    *importlib.import_module("apps.register.migrations.0001_register").COMPOSITE_KEYS,
    *importlib.import_module("apps.register.migrations.0002_gaps_history_links").COMPOSITE_KEYS,
)
# A scope row and a gap are owned by a person or a team, never both, so pointing one at
# another bank's team clears the person first, and the other way round.
OTHER_OWNER = {"owner_id": "owner_team_id", "owner_team_id": "owner_id"}


def _seed_library() -> None:
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()


class Register:
    """One bank's register, every table written once as cw_app in its own zone, every
    nullable reference filled so each composite key has a row to be proved on."""

    def __init__(self, tenant: Tenant, obligation: Obligation) -> None:
        self.tenant = tenant
        self.organisation = Organisation(tenant, factories.member(tenant).user_id)
        self.user_id = self.organisation.head_user_id
        self.second_user_id = factories.member(tenant).user_id
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            self.status = ComplianceStatus.objects.using(APP).get(is_default=True)
            self.risk = RiskRating.objects.using(APP).get(key="high")
            self.team = Team.objects.using(APP).get(key="compliance")
            self.gap_status = GapStatus.objects.using(APP).get(key="open")
            self.accepted_status = GapStatus.objects.using(APP).get(key="risk_accepted")
            self.gap_source = GapSource.objects.using(APP).get(key="audit")
            self.reason = RiskAcceptanceReason.objects.using(APP).get(key="other")
            self.entry = self.create(
                TenantObligation,
                obligation_id=obligation.id,
                applicability=Applicability.APPLIES.value,
                applicability_reason="We hold client assets.",
                applicability_decided_at=timezone.now(),
                applicability_decided_by_id=self.user_id,
                compliance_status_id=self.status.id,
                risk_rating_id=self.risk.id,
                first_line_owner_id=self.user_id,
                compliance_contact_id=self.second_user_id,
                owner_team_id=self.team.id,
            )
            self.scope = self.create(
                TenantObligationScope,
                tenant_obligation_id=self.entry.id,
                org_unit_id=self.organisation.entity.id,
                product_id=self.organisation.product.id,
                applicability_decided_by_id=self.user_id,
                compliance_status_id=self.status.id,
                risk_rating_id=self.risk.id,
                owner_id=self.user_id,
            )
            self.assessment_fields = {
                "tenant_obligation_id": self.entry.id,
                "scope_id": self.scope.id,
                "method": AssessmentMethod.INTERNAL_AUDIT.value,
                "status_id": self.status.id,
                "risk_rating_id": self.risk.id,
                "rationale": "Reconciled daily.",
                "assessed_by_id": self.user_id,
            }
            self.assessment = self.create(ComplianceAssessment, **self.assessment_fields)
            self.gap = self.create(
                Gap,
                tenant_obligation_id=self.entry.id,
                org_unit_id=self.organisation.entity.id,
                title="Reconciliation is weekly",
                severity_id=self.risk.id,
                source_id=self.gap_source.id,
                status_id=self.gap_status.id,
                identified_by_id=self.user_id,
                owner_id=self.user_id,
                acceptance_reason_id=self.reason.id,
                acceptance_requested_by_id=self.user_id,
                acceptance_requested_at=timezone.now(),
                accepted_by_id=self.second_user_id,
                accepted_at=timezone.now(),
                closed_by_id=self.user_id,
            )
            self.interpretation = self.create(
                Interpretation, tenant_obligation_id=self.entry.id, version_number=1, body="We read it as daily.", author_id=self.user_id
            )
            self.link = self.create(
                InternalLink,
                tenant_obligation_id=self.entry.id,
                internal_item_id=self.organisation.item.id,
                label="Custody policy",
                external_ref="POL-014",
                created_by_id=self.user_id,
                removed_by_id=self.user_id,
            )

    def create(self, model: type[Model], **fields: Any) -> Any:
        return model._default_manager.using(APP).create(tenant_id=self.tenant.id, **fields)

    def target(self, table: str) -> uuid.UUID:
        """This bank's row of a composite key's target table."""
        return {
            "membership": self.user_id,
            "team": self.team.id,
            "compliance_status": self.status.id,
            "risk_rating": self.risk.id,
            "gap_status": self.gap_status.id,
            "gap_source": self.gap_source.id,
            "risk_acceptance_reason": self.reason.id,
            "org_unit": self.organisation.entity.id,
            "tenant_product": self.organisation.product.id,
            "internal_item": self.organisation.item.id,
            "tenant_obligation": self.entry.id,
            "tenant_obligation_scope": self.scope.id,
        }[table]

    def row(self, table: str) -> Model:
        return {
            "tenant_obligation": self.entry,
            "tenant_obligation_scope": self.scope,
            "gap": self.gap,
            "interpretation": self.interpretation,
            "internal_link": self.link,
        }[table]


class RegisterTablesUnderRowLevelSecurity(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        _seed_library()
        act = library_testing.instrument(key="register-act", regime="regime:securities")
        obligation = library_testing.obligation(act, key="register-duty")
        self.a = Register(factories.tenant(slug="register-a"), obligation)
        self.b = Register(factories.tenant(slug="register-b"), obligation)

    def test_each_tenant_sees_only_its_own_register(self) -> None:
        for register in (self.a, self.b):
            with transaction.atomic(using=APP):
                tenancy.activate(register.tenant.id, using=APP)
                seen = {
                    model._meta.db_table: set(model._default_manager.using(APP).values_list("id", flat=True))
                    for model in REGISTER_MODELS
                }
            self.assertEqual(
                seen,
                {
                    "tenant_obligation": {register.entry.id},
                    "tenant_obligation_scope": {register.scope.id},
                    "compliance_assessment": {register.assessment.id},
                    "gap": {register.gap.id},
                    "interpretation": {register.interpretation.id},
                    "internal_link": {register.link.id},
                },
            )

    def test_the_database_refuses_every_reference_to_another_tenants_row(self) -> None:
        a, b = self.a, self.b
        for table, column, target, _ in COMPOSITE_KEYS:
            constraint = f"{table}_{column}_same_tenant"
            with self.subTest(constraint), transaction.atomic(using=APP):
                tenancy.activate(a.tenant.id, using=APP)
                with self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    if table == "compliance_assessment":
                        a.create(ComplianceAssessment, **{**a.assessment_fields, column: b.target(target)})
                    else:
                        row = a.row(table)
                        changes: dict[str, Any] = {column: b.target(target)}
                        if column in OTHER_OWNER and table in ("tenant_obligation_scope", "gap"):
                            changes[OTHER_OWNER[column]] = None
                        if table == "interpretation":
                            changes["version_number"] = 2  # B's entry already has a version 1
                        type(row)._default_manager.using(APP).filter(pk=row.pk).update(**changes)

    def test_risk_acceptance_keeps_four_eyes_and_names_its_reason_and_requester(self) -> None:
        a = self.a
        refusals: dict[str, dict[str, Any]] = {
            "gap_four_eyes": {"accepted_by_id": a.user_id},
            "gap_acceptance_complete": {"acceptance_reason_id": None},
        }
        refusals_without_requester = {"acceptance_requested_by_id": None}
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            gaps = Gap.objects.using(APP).filter(pk=a.gap.pk)
            for constraint, changes in (*refusals.items(), ("gap_acceptance_complete", refusals_without_requester)):
                with self.subTest(constraint, changes=changes), self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    gaps.update(**changes)
            with self.assertRaisesMessage(IntegrityError, "gap_acceptance_complete"), transaction.atomic(using=APP):
                gaps.update(accepted_at=None)
            gaps.update(status_id=a.accepted_status.id)
            self.assertEqual(gaps.get().status_id, a.accepted_status.id)
            with self.assertRaisesMessage(IntegrityError, "needs an acceptance by a second person"), transaction.atomic(using=APP):
                gaps.update(accepted_by_id=None, accepted_at=None)
            with self.assertRaisesMessage(IntegrityError, "needs an acceptance by a second person"), transaction.atomic(using=APP):
                a.create(
                    Gap,
                    tenant_obligation_id=a.entry.id,
                    title="Accepted by nobody",
                    severity_id=a.risk.id,
                    source_id=a.gap_source.id,
                    status_id=a.accepted_status.id,
                    identified_by_id=a.user_id,
                )

    def test_the_assessment_history_is_append_only_even_with_the_hatch_set(self) -> None:
        a = self.a
        with self.assertRaises(AppendOnlyRefused):
            a.assessment.save(using=APP)
        with self.assertRaises(AppendOnlyRefused):
            a.assessment.delete(using=APP)
        for hatch in ("", "SET LOCAL cw.maintenance = 'on'"):
            for statement in (
                "UPDATE compliance_assessment SET rationale = 'rewritten' WHERE id = %s",
                "DELETE FROM compliance_assessment WHERE id = %s",
            ):
                with self.subTest(statement, hatch=hatch), transaction.atomic(using=APP):
                    tenancy.activate(a.tenant.id, using=APP)
                    with connections[APP].cursor() as cursor, self.assertRaisesMessage(DatabaseError, "append-only"), transaction.atomic(using=APP):
                        if hatch:
                            cursor.execute(hatch)
                        cursor.execute(statement, [a.assessment.id])
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            self.assertEqual(ComplianceAssessment.objects.using(APP).get().rationale, "Reconciled daily.")

    def test_a_link_is_removed_by_a_stamp_never_deleted_and_one_live_link_per_item(self) -> None:
        a = self.a
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            with self.assertRaises(ValidationError) as refused:
                a.link.delete(using=APP)
            self.assertEqual(refused.exception.code, "remove_not_delete")
            live = {
                "tenant_obligation_id": a.entry.id,
                "internal_item_id": a.organisation.item.id,
                "label": "Custody policy again",
                "created_by_id": a.user_id,
            }
            with self.assertRaisesMessage(IntegrityError, "internal_link_live_unique"), transaction.atomic(using=APP):
                a.create(InternalLink, **live)
            InternalLink.objects.using(APP).filter(pk=a.link.pk).update(removed_at=timezone.now())
            a.create(InternalLink, **live)
            self.assertEqual(InternalLink.objects.using(APP).count(), 2)

    def test_one_entry_per_obligation_one_scope_row_per_entity_and_product_one_version_number(self) -> None:
        a = self.a
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            entity_row = {
                "tenant_obligation_id": a.entry.id,
                "org_unit_id": a.organisation.entity.id,
                "compliance_status_id": a.status.id,
            }
            a.create(TenantObligationScope, **entity_row)
            attempts: dict[str, Any] = {
                "tenant_obligation_unique": lambda: a.create(
                    TenantObligation, obligation_id=a.entry.obligation_id, compliance_status_id=a.status.id
                ),
                "tenant_obligation_scope_unique": lambda: a.create(TenantObligationScope, **entity_row),
                "tenant_obligation_scope_one_owner_kind": lambda: TenantObligationScope.objects.using(APP)
                .filter(pk=a.scope.pk)
                .update(owner_team_id=a.team.id),
                "gap_one_owner_kind": lambda: Gap.objects.using(APP).filter(pk=a.gap.pk).update(owner_team_id=a.team.id),
                "interpretation_version_unique": lambda: a.create(
                    Interpretation, tenant_obligation_id=a.entry.id, version_number=1, body="Again.", author_id=a.user_id
                ),
            }
            for constraint, attempt in attempts.items():
                with self.subTest(constraint), self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    attempt()


class EnsureRegisterEntry(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        _seed_library()
        self.tenant = factories.tenant(slug="entry-a")
        self.other = factories.tenant(slug="entry-b")
        self.officer = factories.user_actor(label="Officer")
        act = library_testing.instrument(key="entry-act", regime="regime:securities")
        self.obligation = library_testing.obligation(act, key="entry-duty")
        with transaction.atomic():
            tenancy.activate(self.other.id)
            private_act = library_testing.instrument(key="entry-private-act", regime="regime:securities", owner_tenant=self.other)
            self.private = library_testing.obligation(private_act, key="entry-private-duty", owner_tenant=self.other)

    def _ensure(self, obligation_id: uuid.UUID) -> TenantObligation:
        tenancy.activate(self.tenant.id)
        return logic.ensure_register_entry(tenant_id=self.tenant.id, obligation_id=obligation_id, actor=self.officer)

    def _created_events(self) -> list[AuditEvent]:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            return list(AuditEvent.objects.filter(action=logic.ENTRY_CREATED))

    def test_the_first_write_creates_the_entry_with_one_audit_event_and_the_next_reuses_it(self) -> None:
        with transaction.atomic():
            entry = self._ensure(self.obligation.id)
            again = self._ensure(self.obligation.id)
        self.assertEqual(again.id, entry.id)
        self.assertEqual(entry.applicability, Applicability.NOT_ASSESSED.value)
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            self.assertEqual(ComplianceStatus.objects.get(pk=entry.compliance_status_id).kind, "not_assessed")
        (event,) = self._created_events()
        self.assertEqual((event.subject_type, event.subject_id, event.tenant_id), ("tenant_obligation", entry.id, self.tenant.id))
        self.assertEqual(event.after, {"obligationId": str(self.obligation.id), "applicability": "not_assessed"})

    def test_the_entry_and_its_audit_event_roll_back_together(self) -> None:
        with self.assertRaises(RuntimeError), transaction.atomic():
            self._ensure(self.obligation.id)
            raise RuntimeError("the write that needed the entry failed")
        self.assertEqual(self._created_events(), [])
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            self.assertFalse(TenantObligation.objects.exists())

    def test_another_banks_private_obligation_is_not_found(self) -> None:
        with self.assertRaises(ValidationError) as refused, transaction.atomic():
            self._ensure(self.private.id)
        self.assertEqual(refused.exception.code, "not_found")
        self.assertEqual(self._created_events(), [])

    def test_two_first_writes_at_once_create_one_entry(self) -> None:
        """Two cw_app sessions: the first creates and holds its transaction until the
        second waits on the unique key, then commits; the second reads the first's entry."""
        created = threading.Event()
        second_pid: list[int] = []

        def session(work: Any) -> uuid.UUID:
            connections[DEFAULT_DB_ALIAS] = connections.create_connection(APP)
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT current_user")
                        assert cursor.fetchone()[0] == connections.settings[APP]["USER"], "a racing session must be cw_app"
                    return work()
            finally:
                connections[DEFAULT_DB_ALIAS].close()

        def lead() -> uuid.UUID:
            entry = self._ensure(self.obligation.id)
            created.set()
            hold_until_waiting_on_me(second_pid)
            return entry.id

        def follow() -> uuid.UUID:
            second_pid.append(backend_pid())
            if not created.wait(RACE_WAIT_SECONDS):
                raise AssertionError("the first session never created the entry")
            return self._ensure(self.obligation.id).id

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(session, lead), pool.submit(session, follow)
            self.assertEqual(first.result(), second.result())
        self.assertEqual(len(self._created_events()), 1)


class _EntryCreation(ast.NodeVisitor):
    """Lines that call `TenantObligation(...)` or a create method on a chain that starts at
    `TenantObligation`. Over-approximates, so it fails closed."""

    CREATE_METHODS = frozenset({"create", "bulk_create", "get_or_create", "update_or_create"})

    def __init__(self) -> None:
        self.lines: list[int] = []

    def visit_Call(self, node: ast.Call) -> None:
        target = node.func
        if isinstance(target, ast.Name) and target.id == "TenantObligation":
            self.lines.append(node.lineno)
        elif isinstance(target, ast.Attribute) and target.attr in self.CREATE_METHODS and self._starts_at_entry(target.value):
            self.lines.append(node.lineno)
        self.generic_visit(node)

    def _starts_at_entry(self, node: ast.expr) -> bool:
        while isinstance(node, ast.Attribute | ast.Call):
            node = node.value if isinstance(node, ast.Attribute) else node.func
        return isinstance(node, ast.Name) and node.id == "TenantObligation"


class TheEntryHasOneCreator(SimpleTestCase):
    def test_only_ensure_register_entry_creates_a_register_entry(self) -> None:
        """A second creator would write an entry without its `register.entry_created`
        event, or with a status other than the bank's default."""
        offenders = []
        for path in production_modules():
            rel = path.relative_to(APPS_DIR).as_posix()
            if rel == "register/logic.py":
                continue
            visitor = _EntryCreation()
            visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
            offenders += [f"{rel}:{line}" for line in visitor.lines]
        self.assertEqual(
            offenders, [], f"Create a register entry through apps.register.logic.ensure_register_entry(), not at {offenders}."
        )

    def test_the_guard_sees_the_one_creator(self) -> None:
        visitor = _EntryCreation()
        visitor.visit(ast.parse((APPS_DIR / "register" / "logic.py").read_text(encoding="utf-8")))
        self.assertEqual(len(visitor.lines), 1)

"""Guard: audit on write (playbook 5, 4.3, AUD-01, AC-AUD1).

Three things are enumerated and demanded:

1. Every non-GET operation Ninja registered must be exercised by a scenario test: its
   operation id appears in that app's tests_scenarios.py. A mutating route with no
   scenario fails here.
2. The scenario base client (`AuditAssertingClient`) fails any 2xx mutating request that
   wrote no audit_event row. Proven on two throwaway views below.
3. `record()` writes the audit event and the outbox event in the same transaction,
   refuses to run outside one, and the append-only rule holds in Python and in the
   database (trigger), with the `cw.maintenance` escape hatch working as documented.
4. `batched()` writes, for many `record()` calls, the very rows those calls write one by
   one, in two INSERTs, in the order recorded, under the same triggers, and nothing when
   its block fails.

Proven to fail 2026-09-19 by making the throwaway "audited" view skip record(): the
client raised naming the route and AC-AUD1.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections, transaction
from django.http import HttpRequest, JsonResponse
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType, AppendOnlyRefused, NotInTransaction, batched, record
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.routes import iter_operations
from apps.shared.testing import AuditAssertingClient
from config.api import api

APPS_DIR = Path(__file__).resolve().parent.parent


@csrf_exempt
def unaudited_view(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"ok": True}, status=201)


@csrf_exempt
def audited_view(request: HttpRequest) -> JsonResponse:
    with transaction.atomic():
        record(
            action="probe.created",
            actor=Actor.system("test"),
            subject_type="probe",
            subject_id=uuid.uuid4(),
            subject_title="probe",
            summary="created by the guard test",
            tenant_id=None,
        )
    return JsonResponse({"ok": True}, status=201)


urlpatterns = [
    path("probe/unaudited/", unaudited_view),
    path("probe/audited/", audited_view),
]


class MutatingRoutesHaveScenarios(TestCase):
    def test_every_mutating_operation_is_named_in_a_scenario_test(self) -> None:
        scenario_sources = "\n".join(
            p.read_text(encoding="utf-8") for p in APPS_DIR.glob("*/tests_scenarios.py")
        )
        uncovered: list[str] = []
        mutating = [op for op in iter_operations(api) if op.method != "GET"]
        for operation in mutating:
            if operation.operation_id not in scenario_sources:
                uncovered.append(f"{operation.method} {operation.path} ({operation.operation_id})")
        self.assertEqual(
            uncovered,
            [],
            "Mutating routes with no scenario test naming their operation id:\n  " + "\n  ".join(uncovered),
        )


@override_settings(ROOT_URLCONF="apps.shared.tests_audit_on_write")
class AuditAssertingClientBites(TestCase):
    client_class = AuditAssertingClient

    def test_a_mutating_request_that_writes_no_audit_row_fails(self) -> None:
        with self.assertRaises(AssertionError) as caught:
            self.client.post("/probe/unaudited/")
        self.assertIn("AC-AUD1", str(caught.exception))

    def test_a_mutating_request_that_records_passes(self) -> None:
        response = self.client.post("/probe/audited/")
        self.assertEqual(response.status_code, 201)

    def test_reads_are_not_asserted(self) -> None:
        response = self.client.get("/probe/unaudited/")
        self.assertEqual(response.status_code, 201)


class RecordWritesBothRowsInOneTransaction(TestCase):
    def test_record_writes_audit_and_outbox_rows(self) -> None:
        tenant = factories.tenant()
        subject = uuid.uuid4()
        with transaction.atomic():
            tenancy.activate(tenant.id)
            event = record(
                action="case.triaged",
                actor=factories.user_actor(label="Ada"),
                subject_type="case",
                subject_id=subject,
                subject_title="Case 1",
                summary="Triaged.",
                tenant_id=tenant.id,
                before={"status": "new"},
                after={"status": "assigned"},
            )
            self.assertEqual(AuditEvent.objects.filter(pk=event.pk).count(), 1)
            outbox = OutboxEvent.objects.get(audit_event=event)
        self.assertEqual(outbox.topic, "case.triaged")
        self.assertEqual(outbox.tenant_id, tenant.id)
        self.assertEqual(outbox.payload["auditEventId"], str(event.id))
        self.assertEqual(event.actor_type, ActorType.USER.value)
        self.assertEqual(event.actor_label, "Ada")

    def test_record_refuses_to_run_outside_a_transaction(self) -> None:
        # TestCase wraps each test in a transaction; step out of it on a fresh connection
        # state by checking the guard's own condition directly.
        connection = connections[DEFAULT_DB_ALIAS]
        self.assertTrue(connection.in_atomic_block)
        original = connection.in_atomic_block
        connection.in_atomic_block = False
        try:
            with self.assertRaises(NotInTransaction):
                record(
                    action="x",
                    actor=Actor.system(),
                    subject_type="x",
                    subject_id=None,
                    subject_title="",
                    summary="",
                    tenant_id=None,
                )
        finally:
            connection.in_atomic_block = original

    def test_a_failed_write_rolls_back_the_audit_row_too(self) -> None:
        before = AuditEvent.objects.count()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                record(
                    action="probe.failed",
                    actor=Actor.system(),
                    subject_type="probe",
                    subject_id=uuid.uuid4(),
                    subject_title="",
                    summary="",
                    tenant_id=None,
                )
                raise RuntimeError("the write after the audit row failed")
        self.assertEqual(AuditEvent.objects.count(), before)


class AppendOnlyHolds(TestCase):
    def _event(self) -> AuditEvent:
        return record(
            action="probe",
            actor=Actor.system(),
            subject_type="probe",
            subject_id=uuid.uuid4(),
            subject_title="",
            summary="",
            tenant_id=None,
        )

    def test_python_refuses_update_and_delete(self) -> None:
        event = self._event()
        event.summary = "changed"
        with self.assertRaises(AppendOnlyRefused):
            event.save()
        with self.assertRaises(AppendOnlyRefused):
            event.delete()
        with self.assertRaises(AppendOnlyRefused):
            AuditEvent.objects.filter(pk=event.pk).update(summary="changed")
        with self.assertRaises(AppendOnlyRefused):
            AuditEvent.objects.filter(pk=event.pk).delete()

    def test_the_database_trigger_refuses_update_and_delete(self) -> None:
        event = self._event()
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            with self.assertRaises(DatabaseError) as caught:
                with transaction.atomic():
                    cursor.execute("UPDATE audit_event SET summary = 'x' WHERE id = %s", [str(event.id)])
            self.assertIn("append-only", str(caught.exception))
            with self.assertRaises(DatabaseError):
                with transaction.atomic():
                    cursor.execute("DELETE FROM audit_event WHERE id = %s", [str(event.id)])

    def test_the_maintenance_escape_hatch_states_intent(self) -> None:
        event = self._event()
        with transaction.atomic(), connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SET LOCAL cw.maintenance = 'on'")
            cursor.execute("UPDATE audit_event SET summary = 'fixed' WHERE id = %s", [str(event.id)])
        self.assertEqual(AuditEvent.objects.get(pk=event.pk).summary, "fixed")

    def test_outbox_delivery_state_may_change_but_the_payload_may_not(self) -> None:
        event = self._event()
        outbox = OutboxEvent.objects.get(audit_event=event)
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                "UPDATE outbox_event SET published_at = now(), attempts = 1 WHERE id = %s", [str(outbox.id)]
            )
            with self.assertRaises(DatabaseError) as caught:
                with transaction.atomic():
                    cursor.execute("UPDATE outbox_event SET topic = 'x' WHERE id = %s", [str(outbox.id)])
            self.assertIn("append-only", str(caught.exception))
            with self.assertRaises(DatabaseError):
                with transaction.atomic():
                    cursor.execute("DELETE FROM outbox_event WHERE id = %s", [str(outbox.id)])
        self.assertIsNotNone(OutboxEvent.objects.get(pk=outbox.pk).published_at)


class BatchedRecordWritesTheSameRows(TestCase):
    """`batched()` is `record()` for many subjects at once: the rows are the ones each call
    writes alone, and every guarantee of the single path holds for them."""

    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.actor = factories.user_actor(label="Ada")
        self.step_up = uuid.uuid4()

    def _calls(self) -> list[dict[str, object]]:
        """A tenant row, a library row written from the tenant's session (it crosses the
        zones), and one with its own topic and payload."""
        return [
            {"action": "case.triaged", "subject_type": "case", "tenant_id": self.tenant.id, "before": {"status": "new"}, "after": {"status": "assigned"}},
            {"action": "library.probe", "subject_type": "probe", "tenant_id": None, "step_up_assertion_id": self.step_up},
            {"action": "case.closed", "subject_type": "case", "tenant_id": self.tenant.id, "topic": "case.done", "payload": {"caseId": "c-1"}},
        ]

    def _record(self, call: dict[str, object], subject: uuid.UUID) -> None:
        record(actor=self.actor, subject_id=subject, subject_title="Case 1", summary="Changed.", **call)  # type: ignore[arg-type]

    def _rows(self, subjects: list[uuid.UUID]) -> list[tuple[dict[str, object], dict[str, object]]]:
        """Each subject's audit and outbox row, every column but the rows' own ids, times and
        subject, each of which must point at its own. A library row is read by every zone."""
        rows = []
        for subject in subjects:
            event = AuditEvent.objects.get(subject_id=subject)
            outbox = OutboxEvent.objects.get(audit_event=event)
            payload = dict(outbox.payload)
            if "auditEventId" in payload:
                self.assertEqual((payload.pop("auditEventId"), payload.pop("subjectId")), (str(event.id), str(subject)))
            skip = {"id", "created", "audit_event_id", "payload", "subject_id"}
            rows.append(
                (
                    {f.attname: getattr(event, f.attname) for f in AuditEvent._meta.concrete_fields if f.attname not in skip},
                    {f.attname: getattr(outbox, f.attname) for f in OutboxEvent._meta.concrete_fields if f.attname not in skip} | {"payload": payload},
                )
            )
        return rows

    def test_the_rows_are_the_ones_record_writes_one_by_one(self) -> None:
        tenancy.activate(self.tenant.id)
        alone = [uuid.uuid4() for _ in self._calls()]
        together = [uuid.uuid4() for _ in self._calls()]
        for call, subject in zip(self._calls(), alone, strict=True):
            self._record(call, subject)
        with batched():
            for call, subject in zip(self._calls(), together, strict=True):
                self._record(call, subject)
        self.assertEqual(self._rows(together), self._rows(alone))

    def test_many_events_are_one_audit_insert_and_one_outbox_insert_in_the_order_recorded(self) -> None:
        tenancy.activate(self.tenant.id)
        subjects = [uuid.uuid4() for _ in range(50)]
        with CaptureQueriesContext(connections[DEFAULT_DB_ALIAS]) as captured:
            with batched():
                for subject in subjects:
                    self.assertIsNone(record(actor=self.actor, subject_id=subject, subject_title="", summary="", action="probe.many", subject_type="probe", tenant_id=self.tenant.id))
                self.assertEqual(captured.captured_queries, [])
        inserts = [query["sql"].split('"')[1] for query in captured.captured_queries if query["sql"].startswith("INSERT")]
        self.assertEqual(inserts, ["audit_event", "outbox_event"])
        self.assertEqual([event.subject_id for event in AuditEvent.objects.filter(action="probe.many").order_by("created", "id")], subjects)
        self.assertEqual(
            [outbox.audit_event.subject_id for outbox in OutboxEvent.objects.filter(topic="probe.many").select_related("audit_event").order_by("created", "id")],
            subjects,
        )

    def test_a_block_that_raises_writes_nothing(self) -> None:
        tenancy.activate(self.tenant.id)
        before = (AuditEvent.objects.count(), OutboxEvent.objects.count())
        with self.assertRaises(RuntimeError):
            with transaction.atomic(), batched():
                self._record(self._calls()[0], uuid.uuid4())
                raise RuntimeError("the write after the audit row failed")
        self.assertEqual((AuditEvent.objects.count(), OutboxEvent.objects.count()), before)

    def test_a_block_inside_another_joins_it(self) -> None:
        tenancy.activate(self.tenant.id)
        subjects = [uuid.uuid4(), uuid.uuid4()]
        with batched():
            self._record(self._calls()[0], subjects[0])
            with batched():
                self._record(self._calls()[0], subjects[1])
            self.assertFalse(AuditEvent.objects.filter(subject_id__in=subjects).exists())
        self.assertEqual(AuditEvent.objects.filter(subject_id__in=subjects).count(), 2)

    def test_batched_rows_are_append_only_in_the_database(self) -> None:
        tenancy.activate(self.tenant.id)
        subject = uuid.uuid4()
        with batched():
            self._record(self._calls()[0], subject)
        event = AuditEvent.objects.get(subject_id=subject)
        outbox = OutboxEvent.objects.get(audit_event=event)
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            for statement, row in (("UPDATE audit_event SET summary = 'x' WHERE id = %s", event.id), ("UPDATE outbox_event SET topic = 'x' WHERE id = %s", outbox.id)):
                with self.assertRaises(DatabaseError) as caught:
                    with transaction.atomic():
                        cursor.execute(statement, [str(row)])
                self.assertIn("append-only", str(caught.exception))

    def test_a_block_that_ends_outside_a_transaction_is_refused(self) -> None:
        connection = connections[DEFAULT_DB_ALIAS]
        original = connection.in_atomic_block
        try:
            with self.assertRaises(NotInTransaction):
                with batched():
                    self._record(self._calls()[0], uuid.uuid4())
                    connection.in_atomic_block = False
        finally:
            connection.in_atomic_block = original

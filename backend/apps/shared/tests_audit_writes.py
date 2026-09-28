"""`record()`'s mechanics after ADR 0063 (perf-audit-writes): the audit row and its outbox row
go in as one statement, and a savepoint is taken only when the write crosses the zones.

What must not change, and is proven here:

1. The rows are the rows the two statements wrote before: every column, the order recorded,
   the default and the caller's own payload, the tenant the outbox row carries.
2. A write that fails takes its audit and outbox rows with it, and a failed audit insert
   dooms the caller's transaction: nothing can commit the change without its row.
3. A write that crosses the zones still runs in its savepoint inside `platform_zone()`, so
   a failed insert leaves the tenant as it was and the caller sees the insert's own error.
4. The append-only triggers still refuse UPDATE and DELETE on rows written this way.
5. The compliance lint still refuses a write to either table outside `record()`.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
import tempfile
import uuid
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

from django.db import DEFAULT_DB_ALIAS, DatabaseError, DataError, connections, transaction
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from apps.shared import factories, tenancy
from apps.shared.audit import Actor, batched, record
from apps.shared.models import AuditEvent, OutboxEvent

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compliance_check.py"


def _write_before(calls: list[dict[str, Any]]) -> None:
    """The mechanics `record()` had before ADR 0063, kept here as the reference: per run of
    rows in one zone, an audit INSERT and an outbox INSERT inside a savepoint, the run that
    crosses the zones inside `platform_zone()`."""
    crossing = tenancy.database_tenant_id() is not None
    for crosses_zones, group in itertools.groupby(calls, key=lambda call: crossing and call["tenant_id"] is None):
        rows = list(group)
        events = [AuditEvent(id=event_id, **row["fields"]) for event_id, row in zip(sorted(uuid.uuid4() for _ in rows), rows, strict=True)]
        outbox = [
            OutboxEvent(
                id=outbox_id,
                tenant_id=row["tenant_id"],
                audit_event=event,
                topic=row["topic"],
                payload=row["payload"] or {"auditEventId": str(event.id), "subjectId": str(event.subject_id) if event.subject_id else None},
            )
            for outbox_id, event, row in zip(sorted(uuid.uuid4() for _ in rows), events, rows, strict=True)
        ]
        with tenancy.platform_zone() if crosses_zones else nullcontext(), transaction.atomic():
            AuditEvent.objects.bulk_create(events)
            OutboxEvent.objects.bulk_create(outbox)


class TheRowsAreTheRowsWrittenBefore(TestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.actor = factories.user_actor(label="Ada")
        self.step_up = uuid.uuid4()

    def _calls(self, run: uuid.UUID) -> list[dict[str, Any]]:
        """A tenant row, a library row from the bank's session (it crosses the zones), a row
        with its own topic and payload, and one with no subject. `run` tells two writes of
        the same calls apart."""
        step_up = self.step_up
        rows = [
            ("case.triaged", "case", uuid.uuid4(), self.tenant.id, {"status": "new"}, {"status": "assigned"}, None, None, None),
            ("library.probe", "obligation", uuid.uuid4(), None, {}, {"key": "o-1"}, step_up, None, None),
            ("case.closed", "case", uuid.uuid4(), self.tenant.id, {}, {}, None, "case.done", {"caseId": "c-1"}),
            ("session.signed_out", "user_session", None, self.tenant.id, {}, {}, None, None, None),
        ]
        return [
            {
                "tenant_id": tenant_id,
                "topic": topic or action,
                "payload": payload,
                "fields": {
                    "tenant_id": tenant_id,
                    "actor_type": self.actor.kind.value,
                    "actor_id": self.actor.id,
                    "actor_label": self.actor.label,
                    "action": action,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "subject_title": f"{run}",
                    "summary": "Changed.",
                    "before": before,
                    "after": after,
                    "step_up_assertion_id": step_up_id,
                    "request_id": "",
                },
            }
            for action, subject_type, subject_id, tenant_id, before, after, step_up_id, topic, payload in rows
        ]

    def _record(self, call: dict[str, Any]) -> None:
        fields = call["fields"]
        record(
            action=fields["action"],
            actor=Actor(kind=self.actor.kind, id=fields["actor_id"], label=fields["actor_label"]),
            subject_type=fields["subject_type"],
            subject_id=fields["subject_id"],
            subject_title=fields["subject_title"],
            summary=fields["summary"],
            tenant_id=call["tenant_id"],
            before=fields["before"],
            after=fields["after"],
            step_up_assertion_id=fields["step_up_assertion_id"],
            topic=None if call["topic"] == fields["action"] else call["topic"],
            payload=call["payload"],
        )

    def _rows(self, run: uuid.UUID) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Every column of each audit row and its outbox row in the order the tables read
        them, but for the rows' own ids and times, which are fresh on every write; the
        default payload's ids must point at their own rows."""
        rows = []
        for event in AuditEvent.objects.filter(subject_title=str(run)).order_by("created", "id"):
            outbox = OutboxEvent.objects.get(audit_event=event)
            payload = dict(outbox.payload)
            if "auditEventId" in payload:
                self.assertEqual(payload.pop("auditEventId"), str(event.id))
                self.assertEqual(payload.pop("subjectId"), str(event.subject_id) if event.subject_id else None)
            self.assertLessEqual(event.created, outbox.created)
            skip = {"id", "created", "audit_event_id", "payload", "subject_id", "subject_title"}
            rows.append(
                (
                    {f.attname: getattr(event, f.attname) for f in AuditEvent._meta.concrete_fields if f.attname not in skip},
                    {f.attname: getattr(outbox, f.attname) for f in OutboxEvent._meta.concrete_fields if f.attname not in skip} | {"payload": payload},
                )
            )
        return rows

    def test_record_writes_every_column_as_the_two_statements_did(self) -> None:
        tenancy.activate(self.tenant.id)
        before, after = uuid.uuid4(), uuid.uuid4()
        _write_before(self._calls(before))
        for call in self._calls(after):
            self._record(call)
        self.assertEqual(len(self._rows(after)), 4)
        self.assertEqual(self._rows(after), self._rows(before))

    def test_a_batch_writes_every_column_as_the_two_statements_did(self) -> None:
        tenancy.activate(self.tenant.id)
        before, after = uuid.uuid4(), uuid.uuid4()
        _write_before(self._calls(before))
        with batched():
            for call in self._calls(after):
                self._record(call)
        self.assertEqual(self._rows(after), self._rows(before))

    def test_the_rows_read_back_in_the_order_recorded(self) -> None:
        tenancy.activate(self.tenant.id)
        run = uuid.uuid4()
        calls = self._calls(run)
        for call in calls:
            self._record(call)
        self.assertEqual(
            [event.action for event in AuditEvent.objects.filter(subject_title=str(run)).order_by("created", "id")],
            [call["fields"]["action"] for call in calls],
        )

    def test_the_default_payload_names_the_audit_row_and_the_subject(self) -> None:
        subject = uuid.uuid4()
        event = record(action="case.triaged", actor=self.actor, subject_type="case", subject_id=subject, subject_title="", summary="", tenant_id=self.tenant.id)
        self.assertEqual(OutboxEvent.objects.get(audit_event=event).payload, {"auditEventId": str(event.id), "subjectId": str(subject)})

    def test_the_returned_row_is_the_stored_row_and_is_not_saved_again(self) -> None:
        event = record(action="case.triaged", actor=self.actor, subject_type="case", subject_id=uuid.uuid4(), subject_title="", summary="", tenant_id=self.tenant.id)
        stored = AuditEvent.objects.get(pk=event.pk)
        self.assertEqual((event.action, event.created), (stored.action, stored.created))
        self.assertFalse(event._state.adding)
        self.assertEqual(event._state.db, DEFAULT_DB_ALIAS)


class OneStatementAndASavepointOnlyAcrossTheZones(TestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()

    def _record(self, tenant_id: uuid.UUID | None, subject_type: str = "probe") -> AuditEvent:
        return record(action="probe.write", actor=Actor.system(), subject_type=subject_type, subject_id=uuid.uuid4(), subject_title="", summary="", tenant_id=tenant_id)

    def test_a_tenant_write_is_one_statement_with_no_savepoint(self) -> None:
        tenancy.activate(self.tenant.id)
        with CaptureQueriesContext(connections[DEFAULT_DB_ALIAS]) as captured:
            self._record(self.tenant.id)
        self.assertEqual(len(captured.captured_queries), 1)
        statement = captured.captured_queries[0]["sql"]
        self.assertTrue(statement.startswith("WITH"), statement)
        self.assertIn('INSERT INTO "audit_event"', statement)
        self.assertIn('INSERT INTO "outbox_event"', statement)

    def test_a_platform_write_outside_any_bank_reads_the_zone_and_takes_no_savepoint(self) -> None:
        tenancy.clear_tenant()
        with CaptureQueriesContext(connections[DEFAULT_DB_ALIAS]) as captured:
            self._record(None)
        statements = [query["sql"] for query in captured.captured_queries]
        self.assertEqual(len(statements), 2, statements)
        self.assertIn("current_setting", statements[0])
        self.assertFalse(any("SAVEPOINT" in statement for statement in statements), statements)

    def test_a_write_that_crosses_the_zones_keeps_its_savepoint(self) -> None:
        tenancy.activate(self.tenant.id)
        with CaptureQueriesContext(connections[DEFAULT_DB_ALIAS]) as captured:
            event = self._record(None)
        statements = [query["sql"] for query in captured.captured_queries]
        savepoint = next(index for index, statement in enumerate(statements) if statement.startswith("SAVEPOINT"))
        insert = next(index for index, statement in enumerate(statements) if statement.startswith("WITH"))
        release = next(index for index, statement in enumerate(statements) if statement.startswith("RELEASE SAVEPOINT"))
        self.assertLess(savepoint, insert)
        self.assertLess(insert, release)
        self.assertEqual(sum(statement.startswith("WITH") for statement in statements), 1)
        self.assertIsNone(AuditEvent.objects.get(pk=event.pk).tenant_id)
        self.assertEqual(tenancy.database_tenant_id(), self.tenant.id)

    def test_a_crossing_write_that_fails_rolls_back_to_its_savepoint_and_puts_the_bank_back(self) -> None:
        tenancy.activate(self.tenant.id)
        with self.assertRaises(DataError):
            self._record(None, subject_type="x" * 65)
        # The caller sees the insert's own error, and the bank is back on.
        self.assertEqual(tenancy.database_tenant_id(), self.tenant.id)


class AFailingWriteTakesItsRowsWithIt(TestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        tenancy.activate(self.tenant.id)

    def _counts(self) -> tuple[int, int]:
        return AuditEvent.objects.count(), OutboxEvent.objects.count()

    def _record(self, subject_type: str = "probe") -> None:
        record(action="probe.write", actor=Actor.system(), subject_type=subject_type, subject_id=uuid.uuid4(), subject_title="", summary="", tenant_id=self.tenant.id)

    def test_a_write_that_fails_after_record_rolls_back_both_rows(self) -> None:
        before = self._counts()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self._record()
                raise RuntimeError("the write after the audit row failed")
        self.assertEqual(self._counts(), before)

    def test_a_batch_that_fails_rolls_back_both_rows(self) -> None:
        before = self._counts()
        with self.assertRaises(RuntimeError):
            with transaction.atomic(), batched():
                self._record()
                self._record()
                raise RuntimeError("the write after the audit rows failed")
        self.assertEqual(self._counts(), before)

    def test_a_failed_audit_insert_leaves_no_half_and_dooms_the_change(self) -> None:
        """No savepoint around a same-zone insert: a caller that swallows the error cannot go
        on to commit the change without its audit row, because the database refuses every
        statement until the transaction rolls back."""
        before = self._counts()
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                changed = factories.tenant()
                tenancy.activate(self.tenant.id)
                try:
                    self._record(subject_type="x" * 65)
                except DataError:
                    pass
                AuditEvent.objects.count()  # the next statement of the swallowed failure
        self.assertEqual(self._counts(), before)
        tenancy.activate(self.tenant.id)
        from apps.shared.models import Tenant

        self.assertFalse(Tenant.objects.filter(pk=changed.pk).exists())


class TheTriggersStillRefuse(TestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        tenancy.activate(self.tenant.id)

    def _assert_refused(self, event: AuditEvent) -> None:
        """Read in the row's own zone, so the statement reaches the row and it is the trigger,
        not the row-level security, that refuses it."""
        if event.tenant_id is None:
            tenancy.clear_tenant()
        outbox = OutboxEvent.objects.get(audit_event=event)
        statements = (
            ("UPDATE audit_event SET summary = 'x' WHERE id = %s", event.id),
            ("DELETE FROM audit_event WHERE id = %s", event.id),
            ("UPDATE outbox_event SET topic = 'x' WHERE id = %s", outbox.id),
            ("UPDATE outbox_event SET payload = '{}'::jsonb WHERE id = %s", outbox.id),
            ("DELETE FROM outbox_event WHERE id = %s", outbox.id),
        )
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            for statement, row in statements:
                with self.subTest(statement=statement):
                    with self.assertRaises(DatabaseError) as caught:
                        with transaction.atomic():
                            cursor.execute(statement, [str(row)])
                    self.assertIn("append-only", str(caught.exception))

    def test_a_single_write_is_append_only(self) -> None:
        self._assert_refused(record(action="probe.write", actor=Actor.system(), subject_type="probe", subject_id=uuid.uuid4(), subject_title="", summary="", tenant_id=self.tenant.id))

    def test_a_crossing_write_is_append_only(self) -> None:
        self._assert_refused(record(action="probe.write", actor=Actor.system(), subject_type="probe", subject_id=uuid.uuid4(), subject_title="", summary="", tenant_id=None))

    def test_a_batched_write_is_append_only(self) -> None:
        subject = uuid.uuid4()
        with batched():
            record(action="probe.write", actor=Actor.system(), subject_type="probe", subject_id=subject, subject_title="", summary="", tenant_id=self.tenant.id)
        self._assert_refused(AuditEvent.objects.get(subject_id=subject))


class TheLintStillRefusesAWriteOutsideRecord(SimpleTestCase):
    """The audit-door rule of scripts/compliance_check.py, over planted files in a temporary
    tree, never over the source tree."""

    PLANTED = {
        # Allowed: the door itself, a migration, a test.
        "apps/shared/audit.py": "AuditEvent.objects.bulk_create(rows)\n",
        "apps/shared/migrations/0009_fix.py": "SQL = 'INSERT INTO audit_event (id) VALUES (1)'\n",
        "apps/shared/tests_probe.py": "OutboxEvent.objects.create(topic='x')\n",
        # Refused: every way past record() into either table.
        "apps/cases/logic.py": "AuditEvent.objects.create(action='case.closed')\n",
        "apps/register/logic.py": "OutboxEvent.objects.bulk_create(rows)\n",
        "apps/watch/logic.py": "row = AuditEvent(action='x')\n",
        "apps/home/logic.py": "models.OutboxEvent.objects.get_or_create(topic='x')\n",
        "apps/collab/logic.py": "SQL = 'insert into \"outbox_event\" (id) values (1)'\n",
        "apps/proposals/logic.py": "SQL = 'INSERT INTO audit_event (id) VALUES (1)'  # compliance: audit-door because\n",
        "apps/reports/logic.py": "AuditEvent.objects.update_or_create(action='x')\n",
        "apps/search/logic.py": "SQL = 'INSERT INTO \"public\".\"audit_event\" (id) VALUES (1)'\n",
    }

    def _lint(self) -> ModuleType:
        spec = importlib.util.spec_from_file_location("compliance_check_audit_door", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {spec.name: module}):
            spec.loader.exec_module(module)
        return module

    def test_only_record_may_write_the_audit_and_outbox_tables(self) -> None:
        lint = self._lint()
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            paths = []
            for rel, source in self.PLANTED.items():
                path = base / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
                paths.append(path)
            with mock.patch.object(lint, "BACKEND", base):
                findings = [finding for finding in lint.scan(paths) if finding.rule == "audit-door"]
            flagged = sorted({finding.path.relative_to(base).as_posix() for finding in findings})
        self.assertEqual(
            flagged,
            ["apps/cases/logic.py", "apps/collab/logic.py", "apps/home/logic.py", "apps/proposals/logic.py", "apps/register/logic.py", "apps/reports/logic.py", "apps/search/logic.py", "apps/watch/logic.py"],
        )


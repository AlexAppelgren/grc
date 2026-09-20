"""The one ordered cursor over `outbox_event` (chunk 5 ruling 9; AUD-01, CAS-01, NFR-01,
NFR-04).

`record()` writes an outbox row beside its audit row; `apps/shared/outbox.py` is the only
thing that delivers one, and these tests are what it has to satisfy:

- every pending row is delivered exactly once, in `(created, id)` order, across both
  zones: two tenants' rows and a library row interleaved come back in the order written;
- a tenant row's handlers run with that tenant activated and a library row's with no
  tenant activated, where a read of a tenant table matches nothing (NFR-S4), which is
  what chunk 7's indexing of library rows depends on;
- a handler that raises leaves its row unpublished, counts the attempt and stops the
  batch there, so nothing behind it overtakes it; after `OUTBOX_MAX_ATTEMPTS` the row is
  left failed and the cursor moves on;
- the same four failure paths hold for a library row whose handler raises a *database*
  error, which is what a real consumer's failure looks like: its savepoint takes the
  handler's half-finished writes with it and hands the batch back a usable transaction;
- neither the failure on the row nor the log line carries tenant content;
- two workers cannot deliver one row twice: the cursor row is the lock;
- the batch size, poll interval, backoff and attempt ceiling are settings with env
  overrides documented in `.env.example` and the Railway runbook;
- the beat entry exists and runs the task, the cursor writes no event of its own, and the
  only handler production code registers is chunk 5's case creation.

Proven to fail 2026-09-20 by letting a batch carry on past a failing row (the failure
tests named the row that overtook it) and by running a library row's handlers without
clearing the previous row's tenant (the zone test named the tenant that was still active),
and again by taking the savepoint back out of the library branch (all four library failure
tests raised out of `deliver_batch()` before reaching an assertion).
"""

from __future__ import annotations

import ast
import inspect
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.shared import factories, outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import AuditEvent, OutboxCursor, OutboxEvent, TenantContentLanguage
from apps.shared.tasks import deliver_outbox
from apps.shared.tenancy import is_tenant_task
from config.celery import app as celery_app

ROOT = Path(__file__).resolve().parents[3]
TOPIC = "probe.registered"
FAILING_TOPIC = "probe.refused"
DATABASE_FAILING_TOPIC = "probe.refused-by-the-database"
BEAT_ENTRY = "outbox-deliver"
SETTINGS = ("OUTBOX_BATCH_SIZE", "OUTBOX_POLL_INTERVAL_S", "OUTBOX_MAX_ATTEMPTS", "OUTBOX_RETRY_BACKOFF_S")
# A handler's exception message, standing in for the tenant content a real one would
# carry: a database error's message holds the values of the row that failed.
SECRET = "the bank's own assessment text"
# The name the database-failing handler's half-finished write takes. A second cursor row is
# a plain insert into a table with no zone and no trigger, so what the assertions see is the
# savepoint and nothing else.
HALF_FINISHED = "probe-half-finished"


def enter_zone(tenant_id: uuid.UUID | None, *, using: str = DEFAULT_DB_ALIAS) -> None:
    """Put the test's own connection in one zone, the way the cursor does: a tenant's rows
    are invisible and unwritable until the setting the policy reads holds its id."""
    with connections[using].cursor() as db_cursor:
        db_cursor.execute("SELECT set_config(%s, %s, true)", [tenancy.TENANT_SETTING, str(tenant_id or "")])


class OutboxCursorCase(TestCase):
    """Two tenants, an empty backlog and a handler registry restored after every test."""

    def setUp(self) -> None:
        # The registry is module state; a test that registers a handler leaves none behind.
        self.addCleanup(outbox._HANDLERS.clear)
        self.tenant_a = factories.tenant(slug="outbox-a")
        self.tenant_b = factories.tenant(slug="outbox-b")
        # The factories record their own writes. Deliver them (no handler is registered
        # yet, so nothing runs) so each test asserts on its own rows only.
        outbox.deliver_batch()
        self.seen: list[uuid.UUID] = []

    def remember(self, event: OutboxEvent) -> None:
        self.seen.append(event.id)

    def refuse(self, event: OutboxEvent) -> None:
        raise RuntimeError(SECRET)

    def refuse_in_the_database(self, event: OutboxEvent) -> None:
        """Write half of the work, then fail the way a consumer really fails.

        A handler talks to the database, so its failure is usually the database's: a
        constraint, a policy, a lost connection. That aborts the transaction the batch runs
        in, and everything after it — counting the attempt, marking the rows already
        delivered, moving the cursor — is refused until something rolls back. Only the
        row's own savepoint can, and the half-finished row below is how these tests see it
        happen.
        """
        OutboxCursor.objects.create(name=HALF_FINISHED)
        with connections[DEFAULT_DB_ALIAS].cursor() as db_cursor:
            db_cursor.execute("SELECT %s::uuid", [SECRET])  # invalid text: the message carries it

    def event(self, tenant_id: uuid.UUID | None, *, topic: str = TOPIC) -> OutboxEvent:
        """One pending row, written the only way a row is ever written."""
        with transaction.atomic():
            enter_zone(tenant_id)
            audit = record(
                action=topic,
                actor=Actor.system("outbox probe"),
                subject_type="probe",
                subject_id=uuid.uuid4(),
                subject_title="",
                summary="",
                tenant_id=tenant_id,
            )
            return OutboxEvent.objects.get(audit_event=audit)

    def reload(self, event: OutboxEvent) -> OutboxEvent:
        enter_zone(event.tenant_id)
        return OutboxEvent.objects.get(pk=event.pk)

    def cursor(self) -> OutboxCursor:
        return OutboxCursor.objects.get(name=outbox.CURSOR_NAME)


class RowsAreDeliveredOnceInOrder(OutboxCursorCase):
    def test_two_tenants_and_the_library_come_back_in_created_id_order(self) -> None:
        outbox.register_handler(TOPIC, self.remember)
        first = self.event(self.tenant_a.id)
        second = self.event(None)
        third = self.event(self.tenant_b.id)
        fourth = self.event(self.tenant_a.id)

        result = outbox.deliver_batch()

        self.assertEqual(self.seen, [first.id, second.id, third.id, fourth.id])
        self.assertEqual(result, outbox.BatchResult(delivered=4, failed=0))
        for event in (first, second, third, fourth):
            self.assertIsNotNone(self.reload(event).published_at)
        # Exactly once: a second pass has nothing left and runs no handler again.
        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult())
        self.assertEqual(len(self.seen), 4)

    def test_the_cursor_holds_the_last_delivered_position(self) -> None:
        outbox.register_handler(TOPIC, self.remember)
        self.event(self.tenant_a.id)
        last = self.event(None)

        outbox.deliver_batch()

        cursor = self.cursor()
        self.assertEqual(cursor.last_id, last.id)
        self.assertEqual(cursor.last_created, self.reload(last).created)
        self.assertIsNone(cursor.retry_not_before)

    def test_only_the_handlers_of_the_rows_kind_run(self) -> None:
        outbox.register_handler(TOPIC, self.remember)
        wanted = self.event(self.tenant_a.id)
        other = self.event(self.tenant_a.id, topic="probe.ignored")

        outbox.deliver_batch()

        self.assertEqual(self.seen, [wanted.id])
        # A kind nobody listens to is still delivered: the cursor is not held up by it.
        self.assertIsNotNone(self.reload(other).published_at)

    def test_the_cursor_writes_no_event(self) -> None:
        """record() stays the only writer of audit_event and outbox_event."""
        outbox.register_handler(TOPIC, self.remember)
        self.event(self.tenant_a.id)
        self.event(None)
        enter_zone(self.tenant_a.id)  # sees tenant A's rows and the library's
        audit_rows = AuditEvent.objects.count()
        outbox_rows = OutboxEvent.objects.count()

        outbox.deliver_batch()

        enter_zone(self.tenant_a.id)
        self.assertEqual(AuditEvent.objects.count(), audit_rows)
        self.assertEqual(OutboxEvent.objects.count(), outbox_rows)


class EachRowRunsInItsOwnZone(OutboxCursorCase):
    def test_a_tenant_row_runs_inside_its_tenant_and_a_library_row_with_none_active(self) -> None:
        zones: list[uuid.UUID | None] = []
        tenant_rows: list[int] = []

        def handler(event: OutboxEvent) -> None:
            zones.append(tenancy.database_tenant_id())
            tenant_rows.append(TenantContentLanguage.objects.count())

        outbox.register_handler(TOPIC, handler)
        self.event(self.tenant_a.id)
        self.event(None)

        outbox.deliver_batch()

        self.assertEqual(zones, [self.tenant_a.id, None])
        # NFR-S4: one content language inside the tenant, and with no tenant activated a
        # read of a tenant table matches nothing. Chunk 7 indexes library rows from here.
        self.assertEqual(tenant_rows, [1, 0])

    def test_setting_a_zone_outside_a_transaction_is_refused(self) -> None:
        """SET LOCAL outside a transaction is a silent no-op, and a zone nobody set is a
        batch that reads nothing: the cursor refuses rather than run blind."""
        db = connections[DEFAULT_DB_ALIAS]
        db.in_atomic_block = False
        try:
            with self.assertRaises(tenancy.NotInTransaction):
                outbox._enter_zone(self.tenant_a.id)
        finally:
            db.in_atomic_block = True


class AFailingHandlerHoldsTheOrder(OutboxCursorCase):
    def setUp(self) -> None:
        super().setUp()
        outbox.register_handler(TOPIC, self.remember)
        outbox.register_handler(FAILING_TOPIC, self.refuse)

    @override_settings(OUTBOX_MAX_ATTEMPTS=3, OUTBOX_RETRY_BACKOFF_S=60)
    def test_the_row_stays_unpublished_and_nothing_behind_it_overtakes_it(self) -> None:
        delivered = self.event(self.tenant_a.id)
        failing = self.event(self.tenant_a.id, topic=FAILING_TOPIC)
        behind = self.event(self.tenant_b.id)

        result = outbox.deliver_batch()

        self.assertEqual(self.seen, [delivered.id])
        self.assertEqual(result, outbox.BatchResult(delivered=1, failed=1))
        row = self.reload(failing)
        self.assertIsNone(row.published_at)
        self.assertEqual(row.attempts, 1)
        self.assertIsNone(self.reload(behind).published_at)
        self.assertEqual(self.cursor().last_id, delivered.id)

    @override_settings(OUTBOX_MAX_ATTEMPTS=3, OUTBOX_RETRY_BACKOFF_S=60)
    def test_the_retry_waits_out_the_backoff(self) -> None:
        failing = self.event(self.tenant_a.id, topic=FAILING_TOPIC)
        started = timezone.now()

        outbox.deliver_batch()

        wait = self.cursor().retry_not_before
        assert wait is not None  # the row at the front waits before it is tried again
        self.assertGreaterEqual(wait, started + timedelta(seconds=60))
        # Nothing is tried again before then, and the attempt count does not move.
        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult())
        self.assertEqual(self.reload(failing).attempts, 1)
        # With the wait behind it, the same row is tried again: attempt two, doubled wait.
        OutboxCursor.objects.filter(name=outbox.CURSOR_NAME).update(
            retry_not_before=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult(delivered=0, failed=1))
        self.assertEqual(self.reload(failing).attempts, 2)
        doubled = self.cursor().retry_not_before
        assert doubled is not None
        self.assertGreaterEqual(doubled, started + timedelta(seconds=120))

    @override_settings(OUTBOX_MAX_ATTEMPTS=2, OUTBOX_RETRY_BACKOFF_S=0)
    def test_after_the_last_attempt_the_row_is_left_failed_and_the_cursor_moves_on(self) -> None:
        failing = self.event(self.tenant_a.id, topic=FAILING_TOPIC)
        behind = self.event(self.tenant_b.id)

        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult(delivered=0, failed=1))
        self.assertEqual(self.seen, [])

        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult(delivered=1, failed=1))

        row = self.reload(failing)
        self.assertIsNone(row.published_at)
        self.assertEqual(row.attempts, 2)
        self.assertEqual(row.last_error, "RuntimeError")
        self.assertEqual(self.seen, [behind.id])
        self.assertIsNotNone(self.reload(behind).published_at)
        # The failed row is behind the cursor now: nothing retries it, nothing moves it.
        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult())
        self.assertEqual(self.reload(failing).attempts, 2)
        self.assertIsNone(self.cursor().retry_not_before)

    @override_settings(OUTBOX_MAX_ATTEMPTS=2, OUTBOX_RETRY_BACKOFF_S=0)
    def test_neither_the_row_nor_the_log_carries_tenant_content(self) -> None:
        failing = self.event(self.tenant_a.id, topic=FAILING_TOPIC)

        with self.assertLogs("apps.shared.outbox", level="WARNING") as captured:
            outbox.deliver_batch()

        self.assertTrue(captured.output)
        for line in captured.output:
            self.assertNotIn(SECRET, line)
        self.assertNotIn(SECRET, self.reload(failing).last_error)


class ALibraryHandlerFailsInsideItsOwnSavepoint(OutboxCursorCase):
    """The four paths above again, with library rows and a handler the database refuses.

    A tenant row's handlers have always run inside `@tenant_task`'s transaction, so a
    database error rolled back to that savepoint and the batch carried on. A library row's
    ran bare: the error aborted the batch's own transaction, counting the attempt was
    refused in turn, the whole batch rolled back, and the row came back with its attempts
    still at zero — retried forever, with every row behind it waiting, and whatever the
    handler had already written left committed (review 2026-09-20).

    Proven to fail 2026-09-20 by taking the savepoint out of the library branch again: each
    of the four raised out of `deliver_batch()` before reaching an assertion.
    """

    def setUp(self) -> None:
        super().setUp()
        outbox.register_handler(TOPIC, self.remember)
        outbox.register_handler(DATABASE_FAILING_TOPIC, self.refuse_in_the_database)

    def half_finished_rows(self) -> int:
        return OutboxCursor.objects.filter(name=HALF_FINISHED).count()

    @override_settings(OUTBOX_MAX_ATTEMPTS=3, OUTBOX_RETRY_BACKOFF_S=60)
    def test_the_row_stays_unpublished_and_nothing_behind_it_overtakes_it(self) -> None:
        delivered = self.event(None)
        failing = self.event(None, topic=DATABASE_FAILING_TOPIC)
        behind = self.event(self.tenant_a.id)

        result = outbox.deliver_batch()

        self.assertEqual(self.seen, [delivered.id])
        self.assertEqual(result, outbox.BatchResult(delivered=1, failed=1))
        row = self.reload(failing)
        self.assertIsNone(row.published_at)
        self.assertEqual(row.attempts, 1)
        self.assertIsNone(self.reload(behind).published_at)
        self.assertEqual(self.cursor().last_id, delivered.id)
        # The row in front of the failing one is published even so: the batch committed.
        self.assertIsNotNone(self.reload(delivered).published_at)
        self.assertEqual(self.half_finished_rows(), 0, "the handler's half-finished write is not committed")

    @override_settings(OUTBOX_MAX_ATTEMPTS=3, OUTBOX_RETRY_BACKOFF_S=60)
    def test_the_retry_waits_out_the_backoff(self) -> None:
        failing = self.event(None, topic=DATABASE_FAILING_TOPIC)
        started = timezone.now()

        outbox.deliver_batch()

        wait = self.cursor().retry_not_before
        assert wait is not None  # the row at the front waits before it is tried again
        self.assertGreaterEqual(wait, started + timedelta(seconds=60))
        # Nothing is tried again before then, and the attempt count does not move.
        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult())
        self.assertEqual(self.reload(failing).attempts, 1)
        # With the wait behind it, the same row is tried again: attempt two, doubled wait.
        OutboxCursor.objects.filter(name=outbox.CURSOR_NAME).update(
            retry_not_before=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult(delivered=0, failed=1))
        self.assertEqual(self.reload(failing).attempts, 2)
        doubled = self.cursor().retry_not_before
        assert doubled is not None
        self.assertGreaterEqual(doubled, started + timedelta(seconds=120))

    @override_settings(OUTBOX_MAX_ATTEMPTS=2, OUTBOX_RETRY_BACKOFF_S=0)
    def test_after_the_last_attempt_the_row_is_left_failed_and_the_cursor_moves_on(self) -> None:
        failing = self.event(None, topic=DATABASE_FAILING_TOPIC)
        behind = self.event(self.tenant_a.id)

        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult(delivered=0, failed=1))
        self.assertEqual(self.seen, [])

        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult(delivered=1, failed=1))

        row = self.reload(failing)
        self.assertIsNone(row.published_at)
        self.assertEqual(row.attempts, 2)
        self.assertEqual(row.last_error, "DataError")
        self.assertEqual(self.seen, [behind.id])
        self.assertIsNotNone(self.reload(behind).published_at)
        # The failed row is behind the cursor now: nothing retries it, nothing moves it.
        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult())
        self.assertEqual(self.reload(failing).attempts, 2)
        self.assertIsNone(self.cursor().retry_not_before)
        self.assertEqual(self.half_finished_rows(), 0)

    @override_settings(OUTBOX_MAX_ATTEMPTS=2, OUTBOX_RETRY_BACKOFF_S=0)
    def test_neither_the_row_nor_the_log_carries_tenant_content(self) -> None:
        """The case the type-name-only rule exists for: a database error quotes back the
        values of the statement that failed, and those are the bank's."""
        failing = self.event(None, topic=DATABASE_FAILING_TOPIC)

        with self.assertLogs("apps.shared.outbox", level="WARNING") as captured:
            outbox.deliver_batch()

        self.assertTrue(captured.output)
        for line in captured.output:
            self.assertNotIn(SECRET, line)
        self.assertNotIn(SECRET, self.reload(failing).last_error)


class TheThresholdsAreSettings(OutboxCursorCase):
    @override_settings(OUTBOX_BATCH_SIZE=1)
    def test_the_batch_size_caps_one_pass(self) -> None:
        outbox.register_handler(TOPIC, self.remember)
        first = self.event(self.tenant_a.id)
        second = self.event(self.tenant_b.id)

        self.assertEqual(outbox.deliver_batch().delivered, 1)
        self.assertEqual(self.seen, [first.id])
        self.assertEqual(outbox.deliver_batch().delivered, 1)
        self.assertEqual(self.seen, [first.id, second.id])

    def test_every_threshold_has_an_env_override_and_is_documented(self) -> None:
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        runbook = (ROOT / "docs" / "runbooks" / "RAILWAY_VARIABLES.md").read_text(encoding="utf-8")
        missing = [
            f"{name}: {'settings' if not hasattr(settings, name) else ''} "
            f"{'.env.example' if name not in example else ''} {'runbook' if name not in runbook else ''}".strip()
            for name in SETTINGS
            if not hasattr(settings, name) or name not in example or name not in runbook
        ]
        self.assertEqual(missing, [], "Thresholds without a setting, an example row or a runbook row:\n  " + "\n  ".join(missing))


class TheCursorRowIsTheLock(TransactionTestCase):
    """Two workers, two connections, one row: the second finds the cursor locked and
    delivers nothing rather than delivering it a second time."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def test_a_second_worker_delivers_nothing_while_the_cursor_is_held(self) -> None:
        seen: list[uuid.UUID] = []
        self.addCleanup(outbox._HANDLERS.clear)
        tenant = factories.tenant(slug="outbox-lock")
        outbox.deliver_batch()  # an empty backlog, and the cursor row the workers share
        outbox.register_handler(TOPIC, lambda event: seen.append(event.id))
        with transaction.atomic():
            tenancy.activate(tenant.id)
            record(
                action=TOPIC,
                actor=Actor.system("outbox probe"),
                subject_type="probe",
                subject_id=uuid.uuid4(),
                subject_title="",
                summary="",
                tenant_id=tenant.id,
            )

        with transaction.atomic(using="app"):
            OutboxCursor.objects.using("app").select_for_update().get(name=outbox.CURSOR_NAME)
            self.assertEqual(outbox.deliver_batch(), outbox.BatchResult())
            self.assertEqual(seen, [])

        # The row was not lost either: the worker that holds the cursor next delivers it.
        self.assertEqual(outbox.deliver_batch(), outbox.BatchResult(delivered=1, failed=0))
        self.assertEqual(len(seen), 1)


class TheBeatEntryRunsTheCursor(OutboxCursorCase):
    def test_the_entry_exists_and_points_at_the_task(self) -> None:
        celery_app.loader.import_default_modules()
        entry = settings.CELERY_BEAT_SCHEDULE[BEAT_ENTRY]
        self.assertEqual(entry["task"], "apps.shared.tasks.deliver_outbox")
        self.assertIn(entry["task"], celery_app.tasks)
        self.assertEqual(entry["schedule"], settings.OUTBOX_POLL_INTERVAL_S)

    def test_the_task_delivers_a_batch_and_activates_each_row_by_itself(self) -> None:
        outbox.register_handler(TOPIC, self.remember)
        event = self.event(self.tenant_a.id)

        deliver_outbox()

        self.assertEqual(self.seen, [event.id])
        self.assertIsNotNone(self.reload(event).published_at)
        # NFR-S5: one cursor spans the library and every tenant, so the beat task takes no
        # tenant and is not a @tenant_task; each row's handlers run inside one.
        self.assertEqual(list(inspect.signature(deliver_outbox.run).parameters), [])
        self.assertTrue(is_tenant_task(outbox._run_handlers_in_tenant))

    def test_a_pass_with_nothing_to_do_says_nothing(self) -> None:
        """Beat runs the task every few seconds; a quiet pass writes no log line."""
        with self.assertNoLogs("apps.shared.tasks", level="INFO"):
            deliver_outbox()


class TheRegistryHoldsOnlyItsConsumers(TestCase):
    """The cursor registers nothing of its own: a consumer registers its handler from its
    app's `ready()`. Two consumers exist — chunk 5's case creation (rulings 9 and 32) and
    chunk 7's search index, which fills the embeddings a library change left owing — so a
    second relay, or a handler registered anywhere but in an app's `ready()`, shows up
    here."""

    def test_only_its_two_consumers_are_registered_by_production_code(self) -> None:
        from apps.cases import creation
        from apps.search import tasks as search

        # Order-independent: a test above empties the registry to isolate its own handlers
        # and puts nothing back, so the apps' own registrations are made again here. They
        # are idempotent, so this can never be what makes the assertion pass.
        creation.register()
        search.register()
        self.assertEqual(
            sorted(outbox._HANDLERS),
            sorted([creation.CHANGE_REGISTERED, *search.INDEX_TOPICS]),
        )
        self.assertEqual(outbox.handlers_for(creation.CHANGE_REGISTERED), (creation.create_cases,))
        for topic in search.INDEX_TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(outbox.handlers_for(topic), (search.embed_rebuilt_chunks,))


class RegistrationHappensWhenTheAppIsReady(TestCase):
    """Where a consumer registers, not only what it registers.

    `apps/search/tasks.py` registered its handlers at the module's top level until
    2026-09-21. Nothing imports a `tasks` module in a running API process — only Celery's
    autodiscovery does, in the worker — so the handler was missing in exactly the process
    that writes the event, and the branch's own proof passed only because the test module
    had imported it. Both halves are silent failures, so both are pinned: no module may
    register at import time, and each app config's `ready()` must be what does it.
    """

    def test_no_module_registers_a_handler_at_import_time(self) -> None:
        offenders = []
        for path in sorted((ROOT / "backend" / "apps").rglob("*.py")):
            if path.name.startswith("tests"):
                continue
            calls = _ImportTimeCalls()
            calls.visit(ast.parse(path.read_text(encoding="utf-8")))
            if "register_handler" in calls.names:
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(
            offenders,
            [],
            "Handlers registered at import time, where an API process never sees them; "
            "move the calls into a register() an app config's ready() calls:\n  " + "\n  ".join(offenders),
        )

    def test_each_consumers_handler_comes_back_from_its_app_configs_ready(self) -> None:
        """The other half: `ready()` is what registers, proved on an empty registry, which
        is the state a process starts in. The cleanups put both consumers back for the
        tests that follow."""
        from django.apps import apps as installed

        from apps.cases import creation
        from apps.search import tasks as search

        self.addCleanup(search.register)
        self.addCleanup(creation.register)
        outbox._HANDLERS.clear()
        for label, topics, handler in (
            ("cases", (creation.CHANGE_REGISTERED,), creation.create_cases),
            ("search", search.INDEX_TOPICS, search.embed_rebuilt_chunks),
        ):
            installed.get_app_config(label).ready()
            for topic in topics:
                with self.subTest(app=label, topic=topic):
                    self.assertEqual(outbox.handlers_for(topic), (handler,))


class _ImportTimeCalls(ast.NodeVisitor):
    """The names a module calls while it is being imported.

    A module-level `for`, `if` or class body runs on import and counts; the body of a
    `def` does not, because nothing has called it yet.
    """

    def __init__(self) -> None:
        self.names: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        target = node.func
        self.names.append(target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", ""))
        self.generic_visit(node)

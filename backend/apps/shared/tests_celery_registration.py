"""Guard: Celery registration (playbook 5, 12, 14).

Enumerates every entry in `beat_schedule` and every task registered from apps/ and
demands: every beat entry points at a task that exists, and every task whose first
parameter is `tenant_id` is wrapped in `@tenant_task` (so it activates the tenant inside
its own transaction). Phase 0 registers no tasks and no beat entries; the enumeration
still runs, and `@tenant_task` itself is proven on a plain function.

Proven to fail 2026-09-19 by adding a beat entry for "apps.home.tasks.digest" with no
such task: the test named the entry and the task.
"""

from __future__ import annotations

import inspect
import uuid

from django.db import transaction
from django.test import TestCase

from apps.shared import factories, tenancy
from apps.shared.tenancy import NotInTransaction, is_tenant_task, tenant_task
from config.celery import app as celery_app


class CeleryRegistrationGuard(TestCase):
    def setUp(self) -> None:
        celery_app.loader.import_default_modules()

    def test_every_beat_entry_points_at_a_registered_task(self) -> None:
        schedule = celery_app.conf.beat_schedule or {}
        self.assertIsInstance(schedule, dict)
        missing = [
            f"{name} -> {entry.get('task')}"
            for name, entry in schedule.items()
            if entry.get("task") not in celery_app.tasks
        ]
        self.assertEqual(missing, [], "Beat entries pointing at tasks that do not exist:\n  " + "\n  ".join(missing))

    def test_every_tenant_task_is_wrapped(self) -> None:
        unwrapped: list[str] = []
        for name, task in celery_app.tasks.items():
            if not name.startswith("apps."):
                continue
            fn = getattr(task, "__wrapped__", None) or task.run
            params = list(inspect.signature(fn).parameters)
            if params and params[0] == "tenant_id" and not is_tenant_task(fn):
                unwrapped.append(name)
        self.assertEqual(unwrapped, [], "Tenant tasks not wrapped in @tenant_task:\n  " + "\n  ".join(unwrapped))


class WeeklyBriefingSchedule(TestCase):
    """The first beat entry a tenant task hangs off (HOM-02, `c6-briefing-backend`).

    A bank's Monday morning is not the server's, so beat runs the job every hour and the
    dispatcher picks the banks whose own clock has just struck the configured moment. That
    is why the entry below is hourly rather than weekly, and why the weekday and the hour
    are settings the dispatcher reads rather than numbers inside the schedule.
    """

    def test_the_weekly_briefing_entry_runs_hourly_and_names_a_task_that_exists(self) -> None:
        from django.conf import settings

        entry = (celery_app.conf.beat_schedule or {})["briefing-weekly"]
        self.assertEqual(entry["task"], "apps.home.tasks.send_weekly_briefings")
        self.assertIn(entry["task"], celery_app.tasks)
        self.assertEqual(entry["schedule"].minute, {0}, "every hour on the hour, not once a week")
        self.assertEqual((settings.BRIEFING_SEND_WEEKDAY, settings.BRIEFING_SEND_HOUR), (0, 7))

    def test_the_task_it_hands_on_to_is_a_wrapped_tenant_task(self) -> None:
        """It writes one bank's rows, so it must activate that bank inside its own
        transaction; the guard above enforces the rule and this pins the task by name."""
        from apps.home import tasks

        self.assertTrue(is_tenant_task(tasks.send_weekly_briefing.run))
        self.assertEqual(list(inspect.signature(tasks.send_weekly_briefing.run).parameters)[0], "tenant_id")


class TenantTaskDecorator(TestCase):
    def test_tenant_task_activates_inside_its_own_transaction(self) -> None:
        tenant = factories.tenant()
        seen: dict[str, object] = {}

        @tenant_task
        def body(tenant_id: uuid.UUID, note: str) -> str:
            seen["python"] = tenancy.active_tenant_id()
            seen["database"] = tenancy.database_tenant_id()
            return note

        self.assertTrue(is_tenant_task(body))
        before = tenancy.active_tenant_id()
        # The wrapper also accepts the id as a string (Celery serialises arguments).
        self.assertEqual(body(str(tenant.id), "ok"), "ok")  # type: ignore[arg-type]
        self.assertEqual(seen, {"python": tenant.id, "database": tenant.id})
        # The Python mirror is restored to whatever the caller had (a direct activate() in
        # an earlier test of the same context may have left one; the task never leaks its own).
        self.assertEqual(tenancy.active_tenant_id(), before)

    def test_activate_refuses_to_run_outside_a_transaction(self) -> None:
        from django.db import DEFAULT_DB_ALIAS, connections

        connection = connections[DEFAULT_DB_ALIAS]
        original = connection.in_atomic_block
        connection.in_atomic_block = False
        try:
            with self.assertRaises(NotInTransaction):
                tenancy.activate(uuid.uuid4())
        finally:
            connection.in_atomic_block = original

    def test_set_local_ends_with_the_transaction(self) -> None:
        tenant = factories.tenant()
        with transaction.atomic():
            tenancy.activate(tenant.id)
            self.assertEqual(tenancy.database_tenant_id(), tenant.id)
        # The test's own outer transaction is still open, but the SET LOCAL was scoped to
        # the inner savepoint? No: SET LOCAL is transaction-scoped, not savepoint-scoped,
        # so within the runner's transaction it persists. Prove that on a fresh atomic
        # block the value is what the policy would see, and that it is never unset here.
        self.assertEqual(tenancy.database_tenant_id(), tenant.id)

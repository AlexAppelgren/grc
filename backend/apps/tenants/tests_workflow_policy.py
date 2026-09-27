"""A bank's workflow policy (COL-02, TEN-01): how many days before a due date its members are
reminded, how many days before a review, how long overdue work waits before it escalates and
to which role, the weekday the digest goes out and the triage target in hours. `GET /tenant`
shows it as `workflow`; `PATCH /tenant/workflow` changes it under `workflow.manage`, with no
step-up, and writes one audit event with the values before and after. A tenant that existed
before the policy did takes the platform defaults, which are settings.

Operations exercised: getTenant, updateTenantWorkflow.
"""

from __future__ import annotations

import importlib
from typing import Any

from django.conf import settings
from django.db.migrations.operations import AddField
from django.test import SimpleTestCase

from apps.identity.models import TenantRole
from apps.library.seeds import seed_languages
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import ScenarioTestCase, sign_in

V1 = "/api/v1"
URL = f"{V1}/tenant/workflow"


def _defaults() -> dict[str, Any]:
    return {
        "reminderDaysBefore": list(settings.WORKFLOW_REMINDER_DAYS_BEFORE),
        "reviewReminderDaysBefore": list(settings.WORKFLOW_REVIEW_REMINDER_DAYS_BEFORE),
        "escalateAfterDays": settings.WORKFLOW_ESCALATE_AFTER_DAYS,
        "escalateToRole": settings.WORKFLOW_ESCALATE_TO_ROLE,
        "digestWeekday": settings.WORKFLOW_DIGEST_WEEKDAY,
        "triageTargetHours": settings.WORKFLOW_TRIAGE_TARGET_HOURS,
    }


def _flat(workflow: dict[str, Any]) -> dict[str, Any]:
    return {**workflow, "escalateToRole": workflow["escalateToRole"]["key"]}


class WorkflowPolicy(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.officer = factories.member(self.tenant, roles=("compliance_officer",)).user

    def _patch(self, body: dict[str, Any], user: Any = None) -> Any:
        headers = sign_in(user or self.officer, tenant=self.tenant)
        return self.client.patch(URL, data=body, content_type="application/json", **headers)

    def _events(self) -> list[AuditEvent]:
        self.activate(self.tenant)
        return list(AuditEvent.objects.filter(tenant=self.tenant, action="tenant.workflow_updated").order_by("created", "id"))

    def _stored(self) -> dict[str, Any]:
        row = Tenant.objects.get(pk=self.tenant.id)
        return {
            "reminderDaysBefore": row.reminder_days_before,
            "reviewReminderDaysBefore": row.review_reminder_days_before,
            "escalateAfterDays": row.escalate_after_days,
            "escalateToRole": row.escalate_to_role,
            "digestWeekday": row.digest_weekday,
            "triageTargetHours": row.triage_target_hours,
        }

    def test_a_new_tenant_reads_the_platform_defaults_from_settings(self) -> None:
        response = self.client.get(f"{V1}/tenant", **sign_in(self.officer, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        workflow = response.json()["workflow"]
        self.assertEqual(_flat(workflow), _defaults())
        self.assertEqual(set(workflow["escalateToRole"]), {"key", "kind", "label"})
        self.assertTrue(workflow["escalateToRole"]["label"])

    def test_the_profile_carries_the_platform_defaults_beside_the_policy_so_a_bank_sees_what_it_changes_from(self) -> None:
        self.assertEqual(self._patch({"escalateAfterDays": 9, "escalateToRole": "admin"}).status_code, 200)
        with self.settings(WORKFLOW_ESCALATE_AFTER_DAYS=12, WORKFLOW_DIGEST_WEEKDAY="friday"):
            response = self.client.get(f"{V1}/tenant", **sign_in(self.officer, tenant=self.tenant))
            expected = _defaults()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(_flat(body["workflowDefaults"]), expected)
        self.assertEqual((expected["escalateAfterDays"], expected["digestWeekday"]), (12, "friday"))
        self.assertEqual((body["workflow"]["escalateAfterDays"], body["workflow"]["escalateToRole"]["key"]), (9, "admin"))
        self.assertEqual(set(body["workflowDefaults"]["escalateToRole"]), {"key", "kind", "label"})
        self.assertTrue(body["workflowDefaults"]["escalateToRole"]["label"])

    def test_the_defaults_follow_the_settings_rather_than_a_literal(self) -> None:
        with self.settings(WORKFLOW_REMINDER_DAYS_BEFORE=[7, 1], WORKFLOW_TRIAGE_TARGET_HOURS=24, WORKFLOW_DIGEST_WEEKDAY="friday"):
            row = factories.tenant(slug="later-bank")
        self.assertEqual((row.reminder_days_before, row.triage_target_hours, row.digest_weekday), ([7, 1], 24, "friday"))

    def test_a_holder_of_workflow_manage_changes_the_policy_and_one_event_records_before_and_after(self) -> None:
        body = {
            "reminderDaysBefore": [1, 14, 7],
            "reviewReminderDaysBefore": [60, 30],
            "escalateAfterDays": 10,
            "escalateToRole": "admin",
            "digestWeekday": "thursday",
            "triageTargetHours": 72,
        }
        response = self._patch(body)
        self.assertEqual(response.status_code, 200, response.content)
        expected = {**body, "reminderDaysBefore": [14, 7, 1]}
        self.assertEqual(_flat(response.json()["workflow"]), expected)
        self.assertEqual(response.json()["id"], str(self.tenant.id))
        self.assertEqual(self._stored(), expected)
        [event] = self._events()
        self.assertEqual((event.before, event.after), (_defaults(), expected))
        self.assertEqual((event.subject_type, event.subject_id, event.actor_id), ("tenant", self.tenant.id, self.officer.id))
        self.assertIsNone(event.step_up_assertion_id)

    def test_an_omitted_field_is_left_alone(self) -> None:
        response = self._patch({"escalateAfterDays": 9})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._stored(), {**_defaults(), "escalateAfterDays": 9})

    def test_a_retired_or_custom_role_of_this_bank_is_judged_by_its_own_rows(self) -> None:
        self.activate(self.tenant)
        TenantRole.objects.create(tenant=self.tenant, key="head-of-risk", permissions=[])
        TenantRole.objects.create(tenant=self.tenant, key="old-role", permissions=[], active=False)
        self.assertEqual(self._patch({"escalateToRole": "head-of-risk"}).status_code, 200)
        self.assertEqual(self._stored()["escalateToRole"], "head-of-risk")
        response = self._patch({"escalateToRole": "old-role"})
        self.assertEqual((response.status_code, response.json()["code"]), (422, "unknown_key"))

    def test_a_role_of_another_bank_or_no_bank_and_an_unknown_weekday_answer_unknown_key_naming_the_field(self) -> None:
        other = factories.tenant(slug="other-bank")
        self.activate(other)
        TenantRole.objects.create(tenant=other, key="elsewhere", permissions=[])
        for field, value in (("escalateToRole", "elsewhere"), ("escalateToRole", "nobody"), ("digestWeekday", "someday")):
            response = self._patch({field: value})
            self.assertEqual((response.status_code, response.json()["code"]), (422, "unknown_key"), value)
            self.assertEqual([error["field"] for error in response.json()["errors"]], [field], value)
        self.assertEqual(self._stored(), _defaults())
        self.assertEqual(self._events(), [])

    def test_out_of_range_empty_and_over_long_values_answer_422_naming_the_field(self) -> None:
        cases: tuple[tuple[str, Any], ...] = (
            ("reminderDaysBefore", []),
            ("reminderDaysBefore", [0]),
            ("reminderDaysBefore", [91]),
            ("reminderDaysBefore", [1, 2, 3, 4, 5, 6]),
            ("reviewReminderDaysBefore", []),
            ("reviewReminderDaysBefore", [120]),
            ("escalateAfterDays", 0),
            ("escalateAfterDays", 91),
            ("triageTargetHours", 0),
            ("triageTargetHours", 721),
            ("escalateToRole", ""),
        )
        for field, value in cases:
            response = self._patch({field: value})
            self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"), (field, value))
            named = [error["field"].split(".") for error in response.json()["errors"]]
            self.assertTrue(named and all(field in parts for parts in named), (field, value, response.json()))
        self.assertEqual(self._stored(), _defaults())
        self.assertEqual(self._events(), [])

    def test_a_field_the_policy_does_not_name_is_refused(self) -> None:
        response = self._patch({"escalateAfterDays": 6, "name": "Renamed"})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(self._stored(), _defaults())

    def test_without_workflow_manage_the_change_is_refused_naming_the_permission(self) -> None:
        self.activate(self.tenant)
        TenantRole.objects.create(tenant=self.tenant, key="security-only", permissions=[perms.SECURITY_MANAGE, perms.MEMBERS_MANAGE])
        for roles in (("reader",), ("security-only",)):
            user = factories.member(self.tenant, roles=roles).user
            response = self._patch({"escalateAfterDays": 9}, user=user)
            self.assertEqual((response.status_code, response.json()["code"]), (403, "permission_denied"), roles)
            self.assertEqual(response.json()["requiredPermission"], perms.WORKFLOW_MANAGE)
        self.assertEqual(self._stored(), _defaults())
        self.assertEqual(self._events(), [])

    def test_workflow_manage_alone_does_not_reach_the_profile(self) -> None:
        response = self.client.patch(f"{V1}/tenant", data={"name": "Renamed"}, content_type="application/json", **sign_in(self.officer, tenant=self.tenant))
        self.assertEqual((response.status_code, response.json()["requiredPermission"]), (403, perms.SECURITY_MANAGE))


class ExistingTenantsTakeTheDefaults(SimpleTestCase):
    """The migration adds each column with the platform default, which PostgreSQL writes into
    every tenant row that existed before it: `AddField` with a default backfills, then drops
    the database default and leaves the model's."""

    def test_the_migration_adds_every_column_with_the_platform_default(self) -> None:
        migration = importlib.import_module("apps.shared.migrations.0009_tenant_workflow_policy").Migration
        added = {op.name: op.field for op in migration.operations if isinstance(op, AddField) and op.model_name == "tenant"}
        expected = {
            "reminder_days_before": list(settings.WORKFLOW_REMINDER_DAYS_BEFORE),
            "review_reminder_days_before": list(settings.WORKFLOW_REVIEW_REMINDER_DAYS_BEFORE),
            "escalate_after_days": settings.WORKFLOW_ESCALATE_AFTER_DAYS,
            "escalate_to_role": settings.WORKFLOW_ESCALATE_TO_ROLE,
            "digest_weekday": settings.WORKFLOW_DIGEST_WEEKDAY,
            "triage_target_hours": settings.WORKFLOW_TRIAGE_TARGET_HOURS,
        }
        self.assertEqual(set(added), set(expected))
        for name, value in expected.items():
            self.assertFalse(added[name].null, name)
            self.assertEqual(added[name].get_default(), value, name)

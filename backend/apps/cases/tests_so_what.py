"""A bank's own "So what?" (WAT-05, AUD-02, D-66).

Three things move one field and they must not be confusable: a run's draft arriving, a
person confirming it, and a person rewriting it. What is proved here is that the first
never overwrites what the second or the third left, that neither of the last two reaches
another bank or the shared library, and that the text itself never leaves the bank's zone —
not into an audit value, not into an outbox payload.

Proven to fail 2026-09-21: with the backfill handler unregistered the improved draft never
reached an untouched copy, and with the `so_what_confirmed` filter dropped from the
backfill it overwrote a bank's own wording, which is the one thing the handler exists not
to do.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.cases import creation, so_what, testing as case_build
from apps.cases.models import ChangeCase
from apps.shared import factories, outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange

V1 = "/api/v1"
SECURITIES = "regime:securities"
AML = "regime:aml"

DRAFT = "Teams that pay for external research should confirm that documented criteria exist."
BETTER_DRAFT = "Desks paying for external research need documented annual quality criteria by 1 October."
OUR_WORDS = "Self-directed trading and Guided investing both pay for research; the desk documents the criteria."


def drain() -> None:
    with transaction.atomic():
        tenancy.clear_tenant()
    while outbox.deliver_batch().delivered:
        pass


def registered(change: RegulatoryChange) -> None:
    with transaction.atomic():
        tenancy.clear_tenant()
        record(
            action=creation.CHANGE_REGISTERED,
            actor=Actor.system("watch"),
            subject_type="regulatory_change",
            subject_id=change.id,
            subject_title=change.title,
            summary=f"Registered {change.title}.",
            tenant_id=None,
        )
    drain()


def redrafted(change: RegulatoryChange) -> None:
    """The event `apps/watch/so_what_draft.py` writes when a run files or improves a
    change's drafted wording."""
    with transaction.atomic():
        tenancy.clear_tenant()
        record(
            action=so_what.SO_WHAT_DRAFTED,
            actor=Actor(kind=Actor.system().kind, id=None, label="watch-sweeper"),
            subject_type="regulatory_change",
            subject_id=change.id,
            subject_title=change.title,
            summary="watch-sweeper filed a drafted answer.",
            tenant_id=None,
        )
    drain()


def case_of(tenant: Any, change: RegulatoryChange) -> ChangeCase:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return ChangeCase.objects.select_related("so_what_confirmed_by").get(change=change)


def set_draft(change: RegulatoryChange, text: str) -> None:
    """What `so_what_draft.store()` writes onto the change, without its log row: this module
    is about what the banks do with a draft, and the log row is `tests_so_what_draft.py`'s."""
    change.so_what_draft = text
    with watch_build.watch_write(watch_build.REASON):
        change.save(update_fields=["so_what_draft"])


class DraftBackfillTests(TestCase):
    """A run's draft reaching the banks, and stopping where a person has been."""

    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        creation.register()
        so_what.register()
        self.banks = case_build.two_tenants_with_different_footprints(inside=SECURITIES, outside=AML)
        drain()
        self.change = watch_build.change_with_timeline(terms=(SECURITIES,), so_what_draft=DRAFT)
        registered(self.change)

    def test_the_draft_reaches_every_banks_case_unconfirmed(self) -> None:
        for bank in (self.banks.inside, self.banks.outside):
            with self.subTest(bank=bank.slug):
                case = case_of(bank, self.change)
                self.assertEqual(case.so_what_text, DRAFT)
                self.assertFalse(case.so_what_confirmed, "a copy nobody has stood behind is still AI output")
                self.assertIsNone(case.so_what_confirmed_by_id)

    def test_a_better_draft_reaches_every_untouched_copy(self) -> None:
        set_draft(self.change, BETTER_DRAFT)
        redrafted(self.change)
        for bank in (self.banks.inside, self.banks.outside):
            with self.subTest(bank=bank.slug):
                self.assertEqual(case_of(bank, self.change).so_what_text, BETTER_DRAFT)

    def test_a_bank_that_wrote_its_own_words_keeps_them(self) -> None:
        author = factories.member(self.banks.inside, roles=("compliance_officer",)).user
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            # As the route leaves it: the words, the person and the time, which the
            # `change_case_so_what_confirmation_names_a_person` constraint demands together.
            ChangeCase.objects.filter(change=self.change).update(
                so_what_text=OUR_WORDS,
                so_what_confirmed=True,
                so_what_confirmed_by=author,
                so_what_confirmed_at=timezone.now(),
            )
        set_draft(self.change, BETTER_DRAFT)
        redrafted(self.change)
        self.assertEqual(
            case_of(self.banks.inside, self.change).so_what_text,
            OUR_WORDS,
            "an agent never overwrites a bank's own wording",
        )
        self.assertEqual(case_of(self.banks.outside, self.change).so_what_text, BETTER_DRAFT)

    def test_one_audit_row_per_bank_and_nothing_else_moves(self) -> None:
        set_draft(self.change, BETTER_DRAFT)
        redrafted(self.change)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            rows = AuditEvent.objects.filter(action=so_what.DRAFT_APPLIED, tenant_id=self.banks.inside.id)
            self.assertEqual(rows.count(), 1)
            self.assertEqual(rows.get().after, {"casesUpdated": 1})
            self.assertFalse(case_of(self.banks.inside, self.change).urgency_confirmed)

    def test_a_replayed_event_moves_nothing_and_records_nothing(self) -> None:
        set_draft(self.change, BETTER_DRAFT)
        redrafted(self.change)
        with transaction.atomic():
            tenancy.clear_tenant()
            OutboxEvent.objects.filter(topic=so_what.SO_WHAT_DRAFTED).update(published_at=None)
        drain()
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            self.assertEqual(
                AuditEvent.objects.filter(action=so_what.DRAFT_APPLIED, tenant_id=self.banks.inside.id).count(), 1
            )


class SoWhatRouteTests(ScenarioTestCase):
    """`PUT /changes/{changeId}/so-what` and `POST /changes/{changeId}/so-what/confirm`."""

    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        creation.register()
        so_what.register()
        self.banks = case_build.two_tenants_with_different_footprints(inside=SECURITIES, outside=AML)
        drain()
        self.officer = factories.member(
            self.banks.inside, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")
        ).user
        self.reader = factories.member(self.banks.inside, roles=("reader",)).user
        self.other_officer = factories.member(self.banks.outside, roles=("compliance_officer",)).user
        self.change = watch_build.change_with_timeline(terms=(SECURITIES,), so_what_draft=DRAFT)
        registered(self.change)

    def _put(self, text: str, who: Any) -> Any:
        return self.client.put(
            f"{V1}/changes/{self.change.id}/so-what",
            data={"text": text},
            content_type="application/json",
            **sign_in(who, tenant=self.banks.inside),
        )

    def _confirm(self, who: Any, tenant: Any = None) -> Any:
        return self.client.post(
            f"{V1}/changes/{self.change.id}/so-what/confirm",
            data={},
            content_type="application/json",
            **sign_in(who, tenant=tenant or self.banks.inside),
        )

    def test_confirming_keeps_the_words_and_names_the_person(self) -> None:
        response = self._confirm(self.officer)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["text"], DRAFT, "confirming does not rewrite; the words stay the model's")
        self.assertTrue(body["confirmed"])
        self.assertFalse(body["isAiDraft"])
        self.assertEqual(body["confirmedByName"], "Sara Lind")
        self.assertIsNotNone(body["confirmedAt"])

    def test_saving_our_own_wording_replaces_the_draft_and_confirms_it(self) -> None:
        response = self._put(OUR_WORDS, self.officer)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["text"], OUR_WORDS)
        self.assertTrue(response.json()["confirmed"], "somebody who rewrote it has already decided")
        self.assertFalse(response.json()["isAiDraft"])

    def test_another_banks_copy_is_untouched(self) -> None:
        self._put(OUR_WORDS, self.officer)
        other = case_of(self.banks.outside, self.change)
        self.assertEqual(other.so_what_text, DRAFT)
        self.assertFalse(other.so_what_confirmed)

    def test_the_librarys_draft_and_its_log_row_are_untouched(self) -> None:
        """Ruling I: a bank confirms its own copy and never the shared row."""
        from apps.governance.models import AiGeneration

        with transaction.atomic():
            tenancy.clear_tenant()
            before = list(AiGeneration.objects.values())
        self._confirm(self.officer)
        self._confirm(self.other_officer, tenant=self.banks.outside)
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertEqual(list(AiGeneration.objects.values()), before)
            self.change.refresh_from_db()
            self.assertEqual(self.change.so_what_draft, DRAFT)

    def test_the_wording_never_reaches_an_audit_value_or_an_outbox_payload(self) -> None:
        self._put(OUR_WORDS, self.officer)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            event = AuditEvent.objects.get(action=so_what.SAVED, tenant_id=self.banks.inside.id)
            self.assertEqual(event.after, {"soWhatConfirmed": True, "characters": len(OUR_WORDS)})
            payload = OutboxEvent.objects.get(audit_event=event).payload
        for blob in (str(event.before), str(event.after), str(payload)):
            self.assertNotIn("Self-directed trading", blob)

    def test_a_reader_without_cases_work_is_refused(self) -> None:
        response = self._confirm(self.reader)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["requiredPermission"], "cases.work")

    def test_a_change_this_bank_has_no_case_for_answers_404(self) -> None:
        stranger = uuid.uuid4()
        response = self.client.post(
            f"{V1}/changes/{stranger}/so-what/confirm",
            data={},
            content_type="application/json",
            **sign_in(self.officer, tenant=self.banks.inside),
        )
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))

    def test_confirming_a_case_with_no_draft_answers_404(self) -> None:
        """“This bank confirmed nothing” is not a position anybody should quote."""
        bare = watch_build.change_with_timeline(terms=(SECURITIES,))
        registered(bare)
        response = self.client.post(
            f"{V1}/changes/{bare.id}/so-what/confirm",
            data={},
            content_type="application/json",
            **sign_in(self.officer, tenant=self.banks.inside),
        )
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))

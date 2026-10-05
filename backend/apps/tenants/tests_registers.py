"""The public registers' tables and jobs beyond TEN-S13 and TEN-S14 (TEN-07, TEN-08): the
database's own refusals, the worker's idempotency and caps, where an added company is put,
the re-read of a company gone from the register, and the nightly fan-out."""

from __future__ import annotations

import dataclasses
import itertools
import uuid
from datetime import timedelta
from typing import Any
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.library import testing as library_build
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.reports.models import JobStatus
from apps.shared import factories, tenancy
from apps.shared.adapters.registers import MockRegisters
from apps.shared.models import AuditEvent, TenantStatus
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.tenants import registers_jobs, tasks
from apps.tenants.models import OrgUnit, OrgUnitKind, RegisterEntry, RegisterLookup

BANK_LEI = "549300EXAMPLEBANK001"
FONDER_LEI = "549300EXAMPLEFOND002"


class RegistersCase(TestCase):
    authority: Any
    tenant: Any
    person: Any

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        cls.authority = library_build.authority(key="fi", short_name="Finansinspektionen")
        cls.tenant = factories.tenant(slug="registers-a")
        cls.person = factories.member_user(cls.tenant, roles=("admin",))

    def setUp(self) -> None:
        self.addCleanup(MockRegisters.reset)
        tenancy.activate(self.tenant.id)

    def lookup(self, query: str = "556000-0001") -> RegisterLookup:
        with self.captureOnCommitCallbacks(execute=True):
            lookup = registers_jobs.start_lookup(tenant=self.tenant, actor=factories.user_actor(), user=self.person, query=query)
        tenancy.activate(self.tenant.id)
        lookup.refresh_from_db()
        return lookup

    def apply(self, lookup: RegisterLookup, leis: list[str]) -> Any:
        return registers_jobs.apply_lookup(tenant=self.tenant, actor=factories.user_actor(), order=["en"], lookup_id=lookup.id, leis=leis)


class TheDatabaseRefuses(RegistersCase):
    def test_another_banks_unit_or_person_and_a_unit_that_is_not_a_legal_entity(self) -> None:
        other = factories.tenant(slug="registers-b")
        theirs = factories.legal_entity(other)
        stranger = factories.member_user(other)
        department = factories.org_unit(self.tenant)
        tenancy.activate(self.tenant.id)
        now = timezone.now()
        for unit_id in (theirs.id, department.id):
            with self.subTest(unit=unit_id), self.assertRaises(IntegrityError), transaction.atomic():
                RegisterEntry.objects.create(
                    tenant=self.tenant, org_unit_id=unit_id, authority=self.authority, facts={}, source_url="https://www.fi.se/", read_at=now, changed_at=now
                )
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegisterLookup.objects.create(tenant=self.tenant, query="556000-0001", requested_by=stranger)

    def test_one_entry_per_unit_and_authority(self) -> None:
        unit = factories.legal_entity(self.tenant)
        tenancy.activate(self.tenant.id)
        now = timezone.now()
        values = {"tenant": self.tenant, "org_unit": unit, "authority": self.authority, "facts": {}, "source_url": "https://www.fi.se/", "read_at": now, "changed_at": now}
        RegisterEntry.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegisterEntry.objects.create(**values)


class TheWorker(RegistersCase):
    def test_a_lookup_runs_once_and_only_in_its_own_bank(self) -> None:
        lookup = self.lookup()
        self.assertEqual(lookup.status, JobStatus.SUCCEEDED.value)
        finished = lookup.completed_at
        with mock.patch.object(MockRegisters, "find") as find:
            tasks.run_register_lookup(str(self.tenant.id), str(lookup.id))
            tasks.run_register_lookup(str(factories.tenant(slug="registers-c").id), str(lookup.id))
        find.assert_not_called()
        tenancy.activate(self.tenant.id)
        lookup.refresh_from_db()
        self.assertEqual(lookup.completed_at, finished)

    def test_a_lookup_past_its_time_limit_fails_whole(self) -> None:
        # REGISTERS_JOB_SECONDS bounds the reads inside the bank's transaction: the clock is
        # moved past it after GLEIF answered, so no company is read from FI.
        with mock.patch.object(registers_jobs, "_clock", side_effect=itertools.chain([0.0], itertools.repeat(10_000.0))):
            lookup = self.lookup()
        self.assertEqual((lookup.status, lookup.error, lookup.result.get("entities", [])), (JobStatus.FAILED.value, "register_unavailable", []))

    @override_settings(REGISTERS_MAX_ENTITIES=2)
    def test_the_walk_stops_at_the_cap(self) -> None:
        names = [entity["name"] for entity in self.lookup().result["entities"]]
        self.assertEqual(names, ["Example Bank AB", "Example Fonder AB"])

    def test_an_lei_is_looked_up_upper_cased(self) -> None:
        lookup = self.lookup(BANK_LEI.lower())
        self.assertEqual((lookup.query, lookup.status), (BANK_LEI, JobStatus.SUCCEEDED.value))
        finished = AuditEvent.objects.get(action="register_lookup.finished", subject_id=lookup.id)
        self.assertEqual(finished.after, {"status": "succeeded", "error": None, "companies": 5, "withFacts": 3})

    def test_a_company_whose_number_is_not_one_gets_no_facts(self) -> None:
        odd = MockRegisters().find("556000-0003")[0]
        with mock.patch.object(MockRegisters, "children", return_value=[dataclasses.replace(odd, registration_number="?")]):
            entities = self.lookup().result["entities"]
        self.assertEqual((entities[1]["authority"], entities[1]["facts"]), ("fi", None))


class WhereACompanyGoes(RegistersCase):
    def test_under_the_group_when_no_chosen_company_is_above_it_and_at_the_top_without_one(self) -> None:
        lookup = self.lookup()
        out = self.apply(lookup, [FONDER_LEI])
        self.assertEqual((out.created, out.linked, out.org_units[0].parent_id), (1, 0, None))
        group = OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.GROUP.value, name="Example Group")
        out = self.apply(lookup, [BANK_LEI, "549300EXAMPLELIVF003"])
        self.assertEqual([unit.parent_id for unit in out.org_units], [group.id, out.org_units[0].id])

    def test_a_unit_with_another_country_is_not_the_company(self) -> None:
        OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name="Exempel Pankki Oy", org_number="556000-0001", country_code="FI")
        out = self.apply(self.lookup(), [BANK_LEI])
        self.assertEqual((out.created, out.linked), (1, 0))

    def test_a_newer_lookup_changes_the_stored_facts(self) -> None:
        self.apply(self.lookup(), [BANK_LEI])
        read = MockRegisters().licence_facts("fi", "556000-0001")
        assert read is not None
        MockRegisters.override("556000-0001", dataclasses.replace(read, branches=read.branches[:1]))
        self.apply(self.lookup(), [BANK_LEI])
        entry = RegisterEntry.objects.get()
        self.assertEqual((entry.version, len(entry.facts["branches"])), (2, 1))
        changed = AuditEvent.objects.get(action="register_entry.changed")
        self.assertEqual(changed.after["branchesRemoved"], ["Example Bank AB, filial i Norge"])


class TheReRead(RegistersCase):
    def test_a_company_gone_from_the_register_is_unlisted_with_its_licences_removed(self) -> None:
        self.apply(self.lookup(), [BANK_LEI])
        MockRegisters.override("556000-0001", None)
        tasks.recheck_tenant_registers(str(self.tenant.id))
        tenancy.activate(self.tenant.id)
        entry = RegisterEntry.objects.get()
        self.assertEqual((entry.facts["listed"], entry.facts["licences"], entry.facts["branches"]), (False, [], []))
        self.assertEqual(entry.facts["mainBusiness"], "Bankaktiebolag")
        changed = AuditEvent.objects.get(action="register_entry.changed")
        self.assertEqual((changed.before["listed"], changed.after["listed"], len(changed.after["licencesRemoved"])), (True, False, 5))

    def test_a_deactivated_entity_is_not_read_and_a_bank_without_facts_reads_nothing(self) -> None:
        self.apply(self.lookup(), [BANK_LEI])
        OrgUnit.objects.filter(lei=BANK_LEI).update(active=False)
        with mock.patch.object(MockRegisters, "licence_facts") as read:
            tasks.recheck_tenant_registers(str(self.tenant.id))
            tasks.recheck_tenant_registers(str(factories.tenant(slug="registers-d").id))
        read.assert_not_called()

    def test_a_re_read_past_its_time_limit_leaves_the_rest_for_tomorrow(self) -> None:
        self.apply(self.lookup(), [BANK_LEI])
        with mock.patch.object(registers_jobs, "_clock", side_effect=itertools.chain([0.0], itertools.repeat(10_000.0))):
            tasks.recheck_tenant_registers(str(self.tenant.id))
        tenancy.activate(self.tenant.id)
        self.assertEqual(RegisterEntry.objects.get().version, 1)
        self.assertFalse(AuditEvent.objects.filter(action__in=("register_entry.read", "register_entry.changed")).exists())

    def test_the_beat_hands_each_active_bank_to_its_own_task(self) -> None:
        resting = factories.tenant(slug="registers-e")
        resting.status = TenantStatus.DEACTIVATED.value
        resting.save(update_fields=["status"])
        with mock.patch.object(tasks.recheck_tenant_registers, "delay") as delay:
            tasks.recheck_registers()
        handed = {uuid.UUID(call.args[0]) for call in delay.call_args_list}
        self.assertIn(self.tenant.id, handed)
        self.assertNotIn(resting.id, handed)

    def test_a_stored_number_that_is_not_one_is_skipped(self) -> None:
        self.apply(self.lookup(), [BANK_LEI])
        entry = RegisterEntry.objects.get()
        RegisterEntry.objects.filter(pk=entry.pk).update(facts={**entry.facts, "registrationNumber": "?"}, read_at=timezone.now() - timedelta(days=1))
        tasks.recheck_tenant_registers(str(self.tenant.id))
        tenancy.activate(self.tenant.id)
        self.assertEqual(RegisterEntry.objects.get().version, 1)
        self.assertFalse(AuditEvent.objects.filter(action__in=("register_entry.read", "register_entry.changed")).exists())

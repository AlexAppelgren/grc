"""The model wrapper refuses a call about a bank's own record (INV-07, OWN-04, D-57).

A bank's own instrument, obligation or provision is never a model input. The guard is a
refusal in the one door to a model (`apps/shared/ai.py`), not a caller's good manners: a
call whose subject is such a record raises before any model is asked, and no AI log row
is written. The refusal fails closed: a library subject the call's zone cannot read as a
shared record is refused too, because an owned row is exactly what another zone cannot
read.
"""

from __future__ import annotations

import uuid
from typing import ClassVar
from unittest import mock

from django.test import TestCase

from apps.governance.models import AiGeneration, AiPurpose
from apps.library import testing as build
from apps.library.models import Instrument, Obligation, Provision, SubjectType
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import ai, factories, tenancy
from apps.shared.models import Tenant
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions


def generate(subject_type: str, subject_id: uuid.UUID | None, *, tenant: Tenant | None, llm: object = None) -> ai.Generation:
    return ai.generate(
        purpose=AiPurpose.SO_WHAT,
        system="You say what a change means for the bank.",
        prompt="The record's text would travel here.",
        prompt_template="test/so-what/v1",
        citations=[],
        tenant_id=tenant.id if tenant else None,
        subject_type=subject_type,
        subject_id=subject_id,
        llm=llm,  # type: ignore[arg-type]
    )


class TheWrapperRefusesAPrivateSubject(TestCase):
    tenant: ClassVar[Tenant]
    shared: ClassVar[Obligation]
    own_instrument: ClassVar[Instrument]
    own: ClassVar[Obligation]
    own_under_shared: ClassVar[Obligation]
    own_provision: ClassVar[Provision]

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        cls.tenant = factories.tenant(slug="own-records-ai")
        shared_instrument = build.instrument(key="ai-shared", regime="regime:securities")
        cls.shared = build.obligation(shared_instrument, key="obl-ai-shared")
        cls.own_instrument = build.instrument(key="ai-own", regime="regime:securities", owner_tenant=cls.tenant)
        cls.own = build.obligation(cls.own_instrument, key="obl-ai-own", owner_tenant=cls.tenant)
        cls.own_under_shared = build.obligation(shared_instrument, key="obl-ai-own-under-shared", owner_tenant=cls.tenant)
        cls.own_provision = build.provision(cls.own_instrument, key="ai-own-1")

    def setUp(self) -> None:
        # The bank's own zone, where its own records are readable: the refusal is not the
        # policy hiding them, it is the wrapper declining them.
        tenancy.activate(self.tenant.id)

    def assert_refused(self, subject_type: str, subject_id: uuid.UUID | None) -> None:
        model = mock.Mock()
        with self.assertRaises(ai.PrivateRecordRefused):
            generate(subject_type, subject_id, tenant=self.tenant, llm=model)
        model.complete.assert_not_called()
        model.stream.assert_not_called()
        self.assertFalse(AiGeneration.objects.filter(subject_id=subject_id).exists())

    def test_a_banks_own_obligation_is_refused_before_the_model_is_asked(self) -> None:
        self.assert_refused(SubjectType.OBLIGATION.value, self.own.id)

    def test_a_banks_own_obligation_under_a_shared_instrument_is_refused(self) -> None:
        self.assert_refused(SubjectType.OBLIGATION.value, self.own_under_shared.id)

    def test_a_banks_own_instrument_is_refused(self) -> None:
        self.assert_refused(SubjectType.INSTRUMENT.value, self.own_instrument.id)

    def test_a_provision_of_a_banks_own_instrument_is_refused(self) -> None:
        self.assert_refused(SubjectType.PROVISION.value, self.own_provision.id)

    def test_a_library_subject_the_zone_cannot_read_as_shared_is_refused(self) -> None:
        """Fail closed: outside the bank's zone its record is not readable at all, and an
        id that names nothing proves nothing shared either."""
        tenancy.clear_tenant()
        model = mock.Mock()
        for subject_id in (self.own.id, uuid.uuid4(), None):
            with self.subTest(subject_id=subject_id), self.assertRaises(ai.PrivateRecordRefused):
                generate(SubjectType.OBLIGATION.value, subject_id, tenant=None, llm=model)
        model.complete.assert_not_called()

    def test_a_shared_record_still_reaches_the_model_and_is_logged(self) -> None:
        made = generate(SubjectType.OBLIGATION.value, self.shared.id, tenant=self.tenant)

        self.assertEqual(made.generation.subject_id, self.shared.id)

    def test_a_subject_outside_the_library_is_not_the_refusals_to_judge(self) -> None:
        made = generate("regulatory_change", uuid.uuid4(), tenant=self.tenant)

        self.assertEqual(made.generation.subject_type, "regulatory_change")

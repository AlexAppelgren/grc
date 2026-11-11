"""Case builders for tests (playbook 8.1).

Every builder activates its tenant before writing, because forced row-level security
applies to the test connection too (playbook 14); the two-tenant helper activates neither.
They live here rather than in `apps/shared/factories.py` because a case names a library
model beside a write, which the library fence allows only in `testing.py`.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from django.db import transaction

from apps.cases.models import OWNED_CATEGORIES, CaseLinkDecision, CaseObligationLink, ChangeCase
from apps.identity.models import User
from apps.library.models import Obligation
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.taxonomy.models import CaseStatusCategory, DismissalReason, FootprintTerm, Urgency
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange


def case(
    tenant: Tenant,
    change: RegulatoryChange,
    *,
    urgency: str = "act_now",
    urgency_confirmed: bool = False,
    footprint_match: bool = True,
    owner: User | None = None,
    so_what_text: str = "",
) -> ChangeCase:
    """One bank's case for one change, `new` as creation leaves it, its urgency the change's
    unconfirmed suggestion.
    """
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return ChangeCase.objects.create(
            tenant=tenant,
            change=change,
            urgency=Urgency.objects.get(key=urgency),
            urgency_confirmed=urgency_confirmed,
            footprint_match=footprint_match,
            owner=owner,
            so_what_text=so_what_text,
        )


def in_category(row: ChangeCase, category: CaseStatusCategory) -> None:
    """Put a case straight into `category` with what the CHECKs demand there (an owner
    between triage and close, a reason when dismissed). The state machine is not run."""
    fields: dict[str, object] = {"status": category.value}
    with transaction.atomic():
        tenancy.activate(row.tenant_id)
        if category in OWNED_CATEGORIES and row.owner_id is None:
            fields["owner"] = factories.member_user(row.tenant, roles=("compliance_officer",))
        if category is CaseStatusCategory.DISMISSED:
            fields["dismissed_reason"] = DismissalReason.objects.get(key="out_of_scope")
        ChangeCase.objects.filter(pk=row.pk).update(**fields)

def link_decision(
    row: ChangeCase,
    obligation: Obligation,
    *,
    decision: CaseLinkDecision = CaseLinkDecision.ACCEPTED,
    decided_by: User | None = None,
) -> CaseObligationLink:
    """What this bank decided about one suggested library link. It writes one tenant row
    and touches no library row, which `tests_models.py` proves (WAT-04, ruling C)."""
    with transaction.atomic():
        tenancy.activate(row.tenant_id)
        return CaseObligationLink.objects.create(
            tenant_id=row.tenant_id, case=row, obligation=obligation, decision=decision.value, decided_by=decided_by
        )


def two_tenants_with_different_footprints(
    *, inside: str = "regime:securities", outside: str = "regime:aml"
) -> SimpleNamespace:
    """Two banks whose footprints do not overlap (CAS-S1, WAT-S10, FP-S15). `.inside` follows
    the watch builders' default regime. Neither is left activated, so a forgotten activation
    fails loudly.
    """
    suffix = uuid.uuid4().hex[:8]
    matching = factories.tenant(slug=f"inside-{suffix}", name="Example Bank AB")
    other = factories.tenant(slug=f"outside-{suffix}", name="Second Bank A/S")
    for tenant, ref in ((matching, inside), (other, outside)):
        with transaction.atomic():
            tenancy.activate(tenant.id)
            FootprintTerm.objects.create(tenant=tenant, term=watch_build.term(ref))
    return SimpleNamespace(inside=matching, outside=other)


def case_on_a_new_change(tenant: Tenant) -> ChangeCase:
    """A fresh library change with a case of `tenant` and of nobody else, the reference rows
    seeded first. The tenant-isolation guard's subject for the workflow routes
    (`apps/shared/factories.py:case_change`)."""
    watch_build.seed_watch_reference()
    return case(tenant, watch_build.change())


def registered(change: RegulatoryChange) -> None:
    """Record `change` as registered from the library's zone, then deliver the outbox, so each
    bank's case exists the way the cursor makes it."""
    from apps.cases import creation
    from apps.shared.audit import Actor, record
    from apps.shared.testing import drain

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

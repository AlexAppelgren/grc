"""Case builders for tests (playbook 8.1): one bank's case for a library change, that
bank's own decision about a suggested obligation link, and the pair of banks with
different footprints that CAS-S1, WAT-S10 and FP-S15 all want.

Every builder activates its tenant before writing. FORCE ROW LEVEL SECURITY applies to the
test runner's own connection as well, so a tenant row is invisible and unwritable until
`tenancy.activate()` has run inside the transaction (playbook 14). The activation lasts
until the test's savepoint rolls back, or until the next builder activates another tenant —
which is exactly why the two-tenant helper hands back both tenants and activates neither.

These builders live here rather than in `apps/shared/factories.py` because a case names a
library model (`RegulatoryChange`, `Obligation`) beside a write, and the library fence
treats `factories.py` as a production module while it exempts every `testing.py`
(apps/shared/tests_library_fence.py).
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
    """One bank's case for one change, in the `new` category as creation leaves it.

    The urgency starts as the change's suggestion and `urgency_confirmed` stays false until
    a person triages, which is what the card renders before triage (Alex's item 1).
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
    """Put a case straight into `category` for a test that reads cases by category, with
    what the database's CHECKs demand there: an owner between triage and the close, and a
    reason when dismissed (c9-case-models). The state machine is not run; a test of a move
    goes through the move itself."""
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
    """Two banks whose footprints do not overlap, for every test that has to show a change
    reaching one and not the other (CAS-S1, WAT-S10, FP-S15).

    `.inside` follows the regime the watch builders put on a change by default, so
    `watch_build.change_with_timeline()` matches it and not `.outside`. Neither tenant is
    left activated: a test that writes for one activates it itself, so a forgotten
    activation fails loudly instead of writing into whichever bank came last.
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

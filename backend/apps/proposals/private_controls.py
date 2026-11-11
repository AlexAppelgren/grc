"""A control of the bank's own obligation (OWN-05, REG-05, INV-07; D-89, D-99, ADR 0059).

A control is a REG-05 internal item of the `control` link kind, linked to the bank's own
obligation and created by the private approval (D-99), so a `new_control` proposal writes no
library row. It is filed by the bank's own agent (`proposals.tenant_agent`) and decided in
the bank's own queue by a person with a fresh passkey, never the proposer.

`apply_control`, in the approval's transaction and the bank's zone, checks the obligation
and the link kind again, creates or reuses the internal item, and links it to the
obligation's register entry (409 `already_linked` if a live link exists), each write audited
with ids and keys only (R2_CROSS_CUTTING (m)). `held` is the filing's duplicate check,
answered by the database so the agent never reads the bank's records (D-57).
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError

from apps.library.reading import own_obligation
from apps.proposals.models import Proposal
from apps.proposals.schemas import ProposalControlPayload
from apps.register.links import ITEM_CREATED, LINK_ADDED
from apps.register.logic import ensure_register_entry
from apps.register.models import InternalLink
from apps.shared.audit import Actor, batched, record
from apps.shared.errors import ProblemError
from apps.taxonomy.models import LinkKind
from apps.tenants.models import InternalItem

# The link kind a control is an internal item of: a stable key of the bank's `link_kind` list.
CONTROL_KIND = "control"


def validated_control(payload: ProposalControlPayload, owner_tenant_id: uuid.UUID | None) -> None:
    """A control names an obligation of the bank's own in force (422 `unknown_key`
    otherwise). Its name and reference are stored trimmed."""
    payload.name = payload.name.strip()
    payload.reference = payload.reference.strip()
    if not payload.name:
        raise ValidationError("Give the control a name.", code="validation_error")
    if owner_tenant_id is None:
        raise ValidationError("A control is only ever a record of your organisation's own.", code="validation_error")
    own_obligation(owner_tenant_id, payload.obligation)


def held(tenant_id: uuid.UUID, payload: ProposalControlPayload) -> bool:
    """Whether the bank already links a control of this name to this obligation."""
    return InternalLink.objects.filter(
        tenant_id=tenant_id,
        tenant_obligation__obligation__stable_key=payload.obligation,
        internal_item__kind__key=CONTROL_KIND,
        internal_item__name__iexact=payload.name.strip(),
        removed_at__isnull=True,
    ).exists()


@batched()
def apply_control(proposal: Proposal, payload: ProposalControlPayload, *, actor: Actor, reviewer_id: uuid.UUID, step_up: uuid.UUID | None) -> None:
    """Create or reuse the control and link it to the bank's own obligation, as the module
    docstring says. The caller holds the approval's transaction and stands in the bank's zone."""
    owner = proposal.owner_tenant_id
    if owner is None:
        raise ValidationError("A control is only ever a record of your organisation's own.", code="validation_error")
    validated_control(payload, owner)
    obligation = own_obligation(owner, payload.obligation)
    kind = LinkKind.objects.filter(key=CONTROL_KIND, active=True).first()  # ordering: unique key per bank, at most one row
    if kind is None:
        raise ValidationError("Controls are not on your list of link kinds.", code="unknown_key")
    entry = ensure_register_entry(tenant_id=owner, obligation_id=obligation.id, actor=actor)
    item = InternalItem.objects.filter(kind=kind, name=payload.name).first()  # ordering: unique per bank, kind and name
    if item is not None and not item.active:
        raise ValidationError("A control of that name was retired: restore it or reject this proposal.", code="validation_error")
    if item is None:
        item = InternalItem.objects.create(tenant_id=owner, kind=kind, name=payload.name, reference=payload.reference)
        record(
            action=ITEM_CREATED,
            actor=actor,
            subject_type="internal_item",
            subject_id=item.id,
            subject_title=item.name,
            summary="Internal item created.",
            tenant_id=owner,
            after={"kind": kind.key, "proposal": str(proposal.id)},
            step_up_assertion_id=step_up,
        )
    elif InternalLink.objects.filter(tenant_obligation=entry, internal_item=item, removed_at__isnull=True).exists():
        raise ProblemError(status=409, code="already_linked", detail="That control is already linked to this obligation.")
    link = InternalLink.objects.create(
        tenant_id=owner, tenant_obligation=entry, internal_item=item, label=item.name, created_by_id=reviewer_id
    )
    record(
        action=LINK_ADDED,
        actor=actor,
        subject_type="internal_link",
        subject_id=link.id,
        subject_title=link.label,
        summary="Internal item linked.",
        tenant_id=owner,
        after={"obligationId": str(obligation.id), "internalItemId": str(item.id), "kind": kind.key, "proposal": str(proposal.id)},
        step_up_assertion_id=step_up,
    )

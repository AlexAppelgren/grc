"""Linked internal items (REG-05): the bank's own policies, procedures and controls, with the
references an outside GRC system knows them by. A removal is soft; the item survives the link.

Every link points at an `InternalItem`, which carries the kind (INPUT_DELTAS, c8-register-models):
the call either picks one of the bank's items or creates it from the same body, so there is
no separate internal-items screen in R2. The link keeps its own label, url and external
reference, taken from the item unless the call names its own. An audit row names ids and
keys only (R2_CROSS_CUTTING (m)); the url is stored as given and never fetched.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.identity.models import Membership
from apps.library.reading import obligation_headings
from apps.register.logic import ensure_register_entry
from apps.register.models import InternalLink
from apps.register.schemas import (
    RegisterInternalItem,
    RegisterInternalItemPage,
    RegisterInternalLink,
    RegisterInternalLinkBody,
    RegisterInternalLinkPage,
    RegisterPersonRef,
    RegisterVocabRef,
)
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.vocabulary import label_for
from apps.taxonomy.models import LinkKind, Team
from apps.tenants.models import InternalItem, OrgUnit

ITEM_CREATED = "register.internal_item_created"
LINK_ADDED = "register.internal_link_added"
LINK_REMOVED = "register.internal_link_removed"
# A link is only ever a web page: never `javascript:`, `data:` or a file path.
WEB_URL = URLValidator(schemes=["https", "http"])
# The body fields that describe a new item; a call that picks an item sends none of them.
ITEM_FIELDS = ("reference", "external_system", "owner_id", "owner_team_id", "org_unit_id", "last_reviewed_on", "next_review_on")


def list_links(
    *, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, limit: int, offset: int
) -> RegisterInternalLinkPage:
    """The live links of the bank's entry on one obligation, oldest first, in a constant
    number of queries. An obligation the bank cannot see is 404; one nobody has linked
    anything to is an empty page."""
    if not obligation_headings([obligation_id], []):
        raise ValidationError("That obligation is not here.", code="not_found")
    live = InternalLink.objects.filter(tenant_obligation__obligation_id=obligation_id, removed_at__isnull=True)
    rows = (
        live.select_related("internal_item__kind", "created_by")
        .prefetch_related("internal_item__kind__labels")
        .order_by("created_at", "id")[offset : offset + limit]
    )
    return RegisterInternalLinkPage(items=[_link_out(row, order) for row in rows], total=live.count())


def list_items(*, order: list[str], query: str, limit: int, offset: int) -> RegisterInternalItemPage:
    """The bank's active items whose name or reference holds `query`, by name, for the link
    dialog to pick from, in a constant number of queries. Row-level security keeps it to
    the bank's own."""
    active = InternalItem.objects.filter(active=True)
    if query:
        active = active.filter(Q(name__icontains=query) | Q(reference__icontains=query))
    rows = active.select_related("kind").prefetch_related("kind__labels").order_by("name", "id")[offset : offset + limit]
    items = [
        RegisterInternalItem(
            id=row.id,
            kind=RegisterVocabRef(key=row.kind.key, kind=row.kind.kind, label=label_for(row.kind, order)),
            name=row.name,
            reference=row.reference or None,
        )
        for row in rows
    ]
    return RegisterInternalItemPage(items=items, total=active.count())


def add_link(
    *, tenant: Tenant, actor: Actor, order: list[str], obligation_id: uuid.UUID, body: RegisterInternalLinkBody
) -> RegisterInternalLink:
    """Link a picked item, or create the item and link it, each with its own audit event in
    the request's transaction. `already_linked` (409) when the item has a live link here."""
    if body.url is not None:
        try:
            WEB_URL(body.url)
        except ValidationError:
            raise ValidationError("A link must be a web address starting with https:// or http://.", code="validation_error") from None
    kind = LinkKind.objects.filter(key=body.kind, active=True).first()  # ordering: unique key per bank, at most one row
    if kind is None:
        raise ValidationError("That kind is not on your list of link kinds.", code="unknown_key")
    entry = ensure_register_entry(tenant_id=tenant.id, obligation_id=obligation_id, actor=actor)
    if body.internal_item_id is None:
        item = _create_item(tenant=tenant, actor=actor, kind=kind, body=body)
    else:
        item = _picked_item(item_id=body.internal_item_id, body=body, kind=kind)
        if InternalLink.objects.filter(tenant_obligation=entry, internal_item=item, removed_at__isnull=True).exists():
            raise _already_linked()
    try:
        with transaction.atomic():
            link = InternalLink.objects.create(
                tenant_id=tenant.id,
                tenant_obligation=entry,
                internal_item=item,
                label=body.label,
                url=item.url if body.url is None else body.url,
                external_ref=item.external_ref if body.external_ref is None else body.external_ref,
                created_by_id=person_id(actor),
            )
    except IntegrityError:
        # Two links of the same item at once meet on `internal_link_live_unique`.
        raise _already_linked() from None
    record(
        action=LINK_ADDED,
        actor=actor,
        subject_type="internal_link",
        subject_id=link.id,
        subject_title=link.label,
        summary="Internal item linked.",
        tenant_id=tenant.id,
        after={"obligationId": str(obligation_id), "internalItemId": str(item.id), "kind": kind.key},
    )
    link.internal_item = item
    return _link_out(link, order)


def remove_link(*, tenant: Tenant, actor: Actor, link_id: uuid.UUID) -> None:
    """Stamp the link removed; the row and its item stay. A link another bank holds, or one
    already removed, is 404."""
    link = InternalLink.objects.select_for_update().filter(pk=link_id, removed_at__isnull=True).first()  # ordering: pk lookup, at most one row
    if link is None:
        raise ValidationError("That link is not here.", code="not_found")
    link.removed_at = timezone.now()
    link.removed_by_id = person_id(actor)
    link.save(update_fields=["removed_at", "removed_by"])
    record(
        action=LINK_REMOVED,
        actor=actor,
        subject_type="internal_link",
        subject_id=link.id,
        subject_title=link.label,
        summary="Internal item unlinked.",
        tenant_id=tenant.id,
        before={"removedAt": None},
        after={"removedAt": link.removed_at.isoformat(), "internalItemId": str(link.internal_item_id)},
    )


def person_id(actor: Actor) -> uuid.UUID:
    """The person acting: every register route takes a person's session (api.py)."""
    if actor.id is None:  # pragma: no cover - a session always names its person
        raise ProblemError(status=403, code="permission_denied", detail="A person must do this.")
    return actor.id


def _already_linked() -> ProblemError:
    """409 `already_linked`, with the request's transaction marked for rollback, since a
    ProblemError is answered inside the view and would otherwise commit the entry created
    before it."""
    transaction.set_rollback(True)
    return ProblemError(status=409, code="already_linked", detail="That item is already linked to this obligation.")


def _picked_item(*, item_id: uuid.UUID, body: RegisterInternalLinkBody, kind: LinkKind) -> InternalItem:
    if any(getattr(body, name) is not None for name in ITEM_FIELDS):
        raise ValidationError("Pick an item or describe a new one, not both.", code="validation_error")
    item = InternalItem.objects.filter(pk=item_id, active=True).first()  # ordering: pk lookup, at most one row
    if item is None:
        raise ValidationError("That item is not here.", code="not_found")
    if item.kind_id != kind.id:
        raise ValidationError("That item is of another kind.", code="validation_error")
    return item


def _create_item(*, tenant: Tenant, actor: Actor, kind: LinkKind, body: RegisterInternalLinkBody) -> InternalItem:
    if body.owner_id is not None and body.owner_team_id is not None:
        raise ValidationError("An item is owned by a person or a team, not both.", code="validation_error")
    if body.owner_id is not None and not Membership.objects.filter(user_id=body.owner_id, deactivated_at__isnull=True).exists():
        raise ValidationError("The owner is not a member of your bank.", code="validation_error")
    if body.owner_team_id is not None and not Team.objects.filter(pk=body.owner_team_id, active=True).exists():
        raise ValidationError("That team is not one of your bank's teams.", code="validation_error")
    if body.org_unit_id is not None and not OrgUnit.objects.filter(pk=body.org_unit_id).exists():
        raise ValidationError("That part of the organisation is not here.", code="validation_error")
    if InternalItem.objects.filter(kind=kind, name=body.label).exists():
        raise ValidationError("An item of that kind and name exists already; pick it instead.", code="duplicate_key")
    item = InternalItem.objects.create(
        tenant_id=tenant.id,
        kind=kind,
        name=body.label,
        reference=body.reference or "",
        url=body.url or "",
        owner_user_id=body.owner_id,
        owner_team_id=body.owner_team_id,
        org_unit_id=body.org_unit_id,
        external_system=body.external_system or "",
        external_ref=body.external_ref or "",
        last_reviewed_on=body.last_reviewed_on,
        next_review_on=body.next_review_on,
    )
    record(
        action=ITEM_CREATED,
        actor=actor,
        subject_type="internal_item",
        subject_id=item.id,
        subject_title=item.name,
        summary="Internal item created.",
        tenant_id=tenant.id,
        after={"kind": kind.key, "orgUnitId": _str(body.org_unit_id), "ownerId": _str(body.owner_id), "ownerTeamId": _str(body.owner_team_id)},
    )
    return item


def _str(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


def _link_out(link: InternalLink, order: list[str]) -> RegisterInternalLink:
    item = link.internal_item
    if item is None:  # pragma: no cover - every link is made with its item (module docstring)
        raise ValidationError("That link has no item.", code="not_found")
    return RegisterInternalLink(
        id=link.id,
        kind=RegisterVocabRef(key=item.kind.key, kind=item.kind.kind, label=label_for(item.kind, order)),
        label=link.label,
        url=link.url or None,
        external_ref=link.external_ref or None,
        external_system=item.external_system or None,
        internal_item_id=item.id,
        created_by=RegisterPersonRef(id=link.created_by.id, name=link.created_by.name),
        created_at=link.created_at,
    )

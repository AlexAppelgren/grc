"""People and teams taking part in a register entry (COL-04, D-18, D-19; MY_WORK_AND_MARKETS
3.2). The case half is `c9-case-participants`'.

Participation is attention, never access. It puts a record on a person's My work and in
their notifications and grants nothing: whatever a participant may read or do is still
their role's alone, which is why no route here reads a participant row to decide anything
else.

Four rules hold it to that:

- **The subject is read under row-level security first.** Another bank's private
  obligation is the same 404 as an id that never existed. A shared obligation lands on the
  caller's own bank's register entry, created on the first add by the register's one
  `ensure_register_entry()`, with its own audit event in the same transaction.
- **Only a member who can read the record is added.** A user of another bank, a
  deactivated member and an unknown id are one answer, `unknown_member`, so nothing can be
  probed; a member whose roles lack `register.read` is `participant_cannot_read`. A team is
  not checked, because each member's own read permission already filters what they see.
- **Removal is a stamp.** `removed_at` and `removed_by` are set and the row stays, so the
  history shows who took part until when. A person may always leave their own row;
  removing anyone else needs `register.edit`.
- **Ids only in the audit.** Each add, removal and leave records one event holding ids, and
  the title is the library's.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.collab.models import Participant
from apps.collab.schemas import CollabParticipant, CollabParticipantPage, CollabTeamRef
from apps.identity.models import Membership, UserStatus
from apps.library.reading import obligation_headings
from apps.register.logic import ensure_register_entry
from apps.register.models import TenantObligation
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.vocabulary import label_for
from apps.taxonomy.models import Team
from apps.taxonomy.schemas import PersonRef

SUBJECT_TYPE = "tenant_obligation"
ADDED = "participant.added"
REMOVED = "participant.removed"
LEFT = "participant.left"


def _title(obligation_id: uuid.UUID) -> str:
    """The obligation's library title for the audit row, read under row-level security: an
    obligation this bank cannot see is `not_found`, exactly as one that never existed."""
    heading = obligation_headings([obligation_id], []).get(obligation_id)
    if heading is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return f"{heading.instrument_short_name}, {heading.reference_label}"


def _entry(obligation_id: uuid.UUID) -> TenantObligation | None:
    return TenantObligation.objects.filter(obligation_id=obligation_id).first()  # ordering: unique per bank, at most one row


def _out(row: Participant, order: list[str]) -> CollabParticipant:
    return CollabParticipant(
        id=row.id,
        person=PersonRef(id=row.user.id, name=row.user.name) if row.user is not None else None,
        team=CollabTeamRef(key=row.team.key, label=label_for(row.team, order)) if row.team is not None else None,
        added_by=PersonRef(id=row.added_by.id, name=row.added_by.name),
        added_at=row.added_at,
    )


def list_participants(*, obligation_id: uuid.UUID, order: list[str], limit: int, offset: int) -> CollabParticipantPage:
    """The live participants of the bank's register entry on the obligation, in the order
    they were added. An obligation nobody has worked on has no entry and an empty list: a
    read never creates one."""
    _title(obligation_id)
    entry = _entry(obligation_id)
    if entry is None:
        return CollabParticipantPage(items=[], total=0)
    rows = Participant.objects.filter(tenant_obligation=entry, removed_at__isnull=True)
    page = rows.select_related("user", "team", "added_by").prefetch_related("team__labels")[offset : offset + limit]
    return CollabParticipantPage(items=[_out(row, order) for row in page], total=rows.count())


def _member_who_can_read(user_id: uuid.UUID) -> uuid.UUID:
    """The user, if they are an active member of the bank whose roles read the register.
    Read under row-level security, so another bank's member is simply not found."""
    granted = list(
        Membership.objects.filter(user_id=user_id, deactivated_at__isnull=True, user__status=UserStatus.ACTIVE.value)
        .values_list("roles__permissions", flat=True)
    )
    if not granted:
        raise ValidationError("That person is not a member here.", code="unknown_member")
    if not any(perms.REGISTER_READ in (permissions or []) for permissions in granted):
        raise ValidationError("That person cannot open this record, so they cannot take part in it.", code="participant_cannot_read")
    return user_id


def _team(team_key: str) -> Team:
    team = Team.objects.filter(key=team_key.strip().lower(), active=True).first()  # ordering: unique (tenant, key), at most one row
    if team is None:
        raise ValidationError("There is no such team.", code="unknown_key")
    return team


@transaction.atomic
def add_participant(
    *,
    tenant_id: uuid.UUID,
    obligation_id: uuid.UUID,
    user_id: uuid.UUID | None,
    team_key: str | None,
    caller_id: uuid.UUID,
    actor: Actor,
    order: list[str],
) -> CollabParticipant:
    """Name a person or a team on the bank's register entry for the obligation, creating the
    entry on the first add. The entry's row is locked while the add is checked, so two adds
    at once can neither both pass the cap nor both add the same participant."""
    title = _title(obligation_id)
    person = _member_who_can_read(user_id) if user_id is not None else None
    team = _team(team_key) if team_key is not None else None
    entry = ensure_register_entry(tenant_id=tenant_id, obligation_id=obligation_id, actor=actor)
    TenantObligation.objects.select_for_update().filter(id=entry.id).first()  # ordering: pk lookup, at most one row
    live = Participant.objects.filter(tenant_obligation=entry, removed_at__isnull=True)
    same = live.filter(user_id=person) if person is not None else live.filter(team=team)
    if same.exists():
        raise ValidationError("They already take part in this.", code="already_participant")
    if live.count() >= settings.MAX_PARTICIPANTS_PER_RECORD:
        raise ValidationError(
            f"A record holds at most {settings.MAX_PARTICIPANTS_PER_RECORD} participants.", code="too_many_participants"
        )
    row = Participant.objects.create(
        tenant_id=tenant_id, tenant_obligation=entry, user_id=person, team=team, added_by_id=caller_id
    )
    record(
        action=ADDED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=entry.id,
        subject_title=title,
        summary="Participant added.",
        tenant_id=tenant_id,
        after={
            "participantId": str(row.id),
            "userId": str(person) if person is not None else None,
            "teamId": str(team.id) if team is not None else None,
        },
    )
    row = Participant.objects.select_related("user", "team", "added_by").prefetch_related("team__labels").get(id=row.id)
    return _out(row, order)


@transaction.atomic
def remove_participant(
    *,
    tenant_id: uuid.UUID,
    obligation_id: uuid.UUID,
    participant_id: uuid.UUID,
    caller_id: uuid.UUID,
    actor: Actor,
    can_edit: bool,
) -> None:
    """End one participation on the bank's register entry for the obligation. The person
    named on it leaves (`participant.left`); anyone else removes it (`participant.removed`)
    and needs `register.edit`. Another bank's participant, one already ended and an unknown
    id are all `not_found`."""
    title = _title(obligation_id)
    entry = _entry(obligation_id)
    row = (
        Participant.objects.select_for_update()
        .filter(id=participant_id, tenant_obligation=entry, removed_at__isnull=True)
        .first()  # ordering: pk lookup, at most one row
        if entry is not None
        else None
    )
    if row is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    leaving = row.user_id == caller_id
    if not leaving and not can_edit:
        raise ProblemError(
            status=403,
            code="permission_denied",
            detail="You do not have access to this.",
            required_permission=perms.REGISTER_EDIT,
        )
    row.removed_at = timezone.now()
    row.removed_by_id = caller_id
    row.save(update_fields=["removed_at", "removed_by"])
    record(
        action=LEFT if leaving else REMOVED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.tenant_obligation_id,
        subject_title=title,
        summary="Participant left." if leaving else "Participant removed.",
        tenant_id=tenant_id,
        after={"participantId": str(row.id)},
    )

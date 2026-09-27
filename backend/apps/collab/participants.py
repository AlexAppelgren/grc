"""People and teams taking part in a register entry or a case (COL-04, CAS-03, D-18 to
D-20; MY_WORK_AND_MARKETS 3.2). Both subjects go through the same list, add and remove below;
only what names the subject, and the permission that reads and edits it, differ.

Participation is attention, never access. It puts a record on a person's My work and in
their notifications and grants nothing: whatever a participant may read or do is still
their role's alone, which is why no route here reads a participant row to decide anything
else.

Five rules hold it to that:

- **The subject is read under row-level security first.** Another bank's private
  obligation, a change this bank has no case for and an id that never existed are the same
  404. A shared obligation lands on the caller's own bank's register entry, created on the
  first add by the register's one `ensure_register_entry()`, with its own audit event in the
  same transaction; a shared change lands on the bank's own case.
- **Only a member who can read the record is added.** A user of another bank, a
  deactivated member and an unknown id are one answer, `unknown_member`, so nothing can be
  probed; a member whose roles lack the subject's read permission (`register.read`,
  `cases.read`) is `participant_cannot_read`. A team is not checked, because each member's
  own read permission already filters what they see.
- **A closed case takes nobody new.** A case that is closed or dismissed answers
  `invalid_transition`, from `state.is_open()`; a participation on it may still end.
- **Removal is a stamp.** `removed_at` and `removed_by` are set and the row stays, so the
  history and the case file show who took part until when. A person may always leave their
  own row; removing anyone else needs the subject's edit permission (`register.edit`,
  `cases.contribute`).
- **Ids only in the audit.** Each add, removal and leave records one event holding ids, and
  the title is the library's.

A case's contributor teams are its team participants (D-20): the assessment stores no list,
and each change to them is one add or one remove here, never a replacement of the whole.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.cases import logic as case_logic
from apps.cases import state
from apps.collab.models import Participant
from apps.collab.schemas import CollabParticipant, CollabParticipantPage, CollabTeamRef
from apps.identity.models import Membership, UserStatus
from apps.library.reading import obligation_headings
from apps.register.logic import ensure_register_entry
from apps.register.models import TenantObligation
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import Tenant
from apps.shared.vocabulary import label_for
from apps.taxonomy.models import Team
from apps.taxonomy.schemas import PersonRef

SUBJECT_TYPE = "tenant_obligation"
ADDED = "participant.added"
REMOVED = "participant.removed"
LEFT = "participant.left"


@dataclass(frozen=True)
class _Subject:
    """The one record a participation hangs on, as the shared steps need it: the register
    entry or the case its id names, its audit subject, and who may read and edit it."""

    id: uuid.UUID
    on_case: bool
    audit_type: str
    title: str
    read_permission: str
    edit_permission: str

    @property
    def entry_id(self) -> uuid.UUID | None:
        return None if self.on_case else self.id

    @property
    def case_id(self) -> uuid.UUID | None:
        return self.id if self.on_case else None

    def rows(self) -> QuerySet[Participant]:
        return Participant.objects.filter(tenant_obligation_id=self.entry_id, case_id=self.case_id)


def _not_found() -> ProblemError:
    return ProblemError(status=404, code="not_found", detail="Not found.")


# ---------------------------------------------------------------------------------------
# The shared steps
# ---------------------------------------------------------------------------------------
def _out(row: Participant, order: list[str]) -> CollabParticipant:
    return CollabParticipant(
        id=row.id,
        person=PersonRef(id=row.user.id, name=row.user.name) if row.user is not None else None,
        team=CollabTeamRef(key=row.team.key, label=label_for(row.team, order)) if row.team is not None else None,
        added_by=PersonRef(id=row.added_by.id, name=row.added_by.name),
        added_at=row.added_at,
    )


def _page(rows: QuerySet[Participant], *, order: list[str], limit: int, offset: int) -> CollabParticipantPage:
    live = rows.filter(removed_at__isnull=True)
    page = live.select_related("user", "team", "added_by").prefetch_related("team__labels")[offset : offset + limit]
    return CollabParticipantPage(items=[_out(row, order) for row in page], total=live.count())


def _member_who_can_read(user_id: uuid.UUID, read_permission: str) -> uuid.UUID:
    """The user, if they are an active member of the bank whose roles read the record.
    Read under row-level security, so another bank's member is simply not found."""
    granted = list(
        Membership.objects.filter(user_id=user_id, deactivated_at__isnull=True, user__status=UserStatus.ACTIVE.value)
        .values_list("roles__permissions", flat=True)
    )
    if not granted:
        raise ValidationError("That person is not a member here.", code="unknown_member")
    if not any(read_permission in (permissions or []) for permissions in granted):
        raise ValidationError("That person cannot open this record, so they cannot take part in it.", code="participant_cannot_read")
    return user_id


def _team(team_key: str) -> Team:
    team = Team.objects.filter(key=team_key.strip().lower(), active=True).first()  # ordering: unique (tenant, key), at most one row
    if team is None:
        raise ValidationError("There is no such team.", code="unknown_key")
    return team


def _who(user_id: uuid.UUID | None, team_key: str | None, read_permission: str) -> tuple[uuid.UUID | None, Team | None]:
    """The person or the team an add names, each checked before anything is written."""
    person = _member_who_can_read(user_id, read_permission) if user_id is not None else None
    team = _team(team_key) if team_key is not None else None
    return person, team


def _add(
    subject: _Subject,
    *,
    tenant_id: uuid.UUID,
    person: uuid.UUID | None,
    team: Team | None,
    caller_id: uuid.UUID,
    actor: Actor,
    order: list[str],
) -> CollabParticipant:
    """Name the checked person or team on the subject, whose row the caller has locked, so
    two adds at once can neither both pass the cap nor both add the same participant."""
    live = subject.rows().filter(removed_at__isnull=True)
    same = live.filter(user_id=person) if person is not None else live.filter(team=team)
    if same.exists():
        raise ValidationError("They already take part in this.", code="already_participant")
    if live.count() >= settings.MAX_PARTICIPANTS_PER_RECORD:
        raise ValidationError(
            f"A record holds at most {settings.MAX_PARTICIPANTS_PER_RECORD} participants.", code="too_many_participants"
        )
    row = Participant.objects.create(
        tenant_id=tenant_id,
        tenant_obligation_id=subject.entry_id,
        case_id=subject.case_id,
        user_id=person,
        team=team,
        added_by_id=caller_id,
    )
    record(
        action=ADDED,
        actor=actor,
        subject_type=subject.audit_type,
        subject_id=subject.id,
        subject_title=subject.title,
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


def _remove(
    subject: _Subject | None,
    *,
    tenant_id: uuid.UUID,
    participant_id: uuid.UUID,
    caller_id: uuid.UUID,
    actor: Actor,
    can_edit: bool,
) -> None:
    """End one live participation on the subject. The person named on it leaves
    (`participant.left`); anyone else removes it (`participant.removed`) and needs the
    subject's edit permission. No subject, another bank's participant, one already ended
    and an unknown id are all `not_found`."""
    row = (
        subject.rows().select_for_update().filter(id=participant_id, removed_at__isnull=True).first()  # ordering: pk lookup, at most one row
        if subject is not None
        else None
    )
    if subject is None or row is None:
        raise _not_found()
    leaving = row.user_id == caller_id
    if not leaving and not can_edit:
        raise ProblemError(
            status=403,
            code="permission_denied",
            detail="You do not have access to this.",
            required_permission=subject.edit_permission,
        )
    row.removed_at = timezone.now()
    row.removed_by_id = caller_id
    row.save(update_fields=["removed_at", "removed_by"])
    record(
        action=LEFT if leaving else REMOVED,
        actor=actor,
        subject_type=subject.audit_type,
        subject_id=subject.id,
        subject_title=subject.title,
        summary="Participant left." if leaving else "Participant removed.",
        tenant_id=tenant_id,
        after={"participantId": str(row.id)},
    )


# ---------------------------------------------------------------------------------------
# A register entry
# ---------------------------------------------------------------------------------------
def _title(obligation_id: uuid.UUID) -> str:
    """The obligation's library title for the audit row, read under row-level security: an
    obligation this bank cannot see is `not_found`, exactly as one that never existed."""
    heading = obligation_headings([obligation_id], []).get(obligation_id)
    if heading is None:
        raise _not_found()
    return f"{heading.instrument_short_name}, {heading.reference_label}"


def _entry(obligation_id: uuid.UUID) -> TenantObligation | None:
    return TenantObligation.objects.filter(obligation_id=obligation_id).first()  # ordering: unique per bank, at most one row


def _entry_subject(entry_id: uuid.UUID, title: str) -> _Subject:
    return _Subject(
        id=entry_id,
        on_case=False,
        audit_type=SUBJECT_TYPE,
        title=title,
        read_permission=perms.REGISTER_READ,
        edit_permission=perms.REGISTER_EDIT,
    )


def list_participants(*, obligation_id: uuid.UUID, order: list[str], limit: int, offset: int) -> CollabParticipantPage:
    """The live participants of the bank's register entry on the obligation, in the order
    they were added. An obligation nobody has worked on has no entry and an empty list: a
    read never creates one."""
    title = _title(obligation_id)
    entry = _entry(obligation_id)
    if entry is None:
        return CollabParticipantPage(items=[], total=0)
    return _page(_entry_subject(entry.id, title).rows(), order=order, limit=limit, offset=offset)


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
    entry on the first add; a refused add leaves no entry behind."""
    title = _title(obligation_id)
    person, team = _who(user_id, team_key, perms.REGISTER_READ)
    entry = ensure_register_entry(tenant_id=tenant_id, obligation_id=obligation_id, actor=actor)
    TenantObligation.objects.select_for_update().filter(id=entry.id).first()  # ordering: pk lookup, at most one row
    return _add(
        _entry_subject(entry.id, title), tenant_id=tenant_id, person=person, team=team, caller_id=caller_id, actor=actor, order=order
    )


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
    """End one participation on the bank's register entry for the obligation; removing
    anyone else's needs `register.edit`."""
    title = _title(obligation_id)
    entry = _entry(obligation_id)
    _remove(
        _entry_subject(entry.id, title) if entry is not None else None,
        tenant_id=tenant_id,
        participant_id=participant_id,
        caller_id=caller_id,
        actor=actor,
        can_edit=can_edit,
    )


# ---------------------------------------------------------------------------------------
# A case
# ---------------------------------------------------------------------------------------
def _case_subject(tenant: Tenant, change_id: uuid.UUID, *, for_update: bool = False) -> tuple[_Subject, CaseStatusCategory]:
    """The bank's case for the change, through the case workflow's own loader, so a change
    this bank has no case for is the same 404 as another bank's case; `for_update` locks
    it until the request's transaction ends."""
    case = case_logic.load_case(tenant, change_id, for_update=for_update)
    subject = _Subject(
        id=case.id,
        on_case=True,
        audit_type=case_logic.SUBJECT_TYPE,
        title=case.change.title,
        read_permission=perms.CASES_READ,
        edit_permission=perms.CASES_CONTRIBUTE,
    )
    return subject, CaseStatusCategory(case.status)


def list_case_participants(*, tenant: Tenant, change_id: uuid.UUID, order: list[str], limit: int, offset: int) -> CollabParticipantPage:
    """The live participants of the bank's case for the change, in the order they were added."""
    subject, _ = _case_subject(tenant, change_id)
    return _page(subject.rows(), order=order, limit=limit, offset=offset)


@transaction.atomic
def add_case_participant(
    *,
    tenant: Tenant,
    change_id: uuid.UUID,
    user_id: uuid.UUID | None,
    team_key: str | None,
    caller_id: uuid.UUID,
    actor: Actor,
    order: list[str],
) -> CollabParticipant:
    """Name a person or a team on the bank's case for the change. A closed or dismissed
    case takes nobody new: `invalid_transition`, as the state machine says of any move out
    of it."""
    subject, category = _case_subject(tenant, change_id, for_update=True)
    if not state.is_open(category):
        raise state.InvalidTransition("invalid_transition")
    person, team = _who(user_id, team_key, perms.CASES_READ)
    return _add(subject, tenant_id=tenant.id, person=person, team=team, caller_id=caller_id, actor=actor, order=order)


@transaction.atomic
def remove_case_participant(
    *,
    tenant: Tenant,
    change_id: uuid.UUID,
    participant_id: uuid.UUID,
    caller_id: uuid.UUID,
    actor: Actor,
    can_contribute: bool,
) -> None:
    """End one participation on the bank's case for the change; removing anyone else's
    needs `cases.contribute`. It ends on a closed case too: the stamp rewrites nothing, and
    the case file keeps that they took part until then."""
    subject, _ = _case_subject(tenant, change_id, for_update=True)
    _remove(
        subject, tenant_id=tenant.id, participant_id=participant_id, caller_id=caller_id, actor=actor, can_edit=can_contribute
    )

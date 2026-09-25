"""The notices that taking part and a changed item send (COL-02, COL-04, HOM-05, D-25, D-97).

Each producer names candidates and a reason and decides nothing else: who is an active
member, who can read the record, who switched the kind off and who hears once are
`notify()`'s alone. The person who performed the act is never a candidate.

- **`participant_added`** is sent from the add itself, in the transaction that writes the
  participant row and its audit event, to the person added or to the members of the team
  added.
- **`involved_item_changed`** follows the two library events D-25 names and no third: a
  confirmed WAT-04 link from a change to an obligation (`regulatory_change.curation_confirmed`,
  confirmed by a person or by an independent agent, D-97) and a new version applied to an
  obligation (`obligation.version_applied`). Both are the library's events, written with no
  tenant, so this module reads them off the one ordered cursor rather than being called from
  library or watch code: the handlers are registered from `CollabConfig.ready()` and fan out
  one `@tenant_task` per active bank, each writing only its own bank's notices. A suggestion
  nobody confirmed writes no `curation_confirmed` row, so it notifies nobody.

The people involved in a bank's register entry are the ones My work counts (HOM-05): its
first-line owner and owning team, the owners and owning teams of its rows per legal entity,
and its live participants, people and teams. A team reaches its members.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable

from apps.collab.logic import notify
from apps.collab.models import NotificationKind, Participant
from apps.proposals.reading import VERSION_APPLIED
from apps.register.models import TenantObligation, TenantObligationScope
from apps.shared import outbox, tenancy
from apps.shared.audit import ActorType
from apps.shared.models import OutboxEvent, Tenant, TenantStatus
from apps.tenants.models import TeamMember
from apps.watch.curation import CURATION_CONFIRMED

REGISTER_ENTRY = "tenant_obligation"
# What a confirmation's audit row names an obligation link by (`watch/curation.py` `_names`).
OBLIGATION_LINK = "obligation:"


def register() -> None:
    """Put both handlers on the one cursor. Called from `CollabConfig.ready()`; safe to call
    twice, because `register_handler` counts the same function once."""
    outbox.register_handler(CURATION_CONFIRMED, after_link_confirmed)
    outbox.register_handler(VERSION_APPLIED, after_version_applied)


# ---------------------------------------------------------------------------------------
# participant_added
# ---------------------------------------------------------------------------------------
def participant_added(
    *,
    tenant_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    user_id: uuid.UUID | None,
    team_id: uuid.UUID | None,
    added_by_id: uuid.UUID,
) -> None:
    """Tell the person added, or the members of the team added, that they now take part in
    the record. Runs in the add's transaction; the adder is never told."""
    candidates: list[tuple[uuid.UUID, str]] = []
    if user_id is not None:
        candidates = [(user_id, "participant")]
    elif team_id is not None:
        candidates = [(person, "team") for person in _members([team_id])[team_id]]
    notify(
        tenant_id=tenant_id,
        kind=NotificationKind.PARTICIPANT_ADDED,
        subject_type=subject_type,
        subject_id=subject_id,
        candidates=[(person, reason) for person, reason in candidates if person != added_by_id],
    )


# ---------------------------------------------------------------------------------------
# involved_item_changed
# ---------------------------------------------------------------------------------------
def after_link_confirmed(event: OutboxEvent) -> None:
    """The obligations whose link to a change this confirmation confirmed, each told to the
    people involved in it at every bank. Type, flag and term confirmations name no item."""
    confirmed = event.audit_event.after.get("confirmed") or []
    ids = [uuid.UUID(name.removeprefix(OBLIGATION_LINK)) for name in confirmed if name.startswith(OBLIGATION_LINK)]
    _fan_out(event, ids)


def after_version_applied(event: OutboxEvent) -> None:
    """The obligation a new version was applied to, told to the people involved in it at
    every bank."""
    obligation_id = event.audit_event.subject_id
    _fan_out(event, [obligation_id] if obligation_id is not None else [])


def _fan_out(event: OutboxEvent, obligation_ids: list[uuid.UUID]) -> None:
    """One `@tenant_task` per active bank, read in full before the first writes, each in its
    own zone. The person who confirmed or applied is left out; an agent is nobody's member."""
    if not obligation_ids:
        return
    audit = event.audit_event
    actor_id = audit.actor_id if audit.actor_type == ActorType.USER.value else None
    tenant_ids = list(Tenant.objects.filter(status=TenantStatus.ACTIVE.value).order_by("slug").values_list("id", flat=True))
    for tenant_id in tenant_ids:
        _notify_bank(tenant_id, obligation_ids, actor_id)


@tenancy.tenant_task
def _notify_bank(tenant_id: uuid.UUID, obligation_ids: list[uuid.UUID], actor_id: uuid.UUID | None) -> None:
    """This bank's register entries on the obligations, each told to the people involved in
    it, in four queries whatever the number of entries and people, and one for a bank that
    has no entry on them."""
    entries = list(
        TenantObligation.objects.filter(obligation_id__in=obligation_ids).values_list(
            "id", "first_line_owner_id", "owner_team_id"
        )
    )
    if not entries:
        return
    people: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    teams: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    rows = [
        *((entry, owner, team, "owner") for entry, owner, team in entries),
        *(
            (entry, owner, team, "owner")
            for entry, owner, team in TenantObligationScope.objects.filter(
                tenant_obligation__obligation_id__in=obligation_ids
            ).values_list("tenant_obligation_id", "owner_id", "owner_team_id")
        ),
        *(
            (entry, user, team, "participant")
            for entry, user, team in Participant.objects.filter(
                tenant_obligation__obligation_id__in=obligation_ids, removed_at__isnull=True
            ).values_list("tenant_obligation_id", "user_id", "team_id")
        ),
    ]
    entry_ids: set[uuid.UUID] = set()
    for entry, person, team, reason in rows:
        entry_ids.add(entry)
        if person is not None:
            people[entry].append((person, reason))
        if team is not None:
            teams[entry].add(team)
    members = _members({team for entry in teams.values() for team in entry})
    for entry in sorted(entry_ids):
        candidates = people[entry] + [(person, "team") for team in teams[entry] for person in members.get(team, [])]
        notify(
            tenant_id=tenant_id,
            kind=NotificationKind.INVOLVED_ITEM_CHANGED,
            subject_type=REGISTER_ENTRY,
            subject_id=entry,
            candidates=[(person, reason) for person, reason in candidates if person != actor_id],
        )


def _members(team_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Each team's people, in one query; `notify()` keeps only the active readers."""
    found: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    ids = set(team_ids)
    if ids:
        for team_id, user_id in TeamMember.objects.filter(team_id__in=ids).values_list("team_id", "user_id"):
            found[team_id].append(user_id)
    return found

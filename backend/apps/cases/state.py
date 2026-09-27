"""The case state machine (CAS-02, CAS-06, CAS-08; data-model "Case status machine").

One pure module: no database, no model, no query. It decides every case move from the
seven fixed categories and a small `CaseFacts` value, and everything else reads it —
`allowedTransitions` on a case response is `allowed_transitions()`, and every move goes
through `check_transition()` before anything is written. No other file holds a
transition table.

A sub-status is not a state. A tenant's sub-statuses are vocabulary rows that sit inside
one category (VOC-04); this module takes and returns categories only, so an admin who
adds, renames or retires a sub-status never changes what a case may do next.

The categories and guards are fixed (CLAUDE.md section 5). Every refusal is an
`InvalidTransition` — Django's `ValidationError` with a `code` — which config/api.py turns
into RFC 9457 problem details, so the client branches on the code and no trace leaves.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError

from apps.shared.kinds import CaseStatusCategory, CloseReason

C = CaseStatusCategory

TRANSITIONS: dict[CaseStatusCategory, tuple[CaseStatusCategory, ...]] = {
    C.NEW: (C.ASSIGNED, C.DISMISSED),
    C.DISMISSED: (C.NEW,),
    C.ASSIGNED: (C.ASSESSING, C.CLOSED),
    C.ASSESSING: (C.IMPLEMENTING, C.CLOSED),
    C.IMPLEMENTING: (C.SIGNOFF,),
    C.SIGNOFF: (C.IMPLEMENTING, C.CLOSED),
    # Only a one-person close reopens; a signed-off close stays final (the guard below).
    C.CLOSED: (C.NEW,),
}

# The close reasons one person may choose. Anything else needs the sign-off route and a
# second person.
ONE_PERSON_CLOSE = frozenset({CloseReason.NO_ACTION, CloseReason.NOT_APPLICABLE})

# The codes a refusal may carry (playbook 4.4). The four the contract already names, plus
# the three a request that leaves out what its move must supply is refused with.
REFUSAL_CODES = frozenset(
    {
        "invalid_transition",
        "open_actions",
        "evidence_missing",
        "four_eyes_violation",
        "owner_required",
        "reason_required",
        "why_required",
    }
)


@dataclass(frozen=True, kw_only=True)
class CaseFacts:
    """What the guards read about a case, the move and the person making it.

    Built fresh for every read and every move; never stored. The fields a move itself
    supplies — the owner a triage names, the reason a dismissal or a close gives — are
    read only by `check_transition()`, because a read cannot know them.
    """

    owner_set: bool  # the case has an owner, or the triage names one
    reason_given: bool  # the dismissal names a dismissal reason
    why_saved: bool  # the impact assessment's why is saved
    open_action_count: int  # live actions not yet done
    clean_evidence_count: int  # live evidence the scanner passed
    signoff_requester: UUID | None  # who asked for sign-off, when someone has
    actor: UUID | None  # who reads the case or makes the move
    # The close reason in play: the one a close chooses, or the one a closed case carries.
    close_reason_kind: CloseReason | None


@dataclass(frozen=True)
class Guard:
    """A named predicate on one edge. `on_request` guards test what the move supplies."""

    name: str
    code: str
    holds: Callable[[CaseFacts], bool]
    on_request: bool = False


_ONE_PERSON_CLOSE_GUARDS = (
    Guard(name="close_reason_given", code="reason_required", holds=lambda f: f.close_reason_kind is not None, on_request=True),
    Guard(name="one_person_close", code="four_eyes_violation", holds=lambda f: f.close_reason_kind in ONE_PERSON_CLOSE, on_request=True),
)

GUARDS: dict[tuple[CaseStatusCategory, CaseStatusCategory], tuple[Guard, ...]] = {
    (C.NEW, C.ASSIGNED): (Guard(name="owner_on_triage", code="owner_required", holds=lambda f: f.owner_set, on_request=True),),
    (C.NEW, C.DISMISSED): (Guard(name="reason_on_dismissal", code="reason_required", holds=lambda f: f.reason_given, on_request=True),),
    (C.ASSIGNED, C.CLOSED): _ONE_PERSON_CLOSE_GUARDS,
    (C.ASSESSING, C.IMPLEMENTING): (Guard(name="why_saved", code="why_required", holds=lambda f: f.why_saved),),
    (C.ASSESSING, C.CLOSED): _ONE_PERSON_CLOSE_GUARDS,
    (C.IMPLEMENTING, C.SIGNOFF): (
        Guard(name="no_open_action", code="open_actions", holds=lambda f: f.open_action_count == 0),
        Guard(name="clean_evidence", code="evidence_missing", holds=lambda f: f.clean_evidence_count >= 1),
    ),
    (C.SIGNOFF, C.CLOSED): (
        Guard(
            name="second_person",
            code="four_eyes_violation",
            holds=lambda f: f.signoff_requester is not None and f.actor is not None and f.actor != f.signoff_requester,
        ),
    ),
    (C.CLOSED, C.NEW): (
        Guard(name="restorable_close", code="invalid_transition", holds=lambda f: f.close_reason_kind in ONE_PERSON_CLOSE),
    ),
}

_DETAIL = {
    "invalid_transition": "This case cannot move there from where it is now.",
    "owner_required": "Choose an owner to triage the case.",
    "reason_required": "Choose a reason.",
    "why_required": "Save why the change matters before starting the work.",
    "open_actions": "Every action must be done before sign-off can be requested.",
    "evidence_missing": "Attach at least one piece of evidence before requesting sign-off.",
    "four_eyes_violation": "A second person must sign off.",
}


class InvalidTransition(ValidationError):
    """A refused move, carrying `invalid_transition` or the failing guard's own code."""

    def __init__(self, code: str) -> None:
        super().__init__(_DETAIL[code], code=code)


def check_transition(
    from_status: CaseStatusCategory, to_status: CaseStatusCategory, facts: CaseFacts
) -> None:
    """Raise `InvalidTransition` unless the move is drawn and every guard on it holds."""
    if to_status not in TRANSITIONS[from_status]:
        raise InvalidTransition("invalid_transition")
    for guard in GUARDS.get((from_status, to_status), ()):
        if not guard.holds(facts):
            raise InvalidTransition(guard.code)


def allowed_transitions(category: CaseStatusCategory, facts: CaseFacts) -> list[CaseStatusCategory]:
    """The categories a case may move to from `category`, for every category.

    Guards on what the move supplies are left to `check_transition()`: a new case lists
    triage although nobody has named its owner yet, because the triage names one.
    """
    return [
        to_status
        for to_status in TRANSITIONS[category]
        if all(guard.on_request or guard.holds(facts) for guard in GUARDS.get((category, to_status), ()))
    ]


def is_open(category: CaseStatusCategory) -> bool:
    """A case is open until it is closed or dismissed."""
    return category not in (C.CLOSED, C.DISMISSED)

"""Routes of the collab app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

Eight operations, declared here at once so the inbox, the comments panel and My work can be
built against one contract while the logic arrives (CHUNK10_TASKS rule 3). Each calls a named
function in the module that will own it — `collab/inbox.py`, `collab/comments.py` and
`collab/me_comments.py` — which answers 501 `not_built` until its task lands.

Every route takes a person's session in a bank, and no API key reaches any of them: a
notification is one person's and a comment is one bank's own text. Six carry no decorator
and are listed in `UNGATED_BY_DESIGN` (apps/shared/permissions.py) with their reason: the
three inbox routes and `GET /me/comments` act on the caller's own rows (`self`), and
`GET /comments` and `POST /comments` are gated by the read permission of the record's kind,
which the subject registry decides per record (`logic-gate`); the write also needs
`comments.write`, checked here with the structured 403. Editing and deleting carry
`comments.write`, and the author check is the logic's.

No collab write asks for a step-up: playbook 4.2 lists none of them (CHUNK10_TASKS).

Three more list, add and remove the participants of a register entry (COL-04), in
`collab/participants.py`. Reading needs `register.read` and adding `register.edit`;
removing is `logic-gate`, because a person may always leave their own row and removing
anyone else needs `register.edit` (D-19). Participation approves nothing and grants nothing,
so none of them asks for a step-up.
"""

import uuid
from typing import Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.collab import comments, inbox, me_comments, participants
from apps.collab.schemas import (
    CollabComment,
    CollabCommentCreated,
    CollabCommentInput,
    CollabCommentPage,
    CollabCommentPatch,
    CollabCommentQuery,
    CollabMyCommentPage,
    CollabMyCommentQuery,
    CollabNotificationPage,
    CollabNotificationQuery,
    CollabParticipant,
    CollabParticipantInput,
    CollabParticipantPage,
)
from apps.shared import permissions as perms
from apps.shared.authentication import SessionAuth
from apps.shared.permissions import requires_permission
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, caller_user, principal, require_any
from apps.taxonomy.reading import language_order

router = Router(tags=["Collab"])

SESSION = SessionAuth()

_NOTIFICATION_ID = (
    "The notification to mark read, as a uuid from `GET /notifications`. Another person's "
    "notification, or one in another bank, answers 404, never 403, so no id can be probed."
)
_OBLIGATION_ID = (
    "The obligation, as a uuid from the inventory. The participants are this bank's own, on its "
    "register entry for the obligation. An obligation the bank cannot see, such as another "
    "bank's private one, answers 404, never 403, so no id can be probed."
)
_PARTICIPANT_ID = (
    "The participation, as a uuid from `GET /obligations/{obligationId}/participants`. One on "
    "another bank's register, one that has already ended and one on another obligation answer "
    "404, never 403, so no id can be probed."
)
_COMMENT_ID = (
    "The comment, as a uuid from `GET /comments`. A comment in another bank answers 404, never "
    "403, so no id can be probed."
)


def _member(request: HttpRequest) -> None:
    """A person's session in a bank: a platform session has no bank and gets the 404 every
    tenant read gives it."""
    caller_tenant(request)
    caller_user(request)


# ---------------------------------------------------------------------------------------
# The notification inbox (COL-02)
# ---------------------------------------------------------------------------------------
@router.get(
    "/notifications",
    response=CollabNotificationPage,
    auth=SESSION,
    operation_id="listNotifications",
    by_alias=True,
    summary="See what you have been told about",
)
@answers_problems
def list_notifications(request: HttpRequest, query: Query[CollabNotificationQuery]) -> Any:
    """The caller's own notifications in their bank, newest first: mentions, assignments,
    reminders, escalations and the records they take part in. Call it for the inbox and, with
    `unread=true`, for the count on the bell.

    A read: it changes nothing and writes no audit row. Any person's session in a bank; no
    API key reaches it. It lists the caller's own rows only and takes no parameter that could
    name anyone else's. A notification whose record the caller can no longer read is still
    listed with the title it was sent with, and its link answers 404 when followed.

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. Nothing to tell is a
    200 with an empty `items`, never a 404.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `not_found` for a platform session, which belongs to no bank, and
    `validation_error` for a `limit` above the maximum or below 1.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    # Ungated by design: self (the caller's own notification rows).
    _member(request)
    return inbox.list_notifications()


@router.post(
    "/notifications/read-all",
    response={204: None},
    auth=SESSION,
    operation_id="markAllNotificationsRead",
    by_alias=True,
    summary="Mark all your notifications read",
)
@answers_problems
def mark_all_notifications_read(request: HttpRequest) -> Any:
    """Mark every unread notification of the caller in their bank read at once, for the
    inbox's "Mark all read". Other people's notifications are untouched, whatever the
    caller's role.

    Sets the read time on the caller's unread rows in one statement and records one audit
    event naming the caller, with ids and never a title. Any person's session in a bank; no
    API key reaches it. Answers 204 with no body, also when nothing was unread.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, and `not_found` for a platform session, which belongs to no bank.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    # Ungated by design: self (the caller's own notification rows).
    _member(request)
    return inbox.mark_all_read()


@router.post(
    "/notifications/{notification_id}/read",
    response={204: None},
    auth=SESSION,
    operation_id="markNotificationRead",
    by_alias=True,
    summary="Mark one notification read",
)
@answers_problems
def mark_notification_read(
    request: HttpRequest, notification_id: uuid.UUID = Path(..., description=_NOTIFICATION_ID)
) -> Any:
    """Mark one of the caller's notifications read, when they open it from the inbox.

    Sets its read time once and records an audit event holding ids only; marking it again
    changes nothing and still answers 204. Any person's session in a bank; no API key reaches
    it. Answers 204 with no body.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, and `not_found` for a platform session or for a notification that is
    not the caller's own, in their bank.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    # Ungated by design: self (the caller's own notification rows).
    _member(request)
    return inbox.mark_read()


# ---------------------------------------------------------------------------------------
# Comments on a record (COL-01)
# ---------------------------------------------------------------------------------------
@router.get(
    "/comments",
    response=CollabCommentPage,
    auth=SESSION,
    operation_id="listComments",
    by_alias=True,
    summary="Read the comments on a record",
)
@answers_problems
def list_comments(request: HttpRequest, query: Query[CollabCommentQuery]) -> Any:
    """The comments on one record of the caller's bank, oldest first, for the record's
    "Comments" panel. The record is named by its kind and id in the query string.

    A read: it changes nothing and writes no audit row. Any person's session in a bank whose
    role can read that kind of record (`register.read` for the inventory's records,
    `cases.read` for a case and its actions); no API key reaches it. A deleted comment keeps
    its place without its text, and `canEdit` and `canDelete` say what the caller may do with
    each one.

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. A record nobody has
    commented on is a 200 with an empty `items`.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `not_found` for a platform session and for a record the bank does not
    hold or the caller may not read, and `validation_error` for a missing or malformed kind or
    id, or a `limit` outside 1 to 100. A kind comments are not taken on is refused with a 422.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    # Ungated by design: logic-gate (the read permission of the subject's kind, per record).
    _member(request)
    return comments.list_comments()


@router.post(
    "/comments",
    response={201: CollabCommentCreated},
    auth=SESSION,
    operation_id="addComment",
    by_alias=True,
    summary="Comment on a record and mention people",
)
@answers_problems
def add_comment(request: HttpRequest, body: CollabCommentInput) -> Any:
    """Write a comment on one record of the caller's bank, optionally naming people, for the
    record's "Comments" panel and My work's composer. Everyone in the bank who can read the
    record can read the comment: there are no private comments.

    Needs a person's session in a bank holding `comments.write` and a role that can read the
    record's kind; no API key reaches it. It stores the comment and one row per person
    mentioned and records one audit event holding the comment's id and the mentioned people's
    ids — never the text, which reaches no log, notification, mail or model. Each mentioned
    member who can read the record is notified once; the others are returned in
    `undeliveredMentions` by name so the composer can say the mention did not reach them.
    Answers 201 with the comment.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `permission_denied` without `comments.write` (naming it in
    `requiredPermission`), `not_found` for a platform session and for a record the bank does
    not hold or the caller may not read, and `validation_error` for an empty text, a field the
    body does not name or a malformed id. A kind comments are not taken on, a text longer than
    the deployment allows and a mentioned id that is not a member of the bank are refused with
    a 422.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    # Ungated by design: logic-gate (the read permission of the subject's kind, per record);
    # comments.write is checked here so the 403 names it before the logic runs.
    require_any(request, perms.COMMENTS_WRITE)
    _member(request)
    return comments.add_comment()


@router.patch(
    "/comments/{comment_id}",
    response=CollabComment,
    auth=SESSION,
    operation_id="editComment",
    by_alias=True,
    summary="Correct your own comment",
)
@requires_permission(perms.COMMENTS_WRITE)
@answers_problems
def edit_comment(
    request: HttpRequest, body: CollabCommentPatch, comment_id: uuid.UUID = Path(..., description=_COMMENT_ID)
) -> Any:
    """Change the text of a comment the caller wrote, shortly after writing it. Nobody else
    may edit it, and no role grants that.

    Needs a person's session in a bank holding `comments.write`; no API key reaches it. Only
    the author may edit, and only within the deployment's edit window after writing (15
    minutes unless configured otherwise). The text it replaces is kept by the bank, never
    overwritten and returned by no call, and one audit event records the comment's id — never
    either text. Who was mentioned does not change, so an edit notifies nobody new. Answers
    200 with the comment.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `permission_denied` without `comments.write` (naming it in
    `requiredPermission`), `not_found` for a platform session and for a comment the bank does
    not hold, and `validation_error` for an empty text or a field the body does not name. An
    edit by someone other than the author is refused with a 403, and one after the window
    with a 409.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    _member(request)
    return comments.edit_comment()


@router.delete(
    "/comments/{comment_id}",
    response={204: None},
    auth=SESSION,
    operation_id="deleteComment",
    by_alias=True,
    summary="Delete your own comment",
)
@requires_permission(perms.COMMENTS_WRITE)
@answers_problems
def delete_comment(request: HttpRequest, comment_id: uuid.UUID = Path(..., description=_COMMENT_ID)) -> Any:
    """Take back a comment the caller wrote. Nobody else may delete it, and no role grants
    that.

    Needs a person's session in a bank holding `comments.write`; no API key reaches it. Only
    the author may delete. The comment is kept and marked deleted rather than removed, so the
    thread still reads; its text is no longer returned. One audit event records the comment's
    id and never its text. Deleting it again changes nothing. Answers 204 with no body.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `permission_denied` without `comments.write` (naming it in
    `requiredPermission`), and `not_found` for a platform session and for a comment the bank
    does not hold. A delete by someone other than the author is refused with a 403.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    _member(request)
    return comments.delete_comment()


# ---------------------------------------------------------------------------------------
# My comments and mentions, for My work (COL-01, HOM-05)
# ---------------------------------------------------------------------------------------
@router.get(
    "/me/comments",
    response=CollabMyCommentPage,
    auth=SESSION,
    operation_id="listMyComments",
    by_alias=True,
    summary="Find your comments and the ones that mention you",
)
@answers_problems
def list_my_comments(request: HttpRequest, query: Query[CollabMyCommentQuery]) -> Any:
    """The caller's own comments, or other people's comments that mention them, newest
    first, for My work's "Comments and mentions" panel. These shared comments are the notes on
    My work: everyone in the bank who can read a record can read its comments.

    A read: it changes nothing and writes no audit row. Any person's session in a bank; no API
    key reaches it. Only comments on records the caller can read today are listed; the kinds
    of record the caller's role cannot read are named in `permissionLimitedKinds`, never the
    records themselves.

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. Nothing to show is a
    200 with an empty `items`.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `not_found` for a platform session, which belongs to no bank, and
    `validation_error` for an `about` other than `written` or `mentioned`, or a `limit`
    outside 1 to 100.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    # Ungated by design: self (the caller's own comments and mentions).
    _member(request)
    return me_comments.list_my_comments()


# ---------------------------------------------------------------------------------------
# Participants of a register entry (COL-04, D-18, D-19)
# ---------------------------------------------------------------------------------------
@router.get(
    "/obligations/{obligation_id}/participants",
    response=CollabParticipantPage,
    auth=SESSION,
    operation_id="listObligationParticipants",
    by_alias=True,
    summary="See who takes part in an obligation",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_obligation_participants(
    request: HttpRequest, page: Query[PageQuery], obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """The people and teams taking part in the bank's register entry for an obligation, in
    the order they were added, for the obligation page's participants panel.

    A read: it changes nothing, writes no audit row and never creates a register entry. Needs
    a person's session in a bank holding `register.read`; no API key reaches it. Taking part
    grants nothing, so the list says who is involved and nothing about what they may do.

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. An obligation nobody
    takes part in, or that the bank has not worked on yet, is a 200 with an empty `items`.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `permission_denied` without `register.read` (naming it in
    `requiredPermission`), `not_found` for a platform session and for an obligation the bank
    cannot see, and `validation_error` for a `limit` outside 1 to 100.
    """
    tenant = caller_tenant(request)
    caller_user(request)
    return participants.list_participants(
        obligation_id=obligation_id,
        order=language_order(request, tenant=tenant),
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/obligations/{obligation_id}/participants",
    response={201: CollabParticipant},
    auth=SESSION,
    operation_id="addObligationParticipant",
    by_alias=True,
    summary="Add a person or a team to an obligation",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def add_obligation_participant(
    request: HttpRequest, body: CollabParticipantInput, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """Name a person or a team on the bank's register entry for an obligation, so it reaches
    their My work and their notifications. It grants them nothing: a participant still gets
    403 on anything their role lacks.

    Needs a person's session in a bank holding `register.edit`; no API key reaches it, and no
    step-up is asked, because taking part approves nothing. The first add on an obligation the
    bank has not worked on creates its register entry, with its own audit event. Records one
    audit event holding the participation's, the person's or the team's ids and never a name.
    A shared obligation lands on this bank's own entry and changes nothing another bank sees.
    Answers 201 with the participant.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `permission_denied` without `register.edit` (naming it in
    `requiredPermission`), `not_found` for a platform session and for an obligation the bank
    cannot see, `validation_error` for a body naming both or neither of `userId` and
    `teamKey`, or a field it does not name, `unknown_member` for a person who is not an active
    member of this bank, whether from another bank, deactivated or unknown, `unknown_key` for
    a team the bank has no active row for, `participant_cannot_read` for a member whose roles
    cannot read the register, `already_participant` (409) when they already take part, and
    `too_many_participants` when the entry already holds as many as the deployment allows (50
    unless configured otherwise).
    """
    tenant = caller_tenant(request)
    user = caller_user(request)
    return 201, participants.add_participant(
        tenant_id=tenant.id,
        obligation_id=obligation_id,
        user_id=body.user_id,
        team_key=body.team_key,
        caller_id=user.id,
        actor=actor_for(request, user),
        order=language_order(request, tenant=tenant),
    )


@router.delete(
    "/obligations/{obligation_id}/participants/{participant_id}",
    response={204: None},
    auth=SESSION,
    operation_id="removeObligationParticipant",
    by_alias=True,
    summary="Remove a participant, or leave an obligation",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def remove_obligation_participant(
    request: HttpRequest,
    obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID),
    participant_id: uuid.UUID = Path(..., description=_PARTICIPANT_ID),
) -> Any:
    """End one participation on the bank's register entry for an obligation: "Leave" on the
    caller's own row, or "Remove" on anyone else's.

    Needs a person's session in a bank holding `register.read`, which every participant held
    when they were added. With it, a person may always leave their own participation, and
    the audit event is `participant.left`; removing anyone else, a team included, also needs
    `register.edit`, and the audit event is `participant.removed`. Either holds ids only. The
    participation is ended with its time and who ended it, never deleted, so the record's
    history still shows who took part until when. No API key reaches it and no step-up is
    asked. Answers 204 with no body.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `permission_denied` without `register.read`, or for removing someone
    else without `register.edit` (naming the permission in `requiredPermission`), and `not_found` for a platform session, for an
    obligation the bank cannot see and for a participation that is not live on this bank's
    entry for it.
    """
    # register.edit for anyone else's row is checked by the logic on the row.
    tenant = caller_tenant(request)
    user = caller_user(request)
    participants.remove_participant(
        tenant_id=tenant.id,
        obligation_id=obligation_id,
        participant_id=participant_id,
        caller_id=user.id,
        actor=actor_for(request, user),
        can_edit=principal(request).has_permission(perms.REGISTER_EDIT),
    )
    return 204, None

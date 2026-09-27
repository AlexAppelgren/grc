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
"""

import uuid
from typing import Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.collab import comments, inbox, me_comments
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
)
from apps.shared import permissions as perms
from apps.shared.authentication import SessionAuth
from apps.shared.permissions import requires_permission
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, caller_user, principal, require_any

router = Router(tags=["Collab"])

SESSION = SessionAuth()

_NOTIFICATION_ID = (
    "The notification to mark read, as a uuid from `GET /notifications`. Another person's "
    "notification, or one in another bank, answers 404, never 403, so no id can be probed."
)
_COMMENT_ID = (
    "The comment, as a uuid from `GET /comments`. A comment in another bank answers 404, never "
    "403, so no id can be probed."
)


def _member(request: HttpRequest) -> Any:
    """A person's session in a bank: a platform session has no bank and gets the 404 every
    tenant read gives it. Returns the caller."""
    caller_tenant(request)
    return caller_user(request)


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
    """
    # Ungated by design: self (the caller's own notification rows).
    user = _member(request)
    return inbox.list_notifications(user=user, unread=query.unread, limit=query.limit, offset=query.offset)


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
    """
    # Ungated by design: self (the caller's own notification rows).
    inbox.mark_all_read(user=_member(request))
    return 204, None


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
    """
    # Ungated by design: self (the caller's own notification rows).
    inbox.mark_read(user=_member(request), notification_id=notification_id)
    return 204, None


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
    id, or a `limit` outside 1 to 100. A kind comments are not taken on is refused with a 422
    `unsupported_subject`.
    """
    # Ungated by design: logic-gate (the read permission of the subject's kind, per record).
    _member(request)
    return comments.list_comments(who=principal(request), user=caller_user(request), query=query)


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
    body does not name, a malformed id or a text of only spaces. A kind comments are not taken
    on is refused with a 422 `unsupported_subject`, a text longer than the deployment allows
    (4,000 characters unless configured otherwise) with a 422 `comment_too_long`, and a
    mentioned id that is not a member of the bank with a 422 `unknown_member`, the same answer
    for another bank's member as for an id nobody holds; each writes nothing.
    """
    # Ungated by design: logic-gate (the read permission of the subject's kind, per record);
    # comments.write is checked here so the 403 names it before the logic runs.
    require_any(request, perms.COMMENTS_WRITE)
    _member(request)
    user = caller_user(request)
    created = comments.add_comment(
        who=principal(request), actor=actor_for(request, user), user=user, tenant=caller_tenant(request), payload=body
    )
    return 201, created


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
    not hold or whose record the caller may not read, and `validation_error` for an empty text,
    a text of only spaces or a field the body does not name. A text longer than the deployment
    allows is refused with a 422 `comment_too_long`, an edit by someone other than the author
    with a 403 `not_author`, and one after the window or of a deleted comment with a 409
    `edit_window_closed`; each keeps nothing.
    """
    _member(request)
    user = caller_user(request)
    return comments.edit_comment(
        who=principal(request),
        actor=actor_for(request, user),
        user=user,
        tenant=caller_tenant(request),
        comment_id=comment_id,
        body=body.body,
    )


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
    does not hold or whose record the caller may not read. A delete by someone other than the
    author is refused with a 403 `not_author`.
    """
    _member(request)
    user = caller_user(request)
    comments.delete_comment(
        who=principal(request), actor=actor_for(request, user), user=user, tenant=caller_tenant(request), comment_id=comment_id
    )
    return 204, None


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
    records themselves. A deleted comment has no text left to read and is not listed.

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. Nothing to show is a
    200 with an empty `items`.

    Errors: `unauthenticated` without a session, `enrolment_only` for a session that may only
    finish enrolling, `not_found` for a platform session, which belongs to no bank, and
    `validation_error` for an `about` other than `written` or `mentioned`, or a `limit`
    outside 1 to 100.
    """
    # Ungated by design: self (the caller's own comments and mentions).
    tenant = caller_tenant(request)
    return me_comments.list_my_comments(
        who=principal(request),
        user=caller_user(request),
        tenant=tenant,
        about=query.about,
        limit=query.limit,
        offset=query.offset,
    )

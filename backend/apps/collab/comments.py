"""Comments on one record of one bank (COL-01), read, written, edited and deleted by their
author, with the mentions that notify (COL-02), and never logged.

The subject registry in `collab/subjects.py` decides which records take comments and who may
read each: a kind it does not hold is 422 `unsupported_subject`, and a record the caller may
not read, or that the bank does not hold, is 404, so the answer never says whether it exists.
The route has already refused a caller without a member session in a bank, and without
`comments.write` where the call writes.

The text is tenant content (CHUNK10_TASKS rule 13): the audit row takes the record's own
title as its subject title and ids in `after`, the log line carries ids, and the mention's
notification carries the record's title through `notify()`, in the comment's transaction.
An edit is the author's own inside `COMMENT_EDIT_MINUTES` and keeps the text it replaced in
an append-only revision (ruling 10); a delete is soft and the author's own.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.collab import subjects
from apps.collab.logic import notify
from apps.collab.models import Comment, CommentMention, CommentRevision, NotificationKind
from apps.collab.schemas import CollabComment, CollabCommentCreated, CollabCommentInput, CollabCommentPage, CollabCommentQuery
from apps.identity import roles_logic
from apps.identity.models import Membership, User
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy.schemas import PersonRef

logger = logging.getLogger(__name__)


def _not_found() -> ProblemError:
    return ProblemError(status=404, code="not_found", detail="Not found.")


def _readable(who: Principal, subject_type: str, subject_id: uuid.UUID) -> tuple[subjects.Subject, Any]:
    """The registry row and the record, when the caller's roles read its kind and the bank
    holds it under row-level security; otherwise 404, the same for both."""
    subject = subjects.subject(subject_type)
    found = subject.lookup(subject_id) if who.has_permission(subject.read_permission) else None
    if found is None:
        raise _not_found()
    return subject, found


def _checked_text(body: str) -> str:
    if not body.strip():
        raise ValidationError("Write something before sending.", code="validation_error")
    if len(body) > settings.COMMENT_MAX_CHARS:
        raise ValidationError(f"A comment can be at most {settings.COMMENT_MAX_CHARS} characters.", code="comment_too_long")
    return body


def _can_edit(comment: Comment, user_id: uuid.UUID, now: datetime.datetime) -> bool:
    return (
        comment.author_id == user_id
        and comment.deleted_at is None
        and now <= comment.created_at + datetime.timedelta(minutes=settings.COMMENT_EDIT_MINUTES)
    )


def _views(comments: list[Comment], user_id: uuid.UUID) -> list[CollabComment]:
    """The comments as the caller sees them, their authors and mentions fetched once."""
    mentions: dict[uuid.UUID, list[PersonRef]] = {}
    for mention in CommentMention.objects.filter(comment_id__in=[c.id for c in comments]).select_related("user"):
        mentions.setdefault(mention.comment_id, []).append(PersonRef(id=mention.user_id, name=mention.user.name))
    now = timezone.now()
    return [
        CollabComment(
            id=comment.id,
            subject_type=comment.subject_type,
            subject_id=comment.subject_id,
            body=None if comment.deleted_at else comment.body,
            mentions=mentions.get(comment.id, []),
            author=PersonRef(id=comment.author_id, name=comment.author.name),
            created_at=comment.created_at,
            edited_at=comment.edited_at,
            deleted_at=comment.deleted_at,
            can_edit=_can_edit(comment, user_id, now),
            can_delete=comment.author_id == user_id and comment.deleted_at is None,
        )
        for comment in comments
    ]


def _own(who: Principal, user: User, tenant: Tenant, comment_id: uuid.UUID) -> tuple[Comment, str]:
    """The caller's own comment, locked for the write, with its record's title for the
    audit row: another bank's comment, or one on a record the caller can no longer read, is
    404; someone else's is 403 `not_author`."""
    comment = Comment.objects.select_for_update().select_related("author").filter(pk=comment_id).first()  # ordering: pk lookup, at most one row
    if comment is None:
        raise _not_found()
    subject, found = _readable(who, comment.subject_type, comment.subject_id)
    if comment.author_id != user.id:
        raise ProblemError(status=403, code="not_author", detail="Only the person who wrote a comment can change it.")
    return comment, subject.title(found, roles_logic.language_order(user, tenant))


def list_comments(*, who: Principal, user: User, query: CollabCommentQuery) -> CollabCommentPage:
    """`GET /comments`: a record's comments, oldest first, a deleted one without its text."""
    _readable(who, query.subject_type, query.subject_id)
    rows = Comment.objects.filter(subject_type=query.subject_type, subject_id=query.subject_id)
    page = list(rows.select_related("author")[query.offset : query.offset + query.limit])
    return CollabCommentPage(items=_views(page, user.id), total=rows.count())


def add_comment(*, who: Principal, actor: Actor, user: User, tenant: Tenant, payload: CollabCommentInput) -> CollabCommentCreated:
    """`POST /comments`: the comment, one row per person mentioned and one audit event, then
    one mention notification per person who passes `notify()`'s recipient check, the author
    never, all in the request's transaction. Who was mentioned and not reached is returned by
    name, never with the reason."""
    subject_type, subject_id = payload.subject_type, payload.subject_id
    subject, found = _readable(who, subject_type, subject_id)
    text = _checked_text(payload.body)
    mentioned = list(dict.fromkeys(payload.mention_user_ids))
    people = {
        m.user_id: m.user for m in Membership.objects.filter(tenant_id=tenant.id, user_id__in=mentioned).select_related("user")
    }
    if len(people) != len(mentioned):
        raise ValidationError("Mention only people in your organisation.", code="unknown_member")

    comment = Comment.objects.create(tenant=tenant, subject_type=subject_type, subject_id=subject_id, author=user, body=text)
    CommentMention.objects.bulk_create(CommentMention(tenant=tenant, comment=comment, user_id=person) for person in mentioned)
    title = subject.title(found, roles_logic.language_order(user, tenant))
    record(
        action="comment.added",
        actor=actor,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_title=title,
        summary=f"{actor.label} commented on {title}",
        tenant_id=tenant.id,
        after={"commentId": str(comment.id), "mentionUserIds": [str(person) for person in mentioned]},
    )
    others = [person for person in mentioned if person != user.id]
    told = {
        row.user_id
        for row in notify(
            tenant_id=tenant.id,
            kind=NotificationKind.MENTION,
            subject_type=subject_type,
            subject_id=subject_id,
            candidates=[(person, "mention") for person in others],
        )
    }
    logger.info("comment added", extra={"comment_id": str(comment.id), "actor_id": str(user.id)})
    (view,) = _views([comment], user.id)
    return CollabCommentCreated(
        **view.model_dump(),
        undelivered_mentions=[PersonRef(id=person, name=people[person].name) for person in others if person not in told],
    )


def edit_comment(*, who: Principal, actor: Actor, user: User, tenant: Tenant, comment_id: uuid.UUID, body: str) -> CollabComment:
    """`PATCH /comments/{commentId}`: the author's own, inside the edit window. The text it
    replaces is written to a revision first; the mentions stay as written, so nobody new is
    told."""
    comment, title = _own(who, user, tenant, comment_id)
    if not _can_edit(comment, user.id, timezone.now()):
        raise ProblemError(status=409, code="edit_window_closed", detail="This comment can no longer be edited. You can still delete it.")
    text = _checked_text(body)
    revision = CommentRevision.objects.create(tenant_id=tenant.id, comment=comment, body=comment.body, edited_by=user)
    comment.body = text
    comment.edited_at = timezone.now()
    comment.save(update_fields=["body", "edited_at"])
    record(
        action="comment.edited",
        actor=actor,
        subject_type=comment.subject_type,
        subject_id=comment.subject_id,
        subject_title=title,
        summary=f"{actor.label} edited a comment on {title}",
        tenant_id=tenant.id,
        after={"commentId": str(comment.id), "revisionId": str(revision.id)},
    )
    logger.info("comment edited", extra={"comment_id": str(comment.id), "actor_id": str(user.id)})
    (view,) = _views([comment], user.id)
    return view


def delete_comment(*, who: Principal, actor: Actor, user: User, tenant: Tenant, comment_id: uuid.UUID) -> None:
    """`DELETE /comments/{commentId}`: the author's own, kept and marked deleted. A second
    delete changes nothing and records nothing."""
    comment, title = _own(who, user, tenant, comment_id)
    if comment.deleted_at is not None:
        return
    comment.deleted_at = timezone.now()
    comment.save(update_fields=["deleted_at"])
    record(
        action="comment.deleted",
        actor=actor,
        subject_type=comment.subject_type,
        subject_id=comment.subject_id,
        subject_title=title,
        summary=f"{actor.label} deleted a comment on {title}",
        tenant_id=tenant.id,
        after={"commentId": str(comment.id)},
    )
    logger.info("comment deleted", extra={"comment_id": str(comment.id), "actor_id": str(user.id)})

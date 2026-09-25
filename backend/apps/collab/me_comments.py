"""A person's own comments and mentions for My work's "Comments and mentions" panel (COL-01,
HOM-05), filtered by each record's read permission.

The subject registry (`collab/subjects.py`) decides what the caller may read: a comment on a
kind whose read permission the caller's roles lack is left out of the rows and of the total,
and the kind, never the record, is named in `permissionLimitedKinds`. Each row's title is
the record's own title in the caller's language order, read today, and a record the caller's
bank no longer shows under row-level security leaves its comment out.

A deleted comment has nothing left to read and is not listed. The body is tenant content the
caller may see: it travels in the response and nowhere else, and nothing here logs it.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any, Literal

from django.conf import settings
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.cases.models import ChangeCase
from apps.collab import subjects
from apps.collab.models import Comment, CommentMention
from apps.identity import roles_logic
from apps.identity.models import User
from apps.shared.authentication import Principal
from apps.shared.models import Tenant


def _person(user: User) -> dict[str, Any]:
    return {"id": user.id, "name": user.name}


def list_my_comments(
    *, who: Principal, user: User, tenant: Tenant, about: Literal["written", "mentioned"], limit: int, offset: int
) -> dict[str, Any]:
    """`GET /me/comments`: the caller's comments, or other people's that mention them,
    newest first, one page of those on kinds the caller can read."""
    readable = [kind for kind, row in subjects.SUBJECTS.items() if who.has_permission(row.read_permission)]
    if about == "written":
        matching = Comment.objects.filter(author=user)
    else:
        mentions_me = CommentMention.objects.filter(comment=OuterRef("pk"), user=user)
        matching = Comment.objects.filter(Exists(mentions_me)).exclude(author=user)
    matching = matching.filter(deleted_at__isnull=True, subject_type__in=list(subjects.SUBJECTS))
    limited = sorted(set(matching.exclude(subject_type__in=readable).values_list("subject_type", flat=True)))
    visible = matching.filter(subject_type__in=readable).select_related("author").order_by("-created_at", "-id")
    page = list(visible[offset : offset + limit])

    mentioned: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for mention in CommentMention.objects.filter(comment__in=page).select_related("user").order_by("user__name", "user_id"):
        mentioned[mention.comment_id].append(_person(mention.user))
    order = roles_logic.language_order(user, tenant)
    titles: dict[tuple[str, Any], str | None] = {}
    change_ids: dict[tuple[str, Any], Any] = {}
    for comment in page:
        key = (comment.subject_type, comment.subject_id)
        if key not in titles:
            subject = subjects.subject(comment.subject_type)
            found = subject.lookup(comment.subject_id)
            titles[key] = subject.title(found, order) if found is not None else None
            # A case's page is its change's page, so the row carries the change for the link.
            change_ids[key] = found.change_id if isinstance(found, ChangeCase) else None

    edit_until = timezone.now() - datetime.timedelta(minutes=settings.COMMENT_EDIT_MINUTES)
    items = [
        {
            "id": comment.id,
            "subject_type": comment.subject_type,
            "subject_id": comment.subject_id,
            "subject_title": titles[(comment.subject_type, comment.subject_id)],
            "change_id": change_ids[(comment.subject_type, comment.subject_id)],
            "body": comment.body,
            "mentions": mentioned[comment.id],
            "author": _person(comment.author),
            "created_at": comment.created_at,
            "edited_at": comment.edited_at,
            "deleted_at": comment.deleted_at,
            "can_edit": comment.author_id == user.id and comment.created_at > edit_until,
            "can_delete": comment.author_id == user.id,
        }
        for comment in page
        if titles[(comment.subject_type, comment.subject_id)] is not None
    ]
    return {"items": items, "total": visible.count(), "permission_limited_kinds": limited}

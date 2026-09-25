"""Request and response schemas of the collab app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Eight operations read and write these: a person's notification inbox, the comments on one
record, and a person's own comments and mentions on My work (COL-01, COL-02, HOM-05). Three
more list, add and remove the people and teams taking part in a register entry (COL-04). Every
list is a page of `{items, total}` on the shared `limit` and `offset` (playbook 10), which is
where the designed bare array of comments and the designed cursor on notifications were left
(INPUT_DELTAS §7).

A comment body is tenant content. It travels in a request body and a response body and never
in a path or a query string, because the access log and an error report keep the request
line (CHUNK10_TASKS ruling 9).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import ConfigDict, Field, JsonValue, model_validator

from apps.shared.schemas import CamelSchema, PageQuery, WriteBody
from apps.taxonomy.schemas import PersonRef

# `apps.collab.models.NotificationKind`, spelled out so the contract carries the set;
# tests_contract.py pins that the two never drift.
CollabNotificationKind = Literal[
    "assigned",
    "mention",
    "signoff_requested",
    "approval_requested",
    "due_soon",
    "overdue",
    "escalation",
    "proposal_waiting",
    "saved_search_hit",
    "participant_added",
    "involved_item_changed",
    "review_due",
]
CollabMyCommentsAbout = Literal["written", "mentioned"]

# The longest subject kind a comment or a notification can name: the `subject_type` column.
SUBJECT_TYPE_MAX = 64

_ANNA: dict[str, JsonValue] = {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Anna Berg"}
_ERIK: dict[str, JsonValue] = {"id": "3f6b2d1c-7e8a-4b90-8c1d-2e3f4a5b6c7d", "name": "Erik Holm"}
_COMMENT_EXAMPLE: dict[str, JsonValue] = {
    "id": "c0a1b2c3-d4e5-4f60-8a7b-9c0d1e2f3a4b",
    "subjectType": "change_case",
    "subjectId": "11111111-1111-4111-8111-111111111111",
    "body": "@Erik Holm can you check the custody angle before Friday?",
    "mentions": [_ERIK],
    "author": _ANNA,
    "createdAt": "2026-09-24T08:15:00Z",
    "editedAt": None,
    "deletedAt": None,
    "canEdit": True,
    "canDelete": True,
}
_NOTIFICATION_EXAMPLE: dict[str, JsonValue] = {
    "id": "5e4d3c2b-1a09-4f8e-9d7c-6b5a4f3e2d1c",
    "kind": "mention",
    "subjectType": "change_case",
    "subjectId": "11111111-1111-4111-8111-111111111111",
    "title": "FI adopts amended rules on paying for investment research",
    "createdAt": "2026-09-24T08:15:00Z",
    "readAt": None,
}

_SUBJECT_TYPE = (
    "The kind of record, as a fixed lowercase code of at most 64 characters. Comments are "
    "taken on four kinds: `obligation` (an obligation in the shared library, as this bank "
    "sees it), `tenant_obligation` (an item the bank keeps in its own inventory), "
    "`change_case` (the bank's own case on a regulatory change) and `action` (a piece of work "
    "on a case). A kind outside those four is refused with a 422. A code, not a label: store "
    "and compare it, never show it."
)
_SUBJECT_ID = (
    "The record's identifier, as a uuid. Together with the kind it names exactly one record; "
    "a record this bank does not hold, or one the caller may not read, answers 404 as if it "
    "did not exist."
)
_BODY_IN = (
    "What the person writes, as plain text, at least 1 character long; the deployment sets "
    "the longest accepted (4,000 characters unless configured otherwise), and a longer text or "
    "one of only spaces is refused with a 422. Everyone in the bank who can read the record "
    "can read it, so it is never private. It is the bank's own text: it never leaves the bank, "
    "never reaches a log, a notification, a mail or an audit record, and never reaches a model."
)


class CollabNotification(CamelSchema):
    """One thing one person is told about one record (COL-02): a mention, an assignment, a
    reminder, an escalation. The caller's own and nobody else's, in their own bank."""

    model_config = ConfigDict(json_schema_extra={"examples": [_NOTIFICATION_EXAMPLE]})

    id: uuid.UUID = Field(
        description=(
            "The notification's identifier, as a uuid, which `POST /notifications/{notificationId}/read` "
            "takes. It says nothing about the record it points at."
        ),
        examples=[_NOTIFICATION_EXAMPLE["id"]],
    )
    kind: CollabNotificationKind = Field(
        description=(
            "Why the person is told, a fixed code the screen turns into its own words: "
            "`assigned`, a record was given to them to own or work on; "
            "`mention`, someone named them in a comment; "
            "`signoff_requested`, a case waits for their sign-off; "
            "`approval_requested`, a change waits for their approval; "
            "`due_soon`, something they own falls due within the bank's reminder lead; "
            "`overdue`, something they own is past its due date; "
            "`escalation`, overdue work of their department reached the bank's escalation threshold; "
            "`proposal_waiting`, a proposal waits for review (not produced yet); "
            "`saved_search_hit`, a saved search found something new (not produced yet); "
            "`participant_added`, they were added as a participant on a record; "
            "`involved_item_changed`, a record they are involved in was linked to a change or "
            "given a new version; "
            "`review_due`, a record they are responsible for is due for its periodic review. "
            "New codes may be added, so a screen shows an unknown one generically rather than failing."
        ),
        examples=["mention"],
    )
    subject_type: str = Field(
        max_length=SUBJECT_TYPE_MAX,
        description=(
            "The kind of record the notification points at, as a fixed lowercase code of at most "
            "64 characters, such as `change_case`, `obligation`, `tenant_obligation` or `action`. "
            "A code, not a label: branch on it to build the link, never show it."
        ),
        examples=["change_case"],
    )
    subject_id: uuid.UUID = Field(
        description=(
            "The record the notification points at, as a uuid. The notification stays listed if "
            "the person later loses access to the record; following the link then answers 404."
        ),
        examples=[_NOTIFICATION_EXAMPLE["subjectId"]],
    )
    title: str = Field(
        description=(
            "The record's title as it read when the person was told, for the inbox line. Always a "
            "record's title and never anything a person typed in a comment or a note, so it is "
            "safe to show in a notification list. It is not updated when the record is renamed."
        ),
        examples=[_NOTIFICATION_EXAMPLE["title"]],
    )
    created_at: datetime.datetime = Field(
        description="When the person was told, as an RFC 3339 timestamp in UTC (`2026-09-24T08:15:00Z`). Set by the server.",
        examples=["2026-09-24T08:15:00Z"],
    )
    read_at: datetime.datetime | None = Field(
        description=(
            "When the person marked it read, as an RFC 3339 timestamp in UTC "
            "(`2026-09-24T09:00:00Z`), or null while it is unread. Reading the record itself "
            "does not set it; only the two mark-read calls do."
        ),
        examples=[None],
    )


class CollabNotificationQuery(PageQuery, CamelSchema):
    """The filter and paging of `GET /notifications`: the shared `limit` and `offset`, 20 by
    default and 100 at most, and `unread`. A query parameter the route does not name is
    ignored rather than refused."""

    unread: bool = Field(
        default=False,
        description=(
            "`true` to list only the notifications not yet marked read, for the bell; false by "
            "default, which lists read and unread alike, newest first."
        ),
        examples=[True],
    )


class CollabNotificationPage(CamelSchema):
    """`{items, total}` with `limit` and `offset`, not the designed cursor page (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_NOTIFICATION_EXAMPLE], "total": 1}]})

    items: list[CollabNotification] = Field(
        description=(
            "The caller's own notifications on this page, newest first. Never another person's, "
            "whatever the caller's role. An empty list is a 200 and means there is nothing to "
            "tell them."
        )
    )
    total: int = Field(
        description=(
            "How many notifications match the filter in total, not how many are on this page; "
            "with `unread=true` it is the unread count the bell shows."
        )
    )


class CollabComment(CamelSchema):
    """A comment on one record of one bank (COL-01), shared with everyone in that bank who can
    read the record. There are no private comments (D-22, D-60)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_COMMENT_EXAMPLE]})

    id: uuid.UUID = Field(
        description="The comment's identifier, as a uuid, which the edit and delete calls take.",
        examples=[_COMMENT_EXAMPLE["id"]],
    )
    subject_type: str = Field(max_length=SUBJECT_TYPE_MAX, description=_SUBJECT_TYPE, examples=["change_case"])
    subject_id: uuid.UUID = Field(description=_SUBJECT_ID, examples=[_COMMENT_EXAMPLE["subjectId"]])
    body: str | None = Field(
        description=(
            "What the author wrote, as plain text, or null once the comment was deleted: a "
            "deleted comment keeps its place in the thread so the conversation still reads, but "
            "its text is no longer returned. The bank's own text, visible to everyone in the bank "
            "who can read the record; it never leaves the bank."
        ),
        examples=[_COMMENT_EXAMPLE["body"]],
    )
    mentions: list[PersonRef] = Field(
        description=(
            "The people the author named when writing it, fixed at that moment: an edit does not "
            "change who was mentioned, so an edit can never notify anyone new. Someone mentioned "
            "is not necessarily notified; only those who could read the record were."
        )
    )
    author: PersonRef = Field(description="The person who wrote the comment. Only they may edit or delete it.")
    created_at: datetime.datetime = Field(
        description="When it was written, as an RFC 3339 timestamp in UTC (`2026-09-24T08:15:00Z`). Set by the server.",
        examples=["2026-09-24T08:15:00Z"],
    )
    edited_at: datetime.datetime | None = Field(
        description=(
            "When the author last changed the text, as an RFC 3339 timestamp in UTC, or null if "
            "it was never edited. The text an edit replaced is kept by the bank and returned by "
            "no call."
        ),
        examples=[None],
    )
    deleted_at: datetime.datetime | None = Field(
        description=(
            "When the author deleted it, as an RFC 3339 timestamp in UTC, or null while it stands. "
            "A deleted comment is kept, without its text, rather than removed."
        ),
        examples=[None],
    )
    can_edit: bool = Field(
        description=(
            "Whether the caller may change the text now: true only for the author, only while "
            "the comment stands and only within the deployment's edit window after writing it. "
            "Computed by the server for this caller; a screen shows the edit control from it."
        ),
        examples=[True],
    )
    can_delete: bool = Field(
        description=(
            "Whether the caller may delete it: true only for the author while it stands. No "
            "role grants deleting someone else's comment. Computed by the server for this caller."
        ),
        examples=[True],
    )


class CollabCommentCreated(CollabComment):
    """The comment just written, plus who it mentioned but could not reach (COL-01)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{**_COMMENT_EXAMPLE, "undeliveredMentions": []}]})

    undelivered_mentions: list[PersonRef] = Field(
        description=(
            "The mentioned people who were not notified, so the composer can say by name that the "
            "mention did not reach them: someone who cannot read this record, is no longer an "
            "active member or has switched mentions off. It never says which. The author is never "
            "notified of their own mention and never listed here. Empty when everyone mentioned "
            "was notified."
        )
    )


class CollabCommentQuery(PageQuery, CamelSchema):
    """Which record's comments to read, and the shared `limit` and `offset`: 20 by default and
    100 at most. Kinds and ids ride in the query string; a comment's text never does."""

    subject_type: str = Field(max_length=SUBJECT_TYPE_MAX, description=_SUBJECT_TYPE, examples=["change_case"])
    subject_id: uuid.UUID = Field(description=_SUBJECT_ID, examples=[_COMMENT_EXAMPLE["subjectId"]])


class CollabCommentPage(CamelSchema):
    """`{items, total}` with `limit` and `offset`, not the designed bare array: a busy case
    would otherwise return every comment ever written (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_COMMENT_EXAMPLE], "total": 1}]})

    items: list[CollabComment] = Field(
        description=(
            "The record's comments on this page, oldest first, so the thread reads as it was "
            "written. Deleted comments stay in place without their text. An empty list is a 200: "
            "nobody has commented yet."
        )
    )
    total: int = Field(description="How many comments the record has in total, deleted ones included, not how many are on this page.")


class CollabCommentInput(WriteBody):
    """A new comment on one record. A field the schema does not name answers 422."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "subjectType": "change_case",
                    "subjectId": "11111111-1111-4111-8111-111111111111",
                    "body": "@Erik Holm can you check the custody angle before Friday?",
                    "mentionUserIds": [_ERIK["id"]],
                }
            ]
        },
    )

    subject_type: str = Field(max_length=SUBJECT_TYPE_MAX, description=_SUBJECT_TYPE, examples=["change_case"])
    subject_id: uuid.UUID = Field(description=_SUBJECT_ID, examples=[_COMMENT_EXAMPLE["subjectId"]])
    body: str = Field(min_length=1, description=_BODY_IN, examples=[_COMMENT_EXAMPLE["body"]])
    mention_user_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description=(
            "The people the author names, as the uuids of members of this bank; empty by default. "
            "The screen's picker fills it; the server does not read names out of the text. Each "
            "one who can read the record is notified once; one who cannot is stored on the "
            "comment, notified of nothing and returned in `undeliveredMentions`. A uuid that is "
            "not a member of this bank is refused with a 422."
        ),
        examples=[[_ERIK["id"]]],
    )


class CollabCommentPatch(WriteBody):
    """The new text of one's own comment. A field the schema does not name answers 422."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"body": "@Erik Holm can you check the custody angle before Thursday?"}]})

    body: str = Field(min_length=1, description=_BODY_IN, examples=["@Erik Holm can you check the custody angle before Thursday?"])


class CollabMyComment(CollabComment):
    """One comment on My work's "Comments and mentions" panel: the comment and the title of
    the record it is on, so the row can link there (COL-01, HOM-05)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{**_COMMENT_EXAMPLE, "subjectTitle": _NOTIFICATION_EXAMPLE["title"]}]}
    )

    subject_title: str = Field(
        description=(
            "The title of the record the comment is on, as the caller reads it today, for the row "
            "and its link. A record's title, never text a person typed in a comment."
        ),
        examples=[_NOTIFICATION_EXAMPLE["title"]],
    )


class CollabMyCommentQuery(PageQuery, CamelSchema):
    """Which half of the panel to read, and the shared `limit` and `offset`: 20 by default and
    100 at most."""

    about: CollabMyCommentsAbout = Field(
        description=(
            "Which comments to list: `written`, the comments the caller wrote, on any record; "
            "`mentioned`, other people's comments that name the caller. Any other value is "
            "refused with a 422."
        ),
        examples=["mentioned"],
    )


class CollabMyCommentPage(CamelSchema):
    """`{items, total}` on the shared paging, plus the kinds of record the caller could not
    see, so the panel can say so without naming a record (COL-S12)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [{**_COMMENT_EXAMPLE, "subjectTitle": _NOTIFICATION_EXAMPLE["title"]}],
                    "total": 1,
                    "permissionLimitedKinds": [],
                }
            ]
        }
    )

    items: list[CollabMyComment] = Field(
        description=(
            "The caller's comments or mentions on this page, newest first, only on records the "
            "caller can read today. An empty list is a 200."
        )
    )
    total: int = Field(description="How many comments match in total among the records the caller can read, not how many are on this page.")
    permission_limited_kinds: list[str] = Field(
        description=(
            "The kinds of record, as the same codes `subjectType` carries (`obligation`, "
            "`tenant_obligation`, `change_case`, `action`), that the caller's role cannot read, so "
            "comments on them were left out. It names kinds only, never a record, and it is empty "
            "when nothing was held back."
        ),
        examples=[["change_case"]],
    )


# ---------------------------------------------------------------------------------------
# Participants of a register entry (COL-04, D-18, D-19)
# ---------------------------------------------------------------------------------------
_PARTICIPANT_EXAMPLE: dict[str, JsonValue] = {
    "id": "6d5c4b3a-2e1f-4a09-8b7c-5d4e3f2a1b0c",
    "person": _ERIK,
    "team": None,
    "addedBy": _ANNA,
    "addedAt": "2026-09-24T08:15:00Z",
}
_TEAM_PARTICIPANT_EXAMPLE: dict[str, JsonValue] = {
    "id": "7e6d5c4b-3f2a-4b1c-9d8e-6f5a4b3c2d1e",
    "person": None,
    "team": {"key": "legal", "kind": None, "label": "Legal"},
    "addedBy": _ANNA,
    "addedAt": "2026-09-24T08:16:00Z",
}


class CollabTeamRef(CamelSchema):
    """A team of the bank, as a picker and a list read it: the key to store and send back,
    and a label to show."""

    key: str = Field(
        description=(
            "The team's key, a lowercase code of at most 80 characters such as `legal`, and the only "
            "part to store, compare or send back. Teams are rows of the bank's own `team` vocabulary, "
            "which its administrators extend, rename and retire (`GET /vocab/team` for the live set); the "
            "`compliance` team is there from day one. A key never changes once issued."
        ),
        examples=["legal"],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "The fixed kind of the value, as on every vocabulary reference; always null here, "
            "because the team list has no kinds: every team is simply a team of the bank."
        ),
        examples=[None],
    )
    label: str = Field(
        description=(
            "The team's name in the reader's language: the caller's own language first, then the "
            "bank's default language, then English, then any label the team has, and the key itself "
            "when it has none. For display only: an administrator may rename it at any time, so "
            "nothing may match on it."
        ),
        examples=["Legal"],
    )


class CollabParticipant(CamelSchema):
    """One person or one team taking part in a register entry (COL-04). Taking part puts the
    record on their My work and in their notifications and grants them nothing: what they
    may read or do is still their role's alone."""

    model_config = ConfigDict(json_schema_extra={"examples": [_PARTICIPANT_EXAMPLE]})

    id: uuid.UUID = Field(
        description=(
            "The participation's identifier, as a uuid, which "
            "`DELETE /obligations/{obligationId}/participants/{participantId}` takes. It names this "
            "participation, never the person or the team."
        ),
        examples=[_PARTICIPANT_EXAMPLE["id"]],
    )
    person: PersonRef | None = Field(
        description=(
            "The person taking part, by id and name, or null when a team takes part. Exactly one of "
            "`person` and `team` is set."
        ),
        examples=[_ERIK],
    )
    team: CollabTeamRef | None = Field(
        description=(
            "The team taking part, or null when a person takes part: a row of the bank's own `team` "
            "vocabulary, which its administrators extend (`GET /vocab/team` for the live set). A "
            "team has no kinds. A team reaches its active "
            "members, each of whom still sees only what their own role can read. Exactly one of "
            "`person` and `team` is set."
        ),
        examples=[None],
    )
    added_by: PersonRef = Field(
        description="Who added the participant, by id and name: a member of the bank holding `register.edit` when they did.",
        examples=[_ANNA],
    )
    added_at: datetime.datetime = Field(
        description="When the participant was added, as an RFC 3339 timestamp in UTC (`2026-09-24T08:15:00Z`). Set by the server.",
        examples=["2026-09-24T08:15:00Z"],
    )


class CollabParticipantPage(CamelSchema):
    """`{items, total}` of a register entry's participants, with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": [_PARTICIPANT_EXAMPLE, _TEAM_PARTICIPANT_EXAMPLE], "total": 2}]}
    )

    items: list[CollabParticipant] = Field(
        description=(
            "The people and teams taking part now, in the order they were added. One who left or "
            "was removed is not listed; the record's history keeps that they took part. An empty "
            "list is a 200: nobody takes part, or the bank has not worked on the obligation yet."
        )
    )
    total: int = Field(description="How many take part now in total, not how many are on this page.")


class CollabParticipantInput(WriteBody):
    """Who to add: exactly one of a person and a team. A field the schema does not name
    answers 422."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"userId": _ERIK["id"]}, {"teamKey": "legal"}]},
    )

    user_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The person to add, as the uuid of an active member of this bank, from the people "
            "picker; null by default. Someone who is not an active member of this bank, whether "
            "from another bank, deactivated or unknown, is refused with the one 422 "
            "`unknown_member`; a member whose roles cannot read the register with 422 "
            "`participant_cannot_read`. Set this or `teamKey`, never both."
        ),
        examples=[_ERIK["id"]],
    )
    team_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description=(
            "The team to add, as the key of an active row of the bank's `team` list (`GET "
            "/vocab/team`), at most 80 characters; null by default. A key the bank has no active "
            "team for is refused with 422 `unknown_key`. Set this or `userId`, never both."
        ),
        examples=["legal"],
    )

    @model_validator(mode="after")
    def exactly_one(self) -> CollabParticipantInput:
        if (self.user_id is None) == (self.team_key is None):
            raise ValueError("Name a person or a team, not both and not neither.")
        return self

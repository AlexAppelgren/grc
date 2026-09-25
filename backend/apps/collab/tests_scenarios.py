"""Scenario stubs for the collab app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: COL.
"""

import contextlib
import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from unittest import skip

from django.test import TestCase

from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.collab.logic import notify
from apps.collab import comments
from apps.collab.models import Comment, CommentMention, CommentRevision, EmailMessage, Notification, NotificationKind
from apps.identity.models import User
from apps.shared import factories, sentry_scrub, tenancy
from apps.shared import tests_compliance_lint as lint
from apps.shared.logging import JsonFormatter
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import AuditAssertingClient, sign_in
from apps.watch import testing as watch_build


@contextlib.contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """Every line the application logs meanwhile, at every level, as production writes it."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    loggers = [logging.getLogger(name) for name in ("", "apps", "django", "config")]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    lines: list[str] = []
    try:
        yield lines
    finally:
        for logger, level in zip(loggers, levels, strict=True):
            logger.removeHandler(handler)
            logger.setLevel(level)
        lines.extend(line for line in stream.getvalue().splitlines() if line.strip())


class CollabScenarioTests(TestCase):
    """Scenario tests for apps.collab, one method per @integration scenario."""

    # COL-S1 (c10-comments-mentions)
    def test_col_s1(self) -> None:
        """COL-S1

        A comment with a mention notifies the mentioned person (COL-01).
        Operations: `addComment`, `markNotificationRead`, `markAllNotificationsRead`.
        """
        # Given a case and a contributor with comments.write
        watch_build.seed_watch_reference()
        tenant = factories.tenant(slug="col-s1")
        other = factories.tenant(slug="col-s1-other")
        anna = factories.member_user(tenant, roles=("contributor",))
        erik = factories.member_user(tenant, roles=("reader",))
        case = cases_build.case(tenant, watch_build.change(title="FI amends the custody rules for client assets"))

        # When they comment "@Erik can you check the custody angle?"
        response = self.client.post(
            "/api/v1/comments",
            data={
                "subjectType": "change_case",
                "subjectId": str(case.id),
                "body": "@Erik can you check the custody angle?",
                "mentionUserIds": [str(erik.id)],
            },
            content_type="application/json",
            **sign_in(anna, tenant=tenant),
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["undeliveredMentions"], [])

        # Then the comment is stored against the case with the subject kind and id
        tenancy.activate(tenant.id)
        comment = Comment.objects.get(pk=response.json()["id"])
        self.assertEqual((comment.subject_type, comment.subject_id, comment.author_id), ("change_case", case.id, anna.id))
        self.assertEqual(list(CommentMention.objects.filter(comment=comment).values_list("user_id", flat=True)), [erik.id])

        # And Erik receives a notification linking to the case
        (told,) = Notification.objects.filter(user=erik)
        self.assertEqual((told.kind, told.subject_type, told.subject_id), ("mention", "change_case", case.id))
        self.assertEqual(told.title, "FI amends the custody rules for client assets")
        self.assertFalse(Notification.objects.filter(user=anna).exists())

        # And the comment is visible only inside the tenant
        erik_reads = self.client.get(
            f"/api/v1/comments?subjectType=change_case&subjectId={case.id}", **sign_in(erik, tenant=tenant)
        )
        self.assertEqual([item["id"] for item in erik_reads.json()["items"]], [str(comment.id)])
        stranger = factories.member_user(other, roles=("compliance_officer",))
        foreign_read = self.client.get(
            f"/api/v1/comments?subjectType=change_case&subjectId={case.id}", **sign_in(stranger, tenant=other)
        )
        self.assertEqual(foreign_read.status_code, 404)
        tenancy.activate(other.id)
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())

    @skip("pending: COL-S2")
    def test_col_s2(self) -> None:
        """COL-S2

        Reminders, escalation and the digest reach people in their language (COL-02).
        """

    @skip("pending: COL-S3")
    def test_col_s3(self) -> None:
        """COL-S3

        Schedules run in the tenant's timezone (COL-02).
        """

    @skip("pending: COL-S4")
    def test_col_s4(self) -> None:
        """COL-S4

        A user follows a record and hears about changes (COL-03).
        """

    # COL-S5 (c10-comments-mentions)
    def test_col_s5(self) -> None:
        """COL-S5

        Comment text never reaches a log (COL-01).
        Operations: `addComment`, `editComment`, `deleteComment`.

        The sweep reads every line the application logs while the comment is created,
        edited and deleted, written by the JSON formatter production uses, and also the
        audit rows, their outbox payloads, the notifications and what Sentry's `before_send`
        would send for each request and log line. The kept revision is covered with it.
        """
        watch_build.seed_watch_reference()
        tenant = factories.tenant(slug="col-s5")
        anna = factories.member_user(tenant, roles=("contributor",))
        erik = factories.member_user(tenant, roles=("reader",))
        case = cases_build.case(tenant, watch_build.change(title="FI amends the custody rules for client assets"))
        client = AuditAssertingClient()
        headers = sign_in(anna, tenant=tenant)
        first, second = "col-s5-first-4b1d custody", "col-s5-second-9e2a custody"
        requests: list[tuple[str, dict[str, Any]]] = []

        # Given a comment is created, edited and deleted
        with _captured_logs() as lines:
            payload = {"subjectType": "change_case", "subjectId": str(case.id), "body": first, "mentionUserIds": [str(erik.id)]}
            created = client.post("/api/v1/comments", data=payload, content_type="application/json", **headers)
            self.assertEqual(created.status_code, 201, created.content)
            comment_id = created.json()["id"]
            requests.append(("/api/v1/comments", payload))
            edited = client.patch(f"/api/v1/comments/{comment_id}", data={"body": second}, content_type="application/json", **headers)
            self.assertEqual(edited.status_code, 200, edited.content)
            requests.append((f"/api/v1/comments/{comment_id}", {"body": second}))
            deleted = client.delete(f"/api/v1/comments/{comment_id}", **headers)
            self.assertEqual(deleted.status_code, 204)
            requests.append((f"/api/v1/comments/{comment_id}", {}))

        # When the application log for those requests is read
        written = [json.loads(line) for line in lines]
        ours = [line for line in written if line["logger"] == "apps.collab.comments"]

        # Then it holds the comment id and the actor id and never the text
        self.assertEqual([line["message"] for line in ours], ["comment added", "comment edited", "comment deleted"])
        for line in ours:
            self.assertEqual((line["comment_id"], line["actor_id"]), (comment_id, str(anna.id)))
        tenancy.activate(tenant.id)
        stored = [
            " ".join(lines),
            " ".join(f"{e.summary} {e.subject_title} {e.before} {e.after}" for e in AuditEvent.objects.all()),
            " ".join(str(p) for p in OutboxEvent.objects.values_list("payload", flat=True)),
            " ".join(Notification.objects.values_list("title", flat=True)),
        ]
        events = [
            {"request": {"url": f"http://testserver{path}", "data": body, "query_string": ""}, "extra": {"body": body.get("body")}}
            for path, body in requests
        ] + [{"message": line["message"], "extra": line, "breadcrumbs": {"values": [{"message": line["message"], "data": line}]}} for line in written]
        scrubbed = json.dumps([sentry_scrub.before_send(cast(Any, event), {}) for event in events])
        for fragment in ("col-s5-first-4b1d", "col-s5-second-9e2a"):
            for place, text in zip(("log", "audit", "outbox", "notification"), stored, strict=True):
                self.assertNotIn(fragment, text, place)
            self.assertNotIn(fragment, scrubbed, "sentry")
        # The replaced text is kept by the bank, which is what the sweep had to cover.
        self.assertEqual(list(CommentRevision.objects.filter(comment_id=comment_id).values_list("body", flat=True)), [first])

        # And the compliance lint fails on a log call that passes a comment body
        planted = {"apps/collab/comments.py": 'logger.info("comment added", extra={"body": comment.body})\n'}
        self.assertEqual(lint.flagged(planted), [("apps/collab/comments.py", "log-content")])
        real = {"apps/collab/comments.py": Path(comments.__file__).read_text(encoding="utf-8")}
        self.assertEqual(lint.flagged(real), [])

    @skip("pending: COL-S6 (COL-04, chunk 8)")
    def test_col_s6(self) -> None:
        """COL-S6

        A person or a team is added to a register entry, audited, and gains no access (COL-04, AC-COL1).
        """

    @skip("pending: COL-S7 (COL-04, chunk 8)")
    def test_col_s7(self) -> None:
        """COL-S7

        A participant leaves a register entry on their own (COL-04).
        """

    @skip("pending: COL-S8 (COL-04, chunk 8)")
    def test_col_s8(self) -> None:
        """COL-S8

        Register-entry participant routes refuse other tenants, strangers and people who cannot read (COL-04, NFR-01).
        """

    @skip("pending: COL-S9 (COL-04, chunk 9)")
    def test_col_s9(self) -> None:
        """COL-S9

        Case participants are managed by those who contribute, and refused across tenants (COL-04, NFR-01).
        """

    @skip("pending: COL-S10 (COL-02, COL-04, chunk 10)")
    def test_col_s10(self) -> None:
        """COL-S10

        Participation, confirmed links and new versions notify the people involved, once, if they can read (COL-02, COL-04).
        """

    @skip("pending: COL-S11 (COL-02, chunk 10)")
    def test_col_s11(self) -> None:
        """COL-S11

        Review reminders reach the people responsible, once (COL-02).
        """

    @skip("pending: COL-S12 (COL-01, HOM-05, chunk 10)")
    def test_col_s12(self) -> None:
        """COL-S12

        My comments and mentions are found on My work, limited to what I can read, and never logged (COL-01, HOM-05).
        """

    # COL-S13 (c10-notify-and-prefs)
    def test_col_s13(self) -> None:
        """COL-S13

        Notification preferences mute a kind for one person, never an escalation (COL-02).

        The comment is written as the comments producer will write it (the rows, then
        notify() in the same transaction); the escalation goes through notify(kind=escalation)
        on the case Anna owns, the subject an escalation names until chunk 9 registers the
        action.
        """
        watch_build.seed_watch_reference()
        tenant = factories.tenant(slug="col-s13")
        anna = factories.member_user(tenant, roles=("contributor",))
        erik = factories.member_user(tenant, roles=("contributor",))
        case = cases_build.case(tenant, watch_build.change(title="FI amends the research payment rules"), owner=anna)
        anna_headers = sign_in(anna, tenant=tenant)

        def switch(prefs: dict[str, bool]) -> None:
            response = self.client.patch(
                "/api/v1/me", data={"notificationPrefs": prefs}, content_type="application/json", **anna_headers
            )
            self.assertEqual(response.status_code, 200, response.content)

        def mention(*people: User) -> Comment:
            tenancy.activate(tenant.id)
            comment = Comment.objects.create(tenant=tenant, subject_type="change_case", subject_id=case.id, author=erik, body="Please look.")
            for person in people:
                CommentMention.objects.create(tenant=tenant, comment=comment, user=person)
            notify(
                tenant_id=tenant.id,
                kind=NotificationKind.MENTION,
                subject_type="change_case",
                subject_id=case.id,
                candidates=[(person.id, "mention") for person in people],
            )
            return comment

        def told(person: User, kind: NotificationKind) -> int:
            tenancy.activate(tenant.id)
            return Notification.objects.filter(user=person, kind=kind.value, subject_id=case.id).count()

        # Given Anna has turned mentions off (and reminders) and Erik has not
        switch({"mentions": False, "reminders": False})

        # When Erik mentions them both on a case
        comment = mention(anna, erik)

        # Then Anna receives no notification and no mail, and Erik's own row is written
        self.assertEqual(told(anna, NotificationKind.MENTION), 0)
        self.assertFalse(EmailMessage.objects.filter(user=anna).exists())
        self.assertEqual(told(erik, NotificationKind.MENTION), 1)
        # And the comment still lists both mentions, and the case is unchanged for Anna
        self.assertEqual(
            set(CommentMention.objects.filter(comment=comment).values_list("user_id", flat=True)), {anna.id, erik.id}
        )
        self.assertEqual(ChangeCase.objects.get(pk=case.pk).owner_id, anna.id)

        # When an action Anna owns passes the escalation threshold
        tenancy.activate(tenant.id)
        notify(
            tenant_id=tenant.id,
            kind=NotificationKind.ESCALATION,
            subject_type="change_case",
            subject_id=case.id,
            candidates=[(anna.id, "owner")],
        )
        # Then Anna is notified although reminders are off
        self.assertEqual(told(anna, NotificationKind.ESCALATION), 1)

        # When Anna turns mentions back on
        switch({"mentions": True})
        mention(anna)
        # Then the next mention reaches her, and the muted one is not replayed
        self.assertEqual(told(anna, NotificationKind.MENTION), 1)

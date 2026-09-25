"""Scenario stubs for the collab app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: COL.
"""

from unittest import skip

from apps.collab.tests_case_participants import run_col_s9
from apps.collab.tests_participants import run_col_s6, run_col_s7, run_col_s8
from apps.shared.testing import ScenarioTestCase

from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.collab.logic import notify
from apps.collab.models import Comment, CommentMention, EmailMessage, Notification, NotificationKind
from apps.identity.models import User
from apps.shared import factories, tenancy
from apps.shared.testing import sign_in
from apps.watch import testing as watch_build


class CollabScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.collab, one method per @integration scenario."""

    @skip("pending: COL-S1")
    def test_col_s1(self) -> None:
        """COL-S1

        A comment with a mention notifies the mentioned person (COL-01).
        Operations: `addComment`, `markNotificationRead`, `markAllNotificationsRead`.
        """

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

    @skip("pending: COL-S5")
    def test_col_s5(self) -> None:
        """COL-S5

        Comment text never reaches a log (COL-01).
        Operations: `addComment`, `editComment`, `deleteComment`.
        """

    def test_col_s6(self) -> None:
        """COL-S6

        A person or a team is added to a register entry, audited, and gains no access (COL-04, AC-COL1).
        Operations: `addObligationParticipant`, `listObligationParticipants`.
        """
        run_col_s6(self)

    def test_col_s7(self) -> None:
        """COL-S7

        A participant leaves a register entry on their own (COL-04).
        Operations: `removeObligationParticipant`.
        """
        run_col_s7(self)

    def test_col_s8(self) -> None:
        """COL-S8

        Register-entry participant routes refuse other tenants, strangers and people who cannot read (COL-04, NFR-01).
        Operations: `addObligationParticipant`, `listObligationParticipants`, `removeObligationParticipant`.
        """
        run_col_s8(self)

    def test_col_s9(self) -> None:
        """COL-S9

        Case participants are managed by those who contribute, and refused across tenants (COL-04, NFR-01).
        Operations: `addCaseParticipant`, `listCaseParticipants`, `removeCaseParticipant`.
        """
        run_col_s9(self)

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

"""Scenario stubs for the collab app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: COL.
"""

import datetime
from unittest import mock, skip
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import TestCase

from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.collab import tasks
from apps.collab.logic import notify
from apps.collab.models import Comment, CommentMention, EmailMessage, Notification, NotificationKind
from apps.identity.models import User
from apps.library.reading import today_for
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import Tenant
from apps.shared import factories, tenancy
from apps.shared.testing import sign_in
from apps.watch import testing as watch_build


class CollabScenarioTests(TestCase):
    """Scenario tests for apps.collab, one method per @integration scenario."""

    @skip("pending: COL-S1")
    def test_col_s1(self) -> None:
        """COL-S1

        A comment with a mention notifies the mentioned person (COL-01).
        """

    @skip("pending: COL-S2")
    def test_col_s2(self) -> None:
        """COL-S2

        Reminders, escalation and the digest reach people in their language (COL-02).
        """

    # COL-S3 (c10-reminders-core)
    def test_col_s3(self) -> None:
        """COL-S3

        Schedules run in the tenant's timezone (COL-02).

        Reworded from the digest to the triage reminder, the first schedule built on the
        hourly beat (CHUNK10_TASKS `c10-reminders-escalation-a`). The daylight saving days
        are found by walking forward from the tenant-local date, never written as literals.
        """
        watch_build.seed_watch_reference()
        zone = ZoneInfo("Europe/Helsinki")
        # Given a tenant in Europe/Helsinki, reminders sent at 07:00 and a lead of three days
        tenant = factories.tenant(slug="col-s3", timezone="Europe/Helsinki")
        Tenant.objects.filter(pk=tenant.pk).update(reminder_days_before=[3])
        officer = factories.member_user(tenant, roles=("compliance_officer",))
        anchor = today_for(tenant)

        def offset(day: datetime.date) -> datetime.timedelta | None:
            return datetime.datetime.combine(day, datetime.time(12), tzinfo=zone).utcoffset()

        days = [anchor + datetime.timedelta(days=n) for n in range(1, 400)]
        spring = next(day for day in days if offset(day) > offset(day - datetime.timedelta(days=1)))  # type: ignore[operator]
        autumn = next(day for day in days if offset(day) < offset(day - datetime.timedelta(days=1)))  # type: ignore[operator]

        def served_at(day: datetime.date) -> list[datetime.datetime]:
            """Fire the beat at every UTC hour of `day` in Helsinki; return when it reminded."""
            # And a case awaiting triage, due three days after the tenant-local date
            case = cases_build.case(tenant, watch_build.change(title=f"FI amends the rules of {day.isoformat()}"))
            tenancy.activate(tenant.id)
            due = datetime.datetime.combine(day + datetime.timedelta(days=3), datetime.time(12), tzinfo=zone)
            ChangeCase.objects.filter(pk=case.pk).update(triage_due_at=due)
            start = datetime.datetime.combine(day, datetime.time(0), tzinfo=zone).astimezone(datetime.UTC)
            end = datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time(0), tzinfo=zone).astimezone(datetime.UTC)
            hits: list[datetime.datetime] = []
            moment = start
            while moment < end:
                # When the worker's beat fires every hour of that local day in UTC
                with mock.patch("django.utils.timezone.now", return_value=moment):
                    tasks.send_reminders()
                tenancy.activate(tenant.id)
                if Notification.objects.filter(subject_id=case.id).count() > len(hits):
                    hits.append(moment)
                moment += datetime.timedelta(hours=1)
            # Then the triage reminder is sent once, and its mail once
            tenancy.activate(tenant.id)
            self.assertEqual(Notification.objects.filter(subject_id=case.id, user=officer, kind="due_soon").count(), 1)
            self.assertEqual(EmailMessage.objects.filter(subject_id=case.id, sent_on=day).count(), 1)
            return hits

        MockMailer.reset()
        self.addCleanup(MockMailer.reset)
        for change in (spring, autumn):
            before = served_at(change - datetime.timedelta(days=1))
            on = served_at(change)
            # at 07:00 Helsinki time, and at no other hour
            self.assertEqual([hit.astimezone(zone).hour for hit in before + on], [settings.REMINDER_SEND_HOUR] * 2)
            # And across the change it still arrives at 07:00 local, one UTC hour apart
            shift = datetime.timedelta(hours=-1 if change == spring else 1)
            self.assertEqual(on[0] - before[0], datetime.timedelta(days=1) + shift)

    @skip("pending: COL-S4")
    def test_col_s4(self) -> None:
        """COL-S4

        A user follows a record and hears about changes (COL-03).
        """

    @skip("pending: COL-S5")
    def test_col_s5(self) -> None:
        """COL-S5

        Comment text never reaches a log (COL-01).
        """

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

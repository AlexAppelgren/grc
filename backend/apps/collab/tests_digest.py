"""The weekly digest's content and its mail (COL-02, HOM-05; CHUNK10_TASKS `f03-T81` and
`c10-digest-a`), proved on Postgres under row-level security with the mock mailer.

What these pin:

- **One definition of open items.** The digest is My work's own answer for the reader,
  bucket by bucket, ids and counts alike, and `digest.py` imports no model beyond the
  membership it composes for (D-23).
- **The reader's permissions.** A member without `cases.read` gets neither the case rows
  nor their count, HOM-S10's rule applied to the mail.
- **The cap.** At most `DIGEST_MAX_ITEMS` rows, the most urgent ones, and "and N more".
- **The reader's mail.** In the reader's language, with absolute links built from
  `APP_BASE_URL` that carry no token; one per person per week, proved by the
  `email_message` row keyed to the week's first day.
- **Nobody else's.** No open items, the digest switched off or a deactivated membership
  means no mail and no row; a delegate never receives the absent person's digest.
- **No tenant text.** A string planted in every comment, note, gap and case text reaches no
  mail.

Every date is the bank's own today plus an offset, never a literal (playbook 8.3).
"""

from __future__ import annotations

import ast
import datetime
import inspect
import re
import uuid
from collections import defaultdict
from unittest import mock

from django.conf import settings
from django.db import models
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.collab import digest
from apps.collab.models import Comment, EmailMessage
from apps.home import my_work
from apps.home.schemas import HomeWorkPage
from apps.home.tests_my_work import Bank, obligation
from apps.identity import roles_logic
from apps.identity.models import Membership, MembershipRole, User
from apps.library.models import Obligation
from apps.library.reading import today_for
from apps.register.models import Gap, TenantObligation
from apps.shared import factories
from apps.shared.adapters.mailer import MockMailer
from apps.shared.permissions import REGISTER_READ
from apps.tenants.models import InternalItem
from apps.watch import testing as watch_build
from apps.watch.models import ChangeObligation
from apps.watch.write import watch_write

DAY = datetime.timedelta(days=1)
# Tenant text that must never leave in a mail, planted in every place a bank types text.
PLANTED = "PLANTED-7f3c tenant text that must stay in the bank"


def base() -> str:
    return settings.APP_BASE_URL.rstrip("/")


def item_ids(page: HomeWorkPage) -> dict[str, list[uuid.UUID]]:
    """The page's row ids per bucket, in the service's order."""
    by: dict[str, list[uuid.UUID]] = defaultdict(list)
    for item in page.items:
        subject = item.subject
        by[item.bucket].append(
            next(
                value
                for value in (subject.obligation_id, subject.change_id, subject.internal_item_id)
                if value
            )
        )
    return dict(by)


def membership(user: User) -> Membership:
    return Membership.objects.select_related("user__locale", "tenant__default_language").get(
        user=user
    )


def mails_to(user: User) -> list[tuple[str, str]]:
    return [
        (subject, body)
        for to, subject, body in ((m.to, m.subject, m.body) for m in MockMailer.sent)
        if to == user.email
    ]


class DigestCase(TestCase):
    """Anna, who reads Swedish, has a row in every bucket: an overdue review, a due-soon
    review, an internal item due soon, an undated duty, a gap on Karin's duty and a case on
    a change linked to one of her duties, which the officer confirmed. Johan, who reads
    English, shares the team's duty. Erik reads the register but no case. Every record
    carries a comment, a note or a text with the planted string."""

    bank: Bank
    overdue: Obligation
    due_soon: Obligation
    undated: Obligation
    team_duty: Obligation
    karins: Obligation
    policy: InternalItem
    case: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("digest")
        today = bank.today()
        for person, language in ((bank.anna, "sv"), (bank.johan, "en"), (bank.erik, "en")):
            person.locale = factories.language(language)
            person.save(update_fields=["locale"])

        cls.overdue = obligation("Reconcile client money")
        cls.due_soon = obligation("Report large exposures")
        cls.undated = obligation("Keep a complaints register")
        cls.team_duty = obligation("Assess suitability")
        cls.karins = obligation("Review outsourcing")
        entries = [
            bank.entry(cls.overdue, first_line_owner=bank.anna, next_review_date=today - 2 * DAY),
            bank.entry(cls.due_soon, first_line_owner=bank.anna, next_review_date=today + 3 * DAY),
            bank.entry(cls.undated, first_line_owner=bank.anna),
            bank.entry(cls.team_duty, owner_team=bank.retail_team),
            bank.entry(cls.karins, first_line_owner=bank.karin),
        ]
        TenantObligation.objects.filter(pk__in=[e.pk for e in entries]).update(
            status_note=PLANTED, applicability_reason=PLANTED
        )
        bank.gap(entries[4], owner=bank.anna, target_date=today + 40 * DAY, description=PLANTED)
        bank.gap(entries[0], owner=bank.anna, remediation=PLANTED)
        Gap.objects.filter(tenant_obligation__in=entries).update(title=PLANTED)
        cls.policy = bank.internal_item(
            "Custody policy", owner_user=bank.anna, next_review_on=today + 5 * DAY
        )

        change = watch_build.change(title="Amended rules on client money", key_date=None)
        watch_build.obligation_link(change, cls.undated)
        with watch_write("test fixture"):
            ChangeObligation.objects.filter(change=change).update(
                confirmed_by=bank.officer, confirmed_at=timezone.now()
            )
        cls.case = cases_build.case(bank.tenant, change, so_what_text=PLANTED)

        # Erik reads the register and nothing about cases; the duty is his too.
        bank.activate()
        role = roles_logic.create_role(
            tenant=bank.tenant,
            actor=factories.user_actor(),
            key="register_reader",
            labels={"en": "Register reader"},
            usage_note="",
            permissions=[REGISTER_READ],
            step_up_assertion_id=None,
        )
        erik = Membership.objects.get(user=bank.erik)
        MembershipRole.objects.filter(membership=erik).delete()
        MembershipRole.objects.create(tenant=bank.tenant, membership=erik, role=role)
        TenantObligation.objects.filter(obligation=cls.undated).update(compliance_contact=bank.erik)

        for subject_type, subject_id in (
            ("tenant_obligation", entries[0].id),
            ("tenant_obligation", entries[2].id),
            ("change_case", cls.case.id),
            ("obligation", cls.overdue.id),
        ):
            Comment.objects.create(
                tenant=bank.tenant,
                subject_type=subject_type,
                subject_id=subject_id,
                author=bank.officer,
                body=PLANTED,
            )

    def setUp(self) -> None:
        self.bank.activate()
        MockMailer.reset()
        self.addCleanup(MockMailer.reset)

    def send_all(self) -> None:
        self.bank.activate()
        digest.send_all()


class Content(DigestCase):
    def test_the_content_is_my_work_answer_bucket_by_bucket(self) -> None:
        mine = digest.content(membership(self.bank.anna))
        assert mine is not None
        service = self.bank.read(self.bank.anna, limit=100)
        self.assertEqual(mine.counts, service.counts)
        self.assertEqual(item_ids(mine), item_ids(service))
        for bucket in my_work.BUCKETS:
            with self.subTest(bucket=bucket):
                self.assertTrue(item_ids(mine)[bucket], "every bucket has a row")
                self.assertEqual(
                    item_ids(mine)[bucket],
                    [
                        value
                        for values in item_ids(
                            self.bank.read(self.bank.anna, bucket=bucket)
                        ).values()
                        for value in values
                    ],
                )

    def test_without_cases_read_neither_the_case_rows_nor_their_count(self) -> None:
        eriks = digest.content(membership(self.bank.erik))
        assert eriks is not None
        service = self.bank.read(self.bank.erik, permissions=frozenset({REGISTER_READ}))
        self.assertEqual((item_ids(eriks), eriks.counts), (item_ids(service), service.counts))
        self.assertNotIn(self.case.change_id, sum(item_ids(eriks).values(), []))
        self.assertEqual(eriks.counts.aware, 0)
        self.assertEqual(eriks.permission_limited, ["change_case"])

    def test_digest_imports_no_model_beyond_the_membership(self) -> None:
        """The content comes from the service: no case, action or register entry is read
        here, so "open items" keeps one definition (D-23)."""
        tree = ast.parse(inspect.getsource(digest))
        imported = {
            alias.name: node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        }
        found = set()
        for name, module in imported.items():
            value = getattr(__import__(module, fromlist=[name]), name, None)
            if inspect.isclass(value) and issubclass(value, models.Model):
                found.add(name)
        self.assertEqual(found, {"Membership"})
        bare = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        self.assertFalse([name for name in bare if name.startswith("apps.")], bare)


class Mail(DigestCase):
    def test_each_reader_gets_one_digest_in_their_own_language(self) -> None:
        self.send_all()
        [(anna_subject, anna_body)] = mails_to(self.bank.anna)
        [(johan_subject, johan_body)] = mails_to(self.bank.johan)
        today = today_for(self.bank.tenant)
        anna_total = self.bank.read(self.bank.anna).total
        self.assertEqual(anna_subject, f"Dina öppna uppgifter, veckan från {today}: {anna_total}")
        self.assertIn("Försenade: 1", anna_body)
        self.assertIn(f"Hej {self.bank.anna.name},", anna_body)
        self.assertEqual(johan_subject, f"Your open items, week of {today}: 1")
        self.assertIn(f"Hello {self.bank.johan.name},", johan_body)
        self.assertIn("Assess suitability", johan_body)

    def test_the_body_lists_each_bucket_count_and_every_row_title_with_its_link(self) -> None:
        self.send_all()
        [(_subject, body)] = mails_to(self.bank.anna)
        service = self.bank.read(self.bank.anna)
        for bucket, heading in (
            ("overdue", "Försenade"),
            ("due_soon", "Snart dags"),
            ("aware", "Ändringar på dina uppgifter"),
            ("open", "Allt du ansvarar för"),
        ):
            self.assertIn(f"{heading}: {getattr(service.counts, bucket)}", body)
        for item in service.items:
            self.assertIn(item.subject.title, body)
        self.assertIn(f"{base()}/inventory/obligations/{self.overdue.id}", body)
        self.assertIn(f"{base()}/watch/{self.case.change_id}", body)
        self.assertIn(f"{base()}/work", body)
        # The service's order: the overdue row comes before the due-soon one.
        self.assertLess(body.index("Reconcile client money"), body.index("Report large exposures"))

    def test_every_link_is_absolute_from_the_base_url_and_carries_no_token(self) -> None:
        self.send_all()
        self.assertTrue(MockMailer.sent)
        for body in (m.body for m in MockMailer.sent):
            links = re.findall(r"https?://\S+", body)
            self.assertTrue(links)
            for link in links:
                with self.subTest(link=link):
                    self.assertTrue(link.startswith(base() + "/"))
                    self.assertNotIn("?", link)
                    self.assertNotIn("#", link)
                    self.assertNotRegex(link.lower(), "token|key=|code=")

    @override_settings(DIGEST_MAX_ITEMS=2)
    def test_the_cap_keeps_the_most_urgent_rows_and_counts_the_rest(self) -> None:
        self.send_all()
        [(_subject, body)] = mails_to(self.bank.anna)
        service = self.bank.read(self.bank.anna)
        kept, dropped = service.items[:2], service.items[2:]
        self.assertEqual([item.bucket for item in kept], ["overdue", "due_soon"])
        for item in kept:
            self.assertIn(item.subject.title, body)
        for item in dropped:
            self.assertNotIn(item.subject.title, body)
        self.assertIn(f"och {service.total - 2} till", body)
        # The counts still cover every row.
        self.assertIn(f"Allt du ansvarar för: {service.counts.open}", body)

    def test_one_digest_per_person_per_week_proved_by_the_row(self) -> None:
        today = today_for(self.bank.tenant)
        monday = today - today.weekday() * DAY
        for day in (monday, monday + 6 * DAY, monday + 7 * DAY):
            with mock.patch("apps.collab.tasks.today_for", return_value=day):
                self.send_all()
        self.assertEqual(len(mails_to(self.bank.anna)), 2)
        rows = EmailMessage.objects.filter(user=self.bank.anna, template="weekly_digest")
        self.assertEqual(sorted(row.sent_on for row in rows), [monday, monday + 7 * DAY])
        self.assertEqual({(row.subject_type, row.subject_id) for row in rows}, {(None, None)})

    def test_a_digest_switched_off_a_deactivated_member_and_nothing_open_send_nothing(
        self,
    ) -> None:
        idle = factories.member(self.bank.tenant).user
        Membership.objects.filter(user=self.bank.johan).update(
            notification_prefs={"weeklyDigest": False}
        )
        Membership.objects.filter(user=self.bank.erik).update(deactivated_at=timezone.now())
        self.send_all()
        for person in (idle, self.bank.johan, self.bank.erik):
            with self.subTest(person=person.name):
                self.assertEqual(mails_to(person), [])
                self.assertFalse(EmailMessage.objects.filter(user=person).exists())
        self.assertIsNone(digest.content(membership(idle)))
        self.assertEqual(len(mails_to(self.bank.anna)), 1)

    def test_a_delegate_never_receives_the_absent_person_digest(self) -> None:
        Membership.objects.filter(user=self.bank.anna).update(
            delegate=self.bank.johan,
            out_of_office_until=today_for(self.bank.tenant) + 7 * DAY,
        )
        self.send_all()
        self.assertEqual(len(mails_to(self.bank.anna)), 1)
        [(_subject, johan_body)] = mails_to(self.bank.johan)
        for title in ("Reconcile client money", "Report large exposures", "Custody policy"):
            self.assertNotIn(title, johan_body)

    def test_no_planted_tenant_text_reaches_any_mail(self) -> None:
        self.send_all()
        self.assertGreaterEqual(len(MockMailer.sent), 3)
        for subject, body in ((m.subject, m.body) for m in MockMailer.sent):
            self.assertNotIn(PLANTED, subject)
            self.assertNotIn(PLANTED, body)

"""The collab mail catalog, its composer and its delivery task (COL-02, I18N-01;
CHUNK10_TASKS `c10-mail-catalog-a` and `-b`).

What these pin:

- **One key set.** en and sv hold exactly the same keys, and every placeholder any string
  interpolates is a `MailContext` field or one the composer fills itself, so no template can
  ask for a comment, a note, an assessment or a summary.
- **Typed context.** `MailContext` takes a record title, a date, a count, a person's name and
  a link, and refuses anything else, a wrongly typed value, or a link off the product.
- **The recipient's language.** sv reads Swedish, en English, anything else English with a
  log line that names the key and nothing more.
- **Once a day.** A second send of the same template about the same record the same
  tenant-local day writes no row and sends no mail; a refused send keeps its row as failed,
  and the next run retries that row rather than adding one.
- **Nothing logged.** No address, subject or body reaches a log line.
"""

from __future__ import annotations

import dataclasses
import datetime
import smtplib
import uuid
from unittest import mock

from django.conf import settings
from django.test import TestCase

from apps.collab import mail
from apps.collab.mail_strings import CATALOGS, en, sv
from apps.collab.models import EmailMessage, EmailStatus
from apps.identity.models import Membership, UserStatus
from apps.library.reading import today_for
from apps.shared import factories
from apps.shared.adapters.mailer import MockMailer, OutgoingMail
from apps.shared.models import AuditEvent, Tenant

TITLE = "Quarterly custody reconciliation"
OWNER = "Erik Lund"
# Tenant text a caller must never be able to put in a mail.
COMMENT = "Can you check the custody angle before Friday?"
RECORD_ID = uuid.uuid4()
FORBIDDEN = {"body", "note", "notes", "assessment", "summary", "comment", "text", "interpretation"}


def link(path: str = "actions/1") -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/{path}"


def context(**overrides: object) -> mail.MailContext:
    values: dict[str, object] = {
        "title": TITLE,
        "date": datetime.date(2026, 10, 1),
        "count": 6,
        "name": OWNER,
        "link": link(),
    }
    values.update(overrides)
    return mail.MailContext(**values)  # type: ignore[arg-type]


class Catalog(TestCase):
    def test_en_and_sv_hold_one_key_set(self) -> None:
        self.assertEqual(set(en.STRINGS), set(sv.STRINGS))
        self.assertEqual(set(CATALOGS), {"en", "sv"})

    def test_every_template_has_a_subject_and_a_body_beside_the_header_and_footer(self) -> None:
        expected = {"header", "footer"} | {
            f"{t}.{part}" for t in mail.TEMPLATES for part in ("subject", "body")
        }
        self.assertEqual(set(en.STRINGS), expected)
        self.assertEqual(
            set(mail.TEMPLATES),
            {"due_soon", "overdue", "review_due", "escalation", "weekly_digest"},
        )

    def test_every_placeholder_is_typed_context_or_filled_by_the_composer(self) -> None:
        allowed = {field.name for field in dataclasses.fields(mail.MailContext)} | set(
            mail.COMPOSER_FIELDS
        )
        self.assertEqual(
            {field.name for field in dataclasses.fields(mail.MailContext)},
            {"title", "date", "count", "name", "link"},
        )
        for language, catalog in CATALOGS.items():
            for key, text in catalog.items():
                names = mail.placeholders(text)
                self.assertLessEqual(names, allowed, f"{language}:{key}")
                self.assertFalse(names & FORBIDDEN, f"{language}:{key}")

    def test_a_key_interpolates_the_same_names_in_both_languages(self) -> None:
        for key in en.STRINGS:
            self.assertEqual(
                mail.placeholders(en.STRINGS[key]), mail.placeholders(sv.STRINGS[key]), key
            )


class Context(TestCase):
    def test_no_field_can_carry_a_comment(self) -> None:
        with self.assertRaises(TypeError):
            mail.MailContext(body=COMMENT)  # type: ignore[call-arg]

    def test_wrongly_typed_values_are_refused(self) -> None:
        for bad in (
            {"title": 3},
            {"name": ["a"]},
            {"date": "2026-10-01"},
            {"date": datetime.datetime(2026, 10, 1, 8, 0, tzinfo=datetime.UTC)},
            {"count": "6"},
            {"count": True},
            {"count": -1},
        ):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                context(**bad)

    def test_a_link_must_be_a_page_of_the_product(self) -> None:
        for bad in (
            "https://evil.example/actions/1",
            settings.APP_BASE_URL.rstrip("/") + ".evil.example/x",
            "actions/1",
        ):
            with self.subTest(link=bad), self.assertRaises(ValueError):
                context(link=bad)

    def test_titles_and_names_are_folded_to_one_line(self) -> None:
        folded = context(title="Custody\nreconciliation\r\n  Q3", name="Erik\nLund")
        self.assertEqual((folded.title, folded.name), ("Custody reconciliation Q3", "Erik Lund"))

    def test_the_task_argument_round_trips(self) -> None:
        original = context()
        self.assertEqual(mail.MailContext.from_task(original.to_task()), original)
        self.assertEqual(
            mail.MailContext.from_task(mail.MailContext(count=2).to_task()),
            mail.MailContext(count=2),
        )


class Compose(TestCase):
    tenant: Tenant
    member: Membership

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant()
        cls.member = factories.member(cls.tenant)

    def recipient(self, locale: str | None) -> Membership:
        user = self.member.user
        user.locale = factories.language(locale) if locale else None
        user.save(update_fields=["locale"])
        return Membership.objects.select_related("user__locale").get(pk=self.member.pk)

    def test_a_swedish_reader_gets_swedish(self) -> None:
        sent = mail.compose(self.recipient("sv"), "escalation", context())
        self.assertEqual(sent.subject, f"Eskalerad till dig: {TITLE}")
        self.assertIn(f"Hej {self.member.user.name},", sent.body)
        self.assertIn(
            f"{TITLE}, som ägs av {OWNER}, skulle ha varit klar den 2026-10-01", sent.body
        )
        self.assertIn("Dagar försenad: 6", sent.body)
        self.assertIn(link(), sent.body)
        self.assertTrue(
            sent.body.endswith(
                f"Skickat av {settings.PRODUCT_NAME}. Svar till den här adressen läses inte."
            )
        )

    def test_an_english_reader_gets_english(self) -> None:
        sent = mail.compose(self.recipient("en"), "due_soon", context())
        self.assertEqual(sent.to, self.member.user.email)
        self.assertEqual(sent.subject, f"Due 2026-10-01: {TITLE}")
        self.assertEqual(
            sent.body,
            f"Hello {self.member.user.name},\n\n{TITLE} is due on 2026-10-01.\nOpen it: {link()}\n\n"
            f"Sent by {settings.PRODUCT_NAME}. Replies to this address are not read.",
        )

    def test_every_template_composes_in_both_languages(self) -> None:
        for language in ("en", "sv"):
            recipient = self.recipient(language)
            for template in mail.TEMPLATES:
                with self.subTest(language=language, template=template):
                    sent = mail.compose(recipient, template, context())  # type: ignore[arg-type]
                    self.assertEqual(
                        sent.subject,
                        CATALOGS[language][f"{template}.subject"].format(**_values(self.member)),
                    )

    def test_an_unsupported_language_reads_english_and_logs_only_the_key(self) -> None:
        with self.assertLogs("apps.collab.mail", level="WARNING") as logs:
            sent = mail.compose(self.recipient("fi"), "overdue", context())
        self.assertEqual(sent.subject, f"Overdue since 2026-10-01: {TITLE}")
        self.assertIn("collab mail string overdue.subject fell back to en", "\n".join(logs.output))
        for line in logs.output:
            for secret in (TITLE, self.member.user.email, sent.subject, link()):
                self.assertNotIn(secret, line)

    def test_no_language_reads_english_without_a_fallback_line(self) -> None:
        with self.assertNoLogs("apps.collab.mail", level="WARNING"):
            sent = mail.compose(self.recipient(None), "review_due", context())
        self.assertEqual(sent.subject, f"Review due 2026-10-01: {TITLE}")

    def test_a_template_missing_its_context_is_refused_rather_than_printing_none(self) -> None:
        with self.assertRaises(KeyError):
            mail.compose(self.recipient("en"), "weekly_digest", mail.MailContext(count=3, link=link()))

    def test_an_unknown_template_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            mail.compose(self.recipient("en"), "comment_added", context())  # type: ignore[arg-type]


def _values(member: Membership) -> dict[str, object]:
    return {
        "title": TITLE,
        "date": "2026-10-01",
        "count": 6,
        "name": OWNER,
        "link": link(),
        "recipient": member.user.name,
        "product": settings.PRODUCT_NAME,
    }


class _RefusingMailer:
    name = "refusing"

    def send(self, sent: OutgoingMail) -> None:
        raise smtplib.SMTPRecipientsRefused({sent.to: (550, b"no such user " + sent.to.encode())})


class Delivery(TestCase):
    """The delivery task, eager in tests, run the way a reminder task will run it."""

    tenant: Tenant
    member: Membership

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant(timezone="Europe/Helsinki")
        cls.member = factories.member(cls.tenant)

    def setUp(self) -> None:
        MockMailer.reset()
        self.addCleanup(MockMailer.reset)

    def send(
        self, template: mail.Template = "due_soon", *, subject_id: uuid.UUID | None = RECORD_ID
    ) -> None:
        mail.send(
            self.member,
            template,
            context(),
            subject_type="action" if subject_id else None,
            subject_id=subject_id,
        )

    def test_a_mail_goes_once_and_its_row_says_so(self) -> None:
        self.send()
        self.assertEqual([sent.subject for sent in MockMailer.sent], [f"Due 2026-10-01: {TITLE}"])
        row = EmailMessage.objects.get()
        self.assertEqual(
            (
                row.user_id,
                row.template,
                row.subject_type,
                row.subject_id,
                row.status,
                row.sent_on,
                row.to_email,
            ),
            (
                self.member.user_id,
                "due_soon",
                "action",
                RECORD_ID,
                EmailStatus.SENT.value,
                today_for(self.tenant),
                self.member.user.email,
            ),
        )
        self.assertIsNotNone(row.sent_at)
        event = AuditEvent.objects.get(subject_id=row.id)
        self.assertEqual(
            (event.action, event.after["status"], event.after["template"]),
            ("mail.sent", "sent", "due_soon"),
        )
        self.assertNotIn(TITLE, str(event.after) + event.summary + event.subject_title)

    def test_a_second_send_the_same_day_does_nothing(self) -> None:
        self.send()
        self.send()
        self.assertEqual(len(MockMailer.sent), 1)
        self.assertEqual(EmailMessage.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="mail.sent").count(), 1)

    def test_the_digest_which_names_no_record_is_also_sent_once_a_day(self) -> None:
        self.send("weekly_digest", subject_id=None)
        self.send("weekly_digest", subject_id=None)
        self.assertEqual(len(MockMailer.sent), 1)
        self.assertEqual(EmailMessage.objects.get().subject_id, None)

    def test_another_template_or_record_or_day_is_another_mail(self) -> None:
        self.send()
        self.send("overdue")
        self.send(subject_id=uuid.uuid4())
        with mock.patch(
            "apps.collab.tasks.today_for",
            return_value=today_for(self.tenant) + datetime.timedelta(days=1),
        ):
            self.send()
        self.assertEqual(len(MockMailer.sent), 4)
        self.assertEqual(EmailMessage.objects.count(), 4)

    def test_a_refused_send_keeps_its_row_as_failed_and_the_next_run_retries_it(self) -> None:
        with (
            mock.patch("apps.collab.tasks.get_mailer", return_value=_RefusingMailer()),
            self.assertLogs("apps.collab.tasks", level="WARNING") as logs,
        ):
            self.send()
        row = EmailMessage.objects.get()
        self.assertEqual(
            (row.status, row.error, row.sent_at),
            (EmailStatus.FAILED.value, "SMTPRecipientsRefused", None),
        )
        self.assertEqual(MockMailer.sent, [])
        self.assertTrue(AuditEvent.objects.filter(subject_id=row.id, action="mail.failed").exists())
        for line in logs.output:
            for secret in (self.member.user.email, TITLE, row.subject):
                self.assertNotIn(secret, line)
        self.assertNotIn(self.member.user.email, row.error)

        self.send()
        row.refresh_from_db()
        self.assertEqual((row.status, row.error), (EmailStatus.SENT.value, ""))
        self.assertEqual(EmailMessage.objects.count(), 1)
        self.assertEqual(len(MockMailer.sent), 1)

    def test_a_member_who_left_before_delivery_is_sent_nothing(self) -> None:
        self.member.deactivated_at = datetime.datetime.now(tz=datetime.UTC)
        self.member.save(update_fields=["deactivated_at"])
        self.send()
        self.assertEqual((MockMailer.sent, EmailMessage.objects.count()), ([], 0))

    def test_an_inactive_account_is_sent_nothing(self) -> None:
        user = self.member.user
        user.status = UserStatus.DEACTIVATED.value
        user.save(update_fields=["status"])
        self.send()
        self.assertEqual((MockMailer.sent, EmailMessage.objects.count()), ([], 0))

    def test_a_bad_context_is_refused_before_anything_is_queued(self) -> None:
        with self.assertRaises(ValueError):
            mail.send(self.member, "nope", context(), subject_type=None, subject_id=None)  # type: ignore[arg-type]
        self.assertEqual((MockMailer.sent, EmailMessage.objects.count()), ([], 0))

    def test_the_day_is_the_banks_own(self) -> None:
        """The key's day is where the bank is: 23:30 UTC on 30 September is already
        1 October in Helsinki."""
        late = datetime.datetime(2026, 9, 30, 23, 30, tzinfo=datetime.UTC)
        with mock.patch("django.utils.timezone.now", return_value=late):
            self.send()
        self.assertEqual(EmailMessage.objects.get().sent_on, datetime.date(2026, 10, 1))

    def test_nothing_logs_an_address_subject_or_body(self) -> None:
        with self.assertNoLogs("apps.collab", level="DEBUG"):
            self.send()

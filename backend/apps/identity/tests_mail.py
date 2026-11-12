"""The mails identity composes (`apps/identity/mail.py`; ID-01, ID-02, ID-05, D-135, D-138).

What these pin:

- **The text is unchanged.** Each mail's plain text reads as it did before the HTML part.
- **The HTML part says the same** in the shared layout, under the subject as its heading.
- **The invitation link sits behind one button.** Its token appears once in the HTML part.
- **A mail queued before the HTML part existed still sends,** as text alone.
"""

from __future__ import annotations

from django.conf import settings
from django.test import SimpleTestCase

from apps.identity import mail, tasks
from apps.shared.adapters.mailer import MockMailer, OutgoingMail

TO = "anna@bank.example"
BANK = "Example Bank AB"
PRODUCT = settings.PRODUCT_NAME


class IdentityMails(SimpleTestCase):
    def setUp(self) -> None:
        MockMailer.reset()
        self.addCleanup(MockMailer.reset)

    def sent(self) -> OutgoingMail:
        (only,) = MockMailer.sent
        self.assertEqual(only.to, TO)
        self.assertIn(f">{only.subject}</h1>", only.html)
        return only

    def test_the_invitation_puts_its_link_behind_one_button(self) -> None:
        mail.send_invitation(TO, "tok-123", BANK, reenrolment=False)
        sent, link = self.sent(), mail.invitation_link("tok-123")
        self.assertEqual(sent.subject, f"You are invited to {BANK}")
        self.assertEqual(
            sent.body,
            f"You have been invited to {BANK} on {PRODUCT}.\n"
            f"Open this link within {settings.INVITATION_TTL_HOURS} hours to receive your code: {link}",
        )
        self.assertIn(f"You have been invited to {BANK} on {PRODUCT}.", sent.html)
        self.assertIn(f"Open the link within {settings.INVITATION_TTL_HOURS} hours.", sent.html)
        self.assertIn(f'<a href="{link}"', sent.html)
        self.assertIn(">Open the invitation</a>", sent.html)
        self.assertEqual(sent.html.count("tok-123"), 1)
        self.assertIn(f"{BANK}</div>", sent.html)

    def test_a_reissued_enrolment_says_so_and_names_its_own_action(self) -> None:
        mail.send_invitation(TO, "tok-123", BANK, reenrolment=True)
        sent = self.sent()
        self.assertEqual(sent.subject, f"Set up your passkey again for {BANK}")
        self.assertTrue(sent.body.startswith("An administrator re-issued your enrolment."))
        self.assertIn("Your earlier passkeys and sessions no longer work.", sent.html)
        self.assertIn(">Set up your passkey</a>", sent.html)

    def test_an_invitation_to_no_bank_names_the_product_and_no_bank(self) -> None:
        mail.send_invitation(TO, "tok-123", None, reenrolment=False)
        sent = self.sent()
        self.assertEqual(sent.subject, f"You are invited to {PRODUCT}")
        self.assertNotIn("text-transform:uppercase", sent.html)

    def test_the_code_is_in_both_parts(self) -> None:
        mail.send_code(TO, "482915")
        sent = self.sent()
        minutes = settings.ENROLMENT_CODE_TTL_MINUTES
        self.assertEqual(sent.body, f"Your code is 482915. It works once and expires in {minutes} minutes.")
        self.assertIn(">482915</td>", sent.html)
        self.assertIn(f"The code works once and expires in {minutes} minutes.", sent.html)

    def test_the_device_notice_names_the_device_and_what_to_do(self) -> None:
        for device, named in (("Chrome on Windows", "Chrome on Windows"), ("", "A new device")):
            with self.subTest(device=device):
                MockMailer.reset()
                mail.send_device_let_in(TO, device)
                sent = self.sent()
                let_in = f"{named} was let into your account with your passkey."
                if_not_you = "If this was not you, open My sessions, sign out everywhere, and tell your administrator at once."
                self.assertEqual(sent.body, f"{let_in} {if_not_you}")
                self.assertIn(let_in, sent.html)
                self.assertIn(if_not_you, sent.html)
                self.assertNotIn("<a ", sent.html)

    def test_the_administrators_hear_who_reissued_whose_enrolment(self) -> None:
        mail.send_reenrolment_notice(TO, "Johan Berg", BANK, "Karin Nyström")
        sent = self.sent()
        self.assertEqual(sent.subject, f"Enrolment re-issued for Johan Berg at {BANK}")
        for part in (sent.body, sent.html):
            self.assertIn("Karin Nyström re-issued enrolment for Johan Berg.", part)

    def test_a_name_written_as_markup_arrives_as_text(self) -> None:
        mail.send_reenrolment_notice(TO, "<b>Johan</b>", "<i>Bank</i>", "Karin")
        (only,) = MockMailer.sent
        self.assertIn("<b>Johan</b>", only.body)
        self.assertNotIn("<b>", only.html)
        self.assertNotIn("<i>", only.html)
        self.assertIn("&lt;b&gt;Johan&lt;/b&gt;", only.html)

    def test_a_mail_queued_before_the_html_part_existed_still_sends(self) -> None:
        tasks.deliver_mail(TO, "A subject", "A body")
        self.assertEqual(MockMailer.sent, [OutgoingMail(to=TO, subject="A subject", body="A body", html="")])

"""The shared mail layout (`apps/shared/mail_layout.py`, D-138).

What these pin:

- **Nothing remote.** No picture, font, stylesheet or script, so a mailbox that blocks
  remote content shows the mail whole and opening it tells nobody anything.
- **Text stays text.** Every value a composer hands over is escaped, in every block.
- **Links stay in the product.** A link to another host is refused.
- **The parts a reader sees:** the wordmark as text, the bank's name when there is one, the
  heading, the footer, the inbox preview line and a date that never breaks at its hyphens.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.test import SimpleTestCase

from apps.shared import mail_layout
from apps.shared.mail_layout import Block, Button, Code, Facts, Items, Lead, Notice, Small, Steps, Text

MARKUP = '<img src=x onerror="alert(1)">'
ESCAPED = "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"
# What would make a mailbox fetch something, or run something.
REMOTE = ("<img", "<link", "<script", "<iframe", "@font-face", "@import", "url(", "src=", "background=")


def page(path: str = "watch/1") -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/{path}"


def every_block(text: str) -> list[Block]:
    return [
        Text(text),
        Small(text),
        Steps([text, text]),
        Button(text, page()),
        Code(text),
        Facts([(text, text)]),
        Notice(text),
        Lead(text, text, text, text),
        Items(text, [(text, page()), (text, None)]),
    ]


def render(blocks: list[Block], *, title: str = "A title", tenant_name: str = "Example Bank AB") -> str:
    return mail_layout.render(title=title, blocks=blocks, footer="A footer", tenant_name=tenant_name)


class NothingRemote(SimpleTestCase):
    def test_no_block_makes_a_mailbox_fetch_or_run_anything(self) -> None:
        html = render(every_block("Words"))
        for needle in REMOTE:
            self.assertNotIn(needle, html)

    def test_every_address_in_the_mail_is_a_page_of_the_product(self) -> None:
        addresses = re.findall(r"https?://[^\s\"<]+", render(every_block("Words")))
        self.assertEqual(set(addresses), {page()})


class TextStaysText(SimpleTestCase):
    def test_markup_in_any_block_the_title_the_bank_or_the_footer_arrives_as_text(self) -> None:
        html = mail_layout.render(title=MARKUP, blocks=every_block(MARKUP), footer=MARKUP, tenant_name=MARKUP)
        self.assertNotIn("<img", html)
        self.assertNotIn("onerror=\"", html)
        # Title, heading, preview, bank and footer, then every slot of every block.
        self.assertEqual(html.count(ESCAPED), 5 + 16)

    def test_a_link_cannot_break_out_of_its_attribute(self) -> None:
        html = render([Button("Open", page('x"><b>'))])
        self.assertIn('href="' + page("x&quot;&gt;&lt;b&gt;") + '"', html)


class LinksStayInTheProduct(SimpleTestCase):
    def test_a_link_to_another_host_is_refused(self) -> None:
        for bad in ("https://evil.example/watch/1", settings.APP_BASE_URL.rstrip("/") + ".evil.example/x", "javascript:alert(1)"):
            for block in (Button("Open", bad), Items("Rows", [("A row", bad)])):
                with self.subTest(link=bad, block=type(block).__name__), self.assertRaises(ValueError):
                    render([block])


class WhatAReaderSees(SimpleTestCase):
    def test_the_wordmark_is_text_and_the_bank_is_named_beside_it(self) -> None:
        html = render([Text("Words")])
        self.assertIn("[bl&#603;k&#720;]", html)
        self.assertIn("Example Bank AB</div>", html)

    def test_a_mail_about_no_bank_names_none(self) -> None:
        self.assertNotIn("text-transform:uppercase", render([Text("Words")], tenant_name=""))

    def test_the_heading_the_footer_and_the_language_are_the_composers(self) -> None:
        html = mail_layout.render(title="A title", blocks=[], footer="A footer", language="sv")
        self.assertIn('<html lang="sv">', html)
        self.assertIn(">A title</h1>", html)
        self.assertIn(">A footer</td>", html)

    def test_the_first_paragraph_is_the_inbox_preview(self) -> None:
        html = render([Code("482915"), Text("First words."), Text("Second words.")])
        self.assertIn('<div style="display:none;max-height:0;overflow:hidden;">First words.</div>', html)

    def test_a_date_never_breaks_at_its_hyphens(self) -> None:
        html = render([Text("Due on 2026-11-05.")], title="Due 2026-11-05: A title")
        self.assertEqual(html.count('<span style="white-space:nowrap;">2026-11-05</span>'), 2)
        self.assertIn("<title>Due 2026-11-05: A title</title>", html)

    def test_steps_are_numbered_in_order(self) -> None:
        html = render([Steps(["Open the link.", "Enter the code."])])
        self.assertLess(html.index(">1</td>"), html.index("Open the link."))
        self.assertLess(html.index(">2</td>"), html.index("Enter the code."))

    def test_a_lead_without_a_note_shows_no_note_label(self) -> None:
        self.assertNotIn("What it means", render([Lead("Leading", "A change", "What it means", "")]))
        self.assertIn("What it means", render([Lead("Leading", "A change", "What it means", "Plan for it.")]))

    def test_a_row_with_a_page_is_a_link_and_a_row_without_is_text(self) -> None:
        html = render([Items("Rows", [("Linked row", page()), ("Plain row", None)])])
        self.assertIn(f'<a href="{page()}"', html)
        self.assertEqual(html.count("<a "), 1)
        self.assertIn("Plain row", html)

    def test_classic_outlook_gets_its_own_600_px_column(self) -> None:
        html = render([Text("Words")])
        self.assertIn('<!--[if mso]><table role="presentation" width="600"', html)
        self.assertIn("max-width:600px", html)

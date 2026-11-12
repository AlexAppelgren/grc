"""The one HTML layout every mail uses (the Letterhead direction, Alex 2026-11-12, D-138;
`design/system/mail.md`). A composer hands over a title and typed blocks and gets the HTML
part back; the plain-text part stays the composer's own.

- Nothing remote: no picture, no web font, no tracking pixel. A bank's mail filter draws a
  blocked picture as a cross, so the wordmark is text and every shape is a colour or a border.
- Every value is escaped: `format_html` escapes what it interpolates, and nothing here is
  marked safe except the markup this module writes itself. A title, a name or a support
  purpose is somebody's text and never becomes markup.
- Every link opens a page of the product. A link to any other host is refused, so no mail
  can be made to carry one.
- Tables and inline styles, because classic Outlook lays a mail out with Word. Its own
  conditional comment gives it the 600 px column that `max-width` gives everyone else.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from django.conf import settings
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString, mark_safe

# The brand pair of `frontend/src/styles/brand.css` and the neutral text of Green's tokens.
GREEN = "#0a3a2a"
SAND = "#f6f3ec"
RULE = "#ece5d6"
BRASS = "#6a5730"
INK = "#0a0b0b"
MUTED = "#636967"
WARNING = "#fce8cf"

SANS = "font-family:'Segoe UI',Helvetica,Arial,sans-serif;"
MONO = "font-family:Consolas,'Courier New',monospace;"
TEXT = f"{SANS}font-size:15px;line-height:24px;color:{INK};"
LABEL = f"{SANS}font-size:11px;line-height:16px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;"
TABLE = 'role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"'
ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class Text:
    """A paragraph."""

    text: str


@dataclass(frozen=True)
class Small:
    """A closing remark in the muted colour."""

    text: str


@dataclass(frozen=True)
class Steps:
    """What the reader does, in order; the numbers are the order."""

    items: Sequence[str]


@dataclass(frozen=True)
class Button:
    """The mail's one action. The link sits behind the label, so no address shows."""

    label: str
    url: str


@dataclass(frozen=True)
class Code:
    """A one-time code, large enough to read across a desk."""

    value: str


@dataclass(frozen=True)
class Facts:
    """Label and value pairs."""

    rows: Sequence[tuple[str, str]]


@dataclass(frozen=True)
class Notice:
    """What to do when something is wrong."""

    text: str


@dataclass(frozen=True)
class Lead:
    """The leading item, under the brass margin of the product's legal text block. The note
    is left out when it is empty."""

    label: str
    title: str
    note_label: str
    note: str


@dataclass(frozen=True)
class Items:
    """A labelled list of titles, each a link when it has a page."""

    label: str
    items: Sequence[tuple[str, str | None]]


Block = Text | Small | Steps | Button | Code | Facts | Notice | Lead | Items


def _t(text: str) -> SafeString:
    """Text, escaped, in which a date never breaks at its hyphens."""
    return format_html_join(
        "",
        "{}",
        (
            (format_html('<span style="white-space:nowrap;">{}</span>', part) if ISO_DATE.fullmatch(part) else part,)
            for part in ISO_DATE.split(text)
        ),
    )


def _href(url: str) -> str:
    if not url.startswith(settings.APP_BASE_URL.rstrip("/") + "/"):
        raise ValueError("a mail links only to pages of the product")
    return url


def _label(text: str, colour: str = BRASS) -> SafeString:
    return format_html('<div style="{}color:{};">{}</div>', LABEL, colour, text)


def _rows(rows: Sequence[SafeString]) -> SafeString:
    return format_html(
        '<table {} style="border-bottom:1px solid {};">{}</table>',
        mark_safe(TABLE),  # noqa: S308 - this module's own markup
        RULE,
        mark_safe("".join(rows)),  # noqa: S308 - each row was built by format_html
    )


def _block(block: Block) -> SafeString:
    edge = f"padding:10px 0;border-top:1px solid {RULE};"
    match block:
        case Text(text):
            return format_html('<p style="margin:0;{}">{}</p>', TEXT, _t(text))
        case Small(text):
            return format_html('<p style="margin:0;{}font-size:13px;line-height:20px;color:{};">{}</p>', SANS, MUTED, _t(text))
        case Steps(items):
            return _rows(
                [
                    format_html(
                        '<tr><td width="32" valign="top" style="{}{}font-size:15px;line-height:24px;font-weight:700;color:{};">{}</td>'
                        '<td valign="top" style="{}{}">{}</td></tr>',
                        edge, MONO, BRASS, number, edge, TEXT, _t(item),
                    )
                    for number, item in enumerate(items, start=1)
                ]
            )
        case Button(label, url):
            return format_html(
                '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
                '<td bgcolor="{}" style="background:{};border-radius:6px;padding:11px 20px;">'
                '<a href="{}" style="{}font-size:14px;line-height:20px;font-weight:600;color:#ffffff;text-decoration:none;">{}</a>'
                "</td></tr></table>",
                GREEN, GREEN, _href(url), SANS, label,
            )
        case Code(value):
            return format_html(
                '<table {}><tr><td align="center" bgcolor="{}" style="background:{};border:1px solid {};border-radius:8px;'
                'padding:20px 12px;{}font-size:34px;line-height:44px;font-weight:700;letter-spacing:0.22em;color:{};">{}</td></tr></table>',
                mark_safe(TABLE), SAND, SAND, RULE, MONO, GREEN, value,  # noqa: S308 - this module's own markup
            )
        case Facts(rows):
            return _rows(
                [
                    format_html(
                        '<tr><td width="34%" valign="top" style="{}padding-right:12px;">{}</td><td valign="top" style="{}{}">{}</td></tr>',
                        edge, _label(label), edge, TEXT, _t(value),
                    )
                    for label, value in rows
                ]
            )
        case Notice(text):
            return format_html(
                '<table {}><tr><td bgcolor="{}" style="background:{};border-radius:6px;padding:12px 14px;{}font-size:14px;line-height:22px;color:{};">{}</td></tr></table>',
                mark_safe(TABLE), WARNING, WARNING, SANS, INK, _t(text),  # noqa: S308 - this module's own markup
            )
        case Lead(label, title, note_label, note):
            remark = format_html(
                '<div style="margin:12px 0 0;">{}</div><div style="margin:4px 0 0;{}font-size:14px;line-height:22px;color:{};">{}</div>',
                _label(note_label, MUTED), SANS, INK, _t(note),
            )
            return format_html(
                '<table {} style="border:1px solid {};border-radius:8px;"><tr>'
                '<td width="52" align="center" valign="top" bgcolor="{}" style="background:{};border-radius:7px 0 0 7px;padding:14px 0;{}font-size:26px;line-height:30px;color:{};">&sect;</td>'
                '<td valign="top" style="padding:14px 16px 16px;">{}'
                '<div style="margin:6px 0 0;{}font-size:17px;line-height:24px;font-weight:600;color:{};">{}</div>{}</td>'
                "</tr></table>",
                mark_safe(TABLE), RULE, SAND, SAND, MONO, BRASS, _label(label), SANS, GREEN, _t(title), remark if note else "",  # noqa: S308
            )
        case Items(label, items):
            row = '<tr><td style="{}{}font-size:14px;line-height:22px;">{}</td></tr>'
            return format_html(
                '{}<div style="font-size:8px;line-height:8px;">&nbsp;</div>{}',
                _label(label),
                _rows(
                    [
                        format_html(row, edge, TEXT, format_html('<a href="{}" style="color:{};">{}</a>', _href(url), GREEN, _t(title)) if url else _t(title))
                        for title, url in items
                    ]
                ),
            )


def render(*, title: str, blocks: Sequence[Block], footer: str, tenant_name: str = "", language: str = "en") -> str:
    """The HTML part of one mail. `title` is the heading on the sheet, the mail's subject as
    a rule. `tenant_name` names the bank beside the wordmark; a mail that concerns no bank
    leaves it out. The first paragraph is also the line an inbox shows beside the subject."""
    preview = next((block.text for block in blocks if isinstance(block, Text)), "")
    spaced = format_html_join(
        "", '<tr><td style="padding:18px 0 0;">{}</td></tr>', ((_block(block),) for block in blocks)
    )
    return format_html(
        '<!doctype html><html lang="{language}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title></head>'
        '<body style="margin:0;padding:0;background:{sand};">'
        '<div style="display:none;max-height:0;overflow:hidden;">{preview}</div>'
        '<table {table} bgcolor="{sand}" style="background:{sand};"><tr><td align="center" style="padding:36px 16px 40px;">'
        '<!--[if mso]><table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->'
        '<table {table} style="max-width:600px;margin:0 auto;text-align:left;">'
        '<tr><td style="padding:0 4px 18px;"><table {table}><tr>'
        '<td valign="bottom" style="{mono}font-size:24px;line-height:29px;font-weight:700;letter-spacing:0.04em;color:{green};white-space:nowrap;">[bl&#603;k&#720;]</td>'
        '<td align="right" valign="bottom" style="padding:0 0 4px;">{tenant}</td>'
        "</tr></table></td></tr>"
        '<tr><td bgcolor="#ffffff" style="background:#ffffff;border:1px solid {rule};border-radius:8px;padding:34px 32px;">'
        '<table {table}><tr><td><h1 style="margin:0;{sans}font-size:26px;line-height:32px;font-weight:600;color:{green};">{heading}</h1></td></tr>'
        "{blocks}</table></td></tr>"
        '<tr><td style="padding:18px 4px 0;{sans}font-size:12px;line-height:18px;color:{muted};">{footer}</td></tr>'
        "</table>"
        "<!--[if mso]></td></tr></table><![endif]-->"
        "</td></tr></table></body></html>",
        language=language,
        title=title,
        heading=_t(title),
        preview=preview,
        tenant=_label(tenant_name) if tenant_name else "",
        blocks=spaced,
        footer=footer,
        table=mark_safe(TABLE),  # noqa: S308 - this module's own markup
        sand=SAND,
        rule=RULE,
        green=GREEN,
        muted=MUTED,
        sans=SANS,
        mono=MONO,
    )

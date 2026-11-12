# Mail

How every mail looks: the Letterhead direction, chosen by Alex on 2026-11-12 (D-138). One
layout, `backend/apps/shared/mail_layout.py`, renders all twelve mails; a composer hands it a
heading and typed blocks. The plain-text part of each mail is unchanged and travels beside
the HTML part.

## Rules

- **Nothing remote.** No picture, no web font, no stylesheet, no tracking pixel. A bank's
  mail filter draws a blocked picture as a cross, and a remote request tells a third party
  that the mail was opened. Every shape is a colour or a border.
- **The wordmark is text:** `[blɛkː]` in the monospace stack at 700 with 0.04 em tracking,
  in the brand green. The outlined logo files are not used in mail.
- **One action.** The link sits behind one green button, so no address shows. A mail with no
  page to open has no button.
- **Links open the product only.** The layout refuses any other host.
- **The heading is the subject.** No label above it (Alex, 2026-11-12).
- **Tones stay the product's.** The notice block is the `warning` tint; nothing else is
  coloured by meaning.

## Values

| Part | Value |
|---|---|
| Ground | sand `#f6f3ec`, 36 px above, 40 px below, 16 px at the sides |
| Column | 600 px at most, fluid below it; classic Outlook gets a 600 px table of its own |
| Header | the wordmark at 24 px on the left, the bank's name as a brass label on the right |
| Sheet | white, a 1 px `#ece5d6` border, 8 px radius, 34 px by 32 px padding |
| Heading | 26 / 32 at 600 in the green `#0a3a2a` |
| Text | 15 / 24 in `#0a0b0b`; a closing remark 13 / 20 in `#636967` |
| Label | 11 / 16 at 600, uppercase, 0.06 em tracking, brass `#6a5730` |
| Button | green fill, white label 14 / 20 at 600, 6 px radius, 11 px by 20 px padding |
| Code | 34 / 44 at 700 in the monospace stack, 0.22 em tracking, green on a sand panel |
| Lead | a 52 px sand margin with the paragraph sign in brass, the title 17 / 24 at 600 in green |
| Rows (steps, facts, items) | a 1 px `#ece5d6` rule above each row and under the last |
| Notice | the `warning` tint `#fce8cf`, 6 px radius, text 14 / 22 |
| Footer | 12 / 18 in `#636967` on the sand, under the sheet |
| Fonts | `'Segoe UI', Helvetica, Arial, sans-serif` and `Consolas, 'Courier New', monospace` |

Blocks stand 18 px apart. A date never breaks at its hyphens.

## What a mail client changes

Classic Outlook on Windows lays a mail out with Word: it draws square corners and ignores
`max-width`, which is why the layout carries a fixed table for it. Windows Outlook and Gmail
on the web load no web font, which is why the layout names none.

## Contrast

White on the green 12.7:1, the green on white 12.7:1, brass on sand 6.28:1, muted text on
sand 5.06:1, text on the warning tint above 15:1. All from `foundations.md` and
`brand/README.md`.

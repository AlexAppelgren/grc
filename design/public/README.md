# The public page

`index.html` is the whole public page as one standalone file. Open it in a
browser. It is a design, not an implementation: no framework, no tokens
import, no message catalog. When it is built, it becomes a route in the
`(public)` group and every string moves into `src/messages/`.

## What decides the look

Brand values come from `design/brand/README.md` and
`frontend/src/styles/brand.css`: green `#0a3a2a`, sand `#f6f3ec`, brass
`#6a5730` light and `#d9cba9` dark. Neutrals and the six pill tones are Green's
own, read from `frontend/src/styles/tokens.generated.css`, so the pills on this
page are the pills in the product. Component proportions follow
`design/system/foundations.md`: 36 to 40 px controls, 6 px on controls, 8 px on
cards, hairlines, no shadows, fully rounded shapes reserved for pills.

No SEB value is used anywhere on the page. The three brand values are the
placeholders from D-05 and change with that decision, in one block of custom
properties at the top of the file.

## The direction

A legal instrument rather than a software landing page: a printed statute's
structure, set in Caslon, on a bank's colours.

| Decision | What it is |
|---|---|
| Green as a ribbon and one field | A slim green ribbon carries the masthead, the page itself is paper, and the green returns once at the end as the field behind "Access is by invitation". Two appearances, neither of them large, and never on a button, which keeps `foundations.md`'s rule that a primary action stays neutral |
| Sand where the product uses sand | The marginal column, the legal text block and the AI-drafted callout. Nowhere else, so the page is not a cream page |
| Brass as the only accent on paper | Section references, the paragraph sign, the kickers, the rules under headings. In dark it takes over from green, as `brand.css` says the product accent does |
| A marginal column | Every section carries `§ n` and a one-line marginal note in Noto Sans Mono, in the left margin, the way a statute carries marginal headings. Below 880 px it folds to one line above the heading |
| Thick-thin rules | Each section opens on a 3 px rule over a 1 px rule, the printed-document break. No cards around prose, no shadows anywhere |
| One sentence where two would do | Every section was cut back after the first draft: a heading, a line, and the artefact or list that proves it. Nothing on the page explains twice |
| Real records, not screenshots | The hero holds a change record built from the prototype's own sample data, with the real pill tones, a real diff and the audit chain under it, marked as a sample |

## Type

| Role | Face | Size |
|---|---|---|
| Plate headline | Libre Caslon Display 400 | `clamp(36px, 1.15rem + 4.4vw, 60px)` / 1.04 |
| Section heading | Libre Caslon Display 400 | `clamp(26px, …, 36px)` / 1.12 |
| Lede and record titles | Libre Caslon Text 400, italic for the lede | 18 to 20 px |
| Deck and prose | Hanken Grotesk 400 | 16 / 1.6, measure 62ch |
| Sub-heading, labels, buttons | Hanken Grotesk 500 and 600 | 15 to 18 px |
| Marginalia, references, citations, the chain, the colophon | Noto Sans Mono 400 and 500 | 12 to 13 px |
| Inside a product artefact | The app's own scale | 14 body, 13 meta, 11 microlabel |

Libre Caslon Display and Libre Caslon Text are both SIL OFL (checked in
`google/fonts`, `ofl/librecaslondisplay` and `ofl/librecaslontext`), so they
self-host on the same terms as Hanken Grotesk and Noto Sans Mono. The file
links Google Fonts as the prototype does; a build self-hosts all four.

## What the page contains

| | Section | What it carries |
|---|---|---|
| | Masthead | On the green ribbon: wordmark, five section links, theme toggle, Sign in, Request access |
| | Plate | On paper: the headline, the deck, both actions, and the sample change record with its diff, its AI-drafted callout and its chain |
| | Facts strip | Jurisdictions, content languages, the two zones, audit from the first write |
| § 1 | The case | Why a spreadsheet and an inbox cannot answer what a review asks |
| § 2 | What it does | Inventory, Watch, Ask, Evidence, one paragraph each |
| § 3 | The method | The six steps from sighting to sign-off, with the actor at each one |
| § 4 | Two zones | The shared library, the one-way proposal door, the tenant zone under forced row-level security |
| § 5 | Coverage | Five jurisdictions against their authorities and publication languages |
| § 6 | Assurance | Access, four eyes, isolation, model use, the ledger, retention, leaving, the pack |
| § 7 | Questions | Six, including what it costs and how people get in |
| | Request access | Name, work email, bank, and a note that the prototype sends nothing |
| | Footer | Wordmark, the pronunciation, product, company and trust columns, the colophon |

Nothing on the page is a customer name, a logo, a testimonial or a number we
cannot stand behind. The claims are the PRD's invariants in the words a bank
would use, and the page says what happens rather than how it is built: the
mechanism appears only where a vendor review asks for it, in § 6.

Three claims rest on decisions and would be wrong without them. The second
pair of eyes on a library proposal is a second agent of a different definition
and key, not a bleqq editor, and what it confirms carries machine-confirmed
provenance naming both agents (D-62, D-14, ADR 0054), which is why § 3 and the
record's chain read as they do. A problem report stays inside the bank that
filed it and nobody outside reads it; the correction comes from the agents'
re-check of each record against its source, through the ordinary proposal door
(D-50, ADR 0043, AUD-03), which is what § 7 says. Sign-off inside the bank is a
person, and that is the one place the page claims a person decides.

## Behaviour

Below 880 px the top bar is one line: the wordmark and a Menu button. Menu
opens a panel under the ribbon holding the five sections as 44 px rows, then
both actions and the theme toggle. It closes on a choice, on Escape, and when
the viewport grows past 880 px. Only there is the ribbon sticky, so the way
back is always one tap away, and it clears the notch through
`top: env(safe-area-inset-top)`; sections carry a 76 px `scroll-margin-top`
so an anchor never lands under it. The page gutter takes the larger of its own
step and the safe-area inset at each side, as `foundations.md` asks. On a wide
screen the bar keeps the five links inline and scrolls away with the page.

Light, dark and the unset system theme are all designed; the toggle stamps
`data-theme` and remembers the choice per device, and every colour is a custom
property declared in the light block first. The form is inert and says so on
submit. There is no motion beyond hover and smooth scrolling, and
`prefers-reduced-motion` turns that off. No horizontal scroll at 390 px, no
element wider than the viewport, a 20 px minimum side gutter.

## Open, for Alex

- The display serif is a brand decision: `design/brand/README.md` names only
  Hanken Grotesk and Noto Sans Mono. Libre Caslon is proposed here because the
  brief asked for an old legal feeling; without it the page runs on Hanken
  Grotesk at the same scale and loses that.
- `foundations.md` sets `hero` at 36 / 40 for public pages. That size was set
  for a grotesque; a serif at 36 px reads a step smaller, so the plate headline
  runs to 60 px on a wide screen. Confirm, or the clamp caps at 36.
- The footer carries `org. no. [to be set]`, and Terms, Privacy and
  Sub-processors point at the assurance section until those pages exist.

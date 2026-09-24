# The public page

`index.html` is the whole public page as one standalone file. Open it in a
browser. Alex approved it on 2026-09-24, and it is built at `/welcome`
(`frontend/src/app/(public)/`, `src/components/public/`, copy in
`src/messages/public/`). Every person without a session ends up there: after
signing out, when a session times out or is revoked, and on a first visit to
any address. The sign-in page links back to it. What the
build left out of the design: the request form, which sent nothing, became a
mail link to `NEXT_PUBLIC_SUPPORT_CONTACT`; the footer's placeholder links and
organisation number are gone; section headings use the `display` size, since
the type scale has no role between it and `hero`.

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
| Green as one field | Since 2026-09-24 the top bar is paper with a hairline, not green; the green is left for the closing field and the thin section rules. Never on a button, which keeps `foundations.md`'s rule that a primary action stays neutral |
| Sand where the product uses sand | The marginal column, the legal text block and the AI-drafted callout. Nowhere else, so the page is not a cream page |
| Colour kept to the section references | Since 2026-09-24 hierarchy comes from type and the two greys, as on the best-reviewed legal and product pages: brass marks the `§ n` references, the accent the double rules, and the eyebrow, kickers, step numbers and footer labels are muted. In dark the accent turns brass, as `brand.css` says the product accent does |
| A marginal column | Every section carries `§ n` in Noto Sans Mono in the left margin, the way a statute carries marginal headings, and its heading says what the section shows, so a reader who only scans the headings still gets the argument. The one-line marginal notes were dropped on 2026-09-24 because they repeated the heading. Below 768 px the reference sits above the rule |
| Thick-thin rules | Each section opens on a 3 px rule over a 1 px rule, the printed-document break. No cards around prose, no shadows anywhere |
| One sentence where two would do | Every section was cut back after the first draft: a heading, a line, and the artefact or list that proves it. Nothing on the page explains twice |
| Real records, not screenshots | The hero holds a change record built from the prototype's own sample data, with the real pill tones, a real diff and the audit chain under it, marked as a sample |

## After the first live look (2026-09-24)

Alex, on a phone: the start page was cluttered and nothing drew the eye. The
first screen had four buttons (the bar's two and the hero's two), the sample
record with its red and green diff directly under them, and on a wide screen a
four-cell facts strip. Now the first screen holds the headline and the line
under it; the bar keeps Sign in and Request access, sticky, so the hero repeats
neither. The sample record moved into § 3, where it is the worked example of
the six steps. The facts strip is gone: jurisdictions and languages are in § 5,
the zones in § 4, and a change kept beside what it replaced in § 1. Each
section break is the double rule alone, without a hairline above it.

The same day, on colour: too many colours competing for attention. The top bar
dropped its green and sits on the page's own paper with a hairline under it,
the wordmark in the text colour, the links muted, Sign in as the app's neutral
primary and Request access as the outline. Green is left in two places: the
thin section rules, and the closing "Access is by invitation" field.

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
| | Demo | Since 2026-09-24, under the headline: the product itself on a sample bank's data (below, "The demo") |
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

The top bar carries the wordmark and two buttons at every width, and it is
sticky, so Sign in is on screen wherever the reader has got to. Sign in is the
primary of the pair and Request access the outline beside it, in that order,
because the rule in `design/README.md` puts the primary on the right. From
881 px the five section links sit between the wordmark and the buttons; below
that they step aside and the footer carries them instead. There is no menu
button: at 320 px the bar is still one 56 px row. It clears the notch through
`top: env(safe-area-inset-top)`, sections carry a 76 px `scroll-margin-top` so
an anchor lands under the bar with room to spare, and the page gutter takes the
larger of its own step and the safe-area inset at each side: 16 px below 768 px
and 32 px above, which is `foundations.md`'s rule. The light and dark switch
sits in the footer, beside the colophon.

The hero keeps the opposite emphasis, Request access filled and Sign in
outlined, because the top of the page is read by someone who has no account
yet. Say the word and the two match.

Light, dark and the unset system theme are all designed; the toggle stamps
`data-theme` and remembers the choice per device, and every colour is a custom
property declared in the light block first. The form is inert and says so on
submit. There is no motion beyond hover and smooth scrolling, and
`prefers-reduced-motion` turns that off. No horizontal scroll at 390 px, no
element wider than the viewport, a 20 px minimum side gutter.

## The demo

Alex, 2026-09-24: an interactive demo like Linear's, but the exact product UI,
kept working whenever the UI or the API changes. Linear's is a hand-built copy
of its app with static data (no frame, no calls to its data API, measured on
linear.app the same day); ours is the app itself.

- **What runs.** The public page frames the app (`src/components/public/DemoFrame.tsx`)
  under the name `bleqq-demo`. Inside that frame, and only when its parent is
  this same origin, the one axios instance answers every request from
  recordings (`src/features/demo`): no request leaves the browser, so the demo
  cannot read or change real data even beside a signed-in session. Writes are
  refused with the screen's ordinary problem message, sign-out restarts the
  demo at Today, and the demo's clock reads the day it was recorded.
- **Where the data comes from.** The demo journey (`tests/e2e/demo.journey.spec.ts`)
  signs in on the real stack as the seeded reader of Example Bank AB, who reads
  everything and changes nothing, and walks every tenant screen in the
  navigation except administration and the person's own settings: each screen,
  its tabs, its toggles and the records it links to. What the backend answered
  is the recording. So the data is `seed_e2e`'s, which every chunk already
  extends, and the demo grows with it. Two things are changed on the way in and
  nothing else: the seed's " (E2E)" name marks are dropped, and grants that only
  open administration are left out of the person's `/me`, so the app's own
  rules hide Admin.
- **How it stays current.** Every run of the journeys (it is `@smoke`, so every
  push) walks the app again and compares the answers with the committed
  recordings by API path template and field shape, never by value. A screen
  asking for something unrecorded, or an answer that gained, lost or retyped a
  field, fails the journey with the command that fixes it:
  `npm run demo:record` in `frontend/`, then commit the two files it writes.
- **Phones and desktops.** On a desktop the frame sits in the page and loads
  when it scrolls near. On a phone a button opens it full screen, because a
  frame inside a scrolling page traps the thumb, and nothing of the app loads
  before that. The recordings are their own chunk (about 30 KB compressed), so
  the page itself never carries them.
- **Not a mocked test.** The replay is what the public page ships, not a test
  double: every journey, the demo's recording walk included, runs against the
  real API.

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

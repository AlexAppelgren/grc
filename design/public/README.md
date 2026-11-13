# The public page

`index.html` is the whole public page as one standalone file, with its fonts and the demo's two
pictures inside it. Open it in a browser, scroll it, and move the pointer across the logo. Alex
chose this direction, the Lexicon, on 2026-11-11 (D-130), and it replaces the legal-instrument
direction of 2026-09-24. It is built at `/welcome` (`frontend/src/app/(public)/`,
`src/components/public/`, copy in `src/messages/public/`). Every person without a session ends
up there: after signing out, when a session times out or is revoked, and on a first visit to any
address. The sign-in page links back to it.

## The idea

The brand name is a pronunciation, so the page is written as a dictionary. The phonetic logo
fills the top of a green page, its letters are cut out of the page, and ink moves behind them.
Each section below it is a dictionary entry with a headword, a part of speech and numbered
senses. Two entries are struck out by hand in red and corrected in pen, which is the redline
that the product itself keeps.

## Entries, in page order

| Entry | Headword, en and sv | What it carries |
|---|---|---|
| `bleqq` | bleqq, for screen readers only | The deck, Try out our demo and Request access, and cross-references on the left; where the name comes from on the right, level with the deck |
| `demo` | demo | Two senses, then the demo across both columns |
| `spreadsheet` | spreadsheet, kalkylark, struck: see inventory | Two senses, each with a struck claim and a pen correction |
| `inbox` | inbox, inkorg, struck: see watch | One sense with a struck claim and a pen correction |
| `watch` | watch, bevaka | Two senses and a usage line |
| `inventory` | inventory, förteckning | Two senses and the example provision on a sand sheet with a typeset redline |
| `ask` | ask, fråga | Two senses |
| `evidence` | evidence, underlag | Two senses and a usage line |
| `library` | library, bibliotek | The shared library, with the copy of the page before |
| `zone` | zone, zon | Your zone, and what never reaches a model |
| `signoff` | sign off, attestera | One sense and the six steps in order |
| `source` | source, källa | One sense and the five jurisdictions with their languages |
| `assurance` | assurance, granskning | What a vendor review asks, and the eight answers |
| `question` | question, fråga | The six common questions |
| `request` | | "Access is by invitation." with Request access and Sign in |

The reference has no entry for the library, the zone, the vendor review or the common questions.
They keep their copy as the four entries above (PUBLIC-CONTENT-LEFT-OUT). The English and the
Swedish of every entry come from the brief of 2026-11-11, in which Alex approved förteckning for
the inventory and attestera for a sign-off; every other catalog uses the same two words.

## What decides the look

| Decision | What it is |
|---|---|
| One appearance | One green page in either theme, so the light and dark switch is gone (PUBLIC-ONE-APPEARANCE). The colours are the public set in `brand.css`, under `:root` alone so that `.dark` never changes them: the brand green `#0a3a2a`, the sand `#f6f3ec` as paper, the dark brass `#d9cba9`, a deeper green for the closing field, and the reference's red, struck grey and sheet colours. Each text pair is pinned in `contrast.ts`. The page wraps itself in `dark`, so the demo's tokens and pictures are dark on it |
| The text colour | Everything a visitor reads runs in the paper colour, and grey is left to short labels: the pronunciation, a source's languages, the top line and the footer (Alex, 2026-09-25). Nothing on the page is italic |
| Paper | A noise tile at 22 % with the overlay blend lies over the whole page, as the paper's grain |
| One layout | Every entry is `Entry` in `PublicPage.tsx`: the headword and its part of speech on the left, sticky from 860 px, the senses on the right, and an optional row across both columns. The page's own entry under the logo is the one exception (Alex, 2026-11-11): the logo already shows the name, so its h1 is for screen readers and search engines, the pronunciation is not repeated, and the deck takes the wide column on the left with the name's origin on the right |
| Two actions on a phone | They share one row, with the main action on the right. Below 410 px they take a smaller size and below 360 px the play icon goes, so they still fit inside the margins at 320 |

## Type

| Role | Face | Size |
|---|---|---|
| `text-headword`: a headword, the closing line | Libre Caslon Display 400 | `clamp(3rem, 6.08vw, 5.8rem)` / 0.92, the reference's size times 0.8 |
| `text-lede`: the deck | Libre Caslon Display 400 | `clamp(1.5rem, 2.16vw, 1.92rem)` / 1.28, the reference's size times 0.8 |
| `text-sense`: senses, the page's running text | Libre Caslon Text 400 | 18 px / 1.62 |
| `text-sheet`: the example provision | Libre Caslon Text 400 | `clamp(1.15rem, 1.6vw, 1.4rem)` / 1.45 |
| `text-pen`, `text-pen-head`: the corrections | Reenie Beanie 400 | 1.8 times the sense; in a headword the larger of half its size and 32 px |
| Sense numbers, step names, jurisdictions | Libre Caslon Display 400 | `text-display` at 400 |
| Parts of speech, usage lines, buttons, the bar | Hanken Grotesk 400 to 600 | `text-title` |
| The pronunciation, and the logo at 700 | Noto Sans Mono | |

Every face is SIL OFL and self-hosted. Reenie Beanie is pinned at `@fontsource/reenie-beanie`
5.3.0 and, like Libre Caslon, loads in the `(public)` layout only (PUBLIC-HANDWRITING-FONT,
ADR 0019). The public roles live in `theme.css` beside `text-hero`, and no signed-in screen uses
them.

## Behaviour

- **The bar.** Sticky and 64 px high on the green. The top line and the links Demo, Method and
  Sources show from 860 px. Request access and Sign in show at every width as two buttons, with
  Sign in filled on the right: Alex asked on 2026-11-11 for Sign in to be the main action and
  Request access the second one, in the bar and in the closing section. Sign in is a plain link,
  so a page load reaches the server, which moves it to the app's own host when there is one
  (`src/proxy.ts`).
- **The ink** (`InkHead.tsx`). An SVG mask cuts `[blɛkː]` out of a green rectangle over a canvas.
  Its view is cropped to the ink of the two brackets (61.6 to 938.8 of the line's 1000 units in
  Noto Sans Mono at 700), and the page's gutter is set to where they start and end, so the bar,
  the deck, the entries and the demo line up with the brackets at every width (Alex,
  2026-11-11: the text narrows, the logo keeps its size). The gutter is
  `(100% - 0.8772 × (100% - 1.1 × margin)) / 2`, the margin being the reference's
  `clamp(1.25rem, 5vw, 5.5rem)`: the logo's frame used to sit 0.55 of that margin in from each
  side, and the brackets span 87.72 % of it. Since 2026-11-12 the whole design is a fifth
  narrower on a wide screen (Alex): 80 % of that width, but never under 700 px or under what
  it was below that, so phones and tablets keep their width, and the headword and the deck
  are set at 0.8 of the reference's sizes to match. Below about 1540 px the demo's frame is
  then under 1024 px wide, so the app inside shows its tablet tab bar instead of the rail.
  A small fluid simulation on WebGL2 half-float targets carries the ink, so the pointer drags it
  in every direction and the ink settles back in a few seconds. The reference's script is the
  specification, and the component ports it with no new dependency. When the simulation cannot
  start, the resting pattern runs alone; under `prefers-reduced-motion` it is one still frame;
  without WebGL the element's CSS background stays. The element names its mode in `data-ink`
  (`fluid`, `pattern`, `still` or `css`) for the tests, and the loop stops while the logo is off
  screen.
- **The redline** (`RevisedEntry.tsx`). A struck entry draws its strike, then writes the
  headword's correction, then each sense's, once, when its top passes two thirds of the way up
  the screen. As the server sends the page, and under `prefers-reduced-motion`, it is already
  drawn.
- **Request access.** In the bar and under the deck it jumps to the closing section. There it is
  the mail link to `NEXT_PUBLIC_SUPPORT_CONTACT` with the subject filled in, outlined beside a
  filled Sign in. While no contact is set, the section says that a bank's administrator sends the
  invitation and offers Sign in alone.
- **Anchors** land below the bar. The skip link goes to the main content, and the demo's own
  skip link to the two struck entries (`#case`).

## The demo

Since 2026-11-11 the demo is the demo entry's row across both columns, and the page shows its
dark pictures whatever the visitor's theme. `DemoFrame.tsx`, the demo and its recordings are
otherwise as they were.

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
- **Where the data comes from** (Alex, 2026-10-03, D-120: "I would like it to use the
  actual library and then the rest can be mocked"). The library is the real one: the whole
  baseline in `backend/apps/library/baseline/`, filed through the proposal door by
  `library-baseline` and approved by `library-confirmer`, an agent of another definition and
  key, so every record reads machine-confirmed as it will in production. Only Example Bank AB
  is made up: its organisation, register, cases, comments, evidence and briefing, built on
  real stable keys. Its regulatory changes are facts of the baseline itself, the days an
  instrument's duties start to apply, with that instrument's own authority and page, so no
  authority is said to have published anything it did not. `seed_public_demo`
  (`backend/apps/shared/demo_seed.py`) seeds it on a stack of the demo's own (its own
  database and ports, `E2E_DEMO_STACK` in `playwright.config.ts`), never the journeys'
  `seed_e2e`. The demo journey (`tests/e2e/demo.journey.spec.ts`, `@demo`) signs in there
  as the bank's reader, who reads everything and changes nothing, and walks every tenant
  screen in the navigation except administration and the person's own settings: each
  screen, its tabs, its toggles and the records it links to. What the backend answered is
  the recording, with grants that only open administration left out of the person's `/me`,
  so the app's own rules hide Admin. The bank's register sits on the duties that sort first
  in its inventory, because the walk follows at most twenty records a route. What applies
  is opened once more for each company under each filter, by the address the screen itself
  writes, because its chips count per company and pressing one renames the rest; and when
  recording, every regulation's line on those first pages is opened, so that in the demo
  each of them shows its own obligations. A later page of its regulations and a search in
  it are not recorded, as on every list of the demo (below, "Where nothing was recorded").
- **Where nothing was recorded** (Alex, 2026-11-13). A list under a filter the walk never
  pressed is answered by the first recording of that list, which shows the right kind of
  rows. A later page (`offset` above 0) or a search (`q`, `query` or `search` with text) is
  never answered that way, since the first page would read as its answer: like any read
  with no recording, it fails with `demo_not_recorded`. In the demo frame the app's
  not-found screen and every error state read the demo's own line, "The demo has no
  sample data for this page.", the first with a link back to Today and the second with no
  Try again, since no connection is at fault (`NotFoundScreen` and `ErrorState` in
  `States.tsx`, through `useDemoFrame`). So a record the walk never reached, a later page,
  a search and an address the app does not have all say that, never "Not found" or "Check
  your connection". The recorded week before the first briefing reads it too. Admin's tab
  bar is not drawn: Licences, which What applies links to and the demo answers, stands
  alone, with no tab to Admin pages the demo holds nothing for.
- **How it stays current.** CI's `demo` job, on every push, boots the demo's stack and
  walks the app again and compares the answers with the committed
  recordings by API path template and field shape, never by value. A screen
  asking for something unrecorded, or an answer that gained, lost or retyped a
  field, fails the journey with the command that fixes it:
  `npm run demo:record` in `frontend/`, then commit what it writes: the two
  recording files and the four pictures below.
- **What a visitor sees first** (Alex, 2026-09-27, proposal A of the canvas
  "Demo on the public page: proposals"; the desktop changed 2026-10-03). On a
  desktop the live app runs in place straight away, with a "Skip the demo" link
  for keyboard users, and the page does not move to it. On a phone a frame
  inside a scrolling page traps the thumb, so a picture of the demo's Today and
  one button, "Try out our demo", with "Example Bank AB is made up, and nothing
  you do in it is saved.", open it full screen, and the page behind it holds
  still; nothing of the app loads before the press. Either way a sand bar above
  it names the demo and the bank and offers Start over (and Close, on a phone),
  so nobody takes it for the real product.
- **The pictures** (`frontend/public/demo/today-{desktop,phone}-{light,dark}.jpg`;
  the desktop's holds the frame's place until the browser knows the width) are
  taken of the demo itself by the recorder's second pass, on a build that
  already carries the new recordings, so they show the same sample bank as the
  live demo. A change to the look alone does not fail the gate, so re-record
  after a visible change to Today. The recordings are their own chunk, so the
  page itself never carries them.
- **Framing.** The app answers every page with `Content-Security-Policy:
  frame-ancestors 'self'` and `X-Frame-Options: SAMEORIGIN` (`next.config.ts`),
  so only its own public page can frame it and no other site can put it under a
  click trap; the API refuses every frame on its own side.
- **Not a mocked test.** The replay is what the public page ships, not a test
  double: every journey, the demo's recording walk included, runs against the
  real API.

## Open, for Alex

Three defaults, each in `docs/TODO_FOR_alex.md` under D-130: the one appearance, and with it a
live demo that still follows the visitor's theme on a desktop (PUBLIC-ONE-APPEARANCE); the
handwriting font (PUBLIC-HANDWRITING-FONT); and the four entries the reference left out
(PUBLIC-CONTENT-LEFT-OUT).

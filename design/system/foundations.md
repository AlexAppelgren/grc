# Foundations

The values the frontend is ported to. Source: Alex, 2026-09-19: the prototype
"looks big, clumsy and childish"; take much less from seb.io (keep its
colours) and more from shadcn/ui. ADR 0020, amendment "Foundations".

**The rule in one line.** Green's colours (the neutral scale for surfaces,
borders and text, the brand pair through `brand.css`) at shadcn/ui's
proportions: a 14 px base, a small radius, hairline cards, compact controls.
shadcn values were read on 2026-09-19 from its registry source,
`github.com/shadcn-ui/ui/apps/v4/registry/new-york-v4/ui/` (`button.tsx`,
`badge.tsx`, `card.tsx`, `input.tsx`, `table.tsx`, `sidebar.tsx`), its
`dashboard-01` block and `apps/v4/styles/globals.css` (`--radius: 0.625rem`),
not recalled. The entry belongs in `docs/plans/Verification_Log.md`.

## Type roles

Names are the playbook's (6.4) and stay. Values changed. One family for text
(Hanken Grotesk), Noto Sans Mono for legal references and the wordmark. Three
weights: 400, 500, 600 (700 is gone).

| Role | Size / line height | Weight | Tracking | Was |
|---|---|---|---|---|
| `hero` | 36 / 40 | 600 | -0.025em | public pages only, unchanged in use |
| `display` | 24 / 32 (phone 20 / 28) | 600 | -0.02em | 32 px at 400, lead headlines up to 30 px |
| `title` | 16 / 24 | 600 | -0.01em | 20 px at 500, stat values 36 px |
| `body` | 14 / 20 (long prose 14 / 22) | 400 | 0 | 16 / 24 |
| `meta` | 13 / 18 | 400 | 0 | 13.6 to 15 px, five near-duplicates |
| `microlabel` | 11 / 16, uppercase | 500 | 0.06em | not used; the date kicker was 15 px |

Why: 16 to 18 px everywhere and a 32 px regular-weight title read as a
consumer page. shadcn's scale for the same job is `text-sm` (14 / 20) with
`text-2xl font-semibold tracking-tight` headings. Semibold titles at a
smaller size give more hierarchy with less area. Long prose (the legal text,
the AI callout) keeps 22 px leading for reading. The date eyebrow above the
page title is a `microlabel`.

Buttons use `body` at 500, sentence case, as shadcn's do. Playbook 6.4 still
lists "button labels" under `microlabel`; that line is for Alex to confirm
or correct (see the report of 2026-09-19).

## Radius

| Use | Green token | Value | Was |
|---|---|---|---|
| Controls: button, input, select, toggle, nav row, current tab, callout, banner | `radius-2xs` | 6 px | 999 px buttons, 8 px inputs |
| Cards, list rows, empty states, toast | `radius-xs` | 8 px | 16 to 20 px |
| Dialogs, the sheet and the floating tab bar | `radius-s` | 12 px | 20 px |
| Pill | `radius-max` | 999 px | unchanged |
| Inline marks (`ins`, `del`, `mark`), meters | none (3 px, 2 px) | | 999 px bars |

shadcn's own base is 10 px (`rounded-md` 8 px, `rounded-xl` 14 px on cards).
Ours is one step tighter because Green's scale has 6 and 8, not 10 and 14,
and a small radius reads as a tool. The tab bar is 12 px, never fully
rounded. With its 6 px padding, the 6 px current tab sits concentric with it.

## Spacing

A 4 px grid. Page padding 24 / 32 px (desktop), 12 / 16 px (phone). Card
padding 16 px, gap between cards 16 px, heading to content 12 px, button row
16 px above. List rows 12 px by 16 px. Content max width 1200 px, left
aligned beside the rail. Was: 20 to 28 px card padding, 32 / 36 px page
padding, 1100 px.

The page gutter is safe-area aware at every width. Each side takes the larger
of its step and the safe-area inset. At the sides that is 16 px below 768 px
and 32 px from 768 px (`max(16px, env(safe-area-inset-left))`, and the same on
the right). On top below 768 px it is `max(12px, env(safe-area-inset-top))`.
So nothing sits under a notch, a sensor housing or the home indicator.

Below 1024 px the page ends with room for the tab bar: its measured height,
plus its bottom gap, plus 16 px (`calc(var(--tabbar-top) + 16px)`).
`scroll-padding-bottom` takes the same value, so a focused control never sits
behind the bar. Anything else fixed to the bottom there, such as a toast,
sits at `calc(var(--tabbar-top) + 8px)`. From 1024 px the bottom padding is
64 px, as before.

## Shadow

One shadow, `float`: Green `shadow-l-01` and `shadow-l-02` together (Green
shadows come in pairs). Only the floating tab bar uses it, because it is the
one layer that sits over scrolling content. Cards stay flat.

## Components

**Button.** 36 px tall (`h-9`), 16 px side padding, 6 px radius, `body` at
500, 8 px icon gap, 16 px icon. Small: 32 px, 12 px padding. Variants:

| Variant | Background | Text | Border | Hover |
|---|---|---|---|---|
| primary | `l3-neutral-03` | `content-neutral-03` | same as background | 88% mix toward the page |
| outline | `l2-neutral-02` | `content-neutral-01` | `border-neutral-02` | `state-neutral-05` overlay |
| ghost | none | `content-neutral-01` | none | `state-neutral-05` overlay |
| danger | `l2-neutral-02` | `content-negative-01` | `border-neutral-02` | `l3-negative-02` (light) |

No fully rounded buttons. Primary stays neutral (near black in light, near
white in dark), as shadcn's and seb.io's do, so brand green is not spent on
actions. On phones two buttons share a row, primary on the right (6.8).
Was: 44 px, fully rounded, 600 weight.

**Card.** `l2-neutral-02` on the page, a 1 px hairline, 8 px radius, 16 px
padding, no shadow. No sand fills: the old "feature" and sand panels are
ordinary cards. Stat tiles are cards with the value in `title` and the label
in `meta`. Was: 16 to 20 px radius, 20 to 28 px padding, sand fills.

**Pill (shadcn Badge).** Fully rounded, 20 px tall, 8 px side padding,
`meta` at 500, no border. shadcn's current Badge is `rounded-full px-2 py-0.5
text-xs font-medium`, so the shape stays; with buttons, toggles and nav rows
now at 6 px, the fully rounded shape is the pill's alone and cannot be
mistaken for a control. Tones and dark backgrounds: `pills-and-labels.md`.
Was: 2 by 10 px padding, 600 weight, 12.5 px.

**Input and select.** 36 px, 10 px side padding, 6 px radius, `body`,
background `l2-neutral-02`, border `border-neutral-01` (4.15:1 light, 7.05:1
dark, over the 3:1 WCAG 1.4.11 asks of a field boundary; shadcn's lighter
input border would not pass). Placeholder in `content-neutral-02`, italic.
Textarea 76 px minimum. Label `body` at 500, hint and error `meta`. Was:
44 px, 8 px radius.

**Toggle** (filter and footprint chips, the Search / Ask switch). 32 px, 12 px
padding, 6 px radius, `body` at 500. Off: `l2-neutral-02`, `border-neutral-02`,
`content-neutral-02` text. On: `l3-neutral-02`, `border-neutral-01`,
`content-neutral-01` text. Was: fully rounded, solid black when on.

**Tabs.** Underline tabs, 14 px at 500, muted until selected; the selected tab
gets the text colour and a 2 px underline.

**Sidebar row** (shadcn `SidebarMenuButton`, size default). 32 px (`h-8`),
8 px padding, 8 px gap, 6 px radius, 16 px icon at 1.75 stroke, `body`.
Current row: `l3-neutral-02` and 500 weight. Hover: `state-neutral-05`. Groups
separated by 16 px. Width 240 px, 48 px collapsed (shadcn 3rem). The rail
shows from 1024 px; below that the tab bar takes its place. Account row: name
at 500, organisation and role in `meta`. Was: 36 px rows, 18 px icons, 16 px
labels.

**Tab bar** (below 1024 px; every rule and its source in `navigation.md`). A
floating bar at the bottom: up to four dock destinations from the registry,
then More, which is always last. It floats 16 px above the bottom edge and
16 px from the sides, each the larger of that gap and the safe-area inset.
Below 400 px the side gap is 8 px. The bar is as wide as its cells and
centred: equal cells of at most 96 px, no gap, each cell the whole target.
It is 64 px tall: 6 px padding, a 52 px cell, 6 px padding, with the 1 px
border inside. It grows when a label wraps and never clips. 12 px radius
(`radius-s`), solid `l2-neutral-02`, a 1 px hairline, the `float` shadow, no
blur. It sits above the page and below the scrim and dialogs, and is hidden in
print. A tab is a 20 px icon, a 4 px gap and the label in `meta`, on one or
two lines, never truncated and never set smaller. "Search and ask" shows as
"Search" in the bar. Rest: `content-neutral-02` at 400. Hover:
`state-neutral-05`. Current: `l3-neutral-02` over the whole cell with a 6 px
radius, plus a 1 px `border-neutral-01` outline inset by 1 px, and the text
colour at 500. The outline is the part that reaches 3:1; the fill alone does
not. Keyboard focus swaps the outline for the 2 px focus ring. While the
current page lives in the More sheet, More takes the current treatment.
Below 480 px tall, the icon sits beside the label with a 6 px gap, cells are
44 px tall and up to 128 px wide, the padding is 4 px, and the bar sits 8 px
above the bottom edge (about 54 px tall). Below 320 px tall, the bar leaves
the fixed layer and scrolls away at the top of the page. On a touch screen it
hides while a text field has focus. No counts until a screen feeds one. Was: a
header menu button that opened the rail as a 280 px sheet.

**More sheet.** A modal bottom sheet titled "More" in `title`, with a Close
button that is a 44 by 44 px target. Full width at the bottom edge; centred at
most 560 px wide (`Modal`'s width) once the viewport is wider than 592 px. Top
corners 12 px, `l2-neutral-02`, a 1 px hairline on top, and on the sides too
when centred. At most 85 svh tall, with the content scrolling inside. The
header has 16 px at the sides, rows 8 px, and the bottom 16 px or the
safe-area inset, whichever is larger. Rows are sidebar rows at the `touch`
size: at least 44 px tall, `body`, a 16 px icon, a 6 px radius, labels that
wrap, never a tooltip. The current row takes the current tab's treatment. The
remaining destinations come first, in the rail's groups separated by space.
Then a hairline and the account laid flat: the name at 500, organisation and
roles in muted `meta` (both wrap), My passkeys, My sessions and Sign out. The
scrim is `Modal`'s, the text colour at 60%. The sheet covers the bar and opens
and closes without animation.

**Table** (the heat map, later lists). Rows 36 px, 8 px cell padding, `meta`
size, a hairline between rows only, head cells in 500 muted. Heat cells mix
the accent into the surface at 12% per item, capped at 36%, so the text on
them stays AA (the old 70% cap failed at 3.88:1 light and 2.76:1 dark).

**AI-drafted callout.** The one place sand is a fill in running UI:
`l2-brand-02` with a `l3-brand-02` hairline, 6 px radius, 10 by 12 px
padding; the "Drafted by AI" line is a `microlabel` in `content-brand-02`.

**Legal text block.** The brass margin (`l2-brand-02`, `content-brand-02`, the
paragraph sign in Noto Sans Mono at `display` size) is the product's
signature and stays; the block itself is an ordinary card.

**Dates list.** The urgency tone is an 8 px dot; the date is `body` at 500 in
the text colour, days left in `meta`. Was: bold dates in the tone colour.

## Colour: every alias to a Green token

| Alias | Light | Dark | Use |
|---|---|---|---|
| page | `l1-neutral-01` #ffffff | `l1-neutral-01` #0a0b0b | body |
| surface | `l2-neutral-02` #ffffff | `l2-neutral-02` #191a1a | cards, inputs, outline buttons |
| rail | `l2-neutral-01` #f7f8f7 | `l1-neutral-02` #0a0b0b | sidebar |
| subtle | `l1-neutral-02` #f4f5f5 | `l2-neutral-01` #191a1a | banner, code block |
| accent | `l3-neutral-02` #eaebeb | `l3-neutral-02` #313533 | current row, pressed toggle, meter track |
| hover | `state-neutral-05` | `state-neutral-05` | hover overlay on any surface |
| hairline | `border-neutral-02` #dfe1e1 | `border-neutral-03` #282a29 | card borders, dividers |
| control border | `border-neutral-02` | `border-neutral-02` #454a48 | outline button, toggle, empty state |
| input border | `border-neutral-01` #777e7c | `border-neutral-01` #a0a6a4 | inputs, selects |
| text | `content-neutral-01` | `content-neutral-01` | |
| muted text | `content-neutral-02` | `content-neutral-02` | meta, ledes, hints |
| primary | `l3-neutral-03` #0a0b0b | `l3-neutral-03` #d5d7d7 | primary button, toast |
| on primary | `content-neutral-03` | `content-neutral-03` | |
| focus ring | `content-notice-01` | `content-notice-01` | 2 px, 2 px offset |
| brand accent | `l1-brand-01` (brand.css) | `content-brand-02` (brass) | meters, bars, timeline |
| sand | `l2-brand-02` | `l2-brand-02` | AI callout, legal margin |

The page went from `l1-neutral-02` (#f4f5f5) to white in light, so cards are
drawn by their hairline as in shadcn, and the rail sits one step below the
page. The dark hairline moved one step quieter (`border-neutral-03`) because
`-02` drew every card as a box; controls keep `-02` so an outline button
does not vanish on a dark card.

## Contrast (WCAG AA, computed 2026-09-19)

Every text pair the design uses, lowest first. All pass 4.5:1.

| Pair | Light | Dark |
|---|---|---|
| muted text on accent (count or role on the current row) | 4.69 | 5.66 |
| muted text on sand | 5.06 | 7.50 |
| muted text on subtle | 5.13 | 7.93 |
| muted text on rail | 5.26 | 8.96 |
| muted text on page / surface | 5.60 | 8.96 / 7.93 |
| tab label on the tab bar (muted text on surface) | 5.60 | 7.93 |
| organisation and role line in the More sheet (muted text on surface) | 5.60 | 7.93 |
| negative text on surface (danger button, error) | 6.04 | 7.09 |
| brand text on sand (AI label, legal margin) | 6.28 | 10.26 |
| text on accent | 16.50 | 11.69 |
| current tab label (text on accent) | 16.50 | 11.69 |
| text on sand | 17.78 | 15.49 |
| text on search highlight (`l3-brand-02-2`) | 14.04 | 10.72 |
| primary button | 19.71 | 13.64 |
| row label in the More sheet (text on surface) | 19.71 | 16.38 |
| text on heat cell at the 36% cap | 9.52 | 6.48 |
| pills | see `pills-and-labels.md` | |

Non-text: input border 4.15 / 7.05, focus ring 6.39 / 8.19 against surface.

Non-text on the tab bar and the More sheet, 3:1 each: the tab icon on the bar
5.60 / 7.93; the current-tab outline 4.15 / 7.05 on the bar and 3.47 / 5.03 on
its own fill; the current-row outline on the sheet 4.15 / 7.05; the focus ring
on the bar 6.39 / 8.19. The current tab's fill alone measures 1.19 / 1.40
against the bar, which fails WCAG 1.4.11, so the outline carries the state.
`contrast.test.ts` names each pair for the bar or the sheet, so a later token
change fails by name.

## Wordmark

About 68 px wide in the rail (was 104 px), 64 px in the compact header below
1024 px (was 96 px), 20 px open e when the rail is collapsed (was 28 px).

## What is restyled now

`design/prototype/index.html`, `design/screens/tenant-shell.html` and
`design/screens/tenant-today.html`. The other cards in `design/screens/`
keep their old styling and are restyled to these values when their chunk is
built; where a card and this file disagree on a value, this file wins.

# ADR 0020 — Design direction

**Date:** 2026-09-19 · **Status:** accepted by default (playbook 7 step 1; source `design/README.md`; the owner confirms)

## Context

Playbook Section 7 asks for the chosen direction to be recorded with
`design/README.md` as the source. The interactive prototype
(`design/prototype/index.html`) is the contract for flow, wording, labels and
pills; the pill card (`design/system/pills-and-labels.md`) is the contract for
tones; `design/brand/README.md` holds the wordmark and the brand placeholders.
`design/README.md` also lists where the prototype is wrong or silent.

## Decision

The timeline home showing the next dates as the same short list on phone and
desktop, with part of the weekly briefing on it and the full briefing one
tap away. The full calendar on its own roadmap page where a card expands in
place. Restraint in the style of wealth and asset management: a very dark
green, sand surfaces, brass for identity, Hanken Grotesk for text, Noto Sans
Mono for legal references and the wordmark. Phone first: actions on the
right, two buttons share one row, primary on the right. The prototype's
labels and pill system reproduced, not reinterpreted. Where the prototype is
wrong (the tenant officer approving proposals, direct footprint toggles,
"Switch user", labels stored instead of keys, copied hex values, tags that
never render) the fixes in `design/README.md` apply. Screens the prototype
lacks (sign-in and enrolment, tenant admin, platform console, vocabulary
management, the empty, loading, error and denied states) are designed as
cards in the prototype's language before they are built. Deliberately not
done: a dashboard-first home, Green's own layout components, a light-only
theme.

## Consequences

Easier: every screen decision has a source to point at, and the `@e2e`
journeys follow the prototype's path. Harder: each new screen costs a card
first. To remember: the prototype decides look, wording and flow, never
rules; the PRD wins on any rule.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Tokens, type scale, `Pill`, gallery, phonetic logo, shell | Phase 0 |
| 2 | System cards and screen cards per chunk | Chunks 1 to 14 |

## Amendment 2026-09-19: the rail

**Source.** Alex's instruction on 2026-09-19: the green side rail "looks
childish". Replace it with the shadcn/ui Sidebar component structure
(https://ui.shadcn.com/docs/components/base/sidebar) styled in SEB's design
language, taking seb.io's own left rail as the reference. This owner decision
overrides the prototype's rail, so the prototype changed with it
(`design/prototype/index.html`, `design/screens/tenant-shell.html`,
`design/README.md` "Direction").

**What seb.io's rail does, measured in the browser on 2026-09-19.** The
surface is barely distinct from the page (dark theme: the page colour
`rgb(10, 11, 11)` itself). Rows are 40 px, a 20 px icon and a label at 16 px
and normal weight. Groups are separated by space, not headings. "Minimise
menu" is pinned at the bottom. The current item is a fully rounded pill in
the L3 neutral `#313533` (dark).

**Decision.**
- The shadcn Sidebar parts the shell renders, written by hand with shadcn's
  names in `frontend/src/components/ui/sidebar.tsx`: `SidebarProvider`,
  `Sidebar`, `SidebarHeader`, `SidebarContent`, `SidebarGroup`, `SidebarMenu`,
  `SidebarMenuItem`, `SidebarMenuButton` (with `isActive`, `tooltip`,
  `asChild`), `SidebarFooter`, `SidebarTrigger`, `SidebarInset`, and
  `useSidebar()`. There is no shadcn CLI (ADR 0004 keeps our own components
  on Green tokens) and no shadcn colour variables. Parts and props nothing
  renders are left out and added the day a screen needs one (CLAUDE.md,
  "Simplicity first"): side and variant, the off-canvas and non-collapsing
  modes, the rail edge, the separator, the group label, the menu skeleton and
  the menu badge.
- The behaviours kept: collapse to icons with a tooltip per row, an
  off-canvas sheet below 768 px, ctrl/cmd+b, and the open state remembered in
  `localStorage` (not shadcn's cookie: the API owns the cookie jar and the
  refresh cookie is `SameSite=Strict` on a scoped path).
- Colour through `--sidebar-*` aliases in `theme.css` that resolve to Green
  tokens, redefined under `.dark`, so `brand.css` still owns every brand
  value: the surface is `l2-neutral-01` in light (one step above the page) and
  `l1-neutral-02` in dark (flush with the page, as seb.io's). The hairline is
  `border-neutral-02` and the text `content-neutral-01` and `-02`. The accent is
  the solid `l3-neutral-02`, not an rgba state token, so the contrast test can
  pin it; in dark it is seb.io's own `#313533`. All four rail pairs pass WCAG
  AA in both themes (`contrast.test.ts`); the lowest is the role line on the
  current row in light, at 4.69:1.
- **The current row is shadcn's treatment, not seb.io's pill** (Alex's
  correction the same day): full width, `rounded-md` (Green `radius-2xs`,
  6 px), the neutral accent, medium weight, driven by `data-[active=true]`. A
  fully rounded highlight would read as one of the six pill tones, and the
  fully rounded shape stays `Pill`'s alone (playbook 6.7).
- The phonetic wordmark alone on top at about 104 px in `currentColor`, and the
  open e alone (the favicon's glyph, cut from the same path) when collapsed.
  The signed-in person is one quiet row at the bottom: name, then organisation
  and role, and a menu with My passkeys, My sessions and Sign out.
- On phones the dock is replaced by a header menu button that opens the rail
  as a sheet. The dock carried only dock-ranked destinations, so Roadmap,
  Admin and anything the registry adds later had no route on a phone; the
  sheet lists everything the registry unlocks.

**Deliberately not done.** A brand-green rail, count bubbles, fully rounded
nav highlights, group headings, a second navigation model for phones.

**Consequences.** The rail no longer spends the brand colour, so brand green
and sand stay for identity (pills, the legal margin, the favicon). The E2E
sign-out helper (`frontend/tests/e2e/support/passkeys.ts`) has to open the
account menu first, because "Sign out" is now a menu item. A nav count needs its screen to feed one, and the badge part
comes back with it.

## Amendment 2026-09-19: foundations

**Source.** Alex's instruction on 2026-09-19, after the rail amendment: "Still
not happy with this, looks big, clumsy and childish. Take much less
inspiration from seb.io (maybe only keep colour schemes) and more from shadcn
ui components and other modern and professional styles. We can also reduce
the logo size a bit more." This owner decision overrides the prototype's
look, so the prototype changed with it (`design/prototype/index.html`,
`design/screens/tenant-shell.html`, `design/screens/tenant-today.html`,
`design/README.md` "Direction").

**What made it read that way.** 16 to 18 px text everywhere, a 32 px
regular-weight page title and lead headlines up to 30 px; 44 px fully rounded
buttons; cards with a 16 to 20 px radius, 20 to 28 px padding and sand fills;
36 px sidebar rows with 16 px labels; a 104 px wordmark; bold dates in the
urgency colour.

**Decision.** Green's colours at shadcn/ui's proportions, specified in
`design/system/foundations.md`, with shadcn's values read from its
`new-york-v4` registry source on the day:
- Type roles keep their names and take new values: `display` 24 / 32 at 600,
  `title` 16 / 24 at 600, `body` 14 / 20, `meta` 13 / 18, `microlabel` 11 / 16
  uppercase. Three weights (400, 500, 600).
- Controls at 6 px (`radius-2xs`), cards at 8 px (`radius-xs`), dialogs at
  12 px (`radius-s`). Buttons 36 px in primary, outline and ghost; inputs
  36 px with a 3:1 boundary; toggles 32 px; sidebar rows 32 px with 16 px
  icons. Cards are a hairline, no shadow, no sand.
- Colour: a white page in light (cards drawn by their hairline), near black in
  dark with `l2-neutral-02` cards and a quieter `border-neutral-03` hairline.
  Primary stays neutral. Brand green for meters and the timeline, sand only on
  the AI-drafted callout and the legal margin.
- The wordmark about 68 px wide (64 px on phones).
- Pills stay fully rounded (shadcn's current Badge is too, and every control is
  now 6 px, so the shape stays unambiguous) at 20 px, `meta` at 500. In dark,
  the four status tones move to Green's `-03` background step, because dark
  `negative` at `-02` is 4.47:1 and fails AA.

**Deliberately not done.** shadcn's colour variables or CLI (ADR 0004 stands),
a brand-green primary button, shadows on cards, uppercase button labels, a
change to the tones, slot order, labels or the prototype's flow and wording.

**Consequences.** The frontend is ported to `foundations.md`: the type scale in
`tailwind.config.ts`, the radius and component classes, the colour aliases in
`theme.css`, a dark background per status tone in `pill-tones.ts`, and the new
pairs in `contrast.test.ts`. The other screen cards keep their old styling
until their chunk restyles them. Playbook 6.4 lists button labels under
`microlabel`; the design sets them in `body` at 500, which the owner confirms
or corrects.

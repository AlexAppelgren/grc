# Navigation: the rail and the tab bar

This file sets how people move between destinations at every screen width.

**Source.** Alex, 2026-09-19. On phones today, a header menu button opens the rail as a sheet. Alex does not want that on mobile or tablet. He wants a floating tab bar with five items. The fifth item is "More", and it opens the rest of the menu, as many iPhone apps do. The desktop rail from ADR 0020 (amendment "the rail", 2026-09-19) stays on wide screens.

This owner decision replaces two things in the rail amendment: the phone sheet, and "a second navigation model for phones" under "Deliberately not done". It is recorded as a new ADR 0020 amendment (section 17). Until `design/README.md`, `design/screens/tenant-shell.html` and `design/prototype/index.html` are updated in the same slice, this file wins wherever they disagree with it.

Every rule below gives its reason and its source. Sources marked "own value" are our choices, not external rules.

**Dark theme.** The app follows the system's light or dark setting. There is no switch in the app: next-themes (`providers.tsx`, the `class` attribute, default theme `system`) puts `light` or `dark` on `<html>`, and the dark tokens live under `.dark`. `contrast.test.ts` pins the dark values below from the stylesheets, and the NFR-S9 journey measures them in a browser under a dark system theme. No screenshot is taken of the bar or the sheet in dark.

## The rule in one line

- **Below 1024 px:** a floating bar at the bottom holds up to four dock destinations from the registry, then More. More opens a bottom sheet with every other destination and the account.
- **1024 px and wider:** the rail, unchanged.

---

## 1. Which width gets what

| Viewport width | Navigation | Top of the page |
|---|---|---|
| Below 1024 px ("compact") | Tab bar, plus the More sheet | The wordmark line (section 12) |
| 1024 px and wider | The rail: collapses to icons, ctrl/cmd+b, open state remembered | Nothing |

Where common devices land (CSS px):

| Device | Portrait | Landscape |
|---|---|---|
| Any phone | tab bar | tab bar in its compact-height layout (section 4a). The widest phone in landscape is about 956 |
| iPad mini (744 / 1133) | tab bar | rail |
| iPad (A16), iPad Air 11 (820 / 1180) | tab bar | rail |
| iPad Pro 11 (834 / 1210) | tab bar | rail |
| iPad Air 13, iPad Pro 13 (1024 / 1366, 1032 / 1376) | rail | rail |
| Desktop window narrower than 1024 | tab bar | |

**Why 1024.**
- Alex asked for the tab bar on mobile and tablet. The other candidates fall short:
  - 767 px (today) gives the bar to no tablet.
  - 820 px (the prototype) misses the iPad Pro 11 in portrait (834).
  - 840 px (Material's medium/expanded limit) is not a step in either of our systems.
- 1024 covers every phone in both orientations and every iPad in portrait below 13 inches.
- 1024 is already a step in both of our systems: Green's `viewport-m` token and Tailwind's `lg`. We add no custom breakpoint for switching navigation.
- The 13-inch iPads in portrait are as wide as a laptop. The 240 px rail leaves them 784 px of content. See open question 3.

**Known departures.** Alex's instruction decides these, and we accept them knowingly:
- **Material.** Its window size classes are: compact below 600 dp, medium 600 to 839, expanded from 840. For height, compact is below 480. Android's default adaptive navigation (`NavigationSuiteScaffold`) shows a bar when the width or the height is compact, and a rail otherwise.
  - Here, windows 600 to 1023 px wide with a regular height get the bar, by Alex's decision. That covers every iPad below 13 inches in portrait, and narrow desktop windows.
  - Phones in landscape have a compact height, so they match Material.
- **Apple on iPad.** Apple puts the tab bar at the top, or uses a sidebar. It does not use a floating bottom bar.
- **Apple's tab memory.** Apple keeps each tab's place when a person switches tabs ("preserving the current navigation state within each section"). Here every tab links to its section's root, as the rail does (section 5, open question 4).
- **The same things at every width.** Apple asks for this, and it holds here: every destination is reachable at every width, either through the rail or through the tabs plus More.

**How it is built.**
- One JS constant, `COMPACT_QUERY = '(width < 64rem)'`, in `components/ui/sidebar.tsx`. It replaces `MOBILE_QUERY = '(max-width: 767px)'`. A unit test pins it.
- The CSS switches navigation only with Tailwind's `lg:` and `max-lg:` variants, which compile to the same query. No shell component switches navigation with `md:`.
- CSS decides what is visible: the rail is `hidden lg:block` and the bar is `lg:hidden`.
  - Both render on the server, so the first paint is right before hydration and nothing flashes.
  - JS reads the query only for three things: whether ctrl/cmd+b does anything (section 11), closing open overlays when the width crosses 1024 (section 11), and hiding tooltips.
- These stay at 768 px, because they concern reading width, not navigation:
  - the phone `h1` size (20/28)
  - the page padding step, which is now safe-area aware (section 7)

Sources: Android "Use window size classes" and "Build adaptive navigation". Material 3 navigation bar guidelines. Tailwind responsive design (`lg` = 64rem). Green `viewport-m` = 1024 (Green MCP `get_tokens viewport`). iPad widths from screensizechecker.com, a secondary source. Apple HIG tab bars, sidebars and layout. `frontend/src/components/ui/sidebar.tsx`.

---

## 2. What sits in the bar

1. **The tabs are the registry's dock destinations.** `TabBar` calls the existing `dockDestinations(surface, permissions)` directly: the visible destinations that have a `dockRank`, lowest rank first. There is no new helper.
   - The field keeps its playbook name, `dockRank`. Playbook 6.2 already derives "Dock, sidebar, More menu" from the registry.
   - Why at most four: iOS shows at most four items plus More (UIKit `UITabBarController`). Material allows three to five destinations.
2. **More is always the last item and is always there.** The account lives in it, so it is never empty.
3. **Nothing checks a role name.** A tab appears only if the person's permission list unlocks it (`unlocks()`). The server's 403 still enforces access. Source: playbook 6.2.
4. **Ranked destinations the person cannot open are skipped. Unranked ones are never promoted.**
   - If a ranked destination is not unlocked, it is skipped and the ones after it move up.
   - An empty slot stays empty. An unranked destination (Roadmap, Admin) is never promoted into the bar.
   - Why:
     - The rank is a product decision about what earns a tab.
     - Apple advises few tabs, with More kept for what is used rarely.
     - Promoting would change a person's bar when an unrelated permission changes, and would put Admin in a tab.
5. **At most four ranked destinations per surface.** A registry test enforces it. The 4 lives in that test, with the iOS reason, so a ranked destination can never drop out of the bar unnoticed.
6. **The bar holds 2 to 5 items, in equal cells.** Positions are fixed, and swiping never switches tabs. Source: Material navigation bar.

What today's registry produces:

| Who | Tabs | In More |
|---|---|---|
| Every system role. All hold `library.read`, `watch.read`, `roadmap.read` and `search.use` (`backend/apps/shared/permissions.py`) | Today, Watch, Inventory, Ask | Roadmap. Admin, for a role holding any tenant admin permission. The account |
| A custom role holding none of those four | Today | The account |
| Console, holding every platform permission | Queue, Vocabularies, Sources | The account |

**Tab labels.**
- A new optional registry field, `shortLabelKey`, holds a tab's label. Without it, the tab uses `labelKey`.
- No tab needs one today. Search needed one while its label was "Search and ask"; since D-103 search lives in the inventory and the destination is "Ask" ("Fråga" in Swedish), one word in the rail, the More sheet and the bar alike.
- The rail and the More sheet keep the full labels.
- Why: Apple asks for single-word labels. Material asks for one or two words, and says never to truncate or shrink them.

Sources: Apple HIG tab bars. UIKit `UITabBarController`. Material 3 navigation bar guidelines. `frontend/src/shared/navigation/registry.ts`. The prototype's tab bar (`design/screens/tenant-watch.html`).

---

## 3. More

**What it is.** A button that opens a modal bottom sheet titled "More".

**What the sheet contains, in order:**
1. **A header.**
   - The title is `nav.more` ("More" / "Mer") in the `title` type role.
   - A Close button: the `close` icon, accessible name `shell.close` ("Close" / "Stäng"), and a 44 × 44 px target.
   - Why the Close button: touch screen-reader users cannot reliably press Escape, and the scrim is hidden from them.
2. **The remaining destinations.**
   - A new helper, `moreDestinations(surface, permissions)`, returns `visibleDestinations` minus `dockDestinations`.
   - They use the rail's grouping (`groupDestinations`: primary, then secondary, then admin). Groups are separated by space, with no headings.
   - Admin's child pages are not listed. They live on the Admin index page, as they do from the rail.
3. **A hairline, then the account group.**
   - The group is `role="group"`, with its `aria-label` from `shell.account` ("Account" / "Konto").
   - It carries **no** `data-who-panel`. That marker stays only on the rail's account row. The rail is still mounted at compact widths, so a second marker would give Playwright two matches and break strict mode.
   - It starts with two static lines:
     - the person's name, in `body` at 500
     - organisation · roles, in `meta`, muted, built with `secondLine()`
   - Both lines wrap and are never truncated. At compact widths, this sheet is the only place they are shown.
   - Then the links My passkeys and My sessions (`childDestinations(ACCOUNT_PARENT)`).
   - Then Sign out, which is a button:
     - While signing out it reads "Signing out…" and is disabled.
     - Afterwards it calls `router.replace('/sign-in')`, as the rail's menu does.
   - This is the rail's account menu laid flat. Inside a sheet, a second menu layer would add a tap for nothing.

**How it behaves.**
- **Closing by choice.**
  - Choosing a link closes the sheet (`onClick`), even when the link points to the current page.
  - Close, Escape or a tap on the scrim closes it, and Radix returns focus to More.
- **Any route change closes it.** This covers the Android back gesture, Safari's edge swipe, and any other navigation. Next keeps layout state across history navigation, so without this rule the page underneath would change while the sheet stayed open.
- **Crossing 1024 px closes it** (a rotated iPad or a resized window). The More button is hidden at that point, so focus goes to `#main` instead (section 11).
- **How both closes are built.**
  - `open` is controlled state in `MoreSheet`.
  - It is reset during render whenever `usePathname()` or `isCompact` differs from the value seen on the previous render. This is React's pattern for adjusting state when a value changes.
  - It must not be reset in an effect: `react-hooks/set-state-in-effect` is an error in the repo's lint set (eslint-plugin-react-hooks 7.1.1, recommended).
- **The current page's row** gets the current treatment (section 5) and `aria-current="page"`.
- **The sheet covers the bar.** Apple allows a modal view to cover the tab bar, and Material allows a bottom sheet to cover the bar for a while.
- **Not built:**
  - swipe to dismiss (open question 2)
  - animation (section 10)
  - back closing only the sheet (section 14)

**The component.**
- shadcn's `Sheet` with `side="bottom"`, written by hand as `components/ui/sheet.tsx` with shadcn's part names. It is built on the `@radix-ui/react-dialog` 1.1.23 we already ship.
- Only the bottom side is built.
- The left sheet in `sidebar.tsx` is deleted, because the tab bar replaces its only user.
- This follows ADR 0004 and ADR 0020 (our own components on Green tokens, and parts nothing renders are left out). It adds no dependency.

| Option | Verdict | Why |
|---|---|---|
| **Sheet, `side="bottom"`, on Radix Dialog** | **Chosen** | It is shadcn's own Sheet, which extends Dialog. It adds 0 bytes, because Dialog already ships. Checked in `node_modules`, Radix gives `role="dialog"`, `aria-modal`, a focus trap, the rest of the page hidden from assistive technology, scroll lock, and Escape returning focus to the trigger |
| shadcn Drawer, Radix style (vaul) | Rejected | vaul's README says the repo is unmaintained. It adds about 22 KB minified (6 KB gzip) beyond Dialog |
| shadcn Drawer, Base UI style | Rejected for now | It would bring a second headless library in beside Radix. This is open question 2 |
| DropdownMenu | Rejected | `role="menu"` is a command widget, not site navigation (WAI-ARIA APG, Roselli). A small popover is also a poor fit on a phone for a list plus the account section |
| Community tab-bar components (whiskeyjack, shadcn.io, shadcnui-blocks `tabs-08`, the docks) | Rejected | shadcn has no bottom navigation component (issue #8847 is still open). The candidates use their own tokens, lack `aria-current`, use `role="tablist"` for routes, or magnify on hover, which does nothing on touch |

**Geometry of the sheet.**

| Part | Value | Why |
|---|---|---|
| Position | Fixed to the bottom edge at full width. When the viewport is wider than 592 px, it is centred at a maximum width of 560 px | 560 px is `Modal`'s width. A sheet the full width of a tablet would be a long reach |
| Radius | Top corners 12 px (`rounded-t-overlay`) | Foundations gives `radius-s` to dialogs and the sheet |
| Surface | `bg-surface`, with a 1 px `border-line` on the top edge, and on the sides as well when centred | The same surface as the bar, so they read as one layer family |
| Height | At most 85 svh, with the content scrolling inside | Tall enough for the long Admin and account list on a short landscape phone |
| Padding | Header: 16 px on the sides. Rows: 8 px on the sides (the rail's group padding). Bottom: `max(16px, env(safe-area-inset-bottom))` | The last row stays clear of the home indicator (section 7) |
| Rows | `SidebarMenuButton` with a new size, `touch`: at least 44 px tall (`min-h-11 py-2`), `body` text, a 16 px icon, 6 px radius. The label wraps: the `touch` size drops `overflow-hidden` and the label's `truncate`. The current row takes the section 5 treatment: `sidebar-accent`, 500 weight and the inset `line-strong` outline. No tooltip, ever | Rows look like the rail's, with a touch-sized target (section 6). Text zoom never cuts a label |
| Scrim and stacking | `Modal`'s scrim, `bg-fg/60` at `z-40`. The sheet sits at `z-50` | The same as `Modal.tsx` |

Sources: Apple HIG tab bars (a modal covering the bar, avoiding overflow tabs). Material navigation bar. WAI-ARIA APG modal dialog pattern. Radix Dialog docs. shadcn Sheet, Drawer and components index. vaul README. shadcn issue #8847. Roselli on ARIA menu roles. `frontend/src/components/ui/Modal.tsx`. The original prototype's More modal (commit f8d31b2).

---

## 4. The bar: geometry and surface

| Property | Value | Token | Why | Source |
|---|---|---|---|---|
| Position | `position: fixed`. `bottom: var(--tabbar-bottom)`, which is `max(16px, env(safe-area-inset-bottom))`. `left` and `right`: `max(16px, env(safe-area-inset-left))` and `-right`, dropping to `max(8px, …)` below 400 px (25rem). `margin-inline: auto` | `space-m` | The bar floats with a margin on three sides. From 400 px, the 16 px side gap equals the phone page gutter, so the bar lines up with the content. Below 400 px, the labels need the width (section 5). Safe-area insets are not margins, so they combine with `max()` | Apple HIG tab bars (the bar floats above content). WWDC25 session 356. WebKit's iPhone X notes. The 400 px step is our own value |
| Width | `width: fit-content` (`w-fit`). The list is a grid with `grid-auto-flow: column` and `grid-auto-columns: minmax(0, 6rem)` | own value | On a tablet the bar hugs 96 px cells and sits centred. On a phone the insets decide the width, and the cells share it equally. No JS and no inline style. 96 px fits a 12-character `meta` label on one line | Own value |
| Height | 64 px: 6 px padding, a 52 px cell, 6 px padding, with the border inside. It grows when a label wraps and never clips | `space-5xl` | About the height of iOS's floating bar (third-party measurement: about 62 pt) | learnui.design, Apple forum thread 796299 (third party) |
| Radius | 12 px, `rounded-overlay` | `radius-s` | Foundations gives 12 px to floating layers (dialogs, the sheet), and the bar is one. The fully rounded shape stays the pill's (open question 1). With 6 px padding, the 6 px highlight on the current tab sits concentric with the bar (12 − 6 = 6) | `foundations.md` "Radius", `pills-and-labels.md`, WWDC25 session 356 |
| Surface | `bg-surface`, solid | `l2-neutral-02` (#ffffff light, #191a1a dark) | Solid, so `contrast.test.ts` can pin every pair (it composites solid colours, not rgba). Green has no glass material | `theme.css` comment on the sidebar accent. Apple HIG materials, for what we leave out |
| Border | 1 px `border-line` | `border-neutral-02` light, `-03` dark | Draws the bar's edge on a white page | `foundations.md` "hairline" |
| Elevation | `shadow-float`, a new theme alias combining Green `shadow-l-01` and `shadow-l-02` | `--gds-sys-shadow-l-01`, `-l-02` | This is the only layer that sits over scrolling content. Cards stay flat ("no shadow"). Green shadows come in pairs, `-01` and `-02` | Green MCP `get_tokens shadow`. `foundations.md` "Card" |
| Blur | None | | Solid is simpler, can be pinned, and needs no Reduce Transparency fallback | Apple HIG materials |
| Stacking | `z-30` | | Below the scrim (40) and dialogs (50), so a modal covers it | Apple HIG tab bars |
| Print | `print:hidden` | | Navigation has no place on paper | Own value |

**Cells.**
- The grid has no gap.
- Each cell is the whole hit area, so there is no dead strip between tabs.

### 4a. Short and landscape viewports

Both rules apply only below 1024 px. They are CSS only, in `globals.css`.

| Viewport | Layout | Why | Source |
|---|---|---|---|
| Height below 30rem (480 px, Material's compact height): phones in landscape, short windows | - The icon sits beside the label, with a 6 px gap.<br>- The cell is 44 px tall and the bar padding 4 px, so the bar is about 54 px.<br>- Cells grow up to 8rem.<br>- `--tabbar-bottom: max(8px, env(safe-area-inset-bottom))` | Apple puts icons above labels in compact views, and beside them otherwise; iPhone landscape has its own compact inline layout. A 64 px stacked bar floated about 21 px up would take about a quarter of a 390 px tall landscape phone | Apple HIG tab bars. Android window size classes (compact height) |
| Height below 20rem (320 px): for example 400% zoom on a 1280 px laptop, about 320 × 155–230 CSS px | - The bar leaves the fixed layer: `position: static`, no shadow, `margin: 8px auto 0`, and `--tabbar-top: 0px`.<br>- It is already before `main` in the DOM, and the shell wrapper is `max-lg:flex-col`. So it renders as a row at the top of the page and scrolls away | A fixed 54 to 80 px bar would take a third to a half of the height. WCAG's reflow guidance advises static positioning for sticky parts at small viewport sizes | WCAG 2.2 Understanding 1.4.10 |

---

## 5. A tab

**Anatomy.** A 20 px icon, a 4 px gap, then the label, centred vertically in a 52 px cell with no side padding. In compact height the icon sits beside the label instead (section 4a).
- **Icon.** `NavIcon` gets a new `size` prop:
  - `'row'` (16 px, the default) for the rail and the sheet.
  - `'tab'` (20 px) for the bar. 20 px is on the 4 px grid. The prototype's tab icons are 22 px.
  - Paths and the 1.75 stroke stay the rail's.
- **Label.** The `meta` role (13/18). It is the smallest role without upper case, and there is no seventh role (playbook 6.4).
  - It may use one or two lines, and wraps at spaces.
  - `hyphens: auto` comes first, then `overflow-wrap: anywhere`. A word longer than its cell therefore breaks at a hyphenation point where the browser has a dictionary, and anywhere otherwise. It is never clipped.
  - The `<nav>` carries `lang` from `useLocale()`. `<html lang>` is the build default (`NEXT_PUBLIC_DEFAULT_LOCALE`), while signed-in screens render the person's own language (SessionGate).
  - It is never truncated and never set smaller than `meta`. Source: Material navigation bar, which says to keep the labels and never truncate or shrink them, and that the full label must show at twice the text size.
  - **Measured widths**, Hanken Grotesk at 13 px and weight 500, from the repo's woff2:

    | Label | Width |
    |---|---|
    | Inventory | 55.3 px |
    | Inventarie | 58.2 px |
    | Bevakning | 59.7 px |
    | Vocabularies | 75.8 px |

  - **Space per label** with five items:

    | Viewport width | Label box |
    |---|---|
    | 320 px | 58 px |
    | 360 px | 66 px |
    | 375 px | 69 px |

  - So English fits on one line from 320 px, and Swedish from 360 px. At 320 px, "Bevakning" breaks at a hyphen. In the console at 320 px (four items, 72.5 px each), "Vocabularies" does too.
- **Orientation.** The icon sits above the label, which is Apple's compact layout, except in compact height (section 4a). Tablets keep the stacked layout, so there is one layout per height class.
- **More.** A `<button type="button">` with the `more` icon (three dots, the prototype's) and the label `nav.more`.

**States.**

| State | Background and indicator | Label and icon | Weight | Markup |
|---|---|---|---|---|
| Rest | None | `muted` | 400 | |
| Hover (pointer devices) | `hover:hover-fill` (the `state-neutral-05` overlay) | `muted` | 400 | |
| Current | `sidebar-accent` (`l3-neutral-02`) over the whole cell, 6 px `rounded-control`, **plus a 1 px `line-strong` outline inset by 1 px** | `sidebar-accent-foreground` | 500 | `aria-current="page"`, `data-active="true"` |
| More, while the current page lives in More | Same as current | Same as current | 500 | `data-active="true"`, `aria-current="true"` (section 11) |
| Keyboard focus | As the state underneath. While the cell has keyboard focus, the 2 px `focus` ring (2 px offset) replaces the inset outline (`not-focus-visible:`) | | | The bar's 6 px padding keeps the ring inside the bar |

**How the current tab is marked.**
- **The outline is the indicator that reaches 3:1.**
  - `line-strong` (`border-neutral-01`) measures 4.15 / 7.05 against the bar and 3.47 / 5.03 against the fill.
  - The fill alone measures 1.19 / 1.40 against the bar. That fails WCAG 1.4.11, because a state fill must contrast with its adjacent colours.
  - The pairing is the pressed Toggle's (`foundations.md` "Toggle": `l3-neutral-02` with `border-neutral-01`).
- **Why an outline, not a border.**
  - It takes no layout space.
  - Forced-colours mode keeps outlines, recoloured by the system, while it drops background fills. The current tab therefore stays distinct there, with no extra rules.
- **Fill, colour, weight and `aria-current` add to it.** Colour is never the only cue (WCAG 1.4.1).
- **The rail's current row** keeps its approved treatment in this slice (open question 5).

**Tapping a tab.**
- Every tab is a plain link to its section's root (`href`), as in the rail.
- Tapping the tab that is already current, on a nested route (`/watch/…`), returns to its root. That is Apple's rule for the selected tab.
- Apple also keeps every other tab's place when switching. We do not: section 1, open question 4.
- No scroll-to-top script. Source: UIKit `UITabBarController`.

**Counts.** Not built. The first screen that feeds a count designs the tab and sheet form, as ADR 0020 says.

Sources: Apple HIG tab bars (labels, the selected tint, compact and regular layouts). Material navigation bar (one active item, the indicator, labels, 3:1 icon contrast). UIKit `UITabBarController`. WCAG 2.2 Understanding 1.4.11. MDN `forced-colors`. `foundations.md`. `pills-and-labels.md`. ADR 0020, "the rail".

---

## 6. Touch targets

| Target | Size | Meets |
|---|---|---|
| Tab or More cell | 52 px tall, or 44 px in compact height. About 58 px wide at 320 px with 5 items, 69 px at 375 px, and at most 96 px (128 px in compact height) | WCAG 2.5.8 AA (24 px). WCAG 2.5.5 AAA and Apple (44). Material (48), except in compact height, where Apple's shorter landscape bar is followed |
| Sheet row | At least 44 px tall, full width | WCAG 2.5.5, Apple |
| Sheet Close button | 44 × 44 px | WCAG 2.5.5, Apple |

Sources: WCAG 2.2 Understanding 2.5.8 and 2.5.5. Apple HIG accessibility. Material "structure".

---

## 7. Safe areas and the viewport

- **Viewport export.** The root layout exports `export const viewport: Viewport = { width: 'device-width', initialScale: 1, viewportFit: 'cover' }`.
  - Without `viewport-fit=cover`, `env(safe-area-inset-*)` is 0 on iPhone and the bar cannot clear the home indicator.
  - Width and scale are written out, so the result does not depend on how Next merges its defaults.
  - Never set `maximumScale` or `userScalable: false`. Zoom stays available (WCAG 1.4.4).
- **Page gutter.** Every side is `max(step, inset)`, at every width:
  - Base: `pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))]`.
  - From 768 px: `md:pl-[max(2rem,env(safe-area-inset-left))] md:pr-[max(2rem,env(safe-area-inset-right))]`.
  - Why the 768 px step matters: every iPhone with a notch or Dynamic Island is 812 to 956 px wide in landscape, past that step, with side insets of 44 to 62 px. A bare `md:px-8` would put the page under the sensor housing.
  - Top: `max(12px, env(safe-area-inset-top))` below 768 px, and the existing `md:pt-6` above.
- **Every fixed or absolute element at a viewport edge uses `max(<gap>, env(safe-area-inset-*))`.** Today that means:
  - the bar (section 4)
  - the sheet (section 3)
  - the skip link: `focus:top-[max(8px,env(safe-area-inset-top))] focus:left-[max(8px,env(safe-area-inset-left))]`
  - the rail footer's bottom padding: `pb-[max(1rem,env(safe-area-inset-bottom))]`, for the iPad home indicator
- **Needs a device test.** iOS 26 Safari reportedly tints its toolbar from fixed elements near the viewport edge. The community observed this; Apple has not documented it (section 18).

Sources: MDN `<meta name="viewport">` and `env()`. WebKit, "Designing websites for iPhone X". Next.js `generateViewport` and the `Viewport` type (`viewportFit`). Ben Frain on iOS 26 Safari tinting. `frontend/src/components/shell/AppShell.tsx`.

---

## 8. The on-screen keyboard

**Rule.** Below 1024 px, on a coarse pointer, the bar is `visibility: hidden` while a text-entry field has focus. This is CSS only, in `globals.css`:

```css
@media (width < 64rem) and (pointer: coarse) {
  body:has(:is(input:not([type='checkbox'], [type='radio'], [type='button'], [type='submit'], [type='reset'], [type='range'], [type='color'], [type='file'], [type='image']), textarea, [contenteditable]:not([contenteditable='false'])):focus) [data-slot='tab-bar'] {
    visibility: hidden;
  }
}
```

**Why hide it.**
- By default, Chrome on Android (108 and later) resizes only the visual viewport when the keyboard opens. Fixed elements stay where they are, and the keyboard can cover them. iOS Safari behaves similarly.
- Either way, the bar can end up on top of the field being typed in, which fails WCAG 2.4.11.
- Material explicitly allows the keyboard to cover the bar for a while.

**Why `visibility`, not `display: none`.**
- `visibility: hidden` still removes the bar from assistive technology and the tab order, but the bar keeps its box.
- With `display: none`, the ResizeObserver would fire and report 0 (the Resize Observer spec says an observation fires when `display` becomes `none`). The clearance would then collapse.
- When focus then moves to the next control, the browser scrolls that control into view before the observer restores the height. The control would land behind the bar as it reappears (WCAG 2.4.11).
- With `visibility`, the clearance never changes. The page does not jump, and the next focused control is scrolled clear of the bar.

**Why only on a coarse pointer.**
- An on-screen keyboard exists only on touch devices.
- Desktop windows and zoomed desktops below 1024 CSS px keep their navigation. That includes low-vision users at 150 to 200% zoom.
- Otherwise, autofocused inline fields (`VocabularyScreen.tsx`) would remove the "Main" landmark without the person choosing to type.

**Not used, and why.**
- `VisualViewport` scripting: iOS 26.0 had an `offsetTop` bug that misplaced fixed footers.
- The VirtualKeyboard API: Chromium only.
- `interactive-widget`: Safari has not shipped it. We keep the default, `resizes-visual`.

`:has()` is supported from Safari 15.4, Chrome 105 and Firefox 121. That is below Tailwind 4's own browser floor.

**Trade-off, accepted.** On an iPad with a hardware keyboard, the pointer usually stays coarse, so the bar also disappears while typing. It comes back on blur.

Sources: Chrome for Developers, "viewport resize behavior". MDN VisualViewport and VirtualKeyboard API. W3C Resize Observer. caniuse (`css-has`, `mdn-api_virtualkeyboard`). Apple Developer Forums threads 800125 and 800154. bram.us on `interactive-widget`. Material navigation bar. WCAG 2.2 Understanding 2.4.11.

---

## 9. Clearance, so the bar never hides content or focus

| Name | Value | Set where |
|---|---|---|
| `--tabbar-height` | 64px by default. `TabBar` sets it on `<html>` from a `ResizeObserver` on itself, ignores any entry whose `borderBoxSize[0].blockSize` is 0 (for example `lg:hidden` from 1024 px), and removes it on unmount | `globals.css` (the default), `TabBar.tsx` |
| `--tabbar-bottom` | `max(16px, env(safe-area-inset-bottom))`. When the height is below 30rem: `max(8px, env(safe-area-inset-bottom))` | `globals.css` |
| `--tabbar-top` | Below 1024 px: `calc(var(--tabbar-height) + var(--tabbar-bottom))`. From 1024 px, and when the height is below 20rem: `0px` | `globals.css` |
| Page bottom padding | The shell wrapper's `pb-16` becomes `max-lg:pb-[calc(var(--tabbar-top)+16px)] lg:pb-16` | `AppShell.tsx` |
| `html { scroll-padding-bottom }` | `calc(var(--tabbar-top) + 16px)` | `globals.css` |
| Anything else fixed to the bottom below 1024 px (a toast, a sticky action row) | `bottom: calc(var(--tabbar-top) + 8px)` | The first such component. None exists today |

**Why measure the height.**
- A wrapped label, or text-only zoom (which scales text but not px lengths), makes the bar taller than 64 px.
- A fixed clearance would then let the last line of a page, or a focused control, sit behind the bar.
- That fails WCAG 2.4.11. Technique C43 (scroll padding) is the sufficient technique.

Sources: WCAG 2.2 Understanding 2.4.11 (and failure F110). Technique C43. Material navigation bar accessibility (the bar grows with text size). W3C Resize Observer.

---

## 10. Motion

- **The bar never moves.**
  - No hiding on scroll and no minimising.
  - Apple says to keep the bar visible, and its iOS minimise behaviour is opt-in.
  - Material says not to hide the bar on scroll while a screen reader is active, and a web page cannot detect that.
- **The sheet opens and closes without animation, like `Modal`.**
  - Alex did not ask for motion.
  - One animated overlay beside an unanimated `Modal` would be inconsistent.
  - Motion for `Modal` and the sheet together is a follow-up in `docs/TODO_FOR_alex.md` (open question 6).
- **Colour transitions on the tabs stay** (`transition-colors`). They move nothing.
- **No new packages.** No `tw-animate-css` and no motion library.

Sources: Apple HIG tab bars. WWDC25 session 284 and SwiftUI `tabBarMinimizeBehavior`. Material navigation bar. `frontend/src/components/ui/Modal.tsx`.

---

## 11. Semantics, focus and screen readers

```tsx
<nav aria-label={t('nav.main')} lang={locale} data-slot="tab-bar">
  <ul>
    <li><Link href={d.href} aria-current={current ? 'page' : undefined} data-active={current}>…icon, label…</Link></li>
    {/* one li per tab */}
    <li><SheetTrigger asChild><button type="button" data-active={inMore} aria-current={inMore ? 'true' : undefined}>…icon, {t('nav.more')}…</button></SheetTrigger></li>
  </ul>
</nav>
```

**Landmark.**
- A `<nav>` labelled "Main".
- The rail's `<nav>` is also "Main". At compact widths the rail is `display: none`, and at wide widths the bar is. So exactly one "Main" landmark is exposed at any width.

**Links, not tabs and not a menu.**
- No `role="tablist"` or `tab`, and no `role="menu"`. Page navigation needs no ARIA beyond `aria-current`.
- The list gives screen readers the item count ("list, 5 items").

**`aria-current`.**
- `aria-current="page"` sits on exactly one element across the bar and the sheet: the link to the current page.
- When the current page lives in More, the More button carries `aria-current="true"` ("current item") as well as the visual current state. A screen-reader user therefore hears in the bar that they are inside More, which a sighted user sees (WCAG 1.3.1). The link inside the sheet carries `"page"`.
- While the sheet is open, Radix hides the bar from assistive technology, so the two are never exposed together.
- The prototype put `"page"` on More. We use `"true"`, because the button is not a link to the page.
- `isInMore(surface, permissions, pathname)` decides this. It covers the More destinations and the account children.

**The More button.** Radix's trigger gives it `aria-haspopup="dialog"`, `aria-expanded` and `aria-controls`.

**Order.**
- The DOM order is: skip link, rail, bar, `main`.
- On desktop, the rail sits before the page content in the DOM; below 1024 px, the bar takes that place. Navigation therefore comes before content at every width (WCAG 3.2.3), and the skip link skips it the same way.
- The bar appears at the bottom visually. WCAG 2.4.3 allows that, because the order keeps its meaning.

**Keyboard.**
- Tab moves through the items. Enter follows a link. Enter or Space opens More.
- No arrow-key roving, and no focus trap in the bar.
- ctrl/cmd+b toggles the rail from 1024 px only. Below that, the shortcut is left to the browser, with no `preventDefault`, because there is nothing to toggle.

**The sheet.**
- Radix Dialog: `role="dialog"` and `aria-modal`, labelled by the visible title.
- Focus is trapped inside. The rest of the page is hidden from assistive technology, and page scroll is locked.
- Escape closes it and returns focus to More.
- First focus goes to Radix's default, the first focusable element (Close).
- Pass `aria-describedby={undefined}`: the visible title says everything, so there is no description.

**Overlays when the width crosses 1024 px** (a rotated iPad mini, Air 11 or Pro 11, or a resized window):
- **The More sheet** closes (section 3). Its `onCloseAutoFocus` checks `isCompact`. When the width is no longer compact, it calls `event.preventDefault()` and focuses `#main` (`tabIndex={-1}`), because the More button is now hidden.
- **The rail's account menu** needs the same care.
  - It is a Radix `DropdownMenu`, modal by default, rendered inside the rail without a portal.
  - If the rail became `display: none` while the menu was open, the menu would vanish. Its `aria-hidden` would stay on the bar and `main`, and `pointer-events: none` would stay on `body`.
  - The fix: the menu becomes controlled, and is reset closed during render when `isCompact` changes (the same pattern as section 3).
  - Its `onCloseAutoFocus` then focuses `#main`.

**Copy.** Every label comes from the catalogs (`nav.*`, `shell.*`). There are no string literals in JSX.

Sources: WAI-ARIA APG navigation landmark example and modal dialog pattern. MDN `aria-current`. Roselli, "Don't use ARIA menu roles for site nav". WCAG 2.2 Understanding 1.3.1, 2.4.3 and 3.2.3. Radix Dialog and DropdownMenu (`node_modules`).

---

## 12. The compact header

- **The menu button goes.** There is nothing left for it to open.
- **The wordmark stays.** It is a line at the top of the page that is not sticky:
  - the 64 px mark in the text colour
  - a link to Today
  - `lg:hidden`
  - it scrolls away with the page, as it does today
- **Why keep it.**
  - The tab bar carries no brand.
  - The product is sold to other banks under its own wordmark (DECISIONS D-05).
  - The shell smoke test finds the wordmark on every signed-in screen.
  - It costs 48 px once and is never fixed.
- **In code.** `MobileHeader.tsx` keeps only the `Logo` link and puts nothing on the right.

Sources: `foundations.md` "Wordmark". `frontend/tests/e2e/shell.journey.spec.ts`.

---

## 13. The console

- The console uses the same `TabBar` and More sheet, with `surface="console"`.
  - The tabs are Queue, Vocabularies and Sources (ranks 1 to 3).
  - More holds only the account, until the registry gains a console destination without a rank.
- The prototype's console bar also shows Reports. It joins the bar as the fourth tab when the registry lists it with a rank.
- The console has no route group or layout yet. Unit tests cover the console bar now. Its E2E arrives with the console chunk.

Source: `design/screens/console-shell.html` ("the dock is the first four plus More, as on the tenant side"). The registry.

---

## 14. Deliberately not done

- A capsule-shaped bar, or a fully rounded current tab (open question 1).
- Glass, backdrop blur, or a blurred scroll edge.
- Hiding or minimising the bar on scroll.
- Swiping the sheet down to close it (open question 2).
- Back closing only the sheet.
  - A route change does close the sheet (section 3), but going back also leaves the page.
  - No history entry is pushed for the sheet.
- Per-tab memory. Apple keeps each tab's place; here, every tab links to its root, as the rail does (open question 4).
- Animating the sheet (section 10, open question 6).
- Apple's Edit screen for rearranging tabs.
- Any count or badge before a screen feeds one.
- A top tab bar on iPad.
- The prototype's brand-green, edge-to-edge bar. ADR 0020 took brand green out of navigation, and Alex asked for a floating bar.
- Dark-theme screenshots of the bar and the sheet. The app follows the system theme, so they could be taken; the NFR-S9 journey measures the dark pairs instead (`docs/TODO_FOR_alex.md`).
- vaul, Base UI, `tw-animate-css`, a motion library, or any registry component.

---

## 15. What the build changes

| File | Change |
|---|---|
| `frontend/src/app/layout.tsx` | Add the `viewport` export (section 7) |
| `frontend/src/components/ui/sidebar.tsx` | - Replace `MOBILE_QUERY` with `COMPACT_QUERY = '(width < 64rem)'`.<br>- The rail always renders as `hidden lg:block`.<br>- Delete the phone `Dialog` branch, `openMobile`, `setOpenMobile`, `SidebarTrigger`, `WIDTH_MOBILE` and `--sidebar-width-mobile`.<br>- Rename `isMobile` to `isCompact`.<br>- ctrl/cmd+b acts, and calls `preventDefault`, only when not compact.<br>- `SIZES` gains `touch: 'min-h-11 py-2 text-body'`. That size gets no `overflow-hidden` and no label `truncate`.<br>- Tooltips stay hidden when compact.<br>- The wrapper gains `max-lg:flex-col` (section 4a) |
| `frontend/src/components/ui/sheet.tsx` | New. `Sheet`, `SheetTrigger`, `SheetContent` (bottom only), `SheetTitle` and `SheetClose`, on Radix Dialog |
| `frontend/src/components/shell/TabBar.tsx` | New. The bar, built from `dockDestinations` and `isInMore`, with `lang` and the zero-guarded `ResizeObserver` for `--tabbar-height` |
| `frontend/src/components/shell/MoreSheet.tsx` | New.<br>- Controlled `open`, reset during render when the pathname or `isCompact` changes.<br>- `onCloseAutoFocus` falls back to `#main`.<br>- The remaining destinations (`moreDestinations`) and the account group |
| `frontend/src/components/shell/AccountMenu.tsx` | - The menu always opens to the right.<br>- Drop `setOpenMobile`.<br>- Controlled `open`, reset during render when `isCompact` changes, with focus then going to `#main`.<br>- Share `secondLine` and the sign-out handling with the sheet's account group.<br>- It keeps `data-who-panel` |
| `frontend/src/components/shell/AppSidebar.tsx` | - Drop the `setOpenMobile` and `isMobile` branches.<br>- Footer bottom padding becomes `max(1rem, env(safe-area-inset-bottom))` |
| `frontend/src/components/shell/MobileHeader.tsx` | Wordmark only, `lg:hidden` |
| `frontend/src/components/shell/AppShell.tsx` | - Render `TabBar` after `AppSidebar` and before `SidebarInset`.<br>- Add the safe-area gutter at both steps and the bottom clearance.<br>- Make the skip link safe-area aware |
| `frontend/src/components/shell/NavIcon.tsx` | - Add the `more` (three dots) and `close` icons.<br>- Add the `size` prop (`'row'` 16 px, `'tab'` 20 px) |
| `frontend/src/shared/navigation/registry.ts` | Add `shortLabelKey?`, `moreDestinations` and `isInMore(surface, permissions, pathname)`. No new dock helper and no exported cap |
| `frontend/src/app/(tenant)/[...missing]/page.tsx` | New. It calls `notFound()` |
| `frontend/src/app/(tenant)/not-found.tsx` | New. It renders `NotFoundScreen` inside the shell.<br>- Unmatched tenant URLs, which today include `/watch`, `/inventory`, `/search` and `/roadmap`, keep the bar and the rail instead of dropping to the bare root 404.<br>- An anonymous visitor on an unknown URL now reaches sign-in instead of a bare 404.<br>- Explicit routes (auth, dev, the future console) still win |
| `frontend/src/styles/theme.css` | Add `--shadow-float` |
| `frontend/src/styles/globals.css` | Add `--tabbar-height`, `--tabbar-bottom`, `--tabbar-top`, `scroll-padding-bottom`, the keyboard rule and the two height rules (section 4a) |
| `frontend/src/messages/nav/{en,sv}.json` | - Add `nav.search.short` ("Search" / "Sök") and `shell.close` ("Close" / "Stäng").<br>- Remove `sidebar.title`, `sidebar.description` and `sidebar.toggle`, which nothing uses after this change.<br>- `nav.more` and `shell.account` already exist |
| `frontend/tests/e2e/support/passkeys.ts` | Change the helpers (section 16) |

---

## 16. Tests the build must add or change

### Unit tests (Vitest)

In jsdom, CSS does not apply, so the rail and the bar both render. Scope every query to `[data-slot="tab-bar"]` or `[data-slot="sidebar"]`.

**`registry.test.ts`**
- The existing "orders the phone dock by rank" test covers the order:
  - tenant: `['today','watch','inventory','search']`
  - console: `['console-queue','console-vocabularies','console-sources']`
- Each surface has at most 4 destinations with a `dockRank`. The 4 and its iOS reason sit in the test.
- `moreDestinations` with every permission: tenant `['roadmap','admin']`, console `[]`.
- With an empty permission list: dock `['today']`, More `[]`.
- With `watch.read` missing: dock `['today','inventory','search']`, and nothing unranked is promoted.
- `isInMore` is true for `/roadmap`, `/admin/members` and `/me/sessions`. It is false for `/`, `/watch` and `/watch/42`.
- Every `shortLabelKey` exists in en and sv.

**`shell.test.tsx`**
- **Existing helpers.** `mainNav()` is scoped to `[data-slot="sidebar"]`. A new `tabBar()` is scoped to `[data-slot="tab-bar"]`. Otherwise `getByRole('navigation', { name: 'Main' })` finds two.
- **The "at phone width" block becomes "at compact width":**
  - **The bar.**
    - It is a `navigation` named "Main" holding one list: four links in registry order, then a button named "More".
    - Search shows "Search", not "Search and ask".
    - Rendered in sv, the bar reads Idag, Bevakning, Inventarie, Sök, Mer, and the nav has `lang="sv"`.
  - **The current tab.**
    - It has `aria-current="page"` and `data-active="true"`. No other element has `aria-current="page"`.
    - A nested route (`/admin/members`, for Admin in the sheet) marks its parent.
  - **On `/roadmap`.**
    - More has `data-active="true"` and `aria-current="true"`.
    - In the open sheet, the Roadmap link has `aria-current="page"`.
  - **The More button** has `aria-haspopup="dialog"`, and `aria-expanded` goes from false to true.
  - **The sheet.**
    - It is a dialog named "More".
    - It lists the remaining destinations, grouped primary, secondary, admin.
    - It then has a group named "Account" holding: the name, organisation · roles, My passkeys, My sessions, and a Sign out button.
    - Nothing inside the dialog has `data-who-panel`.
    - Rendered with a 120-character organisation and role string, no element in the dialog has a `truncate` class.
  - **Sign out** shows "Signing out…" and is disabled while pending, then replaces the route with `/sign-in`.
  - **Closing.**
    - Choosing a link closes the sheet.
    - Escape closes it and puts focus back on More.
    - The Close button closes it.
    - A pathname change (the mocked `usePathname` re-rendered) closes it.
    - Flipping the stubbed `COMPACT_QUERY` to false closes it and focuses `#main`.
  - **The rail's account menu.** With it open, flipping `COMPACT_QUERY` to true closes it and focuses `#main`.
  - **Shape.**
    - No element in the bar or the sheet has `rounded-full`.
    - The bar has `rounded-overlay`, and the current cell has `rounded-control`.
  - **Height measurement.** With a stubbed `ResizeObserver`:
    - An entry of 72 px writes `--tabbar-height: 72px` on `<html>`.
    - A later entry of 0 leaves it at 72px.
    - Unmounting removes it.
  - **Permissions.** A person whose permissions unlock only Today sees Today and More.
  - **Console surface.** Queue, Vocabularies, Sources and More. More holds only the account group.
  - **Header.** The wordmark header links to `/` and contains no menu button (`[data-sidebar="trigger"]` is gone).
  - **Gutter.** The page wrapper carries the safe-area gutter utilities at both steps, and no bare `px-*` or `md:px-*`.

**`sidebar.test.tsx`**
- `COMPACT_QUERY` equals `'(width < 64rem)'`.
- **Changed tests.**
  - The "starts expanded … the trigger collapses it" test toggles with ctrl+b, because `SidebarTrigger` is gone. It no longer asserts `--sidebar-width-mobile`.
  - The `State` helper reads `isCompact` (`data-compact`), and `openMobile` goes.
- Below 1024 px, the rail never renders a dialog. ctrl/cmd+b neither toggles anything nor calls `preventDefault`.
- A `touch` row has `min-h-11` and no `truncate`.
- A row in the sheet never shows a tooltip, even when the stored rail state is collapsed.
- The wrapper carries `max-lg:flex-col`.

### Contrast (`contrast.test.ts`, both themes)

| Pair | Foreground / background | Floor | Expected (light / dark) |
|---|---|---|---|
| tab bar: tab label on the bar | `content-neutral-02` / `l2-neutral-02` | 4.5 | 5.60 / 7.93 |
| tab bar: current tab label | `--sidebar-accent-foreground` / `--sidebar-accent` | 4.5 | 16.50 / 11.69 |
| more sheet: row label | `content-neutral-01` / `l2-neutral-02` | 4.5 | passes |
| more sheet: organisation and role line | `content-neutral-02` / `l2-neutral-02` | 4.5 | 5.60 / 7.93 |
| tab bar: tab icon on the bar (non-text) | `content-neutral-02` / `l2-neutral-02` | 3 | 5.60 / 7.93 |
| tab bar: current-tab outline on the bar (non-text) | `border-neutral-01` / `l2-neutral-02` | 3 | 4.15 / 7.05 |
| tab bar: current-tab outline on its fill (non-text) | `border-neutral-01` / `l3-neutral-02` | 3 | 3.47 / 5.03 |
| more sheet: current-row outline on the sheet (non-text) | `border-neutral-01` / `l2-neutral-02` | 3 | 4.15 / 7.05 |
| tab bar: focus ring on the bar (non-text) | `content-notice-01` / `l2-neutral-02` | 3 | 6.39 / 8.19 |

Name each pair for the bar or the sheet, even where a generic pair already covers it, so that a later token change fails by name.

### End to end (Playwright, `frontend/tests/e2e/navigation.journey.spec.ts`)

**Setup.**
- Real backend, no mocks. Existing journeys keep Desktop Chrome at the default width.
- This spec sets its own viewports with `test.use({ viewport, hasTouch, isMobile })`, so the whole suite does not double.
- The phone and tablet blocks use `hasTouch: true`, which gives a coarse pointer; phones also set `isMobile: true`.
- English only (playbook 8.3).

**At 375 × 812, touch.** Tag the first test `@smoke`.
1. **The reader signs in.**
   - A "Main" navigation is visible, with links Today (current), Watch, Inventory and Search, and a button More.
   - The rail is not visible. The wordmark is visible.
   - No horizontal scroll: `scrollWidth ≤ innerWidth`.
2. **Tapping each tab** keeps the "Main" navigation visible, including the tabs whose screens are not built yet. Those render the not-found screen inside the shell.
3. **More** opens a dialog named "More" that contains Roadmap and the "Account" group.
   - Escape closes it, and More has focus.
   - A tap on the scrim closes it. The Close button closes it.
4. **My passkeys**, chosen in the sheet, goes to `/me/passkeys` and closes the sheet.
   - More now has `data-active="true"` and `aria-current="true"`. No link in the bar has `aria-current="page"`.
   - Reopening the sheet shows My passkeys with `aria-current="page"`.
5. **The admin** sees Admin in More. Choosing it goes to `/admin`, where More shows as current.
6. **Back closes the sheet.** On `/admin/organisation`, open More, then `page.goBack()`. No dialog is present.
7. **The keyboard rule**, on `/admin/organisation` as admin:
   - Focusing `#org-name` hides the bar. Blurring it shows the bar again.
   - Scroll `#org-timezone` to the bottom of the viewport (`scrollIntoView({ block: 'end' })`), focus it, and press Tab. The newly focused select's box does not intersect the bar's box.
8. **Clearance**, on `/admin/organisation`:
   - First assert `document.documentElement.scrollHeight > window.innerHeight`, so the step cannot pass on a short page.
   - Scroll to the bottom. The last element in `main` ends above the bar's top edge.
   - Tab through the page. While the bar is visible, no focused element's box intersects the bar's box.
9. **`signOut()`** works at this width through More, and lands on "Sign in".
10. **Screenshots** (Chromium baselines, light only): the bar, and the open sheet.

**At 360 × 780 and 320 × 640, touch.**
- Each tab label is one line tall, which catches a word broken in the middle.
- No horizontal scroll.
- No tab label is clipped: `scrollWidth ≤ clientWidth` for each label.

**At 844 × 390 (landscape phone), touch.**
- The bar is at most 56 px tall.
- Each label is one line and sits beside its icon.
- The last element in `main` ends above the bar.

**At 320 × 256.** The bar's computed `position` is `static`.

**At 768 × 1024, touch.**
- The bar is visible and the rail is not.
- The bar is centred, and at most `5 × 96 + 14` px wide.
- More opens and closes. The sheet is at most 560 px wide and centred.

**At 800 × 900, fine pointer (no touch).** Focusing a text field leaves the bar visible.

**Crossing 1024.**
- **More open.** At 834 × 1194 with More open, call `setViewportSize` to 1194 × 834. Then:
  - No dialog is present.
  - `document.activeElement` is `#main`, not `body`.
  - `getByRole('navigation', { name: 'Main' })` is visible, which proves no stray `aria-hidden`.
  - `body`'s computed `pointer-events` is not `none`.
- **Account menu open.** At 1194 × 834 with the rail's account menu open, resize to 834 × 1194. The same checks hold.

**Boundary.**
- At 1023 px wide, the bar is visible and the rail hidden.
- At 1024 px wide, the rail is visible and the bar hidden.

**Helpers (`support/passkeys.ts`).**
- **`signInAs`** waits for `getByRole('navigation', { name: 'Main' })` to be visible, instead of `[data-who-panel]`. The shell renders only for a signed-in person, and exactly one visible "Main" landmark exists at every width.
- **`signOut`** branches on the viewport, which is deterministic and mirrors `COMPACT_QUERY`:
  - If `(page.viewportSize()?.width ?? 1280) < 1024`: call `openMore(page)`, then click `getByRole('dialog', { name: 'More' }).getByRole('button', { name: 'Sign out' })`.
  - Otherwise, keep today's rail flow.
- **New helper** `openMore(page)`.
- **`[data-who-panel]`** is desktop-only. Journeys that read it run at desktop width and are unchanged. In the sheet, find the account by role: `getByRole('dialog', { name: 'More' }).getByRole('group', { name: 'Account' })`.
- **`copy-drift-check.mjs`** passes: every asserted label ("More", "Close", "Search", "Account") exists in `en.json`.

---

## 17. Design contract changes, in the same slice

| File | Change |
|---|---|
| `design/system/navigation.md` | This file (new) |
| `design/system/foundations.md` | - **Radius:** add "floating tab bar" to the `radius-s` row, and "current tab" to the 6 px controls row.<br>- **Components:** add a "Tab bar" entry and a "More sheet" entry with the values in sections 3 to 5, including the current-tab outline.<br>- **Sidebar row:** remove "280 px as a phone sheet".<br>- **Shadow:** a new line: one shadow, `float` (Green `l-01` + `l-02`), used only by the tab bar.<br>- **Spacing:** the compact bottom clearance and the safe-area gutter.<br>- **Contrast:** the new pairs, text and non-text.<br>- **Wordmark:** "64 px in the compact header (below 1024 px)" |
| `design/system/pills-and-labels.md` | The shape paragraph lists the current tab among the 6 px shapes, and says the bar is 12 px, not fully rounded |
| `design/README.md`, "The rail" | - Replace "On phones there is no dock…" with: the tab bar below 1024 px, four dock destinations plus More, and a More sheet holding the rest and the account.<br>- Keep "A count, once a screen feeds one, is a quiet muted number at the end of its row" |
| `design/screens/tenant-shell.html` | - Replace the `@media (max-width:767px)` block and its note with a `max-width:1023px` tab bar.<br>- Add a More sheet state.<br>- Restate the note |
| `design/screens/console-shell.html` | Its dock sentence now matches this file. The card is restyled with the console chunk |
| `design/prototype/index.html` | - In the `max-width:820px` block, replace the `.mbrand`, `.mtrigger` and `.app.sheet` rules with the tab bar and the More sheet, at `max-width:1023px`.<br>- ctrl/cmd+b only minimises the rail at 1024 px and wider |
| The other 27 screen cards | Their `.tabbar` is the old full-width brand bar. They are restyled when their chunk is built. Until then, this file wins |
| `docs/adr/0020-design-direction.md` | New amendment, "2026-09-19: the tab bar below 1024 px". It:<br>- replaces the rail amendment's phone sheet and "an off-canvas sheet below 768 px"<br>- strikes `SidebarTrigger` from that amendment's parts list<br>- strikes "a second navigation model for phones" from its "Deliberately not done", as Alex's new decision<br>- keeps one navigation model per width<br>- records sections 1, 3 and 14 |
| `docs/plans/Verification_Log.md` | One row per external claim relied on above (see Sources), dated 2026-09-19 |
| `docs/TODO_FOR_alex.md` | - The open questions.<br>- The device checks in section 18.<br>- Overlay motion for `Modal` and the sheet together.<br>- Dark screenshots of the bar and the sheet (the app follows the system theme; say if you want them).<br>- `<html lang>` following the person's language |

`docs/PLAYBOOK.md` 6.2 and `docs/CONVENTIONS.md` 3.2 already name "dock rank … Dock, sidebar, More menu". They are unchanged.

---

## 18. Checks only a real device can make

- **iPhone, in Safari and as a home-screen app.**
  - The bar clears the home indicator in portrait and landscape, and landscape shows the inline bar.
  - The page gutter clears the notch in landscape.
  - With a hardware keyboard, the focused skip link clears the notch in landscape.
  - Safari's toolbar tint does not pick up the bar.
  - The keyboard hides the bar and brings it back.
- **Android, Chrome.**
  - With gesture navigation, the bar clears the gesture area.
  - The keyboard hides and restores the bar.
  - The back gesture with More open closes the sheet along with the page.
- **iPad.**
  - Portrait, with and without a hardware keyboard.
  - Rotating with More open, and with the account menu open, leaves nothing stuck.
  - The rail footer clears the home indicator in landscape.
- **Swedish labels at 360 px and 320 px.** E2E runs in English only (playbook 8.3).
  - At 360 px, every label fits on one line.
  - At 320 px, "Bevakning" breaks at a hyphen (Safari has a Swedish dictionary).
- **Windows forced colours** on a desktop zoomed below 1024 CSS px: the current tab shows its outline.

---


## Open questions

Each takes its stated default (`docs/DECISIONS.md` rule) and is listed in `docs/TODO_FOR_alex.md`. The "Rejected" lines record critiques of this file that were considered and not taken.

- Open question 1: should the bar be capsule-shaped, with a fully rounded current tab, as in iOS 26? Default: no. The bar takes the 12 px overlay radius and the current tab 6 px, because the fully rounded shape belongs to Pill alone (ADR 0020, playbook 6.7).
- Open question 2: should the More sheet close with a downward swipe? That needs the Base UI Drawer (a second headless library beside Radix) or vaul (unmaintained). Default: no swipe. Close, Escape, the scrim and any route change close it.
- Open question 3: the 13-inch iPads in portrait (1024 and 1032 px wide) get the rail, which leaves 784 px of content. Should they get the tab bar instead? That needs a breakpoint that is not a step in Green or Tailwind. Default: the rail, from 1024.
- Open question 4: should each tab remember where the person was in its section, as iOS does? For example, going from /watch/42 to Inventory and back would land on /watch/42. Default: no. Every tab links to its section's root, as the rail does, and the browser's back button returns to the previous place.
- Open question 5: the rail's current row has the same fill-only indicator, at 1.12:1 light and 1.58:1 dark against the rail, which fails WCAG 1.4.11 in the same way. Should it get the tab's 1 px line-strong inset outline, which measures 3.90 / 7.96 against the rail? Default: unchanged in this slice, because ADR 0020 approved that look today. Recorded in TODO_FOR_alex.
- Open question 6: should Modal and the More sheet animate together (a slide and fade that respects reduced motion)? Default: neither animates.
- Open question 7: <html lang> is the build default (NEXT_PUBLIC_DEFAULT_LOCALE), while signed-in screens render the person's own language (SessionGate), so a Swedish user's pages are announced as English (WCAG 3.1.1). Default: fix it as a separate task. Meanwhile the tab bar sets its own lang for hyphenation.
- Rejected: the unit test that focusing an input leaves --tabbar-height unchanged (the critique of sections 8 and 9). jsdom applies no CSS, so nothing would hide the bar. The unit test pins the zero-height guard instead, and E2E step 7 covers the real case.
- Rejected: checkVisibility() for the focus fallback when overlays cross 1024 px. Safari has it only from 17.4, and the close is driven by the width flip, so the handler already knows the trigger is hidden.
- Rejected: raising the current tab's weight to 600 and adding separate forced-colors: rules (the current-state contrast critique). The inset outline alone reaches 3:1, and forced-colours mode keeps outlines, so the weight stays the rail's 500.
- Rejected: Swedish label checks in E2E (the label-break critiques). Playbook 8.3 pins E2E to one language and every seed login has locale 'en'. Swedish widths are covered by the measured arithmetic in section 5 and a device check.
- Rejected: an E2E check with the WCAG 1.4.12 text-spacing override. 1.4.12 asks for no loss of content; a wrapped label grows the bar and loses nothing, and the 320 px no-clip check already covers loss.
- Rejected: the premise that <html lang> carries the person's language for hyphens:auto. It is the build default (app/layout.tsx), so the bar sets lang from useLocale() itself.
- Rejected: an E2E check of long account lines at 320 px. No seed login has a long organisation or role string, so it would pass without testing anything. A unit test renders a 120-character string and asserts that nothing in the sheet truncates.
- Rejected: the 'preferred' option of pushing a history entry so that back closes only the sheet. It couples the sheet to the router and history beyond this slice. Closing on any route change already prevents the stale sheet, and back-to-close stays listed in section 14.
- Rejected: building per-tab memory now. It needs sessionStorage state, a hydration path and clearing on sign-out, while the rail links to roots. The critique's own alternative, a recorded departure, is applied, and Alex is asked in open question 4.
- Rejected: the claim that section 5 calls every tab's root link Apple's rule. The sentence sat under 'Tapping the current tab', where returning to the root is Apple's rule. It has been reworded so it cannot be read as covering the other tabs.

## Sources, as read on 2026-09-19

| Source | Relied on for |
|---|---|
| https://developer.apple.com/design/human-interface-guidelines/tab-bars | Tab bars preserve each section's navigation state (a departure recorded here); icons above labels in compact views and side by side otherwise (the compact-height layout); a modal may cover the bar; labels always shown and short; avoid overflow tabs; iPad puts the tab bar at the top. Text read through developer.apple.com/tutorials/data/design/human-interface-guidelines/tab-bars.json |
| https://developer.apple.com/documentation/uikit/uitabbarcontroller | At most four tabs plus More on iPhone; tapping the selected tab returns to its root |
| https://developer.apple.com/videos/play/wwdc2025/356/ | Floating bar inset from the edge on phones; concentric corners (12 px bar, 6 px padding, 6 px highlight) |
| https://developer.apple.com/design/human-interface-guidelines/materials | Glass responds to Reduce Transparency, which is why the bar is solid |
| https://developer.apple.com/design/human-interface-guidelines/layout | Safe areas; an app should do the same things at every width |
| https://developer.apple.com/design/human-interface-guidelines/sidebars | Apple's iPad pattern (a tab bar first, a sidebar for depth), a departure accepted knowingly |
| https://developer.apple.com/design/human-interface-guidelines/accessibility | 44 x 44 pt default touch target |
| https://developer.apple.com/videos/play/wwdc2025/284/ | Minimising the bar on scroll is opt-in, so never moving it matches the default |
| https://m3.material.io/components/navigation-bar/guidelines | Three to five destinations; never remove or truncate labels; one active item; don't hide on scroll while a screen reader is active; the keyboard may cover the bar for a while; no swiping between destinations |
| https://m3.material.io/components/navigation-bar/accessibility | The bar grows with text size and labels stay visible at twice the text size, which is why --tabbar-height is measured |
| https://developer.android.com/develop/ui/compose/layouts/adaptive/use-window-size-classes | Width classes: compact below 600 dp, medium 600 to 839, expanded from 840. Height: compact below 480 dp (the 30rem compact-height rule). Corrects '840 = compact/medium' to medium/expanded |
| https://developer.android.com/develop/ui/compose/layouts/adaptive/build-adaptive-navigation | NavigationSuiteScaffold default: a navigation bar when the width or the height is compact, a rail otherwise. Basis of the rewritten Material departure |
| https://m3.material.io/foundations/designing/structure | 48 dp minimum touch target |
| https://www.nngroup.com/articles/hamburger-menus/ | Hidden navigation lowers discoverability, which supports replacing the hamburger sheet with visible tabs |
| https://www.nngroup.com/articles/find-navigation-mobile-even-hamburger/ | Combined navigation (some items visible, the rest collapsed) beats fully hidden navigation |
| https://tailwindcss.com/docs/responsive-design | lg = 64rem (1024 px) and its max-lg/lg variants |
| https://screensizechecker.com/devices/ipad-viewport-sizes | iPad CSS viewport widths in portrait and landscape (secondary source) |
| https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/meta/name/viewport | viewport-fit=cover, and using safe-area insets with it |
| https://webkit.org/blog/7929/designing-websites-for-iphone-x/ | env() safe-area insets are not margins, so combine them with max(); landscape side insets on notched iPhones |
| https://developer.mozilla.org/en-US/docs/Web/CSS/env | env(safe-area-inset-*) for a bottom toolbar, the gutter and the skip link |
| https://nextjs.org/docs/app/api-reference/functions/generate-viewport | Next.js viewport export with viewportFit: 'cover' |
| https://raw.githubusercontent.com/vercel/next.js/canary/packages/next/src/lib/metadata/types/extra-types.ts | The Viewport type accepts viewportFit 'auto' / 'cover' / 'contain' |
| https://benfrain.com/ios26-safari-theme-color-tab-tinting-with-fixed-position-elements/ | iOS 26 Safari toolbar tint from fixed elements (observed by the community, hence a device check) |
| https://www.w3.org/TR/resize-observer/ | An observation fires when the watched element's display is set to none, so display:none would zero --tabbar-height; basis of visibility:hidden and the zero-height guard |
| https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html | A state indicator needs 3:1 against adjacent colours; a fill may mark the state only if it contrasts with what surrounds it. Basis of the inset line-strong outline on the current tab |
| https://developer.mozilla.org/en-US/docs/Web/CSS/@media/forced-colors | Forced colours override background-color and outline-color with system colours and remove box-shadow; outlines stay visible, so the current tab stays distinct |
| https://www.w3.org/WAI/WCAG22/Understanding/reflow.html | Advice to make sticky or fixed parts static at small viewport sizes: the height-below-20rem rule |
| https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | WCAG 2.5.8 AA, 24 px target size |
| https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html | WCAG 2.5.5 AAA, 44 px target size |
| https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html | WCAG 2.4.11: a sticky bar must not hide the focused element (F110). Drives the clearance, the keyboard rule and the visibility choice |
| https://www.w3.org/WAI/WCAG22/Techniques/css/C43 | scroll-padding-bottom plus bottom padding as the sufficient technique |
| https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html | DOM order may differ from visual order when meaning is kept (the bar before main, shown at the bottom); focus must not be lost to body when an overlay closes |
| https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation.html | Navigation and content in the same relative order at every width |
| https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html | The visual 'current page is in More' state needs a programmatic equivalent: aria-current='true' on More |
| https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ | The More sheet as a modal dialog: focus inside, Tab wraps, Escape closes, focus returns, labelled by a visible title |
| https://www.w3.org/WAI/ARIA/apg/patterns/landmarks/examples/navigation.html | A labelled nav landmark; only one Main landmark exposed at a time |
| https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-current | aria-current='page' on the current link; 'true' for the current item in a set (the More button) |
| http://adrianroselli.com/2017/10/dont-use-aria-menu-roles-for-site-nav.html | Plain links for site navigation, with no menu or tab roles; why DropdownMenu and Tabs are rejected |
| https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/ | APG avoids the menu role for site navigation |
| https://ui.shadcn.com/docs/components | shadcn has no bottom navigation or tab bar component |
| https://github.com/shadcn-ui/ui/issues/8847 | The Bottom Navigation request is still open, with no maintainer response |
| https://ui.shadcn.com/docs/components/radix/sheet | Sheet with side='bottom' extends Radix Dialog; the chosen presenter for More |
| https://www.radix-ui.com/primitives/docs/components/dialog | Focus trap, Escape returning focus to the trigger, onCloseAutoFocus (used for the #main fallback), opting out of aria-describedby |
| https://ui.shadcn.com/docs/components/radix/drawer | The Radix-flavour Drawer is built on vaul (rejected) |
| https://raw.githubusercontent.com/emilkowalski/vaul/main/README.md | vaul is unmaintained |
| https://ui.shadcn.com/docs/components/drawer | The Base UI Drawer is the swipe-capable alternative; it would add a second primitive library (open question 2) |
| https://developer.chrome.com/blog/viewport-resize-behavior | Chrome on Android resizes only the visual viewport by default, so the keyboard can cover fixed elements |
| https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport | The keyboard shrinks the visual viewport, not the layout viewport, so height media queries are not affected; why no JS placement is attempted |
| https://caniuse.com/mdn-api_virtualkeyboard | The VirtualKeyboard API is Chromium-only, so it is not used |
| https://www.bram.us/2026/09/11/webkit-supports-interactive-widget-and-hopefully-safari-will-too/ | Safari has not shipped interactive-widget, so the default resizes-visual stays |
| https://developer.apple.com/forums/thread/800125 | iOS 26.0 visualViewport.offsetTop bug that misplaced fixed footers; why the keyboard rule is CSS only |
| https://caniuse.com/css-has | :has() support (Safari 15.4, Chrome 105, Firefox 121) for the keyboard rule |
| https://www.learnui.design/blog/ios-design-guidelines-templates.html | Third-party measurement of the iOS floating bar, used only as a sanity check for the 64 px height |
| green-design-system MCP get_tokens (shadow, space, viewport) | shadow-l-01/l-02 for shadow-float, space-m/space-5xl, viewport-m = 1024 |
| frontend/src/shared/navigation/registry.ts | Destinations, dockRank, groups, permission gating, and the existing dockDestinations the bar calls directly |
| frontend/src/components/ui/sidebar.tsx | MOBILE_QUERY, the phone Dialog branch with its bg-fg/50 scrim, SidebarTrigger, SIZES with overflow-hidden and truncate, and the flex wrapper |
| frontend/src/components/ui/Modal.tsx | Modal's scrim is bg-fg/60 at z-40, and Modal opens without animation |
| frontend/src/components/shell/AccountMenu.tsx | Uncontrolled modal DropdownMenu rendered without a portal inside the rail, and data-who-panel on its wrapper |
| frontend/src/components/shell/AppShell.tsx | The wrapper's px-4 pt-3 pb-16 md:px-8 md:pt-6 and the skip link's focus:top-2 focus:left-2 |
| frontend/src/app/layout.tsx | html lang is the build default locale, not the person's language |
| frontend/src/components/shell/SessionGate.tsx | Signed-in screens render in the person's own locale (userLocaleOf), which is why the bar sets its own lang |
| frontend/src/app/(tenant) | Only /, /admin/*, /me/* and /restricted exist, so today the Watch, Inventory, Search and Roadmap links fall through to the root not-found page outside the shell |
| frontend/src/components/admin/OrganisationScreen.tsx | In-page #org-name and #org-timezone text fields followed by a select, used by E2E steps 7 and 8 |
| frontend/src/components/admin/MembersScreen.tsx | Its only text inputs are inside the Invite Modal, so it cannot test the keyboard rule |
| frontend/src/styles/theme.css | Dark tokens only under .dark with no prefers-color-scheme rule; the sidebar accent aliases |
| frontend/src/styles/contrast.test.ts | PAIRS and NON_TEXT structure for the new named pairs |
| frontend/tests/e2e/pills.gallery.spec.ts | Byte-identical dark baselines were already rejected as a control that proves nothing |
| backend/apps/shared/e2e_logins.py | Every seed login runs in locale 'en' (playbook 8.3, one pinned language), so Swedish E2E checks are not possible |
| frontend/node_modules/eslint-plugin-react-hooks | The 7.1.1 recommended rules make set-state-in-effect and set-state-in-render errors, so overlays reset during render, not in an effect |
| design/system/foundations.md | Radius steps, colour aliases, Toggle's pressed pairing (l3-neutral-02 with border-neutral-01), '280 px as a phone sheet', contrast values |
| docs/adr/0020-design-direction.md | The rail amendment this spec reverses below 1024 px: SidebarTrigger in its parts list, 'an off-canvas sheet below 768 px', 'count bubbles' and 'a second navigation model for phones' under Deliberately not done, and the badge coming back with its screen |
| design/README.md | 'A count, once a screen feeds one, is a quiet muted number at the end of its row' |

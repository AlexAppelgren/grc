# Design

| Path | What it is |
|---|---|
| `prototype/index.html` | The interactive prototype ("bleqq: compliance inventory and watch"). Open it in a browser. It is the contract for flow, wording, labels and pills. Its sample data seeds `seed_e2e` and `seed_demo` |
| `system/foundations.md` | Type roles, radius, spacing, the component specs and the Green token behind every colour |
| `system/navigation.md` | The rail and the tab bar: which width gets what, the More sheet, and the reason and source for each rule |
| `system/pills-and-labels.md` and `.html` | The pill and label contract, and a rendered card |
| `brand/` | The phonetic wordmark `[blɛkː]`, the favicon, and the brand layer placeholders |
| `screens/` | Empty. Cut one card per screen from the prototype as each chunk starts (playbook Section 7) |

## Direction (already chosen)

Timeline home showing the next dates as the same short list on phone and
desktop, with part of the weekly briefing on it and the full briefing one tap
away. The full calendar lives on its own roadmap page, where a card expands
in place. Phone first. On phones, actions sit on the right, two buttons share
one row, primary on the right.

**The look (Alex, 2026-09-19; ADR 0020 amendment "Foundations").** "Still not
happy with this, looks big, clumsy and childish. Take much less inspiration
from seb.io (maybe only keep colour schemes) and more from shadcn ui
components and other modern and professional styles. We can also reduce the
logo size a bit more." So: a dense, professional dashboard at shadcn/ui's
proportions in Green's colours. A 14 px base, a 24 px semibold page title,
16 px section titles; 36 px buttons with a 6 px radius in primary, outline
and ghost, never fully rounded; cards on a hairline with an 8 px radius, 16 px
padding and no shadow or fill; 32 px sidebar rows with 16 px icons. Colour
keeps Green's neutral scale for surfaces, borders and text and the brand pair
through `brand.css`: white page in light, near black in dark, a neutral
primary, brand green only for meters and the timeline, sand only on the
AI-drafted callout and the legal margin, brass on `brand` pills. Hanken
Grotesk for text, Noto Sans Mono for legal references and the wordmark, which
is about 68 px wide. Every value is in `system/foundations.md`.

**The rail (Alex, 2026-09-19; ADR 0020 amendment).** The green rail with white
text, fully rounded buttons, count bubbles and a bordered "who" card read as a
consumer app, not software a compliance officer uses all day. The rail is now
shadcn/ui's Sidebar structure in the restraint of seb.io's own left rail: a
neutral surface barely distinct from the page (one step below it in light,
flush in dark) with a hairline border, compact 32 px rows of a 16 px icon and a
14 px label in normal weight, groups separated by space rather than headings or
rules, and no scrollbar. The current row is shadcn's treatment, not seb.io's
pill: full width, a 6 px radius, a neutral tint, medium weight. The fully
rounded shape belongs to the six pill tones alone. The phonetic wordmark
`[blɛkː]` sits alone on top in the text colour, about 68 px wide: a signature,
not a banner (Alex, 2026-09-19, twice: the mark took too much room). The
signed-in person is one quiet row at the bottom (name, then organisation and
role) opening a menu with My passkeys, My sessions and Sign out, followed by
"Minimise menu". Minimised (or ctrl/cmd+b), the rail keeps only icons with a
tooltip each and the open e alone as the mark, and remembers the choice on the
device. The rail shows from 1024 px.

**The tab bar below 1024 px (Alex, 2026-09-19; ADR 0020 amendment "the tab
bar below 1024 px").** Below 1024 px, which covers every phone and every
iPad below 13 inches in portrait, the rail gives way to a floating tab bar
with five items, the fifth being More, as many iPhone apps do. The first four are the registry's dock destinations (Today, Watch,
Inventory and Search for every system role). More opens a sheet from the
bottom holding every other destination and the account: the name,
organisation and role, My passkeys, My sessions and Sign out. So every
destination is reachable at every width. The bar floats on the surface colour
with a hairline and a 12 px radius; the current tab is the rail's current row
with a 1 px outline, never a full pill. The wordmark stays as a line at the
top of the page and scrolls away. Every value and its reason is in
`system/navigation.md`.

A count, once a screen feeds one, is a quiet muted number at the end of its
row.

## Where the prototype is wrong or silent

| Topic | What to do |
|---|---|
| The tenant's compliance officer approves agent proposals into the inventory | Wrong for a shared library. The queue moves to the platform console (`library_editor`). Tenants see library updates and report problems |
| "Switch user" | Prototype device only. Replace with real sign-in |
| The scope toggles apply at once, on a Settings page every user can open | The section is Regulatory scope, under Admin, and only the two scope permissions open it. A change becomes a request with a preview and a second person. The prototype's scope view stops at a pending request with Withdraw; approval, rejection and history follow the app and `screens/admin-footprint.html` |
| `UCLASS` maps the label "Act now" to a colour, and urgency and change type are stored as labels | Store keys. Tone comes from slot or kind |
| Obligation `tags` feed search but never render | Render library tags as `brand` pills after the flags, tenant tags as outlined `information` pills |
| Colours are hex values copied from Green | Import the tokens, override the brand pair |

## Screens the prototype lacks

Design each as a card in the prototype's language before building it.

- **Sign-in and enrolment:** invitation landing, code entry, passkey
  enrolment with the prompt for a second passkey, passkey sign-in, step-up
  prompt, "ask your admin" recovery, my passkeys, my sessions.
- **Tenant admin:** organisation (entities, licences, products, teams),
  members and invitations with re-enrolment and bulk reassignment, roles from
  permissions, vocabularies, workflow policy, security policy, agents,
  integrations and API keys, data (import, export, retention), support access.
- **Platform console:** proposal queue with the source beside the diff,
  library vocabularies, sources and coverage, languages and jurisdictions,
  agent definitions and versions, evaluation sets, problem reports, tenants
  and plans, system health.
- **Vocabulary management:** the list of lists, rows rendered as the real
  pill in light and dark with usage count, inline rename, reorder, retire,
  merge, and "create where you use it" inside pickers.
- **States:** empty, loading, error and denied for every screen. The
  prototype shows few of them.

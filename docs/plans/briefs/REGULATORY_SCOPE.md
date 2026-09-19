# Regulatory scope (was "Footprint"): spec

Status: final proposal for Alex. It serves FP-01, FP-02, FP-03, AC-FP1, ADM-01 and J-6. No requirement text changes. One PRD glossary line is suggested, for Alex to add.

## 1. In one paragraph

The section that decides what every member sees becomes **Regulatory scope** (sv **Regulatorisk omfattning**). It sits under Admin, and only people who hold `footprint.request` or `footprint.approve` can open it. Everyone else gets the restricted page. The page opens read-only: every option is drawn as a checkbox, ticked or empty, and nothing can be changed. A quiet danger button, "Propose a change", turns the options into real checkboxes. A change is a request. The page says what the request adds and removes and counts what it hides and reveals. Someone else approves it after a passkey step-up, or rejects it with a reason. The requester can withdraw it, and the history keeps every decision. Banking and Payments join the regimes.

These parts already exist on `main` (`backend/apps/taxonomy/footprint_logic.py`, `api.py` lines 415-540): the request, the dry-run preview, four eyes (a 409 plus a check constraint), the step-up and an optional If-Match. What is still wrong:
- The prototype applies a toggle at once, on a Settings page every user can open. `design/README.md` already says this is wrong.
- The app draws the options as chips, which read like a harmless filter, and its read state is a row of disabled controls.
- Two decisions on one request can both land, and two requests can both wait at the same time (section 6.1).
- The preview counts nothing, although obligations now exist (commit 51f9efa).
- The name.

## 2. The name everywhere people see it

**What changes:** every string a user can see. That is the nav entry, the H1 and lede, the onboarding step, the Today empty state, the banners, dialogs and history lines, the permission descriptions on the roles screen, the approver role's usage text, the prototype, the design cards and the future list filters.

**What stays.** None of the following is user copy, and renaming it would touch contracts, migrations, audit history and tests without helping any user:
- the code identifiers (`footprint_*`, `FootprintScreen`, `features/footprint`, `data-footprint-*`)
- the message keys (`footprint.*`)
- the permission keys `footprint.request` and `footprint.approve`. The roles editor and the restricted page show them humanised, as "footprint request" and "footprint approve".
- the API paths `/api/v1/tenant/footprint*`
- the tables and the audit action names
- the onboarding step key `footprint`
- the route `/admin/footprint`
- the FP requirement IDs and scenario IDs

Two things stay visible: the route and the humanised permission names. The description line on the roles screen ("Request a regulatory scope change.") connects the permission name to the new one. Renaming the route would need a redirect and would not help anyone reading the page today.

**Strings.** Keys stay the same and only the values change. New keys are marked "(new)".

| Key | en | sv |
|---|---|---|
| `nav.admin.footprint`, `footprint.title` | Regulatory scope | Regulatorisk omfattning |
| `footprint.lede` | Which rules apply to us, what we do and for whom | Vilka regler som gäller för oss, vad vi gör och för vem |
| `footprint.rule` (new) | Changes apply to every member once someone else approves them with a passkey. | Ändringar gäller alla medlemmar när någon annan har godkänt dem med sin nyckel. |
| `footprint.propose` (new) | Propose a change | Föreslå en ändring |
| `footprint.term.in` / `.out` (new, visually hidden) | In our scope / Not in our scope | I vår omfattning / Inte i vår omfattning |
| `footprint.notRestricted` | Not restricted: every option applies. | Ingen begränsning: alla alternativ gäller. |
| `footprint.pending.add` / `.remove` (new, warning pills) | Added when approved / Removed when approved | Läggs till vid godkännande / Tas bort vid godkännande |
| `footprint.request.add` / `.remove` / `.addAndRemove` | Add {adds} / Remove {removes} / Add {adds}, remove {removes} | Lägg till {adds} / Ta bort {removes} / Lägg till {adds}, ta bort {removes} |
| `footprint.preview.title` / `.untitled` (new) | Your change: {title} / Your change | Din ändring: {title} / Din ändring |
| `footprint.draft.nothing` (new) | Nothing changed yet. | Inget ändrat ännu. |
| `footprint.preview.hidesForAll` (new) | What this hides leaves the feed, the inventory, the roadmap and the briefing for every member. | Det som döljs försvinner för alla medlemmar ur flödet, inventariet, färdplanen och briefingen. |
| `footprint.preview.narrows` (new) | {group} will start to filter: records tagged only with other options in it are hidden from every member. | {group} börjar filtrera: poster som bara har andra alternativ i gruppen döljs för alla medlemmar. |
| `footprint.preview.send` | Request approval | Begär godkännande |
| `footprint.banner.youRequested` | You requested this on {date}. | Du begärde detta {date}. |
| `footprint.banner.blocks` (new) | No other change can be proposed until this one is decided. | Ingen annan ändring kan föreslås förrän den här är avgjord. |
| `footprint.fourEyes` | You requested this change, so someone else has to approve it. | Du begärde ändringen, så någon annan måste godkänna den. |
| `footprint.approvedDone` | Approved. The regulatory scope has changed. | Godkänt. Den regulatoriska omfattningen har ändrats. |
| `footprint.errorTitle` | Could not load the regulatory scope | Kunde inte läsa in den regulatoriska omfattningen |
| `today.empty.body` | Upcoming dates and the weekly briefing appear here once the regulatory scope is set and the first sources have been checked. | Kommande datum och veckans briefing visas här när den regulatoriska omfattningen är satt och de första källorna har kontrollerats. |
| `today.empty.action` | Set the regulatory scope under Admin | Sätt den regulatoriska omfattningen under Admin |
| `admin.organisation.step.footprint` | Set the regulatory scope | Sätt den regulatoriska omfattningen |
| List filters (FP-03 screens, later) | Show outside our scope · Outside our scope | Visa utanför vår omfattning · Utanför vår omfattning |

**Deleted keys.** These seven leave the page and the catalogs because they restate rules the page already shows (playbook 6.5): `footprint.readOnly`, `footprint.pendingReadOnly`, `footprint.dimensionNote`, `footprint.preview.secondPerson`, `footprint.preview.discard` (Cancel uses `common.cancel` instead), `footprint.banner.waiting` and `footprint.approve.body`.

**All other `footprint.*` values** drop "footprint", "avtryck" and "fotavtryck" in the same way. Swedish keeps the words the app already uses: "nyckel" for passkey and "revisionsloggen" for the audit log. The passkey prompts use "fingeravtryck", which is unrelated and stays.

## 3. Who sees what

| Person | Admin nav entry | `/admin/footprint` | Propose a change | Approve / reject | Withdraw |
|---|---|---|---|---|---|
| Admin, Compliance officer (`request` + `approve`) | yes | read, propose, decide | yes, while nothing waits | yes, never their own | their own |
| Approver (`approve` only) | yes | read and decide | no | yes, never their own | n/a |
| Custom role with `request` only | yes | read and propose | yes, while nothing waits | no | their own |
| Owner, Contributor, Reader, Auditor | no | restricted page | no | no | no |

- **These rules already exist.** The route gate (`registry.ts` `FOOTPRINT_PERMISSIONS`, `AdminGate`), the server gates (`requires_permission`, `requires_step_up`), four eyes (409 `four_eyes_violation` plus `footprint_change_request_four_eyes`) and withdraw-by-requester-only (403) are all built.
- **Reading stays open.** `GET /tenant/footprint` and `GET /tenant/footprint/requests` stay readable by every member (`UNGATED_BY_DESIGN`, FP-03), because the filtered surfaces need the scope. "Not accessible to an ordinary user" means they cannot open the page or change anything.
- **Where other members meet the scope.** Members without the permissions see the scope only where FP-03 filters lists ("Show outside our scope", "Outside our scope"), once those screens exist. No summary page is added for them.
- **Auditors** read the `footprint.*` events in the audit log. Each per-term event now names its request (section 6.1).

## 4. The page

### 4.1 How the page shows it is restricted

The page reads as serious because of how it behaves, not because of new colours:
- It is restricted.
- It opens read-only.
- A change needs a second person and a passkey.
- The one action that starts a change is a danger button.

There are no new variants, no red frame and no typed confirmation. NN/g warns that people stop reading warnings they see everywhere, and Stripe and Green keep red for destructive actions and errors.

| Element | Part | Tone / token |
|---|---|---|
| The rule, `footprint.rule`, under the page head while nothing waits | `Notice` (plain) | `subtle` fill, neutral text |
| "Propose a change" in the `PageHead` actions | `Button variant="danger"` | `content-negative-01` on the surface (6.04 light, 7.09 dark). Hover is `l3-negative-02` in light and `l3-negative-03` in dark, through a new token `--color-negative-hover`. Dark text on `-02` is 4.47:1, which fails. |
| Options in the read state | a checkbox-shaped glyph and the label | neutral: box `border-line-strong`, tick and label `text-fg` |
| Options in the edit state | `CheckGroup` + `CheckRow` (native checkbox) | neutral |
| A term that a waiting request adds or removes | `Pill` `warning`, "Added when approved" / "Removed when approved" | `warning` |
| Pending banner | `Notice tone="warn"` | `warning` |
| The consequence notice in the change panel and in the approve dialog | `Notice tone="warn"` | `warning` |
| Four-eyes refusal | `Notice tone="bad"` (role `alert`) | `negative` |
| Reject | `Button variant="danger"` | `negative` text |
| Request approval, Approve with passkey | `Button` primary | neutral |
| Sent, Approved, Rejected, Withdrawn | the status line (section 4.3) | `positive` |

These rules are added to foundations.md as the "Restricted setting" pattern:
- **One warn notice at most above the groups:** the pending banner. The rule notice is hidden while the banner shows.
- **All text inside a warn notice is `text-fg`.** In dark mode, muted text on `l3-warning-02` is 3.62:1 and negative text is 3.24:1. An error from a banner button renders under the banner.
- **The change is stated in plain text,** as the request title. It never uses coloured `ins`/`del` marks, because dark negative text on `l3-negative-02` fails AA.

### 4.2 Groups and options

- **Read state.** This covers the default view, the approve-only view, and everything while a request waits.
  - Each group is a heading and a list of every active term.
  - Each term shows a 16 px checkbox-shaped glyph (inline SVG, `aria-hidden`), ticked when held and empty when not. Next to it is the label in body text, plus visually hidden text: "In our scope" or "Not in our scope".
  - These are not form controls. The browser greys nothing out, nothing sits in the tab order, and both held and unheld terms stay visible (Green `gds-checkbox`, read-only).
  - A group with no held term shows one body line instead of its list: "Not restricted: every option applies."
- **Edit state.** This starts after "Propose a change".
  - There is one `CheckGroup` per group. The legend is taken from the dimension row, in the reader's language. Options are stacked; Green's checkbox groups are vertical by default and need a header label.
  - `CheckGroup` renders its hint directly under the legend and links it with `aria-describedby` (section 8, T05).
  - Whenever the draft leaves a group empty, the hint is "Not restricted: every option applies.", so the rule is heard before the options.
  - `disabled` is used only while the request is being sent.
- **Layout, in both states.** One column on phones, two from `md` and three from `xl`, all inside one Panel. Each group wrapper keeps `data-dimension="{key}"`.
- **Which dimensions show.** A dimension shows if it restricts (`restrictsFootprint`) and has at least one active term. This rule is `scopeGroups()`, a presentation function with no API change.
  - Channel, lifecycle stage and theme never show.
  - `licensed_activity`, `product_type` and `jurisdiction` show once they have terms.
  - The design card's "Channels" group goes.
- **Order.** By dimension `sort_order`, then by term `sort_order`. This is unchanged.
- **Pending marks.** While a request waits, each term it adds or removes carries the `warning` pill "Added when approved" or "Removed when approved" (`pendingTermPill()`). Both labels join the Computed row in pills-and-labels.md.
- **An empty group means no restriction** (FP-01, `matching.py`).
  - Emptying a group widens the scope, which is the safe direction. It gets no warning; the group's hint says what empty means.
  - Ticking the first term in an empty group narrows the scope, which is the dangerous direction. It gets a warning (section 4.3).
- **Markets.** The `jurisdiction` dimension already restricts and has no terms. Once the parallel operating-markets work gives it terms ("Terms mirror the jurisdiction table"), it renders as a group like any other, with no change needed here.
  - Matching is flat, though. Ticking only Sweden would hide every EU-level record, so that work has to decide how the Union relates to its member states (see the open questions).
  - Watched markets stay out of this section.
- **Usage notes are not shown.** They are single-language guidance for editors and agents.

### 4.3 Proposing a change

1. Holders of `footprint.request` see "Propose a change" in the page head while nothing waits.
2. Choosing it hides that button and turns the groups into checkboxes. Focus moves to the first checkbox, and the change panel (`data-draft-preview`) appears under the groups and stays for the whole edit. Nothing is written yet.
3. The change panel contains:
   - **Title:** "Your change" while nothing differs, then "Your change: {Add …, remove …}". The title comes from `requestTitle` and is the one statement of the change. While nothing differs, the body reads "Nothing changed yet."
   - **Preview:** a dry run on each change of the draft (`POST …/requests?dryRun=true`; nothing is stored or audited), shown in the existing "Hides" / "Reveals" columns. Obligations are counted (section 6.2). Cases read "not counted yet" until chunk 9.
   - **One warn notice,** only when the counted part hides something or the draft narrows a group. It shows `footprint.preview.hidesForAll`, plus one line per narrowed group from `narrowedGroups()`: "{group} will start to filter: …".
   - **Buttons,** right-aligned. "Cancel" (outline) is always there, and "Request approval" (primary) appears once the draft differs. Cancel clears the draft, leaves edit mode and returns focus to "Propose a change". It is the only cancel on the page during an edit.
4. "Request approval" posts `{adds, removes}`. On success the draft clears and the page shows the pending state.

**Status and focus** (sections 4.3 to 4.7):
- One status line (role `status`, `tabIndex=-1`) is always mounted under the page head, empty until used.
- After a send, an approval, a rejection or a withdrawal, the message goes into it and focus moves to it. On a phone, the focus move also scrolls it into view. The messages are "Sent for approval.", "Approved. The regulatory scope has changed.", "Rejected." and "Withdrawn.".
- A dialog that closes must not try to return focus to a banner button that no longer exists.

**Conflicts** keep their messages: 409 `request_pending` (someone else sent a request first), `stale_write` and `invalid_transition`.

### 4.4 Pending

- **What the page shows.** The rule notice hides. The banner (`Notice warn`, `data-pending-request`) sits under the status line. The groups show in the read state with their pending pills, and "Propose a change" is hidden.
- **The banner's first line:** the `warning` pill "Waiting for approval" and the request title in bold.
- **The second line depends on who is looking:**
  - The requester sees "You requested this on {date}."
  - Anyone else sees "Requested by {name}, {date}." and the preview summary, counted when the page reads it (section 6.2).
  - Holders of `footprint.request` also see "No other change can be proposed until this one is decided."
- **"See the preview"** is a text-style disclosure (a ghost button with `aria-expanded`) on its own line. It opens the Hides / Reveals panel under the banner.
- **Actions** sit in one right-aligned row (`ButtonBar` default, no `justify-start`), with at most two buttons (playbook 6.8):
  - The requester gets "Withdraw".
  - A holder of `footprint.approve` who is not the requester gets "Reject" (outline, left) and "Approve" (primary, right).
  - A holder of `request` only gets no buttons.
- **A Withdraw error** renders under the banner (section 4.1).

### 4.5 Approve

- **The dialog.**
  - The title is "Approve "{title}"?".
  - The description is one sentence: the preview summary.
  - Under it come the warn notice from section 4.3 (when the change hides something or narrows a group), then the four-eyes refusal if the server sends one, then "Cancel" and "Approve with passkey".
- **Step-up.** This is unchanged. The API answers 403 `step_up_required`, and the client opens the passkey prompt and retries. An assertion from the last `STEP_UP_FRESHNESS_MINUTES` counts (ID-06).
- **Four eyes.** The requester never sees Approve. The server answers 409, and the check constraint refuses the row.
- **On approval,** each term gets:
  - one `footprint_term` change
  - one `footprint_history` row
  - one audit event, carrying the step-up assertion id (existing) and the request id (new)
  
  The `footprint.change_approved` event also stores the counts it was approved against in `after.preview` (new).

### 4.6 Reject

A dialog asks for a required reason ("Shown to the requester and kept in the audit log."). The button is "Reject" in the `danger` variant. There is no step-up, because rejecting changes nothing.

New:
- The text area carries `aria-describedby` for its hint and its error, `aria-invalid` when blank, and `aria-required`.
- A blank submit moves focus to the text area.

### 4.7 Withdraw

Only the requester can withdraw; anyone else gets a 403. It takes one click with no confirmation, because the change can be proposed again.

### 4.8 History

`data-footprint-history` lists decided requests, newest first. Each line shows when, who decided, the verb, the title, "requested by {name}", and the rejection note when there is one. Anyone who can open the page sees it.

### 4.9 Without the permissions

- **Navigation.** There is no Admin entry for Regulatory scope. `/admin` itself stays hidden unless another admin permission unlocks it.
- **Direct link.** Opening `/admin/footprint` directly shows the restricted page: "This page is not available to you", with "Needs footprint request", the same name the roles editor uses.
- **Today's empty state.** The body says "…once the regulatory scope is set…". The action "Set the regulatory scope under Admin" links to `/admin/footprint` and shows only to holders of either permission. Today it sends everyone to `/admin`, including readers who cannot open it.
- **List screens** (FP-03, later) get "Show outside our scope", and rows outside the scope are marked "Outside our scope".

### 4.10 Loading and error

As today: a skeleton row while loading, and "Could not load the regulatory scope" with Try again on error.

## 5. Vocabulary: Banking and Payments

PRD 0.2 names banking and payments first in the sector scope, but the regime list has neither. Two regime terms are added at the end of the list, so nothing else moves:

| Term | en / sv | Order |
|---|---|---|
| `regime:banking` | Banking / Bankverksamhet | 7 |
| `regime:payments` | Payments / Betalningar (FI's own area name) | 8 |

- **Where the rows go.** In `taxonomy_terms` of `backend/apps/library/fixtures/prototype_data.json`, with `from_prototype: false`. There is precedent: `lifecycle_stage:onboarding`. `check_prototype_data.py` must still pass.
- **Usage note.** The fixture's `regime` usage note becomes "The body of law: banking, payments, securities, insurance, tax, data protection, AML, AI and ICT."
  - Usage notes are written only once, so this reaches fresh databases only.
  - IMPLEMENTATION_STATUS shows no deployed library yet; the first test deploy comes after chunk 7.
  - If a library is deployed before this lands, it gets the note through a relabel proposal (VOC-07).
- **The seed must not undo proposals.**
  - The problem: `seed_taxonomy_terms` runs on every deploy. Today it re-applies `sort_order` and `active=True` to every existing term and writes no audit row, so it would silently undo an approved `term_update` proposal.
  - The fix: it writes `sort_order`, `is_system` and `active` only when it creates a term. For each term it creates, it records `taxonomy.term_created` with the system actor `seed_reference`, the same way the library seed records `library.seeded`.
- **Tenants.** New terms start unticked.
  - The fixture's `example-group` and E2E tenant A (`EXPECTED_FOOTPRINTS`) get `regime:banking` and `regime:payments`.
  - Tenant B stays small for J-8.
  - No record carries the new terms yet, so nothing is hidden anywhere.
- **Unchanged:** every existing key, label and order, the other dimensions, and `licensed_activity` (termless, and not on the page).

## 6. Data and API

### 6.1 One decision per request, one request at a time (T02)

**Lock the request before deciding.**
- `approve`, `reject` and `withdraw` load the request with `select_for_update(of=("self",))`, then check status and version under the lock. The `of=("self",)` is needed because `decided_by` is a nullable join, and PostgreSQL refuses `FOR UPDATE` on the nullable side of an outer join.
- What goes wrong today: the check runs in Python on an unlocked row. An approve and a withdraw can both pass, so the scope changes but the request ends up "withdrawn". Two approvals write every term's history row and audit event twice.
- After the fix, the second decision gets 409 `invalid_transition`, or `stale_write` when its If-Match is behind. If-Match stays optional (playbook 4.3).

**Allow only one waiting request per tenant.**
- Add a partial unique constraint `footprint_change_request_one_pending` on `(tenant)` where `status = 'pending'`, in the model's `Meta.constraints` and in migration 0002.
- `create_request` inserts inside a savepoint and maps the `IntegrityError` to 409 `request_pending`.
- Today two requests sent at the same moment can both end up waiting.

**Link each term event to its request.** `footprint.term_added` and `footprint.term_removed` carry `"request": "<id>"` in `after` / `before` whenever a request caused them. The audit log then connects each term to its request without matching step-up ids.

**Tests:**
- A concurrency test on two connections, for approve against withdraw and for approve against approve. Exactly one succeeds, and only one set of history rows and audit events exists.
- The database refuses a second pending row.
- Each per-term event names its request.
- A new scenario, FP-S6, in app.md.

### 6.2 The preview counts obligations (T03)

- **Counting.** `preview_of` counts the obligations the tenant can see: shared ones and its own, under RLS.
  - Hidden means in scope now and not in scope after the change. Revealed is the reverse.
  - The count uses the pure function `matching.in_footprint` over each obligation's terms plus its instrument's regime. The SQL function cannot be used, because it reads the stored scope. Results carry `available: true`.
  - Cases stay `available: false` until chunk 9.
- **Pending requests are recounted.** `request_row` recounts the preview of a pending request every time it is read, so the approver sees counts against today's library. Decided requests keep their stored preview.
- **Approval stores the counts.** `approve` writes them into the `footprint.change_approved` event's `after.preview`.
- **Performance.** One query fetches the obligations' terms, and the counting happens in memory. `GET /tenant/footprint` must stay under the 250 ms budget on the seeded data (`Server-Timing: app`).
- **Contract.** There is no schema or route change, so `openapi.json` and `api.generated.ts` do not change.
- **Logging.** Only preview counts and term keys; no tenant content.

## 7. Permissions

- No new permission keys, and the PRD §6 matrix is unchanged. Route and server gates are unchanged.
- The descriptions on the roles screen change:
  - `footprint.request`: "Request a regulatory scope change."
  - `footprint.approve`: "Approve a regulatory scope change requested by someone else."
- The approver role's usage text becomes "Signs off cases and approves regulatory scope and applicability decisions. Never the requester." New tenants get it; existing tenants' role rows are theirs to edit.
- `humanisePermission` does not change, so the restricted page names the same permission the roles editor shows.

## 8. What changes where

- **Prototype** (`design/prototype/index.html`, T11):
  - The Footprint card leaves Settings. Sara, Maria and Erik get a "Regulatory scope" link there; Johan gets nothing.
  - A new `scope` view implements sections 4.1 to 4.4 with a small permission map: Sara and Erik can request and approve, Maria can approve, and Johan has neither.
  - The view has the rule notice, the read-state glyph lists, "Propose a change" (btn danger), `.check` rows, the change panel with Hides / Reveals counted from the prototype's own data, and "Request approval", which leaves a static pending banner with Withdraw.
  - Approval, rejection and history are left to the app and the design card.
  - `REGIMES` gains Banking and Payments.
  - `any()` and `oblInFoot` treat an empty group as no restriction (FP-01). Today both hide everything in that group.
  - The immediate `fp` toggle is removed.
- **Design cards:**
  - `admin-footprint.html` is restyled to the foundations and titled "Screen card: regulatory scope with change requests (/admin/footprint)". It shows every state in section 4 (T12, T13).
  - The other cards change wording only (T14).
- **Shared UI primitives** (T05):
  - The danger button gets its dark-mode hover token.
  - The `PageHead` actions wrapper gets `ml-auto`, so an action that wraps stays on the right on phones.
  - `CheckGroup` puts its hint under the legend, linked with `aria-describedby` via `useId`. The three existing callers keep their copy.
  - `CheckRow` is unchanged.
- **App:**
  - `footprint-presentation.ts` gains `scopeGroups`, `narrowedGroups` and `pendingTermPill` (T06).
  - `FootprintScreen.tsx` gets the read and edit states, the change panel, the status line and focus handling, the banner layout and the dialogs (T07 to T09).
  - `TodayScreen.tsx` shows the link only to permission holders (T10).
  - The catalogs change as in section 2 (T04).
  - `Chip` stays, because the list filters use it.
- **E2E journeys** (`frontend/tests/e2e/`):
  - **FP-S2 and FP-S5 (J-6)** in `taxonomy.journey.spec.ts`:
    - The H1 reads "Regulatory scope".
    - Before "Propose a change", no checkbox named Advice exists inside `[data-dimension="service_type"]`, and its list item reads "In our scope".
    - After it, the test calls `uncheck()` on Advice. The panel reads "Your change: Remove Advice", and the Hides column shows an obligation count.
    - The test clicks "Request approval", and "Sent for approval." has focus.
    - While the request is pending, the Advice item shows "Removed when approved".
    - The approver sees the banner and decides.
    - After approval and a reload, the Advice item reads "Not in our scope".
    - The restore path in `finally` goes through the same door.
  - **New FP-S7:**
    - A reader has no nav entry and gets the restricted page at `/admin/footprint`.
    - An approver sees no checkbox and no "Propose a change".
    - At 375 px wide, the page does not scroll sideways.
  - **`shell.journey.spec.ts`:** the reader no longer sees the "Set … under Admin" link.
  - **`tenants.journey.spec.ts`** keeps `data-step="footprint"`.
- **Scenarios** (`backend/apps/taxonomy/app.md`):
  - In FP-S2, FP-S4 and FP-S5, the prose says "remove" instead of "switch off" and "regulatory scope" instead of "footprint".
  - New FP-S6: one decision per request and one pending request per organisation (`@integration`).
  - New FP-S7: members without scope permissions cannot open the page (`@e2e`).
- **Docs** (T15):
  - `design/README.md` rewords the "Footprint toggles apply at once" row.
  - `foundations.md` adds the Restricted setting pattern and the dark danger hover, and drops "footprint" from the Toggle line.
  - `pills-and-labels.md` adds the two pending labels.
  - `docs/TODO_FOR_alex.md` and `docs/plans/Verification_Log.md` get the entries listed in T15.

## 9. Out of scope, for later

- A reason on each request (open question; not added).
- A read-only scope summary for members without the permissions.
- More regimes or firm types (Funds; payment institutions, e-money institutions, investment firms, occupational pension companies) and relabelling "AI and ICT" (open questions).
- A row on Today for a waiting approval (chunk 6 builds Today's attention items).
- Jurisdiction matching that understands the Union and its member states (the markets work).
- A "New in the library" marker on terms added after a tenant's last scope change.
- Watched markets (a watch setting, not part of the scope).
- Renaming the route.

## 10. Vocabulary and permission changes, in short

- New regime term regime:banking: en 'Banking', sv 'Bankverksamhet', sort_order 7, from_prototype false, in the fixture's taxonomy_terms
- New regime term regime:payments: en 'Payments', sv 'Betalningar' (FI's own area name), sort_order 8, from_prototype false
- Fixture regime dimension usage note becomes 'The body of law: banking, payments, securities, insurance, tax, data protection, AML, AI and ICT.' (fresh databases; no library is deployed yet, and a deployed one would get it by a relabel proposal, VOC-07)
- Fixture footprint_terms for tenant example-group adds regime:banking and regime:payments; E2E EXPECTED_FOOTPRINTS for tenant A adds the same two; tenant B unchanged
- seed_taxonomy_terms writes sort_order, is_system and active only when it creates a term (it no longer re-applies them on every deploy, which would undo an approved term_update proposal) and records taxonomy.term_created for each term it creates
- No key renamed, removed, reused or reordered; ai_ict keeps 'AI and ICT'; legal_entity, service_type, account_type and client_category are unchanged
- Presentation only: the scope page shows dimensions that restrict and have active terms, so channel, lifecycle_stage, theme and the termless licensed_activity, product_type and jurisdiction are not shown; jurisdiction appears once it has terms

- No new permission keys and no change to the PRD §6 role matrix: footprint.request (Admin, Compliance officer) and footprint.approve (Admin, Compliance officer, Approver) stay as they are
- No change to route or server gates: /admin/footprint stays gated by anyOf footprint.request / footprint.approve; approve still needs footprint.approve plus the passkey step-up; reject needs footprint.approve; withdraw is requester-only; GET /tenant/footprint and GET /tenant/footprint/requests stay readable by every member (FP-03, UNGATED_BY_DESIGN)
- Four eyes hardened without a permission change: decisions lock the request row, and the database allows one pending request per tenant (spec §6.1)
- PERMISSION_DESCRIPTIONS relabel (the hint on the roles screen): footprint.request -> 'Request a regulatory scope change.'; footprint.approve -> 'Approve a regulatory scope change requested by someone else.'
- Approver system-role usage text: 'approves footprint and applicability decisions' becomes 'approves regulatory scope and applicability decisions' for new tenants; existing tenant role rows keep their text
- humanisePermission unchanged: the restricted page keeps naming 'footprint request', the same name the roles editor shows
- UI only: 'Propose a change' shows to holders of footprint.request while nothing waits; Reject and Approve show to holders of footprint.approve who are not the requester; Withdraw shows to the requester; the Today empty-state link to /admin/footprint shows only to holders of either permission

## 11. Tasks

Each runs in its own worktree (`docs/runbooks/WORKTREES.md`). T01 waits for chunk3-rest-T2 (same seed files), T02 for chunk4-T2 (same taxonomy models and migration number), T03 is the same work as chunk3-rest-T7 (footprint preview counts), so it is built once, as chunk3-rest-T7, and T08 waits for that, and the screen for the tab bar and chunk3-rest-T5 (shell and message catalogs).

### T01: Seed Banking and Payments, and stop the seed undoing proposals

**Added 2026-09-19 (found by chunk4-T2):** the same fault exists for every library vocabulary list, not only taxonomy terms. `seed_reference` resets sort order, the active flag and the default of library list rows on every deploy, so an approved reorder, retire or default change is undone by the next deploy. T01 applies the same rule to those rows: write sort order, active and default only when the seed creates the row, and prove with a test that an approved reorder survives a second seed run. The security review of chunk4-T2 also found that `seed_library_vocabularies` writes library rows without an audit row, unlike `seed_authorities`; T01 records a `record()` event (system actor `seed_reference`) for each library list row the seed creates.

**Depends on:** nothing

In the prototype fixture's taxonomy_terms, add regime:banking (Banking / Bankverksamhet, sort_order 7) and regime:payments (Payments / Betalningar, sort_order 8), both from_prototype false. Change the fixture's regime usage note as in spec §5. Add both terms to example-group's footprint_terms (added_by erik, same added_at as the others) and to tenant A in EXPECTED_FOOTPRINTS in e2e_seed.py. In seeds/__init__.py, seed_taxonomy_terms writes sort_order, is_system and active only when it creates a term, and records taxonomy.term_created (system actor seed_reference; after carries dimension, key and labels) for each term it creates, as the library seed does with library.seeded. Add tests: seeding creates both keys with en and sv labels and keeps every earlier (dimension, key); a second run creates and records nothing; a term whose sort_order changed after seeding keeps it on the next run.

**Owned paths:**

- `backend/apps/library/fixtures/prototype_data.json`
- `backend/apps/taxonomy/seeds/__init__.py`
- `backend/apps/taxonomy/tests_vocabulary.py`
- `backend/apps/shared/e2e_seed.py`

**Done when:** check_prototype_data.py passes. The new seed tests and the full backend suite pass. The fixture diff is two terms, two footprint rows and one usage note; no key is renamed, removed or reordered.

### T02: One decision per request, one waiting request per organisation

**Depends on:** nothing

api.py _footprint_request takes a lock flag. approve, reject and withdraw load the row with select_for_update(of=('self',)), because decided_by is a nullable join, and _decidable re-checks status and version under the lock. If-Match stays optional. Add a partial UniqueConstraint footprint_change_request_one_pending on (tenant) where status='pending' in FootprintChangeRequest.Meta, with migration 0002. create_request inserts inside transaction.atomic() and maps IntegrityError to ValidationError code request_pending (409). _switch_on and _switch_off add 'request': str(request.id) to after/before when a request exists. Add tests_footprint.py: a TransactionTestCase with two connections for approve vs withdraw and approve vs approve, where exactly one succeeds and exactly one history row and one audit event exist per term; the database refuses a second pending row. In app.md, add FP-S6 (@integration) with its test in tests_scenarios.py, and in FP-S2, FP-S4 and FP-S5 say 'remove' for 'switch off' and 'regulatory scope' for 'footprint' in the prose. Never log tenant content.

**Owned paths:**

- `backend/apps/taxonomy/models.py`
- `backend/apps/taxonomy/migrations/`
- `backend/apps/taxonomy/footprint_logic.py`
- `backend/apps/taxonomy/api.py`
- `backend/apps/taxonomy/tests_footprint.py`
- `backend/apps/taxonomy/tests_scenarios.py`
- `backend/apps/taxonomy/app.md`

**Done when:** makemigrations --check is clean and migrate_from_zero passes. In the race tests, exactly one decision lands and the other answers 409. A second pending insert raises IntegrityError, and the API answers 409 request_pending. Per-term audit events name their request. FP-S3 and the existing four-eyes, If-Match and route-permission tests pass unchanged.

### T03: The preview counts the obligations a change hides and reveals

**Depends on:** T02

preview_of counts the obligations visible to the tenant (shared and its own, under RLS). Hidden means in scope now and not after the change; revealed is the reverse. The count uses matching.in_footprint over each obligation's terms plus its instrument's regime, with the restricting dimensions, and sets available true. One query fetches the obligation terms and the counting happens in memory. Cases stay available false until chunk 9. request_row recounts the preview for a pending request when it is read; decided requests keep the stored preview. approve passes the counts to _decide, which writes them to footprint.change_approved after.preview. The FP-S2 integration test asserts that removing Advice hides the fixture's advice-only obligations.

**Owned paths:**

- `backend/apps/taxonomy/footprint_logic.py`
- `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** The FP-S2 integration test asserts real obligation counts with available true. A test shows that a pending request's preview reflects a library change made after the request. change_approved carries after.preview. The OpenAPI drift check is clean, and GET /tenant/footprint stays under API_BUDGET_MS on the seeded data.

### T04: Footprint becomes Regulatory scope in every string people read

**Depends on:** nothing

Change the en and sv values, keeping the keys, as in spec §2: nav.admin.footprint, footprint.title, footprint.lede, footprint.request.*, footprint.preview.send, footprint.banner.youRequested, footprint.fourEyes, footprint.approvedDone, footprint.errorTitle, footprint.notRestricted, today.empty.body, today.empty.action, admin.organisation.step.footprint. Every other footprint.* value that says footprint, avtryck or fotavtryck loses the word, including values that T07 to T09 delete later. Relabel PERMISSION_DESCRIPTIONS for footprint.request and footprint.approve, and the approver entry in TENANT_ROLE_USAGE. Update the text the tests read: the H1, 'Request approval', 'Remove Advice' and 'Approved. The regulatory scope has changed.' in taxonomy.journey.spec.ts; the link name in shell.journey.spec.ts; the titles in footprint-presentation.test.ts.

**Owned paths:**

- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/taxonomy.journey.spec.ts`
- `frontend/tests/e2e/shell.journey.spec.ts`
- `frontend/src/features/footprint/footprint-presentation.test.ts`
- `backend/apps/shared/permissions.py`
- `backend/apps/identity/roles_logic.py`

**Done when:** No value in en.json or sv.json matches /footprint|(?<!finger)avtryck/i. The passkey prompts are untouched. npm run check:messages, the unit tests, the backend tests, and the taxonomy and shell journeys pass.

### T05: Primitives: dark danger hover, head actions on the right, group hint under the legend

**Depends on:** nothing

Add --color-negative-hover (l3-negative-02 in light, l3-negative-03 in dark) to theme.css, and use it for the danger variant's hover in Button.tsx. Add 'negative on danger hover' to PAIRS in contrast.test.ts for both themes. Add ml-auto to the PageHead actions wrapper, so a wrapped action stays on the right on phones. CheckGroup gets an id from useId, renders its hint directly under the legend, and sets aria-describedby on the fieldset to the hint; the error keeps role alert. CheckRow is unchanged. Nothing is passed through as data-* attributes.

**Owned paths:**

- `frontend/src/styles/theme.css`
- `frontend/src/styles/contrast.test.ts`
- `frontend/src/components/ui/Button.tsx`
- `frontend/src/components/ui/PageHead.tsx`
- `frontend/src/components/ui/Field.tsx`
- `frontend/src/components/ui/primitives.test.tsx`

**Done when:** contrast.test.ts passes with the new pair in light and dark. A primitives test shows the CheckGroup hint comes before the first option and is referenced by the fieldset's aria-describedby. The API keys and members journeys pass. No copy changes.

### T06: Presentation rules for scope groups

**Depends on:** T04

Add three functions to footprint-presentation.ts. scopeGroups(dimensions, terms) keeps dimensions that restrict and have at least one active term, in dimension order, with rows {term, held}. narrowedGroups(dimensions, draft) returns the groups that are empty in the stored scope and non-empty in the draft. pendingTermPill(kind, t) returns the warning pill (slotTone.waitingForApproval) with the label 'Added when approved' or 'Removed when approved'. Add the catalog keys footprint.pending.add, footprint.pending.remove and footprint.preview.narrows in en and sv. Unit tests: channel, lifecycle_stage, theme and termless dimensions are excluded; narrowing is detected and widening is not; the pill's tone is warning.

**Owned paths:**

- `frontend/src/features/footprint/footprint-presentation.ts`
- `frontend/src/features/footprint/footprint-presentation.test.ts`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`

**Done when:** Vitest passes with the new cases. The screen does not change yet.

### T07: Read state by default; checkboxes only after Propose a change

**Depends on:** T05, T06

FootprintScreen replaces the Chip rows with scopeGroups(), in a grid of one column on phones, two from md and three from xl. Each group wrapper keeps data-dimension. Read state: a list per group; each term has a 16 px checkbox-shaped inline SVG (aria-hidden, ticked or empty), the label, and a visually hidden footprint.term.in or footprint.term.out. A group with nothing held shows footprint.notRestricted as one body line. Pending terms carry pendingTermPill. Edit state: CheckGroup and CheckRow per group, with footprint.notRestricted as the hint when the draft leaves a group empty. The plain Notice with footprint.rule shows while nothing waits. The 'Propose a change' danger Button in the PageHead actions (footprint.request, nothing waiting) hides itself, enables editing and focuses the first checkbox. Delete footprint.readOnly, footprint.pendingReadOnly and footprint.dimensionNote from the screen and the catalogs. The existing draft panel keeps working. The E2E helpers in FP-S2 and FP-S5 click 'Propose a change' and uncheck the Advice checkbox, and assert that no Advice checkbox exists before that.

**Owned paths:**

- `frontend/src/components/admin/FootprintScreen.tsx`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:** FootprintScreen no longer imports Chip. Before 'Propose a change', the page has no checkbox. Channel, lifecycle stage, theme and termless dimensions do not render. While a request waits, the Advice item shows 'Removed when approved'. FP-S2 and FP-S5 pass.

### T08: The change panel, the status line and focus

**Depends on:** T07, T03

The change panel shows for the whole edit. Its title is footprint.preview.untitled until the draft differs, then 'Your change: {requestTitle}'. Until then the body is footprint.draft.nothing. Once the draft differs, it shows the dry-run Hides and Reveals columns and one warn Notice, only when counted hides are above zero or narrowedGroups() is non-empty, with footprint.preview.hidesForAll plus one footprint.preview.narrows line per group. Cancel (common.cancel, outline) is always shown, and Request approval (primary) once the draft differs; the head action stays hidden during the edit. Cancel returns focus to 'Propose a change'. Delete footprint.preview.secondPerson and footprint.preview.discard. Add one always-mounted status line (role status, tabIndex -1) under the PageHead; after a send, write the message and focus it. Add FootprintScreen.test.tsx.

**Owned paths:**

- `frontend/src/components/admin/FootprintScreen.tsx`
- `frontend/src/components/admin/FootprintScreen.test.tsx`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:** The component test shows three things: after a send, document.activeElement is the status line reading 'Sent for approval.'; the warn notice renders for a narrowing draft and not for a widening one; exactly one cancel button exists during an edit. FP-S2 and FP-S5 pass against the real API, and FP-S2 asserts an obligation count in the Hides column.

### T09: Pending banner, approve and reject dialogs

**Depends on:** T08

Banner per spec §4.4: the pill and the title; the second line by viewer; footprint.banner.blocks for holders of footprint.request; 'See the preview' as a ghost disclosure with aria-expanded on its own line; one right-aligned action row with at most two buttons (drop justify-start). Withdraw errors render under the banner, and only text-fg is used inside it. Approve dialog: the description is previewSummary only; the warn notice (hidesForAll and narrows lines) goes in the children; the four-eyes bad notice stays; delete footprint.approve.body and footprint.banner.waiting. Reject dialog: the text area gets aria-describedby for its hint and error, aria-invalid when blank and aria-required, and a blank submit focuses it. After approve, reject or withdraw, write the message to the status line and focus it, so no dialog returns focus to a trigger that is gone.

**Owned paths:**

- `frontend/src/components/admin/FootprintScreen.tsx`
- `frontend/src/components/admin/FootprintScreen.test.tsx`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:** The component test shows three things: after approve and after withdraw, activeElement is the status line; no element inside [data-notice='warn'] has text-muted or text-negative; a blank reject submit focuses the text area with aria-invalid true. FP-S2 and FP-S5 pass.

### T10: Members without scope permissions, proved end to end

**Depends on:** T09

In TodayScreen, the empty-state action links to findDestination('admin-footprint') only when unlocks(FOOTPRINT permissions) is true; everyone else sees the body only. Add FP-S7 (@e2e) to app.md and a journey test in taxonomy.journey.spec.ts. A reader has no 'Regulatory scope' entry and gets 'This page is not available to you' at /admin/footprint. An approver sees no checkbox and no 'Propose a change'. At a 375 px viewport, document scrollWidth does not exceed clientWidth. Change shell.journey.spec.ts so the reader sees no 'Set … under Admin' link.

**Owned paths:**

- `frontend/src/components/home/TodayScreen.tsx`
- `frontend/tests/e2e/taxonomy.journey.spec.ts`
- `frontend/tests/e2e/shell.journey.spec.ts`
- `backend/apps/taxonomy/app.md`

**Done when:** FP-S7 and the shell journey pass for the reader, approver and compliance officer logins, with no mocked API. The full taxonomy, shell and tenants journeys pass, and requirements_coverage.py finds FP-S6 and FP-S7.

### T11: Prototype: an Admin-only regulatory scope view with checkboxes and a request

**Depends on:** nothing

Remove the Footprint card from vSettings; Sara, Maria and Erik get a 'Regulatory scope' link there, and Johan gets nothing. Add a vScope view with a PERMS map (Sara and Erik: request and approve; Maria: approve; Johan: neither, so he gets a restricted message). It has the plain rule notice, read-state lists with checkbox glyphs, a 'Propose a change' btn danger that turns them into .check rows in a two-column grid, and a change panel with the title, Hides and Reveals from inFoot and oblInFoot before and after, the warn notice for hiding or narrowing, Cancel and 'Request approval'. The request leaves a static pending banner with the warning pill and Withdraw for the requester; nothing applies. REGIMES gains Banking and Payments. any() treats an empty footprint group as no restriction, and oblInFoot's regime check does the same. Remove the fp action.

**Owned paths:**

- `design/prototype/index.html`

**Done when:** Checked in a browser: Johan has no link and sees a restricted message in the scope view. Sara can tick only after 'Propose a change'. 'Request approval' leaves a pending banner and changes nothing until Withdraw. Emptying Regimes shows every obligation. Settings has no toggles. No console errors, no horizontal scroll at 375 px, and the localStorage state check still works.

### T12: Design card: read and edit states

**Depends on:** nothing

Rewrite design/screens/admin-footprint.html in the foundations, like tenant-shell.html. Title it 'Screen card: regulatory scope with change requests (/admin/footprint)', with H1 Regulatory scope. States: read for a compliance officer (plain rule notice, 'Propose a change' on the right); read for an approve-only viewer; an empty group's 'Not restricted' line; editing with checkboxes (three columns on wide screens, one on phones) and a group hint under its legend; the change panel before and after a change, with Hides and Reveals, the warn notice for a narrowed group, Cancel and 'Request approval'. No chips and no Channels group.

**Owned paths:**

- `design/screens/admin-footprint.html`

**Done when:** The card renders in light and dark with no horizontal scroll at 375 px. The header comment lists FP-01, FP-02, FP-03, AC-FP1 and J-6. The wording matches spec §2.

### T13: Design card: pending and decision states

**Depends on:** T12

Add the remaining states to admin-footprint.html: the pending banner in requester, approver and request-only views with the pending pills on the terms; the approver's banner at 375 px in Swedish; the approve dialog with its one-sentence description, the warn notice and 'Approve with passkey'; the four-eyes refusal; the reject dialog with its error; history; the restricted page for a reader; loading and error.

**Owned paths:**

- `design/screens/admin-footprint.html`

**Done when:** Every state in spec §4 appears once. The Swedish approver banner fits at 375 px with at most two buttons per row. Only text-fg is used inside warn notices.

### T14: Scope wording across the other design cards

**Depends on:** nothing

Replace the footprint wording in the tenant and admin design cards: 'Show outside footprint' becomes 'Show outside our scope', 'Outside my footprint' becomes 'Outside our scope', 'Everything in my footprint' becomes 'Everything in our scope', and 'Set the footprint' becomes 'Set the regulatory scope'. Wording only.

**Owned paths:**

- `design/screens/tenant-inventory.html`
- `design/screens/tenant-watch.html`
- `design/screens/tenant-library-updates.html`
- `design/screens/tenant-roadmap.html`
- `design/screens/tenant-calendar-feeds.html`
- `design/screens/tenant-search.html`
- `design/screens/tenant-briefing.html`
- `design/screens/tenant-shell.html`
- `design/screens/states.html`
- `design/screens/auth-step-up.html`
- `design/screens/admin-members.html`
- `design/screens/admin-organisation.html`

**Done when:** grep -i footprint over these files finds only the /admin/footprint route and FP IDs.

### T15: Docs follow the new name and the restricted-setting pattern

**Depends on:** nothing

design/README.md: reword the 'Footprint toggles apply at once' row to say the prototype's scope view stops at a pending request, and that approval, rejection and history follow the app and admin-footprint.html. foundations.md: add the 'Restricted setting' pattern (spec §4.1 rules), set the danger row's hover to l3-negative-02 in light and l3-negative-03 in dark, drop 'footprint' from the Toggle line, and list admin-footprint.html as restyled. pills-and-labels.md: add 'Added when approved' and 'Removed when approved' to the Computed row. TODO_FOR_alex.md: confirm the Swedish name; add the PRD glossary line (footprint in code = Regulatory scope on screen); answer the open questions on firm types, a request reason, the admin second identity and Admin holding both permissions. Verification_Log.md: FI's area names (Bank, Betalningar) and the Green gds-checkbox guidance, each with its source and date.

**Owned paths:**

- `design/README.md`
- `design/system/foundations.md`
- `design/system/pills-and-labels.md`
- `docs/TODO_FOR_alex.md`
- `docs/plans/Verification_Log.md`

**Done when:** Every Verification_Log row has a source and a date. Each TODO entry names one decision or action for Alex. No doc calls the section 'Footprint' in user-facing terms.

## 12. Open questions

Each takes its stated default until Alex answers.

- Swedish name: confirm 'Regulatorisk omfattning' and the short forms 'I vår omfattning', 'Inte i vår omfattning' and 'Visa utanför vår omfattning'.
- Only Banking and Payments are added. Should the spec also add payment institution, e-money institution, investment firm and occupational pension company as legal entity types, add a Funds regime, or relabel 'AI and ICT' to 'ICT risk and AI' to match the PRD? The default is none of these.
- Tax is not named in PRD 0.2's sector scope. It stays as a regime, for the ISK, SFL and CRS/FATCA duties a firm carries for its clients. Add a line to the PRD? A system term cannot be retired today: there is no term-retire proposal kind, and system rows refuse retirement. Dropping it later would need a new proposal kind.
- A reason on each scope change request is not added. Alex did not ask for it, FP-02 does not require it, and four eyes, the step-up and per-term audit already exist. If it is wanted: one column on footprint_change_request, read through footprint_history.request, required in both the UI and the API.
- One Admin can get past the second person. They can invite a second identity they control, or grant footprint.approve to a new member, and then approve their own request; the check constraint cannot see this. The default is no code: the audit log shows the invitation or role grant next to the approval. The alternative: refuse the approval with 409 four_eyes_violation when the approver's membership, or the role grant that gives footprint.approve, is newer than the request.
- PRD §6 gives Admin both footprint.request and footprint.approve, so two tenant admins can change the scope without a compliance officer. Keep this (the default), or narrow it in a PRD revision?
- Every member can read the request history, decision notes included. It is available through the ungated GET /tenant/footprint/requests and through the audit log, since every role holds audit.read. The UI shows the history only on the restricted page. Keep this?
- Operating markets: matching is flat, so ticking only Sweden in the jurisdiction group would hide every EU-level record. The parallel markets work must either make matching understand the Union and its member states (so a ticked member state keeps Union records), or require the EU term whenever a member state is ticked. It may also move jurisdiction to the top of the dimension order; this page follows either way.
- Found while checking, outside this change: _ensure_rows in backend/apps/taxonomy/seeds/__init__.py re-applies sort_order, kind, is_default and active to every library vocabulary row on every deploy. After the first deploy it would undo an approved library-list reorder (VOC-07). T01 fixes the same pattern in seed_taxonomy_terms only. The vocabulary seed needs the same fix in its own slice.
- Keep the route /admin/footprint (the default), or rename it to /admin/scope with a redirect?
- Rejected: making the Organisation summary reachable from Today, the list filters or the account menu. The summary is removed instead, because Alex asked that ordinary users not reach this setting, and FP-03's 'Outside our scope' marks show members what is filtered.
- Rejected: naming 'your compliance officer' in Today's empty state for members without the permissions. Role names go stale with custom roles, so those members see the body without an action.
- Rejected: listing every anyOf permission on the restricted page. The /admin gate has nine permissions, so that page would list nine. The misnamed approve-only notice is deleted instead.
- Rejected: a Today row for a waiting approval. Today has no data yet (chunk 6 builds its attention items), and approvers already reach the page from Admin.
- Rejected: making If-Match required on the decision routes. Playbook 4.3 defines a missing If-Match as 'no check asked', and the row lock makes the status re-check reliable.
- Rejected: letting a retired but held term be removed. No path retires a taxonomy term (it is not a registry list, there is no term-retire proposal kind, and system rows refuse retirement), so the spec drops that row state.
- Rejected: a fresh passkey ceremony on every approval. ID-06 sets one freshness window for every step-up action. The overstated 'Your passkey will be asked' sentence is deleted instead.
- Rejected: showing 'Counted when requested' next to 'Counted now'. The approver sees one count, recounted on read, and the stored count stays on the request.
- Rejected: must-fail contrast pairs or a lint rule for text inside warn notices. The foundations rule plus a component assertion on this screen cover the only place this occurs.
- Rejected: a character counter and ARIA wiring for the request reason. The reason is not added; the ARIA wiring and the focus move go to the reject note instead.
- Rejected: moving CheckRow's hint outside its label and passing data-* through CheckGroup. Rows no longer carry hints, because pending marks moved to the read list as pills, and the E2E tests find groups by the screen's own data-dimension wrapper.

## Sources

- C:\Users\Alex\projects\grc\PRD.md (sector scope 25-30; FP-01..03 112-114; AC-FP1 259; J-6 276; §6 permissions 280-300, audit.read for every role)
- C:\Users\Alex\projects\grc\docs\PLAYBOOK.md §6.5 (lede at most 60 characters, one description at most 80, no restated invariants) and §6.8 (two buttons per row, on the right)
- C:\Users\Alex\projects\grc\docs\plans\IMPLEMENTATION_STATUS.md (chunk 2 row; first test deploy after chunk 7)
- C:\Users\Alex\projects\grc\design\system\foundations.md (danger row with light-only hover, Toggle line, contrast table)
- C:\Users\Alex\projects\grc\design\system\pills-and-labels.md (six tones, Scope block, computed labels)
- C:\Users\Alex\projects\grc\design\README.md line 61
- C:\Users\Alex\projects\grc\design\prototype\index.html (USERS 315-319, REGIMES 320, any() 532, oblInFoot 534, vSettings 881, fp action 955)
- C:\Users\Alex\projects\grc\frontend\src\components\admin\FootprintScreen.tsx (StatusLine mounted with its text, PendingBanner ButtonBar justify-start, ProblemAlert inside the warn banner, Modal description concatenation)
- C:\Users\Alex\projects\grc\frontend\src\components\ui\Field.tsx (CheckRow disabled, CheckGroup hint after options, no aria wiring), Button.tsx (danger hover bg-negative-soft, ButtonBar flex-nowrap), Notice.tsx, PageHead.tsx, Modal.tsx, States.tsx, Pill.tsx, pill-tones.ts
- C:\Users\Alex\projects\grc\frontend\src\styles\theme.css, tokens.generated.css and contrast.test.ts; contrast ratios computed locally with the WCAG 2.x luminance formula on 2026-09-19 (dark negative on l3-negative-02 4.47, on l3-negative-03 5.40; dark negative on l3-warning-02 3.24; dark muted on l3-warning-02 3.62)
- C:\Users\Alex\projects\grc\frontend\src\shared\navigation\registry.ts (admin-organisation under the gated admin parent) and require-permission.tsx (humanisePermission, anyOf[0])
- C:\Users\Alex\projects\grc\frontend\src\components\admin\RolesScreen.tsx and frontend\src\features\tenant-admin\members-presentation.ts (permissions labelled by humaniseKey)
- C:\Users\Alex\projects\grc\frontend\src\components\home\TodayScreen.tsx (empty-state link to /admin for every member)
- C:\Users\Alex\projects\grc\frontend\src\features\footprint\footprint-presentation.ts (requestTitle, previewSummary, presentScope)
- C:\Users\Alex\projects\grc\frontend\src\messages\en.json and sv.json (fingeravtryck at sv 103, 117, 126)
- C:\Users\Alex\projects\grc\frontend\tests\e2e\taxonomy.journey.spec.ts (FP-S2, FP-S5), shell.journey.spec.ts (reader sees the Admin link), tenants.journey.spec.ts
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\footprint_logic.py (unlocked _decidable, pending() check before insert, per-term events without request id, preview_of not counting), api.py 415-540, http.py (if_match optional), models.py (FootprintChangeRequest), migrations\0001_initial.py (only the four-eyes check), matching.py, terms_logic.py, registry.py (TaxonomyTerm not a registry list), app.md
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\seeds\__init__.py (update_or_create re-applies sort_order and active; no record()) and backend\apps\shared\management\commands\seed_reference.py
- C:\Users\Alex\projects\grc\backend\apps\proposals\models.py (ProposalKind) and apply.py (term_update sort_order, system rows refuse retirement)
- C:\Users\Alex\projects\grc\backend\apps\shared\errors.py and taxonomy\http.py (validation_error is 422; request_pending, invalid_transition, stale_write are 409)
- C:\Users\Alex\projects\grc\backend\apps\shared\permissions.py (enforce_step_up freshness window, PERMISSION_DESCRIPTIONS, UNGATED footprint reads), backend\apps\shared\tenancy.py (library_write fence), backend\apps\shared\e2e_seed.py (EXPECTED_FOOTPRINTS, J-6 pending request), backend\apps\identity\roles_logic.py
- C:\Users\Alex\projects\grc\backend\apps\library\models.py (Obligation.terms, Instrument.regime) and library\seeds\library.py (library.seeded audit precedent)
- C:\Users\Alex\projects\grc\backend\config\settings.py (ATOMIC_REQUESTS, STEP_UP_FRESHNESS_MINUTES 5)
- C:\Users\Alex\projects\grc\backend\apps\library\fixtures\prototype_data.json (term_dimension labels, regime terms 1-6, footprint_terms)
- Green MCP get_component_docs gds-checkbox (vertical by default, group header label, read-only keeps selected and unselected visible), fetched 2026-09-19
- https://www.fi.se/sv/ (top-level areas: Bank, Betalningar, Försäkring, Marknad), fetched 2026-09-19
- https://www.fi.se/sv/vara-register/foretagsregistret/ (firm categories, for the open question on legal entity types), fetched 2026-09-19
- https://cdn.standards.iteh.ai/samples/75080/98db41625e0445a193a12f005dd5f30b/ISO-37301-2021.pdf (ISO 37301 §4.3 scope)
- https://www.sis.se/iso9001/tolkningsgruppfriso9001/tolkningaraviso9001/4_organisationens_forutsattningar/ (SIS: scope = omfattning)
- https://handbook.fca.org.uk/glossary/G2997 and https://www.fca.org.uk/publications/corporate-documents/fca-perimeter-report (perimeter, rejected)
- https://www.cube.global/products/regplatform/regulatory-inventory (regulatory footprint)
- https://regintel-content.thomsonreuters.com/ (monitoring profile)
- https://www.corlytics.com/solutions/regulatory-obligations-management/ (applicability filtering)
- https://www.nngroup.com/articles/toggle-switch-guidelines/ (checkboxes when a change needs a submit step)
- https://www.nngroup.com/articles/confirmation-dialog/ (overused warnings stop being read)
- https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-approval-workflow (no self-approval)
- https://knowledge.workspace.google.com/admin/security/multi-party-approval-for-sensitive-actions (pending request approved by another admin)
- https://docs.stripe.com/stripe-apps/components/button (destructive style reserved)

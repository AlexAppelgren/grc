# UI implementation plan

Playbook 7.5: every backend capability mapped to a screen, for every role,
from the endpoint inventory and the role matrix. The endpoint inventory is
`docs/inputs/openapi.yaml` (134 designed operations) plus the additions in
`docs/inputs/INPUT_DELTAS.md` §1 (vocabularies), §2 (auth, me), §5 (footprint
change requests) and §7 (served differently). Permissions are PRD section 6.
Step-up follows playbook 4.2. E2E scenario IDs are from `backend/apps/<app>/app.md`.

## Progress ledger

Updated at every integration. Corrections are added as new rows, never
overwritten.

| Date | Event | By |
|---|---|---|
| 2026-09-19 | Plan created. Chunk 1 operations marked "in build" (cards `auth-*`, `me-*`, `admin-members|roles|api-keys|security-log|organisation` by the identity agent). Chunks 2 to 7 marked "designed" with their cards in `design/screens/`. R2 and R3 operations mapped to the card that will hold them, marked "later chunk, card pending" | design agent |
| 2026-09-19 | Correction: the tenant never confirms a change's type or flags directly (library facts, PRO-01). `tenant-change.html` shows them as suggested; triage accepts them for the tenant, a library editor corrects them through `PATCH /changes/{id}`, a member reports. The earlier draft of the card had a tenant-side "Confirm classification" button; removed before the card was finished | design agent |
| 2026-09-19 | Paths for the INPUT_DELTAS additions that the contract does not yet spell out (vocabulary writes, footprint change requests, suggestions) are proposed in this table and marked "path proposed". The chunk that builds them fixes the path and adds a ledger row | design agent |
| 2026-09-19 | PRD 0.3: `GET /me/work` no longer feeds Today's "Decide now" — Today reads the queue counts on `GET /me`, and `/me/work` becomes the My work page in chunk 8 (D-23). New rows for the participant routes, the people reference, member teams, the watching routes and the unit and bulk-decision routes. `admin-footprint.html` gains the markets panel, and on screen the section is called Regulatory scope (PRD glossary) | docs agent |
| 2026-09-19 | f03-T60: `tenant-my-work.html` drawn; the participants panel added to `tenant-obligation.html` and `tenant-change.html`; departments with heads and teams added to `admin-organisation.html`; team membership added to `admin-members.html`. My work is not a fifth dock destination: it has no `dockRank` and is reached from the rail and the More sheet | design agent |
| 2026-09-21 | c7-search-screen: `POST /search` built at `/search` (`tenant-search.html`). Type, jurisdiction, duty type, binding and language filters plus "As of" and "Outside our scope" in the URL; the typed query stays out of it, in component state only. The card's instrument filter, per-hit language tag and "N obligations" instrument summary are cut: no route lists instruments to choose from and `SearchHit` carries none of the other two, so nothing here invents them. A provision hit renders as a fact rather than a link: no screen opens one yet | search agent |
| 2026-09-23 | Correction (review of `645b1c3..2492f80`): the status cells are brought back to `main`. Three rows marked shipped name a journey that is still `test.fixme` and move to in build naming it (`GET /obligations`: FP-S4; `GET /obligations/{id}/versions` and `/diff`: AGT-S10; `POST .../problem-reports`: PRO-S7 and AUD-S5), and so do `tenant-inventory.html` until FP-04's watched-market view (FP-S13) lands and `tenant-obligation.html`, whose Related changes, This looks wrong and machine-confirmed journeys are fixme. Rows still reading "designed" for work that is on `main` read in build and say what is missing. `GET /me/whats-new` is served as `GET /library-updates` with `POST /me/visit` (622ce06). `GET /authorities` and `GET /obligations/{id}/changes` are served, and the related-changes panel renders the second. The console problem-report surface is removed (D-50). The footprint request and vocabulary paths are the built ones. `console-change-facts.html` and `console-agent-keys.html` join the card table. "in build" now means any chunk in progress, not chunk 1 alone. On review of this correction, `tenant-instrument.html` moves to in build for the same This looks wrong journeys as the obligation card (and INV-S11), `states.html` reads in build because its shared states are on `main`, and `tenant-calendar-feeds.html` reads in build like its routes' row | review-fixes |

## Honesty rules (playbook 7.5, kept in spirit)

- A feature is **covered** only when its screen exists, its role variants
  render, its empty, loading, error and denied states exist, and its `@e2e`
  journey is un-fixme'd and green. A registry entry that renders "Coming soon"
  is not shipped, and neither is a card in `design/screens/`.
- When the PRD or an `app.md` conflicts with this plan, they win, and the
  ledger records the correction.
- Nothing in UI code checks a role name. The "role variants" column says
  which permission unlocks what; the roles named are the seeded system roles
  of PRD section 6, used only to describe what must render in E2E.
- Every shipped hook has a caller. A payload that carries an id carries
  enough for a person to act on it (title, key, label), never an id alone.
- The status column is the truth of `git log`, not intention. "designed"
  means a card exists and nothing is built. "in build" means the chunk is in
  progress on `main`. "shipped" is set only when the covered rule above holds.

## Status words

| Status | Means |
|---|---|
| served | Exists from Phase 0 (`/health/`, `GET /me` minimal) |
| in build | On `main`, its chunk in progress, and not yet shown to meet the covered rule; the row names what is missing |
| designed | A card in `design/screens/` exists and nothing of it is built on `main` |
| shipped | The covered rule above holds: screen, role variants, every state, `@e2e` un-fixme'd and green, on `main` |
| later chunk N, card pending | An R2/R3 operation; the screen that will hold it is named, its card is not drawn yet |
| removed | Dropped by INPUT_DELTAS; the row says what replaces it |
| agent only | Called with an API key by agents; no screen calls it |

## Screen cards

| Card | Route | Surface | Chunk | Status |
|---|---|---|---|---|
| `tenant-shell.html`, `tenant-today.html` | `/` | tenant | 0, 6 | shell built in chunk 0; Today's panels chunk 6 |
| `auth-invitation`, `auth-code`, `auth-enrol`, `auth-sign-in`, `auth-step-up`, `auth-recovery` | `/auth/*` | both | 1 | in build |
| `me-passkeys`, `me-sessions` | `/me/passkeys`, `/me/sessions` | both | 1 | in build |
| `admin-organisation`, `admin-members`, `admin-roles`, `admin-api-keys`, `admin-security-log` | `/admin/*` | tenant | 1 | in build |
| `admin-vocabularies.html` | `/admin/vocabularies` | tenant | 2 | in build (VOC-S2 to VOC-S5, VOC-S7, VOC-S11 and VOC-S15 journeys un-fixme'd; Suggest, VOC-S6, is chunk 8) |
| `admin-vocabulary.html` | `/admin/vocabularies/[list]`; console variant `/console/vocabularies/[list]` | both | 2, 4 | in build, both variants |
| `admin-footprint.html` (on screen: Regulatory scope) | `/admin/footprint` | tenant | 2; markets panel 3 | in build: requests with preview, four eyes and step-up (FP-S2, FP-S5 un-fixme'd); the markets panel (card states 17 to 19) is not built (FP-S10 fixme) |
| `picker-create-or-suggest.html` | inside every vocabulary picker | both | 2 (near-duplicate), 8 (suggest) | in build: Create with the near-duplicate check (VOC-S7); Suggest is chunk 8 |
| `tenant-inventory.html` | `/inventory` (Obligations, Instruments tabs) | tenant | 3 | in build until FP-04's watched-market view (FP-S13) and FP-S4's journey land; INV-S1, INV-S3 and INV-S4 are un-fixme'd |
| `tenant-obligation.html` | `/inventory/obligations/[obligationId]` | tenant | 3; register panels 8 | in build: INV-S3 to INV-S7 are un-fixme'd; the Related changes panel (WAT-S6), This looks wrong's own journeys (PRO-S7, AUD-S5) and the machine-confirmed label (INV-S14) are fixme; register panels land with chunk 8 |
| `tenant-instrument.html` | `/inventory/instruments/[instrumentId]` | tenant | 3 | in build: INV-S1, INV-S2 and INV-S7 are un-fixme'd; This looks wrong's own journeys (PRO-S7, AUD-S5) and a standard's edition with no text (INV-S11, INV-08) are fixme |
| `console-shell.html` | `/console` | console | 4 | in build (ADM-S4 un-fixme'd) |
| `console-queue.html` | `/console/queue`, `/console/queue/[proposalId]` | console | 4 | in build (PRO-S3, PRO-S4, PRO-S5 and PRO-S9 un-fixme'd; PRO-S13's journey and the batch variant are not) |
| `console-problem-reports.html` | `/console/problem-reports` | console | 4 | removed (D-50; PRD 0.4 AUD-03 and ADM-02): a report stays inside the bank that filed it and the console has no problem-report surface |
| `tenant-library-updates.html` | `/inventory/updates` | tenant | 4 | in build: the screen reads `GET /library-updates` and moves the bookmark with `POST /me/visit`; PRO-S7's journey is fixme |
| `tenant-watch.html` | `/watch` (tabs by case category, Coverage) | tenant | 5; workflow tabs fill in 9 | in build (WAT-S1, WAT-S2 and WAT-S9 un-fixme'd; FP-S4 and FP-S15's watched-market view are not) |
| `tenant-change.html` | `/watch/[changeId]` | tenant | 5; case panels 9 | in build: timeline, documents, obligation links and the "So what?" draft render; Rewrite, Confirm wording, Confirm link and Not related are not built (WAT-S4, WAT-S6, WAT-S7 fixme) |
| `console-sources.html` | `/console/sources` | console | 5 | in build, read-only: Add, Edit, Pause and Check now are not on the page in R1, nor the jurisdiction filter, which needs `GET /authorities` to admit a console session |
| `console-change-facts.html` | `/console/change-facts`, `/console/change-facts/[changeId]` | console | 5 | in build: the queue of facts nobody has confirmed, and correcting one; confirming a suggestion is not built (D-74, WAT-S4) |
| `console-agent-keys.html` | `/console/agent-keys` | console | 5 | in build: the screen is on `main` and its routes answer 501 until they are built (ID-S20's console journey is fixme) |
| `tenant-briefing.html` | `/briefing`, `/briefing/[weekStart]` | tenant | 6 | in build (HOM-S3 un-fixme'd) |
| `tenant-roadmap.html` | `/roadmap` | tenant | 6 | in build (HOM-S4 and HOM-S6 un-fixme'd) |
| `tenant-calendar-feeds.html` | `/me/calendar-feeds` | tenant | 6 | in build: the routes are on `main`; the screen is not built (HOM-S5 fixme) |
| `tenant-search.html` | `/search` | tenant | 7 | in build (SRC-S1 and SRC-S3 un-fixme'd; J-7, SRC-S10, waits on Ask) |
| `tenant-ask.html` | `/search?mode=ask` | tenant | 7 | designed |
| `states.html` | every screen | both | 2 onwards | in build: the shared states are on `main` (`components/ui/States.tsx` for loading, error, not found and the refusals rendered in place; `components/ui/EmptyState.tsx`; the Restricted screen that `RequirePermission` and `/restricted` render); the card is met screen by screen, as each screen that draws its states ships |
| `console-vocabularies.html` | `/console/vocabularies` | console | 4 | not drawn: `admin-vocabularies.html` shared-list tab is the same list, rendered for `library_vocab.manage` with Rename, Merge, Retire producing proposals. Draw a separate card only if the build finds a difference |
| `console-languages.html` | `/console/languages` | console | 4 | card pending (languages and jurisdictions are library vocabularies; `admin-vocabulary.html` console variant renders them) |
| `admin-audit-log.html` | `/admin/audit-log` | tenant | 4 (proposed, AUD-01 is R1 M and no chunk names its screen) | in build without a card: the screen is on `main`, cut from the prototype's `vAudit()`, and AUD-S3's journey is un-fixme'd |
| `admin-ai-log.html` | `/admin/ai-log` | tenant | 7 (AUD-02) | card pending |
| `console-evaluation.html` | `/console/evaluation` | console | 7 (SRC-05) | card pending |
| `tenant-gaps.html`, register panels | `/inventory/obligations/[id]` right column, `/gaps` | tenant | 8 | card pending; prototype `vGaps()`, `vGap()`, `entityPanel()`, `gapsPanel()`, `historyPanel()`, `interpPanel()` are the cut |
| `admin-organisation.html` entities, licences and certificates, products, departments with heads, teams | `/admin/organisation` | tenant | 8 | extends the chunk 1 card; departments with heads and teams designed (f03-T60); the entity, licence, certificate and product sections are card pending |
| `admin-members.html` team membership on the member row | `/admin/members` | tenant | 8 | extends the chunk 1 card; designed (f03-T60) |
| `tenant-my-work.html` | `/work` | tenant | 8 | designed (HOM-05, f03-T60): scope switch, four sections, the link to Today, the permission-limited line, every state, and the comments and mentions panel from chunk 10 |
| participants panel on `tenant-obligation.html` and `tenant-change.html` | `/inventory/obligations/[id]`, `/watch/[changeId]` | tenant | 8, 9 | designed (COL-04, f03-T60) |
| units list, paste dialog and the Statement of Applicability view on `tenant-obligation.html` | `/inventory/obligations/[id]` | tenant | 8 | card pending (REG-08) |
| case panels on `tenant-change.html` | `/watch/[changeId]` | tenant | 9 | card pending; prototype `vChange()` work panels are the cut |
| `tenant-notifications.html`, comments panel | who panel, every record | tenant | 10 | card pending |
| `admin-agents.html`, `console-agent-definitions.html` | `/admin/agents`, `/console/agents` | both | 11 | card pending; prototype `vAgents()` is the cut |
| `console-tenants.html`, `console-health.html` | `/console/tenants`, `/console/health` | console | 4; health 14 | tenants in build without a card (the list, and a tenant created with its first administrator invited, ADM-S6 un-fixme'd; support access is TEN-06, chunk 8); health chunk 14 (ADM-S5), card pending |
| `tenant-reports.html`, `admin-data.html` | `/reports`, `/admin/data` | tenant | 12 | card pending; prototype `vReports()` is the cut |
| `admin-integrations.html`, `admin-security.html` | `/admin/integrations`, `/admin/security` | tenant | 13 | card pending |

## Operations

Columns: operation · screen card that calls it · surface · permission (PRD
section 6; `key:` means an API key scope) · step-up · role variants that must
render · E2E scenario · status.

Role shorthand: A admin, CO compliance officer, O owner, AP approver, C
contributor, R reader, AU auditor, LE library editor, PA platform admin.
"All 7" means every tenant system role.

### System and session

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /health` (served at `/health/`, site root, INPUT_DELTAS §7) | none, load balancer | none | none | no | none | NFR-S14 | served |
| `POST /auth/invitations/open` | `auth-invitation.html` | both | none | no | anyone with the link | ID-S2, ID-S25 | in build |
| `POST /auth/code/request` | `auth-code.html`, `auth-sign-in.html` | both | none | no | anyone; enrolled account looks identical | ID-S6, ID-S25 | in build |
| `POST /auth/code/verify` | `auth-code.html` | both | none | no | anyone; lock after 5 attempts | ID-S3, ID-S4 | in build |
| `POST /auth/passkeys/register/options`, `/verify` | `auth-enrol.html` (enrolment session), `me-passkeys.html` (add) | both | enrolment session or any signed-in | no | anyone | ID-S5, ID-S10 | in build |
| `POST /auth/passkeys/authenticate/options`, `/verify` | `auth-sign-in.html` | both | none | no | anyone | ID-S8, ID-S25 | in build |
| `POST /auth/step-up/options`, `/verify` | `auth-step-up.html`, opened by every step-up action | both | any signed-in | is the step-up | anyone | ID-S14, ID-S15 | in build |
| `POST /auth/refresh` | none, `api-client.ts` | both | refresh cookie | no | none | ID-S9 | in build |
| `POST /auth/sign-out` | who panel (`tenant-shell.html`, `console-shell.html`) | both | any signed-in | no | anyone | ID-S25 | in build |
| `GET /me` | shell (who panel, registry permissions, queue counts) | both | any signed-in or enrolment | no | anyone | ID-S4, ID-S26 | served, grows in chunk 1 |
| `PATCH /me` | who panel language switch (chunk 1); notification preferences on `tenant-notifications.html` (chunk 10) | both | any signed-in | no | anyone | ID-S18 | in build (locale); later chunk 10 (preferences), card pending |
| `GET /me` queue counts (applicability added) | `tenant-today.html` Decide now | tenant | any signed-in | no | All 7; counts differ by permission | HOM-S1, CAS-S14 | in build: `counts{triage, proposals, assignedToMe}` feed Decide now (HOM-S1 un-fixme'd); the sign-off and applicability counts come with chunks 9 and 8 |
| `GET /me/work` (reshaped, INPUT_DELTAS §7) | `tenant-my-work.html` | tenant | any member; each row needs its own read permission | no | All 7; rows and counts filtered, unreadable kinds shown as permission-limited | HOM-S7, HOM-S9, HOM-S13 | later chunk 8, card designed (`tenant-my-work.html`) |
| `GET /me/comments?about=written\|mentioned` | `tenant-my-work.html` Comments and mentions | tenant | any member; filtered by the subject's read permission | no | All 7 | COL-S12 | later chunk 10, card pending |
| `GET /library-updates`, `POST /me/visit` (in place of the designed `GET /me/whats-new`, 622ce06; INPUT_DELTAS) | `tenant-library-updates.html`, count on `tenant-today.html` | tenant | `library.read` (list); any member session, for its own bookmark (visit) | no | All 7 | PRO-S7, AGT-S10 | in build: both routes and `/inventory/updates` are on `main`; PRO-S7 and AGT-S10 are fixme and Today shows no count yet |
| `GET /me/passkeys`, `PATCH /me/passkeys/{id}`, `DELETE /me/passkeys/{id}` | `me-passkeys.html` | both | any signed-in | no | anyone; last passkey cannot go | ID-S10 | in build |
| `GET /me/sessions`, `DELETE /me/sessions/{id}` | `me-sessions.html` | both | any signed-in | no | anyone | ID-S11 | in build |

### Tenant and administration (chunk 1)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /tenant` | `admin-organisation.html` | tenant | any member (reads); edit needs `members.manage` | no | All 7 read; A edits | TEN-S1 | in build |
| `PATCH /tenant` | `admin-organisation.html` (name, timezone, languages); reminders, escalation, retention on `admin-security.html`/`admin-data.html` | tenant | `members.manage` (profile), `workflow.manage` (reminders), `security.manage` (retention) | no | A; CO for workflow | TEN-S1, COL-S2, AUD-S6 | in build (profile); later chunks 10, 12 |
| `GET /tenant/members`, `GET /tenant/members/{id}/sessions` | `admin-members.html` | tenant | `members.manage` | no | A | ADM-S2, ADM-S1 | in build |
| `POST /tenant/members` (invite) | `admin-members.html` | tenant | `members.manage` | no | A | ID-S1, ADM-S2 | in build |
| `PATCH /tenant/members/{id}` (roles, title) | `admin-members.html` | tenant | `members.manage` | yes (roles) | A; last-admin 409 rendered | ID-S19, ADM-S2 | in build |
| `DELETE /tenant/members/{id}` (deactivate) | `admin-members.html` | tenant | `members.manage` | yes | A; bulk reassignment, participations and team memberships end in chunk 8 | ADM-S2, TEN-S5, TEN-S9 | in build |
| `PUT /tenant/members/{userId}/teams` | `admin-members.html` member row | tenant | `members.manage` | no | A | TEN-S8 | later chunk 8, card pending |
| `GET /reference/people` | every people picker (participants, owners) | tenant | any member session; refused for an enrolment session | no | All 7 | COL-S6, TEN-S8 | later chunk 8, card pending |
| `DELETE /tenant/members/{id}/sessions` | `admin-members.html` | tenant | `members.manage` | no | A | ID-S11 | in build |
| `POST /tenant/members/{id}/reissue-enrolment` | `admin-members.html` | tenant | `members.manage` | yes | A | ID-S12 | in build |
| `GET /tenant/invitations`, `POST .../{id}/resend`, `DELETE .../{id}` | `admin-members.html` Invitations tab | tenant | `members.manage` | no | A | ID-S1, ADM-S2 | in build |
| `GET /tenant/roles`, `POST`, `PATCH /{key}`, `POST /{key}/retire`, `GET /reference/permissions` | `admin-roles.html` | tenant | `roles.manage` | yes (create, update, retire) | A | ID-S18, ADM-S3 | in build |
| `GET /tenant/api-keys`, `POST`, `DELETE /{id}` | `admin-api-keys.html` | tenant | `integrations.manage` | yes (create) | A; key shown once | ID-S20, ID-S21 | in build |
| `GET /tenant/security-log` | `admin-security-log.html` | tenant | `security.manage` | no | A | ID-S22 | in build |
| `POST /console/tenants/{tenantId}/members/{userId}/reissue-enrolment` | `console-tenants.html` | console | `support_access.grant` | yes | PA; out-of-band check recorded | ID-S13, ADM-S6 | in build (endpoint); later chunk 11, card pending |

### Vocabularies (INPUT_DELTAS §1, chunk 2)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /vocab` (list of lists) | `admin-vocabularies.html`; console variant | both | any member (tenant lists), `library_vocab.manage` (console) | no | All 7 read their lists; A and CO get actions; LE in console | VOC-S1, VOC-S14 | in build |
| `GET /vocab/{list}` | every picker, filter, presentation function; agents at run start | both | any member; `key:vocab:read` | no | All 7; agents | VOC-S2, AGT-S3, VOC-S14 | in build |
| `POST /vocab/{list}` | `admin-vocabulary.html` Add a value; `picker-create-or-suggest.html` Create | tenant; console for library lists (becomes a proposal, VOC-07) | `vocab.manage`; `library_vocab.manage` via proposal | no | A, CO create; others see Suggest; 409 near_duplicate rendered in place | VOC-S2, VOC-S7, VOC-S11, VOC-S15 | in build |
| `PATCH /vocab/{list}/{key}` (relabel), `POST /vocab/{list}/reorder`, `POST /vocab/{list}/{key}/retire`, `/restore` (the built paths) | `admin-vocabulary.html` inline rename, drag, Retire, Restore | both | `vocab.manage`; console via proposal | no | A, CO; system rows relabel only; last value of a category has no Retire | VOC-S3, VOC-S4, VOC-S8, VOC-S15 | in build |
| `POST /vocab/{list}/{key}/merge` (`?dryRun=true` previews) | `admin-vocabulary.html` Merge with preview | both | `vocab.manage`; console via proposal | no | A, CO; preview shows the count moved | VOC-S5, VOC-S15 | in build |
| `POST /vocab/{list}/suggest`, `GET /vocab/{list}/suggestions`, `POST .../suggestions/{id}/decline`; accept is not built | `picker-create-or-suggest.html` Suggest; `admin-vocabulary.html` Suggested tab | tenant | suggest: any member; decide: `vocab.manage` | no | O, AP, C, R, AU suggest; A, CO decide | VOC-S6, VOC-S7 | later chunk 8 (VOC-03 is R2): the three routes above are on `main` with no screen |

### Taxonomy and footprint

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /taxonomy/terms` | `admin-footprint.html` dimensions; scope pickers; inventory and watch filters | both | `library.read`; `key:library:read` | no | All 7 | FP-S1, VOC-S1 | in build |
| `POST /taxonomy/terms`, `PATCH /taxonomy/terms/{id}` | `admin-vocabulary.html` console variant (Scope terms) → `console-queue.html` (kind Vocabulary) | console | `library_vocab.manage`, applied by `proposals.review` | approve: yes | LE proposes, a second LE approves | VOC-S11, VOC-S15 | in build: each call files a proposal (202) and writes no term (VOC-S11) |
| `GET /tenant/footprint` | `admin-footprint.html`; every footprint-respecting screen reads its match | both | `library.read`; `key:footprint:read` | no | All 7 | FP-S1, FP-S4 | in build (FP-S4's journey is fixme) |
| `PUT /tenant/footprint` | none | tenant | | | | | removed (INPUT_DELTAS §5); replaced by the change requests below |
| `POST /tenant/footprint/requests?dryRun=true` (the built path) | `admin-footprint.html` preview panel | tenant | `footprint.request` | no | A, CO; others read-only banner | FP-S2, FP-S5 | in build |
| `GET /tenant/footprint/requests`, `POST` (the built path) | `admin-footprint.html` pending banner, Send for approval, History | tenant | `footprint.request` | no | A, CO request; All 7 see the pending banner | FP-S2, FP-S5 | in build |
| `POST /tenant/footprint/requests/{id}/approve` (the built path) | `admin-footprint.html` Approve | tenant | `footprint.approve` | yes | A, CO, AP; requester sees the refusal, server 409 four_eyes_violation | FP-S2, FP-S3, FP-S5 | in build |
| `POST /tenant/footprint/requests/{id}/reject`, `/withdraw` (the built paths) | `admin-footprint.html` Reject with reason, Withdraw | tenant | reject `footprint.approve`; withdraw: requester | no | A, CO, AP reject; requester withdraws | FP-S2, FP-S6 | in build |
| `GET /tenant/footprint` markets block | `admin-footprint.html` "Markets we watch" panel | tenant | any member reads | no | All 7 read; only `footprint.request` may change | FP-S10 | in build: `markets` is on `GET /tenant/footprint`; the panel is not built (FP-S10 fixme) |
| `POST /tenant/footprint/watching`, `POST /tenant/footprint/watching/remove` (key in the body, never a path) | `admin-footprint.html` "Markets we watch" panel | tenant | `footprint.request` | no | A, CO; others read-only | FP-S10, FP-S14 | in build: both routes are on `main`; the panel that calls them is not built (FP-S10 fixme) |

### Library and inventory (chunk 3)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /authorities` | `console-sources.html` add form and jurisdiction filter; the console's Change facts authority filter | console | `library.read` (a tenant session); `key:library:read`; a console session holding `sources.manage` is refused today | no | LE; All 7 and agents may read it | — | in build: the route is on `main` (INPUT_DELTAS §8) for a tenant session and a key; no screen calls it, because the console session it is designed for is refused until the gate admits `sources.manage`, as `GET /sources` does |
| `GET /instruments`, `GET /instruments/{id}` | `tenant-inventory.html` Instruments tab; `tenant-instrument.html` | tenant | `library.read`; `key:library:read` | no | All 7 | INV-S1, INV-S10 | shipped; no "Adopted" row on the card, because no such data exists |
| `GET /instruments/{id}/relations` | `tenant-instrument.html` Lineage | tenant | `library.read` | no | All 7 | INV-S1 | shipped (no standalone route: `GET /instruments/{id}` answers `lineage` embedded, the same instrument read the card already makes) |
| `GET /instruments/{id}/provisions`, `GET /provisions/{id}/diff` | `tenant-instrument.html` provision tree, Show what changed | tenant | `library.read` | no | All 7 | INV-S2, INV-S10 | shipped (a provision's versions and their text are embedded in the tree read; there is no `GET /provisions/{id}/versions`) |
| `GET /obligations` | `tenant-inventory.html` (Obligations tab: filters, "as of", outside footprint, instrument filter with counts) | tenant | `library.read`; `key:library:read` | no | All 7; register overlay columns from chunk 8 | INV-S3, INV-S4, FP-S4 | in build: INV-S3 and INV-S4 are un-fixme'd; FP-S4's journey is fixme |
| `GET /obligations/{id}` | `tenant-obligation.html` | tenant | `library.read` | no | All 7 | INV-S3, INV-S6, INV-S7 | shipped |
| `GET /obligations/{id}/versions`, `GET /obligations/{id}/diff` | `tenant-obligation.html` version chips, Show what changed, Versions panel; `tenant-library-updates.html` Show what changed | tenant | `library.read` | no | All 7 | INV-S4, INV-S5, AGT-S10 | in build: INV-S4 and INV-S5 are un-fixme'd; AGT-S10's journey is fixme. `versions[]` is embedded in `GET /obligations/{id}`, so there is no `GET /obligations/{id}/versions` route |
| `GET /obligations/{id}/changes` | `tenant-obligation.html` Related changes | tenant | `library.read` | no | All 7 | WAT-S6 | in build: the route is on `main` and the Related changes panel (`ObligationRelatedChanges.tsx`) renders it; WAT-S6's journey is fixme |
| `POST /obligations/{id}/verifications` | `console-queue.html` (a Re-verification proposal applies the stamp on approval) | console | `proposals.review` | no | LE; never a tenant role | INV-S8 | in build: the route is on `main` (INV-S8's integration half is green) |
| `POST /obligations/{id}/problem-reports` | `tenant-obligation.html`, `tenant-instrument.html`, `tenant-change.html`, `tenant-library-updates.html` This looks wrong | tenant | `problems.report` | no | All 7 | INV-S7, PRO-S7, AUD-S5 | in build: on `tenant-obligation.html` and `tenant-instrument.html` (INV-S7 un-fixme'd; PRO-S7 and AUD-S5 are fixme), body `{description, versionNumber?, language?}` with no "Where" select (open question for Alex, `docs/TODO_FOR_alex.md`); `tenant-change.html` and `tenant-library-updates.html` land with their own chunks. No `GET .../problem-reports` list exists yet (chunk 4, with the tenant's own proposal queue) |

### Register (chunk 8, R2)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `PATCH /obligations/{id}/register` | `tenant-obligation.html` Where we stand, How we handle it, per legal entity | tenant | `register.edit` | no | CO, O edit; others read; `If-Match`, 409 stale_write rendered | REG-S3, REG-S4, REG-S11 | later chunk 8, card pending (prototype `vObligation()` right column) |
| `PUT /obligations/{id}/applicability` (per obligation, legal entity or unit; path proposed) | `tenant-obligation.html` Does it apply to us, with its confirmation dialog | tenant | `applicability.approve` | no (D-75) | CO, AP; others read; one audit event per write | REG-S1, REG-S2, REG-S4, REG-S12 | later chunk 8, card pending |
| `POST /applicability` (many rows in one call; path proposed) | `tenant-obligation.html` paste dialog, confirm the decisions | tenant | `applicability.approve` | no (D-75) | CO, AP; one audit event per row; `REGISTER_BULK_MAX` caps a call | REG-S14 | later chunk 8, card pending |
| `GET/POST` units and the paste with its dry run (paths proposed) | `tenant-obligation.html` units list and paste dialog | tenant | `register.edit`; `applicability.approve` when the paste carries applicability | no | CO, O | REG-S13, REG-S15 | later chunk 8, card pending |
| `GET/POST /obligations/{id}/participants`, `DELETE .../participants/{participantId}` | participants panel on `tenant-obligation.html` | tenant | `register.edit`; anyone may remove their own row | no | CO, O add; the participant leaves | COL-S6, COL-S7 | later chunk 8, card pending |
| `GET/POST /changes/{id}/participants`, `DELETE .../participants/{participantId}` | participants panel on `tenant-change.html` | tenant | `cases.contribute`; anyone may remove their own row | no | CO, O, C add; the participant leaves | COL-S9, CAS-S17 | later chunk 9, card pending |
| `GET/POST /obligations/{id}/internal-links`, `DELETE /internal-links/{id}` | `tenant-obligation.html` Linked internal items | tenant | `register.edit` | no | CO, O | REG-S8 | later chunk 8, card pending |
| `GET/POST /obligations/{id}/attestations` | `tenant-obligation.html` Attestation | tenant | `register.edit` (owner only, server-checked) | no | O | REG-S9 | later chunk 13, card pending |
| `GET/POST /obligations/{id}/waivers` | `tenant-obligation.html` Waivers | tenant | `risk.accept.approve` | yes | CO, AP | REG-S9, REG-S6 | later chunk 13, card pending |

### Watch and the agent API (chunk 5)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /changes` | `tenant-watch.html` | tenant | `watch.read` | no | All 7; tabs by case category | WAT-S2, WAT-S9, FP-S4 | in build (WAT-S2 and WAT-S9 un-fixme'd; FP-S4 is fixme) |
| `GET /changes/{id}` | `tenant-change.html` | tenant | `watch.read` | no | All 7 | WAT-S2, WAT-S4, WAT-S6 | in build (WAT-S2 un-fixme'd; WAT-S4 and WAT-S6 are fixme) |
| `POST /changes` | none | agent | `key:changes:write` | no | agents; 409 merge on known stableKey | AGT-S2, WAT-S3, AGT-S10 | agent only |
| `PATCH /changes/{id}` (library facts: type, flags, scope) | `console-change-facts.html`; agents | console; agent | `proposals.review`; `key:changes:write` | no | LE confirms or corrects agent suggestions; tenants see "Suggested by the agent" until then | WAT-S4, WAT-S5 | in build: the console's Change facts detail corrects a fact through it; confirming a suggestion is not built (D-74, WAT-S4) |
| `POST /changes/{id}/events`, `PATCH /changes/{id}/events/{eventId}` | `console-change-facts.html`; agents | console; agent | `proposals.review`; `key:changes:write` | no | LE; agents | WAT-S2 | in build: the routes are on `main`; no console control calls them yet |
| `POST /changes/{id}/documents` | agents; `tenant-change.html` Documents reads them | agent; tenant | `key:changes:write` | no | agents write; All 7 read | WAT-S3 | in build: agents write, `tenant-change.html` Documents reads |
| `PUT /changes/{id}/obligations` | agents (suggest with confidence); `console-change-facts.html` (LE sets the links for the library) | agent; console | `key:changes:write`; `proposals.review` | no | agents; LE | WAT-S6 | in build: agents suggest and the console's Change facts detail sets the links; a person's call that would drop a confirmed link answers 501 `not_built`, because confirming is not built (D-74) |
| Case-side link confirmation (`tenant-change.html` Confirm link, Not related; stored on the tenant's case): `POST /changes/{id}/case/obligation-links`, `DELETE /changes/{id}/case/obligation-links/{obligationId}` | `tenant-change.html` | tenant | `cases.work` | no | CO, O confirm; others read | WAT-S6 | in build: the routes are on `main` (INPUT_DELTAS §8); the Confirm link and Not related controls are not built (WAT-S6 fixme) |
| `GET /sources`, `GET /sources/coverage` | `tenant-watch.html` Coverage tab; `console-sources.html`; `tenant-today.html` foot | both | `watch.read`; `sources.manage`; `key:sources:read` | no | All 7 read; LE manages | WAT-S1, HOM-S1 | in build: both routes are served to a tenant session and to a console session holding `sources.manage` (INPUT_DELTAS §8), and the Coverage tab and the console Sources page read them (WAT-S1 un-fixme'd) |
| `POST /sources`, `PATCH /sources/{id}` | `console-sources.html` Add, Edit, Pause, Resume | console | `sources.manage` | no | LE | WAT-S1 | in build: the routes are on `main`; the console Sources page is read-only in R1, so no screen calls them |
| Check now (`POST /agent-runs` with one source, or a research request in chunk 11) | `console-sources.html` Check now | console | `sources.manage` | no | LE | WAT-S1, AGT-S7 | later chunk 11 (AGT-05): the console Sources page has no Check now in R1 |
| `GET /agent-runs` | `console-health.html`; `admin-agents.html` history | both | `system.health`; `agents.manage` | no | PA; A | AGT-S5, ADM-S5 | later chunks 11 and 14, card pending; the route itself is on `main` |
| `POST /agent-runs`, `PATCH /agent-runs/{id}`, `POST /agent-runs/{id}/source-checks` | none | agent | `key:runs:write` | no | agents | AGT-S1, AGT-S9 | agent only |
| `PUT /changes/{id}/so-what`, `POST /changes/{id}/so-what/confirm` | `tenant-change.html` Rewrite, Confirm wording; also from `tenant-today.html` lead card | tenant | `cases.work` | no | CO, O; others see the label and no buttons | WAT-S7, CAS-S14 | in build: the routes are on `main` and `tenant-change.html` shows the draft with its label; Rewrite and Confirm wording are not built (WAT-S7 fixme) |

### Case workflow (chunk 9, R2)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `POST /changes/{id}/triage` | `tenant-change.html` Triage panel | tenant | `cases.triage` | no | CO | CAS-S2, CAS-S14 | later chunk 9, card pending (prototype `vChange()` triage) |
| `POST /changes/{id}/dismiss`, `POST /changes/{id}/restore` | `tenant-change.html` Dismiss with reason, Move back to triage | tenant | `cases.triage` | no | CO; reasons from vocabulary | CAS-S3, VOC-S10 | later chunk 9, card pending |
| `POST /changes/{id}/assessment/start`, `PUT /changes/{id}/assessment` | `tenant-change.html` Impact assessment | tenant | `cases.work`; contributors `cases.contribute` | no | CO, O; C saves input; `If-Match`, stale_write rendered | CAS-S4, CAS-S5, CAS-S15 | later chunk 9, card pending |
| `POST /changes/{id}/close` | `tenant-change.html` No action | tenant | `cases.work` | no | CO, O | CAS-S12 | later chunk 9, card pending |
| `GET/POST /changes/{id}/actions`, `PATCH/DELETE /actions/{id}` | `tenant-change.html` Actions | tenant | `cases.work`; update `cases.contribute` | no | CO, O, C; locked during sign-off | CAS-S6 | later chunk 9, card pending |
| `POST /changes/{id}/actions/export-tickets` | `tenant-change.html` Send as tickets | tenant | `cases.work` (needs a tracker from `admin-integrations.html`) | no | CO, O | INT-S3 | later chunk 13, card pending |
| `GET/POST /changes/{id}/evidence`, `DELETE /evidence/{id}` | `tenant-change.html` Evidence | tenant | `cases.contribute` | no | CO, O, C | CAS-S7 | later chunk 9, card pending |
| `GET /evidence/{id}/download` (streams the file, D-11, INPUT_DELTAS §7) | `tenant-change.html` Evidence | tenant | `cases.read` | no | All 7; audited per download | CAS-S7, CAS-S16 | later chunk 9, card pending |
| `POST /changes/{id}/signoff/request` | `tenant-change.html` Request sign-off | tenant | `cases.work` | no | CO, O; refused with open_actions or evidence_missing | CAS-S8 | later chunk 9, card pending |
| `POST /changes/{id}/signoff/approve` | `tenant-change.html` Sign off and close | tenant | `cases.signoff` | yes | AP; requester refused 409 | CAS-S9, CAS-S10, CAS-S15 | later chunk 9, card pending |
| `POST /changes/{id}/signoff/send-back` | `tenant-change.html` Send back | tenant | `cases.signoff` | no | AP | CAS-S10 | later chunk 9, card pending |
| `GET /changes/{id}/case-file` | `tenant-change.html` Show case file | tenant | `cases.read` | no | All 7 | CAS-S11 | later chunk 9, card pending |

### Proposals (chunk 4)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /proposals`, `GET /proposals/{id}` | `console-queue.html` | console | `proposals.review`; `key:proposals:review` (a platform key bound to an agent, D-62) | no | LE; tenant roles see "Restricted" | PRO-S7, ADM-S4 | in build (ADM-S4 un-fixme'd; PRO-S7 is fixme) |
| `POST /proposals` | agents; `admin-vocabularies.html` shared-list Suggest a change; `console-problem-reports.html` Start a proposal; `admin-vocabulary.html` console variant | agent; tenant; console | `key:proposals:write`; `proposals.create`; `proposals.review` | no | agents; CO; LE | PRO-S1, PRO-S6, VOC-S11, AUD-S5 | in build: agents and the vocabulary screens file proposals; `console-problem-reports.html` is removed (D-50) |
| `POST /proposals/{id}/approve` (corrections in the body) | `console-queue.html` Approve and apply | console | `proposals.review`; `key:proposals:review` (a key bound to a different agent from the proposer's, D-62) | yes for a person; a key never steps up | LE; an independent agent; proposer refused, 409 four_eyes_violation rendered | PRO-S3, PRO-S4, PRO-S5, AGT-S10 | in build (PRO-S3 to PRO-S5 un-fixme'd; AGT-S10 and PRO-S13 are fixme) |
| `POST /proposals/{id}/reject` | `console-queue.html` Reject with reason | console | `proposals.review`; `key:proposals:review` (D-62) | no | LE; an independent agent | PRO-S9 | in build (PRO-S9 un-fixme'd) |
| Batch proposals (re-tag, backfill; approve whole or row by row) | `console-queue.html` batch variant | console | `proposals.review` | yes | LE | PRO-S8, VOC-S12, AGT-S7 | later chunk 11, card pending |

### Search and ask (chunk 7)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `POST /search` | `tenant-search.html` | tenant | `search.use`; `key:search:read` | no | All 7 | SRC-S1, SRC-S3, SRC-S10 | in build (SRC-S1 and SRC-S3 un-fixme'd; SRC-S10 waits on Ask) |
| `POST /search/similar` | agents (find similar before registering); the near-duplicate hint in `picker-create-or-suggest.html` uses the vocabulary check, not this | agent | `key:search:read` | no | agents | AGT-S1 | agent only |
| `POST /ask` | `tenant-ask.html` | tenant | `search.use` | no | All 7; "Ask is switched off" state when the tenant disables it | SRC-S4, SRC-S5, SRC-S6, SRC-S10 | designed; the route is a stub that answers one `not_built` event |
| `POST /answers/{id}/feedback` | `tenant-ask.html` Helpful, Wrong | tenant | `search.use` | no | All 7 | SRC-S4, AUD-S4 | designed; the route is a stub that answers `not_built` |
| `GET/POST /saved-searches`, `DELETE /saved-searches/{id}` | `tenant-search.html` Saved tab | tenant | `search.use` | no | All 7 | SRC-S7 | later chunk 13, card pending |

### Home, briefing, roadmap (chunk 6)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /home` | `tenant-today.html` | tenant | any member | no | All 7; Decide now differs by permission | HOM-S1, HOM-S2 | in build (HOM-S1 and HOM-S2 un-fixme'd) |
| `GET /briefings/current`, `GET /briefings/{weekStart}` | `tenant-briefing.html`; part on `tenant-today.html` | tenant | `watch.read` | no | All 7; lead button reads Triage for `cases.triage` | HOM-S3 | in build (HOM-S3 un-fixme'd) |
| `GET /roadmap` | `tenant-roadmap.html`; Coming up on `tenant-today.html` and `tenant-briefing.html` | tenant | `roadmap.read` | no | All 7 | HOM-S4, HOM-S6, REG-S10 | in build (HOM-S4 and HOM-S6 un-fixme'd; REG-S10 is chunk 8) |
| `GET /upcoming` | none (public facts for agents and newsletters) | agent | `key:upcoming:read` | no | agents | HOM-S5 | agent only |
| `GET/POST /calendar-feeds`, `DELETE /calendar-feeds/{id}` | `tenant-calendar-feeds.html` | tenant | `roadmap.read` | create needs a recent sign-in or a step-up (D-52) | All 7; address shown once, no "Include" choice, at most 5 per person | HOM-S5 | in build: the routes are on `main`; the screen is not built (HOM-S5 fixme) |
| `GET /calendar/feed.ics?token=…` | none (the calendar client) | none | token in the query string | no | none | HOM-S5 | in build: served; HOM-S5's journey waits on the screen |

### Reports, exports, imports (chunk 12, R3)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /reports/summary`, `GET /reports/gaps`, `GET /reports/overdue-actions` | `tenant-reports.html`; Where we stand on `tenant-today.html` | tenant | `reports.read` | no | All 7 | REP-S1, HOM-S1 | later chunk 12, card pending (`vReports()` is the cut); Today's standing panel in chunk 8 |
| `POST /exports`, `GET /exports/{id}`, `GET /exports/{id}/download` (streams, INPUT_DELTAS §7) | `tenant-reports.html` exports; `tenant-change.html` case file export; `admin-data.html` | tenant | `exports.create` | yes | A, CO, AP, AU | REP-S2, REP-S3, CAS-S11 | later chunk 12, card pending |
| `POST /imports`, `GET /imports/{id}`, `POST /imports/{id}/commit` | `admin-data.html` import with dry run and mapping | tenant | `register.edit` and `vocab.manage` | no | A, CO | REP-S4 | later chunk 12, card pending |
| Tenant export and verified deletion | `admin-data.html` | tenant | `security.manage` | yes | A | REP-S5 | later chunk 12, card pending |

### Audit and AI governance

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET /audit-events` | `admin-audit-log.html` | tenant | `audit.read` | no | All 7 | AUD-S3, AUD-S7 | in build without a card: the route (offset pages and its own filters, INPUT_DELTAS) and `/admin/audit-log` are on `main`, cut from `vAudit()`; AUD-S3 is un-fixme'd |
| `GET /ai-generations` | `admin-ai-log.html` | tenant | `ai_log.read` | no | A, CO, AP, AU | AUD-S4 | in build: the route is on `main`; its screen and card are chunk 7's (AUD-S4 fixme) |
| `GET /problem-reports`, `PATCH /problem-reports/{id}` | `console-problem-reports.html` | console | `proposals.review` | no | LE | AUD-S5, PRO-S7 | removed from the console (D-50): a report stays inside the bank that filed it; the bank's own list and close are chunk 4's (AUD-03), card pending |
| `GET/POST /eval/questions`, `GET/POST /eval/runs` | `console-evaluation.html` | console | `eval.manage` | no | LE | SRC-S8 | later chunk 7, card pending |

### Collaboration (chunk 10, R2)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET/POST /comments`, `PATCH/DELETE /comments/{id}` | comments panel on `tenant-change.html`, `tenant-obligation.html` | tenant | `comments.write` | no | All 7; own comments only for edit and delete | COL-S1, COL-S5 | later chunk 10, card pending |
| `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/read-all` | `tenant-notifications.html` from the who panel | tenant | any member | no | All 7 | COL-S2 | later chunk 10, card pending |

### Integrations (chunk 13, R3)

| Operation | Card | Surface | Permission | Step-up | Role variants | E2E | Status |
|---|---|---|---|---|---|---|---|
| `GET/POST /webhooks`, `PATCH/DELETE /webhooks/{id}`, `GET /webhooks/{id}/deliveries` | `admin-integrations.html` | tenant | `integrations.manage` | no | A | INT-S1, INT-S2, INT-S5 | later chunk 13, card pending |
| `GET/PUT /integrations/tickets` | `admin-integrations.html` | tenant | `integrations.manage` | no | A | INT-S3 | later chunk 13, card pending |

## Reachability audit (playbook 7.6), to run after each wave

For chunks 2 to 7 as designed:

- Every mutation endpoint has a screen that calls it: yes for chunks 2 to 7,
  except the agent-only operations (`POST /changes`, the run API,
  `POST /search/similar`, `GET /upcoming`), which are called by the seeded
  agent in E2E (AGT-S10).
- Every list has a create path on an empty tenant: vocabularies (Add a
  value), footprint (the seeded dimensions), sources (Add a source), calendar
  feeds (New feed). The inventory, the watch feed and the queue are filled by
  agents and proposals; their empty states say so and name the next action.
- Every list has a detail: obligations, instruments, changes, proposals,
  problem reports, vocabularies.
- Every detail has an edit where the PRD allows one: vocabulary rows (inline),
  footprint (through a request), proposals (corrections before approval),
  sources (Edit). Library records have no edit on the tenant side by design;
  they have "This looks wrong".
- Every vocabulary can be managed without a deploy: tenant lists on
  `admin-vocabulary.html`; library lists through the console variant and the
  queue.

# Things that need Alex, not an agent

Ordered by what blocks testing first. Nothing here is blocked on code.

## Before the first test deploy
- [x] `docs/inputs/schema.sql` and `docs/inputs/data-model.md` (version 0.3) landed on 2026-09-19 at 09:38 together with the updated `INPUT_DELTAS.md`. Chunk 1 starts from them.
- [ ] Create the Railway project in EU West: Postgres with pgvector, Redis, a private bucket, services `api`, `worker`, `beat`, `web`. See `docs/runbooks/RAILWAY_DEPLOY.md`.
- [ ] Point a test host at the web service (for example `compliance-test.bleqq.com`) and set `WEBAUTHN_RP_ID` to it. Passkeys made on a `*.up.railway.app` host stop working the day the host changes.
- [ ] A transactional email sender on an EU region for invitation codes, with SPF and DKIM on the sending domain.
- [ ] D-09: an API key for the first embedding model to try. Until then the test deploy searches by keyword only.
- [ ] D-07: an Anthropic API key for the test environment.
- [ ] Set `TRUSTED_PROXY_HOPS=1` on the `api` service (security review F1, `docs/security/CHUNK1_AUTH_REVIEW_2026-09-19.md`). Railway's edge writes `X-Forwarded-For` (source: Railway's help station, not official docs); confirm on the test deploy that the security log shows your own address, not the proxy's, then mark the Verification_Log row verified.

## Before any real user enrols
- [ ] Confirm who adds a library flag in journey J-5. The PRD's journey says "Admin adds a flag", but a flag is a library vocabulary, so adding one is a proposal (VOC-07), and the PRD's permission table (section 6) gives `proposals.create` only to the compliance officer. The build follows the table: the compliance officer proposes, a library editor approves. If the tenant admin should propose too, say so and the admin role gains `proposals.create`.
- [ ] Confirm the passkey name list may be used. New passkeys are named from the community AAGUID list (github.com/passkeydeveloper/passkey-authenticator-aaguids, `aaguid.json` at commit `91caa53`, names only, vendored in `backend/apps/identity/data/passkey_aaguid_names.tsv`). The repository publishes no licence; its README limits use to naming passkeys in a person's own passkey list, which is exactly our use. If you would rather not rely on an unlicensed list, deleting that file is safe: passkeys then fall back to names like "Chrome on Windows" and "Security key".
- [ ] D-05: the brand layer ships placeholders (`frontend/src/styles/brand.css`, values from `design/brand/README.md`). One note from Phase 0: every dark-theme brand value is also replaced (the brief forbade any SEB value surviving). Confirm or replace it when you pick the final values. (The earlier dark negative pill workaround is gone: in dark the four status pills now use Green's own `-03` background, lowest 5.40:1, per `design/system/pills-and-labels.md`.)
- [ ] D-02: confirm the production host and RP ID.
- [ ] Playbook 6.4 lists button labels under the `microlabel` role (uppercase); the foundations amendment of ADR 0020 sets them in `body` at 500, sentence case, as shadcn does, and the app now follows the design. Confirm, or say so and buttons go back to microlabel.
- [ ] D-05: choose our own brand green and sand, and clear the use of Green with SEB given your role there.
- [x] D-14: name the first library editors. **Answered 2026-09-20 (item 19):** nobody. bleqq staffs no editorial function; an independent agent gives the second pair of eyes and the `library_editor` role stays unstaffed, for the proposals you take over yourself (D-48, ADR 0042).
- [ ] Security review F9 (medium): default taken on 2026-09-19 without waiting: adding or removing a passkey from a full session is allowed only while the session is younger than the step-up window or with a fresh step-up assertion; a sign-in or enrolment no longer counts as a step-up, so every step-up action asks for the passkey explicitly (ID-S14). Revert only if you want passkey management without a second prompt later in a session; the reasoning is in `docs/security/CHUNK1_AUTH_REVIEW_2026-09-19.md`.
- [ ] Security review F12 (medium): default taken on 2026-09-19: the enrolment code and invitation mails are sent by the worker after commit, so the neutral and sending paths take the same time. Nothing to decide unless you prefer synchronous mail on the test deploy.
- [ ] Tab bar, open question 1 (`design/system/navigation.md`; default taken on 2026-09-19): the floating bar has a 12 px radius and the current tab 6 px, because the fully rounded shape stays the pill's. iOS 26 draws a capsule-shaped bar with a fully rounded current tab. Say so if you want the capsule instead.
- [ ] Tab bar, open question 2 (default taken on 2026-09-19): the More sheet closes on a choice, Close, Escape, a tap on the scrim or a route change, not by swiping it down. Swipe to close would need vaul, whose repository says it is unmaintained, or Base UI's Drawer, a second headless library beside Radix.
- [ ] Tab bar, open question 3 (default taken on 2026-09-19): the rail starts at 1024 px, so the 13-inch iPads in portrait (1024 and 1032 px wide) get the rail, with 784 px of content beside it. Say so if they should get the tab bar; that needs a switch point above 1032 px, which is a step in neither Green nor Tailwind.
- [ ] Tab bar, open question 4 (default taken on 2026-09-19): every tab links to its section's root, as the rail does. Apple keeps each tab's place when a person switches tabs; that memory is not built.
- [ ] Tab bar, open question 5 (default taken on 2026-09-19): the rail's current row keeps its approved treatment, the neutral tint and medium weight. The current tab and the current row in the More sheet add a 1 px outline, because the tint alone measures 1.19:1 against the bar and fails WCAG 1.4.11. Say so if the rail's current row should gain the outline too.
- [ ] `<html lang>` is the build default (`NEXT_PUBLIC_DEFAULT_LOCALE`), while signed-in screens render in the person's own language. The tab bar sets `lang` on its own `nav` so its labels hyphenate and are read out in the right language. Confirm that `<html lang>` should follow the person's language, so the whole page does the same.
- [ ] Navigation checks on a real iPhone, in Safari and as a home-screen app (`design/system/navigation.md` section 18): the tab bar clears the home indicator in portrait and landscape, and landscape shows the inline bar; the page gutter clears the notch in landscape; with a hardware keyboard, the focused skip link clears the notch in landscape; Safari's toolbar tint does not pick up the bar; the keyboard hides the bar and brings it back.
- [ ] Navigation checks on a real Android phone in Chrome: with gesture navigation the tab bar clears the gesture area; the keyboard hides and restores the bar; the back gesture with More open closes the sheet along with the page.
- [ ] Navigation checks on a real iPad: portrait with and without a hardware keyboard; rotating with More open, and with the rail's account menu open, leaves nothing stuck; the rail footer clears the home indicator in landscape.
- [ ] Swedish tab labels on a real phone (E2E runs in English only): at 360 px every label fits on one line; at 320 px "Bevakning" breaks at a hyphen.
- [ ] Windows forced colours on a desktop zoomed below 1024 CSS px: the current tab still shows its outline.
- [ ] Regulatory scope, the Swedish name (default taken on 2026-09-19): the section under Admin that decides what every member sees is called **Regulatory scope**, in Swedish **Regulatorisk omfattning**, with the short forms "I vår omfattning", "Inte i vår omfattning" and "Visa utanför vår omfattning" on the list screens. Confirm the Swedish wording, or give the words you want and the message catalogs follow. Every string is in `docs/plans/briefs/REGULATORY_SCOPE.md` section 2.
- [ ] Regulatory scope, firm types and regimes: on 2026-09-19 you asked whether "Kort" belongs. It does, as two licensed activities (card issuing, card acquiring) under Payments, and the missing payment-sector permit types become legal entity types (payment institution, e-money institution, credit market company, investment firm), all verified against FI's register before seeding (REGULATORY_SCOPE.md T01). Still open, default none: a Funds regime, occupational pension company as an entity type, and relabelling "AI and ICT" to "ICT risk and AI".
- [ ] Regulatory scope, open question on a reason for each change request (default taken on 2026-09-19: not added): FP-02 does not ask for one, and four eyes, the passkey step-up and the per-term audit rows already record who changed what. If you want one, it is a column on `footprint_change_request`, required in both the API and the UI.
- [ ] Regulatory scope, open question on an admin's second identity (default taken on 2026-09-19: no code): one admin can invite a second identity they control, or grant `footprint.approve` to a new member, and then approve their own request. The check constraint cannot see this; the audit log shows the invitation or the role grant next to the approval. The alternative is refusing the approval with 409 `four_eyes_violation` when the approver's membership, or the role grant that gives them `footprint.approve`, is newer than the request. Say which you want.
- [ ] Regulatory scope, open question on Admin holding both permissions (default taken on 2026-09-19: keep it): PRD section 6 gives Admin both `footprint.request` and `footprint.approve`, so two tenant admins can change the scope with no compliance officer involved. Keep it, or narrow it in a PRD revision?

## PRD 0.3, decided by default on 2026-09-19

PRD 0.3 landed the three things you asked for in chat: My work and participants,
markets, and standards within the sector scope. The wording of the bump is
yours; everything under it is a `docs/DECISIONS.md` row (D-18 to D-47) with an
ADR (0026 to 0041), each reversible. These are the ones that need you.

- [ ] Read PRD 0.3 itself: the sharpened sector-scope paragraph, the standards
      paragraph, FP-04, HOM-05, COL-04, INV-08, WAT-07, AGT-08, REG-08, the
      amended FP-01, INV-01, INV-02, WAT-03, TEN-02, TEN-03, CAS-03, COL-01,
      COL-02, AGT-04, REG-01, HOM-03, REP-02 and ADM-01, the six new acceptance
      criteria, and the journeys J-9 and J-10. Say the word and any row goes
      back; nothing is built on them yet.
- [ ] **Private notes (D-22).** You asked for "notes on my work". The default is
      shared comments in a panel called "Comments and mentions", because every
      role holds `audit.read`, every write stores before and after values, and
      the outbox feeds webhooks and the audit stream, so nothing written the
      ordinary way is private. Real private notes would change a product
      invariant: a per-user row-level policy, audit and outbox rows without the
      text, exclusion from exports, and compliance work hidden from the tenant's
      own auditors. This one needs your decision, not a default.
- [ ] **Aspiring markets outside EU, SE, DK, NO and FI (D-33).** Which ones do
      you have in mind, and in which release? Each is a change to the platform's
      scope, not a tenant setting: it needs a jurisdiction row, its authorities,
      its sources and a content language before a sweep can find anything.
      Until then a Swedish bank can watch only Denmark, Norway or Finland.
- [ ] **The sector vocabulary, answered once (D-40).** The default names tax and
      AI in the PRD's scope sentence, maps the PRD's six sectors onto terms of
      the existing `licensed_activity` dimension by proposal, and adds a regime
      term only when an instrument needs one. Tell us whether sustainable-finance
      disclosure, consumer credit and the Accessibility Act as applied to banking
      are in scope. This is the same question the regulatory scope spec asks
      about firm types, so one answer settles both.
- [ ] **The standards seed list (D-47).** The default seeds ISO/IEC 27001:2022
      only, once its facts are fetched, with no lineage rows. Decide on ISO
      22301, ISO/IEC 27701, PCI DSS, the Swift CSCF and ISO/IEC 42001, and
      whether ISAE 3402 or SOC reports a tenant issues to its own clients are in
      scope at all.
- [ ] **A Statement of Applicability export in chunk 8 (D-46).** The default
      keeps the dated export in R3 and uses the filtered register as the SoA in
      R2. Banks need the document at a certification audit, so say if you want a
      CSV pulled forward.
- [ ] **A content licence (D-35).** The default is that the shared library holds
      a standard's public facts and one conformance duty in our own words, never
      its clause or control titles. Pursuing a licence (from a national member
      body or the publisher directly) would let the library hold more. Until you
      say so, it stays facts only.
- [ ] Design cards still to be drawn before their chunks: the "Standard" pill's
      wording and tone; the regulatory scope page's opt-in group with "None
      followed"; the "Markets we watch" panel; My work; the participants panels;
      the entity screen's "Licences and certificates"; the units list and paste
      dialog; the approver's decide-selected queue; the Statement of
      Applicability view; and a standard instrument's empty provision tree.

### Legal, before any standard is seeded

`f03-T34` fetched these facts on 2026-09-19 and logged them in
`docs/plans/Verification_Log.md`, section "PRD 0.3 standards facts". The
questions below are still yours: they ask what the terms **allow us to do**,
which no page answers. ISO's own terms could not be read at all (every
`www.iso.org` URL answers HTTP 403), so the ECLA claims in the standards
analysis stay unverified.

The strictest terms we did read: SFS forbids developing or training AI with the
content of standards; IEC and PCI SSC forbid derivative works; Standard Norge
needs a paid reproduction agreement for any excerpt. All of them are consistent
with D-35, which keeps clause and control text out of the library.

- [ ] May the library store and show a standard edition's official title and our
      one-sentence conformance duty?
- [ ] Does automated monitoring of a publisher's catalogue page, keeping a URL, a
      date and a content hash and no snapshot, respect its site terms and its
      text-and-data-mining reservation? Which publishers may be read
      automatically? The default reads none until you say so, so a revision opens
      no case until one is cleared.
- [ ] Before the first bank uses units: is a bank's list of clause and control
      references with its own titles, held in our service, "internal reference"
      or "integration into a compliance system", for the bank and for us? Is a
      person's paraphrase a derivative work? Does a support-access grant (TEN-06)
      to unit text count as disclosure? If the answer is no, chunk 8 ships
      without the unit table and the conformance row per entity still works.
- [ ] What the payment-card and messaging-scheme terms allow, and what the Nordic
      member-body licences cover.
- [ ] Terms of service: a clause making each tenant responsible for its own
      standards licences and for any licensed material it uploads as evidence,
      plus a takedown process.

### Outside facts: fetched, and the five that no site would give us

`f03-T34` fetched every fact of `STANDARDS.md` section 9 on 2026-09-19 and wrote
them into `docs/plans/Verification_Log.md` with their URLs. The ISO/IEC 27001
edition and amendment, the Annex A rule, the IAF MD 26 transition dates, the
Nordic adoptions, the PCI DSS version and its retirement practice, and the terms
of IEC, PCI SSC, SIS, DS, Standard Norge, SFS and Global ACI are all verified
there. Five are logged as **not verified**, each with its reason, and each one
needs a person or a different route:

- [ ] **ISO's licence terms and its text-and-data-mining reservation.** Every
      `www.iso.org` URL answers HTTP 403, `robots.txt` included. Someone has to
      read the ECLA and the site terms in a browser.
- [ ] **ISO's systematic review cycle.** Same 403; `www.iec.ch` too. Nothing in
      the product may schedule a review from an assumed cycle until this is read.
- [ ] **The ISO stage code and the ISO catalogue page.** Same 403. The IEC
      webstore serves the joint ISO/IEC catalogue instead, but gives a status
      word, not a stage code, and offers no feed of any kind.
- [ ] **ISO/IEC 17021-1's certification cycle.** Paid text. The three-year cycle
      is logged from IAF MD 5, which governs QMS, EMS and OH&SMS, not ISMS.
- [ ] **The Swift CSCF version and attestation window.** Every `swift.com` and
      `www2.swift.com` URL answers HTTP 403. The Swift CSCF stays out of the seed.

One fact worth knowing before the seed is written: **IAF no longer exists.**
Global ACI took over the roles of IAF and ILAC on 1 January 2026, and IAF's
mandatory documents stay valid only until equivalent Global ACI documents are
adopted. The ISO/IEC 27001:2022 transition MD 26 describes ended on
31 October 2025.
- [ ] Agent definitions are read at seed time by a small reader in `backend/apps/agents/seeds/definition.py` instead of PyYAML, because PyYAML is a development dependency, the image installs `--only main`, and `seed_reference` runs on every deploy; changing dependencies was outside the package. It reads the five scalar fields the `agent` row needs and refuses anything else, and a test parses the same file with PyYAML and demands the two agree. Say the word and PyYAML moves to the main dependencies, after which the reader is deleted and the seed loads the whole definition — which is what chunk 11 needs anyway, when tools, budgets and vocabularies become columns.

## Before the first bank tenant
- [ ] D-07: contract an EU-pinned inference path.
- [ ] D-15: switch to `staging` and `main` with a second reviewer.
- [ ] Independent penetration test. Certification path (ISO 27001 or SOC 2).
- [ ] DPA, master agreement with the DORA Article 30 provisions, subprocessor list, insurance.
- [ ] Sentry on its EU region, or decide against it.
- [ ] The design for the screens the prototype lacks (`design/README.md`), if you want to shape them before the agent does.
- [ ] Overlay motion (tab bar open question 6): `Modal` and the More sheet open and close without animation, so the two stay consistent. Say if you want motion, and it is added to both together.
- [ ] Dark-theme screenshots of the tab bar and the More sheet, once the app has a real theme switch. Until then the dark tokens exist only under `.dark`, nothing sets that class, and `contrast.test.ts` pins the dark values instead.

## Decisions the parallel build waits on (docs/plans/PARALLEL_PLAN.md section 7)

**Answered 2026-09-19.** q-Q1: problem reports stay inside the bank, and the watch agents find library deviations themselves; retention was changed to "10 years after last use" with two details to confirm. Alex also decided that bleqq's own agents, the general finance regulation watch, are part of the base package and cannot be changed by a tenant; a tenant adds its own agents for its specific needs (item 14). The answers and what they mean are in `docs/plans/briefs/OWNER_RECOMMENDATIONS.md`, section "Alex's answers".

Each involves a product invariant, so it waits for you rather than a default. A row marked **Answered** is kept for the record and blocks nothing. "Needed by" counts hours from the plan's start on 2026-09-19 evening; answers by hour 6 cost nothing. The main agent's recommendation for the first four is in the chat of 2026-09-19.

| Key | Question | Blocks | Needed by | If late |
|---|---|---|---|---|
| q-urgency | Is urgency's tone fixed by its ordinal? Option A: the rows are fixed, create is refused, and only labels and SLA days can be edited. Option B: an editor may add a level and pick its tone, which lets a person choose a pill tone. This is chunk 3's NFR-S10 question | `c3-urgency-rule`, and through `c5-fe-watch-data-layer` every watch and case screen that shows urgency; NFR-S10's status | hour 1.4 | NFR-S10 stays in progress. The watch screens wait from about hour 8, and R1 moves with them |
| q-Q1 | **Answered 2026-09-19.** How may platform staff read and resolve tenants' problem reports? They may not: a bank's reports stay inside the bank, and the watch agents find library deviations themselves | nothing waits: `c4-report-window` is gone and the chunk 4 report packages are replanned for the answer (PARALLEL_PLAN section 3.3.1). AUD-03 is built in that shape | — | — |
| q-search-fence | Is `search_chunk` a LibraryModel, with `search/indexing.py` on the library-fence allowlist, or a derived model with its own write guard? H7 applies either way: the index carries the owner and its own row-level security | `c7-search-index`, and through it hybrid search, `POST /search/similar`, Ask, J-7 and R1 | hour 6 | Chunk 7 has about an hour of slack. After that, each hour late moves R1 by about an hour. Ruling 4's fallback unblocks chunk 5, not chunk 7 |
| q-feed-token | The calendar feed token sits in the feed URL, so the hosting edge's logs hold it. That is the class of problem fixed for invitation tokens (F29, e604de7). Accept it with rotation, or change the design? | `c6-upcoming-calendar-backend`, `c6-calendar-feeds-screen` | hour 11 | Chunk 6 cannot close, and R1 waits |
| q-support-access | Who grants support access? TEN-S6 says a tenant admin, while PRD section 6 gives `support_access.grant` to the platform admin. Is it read-only in R2? How does the console name the tenant? | `c8-card-people-access`, `c8-ten-support-grants`, `c8-support-access-mechanism`, `c8-ui-support-access`, `c10-j8-extension` | hour 4 | Those packages wait, and chunk 8 closes with TEN-06 named open |
| q-retention | Is retention set per tenant for cases, evidence and audit (AUD-04), and how does a purge treat append-only tables? The earlier default purged notifications only, which cuts AUD-04 | `c12-retention-contract`, `c12-retention-purge`, `c12-fe-data-retention`, `c12-config-policies` | hour 22 | Those packages wait, and chunk 12 closes with AUD-04 open |
| q-eu-guards | Which processing locations outside the EU should the production boot refuse? | `c14-eu-data-location` | hour 27 | That package waits |
| q-credential | Does a stricter credential policy apply at sign-in, so existing synced passkeys stop working, or only when a passkey is registered? | `c11-credential-policy` | hour 28 | Chunk 11 closes with the credential policy named open |
| q-exit | Does tenant deletion need four eyes as well as step-up? May deletion remove append-only audit rows, or are they kept, and on what GDPR basis for the names in them? | `c12-exit-deletion`, and through it `c12-exit-export` and `c12-fe-data-exit` | hour 28 | Tenant exit waits, and chunk 12 closes with it open |
| q-private | Who approves tenant-private instruments and obligations (a PRD section 6 bump)? May private text reach a model or the embedder? May a private source start without review? | `c13-private-*`, their screens and `c13-e2e-private` | hour 33 | WAT-06 and INV-07 are cut and named |
| q-sso | How does SSO sit beside "a passkey is the only way in"? Does SSO replace the enrolment code? May a member with a passkey sign in by SSO? What does `enforce_sso` mean? | `c13-sso-*`, `c13-scim`, `c13-fe-sso`, `c13-e2e-identity-admin` | hour 34 | ID-12 is cut from R3 and named |
| q-platform-counters | May the console show per-tenant stream lag, failed jobs and usage through a narrow audited read? Or does each tenant alone see its figures? | `c14-billing-usage`, `c14-health-backend` | hour 38 | Tenant-only figures, and the console shows platform rows only |

## Questions your two decisions of 2026-09-19 raise (problem reports, agents)

Nothing waits for these: the replan of 2026-09-20 took a default for each and says so in
`docs/plans/briefs/CHUNK4_TASKS.md` and `docs/plans/PARALLEL_PLAN.md` section 3.3.1.
Change any of them and the answer changes a task, not an invariant.

**Problem reports (your item 3)**

- [ ] **Should a bank's compliance officers see each other's reports?** Default: **yes**,
      under one permission. A holder of `proposals.create` (the compliance officer today)
      lists and closes every report of their own bank; every other member sees and closes
      only their own, under `problems.report`, which everyone holds. That adds no
      permission and leaves PRD section 6's matrix alone, as D-19 did for participants. A
      dedicated `problems.manage` would be a PRD section 6 bump; say the word.
- [ ] **How does a report close?** Default: the reporter or a permitted colleague sets
      `answered`, `fixed` or `rejected` with a required note, using the kinds chunk 3
      already wrote. No close-reason vocabulary is added.
- [ ] **Does the reporter get a notification when their report is closed?** Default: no.
      They see the state on the record, and on My work once chunk 8 builds it.
      Notifications are chunk 10, and adding one there is small.
- [ ] **PRD wording.** ADM-02 still lists "problem reports" among the platform console's
      surfaces, and AUD-03 reads "Problem reports resolved by a proposal, closing the loop
      to the agents". Both describe the console loop your answer removes. The session that
      lands the decision owns `PRD.md`; the same goes for AUD-S5 and ADM-S4 in
      `backend/apps/governance/app.md`.
- [ ] **Where does a bank see that a library record it doubted was corrected?** Default:
      Library updates, like any other library change. The watch agents' re-check (chunk 5)
      produces an ordinary proposal, which carries no bank's words.

**Agents (your item 14)**

- [ ] **A bank's research request with no agent of its own.** Default: refused, because a
      bank cannot command bleqq's general agents. The alternative is to let a request run
      on a bleqq agent within a quota, which is more product than AGT-05 asks for.
- [ ] **Who pays for bleqq's watch?** Default: bleqq. A bank's monthly cap and its AI off
      switch cover its own agents and Ask; the general finance regulation watch keeps
      running whatever a tenant sets, because it feeds the shared library.
- [ ] **What may a bank see of bleqq's watch?** Default: a read-only panel with each
      general agent's name, purpose, the jurisdictions it sweeps and its check cadence —
      no prompts, tools, budgets, run rows or costs.
- [ ] **AGT-04's wording.** PRD AGT-04 and `backend/apps/agents/app.md` say "a tenant admin
      controls which agents are on", which now means the bank's own agents only. The
      wording needs a line saying so; the decision session owns both files.

## Questions your decision of 2026-09-20 raises (item 19, no editors)

Nothing waits for these: the consolidation of 2026-09-20 took a default for each and says so in
`docs/plans/briefs/NO_EDITORS_CONSOLIDATION.md`, `docs/DECISIONS.md` D-48 and ADR 0042. Change
any of them and the answer changes a task, not an invariant — except the last two, which would
change what four eyes means and are marked as such.

- [ ] **May a bank see which agent confirmed a fact?** Default: **yes**. The record's provenance
      names the proposing and the confirming agent, exactly as it already names an agent proposer,
      and the screen labels it machine-confirmed. The alternative is to show only "machine-
      confirmed" without naming the agents, which is one field fewer in the read and no other
      change.
- [ ] **What happens to a proposal no agent confirms?** Default: **nothing** — it stays open in
      the queue for ever, as an unreviewed proposal does today. No expiry, no auto-approval, no
      escalation. If you want a window (for example, "unconfirmed after 14 days appears on the
      console's own list"), it is a setting and a console filter, not a new state; an
      auto-approval after a window would remove four eyes and is a stop-and-ask.
- [ ] **How many independent agents read the library?** Default: **one confirming definition** to
      start, beside the sweeper and the re-check. "Several agents reading the library" is already
      true of those three; a second confirming definition, or one per record kind, is a chunk 11
      question.
- [ ] **Must the confirming agent differ in more than its definition?** Default: a different
      definition, prompt and key; the same model and provider are allowed. Requiring a different
      model would be a real independence gain and a cost and latency change, and it needs D-07's
      EU path settled first.
- [ ] **Does J-4 stay the golden path as written?** Default: **yes**, unchanged — "an agent
      registers a change and a proposal, the library editor approves in the console, the tenant
      sees what changed". It is the intervention path and it stays tested end to end. The
      agent-confirmed path is `PRO-S12`, whose journey half waits for chunk 5. Say the word if the
      agent path should become the journey and the person's path the variant.
- [ ] **Should any change still need a person?** (Would change what four eyes means.) Default:
      **no** — every proposal kind may be confirmed by an agent. A carve-out is defensible for a
      first-of-its-kind instrument, a retirement, or anything carrying a standard's term, and it
      would be one list in the approval logic.
- [ ] **Is an agent's approval enough for a record a bank relies on?** (Would change what four
      eyes means.) Default: **yes**, with the labelling that goes with it: machine-confirmed, both
      agents named, and the bank answering for its own interpretation. If a vendor review or a
      supervisor expects a person behind every library fact, staffing `library_editor` again is a
      staffing change and no rework — which is why the queue is built once, for both kinds of
      approver.

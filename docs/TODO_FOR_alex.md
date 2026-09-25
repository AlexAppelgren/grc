# Things that need Alex, not an agent

Ordered by what blocks testing first. Nothing here is blocked on code.

## R2 starts: what waits for you (2026-09-25, `r2-plan-docs`)

R2 is planned and its first wave is running. `docs/plans/briefs/R2_CROSS_CUTTING.md` holds
the rules every R2 package shares. Nothing below stops the build: each question has a
default the packages take, and each answer changes a task, not an invariant already built.

**Owner questions this plan raises** (default taken in brackets):
- [x] **Tenant text to a model.** May free text a bank types (a note, an assessment, a
      comment) reach a model in a tenant agent run? (Default: no. A tenant run gets keys
      only until you answer; `R2_CROSS_CUTTING.md` (n), D-07, D-89.) **Answered (Alex, 2026-09-25): yes, guarded, as a second named exception beside Ask (D-98).**
- [x] **The control inventory.** What a bank's controls are and where their list comes from,
      for the D-89 controls work. (Default: `d89-controls` builds the shape its brief names and
      seeds nothing real.) **Answered (Alex, 2026-09-25): a REG-05 internal item of the control kind (D-99).**
- [x] **Agent-confirmed links count for My work (D-97).** A WAT-04 link an independent agent
      confirmed under D-74 now counts for "changes on your items", beside a person's
      confirmation; an unconfirmed suggestion never does. (Default: D-25 amended as D-97 says.) **Answered (Alex, 2026-09-25): default taken (D-97).**
- [x] **The re-tag batch's agent path.** Whether an agent may file a re-tag batch as well as a
      person in the console. (Default: `CHUNK11_TASKS.md` as written, the console form only.) **Answered (Alex, 2026-09-25): default taken: a person decides a batch now; the agent path is a follow-on.**
- [x] **The authenticator list source.** Where a bank's allowed authenticators (AAGUIDs) come
      from: typed in by the bank, or taken from the FIDO metadata service. (Default:
      `CHUNK11_TASKS.md`'s sign-in policy, a list the bank types.) **Answered (Alex, 2026-09-25): not in R2; the device-bound policy moves out and banks can still require passkeys (D-100).**
- [x] **TEN-04 moves to chunk 10 (D-95).** Out-of-office with a delegate is built beside the
      reminders, escalation and delegation that read it. (Default: chunk 10; say the word and it
      goes back to chunk 8's cuttable list.) **Answered (Alex, 2026-09-25): default taken (D-95).**
- [x] **When a banking group's scope is built (D-69, D-96).** (Default: as
      `r2-banking-groups-brief` sets it in D-96.) **Answered (Alex, 2026-09-25): default taken (D-96).**
- [x] **Search scope in R2 (D-10).** D-10 kept tenant content out of search in R1 and put the
      question at R2. (Default: still library only; no tenant text is embedded.) **Answered (Alex, 2026-09-25): default taken: library only through R2 (D-10).**
- [x] **ADM-02's languages (D-94).** Which content languages the console's jurisdiction and
      translation surfaces carry. (Default: as `x-jurisdictions-by-proposal` sets it in D-94.) **Answered (Alex, 2026-09-25): default taken (D-94).**
- [x] **Evidence upload and the scanner.** That evidence arrives by multipart through the API
      rather than a presigned PUT (`CHUNK9_TASKS.md` ruling 4), and that the R2 deploy needs a
      `clamd` service (`PARALLEL_PLAN.md` §7.3). (Default: multipart; a deployed environment
      with no scanner refuses to store a file.) **Answered (Alex, 2026-09-25): multipart confirmed (D-101). Provisioning clamd is your own action, below.**
- [x] **PRD 0.7's OWN group (D-91).** Confirm the ownership requirements as `r2-spec-d89`
      writes them into the PRD. (Default: as D-91 and ADR 0059 say.) **Answered (Alex, 2026-09-25): default taken (D-91), with D-98 and D-99.**

**Your own action:**
- [ ] **Provision `clamd` in Railway EU West (D-101).** Until it runs, a deployed environment
      refuses every evidence file with 503 `scanner_unavailable`.

**Non-blocking defaults already taken**, each in the brief that holds it:
- Chunk 9's four (the evidence allow-list and 25 MB cap, every `cases.read` holder downloads,
  sub-statuses without a route, the scanner refusal at first use): `CHUNK9_TASKS.md`,
  "Not questions". q-case-close is answered, Option B (D-92).
- Chunk 10's: `CHUNK10_TASKS.md`, "DEFAULTS TAKEN" and "Open questions"; `c10-close` copies
  them here.
- Chunk 11's, plus every plan limit as a setting until plans exist: `CHUNK11_TASKS.md`,
  "Defaults taken"; `c11-chunk-close` copies them here.
- Agent access's: `docs/plans/briefs/AGENT_ACCESS.md` and the D-73, D-76 and D-77 items in
  "Landed from `origin/claude/r1-integration`" below.

**CLAUDE.md edits only you make:**
- [ ] Sections 3 and 5: the agent access text already listed under "Landed from
      `origin/claude/r1-integration`" (a) below.
- [ ] Section 11: the golden paths are J-1 to J-12 as `@smoke`, per PRD section 5; the file
      still says J-1 to J-8. (The PRD on `main` stops at J-11; J-12 arrives with PRD 0.7 from
      `r2-spec-d89`.) The journey titles for J-9 (HOM-S13), J-10 (REG-S16) and J-11
      (ACC-S13) already carry `@smoke`.

## R1 is closed: what waits for you (2026-09-24, `r1-close-and-readiness`)

R1's code is on `main` and its gates are green; what is left is yours. The four that block
the first real test, then every open box a package added on 2026-09-23 and 2026-09-24.

**Owner-blocked, before a test deploy is worth running:**
- [ ] **D-07, the model key.** An Anthropic API key for the test environment, plus the cost of
      a run and your approval that a reader's typed Ask question may reach that endpoint there
      (`k-anthropic`). Until then Ask, the "So what?" draft and the confirming agent run on the
      mock, and the real-model timings of NFR-02 are not measured.
- [ ] **D-09, the embedding key and the retrieval baseline.** An API key for the first
      embedding model. The retrieval track of the release gate (SRC-05) is wired and
      **unrecorded**: a retrieval regression does not fail CI until the baseline is recorded
      with that key (`c7-embedder-selection-baseline`). Search runs by keyword and mock vectors
      until then.
- [ ] **The test deployment.** The Railway project, the test host and `WEBAUTHN_RP_ID`, the
      EU mail sender and `TRUSTED_PROXY_HOPS` ("Before the first test deploy" below). Every R1
      requirement reads `built`; none reads `verified` until you exercise it there.
- [ ] **Legal on standard titles.** "Legal, before any standard is seeded" below: what the
      publishers' terms allow. ISO/IEC 27001 exists for tests and E2E only until you answer.

**Security, the one medium finding still open:**
- [x] **H33: must two agents' keys come from two people?** Answered 2026-09-24 in chat:
      "Current state is fine". H33 is a cut you accepted (D-89): independence is checked by
      definition and key, platform admins are trusted, and the audit trail names who minted
      each key.

**Every open box added on 2026-09-23 and 2026-09-24**, each explained in its own section below:
- security-review-c4: console tenant creation takes no step-up.
- lib-instrument-card-fixes: the lineage headings' wording.
- vocab-term-provenance: the risk that comes with D-79's lift.
- proposals-reads-agent-visible: which version an open proposal is compared with.
- agent-flow-run-guards: an agent's key must name an open run of its own; finding similar records names no run.
- agents-confirmer-definition: the confirming agent's self-reported metadata; `library-confirmer` ships with no labelled evaluation case (v2 stays a draft until its evaluation rows exist); an open proposal's reason is kept nowhere; `AgentDecision` on the approve and reject bodies; whether a bank reads the confirming agent's reasoning.
- agents-sector-scope-eval: the two AGT-08 tolerances.
- search-eval-gate: the unrecorded retrieval track (the D-09 item above).
- tax-jurisdiction-derivation: where a record's derived jurisdictions show.
- search-ask-backend: Ask sends a reader's question to the model.
- i18n-en-sv-switch: how a person picks their interface language.
- api-docs-identity-auth: the passkey prompt's two-minute limit; re-enrolment signs out in one bank only.
- watch-curation-confirm-backend: a person's confirmation needs a fresh passkey; both agent names on a machine-confirmed fact; a library editor's own filing is a suggestion; nobody confirms their own filing.
- tax-nordic-seed: Folketinget as an authority.
- lib-standard-e2e-seed: the default taken until the legal answer; the national-adoptions note.
- ai-log-read: a library "So what?" shows the reading bank's own review.
- proposals-kind-instrument-obligation: no citation table; approval does not stamp "last verified"; `update_obligation` and `retire_record` not built; an agent's approval of a new record; a new instrument in the bank's library updates.
- watch-regime-required: a run's classification as AI output; every change names a regime and a merge is exempt.
- ask-screen: an answer the model stopped at its length limit.
- std-journeys: `seed_e2e` and the standard (D-85).
- watch-standards: which publishers no run reads; ISO/IEC 27001 seeded active on a new database only; `licensed_text` has nothing to refuse.
- ask-standard-no-answer: Ask answers nothing about a standard.
- r1-int-w23: the evaluation set's own library door and the merge approval's watch door (D-87).
- security-review-c7: may a bank's search text reach the embedder and the reranker.
- r1-close-and-readiness (the end of this file): chunk 6's three confirmations and chunk 7's two.

## Before the first test deploy
- [x] `docs/inputs/schema.sql` and `docs/inputs/data-model.md` (version 0.3) landed on 2026-09-19 at 09:38 together with the updated `INPUT_DELTAS.md`. Chunk 1 starts from them.
- [ ] Create the Railway project in EU West: Postgres with pgvector, Redis, a private bucket, services `api`, `worker`, `beat`, `web`. See `docs/runbooks/RAILWAY_DEPLOY.md`.
- [ ] Point a test host at the web service (for example `compliance-test.bleqq.com`) and set `WEBAUTHN_RP_ID` to it. Passkeys made on a `*.up.railway.app` host stop working the day the host changes.
- [ ] A transactional email sender on an EU region for invitation codes, with SPF and DKIM on the sending domain.
- [ ] D-09: an API key for the first embedding model to try. Until then the test deploy searches by keyword only.
- [ ] D-07: an Anthropic API key for the test environment.
- [ ] Set `TRUSTED_PROXY_HOPS=1` on the `api` service (security review F1, `docs/security/CHUNK1_AUTH_REVIEW_2026-09-19.md`). Railway's edge writes `X-Forwarded-For` (source: Railway's help station, not official docs); confirm on the test deploy that the security log shows your own address, not the proxy's, then mark the Verification_Log row verified.

## security-review-c4 (chunk 4 security review, 2026-09-23)
- [x] **Must two agents' keys come from two people?** Answered by Alex in chat on 2026-09-24: "Current state is fine" (D-89); H33 is an accepted cut. Found as M5 (`docs/security/CHUNK4_REVIEW_2026-09-23.md`). Since D-14's answer an independent agent is the library's whole second pair of eyes, and today one platform admin can mint the proposing key and the reviewing key and so alone push a change into the library. Default proposed, not built (H33): a `proposals:review` key only for an active agent of kind `review`, never beside `proposals:write`, and a key decision refused when the same person minted both keys or proposed the change. Say yes, or say that one admin minting both keys is acceptable.
- [x] **May an independent agent approve a brand-new record?** Settled on main before this review merged (wave 4 integration, 2026-09-24): D-79 opens `new_instrument` and `new_obligation` to an agent, because both records carry `verified_origin` and `verified_by_agent`, and keeps `new_provision` and `new_provision_version` for a person, because a provision and its versions have no column to name a confirming agent. Both provision kinds are pinned refused to an agent by a test (`tests_kinds.NewProvision`). Confirmed by Alex in chat on 2026-09-24 (D-89): "an agent can always add things to the library, and then another agent can verify it".
- [ ] **Console tenant creation takes no step-up** (T7, playbook 4.2), while CLAUDE.md section 5 puts role changes behind one, and this call hands an administrator role to an outside address. Default kept: no step-up. Say if it should ask for one.

## Found by the cold-start journey (2026-09-20)
- [ ] `bootstrap_platform` prints the one-time enrolment link to the shell as well as emailing it, and `FIRST_RUN_SETUP.md` said it "prints nothing secret". The runbook now says what it is and warns you to close the shell afterwards, and the cold-start journey reads the printed link, which is how it can enrol the first admin before any mail sender is proven. Decide whether the deployed command should keep printing it: dropping the line would make step 4 depend on a working mail sender on the first day, and the journey would read the mock outbox instead.
- [x] A brand-new bank's Watch tab answered "Not found" before chunk 5. **Corrected in the review of `645b1c3..2492f80`:** `/watch` has its route now, with the feed's own empty state, as Roadmap and Search have theirs, so a first-run demo no longer shows it. Nothing for you here; the cold-start journey's watch step is still a `test.fixme` naming chunk 5 and is engineering's to turn on.

## Before any real user enrols
- [ ] Confirm who adds a library flag in journey J-5. The PRD's journey says "Admin adds a flag", but a flag is a library vocabulary, so adding one is a proposal (VOC-07), and the PRD's permission table (section 6) gives `proposals.create` only to the compliance officer. The build follows the table: the compliance officer proposes, a library editor approves. If the tenant admin should propose too, say so and the admin role gains `proposals.create`.
- [ ] Confirm the passkey name list may be used. New passkeys are named from the community AAGUID list (github.com/passkeydeveloper/passkey-authenticator-aaguids, `aaguid.json` at commit `91caa53`, names only, vendored in `backend/apps/identity/data/passkey_aaguid_names.tsv`). The repository publishes no licence; its README limits use to naming passkeys in a person's own passkey list, which is exactly our use. If you would rather not rely on an unlicensed list, deleting that file is safe: passkeys then fall back to names like "Chrome on Windows" and "Security key".
- [ ] D-05: the brand layer ships placeholders (`frontend/src/styles/brand.css`, values from `design/brand/README.md`). One note from Phase 0: every dark-theme brand value is also replaced (the brief forbade any SEB value surviving). Confirm or replace it when you pick the final values. (The earlier dark negative pill workaround is gone: in dark the four status pills now use Green's own `-03` background, lowest 5.40:1, per `design/system/pills-and-labels.md`.)
- [ ] D-02: confirm the production host and RP ID.
- [ ] Playbook 6.4 lists button labels under the `microlabel` role (uppercase); the foundations amendment of ADR 0020 sets them in `body` at 500, sentence case, as shadcn does, and the app now follows the design. Confirm, or say so and buttons go back to microlabel.
- [ ] D-05: choose our own brand green and sand, and clear the use of Green with SEB given your role there.
- [x] D-14: name the first library editors. **Answered 2026-09-20 (item 19):** nobody. bleqq staffs no editorial function; an independent agent gives the second pair of eyes and the `library_editor` role stays unstaffed, for the proposals you take over yourself (D-62, ADR 0054).
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
- [x] **Private notes (D-22).** Answered YES on 2026-09-19: no private notes, the
      recommendation as written (D-60). ADR 0028 moves to accepted; the original
      question is kept below for the record. The default is
      shared comments in a panel called "Comments and mentions", because every
      role holds `audit.read`, every write stores before and after values, and
      the outbox feeds webhooks and the audit stream, so nothing written the
      ordinary way is private. Real private notes would change a product
      invariant: a per-user row-level policy, audit and outbox rows without the
      text, exclusion from exports, and compliance work hidden from the tenant's
      own auditors.
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
      the entity screen's "Licences and certificates"; and a standard
      instrument's empty provision tree. (c8-cards-register, 2026-09-25: the units
      list, the paste dialog and the Statement of Applicability view are drawn in
      `design/screens/tenant-obligation-units.html`; the decide-selected queue is
      struck, because D-75 leaves nothing to decide in bulk.)

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
- [ ] Dark-theme screenshots of the tab bar and the More sheet. The app already follows the system's dark setting (next-themes puts `dark` on `<html>`; there is no switch in the app), so they can be taken now. Until you ask for them, `contrast.test.ts` pins the dark values and the NFR-S9 journey measures them in a browser under a dark system theme.

## PRD 0.4, from your answers of 2026-09-19

- [ ] Read PRD 0.4 itself: the version row, ID-02 and ID-12 (SSO), INV-07,
      PRO-03 and AUD-03 (private records and problem reports), WAT-01 and
      WAT-06, AGT-03, AGT-04 and AGT-05 (whose agents a bank changes), AUD-04
      (retention), REP-04 (tenant exit), ADM-02 (the console loses its
      problem-report surface) and the one new permission,
      `private_records.approve`. Say the word and any row goes back; nothing is
      built on them yet.

## Decisions the parallel build waits on — all answered (2026-09-20)

You answered all twelve on 2026-09-19, and added a thirteenth of your own about
whose agents a bank may change. Nothing in the parallel plan waits on a decision
any more. What each answer means is a row in `docs/DECISIONS.md` (D-48 to D-61)
with an ADR (0042 to 0053), the researched detail is in
`docs/plans/briefs/OWNER_RECOMMENDATIONS.md`, and everything the answers changed
is listed in `docs/plans/briefs/PRD_0_4_CONSOLIDATION.md`. PRD 0.4 carries the
five that change the product: support access, private records, SSO, retention
and tenant exit, plus problem reports and the agents.

- [x] q-urgency (D-48), q-support-access (D-49), q-search-fence (D-51),
      q-feed-token (D-52), q-eu-guards (D-54), q-credential (D-55), q-exit
      (D-56), q-private (D-57), q-sso (D-58), q-platform-counters (D-59) and
      q-private-notes (D-60): the recommendation as written.
- [x] q-Q1 (D-50): your answer replaced it. A problem report stays in the bank,
      and the watch agents re-check the library on every run and propose the
      correction.
- [x] q-retention (D-53): your answer replaced it. Ten years after a record's
      last use, one period for every bank.
- [x] The agents question you raised yourself (D-61): bleqq's agents are the
      base package and no bank changes them; the tenant controls are for the
      agents a bank adds for itself.

The table below is the record of what each question blocked while it was open. Every row is answered now and none of them blocks anything. "Needed by" counted hours from the plan's start on 2026-09-19 evening. The main agent's recommendation for the first four is in the chat of 2026-09-19.

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

## Open details from those answers

Nothing is blocked: each has a default the build uses, stated below. Say the
word and any of them changes.

- [ ] **What counts as "use" for retention, and whether the ten years can move
      (D-53).** The default: the latest of closure, removal, a change, or a
      reference from a live record, and a read never counts; and one fixed
      period that a bank cannot change. Needed before `c12-retention-contract`
      starts, because every tenant table must say what its "last use" is.
- [ ] **Whether bleqq's own editors may read problem reports (D-50).** We read
      "in the bank only" as covering bleqq too, so no editor, agent or model
      reads a report and the console has no problem-report surface. If you meant
      that bleqq may read them, say so before chunk 4's tail is rebuilt.

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
- [ ] **Should `problem_report.tenant` become NOT NULL?** Default: **no, leave it
      nullable for now.** Since your item 3 no report belongs to the library, so a row
      with no tenant is dead shape — and under the mixed policy it would be readable by
      every bank. The writer already refuses one (`create_report` takes a tenant, not an
      optional one) and the route cannot reach it, so nothing can write one today. Making
      the column itself NOT NULL means taking `problem_report` out of the five mixed
      tables named in `docs/CONVENTIONS.md` section 11 and in `MIXED_TABLES` in
      `backend/apps/shared/tests_rls.py`, replacing its policies and rewriting the guards
      that build and probe a tenant-less row. That is a change to the two-zone contract,
      so it waits for you. No data migration is involved: nothing has ever written a row.
- [ ] **How does a report close?** Default: the reporter or a permitted colleague sets
      `answered`, `fixed` or `rejected` with a required note, using the kinds chunk 3
      already wrote. No close-reason vocabulary is added.
- [ ] **Does the reporter get a notification when their report is closed?** Default: no.
      They see the state on the record; My work lists no problem reports.
      Notifications are chunk 10, and adding one there is small.
- [x] **PRD wording.** Done in PRD 0.4: AUD-03 now reads "A problem report stays inside
      the bank that filed it", ADM-02 lists no problem-report surface, and AUD-S5 and
      ADM-S4 in `backend/apps/governance/app.md` follow.
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
- [x] **AGT-04's wording.** Done in PRD 0.4: AGT-04 in `PRD.md` and in
      `backend/apps/agents/app.md` now reads "the agents a bank adds for itself", and says
      such an agent writes only in its own tenant's zone.

## Questions your decision of 2026-09-20 raises (item 19, no editors)

Nothing waits for these: the consolidation of 2026-09-20 took a default for each and says so in
`docs/plans/briefs/NO_EDITORS_CONSOLIDATION.md`, `docs/DECISIONS.md` D-62 and ADR 0054. Change
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
      agent-confirmed path is `PRO-S13`, whose journey half waits for chunk 5. Say the word if the
      agent path should become the journey and the person's path the variant.
- [x] **Who confirms a watch item's curation now?** (Your item 16, `q-editor-confirm`.)
      **Answered 2026-09-21: an agent of a different definition and key confirms, and the item
      reads machine-confirmed** (D-74). The backend is built (`watch-curation-confirm-backend`,
      2026-09-24): `POST /changes/{changeId}/confirmation`, the agent and key columns on a
      change's type, flags, scope terms and obligation links (watch 0002), and the
      machine-confirmed provenance on every read a bank or the console makes, the roadmap
      included. The 501 `not_built` answers are gone. The write goes through the **watch door**
      rather than the proposal door, so it adds no second exception to the library invariant.
      What differs from the note that stood here: a confirming agent's key never steps up, but
      a **person** who confirms or overturns a fact does, with a passkey (see the defaults under
      `watch-curation-confirm-backend` below). The console's Confirm control, its seed and the
      WAT-S4 journey are `watch-curation-confirm-frontend`'s.

      Still worth your eye, but not blocking: a curation confirmation carries no four eyes behind
      it. A proposal's does, through a check constraint on the proposal row; there is no proposal
      here, so this is the one confirmation in the product resting on the scope separation and
      the confirmer-is-not-the-suggester constraint alone. If an assurance review finds that too
      thin, the way back is to make curation a proposal like everything else, which costs a
      queue and nothing else.

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

## The documentation gate's list of error codes (2026-09-20, first OAS sweep)

- [x] **`api_docs_gate.py` refuses a code that routes really do raise.** Done: `raisable_codes()`
      now derives the list from source, every `code=` literal under `backend/apps/` and in
      `config/api.py`'s handlers, so a truthfully documented code passes (checked 2026-09-25,
      `r2-plan-docs`). What follows is the question as it was asked. The gate checks every
      backticked RFC 9457 code in an operation's description against `RAISABLE_CODES`, a
      hand-typed list built from `apps/shared/errors.py`'s `STATUS_BY_CODE` plus what
      `config/api.py` raises. But `config/api.py` passes a logic `ValidationError`'s own code
      straight through, so a 422 really answers `check_required`, `name_required`,
      `languages_required`, `invalid_slug` or `platform_account` from the tenants app alone, and
      `taxonomy/http.py` adds `in_use`, `system_row`, `request_pending` and
      `idempotency_conflict`. None of those are on the list, so documenting one truthfully fails
      the gate. The tenants and agents sweeps worked around it by naming only listed codes in
      backticks and describing the rest as "a 422 for a field the caller can fix, each carrying
      its own `code`" — honest, but it leaves the integrator without the value to branch on.
      Default if you say nothing: the next sweep keeps doing the same. The fix is one of two
      things and both are yours, because one of them touches a gate: derive `RAISABLE_CODES`
      from the source (every `code=` argument under `apps/`), or add the proven ones to the
      list by hand as each sweep meets them. Eight sweeps remain, and every one of them will
      hit this.

## The boot guard costs thirty interpreter starts, and a busy laptop trips it (2026-09-21)

- [ ] **`apps/shared/tests_production_guard.py` is the one test whose cost is process startup,
      and it is the suite's most load-sensitive.** It proves each rule of the production-safety
      block by booting Django in a subprocess with a particular environment — about thirty of
      them, three at a time, each with a 120-second timeout. One boot costs 1.7 s on an idle
      machine. On 2026-09-21, with roughly ten agents and a four-worker test run on the same
      laptop, the same single test took 70 s once and 252 s the next time, failing once on the
      120-second timeout and once on a transient `ImportError` inside a boot. Running it
      entirely alone reproduced both, so this is the machine and not the parallel runner, and
      the test's own comment already records a similar incident on 2026-09-19 at six concurrent
      boots. Default if you say nothing: it stays as it is and an occasional red run on a
      saturated laptop is reread rather than chased. The alternatives each cost something you
      should weigh: raise the per-boot timeout (a hang then takes longer to report), or prove
      the rules in-process by reloading settings instead of booting (cheaper and far faster,
      but it stops proving that a real process refuses to start, which is the whole point).

## Chunk 3's rest: defaults taken and two open questions (2026-09-22)

`docs/plans/briefs/CHUNK3_TASKS.md` names these defaults, each already stated in
its task's commit body, and two open questions from its own "Open questions"
section. Copied here as chunk3-rest-T20 requires.

**Open questions**

- [ ] **Urgency and the rule that a tone is never chosen by a person (NFR-S10).**
      INPUT_DELTAS §1 says urgency has a "fixed ordinal and tone", yet the chunk 2
      registry lists urgency with the kind "pill_tone", so a library editor who
      proposes a new urgency row picks its tone. CHUNK3_TASKS.md left this open on
      2026-09-19 and had T3 leave urgency unchanged, refusing only fields named
      `tone` or `colour`, until you decided. **This looks already answered:**
      `docs/DECISIONS.md` D-48, "answered OK by Alex 2026-09-19 (item 1)", takes
      Option A — the five levels are fixed rows with the tone each already has, a
      library editor changes only labels, usage note and SLA days, creating a
      level answers 422, and `GET /vocab` entries gain `fixedRows` so the screen
      hides Create and reorder. But `fixedRows` does not exist anywhere in
      `backend/apps/taxonomy/`, so D-48's answer was never built. This chunk did
      not touch `apps/taxonomy/registry.py` or the urgency vocabulary screen (out
      of chunk3-rest-T20's owned paths) and is reporting the gap rather than
      building around it: either T3's own work predates D-48 and needs a follow-up
      task to add `fixedRows` and the 422 refusal, or something about D-48's answer
      needs revisiting. Flagging rather than guessing which.
- [ ] **Problem area ("Where" in the report form).** `tenant-obligation.html` was
      designed with a Where select (legal text, translation, scope, duty, source or
      reference, something else), and `console-problem-reports.html` was designed
      to filter and pill by it. Nothing in the rules branches on it, and it is not
      in INPUT_DELTAS §1's kind list, so under "enums in code are for kinds only" it
      cannot be a code enum. Chunk3-rest built the designed body
      `{description, versionNumber?, language?}` with no area column and no Where
      select, on both obligations and instruments. If you want the field, it
      becomes a tier-2 library vocabulary (a registry entry plus seeded system
      rows) in a later task.

**Defaults taken** (each stated in its task's own commit body)

- [x] J-6: one sample advice-only obligation was added (`from_prototype: false`).
      No prototype obligation was rescoped, because none is advice-only.
- [x] The FFFS 2017:2 provision tree and FFFS 2026:11 are sample rows taken from
      the instrument card, marked `from_prototype: false`. Never presented as
      verbatim law.
- [x] Seeded records carry no verifier. The fixture's verifier is a tenant user,
      so `verified_by` stays null until someone re-verifies; the card shows
      "by <name>" only when it is set.
- [x] An instrument's verified date is derived from its obligations, or is the
      fixture anchor date when it has none.
- [x] A provision is shown on its instrument's card, under the instrument's own
      source link and verified date, and is reported through the instrument's
      "This looks wrong" (see also the open question on the Where field above).
- [x] `GET /problem-reports` (a list) moves to chunk 4; `GET /authorities` moves to
      chunk 5, with `console-sources.html`, which builds its add form. An
      instrument's authority is read embedded in `GET /instruments/{id}` until then.
- [x] Lineage and version lists are embedded in the detail reads (`GET
      /instruments/{id}`, `GET /instruments/{id}/provisions`); there is no `GET
      /instruments/{id}/relations` or `GET /provisions/{id}/versions`. The
      obligation detail cites provisions by reference and path, without their
      text; the card shows none.
- [x] `GET /instruments` filters by regime, `q` and `outsideFootprint` only, and
      takes no `asOf`. The Instruments tab lists every visible instrument with its
      in-force dates; "As of" applies to obligations only. `GET /obligations` has
      no tag filter. The unused designed filters are deferred.
- [x] The footprint scope rule sits in one place, `library/reading.py`: an
      instrument's scope is its regime, an obligation's scope is its own terms
      plus its instrument's regime. Neither inherits a jurisdiction term, because
      none is seeded.
- [x] The footprint preview counts obligations only (how many it hides and
      reveals), never their titles and never instruments — a footprint change
      never hides or reveals an instrument row by itself.
- [x] `?lang=` is accepted only on the diff reads (obligation and provision).
      Everything else follows `language_order`, and `translations[]` feeds the
      language chips.
- [x] Re-verification needs `proposals.review` plus a step-up — the stricter of
      the brief and the UI plan.
- [x] Re-pointing records when library lists are merged stays in chunk 4
      (`proposals/apply.py`). `relation_type`'s usage count also stays hardcoded 0
      (`registry.py`'s `_no_usage`) even though `instrument_relations` now uses it;
      wiring a real count is not INV-01 or INV-02 work.
- [x] INV-S9 stays skipped (R3, tenant-private records). FP-S4 stays fixme: its
      backend half is proven (`apps/taxonomy/tests_scenarios.py::test_fp_s4`), but
      its journey still waits on the feed, roadmap and briefing screens to exist
      alongside the inventory's own "Show outside our scope" switch.
- [x] No "Adopted" row on the instrument card, because no such data exists.

## A banking group with several regulated companies (2026-09-22)
- [ ] You want groups like SEB handled: several legal entities under one tenant, each
      narrowing the group's regulatory scope for itself rather than sharing one, and some
      members working across several entities while others stay scoped to one. D-69
      records the direction you chose. **It is design only — nothing is built**, and it
      reshapes `FootprintTerm` and the eleven call sites already shipped in R1 (FP-01 to
      FP-04), plus TEN-02's `LegalEntity`, which does not exist until chunk 8. Say when
      to schedule a proper planning pass for it (a brief, the way `AGENT_ACCESS.md` got
      one, before chunk 8 or as part of it) — it should not land as a slice on an
      unrelated push. That brief is `docs/plans/briefs/AGENT_ACCESS.md`, and its entry
      scope is one more reader of the footprint this reshapes (D-70).

## Landed from `origin/claude/r1-integration` (2026-09-23, lost-content)

Two designs lived on `origin/claude/r1-integration` and nowhere on main. Each landed
only on your own answer in chat to the session that merged it, never on an approval
relayed by an agent: (b) D-75 in `f753830`, and (a) agent access on your answer of
2026-09-23, "Land the design now as decided". Their decision rows took the numbers
`docs/DECISIONS.md` had reserved for them, matched by title and never by arithmetic.

- [x] **Keep the branch that holds them.** Both designs are on main now, so
      `origin/claude/r1-integration` no longer has to be kept for these two; whether it
      holds anything else worth keeping is yours to judge before it goes. Originally: the
      full designs were the commits `cee7cf2` and `b5b70c5`, and only that branch held
      both.

### (a) PRD 0.5: agent access, the agents a bank runs itself (commit `cee7cf2`, landed 2026-09-23)

A bank registers its own agents (a coding agent, a product agent, a procurement
agent, an internal assistant), narrows each to the departments and products it
serves, and gives it a service key or a personal access token. The agent only
reads, through MCP or the API; it reaches the bank's register only after two people
holding `security.manage` switched tenant reach on. Module ACC (ACC-01 to ACC-09 in
chunk 11, ACC-10 in chunk 13). It landed as the PRD 0.5 row and module, ADRs 0055 to
0057, the brief `docs/plans/briefs/AGENT_ACCESS.md`, and scenarios in the agents,
governance, identity, integrations, register and taxonomy specs. Nothing ACC is
built: those are specs, decisions and skipped test stubs.

Its decisions, by title, with the numbers they landed under (the branch numbered them
D-68 to D-73, and its PRD 0.5 row cited "D-63 to D-68"):

- "What a bank's own agent may read": D-76 (D-68 on the branch)
- "How a bank's own agent authenticates": D-77 (D-69 on the branch)
- "How an agent access entry is narrowed": D-70
- "What a bank's agent gets when it asks what applies": D-71
- "How a bank lets its own register leave its zone": D-72
- "When agent access is built": D-73

Its seven open questions, each answered by default by your answer of 2026-09-23. The
build takes the default named in each; nothing here blocks it, each is reversible, and
you can still overrule any one by saying so in chat.

- [ ] **Comments.** **Answered by default** (Alex, 2026-09-23: "Land the design now as
      decided"). Default: the structured notes on the entry are in (the applicability
      reason, the status note, "how we read this rule"), and COL-01 comment threads are
      out, so there is no `comments:read` scope. Your free text said the agent should
      reach "any comments they provided per entry", and your answer on what it reads
      chose register decisions alone. Say if it is the other way round. Reversing it
      adds a `comments:read` scope and a decision about mentions of people who never
      agreed to a machine reading them (D-76).
- [ ] **REG-04 in chunk 8.** **Answered by default** (Alex, 2026-09-23: "Land the design
      now as decided"). Default: chunk 8's order stands, so "How we read this rule"
      stays a cuttable Should below the descope line. It is the single field that turns
      a list of obligations into an answer a developer can build from, so moving it
      above the line is still recommended; D-26 made the order of a chunk's list the
      thing that protects work, so only you can reorder it (D-73).
- [ ] **`tokens.create` defaults.** **Answered by default** (Alex, 2026-09-23: "Land the
      design now as decided"). Default: Admin, Compliance officer and Owner hold it;
      Approver, Contributor, Reader and Auditor do not, and a bank may grant it to any
      role. An auditor running automated evidence pulls is a real case, so say if
      Auditor should have it by default (D-77).
- [ ] **Credential expiry.** **Answered by default** (Alex, 2026-09-23: "Land the design
      now as decided"). Default: 90 days for both a service key and a personal access
      token, settable per environment (`AGENT_ACCESS_KEY_MAX_DAYS`,
      `PERSONAL_TOKEN_MAX_DAYS`), and a credential cannot be issued without one. Say if
      a service key should be allowed to live longer (D-77).
- [ ] **A bank's own model endpoint.** **Answered by default** (Alex, 2026-09-23: "Land
      the design now as decided"). Default: a bank running its agent on a model endpoint
      outside the EU is the bank's decision, as pulling its own register into its own
      agent is, which is what makes it compatible with D-07. The assurance pack states
      it plainly, the tenant switch's approval and the access log are recorded, and we
      do not police the endpoint. The first procurement review will ask what we do about
      it (ADR 0057).
- [ ] **An auditor's agent.** **Answered by default** (Alex, 2026-09-23: "Land the
      design now as decided"). Default: the bank registers an external auditor's agent
      like any other entry, under the named engagement, and it ends when the engagement
      does: the bank revokes the entry, and its credentials expire in any case. It is a
      third party inside the bank's tenant, so if that is wrong, TEN-06's support access
      grants are the nearer pattern.
- [ ] **Where the tab lives.** **Answered by default** (Alex, 2026-09-23: "Land the
      design now as decided"). Default: agent access is built as the second tab of the
      Agents screen, per your answer. The two tabs must read as different things,
      because one kind of agent writes on our schedule and the other only reads on the
      bank's; each tab states in one line what it is, and the access tab says read-only.
      Confirm once you see the screen card.

The CLAUDE.md text that comes with it. No agent edits CLAUDE.md, so it did not land
with the design; add it yourself:

- [ ] Section 3, the R2 row's outcome ends: "tenant-controlled agents, agent access for
      the agents a bank runs itself".
- [ ] Section 5, the bullet that starts "Tenant content never reaches logs" becomes:
      "Tenant content never reaches logs, Sentry, analytics or an unapproved model
      endpoint. A bank's own agents read through agent access: their scope is the
      bank's footprint narrowed by the departments and products they serve, never
      widened; a record outside it answers 404; they write nothing in R2; and they
      never narrow silently, so every answer states the scope it was answered in and
      names what it could not see. The bank's register leaves the zone only after two
      people holding `security.manage` switched tenant reach on, and a personal access
      token acts as its person, can never step up and dies with them. PostgreSQL with
      pgvector everywhere; there is no SQLite."

### (b) D-75: who decides whether an obligation applies (commit `b5b70c5`)

Your words of 2026-09-22, as that commit quotes them: "does not need a second
sign-off with passkey. That is overkill for 'what applies'. It is enough that one
compliance person sets it, with a confirmation dialog before it's stored, and that
an audit event was recorded".

The rule it would replace is PRD REG-01 as it stands: applicability "changes only
through a request that a second person approves. Many pending requests can be
decided in one call, with four eyes on every row", which CLAUDE.md section 5's
"Four eyes, enforced by a check constraint, with a passkey step-up on approvals"
covers. D-75 instead lets one holder of `applicability.approve` set it directly
after a confirmation dialog, with one audit event naming the person, the value
before and after and the reason: no request, no second approver, no step-up, and a
pasted batch is one confirmed call with an audit event per row. Risk acceptance
keeps its four eyes, and "applies" and "we comply" stay separate facts. Nothing in
REG is built (chunk 8, R2), so it changes what gets built, not what exists.

Everything it changes, all in the documents:

- PRD: REG-01, J-10 and AC-REG1 (today "an approver with a fresh step-up decides 93
  pending unit requests" and a request the caller filed answers 409
  `four_eyes_violation`), plus a version row. That row is 0.6, because 0.5 was kept
  for (a).
- The register spec (`backend/apps/register/app.md`): its context, the REG-01 row,
  AC-REG1 and the acceptance bullet on requests, and REG-S1, REG-S2, REG-S4 and
  REG-S12 to REG-S16 (J-10's journey), with their test stubs and journey titles.
- Decisions: D-44 and its ADR 0038 ("many pending applicability requests are decided
  in one call, with four eyes on every row") are superseded. D-41 and D-42 and their
  ADRs 0035 and 0036 lose the applicability request table they extend, and D-42's
  "an approved 'applies'" becomes a confirmed one.
- The four-eyes guard (`backend/apps/shared/tests_four_eyes.py`) no longer lists
  applicability among the tables it must grow to cover. The chunk 8 rows of
  `docs/plans/UI_Implementation_Plan.md` lose their request, approve and decide
  routes. The chunk 8 task briefs (`CHUNK8_TASKS.md` and `FEATURES_0_3_TASKS.md`)
  have tasks that file, approve and decide requests. Those tasks are marked to be
  planned again before chunk 8 starts.
- `applicability.request` retires when chunk 8 builds REG-01.

The commit that carries this text makes all of these changes, on the local branch
`wt/r1w1-lost-content-d75`. `b5b70c5` is the pushed original, and it covers only
REG-01, J-10 and the four register scenarios. The commit merges only after you give
your own answer in chat to the session that merges it.

- [x] **Confirmed 2026-09-23 by the merging session.** Alex gave D-75 in chat on 2026-09-22, in the words quoted above, directly to the session that merged it; the merge commit records them. Originally: Confirm or decline D-75 in chat to the session that merges the build. That
      session merges this change only on your own answer. In its merge commit it ticks
      this item with the date and your words, and brings this section up to date.

## The calendar feed carries every roadmap date, whatever the date's precision (2026-09-21, HOM-04)

- [ ] **ADR 0045 says the feed carries dates "with a day-precision key date today or later";
      the built feed carries every date the roadmap carries.** The two are the same date for
      almost every reform, because a change is registered with day precision unless somebody
      records otherwise. They part when a reform is dated only to a month, a quarter or a
      year: the roadmap shows it with its precision beside it, and a calendar client would
      draw the same date as one all-day event and put a reminder on a day nobody published.
      Filtering it out was built and then taken out again, for a reason worth your ruling: the
      precision lives on `regulatory_change`, a library record, and reading it inside the
      module that writes a bank's `calendar_feed` rows is the exact shape
      `apps/shared/tests_library_fence.py` refuses (a module that names a library model and
      calls a write). The alternatives are each somebody's decision: carry the precision on
      `RoadmapItem` so the feed can read it from the roadmap it already asks (a contract
      change in `c6-home-api-contract`'s shape), have the feed emit a vague date as an event
      spanning the month or quarter (a calendar can say that, and it is arguably the truer
      entry), or leave it as built and let a vague date show as one day, which is what the
      roadmap page already shows. Default if you say nothing: it stays as built, and a feed
      never disagrees with the roadmap page beside it, which is the rule chunk 6 ruling 5 set
      for these two reads.

## lib-instrument-card-fixes: the instrument card's lineage headings and empty text (2026-09-23, INV-01, INV-02)

- [ ] **The lineage headings read "Implements" going out and "Amends this instrument" coming
      in, where the design card says "Amended by" and "Elaborated by".** Relation types
      (`implements`, `elaborates`, `amends`) are vocabulary rows a platform admin can add to
      or relabel, and each has one label. The card now groups the lineage by relation and
      direction with no pair hard-coded, so a new relation type shows up without a deploy:
      an outgoing group is headed by the label itself, and an incoming one by the label
      followed by "this instrument" (in Swedish "den här rättsakten"). "Amended by" needs a
      second label per relation type, said from the other side. Default if you say nothing:
      it stays as built. If you want the design's wording, relation types gain an inverse
      label (a vocabulary change, one more label per row, in every content language) and
      the card uses it for the incoming groups.
- [x] **The empty provision tree says "The provision tree appears here once the library holds
      it."**, where `design/screens/tenant-instrument.html` still says "as the library editor
      approves it". bleqq staffs no library editor (D-62), so the screen names no approver.
      The design card's lineage headings and this sentence are still the old wording; whoever
      next edits `design/` should bring the card in line, or tell us to follow the card.
      Done (lib-standard-presentation): D-62 settled it, so the card's empty line now reads
      as the screen does, and the card draws a standard's licensed-text state too.

## proposals-decide-hardening (2026-09-23): an agent confirms obligation versions only (D-79)

- [x] **An agent may no longer approve a vocabulary or term proposal; it waits for a person.**
      **Answered 2026-09-23, and lifted by `vocab-agent-confirm`:** see the next section.
      Only an obligation version can record that an agent confirmed it (`verified_origin`,
      `verified_by_agent`); a vocabulary row, its labels and a taxonomy term have no such
      columns, so an agent's approval of one would have read as a person's check (INV-05).
      The approve route now answers 409 `person_review_required` to a reviewing key on any
      kind but `new_obligation_version`, and an agent may still reject one. With
      `library_editor` unstaffed, that means every proposed flag, list value or term waits in
      the console queue for you or someone you name. Default if you say nothing: it stays
      this way. The alternative is machine-confirmed provenance columns on every library
      list and on terms, so an agent can confirm those too: say if you want that planned.

## vocab-term-provenance (2026-09-23): the columns for D-79's alternative are built; the 409 waits for your yes

- [x] **Say, in your own words, whether an agent may now approve vocabulary and term
      proposals.** **Answered 2026-09-23, in chat to the session orchestrating the R1
      build, which put it into the repository as the `vocab-agent-confirm` brief
      (`docs/plans/r1-waves/wave4.json` on `claude/r1-plan`).** Asked "An agent can now
      approve proposals (D-62), but vocabulary lists and taxonomy terms have no column to
      record machine-confirmed provenance. How should agent approval of those proposal
      kinds work?", you chose "Add provenance columns now": "Every library list row and taxonomy term gains the machine-confirmed provenance an obligation version has, so agents can confirm them too. More migrations and screens in wave 2, but no human bottleneck on vocabulary." You declined "Refuse until provenance
      exists". Done in `vocab-agent-confirm`: the 409 is lifted for every
      `vocabulary_*` and `term_*` kind (the rule stays keyed on the kinds whose record can
      name its confirming agent, so a kind added without that still waits for a person),
      `library-confirmer` v2 decides the list and term kinds, D-79 records the lift, and PRO-S13 and
      ID-S31 prove it with a vocabulary kind. What follows is the original question. The build plan records your 2026-09-23 answer to the box above as the
      alternative (provenance columns), but it reached this work relayed through the plan,
      not in your words, and the box above is still open. So only the half that changes
      nothing about who may approve was built: every library list and every taxonomy term
      now records who confirmed the approval that wrote its wording (`user` or `agent`), the
      confirming agent, and the proposal, through which the proposing agent is named. Under
      an agent's approval every label it writes, the original included, is stored
      machine-made, and an agent never clears that mark. A person's approval confirms the
      labels it writes, and a row the agents worded keeps naming them until a person has
      approved all of their wording, so a person fixing one Swedish label never makes the
      agents' English read as checked by a person. The list and
      term reads (`GET /vocab/{list}`, `GET /vocab/{list}/{key}`, `GET /taxonomy/terms`)
      return it. The 409 `person_review_required` stays, and the confirming agent's
      definition (`library-confirmer` v1) still leaves list and term proposals to a person.
      Default if you say nothing: it stays so. If you say yes, one follow-up removes the 409
      and its code, amends D-79, lets `library-confirmer` decide every kind, names the run on
      the audit row of an agent's retire, restore or merge, and extends PRO-S13 and ID-S31
      with a vocabulary kind.
- [ ] **A risk to weigh with that yes.** After the lift, a list label an agent confirmed is
      stored machine-made, but no bank-facing screen marks a machine-made list label on a
      pill today, and the console's vocabulary screen shows a row's confirmation only from
      the next wave. Until those screens show it, a bank reads an agent's Swedish label for a
      flag exactly as it reads a person's.

## proposals-reads-agent-visible: which version a reviewer decides a proposal against (2026-09-23, PRO-02)

- [ ] **An open proposal is compared with the version in force today; once approved, it is
      compared with the version just before the one it wrote.** The two differ when an
      approved version is still waiting for its date. Example: version 1 is in force, version
      2 is approved to take effect next month, and a new proposal is opened. The reviewer
      sees version 1 against the new text, so the diff also shows version 2's changes as if
      the new proposal made them. Once approved, the new proposal becomes version 3 and reads
      against version 2. A rejected proposal also stays compared with today's version and
      moves with the calendar. The API descriptions now say exactly this (`ProposalDetail`,
      `currentSummary`, `scopeBefore`). The alternative: compare an open proposal with the
      latest version, the one its approval will follow, so the open and approved views match,
      and pin a rejected one to the version in force on the day it was rejected. Default if
      you say nothing: it stays as built, which is what the brief asked for ("open proposals
      keep today's in-force version").

## agent-flow-run-guards: what an agent files names its run (2026-09-23)
- [ ] **Default taken: an agent's key must name an open run of its own on
      `POST /changes` and `POST /proposals`** (AGT-01, PRO-01): every key that registers a
      change, and every key bound to an agent that files a proposal. Naming none, or a closed
      one, answers 422 `run_not_open`; another key's run answers 404, as does any run a
      person names. A bank's own key, which is bound to no agent, still files a proposal
      without a run in R1, as a bank's person does, and every watch write (a run, a source
      check, a change and anything on one) refuses it with 403 `tenant_agents_not_available`
      whatever scopes it holds. Say so if a bank key's proposal should need a run too: a
      bank's key cannot open one in R1, so that would stop bank keys proposing until
      chunk 11 brings a bank's own agents.
- [ ] **Default taken: finding similar records names no run** (AGT-01, AGT-S1).
      `POST /search/similar` is a read, so it takes no `agentRunId` and leaves nothing
      behind to trace; AGT-S1 therefore says "each write references the run" rather than
      "each step". Every write of the flow (opening and closing the run, a source check, a
      change, a proposal) names it. Say so if you want the lookups an agent makes traced to
      its run as well: that is an optional, checked `agentRunId` on the similar-records call.

## agents-confirmer-definition: the confirming agent ships as a draft (2026-09-23, D-80)

Nothing waits for these; each has the default the build took.

- [ ] **The confirming agent's decisions are logged with metadata it reports itself.** A
      confirming agent's approval, correction or rejection now has an AI-log purpose of its
      own, `agent_review`, and the model and model version on that row are the agent's own
      account, exactly as D-66 has it for the "So what?" (D-80). Default: accepted in R1 as
      a reporting boundary, because every agent is bleqq's own; it becomes a trust boundary
      the day a bank runs its own reviewing agent, which is R2's agent-access work.
- [ ] **`library-confirmer` v1 ships with no labelled evaluation case.** Its definition,
      prompt and key are its own and it may share the sweeper's model (your default of
      2026-09-20). Its `evals/README.md` names the four kinds of case it will be scored on
      (approve, correct, reject, leave open), but none is written yet, so the definition
      stays `draft` and no run of it is meant to decide anything. Default: it stays a
      draft until the rows, a scoring track and a first baseline exist; publishing it is a
      platform admin's act (AGT-03, R2). Say if you want the rows authored before then.
- [ ] **A proposal the confirming agent leaves open has no reason kept anywhere.** It
      leaves a proposal open when the proposal is outside the sector scope or its sources
      contradict each other. A run's stats count only model calls and fetches, and no
      proposal field holds an agent's "not mine to settle", so the next run reads the same
      proposal again, and oldest-first order puts it at the front each time. Default: it
      stays so in R1. The run lists `new_obligation_version` proposals only, so vocabulary
      and term proposals, which are a person's, never cost it a model call. Its decision
      and model-call budgets cap what a stuck proposal can cost, and the console queue
      shows a person what is waiting. Say if you want a leave-open outcome with a reason
      of its own: a proposal note or a counter on the run, and a way for the queue to skip
      what an agent already left open.
- [ ] **Hand-off: the approve and reject bodies must carry `AgentDecision` before any run
      of the confirming agent decides anything.** The definition names the object on both
      tools. Today `ProposalApproveBody` is a `WriteBody` and refuses the field with a 422,
      and `ProposalRejectBody` is a plain `CamelSchema` that drops it without a word, which
      would leave a model call unlogged (AUD-02). The package that wires D-80
      (proposals-agent-decision-log) makes the reject body a `WriteBody` and requires
      `decision` from a key caller on both routes. Default: the definition stays `draft`
      until then, and its tool descriptions say "once the route accepts it". This is a
      note to the next package, not a question.
- [ ] **Should a bank read the confirming agent's reasoning?** Each decision the confirming
      agent makes is logged under `agent_review` in the platform's zone, because its run
      is the platform's. Every row in that zone was readable by every bank's
      `ai_log.read` holders. A decision is about a proposal, and another bank may have
      filed it, while a bank today sees only the proposals it filed itself. Default: the
      library read policy on `ai_generation` leaves `agent_review` out, the platform
      alone reads those rows, and a bank still sees on the record itself which agents
      proposed and confirmed it (D-62). A watch item's curation confirmation (D-74)
      follows the same rule, although the item is one every bank reads. Say if a bank should read the reasoning behind a
      record it relies on. That would take a narrower read, for example the decisions on
      applied proposals only, and never the rejections of other banks' filings.

## agents-sector-scope-eval: the two AGT-08 tolerances are defaults (2026-09-23, AC-AGT1)

- [ ] **In-scope accuracy and standard-term accuracy may not fall at all under their
      recorded baseline.** Both tolerances in `backend/eval/tolerance.json` are 0, with
      their reasons in its `_rationale`. Each metric is the mean over all 60 classification
      texts, where one text is 0.017, so any tolerance of 0.017 or more lets one of the four
      off-sector texts be registered, or the law that cites a standard be tagged, without a
      red build. That is the failure AGT-08 exists to prevent, and the screen's tolerance is
      0 for the same reason. Two things 0 does not settle, for your ruling: a real,
      non-deterministic classifier that flips one text between runs turns the build red
      until the baseline is re-recorded; and a change that puts one text right and another
      wrong keeps the mean and passes. Gating the off-sector and cites-a-standard texts on
      their own would close the second, but needs the baseline to record a value per kind
      of text, which it does not today. Default if you say nothing: 0 for both, and the
      report's lines per kind of text are read by the person recording the baseline.

## search-eval-gate: the release gate does not check search quality yet (2026-09-23, SRC-05)

- [ ] **The retrieval track of the release gate is unrecorded until D-09's key arrives, so a
      retrieval regression would not fail CI until then.** The real retriever is wired
      (`apps.search.eval:Retriever`, hybrid search over the sample library) and SRC-S8 proves
      the gate fails when a recorded score drops, but with only the mock embedder there is
      nothing honest to record: a mock can never set the bar. Nothing to do beyond the D-09
      key already listed under "Before the first test deploy"; the run that chooses the
      model records the baseline and removes this line (`backend/eval/README.md`). The ties
      are fixed (tax-jurisdiction-derivation, 2026-09-23): hybrid search now breaks them on
      the record's stable key, the kind, the language and the start date, never on an id,
      so every question comes back in the same order from one fresh database to the next.
      Only D-09's key remains, plus one thing that run needs that is not yours: a settings
      route with a real embedder and a throwaway database (today's test settings fix the
      embedder to the mock).

## tax-jurisdiction-derivation: where a record's derived jurisdictions show (2026-09-23, FP-04, D-28, D-29)

- [ ] **A record's scope block and its "outside our scope" reason now list the
      jurisdictions its instrument's rules reach.** They are derived at match time and never
      stored, as D-28 and D-29 say, and the card shows the scope the rule matched on: a
      Swedish obligation shows one pill, Sweden, and a Union one five pills, European
      Union, Sweden, Denmark, Norway and Finland. The API marks that Union group as all
      selected, but the card folds a group into one "all" pill only for services, so it
      lists the five. An obligation hidden by a Denmark-only scope says it is outside by
      its jurisdiction, Sweden. A standard's obligation lists none (International is
      mirrored by no term, D-38). Two other readings: the card folds a fully selected
      jurisdiction group into one "All jurisdictions" pill, as it does for services; or it
      shows only the instrument's own jurisdiction, or none, while still matching on all
      of them. Default if you say nothing: the card lists every derived term as its own
      pill, because the card and the rule then cannot disagree.

## Ask sends a reader's question to the model (search-ask-backend, 2026-09-23)

- [ ] Ask's backend now works: `POST /ask` sends the question a reader types, and the
      library passages it rests on, to whatever `LLM_PROVIDER` names. Everywhere it runs
      today that is `mock`, which answers from the passages and sends nothing anywhere.
      `docs/runbooks/RAILWAY_VARIABLES.md` still lists `anthropic` for the Railway test
      deploy (D-07), and an Anthropic key for it is on your list above. The moment both
      are set, a tester's typed question goes to Anthropic's own endpoint, which offers US
      or global inference and not the EU pin D-07 waits on. Say which it is: keep
      `LLM_PROVIDER=mock` on the test deploy until the EU path is contracted, or approve
      Anthropic's endpoint for the test deploy's made-up banks, knowing a question is
      whatever the tester types. Default if you say nothing: nothing changes in code, and
      the deploy follows whatever you set.

## i18n-en-sv-switch: the interface language picker has no design card (2026-09-23, I18N-02)

- [ ] **Confirm how a person picks their interface language, or draw it.** The shell card
      (`design/screens/tenant-shell.html`) shows the account menu and the More sheet without
      a language choice, and the prototype has none either (its English/Svenska chips switch
      the content language of an obligation, not the interface). Default taken without
      waiting: a "Language" group in the rail's account menu, between My sessions and Sign
      out, holding one radio per interface language, each named in its own words ("English",
      "Svenska"), the language in use marked, the menu staying open so the switch is seen to
      land, and a short error line under the group if the save fails. The More sheet below
      1024 px lays the same group out flat as touch rows. Say so if you want it elsewhere, for
      example as a setting on a profile page, and the design card follows.

## api-docs-identity-auth: a passkey prompt gives up after two minutes, and re-enrolment stops at one bank (2026-09-23, ID-02, ID-04, ID-06)

- [ ] **Web Authentication Level 3 (W3C Recommendation, 25 August 2026, §15.1) recommends a
      ceremony timeout of 5 to 10 minutes, default 5, and challenges that stay valid about
      that long (§13.4.3); `CHALLENGE_TTL_SECONDS` defaults to 120.** So a person who takes
      longer than two minutes over a passkey prompt (finding the security key, a phone that
      has to wake for a hybrid sign-in, a screen reader user) gets `challenge_expired` and
      starts again. The spec's range comes from WCAG's "Enough time". Raising the default to
      300 is one setting and changes no invariant: challenges stay single use, and the
      registration and step-up ones stay bound to the person and session. It was left alone
      because the package that found it was documentation only. Every lifetime the published
      descriptions and examples quote is read from its setting when the API loads, so they
      follow the setting either way. Default if you say nothing: it stays at 120.
- [ ] **Re-enrolment signs a person out only in the bank that re-issued it.** Re-issuing
      someone's enrolment (a bank admin, or the console acting for a bank) retires every one
      of their passkeys everywhere, because passkeys belong to the account, and then revokes
      "every" session. But it runs with that one bank activated, and row-level security hides
      the person's sessions in any other bank they belong to. Those sessions keep refreshing
      until their absolute limit (`SESSION_ABSOLUTE_HOURS_DEFAULT`, 12 hours), although the
      person is back to awaiting enrolment. Reaching past one bank's rows from inside a bank
      is a zone decision, so it is yours. Either the product says re-enrolment ends
      sessions in the acting bank only, or re-enrolment revokes the other banks' sessions
      through one narrowly scoped function the schema owner holds, like the retention purge.
      It predates this package and was found while checking that `GET /me/sessions` lists
      only this bank's sessions. Default if you say nothing: it stays as built, and the
      published description of `GET /me/sessions` says a person sees only this bank's
      sessions there.

## watch-curation-confirm-backend: a watch fact's confirmation, and who may give it (2026-09-23, D-74, WAT-03, WAT-04)

The backend half of D-74 has landed: `POST /changes/{changeId}/confirmation`, the person,
agent and key columns on a change's type, flags, scope terms and obligation links (watch
0002), and the machine-confirmed provenance on the change, feed, console and roadmap reads.
The bank's change page and feed already say "Machine-confirmed" for an agent's confirmation
and keep "Confirmed by a library editor" for a person's; the console's Confirm control, its
seed and the WAT-S4 journey are still to come (`watch-curation-confirm-frontend`). Nothing
blocks. Four defaults were taken; say if any is wrong.

- [ ] **A person's confirmation needs a fresh passkey.** An agent of another definition is the
      routine confirmer and never steps up (a key cannot). A person holding
      `proposals.review` may confirm instead, and may overturn a fact somebody confirmed
      through `PATCH /changes/{changeId}` or `PUT /changes/{changeId}/obligations`, but only
      with a fresh passkey assertion, recorded on the audit row, because either is a person
      intervening in the agents' curation, which is how approvals are treated. The console
      design card (`design/screens/console-change-facts.html`) still says "No passkey:
      confirming a fact is not an approval"; it predates D-74 and the frontend package will
      follow the rule. Default if you say nothing: the passkey stays.
- [ ] **A bank sees both agent names on a machine-confirmed watch fact.** Each fact names the
      agent that suggested it and the agent that confirmed it, as a library version does under
      D-62's default. The agent's reasoning (the `agent_review` row) stays the platform's,
      as the D-80 entry above says. Default if you say nothing: both names stay visible.
- [ ] **A library editor's own filing is a suggestion too.** A change a person registers by
      hand now carries its type as a suggestion, like its flags and links always were, where
      the reads used to show the type of such a change as settled. It matches what the route
      already promised ("stored as a suggestion, whoever sent it") and keeps "confirmed" to
      mean the confirm route was used. Default if you say nothing: it stays a suggestion.
- [ ] **Nobody confirms a watch fact they filed themselves, a person included.** D-74 says the
      confirming agent is never the suggesting one. The same rule now holds for people: a
      library editor who files or corrects a type, a flag, a term or a link is named as its
      suggester, and the confirm route answers 409 `own_suggestion` if that same person then
      tries to confirm it; another person, or an agent of another definition, may. A check
      constraint holds it in the database as it does for agents. Without it, one editor could
      file a fact and settle it for every bank alone, which nothing on the fact would show.
      Default if you say nothing: one person cannot file and confirm alone.

Built beyond the brief, for the reviewer: the confirming agent names the **type it checked**
by its key (`changeType: "adopted"`), so a type corrected while the agent was reading is
refused rather than confirmed unread; and each of the three curation writes locks the
change's row before it reads what is confirmed, so a confirmation cannot land between a
call's check and its write (proven with two real sessions). The suggesting **key** is stored
beside the suggesting agent (`suggested_by_api_key`), so the confirm route can say which
refusal it is:
409 `own_suggestion` when the very key that filed a fact tries to confirm it, 409
`same_agent` when another key of the same agent does. The check constraints refuse both on
their own. A key bound to no agent names no suggester, and cannot confirm anything. Two notes
for later packages, not questions: `backend/agents/library-confirmer/v1/definition.yaml`
does not yet list the confirm route as a tool (its package owns that file this wave), and
`backend/apps/watch/app.md`'s context still says every classification waits for "a person"
to confirm it, which `r1-close-and-readiness` rewords when it sets WAT-03 and WAT-04 to built.

## tax-nordic-seed: Kapitalmarkedsloven has no issuer in the sample library (2026-09-23, FP-04)

- [ ] **Folketinget as an authority.** The Danish sample act (`dk-lov-2017-650`, Lov om
      kapitalmarkeder) is filed without an issuing authority. Retsinformation.dk states that
      Folketinget passed it ("Folketinget har vedtaget ..."), but Folketinget's own site,
      ft.dk, answered this build's fetches with a challenge page, so its address could not be
      verified, and the rule is to invent nothing. The Norwegian act names Stortinget, whose
      site answered. Default if you say nothing: the Danish act stays without an issuer until
      someone files Folketinget (key `folketinget`, `https://www.ft.dk/`) after checking the
      address, and then sets it on the instrument through a proposal.

## lib-standard-e2e-seed: the first standard exists for tests and E2E only (2026-09-23, INV-08, FP-01)

- [ ] Default taken until you answer "Legal, before any standard is seeded" above:
      ISO/IEC 27001:2022 and its one conformance duty live in
      `backend/apps/library/fixtures/e2e_standard.json`, which only `seed_e2e`
      loads. `prototype_data.json`, which `seed_demo` loads, holds no standard,
      and `check_prototype_data.py` refuses one there. The edition is titled by
      its reference alone, never its official title, and the duty's wording is
      ours. When you answer yes, moving the rows into the prototype fixture is
      the whole change.
- [ ] The instrument's national-adoptions note names no adoption reference: the
      Nordic adoptions (SS-EN, DS/EN, NS-EN, SFS-EN) were never verified, so the
      note says only that each national body adopts the edition under its own
      reference. A person verifies them before the note names any.
## ai-log-read: a shared "So what?" reads each bank's own review state (2026-09-23, AUD-02)

- [ ] **A library "So what?" in the AI log shows the reading bank's own review, not one
      shared state.** The row is one per change and every bank reads it; no bank may move it
      (chunk 5 ruling I), and D-62 leaves the library to agents, so nobody would ever move it
      and the log would show "draft" forever beside a bank's confirmed case. The default
      taken: `GET /ai-generations` computes the row's `status`, `reviewedBy` and `reviewedAt`
      for the reading bank from its own case (`confirmed` as drafted, `edited` when the bank
      rewrote it, `draft` otherwise), and nothing shared is written. AUD-S4 in
      `governance/app.md` is reworded to match. Default if you say nothing: it stays this way.

## proposals-kind-instrument-obligation: new instruments and obligations through the queue (2026-09-23, PRO-01, INV-01, INV-03)

- [ ] **Default taken: no citation table.** A new instrument or obligation keeps its sources
      field by field on the proposal (`field_sources`, https links only) and its own source on
      the record (`source_url`, from the proposal's `sourceUrl`). A record's citations read
      from the approving proposal until a citation table is planned. Say so if the re-check
      needs a table of its own in R1.
- [ ] **Default taken: approving a new record does not stamp "last verified".** Approval
      stamps who confirmed it (`verified_origin`, and the confirming agent when an agent did),
      as a new version already does, and leaves `last_verified_at` and `verified_by` to the
      re-verification, which is the one act that says someone checked the source on a date.
      A new record therefore reads as never re-verified until the first monthly check.
- [ ] **Default taken: `update_obligation` and `retire_record` are not built.** No R1
      scenario needs them; a changed duty arrives as `new_obligation_version`.
- [ ] **Default taken: an agent's approval of a new instrument or obligation still waits for
      a person (D-79).** The records carry machine-confirmed provenance already; the
      refusal is lifted with the vocabulary and term provenance package, as planned.
- [ ] **Default taken: a new instrument in the bank's library updates is never cut to the
      footprint.** A new obligation is cut like a new version; an instrument is not a duty,
      so it reaches every bank, as a change to a shared list does.
## watch-regime-required: a run's classification is logged with metadata it reports itself (2026-09-23, D-66, AUD-02, D-39)

Nothing waits for these; each has the default the build took.

- [ ] **A run's classification of a new change is now AI output on the record.** When a key
      registers a new change, its type, flags, scope terms and urgency are written as one
      `scope_suggestion` row in the AI output log under the run that filed it, marked
      `model_metadata_reported_by_agent` exactly as D-66 has it for the "So what?" (AUD-S4's
      producer). bleqq made no model call, so the model and version are the run's own
      account: the ones in the filing's `soWhat` when it carries one, else the model and
      pipeline version the run was opened with, because `createChange` itself has no model
      version field. Default: accepted in R1 as a reporting boundary, as D-66 and D-80. A
      library editor's registration is a person's classification and logs no row, and a
      second sighting logs none because it stores no scope. Say if you want a dedicated
      model version on `createChange` instead of the run's pipeline version.
- [ ] **Every change must name a regime (D-39), and a merge is exempt.** `createChange` for a
      new change and an `updateChange` that replaces `termIds` answer 422 `regime_required`
      with the regime keys. A second sighting of a known `stableKey` adds pages and
      milestones and never touches the stored terms, so it is not held to the rule. The six
      E2E-seeded changes that carried no regime now carry one each, chosen inside the
      footprint of the bank whose case they belong to, so no cached scope verdict moved; the
      one visible difference is that tenant B's feed now shows the AI-mapping change as
      outside its scope, since tenant B does not follow the AI and ICT regime.
## ask-screen: what a reader is told when the model cut an answer off (2026-09-23, SRC-03, AUD-02, D-82)

- [ ] **An Ask answer the model stopped at its length limit (`ASK_MAX_TOKENS`, 1024 tokens)
      now says so on screen.** D-82 left open what the stream tells that reader. The default
      taken: the closing `answer` event carries `stopReason`, the provider's own word exactly
      as the AI log row stores it (`end_turn`, or `max_tokens` when it was cut off; empty when
      no model was asked), and the Ask screen shows "This answer was cut short at its length
      limit. Ask a narrower question for the rest." under an answer that ended at
      `max_tokens`. Every statement sent is still cited either way. Say if you would rather
      the stream stayed silent (only the AI log records it), or the limit were raised
      instead. Default if you say nothing: it stays as built.

## std-journeys: a standard shows only to banks that follow it (2026-09-23, FP-01, FP-02, INV-08, AC-FP3)

- [ ] Default taken (D-85 in `docs/DECISIONS.md`): `seed_e2e` switches the
      ISO/IEC 27001 term on so FP-S16 can follow it through the regulatory scope request;
      the reference seed still files it off, so nothing deployed changes. Say if a journey
      should instead wait until you answer "Legal, before any standard is seeded" above.
- [x] The regulatory scope page's opt-in group with "None followed" (listed among the design
      cards still to be drawn above) is drawn: `design/screens/admin-footprint.html`, state 20.
      New string `footprint.noneFollowed`: "None followed." / "Ingen följs.".


## lib-standard-e2e-seed: the first standard exists for tests and E2E only (2026-09-23, INV-08, FP-01)

- [ ] Default taken until you answer "Legal, before any standard is seeded" above:
      ISO/IEC 27001:2022 and its one conformance duty live in
      `backend/apps/library/fixtures/e2e_standard.json`, which only `seed_e2e`
      loads. `prototype_data.json`, which `seed_demo` loads, holds no standard,
      and `check_prototype_data.py` refuses one there. The edition is titled by
      its reference alone, never its official title, and the duty's wording is
      ours. When you answer yes, moving the rows into the prototype fixture is
      the whole change.
- [ ] The instrument's national-adoptions note names no adoption reference: the
      Nordic adoptions (SS-EN, DS/EN, NS-EN, SFS-EN) were never verified, so the
      note says only that each national body adopts the edition under its own
      reference. A person verifies them before the note names any.

## watch-standards: a standard's term needs a standards body, and publishers are not read (2026-09-23, WAT-07, D-45)

Nothing waits for these; each has the default the build took.

- [ ] **Which publishers no run reads.** `STANDARDS_PUBLISHER_HOSTS` defaults to every
      standards publisher whose terms were read on 2026-09-19 (iso.org, iec.ch, sis.se,
      ds.dk, standard.no, sfs.fi, pcisecuritystandards.org; not iaf.nu, which publishes no
      standard's text). A source registered on one of them, or of the `standards_body`
      kind, gets its automated checks switched off, and a run's check of it answers 422
      `source_inactive`. Default: out of the box bleqq reads no publisher. When a lawyer
      clears a publisher, take its host off the list in that environment.
- [ ] **ISO/IEC 27001 is now seeded active on a new database only.** The watch door refuses
      a standard's term on a change whose authority is not a standards body
      (`standard_term_only_on_standards`), which was the reason the term was held. The
      seed creates terms and never updates them, so a database seeded before this keeps
      the term inactive until a vocabulary change switches it on. Default: left to you, since
      switching it on in a deployed library is a library decision. The regulatory scope
      page's "None followed" wording lands with std-journeys in the same wave.
- [ ] **`licensed_text` has nothing to refuse.** No page bleqq stores keeps a snapshot, so
      a body that sends one is refused by the schema (`validation_error`) like any field it
      does not name. WAT-S11's step now says that. Say if you want a dedicated code.

## ask-standard-no-answer: Ask answers nothing about a standard (2026-09-23, D-81, SRC-S12)

- [ ] **Ask now answers "no answer" to any question whose only support is a standard's
      conformance duty** (D-81): the library holds no clause text, so a model given the duty
      could only answer about a control from memory. Search still finds the duty. Nothing to
      do unless you want Ask to answer questions about conformance itself one day. Worth
      knowing: the evaluation row that gates this (`r-en-17`) asks about an invented
      standard, and the sample library holds no standard until `f03-T35` adds the first one,
      so until then the row scores right against any retriever and proves the harness path,
      not the filter; `test_src_s12` proves the filter over an invented standard of its own.
      Default if you say nothing: stays as built.

## r1-int-w23: the wave 2 and 3 integration (2026-09-23, D-84 to D-87, H16, FP-04, AGT-01)

Forty-five cloud branches are merged on `claude/r1-int-w23`. Nothing blocks; one default
was taken, and three statuses moved because the merged code earns them.

- [ ] **The evaluation set has a library door of its own (D-87).** The H16 census counts
      every shared row of a library-zone app, and `eval_question` and `eval_run` (search
      0002) are in the search app. They are platform rows no proposal carries, so the two
      remedies the census names did not fit: a `LibraryModel` would put a console write
      behind a proposal, and the seed door would let a console write open every inventory
      table. Search 0003 gives them the trigger with a door named `eval`, opened only by
      `create_question()` and `record_run()`. Default if you say nothing: the door stays.
      The alternative is moving the two tables out of the search app.
- [ ] **A merge approval opens the watch door for the watch rows it moves (D-87).**
      `watch/write.py`'s `repoint()` now names the watch door to the database inside the
      proposal door, as `index_write()` does for a rebuild. Default: it stays.
- FP-04 and AGT-01 read `built`: every FP-04 scenario (FP-S8 to FP-S15) and every AGT-01
  scenario (AGT-S1, AGT-S2, AGT-S10, AGT-S15) is un-skipped and green over the merged
  branch.

## security-review-c3-f03: chunk 3 and the 0.3 features, reviewed (2026-09-23)

Recorded in `docs/security/CHUNK3_F03_REVIEW_2026-09-23.md`. Nothing blocks and nothing
needs a decision.

- H16 is built (ADR 0058, D-83) and holds as reviewed: no chunk 14 cut to accept. Its
  proofs cover all twelve proposal kinds and every module that opens the watch door; the
  per-function refinement is HARDENING H30.
- One medium finding waits as a named fix task, `merge-moved-ids` (H23): a vocabulary
  merge's audit row counts the records it moved but does not name them. Default: it is
  built with the next batch that owns `proposals/apply.py`.
## security-review-c7: the chunk 7 security review (2026-09-23, D-07, SRC-01, SRC-03)

- [ ] **May a bank's search text reach the embedder and the reranker?** D-07 says the Ask
      question is the only text of a bank's that we send to a model; a hybrid search sends
      what a reader types to the embedder and the reranker too, and so does a bank's own
      key through `POST /search/similar`. The chunk 7 plan made that conditional on your
      approval of the embedder (D-09). Since this review both are under the bank's AI
      switch (D-88): off, the search reads by words alone. Default if you say nothing: with
      the switch on, the query reaches the contracted EU embedder and reranker, and D-07's
      wording gains "and the search query, for retrieval only, under the same switch".
      The alternative is keyword-only search for every bank.

## r1-close-and-readiness: chunks 6 and 7, confirmed by default (2026-09-24)

Defaults taken when the chunks were built; nothing waits on them. Say so if one should change.

- [ ] **Chunk 6: who receives the weekly briefing mail.** Until COL-02's notification
      preferences exist (chunk 10), every active member holding `watch.read` in the bank
      (`home/tasks._recipients`). Confirm, or name a narrower group.
- [ ] **Chunk 6: a confirmed "So what?" travels in that mail, a draft never does.** The lead
      item's "So what?" is in the mail only once a person has confirmed it (WAT-05); an agent's
      draft leaves the line out (`home/mail.py`). Confirm that the confirmed text may leave the
      app by mail.
- [ ] **Chunk 6: Today's standing and the roadmap's own deadlines arrive in chunk 8.** HOM-01
      is `built` without the compliance standing panel, and HOM-03 stays `in_progress`: the
      roadmap shows regulatory dates only, and a bank's own deadlines join with the register and
      the cases (chunks 8 and 9). Confirm that is acceptable for the first test deploy.
- [ ] **Chunk 7: the regulatory scope applies to search.** FP-03 lists the feed, inventory,
      roadmap, briefing and reports, not search; search applies the scope by default with an
      "Outside our scope" switch, as `design/screens/tenant-search.html` draws it, so J-6 is not
      undone by a search. Confirm.
- [ ] **Chunk 7: a standard's question is refused in Ask.** Ask answers "no answer" to a
      question whose only support is a standard's record (D-81, "ask-standard-no-answer" above),
      so no standard's text is restated by a model. Confirm.

The chunk 7 cost-and-approval half of `k-anthropic` and the unrecorded retrieval track are the
D-07 and D-09 items at the top of this file. q-feed-token's answer stands as taken (D-52: the
token stays in the address, which is revocable, and the access log never writes it).

## The public page needs two brand decisions (2026-09-21)

The public page is designed and sits in `design/public/` (`index.html` opens in
a browser, `README.md` is the design note). Two of its choices are yours,
because they add to the brand rather than apply it. Defaults taken so the
design could be finished; say the word and the file changes in one block.

- [x] **A display serif.** Answered 2026-09-24: you approved the design as it
      stands ("I like this design, create this as a public page"), so Libre
      Caslon is in, on public pages only. `design/brand/README.md` names Hanken Grotesk and
      Noto Sans Mono and nothing else. The page sets its headlines in Libre
      Caslon Display, with Libre Caslon Text for the lede and record titles,
      because the brief asked for a page that feels like an old legal
      instrument and a grotesque cannot carry that. Both are SIL OFL, checked
      in `google/fonts` (`ofl/librecaslondisplay`, `ofl/librecaslontext`), so
      they self-host on the same terms as the other two. Default if you say
      nothing: Libre Caslon stays, on public pages only, and never behind
      auth. Decline and the page runs on Hanken Grotesk at the same scale.
- [x] **The plate headline size.** Answered 2026-09-24 with the design: the
      clamp stays, and `foundations.md` now records it. `design/system/foundations.md` sets `hero`
      at 36 / 40 and marks it "public pages only". That size was set for a
      grotesque; the same optical size in a serif reads a step smaller, so the
      page's headline runs from 36 px to 60 px with the viewport. Default if
      you say nothing: the clamp stays. Say so and it caps at 36 px, which
      makes the top of the page much quieter.
- [x] The footer carries `org. no. [to be set]`, and Terms, Privacy and
      Sub-processors link to the assurance section until those pages exist.
      Resolved in the build: the live page carries neither the number nor the
      placeholder links.

## The public page is built; three things before it faces the world (2026-09-24)

The page is in the app at `/welcome`. As you asked on 2026-09-24, it is where
a person without a session ends up: signing out, a session that timed out or
was revoked, or a first visit to any address. The sign-in page has a way back
to it, and sign-out revokes the session on the server so neither token works
again (proved by replaying the old refresh cookie in `public.journey.spec.ts`).

- [ ] **Set `NEXT_PUBLIC_SUPPORT_CONTACT`** on the web service, an email
      address. Until then "Write to us" is hidden and the invitation section
      says only that a bank's administrator sends the invitation.
- [ ] **Confirm two claims before the page is public.** § 5 names authorities
      per jurisdiction (Finanstilsynet, Lovdata, Finanssivalvonta, Finlex,
      EIOPA, the ECB and others) that neither the PRD nor the configured
      sources name yet; the PRD commits only to Swedish, Danish, Norwegian,
      Finnish and EU sources. § 6's "Leaving" and "The pack" describe tenant
      exit and the assurance pack, which are R3 (chunks 12 and 14, pending).
      The copy is as you approved it; say which to soften and the catalog
      changes in one file.
- [ ] **An idle session is found out at the next action, not on its own.**
      The server ends a session after `SESSION_IDLE_MINUTES_DEFAULT` (30)
      minutes without a refresh; the app learns it at the person's next click
      and goes to the public page then. A tab left open keeps showing what it
      showed until someone touches it. Default if you say nothing: it stays so.
      The alternative is a timer in the app that signs out on its own after the
      same number of idle minutes, which needs `GET /me` to carry the limit so
      it is not configured twice.
- [ ] **Sign-out on a dead connection.** If the sign-out request cannot reach
      the server, the app still forgets its token and leaves for the public
      page, but the server session lives until it idles out, and the refresh
      cookie (which only the server can clear) could sign the browser back in
      before then. That is how it was built in chunk 1 ("whatever the server
      answered"). Say if you would rather the app stay put and say the
      sign-out did not go through.
- [ ] **Read the Swedish copy** in `frontend/src/messages/public/sv.json`. It
      follows the app's existing terms (skyldighet, förslag, godkännande), but
      a native read of the headline and the questions is worth five minutes.

## r2-spec-d89: the bank's own regulations (PRD 0.7, 2026-09-25)

- [x] **D-89: confirm PRD 0.7's OWN group.** Non-blocking: chunk 11 builds it on the
      defaults in D-91 and ADR 0059 (design: `docs/plans/briefs/SCOPE_ITEMS.md`). A scope
      item is added through the regulatory scope request with four eyes and a passkey, and
      no agent or key writes one. The bank's own agent files what it finds as proposals only
      through its runner, and a person holding `private_records.approve` decides each one
      with a passkey. Three details are yours to overrule:
      1. **What reaches the model.** Default: only the item's jurisdiction and regime keys
         and the public pages it fetches, never the name the bank typed (D-07 and D-32 stay
         open). Say if the name may reach the bank's own agent.
      2. **What a control inventory is (OWN-05).** Default: a linked internal item of the
         control kind (REG-05) with the fields REG-05 gives it. Say if a control needs more
         (an owner, a test, a frequency).
      3. **Who confirms a bank's own record.** Default: a person, always; an agent never
         confirms one, unlike the shared library (D-62). Say if a bank may switch on a
         confirming agent for its own queue. **Answered (Alex, 2026-09-25): 1 as D-98 (the typed name may reach the bank's own agent, guarded), 2 as D-99, 3 default taken.**

## x-hardening-proposals: a correction now names its source (2026-09-25, H35, D-102)

- [ ] **The console's correction form gained one field.** A reviewer who changes a
      proposal's wording, date or scope before approving now gives "Source of your
      correction", the link or provision they read the new value in; the server refuses a
      changed value without one (security-review-c4 L5). The design card
      (`design/screens/console-queue.html`) shows no such field, so it was added in the
      form's existing style below the scope. Default if you say nothing: it stays. The
      proposer's replaced source is kept in the approval's audit row, not beside the
      reviewer's on the queue screen; say if the queue should show both (a column on
      `proposal`, D-102).
- [ ] **The confirming agent's next version should name its correction's source.**
      `backend/agents/library-confirmer/v2/prompt.md` says a correction goes through
      `payloadOverrides` and does not mention `fieldSources`; a shipped version is never
      edited, so it stays. Until a v3 says "name in `fieldSources` the page you read each
      changed value in", an agent's correction without one answers 422 `source_missing`
      and applies nothing (fails safe; it can still approve as proposed or reject).
      Default if you say nothing: v3 carries that line when the confirmer next changes.

## c10-reminders-core: triage reminders and the delegation hop, defaults taken (2026-09-25, COL-02, TEN-04)

Built by default; nothing waits on you. Say if any should change.

- [ ] **Who is reminded about a case awaiting triage.** Every active member whose
      roles hold `cases.triage`, since a new case has no owner yet. Default: so.
- [ ] **An overdue triage is reminded once.** The morning after its due time
      passes, not every day after; escalation is what follows it. Default: so.
- [ ] **The absent person's switch decides.** A reminder routed to a delegate
      follows the absent person's own `reminders` switch, because it is their
      notice; the delegate's switch is not read. Default: so.
- [ ] **A delegate already told for themself gets one notice.** It carries no
      "on behalf of", so they are not told twice about one record. Default: so.
- [ ] **The mail does not yet say on whose behalf it came.** The notification
      row names the absent person; the mail wording is the mail catalog's to add.
- [ ] **A missed beat hour skips that day.** If the worker's beat is down for
      the whole hour a bank's clock reads `REMINDER_SEND_HOUR`, that day's
      reminders are not sent, and an overdue triage that fell in that window is
      not reminded (escalation still follows). Also keep the hour off 02 to 03,
      which a daylight saving change skips or repeats. Default: accepted for R2;
      a "reminded through" stamp per bank would close it.
- [ ] **A mail the relay refused is not retried by the next day's run.** Its
      `email_message` row stays `failed`, and the notification is in the inbox.
      Default: so.
- [ ] **Several absent people sharing one delegate give the delegate one notice**
      per record, naming the first of them. Default: so.
- [ ] **The 403 proof uses a case write, not the sign-off route.** Chunk 9's
      approve route does not exist on this base yet; `c10-out-of-office` or the
      sign-off package should repeat the proof there.

## c9-signoff: evidence can leave a case while it waits for sign-off (2026-09-25)

- [ ] **Should the approval re-check the evidence, or should evidence lock?** A sign-off
      request needs no open action and one piece of evidence the scanner passed. While
      the case waits, the actions lock (`c9-actions`, `actions_locked`), but nothing in
      the plan locks the evidence: `removeEvidence` only sets `removed_at`, and a rescan
      could mark a file infected. The approval then closes a case whose evidence is gone,
      because the fixed guard on `signoff → closed` checks only the second person.
      Default taken: no change, since the guards are fixed (CLAUDE.md section 5) and this
      package does not own `state.py` or `evidence.py`. Two ways out: (a) `c9-evidence-b`
      refuses `removeEvidence` with 409 `actions_locked`-style `evidence_locked` while
      the case is in `signoff`, which mirrors the actions lock; or (b) the
      `signoff → closed` edge also carries the `no_open_action` and `clean_evidence`
      guards. The first keeps the state machine as designed; say which.

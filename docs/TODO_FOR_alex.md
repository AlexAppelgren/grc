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
- [ ] D-14: name the first library editors.
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

Nothing below was checked in the session that wrote PRD 0.3. **Every fact the
standards analysis states about ISO, IAF, PCI SSC, Swift, SIS, DS, Standard
Norge and SFS is unverified**, and no Verification log row claims otherwise.
Task `f03-T34` in `docs/plans/briefs/FEATURES_0_3_TASKS.md` fetches and logs
them, and nothing is seeded before it is green.

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

### Outside facts still to fetch (none of them checked yet)

These are the rows `f03-T34` must add to `docs/plans/Verification_Log.md`, each
fetched rather than recalled: the current ISO/IEC 27001 edition, its stage and
its amendment; the catalogue page and any per-standard feed; the Annex A
exclusion rule; the IAF MD 26 transition dates; the ISO/IEC 17021-1
certification cycle; ISO's systematic review cycle; the Nordic national
adoptions; the PCI DSS version and its retirement practice; the Swift CSCF
attestation window; and the licence and website terms of ISO, IAF, PCI SSC, SIS,
DS, Standard Norge and SFS. The research reported blocked pages on some of
these, and a row that cannot be fetched is logged as not verified, with the
reason.

## Before the first bank tenant
- [ ] D-07: contract an EU-pinned inference path.
- [ ] D-15: switch to `staging` and `main` with a second reviewer.
- [ ] Independent penetration test. Certification path (ISO 27001 or SOC 2).
- [ ] DPA, master agreement with the DORA Article 30 provisions, subprocessor list, insurance.
- [ ] Sentry on its EU region, or decide against it.
- [ ] The design for the screens the prototype lacks (`design/README.md`), if you want to shape them before the agent does.
- [ ] Overlay motion (tab bar open question 6): `Modal` and the More sheet open and close without animation, so the two stay consistent. Say if you want motion, and it is added to both together.
- [ ] Dark-theme screenshots of the tab bar and the More sheet, once the app has a real theme switch. Until then the dark tokens exist only under `.dark`, nothing sets that class, and `contrast.test.ts` pins the dark values instead.

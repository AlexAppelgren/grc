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
- [ ] D-05: the brand layer ships placeholders (`frontend/src/styles/brand.css`, values from `design/brand/README.md`). Two notes from Phase 0: every dark-theme brand value is also replaced (the brief forbade any SEB value surviving), and the dark negative pill background was deepened from Green's own pair (4.47:1) to `#6a1a0b` (4.84:1) to pass WCAG AA. Confirm or replace both when you pick the final values.
- [ ] D-02: confirm the production host and RP ID.
- [ ] D-05: choose our own brand green and sand, and clear the use of Green with SEB given your role there.
- [ ] D-14: name the first library editors.
- [ ] Security review F9 (medium): default taken on 2026-09-19 without waiting: adding or removing a passkey from a full session is allowed only while the session is younger than the step-up window or with a fresh step-up assertion; a sign-in or enrolment no longer counts as a step-up, so every step-up action asks for the passkey explicitly (ID-S14). Revert only if you want passkey management without a second prompt later in a session; the reasoning is in `docs/security/CHUNK1_AUTH_REVIEW_2026-09-19.md`.
- [ ] Security review F12 (medium): default taken on 2026-09-19: the enrolment code and invitation mails are sent by the worker after commit, so the neutral and sending paths take the same time. Nothing to decide unless you prefer synchronous mail on the test deploy.

## Before the first bank tenant
- [ ] D-07: contract an EU-pinned inference path.
- [ ] D-15: switch to `staging` and `main` with a second reviewer.
- [ ] Independent penetration test. Certification path (ISO 27001 or SOC 2).
- [ ] DPA, master agreement with the DORA Article 30 provisions, subprocessor list, insurance.
- [ ] Sentry on its EU region, or decide against it.
- [ ] The design for the screens the prototype lacks (`design/README.md`), if you want to shape them before the agent does.

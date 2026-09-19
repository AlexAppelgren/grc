# Things that need Alex, not an agent

Ordered by what blocks testing first. Nothing here is blocked on code.

## Before the first test deploy
- [ ] **Blocking now.** `docs/inputs/schema.sql` and `docs/inputs/data-model.md` are still missing (2026-09-19, checked during Phase 0). Phase 0 builds no domain tables and does not need them, but chunk 1 does: the build stops after Phase 0 until both land. Copy version 0.2 from the Compliance Data chat into `docs/inputs/`.
- [ ] Create the Railway project in EU West: Postgres with pgvector, Redis, a private bucket, services `api`, `worker`, `beat`, `web`. See `docs/runbooks/RAILWAY_DEPLOY.md`.
- [ ] Point a test host at the web service (for example `compliance-test.bleqq.com`) and set `WEBAUTHN_RP_ID` to it. Passkeys made on a `*.up.railway.app` host stop working the day the host changes.
- [ ] A transactional email sender on an EU region for invitation codes, with SPF and DKIM on the sending domain.
- [ ] D-09: an API key for the first embedding model to try. Until then the test deploy searches by keyword only.
- [ ] D-07: an Anthropic API key for the test environment.

## Before any real user enrols
- [ ] D-05: the brand layer ships placeholders (`frontend/src/styles/brand.css`, values from `design/brand/README.md`). Two notes from Phase 0: every dark-theme brand value is also replaced (the brief forbade any SEB value surviving), and the dark negative pill background was deepened from Green's own pair (4.47:1) to `#6a1a0b` (4.84:1) to pass WCAG AA. Confirm or replace both when you pick the final values.
- [ ] D-02: confirm the production host and RP ID.
- [ ] D-05: choose our own brand green and sand, and clear the use of Green with SEB given your role there.
- [ ] D-14: name the first library editors.

## Before the first bank tenant
- [ ] D-07: contract an EU-pinned inference path.
- [ ] D-15: switch to `staging` and `main` with a second reviewer.
- [ ] Independent penetration test. Certification path (ISO 27001 or SOC 2).
- [ ] DPA, master agreement with the DORA Article 30 provisions, subprocessor list, insurance.
- [ ] Sentry on its EU region, or decide against it.
- [ ] The design for the screens the prototype lacks (`design/README.md`), if you want to shape them before the agent does.

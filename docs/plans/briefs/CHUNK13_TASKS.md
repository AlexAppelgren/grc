# Chunk 13: tasks

Written 2026-09-20 by the planning workflow (read, plan, parallelism and coverage
critiques, revise). Each task runs in its own worktree or cloud session
(`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on
`main`. The task ids are the `c13-` package ids of `docs/plans/PARALLEL_PLAN.md`
section 3.3; nothing is dropped. Twenty of the 51 ids are split in two, three or four,
because a sub-agent task is about thirty minutes and the plan's own rule 9 stops a
package at sixty: seventeen keep the parent id on their first half, and three
(`c13-e2e-integrations`, `c13-fe-attest-waive`, `c13-security-review`) become two
evenly named halves. Two tasks are new, because INV-07 had no tenant surface.
"Changes from `PARALLEL_PLAN.md`" lists all of them.

## Revised 2026-09-20

A review of the first version found nine things wrong. Each is closed here, with the
smallest edit that keeps the format:

1. **HIGH — re-enrolment lost its four eyes.** `c13-sso-oidc` edits the re-enrolment
   branch but pinned nothing about the approval it needs. It now carries
   `tests_four_eyes` in its gates and a done-when: the second approver and the fresh
   assertion still stand, and the provider proof replaces the emailed code only.
2. **INV-07 had no tenant surface.** Nobody proposed or approved a private record on
   screen, although the private-obligation journey (split out below as
   `c13-e2e-private-obligation`) drives that UI and `c13-close` needs
   `approvePrivateProposal` reachable. `c13-cards-tenant-private` (wave 1) and
   `c13-fe-private-proposals` (wave 5) are added, and the waves and the key table
   with them.
3. **The allow-list exclusion sat in the wrong task.** `c13-ip-allowlist` was to test
   `receiveTicketCallback`, a route declared in wave 3 and served in wave 7. The
   exclusion and its test move to `c13-tickets-inbound`, which declares the route, and
   the line leaves ID-S24's done-when.
4. **A missing order.** `c13-private-sources` now depends on `c13-private-child-rls`:
   both own `backend/apps/watch/migrations/`, as the key table already said.
5. **An unreachable E2E step.** `c13-e2e-identity-admin` names the trusted-hop
   mechanism that makes "an address outside the list" real in Playwright, since the
   middleware reads the address only through `TRUSTED_PROXY_HOPS`.
6. **Three inconsistencies.** `c13-fe-sso-admin` is renamed to `c13-fe-sso` in the
   `secfe` note; "the last four through PRD 0.4" now names ID-S27, ID-S28, INV-S13 and
   PRO-S12, agreeing with the preconditions; and `c13-siem-stream` owns
   `backend/apps/integrations/app.md`, which it rewords.
7. **Owner item 11's last sentence was unbuilt.** Platform support switching SSO
   enforcement off after the out-of-band check is now `c13-sso-enforcement`'s, under a
   platform permission, a step-up and `record()`, and in the safe direction only.
8. **Seven packages were over the cap.** `c13-cards-admin`, `c13-ip-allowlist`,
   `c13-private-sources`, `c13-fe-source-requests`, `c13-sso-saml`, `c13-e2e-private`
   and `c13-private-child-rls` are each split at a green point, as rule 9 requires.
9. **The questions overstated what is open.** Open question 1's mechanism is settled
   by D-54 and owner item 7 (a reviewed constant, never an environment variable), so
   only the approval itself is open; non-blocking question 3 is dropped, because
   `assert_not_last_admin` and ID-S13 already answer it with 409 `last_admin`;
   questions 1 and 4 are marked as product confirmations whose invariant side is
   already settled; 2 and 5 stay open.

> **PRD 0.7 (D-89, D-91, ADR 0059, 2026-09-25).** INV-07 and the private proposal half of PRO-03 move to chunk 11 with group OWN, taking `c13-private-contract` and `c13-private-child-rls` with them; private sources (WAT-06, `c13-private-sources` and the watch packages) stay here.

## Scope, rules and defaults

Chunk 13 is integrations and enterprise access: signed webhooks and their delivery
log, ticket export and flow-back, the SIEM stream, SSO with verified domains and
SCIM, the IP allow-list, the bank's own private instruments, obligations and
sources, saved searches, following a record, yearly attestations and waivers, and
the remaining three UI languages. `Build_Plan.md` gives the chunk INT-01 to INT-03,
ID-12, ID-13, SRC-04, REG-06, WAT-06, INV-07, COL-03 and I18N-02. The chunk has 78
tasks in 15 waves, about 36 agent-hours of package work plus about 18 of review.

PRECONDITIONS: WHAT MUST BE ON MAIN BEFORE WAVE 1
- **PRD 0.4** (`origin/claude/prd-0-4-consolidation-ueuqak`, f5b2296). It carries
  D-48 to D-61, ADRs 0042 to 0053, the `private_records.approve` row in PRD §6, the
  reworded ID-12, INV-07, WAT-06, PRO-03 and AUD-03, and the scenario stubs this
  chunk un-skips (ID-S27, ID-S28, INV-S13, PRO-S12). Every ruling below rests on it.
- **`r1-readiness`** (parallel plan rule 11). Every task here that touches
  authentication, sessions, the proposal door or a dependency waits for it: the SSO
  tasks, `c13-ip-allowlist`, `c13-scim-*`, `c13-secret-box`, `c13-egress-client`,
  `c13-sso-domains` and the four `c13-private-*` tasks.
- **Task H-C** (`HARDENING.md`, H15): mixed tables get the split policy shape (a
  FOR SELECT policy with the mixed read rule, a FOR ALL policy limited to the
  session's own zone). `proposal` becomes a mixed table in `c13-private-contract`
  and the four library parents gain child policies in `c13-private-child-rls`;
  built on the old `rls_operations(mixed=True)` shape, a bank session could write
  another zone's rows. Nothing in the private-records area starts before H-C.
- **Chunk 5:** `c5-outbox-cursor` (the one ordered cursor over `outbox_event`, which
  every delivery in this chunk consumes), `c5-contract-models-watch` (Source,
  RegulatoryChange with `owner_tenant_id`), `c5-watch-registration`,
  `c5-cases-creation`, `c5-library-links-provenance`, `c5-fe-console-sources`,
  `c5-fe-watch-feed`.
- **Chunk 4:** `c4-proposal-kind`, `c4-approve-apply` (the apply path private
  proposals reuse), `c4-console-shell`, and through it `x-frontend-split`.
- **Chunk 7:** `c7-search-index`, `c7-hybrid-search-backend` and `c7-ask-screen`
  (saved searches are saved queries against them).
- **Chunk 8:** `c8-register-models`, `c8-reg-gaps`, `c8-reg-entity-status`,
  `c8-ten-teams`, `c8-home-register-feeds` and `c8-card-obligation-register`
  (attestations and waivers hang off `tenant_obligation` and its roadmap branch).
- **Chunk 9:** `c9-actions` (tickets export actions), `c9-signoff`, `c9-case-design`,
  `c9-fe-actions-panel`.
- **Chunk 10:** `c10-collab-models`, `c10-notifications-api`, `c10-fe-notifications`
  (follow and saved-search hits are notifications, and D-34 owns the recipient check).
- **Chunk 11:** `c11-security-policy` (the `security_policy` row the IP allow-list
  extends), `c11-research-requests`, `c11-run-scheduler` (a private source is
  checked by a run).
- **Chunks 6 and 12:** `c6-briefing-backend`, `c10-mail-catalog` and
  `c12-committee-pack`, whose server-side strings `c13-i18n-server` translates.
- Why they cannot wait: every task here delivers, notifies or approves something
  another chunk creates. A webhook with no outbox cursor, a saved search with no
  search, a private proposal with no apply path or an attestation with no
  `tenant_obligation` would each be built against a stub, which parallel plan rule 3
  forbids.

WHAT IT DELIVERS
- **INT-01.** `webhook_endpoint` and `webhook_delivery`; subscriptions filtered on
  event keys, with a signing secret shown once and kept in the secret box; delivery
  from `outbox_event` through the one cursor, in order per subject, after commit
  only; HMAC-SHA256 signatures with a timestamp; a delivery log with attempts,
  status and response time; backoff, auto-pause and manual redelivery; the admin
  screen with its delivery log.
- **INT-02.** `action_ticket`, one ticket per action through a `ticket_provider`
  kind, idempotent on the action id; the Jira adapter behind the seam; an inbound
  callback, signed and idempotent, that flows a closed ticket back to the action;
  "Send as tickets" on the actions panel.
- **INT-03.** A per-tenant SIEM connection; audit events streamed in order as
  newline-delimited JSON of the one documented envelope; the stream's lag readable
  by the tenant and, through chunk 14's window (D-59), by the console.
- **ID-12.** Verified domains (DNS TXT, one tenant per domain); an OIDC provider
  that replaces the emailed code at enrolment and re-enrolment for those domains;
  enforcement asked **after** the passkey at every sign-in, bound to the browser;
  SCIM as an API key with the single scope `scim` provisioning invitations and
  deactivations; SAML if its library passes Trivy and the Alpine image; the admin
  screen and the sign-in continuation.
- **ID-13.** An optional CIDR allow-list on the security policy, checked after
  authentication so the security log can name the member, with a 403
  `ip_not_allowed`.
- **INV-07, WAT-06, PRO-03 (private half).** `proposal.owner_tenant_id` set by the
  server from the target; forced row-level security on `proposal`; child-table
  policies under the four library parents; `private_records.approve` with a
  passkey step-up and the four-eyes constraint; private sources with their address
  checks and cap; and the proof that no private row, and no child of one, is
  indexed, embedded, reranked or sent to a model.
- **SRC-04.** Saved searches with stored keys, notification on a new hit, and "New
  since your last visit".
- **COL-03.** Following an instrument, obligation or change, with one notification
  per person per event.
- **REG-06.** Yearly attestation by the owner with its roadmap date, and waivers
  with an expiry that returns the gap to open when it lapses.
- **I18N-02.** da, nb and fi across the UI catalogs, the server mail catalogs and
  the seeded list labels, with `check:messages` gating all five languages.
- The chunk's own two security reviews, its fix package and its close.

RULINGS WHERE THE SOURCES DISAGREE
1. **A webhook and the SIEM stream carry ids, kinds and times, never tenant
   content.** INT-S4 says the stream "carries record ids and summaries"; D-22 says
   comment text never reaches outbox payloads or webhooks, and CLAUDE.md §5 keeps
   tenant content out of anything outside the tenant zone. The narrower rule wins:
   the delivered envelope is `{eventId, occurredAt, tenantId, topic, subjectType,
   subjectId, actorKind, actorId, stepUp}` and nothing else — no title, no summary,
   no before or after values, no free text at all. A receiver that wants detail
   reads the API with its own key, under its own permissions. `c13-int-contract`
   owns the envelope schema and a guard test that fails on any key outside the
   allowlist and on any value that is not an id, a key, a boolean or a timestamp.
   INT-S4 is reworded from "summaries" to "the ids, kinds and times of the audit
   rows", with an INPUT_DELTAS §1 row.
2. **Creating a webhook, a ticket connection or a SIEM connection needs a step-up.**
   `UI_Implementation_Plan.md` lines 301 and 302 say step-up "no". Playbook 4.2
   lists API key creation and security policy changes, and each of these three
   writes a credential: a signing secret, a tracker token, a stream token. So
   `POST /webhooks`, `POST /webhooks/{id}/secret`, `PUT /integrations/tickets` and
   `PUT /integrations/siem` carry `@requires_step_up`, and so does every SSO,
   domain, SCIM and allow-list write. Pausing and deleting do not: they are the safe
   direction, as chunk 6 ruled for calendar feeds. The tasks correct the two UI plan
   rows.
3. **`webhook_endpoint.secret_hash` becomes ciphertext.** `schema.sql` stores the
   signing secret as a hash, which cannot sign anything. The column becomes
   `secret_ciphertext`, `secret_key_id` and `secret_prefix` (the prefix for the
   screen), encrypted by `c13-secret-box`; the plaintext is returned exactly once at
   creation or rotation. INPUT_DELTAS §1 records it. An API key stays hashed,
   because verification only compares.
4. **There is no sign-in that starts at the identity provider** (D-58, ADR 0051).
   No route begins an authorisation request from an anonymous visitor, the callback
   is POST-only, an unsolicited response is refused and logged `idp_failed`, and
   `c13-fe-sso-signin` adds only the continuation shown **after** a successful
   passkey. ID-S23's old wording is already reworded on the PRD 0.4 branch.
5. **`tenant_domain.auto_join`, `default_roles` and `identity_provider.scim_token_hash`
   are not built** (D-58). A SCIM key is an ordinary `api_key` row whose single scope
   is `scim`; `POST /tenant/api-keys` answers 422 for that scope. The departure from
   `schema.sql` is already in INPUT_DELTAS on the PRD 0.4 branch; the tasks follow it
   and add no column of their own.
6. **The library keeps one door, now named in three places.** `ProposalDoorGuard`
   lists exactly `approveProposal`, `reverifyObligation` and
   `approvePrivateProposal` (D-57). Adding the third is a guard change, so
   `c13-private-contract` owns it alone, under a security review, and stops on an
   invariant question (parallel plan rule 12).
7. **A private record is tenant content, so nothing about it reaches the platform.**
   No console route lists a private proposal, a platform session's fetch answers
   404, and a support grant does not widen that (INV-S9 as reworded by PRD 0.4).
   `c13-private-obligations` drops the `mig:search` key the plan gave it: under item
   4 (D-51) the index holds shared rows only, so chunk 13 adds proofs, not columns.
8. **The model may read a private source's page; it may never read a private
   record.** The agent runner fetches the bank's public page and classifies it, so
   the source address and the fetched public text reach the EU runner — which is why
   Alex approves that address once (open question 1). Nothing stored afterwards goes
   back to a model: no AI-drafted "So what?" on a private change, no chunk, no
   embedding, no rerank, and find-similar answers from shared records only.
9. **The ticket export route stays on its designed path and is declared by the app
   that owns actions.** `openapi.yaml` puts it at
   `POST /changes/{changeId}/actions/export-tickets`. Ninja mounts routers by
   prefix, so the route is declared in `cases/api.py` (key `casesapi`) by
   `c13-tickets-export-api` and served by `integrations/tickets.py`. The plan's keys
   for that half change accordingly.
10. **Seven operation groups have no designed route.** `openapi.yaml` declares
    webhooks, the ticket connection, saved searches, attestations and waivers, and
    nothing for follow, source requests, SSO, verified domains, SCIM, the IP
    allow-list, the SIEM connection or private proposals. Each contract task that
    adds one writes an INPUT_DELTAS §1 row naming the operation ids it adds; each
    task that departs from a designed path writes its own row.
11. **The attestation and waiver routes are one contract.** The plan gives
    `c13-reg06-attestations` the keys `mig:register homecore`; the routes live in
    `register/api.py`, so it also holds `regapi` and declares the waiver operations
    at the same time, answering 501 until `c13-reg06-waivers` lands. Otherwise
    `c13-reg06-waivers` would have to edit `api.py`, which rule 2 reserves to the
    contract task.
12. **One relay, not two.** `c13-library-change-fanout` adds a dispatch entry to
    `c5-outbox-cursor`'s cursor and writes per-tenant fanout events; webhooks,
    follow and saved searches consume those. No task adds a second cursor, a
    `transaction.on_commit` hook or its own Celery relay (parallel plan ruling 9).
13. **No boot-guard change in this chunk.** The production boot guard is reserved to
    E4 and `c14-eu-data-location` (rule 8). A deployed environment without
    `INTEGRATION_SECRET_KEYS` therefore boots, and saving any integration answers
    422 `secrets_unavailable` with the operator row in `RAILWAY_VARIABLES.md`.

DEFAULTS TAKEN (each stated in its commit body, and copied into
`docs/TODO_FOR_alex.md` by `c13-close`)
- **Outbound calls go through one client.** `apps/shared/egress.py`, built on the
  standard library as `adapters/llm.py` already is, so no HTTP dependency is added:
  https only, no credentials in the URL, the host resolved once and the connection
  pinned to that address (no DNS rebinding), private, loopback, link-local,
  multicast and cloud-metadata addresses refused before and after every redirect, at
  most `EGRESS_MAX_REDIRECTS` (2) redirects, never to another scheme, a total
  timeout (`EGRESS_TIMEOUT_SECONDS`, 10), a response cap
  (`EGRESS_MAX_RESPONSE_BYTES`, 1 MiB) and a fixed user agent. Webhooks, the SIEM
  stream, tickets, OIDC discovery and private-source checks all use it.
- **The secret box is `cryptography`'s `MultiFernet`** over `INTEGRATION_SECRET_KEYS`
  (key id and key per entry, the first encrypts, the rest decrypt so a rotation
  needs no downtime). `cryptography` is already in `poetry.lock` at 50.0.1 through
  `webauthn`; the task pins it explicitly in `pyproject.toml` and changes no
  resolved version.
- **Signature.** `X-Bleqq-Signature: v1=<hex hmac-sha256 of "<timestamp>.<body>">`
  with `X-Bleqq-Timestamp` and `X-Bleqq-Event-Id`; a receiver's clock tolerance is
  documented, not enforced by us. Retries reuse the event id so the receiver dedupes.
- **Retries** are `WEBHOOK_MAX_ATTEMPTS` (6) with exponential backoff and jitter from
  `WEBHOOK_BACKOFF_SECONDS` (30), then the delivery is `failed` and stays in the log;
  `WEBHOOK_AUTO_PAUSE_FAILURES` (20) consecutive failures pause the endpoint and
  notify `integrations.manage` holders.
- **The SIEM stream is HTTPS POST of newline-delimited JSON** in batches of
  `SIEM_BATCH_MAX` (200) every `SIEM_INTERVAL_SECONDS` (60), with a bearer token from
  the secret box. Syslog and mTLS are cut. Lag is `now` minus the oldest undelivered
  event's `created`.
- **The stream and webhooks carry the tenant's own zone only.** A library or platform
  audit row (`tenant_id` NULL) never reaches a tenant endpoint, and a test pins it.
- **Tickets: one provider.** `jira` is built; `linear`, `azure_devops`, `github` and
  `servicenow` stay kinds with no adapter, and `PUT /integrations/tickets` answers
  422 `provider_not_available` for them.
- **The inbound ticket callback is authenticated by the provider's signature**, like
  the calendar feed is authenticated by its token (D-52): declared with its
  credential in the route list, never in `UNGATED_BY_DESIGN`, rate limited, and able
  to do exactly one thing — move an action whose ticket reference it names.
- **The IP allow-list applies to every authenticated request of that tenant**,
  session or tenant-bound API key, evaluated after authentication; the inbound ticket
  callback is the one exclusion, listed by route name in a test, because the
  tracker's addresses are not the bank's. `c13-ip-allowlist-enforcement` builds the
  exclusion set empty; `c13-tickets-inbound`, which declares the route, adds the one
  entry and owns its test (finding 3). An admin cannot save a list that excludes
  the address they are calling from (409), mirroring D-55's self-lockout rule.
- **SCIM never removes the last admin.** A deactivate that would leave the tenant
  without an admin answers 409 `last_admin`, and the other admins are notified, so
  the directory can be corrected. SCIM does no group-to-role sync (D-58).
- **The SCIM default role is checked three times**: when it is chosen, when that role
  is edited, and at every create. It may not hold `members.manage`, `roles.manage`,
  `security.manage` or `integrations.manage`.
- **A saved search stores keys, never labels** (playbook 15), belongs to one person,
  is capped at `SAVED_SEARCHES_MAX` (20) per person, and carries `last_opened_at` so
  "New since your last visit" is a per-search fact rather than a session fact
  (INPUT_DELTAS row: the column is new).
- **Follow is personal and grants nothing.** A follower sees only what their
  permissions already allow; the notification is filtered by D-34's one recipient
  check, and a person who both follows and takes part gets one notification.
  `notification.kind` gains `followed_change` (INPUT_DELTAS row).
- **Attestation** is yearly, `ATTESTATION_INTERVAL_MONTHS` (12) from the last one, by
  the obligation's owner only (server-checked), recording the compliance status at
  the time; a waiver needs `risk.accept.approve` and a step-up, and a nightly
  `@tenant_task` returns a lapsed waiver's gap to open.
- **Private sources** are capped at `PRIVATE_SOURCES_MAX` (20) per bank, are public
  https pages, and are re-checked at the start of every run; a private instrument
  holds no provisions in R3 (D-57's two stated cuts).
- **A private proposal's step-up is the approver's**, and `private_records.approve`
  is never granted to a platform role and never accepted as an API key scope; a test
  proves both.
- **The three new languages ship as catalogs only.** No screen, copy or component
  changes with them; a missing key fails `check:messages`, and the E2E suite keeps
  running in its one pinned language.

CUT, WITH REASONS
- **SAML**, if `pysaml2`'s native XML dependencies break the Alpine image or Trivy
  reports MEDIUM or above (D-58's own order: cut SAML first, then enforcement).
  `c13-sso-saml` is that check and nothing else, so it closes green either way;
  `c13-sso-saml-binding` is dispatched only if it passed, and nothing else depends on
  either.
- **Ticket providers other than Jira**, SIEM transports other than HTTPS JSON, and
  webhook replay of a whole history (one delivery can be redelivered; a bulk replay
  needs a cursor per endpoint nobody asked for).
- **Group-to-role sync, auto-join by domain and SCIM Groups** (D-58).
- **Private provisions and private internal documents**: D-57's cuts; internal
  documents wait for D-07.
- **`user_item_state`** (read, bookmarked, snoozed): no chunk 13 requirement or
  scenario asks for it; only `follow` is COL-03.
- **A per-tenant webhook event catalogue screen**: the event keys are the audit
  actions already listed in the admin audit log, and the screen offers them from
  `GET /reference/event-types`, a read added by `c13-int-contract`, not a new
  managed list.
- **ID-07's credential policy** (`c11-credential-policy`, D-55) and **ID-S29**: chunk
  11 owns them. Chunk 13 touches `security_policy` only for the allow-list columns.
- **The console's per-tenant stream lag** (D-59) is chunk 14's window;
  `c13-siem-stream` exposes the tenant's own figure and writes the `job_run` rows
  chunk 14 reads.

PLAN-WIDE RULES
1. **Slots.** Every backend and E2E gate runs inside the task's slot:
   `set -a; . ./.env.worktree; set +a`. A cloud session runs
   `bash scripts/cloud-setup.sh` (with `--e2e` where the gates include E2E) instead.
2. **Generated files.** No task commits `openapi.json`,
   `frontend/src/types/api.generated.ts` or
   `frontend/tests/e2e/support/e2e-passkeys.generated.ts`. A task regenerates them
   locally to run `contract_drift.py` and the typecheck, then reverts them. The main
   agent regenerates and commits them at the merge, with the navigation and pill
   snapshot baselines when `registry.ts` or `tone-by-kind.ts` changed.
3. **Contracts land first, one at a time per app.** `integrations/api.py` and
   `schemas.py` (key `intapi`) are written once by `c13-int-contract`;
   `identity/api.py` and `schemas.py` (key `idapi`) by `c13-sso-domains` and then
   `c13-sso-idp-contract`; `register/api.py` (key `regapi`) by
   `c13-reg06-attestations`; `proposals/api.py` (key `prop`) by
   `c13-private-contract`; `collab/api.py` by `c13-follow-contract`;
   `search/api.py` by `c13-saved-search-contract`; `cases/api.py` (key `casesapi`)
   by `c13-tickets-export-api`; `tenants/api.py` (key `ten`) by `c13-ip-allowlist`.
   Every other task owns its own module and its tests and never `api.py`. A logic
   task that finds the contract wrong stops and reports. Two of these are
   contract-and-logic tasks, because the whole area is under thirty minutes:
   `c13-follow-contract` and `c13-saved-search-contract` serve their own routes
   instead of stubbing them, and say so in their done-conditions. Every other route a
   contract task declares answers 501 until its logic task lands.
4. **Stubs and screens.** A route whose logic has not landed answers 501 `not_built`
   behind its real gate, and no screen task calls a stub: each screen depends on
   every backend task whose routes it calls. `c13-close` proves no 501 is left.
5. **Scenario stubs already exist.** INT-S1 to S5, ID-S23, ID-S24, ID-S27, ID-S28,
   INV-S9, INV-S13, PRO-S12, WAT-S8, SRC-S7, COL-S4, REG-S9, I18N-S3 and I18N-S4 are
   on main as skips or fixmes (ID-S27, ID-S28, INV-S13 and PRO-S12 through PRD 0.4,
   as the preconditions say). No scenario-stub task is needed; each building task
   deletes only its own skip line.
6. **Append ledgers** (parallel plan rule 5): `docs/inputs/INPUT_DELTAS.md`,
   `backend/scripts/contract_drift_pending.txt`, `docs/TODO_FOR_alex.md`,
   `docs/plans/Verification_Log.md`, `docs/plans/briefs/HARDENING.md`, the UI plan's
   ledger rows and status cells, `backend/.env.example`,
   `docs/runbooks/RAILWAY_VARIABLES.md`, settings banners in
   `backend/config/settings.py`, router mounts in `backend/config/api.py`,
   `apps/shared/kinds.py`, `factories.py`, `routes.py`, the route lists in
   `permissions.py`, the guarded-table lists in `tests_rls.py`, `tests_four_eyes.py`
   and `tests_seed_integrity.py`, `apps/shared/e2e_seed.py`, `e2e_logins.py` and
   `e2e_passkeys.py` and `frontend/tests/e2e/support/passkeys.ts` (one seed call or
   login per task), `frontend/src/shared/navigation/registry.ts` and
   `features/shared/tone-by-kind.ts` entries, each app's `app.md` status cells and
   `tests_scenarios.py` skip lines, and each `*.journey.spec.ts` (own test blocks
   only). Each task adds only its own lines and never edits another's. An
   **allowlist** entry is not an append: it is a guard change (rule 8 below).
7. **Kinds and subject types.** A task that needs a new subject type, status kind or
   reason kind appends it to `apps/shared/kinds.py` and to the vocabulary or CHECK
   that carries it, its own entries only, in the same commit as the model that uses
   it. No task turns a kind into a free-text column.
8. **Coverage floors.** `backend/scripts/coverage_gate.py` gets the chunk 13 floors
   once, from `c13-close`, measured at the close with the date beside each. A task
   states its own `coverage report --include` threshold in its done-condition and
   never lowers an existing floor.
9. **Guards and security review.** The guard changes in this chunk are named and
   nowhere else: `ProposalDoorGuard`'s third route and `proposal`'s policies
   (`c13-private-contract`), the four parents' child-table policies
   (`c13-private-child-rls` for the watch parents, `c13-private-child-rls-library`
   for the library parents), the allow-list check in `middleware.py`
   (`c13-ip-allowlist-enforcement`), its one exclusion entry (`c13-tickets-inbound`,
   which declares the route) and the enforcement step in the session flow
   (`c13-sso-enforcement`). Each of those six, plus every task marked
   **Security review: yes**, gets a security-review sub-agent over
   `git diff main...<branch>` before the squash merge, with `tests_rls`,
   `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`,
   `tests_audit_on_write` and `tests_four_eyes`. No task touches the library-fence
   allowlist, `UNGATED_BY_DESIGN` or the production boot guard.
10. **Cloud sessions stop on invariant questions** (parallel plan rule 12). The four
   guard tasks above and every `c13-private-*` task carry that instruction in their
   prompt explicitly.
11. **Merge at once.** Each task is squash-merged and the full checklist run as soon
    as it passes review (WORKTREES step 5). Finished work never waits for the chunk.
12. **Clocks.** Everything dated is anchored to the tenant-local date plus a fixed
    wall time (CLAUDE.md §8.3 and §11): an attestation due in 13 months, a waiver
    that lapses, a delivery's backoff and a stream's lag are all computed from the
    anchor, never from the real "today", and tests freeze the clock.
13. **Secrets never leave once.** A plaintext secret appears in exactly one response,
    at creation or rotation, is never logged, never lands in an audit `after` value,
    an outbox payload or a Sentry breadcrumb, and a shared test
    (`tests_no_secret_in_logs.py`, created by `c13-secret-box`, extended by each task
    that adds a secret) proves it per secret kind.
14. **E2E.** CLAUDE.md §11 is pasted in full into every task prompt that touches UI or
    journeys: the real stack, a production Next build, sign-in by passkey through the
    UI, `test` imported from `support/api-guard`, expected errors declared where they
    happen, `seed_e2e` extended and never mocked. A receiver, a tracker and an
    identity provider are seeded as local test doubles inside the stack (rule 15), not
    as mocked API responses in the browser.
15. **Three test doubles, each with a production guard.** The webhook and SIEM
    receiver (`c13-e2e-integrations-webhooks`), the ticket tracker
    (`c13-tickets-jira`) and the identity provider (`c13-sso-test-idp`) are real
    HTTP endpoints served by the backend under `E2E_MODE` only, each refusing to load
    on a deployed environment exactly as the mail outbox does, each with its own test
    pinning that refusal.
16. **Scenario ownership.** Exactly one task un-skips each integration test and one
    un-fixmes each journey. Where a scenario has two halves that cannot land
    together, the first owner un-skips it green up to a named line and the second
    extends it, as chunk 8's REG-S5 does:

| Scenario | `@integration` | `@e2e` |
|---|---|---|
| INT-S1 | `c13-webhook-delivery` | `c13-e2e-integrations-webhooks` |
| INT-S2 | `c13-webhook-delivery` (delivery half), extended by `c13-tickets-inbound` (inbound half) | — |
| INT-S3 | `c13-tickets-export-api` (export half), extended by `c13-tickets-inbound` (flow-back) | `c13-e2e-integrations-tickets` |
| INT-S4 | `c13-siem-stream` | `c13-e2e-integrations-webhooks` |
| INT-S5 | `c13-int-subscriptions` | — |
| INT-S6 (new) | `c13-int-contract` | — |
| ID-S23 | `c13-sso-oidc` | — |
| ID-S24 | `c13-ip-allowlist-enforcement` | `c13-e2e-identity-admin` (the tag is added; see below) |
| ID-S27 | `c13-sso-enforcement` | `c13-e2e-identity-admin` (the tag is added; see below) |
| ID-S28 | `c13-scim` (key and default-role half), extended by `c13-scim-users` (the create refusal) | — |
| INV-S9 | `c13-private-child-rls-library` (the watch half of the policies lands first, in `c13-private-child-rls`) | — |
| INV-S13 | `c13-private-no-ai-index` | — |
| PRO-S12 | `c13-private-approval` | — |
| WAT-S8 | `c13-private-source-visibility` (request and ownership half), extended by `c13-private-source-runs` (the re-check at each run) | `c13-e2e-private` |
| SRC-S7 | `c13-saved-search-notify` | `c13-e2e-saved-searches` |
| COL-S4 | `c13-follow-notify` | `c13-e2e-follow` |
| REG-S9 | `c13-reg06-attestations` (attestation half), extended by `c13-reg06-waivers` | `c13-e2e-register` |
| I18N-S3 | — | `c13-i18n-wiring` |
| I18N-S4 | — | `c13-i18n-wiring` |

ID-S24 and ID-S27 carry `@integration` only on `main`. Enterprise access is bought on
the promise that it works in the product, not only in a test client, so
`c13-e2e-identity-admin` adds `@e2e` to both headings in `identity/app.md` and writes
their journey blocks in `identity.journey.spec.ts`; the convention allows a chunk to
add what the PRD did not cover, and the requirements-coverage gate then holds both
halves. ID-S29 (credential policy) stays with `c11-credential-policy`; ADM-S1's "Integrations
and Security policy are absent without their permission" stays with its own chunk and
is re-run by `c13-close` once the two nav entries exist. The contract, card, screen and
i18n-catalog tasks contribute to scenarios and un-skip none.

CHANGES FROM `PARALLEL_PLAN.md`, WITH REASONS
- **Twenty packages are split into forty-five tasks**, seventeen keeping the parent
  id on their first half:
  `c13-cards-admin` → `+c13-cards-admin-security`; `c13-cards-tenant-other` →
  `+c13-cards-source-requests`; `c13-int-contract` → `+c13-int-subscriptions`;
  `c13-webhook-delivery` → `+c13-webhook-retries`; `c13-tickets-export` →
  `+c13-tickets-export-api`; `c13-fe-integrations-screen` →
  `+c13-fe-integrations-connections`; `c13-sso-oidc` → `+c13-sso-test-idp` and
  `+c13-sso-enforcement` (D-58 adds about 80 minutes and says to split the provider
  out); `c13-scim` → `+c13-scim-users`; `c13-fe-sso` → `+c13-fe-sso-signin`;
  `c13-private-contract` → `+c13-private-child-rls` and `+c13-private-approval`
  (D-57 asks for the contract and the child-table RLS to be separate packages);
  `c13-private-sources` → `+c13-private-source-runs`; `c13-private-obligations` →
  `+c13-private-no-ai-index`; `c13-reg06-attestations` →
  `+c13-reg06-attest-roadmap`; `c13-fe-attest-waive` → `c13-fe-attest` and
  `+c13-fe-waive`; `c13-security-review` → `c13-security-review-integrations` and
  `+c13-security-review-identity-private`; `c13-e2e-integrations` →
  `c13-e2e-integrations-webhooks` and `+c13-e2e-integrations-tickets`. The 2026-09-20
  revision splits seven more, each at its own green point (finding 8):
  `c13-cards-admin` → `+c13-cards-admin-connections` (the webhook half of the card is
  complete before the two connection sections); `c13-ip-allowlist` →
  `+c13-ip-allowlist-enforcement` (the list is stored and refused before the guard
  reads it); `c13-private-child-rls` → `+c13-private-child-rls-library` (one migration
  per owning app, the watch parents first); `c13-private-sources` →
  `+c13-private-source-visibility` (a request is validated and queued before the
  private branch creates an owned source); `c13-fe-source-requests` →
  `+c13-fe-source-list` (the form before the list); `c13-sso-saml` →
  `+c13-sso-saml-binding` (the library check and its refusal path close green whether
  or not the binding is built); and `c13-e2e-private` → `+c13-e2e-private-obligation`
  (one journey each). Every split falls at a green point, and the second half inherits
  the first's dependencies.
- **Two tasks are new, outside the 51 ids.** INV-07 had no tenant surface: nothing
  proposed or approved a private instrument or obligation on screen, although
  `c13-e2e-private`'s second journey drives that UI and `c13-close`'s reachability
  audit needs `approvePrivateProposal` reachable. `c13-cards-tenant-private` draws it
  and `c13-fe-private-proposals` builds it (finding 2).
- **`c13-egress-client` loses the `deps` key.** `adapters/llm.py` already speaks HTTP
  through `http.client` and `urllib`, the cloud rules forbid a session changing
  dependencies, and a shared `backend/.venv` link makes a dependency change reach
  every worktree. The client is standard library only.
- **`c13-secret-box` keeps `deps`** for one explicit pin of `cryptography`, already
  resolved at 50.0.1 through `webauthn`, so no version moves.
- **`c13-tickets-export-api` takes `casesapi` instead of `intapi`** (ruling 9): the
  designed path sits under `/changes/{changeId}/actions/`, which the cases router
  serves.
- **`c13-reg06-attestations` gains `regapi`** (ruling 11), so the waiver routes are
  declared once, with the attestation routes.
- **`c13-private-obligations` drops `mig:search`** (ruling 7): the index holds shared
  rows only, so the task adds proofs, not columns.
- **New key `secfe`** for `frontend/src/features/security/` and its catalog
  namespace, held one at a time by `c13-fe-allowlist`, `c13-fe-sso` and
  `c13-fe-sso-signin`, which would otherwise have shared a directory.
- **`c13-fe-follow`, `c13-fe-attest` and `c13-fe-waive` serialize on `obpage`**, the
  obligation page component, and run in three different waves.
- **`c13-i18n-da`, `-nb` and `-fi` run side by side**: after `x-frontend-split` each
  language is its own file per namespace, so the three touch no common file. They
  still wait for the global catalog freeze (every R2 and R3 screen package), which is
  a dispatch condition, not a chunk 13 wave.

CHANGES FROM THE TWO CRITIQUES
- **Parallelism.** Seven collisions and one wrong dependency were found and fixed:
  `c13-cards-tenant-register` and `c13-cards-tenant-other` both draw on
  `tenant-obligation.html`, so they now serialize on that card instead of sharing
  wave 1; `c13-cards-source-requests` lost a dependency it did not need, since its
  two cards touch neither of the other's files; `c13-webhook-delivery`,
  `c13-siem-stream` and `c13-webhook-retries` all register in
  `integrations/tasks.py`, so `inttasks` now orders them across three waves rather
  than two of them sharing one; `c13-tickets-inbound` lost its dependency on
  `c13-webhook-retries`, which it never used, freeing a wave; `c13-follow-notify`
  gained the `collab` migration that its new `notification.kind` value needs, and
  with it the `mig:collab` order behind `c13-follow-contract`; `c13-fe-allowlist`
  now says it may find `features/security/` already created by
  `c11-fe-admin-security`, rather than creating a second one; and the wave list was
  rebuilt from dependency depth, which turned 13 optimistic waves into 15 honest
  ones and removed four cases of a task sitting in the same wave as something it
  depends on.
- **Coverage.** Six gaps were found and closed: `listEventTypes` was declared by the
  contract task and served by nobody, so the contract task now serves it;
  `c13-siem-stream` wrote `job_run` rows that chunk 14 builds, so the tenant's lag
  now lives on the connection row and the console's view stays chunk 14's;
  nothing proved that the envelope of ruling 1 stays fixed, so INT-S6 is added to
  `integrations/app.md` and owned by `c13-int-contract`; ID-S24 said nothing about a
  tenant API key or about an admin locking themselves out, both of which the task
  builds, so it is reworded and its owner named; no task ran the UI plan's
  reachability audit or re-ran ADM-S1 with the two new nav entries, which `c13-close`
  now does; and no rule said who may add a subject type or a status kind, which is
  now plan-wide rule 7. A seventh gap: ID-S24 and ID-S27 were given journey owners
  although both carry `@integration` only on `main` and neither has a block in
  `identity.journey.spec.ts`, so `c13-e2e-identity-admin` now adds the tag and writes
  both blocks, rather than the brief claiming a fixme that does not exist.
- **Rejected, from the parallelism critique:** merging `c13-follow-contract` and
  `c13-saved-search-contract` into one "personal reads" task. They own different
  apps, different migrations and different scenarios, and the merge would put
  `mig:collab` and `mig:search` in one package for no gain.
- **Rejected, from the coverage critique:** adding a scenario for the egress client's
  SSRF refusals. Its rules are a guard with a test each, not product behaviour a
  person can observe; an `@integration` scenario would restate the test and drift
  from it. The proof lives in `tests_egress.py` and in
  `c13-security-review-integrations`.
- **Rejected, from the coverage critique:** giving chunk 13 a scenario-stub task.
  Every scenario this chunk builds already exists as a skip or a fixme on `main`,
  ID-S27, ID-S28, INV-S13 and PRO-S12 through PRD 0.4, so a stub task would only add INT-S6, which its own
  contract task adds in the same commit that makes it green.

## Waves

A wave is the dependency depth inside the chunk, not a clock. Tasks in one wave have
disjoint owned paths and hold no key another task in the same wave holds; dispatch is
still by readiness.

1. `c13-cards-admin`, `c13-cards-admin-security`, `c13-cards-tenant-other`,
   `c13-cards-source-requests`, `c13-cards-tenant-private`, `c13-egress-client`,
   `c13-follow-contract`, `c13-saved-search-contract`, `c13-i18n-seed-labels`,
   `c13-ip-allowlist`, `c13-reg06-attestations`, `c13-private-contract`
2. `c13-cards-admin-connections`, `c13-cards-tenant-register`, `c13-secret-box`,
   `c13-fe-follow`, `c13-fe-saved-searches`, `c13-fe-allowlist`,
   `c13-ip-allowlist-enforcement`, `c13-private-child-rls`,
   `c13-private-approval`, `c13-reg06-attest-roadmap`, `c13-reg06-waivers`
3. `c13-int-contract`, `c13-sso-domains`, `c13-private-child-rls-library`,
   `c13-private-sources`, `c13-fe-attest`
4. `c13-int-subscriptions`, `c13-sso-idp-contract`, `c13-private-obligations`,
   `c13-private-source-visibility`, `c13-library-change-fanout`, `c13-fe-waive`,
   `c13-fe-source-requests`
5. `c13-webhook-delivery`, `c13-sso-oidc`, `c13-tickets-export`,
   `c13-private-no-ai-index`, `c13-private-source-runs`, `c13-follow-notify`,
   `c13-saved-search-notify`, `c13-fe-source-list`, `c13-fe-private-proposals`,
   `c13-fe-console-source-requests`
6. `c13-siem-stream`, `c13-sso-test-idp`, `c13-scim`, `c13-tickets-export-api`,
   `c13-e2e-private`, `c13-e2e-private-obligation`, `c13-e2e-follow`,
   `c13-e2e-saved-searches`, `c13-e2e-register`
7. `c13-webhook-retries`, `c13-sso-enforcement`, `c13-scim-users`,
   `c13-tickets-inbound`
8. `c13-fe-integrations-screen`, `c13-tickets-jira`, `c13-sso-saml`
9. `c13-fe-integrations-connections`, `c13-fe-sso`, `c13-sso-saml-binding`
10. `c13-fe-tickets-screen`, `c13-fe-sso-signin`, `c13-e2e-integrations-webhooks`,
    `c13-i18n-server`
11. `c13-e2e-integrations-tickets`, `c13-e2e-identity-admin`
12. `c13-security-review-integrations`, `c13-security-review-identity-private`
13. `c13-review-fixes`, `c13-i18n-da`, `c13-i18n-nb`, `c13-i18n-fi`
14. `c13-i18n-wiring`
15. `c13-close`

The keys that force an order, all of them respected by the waves above:

| Key | Order |
|---|---|
| `intapi`, `mig:integrations` | `c13-int-contract` → `c13-tickets-export` → `c13-tickets-inbound` |
| `inttasks` | `c13-webhook-delivery` → `c13-siem-stream` → `c13-webhook-retries` |
| `idapi`, `mig:identity` | `c13-sso-domains` → `c13-sso-idp-contract` → `c13-scim-users` (the SCIM mount) → `c13-sso-saml` → `c13-sso-saml-binding` |
| `idp` | `c13-sso-oidc` → `c13-sso-enforcement` |
| `idkeys` | `c13-scim` → `c13-scim-users` |
| `prop`, `mig:proposals`, `apply` | `c13-private-contract` → `c13-private-approval` → `c13-private-obligations` |
| `mig:watch`, `watchapi` | `c13-private-child-rls` → `c13-private-sources` → `c13-private-source-visibility` |
| `mig:library` | `c13-private-child-rls-library` alone |
| `ten`, `middleware` | `c13-ip-allowlist` → `c13-ip-allowlist-enforcement` → `c13-tickets-inbound` (the one exclusion entry) |
| `regapi`, `mig:register` | `c13-reg06-attestations` → `c13-reg06-waivers` |
| `mig:collab`, `collabtasks` | `c13-follow-contract` → `c13-library-change-fanout` → `c13-follow-notify` |
| `obpage` | `c13-fe-follow` → `c13-fe-attest` → `c13-fe-waive` |
| `intfe` | `c13-fe-integrations-screen` → `c13-fe-integrations-connections` → `c13-fe-tickets-screen` |
| `secfe` | `c13-fe-allowlist` → `c13-fe-sso` → `c13-fe-sso-signin` |
| `watchfe` | `c13-fe-source-requests` → `c13-fe-source-list` |
| `propfe` | `c13-fe-private-proposals` alone |
| `deps` (local only) | `c13-secret-box` → `c13-sso-domains` → `c13-sso-saml` |
| the `tenant-obligation.html` card | `c13-cards-tenant-other` → `c13-cards-tenant-register` |
| the `admin-integrations.html` card | `c13-cards-admin` → `c13-cards-admin-connections` |

If SAML fails its library check (see the cut list), `c13-sso-saml` closes with the
note, `c13-sso-saml-binding` is never dispatched and nothing else moves: no task
depends on either and `c13-e2e-identity-admin` uses the OIDC test provider. If Alex's approval for the private-source runner address
(open question 1) is late, `c13-private-source-runs` stops after its checks and the
run half waits; WAT-S8's last line waits with it, `c13-e2e-private` asserts the
waiting state instead of a run, and `c13-close` names WAT-06 in progress. Everything
else proceeds.

## Open questions

- **Open question 1 — Alex's approval to send a private source's address to the EU
  agent runner (needs Alex; it is his approval by definition, not a design choice).**
  D-57 says a private source "runs only after you approve sending its address to the
  EU agent runner". A run fetches the bank's chosen public page and classifies it, so
  two tenant-confidential facts reach the runner: the address the bank chose to
  watch, and the page's text. Nothing stored afterwards ever goes back to a model
  (ruling 8).

  **The mechanism is settled, not a choice.** D-54 and owner item 7 rule that every
  processor allowlist is a constant in the production-safety block, never an
  environment variable, so that a transfer can never follow from a changed variable.
  Approval is therefore `PRIVATE_SOURCE_RUNNERS_APPROVED`, a reviewed constant beside
  item 7's lists, starting empty: private sources are registered and visible but never
  scheduled until an endpoint is listed, and the screen says so in plain words. An
  approval per source by the platform is refused by D-57, because a platform person
  would read a bank's private source address; and dropping the runs would leave WAT-06
  at half and a source the bank cannot use. Neither is on the table.

  **What is open is only Alex's approval itself:** which runner endpoint, in which
  region, he is willing to send a bank's private source address and page text to. It
  lands as one reviewed line in the constant plus a `Verification_Log.md` row naming
  the endpoint and its region, in `c13-private-source-runs` or a one-line follow-up.

  This gates the run half of `c13-private-source-runs` and WAT-S8's last line;
  `c13-e2e-private` then asserts the waiting state instead of a run. Registration, the
  address checks, the cap, the RLS and every screen are unaffected.
- Non-blocking, to confirm (the defaults are taken and nothing waits);
  `c13-close` writes all four into `docs/TODO_FOR_alex.md`:
  1. **A product confirmation; the invariant side is settled.** That a webhook and the
     SIEM stream carrying ids, kinds and times only — no titles, no summaries
     (ruling 1) — is what a bank's SIEM needs, given that INT-S4 as designed said
     "summaries" and the receiver must call the API for detail. What may not be sent
     is not in question: D-22 keeps comment text out of outbox payloads and webhooks,
     and CLAUDE.md §5 keeps tenant content out of everything beyond the tenant zone.
     Only whether ids and kinds are *enough* for a bank is being asked.
  2. That the IP allow-list also binds the bank's own API keys, with the signed
     inbound ticket callback as the one exclusion.
  3. **A product confirmation; the invariant side is settled.** That a tenant's
     webhooks and SIEM stream receive events about the tenant's own private records
     (ids only), since those stay inside the bank. D-57 and CLAUDE.md §5 already
     settle that the record's text never leaves and that no other tenant, and no
     platform surface, learns of it; only whether the bank wants its own private
     records in its own stream at all is being asked.
  4. That `jira` is the only ticket provider built in R3, the other four kinds
     answering 422 `provider_not_available`.

  The first version also asked whether SCIM should answer 409 rather than deactivate
  the last admin. That is not open: `assert_not_last_admin` in
  `backend/apps/identity/members_logic.py` already raises `last_admin` for every path
  that would leave a tenant without an administrator, and ID-S13 already gives the
  last admin a recovery through platform support after an out-of-band check. SCIM
  follows the rule the product already has; `c13-scim-users` builds no new answer.
- **Answered already, and not re-opened here.** q-private is item 10 of
  `OWNER_RECOMMENDATIONS.md` ("YES", D-57, ADR 0050) and q-sso is item 11 ("YES",
  D-58, ADR 0051); both are built as recommended. q-eu-guards (item 7, D-54) fixes
  the EU rule this chunk obeys but changes no boot guard here (ruling 13).
  q-platform-counters (item 12, D-59) owns the console's view of stream lag, which is
  chunk 14's. q-credential (item 8, D-55) and ID-S29 are chunk 11's. q-Q1 (item 3,
  D-50) removed the console problem-report surface, so no task here reads or streams
  a problem report, and a test pins `problem_report.*` out of every tenant delivery.

## Tasks

### c13-cards-admin: the admin Integrations card

**Requirements:** INT-01, INT-02, INT-03, ADM-01
**Scenarios:** none (it un-skips nothing)
**Depends on:** nothing

Draw `design/screens/admin-integrations.html`. The prototype has no integrations
view, so the card is built from `design/system/foundations.md` and the closest
existing card, `admin-api-keys.html`, whose once-shown-secret pattern the webhook
secret reuses. This half draws the webhook sections only: Webhooks (list with url
host, event keys as pills, active or paused, last delivery; Add opens the dialog that
shows the secret once and says it is never shown again; Rotate secret; Pause; Delete)
and Deliveries (per endpoint: time, topic, status, response code, attempts, duration,
a Redeliver control). The two connection sections are `c13-cards-admin-connections`'s.
Every state from `states.html`: empty, loading, error, denied for a member without
`integrations.manage`, and the paused-endpoint notice. Pills come from the six
tones by kind (`positive` delivered, `warning` retrying, `negative` failed,
`notice` paused), never chosen by a person. The step-up prompt is drawn on Add and
Rotate (ruling 2). Copy says what the person is doing and carries no requirement id.

**Owned paths:**
- `design/screens/admin-integrations.html` (the webhook and delivery sections)
- `docs/plans/UI_Implementation_Plan.md` (its own card and operation rows only)

**Done when:**
- The card renders in both themes, at 375 px and at 1280 px, with no horizontal
  scroll and every state drawn.
- The UI plan's `admin-integrations.html` row moves to `designed`, and its webhook
  operation rows gain the step-up correction of ruling 2 plus a row for
  `POST /webhooks/{id}/secret`.
- Every pill on the card appears in `design/system/pills-and-labels.md`'s contract;
  no new tone is invented.
- No string on the card restates an invariant or names a requirement.

**Gates:**
- No automated gate covers a static card: the task opens it at 375 px and 1280 px in
  both themes and records what it saw in its report.
- `python backend/scripts/requirements_coverage.py`; `bash scripts/prepush.sh --quick`

**Invariants:**
- Six pill tones, chosen by slot or kind. A secret is shown once and never listed.
- The design decides how things look, never what the rules are.

### c13-cards-admin-connections: the ticket and SIEM connection sections

**Requirements:** INT-02, INT-03, ADM-01
**Scenarios:** none
**Depends on:** `c13-cards-admin` (the same card file, so they never run side by side)

Add the two remaining sections to `design/screens/admin-integrations.html`: Ticket
connection (provider, project key, base url, the token shown as a prefix only, Test,
Disconnect, and the plain message for a provider kind with no adapter) and SIEM
connection (endpoint, the token as a prefix, Test, Disconnect, and the stream's lag as
a plain sentence with the last delivered event's time). Every state from
`states.html`, including the denied state for a member without `integrations.manage`
and the `secrets_unavailable` state of ruling 13. The step-up prompt is drawn on both
writes (ruling 2). Nothing the webhook half drew moves.

**Owned paths:**
- `design/screens/admin-integrations.html` (the two connection sections only)
- `docs/plans/UI_Implementation_Plan.md` (its own operation rows only)

**Done when:**
- Both sections render in both themes at 375 px and at 1280 px with every state.
- The UI plan gains rows for `PUT /integrations/tickets` and `PUT /integrations/siem`,
  each naming its permission, its step-up and its scenario.
- The token is drawn as a prefix and never as a value, and the webhook half is
  untouched.
- No string on the card restates an invariant or names a requirement.

**Gates:**
- The two-width, two-theme check, recorded in the report.
- `python backend/scripts/requirements_coverage.py`; `bash scripts/prepush.sh --quick`

**Invariants:**
- A secret is shown once and never listed; a stored one shows as a prefix.
- The design decides how things look, never what the rules are.

### c13-cards-admin-security: the admin Security card (SSO, domains, SCIM, allow-list)

**Requirements:** ID-12, ID-13, ADM-01
**Scenarios:** none
**Depends on:** nothing

Draw `design/screens/admin-security.html` for the chunk 13 half only: the identity
provider (protocol, issuer, client id, metadata url, Test connection, Active), the
verified domains list (domain, the TXT record to publish shown with a copy control,
Verify, Verified at, one tenant per domain), enforcement (off by default, the count
of members not yet linked shown **before** the switch, the admin's own round trip
required, the 409 when it has not happened), the SCIM key (created here only, shown
once, the single scope named, the default role picker with the four refused
permissions named in plain words), the member list marker "outside SSO", and the IP
allow-list (CIDR rows, add and remove, the 409 that refuses a list excluding the
admin's own address). Step-up is drawn on every write. There is no "Sign in with
your organisation" control anywhere, on this card or on `auth-sign-in.html`
(ruling 4); the card states that the passkey comes first and the provider after.
The chunk 11 half of this card (credential and session policy) is not drawn here.

**Owned paths:**
- `design/screens/admin-security.html`
- `docs/plans/UI_Implementation_Plan.md` (its own card and operation rows only)

**Done when:**
- The card renders in both themes at both widths with every state, including the
  not-yet-verified domain, the unlinked-member count and the denied state for a
  member without `security.manage`.
- New UI plan operation rows exist for the SSO, domain, SCIM and allow-list
  operations, each naming its permission, its step-up and its scenario.
- Nothing on the card offers SSO as a way to sign in, and the enrolment path is
  drawn as the provider replacing the emailed code.

**Gates:**
- The two-width, two-theme check, recorded in the report.
- `python backend/scripts/requirements_coverage.py`; `bash scripts/prepush.sh --quick`

**Invariants:**
- A passkey is the only way in; SSO proves identity only.
- A key is shown once and stored hashed or encrypted, never listed again.

### c13-cards-tenant-other: saved searches, following and Send as tickets

**Requirements:** SRC-04, COL-03, INT-02
**Scenarios:** none
**Depends on:** `c9-case-design`

Extend three existing cards in place: `tenant-search.html` gains the Saved tab (the
list with name, the filters as pills from their keys, notify on or off, Open,
Rename, Delete, the per-search "New since your last visit" marker and the cap
notice), `tenant-obligation.html` and `tenant-instrument.html` gain the Follow
control (a quiet toggle with its following state, never a count of other
followers), and `tenant-change.html`'s actions panel gains "Send as tickets" with
its confirmation, the per-action ticket reference once created, the "already sent"
state and the "no tracker connected" state that links to
`admin-integrations.html` for an admin and says who to ask for everyone else.

**Owned paths:**
- `design/screens/tenant-search.html` (the Saved tab only)
- `design/screens/tenant-obligation.html`, `design/screens/tenant-instrument.html`
  (the follow control only)
- `design/screens/tenant-change.html` (the Send as tickets panel only)
- `docs/plans/UI_Implementation_Plan.md` (its own rows only)

**Done when:**
- Each addition renders in both themes at both widths, with empty, loading, error
  and denied states, and does not move what the card already had.
- UI plan rows exist for the saved-search, follow and export-ticket operations.
- Following shows no other person's name or count anywhere.

**Gates:**
- The two-width, two-theme check, recorded in the report.
- `python backend/scripts/requirements_coverage.py`; `bash scripts/prepush.sh --quick`

**Invariants:**
- Filters and saved searches store keys; the screen renders labels from the catalog.
- Six pill tones, no string literals in the copy that reach JSX later.

### c13-cards-source-requests: requesting a source, in the bank and in the console

**Requirements:** WAT-06, INV-07, ADM-02
**Scenarios:** none
**Depends on:** nothing

Draw the two source-request surfaces. On `tenant-watch.html`: "Request a source"
with the address field and its checks stated before submission (public https page,
no credentials, not a publisher we already watch), the choice between private to us
and shared with everyone, the request list with its status, the cap, and the
"waiting for approval of the agent runner" state (open question 1) written so a
compliance officer understands what is happening. On `console-sources.html`: the
queue of **shared** requests only, with approve and decline; the card states in its
own header comment that a private request never appears here and that no platform
person can read one. A private source's rows elsewhere carry the "Private to us"
marker used for private records.

**Owned paths:**
- `design/screens/tenant-watch.html` (the request panel and list only)
- `design/screens/console-sources.html` (the shared-request queue only)
- `docs/plans/UI_Implementation_Plan.md` (its own rows only)

**Done when:**
- Both surfaces render in both themes at both widths with every state.
- The console card shows no private request anywhere and says so in its comment.
- UI plan rows exist for the source-request operations, tenant and console.

**Gates:**
- The two-width, two-theme check, recorded in the report.
- `python backend/scripts/requirements_coverage.py`; `bash scripts/prepush.sh --quick`

**Invariants:**
- Private records never reach a platform surface.
- Copy says what the user is doing and names no requirement.

### c13-cards-tenant-private: proposing and approving the bank's own records

**Requirements:** INV-07, PRO-03
**Scenarios:** none
**Depends on:** nothing

Draw `design/screens/tenant-private-records.html`, the bank's own half of the
proposal door, which no card covers today. The list of the bank's private proposals
with their state; "Propose a private instrument" and "Propose a private obligation"
with the fields the apply path needs and the plain note that a private instrument
holds no provisions in R3 (D-57); the reviewer's view with Approve and Reject, the
step-up prompt drawn on Approve, the refusal a proposer sees when they approve their
own (four eyes), and the reject-reason picker from the existing list. The card also
defines the "Private to us" marker that the inventory, the obligation page, the feed
and the source-request surfaces reuse in place. Every state from `states.html`,
including empty and the denied state for a member without `private_records.approve`.
Nothing on the card suggests that a platform person reviews these.

**Owned paths:**
- `design/screens/tenant-private-records.html`
- `design/system/pills-and-labels.md` (the "Private to us" marker's own row)
- `docs/plans/UI_Implementation_Plan.md` (its own card and operation rows only)

**Done when:**
- The card renders in both themes, at 375 px and at 1280 px, with no horizontal
  scroll and every state drawn.
- UI plan rows exist for the private-proposal list, approve and reject operations,
  each naming `private_records.approve` and its step-up.
- The marker has one row in `pills-and-labels.md` with its tone, and no new tone is
  invented.
- No string on the card restates an invariant or names a requirement, and nothing on
  it offers a platform reviewer.

**Gates:**
- The two-width, two-theme check, recorded in the report.
- `python backend/scripts/requirements_coverage.py`; `bash scripts/prepush.sh --quick`

**Invariants:**
- Four eyes, with a passkey step-up, drawn wherever the server demands it.
- A tenant's private records never reach a platform surface.

### c13-cards-tenant-register: attestation and waiver panels

**Requirements:** REG-06
**Scenarios:** none
**Depends on:** `c8-card-obligation-register`, `c13-cards-tenant-other` (both draw on
`tenant-obligation.html`, so they never run side by side)

Extend `tenant-obligation.html` with the two REG-06 panels: Attestation (when it was
last attested and by whom, the status attested to, the due date, the "due for
attestation" state, the Attest control the owner alone sees, and the statement
field) and Waivers (the waiver on a gap with its description, who granted it, from
and to dates, the step-up on granting, the expiring-soon state and the lapsed state
that says the gap is open again). Both panels state plainly that a waiver does not
make a gap disappear.

**Owned paths:**
- `design/screens/tenant-obligation.html` (the two panels only)
- `docs/plans/UI_Implementation_Plan.md` (its own rows only)

**Done when:**
- Both panels render in both themes at both widths with every state, including the
  non-owner view where Attest is absent rather than disabled.
- The UI plan's two REG-06 rows move to `designed` and carry the step-up on waivers.

**Gates:**
- The two-width, two-theme check, recorded in the report.
- `python backend/scripts/requirements_coverage.py`; `bash scripts/prepush.sh --quick`

**Invariants:**
- "Applies" and "we comply" stay separate facts; a waiver never hides a gap.
- Pills by kind only.

### c13-egress-client: one guarded way out of the process

**Requirements:** INT-01, INT-02, INT-03, ID-12, WAT-06, NFR-02
**Scenarios:** none (every consumer's scenario rests on it)
**Depends on:** `r1-readiness`
**Security review:** yes (outbound calls, SSRF)

Build `backend/apps/shared/egress.py`: one `fetch()` and one `post()` that every
outbound call a tenant configures goes through. Standard library only, like
`adapters/llm.py` (no dependency change). The rules, each its own test: https only
(`http` refused, any other scheme refused); no user info in the URL; the host
resolved once and the socket connected to that resolved address, so a second
resolution cannot swap it; every resolved address checked against private,
loopback, link-local, multicast, reserved and cloud-metadata ranges, in IPv4 and
IPv6, before the connection and again after each redirect; at most
`EGRESS_MAX_REDIRECTS` redirects and never to another scheme or to a refused
address; a total deadline `EGRESS_TIMEOUT_SECONDS`; a response cap
`EGRESS_MAX_RESPONSE_BYTES` enforced while reading, not after; the process proxy
variables ignored; a fixed user agent; and an `EgressRefused` error carrying a
reason key, never a host or a URL, so a caller can answer 422 without leaking
what it resolved. Fetched bodies are returned as bytes with their content type and
are never executed, rendered or logged (playbook 11.2).

**Owned paths:**
- `backend/apps/shared/egress.py`
- `backend/apps/shared/tests_egress.py`
- `backend/config/settings.py` (one settings banner), `backend/.env.example`,
  `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**
- Every rule above has a test, including a redirect to `169.254.169.254`, a redirect
  from https to http, a DNS answer that changes between calls, a body larger than the
  cap and a host that resolves to a private address only.
- No log line, error message or exception text produced by the module contains a URL,
  a host or a response body.
- `apps.shared` coverage `--include='apps/shared/egress.py'` ≥ 95.
- No dependency file changes.

**Gates:**
- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/egress.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**
- Fetched content is untrusted: never executed, never rendered as HTML, never logged.
- No threshold is hard-coded; each is a setting with an env override.
- No bare `except Exception:`; errors carry a code, never a trace.

### c13-secret-box: integration secrets encrypted at rest

**Requirements:** INT-01, INT-02, INT-03, ID-12
**Scenarios:** none
**Depends on:** `c13-egress-client`, `r1-readiness`
**Security review:** yes (secret handling, one dependency pin)

Build `backend/apps/shared/secret_box.py`: `seal(plaintext) -> (ciphertext, key_id)`
and `open(ciphertext, key_id) -> plaintext` over `INTEGRATION_SECRET_KEYS`, a list of
`<key_id>:<urlsafe base64 key>` entries where the first encrypts and every entry can
decrypt, so a rotation needs no downtime. `cryptography`'s `MultiFernet` does the
work; the pin is added explicitly to `backend/pyproject.toml` at the version already
resolved through `webauthn` (50.0.1), so `poetry.lock` does not move. With no key
configured, `seal()` raises `SecretsUnavailable`, which every caller turns into 422
`secrets_unavailable`; the boot guard is not touched (ruling 13). Add
`backend/apps/shared/tests_no_secret_in_logs.py`, the shared proof each later task
extends: for every secret kind, the plaintext appears in no log record, no audit
`after` value, no outbox payload, no Sentry event after the scrubbers and no API
response other than the one creation response.

**Owned paths:**
- `backend/apps/shared/secret_box.py`, `backend/apps/shared/tests_secret_box.py`
- `backend/apps/shared/tests_no_secret_in_logs.py`
- `backend/pyproject.toml` (one pin), `backend/config/settings.py` (one banner),
  `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`,
  `docs/plans/Verification_Log.md`

**Done when:**
- Round-trip, rotation (a ciphertext sealed under the old key still opens), an
  unknown key id (refused with a code), a tampered ciphertext (refused) and the
  no-key path each have a test.
- `poetry.lock` is unchanged and `poetry check --lock` passes.
- The no-secret-in-logs proof is green for the one kind that exists today (the box's
  own test double) and is written so a later task adds a kind in three lines.
- `--include='apps/shared/secret_box.py'` ≥ 95.

**Gates:**
- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh install && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/secret_box.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `bash scripts/prepush.sh --quick` (it runs osv-scanner and the licence check over
  the changed dependency file)

**Invariants:**
- A secret is shown once, never logged, never in an audit or outbox row.
- Dev-only defaults are prefixed and allowlisted by exact literal; `.env.example`
  carries no real value.
- The production boot guard is not this task's to change.

### c13-int-contract: the integrations contract, models and the one event envelope

**Requirements:** INT-01, INT-02, INT-03
**Scenarios:** INT-S6 (added and un-skipped)
**Depends on:** `c13-secret-box`, `c13-egress-client`, `c5-outbox-cursor`
**Security review:** yes (new tenant tables, a stored credential, an outbound contract)

Write `integrations/models.py` with its migration and `api.py` and `schemas.py`
once. Models, all `TenantModel` under enabled and forced row-level security:
`WebhookEndpoint` (url, event keys as an array of keys, active, `secret_ciphertext`,
`secret_key_id`, `secret_prefix`, created by, `paused_reason` kind),
`WebhookDelivery` (endpoint, outbox event, status kind, attempts, response code,
duration ms, last attempt at), `SiemConnection` (one per tenant: endpoint,
`token_ciphertext`, `token_key_id`, active, last delivered event, last delivered at)
and `TicketIntegration` (one per tenant: provider kind, project key, base url,
`token_ciphertext`, `token_key_id`, active). Routes, each behind its real gate,
answering 501 `not_built` from the module that will serve it: `listWebhooks`,
`createWebhook`, `updateWebhook`, `deleteWebhook`, `rotateWebhookSecret`,
`listWebhookDeliveries`, `redeliverWebhookDelivery`, `getTicketIntegration`,
`setTicketIntegration`, `getSiemConnection`, `setSiemConnection`,
`getStreamStatus`, `listEventTypes`, `receiveTicketCallback`. Every one is
`integrations.manage` except the callback, which declares the provider signature as
its credential, and `listEventTypes`, which any member may read. `createWebhook`,
`rotateWebhookSecret`, `setTicketIntegration` and `setSiemConnection` carry
`@requires_step_up` (ruling 2). `listEventTypes` is served here, not stubbed: it
returns the audit action keys a subscription may filter on, read from the one place
they are already declared, so no new managed list exists. `IntegrationEvent` is the
one envelope of ruling 1, with the guard test that no other key and no free text can
appear in it. The task also adds INT-S6 to `integrations/app.md` and its stub — the
envelope carries ids, kinds and times only, and a library or platform row never
reaches a tenant endpoint — and un-skips it, since the guard proves both.

**Owned paths:**
- `backend/apps/integrations/models.py`, `migrations/`, `api.py`, `schemas.py`,
  `event_types.py`, `tests_contract.py`, `tests_envelope.py`,
  `backend/apps/integrations/app.md` (the INT-S6 heading) and `tests_scenarios.py`
  (the INT-S6 method)
- `backend/config/api.py` (the router mount), `backend/apps/shared/permissions.py`
  (the route lists), `apps/shared/kinds.py`, `tests_rls.py` and `factories.py` (own
  entries), `docs/inputs/INPUT_DELTAS.md`

**Done when:**
- The fourteen operations are in `openapi.json` with those ids; thirteen answer 501
  behind the real gate and `listEventTypes` answers its list, each giving 401 then 403
  before anything else, proved per route.
- INT-S6 is green: the envelope's key set is fixed, and a platform audit row produces
  no tenant delivery.
- `migrate_from_zero` applies the graph; `tests_rls` lists all four tables with
  forced RLS, and tenant B cannot read or write tenant A's rows as `cw_app`.
- The envelope guard fails on an added `title` key and on a value that is not an id,
  key, boolean or timestamp.
- INPUT_DELTAS rows exist for ruling 1, ruling 3 and the operations `openapi.yaml`
  does not declare (`/integrations/siem`, the secret rotation, the callback, the
  event-type read, the stream status).

**Gates:**
- `set -a; . ./.env.worktree; set +a`; `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.integrations apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/integrations/*'` (≥ 90)
- `./run.sh run ruff check . && ./run.sh run mypy`; `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh` as a check only, then revert; `bash scripts/prepush.sh --quick`

**Invariants:**
- No logic in `api.py`; no `Dict[str, Any]`; `JSONField` only with a named schema.
- Every route has a permission or a declared credential; `UNGATED_BY_DESIGN` is not touched.
- Tenant content never reaches an integration payload.

### c13-int-subscriptions: subscriptions, secrets shown once, stored keys

**Requirements:** INT-01
**Scenarios:** INT-S5 (un-skipped)
**Depends on:** `c13-int-contract`
**Security review:** yes (a credential is minted)

Serve the subscription half from `integrations/subscriptions.py`: create (url
validated through the egress client's rules without calling out, event keys checked
against `listEventTypes`, a 32-byte secret sealed by the box and returned once with
its prefix), update (pause, resume, change the event keys), rotate the secret (the
old one keeps signing for `WEBHOOK_SECRET_OVERLAP_SECONDS` so a receiver can roll),
delete, and the delivery list. Every write goes through `record()`; the secret never
appears in the audit `after` value, and `tests_no_secret_in_logs.py` gains the
webhook kind. INT-S5: a subscription stores the change-type **key**, and renaming
the label in the vocabulary changes neither the stored filter nor what matches.

**Owned paths:**
- `backend/apps/integrations/subscriptions.py`, `tests_subscriptions.py`,
  `tests_scenarios.py` (the INT-S5 skip line only)
- `backend/apps/shared/tests_no_secret_in_logs.py` (its own kind),
  `backend/config/settings.py` (one banner), `.env.example`, `RAILWAY_VARIABLES.md`

**Done when:**
- INT-S5 is green: rename the label, the stored filter and the match are unchanged.
- The plaintext secret appears in exactly one response body and nowhere else, proved
  by the shared test.
- A url that is http, carries credentials, or resolves only to a private address is
  refused 422 with a code and no host in the message; a member without
  `integrations.manage` gets 403; a create without a fresh assertion gets the
  step-up 401.
- `--include='apps/integrations/subscriptions.py'` ≥ 95.

**Gates:** as `c13-int-contract`, plus `bash scripts/prepush.sh --quick`.

**Invariants:**
- Filters store keys, never labels; a rename changes nothing.
- A secret is shown once; `record()` on every write.

### c13-webhook-delivery: delivery from the outbox, signed and logged

**Requirements:** INT-01
**Scenarios:** INT-S1 (un-skipped), INT-S2 (un-skipped, green up to the inbound line)
**Depends on:** `c13-int-subscriptions`, `c5-outbox-cursor`, `c9-signoff`, `c5-watch-registration`
**Security review:** yes (outbound delivery of tenant events)

Build `integrations/tasks.py`'s delivery half as a consumer of the one cursor
(ruling 12): for each published outbox row, under `@tenant_task`, match the tenant's
active endpoints on the topic key, write one `WebhookDelivery` per match, and send
the ruling 1 envelope through the egress client with the HMAC signature, the
timestamp and the event id. Order is kept per subject and per endpoint; a delivery
is attempted only after the writing transaction commits; the same outbox row is
never delivered twice as a new event, and a worker restart mid-batch re-attempts the
same delivery row with the same event id. A library or platform audit row
(`tenant_id` NULL) matches nothing, and `problem_report.*` topics never match (D-50).
Retries themselves are `c13-webhook-retries`; here a failure is recorded with its
response code and left `retrying`.

**Owned paths:**
- `backend/apps/integrations/tasks.py`, `backend/apps/integrations/delivery.py`,
  `tests_delivery.py`, `tests_scenarios.py` (INT-S1 and INT-S2 skip lines)
- `backend/apps/shared/e2e_seed.py` (one seed call: an endpoint for tenant A)

**Done when:**
- INT-S1 is green, including the delivery log's attempt, status and response time.
- INT-S2 is green up to its inbound line, named in the test's docstring as extended
  by `c13-tickets-inbound`.
- A signature test verifies the exact string signed; a test proves no title, summary
  or before/after value is in the body.
- Tests prove: no delivery before commit, none for a `tenant_id IS NULL` row, none
  for `problem_report.*`, and order per subject.
- `--include='apps/integrations/delivery.py'` ≥ 95.

**Gates:** as `c13-int-contract`, plus `bash scripts/prepush.sh --quick`.

**Invariants:**
- One relay only: this task adds a handler to the cursor, never a second cursor.
- `@tenant_task` in the worker; ids, kinds and times only in the body.

### c13-webhook-retries: backoff, auto-pause and redelivery

**Requirements:** INT-01
**Scenarios:** INT-S1 stays green (its retry lines are this task's to keep green)
**Depends on:** `c13-webhook-delivery`

Add the failure path: exponential backoff with jitter from `WEBHOOK_BACKOFF_SECONDS`
up to `WEBHOOK_MAX_ATTEMPTS`, then `failed` and kept in the log;
`WEBHOOK_AUTO_PAUSE_FAILURES` consecutive failures across deliveries pause the
endpoint with a reason kind and notify the `integrations.manage` holders through
chunk 10's notification writer; and `redeliverWebhookDelivery`, which sends the same
event id again and writes a new attempt row rather than a new event. Every threshold
is a setting with an env override, and the tests use fixtures and a frozen clock.

**Owned paths:**
- `backend/apps/integrations/retries.py`, `tests_retries.py`
- `backend/apps/integrations/tasks.py` (the retry entry point only, after
  `c13-webhook-delivery` merged), `backend/config/settings.py` (banners),
  `.env.example`, `RAILWAY_VARIABLES.md`

**Done when:**
- Backoff, the cap, the pause, the notification and the redelivery each have a test
  on a frozen clock.
- A redelivery reuses the event id, so a receiver dedupes it.
- A paused endpoint matches nothing until it is resumed.
- `--include='apps/integrations/retries.py'` ≥ 95.

**Gates:** as `c13-int-contract`, plus `bash scripts/prepush.sh --quick`.

**Invariants:**
- Thresholds are settings; tests freeze the clock and never sleep.
- A notification obeys D-34's one recipient check.

### c13-siem-stream: the audit stream and its lag

**Requirements:** INT-03
**Scenarios:** INT-S4 (un-skipped)
**Depends on:** `c13-webhook-delivery`
**Security review:** yes (a second outbound path for audit rows)

Serve the SIEM half: `setSiemConnection` (endpoint validated as for a webhook, token
sealed, step-up, `record()`), `getSiemConnection`, `getStreamStatus` (the tenant's
own lag: `now` minus the oldest undelivered event's `created`, plus the last
delivered event id and time), and a `@tenant_task` that every
`SIEM_INTERVAL_SECONDS` sends the next `SIEM_BATCH_MAX` events in order as
newline-delimited ruling 1 envelopes with a bearer token, advancing the connection's
cursor only on a 2xx. The lag lives on the connection row as the last delivered event
and its time; the console's per-bank view of it is chunk 14's audited window (D-59,
`c14-health-backend`), and nothing here reads another tenant's figures or builds that
window.

**Owned paths:**
- `backend/apps/integrations/siem.py`, `tests_siem.py`, `tests_scenarios.py`
  (the INT-S4 skip line), `backend/apps/integrations/app.md` (INT-S4's Gherkin and
  its status cell only, which this task rewords under ruling 1)
- `backend/apps/integrations/tasks.py` (its own beat entry), settings banners,
  `.env.example`, `RAILWAY_VARIABLES.md`,
  `backend/apps/shared/tests_no_secret_in_logs.py` (its own kind)

**Done when:**
- INT-S4 is green with the reworded line: events stream in order, in the documented
  envelope, and the tenant's lag is readable.
- A test proves the stream carries no title, summary or evidence content, no library
  or platform row and no `problem_report.*` topic.
- A 500 from the endpoint does not advance the cursor and does not lose an event.
- `integrations/app.md`'s INT-S4 Gherkin is reworded per ruling 1 with the
  INPUT_DELTAS row already written by `c13-int-contract` cited.
- `--include='apps/integrations/siem.py'` ≥ 95.

**Gates:** as `c13-int-contract`, plus `bash scripts/prepush.sh --quick`.

**Invariants:**
- Tenant content never leaves the tenant zone as text.
- Append-only rows are read, never rewritten, by the stream.

### c13-library-change-fanout: one library change, one event per interested bank

**Requirements:** INT-01, COL-03, SRC-04
**Scenarios:** none (it feeds `c13-follow-notify` and `c13-saved-search-notify`)
**Depends on:** `c13-int-contract`, `c4-approve-apply`, `c10-collab-models`

A library change (a new obligation version, a new instrument, a change registered
against a followed record) is one platform outbox row with no tenant. Add a handler
on the one cursor that, for each such row, finds the tenants that can see the record
(the footprint and scope rules the library reads already apply) and writes one
tenant-zone fanout event per tenant through `record()` with a `library.changed`
topic, carrying ids and kinds only. Webhook delivery, follow notifications and saved
searches all consume the fanout, so none of them re-queries the library. A private
record's change fans out to its owner only.

**Owned paths:**
- `backend/apps/collab/fanout.py`, `backend/apps/collab/tests_fanout.py`
- `backend/apps/collab/tasks.py` (its own handler registration)

**Done when:**
- One library change writes exactly one fanout event per entitled tenant, and none
  for a tenant that cannot see the record; a test pins the query count so the fanout
  does not grow with the library.
- A private record's change reaches its owner only.
- A replayed platform row writes no duplicate fanout event (idempotent on the source
  event id).
- `--include='apps/collab/fanout.py'` ≥ 95.

**Gates:**
- `set -a; . ./.env.worktree; set +a`; `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`; `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**
- One cursor, one relay; `@tenant_task` for the per-tenant write.
- A tenant never learns of a record it may not see.

### c13-tickets-export: the ticket table, the provider seam and the job

**Requirements:** INT-02
**Scenarios:** INT-S3 stays skipped until `c13-tickets-export-api`
**Depends on:** `c13-int-subscriptions`, `c9-actions`

Add `ActionTicket` (tenant, action, provider kind, ticket key, ticket url, status
kind, created by, created at, `UNIQUE (tenant, action)`) with its migration, and
`integrations/tickets.py`: a `TicketProvider` seam with `create_issue()` and
`read_issue()`, a mock provider for tests and E2E, and a `@tenant_task` that creates
one ticket per action, idempotent on the action id, writing the reference back on the
action through `record()`. A second export of the same action creates nothing and
returns the existing references. No provider adapter is built here (ruling: `jira`
is `c13-tickets-jira`); an unconfigured or unsupported provider raises the error the
route turns into 422.

**Owned paths:**
- `backend/apps/integrations/models.py` (the one model, after `c13-int-contract`),
  `migrations/`, `backend/apps/integrations/tickets.py`, `tests_tickets.py`
- `apps/shared/kinds.py`, `tests_rls.py`, `factories.py` (own entries)

**Done when:**
- `migrate_from_zero` applies; `ActionTicket` is under forced RLS and listed in
  `tests_rls`; tenant B sees none of A's tickets.
- Exporting twice creates one ticket, proved with a concurrency test (two workers,
  one row).
- The mock provider records what it was asked to create; nothing tenant-written
  beyond the action's own title and reference leaves (the seam's payload is fixed and
  tested).
- `--include='apps/integrations/tickets.py'` ≥ 95.

**Gates:** as `c13-int-contract`, plus `bash scripts/prepush.sh --quick`.

**Invariants:**
- Idempotency on every outward write; `record()` on the action's update.
- Kinds in code, provider names as kinds, never phrases.

### c13-tickets-export-api: "Send as tickets" as a route

**Requirements:** INT-02
**Scenarios:** INT-S3 (un-skipped, green up to the flow-back line)
**Depends on:** `c13-tickets-export`

Declare `exportActionsAsTickets` at the designed path
`POST /changes/{changeId}/actions/export-tickets` in `cases/api.py` (ruling 9) under
`cases.work`, with an `Idempotency-Key` header, serving from
`integrations/tickets.py`. It answers the created references, 422
`tracker_not_configured` when the tenant has no connection, 422
`provider_not_available` for a provider with no adapter, and 409 nothing-to-do when
every action already has a ticket. `GET /changes/{changeId}/actions` gains the
ticket reference per action so the panel can render it.

**Owned paths:**
- `backend/apps/cases/api.py`, `backend/apps/cases/schemas.py` (the one operation and
  the ticket fields only), `backend/apps/integrations/tests_scenarios.py` (the INT-S3
  skip line), `docs/inputs/INPUT_DELTAS.md`

**Done when:**
- INT-S3 is green up to "a ticket closes at the provider", named in the docstring as
  extended by `c13-tickets-inbound`.
- The four answers above each have a test, and a member without `cases.work` gets 403.
- Re-posting with the same idempotency key returns the first answer and creates nothing.

**Gates:** as `c13-int-contract`, with `apps.cases` added to the test target.

**Invariants:**
- No logic in `api.py`; the contract task owns the route, the logic module the work.
- Idempotency on every write that reaches outside.

### c13-tickets-inbound: a closed ticket moves its action

**Requirements:** INT-02, INT-01
**Scenarios:** INT-S2 (extended, inbound line), INT-S3 (extended, flow-back line)
**Depends on:** `c13-tickets-export-api`, `c13-ip-allowlist-enforcement`
**Security review:** yes (an unauthenticated-by-session route, and the allow-list's one exclusion)

Serve `receiveTicketCallback`: the provider signs its callback with the shared secret
kept in the box; the handler verifies the signature in constant time, refuses an
unknown or stale one with 401 and a security-log row, looks up the `ActionTicket` by
provider and ticket key inside that tenant, and moves the action's status once.
Applying the same callback twice changes nothing (idempotent on the provider's
delivery id, stored). The route is rate limited through
`apps.identity.rate_limit.enforce`, reads no body field it does not need, and can do
nothing but move that one action. This task also adds the route's name to the IP
allow-list exclusion set `c13-ip-allowlist-enforcement` left empty — the one
exclusion, because the tracker's addresses are not the bank's — and owns the test
that proves it is the only entry (finding 3). Adding it is a guard change, so it
happens here, where the route is declared, under this task's security review, and the
task stops on an invariant question.

**Owned paths:**
- `backend/apps/integrations/inbound.py`, `tests_inbound.py`,
  `backend/apps/integrations/models.py` (the delivery-id column only), `migrations/`
- `backend/apps/shared/middleware.py` (the one exclusion entry) and
  `backend/apps/shared/tests_middleware.py` (its own test only)
- `backend/apps/integrations/tests_scenarios.py` (the INT-S2 and INT-S3 extensions)

**Done when:**
- INT-S2's inbound line and INT-S3's flow-back line are green.
- A wrong signature, a replayed delivery id, an unknown ticket key and a ticket key
  belonging to another tenant each have a test, and none of them changes a row.
- The route appears in the permissions route list with its declared credential, and a
  test proves it is the only name in the allow-list exclusion set and that a request
  to any other route from a refused address is still refused.
- It appears in no allowlist that loosens a guard.
- `--include='apps/integrations/inbound.py'` ≥ 95.

**Gates:** as `c13-int-contract`, plus `bash scripts/prepush.sh --quick`.

**Invariants:**
- Input from outside is validated at the boundary; a signature is compared in
  constant time.
- Idempotency on every inbound handler (playbook 4.3).

### c13-tickets-jira: the one provider adapter

**Requirements:** INT-02
**Scenarios:** INT-S3 stays green
**Depends on:** `c13-tickets-inbound`

Implement `JiraProvider` behind the seam, using the egress client: create an issue in
the configured project, read one back, and map its resolution to the action status
kinds. The E2E tracker double is a small in-backend endpoint served only under
`E2E_MODE` (rule 15) with its production-refusal test, so `npm run test:e2e` exercises
the real adapter against a real HTTP endpoint without mocking a response. The
manual check against a Jira Cloud sandbox is an operator step recorded in
`Verification_Log.md` and listed for Alex by `c13-close` (section 7.3 of the parallel
plan: sandboxes).

**Owned paths:**
- `backend/apps/integrations/providers/jira.py`, `tests_jira.py`,
  `backend/apps/integrations/providers/e2e_tracker.py` (the double and its guard test)
- `docs/plans/Verification_Log.md` (the Jira API rows, fetched not recalled)

**Done when:**
- Create, read, the field mapping, an error answer and a timeout each have a test
  against the double.
- The double refuses to load when `E2E_MODE` is off, proved by a test, exactly as the
  mail outbox does.
- Every Jira API claim in the code has a `Verification_Log.md` row with the URL it was
  read from.
- `--include='apps/integrations/providers/*'` ≥ 90.

**Gates:** as `c13-int-contract`, plus `bash scripts/prepush.sh --quick`.

**Invariants:**
- Provider documentation is fetched, never recalled, and logged.
- No API is mocked in E2E; the double is a real endpoint inside the stack.

### c13-ip-allowlist: an optional allow-list per bank, stored and validated

**Requirements:** ID-13, ADM-01
**Scenarios:** none (ID-S24 needs the guard, and is `c13-ip-allowlist-enforcement`'s)
**Depends on:** `c11-security-policy`, `r1-readiness`
**Security review:** yes (a security-policy write with a step-up)

Add `ip_allowlist` (a list of CIDR rows) and `ip_allowlist_enabled` to the
`security_policy` row chunk 11 built, with the routes on `tenants/api.py` (key `ten`)
under `security.manage` and a step-up (ruling 2). Parsing and validation live in
`security_policy_logic.py`: IPv4 and IPv6 rows both work, a malformed row is refused
by code, `IP_ALLOWLIST_MAX_ENTRIES` (50) caps the list, an empty list means "no
restriction", and a list that would exclude the address the acting admin is calling
from answers 409 `would_lock_you_out` (D-55's self-lockout rule), using the same
client-address helper the guard half will use. Nothing enforces the list yet; that is
`c13-ip-allowlist-enforcement`'s, which this half leaves green behind it.

**Owned paths:**
- `backend/apps/tenants/models.py` (the two fields), `migrations/`,
  `backend/apps/tenants/api.py`, `schemas.py`, `security_policy_logic.py`,
  `backend/apps/tenants/tests_ip_allowlist.py`
- settings banner, `.env.example`, `RAILWAY_VARIABLES.md`,
  `docs/inputs/INPUT_DELTAS.md`

**Done when:**
- Saving, reading and clearing the list work under `security.manage` with a step-up,
  each with a `record()` row, and a member without the permission gets 403.
- Tests cover both address families, a malformed row, the cap, the empty list and the
  self-lockout 409, including the proxied case where the admin's address comes from
  the trusted hop.
- `--include='apps/tenants/security_policy_logic.py'` ≥ 95.

**Gates:** as `c13-int-contract`, with `apps.tenants apps.shared` as the test target,
plus the guard suites `tests_route_permissions` and `tests_rls`.

**Invariants:**
- Every threshold is a setting; input from a person is validated at the boundary.
- The client address is never taken from an untrusted header.

### c13-ip-allowlist-enforcement: the allow-list is enforced after authentication

**Requirements:** ID-13
**Scenarios:** ID-S24 (un-skipped)
**Depends on:** `c13-ip-allowlist`
**Security review:** yes (a guard in `middleware.py`; stops on an invariant question)

Enforce the list in `apps/shared/middleware.py` after authentication, so the security
log can name the member: a request from outside the list answers 403 `ip_not_allowed`,
writes a `login_event` row and reveals nothing about the list. The client address
comes from the existing `TRUSTED_PROXY_HOPS` handling and from nowhere else. The list
binds sessions and tenant-bound API keys alike. The guard reads one exclusion set,
which this task creates **empty** and documents; the one entry is added by
`c13-tickets-inbound`, the task that declares `receiveTicketCallback`, together with
its test (finding 3). No wildcard and no pattern is accepted in that set.

**Owned paths:**
- `backend/apps/shared/middleware.py`, `backend/apps/shared/tests_middleware.py`
- `backend/apps/identity/app.md` (ID-S24's two added lines) and `tests_scenarios.py`
  (the ID-S24 skip line)

**Done when:**
- ID-S24, reworded in `identity/app.md` with two lines it did not carry (a tenant API
  key from a refused address is refused too, and a list that would exclude the acting
  admin answers 409), is green in all of them.
- Tests cover: an allowed and a refused address in both families, a proxied request
  with the configured hop count, a spoofed `X-Forwarded-For` beyond the hops, an empty
  list meaning "no restriction", and a refused request writing a `login_event` row
  whose response names no CIDR.
- A tenant API key from a refused address is refused the same way.
- The exclusion set is empty here, and a test pins that it holds only exact route
  names.
- `--include='apps/shared/middleware.py'` ≥ 95.

**Gates:** as `c13-int-contract`, with `apps.tenants apps.identity apps.shared` as the
test target, plus the guard suites `tests_route_permissions` and `tests_rls`.

**Invariants:**
- A guard changes only in the package named for it, after a security review.
- The client address is never taken from an untrusted header.

### c13-sso-domains: verified email domains

**Requirements:** ID-12
**Scenarios:** none (ID-S23 and ID-S27 need the provider)
**Depends on:** `r1-readiness`
**Security review:** yes (identity, one dependency pin)

Add `TenantDomain` (tenant, domain as citext unique across every tenant,
verification token, verified at) with its migration — without `auto_join`,
`default_roles` or any role column (ruling 5) — and the routes on `identity/api.py`
under `security.manage` with a step-up: list, add (which returns the TXT record to
publish), verify (which resolves `_bleqq-verification.<domain>` and compares the
token in constant time) and remove. `dnspython` is pinned for the TXT lookup, with a
resolver timeout from a setting and the answer treated as untrusted input. A domain
already verified for another tenant answers 409, and removing a domain that
enforcement depends on answers 409 with the reason. Each action writes `record()`.

**Owned paths:**
- `backend/apps/identity/models.py` (one model), `migrations/`,
  `backend/apps/identity/api.py`, `schemas.py`, `domains_logic.py`,
  `tests_domains.py`
- `backend/pyproject.toml`, `poetry.lock` (one dependency), settings banner,
  `.env.example`, `RAILWAY_VARIABLES.md`, `docs/inputs/INPUT_DELTAS.md`,
  `docs/plans/Verification_Log.md`

**Done when:**
- `migrate_from_zero` applies and the table is under forced RLS and in `tests_rls`.
- Add, verify, a wrong token, a missing record, a resolver timeout, a duplicate
  domain across tenants and the removal 409 each have a test with a stubbed resolver.
- The new dependency passes `osv-scanner`, the licence check and `npm`-free Trivy on
  both images through `prepush.sh --all` run once by the main agent at merge.
- `--include='apps/identity/domains_logic.py'` ≥ 95.

**Gates:** as `c13-int-contract`, with `apps.identity apps.shared` as the target and
`./run.sh install` first; `bash scripts/prepush.sh --quick`.

**Invariants:**
- A DNS answer is untrusted input, validated at the boundary.
- No password, no self-service path; every write audited with the step-up id.

### c13-sso-idp-contract: the provider record and its routes

**Requirements:** ID-12
**Scenarios:** none
**Depends on:** `c13-sso-domains`, `c13-secret-box`, `c13-egress-client`

Add `IdentityProvider` (tenant, protocol kind, name, issuer, client id, metadata
url, `client_secret_ciphertext`, `client_secret_key_id`, enforce_sso, active,
created by) with its migration, without `scim_token_hash` (ruling 5), and declare
every remaining SSO operation on `identity/api.py`, answering 501 from the module
that will serve it: `getIdentityProvider`, `setIdentityProvider`,
`testIdentityProvider`, `setSsoEnforcement`, `listSsoLinks`, `createScimKey`,
`setScimDefaultRole`, `beginIdpChallenge`, `completeIdpChallenge` (POST only),
`disableIdpEnforcementForTenant` (the platform's safe-direction switch-off of owner
item 11, under `support_access.grant` with a step-up) and the enrolment variants. All
are `security.manage` with a step-up except that one platform operation and the two
challenge operations, which belong to a half-authenticated flow and declare that
(the passkey has already passed; the challenge is single-use and bound to the
browser). No operation starts a sign-in at the provider (ruling 4), and no operation
lets a platform session switch enforcement **on**. INPUT_DELTAS gets the row naming
the new operation ids.

**Owned paths:**
- `backend/apps/identity/models.py` (one model), `migrations/`,
  `backend/apps/identity/api.py`, `schemas.py`, `tests_contract_sso.py`
- `apps/shared/permissions.py` (route lists), `tests_rls.py`, `factories.py`,
  `docs/inputs/INPUT_DELTAS.md`

**Done when:**
- Every operation is in `openapi.json`, answers 501 behind its gate, and gives 401
  then 403 first.
- There is no operation that begins an authorisation request for an anonymous
  visitor, proved by a test over the route list.
- Exactly one SSO operation accepts a platform session, it carries
  `support_access.grant` and a step-up, and it can only switch enforcement off.
- The client secret column is ciphertext, never a hash, and never returned.
- `migrate_from_zero` applies; the table is in `tests_rls` under forced RLS.

**Gates:** as `c13-int-contract`, with `apps.identity apps.shared` as the target.

**Invariants:**
- SSO proves identity only; the passkey stays the only way in.
- Contracts land first; a logic task never edits `api.py`.

### c13-sso-oidc: the OIDC client and enrolment without an emailed code

**Requirements:** ID-12
**Scenarios:** ID-S23 (un-skipped)
**Depends on:** `c13-sso-idp-contract`, `r1-readiness`
**Security review:** yes (authentication)

Build `identity/idp_oidc.py`: discovery from the metadata url through the egress
client, JWKS cached for `OIDC_JWKS_TTL_SECONDS` and refetched on an unknown key id,
an authorisation request with PKCE, a single-use `state` and `nonce`, and
`response_mode=form_post`; verification of the id token's signature (RS256 through
`cryptography`, no new dependency), issuer, audience, `nonce`, `exp` and `iat` with
`OIDC_CLOCK_SKEW_SECONDS`. Then the enrolment half: for an address on a verified
domain, opening an invitation asks the provider instead of sending a code; a code
request for such an address sends nothing and answers exactly as every other code
request does. The link stored is issuer plus subject (for Entra, issuer plus `oid`),
never the email claim, and a link is made only where the invitation or re-enrolment
token and the provider proof arrive together. Every link emails the member and
notifies the other admins. The security log gains `idp_verified` and `idp_failed`.

**Re-enrolment keeps its four eyes.** CLAUDE.md §5 lists re-enrolment among the
actions that need four eyes and a passkey step-up, and this task edits
`invitation_logic.py` and `code_logic.py`'s re-enrolment branch. The provider proof
replaces the emailed code and nothing else: the second approver, the check
constraint and the approver's fresh assertion all still stand, on a verified domain
exactly as off one. A provider round trip is never accepted in place of either.

**Owned paths:**
- `backend/apps/identity/idp_oidc.py`, `tests_idp_oidc.py`,
  `backend/apps/identity/invitation_logic.py` and `code_logic.py` (the verified-domain
  branch only), `security_log.py` (two kinds), settings banners, `.env.example`,
  `RAILWAY_VARIABLES.md`, `identity/tests_scenarios.py` (the ID-S23 skip line),
  `docs/plans/Verification_Log.md`

**Done when:**
- ID-S23 is green: the provider replaces the emailed code, no password is stored,
  SCIM's invited state needs no credential, and step-up still asks for a passkey.
- Tests cover a bad signature, a wrong issuer or audience, a replayed `nonce` or
  `state`, an expired token, an unknown key id, a response arriving by GET, and an
  address outside the verified domains still getting the emailed code.
- No link is ever made by matching an email claim, proved by a test that a matching
  address with no invitation and no SCIM record links nothing.
- Every OIDC claim in the code cites the specification URL it was read from.
- A re-enrolment on a verified domain still requires the second approver and a fresh
  step-up assertion, with a test for each: the requester's own approval answers 409
  `four_eyes_violation`, and an approval without a fresh assertion answers 403
  `step_up_required`. The provider proof replaces the emailed code only.
- `--include='apps/identity/idp_oidc.py'` ≥ 95.

**Gates:** as `c13-int-contract`, with `apps.identity apps.shared` as the target and
the guard suites `tests_no_passwords`, `tests_authentication`, `tests_four_eyes` and
`tests_route_permissions`; `bash scripts/prepush.sh --quick`.

**Invariants:**
- No passwords, ever; the emailed code still stops at the first passkey.
- Four eyes and a passkey step-up on re-enrolment; SSO replaces the code, not them.
- Issuer plus subject is the only identifier; the email claim decides nothing.

### c13-sso-test-idp: a real identity provider inside the E2E stack

**Requirements:** ID-12
**Scenarios:** none (it lets ID-S27 and the journeys run without mocking)
**Depends on:** `c13-sso-oidc`
**Security review:** yes (a route that issues tokens, refused outside E2E)

Build the test provider (rule 15): a small OIDC provider served by the backend under
`E2E_MODE` only, with its own key pair generated at boot, a discovery document, a
JWKS, an authorisation endpoint that signs in the seeded person the journey names,
and a `form_post` response. It refuses to load when `E2E_MODE` is off, exactly as
the mail outbox does, with a test pinning that refusal and a second test proving no
URL of it is reachable on a deployed configuration. `seed_e2e` gains one provider
and one verified domain for tenant A.

**Owned paths:**
- `backend/apps/identity/e2e_idp.py`, `tests_e2e_idp.py`
- `backend/config/api.py` (the E2E-only mount), `backend/apps/shared/e2e_seed.py`
  (one seed call)

**Done when:**
- The provider serves a full OIDC round trip against `idp_oidc.py` in a test.
- Loading it with `E2E_MODE` off raises, and the deployed-configuration test proves
  the routes are absent.
- The seeded domain and provider appear for tenant A only.

**Gates:** as `c13-int-contract`, with `apps.identity apps.shared` as the target and
`tests_production_guard` added.

**Invariants:**
- No API is mocked in E2E; a double is a real endpoint that cannot exist in production.
- A test double never weakens a production path.

### c13-sso-enforcement: the provider is asked after the passkey

**Requirements:** ID-12
**Scenarios:** ID-S27 (un-skipped)
**Depends on:** `c13-sso-test-idp`
**Security review:** yes (the session flow; stops on an invariant question)

With enforcement on, a successful passkey assertion does not open a session: the API
answers `next: idp` and stores a single-use challenge bound to the user, the tenant,
the assertion and this browser, the last through a short-lived single-use cookie
compared at the callback. Only `completeIdpChallenge`, by POST, turns it into a
session; an unsolicited response, a response for another browser, a reused challenge
or one past `IDP_CHALLENGE_TTL_SECONDS` is refused and logged `idp_failed`.
Switching enforcement on needs `security.manage`, a step-up and a successful round
trip by the acting admin in the same step (otherwise 409), and the response first
reports how many members are not yet linked. Members outside the verified domains
are marked "outside SSO" and keep the ordinary flow. SSO never recovers a passkey and
never replaces a step-up, each proved by a test.

**Platform support may switch enforcement off, and only off** (owner item 11's last
sentence, which the first version of this plan left unbuilt). A misconfigured
provider can shut a whole bank out of its own tenant, and the bank's own admins are
inside it. So `disableIdpEnforcementForTenant` takes a platform session holding
`support_access.grant`, a fresh step-up assertion, and a reference to the out-of-band
check with the bank's contract contact, in the shape ID-S13 already uses for the last
admin. It writes the support access log and the tenant's audit through `record()`,
carrying the assertion id and the check reference, and notifies every active admin of
that tenant. The safe direction only: the same session cannot switch enforcement on,
cannot touch the provider, the domains, the links or the SCIM key, and cannot read a
single member's identity. Three tests pin that, one per refusal.

**Owned paths:**
- `backend/apps/identity/idp_enforcement.py`, `tests_idp_enforcement.py`
- `backend/apps/identity/api.py` is **not** this task's: the support route is declared
  by `c13-sso-idp-contract` with the rest of the SSO contract, answering 501 until
  this task lands (rule 3)
- `backend/apps/identity/session_logic.py` and `passkey_logic.py` (the `next: idp`
  branch only), `identity/tests_scenarios.py` (the ID-S27 skip line), settings
  banners, `.env.example`, `RAILWAY_VARIABLES.md`

**Done when:**
- ID-S27 is green, including the unsolicited response, the response in a URL and the
  absence of any provider-first route.
- Tests cover: the challenge bound to another browser, a reused challenge, an expired
  one, enforcement switched on without the admin's own round trip (409), and a
  step-up that still demands a passkey while enforcement is on.
- A member with no link cannot be locked out silently: the admin sees the count
  before switching on, and a test pins that the count is computed before the write.
- Platform support can switch enforcement off with the permission, the step-up and
  the check reference, and the action lands in both logs and in every admin's inbox;
  the same session switching it on, or touching any other SSO setting, is refused.
- `--include='apps/identity/idp_enforcement.py'` ≥ 95.

**Gates:** as `c13-sso-oidc`, plus `tests_route_permissions` and `tests_audit_on_write`.

**Invariants:**
- A passkey is the only way in; SSO opens no session alone.
- Step-up is always a fresh passkey assertion.
- Platform staff act in the safe direction only, under a logged grant the bank sees.

### c13-scim: the SCIM key and its default role

**Requirements:** ID-12
**Scenarios:** ID-S28 (un-skipped, green up to the create line)
**Depends on:** `c13-sso-oidc`
**Security review:** yes (a key with a new scope, privilege escalation)

Add the scope `scim` to `permissions.py`'s scope set, and `createScimKey` on the SSO
route: `security.manage` and `members.manage` together, plus a step-up, minting an
ordinary `api_key` row whose only scope is `scim`, shown once, stored hashed.
`POST /tenant/api-keys` answers 422 for that scope, so the key exists only where both
permissions were checked. `setScimDefaultRole` refuses a role holding
`members.manage`, `roles.manage`, `security.manage` or `integrations.manage`, and
`roles_logic` refuses an edit that would add one of those to a role already chosen as
the SCIM default. Every action is audited with the step-up id.

**Owned paths:**
- `backend/apps/identity/api_keys_logic.py`, `backend/apps/identity/scim_keys.py`,
  `tests_scim_keys.py`, `backend/apps/identity/roles_logic.py` (the one refusal),
  `apps/shared/permissions.py` (the scope constant and its description),
  `identity/tests_scenarios.py` (the ID-S28 skip line)

**Done when:**
- ID-S28 is green up to its create line, named in the docstring as extended by
  `c13-scim-users`.
- The general key route refuses the scope (422); a key created with only one of the
  two permissions is refused; the role checks fire in all three places.
- The key's plaintext appears once, and the shared no-secret proof gains the SCIM kind.
- `--include='apps/identity/scim_keys.py'` ≥ 95.

**Gates:** as `c13-sso-oidc`, plus `tests_permissions` and `tests_route_permissions`.

**Invariants:**
- No scope reaches the library or an admin permission.
- A key is shown once and stored hashed.

### c13-scim-users: provisioning and deprovisioning

**Requirements:** ID-12
**Scenarios:** ID-S28 (extended, the create line)
**Depends on:** `c13-scim`
**Security review:** yes (an external system writing members)

Serve the SCIM 2.0 `/scim/v2/Users` subset under `@requires_scope("scim")`: list
with a `userName eq` filter, get by id, create (which writes an invitation with the
default role and the directory id, never a credential), and PATCH `active=false`
(which deactivates as the members screen does). Responses are SCIM-shaped and carry
no permission, role list or tenant detail beyond what SCIM needs. A create whose
default role has since gained an admin permission is refused. A deactivate that would
leave the tenant without an admin answers 409 `last_admin` and notifies the admins
(the default of open question 3). Every action writes `record()` under the tenant,
with the key as actor. No Groups endpoint exists, and a request for one answers 404.

**Owned paths:**
- `backend/apps/identity/scim.py`, `tests_scim.py`, `backend/apps/identity/api.py`
  (the SCIM router mount only, after `c13-sso-idp-contract` merged),
  `identity/tests_scenarios.py` (the ID-S28 extension)

**Done when:**
- ID-S28's create line is green, including the refused admin-holding default role.
- Tests cover: the filter, an unknown user, a duplicate create (idempotent on the
  directory id), deactivation, the last-admin 409, a Groups request (404) and a key
  from another tenant (404).
- No SCIM response carries a permission or a role name a directory could act on.
- `--include='apps/identity/scim.py'` ≥ 95.

**Gates:** as `c13-sso-oidc`.

**Invariants:**
- A tenant always keeps one admin.
- Idempotency on every external write; `record()` on each.

### c13-sso-saml: the library check, and the answer either way

**Requirements:** ID-12
**Scenarios:** none (ID-S23 and ID-S27 are protocol-agnostic and stay green)
**Depends on:** `c13-scim`, `r1-readiness`
**Security review:** yes (a new dependency)

The check the cut list names, and nothing else: install the candidate SAML library in
the worktree, build both images, and run Trivy and `osv-scanner`. If the image breaks
or anything reports MEDIUM or above, the pin is reverted, what was found goes into
`HARDENING.md` and `TODO_FOR_alex.md`, `saml` stays a protocol kind whose selection
answers 422 `protocol_not_available`, and the chunk's SAML story ends here —
`c13-sso-saml-binding` is then not dispatched and `c13-close` names the cut. If it
passes, the pin and the scan output stay, `setIdentityProvider` accepts `saml` as a
protocol whose flow answers 501 until the binding lands, and the next task builds it.
Either way this task closes green: that is the green point the split falls on.

**Owned paths:**
- `backend/pyproject.toml`, `poetry.lock`,
  `backend/apps/identity/tests_saml_availability.py`,
  `docs/plans/briefs/HARDENING.md`, `docs/TODO_FOR_alex.md`,
  `docs/plans/Verification_Log.md`

**Done when:**
- The scan output is quoted in `Verification_Log.md` with the date and the versions
  scanned, whichever way it went.
- `setIdentityProvider` answers coherently for `saml` — 422 `protocol_not_available`
  if the check failed, 501 `not_built` if it passed — and a test pins that answer.
- If the check failed, `poetry.lock` is byte-identical to `main`'s.

**Gates:** as `c13-sso-oidc`, plus `bash scripts/prepush.sh --all` for the image and
scanner part of the check (the one task in this chunk that needs the full tier).

**Invariants:**
- No gate is lowered to fit a library in.
- What was cut is written down, never quietly dropped.

### c13-sso-saml-binding: the HTTP-POST binding, if the check passed

**Requirements:** ID-12
**Scenarios:** none (ID-S23 and ID-S27 are protocol-agnostic and stay green)
**Depends on:** `c13-sso-saml` (and only if it passed; otherwise this task is never dispatched)
**Security review:** yes (authentication)

The HTTP-POST binding only: signature and condition validation against the provider's
metadata fetched through the egress client, `InResponseTo` matched to our own
challenge, assertions single-use by id, clock skew from a setting, and the same
linking rules as OIDC (issuer plus subject, never the email claim). An unsolicited
assertion is refused, logged `idp_failed` and opens no session, exactly as under OIDC.

**Owned paths:**
- `backend/apps/identity/idp_saml.py`, `tests_idp_saml.py`, settings banners,
  `.env.example`, `RAILWAY_VARIABLES.md`

**Done when:**
- A valid response links and enrols; a bad signature, a wrong audience, an expired
  condition, a replayed assertion id, a mismatched `InResponseTo` and an unsolicited
  response each have a test and none opens a session.
- No link is made by matching an email claim, with a test.
- `--include='apps/identity/idp_saml.py'` ≥ 95.

**Gates:** as `c13-sso-oidc`.

**Invariants:**
- An unsolicited assertion is refused, logged and never opens a session.
- Issuer plus subject is the only identifier; the email claim decides nothing.

### c13-private-contract: the proposal's owner, its row-level security and the third door

**Requirements:** INV-07, PRO-03
**Scenarios:** none (PRO-S12 is `c13-private-approval`'s)
**Depends on:** `c4-proposal-kind`, `c5-contract-models-watch`, `r1-readiness`, task H-C
**Security review:** yes (the proposal door and a policy shape; stops on an invariant question)

Add `proposal.owner_tenant_id`, set by the server from the proposal's target — the
active tenant for a private-record kind or a target already owned, NULL otherwise —
and never read from the request body, proved by a test that a body naming an owner
is ignored. Give `proposal` forced row-level security in H-C's split shape: reads
cover shared rows and the session's own, inserts may be shared or own, updates and
deletes stay inside the session's own zone. Declare
`POST /private-proposals/{proposalId}/approve` and `/reject` on `proposals/api.py`
under the new `private_records.approve` permission with `@requires_step_up`,
answering 501 until `c13-private-approval`. Add `PRIVATE_RECORDS_APPROVE` to
`permissions.py` and to the Compliance officer and Approver system roles, to
`TENANT_PERMISSIONS` and to the four-eyes permission set, never to a platform role
and never to `ALL_SCOPES`. Add `approvePrivateProposal` as the third route
`ProposalDoorGuard` allows (ruling 6).

**Owned paths:**
- `backend/apps/proposals/models.py`, `migrations/`, `api.py`, `schemas.py`,
  `tests_private_contract.py`
- `backend/apps/shared/permissions.py` (the constant, its description, the role rows
  and the route list), `tests_rls.py`, `tests_four_eyes.py` (own entries),
  `backend/apps/proposals/door_guard.py` (the one route), `docs/inputs/INPUT_DELTAS.md`

**Done when:**
- `migrate_from_zero` applies; `tests_rls` proves as `cw_app` that tenant B cannot
  read, update or delete tenant A's proposal, cannot move a row between zones, and
  can still file a shared proposal that the console lists.
- A body carrying `ownerTenantId` changes nothing; the owner comes from the target.
- The permission is absent from every platform role and refused as an API key scope,
  each with a test.
- The door guard names exactly three routes, and `tests_library_fence` is untouched.

**Gates:** as `c13-int-contract`, with `apps.proposals apps.shared` as the target and
the guard suites `tests_rls`, `tests_four_eyes`, `tests_library_fence`,
`tests_route_permissions` and `tests_audit_on_write`.

**Invariants:**
- Proposals are the only door into the library; the door's routes are named and few.
- Two zones: forced RLS, and `cw_app` cannot bypass it.

### c13-private-child-rls: a watch child row cannot hide under a shared parent

**Requirements:** INV-07
**Scenarios:** none (INV-S9 goes green once the library parents follow)
**Depends on:** `c13-private-contract`, task H-C
**Security review:** yes (row-level security on watch child tables; stops on an invariant question)

Give every child table of `source` and `regulatory_change` — timeline events,
coverage rows, citations, documents, tags — two policies: FOR SELECT where the parent
is visible, and FOR ALL where the parent's `owner_tenant_id` equals the session's
tenant. That closes half of H7's private half: today a child is reachable only through
its parent by convention, not by the database. One migration in `watch`, each table
listed in `tests_rls` with its parent named, and one `cw_app` test per child table
proving that tenant B cannot insert, update or delete a child under a shared parent or
under tenant A's parent, and that reads of a shared parent's children are unchanged.
The `mig:watch` key is taken here first, before `c13-private-sources`.

**Owned paths:**
- `backend/apps/watch/migrations/`
- `backend/apps/shared/tests_rls.py` (its own table entries),
  `backend/apps/watch/tests_private_rls.py`

**Done when:**
- Every child table of `source` and `regulatory_change` is covered; the RLS guard
  fails if a new child table of either appears without the pair of policies.
- A `cw_app` test per child table proves the refused write and the unchanged read.
- No read path regresses: the watch read suites stay green.

**Gates:** as `c13-private-contract`, with `apps.watch apps.shared` as the target and
`migrate_from_zero`.

**Invariants:**
- Two zones hold in the database, not only in code.
- Nothing overwritten: the policies add, they do not replace an append-only rule.

### c13-private-child-rls-library: the library parents get the same pair

**Requirements:** INV-07
**Scenarios:** INV-S9 (un-skipped, as reworded by PRD 0.4)
**Depends on:** `c13-private-child-rls`
**Security review:** yes (row-level security on library child tables; stops on an invariant question)

The same pair of policies, in the same shape, on every child table of `instrument`
and `obligation` — titles, versions, summaries, translations, terms, tags, citations,
documents. One migration in `library`, each table listed in `tests_rls` with its
parent named, and one `cw_app` test per child table. With all four parents covered,
H7's private half is closed and INV-S9 goes green in every clause.

**Owned paths:**
- `backend/apps/library/migrations/`
- `backend/apps/shared/tests_rls.py` (its own table entries),
  `backend/apps/library/tests_private_rls.py`,
  `backend/apps/library/tests_scenarios.py` (the INV-S9 skip line),
  `docs/plans/briefs/HARDENING.md` (H7's private half, closed)

**Done when:**
- INV-S9 is green, including the platform-session 404 and the refused child write.
- Every child table of all four parents is covered; the RLS guard fails if a new child
  table appears without the pair of policies.
- No read path regresses: the library read suites stay green.

**Gates:** as `c13-private-contract`, with `apps.library apps.shared` as the target and
`migrate_from_zero`.

**Invariants:**
- Two zones hold in the database, not only in code.
- Nothing overwritten: the policies add, they do not replace an append-only rule.

### c13-private-approval: a second person in the bank approves

**Requirements:** INV-07, PRO-02, PRO-03
**Scenarios:** PRO-S12 (un-skipped)
**Depends on:** `c13-private-contract`, `c4-approve-apply`
**Security review:** yes (four eyes, step-up, the apply path)

Serve the two private-proposal routes from `proposals/private_approval.py`, reusing
`approve_and_apply` unchanged: the same standards checks, the same version write, the
same `record()` — but inside the tenant's zone, with `private_records.approve`, a
fresh assertion and the four-eyes check constraint, so the proposer's own approval
answers 409 `four_eyes_violation`. A library editor's fetch of a private proposal
answers 404 and the console queue never lists one. Rejecting needs a reason from the
existing rejection-reason list and no step-up.

**Owned paths:**
- `backend/apps/proposals/private_approval.py`, `tests_private_approval.py`,
  `backend/apps/proposals/tests_scenarios.py` (the PRO-S12 skip line)

**Done when:**
- PRO-S12 is green in all four of its clauses.
- The audit and outbox rows carry the tenant, the approver and the step-up assertion
  id; a test proves `steppedUp` is true (the H8 class of bug does not return).
- A platform session, in the console or under a support grant, gets 404 for the
  proposal, the approve route and the reject route.
- `--include='apps/proposals/private_approval.py'` ≥ 95.

**Gates:** as `c13-private-contract`.

**Invariants:**
- Four eyes, enforced by the check constraint, with a passkey step-up.
- One apply path: a private proposal reuses it rather than copying it.

### c13-private-sources: a bank asks for a source, and the address is checked

**Requirements:** WAT-06, INV-07
**Scenarios:** none (WAT-S8 is `c13-private-source-visibility`'s)
**Depends on:** `c13-private-contract`, `c13-private-child-rls`, `c5-watch-registration`, `c11-research-requests`
**Security review:** yes (an address the bank supplies)

Serve `POST /source-requests` and its list under `agents.manage` or
`proposals.create`: the address is checked at the request — https only, no
credentials, a public host through the egress client's rules, not a standards
publisher's host, not an existing shared source (409 naming it), and no more than
`PRIVATE_SOURCES_MAX` per bank — and one tenant audit row is written. This half
stores the `SourceRequest` with its chosen visibility and completes the shared path:
a shared request lands in the console queue `c5-fe-console-sources` already shows. The
private branch — the owned `Source`, the console's blindness and the cross-tenant
404 — is `c13-private-source-visibility`'s. It depends on `c13-private-child-rls`
because both own `backend/apps/watch/migrations/` (finding 4), which the key table
already ordered.

**Owned paths:**
- `backend/apps/watch/source_requests.py`, `tests_source_requests.py`,
  `backend/apps/watch/api.py` and `schemas.py` (the three operations, holding
  `watchapi`), `backend/apps/watch/models.py` and `migrations/` (the
  `SourceRequest` model), settings banner, `.env.example`, `RAILWAY_VARIABLES.md`,
  `docs/inputs/INPUT_DELTAS.md`

**Done when:**
- A request is stored with its visibility, under either permission, with its one
  tenant audit row; a member with neither permission gets 403.
- Each address check has a test, including a host that resolves to a private address
  and one that redirects to a publisher we watch.
- The cap has a test, and the shared path reaches the console queue unchanged.
- `--include='apps/watch/source_requests.py'` ≥ 95.

**Gates:** as `c13-private-contract`, with `apps.watch apps.shared` as the target.

**Invariants:**
- Input from a person is validated at the trust boundary; the error names no host.
- Every threshold is a setting with an env override.

### c13-private-source-visibility: a private source belongs to one bank

**Requirements:** WAT-06, INV-07
**Scenarios:** WAT-S8 (un-skipped, green up to the re-check line)
**Depends on:** `c13-private-sources`
**Security review:** yes (an owner column and a platform surface)

Build the private branch: an approved private request creates a `Source` with
`owner_tenant_id` set, which never reaches the console queue and never appears on any
platform surface. Tenant B's read of A's private source, and of anything registered
against it, answers 404 — never 403, and never a hint that the row exists. A platform
session, in the console or under a support grant, gets the same 404 (INV-S9 as
reworded by PRD 0.4).

**Owned paths:**
- `backend/apps/watch/source_requests.py` (the private branch only),
  `backend/apps/watch/tests_private_sources.py`,
  `backend/apps/watch/tests_scenarios.py` (the WAT-S8 skip line)

**Done when:**
- WAT-S8 is green up to "the host is checked again at the start of every run", named
  in the docstring as extended by `c13-private-source-runs`.
- The console's blindness to a private request, the platform session's 404 and the
  cross-tenant 404 each have a test.
- A private request is never listed by any console route, proved over the route list
  rather than over one endpoint.
- `--include='apps/watch/source_requests.py'` ≥ 95.

**Gates:** as `c13-private-contract`, with `apps.watch apps.shared` as the target.

**Invariants:**
- A tenant's own records never reach a platform surface.
- Tenant B sees 404, never 403 and never the data.

### c13-private-source-runs: a private source is re-checked, and runs only when approved

**Requirements:** WAT-06
**Scenarios:** WAT-S8 (extended, the re-check line)
**Depends on:** `c13-private-source-visibility`, `c11-run-scheduler`, `c5-cases-creation`
**Security review:** yes (what leaves to the agent runner; stops on an invariant question)

At the start of every run that touches a private source, re-run the address checks;
a host that has become private, moved scheme or started redirecting off its origin
makes the run skip that source, write a coverage row with the reason kind and notify
the requester. Add the runner gate of open question 1: the scheduler skips a private
source unless its runner endpoint is on `PRIVATE_SOURCE_RUNNERS_APPROVED`, a reviewed
constant in the production-safety block that starts empty, and the screen shows the
waiting state. What reaches the runner is the address and the fetched public page;
nothing stored about the bank goes with it, proved by a test over the request the
adapter is given. A change registered from a private source carries
`owner_tenant_id` and reaches that bank's feed only.

**Owned paths:**
- `backend/apps/watch/private_runs.py`, `tests_private_runs.py`,
  `backend/apps/watch/tests_scenarios.py` (the WAT-S8 extension),
  `backend/config/settings.py` (the reviewed constant, in the production-safety
  block), `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`

**Done when:**
- WAT-S8's last line is green.
- With the constant empty, no private source is scheduled and the reason is readable;
  with an endpoint listed, the run proceeds — both tested.
- A test asserts the exact payload handed to the agent runner: the address and the
  fetched page, no tenant name, no footprint, no judgement.
- `--include='apps/watch/private_runs.py'` ≥ 95.

**Gates:** as `c13-private-contract`, with `apps.watch apps.agents apps.shared` as the
target.

**Invariants:**
- Tenant content never reaches an unapproved model endpoint.
- A guard list is a reviewed constant, never an environment variable.

### c13-private-obligations: the bank's own instruments and obligations

**Requirements:** INV-07
**Scenarios:** none (INV-S13 is `c13-private-no-ai-index`'s)
**Depends on:** `c13-private-approval`, `c13-private-sources`
**Security review:** yes (the apply path writing owned rows)

Add the private kinds to `proposals/apply.py`: `create_private_instrument` and
`create_private_obligation`, which write `instrument` and `obligation` rows with
`owner_tenant_id` set from the proposal's owner, their version and title children in
the same transaction, and the audit and outbox rows in the tenant's zone. A private
instrument holds no provisions in R3 (D-57): a payload carrying one answers 422
`private_provisions_not_supported`. The inventory, the obligation page and every
library read already filter by `owner_tenant_id IS NULL OR owner_tenant_id = :tenant`
through `library/reading.py`; this task proves it for the new rows rather than adding
a second rule. A shared proposal can never produce an owned row, and an owned
proposal can never write a shared one.

**Owned paths:**
- `backend/apps/proposals/apply.py` (the two kinds only),
  `backend/apps/proposals/tests_apply_private.py`,
  `backend/apps/library/tests_private_reads.py`

**Done when:**
- Both kinds apply, with their versions, under the approver's step-up, and appear in
  the owner's inventory and nowhere else.
- The provisions refusal, the shared-to-owned refusal and the owned-to-shared refusal
  each have a test.
- `library_write()` is still called only from `apply.py`; the fence suite is green and
  its allowlist unchanged.
- `--include='apps/proposals/apply.py'` does not drop below its existing floor.

**Gates:** as `c13-private-contract`, with `apps.proposals apps.library apps.shared`
as the target.

**Invariants:**
- One door, one apply path; the fence allowlist does not grow.
- Stable keys never change; versions with effective dates, nothing overwritten.

### c13-private-no-ai-index: no private text to a model or the index

**Requirements:** INV-07
**Scenarios:** INV-S13 (un-skipped)
**Depends on:** `c13-private-obligations`, `c7-search-index`
**Security review:** yes (the AI and index boundary)

Prove and, where needed, enforce the second half of D-57. The indexer skips any row
with an owner and any child of one; the embedder and reranker are never called for
them; find-similar answers from shared rows only; a private change gets no AI-drafted
"So what?" and the AI log records no generation for it; and the tenant's exit deletes
private instruments and obligations with their append-only children (the hook chunk
12 owns is called with the new tables listed). Where a code path could reach a model
with an owned row, the guard is a refusal in the one logging wrapper, not a caller's
good manners.

**Owned paths:**
- `backend/apps/search/indexing.py` (the owner skip only),
  `backend/apps/shared/adapters/__init__.py` or the AI logging wrapper (one refusal),
  `backend/apps/library/tests_scenarios.py` (the INV-S13 skip line),
  `backend/apps/search/tests_private_index.py`,
  `backend/apps/cases/tests_private_so_what.py`

**Done when:**
- INV-S13 is green in all four of its clauses.
- A test drives the indexer over a tenant's private instrument, obligation and their
  versions and asserts no chunk row, no embedding call and no rerank call.
- A direct call to the model wrapper carrying an owned row raises, with a test.
- The tenant-exit list names the private tables, with a test that the export and the
  deletion see them.

**Gates:** as `c13-private-contract`, with `apps.search apps.library apps.cases
apps.shared` as the target; `python backend/scripts/search_eval.py` (the index
changed).

**Invariants:**
- No private row, and no child of one, is indexed, embedded, reranked or sent to a model.
- Every model call goes through the one logging wrapper.

### c13-follow-contract: following a record

**Requirements:** COL-03
**Scenarios:** none (COL-S4 is `c13-follow-notify`'s)
**Depends on:** `c3-provision-read`, `c10-collab-models`

Add `Follow` as the designed composite-key tenant table (tenant, user, subject type,
subject id) with its migration and `Meta.ordering`, and declare `listFollows`,
`followRecord` and `unfollowRecord` on `collab/api.py` under any member session,
serving from `collab/follow.py`. Following is personal: a row is written for the
caller only, the caller can only read and remove their own, and the response carries
no other person's name or any count. A follow of a record the caller cannot read
answers 404, and a subject type outside instrument, obligation and change answers
422. `openapi.yaml` declares no follow operation, so an INPUT_DELTAS §1 row names the
three ids.

**Owned paths:**
- `backend/apps/collab/models.py` (one model), `migrations/`, `api.py`, `schemas.py`,
  `follow.py`, `tests_follow.py`
- `apps/shared/permissions.py` (route list), `tests_rls.py`, `factories.py`,
  `docs/inputs/INPUT_DELTAS.md`

**Done when:**
- `migrate_from_zero` applies; the table is under forced RLS and in `tests_rls`;
  tenant B sees none of A's rows and cannot write one.
- Follow, unfollow, following twice (idempotent), the unreadable-record 404 and the
  bad subject type 422 each have a test.
- No response carries another person's identity or a follower count.

**Gates:** as `c13-int-contract`, with `apps.collab apps.shared` as the target.

**Invariants:**
- Following grants no access; permissions still decide every read.
- Personal rows stay personal: one person's follows are invisible to everyone else.

### c13-follow-notify: a followed record changed

**Requirements:** COL-03, COL-02
**Scenarios:** COL-S4 (un-skipped)
**Depends on:** `c13-follow-contract`, `c13-library-change-fanout`, `c10-notifications-api`

Consume the fanout: for each `library.changed` event, notify the tenant's followers
of that subject in their own language, once each, through chunk 10's notification
writer and D-34's one recipient check, with the new `notification.kind`
`followed_change`. A person who both follows the record and takes part in it gets one
notification, not two: the writer deduplicates on (person, subject, event). After an
unfollow the next change sends nothing. A follower whose permissions no longer let
them read the record is not notified.

**Owned paths:**
- `backend/apps/collab/follow_notify.py`, `tests_follow_notify.py`,
  `backend/apps/collab/tasks.py` (its own handler), `backend/apps/collab/migrations/`
  (the one new `notification.kind` value, holding `mig:collab` after
  `c13-follow-contract`), `apps/shared/kinds.py` (one kind),
  `backend/apps/collab/tests_scenarios.py` (the COL-S4 skip line),
  `docs/inputs/INPUT_DELTAS.md`

**Done when:**
- COL-S4 is green, including the one-notification rule and the silence after
  unfollowing.
- A test proves the notification title carries no tenant judgement and no comment text.
- A second run over the same event notifies nobody.
- `--include='apps/collab/follow_notify.py'` ≥ 95.

**Gates:** as `c13-library-change-fanout`.

**Invariants:**
- D-34's one recipient check, for every kind.
- Notifications are idempotent per event.

### c13-saved-search-contract: saved searches that store keys

**Requirements:** SRC-04
**Scenarios:** none (SRC-S7 is `c13-saved-search-notify`'s)
**Depends on:** `c7-hybrid-search-backend`, `c7-search-index`

Add `SavedSearch` as designed, plus `last_opened_at` (INPUT_DELTAS row: the column is
new and is what "New since your last visit" reads), and declare `listSavedSearches`,
`createSavedSearch`, `updateSavedSearch`, `deleteSavedSearch` and
`openSavedSearch` on `search/api.py` under `search.use`, serving from
`search/saved.py`. A saved search belongs to one person: another member of the same
tenant gets 404. Filters are stored as the keys the search API already takes, never
labels, and a filter naming an unknown key answers 422. `SAVED_SEARCHES_MAX` caps the
list per person. `openSavedSearch` runs the stored query, marks the hits newer than
`last_opened_at`, and then advances it in the same transaction.

**Owned paths:**
- `backend/apps/search/models.py` (one model), `migrations/`, `api.py`, `schemas.py`,
  `saved.py`, `tests_saved.py`
- `apps/shared/permissions.py` (route list), `tests_rls.py`, `factories.py`, settings
  banner, `.env.example`, `RAILWAY_VARIABLES.md`, `docs/inputs/INPUT_DELTAS.md`

**Done when:**
- `migrate_from_zero` applies; forced RLS, `tests_rls` entry, cross-tenant and
  cross-person 404s tested.
- A vocabulary rename leaves a stored filter and its results unchanged (the SRC-04
  half of playbook 15), with a test.
- The cap, the unknown-key 422 and the `last_opened_at` advance each have a test.
- The search budget still holds: `openSavedSearch` is one search, measured.

**Gates:** as `c13-int-contract`, with `apps.search apps.shared` as the target;
`python backend/scripts/search_eval.py`.

**Invariants:**
- Store and compare keys, never labels.
- Paginate; default 20, max 100.

### c13-saved-search-notify: a new hit, in the reader's language

**Requirements:** SRC-04
**Scenarios:** SRC-S7 (un-skipped)
**Depends on:** `c13-saved-search-contract`, `c13-library-change-fanout`, `c10-notifications-api`

Consume the fanout: for each `library.changed` event in a tenant, run the saved
searches that asked for notification against the changed record alone — never the
whole index — and notify the owner in their language with the existing
`saved_search_hit` kind, once per search per event. The match runs under the owner's
own permissions and the tenant's scope, so a person is never told about a record they
could not open. Opening the search then shows the hit marked new, from
`last_opened_at`.

**Owned paths:**
- `backend/apps/search/saved_notify.py`, `tests_saved_notify.py`,
  `backend/apps/search/tasks.py` (its own handler),
  `backend/apps/search/tests_scenarios.py` (the SRC-S7 skip line)

**Done when:**
- SRC-S7 is green, including the language and the "New since your last visit" marker.
- A test pins that one event costs one match per notifying saved search, not one
  index sweep.
- A saved search whose owner lost `search.use`, or whose hit is outside their reads,
  notifies nobody.
- `--include='apps/search/saved_notify.py'` ≥ 95.

**Gates:** as `c13-saved-search-contract`.

**Invariants:**
- D-34's recipient check; a notification never carries tenant judgement.
- Fan out, never chain.

### c13-reg06-attestations: the yearly attestation and its routes

**Requirements:** REG-06
**Scenarios:** REG-S9 (un-skipped, green up to the waiver line)
**Depends on:** `c8-register-models`, `c8-ten-teams`, `c6-roadmap-backend`, `c8-reg-duty-occurrences`, `c8-home-register-feeds`
**Security review:** yes (a new tenant table and an owner-only write)

Add `Attestation` as designed (tenant, tenant obligation, period year, attested by,
attested at, status at attest, statement, unique per obligation and year) with its
migration, and declare both REG-06 contracts on `register/api.py` (ruling 11):
`listAttestations` and `createAttestation` under `register.edit`, plus
`listWaivers`, `createWaiver` and `revokeWaiver` under `risk.accept.approve` with a
step-up, the waiver three answering 501 until `c13-reg06-waivers`. Only the
obligation's owner may attest, checked on the server, not in the screen. Attesting
records the compliance status at that moment and writes `record()`; attesting twice
in the same period year answers 409. `ATTESTATION_INTERVAL_MONTHS` decides when an
obligation is due.

**Owned paths:**
- `backend/apps/register/models.py` (one model), `migrations/`, `api.py`, `schemas.py`,
  `attestations.py`, `tests_attestations.py`
- `apps/shared/permissions.py` (route lists), `tests_rls.py`, `factories.py`, settings
  banner, `.env.example`, `RAILWAY_VARIABLES.md`,
  `backend/apps/register/tests_scenarios.py` (the REG-S9 skip line)

**Done when:**
- REG-S9 is green up to "When a waiver is granted", named in the docstring as extended
  by `c13-reg06-waivers`.
- Due-for-attestation is computed on a frozen clock from the anchor, with a test at 11,
  12 and 13 months.
- A non-owner's attest answers 403, a second attest in the year 409, and both are
  audited.
- `migrate_from_zero` applies; forced RLS and a `tests_rls` entry.

**Gates:** as `c13-int-contract`, with `apps.register apps.shared` as the target.

**Invariants:**
- Permissions, never role names; ownership is checked on the server.
- `record()` on every write; clocks anchored, never "today".

### c13-reg06-attest-roadmap: the attestation date on the roadmap and on Today

**Requirements:** REG-06, HOM-03
**Scenarios:** REG-S9 stays green; HOM-S4 stays green
**Depends on:** `c13-reg06-attestations`

Extend the roadmap's register branch, which `c8-home-register-feeds` built, with the
attestation due date as an internal item carrying "Our deadline" and its owner, and
add the same item to My work's "Due soon" through the service D-23 defines. No second
roadmap query is written: the branch is added inside `home/roadmap.py`'s existing
register feed (chunk 6 ruling 5). The calendar feed carries no attestation date: it
holds public library facts only (D-52).

**Owned paths:**
- `backend/apps/home/roadmap.py` (the one branch), `backend/apps/home/my_work.py`
  (the one section), `backend/apps/home/tests_roadmap_attestation.py`

**Done when:**
- An attestation due inside the quarter appears on the roadmap with its owner, and
  disappears once attested, both tested on a frozen clock.
- The item appears on the owner's My work and on no one else's without
  `register.read`.
- The calendar feed still carries no internal date, with a test.
- The roadmap query count is unchanged (the chunk 6 pin stays green).

**Gates:** as `c13-int-contract`, with `apps.home apps.register apps.shared` as the
target.

**Invariants:**
- One roadmap query; fan out, never chain.
- Tenant judgement never reaches the public feed.

### c13-reg06-waivers: a waiver with an expiry

**Requirements:** REG-06, REG-03
**Scenarios:** REG-S9 (extended, the waiver line)
**Depends on:** `c13-reg06-attestations`, `c8-reg-gaps`

Add `Waiver` as designed (tenant, tenant obligation, description, granted by as text,
valid from, valid to, created by), serve the three routes from
`register/waivers.py` under `risk.accept.approve` with a step-up and the four-eyes
rule (never the person who raised the gap), show it on the gap, and add a nightly
`@tenant_task` that returns a lapsed waiver's gap to open and notifies the owner. A
waiver never changes the gap's own status history: it is its own row, and the gap
returns to exactly the status it had.

**Owned paths:**
- `backend/apps/register/models.py` (one model, after `c13-reg06-attestations`),
  `migrations/`, `backend/apps/register/waivers.py`, `tests_waivers.py`,
  `backend/apps/register/tasks.py` (its own beat entry),
  `backend/apps/register/tests_scenarios.py` (the REG-S9 extension),
  `apps/shared/tests_four_eyes.py` (its own entry)

**Done when:**
- REG-S9's waiver lines are green, lapse included, on a frozen clock.
- The step-up, the four-eyes refusal and the audit row with the assertion id are
  tested.
- A lapsed waiver leaves the gap open and the history readable; a second nightly run
  changes nothing.
- `--include='apps/register/waivers.py'` ≥ 95.

**Gates:** as `c13-reg06-attestations`, plus `tests_four_eyes`.

**Invariants:**
- "Applies" and "we comply" stay separate; a waiver never hides a gap.
- Four eyes on an approval; nothing overwritten.

### c13-i18n-seed-labels: da, nb and fi labels on every seeded list

**Requirements:** I18N-02, I18N-01
**Scenarios:** I18N-S1 and I18N-S2 stay green
**Depends on:** every package that seeds a vocabulary or a library list (keys `taxseed`, `seedlib`)

Add the Danish, Norwegian and Finnish labels to every seeded vocabulary row and
library list row, beside the existing en and sv. The five `Language` rows already
exist in the library seed, so nothing is added there. The seed stays idempotent on
its immutable keys, adds no audit row where H5's fix says none should appear, and
never rewrites a label an editor changed through a proposal (f03-T01's rule). A
label missing in one of the five languages fails the seed-integrity test, which gains
the three languages.

**Owned paths:**
- `backend/apps/taxonomy/seeds/__init__.py`, `backend/apps/library/seeds/*.py`
  (labels only), `backend/apps/shared/tests_seed_integrity.py` (its own entries)

**Done when:**
- Every seeded list row has five labels; the integrity test fails if one is missing.
- Re-running `seed_reference` twice changes nothing, and an approved relabel survives
  it.
- The native-speaker review of the three languages is listed for Alex by `c13-close`
  (parallel plan 7.3: people).

**Gates:** as `c13-int-contract`, with `apps.taxonomy apps.library apps.shared` as the
target and `tests_seed_integrity`.

**Invariants:**
- Labels are rows; keys never change.
- A seed never undoes an approved change.

### c13-i18n-server: the server's mail and documents in five languages

**Requirements:** I18N-02
**Scenarios:** COL-S2 stays green
**Depends on:** `c10-mail-catalog`, `c6-briefing-backend`, `c12-committee-pack`, `f03-T79`

Add da, nb and fi to every server-side catalog: the briefing mail, the notification
and reminder mails, the digest, the escalation and the committee pack's fixed
strings, each in the recipient's own language from `User.locale`, which is already a
foreign key to the five seeded `Language` rows (so no CHECK and no column changes,
correcting parallel-plan ruling 21's premise). A missing key in any of the five
languages fails the existing catalog test rather than falling back silently; the
fallback to en remains only for a language nobody has selected.

**Owned paths:**
- `backend/apps/collab/mail_catalog.py` (or the module `c10-mail-catalog` created),
  `backend/apps/home/briefing_mail.py` strings, `backend/apps/reports/pack_strings.py`,
  their tests, `docs/inputs/INPUT_DELTAS.md` (the ruling 21 correction)

**Done when:**
- Every server catalog has five languages and the completeness test covers all five.
- A recipient with locale da receives the da mail, tested per mail kind.
- No user-facing server string is built by concatenation; each is one catalog entry
  with named placeholders.

**Gates:** as `c13-int-contract`, with `apps.collab apps.home apps.reports apps.shared`
as the target.

**Invariants:**
- Every user-facing string is in a catalog; no string literal in code.
- A person's language is a row, never a branch.

### c13-fe-follow: the follow control on a record

**Requirements:** COL-03
**Scenarios:** none (COL-S4's journey is `c13-e2e-follow`'s)
**Depends on:** `c13-follow-contract`, `c3-fe-instruments`, `c13-cards-tenant-other`

Add `frontend/src/features/follow/` (`api.ts`, `hooks.ts`) and the control the card
draws, mounted on the obligation page and the instrument page (key `obpage`, first of
the three tasks that hold it). Optimistic on the follower's own row only, invalidating
the follow query on settle; every string in the catalog; the denied and error states
from `states.html`; no follower count and no other person's name anywhere.

**Owned paths:**
- `frontend/src/features/follow/`, `frontend/src/components/inventory/FollowButton.tsx`
  and its test, the obligation and instrument screen components (the mount only),
  `frontend/src/messages/follow/{en,sv}.json`,
  `frontend/src/shared/navigation/registry.ts` (no entry; stated here so the next
  reader does not look for one)

**Done when:**
- Follow and unfollow work against the real API, with loading, error and denied
  states; the control says what it does in both languages.
- `npm run lint`, `typecheck`, `test:coverage` and `check:messages` pass, and
  `npm run build` is green.
- No string literal in JSX text; no `console.log`.

**Gates:**
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**
- Typography roles only; pills through `Pill`; every string in a catalog.
- The client branches on `code`, never on `detail`.

### c13-fe-saved-searches: the Saved tab

**Requirements:** SRC-04
**Scenarios:** none (SRC-S7's journey is `c13-e2e-saved-searches`'s)
**Depends on:** `c13-saved-search-contract`, `c7-ask-screen`, `c13-cards-tenant-other`

Build the Saved tab on the search screen (key `searchscreen`): save the current query
and filters with a name, list, rename, delete, open (which runs the search and marks
the new hits), the notify switch, and the cap notice. Filters render their labels from
the vocabulary catalogs while the saved row keeps keys, so a rename in the admin
changes the label on screen and nothing else.

**Owned paths:**
- `frontend/src/features/search/saved-*.ts(x)` and their tests, the search screen
  component (the tab only), `frontend/src/messages/search/{en,sv}.json` (its own keys)

**Done when:**
- Save, open with the new-hit marker, rename, delete, the notify switch and the cap
  message all work against the real API in both languages.
- A search saved with a filter whose label is later renamed shows the new label and
  the same results.
- The frontend gate set passes.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- Keys stored, labels rendered; no string literal in JSX.

### c13-fe-allowlist: the IP allow-list panel

**Requirements:** ID-13, ADM-01
**Scenarios:** none (ID-S24's journey is `c13-e2e-identity-admin`'s)
**Depends on:** `c13-ip-allowlist`, `c13-cards-admin-security`, `c11-fe-admin-security`

Add the allow-list panel to the admin Security screen that chunk 11 built, in
`frontend/src/features/security/` (key `secfe`, first of the three tasks that hold
it; the task extends the directory if `c11-fe-admin-security` created it and
otherwise creates it): the CIDR rows, add and remove with the step-up prompt, the cap, and the 409
`would_lock_you_out` rendered as the plain sentence the card draws. A nav entry for
Security already exists from chunk 11; this task adds none.

**Owned paths:**
- `frontend/src/features/security/` (`api.ts`, `hooks.ts`, `allowlist-*.tsx`) and
  tests, the admin security screen component (the panel mount only),
  `frontend/src/messages/security/{en,sv}.json`

**Done when:**
- Add, remove, the step-up, the cap and the lock-out refusal all render from the
  server's `code`, in both languages, with every state.
- The frontend gate set passes.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- Step-up is prompted where the server demands it; the client never decides it alone.
- Errors branch on `code`.

### c13-fe-attest: the attestation panel

**Requirements:** REG-06
**Scenarios:** none (REG-S9's journey is `c13-e2e-register`'s)
**Depends on:** `c13-reg06-attest-roadmap`, `c8-ui-where-we-stand`, `c13-cards-tenant-register`

Build the attestation panel on the obligation page (key `obpage`, after
`c13-fe-follow`): last attested and by whom, the status attested to, the due date and
"due for attestation" as a `warning` pill from the kind, the statement field, and the
Attest control shown only to the owner — absent, not disabled, for everyone else.

**Owned paths:**
- `frontend/src/features/register/attestation-*.ts(x)` and tests,
  `frontend/src/components/register/AttestationPanel.tsx`, the obligation page
  component (the mount only), `frontend/src/messages/register/{en,sv}.json` (own keys),
  `frontend/src/features/shared/tone-by-kind.ts` (its own entries)

**Done when:**
- The panel renders every state in both languages and attests against the real API.
- A non-owner sees the history and no control; a 403 is never reached by clicking.
- The presentation function has its unit test, and the tone comes from the kind.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- Pills only through `Pill`, tone by kind; no permission decided in the client beyond
  hiding what the server would refuse.

### c13-fe-waive: the waiver panel

**Requirements:** REG-06, REG-03
**Scenarios:** none
**Depends on:** `c13-reg06-waivers`, `c8-ui-risk-acceptance`, `c13-fe-attest`

Build the waiver panel on the gap (key `obpage`, after `c13-fe-attest`): the waiver
with its description, who granted it, the dates, the step-up on granting, the
expiring-soon and lapsed states, and the sentence that says the gap is open again.
Revoking a waiver is the safe direction and needs no step-up.

**Owned paths:**
- `frontend/src/features/register/waiver-*.ts(x)` and tests,
  `frontend/src/components/register/WaiverPanel.tsx`, the obligation page component
  (the mount only), `frontend/src/messages/register/{en,sv}.json` (own keys)

**Done when:**
- Grant with step-up, revoke, the four-eyes refusal rendered from its `code`, and the
  lapsed state all work in both languages.
- The gap's own status is never shown as changed by a waiver.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- A waiver never hides a gap on screen either.

### c13-fe-integrations-screen: webhooks and their delivery log

**Requirements:** INT-01, ADM-01
**Scenarios:** none (INT-S1's journey is `c13-e2e-integrations-webhooks`'s)
**Depends on:** `c13-webhook-retries`, `c13-cards-admin`

Build `/admin/integrations` (key `intfe`) with the webhook half: the list, Add with
the secret shown once and the step-up, Rotate, Pause, Delete, and the delivery log
with its status pills, response code, attempts and duration, plus Redeliver. Add the
nav entry under `integrations.manage` in `registry.ts`, which makes ADM-S1's "absent
without the permission" clause real for this screen.

**Owned paths:**
- `frontend/src/features/integrations/` (`api.ts`, `hooks.ts`,
  `integrations-presentation.ts`) and tests,
  `frontend/src/app/(tenant)/admin/integrations/page.tsx`,
  `frontend/src/components/admin/WebhooksPanel.tsx`,
  `frontend/src/messages/integrations/{en,sv}.json`,
  `frontend/src/shared/navigation/registry.ts` (one entry),
  `frontend/src/features/shared/tone-by-kind.ts` (its own entries)

**Done when:**
- Every webhook operation works against the real API, with empty, loading, error and
  denied states, in both languages.
- The secret is shown once, with the copy control and the sentence that it will not be
  shown again; it is never re-fetched.
- The nav entry appears only with `integrations.manage`.
- The frontend gate set passes and the navigation snapshot is regenerated by the main
  agent at merge.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- A secret is shown once; the client stores none.
- Pills by kind; every string in the catalog.

### c13-fe-integrations-connections: the ticket and SIEM connections

**Requirements:** INT-02, INT-03
**Scenarios:** none (INT-S4's journey is `c13-e2e-integrations-webhooks`'s)
**Depends on:** `c13-fe-integrations-screen`, `c13-siem-stream`, `c13-tickets-export-api`, `c13-cards-admin-connections`

Add the two connection panels to the same screen (key `intfe`, after
`c13-fe-integrations-screen`): the ticket tracker (provider, project key, base url,
token entered once, Test, Disconnect, and the plain message for a provider with no
adapter) and the SIEM connection (endpoint, token once, Test, Disconnect, the lag as
a sentence and the last delivered event's time). Both writes prompt the step-up.

**Owned paths:**
- `frontend/src/features/integrations/connections-*.ts(x)` and tests,
  `frontend/src/components/admin/ConnectionsPanel.tsx`,
  `frontend/src/messages/integrations/{en,sv}.json` (own keys)

**Done when:**
- Both connections save, test and disconnect against the real API in both languages,
  with every state including `provider_not_available` and `secrets_unavailable`.
- The token is entered once and never returned; the screen shows a prefix only.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- Errors branch on `code`; no trace ever reaches the screen.

### c13-fe-tickets-screen: Send as tickets on the actions panel

**Requirements:** INT-02
**Scenarios:** none (INT-S3's journey is `c13-e2e-integrations-tickets`'s)
**Depends on:** `c13-tickets-export-api`, `c13-fe-integrations-connections`, `c9-fe-actions-panel`, `c13-cards-tenant-other`

Add the control to the case actions panel (keys `intfe`, `casesfe`): "Send as
tickets" with its confirmation, the per-action ticket reference and link once
created, the already-sent state, and the no-tracker state that links an admin to
`/admin/integrations` and tells everyone else who to ask. The idempotency key comes
from `hooks.ts`, as the frontend conventions require.

**Owned paths:**
- `frontend/src/features/cases/tickets-*.ts(x)` and tests,
  `frontend/src/components/cases/ActionsPanel.tsx` (the control only),
  `frontend/src/messages/cases/{en,sv}.json` (own keys)

**Done when:**
- Export, re-export (which creates nothing), the no-tracker state and the provider
  refusal all render in both languages.
- The ticket reference appears on each action and links out.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- Idempotency keys belong to `hooks.ts`; the client never invents a second one.

### c13-fe-source-requests: asking for a source

**Requirements:** WAT-06
**Scenarios:** none (WAT-S8's journey is `c13-e2e-private`'s)
**Depends on:** `c13-private-sources`, `c5-fe-watch-feed`, `c13-cards-source-requests`

Build the request form on the watch screen (key `watchfe`, first of the two tasks
that hold it): the address field with the checks stated before submission, the
private-or-shared choice, the cap message and the refusal messages rendered from
their `code`. The list of requests is `c13-fe-source-list`'s.

**Owned paths:**
- `frontend/src/features/watch/source-requests-*.ts(x)` and tests,
  `frontend/src/components/watch/SourceRequestPanel.tsx`,
  `frontend/src/messages/watch/{en,sv}.json` (own keys)

**Done when:**
- Requesting, the six refusal codes, the cap and both visibility choices render in
  both languages with every state.
- The checks are stated before submission, in the card's words, and the form refuses
  nothing the server would accept.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- No string literal in JSX; errors branch on `code`.

### c13-fe-source-list: the request list and the private marker

**Requirements:** WAT-06, INV-07
**Scenarios:** none (WAT-S8's journey is `c13-e2e-private`'s)
**Depends on:** `c13-fe-source-requests`, `c13-private-source-visibility`

Add the request list beside the form (key `watchfe`, after `c13-fe-source-requests`):
the rows with their status pills by kind, the "waiting for approval of the agent
runner" state in the words the card draws, and the "Private to us" marker — the one
`c13-cards-tenant-private` defines — on the request, on the source and on any change
registered from it. A shared request shows its console decision when it has one.

**Owned paths:**
- `frontend/src/features/watch/source-list-*.ts(x)` and tests,
  `frontend/src/components/watch/SourceRequestList.tsx`,
  `frontend/src/features/shared/tone-by-kind.ts` (its own entries),
  `frontend/src/messages/watch/{en,sv}.json` (own keys)

**Done when:**
- The list, every status, the waiting state and the empty state render in both
  languages against the real API.
- The private marker appears on the request, the source and any change from it, from
  one presentation function rather than from three call sites.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- Pills through `Pill`, by kind; no string literal in JSX.

### c13-fe-console-source-requests: the shared queue in the console

**Requirements:** WAT-06, ADM-02
**Scenarios:** none
**Depends on:** `c13-private-source-visibility`, `c5-fe-console-sources`, `c4-console-shell`, `c13-cards-source-requests`

Add the shared source-request queue to the console sources screen: the list with the
organisation's name, the address, the reason and the decision controls, approve
creating the shared source through the path `c5-watch-sources-coverage` already
serves, decline needing a reason. A private request is not in the list, and a direct
fetch of one answers 404, which the screen renders as "Not found".

**Owned paths:**
- `frontend/src/features/console/source-requests-*.ts(x)` and tests,
  `frontend/src/components/console/SourceRequestQueue.tsx`,
  `frontend/src/messages/console/{en,sv}.json` (own keys)

**Done when:**
- Approve and decline work against the real API; the queue holds shared requests only.
- A private request's id typed into the URL renders "Not found", never a 403 and never
  a hint that it exists.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- A tenant's private rows never appear on a platform surface.

### c13-fe-private-proposals: the bank proposes and approves its own records

**Requirements:** INV-07, PRO-03
**Scenarios:** none (the journey is `c13-e2e-private-obligation`'s)
**Depends on:** `c13-private-approval`, `c13-private-obligations`, `c13-cards-tenant-private`

Build the tenant's private-proposal surface (key `propfe`,
`frontend/src/features/private-proposals/`), the screen INV-07 had no owner for: the
list of the bank's own private proposals, the two propose forms, the reviewer's
Approve with its step-up prompt and Reject with a reason from the vocabulary, the 409
`four_eyes_violation` rendered as the plain sentence the card draws, and the 422
`private_provisions_not_supported` message. The resulting record carries the "Private
to us" marker. Every string is in the catalog and every pill comes through `Pill` from
the proposal's state. The screen is reachable from the inventory under
`private_records.approve` or `proposals.create`, which is what `c13-close`'s
reachability audit looks for when it asks whether `approvePrivateProposal` can be
reached from a screen.

**Owned paths:**
- `frontend/src/features/private-proposals/` (`api.ts`, `hooks.ts`,
  `private-proposals-presentation.ts`) and tests,
  `frontend/src/app/(tenant)/private-records/page.tsx`,
  `frontend/src/components/inventory/PrivateProposalsPanel.tsx`,
  `frontend/src/messages/private-proposals/{en,sv}.json`,
  `frontend/src/shared/navigation/registry.ts` (one entry),
  `frontend/src/features/shared/tone-by-kind.ts` (its own entries)

**Done when:**
- Propose, list, approve with the step-up and reject with a reason all work against
  the real API in both languages, with empty, loading, error and denied states.
- The four-eyes 409 and the provisions 422 render from their `code`, never from a
  `detail`.
- The nav entry appears only with the permission, and `approvePrivateProposal` is
  reachable from a screen a permitted role can open.
- The frontend gate set passes and the navigation snapshot is regenerated by the main
  agent at merge.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- Step-up is prompted where the server demands it; the client never decides it alone.
- A private record's screen is a tenant screen; nothing about it reaches the console.

### c13-fe-sso: the SSO admin panels

**Requirements:** ID-12, ADM-01
**Scenarios:** none (ID-S27's journey is `c13-e2e-identity-admin`'s)
**Depends on:** `c13-scim-users`, `c13-sso-enforcement`, `c13-cards-admin-security`, `c13-fe-allowlist`

Build the provider, domains, enforcement and SCIM panels on the admin Security screen
(key `secfe`, after `c13-fe-allowlist`): the provider form with Test connection, the
domain list with the TXT record and Verify, the enforcement switch that first shows
how many members are not yet linked and renders the 409 when the admin has not done
their own round trip, the SCIM key shown once, the default-role picker with the four
refused permissions named, and the "outside SSO" marker on the member list. Nothing
here offers SSO as a way to sign in.

**Owned paths:**
- `frontend/src/features/security/sso-*.ts(x)` and tests,
  `frontend/src/components/admin/SsoPanel.tsx`,
  `frontend/src/components/admin/MemberDetailScreen.tsx` (the marker only),
  `frontend/src/messages/security/{en,sv}.json` (own keys)

**Done when:**
- Every panel works against the real API in both languages with all its states.
- The enforcement switch cannot be flipped without the round trip, and the count is
  shown before the switch.
- The SCIM key is shown once and never listed.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- A passkey is the only way in; no screen offers a provider-first sign-in.

### c13-fe-sso-signin: the continuation after the passkey

**Requirements:** ID-12
**Scenarios:** none (ID-S27's journey is `c13-e2e-identity-admin`'s)
**Depends on:** `c13-sso-enforcement`, `c13-fe-sso`

Add the continuation to the sign-in and enrolment screens (key `secfe`, after
`c13-fe-sso`): after a successful passkey, when the API answers `next: idp`, the
screen says the organisation's provider will be asked, posts the challenge, and
handles the return; on refusal it shows what the server said, by `code`, and offers
to start again. At enrolment on a verified domain the screen asks the provider
instead of showing the code field, and the code field is not rendered at all. The
sign-in screen gains no provider button.

**Owned paths:**
- `frontend/src/features/security/signin-continuation-*.ts(x)` and tests,
  `frontend/src/app/(tenant)/auth/*` (the continuation branch only),
  `frontend/src/messages/auth/{en,sv}.json` (own keys)

**Done when:**
- The continuation, the refusal and the enrolment variant render in both languages.
- A test proves the sign-in screen renders no control that starts at the provider.
- Nothing stores a token or a cookie the client can read.

**Gates:** as `c13-fe-follow`.

**Invariants:**
- No passwords; the passkey first, always.
- Tokens live in memory and in HttpOnly cookies, never in client storage.

### c13-e2e-follow: following a record, end to end

**Requirements:** COL-03
**Scenarios:** COL-S4 (`@e2e`, un-fixmed)
**Depends on:** `c13-follow-notify`, `c13-fe-follow`, `c10-fe-notifications`, `c4-fe-approve`

One journey against the real stack: a seeded member signs in with a passkey, follows
a seeded obligation, a library editor approves a proposal that writes a new version
of it (the chunk 4 journey's own path), the follower opens their notifications and
finds one entry, unfollows, a second version lands and no new notification appears.
`seed_e2e` gains nothing beyond one follow-capable member; the clock is anchored.

**Owned paths:**
- `frontend/tests/e2e/collab.journey.spec.ts` (the COL-S4 block only),
  `backend/apps/shared/e2e_seed.py` (one seed call)

**Done when:**
- The journey is green twice in a row against `npm run test:e2e`, with no API
  response mocked and no token injected.
- The api-guard declares every expected error where it happens, or none is expected.
- `backend/apps/collab/app.md`'s COL-S4 status cell is updated.

**Gates:**
- `bash scripts/cloud-setup.sh --e2e` (or the slot's E2E database locally)
- `cd frontend && npm run test:e2e -- --grep "COL-S4"`, then `bash scripts/prepush.sh --quick`

**Invariants:**
- Sign-in through the UI with the virtual authenticator; the seed is extended, never
  mocked.

### c13-e2e-saved-searches: saving a search and being told about a hit

**Requirements:** SRC-04
**Scenarios:** SRC-S7 (`@e2e`, un-fixmed)
**Depends on:** `c13-saved-search-notify`, `c13-fe-saved-searches`, `c10-fe-notifications`, `c4-fe-approve`

One journey: search for a seeded term, save it with notifications on, have a library
editor approve a proposal that creates a matching obligation, find the notification
in the reader's own language, open the saved search and see the hit marked new, then
reopen and see it unmarked.

**Owned paths:**
- `frontend/tests/e2e/search.journey.spec.ts` (the SRC-S7 block only),
  `backend/apps/shared/e2e_seed.py` (one seed call)

**Done when:**
- The journey is green twice in a row, in the pinned language, with the marker
  appearing and then clearing.
- `backend/apps/search/app.md`'s SRC-S7 status cell is updated.

**Gates:** as `c13-e2e-follow`, with `--grep "SRC-S7"`.

**Invariants:**
- No mocked API; the real search runs against the seeded index.

### c13-e2e-register: attesting and waiving

**Requirements:** REG-06
**Scenarios:** REG-S9 (`@e2e`, un-fixmed)
**Depends on:** `c13-fe-waive`, `c13-fe-attest`

One journey: the owner opens an obligation seeded as attested 13 months ago, sees it
due, attests it with a statement, and the roadmap shows the next date; an approver
grants a waiver on a seeded gap with a step-up and an expiry, the gap shows it, and a
second seeded waiver already past its date shows the gap open again.

**Owned paths:**
- `frontend/tests/e2e/register.journey.spec.ts` (the REG-S9 block only),
  `backend/apps/shared/e2e_seed.py` (one seed call: the dated attestation and the two
  waivers, all anchored)

**Done when:**
- The journey is green twice in a row; every date in the seed derives from the anchor,
  so it cannot pass in September and fail in October.
- `backend/apps/register/app.md`'s REG-S9 status cell is updated.

**Gates:** as `c13-e2e-follow`, with `--grep "REG-S9"`.

**Invariants:**
- Clocks anchored to the tenant-local date plus a fixed wall time.

### c13-e2e-private: a private source stays in the bank

**Requirements:** WAT-06, INV-07
**Scenarios:** WAT-S8 (`@e2e`, un-fixmed)
**Depends on:** `c13-private-source-visibility`, `c13-fe-source-list`, `c13-fe-console-source-requests`

One journey: tenant A's compliance officer requests a private source, sees the checks
refuse a bad address, then registers a good one; a seeded private change from it
appears in A's feed; tenant B signs in, opens the change's URL and gets "Not found";
a library editor opens the console sources queue and the private request is not there.

**Owned paths:**
- `frontend/tests/e2e/watch.journey.spec.ts` (the WAT-S8 block only),
  `backend/apps/shared/e2e_seed.py` (one seed call)

**Done when:**
- The journey is green twice in a row, with the 404s declared in the api-guard where
  they happen.
- The console step proves the absence of the private request by an exact-text
  assertion, not by a screenshot.
- `watch/app.md`'s WAT-S8 cells are updated.

**Gates:** as `c13-e2e-follow`, with `--grep "WAT-S8"`.

**Invariants:**
- Tenant B sees 404, never 403 and never the data.
- No API mocked; the private-source run is the seeded double, not a stub.

### c13-e2e-private-obligation: the bank's own obligation, proposed and approved

**Requirements:** INV-07
**Scenarios:** none (INV-S9, INV-S13 and PRO-S12 are `@integration`; this journey
proves the same path through the UI)
**Depends on:** `c13-private-obligations`, `c13-private-no-ai-index`, `c13-fe-private-proposals`

One journey: tenant A's compliance officer proposes a private obligation, approves
their own and is refused, a second person in A approves with a step-up, the obligation
appears in A's inventory marked "Private to us", and a search for its text returns
nothing.

**Owned paths:**
- `frontend/tests/e2e/library.journey.spec.ts` (the private block only),
  `backend/apps/shared/e2e_seed.py`, `e2e_logins.py` and
  `frontend/tests/e2e/support/passkeys.ts` (one seed call and one login: a second
  approver in tenant A)

**Done when:**
- The journey is green twice in a row, with the four-eyes 409 declared in the
  api-guard where it happens.
- The step-up is a real passkey assertion through the virtual authenticator, never an
  injected token.
- The empty search result is asserted by exact text, not by an empty screenshot.
- `library/app.md`'s status cells are updated.

**Gates:** as `c13-e2e-follow`, with `--grep "private obligation"`.

**Invariants:**
- Four eyes hold through the UI, not only in a unit test.
- No private text is indexed; the search proves it from the outside.

### c13-e2e-integrations-webhooks: a signed delivery and a stream

**Requirements:** INT-01, INT-03
**Scenarios:** INT-S1 (`@e2e`, un-fixmed), INT-S4 (`@e2e`, un-fixmed)
**Depends on:** `c13-webhook-retries`, `c13-siem-stream`, `c13-fe-integrations-connections`

Build the receiver double (rule 15): an `E2E_MODE`-only endpoint in the backend that
records what it receives and can be told to answer 500 once, with its production
refusal test. Then the journeys: an admin creates a webhook, copies the secret once,
a case is closed in the UI, the delivery log shows the attempt with its status and
duration, the receiver verified the signature, and the body carries no title or
summary; the admin then connects the SIEM endpoint and the screen shows the lag
falling as the stream catches up.

**Owned paths:**
- `backend/apps/integrations/e2e_receiver.py` and its guard test,
  `backend/config/api.py` (the E2E-only mount),
  `frontend/tests/e2e/integrations.journey.spec.ts` (the INT-S1 and INT-S4 blocks),
  `backend/apps/shared/e2e_seed.py` (one seed call)

**Done when:**
- Both journeys are green twice in a row against the real stack.
- The receiver refuses to load with `E2E_MODE` off, proved by a test.
- The journey asserts the received body's exact key set (ruling 1).
- `integrations/app.md` status cells are updated.

**Gates:** as `c13-e2e-follow`, with `--grep "INT-S1|INT-S4"`.

**Invariants:**
- A double is a real endpoint that cannot exist in production; nothing is mocked.

### c13-e2e-integrations-tickets: actions become tickets

**Requirements:** INT-02
**Scenarios:** INT-S3 (`@e2e`, un-fixmed)
**Depends on:** `c13-tickets-jira`, `c13-fe-tickets-screen`, `c13-e2e-integrations-webhooks`

One journey against the tracker double: an admin connects the tracker, an owner opens
a case with three actions and chooses "Send as tickets", three references appear,
choosing it again creates nothing, the double closes one ticket and posts its signed
callback, and the action's status follows.

**Owned paths:**
- `frontend/tests/e2e/integrations.journey.spec.ts` (the INT-S3 block only),
  `backend/apps/shared/e2e_seed.py` (one seed call)

**Done when:**
- The journey is green twice in a row, including the second export creating nothing.
- The callback is signed by the double and verified by the app; no signature is
  bypassed for the test.
- `integrations/app.md`'s INT-S3 cells are updated.

**Gates:** as `c13-e2e-follow`, with `--grep "INT-S3"`.

**Invariants:**
- Idempotency proved through the UI, not only in a unit test.

### c13-e2e-identity-admin: the allow-list and SSO, end to end

**Requirements:** ID-12, ID-13
**Scenarios:** ID-S24 and ID-S27 gain `@e2e` here, and both journeys are written
**Depends on:** `c13-fe-allowlist`, `c13-ip-allowlist-enforcement`, `c13-fe-sso-signin`, `c13-sso-test-idp`

Two journeys. **One:** an admin adds one address to the allow-list, a second member
signs in from an address outside it and is refused with the plain message, the
security log shows the refusal, and removing the list restores access. **Two:** the
admin verifies a domain against the test provider, sees how many members are
unlinked, switches enforcement on with a step-up and their own provider round trip,
then a member signs in: passkey first, provider second, session third; and a forged
callback is refused. Both use the test identity provider, never a mock.

**The address a browser appears to come from.** Every Playwright request reaches the
backend from the same loopback socket, so "an address outside the list" cannot be
produced by the browser alone. The E2E stack therefore boots with
`TRUSTED_PROXY_HOPS=1`, exported by `tests/e2e/support/start-backend.sh` beside
`E2E_MODE`, which is exactly the shape the deployed app runs in behind our edge:
`client_ip()` then reads the rightmost hop of `X-Forwarded-For` and falls back to the
socket address when the header is absent, so every other journey is unchanged. This
journey opens its second member's browser context with
`extraHTTPHeaders: { 'X-Forwarded-For': '<an address outside the list>' }`, and the
admin's own context with the address it just allowed. Nothing is mocked and no guard
is relaxed: the middleware runs its real check over a real proxied request. The task
also pins, in `tests_middleware.py`'s existing suite, that a header with more entries
than the hop count still resolves to the hop our edge appended.

**Owned paths:**
- `backend/apps/identity/app.md` (the `@e2e` tag on the two headings only),
- `frontend/tests/e2e/identity.journey.spec.ts` (the ID-S24 and ID-S27 blocks, which
  this task writes: neither exists on `main`),
  `frontend/tests/e2e/support/start-backend.sh` (the one exported variable),
  `backend/apps/shared/e2e_seed.py`, `e2e_logins.py` and
  `frontend/tests/e2e/support/passkeys.ts` (one seed call and one login)

**Done when:**
- Both journeys are green twice in a row, with the 403 `ip_not_allowed` declared in
  the api-guard where it happens.
- A journey that sends no `X-Forwarded-For` still signs in, proving the hop setting
  broke nothing; the whole suite is run once to show it.
- The teardown restores the seeded allow-list and enforcement state even on failure,
  so a later journey is not locked out.
- `identity/app.md`'s ID-S24 and ID-S27 cells are updated.

**Gates:** as `c13-e2e-follow`, with `--grep "ID-S24|ID-S27"`.

**Invariants:**
- Sign-in through the UI with a passkey; SSO never opens the session alone.
- Teardown restores seeded data on failure too.

### c13-i18n-da: the Danish catalogs

**Requirements:** I18N-02
**Scenarios:** none (I18N-S3 and I18N-S4 are `c13-i18n-wiring`'s)
**Depends on:** every R2 and R3 screen package (the catalog freeze), `x-frontend-split`

Add `da.json` beside `en.json` and `sv.json` in every namespace directory, with every
key translated and the same placeholders. No component, screen or copy changes, and
`messages.ts` is not touched (that is `c13-i18n-wiring`'s), so this task runs beside
its two siblings. Plural rules and placeholder names are checked by
`check:messages` once the language is wired; until then the task runs the checker in
the mode that compares a candidate file against `en.json` key by key.

**Owned paths:**
- `frontend/src/messages/*/da.json`

**Done when:**
- Every namespace has a `da.json` with exactly the keys of its `en.json` and the same
  placeholders, proved by the checker.
- No other file changes.
- The native-speaker review is listed for Alex by `c13-close`.

**Gates:**
- `cd frontend && npm run check:messages && npm run typecheck && npm run build`

**Invariants:**
- Every user-facing string lives in a catalog; nothing is translated in code.

### c13-i18n-nb: the Norwegian catalogs

**Requirements:** I18N-02
**Scenarios:** none
**Depends on:** every R2 and R3 screen package (the catalog freeze), `x-frontend-split`

As `c13-i18n-da`, for `nb.json`.

**Owned paths:**
- `frontend/src/messages/*/nb.json`

**Done when:** as `c13-i18n-da`, for nb.

**Gates:** as `c13-i18n-da`.

**Invariants:** as `c13-i18n-da`.

### c13-i18n-fi: the Finnish catalogs

**Requirements:** I18N-02
**Scenarios:** none
**Depends on:** every R2 and R3 screen package (the catalog freeze), `x-frontend-split`

As `c13-i18n-da`, for `fi.json`.

**Owned paths:**
- `frontend/src/messages/*/fi.json`

**Done when:** as `c13-i18n-da`, for fi.

**Gates:** as `c13-i18n-da`.

**Invariants:** as `c13-i18n-da`.

### c13-i18n-wiring: five languages, switchable and gated

**Requirements:** I18N-02
**Scenarios:** I18N-S3 (`@e2e`, un-fixmed), I18N-S4 (`@e2e`, un-fixmed)
**Depends on:** `c13-i18n-da`, `c13-i18n-nb`, `c13-i18n-fi`, `c13-i18n-seed-labels`, `c13-i18n-server`

Turn the three catalogs on: `locales` becomes the five, `localeTags` gains `da-DK`,
`nb-NO` and `fi-FI`, the `LocaleProvider` and the language picker offer them,
`check:messages` fails on a key missing in any of the five, and the formatting helpers
are tested per language, including the partial-date phrase. The E2E suite keeps
running in its one pinned language; I18N-S3's journey switches the UI to one of the
new languages and back.

R1 already built the `en` and `sv` half (wave 1, `i18n-en-sv-switch`), and this task
extends it rather than starting over. The picker is the Language group in the rail's
account menu (`frontend/src/components/shell/AccountMenu.tsx`) and in the More sheet
below 1024 px (`MoreSheet.tsx`), both fed by `useInterfaceLanguages` in
`AccountMenu.tsx`: it offers the language rows (`GET /reference/languages`) whose key is
in `locales`, so the three new ones appear in both once `locales` names them, each in
its own words from its row. `useSetLanguage` (`frontend/src/features/identity/hooks.ts`)
saves the choice with `PATCH /me` and refetches every cached answer. I18N-S3 and I18N-S4
are already real journeys for `sv`: extend I18N-S3 to switch to a new language and back
on its reserved login (`language@example-bank.test`, reserved for I18N-S3), and I18N-S4
to format the same seeded dates in that language. `format.test.ts` pins the Swedish
quarter phrase ("kv. 4 2026"); add the new languages' phrases beside it.

**Owned paths:**
- `frontend/src/shared/i18n/messages.ts`, `LocaleProvider.tsx`, `i18n.test.ts`,
  `frontend/scripts/messages-check.mjs`, the language picker component,
  `frontend/tests/e2e/shared.journey.spec.ts` (the I18N-S3 and I18N-S4 blocks),
  `backend/apps/shared/app.md` (the two status cells)

**Done when:**
- I18N-S3 and I18N-S4 are green; a deliberately removed key in `fi.json` fails
  `check:messages`, proved once and restored.
- Dates, numbers and partial dates format per language, with a unit test each.
- The whole frontend gate set and the full E2E suite pass.

**Gates:**
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "I18N-S3|I18N-S4"`; `bash scripts/prepush.sh --quick`

**Invariants:**
- No gate is lowered to make a language pass; a missing key fails.
- Language is a row and a catalog, never a branch in code.

### c13-security-review-integrations: the outward half, reviewed

**Requirements:** INT-01, INT-02, INT-03, NFR-02
**Scenarios:** none
**Depends on:** `c13-egress-client`, `c13-secret-box`, `c13-int-subscriptions`, `c13-webhook-retries`, `c13-siem-stream`, `c13-tickets-inbound`, `c13-tickets-jira`, `c13-library-change-fanout`

A security-review sub-agent reads the diff of every task above against `main` and
answers, with a test named for each: can any configured address reach inside the
network, directly or through a redirect or a DNS change between calls; can a secret
appear anywhere but its one creation response; can a payload carry a title, summary,
before or after value, a library row or another tenant's row; is every inbound
handler idempotent and its signature compared in constant time; does a delivery ever
run before its transaction commits; can a webhook or stream be created, paused or
deleted without the permission, the step-up or the audit row. The guard suites run
with it: `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`,
`tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`,
`tests_no_secret_in_logs`, `tests_no_query_in_logs`.

**Owned paths:**
- `docs/security/CHUNK13_INTEGRATIONS_REVIEW_2026-09-20.md`
- `docs/plans/briefs/HARDENING.md` (its own rows)

**Done when:**
- The report lists every finding with severity, the file and line, a reproduction and
  a fix, and names what was checked and found clean.
- Nothing critical or high is open: each is either fixed by `c13-review-fixes` before
  the merge of this report or blocks it.
- Findings below high become rows in `HARDENING.md` with an owning package.

**Gates:**
- The guard suites above, plus `bash scripts/prepush.sh --quick`.

**Invariants:**
- A critical or high finding blocks a merge; no finding is closed by rewording it.

### c13-security-review-identity-private: the identity and private half, reviewed

**Requirements:** ID-12, ID-13, INV-07, WAT-06, NFR-02
**Scenarios:** none
**Depends on:** `c13-ip-allowlist`, `c13-sso-enforcement`, `c13-scim-users`, `c13-sso-saml`, `c13-private-no-ai-index`, `c13-private-source-runs`, `c13-private-approval`, `c13-private-child-rls`

The second review, over the identity and private-record diffs: can a session be
opened without a passkey, or a passkey recovered through the provider; is the
enforcement challenge single-use and bound to user, tenant, assertion and browser; can
an unsolicited or replayed assertion do anything; can SCIM escalate a role, remove the
last admin, or reach a scope it was not granted; can the allow-list be turned into a
lock-out or bypassed through a header; can any private row, or a child of one, be read
by another tenant, by the platform, by the index or by a model; is the proposal door
still three routes; does every private approval carry four eyes and a step-up. The
same guard suites run, plus `tests_no_passwords` and `tests_authentication`.

**Owned paths:**
- `docs/security/CHUNK13_IDENTITY_PRIVATE_REVIEW_2026-09-20.md`
- `docs/plans/briefs/HARDENING.md` (its own rows)

**Done when:** as `c13-security-review-integrations`, for this half.

**Gates:** as `c13-security-review-integrations`.

**Invariants:**
- A passkey is the only way in; two zones; one door into the library.

### c13-review-fixes: close the findings

**Requirements:** the requirements of the findings
**Scenarios:** whatever a finding reopens
**Depends on:** `c13-security-review-integrations`, `c13-security-review-identity-private`

Fix every critical, high and medium finding of both reports, re-run the review over
the fix diff, and repeat until nothing at medium or above remains. Each fix keeps its
own test, written first. If a review found nothing at medium or above, the task closes
at once with a note in both reports. Findings below medium become `HARDENING.md` rows
with an owning package, never silent.

**Owned paths:**
- Whatever the findings name, listed in the task's own commit body
- `docs/security/CHUNK13_*_REVIEW_2026-09-20.md` (the closing notes),
  `docs/plans/briefs/HARDENING.md`

**Done when:**
- Both reports show every critical, high and medium finding closed with the commit
  that closed it.
- Every gate the touched areas need is green, and no test was skipped or weakened to
  close a finding.

**Gates:**
- The gates of each area touched, then `bash scripts/prepush.sh --all` once.

**Invariants:**
- No gate is lowered, no test quarantined, to close a finding.

### c13-close: the chunk is done and says what it cut

**Requirements:** every chunk 13 requirement
**Scenarios:** every chunk 13 scenario
**Depends on:** `c13-e2e-integrations-webhooks`, `c13-e2e-integrations-tickets`, `c13-e2e-identity-admin`, `c13-e2e-saved-searches`, `c13-e2e-follow`, `c13-e2e-register`, `c13-e2e-private`, `c13-e2e-private-obligation`, `c13-i18n-wiring`, `c13-review-fixes`, `c13-i18n-server`

Close the chunk: prove no chunk 13 route answers 501 and no chunk 13 journey is
`fixme`; set the coverage floors for `apps/integrations`, the new identity modules,
`apps/watch/source_requests.py` and the register additions, measured at the close with
the date beside each; move every chunk 13 `app.md` status cell to `built`, or to
`in_progress` with the named reason (WAT-06 if open question 1 is unanswered, ID-12 if
SAML was cut); update `IMPLEMENTATION_STATUS.md`'s chunk 13 row and the UI plan's
status cells; write the four non-blocking confirmations, open question 1, the Jira and
identity-provider sandbox checks, the `INTEGRATION_SECRET_KEYS` operator step and the
native-speaker review of da, nb and fi into `docs/TODO_FOR_alex.md`; and run the whole
suite once.

**Owned paths:**
- `docs/plans/IMPLEMENTATION_STATUS.md`, `docs/TODO_FOR_alex.md`,
  `docs/plans/UI_Implementation_Plan.md` (status cells),
  `backend/scripts/coverage_gate.py` (the chunk 13 floors),
  every chunk 13 `app.md` status cell

**Done when:**
- `python backend/scripts/requirements_coverage.py` shows every chunk 13 requirement
  with a built scenario or a named reason.
- The UI plan's reachability audit (playbook 7.6) is re-run: every chunk 13 operation
  is reachable from a screen a permitted role can open, and ADM-S1's journey is green
  with the two new nav entries in place.
- `bash scripts/prepush.sh --all` and the full `npm run test:e2e` are green on the
  close commit.
- No route answers 501 and no journey is `fixme` for this chunk, each proved by a
  test rather than by reading.
- What was cut is named here, in the commit body and in the status file.

**Gates:**
- `bash scripts/prepush.sh --all`; `cd frontend && npm run test:e2e`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**
- A status cell moves only when the commit that earns it is on `main`.
- What was cut is written down, never quietly dropped.

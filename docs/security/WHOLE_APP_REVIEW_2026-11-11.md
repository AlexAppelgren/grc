# Whole-application security review (2026-11-11), closed

The review covered the backend, the web app, the configuration and the delivery chain against
the OWASP Top 10 (2021), the OWASP API Security Top 10 (2023) and the OWASP Top 10 for LLM
applications (2025). It found 15 findings of high or medium severity and 18 of low severity.
Every finding is fixed on `main`; each fix has a regression test whose docstring names the
finding ID. The simplification half of the same review is
`docs/reviews/SIMPLIFICATION_REVIEW_2026-11-11.md`.

## High and medium

| ID | Severity | Finding | Fix | Commit |
|---|---|---|---|---|
| S-1 | High | An enrolment session could still register a passkey after the first passkey existed or the invitation was revoked | Registration checks the account's passkeys and the invitation inside the same transaction | 29bb706 |
| S-2 | High | A bank administrator's re-enrolment reached the account's other banks and the console | Re-enrolment acts in the administrator's bank only; an account held elsewhere answers `account_held_elsewhere` (409) | 29bb706 |
| S-3 | Medium | The confirming agent could approve a library proposal a bank member filed | An agent confirms only a platform proposal, filed by a platform key under an open run | abe9420 |
| S-4 | Medium | Invitations that grant roles, member removal and bank creation had no passkey step-up | Step-up on all three; the step-up-less member delete route is gone | 29bb706 |
| S-5 | Medium | The sole-approver test (D-125) read state the requester could change | The requester's sole-approver state is fixed when the request is filed (taxonomy migration 0015) | 7a5be17 |
| S-6 | Medium | One person could be both sides of a library approval through an agent key | The confirmer's key and the proposer's key must have been created by different people | abe9420 |
| S-7 | Medium | The EU-only processor guard of D-54 was not built | Boot rule 10 refuses a non-EU model provider and the managed agents runner on a deployed environment | 61834d7, ee6559d |
| S-8 | Medium | Outbound URLs reached Sentry and trace headers reached fetched hosts | Sentry gets no outbound URLs or trace propagation, and only an EU ingest host is accepted | 61834d7 |
| S-9 | Medium | A model call that failed after it was sent was neither logged nor counted | The call is logged and counted against the bank's cap | c2344fc |
| S-10 | Medium | `check_url` fetched under the spend lock with no rate limit | One fetch at a time per bank, rate-limited by `RESEARCH_URL_RATE_PER_HOUR`, outside the lock | f8e0972 |
| S-11 | Medium | Register lookups had no per-bank limit and ran past the job deadline | One lookup at a time, `REGISTERS_LOOKUPS_PER_HOUR`, the deadline checked page by page | 4c3aa0d |
| S-12 | Medium | The web app's Content-Security-Policy had only `frame-ancestors` | A full policy: the app's own files and the API only | 87ac7b4 |
| S-13 | Medium | The API process kept the schema owner's credential | The entrypoint removes `MIGRATOR_DATABASE_URL` after the migration | 1caa6d3 |
| S-14 | Medium | An unset `ENVIRONMENT` switched the boot guards off | The image sets `ENVIRONMENT=production`; the runbook says so | 1caa6d3 |
| S-15 | Medium | `bootstrap_platform` granted the strongest platform role by default | The role is asked for explicitly and confirmed; a command revokes it | 29bb706 |

## Low

| ID | Finding | Fix | Commit |
|---|---|---|---|
| L-1 | "Approve all" continued after its reviewer lost the permission | Re-reads the grant and the account every batch | ed5232a |
| L-2 | An invitation showed an existing account's name and id in the inviting bank's audit | The mailbox name only, the id after acceptance | 29bb706 |
| L-3 | "First time here?" enrolled into the bank that invited last | The re-enrolment or platform invitation comes first | 29bb706 |
| L-4 | Sign-out and refresh had no rate limit | They share the per-IP auth bucket | 29bb706 |
| L-5 | Refresh cookie without a prefix, no `Origin` check, HSTS without subdomains | `__Secure-cw_refresh`, `origin_refused` (403), `includeSubDomains` | 29bb706, 87ac7b4 |
| L-6 | Three read-then-write sequences in sessions and membership had no lock | Row locks or a conditional update | 29bb706 |
| L-7 | The database role guard missed role membership | `pg_has_role` and `rolcreaterole` are checked | 6550f12 |
| L-8 | `/health/` said too much and pinged Celery on every call | Status only, cached for `HEALTH_CACHE_SECONDS` | fe54e16 |
| L-9 | Developer pages shipped in production | Served only with `E2E_DEV_PAGES` | 87ac7b4 |
| L-10 | The CI image tier named the wrong entrypoint file | Corrected in CI and the pre-push script | 5a12f31 |
| L-11 | An expired advisory exception, and a gate that accepted one with no expiry | Entry deleted; `osv_ignores_gate.py` refuses an entry without `ignoreUntil` | 66d023a |
| L-12 | Floating base images and MCP package | Pinned by digest and version; Dependabot covers Docker | 97ecc25 |
| L-13 | Local Postgres and Redis listened on every interface | Bound to `127.0.0.1` | 97ecc25 |
| L-14 | One link from API data skipped `externalHref` | Uses the guard | 87ac7b4 |
| L-15 | A page declaring `charset=idna` made `check_url` answer 500 | The decode error is handled | f8e0972 |
| L-16 | Most integer settings had no boot-time bound | Every numeric setting has bounds and refuses to boot outside them | 7808fa7 |
| L-17 | One API key path wrote no security-log row | One mint and one revoke path, each logged | c3f6acf |
| L-18 | `TRUSTED_PROXY_HOPS` could be 0 behind the edge | Defaults to 1 when deployed; 0 is refused | 1caa6d3 |

## What the owner sets before the next deploy

- `LLM_PROVIDER=bedrock` and `AGENT_RUNNER=none` on every deployed environment except `test`
  (S-7). Bedrock is the EU path of D-54 and is not built yet.
- The sweeper's and the confirmer's agent keys are created by two different people (S-6).
- Pending regulatory scope requests are refiled if their requester should approve them alone (S-5).
- The settings `HEALTH_CACHE_SECONDS`, `E2E_DEV_PAGES`, `RESEARCH_URL_RATE_PER_HOUR` and
  `REGISTERS_LOOKUPS_PER_HOUR` have defaults; `.env.example` and
  `docs/runbooks/RAILWAY_VARIABLES.md` list them.

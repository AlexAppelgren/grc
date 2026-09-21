# Compliance Watch playbook

**What this is.** The engineering playbook for Compliance Watch (brand: bleqq), a
compliance inventory and regulatory watch platform for enterprise banks in the
Nordics. It started as the Eden OS playbook and keeps everything that made that
repo good: gates that block, tests against the real thing, structural guards,
the document chain, whole slices. Everything specific to a booking and payments
product has been replaced with what this product needs: two data zones,
passkey-only sign-in, admin-owned vocabularies, research agents, five
languages and an assurance track for bank customers.

**How to use it.**

1. This file lives at `docs/PLAYBOOK.md`. The PRD is `PRD.md` at the repo root,
   the design is under `design/`, and earlier design work is under
   `docs/inputs/`.
2. **Precedence** when two sources disagree: `PRD.md`, then
   `docs/DECISIONS.md` and the ADRs, then `docs/inputs/INPUT_DELTAS.md`, then
   the other files in `docs/inputs/`, then this playbook's conventions. The
   prototype in `design/` decides how things look, read and flow. It never
   decides what the rules are.
3. Run Phase 0, then work through `docs/plans/Build_Plan.md` chunk by chunk.
4. After Phase 0 the repo has its full `CLAUDE.md` and `docs/CONVENTIONS.md`
   (generated from Appendix A and the sections below), and this file becomes
   the reference they point back to.

| Setting | Value |
|---|---|
| `<Project>` | Compliance Watch. The display name comes from the `PRODUCT_NAME` setting, so a rebrand is a variable |
| `<PRD>` | `PRD.md`, with a version log at the top |
| `<design>` | `design/` (prototype, system cards, brand) |
| Tenancy | Multi-tenant with two zones, library and tenant (Section 14) |
| Languages | `en`, `sv`, `da`, `nb`, `fi` for content. The UI ships `en` and `sv` first (Section 17) |
| Jurisdictions | EU, SE, DK, NO, FI, as data |
| Default tenant timezone | `Europe/Stockholm`. Storage is always UTC |
| `<privacy law>` | GDPR |
| Data region | EU only. Railway EU West |
| `<host>` | Railway. The environment is named by `RAILWAY_ENVIRONMENT_NAME` |
| RP ID | `WEBAUTHN_RP_ID`, the exact app host per environment (DECISIONS D-02) |
| LLM, embedder, agent runner | One adapter each, chosen by a setting, mock by default (Section 16) |
| Money | Only in billing, where it is an integer minor unit |
| `<owner>` | Alex, who approves product-invariant changes and deploys |

---

## 1. The principles that made the last repo good

These are the reasons it worked. Everything after this section is how.

- **The PRD is the source of truth and every artefact points back to it.**
  Requirements carry IDs (`CAS-04`, `ID-03`, `VOC-02`). Those IDs appear in
  each app's spec, in test names, in commit bodies and in code comments. They
  never appear on screen. On any conflict the PRD wins, and the PRD is
  versioned, so a founder decision becomes a PRD bump before it becomes code.
- **Every gate blocks, and every gate can fail.** Nothing in CI is advisory,
  nothing is `continue-on-error`. A control that reports green while doing
  nothing is worse than no control: the last repo found a CVE scanner that had
  audited an empty file for months, a SAST job whose upload 403'd behind
  `continue-on-error`, and a paths filter whose negation matched every file.
  Prove each gate fails once before trusting it.
- **Tests drive the real thing.** E2E logs in through the UI against a real
  backend seeded with a deterministic, realistic dataset. No mocked fetch, no
  injected tokens. A journey also fails on any undeclared 4xx/5xx or page
  exception, because a suite that only asserts the happy path proved nothing
  when a button 403'd on every click.
- **Slow is a bug.** API under 250 ms, screen under 500 ms to real data.
  Search, Ask, exports and agent runs carry their own budgets (Section 10).
  Measured, not felt. The API stamps its own server time on every response.
- **Write it down where the next person will trip on it.** A rule lives as a
  code comment beside the thing it governs, a docstring on the guard test that
  enforces it, or a dated review document. Comments explain *why*, name the
  incident, and carry the measurement. The repo's comments read like a
  logbook, and that is what made it navigable.
- **Invariants over features.** Two zones under row-level security,
  proposals as the only door into the library, versions never overwritten,
  an audit row with every write, four eyes, no passwords, AI output labelled
  and logged. These are not features to schedule. They are the floor.
- **The design is a contract too.** The prototype's flow, its labels and its
  pill system are reproduced, not reinterpreted (Sections 6.7 and 7).
- **Configuration, never branching.** A status, type or tag is a row an admin
  manages, a threshold is a setting, a role is a set of permissions in the
  database. Code branches on kinds and grants, never on names (Section 15).
- **Deliver whole slices.** A feature is done when the requirement's status is
  updated, its scenarios are un-skipped and green, the types are regenerated,
  the screen renders real data with empty/loading/error/denied states, and its
  E2E journey runs. Half-built work is written up, never quietly left.

---

## 2. Phase 0: bootstrap (day one, before any feature)

Run every item. The order matters because each later item depends on an
earlier one. Do not start Phase 1 until the pre-push checklist (Appendix D)
passes on an empty app.

### 2.1 Repo shape

```
<Project>/
├── PRD.md                   # the requirements, versioned, at the root
├── CLAUDE.md                # agent context (Appendix A)
├── README.md                # quick start + links, nothing else
├── .mcp.json                # Green Design System MCP for token and component lookups
├── design/                  # prototype/, system/ (cards), brand/ (logo)
├── docs/
│   ├── PLAYBOOK.md          # this file
│   ├── CONVENTIONS.md       # architecture and conventions (Sections 4 to 18)
│   ├── DECISIONS.md         # open decisions with the default the build uses
│   ├── inputs/              # earlier design work: openapi.yaml, schema.sql, data-model.md, INPUT_DELTAS.md
│   ├── adr/                 # decisions, numbered (Appendix C)
│   ├── plans/               # solution design, backlog, build plan, status, verification log
│   ├── reviews/             # dated audits: coverage, CI failures, flows
│   ├── runbooks/            # first-run setup, Railway deploy, variables, breach response
│   ├── security/            # audit log + the OWASP reference it was written against
│   ├── assurance/           # what a bank's vendor review asks for (Section 18)
│   └── TODO_FOR_alex.md     # everything that needs a person, not an agent
├── backend/                 # Django + Django Ninja, Poetry
│   ├── apps/<app>/          # models, schemas, logic, api, app.md, tests_*
│   ├── apps/shared/         # auth, permissions, tenancy, audit, vocabulary base, storage, adapters, seed, guards
│   ├── agents/              # versioned agent definitions: prompt, tools, skills, evals (the image seeds from them)
│   ├── config/              # settings.py, test_settings.py, urls.py (/api/v1)
│   ├── scripts/             # compliance_check.py, coverage_gate.py, requirements_coverage.py, contract_drift.py, search_eval.py
│   └── run.sh / run.ps1     # Poetry wrapper that unsets VIRTUAL_ENV
├── frontend/                # Next.js + TypeScript + Tailwind + Radix primitives + TanStack Query
│   ├── src/app/             # routes, thin. (tenant) and (console) route groups
│   ├── src/components/      # UI by domain + ui/ (Pill, Row, Chip and the other design primitives)
│   ├── src/features/        # api.ts, hooks.ts, *-presentation.ts per domain
│   ├── src/shared/          # api-client, format, logger, navigation registry, i18n
│   ├── src/messages/        # <namespace>/{en,sv}.json, one file pair per feature namespace
│   ├── src/styles/          # tokens.generated.css (from Green, never edited), brand.css (our override)
│   ├── src/types/api.generated.ts   # generated, never hand-edited
│   ├── tests/e2e/           # Playwright journeys + support/ (api-guard, passkeys, start-backend)
│   └── scripts/             # build-tokens.mjs, copy-drift-check.mjs, messages-check.mjs
├── .github/workflows/       # ci.yml, codeql.yml
├── .github/scripts/         # codeql_gate.py
├── .gitleaks.toml
├── docker-compose.yml       # Postgres 16 with pgvector + Redis, the same engines as production
└── generate-types.sh        # OpenAPI export → normalise → openapi-typescript
```

Apps: `identity`, `tenants`, `taxonomy` (vocabularies and footprint),
`library`, `proposals`, `watch`, `register`, `cases`, `search`, `home`,
`collab`, `agents`, `reports`, `integrations`, `governance` (audit, AI output
log, problem reports), `billing`, and `shared`.

Stack (pin exact versions in Phase 0 and record them in an ADR): Python 3.12,
Django 5.2 LTS, Django Ninja, **PostgreSQL 16 with pgvector everywhere,
including tests and local**, Celery + Redis, `webauthn` (py_webauthn) for
passkeys, Next.js + TypeScript, Tailwind, Radix primitives, TanStack Query,
Vitest, Playwright 1.61 or later (its `browserContext.credentials` virtual
authenticator is what makes passkey journeys possible), Sentry on its EU
region, structured JSON logs with request IDs. There is no SQLite anywhere:
the model depends on row-level security, pgvector, generated `tsvector`
columns, `citext`, `pg_trgm` and triggers.

### 2.2 Backend skeleton

- `config/settings.py` with the **boot guards** from Section 11.1 in place
  from the first commit: deny-by-default deployed-environment detection,
  refuse `DEBUG=True` when deployed, refuse a missing or default `SECRET_KEY`
  outside DEBUG, refuse the E2E flag when deployed, refuse a mock LLM,
  embedder, agent runner or mailer outside the one named test environment,
  and refuse to start when
  the database role is a superuser, owns the tables or has `BYPASSRLS`.
- `config/test_settings.py`: imports everything, then a throwaway Postgres
  database, MD5 hashing for any legacy hasher Django still loads, stripped
  middleware, eager Celery, locmem cache, rate limiting off, a throwaway
  `MEDIA_ROOT`, mock adapters. Every override carries a numbered comment
  saying why.
- `apps/shared/`:
  - `authentication.py` (`SessionAuth` for people, `ApiKeyAuth` for agents
    and integrations, `EnrolmentAuth` for the one session that may only
    register a passkey),
  - `permissions.py` (constants + `@requires_permission`, `@requires_scope`,
    `@requires_step_up`),
  - `tenancy.py` (`activate(tenant_id)` issuing `SET LOCAL`, the `@tenant_task`
    decorator, `TenantModel`, `LibraryModel` and its `library_write()` fence),
  - `audit.py` (`record()`, the only way to write `audit_event` and
    `outbox_event`), `AppendOnlyModel`,
  - `vocabulary.py` (the abstract `Vocabulary` model, generic endpoints),
  - `adapters/` (`llm.py`, `embedder.py`, `agent_runner.py`, `mailer.py`, each
    with a mock),
  - `middleware.py` (request ID, request timing with `Server-Timing`),
    `storage.py`, `health_check.py`, `factories.py`, `e2e_seed.py` + the
    `seed_e2e` management command, and the **structural guard tests** from
    Section 5.
- `scripts/compliance_check.py`, `scripts/coverage_gate.py`,
  `scripts/requirements_coverage.py`, `scripts/contract_drift.py` and
  `scripts/search_eval.py` (Section 9).
- `/health/` that checks DB, cache, worker and the pgvector extension and
  answers 503 with the failing component named.
- `docker-entrypoint.sh` that migrates as the migrator role, runs every
  idempotent reference seed (permissions, system roles, system vocabularies,
  languages, jurisdictions, authorities, agent definitions) and only then
  starts gunicorn as the app role. Each seed line carries a comment saying
  what silently breaks without it. The last repo shipped four reference seeds
  that ran nowhere, and every failure was quiet.

### 2.3 Frontend skeleton

- `shared/utils/api-client.ts`: the single axios instance. Bearer injection,
  request ID, one-flight refresh on 401, cold-load refresh before the first
  request, session-bootstrap paths that never carry a token, `If-Match` on
  writes to versioned records.
- `shared/utils/format.ts` (`formatDate`, `formatDateTime`, `formatPartialDate`
  in the tenant or user timezone) and `shared/utils/logger.ts`
  (production-silent except errors, never PII, never tenant content).
- `shared/i18n/` and `messages/<lang>.json`. No user-facing string lives in a
  component.
- `shared/navigation/registry.ts` (pure TypeScript, permission-gated
  destinations for the tenant app and the platform console) and
  `require-permission.tsx` (client gate + the Restricted screen that also
  renders the server's structured 403).
- `styles/tokens.generated.css`, written by `scripts/build-tokens.mjs` from
  `@sebgroup/green-tokens` (2023 theme: light under `:root`, dark under
  `.dark`) and never edited by hand, plus `styles/brand.css`, the one file
  that overrides the `brand-01` and `brand-02` variables with our own green and
  sand. `tailwind.config.ts` maps semantic colour names to those variables
  and carries the **named type scale** (Section 6.4) replacing the numbered
  one.
- `components/ui/Pill.tsx` and the other design primitives from the prototype
  (Section 6.7), before any screen.
- `eslint.config.js` with the rules that have teeth: no legacy font sizes, no
  `console.log`, no raw pill markup outside `Pill`, no string literal in JSX
  text, and E2E specs must import `test` from `tests/e2e/support/api-guard`.
- `vitest.config.ts` with coverage thresholds per directory, and
  `playwright.config.ts` whose `webServer` boots the real backend and a
  **production** Next build (`next dev` compiles routes on first request and
  hands specs un-hydrated HTML; measured in the last repo: 3 to 6 minutes
  with retries under `next dev`, 35 seconds and zero flakes under
  `next start`).

### 2.4 CI from the first commit

`ci.yml` with every gate in Section 9, tiered, with a timeout on every job and
a `pgvector/pgvector:pg16` service container. `codeql.yml` with its own SARIF
gate. `.gitleaks.toml` extending the default ruleset. `dependabot.yml` grouped
weekly per ecosystem targeting `main`. There is one branch during the build
phase (Section 12), so there is no branch guard yet.

### 2.5 The document chain

Create these before Phase 1, from the PRD:

| Document | What it holds | Who updates it |
|---|---|---|
| `<PRD>` | Requirements with IDs, acceptance criteria, permissions matrix, release plan, a version log at the top that records each founder decision | The owner (agent drafts the bump, owner approves) |
| `docs/plans/Solution_Design.md` | Architecture, monorepo layout, the domain model per app, the key mechanics agents implement against (tenancy, proposals, case workflow, vocabularies, search, auth), API surface, background jobs, control mapping (where each engineering standard physically lives) | Agent, at each architectural change |
| `docs/plans/Implementation_Backlog.md` | Tasks `T-<REQ>-<n>`, each with Gherkin scenarios tagged `@REQ:` and `@AC:`; a coverage index | Agent |
| `docs/plans/Build_Plan.md` and `Launch_Plan.md` | Chunks in order, the operative timeline, descope triggers | Owner + agent |
| `docs/plans/IMPLEMENTATION_STATUS.md` | Living ledger of chunks: implemented / tested / verified, with definitions of each word. Updated at the end of every chunk. Status is the truth of `git log`, not intentions | Agent |
| `docs/plans/Verification_Log.md` | Every externally dependent claim in the PRD checked against sources: corrected, refined, verified, or "needs a person" | Agent, on each PRD bump |
| `docs/TODO_FOR_alex.md` | Vendor accounts, signatures, legal opinions, product decisions. Ordered by what threatens the launch date. Nothing on it is blocked on code | Agent adds, owner clears |
| `docs/runbooks/FIRST_RUN_SETUP.md` | For the owner in front of an empty database: what the deploy seeds, then each step in dependency order with the grant it needs | Agent, as consoles land |
| `docs/reviews/<TOPIC>_<date>.md` | Dated audits with a question, a method, a taxonomy and the changes made | Agent, when asked or when a class of failure repeats |
| `docs/adr/NNNN-*.md` | Decisions with context, options, consequences (Appendix C) | Agent proposes, owner accepts |

`docs/plans/Solution_Design.md`, `Build_Plan.md`, `Verification_Log.md`,
`docs/DECISIONS.md` and `docs/TODO_FOR_alex.md` ship with the kick-off package:
extend them, never regenerate them. The domain model starts from
`docs/inputs/` as corrected by `INPUT_DELTAS.md`, not from a blank page.

Then one `app.md` per Django app (Appendix B), extracted from the PRD module
it implements, with every requirement at status `pending` and every scenario
present as a skipped stub.

---

## 3. From PRD to shipped feature: the workflow

This is the loop. It does not change per feature.

1. **Read `app.md`** for the app. Confirm the requirement, its acceptance
   criteria and scenarios exist. If the PRD covers behaviour the app.md does
   not, add it. If the PRD is silent, propose the scenario and ask.
2. **Schemas** in `schemas.py`: reuse or compose, camelCase, `from_attributes`
   where a model maps to a response. Never `Dict[str, Any]`.
3. **Logic** in `logic.py`: raise `ValidationError` with user-facing text for
   business-rule failures. No `*args`/`**kwargs`. Every threshold from settings.
   Every write goes through `record()` so its audit and outbox rows exist.
4. **Route** in `api.py`: auth class, then `@requires_permission` or
   `@requires_scope`, then `@requires_step_up` where Section 4.2 lists the
   action. No business logic here.
5. **Tests**: one test per scenario ID in `tests_scenarios.py` (docstring
   carries the ID), plus unit tests for the money and policy branches.
   Pin query counts on list endpoints with `assertNumQueries`.
6. **Migrations** if a model changed, and prove the graph applies from zero.
7. **Regenerate types** (`generate-types.sh`) and commit `openapi.json` +
   `api.generated.ts`.
8. **Feature layer** in `frontend/src/features/<domain>/`: `api.ts` (thin
   typed wrappers), `hooks.ts` (TanStack Query with the cache invalidation
   each mutation needs), `*-presentation.ts` (pure functions, unit-tested).
9. **Screen** under `components/<domain>/` and a thin route under `app/`.
   Empty, loading, error and denied states exist. Copy per Section 6.5.
   Register the destination in the navigation registry with its grants.
10. **E2E journey** in `tests/e2e/<app>.journey.spec.ts` with the scenario ID
    in the title, driving the real UI. Extend `seed_e2e` if it needs data.
11. **Update `app.md`** (status `built`, then `verified` once exercised against
    a running server), un-skip the scenario stubs, and add a line to
    `IMPLEMENTATION_STATUS.md`.
12. **Run the pre-push checklist** (Appendix D). Commit with a message per
    Section 13.4. Commit to `main` (Section 12).

**Definition of done** for a chunk: every step above for every requirement in
the chunk, CI green, status ledger updated, and any scope that was not
delivered named in the commit body and the status file.

---

## 4. Backend conventions

### 4.1 App layout

| File | Purpose |
|---|---|
| `app.md` | The app's spec (Appendix B). Read first. |
| `models.py` | Django models with snake_case columns (the API is camelCase through the alias generator). `JSONField` only with an inline lint suppression that names its Pydantic schema. Every field explicit. Tenant models extend `TenantModel`, library models `LibraryModel`, lists an admin edits extend `Vocabulary`. Writes are audited through `record()`. Ledgers extend `AppendOnlyModel`. Every model that will ever be `.first()`ed declares `Meta.ordering` on a meaningful column (Section 5). |
| `schemas.py` | All Pydantic request/response models. camelCase. Schema class names are global across apps: prefix with the app when a shape is app-specific (`CasesTriageBody`). |
| `logic.py` | All business logic. Split into `<topic>_logic.py` when it grows. |
| `api.py` | Routes only. Auth, permission, step-up decorators. |
| `tests_scenarios.py` | One test per `@integration` scenario in app.md. |
| `tests_*.py` | Everything else: models, rule branches, isolation, concurrency storms, regression pins. |

### 4.2 Auth and permissions

**Nobody has a password.** A person signs in with an emailed one-time code
exactly once, to enrol a passkey, and with a passkey from then on.

- **Principals.** People (tenant members and platform staff) use
  `SessionAuth`. Agents and integrations use `ApiKeyAuth` with narrow scopes
  (`@requires_scope`). No scope allows a library edit.
- **Invitation only.** A tenant admin invites an email address with roles.
  The invite link carries a single-use token (stored hashed, 72 h). Opening
  it sends a 6-digit code: single use, 10 minutes, stored hashed, 5 attempts,
  rate limited per address and IP, compared in constant time. All numbers are
  settings.
- **The enrolment session can do one thing.** A verified code yields an
  `EnrolmentAuth` session that reaches the passkey registration ceremony and
  `GET /me`, nothing else. The account becomes active when the first passkey
  is stored.
- **The code switches off after the first passkey.** A code request for an
  account that holds a passkey answers exactly like any other request and
  sends nothing. Without this rule email is the real authenticator and the
  passkey adds nothing.
- **Recovery has no self-service fallback.** A tenant admin re-issues
  enrolment behind step-up. It is audited, revokes existing sessions, and
  notifies the user and the other admins. The last admin of a tenant goes
  through platform support with an out-of-band check, written to the support
  access log. Enrolment prompts for a second passkey.
- **WebAuthn settings.** User verification required, discoverable
  credentials, `WEBAUTHN_RP_ID` and allowed origins from settings. Store
  credential id, public key, sign count, transports, AAGUID, backup-eligible
  and backup-state flags, nickname, created and last used.
- **Credential policy is tenant configuration:** allow synced passkeys, or
  require attested device-bound authenticators from an AAGUID allow-list.
- **Sessions.** A short-lived access token held in memory, a rotating refresh
  token in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie scoped to the
  auth path, a replay grace window, and a `user_session` row behind every
  refresh so a user or admin can revoke at once. Idle and absolute limits are
  tenant policy with platform maximums.
- **Step-up is a fresh passkey assertion** (`@requires_step_up`) on: case
  sign-off, applicability and proposal approval, footprint changes, exports,
  API key creation, role and permission changes, security policy changes,
  re-enrolment. The assertion reference is stored on the audit event.
- **Permissions, never role names.** Permission constants live in one file
  and are owned by engineering. Roles are database rows: system roles seeded
  from the PRD's matrix, plus tenant-defined roles composed from permissions.
  Endpoints and UI check permissions only. A tenant always keeps one admin.
- **Four eyes.** The approver of an applicability decision, a case sign-off,
  a footprint change or a library proposal is never the requester. The
  database enforces it with a check constraint and the API answers 409
  `four_eyes_violation`.
- **Platform staff see tenant data only through a support access grant** that
  the tenant can see, time-boxed and logged.
- **SSO (OIDC, SAML) and SCIM** are a tenant option planned for R3. They
  never reintroduce a password: the app holds none either way.
- The 403 is structured: `detail` (human), `code`, `requiredPermission`. The
  UI renders it directly.

### 4.3 Product invariants, time, correctness

- **Facts and judgement live apart.** Library tables hold sourced public
  facts and carry no `tenant_id`. Tenant tables hold one company's
  assessments and work, carry `tenant_id` and sit under row-level security
  (Section 14).
- **Proposals are the only door into the library.** Agents and people
  propose, a second person approves, and approval applies the payload, writes
  the new version, the audit row and the search re-index in one transaction.
  Re-verification stamps are the single exception.
- **Nothing is overwritten.** Legal text and obligation summaries are version
  rows with effective dates, which is what makes "as of" and "show what
  changed" possible. Evidence is soft-deleted. Ledger-like tables extend
  `AppendOnlyModel`, which raises on update or delete, and on Postgres a
  trigger makes the docstring true (`BEFORE UPDATE OR DELETE … RAISE`, with a
  `SET LOCAL cw.maintenance` escape hatch so a conscious fix states its
  intent; the trigger ignores it for the application role, so the hatch is the
  schema owner's, in a migration).
- **No write commits without its audit row.** `record()` writes the
  `audit_event` and the `outbox_event` in the same transaction as the change,
  with a user, agent or system actor and before and after values.
- **"Applies" and "we comply" are separate facts**, so a gap can never hide
  behind an applicability flag.
- **Stable keys never change.** Instruments, provisions, obligations, changes
  and every vocabulary row carry an immutable key. Labels can be renamed
  freely because nothing stores a label.
- **AI output is labelled until a person confirms it**, and every model
  output is logged with model, version and review state.
- **Concurrent edits cannot overwrite each other.** Tenant-editable records
  carry a `version` and writes send `If-Match`. A stale write answers 409
  `stale_write`.
- **Timestamps stored UTC** (`USE_TZ = True`). Deadlines, digests and
  reminders convert through the tenant's timezone explicitly. Legal dates are
  plain dates with a precision (day, month, quarter, year), never timestamps.
- **Idempotency** on every agent write (`stableKey` on changes,
  `Idempotency-Key` on proposals) and on webhook handlers, because agents and
  senders retry.
- **Every window, cap, rate and threshold is a setting** with an env
  override, grouped in `settings.py` under a banner comment naming the
  requirement. The concrete number in a test is a fixture, never a hardcode.
- **Enums in code are for kinds only** (Section 15). A value an admin might
  want to add, rename or retire is a row, never a Postgres enum, a
  `TextChoices` or a TypeScript union.
- **No Django admin.** Zero `admin.py` files, on purpose, recorded in an ADR.
  The API with its permissions is the only write surface.
- **Money** appears only in billing, as an integer minor unit.

### 4.4 Errors and the empty state

- `logic.py` raises `ValidationError` with clear user-facing text.
  `api.py` re-raises as `HttpError` with the right status. Never a stack trace
  or implementation detail in a response.
- **One error shape everywhere:** RFC 9457 problem details with `title`,
  `status`, `detail` for people and a machine-readable `code`
  (`four_eyes_violation`, `open_actions`, `evidence_missing`,
  `invalid_transition`, `stale_write`, `unknown_key`), plus `errors[]` for
  field validation and `requiredPermission` on a 403. The client branches on
  `code` and never string-matches `detail`.
- **An empty answer is 200, not 4xx.** A well-formed read that finds nothing
  returns 200 with an empty collection and, where the reason matters, a field
  that states it. 404 is for an addressed resource that is not there, which
  includes a record in another tenant.
- Responses that drive a workflow carry `allowedTransitions`, so the UI never
  guesses what the state machine permits.

### 4.5 Rules learned from real bugs

- **A picker's options come from the thing being picked, not from rows that
  already reference it.** Six consoles derived departments from existing
  rooms and instructors from existing certifications: correct on a running
  venue, a closed loop on a new one (empty list, hidden create button, nothing
  ever created). Provide reference reads (`/reference/departments`,
  `/reference/staff`) carrying label and id and nothing else.
- **An empty restriction list means "no restriction".** Any M2M that narrows
  who or what may do something answers "what does empty mean?" on the model,
  on the screen that edits it ("Anyone eligible"), and in a test. The failure
  is silent: a client reads "no times available" as "we do not do this".
- **Configured, not branched on.** A category's behaviour (booking modality,
  client-selectable, required waiver kind) is a column on the category row,
  edited through one audited PATCH, read by every consumer. Statutory mappings
  key on the immutable `kind`, never on the editable name.
- **A migration reads no live setting and declares every dependency its own
  operations need.** A `RunPython` that reads `settings.X` replays differently
  per environment and breaks the day `X` is deleted. Freeze the list inline.
- **Data-fix migrations and commands are environment-guarded**: check the
  `<host>` environment variable and return silently elsewhere.
- **`.first()` on an unordered queryset with uuid primary keys is a coin
  flip on Postgres.** Declare `Meta.ordering`,
  and pin the intended `order_by` structurally in a test (capture the SQL),
  not just behaviourally.
- **Tests run on the production engine.** The last repo tested on SQLite,
  where `select_for_update` is a no-op and ordering looks stable, and both
  hid real bugs. This project has one engine everywhere.

### 4.6 File storage

Binary artefacts (evidence, exports, imports, case files) never live in the
database. One seam (`apps/shared/storage.py`) returns the backend for the
environment: local for dev and tests, a private S3-compatible bucket when
deployed, which refuses to boot on the ephemeral local backend. Keys are
deterministic (tenant id plus row id), a failed write raises inside the
transaction that creates the row, and nothing is public.

**Downloads stream through permission-checked endpoints**, so every evidence
download is authorised and audited. This overrides the presigned download
links in `docs/inputs/openapi.yaml`. Uploads store a content hash, enforce a
size and type allow-list, and pass a malware scan before the file becomes
visible to anyone else.

### 4.7 Logging

`logging.getLogger(__name__)` per module. `error` for failures needing
attention, `warning` for recoverable, `info` for business events. Request-ID
correlation is automatic via middleware.

Two classes of data are protected. **Personal data:** a person's name and id
are permitted in logs, and nothing else about a person is (contact details,
tokens, IP beyond the security log). **Tenant content:** the text of an
assessment, a gap, a status note, a comment, evidence or a question typed
into Ask is a bank's confidential material. It never appears in logs, in
Sentry, in analytics, or in a prompt sent to a model endpoint the tenant's
contract does not allow. Log the record id instead. The compliance lint
checks both classes. Logs contain personal data by design and inherit a
retention limit.

---

## 5. Structural guard tests (build these first, keep them forever)

Each one closes a hole that hand review cannot see because the bad diff looks
exactly like the twenty good ones above it. Each fails with a message that
says what to do. Each lives in `apps/shared/tests_*.py`.

| Guard | What it enumerates | What it demands |
|---|---|---|
| **Route permissions** | Every operation Ninja registered (the same objects that produce `openapi.json`) | Each is `@requires_permission`-gated or `@requires_scope`-gated OR listed in `UNGATED_BY_DESIGN` with a reason of one of five shapes: `self`, `bootstrap`, `capability`, `logic-gate`, `public-token`. An allowlist of bare paths decays into a rubber stamp; a reason can be read back and disagreed with. |
| **Row-level security** | Every model with a tenant foreign key, against `pg_policies` and `pg_class` | RLS is enabled and forced, and a tenant policy exists. A new tenant table without a policy fails here, not in production. |
| **Database role** | The role the app connects with | Not a superuser, not the table owner, no `BYPASSRLS`. |
| **Tenant isolation** | Every tenant-scoped GET, PATCH and DELETE route, with a record that belongs to another tenant | 404, never 403 and never data. |
| **Library fence** | The AST of every module that writes a `LibraryModel` | Writes happen only inside `library_write()` in the allowlisted modules (`proposals/apply.py`, `watch/write.py`, reference seeds). `watch/write.py` is the watch door: the only module under `apps/watch/` on the list, and it reaches the seven watch tables and no inventory table. |
| **Four eyes** | Every table in the four-eyes list | The requester-is-not-approver check constraint exists. |
| **Audit on write** | Every non-GET operation, through its scenario test | The request wrote at least one `audit_event`. A mutating route with no scenario fails too. |
| **Kinds only** | Every `TextChoices`, Postgres enum and generated TypeScript union | Each is in the tier-one allowlist of Section 15 with a reason. |
| **Vocabulary integrity** | Every vocabulary with a `kind` | Each kind has at least one active system row and every list has a default. |
| **Schema names** | Every `Schema` subclass across all `schemas.py` modules | Two apps may not define divergent schemas with the same class name (Ninja flattens components globally and the loser silently mistypes the generated client). Identical duplicates are allowed. |
| **Production guard** | Boots Django in a subprocess under different environment names | An unrecognised environment name is treated as production (fail closed). `prod`, `Production`, `demo`, `dev` all keep every guard on. |
| **Query ordering** | The SQL the production code executes for each `.first()` | Ordered by the intended column, not the primary key. |
| **Seed integrity** | The E2E seed | Two tenants exist. Every fixed login has exactly the properties journeys depend on (its roles, its passkey, the one user still awaiting enrolment), so a test cannot be hollowed out by a seed change. |
| **Celery registration** | Every task module | Every beat entry points at a task that exists, and every tenant task is wrapped in `@tenant_task`. |
| **Health** | `/health/` | 200 with all components ok, 503 with the failing one named, and the worker ping bounded (`limit=1`). |

Add a guard whenever a class of bug recurs. The docstring names the incident.

---

## 6. Frontend conventions

### 6.1 Data layer

- One axios instance. Never a second one, never raw `fetch` for API calls.
- `api.generated.ts` is generated from the backend OpenAPI schema and never
  hand-edited. Types are imported from it (`components['schemas'][…]`,
  `operations[…]['parameters']['query']`), never redeclared.
- `features/<domain>/api.ts` is thin wrappers returning `.data`.
  `hooks.ts` owns query keys, invalidation, and idempotency keys for
  mutations that need them (stable across retries of one attempt).
  `*-presentation.ts` holds pure functions (labels, groupings, derived state)
  with unit tests beside them.
- TanStack Query for server state. React state for local UI. No global store
  until a real need appears.
- **Fan out, never chain.** Six sequential 200 ms calls blow the 500 ms
  screen budget. Disable queries a surface cannot satisfy (the console shell
  must not fire tenant queries that can only 404).

### 6.2 Navigation and permissions

- One typed **navigation registry** (pure TypeScript, no React) is the source
  of truth for every destination: href, label key, surface (`tenant` or
  `console`), `anyOfPermissions`, dock rank, group. Dock, sidebar, More menu, command palette
  and the client-side gate all derive from it. The Playwright role-matrix
  spec reads it too.
- **Nothing in UI code checks a role name.** A destination is visible iff the
  signed-in user's permission list unlocks it. The server's structured 403
  remains the enforcer; the registry is UX hinting.
- `<RequirePermission anyOf={…}>` renders children or the quiet Restricted
  screen, and its error boundary renders a server 403 as the same screen
  with the server's `detail` as body copy and the missing grant humanised.
- **Never branch on an editable name** (a flag called "AI"). Branch
  on `kind` or on a configured column the server owns.

### 6.3 Theming

The palette is the Green Design System's 2023 theme, imported and never
copied. `scripts/build-tokens.mjs` reads `@sebgroup/green-tokens` and writes
`tokens.generated.css` (light under `:root`, dark under `.dark`).
`brand.css` is the only place our own values live: it overrides the
`brand-01` and `brand-02` variables, because those two pairs are SEB's brand
and this product is sold to other banks (DECISIONS D-05). A rebrand or a
white-label is a change to that one file.

Light and dark via `next-themes` (`attribute="class"`, system default).
Tailwind colour names map to the token variables, so screens use semantic
names only. Never `text-white` / `text-black` for content, never a hex value
in a component. Contrast is pinned by a unit test against WCAG AA for every
text-on-surface pair the design uses, in both themes, including all six pill
tones. Every screen is checked in both themes before done.

The prototype's own components (rows, pills, chips, the timeline, the legal
text block) are built as our primitives on these tokens. A Green Core
component may be used for a heavy widget only after the Phase 0 spike proves
it renders and hydrates under `next start` (DECISIONS D-04). Use the Green MCP
server to look up token names. Never recall them.

### 6.4 Typography: named roles, and no seventh

Tailwind's numbered font scale is **replaced**, not extended (set
`theme.fontSize` outside `extend`), so `text-sm` generates nothing, and an
ESLint `no-restricted-syntax` rule fails the build on any legacy or one-off
size, including inside template literals and `cva` variants. The last repo
had grown sixteen sizes before this landed.

| Role | Use |
|---|---|
| `text-hero` | Public marketing headlines only. Never behind auth. |
| `text-display` | The page `h1`; a single headline figure. |
| `text-title` | Section headings, card titles, stat-tile values. |
| `text-body` | Running text, labels, table cells, controls. The default, set on `<body>`. |
| `text-meta` | Everything that describes the content: hints, captions, timestamps, ledes, notices, empty states. |
| `.microlabel` | The same register uppercase with tracking: eyebrows, column heads, button labels. |

Take the design's values for each role. Keep `body` and `meta` as separate
names even if they share a size, so one can move without a codemod. Three
weights, two families, and `text-primary` only on things you can press.

### 6.5 Screen copy

Screens say what the user is doing, not what the module is. On internal
surfaces: a masthead gets one line of at most 60 characters or none; section
descriptions are deleted (one per screen may survive, at most 80 characters,
only when it states a rule the operator cannot see from the UI); no PRD ids,
no restated invariants ("every change is audited"). Keep and tighten
destructive-action confirmations, empty states that name the next action, and
field hints stating a real constraint. Public pages sell and keep their voice.
A rule cut from a screen goes into a code comment, never a tooltip.
Every string lives in the message catalogs, in each shipped language, and
vocabulary labels come from their rows (Section 17).

Placeholders are styled as hints (dim italic, "e.g." prefixed) so an example
is never mistaken for typed input.

### 6.6 Formatting and logging

`formatDate()`, `formatDateTime()` and `formatPartialDate()` (UTC or a plain
date plus precision in, the user's language and the tenant's timezone out)
for every date. `logger` from `shared/utils/logger`, never `console.log`
(ESLint blocks it). No tokens, PII or tenant content in URLs, storage, or
logs. Store only what a screen needs.

### 6.7 Pills and labels

The prototype's pill system is a contract. `design/system/pills-and-labels.md`
is the source, and this is its summary.

- **Six tones, named as Green names them:** `information` (neutral grey),
  `notice` (blue), `positive`, `warning`, `negative`, and `brand` (the brass
  pair, `brand-02`). There is no seventh, and no component accepts a colour.
- **Tone is never chosen by a person.** It comes from the slot (a change type
  is always `notice`, a scope facet always `brand`) or from the fixed `kind`
  behind a severity scale (a gap category is always `negative`). An admin
  supplies a label, translations and a usage note, nothing else.
- **Slot order is fixed per record type.** Change: type, urgency, flags,
  status. Obligation: instrument, guidance, applicability, compliance status,
  pending approval, open changes.
- **One `Pill` component, one presentation function per record type.**
  `*-presentation.ts` returns label, tone and order from keys and kinds, and
  unit tests pin all three. No raw pill markup anywhere else (ESLint).
- **Computed pills** ("2 open changes", "Change pending: in force 1 Oct",
  "All services", "Not client-specific") are built in presentation functions
  from facts the API sends (`openChangeCount`, `pendingApplicability`). The
  API never sends a phrase.
- **Labels are phrases, not codes** (`new` reads "Needs triage"). They live in
  the vocabulary row or the message catalog, in every UI language.
- **Tenant tags** render as an outlined `information` pill, so `brand` keeps
  meaning "from the shared library".
- A `/dev/pills` gallery route renders every tone, slot and record type, and a
  Playwright screenshot pins it in both themes.

### 6.8 Mobile actions

On phones, action buttons sit on the right for thumb reach. Two buttons
share one row, never stacked, with the primary on the right and the
secondary on the left.

---

## 7. From UI design to screens

The design input is the interactive prototype in `design/prototype/`, the
system cards in `design/system/` and the brand files in `design/brand/`.

1. **Direction.** Already chosen: the timeline home with the weekly briefing
   reachable from it, the roadmap as its own page, SEB-style wealth and asset
   management restraint, very dark green, sand and brass. Record it in an ADR
   with `design/README.md` as the source.
2. **Tokens.** Generated from Green and overridden in `brand.css`
   (Section 6.3), plus the named type scale in `tailwind.config.ts` with
   Hanken Grotesk and Noto Sans Mono. Pin contrast in a unit test. Brand
   constants (name, support contact, legal footer) live in `shared/brand.ts`,
   read from settings where the backend owns them.
3. **System cards.** `design/system/` cards become shared components and the
   navigation registry's structure. The pill and label card comes first.
   Decompose the prototype into further cards as you go (rows and lists,
   forms, the change timeline, the legal text block with version diff, empty
   states) and commit each card before the screens that use it.
4. **Screen cards.** One `design/screens/<surface>-<screen>.html` per screen,
   cut from the prototype. **Screens the prototype lacks are listed in
   `design/README.md`** (sign-in and enrolment, tenant admin, platform
   console, vocabulary management). Design each as a card in the prototype's
   language first, get the card committed, then build it.
5. **UI implementation plan** (`docs/plans/UI_Implementation_Plan.md`) maps
   **every backend capability to a screen, for every role**, generated from
   the real endpoint inventory (route, auth, permission, step-up) and the
   role matrix. Honesty rules from the last repo, verbatim in spirit:
   - A feature is covered when its screen exists, its role variants render,
     its empty/loading/error/denied states exist, and its `@e2e` journey is
     un-fixme'd. A registry entry rendering "Coming soon" is not shipped.
   - When the PRD or an app.md conflicts with the plan, they win.
   - Never check role names in UI code.
   - A progress ledger at the top, updated at every integration, with
     corrections recorded rather than overwritten.
   - Every shipped hook has a caller. A payload that carries an id must carry
     enough for a human to act on it.
6. **Reachability audit** after each wave: every mutation endpoint has a
   screen that calls it, every list has a create path on an empty tenant,
   every list a detail, every detail an edit where the PRD allows one, and
   every vocabulary can be managed without a deploy.

---

## 8. Testing

### 8.1 Backend

Django test framework under `config.test_settings`, on Postgres. Per app
`tests_*.py`. Scenario tests carry the scenario ID. These rules require tests
with every change: footprint matching, "as of" version selection, the case
state machine and its guards, four eyes, proposal apply, tenant isolation,
vocabulary retire and merge, rank fusion in search. Concurrency tests use
real threads against Postgres, where `select_for_update` and the `version`
check mean what they say. The scenario base class fails a mutating request
that wrote no audit row (Section 5).

### 8.2 Coverage floors are a ratchet

- A **global floor** (`fail_under`) plus **per-module floors** on the modules
  where a bug costs money, mis-states a statutory figure, or lets the wrong
  person through (tenancy, authentication, permissions, proposals, cases,
  register, footprint matching, vocabulary, search, audit). A single aggregate lets a 100% module
  mask a regression next to it.
- Floors sit just below measured coverage, and the **margin is sized to the
  module**: minus 2 at 400+ statements, minus 3 at 100 to 400, minus 4 below
  100, because two points at 53 statements is one statement.
- **Never lower a floor to go green.** Raise a floor when a module climbs
  away from it. Record the measured value, the test count and the date beside
  each floor, and restate them whenever you touch the file.
- The per-module gate **refuses to judge a partial run** (aggregate far below
  the global floor means the suite was subsetted; the numbers are real but the
  question was wrong). A gate that answers a question it cannot answer is
  worse than one that declines.
- Frontend: Vitest thresholds per directory (`features/**`, `shared/utils/**`,
  `components/**` and named component directories with real coverage). A
  directory in `include` with no threshold is a number on a dashboard, not a
  gate. A low floor stated as "ratchet, not a quality bar" is honest; a low
  floor dressed as an achievement is not.

### 8.3 E2E: real flows, mandatory for every UI chunk

- **One command** runs it: Playwright's `webServer` drops and recreates a
  throwaway Postgres database, migrates from zero (which is what proves the
  migration graph still applies), runs `seed_e2e`, boots Django with the E2E
  flag and mock adapters, builds and starts Next in production mode, then
  runs the suite.
- **Sign in through the UI with a passkey.** The seed stores the public keys
  of fixed test credentials, and `support/passkeys.ts` seeds the matching
  private keys into Playwright's virtual authenticator
  (`browserContext.credentials`). The sign-in page then runs a real WebAuthn
  ceremony. The test private keys are allowlisted in `.gitleaks.toml` by exact
  literal with this reason. Never inject tokens or cookies. Never mock API
  responses. If the backend is down, tests fail.
- **The emailed code appears in exactly two journeys:** enrolment of the one
  seeded user who has no passkey yet (the E2E flag makes the code
  deterministic), and the proof that a code request for an enrolled user
  sends nothing. The flag is refused on two independent legs when deployed.
- **Golden-path journeys** cross apps and roles and are tagged `@smoke`. They
  are listed in PRD section 5 and follow the prototype's path: Today, triage,
  assessment, actions, evidence, a refused self sign-off, sign-off by a second
  person, the case file, then an agent proposal approved in the console.
- **Extend the seed, never mock.** The seed is idempotent (natural keys),
  deterministic (no randomness), realistic, and built from the prototype's
  sample data so journeys match the design: two tenants, one login per
  system role, a platform editor, and one login per negative case a journey
  needs. `seed_e2e` refuses to run on a deployed environment.
- **Every spec imports `test` from `support/api-guard`** (ESLint enforces
  it). The guard is an auto fixture that fails an otherwise-passing journey
  on any undeclared `/api/` response ≥ 400 or any uncaught page exception.
  A journey that provokes an error on purpose declares it where it happens:
  `apiGuard.allow(/\/signoff\/approve/, 409, 'the requester cannot sign off')`.
  The guard's default list is for **known smells awaiting a fix**, each entry
  a task, deleted when the task closes, never widened.
- **When a journey fails, look at the screenshot and trace before touching
  anything.** Diagnose from what the user would have seen.
- **The four ways the suite broke** in the last repo (every red run traced):
  1. **Clocks.** Anchor fixtures to the tenant-local date plus a fixed wall
     time, never `now + Nh` that can cross midnight. A test that freezes time
     freezes it everywhere.
  2. **Branching before the page settles.** `isVisible()` does not wait.
     Settle first (`await expect(a.or(b).first()).toBeVisible()`), then
     branch. Never `.catch(() => false)` around visibility.
  3. **Text that matches the wrong element or nothing.** Use `{ exact: true }`
     where copy can collide. Assert a sentence's distinctive spine, not one
     adverb. Run the **copy-drift check** when a diff rewords UI copy.
     Journeys run in one pinned language.
  4. **Retries inheriting wreckage.** A spec that mutates seeded data restores
     it in a teardown that runs on failure too.
- Push CI runs the `@smoke` subset; nightly runs everything.
- Run every chunk against a **freshly seeded** backend.

---

## 9. CI and quality gates

Every gate blocks. Run the same commands locally before every push (Appendix
D); CI is insurance, not first detection.

| Gate | Stops |
|---|---|
| Migration drift (`makemigrations --check`) | A model change without a migration, which passes tests and breaks the deploy |
| Migration graph applies from zero | A conflicting or broken graph `--check` cannot see |
| Backend tests under coverage | Regressions |
| Global coverage floor + per-module floors | Coverage sliding; a covered module masking an uncovered one |
| ruff (correctness classes: E4/E7/E9, F, B, DJ, S) + mypy (pragmatic, whole tree) | Undefined names, bugbear patterns, Django footguns, bandit findings, type errors on annotated code. Every excluded rule names its reason in `pyproject.toml`; a rule selected then blanket-ignored is worse than none |
| Compliance lint (`--all`, never `--since HEAD~1`) | `JSONField` without a named schema, a new enum outside the kinds allowlist, PII or tenant content in logs, bare `except Exception:`, untyped responses, `import random` for security randomness, `**kwargs` in endpoints or logic. Suppressions are inline with a reason |
| OpenAPI + TypeScript drift | Frontend types diverging from the contract. The export is normalised (status descriptions) identically in CI and locally |
| Frontend lint, typecheck, unit coverage, build | Lint and type errors, coverage drops, broken build |
| E2E (real stack) | Broken journeys, undeclared API failures, page exceptions |
| Secret scan (gitleaks, always on push) | Committed secrets. Allowlist entries are exact literals with a stated reason, never a relaxed rule |
| Dependency CVEs (osv-scanner on the **committed** lockfiles + `npm audit`) | Known-vulnerable dependencies. The scan refuses to run on an empty lockfile, and the step runs under `bash -eo pipefail` so a broken pipe fails instead of passing on the last exit code |
| CodeQL (own SARIF gate, medium and above) | Injection, traversal, unsafe deserialisation. Findings are accepted per fingerprint with a reason, never per rule; stale acceptances are reported so the list cannot rot into a mute |
| Requirements coverage | A PRD requirement with no scenario, or a scenario with no test |
| Contract drift | A designed operation in `docs/inputs/openapi.yaml` that is missing or reshaped without an entry in `INPUT_DELTAS.md` |
| Search and classification evaluation | Retrieval or agent tagging quality dropping beyond the recorded tolerance |
| Message catalogs | A UI string missing in a shipped language |
| Pill gallery screenshot | The design's tones, slots and labels drifting, in either theme |
| Dependency licences | A copyleft dependency (AGPL in particular), and missing Apache attribution for the Green packages |
| Container image scan | Vulnerable OS packages, which lockfile scanners never see |

Shape rules:

- **Tiered.** A `changes` job decides which expensive jobs run (backend,
  frontend, lockfiles). On push events give the filter `base: ${{ github.ref_name }}`
  or it diffs against the default branch and matches everything. Use extglob
  (`backend/**/!(*.md)`), not list negation, which matches every non-markdown
  file in the repo. A change to the workflows counts as everything.
- **Nightly full run** scheduled away from local midnight (wall-clock
  fixtures are fragile there), plus the CVE scan regardless of lockfile
  changes, because advisories publish against lockfiles that did not move.
- **The nightly run is never thinned.** Everything, in full.
- **A timeout on every job**, at roughly twice the slowest observed run. A
  hung runner otherwise holds the queue for six hours.
- **Explicit `permissions:`** (`contents: read`, `pull-requests: read`).
  A Dependabot token has less by default and the paths filter 403s without it.
- **Concurrency cancels in-flight runs** on the same ref, except the schedule.
- **Never interpolate `${{ }}` into a script body.** Pass through `env:` and
  read as `"$VAR"`; a branch name can be shell source.
- **Dependabot grouped weekly** per ecosystem targeting `main`; majors a
  peer dependency cannot take are ignored by name with the reason.
- Failure artifacts (screenshots, traces, SARIF) uploaded on failure with a
  retention of two weeks.

Two failure classes CI catches that locals cannot, so a red run is not
necessarily your commit: new advisories on unchanged lockfiles (fix same day
via overrides or version floors, never `audit fix --force`, never a lowered
gate) and CodeQL fingerprints rehashed by adjacent edits (re-triage at the
new location before re-keying, never on faith).

---

## 10. Performance budgets

| Surface | Budget | Measured as |
|---|---|---|
| Any API endpoint | < 250 ms | Server time, warm: the `Server-Timing: app` header the API sets on every response |
| Any screen | < 500 ms | Interaction or navigation to the screen showing real data, not a skeleton |
| Hybrid search | < 800 ms without the reranker, < 1.5 s with it | `Server-Timing`, warm, on the evaluation corpus |
| Ask | First token < 2 s, streamed | Time to first streamed chunk |
| Exports, imports, agent runs | Asynchronous jobs with a status endpoint | Never inside a request |

- Over budget is a bug: fix it or write down why not.
- Measure before optimising and prove the fix with a number beside the claim
  (query count and timing for the backend, network panel or Playwright timing
  for the UI).
- Never diagnose against `next dev`. Reproduce against `npm run build && npm
  start` and hit the endpoint directly with curl to separate server from client.
- The budget is per request **and** per screen. Fan out; never chain a call on
  another call's result when one endpoint could answer.
- Usual causes in order: N+1 (`select_related`/`prefetch_related`, pin with
  `assertNumQueries`), unindexed filters on hot columns, client waterfalls,
  per-request work that belongs in cache or the worker.
- The API logs a WARNING above the budget (a setting) with the request ID.
- **Deploy every service in one region next to the database and the users.**
  A 190 ms round trip per statement is not recoverable by query tuning.
  Pair with persistent DB connections.
- List endpoints paginate (limit default 20, max 100).

---

## 11. Security and privacy

### 11.1 Boot guards (settings.py, first commit)

- `IS_DEPLOYED_ENVIRONMENT` is true when the host's environment variable is
  set at all, or when the environment name is not one of `local`, `test`,
  `ci`. Deny by default: `prod`, `Production`, `demo`, `dev` are deployed.
  DEBUG never disarms a guard.
- Refuse to boot when deployed with `DEBUG=True`; with a missing or default
  `SECRET_KEY` outside DEBUG; with the E2E flag set; with a mock LLM, embedder, agent
  runner or mailer anywhere except the one named test environment (where the
  UI shows a banner saying so); with a database role that can bypass
  row-level security;
  with the local file storage backend in production.
- A production-safety block near the bottom of settings owns the full
  rationale and the tests boot Django in subprocesses to prove it.

### 11.2 Runtime

- **Passkeys only. The emailed code is a one-time bootstrap, never a
  fallback** (Section 4.2). Session limits, step-up and credential policy are
  tenant settings with platform maximums.
- Rate limiting on auth and expensive endpoints (search, Ask, exports, agent
  "run now"). Off in tests by default, on in the one test that proves it fires.
- `ALLOWED_HOSTS` explicit, CORS allowlist only and scoped to `/api/`,
  HSTS/secure cookies when not DEBUG, `X-Frame-Options: DENY`, a strict
  Content-Security-Policy. Optional IP allow-list per tenant.
- ORM only. Validate path and query parameters. The raw SQL the design needs
  (RLS policies, triggers, the hybrid search query) is parameterised and
  lives in migrations or one search module.
- Secrets only in host variables and GitHub encrypted secrets; `.env.example`
  is a template with no real values; dev-only defaults are prefixed
  (`django-insecure-…`, `…-dev-only`) and allowlisted by exact literal.
- **Sentry** on its EU region: `send_default_pii=False`,
  `max_request_body_size='never'`, `include_local_variables=False`, a
  `before_send` and a `before_send_transaction` scrubber (transactions bypass
  `before_send`, and a 10% trace sample silently exempted one in ten requests
  in the last repo).
- **Fetched web content is untrusted.** Agents screen it for embedded
  instructions, hits land in `change_document.risk_flags`, and no fetched
  text is ever executed as an instruction or rendered as HTML.
- GDPR: export and deletion workflows, personal-data access audited, breach
  response runbook with the statutory notification clocks, a subprocessor
  register. B2B only, so no marketing consent flows.
- Tenant exit: a full export in open formats and verified deletion (Section 18).

### 11.3 Reviews

A dated security audit in `docs/security/` written against the published
OWASP Top 10 of the year (fetched and recorded, not recalled), re-run until
findings converge. Protect production data from accidental developer writes
(ADR): model-level fences on locked rows, database triggers on ledgers with an
explicit maintenance escape hatch, a read-only role for humans, backups and
PITR confirmed before launch. An independent penetration test precedes the
first bank tenant (Section 18).

---

## 12. Git, environments and deploy

- **Build phase: one branch.** All work is committed directly to `main`, in
  small commits per whole slice, each passing the pre-push checklist. The
  owner deploys `main` to the Railway test environment. No feature branches.
- **Before the first real tenant**, switch to `staging` → `main`: `staging`
  auto-deploys, `main` is production and is only merged from `staging` after
  the owner approves, and `main-branch-guard.yml` enforces it. Record the
  switch in an ADR. A bank's vendor review will also expect a second reviewer
  on production changes, which belongs in the same ADR.
- `.env.example` lists every variable with a comment; the runbooks
  (`RAILWAY_DEPLOY.md`, `RAILWAY_VARIABLES.md`, `DNS_DOMAINS.md`) say where
  each lives and what it unlocks.
- The entrypoint migrates as the migrator role and seeds reference data
  idempotently on every deploy. Reference rows match on their immutable key,
  so a rename survives a deploy.
- Worker and beat are separate services from the same image with a
  `startCommand` override. Business-time schedules (digests, reminders,
  agent cadences) live in the worker and run per tenant timezone; a host cron
  is UTC and only triggers.
- The deploy is container-only and twelve-factor, with nothing
  Railway-specific in code, because the design lets the tenant zone move
  into a bank's own environment.
- The Dockerfile runs as a non-root user and carries a `HEALTHCHECK` on
  `/health/`.
- Test-only data changes never execute in production (environment guard).

---

## 13. Working agreement for agents

### 13.1 Session start

1. Read `CLAUDE.md`, then `docs/CONVENTIONS.md`, then the `app.md` of every
   app the task touches. For a UI task, also the screen card in `<design>`
   and the UI implementation plan row.
2. Check `IMPLEMENTATION_STATUS.md` for where the chunk stands and
   `TODO_FOR_alex.md` for anything that blocks on a person, and
   `docs/DECISIONS.md` for the default to use when a decision is open.
3. Ask rather than guess when a convention or requirement is unclear after
   those three. A guess that conflicts with a product invariant is a stop.

### 13.2 Product invariants need the owner

Any task that would weaken one of these stops and asks: the two zones and
row-level security; proposals as the only door into the library; versions
never overwritten; an audit row with every write; four eyes and its step-up;
"applies" and "we comply" as separate facts; stable keys; AI output labelled
and logged; no passwords and no code fallback; tenant content never in logs
or unapproved model calls; the case state machine's categories and guards;
the six pill tones. Keep this table in `CONVENTIONS.md` with the PRD
reference and the owner's name on each row.

Everything else has a default. When a decision is open, take the default in
`docs/DECISIONS.md`, note it in the commit body, and keep building.

### 13.3 Delivery

- Deliver the whole slice (Section 3). If part is blocked, finish every other
  part and say exactly what was left out and why, in the commit body and the
  status file. Scaling scope down is the owner's call.
- Before pushing, run the pre-push checklist (Appendix D). One validated push
  beats three speculative ones.
- Keep code simple and beginner-friendly. Reuse before adding. Extend a
  schema, a hook, a component; do not fork one.
- Never lower a gate to go green. Never skip, disable or quarantine a test.
- When a class of failure repeats, add a guard (a test, a lint rule, a
  script) and record the incident in its docstring.
- A time-anchored fixture is reviewed against the clock rules before it is
  committed.

### 13.4 Commit messages

A headline in plain English that says what changed from the user's or the
system's point of view ("Every CI job learns when to give up", "The swap
marketplace learns that a started shift is history"). A body that explains
why: the request or incident with its date, the requirement IDs, what now
happens, and the measurement that justifies it. Name what was deliberately
not done. No model identifiers or tool names in commits.

### 13.5 Where knowledge goes

| Kind | Home |
|---|---|
| Why a line of code is the way it is | A comment beside it, naming the incident and the number |
| A rule that spans files | `docs/CONVENTIONS.md`, with the bug that taught it |
| A decision between options | `docs/adr/` |
| A requirement's state | The app's `app.md` status cell |
| A chunk's state | `docs/plans/IMPLEMENTATION_STATUS.md` |
| A cut screen sentence worth keeping | A code comment, never a tooltip |
| Something needing a person | `docs/TODO_FOR_alex.md` |
| An open decision and its default | `docs/DECISIONS.md`, then an ADR |
| A claim about the outside world | `docs/plans/Verification_Log.md`, with the source |
| An audit | `docs/reviews/` or `docs/security/`, dated |

---

## 14. Tenancy and zones

| Zone | Holds | Isolation |
|---|---|---|
| **Library** | Sourced public facts shared by every tenant: instruments, provisions, obligations and their versions, regulatory changes, sources, library vocabularies, search chunks | No `tenant_id`. `LibraryModel` refuses writes outside `library_write()`. Content changes only through approved proposals |
| **Tenant** | One company's judgement and work: footprint, register, gaps, cases, evidence, comments, tenant vocabularies, agent settings | `tenant_id` on every row, row-level security enabled and forced |

- **Two database roles.** `cw_migrator` owns the tables and runs migrations.
  `cw_app` runs the application: no superuser, no ownership, no `BYPASSRLS`.
  PostgreSQL lets superusers, `BYPASSRLS` roles and table owners skip
  policies, which is why the boot guard checks the role.
- **Setting the tenant.** `ATOMIC_REQUESTS = True`. After authentication
  resolves the membership, `tenancy.activate()` runs
  `SET LOCAL app.tenant_id = …`. Policies read
  `current_setting('app.tenant_id', true)`, so an unset value matches no rows.
  Fail closed.
- **Tasks.** Every tenant task is wrapped in `@tenant_task`, takes the tenant
  id as an explicit argument and activates it inside its own transaction.
- **Mixed tables** (`audit_event`, `ai_generation`, `problem_report`,
  `outbox_event`, `api_key`) show library rows to everyone and tenant rows to
  their tenant.
- **Private library records.** A tenant's own sources, and the changes and
  obligations derived from them, carry `owner_tenant_id`. The policy is
  "shared or mine".
- **Platform staff** have no bypass. Support access activates a tenant only
  through a grant the tenant can see, time-boxed and logged.
- **Schema ownership.** Django migrations own the schema. Policies, triggers,
  functions, views, generated columns and HNSW indexes are `RunSQL` with
  reverse SQL. `docs/inputs/schema.sql` is the design reference and
  `INPUT_DELTAS.md` says where to depart from it. Columns are snake_case and
  the API is camelCase through Ninja's alias generator.
- **Contract.** `docs/inputs/openapi.yaml` is the designed target. The
  exported `openapi.json` is the truth of what is built.
  `scripts/contract_drift.py` reports designed operations that are missing,
  renamed or reshaped, and each difference is either fixed or recorded in
  `INPUT_DELTAS.md`.

---

## 15. Vocabularies and configuration

A new type, status, tag or reason must never need engineering. A new rule
always does.

| Tier | Owner | Stored as | Examples |
|---|---|---|---|
| **1. Kinds** | Engineering, through a PRD bump | Enum in code | Permissions, case status categories and their transition guards, proposal kinds, applicability, evidence kind, actor type, pill tones, severity ordinals |
| **2. Library vocabularies** | Platform console | Shared rows | Instrument levels, provision kinds per jurisdiction, change types, duty types, taxonomy dimensions and terms, library tags and flags, authorities, sources, languages, jurisdictions |
| **3. Tenant vocabularies** | Tenant admin | Rows under RLS | Roles, teams, legal entities, products, tenant tags, sub-statuses, compliance status and risk scales, dismissal and close reasons, link kinds, reminder and escalation settings |

- **One abstract `Vocabulary` model:** immutable `key`, optional fixed `kind`,
  labels per language, a `usage_note` written for people and agents alike,
  `sort_order`, `active`, `is_system`, `is_default`. One generic endpoint set
  and one admin screen component render every list.
- **Statuses live inside fixed categories.** A tenant can add "Waiting for
  legal" under `assessing`. The state machine, its guards, the reports and
  the pill tone read only the category. A category always keeps one status.
  There is no configurable workflow engine, on purpose.
- **The API returns `key` and `kind`, never an enum of values**, so an admin
  adding a value changes no contract and no generated type, and the frontend
  can branch on nothing but `kind`.
- **Retire, never delete**, and show the usage count first. **Merge**
  re-points duplicates in one audited transaction.
- **Case-insensitive uniqueness and a near-duplicate check on create**
  (trigram and vector similarity): "Did you mean Custody?".
- **System rows** can be relabelled but not removed.
- **Wide blast radius means dry run, preview, commit.** A footprint change
  shows what it hides and needs a second person. Imports and bulk tagging
  follow the same pattern.
- **Library vocabulary changes go through the proposal queue**, because they
  alter footprint matching for every tenant.
- **Create where you use it.** A picker offers "Create" to a holder of
  `vocab.manage` and "Suggest" to everyone else.
- **Filters, saved searches, reports, webhooks and exports store keys**, so a
  rename is instant and safe.
- **Tenant configuration is versioned and exportable**, so a bank can take it
  through its own change process.
- **Permissions for administration are split:** `members.manage`,
  `roles.manage`, `vocab.manage`, `workflow.manage`, `security.manage`,
  `integrations.manage`, `agents.manage`, so a tenant can keep user
  administration apart from business configuration.

---

## 16. Agents and AI

- **Adapters.** `llm`, `embedder` and `agent_runner` each have one interface,
  a mock for tests and E2E, and real providers chosen by a setting. Production
  refuses a mock at boot. Before implementing a real provider, fetch its
  current documentation and record what you relied on in
  `Verification_Log.md`. Provider APIs move and are not to be recalled.
- **The app is the scheduler of record.** `backend/agents/` holds versioned
  definitions (prompt, tools, skills) that only the platform changes. They sit
  under `backend/` because the API image builds from it and the deploy seeds
  from them.
  `apps/agents` holds per-tenant settings, schedules, research requests, runs
  and budgets. The worker starts runs and updates them from runner events.
- **A tenant admin controls** which agents are on, cadence within plan
  limits, scope (topics, languages, private sources), run now, pause,
  interrupt, run history with findings and cost, a monthly budget cap and an
  off switch for all AI features. They never control instructions, tools or
  direct library writes.
- **Agent output has three destinations:** the tenant zone (drafts and
  pre-assessments), the shared library as a proposal, or a tenant-private
  library record.
- **Agents read vocabularies at run start** (key, label, usage note) and may
  submit existing keys only. An unknown key answers 422 `unknown_key` with the
  valid list. A new term is a proposal, never invented text.
- **Agent classifications are suggestions** with a confidence, shown as such
  until a person confirms.
- **Re-tag requests** apply a new tag or type to existing records as one batch
  proposal with a preview, so a new vocabulary value does not start empty.
- **Every model call writes `ai_generation`** (purpose, model, version, input
  reference, output, citations, review state). Ask answers quote only
  retrieved chunks, cite every statement, flag pending changes and return
  `noAnswer` instead of guessing.
- **Data location.** Until an EU-pinned inference path is contracted, no
  tenant-zone text is sent to a model, with one exception the tenant can
  switch off: the question typed into Ask (DECISIONS D-07).
- **Evaluation is a gate.** `search_eval.py` runs the labelled question set
  (retrieval) and the classification set (change type, flags, scope).
  A drop beyond the recorded tolerance fails CI.

---

## 17. Languages and jurisdictions

- Jurisdiction and language are data. No column, enum value or branch names a
  country or a language (no `summary_sv`, no `swedish_act`).
- Translatable text lives in translation rows keyed by language, with the
  original language marked and machine translations labelled as such.
- Search chunks exist per language and use the matching Postgres text search
  configuration (`swedish`, `danish`, `norwegian`, `finnish`, `english`).
  The embedding model must cover all five, which the evaluation set checks.
- UI copy lives in message catalogs. `messages-check.mjs` fails CI when a key
  is missing in any shipped language. E2E runs in one pinned language.
- Users pick a UI language and a content language order. Dates, numbers and
  partial dates format per language.

---

## 18. Assurance for bank customers

Under DORA the product is an ICT third-party service to each bank, and its
contract must state service locations, data handling, access and recovery,
service levels, incident assistance, audit rights and exit. Build the
evidence as you build the product, under `docs/assurance/`:

- a subprocessor register with processing locations, a data flow diagram per
  zone, RTO and RPO, a backup restore test log, the incident notification
  runbook and an exit plan;
- **exit as a feature:** a full tenant export in open formats (register,
  cases, evidence, configuration, audit log) and verified deletion;
- audit log streaming to the customer's SIEM, IP allow-listing, the support
  access log;
- an independent penetration test and a certification path (ISO 27001 or
  SOC 2) in `TODO_FOR_alex.md`, since certificates support audit rights and
  do not replace them.

---

## Appendix A: CLAUDE.md skeleton for the new repo

The package ships a bootstrap `CLAUDE.md`. Expand it in Phase 0. Keep it under
~250 lines; it is the entry point, not the manual. Sections, in order:

1. **What Compliance Watch is**, in two paragraphs, and the line "The full
   scope lives in `PRD.md`; requirement IDs refer to it. Read the relevant
   module before building any feature."
2. **Precedence** of sources (the list at the top of this playbook).
3. **Release plan** as the PRD states it, with `Build_Plan.md`.
4. **Tech stack** table with pinned versions.
5. **Non-negotiable invariants** (Section 4.3 and 13.2 condensed).
6. **Performance budgets** (Section 10 condensed).
7. **Git workflow** (Section 12) and the **pre-push checklist** (Appendix D)
   verbatim.
8. **Build and run** commands, including the Postgres with pgvector setup
   with and without Docker.
9. **Project structure** tree and the per-app file table.
10. **The app.md convention** (Appendix B rules).
11. **E2E user-flow testing** (Section 8.3 condensed, marked MANDATORY, with
    the instruction to propagate it to any sub-agent doing UI work).
12. **Rules and conventions**: snake_case in the database and camelCase in the
    API, JSONField only with a named schema, no kwargs, no logic in api.py,
    schemas in schemas.py, never expose traces, the two logging rules,
    kinds-only enums, vocabularies as rows, keys never labels, pills through
    `Pill` only, no string literals in JSX, typography roles, screen copy,
    permissions not roles, tenant activation, `record()` on every write, ask
    rather than guess on invariants and take the default elsewhere.
13. **Key file reference** table.

Also create `.cursor/rules/compliance-watch-rules.mdc` (or the IDE's
equivalent) with the ten-line summary: Ninja not DRF, OpenAPI is the
contract, two zones and RLS, proposals are the only door, `record()` on every
write, vocabularies are rows, app.md first, schemas/logic/api split, UTC and
plain legal dates, settings not literals, permissions not roles, safe
logging.

## Appendix B: app.md template

Exactly four sections. Never invent another spec format.

````markdown
# <app> — <Module name>

> **App spec.** Source: `<PRD>` Module <X> (<REQ-01>–<REQ-nn>, AC-<X>1–AC-<X>n).
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context
Why the app exists, in the product's own terms. What it replaces. What is
deliberately simplified for the first release.

## 2. Requirements
Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| <REQ-01> | … | M | R1 | pending |

## 3. Acceptance criteria (from PRD, condensed)
AC-<X>1 … one paragraph each, keeping the PRD's numbers as concrete defaults
that are read from configuration.

## 4. Test scenarios (Gherkin)
Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/<app>.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### <APP>-S1 — <Title> `@integration` `@e2e` (AC-<X>1)
```gherkin
Given …
When …
Then …
```
````

Rules: the PRD wins; read app.md before writing code in the app; `@integration`
scenarios map to `tests_scenarios.py` and `@e2e` to the journey spec with the
ID in the title; not-yet-built scenarios exist as `@skip` / `test.fixme()`
stubs; when a feature lands update Status, un-skip, and add scenarios for
behaviour the PRD does not cover; cross-app flows live in the app that
triggers them with cross-references; cross-cutting concerns are documented
where the code lives, not duplicated per app.

## Appendix C: ADR template

```markdown
# ADR NNNN — <Title>

**Date:** YYYY-MM-DD · **Status:** proposed | accepted | superseded by NNNN

## Context
The situation, the constraint, what was verified in code or against sources
(with dates), and the gaps.

## Decision
What was chosen, and what was deliberately not done, with reasons.

## Consequences
What gets easier, what gets harder, what must now be remembered.

## Implementation plan (when staged)
| Tranche | What | When |
```

Write an ADR for every entry in `docs/DECISIONS.md` during Phase 0 (status
`accepted by default` until the owner confirms), and later for: reusing this
playbook's structure, framework and version pins, the design direction, the
UI foundation, database roles for row-level security, the RP ID and domain,
the auth library, the SSO stance, LLM provider and inference region, agent
runtime, embedding model and reranker, translations as rows, evidence
delivery, tenant-zone portability, and the switch from one branch to
`staging` and `main`.

## Appendix D: pre-push checklist

Every item is enforced by CI and blocks. Run what the diff touched. All
commands assume Postgres with pgvector is running (`docker compose up -d db
redis`, or a local PostgreSQL 16 with the `vector` extension installed).

1. **Migration drift and graph** (any model change):
   ```bash
   cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings
   ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings
   ```
   `migrate_from_zero` drops and recreates a scratch database and applies the
   whole graph.
2. **Backend tests + coverage floors** (any backend change):
   ```bash
   cd backend
   ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput --parallel 4
   ./run.sh run coverage combine
   ./run.sh run coverage report
   ./run.sh run python scripts/coverage_gate.py
   ```
   `--parallel` splits the suite by TestCase across worker processes, each with its
   own clone of the test database, and each worker writes coverage data of its own,
   which is what `coverage combine` merges. Both are part of the gate: leaving the
   combine out fails with "No data to report". `scripts/prepush.sh` picks the worker
   count (`BACKEND_TEST_PARALLEL` overrides it), and CI uses one per runner vCPU.
3. **Backend lint + types**: `./run.sh run ruff check . && ./run.sh run mypy`
4. **Compliance lint**, full tree: `python backend/scripts/compliance_check.py --all`
5. **Requirements coverage**: `python backend/scripts/requirements_coverage.py`
6. **OpenAPI + TypeScript drift** (any route, schema or model change):
   `bash generate-types.sh`, commit `openapi.json` and `api.generated.ts`.
7. **Frontend** (any frontend change):
   `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
8. **E2E** for the journeys the change touches: `npm run test:e2e -- --grep "<spec or @smoke>"`,
   the full suite before closing a chunk.
9. **Search evaluation** (any change to search, chunking, embeddings or agent classification): `python backend/scripts/search_eval.py`
10. **Secrets**: `gitleaks git . --config .gitleaks.toml` if the binary is local.
11. **Copy drift** (any reworded user-facing string): `cd frontend && npm run check:copy-drift`
12. **Time-anchored fixtures** (any seed or fixture derived from "now"):
    check against the clock rules in Section 8.3.

### Which items a change runs

"Run what the diff touched" is a list, not a judgement call. `scripts/prepush.sh`
sorts the work since `origin/main` into tiers and the `changes` jobs in
`.github/workflows/ci.yml` and `.github/workflows/codeql.yml` sort a push the same
way. The rule behind every row: **a file may skip a gate only when it cannot change
what that gate measures.** That is tiering; lowering a gate is something else and is
never allowed.

| Tier | The change | Items it runs |
|---|---|---|
| `workflows` | `.github/**` | everything, as the nightly run does |
| `backend` | backend code, `docs/inputs/INPUT_DELTAS.md`, `generate-types.sh`, `openapi.json`, `infra/db/**`, `docker-compose.yml` | 1 to 6 and 9, the contract-drift and API-documentation gates, and E2E |
| `specs` | `backend/apps/*/app.md`, `PRD.md`, `docs/inputs/openapi.yaml` | 3, 4, 5, plus the contract-drift and API-documentation gates: everything in the backend job that reads text rather than running code. No migration, no suite, no coverage, no search evaluation, no browser |
| `frontend` | frontend code, `openapi.json`, `generate-types.sh` | 6, 7, 11, and E2E |
| `lockfiles` | the lockfiles, `frontend/THIRD_PARTY_NOTICES.md`, `scripts/**` | dependency CVEs and licences |
| `containers` | the Dockerfiles, `.dockerignore`, `backend/entrypoint.sh` | the image scans |
| `python` / `javascript` | `**/*.py` / `**/*.{ts,tsx,js,jsx,mjs,cjs}` | that CodeQL language |

Item 10, the secret scan, always runs, and so does the tier guard below. Nothing
under `docs/` reaches a tier except `docs/inputs/`, so a rewritten plan, runbook or
decision runs those two and nothing else. `INPUT_DELTAS.md` is
the one design input that sits in `backend` and not in `specs`, because a live
scenario test reads its text (taxonomy, I18N-S2), so editing it really can change
what the suite measures.

The three lists are one promise: a green prepush predicts a green CI run. Nothing
notices a pattern added to one file and forgotten in the other two, so
`scripts/check_ci_tiers.py` compares them (reducing both syntaxes to the paths they
select) and runs on every prepush and in every CI run, whatever changed. Its
`self-test` argument proves it still catches a dropped pattern.

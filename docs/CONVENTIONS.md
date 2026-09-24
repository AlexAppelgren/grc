# Conventions

The architecture and conventions reference for Compliance Watch, restated
from `docs/PLAYBOOK.md` Sections 4 to 18. The playbook keeps the incidents
and the reasoning; this file is the rulebook. When they differ, fix this
file. Every rule here is enforced somewhere (a guard test, a lint rule, a CI
gate, a check constraint); a rule with no enforcement is a rule waiting for
its first incident.

## 1. Backend (playbook 4)

### 1.1 App layout

| File | Purpose |
|---|---|
| `app.md` | The app's spec (Appendix B). Read first |
| `models.py` | snake_case columns; the API is camelCase through the alias generator. `JSONField` only with an inline lint suppression naming its Pydantic schema. Every field explicit. Tenant models extend `TenantModel`, library models `LibraryModel`, admin-edited lists `Vocabulary`, ledgers `AppendOnlyModel`. Writes through `record()`. Every model that will ever be `.first()`ed declares `Meta.ordering` on a meaningful column |
| `schemas.py` | All Pydantic request and response models, camelCase. Schema class names are global across apps: prefix with the app when app-specific (`CasesTriageBody`) |
| `logic.py` | All business logic. Split into `<topic>_logic.py` when it grows |
| `api.py` | Routes only: auth, permission and step-up decorators |
| `tests_scenarios.py` | One test per `@integration` scenario in app.md |
| `tests_*.py` | Everything else: models, rule branches, isolation, concurrency storms, regression pins |

### 1.2 Auth and permissions

Nobody has a password. A person signs in with an emailed one-time code
exactly once, to enrol a passkey, and with a passkey from then on.

- **Principals.** People use `SessionAuth`. Agents and integrations use
  `ApiKeyAuth` with narrow scopes (`@requires_scope`). No scope allows a
  library edit.
- **Invitation only.** A tenant admin invites an email address with roles.
  The invite link carries a single-use token (stored hashed, 72 h). Opening
  it sends a 6-digit code: single use, 10 minutes, stored hashed, 5
  attempts, rate limited per address and IP, compared in constant time. All
  numbers are settings.
- **The enrolment session can do one thing.** A verified code yields an
  `EnrolmentAuth` session that reaches the passkey registration ceremony and
  `GET /me`, nothing else. The account becomes active when the first passkey
  is stored.
- **The code switches off after the first passkey.** A code request for an
  account that holds a passkey answers exactly like any other request and
  sends nothing. Otherwise email is the real authenticator.
- **Recovery has no self-service fallback.** A tenant admin re-issues
  enrolment behind step-up: audited, revokes sessions, notifies the user and
  the other admins. The last admin goes through platform support with an
  out-of-band check written to the support access log. Enrolment prompts for
  a second passkey.
- **WebAuthn.** User verification required, discoverable credentials,
  `WEBAUTHN_RP_ID` and allowed origins from settings. Stored: credential id,
  public key, sign count, transports, AAGUID, backup-eligible and backup-state
  flags, nickname, created, last used.
- **Credential policy is tenant configuration:** synced passkeys allowed, or
  attested device-bound authenticators from an AAGUID allow-list.
- **Sessions.** Short-lived access token in memory, rotating refresh token in
  an `HttpOnly`, `Secure`, `SameSite=Strict` cookie scoped to the auth path, a
  replay grace window, a `user_session` row behind every refresh for instant
  revocation. Idle and absolute limits are tenant policy with platform
  maximums (defaults 30 min and 12 h, D-06).
- **Step-up is a fresh passkey assertion** (`@requires_step_up`) on: case
  sign-off, applicability and proposal approval, footprint changes, exports,
  API key creation, role and permission changes, security policy changes,
  re-enrolment. The assertion reference is stored on the audit event.
- **Permissions, never role names.** Permission constants live in one file
  owned by engineering. Roles are rows: system roles seeded from the PRD's
  matrix plus tenant-defined roles composed from permissions. Endpoints and
  UI check permissions only. A tenant always keeps one admin.
- **Four eyes.** The approver of an applicability decision, a case sign-off, a
  footprint change or a library proposal is never the requester. A check
  constraint enforces it and the API answers 409 `four_eyes_violation`.
- **Platform staff see tenant data only through a support access grant** the
  tenant can see, time-boxed and logged.
- **SSO (OIDC, SAML) and SCIM** are an R3 tenant option and never reintroduce
  a password.
- **The 403 is structured:** `detail`, `code`, `requiredPermission`. The UI
  renders it directly.

### 1.3 Product invariants, time, correctness

- **Facts and judgement live apart.** Library tables hold sourced public
  facts with no `tenant_id`. Tenant tables hold one company's assessments and
  work, carry `tenant_id` and sit under row-level security.
- **Proposals are the only door into the library.** Approval applies the
  payload, writes the version, the audit row and the search re-index in one
  transaction. Re-verification stamps are the single exception.
- **Nothing is overwritten.** Legal text and summaries are version rows with
  effective dates. Evidence is soft-deleted. Ledgers extend `AppendOnlyModel`
  (raises on update or delete) and a Postgres trigger makes it true
  (`BEFORE UPDATE OR DELETE … RAISE`, with `SET LOCAL cw.maintenance` as the
  escape hatch for a conscious fix, which the trigger honours for the schema
  owner in a migration and ignores for the application role).
- **No write commits without its audit row.** `record()` writes `audit_event`
  and `outbox_event` in the same transaction with a user, agent or system
  actor and before and after values.
- **"Applies" and "we comply" are separate facts.**
- **Stable keys never change.** Instruments, provisions, obligations, changes
  and every vocabulary row carry an immutable key; labels rename freely.
- **AI output is labelled until a person confirms it**, and every model
  output is logged with model, version and review state.
- **Concurrent edits cannot overwrite each other.** Tenant-editable records
  carry `version`; writes send `If-Match`; a stale write answers 409
  `stale_write`.
- **Timestamps in UTC** (`USE_TZ = True`). Deadlines, digests and reminders
  convert through the tenant's timezone explicitly. Legal dates are plain
  dates with a precision (day, month, quarter, year), never timestamps.
- **Idempotency** on every agent write (`stableKey` on changes,
  `Idempotency-Key` on proposals) and on webhook handlers.
- **Every window, cap, rate and threshold is a setting** with an env
  override, grouped in `settings.py` under a banner naming the requirement.
  The number in a test is a fixture, never a hardcode.
- **Enums in code are for kinds only** (Section 12). A value an admin might
  add, rename or retire is a row, never a Postgres enum, a `TextChoices` or a
  TypeScript union.
- **No Django admin.** Zero `admin.py` files (ADR 0021). The API with its
  permissions is the only write surface.
- **Money** appears only in billing, as an integer minor unit.

### 1.4 Errors and the empty state

- `logic.py` raises `ValidationError` with clear user-facing text; `api.py`
  re-raises as `HttpError` with the right status. Never a stack trace or an
  implementation detail in a response.
- **One error shape:** RFC 9457 problem details with `title`, `status`,
  `detail` and a machine-readable `code` (`four_eyes_violation`,
  `open_actions`, `evidence_missing`, `invalid_transition`, `stale_write`,
  `unknown_key`, `step_up_required`), plus `errors[]` for field validation and
  `requiredPermission` on a 403. The client branches on `code`, never on
  `detail`.
- **An empty answer is 200.** A well-formed read that finds nothing returns
  200 with an empty collection and, where the reason matters, a field that
  states it. 404 is for an addressed resource that is not there, including a
  record in another tenant.
- Workflow responses carry `allowedTransitions`.

### 1.5 Rules learned from real bugs

- **A picker's options come from the thing being picked**, never from rows
  that already reference it (a closed loop on an empty tenant). Provide
  reference reads (`/reference/…`) carrying label and id only.
- **An empty restriction list means "no restriction"**, stated on the model,
  on the screen ("Anyone eligible", "Not client-specific") and in a test.
- **Configured, not branched on.** Behaviour is a column on the row, edited
  through one audited PATCH. Statutory mappings key on the immutable `kind`.
- **A migration reads no live setting** and declares every dependency its own
  operations need. Freeze lists inline.
- **Data-fix migrations and commands are environment-guarded.**
- **`.first()` on an unordered queryset with uuid keys is a coin flip.**
  Declare `Meta.ordering` and pin the intended `order_by` structurally.
- **Tests run on the production engine.** One engine everywhere.

### 1.6 File storage

Binary artefacts never live in the database. `apps/shared/storage.py` returns
the backend for the environment: local for dev and tests, a private
S3-compatible bucket when deployed, which refuses to boot on the local
backend. Keys are deterministic (tenant id plus row id), a failed write
raises inside the row's transaction, nothing is public. **Downloads stream
through permission-checked endpoints** (D-11, overriding the presigned links
in `docs/inputs/openapi.yaml`). Uploads store a content hash, enforce a size
and type allow-list, and pass a malware scan before the file is visible.

### 1.7 Logging

`logging.getLogger(__name__)` per module; `error`, `warning`, `info` by
severity; request-ID correlation through middleware. **Personal data:** a
person's name and id may be logged, nothing else (contact details, tokens,
IP beyond the security log). **Tenant content:** assessment, gap, note,
comment, evidence or Ask text never appears in logs, Sentry, analytics, or a
prompt to a model endpoint the tenant's contract does not allow. Log the
record id. The compliance lint checks both. Logs inherit a retention limit.
A query string is tenant content (`?q=` is what someone searched for): the
access log prints the path without it, and no formatter or Sentry hook may
pass one on.

### 1.8 The published API explains itself

The standard is `docs/plans/briefs/API_DOCUMENTATION.md`; read it before
writing a schema or a route. The reader is an integrator at a bank who has
never seen this codebase and cannot ask a question, so `openapi.json` is the
whole manual.

- **Every attribute carries a description** in full sentences: what the fact
  is in the bank's language, where it comes from (the library, the bank's own
  zone, an agent, the server) and what a reader must not conclude from it
  ("applies to us" is not "we comply"). A description that re-spaces the
  property name documents nothing.
- **Every value set is spelled out in words.** A kind enum names each member
  and what the system does differently for it. A vocabulary names its
  vocabulary and kinds, says the values are rows an admin may extend and
  points at the vocabulary endpoint; it is never presented as a closed enum,
  and never matched on the label.
- **Every limit is in the sentence, not only in the keyword.** Pagination
  default and maximum, the longest accepted text, which records need
  `If-Match` and that a stale ETag is 412, which calls need a step-up or an
  idempotency key, what is append-only or soft-delete-only, and which fields
  never leave the bank.
- **Every operation carries** a summary in the user's voice, a description
  saying when to call it, what it changes, which permission or scope it needs
  and what it records in the audit, at least one example from the prototype's
  data and never from a real bank, and each error `code` the caller must
  branch on with the condition that produces it.

`backend/scripts/api_docs_gate.py` reads the exported contract, never the
source, and blocks in `prepush.sh` and CI beside the contract-drift gate.
What is not documented yet is listed in `backend/scripts/api_docs_pending.txt`,
one line per schema class or operationId; the gate fails on a line that is
already documented and on anything undocumented that is not listed, so the
ledger only shrinks. It must be empty before R1 is called done.

## 2. Structural guard tests (playbook 5)

Built first, kept forever, in `apps/shared/tests_*.py`. Each fails with a
message that says what to do.

| Guard | Enumerates | Demands |
|---|---|---|
| Route permissions | Every Ninja operation | `@requires_permission` or `@requires_scope`, or listed in `UNGATED_BY_DESIGN` with a reason of shape `self`, `bootstrap`, `capability`, `logic-gate`, `public-token` |
| Row-level security | Every model with a tenant FK, against `pg_policies` and `pg_class` | RLS enabled and forced, a tenant policy exists |
| Database role | The app's role | Not superuser, not owner, no `BYPASSRLS` |
| Tenant isolation | Every tenant-scoped GET, PATCH, DELETE with another tenant's record | 404, never 403, never data |
| Library fence | The AST of every module writing a `LibraryModel` | Only inside `library_write()` in `proposals/apply.py`, `watch/write.py` (the watch door: the seven watch tables, no inventory table), reference seeds |
| Library door (ADR 0058) | Every `LibraryModel` table, `search_chunk` and the reference tables, from the app registry against `pg_trigger`; every proposal kind and watch step as cw_app | The `cw_library_door_guard()` trigger of shared 0008 with exactly the doors its table accepts; as cw_app a write outside a door refused and every real writer passing; each door named by one function and `seed` by the reference seeds only; the setting's name only where the `library-door` lint allows it |
| Four eyes | Every table in the four-eyes list | The requester-is-not-approver check constraint exists |
| Audit on write | Every non-GET operation through its scenario test | At least one `audit_event` written; a mutating route with no scenario fails |
| Kinds only | Every `TextChoices`, Postgres enum, generated TS union | In the tier-one allowlist with a reason |
| Vocabulary integrity | Every vocabulary with a `kind` | At least one active system row per kind, a default per list |
| Schema names | Every `Schema` subclass | No divergent schemas with the same class name across apps |
| Production guard | Django booted in subprocesses under environment names | Unrecognised names are production; `prod`, `Production`, `demo`, `dev` keep every guard on |
| Query ordering | The SQL behind each `.first()` | Ordered by the intended column |
| Seed integrity | The E2E seed | Two tenants; every fixed login has exactly the properties journeys depend on |
| Celery registration | Every task module | Every beat entry points at a real task; every tenant task wrapped in `@tenant_task` |
| Health | `/health/` | 200 all ok; 503 names the failing component; worker ping bounded |
| No query in logs | gunicorn's access format in `docker-entrypoint.sh` | Only method, path, status, size, time and request id atoms: no query, address, referrer, agent or request header |

Add a guard whenever a class of bug recurs; the docstring names the incident.

## 3. Frontend (playbook 6)

### 3.1 Data layer

One axios instance, never a second, never raw `fetch`. `api.generated.ts` is
generated and never hand-edited; types are imported from it
(`components['schemas'][…]`), never redeclared. `features/<domain>/api.ts` is
thin wrappers; `hooks.ts` owns query keys, invalidation and idempotency keys;
`*-presentation.ts` is pure functions with unit tests. TanStack Query for
server state, React state for local UI, no global store. **Fan out, never
chain.** Disable queries a surface cannot satisfy.

### 3.2 Navigation and permissions

One typed navigation registry (pure TypeScript) is the source of truth for
every destination: href, label key, surface (`tenant` or `console`),
`anyOfPermissions`, dock rank, group. Dock, sidebar, More menu, command
palette, the client gate and the role-matrix spec derive from it. Nothing in
UI code checks a role name. `<RequirePermission anyOf={…}>` renders children
or the quiet Restricted screen; its error boundary renders a server 403 the
same way with the server's `detail`. Never branch on an editable name.

### 3.3 Theming

Green Design System 2023 tokens, imported and never copied:
`scripts/build-tokens.mjs` writes `tokens.generated.css` (light under
`:root`, dark under `.dark`). `brand.css` is the only place our own values
live: it overrides the `brand-01` and `brand-02` variables (D-05). Light and
dark via `next-themes` (`attribute="class"`, system default). Tailwind colour
names map to token variables; never `text-white`/`text-black` for content,
never a hex in a component. Contrast is pinned by a unit test against WCAG
AA for every text-on-surface pair in both themes, including the six pill
tones. Every screen is checked in both themes. Green Core components only
after the D-04 spike proves them under `next start`. Use the Green MCP server
for token names; never recall them.

### 3.4 Typography

The numbered scale is replaced (`theme.fontSize` outside `extend`), an ESLint
rule fails any legacy or one-off size, including in template literals and
`cva` variants.

| Role | Use |
|---|---|
| `text-hero` | Public marketing headlines only |
| `text-display` | The page `h1`; a single headline figure |
| `text-title` | Section headings, card titles, stat-tile values |
| `text-body` | Running text, labels, cells, controls. The default on `<body>` |
| `text-meta` | Hints, captions, timestamps, ledes, notices, empty states |
| `.microlabel` | Uppercase with tracking: eyebrows, column heads, button labels |

Three weights, two families (Hanken Grotesk, Noto Sans Mono), `text-primary`
only on things you can press. `body` and `meta` stay separate names. Public
pages add Libre Caslon (`font-serif-display` for `text-hero`, `font-serif` for
section headings and ledes), loaded only by the `(public)` layout.

### 3.5 Screen copy

Screens say what the user is doing. A masthead gets one line of at most 60
characters or none; section descriptions are deleted (one per screen may
survive at 80 characters when it states a rule the operator cannot see); no
PRD ids, no restated invariants. Keep destructive confirmations, empty states
naming the next action, field hints stating a real constraint. A rule cut
from a screen goes into a code comment, never a tooltip. Every string in the
message catalogs in each shipped language; vocabulary labels from their rows.
Placeholders are dim italic and "e.g." prefixed.

### 3.6 Formatting and logging

`formatDate()`, `formatDateTime()`, `formatPartialDate()` for every date (UTC
or plain date plus precision in, user language and tenant timezone out).
`logger` from `shared/utils/logger`, never `console.log`. No tokens, PII or
tenant content in URLs, storage or logs.

**One named exception, and it stays one.** `GET /api/v1/calendar/feed.ics`
carries its token in the query string, because a calendar client sends no
header, follows no sign-in and subscribes by web address alone (D-52, ADR
0045). A token in the path would land in a hosting edge's request line, which
is the finding that moved invitation tokens out of paths; our own access log
prints the route and drops the query, proved by
`apps/shared/tests_no_query_in_logs.py` and, for this route, by
`test_no_token_prefix_or_secret_reaches_a_log_line` in `apps/home/tests_feed.py`,
which captures every configured logger at its handler. The address is
shown once, kept as a lookup prefix beside the secret's hash, revocable with
immediate effect, and it is never put in a screen's URL, in browser storage or
in a log line. `apps/home/tests_contract.py` reads the published contract and
fails if any second operation takes a credential in a query string.

### 3.7 Pills and labels

`design/system/pills-and-labels.md` is the source. Six tones named as Green
names them: `information` (grey), `notice` (blue), `positive`, `warning`,
`negative`, `brand`. No seventh; no component accepts a colour. Tone comes
from the slot (change type `notice`, scope facet `brand`) or the fixed `kind`
behind a severity scale (gap category `negative`); an admin supplies label,
translations and usage note only. Slot order is fixed per record type. One
`Pill` component, one presentation function per record type returning label,
tone and order, unit-tested. Computed pills ("2 open changes", "Change
pending: in force 1 Oct") are built from facts the API sends; the API never
sends a phrase. Labels are phrases (`new` reads "Needs triage"). Tenant tags
are an outlined `information` pill. `/dev/pills` renders every tone, slot and
record type and a Playwright screenshot pins it in both themes.

### 3.8 Mobile actions

On phones actions sit on the right; two buttons share one row, primary on
the right, secondary on the left.

## 4. From UI design to screens (playbook 7)

1. Direction is chosen (ADR 0020, source `design/README.md`).
2. Tokens from Green plus `brand.css`, the named type scale, contrast test,
   brand constants in `shared/brand.ts`.
3. System cards in `design/system/` become shared components; the pill card
   first; further cards committed before the screens that use them.
4. One `design/screens/<surface>-<screen>.html` per screen cut from the
   prototype; screens the prototype lacks are designed as cards first.
5. `docs/plans/UI_Implementation_Plan.md` maps every backend capability to a
   screen for every role, from the real endpoint inventory. A feature is
   covered when its screen exists, role variants render, empty, loading,
   error and denied states exist, and its `@e2e` journey is un-fixme'd.
   "Coming soon" is not shipped. A progress ledger at the top records
   corrections rather than overwriting.
6. Reachability audit after each wave: every mutation has a screen, every
   list a create path on an empty tenant, every list a detail, every detail
   an edit where allowed, every vocabulary manageable without a deploy.

## 5. Testing (playbook 8)

**Backend.** Django test framework under `config.test_settings`, on Postgres.
Tests required with every change for: footprint matching, "as of" selection,
the case state machine and guards, four eyes, proposal apply, tenant
isolation, vocabulary retire and merge, rank fusion. Concurrency tests use
real threads. The scenario base class fails a mutating request that wrote no
audit row.

**Coverage floors are a ratchet.** A global floor plus per-module floors on
tenancy, authentication, permissions, proposals, cases, register, footprint
matching, vocabulary, search, audit. Floors sit just below measured
coverage with a margin sized to the module (minus 2 at 400+ statements,
minus 3 at 100 to 400, minus 4 below 100). Never lower a floor to go green;
raise it when a module climbs. Record measured value, test count and date
beside each floor. The gate refuses to judge a partial run. Frontend: Vitest
thresholds per directory; a directory in `include` without a threshold is
not a gate.

**E2E (mandatory for every UI chunk).** One command: Playwright's `webServer`
recreates the throwaway database, migrates from zero, runs `seed_e2e`, boots
Django with the E2E flag and mock adapters, builds and starts Next in
production mode. Sign in through the UI with a passkey seeded into
`browserContext.credentials`; test private keys allowlisted in
`.gitleaks.toml` by exact literal. Never inject tokens or cookies, never mock
an API. The emailed code appears in exactly two journeys. Golden paths are
`@smoke`. Extend the seed (idempotent, deterministic, realistic, from the
prototype's data), never mock; `seed_e2e` refuses to run deployed. Every spec
imports `test` from `support/api-guard`; declared errors are declared where
they happen; the guard's default list is for known smells with a task each.
Read the screenshot and trace before touching anything. The four ways the
suite broke: clocks (anchor to tenant-local date plus fixed wall time),
branching before the page settles, text matching the wrong element (exact
text, distinctive spine, copy-drift check, one pinned language), retries
inheriting wreckage (teardown on failure). Push CI runs `@smoke`; nightly
runs everything; every chunk runs against a freshly seeded backend.

## 6. CI and quality gates (playbook 9)

Every gate blocks: migration drift, migration graph from zero, backend tests
under coverage, global and per-module floors, ruff (E4/E7/E9, F, B, DJ, S)
and mypy with every exclusion reasoned, compliance lint (`--all`), OpenAPI and
TypeScript drift with normalised export, frontend lint, typecheck, unit
coverage and build, E2E on the real stack, gitleaks on every push, osv-scanner
on committed lockfiles plus `npm audit` under `bash -eo pipefail` and
refusing an empty lockfile, CodeQL with its own SARIF gate (medium and above,
acceptances per fingerprint with a reason, stale ones reported),
requirements coverage, contract drift against `docs/inputs/openapi.yaml`,
API documentation against the standard (Section 1.8),
search and classification evaluation, message catalogs, pill gallery
screenshot, dependency licences (no copyleft, Apache attribution for Green),
container image scan.

Shape: tiered by a `changes` job (`base: ${{ github.ref_name }}` on push,
extglob not list negation, workflow changes count as everything); nightly
full run away from local midnight, never thinned; a timeout on every job;
explicit `permissions:`; concurrency cancels in-flight runs except the
schedule; never interpolate `${{ }}` into a script body; Dependabot grouped
weekly per ecosystem targeting `main`; failure artifacts kept two weeks. New
advisories on unchanged lockfiles are fixed same day with overrides or
floors, never `audit fix --force`; CodeQL fingerprints are re-triaged at the
new location, never on faith.

## 7. Performance budgets (playbook 10)

| Surface | Budget | Measured as |
|---|---|---|
| Any API endpoint | < 250 ms | `Server-Timing: app`, warm |
| Any screen | < 500 ms | To real data, not a skeleton |
| Hybrid search | < 800 ms without the reranker, < 1.5 s with it | `Server-Timing`, warm, evaluation corpus |
| Ask | First token < 2 s, streamed | Time to first chunk |
| Exports, imports, agent runs | Asynchronous with a status endpoint | Never inside a request |

Over budget is a bug. Measure before optimising and prove the fix with a
number. Never diagnose against `next dev`. Per request and per screen; fan
out. Usual causes: N+1 (pin with `assertNumQueries`), unindexed filters,
client waterfalls, per-request work that belongs in cache or the worker. The
API logs a WARNING above the budget with the request ID. One region for
every service, persistent connections. Lists paginate (20 default, 100 max).

## 8. Security and privacy (playbook 11)

**Boot guards** (`settings.py`, from the first commit): `IS_DEPLOYED_ENVIRONMENT`
is true when the host's variable is set at all or the name is not `local`,
`test`, `ci`; DEBUG never disarms a guard. When deployed refuse `DEBUG=True`,
a missing or default `SECRET_KEY`, the E2E flag, a mock LLM, embedder, agent
runner or mailer outside the one named test environment (where the UI shows a
banner), a database role that can bypass RLS, the local storage backend. Tests
boot Django in subprocesses to prove it.

How Phase 0 reads three of these rules (backend `config/settings.py`, ADR 0019):
the default `SECRET_KEY` literal (`django-insecure-dev-only-change-me`) is
accepted only when the environment is `local`, `test` or `ci` and refused on
every deployed name, whatever `DEBUG` says; a mock LLM, embedder, agent runner
or mailer is refused when deployed unless `ENVIRONMENT=test`, and non-deployed
names may use mocks (the test runner could not boot otherwise);
`EMBEDDER_PROVIDER=none` is not a mock but an explicit absence that fails
loudly on use and leaves search keyword-only, so a deployed environment can
boot before D-09 is settled.

**Runtime.** Passkeys only. Rate limiting on auth and expensive endpoints,
off in tests except the one test proving it fires. `ALLOWED_HOSTS` explicit,
CORS allowlist scoped to `/api/`, HSTS and secure cookies outside DEBUG,
`X-Frame-Options: DENY`, strict CSP, optional IP allow-list per tenant. ORM
only; the raw SQL the design needs (policies, triggers, the hybrid query) is
parameterised and lives in migrations or one search module. Secrets only in
host variables and GitHub secrets; dev-only defaults prefixed and allowlisted
by exact literal. Sentry on its EU region with `send_default_pii=False`,
`max_request_body_size='never'`, `include_local_variables=False`, `before_send`
and `before_send_transaction` scrubbers. Fetched web content is untrusted:
screened, flagged in `change_document.risk_flags`, never executed, never
rendered as HTML. GDPR export and deletion, audited personal-data access,
breach runbook, subprocessor register, B2B only. Tenant exit as a feature.

**Reviews.** A dated audit in `docs/security/` against the published OWASP
Top 10 of the year, re-run until findings converge. Production data protected
from accidental developer writes (ADR): model fences, ledger triggers with a
maintenance escape hatch, a read-only role for humans, backups and PITR
confirmed. An independent penetration test before the first bank tenant.

## 9. Git, environments and deploy (playbook 12)

One branch, `main`, during the build; small commits per whole slice, each
passing the checklist; the owner deploys `main` to the Railway test
environment. Before the first real tenant: `staging` → `main` with a second
reviewer and `main-branch-guard.yml`, recorded in an ADR (D-15). `.env.example`
lists every variable; the runbooks say where each lives. The entrypoint
migrates as the migrator role and seeds reference data idempotently on every
deploy, matching on immutable keys. Worker and beat are separate services
from the same image; business-time schedules run per tenant timezone in the
worker. Container-only, twelve-factor, nothing Railway-specific in code.
Non-root Dockerfile with a `HEALTHCHECK`. Test-only data changes never run in
production.

## 10. Working agreement (playbook 13)

**Session start:** `CLAUDE.md`, `docs/CONVENTIONS.md`, the `app.md` of every
app touched (and the screen card and UI plan row for UI work);
`IMPLEMENTATION_STATUS.md`, `TODO_FOR_alex.md`, `docs/DECISIONS.md`. Ask
rather than guess when still unclear. A guess that conflicts with a product
invariant is a stop.

**Product invariants need the owner.** Any task that would weaken one of
these stops and asks Alex:

| Invariant | PRD reference | Owner |
|---|---|---|
| The two zones and row-level security | NFR-01, AC-NFR1, AC-NFR2, playbook 14 | Alex |
| Proposals as the only door into the library | PRO-01, PRO-02, AC-PRO1 | Alex |
| Versions never overwritten | INV-04, AC-INV1, playbook 4.3 | Alex |
| An audit row with every write | AUD-01, AC-AUD1 | Alex |
| Four eyes and its step-up | ID-06, AC-ID3, AC-PRO2, AC-CAS1, FP-02, REG-01, REG-03, CAS-06 | Alex |
| "Applies" and "we comply" as separate facts | REG-01, REG-02, playbook 4.3 | Alex |
| Stable keys | VOC-01, INV-01, INV-03, playbook 4.3 | Alex |
| AI output labelled and logged | WAT-03, WAT-05, AUD-02, SRC-03 | Alex |
| No passwords and no code fallback | ID-02, ID-03, AC-ID1, AC-ID2 | Alex |
| Tenant content never in logs or unapproved model calls | NFR-04, playbook 4.7, D-07 | Alex |
| The case state machine's categories and guards | CAS-06, CAS-08, VOC-04, AC-CAS1 | Alex |
| The six pill tones | NFR-03, AC-NFR3, `design/system/pills-and-labels.md` | Alex |

Everything else has a default: take it from `docs/DECISIONS.md`, note it in
the commit body, keep building.

**Delivery.** Deliver the whole slice; if part is blocked, finish every other
part and say exactly what was left out and why, in the commit body and the
status file. Run the pre-push checklist before pushing. Keep code simple;
reuse before adding; extend a schema, hook or component rather than fork it.
Never lower a gate, never skip, disable or quarantine a test. When a class of
failure repeats, add a guard and record the incident in its docstring.
Review time-anchored fixtures against the clock rules.

**Commit messages.** A plain-English headline from the user's or the
system's point of view; a body with the request or incident and its date,
the requirement IDs, what now happens, the measurement, and what was
deliberately not done. No model identifiers or tool names.

**Where knowledge goes.**

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

## 11. Tenancy and zones (playbook 14)

| Zone | Holds | Isolation |
|---|---|---|
| Library | Instruments, provisions, obligations and versions, changes, sources, library vocabularies, search chunks | No `tenant_id`. `LibraryModel` refuses writes outside `library_write()`. Content changes only through approved proposals |
| Tenant | Footprint, register, gaps, cases, evidence, comments, tenant vocabularies, agent settings | `tenant_id` on every row, RLS enabled and forced |

- **Two database roles.** `cw_migrator` owns the tables and runs migrations.
  `cw_app` runs the application: no superuser, no ownership, no `BYPASSRLS`
  (ADR 0022). The boot guard checks the role.
- **Setting the tenant.** `ATOMIC_REQUESTS = True`. After authentication
  resolves the membership, `tenancy.activate()` runs
  `SET LOCAL app.tenant_id = …`. Policies read
  `current_setting('app.tenant_id', true)`, so an unset value matches no rows.
- **Tasks.** Every tenant task is wrapped in `@tenant_task`, takes the tenant
  id explicitly and activates it inside its own transaction.
- **Mixed tables** (`audit_event`, `ai_generation`, `problem_report`,
  `outbox_event`, `api_key`) show library rows to everyone and tenant rows to
  their tenant.
- **Private library records** carry `owner_tenant_id`; the policy is "shared
  or mine".
- **Platform staff have no bypass**; support access is a visible, time-boxed,
  logged grant.
- **Schema ownership.** Django migrations own the schema. Policies, triggers,
  functions, views, generated columns and HNSW indexes are `RunSQL` with
  reverse SQL. `docs/inputs/schema.sql` is the reference; `INPUT_DELTAS.md`
  says where to depart. snake_case columns, camelCase API.
- **Contract.** `docs/inputs/openapi.yaml` is the designed target; the
  exported `openapi.json` is the truth. `scripts/contract_drift.py` reports
  differences; each is fixed or recorded in `INPUT_DELTAS.md`.

## 12. Vocabularies and configuration (playbook 15)

A new type, status, tag or reason never needs engineering. A new rule always
does.

| Tier | Owner | Stored as | Examples |
|---|---|---|---|
| 1. Kinds | Engineering, through a PRD bump | Enum in code | Permissions, case status categories and transition guards, proposal kinds, applicability, evidence kind, actor type, pill tones, severity ordinals |
| 2. Library vocabularies | Platform console | Shared rows | Instrument levels, provision kinds per jurisdiction, change types, duty types, taxonomy dimensions and terms, library tags and flags, authorities, sources, languages, jurisdictions |
| 3. Tenant vocabularies | Tenant admin | Rows under RLS | Roles, teams, legal entities, products, tenant tags, sub-statuses, compliance status and risk scales, dismissal and close reasons, link kinds, reminder and escalation settings |

One abstract `Vocabulary` model (immutable `key`, optional fixed `kind`,
labels per language, `usage_note`, `sort_order`, `active`, `is_system`,
`is_default`), one generic endpoint set, one admin screen component.
Statuses live inside fixed categories; a category keeps one status; no
workflow engine. The API returns `key` and `kind`, never an enum of values.
Retire, never delete, showing the usage count first; merge re-points in one
audited transaction. Case-insensitive uniqueness and a near-duplicate check
on create ("Did you mean Custody?"). System rows can be relabelled, not
removed. Wide blast radius means dry run, preview, commit (footprint,
imports, bulk tagging). Library vocabulary changes go through the proposal
queue. Create where you use it ("Create" with `vocab.manage`, "Suggest"
otherwise). Filters, saved searches, reports, webhooks and exports store
keys. Tenant configuration is versioned and exportable. Admin permissions are
split: `members.manage`, `roles.manage`, `vocab.manage`, `workflow.manage`,
`security.manage`, `integrations.manage`, `agents.manage`.

## 13. Agents and AI (playbook 16)

`llm`, `embedder` and `agent_runner` each have one interface, a mock for
tests and E2E, and real providers chosen by a setting; production refuses a
mock at boot; fetch provider docs before implementing one and record them in
`Verification_Log.md`. The app is the scheduler of record: `backend/agents/`
holds versioned definitions only the platform changes (inside the API image,
which builds from `backend/` and seeds from them); `apps/agents` holds
per-tenant settings, schedules, research requests, runs and budgets. A tenant
admin controls which agents are on, cadence within plan limits, scope, run
now, pause, interrupt, history with findings and cost, a monthly budget cap
and an off switch for all AI; never instructions, tools or library writes.
Agent output goes to the tenant zone, the library as a proposal, or a
tenant-private library record. Agents read vocabularies at run start and
submit existing keys only (422 `unknown_key` with the valid list); a new term
is a proposal. Classifications are suggestions with a confidence until
confirmed. Re-tag requests are one batch proposal with a preview. Every model
call writes `ai_generation`. Ask quotes only retrieved chunks, cites every
statement, flags pending changes, returns `noAnswer` instead of guessing.
Until an EU-pinned inference path is contracted, no tenant-zone text goes to
a model except the Ask question, which a tenant can switch off (D-07).
`search_eval.py` is a gate.

## 14. Languages and jurisdictions (playbook 17)

Jurisdiction and language are data; no column, enum value or branch names a
country or a language. Translatable text lives in translation rows keyed by
language with the original marked and machine translations labelled (D-12,
ADR 0023). Search chunks exist per language with the matching Postgres text
search configuration. UI copy lives in message catalogs; `messages-check.mjs`
fails CI on a missing key; E2E runs in one pinned language. Users pick a UI
language and a content language order; dates, numbers and partial dates
format per language.

## 15. Assurance for bank customers (playbook 18)

Under DORA the product is an ICT third-party service. Build the evidence
under `docs/assurance/` as the product is built: subprocessor register with
locations, data flow diagram per zone, RTO and RPO, backup restore test log,
incident notification runbook, exit plan; exit as a feature (full export in
open formats, verified deletion); audit log streaming, IP allow-listing, the
support access log; an independent penetration test and a certification
path in `TODO_FOR_alex.md`.

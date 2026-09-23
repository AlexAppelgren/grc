# shared — Cross-cutting mechanics

> **App spec.** Source: `PRD.md` NFR-01–NFR-04 (AC-NFR1–AC-NFR3) and I18N-02, playbook
> 2.2, 5 (structural guards), 10, 11, 14, 17, `docs/inputs/INPUT_DELTAS.md` §4 and §5.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.
>
> `shared` has no domain of its own. Its code (`authentication.py`,
> `permissions.py`, `tenancy.py`, `audit.py`, `vocabulary.py`, `adapters/`,
> `middleware.py`, `storage.py`, `health_check.py`, `factories.py`,
> `e2e_seed.py`) and its tests belong to the backend; this file lists the
> scenarios so requirements coverage can find them. I18N-02 is frontend-owned
> and listed here because no backend app hosts it.

## 1. Business / user context

The floor every app stands on: two zones under row-level security that the
app role cannot bypass, `record()` on every write, the boot guards that fail
closed, the performance budgets, the design contract for pills and contrast,
EU-only hosting with the assurance pack, and the message catalogs that carry
every UI string in every shipped language. The structural guard tests of
playbook Section 5 live here and are kept forever.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| NFR-01 | Tenant isolation by row-level security, proven per route | M | R1 | built |
| NFR-02 | Performance budgets of playbook 10 | M | R1 | pending |
| NFR-03 | The design is reproduced: flow, labels, six-tone pill system, light and dark, WCAG AA | M | R1 | pending |
| NFR-04 | EU-only hosting and the assurance pack of playbook 18 | M | R3 | pending |
| I18N-02 | UI in `en` and `sv` at R1, the others by R3, from message catalogs | M | R1 | pending |

> **Note — I18N-02 at R1.** `en` and `sv` are built. Every UI string is in both catalogs
> (`check:messages`); a person switches their own interface language from the account menu
> in the rail, or from the More sheet below 1024 px, which saves it on them through
> `PATCH /me` and refetches every cached answer, so vocabulary labels arrive from their rows
> in the new language; dates, partial dates and times format per language in the tenant's
> timezone, a Swedish quarter reading "kv. 4 2026". I18N-S3 and I18N-S4 are the journeys.
> `da`, `nb` and `fi` come in chunk 13: their catalogs in `c13-i18n-da`, `-nb` and `-fi`,
> then `c13-i18n-wiring` turns them on and extends both journeys. Until then those language
> rows are content languages only, and the picker does not offer them. `<html lang>` stays the
> build default (an open question in `docs/TODO_FOR_alex.md`). The status cell above is set
> by `r1-close-and-readiness` after the batch E2E run.

## 3. Acceptance criteria (from PRD, condensed)

- **AC-NFR1** For every tenant route, a record of tenant A requested by tenant
  B answers 404.
- **AC-NFR2** The app refuses to boot on a database role that can bypass
  row-level security.
- **AC-NFR3** The pill gallery matches the design card in both themes, and
  every text pair passes WCAG AA.
- **Budgets:** API under 250 ms (`API_BUDGET_MS`, warning above it with the
  request id), screen under 500 ms to real data, list endpoints paginated
  (limit default 20, max 100), `Server-Timing: app` on every response.
- **Boot guards (playbook 11.1):** an unrecognised environment name is
  deployed; when deployed refuse `DEBUG=True`, a missing or default
  `SECRET_KEY`, the E2E flag, a mock adapter outside the one named test
  environment, a bypassing database role, the local storage backend.
- **Errors:** RFC 9457 problem details with `title`, `status`, `detail`,
  `code`, `errors[]`, `requiredPermission` on 403; an empty answer is 200.
- **Catalogs:** every string lives in `messages/<lang>.json`; a key missing
  in a shipped language fails CI; E2E runs in one pinned language.

## 4. Test scenarios (Gherkin)

Integration scenarios for `shared` live in the backend's `apps/shared/tests_*.py`
(the structural guards) and its `tests_scenarios.py`, which the backend agent
owns. E2E scenarios in `frontend/tests/e2e/shared.journey.spec.ts`, except NFR-S8, which
sits beside its screenshot baselines in `pills.gallery.spec.ts`. Each test carries its
scenario ID.

> **Note — NFR-01 and NFR-02 scenarios (`nfr-integration-scenarios`).** NFR-S1 to S6, S13
> and S16 assert their own Gherkin in `tests_scenarios.py`, through the entry points the
> guards use (`TENANT_SCOPED_ROUTES`, `check_role`, `pg_class` and `pg_policies`,
> `tenancy.activate` on cw_app, `@tenant_task` and the beat schedule, the middleware,
> `gate_of` and `UNGATED_BY_DESIGN`, the problem shape). Where the Gherkin says a new route,
> table, task or entry fails, the scenario plants one and reads the failure. NFR-S1 also
> demands that every GET, PATCH and DELETE under `/tenant/` addressing one record is in the
> registry. NFR-S6 walks every list GET in the exported contract: each takes `PageQuery` (limit
> 20 by default, 100 at most, 422 above, proven per route) or has a reason in
> `BOUNDED_BY_DESIGN`. NFR-S11, S12, S14 and S15 are NFR-04 and wait for chunk 14. The
> requirement status cells are set by `r1-close-and-readiness`.

### NFR-S1 — A record of tenant A requested by tenant B answers 404 on every tenant route `@integration` (NFR-01, AC-NFR1)
```gherkin
Given every tenant-scoped GET, PATCH and DELETE route Ninja registered
And a record in tenant A for each
When tenant B's session requests it
Then each answers 404, never 403 and never the record
And a new tenant route without this proof fails the tenant isolation guard
```

### NFR-S2 — The app refuses to boot on a role that can bypass row-level security `@integration` (NFR-01, AC-NFR2)
```gherkin
Given DATABASE_URL points at a superuser, a BYPASSRLS role or the table owner
When Django boots in a subprocess
Then it exits with a message naming the role property that is wrong
Given DATABASE_URL points at cw_app
Then it boots
```

### NFR-S3 — Every tenant table has row-level security enabled, forced and with a policy `@integration` (NFR-01)
```gherkin
Given every model with a tenant foreign key
When pg_class and pg_policies are read
Then each table has relrowsecurity and relforcerowsecurity true and a tenant policy
And a new tenant table without a policy fails the guard with the migration to add named
```

### NFR-S4 — An unset tenant matches no rows `@integration` (NFR-01)
```gherkin
Given a connection as cw_app without SET LOCAL app.tenant_id
When it selects from a tenant table
Then zero rows come back
When tenancy.activate(tenant_id) has run inside the transaction
Then only that tenant's rows come back
```

### NFR-S5 — Every tenant task is wrapped in @tenant_task and every beat entry exists `@integration` (NFR-01)
```gherkin
Given every Celery task module
Then every task that touches tenant data is decorated with @tenant_task and takes the tenant id explicitly
And every beat schedule entry points at a task that exists
```

### NFR-S6 — Every API response carries Server-Timing and the budget is enforced `@integration` (NFR-02)
```gherkin
Given any endpoint
When it is called
Then the response carries Server-Timing: app with the server time and a request id
When an endpoint exceeds API_BUDGET_MS
Then a WARNING is logged with the request id and the endpoint name
And list endpoints refuse a limit above 100 and default to 20
```

### NFR-S7 — Every screen reaches real data within its budget `@e2e` (NFR-02)
```gherkin
Given the seeded backend and a production Next build
When each registered destination is opened
Then real data, not a skeleton, is visible within 500 ms of navigation
And the measurement is recorded beside the screen in the UI plan
```

The journey (`shared.journey.spec.ts`) measures every tenant and console destination of the
navigation registry: the median of `E2E_SCREEN_SAMPLES` client-side navigations (5 by default)
to the destination's own real-data locator in `frontend/tests/e2e/support/screen-budgets.ts`,
500 ms unless its row says otherwise. A destination with no row, a locator that never shows, a
skeleton that lingers or a `next dev` build fails it. The medians go in the Measured column of
`docs/plans/UI_Implementation_Plan.md`.

### NFR-S8 — The pill gallery matches the design card in both themes `@e2e` (NFR-03, AC-NFR3)
```gherkin
Given the /dev/pills gallery route rendering every tone, slot and record type
When the screenshot spec runs in light and dark
Then both match the committed baselines from design/system/pills-and-labels.html
And each section's pills, tone and label in order, match the text pinned beside the screenshot
And a changed tone, label or slot order fails the spec
```

### NFR-S9 — Every text-on-surface pair passes WCAG AA in both themes `@e2e` (NFR-03, AC-NFR3)
```gherkin
Given the token pipeline output and brand.css
When the contrast test runs over every text and surface pair the design uses, including the six pill tones
Then each pair reaches the AA ratio in light and in dark
Given the pill gallery and the seeded Today, Watch, Inventory, an instrument, Roadmap, Search and the console queue in a browser under a light and a dark system theme
When every named pair is measured once per theme, and every pill on each screen, once it has loaded, against what is behind it, from the colours the browser computes
Then text and pills reach 4.5:1 and non-text 3:1 in both themes
```

### NFR-S10 — Tone is never chosen by a person and the API never sends a phrase `@integration` (NFR-03)
```gherkin
Given every vocabulary write endpoint
When a payload includes a tone or colour field
Then it answers 422
Given every list and detail response
Then pills are derivable from key, kind and counts only, and no response field holds a rendered phrase
```

### NFR-S11 — An unrecognised environment name is treated as production `@integration` (NFR-04)
```gherkin
Given ENVIRONMENT set to "prod", "Production", "demo" and "dev" in turn, and RAILWAY_ENVIRONMENT_NAME set with ENVIRONMENT "local"
When Django boots in a subprocess
Then every guard is on for each of them
Given ENVIRONMENT "local", "test" or "ci" without RAILWAY_ENVIRONMENT_NAME
Then the guards allow mock adapters and DEBUG
```

### NFR-S12 — The boot guards refuse an unsafe deployed configuration `@integration` (NFR-04)
```gherkin
Given a deployed environment name
When Django boots with DEBUG=True, or a missing or default SECRET_KEY, or E2E_MODE set, or a mock LLM, embedder, agent runner or mailer, or STORAGE_BACKEND=local
Then each boot fails with the offending setting named
Given the one environment named "test"
Then mock adapters are allowed and the API reports them so the UI can show its banner
```

### NFR-S13 — Every route is permission-gated or ungated by design with a reason `@integration` (NFR-01)
```gherkin
Given every operation Ninja registered
Then each is gated by @requires_permission or @requires_scope
Or it is listed in UNGATED_BY_DESIGN with a reason of the shape self, bootstrap, capability, logic-gate or public-token
And a new route with neither fails the guard
```

### NFR-S14 — /health/ names the failing component `@integration` (NFR-04)
```gherkin
Given the database, cache, worker and the pgvector extension are up
When /health/ is called
Then it answers 200 with each component ok
When the worker ping fails
Then it answers 503 with "worker" named and the ping bounded to one attempt
```

### NFR-S15 — Tenant content and personal data beyond name and id never reach logs or Sentry `@integration` (NFR-04)
```gherkin
Given the compliance lint runs over the whole tree
Then it fails on a log call that passes a note, comment, assessment, evidence or question body
And on a log call that passes contact details or a token
Given the Sentry configuration
Then send_default_pii is false, request bodies are never sent, local variables are off, and before_send and before_send_transaction scrub
Given a request whose query string holds what someone searched for
Then no access log line or application log line holds the query, the client address, the referrer or the user agent
And gunicorn's access logger never reaches Sentry, and a breadcrumb message loses any query string and address
Given an exception whose message, or a cause's, carries row values
Then Sentry receives its type, module and frames, never its message, and a log event keeps its template but not what was interpolated into it
```

### NFR-S16 — Every error uses one shape and an empty answer is 200 `@integration` (NFR-01)
```gherkin
Given a validation failure, a denied request, a stale write and a missing record
Then each answers problem details with title, status, detail and code
And the 403 adds requiredPermission and the 422 adds errors[]
And a filtered list that matches nothing answers 200 with an empty collection
```

### I18N-S3 — Every UI string is in the catalog for every shipped language `@e2e` (I18N-02)
```gherkin
Given the message catalogs for en and sv
When messages-check.mjs and ESLint run
Then messages-check.mjs fails on any key missing in either language and ESLint on any string literal in JSX text
When a user switches the UI language to sv
Then every screen renders in sv with vocabulary labels from their sv rows
```

### I18N-S4 — Dates, numbers and partial dates format per language and timezone `@e2e` (I18N-02)
```gherkin
Given a user with language sv in a tenant in Europe/Stockholm
When a deadline stored as UTC and an in-force date with quarter precision render
Then formatDateTime shows the Stockholm time in Swedish and formatPartialDate shows "kv. 4 2026"
And E2E journeys run in the one pinned language
```

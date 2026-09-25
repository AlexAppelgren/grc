# R2: the rules every package shares

Written 2026-09-25 by `r2-plan-docs`, wave 1 of the R2 build. Every R2 package reads this
file after `CLAUDE.md` and before its own brief. It holds what no single brief can: the
rules for shared files, the migration and decision numbers handed out in advance, who owns
each page shell, and the safety rules that cut across chunks 8 to 11. Where
`docs/plans/PARALLEL_PLAN.md` or a chunk brief disagrees with this file, this file wins;
where this file disagrees with `CLAUDE.md` section 5 or `PRD.md`, they win and the package
stops and reports. The cloud session's own standing rules are
`docs/plans/r2-waves/CLOUD_SESSION.md` on the plan branch.

## (a) Shared files: your own clearly separated block, nothing else

Many packages build from the same base at once. Each one touches a shared file only by
adding or changing its **own** block, so every merge stays mechanical. A block is one
contiguous, labelled piece that names the package or the scenario it belongs to; never
reorder, reformat or re-sort what another package wrote.

| Shared file | Your block is |
|---|---|
| `backend/apps/<app>/app.md` | Your requirement rows, your status cells, your scenarios |
| `backend/apps/<app>/tests_scenarios.py` | Your own test function (and the removal of its own `@skip`) |
| `frontend/tests/e2e/<app>.journey.spec.ts` | Your own `test` block |
| `backend/apps/shared/e2e_seed.py` | Your own seed function, called once from the entry point |
| `backend/apps/shared/tests_seed_integrity.py` | Your own assertions |
| `backend/apps/shared/kinds.py` | Your own kind |
| `backend/apps/shared/tests_rls.py` and the other guard lists | Your own entries: `FOUR_EYES_TABLES` in `tests_four_eyes.py`; `UNGATED_BY_DESIGN` and the route lists in `permissions.py`; `TENANT_SCOPED_ROUTES` in `routes.py`; `PLATFORM_ROUTE_REQUESTS` in `apps/governance/tests_scenarios.py` |
| `backend/apps/shared/factories.py` | Your own factory functions |
| `backend/config/settings.py` | One labelled block, its Celery beat entries included |
| `.env.example` at the repository root | Your own lines. There is no `backend/.env.example`; a brief that names one means the root file |
| `docs/runbooks/RAILWAY_VARIABLES.md` | Your own rows |
| `docs/inputs/INPUT_DELTAS.md`, `docs/plans/briefs/HARDENING.md` | Your own rows |
| `docs/DECISIONS.md` | Your pre-assigned row, section (c) |
| `docs/TODO_FOR_alex.md` | One block headed with your package key |
| `docs/plans/UI_Implementation_Plan.md`, `design/system/pills-and-labels.md` | Your own rows |
| `docs/plans/Verification_Log.md` | Your own entries |
| `backend/scripts/contract_drift_pending.txt`, `backend/scripts/api_docs_pending.txt` | Deleting your own lines only |
| `backend/config/api.py` | One mount line |
| `frontend/src/shared/i18n/messages.ts` | Your own catalog registration |
| `frontend/src/shared/navigation/registry.ts` | Your own entry |
| `frontend/src/features/shared/tone-by-kind.ts` | Your own kind's tones |
| The message catalogs, `en` and `sv` | Your own keys |

`openapi.json` and `frontend/src/types/api.generated.ts` are generated: regenerate them
with `bash generate-types.sh` to build and typecheck, and do not commit them from a cloud
session (the runbook's rule 4). The integrator regenerates and commits both from the merged
tree, so a hand-merged copy never lands.

## (b) Migration numbers

Each app's numbers are handed out in advance so the merged graph has one leaf per app.

| App | Number | Package |
|---|---|---|
| tenants | 0002 | c8-org-models |
| tenants | 0003 | c8-teams-model |
| tenants | 0004 | c8-ten-support-grants |
| taxonomy | 0009 | c8-vocab-lists-rules |
| taxonomy | 0010 | c8-teams-model |
| taxonomy | 0011 | acc-scope-and-reach |
| taxonomy | 0012 | d89-scope-items-model |
| register | 0001, 0002 | c8-register-models |
| register | 0003 | c8-reg-units |
| register | 0004 | c8-duty-occurrences |
| collab | 0001 | c10-collab-models |
| collab | 0002 | c8-participants |
| cases | 0002, 0003 | c9-case-models |
| cases | 0004 | c10-case-triage-due |
| cases | 0005 | c9-owner-team-and-reassign |
| agents | 0004, 0005 | c11-agent-models |
| agents | 0006 | acc-foundation |
| agents | 0007 | d89-agent-research |
| identity | 0006 | c8-retire-applicability-request |
| identity | 0007 | acc-foundation |
| identity | 0008 | c11-signin-policy-enrol |
| identity | 0009 | c8-support-session-guard |
| governance | 0004 | acc-scope-and-reach |
| governance | 0005 | acc-entries-and-log |
| governance | 0006 | acc-summary-j11 |
| proposals | 0008 | c11-proposal-batches-model |
| proposals | 0009 | d89-proposal-owner |
| proposals | 0010 | c8-recurring-duty-proposal, only if the kind's choices need one |
| proposals | next free | d89-controls |
| library | 0010 | c8-recurring-duty-library |
| library | 0011 | x-jurisdictions-by-proposal |
| library | 0012 | d89-child-rls |
| shared | 0009 | c10-workflow-policy |
| shared | 0010 | x-jurisdictions-by-proposal |
| reports | 0001 | x-exports-contract |

A package writing migration N in an app depends on the package that owns N-1 in that app,
so a build from its dependencies' branches has exactly one leaf. If your number is already
taken when you build, take the next free number and depend on the one before it; never
leave two leaves, and never merge migrations to hide one.

## (c) Decision numbers

| Row | ADR | Package | What |
|---|---|---|---|
| D-91 | 0059 | r2-spec-d89 | The R2 spec of D-89 |
| D-92 | 0060 | c9-triage | The one-person close (q-case-close, Option B) |
| D-93 | | x-hardening-agent-runs | Named in its brief |
| D-94 | | x-jurisdictions-by-proposal | Named in its brief, ADM-02 languages included |
| D-95 | | r2-plan-docs | TEN-04 is built in chunk 10, by default, pending Alex's answer on the reorder |
| D-96 | | r2-banking-groups-brief | Named in its brief: when D-69 is built |
| D-97 | | r2-plan-docs | D-25 amended by default: a WAT-04 link confirmed by a person, or by an independent agent under D-74, counts for My work; an unconfirmed suggestion never does |

A package that needs a row not listed here numbers it D-9x with its package key in the
row, and the integrator gives it the next free number. An ADR is written only where the
table names one.

## (d) Logins

E2E logins come only from `r2-e2e-login-roster`. A journey that needs a person with a role
or a negative case not on the roster asks for the roster to grow; it never seeds a login of
its own.

## (e) Contracts, stubs and documentation

- A contract stub raises `ProblemError(status=501, code="not_built")` literally, behind its
  real gate: the auth class, `@requires_permission` or `@requires_scope`, and
  `@requires_step_up` where the finished route will need it
  (`docs/plans/briefs/API_DOCUMENTATION.md` section 4b).
- Every operation is fully documented when it is written, stub or not:
  `python backend/scripts/api_docs_gate.py --app <app>` is clean for your app.
  `backend/scripts/api_docs_pending.txt` only shrinks, and `VOCABULARY_PROPERTIES` is an
  append-only ledger.
- A stub on a `/tenant/` route that takes an id loads its record under row-level security
  first, so another tenant gets 404 before it ever sees a 501.
- The package that makes a tenant-scoped id route answer for real registers it in
  `TENANT_SCOPED_ROUTES` with a factory, in the same package.

## (f) The demo recordings

Never commit `frontend/src/features/demo/recordings.json` or `recorded-at.json`. The
integrator re-records them once per merged wave.

## (g) Page shells and who owns each panel file

| Page | Shell owner |
|---|---|
| The obligation page | c8-fe-obligation-shell |
| The change page | c9-fe-cases-shell |
| Organisation | c8-ui-organisation |
| Agents (admin) | c11-fe-admin-agents |
| Security (admin) | c11-fe-admin-security |

The shell owner writes the page and one mount point per panel. Every other package owns
only its own panel file and mounts it at its point; it never edits the shell.

## (h) Performance routes

Only `r2-perf` edits `backend/perf/routes.py`.

## (i) Who runs which tests (D-67)

A builder runs the static gates and the suites of the apps it touched, and writes its
journeys in full. The integrator runs the whole backend suite, the coverage floors and the
E2E journeys once per merged wave, and CI on `candidate` stays the authority.

## (j) Corrections to the earlier briefs

- The roadmap is `apps/home/roadmap.py`, a query, not a database view.
- Storage is `apps/shared/storage.py`.
- D-75 voids applicability requests: there is no request, no applicability queue count and
  no `pendingApplicability` on the obligation row. `c10-tag-filters-and-limits` retires the
  field.
- Member removal is `POST /tenant/members/{userId}/remove`.
- Export jobs, not import jobs, move into R2 as `x-exports-contract` (the `ExportJob`
  framework and `/exports`). Import stays R3.
- `closeWithoutAction` lives in `apps/cases/triage.py`, not in `assessment.py`.
- `addAction` owns the move from `assessing` to `implementing`; saving an assessment moves
  no state.
- Comments register `obligation`, `change_case`, `tenant_obligation` and `action` as
  subjects, and not `change`: a bank's change page is its case.

## (k) A response the shipped frontend reads

A package that changes a response the shipped frontend reads keeps `npm run typecheck`
green in the same package: it fixes the consumer minimally and lists that file as owned.

## (l) Nothing overwritten

`CLAUDE.md` section 5: actions, internal links and Statement of Applicability units are
removed by setting `removed_at` and `removed_by`, and their model's `delete()` raises. Only
D-53 (retention) and D-56 (tenant exit) delete whole rows.

## (m) What an audit row or an outbox payload may carry

A before or after value in an audit row, and an outbox payload, carry ids, keys, dates and
the fields a requirement names (the applicability reason, AC-REG1). Never a comment body, a
note, assessment or interpretation text, or any description a person typed
(`CHUNK10_TASKS.md` rule 13). From wave 3 the compliance lint refuses the keys `body`,
`text`, `comment`, `note`, `summary`, `assessment` and `question` in those values.

## (n) D-89 packages

D-89 packages are not owner-blocked: D-89 put them in R2. Free text a bank types reaches no
model until Alex answers the tenant-text question (`docs/TODO_FOR_alex.md`, "R2 starts"), so
a tenant agent run is given keys only.

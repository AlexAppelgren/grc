# PRD 0.4 consolidation: what landed

One documentation change, in one commit, turning Alex's fourteen answers of
2026-09-19 into PRD 0.4 and everything that must land with it. The input was
`docs/plans/briefs/OWNER_RECOMMENDATIONS.md` — its fourteen researched sections
and its "Alex's answers" table, which reached `main` while this ran and is left
as `main` has it. The precedent was
`docs/plans/briefs/PRD_0_3_CONSOLIDATION.md`. Written 2026-09-20 by the cloud
session on `claude/prd-0-4-consolidation-ueuqak`.

Nothing here is built. Every ID below is a row in a document; the code that
implements it lands with the packages the ADRs name.

## 1. The answers and the IDs they were given

| # | Key | Decision | ADR | PRD 0.4 |
|---|---|---|---|---|
| 1 | q-urgency | D-48 | — (INPUT_DELTAS §1 already records the fixed rows) | no change |
| 2 | q-support-access | D-49 | 0042 | §6 `support_access.grant` and `security.manage` |
| 3 | q-Q1 (replaced by Alex) | D-50 | 0043 | PRO-03, AUD-03, WAT-01, ADM-02 |
| 4 | q-search-fence | D-51 | 0044 | no change |
| 5 | q-feed-token | D-52 | 0045 | no change |
| 6 | q-retention (replaced by Alex) | D-53 | 0046 | AUD-04 |
| 7 | q-eu-guards | D-54 | 0047 | no change |
| 8 | q-credential | D-55 | 0048 | no change |
| 9 | q-exit | D-56 | 0049 | REP-04, §6 `security.manage` |
| 10 | q-private | D-57 | 0050 | INV-07, PRO-03, WAT-06, §6 `private_records.approve` |
| 11 | q-sso | D-58 | 0051 | ID-02, ID-12 |
| 12 | q-platform-counters | D-59 | 0052 | ADM-02 |
| 13 | q-private-notes | D-60 | — (ADR 0028, moved to accepted) | no change |
| 14 | agents (Alex's own) | D-61 | 0053 | AGT-03, AGT-04, AGT-05 |

New ADR files: `0042-support-access-granted-by-the-bank.md`,
`0043-problem-reports-stay-in-the-bank.md`,
`0044-search-index-is-derived-data.md`,
`0045-calendar-feed-token-in-the-query-string.md`,
`0046-retention-by-age-of-last-use.md`,
`0047-eu-only-processors-refused-at-boot.md`,
`0048-credential-policy-takes-effect-at-a-notice-date.md`,
`0049-tenant-exit-needs-two-people-and-deletes-everything.md`,
`0050-private-records-approved-inside-the-bank.md`,
`0051-sso-proves-identity-the-passkey-signs-in.md`,
`0052-platform-counters-window.md`,
`0053-bleqq-agents-are-the-base-package.md`. Each carries status `accepted`,
not `accepted by default`, because the owner answered.

## 2. New scenario IDs

Each `@integration` scenario has its `@skip("pending: <ID>")` stub in the app's
`tests_scenarios.py`; the one `@e2e` scenario has its `test.fixme` stub.

| Scenario | App | Tags | About |
|---|---|---|---|
| ID-S27 | identity | `@integration` | SSO proves identity and never opens a session on its own |
| ID-S28 | identity | `@integration` | A SCIM key carries one scope and its default role holds no admin permission |
| ID-S29 | identity | `@integration` | A stricter passkey policy binds new passkeys now and old ones from its notice date |
| TEN-S11 | tenants | `@integration` | A support session reads and never writes, and never approves itself |
| TEN-S12 | tenants | `@integration` | A closing tenant refuses writes and still lets people sign in and export |
| REP-S7 | reports | `@integration` | Tenant exit needs two different people, each with a passkey |
| REP-S8 | reports | `@integration` | Execution refuses until its conditions are met, and deletes nothing through the app role |
| INV-S13 | library | `@integration` | A private record's text never reaches a model, the index or another bank |
| PRO-S12 | proposals | `@integration` | A private proposal is approved inside the bank and never reaches the console |
| WAT-S12 | watch | `@integration` | A run re-checks the library records of the sources it checked and proposes the correction |
| AGT-S13 | agents | `@integration` `@e2e` | A bank cannot switch off, pause or re-scope one of bleqq's agents |
| AGT-S14 | agents | `@integration` | A bank's own agent writes only in its own zone |
| AUD-S8 | governance | `@integration` | The ledger purge refuses a cutoff inside the floor and a paused tenant |
| ADM-S7 | governance | `@integration` | The console reads each bank's figures through one audited window |

Rewritten in place, keeping their IDs and tags: ID-S12 (re-enrolment on a
verified SSO domain), ID-S23 (the SSO stance), TEN-S6 (request, approve,
revoke), REP-S5 (four eyes, read-only period, deletion, tombstone), INV-S9
(no platform read, no child row under a shared parent), PRO-S7 (the report
stays in the bank), WAT-S8 (a private source is a checked public page), AGT-S4
and AGT-S5 (bleqq's agents versus the bank's own), AUD-S5 (the report stays in
the bank), AUD-S6 (ten years after last use).

## 3. Every file changed

| File | What changed |
|---|---|
| `PRD.md` | Version row 0.4 (2026-09-20, decided by Alex). ID-02, ID-12, INV-07, PRO-03, WAT-01, WAT-06, AGT-03, AGT-04, AGT-05, REP-04, AUD-03, AUD-04, ADM-02. §6: the new `private_records.approve` row, the widened `security.manage` and `support_access.grant` descriptions, and the closing note |
| `CLAUDE.md` | §5 only: the two named exceptions to "Nothing overwritten", one sentence each (retention by age, tenant-exit deletion) |
| `docs/DECISIONS.md` | D-48 to D-61; D-22's open question closed; the closing paragraph |
| `docs/adr/` | Twelve new ADRs (0042 to 0053); 0028 moved to accepted; the index gains their rows, drops the SSO stance from "still to write", and gains a closing paragraph |
| `docs/inputs/INPUT_DELTAS.md` | One "PRD 0.4" block of eleven rows, appended after the chunk 3 rows a running task owns |
| `backend/apps/identity/app.md` | §1 (the SSO stance and the credential-policy timing), ID-07 and ID-12 rows, ID-S12 and ID-S23, ID-S27 to ID-S29 |
| `backend/apps/tenants/app.md` | §1 (support access, exit), TEN-06 row, TEN-S6, TEN-S11, TEN-S12 |
| `backend/apps/reports/app.md` | §1 (exit), REP-04 row, REP-S5, REP-S7, REP-S8 |
| `backend/apps/library/app.md` | §1 (private records), INV-07 row, INV-S9, INV-S13 |
| `backend/apps/proposals/app.md` | §1 (reports stay in the bank, private proposals), PRO-03 row, PRO-S7, PRO-S12 |
| `backend/apps/watch/app.md` | §1 (the re-check, bleqq's agents), WAT-01 and WAT-06 rows, WAT-S8, WAT-S12 |
| `backend/apps/agents/app.md` | §1 (two kinds of agent), AGT-03 to AGT-05 rows, AGT-S4, AGT-S5, AGT-S13, AGT-S14 |
| `backend/apps/governance/app.md` | §1 (reports, the counters window, the two deletions), AUD-03, AUD-04 and ADM-02 rows, AUD-S5, AUD-S6, AUD-S8, ADM-S7 |
| `backend/apps/collab/app.md` | §1 and COL-01: private notes are not built and will not be |
| `backend/apps/*/tests_scenarios.py` | Skipped stubs for the thirteen new `@integration` scenarios (agents, governance, identity, library, proposals, reports, tenants, watch); identity's module docstring lists the new skips |
| `frontend/tests/e2e/agents.journey.spec.ts` | One `test.fixme` for AGT-S13 |
| `docs/TODO_FOR_alex.md` | The "Decisions the parallel build waits on" table replaced by its closure; the private-notes item closed; a "PRD 0.4" read item; a new "Open details from those answers" section |
| `docs/plans/briefs/PRD_0_4_CONSOLIDATION.md` | This brief |

## 4. Defaults taken, where the task left a choice

- **An ADR per item.** The task said one ADR per item whose recommendation asks
  for one. D-48 and D-60 therefore have none: each confirms a design already
  recorded, so there was no new architectural decision to write down, and the
  ADR index says so. Item 14 has no recommendation section at all, being Alex's
  own, but it changes three PRD requirements, so it was given ADR 0053.
- **Where the retention scenarios went.** The task named the reports app for
  retention. AUD-04 and AUD-S6 live in `governance/app.md`, so the retention
  rows and scenarios went there and the reports app took tenant exit (REP-04).
  A scenario may reference a requirement hosted elsewhere, so coverage is
  unaffected.
- **No new PRD requirement IDs.** Every answer fitted an existing requirement's
  text, so 0.4 changes wording rather than adding rows. Only one new constant
  appears: `private_records.approve` in §6.
- **The apps the search fence and the calendar feed touch.** D-51 and D-52
  change no requirement's text, so `search/app.md` and `home/app.md` were left
  alone; both decisions are carried by their ADR, their DECISIONS row and their
  INPUT_DELTAS row.
- **CONVENTIONS 3.6.** ADR 0045 names the calendar feed as the one route that
  reads a token from the query string. The exception's own line in
  `docs/CONVENTIONS.md` lands with `c6-upcoming-calendar-backend`, which builds
  the route and the guard test, because the task's owned paths do not include
  that file.
- **Priorities and releases are unchanged.** No answer moved a requirement's
  MoSCoW letter or its release; §7's release plan already names SSO, retention
  and tenant exit in R3.

## 5. What this change deliberately did not touch

`docs/plans/briefs/CHUNK*_TASKS.md`, `docs/plans/PARALLEL_PLAN.md` and
`docs/plans/briefs/HARDENING.md` (another session replans them), the INV-03 to
INV-06 rows of `backend/apps/library/app.md` and the obligation-detail rows of
`docs/inputs/INPUT_DELTAS.md` (a running task owns them), and all application
code: models, migrations, API modules, messages and seeds. `docs/plans/Build_Plan.md`,
`UI_Implementation_Plan.md` and `IMPLEMENTATION_STATUS.md` were left to the
replanning session, because every package the answers change is one it is
already rewriting.

## 6. What a reviewer should read first

PRD.md's 0.4 row against the fourteen answers; CLAUDE.md §5, where the two
deletions are the only bend in an invariant; ADR 0043 and ADR 0046, the two
places where Alex replaced a recommendation; and the "Open details" section of
`docs/TODO_FOR_alex.md`, which is where the four unanswered points now live.

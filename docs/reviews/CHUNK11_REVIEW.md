# Security review of chunk 11: agents, security policy, credentials and batches

Package `security-review-c11`, wave 7 of the R2 build, 2026-09-27. Requirements AGT-03 to
AGT-06, PRO-04, ID-08 (ID-07 is out of R2, D-100).

**Commit read:** `bdf191d` on `claude/r2w7-security-review-c11`, which is `origin/main`
(`7242ac8`) with the six dependency branches merged: `c11-tenant-controls-cap`,
`c11-research-requests`, `c11-e2e-console`, `c10-fe-prefs-and-ooo`, `c11-fe-admin-security`
and `c11-agent-config-platform`, and through them every earlier chunk 11 package. The review
read the diff `origin/main...bdf191d`, and the whole of `backend/apps/agents/`, the session
policy, the passkey flags and the batch decide, since part of chunk 11 (the session policy,
the batch filing, the runner and the contract) was already on main from wave 2.

The six guard suites (`tests_rls`, `tests_tenant_isolation`, `tests_library_fence`,
`tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`) and the rest of
`apps.shared`, `apps.agents`, `apps.proposals` and `apps.identity` were green on `bdf191d`
(1311 tests, 20 skips with named reasons), and green again with the fixes.

## Summary

One high and nine medium findings, all fixed in this package, each with a test written first
that failed without the fix (`backend/apps/agents/tests_security_review.py`,
`backend/apps/identity/tests_security_review.py`). One high finding is latent and deferred
with its guard named (F11). The low findings are HARDENING rows H80 to H95.

| # | Severity | Finding | Status |
|---|---|---|---|
| F8 | high | The person who asked for a re-tag could approve the batch their request produced | fixed |
| F1 | medium | The cap before a run ignored what open runs may still spend | fixed |
| F2 | medium | A research request skipped the pause, the off switch, the run budget and the spend lock | fixed |
| F3 | medium | `check_url` fetched before the quota, the AI switch and the cap were checked | fixed |
| F4 | medium | `check_url` had no overall deadline: a page sent a byte at a time held a request thread | fixed |
| F5 | medium | The cap's second point read the spend without the spend lock | fixed |
| F6 | medium | The AI switch did not stop a run already open | fixed |
| F7 | medium | A PATCH of a bank's agent could write back over a cap pause it had not seen | fixed |
| F9 | medium | A person could file proposals under an agent's keyless run | fixed |
| F10 | medium | An idle limit no longer than the access token's life signed working people out | fixed |
| F11 | high, latent | Nothing polls the runner, so no run's cost ever arrives and the cap's second point never fires | deferred, H80 |

## Findings

### [HIGH] F8, four eyes: the requester of a re-tag approves its batch
- Where: `backend/apps/proposals/batch.py` `decide`, `backend/apps/agents/requests.py`
  `file_retag`.
- Scenario: a library editor asks for a re-tag in the console
  (`POST /console/research-requests`, `proposals.review`); bleqq's sweeper files the batch
  through `file_retag` as the agent, so `proposed_by_user_id` is null; the same editor steps
  up and `POST /proposal-batches/{id}/decide {"rest": "approved"}` answers 200 and rewrites
  the scope terms. One person commissioned the change and let it into the library. The
  decide compared only `proposed_by_user_id`, and the database's row trigger and
  `proposal_four_eyes` compare the same column, so neither saw the requester. The route's
  published description said the requester was refused.
- Breaks: CLAUDE.md section 5, four eyes (the approver is an independent second principal).
- Fix: `decide` also refuses, 409 `four_eyes_violation` under the batch's lock, the person
  whose request opened the run that filed the batch (`_requested_by`, from
  `agent_run.requested_by`). The operation's description now says which of the two the
  database enforces. Test: `TheRequesterIsNotTheSecondPerson`.
- Left: the database backstop for the requester (H93): a trigger change is a proposals
  migration, whose numbers other packages hold.

### [MEDIUM] F1, cap: open runs reserved nothing
- Where: `backend/apps/agents/tasks.py` `fits_the_cap`, `backend/apps/agents/budget.py`.
- Scenario: with a cap of 20 and nothing spent, ten "Run now" calls (or the beat and run
  now) each took the spend lock in turn, each read a spend of 0 because an open run's
  `cost` stays null until the runner reports, and all ten opened: 50 promised against 20.
- Breaks: AGT-04, AGT-S6 ("a run that would exceed the cap is not started").
- Fix: `budget.held` counts a finished run's cost and an open run's larger of its cost so far
  and its `budget_limit`; `fits_the_cap` reads it. `spend` (what the page shows and the mid-
  run check reads) is unchanged. Test: `TheCapCountsOpenRuns`.

### [MEDIUM] F2, cap and controls: a research request walked around run now's refusals
- Where: `backend/apps/agents/requests.py` `create_request`.
- Scenario: the beat pauses an agent for the cap because spend + 5 > cap (spend 18, cap 20);
  a research request read `at_cap` (18 < 20), never looked at `paused_at` or `enabled`, took
  its own lock rather than the spend lock, and opened a run of the paused agent with a budget
  of 5.
- Breaks: AGT-04, AGT-05.
- Fix: the request refuses a switched-off or paused agent with run now's codes
  (`tenant_agents.refuse_stopped`, now shared by both) and checks the run's budget with
  `tasks.fits_the_cap`, under the same `agent_spend` lock. Test:
  `ARequestStopsWhereRunNowStops`.

### [MEDIUM] F3, SSRF surface: the address was fetched before the request could be refused
- Where: `backend/apps/agents/requests.py` `create_request`.
- Scenario: a bank over `RESEARCH_REQUESTS_PER_MONTH`, with AI off or at its cap, still got
  a real outbound fetch of up to 1 MB per call, then a 429 or 422: the quota did not limit
  the fetcher, and the switch did not stop agent-side network work.
- Fix: every refusal runs first; the fetch is the last step before the row is written.
  Test: `test_check_url_fetches_nothing_when_the_request_would_be_refused`.

### [MEDIUM] F4, SSRF: no overall deadline on a fetch
- Where: `backend/apps/agents/requests.py` `_get`, `_fetch`.
- Scenario: the socket timeout bounds each read, not the fetch; a server sending one byte a
  second held `read()` indefinitely (a local probe held it 6 s against a 2 s timeout), over up
  to four hops, inside the request's open transaction (`ATOMIC_REQUESTS`). Eight such
  requests took every API thread.
- Fix: one deadline per fetch, `RESEARCH_URL_TOTAL_SECONDS` (15 by default, an env setting),
  shared by every hop; the body is read one network read at a time (`read1`), each waiting
  no longer than what is left, and a watchdog shuts the socket at the deadline, which also
  ends a status line or headers sent a byte at a time inside `http.client`. Tests: `OneDeadlinePerFetch`. The same class fixes two low
  findings at the same boundary: a malformed address or redirect (`https://[x]/`) answers 422
  `url_not_allowed` instead of 500, and an IPv4 address inside NAT64 (`64:ff9b::/96`) or the
  IPv4-compatible form (`::/96`) is judged as that IPv4 address.

### [MEDIUM] F5, cap: the second point read the spend without the lock
- Where: `backend/apps/agents/runner_events.py` `_hold_to_the_cap`.
- Scenario: events for two runs applied at once each missed the other's uncommitted cost, so
  both passed `spend <= cap`.
- Fix: the check takes `budget.SPEND_LOCK` before reading the spend. Test:
  `test_the_spend_is_read_under_the_banks_spend_lock`.

### [MEDIUM] F6, AI switch: an open run kept going after the bank switched AI off
- Where: `backend/apps/agents/runner_events.py`.
- Scenario: `set_ai_enabled(False)` stops every new model call and run, but a bank's run
  already open kept reporting model work and spend.
- Breaks: CLAUDE.md section 5 (every model call gated), AGT-S6.
- Fix: an event for a bank's run whose bank has AI off stops the run through the runner with
  the reason `feature_off` and pauses nothing. Test:
  `test_an_event_after_the_bank_switched_ai_off_stops_the_run`.

### [MEDIUM] F7, cap: a PATCH could undo a cap pause
- Where: `backend/apps/agents/tenant_agents.py` `update_tenant_agent`.
- Scenario: a PATCH read the agent unlocked, `put_budget` paused it for the cap and
  committed, and the PATCH then saved the whole row with `paused_at` null. The pause was gone
  and no audit row said so.
- Fix: `own_agent(..., lock=True)` reads the row `FOR UPDATE`; the PATCH uses it. Test:
  `AChangeLocksTheAgent`.

### [MEDIUM] F9, provenance: a person could file under an agent's run
- Where: `backend/apps/agents/runs.py` `_own_run`, called by `proposals/batch.py`
  `create_batch` and `proposals/logic.py` `create`.
- Scenario: runs the scheduler and requests open carry no key, and `_own_run` filtered
  `api_key_id=None` for a person, so an editor's `POST /proposal-batches` naming the
  re-tag's run was filed as that run's work, spent its `WATCH_RUN_MAX_PROPOSALS`, and could
  make `file_retag` fail with `run_budget_exhausted`. A bank's `proposals.create` could do
  the same with its own agent's run.
- Breaks: AI output labelled and attributable (CLAUDE.md section 5, AUD-02).
- Fix: `runs.refuse_person_run` answers a person naming any run with the 404 a run of
  another key answers (`tests_create` pins that a person naming a run is 404, never a
  probe-able 422), in both doors. Tests: `test_a_person_naming_an_agents_run_files_nothing`,
  `test_the_single_proposal_door_refuses_it_too`.

### [MEDIUM] F10, sessions: the idle limit and the access token
- Where: `backend/apps/tenants/security_policy.py`, `backend/apps/identity/session_logic.py`
  `limits`.
- Scenario: a bank sets the idle limit to 5 minutes. The web app refreshes only when its
  10-minute access token runs out, so the refresh of a person who worked the whole time finds
  `last_seen_at` 10 minutes old and revokes the session as idle; every working person is
  signed out every 10 minutes, while an idle one keeps a working token for up to 10.
- Breaks: ID-08, the limit applies as the bank means it.
- Fix: `SESSION_IDLE_MINUTES_MIN` (15 by default), which settings refuse to boot unless it
  exceeds `ACCESS_TOKEN_TTL_MINUTES`; the route refuses a lower limit with 422
  `validation_error` naming `sessionIdleMinutes`, and `limits` reads a stored lower value as
  the floor. The one existing test that set 10 minutes now sets the floor. Tests:
  `TheIdleLimitOutlivesTheAccessToken`.

### [HIGH, latent] F11, runner: nothing applies runner events
- Where: `backend/apps/agents/runner_events.py` `apply_event`,
  `backend/apps/shared/adapters/agent_runner.py` `poll`: no task, beat or route calls either.
- Scenario: once a real runner exists, every bank run stays `running` with a null cost, so
  `spend` stays 0, the cap's second point (and F6) never fires, and the cap reduces to one
  run's limit per open. D-98's topic has no consumer yet either, so the "only through the
  logged wrapper" rule for it has no code to hold it.
- Why deferred: no deployed environment can run an agent today. `AGENT_RUNNER=mock` is refused
  on prod and staging (`MOCK_ADAPTER_SETTINGS`, proven by
  `TheBootRefusesTheMockRunnerDeployed`) and `managed_agents` is refused everywhere deployed
  (D-54, ADR 0047). Wiring a poller is the runner leg's work (AGT-06), not a review fix, and
  would change what every E2E journey sees of a run. H80 names it as a gate on lifting
  ADR 0047's refusal.

## What was proven

**The fence at database, route and scheduler.** Database: `agent` CHECKs keep a platform
agent from being tenant-configurable (`agents/models.py` CHECKs on `agent`), `scope` never
changes (`agents/migrations/0004`), and a trigger refuses a `tenant_agent` on anything but a
tenant-scoped, tenant-configurable definition and refuses its deletion (`0005`). Routes: every
tenant control reaches `refuse_platform_agent` (create in `tenant_agents.create_tenant_agent`;
PATCH, pause, resume and run now through `own_agent`; research requests through `own_agent`;
interrupt in `control.interrupt`, which also refuses a platform run by name before locking).
PATCH has no `agent` field. Definition, version and platform-settings routes need the
platform permission `agent_definitions.manage` (publish, retire and settings with a step-up).
Scheduler: `run_platform_agents` is not a `@tenant_task` and takes no tenant; the banks' beat
hands tenant ids only to `run_due_tenant_agents`, which activates that tenant and reads its
agents under RLS (`tasks.py`). The cadence floor and `AGENTS_PER_TENANT_MAX` are checked
server side, the latter under an advisory lock.

**No platform run reads a tenant row.** The platform half reads `agent`, `agent_version`,
`jurisdiction` and platform runs, never `scope.py` or a bank's switch (proven by
`tests_tasks.TheBeatOfBleqqsAgentsStaysOutOfEveryBank` and the console re-tag's
`test_it_reads_no_tenant_row_with_two_banks_present`); the tenant setting is
transaction-local (`shared/tenancy.py`).

**No tenant text in logs, model inputs or platform surfaces.** The topic and the fetched text
are in no `logger` call, audit value or outbox payload (`requests._opened` records kind,
agent, source, run and flags only; `TheTopicStaysInTheBank`); `ResearchRequestOut` never
returns `fetched_text`; the frontend renders topic and address as React text and
`no-dangerous-html.test.ts` gates `dangerouslySetInnerHTML`. The console's run list and
`GET /agents/platform` read platform runs only, with no cost, error or topic
(`platform.py`, `platform_read.py`). A runner's `error` is stored and never logged.

**`check_url`.** https on port 443 only, no user info, no standards publisher; every
resolved address must be public (numeric, octal and hex forms, mapped IPv6, loopback,
link-local, CGNAT and metadata addresses refused; checked in a shell over 37 inputs); the
connection dials the checked address with SNI and certificate verification
(`_CheckedConnection`), so rebinding cannot move it; `http.client` honours no proxy
variable; every redirect is re-checked and counted; no `Accept-Encoding` is sent and nothing
is decompressed; NUL bytes are stripped. With F3 and F4 it now fetches last and within one
deadline.

**Runner events validated.** One door, `runner_events.apply_event`: the run must exist and be
in the applying worker's own zone, is locked, and takes no event once finished; cost is
finite, non-negative, below the column's bound and at most four places; totals never go
down; unknown counters are refused (`tests_runner_events.RefusingAnEvent`). No HTTP route or
API key reaches it.

**The cap's two points.** Before a run: `fits_the_cap` under the `agent_spend` lock, now with
open runs held (F1) and research requests on the same check (F2). Mid-run: an event taking
the month's spend past the cap stops the run and pauses the agent, now under the same lock
(F5), plus the AI switch (F6). The month is the bank's own; money is `Decimal` throughout; no
cap set means no run.

**The BE flag.** Backup eligibility and state come from py_webauthn's verified result, never
the client's JSON, at registration and at every assertion; a change of BE is refused at sign-in
and at step-up and logged with a reason code; a refused passkey is kept; no attestation
object, certificate or assertion is logged (`identity/passkey_logic.py`,
`tests_backup_flag.py`). The AAGUID is in the `passkey.registered` audit row, as the spec
asks, and in no log.

**Session limits.** The bank's limits never pass the platform maximums (schema `strict`,
`ge=1`, the route's check, database CHECKs, and a clamp where they are read); the absolute
end is fixed at sign-in and a refresh only narrows it; a platform session keeps the platform
defaults and reads no bank's row; the write needs `security.manage` and a fresh passkey and is
audited with the assertion id. F10 adds the floor.

**The D-98 path for a bank's capped research text.** Length-capped by the schema
(`AGENT_RESEARCH_TOPIC_MAX_CHARS`), screened (`risk_flags`), stored on the bank's own request
only, never logged or audited; a bank's request can open only its own agent's run, never a
platform run; the request is refused with AI off or at the cap. The model leg (the logged
wrapper, the approved EU endpoint, the switch on every call) has no code yet: F11.

**Batch four eyes and apply.** The decide route is session-only, `proposals.review`,
`@requires_step_up`; the logic refuses an agent reviewer and a caller inside a bank; one
transaction with the batch and its rows locked; a decided batch or row refused; rows only of
this batch; stale rows re-checked under the obligation locks in `apply.py`; one audit row per
decided row and one for the batch, each with the step-up assertion
(`tests_batch_decide.py`). F8 and F9 close the two gaps.

**The fence allowlists and the boot guard.** Compared with `origin/main`:
`LIBRARY_WRITE_ALLOWLIST`, `LIBRARY_WRITE_ALLOWED_DIRS`, `WATCH_WRITE_ALLOWLIST`,
`DOOR_NAMERS`, `compliance_check.py` and the boot guard refusing a role with `BYPASSRLS` are
byte-identical. What the merged packages added is exactly what they declared:

| Where | Added | Declared by |
|---|---|---|
| `tests_library_fence.py` `PLATFORM_CONFIGURATION` | `Agent`, `AgentVersion` | D-102, ADR 0059 (`c11-agent-config-platform`) |
| `tests_library_fence.py` `PLATFORM_CONFIGURATION_ROUTES` | `publishAgentVersion`, `retireAgentVersion`, `updatePlatformAgentSettings` to `seeds/console.py` | D-102 |
| `tests_library_fence.py` `unexpected_writer`, route-gate walk | the three console routes, each to its own writer only | D-102 |
| `tests_library_fence.py` door calls | `decideProposalBatch` to `apply` | PRO-04 (`c11-proposal-batches-decide`) |
| `tests_hardening.py` `REVIEWED_LIBRARY_RECORD_CALLS` | two `batch.py` `record()` calls with no tenant | PRO-04 |

`seeds/console.py` writes only `AgentVersion` and `Agent`, from three routes that need a
person's session, `agent_definitions.manage` and a step-up. This package changes none of
these lists.

## Fixes

In `backend/apps/agents/`: `budget.py` (`held`, `SPEND_LOCK`), `tasks.py` (`fits_the_cap`,
`run_budget_limit` made public for requests), `requests.py` (order of refusals, deadline,
malformed addresses, NAT64), `runner_events.py` (spend lock, AI switch), `tenant_agents.py`
(`own_agent(lock=)`, `refuse_stopped`), `control.py` (uses `refuse_stopped`), `runs.py`
(`refuse_person_run`). In `backend/apps/proposals/`: `batch.py` (`_requested_by`, the person
check), `logic.py` (the person check), `api.py` (the decide's description). In identity and
tenants: `session_logic.py`, `security_policy.py`, `schemas.py`. Settings:
`RESEARCH_URL_TOTAL_SECONDS`, `SESSION_IDLE_MINUTES_MIN`, in `.env.example` and
`RAILWAY_VARIABLES.md`.

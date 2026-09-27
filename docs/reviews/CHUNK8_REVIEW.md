# Security review: chunk 8, the register, the organisation, support access and My work (2026-09-27)

## Question

Do chunk 8's surfaces hold the product invariants the wave 6 brief names (NFR-01, REG-01,
REG-03, REG-08, TEN-06, COL-04, HOM-05)? The surfaces are:

- the register: applicability, compliance status, gaps and risk acceptance, internal links and
  interpretation, Statement of Applicability units and paste, and recurring duties with their
  dated occurrences;
- the inventory's register overlay;
- the organisation: legal entities, licences, products, departments and teams;
- member removal with reassignment;
- support access and the support session;
- My work, Today's standing and the roadmap's internal deadlines;
- participants;
- the bank's vocabulary usage counts;
- the recurring-duty proposal.

The invariants are two zones under forced row-level security, proposals as the only door into
the library, four eyes where the rules demand them and none where D-75 removed them, nothing
overwritten, no typed text in an audit value, outbox payload, log or model input, validation at
every trust boundary, and permission-filtered reads.

## Standard

As in the chunk 1, 6 and 7 reviews: OWASP ASVS 5.0.0 chapters V4 (API), V8
(authorization), V14 (data protection) and V16 (logging), read against CLAUDE.md section 5,
R2_CROSS_CUTTING sections (e), (l) and (m), ADR 0042 and D-49 (support access), D-75
(applicability without four eyes) and D-89 (agents never manage a bank's scope).

## Method

1. **Merged the chunk 8 tree.** The tree is `origin/main` with the ten wave 4 and 5 packages
   this review depends on, merged with `--no-ff`. The merge seams are three commits, each named
   below under Gates run.
2. **Read the production code of every chunk 8 module:**
   - `apps/register/`: `api`, `applicability`, `duties`, `gaps`, `history`, `links`,
     `logic`, `overlay`, `soa`, `status_logic`, `units`, and the migrations 0001 to 0004;
   - `apps/tenants/`: `api`, `support_access`, `organisation`, `products`, `teams`,
     `people`, `reassignment`, `logic`, and the migrations 0002 to 0004;
   - `apps/home/`: `my_work`, `roadmap`, `feed`, `logic`;
   - `apps/collab/`: `participants`, `subjects`, `me_comments`;
   - `apps/taxonomy/tenant_lists_logic.py`;
   - `apps/library/`: `recurrence.py`, and `reading.py`'s overlay join;
   - `apps/proposals/`: the recurring-duty kind in `logic` and `apply`;
   - the support session in `apps/identity/session_logic.py`, `apps/shared/authentication.py`,
     `middleware.py` and `routes.py`.
3. **Enumerated every `CREATE POLICY`** in every migration.
4. **Enumerated every `record(` in the register and tenants apps** and read its before and
   after values.
5. **Timed an RRULE expansion** directly against dateutil.
6. **Proved each fix red before it.** Each new test was run against the unfixed source,
   restored from `HEAD` for the run, and was red there.
7. **Ran the gates** listed under Gates run.

## Verdict per area

| Area | Verdict | Evidence |
|---|---|---|
| Tenancy and composite keys | **Holds.** | Every register, organisation, team, participant and duty-occurrence table is under forced RLS and named in `tests_rls.TENANT_ONLY_TABLES`. Every tenant reference is a composite `(tenant_id, x)` foreign key, `gap.unit_id` and the `soa_unit` columns included. Ids in bodies are resolved under RLS and refused when removed or inactive. A library obligation is resolved under the `owner_tenant_id` policy before any entry is made, so another bank's private obligation is a 404. Evidence: `register/tests_models.py`, `tenants/tests_team_models.py`, `collab/tests_participants.py`, `register/tests_duties.py` (`test_the_database_refuses_another_banks_entry`), `shared/tests_tenant_isolation.py`. |
| Support access: one policy (ADR 0042) | **Holds.** | Of every policy in every migration, only `support_access_own_grants` (tenants 0004) names `app.platform_user_id`. It is SELECT only, on `support_access`. No other policy widens a tenant table. |
| Support access: allow-list | **Holds.** | `SUPPORT_READ_ROUTES` holds GETs only. The middleware matches the resolved route template before the view, and everything else answers 403 `support_read_only`. The principal holds seven reads. |
| Support access: grant life and tenancy | **Holds.** | The grant is re-read on every request (401 `support_access_ended`). The session's bank comes from the grant. The requester cannot approve, which is enforced in code and by the CHECK. Approval needs `security.manage` and a step-up. The window is capped by `SUPPORT_ACCESS_MAX_HOURS`. Evidence: `shared/tests_support_session.py`, `shared/tests_support_routes.py`, `tenants/tests_support_access.py`. |
| Support access: each read logged | **Did not hold; fixed** (M5). | Below. |
| Four eyes on risk acceptance | **Held at the approval, not after it; fixed** (M2). | The approval needs `risk.accept.approve` and a step-up, and names its assertion. The requester is refused in code, by `gap_four_eyes` and by the `gap_accepted_guard` trigger. The race is covered by `tests_gaps.RiskAcceptanceRace`. The facts accepted could still change: below. |
| Four eyes on support grants | **Holds.** | As above. |
| No four eyes on applicability (D-75) | **Holds.** | `setApplicability` and `setApplicabilityMany` need `applicability.approve` and a confirmation, with no second person. The paste's answers need the same permission. Evidence: `register/tests_applicability.py`, `tests_units.py`. |
| The recurring-duty fence | **Holds.** | `RecurringDuty.objects.create` in `proposals/apply.py` under `library_write(door="proposal")` is the only production writer. The table has no tenant column and no policy, and carries the door trigger. Evidence: `tests_rls.RecurringDutyIsLibraryOnly`, `tests_library_db_guard.py`, `tests_library_fence.py`. The target must be a shared active obligation. The approver is a second principal: a person with a step-up, or an agent of another definition and key, under the `recurring_duty_confirmer_independent` check. |
| Recurring-duty rules | **Did not hold; fixed** (M4). | The rule grammar, caps and ten-year occurrence limit are enforced at proposal and at apply (`library/tests_recurrence.py`). The register expanded rules unbounded: below. |
| Soft removal of links and units | **Holds in code.** | `SoaUnit.delete` and `InternalLink.delete` raise, and no register code deletes a row. Removed rows are excluded from reads and refuse edits. A unit with history cannot be removed or renamed. The database would still allow a delete: I1, H57. |
| Typed text in audit, outbox, logs and models | **Did not hold for one value; fixed** (M1). One policy question remains (L1). | Gap, status, interpretation, link, applicability, participant, reassignment and support-read rows carry ids, keys, dates, and the names of typed fields. The applicability reason is the one sanctioned value (AC-REG1). No register or tenants log line carries content. No chunk 8 text reaches a model. |
| Paste, bulk and key validation | **Holds.** | `REGISTER_BULK_MAX` has an env override. Duplicate targets and duplicate references are refused. Every text field is capped, NUL is refused and unknown fields are refused. Writes are all-or-nothing. Vocabulary keys are slugged, capped, immutable and deduplicated case-insensitively, and a bank's lists are capped by `TENANT_LIST_MAX_ROWS`. Control characters in names are L7. |
| My work permission filtering | **Holds.** | No user id is accepted. A department of another bank answers 404. Every row is gated by the reader's own `register.read` and `cases.read`. No gap title, note or comment text is in the page. Evidence: `home/tests_my_work.py`, `tests_my_work_api.py`. |
| SoA permission filtering | **Holds.** | Needs `register.read` and a conformance scope. The history comes from the bank's own audit rows under RLS (`register/tests_soa.py`). |
| The inventory overlay | **Did not hold; fixed** (M3). | Below. |
| The calendar feed | **Holds.** | Only the regulatory branch reaches the ICS, with library properties only (`home/tests_feed.py`). |
| D-89: agents and a bank's scope | **Holds.** | `TENANT_KEY_SCOPES` holds reads and `proposals:write`. Every register and tenants route takes a person's session only. Footprint approval needs `footprint.approve` and a step-up. |

## Findings

Severity: critical / high / medium / low / info. Status: fixed / open (with where it gets
fixed) / accepted. Every fix has a test that was red before it.

### Fixed (medium)

- **M1. A duty completion note was copied into the audit trail.**
  - Where: `apps/register/duties.py` `complete_occurrence`.
  - Finding: the audit row of a completed duty occurrence, and its outbox event, carried the
    note the person typed (`after.note`). R2_CROSS_CUTTING (m) forbids it, and the compliance
    lint flagged it.
  - Fix: the row now says `noted: true|false`; the note stays on the occurrence.
  - Test: `register/tests_duties.py`,
    `test_the_note_stays_on_the_occurrence_and_out_of_the_audit_trail_and_the_outbox`.
- **M2. A risk acceptance could be changed after, or under, the approval.**
  - Where: `apps/register/gaps.py` `update_gap`.
  - Finding: four eyes held at the approval but not after it. `PATCH /gaps/{gapId}` changed
    the severity, title, description, plan and target date of a risk-accepted gap, and of a
    gap whose acceptance was waiting. A requester could have a low gap accepted, then raise it
    to critical, or rewrite it between the approver's reading and their step-up.
  - Fix: those facts answer 409 `invalid_transition` on an accepted gap (reopen it first), and
    409 `request_pending` while an acceptance waits. The owner may still change (TEN-03), and
    closing still drops a waiting request. `updateGap` documents both refusals.
  - Tests: `register/tests_gaps.py`, `test_an_accepted_risk_keeps_the_facts_the_approver_accepted`
    and `test_a_waiting_acceptance_is_approved_on_the_facts_it_was_asked_for`.
- **M3. The inventory showed the bank's register to people who may not read it.**
  - Where: `apps/library/api.py` `listObligations` and `getObligation`; `apps/register/overlay.py`.
  - Finding: every inventory row and the card carried the bank's applicability answers,
    compliance status and first-line owner to any holder of `library.read`. That includes the
    seeded `library_only` role, which exists to be the no-register-read case, and a bank's agent
    key with `library:read`. The overlay filters let them search by it.
  - Fix: the overlay is filled only for a person holding `register.read`. Anyone else reads
    every row as unanswered. An overlay filter from a caller in a bank without `register.read`
    answers 403 `permission_denied`.
  - Placement: the rule is in `register/overlay.py` (`withheld`,
    `refuse_filters_without_register`), because `library/reading.py` is owned by a wave 6
    build package and is unchanged.
  - Tests: `register/tests_overlay.py`,
    `test_a_reader_without_register_read_sees_the_library_and_none_of_the_banks_judgement` and
    `test_a_reader_without_register_read_cannot_probe_the_register_through_the_filters`.
- **M4. Recurring-duty rules were expanded without a bound.**
  - Where: `apps/register/duties.py` `next_due`.
  - Finding: the register called dateutil directly, skipping the bounded walk. A rule is
    validated from the day it was proposed, but a bank's series starts on the bank's own day.
    A rule that passes validation, such as every 35th day on a Tuesday, matches nothing from
    any other start, and dateutil walks to the year 9999: about 0.2 s per target, under the
    applicability write's row locks.
  - Repeats: the cost is paid again on every later answer, because nothing is written.
  - Fix: `next_due` expands through `library/recurrence.expand` over the ten-year horizon.
  - Test: `register/tests_duties.py`,
    `test_a_rule_with_no_date_from_this_start_gives_none_without_walking_to_the_year_9999`.
    The rule's own correctness is L8.
- **M5. A refused support-session read left no log row.**
  - Where: `apps/shared/authentication.py`, `middleware.py`, `apps/tenants/support_access.py`.
  - Finding: ADR 0042 logs every request of a support session. The row was written in the
    request's transaction, so a refusal that rolled it back took the row with it. Examples are
    a 404, or a 422 that names which of the bank's own tags do not exist. Support could probe
    the bank without a trace in its log.
  - Fix: the read-only middleware checks after the response that the row survived. If a
    refusal rolled it back, the row is written again in its own transaction under the bank.
    Each request still has exactly one row.
  - Test: `shared/tests_support_session.py`, `test_a_read_the_route_refuses_is_still_logged`.
- **M6. A refused last-admin recovery left a false record.**
  - Where: `apps/tenants/logic.py` `console_reissue_enrolment`. This is chunk 1 code, found in
    this review.
  - Finding: the recovery wrote its write-level `support_access` row and its
    `support_access.recorded` audit row before it looked for the member, and the route does
    not roll back a 404. A wrong or deactivated user id left a recovery in the bank's audit
    trail and SIEM stream that never happened.
  - Fix: the member is found first.
  - Test: `tenants/tests_recovery.py`.

### Open (low and info)

| # | Sev. | Finding | Status |
|---|---|---|---|
| L1 | low | A Statement of Applicability unit's reference and title, in the bank's words, are in its audit values. They are the unit's name, but (m) names no exception. | Open: H50, and Alex decides (`TODO_FOR_alex.md`). |
| L2 | low | Obligation comments are read under `library.read`, so a custom role without `register.read` reads the bank's register discussion. System roles hold both, and D-22 and D-60 say everyone in the bank reads comments. | Open: H51. |
| L3 | low | The roadmap gives a regulatory row's case status and urgency to `roadmap.read` without `cases.read`. | Open: H52. |
| L4 | low | Leaving one's own obligation participation needs `register.read`, but leaving a case participation needs nothing. | Open: H53. |
| L5 | low | `If-Match` is optional on `setApplicability` and `saveInterpretation`. | Open: H54. |
| L6 | low | A gap and a new internal item accept a deactivated legal entity. Status and gap writes are not checked against the entities the obligation spans. | Open: H55. |
| L7 | low | Control and bidi characters are accepted in unit, gap, link and recurring-duty titles and in a bank's vocabulary labels. A reason of only spaces is stored. | Open: H56. |
| L8 | low | A start-dependent rule schedules nothing from some starts. `COUNT` never ends a series. There is no retire kind and no uniqueness check. | Open: H58. |
| L9 | low | Two administrators removing each other at once can leave the bank with no administrator (write skew). | Open: H59. |
| L10 | low | A support session outlives the loss of the platform permission. A lowered maximum window does not shorten a waiting request. Support requests are not rate-limited. | Open: H61. |
| I1 | info | `cw_app` holds DELETE on `soa_unit`, `internal_link` and `gap`, and only code refuses it. | Open: H57. |
| I2 | info | `team_member`, `licence_service_term` and `tenant_product_term` rows are deleted when a link ends; the audit keeps them. | Open: H62, and Alex confirms. |
| I3 | info | `approveProposal`'s description omits `new_recurring_duty` from the kinds an agent may confirm. | Open: H63. |
| I4 | info | `subject_title` carries a gap's, link's or item's own title, as CHUNK10_TASKS rule 13 allows. | Accepted, noted. |
| I5 | info | The library door trigger's `seed` door can be opened by `cw_app` itself. It is a backstop against mistakes, not against a compromised app. | Accepted, noted: the same for every library table (ADR 0058). |

## Gates run

- **Merge seams.**
  - `The merged chunk 8 packages build, type-check and migrate together`: the case response
    names its owner team; duplicate factories, guard entries and settings are dropped.
  - `The merged departures and owner questions keep every package's own text`.
  - `The merged packages pass each other's guards again`: GET /me's support count moves into
    `support_access`; a participant route is no longer declared both gated and ungated.
- **Backend.**
  - The whole backend suite on the merged tree before the fixes: 3,327 tests, 4 failures, all
    merge seams, fixed as above.
  - Then 3,334 tests with the fixes and one transient failure: a boot subprocess started while
    a file was being edited.
  - Then every suite the fixes touch, on the final tree, green: `apps.register`,
    `apps.library`, `apps.tenants`, `apps.shared` (with `tests_rls`,
    `tests_tenant_isolation`, `tests_library_fence`, `tests_library_db_guard`,
    `tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`), `apps.identity`,
    `apps.home`, `apps.collab` and `apps.agents.tests_runner_events`. That is 1,759 tests, 25
    skipped as pending scenarios.
  - `apps.tenants.tests_recovery` with `apps.identity.tests_scenarios`.
- **Static.** ruff; mypy; `makemigrations --check`; `migrate_from_zero`;
  `compliance_check.py --all` (0 findings); `requirements_coverage.py`; `api_docs_gate.py`;
  `contract_drift.py` (0 unexplained).
- **Final backend run.** The whole suite on the final tree: 3,335 tests, 0 failures, 68
  skipped as pending scenarios.
- **Frontend.** lint, typecheck (on a regenerated, uncommitted contract), the whole vitest
  suite (1,664 tests), `check:messages` and `check:copy-drift` are green. Two merge seams
  were fixed first: the roadmap's `duty_due` phrase, and the navigation test's order with My
  work.
- **E2E.**
  - The whole suite ran (140 passed). Every journey this review's fixes touch passed:
    register, library and inventory, tenants' TEN-S6 and home.
  - Two failures were merge seams, fixed: NFR-S7 had no screen budget for My work, and the
    phone's More-sheet baseline predated Gaps (re-drawn for Linux).
  - The demo and public-page journeys and ID-S25 failed on the stale demo recordings: the
    recorded `GET /home` predates `standing`. With a local re-recording, not committed
    (R2_CROSS_CUTTING (f)), the public, demo, identity and shared specs pass (35 passed).
  - ID-S11 failed only in the parallel full run. Three merged journeys (collab, home,
    register) now sign in as the seeded owner, which ID-S11 assumes it has to itself. It
    passes on its own and is the integrator's (a roster login reserved for it).
- **`prepush.sh --quick`.** Green up to "OpenAPI/TS: artefacts match the contract", which is
  the integrator's, since the two generated files are never committed here. The frontend
  gates after it were run by hand and are green. gitleaks is green.

# Implementation backlog

One task group per PRD requirement, `T-<REQ>-<n>`. The Gherkin scenarios
themselves live in each app's `app.md` (playbook Appendix B); this file points
at them by ID so there is one place a scenario is written. The coverage index
at the end is what `scripts/requirements_coverage.py` checks: every
requirement has at least one scenario, every `@integration` scenario has a
test in `tests_scenarios.py`, every `@e2e` scenario a journey spec.

Task shapes:

- `T-<REQ>-1` **Backend**: models and migrations, `schemas.py`, `logic.py` with
  `record()` on every write, `api.py` with auth, permission and step-up
  decorators, the `@integration` scenarios un-skipped, query counts pinned,
  types regenerated. Steps 1 to 7 of the playbook Section 3 loop.
- `T-<REQ>-2` **Screen and journey**: feature layer (`api.ts`, `hooks.ts`,
  `*-presentation.ts` with unit tests), the screen with empty, loading, error
  and denied states, the navigation registry entry, the message catalog keys,
  the `@e2e` scenarios un-fixme'd. Steps 8 to 11. Only present where the
  requirement has an `@e2e` scenario.
- `T-<REQ>-3` **Guard or gate**, only where the requirement is enforced by a
  structural guard, a lint rule or a CI gate rather than a feature.

Chunk numbers are from `Build_Plan.md`. Status lives in the app's `app.md`
requirement table and in `IMPLEMENTATION_STATUS.md`, not here.

This file is generated from the app.md files by the Phase 0 docs pass;
regenerate it (or edit both) when a scenario is added.

## Chunk 0

### AUD-01 (M, R1, `governance`)

Append-only audit log written with every change: actor (user, agent, system), action, subject with its title at the time, summary, before and after.
Note: record() and the append-only trigger in Phase 0, exercised by every mutating route.

- **T-AUD-01-1** Backend. Scenarios: AUD-S1, AUD-S2, AUD-S7. Spec: `backend/apps/governance/app.md`.
- **T-AUD-01-2** Screen and journey. Scenarios: AUD-S3. Journey spec: `frontend/tests/e2e/governance.journey.spec.ts`.
- **T-AUD-01-3** Guard or gate. The audit-on-write guard and the append-only trigger test.

### NFR-01 (M, R1, `shared`)

Tenant isolation by row-level security, proven per route.
Note: mechanics in Phase 0, proven per route in every chunk that adds a tenant route.

- **T-NFR-01-1** Backend. Scenarios: CAS-S16, NFR-S1, NFR-S2, NFR-S3, NFR-S4, NFR-S5, NFR-S13, NFR-S16. Spec: `backend/apps/shared/app.md`.
- **T-NFR-01-3** Guard or gate. The RLS, database role, tenant isolation and route permission guards (playbook 5) and the production guard.

### NFR-03 (M, R1, `shared`)

The design is reproduced: flow, labels, six-tone pill system, light and dark, WCAG AA.
Note: Pill, gallery and contrast test in Phase 0, every screen from chunk 1 on.

- **T-NFR-03-1** Backend. Scenarios: NFR-S10. Spec: `backend/apps/shared/app.md`.
- **T-NFR-03-2** Screen and journey. Scenarios: NFR-S8, NFR-S9, WAT-S9. Journey spec: `frontend/tests/e2e/shared.journey.spec.ts`, `frontend/tests/e2e/watch.journey.spec.ts`.
- **T-NFR-03-3** Guard or gate. The pill gallery screenshot spec in both themes and the WCAG AA contrast unit test; ESLint rules for raw pills, JSX literals and font sizes.

## Chunk 1

### ID-01 (M, R1, `identity`)

Invitation only, roles set at invite.

- **T-ID-01-1** Backend. Scenarios: ID-S1. Spec: `backend/apps/identity/app.md`.
- **T-ID-01-2** Screen and journey. Scenarios: ID-S25. Journey spec: `frontend/tests/e2e/identity.journey.spec.ts`.

### ID-02 (M, R1, `identity`)

First sign-in by one-time emailed code straight into passkey enrolment; the enrolment session can do nothing else.

- **T-ID-02-1** Backend. Scenarios: ID-S2, ID-S3, ID-S4, ID-S5. Spec: `backend/apps/identity/app.md`.
- **T-ID-02-2** Screen and journey. Scenarios: ID-S4, ID-S5, ID-S25. Journey spec: `frontend/tests/e2e/identity.journey.spec.ts`.

### ID-03 (M, R1, `identity`)

After the first passkey, passkey only; the code stops working for that account; no password anywhere.

- **T-ID-03-1** Backend. Scenarios: ID-S5, ID-S6, ID-S7, ID-S8, ID-S9. Spec: `backend/apps/identity/app.md`.
- **T-ID-03-2** Screen and journey. Scenarios: ID-S5, ID-S6, ID-S8, ID-S25. Journey spec: `frontend/tests/e2e/identity.journey.spec.ts`.
- **T-ID-03-3** Guard or gate. The guard that no usable password hash and no password field exists.

### ID-04 (M, R1, `identity`)

Users manage passkeys (add, rename, remove, never the last) and see and revoke sessions.

- **T-ID-04-1** Backend. Scenarios: ID-S10, ID-S11. Spec: `backend/apps/identity/app.md`.
- **T-ID-04-2** Screen and journey. Scenarios: ID-S10, ID-S11. Journey spec: `frontend/tests/e2e/identity.journey.spec.ts`.

### ID-05 (M, R1, `identity`)

Recovery: tenant admin re-issues enrolment behind step-up, audited, with notices; the last admin goes through platform support with an out-of-band check.

- **T-ID-05-1** Backend. Scenarios: ID-S12, ID-S13. Spec: `backend/apps/identity/app.md`.
- **T-ID-05-2** Screen and journey. Scenarios: ID-S12. Journey spec: `frontend/tests/e2e/identity.journey.spec.ts`.

### ID-06 (M, R1, `identity`)

Step-up by fresh passkey assertion on the sensitive actions of playbook 4.2, recorded on the audit event.

- **T-ID-06-1** Backend. Scenarios: ID-S14, ID-S15. Spec: `backend/apps/identity/app.md`.
- **T-ID-06-2** Screen and journey. Scenarios: ID-S14. Journey spec: `frontend/tests/e2e/identity.journey.spec.ts`.

### ID-09 (M, R1, `identity`)

Permissions are code, roles are rows: seeded system roles plus tenant-defined roles; a tenant always keeps one admin.

- **T-ID-09-1** Backend. Scenarios: ID-S18, ID-S19, ID-S26. Spec: `backend/apps/identity/app.md`.
- **T-ID-09-2** Screen and journey. Scenarios: ID-S18, ID-S26. Journey spec: `frontend/tests/e2e/identity.journey.spec.ts`.
- **T-ID-09-3** Guard or gate. The route permissions guard (`UNGATED_BY_DESIGN` reasons) and the seed integrity guard.

### ID-10 (M, R1, `identity`)

Scoped API keys for agents and integrations, shown once, stored hashed, revocable, with last use.
Note: chunk 1 builds the key model; chunk 5 gives the agents their scopes.

- **T-ID-10-1** Backend. Scenarios: ID-S20, ID-S21. Spec: `backend/apps/identity/app.md`.
- **T-ID-10-2** Screen and journey. Scenarios: ID-S20. Journey spec: `frontend/tests/e2e/identity.journey.spec.ts`.

### ID-11 (M, R1, `identity`)

Security log of sign-ins, failures, enrolments, recoveries and key use.

- **T-ID-11-1** Backend. Scenarios: ID-S22. Spec: `backend/apps/identity/app.md`.

### TEN-01 (M, R1, `tenants`)

Tenant profile, timezone, default languages, onboarding checklist.

- **T-TEN-01-1** Backend. Scenarios: TEN-S1. Spec: `backend/apps/tenants/app.md`.
- **T-TEN-01-2** Screen and journey. Scenarios: TEN-S1. Journey spec: `frontend/tests/e2e/tenants.journey.spec.ts`.

### ADM-01 (M, R1 to R3, `tenants`)

Tenant admin: organisation, members and invitations, passkey re-enrolment, sessions, roles, footprint, vocabularies, workflow policy, agents, integrations, security policy, data, audit log.

- **T-ADM-01-1** Backend. Scenarios: ADM-S1. Spec: `backend/apps/tenants/app.md`.
- **T-ADM-01-2** Screen and journey. Scenarios: ADM-S1, ADM-S2. Journey spec: `frontend/tests/e2e/tenants.journey.spec.ts`.

### ADM-03 (M, R1, `tenants`)

Admin duties are separate permissions.

- **T-ADM-03-1** Backend. Scenarios: ADM-S1, ADM-S3. Spec: `backend/apps/tenants/app.md`.
- **T-ADM-03-2** Screen and journey. Scenarios: ADM-S1, ADM-S3. Journey spec: `frontend/tests/e2e/tenants.journey.spec.ts`.

## Chunk 2

### VOC-01 (M, R1, `taxonomy`)

Every extendable list is rows in three tiers; only kinds are code.

- **T-VOC-01-1** Backend. Scenarios: VOC-S1, VOC-S2, VOC-S14. Spec: `backend/apps/taxonomy/app.md`.
- **T-VOC-01-2** Screen and journey. Scenarios: VOC-S2, VOC-S15. Journey spec: `frontend/tests/e2e/taxonomy.journey.spec.ts`.
- **T-VOC-01-3** Guard or gate. The kinds-only guard and the vocabulary integrity guard.

### VOC-02 (M, R1, `taxonomy`)

One vocabulary screen per surface: real pill in light and dark, usage count, inline rename, drag to reorder, retire, merge.

- **T-VOC-02-1** Backend. Scenarios: VOC-S3, VOC-S4, VOC-S5. Spec: `backend/apps/taxonomy/app.md`.
- **T-VOC-02-2** Screen and journey. Scenarios: VOC-S3, VOC-S4, VOC-S5, VOC-S15. Journey spec: `frontend/tests/e2e/taxonomy.journey.spec.ts`.

### VOC-07 (M, R1, `taxonomy`)

Library vocabulary changes go through the proposal queue.

- **T-VOC-07-1** Backend. Scenarios: VOC-S11. Spec: `backend/apps/taxonomy/app.md`.
- **T-VOC-07-2** Screen and journey. Scenarios: VOC-S11, VOC-S15. Journey spec: `frontend/tests/e2e/taxonomy.journey.spec.ts`.

### FP-01 (M, R1, `taxonomy`)

Footprint across all dimensions; a record matches when every dimension it carries has a term in the footprint; an empty dimension does not restrict.

- **T-FP-01-1** Backend. Scenarios: FP-S1. Spec: `backend/apps/taxonomy/app.md`.
- **T-FP-01-2** Screen and journey. Scenarios: FP-S5. Journey spec: `frontend/tests/e2e/taxonomy.journey.spec.ts`.

### FP-02 (M, R1, `taxonomy`)

A footprint change previews what it hides and reveals, needs a second person and step-up, one audit event per term.

- **T-FP-02-1** Backend. Scenarios: FP-S2, FP-S3. Spec: `backend/apps/taxonomy/app.md`.
- **T-FP-02-2** Screen and journey. Scenarios: FP-S2, FP-S5. Journey spec: `frontend/tests/e2e/taxonomy.journey.spec.ts`.

### FP-03 (M, R1, `taxonomy`)

Feed, inventory, roadmap, briefing and reports respect the footprint, with a visible way to look outside it.

- **T-FP-03-1** Backend. Scenarios: FP-S4. Spec: `backend/apps/taxonomy/app.md`.
- **T-FP-03-2** Screen and journey. Scenarios: FP-S4, FP-S5. Journey spec: `frontend/tests/e2e/taxonomy.journey.spec.ts`.

### I18N-01 (M, R1, `taxonomy`)

Content in `en`, `sv`, `da`, `nb`, `fi` as translation rows; jurisdictions EU, SE, DK, NO, FI as data.

- **T-I18N-01-1** Backend. Scenarios: I18N-S1, I18N-S2. Spec: `backend/apps/taxonomy/app.md`.

## Chunk 3

### INV-01 (M, R1, `library`)

Instruments with level, binding force, official reference, ELI where available, jurisdiction, authority, in-force dates and lineage.

- **T-INV-01-1** Backend. Scenarios: INV-S1, INV-S10. Spec: `backend/apps/library/app.md`.
- **T-INV-01-2** Screen and journey. Scenarios: INV-S1. Journey spec: `frontend/tests/e2e/library.journey.spec.ts`.

### INV-02 (S, R1, `library`)

Provision tree with verbatim text versions, in-force dates and transitional notes.

- **T-INV-02-1** Backend. Scenarios: INV-S2, INV-S10. Spec: `backend/apps/library/app.md`.
- **T-INV-02-2** Screen and journey. Scenarios: INV-S2. Journey spec: `frontend/tests/e2e/library.journey.spec.ts`.

### INV-03 (M, R1, `library`)

Obligations: plain-language duty, duty type, scope facets, trigger, retention, sanction exposure, provenance, related obligations.

- **T-INV-03-1** Backend. Scenarios: INV-S3. Spec: `backend/apps/library/app.md`.
- **T-INV-03-2** Screen and journey. Scenarios: INV-S3. Journey spec: `frontend/tests/e2e/library.journey.spec.ts`.

### INV-04 (M, R1, `library`)

Versioned summaries with effective dates, "as of" reads and a sentence-level diff.

- **T-INV-04-1** Backend. Scenarios: INV-S4, INV-S5. Spec: `backend/apps/library/app.md`.
- **T-INV-04-2** Screen and journey. Scenarios: AGT-S10, INV-S4, INV-S5. Journey spec: `frontend/tests/e2e/agents.journey.spec.ts`, `frontend/tests/e2e/library.journey.spec.ts`.

### INV-05 (M, R1, `library`)

Text in the original language plus translations, machine translations labelled.

- **T-INV-05-1** Backend. Scenarios: INV-S6. Spec: `backend/apps/library/app.md`.
- **T-INV-05-2** Screen and journey. Scenarios: INV-S6. Journey spec: `frontend/tests/e2e/library.journey.spec.ts`.

### INV-06 (M, R1, `library`)

Source link and last-verified date on every record, and a "this looks wrong" report.

- **T-INV-06-1** Backend. Scenarios: INV-S7, INV-S8. Spec: `backend/apps/library/app.md`.
- **T-INV-06-2** Screen and journey. Scenarios: INV-S7. Journey spec: `frontend/tests/e2e/library.journey.spec.ts`.

## Chunk 4

### PRO-01 (M, R1, `proposals`)

The review queue is the only way into the library, for agents and people, with a source per changed field.

- **T-PRO-01-1** Backend. Scenarios: PRO-S1, PRO-S2, PRO-S6, PRO-S9. Spec: `backend/apps/proposals/app.md`.
- **T-PRO-01-2** Screen and journey. Scenarios: PRO-S9. Journey spec: `frontend/tests/e2e/proposals.journey.spec.ts`.
- **T-PRO-01-3** Guard or gate. The library fence guard (AST) and the API-key scope check.

### PRO-02 (M, R1, `proposals`)

Approval applies the payload, writes the version, the audit row and the re-index in one transaction; the reviewer can correct scope and wording first; never the proposer.

- **T-PRO-02-1** Backend. Scenarios: PRO-S3, PRO-S4, PRO-S5. Spec: `backend/apps/proposals/app.md`.
- **T-PRO-02-2** Screen and journey. Scenarios: AGT-S10, PRO-S3, PRO-S4, PRO-S5. Journey spec: `frontend/tests/e2e/agents.journey.spec.ts`, `frontend/tests/e2e/proposals.journey.spec.ts`.

### PRO-03 (M, R1, `proposals`)

The queue lives in the platform console; tenants see library updates and can report problems.

- **T-PRO-03-1** Backend. Scenarios: PRO-S7. Spec: `backend/apps/proposals/app.md`.
- **T-PRO-03-2** Screen and journey. Scenarios: PRO-S7. Journey spec: `frontend/tests/e2e/proposals.journey.spec.ts`.

### AUD-03 (S, R1, `governance`)

Problem reports resolved by a proposal, closing the loop to the agents.

- **T-AUD-03-1** Backend. Scenarios: AUD-S5. Spec: `backend/apps/governance/app.md`.
- **T-AUD-03-2** Screen and journey. Scenarios: AUD-S5. Journey spec: `frontend/tests/e2e/governance.journey.spec.ts`.

### ADM-02 (M, R1 to R3, `governance`)

Platform console: library vocabularies, sources, languages and jurisdictions, agent definitions, proposal queue, problem reports, evaluation sets, tenants and plans, support access, system health.

- **T-ADM-02-1** Backend. Scenarios: ADM-S4, ADM-S5, ADM-S6. Spec: `backend/apps/governance/app.md`.
- **T-ADM-02-2** Screen and journey. Scenarios: ADM-S4, ADM-S5, ADM-S6. Journey spec: `frontend/tests/e2e/governance.journey.spec.ts`.

## Chunk 5

### WAT-01 (M, R1, `watch`)

Source registry and coverage log: what was checked, when, with what result.

- **T-WAT-01-1** Backend. Scenarios: WAT-S1. Spec: `backend/apps/watch/app.md`.
- **T-WAT-01-2** Screen and journey. Scenarios: WAT-S1. Journey spec: `frontend/tests/e2e/watch.journey.spec.ts`.

### WAT-02 (M, R1, `watch`)

One record per reform with a timeline from consultation to in force, partial dates, duplicates merged.

- **T-WAT-02-1** Backend. Scenarios: WAT-S2, WAT-S3. Spec: `backend/apps/watch/app.md`.
- **T-WAT-02-2** Screen and journey. Scenarios: AGT-S10, WAT-S2. Journey spec: `frontend/tests/e2e/agents.journey.spec.ts`, `frontend/tests/e2e/watch.journey.spec.ts`.

### WAT-03 (M, R1, `watch`)

Change types, flags and scope from vocabularies; agent classifications shown as suggestions until confirmed.

- **T-WAT-03-1** Backend. Scenarios: WAT-S4, WAT-S5. Spec: `backend/apps/watch/app.md`.
- **T-WAT-03-2** Screen and journey. Scenarios: WAT-S4, WAT-S9. Journey spec: `frontend/tests/e2e/watch.journey.spec.ts`.

### WAT-04 (M, R1, `watch`)

Links to affected obligations with confidence, confirmed by a person.

- **T-WAT-04-1** Backend. Scenarios: WAT-S6. Spec: `backend/apps/watch/app.md`.
- **T-WAT-04-2** Screen and journey. Scenarios: WAT-S6. Journey spec: `frontend/tests/e2e/watch.journey.spec.ts`.

### WAT-05 (M, R1, `watch`)

A drafted "So what?" per change, labelled AI-drafted until a person confirms or rewrites it per tenant.

- **T-WAT-05-1** Backend. Scenarios: WAT-S7. Spec: `backend/apps/watch/app.md`.
- **T-WAT-05-2** Screen and journey. Scenarios: CAS-S14, WAT-S7. Journey spec: `frontend/tests/e2e/cases.journey.spec.ts`, `frontend/tests/e2e/watch.journey.spec.ts`.

### CAS-01 (M, R1, `cases`)

One case per tenant per change, created in "needs triage" with its footprint match.

- **T-CAS-01-1** Backend. Scenarios: CAS-S1. Spec: `backend/apps/cases/app.md`.
- **T-CAS-01-2** Screen and journey. Scenarios: CAS-S14. Journey spec: `frontend/tests/e2e/cases.journey.spec.ts`.

### AGT-01 (M, R1, `agents`)

Agent API: open a run, log source checks, find similar, register changes idempotently, submit proposals, close the run.

- **T-AGT-01-1** Backend. Scenarios: AGT-S1, AGT-S2. Spec: `backend/apps/agents/app.md`.
- **T-AGT-01-2** Screen and journey. Scenarios: AGT-S10. Journey spec: `frontend/tests/e2e/agents.journey.spec.ts`.

### AGT-02 (M, R1, `agents`)

Agents read vocabularies at run start and may use existing keys only.

- **T-AGT-02-1** Backend. Scenarios: AGT-S3. Spec: `backend/apps/agents/app.md`.

### AGT-07 (M, R1, `agents`)

Fetched content screened for embedded instructions.

- **T-AGT-07-1** Backend. Scenarios: AGT-S9. Spec: `backend/apps/agents/app.md`.
- **T-AGT-07-3** Guard or gate. The content screen unit tests and the rule that fetched text is never rendered as HTML.

## Chunk 6

### HOM-01 (M, R1, `home`)

Timeline home: next dates as a short list on every screen size, the lead item, what needs a decision, compliance standing, source health.

- **T-HOM-01-1** Backend. Scenarios: HOM-S1. Spec: `backend/apps/home/app.md`.
- **T-HOM-01-2** Screen and journey. Scenarios: CAS-S14, HOM-S1, HOM-S2. Journey spec: `frontend/tests/e2e/cases.journey.spec.ts`, `frontend/tests/e2e/home.journey.spec.ts`.

### HOM-02 (M, R1, `home`)

Weekly briefing, reachable from home with part of it shown there, snapshotted when emailed.

- **T-HOM-02-1** Backend. Scenarios: HOM-S3. Spec: `backend/apps/home/app.md`.
- **T-HOM-02-2** Screen and journey. Scenarios: HOM-S3. Journey spec: `frontend/tests/e2e/home.journey.spec.ts`.

### HOM-03 (M, R1, `home`)

Roadmap page by quarter, regulatory dates and our own deadlines, a card expanding in place.

- **T-HOM-03-1** Backend. Scenarios: HOM-S4. Spec: `backend/apps/home/app.md`.
- **T-HOM-03-2** Screen and journey. Scenarios: HOM-S4, HOM-S6. Journey spec: `frontend/tests/e2e/home.journey.spec.ts`.

### HOM-04 (S, R1, `home`)

Upcoming changes as public facts for agents and newsletters, and a revocable calendar feed.

- **T-HOM-04-1** Backend. Scenarios: HOM-S5. Spec: `backend/apps/home/app.md`.
- **T-HOM-04-2** Screen and journey. Scenarios: HOM-S5. Journey spec: `frontend/tests/e2e/home.journey.spec.ts`.

## Chunk 7

### SRC-01 (M, R1, `search`)

Hybrid search: exact identifiers by keyword, concepts by vector, fused by rank, reranked, per language.

- **T-SRC-01-1** Backend. Scenarios: SRC-S1, SRC-S2, SRC-S9, SRC-S11. Spec: `backend/apps/search/app.md`.
- **T-SRC-01-2** Screen and journey. Scenarios: SRC-S1, SRC-S10. Journey spec: `frontend/tests/e2e/search.journey.spec.ts`.

### SRC-02 (M, R1, `search`)

Filters from vocabularies, an "as of" date, and the match kind on every hit.

- **T-SRC-02-1** Backend. Scenarios: SRC-S3. Spec: `backend/apps/search/app.md`.
- **T-SRC-02-2** Screen and journey. Scenarios: SRC-S3, SRC-S10. Journey spec: `frontend/tests/e2e/search.journey.spec.ts`.

### SRC-03 (M, R1, `search`)

Cited answers grounded only in the inventory, pending changes flagged, "no answer" instead of a guess.

- **T-SRC-03-1** Backend. Scenarios: SRC-S4, SRC-S5, SRC-S6. Spec: `backend/apps/search/app.md`.
- **T-SRC-03-2** Screen and journey. Scenarios: SRC-S4, SRC-S5, SRC-S10. Journey spec: `frontend/tests/e2e/search.journey.spec.ts`.

### SRC-05 (M, R1, `search`)

An evaluation set that gates releases.

- **T-SRC-05-1** Backend. Scenarios: SRC-S8. Spec: `backend/apps/search/app.md`.
- **T-SRC-05-3** Guard or gate. `scripts/search_eval.py` as a CI gate with recorded tolerances.

### AUD-02 (M, R1, `governance`)

AI output log with model, version, purpose, citations, review state and feedback.

- **T-AUD-02-1** Backend. Scenarios: AUD-S4. Spec: `backend/apps/governance/app.md`.
- **T-AUD-02-2** Screen and journey. Scenarios: AUD-S4. Journey spec: `frontend/tests/e2e/governance.journey.spec.ts`.

## Chunk 8

### TEN-02 (M, R2, `tenants`)

Legal entities with licences, and products described the way obligations are scoped.

- **T-TEN-02-1** Backend. Scenarios: TEN-S2. Spec: `backend/apps/tenants/app.md`.
- **T-TEN-02-2** Screen and journey. Scenarios: TEN-S2. Journey spec: `frontend/tests/e2e/tenants.journey.spec.ts`.

### TEN-03 (S, R2, `tenants`)

Teams as owners, so ownership survives a person leaving.

- **T-TEN-03-1** Backend. Scenarios: TEN-S3. Spec: `backend/apps/tenants/app.md`.

### TEN-04 (S, R2, `tenants`)

Out-of-office with a delegate for approvals and reminders.

- **T-TEN-04-1** Backend. Scenarios: TEN-S4. Spec: `backend/apps/tenants/app.md`.
- **T-TEN-04-2** Screen and journey. Scenarios: TEN-S4. Journey spec: `frontend/tests/e2e/tenants.journey.spec.ts`.

### TEN-05 (M, R2, `tenants`)

Removing a member who owns open work offers bulk reassignment.

- **T-TEN-05-1** Backend. Scenarios: TEN-S5. Spec: `backend/apps/tenants/app.md`.
- **T-TEN-05-2** Screen and journey. Scenarios: TEN-S5. Journey spec: `frontend/tests/e2e/tenants.journey.spec.ts`.

### TEN-06 (M, R2, `tenants`)

Support access grants: visible to the tenant, time-boxed, logged.

- **T-TEN-06-1** Backend. Scenarios: TEN-S6. Spec: `backend/apps/tenants/app.md`.
- **T-TEN-06-2** Screen and journey. Scenarios: TEN-S6, TEN-S7. Journey spec: `frontend/tests/e2e/tenants.journey.spec.ts`.

### VOC-04 (M, R2, `taxonomy`)

Statuses are tenant-defined inside fixed categories; a category never goes empty.

- **T-VOC-04-1** Backend. Scenarios: CAS-S13, VOC-S8. Spec: `backend/apps/taxonomy/app.md`.

### VOC-05 (S, R2, `taxonomy`)

Tenant scales for compliance status and risk mapped to fixed ordinals.

- **T-VOC-05-1** Backend. Scenarios: VOC-S9. Spec: `backend/apps/taxonomy/app.md`.

### VOC-06 (S, R2, `taxonomy`)

Reason lists for dismissal, closure and risk acceptance.

- **T-VOC-06-1** Backend. Scenarios: VOC-S10. Spec: `backend/apps/taxonomy/app.md`.

### REG-01 (M, R2, `register`)

Applicability per obligation with a reason, changed only through a request a second person approves.

- **T-REG-01-1** Backend. Scenarios: REG-S1, REG-S2, REG-S4. Spec: `backend/apps/register/app.md`.
- **T-REG-01-2** Screen and journey. Scenarios: REG-S1. Journey spec: `frontend/tests/e2e/register.journey.spec.ts`.

### REG-02 (M, R2, `register`)

Compliance status, status note, risk, owners, process, system, evidence location, next review, per legal entity where the obligation spans several.

- **T-REG-02-1** Backend. Scenarios: REG-S3, REG-S4, REG-S11. Spec: `backend/apps/register/app.md`.
- **T-REG-02-2** Screen and journey. Scenarios: REG-S3. Journey spec: `frontend/tests/e2e/register.journey.spec.ts`.

### REG-03 (M, R2, `register`)

Gaps with owner, severity, target date, remediation, and risk acceptance behind four eyes.

- **T-REG-03-1** Backend. Scenarios: REG-S5, REG-S6. Spec: `backend/apps/register/app.md`.
- **T-REG-03-2** Screen and journey. Scenarios: REG-S5, REG-S6. Journey spec: `frontend/tests/e2e/register.journey.spec.ts`.

### REG-04 (S, R2, `register`)

Assessment history and "how we read this rule" per obligation.

- **T-REG-04-1** Backend. Scenarios: REG-S7. Spec: `backend/apps/register/app.md`.
- **T-REG-04-2** Screen and journey. Scenarios: REG-S7. Journey spec: `frontend/tests/e2e/register.journey.spec.ts`.

### REG-05 (M, R2, `register`)

Linked internal items (policy, procedure, control, process, system) with external references.

- **T-REG-05-1** Backend. Scenarios: REG-S8. Spec: `backend/apps/register/app.md`.
- **T-REG-05-2** Screen and journey. Scenarios: REG-S8. Journey spec: `frontend/tests/e2e/register.journey.spec.ts`.

### REG-07 (S, R2, `register`)

Recurring duties on the roadmap from recurrence rules.

- **T-REG-07-1** Backend. Scenarios: REG-S10. Spec: `backend/apps/register/app.md`.

## Chunk 9

### CAS-02 (M, R2, `cases`)

Triage needs urgency and owner; dismissal needs a reason and can be restored.

- **T-CAS-02-1** Backend. Scenarios: CAS-S2, CAS-S3, CAS-S13. Spec: `backend/apps/cases/app.md`.
- **T-CAS-02-2** Screen and journey. Scenarios: CAS-S2, CAS-S3, CAS-S14. Journey spec: `frontend/tests/e2e/cases.journey.spec.ts`.

### CAS-03 (M, R2, `cases`)

Impact assessment: applies, why, what must change, internal deadline, effort, contributors.

- **T-CAS-03-1** Backend. Scenarios: CAS-S4, CAS-S5. Spec: `backend/apps/cases/app.md`.
- **T-CAS-03-2** Screen and journey. Scenarios: CAS-S4, CAS-S15. Journey spec: `frontend/tests/e2e/cases.journey.spec.ts`.

### CAS-04 (M, R2, `cases`)

Actions with owner and due date, locked while sign-off is pending, exportable as tickets.

- **T-CAS-04-1** Backend. Scenarios: CAS-S6. Spec: `backend/apps/cases/app.md`.
- **T-CAS-04-2** Screen and journey. Scenarios: CAS-S6, CAS-S15. Journey spec: `frontend/tests/e2e/cases.journey.spec.ts`.

### CAS-05 (M, R2, `cases`)

Evidence as file, link or reference, scanned, hashed, streamed through permission checks.

- **T-CAS-05-1** Backend. Scenarios: CAS-S7, CAS-S16. Spec: `backend/apps/cases/app.md`.
- **T-CAS-05-2** Screen and journey. Scenarios: CAS-S7, CAS-S15. Journey spec: `frontend/tests/e2e/cases.journey.spec.ts`.

### CAS-06 (M, R2, `cases`)

Sign-off only with no open action and at least one piece of evidence, only by a second person, with step-up.

- **T-CAS-06-1** Backend. Scenarios: CAS-S8, CAS-S9, CAS-S10. Spec: `backend/apps/cases/app.md`.
- **T-CAS-06-2** Screen and journey. Scenarios: CAS-S8, CAS-S9, CAS-S10, CAS-S15. Journey spec: `frontend/tests/e2e/cases.journey.spec.ts`.

### CAS-07 (M, R2, `cases`)

A case file that stands alone, as text and as an export.

- **T-CAS-07-1** Backend. Scenarios: CAS-S11, CAS-S16. Spec: `backend/apps/cases/app.md`.
- **T-CAS-07-2** Screen and journey. Scenarios: CAS-S11, CAS-S15. Journey spec: `frontend/tests/e2e/cases.journey.spec.ts`.

### CAS-08 (M, R2, `cases`)

Every response lists allowed transitions; concurrent edits are refused, never merged silently.

- **T-CAS-08-1** Backend. Scenarios: CAS-S5, CAS-S12. Spec: `backend/apps/cases/app.md`.
- **T-CAS-08-3** Guard or gate. The `allowedTransitions` contract test and the concurrency test with real threads.

## Chunk 10

### VOC-03 (S, R2, `taxonomy`)

Create where you use it: "Create" with `vocab.manage`, "Suggest" without, both with a near-duplicate hint.

- **T-VOC-03-1** Backend. Scenarios: VOC-S6, VOC-S7. Spec: `backend/apps/taxonomy/app.md`.
- **T-VOC-03-2** Screen and journey. Scenarios: VOC-S6, VOC-S7. Journey spec: `frontend/tests/e2e/taxonomy.journey.spec.ts`.

### VOC-08 (S, R2, `taxonomy`)

Bulk tagging from list views with preview and one audit entry.

- **T-VOC-08-1** Backend. Scenarios: VOC-S12. Spec: `backend/apps/taxonomy/app.md`.
- **T-VOC-08-2** Screen and journey. Scenarios: VOC-S12. Journey spec: `frontend/tests/e2e/taxonomy.journey.spec.ts`.

### COL-01 (S, R2, `collab`)

Comments and mentions on any record.

- **T-COL-01-1** Backend. Scenarios: COL-S1, COL-S5. Spec: `backend/apps/collab/app.md`.
- **T-COL-01-2** Screen and journey. Scenarios: COL-S1. Journey spec: `frontend/tests/e2e/collab.journey.spec.ts`.

### COL-02 (M, R2, `collab`)

Notifications, reminders before due dates, escalation after a threshold, a weekly digest in the user's language.

- **T-COL-02-1** Backend. Scenarios: COL-S2, COL-S3. Spec: `backend/apps/collab/app.md`.
- **T-COL-02-2** Screen and journey. Scenarios: COL-S2. Journey spec: `frontend/tests/e2e/collab.journey.spec.ts`.

## Chunk 11

### ID-07 (S, R2, `identity`)

Tenant credential policy: synced passkeys allowed, or attested device-bound authenticators required.

- **T-ID-07-1** Backend. Scenarios: ID-S16. Spec: `backend/apps/identity/app.md`.

### ID-08 (S, R2, `identity`)

Tenant session policy: idle and absolute limits within platform maximums.

- **T-ID-08-1** Backend. Scenarios: ID-S17. Spec: `backend/apps/identity/app.md`.

### PRO-04 (S, R2, `proposals`)

Batch proposals (re-tag, backfill) with a preview, approved whole or row by row.

- **T-PRO-04-1** Backend. Scenarios: PRO-S8. Spec: `backend/apps/proposals/app.md`.
- **T-PRO-04-2** Screen and journey. Scenarios: PRO-S8. Journey spec: `frontend/tests/e2e/proposals.journey.spec.ts`.

### AGT-03 (M, R2, `agents`)

Versioned agent definitions owned by the platform.

- **T-AGT-03-1** Backend. Scenarios: AGT-S4. Spec: `backend/apps/agents/app.md`.
- **T-AGT-03-2** Screen and journey. Scenarios: AGT-S4. Journey spec: `frontend/tests/e2e/agents.journey.spec.ts`.

### AGT-04 (M, R2, `agents`)

Tenant controls: on and off, cadence, scope, run now, pause, interrupt, history with findings and cost, monthly budget cap, AI off switch.

- **T-AGT-04-1** Backend. Scenarios: AGT-S5, AGT-S6. Spec: `backend/apps/agents/app.md`.
- **T-AGT-04-2** Screen and journey. Scenarios: AGT-S5, AGT-S6. Journey spec: `frontend/tests/e2e/agents.journey.spec.ts`.

### AGT-05 (S, R2, `agents`)

Research requests: check a source now, research a topic, re-tag existing records.

- **T-AGT-05-1** Backend. Scenarios: AGT-S7. Spec: `backend/apps/agents/app.md`.
- **T-AGT-05-2** Screen and journey. Scenarios: AGT-S7. Journey spec: `frontend/tests/e2e/agents.journey.spec.ts`.

### AGT-06 (M, R2, `agents`)

Runner adapter with a mock, the app as scheduler of record.

- **T-AGT-06-1** Backend. Scenarios: AGT-S8. Spec: `backend/apps/agents/app.md`.

## Chunk 12

### VOC-09 (S, R3, `taxonomy`)

Tenant configuration is versioned, exportable and importable.

- **T-VOC-09-1** Backend. Scenarios: VOC-S13. Spec: `backend/apps/taxonomy/app.md`.

### REP-01 (S, R3, `reports`)

Dashboard: open changes by urgency, overdue actions, gaps, unconfirmed AI drafts, time to triage, regime by account heatmap, load per owner.

- **T-REP-01-1** Backend. Scenarios: REP-S1. Spec: `backend/apps/reports/app.md`.
- **T-REP-01-2** Screen and journey. Scenarios: REP-S1. Journey spec: `frontend/tests/e2e/reports.journey.spec.ts`.

### REP-02 (S, R3, `reports`)

Committee pack and exports of inventory, changes, cases and the audit log.

- **T-REP-02-1** Backend. Scenarios: REP-S2, REP-S3. Spec: `backend/apps/reports/app.md`.
- **T-REP-02-2** Screen and journey. Scenarios: REP-S2. Journey spec: `frontend/tests/e2e/reports.journey.spec.ts`.

### REP-03 (S, R3, `reports`)

Spreadsheet register import: dry run, near-match mapping asked once per value, then commit.

- **T-REP-03-1** Backend. Scenarios: REP-S4. Spec: `backend/apps/reports/app.md`.
- **T-REP-03-2** Screen and journey. Scenarios: REP-S4. Journey spec: `frontend/tests/e2e/reports.journey.spec.ts`.

### REP-04 (M, R3, `reports`)

Full tenant export in open formats and verified deletion.

- **T-REP-04-1** Backend. Scenarios: REP-S5. Spec: `backend/apps/reports/app.md`.
- **T-REP-04-2** Screen and journey. Scenarios: REP-S5. Journey spec: `frontend/tests/e2e/reports.journey.spec.ts`.

### AUD-04 (S, R3, `governance`)

Retention per tenant with a purge that respects append-only tables.

- **T-AUD-04-1** Backend. Scenarios: AUD-S6. Spec: `backend/apps/governance/app.md`.

## Chunk 13

### ID-12 (C, R3, `identity`)

SSO (OIDC, SAML), verified domains and SCIM as a tenant option.

- **T-ID-12-1** Backend. Scenarios: ID-S23. Spec: `backend/apps/identity/app.md`.

### ID-13 (C, R3, `identity`)

Optional IP allow-list per tenant.

- **T-ID-13-1** Backend. Scenarios: ID-S24. Spec: `backend/apps/identity/app.md`.

### INV-07 (C, R3, `library`)

Tenant-private instruments and obligations from the tenant's own sources.

- **T-INV-07-1** Backend. Scenarios: INV-S9. Spec: `backend/apps/library/app.md`.

### WAT-06 (S, R3, `watch`)

Tenants can request a source; private sources are visible to that tenant only.

- **T-WAT-06-1** Backend. Scenarios: WAT-S8. Spec: `backend/apps/watch/app.md`.
- **T-WAT-06-2** Screen and journey. Scenarios: WAT-S8. Journey spec: `frontend/tests/e2e/watch.journey.spec.ts`.

### REG-06 (C, R3, `register`)

Yearly attestation by the owner, and waivers.

- **T-REG-06-1** Backend. Scenarios: REG-S9. Spec: `backend/apps/register/app.md`.
- **T-REG-06-2** Screen and journey. Scenarios: REG-S9. Journey spec: `frontend/tests/e2e/register.journey.spec.ts`.

### SRC-04 (S, R3, `search`)

Saved searches with notification, and "what changed since my last visit".

- **T-SRC-04-1** Backend. Scenarios: SRC-S7. Spec: `backend/apps/search/app.md`.
- **T-SRC-04-2** Screen and journey. Scenarios: SRC-S7. Journey spec: `frontend/tests/e2e/search.journey.spec.ts`.

### COL-03 (C, R3, `collab`)

Follow a record.

- **T-COL-03-1** Backend. Scenarios: COL-S4. Spec: `backend/apps/collab/app.md`.
- **T-COL-03-2** Screen and journey. Scenarios: COL-S4. Journey spec: `frontend/tests/e2e/collab.journey.spec.ts`.

### INT-01 (S, R3, `integrations`)

Signed webhooks with a delivery log, from a transactional outbox.

- **T-INT-01-1** Backend. Scenarios: INT-S1, INT-S2, INT-S5. Spec: `backend/apps/integrations/app.md`.
- **T-INT-01-2** Screen and journey. Scenarios: INT-S1. Journey spec: `frontend/tests/e2e/integrations.journey.spec.ts`.

### INT-02 (C, R3, `integrations`)

Ticket export for actions.

- **T-INT-02-1** Backend. Scenarios: INT-S3. Spec: `backend/apps/integrations/app.md`.
- **T-INT-02-2** Screen and journey. Scenarios: INT-S3. Journey spec: `frontend/tests/e2e/integrations.journey.spec.ts`.

### INT-03 (S, R3, `integrations`)

Audit log stream to the customer's SIEM.

- **T-INT-03-1** Backend. Scenarios: INT-S4. Spec: `backend/apps/integrations/app.md`.
- **T-INT-03-2** Screen and journey. Scenarios: INT-S4. Journey spec: `frontend/tests/e2e/integrations.journey.spec.ts`.

### I18N-02 (M, R1, `shared`)

UI in `en` and `sv` at R1, the others by R3, from message catalogs.

- **T-I18N-02-1** Backend. Scenarios: none (frontend-owned). Spec: `backend/apps/shared/app.md`.
- **T-I18N-02-2** Screen and journey. Scenarios: I18N-S3, I18N-S4. Journey spec: `frontend/tests/e2e/shared.journey.spec.ts`.
- **T-I18N-02-3** Guard or gate. `messages-check.mjs` and the copy-drift check.

## Chunk 14

### NFR-02 (M, R1, `shared`)

Performance budgets of playbook 10.

- **T-NFR-02-1** Backend. Scenarios: NFR-S6, SRC-S9. Spec: `backend/apps/shared/app.md`.
- **T-NFR-02-2** Screen and journey. Scenarios: NFR-S7. Journey spec: `frontend/tests/e2e/shared.journey.spec.ts`.
- **T-NFR-02-3** Guard or gate. `Server-Timing` middleware, the budget WARNING, `assertNumQueries` pins on list endpoints.

### NFR-04 (M, R3, `shared`)

EU-only hosting and the assurance pack of playbook 18.

- **T-NFR-04-1** Backend. Scenarios: NFR-S11, NFR-S12, NFR-S14, NFR-S15. Spec: `backend/apps/shared/app.md`.
- **T-NFR-04-3** Guard or gate. Boot guards in `settings.py` proven in subprocesses; Sentry scrubbers; the compliance lint for logs.

### NFR-05 (C, R3, `billing`)

Billing: plans, limits, usage.

- **T-NFR-05-1** Backend. Scenarios: NFR-S17, NFR-S18, NFR-S19. Spec: `backend/apps/billing/app.md`.
- **T-NFR-05-2** Screen and journey. Scenarios: NFR-S17, NFR-S19. Journey spec: `frontend/tests/e2e/billing.journey.spec.ts`.

## Coverage index

Requirement → app.md → scenario IDs (every app that references the requirement). `@i` integration, `@e` E2E, `@ie` both.

| Requirement | app.md | Scenarios |
|---|---|---|
| ID-01 | `backend/apps/identity/app.md` | ID-S1 @i, ID-S25 @e |
| ID-02 | `backend/apps/identity/app.md` | ID-S2 @i, ID-S3 @i, ID-S4 @ie, ID-S5 @ie, ID-S25 @e |
| ID-03 | `backend/apps/identity/app.md` | ID-S5 @ie, ID-S6 @ie, ID-S7 @i, ID-S8 @ie, ID-S9 @i, ID-S25 @e |
| ID-04 | `backend/apps/identity/app.md` | ID-S10 @ie, ID-S11 @ie |
| ID-05 | `backend/apps/identity/app.md` | ID-S12 @ie, ID-S13 @i |
| ID-06 | `backend/apps/identity/app.md` | ID-S14 @ie, ID-S15 @i |
| ID-07 | `backend/apps/identity/app.md` | ID-S16 @i |
| ID-08 | `backend/apps/identity/app.md` | ID-S17 @i |
| ID-09 | `backend/apps/identity/app.md` | ID-S18 @ie, ID-S19 @i, ID-S26 @ie |
| ID-10 | `backend/apps/identity/app.md` | ID-S20 @ie, ID-S21 @i |
| ID-11 | `backend/apps/identity/app.md` | ID-S22 @i |
| ID-12 | `backend/apps/identity/app.md` | ID-S23 @i |
| ID-13 | `backend/apps/identity/app.md` | ID-S24 @i |
| TEN-01 | `backend/apps/tenants/app.md` | TEN-S1 @ie |
| TEN-02 | `backend/apps/tenants/app.md` | TEN-S2 @ie |
| TEN-03 | `backend/apps/tenants/app.md` | TEN-S3 @i |
| TEN-04 | `backend/apps/tenants/app.md` | TEN-S4 @ie |
| TEN-05 | `backend/apps/tenants/app.md` | TEN-S5 @ie |
| TEN-06 | `backend/apps/tenants/app.md` | TEN-S6 @ie, TEN-S7 @e |
| VOC-01 | `backend/apps/taxonomy/app.md` | VOC-S1 @i, VOC-S2 @ie, VOC-S14 @i, VOC-S15 @e |
| VOC-02 | `backend/apps/taxonomy/app.md` | VOC-S3 @ie, VOC-S4 @ie, VOC-S5 @ie, VOC-S15 @e |
| VOC-03 | `backend/apps/taxonomy/app.md` | VOC-S6 @ie, VOC-S7 @ie |
| VOC-04 | `backend/apps/taxonomy/app.md` | CAS-S13 @i, VOC-S8 @i |
| VOC-05 | `backend/apps/taxonomy/app.md` | VOC-S9 @i |
| VOC-06 | `backend/apps/taxonomy/app.md` | VOC-S10 @i |
| VOC-07 | `backend/apps/taxonomy/app.md` | VOC-S11 @ie, VOC-S15 @e |
| VOC-08 | `backend/apps/taxonomy/app.md` | VOC-S12 @ie |
| VOC-09 | `backend/apps/taxonomy/app.md` | VOC-S13 @i |
| FP-01 | `backend/apps/taxonomy/app.md` | FP-S1 @i, FP-S5 @e |
| FP-02 | `backend/apps/taxonomy/app.md` | FP-S2 @ie, FP-S3 @i, FP-S5 @e |
| FP-03 | `backend/apps/taxonomy/app.md` | FP-S4 @ie, FP-S5 @e |
| INV-01 | `backend/apps/library/app.md` | INV-S1 @ie, INV-S10 @i |
| INV-02 | `backend/apps/library/app.md` | INV-S2 @ie, INV-S10 @i |
| INV-03 | `backend/apps/library/app.md` | INV-S3 @ie |
| INV-04 | `backend/apps/library/app.md` | AGT-S10 @e, INV-S4 @ie, INV-S5 @ie |
| INV-05 | `backend/apps/library/app.md` | INV-S6 @ie |
| INV-06 | `backend/apps/library/app.md` | INV-S7 @ie, INV-S8 @i |
| INV-07 | `backend/apps/library/app.md` | INV-S9 @i |
| PRO-01 | `backend/apps/proposals/app.md` | PRO-S1 @i, PRO-S2 @i, PRO-S6 @i, PRO-S9 @ie |
| PRO-02 | `backend/apps/proposals/app.md` | AGT-S10 @e, PRO-S3 @ie, PRO-S4 @ie, PRO-S5 @ie |
| PRO-03 | `backend/apps/proposals/app.md` | PRO-S7 @ie |
| PRO-04 | `backend/apps/proposals/app.md` | PRO-S8 @ie |
| WAT-01 | `backend/apps/watch/app.md` | WAT-S1 @ie |
| WAT-02 | `backend/apps/watch/app.md` | AGT-S10 @e, WAT-S2 @ie, WAT-S3 @i |
| WAT-03 | `backend/apps/watch/app.md` | WAT-S4 @ie, WAT-S5 @i, WAT-S9 @e |
| WAT-04 | `backend/apps/watch/app.md` | WAT-S6 @ie |
| WAT-05 | `backend/apps/watch/app.md` | CAS-S14 @e, WAT-S7 @ie |
| WAT-06 | `backend/apps/watch/app.md` | WAT-S8 @ie |
| REG-01 | `backend/apps/register/app.md` | REG-S1 @ie, REG-S2 @i, REG-S4 @i |
| REG-02 | `backend/apps/register/app.md` | REG-S3 @ie, REG-S4 @i, REG-S11 @i |
| REG-03 | `backend/apps/register/app.md` | REG-S5 @ie, REG-S6 @ie |
| REG-04 | `backend/apps/register/app.md` | REG-S7 @ie |
| REG-05 | `backend/apps/register/app.md` | REG-S8 @ie |
| REG-06 | `backend/apps/register/app.md` | REG-S9 @ie |
| REG-07 | `backend/apps/register/app.md` | REG-S10 @i |
| CAS-01 | `backend/apps/cases/app.md` | CAS-S1 @i, CAS-S14 @e |
| CAS-02 | `backend/apps/cases/app.md` | CAS-S2 @ie, CAS-S3 @ie, CAS-S13 @i, CAS-S14 @e |
| CAS-03 | `backend/apps/cases/app.md` | CAS-S4 @ie, CAS-S5 @i, CAS-S15 @e |
| CAS-04 | `backend/apps/cases/app.md` | CAS-S6 @ie, CAS-S15 @e |
| CAS-05 | `backend/apps/cases/app.md` | CAS-S7 @ie, CAS-S15 @e, CAS-S16 @i |
| CAS-06 | `backend/apps/cases/app.md` | CAS-S8 @ie, CAS-S9 @ie, CAS-S10 @ie, CAS-S15 @e |
| CAS-07 | `backend/apps/cases/app.md` | CAS-S11 @ie, CAS-S15 @e, CAS-S16 @i |
| CAS-08 | `backend/apps/cases/app.md` | CAS-S5 @i, CAS-S12 @i |
| SRC-01 | `backend/apps/search/app.md` | SRC-S1 @ie, SRC-S2 @i, SRC-S9 @i, SRC-S10 @e, SRC-S11 @i |
| SRC-02 | `backend/apps/search/app.md` | SRC-S3 @ie, SRC-S10 @e |
| SRC-03 | `backend/apps/search/app.md` | SRC-S4 @ie, SRC-S5 @ie, SRC-S6 @i, SRC-S10 @e |
| SRC-04 | `backend/apps/search/app.md` | SRC-S7 @ie |
| SRC-05 | `backend/apps/search/app.md` | SRC-S8 @i |
| HOM-01 | `backend/apps/home/app.md` | CAS-S14 @e, HOM-S1 @ie, HOM-S2 @e |
| HOM-02 | `backend/apps/home/app.md` | HOM-S3 @ie |
| HOM-03 | `backend/apps/home/app.md` | HOM-S4 @ie, HOM-S6 @e |
| HOM-04 | `backend/apps/home/app.md` | HOM-S5 @ie |
| COL-01 | `backend/apps/collab/app.md` | COL-S1 @ie, COL-S5 @i |
| COL-02 | `backend/apps/collab/app.md` | COL-S2 @ie, COL-S3 @i |
| COL-03 | `backend/apps/collab/app.md` | COL-S4 @ie |
| AGT-01 | `backend/apps/agents/app.md` | AGT-S1 @i, AGT-S2 @i, AGT-S10 @e |
| AGT-02 | `backend/apps/agents/app.md` | AGT-S3 @i |
| AGT-03 | `backend/apps/agents/app.md` | AGT-S4 @ie |
| AGT-04 | `backend/apps/agents/app.md` | AGT-S5 @ie, AGT-S6 @ie |
| AGT-05 | `backend/apps/agents/app.md` | AGT-S7 @ie |
| AGT-06 | `backend/apps/agents/app.md` | AGT-S8 @i |
| AGT-07 | `backend/apps/agents/app.md` | AGT-S9 @i |
| REP-01 | `backend/apps/reports/app.md` | REP-S1 @ie |
| REP-02 | `backend/apps/reports/app.md` | REP-S2 @ie, REP-S3 @i |
| REP-03 | `backend/apps/reports/app.md` | REP-S4 @ie |
| REP-04 | `backend/apps/reports/app.md` | REP-S5 @ie |
| INT-01 | `backend/apps/integrations/app.md` | INT-S1 @ie, INT-S2 @i, INT-S5 @i |
| INT-02 | `backend/apps/integrations/app.md` | INT-S3 @ie |
| INT-03 | `backend/apps/integrations/app.md` | INT-S4 @ie |
| AUD-01 | `backend/apps/governance/app.md` | AUD-S1 @i, AUD-S2 @i, AUD-S3 @e, AUD-S7 @i |
| AUD-02 | `backend/apps/governance/app.md` | AUD-S4 @ie |
| AUD-03 | `backend/apps/governance/app.md` | AUD-S5 @ie |
| AUD-04 | `backend/apps/governance/app.md` | AUD-S6 @i |
| ADM-01 | `backend/apps/tenants/app.md` | ADM-S1 @ie, ADM-S2 @e |
| ADM-02 | `backend/apps/governance/app.md` | ADM-S4 @ie, ADM-S5 @ie, ADM-S6 @ie |
| ADM-03 | `backend/apps/tenants/app.md` | ADM-S1 @ie, ADM-S3 @ie |
| I18N-01 | `backend/apps/taxonomy/app.md` | I18N-S1 @i, I18N-S2 @i |
| I18N-02 | `backend/apps/shared/app.md` | I18N-S3 @e, I18N-S4 @e |
| NFR-01 | `backend/apps/shared/app.md` | CAS-S16 @i, NFR-S1 @i, NFR-S2 @i, NFR-S3 @i, NFR-S4 @i, NFR-S5 @i, NFR-S13 @i, NFR-S16 @i |
| NFR-02 | `backend/apps/shared/app.md` | NFR-S6 @i, NFR-S7 @e, SRC-S9 @i |
| NFR-03 | `backend/apps/shared/app.md` | NFR-S8 @e, NFR-S9 @e, NFR-S10 @i, WAT-S9 @e |
| NFR-04 | `backend/apps/shared/app.md` | NFR-S11 @i, NFR-S12 @i, NFR-S14 @i, NFR-S15 @i |
| NFR-05 | `backend/apps/billing/app.md` | NFR-S17 @ie, NFR-S18 @i, NFR-S19 @ie |

### Acceptance criteria

| AC | Scenarios |
|---|---|
| AC-AUD1 | AUD-S1, AUD-S2 |
| AC-CAS1 | CAS-S8, CAS-S9, CAS-S15 |
| AC-CAS2 | CAS-S5 |
| AC-FP1 | FP-S2, FP-S5 |
| AC-ID1 | ID-S6, ID-S25 |
| AC-ID2 | ID-S4 |
| AC-ID3 | ID-S14, ID-S15 |
| AC-INV1 | INV-S4, INV-S5 |
| AC-NFR1 | NFR-S1 |
| AC-NFR2 | NFR-S2 |
| AC-NFR3 | NFR-S8, NFR-S9 |
| AC-PRO1 | ID-S21, PRO-S2 |
| AC-PRO2 | PRO-S5 |
| AC-SRC1 | SRC-S1, SRC-S10 |
| AC-SRC2 | SRC-S4, SRC-S5, SRC-S10 |
| AC-VOC1 | VOC-S2, VOC-S15 |
| AC-VOC2 | VOC-S4, VOC-S15 |
| AC-VOC3 | VOC-S7 |
| AC-WAT1 | WAT-S3 |
| AC-WAT2 | WAT-S5 |

### Golden-path journeys (`@smoke`)

| Journey | `@e2e` scenario | Lives in |
|---|---|---|
| J-1 | ID-S25 | `identity` |
| J-2 | CAS-S14 | `cases` |
| J-3 | CAS-S15 | `cases` |
| J-4 | AGT-S10 | `agents` |
| J-5 | VOC-S15 | `taxonomy` |
| J-6 | FP-S5 | `taxonomy` |
| J-7 | SRC-S10 | `search` |
| J-8 | TEN-S7 | `tenants` |

### Totals

| App | Requirements | Scenarios | `@integration` | `@e2e` |
|---|---|---|---|---|
| `agents` | 7 | 10 | 9 | 5 |
| `billing` | 1 | 3 | 3 | 2 |
| `cases` | 8 | 16 | 14 | 11 |
| `collab` | 3 | 5 | 5 | 3 |
| `governance` | 5 | 10 | 9 | 6 |
| `home` | 4 | 6 | 4 | 6 |
| `identity` | 13 | 26 | 25 | 12 |
| `integrations` | 3 | 5 | 5 | 3 |
| `library` | 7 | 10 | 10 | 7 |
| `proposals` | 4 | 9 | 9 | 6 |
| `register` | 7 | 11 | 11 | 7 |
| `reports` | 4 | 5 | 5 | 4 |
| `search` | 5 | 11 | 10 | 6 |
| `shared` | 5 | 18 | 13 | 5 |
| `taxonomy` | 13 | 22 | 20 | 12 |
| `tenants` | 8 | 10 | 8 | 9 |
| `watch` | 6 | 9 | 8 | 7 |
| **Total** | **103** | **186** | **168** | **111** |

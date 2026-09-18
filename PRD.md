# Compliance Watch: product requirements

| Version | Date | Change | Decided by |
|---|---|---|---|
| 0.1 | 2026-09-19 | First PRD. Consolidates the journey and capability list from the Compliance Watch chat, the data model and API work from the Compliance Data chat, the playbook review, and the decisions on passkeys, Nordic scope, admin-owned vocabularies, the pill system and Green tokens | Alex |

Requirement IDs never appear on screen. Priority is MoSCoW (M, S, C).
Release: R1 makes it useful alone, R2 makes it a system of record, R3 is what
large buyers require. Every requirement starts at status `pending` in its
app's `app.md`.

## 1. Product

Compliance Watch keeps one obligations inventory current and carries every
regulatory change from first sighting to signed-off evidence. Research agents
find and propose, people decide, and every decision is logged. It is built for
enterprise banks in the Nordics: Swedish, Danish, Norwegian, Finnish and EU
sources, five content languages, bank-grade access control, and an assurance
pack a vendor review can use.

**Wedge.** Inventory plus watch, done deeply for Nordic sources, with
paragraph-level citations and a plain verdict on every item.
**Out of scope by decision.** Control testing, policy management, incidents
and risk registers. Obligations carry linked internal items and the API lets
an existing GRC system integrate.

**Users.** Compliance officer (triages, curates the register), obligation
owner (assesses, plans, evidences), approver (second pair of eyes),
contributor (legal, product, tech input), reader, auditor (read-only with
exports), tenant admin (people, configuration, security), and on the platform
side the library editor and the platform admin.

## 2. The journey

| Stage | What happens | Done when |
|---|---|---|
| 0. Set the footprint | The company describes itself once: entities and licences, products and account types, services, client categories, jurisdictions, teams. An existing spreadsheet register can be imported | Everything downstream is filtered by it |
| 1. Build the inventory | Instruments are broken into obligations. Per obligation the company records whether it applies and why, who owns it, its compliance status per entity, and linked internal items | A reasoned "not applicable" is stored as carefully as "applies" |
| 2. Watch | Agents detect changes, classify them, merge duplicates, link affected obligations and score against the footprint | Every finding lands in a queue, never directly in the inventory |
| 3. Triage | A compliance officer confirms relevance, sets urgency and owner, or dismisses with a reason | Every incoming item has a decision |
| 4. Assess | The owner completes a short impact assessment with input from colleagues | What applies, what must change, by when, at what effort |
| 5. Plan and implement | Actions with owners and deadlines, exportable as tickets | Status flows back |
| 6. Close and evidence | Evidence attached, sign-off by a second person, inventory updated through its own proposal | The case file stands alone |
| 7. Report and review | Dashboards, committee pack, periodic re-verification, yearly attestation | The slow loop runs |
| 8. Answer questions | Search and cited answers with an "as of" date | A question takes a minute |

## 3. Requirements

### ID: identity and access

| ID | Requirement | P | R |
|---|---|---|---|
| ID-01 | Users join by invitation only, with roles set at invite | M | R1 |
| ID-02 | First sign-in uses a one-time emailed code and leads straight into passkey enrolment. The enrolment session can do nothing else | M | R1 |
| ID-03 | After the first passkey, sign-in is by passkey only and the emailed code stops working for that account. No password exists anywhere | M | R1 |
| ID-04 | Users manage their passkeys (add, rename, remove, never the last one) and see and revoke their sessions | M | R1 |
| ID-05 | Recovery: a tenant admin re-issues enrolment behind step-up, audited, with notices. The last admin recovers through platform support with an out-of-band check | M | R1 |
| ID-06 | Step-up by fresh passkey assertion on the sensitive actions listed in playbook 4.2, recorded on the audit event | M | R1 |
| ID-07 | Tenant credential policy: allow synced passkeys or require attested device-bound authenticators | S | R2 |
| ID-08 | Tenant session policy: idle and absolute limits within platform maximums | S | R2 |
| ID-09 | Permissions are code, roles are rows: seeded system roles plus tenant-defined roles. A tenant always keeps one admin | M | R1 |
| ID-10 | Scoped API keys for agents and integrations, shown once, stored hashed, revocable, with last use | M | R1 |
| ID-11 | Security log of sign-ins, failures, enrolments, recoveries and key use | M | R1 |
| ID-12 | SSO (OIDC, SAML), verified domains and SCIM as a tenant option | C | R3 |
| ID-13 | Optional IP allow-list per tenant | C | R3 |

### TEN: tenant and organisation

| ID | Requirement | P | R |
|---|---|---|---|
| TEN-01 | Tenant profile, timezone, default languages, onboarding checklist | M | R1 |
| TEN-02 | Legal entities with licences, and products described the way obligations are scoped | M | R2 |
| TEN-03 | Teams as owners, so ownership survives a person leaving | S | R2 |
| TEN-04 | Out-of-office with a delegate for approvals and reminders | S | R2 |
| TEN-05 | Removing a member who owns open work offers bulk reassignment | M | R2 |
| TEN-06 | Support access grants: visible to the tenant, time-boxed, logged | M | R2 |

### VOC: vocabularies and configuration

| ID | Requirement | P | R |
|---|---|---|---|
| VOC-01 | Every list a person might extend is rows, in three tiers (playbook 15). Only kinds are code | M | R1 |
| VOC-02 | One vocabulary screen per surface: rows render as the real pill in light and dark with usage count, inline rename, drag to reorder, retire, merge | M | R1 |
| VOC-03 | Create where you use it: "Create" with `vocab.manage`, "Suggest" without, both with a near-duplicate hint | S | R2 |
| VOC-04 | Statuses are tenant-defined inside fixed categories. A category never goes empty | M | R2 |
| VOC-05 | Tenant scales for compliance status and risk, mapped to fixed ordinals | S | R2 |
| VOC-06 | Reason lists for dismissal, closure and risk acceptance | S | R2 |
| VOC-07 | Library vocabulary changes go through the proposal queue | M | R1 |
| VOC-08 | Bulk tagging from list views with preview and one audit entry | S | R2 |
| VOC-09 | Tenant configuration is versioned, exportable and importable | S | R3 |

### FP: footprint

| ID | Requirement | P | R |
|---|---|---|---|
| FP-01 | Footprint across all taxonomy dimensions. A record matches when every dimension it carries has a term in the footprint. An empty dimension does not restrict | M | R1 |
| FP-02 | A footprint change previews what it hides and reveals, needs a second person and step-up, and writes one audit event per term | M | R1 |
| FP-03 | Feed, inventory, roadmap, briefing and reports respect the footprint, with a visible way to look outside it | M | R1 |

### INV: inventory (library)

| ID | Requirement | P | R |
|---|---|---|---|
| INV-01 | Instruments with level, binding force, official reference, ELI where available, jurisdiction, authority, in-force dates and lineage | M | R1 |
| INV-02 | Provision tree with verbatim text versions, in-force dates and transitional notes | S | R1 |
| INV-03 | Obligations: plain-language duty, duty type, scope facets, trigger, retention, sanction exposure, provenance, related obligations | M | R1 |
| INV-04 | Versioned summaries with effective dates, "as of" reads and a sentence-level diff | M | R1 |
| INV-05 | Text in the original language plus translations, machine translations labelled | M | R1 |
| INV-06 | Source link and last-verified date on every record, and a "this looks wrong" report | M | R1 |
| INV-07 | Tenant-private instruments and obligations from the tenant's own sources | C | R3 |

### PRO: proposals

| ID | Requirement | P | R |
|---|---|---|---|
| PRO-01 | The review queue is the only way into the library, for agents and people, with a source per changed field | M | R1 |
| PRO-02 | Approval applies the payload, writes the version, the audit row and the re-index in one transaction. The reviewer can correct scope and wording first. Never the proposer | M | R1 |
| PRO-03 | The queue lives in the platform console. Tenants see library updates and can report problems | M | R1 |
| PRO-04 | Batch proposals (re-tag, backfill) with a preview, approved whole or row by row | S | R2 |

### WAT: watch

| ID | Requirement | P | R |
|---|---|---|---|
| WAT-01 | Source registry and coverage log: what was checked, when, with what result | M | R1 |
| WAT-02 | One record per reform with a timeline from consultation to in force, partial dates, and duplicates merged | M | R1 |
| WAT-03 | Change types, flags and scope from vocabularies. Agent classifications shown as suggestions until confirmed | M | R1 |
| WAT-04 | Links to affected obligations with confidence, confirmed by a person | M | R1 |
| WAT-05 | A drafted "So what?" per change, labelled AI-drafted until a person confirms or rewrites it per tenant | M | R1 |
| WAT-06 | Tenants can request a source. Private sources are visible to that tenant only | S | R3 |

### REG: register

| ID | Requirement | P | R |
|---|---|---|---|
| REG-01 | Applicability per obligation with a reason, changed only through a request a second person approves | M | R2 |
| REG-02 | Compliance status, status note, risk, owners, process, system, evidence location, next review, per legal entity where the obligation spans several | M | R2 |
| REG-03 | Gaps with owner, severity, target date, remediation, and risk acceptance behind four eyes | M | R2 |
| REG-04 | Assessment history and "how we read this rule" per obligation | S | R2 |
| REG-05 | Linked internal items (policy, procedure, control, process, system) with external references | M | R2 |
| REG-06 | Yearly attestation by the owner, and waivers | C | R3 |
| REG-07 | Recurring duties on the roadmap from recurrence rules | S | R2 |

### CAS: case workflow

| ID | Requirement | P | R |
|---|---|---|---|
| CAS-01 | One case per tenant per change, created in "needs triage" with its footprint match | M | R1 |
| CAS-02 | Triage needs urgency and owner. Dismissal needs a reason and can be restored | M | R2 |
| CAS-03 | Impact assessment: applies, why, what must change, internal deadline, effort, contributors | M | R2 |
| CAS-04 | Actions with owner and due date, locked while sign-off is pending, exportable as tickets | M | R2 |
| CAS-05 | Evidence as file, link or reference, scanned, hashed, streamed through permission checks | M | R2 |
| CAS-06 | Sign-off only with no open action and at least one piece of evidence, only by a second person, with step-up | M | R2 |
| CAS-07 | A case file that stands alone, as text and as an export | M | R2 |
| CAS-08 | Every response lists allowed transitions. Concurrent edits are refused, never merged silently | M | R2 |

### SRC: search and ask

| ID | Requirement | P | R |
|---|---|---|---|
| SRC-01 | Hybrid search: exact identifiers by keyword, concepts by vector, fused by rank, reranked, per language | M | R1 |
| SRC-02 | Filters from vocabularies, an "as of" date, and the match kind on every hit | M | R1 |
| SRC-03 | Cited answers grounded only in the inventory, with pending changes flagged and "no answer" instead of a guess | M | R1 |
| SRC-04 | Saved searches with notification, and "what changed since my last visit" | S | R3 |
| SRC-05 | An evaluation set that gates releases | M | R1 |

### HOM: home, briefing, roadmap

| ID | Requirement | P | R |
|---|---|---|---|
| HOM-01 | Timeline home: the next dates as a short list on every screen size, the lead item, what needs a decision, compliance standing, source health | M | R1 |
| HOM-02 | Weekly briefing, reachable from home with part of it shown there, snapshotted when emailed | M | R1 |
| HOM-03 | Roadmap page by quarter, regulatory dates and our own deadlines, a card expanding in place | M | R1 |
| HOM-04 | Upcoming changes as public facts for agents and newsletters, and a revocable calendar feed | S | R1 |

### COL: collaboration

| ID | Requirement | P | R |
|---|---|---|---|
| COL-01 | Comments and mentions on any record | S | R2 |
| COL-02 | Notifications, reminders before due dates, escalation after a threshold, a weekly digest in the user's language | M | R2 |
| COL-03 | Follow a record | C | R3 |

### AGT: agents

| ID | Requirement | P | R |
|---|---|---|---|
| AGT-01 | Agent API: open a run, log source checks, find similar, register changes idempotently, submit proposals, close the run | M | R1 |
| AGT-02 | Agents read vocabularies at run start and may use existing keys only | M | R1 |
| AGT-03 | Versioned agent definitions owned by the platform | M | R2 |
| AGT-04 | Tenant controls: on and off, cadence, scope, run now, pause, interrupt, history with findings and cost, monthly budget cap, AI off switch | M | R2 |
| AGT-05 | Research requests: check a source now, research a topic, re-tag existing records | S | R2 |
| AGT-06 | Runner adapter with a mock, the app as scheduler of record | M | R2 |
| AGT-07 | Fetched content screened for embedded instructions | M | R1 |

### REP, INT: reporting and integration

| ID | Requirement | P | R |
|---|---|---|---|
| REP-01 | Dashboard: open changes by urgency, overdue actions, gaps, unconfirmed AI drafts, time to triage, regime by account heatmap, load per owner | S | R3 |
| REP-02 | Committee pack and exports of inventory, changes, cases and the audit log | S | R3 |
| REP-03 | Spreadsheet register import: dry run, near-match mapping asked once per value, then commit | S | R3 |
| REP-04 | Full tenant export in open formats and verified deletion | M | R3 |
| INT-01 | Signed webhooks with a delivery log, from a transactional outbox | S | R3 |
| INT-02 | Ticket export for actions | C | R3 |
| INT-03 | Audit log stream to the customer's SIEM | S | R3 |

### AUD: audit and AI governance

| ID | Requirement | P | R |
|---|---|---|---|
| AUD-01 | Append-only audit log written with every change: actor (user, agent, system), action, subject with its title at the time, summary, before and after | M | R1 |
| AUD-02 | AI output log with model, version, purpose, citations, review state and feedback | M | R1 |
| AUD-03 | Problem reports resolved by a proposal, closing the loop to the agents | S | R1 |
| AUD-04 | Retention per tenant with a purge that respects append-only tables | S | R3 |

### ADM: admin surfaces

| ID | Requirement | P | R |
|---|---|---|---|
| ADM-01 | Tenant admin: organisation, members and invitations, passkey re-enrolment, sessions, roles, footprint, vocabularies, workflow policy, agents, integrations, security policy, data, audit log | M | R1 to R3, following the features |
| ADM-02 | Platform console: library vocabularies, sources, languages and jurisdictions, agent definitions, proposal queue, problem reports, evaluation sets, tenants and plans, support access, system health (coverage, runs, outbox lag, failed jobs with retry) | M | R1 to R3 |
| ADM-03 | Admin duties are separate permissions, so user administration and business configuration can sit with different people | M | R1 |

### I18N and NFR

| ID | Requirement | P | R |
|---|---|---|---|
| I18N-01 | Content in `en`, `sv`, `da`, `nb`, `fi` as translation rows. Jurisdictions EU, SE, DK, NO, FI as data | M | R1 |
| I18N-02 | UI in `en` and `sv` at R1, the others by R3, from message catalogs | M | R1 |
| NFR-01 | Tenant isolation by row-level security, proven per route | M | R1 |
| NFR-02 | Performance budgets of playbook 10 | M | R1 |
| NFR-03 | The design is reproduced: flow, labels, six-tone pill system, light and dark, WCAG AA | M | R1 |
| NFR-04 | EU-only hosting and the assurance pack of playbook 18 | M | R3 |
| NFR-05 | Billing: plans, limits, usage | C | R3 |

## 4. Acceptance criteria (condensed)

- **AC-ID1** A user who has a passkey requests a code: the response matches any other request and no email is sent. **AC-ID2** The enrolment session receives 403 on every route except passkey registration and `GET /me`. **AC-ID3** A sensitive action without a fresh assertion answers 403 `step_up_required`, and the audit event of a completed one references the assertion.
- **AC-NFR1** For every tenant route, a record of tenant A requested by tenant B answers 404. **AC-NFR2** The app refuses to boot on a database role that can bypass row-level security.
- **AC-PRO1** No API key scope and no tenant role can change a library record except through an approved proposal. **AC-PRO2** Approving your own proposal answers 409 `four_eyes_violation`.
- **AC-VOC1** An admin adds a change type, a tag and a sub-status with no deploy: each appears in pickers, filters, agent vocabulary reads and pills, and `openapi.json` is unchanged. **AC-VOC2** Retiring a used value keeps history readable and removes it from pickers. **AC-VOC3** Creating "custody " when "Custody" exists is refused with the near match offered.
- **AC-FP1** Switching off "Advice" previews the obligations and open cases it hides, waits for a second person, then hides advice-only obligations and changes everywhere.
- **AC-INV1** "As of" a date returns the version in force on it, and the diff shows what changed between two versions.
- **AC-CAS1** Sign-off is refused with `open_actions` or `evidence_missing`, and with `four_eyes_violation` for the requester. **AC-CAS2** Two people saving the same assessment: the second receives `stale_write`.
- **AC-WAT1** Posting a known `stableKey` merges new pages as duplicates and returns the existing change. **AC-WAT2** An agent submitting an unknown key receives 422 `unknown_key` with the valid keys.
- **AC-SRC1** "FFFS 2017:2" is won by keyword and "nudging in onboarding" by concept, in one query. **AC-SRC2** Every statement in an answer carries a citation, and a question with no support returns "no answer".
- **AC-AUD1** Every mutating request leaves an audit row in the same transaction, and the table rejects update and delete.
- **AC-NFR3** The pill gallery matches the design card in both themes, and every text pair passes WCAG AA.

## 5. Golden-path journeys (`@smoke`)

| ID | Path |
|---|---|
| J-1 | Invitation, emailed code, passkey enrolment, sign-out, passkey sign-in, a code request that now sends nothing |
| J-2 | Today, open the lead change, confirm the So what, triage with urgency and owner |
| J-3 | Owner assesses, adds actions, completes them, attaches evidence, requests sign-off, is refused self sign-off, a second person signs off with step-up, the case file opens |
| J-4 | Agent key registers a change and a proposal, the library editor approves in the console, the obligation shows version 2 with a diff and the tenant sees "what changed" |
| J-5 | Admin adds a flag with a usage note, it appears in the picker, the filter and the agent vocabulary read, renders as a brand pill, and is later renamed and merged without losing history |
| J-6 | Footprint change with preview and second-person approval hides advice-only records |
| J-7 | Search by identifier and by concept, then Ask with citations and an "as of" date |
| J-8 | Tenant B cannot see tenant A's case, evidence, comments or configuration |

## 6. Permissions and system roles

Permissions are constants in code. System roles are seeded rows a tenant can
copy and adapt. `x` means granted.

| Permission | Admin | Compliance officer | Owner | Approver | Contributor | Reader | Auditor |
|---|---|---|---|---|---|---|---|
| `library.read`, `watch.read`, `roadmap.read`, `search.use`, `comments.write`, `problems.report` | x | x | x | x | x | x | x |
| `register.read`, `cases.read`, `reports.read`, `audit.read` | x | x | x | x | x | x | x |
| `footprint.request` | x | x | | | | | |
| `footprint.approve` | x | x | | x | | | |
| `cases.triage` | | x | | | | | |
| `cases.work` (so what, assessment, actions, evidence, request sign-off) | | x | x | | | | |
| `cases.contribute` (save assessment input, update actions, add evidence) | | x | x | | x | | |
| `cases.signoff` | | | | x | | | |
| `register.edit`, `gaps.edit` | | x | x | | | | |
| `applicability.request` | | x | x | | | | |
| `applicability.approve`, `risk.accept.approve` | | x | | x | | | |
| `proposals.create` | | x | | | | | |
| `exports.create`, `ai_log.read` | x | x | | x | | | x |
| `members.manage`, `roles.manage`, `security.manage` | x | | | | | | |
| `vocab.manage`, `workflow.manage` | x | x | | | | | |
| `agents.manage`, `integrations.manage` | x | | | | | | |

Platform roles: `library_editor` (`proposals.review`, `library_vocab.manage`,
`sources.manage`, `eval.manage`) and `platform_admin` (`tenants.manage`,
`agent_definitions.manage`, `support_access.grant`, `system.health`). Four
eyes applies to every approve permission: never the requester.

## 7. Release plan

| Release | Outcome | Build plan chunks |
|---|---|---|
| R1 | Sign in with a passkey, set the footprint, browse the inventory with versions and diffs, follow the watch feed fed by agents, search and ask, the timeline home, briefing and roadmap, vocabularies managed without a deploy, audit from day one | 0 to 7 |
| R2 | The system of record: applicability, compliance status per entity, gaps, the full case workflow, collaboration, tenant-controlled agents | 8 to 11 |
| R3 | What large buyers require: reports and exports, import, integrations, SSO, retention, tenant exit, the assurance pack, billing | 12 to 14 |

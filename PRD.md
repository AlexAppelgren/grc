# Compliance Watch: product requirements

| Version | Date | Change | Decided by |
|---|---|---|---|
| 0.1 | 2026-09-19 | First PRD. Consolidates the journey and capability list from the Compliance Watch chat, the data model and API work from the Compliance Data chat, the playbook review, and the decisions on passkeys, Nordic scope, admin-owned vocabularies, the pill system and Green tokens | Alex |
| 0.2 | 2026-09-19 | Sector scope: regulated financial services only, not a general-purpose GRC product. Standards and certifications within that scope (for example ISO/IEC 27001 followed by some of a tenant's legal entities) are inventoried, watched and worked like regulation; their requirements are being analysed and land in a following version | Alex |
| 0.3 | 2026-09-19 | Three things Alex asked for in chat, analysed and merged. **My work and participants:** one page of everything a person or their teams are responsible for or take part in, with next reviews and the changes on those items, the same view for a department's head, participants (people or teams) on register entries and cases that grant nothing, departments as org units with a head, and notes as shared comments. **Markets:** each covered country is operating, watching or not followed; operating markets are the regulatory scope's jurisdictions; watching hides nothing and steers tenant agents; EU rules reach every member country and Norway, as data. **Standards within the sector scope:** an edition is an instrument holding public facts and one conformance duty, a tenant opts in through its regulatory scope, a legal entity follows a standard through approved applicability and records its certificate, and the units it lists in its own words per entity form the Statement of Applicability. The sector scope paragraph is sharpened and the regime list becomes the enforced boundary. The wording is Alex's decision; the design defaults under it are `docs/DECISIONS.md` rows D-18 to D-47, each reversible | Alex |

| 0.4 | 2026-09-20 | The fourteen owner decisions Alex answered in chat on 2026-09-19 (`docs/plans/briefs/OWNER_RECOMMENDATIONS.md`). **Support access:** platform staff enter a bank read-only, for a stated purpose and a time limit a tenant admin approves with a passkey, and every read is logged in the bank. **Problem reports:** a report stays inside the bank that filed it; a library error is found instead by the watch agents, which re-check the records of the sources they check on every run and correct them through a proposal. **Retention:** a record is deleted ten years after its last use, through one database-guarded path. **Tenant exit:** two different people request and approve it, the tenant goes read-only while a final export is taken, and deletion removes every tenant row, the audit trail included, leaving a tombstone report. **Private records:** a bank's own instruments, obligations and sources are approved by a second person in the same bank under a new permission and never reach the platform, a model or the search index. **SSO:** the bank's identity provider proves who a person is, and the passkey stays the only way in. **Agents:** bleqq's general financial-regulation watch is part of the base package and no bank changes it; the tenant controls are for the agents a bank adds for itself **No editorial function:** bleqq staffs none, so a proposal is still the only door into the shared library and four eyes still refuses the same principal twice, but the second principal may be an independent agent — a different agent definition and API key from the proposer — reading the same queue with a review scope. A person approving still steps up with a passkey; an agent's approval, correction or rejection lands in the same audit trail with the agent named, and the record it applies carries machine-confirmed provenance instead of a person's verification. The console queue is still built: it is where the platform watches what the agents did and intervenes, and where a human approver is switched on later with no rework. A bank answers for its own interpretation of every library fact; the design defaults under that decision are `docs/DECISIONS.md` row D-62 and ADR 0054, reversible by staffing the `library_editor` role | Alex |

| 0.5 | 2026-09-20 | **Agent access**, the agents a bank runs itself. A bank's own agents (a coding agent building a service, a product agent shaping an account type, a procurement agent reading a contract, an internal assistant) need to know which regulation applies to what they are building. The bank registers each one, narrows it to the departments and products it serves, and gives it a credential: a service key, or a personal access token a member mints from a passkey session that acts as that person and can never step up. The agent reads through an MCP server over the same API, under the same gates, and reads only: the library records in its scope, and, once two people holding `security.manage` have switched tenant reach on for the bank, the register decisions on them. Its scope can only narrow the bank's own regulatory scope, never widen it, and it is never allowed to narrow silently: every answer states the scope it was answered in and names what it could not see. This amends D-07, because a bank pulling its own register into its own agent is tenant-zone text reaching a model. The design defaults under it are `docs/DECISIONS.md` rows D-63 to D-68 and ADRs 0055 to 0057, each reversible; the detail is `docs/plans/briefs/AGENT_ACCESS.md` | Alex |

Requirement IDs never appear on screen. Priority is MoSCoW (M, S, C).

**Glossary.** *Footprint* and *regulatory scope* are the same thing. On screen
the section is called **Regulatory scope** (sv *Regulatorisk omfattning*); in the
code, the API paths, the permission keys (`footprint.request`, `footprint.approve`)
and the route `/admin/footprint` the word stays *footprint*, because renaming the
identifiers would touch contracts, migrations, audit history and tests without
helping anyone reading the page. *Markets we operate in* are its jurisdiction terms.

*Agent access* is an agent the **bank** runs on its own infrastructure, registered so
it may read Compliance Watch through MCP or the API. It is not one of *Agents*, which
bleqq runs on its own schedules and which write; an agent access entry only reads. On
screen it is the second tab of **Agents**; in code, the API paths and the permission key
the word is `agent_access`.

Release: R1 makes it useful alone, R2 makes it a system of record, R3 is what
large buyers require. Every requirement starts at status `pending` in its
app's `app.md`.

## 1. Product

Compliance Watch keeps one obligations inventory current and carries every
regulatory change from first sighting to signed-off evidence. Research agents
find and propose, and every decision is logged. In the shared library the
proposing and the approving principal are both agents, each independent of the
other; in a bank's own zone people decide, and the bank answers for its own
interpretation of every library fact. It is built for enterprise banks in the
Nordics: Swedish, Danish, Norwegian, Finnish and EU sources, five content
languages, bank-grade access control, and an assurance pack a vendor review
can use.

**Wedge.** Inventory plus watch, done deeply for Nordic sources, with
paragraph-level citations and a plain verdict on every item.

**Sector scope.** Compliance Watch covers regulated financial services only: banking,
payments, investment services, insurance and pension provision, and asset and wealth
management. It also covers the AML, data protection and ICT-risk regimes that apply to
them, and the tax and AI rules as they apply to financial firms and their products. It is
not a general-purpose or multi-industry GRC product. It is not built for, and has no path
to, other regulated sectors such as healthcare, life sciences, construction, environmental
compliance or workplace safety. The regime list is the boundary: every instrument and
every change carries a regime from it. Nothing outside this scope enters the library, even
when one of a tenant's entities holds it (for example ISO 9001, ISO 14001 or ISO 45001).

**Standards and certifications.** Within that scope, a firm may follow a standard by
choice, by contract or because a supervisor expects it, and such a standard is handled
like regulation. Examples are information-security, business-continuity, privacy and
payment-card standards, such as ISO/IEC 27001.

- **In the library.** Each edition is an instrument in the shared library. It holds the
  standard's public facts and one duty to conform, written in our own words. The library
  never holds a standard's licensed text, its clause or control titles, or a paraphrase
  of them.
- **Opting in.** A tenant opts in through its regulatory scope. Only then do the
  standard's records match.
- **Per legal entity.** An entity follows the standard when its applicability is
  approved, and it records any certificate with its issuer, scope, validity and next
  audit.
- **Statement of Applicability.** For each entity that follows a standard, the tenant
  lists the clauses and controls it works with, by reference and in its own words. Each
  has applicability with a reason, a status and gaps. Together they are the Statement of
  Applicability.
- **Watch.** Revisions and transition deadlines are watched like any change.

**Out of scope by decision.** Control testing, policy management, incidents,
and risk registers (including a standard's own risk assessment and treatment
plan), and certificates or assurance reports received from suppliers.
Obligations carry linked internal items and the API lets an existing GRC
system integrate.

**Users.** Compliance officer (triages, curates the register), obligation
owner (assesses, plans, evidences), approver (second pair of eyes),
contributor (legal, product, tech input), reader, auditor (read-only with
exports), tenant admin (people, configuration, security), and on the platform
side the confirming agents that work the review queue, the platform admin, and
the `library_editor` role, which bleqq staffs with nobody and keeps for the
proposals it chooses to decide itself.

A bank's own agents read too, under **agent access**: they are not users, hold no role
and never write, and what they may read is a credential and a scope, not a seat.

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
| ID-02 | First sign-in uses a one-time emailed code and leads straight into passkey enrolment. The enrolment session can do nothing else. For an address on a verified domain of a tenant that has switched SSO on, the bank's identity provider proves the person instead of the code | M | R1 |
| ID-03 | After the first passkey, sign-in is by passkey only and the emailed code stops working for that account. No password exists anywhere | M | R1 |
| ID-04 | Users manage their passkeys (add, rename, remove, never the last one) and see and revoke their sessions | M | R1 |
| ID-05 | Recovery: a tenant admin re-issues enrolment behind step-up, audited, with notices. The last admin recovers through platform support with an out-of-band check | M | R1 |
| ID-06 | Step-up by fresh passkey assertion on the sensitive actions listed in playbook 4.2, recorded on the audit event | M | R1 |
| ID-07 | Tenant credential policy: allow synced passkeys or require attested device-bound authenticators | S | R2 |
| ID-08 | Tenant session policy: idle and absolute limits within platform maximums | S | R2 |
| ID-09 | Permissions are code, roles are rows: seeded system roles plus tenant-defined roles. A tenant always keeps one admin | M | R1 |
| ID-10 | Scoped API keys for agents and integrations, shown once, stored hashed, revocable, with last use | M | R1 |
| ID-11 | Security log of sign-ins, failures, enrolments, recoveries and key use | M | R1 |
| ID-12 | SSO (OIDC, SAML), verified domains and SCIM as a tenant option. SSO proves who a person is and never opens a session on its own: there is no sign-in button that starts at the identity provider, and with enforcement on the provider is asked after the passkey, at every sign-in. SSO never recovers a lost passkey and never replaces step-up | C | R3 |
| ID-13 | Optional IP allow-list per tenant | C | R3 |

### TEN: tenant and organisation

| ID | Requirement | P | R |
|---|---|---|---|
| TEN-01 | Tenant profile, timezone, default languages, onboarding checklist | M | R1 |
| TEN-02 | Legal entities with licences and certificates (issuer, reference, scope, validity, next audit, owner), departments (business areas, units and functions) with a head and the teams in them, and products described the way obligations are scoped | M | R2 |
| TEN-03 | Teams as owners and participants, so ownership survives a person leaving | M | R2 |
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
| FP-01 | Footprint across all taxonomy dimensions. A record matches when every dimension it carries has a term in the footprint. An empty dimension does not restrict, except the standards dimension: a record carrying a standard matches only when the footprint names that standard. An obligation also needs its instrument's regime in the footprint | M | R1 |
| FP-02 | A footprint change previews what it hides and reveals, needs a second person and step-up, and writes one audit event per term | M | R1 |
| FP-03 | Feed, inventory, roadmap, briefing and reports respect the footprint, with a visible way to look outside it | M | R1 |
| FP-04 | Markets: each covered country is operating, watching or not followed. Operating markets are the footprint's jurisdictions and change only as FP-02 does. A record's jurisdiction comes from its instrument or its authority, and EU rules reach every member country and Norway (EEA Agreement), recorded as data. A record without a jurisdiction is not restricted by it. Watching is a direct, audited setting that hides nothing, never sets urgency or opens triage, and adds a view on the inventory and the watch feed showing what the watched markets add. Library research sweeps every covered market, whatever a tenant chooses | M | R1 |

### INV: inventory (library)

| ID | Requirement | P | R |
|---|---|---|---|
| INV-01 | Instruments with level (a standard's level says so), binding force, official reference, ELI where available, jurisdiction (International for standards bodies), authority, a regime, in-force dates and lineage | M | R1 |
| INV-02 | Provision tree with verbatim text versions, in-force dates and transitional notes. Never for a standard, whose text is licensed | S | R1 |
| INV-03 | Obligations: plain-language duty, duty type, scope facets, trigger, retention, sanction exposure, provenance, related obligations | M | R1 |
| INV-04 | Versioned summaries with effective dates, "as of" reads and a sentence-level diff | M | R1 |
| INV-05 | Text in the original language plus translations, machine translations labelled. A record whose proposal an agent confirmed is labelled machine-confirmed and names the proposing and the confirming agent; it never reads as verified by a person until a person verifies it | M | R1 |
| INV-06 | Source link and last-verified date on every record, and a "this looks wrong" report | M | R1 |
| INV-07 | Tenant-private instruments and obligations from the tenant's own sources, proposed and approved inside that bank by a second person. Platform staff never see or approve them, and their text never reaches a model, the search index or another tenant | C | R3 |
| INV-08 | Standards within the sector scope as instruments, one per edition. Each holds publisher, reference, dates, lifecycle, national adoptions as a note, a catalogue link, and exactly one conformance duty in our own words, which carries the standard's term. Only a standard's own records carry a standard term. There is no standard text, clause or control title, or paraphrase in the library, the search index, Ask or agent output | M | R1 |

### PRO: proposals

| ID | Requirement | P | R |
|---|---|---|---|
| PRO-01 | The review queue is the only way into the library, for agents and people, with a source per changed field. One queue serves both kinds of approver: a confirming agent reads the pending proposals through the same route as a person, with its key's review scope | M | R1 |
| PRO-02 | Approval applies the payload, writes the version, the audit row and the re-index in one transaction. The reviewer can correct scope and wording first. Never the same principal: the approver is a second person, who steps up with a passkey, or an independent agent whose definition and key differ from the proposer's. The audit row names whoever decided | M | R1 |
| PRO-03 | The queue lives in the platform console, where the platform watches what the agents decided and can take a proposal over. Tenants see library updates and can report a problem, and that report stays inside the bank that filed it. A bank's private records are proposed and approved inside the bank and never reach the console | M | R1 |
| PRO-04 | Batch proposals (re-tag, backfill) with a preview, approved whole or row by row | S | R2 |

### WAT: watch

| ID | Requirement | P | R |
|---|---|---|---|
| WAT-01 | Source registry and coverage log: what was checked, when, with what result. Every run also re-checks the library records that came from the sources it checked, and proposes a correction where a record no longer matches its source | M | R1 |
| WAT-02 | One record per reform with a timeline from consultation to in force, partial dates, and duplicates merged | M | R1 |
| WAT-03 | Change types, flags and scope from vocabularies, with at least one regime on every change and a standard term only on a change from a standards body. Agent classifications shown as suggestions until confirmed | M | R1 |
| WAT-04 | Links to affected obligations with confidence, confirmed by a person | M | R1 |
| WAT-05 | A drafted "So what?" per change, labelled AI-drafted until a person confirms or rewrites it per tenant | M | R1 |
| WAT-06 | Tenants can request a source. Private sources are visible to that tenant only, are public pages checked when requested and again at each run, and run only on an approved EU model endpoint | S | R3 |
| WAT-07 | Standards are watched from public metadata: one change per edition or amendment, with a timeline from draft to publication and a key date for the end of the transition. A publisher's page keeps no snapshot, and automated checks run only on publishers whose terms allow them | S | R1 |

### REG: register

| ID | Requirement | P | R |
|---|---|---|---|
| REG-01 | Applicability per obligation, per legal entity where it spans several, and per unit of a standard, with a reason. It changes only through a request that a second person approves. Many pending requests can be decided in one call, with four eyes on every row | M | R2 |
| REG-02 | Compliance status, status note, risk, owners, process, system, evidence location, next review, per legal entity where the obligation spans several | M | R2 |
| REG-03 | Gaps with owner, severity, target date, remediation, and risk acceptance behind four eyes | M | R2 |
| REG-04 | Assessment history and "how we read this rule" per obligation | S | R2 |
| REG-05 | Linked internal items (policy, procedure, control, process, system) with external references | M | R2 |
| REG-06 | Yearly attestation by the owner, and waivers | C | R3 |
| REG-07 | Recurring duties on the roadmap from recurrence rules | S | R2 |
| REG-08 | Statement of Applicability. For each legal entity that follows a standard, the tenant lists the clauses and controls it works with as units, by reference and in its own words, entered one by one or pasted with a dry run. Each unit has applicability with a reason, a status and gaps. A unit's reference and words are fixed once it has history. The register filtered by standard and entity is the Statement of Applicability. Nothing written under a standard is indexed, sent to a model or shown to another tenant | M | R2 |

### CAS: case workflow

| ID | Requirement | P | R |
|---|---|---|---|
| CAS-01 | One case per tenant per change, created in "needs triage" with its footprint match | M | R1 |
| CAS-02 | Triage needs urgency and owner. Dismissal needs a reason and can be restored | M | R2 |
| CAS-03 | Impact assessment: applies, why, what must change, internal deadline, effort, and contributor teams, recorded as the case's team participants | M | R2 |
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
| HOM-03 | Roadmap page by quarter, regulatory dates and our own deadlines, a card expanding in place. From R2, our own deadlines include a certificate's expiry and next audit, which never reach the calendar feed | M | R1 |
| HOM-04 | Upcoming changes as public facts for agents and newsletters, and a revocable calendar feed | S | R1 |
| HOM-05 | My work: everything a person or their teams are responsible for or take part in, grouped as overdue, due soon, changes on those items, and the rest. Next reviews are included, also for compliant obligations, per legal entity and for internal items, and each item says why it is there. A department's head sees the same view for the department, naming who is responsible. Every item and count respects the reader's permissions, and the footprint never hides a person's own items. Decisions stay on Today | M | R2 |

### COL: collaboration

| ID | Requirement | P | R |
|---|---|---|---|
| COL-01 | Comments and mentions on any record, and a person's own comments and mentions listed on My work, limited to records they can read | S | R2 |
| COL-02 | Notifications, reminders before due dates including next reviews, notice to the people responsible and taking part when a change is linked to their obligation or a new version applies, escalation to the head of the owner's department after a threshold, a weekly digest in the user's language. A notification reaches only active members who can read its record, once per event | M | R2 |
| COL-03 | Follow a record | C | R3 |
| COL-04 | Participants: people or teams added to a register entry or a case by someone who can edit it. Participation lists and notifies, grants no access, and a participant can leave. Unlike following (COL-03), which a person does alone on library records, participation is on the tenant's own records | M | R2 |

### AGT: agents

| ID | Requirement | P | R |
|---|---|---|---|
| AGT-01 | Agent API: open a run, log source checks, find similar, register changes idempotently, submit proposals, close the run | M | R1 |
| AGT-02 | Agents read vocabularies at run start and may use existing keys only | M | R1 |
| AGT-03 | Versioned agent definitions owned by the platform. bleqq's agents, the general financial-regulation watch that feeds the shared library, are part of the base package: no tenant switches them off, pauses them, changes their cadence, scope or budget, or edits their definitions | M | R2 |
| AGT-04 | Tenant controls over the agents a bank adds for itself: on and off, cadence, scope (by default the operating markets first, then the watched ones), run now, pause, interrupt, history with findings and cost, monthly budget cap, AI off switch. A tenant's own agent writes only in that tenant's zone, never the shared library | M | R2 |
| AGT-05 | Research requests: check a source now, research a topic, re-tag existing records. A bank asks its own agents; re-tagging library records is asked in the platform console | S | R2 |
| AGT-06 | Runner adapter with a mock, the app as scheduler of record | M | R2 |
| AGT-07 | Fetched content screened for embedded instructions | M | R1 |
| AGT-08 | Agents stay inside the sector scope. An out-of-scope document is logged as a source check and counted, and nothing is registered or proposed. A standard's text is never fetched, quoted, summarised, translated or restated from memory. A blocked page is a failed check and is never worked around. A law that cites a standard never carries the standard's term | M | R1 |

### ACC: agent access (the agents a bank runs itself)

| ID | Requirement | P | R |
|---|---|---|---|
| ACC-01 | A tenant registers each agent it runs itself as an agent access entry: name, purpose, the team that owns it, and the departments and products it serves. Registering, changing and revoking need `agent_access.manage` and a step-up, and revoking stops every credential under the entry on the next request | M | R2 |
| ACC-02 | The entry's scope is the taxonomy terms of the departments and products it names, intersected with the tenant's footprint. It can only narrow: an entry never sees what the bank's own regulatory scope does not. Naming no department and no product narrows nothing. An empty dimension does not restrict, as FP-01 says, and a record outside scope answers 404, never a filtered result | M | R2 |
| ACC-03 | Two credential kinds, one table and one revocation path. A service key is bound to an entry and acts as it. A personal access token is minted by a member holding `tokens.create`, from an authenticated session behind a step-up, and acts as that person, never exceeding their permissions. Both are shown once, hashed, expiring, revocable, carry a last use and appear in the security log. A token cannot open a session and cannot step up, so every step-up action refuses it, and it dies when the person is deactivated or loses the permission behind it | M | R2 |
| ACC-04 | An entry reads the library records in its scope with their citations, "as of" date and provenance, and the upcoming dated changes touching them. With tenant reach on it also reads the bank's register decisions on those obligations: applicability and its reason per legal entity, compliance status and status note, how we read this rule, owner, process, system, next review and linked internal items. Never gaps, cases, comments, evidence, the audit log or a private record | M | R2 |
| ACC-05 | An MCP server over the same API: the same authentication, the same scope gates, the same logic and the same pagination, with no read path of its own. Its tool list follows the credential. Every agent access credential is read-only through R2, and a mutating route refuses it | M | R2 |
| ACC-06 | One call takes a description of what is being built, bought or reviewed and returns a short summary drafted by the model, labelled and logged like any AI output, above the deterministic full list of the register entries and obligations in scope. The list is never shortened by the model, and it is still returned when the model fails or AI is switched off | M | R2 |
| ACC-07 | A narrowed entry never narrows silently. Every answer states the scope it was answered in and its "as of" date, and an answer to a description that appears to touch the bank's footprint outside the entry's scope names the dimensions and terms it could not see, from their labels and never from their records | M | R2 |
| ACC-08 | Tenant reach is off until two different people holding `security.manage` switch it on for the bank, each with a passkey; a tenant admin then enables it per entry. With the tenant switch off every entry is library-only whatever its own setting says. Every call is logged with the credential, the entry, the person where the credential is personal, the tool, the filters, the record count, the scope applied and the timing, and never the content or the question | M | R2 |
| ACC-09 | Limits: pagination as everywhere, a rate limit per credential, and model calls counted against the tenant's monthly budget cap and stopped by its AI off switch | M | R2 |
| ACC-10 | An entry records that a named application or system touches a register entry and how, as a linked internal item under REG-05, so the bank holds a map of which of its applications each obligation reaches | C | R3 |

### REP, INT: reporting and integration

| ID | Requirement | P | R |
|---|---|---|---|
| REP-01 | Dashboard: open changes by urgency, overdue actions, gaps, unconfirmed AI drafts, time to triage, regime by account heatmap, load per owner | S | R3 |
| REP-02 | Committee pack and exports of inventory (including a dated Statement of Applicability per standard and entity), changes, cases and the audit log | S | R3 |
| REP-03 | Spreadsheet register import: dry run, near-match mapping asked once per value, then commit | S | R3 |
| REP-04 | Full tenant export in open formats and verified deletion. Exit is requested and approved by two different people holding `security.manage`, each with a passkey; the tenant is then read-only while the final export is taken, and the platform operator deletes every tenant row, the audit trail included, leaving only a tombstone report | M | R3 |
| INT-01 | Signed webhooks with a delivery log, from a transactional outbox | S | R3 |
| INT-02 | Ticket export for actions | C | R3 |
| INT-03 | Audit log stream to the customer's SIEM | S | R3 |

### AUD: audit and AI governance

| ID | Requirement | P | R |
|---|---|---|---|
| AUD-01 | Append-only audit log written with every change: actor (user, agent, system), action, subject with its title at the time, summary, before and after | M | R1 |
| AUD-02 | AI output log with model, version, purpose, citations, review state and feedback. A confirming agent's approval, correction or rejection is logged there and in the audit trail, naming the agent definition, its version and the key it used | M | R1 |
| AUD-03 | A problem report stays inside the bank that filed it and nobody outside reads it. The loop to the library is closed by the watch agents' re-check, which proposes the correction | S | R1 |
| AUD-04 | Retention of closed cases, removed evidence and the audit trail: a record is deleted ten years after its last use. The purge never updates an append-only row, deletes one only past that age, and runs through one database-guarded path | S | R3 |

### ADM: admin surfaces

| ID | Requirement | P | R |
|---|---|---|---|
| ADM-01 | Tenant admin: organisation with departments and teams, members and invitations with team membership, passkey re-enrolment, sessions, roles, footprint with markets, vocabularies, workflow policy, agents, integrations, security policy, data, audit log | M | R1 to R3, following the features |
| ADM-02 | Platform console: library vocabularies, sources, languages and jurisdictions, agent definitions, proposal queue, evaluation sets, tenants and plans, support access, system health (coverage, runs, outbox lag, failed jobs with retry, and each bank's usage figures through one audited read of numbers only) | M | R1 to R3 |
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
- **AC-PRO1** No API key scope and no tenant role can change a library record except through an approved proposal. **AC-PRO2** Approving your own proposal answers 409 `four_eyes_violation`, for a person and for an agent alike: the same user, the same key or the same agent definition on both sides is refused, and the check constraint refuses the row on its own.
- **AC-VOC1** An admin adds a change type, a tag and a sub-status with no deploy: each appears in pickers, filters, agent vocabulary reads and pills, and `openapi.json` is unchanged. **AC-VOC2** Retiring a used value keeps history readable and removes it from pickers. **AC-VOC3** Creating "custody " when "Custody" exists is refused with the near match offered.
- **AC-FP1** Switching off "Advice" previews the obligations and open cases it hides, waits for a second person, then hides advice-only obligations and changes everywhere.
- **AC-FP2: markets.** Turning Denmark on in the footprint's jurisdictions previews the change and waits for a second person with step-up, and EU rules keep showing with Denmark. Operating in Norway alone shows EU rules too. Watching Norway is one audited write that changes no default view, and no market key appears in a URL.
- **AC-FP3: standards are opt-in.** A tenant whose regulatory scope names no standard sees no standard's obligations or changes. Its case for a standard's change is created with `footprintMatch` false and appears in neither its feed nor its roadmap. After an approved change adding ISO/IEC 27001, it sees them. A law's obligation or change never carries a standard term.
- **AC-INV1** "As of" a date returns the version in force on it, and the diff shows what changed between two versions.
- **AC-INV2** A provision or provision-version proposal under a standard is refused at creation, through `POST /proposals` and the agent API, with 422 `licensed_text`. A provision row under a standard is refused by the database. The Ask evaluation row about a standard's control expects "no answer", and it gates the release.
- **AC-REG1** An approver with a fresh step-up decides 93 pending unit requests for one entity in one call, and 93 audit rows are written. A call that includes a request the caller filed answers 409 `four_eyes_violation` and decides nothing. **AC-REG2** Nothing a tenant writes under a standard (units, notes, gaps, assessments, interpretations, links) appears in a search chunk, an embedding input or an AI-generation input. Tenant B receives 404 for it.
- **AC-TEN1** A certificate's expiry and next audit appear on the roadmap as "Our deadline" with its owner. They disappear once it is withdrawn, and never appear in the calendar feed.
- **AC-HOM1: My work.** An owner's compliant obligation with a review in 20 days is under "Due soon". An item they own outside the footprint is listed. A role without `register.read` gets no obligation rows or counts and a permission-limited notice, never a page-level 403.
- **AC-COL1: participants.** A participant still receives 403 on writes their role lacks. Tenant B adding a participant to tenant A's private record, or removing A's participant, gets 404; on a shared record, B's add lands on B's own entry. A user of another tenant gets 422 `unknown_member`, and a member who cannot read the record gets 422 `participant_cannot_read`.
- **AC-CAS1** Sign-off is refused with `open_actions` or `evidence_missing`, and with `four_eyes_violation` for the requester. **AC-CAS2** Two people saving the same assessment: the second receives `stale_write`.
- **AC-WAT1** Posting a known `stableKey` merges new pages as duplicates and returns the existing change. **AC-WAT2** An agent submitting an unknown key receives 422 `unknown_key` with the valid keys.
- **AC-SRC1** "FFFS 2017:2" is won by keyword and "nudging in onboarding" by concept, in one query. **AC-SRC2** Every statement in an answer carries a citation, and a question with no support returns "no answer".
- **AC-AUD1** Every mutating request leaves an audit row in the same transaction, and the table rejects update and delete.
- **AC-AGT1** A change without a regime answers 422 `regime_required`. The evaluation set scores in-scope and standard-term accuracy on out-of-sector texts and on a law that cites a standard, and the release gate fails below tolerance.
- **AC-NFR3** The pill gallery matches the design card in both themes, and every text pair passes WCAG AA.
- **AC-ACC1** An agent access entry narrowed to the Trading department reads trading and untagged obligations, answers 404 for a card obligation's stable key, and names "Product type" and "Licensed activity" among what it could not see when asked about a card feature.
- **AC-ACC2** With the tenant reach switch off, every register route answers 403 `tenant_reach_off` to every agent access credential, whatever the entry's own setting says.
- **AC-ACC3** A personal access token answers 403 `step_up_required` on every step-up action, with no path to an assertion, and stops working on the next request once the person is deactivated or loses the permission behind it.
- **AC-ACC4** Every mutating route answers 403 `read_only_credential` to every agent access credential in R2, and no such credential holds a scope that writes.

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
| J-8 | Tenant B cannot see tenant A's case, evidence, comments, participants, watched markets or configuration |
| J-9 | Monday morning: the owner opens My work and sees an overdue review and a change linked to an obligation they are responsible for; they add a contributor as participant on that obligation; the contributor sees it on their own My work; the department head's view shows it with the owner named; the contributor leaves, and both events are in the audit log |
| J-10 | The officer adds ISO/IEC 27001 to the regulatory scope and an approver approves it with step-up. The officer records the certificate on an entity and requests "applies" for that entity with the reason "Certified", and the approver approves it. The officer pastes three units with applicability, and the approver decides them in one call. The register filtered by standard and entity shows the decisions, and the next audit is on the roadmap |
| J-11 | A tenant admin registers an agent access entry for the Trading team's coding agent, narrowed to that department's products, and issues it a key with a step-up. Two people holding `security.manage` switch tenant reach on, and the admin enables it on the entry. The agent asks what applies to a new order-routing service and receives the bank's approved applicability and reading with citations, the full list beneath a labelled summary, and a line naming card issuing as outside its scope. A card obligation's stable key answers 404, a write answers 403, and revoking the entry stops the next call |

## 6. Permissions and system roles

Permissions are constants in code. System roles are seeded rows a tenant can
copy and adapt. `x` means granted.

| Permission | Admin | Compliance officer | Owner | Approver | Contributor | Reader | Auditor |
|---|---|---|---|---|---|---|---|
| `library.read`, `watch.read`, `roadmap.read`, `search.use`, `comments.write`, `problems.report` | x | x | x | x | x | x | x |
| `register.read`, `cases.read`, `reports.read`, `audit.read` | x | x | x | x | x | x | x |
| `footprint.request` (ask for a footprint change, including the markets we operate in; set the markets we watch) | x | x | | | | | |
| `footprint.approve` | x | x | | x | | | |
| `cases.triage` | | x | | | | | |
| `cases.work` (so what, assessment, actions, evidence, request sign-off) | | x | x | | | | |
| `cases.contribute` (save assessment input, update actions, add evidence, add or remove case participants) | | x | x | | x | | |
| `cases.signoff` | | | | x | | | |
| `register.edit`, `gaps.edit` (`register.edit` includes adding or removing participants on a register entry, and adding, pasting, editing or removing a standard's units) | | x | x | | | | |
| `applicability.request` | | x | x | | | | |
| `applicability.approve`, `risk.accept.approve` | | x | | x | | | |
| `private_records.approve` (approve a proposal for the bank's own instruments, obligations and sources; never a platform grant and never an API key scope) | | x | | x | | | |
| `proposals.create` | | x | | | | | |
| `exports.create`, `ai_log.read` | x | x | | x | | | x |
| `members.manage`, `roles.manage`, `security.manage` (`members.manage` includes team membership; `security.manage` includes approving, declining and revoking support access, and requesting or approving tenant exit, never both by the same person) | x | | | | | | |
| `vocab.manage`, `workflow.manage` (`vocab.manage` includes departments, their heads, teams, and the certificates on a legal entity) | x | x | | | | | |
| `agents.manage`, `integrations.manage` | x | | | | | | |
| `agent_access.manage` (register, change and revoke an agent access entry, issue and revoke its service keys, set its tenant reach) | x | | | | | | |
| `tokens.create` (mint a personal access token for yourself, which acts as you and can never exceed your own permissions) | x | x | x | | | | |

Platform roles: `library_editor` (`proposals.review`, `library_vocab.manage`,
`sources.manage`, `eval.manage`) and `platform_admin` (`tenants.manage`,
`agent_definitions.manage`, `support_access.grant` (request support access to a
bank and enter it read-only once a tenant admin approves), `system.health`). Four
eyes applies to every approve permission: never the requester. 0.3 adds no
permission constant and changes no grant; only the descriptions above grew. 0.4
adds one constant, `private_records.approve`, and widens the descriptions of
`security.manage` and `support_access.grant`.

0.5 adds two constants, `agent_access.manage` and `tokens.create`, and widens
`security.manage` to cover approving the tenant reach switch, never both sides by
the same person. It adds no platform permission and no platform scope. The key
scope `tenant:read`, declared since chunk 1 and gated on no route, becomes the
scope that reaches a tenant's register decisions and nothing else.

0.4 also staffs `library_editor` with nobody. The role and its permissions stay
exactly as they are — they are how a person takes a proposal over, and how a
human approver is switched on later without rework — but the routine second
pair of eyes on the library is an agent: a platform API key bound to an agent
definition holds the new scope `proposals:review`, which reaches the queue read
and the approve, correct and reject routes and no library row. The step-up is a
person's gate: a session approving still needs a fresh passkey assertion, and a
key cannot step up, so the four-eyes check constraint, not a passkey, is what
holds an agent approval apart from its proposal. No tenant role and no tenant
key gains either the role or the scope.

**Actions that need membership only:** viewing My work, your own or any
department's (each item still needs its read permission, so the department
view is a filter and not a grant), and leaving your own participation.

## 7. Release plan

| Release | Outcome | Build plan chunks |
|---|---|---|
| R1 | Sign in with a passkey, set the footprint and the markets, follow a standard through the regulatory scope and watch its revisions, browse the inventory with versions and diffs, follow the watch feed fed by agents, search and ask, the timeline home, briefing and roadmap, vocabularies managed without a deploy, audit from day one | 0 to 7 |
| R2 | The system of record: applicability, compliance status per entity, gaps, the full case workflow, legal entities that follow standards and hold certificates with a Statement of Applicability per entity, My work and participants, departments and teams, collaboration, tenant-controlled agents, and agent access so a bank's own agents read what applies to them | 8 to 11 |
| R3 | What large buyers require: reports and exports, import, integrations, SSO, retention, tenant exit, the assurance pack, billing | 12 to 14 |

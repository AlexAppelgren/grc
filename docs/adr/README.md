# Architecture decision records

Template: `docs/PLAYBOOK.md` Appendix C. Every entry in `docs/DECISIONS.md`
has an ADR with status `accepted by default` until the owner confirms it;
when the owner changes one, the ADR is superseded and the PRD version bumps
if behaviour changes. Numbering never reuses a number.

| ADR | Title | Source | Status |
|---|---|---|---|
| [0001](0001-multi-tenant-product.md) | Multi-tenant product with one shared library | D-01 | accepted by default |
| [0002](0002-webauthn-rp-id.md) | WebAuthn RP ID is the exact app host per environment | D-02 | accepted by default |
| [0003](0003-auth-library.md) | py_webauthn with our own thin endpoints | D-03 | accepted by default |
| [0004](0004-ui-foundation.md) | UI foundation: Tailwind, Radix primitives and our own components on Green tokens | D-04 | accepted by default (spike outcome pending) |
| [0005](0005-brand-layer.md) | Brand layer: Green tokens with our own brand pair | D-05 | accepted by default |
| [0006](0006-sessions.md) | Sessions: in-memory access token, rotating refresh cookie, a row per session | D-06 | accepted by default |
| [0007](0007-llm-provider-and-inference-region.md) | LLM provider adapter and the inference region | D-07 | accepted by default; amended by ADR 0057 |
| [0008](0008-agent-runtime.md) | Agent runtime behind an adapter, the app as scheduler of record | D-08 | accepted by default |
| [0009](0009-embedding-model-and-reranker.md) | Embedding model and reranker chosen against the evaluation set | D-09 | accepted by default |
| [0010](0010-search-scope.md) | Search indexes the library only in R1 | D-10 | accepted by default |
| [0011](0011-evidence-delivery.md) | Evidence and exports stream through permission-checked endpoints | D-11 | accepted by default |
| [0012](0012-translations-as-rows.md) | Translations are rows keyed by language | D-12 | accepted by default |
| [0013](0013-statuses-in-fixed-categories.md) | Tenant sub-statuses inside fixed categories, no workflow engine | D-13 | accepted by default |
| [0014](0014-library-curation.md) | Library curation by a platform role in the console | D-14 | accepted by default |
| [0015](0015-branching.md) | One branch during the build, staging and main before the first real tenant | D-15 | accepted by default |
| [0016](0016-hosting.md) | Railway EU West, container-only, nothing Railway-specific in code | D-16 | accepted by default |
| [0017](0017-django-version.md) | Django 5.2 LTS | D-17 | accepted by default |
| [0018](0018-reuse-playbook-structure.md) | Reuse the playbook's structure from the last repo | Appendix C | accepted by default |
| [0019](0019-framework-and-version-pins.md) | Framework choices and exact version pins | Playbook 2.1 | accepted by default |
| [0020](0020-design-direction.md) | Design direction | Playbook 7, `design/README.md` | accepted by default |
| [0021](0021-no-django-admin.md) | No Django admin | Playbook 4.3 | accepted by default |
| [0022](0022-database-roles-for-rls.md) | Two database roles so row-level security means something | Playbook 14 | accepted by default |
| [0023](0023-translations-as-rows.md) | Translations as rows: the full consequences of D-12 | D-12, playbook 17 | accepted by default |
| [0024](0024-tenant-zone-portability.md) | Tenant-zone portability | Playbook 12, 14, 18 | accepted by default |
| [0025](0025-newest-releases-and-medium-findings.md) | Newest releases of every package, and MEDIUM findings block | Alex, 2026-09-19 | accepted by default |
| [0026](0026-markets-footprint-and-watch-list.md) | Markets are the regulatory scope's jurisdictions plus a watch list | D-27 to D-33 | accepted by default |
| [0027](0027-participants-departments-and-my-work.md) | Participants, departments and one My work service | D-18 to D-21, D-23 to D-26 | accepted by default |
| [0028](0028-notes-are-shared-comments.md) | Notes are shared comments, and one recipient check serves every notification | D-22, D-34, D-60 | accepted |
| [0029](0029-standards-library-holds-public-facts-only.md) | The shared library holds a standard's public facts and one conformance duty | D-35 | accepted by default |
| [0030](0030-opt-in-dimension-for-standards.md) | A standard is opted into through an opt-in dimension of the regulatory scope | D-36 | accepted by default |
| [0031](0031-standard-instrument-level-kind.md) | An optional instrument level kind says an instrument is a standard | D-37 | accepted by default |
| [0032](0032-international-jurisdiction.md) | International is a jurisdiction kind of its own | D-38 | accepted by default |
| [0033](0033-regime-is-the-sector-boundary.md) | Every instrument and every change carries a regime, and the regime list is the boundary | D-39 | accepted by default |
| [0034](0034-sector-vocabulary-edges.md) | The sector scope's edges: tax, AI and the licensed-activity dimension | D-40 | accepted by default |
| [0035](0035-soa-units-in-the-tenant-zone.md) | The Statement of Applicability's units live in the tenant zone | D-41 | accepted by default; amended by D-75 |
| [0036](0036-entity-follows-a-standard-by-applicability.md) | A legal entity follows a standard through approved applicability | D-42 | accepted by default; amended by D-75 |
| [0037](0037-certificate-on-the-licence-row.md) | A certificate sits on the entity's licence row and reaches the roadmap, not the feed | D-43 | accepted by default |
| [0038](0038-bulk-decision-of-applicability-requests.md) | Many pending applicability requests are decided in one call, with four eyes on every row | D-44 | superseded by D-75 |
| [0039](0039-standards-watched-from-public-metadata.md) | Standards are watched from public metadata, and only from cleared publishers | D-45 | accepted by default |
| [0040](0040-soa-view-now-export-later.md) | The Statement of Applicability is a filtered register view in R2 and an export in R3 | D-46 | accepted by default |
| [0041](0041-seed-one-standard-first.md) | One standard is seeded first, and the rest arrive by proposal | D-47 | accepted by default |
| [0042](0042-support-access-granted-by-the-bank.md) | Support access is requested by the platform and granted by the bank, read-only | D-49 | accepted |
| [0043](0043-problem-reports-stay-in-the-bank.md) | A problem report stays inside the bank, and the watch agents find library errors | D-50 | accepted |
| [0044](0044-search-index-is-derived-data.md) | The search index is derived data with its own write fence | D-51 | accepted |
| [0045](0045-calendar-feed-token-in-the-query-string.md) | The calendar feed carries its secret in the query string and public dates only | D-52 | accepted |
| [0046](0046-retention-by-age-of-last-use.md) | A record is deleted ten years after its last use | D-53 | accepted |
| [0047](0047-eu-only-processors-refused-at-boot.md) | Production refuses any processor outside the EU at boot | D-54 | accepted |
| [0048](0048-credential-policy-takes-effect-at-a-notice-date.md) | A stricter passkey policy binds at registration now and at sign-in from a notice date | D-55 | accepted |
| [0049](0049-tenant-exit-needs-two-people-and-deletes-everything.md) | Tenant exit needs two people, and execution deletes every tenant row | D-56 | accepted |
| [0050](0050-private-records-approved-inside-the-bank.md) | A bank's private records are proposed and approved inside that bank | D-57 | accepted |
| [0051](0051-sso-proves-identity-the-passkey-signs-in.md) | SSO proves who a person is; the passkey stays the only way in | D-58 | accepted |
| [0052](0052-platform-counters-window.md) | The console reads each bank's figures through one window on tables of numbers | D-59 | accepted |
| [0053](0053-bleqq-agents-are-the-base-package.md) | bleqq's agents are the base package; a bank steers only its own | D-61 | accepted |
| [0054](0054-agent-approves-from-the-same-queue.md) | The second pair of eyes on a library proposal may be an independent agent | D-62 | accepted |
| [0055](0055-agent-access-reads-and-only-narrows.md) | An agent a bank runs reads through a registered entry that can only narrow | D-70, D-73, D-76 | accepted |
| [0056](0056-two-credential-kinds-one-table.md) | A service key and a personal access token, on one table, and a token can never step up | D-77 | accepted |
| [0057](0057-a-bank-pulls-its-own-register.md) | A bank may pull its own register into its own agent; we still send nothing | D-72, D-76 (amends D-07) | accepted |
| [0058](0058-library-writes-refused-by-the-database.md) | The database refuses a library write that never entered a door | D-83 | accepted by default |
| [0059](0059-agent-definitions-are-platform-configuration.md) | Agent definitions are platform configuration, not library rows | D-102 | accepted (owner decision) |

Still to write, when the playbook's Appendix C says so:
the switch from one branch to `staging` and `main` (supersedes 0015), the
chosen embedding model (fills 0009), the first real agent runner (fills 0008),
protection of production data from developer writes (playbook 11.3).

PRD 0.3 (2026-09-19) added 0026 to 0041 for decisions D-18 to D-47. D-18 to
D-21 and D-23 to D-26 share ADR 0027, and D-22 and D-34 share ADR 0028, because
each group is one design that is accepted or reversed whole. The thirteen
standards decisions have one ADR each, because each stands or falls on its own.

PRD 0.4 (2026-09-20) added 0042 to 0053 for the owner decisions D-48 to D-61,
answered by Alex in chat on 2026-09-19 and researched in
`docs/plans/briefs/OWNER_RECOMMENDATIONS.md`. Each stands on its own, so each
has its own ADR, except D-48 (the urgency rows are fixed, which INPUT_DELTAS §1
already records) and D-60 (no private notes, which ADR 0028 carries and which
moved that ADR from accepted by default to accepted). 0047 amends 0016 and
stages 0007's EU runner; 0048 is ADR 0003's third tranche; 0051 is the SSO
stance this index owed.

PRD 0.4 also added 0054 for D-62, Alex's own decision of 2026-09-20 (item 19)
that bleqq staffs no editorial function.

PRD 0.5 (decided 2026-09-20, landed 2026-09-23) added 0055 to 0057 for the agent
access decisions D-70 to D-73, D-76 and D-77, answered by Alex in chat and
consolidated in `docs/plans/briefs/AGENT_ACCESS.md`. D-71 has no ADR of its own: the
labelling and logging of a drafted summary is the existing AI-output invariant, not a
new design. 0057 amends 0007's D-07 and is the first ADR to state what that decision
always meant, that **we** send no tenant-zone text to a model; it leaves D-10 and
ADR 0050's private records untouched.

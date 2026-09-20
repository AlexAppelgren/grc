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
| [0007](0007-llm-provider-and-inference-region.md) | LLM provider adapter and the inference region | D-07 | accepted by default |
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
| [0028](0028-notes-are-shared-comments.md) | Notes are shared comments, and one recipient check serves every notification | D-22, D-34 | accepted by default |
| [0029](0029-standards-library-holds-public-facts-only.md) | The shared library holds a standard's public facts and one conformance duty | D-35 | accepted by default |
| [0030](0030-opt-in-dimension-for-standards.md) | A standard is opted into through an opt-in dimension of the regulatory scope | D-36 | accepted by default |
| [0031](0031-standard-instrument-level-kind.md) | An optional instrument level kind says an instrument is a standard | D-37 | accepted by default |
| [0032](0032-international-jurisdiction.md) | International is a jurisdiction kind of its own | D-38 | accepted by default |
| [0033](0033-regime-is-the-sector-boundary.md) | Every instrument and every change carries a regime, and the regime list is the boundary | D-39 | accepted by default |
| [0034](0034-sector-vocabulary-edges.md) | The sector scope's edges: tax, AI and the licensed-activity dimension | D-40 | accepted by default |
| [0035](0035-soa-units-in-the-tenant-zone.md) | The Statement of Applicability's units live in the tenant zone | D-41 | accepted by default |
| [0036](0036-entity-follows-a-standard-by-applicability.md) | A legal entity follows a standard through approved applicability | D-42 | accepted by default |
| [0037](0037-certificate-on-the-licence-row.md) | A certificate sits on the entity's licence row and reaches the roadmap, not the feed | D-43 | accepted by default |
| [0038](0038-bulk-decision-of-applicability-requests.md) | Many pending applicability requests are decided in one call, with four eyes on every row | D-44 | accepted by default |
| [0039](0039-standards-watched-from-public-metadata.md) | Standards are watched from public metadata, and only from cleared publishers | D-45 | accepted by default |
| [0040](0040-soa-view-now-export-later.md) | The Statement of Applicability is a filtered register view in R2 and an export in R3 | D-46 | accepted by default |
| [0041](0041-seed-one-standard-first.md) | One standard is seeded first, and the rest arrive by proposal | D-47 | accepted by default |
| [0042](0042-agent-approves-from-the-same-queue.md) | The second pair of eyes on a library proposal may be an independent agent | Alex, 2026-09-20 (D-48) | accepted |

Still to write, when the playbook's Appendix C says so: the SSO stance (R3),
the switch from one branch to `staging` and `main` (supersedes 0015), the
chosen embedding model (fills 0009), the first real agent runner (fills 0008),
protection of production data from developer writes (playbook 11.3).

PRD 0.4 (2026-09-20) added 0042 for D-48, Alex's decision that bleqq staffs no
editorial function.

PRD 0.3 (2026-09-19) added 0026 to 0041 for decisions D-18 to D-47. D-18 to
D-21 and D-23 to D-26 share ADR 0027, and D-22 and D-34 share ADR 0028, because
each group is one design that is accepted or reversed whole. The thirteen
standards decisions have one ADR each, because each stands or falls on its own.

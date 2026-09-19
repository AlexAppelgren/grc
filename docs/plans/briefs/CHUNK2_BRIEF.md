# Chunk 2 brief: vocabularies, taxonomy and footprint

Repo `C:\Users\Alex\projects\grc`, branch `main`. Chunk 1 backend is on disk (uncommitted):
read `backend/apps/identity/*`, `backend/apps/shared/{vocabulary,permissions,tenancy,audit,
migration_helpers}.py`, `backend/apps/library/{models,seeds}.py`, `backend/apps/shared/
{e2e_seed,e2e_logins}.py`, `backend/apps/shared/management/commands/seed_reference.py`
before anything else. Then `CLAUDE.md`, `docs/CONVENTIONS.md`, `docs/PLAYBOOK.md` 4.5, 5, 15,
17, `PRD.md` VOC, FP, I18N, AC-VOC1..3, AC-FP1, J-5, J-6, section 6, `docs/inputs/INPUT_DELTAS.md`
sections 1, 3, 5, `docs/inputs/schema.sql` (`taxonomy_term`, `footprint_term`,
`footprint_history`, `tenant_tag`, `tagging`, `jurisdiction`, `proposal`),
`docs/inputs/data-model.md` section 4 "Footprint matching", `backend/apps/taxonomy/app.md`,
`backend/apps/proposals/app.md` (PRO-S* that touch vocabularies), `design/system/pills-and-labels.md`,
`backend/apps/library/fixtures/prototype_data.json` if present (its `vocabularies` section
lists keys and labels the prototype uses; use the same keys).

Scope: VOC-01, VOC-02 (backend), VOC-07, FP-01, FP-02, FP-03 (backend rule; screens apply it
from chunk 3 on), I18N-01, J-5 and J-6 backend halves. Scenarios to un-skip: taxonomy
VOC-S1..S7 (@integration ones), VOC-S11, FP-S1..S5 (@integration), I18N-S1, I18N-S2, and the
proposals scenarios that cover a vocabulary proposal (read `proposals/app.md`; only those).
R2 scenarios (VOC-S8..S10, S12..S14: sub-statuses, scales, reasons, bulk tagging, config
export) stay skipped, but the base mechanics they need (kinds, categories) exist.

## Invariants
Enums in code are kinds only (tier 1 list in INPUT_DELTAS section 1; the kinds-only guard
allowlist in `apps/shared/kinds.py` grows only with a reason). Every list an admin might
extend is `Vocabulary` rows: immutable key, optional kind, labels per language (translation
rows), usage_note, sort_order, active, is_system, is_default. API returns `{key, kind, label}`
never an enum. Retire never delete (usage count first). Merge re-points in one audited
transaction. Case-insensitive uniqueness plus trigram near-duplicate check on create (422
`near_duplicate` with the candidates). System rows can be relabelled, not removed. Library
vocabulary changes are proposals (VOC-07): the only door. Footprint change is a request with a
preview, second-person approval (check constraint decided_by <> requested_by, 409
`four_eyes_violation`) and step-up, one audit event per term. Empty dimension = no
restriction. Every write through `record()`; tenant tables under forced RLS.

## Model (apps/taxonomy unless stated; snake_case)
Library tier 2 vocabularies (each a concrete `Vocabulary` subclass with its own table and
labels table, following the `TenantRole`/`PlatformRole` pattern the chunk 1 agent used):
`TermDimension` (+ `restricts_footprint` bool, fixed `kind` structural: `scope|classification`),
`InstrumentLevel` (+ `binding_default`, `rank`), `ProvisionKind` (+ jurisdiction FK nullable,
`structural_kind`), `ChangeType` (+ `lifecycle_kind`: pre_adoption|adopted|in_force|
supervisory|recurring), `DutyType`, `RelationType`, `SourceKind`, `Urgency` (+ `ordinal`,
`tone` kind from the six tones, `sla_days`), `LibraryTag`, `Flag`.
`TaxonomyTerm` (library): dimension FK TermDimension, key unique per dimension, labels,
parent nullable, usage_note, sort_order, active, is_system. `Jurisdiction` (apps/library):
key (eu, se, dk, no, fi), labels, `default_language` FK Language; seeded.
Tenant tier 3: `TenantTag(TenantVocabulary)`, `LinkKind`, `EffortSize`, `ComplianceStatus`
(+ `category` kind: compliant|partly|gap|not_assessed, `ordinal`), `RiskRating` (+ ordinal),
`CaseSubStatus` (+ `category` kind: the seven case categories), `DismissalReason`,
`CloseReason`: models and seeds with system rows now; their screens are R2.
`FootprintTerm(TenantModel)`: term FK, added_by, added_at, unique (tenant, term).
`FootprintChangeRequest(TenantModel)`: requested_by, requested_at, `adds` and `removes`
(M2M to TaxonomyTerm through tables), preview JSON with named schema `FootprintPreview`
(hidden/revealed counts per record kind: obligations, cases; chunk 2 computes them from
whatever tables exist and returns zeros with `available:false` where the table does not
exist yet), status kind (pending|approved|rejected|withdrawn), decided_by, decided_at,
decision_note, check constraint requester <> decider, version + If-Match.
`FootprintHistory(AppendOnlyModel, TenantModel)`: one row per term added or removed with the
request, actor, step-up assertion id.
Matching: `apps/taxonomy/matching.py`: `in_footprint(record_terms: dict[dimension_key,
set[term_key]], footprint: dict[dimension_key, set[term_key]]) -> bool` (for every dimension
the record carries terms, at least one must be in the footprint; a dimension with no terms
does not restrict; a dimension whose `restricts_footprint` is false is ignored) with
exhaustive unit tests, plus a SQL function `taxonomy_in_footprint(tenant uuid, term_ids uuid[])`
in a RunSQL migration mirroring it, tested against the Python version.
Proposals: minimal `Proposal(LibraryModel)` in `apps/proposals` per schema (kind, target_type,
target_id, title, payload JSON with named schema per kind, field_sources JSON, proposed_by_user,
proposed_by_agent_run nullable, status kind, reviewed_by, reviewed_at, rejection_code,
review_note, idempotency_key unique nullable, check constraint reviewed_by <> proposed_by_user)
with `apply.py` inside `library_write()` for kinds `vocabulary_create`, `vocabulary_relabel`,
`vocabulary_retire`, `vocabulary_merge`, `term_create`; chunk 4 adds the rest. Approve needs
`proposals.review` + step-up; the proposer cannot approve (409).

## API (Ninja `/api/v1`, camelCase, `{items,total}` lists)
- `GET /vocab` (any session): the list of lists `[{list, tier, kind, count, retiredCount}]`.
- `GET /vocab/{list}` (any session, agents with `library:read`): rows `{key, kind, label,
  labels, usageNote, sortOrder, active, isSystem, isDefault, usageCount, extra{...}}`;
  `?includeRetired=true`. Same endpoint serves pickers, filters, pills and agents (AGT-02).
- Tenant lists (`vocab.manage`): `POST /vocab/{list}` (422 `near_duplicate` with candidates
  unless `force:true` from `vocab.manage`), `PATCH /vocab/{list}/{key}` (labels, usage note,
  sort order; If-Match), `POST /vocab/{list}/reorder` `{keys[]}`, `POST /vocab/{list}/{key}/retire`
  (returns usage count; 409 `in_use` unless `confirm:true`), `POST /vocab/{list}/{key}/merge`
  `{into}` (preview then commit: `?dryRun=true` returns what will be re-pointed).
- Library lists: the same routes answer 202 with a created Proposal for `proposals.create`
  holders (tenant compliance officers propose) and require `library_vocab.manage` to skip the
  queue? NO: VOC-07 says library vocabulary changes go through the proposal queue. So library
  list writes ALWAYS create a proposal (202 `{proposal}`); approval in the console applies it.
  Suggest = `POST /vocab/{list}/suggest` for anyone (creates a proposal of kind term_create).
- `GET /proposals`, `GET /proposals/{id}`, `POST /proposals/{id}/approve` (+step-up),
  `POST /proposals/{id}/reject` `{rejectionCode, note}` for `proposals.review` (platform),
  `POST /proposals` for `proposals.create` (tenant) and API keys with `proposals:write`
  (Idempotency-Key header honoured). Designed shapes in openapi.yaml; keep them.
- `GET /taxonomy/terms?dimension=` (designed), `POST /taxonomy/terms` and `PATCH` become
  proposals (INPUT_DELTAS row), `GET /taxonomy/dimensions`.
- `GET /tenant/footprint` `{dimensions[{dimension{key,kind,label}, restrictsFootprint,
  terms[{key,kind,label}], allSelected}], pendingRequest|null}`;
  `POST /tenant/footprint/requests` (`footprint.request`) `{adds[], removes[]}` -> 201 with
  preview; `GET /tenant/footprint/requests`, `POST .../{id}/approve` (`footprint.approve`,
  step-up, four eyes), `POST .../{id}/reject`, `POST .../{id}/withdraw` (requester).
  `PUT /tenant/footprint` is removed (INPUT_DELTAS section 5, row exists).
- `GET /reference/jurisdictions`, `GET /reference/languages`.
Route permissions: every route gated or in `UNGATED_BY_DESIGN` with a reason.

## Seeds
`seed_reference`: every library vocabulary's system rows with en+sv labels and usage notes
(keys from the prototype data fixture and INPUT_DELTAS; urgencies act_now/within_3_months/
six_plus_months/monitor/no_action with tone and ordinal; compliance categories; case
categories), term dimensions (the eleven in schema v0.3 with restricts_footprint true for
regime, account_type, legal_entity, licensed_activity, service_type, client_category,
product_type, channel, lifecycle_stage, jurisdiction; false for theme), jurisdictions EU,
SE, DK, NO, FI. Per-tenant system rows for tenant lists are created when a tenant is
created (hook in the tenant creation logic) and by `seed_reference` for existing tenants.
`seed_e2e`: tenant A's footprint from the prototype (`footprint{regimes, accounts,
entities, services, clients}`), tenant B a different footprint; a pending footprint
request for J-6 authored by the compliance officer; extend the seed-integrity guard.

## Gates and reporting
Test-first per scenario. Full Appendix D backend list, `generate-types.sh` last, contract
drift explained (INPUT_DELTAS section 7 rows for departures), status cells to `built`,
coverage floors for taxonomy and proposals modules. Report files, scenarios, numbers,
deviations, and the exact response shapes for the frontend agent that follows.

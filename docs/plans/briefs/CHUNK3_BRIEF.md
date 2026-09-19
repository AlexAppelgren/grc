# Chunk 3 brief: library and inventory (INV-01 to INV-06)

Repo `C:\Users\Alex\projects\grc`, branch `main`. Chunks 1 and 2 backend are on disk
(read `backend/apps/{identity,taxonomy,proposals,library}/**`, `backend/apps/shared/**`,
the chunk 2 agent's report shapes in `openapi.json`). Then `CLAUDE.md`, `docs/CONVENTIONS.md`,
`docs/PLAYBOOK.md` 4.3, 4.6, 5, 14, 17, `PRD.md` INV, AC-INV1, AUD-03 (report only), section 6,
`docs/inputs/INPUT_DELTAS.md` 1, 3, 5, 7, `docs/inputs/schema.sql` sections for `authority`,
`instrument`, `instrument_relation`, `provision`, `provision_version`, `obligation`,
`obligation_provision`, `obligation_term`, `obligation_relation`, `obligation_version`,
`jurisdiction`, `source_document`, `citation`, `verification`, `problem_report`, `glossary_term`,
`docs/inputs/data-model.md` sections 3, 4 ("Versioning and as of"), 5, 8.1 item 3,
`backend/apps/library/app.md` (INV-S1..S7), `backend/apps/library/fixtures/README.md` and
`prototype_data.json` (the seed source; its keys are the vocabulary keys chunk 2 seeded),
`design/screens/tenant-inventory.html`, `tenant-obligation.html`, `tenant-instrument.html`,
`docs/plans/UI_Implementation_Plan.md` chunk 3 rows.

Scope: INV-01 to INV-06 backend and frontend, `seed_demo` and the E2E seed of the prototype's
library data, "as of", diff, translations, provenance, problem reports (create + list for the
reporter; the console resolves them in chunk 4). Scenarios: library INV-S1..S7 (all), the
`@e2e` ones on the frontend; shared NFR-S10 (tone never chosen by a person, API sends no phrase)
if not yet un-skipped.

## Invariants
Library tables carry no tenant_id (except `owner_tenant_id` nullable for tenant-private
records, R3; add the column now with the "shared or mine" policy so the RLS shape is final).
Library models extend `LibraryModel`; every write happens inside `library_write()` in
`proposals/apply.py` or the reference seeds, nothing else (the library-fence guard enforces
it). Nothing overwritten: provision text and obligation summaries are version rows with
`effective_from` (nullable = since always) and `version_no`; "as of" D returns the version with
the latest effective_from on or before D. Re-verification stamps (`last_verified_at`,
`verified_by`) are the single exception to proposals: `POST /obligations/{id}/verifications`
by `library_editor` inside `library_write()`. Translations are rows keyed by language with
`is_original` and `is_machine` (`INPUT_DELTAS` 3); no `summary_sv` columns. Jurisdiction and
authority are data. Stable keys never change. Every record carries source link and
last-verified date (INV-06). Pills: the API sends keys, kinds and facts (`bindingLevel`,
`openChangeCount`, `pendingApplicability`), never a phrase.

## Model (apps/library)
`Authority` (key, jurisdiction FK, name, short_name, url, kind vocab `SourceKind`? no: authority
kind is not a vocabulary in the deltas; keep `name`, `short_name`, `url`, `jurisdiction`),
`Instrument` (stable_key, short_name, name (translated: `InstrumentTitle` rows), level FK
`InstrumentLevel`, binding bool (default from level), official_ref, eli nullable,
jurisdiction FK, authority FK, regime term FK TaxonomyTerm nullable, in_force_from/to with
precision, implements_note, status kind (`active|retired`), owner_tenant nullable,
created_origin kind, created_by_agent_run nullable uuid, last_verified_at, verified_by nullable
user), `InstrumentRelation` (from, to, relation_type FK RelationType, note),
`Provision` (instrument, parent nullable, kind FK ProvisionKind, ref_label, path (materialised,
e.g. "9 kap. 3 §"), sort_order, stable_key), `ProvisionVersion` (provision, version_no,
effective_from with precision, effective_to nullable, transitional_note, applied_by_proposal
nullable) with `ProvisionText` translation rows (version, language, text, is_original,
is_machine), `Obligation` (stable_key, instrument, ref_label, title (translated rows
`ObligationTitle`), duty_type FK DutyType, trigger_frequency, retention, sanction_exposure,
product_scope, status kind, owner_tenant nullable, provenance: created_origin kind,
created_by_agent_run nullable, created_model text, last_verified_at, verified_by, source_url,
source_label), `ObligationVersion` (obligation, version_no, effective_from with precision,
caused_by_change nullable uuid (chunk 5 FK), applied_by_proposal nullable FK Proposal,
approved_by nullable user, approved_at) with `ObligationSummary` translation rows,
`ObligationProvision` (obligation, provision), `ObligationTerm` (obligation, term),
`ObligationRelation` (from, to, relation_type), `ObligationTag` (obligation, LibraryTag),
`ProblemReport` (mixed: tenant nullable, reporter user, subject_type kind, subject_id, text,
status kind `open|answered|fixed|rejected`, resolved_by_proposal nullable, created_at), and
`Verification` (subject_type, subject_id, verified_by, verified_at, outcome kind, note).
Indexes: trigram on titles and official_ref for chunk 7's keyword leg; `(obligation,
effective_from)`. RLS only on `problem_report` (mixed) and the "shared or mine" policies.

## API (Ninja `/api/v1`, designed shapes in openapi.yaml where they exist; `{items,total}`)
`GET /authorities`, `GET /reference/jurisdictions` (exists), `GET /instruments`
(filters: jurisdiction, level, regime, authority, q, `asOf`, `outsideFootprint=true` to lift
the footprint filter; default respects the tenant footprint via `taxonomy.matching`),
`GET /instruments/{id}`, `GET /instruments/{id}/relations`, `GET /instruments/{id}/provisions`
(tree with the version in force `asOf`), `GET /provisions/{id}/versions`, `GET /obligations`
(filters: instrument, dutyType, term keys per dimension, tag, q, `asOf`, `outsideFootprint`;
each row: `{id, stableKey, refLabel, title, instrument{key,shortName}, bindingLevel{key,kind,
label}, binding, dutyType{key,kind,label}, tags[{key,kind,label}], terms{dimensionKey:[...]},
inFootprint, lastVerifiedAt, openChangeCount: 0 (chunk 5), pendingApplicability: null (chunk 8),
complianceStatus: null (chunk 8)}`), `GET /obligations/{id}` (+ versions list, summary as of,
provisions with text as of, relations, provenance, translations with `isMachine`),
`GET /obligations/{id}/versions`, `GET /obligations/{id}/diff?from=&to=` (sentence-level diff
in the requested language: `[{op: equal|insert|delete, text}]` computed server-side with
`difflib` over sentences), `POST /obligations/{id}/verifications` (`library_editor` only,
step-up), `POST /obligations/{id}/problem-reports` (any member, `problems.report`),
`GET /problem-reports?mine=true`. Content language: `Accept-Language` or `?lang=` chooses
the label and summary language with the tenant's content-language order as fallback;
responses say which language each text is in and whether it is machine translated.

## Seeds
`seed_reference` unchanged (chunk 2 vocabularies). New `manage.py seed_demo` (refuses when
deployed; idempotent by stable key) loads `prototype_data.json` library sections into the
library inside `library_write()` (this is a reference seed, allowlisted by the fence) and
`seed_e2e` calls the same loader so journeys see the prototype's instruments and obligations
(tenant A's footprint from chunk 2 must hide at least one advice-only obligation for J-6).
Extend the seed-integrity guard: instrument and obligation counts, the research-payments
obligation has two versions with a future `effective_from`, and every obligation has en and
sv summaries.

## Frontend (chunk 3 half, same agent or a second one as the orchestrator decides)
Routes `/inventory` (obligation rows in the fixed slot order, filters from `GET /vocab/*`,
"as of", Instruments tab, "Show outside footprint"), `/inventory/obligations/[id]`,
`/inventory/instruments/[id]` per the cards; `features/library/*` extended with the
presentation functions already stubbed in Phase 0; journeys INV-S1..S7 `@e2e`.

## Gates
Test-first; full Appendix D lists; `generate-types.sh` last; contract drift explained;
status cells `built`; coverage floors for library modules. Report shapes and deviations.

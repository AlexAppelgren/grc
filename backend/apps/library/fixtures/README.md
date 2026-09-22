# Prototype sample data as schema rows

`prototype_data.json` is the bleqq prototype's sample data (`design/prototype/index.html`,
the script from line 242: `USERS`, the vocabularies and `seed()`) extracted into plain
JSON keyed by the schema's tables and columns (`docs/inputs/data-model.md` section 5,
`docs/inputs/schema.sql`, vocabularies per `docs/inputs/INPUT_DELTAS.md` section 1).
Text fields are verbatim. Keys, labels in Swedish for vocabularies and taxonomy terms,
authorities, jurisdictions and a few anchor rows are authored here and listed below.

It is not a Django `loaddata` fixture: there are no primary keys or model labels, rows
reference each other by stable key, and it is meant to be read by seed code that goes
through `record()` so audit and outbox rows are written with every insert.

`check_prototype_data.py` validates referential integrity (every referenced key exists,
every vocabulary key is in the `vocabularies` section, every date is ISO 8601, one primary
document per change, no duplicate stable keys, a verified date on every obligation, a
summary in each version's original language) and with `--eval` also that
`backend/eval/retrieval.jsonl` and `classification.jsonl` name only keys that exist here.
Plain Python, no Django, exit 0 when clean.

```
python backend/apps/library/fixtures/check_prototype_data.py --eval
```

## How the seeds load it (chunk 3)

Both seeds are idempotent on the stable keys and deterministic (playbook 8.3). Load order
follows the sections in the file:

1. `jurisdictions`, `authorities`, `vocabularies` (one `Vocabulary` model per section
   name; `kind`, `rank`, `ordinal`, `tone`, `sla_days`, `restricts_footprint` become the
   fixed columns the vocabulary carries), `taxonomy_terms`, `tags`.
2. `instruments`, `instrument_relations`, `provisions`, `provision_versions`,
   `obligations`, `obligation_provisions`, `obligation_versions`, `obligation_terms`,
   `obligation_relations`.
3. `sources`, `source_checks`, `regulatory_changes`, `change_events`, `change_documents`,
   `change_terms`, `change_obligations`, `proposals` (open, never applied by the seed;
   the version-2 text of the research obligation lives in the proposal payload, which is
   what the "approve a proposal" journey applies), `audit_events`.
4. Tenant zone, under `app.tenant_id` of the tenant in `_meta.tenant`: `users` (one login
   per role, passkeys added by the E2E seed), `tenant` (legal entities and products),
   `footprint_terms`, `tenant_obligations`, `internal_links`, `change_cases`,
   `impact_assessments`, `actions`, `evidence`, `gaps`, `tenant_agents`, `agent_runs`.

`seed_demo` loads everything for the demo tenant. `seed_e2e` loads the same rows for
tenant A, a second tenant with a different footprint for the isolation journeys, and adds
the fixed passkey public keys, the one user without a passkey and the negative-case
logins the journeys need. Relative times in the prototype are resolved against
`_meta.anchor_date` (2026-09-16); the E2E seed may re-anchor them to the tenant-local
date at seed time, keeping the same offsets.

References: a field named after a table holds that table's stable key (`instrument`,
`obligation`, `change`, `proposal`, `source`, `agent_run`); term references are
`<dimension>:<key>`; users are their prototype ids (`sara`, `johan`, `maria`, `erik`).
Dates are ISO 8601; a partial prototype date (`2025-12`) is stored as the first day of
the period with a `*_precision` of `month`. Timestamps are naive in `Europe/Stockholm`.

## Keys and vocabularies introduced here

Stable keys: instruments by official reference (`sfs-2007-528`, `fffs-2017-2`,
`esma-35-43-3006`, `celex-32022r2554`); obligations `obl-<topic>`
(`obl-research-payments`, `obl-esma-warnings`); changes `chg-<authority>-<year>-<topic>`;
proposals `prop-<topic>`; provisions `<instrument>/<unit>` (`sfs-2007-528/9`,
`celex-32016r0679/art-22`), a nested unit hyphenating each level down the tree
(`fffs-2017-2/9-6` for 9 kap. 6 §, `fffs-2017-2/9-6-1` for its first paragraph); sources
slugified names; agent runs `run-<agent>-<id>`. Every row keeps its `prototype_id`.

Vocabulary keys (all with English and Swedish labels and a usage note in the file):

- `instrument_level`: `eu_regulation`, `eu_directive`, `eu_guidance`, `act`,
  `authority_regulation`. Jurisdiction neutral as INPUT_DELTAS asks: the prototype's
  "Swedish act" is `act` and "FI regulation" is `authority_regulation`; the country comes
  from `jurisdiction`. The EU levels are the supranational tier and keep their name.
- `change_type` (with lifecycle kind): `proposal`, `adopted`, `supervision`,
  `enforcement`, `recurring_date` from the prototype; `consultation`, `in_force`,
  `guidance`, `court_ruling` used by the classification set only.
- `urgency` (ordinal, tone, SLA days): `act_now`, `within_3_months`, `six_months_plus`,
  `monitor`, `no_action`.
- `flag`: `ai`, `advice_perimeter`.
- `duty_type`: `conduct`, `disclosure`, `record_keeping`, `reporting`, `governance`,
  `technical`.
- `term_dimension` (with `restricts_footprint`): `regime`, `account_type`,
  `legal_entity`, `service_type`, `client_category` restrict; `channel`,
  `lifecycle_stage` describe only.
- `compliance_status` (tenant scale with ordinal and tone): `compliant`,
  `partly_compliant`, `gap`, `not_assessed`. `risk_rating`: `low`, `medium`, `high`.
- `relation_type`: `implements`, `elaborates`, `related` (the last for `obligation_relations`, whose schema v0.3 default it is), `amends` (T8, for FFFS 2026:11's `instrument_relations` row). `source_kind`: `authority_site`,
  `legal_database`, `open_web_sweep`, `tenant_private`. `link_kind`: `policy`,
  `procedure`, `control`.

Taxonomy term keys: regimes `securities`, `insurance`, `tax`, `data_protection`, `aml`,
`ai_ict`; accounts `isk`, `af`, `depa`, `kf`, `pension`; entities `bank`, `insurer`,
`fund_company`; services `advice`, `non_advised`, `execution_only`,
`portfolio_management`, `custody`, `insurance_distribution`; clients `retail`,
`professional`; channels `digital`, `branch`; stages `pre_trade`, `post_trade`, `ongoing`,
`product_lifecycle`, `reporting`, `onboarding` (the last is not in the prototype's
obligations; it comes from the AMLR proposal's scope line).

Enum kinds (tier 1) the file uses are listed in `_meta.kinds_used`. Prototype change
types map per data-model section 5: "Adopted rule", "EU legislation" and "EU regulation"
to `adopted` (none of the three has applied yet, so none is `in_force`), "EU proposal"
to `proposal`, "Supervision", "Enforcement" and "Recurring date" to their keys.

## What was ambiguous in the prototype

- **Relations need targets.** `instrument.implements` is a display line ("MiFID II,
  Directive 2014/65/EU"). To also produce `instrument_relation` rows, three EU directives
  the prototype never lists are added as instruments with `from_prototype: false`:
  MiFID II, the MiFID II delegated directive and the IDD. "Directly applicable" and
  "National rule" produce no relation.
- **Provisions.** Only "9 kap." (LVM) and "Article 22" (GDPR) are structural units in the
  prototype's own sample data, so only those become `provision` rows; the other `ref`
  values ("Costs and charges", "Guideline on warnings") are section headings and stay
  `ref_label`. **FFFS 2017:2's own tree** (T8, INV-02, INV-S2) is added on top, with
  `from_prototype: false`: chapters 9, 10 and 11 kap., three sections under 9 kap. (6 §,
  10 § and 23 §) and one paragraph under 6 §, so the tree has three levels, each with a
  `provision_versions` text row from 2018-01-03 (sv original, en machine translation); 6 §
  also carries a version 2 from 2026-10-01 with a transitional note. The sample amending
  instrument **FFFS 2026:11** is added the same way, related to FFFS 2017:2 by the new
  `amends` relation type (sv "Ändrar"); it carries no obligation, so its verified date
  falls to `_meta.anchor_date`. `obl-research-payments` and `obl-costs-charges` are linked
  to their sections (6 § and 10 §) through `obligation_provisions`. All of this is sample
  text taken from the instrument card (`design/screens/tenant-instrument.html`), never
  presented as verbatim law.
- **Authorities.** "EU Council and Parliament" and "EU" have no single authority in the
  prototype; one row `eu-legislator` is added and used for the EU regulations as issuer
  and for those changes, with `authority_label` kept verbatim. Data-model section 5 notes
  the label is free text; the row is additive.
- **Duplicates.** The prototype counts one merged duplicate on the research-payments
  change without showing a second page. A placeholder document (`#duplicate-1`) carries
  the count so `change_document.is_duplicate` has a row; the seed may drop it.
- **Confidence and confirmation on change-obligation links** are not in the prototype;
  both are null, origin `agent`.
- **J-6 needs an advice-only obligation.** Switching Advice off (the pending footprint
  request of J-6) must hide something, but every prototype obligation that names advice
  also names another service. One sample obligation, `obl-suitability-statement` (LVM
  9 kap., the suitability statement before an advised trade), is added with
  `from_prototype: false`: advice is its only service, every other restricting term is
  inside the prototype's footprint, and it has one version since always with a Swedish
  original and an English machine translation. It is sample text, not verbatim law. No
  prototype obligation is rescoped.
- **Verified dates and verifiers.** The prototype dates obligations only. The loader gives
  an instrument without its own `last_verified_at` the latest date among its obligations,
  or `_meta.anchor_date` when it has none. `verified_by` is kept verbatim (`sara`) but never
  loaded: she is a tenant user, and a library record is verified by a library editor, so
  it stays null until someone re-verifies.
- **Source URLs of instruments** are the prototype's site roots (riksdagen.se, fi.se,
  the EUR-Lex ELI pages it uses). Exact document URLs are verified in chunk 3 and logged in
  `docs/plans/Verification_Log.md`; `in_force_from` dates on instruments are authored and
  need the same check.
- **Source check times.** Sources say "today", "yesterday", "3 days ago"; they are
  resolved against the anchor date at 06:02, the watch agent's run time. `items_found` is
  0 everywhere because the prototype gives no count.
- **The recurring date** gets an RRULE (`FREQ=YEARLY;BYMONTH=11;BYMONTHDAY=30`) because
  the prototype only says "every 30 November" in prose.
- **The AMLR proposal's scope** is a pipe-separated string; it is kept verbatim in
  `payload.scope_text_in_prototype` and parsed into term references beside it.
- **Tags** are English words with a few Swedish ones (`schablonintäkt`, `faktablad`);
  each becomes a tag row whose `label_sv` equals `label_en` because the prototype shows
  one label.
- **The tenant budget** shows a cap and a spent figure with no currency; EUR is assumed
  and noted in the row.
- **Agent `kind`** in `backend/agents/watch-sweeper/v1/definition.yaml` is `watch`, the Phase 0
  skeleton's contract; schema.sql's `agent_kind` enum says `research`. The seed of
  `agent_definition` rows (chunk 5) settles which, and `tenant_agents.agent` here uses the
  definition ids `watch-sweeper`, `reverifier`, `so-what-drafter`, `private-source-watch`;
  only the first has a definition folder yet.
- **The prototype has the tenant's compliance officer approving agent proposals.**
  INPUT_DELTAS section 5 says that review belongs to `library_editor` in the platform
  console; the audit rows here are unchanged, the journey is not.

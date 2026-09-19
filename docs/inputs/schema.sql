-- Compliance Watch: database schema v0.3
-- Target: PostgreSQL 16+, pgvector 0.8+
-- Two zones:
--   LIBRARY  = sourced public facts shared by all tenants. No tenant_id. Changed only through approved proposals.
--   TENANT   = judgement and work of one company. tenant_id on every row, row-level security.
-- Phase markers (P1, P2, P3) follow the build order agreed in the Compliance Watch chat.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- Enumerations
-- ---------------------------------------------------------------------------
CREATE TYPE platform_role      AS ENUM ('platform_admin', 'library_editor');
CREATE TYPE tenant_role        AS ENUM ('admin', 'compliance_officer', 'owner', 'approver', 'contributor', 'reader', 'auditor');
CREATE TYPE actor_type         AS ENUM ('user', 'agent', 'system');
CREATE TYPE origin_type        AS ENUM ('agent', 'user');
CREATE TYPE agent_kind         AS ENUM ('research', 'backfill', 'reverify');
CREATE TYPE run_status         AS ENUM ('running', 'succeeded', 'failed');
CREATE TYPE job_status         AS ENUM ('queued', 'running', 'succeeded', 'failed');

CREATE TYPE term_dimension     AS ENUM ('jurisdiction', 'regime', 'theme', 'account_type', 'legal_entity', 'licensed_activity', 'service_type', 'client_category', 'product_type', 'channel', 'lifecycle_stage');
CREATE TYPE instrument_level   AS ENUM ('eu_regulation', 'eu_directive', 'eu_delegated_act', 'eu_guidance', 'swedish_act', 'swedish_ordinance', 'fi_regulation', 'fi_guidance', 'industry_code');
CREATE TYPE relation_type      AS ENUM ('implements', 'elaborates', 'amends', 'replaces', 'delegated_under');
CREATE TYPE provision_kind     AS ENUM ('part', 'chapter', 'section', 'article', 'paragraph', 'guideline', 'annex');
CREATE TYPE duty_type          AS ENUM ('conduct', 'disclosure', 'record_keeping', 'reporting', 'governance', 'technical');
CREATE TYPE record_status      AS ENUM ('active', 'retired');
CREATE TYPE date_precision     AS ENUM ('day', 'month', 'quarter', 'year');

CREATE TYPE source_kind        AS ENUM ('authority_site', 'legal_database', 'feed', 'open_web_sweep');
CREATE TYPE check_status       AS ENUM ('ok', 'failed');
CREATE TYPE change_type        AS ENUM ('consultation', 'proposal', 'adopted', 'in_force', 'guidance', 'supervision', 'enforcement', 'court_ruling', 'recurring_date');
CREATE TYPE change_status      AS ENUM ('active', 'superseded', 'withdrawn');
CREATE TYPE urgency            AS ENUM ('act_now', 'within_3_months', 'six_months_plus', 'monitor', 'no_action');

CREATE TYPE proposal_kind      AS ENUM ('new_instrument', 'new_provision_version', 'new_obligation', 'new_obligation_version', 'update_obligation', 'retire_obligation', 'reverification', 'link_change_obligation');
CREATE TYPE proposal_status    AS ENUM ('open', 'approved', 'rejected', 'superseded');

CREATE TYPE applicability      AS ENUM ('applies', 'not_applicable', 'under_assessment');
CREATE TYPE compliance_status  AS ENUM ('compliant', 'partly_compliant', 'gap', 'not_assessed');
CREATE TYPE risk_rating        AS ENUM ('low', 'medium', 'high');
CREATE TYPE approval_status    AS ENUM ('pending', 'approved', 'rejected', 'withdrawn');
CREATE TYPE link_kind          AS ENUM ('policy', 'procedure', 'control', 'process', 'system', 'other');

CREATE TYPE case_status        AS ENUM ('new', 'assigned', 'assessing', 'implementing', 'signoff', 'closed', 'dismissed');
CREATE TYPE close_reason       AS ENUM ('signed_off', 'not_applicable', 'no_action');
CREATE TYPE assessment_applies AS ENUM ('yes', 'partly', 'no');
CREATE TYPE effort_size        AS ENUM ('S', 'M', 'L');
CREATE TYPE evidence_kind      AS ENUM ('file', 'link', 'reference');

CREATE TYPE subject_type       AS ENUM ('tenant', 'member', 'api_key', 'footprint', 'taxonomy_term', 'instrument', 'provision', 'obligation', 'tenant_obligation', 'applicability_request', 'change', 'change_case', 'assessment', 'action', 'evidence', 'proposal', 'source', 'agent_run', 'briefing', 'webhook', 'export', 'import', 'roadmap',
  'org_unit', 'licence', 'product', 'internal_item', 'team', 'invitation', 'identity_provider', 'subscription', 'initiative', 'glossary_term', 'requirement', 'recurring_duty', 'duty_occurrence', 'gap', 'compliance_assessment', 'interpretation', 'source_document', 'ai_generation', 'search', 'newsletter_issue', 'feedback', 'support_access', 'agent', 'tenant_agent', 'research_request', 'source_request');
CREATE TYPE search_source      AS ENUM ('provision_version', 'obligation_version', 'change');
CREATE TYPE ai_purpose         AS ENUM ('so_what', 'change_summary', 'scope_suggestion', 'link_suggestion', 'translation', 'answer');
CREATE TYPE ai_status          AS ENUM ('draft', 'confirmed', 'edited', 'rejected');
CREATE TYPE report_status      AS ENUM ('open', 'accepted', 'rejected', 'fixed');
CREATE TYPE export_kind        AS ENUM ('case_file', 'committee_pack', 'inventory', 'changes', 'audit_log');
CREATE TYPE import_kind        AS ENUM ('obligation_register');
CREATE TYPE ticket_provider    AS ENUM ('jira', 'linear', 'azure_devops', 'github', 'servicenow');
CREATE TYPE feed_filter        AS ENUM ('all', 'regulatory', 'internal');

-- ---------------------------------------------------------------------------
-- 1. Identity and access
-- ---------------------------------------------------------------------------
CREATE TABLE tenant (                                   -- P1
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug           text NOT NULL UNIQUE,
  name           text NOT NULL,
  region         text NOT NULL DEFAULT 'eu-west',
  -- settings keys: default_lang, digest_weekday, reminder_days_before (int[]), escalate_after_days,
  -- escalate_to_role, retention_years {cases, evidence, audit}
  settings       jsonb NOT NULL DEFAULT '{}',
  created_at     timestamptz NOT NULL DEFAULT now(),
  deactivated_at timestamptz
);

CREATE TABLE app_user (                                 -- P1. Authentication is delegated to an OIDC provider.
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email            citext NOT NULL UNIQUE,
  name             text NOT NULL,
  external_subject text UNIQUE,                         -- OIDC "sub"
  locale           text NOT NULL DEFAULT 'en' CHECK (locale IN ('en', 'sv')),
  platform_roles   platform_role[] NOT NULL DEFAULT '{}',
  created_at       timestamptz NOT NULL DEFAULT now(),
  last_seen_at     timestamptz,
  deactivated_at   timestamptz
);

CREATE TABLE membership (                               -- P1 TENANT
  tenant_id          uuid NOT NULL REFERENCES tenant(id),
  user_id            uuid NOT NULL REFERENCES app_user(id),
  roles              tenant_role[] NOT NULL CHECK (cardinality(roles) > 0),
  title              text,                              -- "Obligation owner, digital investing"
  notification_prefs jsonb NOT NULL DEFAULT '{"weekly_digest": true, "on_assignment": true, "reminders": true}',
  last_visit_at      timestamptz,                       -- drives "what changed since my last visit"
  created_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE agent (                                    -- P1 LIBRARY
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL UNIQUE,                     -- "regulatory-weekly"
  kind        agent_kind NOT NULL,
  description text,
  active      boolean NOT NULL DEFAULT true
);

CREATE TABLE agent_run (                                -- P1 LIBRARY. One row per execution, the provenance anchor.
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id         uuid NOT NULL REFERENCES agent(id),
  started_at       timestamptz NOT NULL DEFAULT now(),
  finished_at      timestamptz,
  status           run_status NOT NULL DEFAULT 'running',
  model            text NOT NULL,
  pipeline_version text NOT NULL,                       -- "agent pipeline 0.4"
  stats            jsonb NOT NULL DEFAULT '{}',
  output_ref       text,                                -- e.g. newsletters/regulatory/2026-W38.md
  error            text
);

CREATE TABLE api_key (                                  -- P1. tenant_id NULL = platform key for agents writing to the library.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid REFERENCES tenant(id),
  agent_id     uuid REFERENCES agent(id),
  name         text NOT NULL,
  key_prefix   text NOT NULL,
  key_hash     text NOT NULL,
  scopes       text[] NOT NULL CHECK (scopes <@ ARRAY['agent-runs:write', 'sources:write', 'changes:write', 'proposals:write', 'search:read', 'library:read', 'upcoming:read', 'tenant:read']),
  created_by   uuid REFERENCES app_user(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz,
  revoked_at   timestamptz,
  last_used_at timestamptz
);

-- ---------------------------------------------------------------------------
-- 2. Taxonomy and footprint
-- ---------------------------------------------------------------------------
CREATE TABLE taxonomy_term (                            -- P1 LIBRARY. One table for every scope facet.
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dimension  term_dimension NOT NULL,
  code       text NOT NULL,                             -- "ISK", "advice", "retail"
  label_en   text NOT NULL,
  label_sv   text NOT NULL,
  sort_order int NOT NULL DEFAULT 0,
  active     boolean NOT NULL DEFAULT true,
  UNIQUE (dimension, code)
);

CREATE TABLE footprint_term (                           -- P1 TENANT. What the company is and does.
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  term_id   uuid NOT NULL REFERENCES taxonomy_term(id),
  added_by  uuid REFERENCES app_user(id),
  added_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, term_id)
);

-- ---------------------------------------------------------------------------
-- 3. Library: instruments, provisions, obligations
-- ---------------------------------------------------------------------------
CREATE TABLE authority (                                -- P1 LIBRARY
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code         text NOT NULL UNIQUE,                    -- "FI", "ESMA", "SKV", "IMY"
  name         text NOT NULL,
  jurisdiction text NOT NULL,                           -- "SE", "EU"
  url          text
);

CREATE TABLE instrument (                               -- P1 LIBRARY
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stable_key       text NOT NULL UNIQUE,                -- never changes: "SFS-2007-528", "CELEX-32022R2554"
  short_name       text NOT NULL,                       -- "LVM"
  name             text NOT NULL,
  regime_term_id   uuid NOT NULL REFERENCES taxonomy_term(id),
  level            instrument_level NOT NULL,
  binding          boolean NOT NULL,                    -- false = guidance, comply or explain
  official_ref     text NOT NULL,                       -- "SFS 2007:528", "FFFS 2017:2", "CELEX 32014R1286"
  eli_uri          text,
  source_url       text NOT NULL,
  authority_id     uuid REFERENCES authority(id),
  jurisdiction     text NOT NULL,
  in_force_from    date,
  in_force_to      date,
  implements_note  text,                                -- display line, e.g. "MiFID II, Directive 2014/65/EU"
  status           record_status NOT NULL DEFAULT 'active',
  last_verified_at timestamptz,
  verified_by      uuid REFERENCES app_user(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX instrument_official_ref_trgm ON instrument USING gin (official_ref gin_trgm_ops);

CREATE TABLE instrument_relation (                      -- P1 LIBRARY. Lineage between instruments.
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_instrument_id uuid NOT NULL REFERENCES instrument(id),
  to_instrument_id   uuid NOT NULL REFERENCES instrument(id),
  relation           relation_type NOT NULL,
  from_ref           text,                              -- "9 kap."
  to_ref             text,                              -- "Article 25(3)"
  note               text,
  CHECK (from_instrument_id <> to_instrument_id),
  UNIQUE (from_instrument_id, to_instrument_id, relation, from_ref, to_ref)
);

CREATE TABLE provision (                                -- P1 LIBRARY. The legal structure, one node per chapter, article or paragraph.
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  instrument_id uuid NOT NULL REFERENCES instrument(id),
  parent_id     uuid REFERENCES provision(id),
  stable_key    text NOT NULL UNIQUE,                   -- "SFS-2007-528/9/23"
  kind          provision_kind NOT NULL,
  ref           text NOT NULL,                          -- "9 kap. 23 §", "Article 25(3)"
  heading       text,
  path          text NOT NULL,                          -- "LVM > 9 kap. > 23 §", carried into search chunks
  ordinal       int NOT NULL DEFAULT 0,
  status        record_status NOT NULL DEFAULT 'active'
);
CREATE INDEX provision_instrument_idx ON provision (instrument_id, ordinal);

CREATE TABLE obligation (                               -- P1 LIBRARY. A plain-language duty derived from one or more provisions.
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stable_key            text NOT NULL UNIQUE,           -- other agents point at this, so it never changes
  instrument_id         uuid NOT NULL REFERENCES instrument(id),
  ref_label             text NOT NULL,                  -- "9 kap.", "Costs and charges"
  title                 text NOT NULL,
  duty_type             duty_type NOT NULL,
  product_scope         text,                           -- "Complex instruments"
  trigger_frequency     text,                           -- "Per order in a complex instrument"
  retention             text,                           -- "5 years"
  sanction_exposure     text,
  tags                  text[] NOT NULL DEFAULT '{}',
  status                record_status NOT NULL DEFAULT 'active',
  created_origin        origin_type NOT NULL,
  created_by_agent_run  uuid REFERENCES agent_run(id),
  created_by_user       uuid REFERENCES app_user(id),
  created_model         text,                           -- model and pipeline version if an agent drafted it
  verified_by           uuid REFERENCES app_user(id),
  last_verified_at      timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX obligation_instrument_idx ON obligation (instrument_id);
CREATE INDEX obligation_verified_idx ON obligation (last_verified_at NULLS FIRST);  -- monthly re-verify picks the oldest

CREATE TABLE obligation_provision (                     -- P1 LIBRARY
  obligation_id uuid NOT NULL REFERENCES obligation(id),
  provision_id  uuid NOT NULL REFERENCES provision(id),
  PRIMARY KEY (obligation_id, provision_id)
);

CREATE TABLE obligation_term (                          -- P1 LIBRARY. Scope facets: account, entity, service, client, channel, stage.
  obligation_id uuid NOT NULL REFERENCES obligation(id),
  term_id       uuid NOT NULL REFERENCES taxonomy_term(id),
  PRIMARY KEY (obligation_id, term_id)
);

CREATE TABLE obligation_relation (                      -- P1 LIBRARY
  obligation_id         uuid NOT NULL REFERENCES obligation(id),
  related_obligation_id uuid NOT NULL REFERENCES obligation(id),
  relation              text NOT NULL DEFAULT 'related' CHECK (relation IN ('related', 'elaborates', 'precedent')),
  PRIMARY KEY (obligation_id, related_obligation_id),
  CHECK (obligation_id <> related_obligation_id)
);

-- ---------------------------------------------------------------------------
-- 4. Watch: sources, coverage, changes
-- ---------------------------------------------------------------------------
CREATE TABLE source (                                   -- P1 LIBRARY. The source registry.
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name            text NOT NULL UNIQUE,                 -- "fi.se", "Open web sweep"
  url             text,
  kind            source_kind NOT NULL,
  authority_id    uuid REFERENCES authority(id),
  check_frequency text NOT NULL DEFAULT 'weekly' CHECK (check_frequency IN ('daily', 'weekly', 'monthly')),
  active          boolean NOT NULL DEFAULT true
);

CREATE TABLE source_check (                             -- P1 LIBRARY. Coverage log: "how do you know you missed nothing".
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id    uuid NOT NULL REFERENCES source(id),
  agent_run_id uuid REFERENCES agent_run(id),
  checked_at   timestamptz NOT NULL DEFAULT now(),
  status       check_status NOT NULL,
  items_found  int NOT NULL DEFAULT 0,
  error        text
);
CREATE INDEX source_check_latest_idx ON source_check (source_id, checked_at DESC);

CREATE TABLE regulatory_change (                        -- P1 LIBRARY. What happened, sourced facts only.
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stable_key          text NOT NULL UNIQUE,
  title               text NOT NULL,
  change_type         change_type NOT NULL,
  authority_id        uuid REFERENCES authority(id),
  authority_label     text NOT NULL,                    -- "EU Council and Parliament" has no single authority row
  published_on        date,
  published_precision date_precision,
  summary             text NOT NULL,
  so_what_draft       text,                             -- AI draft, copied to each case and confirmed there
  suggested_urgency   urgency,
  key_date            date,                             -- the one date that drives "coming up"
  key_date_precision  date_precision,
  key_date_label      text,                             -- "In force", "Applies", "Rate fixing"
  recurrence_rule     text,                             -- RFC 5545 RRULE for recurring dates
  flags               text[] NOT NULL DEFAULT '{}',     -- "AI", "Advice perimeter"
  source_label        text NOT NULL,
  source_url          text NOT NULL,
  status              change_status NOT NULL DEFAULT 'active',
  superseded_by       uuid REFERENCES regulatory_change(id),
  origin              origin_type NOT NULL,
  agent_run_id        uuid REFERENCES agent_run(id),
  model               text,
  first_seen_at       timestamptz NOT NULL DEFAULT now(),
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX regulatory_change_key_date_idx ON regulatory_change (key_date) WHERE status = 'active';

CREATE TABLE change_event (                             -- P1 LIBRARY. One timeline per change, consultation to in force.
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  change_id      uuid NOT NULL REFERENCES regulatory_change(id) ON DELETE CASCADE,
  label          text NOT NULL,
  event_date     date,                                  -- NULL = date not set
  date_precision date_precision,
  occurred       boolean NOT NULL DEFAULT false,
  sort_order     int NOT NULL DEFAULT 0,
  source_url     text
);
CREATE INDEX change_event_change_idx ON change_event (change_id, sort_order);

CREATE TABLE change_document (                          -- P1 LIBRARY. Source pages, including duplicates merged into the change.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  change_id    uuid NOT NULL REFERENCES regulatory_change(id) ON DELETE CASCADE,
  url          text NOT NULL,
  title        text,
  publisher    text,
  fetched_at   timestamptz,
  content_hash text,
  is_primary   boolean NOT NULL DEFAULT false,
  is_duplicate boolean NOT NULL DEFAULT false,
  risk_flags   text[] NOT NULL DEFAULT '{}',            -- e.g. "embedded_instructions" from the injection screen
  UNIQUE (change_id, url)
);

CREATE TABLE change_term (                              -- P1 LIBRARY. Regimes, accounts and services the change touches.
  change_id uuid NOT NULL REFERENCES regulatory_change(id) ON DELETE CASCADE,
  term_id   uuid NOT NULL REFERENCES taxonomy_term(id),
  PRIMARY KEY (change_id, term_id)
);

CREATE TABLE change_obligation (                        -- P1 LIBRARY
  change_id     uuid NOT NULL REFERENCES regulatory_change(id) ON DELETE CASCADE,
  obligation_id uuid NOT NULL REFERENCES obligation(id),
  origin        origin_type NOT NULL,
  confidence    numeric(4, 3),                          -- similarity score when an agent linked it
  confirmed_by  uuid REFERENCES app_user(id),
  confirmed_at  timestamptz,
  PRIMARY KEY (change_id, obligation_id)
);

-- ---------------------------------------------------------------------------
-- 5. Proposals: the only door into the library
-- ---------------------------------------------------------------------------
CREATE TABLE proposal (                                 -- P1 LIBRARY
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind             proposal_kind NOT NULL,
  target_type      subject_type,                        -- NULL for new records
  target_id        uuid,
  change_id        uuid REFERENCES regulatory_change(id),
  title            text NOT NULL,
  payload          jsonb NOT NULL,                      -- proposed field values, shape depends on kind
  field_sources    jsonb NOT NULL DEFAULT '{}',         -- one source link per changed field
  source_label     text NOT NULL,
  source_url       text NOT NULL,
  effective_from   date,
  origin           origin_type NOT NULL,
  agent_run_id     uuid REFERENCES agent_run(id),
  model            text,
  proposed_by_user uuid REFERENCES app_user(id),
  idempotency_key  text UNIQUE,
  status           proposal_status NOT NULL DEFAULT 'open',
  reviewed_by      uuid REFERENCES app_user(id),
  reviewed_at      timestamptz,
  review_note      text,
  applied_at       timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  CHECK (reviewed_by IS NULL OR proposed_by_user IS NULL OR reviewed_by <> proposed_by_user)  -- four eyes
);
CREATE INDEX proposal_queue_idx ON proposal (status, created_at);

CREATE TABLE provision_version (                        -- P1 LIBRARY. Verbatim legal text with in-force dates.
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provision_id      uuid NOT NULL REFERENCES provision(id),
  version_no        int NOT NULL,
  original_lang     text NOT NULL CHECK (original_lang IN ('sv', 'en')),
  text_sv           text,
  text_en           text,
  translation_note  text,                               -- "Unofficial translation, AI drafted"
  in_force_from     date,
  in_force_to       date,
  transitional_note text,
  source_url        text NOT NULL,
  content_hash      text NOT NULL,
  proposal_id       uuid REFERENCES proposal(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provision_id, version_no),
  CHECK (text_sv IS NOT NULL OR text_en IS NOT NULL),
  CHECK (in_force_to IS NULL OR in_force_from IS NULL OR in_force_to > in_force_from)
);

CREATE TABLE obligation_version (                       -- P1 LIBRARY. The summary text shown on the obligation page.
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  obligation_id  uuid NOT NULL REFERENCES obligation(id),
  version_no     int NOT NULL,
  summary_en     text NOT NULL,
  summary_sv     text NOT NULL,
  effective_from date,                                  -- NULL on the first version = since the rule began
  effective_to   date,
  change_id      uuid REFERENCES regulatory_change(id), -- the change that caused this version
  proposal_id    uuid REFERENCES proposal(id),
  approved_by    uuid REFERENCES app_user(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (obligation_id, version_no),
  CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from)
);
CREATE INDEX obligation_version_asof_idx ON obligation_version (obligation_id, effective_from);

-- ---------------------------------------------------------------------------
-- 6. Search
-- ---------------------------------------------------------------------------
CREATE TABLE search_chunk (                             -- P1 LIBRARY. One row per legal unit per language.
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_type       search_source NOT NULL,
  source_id         uuid NOT NULL,
  lang              text NOT NULL CHECK (lang IN ('sv', 'en')),
  title             text NOT NULL,
  body              text NOT NULL,
  hierarchy_path    text,
  valid_from        date,                               -- copied from the version, enables "as of"
  valid_to          date,
  metadata          jsonb NOT NULL DEFAULT '{}',        -- instrument_id, obligation_id, regime, binding, term ids
  tsv               tsvector GENERATED ALWAYS AS (
                      setweight(to_tsvector(CASE lang WHEN 'sv' THEN 'swedish'::regconfig ELSE 'english'::regconfig END, title), 'A') ||
                      setweight(to_tsvector(CASE lang WHEN 'sv' THEN 'swedish'::regconfig ELSE 'english'::regconfig END, body), 'B')
                    ) STORED,
  embedding         vector(1024),                       -- match the chosen multilingual model, keep under 2000 for HNSW
  embedding_model   text,
  embedding_version text,
  embedded_at       timestamptz,
  UNIQUE (source_type, source_id, lang)
);
CREATE INDEX search_chunk_tsv_idx ON search_chunk USING gin (tsv);
CREATE INDEX search_chunk_embedding_idx ON search_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX search_chunk_validity_idx ON search_chunk (valid_from, valid_to);

CREATE TABLE saved_search (                             -- P3 TENANT
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenant(id),
  user_id    uuid NOT NULL REFERENCES app_user(id),
  name       text NOT NULL,
  query      text NOT NULL,
  mode       text NOT NULL DEFAULT 'search' CHECK (mode IN ('search', 'ask')),
  filters    jsonb NOT NULL DEFAULT '{}',
  notify     boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 7. Register overlay: the tenant's view of each obligation
-- ---------------------------------------------------------------------------
CREATE TABLE tenant_obligation (                        -- P2 TENANT. "Applies" and "we comply" are separate facts.
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                uuid NOT NULL REFERENCES tenant(id),
  obligation_id            uuid NOT NULL REFERENCES obligation(id),
  applicability            applicability NOT NULL DEFAULT 'under_assessment',
  applicability_reason     text,
  applicability_decided_at timestamptz,
  compliance_status        compliance_status NOT NULL DEFAULT 'not_assessed',
  status_note              text,
  risk_rating              risk_rating,
  first_line_owner         uuid REFERENCES app_user(id),
  compliance_contact       uuid REFERENCES app_user(id),
  process                  text,
  system                   text,
  evidence_location        text,
  next_review_date         date,
  updated_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, obligation_id),
  CHECK (compliance_status = 'not_assessed' OR applicability = 'applies')
);
CREATE INDEX tenant_obligation_review_idx ON tenant_obligation (tenant_id, next_review_date);

CREATE TABLE applicability_request (                    -- P2 TENANT. Four-eyes on every applicability decision.
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              uuid NOT NULL REFERENCES tenant(id),
  tenant_obligation_id   uuid NOT NULL REFERENCES tenant_obligation(id),
  proposed_applicability applicability NOT NULL,
  reason                 text NOT NULL,
  requested_by           uuid NOT NULL REFERENCES app_user(id),
  requested_at           timestamptz NOT NULL DEFAULT now(),
  status                 approval_status NOT NULL DEFAULT 'pending',
  decided_by             uuid REFERENCES app_user(id),
  decided_at             timestamptz,
  decision_note          text,
  CHECK (decided_by IS NULL OR decided_by <> requested_by)
);
CREATE UNIQUE INDEX applicability_one_pending_idx ON applicability_request (tenant_obligation_id) WHERE status = 'pending';

CREATE TABLE internal_link (                            -- P2 TENANT. Linked policies, procedures and controls. Deliberately shallow.
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  tenant_obligation_id uuid NOT NULL REFERENCES tenant_obligation(id),
  kind                 link_kind NOT NULL,
  label                text NOT NULL,
  url                  text,
  external_ref         text,                            -- id in the GRC system
  created_by           uuid NOT NULL REFERENCES app_user(id),
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE attestation (                              -- P3 TENANT. Yearly confirmation by the obligation owner.
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  tenant_obligation_id uuid NOT NULL REFERENCES tenant_obligation(id),
  period_year          int NOT NULL,
  attested_by          uuid NOT NULL REFERENCES app_user(id),
  attested_at          timestamptz NOT NULL DEFAULT now(),
  status_at_attest     compliance_status NOT NULL,
  statement            text,
  UNIQUE (tenant_obligation_id, period_year)
);

CREATE TABLE waiver (                                   -- P3 TENANT
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  tenant_obligation_id uuid NOT NULL REFERENCES tenant_obligation(id),
  description          text NOT NULL,
  granted_by           text NOT NULL,
  valid_from           date NOT NULL,
  valid_to             date,
  created_by           uuid NOT NULL REFERENCES app_user(id),
  created_at           timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 8. Case workflow: one case per tenant per change
-- ---------------------------------------------------------------------------
CREATE TABLE change_case (                              -- P1 for status new and footprint match, P2 for the rest
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  change_id            uuid NOT NULL REFERENCES regulatory_change(id),
  status               case_status NOT NULL DEFAULT 'new',
  urgency              urgency NOT NULL,
  footprint_match      boolean NOT NULL,                -- recomputed when the footprint or the change scope moves
  owner_id             uuid REFERENCES app_user(id),
  so_what_text         text,
  so_what_confirmed    boolean NOT NULL DEFAULT false,  -- false = shown as "Drafted by AI, not yet confirmed"
  so_what_confirmed_by uuid REFERENCES app_user(id),
  so_what_confirmed_at timestamptz,
  triaged_by           uuid REFERENCES app_user(id),
  triaged_at           timestamptz,
  dismissed_reason     text,
  dismissed_by         uuid REFERENCES app_user(id),
  dismissed_at         timestamptz,
  signoff_requested_by uuid REFERENCES app_user(id),
  signoff_requested_at timestamptz,
  signed_off_by        uuid REFERENCES app_user(id),
  close_reason         close_reason,
  closed_note          text,
  closed_at            timestamptz,
  briefing_week        date,                            -- Monday of the ISO week it first appeared in the briefing
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, change_id),
  CHECK (status <> 'dismissed' OR dismissed_reason IS NOT NULL),
  CHECK (status NOT IN ('assigned', 'assessing', 'implementing', 'signoff') OR owner_id IS NOT NULL),
  CHECK (signed_off_by IS NULL OR signed_off_by <> signoff_requested_by)  -- four eyes
);
CREATE INDEX change_case_queue_idx ON change_case (tenant_id, status, urgency);
CREATE INDEX change_case_owner_idx ON change_case (tenant_id, owner_id) WHERE status NOT IN ('closed', 'dismissed');

CREATE TABLE impact_assessment (                        -- P2 TENANT
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenant(id),
  case_id           uuid NOT NULL UNIQUE REFERENCES change_case(id),
  applies           assessment_applies NOT NULL DEFAULT 'yes',
  why               text,
  what_must_change  text,
  internal_deadline date,
  effort            effort_size NOT NULL DEFAULT 'M',
  contributors      text[] NOT NULL DEFAULT '{}',       -- "Legal", "Product", "Tech"
  saved             boolean NOT NULL DEFAULT false,
  saved_by          uuid REFERENCES app_user(id),
  saved_at          timestamptz,
  CHECK (NOT saved OR why IS NOT NULL)
);

CREATE TABLE action (                                   -- P2 TENANT
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenant(id),
  case_id           uuid NOT NULL REFERENCES change_case(id),
  title             text NOT NULL,
  owner_id          uuid NOT NULL REFERENCES app_user(id),
  due_date          date,
  done_at           timestamptz,
  done_by           uuid REFERENCES app_user(id),
  ticket_provider   ticket_provider,
  ticket_key        text,
  ticket_url        text,
  created_by        uuid NOT NULL REFERENCES app_user(id),
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX action_due_idx ON action (tenant_id, due_date) WHERE done_at IS NULL;

CREATE TABLE evidence (                                 -- P2 TENANT. Files live in the private bucket, only the key is stored here.
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  case_id              uuid REFERENCES change_case(id),
  tenant_obligation_id uuid REFERENCES tenant_obligation(id),
  kind                 evidence_kind NOT NULL,
  name                 text NOT NULL,
  storage_key          text,
  url                  text,
  content_hash         text,
  size_bytes           bigint,
  mime_type            text,
  uploaded_by          uuid NOT NULL REFERENCES app_user(id),
  uploaded_at          timestamptz NOT NULL DEFAULT now(),
  removed_at           timestamptz,                     -- soft delete, the audit trail keeps the name
  CHECK (case_id IS NOT NULL OR tenant_obligation_id IS NOT NULL)
);

CREATE TABLE comment (                                  -- P2 TENANT. Comments and mentions on any record.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  subject_type subject_type NOT NULL,
  subject_id   uuid NOT NULL,
  body         text NOT NULL,
  mentions     uuid[] NOT NULL DEFAULT '{}',
  author_id    uuid NOT NULL REFERENCES app_user(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  edited_at    timestamptz,
  deleted_at   timestamptz
);
CREATE INDEX comment_subject_idx ON comment (tenant_id, subject_type, subject_id, created_at);

-- ---------------------------------------------------------------------------
-- 9. Briefing, roadmap, calendar
-- ---------------------------------------------------------------------------
CREATE TABLE briefing (                                 -- P1 TENANT. Snapshot of what the weekly email said.
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenant(id),
  week_start    date NOT NULL,                          -- Monday
  generated_at  timestamptz NOT NULL DEFAULT now(),
  email_sent_at timestamptz,
  UNIQUE (tenant_id, week_start)
);

CREATE TABLE briefing_item (                            -- P1 TENANT
  briefing_id uuid NOT NULL REFERENCES briefing(id) ON DELETE CASCADE,
  case_id     uuid NOT NULL REFERENCES change_case(id),
  tenant_id   uuid NOT NULL REFERENCES tenant(id),
  rank        int NOT NULL,                             -- 1 = lead story
  PRIMARY KEY (briefing_id, case_id)
);

CREATE TABLE calendar_feed (                            -- P1 TENANT. Tokenised ICS subscription.
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenant(id),
  user_id    uuid NOT NULL REFERENCES app_user(id),
  token_hash text NOT NULL UNIQUE,
  filter     feed_filter NOT NULL DEFAULT 'all',
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);

-- ---------------------------------------------------------------------------
-- 10. Notifications, integration, jobs
-- ---------------------------------------------------------------------------
CREATE TABLE notification (                             -- P2 TENANT
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  user_id      uuid NOT NULL REFERENCES app_user(id),
  kind         text NOT NULL CHECK (kind IN ('assigned', 'mention', 'signoff_requested', 'approval_requested', 'due_soon', 'overdue', 'escalation', 'proposal_waiting', 'saved_search_hit')),
  subject_type subject_type NOT NULL,
  subject_id   uuid NOT NULL,
  title        text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  read_at      timestamptz,
  emailed_at   timestamptz
);
CREATE INDEX notification_inbox_idx ON notification (tenant_id, user_id, created_at DESC) WHERE read_at IS NULL;

CREATE TABLE outbox_event (                             -- P1. Written in the same transaction as the change it describes.
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id    uuid REFERENCES tenant(id),              -- NULL = library event
  event_type   text NOT NULL,                           -- "case.triaged", "proposal.approved"
  subject_type subject_type NOT NULL,
  subject_id   uuid NOT NULL,
  payload      jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz
);
CREATE INDEX outbox_pending_idx ON outbox_event (id) WHERE processed_at IS NULL;

CREATE TABLE webhook_endpoint (                         -- P3 TENANT
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenant(id),
  url         text NOT NULL,
  secret_hash text NOT NULL,
  event_types text[] NOT NULL,
  active      boolean NOT NULL DEFAULT true,
  created_by  uuid NOT NULL REFERENCES app_user(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE webhook_delivery (                         -- P3 TENANT
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenant(id),
  endpoint_id     uuid NOT NULL REFERENCES webhook_endpoint(id) ON DELETE CASCADE,
  outbox_event_id bigint NOT NULL REFERENCES outbox_event(id),
  status          job_status NOT NULL DEFAULT 'queued',
  attempts        int NOT NULL DEFAULT 0,
  response_code   int,
  last_attempt_at timestamptz
);

CREATE TABLE ticket_integration (                       -- P3 TENANT. One work tracker per tenant.
  tenant_id  uuid PRIMARY KEY REFERENCES tenant(id),
  provider   ticket_provider NOT NULL,
  config     jsonb NOT NULL,                            -- project key, base url. Secrets stay in the platform secret store.
  active     boolean NOT NULL DEFAULT true,
  updated_by uuid NOT NULL REFERENCES app_user(id),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE export_job (                               -- P3 TENANT
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  kind         export_kind NOT NULL,
  subject_id   uuid,                                    -- case id for a case file
  format       text NOT NULL CHECK (format IN ('pdf', 'txt', 'json', 'xlsx', 'csv')),
  status       job_status NOT NULL DEFAULT 'queued',
  storage_key  text,
  requested_by uuid NOT NULL REFERENCES app_user(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  error        text
);

CREATE TABLE import_job (                               -- P3 TENANT. Spreadsheet register import, nobody starts from zero.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  kind         import_kind NOT NULL,
  storage_key  text NOT NULL,
  mapping      jsonb NOT NULL DEFAULT '{}',             -- spreadsheet column to field
  dry_run      boolean NOT NULL DEFAULT true,
  status       job_status NOT NULL DEFAULT 'queued',
  result       jsonb,                                   -- matched, created, skipped, row errors
  requested_by uuid NOT NULL REFERENCES app_user(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

-- ---------------------------------------------------------------------------
-- 11. Audit and AI governance
-- ---------------------------------------------------------------------------
CREATE TABLE audit_event (                              -- P1. Append-only, enforced by trigger and by revoked privileges.
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id      uuid REFERENCES tenant(id),            -- NULL = library event
  occurred_at    timestamptz NOT NULL DEFAULT now(),
  actor_type     actor_type NOT NULL,
  actor_user_id  uuid REFERENCES app_user(id),
  actor_agent_id uuid REFERENCES agent(id),
  action         text NOT NULL,                         -- "case.triaged", "obligation.status_set"
  subject_type   subject_type NOT NULL,
  subject_id     uuid NOT NULL,
  subject_label  text NOT NULL,                         -- title at the time, so the log reads on its own
  summary        text NOT NULL,                         -- "Confirmed as relevant, Act now, assigned to Johan Berg"
  before         jsonb,
  after          jsonb,
  request_id     text
);
CREATE INDEX audit_subject_idx ON audit_event (subject_type, subject_id, occurred_at);
CREATE INDEX audit_tenant_time_idx ON audit_event (tenant_id, occurred_at DESC);

CREATE FUNCTION audit_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_event is append-only';
END $$;
CREATE TRIGGER audit_event_no_change BEFORE UPDATE OR DELETE ON audit_event
  FOR EACH ROW EXECUTE FUNCTION audit_event_immutable();

CREATE TABLE ai_generation (                            -- P1. A log of what the model produced, including Ask answers.
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid REFERENCES tenant(id),
  agent_run_id  uuid REFERENCES agent_run(id),
  user_id       uuid REFERENCES app_user(id),           -- who asked, for purpose = answer
  purpose       ai_purpose NOT NULL,
  subject_type  subject_type,
  subject_id    uuid,
  model         text NOT NULL,
  model_version text,
  prompt_hash   text,
  input         jsonb NOT NULL DEFAULT '{}',            -- question, as_of, ids of the chunks given to the model
  output        text NOT NULL,
  citations     jsonb NOT NULL DEFAULT '[]',            -- [{obligation_id, version_no, instrument, ref}]
  status        ai_status NOT NULL DEFAULT 'draft',
  reviewed_by   uuid REFERENCES app_user(id),
  reviewed_at   timestamptz,
  feedback      text CHECK (feedback IN ('helpful', 'wrong')),
  feedback_note text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ai_generation_subject_idx ON ai_generation (subject_type, subject_id);

CREATE TABLE problem_report (                           -- P1. The "this looks wrong" button. Feeds corrections back to the agents.
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             uuid REFERENCES tenant(id),
  subject_type          subject_type NOT NULL,
  subject_id            uuid NOT NULL,
  description           text NOT NULL,
  reported_by           uuid NOT NULL REFERENCES app_user(id),
  reported_at           timestamptz NOT NULL DEFAULT now(),
  status                report_status NOT NULL DEFAULT 'open',
  resolution_note       text,
  resulting_proposal_id uuid REFERENCES proposal(id),
  resolved_by           uuid REFERENCES app_user(id),
  resolved_at           timestamptz
);

CREATE TABLE eval_question (                            -- P3 LIBRARY. 50 to 100 real questions with known answers.
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  question                text NOT NULL,
  lang                    text NOT NULL CHECK (lang IN ('sv', 'en')),
  as_of                   date,
  expected_obligation_ids uuid[] NOT NULL DEFAULT '{}',
  expected_provision_ids  uuid[] NOT NULL DEFAULT '{}',
  notes                   text,
  active                  boolean NOT NULL DEFAULT true
);

CREATE TABLE eval_run (                                 -- P3 LIBRARY
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_at   timestamptz NOT NULL DEFAULT now(),
  config   jsonb NOT NULL,                              -- embedding model, fusion constant, reranker
  metrics  jsonb NOT NULL,                              -- recall_at_10, mrr
  results  jsonb NOT NULL,                              -- per question
  run_by   uuid REFERENCES app_user(id)
);

-- ---------------------------------------------------------------------------
-- 12. Footprint matching
-- Rule from the prototype: for every dimension where the record carries terms,
-- at least one of them must be in the footprint. A dimension with no terms
-- does not restrict. Obligations also need their instrument's regime in the footprint.
-- ---------------------------------------------------------------------------
CREATE FUNCTION change_in_footprint(p_tenant uuid, p_change uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT NOT EXISTS (
    SELECT 1
    FROM (
      SELECT t.dimension, bool_or(f.term_id IS NOT NULL) AS hit
      FROM change_term ct
      JOIN taxonomy_term t ON t.id = ct.term_id
      LEFT JOIN footprint_term f ON f.term_id = ct.term_id AND f.tenant_id = p_tenant
      WHERE ct.change_id = p_change
      GROUP BY t.dimension
    ) d
    WHERE NOT d.hit
  );
$$;

CREATE FUNCTION obligation_in_footprint(p_tenant uuid, p_obligation uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
           SELECT 1 FROM obligation o
           JOIN instrument i ON i.id = o.instrument_id
           JOIN footprint_term f ON f.term_id = i.regime_term_id AND f.tenant_id = p_tenant
           WHERE o.id = p_obligation)
     AND NOT EXISTS (
           SELECT 1
           FROM (
             SELECT t.dimension, bool_or(f.term_id IS NOT NULL) AS hit
             FROM obligation_term ot
             JOIN taxonomy_term t ON t.id = ot.term_id
             LEFT JOIN footprint_term f ON f.term_id = ot.term_id AND f.tenant_id = p_tenant
             WHERE ot.obligation_id = p_obligation
               AND t.dimension IN ('jurisdiction', 'account_type', 'legal_entity', 'licensed_activity', 'service_type', 'client_category', 'product_type')
             GROUP BY t.dimension
           ) d
           WHERE NOT d.hit);
$$;

-- ---------------------------------------------------------------------------
-- 13. Derived views: one query, many outputs
-- ---------------------------------------------------------------------------
-- Public facts only. Read by the newsletter agent, the app and the calendar feed, so they never disagree.
CREATE VIEW v_upcoming AS
  SELECT c.id AS change_id, c.title, c.key_date, c.key_date_precision, c.key_date_label,
         c.change_type, c.authority_label, c.suggested_urgency, c.source_url
  FROM regulatory_change c
  WHERE c.status = 'active' AND c.key_date >= current_date;

-- Roadmap = regulatory dates plus the tenant's own deadlines.
CREATE VIEW v_roadmap_item AS
  SELECT cc.tenant_id, 'regulatory'::text AS kind, 'change_date'::text AS item_type,
         cc.id AS case_id, NULL::uuid AS obligation_id, c.key_date AS item_date,
         c.key_date_label || ': ' || c.title AS label, cc.owner_id
  FROM change_case cc JOIN regulatory_change c ON c.id = cc.change_id
  WHERE cc.status NOT IN ('closed', 'dismissed') AND cc.footprint_match AND c.key_date >= current_date
  UNION ALL
  SELECT cc.tenant_id, 'internal', 'internal_deadline', cc.id, NULL, ia.internal_deadline,
         'Internal deadline: ' || c.title, cc.owner_id
  FROM impact_assessment ia
  JOIN change_case cc ON cc.id = ia.case_id
  JOIN regulatory_change c ON c.id = cc.change_id
  WHERE ia.saved AND ia.internal_deadline >= current_date AND cc.status NOT IN ('closed', 'dismissed')
  UNION ALL
  SELECT a.tenant_id, 'internal', 'action_due', a.case_id, NULL, a.due_date,
         'Action: ' || a.title, a.owner_id
  FROM action a JOIN change_case cc ON cc.id = a.case_id
  WHERE a.done_at IS NULL AND a.due_date >= current_date AND cc.status NOT IN ('closed', 'dismissed')
  UNION ALL
  SELECT tob.tenant_id, 'internal', 'review_due', NULL, tob.obligation_id, tob.next_review_date,
         'Review: ' || o.title, tob.first_line_owner
  FROM tenant_obligation tob JOIN obligation o ON o.id = tob.obligation_id
  WHERE tob.applicability = 'applies' AND tob.compliance_status <> 'compliant'
    AND tob.next_review_date >= current_date;

-- ===========================================================================
-- PART 2 (v0.2): additions from the data model review
-- Part 1 modelled the prototype and its workflows. Part 2 adds what a running
-- platform needs around them, and the compliance depth a real register needs.
-- ===========================================================================

CREATE TYPE tenant_status      AS ENUM ('trial', 'active', 'suspended', 'cancelled');
CREATE TYPE user_status        AS ENUM ('invited', 'active', 'suspended', 'deactivated');
CREATE TYPE subscription_status AS ENUM ('trialing', 'active', 'past_due', 'cancelled');
CREATE TYPE invoice_status     AS ENUM ('draft', 'open', 'paid', 'void', 'uncollectible');
CREATE TYPE org_unit_kind      AS ENUM ('legal_entity', 'business_area', 'business_unit', 'function');
CREATE TYPE assessment_method  AS ENUM ('self_assessment', 'second_line_review', 'internal_audit', 'external_audit', 'regulator');
CREATE TYPE gap_status         AS ENUM ('open', 'remediating', 'accepted', 'closed');
CREATE TYPE gap_source         AS ENUM ('assessment', 'change_case', 'audit', 'incident', 'regulator');
CREATE TYPE duty_status        AS ENUM ('upcoming', 'in_progress', 'done', 'missed', 'not_applicable');
CREATE TYPE impact_level       AS ENUM ('none', 'low', 'medium', 'high');
CREATE TYPE sanction_type      AS ENUM ('remark', 'warning', 'fine', 'injunction', 'licence_withdrawn');
CREATE TYPE initiative_status  AS ENUM ('proposed', 'negotiation', 'adopted', 'implementing', 'in_force', 'abandoned');
CREATE TYPE verification_outcome AS ENUM ('no_change', 'change_found', 'source_unavailable');
CREATE TYPE feedback_kind      AS ENUM ('bug', 'idea', 'question', 'praise', 'nps');
CREATE TYPE feedback_status    AS ENUM ('new', 'triaged', 'planned', 'done', 'declined');
CREATE TYPE email_status       AS ENUM ('queued', 'sent', 'delivered', 'bounced', 'failed');
CREATE TYPE dsr_kind           AS ENUM ('access', 'erasure', 'rectification', 'portability');

-- ---------------------------------------------------------------------------
-- 15. Tenant account, user profile, identity lifecycle, security
-- ---------------------------------------------------------------------------
ALTER TABLE tenant
  ADD COLUMN legal_name         text,
  ADD COLUMN org_number         text,
  ADD COLUMN vat_number         text,
  ADD COLUMN country_code       char(2),
  ADD COLUMN address            jsonb,
  ADD COLUMN sector             text,                   -- "bank", "insurer", "fund company", "investment firm"
  ADD COLUMN size_band          text,
  ADD COLUMN timezone           text NOT NULL DEFAULT 'Europe/Stockholm',
  ADD COLUMN status             tenant_status NOT NULL DEFAULT 'trial',
  ADD COLUMN trial_ends_at      timestamptz,
  ADD COLUMN billing_email      citext,
  ADD COLUMN primary_contact_id uuid REFERENCES app_user(id),
  ADD COLUMN logo_key           text,
  ADD COLUMN onboarding         jsonb NOT NULL DEFAULT '{}';  -- steps done: footprint, org, import, first triage

ALTER TABLE app_user
  ADD COLUMN given_name    text,
  ADD COLUMN family_name   text,
  ADD COLUMN job_title     text,
  ADD COLUMN department    text,
  ADD COLUMN phone         text,
  ADD COLUMN timezone      text,
  ADD COLUMN avatar_key    text,
  ADD COLUMN status        user_status NOT NULL DEFAULT 'active',
  ADD COLUMN mfa_enrolled  boolean NOT NULL DEFAULT false,
  ADD COLUMN last_login_at timestamptz;

ALTER TABLE membership
  ADD COLUMN invited_by          uuid REFERENCES app_user(id),
  ADD COLUMN deactivated_at      timestamptz,
  ADD COLUMN out_of_office_until date,
  ADD COLUMN delegate_user_id    uuid REFERENCES app_user(id);  -- approvals and reminders go here while away

CREATE TABLE tenant_domain (                            -- P3 TENANT. Verified email domains for SSO and auto-join.
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenant(id),
  domain             citext NOT NULL UNIQUE,
  verification_token text NOT NULL,
  verified_at        timestamptz,
  auto_join          boolean NOT NULL DEFAULT false,
  default_roles      tenant_role[] NOT NULL DEFAULT '{reader}'
);

CREATE TABLE identity_provider (                        -- P3 TENANT. SSO and SCIM configuration per tenant.
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenant(id),
  protocol        text NOT NULL CHECK (protocol IN ('oidc', 'saml')),
  name            text NOT NULL,
  issuer          text NOT NULL,
  client_id       text,
  metadata_url    text,
  config          jsonb NOT NULL DEFAULT '{}',          -- claim mapping, group to role mapping. Secrets stay in the secret store.
  enforce_sso     boolean NOT NULL DEFAULT false,
  scim_enabled    boolean NOT NULL DEFAULT false,
  scim_token_hash text,
  active          boolean NOT NULL DEFAULT true,
  created_by      uuid NOT NULL REFERENCES app_user(id),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE invitation (                               -- P1 TENANT
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id),
  email            citext NOT NULL,
  roles            tenant_role[] NOT NULL,
  title            text,
  token_hash       text NOT NULL UNIQUE,
  invited_by       uuid NOT NULL REFERENCES app_user(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  expires_at       timestamptz NOT NULL,
  accepted_at      timestamptz,
  accepted_user_id uuid REFERENCES app_user(id),
  revoked_at       timestamptz
);

CREATE TABLE user_session (                             -- P1. Lets an admin or the user revoke access at once.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES app_user(id),
  tenant_id    uuid REFERENCES tenant(id),
  idp_id       uuid REFERENCES identity_provider(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  revoked_at   timestamptz,
  ip           inet,
  user_agent   text
);
CREATE INDEX user_session_user_idx ON user_session (user_id) WHERE revoked_at IS NULL;

CREATE TABLE login_event (                              -- P1. Security log, including failures and API key use.
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at    timestamptz NOT NULL DEFAULT now(),
  tenant_id      uuid REFERENCES tenant(id),
  user_id        uuid REFERENCES app_user(id),
  api_key_id     uuid REFERENCES api_key(id),
  email          citext,
  method         text NOT NULL CHECK (method IN ('oidc', 'saml', 'magic_link', 'api_key')),
  success        boolean NOT NULL,
  failure_reason text,
  ip             inet,
  user_agent     text
);
CREATE INDEX login_event_user_idx ON login_event (user_id, occurred_at DESC);

CREATE TABLE team (                                     -- P2 TENANT. Ownership that survives a person leaving.
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenant(id),
  name        text NOT NULL,
  email       citext,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE team_member (                              -- P2 TENANT
  team_id   uuid NOT NULL REFERENCES team(id) ON DELETE CASCADE,
  user_id   uuid NOT NULL REFERENCES app_user(id),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  is_lead   boolean NOT NULL DEFAULT false,
  PRIMARY KEY (team_id, user_id)
);
ALTER TABLE tenant_obligation ADD COLUMN owner_team_id uuid REFERENCES team(id);
ALTER TABLE change_case       ADD COLUMN owner_team_id uuid REFERENCES team(id);

CREATE TABLE legal_document (                           -- P1 PLATFORM. Terms, privacy notice, DPA, subprocessor list.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind         text NOT NULL CHECK (kind IN ('terms', 'privacy', 'dpa', 'subprocessors')),
  version      text NOT NULL,
  published_at timestamptz NOT NULL,
  url          text NOT NULL,
  content_hash text NOT NULL,
  UNIQUE (kind, version)
);

CREATE TABLE legal_acceptance (                         -- P1. Who accepted which version, for the user or for the tenant.
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_document_id uuid NOT NULL REFERENCES legal_document(id),
  user_id           uuid NOT NULL REFERENCES app_user(id),
  tenant_id         uuid REFERENCES tenant(id),         -- set when accepted on behalf of the company
  accepted_at       timestamptz NOT NULL DEFAULT now(),
  ip                inet
);

CREATE TABLE support_access (                           -- P1 TENANT. Every time platform staff enter a tenant, visible to that tenant.
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id),
  platform_user_id uuid NOT NULL REFERENCES app_user(id),
  reason           text NOT NULL,
  ticket_ref       text,
  access_level     text NOT NULL DEFAULT 'read' CHECK (access_level IN ('read', 'write')),
  approved_by      uuid REFERENCES app_user(id),        -- tenant admin, when the tenant requires approval
  started_at       timestamptz NOT NULL DEFAULT now(),
  ended_at         timestamptz
);

CREATE TABLE data_subject_request (                     -- P2. GDPR requests about users of the platform.
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid REFERENCES tenant(id),
  user_id       uuid REFERENCES app_user(id),
  subject_email citext NOT NULL,
  kind          dsr_kind NOT NULL,
  received_at   timestamptz NOT NULL DEFAULT now(),
  due_at        timestamptz NOT NULL,
  status        job_status NOT NULL DEFAULT 'queued',
  handled_by    uuid REFERENCES app_user(id),
  completed_at  timestamptz,
  export_key    text,
  note          text
);

CREATE TABLE legal_hold (                               -- P3 TENANT. Stops retention from deleting a record.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  subject_type subject_type NOT NULL,
  subject_id   uuid NOT NULL,
  reason       text NOT NULL,
  placed_by    uuid NOT NULL REFERENCES app_user(id),
  placed_at    timestamptz NOT NULL DEFAULT now(),
  released_at  timestamptz
);

CREATE TABLE retention_run (                            -- P3 TENANT. Proof that the retention settings were executed.
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id),
  run_at         timestamptz NOT NULL DEFAULT now(),
  policy         jsonb NOT NULL,
  deleted_counts jsonb NOT NULL,
  status         job_status NOT NULL
);

-- ---------------------------------------------------------------------------
-- 16. Plans, subscriptions, usage. Card data never enters this database, the payment provider holds it.
-- ---------------------------------------------------------------------------
CREATE TABLE plan (                                     -- P2 PLATFORM
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code          text NOT NULL UNIQUE,
  name          text NOT NULL,
  price_monthly numeric(10, 2),
  currency      char(3) NOT NULL DEFAULT 'EUR',
  limits        jsonb NOT NULL DEFAULT '{}',            -- seats, ask_queries, api_calls, storage_gb
  features      text[] NOT NULL DEFAULT '{}',
  active        boolean NOT NULL DEFAULT true
);

CREATE TABLE tenant_subscription (                      -- P2 TENANT
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                uuid NOT NULL REFERENCES tenant(id),
  plan_id                  uuid NOT NULL REFERENCES plan(id),
  status                   subscription_status NOT NULL,
  seats                    int NOT NULL DEFAULT 1,
  current_period_start     date,
  current_period_end       date,
  cancel_at                date,
  provider                 text,                        -- "stripe"
  provider_customer_id     text,
  provider_subscription_id text,
  created_at               timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE invoice (                                  -- P2 TENANT. Mirror of the provider's invoice, for the admin page.
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenant(id),
  subscription_id     uuid REFERENCES tenant_subscription(id),
  number              text NOT NULL,
  issued_on           date NOT NULL,
  due_on              date,
  amount_excl_vat     numeric(12, 2) NOT NULL,
  vat_amount          numeric(12, 2) NOT NULL DEFAULT 0,
  currency            char(3) NOT NULL,
  status              invoice_status NOT NULL,
  provider_invoice_id text,
  pdf_url             text,
  UNIQUE (tenant_id, number)
);

CREATE TABLE usage_record (                             -- P2 TENANT. Metered use per month, for limits and billing.
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  metric       text NOT NULL CHECK (metric IN ('seats', 'ask_queries', 'searches', 'api_calls', 'ai_tokens', 'storage_bytes', 'exports', 'agent_runs', 'agent_cost')),
  period_start date NOT NULL,
  quantity     numeric NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, metric, period_start)
);

CREATE TABLE feature_flag (                             -- P2 PLATFORM
  key             text PRIMARY KEY,
  description     text,
  default_enabled boolean NOT NULL DEFAULT false
);

CREATE TABLE tenant_feature (                           -- P2 TENANT
  tenant_id   uuid NOT NULL REFERENCES tenant(id),
  feature_key text NOT NULL REFERENCES feature_flag(key),
  enabled     boolean NOT NULL,
  set_by      uuid REFERENCES app_user(id),
  set_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, feature_key)
);

-- ---------------------------------------------------------------------------
-- 17. The tenant's organisation: entities, licences, products, internal items
-- ---------------------------------------------------------------------------
CREATE TABLE org_unit (                                 -- P2 TENANT. KF sits in the insurer, the accounts in the bank.
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id),
  parent_id      uuid REFERENCES org_unit(id),
  kind           org_unit_kind NOT NULL,
  name           text NOT NULL,
  org_number     text,
  lei            text,
  country_code   char(2),
  entity_term_id uuid REFERENCES taxonomy_term(id),     -- ties a legal entity to the legal_entity scope term
  head_user_id   uuid REFERENCES app_user(id),
  active         boolean NOT NULL DEFAULT true
);
ALTER TABLE team ADD COLUMN org_unit_id uuid REFERENCES org_unit(id);

CREATE TABLE licence (                                  -- P2 TENANT. Licences held decide which rules can apply at all.
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id),
  org_unit_id      uuid NOT NULL REFERENCES org_unit(id),
  authority_id     uuid REFERENCES authority(id),
  licence_type     text NOT NULL,                       -- "Securities business, LVM 2 kap.", "Insurance distribution"
  reference        text,
  granted_on       date,
  withdrawn_on     date,
  service_term_ids uuid[] NOT NULL DEFAULT '{}',
  scope_note       text
);

CREATE TABLE tenant_product (                           -- P2 TENANT. "Which obligations hit this product" is the question a product team asks.
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenant(id),
  org_unit_id uuid REFERENCES org_unit(id),
  name        text NOT NULL,
  description text,
  status      text NOT NULL DEFAULT 'live' CHECK (status IN ('planned', 'live', 'retired')),
  launch_date date,
  owner_id    uuid REFERENCES app_user(id),
  UNIQUE (tenant_id, name)
);

CREATE TABLE tenant_product_term (                      -- P2 TENANT. A product's scope in the same terms as obligations.
  product_id uuid NOT NULL REFERENCES tenant_product(id) ON DELETE CASCADE,
  term_id    uuid NOT NULL REFERENCES taxonomy_term(id),
  tenant_id  uuid NOT NULL REFERENCES tenant(id),
  PRIMARY KEY (product_id, term_id)
);

CREATE TABLE internal_item (                            -- P2 TENANT. One register of policies, procedures, controls, processes, systems.
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenant(id),
  kind            link_kind NOT NULL,
  name            text NOT NULL,
  reference       text,
  url             text,
  owner_id        uuid REFERENCES app_user(id),
  org_unit_id     uuid REFERENCES org_unit(id),
  external_system text,                                 -- the GRC or document system that masters it
  external_ref    text,
  last_reviewed_on date,
  next_review_on  date,
  active          boolean NOT NULL DEFAULT true,
  UNIQUE (tenant_id, kind, name)
);
ALTER TABLE internal_link ADD COLUMN internal_item_id uuid REFERENCES internal_item(id);  -- label stays for ad hoc links

CREATE TABLE custom_field_def (                         -- P3 TENANT. Values live in the custom jsonb of the record.
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenant(id),
  applies_to subject_type NOT NULL,
  key        text NOT NULL,
  label      text NOT NULL,
  field_type text NOT NULL CHECK (field_type IN ('text', 'number', 'date', 'select', 'user')),
  options    jsonb,
  required   boolean NOT NULL DEFAULT false,
  sort_order int NOT NULL DEFAULT 0,
  UNIQUE (tenant_id, applies_to, key)
);
ALTER TABLE tenant_obligation ADD COLUMN custom jsonb NOT NULL DEFAULT '{}';
ALTER TABLE change_case       ADD COLUMN custom jsonb NOT NULL DEFAULT '{}';

CREATE TABLE tenant_tag (                               -- P2 TENANT
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  name      text NOT NULL,
  UNIQUE (tenant_id, name)
);

CREATE TABLE tagging (                                  -- P2 TENANT
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  tag_id       uuid NOT NULL REFERENCES tenant_tag(id) ON DELETE CASCADE,
  subject_type subject_type NOT NULL,
  subject_id   uuid NOT NULL,
  PRIMARY KEY (tag_id, subject_type, subject_id)
);

CREATE TABLE footprint_history (                        -- P1 TENANT. "What was our footprint on that date" without parsing the audit log.
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id  uuid NOT NULL REFERENCES tenant(id),
  term_id    uuid NOT NULL REFERENCES taxonomy_term(id),
  action     text NOT NULL CHECK (action IN ('added', 'removed')),
  changed_by uuid REFERENCES app_user(id),
  changed_at timestamptz NOT NULL DEFAULT now(),
  reason     text
);

-- ---------------------------------------------------------------------------
-- 18. Library depth
-- ---------------------------------------------------------------------------
CREATE TABLE jurisdiction (                             -- P1 LIBRARY
  code        text PRIMARY KEY,                         -- "EU", "SE"
  name        text NOT NULL,
  parent_code text REFERENCES jurisdiction(code),
  kind        text NOT NULL CHECK (kind IN ('supranational', 'country'))
);
ALTER TABLE authority  ADD CONSTRAINT authority_jurisdiction_fk  FOREIGN KEY (jurisdiction) REFERENCES jurisdiction(code);
ALTER TABLE instrument ADD CONSTRAINT instrument_jurisdiction_fk FOREIGN KEY (jurisdiction) REFERENCES jurisdiction(code);

CREATE TABLE initiative (                               -- P1 LIBRARY. Retail Investment Strategy, T+1, the AML package: one reform, many changes.
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stable_key        text NOT NULL UNIQUE,
  name              text NOT NULL,
  description       text,
  status            initiative_status NOT NULL,
  lead_authority_id uuid REFERENCES authority(id),
  url               text
);
ALTER TABLE regulatory_change ADD COLUMN initiative_id uuid REFERENCES initiative(id);

CREATE TABLE initiative_instrument (                    -- P1 LIBRARY. Which instruments a reform creates, amends or repeals.
  initiative_id uuid NOT NULL REFERENCES initiative(id),
  instrument_id uuid NOT NULL REFERENCES instrument(id),
  effect        text NOT NULL CHECK (effect IN ('creates', 'amends', 'repeals')),
  PRIMARY KEY (initiative_id, instrument_id)
);

CREATE TABLE change_relation (                          -- P1 LIBRARY. Merges and sequences between changes.
  change_id         uuid NOT NULL REFERENCES regulatory_change(id),
  related_change_id uuid NOT NULL REFERENCES regulatory_change(id),
  relation          text NOT NULL CHECK (relation IN ('merged_into', 'follows', 'related')),
  PRIMARY KEY (change_id, related_change_id),
  CHECK (change_id <> related_change_id)
);

CREATE TABLE source_document (                          -- P1 LIBRARY. A fetched page with a stored snapshot. Pages move and vanish, proof should not.
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  url           text NOT NULL,
  title         text,
  publisher     text,
  authority_id  uuid REFERENCES authority(id),
  lang          text,
  published_on  date,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  content_hash  text NOT NULL,
  snapshot_key  text,                                   -- object in the bucket
  mime_type     text,
  agent_run_id  uuid REFERENCES agent_run(id),
  risk_flags    text[] NOT NULL DEFAULT '{}',
  UNIQUE (url, content_hash)
);
ALTER TABLE change_document   ADD COLUMN source_document_id uuid REFERENCES source_document(id);
ALTER TABLE provision_version ADD COLUMN source_document_id uuid REFERENCES source_document(id);

CREATE TABLE citation (                                 -- P1 LIBRARY. The source per field, kept on the live record and not only in the proposal.
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_type       subject_type NOT NULL,
  subject_id         uuid NOT NULL,
  field              text NOT NULL,                     -- "summary_en", "retention", "key_date"
  source_document_id uuid REFERENCES source_document(id),
  provision_id       uuid REFERENCES provision(id),
  locator            text,                              -- "Article 24(9a)", "p. 14"
  quote              text,
  proposal_id        uuid REFERENCES proposal(id),
  CHECK (source_document_id IS NOT NULL OR provision_id IS NOT NULL)
);
CREATE INDEX citation_subject_idx ON citation (subject_type, subject_id);

CREATE TABLE verification (                             -- P1 LIBRARY. Every re-verification, not only the latest date.
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_type       subject_type NOT NULL,
  subject_id         uuid NOT NULL,
  verified_at        timestamptz NOT NULL DEFAULT now(),
  origin             origin_type NOT NULL,
  user_id            uuid REFERENCES app_user(id),
  agent_run_id       uuid REFERENCES agent_run(id),
  outcome            verification_outcome NOT NULL,
  source_document_id uuid REFERENCES source_document(id),
  proposal_id        uuid REFERENCES proposal(id),      -- set when the outcome was change_found
  note               text
);
CREATE INDEX verification_subject_idx ON verification (subject_type, subject_id, verified_at DESC);

CREATE TABLE glossary_term (                            -- P1 LIBRARY. Legal terms in both languages. Replaces the prototype's hard-coded synonym table.
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  term_sv       text,
  term_en       text,
  definition_sv text,
  definition_en text,
  synonyms      text[] NOT NULL DEFAULT '{}',           -- "nudging", "robo", "fees": used for query expansion
  provision_id  uuid REFERENCES provision(id),          -- where the law defines it
  active        boolean NOT NULL DEFAULT true,
  CHECK (term_sv IS NOT NULL OR term_en IS NOT NULL)
);

CREATE TABLE obligation_requirement (                   -- P2 LIBRARY. What the duty breaks down into. Optional, only where depth pays.
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  obligation_id uuid NOT NULL REFERENCES obligation(id),
  ordinal       int NOT NULL,
  text_en       text NOT NULL,
  text_sv       text NOT NULL,
  provision_id  uuid REFERENCES provision(id),
  status        record_status NOT NULL DEFAULT 'active',
  UNIQUE (obligation_id, ordinal)
);

CREATE TABLE obligation_exemption (                     -- P2 LIBRARY. Exemptions, thresholds and conditions.
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  obligation_id  uuid NOT NULL REFERENCES obligation(id),
  description_en text NOT NULL,
  description_sv text NOT NULL,
  condition      jsonb,                                 -- machine readable where possible: term ids, thresholds
  provision_id   uuid REFERENCES provision(id)
);

CREATE TABLE recurring_duty (                           -- P2 LIBRARY. Dated duties the law repeats: annual control statements, yearly cost reports.
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  obligation_id          uuid NOT NULL REFERENCES obligation(id),
  title                  text NOT NULL,
  recurrence_rule        text NOT NULL,                 -- RFC 5545 RRULE
  due_rule_note          text,                          -- "31 January after the income year"
  recipient_authority_id uuid REFERENCES authority(id),
  lead_days              int NOT NULL DEFAULT 30,
  status                 record_status NOT NULL DEFAULT 'active'
);

CREATE TABLE enforcement_decision (                     -- P1 LIBRARY. Structured facts for changes of type enforcement.
  change_id              uuid PRIMARY KEY REFERENCES regulatory_change(id) ON DELETE CASCADE,
  authority_id           uuid REFERENCES authority(id),
  firm_name              text NOT NULL,
  firm_type              text,
  decision_date          date,
  sanction               sanction_type NOT NULL,
  amount                 numeric(14, 2),
  currency               char(3),
  breached_provision_ids uuid[] NOT NULL DEFAULT '{}',
  appealed               boolean,
  outcome_note           text
);

CREATE TABLE consultation (                             -- P1 LIBRARY. Structured facts for changes of type consultation.
  change_id         uuid PRIMARY KEY REFERENCES regulatory_change(id) ON DELETE CASCADE,
  opens_on          date,
  closes_on         date,
  response_url      text,
  reference         text,
  outcome_change_id uuid REFERENCES regulatory_change(id)
);

CREATE TABLE newsletter_issue (                         -- P2 LIBRARY. The newsletters as one more output of the same data.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id     uuid NOT NULL REFERENCES agent(id),
  agent_run_id uuid REFERENCES agent_run(id),
  iso_week     text NOT NULL,                           -- "2026-W38"
  title        text NOT NULL,
  repo_path    text NOT NULL,
  sent_at      timestamptz,
  UNIQUE (agent_id, iso_week)
);

CREATE TABLE newsletter_item (                          -- P2 LIBRARY
  issue_id  uuid NOT NULL REFERENCES newsletter_issue(id) ON DELETE CASCADE,
  change_id uuid NOT NULL REFERENCES regulatory_change(id),
  rank      int NOT NULL,
  verdict   text,
  PRIMARY KEY (issue_id, change_id)
);

CREATE TABLE prompt_template (                          -- P2 LIBRARY. Which instruction produced which output.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id     uuid REFERENCES agent(id),
  purpose      ai_purpose,
  version      text NOT NULL,
  content_hash text NOT NULL,
  body         text NOT NULL,
  active_from  timestamptz NOT NULL DEFAULT now(),
  active_to    timestamptz
);
ALTER TABLE ai_generation
  ADD COLUMN prompt_template_id uuid REFERENCES prompt_template(id),
  ADD COLUMN tokens_in  int,
  ADD COLUMN tokens_out int,
  ADD COLUMN cost       numeric(10, 4),
  ADD COLUMN latency_ms int;
ALTER TABLE agent_run
  ADD COLUMN prompt_template_id uuid REFERENCES prompt_template(id),
  ADD COLUMN tokens_in    bigint,
  ADD COLUMN tokens_out   bigint,
  ADD COLUMN cost         numeric(10, 4),
  ADD COLUMN search_count int;
ALTER TABLE proposal
  ADD COLUMN rejection_code   text CHECK (rejection_code IN ('wrong_fact', 'wrong_scope', 'bad_source', 'duplicate', 'not_relevant', 'poor_wording', 'other')),
  ADD COLUMN review_decisions jsonb;                    -- per field: accepted, edited, rejected

-- ---------------------------------------------------------------------------
-- 19. Tenant compliance depth
-- ---------------------------------------------------------------------------
CREATE TABLE tenant_obligation_scope (                  -- P2 TENANT. Applicability and status per legal entity or product, where they differ.
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  tenant_obligation_id uuid NOT NULL REFERENCES tenant_obligation(id),
  org_unit_id          uuid REFERENCES org_unit(id),
  product_id           uuid REFERENCES tenant_product(id),
  applicability        applicability NOT NULL,
  compliance_status    compliance_status NOT NULL DEFAULT 'not_assessed',
  status_note          text,
  owner_id             uuid REFERENCES app_user(id),
  CHECK (org_unit_id IS NOT NULL OR product_id IS NOT NULL),
  UNIQUE NULLS NOT DISTINCT (tenant_obligation_id, org_unit_id, product_id)
);

CREATE TABLE compliance_assessment (                    -- P2 TENANT. History of every status assessment. tenant_obligation holds only the current one.
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  tenant_obligation_id uuid NOT NULL REFERENCES tenant_obligation(id),
  scope_id             uuid REFERENCES tenant_obligation_scope(id),
  assessed_at          timestamptz NOT NULL DEFAULT now(),
  assessed_by          uuid NOT NULL REFERENCES app_user(id),
  method               assessment_method NOT NULL DEFAULT 'self_assessment',
  status               compliance_status NOT NULL,
  risk_rating          risk_rating,
  likelihood           smallint CHECK (likelihood BETWEEN 1 AND 5),
  impact               smallint CHECK (impact BETWEEN 1 AND 5),
  rationale            text NOT NULL,
  next_review_date     date,
  approved_by          uuid REFERENCES app_user(id)
);
CREATE INDEX compliance_assessment_idx ON compliance_assessment (tenant_obligation_id, assessed_at DESC);

CREATE TABLE requirement_status (                       -- P2 TENANT
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  tenant_obligation_id uuid NOT NULL REFERENCES tenant_obligation(id),
  requirement_id       uuid NOT NULL REFERENCES obligation_requirement(id),
  status               compliance_status NOT NULL DEFAULT 'not_assessed',
  note                 text,
  updated_by           uuid REFERENCES app_user(id),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_obligation_id, requirement_id)
);

CREATE TABLE gap (                                      -- P2 TENANT. A gap is a record with an owner and a date, not a note on a status.
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  tenant_obligation_id uuid NOT NULL REFERENCES tenant_obligation(id),
  requirement_id       uuid REFERENCES obligation_requirement(id),
  org_unit_id          uuid REFERENCES org_unit(id),
  case_id              uuid REFERENCES change_case(id),
  title                text NOT NULL,
  description          text,
  severity             risk_rating NOT NULL,
  source               gap_source NOT NULL,
  identified_at        timestamptz NOT NULL DEFAULT now(),
  identified_by        uuid NOT NULL REFERENCES app_user(id),
  owner_id             uuid REFERENCES app_user(id),
  target_date          date,
  status               gap_status NOT NULL DEFAULT 'open',
  acceptance_reason    text,
  accepted_by          uuid REFERENCES app_user(id),
  closed_by            uuid REFERENCES app_user(id),
  closed_at            timestamptz,
  CHECK (status <> 'accepted' OR (acceptance_reason IS NOT NULL AND accepted_by IS NOT NULL)),
  CHECK (accepted_by IS NULL OR accepted_by <> identified_by)
);
CREATE INDEX gap_open_idx ON gap (tenant_id, target_date) WHERE status IN ('open', 'remediating');

CREATE TABLE interpretation (                           -- P2 TENANT. "How we read this rule", versioned and approved. Internal legal judgement.
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  tenant_obligation_id uuid NOT NULL REFERENCES tenant_obligation(id),
  version_no           int NOT NULL,
  body                 text NOT NULL,
  author_id            uuid NOT NULL REFERENCES app_user(id),
  status               text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'superseded')),
  approved_by          uuid REFERENCES app_user(id),
  approved_at          timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_obligation_id, version_no),
  CHECK (approved_by IS NULL OR approved_by <> author_id)
);

CREATE TABLE duty_occurrence (                          -- P2 TENANT. One dated instance of a recurring duty.
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id),
  recurring_duty_id    uuid NOT NULL REFERENCES recurring_duty(id),
  tenant_obligation_id uuid NOT NULL REFERENCES tenant_obligation(id),
  org_unit_id          uuid REFERENCES org_unit(id),
  due_date             date NOT NULL,
  status               duty_status NOT NULL DEFAULT 'upcoming',
  owner_id             uuid REFERENCES app_user(id),
  completed_at         timestamptz,
  completed_by         uuid REFERENCES app_user(id),
  note                 text,
  UNIQUE NULLS NOT DISTINCT (recurring_duty_id, tenant_id, org_unit_id, due_date)
);

-- Actions and evidence now also hang on gaps and duty occurrences.
ALTER TABLE action ALTER COLUMN case_id DROP NOT NULL;
ALTER TABLE action
  ADD COLUMN gap_id             uuid REFERENCES gap(id),
  ADD COLUMN duty_occurrence_id uuid REFERENCES duty_occurrence(id),
  ADD CONSTRAINT action_parent_check CHECK (num_nonnulls(case_id, gap_id, duty_occurrence_id) = 1);
ALTER TABLE evidence DROP CONSTRAINT evidence_check;
ALTER TABLE evidence
  ADD COLUMN gap_id             uuid REFERENCES gap(id),
  ADD COLUMN duty_occurrence_id uuid REFERENCES duty_occurrence(id),
  ADD COLUMN valid_until        date,
  ADD COLUMN reviewed_by        uuid REFERENCES app_user(id),
  ADD CONSTRAINT evidence_parent_check CHECK (num_nonnulls(case_id, tenant_obligation_id, gap_id, duty_occurrence_id) >= 1);

CREATE TABLE consultation_response (                    -- P3 TENANT
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  change_id    uuid NOT NULL REFERENCES consultation(change_id),
  decision     text NOT NULL CHECK (decision IN ('respond', 'via_industry_body', 'no_response')),
  owner_id     uuid REFERENCES app_user(id),
  submitted_on date,
  document_key text,
  note         text,
  UNIQUE (tenant_id, change_id)
);

CREATE TABLE assessment_impact (                        -- P2 TENANT. Impact per obligation, entity and product instead of one text box.
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenant(id),
  assessment_id uuid NOT NULL REFERENCES impact_assessment(id) ON DELETE CASCADE,
  obligation_id uuid REFERENCES obligation(id),
  org_unit_id   uuid REFERENCES org_unit(id),
  product_id    uuid REFERENCES tenant_product(id),
  internal_item_id uuid REFERENCES internal_item(id),   -- the policy, process or system that must change
  level         impact_level NOT NULL,
  description   text
);

CREATE TABLE assessment_contribution (                  -- P2 TENANT. Legal, product and tech each write their part of the same record.
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id),
  assessment_id  uuid NOT NULL REFERENCES impact_assessment(id) ON DELETE CASCADE,
  area           text NOT NULL,
  contributor_id uuid NOT NULL REFERENCES app_user(id),
  requested_by   uuid REFERENCES app_user(id),
  due_date       date,
  body           text,
  submitted_at   timestamptz
);

CREATE TABLE case_transition (                          -- P2 TENANT. Time in each stage, without parsing audit summaries.
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES tenant(id),
  case_id     uuid NOT NULL REFERENCES change_case(id),
  from_status case_status,
  to_status   case_status NOT NULL,
  at          timestamptz NOT NULL DEFAULT now(),
  by_user     uuid REFERENCES app_user(id),
  note        text
);
CREATE INDEX case_transition_idx ON case_transition (case_id, at);
ALTER TABLE change_case ADD COLUMN triage_due_at timestamptz;  -- from the tenant's triage target, drives escalation

CREATE TABLE follow (                                   -- P2 TENANT. A personal watchlist: an instrument, obligation, initiative or theme term.
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  user_id      uuid NOT NULL REFERENCES app_user(id),
  subject_type subject_type NOT NULL,
  subject_id   uuid NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, user_id, subject_type, subject_id)
);

CREATE TABLE user_item_state (                          -- P2 TENANT. Read, bookmarked and snoozed per person.
  tenant_id     uuid NOT NULL REFERENCES tenant(id),
  user_id       uuid NOT NULL REFERENCES app_user(id),
  subject_type  subject_type NOT NULL,
  subject_id    uuid NOT NULL,
  first_seen_at timestamptz,
  last_seen_at  timestamptz,
  bookmarked    boolean NOT NULL DEFAULT false,
  snoozed_until date,
  PRIMARY KEY (tenant_id, user_id, subject_type, subject_id)
);

-- ---------------------------------------------------------------------------
-- 20. Feedback, analytics, delivery logs
-- First-party and server-side, tied to signed-in users. No third-party tracker and nothing extra stored in the browser.
-- ---------------------------------------------------------------------------
CREATE TABLE usage_event (                              -- P1 TENANT. What people actually use. Keep 13 months, then aggregate.
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  user_id      uuid REFERENCES app_user(id),
  session_id   uuid REFERENCES user_session(id),
  occurred_at  timestamptz NOT NULL DEFAULT now(),
  event        text NOT NULL,                           -- "obligation.viewed", "diff.opened", "briefing.opened", "export.created"
  subject_type subject_type,
  subject_id   uuid,
  properties   jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX usage_event_time_idx ON usage_event USING brin (occurred_at);
CREATE INDEX usage_event_tenant_idx ON usage_event (tenant_id, event, occurred_at DESC);

CREATE TABLE search_query_log (                         -- P1 TENANT. The raw material for the evaluation set and for search tuning.
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id            uuid REFERENCES tenant(id),
  user_id              uuid REFERENCES app_user(id),
  api_key_id           uuid REFERENCES api_key(id),
  occurred_at          timestamptz NOT NULL DEFAULT now(),
  mode                 text NOT NULL CHECK (mode IN ('search', 'ask', 'similar')),
  query                text NOT NULL,
  lang                 text,
  as_of                date,
  filters              jsonb NOT NULL DEFAULT '{}',
  result_count         int NOT NULL,
  top_results          jsonb NOT NULL DEFAULT '[]',     -- ids, match kind and scores of the first ten
  latency_ms           int,
  clicked_subject_type subject_type,
  clicked_subject_id   uuid,
  clicked_rank         int,
  ai_generation_id     uuid REFERENCES ai_generation(id)
);
CREATE INDEX search_query_zero_idx ON search_query_log (occurred_at DESC) WHERE result_count = 0;

CREATE TABLE content_feedback (                         -- P1 TENANT. Thumbs on content: So what, summaries, answers, search hits, briefing items.
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id),
  user_id          uuid NOT NULL REFERENCES app_user(id),
  subject_type     subject_type NOT NULL,
  subject_id       uuid NOT NULL,
  ai_generation_id uuid REFERENCES ai_generation(id),
  aspect           text NOT NULL CHECK (aspect IN ('so_what', 'summary', 'answer', 'search_result', 'obligation_text', 'translation', 'briefing', 'link_suggestion')),
  rating           smallint NOT NULL CHECK (rating IN (-1, 1)),
  reason_code      text CHECK (reason_code IN ('inaccurate', 'incomplete', 'not_relevant', 'unclear', 'outdated', 'other')),
  comment          text,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feedback (                                 -- P1 TENANT. Product feedback: bugs, ideas, questions, NPS.
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenant(id),
  user_id    uuid NOT NULL REFERENCES app_user(id),
  kind       feedback_kind NOT NULL,
  score      smallint CHECK (score BETWEEN 0 AND 10),   -- NPS
  body       text,
  page       text,
  status     feedback_status NOT NULL DEFAULT 'new',
  response   text,
  handled_by uuid REFERENCES app_user(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tenant_metric_daily (                      -- P2 TENANT. Status is overwritten, so trends need a daily snapshot.
  tenant_id              uuid NOT NULL REFERENCES tenant(id),
  day                    date NOT NULL,
  obligations_applicable int NOT NULL,
  compliant              int NOT NULL,
  partly_compliant       int NOT NULL,
  gap                    int NOT NULL,
  not_assessed           int NOT NULL,
  open_gaps              int NOT NULL,
  open_cases             int NOT NULL,
  cases_in_triage        int NOT NULL,
  overdue_actions        int NOT NULL,
  overdue_duties         int NOT NULL,
  unconfirmed_ai         int NOT NULL,
  median_hours_to_triage numeric,
  active_users           int NOT NULL,
  PRIMARY KEY (tenant_id, day)
);

CREATE TABLE email_message (                            -- P2 TENANT. Proof that a reminder or escalation was actually sent.
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenant(id),
  user_id             uuid REFERENCES app_user(id),
  to_email            citext NOT NULL,
  template            text NOT NULL,                    -- "weekly_digest", "action_due", "escalation", "invitation"
  subject             text NOT NULL,
  subject_type        subject_type,
  subject_id          uuid,
  status              email_status NOT NULL DEFAULT 'queued',
  provider_message_id text,
  queued_at           timestamptz NOT NULL DEFAULT now(),
  sent_at             timestamptz,
  error               text
);

CREATE TABLE job_run (                                  -- P1 PLATFORM. Worker jobs: embeddings, reminders, snapshots, retention.
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind        text NOT NULL,
  tenant_id   uuid REFERENCES tenant(id),
  started_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  status      job_status NOT NULL DEFAULT 'running',
  stats       jsonb NOT NULL DEFAULT '{}',
  error       text
);

CREATE TABLE idempotency_record (                       -- P1 PLATFORM. Backs the Idempotency-Key header for every agent write.
  key             text NOT NULL,
  api_key_id      uuid NOT NULL REFERENCES api_key(id),
  request_hash    text NOT NULL,
  response_status int NOT NULL,
  response_body   jsonb,
  created_at      timestamptz NOT NULL DEFAULT now(),
  expires_at      timestamptz NOT NULL,
  PRIMARY KEY (api_key_id, key)
);

-- Agent quality from the review queue: how often is each agent and model right, and how fast do people review.
CREATE VIEW v_agent_quality AS
  SELECT a.name AS agent, p.model, p.kind,
         count(*)                                              AS proposals,
         count(*) FILTER (WHERE p.status = 'approved')         AS approved,
         count(*) FILTER (WHERE p.status = 'rejected')         AS rejected,
         round(count(*) FILTER (WHERE p.status = 'approved')::numeric
               / NULLIF(count(*) FILTER (WHERE p.status IN ('approved', 'rejected')), 0), 3) AS acceptance_rate,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM p.reviewed_at - p.created_at) / 3600) AS median_hours_to_review
  FROM proposal p
  JOIN agent_run r ON r.id = p.agent_run_id
  JOIN agent a ON a.id = r.agent_id
  GROUP BY a.name, p.model, p.kind;

-- Roadmap now also carries gap target dates and recurring duties, and actions that hang on a gap.
CREATE OR REPLACE VIEW v_roadmap_item AS
  SELECT cc.tenant_id, 'regulatory'::text AS kind, 'change_date'::text AS item_type,
         cc.id AS case_id, NULL::uuid AS obligation_id, c.key_date AS item_date,
         c.key_date_label || ': ' || c.title AS label, cc.owner_id
  FROM change_case cc JOIN regulatory_change c ON c.id = cc.change_id
  WHERE cc.status NOT IN ('closed', 'dismissed') AND cc.footprint_match AND c.key_date >= current_date
  UNION ALL
  SELECT cc.tenant_id, 'internal', 'internal_deadline', cc.id, NULL, ia.internal_deadline,
         'Internal deadline: ' || c.title, cc.owner_id
  FROM impact_assessment ia
  JOIN change_case cc ON cc.id = ia.case_id
  JOIN regulatory_change c ON c.id = cc.change_id
  WHERE ia.saved AND ia.internal_deadline >= current_date AND cc.status NOT IN ('closed', 'dismissed')
  UNION ALL
  SELECT a.tenant_id, 'internal', 'action_due', a.case_id, NULL, a.due_date,
         'Action: ' || a.title, a.owner_id
  FROM action a LEFT JOIN change_case cc ON cc.id = a.case_id
  WHERE a.done_at IS NULL AND a.due_date >= current_date AND (cc.id IS NULL OR cc.status NOT IN ('closed', 'dismissed'))
  UNION ALL
  SELECT tob.tenant_id, 'internal', 'review_due', NULL, tob.obligation_id, tob.next_review_date,
         'Review: ' || o.title, tob.first_line_owner
  FROM tenant_obligation tob JOIN obligation o ON o.id = tob.obligation_id
  WHERE tob.applicability = 'applies' AND tob.compliance_status <> 'compliant'
    AND tob.next_review_date >= current_date
  UNION ALL
  SELECT g.tenant_id, 'internal', 'gap_target', g.case_id, tob.obligation_id, g.target_date,
         'Close gap: ' || g.title, g.owner_id
  FROM gap g JOIN tenant_obligation tob ON tob.id = g.tenant_obligation_id
  WHERE g.status IN ('open', 'remediating') AND g.target_date >= current_date
  UNION ALL
  SELECT d.tenant_id, 'regulatory', 'duty_due', NULL, tob.obligation_id, d.due_date,
         rd.title, d.owner_id
  FROM duty_occurrence d
  JOIN recurring_duty rd ON rd.id = d.recurring_duty_id
  JOIN tenant_obligation tob ON tob.id = d.tenant_obligation_id
  WHERE d.status IN ('upcoming', 'in_progress') AND d.due_date >= current_date;

-- ===========================================================================
-- PART 3 (v0.3): tenant-scoped agents and tenant-private library records
-- Agent definitions are platform-owned and versioned. A tenant switches agents on,
-- sets cadence, scope and budget, and can run, pause or interrupt them. The app is
-- the scheduler of record. The runtime (Claude Managed Agents, Agent SDK) is an executor.
-- ===========================================================================
ALTER TABLE agent
  ADD COLUMN scope               text NOT NULL DEFAULT 'platform' CHECK (scope IN ('platform', 'tenant')),
  ADD COLUMN tenant_configurable boolean NOT NULL DEFAULT false,
  ADD COLUMN runtime             text NOT NULL DEFAULT 'managed_agents' CHECK (runtime IN ('managed_agents', 'agent_sdk', 'routine')),
  ADD COLUMN default_cadence     text NOT NULL DEFAULT 'weekly' CHECK (default_cadence IN ('daily', 'weekly', 'monthly', 'manual')),
  ADD COLUMN writes_to           text NOT NULL DEFAULT 'library' CHECK (writes_to IN ('library', 'tenant', 'both'));

CREATE TABLE agent_version (                            -- P1 LIBRARY. Tenants never edit instructions or tools, they get a version.
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id           uuid NOT NULL REFERENCES agent(id),
  version_no         int NOT NULL,
  model              text NOT NULL,
  prompt_template_id uuid REFERENCES prompt_template(id),
  tools              jsonb NOT NULL DEFAULT '[]',
  external_agent_id  text,                              -- id of the agent definition in the runtime
  change_note        text,
  published_by       uuid REFERENCES app_user(id),
  published_at       timestamptz NOT NULL DEFAULT now(),
  retired_at         timestamptz,
  UNIQUE (agent_id, version_no)
);

CREATE TABLE tenant_agent (                             -- P2 TENANT. What the tenant admin controls.
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               uuid NOT NULL REFERENCES tenant(id),
  agent_id                uuid NOT NULL REFERENCES agent(id),
  enabled                 boolean NOT NULL DEFAULT false,
  cadence                 text NOT NULL DEFAULT 'weekly' CHECK (cadence IN ('daily', 'weekly', 'monthly', 'manual')),
  run_weekday             smallint CHECK (run_weekday BETWEEN 1 AND 7),
  run_hour                smallint CHECK (run_hour BETWEEN 0 AND 23),
  next_run_at             timestamptz,
  scope                   jsonb NOT NULL DEFAULT '{}',  -- term ids, topics, languages. Empty = follow the footprint.
  monthly_budget          numeric(10, 2),
  currency                char(3) NOT NULL DEFAULT 'EUR',
  pinned_version_id       uuid REFERENCES agent_version(id),  -- NULL = latest published
  environment             text NOT NULL DEFAULT 'anthropic_cloud' CHECK (environment IN ('anthropic_cloud', 'self_hosted')),
  external_environment_id text,
  paused_at               timestamptz,
  paused_by               uuid REFERENCES app_user(id),
  updated_by              uuid REFERENCES app_user(id),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, agent_id)
);
CREATE INDEX tenant_agent_due_idx ON tenant_agent (next_run_at) WHERE enabled AND paused_at IS NULL;

CREATE TABLE research_request (                         -- P2 TENANT. "Check this source now", "research this topic". Capped per plan.
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id),
  tenant_agent_id uuid REFERENCES tenant_agent(id),
  requested_by   uuid NOT NULL REFERENCES app_user(id),
  kind           text NOT NULL CHECK (kind IN ('run_now', 'check_source', 'check_url', 'research_topic', 'reverify')),
  topic          text,
  source_id      uuid REFERENCES source(id),
  url            text,
  status         text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed', 'rejected', 'cancelled')),
  result_summary text,
  changes_found  int,
  created_at     timestamptz NOT NULL DEFAULT now(),
  completed_at   timestamptz
);

CREATE TABLE source_request (                           -- P2 TENANT. A tenant asks for a source: private to them, or shared after editor approval.
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  requested_by uuid NOT NULL REFERENCES app_user(id),
  name         text NOT NULL,
  url          text NOT NULL,
  reason       text,
  visibility   text NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'shared')),
  status       approval_status NOT NULL DEFAULT 'pending',
  decided_by   uuid REFERENCES app_user(id),
  decided_at   timestamptz,
  source_id    uuid REFERENCES source(id),
  created_at   timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE agent_run
  ADD COLUMN tenant_id           uuid REFERENCES tenant(id),        -- NULL = platform run for the shared library
  ADD COLUMN tenant_agent_id     uuid REFERENCES tenant_agent(id),
  ADD COLUMN agent_version_id    uuid REFERENCES agent_version(id),
  ADD COLUMN trigger             text NOT NULL DEFAULT 'schedule' CHECK (trigger IN ('schedule', 'manual', 'request', 'api')),
  ADD COLUMN research_request_id uuid REFERENCES research_request(id),
  ADD COLUMN requested_by        uuid REFERENCES app_user(id),
  ADD COLUMN external_session_id text,
  ADD COLUMN budget_limit        numeric(10, 2),
  ADD COLUMN changes_found       int,
  ADD COLUMN proposals_made      int,
  ADD COLUMN interrupted_at      timestamptz,
  ADD COLUMN interrupted_by      uuid REFERENCES app_user(id);
CREATE INDEX agent_run_tenant_idx ON agent_run (tenant_id, started_at DESC);

-- Tenant-private library records: a source only one tenant watches, and what is found there.
ALTER TABLE source            ADD COLUMN owner_tenant_id uuid REFERENCES tenant(id);
ALTER TABLE regulatory_change ADD COLUMN owner_tenant_id uuid REFERENCES tenant(id);
ALTER TABLE instrument        ADD COLUMN owner_tenant_id uuid REFERENCES tenant(id);
ALTER TABLE obligation        ADD COLUMN owner_tenant_id uuid REFERENCES tenant(id);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['source', 'regulatory_change', 'instrument', 'obligation'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY shared_or_mine ON %I USING (owner_tenant_id IS NULL OR owner_tenant_id = current_setting(''app.tenant_id'')::uuid)', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 21. Housekeeping: updated_at and row-level security, applied by loop to stay reusable
-- ---------------------------------------------------------------------------
CREATE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['instrument', 'obligation', 'regulatory_change', 'tenant_obligation', 'change_case'] LOOP
    EXECUTE format('CREATE TRIGGER %I_touch BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION touch_updated_at()', t, t);
  END LOOP;
END $$;

-- The API sets app.tenant_id per request: SET LOCAL app.tenant_id = '<uuid>'.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'membership', 'footprint_term', 'saved_search', 'tenant_obligation', 'applicability_request',
    'internal_link', 'attestation', 'waiver', 'change_case', 'impact_assessment', 'action', 'evidence',
    'comment', 'briefing', 'briefing_item', 'calendar_feed', 'notification', 'webhook_endpoint',
    'webhook_delivery', 'ticket_integration', 'export_job', 'import_job',
    'tenant_domain', 'identity_provider', 'invitation', 'team', 'team_member', 'support_access', 'legal_hold', 'retention_run',
    'tenant_subscription', 'invoice', 'usage_record', 'tenant_feature', 'org_unit', 'licence', 'tenant_product', 'tenant_product_term',
    'internal_item', 'custom_field_def', 'tenant_tag', 'tagging', 'footprint_history', 'tenant_obligation_scope', 'compliance_assessment',
    'requirement_status', 'gap', 'interpretation', 'duty_occurrence', 'consultation_response', 'assessment_impact', 'assessment_contribution',
    'case_transition', 'follow', 'user_item_state', 'usage_event', 'content_feedback', 'feedback', 'tenant_metric_daily', 'email_message', 'tenant_agent', 'research_request', 'source_request'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'')::uuid)', t);
  END LOOP;
END $$;

-- Tables with a nullable tenant_id: library rows are visible to everyone, tenant rows only to their tenant.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['audit_event', 'ai_generation', 'problem_report', 'outbox_event', 'api_key', 'user_session', 'login_event', 'legal_acceptance', 'data_subject_request', 'search_query_log', 'job_run', 'agent_run'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant_or_library ON %I USING (tenant_id IS NULL OR tenant_id = current_setting(''app.tenant_id'')::uuid)', t);
  END LOOP;
END $$;

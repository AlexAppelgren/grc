# Input deltas: where the build departs from schema.sql and openapi.yaml

The inputs were designed before the decisions below. Apply these when
modelling. When the build finds another difference, fix it or add a row here
with the reason.

## 1. Vocabularies replace enums (PRD VOC, playbook 15)

Keep as enums in code (tier 1, kinds): `actor_type`, `origin_type`,
`run_status`, `job_status`, `check_status`, `proposal_kind`,
`proposal_status`, `approval_status`, `applicability`, `assessment_applies`,
`close_reason`, `evidence_kind`, `subject_type`, `search_source`,
`ai_purpose`, `ai_status`, `report_status`, `export_kind`, `import_kind`,
`date_precision`, `record_status`, `change_status`, `feed_filter`,
`ticket_provider`, `agent_kind`, and `case_status` reduced to its
**categories** (`new`, `assigned`, `assessing`, `implementing`, `signoff`,
`closed`, `dismissed`).

Become library vocabulary rows (tier 2): `instrument_level` (jurisdiction
neutral, with a `binding` default and a rank), `provision_kind` (per
jurisdiction, with a fixed structural kind), `change_type` (with a fixed
lifecycle kind: pre-adoption, adopted, in force, supervisory, recurring),
`duty_type`, `relation_type`, `source_kind`, `term_dimension` (with a
`restricts_footprint` flag), and `urgency` (fixed ordinal and tone, editable
label and SLA days). `obligation.tags` and `regulatory_change.flags` become
many-to-many links to tag rows, never `text[]`.

Become tenant vocabulary rows (tier 3): `tenant_role` and `platform_role`
(roles are rows composed of permissions, `membership.roles` links to them),
`compliance_status` and `risk_rating` (tenant scales mapped to a fixed
ordinal), `link_kind`, `effort_size`, case sub-statuses, dismissal and close
reasons, `impact_assessment.contributors` (teams or functions, never
`text[]`), tenant tags.

Every vocabulary row: immutable `key`, optional `kind`, labels per language,
`usage_note`, `sort_order`, `active`, `is_system`, `is_default`.
In the API every such field is `{key, kind, label}` on reads and `key` on
writes, never an OpenAPI `enum`.

## 2. Identity (PRD ID, playbook 4.2)

- Drop `app_user.external_subject` as the primary identity, `mfa_enrolled`,
  and the assumption "sign-in is delegated to an OIDC provider".
- Add `webauthn_credential` (credential id, public key, sign count,
  transports, AAGUID, backup eligible, backup state, nickname, created, last
  used), `auth_challenge` (registration, assertion, step-up, short-lived),
  `otp_code` (hashed, attempts, expiry, consumed), `step_up_assertion`,
  tenant `security_policy` (credential policy, session limits, IP allow-list).
- `invitation` stays. `login_event.method` becomes a kind with `email_code`,
  `passkey`, `api_key`, later `oidc` and `saml`. `identity_provider`,
  `tenant_domain` and SCIM move to R3.
- New endpoints under `/auth`: request code, verify code, passkey
  registration options and verify, passkey sign-in options and verify,
  step-up options and verify, refresh, sign-out. Under `/me`: passkeys and
  sessions. Under tenant admin: re-issue enrolment. `bearerAuth` in the
  contract means our own session token.

## 3. Nordic scope (PRD I18N, playbook 17)

- Replace `summary_sv`/`summary_en`, `text_sv`/`text_en`, `label_sv`/`label_en`
  and every `lang IN ('sv','en')` check with translation rows and a language
  table. `search_chunk.lang` references the language table, and its `tsv`
  uses the language's text search configuration.
- `instrument.jurisdiction` and `authority.jurisdiction` reference a
  jurisdiction table. Seed EU, SE, DK, NO, FI with their authorities.
- `app_user.locale` references the language table.

## 4. Errors, concurrency, files

- One error shape (playbook 4.4) with the codes already used by the contract
  plus `stale_write`, `unknown_key`, `step_up_required`.
- Add `version` to tenant-editable records (`tenant_obligation`,
  `impact_assessment`, `action`, `gap`, `change_case`, configuration rows)
  and require `If-Match` on their writes.
- Evidence and export downloads stream through the API. Remove `DownloadLink`
  and the presigned download operations. Upload may stay presigned if the
  scan and the hash still happen before the file is visible.

## 5. Tenancy and agents

- Version 0.3 of the schema already has `owner_tenant_id` on `source`,
  `regulatory_change`, `instrument` and `obligation` with a "shared or mine"
  policy. Keep it.
- RLS policies read `current_setting('app.tenant_id', true)` and tables are
  `FORCE ROW LEVEL SECURITY`. Two database roles (playbook 14).
- Version 0.3 already has the agent tables. Use its names: `agent`,
  `agent_version`, `tenant_agent` (cadence, next run, scope, monthly budget,
  pause, pinned version), `research_request`, `source_request`, and the
  trigger and requester columns on `agent_run`. Add only a `retag` kind to
  `research_request` and the batch proposal it produces (PRD AGT-05, PRO-04).
  `agent.runtime` and `tenant_agent.environment` become kinds in code.
- The proposal queue is reviewed in the platform console by `library_editor`.
  The prototype shows the tenant's compliance officer approving agent
  proposals. That is the one place the prototype is wrong.
- Footprint changes become a request with preview and second-person approval
  (`footprint_change_request`), replacing the direct `PUT /tenant/footprint`.

## 6. Audit

`audit_event` and `outbox_event` stay as designed. django-simple-history is
not used. Add `step_up_assertion_id` to `audit_event`.

## 7. Operations the build serves differently (contract drift, Phase 0)

`scripts/contract_drift.py` accepts an operation as explained only when a row
here names it with its backticked `METHOD /path`.

- `GET /health` is served at `/health/` on the site root, outside `/api/v1`,
  so a load balancer can probe it without the API prefix and without
  authentication. It answers 200 with every component named, or 503 naming
  the failing one (playbook 2.2).
- `GET /me` exists from Phase 0 with the principal only (`SessionAuth` and
  `EnrolmentAuth`, AC-ID2). Chunk 1 grows it to the designed shape.
- `GET /evidence/{evidenceId}/download` and `GET /exports/{exportId}/download`
  are the presigned-link operations section 4 removes; chunks 9 and 12
  replace them with streaming endpoints of the same paths that answer the
  file itself, permission-checked and audited (D-11).

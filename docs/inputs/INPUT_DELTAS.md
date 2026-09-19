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
  `EnrolmentAuth`, AC-ID2). Chunk 1 gives it the shape the chunk 1 brief specifies:
  `{user, tenant|null, roles[{key,kind,label}], permissions[], platformRoles[],
  enrolmentPending, passkeyCount, stepUpValidUntil}`. The designed `counts` and
  `lastVisitAt` wait for the home chunk (6), when there is a queue to count.
- `PATCH /me` takes `{name?, locale?}` (chunk 1 brief); the designed
  `notificationPrefs` move to the membership row and land with collaboration (chunk 10).
- `GET /tenant` and `PATCH /tenant` (TEN-01, chunk 1 brief): explicit columns instead of
  the designed `settings` blob and `region`. The response is `{id, name, slug, timezone,
  status, defaultLanguage{key,kind,label}, contentLanguages[...], onboarding{stepsDone,
  steps[{key,done}]}}`; the patch takes `{name?, timezone?, defaultLanguage?,
  contentLanguages?}` as keys. Reminder, escalation and retention settings land with
  the workflow policy (chunk 9) as columns of their own.
- `GET /tenant/members` answers a page `{items, total}` (playbook 10: every list
  paginates) of `{userId, email, name, status, roles[{key,kind,label}], title,
  lastSeenAt, passkeyCount, activeSessions}` rather than a bare array of the designed
  `Member`; `POST /tenant/members` takes `{email, roleKeys[], title?}` (roles are rows
  addressed by key, INPUT_DELTAS §1) and answers 201 with the invitation it created
  (`{id, email, roles, title, kind, status, createdAt, expiresAt}`), because a person
  becomes a member when the first passkey is stored (ID-02), not when invited;
  `PATCH /tenant/members/{userId}` takes `{roleKeys?, title?}` and answers the member.
- `GET /reference/languages` is not in the designed contract (it used a `Lang` enum,
  section 3): it answers `[{key, kind: null, label}]` from the language rows for the
  locale and tenant-language pickers, any session.
- `GET /tenant/api-keys` answers a page `{items, total}`; `POST /tenant/api-keys` takes
  `{name, scopes[], expiresAt?}` (no `agentId` until agents exist, chunk 5) and answers
  `{id, name, keyPrefix, scopes, createdAt, expiresAt, plainKey}` in one flat object
  instead of the designed `{key, secret}` pair (chunk 1 brief; `plainKey` is the only
  place the secret appears).
- `GET /evidence/{evidenceId}/download` and `GET /exports/{exportId}/download`
  are the presigned-link operations section 4 removes; chunks 9 and 12
  replace them with streaming endpoints of the same paths that answer the
  file itself, permission-checked and audited (D-11).

Chunk 2 (vocabularies, taxonomy, footprint, proposals), 2026-09-19:

- Reference reads are short fixed lists answered as a plain array, never a page:
  `GET /reference/languages` (above) and the new `GET /reference/jurisdictions`
  (`[{key, kind, label, parentKey, defaultLanguage{key,kind,label}}]`, I18N-01, any
  session). Every other list answers `{items, total}` (playbook 10).
- `GET /taxonomy/terms` (`listTerms`) answers `{items, total}` of `{id, key, kind: null,
  label, labels{<lang>: text}, dimension{key,kind,label}, parentKey, usageNote, sortOrder,
  active, isSystem, version}` instead of a bare array of the designed `Term`; filters
  `?dimension=<key>&includeRetired=true`. The designed `code`, `labelEn` and `labelSv` are
  the immutable `key` and translation rows (sections 1 and 3). Any session, or an API key
  with `library:read` (AGT-02).
- `POST /taxonomy/terms` (`createTerm`) and `PATCH /taxonomy/terms/{termId}` (`updateTerm`)
  answer 202 `{proposal}` instead of the designed 201 and 200 `Term`: a term is a library
  row and every library change is a proposal (VOC-07, PRO-01). The bodies are
  `{dimension, key?, labels{}, usageNote?, parent?}` and `{labels?, usageNote?, sortOrder?}`
  with `If-Match` carrying the term's `version`. `proposals.create` (tenant) or
  `library_vocab.manage` (console); an API key is 401 (AC-PRO1).
- `GET /tenant/footprint` (`getFootprint`) answers `{dimensions[{dimension{key,kind,label},
  restrictsFootprint, terms[{key,kind,label}], allSelected}], pendingRequest|null}` instead
  of `{terms, updatedAt}`: the screen states the rule per dimension (an empty dimension does
  not restrict, FP-01) and shows the one change waiting (FP-02). The history of changes is
  the request list, so `updatedAt` has no single meaning. `PUT /tenant/footprint` is
  removed (section 5); a change is a request: `POST /tenant/footprint/requests` (201
  `FootprintRequestRow`; with `?dryRun=true`, 200 `{adds, removes, preview, dryRun}` and
  nothing written), `GET /tenant/footprint/requests` (`{items, total}`), and
  `POST /tenant/footprint/requests/{requestId}/approve` (step-up, four eyes, `If-Match`),
  `/reject` and `/withdraw` (the requester only).
- `GET /proposals` (`listProposals`) answers `{items, total}` instead of a cursor page, and
  filters by `status` and `kind` (each one value or a comma-separated list) and
  `targetList` (a vocabulary list name or a taxonomy dimension key, matching
  `payload.list` or `payload.dimension`). `proposals.review` only (PRO-03).
- `GET /proposals/{proposalId}` (`getProposal`), `POST /proposals` (`createProposal`),
  `POST /proposals/{proposalId}/approve` (`approveProposal`) and
  `POST /proposals/{proposalId}/reject` (`rejectProposal`) carry `rejectionCode` beside
  `reviewNote` on the proposal. Reject takes `{rejectionCode, note}` instead of the
  designed `{reason}`: a code the proposer's screen can branch on and a sentence they read,
  both required (422 `reason_required`). Approve takes `{note}`; the designed
  `payloadOverrides` lands with obligation proposals in chunk 4 (PRO-S4). `POST /proposals`
  answers 200 with the existing proposal when an `Idempotency-Key` is replayed with the same
  body, 409 `idempotency_conflict` with a different one. Payloads are named per kind in
  `apps/proposals/schemas.py`; chunk 2 kinds are `vocabulary_create`,
  `vocabulary_relabel`, `vocabulary_retire`, `vocabulary_restore`, `vocabulary_merge`,
  `term_create`, `term_update`.
- New in chunk 2 and not in the design, one generic set for every vocabulary list
  (VOC-01, AC-VOC1: adding a list never moves the contract): `GET /vocab` (the list of
  lists), `GET /vocab/{list}` and `GET /vocab/{list}/{key}` (any session, or `library:read`),
  `POST /vocab/{list}`, `PATCH /vocab/{list}/{key}`, `POST /vocab/{list}/{key}/retire`,
  `/restore` and `/merge` (`?dryRun=true` previews and writes nothing), `POST
  /vocab/{list}/reorder`, `POST /vocab/{list}/suggest`, `GET /vocab/{list}/suggestions` and
  `POST /vocab/{list}/suggestions/{suggestionId}/decline`, and `GET /taxonomy/dimensions`.
  A tenant list is written directly under `vocab.manage`; every write to a library list
  answers 202 `{proposal}` (VOC-07). Refusals carry their evidence beside the code:
  `candidates[{key,label}]` on 409 `duplicate_key` and 422 `near_duplicate`, `usageCount`
  on 409 `in_use`; `system_row` and `invalid_transition` are 409.

Chunk 1 follow-up (enrolment without an address, Alex 2026-09-19):

- `POST /auth/invitations/verify` (`verifyInvitationCode`) is new and not in the design:
  the invitation path verifies the emailed code with `{token, code}` and no address,
  because the link's token already names the account and is a secret only the
  recipient holds. The token rides in the body, never the path, so no access log
  holds it (security review F6). It answers the same `SessionTokens` and refresh cookie
  as `POST /auth/code/verify`, 410 `invitation_expired` for an expired, revoked,
  consumed or unknown invitation, and verifies only a code issued for that
  invitation's address. `POST /auth/code/verify` with `{email, code}` stays for the
  sign-in page's "First time here?" path (J-1).
- `POST /auth/invitations/open` (`openInvitation`) is not in the design either, and
  takes `{token}` in the body: there is no path form (security review F29). Every
  server that logs request lines (Django's request logger on a 4xx, gunicorn's access
  log, the hosting edge) would otherwise write the token down. The emailed link is
  `/invite#<token>`: a fragment never reaches a server, proxy or `Referer`, and the page
  clears it before its first request. Same `auth:ip` rate limit, 202 `{}`, and 410
  `invitation_expired` for an expired, revoked, consumed or unknown token.

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

**PRD 0.3 (2026-09-19).** Kinds added to tier 1, each authorised by the bump:

- `term_dimension_kind` gains `opt_in`: a record carrying a term of such a
  dimension matches only when the regulatory scope names that term (FP-01,
  INV-08, D-36).
- A new, optional `instrument_level_kind` whose only value is `standard`. The
  five existing level rows keep a null kind (INV-01, INV-08, D-37).
- `jurisdiction_kind` gains `international`, for standards bodies (INV-08,
  I18N-01, D-38).
- `WorkReason` (`owner`, `participant`), `WorkBucket` (`overdue`, `due_soon`,
  `aware`, `open`) and `WorkDateKind`, each value with its reason (HOM-05,
  D-23).
- `notification_kind` gains `participant_added`, `involved_item_changed` and
  `review_due` (COL-02, COL-04, D-34).

**PRD 0.3 structures.** Tables and columns the designed schema does not have,
or has differently:

- `participant`: a tenant row naming a person or a team on `tenant_obligation`
  or `change_case`, with composite `(tenant_id, …)` foreign keys to the
  subject, the team and the membership, soft removal, partial unique and index
  definitions where it is not removed, and forced row-level security. It
  replaces `impact_assessment.contributors`, which is dropped: the assessment's
  contributor teams are the case's team participants (COL-04, CAS-03, D-18,
  D-20).
- `team` becomes a tier-3 list carrying its org unit; `team_member` has
  composite keys and **no** `is_lead`, because a department's head sits on
  `org_unit.head_user_id` and team notices go to a team's active members
  (TEN-02, TEN-03, D-21). `team.org_unit_id` and `org_unit.head_user_id` are
  composite keys, and `tenant_obligation`, `change_case`, `team` and `org_unit`
  gain `UNIQUE (tenant_id, id)` so the composite keys can point at them.
- `tenant_obligation_scope` gains `next_review_date`, an applicability reason
  and an applicability decision time; `applicability_request` gains a nullable
  scope row and a nullable unit, and its one-pending index covers both with
  nulls not distinct (REG-01, REG-02, D-42).
- `soa_unit`: a tenant row per unit per legal entity holding the tenant's own
  reference and title, applicability with its reason and decision time,
  compliance status, note and version, unique per scope row and reference, under
  forced row-level security. `gap` gains a nullable unit. `tenant_obligation`
  keeps `UNIQUE (tenant_id, obligation_id)` (REG-08, D-41).
- `licence` gains a nullable validity end date, next audit date and owner, so a
  certificate is a licence row. It carries no term and decides no span
  (TEN-02, D-43).
- `taxonomy_term` gains a nullable unique `jurisdiction_id`: the jurisdiction
  dimension's terms mirror the jurisdiction rows and are never proposed
  (FP-04, D-29). `watched_market` is a tenant row naming a jurisdiction, unique
  per tenant, under forced row-level security (FP-04, D-30).
- `Jurisdiction.parent` means "the jurisdiction whose rules reach this one", and
  Norway points at the EU under the EEA Agreement. No new column (FP-04, D-28).
- `Instrument.regime` becomes NOT NULL, as `schema.sql` already has it; one
  trigger on `provision` refuses a row under a standard-level instrument
  (INV-01, INV-08, D-35, D-39).
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
- `agent_kind` gains `watch` (chunk 5). Version 0.3 has `research`, `backfill`
  and `reverify`; the first shipped definition,
  `backend/agents/watch-sweeper/v1/definition.yaml`, declares `kind: watch`, which is
  what sweeping registered sources for new documents is. It stays a tier-one
  kind (§1): the scheduler branches on it and no admin adds one.
- `agent.name` becomes `agent.key`, an immutable slug holding the definition's
  `id`, because a library record is addressed by a key that never changes
  (playbook 15). `agent` also gains `current_version`, the version folder the
  reference seed loaded, until `agent_version` rows land with AGT-03.
- `agent_run` gains `api_key_id` (the key that opened the run: R1 runs all come
  through the agent API) and `idempotency_key`, unique per key, so a retried
  `POST /agent-runs` returns the run it already opened instead of a second one.
  A run's `tenant_id` is always its key's: a platform key opens library runs, a
  tenant's key that tenant's runs. Reads are mixed, writes are not: a tenant
  reads library runs but writes only its own, and a session with no tenant
  writes only library runs (agents migration 0001).
  The remaining v0.3 columns (`tenant_agent_id`, `agent_version_id`, `trigger`,
  the cost and token columns) arrive with chunk 11.
- The proposal queue is reviewed in the platform console by `library_editor`.
  The prototype shows the tenant's compliance officer approving agent
  proposals. That is the one place the prototype is wrong.
- Footprint changes become a request with preview and second-person approval
  (`footprint_change_request`), replacing the direct `PUT /tenant/footprint`.
- PRD 0.3: `tenant_agent.scope` has a default rather than being empty. At run
  start the scheduler builds it from the tenant's market levels, operating
  first, unless the row names jurisdictions of its own, and stores a copy on the
  run. A platform library run never reads a tenant's markets (AGT-04, D-32).

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

PRD 0.3 (My work, participants, markets and standards), 2026-09-19:

- `GET /me/work` is reshaped and moves screens. The designed `MyWork` fed
  Today's "Decide now"; instead Today reads the queue counts on `GET /me`,
  which gain applicability, and `/me/work` becomes the My work page from chunk
  8. It answers `{items, total, counts}` with the shared `limit`/`offset` and an
  optional bucket filter, where an item carries its kind, key, record name,
  reason, who, via, date kind and date, and the kinds the reader may not see are
  listed as permission-limited rather than refused (HOM-05, D-23).
- `GET /me` gains `headOf`, the departments the caller heads (HOM-05, TEN-02).
- `GET`, `POST /obligations/{obligationId}/participants` and
  `DELETE /obligations/{obligationId}/participants/{participantId}`, and the
  same three on `/changes/{changeId}`, are new: add needs `register.edit` or
  `cases.contribute`, and the delete is gated in logic because a person may
  always remove their own row (COL-04, D-19).
- `GET /reference/people` is new: active members' ids and names only, a plain
  array like the other reference reads, ungated for a member session and
  refused for an enrolment session. Teams come from the team vocabulary list
  (COL-04, TEN-03).
- `PUT /tenant/members/{userId}/teams` is new, under `members.manage`, writing
  one audit event per call (TEN-03, D-21).
- `GET /me/comments?about=written|mentioned` is new, paginated and filtered by
  the subject's read permission, with the permission-limited kinds named
  (COL-01, D-22).
- `GET /tenant/footprint` gains `markets` (jurisdiction, operating, watching),
  and `POST /tenant/footprint/watching` and
  `POST /tenant/footprint/watching/remove` take the jurisdiction **in the body**
  under `footprint.request`. The key never rides in a path or query string,
  because the access log and error reports keep the request line (FP-04, D-30).
- The list filter `inFootprint`/`outsideFootprint` becomes one value,
  `footprint=in|all|watched`, on `GET /instruments`, `GET /obligations` and
  `GET /changes`, so no contradictory pair can be sent; those rows also return
  the record's jurisdiction (FP-04, D-29).
- A route under `applicability.approve` with a step-up decides many pending
  applicability requests in one call, taking a list of request ids each with a
  decision and a note, capped by `REGISTER_BULK_MAX`; a request the caller filed
  answers 409 `four_eyes_violation` and nothing is decided (REG-01, D-44).
- A unit paste route under `register.edit` takes one entity's lines with a dry
  run, and files one pending applicability request per row when the line carries
  an applicability (REG-08, D-41).
- New refusal codes, all with their evidence beside the code: 409
  `already_participant`, `already_watching`, `unit_has_history`; 422
  `participant_cannot_read`, `too_many_participants`,
  `standard_term_only_on_standards`, `standard_term_required`,
  `one_conformance_obligation`, `licensed_text`, `not_a_regime`,
  `regime_required`, `units_only_under_standards`, `scope_not_applicable`.

Chunk 3 (library and inventory), 2026-09-19:

- `GET /obligations` (`listObligations`) answers `{items, total}` with `limit` and `offset`
  instead of a cursor page (playbook 10). Its filters are `instrument` (the instrument's
  stable key, not the designed `instrumentId`), `dutyType` (a key), `term` (repeatable
  `dimension:key` instead of `termId`, at most `LIBRARY_TERM_FILTER_MAX`, default 20;
  every term must be in the obligation's scope, which is its own terms plus its
  instrument's regime; 422 `unknown_key` naming each term that does not exist), `q` (the
  title in any language, or the reference label), `asOf` (the
  version in force on that date; default today in the tenant's time zone) and
  `outsideFootprint=true`, which lifts the footprint filter instead of the designed
  `inFootprint`. A row is `{id, stableKey, refLabel, title{text, language, isOriginal,
  isMachine}, instrument{key, shortName}, bindingLevel{key,kind,label}, binding,
  dutyType{key,kind,label}, tags[{key,kind,label}], scope[{dimension{key,kind,label},
  terms[{key,kind,label}], allSelected}], version{versionNumber,
  effectiveFrom{date,precision}}, upcomingVersion, inFootprint, outsideReason[{dimension,
  terms}], lastVerifiedAt, openChangeCount, pendingApplicability, complianceStatus}`:
  keys, kinds, counts and dates, never a phrase. `scope` lists every active dimension,
  an empty one meaning no restriction, instead of the designed flat `terms`. The register
  overlay waits for its chunks: `openChangeCount` is 0 until the watch feed (chunk 5), and
  `pendingApplicability` and `complianceStatus` are null until the register (chunk 8), as
  are the designed `applicability`, `riskRating` and `owner` and the `applicability`,
  `complianceStatus`, `ownerId`, `hasOpenChanges` and `reviewDueBefore` filters. The tag
  filter is deferred. A person with `library.read` in their tenant, or an API key with
  `library:read`.

- `POST /obligations/{}/problem-reports` (`reportObligationProblem`) answers 201 with
  `{id, status, createdAt}` instead of the designed whole `ProblemReport`. The reader is
  told their report exists and is open; their own words are not read back to them, since
  they are on the screen already and every copy of tenant content is a place it can
  leak (playbook 4.7). The body is `{description, versionNumber?, language?}`: the
  version and language record what was on screen, so a colleague opens the same words.
  There is no problem-area field ("Where" in tenant-obligation.html): nothing branches on
  one, and under "types and reasons are rows" it would be a library vocabulary rather
  than a code enum. It waits for Alex's answer (the open question in
  docs/plans/briefs/CHUNK3_TASKS.md). `problems.report`, which every member of a bank
  holds and no platform role does.
- `POST /instruments/{}/problem-reports` (`reportInstrumentProblem`) is not in the design,
  which reports obligations only. A reader sees instruments and provisions too, and a
  provision is reported through the instrument whose card shows it (chunk 3 default), so
  the same body and the same answer serve both. `GET /problem-reports` stays in chunk 4.
- `POST /obligations/{}/verifications` (`reverifyObligation`) takes `{outcome, note?}`,
  where `outcome` is a VerificationOutcome key, and answers 201
  `{id, outcome, verifiedAt, lastVerifiedAt, verifiedBy{id,name}|null}` instead of the
  designed 200 `{lastVerifiedAt, verifiedBy}`: a row is created on every outcome, and the
  answer says which check was recorded as well as what the record now carries. The stamp
  moves only on `no_change`; any other outcome files the check and leaves the old stamp
  standing, because the correction itself arrives as a proposal.
  The designed `x-roles` names `compliance_officer` beside `library_editor`. The build is
  stricter: `proposals.review` plus a fresh passkey, and no tenant role holds
  `proposals.review` (PRD §6). Re-verification is the single exception to "a proposal is
  the only door into the library" (INV-06, INV-S8), so it stays with the reviewers the
  fence already trusts, and a bank that thinks a record is wrong files a problem report
  instead. A report stays inside that bank (Alex, 2026-09-19): bleqq's watch agents find
  the deviation themselves by re-checking the source, and propose the correction.

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

Chunk 5 adds two tier-one kinds the designed schema spells differently:
`source_check_kind` (`sweep` or `recheck`), which `schema.sql` does not have at all, and
`check_frequency` (`daily`, `weekly`, `monthly`), which `schema.sql` has as a `CHECK`
constraint on a `text` column. Both are things the scheduler and the re-check branch on
and neither is a list an admin curates, so both are kinds in code (WAT-01, AGT-01).

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

**Chunk 7 (2026-09-20).** Kinds the search and ask contract adds to tier 1:
`search_hit_type` (a hit is an obligation, a provision or a change),
`search_match_kind` (keyword, concept or both, said on every hit) and
`answer_feedback` (helpful or wrong, the verdict the evaluation set reads back).
`search_source` above is not one of them: it stays the chunk table's own column,
which the search index builds.

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
- `source_check` gains `kind` (`sweep` or `recheck`, default `sweep`) and the
  nullable `subject_type` and `subject_id` a re-check names, which `schema.sql`
  lacks: every watch run re-checks the library records its sources cover and
  logs each re-check as a source check, and a correction goes through the
  proposal door (WAT-01, AGT-01, INV-06, Alex 2026-09-19 item 3). A check
  constraint pins the pairing: a re-check names a subject, a sweep names none.
- `change_term` gains `confidence`, `suggested`, `confirmed_by` and
  `confirmed_at`, which `schema.sql` lacks: an agent's classification is a
  suggestion carrying its confidence until a library editor confirms it
  (WAT-03). The same four columns' shape on `change_obligation` is the designed
  one, with `suggested` read off `confirmed_at` (WAT-04).
- `regulatory_change.flags text[]` is dropped. A flag is a row of the `flag`
  list and a scope term a row of a dimension, and both are `change_term` rows —
  one table, exactly one of `flag_id` and `term_id` set — so a flag carries the
  same confidence and suggestion marker as a scope term and a usage count and a
  merge reach both (§1 above, VOC-02, WAT-03). `change_document.risk_flags`
  stays the designed `text[]`: its values are what the injection screen found
  (`apps/agents/screen.py`), which engineering owns, not a list an admin curates.
- `source.check_frequency` and `source_check.status` are kinds in code, and
  `source.kind`, `regulatory_change.change_type` and
  `regulatory_change.suggested_urgency` are foreign keys to the library
  vocabulary rows chunk 2 seeded, never the designed Postgres enums (§1 above).
- `watch/logic.py` is replaced by `watch/write.py`, the one module under
  `apps/watch/` that may call `library_write()`. It opens `watch_write()`, which
  reaches the seven watch tables and refuses every other library table at
  runtime, so no watch step can write an authority, an instrument, a provision,
  an obligation or a version table (PRO-01, chunk 5 ruling H).
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
- **PRD 0.4 (2026-09-20).** `api_key.scopes`' CHECK gains `proposals:review`
  (D-62, ADR 0054): a platform key bound to an agent definition may read the
  proposal queue and approve, correct or reject, and still reaches no library
  row. It is a platform scope only; a tenant key that carries it is refused.
  Nothing else about a key changes, and a key still cannot step up.

## 3. Nordic scope (PRD I18N, playbook 17)

- Replace `summary_sv`/`summary_en`, `text_sv`/`text_en`, `label_sv`/`label_en`
  and every `lang IN ('sv','en')` check with translation rows and a language
  table. `search_chunk.lang` references the language table, and its `tsv`
  uses the language's text search configuration.
- `instrument.jurisdiction` and `authority.jurisdiction` reference a
  jurisdiction table. Seed EU, SE, DK, NO, FI with their authorities.
- `app_user.locale` references the language table.
- `jurisdiction.parent` is "the jurisdiction whose rules reach this one", not membership
  of a union (D-28, ADR 0026). Norway's parent is the EU: it is outside the Union but
  inside the internal market under the EEA Agreement, so EU financial rules reach it and a
  bank operating only in Norway must still see Union law.
- The `jurisdiction` dimension's terms mirror those rows one for one, written by the
  reference seed (FP-04). `docs/plans/briefs/MY_WORK_AND_MARKETS.md` T-12 says a term
  written by hand under a mirrored key is "adopted"; the build **refuses** it with
  `system_key_taken` instead, the way every other reference seed refuses a key a row of its
  own already holds. Adopting it would keep its author's labels, parent and place in the
  list while flipping `is_system` behind their back, and nobody could then tell the mirror
  from a term a person wrote. Refusing names the one key to rename and stops there.

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
- **PRD 0.4 (2026-09-20), the queue's second principal.** bleqq staffs no
  editorial function (Alex, item 19), so the routine approver is an independent
  agent and `library_editor` is kept, unstaffed, for the proposals a person
  takes over. `proposal` therefore gains `reviewed_by_api_key` beside
  `reviewed_by`, and `proposed_by_agent` and `reviewed_by_agent`, copied from
  each key by the one write path. Version 0.3's four-eyes CHECK compares users
  only; it is widened to refuse a row whose user, key **or** agent is the same
  on both sides, so two keys of one agent definition cannot confirm each other,
  and to refuse a reviewing key that names no agent, because two unbound keys
  would otherwise pass the agent comparison on nulls.
  The console queue, its screens and its audit rows are otherwise unchanged
  (D-62, ADR 0054).
- **PRD 0.4, machine-confirmed provenance.** The verification columns version
  0.3 puts on `instrument`, `obligation` and the version rows (`last_verified_at`,
  `verified_by`) name a person only. They gain `verified_origin` (the existing
  `origin_type` kind) and `verified_by_agent`: a record applied from a proposal
  an agent confirmed names the proposing and the confirming agent and never
  reads as verified by a person. The re-verification stamp of INV-06 stays a
  person's act and keeps writing `verified_by`.
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
  `{name, scopes[], expiresAt?}` and never an `agentId` — corrected 2026-09-20: chunk 5
  puts `agentId` on the platform's `POST /agent-keys`, not here, because a key bound to an
  agent is the platform's and no tenant route creates one (ID-10, AGT-01) — and answers
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

Chunk 7 (the search and ask contract), 2026-09-19:

- `POST /search` (`search`), `POST /search/similar` (`findSimilar`), `POST /ask`
  (`ask`) and `POST /answers/{answerId}/feedback` (`rateAnswer`) are declared in
  their designed shape but answer 501 `not_built` behind their real gates until
  the search index and the hybrid query land; `POST /ask` answers its 501 as a
  stream carrying one `not_built` problem event, because a stream is what it will
  always answer. A stub is not a served route: no screen calls one, and the chunk
  close proves none is left.
- `POST /ask` answers `text/event-stream`, not the designed single `Answer`
  body. Ask's budget is a first token under 2 s (playbook 10, SRC-S9), which an
  answer that waits for its last cited sentence cannot meet, and the LLM adapter
  already streams. One JSON object per `data:` frame, each naming its kind in
  `event`: `start` (the answer's id, and what the 2 s is measured to), then a
  `statement` per cited sentence, and then either `answer` (the whole answer with
  its citation list, which is what the `ai_generation` row records) or `problem`
  (the `code` an RFC 9457 body would carry, because a failure found after the
  first byte can no longer be a status). Everything that can refuse the call
  before the first byte still answers a status and a problem body: the session,
  `search.use`, and the question's cap.
- `POST /search` drops the designed `apiKeyAuth`: it is a person's route, gated
  on `search.use` (PRD §6, everyone). No agent needs a ranked reader's search;
  the agents read `POST /search/similar`, and a route no caller needs is a door
  left open.
- `POST /search/similar` is gated on the `search:read` key scope alone, so a
  person's session is 401 and only an agent's key reaches it. The designed
  `x-roles: library_editor` names no permission in the matrix that gives a
  library editor a similarity read (their four are `proposals.review`,
  `library_vocab.manage`, `sources.manage`, `eval.manage`), and the R1 consumer
  is the agent flow (AGT-02). A console surface that wants it comes with its own
  permission and its own security review; widening this route is a guard change.
- `lang` on `SearchRequest` and `AskRequest` is a language key from the language
  rows, not the designed two-value `Lang` enum (section 3).
- `SearchHit.urgency` is taxonomy's `TermRef` (`{key, kind, label}`), not the
  designed phrase enum: urgency is a library vocabulary row with a fixed ordinal
  and tone and an editable label (section 1), so the client stores and compares
  the key. It is the shared reference shape, not a search-specific copy of it,
  so a screen reads one type wherever a vocabulary value appears.
- `SearchRequest.limit` and `SimilarRequest.limit` are the shared page size
  (`API_PAGE_SIZE_DEFAULT`, max `API_PAGE_SIZE_MAX`): above the maximum is a 422,
  never a clamp (playbook 10). `q`, `text`, `question` and a feedback `note` are
  capped by `SEARCH_QUERY_MAX_CHARS`, `SEARCH_SIMILAR_MAX_CHARS`,
  `ASK_QUESTION_MAX_CHARS` and `SEARCH_FEEDBACK_NOTE_MAX_CHARS`; each is a cap at
  a trust boundary, because the text reaches a text-search query, the embedder
  and, for Ask, a model prompt. `filters.termIds` is capped by
  `LIBRARY_TERM_FILTER_MAX`, the cap the library's own term filter already uses.
- `SearchResponse` stays `{items, asOf}` rather than a page `{items, total}`:
  ranked results are a top-N cut, and a total over a fused ranking would be a
  number nobody can act on. `asOf` is echoed so the screen can say which day's
  law it showed.
- `SearchFilters` holds the R1 filters only: `instrumentId`, `jurisdiction`,
  `dutyType`, `termIds`, `binding` and `inFootprint`, each an id or a key and
  never a label, which is what the search screen and SRC-S3 filter by. The
  designed `applicability` and `complianceStatus` are not declared: the register
  overlay that answers them lands in chunk 8 (REG-01, REG-02), and a filter the
  query cannot honour would be a 200 that silently ignored it rather than the
  422 an unknown field earns. Chunk 8's register contract adds them with the
  overlay that reads them.
- `Citation` and `AnswerFeedback` are `AnswerCitation` and `AnswerFeedbackBody`
  in the build: Ninja flattens component names across apps, so an app-specific
  shape carries its prefix (playbook 4.1). The wire fields are unchanged.
- Saved searches (`GET`, `POST /saved-searches`,
  `DELETE /saved-searches/{savedSearchId}`) are SRC-04, R3: they stay in
  `backend/scripts/contract_drift_pending.txt` and nothing here declares them.

PRD 0.4 (the fourteen owner decisions), 2026-09-20. Each row names its decision
in `docs/DECISIONS.md`; the researched detail is in
`docs/plans/briefs/OWNER_RECOMMENDATIONS.md`:

- `urgency` rows are fixed (D-48): `GET /vocab` entries gain `fixedRows`, so the
  vocabulary screen hides Create and reorder. Creating an urgency level, and a
  relabel whose extra carries an ordinal, answer 422 at `/vocab/urgency`, at
  `POST /proposals` for a person or an API key, and inside `proposals/apply.py`.
- `support_access` (D-49) is the designed table with a CHECK that `approved_by`
  is not the platform person, a guard trigger refusing DELETE and refusing any
  change to the tenant, person, purpose, ticket, level or duration after insert,
  and a request TTL. `user_session` gains the grant id, so a support session
  carries the grant it was opened under and expires with it. The designed
  console list of a person's own grants runs through a SELECT-only policy keyed
  on `app.platform_user_id`, never through `identity_lookup`.
- `problem_report` (D-50) stays tenant-only: no console route reads it, no
  platform policy is added, and the designed console problem-report surface in
  ADM-02 is dropped. Its resolution is not a status a bleqq editor sets; a
  library error reaches the library through the watch agents' re-check and a
  proposal. `agent_run` therefore also records the library records re-checked in
  a run beside its source checks (WAT-01).
- `search_chunk` (D-51) is labelled LIBRARY in `schema.sql`. It is not a
  `LibraryModel`: it is derived data with `owner_tenant_id` (NULL in R1), forced
  row-level security in the agents 0001 shape, and its own write fence
  `index_write()`, allowed by an AST guard only in `search/indexing.py`.
- `calendar_feed` (D-52) is new: a token prefix plus SHA-256, the owner, the
  created, last used and revoked times. It becomes the fifth table of the
  identity-lookup clause, and `GET /api/v1/calendar/feed.ics?token=<prefix>.<secret>`
  is the one route that reads a token from the query string (the CONVENTIONS 3.6
  exception). `login_event.kind` gains `feed_used`.
- Retention (D-53) replaces the per-tenant periods §7 plans as columns of the
  workflow policy: one fixed age, ten years after a record's last use, so the
  tenant carries a pause switch rather than three periods, and there is no
  per-record legal hold. New: a lifecycle registry mapping every tenant table to
  cases, evidence, audit, live or platform window, a `retention_run` row per
  run, and one `SECURITY DEFINER` purge function owned by `cw_migrator` whose
  cutoff can never be younger than one year.
- Tenant exit (D-56): `tenant_exit_request` is new, with a CHECK that
  `approved_by` is not `requested_by`, and joins FOUR_EYES_TABLES. `tenant.status`
  gains `closing` and `deleted`, mutating routes answer 409 `tenant_closing`
  while closing, and a `TenantExitReport` tombstone holds the counts, the export
  hash, the people and the assertion ids. Deletion is a SQL function owned by
  `cw_migrator` and never granted to `cw_app`, run by
  `manage.py execute_tenant_exit`.
- Private records (D-57): `proposal` gains `owner_tenant_id`, set by the server
  from the target and never from the body, plus forced row-level security
  (read shared or own, insert shared or own, update and delete own only). The
  library and watch child tables of `instrument`, `obligation`, `source` and
  `regulatory_change` each gain a FOR SELECT policy where the parent is visible
  and a FOR ALL policy where the parent's owner is the session tenant. A new
  permission constant, `private_records.approve`, and two routes,
  `POST /private-proposals/{id}/approve` and `/reject`. `source` gains the
  private-source checks (https, no credentials, a public host, not a standards
  publisher, `PRIVATE_SOURCES_MAX` per bank).
- SSO (D-58) fills in what §2 defers to R3: `identity_provider` and
  `tenant_domain` arrive with a DNS TXT verification, one tenant per domain, and
  no `auto_join`, `default_roles`, group-to-role sync or `scim_token_hash`
  column; a SCIM key is an ordinary API key whose single scope is `scim`, which
  `POST /tenant/api-keys` refuses (422). `login_event.method` gains `oidc` and
  `saml` as planned, and the security log gains `idp_verified` and `idp_failed`.
  The link is the directory id SCIM provisioned (for Entra, issuer plus `oid`),
  never the email claim, and the enforcement challenge is bound to the browser
  by a short-lived single-use cookie.
- Credential policy (D-55): the `security_policy` row §2 already plans carries
  three fields, `credential_policy`, `allowed_authenticators` and
  `device_bound_from`, and the allowed list is a committed platform list of
  authenticator models, never downloaded at runtime.
- Platform counters (D-59): `usage_record` and `job_run` may hold numbers, kinds
  and times only — `job_run` carries an `error_code` kind rather than the
  designed error text, typed integer stats, and a typed subject kind and uuid so
  a retry can rebuild the job — and each gains one SELECT-only policy keyed on
  `app.platform_counters`. A structural test refuses a free-text or untyped JSON
  column on either.
- Agents (D-61): `tenant_agent` rows exist only for the agents a bank adds for
  itself. bleqq's agents have no `tenant_agent` row, so cadence, scope, pause and
  budget do not apply to them, and their runs stay platform runs opened by a
  platform key. A tenant agent's run writes only in that tenant's zone and may
  register nothing in the shared library. `research_request` follows the same
  split: a bank's request names its own agent, and a `retag` request is a console
  request.

- `GET /obligations/{obligationId}` (`getObligation`) answers the whole card as of a date
  rather than the designed `Obligation`: `{id, stableKey, refLabel, title, instrument{key,
  shortName, name, officialRef, implementsNote}, regime, bindingLevel, binding, dutyType,
  triggerFrequency, retention, sanctionExposure, productScope, tags[], scope[], inFootprint,
  outsideReason[], summary, translations[], version, versions[], provisions[], related[],
  provenance}`. Same caller as the list. Each departure has its reason:
  - The summary is `{text, language, isOriginal, isMachine}` with every language of that
    version in `translations[]`, instead of the designed `summaryEn`/`summarySv` pair
    (sections 1 and 3): the languages are rows and a machine translation stays labelled
    (INV-05). `?asOf=` picks the version in force, today in the tenant's time zone by
    default; the record is answered whatever the footprint says, with the verdict and its
    reason beside it, because an address always resolves (FP-03).
  - `versions[]` is embedded here, so the designed `GET /obligations/{obligationId}/versions`
    (`listObligationVersions`) is not built. A row is `{versionNumber, effectiveFrom,
    effectiveTo, approvedAt}`: `effectiveTo` is derived as the day before the next version
    takes effect, because nothing stores an end date (INV-04), and the approver is not
    named, matching the card.
  - `provisions[]` is `{id, refLabel, path}` and holds no text: the verbatim text belongs to
    the provision tree read, and the card shows none. `related[]` is `{id, title, instrument,
    binding, relation}`.
  - `provenance` is `{createdOrigin, createdModel, createdAt, verifiedBy, lastVerifiedAt,
    sourceUrl, sourceLabel}` (INV-06). `verifiedBy` is null until someone re-verifies the
    record, and is then a platform person, never a tenant member.
  - The designed `lineage` sits on the instrument's read, and `register`,
    `pendingApplicabilityRequest` and `internalLinks` wait for the register (chunk 8);
    related changes are `GET /obligations/{obligationId}/changes` (chunk 5).
  - A record the caller cannot see answers 404 `not_found`, never 403, so no address can be
    probed for what another bank holds privately (INV-07).
- `GET /obligations/{obligationId}/diff` (`getObligationDiff`, the designed
  `diffObligationVersions`) answers `{fromVersion, toVersion, fromEffective, toEffective,
  language, isMachine, segments[{op, text}]}` instead of the designed `{fromVersion,
  toVersion, lang, segments}`: the screen names both effective dates and says when the text
  it compares is a machine translation (INV-05). `from` and `to` are version numbers and
  default to the latest version against the one before it; a number the obligation has no
  version for is 422 `unknown_key`, and fewer than two versions to compare, or two versions
  with no language in common, are 422. `lang` is accepted here and on the provision diff
  alone; every other read follows the reader's language order.

Chunk 5 (watch and the agent API), 2026-09-20:

- `GET /agent-runs` (`listAgentRuns`) answers `{items, total}` with `limit` and `offset`
  instead of a cursor page, like every other list (playbook 10). Its rows are the runs the
  caller may see: a tenant reads the library's runs and its own, the console reads them
  under `system.health`. bleqq's agents are platform-owned and platform-run in R1, so no
  session opens or closes a run and the two run writes take an agent key alone (AGT-01,
  item 14).
- `POST /agent-keys` (`createAgentKey`), `GET /agent-keys` (`listAgentKeys`) and
  `POST /agent-keys/{keyId}/revoke` (`revokeAgentKey`) are new: the design has only the
  tenant's `POST /tenant/api-keys`, and a key bound to an agent needs a route of its own
  under `agent_definitions.manage` with a passkey step-up on creation. `agentId` is
  required here and is not accepted on the tenant route (ID-10, AGT-01).
- `PUT /changes/{changeId}/obligations` (`replaceChangeObligations`) is served to an agent
  key holding `changes:write`, although the designed contract names no key for it: the
  agent that registers a change also suggests the obligations it touches, and the same
  scope already carries `POST /changes` and the change's documents (WAT-04, AGT-01). A
  library editor's session with `proposals.review` writes it too; the link stays a
  suggestion until a person confirms it. The list is capped at 200 links per call, the cap
  the same list carries inside `POST /changes`.

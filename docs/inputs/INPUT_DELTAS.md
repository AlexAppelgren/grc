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
  five existing level rows keep a null kind (INV-01, INV-08, D-37). Built
  2026-09-23 as `InstrumentLevelKind` (apps/taxonomy/models.py), the
  `instrument_level` list's optional kind, with one seeded row `standard`
  (`binding_default` false, rank 60) from the prototype fixture.
- `jurisdiction_kind` gains `international`, for standards bodies (INV-08,
  I18N-01, D-38). Built 2026-09-23 with one seeded row, `intl`, no parent,
  outside the footprint's jurisdiction mirror.
- `WorkReason` (`owner`, `participant`), `WorkBucket` (`overdue`, `due_soon`,
  `aware`, `open`) and `WorkDateKind`, each value with its reason (HOM-05,
  D-23).
- `notification_kind` gains `participant_added`, `involved_item_changed` and
  `review_due` (COL-02, COL-04, D-34).

**Chunk 6 (2026-09-21).** Kinds the home contract adds to tier 1, and one it corrects:

- `roadmap_item_kind` (`regulatory`, `internal`): what a dated thing on the roadmap is
  about. The screen picks its pill from it - an urgency for a date the outside world set,
  "Our deadline" for one this bank set - so it is a thing the code branches on and never a
  list an admin curates (HOM-03).
- `roadmap_item_type` (`change_date`, `internal_deadline`, `action_due`, `review_due`):
  what produced the date. The calendar builder and the card branch on it. Declared in full
  although R1 produces `change_date` alone, so a client written against the contract now
  does not change when the register (chunk 8) and the case workflow (chunk 9) fill the rest.
- `feed_filter` (`all`, `regulatory`, `internal`) is **corrected twice**. It was recorded as
  "FP-03: inside or outside the footprint", which it is not: `schema.sql` line 61 has it as
  a calendar subscription's scope and nothing branches on it for the footprint. It was then
  recorded as that scope and the roadmap's `kind` filter at once, and D-52 left it with one
  reader: a calendar feed carries the dates the outside world set and never the bank's own,
  so the subscription has nothing to choose between and its column is not built (§9). The
  kind is the roadmap read's filter, which does have internal branches coming.

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
  (INV-01, INV-08, D-35, D-39). Built 2026-09-23 in library 0008: the trigger
  `provision_not_under_standard` fires on insert and on a change of
  `instrument_id`, and raises `check_violation`; it also refuses a provision
  under an instrument the writer cannot see, since it runs under row-level
  security. Two smaller triggers close the other paths under a standard: an
  instrument holding provisions moved onto a standard level, and an existing
  level given the kind `standard` while provisions sit under it.
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
- `agent_kind` gains `review` (D-62, D-80, 2026-09-23). A definition of this kind
  proposes nothing and decides what another definition proposed, as the
  independent second principal on the library's queue; the first is
  `backend/agents/library-confirmer/v1/definition.yaml`. Version 0.3's kinds all
  produce work, and none names the side of four eyes that decides it.
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
  enrolmentPending, passkeyCount, stepUpValidUntil}`. `f03-T48` (chunk 6) adds
  `counts{triage, proposals, assignedToMe}` and `lastVisitAt`: null for a platform session,
  each count 0 rather than refused when the caller's own permission does not unlock it
  (`triage` needs `cases.triage`, `proposals` needs `proposals.create`, `assignedToMe`
  needs none). The home contract deliberately keeps `decideNow` off `Home`, so Today reads
  one source for the number (D-23, ruling 1). The designed `signoffs` and
  `unreadNotifications` are cut for now: sign-off is chunk 9's and notifications chunk
  10's, and a field that always reads 0 before either exists is a false statement about
  the bank's queue; the chunk that builds each adds its own count.
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
  `index_write()`, allowed by an AST guard only in `search/indexing.py`. Built
  2026-09-20: the shape is what `rls_operations(mixed=True,
  column="owner_tenant_id")` emits since H15, so the chunk table carries the same
  policies as `agent_run` and `source`. Its `lang` is a foreign key to the
  `language` rows and its generated `tsv` carries one branch per content language
  (`english`, `swedish`, `danish`, `norwegian`, `finnish`), so schema.sql's
  `CHECK (lang IN ('sv', 'en'))`, which would have refused Danish, Norwegian and
  Finnish, goes with the LIBRARY label (§3).
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
- `POST /obligations/{}/problem-reports` (`reportObligationProblem`) answers 201 with
  `{id, status, createdAt}` instead of the designed whole `ProblemReport`. The reader is
  told their report exists and is open; their own words are not read back to them, since
  they are on the screen already and every copy of tenant content is a place it can
  leak (playbook 4.7). The body is `{description, versionNumber?, language?}`: the
  version and language record what was on screen, so a colleague opens the same words.
  There is no problem-area field ("Where" in tenant-obligation.html): nothing branches on
  one, and under "types and reasons are rows" it would be a library vocabulary rather
  than a code enum. It waits for Alex's answer (the open question in
  docs/plans/briefs/CHUNK3_TASKS.md). The gate is `problems.report`, which every member
  of a bank holds and no platform role does.
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
- `GET /instruments` (`listInstruments`) answers `{items, total}` with `limit` and
  `offset`, like `GET /obligations`, instead of the designed bare array. Its filters are
  `regime` (a regime term's key, not the designed `regimeTermId`) and `q` (matches the
  name, short name or official reference, ignoring case); `outsideFootprint=true` lifts
  the footprint filter, exactly as it does on `GET /obligations`. The designed `binding`
  filter, and jurisdiction, level, authority and `asOf` filters nobody asked for, are
  deferred (chunk3-rest defaults): "as of" applies to obligations only, and the
  Instruments tab lists every visible instrument with its own in-force dates. A row is
  `{id, stableKey, shortName, name{text,language,isOriginal,isMachine}, level, binding,
  jurisdiction, authority{key,name,shortName,url}, regime, officialRef,
  inForceFrom{date,precision}, inForceTo, implementsNote, obligationCount, inFootprint,
  lastVerifiedAt, sourceUrl}`. `obligationCount` counts the obligations this bank would
  see under the instrument: inside its footprint by default, or every one when
  `outsideFootprint` lifts the filter, matching what `GET /obligations?instrument=` would
  itself list. `inFootprint` is the instrument's own scope (its regime, the one dimension
  an instrument carries) against the footprint, computed by the same `instrument_scopes()`
  rule `GET /obligations` inherits through (one rule serves both, chunk3-rest-T13).
- `GET /instruments/{instrumentId}` (`getInstrument`) answers the row's own facts plus
  `eliUri` (an empty string, never null, when none is published), `authority` in full,
  `verifiedBy` (a platform person or null, INV-06) and `lineage`, instead of the designed
  `Instrument`. `lineage` is `[{relation, direction: outgoing|incoming, instrument{key,
  shortName}, note, fromRef, toRef}]`, both directions of `InstrumentRelation` in one
  list, so the designed `GET /instruments/{instrumentId}/relations` is served here instead
  of as its own route. `direction` says whether this instrument is the one relating
  (`outgoing`) or the one related to (`incoming`). `fromRef` and `toRef` keep the designed
  relation's own meaning whichever card reads them: the place in the instrument relating
  and the place in the one related to (`Article 25(3) and (4)`), each an empty string
  rather than null when the relation names no specific place, which is most of them. The
  card carries no footprint verdict of its own; the Instruments
  tab and its filter read that from the row. The provision tree is its own read
  (`GET /instruments/{instrumentId}/provisions`, chunk3-rest-T16). A record the caller
  cannot see answers 404, never 403 (INV-07).
- `GET /instruments/{instrumentId}/provisions` (`listInstrumentProvisions`) answers a
  plain array of root nodes instead of the designed array of flat `Provision` rows,
  because the tree has no natural page boundary and a node needs its children beside it.
  Each node is `{id, stableKey, kind{key,kind,label}, refLabel, heading, path,
  children[], versions[{versionNumber, effectiveFrom, effectiveTo, transitionalNote,
  text}], inForceVersion, obligations[{id, title, refLabel}]}`. `kind` on the reference
  carries the row's own fixed structural kind (`division`, `unit` or `annex`) rather than
  being null, because a screen groups by it. `versions[]` always lists every version, in
  and out of force, so a reader chooses one by its own chip rather than trusting today's
  date; `asOf` (default today in the tenant's time zone) decides only `inForceVersion`.
  The designed `GET /provisions/{provisionId}/versions` is served embedded here instead
  of as its own route. `effectiveTo` is derived exactly as an obligation version's is:
  nothing is stored, and a version row is never touched after it is written. The number
  of queries does not grow with the tree's size; an instrument the caller cannot see
  answers 404 (INV-07), and a citing obligation the caller cannot see is left out
  silently, never returned with a null.
- `GET /provisions/{provisionId}/diff` (`getProvisionDiff`) is not in the design, which
  has no diff operation at all. It takes the same `{from, to, lang}` triple as
  `GET /obligations/{obligationId}/diff` (one shared query schema, `VersionDiffQuery`)
  and answers the same `VersionDiff` shape: a provision's verbatim text and an
  obligation's plain-language summary are versioned and diffed the same way, so one
  function and one response shape serve both (chunk3-rest-T1, chunk3-rest-T16).

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

Chunk 6 (home, the briefing, the roadmap and the calendar feed), 2026-09-21:

- `GET /home` (`getHome`) answers `{date, comingUp, roadmapCount, lead, sources}`. Two
  designed fields are **not** there. `decideNow` is cut for good: `docs/inputs/openapi.yaml`
  puts the queue counts on `Home` and D-23 puts them on `GET /me`, D-23 is the later input,
  and one number with two sources is how two screens come to disagree. `f03-T48` builds
  `counts` and `lastVisitAt` on `GET /me`; nothing reads them from `Home`. `standing` waits
  for the obligation register, which R1 does not have: `c8-home-register-feeds` adds the
  field and the panel with it. Zeros were rejected - "0 gaps" before a register exists is a
  false statement about a bank's compliance, and the first test deploy would have shown it.
  `sources` is nullable rather than the designed object, because a reader without
  `watch.read` gets that panel hidden and never a page-level 403.
- `RoadmapItem` carries `{id, kind, itemType, date, quarter, label, title, status, urgency,
  sourceLabel, changeId, obligations}`. The designed `what`, `soWhat`, `owner` and
  `obligationId` are absent because no R1 branch fills them: `v_roadmap_item` has four
  branches and three of them read tables R1 does not have. Chunk 6 builds the regulatory
  branch alone (`kind` `regulatory`, `itemType` `change_date`); `c8-home-register-feeds`
  adds next reviews and gap targets, chunk 9 adds assessment deadlines and actions, and
  `f03-T74` adds a certificate's expiry and next audit (D-43). Each of those branches brings
  the fields it can fill. `kind=internal` therefore answers an empty list in R1, with 200
  and never 422.
- The other eight home operations are published in their designed shape ahead of the logic
  that fills them and answer 501 `not_built` behind their real gate, so the screens and the
  newsletter agent are built against a committed contract (`c6-home-api-contract`). There is
  no drift to record for them; what each one will do is in its own description in
  `openapi.json`.
- The calendar feed's address is **not** the designed `GET /calendar/{feedToken}`.
  `getCalendarIcs` is served at `GET /api/v1/calendar/feed.ics` with the token as the
  required query parameter `token`, shaped `<prefix>.<secret>` and at most 128 characters
  (D-52, ADR 0045, `c6-feed-contract`). A calendar client sends no header and cannot be
  asked for a passkey, so the address is the whole credential either way; what the query
  string changes is who writes it down. Our access log prints the route and drops the query
  (playbook 4.7, finding H10), while a hosting edge records whole request lines, so a token
  in the path is the invariant "a secret never reaches a log" broken by a third party we do
  not control. This is the one named exception to CONVENTIONS 3.6 and
  `apps/home/tests_contract.py` pins that no other operation takes a credential in its
  query string. The designed path form answers 404 and is not built.
- `createCalendarFeed` takes a body with **no fields**, where the designed
  `CalendarFeedInput` offers `filter` of `all`, `regulatory` or `internal`. A feed carries
  the dates the outside world set and never the bank's own — ADR 0045 lists our own
  deadlines among the things deliberately not in it, and AC-TEN1 says a certificate's
  expiry and next audit never reach the calendar feed — so `internal` would be empty
  forever and `all` could never differ from `regulatory`. The body stays declared rather
  than being dropped, so a client written against the designed contract is told with a 422
  that the choice is gone instead of quietly subscribing to something else. `feed_filter`
  itself survives as the roadmap read's `kind` filter, which does have internal branches
  coming (chunks 8 and 9).
- `HomeCalendarFeed` gains `lastUsedAt`, which the designed `CalendarFeed` does not carry:
  a person needs to see whether an address is in use before revoking it, and it is what the
  idle expiry reads. `revokedAt` is unchanged in shape and wider in meaning — the server
  stamps it when a member leaves, loses `roadmap.read`, is enrolled again or lets a
  subscription go idle, as well as when a person revokes one.
- `createCalendarFeed` refuses a session that is neither recent nor freshly confirmed by a
  passkey, with 403 `step_up_required` (`enforce_recent_sign_in_or_step_up`, the rule the
  passkey routes already use). The designed contract names no such refusal. The address
  outlives the session that asked for it, so without this a stolen access token would leave
  behind a calendar address that answers for months. Revoking asks for nothing of the kind:
  a person whose address has leaked must be able to stop it at once.

## 8. Chunk 5's tenant tables and screen contract (2026-09-20)

**`change_case` (`c5-contract-models-cases`).** Built with R1 columns only:

- The chunk 9 columns of the designed `change_case` are **not built**: `triaged_by`,
  `triaged_at`, `dismissed_reason`, `dismissed_by`, `dismissed_at`,
  `signoff_requested_by`, `signoff_requested_at`, `signed_off_by`, `close_reason`,
  `closed_note` and `closed_at`, together with the two CHECKs that read them and the
  four-eyes CHECK on the sign-off. `c9-case-models` adds them with the workflow they
  guard (CAS-02 to CAS-08). R1 builds creation, the footprint match and the "So what?".
- **`urgency_confirmed` is added**, default false: the designed schema has no such
  column. A case is created with the change's suggested urgency and says, until a person
  triages it, that the value is the agent's suggestion and not the bank's decision
  (Alex's item 1, `q-case-urgency-at-creation` Option A). `urgency` stays NOT NULL as
  designed: every card renders an urgency pill from the moment the case exists.
- **`case_obligation_link` is a new table**, which `schema.sql` lacks: a bank's own
  decision (`accepted` or `removed`, the `case_link_decision` kind) about one suggested
  library obligation link, unique per `(tenant, case, obligation)`. It holds no library
  row and writes none — a library editor confirms the link for the shared library, and a
  compliance officer decides it on the bank's own case (WAT-04, chunk 5 ruling C). A
  removal is stored, never deleted, so the case file can say the bank looked and said no.
- `briefing_week` is the designed `date` (the Monday of the ISO week the case first
  appeared in a briefing), not the boolean the prototype fixture shows.
- No `version` column in R1, so no case write takes `If-Match` and none answers
  `stale_write`; CAS-08's concurrency lands with chunk 9.

**The screen contract (`c5-contract-api-screens`).** Where the built routes depart from
`docs/inputs/openapi.yaml`:

- `GET /changes` (`listChanges`) answers `{items, total}` with `limit` and `offset`
  instead of a cursor page, like every other list (playbook 10): 20 by default, 100 at
  most, and a larger `limit` is a 422 rather than a clamp. A row carries the library's
  facts as `{ref: {key, kind, label}, confidence, suggested}` — the vocabulary row itself
  beside how it came to be on the change — and the reader's own case beside them, never a
  phrase and never a tone. The provenance is kept out of the reference on purpose: every
  vocabulary reference in this API is exactly `{key, kind, label}`, and the presentation
  guard refuses one that is not (NFR-03, NFR-S10). Ordered by key date then first seen,
  both newest first, with the row id as a stable tiebreak; a change with no key date
  sorts last. `footprint` is the single value of §7 (`in`, `all`, `watched`) and the
  designed `inFootprint` pair answers 422 rather than being ignored, because ignoring it
  would hand a client that asked for `inFootprint=false` the opposite feed in silence.
- `GET /changes/{changeId}` (`getChange`) answers the library record — timeline,
  documents, terms and obligation links — plus `inFootprint` and the reader's own bank's
  `case`. The case block carries the category, the urgency and whether a person confirmed
  it, the footprint match, the "So what?" and its confirmation, the bank's own
  obligation-link decisions, and `allowedTransitions`, which is an empty list in R1
  because the workflow that would move a case is chunk 9. Its `flags` and `terms` are
  facts, `{ref: {key, kind, label}, confidence, suggested}`, exactly as a feed row answers
  them, and not the bare references a write response carries (2026-09-21): this is the
  page a person judges a change on, and an agent's suggestion has to read as a suggestion
  where the decision is taken (WAT-03). `changeType` stays a bare reference here, because
  the library stores no confidence and no confirmation for the type itself and this
  response already carries `origin`, `model` and `agentRunId` at the top level for it to
  be read off; an individual flag or scope term has no such field, which is why those two
  had to carry their own.
- `GET /console/changes` (`listConsoleChanges`) is **new**: the console's queue of
  changes carrying a fact nobody has confirmed, under `proposals.review`, with a
  `confirmed=false|all` filter and an authority filter. It joins no case, because a
  platform console session has no tenant; without it the Change facts screen would call
  `GET /changes` and read nothing.
- `POST /changes/{changeId}/case/obligation-links` (`acceptCaseObligationLink`) and
  `DELETE /changes/{changeId}/case/obligation-links/{obligationId}`
  (`removeCaseObligationLink`) are **new**, under `cases.work`: the bank's own decision
  about a suggested link. This fixes the path the UI plan had only proposed.
- `PUT /changes/{changeId}/so-what` (`saveSoWhat`) and
  `POST /changes/{changeId}/so-what/confirm` (`confirmSoWhat`) answer the bank's own copy
  of the "So what?" — `{caseId, changeId, text, confirmed, confirmedAt, confirmedByName,
  isAiDraft}` — rather than the designed case object, because R1 has no case workflow to
  answer. Saving text marks it confirmed: a person who rewrote it has already decided.
- `GET /obligations/{obligationId}/changes` (`listObligationChanges`) answers
  `{items, total, openCount}`: the related-changes panel and the open-change count the
  obligation page shows. `openCount` counts the reader's own cases that are neither
  closed nor dismissed, so two banks reading one obligation see different numbers.
- `GET /authorities` (`listAuthorities`) is the list chunk 3 cut to chunk 5 (ruling E),
  answered as a plain array like the other reference reads: `{id, key, shortName, name,
  jurisdiction{key,kind,label}, url}`. A person with `library.read` or an agent's key with
  `library:read`.
- `GET /obligations/{obligationId}/sources` (`getRecordSources`) is **new**: a live
  record's citations with their source document, url, content hash and fetched date. It is
  how an agent key holding `library:read` alone re-checks a library record against the page
  it came from; the correction it finds is a proposal, never an edit (AGT-01, item 3,
  PRO-01).
- `GET /sources` and `GET /sources/coverage` also accept a console session holding
  `sources.manage`, so the read-only console Sources page calls a real route. A console
  session has no tenant and therefore no `watch.read` (ruling 3).

## 9. Chunk 6's tenant tables (2026-09-21)

**`briefing`, `briefing_item` and `calendar_feed` (`c6-home-models`).** Built as
`schema.sql` §9 designs them, with three departures and one addition:

- `briefing_item` is keyed on a uuid `id` with `UNIQUE (briefing_id, case_id)` beside it,
  rather than the designed composite primary key `(briefing_id, case_id)`. Django addresses
  a row by one column, and the unique constraint says exactly what the composite key said.
- `calendar_feed.token_hash` is `varchar(64)` rather than `text`: a SHA-256 in hex is
  exactly 64 characters, and a column that cannot hold more cannot hold anything else.
- **Added:** `briefing_item` carries the append-only trigger, which `schema.sql` does not
  give it. "A later change to the feed does not alter a sent briefing" is HOM-S3's last
  line, and a ledger nobody can rewrite is the only way to mean it. The `briefing` row
  itself stays ordinary, because `email_sent_at` is stamped when the mail goes out and is
  not known when the snapshot is taken.

All three tables carry `tenant_id` under enabled and forced row-level security with the one
`tenant_isolation` policy, and none is `mixed`: a week that holds nothing for one bank holds
three reforms for another, because the footprint and the cases behind it are that bank's
own. `apps/shared/tests_rls.py` names them in its tenant-only list.

**`calendar_feed` again (`c6-feed-contract`, home 0002).** The table was built from
`schema.sql` §9 while q-feed-token was still open. D-52 and ADR 0045 answered it, and the
row now holds what that answer needs:

- `token_prefix` is new, 16 characters and unique, and `token_hash` keeps the secret's
  SHA-256 without its unique index. The address is `<prefix>.<secret>` with 256 bits of
  secret: the prefix finds the row in one indexed read and the hash is what is verified, the
  same shape `api_key` already uses. The prefix is unique across every bank rather than
  within one, because the row is found before any bank is known.
- `last_used_at` is new. The idle expiry reads it and a fetch stamps it, throttled the way
  an API key's stamp is, so a subscription nobody has fetched for `CALENDAR_FEED_IDLE_DAYS`
  can be told from one in daily use.
- `filter` is **removed**, with the `feed_filter` enum the designed column named. A feed
  carries the dates the outside world set and never the bank's own (ADR 0045's own list of
  what it does not carry; AC-TEN1), so `internal` would be empty forever and `all` could
  never differ from `regulatory`. The accepted recommendation behind D-52 says the filter
  column is not built, in those words.
- `calendar_feed` joins the identity-lookup clause as its fifth table, beside `invitation`,
  `membership`, `user_session` and `api_key`. A calendar client presents no session and no
  key at all, so the subscription has to be found before a tenant is known. The clause is
  `FOR SELECT` only: since H15 the write rule is the session's own zone, so nothing can be
  written through the opening, and `IDENTITY_LOOKUP_TABLES` in `apps/shared/tests_rls.py`
  pins the list at five.
- `login_event.event` gains `feed_used` (identity 0004). A fetch of a subscribed feed is
  the use of a credential, so it belongs in the security log beside `key_used`; the row
  records the subscription's owner and never the address, and the write is throttled
  because a calendar client polls for years.


## 10. A source check says what kind of check it was (2026-09-21)

`POST /agent-runs/{runId}/source-checks` is designed to carry `sourceName`, `status`,
`checkedAt`, `itemsFound` and `error`. The build adds three fields: `kind`, and the pair
`subjectType` and `subjectId`.

A sweep of a source and a re-check of one record are both checks, and the route validates
the pairing between them — a sweep names a source and no subject, a re-check names the
record it re-read. Without `kind` a re-check cannot be sent at all, and the rule the route
exists to enforce (a re-check never freshens a source's coverage, because asking the same
page again is not the same as the page having been read) has nothing to read. The fields
are additive: a caller that sends only the designed five is a sweep, exactly as before.

Reported rather than decided quietly: the task that found it judged an additive field the
brief itself names too small to stop on, and said so in its commit body. Recorded here so
the drift gate and the next reader agree.


## 11. The AI output log, and who reports what a model was (2026-09-21)

`ai_generation` (schema v0.3 line 794) is built as designed with four departures, all
additive, in `apps/governance/models.py` and `governance/0001_ai_generation.py`:

- `input jsonb` is not built. The designed column holds "question, as_of, ids of the chunks
  given to the model", which is the prompt in pieces; the build stores `prompt_template`
  and `prompt_hash` instead and nothing else of the input, so a bank's own question can
  never be read back out of a table every bank reads (NFR-04, D-07). The record the call was
  about is still named, by the designed `subject_type` and `subject_id`.
- `prompt_template`, `input_tokens`, `output_tokens` and `cost_minor` are added: AUD-02 asks
  which prompt produced an output, and billing reads the usage (money as an integer minor
  unit, playbook 4.3). The designed table has none of the four.
- `model_metadata_reported_by_agent` is added (D-66, Alex, 2026-09-21). The "So what?" is
  written by the agent that read the change and filed with the change, so the model and the
  model version on that row are the agent's account of itself rather than a measurement
  bleqq took, while an Ask answer's are read off the provider's own response by
  `apps/shared/ai.py`. One boolean is what lets a reader tell the two apart. In R1 every
  agent is bleqq's own, so this is a reporting boundary; it becomes a trust boundary the day
  a bank runs its own agent against the write routes, which is R2's agent-access work. The
  column is stored rather than derived from the purpose, because it is the boundary itself
  and a purpose added later must not inherit somebody else's answer.
- `citations` keeps its designed name and type, and its shape is `AiCitation`
  (`{label, url}`) rather than the designed `{obligation_id, version_no, instrument, ref}`.
  R1's only producer is the drafted "So what?", whose sources are public pages and never
  library records; chunk 7's Ask adds what it needs to the same JSON column.

`GET /ai-generations` (`listAiGenerations`) ships with the designed `purpose` and `status`
filters and the shared `limit`/`offset` pagination. `subjectId` and the `feedback` fields
are chunk 7's (`c7-ai-log-backend`), which is also the one that lets a platform reader move
a library row's review state: a bank never does, because the library row has no tenant and
the split write policy refuses it (chunk 5 ruling I).

### The "So what?" arrives with the change, not from a second call (D-66)

`POST /changes` (`createChange`) and `PATCH /changes/{changeId}` (`updateChange`) each gain
one optional object, `soWhat`, which the designed contract has on neither. It carries the
drafted answer, the model and the model version that wrote it, the prompt's name and hash,
and at least one public citation.

The design assumed bleqq would draft the "So what?" itself from a handler watching for new
changes. Alex decided on 2026-09-21 (D-66) that the agent which read the source writes it
and files it with the change, because that agent has just read the source and a second call
of ours over the same facts is a second moving part, a second cost and a second thing to
keep in step. There is nowhere else for the words to arrive, so the two write routes carry
them. `POST /changes` also loses the bare `soWhatDraft` string the build had put on its
body: words with no model, no model version and no citation cannot become the
`ai_generation` row AUD-02 asks for, so the object is the shape and a bare string is a 422.
`WatchChange.soWhatDraft`, the response field, is unchanged.

### A confirming agent's decision is logged under a purpose of its own (D-80, 2026-09-23)

`ai_purpose` gains `agent_review`, which the designed kind does not have: a confirming
agent's decision on another agent's work — approving, correcting or rejecting a proposal,
or confirming a watch item's curation — is a model call, and AUD-02 asks that it be logged
with the model behind it. None of the designed purposes fits, because each names something
a model drafts, and a reader of the log must be able to tell a machine's decision from a
machine's draft. The decision arrives with one `AgentDecision` object (model, model
version, the prompt's name and hash, the output and at least one citation), the shape of
D-66's `soWhat` with `output` for `text`. A check constraint holds that its row is marked
`model_metadata_reported_by_agent` and names the run and the record decided. The designed
log is read by every bank for its library rows; an `agent_review` row is left out of that
read, because it is about the proposal queue, where a bank sees only its own filings, and
the platform alone reads it (governance 0002). `AiCitation` moves from `apps/governance/schemas.py` to
`apps/shared/schemas.py` beside it, unchanged, because the shared shape cites with it and a
governance import from there would be a cycle.

### The log's read narrows to one record and carries the review and the feedback (2026-09-23, ai-log-read)

`GET /ai-generations` (`listAiGenerations`) gains the designed `subjectId` filter, and
`AiGenerationRow` gains `feedback`, `feedbackNote` and `reviewedBy` (`{id, name}`), beside the
`status` and `reviewedAt` it already carried. The designed table has `feedback`, the
reviewer and the review time; the read now returns them. Two departures, both about the
shared "So what?":

- A library "So what?" row's `status`, `reviewedBy` and `reviewedAt` are **computed for the
  reading bank** from its own `change_case` (`so_what_confirmed_by`, `so_what_confirmed_at`),
  and nothing shared is written (D-62; resolves chunk 5 ruling I). The designed column is one
  review state per row, but that row is every bank's, and one bank's confirmation must not
  read as another's. A case settles the newest draft of the change logged by the time it was
  confirmed: `confirmed` when the bank's words are the draft's, `edited` when the bank
  rewrote them, and `draft` for every other draft of that change. The `status` filter reads
  the same computed state. The stored columns stay the platform's.
- `feedbackNote` is added: the reader's own words with a verdict (`POST
  /answers/{answerId}/feedback`, SRC-05) are stored beside the answer and returned only on
  the bank's own row. The designed table has the verdict alone.

`agent_review` rows stay out of a bank's read (D-80).

## 12. Two reads that are on `main` in a shape of their own (review-fixes, 2026-09-23)

`backend/scripts/contract_drift_pending.txt` still listed both as chunk 1 work to come.
Both are built, and each departs from the design on purpose, so they are explained here
instead and their pending lines are gone.

- `GET /me/whats-new` (`getWhatsNew`) is not built and is not coming: `GET /library-updates`
  (`listLibraryUpdates`, 622ce06) answers the same question, with the designed
  `POST /me/visit` (`markVisit`) moving the reader's bookmark. The designed read was one
  object, `{since, changes[], newObligationVersions[], decidedProposals}`, from a `since`
  that defaulted to the last visit. The built read lists what an approved proposal applied
  to the shared library since the reader's own bookmark, grouped by the day it arrived in
  the bank's time zone, as `{since, days[{date, items[]}], total}` paged with `limit` and
  `offset`, filtered by `kind`, and cut to the bank's footprint unless `outsideFootprint`
  asks otherwise. It takes no `since`: the start is the bookmark, or the default window for
  a reader who has never marked the library as seen. Each row is titled by the library
  record it touched and names nobody, so a change another bank asked for reads like any
  other. It sits beside the inventory under `library.read` rather than under `/me`, because
  what it lists is library facts; only the bookmark is the person's, and it stays on
  `POST /me/visit`. The designed `decidedProposals` count is not carried.
- `GET /audit-events` (`listAuditEvents`, built 2026-09-19 in cfc3bf40) answers
  `{items, total}` paged with `limit` and `offset`, like every other list (playbook 10),
  instead of the designed cursor page `{items, nextCursor}`. Its filters are `subjectType`,
  `subjectId`, `actorId`, `from` (inclusive) and `to` (exclusive): `actorId` matches any
  actor, a person or an agent, where the designed `actorUserId` named a person only, and the
  designed `action` filter is not built.

## 13. What an Ask statement says about a pending change (2026-09-23, search-ask-backend)

`AnswerStatement` gains two optional fields the designed contract does not have, both
additive: `pendingChangeInForceOn`, the day the flagged change takes effect as a plain
date, and `pendingChangeInForceOnPrecision`, how exact that day is (`day`, `month`,
`quarter`, `year`). The design's statement names a pending change by id and label only,
which leaves the screen's "Change pending: in force 1 Oct" (SRC-S4) with nothing to print
but a phrase it would have to invent; a legal date is a plain date with its precision
(playbook 4.3), so the two travel together. Both are empty exactly when `pendingChangeId`
is.

What is flagged is also narrower than "an open change": only a change the library
confirmed affects a cited obligation (a confirmed `change_obligation` link, never an
agent's suggestion), still active, whose type's lifecycle kind moves the law on its key
date (`adopted`, or `in_force` from a later day) and whose key date falls after the
answer's `asOf`; of several, the earliest. A proposal, a supervisory statement or a
recurring date moves no law on its date, and flagging one would warn a reader about a rule
that may never exist.

`Answer.model` is empty when no model was asked: a question no library passage supports is
answered `noAnswer` at once, with no model call and so no `ai_generation` row.

`ai_generation` gains `stop_reason` (`governance/0003_ai_generation_stop_reason.py`) and
`AiGenerationRow` gains `stopReason`, neither of which the designed table or contract has:
how a call bleqq made ended, the provider's own stop reason when the model finished,
`aborted` when the caller stopped reading first and `failed` when the model failed once
asked (D-82). A streamed Ask answer is logged however it ends, and without the column a
call cut short read in the log exactly as a finished one. Empty on a row an agent filed.

## 14. A confirming agent's approval or rejection carries its decision and its run (2026-09-23, proposals-agent-decision-log)

`ProposalApproveBody` and `ProposalRejectBody` (`approveProposal`, `rejectProposal`) each
gain two optional fields the designed `{note}` and `{reason}` bodies do not have:
`decision`, the `AgentDecision` section 11 describes (D-80), and `agentRunId`, the run the
decision was made in. Both are required from a key bound to an agent and refused from a
person: a key's decision without `decision` answers 422 `validation_error`, without
`agentRunId`, or naming a closed run, 422 `run_not_open`, and naming a run another key
opened, another agent's included, 404 `not_found`, as a proposal's `agentRunId` already
does at `createProposal`; a person's body naming either answers 422 `validation_error`.
The run is checked against the deciding key rather than its agent, the same rule every
other agent write follows (`runs.require_open_run_of_key`), which is the stricter reading
of D-80's "a run of the deciding key's own agent". In the decision's own transaction the
write logs one `ai_generation` row under `agent_review` naming the proposal and the run,
and the decision's audit row gains `agentRunId` beside `reviewingApiKeyPrefix`.
`ProposalRejectBody` becomes a strict write body like the approve body: a field it does
not name answers 422 rather than being dropped. The reject route keeps
`{rejectionCode, note}` (section 7) and is documented to the API standard.

## 15. A bank reads and closes its own problem reports (2026-09-23, problem-reports-backend)

- `GET /problem-reports` (`listProblemReports`) serves a bank's own session only, under
  `problems.report`, which every member holds and no platform role does. The designed
  `x-roles` list `library_editor` and the designed read is the console's; since D-50 a
  report stays inside the bank that filed it, so a platform session is refused 403 naming
  `problems.report`. Reach inside the bank is `proposals.create`: its holder lists every
  report of the bank, every other member lists the reports they filed (the
  docs/TODO_FOR_alex.md default of item 3; no permission is added). Paging is `limit` and
  `offset` with `total`, as on every list here, not the designed `cursor` and
  `nextCursor`. Filters are `status`, `subjectType` and `subjectId`. A row carries
  `description` (the reporter's words), `subjectTitle` and `subjectReference` (the record
  named in the caller's language), `versionNumber` and `language` (what was on screen),
  `reporter`, `closedBy` and `closedAt` as `{id, name}` and a timestamp, and
  `resolutionNote`; the designed `reportedBy`, `reportedAt` and `resultingProposalId` are
  `reporter`, `createdAt` and nothing, because no proposal ever links to a bank's report.
- `PATCH /problem-reports/{}` is `closeProblemReport`, not the designed
  `resolveProblemReport`, and its body is `{status, resolutionNote}` with no
  `resultingProposalId`. The status is `answered`, `fixed` or `rejected`, the kinds chunk 3
  wrote (`ReportStatus`); the designed `accepted` and a return to `open` do not exist. The
  note is required. The reporter closes their own report and a `proposals.create` holder
  any of the bank's; anyone else is 403 naming `proposals.create`, and a second close is
  409 `already_closed`. It answers the closed report as a `listProblemReports` row. The
  close records `problem_report.closed` with the states only, never the words, and no
  step-up or second person is asked: it changes nothing outside the report.
- An agent's key on either route answers 401 `unauthenticated`, as every session-only
  route does, rather than the 403 AUD-S5's wording allows: a key is not a session, so it is
  refused before any gate runs. Nothing about the key is revealed either way.
- `problem_report` loses `resolved_by_proposal` and gains `resolution_note`, `closed_by`
  and `closed_at` (library 0009), with a check constraint that a report is open with none
  of the three or closed with all three and a note. `tenant_id` stays nullable and the
  table stays mixed until Alex decides otherwise (docs/TODO_FOR_alex.md, item 3).

## 16. A bank switches its own AI features off with a passkey (2026-09-23, ask-switch-route)

`PUT /tenant/ai` (`setTenantAi`) and `TenantOut.aiEnabled` are not in the designed contract,
which has no way to reach D-07's per-bank switch: `tenant.ai_enabled` (shared 0007) was read
before every model call and nothing set it. The route takes `{enabled}`, a strict boolean
and nothing else, and answers the profile as it now stands. It needs `security.manage` and a
passkey step-up, because whether a bank's own words may leave it for a model is a security
change (CLAUDE.md section 5), and it is recorded as `tenant.ai_switched` with the state
before and after and the step-up assertion. It is a route of its own rather than a field on
`PATCH /tenant` (`updateTenant`), which stays as designed, so a profile edit never needs a
passkey and never moves the switch. The switch covers the bank's own Ask and drafts only; a
platform run is in no bank's zone and never reads it (owner item 14).

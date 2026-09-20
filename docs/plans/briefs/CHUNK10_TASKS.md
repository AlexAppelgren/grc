# Chunk 10: tasks

Written 2026-09-20 by the planning session (read, plan, parallelism and coverage critiques, revise). Each task runs in its own worktree or cloud session (`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on `main`. The task ids are the `c10-` package ids of `docs/plans/PARALLEL_PLAN.md` section 3.3, plus `f03-T78` to `f03-T81` from `docs/plans/briefs/FEATURES_0_3_TASKS.md`; nothing is renamed, added or dropped. Packages estimated at 50 minutes or more are split into halves, keeping the package id as the stem, the way chunk 3 split T11 and chunk 4 split T16 and T24: eleven when the plan was written and five more on the review of 2026-09-20. Where `-b` was already taken by the package's other half, the third task takes the next free letter (`-c`); the wave table and the depends-on fields give the order, never the letter. The splits are listed with their reasons under "Changes from `PARALLEL_PLAN.md`".

## Revised 2026-09-20

The plan review's findings, each with the edit that closes it:

1. **HIGH — a route-gating mechanism that does not exist.** The plan told `c10-notifications-api-a` to "add no entry to `UNGATED_BY_DESIGN`: every route has an ownership rule declared in its route entry". `apps/shared/tests_route_permissions.py` accepts only `@requires_permission`/`@requires_scope` or an `UNGATED_BY_DESIGN` entry with one of its five reasons and a note. The contract tasks now name the entries they write: `SELF` for the three notification routes and for `GET /me/comments`, `LOGIC_GATE` for `GET /comments` and `POST /comments`, each with its sentence; `PATCH` and `DELETE /comments/{commentId}` carry the decorator. "Lists no ungated route" and the security review's "no new `UNGATED_BY_DESIGN` entry" question are gone.
2. **MEDIUM — `digest_weekday` had no owner.** `schema.sql` lists it in the `tenant.settings` keys beside the four columns `c10-workflow-policy` builds, and `c10-digest-b` reads it. It is now a fifth workflow column (default Monday), with its field on the design card and on `/admin/workflow`.
3. **MEDIUM — COL-S3 named a feature built six waves later.** `c10-reminders-escalation-a` proves COL-S3 in wave 4, but its Gherkin says "a digest scheduled for Monday 08:00" and the digest is `c10-digest-b`'s. The task now owns COL-S3's Gherkin in `collab/app.md` and rewords it to the reminder beat before un-skipping the test, so the test and the scenario say the same thing (CLAUDE.md §10); the scenario keeps its point, the tenant timezone across a daylight saving change.
4. **MEDIUM — the mail guard allowed only "a library title".** Reminders, escalation and the digest name an action, a case or a register entry. The allowed context is now a record title (library or tenant record), a date, a count, a person's name or a link; the refusal list keeps body, note, assessment, summary and comment.
5. **MEDIUM — the tagging tasks took `taxonomy/api.py` with no key.** `c8-vocab-scales-reasons` and `c12-config-policies` hold `taxapi`. Both tagging tasks now name `taxapi` and `libread`, and `c8-vocab-scales-reasons` is a precondition.
6. **MEDIUM — two missing dependencies.** `c10-fe-comments-panel-a`'s mention control calls `GET /reference/people`, so it depends on `f03-T52`; `c10-fe-collab-feature`'s `api.ts` calls `PATCH /me`'s preferences, so it depends on `c10-notification-prefs`.
7. **MEDIUM — TEN-S4's journey was attributed to chunk 9.** CHUNK8_TASKS.md gives TEN-S4 `@e2e` to `c8-ui-out-of-office`; the scenario table says so.
8. **MEDIUM — editing a comment dropped the previous text.** Ruling 10 now keeps it: `c10-collab-models-a` adds the append-only `comment_revision` table with its trigger, `c10-comments-api-a` writes the replaced text there in the edit's transaction, and the audit row still carries ids only (CLAUDE.md §5, rule 13).
9. **LOW — five tasks were still whole packages.** `c10-notifications-api-a`, `c10-mail-catalog`, `c10-e2e-seed`, `c10-fe-bulk-tagging` and `f03-T78a` are split into halves like the other eleven, with no wave added.
10. **Questions for Alex.** q-comment-subjects and three confirmations stay, a fourth is added for the stored record title a member who has lost the read permission still sees, and the two the repository had already settled are dropped with their sources named.

## Scope, rules and defaults

Chunk 10 plan: comments and mentions on a record, the notification inbox with per-person preferences, reminders before due dates, escalation to the head of the owner's department, the weekly digest, out-of-office delegation, and tenant tagging with the create-or-suggest picker. `Build_Plan.md` gives the chunk COL-01, COL-02, VOC-03 and VOC-08, plus HOM-05's comments and mentions; PRD 0.3 adds `f03-T78` to `f03-T81`. COL-04's own routes are built in chunks 8 and 9 (D-26); chunk 10 builds only the notifications that participation produces. COL-03 (follow a record) is R3 and belongs to chunk 13. The plan has 43 tasks in 16 waves, about 19 agent-hours of package work plus review.

PRECONDITIONS: WHAT MUST BE ON MAIN BEFORE WAVE 1
- Consolidation: `p03-consolidation` (the PRD 0.3 requirement rows, the scenario stubs and the coverage gate this chunk closes).
- Chunk 5: `c5-outbox-cursor` (the one ordered cursor over `outbox_event`, which dispatches to the worker per tenant; ruling 9 of the parallel plan forbids a second relay), `c5-contract-models-cases` (`ChangeCase`, the first subject a comment is written against), `c5-contract-models-watch` (`RegulatoryChange`, the library title a notification carries).
- Chunk 6: `c6-briefing-backend` (the first server-rendered mail and the first `CELERY_BEAT_SCHEDULE` entry, which `c10-mail-catalog-a` extends, ruling 21), `c6-home-backend` and `c4-mark-seen` (the `GET /me` shape that `c10-notification-prefs` adds to).
- Chunk 8: `c8-tenants-api-contract` (the tenant settings contract the workflow policy fills), `c8-ten-teams` and `f03-T51` (teams, departments and `org_unit.head_user_id`, without which there is no head to escalate to), `c8-ten-out-of-office` (the out-of-office window and the delegate column `c10-delegation` routes to), `f03-T62` (the My work screen the comments panel is added to), `f03-T52` (`GET /reference/people`, the read the mention control draws on), `c8-vocab-scales-reasons` (which holds `taxapi`, the key both tagging tasks take: the tagging routes cannot be written while it is open).
- Chunk 9: `c9-case-models`, `c9-case-contract` and `c9-e2e-seed` (a case with an owner, a due date and a sign-off request: the records reminders, escalation and the digest count), `f03-T76` and `f03-T77` (case participants and the case sources on My work, which `f03-T78` notifies about).
- Chunk 3 and chunk 4: the library read chain and the inventory (`c3-provision-read`, `c3-fe-obligation-versions`, `c3-fe-instruments`), which the tagging routes filter and the tagging screens act on; `c4-console-shell` and through it `x-frontend-split`.
- Why it cannot wait: every notification names a record, every reminder counts a date and every digest line is a My work row. Without chunks 8 and 9 there is nothing to remind anybody about, and a screen would be built against a stub, which rule 3 of the parallel plan forbids.

WHAT IT DELIVERS
- COL-01, comments: `GET/POST /comments` and `PATCH/DELETE /comments/{commentId}` on the record kinds that have a panel, with mentions, the shared-visibility line in the composer (D-22, D-60), and the proof that comment text reaches no log, no Sentry event, no audit before or after value, no outbox payload, no webhook, no notification title and no email.
- COL-01 on My work: `GET /me/comments?about=written|mentioned`, paginated, filtered by the subject's read permission, with the permission-limited kinds named (`f03-T80`).
- COL-02, notifications: one `notify()` with one recipient check (D-34) writing every notification row in the product; the inbox (`GET /notifications`, mark one read, mark all read); per-person preferences on `PATCH /me`; reminders at the tenant's lead times; escalation after the threshold to the head of the owner's department and to the escalation role; the weekly digest in each person's language, built on the My work service (`f03-T81`) so "my open items" keeps one definition.
- COL-02's workflow policy: the reminder lead days, the escalation threshold, the escalation role, the digest weekday and the triage target as tenant columns of their own, replacing the designed `tenant.settings` blob.
- TEN-04's second half: while a person is away, their reminders and approval requests reach the delegate, who gains no permission.
- VOC-03: the create-or-suggest picker on the obligation page, over the routes chunk 2 already built.
- VOC-08: bulk tagging from the inventory list with a preview and one audited batch, and the tenant-tag filter the inventory read deferred.
- J-8 extended: tenant B sees none of tenant A's comments and receives none of its notifications.
- The chunk's own security review, its fix package and its close.

RULINGS WHERE THE SOURCES DISAGREE
1. **One writer for notification rows.** `docs/inputs/openapi.yaml` and `schema.sql` describe the `notification` table but not who fills it, and chunks 9, 11 and 13 all want to. `notify()` in `backend/apps/collab/logic.py` is the only code that creates a `Notification`, and `c10-collab-models-b` builds it with D-34's recipient check inside. A guard test walks production code and fails on any `Notification.objects.create`, `bulk_create` or `Notification(` outside that module. This is why `c9-triage`, `c9-signoff`, `c11-run-scheduler`, `c13-follow-notify` and `c13-saved-search-notify` all depend on `c10-collab-models`: the resolver exists before any producer.
2. **One recipient check, extended, never a second one.** `f03-T78`'s title says "through one recipient check". It does not build a resolver: `c10-collab-models-b` builds it, and `f03-T78b` adds the three PRD 0.3 kinds to the subject registry it reads. A second resolver would let one kind reach a deactivated member while another did not.
3. **A subject registry decides who may read what.** COL-01 says "any record" and `subject_type` has 50 values, most of which are tables R2 does not have. `c10-comments-api-a` builds one registry in `collab/subjects.py` mapping a subject kind to its read permission and its row lookup, and `POST /comments` answers 422 `unsupported_subject` for a kind not in it. R2 registers `obligation`, `tenant_obligation`, `change`, `change_case` and `action`. The same registry serves `notify()`, `GET /me/comments` and the mention check, so "can this person read this record" is written once. A later chunk adds a kind by adding one row with its read check, and a registry test fails on a row missing either half. Recorded in INPUT_DELTAS §7 with q-comment-subjects under Open questions.
4. **The tenant tag filter is this chunk's.** INPUT_DELTAS §7 says of `GET /obligations` that "the tag filter is deferred". Chunk 10 delivers it as two filters, because the row already carries two kinds of tag: `tag` over the library tag keys already on the row, and `tenantTag` over the tenant's own tag keys, with the row gaining `tenantTags[{key,kind,label}]`. An API key with no tenant never sees `tenantTags` and gets 422 `unknown_filter` for `tenantTag`.
5. **VOC-03's backend is already on `main`.** `suggestVocabularyRow`, `createVocabularyRow`, `listVocabularySuggestions`, `declineVocabularySuggestion` and the near-duplicate check landed with chunk 2; `test_voc_s6` and `test_voc_s7` are green and VOC-S7's journey is green. `c10-tagging-api` therefore builds tagging and VOC-08 only, and `c10-fe-suggest` builds the picker component and VOC-S6's journey only. Neither re-implements the routes.
6. **Workflow policy is columns, not a blob, and it carries the triage target.** INPUT_DELTAS §7 replaces the designed `tenant.settings` jsonb with explicit columns and says the reminder, escalation and retention settings land with the workflow policy. Retention is chunk 12's (`c12-retention-contract`); chunk 10 adds `reminder_days_before`, `escalate_after_days`, `escalate_to_role`, `digest_weekday` and `triage_target_hours`. `digest_weekday` is included because `schema.sql` lists it in the `tenant.settings` keys beside the reminder and escalation settings, `c10-digest-b` reads it to pick the day, and no other package owns a tenant workflow column. The triage target is included although COL-02 does not ask for it: `schema.sql` §16 says `change_case.triage_due_at` comes "from the tenant's triage target", `c9-triage` reads it, and this is the package that owns the tenant's workflow columns. Splitting it across two chunks would give the same setting two homes.
7. **Escalation has two recipients, not one.** PRD 0.4 COL-02 says "escalation to the head of the owner's department"; `schema.sql` has `escalate_to_role`; COL-S2 says "the head of the department of the owner's team **and** the compliance officer are notified". All three hold together: escalation notifies the head of the owner's department (`org_unit.head_user_id`, `f03-T51`) and every active member holding the tenant's `escalate_to_role`, each once, through the same recipient check. Where the department has no head, the role holders alone are notified and the escalation records that the department had no head.
8. **The workflow policy gets its own admin section.** `UI_Implementation_Plan.md` puts reminders and escalation on `admin-organisation.html`. That screen is `c8-ui-organisation`'s, gated by `members.manage`, while the workflow fields are gated by `workflow.manage`, so sharing it would both serialise two chunks on one component and show a member fields their permission does not cover. `c10-fe-workflow-policy` builds `/admin/workflow` with its own feature directory and its own catalog namespace, and the UI plan row is corrected by the close.
9. **A subject kind and id ride in the query string; a body never does.** `GET /comments?subjectType&subjectId` and `GET /me/comments` carry kinds and ids, which the access log may keep without harm, and that is why the reads are shaped that way. Every write that carries text or a key that must not be logged — `POST /comments`, `PATCH /comments/{id}`, `POST /taggings` and the batch routes — carries it in the body, the rule INPUT_DELTAS §7 set for the market keys after finding F29 and H10. No chunk 10 route puts a comment body, a tag label or a token in a path or a query string.
10. **A comment is edited in place, and the text it replaces is kept.** `schema.sql` gives `comment` an `edited_at` and `openapi.yaml` declares `editComment`, so the row the API returns is edited rather than versioned. Nothing overwritten (CLAUDE.md §5) still applies to the text: an edit writes the previous body to an append-only `comment_revision` row before the new one lands, in the same transaction, and the audit row carries the comment id and the revision id only, because it may not hold tenant content (rule 13). An edit is the author's own, inside `COMMENT_EDIT_MINUTES` (a setting, default 15); after that the author may delete but not edit. A delete is soft (`deleted_at`): the row stays for the tenant export, and the API stops returning its body. Revisions are the tenant's own history: no route returns them, and `c12-exit-export` and `c12-retention-contract` carry them with the comment.
11. **Notifications ignore the regulatory scope.** HOM-05 says the footprint never hides a person's own items. The recipient check filters on active membership and read permission only; a record outside the tenant's scope still notifies the people responsible for it. FP-S4 is unaffected: no chunk 10 surface is a footprint-filtered list.
12. **The digest is composed once and sent once.** Ruling 27 of the parallel plan splits them: `f03-T81` builds the digest's open items on the My work service, `c10-digest` composes and sends the mail. Neither defines "open items" a second time, and a test pins that the digest and `GET /me/work` return the same ids for the same reader.

DEFAULTS TAKEN (each stated in its commit body, and copied into `docs/TODO_FOR_alex.md` by `c10-close`)
- Reading comments needs a member session plus the subject's read permission; writing one also needs `comments.write`, which PRD §6 gives every role. A reader who cannot read the subject gets 404, never 403 and never an empty 200, so the answer says nothing about whether the record exists.
- Editing and deleting are the author's own rows only; nobody else may edit or delete a comment, and no permission grants it. A tenant admin who needs a comment gone raises it with support, which the tenant export and chunk 12's retention cover.
- A mention notifies only a member who could read the subject at send time (COL-S12's Johan). A mention of a person who cannot read it is stored on the comment and notifies nobody; the composer shows who was not reachable, by name, never why.
- Notifications are in-app by default. Only reminders, escalations and the weekly digest leave by mail, because only those need to reach a person who is not looking at the product. `notification.emailed_at` is set by the task that sent the mail, in the same transaction.
- `MembershipNotificationPrefs` is `{weeklyDigest, reminders, mentions, assignments}`, each a boolean defaulting to true, stored on `membership.notification_prefs`, which already exists. A muted kind writes no notification row and sends no mail; it never hides the record, and it never mutes an escalation, which is the tenant's control rather than the person's.
- Reminder lead days default to `[3]`, the escalation threshold to 5 days, the escalation role to the compliance officer, the digest weekday to Monday and the triage target to 48 hours. Each is a tenant column with a platform default in settings and an env override, per playbook 3.
- A reminder is sent at most once per person, per record, per lead day, proved by an `email_message` row with its template, subject kind and subject id; the second run the same day finds it and sends nothing. `email_message` is the only idempotency key, so a retried worker does not double-send.
- Reminders, escalations and the digest all run on the tenant's timezone in `@tenant_task`, from one hourly beat entry that picks the tenants whose local wall time has reached the configured hour. A daylight saving change shifts the UTC firing, not the local hour.
- The digest goes to every active member with `weeklyDigest` on, on the tenant's `digest_weekday`, in the member's locale, listing the My work buckets with their counts and at most `DIGEST_MAX_ITEMS` (20) rows, each a title and a link.
- Mail text is a server-side catalog in `backend/apps/collab/mail_strings/`, en and sv only, beside chunk 6's briefing mail. `c13-i18n-server` adds da, nb and fi. A missing string falls back to en and logs the key, never the text.
- Delegation routes reminders and approval requests only; mentions, the digest and read-state stay with the absent person, because a mention is addressed to a human being and a digest is that person's own list. The delegate needs the approve permission themself (parallel plan §7.2); delegation routes work and grants nothing.
- Tagging a record is gated by `vocab.manage` (parallel plan §7.2), applies only to `obligation`, `tenant_obligation`, `change` and `change_case`, and writes only `tagging` rows in the tenant zone. Bulk tagging caps at `BULK_TAGGING_MAX_RECORDS` (200) per batch and writes one audit event holding the tag key and the record ids.
- No chunk 10 write asks for a step-up. Playbook 4.2 lists none of them, `UI_Implementation_Plan.md` marks `PATCH /tenant` "Step-up: no", and the workflow policy is a workflow control rather than a security control.
- `GET /notifications` and `GET /me/comments` use the shared pagination (default 20, max 100); `GET /comments` returns a record's comments oldest first, paginated the same way.

CUT, WITH REASONS
- COL-03, following a record, and `COL-S4`: R3, chunk 13 (`c13-follow-contract`, `c13-follow-notify`). The stub keeps its chunk name.
- COL-04's participant routes and `COL-S6` to `COL-S9`: chunks 8 and 9 (D-26). Chunk 10 owns only `COL-S10`, the notifications participation produces.
- The `proposal_waiting` notification kind: nothing produces it in R2. Today's "Decide now" counts waiting proposals on `GET /me` (D-23), which is the surface the kind was for. It stays in the kind list with its chunk named.
- The `saved_search_hit` kind: chunk 13 (`c13-saved-search-notify`).
- Webhook and SIEM delivery of notifications: chunk 13 (`c13-int-contract`), which adds delivery targets to the one cursor and adds no relay of its own.
- Retention of comments and notifications: chunk 12 (`c12-retention-contract`), under Alex's ten-year answer. Their place in the full tenant export is `c12-exit-export`'s, which already depends on `c10-comments-api`.
- A notification digest email per kind, an unread badge count endpoint and a "snooze": nothing in COL-02 or the design asks for them. The bell reads the unread count from the first page of `GET /notifications?unread=true`.
- Comment reactions, threads and attachments: not in COL-01 and not designed.
- Comments in search and in Ask: `data-model.md` §14 says search covers the library only in version 1, and the invariant forbids tenant content reaching an unapproved model endpoint. Nothing in chunk 10 embeds or indexes a comment.
- VOC-04, VOC-05 and VOC-06 (tenant statuses, scales and reason lists): chunk 8 (`c8-vocab-scales-reasons`), although they share the vocabulary screens with VOC-03.

PLAN-WIDE RULES
1. **Slots.** Every backend and E2E gate runs inside the task's slot: `set -a; . ./.env.worktree; set +a`. A cloud session runs `bash scripts/cloud-setup.sh` (with `--e2e` where the gates include E2E) instead.
2. **Generated files.** No task commits `openapi.json`, `frontend/src/types/api.generated.ts` or `frontend/tests/e2e/support/e2e-passkeys.generated.ts`. A task regenerates them locally to run `contract_drift.py` and the typecheck, then reverts them. The main agent regenerates and commits them at the merge, and regenerates the navigation and pill snapshot baselines when `registry.ts` or `tone-by-kind.ts` changed.
3. **The collab backend chain.** One task at a time owns `backend/apps/collab/api.py` and `schemas.py` (key `collabapi`): `c10-notifications-api-a` writes them for the seven record-facing operations and `c10-notifications-api-c` adds `GET /me/comments` after it, each sending an operation to a named function in the module that will build it, which answers 501 `not_built` (parallel plan rule 2). No third task writes those two files in this chunk. The modules are `collab/inbox.py` (the notification inbox), `collab/comments.py` (comments) and `collab/me_comments.py` (My work's panel). There is no `collab/prefs.py`: preferences ride on `PATCH /me` in identity and are `c10-notification-prefs`'s. A logic task owns only its own module and its tests, never `api.py`. A logic task that finds the contract wrong stops and reports.
4. **`logic.py` is the notification core, and nothing else.** `backend/apps/collab/logic.py` holds `notify()`, the recipient check and the delegation hop, and is held by key `collabcore`: `c10-collab-models-b`, then `c10-notification-prefs`, then `c10-delegation`, then `f03-T78b`, in that order and never side by side. Comments, the inbox, reminders, escalation and the digest call it; none of them edits it.
5. **The collab worker chain.** `backend/apps/collab/tasks.py` (key `collabtasks`) holds the beat entries and the task bodies: `c10-mail-catalog-b`, then `c10-reminders-escalation-a`, then `c10-reminders-escalation-b`, then `c10-digest-b`. `c10-mail-catalog-a` writes no task, which is why it can sit a wave earlier. The bodies that compute live in modules of their own (`collab/reminders.py`, `collab/escalation.py`, `collab/digest.py`), so `f03-T79` and `f03-T81` can run side by side without touching `tasks.py`.
6. **The collab frontend chain.** One task at a time owns `frontend/src/features/collab/{types,api,hooks}.ts` and the `collab` catalog namespace (key `collabfe`), in this order: `c10-fe-collab-feature`, `c10-fe-comments-panel-a`, `c10-fe-notifications-a`, `c10-fe-notifications-b`. `c10-fe-comments-panel-b` mounts the panel and holds `casesfe`, `changescreen` and `obpage` instead. The directory already exists from `f03-T63`'s participants panel; each task adds only the operations its own surface calls. The workflow policy screen and the create-or-suggest picker have feature directories of their own and join no chain.
7. **Screens call no stub.** Each screen task depends on every backend task whose routes it calls. The comments panel therefore waits for `c10-comments-api-b`, and the notification preferences control waits for `c10-notification-prefs`.
8. **Append ledgers** (parallel plan rule 5): `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`, `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`, `docs/plans/briefs/HARDENING.md`, the UI plan's ledger rows and status cells, `backend/config/settings.py` setting banners, `backend/.env.example` and `docs/runbooks/RAILWAY_VARIABLES.md`, router mounts in `backend/config/api.py`, `backend/apps/shared/kinds.py`, the route lists in `permissions.py`, the guarded-table lists in `tests_rls.py`, `tests_four_eyes.py` and `tests_seed_integrity.py`, new test classes (and only new test classes) in `apps/shared/tests_hardening.py` and the other shared test modules, `backend/apps/shared/e2e_seed.py` and `e2e_logins.py` (one seed call or one login per task), `frontend/src/shared/navigation/registry.ts` entries, `frontend/src/features/shared/tone-by-kind.ts` entries, `backend/apps/collab/app.md` and the other app.md status cells, each `tests_scenarios.py` skip line, and each `*.journey.spec.ts` (own test blocks only). Each task adds only its own lines and never edits another's.
9. **Contract drift.** `c10-notifications-api-a` writes one `contract_drift_pending.txt` line per operation it declares as a stub. The task that fills an operation deletes its own line in the same commit, and `c10-close` proves no chunk 10 line is left. Nobody else edits another task's line.
10. **Coverage floors.** `backend/scripts/coverage_gate.py` gets the chunk 10 floors once, from `c10-close`, measured at the close with the date beside each. A task states its own `coverage report --include` threshold in its done-condition and never lowers an existing floor.
11. **Security review before merge.** `c10-collab-models-a` and `-b` (five new tenant tables and the recipient check that decides who may see a record), `c10-notifications-api-a` and `-c` (the contract and its gates), `c10-comments-api-a` and `-b` (tenant content at a trust boundary), `c10-workflow-policy` (a tenant column that changes who is told about overdue work), `c10-delegation` (work routed to another person), `f03-T78a`, `-b` and `-c`, `f03-T80a` (a cross-record read filtered by permission) and `c10-e2e-seed-a` and `-b` each get a security-review sub-agent over `git diff main...<branch>` before the squash merge, with `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write` and `tests_four_eyes`. `c10-security-review` is the chunk-wide sweep after the last screen merges, and `c10-review-fixes` closes its findings.
12. **Merge at once.** Each task is squash-merged and the full checklist run as soon as it passes review (WORKTREES step 5). Finished work never waits for the rest of the chunk.
13. **Tenant content.** Comment text, mention lists, case notes and assessment text are tenant content. No task may put them in a log line, a Sentry event, an `extra` key, an audit `before` or `after` value, an outbox payload, a webhook body, a `notification.title`, a mail subject or a mail body. `record()` for a comment write takes the **record's** title as `subject_title` and a summary naming the actor and the record, never the body. The compliance lint's `log-content` rule already refuses a logger call carrying a value named `comment`, `body`, `text` or `note`; `f03-T80a` widens the same rule to `record()` and outbox payloads, so a new writer is caught by the lint rather than by a reviewer.
14. **Clocks.** Everything dated is anchored to the tenant-local date plus a fixed wall time (CLAUDE.md §8.3 and §11). No seed, fixture, test or journey may depend on the real "today": a lead time of three days would make a reminder test green on a Tuesday and red on a Friday. Tests freeze the clock; the seed derives its dates from the anchor; COL-S3 drives the clock across a daylight saving boundary explicitly.
15. **E2E, in full.** Every task with a journey follows CLAUDE.md §11 as written: one command against a production Next build and the real backend on a freshly seeded throwaway database, sign-in through the UI with a passkey and the virtual authenticator, `test` imported from `tests/e2e/support/api-guard` with every expected error declared where it happens, `seed_e2e` extended rather than mocked, clocks anchored to the tenant-local date, and the screenshot and trace read before any code is touched when a journey fails. The main agent pastes that section in full into every UI task's prompt.
16. **Scenario ownership.** Exactly one task un-skips each integration test and one un-fixmes each journey:

| Scenario | `@integration` | `@e2e` |
|---|---|---|
| COL-S1 | `c10-comments-api-b` | `c10-fe-comments-panel-b` |
| COL-S2 (amended by `f03-T81`) | `c10-digest-b` | `c10-fe-notifications-b` |
| COL-S3 (reworded to the reminder beat by `c10-reminders-escalation-a`) | `c10-reminders-escalation-a` | — |
| COL-S5 | `c10-comments-api-a` | — |
| COL-S10 | `f03-T78b` | — |
| COL-S11 | `f03-T79` | — |
| COL-S12 | `f03-T80a` | `f03-T80b` |
| COL-S13 (new, written by `c10-notification-prefs`) | `c10-notification-prefs` | — (integration only) |
| TEN-S4 (its reminder half) | `c10-delegation` | — (`c8-ui-out-of-office`'s journey, reworded there; CHUNK8_TASKS.md) |
| TEN-S7 (extended) | — | `c10-j8-extension` |
| VOC-S6 | already green (chunk 2) | `c10-fe-suggest-b` |
| VOC-S12 | `c10-tagging-api-b` | `c10-fe-bulk-tagging-b` |

COL-S4 stays skipped and fixme with chunk 13 named. COL-S6 to COL-S9 belong to chunks 8 and 9 and are green before wave 1. `c10-collab-design-a` and `-b`, `c10-collab-models-a`, `c10-notifications-api-a`, `-b` and `-c`, `c10-mail-catalog-a` and `-b`, `c10-tagging-api-a`, `c10-fe-collab-feature`, `c10-e2e-seed-a` and `-b`, `c10-fe-comments-panel-a`, `c10-fe-notifications-a`, `c10-fe-bulk-tagging-a`, `c10-fe-suggest-a`, `c10-fe-workflow-policy`, `f03-T78a` and `f03-T78c` contribute to scenarios and un-skip none.

CHANGES FROM `PARALLEL_PLAN.md`, WITH REASONS
- **Five more tasks are split, on the review of 2026-09-20**, for the same reason as the eleven below and with no wave added. `c10-notifications-api-a` keeps the seven record-facing operations and `c10-notifications-api-c` adds `GET /me/comments` with its page shapes, which only `f03-T80a` waits for. `c10-mail-catalog-a` is the catalog and the composer and moves to wave 2; `c10-mail-catalog-b` is the delivery task and the `email_message` row, and is what the reminder, escalation and digest tasks depend on. `c10-e2e-seed-a` seeds comments, notifications and the tenant B row, `c10-e2e-seed-b` the dated work behind reminders, escalation and the digest; the comments panel and J-8 need only `-a`, so they no longer wait for the digest, and `c10-fe-notifications-b` moves to wave 13 with `c10-j8-extension`. `c10-fe-bulk-tagging-a` is the selection and the preview on the inventory, `c10-fe-bulk-tagging-b` VOC-S12's journey. `f03-T78a` keeps `participant_added` and `review_due`, both in `collab/`, and `f03-T78c` takes `involved_item_changed`, whose two call sites are in `watch/` and `library/`; they share wave 6 because their paths are disjoint, and `f03-T78b` waits for both.
- **Eleven packages are split into `-a` and `-b`.** `c10-collab-design`, `c10-collab-models`, `c10-comments-api`, `c10-tagging-api`, `c10-reminders-escalation`, `c10-digest`, `c10-fe-suggest`, `c10-fe-notifications`, `c10-fe-comments-panel`, `f03-T78` and `f03-T80` are estimated at 50 to 60 minutes. The reviews of the chunk 5, 7 and 8 plans each found tasks "far beyond thirty minutes of sub-agent work", and on 2026-09-19 long sub-agents died at a usage limit mid-task. Each half has its own done-condition and its own green point; the package id is the stem, as with `chunk3-rest-T11a/b`, `chunk4-T16a/b` and `chunk4-T24a/b`.
- **`c10-notifications-api-a` is the chunk's contract task**, declaring every collab operation, comments and `GET /me/comments` included, behind its real gate and answering 501 from a named module. Without it `c10-comments-api` and `f03-T80` would each write `collab/api.py`, which is parallel plan rule 2's whole point, and the comments panel would have to wait for both.
- **`c10-comments-api` and `f03-T80` lose the `collabapi` key**, because the contract task holds it. They own `collab/comments.py` and `collab/me_comments.py`. This removes the chunk's worst serialisation: three packages on one `api.py`.
- **`f03-T79` and `f03-T81` lose the `collabtasks` key** and own `collab/reminders.py` (its review branch) and `collab/digest.py`. Both depend only on `f03-T78`, so keeping them on `tasks.py` would have cost a whole wave for nothing.
- **`c10-fe-workflow-policy` loses `c10-fe-notifications` from its depends-on and gains the new key `workflowfe`** (`frontend/src/features/workflow-policy/`, `app/(tenant)/admin/workflow/` and the `workflow` catalog namespace). It calls `GET /tenant` and `PATCH /tenant`, not one collab route, so it needs the workflow policy backend and the admin shell and nothing else; ruling 8 explains why it does not share `admin-organisation.html`.
- **`c10-fe-suggest` loses `c4-fe-tenant-proposals`** from its depends-on. Under ruling 5 the picker calls `suggestVocabularyRow` and `createVocabularyRow`, both on `main` since chunk 2; the tenant's pending proposals screen is a different surface and VOC-S6 does not walk it. It keeps `c10-tagging-api` and `c3-fe-obligation-versions`.
- **`c10-delegation` gains TEN-S4's integration half.** No package owned it: `c8-ten-out-of-office` builds the window and the delegate column, and the routing of reminders and approvals is this package. If chunk 8 has already un-skipped `test_ten_s4`, `c10-delegation` extends that test instead of un-skipping it, and says so in its commit body.
- **`c10-notification-prefs` writes a new scenario, COL-S13**, in `collab/app.md` and `collab/tests_scenarios.py`. Preferences are behaviour no scenario covered, and the requirements-coverage gate pairs a heading with a stub, so the scenario and the stub land in the same commit (CLAUDE.md §10).
- **`c10-e2e-seed-b` moves after `c10-digest-b`** rather than beside it, because the seeded weekly digest needs the composer that `c10-digest-a` builds, the same reason ruling 17 of the parallel plan gave for chunk 6's emailed briefing snapshot.
- **`c10-tagging-api` and `c10-fe-suggest` shrink** under ruling 5: VOC-03's routes, the near-duplicate check and `test_voc_s6`, `test_voc_s7` and VOC-S7's journey are already on `main`.
- **`c10-fe-comments-panel-b` gains the case page and the `casesfe` key**, and `c9-fe-cases-feature` in its depends-on. COL-S1's own Gherkin comments on a case, and the plan's keys named only `changescreen`, `obpage` and `collabfe`.
- **`c10-fe-notifications-a` loses the E2E seed** from its depends-on: the screen and its unit tests need no chunk 10 seed, only its journeys do, and those are `-b`'s. It moves from wave 12 to wave 7.

CHANGES FROM THE TWO CRITIQUES
- Parallelism: three packages held `collab/api.py`, so the contract task now holds it alone and `c10-comments-api` and `f03-T80` drop the `collabapi` key; `f03-T79` and `f03-T81` were both on `collab/tasks.py` although neither needs it, so each got its own module and they now share a wave; `c10-delegation` and `c10-notification-prefs` both wrote `collab/logic.py` in one wave, so delegation moved to wave 4; `EmailMessage` was a second `mig:collab` migration in the mail catalog package and moved into the chunk's one migration; `c10-collab-design-a` and `-b` both edited `design/README.md`, which is not an append ledger, so the index rows went to `-a` alone; `c10-fe-notifications-a` was waiting on the E2E seed although only its journeys need it, and moved five waves earlier; `c10-fe-workflow-policy` would have serialised on `admin-organisation.html` against chunk 8, so it got its own section and key (ruling 8); `apps/shared/tests_hardening.py` was named as a new-test-classes ledger, since `c10-collab-models-b` adds a guard test to a file `h-a-guards` created.
- Coverage: COL-S1's own Gherkin comments on a **case**, and no task mounted the panel there, so `c10-fe-comments-panel-b` gained the case page, the `casesfe` key and `c9-fe-cases-feature`; D-25 says comments join "changes on your items" from chunk 10, which contradicts HOM-S11 as written, so `f03-T80a` now owns HOM-S11's rewording and its test; the `assignments` preference has no chunk 10 producer, so `c10-notification-prefs` names chunk 9's assignment scenario as the proof of that branch rather than leaving it untested; COL-S13's journey would have needed a screen built in the same wave, so the scenario is integration only and the reason is written into `c10-fe-notifications-b`; nobody set `notification.emailed_at`, which is now a done-condition of `c10-reminders-escalation-a`; no task deleted its own `contract_drift_pending.txt` lines, so plan-wide rule 9 gives each task its own and the close proves none is left; the pill gallery baseline gains tones nobody had named, so `c10-fe-collab-feature` states that the main agent regenerates and reviews it; the inbox had no budget check at all before `c14-perf-rest`, so it now measures once on 5,000 rows; the INPUT_DELTAS row for `mentions uuid[]` becoming rows sat with the contract task rather than with the migration that makes it true; and CLAUDE.md §11 was not restated, so plan-wide rule 15 now carries it and requires it in every UI task's prompt.

## Waves

Tasks in one wave have disjoint owned paths and share no serialization key, so they can run side by side.

1. `c10-collab-design-a`, `c10-collab-design-b`, `c10-collab-models-a`, `c10-tagging-api-a`
2. `c10-collab-models-b`, `c10-notifications-api-a`, `c10-workflow-policy`, `c10-tagging-api-b`, `c10-mail-catalog-a`
3. `c10-notifications-api-b`, `c10-notifications-api-c`, `c10-comments-api-a`, `c10-notification-prefs`, `c10-mail-catalog-b`
4. `c10-comments-api-b`, `c10-reminders-escalation-a`, `c10-delegation`, `c10-fe-suggest-a`, `c10-fe-workflow-policy`
5. `c10-reminders-escalation-b`, `c10-fe-collab-feature`
6. `f03-T78a`, `f03-T78c`, `c10-fe-comments-panel-a`, `c10-fe-suggest-b`
7. `f03-T78b`, `c10-fe-notifications-a`, `c10-fe-bulk-tagging-a`
8. `f03-T79`, `f03-T81`, `c10-fe-bulk-tagging-b`
9. `c10-digest-a`, `f03-T80a`
10. `c10-digest-b`, `f03-T80b`
11. `c10-e2e-seed-a`
12. `c10-e2e-seed-b`, `c10-fe-comments-panel-b`
13. `c10-fe-notifications-b`, `c10-j8-extension`
14. `c10-security-review`
15. `c10-review-fixes`
16. `c10-close`

The chunk has two chains and they are the wall clock: models → contract → comments → the collab feature layer → the comments panel, and models → mail catalog → reminders → escalation → `f03-T78` → the digest → the seed → the notification screens. Everything else hangs off them. `c10-tagging-api` and `c10-fe-suggest` are a third, short chain that shares nothing with the other two and can run whenever a slot is free.

`c10-collab-models-b` is a cross-chunk contract, not only a chunk 10 task: `c9-triage`, `c9-signoff`, `c11-run-scheduler`, `c13-follow-notify` and `c13-saved-search-notify` all call `notify()` and all depend on it (ruling 1). It therefore merges before chunk 9's workflow packages start, whatever chunk 10's own order says, and its review is the first of the chunk.

## Open questions

- **q-comment-subjects (non-blocking; the default is taken and nothing waits).** COL-01 says comments and mentions work "on any record". `subject_type` has 50 values, and most name tables R2 does not have. Every comment read must also answer "may this person read the record this comment hangs on", which needs a read check per kind.

  Option A (recommended, and the default this plan builds): one subject registry in `collab/subjects.py` maps a kind to its read permission and its row lookup, R2 registers `obligation`, `tenant_obligation`, `change`, `change_case` and `action`, and `POST /comments` answers 422 `unsupported_subject` for anything else. A later chunk opens a kind by adding one registry row with its read check, and a registry test fails on a row missing either half. The five kinds are exactly the records the designed screens carry a comments panel on.

  Option B: register every `subject_type` value now, with a default-deny for kinds that have no check yet. It is the same code with a wider door, and a kind whose check was forgotten would answer 404 for everybody, which reads as a bug rather than as "not yet".

  Option C: comments on cases only, as the prototype's case page shows them. It is less than COL-01 asks for, and `tenant-my-work.html` already lists comments on obligations.

  This is under open questions because Option A narrows a PRD requirement's stated breadth, not because anything waits: `c10-comments-api-a` builds Option A, and reopening it later costs one registry row per kind.
- Non-blocking, to confirm (defaults are taken and the build does not wait): that only reminders, escalations and the digest leave by mail while every other notification is in-app; that a person may mute mentions, assignments, reminders and the digest but not an escalation; that a comment is editable by its author for fifteen minutes and afterwards only deletable, the replaced text kept in an append-only revision nobody can read back (ruling 10); and that a notification keeps showing the record title it was written with to a member who has since lost the permission to read that record, the link answering 404 when followed (`c10-notifications-api-b`). `c10-close` writes all four into `docs/TODO_FOR_alex.md`.
- Two questions the first draft asked are **not** asked, because the repository settles them: that escalation reaches both the head of the owner's department and the escalation-role holders is decided by PRD 0.4 COL-02 read with COL-S2 in `collab/app.md`, which names the department head and the compliance officer, and ruling 7 holds them together; that the triage target lives on the tenant's workflow columns is decided by `schema.sql`'s `change_case.triage_due_at`, "from the tenant's triage target", and INPUT_DELTAS §7's rule that the reminder and escalation settings are columns of their own, which ruling 6 applies.
- Already answered, and therefore **not** asked (the reviews of the chunk 5, 7 and 8 plans each rejected a question the repository had already settled):
  - Private notes on My work: there are none (D-60, D-22, OWNER_RECOMMENDATIONS item 13). The panel is "Comments and mentions" and its composer says everyone in the organisation can read them.
  - Who receives a notification: D-34's one recipient check, active members whose roles can read the record at send time, once per person per event.
  - Whether a delegate needs the approve permission: yes (parallel plan §7.2).
  - Whether tagging is gated by `vocab.manage`: yes (parallel plan §7.2).
  - Whether a bank's comments may be read outside the bank: they may not (Alex, 2026-09-19, item 3; D-50). `comment` is a tenant table under forced RLS and nothing reads it across the fence.
  - Whether a comment may reach a model: it may not (CLAUDE.md §5; `data-model.md` §14 keeps search on the library in version 1).

## Tasks

### c10-collab-design-a: the notifications screen card

**Requirements:** COL-02
**Scenarios:** none
**Depends on:** none

Cut `design/screens/tenant-notifications.html` from the prototype (playbook Section 7), in the house pattern of `tenant-library-updates.html` and `me-sessions.html`: the header comment naming the requirements, journeys and chunk, then one numbered block per state. The card shows:
- the bell in the who panel of `tenant-shell.html` with its unread dot, and the same entry under More on a 375 px phone;
- the inbox: one row per notification with its kind pill, the record's title as the link, the time, and read and unread rows visibly different;
- "Mark all as read", and marking one read in place;
- the empty state ("Nothing waiting for you"), the loading state and the error state;
- the preferences block that `c10-fe-notifications-b` builds: one switch per mutable kind (mentions, assignments, reminders, the weekly digest), with escalation shown as always on and explained;
- both themes, from `tokens.generated.css`, with every pill a real `Pill` tone chosen by kind.

Write the copy as what the user is doing, with no requirement id and no restated invariant on screen. Add the card's row to the `design/README.md` index and its rows to the UI plan's chunk 10 table.

**Owned paths:**

- `design/screens/tenant-notifications.html`
- `design/README.md` (the index rows of both design cards, since the file is not an append ledger)
- `docs/plans/UI_Implementation_Plan.md` (its own chunk 10 rows only)

**Done when:**

- The card renders standalone in light and dark with no missing token and no inline colour literal.
- Every state the screen can be in has a block, the empty state included.
- Every pill in the card names the tone it will get and the kind it comes from, so `tone-by-kind.ts` can be filled without a second decision.
- The notification title in every example is a record title or a catalog phrase, never a comment, a case note or any other tenant text.
- The UI plan's chunk 10 rows name this card instead of "card pending".

**Gates:**

- `cd frontend && npm run build:tokens` (the card's tokens resolve)
- A visual check in both themes at 375 px and at desktop width, recorded in the commit body

**Invariants:**

- The prototype decides how things look, never what the rules are.
- Six pill tones, chosen by slot or kind, never by a person; pills only through `Pill`.
- Screen copy says what the user is doing: no requirement IDs, no restated invariants.

### c10-collab-design-b: the comments panel and the workflow policy cards

**Requirements:** COL-01, COL-02
**Scenarios:** none
**Depends on:** none

Two cards, both small:
1. `design/system/comments-and-mentions.md`, the panel that appears on the change page, the obligation page and My work. It fixes: the list oldest first with author, time and "edited"; the composer with the visibility line "Everyone in your organisation can read comments" (D-22, D-60), taken from `tenant-my-work.html` §6 so the three surfaces say the same thing; the mention control drawing on `GET /reference/people`; "Edit" and "Delete" on the author's own rows only, and what a soft-deleted row looks like; the mention that could not be delivered, shown by name with no reason; the empty, loading and error states; and the panel at 375 px.
2. `design/screens/admin-workflow.html`, the workflow policy section under Admin (ruling 8): reminder lead days as a small list of day counts, the escalation threshold in days, the escalation role picker, the weekday the digest goes out, the triage target in hours, each with its unit and its platform default shown, plus the saved and the refused states.

Both carry the header comment, both themes, and the tone for every pill.

**Owned paths:**

- `design/system/comments-and-mentions.md`
- `design/screens/admin-workflow.html`
- `docs/plans/UI_Implementation_Plan.md` (its own chunk 10 rows only)

`design/README.md` is **not** an append ledger, so `c10-collab-design-a` adds both index rows and this task adds none; the two cards would otherwise collide in wave 1.

**Done when:**

- The composer's visibility line is identical in the card and in `tenant-my-work.html`, quoted in the card with its source.
- The workflow card shows a unit beside every number and the platform default beside every field, so a tenant can see what it is changing from.
- Nothing in either card implies a private note, a per-user visibility or an approval step that does not exist.
- The UI plan rows for the comments panel and for `PATCH /tenant`'s workflow fields name these cards and the new `/admin/workflow` section.

**Gates:**

- `cd frontend && npm run build:tokens`
- A visual check in both themes at 375 px and at desktop width, recorded in the commit body

**Invariants:**

- The prototype decides how things look, never what the rules are.
- Every string on a card becomes a message-catalog key; no string literal survives into JSX.

### c10-collab-models-a: the comment and notification tables

**Requirements:** COL-01, COL-02
**Scenarios:** none
**Depends on:** `p03-consolidation`, `c5-contract-models-cases`
**Security review:** yes (five new tenant tables, two holding tenant content and one holding an address)

Add the tables to `backend/apps/collab/models.py` and a migration beside the participant migration chunk 8 added, from `docs/inputs/schema.sql` §8 and §10 and `data-model.md`:
- `Comment(TenantModel)`: `subject_type` (a `SubjectType` value), `subject_id`, `body`, `author`, `created_at`, `edited_at` (nullable), `deleted_at` (nullable), `Meta.ordering = ["created_at", "id"]`, and the index `(tenant, subject_type, subject_id, created_at)` the schema names. Mentions are rows, not a `uuid[]`: `CommentMention(TenantModel)` with `comment`, `user` and a unique `(comment, user)`, because a `uuid[]` cannot carry a composite foreign key and INPUT_DELTAS §1 turns array columns into rows everywhere else.
- `CommentRevision(TenantModel, AppendOnlyModel)` (ruling 10, new beside `schema.sql`): `comment`, `body` (the text the edit replaced), `edited_by`, `created_at`, `Meta.ordering = ["-created_at", "-id"]`, and the append-only trigger, so an edit keeps the previous text and nobody can rewrite or delete it. It is tenant content and carries the same model docstring as `Comment`. The INPUT_DELTAS §1 row says why the table is new: `schema.sql` has only `comment.edited_at`, and dropping the replaced text would overwrite tenant work.
- `Notification(TenantModel)`: `user`, `kind` (a `NotificationKind` value), `subject_type`, `subject_id`, `title`, `created_at`, `read_at` (nullable), `emailed_at` (nullable), `Meta.ordering = ["-created_at", "-id"]`, and the partial inbox index on unread rows.
- `EmailMessage(TenantModel)` (`schema.sql` §21): `user` (nullable), `to_email`, `template`, `subject`, `subject_type` and `subject_id` (both nullable), `status` (an `EmailStatus` kind), `provider_message_id`, `queued_at`, `sent_at`, `error`, `Meta.ordering = ["-queued_at", "-id"]`, and a unique `(tenant, user, template, subject_type, subject_id, sent_on)` where `sent_on` is the tenant-local date, so a retried worker cannot double-send. It lands here rather than with the mail catalog package so the chunk has one migration and one `mig:collab` holder.

Also:
- Add `NotificationKind` and `EmailStatus` to `apps/shared/kinds.py` with its INPUT_DELTAS §1 name and reason, carrying the schema's nine values plus `participant_added`, `involved_item_changed` and `review_due` (INPUT_DELTAS §1, D-34). `proposal_waiting` and `saved_search_hit` are declared with the chunk that will produce them named in the reason.
- Add `comment`, `comment_mention`, `comment_revision`, `notification` and `email_message` to the guarded-table list in `apps/shared/tests_rls.py` and to `tests_seed_integrity.py`.
- A test that `email_message` holds no body column at all: the proof of a send is the template key and the subject, never the text that was sent.
- Add a model docstring on `Comment` stating that `body` is tenant content and naming the four places it must never reach, so the next reader of the file does not have to find D-22.

No logic, no routes and no `notify()`: this task is the tables and their guards.

**Owned paths:**

- `backend/apps/collab/models.py`
- `backend/apps/collab/migrations/0002_comments_notifications.py`
- `backend/apps/collab/tests_models.py`
- `backend/apps/shared/kinds.py` (its own entry only)
- `backend/apps/shared/tests_rls.py`, `backend/apps/shared/tests_seed_integrity.py` (the guarded-table lists only)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph.
- The RLS guard lists `comment`, `comment_mention`, `comment_revision`, `notification` and `email_message` as forced tenant-only, and a cross-tenant read returns nothing under `cw_app`.
- The INPUT_DELTAS §1 row says why `mentions uuid[]` became `comment_mention` rows, and a test proves the database refuses a `comment_mention` whose user is a member of another tenant, and a `notification` whose user is not a member of its tenant.
- `Comment.__str__` and `__repr__` return ids, never the body; a test asserts it, and the same test covers `CommentRevision`.
- The append-only trigger on `comment_revision` refuses an update and a delete under `cw_app`, with a test for each, so an edited comment's previous text cannot be rewritten away.
- The kinds-only guard and the compliance lint are green, and `NotificationKind`'s reason names the producer chunk of every value chunk 10 does not produce.
- The task edits no other file under `apps/collab/`, so it can share a wave with the design cards and the tagging read.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*' (models.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Tenant tables carry `tenant_id` under enabled and forced row-level security; `cw_app` cannot bypass it.
- Enums in code are for kinds only; the API returns `key` and `kind`, never a phrase.
- Tenant content never reaches logs, Sentry, analytics or an unapproved model endpoint.

### c10-tagging-api-a: tenant tags on a record, and the two tag filters

**Requirements:** VOC-08 (its read half), INV-02
**Scenarios:** none (VOC-S12 is `-b`'s)
**Depends on:** `c3-provision-read`

`TenantTag`, `TenantTagLabel` and `Tagging` are already on `main` from chunk 2; only the routes are missing. Build the single-record half:
- `POST /taggings` and `DELETE /taggings` (the subject in the body, never in a path or query string, for the reason INPUT_DELTAS §7 gives the market keys: the access log and error reports keep the request line), gated by `vocab.manage`, taking `{tagKey, subjectType, subjectId}`. A kind outside `obligation`, `tenant_obligation`, `change` and `change_case` answers 422 `unsupported_subject`; an unknown tag key answers 422 `unknown_key`; a repeated add is idempotent and answers 200 with the current tags.
- The obligation row gains `tenantTags[{key, kind, label}]`, filled from one query for the page, never per row.
- `GET /obligations` gains `tag` (library tag keys, the filter INPUT_DELTAS §7 deferred) and `tenantTag` (the tenant's own tag keys). Both take a list, both answer 422 `unknown_key` naming each key that does not exist, and an API key with no tenant gets 422 `unknown_filter` for `tenantTag` and no `tenantTags` field at all.
- Each write goes through `record()` with the record's title as `subject_title` and the tag key in `after`, in the request's transaction.

**Owned paths:**

- `backend/apps/taxonomy/api.py`, `backend/apps/taxonomy/schemas.py` (the tagging operations only)
- `backend/apps/taxonomy/tagging_logic.py` (new)
- `backend/apps/library/api.py`, `backend/apps/library/reading.py`, `backend/apps/library/schemas.py` (the two filters and the row field only)
- `backend/apps/taxonomy/tests_tagging.py` (new)
- `backend/apps/shared/permissions.py` (the route lists only)

**Serialization keys** (`PARALLEL_PLAN.md` §3.4): `taxapi` (`taxonomy/api.py` and `schemas.py`, which `c8-vocab-scales-reasons` and `c12-config-policies` also hold) and `libread` (the library read files). Both halves of the tagging chain hold both keys from start to merge, so neither runs beside a package holding either.

**Done when:**

- Tagging and untagging an obligation, a tenant obligation, a change and a case work, are audited, and answer 422 for any other kind.
- A member without `vocab.manage` gets 403 with `requiredPermission`; an anonymous request gets 401.
- Tenant A's tags never appear on tenant B's reading of the same library obligation, proved on the `cw_app` alias.
- The list read's query count is unchanged by the new field: a test pins it for a page of 20.
- No library table is written: the library fence test is green and the diff touches no library writer.
- `contract_drift.py` reports the new operations as delivered.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.taxonomy apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/taxonomy/*,apps/library/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only; do not commit `openapi.json` or `api.generated.ts`

**Invariants:**

- Proposals are the only door into the library; a tenant tag is a tenant row and writes nothing in the library.
- Store and compare keys, never labels.
- `record()` on every write, in the same transaction.

### c10-collab-models-b: `notify()`, the one recipient check

**Requirements:** COL-02, COL-04 (its notification side)
**Scenarios:** none (its behaviour is proved by COL-S1, COL-S10 and COL-S11 later)
**Depends on:** `c10-collab-models-a`, `c5-outbox-cursor`
**Security review:** yes (the code that decides who may be told a record exists)

Build `notify()` in `backend/apps/collab/logic.py`, the only writer of a notification row in the product (ruling 1). Its signature takes a tenant, a kind, a subject kind and id, a title and a set of candidate user ids with the reason each was a candidate; it returns the rows it wrote.

D-34's recipient check, written once:
- keep only active members of that tenant (no `deactivated_at`, membership present);
- keep only those whose roles hold the read permission of the subject's kind, read from the subject registry that `c10-comments-api-a` will own and that this task creates as a two-entry seed (`change_case` and `obligation`), with the registry's contract and its test in place so the later task only adds rows;
- de-duplicate per person per event, whatever the number of reasons, so a person who is both owner and participant gets one row;
- honour `membership.notification_prefs` for the mutable kinds (`c10-notification-prefs` fills the schema; until then an absent key means on) and never mute an escalation;
- write every row in the caller's transaction through `record()`'s sibling path, so a notification and the write that caused it commit together or not at all.

Register the collab dispatch entry on `c5-outbox-cursor`, so a worker consuming an outbox row for a tenant calls `collab.tasks.notify_for_event` inside `@tenant_task`. Do not add a second relay (parallel plan ruling 9).

**Owned paths:**

- `backend/apps/collab/logic.py`
- `backend/apps/collab/subjects.py` (the registry, with its first two rows)
- `backend/apps/collab/tasks.py` (the dispatch entry only)
- `backend/apps/collab/tests_notify.py` (new)
- `backend/apps/shared/tests_hardening.py` (the one-writer guard test only)

**Done when:**

- A guard test walks production code and fails on any `Notification(`, `Notification.objects.create` or `bulk_create` outside `collab/logic.py`, listing today's single call site as the allowed set.
- A person who is both owner and participant of the same record receives one row; a deactivated member, a member of another tenant and a member whose roles lack the subject's read permission receive none. Each is its own test.
- A registry test fails on a registry row with no read permission or no row lookup.
- `notify()` raises `NotInTransaction` outside a transaction, the way `record()` does, with its own test.
- No title, argument or log line in this module can carry tenant text: the function takes a title the caller built and a test proves the module logs ids only.
- The dispatch runs inside `@tenant_task` and `tests_celery_registration` is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*' (logic.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Permissions, never role names. `tenancy.activate()` after auth; `@tenant_task` in the worker.
- A notification reaches only active members who can read its record, once per event.
- Tenant content never reaches logs, Sentry, analytics or an unapproved model endpoint.

### c10-notifications-api-a: the collab contract, every record-facing operation behind its real gate

**Requirements:** COL-01, COL-02
**Scenarios:** none
**Depends on:** `c10-collab-models-a`
**Security review:** yes (the chunk's gates)

Write `backend/apps/collab/api.py` and `schemas.py`, and mount the router in `config/api.py`. The seven record-facing operations are here; `GET /me/comments` and its page shapes are `c10-notifications-api-c`'s, which holds `collabapi` after this task. Every operation carries its auth class and permission and calls a named function in the module that will build it, which answers 501 `not_built` (parallel plan rule 2):

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `listNotifications` | `GET /notifications` | SessionAuth, member session | `collab/inbox.py` |
| `markNotificationRead` | `POST /notifications/{notificationId}/read` | SessionAuth, member session | `collab/inbox.py` |
| `markAllNotificationsRead` | `POST /notifications/read-all` | SessionAuth, member session | `collab/inbox.py` |
| `listComments` | `GET /comments` | SessionAuth, the subject's read permission | `collab/comments.py` |
| `addComment` | `POST /comments` | SessionAuth, `comments.write` and the subject's read permission | `collab/comments.py` |
| `editComment` | `PATCH /comments/{commentId}` | SessionAuth, `comments.write`, author only | `collab/comments.py` |
| `deleteComment` | `DELETE /comments/{commentId}` | SessionAuth, `comments.write`, author only | `collab/comments.py` |

Schemas, camelCase through `CamelSchema`, matching `openapi.yaml` where it is right and INPUT_DELTAS where it is not:
- `Comment` = `{id, subjectType, subjectId, body, mentions[UserRef], author, createdAt, editedAt, canEdit, canDelete}`; `CommentInput` = `{subjectType, subjectId, body, mentionUserIds[]}`; `CommentPatch` = `{body}`.
- `CommentPage` and `NotificationPage` use the shared pagination (default 20, max 100). `openapi.yaml` returns a bare array for `listComments`; a page is used instead, because a busy case would return every comment ever written (playbook 10).
- `Notification` = `{id, kind, subjectType, subjectId, title, createdAt, readAt}`; `NotificationQuery` = `{unread?}` plus the shared page query.

Also:
- Add the seven routes to the route lists in `apps/shared/permissions.py`. Five of them carry no `@requires_permission`, and `apps/shared/tests_route_permissions.py` accepts only a decorator or an `UNGATED_BY_DESIGN` entry with one of the five reasons and a note a reviewer can disagree with, so each of the five gets its entry: `GET /notifications`, `POST /notifications/{notificationId}/read` and `POST /notifications/read-all` as `SELF`, "Acts only on the caller's own notification rows; no parameter reaches another person's (COL-02)."; `GET /comments` and `POST /comments` as `LOGIC_GATE`, "The gate is the read permission of the subject's kind, which `collab/subjects.py` decides per record; the write also needs `comments.write` (COL-01)." `PATCH` and `DELETE /comments/{commentId}` carry `@requires_permission("comments.write")` with the author check in logic, so they are gated and take no entry: the guard refuses a route that is both.
- Write the INPUT_DELTAS §7 rows for the comment page shape, for `canEdit`/`canDelete` and for ruling 3's subject registry, each naming the task that closes it, and the matching `contract_drift_pending.txt` lines. The row for the mention rows replacing `mentions uuid[]` is `c10-collab-models-a`'s, because that is where the column becomes a table.

**Owned paths:**

- `backend/apps/collab/api.py`
- `backend/apps/collab/schemas.py`
- `backend/apps/collab/inbox.py`, `comments.py` (the `not_built` stubs only)
- `backend/apps/collab/tests_contract.py`
- `backend/config/api.py` (the router mount only)
- `backend/apps/shared/permissions.py` (the route lists only)
- `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`

**Done when:**

- The seven operations appear in `openapi.json` with the ids above and answer 501 `not_built` behind their real gate.
- A session without the permission gets 403 with `requiredPermission` and an anonymous request gets 401, both before the 501, proved per route.
- An enrolment session gets 403 on every one of them.
- The route-permission guard is green: the two decorated comment routes carry their permission, the five others each have an `UNGATED_BY_DESIGN` entry with its reason and its note, no route is both, and no entry names a route that does not exist.
- `bash generate-types.sh` produces types for all seven without the task committing them.
- The diff stays inside the owned paths, and no stub module holds a line of logic.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*' (api.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only; do not commit `openapi.json` or `api.generated.ts`

**Invariants:**

- No logic in `api.py`; no `Dict[str, Any]`; no `*args`/`**kwargs`.
- Every route carries `@requires_permission` or `@requires_scope`, or an `UNGATED_BY_DESIGN` entry with one of the five reasons and a sentence a reviewer can disagree with.
- Errors are RFC 9457 with a `code`; no trace ever leaves.

### c10-workflow-policy: the tenant's reminder, escalation and triage columns

**Requirements:** COL-02, TEN-01
**Scenarios:** none (COL-S2 and COL-S11 prove the values in use)
**Depends on:** `c10-collab-models-a`, `c8-tenants-api-contract`
**Security review:** yes (a tenant column that changes who is told about overdue work)

Replace the designed `tenant.settings` blob with five explicit columns on `Tenant` in `apps/shared/models.py` (INPUT_DELTAS §7, ruling 6): `reminder_days_before` (a small integer array, each value 1 to 90, at most five entries, default `[3]`), `escalate_after_days` (1 to 90, default 5), `escalate_to_role` (a `TenantRole` key, default the compliance officer's), `digest_weekday` (a weekday kind, default Monday, the day `c10-digest-b` sends on) and `triage_target_hours` (1 to 720, default 48). Retention stays for `c12-retention-contract`.

`GET /tenant` gains a `workflow` object and `PATCH /tenant` accepts it under `workflow.manage`, beside the profile fields `c8-tenants-api-contract` gates with `members.manage`: a member holding only one of the two sees and may write only its own fields, and a patch touching the other's answers 403 with `requiredPermission`. Every platform default is a setting with an env override, and a tenant created before this migration takes the defaults.

The write goes through `record()` with the before and after values (these are the tenant's own settings, not tenant content, so both sides are recorded) and needs no step-up.

**Owned paths:**

- `backend/apps/shared/models.py`, `backend/apps/shared/migrations/` (one migration)
- `backend/apps/tenants/api.py`, `backend/apps/tenants/schemas.py`, `backend/apps/tenants/logic.py` (the workflow fields only)
- `backend/apps/tenants/tests_workflow_policy.py` (new)
- `backend/config/settings.py`, `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (the five defaults only)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph; an existing tenant row gets the defaults.
- Out-of-range, empty and over-long values answer 422 with `code` and the field named; a role key that is not a role of that tenant, and a weekday that is not one of the seven, each answer 422 `unknown_key`.
- A holder of `members.manage` alone cannot change a workflow field, and a holder of `workflow.manage` alone cannot change the profile; each gets 403 with `requiredPermission` and nothing is written.
- Each change writes one audit event with before and after.
- The five defaults are settings with env overrides, and a test reads each from settings rather than from a literal.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*,apps/shared/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- Every threshold is a setting with an env override; tests use fixtures.
- Permissions, never role names; a partial permission never widens a patch.
- `record()` on every write, in the same transaction.

### c10-tagging-api-b: bulk tagging, previewed and audited once

**Requirements:** VOC-08
**Scenarios:** VOC-S12 `@integration`
**Depends on:** `c10-tagging-api-a`

Build the batch half in `taxonomy/tagging_logic.py` and two routes:
- `POST /taggings/preview` answers what a batch would do without writing: the records that would gain the tag, the ones that already carry it, and the ones the reader may not read or that are not of a taggable kind, each as ids and counts.
- `POST /taggings/batch` applies it in one transaction and writes **one** audit event holding the tag key and the record ids, never one per record (VOC-S12's last line).

Both are gated by `vocab.manage`, both cap at `BULK_TAGGING_MAX_RECORDS` (a setting, default 200) and answer 422 `too_many_records` above it, both take the subject kind and the ids in the body, and both refuse a mixed batch of kinds with 422 `unsupported_subject`. A record the reader cannot read is skipped and counted, never tagged and never named. Un-skip `test_voc_s12`.

**Owned paths:**

- `backend/apps/taxonomy/api.py`, `backend/apps/taxonomy/schemas.py` (the two batch operations only)
- `backend/apps/taxonomy/tagging_logic.py`
- `backend/apps/taxonomy/tests_tagging.py`
- `backend/apps/taxonomy/tests_scenarios.py` (its own skip line only)
- `backend/apps/taxonomy/app.md` (VOC-08's status cell only)
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/config/settings.py`, `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (the cap only)

**Serialization keys**: `taxapi` and `libread`, held on from `c10-tagging-api-a` (the chain is sequential, and `-a`'s row field and filters are read back here).

**Done when:**

- `test_voc_s12` is green: six selected obligations, the preview naming which already carry the tag, the commit linking the tag to each and writing exactly one audit event with the six ids.
- A second commit of the same batch is idempotent and writes one audit event saying nothing changed.
- 201 records answer 422 `too_many_records` and write nothing.
- A record of another tenant, or one the reader cannot read, is never tagged; a test proves the row count on the `cw_app` alias.
- The audit event's `after` holds keys and ids only, no label and no tenant text.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/taxonomy/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- One audited transaction, never a partial batch.
- Store and compare keys, never labels; the API returns `key` and `kind`.
- Every threshold is a setting with an env override.

### c10-notifications-api-b: the notification inbox

**Requirements:** COL-02
**Scenarios:** none (COL-S2's journey reads the inbox later)
**Depends on:** `c10-notifications-api-a`, `c10-collab-models-b`

Build `backend/apps/collab/inbox.py` behind the three contract routes:
- `listNotifications` returns the reader's own rows in that tenant, newest first, paginated, with `unread=true` filtering on `read_at IS NULL`. It reads no other person's rows under any parameter, and it takes no `userId`.
- `markNotificationRead` sets `read_at` once; a second call is idempotent and answers 204. Another person's notification id answers 404, never 403.
- `markAllNotificationsRead` marks the reader's unread rows in that tenant and answers 204; a test pins that it is one UPDATE, not one per row.

Reading is not a write: none of the three calls `record()` except the two mark operations, which record a `notification.read` event holding ids only. A row whose subject the reader has since lost permission to read is still listed with its stored title, because the title was already shown to them and hiding it would silently empty the inbox; the link answers 404 when followed.

**Owned paths:**

- `backend/apps/collab/inbox.py`
- `backend/apps/collab/tests_inbox.py` (new)

**Done when:**

- The three operations answer from real rows and no route answers 501 any more.
- A cross-tenant and a cross-user id answer 404 in body and in status, proved for each route.
- `unread=true` and the default both paginate with the shared page query, and a test pins the query count for a page of 20.
- Marking all read is one statement; marking one read twice is idempotent.
- Nothing in the module logs a title; a test asserts the log lines hold ids only.
- The inbox read stays inside the 250 ms API budget on a tenant with 5,000 notifications, measured once and recorded in the commit body; the chunk's budget pass proper is `c14-perf-rest`'s.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- An empty answer is 200; a record that is not yours is 404, never 403.
- Paginate (default 20, max 100).
- `record()` on every write; no read writes one.

### c10-notifications-api-c: the My work comments contract

**Requirements:** COL-01, HOM-05
**Scenarios:** none
**Depends on:** `c10-notifications-api-a`
**Security review:** yes (the chunk's gates)

Add the one operation `c10-notifications-api-a` left out, holding `collabapi` after it (rule 3): `listMyComments`, `GET /me/comments`, SessionAuth on a member session, answering 501 `not_built` from `collab/me_comments.py`. Its schemas: `MyCommentQuery` = `{about: 'written'|'mentioned'}` plus the shared page query, and `MyCommentPage` on the shared pagination carrying `permissionLimitedKinds[]`, the kinds the reader could not see, so the panel can say so without naming a record (COL-S12, INPUT_DELTAS §7).

Add the route to the route lists in `apps/shared/permissions.py` with its `UNGATED_BY_DESIGN` entry, `SELF`, "Returns the caller's own comments and mentions, filtered afterwards by each subject's read permission (COL-01)." Write the INPUT_DELTAS §7 row for the page shape and its `contract_drift_pending.txt` line, which `f03-T80a` deletes.

**Owned paths:**

- `backend/apps/collab/api.py`, `backend/apps/collab/schemas.py` (this operation only)
- `backend/apps/collab/me_comments.py` (the `not_built` stub only)
- `backend/apps/collab/tests_contract.py` (its own test class only)
- `backend/apps/shared/permissions.py` (the route lists only)
- `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`

**Done when:**

- `listMyComments` appears in `openapi.json` with that id and answers 501 `not_built` behind its real gate.
- An anonymous request gets 401 and an enrolment session 403, both before the 501.
- The route-permission guard is green and the new entry names a route that exists, with a reason and a note.
- `about` outside `written|mentioned` answers 422 before the 501, so the query is validated at the boundary.
- The other seven operations are untouched: the diff adds one route and one schema pair.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*' (api.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only; do not commit `openapi.json` or `api.generated.ts`

**Invariants:**

- No logic in `api.py`; no `Dict[str, Any]`; no `*args`/`**kwargs`.
- Every route carries a decorator or an `UNGATED_BY_DESIGN` entry with one of the five reasons and a note.
- Paginate (default 20, max 100).

### c10-comments-api-a: comments written, read and never logged

**Requirements:** COL-01
**Scenarios:** COL-S5 `@integration`
**Depends on:** `c10-notifications-api-a`
**Security review:** yes (tenant content at a trust boundary)

Build `backend/apps/collab/comments.py` behind four contract routes, and finish the subject registry `c10-collab-models-b` seeded (ruling 3): one row per kind with its read permission and its row lookup, registering `obligation`, `tenant_obligation`, `change`, `change_case` and `action`.
- `listComments` takes `subjectType` and `subjectId`, checks the registry's read permission **and** that the row exists and is the reader's tenant's to see, and returns the page oldest first with soft-deleted rows present but their bodies replaced by a deleted marker. A kind not in the registry answers 422 `unsupported_subject`; a subject the reader may not read answers 404.
- `addComment` validates the body against `COMMENT_MAX_CHARS` (a setting, default 4000), rejects an empty or whitespace-only body with 422, stores mention rows for the ids given, and answers 201. It does not notify: that is `-b`.
- `editComment` allows the author alone, within `COMMENT_EDIT_MINUTES` (a setting, default 15), writes the text it replaces to a `comment_revision` row and sets `edited_at`, both in the request's transaction (ruling 10: nothing overwritten), and answers 403 `not_author` or 409 `edit_window_closed`. The revision is written before the new body, it is returned by no route, and the audit row carries the comment id and the revision id and no text. Mentions are not re-parsed on an edit; the mention list is fixed at creation, so an edit cannot notify a new person silently.
- `deleteComment` allows the author alone, sets `deleted_at`, and answers 204; a second delete is idempotent.

Every write goes through `record()` with the **record's** title as `subject_title`, a summary naming the actor and the record, and `after` holding the comment id and the mention ids — never the body (rule 12). Un-skip `test_col_s5`.

**Owned paths:**

- `backend/apps/collab/comments.py`
- `backend/apps/collab/subjects.py`
- `backend/apps/collab/tests_comments.py` (new)
- `backend/apps/collab/tests_scenarios.py` (its own skip line only)
- `backend/apps/collab/app.md` (COL-01's status cell only)
- `backend/config/settings.py`, `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (the two settings only)

**Done when:**

- `test_col_s5` is green: a comment is created, edited and deleted, and the captured application log for those requests holds the comment id and the actor id and never the text; the compliance lint fails on a planted logger call that passes a comment body, proved by running it against the plant and then restoring.
- The same test asserts the audit `before` and `after`, the outbox payload and the Sentry `before_send` output for those three writes hold no fragment of the body.
- A reader who cannot read the subject gets 404 on the list and on the write; a reader of another tenant gets 404 on a comment id that exists.
- Editing after the window, editing another person's comment, and an empty or over-long body each answer their declared code and write nothing, the revision row included.
- Two edits leave two `comment_revision` rows holding the two earlier texts, in order; a refused edit leaves none; and `test_col_s5`'s log, audit, outbox and Sentry sweep covers the edit path, so the kept text reaches none of them.
- The list's query count is pinned for a page of 20, including the author and mention lookups.
- No comment route answers 501 any more.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*' (comments.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Nothing overwritten: an edit keeps the text it replaced in an append-only row.
- Tenant content never reaches logs, Sentry, analytics or an unapproved model endpoint.
- Validation at a trust boundary is never simplified away: a body from a browser is untrusted input.
- Never expose a trace; RFC 9457 problem details with a `code` the client branches on.

### c10-notification-prefs: a person's own notification preferences

**Requirements:** COL-02
**Scenarios:** COL-S13 `@integration` (new, written by this task; integration only, so no journey stub is added)
**Depends on:** `c10-collab-models-b`, `c4-mark-seen`, `c6-home-backend`

`membership.notification_prefs` already exists as a `JSONField` carrying `# schema: MembershipNotificationPrefs`. Give the schema a definition and a door:
- `MembershipNotificationPrefs` in `identity/schemas.py` = `{weeklyDigest, reminders, mentions, assignments}`, each a boolean defaulting to true. An unknown key answers 422 `unknown_key`; a missing key means the default, so an older row needs no migration.
- `GET /me` returns `notificationPrefs`; `PATCH /me` accepts it beside `name` and `locale` (INPUT_DELTAS §7 moved it here), writing one audit event with before and after — these are the person's own settings, not tenant content.
- `notify()` already asks for the preference; this task replaces its "absent means on" stub with the real read, and proves an escalation is never muted.

Write COL-S13 into `backend/apps/collab/app.md` and its stub into `collab/tests_scenarios.py` in this commit, then un-skip it. Its app.md heading is `COL-S13 — Notification preferences mute a kind for one person, never an escalation` tagged `@integration` and carrying `(COL-02)`, in the heading form CLAUDE.md §10 fixes, over this Gherkin:

```gherkin
Given Anna has turned mentions off and Erik has not
When Erik mentions them both on a case
Then Anna receives no notification and no mail, and Erik's own row is written
And the comment still lists both mentions, and the case is unchanged for Anna
When an action Anna owns passes the escalation threshold
Then Anna is notified although reminders are off, because escalation is the bank's control and not hers
When Anna turns mentions back on
Then the next mention reaches her, and the muted one is not replayed
```

**Owned paths:**

- `backend/apps/identity/api.py`, `backend/apps/identity/schemas.py`, `backend/apps/identity/me_logic.py` (the preferences only)
- `backend/apps/identity/tests_policies.py` (its own test class only)
- `backend/apps/collab/logic.py` (the preference read only; this task holds `collabcore` for its wave)
- `backend/apps/collab/app.md`, `backend/apps/collab/tests_scenarios.py` (COL-S13 only)

**Done when:**

- COL-S13 is green, escalation included.
- `GET /me` carries `notificationPrefs` and the existing `GET /me` tests and journeys are unchanged.
- A muted kind writes no notification row and queues no mail; a test counts both.
- An unknown preference key answers 422 and writes nothing; a partial patch leaves the other keys alone.
- The `assignments` switch is declared and stored here but proved by chunk 9's assignment scenario, because chunk 10 produces no `assigned` notification; the task's commit body names that scenario so the branch is not left untested by accident.
- The preference is read per recipient at send time, never cached across a run; a test flips it between two sends.
- `bash generate-types.sh` picks up the schema without the task committing the generated files.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.identity apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/identity/*,apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- `JSONField` only with a named schema; no `Dict[str, Any]`.
- A person's own setting is audited with before and after; tenant content is not.
- Kinds in code, values as rows; the API returns keys.

### c10-mail-catalog-a: the mail catalog and the notification mail composer

**Requirements:** COL-02, I18N-01
**Scenarios:** none
**Depends on:** `c10-collab-models-a`, `c6-briefing-backend`

Extend chunk 6's briefing mail composer into a small catalog the three collab mails share (parallel plan ruling 21):
- `backend/apps/collab/mail_strings/en.py` and `sv.py`, one dictionary of keys to plain-text templates, with the subject and the body of `action_due`, `review_due`, `escalation` and `weekly_digest`, plus the shared header and footer. A missing key falls back to en and logs the key, never the text.
- `backend/apps/collab/mail.py`, the composer: it takes a recipient membership, a template key and typed context (a record title, a date, a count, a person's name, a link), picks the recipient's locale, renders plain text and hands the message to the mailer adapter through the same `on_commit` path `identity/mail.py` uses.
- A guard test that every context value a template can interpolate is a record title (a library title, or a tenant record's own title: an action, a case or a register entry, which is what a reminder, an escalation and the digest name), a date, a count, a person's name or a link, and that no template string references a body, a note, an assessment, a summary or a comment.

en and sv only; `c13-i18n-server` adds da, nb and fi to the same files. This task writes no Celery task, which is why it sits a wave before `-b` and touches no file the wave's other packages hold.

**Owned paths:**

- `backend/apps/collab/mail.py`, `backend/apps/collab/mail_strings/`
- `backend/apps/collab/tests_mail.py` (new)

**Done when:**

- Both catalogs hold exactly the same key set; a test fails on a key present in one and missing in the other.
- A recipient with locale `sv` gets the Swedish subject and body, one with `en` the English, and one with an unsupported locale gets en and a log line naming the key.
- The composer refuses, at type level and in a test, any context value that is not a record title, a date, a count, a person's name or a link.
- Nothing in the module logs a recipient address or a body (the rule `identity/mail.py` already follows).
- The diff touches no task and no beat entry, so `collabtasks` is free for the wave.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Tenant content never leaves in a mail: a record title (library or tenant record), a date, a count, a person's name and a link, and nothing else.
- Mail goes only to a host on the reviewed list (D-54); the boot guard is untouched here.
- Every threshold and address is a setting with an env override.

### c10-mail-catalog-b: the delivery task, and one mail per event per day

**Requirements:** COL-02
**Scenarios:** none
**Depends on:** `c10-mail-catalog-a`, `c10-collab-models-b`

`backend/apps/collab/tasks.py` gains the delivery task, which writes the `email_message` row `c10-collab-models-a` created, in the same transaction as the send, with the template, the subject kind and the subject id, so a later run can see what was already sent. It holds `collabtasks` for its wave (rule 5) and is what the reminder, escalation and digest tasks call.

**Owned paths:**

- `backend/apps/collab/tasks.py` (the delivery task only)
- `backend/apps/collab/tests_mail.py` (the delivery half only)

**Done when:**

- Sending twice for the same template, subject and day writes one `email_message` row and sends one mail, proved on the mock outbox.
- The row and the send commit together: a forced failure in the adapter leaves neither, with a test.
- A failed send leaves the row with its error and its status, and the next run may retry it without a duplicate.
- The task is registered and `tests_celery_registration` is green.
- Nothing in the module logs a recipient address, a subject or a body.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- `@tenant_task` in the worker; one tenant activated per run.
- One mail per person per event, proved by a row, not by a memory.
- Tenant content never leaves in a mail.

### c10-delegation: while a person is away, their work reaches their delegate

**Requirements:** COL-02, TEN-04
**Scenarios:** TEN-S4 `@integration` (its reminder and notification half)
**Depends on:** `c10-collab-models-b`, `c8-ten-out-of-office`
**Security review:** yes (work routed to another person)

Add the delegation hop to `notify()` in `collab/logic.py`, in one place, after the recipient check and before the rows are written:
- a recipient whose membership has `out_of_office_until` on or after the tenant's local today and a `delegate` gets no row; the delegate gets it instead, with the absent person recorded on the notification's context so the mail can say on whose behalf it arrived;
- the hop applies to reminder, escalation, assignment and sign-off kinds only. A mention, the digest and read state stay with the absent person: a mention is addressed to a human being, and a digest is that person's own list;
- the delegate must pass the same recipient check: active, in the tenant, able to read the subject. A delegate who cannot read it is skipped and the absent person is left as the recipient, so a notice is never dropped silently;
- one hop only. A delegate who is themself away does not forward again, and a delegation cycle is impossible by construction; a test builds one and proves it terminates;
- delegation grants nothing: the delegate needs the approve permission themself (parallel plan §7.2), and a test proves a delegate without it still gets 403 on the approval route.

If chunk 8 has already un-skipped `test_ten_s4`, extend it here rather than un-skipping it again, and say so in the commit body.

**Owned paths:**

- `backend/apps/collab/logic.py`
- `backend/apps/collab/tests_delegation.py` (new)
- `backend/apps/tenants/tests_scenarios.py` (TEN-S4's skip line only)
- `backend/apps/tenants/app.md` (TEN-04's status cell only)

**Done when:**

- TEN-S4's integration half is green: an absent approver's sign-off request and reminders reach the delegate, the audit records the delegate as actor and the absent person as delegated, and the window closing restores the approver.
- A mention of an absent person still reaches that person and not the delegate; a test proves it per kind.
- A delegate who cannot read the subject is skipped and the absent person keeps the notice.
- A two-step delegation chain writes one row, for the first delegate.
- A delegate without the approve permission still gets 403 on the approval route.
- The whole hop is one function in `logic.py`; no other module knows about out-of-office.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Delegation routes work and grants no permission.
- A notification reaches only active members who can read its record, once per event.
- Permissions, never role names.

### c10-comments-api-b: a mention notifies the person mentioned

**Requirements:** COL-01, COL-02
**Scenarios:** COL-S1 `@integration`
**Depends on:** `c10-comments-api-a`, `c10-collab-models-b`
**Security review:** yes (tenant content at a trust boundary)

Make `addComment` notify, through `notify()` and nothing else:
- one `mention` notification per mentioned member who passes the recipient check, in the same transaction as the comment;
- the notification's title is the **record's** title (the library title for an obligation or a change, the case's own title for a case), never a word of the comment;
- the author is never notified of their own mention;
- a mentioned member who cannot read the subject, is deactivated, or has muted mentions gets none, and the response tells the author which mentions were not delivered, by name, with no reason (COL-S12's Johan);
- a repeated mention of the same person in one comment writes one row.

Un-skip `test_col_s1`.

**Owned paths:**

- `backend/apps/collab/comments.py`
- `backend/apps/collab/tests_comments.py`
- `backend/apps/collab/tests_scenarios.py` (its own skip line only)
- `backend/apps/collab/app.md` (COL-01's status cell only)

**Done when:**

- `test_col_s1` is green: the comment is stored against the case with its subject kind and id, Erik receives a notification linking to the case, and the comment is visible only inside the tenant.
- The notification title equals the record's title exactly, proved by a test that plants a distinctive string in the comment body and asserts it appears in no notification row, no outbox payload and no mail.
- A mention of a member of another tenant answers 422 `unknown_member`, the same answer as an unknown id, and writes nothing.
- The undelivered-mention list names people and never says why.
- The comment write and the notification rows commit together: a forced failure in `notify()` rolls the comment back, with a test.
- `test_col_s5` is still green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- A notification reaches only active members who can read its record, once per event.
- Audit and outbox rows in the same transaction as every write, through `record()`.
- Tenant content never reaches a notification title or an email.

### c10-reminders-escalation-a: reminders before a due date, on the tenant's clock

**Requirements:** COL-02
**Scenarios:** COL-S3 `@integration`
**Depends on:** `c10-mail-catalog-b`, `c10-workflow-policy`, `c10-notification-prefs`, `c9-case-models`, `c8-ten-teams`, `f03-T51`

Build `backend/apps/collab/reminders.py` and the beat that drives it:
- one hourly `CELERY_BEAT_SCHEDULE` entry in `collab/tasks.py` that selects the tenants whose local wall time has just reached `REMINDER_SEND_HOUR` (a setting, default 07:00) and fans out one `@tenant_task` per tenant. Fan out, never chain.
- for each tenant, for each lead day in `reminder_days_before`, find the records due on the tenant-local date plus that lead: an action's due date and a case's triage due time to start with, the shapes chunk 9 built.
- resolve the people responsible (the owner, the owning team's active members) and call `notify()` with kind `due_soon`; an overdue record uses `overdue`.
- queue the mail through `collab/mail.py`, whose `email_message` uniqueness makes a second run of the same day send nothing.

Reword COL-S3 in `backend/apps/collab/app.md` first, then un-skip `test_col_s3` against the reworded text. COL-S3 reads today "a digest scheduled for Monday 08:00", and the digest is `c10-digest-b`'s, six waves later; a test cannot prove a scenario that names a feature nobody has built, and CLAUDE.md §10 requires the test and the scenario to say the same thing. The Given becomes a reminder scheduled for the tenant's `REMINDER_SEND_HOUR` and the Then the reminder arriving at that local hour; the scenario's point, that the one beat runs on the tenant's timezone across a daylight saving change, is unchanged, and `c10-digest-b` keeps COL-S3 green for the weekly entry as its own done-condition already says. Drive the clock: a tenant in `Europe/Helsinki` is served at that local hour when the beat fires in UTC, across a daylight saving change too, and the fixture anchors to the tenant-local date rather than to "now plus hours".

**Owned paths:**

- `backend/apps/collab/reminders.py`
- `backend/apps/collab/tasks.py` (the beat entry and the fan-out task only)
- `backend/apps/collab/tests_reminders.py` (new)
- `backend/apps/collab/tests_scenarios.py` (its own skip line only)
- `backend/apps/collab/app.md` (COL-S3's Gherkin only, reworded from the digest to the reminder for the reason above; no other task edits that scenario)
- `backend/config/settings.py`, `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (the send hour only)

**Done when:**

- `test_col_s3` is green, including the daylight saving crossing in both directions, and the test says step for step what COL-S3 now says in `app.md`.
- A record due in three days with a lead of `[3]` reminds its owner once; running the job again the same day reminds nobody.
- A tenant with `[1, 3, 7]` reminds on each of the three days and not in between.
- The beat entry is registered and `tests_celery_registration` is green; the fan-out task is `@tenant_task` and activates exactly one tenant.
- A person whose `reminders` preference is off gets no row and no mail; an owner who is no longer active gets neither.
- Every notification whose mail was queued carries `emailed_at`, set in the transaction that queued it; a test asserts no row is left with a sent mail and a null stamp.
- The query count per tenant is pinned and does not grow with the number of lead days.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- `@tenant_task` in the worker; one tenant activated per run.
- Fan out, never chain; jobs have a status endpoint or a `job_run` row.
- Clocks anchor to the tenant-local date plus a fixed wall time.

### c10-reminders-escalation-b: escalation to the head of the owner's department

**Requirements:** COL-02
**Scenarios:** none on its own (COL-S2's integration is `c10-digest-b`'s, once all three parts exist)
**Depends on:** `c10-reminders-escalation-a`, `f03-T51`

Build `backend/apps/collab/escalation.py` behind a second task in the same fan-out:
- a record overdue by more than the tenant's `escalate_after_days` escalates once, with kind `escalation`;
- the recipients are the head of the department of the owner's team (`org_unit.head_user_id`, reached from the team's org unit) **and** every active member holding the tenant's `escalate_to_role` (ruling 7), each once through the recipient check;
- where the team has no department, or the department has no head, the role holders alone are notified and the escalation records that there was no head, so the gap is visible rather than silent;
- the owner themself is notified too, because an escalation about your work that you do not see is a surprise in a meeting;
- escalation ignores notification preferences (COL-S13) and is never muted;
- one escalation per record: a second run finds the `email_message` row and sends nothing, and a record that stays overdue does not escalate weekly.

**Owned paths:**

- `backend/apps/collab/escalation.py`
- `backend/apps/collab/tasks.py` (the escalation task only)
- `backend/apps/collab/tests_escalation.py` (new)

**Done when:**

- An action five days overdue with a threshold of five escalates to the department head and the compliance officers, once each.
- A team with no department, and a department with no head, both escalate to the role holders and record the missing head; neither raises.
- A second run escalates nobody; a test runs the job three days running.
- A recipient with reminders muted still receives the escalation.
- No escalation mail carries a case note, an assessment or a comment: the guard test of `c10-mail-catalog-a` covers the new template and a test asserts the rendered body.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- A notification reaches only active members who can read its record, once per event.
- Every threshold is a setting or a tenant column, never a literal.
- Tenant content never leaves in a mail.

### f03-T78a: the participation and review producers

**Requirements:** COL-02, COL-04, HOM-05
**Scenarios:** none (COL-S10 is `-b`'s)
**Depends on:** `c10-reminders-escalation-b`, `f03-T77`
**Security review:** yes (it tells people a record exists)

Two of the three PRD 0.3 kinds gain a producer, each calling `notify()` and writing nothing itself. The third, `involved_item_changed`, is `f03-T78c`'s: its call sites are in `watch/` and `library/`, so the two tasks share a wave without sharing a path.
- `participant_added`: adding a participant to a register entry or a case, in the transaction that already writes the participant row and its audit event;
- `review_due`: reached by `c10-reminders-escalation-a`'s lead-day walk over the next review dates `f03-T59` built, added here rather than there so the review branch is one change (`f03-T79` proves it).

The candidates each producer passes in are the owner, the participants and the active members of a participating team, with the reason for each; the de-duplication and the read check are `notify()`'s, not theirs. The person who performed the act is never a candidate.

**Owned paths:**

- `backend/apps/collab/participants.py` (the notification call only; the participant routes are chunk 8's and chunk 9's). If chunk 8 put the participant writes in `collab/logic.py` instead, this task takes `collabcore` for its wave and the wave table is corrected at dispatch
- `backend/apps/collab/reminders.py` (the review branch's candidates only)
- `backend/apps/collab/tests_producers.py` (new)

**Done when:**

- Each of the two events produces exactly one `notify()` call, proved by a test that patches `notify` and counts.
- No producer builds its own recipient list, filters on permission or de-duplicates; a test asserts each passes candidates and a reason and nothing else.
- The person who added the participant is never in the candidates.
- Every call site is inside the transaction of the write it follows.
- The diff touches nothing under `apps/watch/` or `apps/library/`, so `f03-T78c` can run beside it.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- One recipient check; a producer names candidates and a reason and decides nothing.
- Audit and outbox rows in the same transaction as every write.
- Permissions, never role names.

### f03-T78c: the involved-item producer, in watch and library

**Requirements:** COL-02, HOM-05
**Scenarios:** none (COL-S10 is `f03-T78b`'s)
**Depends on:** `c10-reminders-escalation-b`, `f03-T77`
**Security review:** yes (it tells people a record exists, from inside the library apply path)

`involved_item_changed` gains its producer at its two call sites: a person confirming a WAT-04 link from a change to an obligation someone is involved in, and a new obligation version being applied to such an obligation (D-25's two sources of "changes on your items", and no third). Each calls `notify()` with the owner, the participants and the active members of a participating team as candidates with their reason, inside the transaction of the write it follows, and decides nothing itself.

**Owned paths:**

- `backend/apps/watch/curation.py`, `backend/apps/library/apply.py` call sites (the `notify()` call only, at most three lines each)
- `backend/apps/collab/tests_producers_links.py` (new)

**Done when:**

- Each of the two call sites produces exactly one `notify()` call, proved by a test that patches `notify` and counts.
- The person who confirmed the link or applied the version is never in the candidates.
- An unconfirmed agent suggestion produces nothing (D-25).
- The library fence is green: `library/apply.py` gains a notification call, not a library write, and the diff touches no library writer.
- The producer builds no recipient list and filters on no permission; a test asserts it passes candidates and a reason and nothing else.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.watch apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*,apps/watch/*,apps/library/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- AI output is labelled until a person confirms it; an unconfirmed suggestion notifies nobody.
- Proposals are the only door into the library; a notification call is not a library write.
- Audit and outbox rows in the same transaction as every write.

### f03-T78b: one recipient check over every kind, once per person

**Requirements:** COL-02, COL-04
**Scenarios:** COL-S10 `@integration`
**Depends on:** `f03-T78a`, `f03-T78c`
**Security review:** yes (the recipient check)

Extend the subject registry and the recipient check so the three new kinds go through exactly the same door as the old ones, and prove it:
- register the remaining subject kinds the three producers address, each with its read permission and its row lookup;
- a person involved twice (as owner and through a team) receives one notification, and a person involved on two records receives two;
- a member whose roles lack the subject's read permission, and a deactivated member, receive none, whatever the kind;
- every title is the library title and every mail carries the title and a link only.

Un-skip `test_col_s10`.

**Owned paths:**

- `backend/apps/collab/logic.py`
- `backend/apps/collab/subjects.py`
- `backend/apps/collab/tests_notify.py`
- `backend/apps/collab/tests_scenarios.py` (its own skip line only)
- `backend/apps/collab/app.md` (COL-02's status cell only)

**Done when:**

- `test_col_s10` is green line by line: Erik's `participant_added`, Anna once although involved twice, Karin once, and none for the confirmer, for Lisa without `register.read` or for the deactivated Johan; the same people once each on a new version, in their own language.
- A parameterised test runs every `NotificationKind` chunk 10 produces through the same check and asserts the same four refusals, so no kind can grow its own rule.
- The guard test of ruling 1 is still the only writer.
- No notification title or email carries tenant text: the planted-string test of `c10-comments-api-b` is extended to the three new kinds.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*' (logic.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- One recipient check for every kind; a per-kind rule is a finding.
- A notification reaches only active members who can read its record, once per event.
- Permissions, never role names.

### f03-T79: review reminders reach the people responsible, once

**Requirements:** COL-02
**Scenarios:** COL-S11 `@integration`
**Depends on:** `f03-T78b`

Finish the review branch of `collab/reminders.py`: at the tenant's lead time, remind the people responsible for a next review date, whichever row carries it — the first-line owner of a compliant obligation, the owner of that obligation's row for a legal entity, and the owning team of a register entry, each once, in their language. A team reminds each of its active members; a person responsible twice is reminded once.

Un-skip `test_col_s11`. It runs the job twice on the same day and proves the second run reminds nobody.

**Owned paths:**

- `backend/apps/collab/reminders.py` (the review branch only)
- `backend/apps/collab/tests_reminders.py`
- `backend/apps/collab/tests_scenarios.py` (its own skip line only)

**Done when:**

- `test_col_s11` is green: Anna, Erik and each active member of "Legal" reminded once at a 30-day lead, and nobody reminded twice on a second run.
- A compliant obligation's review is reminded: a test proves the compliant rows are not filtered out, which is the mistake HOM-S8 exists to catch.
- The reminder mail is in each recipient's locale, asserted on the mock outbox.
- The query count for a tenant with 200 review dates is pinned and does not grow per recipient.
- COL-S3 and the due-date reminders are still green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.register apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- One recipient check; the review branch adds no rule of its own.
- Clocks anchor to the tenant-local date; no fixture depends on the real today.

### f03-T81: the digest's open items come from the My work service

**Requirements:** COL-02, HOM-05
**Scenarios:** none on its own (COL-S2 is `c10-digest-b`'s)
**Depends on:** `f03-T78b`

Build `backend/apps/collab/digest.py`: for one recipient in one tenant, the digest's content is `home/my_work.py`'s answer for that reader's own scope — the same buckets, the same permission-filtered rows and the same counts — trimmed to `DIGEST_MAX_ITEMS` (a setting, default 20) with an "and N more" count. No second definition of "open items" is written, and no query in this module reads a case, an action or a register entry directly.

**Owned paths:**

- `backend/apps/collab/digest.py`
- `backend/apps/collab/tests_digest.py` (new)
- `backend/config/settings.py`, `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (the cap only)

**Done when:**

- A test asserts the digest's ids equal `GET /me/work`'s ids for the same reader, bucket by bucket, on a seeded tenant with rows in all four buckets.
- A grep-style test fails if `digest.py` imports a model other than the membership it is composing for: the content comes from the service.
- A reader with no open items produces no digest at all, rather than an empty mail.
- Rows and counts respect the reader's permissions: a member without `cases.read` sees neither the case rows nor their count, which is HOM-S10's rule applied to the mail.
- The trim keeps the most urgent rows and the count of what it dropped.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.home apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*,apps/home/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- "My open items" has one definition (D-23); a second one is a finding.
- Rows and counts come from the permission-filtered set, never from a count taken before filtering.

### c10-digest-a: the weekly digest mail, one per person per week

**Requirements:** COL-02
**Scenarios:** none (COL-S2 is `-b`'s)
**Depends on:** `f03-T81`, `c10-mail-catalog-b`, `c10-workflow-policy`, `c10-notification-prefs`, `c10-reminders-escalation-b`

Compose and send, over `f03-T81`'s content:
- one mail per active member whose `weeklyDigest` preference is on, in that member's locale, from the `weekly_digest` template;
- the subject names the week and the number of open items; the body lists the buckets with their counts and at most `DIGEST_MAX_ITEMS` rows, each a record title and a link, and nothing else;
- `email_message` carries the template and the week, so a re-run of the same week sends nothing;
- a member with no open items receives no mail; the absent digest is not an error.

The delegate does not receive another person's digest (`c10-delegation`'s rule), and a digest is never escalated, forwarded or copied to a department head.

**Owned paths:**

- `backend/apps/collab/digest.py` (the composer half)
- `backend/apps/collab/tests_digest.py`

**Done when:**

- A Swedish-speaking and an English-speaking member of the same tenant each receive their own digest in their own language, asserted on the mock outbox.
- Running the send twice in one week sends one mail per person, proved by the outbox and the `email_message` rows.
- A member with `weeklyDigest` off, a deactivated member and a member with no open items each receive nothing.
- The rendered body contains no case note, assessment, comment or other tenant text: a planted-string test over a seeded tenant with comments on every record.
- The mail's links are absolute URLs built from `APP_BASE_URL` and carry no token.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.home apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Tenant content never leaves in a mail.
- One mail per person per week, proved by a row, not by a memory.

### c10-digest-b: the weekly beat, and COL-S2 end to end in the worker

**Requirements:** COL-02
**Scenarios:** COL-S2 `@integration` (as `f03-T81` amends it)
**Depends on:** `c10-digest-a`

Add the weekly entry to `collab/tasks.py`: the same hourly beat picks the tenants whose local wall time has reached `DIGEST_SEND_HOUR` (a setting, default 07:00) on the tenant's `digest_weekday`, and fans out one `@tenant_task` per tenant. Fan out, never chain.

Un-skip `test_col_s2`, which now proves all three parts in one test, as COL-S2 reads after `f03-T81`'s amendment: an action due in three days with a lead of three reminds its Swedish-speaking owner once, in sv; five days overdue with a threshold of five notifies the head of the owner's department and the compliance officer; and the weekly digest job gives each user one digest in their language, listing their open items as My work counts them.

**Owned paths:**

- `backend/apps/collab/tasks.py` (the weekly entry and its fan-out task only)
- `backend/apps/collab/tests_scenarios.py` (its own skip line only)
- `backend/apps/collab/app.md` (COL-02's status cell only)
- `backend/config/settings.py`, `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (the send hour only)

**Done when:**

- `test_col_s2` is green, in one test, with the clock frozen and the tenant timezone set.
- The beat entry is registered, `tests_celery_registration` is green, and the fan-out task is `@tenant_task`.
- A tenant whose `digest_weekday` has not arrived gets nothing; the day after, it gets exactly one round.
- COL-S3 and COL-S11 are still green: the three schedules share one beat and one timezone rule.
- A `job_run` row records each fan-out with its counts, so a missed week is visible without reading logs.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.home apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Fan out, never chain; every job leaves a `job_run` row.
- `@tenant_task` in the worker; one tenant per run.
- Clocks anchor to the tenant-local date plus a fixed wall time.

### f03-T80a: my comments and mentions, filtered by what I can read

**Requirements:** COL-01, HOM-05
**Scenarios:** COL-S12 `@integration`
**Depends on:** `f03-T78b`, `c10-comments-api-b`, `c10-notifications-api-c`, `f03-T62`
**Security review:** yes (a cross-record read filtered by permission)

Build `backend/apps/collab/me_comments.py` behind `listMyComments`:
- `about=written` returns the reader's own comments, newest first, paginated; `about=mentioned` returns the comments that mention them;
- both are filtered through the subject registry: a comment whose subject the reader may not read is left out, and its kind is named in `permissionLimitedKinds` so the panel can say "cases are limited by your permissions" without naming a record;
- each row carries the record's title and a link, the author, the time, and the body — the body is tenant content the reader is allowed to see, and it travels in the response and nowhere else;
- add the awareness half to `home/my_work.py`: a comment on a record you are responsible for joins "Changes on your items" for `MY_WORK_AWARE_DAYS` (D-25's window, already a setting), carrying the record as the reason. HOM-S11 says today that "changes on your items are confirmed links and new versions only", which D-25 amends from chunk 10 on; this task rewords HOM-S11's Gherkin and its test to name comments and mentions as the third source, so the new behaviour does not contradict a green test;
- widen the compliance lint (`backend/scripts/compliance_check.py`) from logger calls to `record()` and outbox payloads: a `record(...)` whose `before`, `after` or `payload` carries a value named like tenant content (`body`, `text`, `comment`, `note`, `summary`, `assessment`, `question`) is a finding with its own suppression id, planted and proved to fail.

Un-skip `test_col_s12`.

**Owned paths:**

- `backend/apps/collab/me_comments.py`
- `backend/apps/home/my_work.py` (the comments source only)
- `backend/scripts/compliance_check.py`, `backend/apps/shared/tests_compliance_lint.py`
- `backend/apps/collab/tests_me_comments.py` (new)
- `backend/apps/collab/tests_scenarios.py` (its own skip line only)
- `backend/apps/collab/app.md`, `backend/apps/home/app.md` (status cells only)

**Done when:**

- `test_col_s12` is green: Anna's mentions and her two comments newest first in pages; Johan, whose role lacks `cases.read`, gets no case comment, sees `cases` in `permissionLimitedKinds`, and received no notification for the mention; Johan's comment on Anna's obligation appears on Anna's My work under "Changes on your items" for the window.
- The same test asserts the application log, the audit `after` value and the outbox payload for those requests hold ids and never the comment text.
- The widened lint fails on a planted `record(after={"body": ...})` and passes on the tree, proved by running it against the plant and restoring.
- `test_hom_s12`'s pinned query count is unchanged: the comments source adds no per-row query.
- The amended `test_hom_s11` is green and its app.md scenario says the same thing, so the requirements-coverage gate stays green.
- `test_col_s5` is still green, and `listMyComments` no longer answers 501.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.home apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*,apps/home/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Rows and counts come from the permission-filtered set.
- Tenant content never reaches logs, Sentry, audit values, outbox payloads or webhooks.
- No gate lowered: the lint is widened, never relaxed.

### c10-fe-collab-feature: the collab feature layer

**Requirements:** COL-01, COL-02
**Scenarios:** none
**Depends on:** `c10-notifications-api-b`, `c10-comments-api-b`, `c10-notification-prefs` (its `api.ts` calls `PATCH /me`'s preferences), `c10-collab-design-a`, `c10-collab-design-b`, `x-frontend-split`

`frontend/src/features/collab/` already exists from `f03-T63`'s participants panel. Add the layer the three chunk 10 surfaces share, and nothing they do not yet call (rule 6):
- `types.ts` from `api.generated.ts`, never hand-written;
- `api.ts` with the eight collab operations and `PATCH /me`'s preferences;
- `hooks.ts` with the React Query hooks, including the optimistic mark-as-read and its rollback;
- `collab-presentation.ts`: one presentation function per record type, turning a notification kind into its pill tone and its catalog key, and a comment row into its author, time and "edited" line. No component decides a tone.
- the `collab` message namespace in en and sv, with every string the panel, the inbox and the preferences need;
- the `tone-by-kind.ts` entries for `NotificationKind`.

No screen, no route and no page in this task: it is the layer the screens call.

**Owned paths:**

- `frontend/src/features/collab/{types,api,hooks,collab-presentation}.ts`
- `frontend/src/features/collab/*.test.ts`
- `frontend/src/messages/collab/{en,sv}.json`
- `frontend/src/features/shared/tone-by-kind.ts` (its own entries only)

**Done when:**

- Every notification kind has a tone, and a unit test fails on a kind with none, so a kind added later cannot render untoned.
- The pill gallery gains the new tones; the task does not commit the snapshot baselines, and the main agent regenerates and reviews them image by image at the merge (rule 2), so NFR-S8 stays honest.
- `npm run check:messages` is green: en and sv hold the same keys and no screen string is missing.
- The presentation tests cover every kind and both themes' tone choices.
- `npm run typecheck` is green against regenerated types, which the task does not commit.
- No string literal appears in any component this task adds.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `bash generate-types.sh` to typecheck against the real contract; revert the generated files before committing

**Invariants:**

- Pills only through `Pill`; six tones, chosen by kind, never by a person.
- No string literals in JSX text; every string in the message catalogs.
- Typography roles only; `logger` only, never `console.log`.

### c10-fe-suggest-a: the create-or-suggest picker

**Requirements:** VOC-03
**Scenarios:** none (VOC-S6's journey is `-b`'s)
**Depends on:** `c10-tagging-api-b`

Build the picker component in `frontend/src/features/vocabularies/`, from `design/screens/picker-create-or-suggest.html`: a combobox over a tenant list that, on a value that does not exist, offers "Create" to a holder of `vocab.manage` and "Suggest" to everybody else, shows the near-duplicate hint the API returns (409 `duplicate_key` with the existing row, 422 `near_duplicate` with the near match), and says what happened after either. It calls `createVocabularyRow` and `suggestVocabularyRow`, both on `main` since chunk 2 (ruling 5).

The component is generic over a tenant list name so the tags picker and later pickers share it; it is used once in this chunk, so it gains no option nobody asked for.

**Owned paths:**

- `frontend/src/features/vocabularies/CreateOrSuggestPicker.tsx` and its test
- `frontend/src/features/vocabularies/{api,hooks}.ts` (the two operations only)
- `frontend/src/messages/vocabularies/{en,sv}.json` (its own keys only)

**Done when:**

- The picker offers "Create" with the permission and "Suggest" without it, driven by the permissions on `GET /me` and never by a role name.
- Both hint states render from the API's `code`, never from its `detail`.
- Keyboard use works end to end: open, type, choose, create, with the announcements the design card names.
- Both themes pass the contrast test, and the component holds no string literal.
- `npm run test:coverage` covers both branches and both error codes.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`

**Invariants:**

- Permissions, never role names.
- The client branches on `code`, never on `detail`.
- No abstraction for code used once: the picker is generic only where the two call sites differ.

### c10-fe-suggest-b: tags on the obligation page, created or suggested where they are used

**Requirements:** VOC-03, VOC-08 (its single-record half)
**Scenarios:** VOC-S6 `@e2e`
**Depends on:** `c10-fe-suggest-a`, `c3-fe-obligation-versions`

Mount the picker on the obligation page as a tags panel: the record's tenant tags as `Pill`s with a remove control for a holder of `vocab.manage`, the picker to add one, and a read-only list for everybody else. It calls `POST /taggings` and `DELETE /taggings` from `c10-tagging-api-a`.

Un-fixme VOC-S6's journey in `taxonomy.journey.spec.ts`: sign in through the UI with a passkey as a holder of `vocab.manage`, type a value that does not exist on the obligation's tags picker, see "Create"; sign in as a member without it, see "Suggest", and see the suggestion land in the admin's list. Import `test` from `support/api-guard` and declare the expected 422 where it happens.

**Owned paths:**

- `frontend/src/components/inventory/ObligationScreen.tsx` (the tags panel only), `frontend/src/features/register/` is **not** touched
- `frontend/src/features/vocabularies/hooks.ts` (the tagging operations only)
- `frontend/src/messages/vocabularies/{en,sv}.json` (its own keys only)
- `frontend/tests/e2e/taxonomy.journey.spec.ts` (VOC-S6's block only)
- `backend/apps/taxonomy/app.md` (VOC-03's status cell only)

**Done when:**

- VOC-S6's journey is green against the real stack, signed in by passkey through the UI, with no mocked response and no injected token.
- A reader without `vocab.manage` sees the tags and no remove control, and the API refuses the write if it is called anyway.
- The panel renders in both themes at 375 px and at desktop width.
- The page's data-fetching budget is unchanged: the tags come with the obligation read, not from a second round trip.
- The journey runs on the chunk 2 and chunk 3 seed and needs nothing from `c10-e2e-seed-a` or `-b`, which land later; if a tag row is missing, this task adds its own one-line seed call rather than waiting.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "VOC-S6"`

**Invariants:**

- Sign in through the UI with a passkey; never inject a token or a cookie, never mock an API response.
- Pills only through `Pill`; no string literals in JSX.

### c10-fe-bulk-tagging-a: selection, preview and commit on the inventory

**Requirements:** VOC-08
**Scenarios:** none (VOC-S12's journey is `-b`'s)
**Depends on:** `c10-fe-suggest-b`, `c3-fe-instruments`

Add selection and bulk tagging to the inventory list: row checkboxes with a select-all for the page, a "Tag" control for a holder of `vocab.manage`, the picker from `c10-fe-suggest-a`, the preview `POST /taggings/preview` returns (how many would gain the tag, how many already carry it, how many were skipped), and the commit with its result. Above the cap the control says so and refuses before calling. If six rows are not already in the seed for `-b`'s journey, this task adds its own one-line seed call.

**Owned paths:**

- `frontend/src/components/inventory/InventoryScreen.tsx` and its tests
- `frontend/src/features/library/hooks.ts` (the batch operations only)
- `frontend/src/messages/library/{en,sv}.json` (its own keys only)
- `backend/apps/shared/e2e_seed.py` (one seed call, only if the rows are missing)

**Done when:**

- Selection survives a filter change on the same page and is cleared by a page change, so a commit can never act on rows the person is no longer looking at; a unit test pins it.
- A member without `vocab.manage` sees no selection and no "Tag" control.
- The preview and the commit are two calls, and the commit sends the ids the preview showed, not the current selection.
- The screen stays within its budget with 100 rows selected, and renders at 375 px in both themes.
- No string literal appears in the component, and the counts come from the API's answer, never recomputed.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`

**Invariants:**

- One audited transaction; the screen never writes row by row.
- The client branches on `code`, never on `detail`; no string literals in JSX.

### c10-fe-bulk-tagging-b: VOC-S12 from the inventory, end to end

**Requirements:** VOC-08
**Scenarios:** VOC-S12 `@e2e`
**Depends on:** `c10-fe-bulk-tagging-a`

Un-fixme VOC-S12's journey: six rows selected, "Custody" applied, the preview listing the six and which already carry it, the commit, and the tag then visible on each row and usable as the `tenantTag` filter. Import `test` from `support/api-guard` and declare the expected errors where they happen.

**Owned paths:**

- `frontend/tests/e2e/taxonomy.journey.spec.ts` (VOC-S12's block only)
- `backend/apps/taxonomy/app.md` (VOC-08's status cell only)

**Done when:**

- VOC-S12's journey is green against the real stack, signed in by passkey through the UI, with no mocked response and no injected token.
- The journey runs on the seed as it stands, with no fixture of its own.
- VOC-S6's journey, which walks the same picker, is still green.
- One audited batch reaches the backend for the six rows, asserted on the screen's result and not on the database.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run test:e2e -- --grep "VOC-S12|VOC-S6"`

**Invariants:**

- Sign in through the UI with a passkey; never mock an API response.
- Every spec imports `test` from `tests/e2e/support/api-guard`; an expected error is declared where it happens.

### c10-fe-workflow-policy: the workflow policy section

**Requirements:** COL-02, TEN-01
**Scenarios:** none
**Depends on:** `c10-workflow-policy`, `c10-collab-design-b`, `x-frontend-split`

Build `/admin/workflow` from `design/screens/admin-workflow.html` (ruling 8), in its own feature directory: the reminder lead days, the escalation threshold, the escalation role, the digest weekday and the triage target, each with its unit and its platform default, saved through `PATCH /tenant`. The navigation entry appears only for a holder of `workflow.manage`, and the page answers the restricted state for anybody else rather than a blank screen.

**Owned paths:**

- `frontend/src/app/(tenant)/admin/workflow/page.tsx`
- `frontend/src/features/workflow-policy/` (new)
- `frontend/src/messages/workflow/{en,sv}.json` (new)
- `frontend/src/shared/navigation/registry.ts` (its own entry only)

**Done when:**

- A holder of `workflow.manage` can change each field and see the saved state; a 422 renders the field-level message from the `code`.
- A member without the permission sees no navigation entry and the restricted page, never a blank one.
- The registry snapshot test is green (at most four ranked destinations; the entry sits under More on phones).
- Both themes render at 375 px and at desktop width, and no string literal appears in the component.
- The page shows the platform default beside each field, so a tenant sees what it is changing from.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`

**Invariants:**

- Permissions, never role names; a missing permission is a restricted page, not a blank one.
- No string literals in JSX; typography roles only.

### c10-fe-comments-panel-a: the comments panel component

**Requirements:** COL-01
**Scenarios:** none (the journeys are `-b`'s)
**Depends on:** `c10-fe-collab-feature`, `f03-T52` (the mention control calls `GET /reference/people`, which that chunk 8 task builds; rule 7 says a screen calls no stub)

Build the panel from `design/system/comments-and-mentions.md`, in `frontend/src/features/collab/`: the list oldest first with author, time and "edited"; the composer with the visibility line "Everyone in your organisation can read comments" (D-22, D-60), taken from the catalog and identical on all three surfaces; the mention control over `GET /reference/people`; "Edit" and "Delete" on the author's own rows only, driven by `canEdit` and `canDelete` from the API and never recomputed in the browser; the deleted-row marker; the undelivered-mention notice naming the people, with no reason; and the empty, loading and error states.

The panel takes a subject kind and id and nothing else, so the three surfaces mount the same component.

**Owned paths:**

- `frontend/src/features/collab/CommentsPanel.tsx` and its tests
- `frontend/src/features/collab/{api,hooks}.ts` (the comment operations only)
- `frontend/src/messages/collab/{en,sv}.json` (its own keys only)

**Done when:**

- The composer's line is the one string in the catalog, asserted equal to the design card's text by a unit test, so the three surfaces cannot drift.
- Edit and delete appear only on the author's own rows and only while `canEdit` is true; a test proves the browser does not decide.
- The edit window closing mid-session renders the 409 `edit_window_closed` message and leaves the row intact.
- The panel renders at 375 px with a long comment and a long record title, in both themes.
- No component holds a string literal, and no tone is chosen outside `collab-presentation.ts`.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`

**Invariants:**

- The client branches on `code`, never on `detail`.
- The server decides what a person may do; the browser renders the decision.
- No string literals in JSX text.

### f03-T80b: the Comments and mentions panel on My work

**Requirements:** COL-01, HOM-05
**Scenarios:** COL-S12 `@e2e`
**Depends on:** `f03-T80a`, `c10-fe-collab-feature`

Add the panel to `components/work/MyWorkScreen.tsx`, below the four sections, from `tenant-my-work.html` §6: the two tabs "Mentions" and "My comments", paginated from `GET /me/comments`, the permission-limited line naming the kinds the API returned, and the composer with its visibility line. The composer on My work writes against the record the row names, so it reuses `CommentsPanel`'s composer rather than a second one.

Un-fixme COL-S12's journey in `collab.journey.spec.ts`: Anna sees Erik's mention with a link to the case and her own two comments newest first in pages, and the composer says everyone in the organisation can read comments; Johan, whose role lacks `cases.read`, sees no case comment and sees cases listed as permission-limited.

**Owned paths:**

- `frontend/src/components/work/MyWorkScreen.tsx` (the panel only)
- `frontend/src/features/my-work/{api,hooks}.ts` (the comments operations only)
- `frontend/src/messages/work/{en,sv}.json` (its own keys only)
- `frontend/tests/e2e/collab.journey.spec.ts` (COL-S12's block only)
- `backend/apps/collab/app.md`, `backend/apps/home/app.md` (status cells only)

**Done when:**

- COL-S12's journey is green against the real stack, both readers, signed in by passkey through the UI.
- The panel's composer line is the same catalog string as the panel component's, asserted by the same unit test.
- The permission-limited line names kinds, never records, and is absent when nothing was limited.
- HOM-S7 and HOM-S9's journeys are still green: the panel is added below the four sections and changes none of them.
- The screen renders at 375 px in both themes with both tabs empty and both full.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "COL-S12|HOM-S7|HOM-S9"`

**Invariants:**

- Sign in through the UI with a passkey; never mock an API response.
- Notes are shared comments; nothing on this panel suggests a private note (D-60).

### c10-e2e-seed-a: the comments and notifications seed

**Requirements:** COL-01, COL-02
**Scenarios:** none (it feeds them)
**Depends on:** `c9-e2e-seed`, `c10-comments-api-b`
**Security review:** yes (seed data crosses no tenant)

The tagging journeys (VOC-S6 and VOC-S12) run several waves before this task and need nothing from it: they read the tenant tag list chunk 2 seeded and the obligations chunk 3 seeded, and `c10-fe-bulk-tagging-a` adds its own one-line seed call if six rows are not already there. This half seeds what the comments panel, the inbox and J-8 need, so `c10-fe-comments-panel-b` and `c10-j8-extension` wait for it and not for the digest.

Extend `backend/apps/shared/e2e_seed.py`, never mock, with what those journeys need and nothing more:
- comments on a case and on an obligation in tenant A, one of them mentioning the seeded reader, one edited (its `comment_revision` row seeded with it), one soft-deleted;
- one comment in tenant B on a shared obligation, so J-8 can prove the two never meet;
- unread and read notifications for the seeded logins, one of each kind the chunk's comment and participation paths produce.

Every date derives from the tenant-local anchor, never from the real today. Every row is realistic, from the prototype's data. Add one seed call and, where a journey needs a new person, one login to `e2e_logins.py`.

**Owned paths:**

- `backend/apps/shared/e2e_seed.py` (its own seed call only)
- `backend/apps/shared/e2e_logins.py` (its own logins only)
- `backend/apps/shared/tests_seed_integrity.py` (its own assertions only)

**Done when:**

- `manage.py seed_e2e` is idempotent: running it twice leaves the same row counts and the same ids.
- The seed integrity test proves every seeded comment, revision and notification row carries the tenant of its subject, and that no tenant B row points at a tenant A record.
- Every seeded date is derived from the anchor; a test fails if a literal date appears in this seed block.
- The full E2E stack boots on the new seed and the existing `@smoke` journeys are still green.
- No journey needs a fixture outside the seed, and nothing is mocked.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput`
- `cd frontend && npm run test:e2e -- --grep @smoke`

**Invariants:**

- Extend `seed_e2e`, never mock: idempotent, deterministic, realistic.
- Clocks anchor to the tenant-local date plus a fixed wall time.
- Two zones: a seeded tenant row never points at another tenant's record.

### c10-e2e-seed-b: the dated work behind reminders, escalation and the digest

**Requirements:** COL-02
**Scenarios:** none (it feeds them)
**Depends on:** `c10-e2e-seed-a`, `c10-reminders-escalation-b`, `c10-digest-b`
**Security review:** yes (seed data crosses no tenant)

Seed what the notification screens' journeys read, which needs the worker that `c10-digest-b` finished (the reason ruling 17 of the parallel plan gave for chunk 6's emailed briefing snapshot):
- an action due in three days and one five days overdue, owned by a Swedish-speaking member of a team whose department has a head, so the reminder, the escalation and the digest all have a subject;
- a member with mentions muted and a member out of office with a delegate;
- one sent digest for the previous week, with its `email_message` row, so the notifications screen has history.

Every date derives from the tenant-local anchor, never from the real today.

**Owned paths:**

- `backend/apps/shared/e2e_seed.py` (its own seed call only)
- `backend/apps/shared/e2e_logins.py` (its own logins only)
- `backend/apps/shared/tests_seed_integrity.py` (its own assertions only)

**Done when:**

- `manage.py seed_e2e` is still idempotent with both halves in place, and the row counts are stable across two runs.
- The seed integrity test proves every seeded `email_message` row carries the tenant of its subject and its recipient's membership.
- Running the reminder, escalation and digest jobs on the seeded tenant sends what the journeys expect and nothing more, with the clock anchored.
- Every seeded date is derived from the anchor; a test fails on a literal date in this seed block.
- The existing `@smoke` journeys are still green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput`
- `cd frontend && npm run test:e2e -- --grep @smoke`

**Invariants:**

- Extend `seed_e2e`, never mock: idempotent, deterministic, realistic.
- Clocks anchor to the tenant-local date plus a fixed wall time.
- Two zones: a seeded tenant row never points at another tenant's record.

### c10-fe-notifications-a: the inbox and the bell

**Requirements:** COL-02
**Scenarios:** none (COL-S2's journey is `-b`'s)
**Depends on:** `c10-fe-collab-feature`, `c4-console-shell`

Build `/notifications` from `design/screens/tenant-notifications.html`, and the bell in the who panel of the tenant shell: the unread dot from the first page of `GET /notifications?unread=true`, the inbox with its kind pills and record links, marking one read in place with an optimistic update and a rollback, "Mark all as read", and the empty, loading and error states. The navigation entry sits where the registry test allows, under More on a phone.

**Owned paths:**

- `frontend/src/app/(tenant)/notifications/page.tsx`
- `frontend/src/features/collab/NotificationsScreen.tsx`, `NotificationBell.tsx` and their tests
- `frontend/src/features/collab/{api,hooks}.ts` (the inbox operations only)
- `frontend/src/components/shell/` (the bell's slot only)
- `frontend/src/shared/navigation/registry.ts` (its own entry only)
- `frontend/src/messages/collab/{en,sv}.json` (its own keys only)

**Done when:**

- The inbox renders every kind with its pill, in both themes, at 375 px and at desktop width.
- Marking read is optimistic and rolls back on a failure, with a test for each.
- The bell's dot appears with an unread row and disappears after "Mark all as read", without a page reload.
- A notification whose record the reader can no longer open still lists, and the link answers the not-found page rather than a blank one.
- The registry snapshot test is green and the shell's existing journeys are unchanged.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "@smoke"`

**Invariants:**

- Pills only through `Pill`; no string literals in JSX.
- An empty answer is 200 and renders the empty state, never an error.

### c10-fe-notifications-b: preferences, and COL-S2 on screen

**Requirements:** COL-02
**Scenarios:** COL-S2 `@e2e`
**Depends on:** `c10-fe-notifications-a`, `c10-notification-prefs`, `c10-e2e-seed-b`

Add the preferences block to `/notifications`: one switch per mutable kind (mentions, assignments, reminders, the weekly digest), saved through `PATCH /me`, with escalation shown as always on and one line saying why. The switches read `notificationPrefs` from `GET /me` and write the whole object back, so a half-saved state cannot exist.

Un-fixme COL-S2's journey in `collab.journey.spec.ts`: the seeded reminder, escalation and digest appear in the inbox in the reader's language, and the digest mail is visible in the E2E mail outbox with its Swedish subject for the Swedish-speaking member. COL-S13 stays an integration scenario: muting a kind and watching a mention not arrive needs two sign-ins and a third screen to produce the mention, and the rule it proves is `notify()`'s, not the screen's.

**Owned paths:**

- `frontend/src/features/collab/NotificationPreferences.tsx` and its test
- `frontend/src/features/collab/{api,hooks}.ts` (the preferences operation only)
- `frontend/src/messages/collab/{en,sv}.json` (its own keys only)
- `frontend/tests/e2e/collab.journey.spec.ts` (COL-S2's block only)
- `backend/apps/collab/app.md` (COL-02's status cell only)

**Done when:**

- COL-S2's journey is green against the real stack, signed in by passkey through the UI, with the mail read from the E2E outbox endpoint rather than mocked.
- The escalation line explains that the bank sets it, without restating an invariant or naming a requirement.
- A failed save restores the previous switch state and shows the error from its `code`.
- The block renders at 375 px in both themes.
- COL-S13's integration test is still green, and the switches it describes are the switches the screen shows.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "COL-S2"`

**Invariants:**

- Never mock an API in E2E; the backend being down means the tests fail.
- The client branches on `code`, never on `detail`.

### c10-fe-comments-panel-b: the panel on the case, change and obligation pages

**Requirements:** COL-01
**Scenarios:** COL-S1 `@e2e`
**Depends on:** `c10-fe-comments-panel-a`, `c10-fe-notifications-a`, `c10-e2e-seed-a`, `c9-fe-cases-feature`, `c9-case-contract`, `c5-fe-change-detail`, `c3-fe-obligation-versions`

Mount `CommentsPanel` on the **case page**, the change page and the obligation page, each with its own subject kind and id, and nothing else: no second composer, no per-page variant, no per-page string. The case page is the one COL-S1's journey walks ("Given a case and a contributor with comments.write"); `UI_Implementation_Plan.md` names only the change and obligation pages, which predates chunk 9's case page, and `c10-close` corrects the row.

Un-fixme COL-S1's journey: a contributor opens the case, comments mentioning Erik, the comment appears with its author and time, and Erik — signed in afterwards — finds the notification in the inbox with a link back to the case. Declare the expected errors where they happen with `apiGuard.allow`.

**Owned paths:**

- `frontend/src/features/cases/CaseScreen.tsx` (the panel mount only)
- `frontend/src/components/inventory/ObligationScreen.tsx` (the panel mount only)
- `frontend/src/features/watch/ChangeScreen.tsx` (the panel mount only)
- `frontend/tests/e2e/collab.journey.spec.ts` (COL-S1's block only)
- `backend/apps/collab/app.md` (COL-01's status cell only)

**Done when:**

- COL-S1's journey is green against the real stack, across two sign-ins, with no injected token and no mocked response.
- The three mounts differ only in the subject they pass; a test asserts the same component is used on all three.
- No page's budget regresses: the panel loads after the record, in parallel with nothing else it blocks.
- All three pages render the panel at 375 px in both themes.
- VOC-S6's journey, which walks the same obligation page, is still green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "COL-S1|VOC-S6"`

**Invariants:**

- Sign in through the UI with a passkey; never mock an API response.
- Every spec imports `test` from `tests/e2e/support/api-guard`; an expected error is declared where it happens.

### c10-j8-extension: J-8 gains comments and notifications

**Requirements:** NFR-01, TEN-06, COL-01
**Scenarios:** TEN-S7 `@e2e` (extended)
**Depends on:** `c10-e2e-seed-a`, `c10-fe-comments-panel-b`, `c9-fe-evidence-panel`, `c9-e2e-seed`, `c8-support-access-mechanism`

Extend TEN-S7, the J-8 journey, with what chunks 9 and 10 added, in its existing test block: tenant B's compliance officer opens tenant A's case URL, its evidence URL and a comment's deep link and gets the not-found page each time, never a 403 and never the data; B's own notification inbox holds nothing about A; B's My work comments panel lists none of A's comments; and B's search, if chunk 7's screen is reachable from the seed, returns none of A's text.

Update TEN-S7's Gherkin in `tenants/app.md` to name the surfaces that now exist, and nothing that does not.

**Owned paths:**

- `frontend/tests/e2e/tenants.journey.spec.ts` (TEN-S7's block only)
- `backend/apps/tenants/app.md` (TEN-S7's Gherkin and TEN-06's status cell only)

**Done when:**

- TEN-S7 is green as `@smoke` with the new steps, and the journey still runs inside the smoke budget.
- Every cross-tenant answer is 404 in status and "Not found" on screen; a 403 anywhere in the journey fails it.
- The journey reads only seeded data and mocks nothing.
- The scenario text in `app.md` matches the test step for step.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run test:e2e -- --grep "TEN-S7"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Two zones, and a tenant never sees another tenant's row: 404, never 403.
- Never mock an API in E2E.

### c10-security-review: the chunk-wide sweep

**Requirements:** NFR-04 (the chunk's share)
**Scenarios:** none
**Depends on:** `c10-fe-notifications-b`, `c10-fe-comments-panel-b`, `c10-fe-workflow-policy`, `c10-fe-bulk-tagging-b`, `c10-delegation`, `c10-j8-extension`, `f03-T78b`, `f03-T80b`, `c10-digest-b`

A security-review sub-agent reads the whole chunk 10 diff on `main` (`git diff <chunk 10 base>..main` limited to the chunk's paths) and answers, with evidence:
- **Tenant content.** Can a comment body, a mention list, a case note or an assessment reach a log line, a Sentry event or breadcrumb, an `extra` key, an audit `before` or `after`, an outbox payload, a webhook body, a `notification.title`, a mail subject, a mail body or a URL? Plant a distinctive string in a comment and grep every one of those sinks. Is the widened compliance lint actually failing on a plant, and is its pattern case-insensitive?
- **The recipient check.** Is there exactly one? Does every kind go through it, including the ones chunks 9, 11 and 13 will add? Can a deactivated member, a member of another tenant, a member who lost a read permission, or a person outside the tenant receive a row or a mail? Does the delegation hop widen the check, and can it loop?
- **Tenancy.** Do `comment`, `comment_mention`, `comment_revision`, `notification` and `email_message` sit under forced RLS with no bypass? Does the append-only trigger on `comment_revision` refuse an update and a delete? Does every beat fan-out activate exactly one tenant, and can a task started for tenant A read tenant B under any failure path? Does `tests_tenant_isolation` cover each table?
- **Permissions.** Is every chunk 10 route either decorated or carried by an `UNGATED_BY_DESIGN` entry whose reason and note still hold, with no entry naming a route that no longer exists? Does the subject registry's read check match the route's, so a comment cannot be read on a record the reader may not open? Can a partial permission on `PATCH /tenant` write the other half's fields? Does a permission-filtered field ever turn into a page-level 403, or a 403 into a silent empty page?
- **The library fence.** Does tagging, the tag filter or `f03-T78c`'s call in `library/apply.py` write a library row? Is `tests_library_fence` unchanged and green?
- **Mail.** Can an unconfirmed AI draft, a case note, a comment or another tenant's row enter a reminder, an escalation or a digest? Does the outbox hold a mail for a deactivated member, for a member without the record's read permission, or twice for the same event? Is every mail host on the reviewed list (D-54)?
- **Audit.** Does every write have a `record()` row in the same transaction, and no read write one? Does any audit row carry tenant content after `f03-T80a`'s lint change?
- **Simplicity.** Is anything here speculative or overbuilt? Name it for the fix package to cut.

Run the guard suites with it: `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`.

**Owned paths:**

- `docs/security/CHUNK10_REVIEW_2026-09-20.md` (new)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- The report names every finding with a severity, the file and line, and the fix it asks for.
- A critical or high finding blocks the chunk close and is listed for `c10-review-fixes`.
- Findings below high become rows in `HARDENING.md` with the package that will fix them.
- The planted-string sweep is recorded in the report with the command and its output for every sink.
- The six guard suites are green on `main`, and the report says so with the command output.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_rls apps.shared.tests_tenant_isolation apps.shared.tests_library_fence apps.shared.tests_route_permissions apps.shared.tests_audit_on_write apps.shared.tests_four_eyes --settings=config.test_settings --noinput`

**Invariants:**

- The review lowers nothing and fixes nothing; it reports.
- A finding is evidence, not opinion: each carries the code that proves it.

### c10-review-fixes: close the review's findings

**Requirements:** NFR-04 (the chunk's share)
**Scenarios:** the chunk's scenarios stay green
**Depends on:** `c10-security-review`
**Security review:** yes (re-run on its own diff)

Fix every critical, high and medium finding of `c10-security-review`, test first, then re-run the review over this task's diff and repeat until nothing at medium or above remains. If the review found nothing at medium or above, close at once with a note in `HARDENING.md` and no code change.

Owned paths are the files the findings name, and nothing else; a finding that needs a file another task owns waits for that task or becomes its own package (parallel plan rule 9).

**Done when:**

- No critical, high or medium finding is open.
- Every chunk 10 scenario that was green is still green, and no test was weakened to get there.
- Findings below medium are rows in `HARDENING.md` with a package named.
- The re-run review is appended to `docs/security/CHUNK10_REVIEW_2026-09-20.md`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run build`

**Invariants:**

- No gate lowered, no test skipped or quarantined, no API mocked in E2E.
- A guard, audit row, permission check or validation is never simplified away.

### c10-close: the chunk closes

**Requirements:** COL-01, COL-02, VOC-03, VOC-08, HOM-05 (its comments half)
**Scenarios:** every chunk 10 scenario green; the deferred ones named
**Depends on:** `c10-review-fixes`, `f03-T79`, `f03-T80b`, `f03-T81`, `c10-j8-extension`, `c10-fe-bulk-tagging-b`, `c10-fe-workflow-policy`

Close the chunk on `main` (playbook Section 3):
- Run `bash scripts/prepush.sh --all` and the full `npm run test:e2e`.
- Prove no chunk 10 route answers 501 and no chunk 10 journey is fixme, by enumerating the eight collab operations, the four tagging operations and the six chunk 10 journeys (COL-S1, COL-S2, COL-S12, VOC-S6, VOC-S12, TEN-S7).
- Prove `backend/scripts/contract_drift_pending.txt` holds no chunk 10 line.
- Add the chunk 10 coverage floors to `backend/scripts/coverage_gate.py`, measured at this close, each with its measured value, statement count and date, and restate the header's measurement note.
- Update `backend/apps/collab/app.md`: COL-01 and COL-02 `built`, COL-04 `built` for its notification side with chunks 8 and 9 named for the routes, COL-03 `pending` with chunk 13 named, and the "deliberately simplified" paragraph rewritten to what is now true (no private notes, D-60; following is R3). Update `backend/apps/taxonomy/app.md` (VOC-03 and VOC-08 `built`), `backend/apps/home/app.md` (HOM-05's comments half) and `backend/apps/tenants/app.md` (TEN-04's reminder half).
- Update `docs/plans/IMPLEMENTATION_STATUS.md`: chunk 10 implemented and tested with today's date, `in progress` until a person verifies it, and a notes cell naming what was cut and why (COL-03, the `proposal_waiting` and `saved_search_hit` kinds, webhook delivery of notifications, comment retention).
- Update `docs/plans/UI_Implementation_Plan.md`'s chunk 10 rows: the comments panel and the notifications screen from "card pending" to `built`; the panel's surfaces named as the case page, the change page, the obligation page and My work, not two of them; `GET /comments` gated by the subject's read permission rather than by `comments.write` alone; and the workflow fields moved from `admin-organisation.html` to the new `/admin/workflow` section (ruling 8). Re-run the reachability audit for the chunk: every chunk 10 mutation has a screen that calls it, the batch tagging routes included.
- Write the open points into `docs/TODO_FOR_alex.md`: q-comment-subjects as it was taken, and the four non-blocking confirmations of the Open questions section.
- Add the `Verification_Log.md` row for any provider fact the chunk relied on (there should be none: nothing in chunk 10 calls an outside service that chunk 6 did not already log).

**Owned paths:**

- `backend/apps/collab/app.md`, `backend/apps/taxonomy/app.md`, `backend/apps/home/app.md`, `backend/apps/tenants/app.md` (status cells and notes only)
- `docs/plans/IMPLEMENTATION_STATUS.md`
- `docs/plans/UI_Implementation_Plan.md` (the chunk 10 rows only)
- `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md` (its own rows only)
- `backend/scripts/coverage_gate.py` (the chunk 10 floors only)

**Done when:**

- `bash scripts/prepush.sh --all` is green on the close commit.
- The full E2E suite is green against the real stack, `@smoke` included.
- No chunk 10 route answers 501, no chunk 10 journey is fixme, and no chunk 10 line is left in `contract_drift_pending.txt`.
- COL-S4 is still skipped and fixme with chunk 13 named, and the requirements-coverage gate is green.
- The status files, the UI plan rows and the four app.md files say what is on `main`, not what was intended.
- The coverage floors are raised to the measured values and none is lowered.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `bash scripts/prepush.sh --all`
- `cd frontend && npm run test:e2e`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Status is the truth of `git log`, not intention: a row moves only when its commit is on `main`.
- No gate lowered to close a chunk; a cut is named, never hidden.
- The owner deploys; an agent never does.

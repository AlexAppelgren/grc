# Security review: chunk 10, collaboration (2026-09-27)

Package `security-review-c10`, wave 6 of the R2 build. Requirements COL-01, COL-02 and
VOC-08.

## Question

Do chunk 10's surfaces hold the product invariants of CLAUDE.md section 5 and of
`R2_CROSS_CUTTING.md` (m)? The surfaces are:

- comments and mentions;
- the inbox;
- `notify()` and its delegation hop;
- the reminder, escalation and digest jobs and their mails;
- the participation and linked-change producers;
- participants;
- out of office and the notification switches;
- the workflow policy;
- bulk tagging and the obligation tag filters;
- My work.

The invariants in question:

- two zones under forced row-level security;
- one recipient check;
- a delegation hop that cannot loop or grant;
- no bank text in any sink;
- every route gated or reviewed as ungated;
- the library fence;
- reviewed mail hosts.

## Standard

The earlier chunk reviews' standard: OWASP ASVS 5.0.0, chapters V4 (API), V8
(authorization), V14 (data protection) and V16 (logging). It is read against:

- CLAUDE.md section 5;
- playbook 4.2, 4.3 and 4.7;
- `docs/plans/briefs/CHUNK10_TASKS.md`, `c10-security-review` (every question that task
  asks is answered below);
- this package's acceptance line.

## Method

1. **Built the reviewed tree.** Branch `claude/r2w6-security-review-c10` is `origin/main`
   with the seven dependency branches merged:
   - `c10-digest-beat-and-journeys`
   - `c10-producers`
   - `c10-fe-prefs-and-ooo`
   - `c10-fe-bulk-tagging`
   - `c10-fe-workflow-policy`
   - `c8-ui-mywork`
   - `x-briefing-mail`

   The merge resolutions are their own commits. Three tests that read older shapes were
   brought onto the merged code in `18cb837a`.
2. **Read the production code**, every file under:
   - `backend/apps/collab/`;
   - `cases/signoff.py`, `cases/triage.py` and `cases/logic.transition`;
   - `tenants/out_of_office.py` and the workflow policy route in `tenants/api.py`;
   - `taxonomy/tagging_logic.py` and its routes;
   - the tag filters in `library/reading.py`;
   - `home/my_work.py`, `home/tasks.py` and `home/mail.py`.

   Then the pieces they lean on:
   - `shared/tenancy.py`, `shared/outbox.py` and `shared/audit.py`;
   - `shared/logging.py` and `shared/sentry_scrub.py`;
   - `shared/adapters/mailer.py`;
   - `config/settings.py` (logging, Celery and the production-safety block);
   - `config/celery.py`;
   - the installed Celery and sentry-sdk sources for what a failed task logs and sends.
3. **Traced three paths by hand:**
   - every writer of `notification` and `email_message`;
   - every `record()` in chunk 10 with its `before`, `after` and `subject_title`;
   - every beat entry down to the transaction and the zone its work runs in.
4. **Planted one string** in everything a bank types about a case, then ran the comment
   route and the three jobs, and read every sink
   (`apps/collab/tests_review_c10.py::APlantedStringReachesNoSink`, below).
5. **Ran the guards and gates** listed at the end.

## Verdict per area

| Area | Verdict | Evidence |
|---|---|---|
| Tenant content in any sink | **Holds** in the chunk's code, proved by the sweep below. Two gaps were found and fixed: Celery's failure line (M2), and the lint's coverage (L1, open). | `tests_review_c10.APlantedStringReachesNoSink`, `collab.tests_scenarios.test_col_s5`, `tests_digest` (its planted string), `tests_review_c10.AFailedTaskLogsNoText`. |
| One recipient check | **Holds.** `collab/logic.py` `notify()` holds the only `Notification` write in production code, and an AST guard fails on any other. `_readers` admits only active members of the bank, with an active account, whose roles hold the subject's read permission; the record is looked up under RLS. Every producer calls it: mentions, participation, involved-item changes, the three reminders, escalation, assignment and the sign-off request. `email_message` is written only by `collab/tasks.deliver_mail` and `home/tasks`, each behind its own recipient gate. | `shared/tests_hardening.NotifyIsTheOneWriterOfANotification`, `collab/tests_notify.py`, `collab/tests_delegation.py`. |
| The subject registry matches each record's own read | **Holds.** `obligation` takes `library.read`, `tenant_obligation` takes `register.read`, and `change_case` and `action` take `cases.read`, as the record's own routes demand. Another bank's record and a record the reader may not open both answer the same 404. | `collab/subjects.py` `SUBJECTS`, `collab/tests_comments.py`. |
| The delegation hop cannot loop or grant | **Holds, one fix.** It is one hop only: a chain stops at the first delegate and a cycle ends. The delegate passes the same recipient check, or the absent person keeps the notice. Mentions are never delegated. A delegate gains nothing: approving still needs their own `cases.signoff`, the step-up and the four-eyes CHECK. **Did not hold:** a delegate who *caused* the notice received it on the absent person's behalf, because no production caller named the mover (M1, fixed). | `collab/tests_delegation.py` (`OneHop`, `NothingIsGranted`), `tests_review_c10.TheMoverIsNeverTheDelegate`. |
| Forced RLS on the chunk's tables | **Holds.** `comment`, `comment_mention`, `comment_revision`, `notification`, `email_message` and `participant` each run `rls_operations`: RLS enabled and forced, one FOR ALL tenant policy, the same WITH CHECK. Every person column and every comment reference is a composite `(tenant_id, …)` key. All six are in `TENANT_ONLY_TABLES`, and `db_role_guard` refuses a BYPASSRLS role at boot. | `collab/migrations/0001`, `0002_participant`, `shared/tests_rls.py`. |
| The append-only trigger | **Holds where the data is a ledger.** `comment_revision` carries `cw_append_only_guard` and is pinned in `APPEND_ONLY_TRIGGERS`. Of the other five tables, `comment`, `notification`, `email_message` and `participant` are rightly updated in place (an edit and soft delete, `read_at`, the send status, `removed_at`). `comment_mention` is insert-only in code and could take the trigger (I3). The acceptance line's "the append-only trigger on the five tables" reads as forced RLS on the tables plus the trigger on the revision ledger. | `collab/migrations/0001` `append_only_trigger_operations("comment_revision")`, `shared/tests_append_only.py`. |
| Per-tenant fan-out | **Holds for the beat.** `send_reminders` and `send_digests` (collab) and `send_weekly_briefings` (home) only enqueue. Each bank's work is its own `@tenant_task`, one transaction with exactly that bank active, so a failure rolls back that bank alone. The one synchronous nesting, the outbox producer's per-bank calls, leaves the database setting on the last bank after the loop (L2, latent). | `collab/tasks.py`, `home/tasks.py`, `collab/producers.py` `_fan_out`. |
| Route gates and `UNGATED_BY_DESIGN` | **Holds.** Every chunk 10 route is decorated or carries its entry, and each entry's reason still holds against the code. The self routes act on the caller's own rows only: the three inbox routes, `GET /me/comments`, and `GET` and `PUT /me/out-of-office`. The logic-gated routes check in logic: `GET` and `POST /comments`, both participant removals and `GET /me/work`. No entry names a dead route; the guard fails on one. Tenant isolation now also covers `DELETE /comments/{id}` and `POST /notifications/{id}/read` (L7, fixed). | `shared/tests_route_permissions.py`, `shared/tests_tenant_isolation.py`, `shared/routes.py`. |
| The workflow policy route | **Holds.** `PATCH /tenant/workflow` carries `@requires_permission(workflow.manage)` and a session only. There is no step-up, which PRD section 6 and the CLAUDE.md step-up list do not ask for. `PATCH /tenant` (`security.manage`) has no workflow field, so one half's permission cannot write the other half's fields. | `tenants/api.py` `update_tenant_workflow`, `tenants/schemas.py` `TenantPatch`, `TenantWorkflowPatch`. |
| The library fence | **Holds.** `LIBRARY_WRITE_ALLOWLIST`, the allowed directories and the route maps gained nothing in chunk 10. `Tagging` and `TenantTag` are tenant tables. The `tenantTag` filter resolves keys within the caller's bank only, and another bank's key answers the same `unknown_key` as a key nobody has. The producers read `TenantObligation`, `Participant` and `TeamMember` and write only notifications. | `shared/tests_library_fence.py` (green, unchanged by chunk 10), `library/reading.py` tag filters, `collab/producers.py`. |
| Mail content | **Holds.** `MailContext` has five fields: a record title, a date, a count, a person's name and a product link that must start with `APP_BASE_URL`. A comment, a note or an assessment has nowhere to go. Reminder and escalation titles are the change's library title, never the action's typed one. The digest is recomposed in the worker from the member's own permissions. The briefing carries a "So what?" only once a person confirmed it. | `collab/mail.py`, `collab/reminders.py`, `collab/escalation.py`, `collab/digest.py`, `home/tasks.py`. |
| Mail recipients and duplicates | **Holds.** A mail goes only to someone `notify()` admitted or, for the digest and briefing, an active member composed for themselves. The worker re-checks the member is active before sending. It does not re-check the read permission (L4). `email_message`'s unique `(tenant, user, template, subject_type, subject_id, sent_on)`, with nulls not distinct, plus the row lock, stops a second send the same day (the same week for the digest). | `collab/tasks.deliver_mail`, `collab/models.py` constraint, `collab/tests_mail.py`. |
| Mail hosts (D-54) | **Does not hold yet, and not by chunk 10.** `MAIL_SMTP_HOST` is any value the environment gives, with no reviewed list in code. The guard is planned as `c14-eu-data-location` (R3). Chunk 10 adds no host or mail path; it uses the chunk 1 mailer. It is, however, the first chunk that mails every member regularly (L5). | `config/settings.py` mail block and production-safety block, `shared/adapters/mailer.py`, `docs/plans/PARALLEL_PLAN.md` (`c14-eu-data-location`). |
| Audit | **Holds.** Every chunk 10 write has its `record()` row in the same transaction, and no read writes one. Each `after` carries only ids, keys, dates and counts: `commentId`, `mentionUserIds`, `revisionId`, the participant ids, the mail's template, status, user id and date, and the escalation's dates and counts. Each title is the record's own library title, or the mail template's key. | `shared/tests_audit_on_write.py`, `shared/tests_hardening.py` (the reviewed `record()` calls), the sweep. |
| Sentry | **Holds.** `send_default_pii=False`, `max_request_body_size="never"` and `include_local_variables=False`. The Celery integration therefore replaces task arguments with a placeholder. Exception values, request data, query strings and the content keys in `extra`, contexts and breadcrumbs are redacted. | `config/settings.py` Sentry block, `shared/sentry_scrub.py`, sentry-sdk `integrations/celery/__init__.py`. |
| URLs | **Holds.** `GET /comments` carries only `subjectType`, `subjectId`, `limit` and `offset`, and a comment's text rides only in a body. The mention picker filters `/reference/people` on the client, so no typed text reaches a query. Inbox and My work hrefs carry ids only. Mail links are built from `APP_BASE_URL` and ids. | `collab/schemas.py` `CollabCommentQuery`, `frontend/src/features/collab/`, the sweep's mail bodies. |
| Simplicity | Nothing speculative or overbuilt was found for a fix package to cut. | |

## The planted-string sweep

`apps/collab/tests_review_c10.py::APlantedStringReachesNoSink` plants
`planted-c10-5d9a` in:

- the body of a comment that mentions a reader;
- the titles of three actions: one due at the bank's first reminder lead, one due
  yesterday and one past the escalation threshold;
- a `case_transition` note;
- both texts of the impact assessment;
- the case's unconfirmed "So what?" draft;
- a register entry's status note and applicability reason.

It posts the comment through the route, runs `send_tenant_reminders`,
`send_tenant_escalations` and `send_tenant_digests` for the bank, and requires all four
collab mails (`due_soon`, `overdue`, `escalation`, `weekly_digest`) to have gone out, so
the sweep read something. It then reads each sink:

| Sink | Read from | Result |
|---|---|---|
| log | every line on the root, `apps`, `django` and `celery` loggers, written by the production `JsonFormatter` | absent |
| Sentry | `sentry_scrub.before_send` over every log line as an event | absent |
| audit | every `audit_event` row's summary, subject title, `before` and `after` | absent |
| outbox | every `outbox_event` payload | absent |
| notification title | every `notification.title` (the mention included) | absent |
| mail row | every `email_message` subject and address | absent |
| mail and URL | every sent mail's subject and body, its links included | absent |

The command and its output:

```
$ cd backend && ./run.sh run python manage.py test apps.collab.tests_review_c10 --settings=config.test_settings --noinput
Ran 5 tests in 4.730s
OK
```

`collab.tests_scenarios.test_col_s5` already swept the comment routes alone (log, audit,
outbox, notification, Sentry). It also proves the compliance lint fails on a planted
`logger.info(..., extra={"body": comment.body})`. The lint compares a key's last word
lowercased, so `Body` and `NOTE` are caught; what it misses is L1.

## Findings

Severity is critical, high, medium, low or info. Status is fixed, open (with where it gets
fixed) or accepted.

| # | Sev. | Where | Finding | Status |
|---|---|---|---|---|
| M1 | medium | `apps/cases/signoff.py` `request_signoff`, `apps/cases/triage.py` `triage_change` | `notify()` skips a delegate who caused the notice (`actor_id`), but neither move passed it. An approver away with the case's owner as delegate therefore had the owner's own sign-off request routed to the owner, stamped on the approver's behalf. The owner may not approve (the four-eyes CHECK), so the request reached nobody who could act on it (TEN-04, CAS-06). An assignment triaged by the new owner's delegate went back to the triager. | **Fixed** in `a1ff84c8`: both pass `actor_id=user.id`, so the away recipient keeps the notice. Tests, red before the fix: `tests_review_c10.TheMoverIsNeverTheDelegate` (two). |
| M2 | medium | `config/settings.py` Celery block, `apps/shared/logging.py` `JsonFormatter` | Celery's failure and retry lines interpolate the exception's repr into the message. They attach the formatted traceback and the task's arguments as `data`, and the worker replaced LOGGING's JSON handler with its own, whose tracebacks print messages. A database error's message carries the failing row, so a collab mail job failing on `email_message` would have logged the member's address and the mail's subject (playbook 4.7). | **Fixed** in `4aed5352`. `CELERY_WORKER_HIJACK_ROOT_LOGGER = False`, and the formatter writes a `celery.app.trace` line as the task, its id and what happened, with `[redacted]` for the exception and no `data`. Frames and exception types still come from `formatException`. Tests, red before the fix: `tests_review_c10.AFailedTaskLogsNoText` (two). |
| L1 | low | `backend/scripts/compliance_check.py` `RECORD_CONTENT`, the `record-content` and `log-content` rules | The lint reads literal key names only. It misses plural keys (`comments`, `notes`), a safe-sounding key holding content (`{"commentId": c.body}`), `after=payload`, `after=body.model_dump()`, `{**payload}` and `extra=ctx`. It also misses keys outside its seven (`content`, `description`, `message`, `interpretation`, `soWhat`), and never looks at `subject_title=`. No chunk 10 call does any of these (the sweep), so this is a future risk. | **Open**, HARDENING H74. |
| L2 | low | `apps/shared/tenancy.py` `tenant_task`, reached from `apps/collab/producers.py` `_fan_out` | Called in process inside the outbox batch, each `@tenant_task` is a savepoint. `activate()` is `SET LOCAL`, which a released savepoint keeps, and the wrapper restores only the Python context variable. After the loop, the database stays in the last bank's zone for the rest of the library event's handlers. Harmless today because collab's handler registers last, and each outbox step re-enters its own zone. | **Open**, HARDENING H75. |
| L3 | low | `apps/identity/models.py` `Membership.delegate`, `apps/tenants/out_of_office.py` | "Not yourself, same bank, active" is enforced in logic only, with no CHECK; the seed writes the column directly. A delegate who is away is accepted, so A→B with B away leaves A's work with an absent person, and A↔B passes each other's work while both are away. Nothing widens: `notify()` re-checks every delegate and ignores a self-delegate. | **Open**, HARDENING H76. |
| L4 | low | `apps/collab/tasks.py` `deliver_mail` | The worker re-checks that the member and their account are active before sending, but not the subject's read permission. A member whose role lost `cases.read` between the commit and the send still gets that one reminder. It holds a library title, a date and a link. | **Open**, HARDENING H77. |
| L5 | low (for this chunk) | `config/settings.py` mail block, production-safety block | D-54's reviewed list of mail hosts is not enforced: `MAIL_SMTP_HOST` can name any relay in a deployed environment. It predates chunk 10 and is planned for `c14-eu-data-location` (R3). Chunk 10 is the first chunk that mails every member regularly, with names, addresses and record titles. | **Open**, HARDENING H78 and `docs/TODO_FOR_alex.md` (security-review-c10). |
| L6 | low | `config/settings.py` `APP_BASE_URL` | No boot check: a deployed environment can mail `http://` or `localhost` links. `MailContext` pins links to the value, whatever it is. | **Open**, HARDENING H79. |
| L7 | low | `apps/shared/routes.py` `TENANT_SCOPED_ROUTES` | `DELETE /comments/{commentId}` and `POST /notifications/{notificationId}/read` were proved against another bank only in the app's own tests, not in the tenant-isolation guard. | **Fixed** in `02af0783`: both registered, with a `comment` and a `notification` factory (the latter through `notify()`). |
| L8 | low | `apps/collab/api.py` `list_comments` | The published description named `register.read` for the inventory's records. An obligation of the library takes `library.read`, and `register.read` applies to the bank's own register entry. | **Fixed** in `02af0783`. |
| I1 | info | `apps/collab/digest.py`, `apps/home/my_work.py` (an internal item's `title=item.name`) | The digest mails a bank-typed record title, an internal item's name, which `collab/mail.py` allows ("a bank's own action, case or register entry") and CHUNK10_TASKS finding 4 sanctions. `collab/subjects.py` says its titles are "never text a person typed", and reminders deliberately use the change's library title over an action's. Consistent within each module, but two readings of one rule. | **Accepted**, the owner's to confirm (`docs/TODO_FOR_alex.md`, security-review-c10). |
| I2 | info | `apps/taxonomy/tenant_lists_logic.py` | A tenant tag's key is a slug of its typed label, and keys are what audit rows carry, so a label survives in the trail as its slug. Keys are the designed audit currency. | **Accepted.** |
| I3 | info | `apps/collab/migrations/0001` | `comment_mention` is insert-only in code but carries no append-only trigger. Nothing updates it; a trigger would make that a database fact. | **Accepted**, noted for the next collab migration. |
| I4 | info | `apps/collab/me_comments.py` | `total` counts the rows before those whose record lookup returns nothing are dropped, so it can overstate the page's total. It is the same bank's rows under RLS. | **Accepted.** |
| I5 | info | `apps/collab/reminders.py` `link`, `apps/collab/subjects.py` | A case or action mail links to `watch/{changeId}`, which needs `watch.read`, while the recipient check is `cases.read`. Both belong to every system role, so only a custom role without `watch.read` meets a dead link. The delegate check at `notify()` time is the read permission, not `cases.signoff`; that one is checked when the absence is set. | **Accepted.** |

## Gates run

- **Backend.** `apps.shared` in full on the merged tree (529 tests, OK). `apps.collab`,
  `apps.home`, `apps.cases`, `apps.taxonomy`, `apps.identity`, `apps.tenants`,
  `apps.register`, `apps.library` and `apps.watch`: red only on the three merge leftovers,
  which are fixed and re-run green. After the fixes, the six guard suites the chunk 10 brief
  names, with `tests_append_only` added:

  ```
  $ cd backend && ./run.sh run python manage.py test apps.shared.tests_rls apps.shared.tests_tenant_isolation \
      apps.shared.tests_library_fence apps.shared.tests_route_permissions apps.shared.tests_audit_on_write \
      apps.shared.tests_four_eyes apps.shared.tests_append_only --settings=config.test_settings --noinput
  Ran 68 tests in 24.567s
  OK
  ```
- **The whole backend suite** after the fixes: `manage.py test apps --parallel 4`, 3033
  tests, OK (87 skipped as pending scenarios).
- **Frontend.** lint, typecheck, `vitest run` (149 files, 1473 tests), `check:messages`
  and `check:copy-drift`, all green.
- **E2E** for the journeys the merged collaboration code and the two fixes touch: COL-S1,
  COL-S2, COL-S6, COL-S7, COL-S12, TEN-S4, HOM-S7, HOM-S9, HOM-S13 (J-9) and VOC-S12 all
  pass. VOC-S12 first failed on the pending register-entry read, which it now declares like
  the other obligation-page journeys. CAS-S2 and CAS-S10 are still `test.fixme` on this
  tree.
- **Static checks.** ruff; mypy; `compliance_check.py --all`; `requirements_coverage.py`;
  `api_docs_gate.py`; `contract_drift.py`.
- **Migrations.** `makemigrations --check` answers "No changes detected", and
  `migrate_from_zero` applies the whole graph.

# collab — Collaboration

> **App spec.** Source: `PRD.md` Module COL (COL-01–COL-03), playbook 4.7 (tenant
> content never in logs), 12 (business-time schedules per tenant timezone), 17.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

Assessments need input from legal, product and technology. Comments and
mentions work on any record, notifications reach people in their own
language, reminders go out before due dates, escalation fires after a
threshold, and a weekly digest summarises. All of it runs in the worker on
the tenant's timezone. A comment is tenant content: it never reaches a log.

Deliberately simplified: the whole app is R2 (chunk 10); following a record
is R3.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| COL-01 | Comments and mentions on any record | S | R2 | pending |
| COL-02 | Notifications, reminders before due dates, escalation after a threshold, a weekly digest in the user's language | M | R2 | pending |
| COL-03 | Follow a record | C | R3 | pending |

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this module. The criteria below are
the PRD rows and the playbook rules read as tests:

- A comment belongs to a subject (`subject_type` kind plus id), is under RLS,
  and a mention notifies the mentioned member.
- Reminder lead time and escalation threshold are tenant settings with
  platform defaults; both are computed in the tenant's timezone and delivered
  through the mailer adapter in the recipient's language.
- The digest is one email per user per week with their open items.
- The compliance lint fails on any log line that includes comment text.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/collab.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### COL-S1 — A comment with a mention notifies the mentioned person `@integration` `@e2e` (COL-01)
```gherkin
Given a case and a contributor with comments.write
When they comment "@Erik can you check the custody angle?"
Then the comment is stored against the case with the subject kind and id
And Erik receives a notification linking to the case
And the comment is visible only inside the tenant
```

### COL-S2 — Reminders, escalation and the digest reach people in their language `@integration` `@e2e` (COL-02)
```gherkin
Given an action due in three days owned by a Swedish-speaking owner and a tenant reminder lead of three days
When the reminder job runs
Then the owner receives one reminder in sv
When the action is five days overdue and the escalation threshold is five days
Then the owner's manager and the compliance officer are notified
When the weekly digest job runs
Then each user receives one digest in their language listing their open items
```

### COL-S3 — Schedules run in the tenant's timezone `@integration` (COL-02)
```gherkin
Given a tenant in Europe/Helsinki and a digest scheduled for Monday 08:00
When the worker's beat fires in UTC
Then the digest is sent at 08:00 Helsinki time, across a daylight saving change too
And the fixture anchors to the tenant-local date, never to "now plus hours"
```

### COL-S4 — A user follows a record and hears about changes `@integration` `@e2e` (COL-03)
```gherkin
Given a user follows an obligation
When a new version is applied to it
Then the user is notified
When they unfollow it
Then the next change sends nothing
```

### COL-S5 — Comment text never reaches a log `@integration` (COL-01)
```gherkin
Given a comment is created, edited and deleted
When the application log for those requests is read
Then it holds the comment id and the actor id and never the text
And the compliance lint fails on a log call that passes a comment body
```

# collab — Collaboration

> **App spec.** Source: `PRD.md` Module COL (COL-01–COL-04, AC-COL1, J-9), playbook 4.7 (tenant
> content never in logs), 12 (business-time schedules per tenant timezone), 17.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

Assessments need input from legal, product and technology. Comments and
mentions work on any record, notifications reach people in their own
language, reminders go out before due dates, escalation fires after a
threshold, and a weekly digest summarises. All of it runs in the worker on
the tenant's timezone. A comment is tenant content: it never reaches a log.

Participants are the other half of the same idea: a person or a team named on
a register entry or a case so that it reaches their My work and their
notifications. Participation grants nothing, and a participant can leave. A
notification reaches only active members whose roles can read the record, once
per event, whatever the number of reasons.

Deliberately simplified: the whole app is R2 (participants with the register in
chunk 8 and with cases in chunk 9, comments and notifications in chunk 10);
following a record is R3; participant roles are not built (D-18). Private notes
are not built and will not be: Alex confirmed on 2026-09-19 that notes on My
work are the shared comments in the "Comments and mentions" panel, whose
composer says that everyone in the organisation can read them (D-22, D-60,
ADR 0028).

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| COL-01 | Comments and mentions on any record, and a person's own comments and mentions on My work, limited to records they can read. These shared comments are the notes on My work; there are no private notes (D-60) | S | R2 | pending |
| COL-02 | Notifications, reminders before due dates including next reviews, notice when a change is linked to an involved obligation or a new version applies, escalation to the head of the owner's department, a weekly digest in the user's language, once per person per event | M | R2 | in_progress |
| COL-03 | Follow a record | C | R3 | pending |
| COL-04 | Participants: people or teams added to a register entry or a case by someone who can edit it; participation lists and notifies, grants no access, and a participant can leave | M | R2 | pending |

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
- **AC-COL1** A participant still receives 403 on writes their role lacks.
  Tenant B adding a participant to tenant A's private record, or removing A's
  participant, gets 404; on a shared record, B's add lands on B's own entry. A
  user of another tenant gets 422 `unknown_member`, and a member who cannot
  read the record gets 422 `participant_cannot_read`. A record holds at most
  `MAX_PARTICIPANTS_PER_RECORD` participants.

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
Then the head of the department of the owner's team and the compliance officer are notified
When the weekly digest job runs
Then each user receives one digest in their language listing their open items as My work counts them
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
And a person who both follows the obligation and takes part in it receives one notification
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

### COL-S6 — A person or a team is added to a register entry, audited, and gains no access `@integration` `@e2e` (COL-04, AC-COL1)
```gherkin
Given Anna holds register.edit and an obligation has no register entry yet
When she adds Erik and the team "Legal" as participants
Then the register entry is created with one audit event "register.entry_created" in the same transaction
And two participant rows exist, each naming who added them, each with one audit event "participant.added" holding ids only
And Erik's permissions are unchanged: saving the register entry still answers 403
When Anna adds Erik again
Then the answer is 409 with code "already_participant"
Given Erik holds cases.contribute but not register.edit
When he adds a participant to an obligation
Then the answer is 403 with requiredPermission "register.edit"
```

### COL-S7 — A participant leaves a register entry on their own `@integration` `@e2e` (COL-04)
```gherkin
Given Erik, a Reader, takes part in an obligation
When he chooses "Leave"
Then his participation ends with its removal time and remover recorded, and the audit event is "participant.left"
And the obligation's history still shows that Erik took part until he left
When Erik tries to remove another participant
Then the answer is 403
```

### COL-S8 — Register-entry participant routes refuse other tenants, strangers and people who cannot read `@integration` (COL-04, AC-COL1, NFR-01, AC-NFR1)
```gherkin
Given an obligation private to tenant A and a shared obligation
When tenant B's owner adds a participant to A's private obligation
Then the answer is 404
When they add one to the shared obligation
Then it lands on tenant B's own register entry and tenant A's participant list is unchanged
When they remove tenant A's participant by its id
Then the answer is 404 and the row is unchanged
When tenant A's owner adds a user who is a member only of tenant B
Then the answer is 422 with code "unknown_member", the same answer as for an unknown id or a deactivated member
When they add a team key of tenant B
Then the answer is 422 with code "unknown_key"
When they add a member whose roles lack register.read
Then the answer is 422 with code "participant_cannot_read"
When a register entry already holds the configured maximum of participants
Then the next add answers 422 with code "too_many_participants"
And the database refuses a participant row whose user, team or register entry belongs to another tenant
```

### COL-S9 — Case participants are managed by those who contribute, and refused across tenants `@integration` `@e2e` (COL-04, AC-COL1, NFR-01)
```gherkin
Given Erik holds cases.contribute but not register.edit
When he adds Anna to a case
Then the answer is 201
When he removes Johan from the case
Then the answer is 204 and the audit event is "participant.removed"
Given a Reader who takes part in a case
When they choose "Leave"
Then the audit event is "participant.left"
When a participant is added to a closed case
Then the answer is 409 with code "invalid_transition"
Given a change private to tenant A
When tenant B adds a participant to it
Then the answer is 404
Given a shared change
When tenant B adds a participant to it
Then it lands on tenant B's own case and tenant A's list is unchanged
When tenant B removes tenant A's case participant by its id
Then the answer is 404
```

### COL-S10 — Participation, confirmed links and new versions notify the people involved, once, if they can read `@integration` (COL-02, COL-04)
```gherkin
Given Anna owns an obligation and Erik takes part in it
And the team "Legal" with members Anna, Karin, Lisa and Johan takes part in it
And Lisa's role lacks register.read and Johan is deactivated
When Erik is added to a case
Then Erik receives one "participant_added" notification linking to the case
When a person confirms a link from a change to the obligation
Then Anna, Erik and Karin each receive one "involved_item_changed" notification, Anna once although she is involved twice
And the person who confirmed it, Lisa and Johan receive none
When a new version of the obligation is applied
Then the same people are notified once each, in their own language
And no notification title or email carries tenant text, only the library title and a link
```

### COL-S11 — Review reminders reach the people responsible, once `@integration` (COL-02)
```gherkin
Given a tenant reminder lead of 30 days
And Anna is first-line owner of a "Compliant" obligation whose next review is in 30 days
And Erik owns that obligation's row for Fund AB, whose own next review is in 30 days
And the team "Legal" owns a register entry whose next review is in 30 days
When the reminder job runs
Then Anna and Erik each receive one "review_due" reminder in their language, and each active member of "Legal" receives one
When the job runs again the same day
Then nobody is reminded twice
```

### COL-S12 — My comments and mentions are found on My work, limited to what I can read, and never logged `@integration` `@e2e` (COL-01, HOM-05)
```gherkin
Given Anna commented on two obligations and Erik mentioned Anna on a case
When Anna opens "Comments and mentions" on My work
Then "Mentions" lists Erik's comment with a link to the case
And "My comments" lists her two comments, newest first, in pages
And the composer says that everyone in the organisation can read comments
Given Johan's role lacks cases.read and he is mentioned on a case
When Johan reads his mentions
Then no case comment is returned, cases are listed as permission-limited, and he received no notification for the mention
When Johan comments on an obligation Anna owns
Then it appears on Anna's My work under "Changes on your items" for the awareness window
And the application log, the audit after value and the outbox payload for these requests hold ids and never the comment text
```

### COL-S13 — Notification preferences mute a kind for one person, never an escalation `@integration` (COL-02)
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

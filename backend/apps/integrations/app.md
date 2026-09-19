# integrations — Webhooks, tickets and SIEM

> **App spec.** Source: `PRD.md` Module INT (INT-01–INT-03), playbook 4.3 (idempotent
> webhook handlers), 15 (webhooks store keys), 18 (audit streaming).
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

An existing GRC system, ticket tool or SIEM must be able to follow what
happens here. Every write already leaves an outbox event in the same
transaction, so integrations deliver from the outbox: signed webhooks with a
delivery log and retries, ticket export for actions, and an audit log stream
to the customer's SIEM. Nothing is delivered that was not committed, and
nothing is delivered twice as a new event.

Deliberately simplified: the whole app is R3 (chunk 13). Ticket export is a
Could.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| INT-01 | Signed webhooks with a delivery log, from a transactional outbox | S | R3 | pending |
| INT-02 | Ticket export for actions | C | R3 | pending |
| INT-03 | Audit log stream to the customer's SIEM | S | R3 | pending |

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this module. The criteria below are
the PRD rows and the playbook rules read as tests:

- A webhook subscription needs `integrations.manage`, stores event keys, a
  URL and a signing secret shown once; each delivery is signed, logged with
  status and attempts, and retried with backoff (settings).
- Delivery is from `outbox_event` in order per subject, after commit only.
- Ticket export produces one ticket per action through a `ticket_provider`
  kind, idempotent on the action id.
- The SIEM stream sends audit events in a documented format, with delivery
  lag visible in system health.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/integrations.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### INT-S1 — A signed webhook is delivered from the outbox with a delivery log `@integration` `@e2e` (INT-01)
```gherkin
Given an admin with integrations.manage created a subscription for "case.closed" with a secret shown once
When a case is closed
Then the outbox event is picked up after commit and delivered with a signature over the body
And the delivery log shows the attempt, the status and the response time
When the endpoint answers 500
Then the delivery is retried with backoff and the log shows each attempt
```

### INT-S2 — Webhook delivery and inbound handlers are idempotent `@integration` (INT-01)
```gherkin
Given an outbox event delivered once
When the worker is restarted mid-batch
Then the event is not delivered as a new event and the receiver can dedupe on the event id
When an inbound callback arrives twice
Then the handler applies it once
```

### INT-S3 — Actions export as tickets `@integration` `@e2e` (INT-02)
```gherkin
Given a case with three actions and a ticket provider configured
When the owner chooses "Send as tickets"
Then one ticket per action is created through the provider kind and the ticket reference is stored on the action
When they choose it again
Then no duplicate tickets are created
When a ticket closes at the provider
Then the action status flows back
```

### INT-S4 — Audit events stream to the customer's SIEM `@integration` `@e2e` (INT-03)
```gherkin
Given a tenant configured a SIEM endpoint
When audit events are written
Then they are streamed in order in the documented format
And system health shows the stream's lag
And the stream carries record ids and summaries, never evidence content
```

### INT-S5 — Subscriptions store keys so a rename changes nothing `@integration` (INT-01)
```gherkin
Given a subscription filtered on the change type key "amendment"
When the admin renames the label to "Amending act"
Then the subscription still matches and its stored filter is unchanged
```

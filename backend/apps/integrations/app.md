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

PRD 0.5 (ACC-05, ADR 0055) adds the MCP server, which is how a bank's own agents
reach everything above. It is **one router over the endpoints that already
exist**: the same authentication classes, the same `@requires_scope` gates, the
same logic modules and the same pagination, with no read path of its own, so a
bank that prefers the REST API directly gets identical guarantees. Its tool list
follows the credential. Through R2 every agent access credential is read-only and
a mutating route answers 403 `read_only_credential`. `tools/call` (acc-mcp-tools) runs the
REST route behind each of the six tools as a request of its own, so the structured content
is that route's body and a refusal is a tool error keeping the route's problem code. The calls are bounded like
any other: pagination as everywhere, a rate limit per credential, and model calls
counted against the tenant's monthly budget cap and stopped by its AI off switch.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| INT-01 | Signed webhooks with a delivery log, from a transactional outbox | S | R3 | pending |
| INT-02 | Ticket export for actions | C | R3 | pending |
| INT-03 | Audit log stream to the customer's SIEM | S | R3 | pending |
| ACC-05 | An MCP server over the same API: same authentication, same scope gates, same logic, same pagination, no read path of its own. Its tool list follows the credential, and every agent access credential is read-only through R2 | M | R2 | built |
| ACC-09 | Limits: pagination as everywhere, a rate limit per credential, and model calls counted against the tenant's monthly budget cap and stopped by its AI off switch | M | R2 | in_progress |

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

### ACC-S7 — The MCP server is one router over the same gates, and every credential is read-only `@integration` (ACC-05, AC-ACC4)
```gherkin
Given an agent access credential and the MCP server
When it lists tools
Then the list holds only the tools its scopes reach, and a credential without tenant:read is offered no register tool
When it calls a tool
Then the request passes the same authentication class and the same scope gate as the REST route behind it, and returns the same body
When it calls any mutating route, by MCP or directly
Then the request answers 403 "read_only_credential"
And no scope an agent access credential may hold writes anything
```

### ACC-S8 — Pagination, the rate limit, the budget cap and the AI off switch bound every call `@integration` (ACC-09)
```gherkin
Given an entry whose scope holds 250 obligations
When it lists them without a page size
Then 20 are returned, and a page size of 500 is refused with the maximum named
When it exceeds the per-credential rate limit
Then the request answers 429 and the security log records it
When the tenant's monthly budget cap is reached
Then a what-applies call returns its list with no summary and the reason says the cap
When the tenant's AI off switch is on
Then no model call is made for that tenant and the list is still returned
```

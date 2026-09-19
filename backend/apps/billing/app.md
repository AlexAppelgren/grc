# billing — Plans, limits and usage

> **App spec.** Source: `PRD.md` NFR-05, playbook 4.3 (money only here, as an integer
> minor unit), 16 (cadence within plan limits, budget caps).
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.
>
> Scenario IDs continue the `NFR` sequence from `shared/app.md` (NFR-S1 to
> NFR-S16), so they stay unique across the repository.

## 1. Business / user context

A plan states what a tenant may use: members, agents and their cadence, the
monthly AI budget, storage. Usage is metered so the platform admin can see
it and the tenant can see where it stands. Money appears only here, as an
integer minor unit with a currency code, never as a float and never anywhere
else in the product. There is no self-service checkout: contracts are signed
with banks, and a plan is assigned from the console.

Deliberately simplified: the whole app is R3 and a Could (chunk 14).

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| NFR-05 | Billing: plans, limits, usage | C | R3 | pending |

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this requirement. The criteria below
are the PRD row and the playbook rules read as tests:

- A plan is a platform row with limits (members, agents, cadence floor, AI
  budget, storage) and a price as an integer minor unit plus currency.
- A tenant's limits are read from its plan everywhere a limit is enforced
  (`above_plan_limit`).
- Usage is metered per tenant per month from facts that already exist (runs,
  `ai_generation` cost, storage) and shown to both the tenant and the platform.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/billing.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### NFR-S17 — A plan holds limits and a price as an integer minor unit `@integration` `@e2e` (NFR-05)
```gherkin
Given a platform admin with tenants.manage
When they create the plan "Nordic" with 50 members, 3 agents, a weekly cadence floor, a monthly AI budget and a price of 250000 SEK minor units
Then the plan row stores each limit and the price as an integer with the currency code
And a price sent as a decimal answers 422
```

### NFR-S18 — Plan limits are enforced where the tenant acts `@integration` (NFR-05)
```gherkin
Given a tenant on a plan with 3 agents and a weekly cadence floor
When an admin switches on a fourth agent or sets a daily cadence
Then the request answers 422 with code "above_plan_limit"
When the platform admin moves the tenant to a larger plan
Then the same request succeeds without a deploy
```

### NFR-S19 — Usage is metered and visible to the tenant and the platform `@integration` `@e2e` (NFR-05)
```gherkin
Given a month of runs, model calls and evidence uploads
When the tenant admin opens the usage screen
Then it shows runs, "Spend this month" against the cap, and storage against the limit
When the platform admin opens tenants and plans
Then the same figures appear per tenant and no money value is a float anywhere in the API
```

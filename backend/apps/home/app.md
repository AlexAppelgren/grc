# home — Home, briefing and roadmap

> **App spec.** Source: `PRD.md` Module HOM (HOM-01–HOM-04), `design/README.md`
> (the chosen direction), playbook 6.7 (roadmap pills), 6.8 (mobile actions).
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

Home is a timeline: the next dates as the same short list on a phone and on
a desktop, the lead item, what needs a decision, where the bank stands, and
whether the sources are healthy. Part of the weekly briefing is shown on it
and the full briefing is one tap away, snapshotted when it is emailed. The
full calendar lives on its own roadmap page by quarter, where a card expands
in place. Upcoming changes are public facts, so they feed agents and
newsletters, and a revocable calendar feed lets a user subscribe.

Everything on these screens respects the footprint (FP-03) and reads keys and
counts from the API; every phrase is built in a presentation function.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| HOM-01 | Timeline home: next dates as a short list on every screen size, the lead item, what needs a decision, compliance standing, source health | M | R1 | pending |
| HOM-02 | Weekly briefing, reachable from home with part of it shown there, snapshotted when emailed | M | R1 | pending |
| HOM-03 | Roadmap page by quarter, regulatory dates and our own deadlines, a card expanding in place | M | R1 | pending |
| HOM-04 | Upcoming changes as public facts for agents and newsletters, and a revocable calendar feed | S | R1 | pending |

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this module. The criteria below are
the PRD rows and the design read as tests:

- The home list is the same items on a 375 px viewport and a desktop; the
  lead item carries the `brand` pill "Lead".
- The briefing is snapshotted (content, date, footprint at the time) when the
  email goes out, so what was sent can be reopened unchanged.
- A roadmap item shows urgency or "Our deadline" as its pill, then the date and
  days left as text; expanding a card does not navigate.
- The calendar feed is a per-user token URL; revoking it makes the URL answer
  404; the feed carries public facts only, never tenant notes.
- Every screen renders within the 500 ms budget on real data and has empty,
  loading, error and denied states.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/home.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### HOM-S1 — Today shows the next dates, the lead item, decisions, standing and source health `@integration` `@e2e` (HOM-01)
```gherkin
Given the seeded tenant with open changes, cases and deadlines
When a user opens Today
Then the "Coming up" list shows the next dates in order with urgency pills
And the lead change carries the brand pill "Lead"
And "Where we stand" shows the compliance standing counts and "Source coverage" shows source health
And the API answered from one fan-out of independent calls, none chained
```

### HOM-S2 — The same short list appears on a phone `@e2e` (HOM-01)
```gherkin
Given Today on a 375 px viewport
Then the "Coming up" list holds the same items as on desktop
And two action buttons share one row with the primary on the right
```

### HOM-S3 — The weekly briefing is reachable from home and snapshotted when emailed `@integration` `@e2e` (HOM-02)
```gherkin
Given Today shows "This week in brief" with the first items
When the user chooses "Read the briefing"
Then the full briefing opens, filtered by the footprint
When the weekly email job runs
Then a briefing snapshot is stored with its date and the email links to the snapshot
And a later change to the feed does not alter the snapshot
```

### HOM-S4 — The roadmap shows quarters with regulatory dates and our own deadlines `@integration` `@e2e` (HOM-03)
```gherkin
Given regulatory dates and case deadlines across two quarters
When the user opens the roadmap
Then each quarter lists its items, regulatory dates with an urgency pill and our deadlines with "Our deadline"
When they tap a card
Then it expands in place with the change summary and the next step, without navigating
```

### HOM-S5 — Upcoming changes are public facts and the calendar feed is revocable `@integration` `@e2e` (HOM-04)
```gherkin
Given an agent key and a user
When the agent reads /upcoming
Then it gets library facts with dates and keys and nothing tenant-specific
When the user chooses "Subscribe to calendar feed"
Then a token URL serves an ICS of their roadmap
When they revoke it
Then the URL answers 404
```

### HOM-S6 — A roadmap item's pill is the urgency or "Our deadline" `@e2e` (HOM-03)
```gherkin
Given a regulatory date with urgency "6+ months" and a case deadline
When the roadmap renders them
Then the first shows "6+ months" as a notice pill and the second shows "Our deadline" as brand, each followed by the date and days left as text
```

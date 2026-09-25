# home — Home, briefing and roadmap

> **App spec.** Source: `PRD.md` Module HOM (HOM-01–HOM-05, AC-HOM1, AC-TEN1, J-9),
> `design/README.md`
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

My work is the person's own page: everything they or their teams are
responsible for or take part in, with the next reviews and the changes on
those items, and the same view for the head of a department. It is about
attention, not access: every row and every count is filtered by the reader's
own permissions, and the department view is a filter, never a grant.
Decisions stay on Today.

Everything on these screens respects the footprint (FP-03) and reads keys and
counts from the API; every phrase is built in a presentation function. My work
is the one exception: a person never loses sight of their own items because of
a regulatory scope change (D-24).

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| HOM-01 | Timeline home: next dates as a short list on every screen size, the lead item, what needs a decision, compliance standing, source health. R1 built every part but compliance standing, which `c8-home-standing-roadmap` added with the register | M | R1 | built |
| HOM-02 | Weekly briefing, reachable from home with part of it shown there, snapshotted when emailed | M | R1 | built |
| HOM-03 | Roadmap page by quarter, regulatory dates and our own deadlines, a card expanding in place; from R2 a certificate's expiry and next audit are our deadlines and never reach the calendar feed. R1 built the regulatory branch; `c8-home-standing-roadmap` added next reviews, gap targets and certificates (HOM-S15); the case workflow's deadlines and actions join in chunk 9 | M | R1 | in_progress |
| HOM-04 | Upcoming changes as public facts for agents and newsletters, and a revocable calendar feed | S | R1 | built |
| HOM-05 | My work: what a person or their teams are responsible for or take part in, as overdue, due soon, changes on those items and the rest, with next reviews and a department head's view; permission-filtered rows and counts; the footprint never hides a person's own items | M | R2 | pending |

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
- **AC-HOM1** An owner's compliant obligation with a review in 20 days is under
  "Due soon"; an item they own outside the footprint is listed; a role without
  `register.read` gets no obligation rows or counts and a permission-limited
  notice, never a page-level 403.
- **AC-TEN1** A certificate's expiry and next audit appear on the roadmap as
  "Our deadline" with its owner, disappear once it is withdrawn, and never
  appear in the calendar feed.
- Every screen renders within the 500 ms budget on real data and has empty,
  loading, error and denied states.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/home.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### HOM-S1 — Today shows the next dates, the lead item, what needs a decision and source health `@integration` `@e2e` (HOM-01)
```gherkin
Given the seeded tenant with open changes and cases
When a user opens Today
Then the "Coming up" list shows the next dates in order with urgency pills
And the lead change carries the brand pill "Lead"
And "Decide now" shows the queue counts the reader's own permissions unlock
And "Source coverage" shows how many sources were checked and which ones failed
And a reader without watch.read gets the page with no lead and no source panel, never a 403
And the API answered from one fan-out of independent calls, none chained
```
Where the bank stands is the note below.

> **Note — where we stand on Today** (`c8-home-standing-roadmap`). `standing` on `GET /home`
> counts the obligations inside the regulatory scope that apply, to the bank or to one of its
> legal entities, each once in the worst category of the entities it applies to (the rule
> behind the obligation's pill), and the gaps that are open or being remediated. It is null for
> a reader without `register.read`, never a 403. A standard's one conformance obligation counts
> once however many entities follow it. What needs a decision is the `counts` object on
> `GET /me` (D-23), so one number has one source. The screen's panel is a UI package's.

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

### HOM-S4 — The roadmap shows the quarters ahead with their regulatory dates `@integration` `@e2e` (HOM-03, FP-03)
```gherkin
Given regulatory dates across two quarters, one of them outside our regulatory scope
When the user opens the roadmap
Then each quarter lists its dates in order, each with its urgency pill
And the date outside our regulatory scope is absent
When they tap a card
Then it expands in place with the change summary and the next step, without navigating
```
Our own deadlines with the "Our deadline" pill are the note below.

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

### HOM-S6 — A regulatory date on the roadmap wears its urgency as a pill `@e2e` (HOM-03)
```gherkin
Given a regulatory date with urgency "6+ months"
When the roadmap renders it
Then it shows "6+ months" as a notice pill, followed by the date and days left as text
```
The "Our deadline" half is the note below; `roadmap-presentation.test.ts` already pins
that pill's tone, so the rule is proved before a branch produces a row for it.

> **Note — our own deadlines on the roadmap.** A roadmap item is either a date the outside
> world set or one this bank set for itself. `c8-home-standing-roadmap` built four internal
> branches, each with its owner and its record, proved in `tests_roadmap.py`: next reviews of
> register entries and entity rows, compliant ones included, and targets of open or
> remediating gaps, both inside the regulatory scope and only for a reader holding
> `register.read`; and a certificate's expiry and next audit, left out once withdrawn (D-43,
> AC-TEN1, HOM-S15). None reaches the calendar feed. The case workflow's internal deadlines
> and actions are chunk 9's, so HOM-03 stays `in_progress`.

### HOM-S7 — My work lists what I'm responsible for or take part in, most urgent first `@integration` `@e2e` (HOM-05, AC-HOM1)
```gherkin
Given Anna is first-line owner of an obligation whose next review was 12 days ago
And she owns a gap with a target date in 9 days
And she owns the internal item "Complaints procedure" with a next review in 40 days
And her team "Retail compliance" takes part in an obligation with no date
And she owns an obligation marked as not applying
When Anna opens My work
Then "Overdue" lists the review and "Due soon" lists the gap
And "Everything you're responsible for" lists the internal item and the obligation her team takes part in, with the reason "Your team takes part"
And the obligation that does not apply is absent
And each item appears once, in its most urgent section
And the response carries keys, kinds, dates and record names, never a phrase
And the page links to Today for decisions waiting for her
```

### HOM-S8 — Compliant and per-entity reviews reach My work `@integration` (HOM-05, AC-HOM1)
```gherkin
Given an obligation marked "Compliant" for Bank AB with a next review in 20 days, whose first-line owner is Anna
And a second obligation whose first-line owner is Johan and whose row for Fund AB has its own next review 3 days ago, owned by Erik
When Anna's work is read
Then the compliant obligation is under "Due soon"
When Erik's work is read
Then the second obligation is under "Overdue", dated by the Fund AB review, with the reason "You're responsible"
When Johan's work is read
Then the second obligation is under "Overdue" too
```

### HOM-S9 — A department head sees the department's work, naming who is responsible `@integration` `@e2e` (HOM-05, TEN-02, TEN-03)
```gherkin
Given Karin heads the department "Retail Banking"
And the team "Retail compliance" with Anna and Johan belongs to it
And the team "Cards" with Erik belongs to "Cards and payments", a unit under "Retail Banking"
And "Retail compliance" owns one obligation, Anna owns another, and Erik takes part in a third
When Karin opens My work
Then it opens on "Retail Banking" and lists all three items, each naming the team or the person responsible
When Johan opens the "Retail Banking" view
Then he sees the same items, because the department view is a filter and grants nothing
When Erik is deactivated
Then the department view no longer expands to Erik
```

### HOM-S10 — My work applies each record's read permission to rows and counts, and ignores the footprint `@integration` (HOM-05, AC-HOM1)
```gherkin
Given Erik was added as a participant to an obligation while his role held register.read
And an admin then removed register.read from that role
When Erik opens My work
Then no obligation row is returned and every count excludes it
And the response lists obligations as permission-limited, and the page says so instead of "Nothing to do"
And his participation still exists
Given Anna owns an obligation scoped to "Advice" and the regulatory scope excludes "Advice"
When Anna opens My work
Then the obligation is listed like any other
```

### HOM-S11 — Changes on your items are confirmed links and new versions only `@integration` (HOM-05)
```gherkin
Given Anna owns an obligation
And an agent suggested a link from a new change to it that no person has confirmed
When Anna opens My work
Then the change is not under "Changes on your items"
When a compliance officer confirms the link
Then the change's open case is listed there, naming Anna's obligation
When a new version of the obligation is applied
Then it is listed there until 14 days have passed
And nothing Anna did herself is listed there
```

### HOM-S12 — My work answers within budget for a fifty-member department `@integration` (HOM-05, NFR-02)
```gherkin
Given a department of fifty members across its teams, with seeded obligations, entity rows, internal items, gaps, duties and participants
When the department view of My work is read
Then it runs the same number of queries whatever the number of items
And it answers within 250 ms
```

### HOM-S13 — J-9: Monday morning `@e2e` (HOM-05, COL-04, TEN-03, J-9)
```gherkin
Given the seeded owner Anna, contributor Erik and department head Karin
When Anna opens My work
Then she sees her overdue review, and under "Changes on your items" a change linked to an obligation she is responsible for
When she opens that obligation and adds Erik as a participant
Then Erik's My work lists the obligation with the reason "You take part"
And Karin's department view lists it with Anna named as responsible
When Erik chooses "Leave"
Then the obligation leaves Erik's My work and the audit log holds both events
```

### HOM-S14 — Case work reaches My work `@integration` (HOM-05)
```gherkin
Given Anna owns an action that was due yesterday on an open case
And Anna owns a case whose change came into force last month and that has no open dates
And Erik owns only one action, due in 40 days, on a case whose internal deadline is tomorrow
And the team "Legal" takes part in a case
When their work is read
Then Anna's action is under "Overdue" and her case is under "Everything you're responsible for", not "Overdue"
And Erik's item for that case is dated by his action
And each member of "Legal" sees the case with the reason "Your team takes part"
And the query count pinned by HOM-S12 is unchanged
```

### HOM-S15 — A certificate's expiry and next audit are our deadlines, never in the calendar feed `@integration` `@e2e` (HOM-03, HOM-04, TEN-02, AC-TEN1)
```gherkin
Given Example Bank AB's licence "ISO/IEC 27001:2022 certificate" valid until 2028-11-30, with the next audit on 2027-03-15 and an owner
When the roadmap for Q1 2027 is read
Then the audit appears as "Our deadline" with that owner, naming the certificate and the entity
When the roadmap for Q4 2028 is read
Then the certificate's expiry appears as "Our deadline"
And the user's calendar feed contains neither item
When the licence is withdrawn
Then neither date appears on the roadmap
```

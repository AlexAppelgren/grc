# Agent access: the agents a bank runs itself

> **Planning brief.** Written 2026-09-20 from Alex's answers in chat. It carries the
> design for PRD module **ACC** (ACC-01 to ACC-10), decisions **D-70 to D-73, D-76
> and D-77** and ADRs **0055, 0056 and 0057**. The PRD wins on any conflict; this
> file is the detail an implementing agent needs and the PRD does not carry.

## 1. What this is

A bank runs agents of its own, on its own infrastructure, and they need to know
which regulation applies to what they are building, planning or reviewing. A
coding agent designing an order-routing service. A product agent shaping a new
account type. A procurement agent reading a supplier contract. An internal
assistant answering a staff question. None of them should have to ask a
compliance officer to paste an export.

So the bank registers each one as an **agent access entry**, gives it a
credential, and narrows what it may see. The agent then reads Compliance Watch
through an MCP server or the REST API underneath it.

The point of the narrowing is Alex's own example: an agent building in the
trading domain has no business reading card regulation, and an agent that can
read everything is an agent whose blast radius is the whole compliance register.

### It is not the agents we run

The product already has two kinds of agent, and this is a third thing that
must never be confused with them.

| | Agents (AGT-03, AGT-04) | Agent access (ACC) |
|---|---|---|
| Who runs it | bleqq, or the bank through our scheduler | The bank, on its own infrastructure |
| Where it runs | Our worker, through the `agent_runner` adapter | Anywhere the bank puts it; we never see it |
| What it does | Finds, classifies and **writes**: changes, proposals, findings | **Reads**, and nothing else through R2 |
| What we hold | Its definition, prompt, cadence, budget, run history | A name, a purpose, a scope and a credential |
| What governs it | Plan limits, budget caps, the AI off switch | The tenant reach switch, the scope, the credential |

The screen keeps them apart by saying so: **Agents** gains a second tab, and each
tab states in one line what that kind of agent does. The access tab says
read-only, in those words, because a reader who confuses the two will assume a
bank's coding agent can change the register.

## 2. The decisions this is built on

Alex answered these in chat on 2026-09-20. Each is a row in `docs/DECISIONS.md`.

1. **Both credential kinds, service key first** (D-77). A service key bound to
   an entry, and a personal access token that acts as a person.
2. **The bank's own register is the payload** (D-76). "The agent can access
   anything that the bank has put as it applies to them and any comments they
   provided per entry. The shared library is mainly a way for the bank to quicker
   provide which regulations that are applicable to them." The library is the
   substrate; the bank's decisions on it are the answer.
3. **Scope comes from departments and products** (D-70), which the bank already
   maintains under TEN-02. No second scope list to keep current.
4. **Chunk 11, R2** (D-73), beside the tenant agent work that already builds
   credentials, budgets and the Agents screen.
5. **A summary and the full list** (D-71). "I want both a short summary of what
   applies but also a full list of registries that applies."
6. **A tenant-wide switch plus per-entry toggles** (D-72) for letting tenant
   content leave the zone.
7. **Read-only to start.** Alex: "eventually I want a full map of all
   applications that touch each registry and how, but not in the first releases."
   That is ACC-10, R3, and the data model is shaped so it needs no migration of
   built columns when it lands.

## 3. The model

Three tables and two columns. Nothing else is new.

### `agent_access` (tenant table, forced RLS, `apps/agents`)

| Column | Notes |
|---|---|
| `id`, `tenant_id` | As every tenant table |
| `name` | What the bank calls it, for example "Trading platform coding agent" |
| `purpose` | Free text, one sentence, shown on the entry and in the access log |
| `owner_team_id` | FK `team` (TEN-03). Who answers for it. Null until chunk 8 lands teams |
| `tenant_reach` | Boolean, default false. The per-entry half of D-72 |
| `active` | Revoking an entry stops every credential under it on the next request |
| `created_by`, `created_at`, `version` | `version` for `If-Match`, as every versioned record |

`Meta.ordering = ["name", "id"]`.

### `agent_access_department` and `agent_access_product`

Join rows, `(agent_access, department)` and `(agent_access, product)`, each
unique. Naming none of either means no narrowing.

### Two columns on `api_key`

| Column | Notes |
|---|---|
| `kind` | `service` or `personal`. A kinds-only enum in code, per the vocabulary rule |
| `agent_access_id` | Nullable FK. The entry this credential reads as |

`api_key` already carries `tenant`, `agent`, `scopes`, `key_prefix`, `key_hash`,
`created_by`, `expires_at`, `revoked_at` and `last_used_at`. Nothing is
duplicated and no second credential table exists: one hashing path, one
revocation path, one security log.

## 4. The scope rule

The effective scope is computed at request time and never stored:

```
effective = tenant_footprint  ∩  terms_of(departments ∪ products)
```

Then a record is visible when it passes **both** the existing footprint rule and
the same rule again against the entry's terms. The second pass reuses
`apps/taxonomy/matching.py:in_footprint` with the entry's term map, and the SQL
list queries take a second term array beside the one they already pass to
`taxonomy_in_footprint`.

Three consequences worth stating, because each is a place an implementer will
guess wrong:

- **An empty dimension does not restrict**, exactly as FP-01 says. A trading
  entry whose products carry `product_type: {derivatives, securities}` sees every
  obligation carrying no product type at all, plus those two, and never one
  carrying only `cards`. This is why the rule needs no special case for a general
  assistant: name no department and no product, narrow nothing.
- **It can only narrow.** The intersection with the tenant footprint is taken on
  our side, from the footprint table, not from anything the caller sends. An entry
  can never widen what the bank itself sees, so FP-02's preview, second person and
  step-up stay the only way the bank's own scope grows.
- **Terms are derived, not copied.** A product's terms are read at request time,
  so an entry stays true as the bank re-describes its products. A run does not
  snapshot them (unlike AGT-04's market scope, which does, because a run is a
  record of what was checked and this is a read).

## 5. What it reads

### Always, with `library:read`, `search:read` and `upcoming:read`

The library records in scope: instruments, obligations, provisions, versions with
an "as of" read, provenance and the source link. Upcoming dated changes that
touch them. Every hit carries its citation, its "as of" date and its provenance
label, so an unconfirmed AI draft never reaches an agent as settled fact.

### With tenant reach on and `tenant:read`

The bank's register decisions on those obligations: applicability and its reason
per legal entity, compliance status and status note, how we read this rule
(REG-04), owner, process, system, next review, and the linked internal items of
REG-05.

`tenant:read` is already declared in `apps/shared/permissions.py` and gated on no
route. This gives it its meaning rather than adding a ninth scope.

### Never, in R2

Gaps, cases and their assessments, comments and mentions, evidence of any kind
including its metadata, the audit log, other tenants' anything, and a tenant's
private records (D-57: a private record is never sent to a model, and a bank's
own agent is a model).

`tenant:read` is a read of **decisions**, not of work in progress. A gap or an
open case is the bank arguing with itself, and it is not what an agent building a
service needs in order to build it right.

## 6. What it answers

Six tools on the MCP server, each one call to an endpoint that already exists or
is planned. The server adds no read path of its own: same auth classes, same
`@requires_scope`, same logic modules, same pagination.

| Tool | Endpoint behind it | Chunk that built it |
|---|---|---|
| `search` | `GET /search` | 7 |
| `list_obligations` | `GET /obligations` | 3 |
| `get_obligation` | `GET /obligations/{stableKey}` | 3 |
| `list_upcoming_changes` | `GET /upcoming` | 6 |
| `list_register_entries` | `GET /register` | 8 |
| `what_applies` | `POST /agent-access/what-applies` | 11, new |

### `what_applies`, the one that earns the feature

It takes a description of what is being built, bought or reviewed, and returns
two things in one response:

1. **A short summary**, drafted by our model, carrying the AI-drafted label and
   logged per AUD-02 with model, version, purpose and citations. It never reads as
   a verdict: the fixed sentence says it is guidance and that the bank's own
   confirmed applicability is the decision.
2. **The full list**, deterministic, of the register entries and obligations in
   scope that match, ranked by the same relevance the summary used but **never
   truncated by it**. If the model fails, times out or the AI off switch is on,
   the list is still returned and the summary slot says so.

That ordering is the requirement. Alex asked for both, and the list is the part
that must be right.

## 7. The safety property

A narrowed agent that silently omits card rules from a payments feature is worse
than no agent at all, because a developer reads silence as "nothing applies". So:

- **Every answer states the scope it was answered in.** The entry's name, the
  departments and products it covers, and the "as of" date.
- **A narrowed answer names what it could not see.** `what_applies` compares the
  description against the **dimension and term labels of the full tenant
  footprint**, not against its records, and says so: "This looks like it touches
  Card issuing, which is outside this agent's scope. Ask compliance." No record
  crosses the line, no data leaks, and the dangerous failure stops being silent.
- **404, never a filtered 200, for a record outside scope.** Asking for a card
  obligation's stable key from a trading entry answers 404, the same answer
  another tenant gets, so scope cannot be probed by the shape of the error.

These three are ACC-07 and they are not a nice-to-have. A compliance product
whose false negatives are invisible is a liability, not a control.

## 8. Credentials

### Service key (`kind=service`)

Bound to an entry, acts as the entry, permissions are the key's scopes. Created
under `agent_access.manage` behind a step-up, shown once, hashed, default
expiry 90 days (`AGENT_ACCESS_KEY_MAX_DAYS`), revocable, `last_used_at` on
screen. For anything deployed, scheduled or running in CI.

### Personal access token (`kind=personal`)

Minted by a member holding the new permission `tokens.create`, from an
authenticated session, behind a passkey step-up. It **acts as that person**: the
audit log names the human, and its effective permissions are that person's
permissions intersected with the token's scopes and, where it names an entry,
that entry's scope.

It does not break "a passkey is the only way in", because the passkey is how the
person got in to mint it. That only holds if the token is fenced, and an
implementer will get this wrong unless every line below is built:

- A token **cannot open a UI session**. It authenticates API and MCP requests only.
- A token **cannot step up**, so every route carrying `@requires_step_up` answers
  403 `step_up_required` to it, always, with no path to an assertion.
- A token **expires** (default 90 days, `PERSONAL_TOKEN_MAX_DAYS`) and cannot be
  minted without an expiry.
- A token **dies with the person**: deactivating a member, removing their
  membership, or removing the permission a token's scope depends on revokes it,
  checked on every request rather than by a sweep.
- Every mint, use and revocation is a `LoginEvent` with its own method, so the
  security log (ID-11) shows it beside sign-ins and key use.
- The person sees their own tokens in their settings; an admin sees and revokes
  every token in the tenant.

`tokens.create` is granted by default to Admin, Compliance officer and Owner.
Not to Approver, Contributor, Reader or Auditor, and a bank may grant it to any
of them.

## 9. Governance

Two switches, because D-72 asks for both and they do different jobs.

**The tenant switch** lets the bank's own register leave the zone at all. It is
requested and approved by two different people holding `security.manage`, each
with a passkey, like tenant exit and for the same reason: it is an egress
decision about the bank's confidential judgement. Turning it off stops every
entry at once, immediately, which is the lever a security function will reach for
at three in the morning.

**The per-entry toggle** sits under `agent_access.manage` behind a step-up. With
the tenant switch off, every entry is library-only whatever its own toggle says,
and every register route answers 403 `tenant_reach_off`.

**The access log.** Every call records the credential, the entry, the person
where the credential is personal, the tool, the filters, the record count, the
scope applied and the timing. **Never the content**, never the question text, per
the logging rule. It is visible to the tenant on the entry, and it is what a
vendor review will ask to see.

**Limits.** Pagination as everywhere (default 20, max 100). A rate limit per
credential (`AGENT_ACCESS_RATE_PER_MINUTE`). `what_applies` model calls count
against the tenant's monthly budget cap and stop at the AI off switch, both of
which AGT-04 already builds.

## 10. What changes outside this feature

- **D-07 is amended** and needs its ADR (0057). It reads today: "No tenant-zone
  text is sent to a model except the question typed into Ask." Register decisions
  reaching a bank's own coding agent is tenant-zone text reaching a model. The
  distinction that makes it acceptable is that **we are not sending it, the bank
  is pulling its own data into its own agent**, over an authenticated channel it
  controls, after two of its own people approved it. That is a different act from
  us calling a provider with it, and D-07's EU-inference reasoning does not reach
  it. It still must be written down rather than reinterpreted quietly.
- **D-10** ("library only in R1, tenant content is not indexed") is untouched.
  Nothing here indexes or embeds tenant content. `what_applies` ranks in memory
  over rows the scope already selected.
- **REG-04 should be promoted** above the descope line in chunk 8. "How we read
  this rule" is the single field that turns a list of obligations into an answer a
  developer can build from, and it is currently a cuttable Should. This is a
  recommendation, not a change: D-26 made the order of a chunk's list the thing
  that protects work, so reordering chunk 8 is Alex's call. It is answered by
  default in `docs/TODO_FOR_alex.md`: chunk 8's order stands until he moves it.

## 11. Where the code goes

No new app.

| Piece | App |
|---|---|
| `AgentAccess`, its joins, the entry logic and routes | `apps/agents` |
| `api_key.kind`, `api_key.agent_access`, personal tokens, the token guards, the security log entries | `apps/identity` |
| The scope derivation beside the footprint matcher | `apps/taxonomy` |
| The register read for an agent access credential | `apps/register` |
| The MCP server router and its tool definitions | `apps/integrations` |
| The tenant reach switch and its four-eyes request | `apps/governance` |
| The Agents screen's second tab | `frontend/src/features/agents/` |

## 12. Dependencies

Chunk 11 is the right home and its inputs are already ordered:

| Needs | From | Chunk |
|---|---|---|
| Library reads with "as of" and provenance | `library` | 3 |
| Search | `search` | 7 |
| Departments, products, teams | `tenants` | 8 |
| The register and REG-04, REG-05 | `register` | 8 |
| Budget cap, AI off switch, the Agents screen | `agents` | 11 |

Nothing in ACC can start before chunk 8 lands, which is why it sits in 11 and
not earlier.

## 13. Test scenarios to write

Each becomes a Gherkin scenario in the owning app's `app.md`, `@integration` in
`tests_scenarios.py` and `@e2e` in `frontend/tests/e2e/agents.journey.spec.ts`.

1. An entry narrowed to Trading reads trading and untagged obligations, and
   answers 404 for a card obligation's stable key.
2. An entry naming no department and no product reads the whole tenant footprint
   and nothing beyond it.
3. Tenant B's credential cannot read tenant A's anything (the NFR-01 pattern,
   per route).
4. With the tenant switch off, every register route answers 403
   `tenant_reach_off` for an entry whose own toggle is on.
5. A personal token answers 403 `step_up_required` on every step-up route, and
   deactivating the person stops it on the next request.
6. Every mutating route answers 403 `read_only_credential` to every agent access
   credential.
7. `what_applies` returns the full list when the model call fails, and the
   summary slot says why.
8. A narrowed `what_applies` answer names the footprint dimensions it could not
   see when the description touches them.
9. Revoking an entry stops its keys and its tokens on the next request.
10. The access log records the call and holds no question text and no record
    content.

## 14. Answered by default, in `docs/TODO_FOR_alex.md`

Alex's answer of 2026-09-23, "Land the design now as decided", lands each of these on
the default below. Each stays his to overrule, and `docs/TODO_FOR_alex.md` lists them
with the three smaller ones (the `tokens.create` defaults, credential expiry and
where the tab lives).

- **Comments.** Alex's free text said "any comments they provided per entry";
  his answer on the reach question chose register decisions alone. The build reads
  that as: the structured notes on the entry are in (applicability reason, status
  note, how we read this rule), and COL-01 comment threads are out. Reversing it
  means adding `comments:read` and deciding what happens to mentions of people who
  never consented to a machine reading them.
- **REG-04's promotion** in chunk 8 (section 10). Default: chunk 8's order stands,
  so REG-04 stays a cuttable Should until Alex moves it.
- **Where a bank draws the line on its own model.** We say a bank pulling its own
  data into its own agent is the bank's decision. A bank running that agent on a
  model endpoint outside the EU is still that bank's decision, but the first
  procurement review will ask what we do about it. Default: we state it plainly
  in the assurance pack and record the tenant switch's approval, and we do not
  attempt to police the endpoint.
- **Whether an auditor's agent is a tenant entry or something else.** An external
  auditor reading the register through an agent during fieldwork fits this model
  exactly, but it is a third party inside the bank's tenant. Default: the bank
  registers it like any other entry, under the auditor's named engagement, and it
  ends when the engagement does: the bank revokes the entry, and its credentials
  expire in any case (section 3 gives an entry no expiry of its own). TEN-06's
  support access grants are the nearer pattern if that is wrong.

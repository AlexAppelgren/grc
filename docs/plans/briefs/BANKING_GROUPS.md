# Banking groups: one bank, several regulated companies

> **Planning brief.** Written 2026-09-25 by `r2-banking-groups-brief` (wave 2 of the R2
> build) against chunk 8's merged organisation tables (`apps/tenants/models.py`, tenants
> 0002) and the R1 footprint code. It is the planning pass D-69 asks for and carries the
> design of D-69 and the schedule in D-96. **Nothing here is built, and no code changed with
> it.** The PRD wins on any conflict. When Alex promotes the build, the PRD gains the
> requirement rows in section 12 and each app's `app.md` its scenarios from section 13.

## 1. What this is

Alex, 2026-09-22: "I need to be able to easily handle several companies that are part of a
group, like the SEB structure", and "there are users that will be cross several of the
entities, so they need easy access".

SEB is the worked example. SEB AB (a credit institution), SEB Fonder (a fund manager) and
SEB Liv (an insurer) sit in one banking group and one tenant, and each is regulated
differently. Today the tenant has one regulatory scope (the code calls it the footprint,
FP-01), so every entity sees every regime the group follows. The E2E seed will carry the
same shape from chunk 8 (`c8-seed-org-register`): Example Bank AB, Example Fonder AB and
Example Liv Försäkring AB under one group.

D-69 asks for two things, and they are different axes:

| | Per-entity narrowing | A membership's entity scope |
|---|---|---|
| The question | Which rules does this company face? | Which companies does this person work for? |
| Who it is about | A legal entity | A member |
| What it changes | What a view scoped to the entity shows | Where the member's permissions act |
| Its gate | FP-02: a request, a second person, a passkey (section 5) | `members.manage` with a passkey, like a role change (section 6) |
| Stored as | Exclusions per entity (section 4.2) | A kind and a join (section 6.2) |

A design that solves one without the other is not what a group compliance function needs,
which is why D-69 names both.

## 2. What this builds on

| Source | What it fixes for this design |
|---|---|
| D-69 | An entity only narrows the group's scope, never widens it. A member's access to entities is a separate axis: every entity, or a named subset |
| CLAUDE.md §5 | Four eyes and a passkey step-up on footprint changes; permissions, never role names; nothing overwritten; stable keys never change |
| D-89 | No agent manages a bank's regulatory scope, and scope changes keep four eyes |
| FP-01, D-36, STANDARDS §3.1 | The one scope rule; an empty dimension does not restrict; opt-in dimensions (standards) match only what the scope names and **gate at tenant level only** |
| STANDARDS §3.4, D-42, D-75, REG-01 | An entity follows a standard through its applicability on the conformance obligation, which is the only record that it follows it |
| `c8-reg-applicability` (wave 3) | Which entities an obligation spans: the legal-entity org units whose entity term matches the obligation's terms, opt-in dimensions left out |
| D-21 | A department's view is a filter, not a grant |
| D-70, `AGENT_ACCESS.md` | An agent access entry narrows by derived terms, computed per request, never stored; a record outside scope answers 404 |
| D-10, D-07, D-88 | Search is library only; nothing here indexes or sends tenant content anywhere |

## 3. What chunk 8 already gives

Chunk 8's tables are enough to attach both axes without changing a built column.

- **`OrgUnit`** (`apps/tenants/models.py`): `kind` is a tier-one kind with `legal_entity`;
  `entity_term` is a term of the `legal_entity` dimension (the entity's type: credit
  institution, fund manager, insurer), checked by the trigger `cw_org_unit_entity_term_guard`;
  `parent` makes the tree; `active` deactivates; `UNIQUE (tenant_id, id)` is the target of
  every composite key. The class docstring already says a membership's entity scope needs
  nothing more of this table.
- **The span** (`c8-reg-applicability`): an obligation carrying `legal_entity:
  credit_institution` spans SEB AB and not SEB Liv. A conformance obligation spans every
  entity. The span decides which per-entity rows an obligation offers; it narrows nothing
  in the inventory.
- **Per-entity rows**: `TenantObligationScope` (entry, org unit, optional product),
  `Gap.org_unit`, `SoaUnit` through its scope row, `DutyOccurrence.org_unit`, `Licence`.
  Each names its entity by a composite key.
- **`Membership`** (`apps/identity/models.py`): one row per person per tenant,
  `membership_tenant_user_unique (tenant, user)` as the target of a composite key.
  `TeamMember` joins it from chunk 8 (`c8-teams-model`).

**What the span already does, and what narrowing adds.** The span already keeps a
credit-institution rule off SEB Liv's rows, from the entity's type alone. Narrowing adds
everything else a company does not face that the group does: SEB Fonder operates in Sweden
only while the group's scope names four markets, or SEB Liv sells no card product while the
group does. Those are dimensions other than the entity's type, and only a narrowing can say
them.

## 4. Per-entity narrowing

### 4.1 The rule

An entity's scope is the group's scope with some terms taken out, and one thing added from
chunk 8: the entity's own type. For every restricting dimension `d` (`restricting_dimensions()`):

```
G(d) = the group's footprint terms in d, or every term of d when the group names none
S(d) = the entity's own type term when d = legal_entity and the entity has one, else every term of d
X(d) = the entity's excluded terms in d
E(d) = G(d) ∩ S(d) − X(d)
```

A record is in the entity's scope when, for every dimension it carries terms in, one of those
terms is in `E(d)`. A dimension where the group names nothing, the span says nothing and the
entity excludes nothing stays open, exactly as FP-01 says.

Three places an implementer will guess wrong, each with the reason:

- **Taking out the last term must not open the dimension.** Under FP-01 an empty dimension
  does not restrict. If SEB Fonder takes out both of the group's product types, a naive
  "footprint minus exclusions" map is empty in that dimension and admits every product,
  including the ones the group left out: a widening. So a dimension the entity narrows is
  **closed**: it admits only what `E(d)` names, also when `E(d)` is empty. It behaves the
  way an opt-in dimension already does (`Restricting.opt_in`, D-36), and the build reuses
  that mechanism rather than adding a second one.
- **One pass, not two.** `AGENT_ACCESS.md` §4 checks a record twice, against the footprint
  and against the entry's terms, and that is right for relevance: a record touching both
  cards and derivatives matters to a derivatives agent. It is wrong here. Group scope
  `{cards}`, SEB Fonder excludes `cards`, a record carries `{cards, mortgages}`: the group
  pass succeeds on `cards` and an exclusion pass succeeds on `mortgages`, yet nothing in the
  record is in Fonder's scope. The rule must meet one term in `E(d)`, the intersection, in a
  single check per dimension.
- **Opt-in dimensions are never narrowed per entity.** Whether an entity follows a standard
  is its applicability on the conformance obligation (STANDARDS §3.4). A standard term taken
  out per entity would be a second record that could disagree with it, outside the register.
  An exclusion in an opt-in dimension answers 422 `opt_in_not_narrowable`. A dimension whose
  `restricts_footprint` is false (theme, channel) narrows nothing, so an exclusion in it
  answers 422 `dimension_does_not_restrict` rather than being stored and ignored.

It can only narrow. `E(d) ⊆ G(d)` for every dimension by construction: the entity's terms
are the group's minus a list. Nothing the caller sends is added, and a term outside the
group's scope cannot be excluded (422 `term_outside_group_scope`) because there is nothing to
take out.

Consequences worth stating on screen and in the scenarios:

- **A record that carries no terms in a dimension reaches every entity**, as it reaches the
  group. Narrowing cannot hide a general rule from one company; applicability per entity
  (REG-01) is where a compliance person says a rule does not apply to it.
- **A term the group adds reaches every entity that has not excluded it.** An exclusion is
  kept when the group removes the term and returns to force if the group adds it back. That
  is why the store is exclusions and not a subset: a subset would leave a new group term off
  every entity until someone ticked it, a silent false negative.
- **One level.** Every entity narrows the group's scope directly. A subsidiary in the tree
  (SEB Fonder under SEB AB) does not inherit its parent's exclusions. The tree is ownership,
  not scope.
- **Nothing is deleted or re-decided.** A narrowing hides; a scope row, gap, unit or case on
  an obligation that leaves an entity's scope stays readable, as FP-02 treats a group
  removal (STANDARDS §3.4, REG-S4).

### 4.2 The model

One new tenant table and two nullable columns, in `apps/taxonomy` beside the footprint.

**`entity_scope_exclusion`** (tenant table, forced RLS)

| Column | Notes |
|---|---|
| `id`, `tenant_id` | As every tenant table |
| `org_unit_id` | Composite key `(tenant_id, org_unit_id)` to `org_unit`; the unit must be of kind `legal_entity`, checked by a trigger in the style of `cw_org_unit_entity_term_guard`, since a CHECK cannot read another table |
| `term_id` | FK `taxonomy_term`; a restricting, non-opt-in dimension, checked at write |
| `added_by`, `added_at`, `request_id` | As `footprint_term`, the request that approved it |

Unique `(org_unit, term)`. `Meta.ordering = ["added_at", "id"]`. Lifting an exclusion
removes the row exactly as FP-02 removes a `footprint_term` row; `footprint_history` keeps
what the scope was on any date.

**`footprint_change_request.org_unit_id`**, nullable composite key: null is a change to the
group's scope, an id is a narrowing of that entity. The partial unique "one waiting request
per tenant" becomes one per `(tenant, org_unit)` with `NULLS NOT DISTINCT`, so the group
and each entity can each have one request waiting. The four-eyes check constraint is
unchanged.

**`footprint_history.org_unit_id`**, nullable, so "what was SEB Fonder's scope on that
date" replays from the same ledger. The table stays append-only with its trigger.

For an entity request, `removes` lists terms to exclude and `adds` lists exclusions to
lift. The request row, its preview, its decision and its audit events are the group
request's in every other respect.

### 4.3 The code

- **`matching.entity_scope_of(tenant_id, org_unit_id)`** returns the map `E` and a
  `Restricting` whose `opt_in` set also names the closed dimensions, so the existing pure
  `in_footprint()` decides an entity's scope unchanged.
- **`taxonomy_entity_guard(tenant, org_unit)`**, a new SQL function returning the same three
  columns as `taxonomy_footprint_guard` (taxonomy 0008): the guarded terms with their
  dimensions, and the allowed terms. The per-row half, `taxonomy_scope_admits`, reads no
  table and is unchanged. `in_footprint_expression(tenant_id, term_ids, entity=None)` picks
  the guard, so every list keeps reading its scope once per query (NFR-02) and a view scoped
  to an entity costs the same as the group's.
- **The pure rule and the SQL twin are pinned against each other** in
  `apps/taxonomy/tests_matching.py`, as the group rule already is, with the three cases of
  section 4.1 in both suites.
- **The span is folded in, not copied.** `S(d)` comes from the one function
  `c8-reg-applicability` writes for the span (TODO row (a), section 11). A second reading of
  "the entity's terms" would drift from the register's rows.

## 5. Does narrowing need FP-02's four eyes and step-up? Yes

A narrowing is a footprint change. CLAUDE.md §5 puts footprint changes under four eyes with
a passkey step-up, and D-89 says scope changes keep four eyes. Weakening that is a stop for
Alex, and nothing argues for it: the dangerous failure of a scope is the rule it hides, and
a narrowing only hides. A lighter gate would make the entity level the easy way to hide what
the group level guards.

So a narrowing is the FP-02 flow with an entity named:

- A person holding `footprint.request` files it; the counted preview shows what it would
  hide from that entity, per record kind, from `entity_scope_of` before and after (the same
  `preview_of` pattern, run on the entity's map).
- A **second person** holding `footprint.approve` approves it with a passkey step-up; the
  check constraint refuses the requester as decider.
- One audit event per term, as today, each naming the entity's id. No agent key reaches it:
  every footprint route requires a person's permission and an API key carries scopes.
- A **member's entity scope applies to both people**: each must hold the entity in scope
  (section 6), or the answer is 403 `entity_outside_your_scope`. A group-wide member can
  narrow any entity.

Lifting an exclusion takes the same gate. It only reveals, but it is a footprint change, the
group's own additions take four eyes, and one gate for both directions is one path to test.

## 6. A membership's entity scope

### 6.1 What it means

A membership's entity scope is either **every entity** (a group compliance function) or a
**named set** of legal entities (a local team). It is about where a person works, and it
narrows the member's permissions; it never grants one. Permissions still come from roles
alone; the entity scope is a second condition beside them.

- **Writes on an entity's rows.** A member may make a write on a row anchored to an entity
  only when the entity is in their scope and their roles grant the permission. Anchored rows
  are those that name an org unit: per-entity register rows (`TenantObligationScope`), gaps
  on an entity, SoA units through their scope row, duty occurrences on an entity, licences,
  and an entity's narrowing requests. A department's rows are anchored to its nearest
  legal-entity ancestor. Outside scope the write answers 403 `entity_outside_your_scope`.
- **Writes on rows with no entity** (the register entry's own fields, cases, the group's
  scope, members, vocabularies, security) follow roles exactly as today. A local team keeps
  triaging its bank's cases; a named scope never takes away what a role grants at the group
  level.
- **Reads are not walled (default).** Any member may read any entity's rows and choose any
  entity in the switcher, as D-21 treats a department's view: a filter, not a grant. The
  entity scope sets the member's default view (section 8). Whether a bank needs a read wall
  between its companies (an insurer's confidentiality from its bank sister, say) is an owner
  question (`docs/TODO_FOR_alex.md`, block `r2-banking-groups-brief`), and the model is
  shaped so a wall adds only a filter, not a column.
- **Named with nothing in it is refused** (422 `entity_scope_empty`). An empty named set must
  never read as "every entity", the same trap as section 4.1; to take someone off all work,
  deactivate the membership.

### 6.2 The model

| Where | What |
|---|---|
| `membership.entity_scope` | A tier-one kind, `EntityScopeKind`: `all` or `named`, default `all`, so every existing membership keeps today's behaviour with no data migration beyond the default |
| `membership_entity` (tenant table, forced RLS, `apps/identity`) | `(tenant_id, user_id)` composite key to `membership_tenant_user_unique`, `(tenant_id, org_unit_id)` composite key to `org_unit` with the legal-entity trigger of section 4.2, `created_by`, `created_at`; unique `(tenant, user, org_unit)`; the pattern of `membership_role`, keyed the way chunk 8 keys a person |
| `invitation.entity_scope` and `invitation_entity` | The same pair, so an invitation names the scope the membership will get, as it names roles |

Changing a member's entity scope is `PUT /tenant/members/{userId}/entities` under
`members.manage` with a passkey step-up, like a role change (CLAUDE.md §5 names role and
security changes), with one audit event carrying the before and after entity ids. It is not
four eyes: a role change is not, and this is a narrowing of what a role already grants.

### 6.3 The code

One function decides it: `identity.entity_scope.can_act_on(principal, org_unit_id)`, which
resolves a department to its legal entity and answers from the membership. Every writer of
an anchored row calls it before `record()`. An AST guard in the style of the library fence
lists the anchored tables and fails when a module writes one without calling it, so a later
table cannot forget. A personal access token (ACC-03) acts as its person, so the person's
entity scope applies to it; every agent access credential is read-only through R2 anyway.

## 7. What each footprint reader does with an entity

D-69 counted eleven call sites in R1. On the base of this brief (`origin/main` with
`c8-org-models`), the regulatory scope is read at **seven** `footprint_of` calls in six
files, **five** `in_footprint_expression` calls that hand the SQL guard to a list, three
direct `FootprintTerm` reads in production code beside the seeds, and the two FP-02 writers. Every one is below, with what it does with an entity. "Takes
`entity`" means the reader gains an optional `entity=<org unit id>` query parameter: absent is
the group's scope, exactly as today; an id loads the unit under row-level security (another
bank's id answers 404, a unit that is not a legal entity 422 `not_a_legal_entity`) and
swaps in the entity guard of section 4.3. **No reader's default changes.**

### 7.1 `footprint_of` (`apps/taxonomy/matching.py:81`)

| File and line | Function | Surface | With an entity |
|---|---|---|---|
| `apps/library/reading.py:632` | `obligation_page` | `GET /obligations` (INV-03, FP-03) | Takes `entity`: `footprint=in` means the entity's scope; `all` is unchanged; `watched` stays the group's, because markets are the tenant's (FP-04) |
| `apps/library/reading.py:808` | `obligation_detail`, through `scope_and_verdict` | `GET /obligations/{obligationId}` | Takes `entity`: the outside reasons are per dimension of `E`, so the page can say "outside Example Fonder AB's scope: product type" |
| `apps/library/reading.py:910` | `instrument_page` | `GET /instruments` (INV-01) | As `obligation_page` |
| `apps/watch/reading.py:245` | `_Scopes`, the feed's verdict and watched market | `GET /changes` (WAT-01, FP-04) | Takes `entity` for the inside verdict; the watched-market column stays the group's |
| `apps/cases/creation.py:103` | `_create_case` | One case per bank per change (CAS-01) | **Nothing.** A case belongs to the bank, and `footprint_match` stays the group's verdict. A narrowing opens, closes and recomputes no case |
| `apps/proposals/updates.py:150` | `_verdicts` | `GET /library-updates` | **Nothing.** A digest of what the library changed, kept at the group's scope as D-84 keeps it simple |
| `apps/taxonomy/footprint_logic.py:168` | `preview_of` | The counted preview (AC-FP1) | For an entity request, `now` and `after` are the entity's map before and after; for a group request, unchanged |

### 7.2 `in_footprint_expression` (`apps/taxonomy/matching.py:106`), the lists' SQL guard

| File and line | Function | Surface | With an entity |
|---|---|---|---|
| `apps/library/reading.py:510` | `_matches` | The obligations and instruments lists | Passes the entity to the guard |
| `apps/watch/reading.py:170` | `_in_footprint` | The watch feed's filters | Passes the entity to the guard |
| `apps/search/hybrid.py:375` | `_in_footprint` | `POST /search` and Ask's passages (SRC-01, SRC-03) | Takes `entity`, so a search or an Ask question asked while the switcher names an entity is answered in its scope. Still library only (D-10); the AI switch is unchanged (D-88) |
| `apps/cases/matching.py:120` | `_recompute` | Re-deciding `footprint_match` after a group change | **Nothing**, as `_create_case` |
| `apps/proposals/updates.py:74` | `_applied` | The library-updates count | **Nothing**, as `_verdicts` |

### 7.3 Direct `FootprintTerm` reads

| File and line | What it reads | With an entity |
|---|---|---|
| `apps/taxonomy/terms_logic.py:204` | `selected_terms_by_dimension`, the Regulatory scope screen | Gains an entity view listing the group's terms with the entity's exclusions marked, beside the group view |
| `apps/taxonomy/markets_logic.py:52` | `_operating`, the operating markets (FP-04) | **Nothing.** Markets are the tenant's; an entity that excludes a jurisdiction simply sees less of it |
| `apps/tenants/logic.py:56` | Onboarding's "footprint" step | **Nothing** |
| `apps/shared/e2e_seed.py:382`, `:404`; `apps/cases/testing.py:95` | Seeds and test builders | The build adds an entity narrowing to the seed (section 13) |
| `apps/taxonomy/footprint_logic.py:254`, `:296` | `_switch_on` and `_switch_off`, the FP-02 writers of `footprint_term` | **Unchanged** for the group; an approved entity request writes `entity_scope_exclusion` through its own pair beside them, with the same history and audit rows |

### 7.4 Readers of a stored verdict, not of the footprint

`apps/home/roadmap.py` and `apps/home/logic.py` (Today) filter on `change_case.footprint_match`.
With `entity`, they apply the entity guard over each case's change scope at read time
(`apps/cases/reading.py`'s `scope_term_ids_of_each_case`, which already exists for the
preview); nothing per entity is stored on a case. `GET /upcoming` (`apps/home/calendar.py`) is
a library read with no scope verdict and stays one. My work (HOM-05) ignores the entity, as
the footprint "never hides a person's own items", and labels each item with its entity.

### 7.5 Tests that call it

`apps/shared/tests_seed_integrity.py`, `apps/taxonomy/tests_matching.py`,
`apps/taxonomy/tests_scenarios.py` and `apps/watch/tests_testing.py`. None changes: the
group's scope is unchanged, and the build adds its own cases beside them.

## 8. The entity switcher

- **Where.** One control in the tenant shell's top bar, shown only when the tenant has two
  or more active legal entities. A bank with one company never sees it.
- **What it lists.** "Whole group" first, then each active legal entity by name, the
  member's own entities first. Inactive entities are left out of the list but still open by
  link, dimmed, as the organisation tree shows them.
- **Where the choice lives.** In the URL, as `?entity=<org unit id>`, so a link, the back
  button and a second tab behave, and every scoped screen passes it to its API call. The last
  choice is remembered per browser as a convenience; nothing is stored on the server.
- **The default.** A member whose named scope holds exactly one entity opens on it; everyone
  else opens on "Whole group". This is the "easy access" Alex asked for: a group function
  switches in one click and loses nothing; a local team lands in its own company.
- **What it scopes.** The inventory, the obligation page's verdict, the watch feed, search,
  Ask, the roadmap, Today and the briefing. Not My work (section 7.4), not the admin screens,
  not the library-updates digest.
- **What it says.** Every scoped screen names the entity it is showing next to its title, so
  a narrowed view never reads as the whole group, the ACC-07 principle for people. Copy in
  the `en` and `sv` catalogs; no pill is needed, because the entity is a name, not a state.

The switcher decides no permission. A write outside the member's scope is refused by the
server (section 6.3) whatever the switcher shows, and the screen hides the write controls
the member cannot use, as it already does for permissions.

## 9. What each agent access scope does with an entity

An agent access entry (ACC, chunk 11) is a group-level reader narrowed by the terms of its
departments and products (D-70). The build adds one axis, the membership's, to the entry: an
entry reads **every entity** (default, so an entry built in chunk 11 changes nothing) or a
**named set**. The entity scope intersects with D-70's narrowing; it never replaces it.

| Scope | With every entity | With a named set |
|---|---|---|
| `library:read` | Unchanged: group scope ∩ the entry's terms | A record is readable when it is in at least one named entity's scope (section 4) and passes the entry's terms; outside, 404, never a filtered 200 (ACC-02) |
| `search:read` | Unchanged | The same guard as `library:read`, in `hybrid.py` |
| `upcoming:read` | Unchanged | The dated changes touching a record readable as above |
| `tenant:read` | Every entity's register rows, behind the tenant reach switch (ACC-08) | Only the scope rows, and the entry-level fields of obligations in scope, of the named entities; another entity's row answers 404 |
| `what_applies` (ACC-06, ACC-07) | Unchanged | Answers in the named entities' scope and names them in the scope it states; a description that touches another entity's scope says so from labels, never records, as ACC-07 already does for dimensions |

A personal token acts as its person (ACC-03), so its entity scope is the person's
membership scope intersected with the entry's, when it names one. `agent_access_entity`
mirrors `membership_entity`, one join with composite keys. No scope gains a write.

## 10. What `OrgUnit` and `Membership` must carry so the build is additive

Checked against the merged tenants 0002 and identity models:

| Needed | Present now | The D-69 build adds |
|---|---|---|
| A stable target for a composite key to an entity | `org_unit_tenant_id_id_unique` | Nothing |
| Knowing a unit is a legal entity | `OrgUnit.kind = legal_entity` | The trigger on its two new joins |
| The entity's own type, for the span | `OrgUnit.entity_term` with its trigger | Nothing |
| A department's entity | `OrgUnit.parent` | Nothing: resolved by walking to the nearest legal entity |
| Deactivating an entity | `OrgUnit.active` | Nothing |
| A target for a composite key to a membership | `membership_tenant_user_unique (tenant, user)` | Nothing |
| The member's entity scope | Absent, as `c8-org-models` was told | `membership.entity_scope` (default `all`) and `membership_entity` |
| An entity's narrowing | Absent | `entity_scope_exclusion`, and a nullable `org_unit_id` on `footprint_change_request` and `footprint_history` |

Every addition is a new table or a nullable or defaulted column, and no built column changes
meaning. The one constraint that changes is the partial unique on
`footprint_change_request`, replaced by a wider one in the same migration; no existing row
violates it.

## 11. What chunk 8 must do now

Each is a row in `docs/TODO_FOR_alex.md` under `r2-banking-groups-brief`, for the package
named, not a code change here.

- **(a) One span function.** `c8-reg-applicability` computes "which entities an obligation
  spans" in one named function that also exposes the entity's terms as a dimension map, and
  every reader of the span calls it. The D-69 build folds that map into `S(d)` (section 4.3);
  a second reading would drift from the register's rows.
- **(b) A legal entity stays a legal entity once rows point at it.** `c8-ten-organisation`'s
  `PATCH /tenant/org-units/{id}` refuses changing `kind` to or from `legal_entity` while a
  licence, a per-entity scope row, a gap or a duty occurrence names the unit (409). Otherwise
  a per-entity row in chunk 8 could end up naming a department, and D-69's joins would inherit
  the same hole.
- **(c) Per-entity rows name a legal entity.** The writers of `TenantObligationScope`,
  `Gap.org_unit` and `DutyOccurrence.org_unit` (`c8-reg-applicability`, `c8-reg-status`,
  `c8-reg-gaps-risk`, `c8-duty-occurrences`) check that the unit is an active legal entity
  (422 `not_a_legal_entity`), with a test each. It is chunk 8's own correctness, and it is
  what lets section 6's `can_act_on` read the entity straight from the row.

Nothing else in chunk 8 needs to move: every other addition in section 10 is additive.

## 12. The build, when it comes (D-96)

After R2, unless Alex promotes it. It needs chunk 8 (the organisation, the register and the
span) and, for section 9 only, chunk 11's agent access. When promoted, the PRD gains two
rows (numbered then): per-entity narrowing under FP, and a membership's entity scope under
TEN. Suggested packages, in the R2 plan's shape:

| Package | What | Depends on | Owned paths |
|---|---|---|---|
| `bg-scope-models` | `entity_scope_exclusion`; `org_unit_id` on `footprint_change_request` and `footprint_history`; the wider one-waiting unique; the legal-entity trigger; forced RLS and the `tests_rls` entries | chunk 8 | `apps/taxonomy/models.py`, the next taxonomy migration, `apps/taxonomy/tests_entity_models.py` |
| `bg-entity-guard` | `entity_scope_of`, `taxonomy_entity_guard`, `in_footprint_expression(..., entity=)`; the mirror tests with the three traps of section 4.1; the span folded in | `bg-scope-models`, TODO (a) | `apps/taxonomy/matching.py`, the next taxonomy migration, `apps/taxonomy/tests_matching.py` (own block) |
| `bg-narrowing-requests` | The FP-02 flow with an entity: request, preview, approve with step-up, reject, withdraw; the 422 and 403 codes of sections 4 and 5; the Regulatory scope screen's entity view (API) | `bg-entity-guard`, `bg-membership-scope` | `apps/taxonomy/footprint_logic.py`, `apps/taxonomy/api.py`, `apps/taxonomy/schemas.py`, `apps/taxonomy/terms_logic.py` |
| `bg-membership-scope` | `membership.entity_scope`, `membership_entity`, the invitation pair; `PUT /tenant/members/{userId}/entities` with step-up; `can_act_on` and its AST guard over every anchored writer | chunk 8, TODO (b) and (c) | `apps/identity/models.py`, the next identity migration, `apps/identity/entity_scope.py`, `apps/identity/api.py` |
| `bg-readers` | `entity` on every reader section 7 marks, 404 and 422 as stated, query counts that do not grow with the number of entities, the budget held | `bg-entity-guard` | The reader modules of section 7, each its own block |
| `bg-fe-switcher` | The switcher, the scoped screens passing `entity`, the entity named on each, the Regulatory scope screen's entity tab, `en` and `sv` | `bg-readers`, `bg-narrowing-requests` | `frontend/src/features/entity-switcher/`, the shell's one mount point, the screens' own blocks |
| `bg-acc-entity` | `agent_access_entity` and section 9 | `bg-entity-guard`, chunk 11 ACC | `apps/agents/models.py`, the ACC scope code |
| `bg-close` | `seed_e2e`'s narrowing, and a named-scope login added to the E2E login roster (`R2_CROSS_CUTTING.md` (d)), the journeys, the `app.md` rows and statuses, the TODO rows closed | all above | The seed's own function, the journey specs, the `app.md`s |

Gates as every R2 package: the suites of the apps touched, `migrate_from_zero`, the
compliance lint, the API documentation gate for every new operation, contract drift, the
journeys below against the real stack, then `prepush.sh --quick`.

## 13. Test scenarios to write

Each becomes a Gherkin scenario in the owning app's `app.md`, `@integration` in its
`tests_scenarios.py` and, where it is a screen, `@e2e` in its journey spec. The data is the
seed's group: Example Bank AB, Example Fonder AB and Example Liv Försäkring AB.

1. Example Fonder AB excludes a jurisdiction; its inventory hides a rule carrying only that
   jurisdiction and still shows a rule carrying no jurisdiction; the group's inventory is
   unchanged.
2. Excluding the last of the group's terms in a dimension closes it: a record carrying any
   other term of that dimension, including one the group never named, stays hidden from the
   entity (the widening trap).
3. The one-pass rule: group `{cards}`, the entity excludes `cards`, a record carrying `{cards,
   mortgages}` is outside the entity's scope; the pure rule and the SQL guard agree.
4. An exclusion in the standards dimension answers 422 `opt_in_not_narrowable`; one in a
   dimension that does not restrict, 422 `dimension_does_not_restrict`; one of a term outside
   the group's scope, 422 `term_outside_group_scope`.
5. A narrowing waits for a second person, the requester cannot approve it, the approval
   needs a passkey, and one audit event per term names the entity; a group request and an
   entity request can wait at the same time, two for the same entity cannot.
6. A narrowing opens, closes and recomputes no case, and deletes no per-entity row; lifting
   it shows the same rows unchanged.
7. The group adds a term: every entity that has not excluded it sees the records it reveals.
8. A member scoped to Example Liv Försäkring AB sets a status on its own entity row, is
   refused 403 `entity_outside_your_scope` on Example Bank AB's row, and still triages a case.
9. A named scope with no entity is refused 422 `entity_scope_empty`; changing a member's
   entity scope needs `members.manage` and a passkey and writes one audit event.
10. Another bank's entity id on any reader answers 404; a department's id answers 422
    `not_a_legal_entity`; a list's query count does not grow with the number of entities.
11. The switcher: a local member opens on their entity, a group member on "Whole group";
    switching changes the inventory and names the entity on the screen; a bank with one
    entity shows no switcher.
12. An agent access entry naming one entity answers 404 for a rule outside that entity's
    scope and reads only that entity's register rows under `tenant:read`.

## 14. Defaults taken, and what stays open

Each default is recorded in `docs/TODO_FOR_alex.md` under `r2-banking-groups-brief`.

- **When it is built (D-96).** The brief now, the build after R2 unless Alex promotes it.
  Alex took the plan's default on 2026-09-25 ("take the defaults for the rest",
  `docs/plans/r2-waves/owner_questions.json`).
- **No read wall between entities.** An entity scope narrows where a member acts and sets
  their default view; any member reads any entity (section 6.1). Open: whether a bank needs
  the wall.
- **Narrowing keeps FP-02's four eyes and step-up**, both ways. This is CLAUDE.md §5 and D-89,
  not a default; it is written down so nobody proposes a lighter gate for entities.
- **Exclusions, not subsets**, and **one level**: every entity narrows the group's scope
  directly (section 4.1).
- **Markets stay the tenant's** (FP-04), and the library-updates digest and case creation
  stay at the group's scope (section 7).
- **The switcher lists "Whole group" to every member**, because reads are not walled; it
  goes if the wall comes.

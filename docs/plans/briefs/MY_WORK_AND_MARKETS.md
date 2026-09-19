# My work, participants and markets: analysis

This was read-only analysis. No file in the repository was edited. I checked against `main` at **e629481**, which is 51f9efa (chunk 3's data layer) plus the navigation specification. PRD **0.2** (sector scope, 7613874) is already on main, so the PRD bump below is **0.3**.

**What changed after review**
- **Markets.**
  - Markets live on the existing Footprint screen. There is no separate screen.
  - EU reach reuses `Jurisdiction.parent` and is applied when a record's terms are derived. That needs no new column, no `parent_required` and no change to the SQL function.
  - A market's level is computed, with operating first, so footprint approval never touches the watch list.
  - No tenant fact travels in a URL, because the access log and Sentry keep paths.
- **Departments** are the org units already in the designed schema, each with a head. They are no longer team leads.
- **My work.**
  - It loses the decisions bucket, the per-person strip and the footprint marker.
  - It uses the shared pagination.
  - Every row and every count is filtered by read permission.
- **Notifications** pass one recipient check: only active members who can read the record, once per event.
- **Scenarios** are split so that each one is completed within a single chunk.
- **Repeated writes answer 409.** A check I found myself: the audit guard fails any 2xx write that leaves no audit row, so "200, nothing written" is not available.

## 1. The problem

Alex asked for two features. Broken into needs:

**Feature 1: my work and participants**
1. One page showing what I am responsible for or take part in, when my next reviews are due, and which changes I need to watch.
2. Notes on my work that I can find on that page.
3. Adding a participant to an inventory item or to an upcoming change.
4. As a department head, everything affecting my department, next to what I own or take part in.

**Feature 2: markets**
1. In Settings, the markets we operate in, clearly marked as where we pay extra attention.
2. Research keeps sweeping broadly.
3. Aspiring or interesting markets that agents pay attention to.

Both features are about **attention, not access**. None of these needs requires a person to see something they cannot see today, or to be kept away from something they can see. Both designs therefore stay clear of RLS and the permission model, and both can stay small.

## 2. What already exists

**Built on main**
- **Identity, members and roles.**
  - `Membership` has `last_visit_at`, `notification_prefs`, `out_of_office_until` and `delegate`. None of them is read yet.
  - `Membership` is unique on (tenant, user).
  - Removing a member (`DELETE /tenant/members/{userId}`) only sets `deactivated_at`, revokes sessions and closes invitations (`members_logic.deactivate_member`).
- **Vocabularies and eleven taxonomy dimensions.**
  - One dimension is `jurisdiction`: `restricts_footprint=True`, with the usage note "Terms mirror the jurisdiction table", and **zero terms**, so it restricts nothing.
  - `/admin/footprint` shows an empty Jurisdiction row, while the card (`admin-footprint.html:275`) draws EU, Sweden, Denmark, Norway and Finland.
  - The jurisdiction *list* is `proposable=False`, but its *dimension* accepts term proposals like any other today.
- **Footprint change requests.**
  - Dry-run preview, step-up, and four eyes enforced by a check constraint.
  - One audit event and one history row per term.
  - One pending request at a time (409 `request_pending`).
  - `GET /tenant/footprint` is readable by every member.
- **Matching is flat.**
  - `matching.in_footprint(record_terms, footprint)` compares term sets per dimension.
  - Its SQL twin `taxonomy_in_footprint(p_tenant, p_terms uuid[])` reads the footprint itself and takes the record's term ids as an array that its caller builds.
- **Jurisdiction rows EU, SE, DK, NO and FI**, seeded only.
  - `Jurisdiction.parent` points SE, DK and FI at the EU. **Norway has none**, although EU financial law reaches it through the EEA Agreement.
  - Only `GET /reference/jurisdictions` (`parentKey`) reads `parent`.
- **Chunk 3.**
  - Its data layer is on main (51f9efa): `Authority.jurisdiction` and `Instrument.jurisdiction`, both required; `ObligationTerm`; and the "shared or mine" rule on instruments and obligations. There is no read API yet.
  - `CHUNK3_TASKS.md` plans one scope rule in `library/reading.py`, with a SQL twin, and an `outsideFootprint=true` filter.
  - It also records that "neither inherits a jurisdiction term, because none is seeded".
  - `IMPLEMENTATION_STATUS.md` still marks chunk 3 `pending`.
- **Guards this design must meet.**
  - `AuditAssertingClient` fails any 2xx write that leaves no audit row, and a duplicate answers 409 (`already_member`).
  - Only the app logger uses `loggable_route()`. Gunicorn runs with `--access-logfile -`, whose default format prints the full request line with path and query. Sentry transactions keep `request.url`, and `scrub_url` rewrites only invitation paths.
  - Every list uses `PageQuery`: limit and offset, from `API_PAGE_SIZE_DEFAULT` and `API_PAGE_SIZE_MAX`.
  - `GET /vocab/{list}` already serves any tenant list to member sessions for pickers.
  - `TenantModel` declares no `UNIQUE (tenant_id, id)`, which composite foreign keys need.
  - The navigation spec (e629481) allows at most four dock destinations per surface, and all four are taken.
- **Prototype data.** 8 EU and 7 Swedish instruments.

**Not built: anything a person can own.** The `register`, `cases`, `collab`, `agents`, `watch` and `home` apps have empty `models.py` files. There is no tenant_obligation, change_case, team, org unit, internal item, comment, notification, follow or tenant agent.

**Designed in the inputs and relied on here**
- **Owners.**
  - `tenant_obligation` has `first_line_owner`, `compliance_contact`, `owner_team_id` and `next_review_date`.
  - `tenant_obligation_scope` has `owner_id`, but no per-entity `next_review_date`, although REG-S3 requires one.
  - `change_case` has `owner_id` and `owner_team_id`.
  - Actions, gaps and duty occurrences each have an owner.
  - `internal_item` (REG-05) has `owner_id` and `next_review_on`.
- **Organisation.**
  - `org_unit` has the kinds legal_entity, business_area, business_unit and function, a `parent_id` and a `head_user_id`. `team.org_unit_id` places a team in a unit.
  - So a department with a head and teams under it is already designed, although PRD TEN-02 names only legal entities.
  - `team_member` carries `is_lead`.
  - All of these use plain foreign keys.
- **Collaboration.**
  - `comment` is visible to the whole tenant.
  - `notification` has a kind column.
  - `follow` (R3) is a personal watchlist of library records: instruments, obligations, initiatives and theme terms.
- **`GET /me/work`** returns five unpaginated arrays: cases, actions, sign-offs waiting, applicability requests waiting and reviews due. It feeds Today's "Decide now" in chunk 6 (UI plan line 116). `GET /me` carries `QueueCounts`: triage, proposals, sign-offs, assigned to me and unread notifications.
- **`v_roadmap_item`** leaves out reviews of compliant obligations and past dates. My work does not read it, and the roadmap stays as designed.
- **Agent scope.** `tenant_agent.scope` reads "empty = follow the footprint". AGT-S5 already restricts scope to SE and FI.
- **Broad sweeps are already in the design.** Platform library runs (`agent_run.tenant_id` NULL) sweep every registered source for every tenant, and no tenant setting narrows the shared library.
- **Every change already has a tenant record.** CAS-01 creates one case per tenant per change, whatever the footprint (CAS-S1). Changes and obligations themselves are library rows, shared unless `owner_tenant_id` makes them one tenant's.

**Genuinely new**
- a participant relation
- a personal page that says why each item is on it
- a department view
- a list of my comments and mentions
- a "watching" level for markets
- EU reach for Norway

## 3. Feature 1: My work and participants

### 3.1 What Alex's words map to

| Alex's word | What it is | Chunk |
|---|---|---|
| Owner of an inventory item | The designed owners of the register entry: first-line owner, compliance contact, owner team, owner per legal entity. Also the owner of an internal item | 8 (REG-02, REG-05, TEN-03) |
| Owner of an upcoming change | `change_case.owner`, `owner_team` | 9 (CAS-02) |
| Owner of smaller work | Owners of gaps and duty occurrences (8) and actions (9) | 8, 9 |
| Contributor / participant | **New** participant row: a person or a team on a register entry or a case. It lists and notifies, and grants nothing. CAS-03 contributor teams are the case's team participants | 8, 9 |
| Department | The designed `org_unit` of kind business_area, business_unit or function, with teams in it (`team.org_unit_id`) | 8 (TEN-02, TEN-03) |
| Department head | `org_unit.head_user_id` | 8 |
| Notes | Shared COL-01 comments, listed on My work as "Comments and mentions" | 10 |

Screen text says "Participants" and "Takes part", never "Contributor". Contributor is already a system role, and it grants `cases.contribute` across the whole tenant.

### 3.2 Data

**New: `participant`** (app `collab`, tenant zone, forced RLS)
```
participant(id, tenant_id,
  tenant_obligation_id NULL, case_id NULL,
  user_id NULL, team_id NULL,
  added_by, added_at, removed_by NULL, removed_at NULL)
FK (tenant_id, tenant_obligation_id) -> tenant_obligation(tenant_id, id)
FK (tenant_id, case_id)              -> change_case(tenant_id, id)
FK (tenant_id, team_id)              -> team(tenant_id, id)
FK (tenant_id, user_id)              -> membership(tenant_id, user_id)
CHECK num_nonnulls(tenant_obligation_id, case_id) = 1
CHECK num_nonnulls(user_id, team_id) = 1
partial UNIQUE (subject, user|team) WHERE removed_at IS NULL
indexes on (tenant_id, user_id), (tenant_id, team_id), (tenant_id, case_id),
(tenant_id, tenant_obligation_id), each WHERE removed_at IS NULL
```
- **Anchors are tenant rows only, never library rows.**
  - An inventory item is the register entry (`tenant_obligation`). It is created on its first write by the register's single `ensure_register_entry()`, which writes its own `register.entry_created` audit event in the same transaction.
  - An upcoming change is its `change_case`.
- **Composite foreign keys, membership included.**
  - PostgreSQL foreign-key checks bypass RLS, so a plain key would accept another tenant's row, or a user who is not a member.
  - `membership_tenant_user_unique` already exists. tenant_obligation, change_case, team and org_unit each gain `UNIQUE (tenant_id, id)` when they are built.
  - The constraints are added in the migration as SQL, the way the RLS policies are.
  - Logic also loads the subject under RLS first and answers 404 if it is not visible.
- **Soft removal** (`removed_at`). The case file (CAS-07) and the history (REG-04) show who took part. Nothing is overwritten.
- **No text column**, and no participant-role vocabulary.

**Also in chunk 8, each as an INPUT_DELTAS row**
- `tenant_obligation_scope.next_review_date`.
- `team` as a tier-3 tenant list, so `GET /vocab/team` serves pickers. It sits in a department through `org_unit_id`.
- `team_member(team, user)`, with composite keys to team and membership. **`is_lead` is not built**: department heads sit on the org unit, and team notifications go to the team's members (D-21, D-34).
- `org_unit.head_user_id` and `team.org_unit_id` as composite keys.

**Tier-one kinds** (`backend/apps/shared/kinds.py`)
- **`WorkReason`**: owner, participant. Whether it names a person or a team rides in `who`, and which child it concerns comes from `itemKind` and `date.kind`. Four phrases, two values.
- **`WorkBucket`**: overdue, due_soon, aware, open.
- **`WorkDateKind`**: review, gap_target, duty_due, internal_deadline, action_due, key_date, linked and version_applied, plus commented from chunk 10.
- **`NotificationKind`** (chunk 10): the nine designed kinds, plus participant_added, involved_item_changed and review_due.

**Settings**
- `MY_WORK_DUE_SOON_DAYS`: 30, replaced by the tenant reminder lead once COL-02 lands.
- `MY_WORK_AWARE_DAYS`: 14.
- `MAX_PARTICIPANTS_PER_RECORD`: 50.
- Pages use the shared `PageQuery`.

### 3.3 One definition of "my work"

One service, `backend/apps/home/my_work.py`, unions ORM queries under the activated tenant. **There is no database view**, so RLS applies the same way it does everywhere else. The page, the COL-02 reminders, the digest and the TEN-05 removal preview all read this one service.

**Step 1: which items involve me**

| Source | Reason (who) |
|---|---|
| I am the register entry's first-line owner or compliance contact, or I own one of its entity rows | owner (me) |
| I own an internal item, a gap or a duty occurrence; from chunk 9, a case or an action | owner (me) |
| One of my teams owns a register entry, or (from chunk 9) a case | owner (the team) |
| I take part, or one of my teams does | participant (me or the team) |

**The department scope** is `scope=unit&unit=<id>`. There, "me" becomes the teams whose department is that unit or a unit below it, together with their **active** members. Every row names who is responsible.

**Step 2: which items are still live.** Hidden:
- register entries that do not apply
- inactive internal items
- closed or dismissed cases
- finished actions, closed gaps and completed duties

**Step 3: the next date on each item** (compared with the tenant-local today, COL-S3)
- **Involved in the record itself:** the earliest open date on it. That covers the next review (also for **compliant** obligations, per entity, and on internal items), gap targets, duty dates, the internal deadline and action dates.
- **Involved only through a child:** the earliest date among the children I own.
- **A change's key date** counts toward "due soon" only while it is still ahead. A key date in the past means the rule is in force, not that anything is overdue.

**Step 4: buckets.** Each item appears once, in the first bucket it qualifies for:
1. **Overdue**: oldest first.
2. **Due soon**: within the reminder lead, soonest first.
3. **Changes on your items** (aware):
   - open cases whose change has a WAT-04 link, **confirmed by a person**, to an obligation I am involved in (the row carries `via` naming that obligation);
   - obligation versions applied in the last 14 days;
   - from chunk 10, new comments and mentions on my items.

   It never shows the caller's own acts, or agent-suggested links that no person has confirmed.
4. **Everything you're responsible for**: by date, undated items last, then by id.

**Decisions** (sign-offs, applicability and risk acceptance) stay on Today's "Decide now", fed by the queue counts on `GET /me`. My work links there in one line.

**Permissions.** Register and internal-item rows need `register.read`, and case rows need `cases.read`. **Rows and every count** come from the permission-filtered set. A kind the viewer cannot read is returned as `permissionLimited`, and the page says so. It never answers 403 for the whole page and never shows "Nothing to do" instead. If a participant's role later loses read permission, the participation stays and the item comes back to that person as permission-limited.

**The footprint.** My work does not apply the footprint and marks nothing as outside it. FP-03 names the feed, inventory, roadmap, briefing and reports. Losing sight of your own responsibility after the footprint narrows would do more harm than showing it.

### 3.4 API

| Route | Gate | Returns |
|---|---|---|
| `GET /me/work?scope=mine\|unit&unit=<id>&bucket=&limit=&offset=` | Ungated `LOGIC_GATE`; logic checks the read permission for each record kind | `{scope, counts{overdue,dueSoon,aware,open}, permissionLimited[], items: WorkItem[], total}` |
| `GET\|POST /obligations/{obligationId}/participants` | Read: `register.read`. Add: `register.edit` | `{items,total}` of `Participant{id, person?, team?, addedBy, addedAt}` |
| `DELETE /obligations/{obligationId}/participants/{participantId}` | Ungated `LOGIC_GATE`: `register.edit`, or the person on their own row | 204 |
| `GET\|POST /changes/{changeId}/participants` | Read: `cases.read`. Add: `cases.contribute` | as above |
| `DELETE /changes/{changeId}/participants/{participantId}` | Ungated `LOGIC_GATE`: `cases.contribute`, or the person on their own row | 204 |
| `GET /reference/people` | Ungated `CAPABILITY`: a member session, not an enrolment session. `GET /tenant/members` needs `members.manage` | `[{id,name}]`, active members only |
| Team picker | `GET /vocab/team` (exists) | active team rows |
| `GET /me` | unchanged | adds `headOf[{id,name}]`, the departments the viewer heads |
| `PUT /tenant/members/{userId}/teams` | `members.manage` | `{teams:[key]}`, with one audit event per call holding the before and after keys |
| `GET /me/comments?about=written\|mentioned&limit&offset` (chunk 10) | `comments.write`; each comment is also filtered by the read permission of its subject | a page of comments with `subject{type,id,title}`, plus `permissionLimited[]` |

**The `WorkItem` shape**
- `bucket`, and `itemKind` (the existing subject type key)
- `subject{obligationId|changeId|internalItemId, title}`
- `entity?`
- `date{value,kind,precision}`
- `reasons[{reason, who{person|team}, via?{obligationId,title}}]`
- `status?{key,kind,label}`, `urgency?{key,kind,label}`
- `openChangeCount`

It carries keys, kinds, dates and record names, never a phrase. Items are ordered by (bucket order, date, urgency ordinal, id) and paged with limit and offset.

**Participant writes.** `POST {userId}|{teamKey}` answers 201. Refusals:
- 409 `already_participant` when the row is already there.
- 404 when the subject is not visible.
- 422 `unknown_member`, answered the same way for a user of another tenant, a deactivated member or an unknown id.
- 422 `unknown_key` for an unknown team.
- 422 `participant_cannot_read` when a person's roles cannot read the record. A team is not checked, because each member's own read permission already filters what they see and receive.
- 422 `too_many_participants` over the cap.
- 409 `invalid_transition` on a closed or dismissed case.

**Tenant isolation registry.** The participant `GET` and `DELETE` routes join `TENANT_SCOPED_ROUTES`, with a factory that builds the participant on a tenant-private record.

**Contract change (INPUT_DELTAS §7)**
- `/me/work` is reshaped as above.
- The designed decision arrays move to `QueueCounts` on `GET /me`: `signoffs` already exists there, and `applicability` is added in chunk 8.
- The UI plan moves `/me/work` from Today (chunk 6) to the My work screen (chunk 8).

### 3.5 Screens (design cards first, playbook 7)

**My work** (card `tenant-my-work.html`, route `/work`)
- **Nav entry.** `my-work`, in the secondary group with no `dockRank`, and no permission gate. The dock is full, so phones reach it under More.
- **Scope switch.** "Mine", plus each department the viewer heads. A head opens on their department, and the choice is remembered in localStorage inside try/catch.
- **Sections.** The four buckets, in order, then one line linking to Today for decisions.
- **Each row:**
  - the title as a link;
  - the item kind and date as meta text ("12 days overdue", "in 9 days");
  - existing pills only;
  - the reason as muted text: "You're responsible", "Your team is responsible", "You take part", "Your team takes part", "Linked to {obligation}", and in the department scope "Anna is responsible".
- **Chunk 10.** A "Comments and mentions" panel. Its composer says that everyone in the organisation can read comments.
- **States.** Empty, loading, error and denied. On a phone it is the same list.
- **No new pill slot and no new tone.**

**Participants panel.** On the obligation page from chunk 8, and on the change page from chunk 9.
- The owners, read-only, above the list.
- Each participant, with who added them.
- "Add": one picker over `/reference/people` and `/vocab/team`, shown only with the edit permission.
- "Leave" on your own row.
- On the change page, the assessment's Contributors field is this list filtered to teams. Each change is sent as a single add or remove call.

**Organisation admin** (`admin-organisation.html`, chunk 8). Departments (org units of kind business area, unit or function) with a head, and teams with their department. **Members admin** (`admin-members.html`). Team membership on each member row. **Today** is unchanged.

### 3.6 Permissions

There is no new permission. The PRD §6 matrix changes only descriptions.

| Action | Who may |
|---|---|
| View My work, your own or any department's | Any member. Each item still needs its read permission; the department scope is a filter, not a grant |
| Add or remove participants on a register entry | `register.edit` (compliance officer, owner) |
| Add or remove participants on a case | `cases.contribute` (compliance officer, owner, contributor) |
| Leave your own participation | Anyone |
| Departments, their heads and teams | `vocab.manage`, as for the legal entities in TEN-S2 |
| Team membership | `members.manage` |

Participation needs no step-up and no four eyes: it approves nothing, hides nothing and grants nothing.

### 3.7 Behaviour

**Audit.** `participant.added`, `participant.removed`, `participant.left` and `register.entry_created`, all through `record()`, carrying ids only. The subject is the register entry or the case, and the title is the library title.

**Notifications (chunk 10).** One recipient check serves every kind: active members whose roles can read the record's kind at send time, one notification per person per event, whatever the number of reasons. A team named on a record reaches its active members. Titles and emails carry the library title and a link, nothing else.
- `participant_added` goes to the person added, or to the members of the team added.
- `involved_item_changed` goes to owners and participants when a link is confirmed or a new version is applied. It never goes to the person who acted.
- `review_due` goes to whoever is responsible for each review date, at the reminder lead.
- Escalation goes to the head of the department of the owner's teams (COL-S2's "owner's manager"), together with the compliance officer.
- Mentions pass through the same check, so a person mentioned on a record they cannot read receives nothing.

**Comment text.** Comment bodies never reach logs, Sentry, the audit `after` value, outbox payloads, webhooks, the SIEM stream, notification titles or emails. `GET /me/comments` returns only comments on records the reader can read.

**Member removal (TEN-05).**
- The preview lists what the member owns, "Takes part in N items" and their teams.
- On confirm, their person participations and team memberships end in the same transaction, with one audit event each.
- Team participations are not affected.

**Teams.** Retiring a team that owns open work is refused. Merging teams re-points the owner-team and participant rows.

**Performance.** A test pins a fixed query count and a response under 250 ms for a department of 50 members.

## 4. Feature 2: markets

### 4.1 The idea

A market is a country the platform covers. Each one is **Operating**, **Watching** or **Not followed**.

- **Operating** means the country's term is in the footprint.
  - It is set on the Footprint screen's Jurisdiction row and changes only through the existing FP-02 request: preview, second person, step-up, one audit event per term.
  - This is what "extra attention" means here: operating markets make up the default view everywhere.
- **Watching** means a row in a new tenant list, `watched_market`, set on the same screen.
  - It hides nothing and reveals nothing by default, so it is a direct write with an audit row.
  - It powers the "Markets we watch" view of the inventory and the watch feed, and from chunk 11 it feeds tenant agents' scope.
- **Not followed** means neither.
- **The level is computed.** A market is operating if its term is in the footprint, otherwise watching if a watch row exists, otherwise not followed.
- **Broad sweeps are untouched.** Platform runs never read either list.

Each fact is stored once. There is no separate Markets screen and no `MarketLevel` kind.

### 4.2 Prerequisite, built with chunk 3: jurisdiction as data the footprint can see

1. **EU reach is `Jurisdiction.parent`.**
   - The seed sets Norway's parent to the EU, with a comment naming the EEA Agreement, and the fixture's `parent_code` does the same.
   - The docstring becomes "the jurisdiction whose rules reach this one".
   - No new column and no migration.
2. **Mirror terms.**
   - `taxonomy_term.jurisdiction_id` is a nullable, unique foreign key.
   - `seed_reference` creates one term per jurisdiction in the jurisdiction dimension, with the same key and labels. The term's parent follows `Jurisdiction.parent`, and `active` is mirrored. A hand-made term with the same key is adopted.
   - A guard test checks that the mirror is exact in both directions.
   - Term proposals in any dimension whose terms mirror jurisdictions, and tagging a record with such a term, answer 422. This is decided from the data, not from a dimension key.
   - The chunk 4 console edit of a jurisdiction updates its term in the same transaction; this is a note in `CHUNK4_BRIEF.md`.
3. **Derived at match time, never stored.**
   - This lives inside chunk 3's single scope rule (`library/reading.py`).
   - A record carries the term of its jurisdiction plus the terms of every jurisdiction whose parent that is, so an EU record carries EU, SE, DK, FI and NO.
   - Obligations and instruments take their jurisdiction from `Instrument.jurisdiction`, which is required. Changes (chunk 5) take it from their authority. A change without an authority is not restricted by jurisdiction.
   - Nothing is written to `obligation_term` or `change_term`.
   - **The SQL function is unchanged.** The caller appends the derived term ids to the array it already passes. `CHUNK3_TASKS.md`'s "neither inherits a jurisdiction term" is reversed.

The result:
- A footprint of {Norway} shows Norwegian and EU law.
- A footprint of {Sweden} shows Swedish and EU law and hides Danish law.
- Footprint validation is unchanged for every dimension. There is no `parent_required` and no draft logic.
- Nothing is hidden until a tenant turns a jurisdiction on, because an empty dimension restricts nothing (FP-01).
- The EU chip stays, and it is harmless. Turning it off does not hide EU rules while a country they reach is on, and the preview shows zero hidden.

### 4.3 Watched markets
```
watched_market (TenantModel, forced RLS)
  id, tenant_id, jurisdiction_id FK PROTECT (library row), added_by NULL, added_at
  UNIQUE (tenant_id, jurisdiction_id)
```
- **What can be watched.** Only active country jurisdictions.
- **Precedence.** Footprint approval never writes watch rows. A market watched before it became operating reads as watched again once operating stops. A market that was never watched reads as not followed.

| | Operating | Watching | Not followed |
|---|---|---|---|
| Footprint | In it | Not in it | Not in it |
| Default views (FP-03) | Shown | Hidden | Hidden |
| "Markets we watch" (inventory in chunk 3, feed in chunk 5) | Not applicable | Shown, with the other dimensions still applied | No |
| Cases (CAS-01) | `footprint_match` true | false | false |
| Urgency, triage, notifications | Never set by market | Never | Never |
| Platform sweeps | Unchanged | Unchanged | Unchanged |
| Tenant agents (chunk 11) | Default scope, first | Default scope, with the remaining budget | Only if added to one agent |
| How it changes | Request, preview, second person, step-up | Direct write, audited | Direct write, audited |

**The lens.** A record is in it when it matches `F ∪ W` but not `F`. F is the footprint, and W is the watched countries' terms.
- EU records carry every country the EU reaches, so they match F and stay out of the lens.
- In SQL, with the function unchanged: `in_footprint(stored terms) AND NOT in_footprint(stored + derived) AND derived && W`.
- In Python: `in_footprint` with a merged footprint.
- With no jurisdiction in F, the lens is empty, because jurisdiction hides nothing in the first place.

### 4.4 API
- **`GET /tenant/footprint`** (unchanged gate: ungated `CAPABILITY`) gains `markets: MarketRow[]`, one per active country. `MarketRow` is `{jurisdiction{key,kind,label}, operating, watching}`.
- **`POST /tenant/footprint/watching`**, body `{jurisdiction}`, gated by `footprint.request`.
  - 201 when added.
  - 409 `already_watching`.
  - 422 `unknown_key` when the key is unknown, inactive or not a country.
- **`POST /tenant/footprint/watching/remove`**, body `{jurisdiction}`, gated by `footprint.request`. 204, or 404 when the market is not watched.
- **Why the key rides in the body.** It never goes in a path or a query string, because the gunicorn access log prints the request line and Sentry transactions keep `request.url`.
- **Audit.** `markets.watch_added` and `markets.watch_removed`, with keys only.
- **Operating markets** use the existing `POST /tenant/footprint/requests[?dryRun=true]`, unchanged.
- **One footprint filter.** Chunk 3's planned `outsideFootprint=true` becomes `footprint=in|all|watched` (default `in`) on `GET /instruments` and `GET /obligations` (chunk 3) and on `GET /changes` (chunk 5).
  - `all` is today's "Show outside footprint", which lists everything and marks what is outside (FP-S4).
  - List rows gain `jurisdiction{key,kind,label}`.
  - No contradictory pair of filters can be sent, so no 422 is needed.

### 4.5 Settings screen

The markets live on `/admin/footprint`, the existing Admin child. Its card is updated.
- **The Jurisdiction row is unchanged.** It shows five chips, which are the markets we operate in, edited through the existing FP-02 flow.
- **A new panel, "Markets we watch", below it:**
  - An intro line: the jurisdictions turned on above are the markets you operate in, and watching a market hides nothing.
  - One row per active country: the name, then either "Operating" as meta text or a Watching switch that saves at once.
- **"Also included"**, rendered from `parentKey`: EU rules show for every country they reach.
- **"Everywhere else"**: our research sweeps every source in the library for every market, whatever you choose here.
- **Without `footprint.request`**, the switches are read-only, with the page's existing notice.
- **Inventory (chunk 3) and watch feed (chunk 5).** A "Markets we watch" option sits beside "Show outside footprint". Rows in the lens show "Market we watch: Norway" as meta text. **No new pill.**
- **Screen text stays true slice by slice.** The panel names the watch feed only from chunk 5, and agents only from chunk 11. Strings come from the en and sv catalogs.

### 4.6 Agents
- **Before chunk 11.** No agent reads either list. Platform runs keep sweeping every covered jurisdiction, including the open-web sweep.
- **Chunk 11.**
  - At run start, the scheduler builds the scope `{operating, watching, alsoIncluded, topics, languages}` with the same precedence, and stores a copy on `agent_run`.
  - An explicit AGT-04 scope overrides it (AGT-S5).
  - A new watch-sweeper prompt version, published through AGT-S4, spends the budget on operating markets first.
  - The `tenant_agent.scope` default becomes "empty = follow the markets".
- **Platform runs.** The builder never reads tenant rows for a platform run (`tenant_id` NULL).

### 4.7 Confidentiality

A watched market can reveal expansion plans. Where it may and may not travel:
- It is tenant data under forced RLS, readable by every member of that tenant.
- It is written to audit and outbox rows as keys, so the tenant's own webhooks and SIEM stream receive it.
- It never goes in a URL, and never reaches logs, Sentry or platform runs.
- From chunk 11, its keys reach the tenant-scoped runner (D-07/D-08).
- The provenance of changes that a tenant run registers in the shared library could let platform staff infer who watches what. This is noted for D-08.

## 5. What can be built when

**Now (R1)**
- Every document: tasks T-01 to T-10.
- The markets work:
  - Norway's reach, mirror terms and the proposal refusal, before chunk 3's list routes;
  - the derived jurisdiction inside chunk 3's scope rule;
  - watched markets, their two routes and the panel on the Footprint screen;
  - seeds and isolation tests.

  They need chunk 2 (built) and chunk 3's data layer (on main).

**With chunk 3 and chunk 5**
- The lens on the inventory (chunk 3).
- A change's jurisdiction taken from its authority, and the lens on the feed (chunk 5).

**Chunk 8**
- Departments and teams.
- Participants on register entries.
- My work v1, with register entries, entity rows, internal items, gaps, duties and linked changes.
- Member removal.
- J-9.

**Chunk 9.** Case participants, contributors as team participants, and case and action sources.

**Chunk 10.** The notification recipient check, the three new kinds, review reminders, escalation to department heads, the digest, and the comments and mentions panel.

**Chunk 11.** Tenant agents' default scope.

All of Feature 1 needs something to own, which chunk 8 provides. Building the page earlier would mean pulling REG-02, TEN-02, TEN-03, CAS-02 and COL-01 forward.

## 6. Deferred, and why

- **Private notes.** Every role holds `audit.read`, `record()` stores before and after values, and the outbox feeds webhooks and the SIEM stream. This is open question 1.
- **Decisions on My work.** They are on Today's Decide now. They can come back as a reason if Alex asks.
- **A per-person strip, and footprint marking on My work.** Rows already name who is responsible, and My work does not filter by footprint.
- **Team leads (`team_member.is_lead`).** Departments have heads, and team notices go to the team's members.
- **Participant roles** (contributor, informed). Nothing depends on them yet.
- **"Affecting" by impact or by scope terms.** It needs the CAS-03 impact model. Involvement can be explained on every row.
- **Internal items of a department that no team member owns.**
- **"Since my last visit", snooze and read state.** SRC-04 and `user_item_state` are R3.
- **Follow (COL-03).** Stays R3, and then becomes one more reason on My work.
- **A delegate's "covering for" view.** TEN-04 covers approvals and reminders only.
- **Inline actions on My work.** Recording a review stays on the record page, with If-Match.
- **Markets beyond EU, SE, DK, NO and FI.** A platform scope change. This is open question 2.
- **A briefing section and alerts for watched markets**, and **the lens on the roadmap, briefing and reports.** No requirement asks for them, and watching must not create noise.
- **Suggesting markets from licences, markets per entity, need-to-know access to the watch list, and ranking by market.**

## 7. Ideas considered and not taken

- **A database view `v_involvement`.** Replaced by one ORM service.
- **One `tenant_market` table holding both levels.** It would store operating markets twice.
- **A separate `/admin/markets` screen.** Operating markets are the footprint's jurisdictions, which the Footprint screen already manages. A second screen would bring an extracted request component, a `managedByMarkets` flag, a `MarketLevel` kind, a second pending-request read and a new card.
- **`rules_reach_from` and `parent_required`.** `Jurisdiction.parent` already holds the link, and deriving the reach on the record side needs no validation or draft logic.
- **A hook in footprint approval that moves watch rows.** A computed level with precedence gives the same result without writing anything.
- **An `extra_term_ids` argument on the SQL function.** The caller already builds the array.
- **Keyset pagination, `MY_WORK_PAGE_SIZE`, `/reference/teams`, a `byPerson` strip, and ten work reasons.** The shared mechanisms already cover these.
- **Idempotent "200, nothing written" answers.** The audit guard fails them, and the codebase answers a duplicate with 409.
- **Watch routes with the key in the path.** It would reach the access log and Sentry.
- **Dropping reviews of compliant obligations and past dates from the roadmap view.** My work computes its own dates, and the roadmap stays as designed.
- **"Watched market" and "Overdue" pills.** Reasons and dates are meta text.
- **A 409 `case_required` for changes outside the footprint.** Every change has a case per tenant (CAS-S1).

## 8. Risks

- **Feature 1 gives nothing before R2.** Only reordering the build plan would change that.
- **Involvement, not impact.** A change that nobody attaches to a department's team or people will not show on its view.
- **Departments are built from teams.** A person in no team under a department does not appear on its view. TEN-02 grows to name departments.
- **Team notices reach every active member.** Notification preferences (designed) let people mute kinds.
- **Notes.** Shared comments may not be what Alex meant (open question 1).
- **Cross-tenant ids.** Composite keys, loading under RLS and the `TENANT_SCOPED_ROUTES` entries each need their own tests.
- **Performance.** A union over about ten sources, expanded to every department member, can breach 250 ms without the indexes and the pinned query count.
- **Operating hides everything else by default.** The preview, the lens and Show outside footprint soften it.
- **EU reach for Norway shows too much.** It includes EU acts not yet incorporated into the EEA Agreement. Applicability stays a human decision (REG-01).
- **The EU chip.** Turning it off does not hide EU rules while a country they reach is on. The preview shows zero hidden.
- **Mirror drift.** A migration that bypasses `seed_reference` could split jurisdictions from their terms. The guard test catches it.
- **One pending request.** A pending footprint request blocks operating-market edits.
- **Watching does little at first.** Its effects arrive with the chunk 3 lens, the chunk 5 feed and chunk 11. Screen text must stay true slice by slice.
- **The watch list is sensitive.** It reaches every member, audit rows, the outbox and, from chunk 11, the runner.
- **Tenant keys in paths already exist.** Tenant vocabulary keys in `/vocab/{list}/{key}` paths reach the access log today. This is not changed here; it is flagged for the chunk security review.
- **Changes to built or planned code.** The panel on `FootprintScreen` and the reversed chunk 3 scope decision risk regressions in FP-S1 to FP-S5, J-6 and chunk 3's footprint agreement test.
- **Process weight.**
  - PRD 0.3.
  - 17 decisions, 3 ADRs.
  - 27 new scenarios, and 5 existing ones amended (CAS-S4, COL-S2, COL-S4, TEN-S5, TEN-S7).
  - Design cards and INPUT_DELTAS rows.
  - All of these must land before code, or `requirements_coverage.py` refuses the new IDs.

---

# Appendix A. The PRD bump as drafted

# PRD bump: 0.3

`main` already holds 0.2 (sector scope, commit 7613874), so these rows make **0.3**. Writing 0.2 again would overwrite a recorded decision.

FP-01, FP-03 and I18N-01 are **not** changed. Chunk 2 carries a Tested date, and its app.md marks them built. The jurisdiction rule and the lens are written into the new FP-04 instead, so no tested chunk 2 requirement is reopened.

## Version log

| Version | Date | Change | Decided by |
|---|---|---|---|
| 0.3 | 2026-09-19 | **My work and participants:** a page of everything a person or their teams are responsible for or take part in, with next reviews and changes on those items, and the same view for a department's head; participants (people or teams) on register entries and cases, granting nothing; departments as org units with a head; notes as shared comments. **Markets:** each covered country is operating, watching or not followed; operating markets are the footprint's jurisdictions; watching hides nothing and steers tenant agents; EU rules reach every member country and Norway, as data; a record's jurisdiction comes from its instrument or authority | Alex |

## 3. Requirements: changed and new rows

### TEN: tenant and organisation (changed)

| ID | Requirement | P | R |
|---|---|---|---|
| TEN-02 | Legal entities with licences, **departments (business areas, units and functions) with a head and the teams in them**, and products described the way obligations are scoped | M | R2 |
| TEN-03 | Teams as owners **and participants**, so ownership survives a person leaving | **M** (was S) | R2 |

### FP: footprint (new)

| ID | Requirement | P | R |
|---|---|---|---|
| **FP-04** | Markets: each covered country is operating, watching or not followed. **Operating** markets are the footprint's jurisdictions and change only as FP-02 does. A record's jurisdiction comes from its instrument or its authority, and EU rules reach every member country and Norway (EEA Agreement), recorded as data. A record without a jurisdiction is not restricted by it. **Watching** is a direct, audited setting that hides nothing, never sets urgency or opens triage, and adds a view on the inventory and the watch feed showing what the watched markets add. Library research sweeps every covered market, whatever a tenant chooses | M | R1 |

### CAS: case workflow (changed)

| ID | Requirement | P | R |
|---|---|---|---|
| CAS-03 | Impact assessment: applies, why, what must change, internal deadline, effort, and **contributor teams, recorded as the case's team participants** | M | R2 |

### HOM: home, briefing, roadmap (new)

| ID | Requirement | P | R |
|---|---|---|---|
| **HOM-05** | My work: everything a person or their teams are responsible for or take part in, grouped as overdue, due soon, changes on those items, and the rest. Next reviews are included, also for compliant obligations, per legal entity and for internal items, and each item says why it is there. A department's head sees the same view for the department, naming who is responsible. Every item and count respects the reader's permissions, and the footprint never hides a person's own items. Decisions stay on Today | M | R2 |

### COL: collaboration (changed, new)

| ID | Requirement | P | R |
|---|---|---|---|
| COL-01 | Comments and mentions on any record, **and a person's own comments and mentions listed on My work, limited to records they can read** | S | R2 |
| COL-02 | Notifications, reminders before due dates **including next reviews**, **notice to the people responsible and taking part when a change is linked to their obligation or a new version applies**, escalation **to the head of the owner's department** after a threshold, a weekly digest in the user's language. **A notification reaches only active members who can read its record, once per event** | M | R2 |
| **COL-04** | Participants: people or teams added to a register entry or a case by someone who can edit it. Participation lists and notifies, grants no access, and a participant can leave. Unlike following (COL-03), which a person does alone on library records, participation is on the tenant's own records | M | R2 |

### AGT: agents (changed)

| ID | Requirement | P | R |
|---|---|---|---|
| AGT-04 | Tenant controls: on and off, cadence, scope (**by default the operating markets first, then the watched ones**), run now, pause, interrupt, history with findings and cost, monthly budget cap, AI off switch | M | R2 |

### ADM (changed)

| ID | Requirement | P | R |
|---|---|---|---|
| ADM-01 | Tenant admin: organisation **with departments and teams**, members and invitations **with team membership**, passkey re-enrolment, sessions, roles, footprint **with markets**, vocabularies, workflow policy, agents, integrations, security policy, data, audit log | M | R1 to R3, following the features |

## 4. Acceptance criteria (new)

- **AC-FP2: markets.**
  - Turning Denmark on in the footprint's jurisdictions previews the change and waits for a second person with step-up, and EU rules keep showing with Denmark.
  - Operating in Norway alone shows EU rules too.
  - Watching Norway is one audited write that changes no default view, and no market key appears in a URL.
- **AC-HOM1: My work.**
  - An owner's compliant obligation with a review in 20 days is under "Due soon".
  - An item they own outside the footprint is listed.
  - A role without `register.read` gets no obligation rows or counts and a permission-limited notice, never a page-level 403.
- **AC-COL1: participants.**
  - A participant still receives 403 on writes their role lacks.
  - Tenant B adding a participant to tenant A's private record, or removing A's participant, gets 404. On a shared record, B's add lands on B's own entry.
  - A user of another tenant gets 422 `unknown_member`.
  - A member who cannot read the record gets 422 `participant_cannot_read`.

## 5. Golden-path journeys

| ID | Path |
|---|---|
| J-8 (changed) | Tenant B cannot see tenant A's case, evidence, comments, **participants, watched markets** or configuration |
| **J-9** (new) | Monday morning: (1) the owner opens My work and sees an overdue review and a change linked to an obligation they are responsible for; (2) they add a contributor as participant on that obligation; (3) the contributor sees it on their own My work; (4) the department head's view shows it with the owner named; (5) the contributor leaves, and both events are in the audit log |

## 6. Permissions and system roles

**No new permission constant.** Only descriptions change; grants are unchanged.

| Permission | Admin | Compliance officer | Owner | Approver | Contributor | Reader | Auditor |
|---|---|---|---|---|---|---|---|
| `footprint.request` (ask for a footprint change, **including the markets we operate in; set the markets we watch**) | x | x | | | | | |
| `cases.contribute` (save assessment input, update actions, add evidence, **add or remove case participants**) | | x | x | | x | | |
| `register.edit`, `gaps.edit` (`register.edit` **includes adding or removing participants on a register entry**) | | x | x | | | | |
| `members.manage`, `roles.manage`, `security.manage` (`members.manage` **includes team membership**) | x | | | | | | |
| `vocab.manage`, `workflow.manage` (`vocab.manage` **includes departments, their heads and teams**) | x | x | | | | | |

**Actions that need membership only:**
- Viewing My work, your own or any department's. Each item still needs its read permission; the department view is a filter, not a grant.
- Leaving your own participation.

## 7. Release plan (changed wording)

| Release | Outcome | Build plan chunks |
|---|---|---|
| R1 | Sign in with a passkey, set the footprint **and the markets**, browse the inventory with versions and diffs, follow the watch feed fed by agents, search and ask, the timeline home, briefing and roadmap, vocabularies managed without a deploy, audit from day one | 0 to 7 |
| R2 | The system of record: applicability, compliance status per entity, gaps, the full case workflow, **My work and participants, departments and teams**, collaboration, tenant-controlled agents | 8 to 11 |

## Rows that change in the same commit

- **`backend/apps/home/app.md`** gains HOM-05.
- **`backend/apps/collab/app.md`** gains COL-04, plus the COL-01 and COL-02 wording.
- **`backend/apps/taxonomy/app.md`** gains FP-04.
- **`backend/apps/tenants/app.md`** takes the TEN-02 and TEN-03 wording and priority.
- **`backend/apps/cases/app.md`** takes the CAS-03 wording.
- **`backend/apps/agents/app.md`** takes the AGT-04 wording.
- **`Build_Plan.md`:**
  - Chunk 3 gains FP-04, and chunk 5 its feed part.
  - Chunk 8 gains HOM-05 and COL-04. They are listed above the cuttable Should items (REG-04, REG-07, VOC-04 to VOC-06), with TEN-02 and TEN-03 also above them.
  - Chunk 9 gains COL-04 on cases.
  - Chunk 10 gains HOM-05 comments, and COL-01 stays first there.
  - Chunk 11 gains the AGT-04 default scope.
- **Coverage.** `backend/scripts/requirements_coverage.py` passes on this commit.


# Appendix B. Decisions as drafted

## D-18: What a participant is

**Default:** A tenant-zone row naming a person or a team on a register entry (tenant_obligation) or a case (change_case). It has composite (tenant_id, ...) foreign keys to the entry, the case, the team and membership, so the database refuses another tenant's row or a user who is not a member. It is removed softly (removed_at, removed_by). It puts the item on My work and in notifications and grants no access. Adding someone who is already there answers 409 already_participant. There is no participant-role vocabulary.

**Why:** Everything Alex asked for is attention, not access. PostgreSQL foreign-key checks bypass RLS, so only composite keys (membership_tenant_user_unique already exists) make a cross-tenant or non-member row impossible. Soft removal keeps who took part for the case file (CAS-07) and history (REG-04). The audit guard fails a 2xx write without an audit row, so a duplicate is a 409, as already_member is.

**Owner confirms:** That participation never grants access, and that participant roles can wait until something depends on them.

## D-19: Who adds and removes participants

**Default:** Adding needs register.edit on a register entry and cases.contribute on a case. Removing needs the same permission, except that a person may always remove their own row (Leave). A person whose roles cannot read the record is refused with 422 participant_cannot_read. A team is not checked, because each member's own read permission filters what they see and receive. If a role later loses read permission, the participation stays and the item comes back to that person as permission-limited. A record holds at most 50 participants (MAX_PARTICIPANTS_PER_RECORD). No new permission.

**Why:** It reuses the people who already edit the record or save assessment input, keeps the PRD §6 matrix unchanged, and prevents adding someone to a record they cannot open.

**Owner confirms:** Whether Contributors should also add participants to register entries (a new permission and a PRD §6 change), and that a participation outlives a lost read permission.

## D-20: CAS-03 contributors

**Default:** The assessment's contributor teams are the case's team participants. Each change is sent as a single add or remove call, never as a replacement of the whole list. impact_assessment gets no contributors column. CAS-S4 is amended, and an INPUT_DELTAS §1 row replaces 'a vocabulary of teams or functions'.

**Why:** One list of who is involved instead of two. Single calls mean a stale assessment form cannot remove a team that someone added in between. That would be the silent merge CAS-08 forbids, and it needs no version on the assessment.

**Owner confirms:** That merging them is acceptable. The fallback is two separate lists.

## D-21: Department and department head

**Default:** A department is the designed org_unit of kind business_area, business_unit or function. Its head is org_unit.head_user_id, and teams belong to it through team.org_unit_id. The department view covers the teams of that unit and of the units below it, and their active members. Any member may open any department's view, because it is a filter, not a grant. COL-S2's 'owner's manager' is the head of the department of the owner's teams. team_member.is_lead is not built (an INPUT_DELTAS row).

**Why:** The designed schema already has departments with heads above teams (schema.sql:941, 1219-1232). The earlier reading that org units are only legal entities was wrong. Using that model avoids a second 'head' concept, and a department of several teams becomes one view instead of a lead flag on every team. Nothing would read is_lead once heads sit on the unit and team notices go to members.

**Owner confirms:** That a department is an org unit with a head (TEN-02 grows to name departments), that team leads are not needed, and that impact-based 'affecting' can wait.

## D-22: Notes on my work

**Default:** Notes are shared COL-01 comments. On My work they sit in a panel named 'Comments and mentions', never 'Notes', and its composer says that everyone in the organisation can read them. GET /me/comments returns only comments on records the reader can read, and lists the other kinds as permission-limited. Comment text never reaches logs, Sentry, audit after values, outbox payloads, webhooks, notification titles or emails. Private notes are not built.

**Why:** Every role holds audit.read, record() stores before and after values, and the outbox feeds webhooks and the SIEM stream. The word 'Notes' on a personal page suggests privacy. comments.write is held by everyone, so without the per-subject filter a person mentioned on a case they cannot read would receive its text.

**Owner confirms:** See open question 1: whether private notes are wanted at all.

## D-23: How My work is computed and exposed

**Default:** One ORM service under RLS, backend/apps/home/my_work.py, with no database view.
- Reasons are owner and participant. who names the person or team; via names the obligation for a linked change.
- Buckets are overdue, due soon, changes on your items, and everything else.
- Rows and every count come from the permission-filtered set.
- GET /me/work uses PageQuery (limit and offset) with an optional bucket filter, and returns counts per bucket.
- Decisions stay on Today's Decide now, fed by the queue counts on GET /me; My work links there.
- The page, the reminders, the digest and the TEN-05 preview all read the same service.

**Why:** 'My open items' gets one definition. It avoids the codebase's first view and uses the shared pagination. It keeps decisions in one place. Four phrases need only two reasons. Counts taken before filtering would tell a role without cases.read how many overdue cases colleagues have.

**Owner confirms:** That decisions stay on Today and are not repeated on My work.

## D-24: My work and the footprint

**Default:** My work does not apply the footprint and marks nothing as outside it.

**Why:** FP-03 names the feed, inventory, roadmap, briefing and reports. Losing sight of your own responsibility after a footprint change is worse than seeing it. With no filter, a marker and a 'Show outside footprint' link have nothing to reveal.

**Owner confirms:** That My work is exempt from FP-03 hiding.

## D-25: What counts as 'changes on your items'

**Default:** Open cases whose change has a WAT-04 link, confirmed by a person, to an obligation you are involved in, carrying that obligation as via. Also obligation versions applied in the last 14 days (MY_WORK_AWARE_DAYS). From chunk 10, comments and mentions on your items are added. Links that agents suggested and nobody confirmed are left out, and so are your own acts. SRC-04's 'since my last visit' replaces the window in R3.

**Why:** Agents propose and people decide. A fixed window needs no write on every page load, and it does not clash with last_visit_at, which Library updates uses.

**Owner confirms:** The 14-day window.

## D-26: When Feature 1 lands and its priority

**Default:** With chunks 8, 9 and 10 (R2); nothing is pulled forward. HOM-05 and COL-04 are Must. TEN-03 rises from Should to Must, because HOM-05's department view is built from teams. The descope rule cuts from the bottom of a chunk's requirement list, not by priority. Build_Plan therefore lists HOM-05, COL-04, TEN-02 and TEN-03 in chunk 8 above the cuttable items (REG-04, REG-07, VOC-04 to VOC-06), and COL-01 stays first in chunk 10.

**Why:** Nothing a person can own exists before chunk 8. Priority alone protects nothing under the cut rule; the order of the list does.

**Owner confirms:** Keep R1 as planned, or reorder the build plan to bring chunk 8 forward.

## D-27: What a market is and where it is set

**Default:** Operating markets are the footprint's jurisdiction terms. They are set on the Footprint screen's Jurisdiction row through FP-02 (preview, second person, step-up). Watched markets are a separate tenant list, watched_market, set in a 'Markets we watch' panel on the same screen. A market's level is computed: operating if its term is in the footprint, otherwise watching if a watch row exists, otherwise not followed. There is no separate Markets screen and no MarketLevel kind.

**Why:** Each fact is stored once, and four eyes stays on everything that hides records. The Footprint screen already manages the operating markets. A second screen would need an extracted request component, a managedByMarkets flag and a second pending-request read.

**Owner confirms:** That 'extra attention' means the default view, and that markets belong on the Footprint screen rather than on a screen of their own.

## D-28: How EU rules reach a country

**Default:** Jurisdiction.parent means 'the jurisdiction whose rules reach this one'. The seed and the fixture set Norway's parent to the EU (EEA Agreement), as SE, DK and FI already are. A record's derived terms are the term of its jurisdiction plus the terms of every jurisdiction whose parent that is, so an EU record carries EU, SE, DK, FI and NO. There is no parent_required rule, no draft logic and no new column.

**Why:** A bank operating only in Norway would otherwise hide all EU law. The column already exists, and nothing but GET /reference/jurisdictions reads it. Derivation on the record side keeps footprint validation unchanged for every dimension.

**Owner confirms:** That Norway will also show EU acts not yet incorporated into the EEA Agreement (applicability stays a human decision, REG-01), and that turning off the EU chip does not hide EU rules while a country they reach is on.

## D-29: Where a record's jurisdiction comes from

**Default:** It is derived at match time inside chunk 3's single scope rule (library/reading.py). Obligations and instruments take it from Instrument.jurisdiction, which is required. Changes (chunk 5) take it from their authority. The terms used mirror the jurisdiction rows (taxonomy_term.jurisdiction_id).
- It is never stored in obligation_term or change_term.
- Term proposals and tagging in that dimension answer 422.
- The SQL function taxonomy_in_footprint is unchanged: the caller appends the derived ids to the array it already passes.
- A change without an authority is not restricted by jurisdiction.
- CHUNK3_TASKS' decision that 'neither inherits a jurisdiction term' is reversed.

**Why:** The foreign key the library already has stays the only source. Showing too much is the safe side. A second array argument would mean a migration of built code for nothing.

**Owner confirms:** Nothing.

## D-30: How watching is protected and who sees it

**Default:** Watching is a direct write under footprint.request, audited through record(), with no second person and no step-up. Adding a watched market twice answers 409 already_watching. Every member of the tenant can read the list. It never hides or reveals anything by default, sets urgency, opens triage or notifies anyone. The jurisdiction key travels only in request bodies and responses, never in a URL path or query string.

**Why:** Four eyes guards changes that hide records, and watching hides nothing. The gunicorn access log prints the full request line, and Sentry transactions keep request.url, so a key in the path would leak a possible expansion plan.

**Owner confirms:** That watching needs no second person, and that every member may read the list even though it may reveal expansion plans.

## D-31: How a market's level behaves when operating changes

**Default:** Footprint approval never writes watch rows. A market watched before it became operating reads as watched again once operating stops. A market that was never watched reads as not followed once operating stops. The preview's hide count shows what disappears.

**Why:** A computed level with precedence needs no hook in the approval transaction, no watchChanges field and no already_operating error. Attention is kept wherever someone asked for it.

**Owner confirms:** That a market you never watched simply drops to not followed when you stop operating there.

## D-32: Markets and research

**Default:** Platform (library) runs never read tenant markets, so broad sweeps are unchanged. From chunk 11, a tenant agent's default scope is the operating markets first, then the watched ones, using the same precedence and whatever budget remains. A copy of the scope is stored on agent_run at run start, and an explicit AGT-04 scope overrides it. Jurisdiction keys may reach the tenant-scoped runner, but tenant text never does.

**Why:** The two-zone rule. A tenant's expansion plans must not steer or leak through the shared library.

**Owner confirms:** Confirm together with D-07 and D-08 before chunk 11.

## D-33: Which markets can be chosen

**Default:** Only active jurisdictions the platform covers: EU, SE, DK, NO and FI today, and only countries can be watched. Any other market is a change to the platform's scope, not a tenant setting.

**Why:** PRD §1 and I18N-01 limit scope to the Nordics plus the EU. A new market needs authorities, sources and a content language first.

**Owner confirms:** See open question 2.

## D-34: Who receives a notification

**Default:** One recipient check serves every notification kind, mentions included. It picks active members whose roles can read the record's kind at send time, and sends one notification per person per event, whatever the number of reasons. A team named on a record reaches its active members. TEN-05 removal also ends the member's team memberships.

**Why:** Without it, a removed member would keep receiving library titles and links about the bank's work through team rows, and so would a person who lost read permission. One check replaces one per kind.

**Owner confirms:** That team notices go to every active member, who can mute kinds in notification preferences, rather than to team leads.

# Appendix C. Scenarios as drafted

App `home`:

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

App `home`:

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

App `home`:

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

App `home`:

### HOM-S10 — My work applies each record's read permission to rows and counts, and ignores the footprint `@integration` (HOM-05, AC-HOM1)

```gherkin
Given Erik was added as a participant to an obligation while his role held register.read
And an admin then removed register.read from that role
When Erik opens My work
Then no obligation row is returned and every count excludes it
And the response lists obligations as permission-limited, and the page says so instead of "Nothing to do"
And his participation still exists
Given Anna owns an obligation scoped to "Advice" and the footprint excludes "Advice"
When Anna opens My work
Then the obligation is listed like any other
```

App `home`:

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

App `home`:

### HOM-S12 — My work answers within budget for a fifty-member department `@integration` (HOM-05, NFR-02)

```gherkin
Given a department of fifty members across its teams, with seeded obligations, entity rows, internal items, gaps, duties and participants
When the department view of My work is read
Then it runs the same number of queries whatever the number of items
And it answers within 250 ms
```

App `home`:

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

App `home`:

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

App `collab`:

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

App `collab`:

### COL-S7 — A participant leaves a register entry on their own `@integration` `@e2e` (COL-04)

```gherkin
Given Erik, a Reader, takes part in an obligation
When he chooses "Leave"
Then his participation ends with its removal time and remover recorded, and the audit event is "participant.left"
And the obligation's history still shows that Erik took part until he left
When Erik tries to remove another participant
Then the answer is 403
```

App `collab`:

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
When a register entry already has 50 participants
Then the next add answers 422 with code "too_many_participants"
And the database refuses a participant row whose user, team or register entry belongs to another tenant
```

App `collab`:

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

App `collab`:

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

App `collab`:

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

App `collab`:

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
Then it appears on Anna's My work under "Changes on your items" for 14 days
And the application log, the audit after value and the outbox payload for these requests hold ids and never the comment text
```

App `collab`:

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

App `collab`:

### COL-S4 — A user follows a record and hears about changes `@integration` `@e2e` (COL-03)

```gherkin
Given a user follows an obligation
When a new version is applied to it
Then the user is notified
And a person who both follows the obligation and takes part in it receives one notification
When they unfollow it
Then the next change sends nothing
```

App `cases`:

### CAS-S4 — The impact assessment records what applies and what must change `@integration` `@e2e` (CAS-03)

```gherkin
Given an assigned case and its owner with cases.work
When they choose "Start assessment" and save applies, why, what must change, an internal deadline and an effort size, and add two contributor teams
Then the case moves to assessing and the assessment stores each field with a key for effort
And the two contributor teams are the case's team participants
When they save without a why
Then the request answers 422
```

App `cases`:

### CAS-S17 — Contributor teams are the case's team participants `@integration` (CAS-03, COL-04)

```gherkin
Given an assigned case and its owner with cases.work
When they add the contributor teams "Legal" and "Retail compliance" on the assessment
Then two team participants exist on the case, each added by its own call, and the assessment stores no separate contributor list
Given Erik added the team "Cards" to the case after the owner loaded the assessment
When the owner removes "Legal" and saves the assessment
Then "Cards" is still a participant, because contributor changes are single adds and removals, never a list replacement
And the case file shows that "Legal" took part until it was removed
```

App `tenants`:

### TEN-S8 — A department has a head and teams, and team membership is set on the member row `@integration` `@e2e` (TEN-02, TEN-03)

```gherkin
Given an admin with vocab.manage
When they add the department "Retail Banking" with Karin as head and the team "Retail compliance" in it
Then GET /me for Karin lists "Retail Banking" among the departments she heads
Given an admin with members.manage
When they put Anna and Johan in "Retail compliance"
Then one audit event is written per call, holding the team keys before and after
When they put a user who is a member only of another tenant in the team
Then the answer is 422 with code "unknown_member"
And the database refuses a team membership, a team's department or a department head that belongs to another tenant
Given a person without members.manage
When they change a member's teams
Then the answer is 403
```

App `tenants`:

### TEN-S9 — Removing a member ends their participations and team memberships `@integration` (TEN-05, COL-04)

```gherkin
Given Erik owns one obligation, takes part in three items and is in the teams "Legal" and "Cards"
When an admin opens his removal
Then the screen lists what he owns by kind, "Takes part in 3 items" and his two teams
And nothing changes until the admin confirms
When the admin confirms with a new owner for the obligation
Then the obligation is reassigned, his three participations and two team memberships end, and he is removed, in one transaction
And one audit event is written per item
And the participations of his teams are unchanged
```

App `tenants`:

### TEN-S7 — J-8: tenant B cannot see tenant A `@e2e` (TEN-06, COL-04, J-8)

```gherkin
Given seeded tenants A and B, a case with evidence, comments and a participant in A, and A watching Norway
When B's compliance officer signs in and opens A's case URL, evidence URL and vocabulary screen
Then each answers 404 and the UI shows "Not found", never the data and never a 403
When B opens the participants of a shared obligation on which A has participants
Then B sees only its own participants
And B's Footprint screen shows no market that A watches
And B's lists show only B's records
```

App `taxonomy`:

### FP-S6 — Turning on a country brings the EU rules that reach it `@integration` `@e2e` (FP-04, AC-FP2)

```gherkin
Given a tenant whose footprint has no jurisdiction, and obligations from EU, Swedish, Danish and Norwegian instruments
And a compliance officer with footprint.request
When they turn on Denmark in the footprint's jurisdictions and choose "Preview"
Then the preview says that the Swedish and Norwegian obligations will be hidden, and hides no EU obligation
When they send it for approval and an approver with footprint.approve and a fresh step-up approves it
Then the request held Denmark only
And the inventory lists the EU and Danish obligations and no Swedish or Norwegian one
And one audit event and one history row are written for the term
```

App `taxonomy`:

### FP-S7 — A record's jurisdiction comes from its instrument, and EU rules reach every member country and Norway `@integration` (FP-04, AC-FP2)

```gherkin
Given a footprint whose only jurisdiction is Norway
And one obligation each from an EU, a Norwegian and a Swedish instrument
Then the EU and Norwegian obligations match and the Swedish one does not
And no jurisdiction term is stored for any of them
When a proposal would tag an obligation with a jurisdiction term
Then applying it answers 422
And the SQL function, called unchanged, and the Python rule give the same answers
And the code that decides this names no country and no dimension
```

App `taxonomy`:

### FP-S8 — Watching a market is one audited write that hides nothing `@integration` `@e2e` (FP-04, AC-FP2)

```gherkin
Given a tenant operating in Sweden and an admin with footprint.request
When they switch on "Watching" for Norway
Then one watched market row and one audit event "markets.watch_added" holding the key only are written, with no second person and no step-up
And the footprint and every default view are unchanged
When Norway is watched again through the API
Then the answer is 409 with code "already_watching"
When they switch "Watching" off for Norway
Then the row is removed and the audit event is "markets.watch_removed"
Given a Reader
When they read the footprint
Then they see which markets are operating and which are watched
And watching one answers 403 with requiredPermission "footprint.request"
```

App `taxonomy`:

### FP-S9 — A market's level is computed, and operating comes first `@integration` (FP-04)

```gherkin
Given a tenant operating in Sweden and watching Norway
When a request to operate in Norway is approved
Then Norway reads as operating, its watch row is untouched, and no watch event is written
When a request to stop operating in Norway is approved
Then Norway reads as watching again
Given Finland was never watched
When a request to operate in Finland is approved and later reversed
Then Finland reads as not followed
```

App `taxonomy`:

### FP-S10 — Jurisdiction terms mirror the jurisdiction rows and cannot be proposed `@integration` (FP-04)

```gherkin
Given the seeded jurisdictions EU, Sweden, Denmark, Norway and Finland
Then the jurisdiction dimension holds exactly one term per active jurisdiction, with the same key and labels
And each country's term has the EU's term as parent, Norway's included
And GET /tenant/footprint lists five jurisdiction terms
When a proposal adds or renames a term in the jurisdiction dimension
Then it answers 422
When seed_reference runs a second time
Then nothing changes
```

App `taxonomy`:

### FP-S11 — The watched-market view of the inventory shows only what watching adds `@integration` `@e2e` (FP-04)

```gherkin
Given a tenant operating in Sweden with the service "Custody" and watching Denmark
And Danish obligations scoped to "Custody" and to "Advice"
When a user chooses "Markets we watch" in the inventory
Then the Danish "Custody" obligation is listed with "Market we watch: Denmark"
And the Danish "Advice" obligation is absent, because the other dimensions still apply
And no EU or Swedish obligation is listed, because they are already in the footprint
And the list takes one footprint filter value, so no contradictory pair can be sent
```

App `taxonomy`:

### FP-S12 — Markets stay inside the tenant and out of logs and error reports `@integration` (FP-04, NFR-01, AC-NFR1)

```gherkin
Given tenant A watches Norway and tenant B watches nothing
When tenant B reads its footprint
Then Norway is not watched and no id of tenant A's rows is returned
When tenant B asks to stop watching Norway
Then the answer is 404 and tenant A's row is unchanged
When tenant A watches and stops watching a market
Then the request line that the access log prints, the application log and the captured error-reporting transaction hold no jurisdiction key
```

App `taxonomy`:

### FP-S13 — A change's jurisdiction comes from its authority, and the watch feed has the watched-market view `@integration` `@e2e` (FP-04)

```gherkin
Given a footprint whose only jurisdiction is Sweden
And changes from a Danish authority, from an EU authority and with no authority
Then the Danish change does not match, the EU change matches, and the change with no authority matches, because a missing jurisdiction never hides a record
Given the tenant watches Denmark and has the service "Custody"
When a user chooses "Markets we watch" in the watch feed
Then the Danish "Custody" change is listed with "Market we watch: Denmark"
And its case gets no urgency from the market and nobody is notified
```

App `agents`:

### AGT-S11 — A tenant agent's default scope is the operating markets first, then the watched ones `@integration` (AGT-04)

```gherkin
Given a tenant operating in Sweden and watching Norway, and a tenant agent with no scope of its own
When a run starts
Then the run's stored scope lists Sweden as operating, Norway as watching and the EU as reaching them, in that order
And later market changes do not alter that run's scope
When an admin with agents.manage restricts the agent's scope to Sweden and Finland
Then the next run's scope is Sweden and Finland only
When a platform library run starts
Then its scope contains no tenant's markets and every covered jurisdiction is swept
```

# Appendix D. Placement

| Part | Chunk | Depends on | Why |
|---|---|---|---|
| Documents: PRD 0.3, DECISIONS D-18 to D-34, three ADRs, INPUT_DELTAS rows, app.md rows and scenarios (new and amended) with skipped stubs, Build_Plan, UI plan, CHUNK3_TASKS and CHUNK4_BRIEF edits, IMPLEMENTATION_STATUS | Now, before any code | Alex accepting the PRD bump (the version log says 'decided by Alex') | requirements_coverage.py refuses IDs the PRD does not know, and every new ID needs a scenario, a test stub and an @e2e stub. CHUNK3_TASKS must reverse its 'no jurisdiction term' decision before chunk 3's read tasks start. |
| Design cards: 'Markets we watch' panel on admin-footprint.html; the 'Markets we watch' option on tenant-inventory.html and tenant-watch.html | Now | The documents; the Green MCP server for tokens and components | Playbook 7 requires a card before a screen. The markets panel is the only screen work that can be built in R1. |
| Norway's reach (seed and fixture), mirror terms (taxonomy_term.jurisdiction_id), and the refusal of proposals and tagging in the mirrored dimension | Now, before chunk 3's list routes (chunk3-rest-T4) | Chunk 2 (built) and chunk 3's data layer (on main) | The jurisdiction dimension has no terms, so it restricts nothing and the Footprint card's chips are empty. Chunk 3's list queries should see the mirror terms from their first version. |
| Derived jurisdiction inside chunk 3's single scope rule (library/reading.py and its SQL twin), with the SQL function unchanged | 3, inside the scope rule's first version | The mirror terms; chunk3-rest-T4 (library/reading.py) | A record's jurisdiction must come from its instrument before any list surface applies the footprint. The rule is planned to live in one place. |
| Watched markets: watched_market model, markets logic, markets on GET /tenant/footprint, the two POST watching routes, the panel on the Footprint screen, seeds, isolation and log tests | Now (R1), within chunk 3's window | The mirror terms and the admin-footprint card | It needs no chunk 3 route. It sits on the existing Footprint screen and route, so the FP-02 flow stays as built. |
| The watched-market view on the inventory (footprint=in|all|watched, jurisdiction on list rows) | 3 | Chunk 3's GET /instruments and GET /obligations routes and the inventory screen | The view is a value of those lists' footprint filter and cannot exist before them. |
| A change's jurisdiction from its authority, and the view in the watch feed | 5 | regulatory_change with authority_id (WAT-01 to WAT-03) and CAS-01 cases | Changes do not exist before chunk 5. |
| Today's Decide now reads the queue counts on GET /me instead of /me/work; /me/work moves to the My work screen in the UI plan | 6 | The chunk 6 Today work | The designed MyWork fed Decide now; decisions stay on Today while /me/work becomes the My work page from chunk 8. |
| Departments (org units with a head), teams in them, team membership with composite keys, GET /me headOf, GET /reference/people | 8 | TEN-02 org units and TEN-03 team rows in chunk 8 | The department view and team participants need departments and teams. The chunk 8 owner pickers need the same people reference read. |
| participant table, obligation participant routes, the participants panel on the obligation page, TEN-05 removal ending participations and team memberships | 8 | tenant_obligation and ensure_register_entry (REG-02), team (TEN-03), change_case with UNIQUE (tenant_id, id) (chunk 5) | A participant hangs on tenant rows only, and the register entry first exists in chunk 8. It cannot be built earlier. |
| My work v1: register, entity-row, internal-item, gap and duty sources, department expansion, buckets, date rules, the 'changes on your items' bucket, GET /me/work, the /work screen, J-9 | 8 | REG-02 owners and per-entity next review, REG-03 gaps, REG-05 internal items, REG-07 duties, WAT-04 confirmed links (chunk 5), obligation versions (chunks 3 and 4) | Before chunk 8 nothing can be owned, so the page would be empty. It cannot be built earlier without pulling REG-02, TEN-02 and TEN-03 forward. |
| Case participants, contributor teams as participants (CAS-S4 amended, CAS-S17), case and action sources in My work, J-8's participant steps | 9 | CAS-02 to CAS-06 (owner, assessment, actions, sign-off) | Case owners, assessments and actions exist only from chunk 9. It cannot be built earlier. |
| The notification recipient check, participant_added, involved_item_changed and review_due, escalation to department heads, the digest on the My work service, GET /me/comments and the 'Comments and mentions' panel | 10 | COL-01 comments and COL-02 notifications | Comments and notifications do not exist before chunk 10. It cannot be built earlier. |
| Tenant agent default scope from markets with precedence, the scope copy stored on agent_run, a prompt version ordering the budget | 11 | AGT-04, AGT-06 and D-08 (runner) | Tenant agents do not exist before chunk 11. Until then, broad platform sweeps are the only research. It cannot be built earlier. |
| REP-01 load per owner on the My work service, follow as a reason (with the follower de-duplication in COL-S4), 'since my last visit', attestations due | 12 and 13 (R3) | REP-01, COL-03, SRC-04, REG-06 | These are R3 requirements. Each becomes one more source or reason in the same service. |

# Appendix E. Tasks

## T-01: Bump the PRD to 0.3

**Depends on:** nothing

Add the 0.3 version row. Change TEN-02, TEN-03 (to Must), CAS-03, COL-01, COL-02, AGT-04 and ADM-01. Add FP-04, HOM-05 and COL-04, and AC-FP2, AC-HOM1 and AC-COL1. Change J-8 and add J-9. Change the permission descriptions and the release plan wording. Leave FP-01, FP-03 and I18N-01 unchanged. All as in the PRD bump.

**Owned paths:** `PRD.md`

**Done when:** PRD.md holds every row of the bump verbatim. It is committed together with T-02 to T-05, and python backend/scripts/requirements_coverage.py passes on that commit.

## T-02: Add HOM-05 and its scenarios to the home app

**Depends on:** T-01

Add the HOM-05 row (status pending) and the scenarios HOM-S7 to HOM-S14. Add one skipped test per @integration scenario, and one test.fixme per @e2e scenario (HOM-S7, HOM-S9, HOM-S13).

**Owned paths:** `backend/apps/home/app.md`, `backend/apps/home/tests_scenarios.py`, `frontend/tests/e2e/home.journey.spec.ts`

**Done when:** The app.md text matches the analysis. test_hom_s7 to test_hom_s12 and test_hom_s14 exist, each skipped with its reason. The @e2e stubs carry their scenario IDs. The coverage script passes.

## T-03: Add COL-04, the COL wording and the CAS-03 changes to the collab and cases apps

**Depends on:** T-01

Add the COL-04 row and the COL-01 and COL-02 wording. Add COL-S6 to COL-S12, and amend COL-S2 (escalation to the department head; digest from My work) and COL-S4 (one notice for a follower who also takes part). Add the CAS-03 wording, amend CAS-S4 so contributor teams are team participants, and add CAS-S17. Add skipped stubs.

**Owned paths:** `backend/apps/collab/app.md`, `backend/apps/collab/tests_scenarios.py`, `backend/apps/cases/app.md`, `backend/apps/cases/tests_scenarios.py`, `frontend/tests/e2e/collab.journey.spec.ts`

**Done when:** The rows and the new and amended scenarios are present verbatim, the new stubs are skipped with a reason, and the coverage script passes.

## T-04: Add the department and team wording and scenarios to the tenants app

**Depends on:** T-01

Change the TEN-02 and TEN-03 wording and the TEN-03 priority. Add TEN-S8 and TEN-S9. Amend TEN-S7 (J-8) with the participant and watched-market steps and add COL-04 to its refs. Add stubs.

**Owned paths:** `backend/apps/tenants/app.md`, `backend/apps/tenants/tests_scenarios.py`, `frontend/tests/e2e/tenants.journey.spec.ts`

**Done when:** The scenarios are present verbatim, the new stubs are skipped, and the coverage script passes.

## T-05: Add FP-04 and the AGT-04 change to the taxonomy and agents apps

**Depends on:** T-01

Add the FP-04 row and FP-S6 to FP-S13, each referencing FP-04 and never FP-01, FP-03 or I18N-01. Change the AGT-04 wording and add AGT-S11, which references AGT-04 only. Add stubs.

**Owned paths:** `backend/apps/taxonomy/app.md`, `backend/apps/taxonomy/tests_scenarios.py`, `backend/apps/agents/app.md`, `backend/apps/agents/tests_scenarios.py`, `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:** The scenarios are present verbatim, the stubs are skipped, and the coverage script passes. FP-S1 to FP-S5 and the FP-01, FP-03 and I18N-01 rows are unchanged.

## T-06: Record the decisions and ADRs

**Depends on:** T-01

Add rows D-18 to D-34 to DECISIONS.md. Write three ADRs marked 'accepted by default'. 0026: markets as footprint jurisdictions plus a watch list, EU reach in Jurisdiction.parent, derived jurisdiction. 0027: participants, departments and My work. 0028: notes are shared comments, with one notification recipient check.

**Owned paths:** `docs/DECISIONS.md`, `docs/adr/0026-markets-footprint-and-watch-list.md`, `docs/adr/0027-participants-departments-and-my-work.md`, `docs/adr/0028-notes-are-shared-comments.md`, `docs/adr/README.md`

**Done when:** Each decision has its default, reason and what Alex confirms. The ADR index lists 0026 to 0028, and the links resolve.

## T-07: Write the INPUT_DELTAS rows

**Depends on:** T-06

§1:
- the kinds WorkReason, WorkBucket and WorkDateKind, and the three new NotificationKind values;
- Jurisdiction.parent means the jurisdiction whose rules reach this one, and NO points to EU;
- taxonomy_term.jurisdiction_id, watched_market and participant;
- tenant_obligation_scope.next_review_date;
- team as a tier-3 list with org_unit_id, team_member with composite keys and no is_lead, org_unit.head_user_id and team.org_unit_id as composite keys;
- UNIQUE (tenant_id, id) on tenant_obligation, change_case, team and org_unit;
- impact_assessment.contributors replaced by team participants.
§5: the tenant_agent.scope default.
§7:
- the MyWork reshape, with decisions moving to QueueCounts on GET /me, which gains applicability;
- the participant routes, /reference/people, headOf on /me, PUT /tenant/members/{userId}/teams and /me/comments;
- markets on GET /tenant/footprint and the two POST watching routes;
- footprint=in|all|watched, replacing inFootprint and outsideFootprint;
- jurisdiction on list rows.

**Owned paths:** `docs/inputs/INPUT_DELTAS.md`

**Done when:** Every schema and contract difference named in the analysis has a row with its reason and its requirement ID, and contract_drift_pending.txt is consistent with it.

## T-08: Update the build and UI plans and the chunk briefs

**Depends on:** T-01

Build_Plan:
- chunk 3 gains FP-04, and chunk 5 its feed part;
- chunk 8 gains HOM-05 and COL-04, listed with TEN-02 and TEN-03 above REG-04, REG-07 and VOC-04 to VOC-06;
- chunk 9 gains COL-04 on cases;
- chunk 10 keeps COL-01 first;
- chunk 11 gains the AGT-04 default.
UI plan:
- /me/work moves to tenant-my-work.html in chunk 8;
- Decide now reads the GET /me counts;
- line 83 gains departments with heads on admin-organisation.html and membership on admin-members.html;
- add rows for the participant routes, /reference/people, PUT member teams and the watching routes.
CHUNK3_TASKS: reverse 'neither inherits a jurisdiction term'; replace outsideFootprint with footprint=in|all|watched; add jurisdiction to rows.
CHUNK4_BRIEF: a console edit of a jurisdiction updates its mirrored term.
IMPLEMENTATION_STATUS: chunk 3 becomes 'in progress'.

**Owned paths:** `docs/plans/Build_Plan.md`, `docs/plans/UI_Implementation_Plan.md`, `docs/plans/briefs/CHUNK3_TASKS.md`, `docs/plans/briefs/CHUNK4_BRIEF.md`, `docs/plans/IMPLEMENTATION_STATUS.md`

**Done when:** The plans agree with the placement table. No row still says /me/work feeds Decide now. No new requirement sits below a cuttable Should item.

## T-09: Design the markets panel and the watched-market view

**Depends on:** T-06

admin-footprint.html gains the 'Markets we watch' panel:
- the intro line naming the Jurisdiction row as the markets we operate in;
- one row per country with 'Operating' meta text or a Watching switch;
- the 'also included' and 'everywhere else' lines;
- read-only and denied states, in light and dark.
tenant-inventory.html and tenant-watch.html gain the 'Markets we watch' option and the meta reason. Tokens and components come from the Green MCP server.

**Owned paths:** `design/screens/admin-footprint.html`, `design/screens/tenant-inventory.html`, `design/screens/tenant-watch.html`

**Done when:** The cards render in both themes, use only existing pill tones, and every string maps to a catalog key.

## T-10: Design My work, the participants panels and the organisation admin

**Depends on:** T-06

New tenant-my-work.html: scope switch (Mine and the departments you head), four sections, the link to Today, the 'Comments and mentions' panel with its visibility line, every state and the phone layout. Add a participants panel to tenant-obligation.html and tenant-change.html. Add departments with a head, and teams with their department, to admin-organisation.html, and team membership to admin-members.html.

**Owned paths:** `design/screens/tenant-my-work.html`, `design/screens/tenant-obligation.html`, `design/screens/tenant-change.html`, `design/screens/admin-organisation.html`, `design/screens/admin-members.html`

**Done when:** The cards render in both themes with no new pill slot or tone, and they are reviewed before chunk 8 starts.

## T-11: Record that EU rules reach Norway

**Depends on:** T-07

In the JURISDICTIONS seed, set Norway's parent to 'eu' with a comment naming the EEA Agreement, and do the same for the fixture's parent_code. Reword the Jurisdiction docstring to 'the jurisdiction whose rules reach this one'. No migration and no new field.

**Owned paths:** `backend/apps/library/seeds/__init__.py`, `backend/apps/library/models.py`, `backend/apps/library/fixtures/prototype_data.json`, `backend/apps/library/tests_library.py`

**Done when:** After seed_reference, GET /reference/jurisdictions returns parentKey 'eu' for no. makemigrations --check reports nothing. check_prototype_data passes.

## T-12: Mirror the jurisdiction rows as taxonomy terms

**Depends on:** T-11

Add TaxonomyTerm.jurisdiction, a nullable unique foreign key, with a reversible migration. seed_reference creates or updates one term per jurisdiction in the jurisdiction dimension, inside library_write. The term has the same key and labels, its parent is the term of Jurisdiction.parent, and active is mirrored. A hand-made term with the same key is adopted.

**Owned paths:** `backend/apps/taxonomy/models.py`, `backend/apps/taxonomy/migrations/00NN_term_jurisdiction.py`, `backend/apps/taxonomy/seeds/__init__.py`, `backend/apps/taxonomy/tests_vocabulary.py`

**Done when:** A guard test asserts the mirror is exact in both directions. /admin/footprint lists five jurisdiction chips. A second seed run changes nothing.

## T-13: Refuse proposals and tagging in the mirrored dimension

**Depends on:** T-12

Proposal creation and apply refuse a term proposal in any dimension whose terms mirror jurisdictions, and any tagging of an obligation or change with such a term. This is decided from the data, never from a dimension key.

**Owned paths:** `backend/apps/taxonomy/library_lists_logic.py`, `backend/apps/proposals/apply.py`, `backend/apps/proposals/tests_apply.py`

**Done when:** test_fp_s10 is green on Postgres.

## T-14: Derive a record's jurisdiction inside chunk 3's scope rule

**Depends on:** T-12, chunk3-rest-T4 (library/reading.py)

library/reading.py adds, to an instrument's and an obligation's scope, the mirrored term of Instrument.jurisdiction plus the terms of the jurisdictions whose parent it is. The SQL twin appends those term ids to the array it passes to taxonomy_in_footprint, which is left unchanged. Tests pin SQL and Python to the same answers.

**Owned paths:** `backend/apps/library/reading.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** test_fp_s7 and test_fp_s6 are green. No migration touches taxonomy_in_footprint. Chunk 3's footprint agreement test stays green.

## T-15: Add the watched_market model

**Depends on:** T-07

A WatchedMarket TenantModel with a jurisdiction foreign key (PROTECT), added_by and added_at, unique on (tenant, jurisdiction). Its migration forces RLS.

**Owned paths:** `backend/apps/taxonomy/models.py`, `backend/apps/taxonomy/migrations/00NN_watched_market.py`

**Done when:** The RLS structural guard (NFR-S3) passes. The migration applies from zero and reverses.

## T-16: Write the markets logic

**Depends on:** T-12, T-15

markets_logic provides levels(), computed with operating first, plus watch() and unwatch(). Writes go through record() as markets.watch_added and markets.watch_removed, with keys only. It refuses already_watching, and refuses unknown, inactive or non-country keys. Footprint approval is not touched. Logs carry counts only.

**Owned paths:** `backend/apps/taxonomy/markets_logic.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** test_fp_s9 is green. Audit and outbox rows are written in the same transaction.

## T-17: Serve markets on the footprint routes

**Depends on:** T-16

GET /tenant/footprint gains markets (MarketRow: jurisdiction, operating, watching). POST /tenant/footprint/watching and POST /tenant/footprint/watching/remove take the jurisdiction in the body and require footprint.request. Add the schemas and regenerate the types.

**Owned paths:** `backend/apps/taxonomy/api.py`, `backend/apps/taxonomy/schemas.py`, `backend/apps/taxonomy/http.py`, `openapi.json`, `frontend/src/types/api.generated.ts`

**Done when:** test_fp_s8 is green. The route-permissions guard (NFR-S13) passes. The contract drift check passes with the INPUT_DELTAS §7 rows.

## T-18: Add the 'Markets we watch' panel to the Footprint screen

**Depends on:** T-09, T-17

Add a MarketsPanel in features/footprint, composed into FootprintScreen: one row per country, with 'Operating' meta text or a Watching switch that saves at once through the new hooks. It includes the 'also included' line from parentKey and the 'everywhere else' line, is read-only without footprint.request, and has en and sv strings.

**Owned paths:** `frontend/src/features/footprint`, `frontend/src/components/admin/FootprintScreen.tsx`, `frontend/src/messages/en.json`, `frontend/src/messages/sv.json`

**Done when:** The screen matches the updated admin-footprint.html in both themes. The frontend compares no dimension key. check:messages passes. The existing footprint unit tests and J-6 stay green.

## T-19: Seed markets and turn on the markets end-to-end tests

**Depends on:** T-14, T-18

Seed tenant A as operating in SE (through footprint_logic.seed_terms) and watching NO (through markets_logic.watch). Tenant B has none. Un-fixme the FP-S6 and FP-S8 e2e tests.

**Owned paths:** `backend/apps/shared/e2e_seed.py`, `backend/apps/shared/tests_seed_integrity.py`, `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:** The seed-integrity counts are unchanged, with the 8 EU and 7 SE instruments still visible. J-6 and the FP-S6 and FP-S8 e2e tests are green against the real stack.

## T-20: Prove markets are isolated and stay out of logs

**Depends on:** T-17

Cross-tenant reads and removals. A test asserts that the request line of every markets write, which gunicorn's access log prints, and the scrubbed Sentry transaction hold no jurisdiction key. The same test checks the application log.

**Owned paths:** `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** test_fp_s12 is green.

## T-21: Add the watched-market view to the inventory

**Depends on:** T-14, T-16, chunk 3 list routes and inventory screen

GET /instruments and GET /obligations take footprint=in|all|watched, where watched means in F plus W but not in F, and return jurisdiction on each row. The inventory gets a 'Markets we watch' option beside 'Show outside footprint', with the reason as meta text.

**Owned paths:** `backend/apps/library/api.py`, `backend/apps/library/schemas.py`, `backend/apps/library/reading.py`, `frontend/src/features/library`, `frontend/src/messages/en.json`, `frontend/src/messages/sv.json`

**Done when:** test_fp_s11 and its e2e test are green. No new pill. FP-S4 stays green with footprint=all.

## T-22: Give changes their jurisdiction and add the view to the feed

**Depends on:** T-21, chunk 5 regulatory_change and feed

A change's jurisdiction terms are derived from its authority when matching. GET /changes takes footprint=in|all|watched and returns jurisdiction. The feed gets the option and the meta reason.

**Owned paths:** `backend/apps/watch/api.py`, `backend/apps/watch/logic.py`, `frontend/src/features/watch`

**Done when:** test_fp_s13 and its e2e test are green.

## T-23: Set tenant agents' default scope from the markets

**Depends on:** T-16, chunk 11 AGT-04 and AGT-06

At run start the scheduler builds the scope from the market levels, unless tenant_agent.scope names jurisdictions, and stores a copy on agent_run. The builder never reads tenant rows for a platform run. A new watch-sweeper prompt version orders the budget by level.

**Owned paths:** `backend/apps/agents/logic.py`, `backend/apps/agents/models.py`, `agents/watch-sweeper/v2/prompt.md`

**Done when:** test_agt_s11 is green, and AGT-S5 stays green.

## T-24: Add the My work kinds and settings

**Depends on:** T-07, chunk 8 start

Add WorkReason (owner, participant), WorkBucket (overdue, due_soon, aware, open) and WorkDateKind to kinds.py, with their reasons. Add MY_WORK_DUE_SOON_DAYS, MY_WORK_AWARE_DAYS and MAX_PARTICIPANTS_PER_RECORD under one banner in settings, each with an env override.

**Owned paths:** `backend/apps/shared/kinds.py`, `backend/config/settings.py`

**Done when:** The kinds-only guard passes, and the settings have typed defaults.

## T-25: Add departments with heads and team membership

**Depends on:** T-24, chunk 8 TEN-02 org units and TEN-03 team rows

Org units of kind business_area, business_unit or function with head_user_id. team as a tier-3 list with org_unit_id. team_member without is_lead. Composite keys to membership and org_unit, and UNIQUE (tenant_id, id) on team and org_unit. PUT /tenant/members/{userId}/teams (members.manage), writing one audit event per call. GET /me gains headOf. Admin screens: departments and teams on the organisation page, membership on the member row.

**Owned paths:** `backend/apps/tenants/models.py`, `backend/apps/tenants/api.py`, `backend/apps/tenants/logic.py`, `backend/apps/identity/me_logic.py`, `backend/apps/identity/schemas.py`, `frontend/src/features/tenant-admin`, `frontend/src/components/admin`

**Done when:** test_ten_s8 and its e2e test are green, and NFR-S1 holds for the route.

## T-26: Add the people picker

**Depends on:** T-25

GET /reference/people returns active members' ids and names only. It is ungated as CAPABILITY for member sessions and refused for enrolment sessions. Teams come from GET /vocab/team.

**Owned paths:** `backend/apps/tenants/api.py`, `backend/apps/shared/permissions.py`

**Done when:** The route is listed in UNGATED_BY_DESIGN with a reason. An enrolment session gets 403. A test shows another tenant's people and deactivated members never appear.

## T-27: Add the participant model

**Depends on:** T-24, T-25, chunk 8 tenant_obligation

In collab: the participant table, with composite foreign keys to tenant_obligation, change_case, team and membership (added as SQL in the migration). Two num_nonnulls checks, partial unique and index definitions WHERE removed_at IS NULL, and forced RLS. tenant_obligation and change_case carry UNIQUE (tenant_id, id).

**Owned paths:** `backend/apps/collab/models.py`, `backend/apps/collab/migrations/0001_participant.py`

**Done when:** The migration applies from zero and reverses. A model test proves that the database refuses a cross-tenant user, team or register entry. The RLS guard passes.

## T-28: Write the participant logic

**Depends on:** T-27

add(), remove() and leave() go through record() as participant.added, participant.removed and participant.left. They load the subject under RLS, check the member and the read permission, enforce the cap, and answer 409 already_participant for a repeated add. ensure_register_entry creates the register entry with its own register.entry_created event in the same transaction.

**Owned paths:** `backend/apps/collab/logic.py`, `backend/apps/register/logic.py`

**Done when:** Unit tests on Postgres cover each refusal code and the register.entry_created event.

## T-29: Add the obligation participant routes

**Depends on:** T-28

GET and POST /obligations/{obligationId}/participants, and DELETE /obligations/{obligationId}/participants/{participantId}, which is ungated as LOGIC_GATE with a reason. Schemas, regenerated types, and the gate registry. TENANT_SCOPED_ROUTES entries with a factory on a tenant-private obligation.

**Owned paths:** `backend/apps/collab/api.py`, `backend/apps/collab/schemas.py`, `backend/apps/shared/permissions.py`, `backend/apps/shared/routes.py`, `backend/apps/shared/factories.py`, `openapi.json`, `frontend/src/types/api.generated.ts`

**Done when:** test_col_s6, test_col_s7 and test_col_s8 are green. tests_tenant_isolation and NFR-S13 pass.

## T-30: Collect the register sources for My work

**Depends on:** T-29, chunk 8 REG-02, REG-03, REG-05, REG-07

my_work.involvement() unions the register sources with the reasons owner and participant: first-line owner, compliance contact, entity-row owner, owner team, internal-item owner, gap and duty owners, and person and team participants. It supports the mine scope, and the unit scope over the unit, the units below it, their teams and those teams' active members.

**Owned paths:** `backend/apps/home/my_work.py`, `backend/apps/home/tests_my_work.py`

**Done when:** Unit tests on Postgres cover every source, the department expansion, and the exclusion of deactivated members.

## T-31: Compute buckets, dates, permissions and counts for My work

**Depends on:** T-30

Date rules: involvement in the record itself versus only through a child, key dates in the past, and the tenant-local today. Buckets with precedence. Permission-limited kinds, with every count computed from the filtered set. Ordering and PageQuery.

**Owned paths:** `backend/apps/home/my_work.py`, `backend/apps/home/tests_scenarios.py`

**Done when:** test_hom_s8 and test_hom_s10 are green.

## T-32: Fill the 'changes on your items' bucket

**Depends on:** T-31

Add open cases with a confirmed WAT-04 link to an involved obligation, carrying via, and versions applied within MY_WORK_AWARE_DAYS. Leave out links nobody confirmed and the caller's own acts.

**Owned paths:** `backend/apps/home/my_work.py`, `backend/apps/home/tests_scenarios.py`

**Done when:** test_hom_s11 is green.

## T-33: Serve GET /me/work

**Depends on:** T-32

The route, with the WorkPage and WorkItem schemas and an UNGATED_BY_DESIGN entry as LOGIC_GATE. Regenerated types. A performance test with a pinned query count. GET /me's QueueCounts gain applicability for Today's Decide now.

**Owned paths:** `backend/apps/home/api.py`, `backend/apps/home/schemas.py`, `backend/apps/shared/permissions.py`, `backend/apps/identity/schemas.py`, `openapi.json`, `frontend/src/types/api.generated.ts`

**Done when:** test_hom_s7, test_hom_s9 and test_hom_s12 are green. The contract drift check passes with its §7 row.

## T-34: Write the My work frontend library

**Depends on:** T-33, T-10

features/my-work: API client, hooks, and a presentation module that maps reasons, who, via, date kinds and buckets to message keys. Unit tests.

**Owned paths:** `frontend/src/features/my-work`

**Done when:** The unit tests cover every reason, date kind and bucket, including '12 days overdue' and 'in 9 days' in en and sv.

## T-35: Build the My work screen

**Depends on:** T-34

The /work route. A my-work registry entry in the secondary group with no dockRank, so it sits under More on phones. MyWorkScreen with the scope switch (remembered in localStorage inside try/catch), the four sections, the link to Today and every state.

**Owned paths:** `frontend/src/app/(tenant)/work/page.tsx`, `frontend/src/components/work/MyWorkScreen.tsx`, `frontend/src/shared/navigation/registry.ts`, `frontend/src/messages/en.json`, `frontend/src/messages/sv.json`

**Done when:** The HOM-S7 and HOM-S9 e2e tests are green. The registry test (at most four ranked destinations) passes. The screen matches tenant-my-work.html in both themes.

## T-36: Add the participants panel to the obligation page

**Depends on:** T-29, T-26, T-10

Owners shown read-only. The participants list, with who added them. Add, with one picker over /reference/people and /vocab/team, shown only with register.edit. Leave on your own row.

**Owned paths:** `frontend/src/features/collab`, `frontend/src/features/register`

**Done when:** The COL-S6 and COL-S7 e2e tests are green.

## T-37: End participations and team memberships on member removal

**Depends on:** T-28, T-25, chunk 8 TEN-05

The TEN-05 removal preview counts participations and lists teams. On confirm, person participations and team memberships end in the same transaction, with one audit event each. Team participations are untouched.

**Owned paths:** `backend/apps/identity/members_logic.py`, `frontend/src/components/admin/MemberDetailScreen.tsx`

**Done when:** test_ten_s9 is green.

## T-38: Run J-9, Monday morning, end to end

**Depends on:** T-35, T-36

Seed Anna, Erik and Karin with a department, a team, an overdue review and a confirmed linked change. Un-fixme HOM-S13.

**Owned paths:** `backend/apps/shared/e2e_seed.py`, `frontend/tests/e2e/home.journey.spec.ts`

**Done when:** HOM-S13 is green against the real stack in the @smoke run.

## T-39: Add case participants and turn contributors into team participants

**Depends on:** T-29, chunk 9 CAS-02 and CAS-03

The participant routes on /changes/{changeId}: add with cases.contribute, remove with cases.contribute or your own row. TENANT_SCOPED_ROUTES entries on a tenant-private change. The change-page panel. The assessment's contributors picker makes single add and remove calls.

**Owned paths:** `backend/apps/collab/api.py`, `backend/apps/cases/logic.py`, `backend/apps/shared/routes.py`, `frontend/src/features/collab`, `frontend/src/features/cases`

**Done when:** test_col_s9, test_cas_s17 and test_cas_s4 (as amended) are green. The COL-S9 e2e test and TEN-S7 are green.

## T-40: Add case sources to My work

**Depends on:** T-39, chunk 9 CAS-04

my_work gains the case owner, the owner team, case participants and action owners, with their dates.

**Owned paths:** `backend/apps/home/my_work.py`, `backend/apps/home/tests_scenarios.py`

**Done when:** test_hom_s14 is green, and test_hom_s12 stays green.

## T-41: Send participant and linked-change notifications through one recipient check

**Depends on:** T-40, chunk 10 COL-02

Add participant_added, involved_item_changed and review_due to NotificationKind. One resolver picks active members whose roles can read the subject's kind at send time and sends one notification per person per event. Team recipients expand to active members. Mentions use the same resolver. Titles and emails carry the library title and a link only.

**Owned paths:** `backend/apps/collab/models.py`, `backend/apps/collab/logic.py`, `backend/apps/collab/tasks.py`, `backend/apps/shared/kinds.py`

**Done when:** test_col_s10 is green, and COL-S1 stays green.

## T-42: Send review reminders

**Depends on:** T-41

The reminder job sends review_due, at the tenant reminder lead, to whoever is responsible for each review date: first-line owner, entity-row owner, internal-item owner, or the owning team's active members. It never sends the same reminder twice.

**Owned paths:** `backend/apps/collab/tasks.py`, `backend/apps/collab/tests_scenarios.py`

**Done when:** test_col_s11 is green.

## T-43: List my comments and mentions on My work

**Depends on:** T-41, chunk 10 COL-01

GET /me/comments?about=written|mentioned, paginated and filtered by the subject's read permission, with permissionLimited. The 'Comments and mentions' panel with its visibility line. Comments and mentions join the 'changes on your items' bucket. The compliance lint extends to the new route.

**Owned paths:** `backend/apps/collab/api.py`, `backend/apps/home/my_work.py`, `frontend/src/components/work/MyWorkScreen.tsx`, `backend/scripts/compliance_check.py`

**Done when:** test_col_s12 and its e2e test are green, and test_col_s5 stays green.

## T-44: Escalate to department heads and build the digest on My work

**Depends on:** T-41

Escalation goes to the head of the department of the owner's teams, together with the compliance officer. The weekly digest calls my_work with scope mine and lists the section counts and first items in the user's language.

**Owned paths:** `backend/apps/collab/tasks.py`, `backend/apps/collab/tests_scenarios.py`

**Done when:** test_col_s2 (as amended) is green, with no second definition of open items.

# Appendix F. Open questions

- Do you want private notes that only their author can read, alongside the shared comments shown on My work? The build default is shared comments only, in a panel named 'Comments and mentions' (D-22). Private notes would change a product invariant:
  - they need a per-user RLS policy;
  - they need audit and outbox rows without the note's text;
  - they must be left out of exports;
  - they would hide compliance work from the tenant's own auditors, although every role holds audit.read.
  This needs your decision, not a default.
- Which aspiring markets outside EU, SE, DK, NO and FI do you have in mind (for example the Baltics, Germany or the UK), and in which release? Each one is a platform scope change (PRD §1, I18N-01). It needs a jurisdiction row, its authorities, sources and a content language before any sweep can find anything there. Until then, a Swedish bank can watch only Denmark, Norway or Finland (D-33).
- Rejected: moving T-44 (the roadmap query) to chunk 8. Superseded: T-44 and the v_roadmap_item delta row are dropped, because My work computes its own dates, so there is nothing to move.
- Rejected: moving the applicability and risk-acceptance approver sources into My work v1 in chunk 8. Superseded: the decisions bucket and the approver reason are dropped, and decisions stay on Today's Decide now (D-23).
- Rejected in part: the amended TEN-S7 answering 404 when tenant B opens A's participant list and A's markets. On a shared obligation or change, B's list is B's own (200, empty), and B's markets are B's own. Only tenant-private records and A's participant ids answer 404, and TEN-S7 and COL-S8 are written that way.
- Rejected in part: keeping team_member.is_lead team-level under the org-unit option. Nothing would read it once department heads sit on the org unit and team notices go to the team's members, so it is not built (INPUT_DELTAS row, D-21, D-34).
- Rejected in part: relabelling the Jurisdiction row 'Markets we operate in' through the catalog. The frontend would have to single out one dimension by its key. The row keeps its data label, and the 'Markets we watch' panel's intro line names it as the markets we operate in.
- Rejected in part: keeping PUT and DELETE /tenant/markets/{key}/watching in the same-screen critique. Superseded by the access-log critique: the key rides in the body of POST /tenant/footprint/watching and POST /tenant/footprint/watching/remove.
- Rejected in part: that a market 'falls back to Watching by itself' once operating stops. That is true only when a watch row exists. A market never watched reads as not followed, and D-31 says so.
- Rejected in part: a lens filter value 'outside'. Chunk 3's 'Show outside footprint' lifts the filter and marks the rows outside it (FP-S4, CHUNK3_TASKS), so the values are in, all and watched.

# Sources

- C:\Users\Alex\projects\grc\PRD.md (version log 0.1 and 0.2; TEN-02, TEN-03, FP-03, REG-05, HOM-01, HOM-03, COL-01 to COL-03; AC-NFR1, AC-FP1; J-8; §6 matrix lines 287-302)
- C:\Users\Alex\projects\grc\docs\DECISIONS.md (D-01 to D-17)
- C:\Users\Alex\projects\grc\docs\adr\ (0023 to 0025, README)
- C:\Users\Alex\projects\grc\docs\plans\Build_Plan.md (chunk table lines 10-24; descope trigger lines 26-28)
- C:\Users\Alex\projects\grc\docs\plans\IMPLEMENTATION_STATUS.md (definitions; chunk 2 Tested 2026-09-19; chunk 3 pending)
- C:\Users\Alex\projects\grc\docs\plans\UI_Implementation_Plan.md:83 (admin-organisation teams, chunk 8), :116 (/me/work feeds Today's Decide now)
- C:\Users\Alex\projects\grc\docs\plans\briefs\CHUNK3_BRIEF.md:67-75 and CHUNK3_TASKS.md:39-41, 67, 228-239 (one scope rule in library/reading.py; outsideFootprint; 'neither inherits a jurisdiction term')
- C:\Users\Alex\projects\grc\docs\plans\briefs\CHUNK4_BRIEF.md:71 (console jurisdiction edits)
- C:\Users\Alex\projects\grc\docs\inputs\schema.sql:289-300 (regulatory_change is library), 941 (org_unit_kind), 1063-1079 (team, team_member.is_lead, owner_team_id), 1219-1232 (org_unit.head_user_id, team.org_unit_id), 1266-1280 (internal_item owner and next_review_on), 1685 (follow on library records), 1980-1990 (owner_tenant_id, shared_or_mine)
- C:\Users\Alex\projects\grc\docs\inputs\openapi.yaml:124 (/me/work), 790-805 (inFootprint), 4570-4610 (Me counts, QueueCounts), 4732-4760 (MyWork)
- C:\Users\Alex\projects\grc\docs\inputs\INPUT_DELTAS.md (sections 1, 5, 7)
- C:\Users\Alex\projects\grc\backend\docker-entrypoint.sh:36-43 (gunicorn --access-logfile -)
- C:\Users\Alex\projects\grc\backend\config\settings.py:304-309 (API_PAGE_SIZE_*), 398-419 (Sentry traces, before_send_transaction)
- C:\Users\Alex\projects\grc\backend\apps\shared\sentry_scrub.py:61-86 (scrub_url keeps paths except invitations)
- C:\Users\Alex\projects\grc\backend\apps\shared\middleware.py:71-79 (loggable_route)
- C:\Users\Alex\projects\grc\backend\apps\shared\testing.py:129-145 (AuditAssertingClient fails 2xx writes without an audit row)
- C:\Users\Alex\projects\grc\backend\apps\shared\errors.py:37 (already_member 409)
- C:\Users\Alex\projects\grc\backend\apps\shared\routes.py:48-60 (TENANT_SCOPED_ROUTES) and tests_tenant_isolation.py
- C:\Users\Alex\projects\grc\backend\apps\shared\tenancy.py:175-183 (TenantModel has no UNIQUE (tenant_id, id))
- C:\Users\Alex\projects\grc\backend\apps\shared\schemas.py:24-29 (PageQuery)
- C:\Users\Alex\projects\grc\backend\apps\shared\permissions.py:139-170 (_EVERYONE holds comments.write, register.read, cases.read, audit.read), 365-392 (/vocab/{list_name}, /tenant/footprint, /reference/jurisdictions gates)
- C:\Users\Alex\projects\grc\backend\apps\shared\kinds.py (tier-one allowlist)
- C:\Users\Alex\projects\grc\backend\apps\identity\members_logic.py:188-211 (deactivate_member)
- C:\Users\Alex\projects\grc\backend\apps\identity\models.py:192 (membership_tenant_user_unique)
- C:\Users\Alex\projects\grc\backend\apps\identity\schemas.py:196-224 (Me has no counts yet)
- C:\Users\Alex\projects\grc\backend\apps\library\models.py:55-70 (Jurisdiction.parent, docstring), 166-194 (Authority and Instrument jurisdiction, required), 416-423 (ObligationTerm)
- C:\Users\Alex\projects\grc\backend\apps\library\seeds\__init__.py:31-39 (JURISDICTIONS: NO without parent)
- C:\Users\Alex\projects\grc\backend\apps\library\fixtures\prototype_data.json (jurisdictions: NO parent_code null; 8 EU and 7 SE instruments) and check_prototype_data.py:131
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\seeds\__init__.py:65 (jurisdiction dimension, 'Terms mirror the jurisdiction table', no terms)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\registry.py:112-134 (jurisdiction list proposable=False; tenant lists)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\library_lists_logic.py:196-212 (term proposals with parent)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\schemas.py:51-56 (JurisdictionRow.parent_key), 213-218 (TaxonomyTermCreateBody.parent), 246-250 (FootprintDimension)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\matching.py:20-75 (in_footprint, footprint_of, in_footprint_sql)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\migrations\0001_initial.py:15-40 (taxonomy_in_footprint(p_tenant, p_terms uuid[]))
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\api.py:183-191 (GET /vocab/{list_name}), 554-561 (reference jurisdictions parentKey)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\footprint_logic.py (_validate_change, one pending request, approve, seed_terms)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\app.md:45-48 (FP-01, FP-02 built, FP-03 in progress, I18N-01 built), 215-271 (FP-S1 to FP-S5, I18N-S1, I18N-S2)
- C:\Users\Alex\projects\grc\backend\apps\cases\app.md:32-36 (CAS-01, CAS-03), 66-74 (CAS-S1), 96-112 (CAS-S4, CAS-S5)
- C:\Users\Alex\projects\grc\backend\apps\collab\app.md (COL-S1 to COL-S5)
- C:\Users\Alex\projects\grc\backend\apps\tenants\app.md:31-36, 77-131 (TEN-02 to TEN-06, TEN-S2, TEN-S3, TEN-S5, TEN-S7)
- C:\Users\Alex\projects\grc\backend\apps\home\app.md (HOM-S1)
- C:\Users\Alex\projects\grc\backend\apps\shared\app.md (NFR-01, NFR-S1 to NFR-S5)
- C:\Users\Alex\projects\grc\backend\apps\register\app.md (REG-S3), agents\app.md (AGT-S5)
- C:\Users\Alex\projects\grc\backend\scripts\requirements_coverage.py (one test method per scenario, prefixes numbered globally)
- C:\Users\Alex\projects\grc\frontend\src\shared\navigation\registry.ts:45-63 (dockRank 1 to 4 taken; admin-footprint gated by footprint permissions)
- C:\Users\Alex\projects\grc\frontend\src\components\admin\FootprintScreen.tsx (generic dimension rows, request components)
- C:\Users\Alex\projects\grc\frontend\tests\e2e\tenants.journey.spec.ts:70 (TEN-S7 stub)
- C:\Users\Alex\projects\grc\design\system\navigation.md:15, 71-83 (at most four dock destinations; More sheet)
- C:\Users\Alex\projects\grc\design\screens\admin-footprint.html:268-282 (Jurisdictions chips designed)
- C:\Users\Alex\projects\grc\design\screens\tenant-today.html:106-110 (Decide now: triage, sign-offs, agent proposals)
- C:\Users\Alex\projects\grc\agents\watch-sweeper\v1\prompt.md:16 (scope arrives at run start)
- git: 7613874 (PRD 0.2), 51f9efa (chunk 3 data layer), e629481 (navigation specification, current main)
- https://linear.app/docs/my-issues
- https://linear.app/docs/assigning-issues
- https://help.vanta.com/en/articles/11345482-assignment-and-ownership-for-tests-policies-and-documents
- https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/evidence_hub/concepts/roles-and-permissions.htm
- https://support.atlassian.com/jira-software-cloud/docs/watch-share-and-comment-on-a-work-item/
- https://docs.github.com/en/subscriptions-and-notifications/concepts/about-notifications
- https://www.servicenow.com/docs/r/governance-risk-compliance/grc-compliance-management-workspace/work-in-compliance-ws.html
- https://help.archerirm.cloud/archersolutions/en-us/Content/ArcherSolutions/risk_management.htm
- https://asana.com/features/project-management/my-tasks
- https://www.cube.global/products/regplatform/regprofile
- https://www.cube.global/products/regplatform/horizon-scanning
- https://www.regology.com/regulatory-change-agent
- https://www.compliance.ai/solution/regulatory-intelligence/
- https://www.onetrust.com/news/onetrust-unveils-the-next-generation-of-dataguidance-regulatory-research/
- https://www.servicenow.com/community/grc-articles/regulatory-change-management-servicenow-a-practical-guide-to/ta-p/3417713
- https://www.adherent.com/blog/jurisdictional-change-monitoring-strategies-building-resilient-compliance-programs-across-global-markets/

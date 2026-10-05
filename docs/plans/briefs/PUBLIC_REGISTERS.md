# Public registers: the organisation and the regulatory scope from GLEIF and FI (PRD 0.9)

Source: Alex, 2026-10-05. The requirements are PRD 0.9's TEN-07, TEN-08 and FP-05 with
AC-TEN2, AC-FP4 and J-13; the scenarios are TEN-S13, TEN-S14, FP-S20, FP-S21 and REG-S18.
The defaults are D-121 and ADR 0066. It builds on chunk 8's organisation (TEN-02), the
regulatory scope request (FP-01, FP-02, FP-04) and the register's span (REG-01), and it
builds the per-entity half of `BANKING_GROUPS.md` (D-96) from register facts instead of
hand-filed exclusions.

## 1. What Alex decided

"Since data from Finansinspektionen is public, bleqq [should] load that when an organisation
gets onboarded so they don't enter [it] manually and something goes wrong." After comparing
the sources he asked to "see how this can be used to simplify the regulatory surface
management", and then: "go ahead, write the brief and build all steps". The three steps were:

1. A bank types its organisation number and gets its companies, licences and branches from the
   public registers, ready to confirm.
2. Each company's regulatory scope comes from its own licences, which replaces most of the
   hand-filed exclusions D-96 planned.
3. The registers are re-checked, and a new or withdrawn licence turns into a suggested scope
   change.

Today a bank describes itself twice: once on Organisation (companies, types, licences) and
once on Regulatory scope (around 40 boxes across nine dimensions), and nothing joins them.
Most of the scope's restricting dimensions are facts a supervisor already publishes.

## 2. What the registers give (verified 2026-10-05, `Verification_Log.md`)

| Source | What it holds | How it is read |
|---|---|---|
| GLEIF, the Global LEI Index (Swiss foundation set up by the FSB; data CC0) | Each company's legal name, registration number, country, LEI status, and its parent and children (Level 2) | JSON API at `api.gleif.org/api/v1`, no key: `lei-records/{lei}`, `lei-records?filter[entity.registeredAs]=…`, `lei-records/{lei}/direct-children` |
| Finansinspektionen's company register (free reuse with source and date) | Per company: name, org number, LEI, main business, other businesses, every licence with its grant date and legal basis, and the branches abroad with their addresses | The register's search exported as semicolon-separated text (`…/foretagsregistret/index?query=<org nr>&format=csv`, one row per company); the company's page (`details?id=…`) for the branch list, and each branch's page for its country |

What the comparison showed for SEB: every company present in both sources has the same name,
org number and LEI; GLEIF lists holding companies FI does not (they hold no licence) and FI
lists funds GLEIF does not hang under the bank. GLEIF knows two of SEB's eleven branches, FI
all eleven, so markets come from FI. GLEIF has no licences at all.

Neither source has a documented API for licences: FI's file is the export behind its search
page, and its branch list is on HTML pages. Both are read strictly, as untrusted content, and a
change in FI's layout fails the lookup loudly rather than guessing (section 6).

## 3. The flow

### 3.1 Fill in the organisation (TEN-07, TEN-S13)

1. On Organisation, a person holding `vocab.manage` chooses "Fill in from public registers"
   and types an organisation number (`556000-0001`) or an LEI. This starts a job (`POST
   /tenant/register-lookups`, 202); the screen polls its status.
2. The job finds the company in GLEIF (by LEI, or by registration number when exactly one
   company carries it), walks its children (direct children, breadth first, companies only:
   no funds and no branches, at most `REGISTERS_MAX_ENTITIES`), and for each company in a
   country whose supervisor publishes a register bleqq can read (FI for Sweden today) reads
   its FI row and branches.
3. The result lists every company with its country, registration number, LEI status and, where
   FI has it, its categories, licences and branches. A company FI licenses is preselected;
   the rest (holding companies, foreign subsidiaries, lapsed LEIs) are listed unticked.
   Companies the bank already has (same LEI, or same org number and country) are marked
   "Already in your organisation" and are linked rather than added again.
4. "Add the selected companies" (`POST /tenant/register-lookups/{id}/apply`) creates one legal
   entity per new company: name, org number, LEI, country and, from FI's main business, its
   type (the `legal_entity` term). The parent is the nearest selected owner in GLEIF's tree,
   else the bank's group unit when it has one, else none. Each FI company gets its register
   facts (`RegisterEntry`) with the source address and the date read.
5. Nothing is written before step 4, and step 4 writes no licence row and no scope term. The
   licences are shown from the register facts ("From Finansinspektionen's register, read 5 Oct
   2026"), so nobody types them and they cannot drift from the source. A bank still records
   certificates and other authorities' licences by hand, as TEN-02 does today.

### 3.2 The scope suggested from the register (FP-05, FP-S20)

On Regulatory scope, a person holding `footprint.request` sees "Suggested from your
licences" whenever the register facts and the scope disagree (`GET
/tenant/footprint/suggestions`). It lists each suggested change with the company and the
register line behind it, every line ticked. "Request approval" files the ticked lines as one
ordinary change request (`POST /tenant/footprint/requests`): the same preview, one waiting
request per bank, a second person holding `footprint.approve` approving with a passkey, one
audit event and one history row per term. Nothing in the scope changes until then.

### 3.3 Each company's scope from its own licences (FP-05, FP-S21, REG-S18)

The same request carries each company's exclusions: the licence-bound terms its register facts
do not give it. Once approved, the register does not offer that company a rule whose terms in
a dimension are all excluded for it (REG-S18). The bank's view of the inventory, feed and
roadmap does not change: exclusions narrow which per-entity rows the register offers, the way
the company's type already does.

### 3.4 The re-check (TEN-08, TEN-S14)

Every night (`REGISTERS_RECHECK_HOUR`, UTC) the worker re-reads FI for every company with
register facts and stores what changed, with an audit event. It never edits the organisation
or the scope: a new or withdrawn licence simply makes the suggestion in 3.2 non-empty, and the
company's facts on Organisation show the date of the last read. A register that cannot be
reached leaves the stored facts as they are and is tried again the next night.

## 4. The rule

### 4.1 From register facts to terms

`backend/apps/tenants/register_terms.json` maps a register's own wording to term keys, per
authority:

- `categories`: FI's main and other business names (`Bankaktiebolag`, `Värdepappersbolag`,
  `Fondbolag`, `Riksbolag, livförsäkringar`, …) to terms, for example `Bankaktiebolag` →
  `legal_entity:bank`, `regime:banking`.
- `licences`: a phrase found in a licence's text (case-insensitive) to terms, for example
  `bankrörelse` → `regime:banking`; `portföljförvaltning` → `service_type:portfolio_management`,
  `regime:securities`; `(direkt)` and `(indirekt)`, FI's marker on every insurance class, →
  `regime:insurance`; `Ge ut betalningsinstrument` → `licensed_activity:card_issuing`,
  `licensed_activity:card_acquiring`, `regime:payments`.

A company's **derived terms** are the union over its categories and licences. They are what
its licences allow, not what it chooses to do: a credit institution may provide payment
services and means of payment and safekeep securities under its licence (LBF 7 kap. 1 §), and
FI lists no separate licence for them, so a bank or credit market company derives payments,
card issuing and acquiring and custody and is never excluded from them. Its **type** is
the first `legal_entity` term of its main business. A licence or category the file does not
know is listed as "not used for the scope" (FI also publishes capital and model approvals such
as `IM_MR_SA` that map to nothing). A key the live taxonomy does not hold is dropped, never
created.

The **derivable terms** `D(d)` of a dimension are every term the file can produce in it:
regime {banking, securities, insurance, payments}, service type {portfolio management, advice,
custody, insurance distribution}, licensed activity {card issuing, card acquiring}, and the
seven legal-entity types. The other terms are choices no licence answers: AML, data
protection, tax and ICT apply whatever the licences; advised, non-advised and execution-only
describe how a bank sells.

Insurance undertakings are insurance distributors under IDD, so every insurer category also
maps to `service_type:insurance_distribution`.

### 4.2 The group's scope

For each restricting dimension `d` the suggestion compares `R(d)`, the union of the derived
terms of every company with register facts, with the scope's terms `G(d)`:

- `G(d)` empty (not restricted) and some derivable term missing from `R(d)`: add `R(d)` plus
  every term of `d` that is not derivable. Ticking only the derived terms would hide AML, tax
  or execution-only rules that no licence names; adding the non-derivable ones keeps them, so
  the change hides only licence-bound rules the group holds no licence for. When `R(d)` holds
  every derivable term, or is empty, nothing is suggested and `d` stays open.
- `G(d)` not empty: add `R(d) − G(d)`; remove the derivable terms no company derives
  (`G(d) ∩ D(d) − R(d)`), unless that would leave `d` empty, which would widen it instead.
- Markets: add the jurisdiction terms of each company's country and each branch's country that
  the library covers (FP-04 keeps EU rules reaching them). Markets are never suggested for
  removal: a bank may serve a country without a branch.

Each suggested line names the company and the register line behind it.

### 4.3 Each company's exclusions

For a company with register facts whose main business the file knows, its exclusions in the
licence-bound dimensions (regime, service type, licensed activity) are `D(d) − derived(d)`.
The suggestion adds the exclusions it lacks and lifts the ones it no longer needs. A company
without register facts, or whose main business is unknown, gets none, so it is never narrowed
by a guess. The type dimension stays with the company's type (the span's existing rule).

### 4.4 The span

`register/applicability._spans` gains one check. For every dimension in which the company has
exclusions `X(d)` and the obligation carries terms `O(d)`, the obligation spans the company
only if `O(d) − X(d)` is not empty. One pass per dimension, as `BANKING_GROUPS.md` 4.1
requires: an obligation tagged `{insurance, securities}` still reaches a company excluded from
insurance only. A cross-cutting term is never excluded, so an AML rule reaches every company.

## 5. Data and API

### 5.1 Tables (all tenant tables: `tenant_id`, forced RLS, composite tenant keys)

| Table | Columns | Notes |
|---|---|---|
| `register_lookup` (`tenants`) | `query`, `status` (`JobStatus`), `requested_by`, `created_at`, `completed_at`, `error`, `result` (`# schema: RegisterLookupResult`) | One job per lookup; the result holds public register data only |
| `register_entry` (`tenants`) | `org_unit` (a legal entity), `authority` (library), `facts` (`# schema: RegisterFacts`), `source_url`, `read_at`, `changed_at`, `version` | Unique per `(org_unit, authority)`; written by apply and the re-check only, each write audited |
| `entity_scope_exclusion` (`taxonomy`) | `org_unit`, `term`, `request`, `added_by`, `added_at` | The name `BANKING_GROUPS.md` 4.2 gave it; written only by an approved request |
| `footprint_change_entity_term` (`taxonomy`) | `request`, `org_unit`, `term`, `action` (`removed` excludes, `added` puts back), `created_at` | A request's company lines, beside its terms and scope items; unique per `(request, org_unit, term)` |
| `footprint_history` | + nullable `org_unit` | The history says which company a line was for; a row without one is the bank's |

Departure from `BANKING_GROUPS.md` 4.2: the company sits on each request line, not on the
request, so one request can carry the group's change and every company's exclusions, and one
waiting request per bank stays the rule. The lines have a table of their own, like scope
items, so nothing that reads a request's terms (the preview, the title, the history) can
mistake a company line for the bank's.

### 5.2 Routes

| Route | Permission | Does |
|---|---|---|
| `POST /tenant/register-lookups` | `vocab.manage` | Starts a lookup; 202 with the job |
| `GET /tenant/register-lookups/{id}` | `vocab.manage` | The job's status and, once done, the companies found |
| `POST /tenant/register-lookups/{id}/apply` | `vocab.manage` | Adds or links the chosen companies (by LEI) and stores their register facts |
| `GET /tenant/org-units` | (as today) | Each legal entity also carries its register facts and its exclusions |
| `GET /tenant/footprint/suggestions` | `footprint.request` | The suggested group and company changes, each with its reason |
| `POST /tenant/footprint/requests` | `footprint.request` | Also takes `entityExclusions` and `entityInclusions`: `{orgUnitId, dimension, key}` |
| `POST …/requests/{id}/approve` | `footprint.approve` + step-up | Also writes the company lines, with history and audit |

Errors: `lookup_not_found` (no company carries that number or LEI), `lookup_ambiguous` (more
than one does; type the LEI), `register_unavailable` (a register could not be read or its
format changed), `lookup_not_done` (409, apply before the job succeeded), `not_a_legal_entity`
and `dimension_not_narrowable` on a company line.

### 5.3 The adapter

`apps/shared/adapters/registers.py`, shaped like the scanner and the mailer: `RegistersAdapter`
with `find(query)`, `children(lei)` and `licence_facts(authority_key, registration_number)`;
`LiveRegisters` (GLEIF and FI) and `MockRegisters` (the E2E group: Example Bank AB with Example
Fonder AB and Example Liv Försäkring AB, its branches in Denmark and Norway, and a holding
company FI does not list); `get_registers()` refuses an unknown provider, and the mock is
refused deployed outside `ENVIRONMENT=test` (`MOCK_ADAPTER_SETTINGS`). It defaults to `live`
when deployed and `mock` elsewhere, so no deployed variable is needed.

The live provider reads only the two configured hosts over https, with one timeout per call,
a byte cap, no redirects, a fixed user agent and the registration number validated before it
reaches a URL. It returns facts, never HTML: a page that does not parse raises
`RegisterUnavailable`.

### 5.4 Settings (`public-registers` banner)

`REGISTERS_PROVIDER`, `REGISTERS_GLEIF_URL`, `REGISTERS_FI_URL`, `REGISTERS_TIMEOUT_SECONDS`
(10), `REGISTERS_MAX_BYTES` (2 000 000), `REGISTERS_MAX_ENTITIES` (100),
`REGISTERS_MAX_BRANCHES` (40), `REGISTERS_RECHECK_HOUR` (3), `REGISTERS_JOB_SECONDS` (300: the register
reads one lookup or one bank's re-read may take in all, since both run inside the bank's
transaction), `FOOTPRINT_ENTITY_CHANGE_MAX` (200).

## 6. What never happens

- No register read changes the scope. Every scope change, a company's exclusions included, is a
  request a second person approves with a passkey (FP-02, D-89). The re-check only refreshes
  facts.
- No agent and no API key reaches any of it: the routes are session-only.
- Nothing is guessed: an unknown category or licence is shown and not mapped; a register whose
  format changed fails the job with `register_unavailable`; a company with unknown main business
  gets no exclusions.
- Nothing reaches a model. The data is public, and only a registration number or LEI leaves the
  bank, to GLEIF and FI.
- The library is not written. The mapping file is reference configuration read by the tenant
  logic; the terms it names must already exist.

## 7. Screens

- **Organisation, legal entities** (`design/screens/admin-organisation.html`): "Fill in from
  public registers" beside "Add a legal entity" and in the empty state; a dialog with the number
  field, a progress line while the job runs, and the result as a checklist; each entity with
  register facts shows its categories, licences (collapsed), branches, "Read from
  Finansinspektionen's register on {date}" and, when it has any, "Outside this company's scope:
  {terms}".
- **Regulatory scope** (`design/screens/admin-footprint.html`): the "Suggested from your
  licences" panel above the groups, for holders of `footprint.request` while nothing waits; the
  pending banner, the approve dialog and the history list company lines as "{company}: outside
  its scope: {term}" and "{company}: back in its scope: {term}".

## 8. Defaults taken (D-121, each reversible)

- Licences are shown from the register facts, not copied into licence rows. TEN-02's licence
  rows stay for certificates and for what a register does not cover.
- The mapping is a versioned file maintained with the code, reviewed like code, not a library
  vocabulary with a proposal kind. A bank never edits it.
- Exclusions sit on request lines; one waiting request per bank (5.1).
- A company's type stays one term; the other legal-entity terms its other businesses give feed
  the group's suggestion only.
- The re-check runs nightly; the suggestion is computed on read, so it is never stale against
  the scope.
- Only FI's register is read for licences. Another supervisor is another entry in the adapter
  and the mapping file.

## 9. Not done

- The entity switcher, a membership's entity scope and entity-scoped inventory views
  (`BANKING_GROUPS.md` sections 6 to 9) stay as D-96 planned.
- Markets from cross-border services without a branch (FI lists them per company); only home
  countries and branches are suggested.
- Danish, Norwegian and Finnish licence registers (Norway has an open API,
  `api.finanstilsynet.no/registry/`).
- A Today row for a non-empty suggestion.

## Sources

- GLEIF API: `https://api.gleif.org/api/v1/lei-records/F3JS33DEI6XQ4ZBPTN86` and its
  `direct-children`, `ultimate-children` and `branches`; GLEIF open data and LEI data terms
  (CC0), fetched 2026-10-05.
- FI: `https://www.fi.se/sv/vara-register/foretagsregistret/`, the search's CSV export, SEB's
  page (`details?id=1356`) and its branch pages; FI's open data page (`/sv/om-fi/om-webbplatsen/oppen-data/`), fetched 2026-10-05.
- The category and licence wording in the mapping file was read from FI's CSV export for 21
  categories (banks, savings banks, investment firms, fund and AIF managers, insurers, payment
  and e-money institutions, credit market companies, insurance distributors) on 2026-10-05.

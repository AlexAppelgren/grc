# Standards and certifications within the sector scope

## Final IDs (PRD 0.3)

Assigned by the PRD 0.3 consolidation (`PRD_0_3_CONSOLIDATION.md`, 2026-09-19),
which merged this analysis with `MY_WORK_AND_MARKETS.md` and `REGULATORY_SCOPE.md`
into one bump. **Read the right-hand column, not the drafts below.** The decision
slugs became numbers continuing from D-34, which the markets analysis took.

| Drafted here | Final | ADR |
|---|---|---|
| `std-library-facts-only` | D-35 | 0029 |
| `std-opt-in-dimension` | D-36 | 0030 |
| `std-level-kind` | D-37 | 0031 |
| `std-international-jurisdiction` | D-38 | 0032 |
| `std-regime-boundary` | D-39 | 0033 |
| `std-sector-vocabulary` | D-40 | 0034 |
| `std-units-in-tenant-zone` | D-41 | 0035 |
| `std-entity-follows-by-applicability` | D-42 | 0036 |
| `std-certificate-on-licence` | D-43 | 0037 |
| `std-bulk-decide` | D-44 | 0038 |
| `std-watch-manual-first` | D-45 | 0039 |
| `std-soa-view-and-export` | D-46 | 0040 |
| `std-seed-list` | D-47 | 0041 |

| Drafted here | Final | Note |
|---|---|---|
| FP-01, INV-01, INV-02, INV-08, WAT-03, WAT-07, AGT-08, TEN-02, REG-01, REG-08, HOM-03, REP-02 | same | Applied; TEN-02 merged with the departments wording of the markets bump |
| AC-FP3, AC-INV2, AC-REG1, AC-REG2, AC-TEN1, AC-AGT1 | same | AC-FP2 went to the markets bump, so AC-FP3 stands |
| J-10 | J-10 | Unchanged |
| FP-S14 | **FP-S16** | The markets analysis's FP scenarios took S8 to S15 |
| FP-S15 | **FP-S17** | Same reason |
| INV-S11, INV-S12, PRO-S10, PRO-S11, WAT-S10, WAT-S11, AGT-S12, SRC-S12, SRC-S13, TEN-S10, REG-S12 to REG-S16, HOM-S15, REP-S6 | same | Unchanged |
| Amended: FP-S1, I18N-S1, INV-S1, INV-S2, INV-S3, PRO-S9, AGT-S3, TEN-S2, REG-S1, REG-S3 | same | Applied in the app.md files |
| STD-01, STD-02 | — | Done by the consolidation commit |
| STD-03 to STD-33 | `f03-*` | `docs/plans/briefs/FEATURES_0_3_TASKS.md` carries them with their final IDs and dependencies. STD-03's fetching half is open: nothing from §9 was fetched in that session, so every such fact is listed in `docs/TODO_FOR_alex.md` and **no** Verification log row was written |

This is read-only work against `main` at `bc10e37`. I edited no file.

- **Chunk 3.** Its data layer is on `main` (51f9efa). Its read API and screens are planned in `docs/plans/briefs/CHUNK3_TASKS.md` and not built. `docs/plans/IMPLEMENTATION_STATUS.md` still shows chunk 3 as `pending`, although by the ledger's own definition one commit on `main` makes it `in progress`.
- **Three plans landed after this analysis started, and they change it:**
  - `CHUNK3_TASKS.md` already folds the instrument's regime into obligation matching: `obligation_scopes()` in `library/reading.py` (lines 40 and 239).
  - `CHUNK4_TASKS.md` builds only the `new_obligation_version` proposal kind. It moves the instrument, obligation, provision and change-link kinds to chunk 5 (lines 68-72). It also turns rejection codes into a `rejection_reason` list with seven rows from schema.sql. None of them is `out_of_scope` (chunk4-T2).
  - `REGULATORY_SCOPE.md` renames the footprint "Regulatory scope" on screen and adds the regimes Banking and Payments (its task T01). It gives the page `scopeGroups()` and `narrowedGroups()`, and it claims FP-S6 and FP-S7.
- **The parallel analysis** is in the working tree as `docs/plans/briefs/MY_WORK_AND_MARKETS.md` (untracked). It drafts its own PRD 0.3 and claims D-18 onward, J-9, AC-FP2, FP-S6 to FP-S13, HOM-S7 to HOM-S14, TEN-S8, TEN-S9 and AGT-S11.
  - Here, decisions are named by slug.
  - New scenario, criterion and journey IDs are provisional and numbered past every claimed ID.
  - The orchestrator assigns the final numbers across all three documents.
- **Outside facts.** Every fact here about ISO, IAF, PCI SSC, Swift and the national standards bodies comes from the research maps and is unverified. Section 9 lists what to fetch and log before anything is seeded.

## 1. In brief

A standard fits the plan with little new code. ISO/IEC 27001 is the example throughout.

- **Each edition of a standard is an instrument.**
  - Its level carries a new optional kind, `standard`, so the pill reads "Standard" and not "Guidance, comply or explain".
  - The library holds only public facts about it, plus exactly one **conformance obligation** in our own words.
  - It never holds the standard's text, its clause or control titles, or a paraphrase of them. One check at proposal time and one database trigger enforce this on every write path.
- **A tenant opts in through its regulatory scope.**
  - A new dimension, "Standards followed", has a new kind, `opt_in`. A record that carries a standard matches only when the scope names that standard.
  - A standard term may sit only on a standard's own records, so it can never hide a law.
- **A legal entity follows a standard when its applicability is approved.**
  - The conformance obligation spans every legal entity.
  - "Applies", with a reason such as "Certified", goes through the existing four-eyes request.
  - That approval is the only record that the entity follows the standard.
- **A certificate sits on the entity's planned licence row.** Three columns are added: valid until, next audit and owner. The expiry and the next audit appear on the roadmap as "Our deadline", and never in the calendar feed.
- **The Statement of Applicability (SoA) is a list of units per following entity.**
  - A unit is a tenant row holding the tenant's own reference and words. It follows the planned `requirement_status` shape.
  - Each unit has its own applicability (through an ordinary request), status and gaps.
  - Many pending requests are decided in one call, with four eyes on every row.
- **A revision is one change per edition, with a timeline.** Only tenants that follow the standard match it. Automated reading of publisher pages waits for a lawyer.
- **The regime is the sector boundary.** Every instrument and every change carries one.

What a user gets, by release:

| Release | What works for ISO/IEC 27001 |
|---|---|
| R1 (chunks 2 to 7) | Browse the standard with "Show outside our scope". Add it to the regulatory scope. It then appears in the inventory, feed, roadmap, briefing and search. A new edition or amendment from a cleared source matches only following tenants, and its transition date reaches their roadmap. Ask answers "no answer" to a question about what a control says |
| R2 (chunk 8, cases in chunk 9) | Per entity: approve that it follows the standard, record its certificate, and see the next audit and the expiry on the roadmap. Paste units with a dry run and optional applicability. The approver decides them in one call. Status and gaps (audit nonconformities) per unit. The register filtered by standard and entity is the SoA |
| R3 (chunk 12) | The SoA as a dated export, through the inventory export |

**New in total:**
- **Kind values (tier 1):** `opt_in`, an optional instrument-level kind `standard`, and a jurisdiction kind `international`.
- **One tenant table:** `soa_unit`.
- **Columns:**
  - `scope_id` and `unit_id` on `applicability_request`;
  - `applicability_reason` and `applicability_decided_at` on the scope row;
  - `gap.unit_id`;
  - `valid_until`, `next_audit_on` and `owner_id` on `licence`.
- **Changes to existing structures:** `Instrument.regime` becomes NOT NULL; one trigger on `provision`; one SQL function replaced.
- **New code:** one standards check function, two watch rules, a paste route, a bulk-decision route and two roadmap branches.
- **Settings:** `REGISTER_BULK_MAX` and `STANDARDS_PUBLISHER_HOSTS`.
- **Content:** vocabulary rows, prompt text and eval rows.

**Not needed:** no new app, no new permission, no batch table and no parallel framework model. No invariant is weakened.
- **A separate framework model** (framework, requirement, control, mapping, SoA, certificate, audit) was rejected. Every one of its tables has a twin in the plan, and it would rebuild row-level security, four eyes, audit, scope and watch a second time. A custom-framework builder is also exactly the path into general GRC that PRD 0.2 closes.

## 2. What already fits

| Need | Existing design | Where |
|---|---|---|
| Edition and lineage | `Instrument`, `InstrumentRelation` | `backend/apps/library/models.py:182`, `:237` |
| An amendment that keeps the edition | `ObligationVersion` with `effective_from`, through `new_obligation_version` | INV-04, chunk4-T1 and T6 |
| Adding a standard to the scope | `FootprintChangeRequest`: preview with obligation counts, four eyes, step-up, one audit event per term | `taxonomy/models.py`, `REGULATORY_SCOPE.md` §6 |
| The instrument's regime in obligation matching | `obligation_scopes()` | `CHUNK3_TASKS.md:40`, `:239` |
| The regimes Banking and Payments | Fixture terms | `REGULATORY_SCOPE.md` §5, T01 |
| "This entity follows the standard" | `applicability_request` and `tenant_obligation_scope` | `docs/inputs/schema.sql:493`, `:1524` |
| One duty broken into parts under one register row | `requirement_status`, `gap.requirement_id` | `schema.sql:1556`, `:1571` |
| Status per entity, worst of | REG-S3 | `register/app.md` |
| "Applies" kept separate from "we comply" | `tenant_obligation` | `schema.sql:471` |
| Audit results | `compliance_assessment.method` of `internal_audit` or `external_audit` | `schema.sql:942` |
| Nonconformities | `gap` with source `audit` | `schema.sql:944`, `:1567` |
| A certificate an entity holds | `licence` (reference, granted_on, withdrawn_on, scope_note) | `schema.sql:1234` |
| The certificate PDF, the audit report | `evidence` | `schema.sql:1628` |
| The tenant's crosswalk | `internal_item` plus `internal_link.internal_item_id` | `schema.sql:1266`, `:1282` |
| Compensating controls | `waiver` (REG-06, R3) | – |
| Transition project | The case that CAS-01 opens | – |
| Scope rejection | `rejection_reason` rows (chunk4-T2), plus one row | `CHUNK4_TASKS.md:245` |
| Stages of a revision | One change per reform with timeline entries (WAT-02); change types `consultation`, `proposal`, `adopted`, `guidance` | `watch/app.md` WAT-S2 |
| Duty type | `governance` | Fixture vocabularies |
| Many approvals in one sitting | Step-up is a freshness window | `shared/permissions.py:462`, `config/settings.py:351` |
| An optional kind on a list | `validated_kind()` with `kind_required=False` | `taxonomy/registry.py:95`, `tenant_lists_logic.py` |

## 3. What must be added

### 3.1 Regulatory scope: an opt-in dimension (a follow-up to chunk 2, buildable now)

**Why.** FP-01 says an empty dimension does not restrict (`taxonomy/matching.py:39-43`). Its SQL twin in `taxonomy/migrations/0001_initial.py` counts a dimension only `WHERE EXISTS` a footprint term. Under that rule, a new `standard` dimension would mark every standard, and every change to one, as matching every tenant that follows no standard. They would reach every feed and roadmap.

**Change.**
- **Kind.** `TermDimensionKind` gains `opt_in` (`taxonomy/models.py:60`). A record carrying a term of an opt-in dimension matches only if the scope names that term. That holds even when the scope has no term in the dimension. Every other dimension keeps FP-01.
- **The rule lives in the matcher, so no data can switch it off.**
  - `restricting_dimensions()` returns `Q(restricts_footprint=True) | Q(kind="opt_in")`. The SQL join becomes `(d.restricts_footprint OR d.kind = 'opt_in') AND d.active`.
  - A relabel, a seed or a migration that clears `restricts_footprint` therefore changes nothing, and no guard is needed at proposal time.
  - A helper `opt_in_dimensions()` sits beside `restricting_dimensions()`.
- **The pure rule.** `in_footprint(..., restricting=..., opt_in=...)` takes `opt_in` as a required keyword, so no caller can forget it. Where `have = footprint.get(dimension)`, the code becomes `if not have: (if dimension in opt_in: return False) continue`. It returns false even when the dimension is missing from the mapping, and so avoids the `isdisjoint(None)` TypeError. Every caller passes it, including `footprint_logic` (REGULATORY_SCOPE T03, which is chunk3-rest-T7) and chunk 3's `obligation_scopes()`.
- **The SQL twin.** A new taxonomy migration replaces `taxonomy_in_footprint` with the join above and `WHERE d.kind = 'opt_in' OR EXISTS (...)`. `tests_matching.py` gains opt-in cases in the pure suite and the mirror suite: a dimension absent from the scope, a dimension with the flag false, and scope dimensions unchanged.
- **Seed rows.**
  - The dimension `standard`, "Standards followed", with kind `opt_in` and `restricts_footprint = true`.
  - One term per standard, not per edition, so the scope survives a new edition. `iso_iec_27001` comes first.
  - New terms start unticked (REGULATORY_SCOPE §5), so no tenant sees a standard until it opts in.
- **The Regulatory scope page** (REGULATORY_SCOPE §4.2):
  - `scopeGroups()` shows an opt-in dimension.
  - An empty opt-in group reads "None followed" (a new key), not "Not restricted: every option applies.", both in the read state and as the edit hint.
  - `narrowedGroups()` never lists an opt-in group. Ticking a standard reveals and never narrows, and the counted preview warns only when something is hidden.
  - The dimension kind must reach the page, as `{key, kind, label}`.
- **An opt-in term sits only on a standard's records, checked in both directions.** A standard term on a law would stop that law matching every tenant that does not follow the standard, with no preview and no second person.
  - At proposal creation, at a reviewer's correction and at apply: an obligation under an instrument whose level kind is not `standard` may not carry an opt-in term (422 `standard_term_only_on_standards`).
  - At `createChange` and at an editor's change correction: an opt-in term needs an authority whose jurisdiction kind is `international`. Otherwise the answer is the same 422, with the valid keys.
  - The prompt adds: "a law that cites a standard never carries its term; the instrument-level `related` relation carries that link".
  - An eval row covers a DORA text that cites ISO/IEC 27001.
- **Opt-in dimensions gate only at tenant level.** When chunk 8 computes which entities an obligation spans, it uses the entity's terms with the opt-in dimensions left out. Otherwise the conformance obligation would span no entity (section 3.4).

### 3.2 The library: one instrument per edition, public facts only (chunk 3 now, the proposal checks in chunks 4 and 5)

| Field | ISO/IEC 27001:2022 |
|---|---|
| `stable_key`, `official_ref`, `short_name` | `iso-iec-27001-2022`, "ISO/IEC 27001:2022", "ISO/IEC 27001" |
| Title | The publisher's title, as the original, confirmed by the lawyer. Other languages come only from a national standards body's public catalogue, entered by a person and never machine-translated |
| `level`, `binding` | The new row `standard` (kind `standard`, `binding_default = false`), and `false` |
| `jurisdiction` | `intl`, a new row with a new kind, `international` |
| `authority` | `iso-iec`, seeded with the standard |
| `regime` | The family of law it serves: `ai_ict` for 27001 and 22301, `data_protection` for 27701, `payments` for PCI DSS (REGULATORY_SCOPE T01 adds `payments`) |
| `in_force_from` / `in_force_to` | Publication and withdrawal dates, each with its precision |
| `implements_note` | National adoptions, as text |
| Lineage | None seeded. `replaces` is added as a relation type through a vocabulary proposal when a second edition is entered. `amends` is not added, because an amendment that keeps the edition is an obligation version |
| Provisions | None. The tree reads "The text of this standard is licensed and not held here", with the catalogue link |

**The conformance obligation.** There is exactly one active obligation per edition.
- Stable key `iso-iec-27001-2022-conformance`. `ref_label` equals the instrument's `official_ref`. Duty type `governance`.
- One term, `standard:iso_iec_27001`. No entity, service or jurisdiction term.
- en and sv summaries in our own words. Proposed: "Operate an information security management system that conforms to ISO/IEC 27001:2022 for the scope you declare, keep its Statement of Applicability current and keep any certificate valid."
- Re-verification checks the edition's status on the catalogue page.

**Code:**
1. **An optional `InstrumentLevelKind` (tier 1) with one value, `standard`.**
   - Registry entry: `kinds=("standard",)`, `kind_required=False`. `validated_kind()` already accepts an empty kind.
   - The five existing levels keep a null kind, and `binding` keeps deciding their pills. A `law` or `guidance` value would have no reader and would duplicate `binding_default`.
   - No relabel guard is needed: `ProposalVocabularyRelabelPayload` has no kind (`proposals/schemas.py:41-47`), and `_vocabulary_relabel` never writes one (`apply.py:132`).
2. **The pill.**
   - When `bindingLevel.kind` is `standard`, the header's binding slot and the row's guidance slot read "Standard", in the `information` tone.
   - Every other level keeps chunk 3's slots: "Guidance, comply or explain" in `warning` in the header, "Guidance" in `information` on the row (chunk3-rest-T5).
   - The contract already carries `{key, kind, label}` (the chunk3-rest-T3 schema walk), so this can land before or after chunk 3's reads.
3. **`JurisdictionKind.INTERNATIONAL` and one `intl` row.** The jurisdiction list is seeded, not proposed.
   - Two rules read the kind: the watch rule for standard terms (section 3.1), and the markets derivation (section 8), which must derive no jurisdiction term for an international instrument or authority.
   - I18N-S1 and its test (`taxonomy/tests_scenarios.py:719`, which asserts the exact set) gain the row.
4. **One standards check function** (`proposals/standards.py`). It runs at `POST /proposals` and at the agent's proposal creation, over a reviewer's `payloadOverrides` at approval, and at apply. A payload is stored at creation, so a check only at apply would keep pasted text in the platform database. The checks:
   - A provision or provision-version proposal under a standard answers 422 `licensed_text`. So does an `instrument_update` that moves an instrument with provisions to the standard level.
   - A field source on a standard's record must be a URL, or the answer is 422 `licensed_text`. There is no citation model: `citation` in `schema.sql:1381` is unbuilt, and `field_sources` is the carrier.
   - A standard has at most one active obligation, and its `ref_label` equals the `official_ref` (422 `one_conformance_obligation`).
   - That obligation has exactly one opt-in term (422 `standard_term_required`). Any other obligation has none (422 `standard_term_only_on_standards`).
   - Chunk 4 wires the term checks for `new_obligation_version`, which can change scope terms. Chunk 5 wires the rest with its new proposal kinds.
5. **A trigger on `provision`** (on INSERT, and on UPDATE of `instrument_id`) refuses a row under a standard-level instrument.
   - A version and its text cannot exist without a provision, so this one trigger covers them.
   - Seeds, the watch pipeline and tenant-private records (INV-07, R3) all inherit it, which matters because `library_write()` admits all three (`shared/tenancy.py:133`).
   - `check_prototype_data.py` also refuses a provision under a standard and requires exactly one obligation under it.

### 3.3 The regime is the sector boundary (chunks 3 and 5)

- **Make the regime required.** `Instrument.regime` is nullable today (`library/models.py:196`), although schema.sql has it NOT NULL. Without a regime, an instrument matches every tenant.
  - Make it NOT NULL.
  - The seed-integrity test and chunk 5's instrument-proposal apply check that it is a term of the `regime` dimension (422 `not_a_regime`).
  - All 15 fixture instruments already have a regime.
- **The fold is already planned.** Chunk 3's `obligation_scopes()` joins "an obligation's terms plus its instrument's regime". FP-S1's clause "an obligation with no scope terms at all matches every tenant" must be amended to match, and so must the `matching.py` docstring.
- **Chunk 5.** `createChange` refuses a change with no regime term (422 `regime_required`). All 52 eval cases already carry one.
- **A consequence to state in the copy.** A standard shows only when both its standard term and its regime are in the scope, or when the scope has no regime at all.
  - The demo scope includes `ai_ict`.
  - The standard term's usage note names its regime, and the counted preview shows what adding it reveals, which may be nothing.

### 3.4 A legal entity follows a standard through applicability (chunk 8)

- **One "follows" record.** The entity's approved applicability on the conformance obligation is the only record that it follows a standard. PRD 0.2 already says standards are worked "through applicability ... per legal entity".
  - The request needs four eyes and a step-up, and it keeps a reason ("Certified", "Required by card-scheme contract", "Voluntary") and its history.
  - A second record, such as a standard term on the licence row, could disagree with it and would move a span-deciding fact out from behind four eyes.
- **Span.** The conformance obligation carries no entity term, so it spans every legal entity. Opt-in dimensions are checked at tenant level only (section 3.1).
- **Per-entity requests.** `applicability_request` gains a nullable `scope_id`. The one-pending index becomes `(tenant_obligation_id, scope_id, unit_id) NULLS NOT DISTINCT`. `tenant_obligation_scope` gains `applicability_reason` and `applicability_decided_at`. Any regulation that spans several entities needs this anyway (REG-02).
- **Reads never write.** A scope row is created, through `record()`, in the transaction of the request that needs it.
- **Removing a standard from the regulatory scope** (four eyes and step-up) hides the conformance obligation and its rows, and deletes nothing. The counted preview shows the obligation as hidden.

### 3.5 The Statement of Applicability: units in the tenant zone (chunk 8)

**Why the tenant zone.**
- Clause and control numbers, titles and requirement text exist only in the paid standard, so they are not "sourced public facts" (CLAUDE.md §1, playbook 4.3).
- The tenant holds the licence and already keeps an SoA. Its own references and words are its own work.
- The library-side `obligation_requirement` cannot hold them, because its `text_en` and `text_sv` sit in the shared library.
- Units must not become extra `tenant_obligation` rows either. Every count that reads that table would inflate: HOM-01's "Where we stand", REP-01's heatmap, and the `review_due` roadmap branch (`schema.sql:1845`).

**Design:** the planned `requirement_status` shape, holding the tenant's own reference and words.
- **The table.** `soa_unit` sits under forced row-level security, one row per unit per legal entity. Its columns:
  - `tenant_id`;
  - `scope_id`: the conformance obligation's scope row for that entity;
  - `unit_ref`, such as "6.1.3" or a control reference;
  - `title`, in the tenant's own words;
  - `applicability`, `applicability_reason`, `applicability_decided_at`, `compliance_status` (from the tenant's list) and `status_note`;
  - `version` and `created_by`.

  It has `UNIQUE (scope_id, unit_ref)` and `CHECK (compliance_status = 'not_assessed' OR applicability = 'applies')`.
- **What stays unchanged.** `tenant_obligation` keeps `UNIQUE (tenant_id, obligation_id)`, and every existing register query stays correct.
- **Where a unit may exist.** Only under a scope row whose obligation belongs to a standard-level instrument (422 `units_only_under_standards`), and whose applicability is `applies` (422 `scope_not_applicable`). A tenant therefore cannot build a framework the library has not admitted, which keeps the product out of general GRC by structure.
- **Applicability of a unit** changes only through `applicability_request`, which gains a nullable `unit_id`. Four eyes applies per row, through the existing CHECK.
- **Gaps.** `gap` gains `unit_id`, the way `gap.requirement_id` works. Evidence and internal links stay on the conformance row. Unit-level evidence is deferred.
- **A unit is fixed once it has history.**
  - `unit_ref` and `title` can no longer change once the unit has a request, a decision or a gap (409 `unit_has_history`). Otherwise an approved "does not apply" could be moved onto another control by renaming it.
  - To correct a unit, add a new one and file "does not apply" for the old one.
  - A unit with no history can be renamed with `If-Match`, or removed. Both are audited with before and after values.
- **Entry.** Units are added one by one, or pasted for one entity, one line each: a reference, a title, and optionally an applicability and a reason.
  - A dry run lists the rows and refuses duplicate references, over-long lines and unknown applicability values.
  - Commit writes each unit with one audit event (`register.edit`). With the optional columns, it also files one pending request per row (`applicability.request`).
  - `REGISTER_BULK_MAX` caps a paste.
  - This is the only entry path for units. REP-03 stays generic.
- **No field for the standard's text.** The form asks for "your own words" (a message key). The terms of service make the tenant responsible for its licence.
- **Roll-up.** The conformance row per entity keeps its own assessed status, which covers the management system itself. REG-S3's per-entity worst-of roll-up is unchanged, and there is no roll-up across units.
- **Fallback if the lawyer says clause references in a SaaS break the bank's ISO licence.** Chunk 8 ships without `soa_unit`. The conformance row per entity, with the tenant's own SoA as evidence, still works, and nothing else in this design changes.

### 3.6 Deciding many requests in one call (chunk 8)

- **Step-up is a freshness window, not a token spent per action.** `enforce_step_up` accepts any assertion younger than `STEP_UP_FRESHNESS_MINUTES`, 5 by default. The earlier claim of "about 300 step-ups" was wrong, and a batch table is not needed.
- **One route under `applicability.approve` and `@requires_step_up`.** It takes `[{requestId, decision, note}]` over pending requests.
  - It decides each request through the single-request logic, in one transaction.
  - A request the caller filed answers 409 `four_eyes_violation`, and nothing is decided.
  - It writes one `record()` per row, citing the assertion.
  - It is capped by `REGISTER_BULK_MAX`, which defaults to 100, the page maximum. That keeps a call inside the 250 ms budget; a full SoA takes two calls.
- **A pending request cannot be edited.** The requester withdraws it and files it again, so the approver decides exactly the rows it listed.
- **The preview is the approver's queue,** filtered by standard, entity and requester.
- **The four-eyes guard.** `applicability_request` joins `FOUR_EYES_TABLES` in `shared/tests_four_eyes.py` when chunk 8 builds it, as that file already demands.

### 3.7 Certificates and the audit cycle (chunk 8)

- **The licence row holds the certificate.** The certificate is held by one entity, like a licence. It uses the existing columns:
  - `licence_type`, for example "ISO/IEC 27001:2022 certificate, issued by Example Certification AB";
  - `reference`: the certificate number;
  - `granted_on`;
  - `withdrawn_on`;
  - `scope_note`: the certificate's scope statement.

  It adds nullable `valid_until`, `next_audit_on` and `owner_id`. It carries no term and decides no span.
- **Two roadmap branches** in `v_roadmap_item`:
  - `licence_expiry`, from `valid_until`, and `licence_audit`, from `next_audit_on`;
  - both of kind `internal`, shown as "Our deadline", with the row's owner;
  - both left out when `withdrawn_on` is set.
- **Kept out of the calendar feed.** The per-user ICS feed carries public facts only (`home/app.md` §3), so the feed leaves both branches out. COL-02 reminders reach the owner in the app.
- **Surveillance audits are not a `recurring_duty`.** That table holds one library rule shared by every tenant and needs an `obligation_id` (`schema.sql:1442`). REG-07 is unchanged. After an audit, the owner records `external_audit` assessments, gaps with source `audit` for nonconformities, and the report as evidence, then sets the next audit date.
- **The licence row is the one source of certificate dates.** An evidence file's `valid_until` belongs to the file.

### 3.8 Watching standards (chunk 5)

**One change per edition or amendment**, keyed by stable key (WAT-02). Stages are timeline entries, and the change type follows the stage.

| Event | Where it goes |
|---|---|
| Draft for comment | Timeline entry. Type `consultation` at this stage |
| Final draft | Timeline entry. Type `proposal` |
| Edition or amendment published | Timeline entry. Type `adopted` |
| Accreditation transition rule | Timeline entry, from the accreditation forum's document |
| End of transition, old certificates invalid | The key date, labelled "Transition ends" |
| Old edition withdrawn | The old instrument's `in_force_to`, through an instrument proposal |

Each change carries `standard:<key>`, its regime, and an authority under `intl`.

- **Cases.** CAS-01 creates one case per tenant per change and caches `footprint_match` (CAS-S1). Only tenants that follow the standard match. `v_roadmap_item` and the feed filter on that match, so the change and its transition date reach only those tenants. The case is the transition project.
- **A new edition.**
  - The editor applies the new instrument and its conformance obligation, and sets `in_force_to` on the old edition (chunk 5 proposal kinds).
  - Each tenant requests per-entity applicability on the new conformance obligation and pastes its units again. Copying units forward is deferred.
  - The old rows stay as history.
- **Sources.**
  - A new `source_kind` row, `standards_body`.
  - Until the lawyer answers, such sources are registered inactive, with no automated check, and a person enters edition facts as instrument proposals.
  - Automated reading starts per publisher, once its terms are read. IAF documents come first.
  - `POST /changes` is agent-only (UI plan line 195), so until one source is cleared, a revision opens no case (open question).
- **Snapshots.** `source_check` has no URL, hash or snapshot (`schema.sql:278-287`). Snapshots live on `source_document` (`:1362-1377`), which has no `source_id`. So:
  - a `source_document` on a host listed in the setting `STANDARDS_PUBLISHER_HOSTS` keeps only its URL, date and hash, never a snapshot;
  - a change that carries an opt-in term may link only snapshot-free documents (422 `licensed_text`). This also covers a copy found on the open web.
- **Watch-sweeper v1** is still `status: draft` (`definition.yaml:8`), so it is edited in place. The prompt:
  - **Scope.** `prompt.md:8-9`: "banks and insurers" becomes the PRD's scope sentence. A new Scope section: an out-of-scope document gets its source check and an `out_of_scope` count, and nothing is registered or proposed.
  - **Standards.** A new Standards section:
    - Register publication facts only.
    - Never fetch, quote, summarise, translate or restate a standard's text, from a page or from memory.
    - Never propose an obligation per clause or control.
    - A 403 or a challenge is a failed source check, never worked around.
    - Never fetch a page of an inactive `standards_body` source.
    - A law that cites a standard gets no standard term.
  - **Dimensions.** `prompt.md:80-81` hard-codes five dimensions. They become "every dimension whose `restricts_footprint` is true or whose kind is `opt_in`, as read at run start", with the opt-in rule above.
- **`definition.yaml`:**
  - lines 63-70 add `instrument_level`, `jurisdiction`, `relation_type`, `duty_type` and `provision_kind` to the vocabularies read at run start, so a `new_instrument` proposal can pass AGT-02;
  - the description mentions standards;
  - the run stats gain `out_of_scope`.
- **Evals.** Every text is written by us (`source: authored`) and never copied from a publisher.
  - Off-sector rows with `expected.in_scope: false`: medical devices, construction safety, an environmental permit, workplace safety and ISO 14001.
  - A DORA text citing ISO/IEC 27001, which expects `in_scope: true` and no standard term.
  - Standards rows that expect `scope.standard`: a new edition with a transition key date, an accreditation rule and a draft for comment.
  - In-scope accuracy and standard-term accuracy, each with a tolerance, in `backend/scripts/search_eval.py`.

### 3.9 Mapping to regulation (on the tenant side)

- **The tenant's crosswalk.** One `internal_item`, such as the ISMS policy, links to the conformance row and to DORA's ICT-risk obligations (REG-05, unchanged).
- **"Also serves" is deferred.** No one asked for it.
- **No library crosswalk at control level.** The library holds no controls.
- **An instrument-level `related` relation** is possible where a regulation's own text refers to standards, through an instrument proposal. One example, unverified: Delegated Regulation 2024/1774, Art. 2(1)(h).

### 3.10 Search, Ask and model memory (chunks 7 and 8)

- **Search** indexes the conformance obligation's summary in our own words. Nothing else of a standard exists in the library.
- **An eval row for SRC-05:** "What does ISO/IEC 27001 control A.8.8 require?" expects "no answer". The row also catches a model restating the control from training data.
- **A guard test, written per row** (chunk 8, before anyone relaxes D-10 at R2):
  - No text from any tenant row whose obligation sits under a standard-level instrument may enter `search_chunk`, an embedding input or an `ai_generation` input.
  - That covers units, scope notes, gaps, assessments, interpretations and links.
  - The test fails as soon as any field of such a row is added to an indexer or model input.

### 3.11 Test data

- Units in tests, seeds and E2E use invented references and titles, such as "X.1 Example control". Never real clause or control titles.
- Eval texts about standards are authored.
- `backend/eval/README.md` states both rules.

## 4. Where content may live

| Content | Shared library | Tenant zone |
|---|---|---|
| Reference, edition, publisher, dates, lifecycle, national adoptions (as a note), catalogue link | Yes | – |
| A revision and its timeline and key date | Yes, from public metadata: facts and a hash, no snapshot | A case per tenant, matching only followers |
| One conformance duty in our own words | Yes, once the lawyer confirms | Applicability ("follows") and status per entity |
| Clause or control numbers, titles, text, paraphrase | No, refused by the check function and the trigger | The tenant's own references and words, as units per entity. Never indexed, never sent to a model |
| Certificate: issuer, number, scope, validity, next audit | – | The entity's licence row |
| Applicability and reason, status, gaps | – | Yes |
| The standard's PDF, the tenant's own SoA document | No | Only under the tenant's own licence, as evidence (terms of service) |

**What the licensing analysis reports (unverified):**
- ISO's End Customer Licence Agreement, updated 2026-05-29, excludes integration into compliance systems (§6(b)) and any AI processing (§7(b)).
- PCI SSC's terms exclude derivative works.

The library-side defaults hold whatever the answer is. The units depend on it, which is why section 3.5 has a fallback.

## 5. Enforcing the sector scope

| Point | Rule | Chunk |
|---|---|---|
| Regime list | Closed, and it grows only through an approved proposal. The reviewer rejects with the reason row `out_of_scope` ("Outside the sector scope") | 2 (built), 4 (row) |
| Standards list | The same for `standard` terms. ISO 9001, 14001, 45001 and 13485 are rejected | 2, 4 |
| Usage notes | The regime note names the sector scope, in REGULATORY_SCOPE T01's rewrite. Each standard term's note names its regime. Agents read the notes at run start | 2 (rows) |
| Every instrument | A required regime from the regime dimension | 3, 5 |
| Every change | At least one regime term | 5 |
| Standard terms | Only on a standard's own obligation and on a change from an international issuer | 4, 5 |
| Standard instruments | One conformance obligation, no provisions, field sources that are URLs | 3 (trigger), 4, 5 |
| Units | Only under a standard the library admitted, for an entity that follows it | 8 |
| Agent | The scope rule, the `out_of_scope` count, negative evals | 5 |
| Private paths (WAT-06, INV-07, R3) | No editor reviews them, so the required regime, the provision trigger and the prompt rule are their scope checks. Tenant-private standard instruments stay text-free | 13 |
| Tenants | Only the platform admin creates them (chunk4-T7). The terms state the intended use | 4, legal |

**Scope edges already in the data** (the same question as REGULATORY_SCOPE §12, answered once):
- The `tax` regime and the AI Act (`ai_ict`) are not named in PRD 0.2's scope sentence. Default: keep both and name them.
- The PRD's six sectors map to terms of the existing, termless `licensed_activity` dimension ("The licence under which the firm acts"), added by proposal.
- Regime terms are added only for a body of law an instrument needs.
- No new `legal_entity` types until `licensed_activity` has been checked.

## 6. Deferred and out of scope

| Item | Why | Trigger |
|---|---|---|
| Control lists or titles in the shared library, library crosswalks at control level | Needs a content licence covering every tenant, every territory and AI processing, plus Alex's decision on "sourced public facts" (stop and ask) | A licence |
| Copying units forward to a new edition or to another entity | Pasting again works, and transitions are rare | Tenants ask |
| Evidence and internal links per unit | Evidence on the conformance row and on gaps covers the audit | Tenants ask |
| "Also serves" across obligations | Not asked for. The crosswalk data exists | A bank asks |
| The SoA "as of" a date, and as a formatted export | Each unit's decided requests are its history. REP-02 is R3 | Alex may pull a CSV into chunk 8 |
| First due date set by the tenant (REG-07) | Only a scheme cadence (Swift CSCF, PCI DSS) needs it, and those are not seeded | A standard with such a cadence is admitted |
| ISO 22301, ISO/IEC 27701, ISO/IEC 42001, PCI DSS, Swift CSCF | Prove the pattern on one standard first. PCI SSC and Swift terms are stricter and unverified | Rows by proposal |
| Tenant-private standard instruments (INV-07) | R3. INV-07 also has open isolation gaps: child tables such as provision have no owner | R3 |
| AI features over units | ISO's §7(b), as reported, and D-07 | Never without a licence |

**Out of scope:**
- control testing;
- the ISMS risk assessment and risk treatment plan, which form a risk register;
- certificates and SOC reports received from suppliers, which belong to vendor management;
- ISAE 3402 or SOC reports that a tenant issues (Alex confirms).

## 7. Main risks

1. **Licensing on the bank's side is open.** Storing units may fall under ISO §6(b), as reported. Mitigation: a lawyer's view before the first bank uses units, the terms-of-service clause, and the fallback in section 3.5.
2. **The opt-in rule edits a built rule that has a SQL mirror.** Mitigation: the required keyword, the rule inside the matcher, and both mirror suites, including a dimension missing from the scope.
3. **A standard term on a law would hide binding law.** Mitigation: the two-direction check, the prompt rule and the DORA eval row.
4. **Deciding many requests at once can become rubber-stamping.** Four eyes holds on every row, but attention does not. Mitigation: explicit request ids, requests that cannot be edited, the filtered queue, the cap of 100, and one audit event per row.
5. **Visibility needs both the standard term and its regime.** Mitigation: the usage note and the counted preview.
6. **Units are per entity,** so a tenant with three certified entities pastes three times. Mitigation: the paste. Copying is deferred.
7. **Standards revisions open cases only from a cleared source,** until the lawyer answers.
8. **Model memory can restate controls.** The prompt rule and the Ask eval row reduce this; they cannot prove it never happens.
9. **Parallel plans:** colliding IDs and the `intl` derivation (section 8).
10. **Every outside fact is unverified** (section 9).

## 8. Interactions with parallel work (not redesigned here)

**`REGULATORY_SCOPE.md`:**
- `scopeGroups()` and `narrowedGroups()` must treat opt-in groups as revealing (section 3.1), and the opt-in group needs its "None followed" key. The keys this analysis first cited, such as `footprint.dimensionNote`, are deleted there.
- T03, the counted preview built as chunk3-rest-T7, must pass `opt_in`.
- T01 owns the fixture's regime rows and note. This analysis only proposes the note's scope wording.
- User copy says "regulatory scope" and "Show outside our scope", not "footprint".
- It claims FP-S6 and FP-S7, which the markets analysis also claims.

**Operating and watched markets (`MY_WORK_AND_MARKETS.md` §4):**
- Its derivation gives each obligation the jurisdiction term of `Instrument.jurisdiction`, and each change that of its authority. It must derive none for kind `international` and create no mirror term for `intl`. Otherwise a tenant that turns on any operating market hides every standard.
- Its bump keeps FP-01 unchanged. This one must amend FP-01, because the opt-in rule contradicts its last sentence. The two bumps merge into one 0.3.
- Chunk 8's entity span, if markets per entity feed it, must leave opt-in dimensions out.
- "Watching" may later suit a standard a tenant is still considering, by reusing `opt_in` rather than adding a second rule.

**My work and participants:**
- The licence row's `owner_id` takes whatever owner shape that analysis settles: a person or a team (TEN-03). TEN-05 reassignment must include licence owners.
- Certificate dates and pending applicability requests may appear in My Work and in approvers' queues.
- Both bumps change TEN-02. Theirs adds departments, this one certificates.
- Certification-body auditors are not users.

**Chunk plans:**
- chunk3-rest-T4, T5, T7, T13 and T18 own files that STD-04, STD-11 and STD-12 touch.
- chunk4-T1, T2 and T6 own the proposal files STD-14 and STD-15 extend.
- The dependencies in the task list name them.

## 9. Outside facts to fetch and log before building

Fetch each of these (do not recall it) and log it in `docs/plans/Verification_Log.md` with its source:
- the current ISO/IEC 27001 edition, its stage, and Amd 1:2024;
- the catalogue page and any per-standard feed;
- the Annex A exclusion rule;
- the IAF MD 26 transition dates;
- the ISO/IEC 17021-1 certification cycle;
- ISO's systematic review cycle;
- the Nordic national adoptions;
- the PCI DSS version and its retirement practice;
- the Swift CSCF attestation window;
- the licence and website terms of ISO, IAF, PCI SSC, SIS, DS, Standard Norge and SFS, including ISO's text-and-data-mining reservation.

The research reports 403 errors and Cloudflare challenges on some of these pages. A row that cannot be fetched is logged as not verified, with the reason.


---

# Appendix: prd_bump_markdown

# PRD bump: 0.2 to 0.3 (proposed; Alex decides)

Nothing below is in `PRD.md` yet.
- `MY_WORK_AND_MARKETS.md` drafts a 0.3 of its own. The orchestrator merges both into one 0.3; TEN-02 is changed by both.
- The kind additions at the end need rows in `docs/inputs/INPUT_DELTAS.md` §1.
- The acceptance criterion AC-FP3, the journey J-10 and the new scenario IDs are provisional: AC-FP2, J-9 and several scenario IDs are already claimed by the parallel documents.

## Version row

| 0.3 | on acceptance | Standards within the sector scope. A standard is an instrument per edition that holds public facts and one conformance duty. Tenants follow standards through an opt-in dimension of the regulatory scope. A legal entity follows a standard through approved applicability and records its certificate on its licence row. Units in the tenant's own words, per entity, form the Statement of Applicability. Standards are watched from public metadata. The regime list is the enforced sector boundary | Alex |

## §1 Product: sharpened paragraphs

**Sector scope.** Compliance Watch covers regulated financial services only: banking, payments, investment services, insurance and pension provision, and asset and wealth management. It also covers the AML, data protection and ICT-risk regimes that apply to them, and the tax and AI rules as they apply to financial firms and their products. It is not a general-purpose or multi-industry GRC product. It is not built for, and has no path to, other regulated sectors such as healthcare, life sciences, construction, environmental compliance or workplace safety. The regime list is the boundary: every instrument and every change carries a regime from it. Nothing outside this scope enters the library, even when one of a tenant's entities holds it (for example ISO 9001, ISO 14001 or ISO 45001).

*(Naming tax and AI is the sector-vocabulary default. Alex confirms, together with REGULATORY_SCOPE.md §12.)*

**Standards and certifications.** Within that scope, a firm may follow a standard by choice, by contract or because a supervisor expects it, and such a standard is handled like regulation. Examples are information-security, business-continuity, privacy and payment-card standards, such as ISO/IEC 27001.
- **In the library.** Each edition is an instrument in the shared library. It holds the standard's public facts and one duty to conform, written in our own words. The library never holds a standard's licensed text, its clause or control titles, or a paraphrase of them.
- **Opting in.** A tenant opts in through its regulatory scope. Only then do the standard's records match.
- **Per legal entity.** An entity follows the standard when its applicability is approved, and it records any certificate with its issuer, scope, validity and next audit.
- **Statement of Applicability.** For each entity that follows a standard, the tenant lists the clauses and controls it works with, by reference and in its own words. Each has applicability with a reason, a status and gaps. Together they are the Statement of Applicability.
- **Watch.** Revisions and transition deadlines are watched like any change.
- **Out of scope.** Testing the controls, the standard's own risk assessment and treatment plan, and certificates received from suppliers.

**Out of scope by decision.** Control testing, policy management, incidents, and risk registers (including a standard's risk assessment and treatment plan), and certificates or assurance reports received from suppliers. Obligations carry linked internal items, and the API lets an existing GRC system integrate.

## §3 Requirements: changed and new rows

### FP (changed)
| ID | Requirement | P | R |
|---|---|---|---|
| FP-01 | Footprint across all taxonomy dimensions. A record matches when every dimension it carries has a term in the footprint. An empty dimension does not restrict, except the standards dimension: a record carrying a standard matches only when the footprint names that standard. An obligation also needs its instrument's regime in the footprint | M | R1 |

### INV (changed and new)
| ID | Requirement | P | R |
|---|---|---|---|
| INV-01 | Instruments with level (a standard's level says so), binding force, official reference, ELI where available, jurisdiction (International for standards bodies), authority, a regime, in-force dates and lineage | M | R1 |
| INV-02 | Provision tree with verbatim text versions, in-force dates and transitional notes. Never for a standard, whose text is licensed | S | R1 |
| INV-08 | Standards within the sector scope as instruments, one per edition. Each holds publisher, reference, dates, lifecycle, national adoptions as a note, a catalogue link, and exactly one conformance duty in our own words, which carries the standard's term. Only a standard's own records carry a standard term. There is no standard text, clause or control title, or paraphrase in the library, the search index, Ask or agent output | M | R1 |

### WAT (changed and new)
| ID | Requirement | P | R |
|---|---|---|---|
| WAT-03 | Change types, flags and scope from vocabularies, with at least one regime on every change and a standard term only on a change from a standards body. Agent classifications shown as suggestions until confirmed | M | R1 |
| WAT-07 | Standards are watched from public metadata: one change per edition or amendment, with a timeline from draft to publication and a key date for the end of the transition. A publisher's page keeps no snapshot, and automated checks run only on publishers whose terms allow them | S | R1 |

### AGT (new)
| ID | Requirement | P | R |
|---|---|---|---|
| AGT-08 | Agents stay inside the sector scope. An out-of-scope document is logged as a source check and counted, and nothing is registered or proposed. A standard's text is never fetched, quoted, summarised, translated or restated from memory. A blocked page is a failed check and is never worked around. A law that cites a standard never carries the standard's term | M | R1 |

### TEN (changed; merge with the departments wording of the parallel bump)
| ID | Requirement | P | R |
|---|---|---|---|
| TEN-02 | Legal entities with licences and certificates (issuer, reference, scope, validity, next audit, owner), and products described the way obligations are scoped | M | R2 |

### REG (changed and new)
| ID | Requirement | P | R |
|---|---|---|---|
| REG-01 | Applicability per obligation, per legal entity where it spans several, and per unit of a standard, with a reason. It changes only through a request that a second person approves. Many pending requests can be decided in one call, with four eyes on every row | M | R2 |
| REG-08 | Statement of Applicability. For each legal entity that follows a standard, the tenant lists the clauses and controls it works with as units, by reference and in its own words, entered one by one or pasted with a dry run. Each unit has applicability with a reason, a status and gaps. A unit's reference and words are fixed once it has history. The register filtered by standard and entity is the Statement of Applicability. Nothing written under a standard is indexed, sent to a model or shown to another tenant | M | R2 |

### HOM (changed)
| ID | Requirement | P | R |
|---|---|---|---|
| HOM-03 | Roadmap page by quarter, with regulatory dates and our own deadlines, a card expanding in place. From R2, our own deadlines include a certificate's expiry and next audit, which never reach the calendar feed | M | R1 |

### REP (changed)
| ID | Requirement | P | R |
|---|---|---|---|
| REP-02 | Committee pack and exports of inventory (including a dated Statement of Applicability per standard and entity), changes, cases and the audit log | S | R3 |

Unchanged on purpose:
- REG-05, REG-07 and REP-03.
- I18N-01. It asks for jurisdictions as data, which one more row satisfies. INV-08 names the International row, and I18N-S1 is amended.

## §4 Acceptance criteria (new)

- **AC-FP3** A tenant whose regulatory scope names no standard sees no standard's obligations or changes. Its case for a standard's change is created with `footprint_match` false and appears in neither its feed nor its roadmap. After an approved change adding ISO/IEC 27001, it sees them. A law's obligation or change never carries a standard term.
- **AC-INV2** A provision or provision-version proposal under a standard is refused at creation, through POST /proposals and the agent API, with 422 `licensed_text`. A provision row under a standard is refused by the database. The Ask evaluation row about a standard's control expects "no answer", and it gates the release.
- **AC-REG1** An approver with a fresh step-up decides 93 pending unit requests for one entity in one call, and 93 audit rows are written. A call that includes a request the caller filed answers 409 `four_eyes_violation` and decides nothing.
- **AC-REG2** Nothing a tenant writes under a standard (units, notes, gaps, assessments, interpretations, links) appears in a search chunk, an embedding input or an AI-generation input. Tenant B receives 404 for it.
- **AC-TEN1** A certificate's expiry and next audit appear on the roadmap as "Our deadline" with its owner. They disappear once it is withdrawn, and never appear in the calendar feed.
- **AC-AGT1** A change without a regime answers 422 `regime_required`. The evaluation set scores in-scope and standard-term accuracy on out-of-sector texts and on a law that cites a standard, and the release gate fails below tolerance.

## §5 Golden-path journey (new, R2)

| ID | Path |
|---|---|
| J-10 | The officer adds ISO/IEC 27001 to the regulatory scope, and an approver approves it with step-up. The officer records the certificate on an entity and requests "applies" for that entity with the reason "Certified", and the approver approves it. The officer pastes three units with applicability, and the approver decides them in one call. The register filtered by standard and entity shows the decisions, and the next audit is on the roadmap |

## §6 Permissions

No new permission.

| Action | Permission | Safeguard |
|---|---|---|
| Admit a standard term, instrument, conformance obligation or standards-body source | `proposals.create`, or an agent key proposes; then `proposals.review`; `sources.manage` | Four eyes and step-up (PRO-02). The standards check at creation, correction and apply |
| Follow or stop following a standard, for the tenant | `footprint.request`, then `footprint.approve` | Four eyes and step-up (FP-02) |
| An entity follows a standard | `applicability.request`, then `applicability.approve` | Four eyes and step-up (REG-01) |
| Record a certificate on an entity | TEN-S2's entity permission (`vocab.manage`) | Audited. It decides no span |
| Add, paste, edit or remove units | `register.edit`, plus `applicability.request` when the paste carries applicability | `If-Match`. Fixed once there is history. One audit event per row |
| Decide many pending requests in one call | `applicability.approve` | Step-up. Four eyes on every row. Capped |
| Status, gaps, risk acceptance | `register.edit`, `gaps.edit`, `risk.accept.approve` | As REG-02 and REG-03 |
| SoA export | `exports.create` | Step-up (R3) |

## §7 Release plan and Build_Plan

- **R1 outcome** adds: "follow a standard through the regulatory scope and watch its revisions".
- **R2 outcome** adds: "legal entities follow standards and hold certificates, with a Statement of Applicability per entity".
- **Chunk table:**
  - Chunk 2 carries the amended FP-01.
  - Chunk 3 adds INV-08 (level kind, International, regime required, the provision trigger, the pill).
  - Chunk 4 carries the standard-term checks on `new_obligation_version`.
  - Chunk 5 adds WAT-07, AGT-08 and the rest of INV-08's proposal checks.
  - Chunk 8 adds REG-08 and the amended TEN-02 and REG-01.
  - Chunk 12 carries the amended REP-02.

## Kinds (tier 1, `INPUT_DELTAS` §1; authorised by this bump)

- `term_dimension_kind` gains `opt_in`.
- A new, optional `instrument_level_kind` with the single value `standard`.
- `jurisdiction_kind` gains `international`.

## Scenarios to amend when the bump lands

- **Taxonomy:**
  - FP-S1: an obligation also needs its instrument's regime, and an opt-in term matches only when named.
  - I18N-S1: the International row, and the test's expected set.
- **Library:**
  - INV-S1: `bindingLevel.kind`.
  - INV-S2: never for a standard.
  - INV-S3: the header slot "Standard".
- **Proposals:** PRO-S9, the reason row "Outside the sector scope".
- **Agents:** AGT-S3, the extra vocabularies.
- **Tenants:** TEN-S2, the certificate fields on the licence row.
- **Register:**
  - REG-S1: per entity.
  - REG-S3: the per-entity reason.

## New scenarios (provisional IDs)

- **Taxonomy:** FP-S14 and FP-S15.
- **Library:** INV-S11 and INV-S12.
- **Proposals:** PRO-S10 and PRO-S11.
- **Watch:** WAT-S10 and WAT-S11.
- **Agents:** AGT-S12.
- **Search:** SRC-S12 and SRC-S13.
- **Tenants:** TEN-S10.
- **Register:** REG-S12 to REG-S16.
- **Home:** HOM-S15.
- **Reports:** REP-S6.


---

# Appendix: decisions

```json
{
 "id": "std-library-facts-only",
 "decision": "What the shared library holds for a standard",
 "default": "Public facts only: publisher, reference, edition, dates, lifecycle, national adoptions as a note, and a catalogue link. Plus exactly one active conformance obligation per edition, written in our own words. Its ref_label equals the official reference, and it carries exactly one standard term. There are no provisions, no clause or control titles and no paraphrase. One check function refuses anything else at proposal creation (POST /proposals and the agent API), at a reviewer's correction and at apply, with 422 licensed_text, one_conformance_obligation or standard_term_required. Field sources on a standard's records must be URLs. A trigger on provision refuses any row under a standard-level instrument, and check_prototype_data.py refuses one too.",
 "why": "The library holds sourced public facts (CLAUDE.md §1, playbook 4.3), and clause content exists only in the paid standard. A proposal payload is stored at creation, so a check only at apply would leave pasted text in the platform database. library_write() also admits seeds, the watch pipeline and INV-07 (shared/tenancy.py:133), and the trigger covers all three. The licensing research reports ISO ECLA §6(b) and §7(b) and PCI SSC's terms (unverified). Holding clause titles would change an invariant, so that is a stop-and-ask, not a default.",
 "owner_confirms": "Before any standard is seeded. The lawyer confirms the official title and the conformance wording. No collision."
}
```
```json
{
 "id": "std-opt-in-dimension",
 "decision": "How a tenant opts in to a standard",
 "default": "A dimension 'standard' (\"Standards followed\") with a new tier-1 kind, opt_in. A record carrying one of its terms matches only when the regulatory scope names that term, including when the scope has no term in the dimension. The rule lives in the matcher: an opt_in dimension restricts whatever restricts_footprint says, in restricting_dimensions() and in the SQL join, so no guard is needed on the flag. opt_in is a required keyword of in_footprint. There is one term per standard, not per edition. An opt-in term may sit only on a standard's own obligation (checked at creation, correction and apply) and on a change whose authority's jurisdiction kind is international (createChange and change corrections). Both answer 422 standard_term_only_on_standards. Opt-in dimensions gate at tenant level only, and an entity's span leaves them out.",
 "why": "FP-01's rule that an empty dimension means everything would mark every standard as matching every tenant. A standard term on a law would hide binding law from every tenant that does not follow the standard, with no preview and no second person. A guard on the flag at two call sites would still leave seeds and migrations open.",
 "owner_confirms": "With the PRD 0.3 wording of FP-01. It interacts with REGULATORY_SCOPE.md: scopeGroups() and narrowedGroups() must treat opt-in groups as revealing. It also interacts with the markets analysis, which should reuse opt_in if watched markets ever need 'empty matches nothing'."
}
```
```json
{
 "id": "std-level-kind",
 "decision": "How an instrument says it is a standard",
 "default": "An optional tier-1 InstrumentLevelKind with the single value 'standard' (registry kinds=(\"standard\",), kind_required=False), plus one level row, 'standard', with binding_default false. The five existing levels keep a null kind, and binding keeps deciding their pills. When bindingLevel.kind is standard, both binding slots read 'Standard' in the information tone. There is no relabel guard, because relabel payloads carry no kind (proposals/schemas.py:41-47, apply.py _vocabulary_relabel).",
 "why": "binding=false renders 'Guidance, comply or explain', which is wrong for a standard. Only 'standard' has a reader. Law and guidance values would be a second source beside binding_default that could disagree with it. The contract's {key, kind, label} already exists, so this adds no contract change.",
 "owner_confirms": "The pill wording and tone, on a design card. No collision."
}
```
```json
{
 "id": "std-international-jurisdiction",
 "decision": "Jurisdiction for international standards bodies",
 "default": "One seeded row, 'intl' ('International'), with a new JurisdictionKind, international. The jurisdiction list is seeded, not proposed. The authority iso-iec is seeded with the first standard. iaf is added with the first IAF-sourced change in chunk 5. A standard's obligations carry no jurisdiction term. I18N-S1 and its exact-set test gain the row.",
 "why": "Instrument.jurisdiction and Authority.jurisdiction are required, and the kinds today are supranational and country. Two rules must tell an international issuer from the EU by kind, never by key. The first is the watch rule that allows a standard term only on a change from an international issuer. The second is the markets analysis's derivation, which would otherwise give every standard a jurisdiction term and hide it from any tenant with an operating market.",
 "owner_confirms": "Collides with the markets analysis (MY_WORK_AND_MARKETS.md §4.2): its derivation must derive nothing for kind international, and create no mirror term for intl."
}
```
```json
{
 "id": "std-regime-boundary",
 "decision": "How the regime enforces the sector scope",
 "default": "Instrument.regime becomes NOT NULL. The seed-integrity test and chunk 5's instrument-proposal apply check that it is a term of the regime dimension (422 not_a_regime). Chunk 3 already plans to fold the instrument's regime into obligation matching (obligation_scopes(), CHUNK3_TASKS.md:40). FP-S1 and the matching.py docstring are amended to match. Every change carries at least one regime term (422 regime_required). A standard takes the regime of the family of law it serves: ai_ict for ISO/IEC 27001, data_protection for 27701, payments for PCI DSS.",
 "why": "schema.sql has the regime NOT NULL, but library/models.py:196 makes it nullable, and an instrument without a regime matches every tenant. The regime list is the one closed list that changes only through a reviewed proposal.",
 "owner_confirms": "No product change. The markets derivation sits in the same obligation_scopes() rule, and both share it."
}
```
```json
{
 "id": "std-sector-vocabulary",
 "decision": "Scope edges and vocabulary inside the scope",
 "default": "Keep tax (tax rules for financial products and the duties a firm carries for its clients) and the AI Act (under ai_ict), and name both in the PRD's scope sentence. The Banking and Payments regimes come from REGULATORY_SCOPE.md T01. The PRD's six sectors become terms of the existing, termless licensed_activity dimension, added by proposal. Regime terms are added only for a body of law an instrument needs. No new legal_entity types until licensed_activity has been checked. This analysis adds no rows itself.",
 "why": "licensed_activity ('The licence under which the firm acts', taxonomy/seeds/__init__.py) exists for exactly these sectors. REGULATORY_SCOPE.md already adds the two regimes and asks the firm-type question in its §12.",
 "owner_confirms": "The PRD sentence, the licensed_activity terms, and whether SFDR, consumer credit and the Accessibility Act as applied to banking are in scope. This is the same question as REGULATORY_SCOPE.md §12, answered once."
}
```
```json
{
 "id": "std-units-in-tenant-zone",
 "decision": "Where the Statement of Applicability's clause and control list lives",
 "default": "A tenant table, soa_unit, under forced RLS, with one row per unit per legal entity. Its columns are scope_id (the conformance obligation's scope row), unit_ref, title (in the tenant's own words), applicability, applicability_reason, applicability_decided_at, compliance_status, status_note, version and created_by, with UNIQUE (scope_id, unit_ref). A unit is allowed only when the scope row's obligation sits under a standard-level instrument (422 units_only_under_standards) and its applicability is 'applies' (422 scope_not_applicable). unit_ref and title are fixed once the unit has a request, a decision or a gap (409 unit_has_history). Applicability changes only through applicability_request, which gains a nullable unit_id. gap gains unit_id. tenant_obligation keeps UNIQUE (tenant_id, obligation_id). Fallback if the lawyer objects: ship chunk 8 without soa_unit, and use the conformance row per entity with the tenant's own SoA as evidence.",
 "why": "The tenant holds the licence and already keeps an SoA. The shape follows the planned requirement_status and gap.requirement_id (schema.sql:1556, :1571). obligation_requirement cannot be used, because its text columns sit in the library. Units as extra tenant_obligation rows would inflate HOM-01's standing, REP-01's heatmap and the review_due roadmap branch. Fixing the reference and title stops an approved decision being moved to another control by a rename.",
 "owner_confirms": "A lawyer's view before the first bank uses units (ISO §6(b), as reported). No collision."
}
```
```json
{
 "id": "std-entity-follows-by-applicability",
 "decision": "How a legal entity follows a standard",
 "default": "The per-entity applicability of the conformance obligation is the only record that an entity follows a standard: an approved 'applies' with a reason such as 'Certified' or 'Card-scheme contract'. The conformance obligation carries no entity term, so it spans every legal entity. applicability_request gains a nullable scope_id, and the one-pending index covers (tenant_obligation_id, scope_id, unit_id) NULLS NOT DISTINCT. tenant_obligation_scope gains applicability_reason and applicability_decided_at. A scope row is created, through record(), in the transaction of the request that needs it; reads never write. Removing a standard from the regulatory scope hides its rows and deletes none.",
 "why": "A second 'follows' record, such as a licence row carrying the standard, could disagree with applicability. It would also move a fact that decides the span out from behind four eyes. PRD 0.2 says standards are worked through applicability per legal entity.",
 "owner_confirms": "Collides with the markets analysis if markets per entity feed chunk 8's span: that span must leave opt-in dimensions out."
}
```
```json
{
 "id": "std-certificate-on-licence",
 "decision": "Where a certificate lives",
 "default": "The entity's planned licence row. It uses the existing columns (licence_type, for example 'ISO/IEC 27001:2022 certificate, issued by …'; reference; granted_on; withdrawn_on; scope_note) and adds valid_until, next_audit_on and owner_id. It carries no term and decides no span. Two roadmap branches, licence_expiry and licence_audit, are of kind internal: they show 'Our deadline' with the row's owner, are left out once withdrawn_on is set, and never enter the calendar feed. Surveillance audits are not a recurring_duty, and REG-07 is unchanged.",
 "why": "A certificate is held by one entity, like a licence. Evidence has no per-entity anchor, and the review_due branch hides compliant rows, so a certified, compliant entity's next audit would vanish from the roadmap there. The calendar feed carries public facts only (home/app.md §3).",
 "owner_confirms": "The owner shape (a person or a team) with the my-work analysis. My Work may list these dates."
}
```
```json
{
 "id": "std-bulk-decide",
 "decision": "How many applicability requests are decided at once",
 "default": "No batch table. One route, under applicability.approve and @requires_step_up, takes [{requestId, decision, note}] over pending requests. It decides each one through the single-request logic, in one transaction. A request the caller filed answers 409 four_eyes_violation, and nothing is decided. The route writes one record() per row, citing the assertion. REGISTER_BULK_MAX caps it (default 100, the page maximum). A pending request cannot be edited; the requester withdraws it. The unit paste accepts optional applicability and reason columns and files one pending request per row. The approver's filtered queue is the preview.",
 "why": "Step-up is a freshness window: enforce_step_up (permissions.py:462) accepts any assertion younger than STEP_UP_FRESHNESS_MINUTES (default 5). The earlier 'about 300 step-ups' was therefore wrong. A batch table would duplicate each request's status, decider and four-eyes CHECK. A cap of 100 keeps each call inside the 250 ms budget.",
 "owner_confirms": "The cap. Pending requests appear in approvers' queues (the my-work analysis)."
}
```
```json
{
 "id": "std-watch-manual-first",
 "decision": "How standards are watched",
 "default": "One change per edition or amendment, keyed by stable key. The draft, final draft, publication and accreditation transition rule are timeline entries, the change type follows the stage (WAT-02), and the end of the transition is the key date. Standards-body sources get a source_kind row, standards_body, and are registered inactive, with no automated check, until the lawyer answers. A person enters edition facts as instrument proposals. A source_document on a host in the setting STANDARDS_PUBLISHER_HOSTS keeps no snapshot. A change that carries an opt-in term may link only documents without a snapshot (422 licensed_text). The prompt says never to fetch, quote, summarise, translate or restate a standard's text, and that a 403 or a challenge is a failed source check that is never worked around.",
 "why": "ISO reportedly reserves text-and-data mining, and its site blocked automated fetches during the research. source_check has no URL, hash or snapshot (schema.sql:278-287). Snapshots live on source_document (:1362-1377), which has no source_id, so a flag on the source kind could not stop them. WAT-02 already means one record per reform. CAS-01 already caches footprint_match per tenant.",
 "owner_confirms": "A lawyer's view on automated monitoring of publishers' pages, and which publishers may be read automatically (IAF documents first). Until one is cleared, a revision opens no case, because POST /changes is agent-only."
}
```
```json
{
 "id": "std-soa-view-and-export",
 "decision": "When the Statement of Applicability becomes a document",
 "default": "In R2, the register filtered by standard and entity is the SoA. For each unit it shows the reference, the title, applicability, the reason, the status, the approver and the decision date. The unit's decided requests are its history. There is no 'as of' in R2. The dated export is R3's filtered inventory export (REP-02), with no new export kind. An existing SoA enters through the chunk 8 paste, and REP-03 is unchanged.",
 "why": "Filters need no new code path, and units keep one entry path.",
 "owner_confirms": "Whether to pull a CSV export into chunk 8, because banks need the document at their certification audits."
}
```
```json
{
 "id": "std-seed-list",
 "decision": "Which standards are seeded",
 "default": "ISO/IEC 27001:2022 only, in the demo fixture (from_prototype false), once its facts are logged, and with no relation rows. The relation type 'replaces' is added by a vocabulary proposal when a second edition is entered. 'amends' is not added, because an amendment that keeps the edition is an obligation version. Other standards come by proposal. PCI DSS and the Swift CSCF stay out until their licence terms are read. ISO/IEC 42001, and ISAE 3402 or SOC reports that a tenant issues, stay out until Alex says otherwise.",
 "why": "Prove the pattern on one standard first. A lineage row needs a second instrument to point at. PRD 0.2 names information-security, business-continuity, privacy and payment-card standards, not AI management or assurance reports.",
 "owner_confirms": "The seed list. No collision."
}
```

---

# Appendix: scenarios

```json
{
 "app": "taxonomy",
 "id": "FP-S14",
 "heading": "### FP-S14 — A standard shows only to tenants whose regulatory scope names it `@integration` `@e2e` (FP-01, FP-02, INV-08, AC-FP3)",
 "gherkin": "Given the dimension \"Standards followed\" of kind opt_in with the term \"ISO/IEC 27001\"\nAnd the obligation \"ISO/IEC 27001:2022 conformance\" carrying that term under an instrument whose regime is \"AI and ICT\"\nAnd tenant A's regulatory scope holds the regime \"AI and ICT\" and no standard\nThen the obligation is absent from tenant A's inventory and appears with \"Show outside our scope\"\nAnd the regulatory scope page shows \"None followed\" for the group\nWhen a compliance officer with footprint.request proposes adding \"ISO/IEC 27001\"\nThen the preview reveals the obligation, hides nothing and shows no narrowing warning\nWhen an approver with footprint.approve and a fresh step-up approves it\nThen the obligation appears in the inventory\nAnd one audit event records the added term with the assertion reference and the request\nWhen the officer later proposes removing it\nThen the preview counts the obligation as hidden and the warning shows"
}
```
```json
{
 "app": "taxonomy",
 "id": "FP-S15",
 "heading": "### FP-S15 — The pure rule and the SQL function agree on opt-in dimensions, whatever the flag says `@integration` (FP-01)",
 "gherkin": "Given every combination of record terms and scope terms over a scope dimension and an opt-in dimension\nThen in_footprint and taxonomy_in_footprint give the same answer for each\nAnd a record carrying an opt-in term matches only when the scope names that term, also when the scope has no entry for the dimension\nAnd an empty scope dimension still does not restrict\nAnd a record carrying no opt-in term is unaffected by the opt-in dimension\nWhen the opt-in dimension's restricts_footprint is false\nThen both still treat it as restricting\nAnd calling in_footprint without the opt_in argument raises a TypeError"
}
```
```json
{
 "app": "library",
 "id": "INV-S11",
 "heading": "### INV-S11 — An edition of a standard is an instrument with public facts and no text `@integration` `@e2e` (INV-01, INV-02, INV-08)",
 "gherkin": "Given the instrument \"ISO/IEC 27001:2022\" at the level \"Standard\" under the jurisdiction \"International\" and the authority \"ISO/IEC\"\nThen it holds its official reference, publication date with precision, catalogue link and regime\nAnd the API returns bindingLevel with kind \"standard\", and a null kind for every other level\nAnd the obligation header and the obligation row show \"Standard\" in the binding slot, never \"Guidance, comply or explain\"\nAnd the provision tree reads \"The text of this standard is licensed and not held here\" with the catalogue link\nAnd the instrument has exactly one obligation and no provision"
}
```
```json
{
 "app": "library",
 "id": "INV-S12",
 "heading": "### INV-S12 — Every instrument carries a regime from the regime dimension `@integration` (INV-01, INV-08)",
 "gherkin": "Given an instrument row written without a regime\nThen the database refuses it\nAnd every seeded instrument's regime is a term of the regime dimension\nWhen an instrument proposal names a term of the dimension \"Service\" as its regime and a library editor approves it\nThen the apply answers 422 with code \"not_a_regime\" and nothing is written"
}
```
```json
{
 "app": "proposals",
 "id": "PRO-S10",
 "heading": "### PRO-S10 — Licensed text and extra obligations never enter a standard `@integration` (INV-08, PRO-01, PRO-02, AC-INV2)",
 "gherkin": "Given the instrument \"ISO/IEC 27001:2022\" whose level kind is standard\nWhen a provision or provision_version proposal on it is submitted through POST /proposals or the agent API\nThen it is refused at creation with 422 \"licensed_text\" and no proposal row is stored\nWhen a proposal for its conformance obligation carries a field source that is not a URL\nThen it is refused at creation with 422 \"licensed_text\"\nWhen a reviewer's correction adds provision text to a pending proposal and approves it\nThen the approval answers 422 \"licensed_text\" and nothing is written\nWhen a new_obligation proposal adds a second active obligation under it\nThen the apply answers 422 \"one_conformance_obligation\"\nWhen an obligation under it carries no term of an opt-in dimension, or two\nThen the apply answers 422 \"standard_term_required\"\nAnd a provision row inserted under it directly, as a seed would, is refused by the database"
}
```
```json
{
 "app": "proposals",
 "id": "PRO-S11",
 "heading": "### PRO-S11 — A standard term never sits on a law's obligation `@integration` (FP-01, INV-08, AC-FP3)",
 "gherkin": "Given the DORA obligation \"ICT risk-management framework\" under a level whose kind is not standard\nWhen a new_obligation_version proposal adds the term \"ISO/IEC 27001\" to it\nThen it is refused at creation with 422 \"standard_term_only_on_standards\"\nWhen a reviewer's correction adds that term to a pending proposal and approves it\nThen the approval answers 422 \"standard_term_only_on_standards\" and nothing is written\nAnd a tenant whose regulatory scope names no standard still sees the obligation"
}
```
```json
{
 "app": "watch",
 "id": "WAT-S10",
 "heading": "### WAT-S10 — A new edition of a standard is one change, and only tenants that follow it see it `@integration` `@e2e` (WAT-02, WAT-07, CAS-01, AC-FP3)",
 "gherkin": "Given tenant A follows \"ISO/IEC 27001\" and tenant B follows no standard\nWhen an agent registers the change \"ISO/IEC 27001 amendment\" with the authority \"ISO/IEC\", the term \"ISO/IEC 27001\", the regime \"AI and ICT\", a draft-for-comment timeline entry and a key date labelled \"Transition ends\"\nAnd later registers the same stable key with its publication date\nThen one change exists with both timeline entries\nAnd each tenant has exactly one case for it, tenant A's matching its scope and tenant B's not\nAnd the change and the transition date appear in tenant A's feed and roadmap and in neither of tenant B's"
}
```
```json
{
 "app": "watch",
 "id": "WAT-S11",
 "heading": "### WAT-S11 — Every change carries a regime, a standard term needs a standards body, and a publisher's page keeps no snapshot `@integration` (WAT-01, WAT-03, WAT-07, AC-AGT1)",
 "gherkin": "Given an agent key with changes:write\nWhen it registers a change with no regime term\nThen the API answers 422 with code \"regime_required\" and the valid regime keys\nWhen it registers a change with the term \"ISO/IEC 27001\" whose authority is \"Finansinspektionen\"\nThen the API answers 422 with code \"standard_term_only_on_standards\"\nGiven the open web sweep fetches a page on a host listed in STANDARDS_PUBLISHER_HOSTS\nThen the stored source document holds the URL, the date and a content hash and no snapshot\nWhen a change carrying an opt-in term links a document that has a snapshot\nThen the API answers 422 with code \"licensed_text\"\nAnd a source of kind \"Standards body\" registered inactive gets no automated check"
}
```
```json
{
 "app": "agents",
 "id": "AGT-S12",
 "heading": "### AGT-S12 — Out-of-scope documents are counted and never registered, and the eval set gates it `@integration` (AGT-08, SRC-05, AC-AGT1)",
 "gherkin": "Given the classification set holds authored texts for a medical-device rule, a construction-safety rule, an environmental permit and an ISO 14001 revision, each expecting in_scope false\nAnd an authored DORA text that cites ISO/IEC 27001, expecting in_scope true and no standard term\nWhen the evaluation runs\nThen in-scope accuracy and standard-term accuracy are reported and the gate fails when either falls below its tolerance\nGiven a run that checked two out-of-scope documents\nWhen it closes with the stat out_of_scope 2\nThen the run history shows two source checks, no change and no proposal from them, and the count 2"
}
```
```json
{
 "app": "search",
 "id": "SRC-S12",
 "heading": "### SRC-S12 — A question about a standard's control gets \"no answer\" `@integration` (SRC-03, SRC-05, INV-08, AC-INV2)",
 "gherkin": "Given the library holds ISO/IEC 27001:2022 with its conformance obligation and no clause text\nWhen a user asks \"What does ISO/IEC 27001 control A.8.8 require?\"\nThen the answer is \"no answer\" and states nothing about the control\nAnd the evaluation set holds this question expecting no answer, and it gates the release"
}
```
```json
{
 "app": "search",
 "id": "SRC-S13",
 "heading": "### SRC-S13 — Nothing a tenant writes under a standard reaches the index or a model `@integration` (REG-08, SRC-01, AC-REG2)",
 "gherkin": "Given tenant A has the invented units \"X.1\" and \"X.2\" with its own titles for Example Bank AB under ISO/IEC 27001:2022\nAnd a status note, a gap, an assessment, an interpretation and an internal link on that conformance obligation\nWhen the index is rebuilt and a user of tenant A asks a question\nThen no search chunk, embedding input or AI-generation input contains text from any of those rows\nAnd a user of tenant B searching those titles finds nothing and receives 404 for the rows"
}
```
```json
{
 "app": "tenants",
 "id": "TEN-S10",
 "heading": "### TEN-S10 — A legal entity records a certificate it holds `@integration` `@e2e` (TEN-02, AC-TEN1)",
 "gherkin": "Given an admin with vocab.manage and the legal entity \"Example Bank AB\"\nWhen they record the licence \"ISO/IEC 27001:2022 certificate, issued by Example Certification AB\" with a certificate number, a scope statement, an issue date, valid until 2028-11-30, next audit 2027-03-15 and an owner\nThen the entity screen lists it under \"Licences and certificates\" with its validity and next audit\nAnd the write is audited with before and after values\nAnd no obligation, scope row or applicability changes\nWhen they set a withdrawal date\nThen the row reads as withdrawn and stays in the history"
}
```
```json
{
 "app": "register",
 "id": "REG-S12",
 "heading": "### REG-S12 — A legal entity follows a standard when its applicability is approved `@integration` `@e2e` (REG-01, REG-02)",
 "gherkin": "Given tenant A follows \"ISO/IEC 27001\" and has the entities \"Example Bank AB\", \"Example Fonder AB\" and \"Example Liv Försäkring AB\"\nThen the conformance obligation offers every legal entity, and reading it writes no scope row\nWhen an officer with applicability.request requests \"Applies\" for Bank AB with the reason \"Certified\" and \"Does not apply\" for Liv with a reason\nThen each request carries its entity's scope row, created in the same transaction, and no other row changes\nAnd a second pending request for Bank AB answers 409\nWhen an approver with applicability.approve and a fresh step-up approves both\nThen Bank AB's row reads \"Applies\" with its reason and decision time, and Liv's reads \"Does not apply\"\nAnd the obligation row shows the worse of its entity statuses as its pill"
}
```
```json
{
 "app": "register",
 "id": "REG-S13",
 "heading": "### REG-S13 — A tenant lists its clauses and controls as units in its own words `@integration` `@e2e` (REG-08)",
 "gherkin": "Given Bank AB's conformance row for ISO/IEC 27001:2022 applies, and an officer with register.edit\nWhen they paste 12 lines for Bank AB, each an invented reference and their own title such as \"X.1\tExample control\"\nThen a dry run lists the rows it will create and refuses duplicate references and over-long lines\nWhen they commit\nThen 12 units exist for Bank AB, each with one audit event\nAnd the form offers no field for the standard's text and asks for their own words\nWhen they add a unit for Liv, whose conformance row does not apply\nThen the API answers 422 with code \"scope_not_applicable\"\nWhen they add a unit under an obligation whose instrument is not a standard\nThen the API answers 422 with code \"units_only_under_standards\"\nWhen they rename a unit that has an applicability request\nThen the API answers 409 with code \"unit_has_history\" and the unit is unchanged\nAnd a unit with no history can be renamed with If-Match or removed, each audited"
}
```
```json
{
 "app": "register",
 "id": "REG-S14",
 "heading": "### REG-S14 — Unit decisions are filed from the paste and decided in one call, with four eyes on every row `@integration` `@e2e` (REG-01, REG-08, AC-REG1)",
 "gherkin": "Given an officer with register.edit and applicability.request pastes 93 invented units for Bank AB, each with \"applies\" or \"does not apply\" and a reason\nThen 93 pending applicability requests exist, each naming its unit, and none can be edited\nWhen the officer, who also holds applicability.approve, decides them in one call\nThen the API answers 409 with code \"four_eyes_violation\" and nothing is decided\nWhen an approver with applicability.approve and a fresh step-up approves 90 and rejects 3 with a note in one call\nThen each unit carries its own decision, reason and time, and 93 audit events cite the assertion\nAnd a call with more requests than the configured cap is refused"
}
```
```json
{
 "app": "register",
 "id": "REG-S15",
 "heading": "### REG-S15 — The register filtered by standard and entity is the Statement of Applicability `@integration` `@e2e` (REG-08)",
 "gherkin": "Given Bank AB's decided units under ISO/IEC 27001:2022\nWhen the officer filters the register by that standard and by Bank AB\nThen each unit shows its reference, the tenant's title, applies or does not apply, the reason, the status pill, the approver and the decision date\nAnd each unit's history lists its decided requests with who and when\nAnd the conformance row shows its own assessed status, and no status is computed from the units\nAnd Today's standing counts the standard as one obligation"
}
```
```json
{
 "app": "register",
 "id": "REG-S16",
 "heading": "### REG-S16 — J-10: a legal entity follows a standard from regulatory scope to Statement of Applicability `@e2e` (FP-02, TEN-02, REG-01, REG-08, J-10)",
 "gherkin": "Given the seeded compliance officer and approver of tenant A\nWhen the officer adds \"ISO/IEC 27001\" to the regulatory scope and the approver approves it with a passkey step-up\nAnd the officer records the certificate on Example Bank AB with its next audit date\nAnd requests \"Applies\" for Bank AB with the reason \"Certified\", which the approver approves with a passkey step-up\nAnd the officer pastes three invented units with applicability and reasons\nAnd the approver decides all three in one call with a passkey step-up\nThen the register filtered by ISO/IEC 27001 and Example Bank AB shows the three decisions\nAnd the roadmap shows the next audit as \"Our deadline\""
}
```
```json
{
 "app": "home",
 "id": "HOM-S15",
 "heading": "### HOM-S15 — A certificate's expiry and next audit are our deadlines, never in the calendar feed `@integration` `@e2e` (HOM-03, HOM-04, TEN-02, AC-TEN1)",
 "gherkin": "Given Example Bank AB's licence \"ISO/IEC 27001:2022 certificate\" valid until 2028-11-30, with the next audit on 2027-03-15 and an owner\nWhen the roadmap for Q1 2027 is read\nThen the audit appears as \"Our deadline\" with that owner, naming the certificate and the entity\nWhen the roadmap for Q4 2028 is read\nThen the certificate's expiry appears as \"Our deadline\"\nAnd the user's calendar feed contains neither item\nWhen the licence is withdrawn\nThen neither date appears on the roadmap"
}
```
```json
{
 "app": "reports",
 "id": "REP-S6",
 "heading": "### REP-S6 — The Statement of Applicability exports as a dated inventory export `@integration` (REP-02, REG-08)",
 "gherkin": "Given a user with exports.create and a fresh step-up\nWhen they export the inventory filtered by ISO/IEC 27001:2022 and Example Bank AB\nThen the job produces a file carrying its export date and, per unit, the reference, the tenant's title, applicability, reason, status, approver and decision date\nAnd the export writes one audit event\nAnd the request returns before the file is built"
}
```

---

# Appendix: placement

```json
{
 "part": "Number and record the decisions as DECISIONS rows and ADRs, add the INPUT_DELTAS rows, and log the outside facts and the TODO items",
 "chunk": "Docs, now",
 "depends_on": "The orchestrator numbering the decisions of all three analyses",
 "why": "Every DECISIONS entry needs an ADR (docs/adr/README.md). The parallel analysis already claims D-18 onward. Outside facts must be fetched before anything is seeded"
}
```
```json
{
 "part": "PRD 0.3 bump, Build_Plan chunk table, app.md rows and scenarios, skipped stubs, journey fixme stubs and backlog entries, all in one commit",
 "chunk": "Docs, after Alex accepts",
 "depends_on": "Alex's acceptance, and the merge with MY_WORK_AND_MARKETS.md's bump",
 "why": "requirements_coverage.py fails when a PRD requirement has no scenario or an @e2e heading has no journey test, so these cannot land in separate commits"
}
```
```json
{
 "part": "The opt_in kind in the matcher, the pure rule, the SQL twin and the mirror suites, the standards dimension and its first term",
 "chunk": "A follow-up to chunk 2 (a built chunk). Buildable now",
 "depends_on": "The PRD bump for FP-01. REGULATORY_SCOPE T01 and T02 and chunk4-T2, which own the taxonomy models, migration numbers and seeds",
 "why": "Without it every standard matches every tenant. It touches built, mirrored code, so it lands before any record carries a standard term"
}
```
```json
{
 "part": "Opt-in groups on the Regulatory scope page ('None followed', never narrowing)",
 "chunk": "Chunk 2 or 3 screens",
 "depends_on": "REGULATORY_SCOPE T06 and T07 (scopeGroups, the page)",
 "why": "The empty-group copy and the narrowing warning are both wrong for an opt-in group"
}
```
```json
{
 "part": "The optional standard level kind, the International jurisdiction, regime NOT NULL, the provision trigger, the 'Standard' pill and the empty provision state",
 "chunk": "Chunk 3. Buildable now",
 "depends_on": "chunk3-rest-T1 (library migrations), T5 (presentation), T13 and T18 (instrument reads and tree), and the markets task that seeds jurisdiction mirror terms",
 "why": "The contract's {key, kind, label} already exists, so these are additive. The trigger belongs with the level kind"
}
```
```json
{
 "part": "ISO/IEC 27001:2022 in the demo fixture",
 "chunk": "Chunk 3",
 "depends_on": "The opt-in seed, the level kind, intl, regime NOT NULL, and the Verification_Log rows",
 "why": "E2E and the eval rows need one real standard, and seeding needs verified facts"
}
```
```json
{
 "part": "The standards check function for new_obligation_version's terms, and the out_of_scope rejection-reason row",
 "chunk": "Chunk 4",
 "depends_on": "chunk4-T1, T2 and T6",
 "why": "Chunk 4 builds only new_obligation_version, which can change scope terms. Rejection reasons are rows (chunk4-T2)"
}
```
```json
{
 "part": "The check function extended to the instrument, obligation and provision kinds; watch rules (regime_required, standard terms, no snapshots, the standards_body source kind); the prompt, definition, evals and in-scope scoring",
 "chunk": "Chunk 5",
 "depends_on": "Chunk 5's proposal kinds, source documents, createChange, CAS-01 and agent runs",
 "why": "The kinds, the sources and the agent API all arrive in chunk 5. Watch v1 is still a draft, so it is edited in place"
}
```
```json
{
 "part": "Roadmap for standards in R1",
 "chunk": "Chunk 6, nothing new",
 "depends_on": "Chunk 5",
 "why": "Transition key dates reach the roadmap through the change_date branch, filtered by footprint_match"
}
```
```json
{
 "part": "The Ask 'no answer' eval row",
 "chunk": "Chunk 7",
 "depends_on": "The demo fixture and chunk 7's Ask",
 "why": "Guards against training-data leakage of licensed text"
}
```
```json
{
 "part": "Certificate columns on the licence row",
 "chunk": "Chunk 8 (R2)",
 "depends_on": "Chunk 8's org_unit and licence work (TEN-02), and the owner shape from the my-work analysis",
 "why": "licence is not built yet. The columns ride on it"
}
```
```json
{
 "part": "Per-entity applicability, soa_unit, the paste, the bulk decision, the SoA view, the per-row guard test and J-10",
 "chunk": "Chunk 8 (R2)",
 "depends_on": "Chunk 8's tenant_obligation, scope and applicability_request, and a lawyer's view before the first bank uses units",
 "why": "All of it is register code. The guard test must exist before D-10 is relaxed at R2"
}
```
```json
{
 "part": "Roadmap branches licence_expiry and licence_audit, left out of the calendar feed",
 "chunk": "Chunk 8 (view migration)",
 "depends_on": "The licence columns, chunk 6's v_roadmap_item and feed, and chunk 8's gap and duty branches",
 "why": "The view carries tenant deadlines, and the feed carries public facts only"
}
```
```json
{
 "part": "Transition project as a case",
 "chunk": "Chunk 9, unchanged",
 "depends_on": "CAS-01 with opt-in matching",
 "why": "The case workflow already covers assessment, actions, evidence and sign-off"
}
```
```json
{
 "part": "SoA export as a filtered inventory export",
 "chunk": "Chunk 12 (R3)",
 "depends_on": "The SoA view from chunk 8",
 "why": "REP-02 is R3, unless Alex pulls a CSV into chunk 8"
}
```
```json
{
 "part": "Scope checks on the private paths (WAT-06 private sources, INV-07 private records)",
 "chunk": "Chunk 13 (R3)",
 "depends_on": "Those features",
 "why": "They bypass the editor. The required regime, the provision trigger and the prompt rule are their scope checks, and tenant-private standard instruments stay text-free"
}
```

---

# Appendix: tasks

```json
{
 "id": "STD-01",
 "title": "Record the standards decisions, ADRs and kind deltas",
 "summary": "After the orchestrator has numbered the decisions of all three analyses, add each std-* decision as a D- row with its default, why and 'Owner confirms'. Add one ADR per decision, with status 'accepted by default', and its row in the README index. Add INPUT_DELTAS §1 rows for term_dimension_kind opt_in, instrument_level_kind (standard, optional) and jurisdiction_kind international. Add delta rows for soa_unit, applicability_request.scope_id and unit_id, the scope reason columns, gap.unit_id, the licence certificate columns, Instrument.regime NOT NULL and the provision trigger.",
 "owned_paths": [
  "docs/DECISIONS.md",
  "docs/adr/",
  "docs/inputs/INPUT_DELTAS.md"
 ],
 "depends_on": [
  "orchestrator numbering across the three analyses"
 ],
 "done_condition": "There are 13 decision rows and 13 ADRs. No D- or ADR number is reused or collides with the parallel analyses. The three kind rows name the requirement they serve. compliance_check.py --all passes"
}
```
```json
{
 "id": "STD-02",
 "title": "Land the PRD bump with its specs, stubs and backlog in one commit",
 "summary": "Once Alex accepts the wording and the bump is merged with the markets and my-work bump into one 0.3, apply the version row and the §1 paragraphs. Apply FP-01, INV-01, INV-02, INV-08, WAT-03, WAT-07, AGT-08, TEN-02, REG-01, REG-08, HOM-03 and REP-02; the six criteria; J-10; the release outcomes; and the Build_Plan chunk table. In the same commit, add:\n- the app.md requirement rows;\n- every new and amended scenario;\n- one skipped test per @integration scenario;\n- one test.fixme per @e2e scenario, carrying its ID;\n- T-INV-08, T-WAT-07, T-AGT-08 and T-REG-08, with coverage-index rows.",
 "owned_paths": [
  "PRD.md",
  "docs/plans/Build_Plan.md",
  "docs/plans/Implementation_Backlog.md",
  "backend/apps/taxonomy/app.md",
  "backend/apps/library/app.md",
  "backend/apps/proposals/app.md",
  "backend/apps/watch/app.md",
  "backend/apps/agents/app.md",
  "backend/apps/search/app.md",
  "backend/apps/tenants/app.md",
  "backend/apps/register/app.md",
  "backend/apps/home/app.md",
  "backend/apps/reports/app.md",
  "backend/apps/*/tests_scenarios.py",
  "frontend/tests/e2e/taxonomy.journey.spec.ts",
  "frontend/tests/e2e/library.journey.spec.ts",
  "frontend/tests/e2e/watch.journey.spec.ts",
  "frontend/tests/e2e/tenants.journey.spec.ts",
  "frontend/tests/e2e/register.journey.spec.ts",
  "frontend/tests/e2e/home.journey.spec.ts"
 ],
 "depends_on": [
  "STD-01",
  "Alex accepts the PRD bump"
 ],
 "done_condition": "requirements_coverage.py and compliance_check.py --all pass. PRD.md reads 0.3. Every new ID appears once in PRD.md and once in the Build_Plan chunk table. No scenario ID collides with REGULATORY_SCOPE.md or MY_WORK_AND_MARKETS.md. The backend suite is green"
}
```
```json
{
 "id": "STD-03",
 "title": "Log the outside facts and the owner's TODO items",
 "summary": "Fetch each source rather than recalling it, and log each fact: the ISO/IEC 27001 edition, stage and Amd 1:2024; the catalogue page; IAF MD 26; the ISO/IEC 17021-1 cycle; the Annex A exclusion rule; the PCI DSS version; the Swift CSCF window; and the licence and website terms of ISO, IAF, PCI SSC, SIS, DS, Standard Norge and SFS. In TODO_FOR_alex.md, add the legal questions, the list of publishers to clear, the design cards, the seed list and the sector-vocabulary question.",
 "owned_paths": [
  "docs/plans/Verification_Log.md",
  "docs/TODO_FOR_alex.md"
 ],
 "depends_on": [],
 "done_condition": "Each fact is a row with its source URL and a date of 2026-09-19 or later, or a row marked not verified with its reason. The TODO lists the lawyer's questions under 'Before the first bank tenant'"
}
```
```json
{
 "id": "STD-04",
 "title": "Add the opt_in kind to the matcher and the pure rule",
 "summary": "Add OPT_IN to TermDimensionKind, with its reason in kinds.py. in_footprint takes a required keyword-only opt_in: 'if not have: (if dimension in opt_in: return False) continue'. restricting_dimensions() adds Q(kind='opt_in'). Add opt_in_dimensions(). Rewrite the matching.py docstring to cover opt-in and the regime fold. Update every caller, including the footprint_logic preview. Add pure cases to tests_matching.py.",
 "owned_paths": [
  "backend/apps/taxonomy/models.py",
  "backend/apps/shared/kinds.py",
  "backend/apps/taxonomy/matching.py",
  "backend/apps/taxonomy/footprint_logic.py",
  "backend/apps/taxonomy/tests_matching.py"
 ],
 "depends_on": [
  "STD-02",
  "REGULATORY_SCOPE-T02",
  "chunk3-rest-T7"
 ],
 "done_condition": "The pure cases pass: an opt-in dimension missing from the scope mapping returns False without a TypeError; an opt-in dimension with restricts_footprint false still restricts; scope dimensions are unchanged. Calling without opt_in raises TypeError. The kinds guard and mypy pass"
}
```
```json
{
 "id": "STD-05",
 "title": "Replace the SQL footprint function for opt-in dimensions",
 "summary": "Write a new taxonomy migration: the kind choices, and taxonomy_in_footprint joined on (d.restricts_footprint OR d.kind = 'opt_in') AND d.active, with WHERE d.kind = 'opt_in' OR EXISTS(...). The reverse migration restores the 0001 text. Extend the mirror suite.",
 "owned_paths": [
  "backend/apps/taxonomy/migrations/",
  "backend/apps/taxonomy/tests_matching.py"
 ],
 "depends_on": [
  "STD-04",
  "chunk4-T2",
  "REGULATORY_SCOPE-T02"
 ],
 "done_condition": "migrate_from_zero and the reverse migration pass. FP-S15 is un-skipped and green. The row-level-security test still passes"
}
```
```json
{
 "id": "STD-06",
 "title": "Seed the standards dimension and its first term",
 "summary": "Add a row 'standard' to _EXTRA_DIMENSIONS: 'Standards followed' / 'Standarder vi följer', kind opt_in, restricts_footprint true, with a usage note saying it is opt-in and within the sector scope. Add the fixture term standard:iso_iec_27001 (from_prototype false), whose usage note names its regime, ai_ict. Propose the regime note's scope wording to the owner of REGULATORY_SCOPE-T01. No E2E tenant holds the term.",
 "owned_paths": [
  "backend/apps/taxonomy/seeds/__init__.py",
  "backend/apps/library/fixtures/prototype_data.json"
 ],
 "depends_on": [
  "STD-05",
  "REGULATORY_SCOPE-T01",
  "chunk3-rest-T2"
 ],
 "done_condition": "seed_reference is idempotent and records taxonomy.term_created once, under T01's rule. check_prototype_data.py passes. No E2E tenant's scope holds the term"
}
```
```json
{
 "id": "STD-07",
 "title": "Show opt-in groups on the Regulatory scope page",
 "summary": "scopeGroups() shows a dimension of kind opt_in. An empty opt-in group reads 'None followed' (a new key) in the read state and as the edit hint. narrowedGroups() never lists an opt-in group. Expose the dimension kind in GET /tenant/footprint if it is missing. Add the en and sv messages and regenerate the types.",
 "owned_paths": [
  "backend/apps/taxonomy/schemas.py",
  "frontend/src/features/footprint/footprint-presentation.ts",
  "frontend/src/features/footprint/footprint-presentation.test.ts",
  "frontend/src/components/admin/FootprintScreen.tsx",
  "frontend/src/messages/en.json",
  "frontend/src/messages/sv.json"
 ],
 "depends_on": [
  "STD-06",
  "REGULATORY_SCOPE-T06",
  "REGULATORY_SCOPE-T07"
 ],
 "done_condition": "The presentation tests cover both empty-group texts and keep opt-in groups out of the narrowing list. No string literal appears in JSX. The contract-drift gate passes. The FP-S14 E2E half is green once STD-13 lands"
}
```
```json
{
 "id": "STD-08",
 "title": "Add the optional standard level kind and the provision trigger",
 "summary": "Add InstrumentLevelKind with the one value 'standard'. Set the registry entry: kind_name 'instrument_level_kind', kinds=('standard',), kind_required False. Add a fixture level row 'standard' (binding_default false, rank 60). A library migration adds a trigger on provision, on INSERT and on UPDATE of instrument_id, that refuses a row under an instrument whose level kind is standard. check_prototype_data.py refuses a provision under a standard and requires exactly one obligation under it.",
 "owned_paths": [
  "backend/apps/taxonomy/models.py",
  "backend/apps/taxonomy/registry.py",
  "backend/apps/shared/kinds.py",
  "backend/apps/taxonomy/migrations/",
  "backend/apps/library/migrations/",
  "backend/apps/library/fixtures/prototype_data.json",
  "backend/apps/library/fixtures/check_prototype_data.py"
 ],
 "depends_on": [
  "STD-01",
  "STD-05",
  "chunk3-rest-T1",
  "chunk3-rest-T8"
 ],
 "done_condition": "The five existing levels keep a null kind. Inserting a provision under a standard-level instrument raises. check_prototype_data --eval passes. The kinds guard is green"
}
```
```json
{
 "id": "STD-09",
 "title": "Add the International jurisdiction",
 "summary": "Add JurisdictionKind.INTERNATIONAL with a migration. Add the intl row to JURISDICTIONS, with no parent and English as its default language. Add the authority iso-iec under intl to the reference seed (from_prototype false). Amend test_i18n_s1's expected set and kinds. Agree with the markets owner that intl gets no mirror term and derives none.",
 "owned_paths": [
  "backend/apps/library/models.py",
  "backend/apps/library/migrations/",
  "backend/apps/library/seeds/",
  "backend/apps/shared/kinds.py",
  "backend/apps/taxonomy/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-01",
  "chunk3-rest-T1",
  "markets prerequisite: jurisdiction mirror terms"
 ],
 "done_condition": "The amended I18N-S1 is green. GET /reference/jurisdictions returns intl with kind international. The seed is idempotent"
}
```
```json
{
 "id": "STD-10",
 "title": "Require a regime on every instrument",
 "summary": "Make Instrument.regime NOT NULL through a migration. The seed-integrity test asserts that every instrument's regime is a term of the regime dimension.",
 "owned_paths": [
  "backend/apps/library/models.py",
  "backend/apps/library/migrations/",
  "backend/apps/library/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-09"
 ],
 "done_condition": "The database half of INV-S12 is green. seed_demo still loads all 15 instruments"
}
```
```json
{
 "id": "STD-11",
 "title": "Choose the binding pill from the level kind",
 "summary": "When bindingLevel.kind is standard, render 'Standard' in the information tone in the header binding slot and in the row guidance slot. Every other level keeps chunk 3's slots. Update pills-and-labels.md and add the en and sv messages.",
 "owned_paths": [
  "frontend/src/features/library/obligation-presentation.ts",
  "frontend/src/features/library/obligation-presentation.test.ts",
  "design/system/pills-and-labels.md",
  "frontend/src/messages/en.json",
  "frontend/src/messages/sv.json"
 ],
 "depends_on": [
  "STD-08",
  "chunk3-rest-T5",
  "chunk3-rest-T13"
 ],
 "done_condition": "The presentation tests cover a null kind with binding true, a null kind with binding false, and standard. A standard never shows 'Guidance, comply or explain'. The pill gallery check passes"
}
```
```json
{
 "id": "STD-12",
 "title": "Show the licensed-text empty state on a standard's provision tree",
 "summary": "On the instrument card, when bindingLevel.kind is standard, the provision tree reads 'The text of this standard is licensed and not held here', with the catalogue link. Add the INV-S11 E2E step.",
 "owned_paths": [
  "frontend/src/features/library/",
  "frontend/src/messages/en.json",
  "frontend/src/messages/sv.json",
  "frontend/tests/e2e/library.journey.spec.ts"
 ],
 "depends_on": [
  "STD-11",
  "chunk3-rest-T18",
  "STD-13"
 ],
 "done_condition": "The INV-S11 E2E half is green against the real stack. The empty, loading, error and denied states are all present"
}
```
```json
{
 "id": "STD-13",
 "title": "Add ISO/IEC 27001:2022 to the demo fixture",
 "summary": "Add the instrument: level standard, jurisdiction intl, authority iso-iec, regime ai_ict, with dates taken from the Verification_Log. Add its conformance obligation: ref_label equal to the official reference, duty type governance, en and sv summaries in our own words, and one term, standard:iso_iec_27001. Add no provisions and no relation rows; everything is from_prototype false. Un-skip the integration halves of INV-S11 and FP-S14.",
 "owned_paths": [
  "backend/apps/library/fixtures/prototype_data.json",
  "backend/apps/library/seeds/library.py",
  "backend/apps/library/tests_scenarios.py",
  "backend/apps/taxonomy/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-03",
  "STD-06",
  "STD-08",
  "STD-09",
  "STD-10",
  "chunk3-rest-T13"
 ],
 "done_condition": "check_prototype_data passes, including --eval. The integration halves of INV-S11 and FP-S14 are green. Every date cites a Verification_Log row"
}
```
```json
{
 "id": "STD-14",
 "title": "Add one standards check at proposal creation, correction and apply",
 "summary": "Add proposals/standards.py, whose check_standard_rules() applies these rules to new_obligation_version:\n- a standard's obligation carries exactly one opt-in term (standard_term_required);\n- any other obligation carries none (standard_term_only_on_standards).\nCall it at POST /proposals and at agent proposal creation, over payloadOverrides at approval, and in apply.",
 "owned_paths": [
  "backend/apps/proposals/standards.py",
  "backend/apps/proposals/logic.py",
  "backend/apps/proposals/apply.py",
  "backend/apps/proposals/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-04",
  "STD-08",
  "chunk4-T1",
  "chunk4-T6"
 ],
 "done_condition": "PRO-S11 is green. A refusal at creation stores no proposal. A refusal at approval writes nothing and no audit row"
}
```
```json
{
 "id": "STD-15",
 "title": "Add the out-of-scope rejection reason",
 "summary": "Add a system row, out_of_scope, to the rejection_reason seed: 'Outside the sector scope' / 'Utanför sektorsomfattningen', with a usage note naming the PRD's sector scope. It is seeded create-only, as chunk4-T2 seeds the others.",
 "owned_paths": [
  "backend/apps/taxonomy/seeds/__init__.py"
 ],
 "depends_on": [
  "chunk4-T2"
 ],
 "done_condition": "The amended PRO-S9 is green. The row has en and sv labels. A relabel survives a redeploy"
}
```
```json
{
 "id": "STD-16",
 "title": "Extend the standards check to instrument, obligation and provision proposals",
 "summary": "Extend the check function:\n- A provision or provision_version proposal under a standard answers licensed_text, and so does a field source that is not a URL.\n- At most one active obligation per standard, and its ref_label equals the official reference (one_conformance_obligation).\n- An instrument proposal whose regime is not a regime term answers not_a_regime.\n- An instrument_update that moves an instrument with provisions to the standard level is refused.\nWire it into chunk 5's new kinds, at creation, correction and apply.",
 "owned_paths": [
  "backend/apps/proposals/standards.py",
  "backend/apps/proposals/apply.py",
  "backend/apps/proposals/tests_scenarios.py",
  "backend/apps/library/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-14",
  "STD-10",
  "chunk 5 proposal kinds"
 ],
 "done_condition": "PRO-S10 and the proposal half of INV-S12 are green"
}
```
```json
{
 "id": "STD-17",
 "title": "Add the watch rules for regime and standards",
 "summary": "createChange and the editor's change corrections answer 422 regime_required with the valid keys. They accept an opt-in term only when the authority's jurisdiction kind is international (standard_term_only_on_standards). A source_document on a host in the setting STANDARDS_PUBLISHER_HOSTS stores no snapshot. A change carrying an opt-in term may link only documents without a snapshot (licensed_text). Add the source_kind row standards_body. CAS-01 computes footprint_match with opt_in.",
 "owned_paths": [
  "backend/apps/watch/logic.py",
  "backend/apps/watch/api.py",
  "backend/apps/watch/tests_scenarios.py",
  "backend/config/settings.py",
  "backend/apps/library/fixtures/prototype_data.json"
 ],
 "depends_on": [
  "STD-09",
  "STD-13",
  "chunk 5 base: sources, source documents, createChange, CAS-01"
 ],
 "done_condition": "WAT-S10 and WAT-S11 are green. The settings test lists STANDARDS_PUBLISHER_HOSTS"
}
```
```json
{
 "id": "STD-18",
 "title": "Add sector scope and standards to the watch-sweeper prompt",
 "summary": "Replace 'banks and insurers' with the PRD's scope sentence. Add a Scope section: an out_of_scope count, and nothing registered. Add a Standards section:\n- publication facts only;\n- never fetch, quote, summarise, translate or restate a standard's text, from a page or from memory;\n- never propose an obligation per clause or control;\n- a 403 or a challenge is a failed check that is never worked around;\n- never fetch a page of an inactive standards_body source;\n- a law that cites a standard gets no standard term.\nReplace the hard-coded dimensions with 'every dimension whose restricts_footprint is true or whose kind is opt_in'.",
 "owned_paths": [
  "agents/watch-sweeper/v1/prompt.md"
 ],
 "depends_on": [
  "STD-02"
 ],
 "done_condition": "The prompt still reads status draft. No list of dimension keys remains in it. The agent eval README references the new rules"
}
```
```json
{
 "id": "STD-19",
 "title": "Extend the watch-sweeper definition and run stats",
 "summary": "Add instrument_level, jurisdiction, relation_type, duty_type and provision_kind to vocabularies_read_at_run_start. Mention standards in the description. Accept and show an out_of_scope count in AgentRunFinish and in the run history.",
 "owned_paths": [
  "agents/watch-sweeper/v1/definition.yaml",
  "backend/apps/agents/schemas.py",
  "backend/apps/agents/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-18",
  "chunk 5 base: agent run schemas"
 ],
 "done_condition": "The AGT-S3 amendment and the run-stats half of AGT-S12 are green"
}
```
```json
{
 "id": "STD-20",
 "title": "Add off-sector and standards eval rows",
 "summary": "Add authored texts, never copied from a publisher:\n- at least four off-sector rows with expected.in_scope false;\n- a DORA text citing ISO/IEC 27001, with in_scope true and no standard term;\n- three standards rows that expect scope.standard: a new edition with a transition key date, an accreditation transition rule, and a draft for comment.\nDocument in_scope and the authored-text rule in the README.",
 "owned_paths": [
  "backend/eval/classification.jsonl",
  "agents/watch-sweeper/v1/evals/cases.jsonl",
  "backend/eval/README.md"
 ],
 "depends_on": [
  "STD-13"
 ],
 "done_condition": "check_prototype_data --eval passes. Every existing row reads as in_scope true by default. Every new row has source: authored"
}
```
```json
{
 "id": "STD-21",
 "title": "Score in-scope and standard-term accuracy in the eval gate",
 "summary": "The classifier returns in_scope. search_eval.py scores in-scope accuracy and standard-term accuracy. tolerance.json gains both, each with a rationale.",
 "owned_paths": [
  "backend/scripts/search_eval.py",
  "backend/eval/tolerance.json",
  "backend/eval/tests_scoring.py"
 ],
 "depends_on": [
  "STD-20",
  "chunk 5 classifier"
 ],
 "done_condition": "search_eval.py --self-test is green. The mock classifier reports both metrics. The eval half of AGT-S12 is green"
}
```
```json
{
 "id": "STD-22",
 "title": "Make Ask give no answer about a standard's controls",
 "summary": "Add the question 'What does ISO/IEC 27001 control A.8.8 require?' to the Ask evaluation set, expecting no answer. Un-skip SRC-S12.",
 "owned_paths": [
  "backend/eval/retrieval.jsonl",
  "backend/apps/search/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-13",
  "chunk 7 base: Ask"
 ],
 "done_condition": "SRC-S12 is green against the mock and against the recorded real model"
}
```
```json
{
 "id": "STD-23",
 "title": "Add certificate columns to the licence row",
 "summary": "When chunk 8 builds licence (TEN-02), add nullable valid_until, next_audit_on and owner_id, with no terms and no instrument link. Audit writes with before and after values. The entity screen lists 'Licences and certificates'.",
 "owned_paths": [
  "backend/apps/tenants/models.py",
  "backend/apps/tenants/migrations/",
  "backend/apps/tenants/logic.py",
  "backend/apps/tenants/api.py",
  "backend/apps/tenants/schemas.py",
  "backend/apps/tenants/tests_scenarios.py",
  "frontend/src/features/tenants/"
 ],
 "depends_on": [
  "chunk 8 base: org_unit and licence",
  "owner shape from the my-work analysis"
 ],
 "done_condition": "TEN-S10 is green in both halves. The TEN-S2 amendment is green. The row-level-security guard lists licence"
}
```
```json
{
 "id": "STD-24",
 "title": "Decide applicability per entity for the conformance obligation",
 "summary": "Add scope_id to applicability_request, with a one-pending index on (tenant_obligation_id, scope_id) NULLS NOT DISTINCT. Add applicability_reason and applicability_decided_at to tenant_obligation_scope. A request creates its scope row, through record(), when the row is missing; reads never write. Approval writes the scope row. An entity's span leaves out opt-in dimensions.",
 "owned_paths": [
  "backend/apps/register/models.py",
  "backend/apps/register/migrations/",
  "backend/apps/register/logic.py",
  "backend/apps/register/tests_scenarios.py"
 ],
 "depends_on": [
  "chunk 8 base: tenant_obligation, tenant_obligation_scope, applicability_request",
  "STD-04"
 ],
 "done_condition": "REG-S12 and the REG-S1 amendment are green. A test proves that a GET writes no row"
}
```
```json
{
 "id": "STD-25",
 "title": "Add the soa_unit table and its rules",
 "summary": "Create soa_unit (a TenantModel under forced RLS) with the fields in the decision std-units-in-tenant-zone and UNIQUE (scope_id, unit_ref). Enforce 422 units_only_under_standards and scope_not_applicable, and 409 unit_has_history. Add unit_id to applicability_request, widening the one-pending index, and to gap. Approving a unit request writes the unit's applicability. Status and note take If-Match. Every write is one audit event.",
 "owned_paths": [
  "backend/apps/register/models.py",
  "backend/apps/register/migrations/",
  "backend/apps/register/logic.py",
  "backend/apps/register/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-24"
 ],
 "done_condition": "The row-level-security guard lists soa_unit. The 422 and 409 checks of REG-S13 are green. UNIQUE (tenant_id, obligation_id) on tenant_obligation is unchanged"
}
```
```json
{
 "id": "STD-26",
 "title": "Paste units with a dry run",
 "summary": "Parse lines of 'reference<TAB>title[<TAB>applies|does_not_apply<TAB>reason]' for one entity's scope row. The dry run lists the rows and refuses duplicates, over-long lines and unknown values. Commit writes the units (register.edit) and, when applicability is given, one pending request per row (applicability.request). REGISTER_BULK_MAX caps the lines.",
 "owned_paths": [
  "backend/apps/register/units.py",
  "backend/apps/register/api.py",
  "backend/apps/register/schemas.py",
  "backend/apps/register/tests_scenarios.py",
  "backend/config/settings.py"
 ],
 "depends_on": [
  "STD-25"
 ],
 "done_condition": "REG-S13 (integration) is green, including the 422 and 409 paths. The settings test lists REGISTER_BULK_MAX"
}
```
```json
{
 "id": "STD-27",
 "title": "Decide many pending requests in one call",
 "summary": "Add a route under applicability.approve and @requires_step_up that takes [{requestId, decision, note}]. It decides each request through the single-request logic in one transaction. A request the caller filed answers 409 four_eyes_violation, and nothing is decided. It writes one record() per row, citing the assertion. It is capped by REGISTER_BULK_MAX. Add applicability_request to FOUR_EYES_TABLES if chunk 8 has not.",
 "owned_paths": [
  "backend/apps/register/api.py",
  "backend/apps/register/logic.py",
  "backend/apps/register/tests_scenarios.py",
  "backend/apps/shared/tests_four_eyes.py"
 ],
 "depends_on": [
  "STD-25"
 ],
 "done_condition": "REG-S14 (integration) is green, including the 409 path with no partial decision. A call with 100 rows stays under API_BUDGET_MS, and the query count is asserted"
}
```
```json
{
 "id": "STD-28",
 "title": "Build the units list, the paste dialog and the bulk decision screen",
 "summary": "On the conformance obligation's entity row: the units list, a paste dialog with a dry-run preview and commit, and a hint to write in your own words. The approver's queue is filtered by standard, entity and requester, with a decide-selected action. Add en and sv messages, and the empty, loading, error and denied states.",
 "owned_paths": [
  "frontend/src/features/register/units/",
  "frontend/src/messages/en.json",
  "frontend/src/messages/sv.json",
  "frontend/tests/e2e/register.journey.spec.ts"
 ],
 "depends_on": [
  "STD-26",
  "STD-27",
  "chunk 8 register screens"
 ],
 "done_condition": "The E2E halves of REG-S13 and REG-S14 are green, using invented units only. No string literal appears in JSX"
}
```
```json
{
 "id": "STD-29",
 "title": "Filter the register into a Statement of Applicability",
 "summary": "Add register filters for instrument and org unit, and unit rows showing reference, title, applicability, reason, status, approver and decision date. Each unit's history comes from its decided requests. The conformance row keeps its own status, with no roll-up across units.",
 "owned_paths": [
  "backend/apps/register/api.py",
  "backend/apps/register/logic.py",
  "frontend/src/features/register/"
 ],
 "depends_on": [
  "STD-27",
  "STD-28"
 ],
 "done_condition": "REG-S15 is green at both the integration and the E2E level. HOM-S1's standing counts are unchanged by units"
}
```
```json
{
 "id": "STD-30",
 "title": "Prove nothing written under a standard reaches the index or a model",
 "summary": "Add a guard test, written per row. No text from any tenant row whose obligation sits under a standard-level instrument may enter search_chunk, embedder input or ai_generation input. That covers units, scope notes, gaps, assessments, interpretations and links. Tenant B's search finds none of it.",
 "owned_paths": [
  "backend/apps/search/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-25",
  "chunk 7 base: indexer, embedder, ai_generation"
 ],
 "done_condition": "SRC-S13 is green. The test fails when a field of any such row is added to an indexer, embedder or model input"
}
```
```json
{
 "id": "STD-31",
 "title": "Put certificate dates on the roadmap, never in the calendar feed",
 "summary": "Replace v_roadmap_item with a version that adds licence_expiry and licence_audit: kind internal, 'Our deadline', the row's owner, left out once withdrawn_on is set. The calendar feed leaves both branches out.",
 "owned_paths": [
  "backend/apps/home/migrations/",
  "backend/apps/home/logic.py",
  "backend/apps/home/tests_scenarios.py"
 ],
 "depends_on": [
  "STD-23",
  "chunk 6 base: v_roadmap_item and calendar feed",
  "chunk 8 gap and duty branches"
 ],
 "done_condition": "HOM-S15 is green. HOM-S4, HOM-S5 and HOM-S6 are still green"
}
```
```json
{
 "id": "STD-32",
 "title": "Run J-10 end to end",
 "summary": "Use the seeded officer and approver. The journey:\n1. The officer adds the standard to the regulatory scope; the approver approves with step-up.\n2. The officer records the certificate on Bank AB.\n3. The officer requests per-entity applicability, and the approver approves with step-up.\n4. The officer pastes three invented units with applicability.\n5. The approver decides them in one call with step-up.\n6. The SoA filter and the roadmap audit date show the result.",
 "owned_paths": [
  "frontend/tests/e2e/register.journey.spec.ts",
  "backend/apps/shared/e2e_seed.py"
 ],
 "depends_on": [
  "STD-07",
  "STD-23",
  "STD-28",
  "STD-29",
  "STD-31"
 ],
 "done_condition": "REG-S16 is green against the real stack, with no mocked API. seed_e2e stays idempotent. No real clause or control title appears in the repository"
}
```
```json
{
 "id": "STD-33",
 "title": "Export the Statement of Applicability",
 "summary": "The REP-02 inventory export accepts the instrument and org-unit filters and produces the SoA columns per unit. It runs as a job, needs step-up and writes one audit event.",
 "owned_paths": [
  "backend/apps/reports/"
 ],
 "depends_on": [
  "STD-29",
  "chunk 12 base: REP-02 export jobs"
 ],
 "done_condition": "REP-S6 is green. REP-S3 is still green"
}
```

---

# Appendix: todo_for_owner

- Accept or amend the PRD 0.3 bump, merged with the markets and my-work bump into one 0.3. It covers the sharpened 'Sector scope' and 'Standards and certifications' paragraphs; FP-01 with opt-in; INV-01, INV-02 and INV-08; WAT-03 and WAT-07; AGT-08; TEN-02 (certificates, alongside the departments wording); REG-01 and REG-08; HOM-03; REP-02; the six acceptance criteria; and J-10.
- Confirm or change the 13 std-* defaults. Settle the intl derivation (std-international-jurisdiction), the entity span (std-entity-follows-by-applicability) and the licence owner shape (std-certificate-on-licence) together with the markets and my-work analyses.
- Legal, before any standard is seeded: may the library store and show a standard edition's official title and our one-sentence conformance duty? Does automated monitoring of publishers' catalogue pages, keeping a hash and no snapshot, respect ISO's text-and-data-mining reservation and site terms? Which publishers may be read automatically (IAF documents first)?
- Legal, before the first bank uses units: is a bank's list of clause and control references with its own titles, held in our SaaS, 'internal reference' (ISO licence §4) or 'integration into compliance systems' (§6(b)), for the bank and for bleqq? Is a person's paraphrase a derivative work? Does support access (TEN-06) to unit text count as disclosure?
- Legal: what PCI SSC's terms (including its Material License Agreement) and the Swift CSCF terms allow, and what the member-body licences (SIS, DS, Standard Norge, SFS) cover across the Nordics.
- Terms of service: a clause making each tenant responsible for its own standards licences and for any licensed material it uploads as evidence, plus a takedown process.
- Design cards: the 'Standard' pill (wording and tone); the Regulatory scope page's opt-in group with 'None followed'; the entity screen's 'Licences and certificates' with its validity and next-audit fields; the units list and paste dialog; the approver's decide-selected queue; the SoA register view; and a standard instrument's empty provision state.
- Confirm the seed list: ISO/IEC 27001:2022 first. Decide on ISO 22301, ISO/IEC 27701, PCI DSS, the Swift CSCF and ISO/IEC 42001, and whether ISAE 3402 or SOC reports that a tenant issues are in scope.
- Answer the sector-vocabulary question once, together with REGULATORY_SCOPE.md §12: name tax and AI in the PRD; map the six sectors to licensed_activity terms; decide whether SFDR, consumer credit and the Accessibility Act as applied to banking are in scope.
- Decide whether to pursue a content licence (for example SIS's licence for digital tools, or ISO directly) so the library could hold clause and control titles. Until then the library stays facts only.

---

# Appendix: open_questions

- Which standards besides ISO/IEC 27001 belong in the first releases: ISO 22301, ISO/IEC 27701, PCI DSS, the Swift CSCF, ISO/IEC 42001? Are ISAE 3402 or SOC 2 reports that a tenant issues to its own clients in scope at all? The default (std-seed-list) is ISO/IEC 27001 only.
- Are tax rules for financial products, and AI rules as they apply to financial firms, inside the sector scope? Are SFDR, consumer credit and the Accessibility Act for banking services? REGULATORY_SCOPE.md §12 asks the same question, so answer it once. The default is to keep tax and AI and name them in the PRD.
- Should bleqq pursue a content licence so the shared library can hold clause and control titles, or stay with public facts plus the tenant's own units? The default (std-library-facts-only) is public facts only.
- Should the Statement of Applicability export move from R3 into chunk 8, since banks need the document at certification audits? The default (std-soa-view-and-export) keeps it in R3, with the filtered register as the SoA in R2.
- Who registers a standards change while no publisher source is cleared? POST /changes is agent-only (UI_Implementation_Plan.md line 195). The default (std-watch-manual-first): the agent registers from cleared sources only, and the library editor enters new editions as instrument proposals. No case opens for a revision until a source is cleared. The alternative is a console route for the editor to register a change, which is new scope.
- IDs are provisional: the decision slugs, FP-S14 and FP-S15, TEN-S10, HOM-S15, AGT-S12, AC-FP3 and J-10. They skip IDs claimed by REGULATORY_SCOPE.md and MY_WORK_AND_MARKETS.md. Those two documents both claim FP-S6 and FP-S7, and the orchestrator must resolve that too.
- Rejected in part (the certificate as evidence on the scope row, from the critique that drops the licence extension): evidence has no per-entity anchor (schema.sql evidence_parent_check), and the review_due branch hides compliant rows, so a certified, compliant entity's next audit would vanish from the roadmap. The certificate stays on the licence row with three added columns. The rest of that critique, and the other critique on the same point, are adopted: the licence row no longer says that an entity follows a standard, and no longer decides the span.
- Rejected in part (seed intl with the kind supranational): the markets analysis derives a jurisdiction term from Instrument.jurisdiction and hides it under any operating market. The new watch rule allows a standard term only on a change from an international issuer. Both must tell an international issuer from the EU by kind, never by key, so the kind has two readers. Dropping 'amends', and deferring 'replaces' and iaf, are adopted.
- Rejected in part (add I18N-01 to the changed rows): I18N-01 asks for jurisdictions as data, which one more row satisfies. The markets bump also leaves built chunk 2 rows unchanged. INV-08 names the International row, and I18N-S1 and its exact-set test are amended, which is the part of the critique that was correct.
- Rejected in part (approve the SoA per entity as one applicability request carrying the unit list, from the units critique): that needs a child table on the request and a second apply path. Each unit decision stays an ordinary applicability request, decided through the bulk route that the two step-up critiques propose. The rest of the units critique (a child row per unit and UNIQUE (tenant_id, obligation_id) kept) is adopted.

---

# Appendix: sources

- C:\Users\Alex\projects\grc\PRD.md (0.2 §1 'Sector scope' and 'Standards and certifications'; §3 rows FP-01, INV-01 to INV-07, WAT-01 to WAT-06, CAS-01, SRC-03, SRC-05, HOM-01 to HOM-04, AGT-01 to AGT-07, REP-01 to REP-03, TEN-02, I18N-01; journeys J-1 to J-8; acceptance criteria in use)
- C:\Users\Alex\projects\grc\CLAUDE.md (§1 two zones and 'sourced public facts'; §5 invariants and 'Simplicity first'; §6 budgets)
- C:\Users\Alex\projects\grc\docs\plans\briefs\REGULATORY_SCOPE.md (§4.2 scopeGroups and narrowedGroups, §5 Banking and Payments with the regime note, §6.2 preview counts with the regime fold, §8 FP-S6 and FP-S7, §11 T01 to T07, §12 open questions)
- C:\Users\Alex\projects\grc\docs\plans\briefs\MY_WORK_AND_MARKETS.md (untracked parallel analysis: §4.2 jurisdiction mirror terms and derivation, FP-04, D-18 to D-30, J-9, AC-FP2, FP-S6 to FP-S13, HOM-S7 to HOM-S14, TEN-S8, AGT-S11, TEN-02 change)
- C:\Users\Alex\projects\grc\docs\plans\briefs\CHUNK3_TASKS.md:40, :239 (obligation_scopes with the regime fold), :188 ({key, kind, label} schema walk), :298 (binding slots), task headings T1 to T20
- C:\Users\Alex\projects\grc\docs\plans\briefs\CHUNK4_TASKS.md:5-72 (only new_obligation_version; instrument, obligation and provision kinds in chunk 5), :245-262 (chunk4-T2 rejection_reason rows, no out_of_scope)
- C:\Users\Alex\projects\grc\docs\plans\briefs\CHUNK4_BRIEF.md:30-46 (proposal kinds, rejection codes, field_sources)
- C:\Users\Alex\projects\grc\docs\plans\IMPLEMENTATION_STATUS.md (chunk 3 still 'pending' although 51f9efa is on main)
- C:\Users\Alex\projects\grc\docs\plans\Build_Plan.md (chunk table rows 3, 5, 8)
- C:\Users\Alex\projects\grc\docs\plans\Implementation_Backlog.md (T-<REQ> groups and the coverage index)
- C:\Users\Alex\projects\grc\docs\plans\UI_Implementation_Plan.md:195 (POST /changes is agent-only), :196-199
- C:\Users\Alex\projects\grc\docs\adr\README.md (every DECISIONS entry has an ADR; numbers are never reused)
- C:\Users\Alex\projects\grc\docs\DECISIONS.md (D-07, D-10)
- C:\Users\Alex\projects\grc\docs\inputs\schema.sql:278-287 (source_check), :471-490 (tenant_obligation UNIQUE), :493-506 (applicability_request), :1219-1245 (org_unit, licence), :1266 and :1282 (internal_item, internal_link), :1362-1377 (source_document), :1381-1392 (citation, not built), :1422 (obligation_requirement), :1442 (recurring_duty), :1524-1536 (tenant_obligation_scope), :1556 (requirement_status), :1571 (gap.requirement_id), :1628-1634 (evidence parent check, valid_until), :1845-1880 (v_roadmap_item, footprint_match filter), :1980-1991 (shared_or_mine)
- C:\Users\Alex\projects\grc\docs\inputs\data-model.md:214, :300-316
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\matching.py:25-44 (in_footprint; 'have = footprint.get' at :39, the isdisjoint path at :42), restricting_dimensions()
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\migrations\0001_initial.py (taxonomy_in_footprint, the WHERE EXISTS clause)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\models.py:60 (TermDimensionKind), TermDimension, InstrumentLevel (no kind choices), SourceKind (no extra fields)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\registry.py:85-133 (VocabularyList with kind_required; the jurisdiction list not proposable), tenant_lists_logic.py validated_kind
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\library_lists_logic.py propose_relabel; backend\apps\proposals\schemas.py:41-47 and :94-110 (relabel payload with no kind; ProposalFieldSources); backend\apps\proposals\apply.py:132-156 (_vocabulary_relabel)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\seeds\__init__.py (_EXTRA_DIMENSIONS: licensed_activity, 'The licence under which the firm acts')
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\tests_scenarios.py:705-724 (I18N-S1 asserts the exact jurisdiction set)
- C:\Users\Alex\projects\grc\backend\apps\taxonomy\app.md (FP-S1 'matches every tenant' clause, FP-S2 to FP-S5, I18N-S1, requirement statuses)
- C:\Users\Alex\projects\grc\backend\apps\library\models.py:49-53 (JurisdictionKind), :182-203 (Instrument, regime nullable, owner_tenant), Provision, ProvisionVersion, ProvisionText (no owner), no citation model
- C:\Users\Alex\projects\grc\backend\apps\shared\tenancy.py:130-142 (library_write admits seeds, watch and proposals)
- C:\Users\Alex\projects\grc\backend\apps\shared\permissions.py:462-478 (enforce_step_up, a freshness window); backend\config\settings.py:351 (STEP_UP_FRESHNESS_MINUTES 5)
- C:\Users\Alex\projects\grc\backend\apps\shared\tests_four_eyes.py (FOUR_EYES_TABLES must grow with applicability requests)
- C:\Users\Alex\projects\grc\backend\scripts\requirements_coverage.py (a PRD requirement without a scenario, or an @e2e scenario without a test or test.fixme title, fails)
- C:\Users\Alex\projects\grc\backend\apps\register\app.md (REG-01 to REG-07, REG-S1 to REG-S11), cases\app.md CAS-S1 (one case per tenant with footprint_match), watch\app.md WAT-S2 (one record per reform), home\app.md §3 and HOM-S5 (the calendar feed carries public facts only), tenants\app.md TEN-S2 (vocab.manage)
- C:\Users\Alex\projects\grc\backend\apps\library\fixtures\prototype_data.json (instrument levels with null kind, relation types implements, elaborates and related; source kinds; six regimes; 15 instruments; proposals new_obligation_version, new_obligation and reverification)
- C:\Users\Alex\projects\grc\agents\watch-sweeper\v1\prompt.md:8-9, :41, :80-81 and definition.yaml:8, :62-70
- C:\Users\Alex\projects\grc\frontend\src\features\library\obligation-presentation.ts (binding pill branch); design\system\pills-and-labels.md
- Reported by the research maps, not verified here: ISO End Customer Licence Agreement (updated 2026-05-29) https://www.iso.org/terms-conditions-licence-agreement.html; https://www.iso.org/copyright.html; https://www.iso.org/standard/27001
- Reported, not verified: PCI SSC terms https://www.pcisecuritystandards.org/terms_and_conditions/ and the PCI DSS v4.0.1 notes on blog.pcisecuritystandards.org
- Reported, not verified: IAF MD 26:2023 https://iaf.nu/iaf_system/uploads/documents/IAF_MD26_Issue_2_15012023.pdf; ISO/IEC 17021-1 §9 summary https://www.iasonline.org/wp-content/uploads/2021/02/17021-1-2015-Section-9.pdf
- Reported, not verified: SIS licence for digital tools https://www.sis.se/bckerochverktyg/licensavtal-for-digitala-verktyg/; DS AI terms https://www.ds.dk/da/kundeservice/ai-vilkaar; Standard Norge https://standard.no/standarder/hjelp/opphavsrett/bruk-og-kopiering/; SFS https://sfs.fi/en/keep-in-mind-the-correct-use-of-standards-pay-attention-to-copyright/
- Reported, not verified: DORA (EU) 2022/2554, Delegated Regulation (EU) 2024/1774 Art. 2(1)(h), Regulation (EU) 1025/2012 and NIS2 (EU) 2022/2555 on eur-lex.europa.eu; EBA GL/2019/02 paragraphs 91-93; NIST IR 8477 https://csrc.nist.gov/pubs/ir/8477/final

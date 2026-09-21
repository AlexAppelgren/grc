# Build plan

Each chunk is a whole slice that ends in something a person can use on the
Railway test environment. Finish a chunk (playbook Section 3, definition of
done), update `IMPLEMENTATION_STATUS.md`, commit, then start the next. Do not
stop between chunks unless a product invariant is at stake.

| # | Chunk | Outcome for a user | Requirements | Release |
|---|---|---|---|---|
| 0 | Phase 0 bootstrap | An empty app that boots, migrates from zero, passes every gate and guard, renders the shell with the phonetic logo, the token pipeline and the pill gallery. Spike D-04 | Playbook 2, 5, 9 | R1 |
| 1 | Identity and tenant admin basics | An invited person enrols a passkey and signs in. An admin invites, assigns roles, re-issues enrolment and revokes sessions | ID-01 to ID-06, ID-09 to ID-11, TEN-01, ADM-01 (people), ADM-03, J-1, J-8 | R1 |
| 2 | Vocabularies, taxonomy and footprint | Admins manage lists without a deploy. The regulatory scope is set with preview and second-person approval | VOC-01, VOC-02, VOC-07, FP-01 to FP-03, I18N-01, J-5, J-6 | R1 |
| 3 | Library and inventory | Browse instruments and obligations with versions, "as of", diff, translations, provenance, the markets we watch and the first standard. Seeded from the prototype's data | INV-01 to INV-06, INV-08, FP-04, FP-01 (the opt-in rule and the regime fold) | R1 |
| 4 | Proposals and the platform console | A library editor reviews and approves proposals. Tenants see library updates and report problems | PRO-01 to PRO-03, ADM-02 (queue, vocabularies, sources), AUD-03 | R1 |
| 5 | Watch and the agent API | Agents register changes and proposals with a key. The watch feed shows one record per reform with its timeline, flags and suggested links, and the markets we watch | WAT-01 to WAT-05, WAT-07, AGT-01, AGT-02, AGT-07, AGT-08, CAS-01, ID-10, FP-04 (the feed view and a change's jurisdiction), J-4 | R1 |
| 6 | Home, briefing, roadmap | The timeline home, the weekly briefing with its email, the roadmap page, the calendar feed | HOM-01 to HOM-04 | R1 |
| 7 | Search and ask | Hybrid search with filters and "as of", cited answers, the evaluation gate | SRC-01 to SRC-03, SRC-05, AUD-02, J-7 | R1 |
| 8 | Register | Applicability with approval, compliance status per entity, gaps, history, internal links, entities, products, departments and teams, My work and participants, and the Statement of Applicability per entity | REG-01 to REG-03, REG-05, REG-08, HOM-05, COL-04, TEN-02, TEN-03, TEN-05, TEN-06, then the cuttable REG-04, REG-07, TEN-04, VOC-04 to VOC-06 | R2 |
| 9 | Case workflow | Triage to sign-off with evidence and the case file, with participants on cases | CAS-02 to CAS-08, COL-04 (cases), J-2, J-3 | R2 |
| 10 | Collaboration | Comments, mentions, notifications, reminders, escalation, digest, delegation, and comments and mentions on My work | COL-01, COL-02, HOM-05 (comments and mentions), VOC-03, VOC-08 | R2 |
| 11 | Tenant-controlled agents, and agent access | Definitions, tenant settings, schedules, requests, budgets, the runner adapter, re-tag batches, and a default scope from the markets. Then agent access: a bank registers the agents it runs itself, narrows each to the departments and products it serves, issues a service key or mints a personal access token, and reads what applies through an MCP server over the same API | AGT-03 to AGT-06 (including AGT-04's default market scope), PRO-04, ID-07, ID-08, then ACC-01 to ACC-09, J-11 | R2 |
| 12 | Reports, exports, import, exit | Dashboard, committee pack, exports, spreadsheet import, full tenant export and deletion | REP-01 to REP-04, AUD-04, VOC-09 | R3 |
| 13 | Integrations and enterprise access | Webhooks, tickets, SIEM stream, SSO and SCIM, IP allow-list, saved searches, attestations, waivers, private sources, remaining UI languages, and agent access write-back: the map of which application touches which register entry | INT-01 to INT-03, ID-12, ID-13, SRC-04, REG-06, WAT-06, INV-07, COL-03, I18N-02, ACC-10 | R3 |
| 14 | Hardening and assurance | OWASP review until findings converge, performance pass, `docs/assurance/`, runbooks, billing | NFR-02, NFR-04, NFR-05 | R3 |

**Descope triggers.** If a chunk runs long, cut from the bottom of its
requirement list, write what was cut into the commit body and the status
file, and move on. R1 chunks 0 to 7 are the first target for the test deploy.

**PRD 0.3 (2026-09-19).** Chunk 8's list is ordered, not just listed: HOM-05,
COL-04, TEN-02 and TEN-03 sit above the cuttable Should items (REG-04, REG-07,
VOC-04 to VOC-06), because the descope rule cuts from the bottom and priority
alone protects nothing (D-26). COL-01 stays first in chunk 10. The tasks that
carry the new requirement IDs, with their dependencies and done-conditions,
are in `docs/plans/briefs/FEATURES_0_3_TASKS.md`. Chunk 12 carries the amended
REP-02 (a dated Statement of Applicability inside the inventory export).

**PRD 0.5 (2026-09-20).** Chunk 11 gains module ACC, the agents a bank runs
itself (`docs/plans/briefs/AGENT_ACCESS.md`, D-68 to D-73, ADRs 0055 to 0057).
ACC sits **below** the AGT work in the chunk's list, so the descope rule cuts it
first: it depends on chunk 8's departments, products, teams and register and on
chunk 7's search, and it is the newest requirement in the release. If it is cut,
it moves whole to chunk 13, where ACC-10 already sits, and nothing else in
chunk 11 changes. ACC-10 is R3 either way.

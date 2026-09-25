# Pills and labels: the contract

Taken from the prototype. The build reproduces it and the agents feed it.

## Six tones

| Tone | Background token (light / dark) | Text token | Contrast light / dark | Means |
|---|---|---|---|---|
| `information` | `l3-neutral-02` | `content-neutral-01` | 16.50 / 11.69 | Neutral fact: regime, workflow status, "Guidance", "Standard", "Monitor", "Not assessed", risk, match kind |
| `notice` | `l3-notice-02` / `l3-notice-03` | `content-notice-01` | 5.67 / 5.74 | What kind of change this is, and counts: change type, "2 open changes", "6+ months", a running agent |
| `positive` | `l3-positive-02` / `l3-positive-03` | `content-positive-03` | 6.05 / 8.06 | Good on a severity scale: "Compliant", "No action", "Closed" gap, a finished run |
| `warning` | `l3-warning-02` / `l3-warning-03` | `content-warning-01` | 5.16 / 5.92 | Needs attention: "Within 3 months", "Partly compliant", "Remediating", "Waiting for approval", "Guidance, comply or explain" |
| `negative` | `l3-negative-02` / `l3-negative-03` | `content-negative-01` | 5.24 / 5.40 | Bad on a severity scale: "Act now", "Gap", an open gap, high severity |
| `brand` | `l3-brand-02` | `content-brand-02` | 5.55 / 8.87 | Identity and scope from the shared library: instrument short name, legal entity, service, client category, flags, library tags, "Lead", "Our deadline", agent version |

Token names are Green's (`--gds-sys-color-…`), with the `brand` pair
overridden in `brand.css`. Note Green's naming: `information` is the grey
one and `notice` is blue. Tenant tags use an outlined `information` pill.
Shape (foundations.md, 2026-09-19): fully rounded, 20 px tall, 8 px side
padding, the `meta` type role (13 / 18) at 500 weight, no border. shadcn's
current Badge is fully rounded too; buttons, toggles, the current nav row and
the current tab in the tab bar are 6 px, and the floating tab bar itself is
12 px, not fully rounded (`navigation.md`). So the round shape stays the
pill's alone. Was 2 by 10 px at 600.

Dark theme: the four status tones take Green's `-03` background step. At
`-02`, dark `negative` measures 4.47:1 and fails AA (dark `warning` 4.57:1,
`notice` 4.61:1, too close to the line); at `-03` the lowest is 5.40:1.
Light is unchanged. `frontend/src/components/ui/pill-tones.ts` maps one
background per tone for both themes, so it needs a dark mapping to match.

There is no seventh tone and no component accepts a colour.

## Where tone comes from

| Source | Rule |
|---|---|
| Slot | Change type is `notice`. Scope facets, instrument, flags and library tags are `brand`. Regime and workflow status are `information` |
| Kind with severity | The fixed ordinal decides: urgency (act now `negative`, within 3 months `warning`, 6+ months `notice`, monitor `information`, no action `positive`), compliance category (compliant `positive`, partly `warning`, gap `negative`, not assessed `information`), gap category (open `negative`, remediating `warning`, risk accepted `information`, closed `positive`), severity (high `negative`, medium `warning`, low `information`) |
| Kind (support access grant, c8-cards-admin) | Requested reads "Waiting for approval" `warning`; approved and inside its window reads "Active" `notice`, like a running agent; ended, revoked, declined and lapsed are `information` |
| Computed | "Waiting for approval" `warning` (a request someone else decides, such as a risk acceptance; never applicability, which one person sets, D-75), "N open changes" `notice`, "Change pending: …" `warning`, "Added when approved" and "Removed when approved" `warning`, "You" `positive` |

An admin adds a value by typing a label, its translations and a usage note.
A new compliance sub-status inherits the tone of its category.

## Case work

| Source | Rule |
|---|---|
| Slot | Workflow status stays in its `information` slot and reads the tenant's sub-status label ("Waiting for legal" under `assessing`), never a tone of its own: a sub-status changes the words, not the tone (CAS-S13) |
| Kind with severity | Evidence scan state (`ScanState` plus `pending`): pending "Being checked" `notice`, clean "Checked" `positive`, error "Could not be checked" `warning`, infected "Refused, malware found" `negative` |
| Computed | An open action whose due date is before the tenant-local today reads "Overdue" `negative`; a due date not yet passed, and any completed action, shows no pill, only the date and days left as text |

Action row order: completion, title, owner, due date, "Overdue" if it applies,
then days left or days late as text in tabular numerals.

## Slot order

| Record | Order |
|---|---|
| Change row and header | Change type, urgency, flags, then workflow status (header only), then authority and date as plain meta text |
| Obligation row | Instrument, "Guidance" if not binding ("Standard" when the binding level's kind is `standard`), applicability, compliance status if it applies, "N open changes" |
| Obligation header | Instrument, regime, binding level ("Standard" when its kind is `standard`), compliance status |
| Instrument header and row | Short name, level, binding level ("Standard" when the level's kind is `standard`), jurisdiction, regime |
| Scope block | One `brand` pill per term. "All services" when every term is selected. Plain text "Not client-specific" when the list is empty, because empty means no restriction |
| Gap | Gap status, severity, source |
| Roadmap item | Urgency or "Our deadline", then date and days left as text |

## Labels

Phrases, never codes: `new` reads "Needs triage", `signoff` reads "Waiting
for sign-off", non-binding reads "Guidance, comply or explain", and a
level whose kind is `standard` reads "Standard" in `information` in both
binding slots whatever `binding` says, because an edition of a standard is
neither law nor guidance (D-37). Vocabulary
labels come from their rows in the user's language. Computed labels come
from the message catalogs with plural forms. The API sends keys, kinds and
facts, never a phrase.

## For agents

Agents read key, label and usage note at run start, submit keys only, and
their classifications show as suggestions until a person confirms. A new
term is a proposal. A re-tag request applies a new value to existing records
as one batch proposal.

## Notification kinds (chunk 10)

A notification's pill takes its tone from its kind, a fixed code list
(`notification.kind`), never from the record it points at. Drawn in
`screens/tenant-notifications.html`.

| Kind | Tone | Label |
|---|---|---|
| `mention`, `assigned`, `participant_added` | `information` | "Mention", "Assigned to you", "Added to" |
| `signoff_requested`, `approval_requested`, `due_soon`, `review_due`, `proposal_waiting` | `warning` | "Sign-off requested", "Approval requested", "Due soon", "Review due", "Proposal waiting" |
| `overdue`, `escalation` | `negative` | "Overdue", "Escalated" |
| `involved_item_changed`, `saved_search_hit` | `notice` | "Change on your item", "New search match" |

The comments panel (`comments-and-mentions.md`), the workflow settings and the
out-of-office page add no pill.

## Chunk 11: agents, definitions, batch review and jurisdictions (c11-cards-agents-security)

Each is from the record's own facts, never chosen by a person. Where a pill above already
covers a case (agent version `brand`, a finished run `positive`, a running agent `notice`,
"Added when approved" and "Removed when approved" `warning`), the chunk 11 cards reuse it.

| Pill | Tone | Slot or kind, and why |
|---|---|---|
| Agent state: "On", "Paused", "Off" | `positive`, `warning`, `information` | Kind (a bank's own agent). On is the working state; Paused needs attention because nothing runs until someone resumes it; Off is a neutral fact (`admin-agents.html`) |
| Run status: "Done", "Running", "Stopped", "Failed" | `positive`, `notice`, `warning`, `negative` | Kind (agent run), a severity scale. Done and Running are the finished run and the running agent above; Stopped was interrupted by a person; Failed did not finish (`admin-agents.html`, `console-agent-definitions.html`) |
| Jurisdiction on an agent: "EU", "Sweden", … | `brand` | Slot: a scope facet, what the agent covers or sweeps |
| Definition scope: "Platform", "For banks" | `information` | Slot: a neutral fact about who runs the definition (`console-agent-definitions.html`) |
| Definition state: "Active", "Draft" | `positive`, `information` | Kind: a published current version, or none yet |
| Version state: "Current", "Retired" | `positive`, `information` | Kind: the version new runs use, or one no run starts on again |
| Proposal kind "Re-tag" | `notice` | Slot: the proposal kind, as every kind in the queue (`console-queue-batch.html`) |
| Batch and row status: "Waiting", "Approved", "Rejected" | `warning`, `positive`, `information` | The queue's own statuses (`console-queue.html`), applied to the batch and to each row |
| Library tag in a batch's before and after | `brand` | Slot: library tags, as above |
| Jurisdiction row: the label, "Retired", "Rename waiting for review" | `brand`, `information`, `warning` | The label is a scope facet; Retired is a neutral fact; waiting for review is computed from the open proposal, like "Waiting for approval" (`admin-vocabulary.html` console variant) |

`admin-security.html` adds no pill: every state there is a sentence.

## Agent access: entries, credentials and reach (acc-cards)

From the record's own facts, never chosen by a person. Revoked and Expired reuse the chunk 1
API keys card's tones.

| Pill | Tone | Slot or kind, and why |
|---|---|---|
| Entry state: "Active", "Revoked" | `positive`, `information` | Kind (an agent access entry). Active is the working state; Revoked is a neutral fact, since a revoked entry is kept, read-only, and never comes back (`admin-agent-access.html`) |
| What an entry reads now: "Reads our register", "Library only" | `notice`, `information` | Computed from both halves of tenant reach (ACC-08): on only when the organisation's switch and the entry's own toggle are both on. Reads our register is `notice`, a fact worth seeing because the bank's own judgement leaves the zone; Library only is the neutral default. With the organisation's switch off every entry reads Library only, whatever its own toggle says |
| Department and product on an entry | `brand` | Slot: scope facets, as the scope block above. Naming none renders plain text "All of our regulatory scope", because empty means no narrowing |
| Credential kind: "Service", "Personal" | `information` | Kind (`api_key.kind`), a neutral fact about who the credential reads as: an entry or an integration, or a person (`admin-agent-access.html`, `admin-api-keys.html`). `me-tokens.html` shows none, since every row there is personal |
| Credential state: "Revoked", "Expired" | `information`, `warning` | From the credential's facts, as on the chunk 1 API keys card |
| Scope on a credential: "library read", … | `information` | Slot: a neutral fact, as on the chunk 1 API keys card |

`admin-security.html`'s tenant reach panel adds no pill: every state there is a sentence, and a
request waiting for its second person is a warning banner naming who asked.

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
| Computed | "Waiting for approval" and "Change waiting for approval" `warning`, "N open changes" `notice`, "Change pending: …" `warning`, "Added when approved" and "Removed when approved" `warning`, "You" `positive` |

An admin adds a value by typing a label, its translations and a usage note.
A new compliance sub-status inherits the tone of its category.

## Slot order

| Record | Order |
|---|---|
| Change row and header | Change type, urgency, flags, then workflow status (header only), then authority and date as plain meta text |
| Obligation row | Instrument, "Guidance" if not binding ("Standard" when the binding level's kind is `standard`), applicability, compliance status if it applies, "Change waiting for approval", "N open changes" |
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

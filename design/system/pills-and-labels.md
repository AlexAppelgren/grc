# Pills and labels: the contract

Taken from the prototype. The build reproduces it and the agents feed it.

## Six tones

| Tone | Background token | Text token | Means |
|---|---|---|---|
| `information` | `l3-neutral-02` | `content-neutral-01` | Neutral fact: regime, workflow status, "Guidance", "Monitor", "Not assessed", risk, match kind |
| `notice` | `l3-notice-02` | `content-notice-01` | What kind of change this is, and counts: change type, "2 open changes", "6+ months", a running agent |
| `positive` | `l3-positive-02` | `content-positive-03` | Good on a severity scale: "Compliant", "No action", "Closed" gap, a finished run |
| `warning` | `l3-warning-02` | `content-warning-01` | Needs attention: "Within 3 months", "Partly compliant", "Remediating", "Waiting for approval", "Guidance, comply or explain" |
| `negative` | `l3-negative-02` | `content-negative-01` | Bad on a severity scale: "Act now", "Gap", an open gap, high severity |
| `brand` | `l3-brand-02` | `content-brand-02` | Identity and scope from the shared library: instrument short name, legal entity, service, client category, flags, library tags, "Lead", "Our deadline", agent version |

Token names are Green's (`--gds-sys-color-…`), with the `brand` pair
overridden in `brand.css`. Note Green's naming: `information` is the grey
one and `notice` is blue. Tenant tags use an outlined `information` pill.
Shape: fully rounded, 2 px by 10 px padding, 600 weight, the `meta` type
role. There is no seventh tone and no component accepts a colour.

## Where tone comes from

| Source | Rule |
|---|---|
| Slot | Change type is `notice`. Scope facets, instrument, flags and library tags are `brand`. Regime and workflow status are `information` |
| Kind with severity | The fixed ordinal decides: urgency (act now `negative`, within 3 months `warning`, 6+ months `notice`, monitor `information`, no action `positive`), compliance category (compliant `positive`, partly `warning`, gap `negative`, not assessed `information`), gap category (open `negative`, remediating `warning`, risk accepted `information`, closed `positive`), severity (high `negative`, medium `warning`, low `information`) |
| Computed | "Waiting for approval" and "Change waiting for approval" `warning`, "N open changes" `notice`, "Change pending: …" `warning`, "You" `positive` |

An admin adds a value by typing a label, its translations and a usage note.
A new compliance sub-status inherits the tone of its category.

## Slot order

| Record | Order |
|---|---|
| Change row and header | Change type, urgency, flags, then workflow status (header only), then authority and date as plain meta text |
| Obligation row | Instrument, "Guidance" if not binding, applicability, compliance status if it applies, "Change waiting for approval", "N open changes" |
| Obligation header | Instrument, regime, binding level, compliance status |
| Scope block | One `brand` pill per term. "All services" when every term is selected. Plain text "Not client-specific" when the list is empty, because empty means no restriction |
| Gap | Gap status, severity, source |
| Roadmap item | Urgency or "Our deadline", then date and days left as text |

## Labels

Phrases, never codes: `new` reads "Needs triage", `signoff` reads "Waiting
for sign-off", non-binding reads "Guidance, comply or explain". Vocabulary
labels come from their rows in the user's language. Computed labels come
from the message catalogs with plural forms. The API sends keys, kinds and
facts, never a phrase.

## For agents

Agents read key, label and usage note at run start, submit keys only, and
their classifications show as suggestions until a person confirms. A new
term is a proposal. A re-tag request applies a new value to existing records
as one batch proposal.

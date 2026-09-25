# Brand

**Logo.** The phonetic wordmark `[blɛkː]`, outlined from Noto Sans Mono at
weight 500 with 0.04 em tracking, so it needs no font. `logo-phonetic.svg`
uses `currentColor`. The green and sand files are for places that cannot set
a colour (email, the favicon's neighbours). Accessible name: "bleqq,
pronounced blek". Keep clear space of one bracket width around it.
`favicon.svg` is the open e on a rounded square.

**Brand layer.** The prototype's green (`#003824`) and its brass pair
(`#efe9dc`, `#685631`) are SEB's brand token values, so `brand.css` overrides
them. Placeholders until Alex chooses (DECISIONS D-05), checked for WCAG AA:

| Variable overridden | Light | Dark | Check |
|---|---|---|---|
| `l1-brand-01`, `l2-brand-01`, `l3-brand-01`, `content-brand-01` (the green) | `#0a3a2a` | keep Green's dark values | White on it 12.7:1, sand on it 10.1:1 |
| `l2-brand-02` (sand surface) | `#f6f3ec` | keep | |
| `l3-brand-02` (brass pill background) | `#ece5d6` | `#33291a` | |
| `content-brand-02` (brass pill text) | `#6a5730` | `#d9cba9` | 5.6:1 light, 8.9:1 dark |

Look up the full list of `brand` variables with the Green MCP `get_tokens`
tool and override every one, so no SEB brand value survives by accident.

**Type.** Hanken Grotesk (text) and Noto Sans Mono (legal references,
wordmark), both under the SIL Open Font License. Self-host them. SEB's own
typeface is never used. Public pages only, and never behind sign-in: Libre
Caslon Display for plate headlines and Libre Caslon Text for section headings,
ledes and questions, both SIL OFL (approved with the public page by Alex,
2026-09-24; `design/public/README.md`).

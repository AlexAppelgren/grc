# Design

| Path | What it is |
|---|---|
| `prototype/index.html` | The interactive prototype ("bleqq: compliance inventory and watch"). Open it in a browser. It is the contract for flow, wording, labels and pills. Its sample data seeds `seed_e2e` and `seed_demo` |
| `system/pills-and-labels.md` and `.html` | The pill and label contract, and a rendered card |
| `brand/` | The phonetic wordmark `[blɛkː]`, the favicon, and the brand layer placeholders |
| `screens/` | Empty. Cut one card per screen from the prototype as each chunk starts (playbook Section 7) |

## Direction (already chosen)

Timeline home showing the next dates as the same short list on phone and
desktop, with part of the weekly briefing on it and the full briefing one tap
away. The full calendar lives on its own roadmap page, where a card expands
in place. Restraint in the style of wealth and asset management: a very dark
green, sand surfaces, brass for identity, Hanken Grotesk for text and Noto
Sans Mono for legal references and the wordmark. Phone first. On phones,
actions sit on the right, two buttons share one row, primary on the right.

## Where the prototype is wrong or silent

| Topic | What to do |
|---|---|
| The tenant's compliance officer approves agent proposals into the inventory | Wrong for a shared library. The queue moves to the platform console (`library_editor`). Tenants see library updates and report problems |
| "Switch user" | Prototype device only. Replace with real sign-in |
| Footprint toggles apply at once | Becomes a request with a preview and a second person |
| `UCLASS` maps the label "Act now" to a colour, and urgency and change type are stored as labels | Store keys. Tone comes from slot or kind |
| Obligation `tags` feed search but never render | Render library tags as `brand` pills after the flags, tenant tags as outlined `information` pills |
| Colours are hex values copied from Green | Import the tokens, override the brand pair |

## Screens the prototype lacks

Design each as a card in the prototype's language before building it.

- **Sign-in and enrolment:** invitation landing, code entry, passkey
  enrolment with the prompt for a second passkey, passkey sign-in, step-up
  prompt, "ask your admin" recovery, my passkeys, my sessions.
- **Tenant admin:** organisation (entities, licences, products, teams),
  members and invitations with re-enrolment and bulk reassignment, roles from
  permissions, vocabularies, workflow policy, security policy, agents,
  integrations and API keys, data (import, export, retention), support access.
- **Platform console:** proposal queue with the source beside the diff,
  library vocabularies, sources and coverage, languages and jurisdictions,
  agent definitions and versions, evaluation sets, problem reports, tenants
  and plans, system health.
- **Vocabulary management:** the list of lists, rows rendered as the real
  pill in light and dark with usage count, inline rename, reorder, retire,
  merge, and "create where you use it" inside pickers.
- **States:** empty, loading, error and denied for every screen. The
  prototype shows few of them.

import type { CSSProperties } from 'react';

import { pillTones, type PillTone } from './pill-tones';

// Prototype `.dates i` (design/screens/tenant-today.html, tenant-briefing.html):
// the "Coming up" list marks its urgency by a small solid dot rather than a
// pill, so the list reads as data and not as a row of coloured headlines.
// The colour is still the tone a presentation function chose — never picked
// here — so it uses the pill's own strong (`text`) token for a solid fill.
export function ToneDot({ tone }: { tone: PillTone }) {
  const { text } = pillTones[tone];
  const style: CSSProperties = { background: `var(${text})` };
  return <i aria-hidden="true" className="mt-1.5 block size-2 shrink-0 rounded-full" style={style} />;
}

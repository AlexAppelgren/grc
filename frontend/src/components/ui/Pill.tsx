import type { CSSProperties, ReactNode } from 'react';

import { pillTones, type PillTone } from './pill-tones';

export type { PillTone } from './pill-tones';
export { pillToneNames } from './pill-tones';

export interface PillProps {
  /** One of the six tones. Chosen by slot or kind in a presentation function, never by a person. */
  tone: PillTone;
  /** Tenant tags render outlined, so `brand` keeps meaning "from the shared library". */
  outlined?: boolean;
  children: ReactNode;
}

// The one pill component (playbook 6.7). Shape from the prototype: fully
// rounded, 2px by 10px padding, 600 weight, the `meta` type role. Colours are
// the token pair of the tone, read at render time so light and dark follow
// the tokens. No className, no colour prop.
export function Pill({ tone, outlined = false, children }: PillProps) {
  const { background, text } = pillTones[tone];
  const style: CSSProperties = outlined
    ? { color: `var(${text})`, background: 'transparent', boxShadow: `inset 0 0 0 1px var(${text})` }
    : { color: `var(${text})`, background: `var(${background})` };
  return (
    <span
      data-pill={tone}
      data-outlined={outlined ? '' : undefined}
      className="inline-block rounded-full px-2.5 py-0.5 text-meta font-semibold whitespace-nowrap"
      style={style}
    >
      {children}
    </span>
  );
}

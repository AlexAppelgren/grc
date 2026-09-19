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

// The one pill component (playbook 6.7). Shape from foundations.md (shadcn's
// Badge): fully rounded, 20px tall, 8px side padding, the `meta` role at 500,
// no border. Colours are the token pair of the tone. The background is
// light-dark(), which follows the nearest theme class through color-scheme
// (theme.css), so a .dark swatch inside a light page still gets the dark
// step. No className, no colour prop.
export function Pill({ tone, outlined = false, children }: PillProps) {
  const { background, darkBackground, text } = pillTones[tone];
  const style: CSSProperties = outlined
    ? { color: `var(${text})`, background: 'transparent', boxShadow: `inset 0 0 0 1px var(${text})` }
    : { color: `var(${text})`, background: `light-dark(var(${background}), var(${darkBackground}))` };
  return (
    <span
      data-pill={tone}
      data-outlined={outlined ? '' : undefined}
      className="inline-flex h-5 items-center rounded-full px-2 text-meta font-medium whitespace-nowrap"
      style={style}
    >
      {children}
    </span>
  );
}

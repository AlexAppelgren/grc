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
// Badge): fully rounded, 20px tall on one line, 8px side padding, the `meta` role at 500,
// no border. Colours are the token pair of the tone. The background is
// light-dark(), which follows the nearest theme class through color-scheme
// (theme.css), so a .dark swatch inside a light page still gets the dark
// step. No className, no colour prop.
//
// A label wider than its container wraps inside the pill rather than running
// past the card (an instrument's short name may be 120 characters): the pill
// is never wider than its container and grows a line at a time. The 10px
// radius is half the one-line height, so a one-line pill is still fully
// rounded, and the text never reaches past a corner of a taller one. It does
// not shrink beside other content, so a short pill keeps its one line.
export function Pill({ tone, outlined = false, children }: PillProps) {
  const { background, darkBackground, text } = pillTones[tone];
  const style: CSSProperties = outlined
    ? { color: `var(${text})`, background: 'transparent', boxShadow: `inset 0 0 0 1px var(${text})` }
    : { color: `var(${text})`, background: `light-dark(var(${background}), var(${darkBackground}))` };
  return (
    <span
      data-pill={tone}
      data-outlined={outlined ? '' : undefined}
      className="inline-flex max-w-full shrink-0 items-center rounded-[10px] px-2 py-px text-meta font-medium wrap-anywhere"
      style={style}
    >
      {children}
    </span>
  );
}

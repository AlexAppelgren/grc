import type { ReactNode } from 'react';

import { cn } from '@/shared/utils/cn';

// The card's `.swatch.light` / `.swatch.dark`
// (design/screens/admin-vocabulary.html): a fixed-theme frame so an admin
// sees the value's real pill in both themes whatever theme they are in.
// Themes switch on the class and the theme utilities are `inline`, so a
// wrapper re-themes everything inside it (styles/theme.css).

export function Swatch({ scheme, className, children }: { scheme: 'light' | 'dark'; className?: string; children: ReactNode }) {
  return (
    <span className={cn(scheme, 'inline-flex items-center rounded-control border border-line bg-page px-1.5 py-1', className)} data-swatch={scheme}>
      {children}
    </span>
  );
}

/** Both swatches side by side: how every vocabulary row and the add form show a value. */
export function SwatchPair({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5" data-swatch-pair="">
      <Swatch scheme="light">{children}</Swatch>
      <Swatch scheme="dark">{children}</Swatch>
    </span>
  );
}

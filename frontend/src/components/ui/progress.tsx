'use client';

import * as ProgressPrimitive from '@radix-ui/react-progress';
import type { HTMLAttributes } from 'react';

import { cn } from '@/shared/utils/cn';

// shadcn/ui's Progress on the Radix Progress, in our colours (read from
// github.com/shadcn-ui/ui, apps/v4/registry/new-york-v4/ui/progress.tsx): an
// 8px bar, fully rounded, the meter track (neutral-soft) filled with the
// product accent, green in light and brass in dark. Radix gives the
// progressbar role and reads the value out as a percentage. The bar says how
// much, never of what, so the caller names it. Other attributes (a data- hook,
// aria-valuetext in the caller's own words) pass through to the element.

type Named = { 'aria-label': string } | { 'aria-labelledby': string };

export type ProgressProps = Omit<HTMLAttributes<HTMLDivElement>, 'role' | 'children'> &
  Named & {
    value: number;
    /** What `value` is a part of. Left out it is 100, and `value` a percentage. */
    max?: number;
  };

export function Progress({ value, max = 100, className, ...rest }: ProgressProps) {
  // The part done, as a percentage. A count past its max reads as full, and a
  // whole of nothing as empty: there is nothing to divide by.
  const percent = max > 0 ? Math.min(Math.max((value / max) * 100, 0), 100) : 0;
  return (
    <ProgressPrimitive.Root data-slot="progress" value={percent} className={cn('h-2 w-full overflow-hidden rounded-full bg-neutral-soft', className)} {...rest}>
      <ProgressPrimitive.Indicator data-slot="progress-indicator" className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
    </ProgressPrimitive.Root>
  );
}
